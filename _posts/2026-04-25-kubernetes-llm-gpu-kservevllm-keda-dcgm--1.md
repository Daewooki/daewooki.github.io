---
title: "Kubernetes에서 LLM 서빙을 “GPU 기준”으로 오토스케일링하기: KServe(vLLM) + KEDA + DCGM, 그리고 노드까지 따라오는 설계(2026년 4월)"
date: 2026-04-25 03:20:30 +0900
categories: [Infra, Kubernetes]
tags: [infra, kubernetes, trend, 2026-04]
---

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>

## 들어가며
LLM inference는 CPU 웹서비스처럼 “QPS만 보고” HPA로 늘리면 자주 망합니다. 이유는 간단합니다. **스파이크가 오면 GPU가 포화되기 전에 이미 큐(대기 요청)가 쌓이고, 새 Pod는 뜨자마자 바로 처리 못 하는 경우(모델 로딩, KV cache warm-up)가 많기 때문**입니다. Red Hat/IBM 사례에서도 “새 Pod가 모델을 GPU 메모리에 올릴 때까지는 트래픽을 못 받는다”는 점을 반복해서 강조합니다. ([developers.redhat.com](https://developers.redhat.com/articles/2025/11/26/autoscaling-vllm-openshift-ai-model-serving?utm_source=openai))

그래서 2026년 4월 기준 “실전”에서 가장 많이 채택되는 패턴은:
- **(Pod 오토스케일)** KServe + KEDA로 *request/queue 기반* 스케일링 (vLLM의 `num_requests_waiting` 같은 지표) ([kserve.github.io](https://kserve.github.io/kserve/?utm_source=openai))  
- **(GPU 지표 수집)** NVIDIA DCGM Exporter를 DaemonSet으로 깔고 Prometheus가 스크랩 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))  
- **(노드 오토스케일)** Cluster Autoscaler 또는 Karpenter 계열로 GPU 노드를 따라 늘림(단, 노드 프로비저닝은 분 단위라 “스파이크 흡수”는 Pod 레벨에서 먼저 해야 함) ([sedai.io](https://sedai.io/blog/ultimate-guide-to-gpu-scaling-karpenter?utm_source=openai))

언제 쓰면 좋나:
- **트래픽 변동이 큰 LLM API**, multi-tenant inference, “낮엔 바쁘고 밤엔 한가한” 서비스
- SLO(예: TTFT/latency) 관리가 필요하고, *비용을 위해* scale-to-zero/최소 GPU를 고민할 때

언제 쓰면 안 되나(혹은 신중히):
- **초저지연(수 초 이내 노드 증설이 불가능한 수준의) 스파이크**를 “오토스케일만으로” 해결하려는 경우  
- **GPU time-slicing**을 켜고 “컨테이너 단위 GPU 메트릭”으로 정교하게 스케일링하려는 경우(DCGM Exporter 제한이 문서에 명시됨) ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/24.3.0/gpu-sharing.html?utm_source=openai))  

---

## 🔧 핵심 개념
### 1) “GPU utilization 기반 스케일링”이 LLM에 자주 늦는 이유
DCGM Exporter → Prometheus scrape → KEDA polling → HPA 반영까지 **측정/전파 지연**이 생깁니다. 실제로 커뮤니티에서도 “스크랩/반응 지연 때문에 스파이크를 놓친다”는 피드백이 나옵니다. ([reddit.com](https://www.reddit.com/r/kubernetes/comments/1sd7zyr/keda_gpu_scaler_autoscale_vllmtriton_inference/?utm_source=openai))  
게다가 LLM은 **input 길이/출력 토큰/동시성**에 따라 처리량이 요동치므로, “GPU util 80% 넘으면 scale” 같은 정책이 SLO 관점에서 둔합니다. ([developers.redhat.com](https://developers.redhat.com/articles/2025/09/23/how-set-kserve-autoscaling-vllm-keda?utm_source=openai))

### 2) LLM 서빙에서 더 나은 신호: “큐/대기 요청” (work-conserving 지표)
vLLM은 서빙 내부 큐/동시 처리 상황을 지표로 내보내고, KServe는 이를 **Prometheus 기반 KEDA autoscaling**으로 연결하는 가이드를 제공합니다. 예시로 `vllm:num_requests_running`, `vllm:num_requests_waiting` 같은 메트릭을 직접 스케일 트리거로 사용합니다. ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))  
이 접근의 장점:
- GPU가 아직 70%라도 **대기 요청이 늘면 미리 스케일 아웃**
- 반대로 GPU util이 순간 90%여도 **대기 큐가 0이면** 무작정 증설하지 않도록 설계 가능

### 3) KServe + KEDA의 구조(흐름)
흐름을 “제어면/데이터면”으로 쪼개면 이해가 쉽습니다.

- **데이터면**: 사용자 요청 → KServe ingress/gateway → predictor(vLLM) Pod
- **관측**: vLLM / DCGM Exporter가 `/metrics`로 Prometheus 형식 노출 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))  
- **제어면(스케일)**: KEDA가 Prometheus query를 주기적으로 평가 → External Metrics로 HPA에 전달 → Deployment/InferenceService replica 변경 ([keda.sh](https://keda.sh/docs/2.19/scalers/prometheus/?utm_source=openai))  

여기서 중요한 차이점:
- “KServe autoscaling”은 결국 내부적으로 KEDA/HPA를 활용하는 형태가 많고, generative workload에 맞춘 request-based 접근을 강조합니다. ([kserve.github.io](https://kserve.github.io/kserve/?utm_source=openai))  

---

## 💻 실전 코드
아래 예제는 “현실적인” 상황(모델이 크고, cold start가 비싸며, 트래픽이 출렁임)을 가정합니다.

- **목표**:  
  1) KServe로 vLLM 기반 LLM endpoint 배포  
  2) `vllm:num_requests_waiting` 기반으로 KEDA가 Pod 스케일  
  3) (선택) GPU util 기반 스케일도 보조로 걸 수 있게 토대 마련(DCGM)

### 단계 0) 전제(의존성)
- Kubernetes 클러스터에 GPU 노드 존재
- NVIDIA GPU Operator 또는 동등한 드라이버/디바이스플러그인 설치(DCGM Exporter를 같이 깔면 더 편함) ([docs.nvidia.com](https://docs.nvidia.com/enterprise-reference-architectures/observability-guide.pdf?utm_source=openai))  
- Prometheus가 있고, KEDA가 설치되어 있어야 함(KEDA Prometheus scaler 사용) ([keda.sh](https://keda.sh/docs/2.19/scalers/prometheus/?utm_source=openai))  

### 단계 1) KServe InferenceService (vLLM)
> KServe는 vLLM 등 “optimized backend”와 generative inference autoscaling을 문서로 안내합니다. ([kserve.github.io](https://kserve.github.io/kserve/?utm_source=openai))

```yaml
# llm-isvc.yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: llama3-8b
  namespace: llm
  annotations:
    serving.kserve.io/autoscalerClass: "keda"
spec:
  predictor:
    # 운영에서는 대개 RawDeployment가 디버깅/튜닝이 쉬움(멀티GPU/멀티노드도 RawDeployment에 제약이 있음)
    # multi-node가 필요하면 RawDeployment만 지원된다는 문서도 참고. ([kserve.github.io](https://kserve.github.io/archive/0.15/modelserving/v1beta1/llm/huggingface/multi-node?utm_source=openai))
    containers:
    - name: vllm
      image: vllm/vllm-openai:latest
      args:
        - "--model"
        - "meta-llama/Meta-Llama-3-8B-Instruct"
        - "--served-model-name"
        - "llama3-8b"
        - "--port"
        - "8000"
        # 트래픽 스파이크 완충을 위해 동시성/배치 관련 옵션은 환경에 맞게 튜닝
      ports:
        - containerPort: 8000
      resources:
        limits:
          nvidia.com/gpu: "1"
        requests:
          nvidia.com/gpu: "1"
      env:
        # Hugging Face 토큰 등은 Secret로 관리 권장
        - name: HF_TOKEN
          valueFrom:
            secretKeyRef:
              name: hf-token
              key: token
```

예상 동작:
- `kubectl -n llm get pods`에서 predictor Pod가 뜨고
- OpenAI-compatible endpoint로 호출 가능(KServe가 이 프로토콜을 강조) ([kserve.github.io](https://kserve.github.io/kserve/?utm_source=openai))

### 단계 2) KEDA ScaledObject: “대기 요청 수” 기반 스케일
KServe/Red Hat 문서에서 핵심으로 미는 방식이 **vLLM queue depth(`num_requests_waiting`)** 입니다. ([zartis.com](https://www.zartis.com/scaling-llm-workloads-on-kubernetes-a-production-engineers-guide/?utm_source=openai))

```yaml
# keda-vllm-queue-scaledobject.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: llama3-8b-queue
  namespace: llm
spec:
  scaleTargetRef:
    kind: Deployment
    name: llama3-8b-predictor   # 실제 생성되는 이름은 환경/모드에 따라 다를 수 있어 확인 필요
  minReplicaCount: 1
  maxReplicaCount: 6
  pollingInterval: 5           # 너무 짧게 하면 Prometheus/adapter 비용↑, 너무 길면 반응성↓
  cooldownPeriod: 120          # 모델 로딩 비용이 큰 LLM은 과도한 scale-in을 막는 게 보통 유리
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://kube-prometheus-stack-prometheus.monitoring:9090
      metricName: vllm_requests_waiting
      # 핵심: (전체 대기 요청 합) / (현재 replica 수) 가 임계치 넘으면 scale-out
      # 라벨은 실제 vLLM metrics 라벨(pod, namespace 등)에 맞게 조정
      query: |
        sum(vllm:num_requests_waiting{namespace="llm", service="llama3-8b"}) 
        / 
        max(count(up{namespace="llm", job=~".*llama3-8b.*"}), 1)
      threshold: "2"
```

예상 출력(관찰 포인트):
- `kubectl -n llm describe scaledobject llama3-8b-queue`에서 KEDA가 metric을 찾고 HPA가 붙습니다(유사 로그/상태는 AKS 가이드에도 나옵니다). ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/aks/autoscale-gpu-workloads-with-keda?utm_source=openai))  
- 부하를 주면 replica가 1→N으로 늘고, 부하가 빠지면 cooldown 이후 줄어듭니다.

### 단계 3) (선택) DCGM 기반 “GPU util”은 보조 신호로만
DCGM Exporter는 GPU 텔레메트리를 `/metrics`로 노출하고, Kubernetes에서 DaemonSet으로 배포하는 전형적인 구성이 문서화되어 있습니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))  
다만 LLM은 queue 신호가 더 직접적이므로, GPU util은 “과열 방지/안전장치” 정도로 섞는 것을 권합니다.

```yaml
# keda-gpu-util-scaledobject.yaml (보조 스케일: GPU util이 계속 높을 때만 완만히 스케일)
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: llama3-8b-gpu-util
  namespace: llm
spec:
  scaleTargetRef:
    kind: Deployment
    name: llama3-8b-predictor
  minReplicaCount: 1
  maxReplicaCount: 6
  pollingInterval: 15
  cooldownPeriod: 180
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://kube-prometheus-stack-prometheus.monitoring:9090
      metricName: dcgm_gpu_util
      # DCGM 메트릭 이름/라벨은 배포 설정에 따라 다를 수 있음(대시보드/문서로 확인)
      # 예: DCGM_FI_DEV_GPU_UTIL
      query: |
        avg(DCGM_FI_DEV_GPU_UTIL{namespace="gpu-operator"}) / 100
      threshold: "0.85"
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “노드 스케일”은 별개의 문제로 분리하라
Pod 스케일은 초~수십 초, GPU 노드 프로비저닝은 보통 분 단위입니다. EKS에서 Karpenter를 쓸 때도 “미리 ASG를 맞춰두는 Cluster Autoscaler 방식의 한계(특정 GPU 타입 없으면 Pending)”가 자주 언급됩니다. ([sedai.io](https://sedai.io/blog/ultimate-guide-to-gpu-scaling-karpenter?utm_source=openai))  
권장:
- **(Pod) 큐 기반 KEDA로 먼저 흡수**
- **(Node) Karpenter/CA로 천천히 따라오게** 설계
- 최악의 스파이크를 위해 “baseline GPU(최소 노드/최소 replica)”는 남겨두기

### Best Practice 2) cooldown/scale-down을 공격적으로 하지 마라(LLM은 cold start가 비싸다)
vLLM Pod는 뜬 뒤 모델 웨이트 로딩이 끝나야 트래픽을 처리합니다. 즉, **너무 빨리 줄이면** 다음 스파이크 때 TTFT/SLO가 박살납니다. ([developers.redhat.com](https://developers.redhat.com/articles/2025/11/26/autoscaling-vllm-openshift-ai-model-serving?utm_source=openai))  
실무적으로는:
- scale-out은 빠르게, scale-in은 느리게(긴 cooldown, 안정화 윈도우)
- 모델 파일을 로컬 SSD 캐시/공유 스토리지 전략으로 최적화(단, 공유 스토리지 병목 주의)

### 함정 1) GPU time-slicing 켠 뒤 “컨테이너별 GPU 메트릭”을 기대
NVIDIA GPU Operator 문서에 **time-slicing 시 DCGM Exporter가 컨테이너에 메트릭을 연결하지 못한다**는 제한이 명시되어 있습니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/24.3.0/gpu-sharing.html?utm_source=openai))  
즉, “Pod별 GPU util 기반 오토스케일”을 정밀하게 하고 싶다면:
- MIG(하드 파티셔닝) 쪽으로 가거나
- 아예 queue 기반으로 스케일하고 GPU util은 노드/풀 수준으로만 보거나
- (실험적) NVML 직접 수집처럼 파이프라인을 줄이는 접근을 검토(커뮤니티/문서화된 시도 존재) ([researchgate.net](https://www.researchgate.net/publication/403529195_keda-gpu-scaler?utm_source=openai))  

### 함정 2) “GPU util = 성능”으로 착각
LLM은 토큰 생성 특성상 **GPU util이 높아도** SLO가 이미 깨졌을 수 있고(큐가 쌓였을 수 있음), 반대로 util이 낮아도 latency가 나쁠 수 있습니다(메모리/IO/컨텍스트 스위칭/배치 정책). 그래서 2026년 연구/실무 흐름이 “lagging indicator(util) 대신 request/토큰 처리율 같은 신호”를 강조하는 쪽으로 가는 중입니다. ([arxiv.org](https://arxiv.org/abs/2512.03416?utm_source=openai))  

---

## 🚀 마무리
정리하면, 2026년 4월 기준 Kubernetes에서 LLM 서빙 GPU 오토스케일을 “프로덕션답게” 하려면:

- **1순위 스케일 신호**: GPU util보다 **queue/request 기반(vLLM metrics)** ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))  
- **구성의 표준 조합**: KServe(서빙/컨트롤 플레인) + KEDA(Prometheus scaler) + DCGM Exporter(GPU 관측) ([kserve.github.io](https://kserve.github.io/kserve/?utm_source=openai))  
- **도입 판단 기준**:
  - “스파이크가 잦고 비용이 민감”하면 강력 추천
  - “항상 일정 트래픽 + 고정 GPU”면 굳이 복잡도를 올릴 이유가 적음
  - time-slicing/MIG 같은 **GPU 공유 전략**이 들어가면 메트릭/격리/과금(내부 쇼백)까지 같이 설계해야 함 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/24.3.0/gpu-sharing.html?utm_source=openai))  

다음 학습 추천(바로 실무에 도움 되는 순서):
1) KServe generative autoscaling 문서(어떤 vLLM 메트릭으로 스케일할지) ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))  
2) KEDA Prometheus scaler 인증/TriggerAuthentication 패턴 ([keda.sh](https://keda.sh/docs/2.19/scalers/prometheus/?utm_source=openai))  
3) DCGM Exporter 메트릭 카탈로그/대시보드로 “내 클러스터에서 어떤 라벨로 보이는지” 확정 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))  

원하면, (1) EKS+Karpenter 또는 (2) GKE DCGM managed Prometheus 또는 (3) AKS KEDA 가이드 중 하나로 클라우드별로 YAML/라벨/권한(Workload Identity)까지 맞춘 “실제 적용 버전”으로 변환해 드릴까요? ([cloud.google.com](https://cloud.google.com/kubernetes-engine/docs/how-to/dcgm-metrics?utm_source=openai))