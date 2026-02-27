---
title: "FastAPI로 LLM API 서버 “진짜 스트리밍” 만들기 (2026년 2월 기준): SSE, Cancel, Backpressure까지 한 번에"
date: 2026-02-27 02:43:25 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-02]
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
LLM API 서버를 직접 운영해보면 “응답이 느리다”는 사용자 불만의 대부분은 **총 처리시간**보다 **Time-to-first-token(첫 토큰 도착 시간)** 에서 발생합니다. 특히 프롬프트가 길거나 tool 호출/후처리가 붙으면 첫 화면이 뜨기까지 수 초가 걸리기도 하죠. 이때 **Streaming**을 붙이면 UX가 급격히 좋아집니다.

2026년 2월 현재도 웹/모바일에서 가장 현실적인 선택지는 크게 두 가지입니다.

- **SSE(Server-Sent Events)**: HTTP 위에서 server → client 단방향 스트리밍. 브라우저는 `EventSource`로 즉시 소비 가능.
- **WebSocket**: 양방향이 필요할 때 강력하지만, 인프라/프록시/인증/스케일링 복잡도가 올라감.

LLM “생성 텍스트를 흘려보내는” 전형적인 API에는 **SSE가 기본값으로 더 단순**하다는 흐름이 강합니다. 또한 OpenAI도 “Streaming API responses” 가이드를 SSE 이벤트 기반으로 설명합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))

---

## 🔧 핵심 개념
### 1) StreamingResponse vs SSE(EventSourceResponse)
- `StreamingResponse`(FastAPI/Starlette): **바이트 스트림**을 chunked transfer로 흘려보내는 가장 저수준 방식. 파일/바이너리/텍스트 모두 가능. ([medium.com](https://medium.com/%40ab.hassanein/streaming-responses-in-fastapi-d6a3397a4b7b?utm_source=openai))  
- SSE(`text/event-stream`): 스트리밍 “형식(protocol)”이 얹힌 텍스트 스트림. 메시지 프레이밍이 명확해서 **프론트에서 토큰 단위 UI 업데이트**가 쉽습니다. 이벤트는 아래처럼 `\n\n`로 이벤트 경계를 자릅니다. ([medium.com](https://medium.com/%40inandelibas/real-time-notifications-in-python-using-sse-with-fastapi-1c8c54746eb7?utm_source=openai))  

SSE wire format(핵심만):
- 한 이벤트는 여러 줄로 구성 가능
- `data: ...` 여러 줄 가능
- 이벤트 끝은 **blank line(`\n\n`)**
- `:`로 시작하는 라인은 comment(heartbeat로 활용)

### 2) LLM Provider 스트리밍 → 우리 서버 SSE 재스트리밍
요즘 LLM Provider는 대체로 “stream=True” 같은 옵션으로 **이벤트/델타 스트림**을 줍니다. OpenAI Responses API는 스트리밍을 “typed semantic events”로 내보내며, 예를 들어 `response.output_text.delta` 같은 이벤트를 반복적으로 받습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))  
서버는 이를 받아:
1) 델타를 파싱하고
2) SSE `data:`로 감싸서
3) 클라이언트로 즉시 flush

