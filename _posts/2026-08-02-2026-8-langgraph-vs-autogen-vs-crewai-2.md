---
title: "“멀티 에이전트”를 진짜로 프로덕션에 올리는 법: LangGraph vs AutoGen vs CrewAI 심층 비교 & 구현 가이드"
description: "멀티 에이전트가 필요한 순간은 명확합니다. (1) 역할 분리(Research/Plan/Execute/Review)가 성능·품질에 직접 기여하고, (2) 루프/분기/재시도/승인(HITL) 같은 제어 흐름(control flow)이 제품 요구사항으로 고정될 때입니다."
date: 2026-08-02 03:37:30 +0900
categories: [AI, Agent]
tags: [ai, agent]
render_with_liquid: false
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
멀티 에이전트가 필요한 순간은 명확합니다. **(1) 역할 분리(Research/Plan/Execute/Review)**가 성능·품질에 직접 기여하고, **(2) 루프/분기/재시도/승인(HITL)** 같은 **제어 흐름(control flow)**이 제품 요구사항으로 고정될 때입니다. 반대로 “에이전트가 많을수록 똑똑해지겠지”라는 기대감으로 늘리면, 대부분 **비용·지연·실패율**만 올라갑니다(에이전트 간 대화 오버헤드, 컨텍스트 중복, 비결정성 증가).

2026년 8월 기준, 실무 관점에서 프레임워크 선택을 한 줄로 요약하면 이렇습니다.

- **LangGraph**: “워크플로우/상태/내구성(durability)”가 제품의 핵심이면 선택. 체크포인트·재개(resume)·장기 실행에 강함. LangSmith Deployment(구 LangGraph Platform)로 운영 인프라까지 연결 가능.[^1]  
- **AutoGen**: “대화 기반 협업(conversation-first)”이 자연스러운 **탐색형 작업**(리서치, 브레인스토밍, 자유로운 협상)에서 강점. Group chat 매니저/스피커 선택 등 메시지 기반 오케스트레이션이 중심.[^2]  
- **CrewAI**: “조직도/역할 기반(role-based)으로 빠르게 팀을 만들고, 정해진 프로세스로 돌린다”에 최적. Agents/Tasks/Processes + Flows로 빠른 배송.[^3]  

여기서 중요한 판단 기준: **당신의 시스템이 ‘대화’가 핵심인가, ‘상태를 가진 실행(runtime)’이 핵심인가**입니다. 비교 글들이 공통적으로 “LangGraph는 제어/디버깅/체크포인트가 강하고, CrewAI는 빠르며, AutoGen은 대화형 연구에 강하다”는 결론으로 수렴하는 이유가 여기에 있습니다.[^4]  

---

## 🔧 핵심 개념
### 1) 세 프레임워크의 “기본 단위”가 다르다
- **LangGraph = Graph(State Machine)**
  - 노드(node)는 함수/에이전트/툴 실행이고, 엣지(edge)는 다음으로 갈 경로(조건 분기 포함)입니다.
  - 핵심은 **typed state**를 “단일 진실 소스(SSOT)”로 두고, 각 단계가 state를 읽고/갱신하며 진행한다는 점.
  - 프로덕션에서 중요한 이유: 실패했을 때 **어느 state에서 깨졌는지**, 재시도는 **어느 노드부터** 해야 하는지, 사람 승인은 **어느 지점에서 interrupt**할지 설계가 가능. (장기 실행/재개를 전제로 함)[^5]  

- **AutoGen = Message(Conversation)**
  - 모든 것이 “메시지 교환”입니다. 에이전트는 conversable하고, 그룹 채팅에서 **다음 발화자(next speaker)**를 고르거나, 자동 응답 함수를 플러그인처럼 끼우는 방식으로 흐름을 만듭니다.[^2]  
  - 장점: 탐색형 문제에서 자연스럽고, “대화가 곧 로그”라서 실험이 빠름.
  - 단점: 복잡한 비즈니스 프로세스(승인/재시도/정책 게이트/정확한 상태 복구)에서는 메시지 흐름을 상태기계로 “다시 모델링”하게 되는 순간이 자주 옴.

