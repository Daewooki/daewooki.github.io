---
title: "FastAPI로 LLM API 서버를 “진짜 스트리밍”으로 만들기: SSE/백프레셔/취소까지 (2026년 5월 기준)"
date: 2026-05-16 03:49:16 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-05]
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
LLM API 서버를 운영하다 보면 “응답이 느리다”는 불만의 대부분은 **모델이 느려서가 아니라, 사용자가 첫 토큰을 받기까지의 체감 지연**에서 옵니다. 특히 Chat UI/Agent UI에서는 **1~2초 내 첫 글자**가 나오느냐가 UX를 갈라요. 이때 가장 현실적인 해법이 **HTTP 기반 스트리밍**(대개 SSE)입니다. FastAPI는 Starlette 기반이라 스트리밍이 자연스럽고, 2026년 현재 FastAPI 공식 문서도 **SSE를 AI chat streaming의 대표 케이스**로 명시합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))

언제 쓰면 좋은가
- 웹/모바일에서 “토큰이 생성되는 대로” 점진 표시(typing 효과), 진행 상황(progress), 로그 tail
- LLM 호출을 **프록시**하거나, 여러 upstream을 합쳐 **하나의 스트림**으로 내보내야 할 때
- “결과가 완성될 때까지 기다리면 타임아웃/사용자 이탈”이 발생하는 API

언제 쓰면 안 되는가
- 클라이언트가 SSE를 제대로 처리하지 못하거나(구형 기업망/프록시), 중간 프록시가 장시간 연결을 자주 끊는 환경
- 서버→클라이언트 단방향이 아니라 **양방향** 상호작용이 본질(그때는 WebSocket이 맞음)
- “완성된 JSON 한 방”이 필요한 배치/백오피스(스트리밍은 오히려 복잡도만 증가)

---

## 🔧 핵심 개념
### 1) SSE(Server-Sent Events) vs 일반 StreamingResponse
FastAPI에서 “스트리밍”은 크게 두 층입니다.

- **ASGI 레벨 스트리밍**: 서버가 `http.response.body`를 여러 번 보내며 chunk를 흘려보냄. Uvicorn/ASGI 스펙 상 가능한 구조입니다. ([uvicorn.dev](https://uvicorn.dev/concepts/asgi/?utm_source=openai))  
- **프로토콜 레벨 스트리밍**: 그 chunk의 포맷을 무엇으로 할지(SSE, JSON Lines, raw bytes 등)

SSE는 텍스트 기반으로 `data: ...\n\n` 프레임을 반복 전송합니다. 브라우저/프록시 친화적이고, “이벤트 단위”로 파싱이 쉽습니다. FastAPI는 공식적으로 `EventSourceResponse`를 사용해 SSE 엔드포인트를 구성하는 방식을 안내합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))

### 2) 내부 흐름(요청 1개가 서버에서 어떻게 흐르는가)
LLM 스트리밍 서버는 보통 아래 파이프라인입니다.

1. Client → FastAPI `/v1/chat/stream` 요청
2. FastAPI 핸들러가 **async generator**를 만들고,
3. generator는 upstream(OpenAI/자체 모델/게이트웨이)에서 토큰/이벤트를 받아
4. SSE 프레임으로 변환해서 `yield`
5. ASGI 서버(Uvicorn)가 chunk를 소켓에 flush
6. 클라이언트는 이벤트를 수신하며 UI를 업데이트

