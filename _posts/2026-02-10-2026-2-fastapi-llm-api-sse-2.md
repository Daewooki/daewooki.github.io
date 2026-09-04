---
title: "2026년 2월판: FastAPI로 LLM API 서버 스트리밍(SSE) “제대로” 구축하는 법"
description: "LLM API 서버에서 UX를 좌우하는 건 “정확도”만이 아닙니다. 첫 토큰까지의 지연(TTFT), 생성 중 부분 결과를 얼마나 자연스럽게 전달하는지, 그리고 연결이 끊겼을 때의 복구 전략이 실제 체감 품질을 결정합니다."
date: 2026-02-10 03:17:50 +0900
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
LLM API 서버에서 UX를 좌우하는 건 “정확도”만이 아닙니다. **첫 토큰까지의 지연(TTFT)**, 생성 중 **부분 결과를 얼마나 자연스럽게 전달하는지**, 그리고 **연결이 끊겼을 때의 복구 전략**이 실제 체감 품질을 결정합니다. 특히 긴 답변/툴 호출/검색 기반 응답이 늘면서, **한 번에 완성된 JSON을 주는 방식**은 대기 시간이 길고, 클라이언트는 “멈춘 것처럼” 보이기 쉽습니다.

2026년 2월 기준 실무에서 가장 현실적인 선택은:
- 서버는 FastAPI
- 스트리밍은 **HTTP 기반 SSE(Server-Sent Events)** 또는 chunked streaming
- 업스트림 LLM은 OpenAI **Responses API stream 이벤트** 또는 vLLM 같은 **OpenAI-compatible server의 스트리밍**을 “그대로” 프록시

입니다. OpenAI의 스트리밍은 이벤트 타입이 명확한 **semantic events**로 흘러오고(예: `response.output_text.delta`)[^1], vLLM은 OpenAI 호환 HTTP 서버 형태로 띄워 로컬/자가호스팅 모델도 동일한 클라이언트 패턴으로 호출할 수 있습니다.[^2]

---

## 🔧 핵심 개념
### 1) FastAPI 스트리밍의 본질: “응답을 쪼개서 flush”
FastAPI의 `StreamingResponse`는 결과를 한 번에 만들지 않고 **async generator가 yield하는 조각(chunk)** 을 즉시 전송합니다. 이때 HTTP/1.1에서는 보통 **chunked transfer encoding**으로 동작하고, 연결을 유지한 채 계속 흘려보냅니다. (WebSocket 업그레이드가 필요 없음)

### 2) SSE vs NDJSON vs raw bytes — LLM에 SSE가 잘 맞는 이유
- **SSE**: `text/event-stream`으로 이벤트 단위 전송. 브라우저/프록시 친화적이고, “토큰 델타”처럼 작은 메시지를 자주 보내기 좋습니다.
- **NDJSON**: 줄 단위 JSON. 구현은 쉽지만 브라우저 기본 지원이 약하고, 이벤트 타입/재시도 같은 SSE의 관례가 없습니다.
- **raw bytes**: 가장 단순하지만, 구조(이벤트 타입/메타데이터)를 직접 설계해야 합니다.

LLM 스트리밍은 “텍스트 델타 + 라이프사이클 이벤트 + 에러”가 섞이므로, OpenAI도 **SSE 형태로 스트리밍 가이드**를 제공하고 이벤트 타입을 정의합니다.[^1]

### 3) 업스트림(OpenAI/vLLM) 스트림을 “중간 서버”가 망치는 지점
중간에 FastAPI를 두면 다음이 자주 깨집니다.

- **버퍼링**: Nginx/클라우드 LB/프록시가 응답을 버퍼링하면 “스트리밍인데 한 번에 옴”
- **백프레셔(backpressure)**: 클라이언트가 느리면 서버 메모리에 이벤트가 쌓임
- **cancel 전파**: 사용자가 탭을 닫아도 업스트림 LLM 호출이 계속 돈다면 비용/자원 낭비
- **keepalive**: 중간 장비가 idle connection으로 끊어버림 → 주기적 ping 필요

