---
title: "2025년형 LLM RAG 에이전트 튜토리얼: “retrieve→answer”를 넘어 “plan→search→grade→rewrite”로 진화시키기"
date: 2025-12-23 02:12:52 +0900
categories: [AI, Tutorial]
tags: [ai, tutorial, trend, 2025-12]
---

<div class="pageviews" style="margin: 0.25rem 0 1rem; opacity: 0.8;">
  <span style="font-weight: 600;">조회수</span>: <span id="pv-post">-</span>
</div>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
<script defer src="/assets/js/pageviews.js"></script>


## 들어가며
2024년까지의 전형적인 RAG는 “질문 → vector search → top-k 컨텍스트 → LLM 답변”이라는 단선형 파이프라인이었습니다. 문제는 이 구조가 **사용자 질문이 모호**하거나, **첫 검색 결과가 부정확**하거나, **답이 여러 소스에 흩어져** 있을 때 급격히 취약해진다는 점입니다. 그래서 2025년에는 “RAG + Agent”가 사실상 표준 패턴으로 자리 잡았습니다. 핵심은 LLM이 단순 생성기가 아니라, **도구(tool)를 선택하고 루프를 돌며 품질을 스스로 검증**하는 오케스트레이터가 되는 것입니다(일명 Agentic RAG). ([medium.com](https://medium.com/%40mohitagr18/the-ai-that-thinks-before-it-searches-a-deep-dive-into-agentic-rag-82e5db9a0826))

이번 글은 “기술 심층 분석 + 구현 튜토리얼”로, **(1) retrieval tool**, **(2) document grading**, **(3) query rewrite & retry**, **(4) state 유지(메모리/컨텍스트)** 를 한 번에 묶어, 실무에서 바로 쓸 수 있는 RAG agent 골격을 제공합니다. LlamaIndex가 공식 문서에서 말하는 “RAG pipeline → agent → workflows” 계층을 기준으로 개념을 정리하고, 코드 구현은 범용적으로 작성하겠습니다. ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/understanding/))

---

## 🔧 핵심 개념
### 1) Agentic RAG의 정의: “검색”이 아니라 “조사(Research)”
Agentic RAG는 LLM이 아래를 **상태(state)** 와 함께 반복 수행하는 구조입니다.

- **Plan**: 지금 필요한 정보가 무엇인지(어떤 소스/어떤 키워드/어떤 범위)
- **Tool use**: retriever/search tool 호출(벡터 검색, 요약, 웹 검색 등)
- **Grade**: 가져온 근거가 질문에 충분히 relevant/complete 한지 평가
- **Rewrite**: 부족하면 질문을 재작성해 재검색(루프)
- **Answer**: 충분한 근거가 모이면 최종 답변 생성 + 근거 인용/출처 노드 보관

