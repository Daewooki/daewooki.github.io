---
title: "LLM RAG Agent 튜토리얼: “검색 → 검증 → 재검색”까지 자동화하는 Agentic RAG 설계/구현"
description: "2024~2025년에 RAG를 실제 서비스에 붙여본 팀들이 공통으로 부딪히는 벽이 있습니다. “Vector search로 top-k 뽑고 LLM에 넣는 선형 파이프라인”이 생각보다 쉽게 무너진다는 점입니다."
date: 2025-12-29 02:27:19 +0900
categories: [AI, Tutorial]
tags: [ai, tutorial]
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
2024~2025년에 RAG를 실제 서비스에 붙여본 팀들이 공통으로 부딪히는 벽이 있습니다. **“Vector search로 top-k 뽑고 LLM에 넣는 선형 파이프라인”**이 생각보다 쉽게 무너진다는 점입니다. 질문이 애매하거나, 답이 여러 문서에 흩어져 있거나, 첫 검색 결과가 부정확하면 모델은 그럴듯한 문장을 만들어 내며 실패합니다.

그래서 최근 튜토리얼/프레임워크들이 강조하는 방향은 **Agentic RAG**입니다. “검색”을 한 번 하고 끝내는 게 아니라, **LLM이 도구(tool)를 사용해** 다음을 반복 수행합니다: (1) 질문 재작성, (2) 다중 소스 조회, (3) 검색 결과 품질 평가, (4) 필요 시 재검색/경로 변경. LangChain/LangGraph, LlamaIndex Workflows 같은 오케스트레이션 레이어가 이 흐름을 전제로 발전하고 있습니다.[^1]

---

## 🔧 핵심 개념
### 1) Agentic RAG의 정의: “Retriever를 Tool로 만드는 순간”
전통 RAG는 대개 다음 고정 흐름입니다.

- user query → embedding → vector DB 검색 → top-k context → LLM answer

Agentic RAG는 여기서 **Retriever를 “필요할 때 호출하는 Tool”**로 바꿉니다. 즉, LLM은 “지금은 답을 써야 할지 / 더 찾아야 할지 / 질문을 바꿔야 할지”를 판단하고, 그에 따라 tool call을 수행합니다. IBM의 agentic RAG 튜토리얼도 “agent가 외부 정보/도구를 활용해 멀티스텝으로 자가 수정한다”는 점을 전면에 둡니다.[^1]

### 2) 핵심 루프: Retrieve → Grade → (Rewrite | Generate)
2025년형 구현에서 가장 실전적인 패턴은 아래 3단계 루프입니다.

1. **Retrieve**: 검색(벡터/키워드/웹/DB 등)  
2. **Grade**: 검색 결과가 질문에 “충분히 관련 있는지” LLM/규칙으로 평가  
3. **Rewrite or Generate**:  
   - 관련성이 낮으면: **query rewrite** 후 재검색  
   - 관련성이 높으면: **최종 답변 생성**  

LangGraph 기반 튜토리얼에서도 retrieval 후 “grade_documents” 같은 노드로 relevance를 판정하고, routing으로 rewrite/generate를 분기하는 구성이 대표적입니다.[^2]

### 3) Orchestration 레이어가 중요한 이유: “제어 가능성”
Agentic RAG는 필연적으로 **루프/분기/상태(state)**가 생깁니다. 그래서 프레임워크도 “graph/workflow” 형태로 진화합니다.

- **LlamaIndex Workflows**: event-driven step으로 구성하고, 상태/재시도/관측성을 워크플로우 단위로 다룹니다. 또한 자동 instrument로 Phoenix 같은 observability 도구 연동을 언급합니다.[^3]  
- **LangGraph**: state graph로 노드를 구성하고, tool 호출과 조건 분기를 명시적으로 설계할 수 있는 방향으로 널리 사용됩니다.[^2]  

---

## 💻 실전 코드
아래는 “검색 → 관련성 평가 → (재검색 | 답변)”을 최소 구성으로 구현한 **실행 가능한 Python 예제**입니다.  
전제: 로컬에 문서가 있고, Chroma에 인덱싱한 뒤, LLM이 **retriever tool**을 호출합니다.

