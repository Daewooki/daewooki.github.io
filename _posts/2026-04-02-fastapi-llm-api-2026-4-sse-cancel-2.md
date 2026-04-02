---
title: "FastAPI로 LLM API 서버 “진짜 스트리밍” 만들기 (2026년 4월 기준): SSE, Cancel, 프록시 버퍼링까지 한 번에 정리"
date: 2026-04-02 02:55:53 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-04]
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
LLM API 서버를 운영해보면 병목은 대개 “모델이 느리다”가 아니라 **유저가 느리게 느낀다**입니다. 800~1500 tokens짜리 답변은 생성 자체가 수 초 걸리는데, 전통적인 JSON 응답은 **완료될 때까지 클라이언트가 아무것도 못 보고 기다립니다.** 반면 스트리밍을 붙이면 총 생성 시간은 같아도 **Time-to-first-token**이 줄어 체감 성능이 급상승합니다. 게다가 “생성 중 취소”, “부분 결과 저장/관찰”, “툴 호출 진행 상황 중계” 같은 운영 기능도 스트리밍이 사실상 전제입니다.

2026년 4월 기준으로는 브라우저/프록시 호환성과 구현 난이도 균형 때문에 **SSE(Server-Sent Events)** 가 LLM 텍스트 스트리밍의 사실상 표준으로 굳어졌고(OpenAI도 SSE 기반 이벤트 스트리밍), FastAPI 역시 SSE 사용성을 공식 문서로 정리하며 `EventSourceResponse`를 안내합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))

---

## 🔧 핵심 개념
### 1) StreamingResponse vs SSE(EventSource)
- **StreamingResponse**: HTTP 응답 바디를 generator/async generator로 흘려보내는 “전송 방식”입니다. 포맷은 자유(plain text, JSON lines 등).
- **SSE**: `text/event-stream`이라는 **프로토콜 포맷**(라인 기반)을 얹은 스트리밍입니다. 브라우저는 `EventSource`로 바로 소비 가능하고, 서버→클라이언트 단방향에 최적화되어 LLM 채팅 UI와 궁합이 좋습니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/es/tutorial/server-sent-events/?utm_source=openai))

실무적으로는 “LLM 토큰/청크를 스트리밍한다” = “SSE로 보낸다”에 가깝습니다.

### 2) OpenAI식 “이벤트 스트리밍” 모델
OpenAI 최신 스트리밍은 단순 텍스트 chunk가 아니라 **typed event**(예: `response.output_text.delta`, `response.completed`, `error`)로 흘러옵니다. 서버는 이 이벤트를 받아서
- 그대로 프록시(투명 중계)하거나
- 제품 요구에 맞춰 `delta`만 추려 UI에 전달하거나
- tool call/상태 이벤트를 별도 채널로 분리
같은 설계를 합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))

### 3) “스트리밍이 안 되는” 가장 흔한 원인: 버퍼링
코드가 맞아도 운영 환경에서 “한 번에 몰아서 도착”하는 경우가 많습니다. 원인은 보통:
- **Reverse proxy(Nginx 등) buffering**
- **CDN / API Gateway buffering**
- 너무 큰 chunk로만 `yield`해서 사실상 flush가 늦는 경우

특히 Nginx 기본 설정은 스트리밍을 삼켜버리기 쉬워 `proxy_buffering off` 같은 조치가 사실상 필수입니다. ([php.cn](https://www.php.cn/faq/2045006.html?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “LLM provider(OpenAI Responses API 스트리밍) → FastAPI SSE → 브라우저”의 전형적인 구조입니다. 핵심은 **(1) async generator로 이벤트를 소비하고 (2) SSE 포맷으로 즉시 yield (3) 클라이언트 disconnect 시 생성도 즉시 중단**입니다.

```python
# Python 3.11+
# pip install fastapi uvicorn openai
# (FastAPI SSE는 버전에 따라 EventSourceResponse 위치가 다를 수 있습니다.
#  공식 문서 기준으로는 fastapi.sse.EventSourceResponse를 사용합니다.)

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.sse import EventSourceResponse  # FastAPI SSE 튜토리얼의 권장 방식
from pydantic import BaseModel

from openai import AsyncOpenAI

app = FastAPI()
client = AsyncOpenAI()  # OPENAI_API_KEY 환경변수 사용

class ChatIn(BaseModel):
    prompt: str

def sse(event: str, data: dict) -> str:
    """
    SSE는 'event:' / 'data:' 라인 포맷을 사용하고,
    메시지 하나는 빈 줄(\n\n)로 끝납니다.
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

async def llm_to_sse_stream(prompt: str, request: Request) -> AsyncIterator[str]:
    """
    OpenAI 스트리밍 이벤트를 받아서, 클라이언트에 SSE로 전달.
    - disconnect 감지 시 즉시 중단
    - delta(토큰) / completed / error 등 이벤트를 분기 처리
    """
    try:
        stream = await client.responses.create(
            model="gpt-5",
            input=[{"role": "user", "content": prompt}],
            stream=True,
        )

        async for event in stream:
            # 1) 클라이언트가 끊겼으면 즉시 중단 (계속 생성하면 비용/자원 낭비)
            if await request.is_disconnected():
                # 여기서 그냥 return하면 generator 종료 -> 응답 종료
                return

            etype = getattr(event, "type", None)

            # 2) 가장 많이 쓰는 텍스트 델타 이벤트만 프론트로 전달
            if etype == "response.output_text.delta":
                # SDK 이벤트 구조는 버전에 따라 다를 수 있어 안전하게 접근
                delta = getattr(event, "delta", None) or getattr(event, "text", None)
                if delta:
                    yield sse("delta", {"text": delta})

            # 3) 완료 이벤트
            elif etype == "response.completed":
                yield sse("done", {"ok": True})
                return

            # 4) 실패/에러 이벤트
            elif etype in ("response.failed", "error"):
                yield sse("error", {"message": "LLM stream failed", "type": etype})
                return

            # 필요하면 tool call 등 다른 이벤트도 그대로 브로드캐스트 가능
            # else:
            #     yield sse("event", {"type": etype})

            # 5) (선택) 너무 타이트한 루프 방지: provider가 이벤트를 매우 자주 줄 때
            await asyncio.sleep(0)

    except asyncio.CancelledError:
        # 서버가 요청을 cancel(클라이언트 disconnect 등)하면 여기로 올 수 있음
        # 필요한 정리 로직이 있으면 수행
        raise
    except Exception as e:
        yield sse("error", {"message": str(e)})

@app.post("/v1/chat/stream")
async def chat_stream(body: ChatIn, request: Request):
    """
    media_type은 반드시 text/event-stream.
    """
    return EventSourceResponse(
        llm_to_sse_stream(body.prompt, request),
        media_type="text/event-stream",
        # 헤더는 인프라에 따라 조정. 예: Nginx buffering 우회 힌트
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 일부 Nginx 구성에서 유효
        },
    )
```

참고로 FastAPI는 SSE에서 “유휴 시간에 ping(comment)”를 보내 프록시가 연결을 끊지 않게 하는 패턴도 공식 문서에서 권장합니다(keep-alive). ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/es/tutorial/server-sent-events/?utm_source=openai))  
또한 OpenAI 스트리밍은 이벤트 타입이 명확히 정의되어 있어, `delta`만 소비할지/툴 호출까지 중계할지 설계를 먼저 하는 게 중요합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))

