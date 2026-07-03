---
title: "2026년 7월, Kubernetes에서 LLM 서빙을 “GPU 오토스케일”로 굴리는 현실적인 방법: KEDA + (Queue Depth / KV Cache) + DCGM/NVML"
date: 2026-07-03 03:55:58 +0900
categories: [Infra, Kubernetes]
tags: [infra, kubernetes, trend, 2026-07]
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
LLM inference를 Kubernetes 위에 올리면 금방 마주치는 문제가 있습니다. **HPA는 CPU/Memory 위주로 설계**되어 있어서, 실제 병목인 **GPU pressure(Compute, VRAM, KV cache, queueing)**를 제대로 반영하지 못합니다. 결과는 뻔합니다:  
- 트래픽이 늘었는데도 replica가 늦게 늘어 **P95 latency/SLO가 터지거나**  
- 반대로 GPU utilization 같은 “그럴듯한” 지표에 매달리다가 **불필요하게 과스케일**해서 비용이 폭증합니다(특히 vLLM 계열). ([kubenatives.com](https://www.kubenatives.com/p/autoscaling-gpu-inference-kubernetes-hpa-keda?utm_source=openai))

**언제 쓰면 좋은가**
- vLLM/Triton 같은 **GPU inference**를 운영하며, 요청량 변동이 크고(주간/야간, 배치/실시간 혼재) **scale-to-zero 또는 빠른 scale-out**이 필요할 때
- “GPU 사용률”이 아니라 **queue depth / in-flight requests / KV cache**처럼 **서빙 병목을 직접 나타내는 지표**로 스케일하고 싶을 때 ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))

**언제 쓰면 안 되는가**
- 모델 로딩이 5~10분 이상이고, 워밍업/캐시가 핵심이라서 **스케일 이벤트 자체가 장애**가 되는 워크로드(이 경우는 “오토스케일”보다 “warm pool + 예약 용량”이 먼저입니다)
- 트래픽이 일정하고(24/7 steady) GPU가 항상 포화라서 **스케일링보다 배치/배포 전략**(모델 샤딩, 텐서 병렬, MIG, 라우팅)이 본질인 경우

---

