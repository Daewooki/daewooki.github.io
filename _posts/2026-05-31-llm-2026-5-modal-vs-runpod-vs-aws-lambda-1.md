---
title: "서버리스 LLM 배포 2026년 5월 판: Modal vs Runpod vs AWS Lambda, 그리고 Cold Start를 “설계로” 이기는 법"
date: 2026-05-31 04:40:05 +0900
categories: [Infra, Serverless]
tags: [infra, serverless, trend, 2026-05]
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
서버리스 LLM 배포가 해결하는 문제는 명확합니다: **GPU/서빙 인프라를 상시 띄우지 않고도(=idle cost 최소화), 트래픽 스파이크를 흡수하면서, API 형태로 LLM inference를 제공**하는 것. 다만 LLM은 일반적인 serverless 함수와 달리 **모델 로드(디스크→RAM→VRAM), 커널/JIT 컴파일, KV cache 준비** 같은 “초기화 비용”이 커서, **cold start가 곧 UX/비용/장애율**로 직결됩니다.

언제 쓰면 좋나
- **스파이크/버스트 트래픽**(하루 몇 번 몰림), **배치성 작업 + 간헐적 API**, **PoC→프로덕션으로 빠르게 검증**할 때
- 모델이 크더라도 **항상-on을 최소 1개만 유지**하고 나머지를 탄력 확장하고 싶을 때(“warm 1 + burst N”)

언제 쓰면 안 되나
- p95/p99 latency가 **항상 수백 ms~수초 이하로 고정**되어야 하고, 요청이 하루 종일 지속되는 서비스(결국 warm 유지 비용이 상시 발생)
- “scale to zero”를 고집하면서도 **TTFT(Time-To-First-Token) SLO**를 빡세게 가져가야 하는 경우(구조적으로 충돌)
- 운영 관점에서 **가용성/관측/디버깅**을 아주 강하게 요구하는데, 플랫폼 제약이 큰 경우(특히 GPU serverless는 아직 러프엣지가 남아있음)

---

