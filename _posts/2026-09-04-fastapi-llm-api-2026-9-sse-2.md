---
title: "FastAPI로 “진짜” LLM 스트리밍 API 서버 만들기: SSE, 백프레셔, 끊김/재개까지"
description: "LLM API 서버에서 스트리밍(token-by-token)은 “UX”만의 문제가 아닙니다. TTFT(Time To First Token)를 줄여 사용자가 “응답이 살아있다”는 확신을 얻고, 동시에 서버는 긴 생성 작업을 요청 타임아웃/리버스 프록시 제한 속에서도 안정적으로 전달해야 합…"
date: 2026-09-04 04:08:43 +0900
categories: [Backend, API]
tags: [backend, api]
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
LLM API 서버에서 스트리밍(token-by-token)은 “UX”만의 문제가 아닙니다. **TTFT(Time To First Token)**를 줄여 사용자가 “응답이 살아있다”는 확신을 얻고, 동시에 서버는 긴 생성 작업을 **요청 타임아웃/리버스 프록시 제한** 속에서도 안정적으로 전달해야 합니다. 특히 2026년 기준으로도 많은 팀이 겪는 병목은 “모델 호출”보다 **스트리밍 파이프라인(ASGI/프록시/클라이언트)에서의 버퍼링·끊김·리소스 누수**입니다.

**언제 쓰면 좋은가**
- Chat UI/Agent처럼 **부분 결과를 즉시 보여줘야** 할 때(사용자 이탈 방지)
- 생성 길이가 길거나, tool call/검색 등으로 **응답 시간이 흔들릴 때**
- OpenAI 호환 스트리밍(SSE) 형태로 **클라이언트/SDK 재사용**을 원할 때(vLLM 포함)[^1]

**언제 쓰면 안 되는가**
- 모바일/사내망 등에서 프록시가 강하게 개입해 **장시간 연결 유지가 불안정**한 환경(이때는 “짧은 폴링 + job 상태 조회”가 더 단순)
- 응답이 반드시 **완전한 JSON**이어야 하고(스키마 검증/서명), 중간 청크가 의미 없을 때(스트리밍보다 배치가 운영이 쉬움)
- 요청당 과금/감사 로그가 엄격해 “중간에 끊긴 응답”을 비용/정산 측면에서 처리하기 까다로운 조직

---

## 🔧 핵심 개념
### 1) LLM 스트리밍의 사실상 표준: SSE(text/event-stream)
2026년에도 LLM 스트리밍은 실무에서 **SSE(Server-Sent Events)**가 가장 흔합니다. 브라우저는 `EventSource`로 네이티브 지원하고, 서버는 **단방향(서버→클라이언트) push**를 HTTP 위에서 구현합니다. FastAPI도 SSE 튜토리얼에서 `EventSourceResponse` 패턴을 공식적으로 안내합니다.[^2]

SSE는 “청크드 전송”과 비슷해 보이지만, 핵심 차이는:
- **프레이밍**: `event:` / `data:` 라인 기반 메시지 단위
- **운영 안정성**: keep-alive(ping), 재연결(Last-Event-ID) 같은 관행이 이미 있음
- LLM API(OpenAI 스타일)는 흔히 `stream: true`일 때 `text/event-stream`으로 토큰 이벤트를 보냄(클라이언트가 항상 `Accept` 헤더로 강제하지 않는 케이스도 존재)[^3]

### 2) FastAPI/Starlette 스트리밍의 내부 흐름(중요)
FastAPI는 Starlette 위에서 동작하고, 스트리밍은 결국 **ASGI send 채널로 바이트를 “조금씩” 보내는 것**입니다.

- 여러분이 `async generator`에서 `yield`를 하면  
  Starlette `StreamingResponse`(또는 SSE 구현체)가 그 값을 받아 `http.response.body` 메시지로 전송
- 문제는 여기서 **버퍼링/백프레셔/Disconnect 감지**가 프레임워크·ASGI 서버·프록시 조합에 따라 달라진다는 점입니다.
- 일부 구현은 “그냥 `StreamingResponse` + content-type=text/event-stream”로도 되지만, 실제로는 **필수 헤더, disconnect 처리, 예상치 못한 버퍼링** 같은 운영 이슈가 터집니다. 이런 이유로 SSE 전용 응답(예: sse-starlette 계열)을 권장하는 글들이 늘었습니다.[^4]

