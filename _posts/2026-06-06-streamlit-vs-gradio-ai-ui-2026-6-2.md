---
title: "Streamlit vs Gradio, “빠른 AI 데모 UI”를 2026년 6월 기준으로 제대로 굴리는 법"
date: 2026-06-06 04:10:21 +0900
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
LLM/RAG/vision 모델을 “지금 당장” 이해관계자에게 보여줘야 할 때 가장 자주 부딪히는 문제는 UI가 아니라 **데모의 운영성**입니다. 즉, (1) 매 클릭마다 재실행되어 상태가 꼬이거나, (2) 동시 접속에서 큐/스트리밍이 망가지거나, (3) 모델/Vector DB 연결을 매번 다시 만들어 느려지거나, (4) 보안 기본값이 허술한 채로 외부에 노출되는 문제죠.

- **Streamlit을 쓰면 좋은 때**
  - “데모인데도” 표/차트/필터/탐색 UI가 필요하고, 대시보드+챗을 한 화면에서 조합해야 할 때
  - 스크립트 기반 재실행 모델을 이해하고, `st.cache_data`/`st.cache_resource`로 비용 큰 리소스를 안정적으로 고정할 수 있을 때 ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/caching-and-state?utm_source=openai))
- **Gradio를 쓰면 좋은 때**
  - 모델 함수(또는 체인/파이프라인)를 이벤트로 연결해 **최소 코드로 “작동하는 데모”**를 만들어야 할 때
  - 동시 실행 제어(Queue), 진행 표시, 스트리밍 출력 같은 “ML 데모에 흔한 UX”를 프레임워크가 제공해주길 원할 때 ([gradio.app](https://www.gradio.app/main/docs/gradio/blocks?utm_source=openai))
- **둘 다 피해야 할 때**
  - 공개 서비스급 제품 UI(권한/감사로그/AB테스트/복잡한 라우팅/프론트 커스터마이징)가 필요하면, 결국 FastAPI(+React/Next) 쪽이 총비용이 낮아집니다.
  - 내부망이 아닌 외부 공개라면, 프레임워크 기본 설정만 믿고 올리면 사고가 납니다(예: Gradio의 Windows+Python 3.13+에서의 경로 탐색 이슈 등). ([nvd.nist.gov](https://nvd.nist.gov/vuln/detail/CVE-2026-28414?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Streamlit의 본질: “상호작용마다 스크립트 재실행”
Streamlit은 **사용자 상호작용(위젯 변경)**이 발생할 때마다 앱 스크립트를 위에서 아래로 다시 실행합니다. 이 모델은 생산성이 높지만, 비용 큰 객체(LLM 클라이언트, DB 연결, 임베딩 모델, Vector DB 핸들 등)를 매번 생성하면 성능/비용이 터집니다. 그래서 캐시가 핵심이 됩니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/caching-and-state?utm_source=openai))

- `st.cache_data`: “데이터” 캐시(파라미터에 따라 결과가 달라지는 순수 함수 성격)
- `st.cache_resource`: “리소스” 캐시(연결/모델/클라이언트처럼 오래 살아야 하는 것). 2026년 릴리즈 노트 기준 `on_release`로 종료/정리 훅도 제공되어 커넥션 누수를 줄일 수 있습니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026?utm_source=openai))

또 하나: 2026년 Streamlit은 **Starlette 기반 서버를 실험적으로** 켤 수 있는 `server.useStarlette` 옵션을 제공합니다. 다만 문서에서 production에 쓰지 말라고 강하게 경고합니다. 즉, “빠른 실험”은 가능하지만 운영 안정성은 아직 보류라는 신호로 읽는 게 맞습니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026?utm_source=openai))

### 2) Gradio의 본질: “함수/이벤트 그래프 + Queue”
Gradio는 UI 컴포넌트와 이벤트를 연결해서 “입력 → 함수 실행 → 출력”을 구성합니다. 여기서 실무적으로 가장 큰 차별점은:

