---
title: "FastAPI로 LLM API “진짜” 스트리밍 서버 만들기: 2026년 7월 기준 SSE 파이프라인 심층 분석"
date: 2026-07-04 03:49:35 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-07]
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
LLM API 서버를 만들다 보면 “응답을 빨리 시작해서(=TTFT, Time To First Token) 사용자가 기다리는 느낌을 줄이고 싶다”가 거의 필수 요구가 됩니다. 문제는 **모델이 토큰을 생성하는 속도**가 아니라, 그 토큰이 **내 서버 → 프록시/로드밸런서 → 브라우저/앱**까지 *끊김 없이* 전달되는 “스트리밍 파이프라인”을 구성하는 게 더 어렵다는 점입니다. 특히 2026년 기준 OpenAI의 Responses API는 **SSE(Server-Sent Events) 기반의 typed event 스트리밍**을 제공하므로, FastAPI도 그에 맞춰 “이벤트 릴레이” 서버를 구성하는 패턴이 실무에서 많이 쓰입니다. ([platform.openai.com](https://platform.openai.com/docs/api-reference/responses-streaming/response/code_interpreter_call_code/delta?api-mode=responses&utm_source=openai))

### 언제 쓰면 좋은가
- 웹/앱에서 ChatGPT 같은 UX(토큰 단위로 출력)를 제공해야 할 때
- 긴 응답/추론이 많은 요청에서 **perceived latency**를 줄이고 싶을 때(“50~80% 체감 개선” 같은 이야기가 나오는 이유가 여기) ([tokenmix.ai](https://tokenmix.ai/blog/how-to-stream-ai-api-response?utm_source=openai))
- 서버가 “LLM 공급자(OpenAI/자체모델/다중벤더)” 앞단에서 **표준화된 스트리밍 인터페이스**를 제공해야 할 때

### 언제 쓰면 안 되는가
- 결과를 **원자적(atomic)** 으로 처리해야 하는 경우(예: 결제, 승인, DB 트랜잭션 결과 등)
- 클라이언트가 SSE를 제대로 소비할 수 없거나(사내 SDK 제약), 중간 프록시가 **버퍼링으로 스트리밍을 망가뜨리는** 환경을 통제할 수 없을 때(이 경우 WebSocket이나 “폴링 + 작업 큐”가 더 낫습니다) ([networkspy.app](https://networkspy.app/blog/debugging-broken-openai-streaming-responses?utm_source=openai))
- 스트리밍 중간에 tool call / JSON structured output을 섞어 처리해야 하는데, 클라이언트가 이벤트 타입 분기 처리를 할 역량이 없을 때(오히려 UX/오류가 복잡해짐)

---

## 🔧 핵심 개념
### 1) “FastAPI 스트리밍”의 실체: ASGI send 루프 + iterator
FastAPI의 `StreamingResponse`는 내부적으로 **ASGI 스펙에 맞게 `response.start`를 먼저 보내고, 이후 바디를 chunk 단위로 반복(iterate)하며 `send`** 합니다. 즉, 핵심은 “리스트를 만들어 한 번에 반환”이 아니라 **(async) generator** 를 통해 *흐름*을 만드는 것입니다. ([starlette.dev](https://starlette.dev/responses/?utm_source=openai))

여기서 중요한 구조는 다음입니다.

- **업스트림(OpenAI Responses streaming)**: SSE 이벤트가 “줄줄이” 옴  
- **내 서버(FastAPI)**: 업스트림 이벤트를 읽어서, 다운스트림(브라우저/앱)로 그대로 SSE로 흘려보냄
- **다운스트림(브라우저)**: `EventSource` 또는 fetch-stream으로 수신/렌더링

### 2) 2026년 OpenAI Responses API 스트리밍: “typed events”로 설계하기
OpenAI Responses API 스트리밍은 단순히 텍스트 조각만 오는 게 아니라 `response.created`, `response.output_text.delta`, `response.function_call_arguments.delta`, `response.completed` 등 **타입이 있는 이벤트**들이 SSE로 흘러옵니다. 따라서 “텍스트 누적”만이 아니라 **이벤트 라우팅/정규화 레이어**를 서버에 두는 게 실무적으로 유리합니다. ([platform.openai.com](https://platform.openai.com/docs/api-reference/responses-streaming/response/code_interpreter_call_code/delta?api-mode=responses&utm_source=openai))

이게 중요한 이유:
- tool call 인자(JSON)가 delta로 쪼개져 올 수 있음
- “partial JSON”을 클라이언트가 직접 파싱하게 만들면 장애 포인트가 늘어남
- 이벤트 기반으로 로깅/메트릭(TTFT, tokens/sec, cancel rate)을 넣기 쉬움

### 3) “진짜 스트리밍”을 깨뜨리는 2대 원인: 버퍼링과 취소 전파
- **버퍼링**: 중간 프록시/클라이언트 라이브러리가 SSE를 “끝까지 모아” 한 번에 반환하면 스트리밍이 무의미해집니다(노코드/워크플로우 도구에서도 흔함). ([automatelab.tech](https://automatelab.tech/blog/no-code/n8n-openai-streaming/?utm_source=openai))
- **취소(cancellation) 전파**: 사용자가 탭을 닫거나 네트워크가 끊기면 서버는 빨리 멈춰야 비용/리소스를 아낍니다. ASGI 서버는 보통 `http.disconnect`를 발생시키고, Starlette/FastAPI는 generator 반복이 중단되며 task cancellation이 걸립니다(정리 코드가 없으면 누수/좀비 작업이 생김). ([stackoverflow.com](https://stackoverflow.com/questions/78233692/fastapi-finish-streaming-function-in-streamingresponse-even-if-client-closed-the?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “우리 팀이 실제로 운영할 법한” 패턴을 목표로 했습니다.

- 엔드포인트: `POST /v1/chat/stream`
- 동작: OpenAI Responses API를 `stream=true`로 호출하고, **업스트림 SSE 이벤트를 다운스트림 SSE로 릴레이**
- 추가:  
  - TTFT 측정(첫 delta까지 시간)  
  - 클라이언트 disconnect 시 업스트림 요청 취소  
  - Nginx 등에서 스트리밍이 깨지지 않도록 헤더 세팅(가능한 범위)

### 1) 의존성 / 실행
```bash
python -m venv .venv
source .venv/bin/activate

pip install fastapi uvicorn httpx python-dotenv
export OPENAI_API_KEY="YOUR_KEY"
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 2) FastAPI: 업스트림(OpenAI) SSE → 다운스트림 SSE 릴레이
```python
# app.py
import os
import json
import time
import asyncio
from typing import AsyncIterator, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

app = FastAPI()


def sse(data: dict, event: Optional[str] = None) -> bytes:
    """
    Downstream SSE framing.
    We keep it simple: send only `data:` lines + blank line.
    (You can add `event:` for client-side routing if desired.)
    """
    payload = json.dumps(data, ensure_ascii=False)
    if event:
        return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
    return f"data: {payload}\n\n".encode("utf-8")


async def relay_openai_sse(request: Request, user_input: str) -> AsyncIterator[bytes]:
    """
    Core streaming pipeline:
    - Call OpenAI Responses API with stream=true (SSE).
    - Parse each SSE 'data:' line into JSON event.
    - Forward selected events downstream quickly.
    - Stop immediately on client disconnect.
    """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "gpt-4.1-mini",  # 예시. 실제 운영 모델은 팀 정책에 맞게.
        "stream": True,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_input}],
            }
        ],
    }

    t0 = time.perf_counter()
    first_delta_sent = False

    # httpx AsyncClient streaming
    async with httpx.AsyncClient(timeout=None) as client:
        try:
            async with client.stream("POST", OPENAI_RESPONSES_URL, headers=headers, json=body) as resp:
                resp.raise_for_status()

                # OpenAI streaming is SSE. We'll read line-by-line.
                async for line in resp.aiter_lines():
                    # Client disconnect check (critical for cost control)
                    if await request.is_disconnected():
                        # Letting context exit will close upstream connection.
                        break

                    if not line:
                        continue

                    # SSE format: lines like "data: {...}" or maybe other fields.
                    if not line.startswith("data:"):
                        continue

                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        yield sse({"type": "done"})
                        break

                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        # Forward parse error as a diagnostic event (optional)
                        yield sse({"type": "relay_error", "message": "json_decode_error", "raw": data_str})
                        continue

                    etype = event.get("type")

                    # TTFT measurement: first output_text delta
                    if (not first_delta_sent) and etype == "response.output_text.delta":
                        first_delta_sent = True
                        ttft_ms = int((time.perf_counter() - t0) * 1000)
                        yield sse({"type": "metrics.ttft", "ttft_ms": ttft_ms})

                    # Practical policy:
                    # - forward text deltas
                    # - forward tool call deltas (if you want client to show tool progress)
                    # - forward completion/error
                    if etype in (
                        "response.created",
                        "response.output_text.delta",
                        "response.function_call_arguments.delta",
                        "response.completed",
                        "error",
                    ):
                        yield sse(event)
        except httpx.HTTPError as e:
            yield sse({"type": "upstream_http_error", "message": str(e)})


@app.post("/v1/chat/stream")
async def chat_stream(req: Request):
    payload = await req.json()
    user_input = payload.get("input")
    if not user_input:
        return StreamingResponse(
            iter([sse({"type": "error", "message": "missing input"})]),
            media_type="text/event-stream",
        )

    headers = {
        # Prevent proxy buffering when possible (works depending on infra)
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        # Nginx: disable response buffering for SSE
        "X-Accel-Buffering": "no",
    }

    return StreamingResponse(
        relay_openai_sse(req, user_input),
        media_type="text/event-stream",
        headers=headers,
    )
```

### 3) 예상 출력(다운스트림 SSE)
클라이언트는 이런 식으로 받습니다(예: 브라우저 콘솔에서):
- `response.created` 이벤트
- `metrics.ttft` 이벤트(서버가 삽입)
- 여러 개의 `response.output_text.delta`
- 마지막에 `response.completed` 또는 `done`

OpenAI Responses의 스트리밍 이벤트 타입 자체는 공식 레퍼런스에 정의되어 있고, “typed events”로 흘러온다는 점이 핵심입니다. ([platform.openai.com](https://platform.openai.com/docs/api-reference/responses-streaming/response/code_interpreter_call_code/delta?api-mode=responses&utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “disconnect 되면 즉시 중단”을 비용 설계로 넣어라
스트리밍 UX에서는 사용자가 중간에 닫는 비율이 생각보다 큽니다. 그때 업스트림을 계속 돌리면 **토큰 비용 + 워커 점유 + 로그 폭발**이 생깁니다.  
ASGI에서는 클라이언트가 끊기면 `http.disconnect`가 발생하고, Starlette/FastAPI가 반복을 중단/취소하는 흐름이 일반적이지만(상황에 따라 다름) **명시적으로 `request.is_disconnected()` 체크를 넣는 패턴이 방어적**입니다. ([stackoverflow.com](https://stackoverflow.com/questions/78233692/fastapi-finish-streaming-function-in-streamingresponse-even-if-client-closed-the?utm_source=openai))

### Best Practice 2) 이벤트를 “텍스트만” 흘리지 말고, 최소한의 정규화를 해라
OpenAI Responses API는 text delta 외에도 다양한 이벤트가 옵니다. ([platform.openai.com](https://platform.openai.com/docs/api-reference/responses-streaming/response/code_interpreter_call_code/delta?api-mode=responses&utm_source=openai))  
추천 전략:
- 서버 내부 표준 이벤트 스키마를 정의(예: `type`, `ts`, `stream_id`, `payload`)
- 공급자별(OpenAI/Anthropic/자체) 이벤트를 **서버에서 normalize** 해서 프론트는 하나만 처리

이게 있어야 “벤더 교체/멀티벤더”가 현실이 됩니다(프론트가 벤더 SSE 포맷에 종속되면 나중에 거의 못 바꿉니다).

### Best Practice 3) “버퍼링 방지”는 코드가 아니라 인프라까지 포함이다
코드에서 SSE를 잘 만들어도, 중간 레이어가 모아서 보내면 끝입니다. 실제로 “스트리밍인데 한 번에 다 옴” 이슈는 너무 흔합니다. ([automatelab.tech](https://automatelab.tech/blog/no-code/n8n-openai-streaming/?utm_source=openai))  
체크리스트:
- Nginx: buffering off, gzip off(SSE에서 압축/버퍼링이 문제를 만들 수 있음)
- CDN/Ingress: streaming 지원 여부 확인
- 클라이언트: SSE 파서가 chunk를 바로 소비하는지 확인(일부 HTTP 클라이언트는 내부 버퍼링)

### 흔한 함정 1) generator 안에서 “큰 문자열 누적” 후 yield
스트리밍의 목표는 “최대한 빨리 작은 덩어리로 보내기”인데, 서버에서 누적 후 내보내면 TTFT가 다시 늘어납니다.  
- UI는 “첫 토큰이 빨리 보이느냐”가 승부처입니다.
- 대신 너무 작은 chunk는 syscall/flush 오버헤드가 늘 수 있어 “적당한 단위”가 필요합니다(대개 공급자 delta 그대로 릴레이가 무난).

### 흔한 함정 2) upstream SDK/라이브러리 스트리밍 버그/이슈를 무시
2026년에도 특정 SDK/환경에서 Responses streaming 이슈가 실제로 보고됩니다(예: OpenAI status에 “Java SDK + streaming” 이슈가 올라왔던 적). 운영이라면 “우리 스택에서 재현 가능한가”를 사전에 검증해야 합니다. ([status.openai.com](https://status.openai.com/incidents/01KPBWZ18HR2G685X2XMZD78EP?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **SSE(HTTP)**: 단방향이라 단순하고, 브라우저 친화적. 하지만 양방향 제어(클라이언트 → 서버로의 지속 제어)가 필요하면 별도 채널이 필요.
- **WebSocket**: 양방향/제어는 강점. 다만 프록시/보안/관측/스케일링에서 운영 난이도가 올라갈 수 있음.
- **HTTP/2**: 스트리밍 자체는 HTTP/1.1에서도 가능하지만, 인프라/서버 조합에 따라 체감 차이가 나거나 특정 “스트리밍 의미”가 달라지는 경우가 있어(특히 bidirectional을 기대하는 경우) 서버 선택과 배포 구성이 중요합니다. ([uvicorn.org](https://www.uvicorn.org/?utm_source=openai))

---

## 🚀 마무리
핵심은 “FastAPI에서 StreamingResponse를 쓴다”가 아니라, **업스트림(OpenAI Responses typed SSE) → 내 서버(취소/정규화/관측) → 다운스트림(버퍼링 없는 전달)** 이 3단 파이프라인을 *끝까지* 설계하는 것입니다. ([platform.openai.com](https://platform.openai.com/docs/api-reference/responses-streaming/response/code_interpreter_call_code/delta?api-mode=responses&utm_source=openai))

도입 판단 기준:
- 스트리밍 UX가 제품 KPI(TTFT, 이탈률)에 영향을 주는가?
- 인프라(ingress/proxy/CDN)에서 **SSE 버퍼링을 통제**할 수 있는가?
- 이벤트 정규화/관측(메트릭, 취소율, 오류 이벤트)을 운영 레벨로 넣을 팀 역량이 있는가?

다음 학습 추천:
- OpenAI Responses API streaming event 타입을 기준으로 “우리 제품의 표준 이벤트 스키마” 정의하기 ([platform.openai.com](https://platform.openai.com/docs/api-reference/responses-streaming/response/code_interpreter_call_code/delta?api-mode=responses&utm_source=openai))
- 프록시/로드밸런서 환경에서 SSE가 끊기거나 뭉치는 케이스를 재현하고, 헤더/버퍼링 옵션을 체계적으로 검증하기 ([networkspy.app](https://networkspy.app/blog/debugging-broken-openai-streaming-responses?utm_source=openai))
- 멀티벤더 스트리밍을 염두에 둔다면, 서버에서 normalize 하는 계층을 먼저 만들기(나중에 붙이면 더 어렵습니다)

원하시면, 위 예제를 확장해서 (1) tool call 결과를 서버에서 실행 후 다시 스트리밍에 섞기, (2) structured output(JSON schema) 안전 스트리밍, (3) Redis로 스트림 세션 상태/재연(replay)까지 포함한 “운영형” 아키텍처로도 이어서 작성해드릴게요.