---
title: "멀티 에이전트 “진짜로” 굴리기: LangGraph vs AutoGen vs CrewAI 심층 비교와 구현 패턴"
description: "2026년의 AI Agent 개발은 “LLM 한 번 호출”에서 끝나지 않습니다. 제품/업무에 투입되는 에이전트는 (1) 여러 단계의 workflow, (2) 실패/재시도, (3) 사람 승인(Human-in-the-loop), (4) 상태 저장과 재개, (5) 관측가능성(Tracing/D…"
date: 2026-02-03 02:48:37 +0900
categories: [AI, Agent]
tags: [ai, agent]
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
2026년의 AI Agent 개발은 “LLM 한 번 호출”에서 끝나지 않습니다. 제품/업무에 투입되는 에이전트는 (1) 여러 단계의 workflow, (2) 실패/재시도, (3) 사람 승인(Human-in-the-loop), (4) 상태 저장과 재개, (5) 관측가능성(Tracing/Debugging)을 요구합니다.  
여기서 프레임워크 선택이 곧 아키텍처 선택이 됩니다. LangGraph는 **명시적 control flow + state/checkpoint**로 “운영 가능한 에이전트”에 초점이 있고, AutoGen은 **대화 기반 multi-agent 협업**에 강하며, CrewAI는 **role/task 중심의 빠른 조립**에 최적화되어 있습니다.[^1]

---

## 🔧 핵심 개념
### 1) 오케스트레이션 모델의 차이: Graph vs Chat vs Process
- **LangGraph**: 노드(node)와 엣지(edge)로 workflow를 “상태 기계(state machine)”처럼 구성합니다. 중요한 건 *프롬프트보다 흐름이 먼저*라는 점입니다. 실패 시 fallback edge, 승인 노드, 분기/루프가 구조적으로 들어갑니다.[^1]  
- **AutoGen**: 에이전트들이 메시지를 주고받는 **conversation loop**가 중심입니다. 역할/종료조건/팀(예: GroupChat)을 정의하고, 협상/토론형 문제에서 자연스럽게 성능이 나옵니다.[^2]  
- **CrewAI**: `Agents-Tasks-Crew`로 구성하고, `Process.sequential / Process.hierarchical` 같은 “프로젝트 관리” 메타포로 실행합니다. 빠르게 만들기 쉽지만, 내부 오케스트레이션을 아주 정교하게 제어하는 건 상대적으로 어렵습니다.[^3]  

### 2) 멀티 에이전트 구현에서 진짜 중요한 것: “상태(state)”
멀티 에이전트는 메시지가 늘어나고, 툴 호출이 섞이고, 중간 산출물이 누적됩니다. 이때 상태를 어떻게 다루느냐가 운영 난이도를 결정합니다.
- **LangGraph**: 상태를 타입/스키마로 설계하고, 단계별 checkpoint를 남겨 **디버깅(일명 time-travel)과 재실행**을 강하게 지원하는 방향이 강조됩니다.[^4]  
- **AutoGen**: 기본적으로 상태가 “대화 히스토리”에 가깝지만, v0.4에서 `save_state()/load_state()`로 상태 저장/복원이 공식화되었습니다(팀 단위도 가능).[^5]  
- **CrewAI**: workflow 관점에선 process 기반으로 흘러가며, task 결과가 다음 task 컨텍스트가 됩니다. Hierarchical에선 manager가 task를 위임/검증합니다.[^3]  

### 3) 멀티 에이전트 패턴: Supervisor가 “기본값”이 되는 이유
2026년 실무에선 “모든 에이전트가 서로 방송(broadcast)하며 토론”하는 구조가 토큰 비용/디버깅 난이도 때문에 쉽게 무너집니다. 그래서 흔히 쓰는 패턴이:
- **Supervisor(중앙 라우터) → Specialist Agents(전문화)**  
LangGraph 진영에서도 supervisor 패턴을 “툴 기반 handoff로 직접 구현”하는 쪽을 권장하는 흐름이 보입니다(전용 라이브러리보다 수동 패턴 권장).[^6]  

