---
title: "FastAPI로 LLM API “진짜 스트리밍” 서버 만들기 (2026년 3월 기준): SSE/StreamingResponse 함정과 설계 해법"
date: 2026-03-16 03:23:02 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-03]
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
LLM API 서버에서 “스트리밍”은 단순 UX 옵션이 아니라 **서버 자원과 지연(latency)을 결정하는 아키텍처 요소**입니다. 긴 응답을 한 번에 내려주면 TTFB(Time To First Byte)가 커지고, 프록시/타임아웃에 걸릴 확률도 올라갑니다. 반대로 토큰 단위로 흘려보내면 사용자는 즉시 반응을 느끼고, 서버는 **backpressure(클라이언트가 느릴 때의 압력)**를 고려한 전송 전략을 가져갈 수 있죠.

2026년 3월 기준으로는 FastAPI 자체 `StreamingResponse` 안정성이 개선되었고(특히 dependency가 `yield`를 쓰는 경우 정리/close 동작 관련 수정) ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/release-notes/?utm_source=openai)), LLM 측에서도 OpenAI Responses API가 **semantic event 기반 SSE 스트리밍**을 제공해(예: `response.output_text.delta`, `response.completed`) 서버가 “토큰” 이상의 이벤트를 다룰 수 있게 됐습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))

---

## 🔧 핵심 개념
### 1) 스트리밍의 2가지 축: Transport vs Event
- **Transport(전송 방식)**  
  - SSE(Server-Sent Events): HTTP 연결 하나를 열고 `text/event-stream`으로 서버→클라이언트 단방향 스트림.
  - WebSocket: 양방향, 세션성. (실시간 음성/상호작용에 유리)
- **Event(이벤트 모델)**  
  과거엔 “그냥 텍스트 chunk”가 대부분이었지만, Responses API는 이벤트 타입이 명확합니다. 예:  
  - `response.created`
  - `response.output_text.delta`
  - `response.completed`
  - `error` ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))  
  즉, 서버는 **delta를 흘리고**, 마지막에 **completed를 보장**해야 클라이언트가 상태머신을 깔끔히 종료할 수 있습니다.

### 2) FastAPI `StreamingResponse`의 본질
FastAPI는 스트리밍 응답에서 **Pydantic 직렬화/JSON 변환을 하지 않고**, iterable/async iterable이 내는 bytes/str을 그대로 내려보냅니다. 즉, “반드시 JSON 한 덩어리”라는 고정관념을 버려야 합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/fr/advanced/stream-data/))  
또한 2026-02-22 릴리즈(0.131.0)에서 `StreamingResponse`와 dependency(`yield`) 조합에서 close 타이밍 관련 버그가 수정되었습니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/release-notes/?utm_source=openai))

### 3) LLM 서버 구축 관점: “내가 추론까지 할 건가, 프록시만 할 건가”
- **직접 추론 서버**: vLLM 같은 OpenAI-compatible server를 띄우고(로컬/온프렘), FastAPI는 인증/가드레일/메타데이터 레이어로 둠. vLLM은 OpenAI 호환 HTTP 서버를 제공하고, OpenAI Python client로도 붙을 수 있는 형태를 지향합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html))
- **프록시 서버**: FastAPI가 OpenAI Responses API 스트리밍을 받아서, 그대로 SSE로 재방출. 이때 핵심은 **(1) upstream 이벤트를 안정적으로 소비**하고, **(2) downstream SSE 포맷을 정확히** 만드는 겁니다.

---

## 💻 실전 코드
아래 예제는 “FastAPI 스트리밍 엔드포인트”를 만들고, 내부에서 OpenAI Responses API 스트림 이벤트를 소비해 **SSE로 변환**해 내려보내는 패턴입니다. (클라이언트는 `EventSource` 또는 `fetch + SSE parser` 사용)

```python
import json
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from openai import OpenAI

app = FastAPI()
client = OpenAI()

def sse(event: str, data) -> str:
    """
    SSE 포맷:
      event: <name>\n
      data: <json>\n
      \n  (빈 줄로 이벤트 경계)
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@app.get("/v1/chat/stream", response_class=StreamingResponse)
async def chat_stream(request: Request, q: str):
    """
    - FastAPI StreamingResponse로 SSE 스트림을 제공
    - upstream(OpenAI Responses API)의 semantic events를 downstream SSE로 매핑
    - 클라이언트 disconnect 시 루프를 즉시 중단(불필요한 토큰 생성/전송 방지)
    """

    async def gen() -> AsyncIterator[str]:
        # 1) upstream 스트리밍 시작 (Responses API: stream=True)
        # 이벤트 타입 예: response.created, response.output_text.delta, response.completed, error 등 ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))
        stream = client.responses.create(
            model="gpt-5",
            input=[{"role": "user", "content": q}],
            stream=True,
        )

        # 2) downstream: 최초 핸드셰이크/메타 이벤트(선택)
        yield sse("meta", {"protocol": "sse", "source": "openai-responses"})

        try:
            for event in stream:
                # 클라이언트가 끊었으면 즉시 중단
                if await request.is_disconnected():
                    break

                etype = getattr(event, "type", None)

                if etype == "response.output_text.delta":
                    # 실제 토큰/부분 문자열 델타
                    # SDK 객체 구조는 버전에 따라 달라질 수 있어,
                    # 안전하게 dict화하거나 필요한 필드만 추출하는 전략을 권장
                    yield sse("delta", {"text": event.delta})

                elif etype == "response.completed":
                    yield sse("done", {"reason": "completed"})
                    break

                elif etype == "error":
                    yield sse("error", {"message": getattr(event, "message", "unknown")})
                    break

                else:
                    # 필요 시 디버깅/관측용으로만 흘리거나 무시
                    pass

        finally:
            # upstream 스트림 정리(가능한 경우)
            # (SDK/transport에 따라 close가 다를 수 있음)
            yield sse("final", {"closed": True})

    headers = {
        # 프록시 버퍼링 방지를 위해 흔히 추가(환경에 따라 효과 차이)
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
```

