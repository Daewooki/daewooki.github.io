---
title: "2026년 6월, 멀티 에이전트 “진짜로” 굴리려면: LangGraph vs AutoGen vs CrewAI 심층 비교 & 구현 가이드"
date: 2026-06-12 04:48:45 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-06]
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
LLM 기반 기능이 “단일 Agent + Tool 몇 개” 수준을 넘어서면, 곧바로 **오케스트레이션 문제**가 터집니다.

- 작업이 길어져서 **중간 실패/재시도/재개(resume)** 가 필요하다
- 여러 역할(Researcher/Planner/Coder/Reviewer 등)을 **병렬/순차/조건 분기**로 묶어야 한다
- “모델이 알아서 하겠지”로 두면 **비용 폭증 + 무한 루프 + 품질 편차**가 생긴다
- 운영 환경에서 **관찰성(observability), 상태(state), 승인(human-in-the-loop)** 이 요구된다

2026년 6월 기준, 실무에서 가장 자주 비교되는 오픈소스 축은 **LangGraph, Microsoft AutoGen(AgentChat 계열), CrewAI**입니다. (최근 AutoGen+Semantic Kernel을 단일 프레임워크로 통합하려는 흐름도 커졌습니다.) ([reddit.com](https://www.reddit.com/r/AutoGenAI/comments/1o0p73u/autogen_semantic_kernel_microsoft_agent_framework/?utm_source=openai))

### 언제 쓰면 좋나
- **LangGraph**: “프로덕션 워크플로우 엔진”에 가까운 제어가 필요할 때(체크포인트/재개/승인/실패 처리/분기) ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/persistence?utm_source=openai))  
- **AutoGen**: 여러 Agent의 **대화 패턴(그룹챗, 선택자, 종료조건 등)** 을 중심으로 설계하고 싶을 때(대화 기반 협업, 실험 속도) ([microsoft.github.io](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.base.html?utm_source=openai))  
- **CrewAI**: Role/Task 중심으로 팀을 빠르게 구성하고, **sequential/hierarchical 프로세스**로 빨리 MVP를 뽑고 싶을 때 ([docs.crewai.com](https://docs.crewai.com/?utm_source=openai))  

### 언제 쓰면 안 되나
- 절차가 단순하고 상태가 짧은데도 “멀티 에이전트”로 과설계하면, 오히려 **토큰 비용 + 디버깅 난이도**만 증가합니다. 최근에는 **절차형 작업은 In-Context Prompting만으로도 충분한 경우가 늘었다**는 문제제기도 있습니다. ([arxiv.org](https://arxiv.org/abs/2604.27891?utm_source=openai))  
- 사람이 승인해야 하는 지점이 많고 규제가 강한 도메인인데 “대화형 Agent가 알아서”로 밀면, 책임소재/감사로그/재현성이 무너집니다(이 경우 LangGraph류가 유리).

---

## 🔧 핵심 개념
세 프레임워크는 모두 “도구 호출 + 상태 + 라우팅”을 다루지만, **기본 추상화가 다릅니다.**

### 1) LangGraph: Graph 실행 모델(StateGraph + Checkpoint)
LangGraph의 핵심은 **노드(node) 함수들이 state를 읽고/갱신**하며, **edge(조건 포함)** 로 다음 노드를 결정하는 **graph 실행 엔진**입니다. 여기에 “프로덕션 핵심”이 붙습니다:

- **Checkpointing/Persistence**: 각 실행 스텝의 state 스냅샷을 저장해서  
  - 장애 후 **crash recovery**
  - “승인 대기” 같은 **human-in-the-loop interrupt**
  - 장시간 작업의 **재개(resume)**
  를 가능하게 합니다. ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/persistence?utm_source=openai))  
- “pending writes”처럼, 병렬 노드가 섞일 때도 **부분 성공을 기록**하는 쪽으로 설계되어 운영 안정성을 올립니다. ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/persistence?utm_source=openai))  

