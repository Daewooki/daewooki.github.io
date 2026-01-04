---
title: "2025년형 LLM RAG 에이전트 구현 튜토리얼: LangGraph + (OpenAI Responses/File Search)로 “검색→판단→생성→검증” 루프 만들기"
date: 2026-01-03 02:08:36 +0900
categories: [AI, Tutorial]
tags: [ai, tutorial, trend, 2026-01]
---

<div class="pageviews" style="margin: 0.25rem 0 1rem; opacity: 0.8;">
  <span style="font-weight: 600;">조회수</span>: <span id="pv-post">-</span>
</div>
<script defer src="/assets/js/pageviews.js"></script>


## 들어가며
2023~2024년의 “단순 RAG”는 **질문 → retrieve → LLM 답변**의 직선 파이프라인이 주류였지만, 2025년 실무에서는 이 구조가 쉽게 한계에 부딪힙니다. 예를 들어 사용자의 질문이 (1) 검색이 필요 없는 상식인지, (2) 내부 문서 기반인지, (3) 웹 최신 정보가 필요한지, (4) 검색 결과 품질이 낮아 재질의/재랭킹이 필요한지 등을 **매번 고정 파이프라인으로 처리하면 비용/지연/환각이 폭증**합니다.

그래서 2025년에는 “Agentic RAG”가 표준에 가까워졌습니다. 핵심은 **LLM이 도구(tool)를 ‘필요할 때만’ 호출**하고, 결과를 보고 **루프를 돌며 품질을 끌어올리는 제어 구조**를 갖추는 것입니다. LangGraph는 이런 “상태(state)+분기(conditional edge)+루프(loop)”를 그래프 구조로 안정적으로 구현하도록 가이드합니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))  
또한 OpenAI는 Responses API와 built-in tool(웹 검색, file search 등), 그리고 에이전트 오케스트레이션을 위한 Agents SDK를 공개해 “에이전트 + 검색”을 제품 레벨 구성요소로 제공하기 시작했습니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Agentic RAG의 정의
- **RAG**: LLM이 답변하기 전에 외부 지식(문서/DB/웹)에서 근거를 가져와 답변 품질을 올리는 방식
- **Agentic RAG**: “항상 검색”이 아니라, **LLM이 상황을 판단해 검색/재검색/요약/검증을 단계적으로 수행**하는 방식  
  - 예: 질문 난이도 분류 → 내부 문서 검색 → 근거 부족 시 질의 재작성(rewrite) → 재검색 → 답변 생성 → 근거 정합성 검사

LangGraph의 “retrieval agent” 튜토리얼도 이 포인트를 강조합니다. 즉, 에이전트가 **retriever tool을 호출할지 말지 결정**하는 것이 출발점입니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))

### 2) 왜 그래프(State Machine)가 필요한가
에이전트는 필연적으로 “여러 턴/여러 도구/여러 분기”를 갖습니다.
- 상태 예시: `messages`, `query`, `retrieved_docs`, `citations`, `retry_count`
- 노드 예시: `route`, `retrieve`, `rewrite`, `generate`, `grounding_check`
- 엣지 예시: `route -> retrieve` 또는 `route -> generate`, `grounding_fail -> rewrite`

이걸 if-else로 덕지덕지 붙이면 관측(Tracing), 재실행, 루프 제한 같은 운영 요소가 망가지는데, LangGraph는 이를 그래프 프리미티브로 정리해줍니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))