LangGraph 튜토리얼에서 강조하는 포인트도 결국 이 “rewrite and retry” 루프가 기존 RAG의 경직성을 깨는 핵심이라는 점입니다. ([medium.com](https://medium.com/%40mohitagr18/the-ai-that-thinks-before-it-searches-a-deep-dive-into-agentic-rag-82e5db9a0826))

### 2) Tool 설계가 성능을 결정한다: “retrieval을 함수로 만들기”
RAG 에이전트에서 retrieval은 보통 **Function Tool** 로 제공됩니다. 즉 “벡터 검색 함수”가 도구가 되고, LLM이 인자를 채워 호출합니다. 예를 들어 LlamaIndex 예제에서는 page number 같은 metadata filter를 인자로 받아 **필터링된 vector search**를 수행하고, LLM이 이를 추론해 호출하는 패턴을 보여줍니다. ([medium.com](https://medium.com/%40samad19472002/agentic-rag-application-using-llamaindex-tool-calling-30bfef6cb4fb?utm_source=openai))  
이게 중요한 이유는:
- 검색 파라미터(top_k, filters, namespace, recency 등)를 **LLM이 동적으로 선택** 가능
- “한 번의 검색”이 아니라 “검색→추가검색→요약→교차검증”으로 확장 가능

### 3) State(메모리) 없이는 에이전트가 ‘누적 학습’하지 못한다
에이전트가 루프를 돌면, 이전 검색 결과/시도한 쿼리/실패 이유를 저장해야 비용과 지연이 줄어듭니다. LlamaIndex의 Workflow/AgentWorkflow 계열은 context에 state를 저장하고 툴에서 읽고 쓰는 패턴을 공식적으로 제공합니다. ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/examples/agent/agent_workflow_basic/))  
실무적으로는 아래를 state로 잡으면 효과가 큽니다.
- `attempts`: 재시도 횟수
- `last_query`: 직전 검색 쿼리
- `evidence`: 누적된 근거 chunk 목록
- `missing_points`: 아직 답에 필요한 항목(체크리스트)

---

## 💻 실전 코드
아래 코드는 **Agentic RAG의 최소 실전 골격**입니다.

- `retrieve()` : vector DB에서 근거 텍스트 가져오는 tool (여기서는 예시로 더미 구현, 실제로는 FAISS/Qdrant/pgvector 등으로 교체)
- `grade_evidence()` : 근거가 충분한지 LLM이 판정(yes/no + 이유)
- `rewrite_query()` : 실패 시 더 좋은 검색 쿼리로 재작성
- `agentic_rag()` : plan→search→grade→rewrite 루프

```python
import os
from typing import List, Dict, Any, Tuple

# -----------------------------
# 1) Retrieval Tool (예시)
# -----------------------------
def retrieve(query: str, top_k: int = 4, metadata: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """
    실제 환경에서는 vector DB 검색 결과를 반환.
    각 item은 {"text": "...", "source": "...", "score": 0.12} 형태를 권장.
    """
    # TODO: FAISS/Qdrant/pgvector/LlamaIndex QueryEngine 등으로 교체
    dummy_corpus = [
        {"text": "Agentic RAG는 질문을 재작성(rewrite)하고 재검색(retry)하는 루프를 포함한다.", "source": "internal-doc-1", "score": 0.18},
        {"text": "Tool calling 기반으로 retrieval을 함수로 제공하면 LLM이 검색 파라미터를 동적으로 선택할 수 있다.", "source": "internal-doc-2", "score": 0.22},
        {"text": "워크플로우/컨텍스트 state를 유지하면 재시도 비용을 줄이고 일관성을 높인다.", "source": "internal-doc-3", "score": 0.25},
    ]
    return dummy_corpus[:top_k]


# -----------------------------
# 2) LLM 호출 어댑터 (의사코드)
# -----------------------------
def call_llm_json(system: str, user: str) -> Dict[str, Any]:
    """
    OpenAI/Anthropic/Gemini 등 어떤 LLM이든 교체 가능한 어댑터.
    여기서는 실행 예시를 위해 규칙 기반 더미 응답을 반환.
    """
    # TODO: 실제 LLM SDK로 교체 (structured output 추천)
    if "grade" in system.lower():
        # evidence가 rewrite를 요구할 정도로 부족한지 평가한다고 가정
        return {"ok": "yes", "reason": "근거가 질문과 직접 관련됨"}
    if "rewrite" in system.lower():
        return {"query": user.replace("구현 방법", "step-by-step implementation with retry loop and grading")}
    return {"answer": "더미 답변", "citations": []}


def grade_evidence(question: str, evidence: List[Dict[str, Any]]) -> Tuple[bool, str]:
    system = "You are a strict grader. Return JSON: {ok: 'yes'|'no', reason: string}. (grade)"
    joined = "\n\n".join([f"- {e['text']} (src={e['source']})" for e in evidence])
    user = f"Question:\n{question}\n\nEvidence:\n{joined}\n\nIs the evidence sufficient?"
    out = call_llm_json(system, user)
    return (out["ok"] == "yes"), out["reason"]


def rewrite_query(question: str, failure_reason: str) -> str:
    system = "Rewrite the search query to improve retrieval. Return JSON: {query: string}. (rewrite)"
    user = f"Original question: {question}\nFailure reason: {failure_reason}\nRewrite query:"
    out = call_llm_json(system, user)
    return out["query"]


def synthesize_answer(question: str, evidence: List[Dict[str, Any]]) -> str:
    # 실전에서는 여기서 answer 생성 + 근거 인용 포맷을 강제하는 것이 중요
    bullets = "\n".join([f"- ({e['source']}) {e['text']}" for e in evidence])
    return f"질문: {question}\n\n근거 기반 요약:\n{bullets}\n\n최종 답변: (여기에 LLM 생성 답변을 붙이세요)"


# -----------------------------
# 3) Agentic RAG 루프
# -----------------------------
def agentic_rag(question: str, max_attempts: int = 3) -> Dict[str, Any]:
    state = {
        "attempts": 0,
        "last_query": question,
        "evidence": [],   # 누적 근거
    }

    while state["attempts"] < max_attempts:
        state["attempts"] += 1

        # (A) retrieve
        retrieved = retrieve(state["last_query"], top_k=4)
        state["evidence"] = retrieved  # 간단히 overwrite (실전에서는 누적/중복제거 추천)

        # (B) grade
        ok, reason = grade_evidence(question, state["evidence"])
        if ok:
            return {
                "answer": synthesize_answer(question, state["evidence"]),
                "attempts": state["attempts"],
                "final_query": state["last_query"],
                "grade_reason": reason,
            }

        # (C) rewrite & retry
        state["last_query"] = rewrite_query(question, reason)

    return {
        "answer": "충분한 근거를 찾지 못했습니다. 데이터 소스/인덱스/쿼리 전략을 점검하세요.",
        "attempts": state["attempts"],
        "final_query": state["last_query"],
    }


if __name__ == "__main__":
    result = agentic_rag("2025년 LLM RAG 에이전트 구현 방법 튜토리얼", max_attempts=3)
    print(result["answer"])
    print("attempts =", result["attempts"], "final_query =", result["final_query"])
```

이 골격을 실제 서비스로 올릴 때는 `retrieve()`를 LlamaIndex의 QueryEngine/Tool로 감싸거나(“retrieval tool” 패턴), LangGraph 같은 그래프 런타임으로 노드화해서 관측/분기/병렬을 강화하는 방식으로 발전시킵니다. ([medium.com](https://medium.com/%40samad19472002/agentic-rag-application-using-llamaindex-tool-calling-30bfef6cb4fb?utm_source=openai))

---

## ⚡ 실전 팁
1) **Grader는 “정확도”보다 “충분성(sufficiency)”을 본다**  
문서가 관련 있어 보이는지(relevance)만으로는 부족합니다. “질문에 답하기 위한 필수 포인트가 다 채워졌는가”를 체크리스트로 채점하게 만들면 hallucination이 줄어듭니다(Agentic RAG의 핵심 가치). ([medium.com](https://medium.com/%40mohitagr18/the-ai-that-thinks-before-it-searches-a-deep-dive-into-agentic-rag-82e5db9a0826))

2) **Tool description/type annotation이 에이전트 품질을 좌우**  
LlamaIndex 문서에서도 tool을 만들 때 name/docstring/type이 중요하다고 강조합니다. LLM은 도구를 “코드”로 읽는 게 아니라 “설명”으로 이해합니다. ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/examples/agent/agent_workflow_basic/?utm_source=openai))  
- docstring에 “언제 쓰는 도구인지”를 구체적으로
- 입력 타입은 가능한 좁게(예: `page_numbers: List[str]` 같은 형태가 추론을 돕습니다) ([medium.com](https://medium.com/%40samad19472002/agentic-rag-application-using-llamaindex-tool-calling-30bfef6cb4fb?utm_source=openai))

3) **State를 “대화 메모리”로만 쓰지 말고 “조사 로그”로 써라**  
에이전트 state에 아래를 남기면 운영 난이도가 급감합니다.
- 어떤 쿼리를 시도했는지
- 어떤 retriever 파라미터(top_k, filter)를 썼는지
- grader가 왜 실패 처리했는지
이건 디버깅뿐 아니라, 이후 자동 튜닝(예: 실패 패턴별 rewrite 템플릿)에도 직접 연결됩니다. ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/examples/agent/agent_workflow_basic/))

4) **Chunking은 “정확도”가 아니라 “의사결정 비용” 문제**
chunk가 너무 크면 grader/rewriter 루프의 토큰 비용이 폭증하고, 너무 작으면 근거가 산산이 깨져 “충분성” 판정이 어려워집니다. Agentic RAG에서는 특히 grader가 읽을 evidence 크기가 비용에 직결되므로, chunk 전략을 별도 튜닝 대상으로 보세요(문서/코드/FAQ 등 도메인별로 다르게).