즉 LangGraph는 “Agent 프레임워크”라기보다 **상태 기계(state machine)/워크플로우 엔진을 LLM에 맞춘 형태**에 가깝습니다. 대신 러닝커브가 있습니다(노드/엣지/리듀서/조건 라우팅 등). ([thinking.inc](https://thinking.inc/en/tool-comparisons/langgraph-vs-crewai-vs-autogen/?utm_source=openai))  

### 2) AutoGen: Multi-Agent Conversation + Runtime(상태 저장 훅)
AutoGen은 “그래프”보다는 **대화(conversation)** 가 1급 객체입니다.

- Agent들이 메시지를 주고받고, **termination condition**으로 종료를 판단합니다. ([microsoft.github.io](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.base.html?utm_source=openai))  
- 커스텀 Agent를 만들면 `save_state()` / `load_state()`를 오버라이드해 상태를 저장/복원할 수 있습니다. ([microsoft.github.io](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/tutorial/state.html?utm_source=openai))  

강점은 “협업 대화 패턴”을 코드로 빨리 실험하는 데 있고, 약점은 “승인 게이트/재개/분기/실패 처리”를 **대화 패턴만으로 깔끔하게 모델링하기가** 케이스에 따라 어렵다는 점입니다(결국 오케스트레이션 계층을 별도로 두게 됨).

### 3) CrewAI: Roles/Tasks/Process(Sequential/Hierarchical) 중심
CrewAI는 실무자가 좋아하는 이유가 명확합니다:

- **Agents(역할)**, **Tasks(업무)** 를 선언하고,
- **Process**를 sequential 또는 hierarchical(매니저가 분배/검수/재할당)로 실행합니다. ([learn.engineering.vips.edu](https://learn.engineering.vips.edu/agent-protocols/crewai-hierarchical-process?utm_source=openai))  
- 문서상으로는 guardrails, memory, knowledge, observability 등을 “내장” 방향으로 강조합니다. ([docs.crewai.com](https://docs.crewai.com/?utm_source=openai))  

즉 CrewAI는 “팀을 꾸려 일을 시키는” 상위 추상화가 강해서, 초기 생산성이 좋습니다. 대신 복잡한 분기/재시도/정교한 상태 제어는 프레임워크가 제공하는 추상화 범위를 넘는 순간 커스텀이 필요해지고, 그때 LangGraph 같은 그래프 모델이 그리워질 수 있습니다.

---

## 💻 실전 코드
현실적인 시나리오: **PRD(Product Requirement Doc) → 설계 초안 → 구현 계획 → 보안/성능 리뷰 → (필요 시) 사람 승인 → 최종 산출물 생성**  
요구사항:
- 중간 산출물은 저장되어야 함(재시도/재개)
- 리뷰에서 리스크가 크면 human approval 필요
- 비용 최적화를 위해 “상태를 크게 만들지 않기”

아래 예시는 **LangGraph(Python)** 로 “멀티 에이전트(역할별 함수/모델)”를 **상태 기반 그래프**로 오케스트레이션하는 패턴입니다. (실제 운영에 가까운 이유: 체크포인트/interrupt 전제를 깔고, 산출물을 구조화해 다음 노드 입력으로 씁니다.)

### 0) 설치/환경
```bash
pip install -U langgraph langchain-core langchain-openai pydantic
export OPENAI_API_KEY="..."
```

### 1) 그래프 상태/도구(현실: 산출물은 구조화 + 요약본만 state에 넣기)
```python
# python
from __future__ import annotations
from typing import TypedDict, Literal, Optional, List
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt

llm_fast = ChatOpenAI(model="gpt-4.1-mini", temperature=0.2)
llm_strict = ChatOpenAI(model="gpt-4.1", temperature=0.1)

class RiskReport(BaseModel):
    severity: Literal["low", "medium", "high"]
    findings: List[str] = Field(default_factory=list)
    recommended_changes: List[str] = Field(default_factory=list)

class AgentState(TypedDict, total=False):
    thread_id: str
    prd: str
    architecture: str
    implementation_plan: str
    risk: RiskReport
    approval_required: bool
    final_doc: str

def _chat(llm, sys: str, user: str) -> str:
    resp = llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)])
    return resp.content
```

### 2) 역할별 “에이전트 노드” (toy가 아닌 이유: 산출물 포맷/리뷰/승인 분기 포함)
```python
# python
def planner_node(state: AgentState) -> AgentState:
    prd = state["prd"]
    architecture = _chat(
        llm_fast,
        "You are a senior solution architect. Produce a concise architecture draft with components, data flow, and APIs.",
        f"PRD:\n{prd}\n\nOutput: Architecture draft (bullet points + simple diagram text)."
    )
    return {"architecture": architecture}

def implementer_node(state: AgentState) -> AgentState:
    plan = _chat(
        llm_fast,
        "You are a tech lead. Write an implementation plan with milestones, repo structure, and testing strategy.",
        f"Architecture:\n{state['architecture']}\n\nOutput: step-by-step implementation plan."
    )
    return {"implementation_plan": plan}

def reviewer_node(state: AgentState) -> AgentState:
    raw = _chat(
        llm_strict,
        "You are a security+performance reviewer. Classify risk as low/medium/high and list findings & changes.",
        f"PRD:\n{state['prd']}\n\nArchitecture:\n{state['architecture']}\n\nImplementation plan:\n{state['implementation_plan']}\n\nReturn JSON matching schema: severity, findings[], recommended_changes[]"
    )
    risk = RiskReport.model_validate_json(raw)
    approval_required = (risk.severity == "high")
    return {"risk": risk, "approval_required": approval_required}

def approval_gate_node(state: AgentState) -> AgentState:
    if not state.get("approval_required"):
        return {}

    # Human-in-the-loop: 여기서 실행을 멈추고 외부 입력(승인/반려 코멘트)을 기다림
    # LangGraph는 interrupt 시점에 state를 persistence로 저장해두고 재개 가능. ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/human-in-the-loop?utm_source=openai))
    decision = interrupt({
        "message": "High risk detected. Approve to proceed? (approve/reject) and optional comment.",
        "risk": state["risk"].model_dump()
    })
    if decision.get("action") != "approve":
        raise RuntimeError(f"Rejected by human: {decision}")
    return {}

def finalizer_node(state: AgentState) -> AgentState:
    final_doc = _chat(
        llm_fast,
        "You are a staff engineer. Produce a final technical doc: overview, architecture, implementation checklist, risk mitigations.",
        f"PRD:\n{state['prd']}\n\nArchitecture:\n{state['architecture']}\n\nPlan:\n{state['implementation_plan']}\n\nRisk:\n{state['risk'].model_dump_json(indent=2)}"
    )
    return {"final_doc": final_doc}
```

### 3) 그래프 구성 + 체크포인트(재개/복구/승인 대기 핵심)
```python
# python
def route_after_review(state: AgentState) -> str:
    return "approval_gate" if state.get("approval_required") else "finalize"

def build_app(sqlite_path: str = "agent_graph.sqlite"):
    sg = StateGraph(AgentState)
    sg.add_node("plan", planner_node)
    sg.add_node("implement", implementer_node)
    sg.add_node("review", reviewer_node)
    sg.add_node("approval_gate", approval_gate_node)
    sg.add_node("finalize", finalizer_node)

    sg.set_entry_point("plan")
    sg.add_edge("plan", "implement")
    sg.add_edge("implement", "review")
    sg.add_conditional_edges("review", route_after_review, {
        "approval_gate": "approval_gate",
        "finalize": "finalize",
    })
    sg.add_edge("approval_gate", "finalize")
    sg.add_edge("finalize", END)

    checkpointer = SqliteSaver.from_conn_string(sqlite_path)
    # LangGraph는 checkpointing/persistence로 멀티턴/복구/승인 워크플로우를 지원. ([langchain-ai.github.io](https://langchain-ai.github.io/langgraph/reference/checkpoints/?h=langgraph+checkpoint+sqlite+import+saver&utm_source=openai))
    return sg.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    app = build_app()
    thread_id = "prd-2026-06-12-001"

    # 1차 실행
    result = app.invoke(
        {"thread_id": thread_id, "prd": "B2B SaaS에 '사용량 기반 과금' 기능을 추가한다. ... (생략)"},
        config={"configurable": {"thread_id": thread_id}}
    )
    print(result.get("final_doc", "(no final_doc yet)"))
```

#### 예상 출력/동작
- risk가 `low/medium`이면: plan→implement→review→finalize로 바로 종료
- risk가 `high`이면: `interrupt()`에서 멈추며, **그 시점 state가 SQLite에 저장**됩니다(프로세스가 죽어도 복구 가능). ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/human-in-the-loop?utm_source=openai))  
- 재개는 동일 `thread_id`로 “승인 입력”을 넣어 이어갈 수 있게 설계합니다(운영에선 API/대시보드로 승인).

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 효과 나는 것 3가지)
1) **State를 작게 유지**
- LangGraph 체크포인트는 강력하지만, state가 커질수록 **저장 비용/직렬화 오버헤드**가 늘어납니다. “원문 전체” 대신 요약/구조화 결과만 state에 넣고, 원문은 외부 스토리지(S3/DB)에 두고 key만 들고 가세요. (LangGraph 문서에서도 state를 작게 유지하라고 강조) ([langgraphjs.guide](https://langgraphjs.guide/persistence/?utm_source=openai))  

2) **승인/중단 지점을 ‘명시적으로’ 설계**
- human-in-the-loop는 “가끔 사람에게 물어보기”가 아니라, **중단 가능한 실행 모델 + 재개 전략**이 있어야 운영됩니다. LangGraph는 interrupt 시 persistence로 상태 저장 후 대기하는 패턴을 공식 가이드로 제공합니다. ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/human-in-the-loop?utm_source=openai))  

3) **멀티 에이전트는 ‘역할 분리’보다 ‘검증 루프’가 핵심**
- 실무에서 품질을 올리는 건 “역할을 늘리는 것”이 아니라, Reviewer/Verifier를 두고 **실패를 빠르게 탐지→재시도/수정**하는 루프를 만드는 겁니다. (다만 루프는 비용을 폭발시킬 수 있으니 termination/예산 상한이 필수)