- **Queue**: 동시 실행을 제어하고(특히 GPU/LLM 호출), 사용자는 대기/진행 UX를 얻습니다. `Blocks.queue()`는 진행 표시 모드까지 제공합니다. ([gradio.app](https://www.gradio.app/main/docs/gradio/blocks?utm_source=openai))
- **Progress**: 함수 내부에서 진행도를 표현하는 도구가 있어, 느린 작업(RAG 인덱싱, 대형 파일 처리)도 데모 품질이 올라갑니다. ([gradio.app](https://www.gradio.app/docs/gradio/progress/?utm_source=openai))
- **Client API**: Gradio 앱은 “UI이면서 API”가 되기 쉬워서, 동일 앱을 다른 서비스가 호출하는 형태로 확장하기 좋습니다(Python/JS client 문서 제공). ([gradio.app](https://www.gradio.app/docs/python-client/client?utm_source=openai))

### 3) “빠른 AI 데모 UI”에서의 결정적 차이
- Streamlit: **복합 UI(챗+표+차트+설정 패널)**를 빠르게 짤 수 있지만, 재실행/상태 모델 때문에 캐시/세션 설계를 잘못하면 “데모가 불안정”해지기 쉽습니다.
- Gradio: **모델 데모 UX(Queue/Progress/스트리밍)를 프레임워크가 제공**해 데모 안정성이 높아지지만, 대시보드식 복잡한 화면 구성은 Streamlit보다 덜 자연스러운 경우가 많습니다.

---

## 💻 실전 코드
현실적인 시나리오: “사내 문서 RAG 데모”
- 업로드한 PDF/MD/TXT를 로컬 디렉토리에 저장
- 백그라운드로 인덱싱(임베딩 생성)하고 진행률 표시
- 챗 화면에서 질문하면 top-k 검색 결과를 컨텍스트로 넣어 LLM 호출
- **핵심**: LLM/Vector DB 핸들은 프로세스 전역으로 재사용(비용 절감), 문서별 인덱스는 캐시/디스크로 재사용

아래 예시는 “외부 API 대신 로컬 LLM 서버(OpenAI-compatible endpoint)”를 가정합니다. (예: vLLM, LM Studio, Ollama의 OpenAI 호환 등) 이 방식이 데모에서 비용/지연을 예측 가능하게 만들어줍니다.

### 0) 의존성/실행
```bash
python -m venv .venv
source .venv/bin/activate

pip install "streamlit>=1.53" "gradio>=6.7" "openai>=1.30" faiss-cpu sentence-transformers pypdf
```

### 1) Streamlit 버전 (복합 UI 강점 + 캐시로 안정화)
`app_streamlit.py`
```python
import os
import time
from dataclasses import dataclass
from typing import List, Tuple

import faiss
import numpy as np
import streamlit as st
from openai import OpenAI
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

DATA_DIR = "data_docs"
os.makedirs(DATA_DIR, exist_ok=True)

@dataclass
class RagIndex:
    model_name: str
    embedder: SentenceTransformer
    index: faiss.IndexFlatIP
    chunks: List[str]
    doc_ids: List[str]

def _chunk_text(text: str, chunk_size=900, overlap=150) -> List[str]:
    text = " ".join(text.split())
    chunks = []
    i = 0
    while i < len(text):
        j = min(len(text), i + chunk_size)
        chunks.append(text[i:j])
        i = max(i + chunk_size - overlap, j)
    return [c for c in chunks if len(c) > 50]

def _read_pdf(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)

@st.cache_resource(show_spinner=False, on_release=lambda r: None)
def get_embedder(model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    # 리소스: 프로세스 전역 재사용(세션/리런에도 유지)
    return SentenceTransformer(model_name)

@st.cache_resource(show_spinner=False, on_release=lambda client: None)
def get_llm_client():
    # OpenAI-compatible local endpoint를 가정
    base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:8000/v1")
    api_key = os.environ.get("OPENAI_API_KEY", "local")
    return OpenAI(base_url=base_url, api_key=api_key)

@st.cache_data(show_spinner=False)
def build_index(file_paths: Tuple[str, ...], model_name: str) -> RagIndex:
    embedder = get_embedder(model_name)

    chunks, doc_ids = [], []
    for p in file_paths:
        if p.lower().endswith(".pdf"):
            text = _read_pdf(p)
        else:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        for c in _chunk_text(text):
            chunks.append(c)
            doc_ids.append(os.path.basename(p))

    emb = embedder.encode(chunks, normalize_embeddings=True, batch_size=64)
    emb = np.asarray(emb, dtype=np.float32)

    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)
    return RagIndex(model_name=model_name, embedder=embedder, index=index, chunks=chunks, doc_ids=doc_ids)

def retrieve(rag: RagIndex, query: str, k=5):
    q = rag.embedder.encode([query], normalize_embeddings=True)
    q = np.asarray(q, dtype=np.float32)
    scores, idx = rag.index.search(q, k)
    results = []
    for s, i in zip(scores[0], idx[0]):
        if i == -1:
            continue
        results.append((float(s), rag.doc_ids[i], rag.chunks[i]))
    return results

def answer(llm: OpenAI, question: str, contexts: List[Tuple[float, str, str]]):
    ctx_text = "\n\n".join([f"[{doc} | score={score:.3f}]\n{chunk}" for score, doc, chunk in contexts])
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Use the provided context. If insufficient, say so."},
        {"role": "user", "content": f"Question:\n{question}\n\nContext:\n{ctx_text}"}
    ]
    resp = llm.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        temperature=0.2,
    )
    return resp.choices[0].message.content

st.set_page_config(page_title="RAG Demo (Streamlit)", layout="wide")

st.title("사내 문서 RAG 데모 (Streamlit)")
with st.sidebar:
    st.header("설정")
    model_name = st.text_input("Embedding model", "sentence-transformers/all-MiniLM-L6-v2")
    k = st.slider("top-k", 3, 10, 5)
    uploaded = st.file_uploader("문서 업로드 (PDF/TXT/MD)", accept_multiple_files=True, type=["pdf", "txt", "md"])

# 업로드 파일을 디스크에 저장(데모에서 재현성 확보)
saved_paths = []
if uploaded:
    for f in uploaded:
        path = os.path.join(DATA_DIR, f.name)
        with open(path, "wb") as out:
            out.write(f.getbuffer())
        saved_paths.append(path)

existing_paths = sorted(
    os.path.join(DATA_DIR, p) for p in os.listdir(DATA_DIR)
    if p.lower().endswith((".pdf", ".txt", ".md"))
)

col1, col2 = st.columns([1, 2])
with col1:
    st.subheader("인덱스 상태")
    st.write(f"- docs: {len(existing_paths)}")
    rebuild = st.button("인덱스 재생성")

# 캐시 키를 바꾸려면 입력(파일 목록/모델명)이 바뀌어야 함
file_key = tuple(existing_paths)
if rebuild:
    # 캐시 무효화(데모 운영에서 '재빌드 버튼'은 필수)
    build_index.clear()

with st.spinner("인덱싱/캐시 로딩 중..."):
    rag = build_index(file_key, model_name)
llm = get_llm_client()

with col2:
    st.subheader("질문")
    if "chat" not in st.session_state:
        st.session_state.chat = []

    q = st.text_input("질문을 입력하세요", placeholder="예: 휴가 정책에서 carry-over 규정은?")
    ask = st.button("질문하기", type="primary")

    if ask and q.strip():
        t0 = time.time()
        hits = retrieve(rag, q, k=k)
        a = answer(llm, q, hits)
        st.session_state.chat.append((q, a, hits, time.time() - t0))

    for q, a, hits, dt in reversed(st.session_state.chat[-5:]):
        st.markdown(f"**Q**: {q}")
        st.markdown(f"**A**: {a}")
        with st.expander(f"컨텍스트(top-{len(hits)}) / latency={dt:.2f}s"):
            for score, doc, chunk in hits:
                st.write(f"- {doc} (score={score:.3f})")
                st.code(chunk[:800])
```

**예상 출력**
- 업로드 후 “인덱싱/캐시 로딩 중…” 1회 발생(이후 동일 파일/모델이면 즉시)
- 질문하면 답변 + 근거 chunk(expander) 표시
- `인덱스 재생성` 버튼으로 캐시 무효화 후 재빌드

여기서 “왜 이 구성이 실전적이냐”:
- Streamlit의 재실행 특성 때문에 **LLM client / embedder는 `st.cache_resource`로 고정**해야 비용과 지연이 안정화됩니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/caching-and-state?utm_source=openai))
- 인덱스는 문서 목록이 입력으로 들어가므로 `st.cache_data`로 캐시가 가능하고, 운영 중 “재빌드 버튼”으로 명시적 무효화를 제공합니다(안 그러면 문서가 바뀌었는데도 캐시가 남아 데모가 깨집니다).

### 2) Gradio 버전 (Queue/Progress 강점 + 데모 운영성)
`app_gradio.py`
```python
import os
import time
from typing import List, Tuple

import faiss
import gradio as gr
import numpy as np
from openai import OpenAI
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

DATA_DIR = "data_docs"
os.makedirs(DATA_DIR, exist_ok=True)

def chunk_text(text: str, chunk_size=900, overlap=150) -> List[str]:
    text = " ".join(text.split())
    chunks, i = [], 0
    while i < len(text):
        j = min(len(text), i + chunk_size)
        chunks.append(text[i:j])
        i = max(i + chunk_size - overlap, j)
    return [c for c in chunks if len(c) > 50]

def read_pdf(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)

class RagState:
    def __init__(self):
        self.embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        self.index = None
        self.chunks: List[str] = []
        self.doc_ids: List[str] = []
        base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:8000/v1")
        api_key = os.environ.get("OPENAI_API_KEY", "local")
        self.llm = OpenAI(base_url=base_url, api_key=api_key)
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

STATE = RagState()

def build_or_rebuild(files: List[gr.File], embed_model: str, progress=gr.Progress(track_tqdm=False)):
    # Progress는 “느린 인덱싱”을 데모에서 견디게 해주는 장치 ([gradio.app](https://www.gradio.app/docs/gradio/progress/?utm_source=openai))
    STATE.embedder = SentenceTransformer(embed_model)

    paths = []
    for f in files:
        # gr.File은 임시 경로를 주므로, 운영 재현성을 위해 저장
        dst = os.path.join(DATA_DIR, os.path.basename(f.name))
        with open(f.name, "rb") as src, open(dst, "wb") as out:
            out.write(src.read())
        paths.append(dst)

    chunks, doc_ids = [], []
    progress(0, desc="문서 파싱 중")
    for i, p in enumerate(paths, start=1):
        if p.lower().endswith(".pdf"):
            text = read_pdf(p)
        else:
            with open(p, "r", encoding="utf-8", errors="ignore") as fp:
                text = fp.read()
        for c in chunk_text(text):
            chunks.append(c)
            doc_ids.append(os.path.basename(p))
        progress(i / max(1, len(paths)), desc=f"파싱 {i}/{len(paths)}")

    progress(0, desc="임베딩 생성 중")
    emb = STATE.embedder.encode(chunks, normalize_embeddings=True, batch_size=64)
    emb = np.asarray(emb, dtype=np.float32)

    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)

    STATE.index = index
    STATE.chunks = chunks
    STATE.doc_ids = doc_ids
    return f"OK: {len(paths)} docs, {len(chunks)} chunks"

def retrieve(query: str, k: int):
    q = STATE.embedder.encode([query], normalize_embeddings=True)
    q = np.asarray(q, dtype=np.float32)
    scores, idx = STATE.index.search(q, k)
    results = []
    for s, i in zip(scores[0], idx[0]):
        if i == -1:
            continue
        results.append((float(s), STATE.doc_ids[i], STATE.chunks[i]))
    return results

def chat(message: str, history: List[Tuple[str, str]], k: int):
    if STATE.index is None:
        return "먼저 문서를 업로드하고 인덱싱하세요."
    t0 = time.time()
    hits = retrieve(message, k=k)
    ctx = "\n\n".join([f"[{doc} | score={score:.3f}]\n{chunk}" for score, doc, chunk in hits])

    resp = STATE.llm.chat.completions.create(
        model=STATE.model,
        messages=[
            {"role": "system", "content": "Use context; if insufficient, say so."},
            {"role": "user", "content": f"Question:\n{message}\n\nContext:\n{ctx}"}
        ],
        temperature=0.2,
    )
    ans = resp.choices[0].message.content
    latency = time.time() - t0
    return f"{ans}\n\n---\n(top-{len(hits)}) latency={latency:.2f}s"

with gr.Blocks(title="RAG Demo (Gradio)") as demo:
    gr.Markdown("### 사내 문서 RAG 데모 (Gradio)")

    with gr.Row():
        files = gr.File(file_count="multiple", file_types=[".pdf", ".txt", ".md"], label="문서 업로드")
        with gr.Column():
            embed_model = gr.Textbox(value="sentence-transformers/all-MiniLM-L6-v2", label="Embedding model")
            build_btn = gr.Button("인덱싱 실행", variant="primary")
            status = gr.Textbox(label="상태", interactive=False)

    k = gr.Slider(3, 10, value=5, step=1, label="top-k")
    chatbot = gr.ChatInterface(fn=lambda m, h: chat(m, h, int(k.value)),
                              additional_inputs=[k])

    build_btn.click(fn=build_or_rebuild, inputs=[files, embed_model], outputs=[status])

# Queue는 동시 요청을 제어하고 진행 UX를 제공(데모에서 체감 큼) ([gradio.app](https://www.gradio.app/main/docs/gradio/blocks?utm_source=openai))
demo.queue(status_update_rate=1).launch()
```

**예상 출력**
- “인덱싱 실행” 시 진행률이 보이며 완료 후 상태 텍스트 갱신
- 동시에 여러 사용자가 질문해도 Queue가 폭주를 완화

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 적용)
1) **“리소스”와 “데이터”를 구분해서 캐시/수명주기 설계**
- Streamlit에서는 `st.cache_resource`에 LLM client/DB connection/임베더를 넣고, 데이터(문서 인덱스, 전처리 결과)는 `st.cache_data`로 분리하세요. 그래야 재실행 모델에서도 지연이 안정화됩니다. ([docs.streamlit.io](https://docs.streamlit.io/develop/concepts/architecture/caching?utm_source=openai))

2) **데모는 반드시 “근거 UI”를 포함**
- RAG 데모는 답만 보여주면 신뢰가 무너집니다. top-k chunk를 expander로 보여주고, score/latency를 같이 노출하면 “프로젝트 적용 가능성”을 즉석에서 판단할 수 있습니다.

3) **동시성/비용 상한을 UI 레이어에서 강제**
- Gradio는 `queue()`로 GPU/LLM 호출 동시 실행을 제한하기 쉬워서, PoC 단계에서 비용 폭발을 막는 데 유리합니다. ([gradio.app](https://www.gradio.app/main/docs/gradio/blocks?utm_source=openai))

### 흔한 함정/안티패턴
- **Streamlit에서 매 rerun마다 Vector DB/LLM client 재생성**
  - 증상: 첫 질문은 되는데 점점 느려짐, 커넥션 누수, API rate limit
  - 처방: `st.cache_resource` + 필요 시 `on_release`로 정리 훅 사용 ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026?utm_source=openai))

- **Gradio 공개 노출을 “share=True”로 급하게 열기**
  - 데모 URL을 외부에 뿌리는 순간, 입력 검증/파일 접근/인증 설정의 빈틈이 바로 공격면이 됩니다. 특히 Gradio는 CVE로 보고된 케이스도 있으니(Windows+Python 3.13+에서의 임의 파일 읽기 등) 버전/환경 제약을 확인하고 업데이트 정책을 잡으세요. ([nvd.nist.gov](https://nvd.nist.gov/vuln/detail/CVE-2026-28414?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **Streamlit**: UI 조합력↑ / 재실행 모델 학습비용↑ / 캐시 설계 실패 시 불안정↑
- **Gradio**: 데모 운영성(Queue/Progress)↑ / 복합 대시보드 구성력은 상황에 따라↓ / 공개 배포 시 보안 설정을 더 의식해야 함

---

## 🚀 마무리
핵심은 “Streamlit이냐 Gradio냐”가 아니라, **빠른 데모를 ‘안정적으로 반복 가능’하게 만드는 구조**입니다.

- **Streamlit 도입 판단 기준**
  - 챗만이 아니라 표/차트/필터/리포트까지 한 화면에서 다뤄야 한다
  - 캐시/세션을 설계할 준비가 되어 있다 (`st.cache_data`/`st.cache_resource`, 재빌드 버튼, 근거 UI) ([docs.streamlit.io](https://docs.streamlit.io/develop/api-reference/caching-and-state?utm_source=openai))
- **Gradio 도입 판단 기준**
  - 모델 함수 중심, 동시 요청 제어가 바로 필요하다
  - 인덱싱/추론이 느리고 Progress/Queue UX가 데모 성패를 가른다 ([gradio.app](https://www.gradio.app/main/docs/gradio/blocks?utm_source=openai))

다음 학습 추천:
- Streamlit: caching/state 문서와 2026 릴리즈 노트에서 `st.cache_resource` 수명주기, `server.useStarlette` 같은 실험 옵션의 의미를 “운영 관점”으로 읽어보세요. ([docs.streamlit.io](https://docs.streamlit.io/develop/quick-reference/release-notes/2026?utm_source=openai))
- Gradio: `Blocks.queue()`/`Progress`/Client API(Python/JS)를 묶어서 “UI+API 겸용 데모”를 만드는 패턴을 정리해두면, PoC가 곧 서비스 프로토타입으로 이어집니다. ([gradio.app](https://www.gradio.app/main/docs/gradio/blocks?utm_source=openai))