## 🔧 핵심 개념
### 1) 왜 “GPU utilization 기반 오토스케일”이 자주 망하나
2026년에도 현업에서 반복되는 교훈은 비슷합니다: **vLLM 같은 LLM 서빙에서는 GPU utilization이 ‘수요’를 잘 표현하지 못할 때가 많다**는 점입니다. 예를 들어,
- 단일 긴 generation이 GPU를 오래 붙잡아 utilization이 높아져도, 실제로는 “대기열”이 없을 수 있고
- 커널/배치 설정 문제로 utilization이 높게 보이지만 throughput이 안 나오는 “나쁜 포화”가 생기면, utilization 스케일은 **문제 복제(Replica만 증가)**를 합니다. ([reddit.com](https://www.reddit.com/r/kubernetes/comments/1sd7zyr/keda_gpu_scaler_autoscale_vllmtriton_inference/?utm_source=openai))

그래서 최근 실무 가이드는 **queue depth / waiting requests / KV cache 사용률**처럼 “서빙 병목”과 더 직결된 지표를 추천합니다. ([zartis.com](https://www.zartis.com/scaling-llm-workloads-on-kubernetes-a-production-engineers-guide/?utm_source=openai))

### 2) 2026년 주류 아키텍처: KEDA가 HPA를 ‘조종’한다
KEDA는 “별도 오토스케일러”가 아니라, 구조적으로는 **외부/커스텀 metric을 HPA로 연결해주는 컨트롤 플레인**에 가깝습니다.

- (A) LLM 서버(vLLM/KServe 등)가 **Prometheus metric**을 노출 (예: `vllm:num_requests_waiting`, `vllm:gpu_cache_usage_perc`) ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))  
- (B) Prometheus가 scrape  
- (C) KEDA `ScaledObject`가 Prometheus query(또는 외부 scaler)를 통해 값을 읽음 ([keda.sh](https://keda.sh/docs/2.21/scalers/prometheus/?utm_source=openai))  
- (D) KEDA가 HPA를 생성/갱신하고, HPA가 replica 수를 조절

여기서 중요한 차이점:
- “표준 HPA + custom metrics adapter(prometheus-adapter)”도 가능하지만, **KEDA는 scale-to-zero**, 다양한 scaler, 운영 단순화 측면에서 우세합니다. ([docs.vllm.ai](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html?utm_source=openai))

### 3) GPU metric 경로: DCGM(표준) vs NVML direct(지연/복잡도 축소)
GPU 지표를 얻는 전통적인 경로는 다음입니다.

- NVIDIA GPU Operator → `dcgm-exporter` → Prometheus → (KEDA Prometheus scaler) ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/23.3.2/getting-started.html?utm_source=openai))  
  - 장점: 표준적, 대시보드/관측 생태계 풍부
  - 단점: 구성요소가 많아지고, metric lag(스크랩/쿼리 주기)이 생깁니다

2026년 5월 CNCF 블로그에서는 “Prometheus 체인 없이” **NVML을 DaemonSet에서 직접 읽고 KEDA에 gRPC external scaler로 제공**하는 접근을 소개합니다. 즉, 구성요소/지연을 줄이는 방향입니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

실무적으로는:
- **정교한 관측/리포팅이 이미 Prometheus 중심**이면 DCGM 체인이 무난
- **스케일 신호의 지연을 줄이고 운영 컴포넌트를 최소화**하고 싶으면 NVML direct external scaler가 매력적입니다 ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “toy”가 아니라, 실제 운영에서 자주 쓰는 **vLLM 기반 LLM 서빙 + KEDA 오토스케일(Queue Depth 우선) + GPU 메모리 가드레일** 패턴입니다.

### 시나리오
- vLLM이 노출하는 metric(`vllm:num_requests_waiting`)으로 scale-out
- 동시에 DCGM metric으로 **VRAM 압박**을 감지해 “너무 빡빡한 상태에서 무작정 scale”하지 않도록(=실패 확률 증가 구간 회피) 운영자가 알람/대시보드 기준을 잡는다  
  - 참고: DCGM Exporter의 대표 지표는 `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_FB_USED` 등입니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))

### 0) 전제(의존성)
- Kubernetes에 NVIDIA GPU Operator 설치(=드라이버/디바이스 플러그인/DCGM Exporter 포함 가능) ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/23.3.2/getting-started.html?utm_source=openai))
- Prometheus(또는 kube-prometheus-stack) 설치
- KEDA 설치
- vLLM(또는 KServe+vLLM)에서 metrics endpoint 활성화 ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))