---

## ⚡ 실전 팁
1) **프록시/게이트웨이 버퍼링부터 의심**
- “서버 로그상 yield는 하고 있는데, 클라이언트는 한 번에 받음” → 80%는 buffering입니다.
- Nginx를 쓴다면 location 단에서 `proxy_buffering off;`가 핵심이고, chunked 전송이 깨지지 않게 설정을 확인해야 합니다. ([php.cn](https://www.php.cn/faq/2045006.html?utm_source=openai))

2) **disconnect 처리(취소)가 비용을 줄인다**
- 스트리밍은 “연결이 끊겨도 LLM 생성이 계속 돈다”가 최악입니다.
- `request.is_disconnected()`를 주기적으로 체크하고, provider 스트림을 즉시 종료하세요.
- FastAPI/ASGI에서는 disconnect 시 task가 cancel되며 `CancelledError`로 전파되는 케이스도 흔합니다(정리 코드는 예외 처리 블록에서). ([reddit.com](https://www.reddit.com/r/FastAPI/comments/1mu2ehv?utm_source=openai))

3) **이벤트 설계: ‘텍스트’만 보내지 말고 ‘상태’도 보내라**
- `delta`, `done`, `error`는 최소 세트입니다.
- 툴 호출/검색/코드 실행 같은 단계가 있다면 “status 이벤트”를 추가하면 UX가 크게 좋아집니다(OpenAI도 lifecycle 이벤트를 스트리밍으로 분리). ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))

4) **chunk 크기와 flush 빈도의 트레이드오프**
- 너무 자주 `yield`하면 서버/네트워크 오버헤드가 커지고,
- 너무 크게 모아서 `yield`하면 스트리밍 체감이 사라집니다.
- 보통은 “provider 이벤트 단위(delta)” 그대로 중계하되, 프론트에서 렌더링을 rate-limit(예: 30~60fps) 하는 쪽이 전체 비용이 낮습니다.

5) **SSE는 단방향이다: 업스트림(클라→서버)은 별도 설계**
- 유저가 “중단/재생성/파라미터 변경”을 보내려면:
  - 별도 HTTP endpoint(POST /cancel 등) + request_id
  - 혹은 WebSocket(양방향)로 전환
  같은 선택지가 필요합니다. 다만 “LLM이 말하고 UI가 듣는” 구조면 SSE가 기본값으로 가장 단순합니다. ([medium.com](https://medium.com/%402nick2patel2/fastapi-server-sent-events-for-llm-streaming-smooth-tokens-low-latency-1b211c94cff5?utm_source=openai))

---

## 🚀 마무리
FastAPI로 LLM API 서버를 만들 때 스트리밍의 본질은 “코드로 yield 한다”가 아니라,
- **SSE 프로토콜로 표준화하고**
- **disconnect/cancel을 제대로 처리하고**
- **프록시 버퍼링을 끄고**
- **이벤트(텍스트/상태/에러)를 제품 요구에 맞게 설계**  
하는 데 있습니다.

다음 학습으로는:
- OpenAI Responses API의 **스트리밍 이벤트 타입 설계**(텍스트뿐 아니라 tool call까지) ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))
- FastAPI 공식 SSE 문서의 **keep-alive(ping) 패턴**과 타입 검증/직렬화 방식 ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/es/tutorial/server-sent-events/?utm_source=openai))
- 운영 인프라(Nginx/API Gateway/CDN)에서 **버퍼링/타임아웃/커넥션 유지** 체크리스트
를 묶어 “개발 환경에서는 되는데 운영에서 안 되는” 문제를 선제적으로 제거하는 걸 추천합니다.