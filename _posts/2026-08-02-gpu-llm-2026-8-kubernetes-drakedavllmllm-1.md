---
title: "GPU 오토스케일링으로 LLM 서빙 비용을 ‘진짜로’ 줄이는 법: 2026년 8월 Kubernetes 최신 패턴(DRA·KEDA·vLLM·llm-d)"
date: 2026-08-02 03:36:27 +0900
categories: [Infra, Kubernetes]
tags: [infra, kubernetes, trend, 2026-08]
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

Kubernetes에서 LLM inference를 운영해보면, 비용의 핵심은 “GPU를 얼마나 오래 켜두느냐”입니다. 문제는 **기본 HPA가 CPU/Memory 중심**이라서, 정작 병목인 GPU 압력(예: VRAM, SM util, power draw)을 반영하지 못해 **과소/과대 스케일링**이 쉽게 발생한다는 점입니다. (GPU가 이미 터졌는데도 CPU는 한가해서 스케일이 안 되거나, 반대로 GPU는 비었는데 replica가 안 줄어드는 식)

**언제 쓰면 좋나**
- vLLM/Triton/커스텀 inference 서버를 **Kubernetes 상에서 멀티-테넌트**로 운영하고,
- 트래픽 변동이 크며(야간/주간 편차, 이벤트성 스파이크),
- “scale-to-zero + 빠른 scale-up”을 통해 **idle GPU 비용을 줄이고 싶을 때**  
  → KEDA(이벤트 기반) + GPU 메트릭 기반 스케일링 조합이 효과가 큽니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-autoscaling-hpa-keda.html?utm_source=openai))

**언제 쓰면 안 되나**
- cold start(모델 로딩)가 1~5분 이상이고 SLO가 빡빡한데, 예열/큐잉/라우팅 계층 없이 “그냥 오토스케일만”으로 해결하려는 경우  
  → 오토스케일은 어디까지나 제어루프라서, 스파이크를 “미리” 처리하지 못하면 첫 파동은 반드시 맞습니다. 큐/프록시/예측(크론 예열) 같은 완충장치가 필요합니다.
- GPU를 사실상 **상시 포화로** 쓰는 워크로드(지속적 배치/학습): scale-to-zero는 의미가 없고, 스케일 다운이 오히려 변동성만 키울 수 있습니다.

---

## 🔧 핵심 개념

### 1) “LLM 서빙 오토스케일”은 3개의 스케일링이 엮인 문제
1) **Pod autoscaling (replica 수)**: KEDA/HPA가 담당  
2) **Node autoscaling (GPU 노드 수)**: Cluster Autoscaler/Karpenter 등이 담당  
3) **Routing/Load balancing (어떤 replica가 받나)**: llm-d/Inference Gateway 같은 계층이 담당

이 3개가 서로 따로 놀면, “replica는 늘었는데 노드가 없어서 Pending”, “노드는 늘었는데 트래픽이 특정 replica에만 몰림” 같은 현상이 납니다. 2026년에는 **Gateway API Inference Extension(GAIE) + llm-d**가 “inference 라우팅” 레이어를 표준화하려는 흐름이 커졌고, GKE도 이를 기반으로 Inference Gateway를 설명합니다. ([github.com](https://github.com/kubernetes-sigs/gateway-api-inference-extension?utm_source=openai))

### 2) GPU 메트릭 기반 스케일링: Prometheus 파이프라인 vs NVML 직결
전통적인 패턴:
- GPU 노드마다 **DCGM Exporter DaemonSet**
- Prometheus scrape
- KEDA가 PromQL로 조회해서 HPA를 구동

장점: 표준적, 관측/대시보드까지 한 번에.  
단점: 구성요소가 많고(Exporter→Prometheus→KEDA), 스크레이프/폴링 주기 때문에 **지연이 생기기 쉽고**, 운영 포인트가 늘어납니다. (DCGM Exporter는 GPU Operator로 함께 깔리기도 합니다.) ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/installation/install-dcgm-exporter.html?utm_source=openai))

2026년에 흥미로운 변화는, **KEDA External Scaler + NVML**로 “Prometheus 없이” GPU 메트릭을 바로 스케일러에 전달하는 아키텍처가 공개적으로 정리되었다는 점입니다. 핵심 이유는:
- NVML은 로컬 노드 GPU에 붙어서 읽는 라이브러리라서, 중앙 Operator가 직접 읽기 어렵고
- KEDA 코어에 GPU 스케일러를 넣기엔 제약이 있어(예: CGO/NVML) 외부 스케일러(노드별 DaemonSet)가 현실적인 해법이라는 주장입니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

