---
title: "GPU 오토스케일링, 2026년 5월 기준 “정답”은 GPU%가 아니라 KV Cache·Queue·SLO다"
date: 2026-05-10 03:59:17 +0900
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
Kubernetes에서 LLM을 서빙(vLLM/Triton/llm-d/Dynamo 등)할 때 “GPU가 비싸니 자동으로 늘렸다 줄이자”는 목표는 단순하지만, **무엇을 기준으로 스케일링할지**에서 대부분 망합니다. CPU 서비스처럼 CPU%로 HPA를 걸면, LLM은 **latency가 터진 뒤에야** 반응하거나(reactive), 반대로 **VRAM(OOM/KV cache) 한계** 때문에 GPU util이 낮아도 이미 포화인 상황을 놓칩니다. 실제로 최근 레퍼런스들은 “GPU utilization은 보조 지표”로 취급하고, **queue depth / in-flight / KV cache pressure / TTFT(첫 토큰 시간)·ITL(토큰 간 지연)** 같은 **LLM 내부 상태 기반 지표**를 주 스케일 신호로 밀고 있습니다. ([developer.nvidia.com](https://developer.nvidia.com/blog/deploying-disaggregated-llm-inference-workloads-on-kubernetes/?utm_source=openai))

언제 쓰면 좋나:
- 트래픽 변동이 크고(버스트), GPU 노드 풀을 상시 크게 가져가기 부담될 때
- 멀티 모델/멀티 테넌트로 “남는 GPU가 있어도 요청이 밀리는” 상황을 줄이고 싶을 때
- SLO(예: P95 TTFT < 1.5s) 중심 운영을 하고 싶을 때 ([developer.nvidia.com](https://developer.nvidia.com/blog/deploying-disaggregated-llm-inference-workloads-on-kubernetes/?utm_source=openai))

언제 쓰면 안 되나(혹은 ROI가 낮나):
- 스케일-아웃 시 **모델 로딩이 수십~수백 초** 걸려서 “오토스케일링이 늦음 = 무의미”한 경우(대신 warm pool/프리로딩/프리페치가 먼저)
- 단일 거대 모델을 단일 GPU 타입에서만 돌리고, 트래픽도 안정적이라면: 고급 오토스케일링보다 **capacity planning + 배치/동시성 튜닝**이 더 직접적

---

## 🔧 핵심 개념
### 1) “GPU 워크로드 오토스케일”의 3개 루프
LLM 서빙의 스케일링은 사실상 3개 제어 루프가 맞물립니다.

1. **Pod autoscaling (HPA/KEDA)**: replicas를 늘리고 줄임  
2. **Node autoscaling (Cluster Autoscaler/Karpenter 등)**: GPU 노드 자체를 늘리고 줄임  
3. **GPU slicing/partitioning (MIG, time-slicing, MPS 등)**: 한 물리 GPU를 여러 워크로드가 나눠 쓰게 함

여기서 가장 흔한 실수는 1번만 잘하면 된다고 생각하는 겁니다. 예를 들어 KEDA가 replicas를 늘려도, GPU 노드가 즉시 안 늘면 Pending이 쌓여 SLO가 깨집니다. 반대로 노드는 늘었는데 파드가 scale-out을 늦게 하면 역시 latency가 터집니다.

### 2) 2026년 관점의 “지표 선택” 우선순위
- **1순위: KV cache utilization / pressure**  
  KV cache가 꽉 차면 GPU util이 60%여도 사실상 “새 요청을 받으면 eviction/스톨/OOM 위험” 상태가 됩니다. llm-d의 WVA도 KV cache와 queue depth를 핵심 신호로 둡니다. ([llm-d.ai](https://llm-d.ai/docs/guide/Installation/workload-autoscaling?utm_source=openai))
- **2순위: queue depth / num_requests_waiting**  
  vLLM production-stack이 KEDA 예제로 queue 기반 메트릭(`vllm:num_requests_waiting`)을 직접 다룹니다. ([docs.vllm.ai](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html?utm_source=openai))
- **3순위(보조): GPU utilization(DCGM)**  
  GPU util은 “지연의 원인”을 설명하는 데는 좋지만, “스케일 트리거”로는 늦거나 왜곡될 수 있습니다. 그래도 infra 관점에서 DCGM은 표준에 가깝고(AKS/GKE 등도 이 스택을 가이드), 운영팀과 합의하기 쉽습니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/aks/autoscale-gpu-workloads-with-keda?utm_source=openai))

### 3) 메트릭 파이프라인: DCGM Exporter → Prometheus → KEDA
가장 보편적인 구성은:
- NVIDIA GPU Operator가 **dcgm-exporter**를 배포하여 GPU 메트릭을 Prometheus 포맷으로 노출 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/1.8/getting-started.html?utm_source=openai))
- Prometheus(또는 Managed Prometheus)가 scrape
- KEDA가 Prometheus query로 scale decision

AKS 문서도 이 체인을 “GPU 워크로드 오토스케일링 레퍼런스”로 제시합니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/aks/autoscale-gpu-workloads-with-keda?utm_source=openai))

