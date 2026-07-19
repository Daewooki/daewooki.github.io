---
title: "2026년 7월, “멀티 에이전트”를 진짜로 출시하려면: LangGraph vs AutoGen(AG2) vs CrewAI 심층 비교 + 구현 가이드"
date: 2026-07-19 03:34:08 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-07]
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
멀티 에이전트가 해결하는 문제는 간단히 말해 **“LLM 호출을 여러 번/여러 역할로 나눴을 때 생기는 복잡성(상태, 분기, 재시도, 승인, 추적, 비용)을 시스템적으로 관리”**하는 것입니다. 데모는 쉽지만, 출시 단계에서 터지는 건 보통 다음 3가지입니다.

- **상태(State) 관리 실패**: 중간 결과/컨텍스트가 누락되거나, 실패 후 재실행 시 같은 단계부터 다시 못 이어감
- **오케스트레이션 난이도**: 분기/병렬/루프/재시도/휴먼 승인(HITL)이 늘면서 코드가 스파게티화
- **디버깅/감사(Audit) 불가**: “왜 이 결론이 나왔는지”를 재현/설명 못함

이 관점에서 2026년 mid-year 기준으로 세 프레임워크는 지향점이 확실히 갈립니다.

- **LangGraph**: “상태ful 그래프 런타임”에 올인. 체크포인트 기반 **time travel(리플레이/포크)**가 핵심 차별점. ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/use-time-travel?utm_source=openai))  
- **CrewAI**: “역할 기반 role-play + Task 파이프라인”을 최단거리로. 대신 복잡한 제어 흐름은 한계가 빨리 옴(관리자/계층 프로세스로 보완 가능). ([docs.crewai.com](https://docs.crewai.com/core-concepts/Agents?utm_source=openai))  
- **AutoGen(AG2)**: “대화형 GroupChat 오케스트레이션”에 강점. 다만 프로덕션 관점에서 **지속성/운영**은 직접 설계할 부분이 많다는 평가가 많음. ([docs.ag2.ai](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/tools/?utm_source=openai))  

### 언제 쓰면 좋고 / 안 쓰면 좋은가
- LangGraph 추천
  - 분기/재시도/중단-재개/승인 게이트가 있는 **장기 실행 workflow**
  - 장애가 “자주” 나는 도메인(외부 API, 크롤링, 사내 시스템)에서 **부분 재개**가 중요
  - 규제/감사 대응(“이 결정을 만든 근거/경로”)이 필요한 제품 ([langchain-ai.github.io](https://langchain-ai.github.io/langgraph/reference/checkpoints/?h=langgraph+checkpoint+sqlite+import+saver&utm_source=openai))
- CrewAI 추천
  - “리서치→요약→작성→검수” 같은 **선형 파이프라인**을 빨리 만들어야 함
  - 팀 합류/온보딩이 중요하고, 복잡한 런타임보다 생산성이 우선 ([docs.crewai.com](https://docs.crewai.com/core-concepts/Agents?utm_source=openai))
- AutoGen(AG2) 추천
  - 에이전트들이 **토론/협상/상호 수정**하며 수렴하는 형태(브레인스토밍, 코드 리뷰, 연구) ([docs.ag2.ai](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/tools/?utm_source=openai))
- 멀티 에이전트를 피하는 게 나은 경우
  - “한 번의 tool call + 한 번의 정제”로 해결되는 문제(오버헤드만 증가)
  - SLA가 엄격한데(예: p95 1~2초), 다중 LLM 왕복이 필연인 구조
  - 테스트/관측/실패 복구 설계 없이 “에이전트 수만 늘리는” 접근(신뢰도/속도 모두 악화) ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1t7k4co/at_what_point_does_adding_another_agent_actually/?utm_source=openai))  

---

## 🔧 핵심 개념
세 프레임워크 비교는 “기능표”보다 **런타임 모델(mental model)**로 봐야 정확합니다.

### 1) LangGraph: Graph + State + Checkpoint(=time travel)
- **정의**
  - Node: 한 단계(LLM 호출, tool 호출, 라우팅 등)
  - Edge: 다음 단계로의 전이(조건부 가능)
  - State: 그래프 전체가 공유/갱신하는 구조화된 데이터
- **내부 흐름(중요)**
  1) 노드 실행 → State를 부분 업데이트
  2) 각 step마다 **Checkpoint에 State 스냅샷 저장**
  3) 실패 시 “처음부터”가 아니라 **특정 checkpoint부터 재개** 가능  
     - Replay: 같은 지점에서 다시 실행
     - Fork: State를 수정하고 다른 경로로 재실행 ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/use-time-travel?utm_source=openai))