### 1) vLLM Deployment (현실적인 포인트 포함)
- 모델 다운로드/로딩이 느리면 scale-out이 늦습니다. **PVC에 모델을 캐시**하거나 이미지에 bake-in하는 전략이 필요합니다(여기서는 PVC 가정). ([kubenatives.com](https://www.kubenatives.com/p/autoscaling-gpu-inference-kubernetes-hpa-keda?utm_source=openai))

```yaml
# vllm-deploy.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  namespace: llm
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm
  template:
    metadata:
      labels:
        app: vllm
    spec:
      terminationGracePeriodSeconds: 120
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - "--model=/models/llama"
            - "--host=0.0.0.0"
            - "--port=8000"
            - "--metrics-port=8001"
            # 운영에서는 아래 같은 옵션(배치/컨텍스트/메모리)을 반드시 모델/트래픽에 맞춰 튜닝
          ports:
            - name: http
              containerPort: 8000
            - name: metrics
              containerPort: 8001
          resources:
            limits:
              nvidia.com/gpu: "1"
            requests:
              nvidia.com/gpu: "1"
          volumeMounts:
            - name: model-cache
              mountPath: /models
      volumes:
        - name: model-cache
          persistentVolumeClaim:
            claimName: llm-model-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: vllm
  namespace: llm
spec:
  selector:
    app: vllm
  ports:
    - name: http
      port: 8000
      targetPort: 8000
    - name: metrics
      port: 8001
      targetPort: 8001
```

적용:
```bash
kubectl create ns llm
kubectl apply -f vllm-deploy.yaml
kubectl -n llm get pods -w
```

예상 확인:
```bash
# metrics가 노출되는지 확인(포트포워드)
kubectl -n llm port-forward svc/vllm 8001:8001
curl -s localhost:8001/metrics | head
```

### 2) Prometheus가 vLLM metrics를 scrape하도록 ServiceMonitor
(kube-prometheus-stack 기준)

```yaml
# vllm-servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: vllm
  namespace: llm
spec:
  selector:
    matchLabels:
      app: vllm
  namespaceSelector:
    matchNames: ["llm"]
  endpoints:
    - port: metrics
      interval: 15s
      path: /metrics
```

```bash
kubectl apply -f vllm-servicemonitor.yaml
```

### 3) KEDA ScaledObject: “대기열(Queue Depth)”로 스케일
KServe 문서/가이드에서도 vLLM의 waiting/running metric이나 KV cache 기반 스케일을 예시로 듭니다. ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))  
KEDA의 Prometheus scaler는 Prometheus HTTP API를 query합니다. ([keda.sh](https://keda.sh/docs/2.21/scalers/prometheus/?utm_source=openai))

```yaml
# keda-scaledobject.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vllm-queue-autoscale
  namespace: llm
spec:
  scaleTargetRef:
    name: vllm
  minReplicaCount: 0
  maxReplicaCount: 10
  cooldownPeriod: 300   # GPU pod는 스타트업이 느리니 scale-down을 공격적으로 하면 비용보다 장애가 커짐
  pollingInterval: 15
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://kube-prometheus-stack-prometheus.monitoring:9090
        metricName: vllm_requests_waiting
        # 핵심: "레플리카당" 대기열을 기준으로 목표를 잡아야 함
        # 예: replica당 waiting이 평균 2를 넘으면 확장
        query: |
          sum(vllm_num_requests_waiting{namespace="llm",service="vllm"}) 
          /
          max(count(kube_pod_info{namespace="llm",pod=~"vllm-.*"}), 1)
        threshold: "2"
```

```bash
kubectl apply -f keda-scaledobject.yaml
kubectl -n llm get hpa
kubectl -n llm describe scaledobject vllm-queue-autoscale
```

스케일 동작 확인(부하를 준다는 가정):
- 동시 요청이 늘어 `vllm_num_requests_waiting`이 올라가면, KEDA가 HPA를 통해 replica를 증가시킵니다. (KServe 문서도 “요청 수/타겟당 pod 수” 예시로 같은 원리를 설명합니다.) ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 적용 가능한 것만)
1) **스케일 지표는 “GPU utilization”이 아니라 “서빙 병목 지표”를 우선**
- vLLM: `num_requests_waiting`, `num_requests_running`, 또는 `gpu_cache_usage_perc` 계열이 운영 판단에 더 직접적입니다. ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))  
- GPU utilization/DCGM은 “참고 지표” 또는 알람/디버깅에 두고, 오토스케일 트리거는 대기열 기반이 보통 더 안전합니다. ([kubenatives.com](https://www.kubenatives.com/p/autoscaling-gpu-inference-kubernetes-hpa-keda?utm_source=openai))

2) **cooldown/scale-down을 보수적으로**
- LLM pod는 (모델 로드 + CUDA init + 캐시 워밍) 때문에 **scale-up 이득이 늦게 오고**, scale-down은 캐시를 날려서 다음 요청에 페널티를 줍니다.  
- 따라서 `cooldownPeriod`를 길게(예: 300s 이상) 두는 패턴이 자주 권장됩니다. ([stackpulsar.com](https://stackpulsar.com/blog/kubernetes-ai-autoscaling-keda/?utm_source=openai))

3) **관측 스택(DCGM Exporter)은 “오토스케일”뿐 아니라 “원인 분석”을 위해 필수**
- DCGM Exporter는 Kubernetes에서 GPU metric을 Prometheus로 내보내는 표준 축이고, GPU Operator와 함께 쓰는 구성이 일반적입니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/23.3.2/getting-started.html?utm_source=openai))  
- 대표 지표: `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_FB_USED` 등 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))

