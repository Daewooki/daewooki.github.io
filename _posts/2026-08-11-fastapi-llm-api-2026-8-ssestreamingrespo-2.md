---
title: "FastAPI로 LLM API 서버를 “진짜로” 스트리밍하기: 2026년 8월 기준 SSE/StreamingResponse 설계와 함정 정리"
date: 2026-08-11 02:12:36 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-08]
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
LLM API 서버에서 “스트리밍”은 UX가 아니라 **서버 아키텍처** 문제입니다. 토큰을 빨리 보내는 것만이 아니라, **취소(cancellation)**, **backpressure**, **프록시 버퍼링**, **동시 연결 수**, **관측성(로그/메트릭)**까지 함께 설계해야 운영이 됩니다.

- 언제 쓰면 좋나  
  - 채팅/요약/에이전트처럼 **생성 시간이 길고(수 초~수십 초)** 중간 결과가 사용자 가치로 직결되는 경우
  - 클라이언트가 브라우저 기반이고 **단방향(서버→클라이언트) 이벤트**면 충분한 경우(SSE가 최적) ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))
- 언제 쓰면 안 되나  
  - 양방향(클라이언트 중간 명령/도구 호출/컨트롤 메시지)이 핵심이면 WebSocket이 자연스럽습니다.
  - CDN/리버스 프록시가 스트림을 **버퍼링**하거나 제한이 강한 환경이면(특히 장시간) 설계 비용이 급증합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) “스트리밍”의 실체: ASGI + chunked + generator
FastAPI의 스트리밍은 결국 **ASGI 서버(Uvicorn 등)**가 `Content-Length` 없이 응답을 보내면 **chunked encoding**으로 바디를 흘려보내는 모델입니다. ([uvicorn.org](https://www.uvicorn.org/server-behavior/?utm_source=openai))  
즉, 애플리케이션은 “조각을 만든다(yield)” / 서버는 “조각을 네트워크로 flush한다”의 조합입니다.

### 2) 2026년 FastAPI SSE: 공식 EventSourceResponse
2026년 기준 FastAPI는 SSE를 공식 기능으로 제공하며(“FastAPI 0.135.0에 추가”), `EventSourceResponse` / `ServerSentEvent`로 **프레이밍, keep-alive ping, no-cache, Nginx 버퍼링 방지 헤더** 같은 운영 디테일까지 기본 지원합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))  
LLM 스트리밍의 “가성비”는 사실 여기서 나옵니다: WebSocket 대비 구현/운영 복잡도가 낮습니다.

### 3) 내부 흐름(권장): “LLM 스트림 → 서버 fan-out → SSE”
현실적인 구조는 보통 이렇습니다.

1. 클라이언트가 `/chat/stream` 호출(POST도 가능) ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))  
2. 서버는 LLM provider(OpenAI 등)로부터 토큰/델타를 **upstream streaming**으로 수신  
3. 수신한 조각을 **즉시 SSE 이벤트로 변환**하여 downstream으로 `yield`  
4. 동시에 DB 저장/메트릭/trace는 **분리된 태스크**로 처리(동기 IO는 threadpool 고려)

여기서 중요한 차이는:
- “단순히 yield만 한다”가 아니라,
- **취소 전파**(클라이언트 끊김 → upstream 요청 중단),
- **threadpool 고갈 방지**(sync code가 끼면 Starlette가 thread pool로 넘기는데 기본 40 토큰 제한이 있음) ([starlette.dev](https://starlette.dev/threadpool/?utm_source=openai))
를 같이 다뤄야 한다는 점입니다.

---

## 💻 실전 코드
아래 예제는 “toy”가 아니라, 실제로 LLM API 서버에서 흔한 요구를 반영했습니다.

- SSE로 토큰 스트리밍
- 연결 종료 시 upstream 취소
- 로그/저장(예: DB write)은 별도 태스크로 분리(여기서는 파일로 대체)
- Nginx/프록시 버퍼링을 피하기 위해 FastAPI SSE 기본 헤더 활용 ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))

### 0) 설치/실행
```bash
python -m venv .venv
source .venv/bin/activate

pip install "fastapi>=0.135.0" uvicorn httpx anyio

uvicorn app:app --host 0.0.0.0 --port 8000
```