그래서 “스트리밍 구현”은 단순히 `yield` 하는 것보다, **헤더/타임아웃/취소 처리/핑**까지 포함한 운영 단위로 봐야 합니다. (실제로 이를 패키징한 SSE wrapper류도 등장했습니다.[^3])

---

## 💻 실전 코드
아래 예제는 “LLM 스트림(업스트림)을 받아서 → 우리 API에서 SSE로 재전송”하는 **프록시 패턴**입니다.  
(업스트림은 OpenAI Responses API 스트리밍 이벤트를 가정. 이벤트 타입 예시는 문서에 정의되어 있습니다.[^1])

```python
# app.py
import json
import os
import asyncio
from typing import AsyncIterator, Dict, Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from openai import OpenAI

app = FastAPI()
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def sse_event(data: Dict[str, Any], event: Optional[str] = None) -> str:
    """
    SSE 포맷:
      event: <name>\n
      data: <json>\n
      \n
    """
    payload = json.dumps(data, ensure_ascii=False)
    if event:
        return f"event: {event}\ndata: {payload}\n\n"
    return f"data: {payload}\n\n"

async def openai_stream(prompt: str) -> AsyncIterator[str]:
    """
    OpenAI Responses API의 stream=True는 'semantic events'를 순회합니다.
    여기서는 text delta만 골라서 전송하고, lifecycle도 함께 내보냅니다.
    """
    # SDK의 stream iterator는 sync로 제공되는 경우가 있어(버전에 따라)
    # thread로 감싸거나, 서버 구현에 맞게 조정이 필요할 수 있습니다.
    stream = client.responses.create(
        model="gpt-5",
        input=[{"role": "user", "content": prompt}],
        stream=True,
    )

    # 연결 유지용 ping (중간 프록시 idle timeout 방지)
    last_send = asyncio.get_event_loop().time()

    try:
        # response.created 같은 이벤트
        yield sse_event({"type": "proxy.started"}, event="lifecycle")

        for ev in stream:
            # ev.type 예: response.output_text.delta / response.completed / error ...
            ev_type = getattr(ev, "type", None)

            # 1) 텍스트 델타 이벤트만 클라이언트로 전달
            if ev_type == "response.output_text.delta":
                delta = getattr(ev, "delta", None) or getattr(ev, "text", None)
                if delta:
                    yield sse_event({"type": ev_type, "delta": delta}, event="delta")
                    last_send = asyncio.get_event_loop().time()

            # 2) 완료 이벤트 전달
            elif ev_type == "response.completed":
                yield sse_event({"type": ev_type}, event="lifecycle")
                break

            # 3) 에러 이벤트 전달
            elif ev_type == "error":
                yield sse_event({"type": "error", "detail": getattr(ev, "error", None)}, event="error")
                break

            # 4) keepalive: 10초 이상 전송 없으면 ping
            now = asyncio.get_event_loop().time()
            if now - last_send > 10:
                yield sse_event({"type": "ping"}, event="ping")
                last_send = now

    except asyncio.CancelledError:
        # 클라이언트가 연결을 끊으면(탭 닫기 등) 여기로 들어올 수 있음
        # 업스트림 취소 전파가 가능한 SDK/클라이언트라면 여기서 중단 처리.
        yield sse_event({"type": "proxy.cancelled"}, event="lifecycle")
        raise
    except Exception as e:
        yield sse_event({"type": "proxy.error", "message": str(e)}, event="error")

@app.get("/v1/chat/stream")
async def chat_stream(q: str, request: Request):
    async def generator():
        # 클라이언트 disconnect 감지: request.is_disconnected() 폴링
        # (더 정교하게 하려면 백그라운드 태스크/취소 전파 설계를 함께)
        stream_iter = openai_stream(q)
        async for chunk in stream_iter:
            if await request.is_disconnected():
                # 연결 끊김 → 더 이상 전송 중단
                break
            yield chunk

    headers = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        # Nginx reverse proxy 사용 시 버퍼링 방지에 도움
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(generator(), headers=headers)
```