핵심 포인트:
- FastAPI가 스트리밍에서는 JSON 변환을 하지 않으므로, **SSE 문자열을 직접 yield**하는 방식이 단순하고 강력합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/fr/advanced/stream-data/))
- OpenAI Responses API 스트리밍은 “텍스트 델타”뿐 아니라 lifecycle 이벤트가 있으니, **`completed/done`를 명시적으로 내려** 클라이언트 종료를 안정화합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))

---

## ⚡ 실전 팁
- **(중요) “서버에서 스트리밍했는데, 클라이언트는 한 번에 받는다”**  
  대부분 FastAPI 코드 문제가 아니라 **중간 프록시(Nginx/Cloudflare 터널/서버리스 런타임)**의 buffering/flush 정책 문제입니다. 특정 터널/프록시 조합에서 SSE가 실시간으로 flush되지 않는 이슈 보고도 있습니다. ([github.com](https://github.com/cloudflare/cloudflared/issues/1449?utm_source=openai))  
  해결은 환경별로 다르니, 최소한 다음을 체크하세요:
  - 응답 `Content-Type: text/event-stream`
  - 압축(gzip) 비활성화 여부(압축은 종종 버퍼링을 유발)
  - reverse proxy buffering off 설정
  - HTTP/2/H3 변환 구간에서 flush가 유지되는지

- **disconnect 처리(리소스 절약의 핵심)**  
  스트리밍은 “길게 열린 연결”입니다. 클라이언트가 탭을 닫았는데 서버가 계속 토큰을 만들면 비용/자원이 그대로 증발합니다. 예제처럼 `request.is_disconnected()`를 폴링하거나, AnyIO cancel을 의식한 구조로 설계하세요. (AnyIO는 cancellation semantics가 명확합니다.) ([anyio.readthedocs.io](https://anyio.readthedocs.io/en/latest/cancellation.html?utm_source=openai))

- **FastAPI 버전 고정 + 릴리즈 노트 확인**  
  스트리밍은 edge case가 많아 프레임워크 패치의 영향이 큽니다. 특히 0.131.0에서 `StreamingResponse`와 dependency(`yield`) 조합의 close 처리 관련 수정이 들어갔습니다. 운영에서는 FastAPI/Starlette/Uvicorn 버전을 고정하고, 업그레이드 시 스트리밍 회귀 테스트를 두세요. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/release-notes/?utm_source=openai))

- **로컬 LLM(OpenAI 호환)로 갈아탈 여지 만들기**  
  비용/지연/데이터 거버넌스 때문에 나중에 로컬로 옮기는 경우가 많습니다. vLLM은 OpenAI-compatible server를 제공해 클라이언트/프록시 코드를 크게 바꾸지 않고 이식 가능하게 만듭니다. ([docs.vllm.ai](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html))

---

## 🚀 마무리
2026년 3월 기준 LLM API 서버의 스트리밍은 “토큰을 잘게 보내는 기술”을 넘어서, **semantic event 스트림을 신뢰성 있게 전달하는 서버 설계 문제**가 됐습니다. FastAPI의 `StreamingResponse`는 충분히 강력하지만, 운영에서 진짜 난이도는 프록시/버퍼링/취소/완료 이벤트(EOF) 처리에 있습니다. OpenAI Responses API의 typed 이벤트 스트림을 기반으로 `delta → done`까지 명확히 모델링하면, 클라이언트 UX와 서버 안정성이 같이 좋아집니다. ([platform.openai.com](https://platform.openai.com/docs/guides/streaming-responses?utm_source=openai))

다음 학습 추천:
- OpenAI Responses API의 스트리밍 이벤트 타입을 기준으로 **클라이언트 상태머신(재연결, partial rendering, 오류 복구)** 설계
- vLLM OpenAI-compatible server로 **로컬 추론 + 동일 스트리밍 프로토콜** 구성 실험 ([docs.vllm.ai](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html))
- SSE가 아닌 WebSocket(Reatime)로 넘어가는 기준 정리(양방향/오디오/툴콜 밀도) ([blog.vllm.ai](https://blog.vllm.ai/2026/01/31/streaming-realtime.html))