또 하나의 실전 포인트:
- 미들웨어 계층에서 StreamingResponse를 잘못 다루면 “No response returned” 같은 이슈가 과거에 있었고, Starlette/FastAPI 버전 이슈로 보고된 바 있습니다. (요지는: 스트리밍은 미들웨어/TaskGroup/anyio 스트림과 얽히면 깨지기 쉬움)[^5]

### 3) “업스트림 LLM 스트림을 그대로 프록시”의 함정
많은 팀이 “우리 서버는 OpenAI/vLLM에서 오는 SSE를 받아 그대로 클라이언트로 relay”를 합니다. 이때 중요한 차이는:

- **업스트림**: SSE를 “받는 쪽”은 네트워크 read를 해야 하고
- **다운스트림**: SSE를 “보내는 쪽”은 ASGI send를 해야 합니다.

둘 사이를 단일 코루틴에서 무식하게 이어붙이면:
- 클라이언트가 느릴 때(모바일/탭 백그라운드), 다운스트림 send가 막혀 업스트림 read가 지연 → **메모리 버퍼/지연 증가**
- 클라이언트 disconnect 시 업스트림 요청을 cancel하지 않으면 → **유령 생성(돈/자원 낭비)**

그래서 실무에서는 anyio의 `create_memory_object_stream()` 같은 **bounded queue**로 “생산자(업스트림) / 소비자(다운스트림)”를 분리해 백프레셔를 명시적으로 설계하는 방식이 자주 쓰입니다.[^6]

---

## 💻 실전 코드
아래 예제는 “우리 FastAPI가 LLM 스트리밍 endpoint를 제공”하는 현실적인 구성을 가정합니다.

- 클라이언트 → 우리 서버: `POST /v1/chat/completions` (OpenAI 스타일)
- 우리 서버 → 업스트림: (1) OpenAI Responses/Chat 스트리밍 또는 (2) 사내 vLLM OpenAI-compatible server
- 우리 서버는 **SSE로 토큰 이벤트를 전달**하고, 동시에 **최종 결과를 저장**(DB 부분은 자리만 마련)

### 0) 의존성/실행
```bash
python -m venv .venv
source .venv/bin/activate

pip install fastapi uvicorn httpx sse-starlette anyio pydantic
# 운영에서는 uvicorn worker/timeout, 프록시 버퍼링 옵션도 함께 점검하세요.
```

