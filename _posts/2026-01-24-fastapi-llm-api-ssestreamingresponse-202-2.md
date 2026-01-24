---
title: "FastAPI로 LLM API 서버 “진짜 스트리밍” 만들기: SSE/StreamingResponse 함정까지 (2026년 1월 기준)"
date: 2026-01-24 02:12:14 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-01]
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
LLM API 서버에서 “스트리밍”은 단순 UX 옵션이 아니라 **서버 비용/지연/타임아웃**을 좌우하는 핵심 설계입니다. 긴 응답을 한 번에 반환하면 TTFB(Time To First Byte)가 커지고, 사용자는 “멈춘 것처럼” 느끼며, 서버는 전체 결과를 버퍼링하는 동안 메모리·커넥션을 오래 물고 있게 됩니다. 반대로 토큰 단위로 흘려보내면 **첫 토큰까지의 지연을 최소화**하고, 중간에 사용자가 취소하면 **즉시 연산을 끊어 비용을 절감**할 수 있습니다.

2026년 1월 시점에서 FastAPI로 스트리밍을 구현할 때는 크게 두 갈래가 실무에서 많이 쓰입니다.

- **SSE(Server-Sent Events)**: 브라우저 친화적(자동 재연결), “서버 → 클라이언트” 단방향 토큰 스트리밍에 최적. FastAPI 생태계에서는 `sse-starlette`의 `EventSourceResponse`가 사실상 표준 도구처럼 쓰입니다. ([pypi.org](https://pypi.org/project/sse-starlette/?utm_source=openai))  
- **StreamingResponse(바이트/텍스트 스트림)**: 프로토콜 제약이 적고 범용이지만, 프록시 버퍼링/클라이언트 구현에 따라 “스트리밍이 안 되는 것처럼” 보이는 문제가 자주 발생합니다(특히 브라우저/axios 조합). ([stackoverflow.com](https://stackoverflow.com/questions/75876640/fastapis-streamingresponse-doesnt-return-stream?utm_source=openai))  

또한, OpenAI API 자체도 스트리밍을 SSE 형태로 제공하므로(서버가 OpenAI SSE를 받아서 다시 클라이언트에 SSE로 중계하는 구조) 파이프라인을 깔끔하게 만들 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))  

---

## 🔧 핵심 개념
### 1) “스트리밍”의 본질: flush 가능한 작은 chunk의 연속
HTTP에서 스트리밍은 응답을 끝까지 만든 뒤 보내는 게 아니라, **만들어지는 대로 작은 조각(chunk)을 바로 전송**하는 방식입니다. 프레임워크 관점에서는 “async generator가 `yield`하는 바이트/문자열을 즉시 네트워크로 흘려보내는가”가 핵심입니다.

여기서 흔한 오해가 하나 있습니다. 서버 코드가 `yield`를 하고 있어도,
- 리버스 프록시(Nginx/Cloudflare 등)가 버퍼링하거나
- 클라이언트 라이브러리가 스트림 소비를 제대로 못 하거나
- gzip/압축/미들웨어가 바디를 다시 모아버리면  
**사용자는 ‘한 번에 도착’하는 것처럼** 보게 됩니다.

`sse-starlette` 문서/설명에서도 Nginx 버퍼링이 SSE를 망가뜨리는 대표 사례로 언급되며, `X-Accel-Buffering: no` 또는 `proxy_buffering off` 같은 대응이 중요하다고 말합니다. ([pypi.org](https://pypi.org/project/sse-starlette/?utm_source=openai))  

### 2) SSE vs WebSocket: LLM 토큰에는 SSE가 더 “정답”인 경우가 많다
LLM 채팅 UI의 대부분은 “서버가 토큰을 흘려주고 클라이언트는 표시”하는 단방향입니다. 이때 SSE는:
- HTTP 기반(업그레이드 불필요)
- 브라우저 `EventSource`가 기본 제공(자동 재연결)
- 서버 구현이 단순(한 커넥션에서 이벤트를 계속 push)

특히 `sse-starlette`는 **ping(heartbeat), disconnect 감지, send timeout** 같은 운영 요소를 라이브러리 레벨에서 다루는 방향으로 발전했습니다. ([github.com](https://github.com/sysid/sse-starlette?utm_source=openai))  

### 3) disconnect/cancel은 “옵션”이 아니라 비용 통제 장치
스트리밍에서 가장 중요한 건 “클라이언트가 탭을 닫았는데도 서버가 계속 LLM을 돌리는” 상황을 막는 겁니다. FastAPI/Starlette에서는 `request.is_disconnected()`로 연결 종료를 감지해 루프를 끊는 패턴이 널리 쓰입니다. ([dev.to](https://dev.to/bobbyiliev/how-to-use-server-sent-events-sse-with-fastapi-52fo?utm_source=openai))  

또 하나 실무 팁: StreamingResponse/SSE 응답에서 쿠키/헤더를 설정할 때는 **반드시 최종적으로 반환할 Response 객체에 설정**해야 합니다. 즉, FastAPI 라우트 인자로 받은 `response: Response`에 set_cookie 해놓고 `StreamingResponse(...)`를 반환하면 헤더가 안 나갈 수 있습니다. 반환할 streaming response 인스턴스에 직접 `set_cookie`를 해야 합니다. ([stackoverflow.com](https://stackoverflow.com/questions/79528427/cannot-set-cookies-when-using-streamingresponse-in-fastapi-route-for-sse-server?utm_source=openai))  

---

## 💻 실전 코드
아래 예제는 **(1) LLM 토큰 생성(모의), (2) SSE로 토큰 스트리밍, (3) 클라이언트 disconnect 시 즉시 중단, (4) 프록시 버퍼링 방지 헤더**까지 포함한 “API 서버 뼈대”입니다.

```python
# main.py
import asyncio
import json
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

app = FastAPI()

async def fake_llm_stream(prompt: str) -> AsyncGenerator[str, None]:
    """
    실제 환경에서는 여기에서 OpenAI/자체 LLM의 stream 이벤트를 받아
    delta token을 yield 하는 구조가 됩니다.
    """
    for tok in ["이", "건", " ", "스트", "리", "밍", " ", "데", "모", " ", "입", "니", "다"]:
        await asyncio.sleep(0.05)  # 토큰 생성 지연(모의)
        yield tok

@app.get("/v1/chat/stream")
async def chat_stream(request: Request, prompt: str):
    async def event_generator() -> AsyncGenerator[dict, None]:
        """
        SSE는 텍스트 프로토콜이라 "event/data/id/retry" 형태로 보냅니다.
        data에 JSON 문자열을 넣어두면 프론트에서 다루기 편합니다.
        """
        # 첫 이벤트: 메타/시작 신호
        yield {"event": "start", "data": json.dumps({"prompt": prompt})}

        try:
            async for tok in fake_llm_stream(prompt):
                # 1) 클라이언트가 끊겼으면 즉시 중단 (비용 절감)
                if await request.is_disconnected():
                    break

                # 2) 토큰을 SSE 이벤트로 푸시
                yield {"event": "token", "data": json.dumps({"delta": tok})}

            # 정상 종료 신호
            yield {"event": "done", "data": json.dumps({"reason": "end"})}

        except asyncio.CancelledError:
            # 서버 측 cancel(예: 워커 종료, 타임아웃 등)도 명확히 처리
            # 필요한 리소스 정리 후 예외 재발생
            raise

    # Nginx 등에서 SSE 버퍼링을 끄는 헤더(가능하면 강제)
    # sse-starlette에서도 Nginx 버퍼링 이슈와 X-Accel-Buffering: no를 언급합니다.
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    # ping: 중간에 아무 데이터가 없으면 LB가 끊는 경우가 있어 heartbeat가 중요
    # send_timeout: 클라이언트가 읽지 않아 send가 멈추는 "hanging" 방지 옵션(버전에 따라 지원)
    return EventSourceResponse(
        event_generator(),
        headers=headers,
        ping=15,
        ping_message_factory=lambda: ServerSentEvent(comment="keep-alive"),
    )
```

실행:
```bash
pip install fastapi uvicorn sse-starlette
uvicorn main:app --host 0.0.0.0 --port 8000
```

브라우저 측은 `EventSource("/v1/chat/stream?prompt=...")`로 바로 붙이면 됩니다(SSE는 브라우저 기본 지원).

---

## ⚡ 실전 팁
1) **SSE는 프록시/CDN 버퍼링이 ‘진짜 적’**  
로컬에서는 잘 스트리밍되는데 운영에서 “한 번에 도착”하면, 대개 앱 문제가 아니라 **중간 계층 버퍼링**입니다. `sse-starlette`는 Nginx 기본 버퍼링과 해결책(`X-Accel-Buffering: no`, `proxy_buffering off`)을 구체적으로 언급합니다. ([pypi.org](https://pypi.org/project/sse-starlette/?utm_source=openai))  

2) **heartbeat(ping) 주기는 LB timeout보다 짧게**  
SSE는 연결을 오래 유지하므로, LB/Ingress idle timeout에 걸리지 않게 **주기적으로 comment ping**을 보내세요. `sse-starlette`는 ping을 기본 개념으로 제공하고 커스터마이즈도 지원합니다. ([pypi.org](https://pypi.org/project/sse-starlette/2.1.0/?utm_source=openai))  

3) **disconnect 감지 없으면 LLM 비용이 새는 구조**  
`request.is_disconnected()` 체크는 “예쁘게 종료”가 아니라 **요금 통제**입니다. 특히 upstream(OpenAI 등)에도 cancel을 전파할 수 있게 설계(요청 task cancel, 스트림 종료)하는 게 중요합니다. ([dev.to](https://dev.to/bobbyiliev/how-to-use-server-sent-events-sse-with-fastapi-52fo?utm_source=openai))  

4) **쿠키/헤더 설정은 ‘반환할 스트리밍 Response’에 직접**  
StreamingResponse/SSE에서 `response.set_cookie()`를 했는데 반영이 안 되면, 라우트 파라미터 `Response`가 아니라 **실제 반환 객체(StreamingResponse/EventSourceResponse)**에 `set_cookie`를 해야 합니다. ([stackoverflow.com](https://stackoverflow.com/questions/79528427/cannot-set-cookies-when-using-streamingresponse-in-fastapi-route-for-sse-server?utm_source=openai))  

5) **OpenAI upstream도 SSE라서 “SSE → SSE 중계”가 자연스럽다**  
OpenAI는 스트리밍을 SSE 기반으로 문서화하고 있어, 서버가 upstream 이벤트를 받아 토큰 단위로 그대로(또는 변환해서) 흘려보내는 파이프라인이 깔끔합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))  

---

## 🚀 마무리
FastAPI로 LLM API 서버를 만들 때 스트리밍은 “기능”이 아니라 **아키텍처 선택(SSE/StreamingResponse) + 운영 요소(버퍼링/heartbeat/disconnect/cancel)**의 조합입니다. 2026년 1월 기준으로는, 브라우저 토큰 스트리밍이라면 `sse-starlette`의 `EventSourceResponse`가 운영 친화적인 선택이고(핑/종료/헤더), 그 위에 **disconnect 즉시 중단**과 **프록시 버퍼링 차단**을 반드시 얹는 게 실무 정답에 가깝습니다. ([github.com](https://github.com/sysid/sse-starlette?utm_source=openai))  

다음 학습으로는:
- OpenAI(또는 다른 LLM) 스트림 이벤트를 **서버에서 어떻게 cancel 전파**할지(요청 스코프 cancel, 타임아웃 전략) ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))  
- “토큰 유실/지연” 같은 네트워크 품질 문제까지 고려한 스트리밍 전송 방식(연구 관점) ([arxiv.org](https://arxiv.org/abs/2401.12961?utm_source=openai))  

원하시면 위 코드에 **OpenAI Responses API 스트리밍을 실제로 붙이는 버전(Async client + 이벤트 매핑 + usage 집계 + 에러 이벤트 표준화)**까지 확장해서 작성해드릴게요.