### 흔한 함정/안티패턴
- **함정 1: GPU utilization 70% 타겟 같은 단일 룰로 끝내기**  
  vLLM에서는 KV cache/메모리 모델 때문에 “util 높음 = 더 많은 replica 필요”가 아닐 수 있습니다. 잘못하면 비용만 증가합니다. ([kubenatives.com](https://www.kubenatives.com/p/autoscaling-gpu-inference-kubernetes-hpa-keda?utm_source=openai))

- **함정 2: scale-to-zero를 켰는데 첫 요청 latency를 감당 못함**  
  비즈니스가 “첫 토큰 시간(TTFT)”에 민감하면, scale-to-zero는 사용자 경험을 망칩니다. 이 경우는 **minReplicaCount=1 + 야간 스케줄 scale-down** 같은 절충이 더 실용적입니다(일부 실무 글에서도 warm node/스케줄 패턴을 언급). ([buildmvpfast.com](https://www.buildmvpfast.com/blog/kubernetes-ai-workloads-gpu-node-pools-autoscaling-2026?utm_source=openai))

- **함정 3: 메트릭 지연(스크랩 주기+쿼리 주기)으로 ‘늦은 스케일’**  
  DCGM→Prometheus→KEDA 체인이 길면 지연이 생길 수 있어, 2026년에는 NVML direct external scaler처럼 경량화 접근도 제시됩니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

### 비용/성능/안정성 트레이드오프 한 줄 요약
- **Queue-based autoscaling**: 안정적(SLO 친화) / 비용 효율 좋음 / 대신 “요청 비용 편차(긴 generation)”가 크면 튜닝 필요 ([reddit.com](https://www.reddit.com/r/Vllm/comments/1rknhsh/interesting_autoscaling_insight_for_vllm_queue/?utm_source=openai))  
- **GPU util-based autoscaling**: 구현은 쉬움 / 하지만 LLM에서는 오판이 잦아 비용·장애 모두 위험 ([kubenatives.com](https://www.kubenatives.com/p/autoscaling-gpu-inference-kubernetes-hpa-keda?utm_source=openai))  
- **NVML direct scaler**: 지연·구성요소↓ / 대신 운영 표준(관측/감사) 측면에서 팀 합의 필요 ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

---

## 🚀 마무리
핵심은 “Kubernetes에서 LLM 서빙을 오토스케일한다”가 아니라, **어떤 신호가 ‘서빙 병목’을 대표하는가**입니다. 2026년 7월 기준 실무 흐름은:
- 오토스케일 엔진은 **KEDA가 사실상 표준 레일**이고 ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))  
- 스케일 신호는 **GPU utilization보다 queue depth / waiting requests / KV cache**가 더 낫다는 경험칙이 강해지고 ([zartis.com](https://www.zartis.com/scaling-llm-workloads-on-kubernetes-a-production-engineers-guide/?utm_source=openai))  
- GPU telemetry는 **DCGM Exporter(표준)** 또는 **NVML direct external scaler(지연/복잡도 축소)** 두 갈래로 발전 중입니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))

**도입 판단 기준(실무 체크리스트)**
- 우리 서비스의 SLO는 “처리량”인가 “P95 latency/TTFT”인가?
- 모델/서버의 병목은 Compute인가 KV cache/VRAM인가? (vLLM이면 KV cache 쪽 가능성이 큼)
- scale-to-zero의 cold start를 제품이 허용하는가?
- Prometheus 기반 관측 스택을 이미 운영 중인가, 아니면 스케일 신호만 빠르게 뽑고 싶은가?

**다음 학습 추천**
- vLLM Production Stack의 KEDA 연동 문서(Helm values로 통합되는 지점 확인) ([docs.vllm.ai](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html?utm_source=openai))  
- KServe의 KEDA autoscaling 가이드(Serving 레이어에서 metric을 어떻게 잡는지) ([kserve.github.io](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling?utm_source=openai))  
- DCGM Exporter 최신 문서에서 metric 라벨/구성 옵션(특히 pod/namespace 라벨링) 정리 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))

원하시면, (1) 사용 중인 서빙 스택(vLLM 단독 / KServe / Triton), (2) 클라우드(GKE/EKS/AKS/온프렘), (3) 모델 크기와 목표 SLO를 기준으로 **ScaledObject 쿼리/threshold/cooldown을 실제 값으로 튜닝**하는 버전으로 더 구체화해 드릴게요.