### 1) 서버: 업스트림 SSE를 “bounded relay”로 전달 + disconnect 시 cancel
```python
from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator, Optional

import anyio
import httpx
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

app = FastAPI()

# ---- OpenAI 스타일 입력(간소화) ----
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionsRequest(BaseModel):
    model: str = Field(..., description="upstream model id")
    messages: list[ChatMessage]
    stream: bool = True
    temperature: float = 0.7
    max_tokens: Optional[int] = 512

UPSTREAM_BASE_URL = os.getenv("UPSTREAM_BASE_URL", "http://localhost:8001")
UPSTREAM_API_KEY = os.getenv("UPSTREAM_API_KEY", "dummy")

def sse_pack(data: dict[str, Any], event: str = "message") -> dict[str, str]:
    # sse-starlette는 {"event": "...", "data": "..."} dict를 yield하면 SSE로 프레이밍합니다.
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}

async def openai_compatible_upstream_stream(payload: dict[str, Any]) -> AsyncIterator[str]:
    """
    업스트림이 OpenAI-compatible SSE로 보내는 raw lines("data: {...}")를 그대로 읽는다.
    vLLM도 OpenAI-compatible server를 제공하며 streaming SSE를 지원한다.[^7]
    """
    url = f"{UPSTREAM_BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {UPSTREAM_API_KEY}"}

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as r:
            if r.status_code >= 400:
                text = await r.aread()
                raise HTTPException(status_code=502, detail=f"Upstream error: {r.status_code} {text[:200]!r}")

            async for line in r.aiter_lines():
                # SSE는 빈 줄/코멘트가 있을 수 있음
                if not line:
                    continue
                yield line

async def relay_sse(request: Request, payload: dict[str, Any]) -> AsyncIterator[dict[str, str]]:
    """
    핵심:
    - producer: 업스트림에서 SSE line을 읽어 queue에 넣음
    - consumer: queue에서 꺼내 SSE로 클라이언트에 전달
    - queue는 bounded로 두어 백프레셔를 강제(느린 클라이언트가 메모리 먹는 것 방지)
    - disconnect 시 producer cancel
    """
    send, recv = anyio.create_memory_object_stream[str](max_buffer_size=50)  # bounded queue[^6]
    start = time.perf_counter()

    async def producer():
        try:
            async for line in openai_compatible_upstream_stream(payload):
                # OpenAI/vLLM 스트림은 보통 "data: {...}" 또는 "data: [DONE]"
                await send.send(line)
        finally:
            await send.aclose()

    async with anyio.create_task_group() as tg:
        tg.start_soon(producer)

        # 첫 토큰 전까지의 시간(TTFT) 측정용 메타 이벤트
        yield sse_pack({"type": "meta", "ttft_ms": None}, event="meta")

        first_token_sent = False
        try:
            async for line in recv:
                # disconnect 감지 (FastAPI/Starlette는 request.is_disconnected 제공)
                if await request.is_disconnected():
                    tg.cancel_scope.cancel()
                    break

                if line.startswith("data:"):
                    data = line[len("data:"):].strip()
                else:
                    # event:, id: 같은 라인도 들어올 수 있어 보수적으로 처리
                    continue

                if data == "[DONE]":
                    yield sse_pack({"type": "done"})
                    break

                # 여기서 업스트림 JSON을 파싱해서 "우리 포맷"으로 정규화 가능
                # (예: choices[0].delta.content → token)
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    # 업스트림 이상/부분라인이면 버림 또는 로깅
                    continue

                if not first_token_sent:
                    ttft_ms = int((time.perf_counter() - start) * 1000)
                    yield sse_pack({"type": "meta", "ttft_ms": ttft_ms}, event="meta")
                    first_token_sent = True

                yield sse_pack({"type": "chunk", "upstream": obj})
        finally:
            tg.cancel_scope.cancel()

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionsRequest, request: Request):
    if not req.stream:
        raise HTTPException(status_code=400, detail="This server only supports stream=true for now")

    payload = req.model_dump()
    # OpenAI-compatible 서버는 stream=true일 때 text/event-stream을 준다(관행).[^3]

    # SSE 응답: ping/keep-alive를 넣어 프록시가 끊지 않게 하는 게 중요[^2]
    return EventSourceResponse(
        relay_sse(request, payload),
        ping=15,  # 15초마다 keep-alive (환경에 따라 조정)
    )
```

**예상 출력(클라이언트가 받는 SSE event)**
- `event: meta` `{ "type":"meta","ttft_ms":123 }`
- `event: message` `{ "type":"chunk","upstream":{...} }`
- 마지막에 `{ "type":"done" }`

### 2) (선택) 업스트림을 OpenAI가 아니라 vLLM로 바꾸기
vLLM은 OpenAI-compatible server를 제공하며(Completions/Chat 등), 스트리밍도 지원합니다. 이 경우 위 서버 코드는 **UPSTREAM_BASE_URL만** 바꿔도 그대로 동작하는 구성이 가능합니다.[^7]

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **bounded queue로 백프레셔를 설계**
- “업스트림 read”와 “다운스트림 send”를 분리하지 않으면 느린 클라이언트가 시스템 전체를 끌어내립니다.
- anyio `create_memory_object_stream(max_buffer_size=...)`로 메모리 상한을 명시하세요.[^6]

2) **disconnect 시 upstream cancel**
- LLM 생성은 비싸고 길어집니다. 클라이언트가 나갔는데 계속 생성하면 GPU/비용이 증발합니다.
- SSE/StreamingResponse에서는 disconnect가 ASGI receive 채널로 들어오며, 구현체에 따라 감지/처리가 다릅니다(따라서 `request.is_disconnected()` 같은 경로를 실제로 테스트).[^4]

3) **keep-alive(ping)와 프록시 버퍼링 설정을 함께 다루기**
- SSE는 중간 프록시가 “한동안 데이터 없음”으로 연결을 끊는 일이 많습니다. FastAPI SSE 예제도 ping을 권장합니다.[^2]
- Nginx를 쓴다면 `proxy_buffering off;` 류의 설정 검토가 필요합니다(버퍼링되면 “스트리밍인데 한 번에 몰아서 도착” 문제가 생김).

