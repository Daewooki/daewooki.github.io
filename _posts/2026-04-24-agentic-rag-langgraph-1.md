---
title: "실무에서 바로 쓰는 Agentic RAG: “자율적 정보 검색 에이전트”를 LangGraph로 구현하는 설계/코드/함정 총정리"
date: 2026-04-24 03:36:12 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-04]
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
전통적 RAG는 보통 `retrieve → (rerank) → generate` 파이프라인이 고정이라, **질문이 애매하거나(재질문 필요), 문서가 방대하거나(추가 탐색 필요), 근거가 부족한데도 답을 생성하는(환각) 상황**에서 취약합니다. 반대로 Agentic RAG는 LLM이 “지금 검색이 필요한가?”, “쿼리를 어떻게 바꿔야 하나?”, “검색 결과가 부실하니 더 파고들까?”를 **자율적으로 결정**하면서 루프를 돌립니다. LangGraph가 이 패턴(상태/루프/중단조건)을 가장 구현하기 좋은 프레임워크로 많이 쓰이고요. ([langchain-ai.lang.chat](https://langchain-ai.lang.chat/langgraph/tutorials/rag/langgraph_agentic_rag/?utm_source=openai))

**언제 쓰면 좋은가**
- 문서가 크고 이질적(위키+PDF+티켓+코드+로그)이라 **한 번의 top-k 검색으로는 정답 근거가 잘 안 모일 때**
- 사용자가 “A와 B 비교해줘”, “조건이 이럴 땐?”, “이 오류의 root cause?”처럼 **다단계 탐색**이 필요한 질문을 할 때
- 제품/운영 환경에서 **근거 부족 시 재검색/재질문/답변 보류** 같은 정책을 넣고 싶을 때(품질, 컴플라이언스)

**언제 쓰면 안 되는가**
- FAQ성 Q&A처럼 **단발성 검색으로 충분**한데도 “에이전트 루프”를 돌리면 비용/지연만 늘어납니다.
- 관측/통제(Observability, Guardrails)가 없는 상태에서 “자율성”만 키우면 **무한 루프·도구 남용·비용 폭발**이 발생합니다(Agentic RAG의 가장 흔한 실전 사고). SoK에서도 비용/안정성/감독(oversight)을 핵심 과제로 봅니다. ([arxiv.org](https://arxiv.org/abs/2603.07379?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Agentic RAG의 정의(실무 관점)
Agentic RAG는 “검색을 붙인 챗봇”이 아니라, **Retrieval을 ‘툴(tool)’로 만들고 LLM이 호출 여부/반복/전략을 결정**하는 구조입니다. LangGraph 튜토리얼도 “retriever tool을 언제 쓸지 에이전트가 결정”하는 흐름을 전제로 합니다. ([langchain-ai.lang.chat](https://langchain-ai.lang.chat/langgraph/tutorials/rag/langgraph_agentic_rag/?utm_source=openai))

### 2) 내부 작동 방식(구조/흐름)
실무에서 가장 재사용 가능한 최소 골격은 아래 상태 머신입니다.

- **State**
  - `user_question`: 원 질문
  - `working_query`: 현재 검색 쿼리(에이전트가 rewrite 가능)
  - `retrieved_docs`: 누적(또는 최근) 근거
  - `draft_answer`: 초안
  - `critique`: “근거 충분?”, “문서와 충돌?”, “추가 검색 필요?”
  - `step_count / budget`: 루프 상한(비용/안정성)

- **Nodes**
  1) **Plan / Decide**: 검색할지, 답을 쓸지, 쿼리를 바꿀지 결정
  2) **Retrieve**: vector + (가능하면) keyword/hybrid 검색
  3) **Filter/Rerank**: 관련도 낮은 문서 제거(여기서 노이즈가 누적되면 이후 모든 step이 망가짐)
  4) **Generate**: 근거 기반 답안 생성(“모르면 모른다” 정책 포함)
  5) **Reflect / Self-check**: 답이 질문을 충족했는지, 근거가 충분한지 평가 → 필요 시 루프

LangChain 블로그는 CRAG/Self-RAG류의 “self-reflective loop(재검색/쿼리 재작성/문서 폐기)”를 LangGraph로 구현하는 방향을 강조합니다. ([langchain.com](https://www.langchain.com/blog/agentic-rag-with-langgraph?utm_source=openai))  
최근 SoK(2026)도 agentic RAG를 **iterative retrieval + dynamic memory + oversight** 관점에서 정리합니다. ([arxiv.org](https://arxiv.org/abs/2603.07379?utm_source=openai))

### 3) 다른 접근과의 차이점
- **Traditional RAG**: 파이프라인이 고정, 실패 시 원인 파악/회복이 어렵지만 단순하고 싸다.
- **Self-RAG(모델 중심)**: “하나의 모델이 retrieval/critique를 내부적으로 수행”하는 쪽(개념적으로는 좋지만, 실무에선 여전히 외부 툴/정책/예산 제약이 필요). ([ibm.com](https://www.ibm.com/think/tutorials/build-self-rag-agent-langgraph-granite?utm_source=openai))
- **Agentic RAG(오케스트레이션 중심)**: 모델은 플래너/결정자 + 툴 호출자. LangGraph/LlamaIndex 워크플로우처럼 **상태/루프/도구 호출을 코드로 통제**하기 쉬움. ([langchain-ai.lang.chat](https://langchain-ai.lang.chat/langgraph/tutorials/rag/langgraph_agentic_rag/?utm_source=openai))
- **Hierarchical retrieval interface(A-RAG, 2026)**: “semantic search만”이 아니라 **keyword/semantic/chunk-read**처럼 계층 툴을 노출해, 에이전트가 granularity를 바꿔가며 탐색(큰 코퍼스에서 비용/성능 균형에 유리). ([arxiv.org](https://arxiv.org/abs/2602.03442?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “사내 운영 Runbook + 장애 티켓 + 설계 문서”를 합쳐서, 질문이 오면 **(1) 쿼리 재작성 → (2) 하이브리드 검색 → (3) 근거 부족 시 추가 탐색 → (4) 최종 답 + 인용**까지 도는 Agentic RAG의 최소 실전형입니다.

- 벡터DB: 로컬 FAISS
- 검색: BM25(키워드) + Vector(semantic) 결합(간단 가중 합)
- 오케스트레이션: LangGraph
- 중단조건: `max_steps`, `no_new_evidence`, `confidence`

> 주: LangGraph의 “그래프 루프”는 잘못 만들면 무한 재검색으로 빠지기 쉽습니다. 실제로 튜토리얼/예제들에서도 recursion/loop 이슈가 자주 언급됩니다. ([langchain-opentutorial.gitbook.io](https://langchain-opentutorial.gitbook.io/langchain-opentutorial/17-langgraph/02-structures/06-langgraph-agentic-rag?utm_source=openai))

### 0) 설치/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install -U langgraph "langchain[openai]" langchain-community langchain-text-splitters \
  faiss-cpu rank-bm25 pydantic
export OPENAI_API_KEY="..."
```
(위 설치 조합은 LangGraph agentic RAG 튜토리얼 계열과 호환되는 편입니다.) ([langchain-ai.lang.chat](https://langchain-ai.lang.chat/langgraph/tutorials/rag/langgraph_agentic_rag/?utm_source=openai))

### 1) 인덱싱(문서 준비는 “현실적인 형태”로)
```python
# index_build.py
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

DATA_DIR = Path("./data")  # runbooks/, tickets/, design/
INDEX_DIR = Path("./faiss_index")

def load_docs():
    loader = DirectoryLoader(
        str(DATA_DIR),
        glob="**/*.txt",
        loader_cls=TextLoader,
        show_progress=True,
    )
    return loader.load()

def main():
    docs = load_docs()
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150)
    chunks = splitter.split_documents(docs)

    vs = FAISS.from_documents(
        chunks,
        embedding=OpenAIEmbeddings(model="text-embedding-3-large"),
    )
    vs.save_local(str(INDEX_DIR))
    print(f"Indexed chunks={len(chunks)} into {INDEX_DIR}")

if __name__ == "__main__":
    main()
```

예상 출력:
```text
Indexed chunks=4823 into faiss_index
```

### 2) Agentic RAG 그래프(Plan→Retrieve→Generate→Reflect 루프)
```python
# agentic_rag.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from rank_bm25 import BM25Okapi

from langgraph.graph import StateGraph, END

INDEX_DIR = "./faiss_index"

# -----------------------------
# State / Schemas
# -----------------------------
class AgentState(BaseModel):
    user_question: str
    working_query: str
    retrieved: List[Document] = Field(default_factory=list)
    answer: Optional[str] = None
    critique: Optional[str] = None
    step: int = 0
    max_steps: int = 4
    evidence_fingerprint: List[str] = Field(default_factory=list)  # for loop stopping

class Decide(BaseModel):
    action: str = Field(description="one of: retrieve, generate, rewrite, stop")
    rewrite_query: Optional[str] = None

class Critique(BaseModel):
    sufficient: bool
    reason: str
    suggest_rewrite: Optional[str] = None

# -----------------------------
# Retrieval: Hybrid (BM25 + Vector)
# -----------------------------
@dataclass
class HybridRetriever:
    faiss: FAISS
    bm25: BM25Okapi
    bm25_docs: List[Document]
    bm25_tokens: List[List[str]]
    k: int = 6

    @staticmethod
    def _tok(s: str) -> List[str]:
        return [t for t in s.lower().replace("/", " ").replace("_", " ").split() if t]

    @classmethod
    def from_faiss(cls, faiss: FAISS, bm25_source_docs: List[Document], k: int = 6):
        tokens = [cls._tok(d.page_content) for d in bm25_source_docs]
        bm25 = BM25Okapi(tokens)
        return cls(faiss=faiss, bm25=bm25, bm25_docs=bm25_source_docs, bm25_tokens=tokens, k=k)

    def search(self, query: str) -> List[Document]:
        # vector
        vec_hits = self.faiss.similarity_search(query, k=self.k)

        # bm25
        qtok = self._tok(query)
        scores = self.bm25.get_scores(qtok)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[: self.k]
        bm25_hits = [self.bm25_docs[i] for i in top_idx]

        # merge (cheap dedup by metadata+prefix)
        seen = set()
        merged = []
        for d in vec_hits + bm25_hits:
            key = (d.metadata.get("source", ""), d.page_content[:120])
            if key in seen:
                continue
            seen.add(key)
            merged.append(d)
        return merged[: self.k * 2]

# -----------------------------
# Graph nodes
# -----------------------------
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

def decide_node(state: AgentState) -> Dict[str, Any]:
    prompt = f"""
You are an autonomous retrieval agent for internal engineering docs.
Decide next action for answering the user question.

User question:
{state.user_question}

Current working query:
{state.working_query}

Already have {len(state.retrieved)} retrieved docs.
Step {state.step}/{state.max_steps}.

Rules:
- If evidence is empty -> retrieve.
- If evidence exists but likely insufficient/ambiguous -> rewrite OR retrieve.
- If answer is likely possible with citations -> generate.
- If step reached max_steps -> stop.
Return JSON with action and optional rewrite_query.
"""
    decision = llm.with_structured_output(Decide).invoke(prompt)
    if state.step >= state.max_steps:
        return {"action": "stop"}
    return {"action": decision.action, "rewrite_query": decision.rewrite_query}

def retrieve_node_factory(retriever: HybridRetriever):
    def retrieve_node(state: AgentState) -> Dict[str, Any]:
        docs = retriever.search(state.working_query)
        # fingerprint to detect "no new evidence"
        fps = [f'{d.metadata.get("source","")}::{hash(d.page_content[:300])}' for d in docs]
        return {"retrieved": state.retrieved + docs, "evidence_fingerprint": state.evidence_fingerprint + fps}
    return retrieve_node

def rewrite_node(state: AgentState) -> Dict[str, Any]:
    prompt = f"""
Rewrite the search query to retrieve better evidence.
Constraints:
- Keep it short and keyword-rich.
- Include system/component names, error codes, config keys if relevant.
- Avoid generic wording.

User question:
{state.user_question}

Current working query:
{state.working_query}
"""
    new_q = llm.invoke(prompt).content.strip()
    return {"working_query": new_q}

def generate_node(state: AgentState) -> Dict[str, Any]:
    # keep context bounded: take recent N docs (pragmatic)
    docs = state.retrieved[-10:]
    ctx = "\n\n".join([f"[{i}] source={d.metadata.get('source','')}:\n{d.page_content}" for i, d in enumerate(docs)])
    prompt = f"""
Answer the question using ONLY the provided context. If context is insufficient, say what is missing and propose next retrieval query.

Question:
{state.user_question}

Context:
{ctx}

Output:
- Final answer in Korean
- Bullet list of citations like [0], [2] referencing the context items
"""
    ans = llm.invoke(prompt).content
    return {"answer": ans}

def reflect_node(state: AgentState) -> Dict[str, Any]:
    prompt = f"""
Evaluate if the answer is sufficiently grounded and complete.
If insufficient, suggest a better query to retrieve missing evidence.

User question:
{state.user_question}

Answer:
{state.answer}

Retrieved docs count: {len(state.retrieved)}

Return JSON: sufficient, reason, suggest_rewrite(optional)
"""
    c = llm.with_structured_output(Critique).invoke(prompt)
    return {"critique": c.reason, "sufficient": c.sufficient, "suggest_rewrite": c.suggest_rewrite}

# -----------------------------
# Routing logic
# -----------------------------
def route_after_decide(state: AgentState) -> str:
    if state.step >= state.max_steps:
        return "stop"
    action = state.__dict__.get("action")  # not in pydantic model; we'll pass via updates
    return action or "retrieve"

def route_after_reflect(state: AgentState) -> str:
    # stop if sufficient OR no new evidence pattern
    if getattr(state, "sufficient", False):
        return "stop"
    # if fingerprints are repeating too much, stop (loop breaker)
    if len(state.evidence_fingerprint) > 0:
        recent = state.evidence_fingerprint[-12:]
        if len(set(recent)) <= max(3, len(recent)//4):
            return "stop"
    return "rewrite"

def build_app(retriever: HybridRetriever):
    g = StateGraph(AgentState)

    g.add_node("decide", decide_node)
    g.add_node("retrieve", retrieve_node_factory(retriever))
    g.add_node("rewrite", rewrite_node)
    g.add_node("generate", generate_node)
    g.add_node("reflect", reflect_node)

    # edges
    g.set_entry_point("decide")

    # decide -> (retrieve|rewrite|generate|stop)
    def decide_router(state: AgentState):
        # we pass action via state updates from decide_node
        return state.__dict__.get("action", "retrieve")

    g.add_conditional_edges(
        "decide",
        decide_router,
        {
            "retrieve": "retrieve",
            "rewrite": "rewrite",
            "generate": "generate",
            "stop": END,
        },
    )

    g.add_edge("retrieve", "generate")
    g.add_edge("rewrite", "retrieve")
    g.add_edge("generate", "reflect")

    g.add_conditional_edges(
        "reflect",
        lambda s: "stop" if getattr(s, "sufficient", False) else "rewrite",
        {"stop": END, "rewrite": "rewrite"},
    )

    return g.compile()

def load_retriever() -> HybridRetriever:
    faiss = FAISS.load_local(INDEX_DIR, OpenAIEmbeddings(model="text-embedding-3-large"), allow_dangerous_deserialization=True)
    # BM25 source: FAISS에 들어간 원본 chunk를 재사용(실무에선 별도 코퍼스/필터 권장)
    bm25_docs = list(faiss.docstore._dict.values())
    return HybridRetriever.from_faiss(faiss, bm25_docs, k=6)

if __name__ == "__main__":
    retriever = load_retriever()
    app = build_app(retriever)

    q = "배포 후 특정 AZ에서만 502가 나는데, runbook 기준으로 어떤 점검 순서가 맞아?"
    init = AgentState(user_question=q, working_query=q, max_steps=4)

    out = app.invoke(init.model_dump())
    print(out["answer"])
    print("\nCritique:", out.get("critique"))
```

예상 출력(형태):
```text
(한국어 답변 …)
- 점검 순서: (1) ALB target health … (2) 해당 AZ 서브넷 라우팅 … (3) 앱 로그에서 upstream timeout …
- 인용: [0], [3], [7]

Critique: 근거는 충분하나 AZ 단위 라우팅 정책 설명이 일부 추상적임…
```

이 예제의 핵심은 “정답 생성”이 아니라:
- **retrieve를 ‘필요할 때만’ 호출하도록 결정(Decide)**
- **근거 부족 시 rewrite→retrieve 루프**
- **무한 루프 방지(스텝/증거 반복 감지)**

이 뼈대가 있어야 실무에서 *Agentic RAG가 비용을 태우지 않고도 품질을 올리는* 형태가 됩니다. (LangGraph 예제들이 강조하는 지점도 결국 이 그래프 제어입니다.) ([langchain-ai.lang.chat](https://langchain-ai.lang.chat/langgraph/tutorials/rag/langgraph_agentic_rag/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Retrieval tool을 “계층화”하라**
- A-RAG가 제안하듯 keyword/semantic/chunk-read처럼 **granularity가 다른 툴**을 주면, 에이전트가 “대충 탐색→정밀 읽기”로 비용을 줄이기 쉽습니다. ([arxiv.org](https://arxiv.org/abs/2602.03442?utm_source=openai))  
- 실무 구현은 간단합니다: `keyword_search()`, `vector_search()`, `read_chunk(doc_id, span)`를 각각 tool로 노출.

2) **중단조건을 품질 메트릭이 아니라 “예산/증거 변화량”으로도 걸어라**
- “충분하다”는 LLM 판정만 믿으면 과하게 낙관적(또는 무한 재시도)입니다.
- `max_steps`, `no_new_evidence`, `token/cost budget`은 필수. SoK에서도 cost-aware orchestration과 oversight를 중요한 연구/실무 과제로 지적합니다. ([arxiv.org](https://arxiv.org/abs/2603.07379?utm_source=openai))

3) **Observability를 먼저 깔아라**
- tool 호출 횟수, 검색 쿼리 변화, top-k 문서, rerank 결과, reflection reason이 남아야 “왜 망했는지” 디버깅이 됩니다.
- (현실적으로) Langfuse 같은 트레이싱을 붙이는 팀이 많고, 커뮤니티 예제도 관측성을 강하게 강조합니다. ([reddit.com](https://www.reddit.com/r/LangChain/comments/1s9oxpw/agentic_rag_learn_ai_agents_tools_flows_in_one/?utm_source=openai))

### 흔한 함정/안티패턴
- **“검색을 많이 할수록 좋다” 착각**: 검색 노이즈가 누적되면 컨텍스트가 오염되어 답 품질이 떨어집니다. 해결: filter/rerank + 컨텍스트 압축/요약(working memory compression). (커뮤니티 프로젝트들도 context compression을 반복적으로 추가합니다.) ([reddit.com](https://www.reddit.com/r/LangChain/comments/1rffpt5/agentic_rag_for_dummies_v20/?utm_source=openai))
- **문서 스코프 미정**: 멀티 테넌트/멀티 서비스 문서가 섞인 인덱스에서 “비슷한 설정 키”가 충돌하면 답이 그럴듯하게 틀립니다. 해결: retrieval에 `service`, `env`, `repo`, `date` 메타데이터 필터를 1급으로.
- **Reflection이 ‘비평’이 아니라 ‘추가 요청’만 하는 형태**: “부족함”을 감지해도 다음 액션(어떤 쿼리로, 어떤 툴로, 어느 범위를)로 연결되지 않으면 루프가 의미 없습니다. reflection output을 구조화(JSON)하고 라우팅에 사용하세요.

### 비용/성능/안정성 트레이드오프
- Agentic RAG는 기본적으로 **LLM 호출 수가 늘어** 비용/지연이 증가합니다. 대신 “필요할 때만 retrieve”와 “계층 검색”을 잘 설계하면, **단일 거대 모델로 무작정 답을 뽑는 것보다** 총비용이 내려갈 수도 있습니다(쉬운 질문에선 retrieve 생략/저가 모델 라우팅).  
- 자율성을 올릴수록 안정성(무한 루프, 툴 남용) 리스크가 커지므로, OpenAI Agents SDK류가 제공하는 guardrails/검증 계층을 함께 고려하는 팀도 많습니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))

---

## 🚀 마무리
Agentic RAG를 2026년 실무에서 “도입할 만한 기술”로 만드는 포인트는 화려한 멀티에이전트가 아니라, **(1) 루프 제어(중단조건), (2) 계층화된 retrieval tool, (3) 관측/디버깅 가능성, (4) 근거 부족 시 안전한 실패(답변 보류/추가 질문)**입니다. ([arxiv.org](https://arxiv.org/abs/2603.07379?utm_source=openai))

**도입 판단 기준**
- 코퍼스가 커서 “한 번 검색”이 자주 실패하고, 실패를 복구할 방법(재검색/재질문)이 필요하다 → 도입 가치 큼
- 질문 난이도가 낮고 top-k만으로 충분하다 → Traditional RAG + rerank가 더 단순/저렴

**다음 학습 추천(순서)**
1) LangGraph의 agentic RAG 그래프 패턴(상태/루프/중단) ([langchain-ai.lang.chat](https://langchain-ai.lang.chat/langgraph/tutorials/rag/langgraph_agentic_rag/?utm_source=openai))  
2) LlamaIndex의 ReAct + QueryEngine 도구화 방식(툴 인터페이스 설계 참고) ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/examples/agent/react_agent_with_query_engine/?utm_source=openai))  
3) 2026 SoK / A-RAG 논문으로 “계층 retrieval·평가·oversight” 관점 확장 ([arxiv.org](https://arxiv.org/abs/2603.07379?utm_source=openai))

원하시면, 위 코드에 **(a) 메타데이터 필터링(서비스/환경), (b) reranker 추가, (c) chunk-read 툴(A-RAG 스타일), (d) 비용 예산 기반 모델 라우팅**까지 붙여서 “운영 가능한 형태”로 한 단계 더 확장한 버전도 이어서 작성해드릴게요.