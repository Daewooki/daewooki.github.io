---
title: "그래프(State)로 통제하고, 대화(Chat)로 협업하라: LangGraph·AutoGen·CrewAI 멀티 Agent 프레임워크 심층 비교"
description: "2026년의 AI Agent 개발은 “LLM 호출을 몇 번 엮는 자동화”가 아니라, 긴 실행 시간·실패 복구·관찰 가능성(observability)·권한/검증(guardrails)까지 포함한 소프트웨어 시스템 문제로 바뀌었습니다."
date: 2026-02-20 02:45:24 +0900
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
2026년의 AI Agent 개발은 “LLM 호출을 몇 번 엮는 자동화”가 아니라, **긴 실행 시간·실패 복구·관찰 가능성(observability)·권한/검증(guardrails)**까지 포함한 **소프트웨어 시스템** 문제로 바뀌었습니다. 단일 Agent로 시작해도, 조금만 복잡해지면 곧 **멀티 Agent**(역할 분리, 병렬화, 상호검증, Human-in-the-loop)가 필요해집니다.

이때 핵심은 “에이전트가 똑똑한가”보다 **오케스트레이션(orchestration)을 어디에 두느냐**입니다.

- **LangGraph**: 상태 머신/그래프 기반. 제어 흐름이 코드로 명시적이라 프로덕션에서 강함. Router 패턴과 `Command`로 동적 분기/병렬 fan-out 지원.[^1]  
- **AutoGen**: 멀티 Agent를 “대화”로 모델링. `ConversableAgent`, `GroupChatManager`로 협업 구조가 직관적. 다만 브로드캐스트 구조는 토큰 비용/통제가 이슈가 되기 쉽다.[^2]  
- **CrewAI**: Agent/Task/Crew 추상화로 빠르게 팀을 꾸리고, Flow로 파이프라인화. `memory=True` 한 줄로 메모리 기본 탑재.[^3]  

이 글은 “비교”에 그치지 않고, **동일한 멀티 Agent 문제(Plan→Research→Code→Critique→Finalize)를 어떻게 구현/운영할지** 관점에서 정리합니다.

---

## 🔧 핵심 개념
### 1) 오케스트레이션 철학 3가지
1. **Graph/State Machine (LangGraph)**  
   - 워크플로를 **노드(node) + 엣지(edge) + 상태(state)**로 모델링  
   - 장점: 분기/재시도/승인(HITL)/병렬 실행을 “구조”로 잡아 **예측 가능**  
   - `Command`를 반환해 “다음 노드”를 런타임에 동적으로 결정(일종의 edgeless routing)[^4]  

2. **Conversation-Driven (AutoGen)**  
   - 멀티 Agent 협업을 “대화(turn)”로 표현  
   - `ConversableAgent`, `AssistantAgent`, `UserProxyAgent`로 사람/도구/LLM이 섞인 협업을 구성[^2]  
   - `GroupChatManager`가 메시지를 중계(사실상 브로드캐스트 허브)[^5]  

3. **Role + Task Orchestration (CrewAI)**  
   - 역할(Role)이 있는 Agent에게 Task를 배정하고 Crew가 실행 전략(Sequential/Hierarchical)을 결정[^6]  
   - Flow( @start/@listen )로 이벤트 기반 파이프라인 작성 가능[^7]  

### 2) 멀티 Agent 구현에서 진짜 중요한 4요소
- **(a) 라우팅/분해**: 어떤 Agent가 언제 호출되는가? (Router/Supervisor/Manager)[^1]  
- **(b) 공유 상태**: 각 Agent가 “무엇을 공유하고 무엇을 숨길지” (토큰 비용/보안/정확도에 직결)
- **(c) 실패 모델**: 재시도는 누가? fallback 경로는? 중간 결과는 저장되는가?
- **(d) 관찰 가능성**: 나중에 “왜 이런 결정을 했는지” 트레이싱 가능한가?

여기서 2026년 기준 실무적 결론은 보통 이겁니다:
- **탐색/협업 UX** 중심이면 AutoGen이 빠르고,
- **업무 파이프라인**(Task 중심)으로 빨리 만들면 CrewAI가 편하고,
- **복잡한 분기/장기 실행/감사 추적**이 필요하면 LangGraph가 유리합니다.[^8]  

---

## 💻 실전 코드
아래 예시는 “Supervisor(라우터)가 Plan을 만들고, Researcher/Coder/Critic를 필요에 따라 호출한 뒤, 최종 요약”하는 **멀티 Agent**를 세 프레임워크로 구현하는 최소 실행 예제입니다. (API 키는 환경변수로 가정)