```python
# 언어: python
# pip install -U langchain langgraph langchain-openai chromadb tiktoken pydantic

import os
from typing import TypedDict, Literal, List

from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate

from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

# -----------------------------
# 1) Data: 간단 문서 셋업 (데모)
# -----------------------------
docs = [
    Document(page_content="RAG는 Retriever로 관련 문서를 찾아 LLM에 컨텍스트를 주입하는 패턴이다."),
    Document(page_content="Agentic RAG는 LLM이 tool을 사용해 검색/재검색/검증을 반복하며 self-correct한다."),
    Document(page_content="Workflows는 event-driven step으로 멀티스텝 에이전트를 구성하고 관측성을 제공한다."),
]

splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=40)
chunks = splitter.split_documents(docs)

emb = OpenAIEmbeddings(model="text-embedding-3-small")  # 필요 시 환경에 맞게 변경
vs = Chroma.from_documents(chunks, embedding=emb, persist_directory="./chroma_demo")
retriever = vs.as_retriever(search_kwargs={"k": 4})

# -----------------------------
# 2) Tool: Retriever를 tool로 노출
# -----------------------------
@tool
def retrieve(query: str) -> str:
    """벡터 스토어에서 query와 관련된 문서를 검색해 요약 컨텍스트를 반환한다."""
    hits = retriever.get_relevant_documents(query)
    # 실전에서는 (chunk_id, source, page) 같은 metadata를 함께 반환하는 게 좋다.
    return "\n\n".join([f"- {d.page_content}" for d in hits])

tools = [retrieve]

# -----------------------------
# 3) LLM: 도구 호출 + 채점 모델(구조화 출력)
# -----------------------------
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

class Grade(BaseModel):
    """retrieved context가 질문에 충분히 관련 있는지"""
    binary_score: Literal["yes", "no"] = Field(..., description="yes or no")

grader_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a strict relevance grader. Answer only with structured output."),
    ("user", "Question:\n{question}\n\nRetrieved Context:\n{context}\n\nIs the context relevant enough to answer?"),
])

rewrite_prompt = ChatPromptTemplate.from_messages([
    ("system", "Rewrite the user question to improve retrieval. Keep it short and specific."),
    ("user", "{question}"),
])

answer_prompt = ChatPromptTemplate.from_messages([
    ("system", "Answer using ONLY the provided context. If missing, say you don't know."),
    ("user", "Question:\n{question}\n\nContext:\n{context}"),
])

# -----------------------------
# 4) LangGraph State + Nodes
# -----------------------------
class State(TypedDict):
    question: str
    context: str
    attempts: int
    answer: str

MAX_ATTEMPTS = 2

def agent_decide(state: State):
    """
    LLM이 tool을 쓸지 말지 결정.
    여기서는 단순화를 위해 항상 retrieve tool을 호출하도록 유도한다.
    """
    model = llm.bind_tools(tools)
    msg = model.invoke([("user", f"Use the retrieve tool to fetch context for: {state['question']}")])
    return {"messages": [msg]}

def grade_context(state: State) -> dict:
    graded = llm.with_structured_output(Grade).invoke(
        grader_prompt.format_messages(question=state["question"], context=state["context"])
    )
    # yes면 generate, no면 rewrite
    route = "generate" if graded.binary_score == "yes" else "rewrite"
    return {"route": route}

def rewrite_query(state: State) -> State:
    new_q = llm.invoke(rewrite_prompt.format_messages(question=state["question"])).content
    return {**state, "question": new_q, "attempts": state["attempts"] + 1}

def generate_answer(state: State) -> State:
    ans = llm.invoke(answer_prompt.format_messages(question=state["question"], context=state["context"])).content
    return {**state, "answer": ans}

# ToolNode 실행 결과에서 context를 State에 적재하기 위한 후처리
def extract_context(state) -> dict:
    # ToolNode가 messages에 tool output을 넣어준다. 여기서는 마지막 message를 context로 간주(데모).
    last = state["messages"][-1]
    # LangChain message 구조에 따라 content 접근이 달라질 수 있어, 실전에선 타입 체크 필요
    return {"context": getattr(last, "content", str(last))}

# -----------------------------
# 5) Graph Wiring
# -----------------------------
g = StateGraph(State)

# 노드 등록
g.add_node("agent", agent_decide)
g.add_node("tools", ToolNode(tools))
g.add_node("extract_context", extract_context)
g.add_node("rewrite", rewrite_query)
g.add_node("generate", generate_answer)

# 흐름: agent -> tools (tool call) -> extract_context -> grade -> (rewrite|generate)
g.add_edge(START, "agent")
g.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
g.add_edge("tools", "extract_context")

def route_after_grade(state: State) -> str:
    # attempts 초과면 generate로 강제 종료(무한루프 방지)
    if state["attempts"] >= MAX_ATTEMPTS:
        return "generate"
    # grade_context에서 route를 계산
    route = grade_context(state)["route"]
    return route

g.add_conditional_edges("extract_context", route_after_grade, {"rewrite": "rewrite", "generate": "generate"})
g.add_edge("rewrite", "agent")
g.add_edge("generate", END)

app = g.compile()

if __name__ == "__main__":
    init: State = {"question": "2025년 기준 Agentic RAG가 뭐고 왜 쓰나?", "context": "", "attempts": 0, "answer": ""}
    out = app.invoke(init)
    print(out["answer"])
```