- **CrewAI = Roles + Tasks/Process**
  - Agent(역할/도구/메모리/지식)와 Task를 선언하고, Process(sequential/hierarchical/hybrid)로 실행합니다.
  - Flows( start/listen/router 등 )로 워크플로우를 확장해 장기 실행·상태·재개를 다루려는 방향성이 문서에 명확히 잡혀 있습니다.[^3]  
  - 장점: “회사에서 실제로 하는 방식”과 비슷하게 설계가 가능해 커뮤니케이션 비용이 낮음.
  - 단점: 프로세스가 복잡해질수록(다중 루프, 부분 재시도, 세밀한 분기) 결국 “그래프/상태기계” 영역으로 들어가며, 그때 추상화가 오히려 제약이 될 수 있음.

### 2) 멀티 에이전트 구현의 본질: “분업”이 아니라 “검증 루프”다
현업에서 멀티 에이전트가 성능을 올리는 패턴은 대체로:
- Planner(계획) → Executor(실행) → Reviewer(검증) → Fixer(수정) 같은 **폐루프(closed loop)**  
- Evidence gating(근거 없으면 다음 단계로 못 감), Policy/HITL gate(승인 전엔 실행 불가)[^5]  

즉, **멀티 에이전트 = 다양한 “역할”보다, 다양한 “게이트/검증자”를 붙이는 구조**로 접근해야 운영 품질이 올라갑니다.

---

## 💻 실전 코드
현실적인 시나리오: **“릴리스 노트 자동 생성 + 위험 변경 감지”**  
- 입력: Git diff(또는 PR summary), 관련 이슈 링크(선택)  
- 출력: (1) 고객용 릴리스 노트 초안, (2) 위험 변경 목록(보안/Breaking change), (3) 승인 필요 여부  
- 요구: 실패 시 재시도, Reviewer가 “근거 부족”이면 Researcher가 추가 근거를 찾아오고, 마지막에 Human approval이 들어가면 좋음

아래 예시는 **LangGraph로 ‘상태 중심’ 멀티 에이전트 루프**를 구현합니다. (실무에서 “언젠가 반드시 필요해지는” 구조라서, 한 번 제대로 익혀두면 다른 프레임워크에서도 응용이 됩니다.)

### 0) 설치/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install -U langgraph langchain-openai pydantic python-dotenv
export OPENAI_API_KEY="YOUR_KEY"
```

### 1) 그래프 설계: 상태 + 노드 + 조건 라우팅
```python
# release_notes_agent.py
from __future__ import annotations
from typing import TypedDict, Literal, List, Optional
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# 1) State: 실행 내내 유지/체크포인트 되는 "단일 진실"
class RiskItem(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    evidence: str

class AgentState(TypedDict):
    diff: str
    context_links: List[str]
    draft_release_notes: Optional[str]
    risks: List[RiskItem]
    reviewer_feedback: Optional[str]
    approved: bool
    iteration: int

llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)

def researcher(state: AgentState) -> AgentState:
    # 실제로는: context_links를 크롤링/검색툴로 증거 수집(RAG) 붙이는 지점
    msg = HumanMessage(content=f"""
다음 diff를 보고 릴리스 노트에 필요한 핵심 변경점과 근거가 될 만한 단서를 정리해줘.
diff:
{state['diff']}
링크:
{state['context_links']}
""")
    out = llm.invoke([SystemMessage(content="You are a senior engineer doing change analysis."), msg]).content
    # 여기서는 간단히 reviewer가 참고할 수 있게 draft에 섞어둔다(실무라면 별도 evidence 필드 추천)
    state["draft_release_notes"] = (state.get("draft_release_notes") or "") + "\n\n[Research Notes]\n" + out
    return state

def writer(state: AgentState) -> AgentState:
    msg = HumanMessage(content=f"""
너는 제품 릴리스 노트 작성자야. 고객이 이해할 수 있게 bullet로 작성해.
반드시 과장하지 말고 diff에 근거한 내용만 써.
diff:
{state['diff']}
추가 메모:
{state.get('draft_release_notes') or ""}
""")
    out = llm.invoke([SystemMessage(content="Write concise release notes for end users."), msg]).content
    state["draft_release_notes"] = out
    return state

