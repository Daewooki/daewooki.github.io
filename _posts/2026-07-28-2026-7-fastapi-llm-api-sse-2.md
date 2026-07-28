---
title: "2026년 7월 기준: FastAPI로 LLM API 서버 “진짜” 스트리밍(SSE) 구축하기 — 끊김/버퍼링/취소까지 엔드투엔드로 잡는 법"
date: 2026-07-28 03:19:37 +0900
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
LLM API 서버에서 “스트리밍”은 단순히 `yield`로 토큰을 흘려보내는 문제가 아닙니다. 실무에서는 다음이 같이 터집니다.

- **프록시/로드밸런서가 응답을 버퍼링**해서 사용자는 “한참 뒤에 한 번에” 받음 (스트리밍 망함)
- **클라이언트가 탭을 닫았는데도** 서버는 LLM 호출을 계속 돌려 비용이 새나감 (취소/cleanup 실패)
- **동시 접속이 늘면** worker/connection이 잠기고 tail latency가 폭증 (SSE는 “연결을 오래 잡는” 모델)
- **관측/재시도/에러 모델**이 없어서 운영 중 디버깅이 불가능

2026년 7월 기준으로는, 브라우저 호환성과 운영 난이도를 감안하면 **SSE(Server-Sent Events)** 가 “LLM 텍스트 스트리밍”의 기본 선택지가 되는 경우가 많습니다(특히 OpenAI류 API처럼 토큰/델타 이벤트를 흘리고 싶을 때). FastAPI 공식 문서도 SSE 튜토리얼을 제공하고, Nginx 버퍼링 방지 헤더(`X-Accel-Buffering: no`) 같은 실전 포인트를 명시합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))

**언제 쓰면 좋은가**
- 브라우저/모바일에서 **실시간 생성 UX**(typing effect, 부분 결과 표시)가 필요
- **단방향 스트림**(서버→클라)만 필요하고, 클라는 요청 1번 + 응답 스트림 1번이면 충분
- 운영 상 WebSocket보다 단순한 네트워크/보안 정책을 원함(HTTP 기반)

**언제 쓰면 안 되는가**
- 클라이언트→서버로도 지속적으로 메시지를 주고받는 **양방향 상호작용**(툴 호출 승인, 멀티턴 협상 등)이 핵심이면 WebSocket이 더 자연스러움
- “연결을 오래 잡는” 특성상, **초고동시성**에서 커넥션 수/메모리/FD 한계가 먼저 오면 별도 스트리밍 게이트웨이/전용 서빙 계층을 고려해야 함

---

## 🔧 핵심 개념
### 1) SSE vs 일반 StreamingResponse: “프레이밍”이 핵심
FastAPI의 `StreamingResponse`는 바이트 청크를 그대로 흘려보내는 저수준 도구입니다. FastAPI 문서도 “그대로 chunk를 전달하며 JSON 변환 같은 건 안 한다”고 명시합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/advanced/stream-data/?utm_source=openai))  
하지만 LLM 스트리밍에서 클라이언트가 기대하는 건 대개 **이벤트 프레이밍**입니다.

- SSE는 `text/event-stream` 포맷으로
  - `event: <type>`
  - `data: <payload>`
  - 빈 줄로 이벤트 경계
- 브라우저 `EventSource`/각종 SDK가 이 포맷을 자동 처리

FastAPI SSE 튜토리얼은 `EventSourceResponse`를 사용해 `yield`로 이벤트를 내보내는 패턴을 안내합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))  
(현장에서 “StreamingResponse로 SSE 흉내”를 내면, keep-alive/ping, disconnect 처리, 포맷 경계에서 사고가 자주 납니다.)