### 3) “도구 표준화” 관점: MCP가 뜨는 이유
2025년에는 도구 연결이 프레임워크마다 제각각이어서 재사용이 어렵다는 문제가 커졌고, 이를 해결하려는 흐름 중 하나가 **Model Context Protocol(MCP)** 입니다. MCP는 JSON-RPC 기반으로 “tool/resource/prompt” 등을 서버가 표준 인터페이스로 제공하도록 정의합니다. ([modelcontextprotocol.io](https://modelcontextprotocol.io/specification/2025-11-25/basic?utm_source=openai))  
즉, 장기적으로는 “RAG용 retriever”도 MCP tool로 노출해 **에이전트/클라이언트가 바뀌어도 동일 도구를 재사용**하는 방향이 유리합니다.

---

## 💻 실전 코드
아래 코드는 **LangGraph로 Agentic RAG의 최소 실전형 뼈대**를 만듭니다.

- `route`: 검색 필요 여부 판단  
- `retrieve`: VectorStore 검색(예시는 로컬 Chroma)  
- `rewrite`: 검색이 부실하면 질의를 재작성  
- `generate`: 최종 답변 생성(근거 포함)  
- `grounding_check`: 답변이 근거에 “기댔는지” 간단 점검 후 루프

> 실행 전: `pip install -U langgraph langchain langchain-community langchain-text-splitters chromadb langchain-openai`  
> 환경변수: `OPENAI_API_KEY`

```python
from __future__ import annotations

from typing import TypedDict, List, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma


# -----------------------------
# 1) 상태 정의: 그래프가 들고 다닐 데이터
# -----------------------------
class RAGState(TypedDict):
    messages: List[BaseMessage]
    query: str
    retrieved: List[Document]
    retry: int


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
emb = OpenAIEmbeddings()

# -----------------------------
# 2) (예시) 아주 작은 문서 코퍼스 구축
#    - 실무에서는 PDF/HTML/DB 등 ingestion 파이프라인을 별도로 둡니다.
# -----------------------------
raw_docs = [
    Document(page_content="LangGraph는 상태 기반 그래프로 LLM 워크플로우를 구성한다."),
    Document(page_content="Agentic RAG는 검색 여부 판단, 재질의, 검증 루프를 포함한다."),
    Document(page_content="Retrieval 품질이 낮으면 query rewrite, rerank, hybrid search를 고려한다."),
]

splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=40)
chunks = splitter.split_documents(raw_docs)

vs = Chroma.from_documents(chunks, embedding=emb, collection_name="rag_demo")
retriever = vs.as_retriever(search_kwargs={"k": 4})


# -----------------------------
# 3) 노드 구현
# -----------------------------
def route(state: RAGState) -> Literal["retrieve", "generate"]:
    """
    LLM이 '검색이 필요한 질문인지' 판단.
    """
    q = state["query"]
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "너는 라우터다. 사용자의 질문이 내부 지식(문서 검색) 기반 답변이 필요한지 판단한다. "
         "검색이 필요하면 'retrieve', 아니면 'generate'만 출력한다."),
        ("human", "{q}")
    ])
    decision = llm.invoke(prompt.format_messages(q=q)).content.strip().lower()
    return "retrieve" if "retrieve" in decision else "generate"


def retrieve(state: RAGState) -> RAGState:
    docs = retriever.get_relevant_documents(state["query"])
    return {**state, "retrieved": docs}


def rewrite(state: RAGState) -> RAGState:
    """
    검색 품질이 낮을 때 질의를 재작성(의도 보존 + 키워드 강화).
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "너는 검색 질의 최적화기다. 원 질문의 의도를 보존하면서 검색에 유리하게 질의를 1개로 재작성하라."),
        ("human", "원 질문: {q}\n현재 검색 결과가 부실함. 더 구체적인 검색 질의로 바꿔줘.")
    ])
    new_q = llm.invoke(prompt.format_messages(q=state["query"])).content.strip()
    return {**state, "query": new_q, "retry": state["retry"] + 1}


def generate(state: RAGState) -> RAGState:
    """
    retrieved 컨텍스트가 있으면 근거 기반 답변 생성.
    """
    context = "\n\n".join([f"- {d.page_content}" for d in state.get("retrieved", [])])
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "너는 시니어 개발자다. 주어진 CONTEXT를 우선 근거로 사용해 답변하라. "
         "근거가 부족하면 '추가 정보 필요'를 명시하라."),
        ("human", "QUESTION: {q}\n\nCONTEXT:\n{context}")
    ])
    answer = llm.invoke(prompt.format_messages(q=state["query"], context=context)).content
    msgs = state["messages"] + [AIMessage(content=answer)]
    return {**state, "messages": msgs}


def grounding_check(state: RAGState) -> Literal["end", "rewrite"]:
    """
    매우 단순한 groundedness 체크:
    - retrieved가 비었거나,
    - 답변에 '추가 정보 필요'가 뜨거나,
    - 재시도 여지가 있으면 rewrite로 루프
    """
    if state["retry"] >= 2:
        return "end"
    if not state.get("retrieved"):
        return "rewrite"
    last = state["messages"][-1].content if state["messages"] else ""
    if "추가 정보 필요" in last:
        return "rewrite"
    return "end"


# -----------------------------
# 4) 그래프 연결
# -----------------------------
g = StateGraph(RAGState)

g.add_node("retrieve", retrieve)
g.add_node("rewrite", rewrite)
g.add_node("generate", generate)

g.add_conditional_edges(START, route, {
    "retrieve": "retrieve",
    "generate": "generate",
})

g.add_edge("retrieve", "generate")
g.add_conditional_edges("generate", grounding_check, {
    "rewrite": "rewrite",
    "end": END,
})
g.add_edge("rewrite", "retrieve")

app = g.compile(checkpointer=MemorySaver())


# -----------------------------
# 5) 실행
# -----------------------------
if __name__ == "__main__":
    question = "Agentic RAG에서 LangGraph를 쓰는 이유를 실무 관점으로 설명해줘"
    init_state: RAGState = {
        "messages": [HumanMessage(content=question)],
        "query": question,
        "retrieved": [],
        "retry": 0,
    }

    out = app.invoke(init_state)
    print(out["messages"][-1].content)
```

이 형태가 “2025년형 튜토리얼”로 중요한 이유는, 단순 RAG 샘플이 아니라 **(1) 라우팅, (2) 검색, (3) 재질의 루프, (4) 종료 조건**이 들어가서 실제 운영 시나리오에 가까워지기 때문입니다. 또한 LangGraph 문서가 말하는 핵심(상태/노드/조건부 엣지)을 그대로 코드로 옮겼습니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))