이 방식은 GPU 노드마다 DaemonSet이 NVML로 메트릭을 읽어 gRPC로 제공하고, KEDA Operator가 그 gRPC를 호출해 HPA를 움직입니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

### 3) GPU “할당” 자체도 바뀌는 중: Device Plugin → DRA
오토스케일링은 “몇 개를 띄울지” 문제고, “GPU를 어떻게 할당/공유할지”는 별개 축입니다. 2026년 기준 Kubernetes는 **DRA(Dynamic Resource Allocation)**를 가속기/특수장치 할당의 장기적 방향으로 계속 밀고 있고(1.34에서 GA 언급, 1.36에서 성숙/확장), NVIDIA도 DRA Driver를 Kubernetes 커뮤니티로 가져가는 흐름을 강조합니다. ([kubernetes.io](https://kubernetes.io/blog/2025/09/01/kubernetes-v1-34-dra-updates/?utm_source=openai))

또한 “GPU를 쪼개 쓰는” 방법도 여전히 중요합니다:
- **MIG**: 메모리/격리 보장(하드웨어 파티셔닝)
- **Time-slicing**: 격리는 약하지만 더 많이 공유 가능(오버서브스크립션) ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/22.9.2/gpu-sharing.html?utm_source=openai))

결론: 2026년의 실전 스택은 보통  
- (할당/드라이버) GPU Operator + (선택) DRA  
- (서빙) vLLM 등  
- (라우팅) GAIE/llm-d 계열(선택)  
- (스케일) KEDA/HPA + GPU 메트릭(DCGM 또는 NVML 직결)  
을 “목표 SLO/비용/복잡도”로 조합합니다.

---

## 💻 실전 코드

아래 예제는 “장난감”이 아니라, 실제로 많이 쓰는 **vLLM OpenAI-compatible 서버**를 Kubernetes에 배포하고, **KEDA HTTP Add-on(요청 기반 scale-from-zero)** + **GPU 메트릭 기반 스케일(External scaler)**를 같이 거는 형태입니다.