- **왜 이게 프로덕션에서 강하나**
  - 체크포인트가 “로그”가 아니라 **런타임 재개 단위**라서 운영 난이도가 확 떨어짐
  - 단, “State 전체가 저장”되는 구조라서 **큰 payload를 State에 넣으면 비용/성능/보안이 즉시 터짐**(레퍼런스 저장 권장). ([kb.langchain.com](https://kb.langchain.com/articles/1242226068-how-do-i-configure-checkpointing-in-langgraph?utm_source=openai))

### 2) CrewAI: Task 파이프라인 + Process(Sequential/Hierarchical)
- **정의**
  - Agent: 역할/목표/툴 보유
  - Task: 한 에이전트가 수행할 작업 단위
  - Process:
    - Sequential: Task를 순서대로 실행하며 출력이 다음 단계 컨텍스트로 전달
    - Hierarchical: Manager가 분해/할당/재할당/검수를 반복 ([learn.engineering.vips.edu](https://learn.engineering.vips.edu/agent-protocols/crewai-hierarchical-process?utm_source=openai))
- **차이점**
  - LangGraph는 “흐름 제어”가 1급 시민(조건/루프/재시도)
  - CrewAI는 “역할과 생산성”이 1급 시민(흐름은 상대적으로 단순)

### 3) AutoGen(AG2): GroupChat 기반 협업(Conversational orchestration)
- **정의**
  - 여러 에이전트가 **그룹 대화**로 문제를 풀고, Manager가 발화 순서를 조정
  - 각 에이전트는 툴을 등록해서 대화 중 호출 가능 ([docs.ag2.ai](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/tools/?utm_source=openai))
- **차이점**
  - LangGraph/CrewAI가 “워크플로우”라면 AutoGen은 “회의”
  - 연구/아이디어 수렴에는 강하지만, **상태 지속성/운영 제어**는 직접 설계할 일이 많음(프로덕션에서는 이게 비용). ([saturncube.com](https://www.saturncube.com/blog/crewai-vs-autogen-vs-langgraph?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: **“사내 티켓(Incident/Support) 요약 → 원인 후보 분석 → Runbook 기반 대응안 생성 → 사람 승인(HITL) → 실행”**  
요구사항은 보통 이렇습니다.

- 외부 시스템(Jira/Slack/PagerDuty/DB) 호출은 실패한다(재시도 필요)
- 사람이 승인해야 실제 조치(예: feature flag off, 롤백)로 넘어간다
- 실패 지점부터 이어서 실행해야 운영이 된다(처음부터 다시 돌리면 비용 폭발)

여기서는 **LangGraph로 “멀티 에이전트 + 체크포인트 기반 재개”**를 구현하고, CrewAI/AG2로 옮길 때 어떤 부분이 달라지는지 기준을 잡겠습니다.

### 0) 의존성/환경 (Python)
```bash
python -m venv .venv
source .venv/bin/activate

pip install -U langgraph langchain openai psycopg[binary] psycopg-pool pydantic python-dotenv
# DB는 Postgres 권장(운영), 로컬은 docker로 띄우는 걸 추천
```

`.env`
```bash
OPENAI_API_KEY=...
POSTGRES_CHECKPOINTER_URI=postgresql://user:pass@localhost:5432/langgraph
```

### 1) LangGraph: Supervisor + Worker(분석/플랜/검수) + HITL 게이트
핵심은 **State를 작게/명확하게** 잡고, “승인 전에는 실행하지 않는다”를 그래프로 강제하는 겁니다.

```python
# python
import os
from typing import Literal, Optional
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# --------
# 1) State 정의: 큰 원문(로그 전체)을 넣지 말고, 저장소 key/요약만 들고 간다
# --------
class TicketState(BaseModel):
    thread_id: str
    ticket_id: str
    raw_context_ref: str  # ex) s3://... or db key
    summary: Optional[str] = None
    hypotheses: list[str] = Field(default_factory=list)
    plan: Optional[str] = None
    requires_approval: bool = True
    approval: Optional[Literal["approved", "rejected"]] = None
    action_result: Optional[str] = None
    last_error: Optional[str] = None

# --------
# 2) 노드 구현(여기서는 예시로 "LLM 호출" 부분을 함수 형태로 둠)
#    실제로는 OpenAI/Anthropic 등 호출 + tool calling 섞으면 된다.
# --------
def summarize(state: TicketState) -> dict:
    # TODO: raw_context_ref로부터 로그/티켓 본문 로딩 (DB/S3)
    # TODO: LLM 요약 생성
    summary = f"[ticket:{state.ticket_id}] 요약: 간헐적 500, 배포 직후 증가, 특정 리전 집중"
    return {"summary": summary}

def analyze_hypotheses(state: TicketState) -> dict:
    # TODO: LLM + runbook/metrics tool 사용해서 가설 리스트업
    hypos = [
        "최근 배포된 API gateway 설정 변경으로 timeout 증가",
        "특정 리전의 DB connection pool 고갈",
        "캐시 미스율 급증으로 backend 부하 증가",
    ]
    return {"hypotheses": hypos}

def propose_plan(state: TicketState) -> dict:
    # TODO: LLM이 실행 계획 작성(단, 실행은 다음 단계에서)
    plan = """1) 리전별 error rate/latency 확인
2) DB pool usage 확인 및 max_conn 임시 상향 검토
3) 문제 배포 버전 feature flag off 가능성 평가
4) 롤백 시 영향도/승인 요청 템플릿 생성"""
    return {"plan": plan, "requires_approval": True}

def request_approval(state: TicketState) -> dict:
    # 현실: Slack/Teams로 승인 요청 보내고, 사람 응답을 기다림
    # 여기서는 간단히 "대기 상태"를 만들고 외부에서 approval을 채우는 방식으로 설계
    if state.approval is None:
        # interrupt/hitl 패턴을 쓸 수 있지만, 핵심은 "승인 없으면 진행 불가"를 그래프로 보장하는 것
        return {}
    return {}

def execute_actions(state: TicketState) -> dict:
    if state.approval != "approved":
        return {"action_result": "승인되지 않아 실행 스킵"}
    # TODO: 실제 조치(Feature flag, 롤백, 설정 변경) tool 호출
    return {"action_result": "feature flag off 적용 + DB pool 상향, 10분 관찰 요청"}

def route_after_approval(state: TicketState) -> Literal["execute", "end", "wait"]:
    if state.approval is None:
        return "wait"
    if state.approval == "approved":
        return "execute"
    return "end"

# --------
# 3) Checkpointer(Postgres) 설정
#    각 checkpoint가 state 전체 스냅샷을 갖고 time travel(Replay/Fork)의 기반이 된다.
# --------
def build_checkpointer() -> PostgresSaver:
    conn_string = os.environ["POSTGRES_CHECKPOINTER_URI"]
    pool = ConnectionPool(
        conn_string,
        max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    saver = PostgresSaver(pool)
    saver.setup()
    return saver

# --------
# 4) Graph 정의
# --------
def build_graph():
    g = StateGraph(TicketState)
    g.add_node("summarize", summarize)
    g.add_node("analyze", analyze_hypotheses)
    g.add_node("plan", propose_plan)
    g.add_node("approval", request_approval)
    g.add_node("execute", execute_actions)

    g.set_entry_point("summarize")
    g.add_edge("summarize", "analyze")
    g.add_edge("analyze", "plan")
    g.add_edge("plan", "approval")

    g.add_conditional_edges(
        "approval",
        route_after_approval,
        {
            "wait": "approval",   # 승인 들어올 때까지 loop
            "execute": "execute",
            "end": END,
        },
    )
    g.add_edge("execute", END)

    checkpointer = build_checkpointer()
    return g.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    app = build_graph()

    # 같은 thread_id로 여러 번 호출하면 checkpoint를 기반으로 이어서 실행 가능
    init = TicketState(
        thread_id="inc-2026-07-19-001",
        ticket_id="INC-18421",
        raw_context_ref="db:tickets/INC-18421",
    )

    # 1차 실행: 승인 없으니 approval 노드에서 루프/대기 상태
    out = app.invoke(init, config={"configurable": {"thread_id": init.thread_id}})
    print("1차 결과:", out.model_dump())

    # 운영에서는 승인 이벤트가 들어오면 state를 업데이트하고 재호출
    init.approval = "approved"
    out2 = app.invoke(init, config={"configurable": {"thread_id": init.thread_id}})
    print("2차 결과:", out2.model_dump())
```

#### 예상 출력(요약)
- 1차 결과: `summary/hypotheses/plan`까지 채워지고 `approval=None` 상태로 대기
- 2차 결과: `approval=approved`가 들어오면 `execute`까지 진행, `action_result` 채워짐

#### 왜 이 예제가 “toy”가 아닌가
- 승인 게이트/루프가 실제 운영 요구사항이고(보안/권한/책임)
- 실패/재시도 시 “어디부터 재개하느냐”가 비용과 MTTR을 결정함
- State에 원문 로그를 넣지 않고 **reference만 저장**하도록 강제(체크포인트 저장 비용/보안 고려) ([kb.langchain.com](https://kb.langchain.com/articles/1242226068-how-do-i-configure-checkpointing-in-langgraph?utm_source=openai))

### CrewAI/AG2로 옮기면 무엇이 달라지나(핵심만)
- CrewAI:
  - 위 시나리오에서 `summarize→analyze→plan`은 **Process.sequential**로 매우 빠르게 구현됨
  - 하지만 “승인 대기→재개→실행” 같은 **장기 실행/루프**는 Crew 내부만으로는 설계가 빡세고, 보통 상위 오케스트레이터(별도 서비스/큐/워크플로우 엔진)와 결합하게 됨 ([devshelfhub.com](https://www.devshelfhub.com/tutorials/crewai/reference/classes/process/?utm_source=openai))
- AutoGen(AG2):
  - `GroupChat`으로 SRE/DBA/Backend agent가 토론하면서 plan을 다듬는 UX는 매우 좋음
  - 대신 “승인 전 실행 불가” 같은 정책 강제와 체크포인트/재개는 아키텍처로 메워야 함 ([docs.ag2.ai](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/tools/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 효과 나는 것 3가지)
1) **State는 ‘작고 결정적’으로**  
   체크포인트는 State 전체를 저장합니다. 로그/이미지/PDF를 그대로 넣으면 DB bloat + 추적 데이터 노출 + 비용 폭발. “원문은 외부 저장소, State에는 ref+요약”이 안전합니다. ([kb.langchain.com](https://kb.langchain.com/articles/1242226068-how-do-i-configure-checkpointing-in-langgraph?utm_source=openai))

2) **승인/정책을 “프롬프트”가 아니라 “그래프/코드”로 강제**  
   “승인 없으면 실행하지 마”를 system prompt로만 해결하면 언젠가 뚫립니다. 라우팅/가드 노드로 구조화하세요.

3) **디버깅 비용은 ‘50번째 실패’에서 갈린다**  
   데모 단계에서는 CrewAI가 가장 빨리 보이지만, 운영에서는 “실패 지점부터 재개/포크”가 되는 쪽이 인건비를 줄입니다(특히 LangGraph의 time travel). ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/use-time-travel?utm_source=openai))

### 흔한 함정/안티패턴
- **에이전트 수를 늘려서 품질을 올리려는 접근**  
  조율/컨텍스트 전달/토큰 오버헤드가 늘며 오히려 느려지고 불안정해질 수 있습니다. 필요한 “역할”만 남기고, 나머지는 tool+검증 로직으로 내리세요. ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1t7k4co/at_what_point_does_adding_another_agent_actually/?utm_source=openai))
- **체크포인트가 있으니 뭐든 State에 넣는 패턴**  
  저장/보안/개인정보 이슈가 운영에서 폭발합니다. TTL/보존 정책까지 같이 설계해야 합니다. ([kb.langchain.com](https://kb.langchain.com/articles/1242226068-how-do-i-configure-checkpointing-in-langgraph?utm_source=openai))
- **AutoGen/대화형 협업을 프로덕션 런타임으로 그대로 사용**  
  연구/실험에는 훌륭하지만, 재현성/운영성(지속성, 리플레이, 승인, 비용 제한)은 별도 설계 없이는 구멍이 생깁니다. ([docs.ag2.ai](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/tools/?utm_source=openai))

### 비용/성능/안정성 트레이드오프(요약)
- LangGraph: 초기 설계 비용↑(그래프/State 설계) ↔ 운영 안정성/복구력↑(checkpoint/time travel) ([langchain-ai.github.io](https://langchain-ai.github.io/langgraph/reference/checkpoints/?h=langgraph+checkpoint+sqlite+import+saver&utm_source=openai))
- CrewAI: 초기 속도↑ ↔ 복잡 제어 흐름/장기 실행에서 외부 오케스트레이션 필요 가능성↑ ([devshelfhub.com](https://www.devshelfhub.com/tutorials/crewai/reference/classes/process/?utm_source=openai))
- AutoGen(AG2): 협업/토론 품질↑ ↔ 프로덕션 지속성/통제는 직접 메워야 할 확률↑ ([docs.ag2.ai](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/tools/?utm_source=openai))

---

## 🚀 마무리
핵심 정리:
- **“멀티 에이전트”의 본질은 에이전트 수가 아니라, 실패/상태/승인/디버깅을 감당하는 런타임**입니다.
- 2026년 7월 기준으로,
  - **LangGraph**는 체크포인트 기반 **time travel(Replay/Fork)**로 “운영 가능한 워크플로우”를 만들기 좋고 ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/use-time-travel?utm_source=openai))
  - **CrewAI**는 “역할 기반 선형 파이프라인”을 가장 빠르게 만들며, 계층형 프로세스로 일부 확장 가능하지만 토큰/디버깅 비용이 증가합니다 ([learn.engineering.vips.edu](https://learn.engineering.vips.edu/agent-protocols/crewai-hierarchical-process?utm_source=openai))
  - **AutoGen(AG2)**는 “대화형 협업”에 강하되, 프로덕션 운영성은 별도 설계가 필요합니다 ([docs.ag2.ai](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/tools/?utm_source=openai))

도입 판단 기준(실무 체크리스트):
1) **중단/재개가 필요한가?** (승인 대기, 외부 API 불안정, 장기 실행) → LangGraph 우선
2) **분기/루프/재시도가 많은가?** → LangGraph 우선
3) **선형 파이프라인이 대부분이고, 출시 속도가 최우선인가?** → CrewAI 우선
4) **에이전트 간 토론/협상이 핵심 가치인가?** → AutoGen(AG2) 고려(단 운영 설계 포함)

다음 학습 추천:
- LangGraph의 **Persistence/Checkpointing**과 **time travel**을 먼저 깊게 보고(“State를 어떻게 설계해야 하는가”가 80%) ([kb.langchain.com](https://kb.langchain.com/articles/1242226068-how-do-i-configure-checkpointing-in-langgraph?utm_source=openai))
- CrewAI는 **Process.sequential vs hierarchical**의 비용/디버깅 차이를 실제 업무 플로우로 검증해보세요 ([learn.engineering.vips.edu](https://learn.engineering.vips.edu/agent-protocols/crewai-hierarchical-process?utm_source=openai))
- AutoGen(AG2)은 GroupChat 기반 시스템을 만들되, “대화 로그=상태”로 끝내지 말고 **영속 상태/정책 강제/재현성**을 별도 계층으로 설계하는 연습이 필요합니다 ([docs.ag2.ai](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/tools/?utm_source=openai))