def risk_reviewer(state: AgentState) -> AgentState:
    msg = HumanMessage(content=f"""
다음 릴리스 노트 초안과 diff를 보고 위험 변경을 JSON으로 뽑아줘.
- breaking change, security, data loss 가능성은 high 우선
- evidence 필드에는 diff의 근거를 짧게 인용/요약
형식:
[{{"title": "...", "severity": "low|medium|high", "evidence": "..."}}]

diff:
{state['diff']}

draft:
{state['draft_release_notes']}
""")
    out = llm.invoke([SystemMessage(content="You are a strict reviewer."), msg]).content

    # 실무에서는 structured output / json schema 강제 추천(파싱 안정성)
    import json
    try:
        items = json.loads(out)
        state["risks"] = [RiskItem(**x) for x in items]
        state["reviewer_feedback"] = None
    except Exception:
        state["reviewer_feedback"] = "리스크 JSON 파싱 실패. 형식 재작성 필요."
    return state

def decision(state: AgentState) -> str:
    # 조건 라우팅: "다시 조사/다시 작성/승인" 같은 분기
    state["iteration"] += 1
    if state.get("reviewer_feedback"):
        return "writer"  # 형식 깨졌으면 다시 쓰게
    if any(r.severity == "high" for r in state["risks"]):
        return "researcher" if state["iteration"] < 3 else "need_approval"
    return "done"

# 2) Graph wiring
from langgraph.graph import StateGraph, END

graph = StateGraph(AgentState)
graph.add_node("researcher", researcher)
graph.add_node("writer", writer)
graph.add_node("risk_reviewer", risk_reviewer)

graph.set_entry_point("researcher")
graph.add_edge("researcher", "writer")
graph.add_edge("writer", "risk_reviewer")
graph.add_conditional_edges("risk_reviewer", decision, {
    "writer": "writer",
    "researcher": "researcher",
    "need_approval": END,  # 여기서 HITL 승인 단계로 넘기는 게 실무 패턴
    "done": END
})

app = graph.compile()

if __name__ == "__main__":
    init: AgentState = {
        "diff": "feat(api): change auth header from X-Auth to Authorization: Bearer ...\nfix: sanitize logs ...",
        "context_links": ["https://internal-jira/browse/SEC-123"],
        "draft_release_notes": None,
        "risks": [],
        "reviewer_feedback": None,
        "approved": False,
        "iteration": 0,
    }
    result = app.invoke(init)
    print("=== Release Notes ===")
    print(result["draft_release_notes"])
    print("\n=== Risks ===")
    for r in result["risks"]:
        print(f"- [{r.severity}] {r.title} :: {r.evidence}")
    print("\niterations:", result["iteration"])