---

## ⚡ 실전 팁
1) **검색은 “항상”이 아니라 “조건부”로**
- 질문의 타입(FAQ/정의/정책/최신 뉴스/사내 문서)을 분류해 **retrieve를 최소화**해야 비용과 latency가 줄고, 불필요한 컨텍스트 주입으로 인한 성능 저하도 줄어듭니다. (LangGraph의 retrieval agent 방향과 일치) ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))

2) **retrieval 품질이 낮을 때의 “플랜 B”를 그래프에 박아라**
- query rewrite(키워드 강화), top-k 확대, rerank, hybrid search(BM25+vector) 같은 보정 전략은 “예외 처리”가 아니라 **핵심 플로우**입니다.  
- 중요한 건 “무한 루프 방지”: `retry` 카운터와 종료 조건을 상태에 반드시 두세요.

3) **관측(Observability)을 처음부터 설계**
- 에이전트는 디버깅이 곧 제품 품질입니다. LangGraph 계열에서는 LangSmith 같은 트레이싱 도구를 붙여 병목/환각 패턴을 찾는 접근이 문서에서도 권장됩니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))  
- OpenAI 쪽도 에이전트 빌딩 블록과 함께 tracing/inspect를 강조합니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))

4) **도구 연결의 미래: MCP 고려**
- 사내에서 retriever, 정책 조회, 권한 체크 같은 도구가 늘어나면 “프레임워크 종속”이 바로 비용이 됩니다. MCP처럼 JSON-RPC 기반 표준으로 tool을 노출하면 장기 유지보수성이 좋아집니다. ([modelcontextprotocol.io](https://modelcontextprotocol.io/specification/2025-11-25/basic?utm_source=openai))

5) **OpenAI built-in File Search vs 직접 VectorStore**
- 빠르게 MVP를 만들고 운영 복잡도를 줄이려면 OpenAI의 file search 같은 managed retrieval을 고려할 수 있습니다(쿼리 최적화/metadata filtering/reranking 지원을 강조). ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))  
- 반대로 규제/비용/커스터마이징(자체 reranker, hybrid, 도메인 특화 chunking)이 중요하면 직접 VectorStore+pipeline이 유리합니다. 실무에선 두 접근을 혼합하기도 합니다(핵심 문서는 managed, 대규모 로그/데이터는 사내 검색).

---

## 🚀 마무리
2025년의 RAG 구현은 “Vector DB 붙이고 끝”이 아니라, **에이전트 제어 구조(라우팅/루프/검증) + 도구 생태계(Responses API, LangGraph, MCP 등)**를 어떻게 조합하느냐가 승부처입니다.  
추천 다음 학습 루트는:
- LangGraph의 “custom RAG agent” 패턴을 확장해 **rerank/grounding evaluator/웹 검색 분기**를 그래프에 추가하기 ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))  
- OpenAI Responses API의 built-in tool(웹 검색, file search) 기반으로 **도구 호출+관측**을 제품 수준으로 끌어올리기 ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))  
- 조직 단위로는 MCP를 염두에 두고 tool 인터페이스를 정리해 **에이전트 프레임워크 교체 비용을 낮추는 구조**를 설계하기 ([modelcontextprotocol.io](https://modelcontextprotocol.io/specification/2025-11-25/basic?utm_source=openai))

원하시면, 위 코드에 **(1) reranker 추가, (2) “답변-근거 정합성” LLM grader, (3) 웹 검색 노드, (4) 캐시/메모리/세션 컨텍스트 유지**까지 포함한 “프로덕션형 그래프”로 확장 버전도 이어서 작성해드릴게요.