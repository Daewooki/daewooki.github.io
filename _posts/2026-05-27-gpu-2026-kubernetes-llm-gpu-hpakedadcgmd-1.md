---
title: "GPU 오토스케일링 2026: Kubernetes에서 LLM 서빙을 “GPU 기준”으로 제대로 스케일하는 법 (HPA/KEDA/DCGM/DRA/MIG 실전 조합)"
date: 2026-05-27 04:27:23 +0900
categories: [Infra, Kubernetes]
tags: [infra, kubernetes, trend, 2026-05]
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
LLM inference를 Kubernetes에 올리면, 첫 번째로 부딪히는 벽이 **“CPU는 놀고 있는데 GPU는 이미 포화인데도 HPA가 안 늘어난다”**입니다. HPA 기본 신호(CPU/Memory)는 LLM 서빙의 병목(대부분 GPU, KV cache, batch/queue)에 둔감합니다. 그래서 *스케일 아웃 타이밍이 늦고*, TTFT(Time To First Token)나 tail latency가 급격히 악화됩니다.

**언제 쓰면 좋나**
- vLLM/TGI/Triton/SGLang 같은 **GPU 기반 LLM 서빙**에서 트래픽이 변동(버스트/야간)하고 비용이 민감할 때
- “GPU utilization” 또는 “queue depth(대기열)” 같은 **서빙-특화 신호**로 replica를 조절하고 싶을 때
- scale-to-zero(또는 1)까지 내려 **GPU 비용을 적극 절감**하고 싶을 때(KEDA 계열)

**언제 쓰면 안 되나**
- 모델 로딩이 길고(수 분), GPU 노드 프로비저닝도 느려서(수 분) **리액티브 스케일링만으로 SLO를 못 맞추는** 경우  
  → 이때는 “예측 + 워밍풀” 또는 LLM-aware autoscaling이 필요합니다(아래에서 Dynamo Planner 언급).
- GPU를 잘게 쪼개 공유해야 하는데(멀티테넌트), 현재 클러스터가 **MIG/DRA 같은 장치 계층 설계**가 준비되지 않은 경우  
  → 오토스케일보다 먼저 “할당 단위(whole GPU vs MIG vs time-slicing)”부터 정해야 합니다.

---

## 🔧 핵심 개념
### 1) “Pod autoscaling”은 결국 **신호(signal)** 싸움이다
LLM 서빙에서 흔한 스케일링 신호는 세 계열입니다.

1. **GPU utilization 기반**
   - DCGM exporter의 `DCGM_FI_DEV_GPU_UTIL` 같은 메트릭을 사용해 HPA/KEDA로 스케일  
   - 장점: 인프라 관점에서 단순, “GPU가 바쁘면 늘린다”는 직관  
   - 단점: LLM은 **GPU util이 낮아도 queue가 쌓일 수 있고**, 반대로 util이 높아도 batching 덕에 지연이 안정적일 수 있습니다. 즉 SLO 직접 최적화가 어렵습니다. (DCGM exporter 자체는 Kubernetes DaemonSet로 운영 가능) ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))

2. **애플리케이션 메트릭 기반(권장)**
   - vLLM의 `/metrics`(Prometheus 포맷)에서 `vllm:num_requests_waiting` 같은 **대기열/백로그** 지표로 스케일  
   - 장점: “지금 사용자 요청이 밀리냐”를 더 직접 반영  
   - 단점: 서빙 프레임워크별 지표 해석/임계값 튜닝이 필요  
   vLLM production-stack 문서도 KEDA+Prometheus로 해당 흐름을 제시합니다. ([docs.vllm.ai](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html?utm_source=openai))

