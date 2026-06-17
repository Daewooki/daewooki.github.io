---
title: "GPU가 병목인 LLM 서빙, Kubernetes에서 “제대로” 오토스케일링하는 법 (2026년 6월 기준)"
date: 2026-06-17 04:57:42 +0900
categories: [Infra, Kubernetes]
tags: [infra, kubernetes, trend, 2026-06]
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
LLM inference는 CPU나 memory가 아니라 **GPU(SM utilization / VRAM / batch/queue)** 가 병목인 경우가 대부분인데, Kubernetes 기본 autoscaling(HPA)은 전통적으로 **CPU/Memory 중심**이라 “트래픽이 늘었는데도 GPU가 이미 95%인데 pod 수가 안 늘어나는” 상황이 자주 발생합니다. 이 문제는 vLLM/Triton 같은 서빙 엔진을 올려도 그대로고, 결국 수동으로 replica를 고정하거나(=비용 폭발), 늦은 반응의 커스텀 지표로 임시방편을 하게 됩니다.

2026년 6월 기준으로 실무에서 선택지는 크게 3가지 흐름으로 정리됩니다.

- **(A) DCGM Exporter → Prometheus → (Adapter) → HPA/KEDA**  
  가장 “정석”이지만 구성요소가 많고(관측/쿼리/어댑터), 지표 지연과 운영 복잡도가 생깁니다. DCGM Exporter는 Kubernetes pod 매핑 옵션과 MIG 지표까지 제공하는 게 강점입니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))
- **(B) KEDA External Scaler로 GPU 지표를 직접 먹이기(=Prometheus 생략 가능)**  
  최근 CNCF 블로그에서 **GPU autoscaling을 위해 external scaler를 직접 구현**하는 패턴이 구체적으로 공유됐습니다. “GPU는 CPU처럼 metrics-server만으로 해결이 잘 안 된다”는 현실을 정면으로 다룹니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))
- **(C) DRA(Dynamic Resource Allocation)로 ‘할당’ 자체를 구조적으로 개선**  
  Kubernetes 1.36에서 DRA가 더 성숙해졌고, NVIDIA가 GPU용 DRA driver를 커뮤니티에 기여하는 흐름이 이어지고 있습니다. 다만 **DRA는 ‘스케일링’이라기보다 ‘디바이스 할당/공유 모델’의 혁신**에 더 가깝고, 지금 당장 “LLM 서빙 오토스케일”만을 해결하려면 (A)/(B) 조합이 여전히 현실적입니다. ([kubernetes.io](https://kubernetes.io/blog/2026/05/07/kubernetes-v1-36-dra-136-updates/?utm_source=openai))

언제 쓰면 좋나?
- **요청량 변동이 큰 LLM API**, 특히 **batching 가능한(vLLM/Triton)** 서빙
- GPU가 비싸서 **idle을 줄여야 하는** 팀
- 최소 1~2주 단위로 트래픽 패턴이 변하는 서비스(=고정 replica가 곧 비용 낭비)

언제 쓰지 말아야 하나?
- **cold-start가 치명적**인 초저지연(예: p99 200ms 미만이 강제) 서비스인데, 모델 로딩/워밍업 전략이 없는 경우  
- GPU가 항상 70~90%로 꽉 차는 “지속 부하” 서비스(=오토스케일보다 capacity planning이 먼저)
- time-slicing 같은 **공유 전략을 쓰면서 per-pod attribution이 필요한데**, 관측 체인이 이를 감당 못 하는 경우(아래 함정 참고)

---

## 🔧 핵심 개념
### 1) “GPU 오토스케일”에서 실제로 스케일해야 하는 대상
LLM 서빙은 단순히 `replicas`를 늘리는 문제가 아니라,
- **단일 pod 내부에서 batching/큐잉으로 throughput을 키우는 것**
- **pod 수를 늘려 병렬 처리량을 늘리는 것**
- **노드/디바이스(GPU) 자체를 더 붙이는 것(Cluster Autoscaler/Node Auto-Provisioning)**  
이 3개가 같이 맞물립니다.

실무적으로 가장 흔한 실패는:
- GPU utilization이 95%인데도 **큐가 길어지는 걸 스케일러가 못 봄**
- 혹은 GPU utilization만 보고 스케일했다가 **batching 효율이 깨져 TPS가 오히려 떨어짐**

그래서 지표는 보통 2축이 필요합니다.
- **Workload 지표(서비스 내부):** queue depth, in-flight requests, tokens/sec, p95 latency  
- **Hardware 지표(노드/GPU):** SM utilization, VRAM used, power/throttle 등 (DCGM이 제공) ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))