```

### 예상 출력(예시)
- Release Notes: “인증 방식이 Bearer 토큰으로 변경…”, “로그가 민감정보를 덜 남기도록 수정…”  
- Risks: `[high] 인증 헤더 변경으로 기존 클라이언트 breaking 가능`, evidence에 diff 근거 요약  
- iteration: high risk면 researcher 재진입 1~2회 후 종료

### 2) 운영까지 생각하면: “내구성(durable) 실행”이 핵심
장기 실행/재개가 필요한 순간(예: 승인 대기, 외부 시스템 장애)부터는 “로컬 파이썬 실행”이 아니라 **체크포인트/스레드/런**을 가진 런타임이 필요합니다. LangGraph 생태계는 이를 LangSmith Deployment(관리형) 또는 Standalone 서버(자체 호스팅)로 연결하는 흐름을 공식 문서로 제공합니다.[^1]  

특히 자체 호스팅 구성에서 **Redis(스트리밍/브로커), Postgres(threads/runs/memory), 체크포인터 백엔드(Postgres/Mongo 선택)** 같은 “운영 필수 구성요소”가 문서에 구체적으로 박혀 있는 점이, 2026년에 LangGraph가 프로덕션에서 강하다고 평가되는 이유 중 하나입니다.[^6]  

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “에이전트 수”가 아니라 “게이트 수”를 설계하라
멀티 에이전트에서 품질을 올리는 건 대개 **Reviewer / Policy / Evidence gate**입니다. Writer/Researcher를 늘리는 것보다, “근거 없으면 다음 단계 못 감” 같은 **진입 조건**을 명시하세요. (LangGraph는 conditional edge로, CrewAI는 process+guardrails/flows로, AutoGen은 매니저의 next-speaker 로직으로 구현)

### Best Practice 2) State에 “대용량 원문”을 넣지 마라
LangGraph 계열에서 체크포인트는 상태 전체를 저장합니다. 대용량 텍스트/파일을 state에 박으면 **DB bloat + 느려짐 + 트레이스 비용 증가**로 이어집니다. 공식 가이드도 “큰 payload는 외부 스토리지에 두고 reference만 state에”를 강하게 권합니다.[^7]  

### Best Practice 3) 재시도는 “전체 리런”이 아니라 “부분 재시도”로
실패율을 낮추는 가장 큰 레버는 모델을 바꾸는 게 아니라, **어디서 실패했는지 분리**하고 그 지점만 재시도하게 만드는 겁니다.
- LangGraph: 노드 단위 재시도/루프 구조가 자연스러움(그래프의 강점).
- CrewAI: process가 단순할 땐 빠르지만, 부분 재시도가 복잡해지면 Flow/상태 설계를 더 적극적으로 해야 함.[^3]  
- AutoGen: 메시지 기반이라 “어느 메시지부터 재개”를 설계하지 않으면 대화가 길어질수록 비용이 폭증.

### 흔한 함정) “대화 로그 = 디버깅”이라고 착각
대화는 보기엔 그럴싸하지만, 운영에서 필요한 건
- 어떤 입력이 어떤 상태를 만들었는지
- 어느 단계의 결과가 다음 단계에 영향을 줬는지
- 실패한 run을 재현할 수 있는지
입니다. 비교 글들이 반복해서 “debuggability가 진짜 차별점”이라고 말하는 이유가 여기에 있습니다.[^8]  

### 비용/성능/안정성 트레이드오프(현실)
- 에이전트가 늘면 **token 중복**(같은 diff를 여러 번 읽음)이 가장 먼저 터집니다.
- 안정성은 “모델 성능”보다 “제어 흐름/재시도/검증/상태관리”에서 결정되는 비중이 커졌고, 2026년 연구/사례들도 테스트/문서/유지보수 취약성을 지적합니다.[^9]  

---

## 🚀 마무리
정리하면, 2026년 8월에 멀티 에이전트를 “내 프로젝트에 적용”하려면 기능 비교표보다 아래 3가지를 먼저 답해야 합니다.

1) 내 문제는 **대화형 탐색**인가, **상태를 가진 프로세스 실행**인가?  
- 탐색형이면 AutoGen 접근이 자연스럽고,  
- 승인/재개/정책/재시도 같은 운영 요구가 강하면 LangGraph 쪽으로 기웁니다.[^2]  

2) 팀이 원하는 속도는 “프로토타입 속도”인가, “운영 안정성까지 포함한 속도”인가?  
- 빠르게 역할/태스크로 묶어 성과를 보여야 하면 CrewAI가 유리하고,  
- 3개월 뒤 장애·재현·부분 재시도를 생각하면 그래프/체크포인트 중심 설계가 결국 시간을 절약합니다.[^3]  

3) 멀티 에이전트의 목적을 “분업”으로 두지 말고 “검증 루프”로 두었는가?  
- Reviewer/Evidence gate를 먼저 설계하면, 에이전트 수를 늘리지 않고도 품질이 오릅니다.[^10]  

다음 학습 추천(우선순위):
- LangGraph로 **conditional routing + retry budget + checkpoint/resume** 패턴을 1개라도 실서비스 시나리오로 만들어보기[^5]  
- CrewAI의 **Tasks/Processes vs Flows** 경계를 이해하고, “프로세스가 복잡해질 때 어디서부터 Flow로 내려갈지” 기준 세우기[^3]  
- AutoGen은 Group chat에서 **next-speaker 정책**을 코드로 명시해 “대화가 흘러가다 끝나는” 것을 방지하기[^2]

[^1]: <https://www.langchain.com/langsmith/deployment>
[^2]: <https://microsoft.github.io/autogen/docs/Use-Cases/agent_chat/>
[^3]: <https://docs.crewai.com/index>
[^4]: <https://pecollective.com/tools/langgraph-vs-crewai-vs-autogen/>
[^5]: <https://arxiv.org/abs/2607.19297>
[^6]: <https://docs.langchain.com/langsmith/deploy-standalone-server>
[^7]: <https://kb.langchain.com/articles/1242226068-how-do-i-configure-checkpointing-in-langgraph>
[^8]: <https://www.examcert.app/blog/langgraph-vs-crewai-vs-autogen-agent-frameworks-2026/>
[^9]: <https://arxiv.org/abs/2601.07136>
[^10]: <https://arxiv.org/abs/2607.20499>
