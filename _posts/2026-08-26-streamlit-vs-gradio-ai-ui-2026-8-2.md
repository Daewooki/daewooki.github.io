---
title: "Streamlit vs Gradio로 “당일” AI 데모 UI를 출고하는 법 (2026년 8월 기준): 성능·상태·배포까지 실전 심층 분석"
date: 2026-08-26 01:47:52 +0900
categories: [AI, Prototyping]
tags: [ai, prototyping, trend, 2026-08]
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

AI 모델을 “작동하는 코드”에서 “사람이 써볼 수 있는 제품 느낌의 데모”로 바꾸는 데 가장 많이 깨지는 지점은 UI 자체가 아니라 **동시성, 상태(State), 캐시, 배포 단위**입니다. 2026년 8월 기준으로 빠른 데모 UI를 만들 때 Streamlit과 Gradio는 여전히 양대 선택지이고, 둘 다 “파이썬만으로 UI를 만든다”는 공통점 때문에 겉보기엔 비슷하지만 **실제 운영/확장 방식은 꽤 다르게 설계**돼 있습니다.

- **언제 Streamlit이 좋은가**
  - 모델 데모가 “앱”처럼 커질 가능성이 높고(페이지/필터/리포트/어드민), **데이터 앱 + AI** 형태로 확장될 때
  - 세션 기반 UI에서 **상태를 정교하게** 다루면서(사용자별 설정/히스토리), 캐시를 통해 비용을 줄여야 할 때
  - 2026년 8월 릴리즈 기준, Streamlit이 **Starlette/Uvicorn 기반으로 전환되어 ASGI 생태계와의 궁합/성능 측면 이점**을 노릴 때 ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026?utm_source=openai))