3. **SLO/LLM-aware autoscaling**
   - 2026년 관점에서 가장 흥미로운 흐름은 “TTFT, ITL, KV cache” 같은 LLM 특화 신호로 prefill/decode를 **협조적으로** 스케일하는 방식입니다. NVIDIA Dynamo Planner는 Prometheus에서 지표를 조회하고 프로파일링/예측 기반으로 replica를 결정하는 구성을 문서화합니다. ([docs.dynamo.nvidia.com](https://docs.dynamo.nvidia.com/dynamo/kubernetes-deployment/deployment-guide/autoscaling?utm_source=openai))  
   - 장점: “GPU util”이 아니라 **사용자 지연(SLA)** 중심으로 최적화 가능  
   - 단점: 도입 복잡도(프로파일링, 컴포넌트 구성, 관측 파이프라인)가 큼

### 2) KEDA는 “더 좋은 신호”를 HPA로 연결하는 어댑터다
KEDA는 이벤트/외부 메트릭을 받아 Kubernetes scale subresource를 통해 Deployment 등을 스케일합니다(즉 내부적으로 HPA를 생성/관리). Prometheus scaler를 쓰면 “PromQL 결과”를 기준으로 스케일합니다. ([cncf.io](https://www.cncf.io/projects/keda/?utm_source=openai))

여기서 실무 포인트는:
- **HPA의 control loop**(평균화, 안정화 윈도우, 쿨다운) 특성은 그대로라서, 신호가 좋아져도 **노드 프로비저닝/모델 로딩 지연**까지 해결되진 않습니다.
- GPU 메트릭 파이프라인(DCGM exporter → Prometheus → Adapter/KEDA)은 구성요소가 늘수록 **메트릭 지연과 운영 복잡도**가 커집니다. 실제로 “Prometheus 체인 없이 GPU 오토스케일을 하겠다”는 동기가 2026년에도 커지고 있습니다(외부 스케일러가 NVML을 직접 읽는 접근 등). ([reddit.com](https://www.reddit.com/r/kubernetes/comments/1sd7zyr/keda_gpu_scaler_autoscale_vllmtriton_inference/?utm_source=openai))

### 3) MIG/DRA는 “스케일링” 이전에 “할당 단위”를 바꾼다
- **MIG**: A100/H100 계열에서 GPU를 여러 인스턴스로 쪼개 Pod당 더 작은 단위로 할당 가능. GPU Operator의 MIG Manager가 노드 라벨(`nvidia.com/mig.config`) 변화를 감시해 설정을 적용합니다(필요 시 GPU Pod 중지 등 영향). ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/23.6.0/gpu-operator-mig.html?utm_source=openai))  
- **DRA(Dynamic Resource Allocation)**: Kubernetes가 장치 할당을 더 유연하게 다루기 위한 프레임워크. NVIDIA는 GPU Operator에서 DRA Driver 설치/구성을 문서화했고, Kubernetes도 DRA 개념/워크플로우를 공식 문서로 제공합니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/dra-intro-install.html?utm_source=openai))  
  핵심은 “요청/할당/구성”이 PV/PVC처럼 구조화되어 장치 벤더 드라이버가 더 많은 재량을 갖는 방향이라는 점입니다.

---

## 💻 실전 코드
아래는 **vLLM + (vLLM backlog 메트릭) + KEDA(Prometheus scaler)** 조합으로 “대기열 기반 GPU 워크로드 오토스케일”을 구성하는 예시입니다. toy가 아니라, 실제 운영에서 자주 쓰는 형태(별도 monitoring 네임스페이스, Prometheus endpoint 질의, scale-to-1~N)로 작성합니다.

### 0) 전제(의존성/구성)
- GPU 노드에 NVIDIA GPU Operator 설치(드라이버, device plugin, DCGM exporter 등)  
- vLLM은 `/metrics` 노출(대부분 기본 제공, 서비스로 열어 Prometheus가 scrape)
- Prometheus가 `vllm` 서비스의 metrics를 scrape하고 있어야 함  
  (vLLM production-stack은 KEDA가 Prometheus에 질의하는 형태를 안내합니다.) ([docs.vllm.ai](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html?utm_source=openai))

### 1) vLLM Deployment + Service (예: Llama 계열, 1 GPU/pod)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-serve
  namespace: llm
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-serve
  template:
    metadata:
      labels:
        app: vllm-serve
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - "--model"
            - "meta-llama/Llama-3-8B-Instruct"
            - "--host"
            - "0.0.0.0"
            - "--port"
            - "8000"
          ports:
            - name: http
              containerPort: 8000
            - name: metrics
              containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: "1"
          env:
            - name: VLLM_LOGGING_LEVEL
              value: "INFO"
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-serve
  namespace: llm
  labels:
    app: vllm-serve
spec:
  selector:
    app: vllm-serve
  ports:
    - name: http
      port: 8000
      targetPort: 8000
```

예상 동작
- `kubectl -n llm port-forward svc/vllm-serve 8000:8000`
- 트래픽을 넣으면 `/metrics`에 `vllm:num_requests_waiting` 같은 backlog 지표가 증가(버전에 따라 이름은 다를 수 있어 실제 노출 메트릭을 확인해야 합니다). ([kubernetes.recipes](https://kubernetes.recipes/recipes/ai/llm-autoscaling-kubernetes/?utm_source=openai))

### 2) KEDA ScaledObject: backlog(대기열) 기반 스케일
Prometheus에 질의해 backlog가 커지면 replica를 늘립니다.

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vllm-serve-so
  namespace: llm
spec:
  scaleTargetRef:
    name: vllm-serve
  minReplicaCount: 1
  maxReplicaCount: 8
  pollingInterval: 10
  cooldownPeriod: 120
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-operated.monitoring.svc:9090
        metricName: vllm_requests_waiting
        query: |
          sum(vllm_num_requests_waiting{namespace="llm", service="vllm-serve"})
        threshold: "5"
```

예상 출력/확인 포인트
- `kubectl -n llm describe scaledobject vllm-serve-so`
- KEDA가 내부적으로 만든 HPA 확인: `kubectl -n llm get hpa`
- 트래픽 급증 시 `replicas` 증가, 트래픽 감소 후 `cooldownPeriod` 지나면 감소

### 3) (선택) GPU util 안전장치: DCGM 메트릭을 “상한”으로 함께 보기
현실에서는 backlog만 보면 “모델 로딩/콜드스타트로 backlog가 순간 급증 → 과도 스케일”이 발생할 수 있습니다. 그래서 운영팀은 종종 DCGM util을 함께 대시보드로 보고 threshold를 재조정합니다. DCGM exporter는 Kubernetes에서 DaemonSet로 올려 GPU 메트릭을 노출할 수 있고, Pod label 매핑 옵션도 존재합니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “Pod autoscaling”과 “Node autoscaling”을 분리해서 설계
LLM은 **Pod가 늘어도 GPU 노드가 없으면 Pending**입니다. 즉 KEDA/HPA만 잘해도 SLO가 깨집니다.
- GPU 노드 프로비저닝(클라우드라면 Karpenter/Cluster Autoscaler 등)의 scale-up latency를 먼저 측정하고,
- “최소 GPU 노드/최소 warm replica”를 유지하는 방식으로 버스트를 흡수하세요.  
특히 모델 로딩 시간이 길면(수 분) 사실상 “예측/워밍풀” 없이는 이길 수 없습니다.

### Best Practice 2) 스케일 신호는 “GPU util”보다 “queue/latency”에 가깝게
- GPU util은 결과 지표라 **늦게 반응**하거나(이미 TTFT 깨짐), 반대로 batching 덕에 효율이 높아도 util이 높아 “불필요 스케일”로 이어질 수 있습니다.
- 가능하면 vLLM backlog, request rate, p95 TTFT 같은 **서빙 품질 지표**로 스케일하세요. LLM-aware로 가면 Dynamo Planner처럼 TTFT/ITL/KV cache를 직접 다룹니다. ([docs.dynamo.nvidia.com](https://docs.dynamo.nvidia.com/dynamo/kubernetes-deployment/deployment-guide/autoscaling?utm_source=openai))

### Best Practice 3) MIG는 “스케일링의 대체재”가 아니라 “할당 단위 최적화”
- MIG로 Pod당 1 GPU 대신 1 MIG slice를 주면 **수평 스케일 granularity**가 좋아져서 오토스케일이 더 부드러워질 수 있습니다.
- 하지만 MIG 재구성은 노드/파드 중단 같은 운영 이벤트를 동반할 수 있고(GPU Operator MIG Manager 동작 특성), 동적 재구성을 잦게 하는 패턴은 위험합니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/23.6.0/gpu-operator-mig.html?utm_source=openai))  
  결론: MIG는 “정적 프로파일 몇 개를 미리 준비”하고, 오토스케일은 그 위에서 하세요.

### 흔한 함정 1) 메트릭 지연(스크레이프 주기 + KEDA polling + HPA 안정화) 과소평가
DCGM exporter → Prometheus → KEDA는 구성요소가 늘수록 지연이 누적됩니다. 커뮤니티에서도 “지연이 종종 체감보다 심각”하다는 피드백이 나옵니다. ([reddit.com](https://www.reddit.com/r/kubernetes/comments/1sd7zyr/keda_gpu_scaler_autoscale_vllmtriton_inference/?utm_source=openai))  
- 해결책: polling/스크레이프 주기를 공격적으로 낮추되, Prometheus 부하와 노이즈를 함께 관리
- 또는 NVML을 노드에서 직접 읽는 external scaler 같은 “short path”를 검토(성숙도/보안/운영 리스크는 별도 평가)

### 흔한 함정 2) scale-down이 너무 빨라서 thrashing
LLM은 캐시(KV cache), JIT/컴파일, 모델 warm 상태가 성능에 크게 영향. 너무 빨리 줄이면 다시 늘릴 때 TTFT가 튑니다.
- cooldownPeriod를 길게(예: 120~300s) 두고
- “최소 1~2 replica 유지” 또는 “야간 최소치” 같은 정책이 비용 대비 안정적입니다.

### 비용/성능/안정성 트레이드오프 한 줄 요약
- **비용 최소화**: scale-to-zero에 가까울수록 콜드스타트로 SLO가 흔들림
- **SLO 안정화**: 워밍풀/최소치 유지 + LLM-aware scaling(또는 예측)로 비용이 올라갈 수 있음
- **운영 단순성**: GPU util 기반은 단순하지만 SLO 최적화는 어려움

---

## 🚀 마무리
2026년 5월 기준, Kubernetes에서 LLM 서빙 GPU 오토스케일의 실전 해법은 크게 3단계로 정리됩니다.

1) **KEDA + Prometheus + 앱 메트릭(backlog/latency)** 로 “스케일 신호”를 바로잡기  
2) GPU util(DCGM)은 “보조 관측/가드레일”로 두고, 운영 임계값을 튜닝  
3) 더 나아가면 **LLM-aware autoscaling(SLA 기반: TTFT/ITL/KV cache)** 또는 DRA/MIG로 “할당 단위” 자체를 재설계  
- Kubernetes DRA는 공식 문서와 v1.36 업데이트에서도 계속 강조되는 축이고, NVIDIA도 GPU DRA Driver를 GPU Operator에 통합해 안내합니다. ([kubernetes.io](https://kubernetes.io/blog/2026/05/07/kubernetes-v1-36-dra-136-updates/?utm_source=openai))

도입 판단 기준(실무 체크리스트)
- 트래픽이 버스트인가? 노드/모델 로딩이 몇 분인가? → 리액티브만으로 되는지 먼저 측정
- 스케일 신호를 GPU util로 둘지, backlog/TTFT로 둘지 → SLO 목표와 연결
- GPU를 쪼개 써야 하나(MIG/DRA)? → 멀티테넌시/비용 구조에 따라 우선순위 결정

다음 학습 추천
- vLLM + KEDA autoscaling 문서 흐름을 그대로 재현해 보고(백로그 기반) ([docs.vllm.ai](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html?utm_source=openai))
- DCGM exporter 메트릭/라벨 매핑 옵션을 이해해 “GPU 메트릭 관측”을 견고히 한 뒤 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))
- SLO 중심이 필요하면 Dynamo Planner 같은 LLM-aware 스케일링 설계를 검토하세요. ([docs.dynamo.nvidia.com](https://docs.dynamo.nvidia.com/dynamo/kubernetes-deployment/deployment-guide/autoscaling?utm_source=openai))

원하시면, 사용 중인 환경(EKS/GKE/온프렘), 서빙 엔진(vLLM/TGI/Triton), GPU 종류(A10/L4/A100/H100), 목표 SLO(TTFT/p95)와 트래픽 패턴(버스트/일변동)을 알려주시면 **“어떤 신호로, 어떤 min/max, 어떤 cooldown, MIG 필요 여부”**까지 포함해 더 구체적인 권장 설정으로 좁혀드릴게요.