### 1) 서버 코드 (SSE + upstream streaming + 취소/관측성)
```python
# app.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import anyio
import httpx
from fastapi import FastAPI, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

app = FastAPI()


class ChatRequest(BaseModel):
    conversation_id: str = Field(..., description="서버가 저장/집계에 쓰는 대화 ID")
    user_id: str
    prompt: str
    model: str = "gpt-4.1-mini"  # 예시
    temperature: float = 0.2


@dataclass
class TokenEvent:
    type: str  # "token" | "done" | "error" | "meta"
    data: dict


async def write_audit_log(conversation_id: str, event: TokenEvent) -> None:
    # 현실에서는 DB/큐/로그 파이프라인으로 보내겠지만,
    # 스트리밍 경로를 막지 않도록 "별도 태스크"로 처리하는 게 핵심.
    line = json.dumps(
        {"ts": time.time(), "conversation_id": conversation_id, **event.data},
        ensure_ascii=False,
    )
    async with await anyio.open_file("audit.log", "a", encoding="utf-8") as f:
        await f.write(line + "\n")


async def openai_like_stream(prompt: str, model: str, temperature: float) -> AsyncIterator[str]:
    """
    실제 운영에서는 OpenAI/다른 provider의 streaming SDK를 쓰세요.
    여기서는 httpx streaming을 가정한 '형태'만 보여줍니다.
    """
    # 예: OpenAI 호환 엔드포인트를 쓴다고 가정(사내 gateway 포함 가능)
    # 주의: 아래 URL/포맷은 예시입니다. 실제로는 provider 문서에 맞춰야 합니다.
    url = "https://example-llm-gateway.internal/v1/chat/completions"

    payload = {
        "model": model,
        "stream": True,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }

    timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                # provider가 SSE/JSONL 등으로 줄 수 있음. 여기서는 "토큰 문자열"만 뽑는다고 가정.
                # (현실에서는 line 파싱이 가장 자주 깨지는 포인트)
                yield line


@app.post("/chat/stream", response_class=EventSourceResponse)
async def chat_stream(body: ChatRequest, request: Request) -> EventSourceResponse:
    """
    핵심 포인트:
    - async generator에서 yield ServerSentEvent
    - 클라이언트 disconnect 감지 시 upstream도 중단
    - 저장/관측성은 별도 태스크로 fan-out
    """

    send_chan, recv_chan = anyio.create_memory_object_stream[TokenEvent](max_buffer_size=200)

    async def producer() -> None:
        try:
            # 메타 이벤트(예: 모델/요청ID 등)
            await send_chan.send(TokenEvent(type="meta", data={"event": "start", "model": body.model}))

            async for tok in openai_like_stream(body.prompt, body.model, body.temperature):
                # 클라이언트가 끊겼으면 빨리 중단(취소 전파 이전에 사전 체크)
                if await request.is_disconnected():
                    break
                await send_chan.send(TokenEvent(type="token", data={"token": tok}))

            await send_chan.send(TokenEvent(type="done", data={"event": "done"}))
        except Exception as e:
            await send_chan.send(TokenEvent(type="error", data={"error": str(e)}))
        finally:
            await send_chan.aclose()

    async def auditor() -> None:
        # recv_chan을 복제해서 쓰는 대신, 여기선 "스트림 이벤트를 만들 때마다" audit을 찍는 방식이 아니라
        # "한 번 더 읽는" 구조가 필요함.
        # 간단화를 위해: 아래에서는 generator에서 write_audit_log를 호출하는 방식으로 처리(가장 흔한 구현).
        # (진짜 운영에서는 브로커/큐를 권장)
        return

    async def event_generator() -> AsyncIterator[ServerSentEvent]:
        # producer를 백그라운드로 돌리고, 이 generator는 downstream으로 내보내기만 함
        async with anyio.create_task_group() as tg:
            tg.start_soon(producer)

            async for ev in recv_chan:
                # audit은 "스트리밍 경로를 막지 않도록" 가볍게/비동기로 처리
                tg.start_soon(write_audit_log, body.conversation_id, ev)

                if ev.type == "token":
                    yield ServerSentEvent(event="token", data=json.dumps(ev.data, ensure_ascii=False))
                elif ev.type == "meta":
                    yield ServerSentEvent(event="meta", data=json.dumps(ev.data, ensure_ascii=False))
                elif ev.type == "error":
                    yield ServerSentEvent(event="error", data=json.dumps(ev.data, ensure_ascii=False))
                    # 에러 후 스트림 종료
                    break
                elif ev.type == "done":
                    yield ServerSentEvent(event="done", data="[DONE]")
                    break

    return EventSourceResponse(event_generator())
```

### 2) 예상 출력(클라이언트 관점)
브라우저/EventSource 또는 `fetch`로 읽으면 다음처럼 이벤트가 옵니다.

- `event: meta` → 시작 메타
- `event: token` → 토큰/델타 반복
- `event: done` → `[DONE]`