## 🔧 핵심 개념
### 1) Cold start를 2개로 쪼개라: “컨테이너 준비” vs “모델 준비”
Modal 문서가 cold start 원인을 **queueing(대기) + initialization(첫 호출 초기화)**로 분리해 설명하는데, 이 구분이 실전 설계의 출발점입니다. ([modal.com](https://modal.com/docs/guide/cold-start?utm_source=openai))  
- **컨테이너 준비(Platform cold start)**: worker/container가 없어서 뜨는 시간(스케줄링, 이미지 pull 등)
- **모델 준비(Model cold start)**: weights 다운로드/캐시, 디스크→VRAM 로드, vLLM 엔진 준비, JIT/graph capture 등

대부분의 팀이 “모델 파일은 volume에 캐시했는데도 느리다”에서 막히는데, 그 다음 병목은 대개 **weights→VRAM 로드 + 엔진 초기화**입니다(디스크 캐싱만으로 해결 안 됨). ([reddit.com](https://www.reddit.com/r/RunPod/comments/1s2uw3z/cold_start_issues/?utm_source=openai))

### 2) Modal / Runpod / Lambda의 “서버리스”는 같은 단어, 다른 물건
- **Modal**: 컨테이너 재사용/워밍을 코드로 제어(`scaledown_window`, `min_containers`, `buffer_containers`)해서 cold start를 비용과 교환하는 모델. ([modal.com](https://modal.com/docs/guide/cold-start?utm_source=openai))  
  또한 vLLM OpenAI-compatible 예제를 공식 제공하며, cold start가 잦으면 vLLM 설정을 “FAST_BOOT” 쪽으로 기울이라고 가이드합니다. ([modal.com](https://modal.com/docs/examples/vllm_inference?utm_source=openai))
- **Runpod Serverless**: Endpoint 중심(큐 기반 vs 로드밸런싱). cold start 정의/라이프사이클이 문서에 명확하고, **Active workers(항상-on)**로 cold start를 제거할 수 있다고 못 박습니다. ([docs.runpod.io](https://docs.runpod.io/serverless/overview?utm_source=openai))  
  추가로 Flash/FlashBoot 계열에서는 `workers=(min,max)`, `idle_timeout`로 warm pool을 설계하는 모델을 강하게 드러냅니다. ([docs.runpod.io](https://docs.runpod.io/flash/execution-model?utm_source=openai))
- **AWS Lambda**: (GPU inference 관점에서) “LLM을 Lambda로 직접 돌린다”는 것보다, **front door / orchestration / lightweight pre/post**에 강점. cold start 최적화로 SnapStart가 있지만 **Java 등 특정 런타임 제약**이 있고, 컨테이너 이미지에는 적용되지 않습니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html?utm_source=openai))  
  즉 “GPU serverless LLM”의 주력이라기보다, **서빙 앞단(인증/라우팅/캐시/요청 shaping) + 비동기 오케스트레이션** 쪽이 현실적입니다.

### 3) Cold start 대응의 3대 레버(그리고 트레이드오프)
1) **Warm pool (min workers / active workers)**  
   - 가장 확실함. 대신 **idle cost** 발생. Runpod는 Active workers가 곧 “cold start 제거”라고 명시. ([docs.runpod.io](https://docs.runpod.io/serverless/endpoints/endpoint-configurations?utm_source=openai))  
2) **Idle timeout / scaledown window를 늘려 “semi-warm” 유지**  
   - sporadic 트래픽(몇 분 간격)에 특히 효율적. Modal의 `scaledown_window`가 대표. ([modal.com](https://modal.com/docs/guide/cold-start?utm_source=openai))  
3) **초기화 자체를 줄이기(FAST_BOOT, 캐시/볼륨, 엔진 옵션)**  
   - Modal vLLM 예제는 cold start가 잦으면 `FAST_BOOT=True`로 “부팅 빠르게 ↔ 토큰 처리 성능”을 트레이드오프로 제시. ([modal.com](https://modal.com/docs/examples/vllm_inference?utm_source=openai))  
   - Runpod는 네트워크 볼륨으로 모델 재다운로드를 피하라고 강하게 권장(파일 fetch cold start 감소). ([docs.runpod.io](https://docs.runpod.io/tutorials/serverless/run-ollama-inference?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: **OpenAI-compatible endpoint**를 표준 인터페이스로 만들고(클라이언트/SDK 재사용), cold start를 “warm 1 + burst N”로 제어합니다. 아래는 (1) Modal, (2) Runpod Flash 스타일, (3) Lambda를 앞단 라우터로 두는 예시입니다.

### 1) Modal: vLLM OpenAI-compatible 서버 + cold start 튜닝 포인트
```python
# modal_vllm_server.py
# 실행: modal deploy modal_vllm_server.py
# 요구: modal 패키지, Modal 프로젝트 설정

import os
import subprocess
import time
import modal

app = modal.App("llm-server-vllm")

# cold start가 잦으면 FAST_BOOT=True 권장(부팅 빠르게, 런타임 처리량 일부 희생)
FAST_BOOT = os.environ.get("FAST_BOOT", "true").lower() == "true"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm==0.8.0",           # 예시 버전(프로젝트에 맞게 고정)
        "fastapi==0.115.0",
        "uvicorn==0.30.0",
    )
)

# 핵심: scaledown_window로 "조금 더 오래 warm 유지" (비용과 교환)
# (Modal 문서의 cold start 가이드 참고)
@app.function(
    gpu="H100",
    image=image,
    timeout=60 * 20,
    scaledown_window=60 * 10,  # 10분간 idle이어도 내려가지 않게(스파이크/간헐 트래픽용)
)
@modal.web_server(port=8000)
def serve():
    model = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")

    # FAST_BOOT일 때는 JIT/graph capture 등을 줄이는 방향으로 vLLM 옵션을 조정하는 식으로 운영
    # (정확한 플래그는 vLLM/모델/드라이버에 따라 달라서, 팀 표준 preset을 두는 게 좋음)
    args = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model,
        "--host", "0.0.0.0",
        "--port", "8000",
    ]
    if FAST_BOOT:
        args += ["--disable-log-stats"]  # 예: 부팅/관측 오버헤드 일부 절감(환경에 맞게 조정)
    p = subprocess.Popen(args)

    # “프로세스 떴다”가 아니라 “모델 ready”까지 기다려야 health가 의미가 있음
    # (실전에서는 /health 엔드포인트 probe 권장)
    time.sleep(2)
    return p.wait()
```

예상 동작
- 최초 호출: 컨테이너 + 모델 준비로 느릴 수 있음
- 10분 내 재호출: `scaledown_window` 덕에 warm 컨테이너 재사용 확률↑ → latency 안정화

Modal이 공식으로 vLLM OpenAI-compatible 예제를 제공한다는 점, 그리고 cold start 잦을 때 FAST_BOOT 트레이드오프를 가이드한다는 점이 “프로젝트 적용 판단”에서 큽니다. ([modal.com](https://modal.com/docs/examples/vllm_inference?utm_source=openai))

### 2) Runpod Flash: workers(min,max) + idle_timeout으로 “warm 1 + burst 10”
```python
# runpod_flash_endpoint.py
# 실행(개략): flash build && flash deploy (Runpod Flash CLI/계정 필요)
# 목표: (1) 최소 1개 warm worker로 cold start 제거, (2) 트래픽 시 최대 10개까지 확장

from runpod_flash import Endpoint, GpuType, NetworkVolume

api = Endpoint(
    name="llm-prod",
    gpu=GpuType.NVIDIA_GEFORCE_RTX_4090,  # 예시: 비용/성능 밸런스 GPU
    workers=(1, 10),          # min=1로 첫 요청 cold start 제거
    idle_timeout=1800,        # 30분: 간헐 트래픽이면 비용 대비 효과 큼
    execution_timeout_ms=60_000,
    volume=NetworkVolume(name="llm-weights"),  # 모델/캐시를 volume에 고정
)

# OpenAI-compatible을 직접 구현하기보다,
# 내부적으로는 /chat 같은 API를 만들고 앞단에서 변환하는 것도 운영상 깔끔함
@api.post("/chat")
async def chat(req: dict) -> dict:
    # 여기서 vLLM 서버에 프록시하거나, 직접 transformers/vLLM 엔진을 호출
    # (핵심은 "첫 요청 때 lazy load" 안 하도록, worker start 시 preload하는 방향)
    prompt = req["prompt"]
    return {"text": f"echo: {prompt[:80]}"}

@api.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

핵심 포인트
- Runpod Flash 문서가 **`workers`와 `idle_timeout`이 cold/warm start 빈도를 직접 결정**한다고 명시합니다. ([docs.runpod.io](https://docs.runpod.io/flash/execution-model?utm_source=openai))  
- Runpod Serverless(콘솔 기반)도 **Active workers**로 동일한 설계를 제공합니다(사실상 min workers). ([docs.runpod.io](https://docs.runpod.io/serverless/endpoints/endpoint-configurations?utm_source=openai))  
- 모델 캐시는 **네트워크 볼륨**이 1차 방어선(재다운로드 제거)입니다. ([docs.runpod.io](https://docs.runpod.io/tutorials/serverless/run-ollama-inference?utm_source=openai))

### 3) AWS Lambda: “LLM GPU 서버리스”가 아니라 “앞단 제어면”으로 쓰는 패턴
Lambda를 LLM inference 본체로 두기보단, 다음을 추천합니다:
- 요청 인증/요금제/Rate limit
- Prompt/Tool schema 검증, PII 필터
- 캐시 키 설계(동일 질의 캐싱)
- provider 라우팅(Modal/Runpod/Managed API) 및 fallback

SnapStart는 cold start를 줄일 수 있지만 **런타임/기능 제약이 명확**하니(특히 컨테이너 이미지 미지원), “GPU inference를 Lambda로”를 고집하기보다 **control plane**으로 두는 편이 안전합니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (추천 3가지)
1) **“warm 1 + burst N”을 기본값으로 잡아라**  
   scale-to-zero는 비용은 좋아 보이지만, LLM은 cold start 비용이 커서 UX가 무너집니다. Runpod도 min worker/active worker로 cold start 제거를 정면으로 권장합니다. ([docs.runpod.io](https://docs.runpod.io/serverless/endpoints/endpoint-configurations?utm_source=openai))

2) **health check는 “프로세스 up”이 아니라 “모델 ready”로**  
   커뮤니티에서 “running인데 서빙이 안 됨” 류의 운영 이슈가 반복됩니다. 이런 류의 문제는 결국 **readiness probe 설계**(실제 추론 1토큰까지)로 줄여야 합니다. ([reddit.com](https://www.reddit.com/r/RunPod/comments/1tbjjdg/runpod_endpoint_says_running_but_isnt_actually/?utm_source=openai))

3) **vLLM 같은 서빙 엔진을 쓰고, cold start 시나리오에 맞춰 옵션 프리셋을 나눠라**  
   Modal 예제처럼 “FAST_BOOT(부팅) vs 처리량(토큰)”을 분리해 운영 프리셋으로 가져가면, 트래픽 패턴에 따라 합리적 선택이 됩니다. ([modal.com](https://modal.com/docs/examples/vllm_inference?utm_source=openai))

### 흔한 함정/안티패턴
- **모델 파일만 캐시하면 끝이라고 생각**: 실제 병목이 weights→VRAM 로드/엔진 초기화면, 디스크 캐싱은 체감이 제한적입니다. 결국 warm worker가 필요해집니다. ([reddit.com](https://www.reddit.com/r/RunPod/comments/1s2uw3z/cold_start_issues/?utm_source=openai))  
- **idle_timeout을 너무 짧게**: Runpod 기본 idle timeout이 짧은 편이라(엔드포인트 설정 기본값이 짧게 잡히는 케이스) 트래픽이 뜸하면 매번 cold start를 맞습니다. ([docs.runpod.io](https://docs.runpod.io/serverless/endpoints/endpoint-configurations?utm_source=openai))  
- **장애를 “재시도”로 덮기**: 서버리스 GPU는 초기화/스케줄링/볼륨 상태 등으로 “애매하게 걸리는” 실패가 나올 수 있습니다. 재시도는 idempotency 보장(요금/중복 응답)과 함께, “언제 재시도할지”를 분류해야 합니다(예: 429/큐 지연 vs 5xx vs timeout). 운영 경험담이 이런 류의 문제를 지적합니다. ([reddit.com](https://www.reddit.com/r/RunPod/comments/1tbjjdg/runpod_endpoint_says_running_but_isnt_actually/?utm_source=openai))

### 비용/성능/안정성 트레이드오프(의사결정 기준)
- **scale-to-zero**: 최저 비용 잠재력 / 최악의 p95-p99 / cold start로 장애처럼 보이는 구간 발생
- **min=1 warm**: 비용은 조금 증가 / 사용자 경험 급상승 / 운영 난이도 급감
- **항상-on 여러 개**: 거의 “서버리스의 껍데기만” 남음. 이쯤이면 Dedicated(상시 Pod/VM/K8s)와 비교해서 더 나은지 재평가 필요

---

## 🚀 마무리
정리하면, 2026년 5월 기준으로 “서버리스 LLM 배포”의 본질은 **GPU를 얼마나 영리하게 warm으로 유지할지(그리고 초기화를 얼마나 통제할지)** 입니다.  
- Modal은 cold start를 구성 요소로 쪼개 튜닝할 수 있고(vLLM 예제/FAST_BOOT 같은 가이드 포함), ([modal.com](https://modal.com/docs/guide/cold-start?utm_source=openai))  
- Runpod은 workers/idle_timeout/active workers로 warm pool을 직접 설계하게 해주며, 모델 캐시(볼륨)와 state retention(FlashBoot 등)으로 cold start를 줄이려는 방향이 뚜렷합니다. ([docs.runpod.io](https://docs.runpod.io/flash/execution-model?utm_source=openai))  
- AWS Lambda는 GPU inference 본체보다는 **앞단 제어/오케스트레이션**에 두는 게 제약 대비 효율이 좋고, SnapStart도 제약을 정확히 이해하고 써야 합니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html?utm_source=openai))

도입 판단 기준(실무용)
1) 트래픽 패턴이 “간헐 + 스파이크”인가? → **serverless 유리**
2) SLO가 p99까지 엄격한가? → **min warm(≥1)** 없으면 거의 불가능
3) 하루 중 warm 유지 시간이 길어지는가? → 어느 순간 **Dedicated + autoscale**이 더 싸고 안정적일 수 있음

다음 학습 추천
- Modal의 vLLM OpenAI-compatible 예제와 cold start 가이드 문서를 그대로 베이스라인으로 삼아, “FAST_BOOT/scaledown_window 프리셋”을 팀 표준으로 만들기 ([modal.com](https://modal.com/docs/examples/vllm_inference?utm_source=openai))  
- Runpod은 Endpoint 설정(Active workers/Idle timeout)과 Flash의 workers/idle_timeout 베스트 프랙티스를 읽고, “warm 1 + burst N” 템플릿을 IaC처럼 고정하기 ([docs.runpod.io](https://docs.runpod.io/serverless/endpoints/endpoint-configurations?utm_source=openai))

원하면, 당신의 전제(모델 크기, 동시성, 목표 TTFT/p95, 하루 트래픽 분포, 예산 상한)를 받아서 **Modal/Runpod 각각에 대해 “권장 workers/idle_timeout/엔진옵션”을 수치로 박은 운영안**(간단한 비용 추정 포함)까지 구체화해드릴게요.