핵심 포인트는 다음입니다.
- **SSE 포맷을 엄격히 지킴**(이벤트 경계는 `\n\n`)
- OpenAI 스트림에서 `response.output_text.delta` 같은 **델타 이벤트만 선별**[^1]
- **ping keepalive**로 중간 장비 idle timeout 완화
- `request.is_disconnected()`로 **disconnect를 감지**하고 스트림을 멈춤

---

## ⚡ 실전 팁
1) “스트리밍이 안 된다”의 80%는 프록시 버퍼링
- Nginx/Ingress가 응답을 모아서 보내면 SSE가 무력화됩니다.
- 서버에서 `X-Accel-Buffering: no`, `Cache-Control: no-transform`를 넣고,
- 인프라에서도 proxy buffering을 꺼야 합니다(환경별 설정 필요).

2) 이벤트 스키마를 “우리 서버 기준”으로 재정의하라
OpenAI는 semantic events로 굉장히 많은 타입(텍스트 델타, 툴 콜 델타, refusal 등)을 흘립니다.[^1]  
클라이언트가 필요한 건 보통:
- `delta`(텍스트)
- `lifecycle`(start/end)
- `error`
- (선택) `usage`

이므로 **내부 이벤트 → 외부 이벤트로 변환하는 thin mapping layer**를 두면, 업스트림이 OpenAI이든 vLLM이든 교체가 쉬워집니다. vLLM은 OpenAI 호환 서버로 띄우는 게 공식 가이드로 제공됩니다.[^2]

3) cancel 전파는 비용 최적화의 핵심
SSE에서 클라이언트가 끊기면 서버는 빠르게 감지하고:
- 업스트림 HTTP 요청을 취소(가능하면)
- 모델 생성 중단(자가 호스팅이면 엔진 cancel)
을 해야 GPU/토큰 비용을 줄입니다. “클라이언트 끊김 감지”만 있고 업스트림이 계속 돌면 반쪽짜리입니다.

4) keepalive ping은 “옵션”이 아니라 “운영 필수”
모바일 네트워크/LB는 가만히 있는 연결을 끊습니다. 토큰이 잠깐 안 나오는 구간(검색/툴 호출)에서도 **주기적 ping 이벤트**를 보내면 안정성이 올라갑니다. 프로덕션 지향 SSE wrapper들이 keepalive를 기능으로 강조하는 이유가 여기에 있습니다.[^3]

---

## 🚀 마무리
FastAPI로 LLM API 서버를 만들 때 스트리밍은 단순 기능이 아니라 **프로토콜(SSE) + 인프라(버퍼링) + 제어흐름(cancel/백프레셔) + UX(이벤트 스키마)**의 조합입니다.  
2026년 2월 기준으로는 OpenAI의 Responses API 스트리밍 이벤트(semantic events)를 이해하고[^1], FastAPI `StreamingResponse`로 SSE를 정확히 내보내며, 필요하면 vLLM 같은 OpenAI-compatible 서버로 동일 패턴을 확장하는 것이 가장 실용적인 아키텍처입니다.[^2]

다음 학습으로는:
- “툴 호출(function calling) 스트리밍”까지 포함해 이벤트를 어떻게 UI/상태머신으로 모델링할지
- Ray Serve LLM/vLLM 기반으로 autoscaling과 backpressure를 어떻게 걸지(대규모 트래픽)
를 추천합니다. (vLLM 문서에 Ray Serve LLM 언급도 포함됩니다.[^2])

[^1]: <https://platform.openai.com/docs/guides/streaming-responses>
[^2]: <https://docs.vllm.ai/en/latest/serving/openai_compatible_server/>
[^3]: <https://pypi.org/project/fastapi-sse-wrapper/>