이 예제의 포인트는 “RAG” 자체가 아니라 **RAG를 제어하는 루프**입니다. 실전에서는 `grade_context`를 더 정교하게 만들어(예: evidence coverage, contradiction 검사, citation 필수화), “검색 결과가 나쁘면 다시 찾는다”가 실제로 동작하도록 해야 합니다.

---

## ⚡ 실전 팁
1) **무한 루프 방지**는 기능이 아니라 “안전장치”
Agentic RAG는 잘 설계하지 않으면 “rewrite→retrieve→rewrite…”로 비용만 태웁니다. 위 코드처럼 `MAX_ATTEMPTS`를 두고, 초과 시 fallback 응답(“근거 부족”)으로 종료하세요. LangGraph/LlamaIndex Workflows 모두 루프/분기를 전제로 하지만, 종료 조건은 개발자가 책임져야 합니다.[^2]

2) **Grade(평가) 노드가 성능을 좌우한다**
대부분 팀이 “Retriever 튜닝”에만 몰입하는데, Agentic RAG에선 **retrieval 이후의 품질 평가(grade)**가 병목입니다.
- yes/no 이진 분기만으로 부족하면:  
  - `relevance_score`(0~1),  
  - `coverage`(질문 하위요소 충족 여부),  
  - `need_more_sources` 같은 필드를 추가하세요(구조화 출력 강제).

3) **RAG는 ‘chunk’가 아니라 ‘context’를 설계하는 일**
LlamaIndex 쪽에서도 문서 처리/워크플로우를 강조하는 흐름이 강합니다. 단순 split이 아니라 “문서를 AI-friendly하게 변환하고, 에이전트가 쓰기 좋은 형태로 제공”하는 쪽이 2025년의 실전 포인트입니다.[^4]

4) **Observability 없으면 개선 불가능**
Agentic RAG는 노드가 늘고 경로가 분기되기 때문에, “왜 실패했는지”를 추적하지 못하면 운영이 불가능합니다. LlamaIndex Workflows는 워크플로우 단계 관측성(예: Phoenix 연동)을 문서에서 언급합니다.[^3]  
최소한 다음은 로깅/트레이싱하세요:
- query rewrite 전/후
- retrieval top-k와 점수
- grade 결과
- 최종 answer가 참조한 근거 목록

---

## 🚀 마무리
2025년형 RAG 구현의 핵심은 “Vector DB 붙이기”가 아니라, **LLM이 검색을 ‘도구’로 쓰며 스스로 경로를 바꾸는 제어 구조(loops/branches/state)**를 설계하는 데 있습니다. Agentic RAG를 도입하면, 애매한 질문·저품질 검색 결과·다중 문서 종합 같은 실제 문제에서 훨씬 견고해집니다.[^1]

다음 학습 추천(순서):
- LangGraph로 “Retrieve→Grade→Rewrite” 그래프를 2~3가지 변형으로 만들어 보기[^2]  
- LlamaIndex Workflows로 동일 패턴을 event-driven step으로 재구현하며 관측성/재시도/상태 관리를 익히기[^3]  
- 마지막으로, grade 기준을 제품 KPI(정답률/근거 포함률/비용/latency)에 맞춰 수치화하고 실험 루프를 돌리기 (여기서부터가 “진짜 RAG 엔지니어링”입니다)

[^1]: <https://www.ibm.com/think/tutorials/agentic-rag>
[^2]: <https://medium.com/%40mohitagr18/the-ai-that-thinks-before-it-searches-a-deep-dive-into-agentic-rag-82e5db9a0826>
[^3]: <https://docs.llamaindex.ai/en/stable/module_guides/workflow/>
[^4]: <https://docs.llamaindex.ai/en/stable/understanding/>