### 2) DCGM Exporter가 “왜” 필요한가
DCGM Exporter는 NVIDIA DCGM 기반으로 `/metrics`에 GPU telemetry를 노출합니다. Kubernetes에서 중요한 포인트는:
- GPU Operator를 쓰면 **dcgm-exporter를 같이 배포**하는 게 일반적이고 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/23.3.2/getting-started.html?utm_source=openai))
- MIG 환경에서도 **GPU instance 단위 지표**를 제공할 수 있으며 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))
- Kubernetes 매핑 옵션을 켜면(문서상 `DCGM_EXPORTER_KUBERNETES`) pod-resources 정보를 이용해 **pod와 GPU를 엮은 형태의 지표**를 만들 수 있습니다(단, 공유/타임슬라이싱에서는 한계가 큼). ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))

### 3) KEDA가 왜 자주 등장하나 (HPA vs KEDA)
HPA는 “metrics API로 들어온 값”을 기준으로 replica를 조절합니다. 문제는 GPU 지표를 표준 resource metric로 넣기 어렵고, 보통은 custom/external metric이 필요합니다.

KEDA는 여기서 한 발 더 나가서:
- “queue length” 같은 **event-driven 지표**를 쉽게 붙이고
- 필요하면 **External Scaler(gRPC)** 로 아예 사용자 정의 스케일러를 붙입니다. ([keda.sh](https://keda.sh/docs/2.4/concepts/external-scalers/?utm_source=openai))

2026년 5월 CNCF 글이 흥미로운 이유는, 현업에서 많이 쓰는 “DCGM→Prometheus→PromQL→KEDA” 체인이 너무 무겁고 지연이 커서, **노드에 DaemonSet으로 GPU 지표를 직접 수집하고 external scaler로 KEDA에 제공**하는 구조를 제안/구현했기 때문입니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))

---

## 💻 실전 코드
아래는 “vLLM 기반 LLM 서빙 + GPU 기반 scale + (가능하면) 큐 기반 scale까지 확장”을 염두에 둔 현실적인 구성입니다.

### 단계 0) 전제
- Kubernetes에 NVIDIA GPU가 붙어 있고, GPU Operator 또는 최소 device plugin이 설치되어 GPU 리소스 요청이 동작해야 합니다. GPU Operator는 telemetry(DCGM Exporter)까지 한 번에 가져가는 게 장점입니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/23.3.2/getting-started.html?utm_source=openai))
- Prometheus가 이미 있다(대부분 있음)고 가정하고, 가장 재현 가능한 **DCGM Exporter + KEDA(Prometheus trigger)** 예제를 먼저 제시합니다.

### 단계 1) (클러스터) DCGM Exporter 배포
GPU Operator를 쓰면 이미 깔려 있을 수 있습니다. 직접 깐다면(예: Helm chart) 형태로 운영합니다. DCGM Exporter는 기본 수집 interval이 30초라서(문서 기본값), 오토스케일 관점에서는 **interval 튜닝**이 필요할 수 있습니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))

```bash
# (예시) GPU Operator를 이미 쓰는 경우, dcgm-exporter pod 확인
kubectl get pods -n gpu-operator -l app=nvidia-dcgm-exporter

# (직접 설치 시) nvidia dcgm-exporter helm repo를 쓰는 사례가 많습니다.
# helm repo add gpu-helm-charts https://nvidia.github.io/dcgm-exporter/helm-charts  (블로그/사례 기반) ([spheron.network](https://www.spheron.network/blog/keda-knative-gpu-autoscaling-kubernetes-llm-cold-start/?utm_source=openai))
```

### 단계 2) (애플리케이션) vLLM 서빙 Deployment + Service
“toy”가 아니려면 최소한:
- readinessProbe로 “모델 로딩 끝”을 판단
- requests/limits에 `nvidia.com/gpu: 1` 명시
- concurrency/batching을 vLLM 설정으로 제어  
가 필요합니다.