- **언제 Gradio가 좋은가**
  - “모델 한두 개를 사람들이 바로 테스트”하는 형태(텍스트/이미지/오디오/챗봇)로 **최단 시간 데모**가 목표일 때
  - **Queue(대기열) + Streaming**을 기본 전제로 두고, 폭주/동시 접속을 UI 레벨에서 흡수해야 할 때 ([gradio.app](https://gradio.app/guides/queuing?utm_source=openai))
  - 기존 FastAPI 서비스에 **UI를 마운트**해서 운영하고 싶을 때(인증/로깅/레이트리밋을 기존 스택에 편입) ([gradio.app](https://gradio.app/docs/gradio/mount_gradio_app?utm_source=openai))

- **언제 둘 다 피하는 게 좋은가**
  - “UI”보다 “정식 제품 프론트엔드(React/Next.js)”가 핵심이고, 디자인 시스템/접근성/정교한 라우팅이 중요한 경우
  - 멀티 테넌트 SaaS로 가는 로드맵이 확실한데, 초기부터 UI를 프레임워크에 강하게 의존해 **나중에 갈아엎는 비용**이 더 커질 때

---

## 🔧 핵심 개념

### 1) 실행 모델(Execution Model): “리런” vs “이벤트”

**Streamlit: 스크립트 리런 기반**
- 사용자의 입력(위젯 변경 등)이 발생하면, 앱은 **위에서 아래로 스크립트를 다시 실행**하는 모델입니다.
- 상태는 `st.session_state`에 유지되고, “비싼 연산”은 캐시로 고정합니다.
- 캐시는 크게 두 층:
  - `st.cache_data`: “데이터 결과” 캐시(복사본 반환 성격)  
  - `st.cache_resource`: “모델/DB 커넥션 같은 리소스” 캐시(언직렬화 어려운 객체 포함) ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching?utm_source=openai))  
- 즉, **UI는 매번 재계산되지만, 비용이 큰 부분만 고정**하는 방식으로 설계를 유도합니다.

**Gradio: 이벤트 핸들러 기반**
- 버튼 클릭/텍스트 입력 등 이벤트마다 **등록된 함수(fn)가 호출**되고, 결과가 컴포넌트에 반영됩니다.
- 중요한 차이: Gradio는 무거운 작업이 많다는 전제를 깔고 **Queue를 자동으로 두는 구조**가 강합니다. `Blocks.queue()`로 동시 처리량/대기열 정책을 조절합니다. ([gradio.app](https://gradio.app/guides/queuing?utm_source=openai))

### 2) 동시성/폭주 대응: 캐시 vs 큐

- Streamlit에서 가장 흔한 병목은 “모델 로드/임베딩 생성/벡터 검색/LLM 호출”이 리런 사이클에 섞일 때입니다. 이때 `st.cache_resource`로 **모델/클라이언트 단을 고정**하고, `st.cache_data`로 **정적 데이터(예: 문서 청크, 인덱스 메타)**를 고정하면 비용이 급감합니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource?utm_source=openai))
- Gradio는 폭주를 “기본값으로 발생할 수 있다”고 보고, Queue로 **대기열 + 동시 실행 제한**을 제공합니다. `default_concurrency_limit` 같은 파라미터로 처리량/대기 UX를 통제합니다. ([gradio.app](https://gradio.app/guides/queuing?utm_source=openai))

### 3) 운영 아키텍처: “UI 단독 배포” vs “서비스에 UI를 합류”

- Streamlit은 보통 “UI 서버”로 단독 배포하기 쉽고, 데이터 앱처럼 확장하기 좋습니다. 2026년 8월 릴리즈 노트에 따르면 내부 서버가 **Starlette/Uvicorn 기반**으로 바뀌어 ASGI 친화성이 좋아진 방향성이 보입니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026?utm_source=openai))
- Gradio는 FastAPI에 `mount_gradio_app()`로 **기존 서비스에 UI를 경로로 붙이는 패턴**이 공식 문서로 정리돼 있습니다. ([gradio.app](https://gradio.app/docs/gradio/mount_gradio_app?utm_source=openai))  
  이 방식이 실무적으로 좋은 이유는 인증(OAuth2-proxy), 관측(로그/트레이싱), 레이트리밋을 **UI에도 동일하게 적용**하기 쉽기 때문입니다.

---

## 💻 실전 코드

현실적인 시나리오: “사내 문서 RAG + 스트리밍 챗 UI + 운영 친화적 배포”  
- 백엔드: FastAPI (기존 서비스)
- UI: Gradio (빠른 데모 + Queue/Streaming)
- 캐시: 프로세스 내 모델/클라이언트는 1회 로드
- 목적: **‘그럴듯한 데모’가 아니라 운영으로 가져갈 수 있는 형태** (API + UI 공존)

### 0) 의존성 / 실행

```bash
python -m venv .venv
source .venv/bin/activate

pip install fastapi uvicorn gradio httpx pydantic
uvicorn app:app --host 0.0.0.0 --port 8000
# 브라우저에서:
# - http://localhost:8000/gradio  (UI)
# - http://localhost:8000/docs    (API 문서)
```

### 1) 초기 셋업: “하나의 모델/클라이언트”를 API와 UI가 공유

아래 예제는 외부 LLM을 직접 호출한다고 가정하고(여기서는 `httpx`로 “LLM Gateway”를 호출하는 형태), **모델 클라이언트는 프로세스에서 한 번만 생성**합니다. 또한 Gradio는 `queue()`를 걸어 폭주를 통제합니다. ([gradio.app](https://gradio.app/guides/queuing?utm_source=openai))

```python
# app.py
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import gradio as gr
from gradio import mount_gradio_app

# ---- "리소스"는 프로세스에 1회 로드 (모델/클라이언트/벡터DB 핸들 등) ----
class LLMGatewayClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=60.0)

    def chat(self, messages: list[dict], stream: bool = False):
        """
        실제론 OpenAI/Claude/사내 Gateway에 맞게 변경.
        여기서는 예시로 /chat 엔드포인트를 호출한다고 가정.
        """
        resp = self._client.post(
            f"{self.base_url}/chat",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"messages": messages, "stream": stream},
        )
        resp.raise_for_status()
        return resp.json()

# 실무 포인트: 프로세스 재시작 전까지 재사용
llm = LLMGatewayClient(base_url="https://llm-gateway.company.internal", api_key="REDACTED")

# ---- FastAPI (기존 서비스) ----
app = FastAPI(title="RAG Demo Service")

class ChatRequest(BaseModel):
    user_id: str
    question: str

@app.post("/api/chat")
def api_chat(body: ChatRequest):
    # RAG 파이프라인(검색→컨텍스트 구성→LLM 호출)이 여기에 온다고 생각하면 됨.
    messages = [
        {"role": "system", "content": "You are a helpful assistant for internal docs."},
        {"role": "user", "content": body.question},
    ]
    result = llm.chat(messages, stream=False)
    return {"answer": result.get("answer", result), "user_id": body.user_id}

# ---- Gradio UI (빠른 데모) ----
def ui_chat(message: str, history: list[list[str]]):
    """
    history: [[user, assistant], ...]
    Gradio Chatbot의 메시지 포맷/컴포넌트는 문서에서 안내하는 포맷을 따르는 게 안전. ([gradio.app](https://gradio.app/main/docs/gradio/chatbot?utm_source=openai))
    """
    # history를 LLM messages로 변환 (실무에선 tool calls, citations 등 추가)
    messages = [{"role": "system", "content": "You are a helpful assistant for internal docs."}]
    for u, a in history:
        messages.append({"role": "user", "content": u})
        messages.append({"role": "assistant", "content": a})
    messages.append({"role": "user", "content": message})

    result = llm.chat(messages, stream=False)
    answer = result.get("answer", str(result))
    history = history + [[message, answer]]
    return history

with gr.Blocks(title="Internal RAG Demo") as demo:
    gr.Markdown("### Internal Docs RAG Demo (FastAPI + Gradio)")
    chatbot = gr.Chatbot(height=520)
    msg = gr.Textbox(placeholder="질문을 입력하세요 (예: 배포 정책에서 staging 승인 조건은?)")
    send = gr.Button("Send")

    send.click(fn=ui_chat, inputs=[msg, chatbot], outputs=[chatbot])
    msg.submit(fn=ui_chat, inputs=[msg, chatbot], outputs=[chatbot])

# Queue로 폭주/동시성 제어 (실무에서 가장 먼저 켜는 옵션 중 하나)
demo = demo.queue(default_concurrency_limit=8)

app = mount_gradio_app(app, demo, path="/gradio")
```

### 2) 확장: “운영 관점”에서 UI를 서비스에 붙이는 이유

- `/api/chat`은 **프로덕션 통합**(다른 서비스/봇/배치) 경로
- `/gradio`는 **사람이 체험**하는 경로
- 둘이 같은 프로세스/클라이언트를 공유하니
  - 모델/커넥션 생성 비용을 중복으로 내지 않고
  - 인증/관측/레이트리밋을 FastAPI 레이어에서 일원화할 수 있습니다.
- 공식적으로도 Gradio는 FastAPI에 마운트하는 함수를 제공하고, 어떤 페이지를 노출할지 옵션이 있습니다. ([gradio.app](https://gradio.app/docs/gradio/mount_gradio_app?utm_source=openai))

(참고) Streamlit로 같은 걸 만들 경우엔 “UI 앱 단독”이 쉬운 대신, 기존 FastAPI에 “같은 방식으로 자연스럽게 합류”시키는 건 접근이 달라집니다. 2026년 8월 기준 Streamlit이 ASGI 친화 방향으로 움직인 점은 주목할 만하지만, 여전히 **합류 방식은 Gradio가 더 직관적**인 편입니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026?utm_source=openai))

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) “리소스 캐시/공유”를 먼저 설계하라
- Streamlit이면 **모델/DB 커넥션은 `st.cache_resource`**, 정적 데이터는 `st.cache_data`로 분리합니다. 잘못 섞으면 리런마다 비용이 터집니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource?utm_source=openai))
- Gradio/FastAPI 합류 패턴이면, 위 코드처럼 **프로세스 전역에서 모델/클라이언트를 1회 로드**하고 UI/API가 공유하게 만드세요.

### Best Practice 2) 동시성은 “성능 튜닝”이 아니라 “안정성 기능”
- Gradio는 Queue를 통해 이벤트 처리량을 통제할 수 있고, `default_concurrency_limit`로 “서버가 버틸 수 있는 만큼만” 동시에 처리하게 만들 수 있습니다. ([gradio.app](https://gradio.app/guides/queuing?utm_source=openai))
- 함정: 동시성 제한을 너무 낮추면 대기열이 길어지고 UX가 망합니다. 너무 높이면 LLM 호출/벡터DB/CPU가 같이 터집니다. **서버 리소스(특히 GPU 메모리/스레드풀/외부 API rate limit)** 기준으로 산정하세요.

### Best Practice 3) 배포 플랫폼의 “큐/빌드”도 병목이 된다
- 특히 Hugging Face Spaces 같은 곳은 빌드 큐가 길어지는 케이스가 실제로 보고됩니다(“Build Queued/Building” 이슈). 데모를 빨리 공개해야 하는데 플랫폼 큐 때문에 막히면 일정이 깨집니다. ([reddit.com](https://www.reddit.com/r/huggingface/comments/1uyqv1k/build_queued/?utm_source=openai))  
- 대응: 중요한 데모는 Docker+자체 배포(또는 사내 클러스터)로 “탈출 경로”를 확보하고, Spaces는 홍보/공개용 2차 채널로 두는 게 안전합니다.

### 흔한 함정/안티패턴
- Streamlit에서 “모델 로드”를 캐시 없이 상단에 두고, 위젯 변화마다 리런되어 **매번 모델을 다시 만드는** 패턴
- Gradio에서 Queue를 켰지만, 내부 함수가 블로킹 I/O(외부 API) + 긴 타임아웃으로 묶여 있어 **대기열이 눈덩이처럼 불어나는** 패턴
- UI만 먼저 만들고, 나중에 API를 붙이려다 **관측/인증/레이트리밋 정책이 UI와 API에 이중으로 생기는** 패턴 → 처음부터 “API + UI 공존” 설계가 장기적으로 싸게 먹힙니다.

### 비용/성능/안정성 트레이드오프(결정 기준)
- **최단 시간 공개**: Gradio 단독(또는 Spaces) + Queue 기본값 → 단, 플랫폼 의존 리스크 ([gradio.app](https://gradio.app/guides/queuing?utm_source=openai))
- **사내 운영/확장**: FastAPI + Gradio mount(인증/관측 일원화) ([gradio.app](https://gradio.app/docs/gradio/mount_gradio_app?utm_source=openai))
- **데이터 앱으로 커질 것**: Streamlit(캐시/세션 기반으로 점진 확장) + 2026년 8월 ASGI 방향성 체크 ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026?utm_source=openai))

---

## 🚀 마무리

2026년 8월 기준 “빠른 AI 데모 UI”의 실전 의사결정은 UI 컴포넌트 예쁨이 아니라 **실행 모델(리런 vs 이벤트), 캐시/큐 전략, 배포 결합 방식**에서 갈립니다.

- **Gradio를 고르세요** if: 단기간 공개, Queue/Streaming 중심 UX, FastAPI에 UI를 붙여 운영하고 싶다. ([gradio.app](https://gradio.app/guides/queuing?utm_source=openai))  
- **Streamlit을 고르세요** if: 데모가 데이터 앱으로 진화할 확률이 높고, 세션/캐시로 비용을 통제하며 기능을 붙일 계획이다. (특히 `st.cache_resource`/`st.cache_data`의 역할 분리가 핵심) ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource?utm_source=openai))  
- **둘 다 경계하세요** if: 처음부터 정식 프론트엔드가 필요하고 장기적으로 UI/디자인 시스템 요구가 강하다.

다음 학습 추천(실무 우선순위):
1) Streamlit 캐시 설계: `st.cache_data` vs `st.cache_resource` 구분과 TTL/갱신 전략 ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching?utm_source=openai))  
2) Gradio Queue/동시성: `Blocks.queue(default_concurrency_limit=...)`로 서버가 버틸 수 있는 처리량 모델링 ([gradio.app](https://gradio.app/guides/queuing?utm_source=openai))  
3) Gradio의 FastAPI 마운트로 “API+UI 단일 배포” 구성 ([gradio.app](https://gradio.app/docs/gradio/mount_gradio_app?utm_source=openai))  

원하면, 당신의 전제(모델 종류: 로컬 GPU vs 외부 API, 예상 동시 사용자 수, 배포 환경: k8s/VM/Spaces)에 맞춰 **Streamlit 설계안 1개 + Gradio 설계안 1개**를 “비용/리스크 표”로 비교해서 의사결정 문서 형태로 정리해줄 수 있습니다.