FastAPI SSE는 keep-alive ping과 캐시/버퍼링 관련 헤더를 기본 처리합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **SSE를 “기본값”으로 두고, WebSocket은 필요할 때만**
- 브라우저 기본 지원 + 재연결 + 단방향 스트리밍에 최적. FastAPI가 SSE 운영 헤더/keep-alive까지 처리합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))  
- “양방향 제어 메시지”가 핵심이면 WebSocket으로 가세요(툴 호출 승인, 중간 stop, 멀티플렉싱 등).

2) **disconnect → upstream 취소를 강제**
- LLM 호출이 비싸면, 클라이언트 이탈 시 upstream을 끊지 않으면 비용이 그대로 나갑니다.
- `request.is_disconnected()` 같은 빠른 체크 + provider SDK의 cancel/close를 엮으세요.

3) **sync 코드(특히 DB/파일/외부 SDK)로 event loop를 막지 말 것**
- Starlette는 sync endpoint/의존성 등을 threadpool로 넘기는데 기본 동시 실행이 제한적입니다(기본 40 토큰). 스트리밍 요청이 늘면 “스트림이 느려졌다”가 아니라 “서버가 멎었다”로 체감됩니다. ([starlette.dev](https://starlette.dev/threadpool/?utm_source=openai))

### 흔한 함정/안티패턴
- **StreamingResponse/SSE 안에서 무거운 저장 로직을 직접 수행**: 토큰 flush 간격이 늘어나고, 결국 “스트리밍처럼 보이지만 끊기는” 현상이 납니다.
- **프록시/Ingress 버퍼링**: 애플리케이션이 yield해도 중간 장비가 버퍼링하면 클라이언트는 마지막에 몰아서 받습니다. FastAPI SSE가 `X-Accel-Buffering: no` 등을 기본 제공하지만, 실제 인프라 설정(Nginx, CDN)은 별도 검증이 필요합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))
- **TaskGroup/CancelScope 정리 실패**: 스트리밍 중 예외/취소에서 TaskGroup 정리가 꼬이면 런타임 에러/리소스 누수가 나기 쉽습니다(특히 “스트림 내부에서 또 다른 스트림을 관리”할 때). AnyIO/TaskGroup은 구조적 동시성이라 종료 규칙이 엄격합니다. ([anyio.readthedocs.io](https://anyio.readthedocs.io/en/stable/api.html?highlight=taskstatus&utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **SSE(HTTP/1.1) vs HTTP/2**: SSE 자체는 HTTP/1.1에서도 잘 동작하지만, 대량 동시 연결에서 프론트(프록시)가 HTTP/2로 받아 multiplexing하는 구성이 유리한 경우가 많습니다. 서버/프록시 조합에 따라 체감이 크게 갈립니다.
- **Uvicorn 설정**: Uvicorn은 설정에 따라 HTTP 구현이 달라질 수 있고(릴리즈 노트/설정 참고), 스트리밍이 “flush된다”는 가정은 반드시 부하테스트로 검증해야 합니다. ([uvicorn.dev](https://uvicorn.dev/release-notes/?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 8월 기준 FastAPI에서 LLM 스트리밍 API를 만들 때의 안전한 기본 선택지는:

- **SSE(EventSourceResponse) + async generator**를 기본으로 두고 ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))  
- 스트림 내부는 **(1) upstream token 수신 (2) downstream 즉시 전달 (3) 저장/관측성 fan-out (4) disconnect 취소 전파**를 분리해서 설계하며,
- sync 작업/threadpool 고갈, 프록시 버퍼링, cancel 정리 같은 “운영 함정”을 초기에 테스트로 잡는 것입니다. ([starlette.dev](https://starlette.dev/threadpool/?utm_source=openai))

도입 판단 기준(실무용):
- “브라우저 채팅 UX + 단방향 스트림”이면 SSE로 시작  
- “양방향 제어/상태 동기화/에이전트 orchestration이 핵심”이면 WebSocket(또는 별도 control channel) 고려  
- “스트림이 돈과 직결(LLM 비용)”이면 cancel 전파와 타임아웃/리트라이 정책부터 먼저 설계

다음 학습 추천:
- FastAPI SSE 공식 문서(keep-alive/헤더 동작까지 포함) ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))  
- Starlette threadpool/AnyIO TaskGroup(구조적 동시성) 이해 ([starlette.dev](https://starlette.dev/threadpool/?utm_source=openai))  
- Uvicorn의 스트리밍/전송 동작(Transfer-Encoding, 설정/릴리즈 변화) ([uvicorn.org](https://www.uvicorn.org/server-behavior/?utm_source=openai))