---
title: "Streamlit vs Gradio로 “이번 주 안에” AI 데모 UI 뽑아내는 법 (2026년 6월 기준 심층 가이드)"
date: 2026-06-21 05:04:45 +0900
categories: [AI, Prototyping]
tags: [ai, prototyping, trend, 2026-06]
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
LLM/RAG/멀티모달 같은 AI 기능은 “모델 성능”만큼이나 **데모 UX**가 성패를 가릅니다. 문제는 대부분의 팀이 (1) 백엔드는 FastAPI로 잘 만들었는데 (2) 프론트는 리소스가 없고 (3) PM/세일즈/내부검증을 위해 **빠르게 클릭 가능한 UI**가 필요하다는 점입니다. 이때 선택지가 Streamlit/Gradio로 수렴합니다.

- **언제 Streamlit이 좋은가**
  - 데이터/운영 관점의 “앱”에 가깝다: 실험 결과 테이블, 관측/모니터링, 설정 화면, 멀티페이지 내비게이션이 필요할 때(예: 관리자용 콘솔). Streamlit의 multipage(`st.Page`, `st.navigation`) 흐름이 “작은 제품”으로 확장하기 좋습니다. ([docs.streamlit.io](https://docs.streamlit.io/get-started/fundamentals/additional-features?utm_source=openai))
  - 스크립트 rerun 모델을 이해하고, 캐시/상태로 성능을 다룰 수 있을 때. 특히 모델/클라이언트는 `st.cache_resource`, 데이터는 `st.cache_data`로 분리 캐싱하는 패턴이 사실상 필수입니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching?utm_source=openai))

- **언제 Gradio가 좋은가**
  - “모델 함수”를 감싸서 바로 공개 가능한 **ML 데모**가 목표일 때: Blocks/ChatInterface로 입력→추론→출력을 직관적으로 엮고, queue/streaming으로 동시성/스트리밍 UX까지 빠르게 가져갈 수 있습니다. ([gradio.app](https://gradio.app/docs/gradio/blocks?utm_source=openai))
  - Hugging Face Spaces에서 데모/공유가 중요한 경우: Gradio Space는 API endpoint로도 바로 노출되어(“Use via API”) 데모를 곧바로 통합 테스트에 활용하기 쉽습니다. ([huggingface.co](https://huggingface.co/docs/hub/en/spaces-api-endpoints?utm_source=openai))

- **언제 둘 다 피하고, 웹 프레임워크로 가야 하나**
  - 사용자 수/트래픽이 확실히 커지고, 화면 상호작용이 복잡해 “부분 업데이트”, “비동기”, “세밀한 상태 관리”가 핵심이 되는 순간입니다. Streamlit은 기본적으로 스크립트 rerun 모델이라(최근 fragments로 개선됐지만) 앱이 커지면 구조적 병목이 옵니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/fragments?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Streamlit의 실행 모델: “상태를 가진 스크립트 rerun”
Streamlit은 이벤트가 발생할 때(위젯 변경 등) **스크립트를 위에서 아래로 다시 실행**하는 모델입니다. 따라서 “UI는 선언적”이지만, 내부는 **재실행(re-execution)**이 기본 전제입니다. 여기서 실무 핵심은:

- **`st.cache_resource`**: 모델/클라이언트/DB connection처럼 “프로세스에 붙어있는 리소스”를 세션 간 재사용하는 캐시
- **`st.cache_data`**: 요청 결과/전처리 결과 같은 “직렬화 가능한 데이터” 캐시  
→ 모델을 매번 로드하거나 API client를 매번 만들면, 데모가 아니라 “로딩 화면”이 됩니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching?utm_source=openai))

#### Fragments: rerun의 단점을 “부분 rerun”으로 완화
Streamlit 1.37.0에서 도입된 `st.fragment`는 **앱 전체 rerun 대신, 특정 함수만 독립 rerun**시킵니다. 특히 `run_every`로 폴링 UI(예: 백엔드 job 상태)를 만들 수 있어, “데모에서 흔한 진행 상태/로그 스트리밍 흉내”에 유용합니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/fragments?utm_source=openai))