---

## 💻 실전 코드
아래 예시는 “멀티 에이전트 구현의 본질”을 보여주기 위해 **LangGraph 스타일 Supervisor 패턴**을 최대한 프레임워크-중립적으로(그러나 LangGraph 개념에 맞게) 구현한 미니 튜토리얼입니다.  
핵심은 **(1) 공유 상태, (2) 라우팅 결정, (3) specialist 실행, (4) 루프/종료**입니다.

```python
# Python 3.10+
# 개념 데모(실행 가능). LLM 대신 더미 라우터/에이전트를 넣어 구조를 이해하는 코드입니다.
# 실제 LangGraph에선 이 구조를 StateGraph + nodes/edges로 옮기면 됩니다.

from dataclasses import dataclass, field
from typing import Literal, List, Dict, Any

Role = Literal["supervisor", "researcher", "coder", "reviewer"]

@dataclass
class Message:
    role: Role
    content: str

@dataclass
class AgentState:
    goal: str
    messages: List[Message] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    next: Literal["researcher", "coder", "reviewer", "done"] = "researcher"

# --- Specialist Agents (현업에선 각자 toolset/LLM/system prompt가 다름) ---

def researcher_agent(state: AgentState) -> AgentState:
    # 예: 웹 검색/문서 수집 결과를 요약해서 artifacts에 넣는 역할
    state.messages.append(Message("researcher", "요구사항을 분석했고, 필요한 리서치 포인트를 정리했습니다."))
    state.artifacts["requirements"] = {
        "need_structured_flow": True,
        "need_state_persistence": True,
        "multi_agent_pattern": "supervisor",
    }
    return state

def coder_agent(state: AgentState) -> AgentState:
    # 예: 설계안을 코드 스케치로 변환
    state.messages.append(Message("coder", "Supervisor 기반으로 모듈 구조와 인터페이스를 설계했습니다."))
    state.artifacts["code_plan"] = {
        "interfaces": ["Router.decide()", "Agent.run()", "State.checkpoint()"],
        "notes": "에이전트별 context를 분리하고, 결과만 state.artifacts로 합칩니다."
    }
    return state

def reviewer_agent(state: AgentState) -> AgentState:
    # 예: 결과 검증/종료 판단
    req = state.artifacts.get("requirements", {})
    plan = state.artifacts.get("code_plan", {})
    ok = bool(req) and bool(plan)
    state.messages.append(Message("reviewer", f"검토 결과: {'통과' if ok else '보완 필요'}"))
    state.artifacts["approved"] = ok
    return state

# --- Supervisor Router (현업에선 LLM tool-calling로 라우팅) ---

def supervisor_router(state: AgentState) -> AgentState:
    """
    라우팅의 핵심: '지금 무엇이 부족한가?'를 기준으로 다음 에이전트를 선택.
    LangGraph에선 이 함수가 '조건 분기(edge)'의 기준이 됩니다.
    """
    if "requirements" not in state.artifacts:
        state.next = "researcher"
    elif "code_plan" not in state.artifacts:
        state.next = "coder"
    elif "approved" not in state.artifacts:
        state.next = "reviewer"
    else:
        state.next = "done"

    state.messages.append(Message("supervisor", f"다음 실행: {state.next}"))
    return state

# --- Simple Orchestrator Loop (LangGraph라면 graph traversal이 이 역할) ---

def run_supervised_multi_agent(goal: str, max_steps: int = 10) -> AgentState:
    state = AgentState(goal=goal)
    state.messages.append(Message("supervisor", f"목표 수신: {goal}"))

    for _ in range(max_steps):
        state = supervisor_router(state)

        if state.next == "done":
            break
        elif state.next == "researcher":
            state = researcher_agent(state)
        elif state.next == "coder":
            state = coder_agent(state)
        elif state.next == "reviewer":
            state = reviewer_agent(state)

    return state

if __name__ == "__main__":
    final_state = run_supervised_multi_agent("LangGraph/AutoGen/CrewAI 중 멀티 에이전트 구현 전략 수립")
    for m in final_state.messages:
        print(f"[{m.role}] {m.content}")
    print("\nArtifacts:", final_state.artifacts)
```

