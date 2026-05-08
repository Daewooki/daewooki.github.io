---
title: "Streamlit vs Gradio: 2026년 5월 기준 “하루 만에 AI 데모 UI”를 제대로 만드는 선택과 설계"
date: 2026-05-08 03:41:07 +0900
categories: [AI, Prototyping]
tags: [ai, prototyping, trend, 2026-05]
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
AI 기능(LLM, vision, STT/TTS, RAG 등)을 “일단 보여주는 것” 자체는 쉬워졌지만, **데모 UI를 빨리 만들수록** 바로 다음 문제가 터집니다.

- 모델 로딩/워밍업이 느려서 첫 요청이 수십 초 걸림
- 동시 접속 시 세션/상태 꼬임, 캐시 오염
- 스트리밍(토큰/프로그레스) UX가 없어 “멈춘 것처럼” 보임
- 프록시/서브패스 배포에서 라우팅 깨짐
- 결국 “프로토타입”이 어느새 “준프로덕션”이 됨

이 글은 **2026년 5월 기준** Streamlit/Gradio로 “빠른 AI 데모 UI”를 만들 때, 단순 소개가 아니라 **내 프로젝트에서 무엇을 기준으로 선택/구조화할지**를 다룹니다. (최신 문서/릴리즈 노트 기반)

**언제 Streamlit이 좋은가**
- 데이터 앱처럼 **여러 뷰(탭/페이지)**, 필터/테이블/차트, 내부 운영툴 성격이 강할 때
- “스크립트 흐름 기반”으로 UI를 빠르게 짜고, 캐시/세션을 통제하면서 점진적으로 확장할 때

**언제 Gradio가 좋은가**
- 모델 inference를 **입력→출력 파이프라인**으로 명확히 정의하고, 데모/공유가 핵심일 때
- FastAPI 같은 백엔드에 **UI를 붙이는 컴포넌트**로 두고 싶을 때(특히 mount) ([gradio.app](https://www.gradio.app/main/docs/gradio/mount_gradio_app))

**언제 둘 다 피하고 Next.js/React(+FastAPI)로 가야 하나**
- 트래픽/권한/테넌시/관측성/QA가 필요한 “진짜 프로덕션 웹앱”
- UI가 복잡한 멀티스텝 폼, 세밀한 인터랙션, SEO/SSR을 강하게 요구

---

## 🔧 핵심 개념
### 1) Streamlit의 “재실행(re-run) 모델”과 캐시 설계
Streamlit은 기본적으로 **사용자 인터랙션이 발생하면 스크립트가 위에서 아래로 다시 실행**되는 모델입니다. 그래서 “빠른 데모”가 가능한 대신, **비싼 작업(모델 로딩, 임베딩 인덱스 로딩, DB 연결)**을 매번 하면 바로 체감이 나빠집니다.

이때 핵심이 캐시 2종입니다.

- `st.cache_data`: **직렬화 가능한 데이터 결과**를 캐시(입력 파라미터 + 함수 코드 변경을 기준으로 무효화) ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching))  
- `st.cache_resource`: **전역 리소스(모델, 커넥션 등)** 를 캐시. 단, 객체를 공유하므로 **mutable 객체 오염/동시성**에 특히 주의 ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching))  

2026년 릴리즈 노트에서 특히 실무적으로 큰 변화는:
- `st.cache_data` / `st.cache_resource`를 **session-scoped로 스코핑**할 수 있음(전역 공유 vs 세션 격리 선택지) ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026))  
- `st.cache_resource`에 `on_release`로 **리소스 정리(커넥션 close 등)** 가능 ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026))  
- (실험) `server.useStarlette` 옵션으로 Streamlit 서버 런타임 선택 폭이 넓어짐(배포/미들웨어 호환성 관점에서 체크 포인트) ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026))  

**정리:** Streamlit의 성능/안정성은 “재실행을 전제로 캐시/상태를 어떻게 나누는가”에서 갈립니다.