다만 단점도 명확합니다:
- scrape interval + KEDA polling interval + HPA stabilization 때문에 **반응이 느림**
- time-slicing을 켜면 dcgm-exporter가 컨테이너 단위로 메트릭을 매핑 못하는 제약이 있습니다(“어느 Pod가 GPU를 쓰는지”가 흐려짐). ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/25.3.4/gpu-sharing.html?utm_source=openai))

### 4) 2026년 5월의 큰 변화: DRA(Dynamic Resource Allocation)와 GPU
Kubernetes 쪽에서는 **DRA가 가속기 할당을 ‘device plugin의 확장 리소스 카운트’에서 한 단계 끌어올리는 방향**으로 굳어지고 있고, NVIDIA도 **GPU용 DRA Driver**를 CNCF/Kubernetes SIGs에 올리는 흐름입니다. ([github.com](https://github.com/kubernetes-sigs/dra-driver-nvidia-gpu?utm_source=openai))  
이건 “오토스케일링” 자체를 바로 해결해주진 않지만, 장기적으로는:
- “GPU 1개” 같은 단순 요청이 아니라 **속성 기반/대안 우선순위/메타데이터 기반** 요청이 가능해져
- 이기종 GPU 클러스터에서 스케일링/스케줄링의 예측 가능성을 올려줍니다. ([kubernetes.io](https://kubernetes.io/blog/2026/05/07/kubernetes-v1-36-dra-136-updates/?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: **vLLM로 Llama 계열 모델을 서빙**하고, KEDA로 “대기열(큐) + GPU 메모리 사용률”을 함께 보고 autoscaling.  
- 큐 메트릭은 “유저가 기다리기 시작했다”를 보여줌  
- GPU memory(utilization)는 “스케일 아웃을 해도 한 파드가 OOM 근처면 더 늘려야” 같은 **안전장치**로 사용

전제:
- GPU Operator(+dcgm-exporter) 설치 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/1.8/getting-started.html?utm_source=openai))
- Prometheus가 `vLLM /metrics`와 `dcgm-exporter`를 scrape
- KEDA 설치

### 1) vLLM Deployment (예: 1 GPU 고정, metrics 노출)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-llama3
  namespace: llm
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-llama3
  template:
    metadata:
      labels:
        app: vllm-llama3
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - "--model=meta-llama/Meta-Llama-3-8B-Instruct"
            - "--host=0.0.0.0"
            - "--port=8000"
            - "--gpu-memory-utilization=0.90"
            - "--max-num-batched-tokens=8192"
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: "1"
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
```

예상 동작:
- `/metrics`에 대기열/처리량/지연 관련 메트릭이 쌓임(배포 스택에 따라 이름은 다를 수 있음)
- GPU는 `nvidia.com/gpu:1`로 할당

### 2) KEDA ScaledObject: Prometheus 기반 트리거 2개(큐 + GPU 메모리)
vLLM production-stack 문서가 Prometheus scaler로 `vllm:num_requests_waiting` 같은 큐 메트릭을 KEDA에 연결하는 흐름을 제공합니다. ([docs.vllm.ai](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html?utm_source=openai))  
여기서는 “큐가 조금이라도 쌓이면 scale-out” + “GPU memory가 높게 유지되면 더 공격적으로”의 조합 예시를 듭니다.

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vllm-llama3-autoscale
  namespace: llm
spec:
  scaleTargetRef:
    name: vllm-llama3
  minReplicaCount: 1
  maxReplicaCount: 6
  pollingInterval: 10
  cooldownPeriod: 180
  advanced:
    horizontalPodAutoscalerConfig:
      behavior:
        scaleUp:
          stabilizationWindowSeconds: 0
          policies:
            - type: Percent
              value: 200
              periodSeconds: 30
        scaleDown:
          stabilizationWindowSeconds: 300
          policies:
            - type: Percent
              value: 50
              periodSeconds: 60
  triggers:
    # (A) 큐 기반: 대기 요청 평균이 0.5를 넘으면 scale out
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-operated.monitoring.svc:9090
        metricName: vllm_num_requests_waiting
        query: |
          avg(vllm_num_requests_waiting{namespace="llm",pod=~"vllm-llama3-.*"})
        threshold: "0.5"

    # (B) GPU 메모리 기반(DCGM): GPU 메모리 사용률이 85% 이상이면 headroom 확보 위해 scale out
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-operated.monitoring.svc:9090
        metricName: dcgm_fb_used_ratio
        query: |
          100 *
          (
            avg(DCGM_FI_DEV_FB_USED{namespace="gpu-operator"}) /
            avg(DCGM_FI_DEV_FB_TOTAL{namespace="gpu-operator"})
          )
        threshold: "85"
```

검증 커맨드(운영자가 바로 보는 포인트):
```bash
kubectl -n llm get scaledobject
kubectl -n llm describe hpa | sed -n '/Metrics/,$p'
kubectl -n monitoring port-forward svc/prometheus-operated 9090:9090
curl -G 'http://localhost:9090/api/v1/query' --data-urlencode \
  'query=avg(vllm_num_requests_waiting{namespace="llm"})'
```

운영에서 기대하는 출력/관찰:
- 트래픽 증가 → `vllm_num_requests_waiting` 상승 → HPA desired replicas 증가
- GPU FB memory ratio가 임계 이상으로 유지되면 scale-out이 더 빨라짐
- 트래픽 감소 → 5분 안정화 후 scale-down(LLM cold start/캐시 재구축 비용을 고려)

### 3) (선택) MIG로 “스케일 단위”를 작게 만들기
오토스케일링이 잘 안 먹는 흔한 이유는 **스케일 step이 너무 크기 때문**입니다(“replica 1개 = GPU 1장”). MIG를 쓰면 “replica 1개 = MIG slice 1개”로 더 촘촘한 스케일이 가능합니다. GPU Operator는 MIG Manager로 Kubernetes에서 MIG 구성을 지원합니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-operator-mig.html?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **스케일 신호는 “SLO에 가까운 것”을 우선**
- GPU%보다 **TTFT/ITL, queue time, KV cache pressure**가 실제 사용자 경험과 더 직결됩니다. llm-d WVA가 KV cache/queue를 핵심으로 두는 이유가 여기 있습니다. ([llm-d.ai](https://llm-d.ai/docs/guide/Installation/workload-autoscaling?utm_source=openai))

2) **scale-up은 빠르게, scale-down은 보수적으로**
- LLM 파드는 모델 로딩/워밍업이 느립니다. scale-down을 공격적으로 하면 곧바로 재확장하며 thrash가 납니다.
- `cooldownPeriod`와 HPA `scaleDown.stabilizationWindowSeconds`를 길게 가져가 “GPU 비용 vs 변동성”을 제어하세요.

3) **GPU sharing(time-slicing)과 메트릭의 정확도를 같이 설계**
- time-slicing을 켜면 dcgm-exporter가 컨테이너별 메트릭 매핑을 못할 수 있습니다. “Pod별 GPU 사용률”을 근거로 한 autoscaling/chargeback을 기대하면 깨집니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/25.3.4/gpu-sharing.html?utm_source=openai))  
  이 경우 스케일 신호를 **앱 메트릭(큐/latency)**로 옮기고, DCGM은 노드/디바이스 헬스 모니터링으로 격리하는 편이 안전합니다.