여기서 중요한 건 “yield를 하면 무조건 바로 전송”이 아니라는 점입니다. Uvicorn은 **write buffer high-water mark**를 넘으면 drain될 때까지 `send`를 지연시켜 **백프레셔(backpressure)** 를 걸어줍니다. 즉, 클라이언트가 느리면 서버도 무한히 버퍼에 쌓지 않도록 제동이 걸립니다. ([uvicorn.org](https://www.uvicorn.org/server-behavior/?utm_source=openai))  
이 특성 때문에 “토큰을 너무 잘게, 너무 자주” 보내면 오히려 컨텍스트 스위칭/헤더 처리로 손해가 나고, 느린 클라이언트가 전체 워커를 오래 점유할 수 있습니다.

### 3) “업스트림 SSE를 다운스트림 SSE로 프록시”할 때의 차이점
많은 팀이 하는 실수: upstream이 이미 SSE인데, FastAPI에서 `await response.text()`로 다 읽어버린 뒤 다시 스트리밍한다고 생각함 → **스트리밍이 아니라 배치 전송**이 됩니다.

httpx에서는 반드시 **stream 모드**로 열고(`AsyncClient.stream(...)`) `aiter_bytes/aiter_lines`로 흘려받아야 “진짜 파이프”가 됩니다. ([python-httpx.org](https://www.python-httpx.org/async/?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “LLM 제공자(OpenAI 호환 SSE 스트림)를 호출해서, 우리 API에서 SSE로 그대로 내보내되” 실무에서 필요한 요소를 포함합니다.

- 인증/요청 스키마(pydantic)
- upstream 스트림 프록시(백프레셔는 ASGI/httpx가 협력)
- client disconnect 시 취소 전파(리소스 누수 방지)
- SSE keep-alive ping(프록시 타임아웃 방지: FastAPI 문서 권장) ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))
- 운영 시 유효한 타임아웃/커넥션 풀

### 0) 의존성/실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn httpx sse-starlette pydantic
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 1) 서버 코드 (SSE 스트리밍 프록시)
```python
# app.py
import os
import json
import asyncio
from typing import AsyncIterator, Optional

import httpx
from fastapi import FastAPI, Request, Header, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse


app = FastAPI()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatStreamRequest(BaseModel):
    model: str = Field(default="gpt-5.2")
    messages: list[ChatMessage]
    temperature: float = 0.2
    request_id: Optional[str] = None


def _sse(data: dict, event: str = "message") -> dict:
    # sse-starlette의 EventSourceResponse는 dict를 yield하면 SSE로 포맷합니다.
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


@app.post("/v1/chat/stream")
async def chat_stream(
    request: Request,
    payload: ChatStreamRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    - Downstream: SSE
    - Upstream: OpenAI-compatible SSE endpoint (예: /v1/responses stream=true)
    """
    # 1) 우리 서비스 인증(예시)
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    # 2) Upstream 설정 (OpenAI 호환 게이트웨이를 붙이는 형태)
    upstream_base = os.environ.get("UPSTREAM_BASE_URL", "https://api.openai.com")
    upstream_key = os.environ.get("UPSTREAM_API_KEY", os.environ.get("OPENAI_API_KEY"))
    if not upstream_key:
        raise HTTPException(status_code=500, detail="Missing UPSTREAM_API_KEY/OPENAI_API_KEY")

    upstream_url = f"{upstream_base}/v1/responses"

    # 운영 포인트: 클라이언트/요청마다 AsyncClient를 만들지 말고(오버헤드 큼),
    # 앱 수명주기에서 재사용하는 게 보통 더 낫습니다. 여기선 예제 단순화를 위해 요청 스코프.
    timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)

    async def event_gen() -> AsyncIterator[dict]:
        # (A) 프록시 타임아웃 방지용 ping: 15s 권장(공식 문서) ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))
        last_sent = asyncio.get_event_loop().time()

        headers = {
            "Authorization": f"Bearer {upstream_key}",
            "Content-Type": "application/json",
        }

        # OpenAI Responses API 스타일(개념): stream=True면 SSE 이벤트가 내려옴 ([platform.openai.com](https://platform.openai.com/docs/api-reference/responses-streaming/response?lang=python&utm_source=openai))
        upstream_body = {
            "model": payload.model,
            "input": [{"role": m.role, "content": m.content} for m in payload.messages],
            "temperature": payload.temperature,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=timeout, limits=limits, http2=True) as client:
            # 핵심: stream 컨텍스트에서 aiter_*로 읽어야 진짜 스트리밍 ([python-httpx.org](https://www.python-httpx.org/async/?utm_source=openai))
            async with client.stream("POST", upstream_url, headers=headers, json=upstream_body) as resp:
                if resp.status_code >= 400:
                    # 에러도 SSE로 흘려보내고 종료
                    detail = await resp.aread()
                    yield _sse({"type": "error", "status": resp.status_code, "detail": detail.decode("utf-8", "ignore")}, event="error")
                    return

                # (B) upstream SSE를 라인 단위로 받아 그대로 중계(필요 시 변환)
                async for line in resp.aiter_lines():
                    # 클라이언트가 끊었는지 확인 (끊겼으면 빨리 중단)
                    if await request.is_disconnected():
                        return

                    now = asyncio.get_event_loop().time()
                    if now - last_sent > 15:
                        yield {"comment": "ping"}  # SSE comment frame
                        last_sent = now

                    if not line:
                        continue
                    # OpenAI 계열 SSE는 "data: {...}" 또는 "data: [DONE]" 형태가 흔함
                    if line.startswith("data:"):
                        data = line.removeprefix("data:").strip()
                        # 종료 프레임 처리
                        if data == "[DONE]":
                            yield _sse({"type": "done"})
                            return
                        # 중계(여기서 우리 내부 스키마로 normalize 해도 됨)
                        yield _sse({"type": "upstream_event", "data": data})

        # upstream이 조용히 끊겼는데 done을 못 받는 경우 대비
        yield _sse({"type": "done", "reason": "upstream_closed"})

    # response_class로 SSE를 명시하는 것이 문서/생태계 기준선 ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))
    return EventSourceResponse(event_gen())
```

### 2) 예상 출력(클라이언트 관점)
curl로 보면 대략 이런 식으로 옵니다(개념):

- `event: message`
- `data: {"type":"upstream_event","data":"{...원본 SSE payload...}"}`

브라우저라면 `fetch`로 스트림을 읽거나(요즘은 이쪽이 일반적), 단순 이벤트면 `EventSource`도 가능(단, 헤더 인증 제약 때문에 쿠키 기반 인증이 편함).

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **프레임 단위를 “토큰 1개”로 고정하지 말고 버퍼링 전략을 둬라**
- 토큰당 1 event는 가장 구현이 쉬운데, QPS가 올라가면 CPU/네트워크/프록시 부하가 커집니다.
- 실무에선 “문장부호/공백 기준” 또는 “50~100ms 단위”로 합쳐 보내는 쪽이 비용 대비 효율이 좋습니다(UX는 큰 차이 없음).

2) **Disconnect를 빠르게 전파**
- 스트리밍은 연결이 길어서, 사용자가 탭을 닫는 순간이 흔합니다.
- Starlette/FastAPI는 클라이언트 disconnect 시 요청 task를 취소/중단시키는 흐름이 있고(ASGI `http.disconnect`), generator가 계속 돌면 리소스 누수가 됩니다. 실제로 “클라가 끊겼는데 서버가 끝까지 스트리밍을 수행” 문제는 자주 질문됩니다. ([stackoverflow.com](https://stackoverflow.com/questions/78233692/fastapi-finish-streaming-function-in-streamingresponse-even-if-client-closed-the/79831282?utm_source=openai))  
- 예제처럼 `request.is_disconnected()`를 주기적으로 확인하거나, 취소 예외를 잡아 upstream 요청을 닫으세요.

3) **keep-alive(ping) 넣기**
- 일부 프록시/CDN은 “데이터가 일정 시간 안 오면” 연결을 끊습니다.
- FastAPI SSE 문서가 15초 ping 코멘트를 권장합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))