### 1) LangGraph (Python) — Router + `Command`로 동적 분기
```python
# pip install langgraph langchain-core
# LANGGRAPH는 Router 패턴에서 Command/Send로 단일/병렬 라우팅을 구성할 수 있다.
# 아래는 단순화를 위해 "단일 라우팅(Command)" 중심으로 작성한다.

from typing import Literal, TypedDict, List
from langgraph.types import Command
from langgraph.graph import StateGraph, END

class State(TypedDict):
    goal: str
    plan: str
    artifacts: List[str]
    next: str

def planner(state: State) -> Command[Literal["research", "code", "final"]]:
    goal = state["goal"]
    # 실제론 LLM 호출로 plan 생성. 여기선 데모로 rule-based.
    plan = f"Plan: research -> code -> critique -> finalize for: {goal}"
    goto = "research" if "research" not in state.get("artifacts", []) else "code"
    return Command(goto=goto, update={"plan": plan, "artifacts": state.get("artifacts", [])})

def researcher(state: State) -> Command[Literal["code"]]:
    artifacts = state.get("artifacts", [])
    artifacts.append("research")  # 실제론 웹/RAG/툴 결과를 저장
    return Command(goto="code", update={"artifacts": artifacts})

def coder(state: State) -> Command[Literal["final"]]:
    artifacts = state.get("artifacts", [])
    artifacts.append("code")  # 실제론 코드 스니펫/패치 생성
    return Command(goto="final", update={"artifacts": artifacts})

def finalizer(state: State) -> Command[Literal[END]]:
    summary = f"{state['plan']}\nArtifacts={state.get('artifacts', [])}"
    return Command(goto=END, update={"next": summary})

g = StateGraph(State)
g.add_node("plan", planner)
g.add_node("research", researcher)
g.add_node("code", coder)
g.add_node("final", finalizer)

g.set_entry_point("plan")
graph = g.compile()

out = graph.invoke({"goal": "Build a multi-agent evaluator", "plan": "", "artifacts": [], "next": ""})
print(out["next"])
```
포인트:
- **노드가 `Command(goto=...)`를 반환**해서 “다음 노드”를 런타임에 결정합니다. 이게 LangGraph의 edgeless routing을 가능하게 하는 핵심 장치입니다.[^4]  

### 2) AutoGen (Python) — GroupChatManager로 대화 기반 협업
```python
# pip install autogen-agentchat~=0.2
# AutoGen은 ConversableAgent 기반으로 멀티 에이전트 채팅을 구성한다.

import autogen
from autogen.agentchat.contrib.gpt_assistant_agent import GPTAssistantAgent

# OAI_CONFIG_LIST 환경변수/JSON을 통해 모델 설정을 로드하는 패턴이 문서에 있다.
# (여기서는 구조만 보여준다)
config_list = autogen.config_list_from_json("OAI_CONFIG_LIST")

llm_config = {"config_list": config_list, "cache_seed": 42}

user_proxy = autogen.UserProxyAgent(
    name="UserProxy",
    system_message="Human admin who can approve final output.",
    human_input_mode="TERMINATE",
    code_execution_config={"use_docker": False, "last_n_messages": 2, "work_dir": "autogen_demo"},
)

planner = GPTAssistantAgent(name="Planner", instructions="Make a step-by-step plan.", llm_config=llm_config)
researcher = GPTAssistantAgent(name="Researcher", instructions="Gather key facts and constraints.", llm_config=llm_config)
coder = GPTAssistantAgent(name="Coder", instructions="Write implementation code.", llm_config=llm_config)
critic = GPTAssistantAgent(name="Critic", instructions="Find flaws, propose fixes.", llm_config=llm_config)

groupchat = autogen.GroupChat(
    agents=[user_proxy, planner, researcher, coder, critic],
    messages=[],
    max_round=8,
)
manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=llm_config)

user_proxy.initiate_chat(manager, message="Build a multi-agent pipeline with safety checks.")
```
포인트:
- `GroupChatManager`가 그룹 채팅을 관리하고, 각 Agent는 메시지를 주고받으며 협업합니다.[^9]  
- 구조가 직관적인 대신, 팀 규모가 커질수록 “모든 메시지를 모두가 공유”하는 형태가 되어 **토큰 비용/정보 과공유** 문제가 생기기 쉽습니다(설계로 완화 필요).

### 3) CrewAI (Python) — Task/Crew + memory=True로 빠른 팀 구성
```python
# pip install crewai
# CrewAI는 Agents/Tasks/Crew로 역할 기반 실행을 만든다.

from crewai import Agent, Task, Crew, Process

researcher = Agent(
    role="Researcher",
    goal="Collect constraints and references",
    backstory="Strong at reading docs and summarizing trade-offs.",
)

coder = Agent(
    role="Coder",
    goal="Implement a working prototype",
    backstory="Writes clean Python with good separation of concerns.",
)

critic = Agent(
    role="Critic",
    goal="Find failure modes and propose mitigations",
    backstory="Paranoid about edge cases, costs, and observability.",
)

t1 = Task(
    description="Research the best architecture for a multi-agent pipeline.",
    expected_output="Bullet list of architecture choices + risks",
    agent=researcher,
)

t2 = Task(
    description="Write runnable code skeleton for the chosen architecture.",
    expected_output="A Python code snippet with comments",
    agent=coder,
)

t3 = Task(
    description="Review the design and code, propose improvements.",
    expected_output="List of issues + fixes",
    agent=critic,
)

crew = Crew(
    agents=[researcher, coder, critic],
    tasks=[t1, t2, t3],
    process=Process.sequential,   # or Process.hierarchical
    memory=True,                  # 기본 메모리 시스템 on
    verbose=True,
)

result = crew.kickoff()
print(result)
```
포인트:
- `memory=True`로 **short-term/long-term/entity memory**를 기본 활성화하는 접근이 문서에 명시돼 있습니다.[^3]  
- Task 모델이 명확해 “업무 분해”가 쉬운 대신, 아주 복잡한 분기/병렬/재시도 정책을 세밀하게 제어하려면 Flow로 넘어가거나(또는 다른 오케스트레이션과 결합) 설계가 필요합니다.[^7]  