### 2) Gradio의 모델: “이벤트 기반 + queue 중심”
Gradio Blocks는 UI 컴포넌트와 이벤트를 연결합니다. 버튼 클릭/텍스트 submit 같은 이벤트가 **함수 호출**로 이어지고, `.then()`으로 후속 이벤트를 체이닝할 수 있습니다. ([gradio.app](https://gradio.app/guides/blocks-and-event-listeners?utm_source=openai))

그리고 실무에서 가장 체감이 큰 건 queue입니다.

- `.queue()`를 켜면 요청이 **작업 큐**로 들어가고, 동시성 제한/대기열/timeout을 관리할 수 있습니다.
- 기본 동시성 제한은 환경변수 `GRADIO_DEFAULT_CONCURRENCY_LIMIT`로도 제어 가능합니다. ([gradio.app](https://gradio.app/main/docs/gradio/interface?utm_source=openai))

즉 Gradio는 “추론 함수 호출”을 안전하게 감싸는 데 강하고, Streamlit은 “앱 구조/데이터 흐름”을 만들어가는 데 강합니다.

### 3) 배포/공유 관점: Spaces의 현실(2026)
Hugging Face Spaces는 Streamlit/Gradio/Docker/Static 모두 지원하지만, 최근 changelog에서 **Streamlit SDK deprecate**가 명시된 바 있어(=Spaces에서 Streamlit 경험이 예전 같지 않을 수 있음) “Spaces에 올릴 앱”이라면 Gradio 또는 Docker로 확실히 고정하는 전략이 안전합니다. ([huggingface.co](https://huggingface.co/docs/hub/en/spaces-changelog?utm_source=openai))  
또한 Protected Spaces(소스는 비공개, 앱은 공개 embed)는 데모 공유에 실무적으로 꽤 유용한 옵션입니다. ([huggingface.co](https://huggingface.co/docs/hub/en/spaces-changelog?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: **FastAPI로 LLM/RAG inference 서버가 이미 있고**, 우리는 “빠른 데모 UI”를 Streamlit/Gradio로 붙입니다.
- 요구사항: (1) 사용자별 세션 유지 (2) 스트리밍 출력(Gradio) 또는 폴링 기반 진행 표시(Streamlit) (3) 캐시로 지연 최소화

### 0) 공통: 백엔드(FastAPI) — 스트리밍 + 작업형(job) 둘 다 제공
```python
# server.py
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import time, uuid

app = FastAPI()
JOBS = {}  # demo용 인메모리(실무는 Redis/Celery 권장)

class ChatReq(BaseModel):
    user_id: str
    message: str
    history: List[dict] = []

@app.post("/chat")
def chat(req: ChatReq):
    # 데모: "생성" 흉내
    text = f"[user={req.user_id}] 답변: " + req.message[::-1]
    return {"text": text}

class JobReq(BaseModel):
    user_id: str
    query: str

@app.post("/rag/jobs")
def start_job(req: JobReq):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "running", "progress": 0, "result": None, "t0": time.time()}
    return {"job_id": job_id}

@app.get("/rag/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS[job_id]
    # 데모: 시간 경과로 progress 증가
    elapsed = time.time() - job["t0"]
    prog = min(int(elapsed * 20), 100)
    job["progress"] = prog
    if prog >= 100 and job["result"] is None:
        job["status"] = "done"
        job["result"] = {"answer": "RAG 결과: (데모) 관련 문서 3개를 종합했습니다."}
    return job
```

```bash
pip install fastapi uvicorn
uvicorn server:app --reload --port 8000
```

---

### 1) Streamlit: “앱형 데모” (캐시 + fragments 폴링)
핵심은 2가지입니다.
- HTTP client는 `st.cache_resource`로 재사용(연결 풀, TLS 핸드셰이크 비용 절감)
- job 상태는 `st.fragment(run_every=...)`로 **부분만 주기적으로 rerun** ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment?utm_source=openai))

```python
# streamlit_app.py
import streamlit as st
import httpx

API = "http://localhost:8000"

@st.cache_resource
def get_client():
    return httpx.Client(timeout=30)

st.set_page_config(page_title="AI Demo Console", layout="wide")
st.title("AI Demo Console (Streamlit)")

user_id = st.sidebar.text_input("user_id", value="demo-user")

tab1, tab2 = st.tabs(["Chat", "RAG Job (polling)"])

with tab1:
    st.subheader("Chat (sync)")
    msg = st.text_area("message", height=120, placeholder="질문을 입력하세요")
    if st.button("Send"):
        client = get_client()
        r = client.post(f"{API}/chat", json={"user_id": user_id, "message": msg, "history": []})
        st.success(r.json()["text"])

with tab2:
    st.subheader("RAG Job (polling with fragments)")
    query = st.text_input("query", value="우리 제품의 환불 정책 요약해줘")

    if "job_id" not in st.session_state:
        st.session_state.job_id = None

    colA, colB = st.columns([1, 2])
    with colA:
        if st.button("Start Job"):
            client = get_client()
            r = client.post(f"{API}/rag/jobs", json={"user_id": user_id, "query": query})
            st.session_state.job_id = r.json()["job_id"]

        st.write("job_id:", st.session_state.job_id)

    with colB:
        status_box = st.container()

        @st.fragment(run_every=0.5)  # 0.5초마다 이 fragment만 갱신
        def poll():
            if not st.session_state.job_id:
                st.info("Job을 시작하세요.")
                return
            client = get_client()
            job = client.get(f"{API}/rag/jobs/{st.session_state.job_id}").json()
            st.progress(job["progress"])
            st.write("status:", job["status"])
            if job["status"] == "done":
                st.json(job["result"])

        with status_box:
            poll()
```

```bash
pip install streamlit httpx
streamlit run streamlit_app.py
```

예상 출력:
- Chat 탭: 입력한 텍스트에 대한 “생성 결과”
- RAG 탭: progress bar가 올라가다가 완료 시 JSON 결과 표시  
(중요: 전체 페이지가 계속 깜빡이며 rerun되는 느낌이 아니라, polling 영역만 갱신되는 UX)

---

### 2) Gradio: “모델 데모” (queue + 이벤트 체이닝)
Gradio는 Blocks로 “입력→요청→출력”을 이벤트로 묶고, `.queue()`로 동시 요청을 제어합니다. ([gradio.app](https://gradio.app/docs/gradio/blocks?utm_source=openai))

```python
# gradio_app.py
import gradio as gr
import httpx

API = "http://localhost:8000"
client = httpx.Client(timeout=60)

def send_chat(user_id, message, history):
    r = client.post(f"{API}/chat", json={"user_id": user_id, "message": message, "history": history})
    text = r.json()["text"]
    history = history + [{"role": "user", "content": message}, {"role": "assistant", "content": text}]
    return "", history

def start_rag(user_id, query):
    r = client.post(f"{API}/rag/jobs", json={"user_id": user_id, "query": query})
    return r.json()["job_id"]

def poll_rag(job_id):
    if not job_id:
        return 0, "no job", None
    job = client.get(f"{API}/rag/jobs/{job_id}").json()
    return job["progress"], job["status"], job.get("result")

with gr.Blocks(title="AI Demo (Gradio)") as demo:
    gr.Markdown("## AI Demo (Gradio) — queue 기반 빠른 데모")

    user_id = gr.Textbox(value="demo-user", label="user_id")

    with gr.Tab("Chat"):
        msg = gr.Textbox(lines=4, label="message")
        chat_history = gr.State(value=[])
        out = gr.JSON(label="history(JSON)")
        btn = gr.Button("Send")
        btn.click(send_chat, inputs=[user_id, msg, chat_history], outputs=[msg, out], queue=True)

    with gr.Tab("RAG Job"):
        query = gr.Textbox(value="우리 제품의 환불 정책 요약해줘", label="query")
        job_id = gr.Textbox(label="job_id", interactive=False)
        start = gr.Button("Start Job")

        prog = gr.Slider(0, 100, value=0, label="progress", interactive=False)
        status = gr.Textbox(label="status", interactive=False)
        result = gr.JSON(label="result")

        # start -> job_id 채우고 -> polling은 사용자가 Refresh 버튼으로(데모 단순화)
        start.click(start_rag, inputs=[user_id, query], outputs=[job_id], queue=True)
        refresh = gr.Button("Refresh Status")
        refresh.click(poll_rag, inputs=[job_id], outputs=[prog, status, result], queue=True)

demo.queue()  # 큐 활성화
demo.launch()
```

```bash
pip install gradio httpx
python gradio_app.py
```

운영 관점 팁:
- 대외 데모는 queue를 켜고(concurrency 제한) “서버가 죽지 않는 UX”가 중요합니다. Gradio는 queue가 꽉 차면 사용자에게 queue full 메시지를 줄 수 있고, 기본 동시성 제한도 환경변수로 제어 가능합니다. ([gradio.app](https://gradio.app/main/docs/gradio/interface?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **UI 프레임워크 선택을 “앱의 수명”으로 결정**
- 2주짜리 PoC/세일즈 데모: Gradio 우세(빠른 래핑 + queue)
- 내부 운영툴/분석 콘솔로 성장 가능: Streamlit 우세(multipage/앱 구조화) ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/multipage-apps/page-and-navigation?utm_source=openai))

2) **Streamlit은 캐시 전략이 곧 성능 전략**
- 모델/임베딩/클라이언트: `st.cache_resource`
- 데이터/쿼리 결과: `st.cache_data`  
캐시 없이 “매 인터랙션마다 로드/요청”하면 rerun 모델 때문에 UX가 급격히 무너집니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching?utm_source=openai))

3) **Streamlit의 rerun 병목은 fragments로 잘라라**
- 채팅 로그 렌더링/상태 폴링/메트릭 영역만 fragment로 분리하면, 전체 rerun 비용이 눈에 띄게 줄어듭니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment?utm_source=openai))

### 흔한 함정 / 안티패턴
- (Streamlit) `st.session_state`에 “거대한 객체(모델/벡터DB 핸들)”를 넣고 세션마다 복제/누수 유발  
  → 리소스는 `st.cache_resource`로.
- (Gradio) queue 없이 외부 LLM endpoint를 그대로 때려서, 동시 요청에서 타임아웃/서킷브레이커 부재로 데모가 터짐  
  → `.queue()` + concurrency 제한으로 “서버 보호”부터.
- (Spaces) Streamlit로 올렸는데 기대한 워크플로우가 안 맞는 경우  
  → Spaces changelog에 Streamlit SDK deprecate 이력이 있으니, 장기 운영이면 Gradio 또는 Docker로 고정하는 게 안전합니다. ([huggingface.co](https://huggingface.co/docs/hub/en/spaces-changelog?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **Gradio(queue)**: 안정성↑(대기열) / 지연↑(대기 발생) / 운영 난이도↓  
- **Streamlit(fragments+cache)**: 로컬/내부툴 UX↑ / 복잡한 실시간성(진짜 push)에는 한계 / 구조 설계가 성능에 직결 ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 6월 기준 “빠른 AI 데모 UI”의 현실적인 선택은 이렇게 나뉩니다.

- **Gradio를 고르세요**: 모델 함수/endpoint를 감싸서 바로 공유해야 하고, 동시성/대기열/데모 안정성이 최우선일 때(특히 Spaces/외부 공유). ([gradio.app](https://gradio.app/main/docs/gradio/interface?utm_source=openai))
- **Streamlit을 고르세요**: 데모가 곧 내부 운영툴이 될 가능성이 크고, 페이지 구조/데이터 뷰/관리자 콘솔 형태로 커질 때. 단, `cache_resource/cache_data`와 fragments로 rerun 비용을 통제해야 합니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching?utm_source=openai))

다음 학습 추천(바로 실무 적용용):
- Streamlit: caching(`st.cache_data`, `st.cache_resource`) + fragments(`st.fragment`) + multipage(`st.Page`, `st.navigation`)를 한 프로젝트에 같이 적용해보기 ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching?utm_source=openai))
- Gradio: Blocks 이벤트 체이닝(`.then`) + `.queue()`로 “동시 요청에서도 안 죽는 데모” 템플릿 만들기 ([gradio.app](https://gradio.app/guides/blocks-and-event-listeners?utm_source=openai))

원하시면, 위 예제를 (1) 실제 LLM streaming(SSE) 연결, (2) Redis 기반 job queue, (3) HF Spaces 배포(Docker 포함)까지 확장한 “팀 공용 템플릿” 형태로 리팩터링해서 드릴게요.