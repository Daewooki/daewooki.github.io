---
title: "상태 머신으로 멀티 에이전트를 “운영”하라: 2026년 LangGraph·AutoGen(=MS Agent Framework)·CrewAI 심층 비교와 구현 패턴"
date: 2026-03-26 02:58:11 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-03]
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
2026년 3월 기준, AI Agent 개발의 병목은 “프롬프트 잘 쓰기”가 아니라 **오케스트레이션(orchestration)** 입니다. POC에서는 한두 개 tool call과 단일 agent로도 그럴듯하지만, 실제 서비스로 가면 곧바로 다음 요구가 붙습니다: (1) 여러 역할의 협업(Planner/Researcher/Coder/Reviewer), (2) 중간 산출물의 **상태(state)** 보존, (3) 실패/재시도/승인(HITL), (4) 관측가능성(tracing)과 재현성.  
이 지점에서 프레임워크 선택이 곧 아키텍처 선택이 됩니다. 최근 비교 글들이 공통으로 강조하는 축은 “대화(conversation) 기반 vs 역할(role) 기반 vs 그래프(state machine) 기반”이고, 특히 Microsoft가 AutoGen과 Semantic Kernel을 묶어 **Microsoft Agent Framework**로 재정렬했다는 흐름이 눈에 띕니다. ([letsdatascience.com](https://letsdatascience.com/blog/ai-agent-frameworks-compared))

---

## 🔧 핵심 개념
### 1) 오케스트레이션 철학: Conversation vs Role vs State Machine
- **AutoGen 계열(대화 기반)**: “상태=대화 로그”에 가깝습니다. Agent들 간 메시지 라우팅이 자연스럽고 데모가 빠르지만, 복잡한 분기/루프/체크포인트를 “대화 프롬프트”로 떠안기면 운영 난도가 급격히 상승합니다. 2026년에는 AutoGen 자체보다 **Microsoft Agent Framework**로 중심이 이동하는 흐름이 언급됩니다. ([letsdatascience.com](https://letsdatascience.com/blog/ai-agent-frameworks-compared))
- **CrewAI(역할 기반)**: 역할(role)과 Task/Process(순차, 계층, 하이브리드)를 먼저 모델링하고, 프레임워크가 협업을 “팀(crew)” 단위로 굴립니다. 문서에서도 Agents/Tasks/Processes/Flows를 핵심 구성으로 두고, Flows가 start/listen/router로 상태를 관리·지속·재개(resume)하는 방향을 강조합니다. ([docs.crewai.com](https://docs.crewai.com/))
- **LangGraph(상태 머신/그래프 기반)**: 핵심은 “LLM을 노드(node) 중 하나로 두고, 전체를 **StateGraph**로 모델링”하는 방식입니다. 노드 간 엣지(edge)에 조건 분기와 루프를 두고, checkpointer로 상태를 저장해 **중간 단계부터 재개**할 수 있는 구조가 강점으로 계속 언급됩니다. (복잡도는 올라가지만, 운영 관점에서 가장 예측 가능) ([letsdatascience.com](https://letsdatascience.com/blog/ai-agent-frameworks-compared))

### 2) 멀티 에이전트 구현의 본질: “공유 상태”와 “합의 프로토콜”
멀티 에이전트가 어려운 이유는 LLM이 여러 개라서가 아니라,
- **공유 상태의 스키마**(무엇을 state로 저장할지),
- **상태 업데이트 규칙**(누가 어떤 키를 언제 덮어쓰는지),
- **합의/검증 단계**(Reviewer가 reject하면 어디로 되돌아갈지),
를 코드로 고정해야 하기 때문입니다.  
따라서 2026년 실무에서는 “agent 수”보다 “그래프의 재시도/승인/관측”이 선택 기준이 되고, 비교 자료들도 복잡한 승인 게이트와 지속성(persistence)이 필요하면 LangGraph류가 유리하다는 결론을 반복합니다. ([letsdatascience.com](https://letsdatascience.com/blog/ai-agent-frameworks-compared))

---

## 💻 실전 코드
아래 예시는 “요구사항 분석 → 리서치 → 초안 작성 → 리뷰(통과/반려) → (반려 시) 리라이트”를 **멀티 에이전트 + 공유 상태**로 구현하는 최소 패턴입니다.  
실무 감각을 위해 “상태 스키마(typed) + 라우터 + 루프”를 핵심으로 보여줍니다. (LangGraph 스타일)

```python
# Python 3.11+
# pip install langgraph langchain-core langchain-openai
# 환경변수: OPENAI_API_KEY (또는 사용 모델에 맞게 교체)

from __future__ import annotations
from typing import TypedDict, Literal, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.2)

# 1) 공유 상태 스키마: 멀티 에이전트가 합의해야 하는 "단일 진실"
class BlogState(TypedDict):
    topic: str
    requirements: str
    research_notes: List[str]
    draft: str
    review: str
    decision: Literal["approve", "revise"]

def analyst(state: BlogState) -> BlogState:
    """요구사항을 '검증 가능한 체크리스트'로 변환 (운영 안정성에 중요)"""
    prompt = [
        SystemMessage(content="You are a senior engineer. Turn requirements into a strict checklist."),
        HumanMessage(content=f"Topic: {state['topic']}\nRequirements:\n{state['requirements']}")
    ]
    checklist = llm.invoke(prompt).content
    notes = state["research_notes"] + [f"[Checklist]\n{checklist}"]
    return {**state, "research_notes": notes}

def researcher(state: BlogState) -> BlogState:
    """리서치 결과를 요약/정규화해서 state에 적재 (후속 노드가 재사용 가능)"""
    prompt = [
        SystemMessage(content="Summarize key technical points, tradeoffs, and pitfalls as bullet notes."),
        HumanMessage(content="Use the checklist and produce research notes.\n\n" + "\n\n".join(state["research_notes"]))
    ]
    more = llm.invoke(prompt).content
    notes = state["research_notes"] + [f"[Research]\n{more}"]
    return {**state, "research_notes": notes}

def writer(state: BlogState) -> BlogState:
    """초안 생성: state의 notes를 단일 소스로 사용해 일관성 유지"""
    prompt = [
        SystemMessage(content="Write a deep technical Korean blog post with code sections. Keep English terms."),
        HumanMessage(content=f"""
Topic: {state['topic']}

Notes:
{chr(10).join(state["research_notes"])}

Write draft now.
""")
    ]
    draft = llm.invoke(prompt).content
    return {**state, "draft": draft}

def reviewer(state: BlogState) -> BlogState:
    """리뷰어는 approve/revise를 명시적으로 결정 -> 라우팅에 사용"""
    prompt = [
        SystemMessage(content=(
            "You are a strict reviewer. Decide approve or revise.\n"
            "Return format:\nDECISION: approve|revise\nREVIEW: ...\n"
        )),
        HumanMessage(content=state["draft"])
    ]
    out = llm.invoke(prompt).content
    decision = "revise" if "DECISION: revise" in out else "approve"
    return {**state, "review": out, "decision": decision}  # decision은 그래프 분기 조건

def rewriter(state: BlogState) -> BlogState:
    """반려 시: 리뷰를 입력으로 받아 특정 지적을 반영한 리라이트"""
    prompt = [
        SystemMessage(content="Revise the draft addressing reviewer feedback. Keep structure and add missing depth."),
        HumanMessage(content=f"REVIEW FEEDBACK:\n{state['review']}\n\nDRAFT:\n{state['draft']}")
    ]
    draft = llm.invoke(prompt).content
    return {**state, "draft": draft}

def route_after_review(state: BlogState) -> str:
    """조건부 엣지: 승인/반려에 따라 END 또는 rewriter로 루프"""
    return END if state["decision"] == "approve" else "rewriter"

# 2) 그래프 구성: 멀티 에이전트 파이프라인 + 루프(운영의 핵심)
g = StateGraph(BlogState)
g.add_node("analyst", analyst)
g.add_node("researcher", researcher)
g.add_node("writer", writer)
g.add_node("reviewer", reviewer)
g.add_node("rewriter", rewriter)

g.set_entry_point("analyst")
g.add_edge("analyst", "researcher")
g.add_edge("researcher", "writer")
g.add_edge("writer", "reviewer")
g.add_conditional_edges("reviewer", route_after_review, {"rewriter": "rewriter", END: END})
g.add_edge("rewriter", "reviewer")  # 루프

app = g.compile()

if __name__ == "__main__":
    init: BlogState = {
        "topic": "2026년 3월 AI Agent 개발 방법: LangGraph, AutoGen(Agent Framework), CrewAI",
        "requirements": "- 프레임워크 비교\n- 멀티 에이전트 구현\n- 운영 관점 팁\n- 코드 포함",
        "research_notes": [],
        "draft": "",
        "review": "",
        "decision": "revise",
    }
    final_state = app.invoke(init)
    print(final_state["draft"])
```

핵심은 “agent들이 서로 메시지로만 싸우게 두지 말고”, **state 스키마와 라우팅을 코드로 고정**해 재현성을 확보하는 것입니다. 이 패턴은 CrewAI의 Process/Flow나 MS Agent Framework의 그래프 지향 흐름으로도 그대로 번역됩니다. ([docs.crewai.com](https://docs.crewai.com/))

---

## ⚡ 실전 팁
1) **멀티 에이전트의 80%는 ‘상태 설계’**  
state에 “최종 산출물”만 넣지 말고, *중간 근거(리서치 노트, 체크리스트, 실패 사유)*를 넣어야 디버깅/재실행 비용이 줄어듭니다. LangGraph가 persistence/checkpointing을 강점으로 내세우는 이유가 여기 있습니다. ([letsdatascience.com](https://letsdatascience.com/blog/ai-agent-frameworks-compared))

2) “역할”은 프롬프트가 아니라 **인터페이스 계약**  
CrewAI처럼 Role을 먼저 두는 접근은 빠르지만, 실무에서는 “이 Role이 state의 어떤 키를 읽고/쓰는가”를 문서화하지 않으면 결국 충돌합니다(덮어쓰기, 환각 근거 전파). CrewAI 문서가 Tasks/Processes/Flows로 구조화를 강조하는 것도 같은 맥락입니다. ([docs.crewai.com](https://docs.crewai.com/))

3) **리뷰/승인 노드는 무조건 분리**  
Writer가 자기 글을 자가검수하게 하면 통과율이 이상하게 높아집니다. Reviewer를 별도 노드로 만들고, decision을 구조화(approve/revise)해서 라우팅 조건으로 쓰세요. “HITL(승인 게이트)”가 필요해지는 순간부터는 그래프 기반이 압도적으로 편해집니다. ([letsdatascience.com](https://letsdatascience.com/blog/ai-agent-frameworks-compared))

4) AutoGen을 새로 시작한다면 “AutoGen 자체”보다 **MS Agent Framework 로드맵**을 확인  
최근 비교 글/정리에서는 AutoGen이 MS Agent Framework로 흡수·정렬되는 흐름을 반복해서 언급합니다. Azure/.NET 생태계라면 이 방향을 전제로 설계하는 게 마이그레이션 리스크를 줄입니다. ([letsdatascience.com](https://letsdatascience.com/blog/ai-agent-frameworks-compared))

---

## 🚀 마무리
- **LangGraph**: 복잡한 분기/루프/승인/재개가 있는 “운영형” 멀티 에이전트에 최적(상태 머신 사고가 필요). ([letsdatascience.com](https://letsdatascience.com/blog/ai-agent-frameworks-compared))  
- **CrewAI**: 역할 기반 협업을 빠르게 올리고, Task/Process/Flow로 팀 개발 경험을 얻기 좋음(중대형 요구에서 한계를 느끼면 그래프형으로 이전 고려). ([docs.crewai.com](https://docs.crewai.com/))  
- **AutoGen → Microsoft Agent Framework**: 2026년에는 “대화 기반 오케스트레이션”만으로는 부족해지고, 엔터프라이즈는 그래프/프로토콜/체크포인트 중심으로 이동 중. ([letsdatascience.com](https://letsdatascience.com/blog/ai-agent-frameworks-compared))  

다음 학습은 “프레임워크 사용법”보다 **(1) 상태 스키마 설계, (2) 라우팅/재시도/승인 패턴, (3) 관측가능성(트레이싱)과 재현성**을 중심으로 파고드는 것을 권합니다. 이 3가지를 장악하면 LangGraph/CrewAI/Agent Framework 중 무엇을 쓰든 멀티 에이전트의 품질이 한 단계 올라갑니다.