### 흔한 함정/안티패턴
- **(안티패턴) upstream 전체를 읽고 나서 yield**: `await resp.text()`/`await resp.aread()` 후 스트리밍하려 하면 이미 끝입니다.
- **(안티패턴) 요청마다 httpx AsyncClient 생성**: 연결 풀/SSL 컨텍스트 생성이 누적되면 지연이 커집니다. 앱 수명주기에서 재사용을 고려하세요(httpx는 커넥션 풀을 전제로 설계). ([python-httpx.org](https://www.python-httpx.org/api/?utm_source=openai))
- **(안티패턴) 무한 스트림에 대한 타임아웃/상한 없음**: read timeout을 `None`으로 두는 건 “스트림이 정상일 때” 필요하지만, 대신 서버 레벨에서 최대 스트리밍 시간/최대 토큰/최대 바이트 등을 걸어야 합니다.

### 비용/성능/안정성 트레이드오프
- **SSE vs WebSocket**: SSE는 단방향이라 단순하고 프록시 친화적이라 운영이 편하지만, 양방향 상호작용/바이너리 스트림에는 약합니다.
- **chunk 크기**: 작을수록 UX는 좋아 보이지만, 이벤트 수가 늘어 서버 비용 증가. 클수록 효율적이지만 UI가 “버벅”해 보일 수 있음.
- **백프레셔**: Uvicorn은 버퍼 수위로 backpressure를 걸어주지만 ([uvicorn.org](https://www.uvicorn.org/server-behavior/?utm_source=openai)), 느린 클라이언트가 워커를 장시간 점유할 수 있어 “동시 스트림 수”를 SLO 관점에서 제한해야 합니다(예: 사용자별 동시 2개).

---

## 🚀 마무리
핵심은 “FastAPI에서 스트리밍은 `yield`가 끝이 아니라, **ASGI/서버 버퍼/업스트림 스트림 처리**까지 포함한 시스템 설계”라는 점입니다. 2026년 5월 기준으로는 FastAPI 공식 SSE 가이드가 AI 스트리밍을 대표 사례로 다루고, ping/`raw_data` 같은 운영 디테일까지 안내합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))

도입 판단 기준
- 사용자가 결과를 기다리며 이탈한다 → **무조건 스트리밍 가치 큼**
- 프록시/기업망/모바일 환경이 다양하다 → SSE + ping + 재연결 전략(Last-Event-ID 등)을 같이 설계
- “업스트림 SSE를 프록시”한다 → httpx stream 모드로 **파이프 유지**가 최우선 ([python-httpx.org](https://www.python-httpx.org/async/?utm_source=openai))

다음 학습 추천
- FastAPI “Stream Data / Stream JSON Lines” 고급 가이드로, SSE 외에 JSONL/바이너리 스트리밍까지 비교해보면 설계 옵션이 넓어집니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/advanced/stream-data/?utm_source=openai))
- Uvicorn의 ASGI/버퍼링 동작을 이해하면, “왜 특정 환경에서 한 번에 몰아서 도착하는지” 같은 운영 이슈를 더 빨리 디버깅할 수 있습니다. ([uvicorn.dev](https://uvicorn.dev/concepts/asgi/?utm_source=openai))