```yaml
# vllm-deploy.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-llama3-8b
  namespace: llm
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-llama3-8b
  template:
    metadata:
      labels:
        app: vllm-llama3-8b
        model: llama3-8b
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - "serve"
            - "meta-llama/Llama-3-8B-Instruct"
            - "--host=0.0.0.0"
            - "--port=8000"
            # 실무에서는 GPU 메모리/배치 정책이 오토스케일 효율에 직결됩니다.
            - "--gpu-memory-utilization=0.90"
            - "--max-num-batched-tokens=8192"
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: "1"
          readinessProbe:
            httpGet:
              path: /v1/models
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 5
            failureThreshold: 30
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-llama3-8b
  namespace: llm
spec:
  selector:
    app: vllm-llama3-8b
  ports:
    - name: http
      port: 8000
      targetPort: 8000
```

예상 출력(모델 준비 후):
```bash
kubectl -n llm get pods
# vllm-llama3-8b-xxxxx   1/1 Running

curl -s http://vllm-llama3-8b.llm.svc.cluster.local:8000/v1/models | jq .
# {"data":[...]} 형태로 모델 목록
```

### 단계 3) (오토스케일) KEDA ScaledObject: GPU utilization 기반
핵심은 “GPU utilization을 Prometheus에서 가져와 external metric으로 replica를 조절”하는 것입니다.

- DCGM Exporter는 `DCGM_FI_DEV_GPU_UTIL` 같은 지표를 노출합니다(환경/버전에 따라 label은 다를 수 있음). ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))
- KEDA는 Prometheus trigger로 해당 지표를 쿼리하고, threshold를 넘으면 스케일합니다.

```yaml
# keda-scaledobject.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vllm-gpu-autoscale
  namespace: llm
spec:
  scaleTargetRef:
    name: vllm-llama3-8b
  minReplicaCount: 1
  maxReplicaCount: 6
  pollingInterval: 10        # 10초마다 체크
  cooldownPeriod: 120        # 2분 동안 안정화
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-operated.monitoring.svc.cluster.local:9090
        metricName: dcgm_gpu_util_avg
        # "이 디플로이먼트가 올라간 GPU의 util 평균"을 이상적으로는 보고 싶지만,
        # 실제로는 label/매핑 제약 때문에 우선 namespace/app 기준으로 근사하는 경우가 많습니다.
        query: |
          avg(DCGM_FI_DEV_GPU_UTIL{namespace="llm"})
        threshold: "70"
```

여기서 중요한 판단 기준:
- **GPU util만으로 스케일하면** batching/큐잉에 의해 util이 높아도 latency가 안정적인 경우 “불필요한 scale-out”이 될 수 있습니다.
- 그래서 다음 단계로 “서비스 내부 queue depth / p95 latency”를 함께 trigger로 넣는 게 더 안전합니다(AND/OR 전략은 KEDA 구성에 따라 다르게 설계).

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) GPU util 하나로 끝내지 말고, “LLM 서빙 지표”를 섞어라
DCGM은 “GPU가 바쁜지”는 말해주지만, “사용자가 느끼는 지연”을 직접 대변하지 않습니다. 실무에서는
- `queue_depth`, `in_flight`, `tokens/sec`, `p95 latency`
같은 앱 지표를 함께 써서 “scale-out은 늦게, scale-in은 더 늦게” 같은 정책을 둡니다. (관측/튜닝 비용은 들지만 비용 폭탄을 막습니다.)

### Best Practice 2) metric lag를 먼저 측정해라 (특히 Prometheus 체인)
CNCF 글에서 지적하듯, **DCGM→Prometheus→쿼리→KEDA** 체인은 구성요소가 늘수록 지연/운영 부담이 늘어납니다. 그래서 최근에는 **KEDA External Scaler로 Prometheus를 생략**하려는 시도가 늘고 있습니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))  
“우리 서비스는 burst가 10~20초 안에 들어온다”면, 이 지연이 실제 장애로 이어질 수 있습니다.

