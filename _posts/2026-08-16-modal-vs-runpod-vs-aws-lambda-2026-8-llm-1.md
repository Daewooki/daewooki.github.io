---
title: "Modal vs Runpod vs AWS Lambda: “서버리스 LLM 배포”에서 cold start를 이기는 현실적인 설계"
description: "서버리스 LLM 배포의 본질적인 문제는 간단합니다. “요청이 없을 땐 비용 0에 가깝게, 요청이 오면 즉시(혹은 예측 가능하게) 토큰을 뽑아야 한다”는 상충 목표를 동시에 만족해야 합니다."
date: 2026-08-16 01:47:25 +0900
categories: [Infrastructure, Serverless]
tags: [infra, serverless]
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
서버리스 LLM 배포의 본질적인 문제는 간단합니다. **“요청이 없을 땐 비용 0에 가깝게, 요청이 오면 즉시(혹은 예측 가능하게) 토큰을 뽑아야 한다”**는 상충 목표를 동시에 만족해야 합니다. LLM은 (1) 컨테이너 부팅, (2) Python/torch import, (3) 모델 weight 다운로드/로딩, (4) GPU 메모리 적재, (5) 커널/JIT warm-up까지 “첫 요청 전 준비”가 길어 **cold start가 곧 사용자 체감 지연**으로 직결됩니다.

언제 쓰면 좋은가
- 트래픽이 **버스트 형태**(낮엔 많고 밤엔 거의 없음)이고, 상시 GPU를 묶어두기 싫을 때
- 모델을 자주 바꾸거나 A/B 테스트, 실험 배포가 잦을 때
- 백엔드가 이미 job/queue 기반 비동기 흐름을 받아들일 수 있을 때(`/run`→`/status` 같은 패턴)

언제 쓰면 안 되는가
- “항상 300ms 이하 TTFT” 같은 **강한 SLO**가 필요하고 트래픽이 꾸준하다면, 결국 **always-on**(혹은 provisioned capacity)로 가는 편이 총비용/안정성에서 유리합니다.
- 요청이 **동기/인터랙티브**이고 사용자가 기다리는 UX라면, cold start 최적화가 한계에 부딪힐 때가 많습니다(특히 30B+).

---

## 🔧 핵심 개념
### 1) cold start를 쪼개서 봐야 한다
cold start는 하나가 아니라 보통 두 덩어리입니다.

1) **큐잉 지연(“warm worker가 없어서 기다림”)**  
   - 플랫폼이 “0 → 1”로 worker를 올릴 때 발생
   - 해결책: *warm pool(최소 유지 컨테이너/워커)*, 버퍼, 스케일 정책

2) **초기화 지연(“컨테이너는 떴는데 준비가 느림”)**  
   - torch import, weight 로딩, tokenizer 준비, vLLM 엔진 기동 등
   - 해결책: *스냅샷/상태 재사용*, *모델 캐시*, *초기화 코드를 첫 요청에서 분리*

Modal은 이 두 영역을 문서에서 명확히 구분하고(큐잉 vs 초기화) 이를 줄이기 위한 파라미터(`min_containers`, `buffer_containers`, `scaledown_window`)와 **Memory Snapshot**을 제공합니다.[^1]  
Runpod도 worker가 0이면 자동으로 시작되고 요청이 큐에 쌓이는 흐름을 공식 문서에서 설명합니다.[^2]

### 2) Modal: “스냅샷으로 초기화를 없애는” 쪽이 강하다
Modal의 핵심은 **Memory Snapshot**입니다. “초기화로 만들어진 메모리 상태(라이브러리 import 결과, 모델 로딩 이후 상태 등)를 디스크에 저장해두고 다음 부팅에서 복원”하는 방식이라, 초기화가 무거울수록 이득이 커집니다. 문서 기준 실무에서 3~10배 빠른 케이스가 흔하다고 합니다.[^3]

LLM 서빙에서는 더 극단적으로, vLLM 서버를 띄우고 warm-up까지 한 뒤 스냅샷을 찍고, cold start 시에는 “복원→wake”로 즉시 서빙하게 만드는 예제가 공개되어 있습니다(심지어 GPU snapshot도 언급).[^4]

또한 Modal은 “HTTP로 오래 살아있는 프로세스”인 `Server` 개념과 autoscaling(타겟 동시성, warm 컨테이너 유지)을 제공합니다.[^5]

