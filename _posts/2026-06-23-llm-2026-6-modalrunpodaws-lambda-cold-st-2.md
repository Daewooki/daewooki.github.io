---
title: "서버리스 LLM 배포의 현실(2026년 6월): Modal·RunPod·AWS Lambda에서 cold start를 “구조적으로” 없애는 방법"
date: 2026-06-23 04:10:35 +0900
categories: [Infra, Serverless]
tags: [infra, serverless, trend, 2026-06]
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
서버리스 LLM 배포가 해결하는 문제는 명확합니다: **트래픽이 들쭉날쭉한 추론 서비스**에서 “항상 켜둔 GPU” 비용을 피하면서도, 배포/스케일링/운영 부담을 줄이는 것. 문제는 더 명확합니다: **cold start가 곧 UX**가 됩니다. LLM은 컨테이너 기동 + CUDA 초기화 + 수 GB~수십 GB weight 로드 + 엔진(vLLM 등) 초기화가 겹치면서, 전통적인 FaaS의 cold start 감각으로 접근하면 그대로 망합니다.

언제 쓰면 좋은가
- **버스트 트래픽**(이벤트성, 배치성, 낮은 평균 QPS) + **P95 지연에 약간의 여유**가 있는 서비스
- 팀이 **쿠버네티스/오토스케일링 운영을 최소화**하고 싶고, “GPU 인프라를 제품이 아니라 수단”으로 보고 싶을 때
- 모델이 7B~소형(혹은 강한 quant)이고, 요청당 생성 길이가 길지 않은 경우(초기 지연이 상대적으로 덜 티 남)

언제 쓰면 안 되는가
- **P95/P99가 SLA로 묶인 실시간**(채팅 UX, 음성 대화, 에이전트 루프 등)인데 warm 유지 비용을 감당 못 하는 경우
- **대형 모델 + 긴 컨텍스트 + 높은 동시성**이 기본값인 경우(결국 “상시 GPU”로 회귀)
- 모델/LoRA/툴체인이 자주 바뀌어 이미지·캐시 전략이 안정화되지 않은 초기 단계(배포가 곧 cold start 리스크)