### Best Practice 3) MIG vs time-slicing은 ‘오토스케일 지표의 신뢰도’ 관점에서 결정하라
- MIG는 “하드 파티셔닝”이라 DCGM에서 instance 단위 지표가 비교적 명확합니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))
- time-slicing은 “공유”라, per-pod attribution이 깔끔하지 않을 수 있고(커뮤니티에서도 이 지점이 자주 언급됨), util 지표가 스케일 판단을 오염시키기 쉽습니다. ([reddit.com](https://www.reddit.com/r/kubernetes/comments/1s7lcsj/how_are_you_all_tracking_perpod_gpu_utilization/?utm_source=openai))

### 흔한 함정 1) scale-to-zero를 GPU 서빙에 무작정 적용
KEDA/Knative 조합으로 GPU inference를 scale-to-zero까지 가는 글/사례가 늘고 있지만, LLM은 **모델 로딩(수 GB~수십 GB), CUDA graph warmup, KV cache** 때문에 cold start가 큽니다. “비용”만 보고 0으로 내렸다가 SLO를 깨는 경우가 많습니다. (최소 1 replica 유지 + 야간 downscale 정도가 현실적)

### 흔한 함정 2) “GPU utilization 70%면 scale-out” 같은 단일 룰로 비용이 줄 거라 착각
LLM은 continuous batching이 잘 되면 util이 높아도 latency가 안정적일 수 있습니다. 이때 scale-out하면:
- throughput이 선형으로 늘지 않고,
- 오히려 batch가 쪼개져 **토큰당 비용이 증가**할 수 있습니다.  
즉 “GPU를 더 붙이는” 것보다 “배치/큐 정책을 조정”하는 게 먼저인 구간이 있습니다.

### 트레이드오프 요약(비용/성능/안정성)
- **Prometheus 기반(정석)**: 안정적/표준적이지만 지연+운영비 증가
- **External scaler 직결**: 빠르고 단순해질 수 있으나, 자체 운영(가용성/보안/업그레이드) 책임이 커짐 ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))
- **MIG**: 격리/예측 가능성↑, 유연성↓(프로파일 제약)
- **time-slicing**: 유연성↑, 측정/격리/디버깅 난이도↑

---

## 🚀 마무리
2026년 6월 시점에서 Kubernetes에서 LLM GPU 오토스케일을 “프로덕션답게” 하려면 결론은 이겁니다.

1) **GPU 지표(DCGM)만으로는 부족**하고, LLM 서빙 지표(큐/지연/토큰 처리량)를 함께 봐야 합니다. DCGM Exporter는 여전히 GPU telemetry의 표준 축입니다. ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))  
2) 구현 경로는 **(정석) DCGM→Prometheus→KEDA/HPA**가 가장 재현 가능하지만, burst 대응/운영 단순화를 위해 **KEDA External Scaler 패턴**이 빠르게 확산 중입니다. ([cncf.io](https://www.cncf.io/blog/2026/05/27/gpu-autoscaling-on-kubernetes-with-keda-building-an-external-scaler/?utm_source=openai))  
3) DRA는 “GPU 할당/공유”를 구조적으로 바꾸는 큰 흐름이고, 앞으로 fractional/공유 모델이 정교해질 여지가 큽니다. 다만 당장 오토스케일 문제를 해결하는 1차 해법은 여전히 관측+스케일 컨트롤러 설계입니다. ([kubernetes.io](https://kubernetes.io/blog/2026/05/07/kubernetes-v1-36-dra-136-updates/?utm_source=openai))

도입 판단 기준(빠른 체크리스트)
- 트래픽 변동이 크고 GPU idle이 크다 → KEDA 기반 autoscaling 가치 큼
- SLO가 빡세고 cold-start가 치명적이다 → scale-to-zero는 보수적으로, 최소 replica 유지
- multi-tenant / GPU 공유가 필요하다 → MIG/DRA/스케줄러까지 포함해 “할당 전략”부터 재설계

다음 학습 추천
- KEDA External Scaler 설계(지표 지연/단순화 관점) ([keda.sh](https://keda.sh/docs/2.4/concepts/external-scalers/?utm_source=openai))  
- DCGM Exporter의 MIG/Pod 매핑 옵션과 한계 정리 ([docs.nvidia.com](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html?utm_source=openai))  
- Kubernetes DRA 개념과 GPU 드라이버/에코시스템 동향 ([kubernetes.io](https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation?utm_source=openai))

원하면, 위 예제를 **“GPU util + queue depth(p95 latency) 이중 트리거”**로 확장한 KEDA 설정(또는 Prometheus 없이 External Scaler로 단순화한 아키텍처)까지, 당신 환경(GKE/AKS/EKS, MIG 여부, vLLM/Triton/KServe 사용 여부)에 맞춰 구체 매니페스트로 이어서 작성해줄게요.