---

## ⚡ 실전 팁
1) **멀티 Agent의 비용 폭발을 먼저 막아라 (Token Topology 설계)**
- AutoGen의 GroupChat은 구조상 메시지 공유가 쉬워 생산성은 높지만, 무심코 설계하면 “전체 브로드캐스트”로 비용이 커집니다. `chat_messages_for_summary` 같은 요약/축약 지점을 설계해 대화 히스토리를 통제하세요.[^5]  
- LangGraph는 애초에 “노드별로 전달 상태”를 설계하므로, **필요한 상태만 흘려보내기**가 쉽습니다(대신 설계 부담이 있음).[^1]  

2) **Human-in-the-loop는 ‘에이전트’가 아니라 ‘워크플로 노드/단계’로 둬라**
- CrewAI는 Flow(@start/@listen)로 단계형 파이프라인을 만들 수 있어, 승인/검증 단계를 자연스럽게 끼우기 좋습니다.[^7]  
- AutoGen은 `UserProxyAgent`로 사용자 피드백을 런에 삽입하는 패턴이 문서에 있습니다. 승인 루프를 termination 조건과 함께 명확히 정의하세요.[^10]  

3) **Memory는 켜는 것보다 ‘스코프/정리 정책’이 더 중요**
- CrewAI는 기본 메모리에서 Short-Term(ChromaDB/RAG), Long-Term(SQLite3), Entity memory를 제공하지만, 오래 쌓이면 품질/성능이 흔들립니다. “어떤 Task 결과를 장기 저장할지”를 정책으로 두세요.[^3]  

4) **조합 전략: “협업은 AutoGen, 운영은 LangGraph”도 가능**
- 실무에서 자주 쓰는 하이브리드는:  
  - AutoGen으로 “탐색적 협업/코드 생성”을 하고  
  - LangGraph가 바깥에서 “상태/재시도/승인/관찰”을 책임지는 형태입니다. (구조적 통제를 그래프로 회수)[^11]  

---

## 🚀 마무리
- **LangGraph**는 멀티 Agent를 “그래프/상태 전이”로 다뤄 **통제·분기·병렬·디버깅**에 강합니다. `Command`/Router 같은 패턴을 익히면, 복잡도가 올라갈수록 빛을 봅니다.[^4]  
- **AutoGen**은 멀티 Agent 협업을 “대화”로 모델링해 직관적이고 빠릅니다. 대신 토큰/공유범위/요약 전략을 설계하지 않으면 비용과 혼란이 커집니다.[^2]  
- **CrewAI**는 Agent/Task/Crew/Flow로 역할 기반 개발에 강하고, `memory=True` 같은 생산성 포인트가 뚜렷합니다. 운영 단계로 갈수록 Flow와 관측/정책을 더 탄탄히 해야 합니다.[^3]  

다음 학습 추천:
1) LangGraph의 **Router/Supervisor 패턴**으로 “fan-out 병렬 + 결과 합성”을 실제 서비스 입력 분류에 적용[^1]  
2) AutoGen의 **selector group chat + UserProxyAgent 승인 루프**로 HITL 품질 보증 체계 만들기[^10]  
3) CrewAI **Flows(@start/@listen) + memory scopes**로 “장기 실행 파이프라인” 운영 모델 구축[^7]

[^1]: <https://docs.langchain.com/oss/python/langchain/multi-agent/router>
[^2]: <https://microsoft.github.io/autogen/0.2/docs/Use-Cases/agent_chat>
[^3]: <https://docs.crewai.com/en/concepts/memory>
[^4]: <https://blog.langchain.com/command-a-new-tool-for-multi-agent-architectures-in-langgraph>
[^5]: <https://microsoft.github.io/autogen/0.2/docs/reference/agentchat/groupchat>
[^6]: <https://docs.crewai.com/en/concepts/tasks>
[^7]: <https://docs.crewai.com/en/concepts/flows>
[^8]: <https://thread-transfer.com/blog/2025-03-15-ai-agent-frameworks-compared/>
[^9]: <https://microsoft.github.io/autogen/0.2/docs/notebooks/agentchat_oai_assistant_groupchat>
[^10]: <https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/selector-group-chat.html>
[^11]: <https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html>