### 3) Runpod: “모델 파일/워커 상태를 최대한 재사용”하는 쪽이 강하다
Runpod Serverless는 엔드포인트에 요청이 오면 워커를 띄우고, 없으면 cold start가 발생합니다.[^2]  
2026년 7월 업데이트 기준으로 Runpod은 FlashBoot을 cold start 최적화 레이어로 강조하며, 마케팅 스펙상 “sub-200ms cold starts” 같은 강한 메시지를 내고 있습니다(단, 이는 **활성/조건**에 따라 달라질 수 있으니 그대로 SLO로 박으면 위험).[^6]

실무에서 더 중요한 건 **모델 로딩 비용을 ‘다운로드’와 ‘GPU 적재’로 분리**하는 것입니다. Runpod은 Hugging Face 기반 **Cached models** 기능으로 “모델 다운로드 시간은 과금하지 않고, 호스트에 캐시된 모델을 우선 배치”하는 구조를 제공합니다.[^7]  
추가로 endpoint 설정에서 **Active workers(항상 켜둠)**로 cold start 자체를 제거할 수 있고, FlashBoot, Idle timeout 같은 파라미터로 절충합니다.[^8]

### 4) AWS Lambda: “LLM inference 서버리스”에는 본질적으로 맞지 않는 구간이 있다
AWS Lambda는 cold start를 “실행 환경 초기화”로 정의하고, 예측 가능한 스타트가 필요하면 **Provisioned Concurrency**를 권장합니다.[^9]  
또한 SnapStart가 cold start를 줄이는 옵션으로 계속 확장되고 있으며(문서에 Python 3.12+ 언급 포함), 제약도 명확합니다(EFS 미지원 등).[^10]

하지만 “GPU 상주 + 대형 weight 적재”가 핵심인 LLM 서빙은 Lambda의 전통적인 강점 영역이 아닙니다. Lambda는 **오케스트레이션/전처리/라우팅**에 두고, 실제 토큰 생성은 GPU 서버리스(Modal/Runpod)나 전용 엔드포인트로 넘기는 하이브리드가 더 현실적입니다.

---

## 💻 실전 코드
아래는 “프로덕션에서 바로 써먹는” 기준으로, **API Gateway/Lambda는 얇게 유지**하고, **GPU 서버리스는 Runpod(비동기 job)로**, 그리고 **cold start를 줄이기 위해 Cached model + Active worker 옵션을 전제로 한** 패턴입니다.

### 1단계: Runpod Serverless worker (Python) — vLLM OpenAI 호환을 직접 띄우지 말고 “요청 단위 처리”로 설계
- 이유: serverless worker는 요청당 lifespan/동시성/timeout이 변동이 크므로 “항상 떠있는 HTTP 서버”보다 **handler 기반**이 운영 단순성이 좋습니다.
- 모델 파일은 Runpod Cached model을 쓰면 `/runpod-volume/huggingface-cache/...`에 존재(문서에 경로 규칙 명시).[^7]

```python
# worker/handler.py
import os
import time
from typing import Dict, Any, List

import runpod
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")
DTYPE = torch.bfloat16 if torch.cuda.is_available() else torch.float32

# 프로덕션 포인트:
# 1) 전역에 모델을 로드해 "warm worker"에서는 재사용
# 2) cold start에서 모델 다운로드를 하면 망함 -> Cached model 또는 이미지 bake/볼륨 전략 필수
_tokenizer = None
_model = None

def _lazy_load():
    global _tokenizer, _model
    if _model is not None:
        return

    t0 = time.time()
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=DTYPE,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    _model.eval()

    # Warm-up: 첫 토큰 TTFT 안정화(커널 캐시/메모리 페이지 인)
    dummy = _tokenizer("warm up", return_tensors="pt").to(_model.device)
    with torch.inference_mode():
        _ = _model.generate(**dummy, max_new_tokens=8)

    print(f"loaded {MODEL_ID} in {time.time() - t0:.2f}s")

def _chat(messages: List[Dict[str, str]], max_new_tokens: int = 256) -> str:
    _lazy_load()

    # 현실적인 시나리오: system+user+history 형태
    prompt = ""
    for m in messages:
        prompt += f"{m['role'].upper()}: {m['content']}\n"
    prompt += "ASSISTANT:"

    inputs = _tokenizer(prompt, return_tensors="pt").to(_model.device)
    with torch.inference_mode():
        out = _model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
        )
    text = _tokenizer.decode(out[0], skip_special_tokens=True)
    return text.split("ASSISTANT:", 1)[-1].strip()

def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    예상 입력:
    {
      "input": {
        "request_id": "req_123",
        "messages": [{"role":"system","content":"..."}, ...],
        "max_new_tokens": 256
      }
    }
    """
    inp = job.get("input", {})
    messages = inp["messages"]
    max_new_tokens = int(inp.get("max_new_tokens", 256))

    t0 = time.time()
    answer = _chat(messages, max_new_tokens=max_new_tokens)
    return {
        "request_id": inp.get("request_id"),
        "latency_s": round(time.time() - t0, 3),
        "answer": answer,
    }

runpod.serverless.start({"handler": handler})
```