- HTTP Add-on은 **요청이 0이면 0 replica**까지 내렸다가, 요청이 오면 인터셉터가 받아두면서 올립니다. ([keda.sh](https://keda.sh/http-add-on/0.15/?utm_source=openai))
- GPU 스케일러는 **VRAM 사용률** 같은 신호로 “이미 GPU가 빡센데 replica가 부족한 상황”을 잡아줍니다. (CNCF 글의 예시는 vLLM 프로파일이 memory_used_percent 기반) ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

### 0) 전제(의존성/환경)
- Kubernetes 1.29+ 권장(클러스터 환경에 맞게)
- GPU 노드 + NVIDIA GPU Operator 설치(드라이버/런타임/플러그인)  
- KEDA 설치
- (선택) KEDA HTTP Add-on 설치
- (선택) GPU External Scaler(예: keda-gpu-scaler 류) 설치 ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

아래는 설치 흐름 예시(명령은 클러스터에 맞게 조정):

```bash
# 1) KEDA
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace

# 2) KEDA HTTP Add-on (문서 기준 최신 라인 확인)
# 구성 요소: interceptor/scaler/operator
helm repo add keda-addons https://kedacore.github.io/charts
helm repo update
helm install http-add-on keda-addons/keda-add-ons-http \
  --namespace keda --create-namespace

# 3) GPU external scaler (CNCF 글에서 소개된 패턴: GPU 노드마다 DaemonSet)
# 실제 chart/values는 프로젝트에 맞게
helm install gpu-scaler <your-gpu-scaler-chart> \
  --namespace gpu-scaler --create-namespace
```

### 1) vLLM Deployment + Service (GPU 워크로드 “현실 버전”)
- GPU는 일반적으로 `nvidia.com/gpu: 1`처럼 “카운터 리소스”로 요청합니다.
- 모델 로딩/캐시 때문에 ephemeral storage, shared volume, image pull 정책 등도 신경 써야 합니다(여기선 핵심만).

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-openai
  namespace: llm
spec:
  replicas: 0  # scale-to-zero를 전제로 시작
  selector:
    matchLabels:
      app: vllm-openai
  template:
    metadata:
      labels:
        app: vllm-openai
    spec:
      nodeSelector:
        nvidia.com/gpu.present: "true"
      tolerations:
        - key: "nvidia.com/gpu"
          operator: "Exists"
          effect: "NoSchedule"
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - "--model"
            - "meta-llama/Llama-3.1-8B-Instruct"   # 예시
            - "--host"
            - "0.0.0.0"
            - "--port"
            - "8000"
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: "1"
            requests:
              cpu: "2"
              memory: "8Gi"
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 20
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-openai
  namespace: llm
spec:
  selector:
    app: vllm-openai
  ports:
    - name: http
      port: 8000
      targetPort: 8000
```

### 2) HTTP 트래픽 기반 scale-from-zero: KEDA HTTP Add-on Route + ScaledObject
HTTP Add-on은 인터셉터가 앞단에서 요청을 받고, KEDA가 그 메트릭으로 scale을 구동합니다. ([keda.sh](https://keda.sh/http-add-on/0.15/?utm_source=openai))

```yaml
apiVersion: http.keda.sh/v1alpha1
kind: HTTPScaledObject
metadata:
  name: vllm-http
  namespace: llm
spec:
  hosts:
    - vllm.example.internal
  scaleTargetRef:
    name: vllm-openai
    kind: Deployment
    apiVersion: apps/v1
    service: vllm-openai
    port: 8000
  replicas:
    min: 0
    max: 6
  scalingMetric:
    requestRate:
      granularity: 1s
      targetValue: 5   # rps 기준(예시)
  scaledownPeriod: 60
```

### 3) GPU 압력 기반 scale-up 보강: External Scaler 트리거
CNCF 글에서 소개된 외부 스케일러는 GPU 메트릭(예: memory_used_percent)을 gRPC로 제공하고, KEDA가 이를 trigger로 사용합니다. vLLM용 프로파일 예시도 제시되어 있습니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vllm-gpu-pressure
  namespace: llm
spec:
  scaleTargetRef:
    name: vllm-openai
  minReplicaCount: 0
  maxReplicaCount: 12
  pollingInterval: 5
  cooldownPeriod: 60
  triggers:
    - type: external
      metadata:
        scalerAddress: "keda-gpu-scaler.gpu-scaler.svc.cluster.local:6000"
        profile: "vllm-inference"
```

**예상 동작**
- 평소 0 replica (GPU 비용 0에 가깝게)
- 요청이 오면 HTTP Add-on이 scale-up 트리거
- 트래픽이 늘어 VRAM이 차고 지연이 늘기 시작하면, GPU 압력 트리거가 replica를 더 밀어올림
- 트래픽이 빠지면 0까지 회수(단, cold start/SLO에 맞게 scaledownPeriod, cooldownPeriod 조정)

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) “스케일 신호”를 GPU Util 하나로 퉁치지 말기
LLM 서빙은 **VRAM(메모리)**이 먼저 꽉 차서 throughput/latency가 무너지는 경우가 많습니다. 그래서 vLLM inference는 gpu_utilization보다 **memory_used_percent 같은 지표가 더 실전적**일 때가 많고, 실제로 해당 외부 스케일러도 vLLM 프로파일을 VRAM 기반으로 잡았습니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))  
반대로 Triton처럼 배치/커널 util이 중요한 서빙은 SM util 기반이 더 맞을 수 있습니다.