이 코드가 시사하는 바는 단순합니다: 멀티 에이전트의 본질은 “에이전트 수”가 아니라 **공유 상태를 중심으로 한 라우팅/검증 루프**입니다. LangGraph는 이것을 그래프로 “표현”하고, AutoGen은 대화 루프로 “표현”하며, CrewAI는 process/task로 “표현”합니다.[^1]  

---

## ⚡ 실전 팁
1) **Broadcast 토론형(모두가 모두에게 말함)은 비용 폭탄**  
AutoGen의 GroupChat류는 메시지 전파 구조에 따라 토큰이 기하급수적으로 늘 수 있습니다. 실무에선 기본값을 Supervisor 라우팅으로 두고, “정말 토론이 필요한 구간”만 제한적으로 회의 모드로 여는 게 안전합니다.[^4]  

2) **상태는 “대화로그”가 아니라 “업무 데이터 모델”로 설계**  
- LangGraph를 선택한다면: 노드별로 어떤 state만 필요하게 할지(컨텍스트 최소화) 설계가 곧 비용 최적화입니다.[^4]  
- AutoGen을 선택한다면: v0.4의 `save_state/load_state`로 “재개 가능성”을 확보하되, 장기 실행은 대화만 쌓지 말고 요약/압축 전략을 별도로 두세요.[^5]  

3) **CrewAI Hierarchical는 ‘조직도’가 아니라 ‘검증 파이프라인’으로 써라**  
CrewAI의 hierarchical process는 manager가 위임/검증을 수행합니다. 여기서 포인트는 “매니저 프롬프트”가 품질의 대부분을 결정한다는 점입니다. manager에게 *검증 기준(acceptance criteria)*, *실패 시 재작업 규칙*을 명문화하세요.[^3]  

4) **프레임워크 선택 기준(현실적인 결론)**  
- 감사/재현/디버깅/승인 게이트가 중요 → **LangGraph** 우선 (control flow를 코드로 고정)[^1]  
- 협상/토론/코드리뷰 같은 대화형 협업이 핵심 → **AutoGen** (multi-agent chat이 본체)[^2]  
- 빠른 PoC, role/task가 명확한 팀 작업 → **CrewAI** (process로 바로 굴림)[^7]  

---

## 🚀 마무리
2026년 2월 기준, LangGraph/AutoGen/CrewAI는 모두 멀티 에이전트를 지원하지만, “멀티 에이전트를 운영한다”는 관점에서 갈리는 지점은 하나입니다: **상태와 흐름을 어디에 고정하느냐**입니다.  
- LangGraph: 흐름/상태를 구조로 고정해 운영 친화적으로  
- AutoGen: 대화 협업을 중심으로 탐색/협상에 강하게  
- CrewAI: 프로세스/역할 중심으로 빠르게 팀을 구성하게

다음 학습으로는 (1) Supervisor + handoff 패턴을 각 프레임워크 방식으로 1번씩 구현해보고, (2) state 최소화(컨텍스트 엔지니어링)와 (3) 저장/재개(Checkpoint/State restore) 시나리오를 꼭 만들어 보길 추천합니다. 특히 AutoGen은 v0.4에서 상태 저장/복원이 공식화되어 장기 실행 설계의 선택지가 넓어졌습니다.[^5]

[^1]: <https://thread-transfer.com/blog/2025-03-15-ai-agent-frameworks-compared/>
[^2]: <https://microsoft.github.io/autogen/0.2/docs/Use-Cases/agent_chat/>
[^3]: <https://docs.crewai.com/en/concepts/processes>
[^4]: <https://www.mmntm.net/articles/orchestration-showdown>
[^5]: <https://microsoft.github.io/autogen/0.4.2/user-guide/agentchat-user-guide/migration-guide.html>
[^6]: <https://reference.langchain.com/python/langgraph/supervisor/>
[^7]: <https://docs.crewai.com/en/concepts/crews>