---

## 🚀 마무리
2025년형 RAG 에이전트의 본질은 “vector search 붙인 챗봇”이 아니라 **반복적으로 검색하고, 근거를 채점하고, 쿼리를 개선하는 조사 시스템**입니다. 정리하면:

- retrieval을 **Tool** 로 만들고(동적 파라미터/필터 가능) ([medium.com](https://medium.com/%40samad19472002/agentic-rag-application-using-llamaindex-tool-calling-30bfef6cb4fb?utm_source=openai))  
- **grade → rewrite → retry** 루프로 신뢰도를 올리며 ([medium.com](https://medium.com/%40mohitagr18/the-ai-that-thinks-before-it-searches-a-deep-dive-into-agentic-rag-82e5db9a0826))  
- workflow/state를 통해 관측 가능하고 재현 가능한 시스템으로 만든다 ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/understanding/))  

다음 학습 추천은 두 갈래입니다.
- **워크플로우/멀티 에이전트 확장**: LlamaIndex의 AgentWorkflow/Workflows 계층을 따라가며 상태/이벤트/streaming을 정교화 ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/examples/agent/agent_workflow_basic/))  
- **그래프 기반 오케스트레이션**: LangGraph 스타일로 노드(검색/채점/재작성/응답)를 분리해 분기/루프/관측성을 강화 ([medium.com](https://medium.com/%40mohitagr18/the-ai-that-thinks-before-it-searches-a-deep-dive-into-agentic-rag-82e5db9a0826))  

원하시면, 위 코드 골격을 기준으로 **(1) 실제 vector DB(Qdrant/pgvector) 연결**, **(2) citation(근거 인용) 강제 프롬프트**, **(3) evaluator-driven 튜닝(offline eval)** 까지 포함한 “프로덕션 체크리스트 버전”으로 확장해 드리겠습니다.