### 흔한 함정/안티패턴
- **`StreamingResponse(text/event-stream)`로만 끝내기**: 헤더/캐시/disconnect/버퍼링 이슈가 운영에서 터질 확률이 큽니다. SSE 전용 응답(예: EventSourceResponse)을 고려할 이유가 충분합니다.[^4]
- **미들웨어에서 스트리밍을 가로채기**: 과거 Starlette/anyio 조합에서 스트리밍이 미들웨어 때문에 깨진 사례들이 공유되었습니다. 관측/인증을 미들웨어에서 한다면 “스트리밍 호환”인지 회귀 테스트가 필요합니다.[^5]
- **재개(resume) 없는 SSE**: 탭 새로고침/모바일 네트워크 전환으로 끊기면 대화 UX가 무너집니다. 2026년에도 이 문제를 다루는 “resumable SSE” 논의가 활발합니다(Last-Event-ID 기반).[^8]

### 비용/성능/안정성 트레이드오프
- **SSE vs WebSocket**: WebSocket은 양방향이지만 프록시/인증/스케일링이 더 복잡해질 수 있습니다. 단방향 스트리밍만 필요하면 SSE가 운영 난이도가 낮은 경우가 많습니다.[^9]
- **streaming 저장(로그/감사)**: 청크를 DB에 모두 저장하면 I/O가 병목이 됩니다. 보통은 (a) 토큰 단위는 메모리 버퍼에 모으고 (b) 주기적으로 flush하거나 (c) 최종본만 저장하는 전략이 필요합니다.
- **모델 서버 선택(OpenAI vs vLLM)**: OpenAI 호환 API로 감싸면 클라이언트/SDK를 재사용할 수 있지만, “호환”이 곧 “완전 동일”은 아닙니다(지원 파라미터/이벤트 포맷 차이). vLLM은 OpenAI-compatible server를 제공하되 확장 파라미터도 존재합니다.[^7]

---

## 🚀 마무리
정리하면, 2026년 9월 기준 FastAPI로 LLM 스트리밍 서버를 만들 때 핵심은 “SSE로 토큰을 흘린다”가 아니라:

- **SSE 프레이밍(EventSourceResponse)**로 프록시/클라이언트 친화적으로 만들고[^2]  
- **producer/consumer 분리 + bounded queue**로 백프레셔를 설계하고[^6]  
- **disconnect 시 upstream cancel**로 비용을 막는 것

도입 판단 기준은 간단합니다.
- “TTFT가 UX/전환율에 중요”하고 “응답 시간이 길거나 변동이 큰” 서비스면 스트리밍은 거의 필수
- 반대로 “완전한 JSON 결과”가 더 중요하거나, 네트워크가 불안정해 재개 전략까지 감당하기 어렵다면 배치 + job 조회가 더 나을 수 있습니다.

다음 학습 추천:
- FastAPI SSE 공식 문서(keep-alive/ping 포함)[^2]  
- OpenAI 스트리밍 이벤트 구조(Responses streaming)[^10]  
- vLLM OpenAI-compatible server 문서(사내 호스팅/호환 계층)[^7]

[^1]: <https://github.com/vllm-project/vllm/blob/main/docs/serving/online_serving/openai_compatible_server.md>
[^2]: <https://fastapi.tiangolo.com/tutorial/server-sent-events/>
[^3]: <https://github.com/fastify/sse>
[^4]: <https://www.server-sent-events.com/backend-stream-generation-connection-management/python-fastapi-sse-implementation-guide/streaming-sse-responses-with-fastapi-and-sse-starlette/>
[^5]: <https://stackoverflow.com/questions/71222144/runtimeerror-no-response-returned-in-fastapi-when-refresh-request>
[^6]: <https://anyio.readthedocs.io/en/stable/streams.html>
[^7]: <https://docs.vllm.ai/en/v0.21.0/serving/openai_compatible_server/>
[^8]: <https://www.reddit.com/r/FastAPI/comments/1vgz7sz/fastapiresumablestream_sse_that_survives_a_page/>
[^9]: <https://pythondatabench.com/article/fastapi-streaming-sse-websockets-ndjson-llm-2026>
[^10]: <https://platform.openai.com/docs/api-reference/responses-streaming/response/refusal?lang=python>