### 2) Gradio의 “함수/블록 중심” 구성과 FastAPI 결합
Gradio는 UI가 **모델 함수(또는 파이프라인)에 바인딩**되는 방식이 강하고, 데모용 UX(입력 컴포넌트/출력 컴포넌트)가 빠릅니다.

실무에서 중요한 포인트는 “Gradio를 단독 서버로 띄울지” vs “기존 백엔드(FastAPI)에 **mount**해서 서브 경로로 붙일지”입니다. Gradio는 공식적으로 `gr.mount_gradio_app(app, blocks, path="/gradio")` 패턴을 제공합니다. ([gradio.app](https://www.gradio.app/main/docs/gradio/mount_gradio_app))

또한 프록시/서브패스(예: `https://example.com/myapp`) 환경에서 `root_path` 이슈가 자주 터지는데, 문서에서 **proxy가 올바른 경로 헤더를 주지 않으면 `root_path`를 명시**하라고 안내합니다. ([gradio.app](https://www.gradio.app/main/docs/gradio/mount_gradio_app))

### 3) “빠른 데모 UI”의 본질: UI 프레임워크가 아니라 “아키텍처 분리”
Streamlit/Gradio 중 무엇을 쓰든, 2026년 시점에서 빠른 데모를 “실무에서 쓸만하게” 만드는 핵심은 다음 2계층 분리입니다.

- **Inference API 계층**: 모델 호출, 큐잉, 타임아웃, 로깅, 비용제어
- **Demo UI 계층**: 입력 검증, 스트리밍 표시, 결과 렌더링, 간단한 상태 관리

UI에서 모델을 직접 들고 있으면 초반은 빠르지만, 동시성/관측성/배포에서 금방 한계가 옵니다. 반대로 “UI는 얇게, inference는 API로” 두면 Streamlit/Gradio 모두 훨씬 오래 갑니다.

---

## 💻 실전 코드
현실적인 시나리오로 **“문서 요약/질의” 데모**를 구성합니다.

- FastAPI: 파일 업로드 → (가짜로) 긴 작업을 흉내 내며 처리 → 결과 반환
- Streamlit & Gradio: 같은 API를 호출해 데모 UI를 빠르게 구성
- 포인트: **모델/리소스는 API 서버에서 관리**, UI는 캐시/세션으로 “빠르게 보이게” 만든다

### 0) 공통: FastAPI inference 서버 (`api/main.py`)
```python
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
import hashlib
import time

app = FastAPI(title="Inference API")

class SummarizeResponse(BaseModel):
    doc_id: str
    summary: str

def fake_expensive_summarize(text: str) -> str:
    # 실제로는 LLM 호출/벡터검색/RAG 등이 위치
    time.sleep(2.5)
    return f"[summary] {text[:240]}..."

@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(file: UploadFile = File(...)):
    content = await file.read()
    doc_id = hashlib.sha256(content).hexdigest()[:12]
    text = content.decode("utf-8", errors="ignore")
    summary = fake_expensive_summarize(text)
    return SummarizeResponse(doc_id=doc_id, summary=summary)
```

실행:
```bash
pip install fastapi uvicorn python-multipart
uvicorn api.main:app --reload --port 8000
```

---

### 1) Streamlit 데모 UI (`ui_streamlit/app.py`)
핵심은:
- 업로드 파일 → `/summarize` 호출
- 결과는 `st.cache_data`로 **문서 해시 키 기반 캐시**
- “리소스(HTTP client)”는 `st.cache_resource`로 재사용

```python
import streamlit as st
import requests
import hashlib

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Doc Summarizer Demo", layout="wide")
st.title("Internal Demo: Document Summarizer (Streamlit)")

@st.cache_resource
def http_session():
    # requests.Session은 연결 재사용(keep-alive)로 체감 성능이 좋아짐
    return requests.Session()

@st.cache_data(show_spinner=False)
def summarize_cached(file_bytes: bytes):
    doc_id = hashlib.sha256(file_bytes).hexdigest()[:12]
    s = http_session()
    files = {"file": ("doc.txt", file_bytes, "text/plain")}
    r = s.post(f"{API_BASE}/summarize", files=files, timeout=60)
    r.raise_for_status()
    data = r.json()
    return doc_id, data["summary"]

col1, col2 = st.columns([1, 2])

with col1:
    up = st.file_uploader("Upload .txt", type=["txt"])
    run = st.button("Summarize", type="primary", use_container_width=True)

with col2:
    if up and run:
        file_bytes = up.getvalue()
        with st.spinner("Calling inference API..."):
            doc_id, summary = summarize_cached(file_bytes)
        st.caption(f"doc_id = {doc_id} (cached by content hash)")
        st.text_area("Summary", summary, height=260)

st.divider()
st.write("Tip: 동일 파일 재실행 시 즉시 결과가 뜨면 캐시가 제대로 먹은 것.")
```

실행:
```bash
pip install streamlit requests
streamlit run ui_streamlit/app.py --server.port 8501
```

**예상 출력**
- 첫 실행: 스피너가 약 2~3초
- 같은 파일로 재실행: 거의 즉시 표시(캐시)

Streamlit 캐시는 “입력 파라미터 + 함수 코드” 변경을 기준으로 동작하므로(= 코드 바꾸면 캐시 무효화), 데모 중 잦은 수정에도 예측 가능하게 동작합니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching))

---

### 2) Gradio 데모 UI + FastAPI에 mount (`ui_gradio/main.py`)
이번엔 **기존 FastAPI에 Gradio를 서브패스로 붙이는** 패턴을 사용합니다. ([gradio.app](https://www.gradio.app/main/docs/gradio/mount_gradio_app))  
(“프로덕션 백엔드가 이미 있다”는 팀에서 특히 유용)

```python
from fastapi import FastAPI
import gradio as gr
import requests

API_BASE = "http://127.0.0.1:8000"

app = FastAPI(title="Backend + Gradio UI")

def summarize(file_obj):
    # file_obj는 tempfile 경로를 포함할 수 있음(환경에 따라 다름)
    with open(file_obj.name, "rb") as f:
        r = requests.post(f"{API_BASE}/summarize", files={"file": ("doc.txt", f, "text/plain")}, timeout=60)
        r.raise_for_status()
        data = r.json()
    return f"doc_id={data['doc_id']}\n\n{data['summary']}"

with gr.Blocks(title="Doc Summarizer (Gradio)") as demo:
    gr.Markdown("### Internal Demo: Document Summarizer (Gradio)")
    inp = gr.File(label="Upload .txt")
    out = gr.Textbox(label="Result", lines=12)
    btn = gr.Button("Summarize", variant="primary")
    btn.click(fn=summarize, inputs=[inp], outputs=[out])

# mount: /gradio 경로로 UI 제공
app = gr.mount_gradio_app(app, demo, path="/gradio")
```

실행:
```bash
pip install gradio fastapi uvicorn requests
uvicorn ui_gradio.main:app --reload --port 9000
```

접속:
- `http://127.0.0.1:9000/gradio`

프록시/서브패스 배포라면 `root_path`를 명시해야 하는 경우가 있습니다(문서에 언급). ([gradio.app](https://www.gradio.app/main/docs/gradio/mount_gradio_app))

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **UI는 “상태”, API는 “작업”**
- Streamlit/Gradio UI에서 모델을 직접 들고 있으면, 데모가 성공할수록 “동시성/재현성/관측성”이 발목 잡습니다.
- inference는 FastAPI 같은 API로 밀어넣고, UI는 입력/출력/스트리밍 UX에 집중하세요.

2) Streamlit은 **`st.cache_data` vs `st.cache_resource` 경계를 엄격히**
- 데이터(요약 결과, 전처리 산출물) = `st.cache_data`
- 커넥션/모델/클라이언트 = `st.cache_resource`
- 특히 `st.cache_resource`는 공유 객체 mutable 오염 위험이 크니 조심하라는 경고가 문서에 명확합니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching))

3) Gradio를 조직에 넣을 때는 **mount + auth 전략**
- `gr.mount_gradio_app`는 `auth`, `auth_dependency`, `root_path` 등 운영 옵션을 제공합니다. ([gradio.app](https://www.gradio.app/main/docs/gradio/mount_gradio_app))  
- “내부 데모”라도 인증 없이 올리면 금방 사고 납니다(파일 업로드/모델 추론은 공격 표면이 큼).

### 흔한 함정/안티패턴
- (Streamlit) 캐시된 리소스를 **in-place mutate**: 한 유저의 변경이 다른 유저에게 새어 나갈 수 있음 ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching))  
- (Streamlit) “빠르게 만들겠다고” 모든 걸 `st.cache_resource`에 박기: 처음은 빨라도, 디버깅 지옥이 옵니다.
- (Gradio) 프록시 환경에서 `root_path`를 무시: 서브패스 배포에서 정적 리소스/라우팅이 깨지기 쉬움 ([gradio.app](https://www.gradio.app/main/docs/gradio/mount_gradio_app))  

### 비용/성능/안정성 트레이드오프
- **Streamlit 단독**: 개발 속도 ↑ / 복잡 UI 구성 ↑, 하지만 고부하 inference를 한 프로세스에서 감당하려 하면 한계가 빨리 옴(결국 API 분리 필요)
- **Gradio 단독**: 모델 데모 속도 ↑ / 공유 ↑, 하지만 “조직 표준 백엔드”에 녹이려면 mount/라우팅/인증/관측성을 같이 설계해야 함
- **API 분리(권장)**: 초기 구성은 조금 번거롭지만, 캐시/큐/오토스케일/로깅을 분리할 수 있어 장기적으로 비용과 장애율이 내려갑니다.

---

## 🚀 마무리
핵심은 “Streamlit이냐 Gradio냐”보다 **데모 UI를 어디까지 운영할 생각인지**입니다.

- **내부 운영툴 + 다중 페이지/데이터 UI 중심**이면 Streamlit이 유리하고, 2026 릴리즈에서 캐시의 session-scope, `on_release` 같은 운영 친화 기능이 강화되었습니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026))  
- **모델 데모/공유 + 기존 FastAPI에 UI를 얹기**가 목표면 Gradio의 mount 패턴이 깔끔하고, 프록시 환경에서는 `root_path`까지 포함해 배포 경로를 명확히 잡아야 합니다. ([gradio.app](https://www.gradio.app/main/docs/gradio/mount_gradio_app))  

다음 학습 추천(프로젝트 적용 순서):
1) Streamlit: `st.cache_data`/`st.cache_resource`를 “데이터 vs 리소스”로 분리하고, 동시성 위험을 문서 수준에서 이해 ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching))  
2) Gradio: `mount_gradio_app`로 FastAPI에 붙이고, `root_path`/auth 옵션을 포함한 “사내 배포” 플로우 정리 ([gradio.app](https://www.gradio.app/main/docs/gradio/mount_gradio_app))  
3) 공통: inference API 계층에 큐잉/타임아웃/로깅/비용제어를 넣어 “데모가 성공해도 망가지지 않는” 구조로 확장

원하면, 당신의 상황(데모 대상: 내부/외부, 예상 동시접속, 배포 환경: k8s/EC2/Cloud Run, 모델 유형: LLM/RAG/vision)에 맞춰 **Streamlit vs Gradio 의사결정 체크리스트**와 **권장 폴더 구조/배포 방식**까지 구체적으로 설계해 드릴게요.