예상 출력(로그)
- cold start 시: `loaded Qwen/... in 18.42s` 같은 로그가 한 번 찍힘
- warm worker 재사용 시: `latency_s`가 크게 감소

### 2단계: AWS Lambda (TypeScript) — 동기 UX를 “비동기 폴링”으로 바꾸는 얇은 게이트웨이
핵심은 Lambda에서 LLM을 돌리는 게 아니라,
1) `/chat` 요청이 오면 Runpod `/run`으로 job을 제출하고 job_id를 반환  
2) 클라이언트가 `/chat/status?job_id=...`로 폴링하거나 SSE/WebSocket으로 붙여서 상태를 가져오게 하는 것입니다. (Runpod 문서 흐름과 동일)[^2]

```typescript
// lambda/chat.ts (Node.js 20.x 가정)
// npm i undici
import { request } from "undici";

const RUNPOD_ENDPOINT_ID = process.env.RUNPOD_ENDPOINT_ID!;
const RUNPOD_API_KEY = process.env.RUNPOD_API_KEY!;

type ChatBody = {
  request_id: string;
  messages: { role: "system" | "user" | "assistant"; content: string }[];
  max_new_tokens?: number;
};

export const handler = async (event: any) => {
  const body: ChatBody = JSON.parse(event.body ?? "{}");

  const url = `https://api.runpod.ai/v2/${RUNPOD_ENDPOINT_ID}/run`;
  const payload = {
    input: {
      request_id: body.request_id,
      messages: body.messages,
      max_new_tokens: body.max_new_tokens ?? 256,
    },
  };

  const res = await request(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${RUNPOD_API_KEY}`,
    },
    body: JSON.stringify(payload),
  });

  const json = await res.body.json();

  // Runpod async는 job_id를 돌려주고 /status로 조회하는 패턴이 일반적
  return {
    statusCode: 202,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      request_id: body.request_id,
      job_id: json.id ?? json.jobId ?? json.job_id,
    }),
  };
};
```

운영 팁(설정)
- Lambda는 cold start가 문제면 Provisioned Concurrency 또는 SnapStart를 검토하되, 여기서는 Lambda가 하는 일이 작아서 “대부분 문제의 중심이 아님”이 포인트입니다. Lambda cold start 정의/완화 방향은 AWS 문서가 명확합니다.[^9]

### 3단계(확장): Modal로 “초기화 자체를 스냅샷”해서 TTFT를 안정화하는 패턴
Modal은 Memory Snapshot을 “첫 warm-up 이후 상태”로 고정해 다음 부팅에서 복원할 수 있습니다.[^3]  
또 `min_containers/buffer_containers/scaledown_window`로 큐잉 지연도 제어합니다.[^1]

(여기서 핵심은 코드 자체보다 설계입니다)
- **스냅샷 대상**: import + 모델 로드 + vLLM 엔진 준비 + 짧은 warm-up
- **스냅샷 이후**: 요청 처리 루프만 남김
- **warm pool**: 최소 1개 유지(비용 vs SLO 트레이드)

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 적용 가능한 것들)
1) **“다운로드”를 cold start 경로에서 제거**
   - Runpod이라면 Cached model을 적극 사용: 모델은 HF 캐시 경로에 놓이고, 시스템이 캐시된 호스트에 우선 스케줄링하며 다운로드 시간 과금도 줄일 수 있습니다.[^7]  
   - 모델이 HF에 없다면: 이미지 bake vs 네트워크 볼륨 vs 자체 아티팩트 레포(조직 사정에 따라)

2) **“큐잉 지연”과 “초기화 지연”을 분리해서 계측**
   - 플랫폼 메트릭에서 pending/queue time이 큰지, 첫 요청 init이 큰지 분리해야 처방이 달라집니다(Modal 문서가 이 구분을 강조).[^1]