### 3) 실무에서 제일 중요한 3가지: disconnect, heartbeat, backpressure
- **Client disconnect 처리**: 브라우저 탭 닫았는데 서버가 계속 LLM을 물고 있으면 비용/스레드/커넥션이 새는 구조가 됩니다. `request.is_disconnected()` 체크나, CancelledError/CancelScope 기반 취소가 핵심 이슈로 자주 언급됩니다. ([github.com](https://github.com/sysid/sse-starlette?utm_source=openai))  
- **Heartbeat(ping)**: 중간 프록시/로드밸런서가 “조용한 연결”을 끊어버리는 일이 있어 주기적으로 `: ping\n\n` 같은 comment를 흘려 연결을 살립니다. `sse-starlette`는 `ping` 옵션도 제공합니다. ([github.com](https://github.com/sysid/sse-starlette?utm_source=openai))  
- **Backpressure**: 생산자(LLM 이벤트)가 빠르고 소비자(클라이언트 네트워크)가 느릴 때 메모리 버퍼가 커집니다. 단순 generator보다 **anyio memory channel** 패턴이 안전한 경우가 많습니다. ([github.com](https://github.com/sysid/sse-starlette?utm_source=openai))  

---

## 💻 실전 코드
아래 코드는 **OpenAI 스트리밍 이벤트를 받아 SSE로 재전송**하는 FastAPI 엔드포인트 예제입니다. 포인트는:
- SSE 프레이밍을 직접 작성 (`data: ...\n\n`)
- disconnect 시 즉시 중단
- heartbeat로 idle timeout 방지
- “done” 이벤트로 종료 신호 제공

```python
import asyncio
import json
import time
from typing import AsyncIterator, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

# OpenAI SDK (Responses API streaming)
from openai import OpenAI

app = FastAPI()
client = OpenAI()

def sse_event(data: dict, event: Optional[str] = None) -> bytes:
    """
    SSE 포맷:
      event: <name>\n
      data: <json>\n
      \n
    """
    lines = []
    if event:
        lines.append(f"event: {event}")
    lines.append("data: " + json.dumps(data, ensure_ascii=False))
    return ("\n".join(lines) + "\n\n").encode("utf-8")

async def stream_openai_to_sse(request: Request, prompt: str) -> AsyncIterator[bytes]:
    """
    OpenAI 스트림(typed events)을 받아서 SSE로 변환해 흘려보낸다.
    - disconnect 시 중단
    - heartbeat 주기적으로 전송
    """
    heartbeat_interval = 10.0
    last_sent = time.monotonic()

    # 1) 클라이언트에게 스트림 시작 알림(선택)
    yield sse_event({"status": "started"}, event="meta")

    try:
        stream = client.responses.create(
            model="gpt-5",
            input=[{"role": "user", "content": prompt}],
            stream=True,
        )

        for ev in stream:
            # 2) 클라이언트 disconnect 확인 (비용/리소스 누수 방지)
            if await request.is_disconnected():
                break

            now = time.monotonic()
            if now - last_sent >= heartbeat_interval:
                # SSE comment(콜론 라인)는 브라우저가 무시하지만 연결 유지에 도움
                yield b": ping\n\n"
                last_sent = now

            # 3) OpenAI typed event 처리: 텍스트 delta만 추출해 전송
            # OpenAI 가이드는 type으로 이벤트 구분을 권장 ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))
            ev_type = getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else None)

            if ev_type == "response.output_text.delta":
                delta = getattr(ev, "delta", None) or (ev.get("delta") if isinstance(ev, dict) else "")
                if delta:
                    yield sse_event({"delta": delta}, event="token")
                    last_sent = time.monotonic()

            elif ev_type in ("response.completed", "response.failed", "error"):
                # 종료/에러 계열은 클라이언트가 처리하기 쉽게 이벤트로 전달
                payload = ev.model_dump() if hasattr(ev, "model_dump") else (ev if isinstance(ev, dict) else {"type": ev_type})
                yield sse_event(payload, event="done" if ev_type == "response.completed" else "error")
                break

            # 그 외 이벤트는 필요 시 로깅/메트릭으로만 사용
            # (tool call delta, annotations 등)

        # 4) 정상 종료 신호(Provider 종료 이벤트를 못 받는 경우 대비)
        yield sse_event({"status": "closed"}, event="meta")

    except asyncio.CancelledError:
        # 서버 쪽 취소(클라이언트 끊김/서버 shutdown) 시 정리 포인트
        raise
    except Exception as e:
        yield sse_event({"message": str(e)}, event="error")

@app.get("/v1/chat/stream")
async def chat_stream(request: Request, prompt: str):
    # SSE는 반드시 text/event-stream
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        # reverse proxy를 쓴다면 X-Accel-Buffering: no(Nginx) 같은 설정도 고려
    }
    return StreamingResponse(
        stream_openai_to_sse(request, prompt),
        media_type="text/event-stream",
        headers=headers,
    )
```

---

## ⚡ 실전 팁
1) **SSE는 “프록시 버퍼링”이 가장 흔한 함정**
- 로컬에서는 잘 되는데 운영(Nginx/Ingress/CDN)에서 토큰이 한 번에 몰아서 오는 경우가 많습니다.
- `text/event-stream`을 쓰고, 프록시의 response buffering을 끄는 설정을 확인하세요(특히 Nginx/Ingress). “MIME type이 중요하다, buffering되면 실시간성이 깨진다”는 가이드가 반복됩니다. ([modal.com](https://modal.com/docs/guide/streaming-endpoints?utm_source=openai))  

2) **disconnect 감지는 ‘항상’ 믿을 수 있다고 가정하지 말기**
- `request.is_disconnected()`로 충분한 경우가 많지만, 환경/버전/서버 조합에 따라 이슈가 보고되기도 합니다. ([gitlab.com](https://gitlab.com/gtucker.io/renelick/-/issues/58?utm_source=openai))  
- 더 강하게 가져가려면 “disconnect watcher task가 CancelScope를 취소”하는 패턴(요지는 `request.receive()`에서 `http.disconnect`를 감지)을 고려하세요. ([fastapiexpert.com](https://fastapiexpert.com/blog/2024/06/06/understanding-client-disconnection-in-fastapi/?utm_source=openai))  

3) **Heartbeat(ping) 없으면 운영에서 끊긴다**
- LLM이 잠깐 생각(?)하는 구간에 프록시가 idle timeout으로 끊을 수 있습니다.
- `: ping\n\n` 같은 comment heartbeat는 구현 난이도 대비 효과가 큽니다. ([medium.com](https://medium.com/%402nick2patel2/fastapi-server-sent-events-for-llm-streaming-smooth-tokens-low-latency-1b211c94cff5?utm_source=openai))  

4) **Backpressure가 걱정되면 generator 대신 channel**
- 간단한 스트림은 async generator로 충분하지만,
- 생산/소비 속도 차가 커지면 `anyio.create_memory_object_stream()`로 bounded buffer를 두고 producer/consumer를 분리하는 방식이 안정적입니다(특히 여러 upstream을 합치거나 fan-out 할 때). ([github.com](https://github.com/sysid/sse-starlette?utm_source=openai))  

5) **SDK/클라이언트 코드까지 “스트리밍 타입”을 고정하라**
- 스트리밍 여부에 따라 반환 타입이 갈리는 경우가 많아, 타입 안정성을 개선하려는 도구/SDK도 계속 나오고 있습니다. API 스펙에 `stream: true`일 때의 응답 이벤트를 명확히 문서화하는 게 장기적으로 이득입니다. ([speakeasy.com](https://www.speakeasy.com/blog/release-sse-improvements?utm_source=openai))  

---

## 🚀 마무리
FastAPI로 LLM API 서버를 만들 때 스트리밍의 본질은 “그냥 yield”가 아니라, **(1) SSE 프레이밍 (2) disconnect 취소 (3) heartbeat (4) backpressure**를 함께 설계하는 것입니다. OpenAI 같은 Provider의 typed streaming event를 그대로 흘려보내지 말고, **클라이언트가 소비하기 쉬운 SSE 이벤트 스키마(token/done/error/meta)** 로 정리해주면 운영 난이도가 확 떨어집니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))  

다음 학습으로는:
- `sse-starlette`의 `ping`, `send_timeout`, channel 기반 streaming 구조 이해 ([github.com](https://github.com/sysid/sse-starlette?utm_source=openai))  
- tool call/structured output까지 포함한 “이벤트 라우팅(텍스트/툴/메타)” 설계 ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))  
를 추천합니다.