### 흔한 함정/안티패턴
- **CrewAI/AutoGen을 쓰는데 결국 분기/재시도/승인/재개 요구가 커져** “프레임워크 위에 또 오케스트레이터”를 얹는 상황  
  → 이러면 처음의 단순성이 사라집니다. 애초에 LangGraph 같은 graph/checkpoint 모델이 맞는지 재검토하세요.
- **Long-term memory를 무비판적으로 축적**
  → 2026년 연구에서도 장기 메모리는 cross-domain leakage, memory-induced sycophancy 같은 리스크가 지적됩니다. 개인화가 필요하면 “저장 정책/만료/스코프 분리”를 설계하세요. ([arxiv.org](https://arxiv.org/abs/2602.01146?utm_source=openai))  

### 비용/성능/안정성 트레이드오프(현실적인 결론)
- LangGraph: 안정성/재현성/운영성 ↑, 초기 구현 난이도/설계 비용 ↑  
- CrewAI: 초기 생산성 ↑, 복잡 제어 요구가 커질수록 추상화 한계에 부딪힐 수 있음  
- AutoGen: 대화 협업 실험 속도 ↑, “워크플로우 엔진급” 요구에는 보강 필요  
또한, “외부 오케스트레이션이 과연 항상 필요한가?”에 대한 반론도 있으니(모델 성능 향상으로 절차형 작업은 프롬프트로 대체 가능) 작업 성격을 냉정히 분류하세요. ([arxiv.org](https://arxiv.org/abs/2604.27891?utm_source=openai))  

---

## 🚀 마무리
**도입 판단 기준**을 한 줄로 정리하면 이렇습니다.

- “장시간/실패/재개/승인/감사로그”가 핵심이면 → **LangGraph** (checkpoint+interrupt가 게임 체인저) ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/persistence?utm_source=openai))  
- “역할 기반 팀을 빠르게 꾸려 결과를 뽑고, 프로세스는 sequential/hierarchical이면 충분” → **CrewAI** ([docs.crewai.com](https://docs.crewai.com/?utm_source=openai))  
- “멀티 에이전트 대화 패턴을 중심으로 다양한 상호작용을 실험/확장” → **AutoGen(AgentChat)**, 필요 시 상태 저장 훅을 적극 활용 ([microsoft.github.io](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.base.html?utm_source=openai))  

### 다음 학습 추천(실무 순서)
1) LangGraph의 **persistence/checkpoint + interrupt**를 먼저 잡고(운영성) ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/persistence?utm_source=openai))  
2) 그 위에 “역할 분리(Planner/Reviewer)”를 얹어 품질 루프를 만든 뒤  
3) 마지막으로 CrewAI/AutoGen의 고수준 추상화를 “필요한 만큼만” 도입하세요

원하면, 당신의 구체 프로젝트(도메인/승인 필요 여부/실패 비용/예산 상한/배포 형태)를 기준으로 **세 프레임워크 중 무엇을 선택하고 어떤 아키텍처로 가는 게 최적인지** 의사결정 트리 형태로 더 날카롭게 정리해줄게요.