3) **SLO가 있으면 결국 warm capacity를 사야 한다**
   - Runpod: Active workers > 0으로 사실상 cold start 제거 가능(비용 증가).[^8]  
   - Modal: `min_containers`, `buffer_containers`, `scaledown_window`로 warm pool을 비용과 교환.[^11]  
   - AWS Lambda: 예측 가능한 스타트를 원하면 Provisioned Concurrency가 권장 경로.[^9]

### 흔한 함정/안티패턴
- **첫 요청에서만 모델을 다운로드**(S3/HF pull): “가끔 느림”이 아니라 “항상 장애처럼 보이는” 시스템이 됩니다.  
- **서버리스에 거대한 올인원 이미지**: 이미지 pull 자체가 cold start가 되고, 롤링 업데이트 때마다 비용과 시간이 튑니다. (Runpod cached model이 “이미지와 모델 분리”를 장점으로 언급)[^7]
- **동기 API로 강제**: serverless GPU는 “처음 몇 초~몇 분”이 튈 수 있는데, 이를 동기 요청 타임아웃/리트라이가 증폭시키면 비용/부하가 폭발합니다. 비동기 job으로 설계를 바꾸는 게 보통 더 안전합니다.[^2]

### 비용/성능/안정성 트레이드오프(결론만)
- **최저비용(Scale-to-zero)**: cold start 감수 + 비동기 UX + 캐시/스냅샷으로 완화
- **최저지연(항상 빠른 TTFT)**: warm worker/컨테이너 유지(=항상 비용 발생)
- **최고안정(예측 가능)**: warm capacity + 지역/데이터센터 제약 최소화(제약 걸수록 가용 GPU 풀이 줄어드는 경향)

---

## 🚀 마무리
핵심 요약:
- 2026년 8월 기준 서버리스 LLM 배포에서 cold start는 **큐잉(0→1) + 초기화(모델/런타임 준비)** 두 문제이며, 둘을 분리해 설계/계측해야 합니다.[^1]
- **Modal**은 Memory Snapshot(및 vLLM 스냅샷 예제)처럼 “초기화 자체를 제거/단축”하는 접근이 강점입니다.[^3]  
- **Runpod**은 Cached model + FlashBoot + Active workers 조합으로 “모델 다운로드/로딩 비용과 cold start 체감”을 줄이는 실전 옵션이 많습니다.[^7]  
- **AWS Lambda**는 LLM 토큰 생성보다는 “라우팅/오케스트레이션”에 두고, cold start는 Provisioned Concurrency/SnapStart로 관리하는 하이브리드가 현실적입니다.[^9]

도입 판단 기준(실무 체크리스트):
- 동기 UX인가? (Yes면 warm capacity 예산부터 잡기)
- 트래픽이 버스트인가? (Yes면 serverless 적합)
- 모델이 HF에 있는가? (Runpod Cached model로 “다운로드 제거” 가능)[^7]
- “초기화가 무겁다”가 핵심 병목인가? (Yes면 Modal Snapshot류가 강하게 유리)[^3]

다음 학습 추천:
- Modal: cold start 최적화 가이드 + Memory Snapshot + Server autoscaling 파라미터를 한 번에 읽고, “내 앱 초기화 단계를 어디까지 스냅샷에 넣을지”를 설계해보세요.[^1]  
- Runpod: Endpoint 설정(Active workers/Idle timeout/FlashBoot)과 Cached model 경로 규칙을 이해한 뒤, “모델/이미지 분리”로 배포 파이프라인을 재구성해보세요.[^8]

[^1]: <https://modal.com/docs/guide/cold-start>
[^2]: <https://docs.runpod.io/serverless/overview>
[^3]: <https://modal.com/docs/guide/memory-snapshots>
[^4]: <https://modal.com/docs/examples/lfm_snapshot>
[^5]: <https://modal.com/docs/guide/servers>
[^6]: <https://www.runpod.io/product/serverless>
[^7]: <https://docs.runpod.io/serverless/endpoints/model-caching>
[^8]: <https://docs.runpod.io/serverless/endpoints/endpoint-configurations>
[^9]: <https://docs.aws.amazon.com/us_en/lambda/latest/dg/lambda-runtime-environment.html>
[^10]: <https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html>
[^11]: <https://frontend.modal.com/docs/guide/scale>