핵심 결론을 먼저 말하면: 2026년 현재 “serverless LLM”의 승부는 **엔진(vLLM) 최적화보다 ‘weight를 어디에, 어떤 상태로, 얼마나 오래 붙잡아 두느냐’**에 더 가깝습니다. 플랫폼들은 이 문제를 각기 다른 방식으로 해결합니다: RunPod은 **pre-warmed worker pool + Cached Models**를 전면에 내세우고, Modal도 vLLM 같은 워크로드는 **min_containers/buffer_containers로 warm 인스턴스 유지**를 사실상 권장합니다. ([runpod.io](https://www.runpod.io/product/serverless?utm_source=openai))

---

## 🔧 핵심 개념
### 1) cold start를 “단계”로 쪼개야 해결책이 보인다
LLM 추론 서버의 cold start는 보통 4단계가 직렬로 터집니다.

1. **Scheduling/Provisioning**: 빈 GPU 잡기(큐 대기 포함)
2. **Image pull / container boot**: 이미지 다운로드/레이어 마운트/프로세스 기동  
3. **Runtime init**: CUDA, tokenizer, Python import 폭탄
4. **Weight staging & engine init**: HF 다운로드/디스크→GPU 적재, vLLM 엔진 초기화(여기서 1~수분 흔함)

RunPod 문서도 “대기시간(Delay time)=워커 대기+콜드스타트”로 보고, **Cached models가 cold start를 ‘major’하게 줄인다**고 못 박습니다. ([docs.runpod.io](https://docs.runpod.io/serverless/development/optimization?utm_source=openai))  
즉, 애플리케이션 레벨에서 할 수 있는 건 (3)(4)를 최대한 줄이는 것인데, (4)의 절대값을 줄이려면 결국 **weight의 위치**가 관건입니다.

### 2) Modal vs RunPod vs AWS Lambda: 같은 “서버리스”가 아니다
#### RunPod Serverless
- 핵심: **active worker pools + pre-warmed GPUs**로 초기화를 줄이고, “Cached Models”로 **이미지와 weight를 분리**해서 weight staging을 가볍게 만듭니다. ([runpod.io](https://www.runpod.io/product/serverless?utm_source=openai))  
- 하지만 커뮤니티 피드백을 보면, 캐시/볼륨/가용 GPU 타입 등 운영상의 제약과 변동성이 이슈가 되기도 합니다(실서비스면 반드시 사전 검증 필요). ([reddit.com](https://www.reddit.com/r/RunPod/comments/1u9updz/serverless_gpu_availability_options/?utm_source=openai))

#### Modal
- Python-first DX가 강점이고, LLM 서빙은 “잘 되지만” **vLLM 자체가 cold start가 길어**서 운영 배포에선 **min_containers=1 이상으로 warm 유지 권장** 같은 형태로 현실 타협이 들어갑니다. ([docs.liquid.ai](https://docs.liquid.ai/docs/inference/modal-deployment?utm_source=openai))  
- 즉, Modal은 “진짜 scale-to-zero로 LLM을 굴리기”보다는, **서버리스 UX로 관리되는 ‘항상 켜진 최소 1개’** 패턴이 실전적입니다.

#### AWS Lambda
- GPU가 아닌 CPU 중심이므로, “LLM 전체”를 올리기보다는 **(a) 라우팅/가드레일/(b) 프롬프트 캐시/(c) 스트리밍 게이트웨이** 같은 역할이 적합합니다.
- Lambda는 **Response Streaming**과 **Lambda Web Adapter** 조합으로 “첫 토큰을 빨리 보내 UX를 살리는” 전략을 공식적으로 제공합니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))  
- (중요) Lambda의 cold start는 컨테이너/런타임/의존성 크기 영향이 큰데, AWS 쪽 연구/발표에서도 “이미지의 일부만 온디맨드 로딩” 같은 방향으로 최적화해왔습니다. ([usenix.org](https://www.usenix.org/system/files/atc23-brooker.pdf?utm_source=openai))

### 3) “cold start 대응”의 3가지 레버
1. **Warm capacity 유지**: min_containers / active workers / provisioned concurrency 같은 형태  
2. **Weight pre-staging**: Cached Models, 레이어드 이미지(가급적 weight 분리), 볼륨 전략  
3. **UX 레벨 숨기기**: streaming으로 “첫 토큰/진행률”을 빨리 보내고, 백그라운드에서 완전 준비

최근 vLLM cold start를 분석한 연구도 “startup latency 자체가 중요한 병목”임을 다루며, 엔진 레벨 최적화가 진행 중입니다. 하지만 제품 관점에서는 여전히 (1)(2)가 체감 지연을 좌우합니다. ([arxiv.org](https://arxiv.org/abs/2606.07362?utm_source=openai))

---

## 💻 실전 코드
아래는 제가 2026년 기준으로 가장 실무적인 조합이라고 보는 패턴입니다.

- **RunPod Serverless GPU(vLLM)**: 추론 담당, Cached Models로 cold start 감소
- **AWS Lambda(Streaming Gateway)**: 사용자 요청을 받아 즉시 스트리밍 연결을 열고, RunPod 호출을 프록시 (필요 시 fall-back/큐잉/레이트리밋)

### 0) 전제
- RunPod: Serverless Endpoint를 만들고(콘솔/CLI), vLLM을 OpenAI-compatible로 띄운다고 가정
- AWS: Lambda Function URL + Response Streaming 사용

### 1) RunPod: Cached Models 전제로 vLLM worker 준비(핵심만)
RunPod 문서 기준으로 Cached Models는 `/runpod-volume/` 경로를 사용하며, 네트워크 볼륨 대비 **캐시된 모델이 훨씬 빠르게 로드**된다고 설명합니다. ([docs.runpod.io](https://docs.runpod.io/serverless/endpoints?utm_source=openai))

```bash
# (예시) runpodctl로 서버리스 엔드포인트 생성 시 환경변수로 모델 지정
# 실제 template-id, GPU 타입, 스케일 설정은 팀 표준에 맞추세요.
runpodctl serverless create \
  --name "llm-vllm-prod" \
  --template-id "tpl_xxx" \
  --env MODEL_NAME=meta-llama/Llama-3.1-8B-Instruct
```

```python
# handler.py (RunPod serverless handler 패턴의 요지)
# - 여기서는 "모델 다운로드"가 아니라 "캐시/로컬 경로에서 로드"가 핵심
# - vLLM 서버를 별도 프로세스로 띄우고(또는 템플릿이 제공), readiness를 체크한 뒤 요청을 프록시하는 방식이 실무적

import os, time, subprocess, requests
import runpod

VLLM_BASE = os.environ.get("VLLM_BASE", "http://127.0.0.1:8000")

def _ensure_vllm():
    # 이미 떠 있으면 패스
    try:
        r = requests.get(f"{VLLM_BASE}/health", timeout=0.5)
        if r.status_code == 200:
            return
    except Exception:
        pass

    model = os.environ.get("MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")

    # 템플릿에 따라 vllm serve 커맨드가 달라질 수 있음
    subprocess.Popen([
        "bash", "-lc",
        f"vllm serve {model} --host 0.0.0.0 --port 8000 --enable-metrics"
    ])

    # readiness wait
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            r = requests.get(f"{VLLM_BASE}/health", timeout=1.0)
            if r.status_code == 200:
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("vLLM failed to become ready")

def handler(job):
    _ensure_vllm()

    prompt = job["input"]["prompt"]
    max_tokens = int(job["input"].get("max_tokens", 256))

    payload = {
        "model": "local",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False
    }
    r = requests.post(f"{VLLM_BASE}/v1/chat/completions", json=payload, timeout=300)
    r.raise_for_status()
    return r.json()

runpod.serverless.start({"handler": handler})
```

예상 출력(요지)
- warm 상태: 첫 응답 수초 내
- cold 상태: vLLM readiness 대기 + weight staging으로 수십초~수분까지 갈 수 있음(여기서 Cached Models가 차이를 만듦)

### 2) AWS Lambda: “스트리밍으로 UX를 살리는” 게이트웨이
Lambda는 공식적으로 **Response Streaming**을 지원하며, Python 등은 커스텀 런타임 또는 **Lambda Web Adapter**로 웹앱 스트리밍을 할 수 있습니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))

여기서는 “Lambda가 SSE(Server-Sent Events)로 즉시 연결을 열고, RunPod의 응답이 올 때까지 진행 상황을 흘려보내는” 패턴을 보여줍니다.

```python
# lambda_function.py (Python Response Streaming 개념 예시)
# 실제 배포는 AWS의 response streaming 샘플/런타임 형태에 맞춰 조정 필요.
import json, os, time, requests

RUNPOD_ENDPOINT_ID = os.environ["RUNPOD_ENDPOINT_ID"]
RUNPOD_API_KEY = os.environ["RUNPOD_API_KEY"]

def _runpod_sync(prompt: str):
    # runpod.rest 같은 REST 레퍼런스가 있으나, 팀에서는 공식 API 스펙/SDK로 고정 권장
    # 여기서는 개념적으로 "endpoint 실행"을 호출한다고 가정
    url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/run"
    headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}"}
    payload = {"input": {"prompt": prompt, "max_tokens": 256}}
    r = requests.post(url, headers=headers, json=payload, timeout=300)
    r.raise_for_status()
    return r.json()

def handler(event, context):
    prompt = json.loads(event.get("body") or "{}").get("prompt", "")

    # (1) 즉시 스트리밍 시작: 사용자에게 "접속됨"을 먼저 전달
    # 실제 스트리밍 구현은 Lambda response streaming 인터페이스에 맞게 작성하세요.
    chunks = []
    chunks.append("event: status\ndata: connected\n\n")
    chunks.append("event: status\ndata: warming_or_running\n\n")

    t0 = time.time()
    try:
        result = _runpod_sync(prompt)
        dt = time.time() - t0
        chunks.append(f"event: meta\ndata: {json.dumps({'latency_sec': dt})}\n\n")
        chunks.append(f"event: result\ndata: {json.dumps(result)}\n\n")
        chunks.append("event: done\ndata: ok\n\n")
    except Exception as e:
        chunks.append(f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n")

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/event-stream"},
        "body": "".join(chunks)
    }
```

이 구조의 장점
- RunPod이 cold start로 40초가 걸려도, 사용자는 **즉시 연결/진행 상태**를 받습니다.
- Lambda는 GPU를 들고 있지 않으니 비용 구조가 단순하고, 앞단에서 auth/레이트리밋/캐시를 깔끔하게 처리 가능
- “완전 서버리스”가 아니라도 UX는 서버리스처럼 보이게 만들 수 있습니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 적용 가능한 것 3가지)
1) **weight는 이미지에 넣지 말고, ‘플랫폼 캐시’에 태워라**  
RunPod의 Cached Models는 “이미지와 모델을 분리”해 cold start의 가장 큰 덩어리(다운로드/스테이징)를 줄이는 목적입니다. 네트워크 볼륨보다 빠르다고도 명시합니다. ([docs.runpod.io](https://docs.runpod.io/serverless/endpoints?utm_source=openai))

2) **“scale-to-zero”는 목표가 아니라 옵션이다: 최소 warm 1개를 숫자로 계산하라**  
Modal 쪽 가이드에서도 vLLM은 cold start가 길어 **min_containers=1** 같은 warm 유지가 권장됩니다. ([docs.liquid.ai](https://docs.liquid.ai/docs/inference/modal-deployment?utm_source=openai))  
실무에서는 “0으로 떨어뜨리면 아낄 돈” vs “cold start로 잃는 전환율/이탈”을 **금액으로** 놓고 결정해야 합니다.

3) **Streaming은 성능 최적화가 아니라 ‘인지 지연’ 최적화다**  
Lambda Response Streaming / Web Adapter는 “첫 바이트/첫 토큰을 빨리” 보내는 데 유효합니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))  
LLM은 생성 자체도 길기 때문에, 사용자 경험에서는 **TTFT(Time To First Token)**이 절반 이상입니다.

### 흔한 함정/안티패턴
- **요청마다 모델 로드/파이프라인 재구성**: 서버리스에서 “상태 없음”을 과하게 해석하면 매 호출마다 비용 폭발 + 지연 폭발
- **거대한 base image + 잦은 배포**: 배포=캐시 미스가 되면, cold start가 “가끔”이 아니라 “항상”이 됩니다(특히 이미지 pull 단계)  
- **가용 GPU 타입/쿼터/리전 편차 무시**: 서버리스 GPU는 “추상화된 것처럼 보여도” 결국 스케줄링 현실이 있고, 커뮤니티에서도 가용성/제약 이슈가 주기적으로 보입니다. ([reddit.com](https://www.reddit.com/r/RunPod/comments/1u9updz/serverless_gpu_availability_options/?utm_source=openai))

### 비용/성능/안정성 트레이드오프(의사결정 프레임)
- **Warm 유지(안정/저지연)** ↔ **Scale-to-zero(최저비용)**  
- **플랫폼 캐시 의존(빠름)** ↔ **완전 이식 가능한 이미지(재현성/이식성)**  
- **서버리스 endpoint(간편)** ↔ **persistent pod/service(예측 가능)**  
여기서 “정답”은 없고, 트래픽 패턴과 SLA가 정합니다.

---

## 🚀 마무리
2026년 6월 기준으로 서버리스 LLM 배포의 핵심은 “어떤 플랫폼이 더 빠르냐”보다 **cold start를 어떤 계층에서 흡수할 수 있냐**입니다.

- RunPod: **pre-warmed worker + Cached Models**로 weight 문제를 정면으로 풀려고 합니다. ([runpod.io](https://www.runpod.io/product/serverless?utm_source=openai))  
- Modal: DX가 뛰어나지만 vLLM급 워크로드는 **min_containers로 warm 유지**가 현실적인 운영 해법이 됩니다. ([docs.liquid.ai](https://docs.liquid.ai/docs/inference/modal-deployment?utm_source=openai))  
- AWS Lambda: LLM 본체보다는 **스트리밍 게이트웨이/오케스트레이션**으로 가치가 크고, Response Streaming/Web Adapter로 UX를 끌어올릴 수 있습니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))  

도입 판단 기준(체크리스트)
1) 우리 서비스는 **P95 TTFT 목표**가 몇 초인가? (cold start를 허용 가능한가)  
2) 트래픽이 버스트형인가, 상시형인가? (warm 1개가 결국 더 싼가)  
3) 모델 교체/배포 빈도가 높은가? (캐시 미스/이미지 pull 리스크가 큰가)  
4) “진짜 서버리스”가 필요한가, 아니면 “운영이 단순한 managed serving”이면 되는가?

다음 학습 추천
- vLLM cold start 분석 연구(엔진 관점)와, 플랫폼별 캐시/워밍 전략 문서를 함께 읽고 “내 워크로드의 병목 단계가 어디인지”부터 계측하세요. 특히 vLLM cold start 분석 논문은 병목을 구조적으로 보는 데 도움이 됩니다. ([arxiv.org](https://arxiv.org/abs/2606.07362?utm_source=openai))