### 2) “진짜 스트리밍”을 망치는 1순위: 프록시 버퍼링
Uvicorn 자체는 ASGI `send`에서 **write buffer의 high/low water mark 기반 흐름 제어**를 하며, 무한정 메모리에 쌓지 않도록 설계되어 있습니다. ([uvicorn.org](https://www.uvicorn.org/server-behavior/?utm_source=openai))  
그런데 앞단에 Nginx 같은 프록시가 있으면 이야기가 달라집니다. Uvicorn 배포 문서 예시에서도 `proxy_buffering off;`를 넣는 구성이 등장합니다. ([uvicorn.org](https://www.uvicorn.org/deployment/?utm_source=openai))  
FastAPI SSE 튜토리얼은 특히 **`X-Accel-Buffering: no` 헤더**를 언급하며, 일부 프록시에서 버퍼링을 끄지 않으면 SSE가 “중간중간 안 나오고” 뭉쳐 나온다고 짚습니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))

즉, 스트리밍 품질은 “앱 코드”만이 아니라 **(클라)–(CDN/LB)–(Nginx)–(ASGI서버)** 전체 체인의 합성 결과입니다.

### 3) 취소(Cancellation)는 비용 최적화이자 안정성 기능
LLM 스트리밍은 대개 “서버가 모델 제공자(OpenAI 등)로부터 SSE를 받아서, 다시 클라이언트에 SSE로 중계”합니다. 이때 사용자가 중간에 끊으면:
- **업스트림 LLM 호출을 즉시 중단**해야 비용과 자원을 절약
- 서버는 **연결 종료 시그널**을 감지하고, 태스크/소켓/큐를 정리해야 함

AnyIO의 `CancelScope` 같은 취소 메커니즘은 FastAPI/Starlette 생태계에서 매우 중요합니다. ([anyio.readthedocs.io](https://anyio.readthedocs.io/en/stable/api.html?utm_source=openai))  
또 Starlette는 sync 코드를 thread pool로 돌리는데, 이 풀은 FastAPI 의존성 처리와도 공유되어 병목이 될 수 있어(스트리밍 중 실수로 blocking 호출을 넣는 순간) 전체 서비스가 느려질 수 있습니다. ([starlette.dev](https://starlette.dev/threadpool/?utm_source=openai))

### 4) 업스트림(OpenAI) 스트리밍 이벤트 모델을 그대로 “중계”할지, “내 도메인 이벤트”로 재정의할지
OpenAI Python SDK는 2026년 7월에도 SSE 기반 스트리밍을 지원하고, 이벤트를 순회(iteration)하는 형태를 제공합니다. ([github.com](https://github.com/openai/openai-python?utm_source=openai))  
여기서 실무 판단 포인트는:

- **그대로 패스스루**: 구현이 빠르나, 클라/서버 버전 결합도가 커지고 이벤트 스키마 변경 영향이 큼
- **내 이벤트로 추상화**: 프런트/모바일에 “진짜 필요한 최소 이벤트(델타/최종/에러/메타)”만 제공 → 장기 운영에 유리

---

## 💻 실전 코드
요구사항을 “현실적으로” 잡아보겠습니다.

- FastAPI로 `/v1/chat/stream` SSE 엔드포인트 제공
- 업스트림은 OpenAI Responses API를 `stream=True`로 호출해 이벤트를 받음 ([github.com](https://github.com/openai/openai-python?utm_source=openai))
- 서버는 이벤트를 **SSE로 재포장**해서 전송
- 클라이언트 disconnect 시 업스트림 스트림을 닫고 정리
- Nginx 뒤에서도 스트리밍이 깨지지 않게 헤더/설정 포함

### 1) 설치/실행
```bash
python -m venv .venv
source .venv/bin/activate

pip install "fastapi>=0.110" "uvicorn[standard]" openai
# SSE를 안정적으로 처리하려면 sse-starlette도 많이 씁니다.
pip install sse-starlette
```

### 2) 서버 코드 (FastAPI + OpenAI 스트리밍 중계)
```python
# app.py
import json
import os
from typing import AsyncIterator, Dict, Any

from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse

from openai import AsyncOpenAI

app = FastAPI()
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def sse_event(event: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    sse-starlette는 dict 형태로 event/data를 받습니다.
    data는 문자열이 안전하므로 JSON serialize해서 보냅니다.
    """
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


@app.post("/v1/chat/stream")
async def chat_stream(request: Request):
    body = await request.json()
    user_text = body["input"]
    model = body.get("model", "gpt-5.5")

    async def event_iter() -> AsyncIterator[Dict[str, Any]]:
        # 1) 프록시 버퍼링/타임아웃 환경에서 연결 유지용 ping 이벤트를
        #    주기적으로 보내고 싶다면(예: 15s) 별도 태스크가 필요합니다.
        #    여기서는 단순화를 위해 업스트림 이벤트만 중계합니다.

        try:
            # 2) 업스트림 스트리밍 시작 (OpenAI Python SDK의 SSE 스트림)
            stream = await client.responses.create(
                model=model,
                input=user_text,
                stream=True,
            )

            # 3) 초기 메타 이벤트(내 도메인 이벤트)
            yield sse_event("server.meta", {"model": model})

            async for evt in stream:
                # evt는 SDK 이벤트 오브젝트(또는 dict 유사)입니다.
                # 여기서 "중요 이벤트만" 선별해서 내려보내는 것이 운영에 유리합니다.
                t = getattr(evt, "type", None) or evt.get("type")

                # OpenAI 스트리밍 이벤트 중 텍스트 델타를 중계
                if t == "response.output_text.delta":
                    delta = evt.delta if hasattr(evt, "delta") else evt.get("delta")
                    if delta:
                        yield sse_event("token", {"delta": delta})

                elif t == "response.completed":
                    # 최종 결과(서버가 조립한 완성 텍스트)를 함께 주면 클라가 단순해집니다.
                    yield sse_event("done", {"ok": True})
                    break

                elif t in ("response.failed", "response.incomplete"):
                    yield sse_event("error", {"type": t})
                    break

            # 4) 스트림 종료 신호
            yield sse_event("eos", {"closed": True})

        except Exception as e:
            # 예외는 반드시 SSE error 이벤트로 전환 (프런트에서 표준 처리)
            yield sse_event("error", {"message": str(e)})

    # SSE 핵심 헤더: 일부 프록시에서 버퍼링 방지
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # Nginx 버퍼링 방지(중요) ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))
    }

    return EventSourceResponse(event_iter(), headers=headers)
```

**예상 동작**
- 클라이언트는 `event: token`으로 델타를 계속 받다가
- `event: done` → `event: eos`로 종료

### 3) Nginx (또는 프록시) 설정 포인트
Uvicorn 배포 문서 예시처럼, Nginx를 쓴다면 `proxy_buffering off;`가 스트리밍에 결정적입니다. ([uvicorn.org](https://www.uvicorn.org/deployment/?utm_source=openai))

```nginx
location / {
  proxy_set_header Host $http_host;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;

  proxy_http_version 1.1;
  proxy_buffering off;          # 스트리밍 필수 ([uvicorn.org](https://www.uvicorn.org/deployment/?utm_source=openai))
  proxy_read_timeout 3600s;     # 장시간 스트림이면 늘려야 함
  proxy_send_timeout 3600s;

  proxy_pass http://uvicorn;
}
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “이벤트 스키마를 내가 소유”하라
OpenAI 이벤트 타입이 풍부하지만(예: `response.output_text.delta` 등) ([fastapi.ai](https://www.fastapi.ai/api/response/streaming.html?utm_source=openai))  
클라이언트가 정말 필요한 건 보통:
- `token` (delta)
- `done` (완료)
- `error` (표준 에러)
- `meta` (model, request_id 등)

서버에서 한 번 추상화하면, 제공자 교체/버전 변경에도 프런트를 안정적으로 유지할 수 있습니다.

### Best Practice 2) disconnect/취소를 “명시적으로” 다뤄라
SSE는 사용자가 탭을 닫으면 조용히 끊깁니다. 이때 업스트림 스트리밍을 멈추지 않으면 비용이 계속 나갑니다.  
구현 방법은 여러 가지인데, 핵심은:
- **request disconnect 감지**(ASGI disconnect)
- **업스트림 스트림 close + 태스크 취소**
- finally에서 **큐/채널/파일 핸들 정리**

AnyIO 기반 취소 모델을 이해하고(예: `CancelScope`) ([anyio.readthedocs.io](https://anyio.readthedocs.io/en/stable/api.html?utm_source=openai))  
“예외가 나도 항상 정리되는 구조”로 짜는 게 중요합니다.

### Best Practice 3) “버퍼링 끄기”는 앱/프록시 둘 다 설정
- 앱: `X-Accel-Buffering: no` ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))
- 프록시: `proxy_buffering off` ([uvicorn.org](https://www.uvicorn.org/deployment/?utm_source=openai))

둘 중 하나만 해도 환경에 따라 실패합니다(특히 CDN/LB를 하나 더 끼면 더 복잡해짐).

### 흔한 함정 1) 스트리밍 중 sync/blocking 코드 호출
Starlette는 sync 코드를 thread pool로 돌립니다. ([starlette.dev](https://starlette.dev/threadpool/?utm_source=openai))  
스트리밍 경로에서 실수로 blocking I/O(파일, DB, requests)를 호출하면:
- thread pool 고갈
- 다른 요청(심지어 비스트리밍 요청)도 같이 느려짐

해결:
- 스트리밍 경로는 **끝까지 async**로 유지
- DB도 async driver 사용, 외부 HTTP도 `httpx.AsyncClient` 등 사용
- 불가피하면 **전용 worker/서비스로 분리**

### 흔한 함정 2) BackgroundTasks로 “응답 중” 이벤트를 보내려는 시도
FastAPI/Starlette의 `BackgroundTasks`는 **응답이 끝난 뒤** 실행됩니다. 그래서 SSE로 진행 상황을 계속 보내려는 용도와 맞지 않습니다(운영에서 자주 삽질 포인트).  
대신:
- SSE generator 내부에서 직접 진행 이벤트를 `yield`
- 또는 큐(메모리/Redis)를 두고 generator가 구독하도록 설계

### 비용/성능/안정성 트레이드오프
- **SSE는 연결을 오래 점유**하므로, QPS보다 “동시 연결 수”가 먼저 한계가 됩니다.
- 워커 수를 늘려도 “커넥션 수/FD/메모리” 병목이 남습니다.
- 대규모로 가면:
  - 스트리밍 전용 게이트웨이(Go/Node)로 분리
  - 모델 호출은 백엔드 작업 큐로 넘기고 SSE는 결과 중계에 집중
  - 또는 WebSocket/HTTP3 등 대안 검토

---

## 🚀 마무리
핵심은 3가지입니다.

1) LLM 스트리밍은 **SSE 프레이밍 + 프록시 버퍼링 제어**가 절반입니다. (`X-Accel-Buffering: no`, `proxy_buffering off`) ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))  
2) “스트리밍 중계 서버”는 **취소/정리**가 비용과 안정성의 핵심이고, AnyIO/ASGI 취소 흐름을 전제로 설계해야 합니다. ([anyio.readthedocs.io](https://anyio.readthedocs.io/en/stable/api.html?utm_source=openai))  
3) 제공자 이벤트를 그대로 노출하기보다, **내 서비스 이벤트 스키마를 소유**하면 장기 운영이 쉬워집니다(OpenAI SDK의 스트리밍 이벤트를 선별/재포장). ([github.com](https://github.com/openai/openai-python?utm_source=openai))

**도입 판단 기준**
- 브라우저 기반 실시간 생성 UX가 필요하고, 단방향이면 → **SSE 추천**
- 양방향 상호작용/빈번한 클라 메시지가 핵심이면 → WebSocket 우선 검토
- 프록시 체인이 복잡하거나(CloudFront/API Gateway 등), SRE 리소스가 부족하면 → “스트리밍 품질” 운영이 생각보다 비쌉니다. 먼저 PoC로 **실제 프로덕션 경로에서** 토큰이 200~500ms 단위로 내려오는지 검증하세요.

**다음 학습 추천**
- FastAPI SSE 튜토리얼(헤더/프록시 버퍼링 포인트 포함) ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/tutorial/server-sent-events/?utm_source=openai))  
- Uvicorn의 flow control/버퍼 동작 이해(스트리밍 메모리/역압) ([uvicorn.org](https://www.uvicorn.org/server-behavior/?utm_source=openai))  
- OpenAI Python SDK 스트리밍 이벤트 모델 파악(어떤 이벤트를 중계할지 결정) ([github.com](https://github.com/openai/openai-python?utm_source=openai))  

원하면, 위 예제를 **(1) Redis pub/sub로 멀티워커 SSE 브로드캐스트**, **(2) 클라이언트 재연결(Last-Event-ID) + 서버 측 재전송**, **(3) OpenTelemetry로 토큰 지연/끊김 구간 계측**까지 확장한 “운영형 템플릿”으로도 이어서 작성해드릴게요.