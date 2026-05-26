---
title: "Agentic RAG 자율 에이전트 구현, 2026년 5월 기준 “프로덕션”에 올리는 법 (LangGraph 중심)"
date: 2026-05-26 04:14:38 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-05]
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
전통적인 RAG는 “질문 → (고정된) 검색 → 답변”으로 끝납니다. 문제는 현실의 질의가 **(1) 검색이 필요 없는 질문**과 **(2) 한 번의 검색으로는 부족한 질문(멀티홉/용어 불명확/정책-기반 답변)**이 섞여 있다는 점입니다. 이때 고정 파이프라인은 **불필요한 검색 비용**을 내거나, 반대로 **근거 부족 답변(=그럴듯한 환각)**을 만들기 쉽습니다.

Agentic RAG는 검색을 “파이프라인 단계”가 아니라 **에이전트가 호출하는 Tool**로 취급합니다. 즉, 모델이 스스로 “검색할지/어떻게 검색할지/결과가 충분한지/재검색할지”를 결정하는 패턴입니다. ([genaipatterns.dev](https://www.genaipatterns.dev/patterns/rag/agentic-rag?utm_source=openai))

**언제 쓰면 좋은가**
- 고객지원/사내 위키/정책·매뉴얼처럼 **근거가 중요하고, 질문 품질이 들쭉날쭉**한 도메인
- 멀티홉(“A가 B에 미치는 영향과 예외 조항까지”)처럼 **한 번의 top-k로 끝나지 않는** 질의
- 운영 중에 “왜 이런 답이 나왔지?”를 추적해야 하는 **감사(audit)/트레이싱 요구**가 있는 서비스(관측성 필요) ([langfuse.com](https://langfuse.com/?utm_source=openai))

**언제 쓰면 안 되는가**
- 대부분 질문이 단순 FAQ이고, 검색 코퍼스가 작아 **고정 RAG로도 충분**할 때(에이전트 루프는 비용·지연을 늘림)
- “툴 호출”이 곧 **실제 write/action**(결제, 티켓 종료, DB 업데이트)로 이어지는 고위험 업무에서 통제가 약할 때(에이전트는 objective drift/실수 리스크가 커짐) ([techradar.com](https://www.techradar.com/pro/navigating-the-rise-of-agentic-ai-in-2026?utm_source=openai))

---

## 🔧 핵심 개념
### 1) 주요 개념 정의
- **Agentic RAG**: retrieval을 고정 단계가 아니라 에이전트의 계획/반성 루프 안에 둔 RAG. “검색=도구 호출”이며 반복 가능. ([genaipatterns.dev](https://www.genaipatterns.dev/patterns/rag/agentic-rag?utm_source=openai))
- **Router / Query Rewriter**: 원 질문을 그대로 던지지 않고, 검색에 맞게 재작성하거나(쿼리 확장/약어 풀기) 어떤 retriever를 쓸지 결정.
- **Grader (Document/Answer)**: 검색 결과가 질문에 충분히 관련 있는지, 답변이 근거에 의해 지지되는지 평가하고 다음 행동(재검색/종료)을 결정. LangGraph 예제는 `grade_documents`가 다음 노드를 선택하는 형태를 보여줍니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))
- **Bounded loop**: 무한 루프 방지를 위해 최대 반복 수, 예산, 시간 제한을 두는 운영 장치.

### 2) 내부 작동 방식(흐름)
프로덕션 관점에서 Agentic RAG는 보통 아래 “결정 지점”을 가진 상태 머신입니다.

1. **Intent 판별**: 이 질문은 검색이 필요한가?
2. **Plan**: 필요한 정보가 무엇인지(키워드/엔티티/기간/정책 버전) 분해
3. **Retrieve**: 하이브리드 검색(BM25 + vector) + 필터(테넌트/권한/문서 타입)
4. **Rerank**: cross-encoder 또는 LLM rerank로 상위 문서 정밀도 확보
5. **Grade**: “관련성/충분성” 평가 → 부족하면 **query rewrite 후 재검색**
6. **Generate**: 인용(quote/citation) 가능한 근거를 컨텍스트로 답변
7. **Answer check**: 근거 미달이면 “모름/추가 질문”으로 종료(여기서 과감히 fail-closed)

이런 구조가 “고정 RAG 대비” 강한 이유는, 검색 실패를 **한 번의 top-k 실패로 끝내지 않고** “재시도 전략(다른 키워드/다른 retriever/다른 필터)”으로 복구하기 때문입니다. Agentic RAG를 “순차 의사결정 시스템”으로 보는 연구/정리도 나왔고, 아키텍처가 파편화되어 평가가 중요하다는 문제의식이 정리되어 있습니다. ([arxiv.org](https://arxiv.org/abs/2603.07379?utm_source=openai))

### 3) 다른 접근과의 차이점
- **Traditional RAG**: 단일 retrieve → generate. 단순/빠름. 하지만 “검색 실패 복구”가 약함.
- **Self-RAG / Corrective 계열**: “검색 결과/답변을 스스로 평가하고 보정” 루프를 명시적으로 넣음(Agentic RAG의 하위 패턴으로 많이 구현). LangGraph 튜토리얼이 이 방향을 잘 보여줍니다. ([langchain-ai.lang.chat](https://langchain-ai.lang.chat/langgraph/tutorials/rag/langgraph_self_rag/?utm_source=openai))
- **Workflow 기반(이벤트/스텝)**: LlamaIndex Workflows처럼 이벤트 기반 step으로 루프/분기/재시도를 구조화(운영 안정성에 유리). ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/module_guides/workflow/?utm_source=openai))

---

## 💻 실전 코드
아래는 “사내 정책 문서(수백~수천 개)”를 대상으로 한 **Agentic RAG 고객지원 에이전트** 예시입니다. 포인트는 toy가 아니라:
- 하이브리드 검색 + rerank
- 문서 관련성 grading → 쿼리 rewrite → 재검색
- 반복 횟수 제한(budget)
- 운영을 위한 trace(최소한 로그 구조)

> 전제: 문서 인덱싱은 이미 되어 있고(예: Elasticsearch + vector, 또는 별도 vector DB), 여기서는 “검색 API”가 있다고 가정합니다.

### 0) 의존성/환경 변수
```bash
python -m venv .venv
source .venv/bin/activate
pip install langgraph langchain openai pydantic httpx python-dotenv
export OPENAI_API_KEY="..."
```

### 1) “검색 Tool” + “상태” 정의
```python
# agentic_rag.py
from __future__ import annotations
import os, json
from typing import List, Literal, Optional, TypedDict
import httpx
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ---- State ----
class RagState(TypedDict):
    user_question: str
    rewritten_question: Optional[str]
    retrieved_docs: List[dict]          # [{"id":..., "title":..., "text":..., "score":...}]
    answer: Optional[str]
    loop: int
    max_loops: int
    trace: List[dict]                  # step-by-step breadcrumbs

# ---- Tool: hybrid search endpoint (your infra) ----
async def hybrid_search(query: str, k: int = 8, tenant_id: str = "acme") -> List[dict]:
    """
    실제로는:
    - BM25 + vector search
    - ACL filter(tenant_id, role)
    - 최신 버전 우선(policy_version)
    - rerank(optional)
    를 서버에서 처리하는 것을 권장.
    """
    url = "http://localhost:8080/search"
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.post(url, json={"query": query, "k": k, "tenant_id": tenant_id})
        r.raise_for_status()
        return r.json()["hits"]

# ---- LLM helpers ----
def llm_json(schema_hint: str, prompt: str) -> dict:
    # Responses/Chat 어느 쪽이든 "JSON only" 강제. (여기선 간단화)
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": f"Return ONLY valid JSON. Schema: {schema_hint}"},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)

def llm_text(prompt: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content
```

### 2) 노드: 검색 필요성 판단 → 검색 → 문서 grading → 재작성 루프
```python
class NeedSearch(BaseModel):
    need_search: bool = Field(...)
    reason: str = Field(...)

def decide_need_search(state: RagState) -> RagState:
    q = state["user_question"]
    out = llm_json(
        "need_search:boolean, reason:string",
        f"""
질문이 사내 정책/문서 근거를 필요로 하면 need_search=true.
개인 의견/일반 상식/코딩 문법 수준이면 false.

question: {q}
"""
    )
    state["trace"].append({"node": "decide_need_search", "out": out})
    if not out["need_search"]:
        state["answer"] = llm_text(f"다음 질문에 답해줘. 근거 문서 없이도 확실한 경우에만 답하고, 아니면 '문서 확인 필요'라고 말해.\n\n질문: {q}")
    return state

def rewrite_question(state: RagState) -> RagState:
    base_q = state["user_question"]
    prev = state.get("rewritten_question") or base_q
    out = llm_json(
        "query:string",
        f"""
너는 검색 쿼리 최적화기다. 약어를 풀고, 핵심 엔티티/조건(기간, 예외, 버전)을 포함해
하이브리드 검색에 잘 걸리도록 한국어 키워드 중심으로 1문장 쿼리를 만들어라.
불필요한 수식/장문 제거.

원문: {base_q}
이전쿼리: {prev}
"""
    )
    state["rewritten_question"] = out["query"]
    state["trace"].append({"node": "rewrite_question", "query": out["query"]})
    return state

async def retrieve(state: RagState) -> RagState:
    q = state["rewritten_question"] or state["user_question"]
    hits = await hybrid_search(q, k=10)
    state["retrieved_docs"] = hits
    state["trace"].append({"node": "retrieve", "k": 10, "hit_ids": [h["id"] for h in hits]})
    return state

class GradeDocs(BaseModel):
    decision: Literal["generate", "rewrite"] = Field(...)
    reason: str = Field(...)

def grade_documents(state: RagState) -> RagState:
    q = state["user_question"]
    docs = state["retrieved_docs"][:6]
    snippet = "\n\n".join([f"[{d['id']}] {d['title']}\n{d['text'][:400]}" for d in docs])

    out = llm_json(
        "decision:'generate'|'rewrite', reason:string",
        f"""
질문: {q}

아래 문서들이 질문에 답하기에 충분히 관련 있고(관련성),
정책/절차/조건이 직접적으로 포함되어 있으면 generate.
그렇지 않으면 rewrite로 보내라(다른 키워드 필요).

docs:
{snippet}
"""
    )
    state["trace"].append({"node": "grade_documents", "out": out})
    return state
```

### 3) 답변 생성 + 루프 제한
```python
def generate_answer(state: RagState) -> RagState:
    q = state["user_question"]
    docs = state["retrieved_docs"][:6]
    context = "\n\n".join([f"({d['id']}) {d['title']}\n{d['text']}" for d in docs])

    state["answer"] = llm_text(f"""
너는 사내 고객지원 엔지니어다.
반드시 아래 context에서만 근거를 가져오고, 각 문장 끝에 (doc_id)로 출처를 남겨라.
context에 없으면 '확인 불가'라고 말하고, 추가로 필요한 정보를 질문해라.

question: {q}

context:
{context}
""")
    state["trace"].append({"node": "generate_answer", "answer_len": len(state["answer"])})
    return state

def bump_loop(state: RagState) -> RagState:
    state["loop"] += 1
    return state

def route_after_grade(state: RagState) -> str:
    # max loop guard
    if state["loop"] >= state["max_loops"]:
        return "stop"
    # read last grade
    last = next(x for x in reversed(state["trace"]) if x["node"] == "grade_documents")["out"]
    return last["decision"]

def stop(state: RagState) -> RagState:
    if not state.get("answer"):
        state["answer"] = "관련 문서를 충분히 찾지 못했습니다. (1) 제품/모듈명 (2) 적용 날짜/버전 (3) 현재 상황을 알려주시면 재검색하겠습니다."
    state["trace"].append({"node": "stop"})
    return state

def build_graph():
    g = StateGraph(RagState)

    g.add_node("decide_need_search", decide_need_search)
    g.add_node("rewrite_question", rewrite_question)
    g.add_node("retrieve", retrieve)
    g.add_node("grade_documents", grade_documents)
    g.add_node("generate_answer", generate_answer)
    g.add_node("bump_loop", bump_loop)
    g.add_node("stop", stop)

    g.add_edge(START, "decide_need_search")

    # need_search가 false면 answer가 채워지고 종료
    def route_after_need_search(state: RagState) -> str:
        return "search" if state.get("answer") is None else "done"

    g.add_conditional_edges("decide_need_search", route_after_need_search, {"search": "rewrite_question", "done": END})

    g.add_edge("rewrite_question", "retrieve")
    g.add_edge("retrieve", "grade_documents")

    g.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {"generate": "generate_answer", "rewrite": "bump_loop", "stop": "stop"}
    )
    g.add_edge("bump_loop", "rewrite_question")
    g.add_edge("generate_answer", END)
    g.add_edge("stop", END)
    return g.compile()

async def run(question: str):
    app = build_graph()
    state: RagState = {
        "user_question": question,
        "rewritten_question": None,
        "retrieved_docs": [],
        "answer": None,
        "loop": 0,
        "max_loops": 2,
        "trace": [],
    }
    out = await app.ainvoke(state)
    return out

if __name__ == "__main__":
    import asyncio
    q = "VPN 접속이 자꾸 끊기는데, 재인증 정책이 어떻게 돼? 예외 신청 절차도 알려줘."
    result = asyncio.run(run(q))
    print(result["answer"])
    print("\n--- TRACE (debug) ---")
    for t in result["trace"]:
        print(t)
```

**예상 출력(형태)**
- 답변 본문에는 각 문장 끝에 `(doc_id)`가 붙고
- TRACE에는 `rewrite_question`에서 어떤 쿼리로 바뀌었는지, `grade_documents`가 왜 rewrite를 택했는지 남습니다.

> 구현 자체는 LangGraph의 “agentic RAG에서 grading 노드가 다음 노드를 선택한다”는 문서 패턴을 그대로 가져오되, 프로덕션에서 필요한 loop guard/trace를 추가한 형태입니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3가지)
1) **Grader는 “관련성”과 “충분성”을 분리**
- 관련성: 질문 주제와 맞나?
- 충분성: 정책 조건/예외/절차가 “답을 만들 만큼” 들어있나?
관련성만 보면 “비슷한 문서”로도 답을 만들어 환각을 유도합니다. LangGraph류 예제도 grading을 의사결정 포인트로 둡니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))

2) **Bounded autonomy: loop / cost / time budget을 상태에 넣어라**
- max_loops(예: 2~3)
- max_context_tokens(문서 길이 제한)
- tool 호출 비용 상한
에이전트형은 실패 모드가 “한 번 틀림”이 아니라 “계속 헤맴”으로 바뀝니다(지연/비용 폭증).

3) **관측성(Tracing/Evals)을 MVP부터 붙여라**
Agentic RAG는 분기/루프 때문에 “왜 이 답이 나왔는지”가 곧 디버깅 난이도입니다. Langfuse는 trace + cost/latency + eval을 한 워크플로로 묶는 쪽으로 포지셔닝합니다. ([langfuse.com](https://langfuse.com/?utm_source=openai))  
또한 RAG 평가 프레임워크(RAGAS 등)로 회귀 테스트를 돌려 “릴리즈마다 검색 품질이 떨어지는지”를 잡는 게 현실적으로 중요합니다. ([arxiv.org](https://arxiv.org/abs/2309.15217?utm_source=openai))

### 흔한 함정/안티패턴
- **“에이전트가 알아서 잘 하겠지”**: tool 스펙(입력/출력 스키마), 필터(ACL), 실패 처리(타임아웃/빈 결과)를 엄격히 안 하면 품질보다 먼저 사고가 납니다.
- **쿼리 rewrite 무제한**: rewrite는 강력하지만, 코퍼스 특성(용어 체계)을 모르면 점점 멀어질 수 있습니다. rewrite 전/후 쿼리를 trace로 남기고, 특정 패턴에서만 허용하세요.
- **Rerank를 LLM에만 의존**: LLM rerank는 비용·지연이 크고 변동성이 있습니다. 가능하면 cheap rerank(전용 모델/캐시) + LLM은 “최종 애매한 케이스”로 제한.

### 비용/성능/안정성 트레이드오프
- **정확도 vs 지연**: loop 1회 추가는 보통 수 초 단위 지연을 만듭니다. “rewrite는 1회까지만”, “rerank는 top-30에만” 같은 가드가 필요.
- **Grounding 강화 vs 컨텍스트 폭발**: 많이 넣을수록 좋아 보이지만, 컨텍스트가 커지면 오히려 답변이 흐려집니다(핵심 문단만 추출/요약하는 전처리가 필요).
- **자율성 vs 리스크**: 에이전트가 실제 action을 하게 만들수록 통제·감사·승인(HITL) 설계가 필수입니다(특히 보안/규정). ([itpro.com](https://www.itpro.com/security/five-eyes-agencies-sound-alarm-over-risky-agentic-ai-deployments?utm_source=openai))

---

## 🚀 마무리
2026년 5월 기준 Agentic RAG의 실전 포인트는 “멋진 에이전트 데모”가 아니라,
- **검색을 도구화**하고(필요할 때만, 여러 번)
- **grading/validation을 분기점으로** 만들며
- **loop/cost/trace를 제품 스펙으로** 박아 넣는 것입니다. ([genaipatterns.dev](https://www.genaipatterns.dev/patterns/rag/agentic-rag?utm_source=openai))

**도입 판단 기준**
- 질문의 30% 이상이 “한 번의 검색으로는 부족”하거나, 검색 실패 시 비용이 큰가? → Agentic RAG 고려
- 답변에 대한 감사/근거 요구가 강한가? → grading + citation + tracing 우선
- latency 예산이 빡빡한가(예: <1s)? → 고정 RAG + 일부 케이스만 agentic fallback 권장

**다음 학습 추천**
- LangGraph의 agentic RAG / Self-RAG 튜토리얼로 “분기/루프 설계” 감 잡기 ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/agentic-rag?utm_source=openai))  
- LlamaIndex Workflows처럼 이벤트 기반 워크플로로 “재시도/타임아웃/서비스화” 설계 보기 ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/module_guides/workflow/?utm_source=openai))  
- RAGAS로 평가 자동화(회귀 테스트) 체계 만들기 ([arxiv.org](https://arxiv.org/abs/2309.15217?utm_source=openai))  
- Langfuse로 trace+eval+cost를 묶어 운영 루프 만들기 ([langfuse.com](https://langfuse.com/?utm_source=openai))