### Best Practice 2) “scale-to-zero”는 라우팅/큐잉 없이는 SLO를 자주 깨뜨린다
HTTP Add-on은 요청을 **인터셉트**해서 스케일 시간을 벌어주지만, 모델 로딩(수십 초~수분) 자체는 사라지지 않습니다. ([keda.sh](https://keda.sh/http-add-on/0.15/?utm_source=openai))  
SLO가 빡빡하면:
- (운영적 타협) minReplicaCount를 1로 두고 “warm” 유지
- (비용 최적화) 시간대별 크론 예열(출근 시간/배치 시작 전)
- (아키텍처) 라우팅 계층(llm-d/GAIE 기반)에서 대기열/백프레셔 전략
을 같이 봐야 합니다.

### Best Practice 3) Node autoscaling과 Pod autoscaling의 ‘시간상수’를 맞추기
Pod는 수 초~수십 초에 늘어나도, GPU 노드는 부팅/드라이버 준비 때문에 더 오래 걸립니다.  
대응:
- “buffer node”(빈 GPU 노드 1대 유지) vs “완전 0” 중 비용/지연 트레이드오프 결정
- 요청 급증이 잦으면, scale-to-zero는 오히려 사용자 경험을 망칠 수 있음(비용 절감보다 SLO 우선)

### 흔한 함정) GPU 공유(Time-slicing)로 “replica만 늘리면 처리량도 비례”한다고 착각
Time-slicing은 “더 많은 Pod에 GPU를 나눠줄 수는” 있지만, 2개 time-sliced GPU를 요청한다고 2배 성능을 보장하지 않는다고 명시합니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/22.9.2/gpu-sharing.html?utm_source=openai))  
LLM은 latency 민감 + 메모리 집약이라, 무작정 오버서브스크립션하면 tail latency가 폭발할 수 있습니다. MIG(격리) vs time-slicing(공유) 선택은 워크로드 특성(멀티테넌시/격리/지연)에 따라 갈립니다.

### 비용/성능/안정성 트레이드오프 요약
- **Prometheus/DCGM 기반**: 관측/대시보드 친화적, 표준적. 대신 지연/구성복잡도 증가. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/installation/install-dcgm-exporter.html?utm_source=openai))  
- **NVML 직결 External Scaler**: 스케일 신호 경로가 짧아지고 구성 단순화 가능. 대신 운영 책임(별도 컴포넌트)과 성숙도/보안/RBAC 검토 필요. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))  
- **DRA 도입**: 장기적으로 유연한 디바이스 할당/공유에 유리. 다만 기존 생태계/툴링과의 접점, 팀의 러닝커브를 고려해야 합니다. ([kubernetes.io](https://kubernetes.io/blog/2025/09/01/kubernetes-v1-34-dra-updates/?utm_source=openai))

---

## 🚀 마무리

2026년 8월 시점의 Kubernetes LLM 서빙 오토스케일링은 “HPA 하나로 끝”이 아니라, **(1) 트래픽 기반 scale-from-zero, (2) GPU 압력 기반 scale-up, (3) 노드/라우팅 계층**을 함께 설계하는 문제가 됐습니다.

도입 판단 기준을 간단히 정리하면:

- **트래픽 변동이 크고 idle GPU 비용이 아픈가?**  
  → KEDA + HTTP Add-on(또는 유사 패턴) 우선 검토 ([keda.sh](https://keda.sh/http-add-on/0.15/?utm_source=openai))
- **GPU가 병목인데 CPU 메트릭으로 스케일링하고 있나?**  
  → DCGM Exporter+Prometheus 또는 NVML 기반 External Scaler로 “GPU 신호”를 스케일 루프에 넣기 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/installation/install-dcgm-exporter.html?utm_source=openai))
- **멀티-테넌트/공유/격리 요구가 큰가?**  
  → MIG/Time-slicing 전략 + DRA 로드맵까지 같이 보기 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/22.9.2/gpu-sharing.html?utm_source=openai))

다음 학습 추천(실무 순서)
1) vLLM의 `/metrics`를 실제 트래픽에서 관측해 “내 워크로드의 병목 지표”를 정하기 ([docs.vllm.ai](https://docs.vllm.ai/en/v0.12.0/design/metrics/?utm_source=openai))  
2) KEDA로 트래픽/큐 기반 스케일을 안정화(쿨다운/폴링/스파이크 대응)  
3) GPU 메트릭 스케일을 추가(DCGM 파이프라인 또는 External Scaler)  
4) 라우팅 계층(GAIE/llm-d)까지 넣어 멀티-레플리카에서 tail latency를 다루기 ([github.com](https://github.com/kubernetes-sigs/gateway-api-inference-extension?utm_source=openai))

원하시면, 사용 중인 환경(EKS/GKE/AKS/온프렘), 서빙 엔진(vLLM/Triton/TGI), 목표 SLO(p95/TTFT), 모델 크기와 GPU 타입(A10/L40s/A100/H100/B200 등)을 알려주시면 위 예제를 **당신 상황에 맞춘 values.yaml/매트릭 임계치/스케일 정책**으로 구체화해드릴게요.