### 흔한 함정/안티패턴
- **GPU utilization 단일 지표로 autoscaling**: KV cache가 꽉 차면 util은 애매한데 latency가 급증하는 구간이 나옵니다(“OOM trap / lagging signal”).  
- **Prometheus scrape interval을 길게(30~60s) + KEDA polling도 길게**: 버스트 트래픽에서 “이미 터진 뒤 스케일”이 됩니다.
- **Pod scale-out만 하고 Node autoscaling을 안 맞춤**: GPU 노드가 없어서 Pending → HPA는 늘리는데 아무도 못 뜸.

### 비용/성능/안정성 트레이드오프
- **MIG**: 안정적 격리 + 작은 스케일 단위 / 하지만 운영 복잡도↑, 프로파일 선택이 고정적  
- **time-slicing/MPS**: GPU 활용률↑ 가능 / 하지만 메트릭 귀속·성능 격리·디버깅 난이도↑ ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/25.3.4/gpu-sharing.html?utm_source=openai))
- **DRA(신규)**: 장기적으로 이기종/속성 기반 할당이 깔끔해질 가능성 / 단, “즉시 오토스케일링 만능키”는 아니고 생태계 성숙을 기다려야 함 ([kubernetes.io](https://kubernetes.io/blog/2026/05/07/kubernetes-v1-36-dra-136-updates/?utm_source=openai))

---

## 🚀 마무리
2026년 5월 기준, Kubernetes에서 LLM GPU 오토스케일링의 핵심은:
- **GPU% 중심에서 “LLM 내부 포화 신호(KV cache, queue, TTFT/ITL)” 중심으로 옮기는 것**
- KEDA/HPA는 “액추에이터(실행기)”로 쓰되, **무슨 메트릭을 넣을지**가 성패를 가른다는 점 ([docs.vllm.ai](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html?utm_source=openai))
- GPU Operator + DCGM + Prometheus는 여전히 표준적인 관측/운영 기반이지만, GPU sharing을 섞으면 메트릭 해석이 어려워질 수 있음 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/1.8/getting-started.html?utm_source=openai))
- DRA는 GPU 할당의 미래 방향(속성/메타데이터 기반)으로 굳어지고 있어, 새 클러스터/플랫폼 설계라면 로드맵에 넣을 가치가 큼 ([kubernetes.io](https://kubernetes.io/blog/2026/05/07/kubernetes-v1-36-dra-136-updates/?utm_source=openai))

도입 판단 기준(현실적인 체크리스트):
- “우리의 병목이 GPU compute인가, VRAM(KV cache)인가, 아니면 cold start인가?”
- “scale-out이 SLO를 구할 만큼 빠른가?”(모델 로딩 시간 vs 트래픽 버스트)
- “노드 오토스케일링/쿼터/스케줄링까지 한 세트로 운영 가능한가?”

다음 학습 추천:
- llm-d의 WVA(Workload Variant Autoscaler) 문서로 “KV cache 기반 capacity model” 감 잡기 ([llm-d.ai](https://llm-d.ai/docs/architecture/Components/workload-variant-autoscaler?utm_source=openai))
- vLLM production-stack의 KEDA autoscaling 예제(메트릭 이름/Helm 옵션 포함) ([docs.vllm.ai](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html?utm_source=openai))
- Kubernetes DRA 최신 업데이트(1.36의 DRA 변화와 드라이버 생태계) ([kubernetes.io](https://kubernetes.io/blog/2026/05/07/kubernetes-v1-36-dra-136-updates/?utm_source=openai))