---
title: "Supervisor가 “팀장(Planner/Router)”, Worker가 “전문가(Executor)”인 순간부터, Multi‑Agent는 **프롬프트 기교가 아니라 런타임 설계 문제**가 됩니다 — 2026년형 Supervisor/Worker 오케스트레이션 심층 분석"
date: 2026-06-20 04:20:21 +0900
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
2026년 6월 기준 multi-agent orchestration은 “여러 에이전트가 채팅하는 데모”를 넘어, **비용/신뢰성/운영**을 정면으로 다루는 아키텍처로 자리 잡았습니다. 특히 Supervisor/Worker 패턴(= manager-worker, orchestrator-worker)은 여전히 “프로덕션 기본값”으로 가장 많이 채택됩니다. ([paiteq.com](https://www.paiteq.com/blog/multi-agent-orchestration-patterns/?utm_source=openai))

이 패턴이 해결하는 구체적 문제는 다음입니다.

- **복잡한 작업을 분해**(task decomposition)하고, 서로 다른 tool/model/prompt를 가진 Worker들에게 위임
- 결과를 **검증/합성**(validation/synthesis)해 “사용자에게 일관된 최종 답”을 제공
- 장애가 발생해도 **부분 실패를 격리**하고, 재시도/대체 경로/중단을 시스템적으로 통제

언제 쓰면 좋은가
- 작업이 **명확히 여러 서브태스크로 분해**되고(예: “설계→구현→테스트→리뷰”), 각 단계가 서로 다른 역량/툴을 요구할 때
- **가드레일을 한 곳에 모으고**(정책/보안/PII/툴 허용 목록), 최종 산출의 톤&품질을 통제해야 할 때
- 비용 최적화가 “모델 선택”보다 “흐름 설계”에서 크게 갈릴 때(2026년 연구/실무 모두 이 방향을 강하게 시사) ([arxiv.org](https://arxiv.org/abs/2602.16873))

언제 쓰면 안 되는가
- 사실상 “단일 에이전트가 함수 몇 번 호출” 수준이라면 굳이 multi-agent로 포장할 필요가 없습니다. 오히려 디버깅/평가가 어려워집니다(커뮤니티에서도 이 비판이 반복됨). ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1tbb2bp/most_multiagent_orchestration_is_just_a_single/?utm_source=openai))
- **절차적(procedural)이고 결정적인 작업**(정해진 규칙대로만 처리)이라면, orchestration을 LLM에게 맡기기보다 코드로 고정하는 편이 빠르고 예측 가능합니다. (오케스트레이션을 “LLM vs 코드”로 어디까지 둘지 경계가 중요) ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/))

---

## 🔧 핵심 개념
### 1) Supervisor/Worker 패턴 정의 (2026년 실무 의미)
- **Supervisor**: (a) 작업을 분해하고 (b) 다음에 호출할 Worker를 선택하며 (c) 결과를 검증/재시도/합성하는 **control plane**
- **Worker**: 좁은 책임을 갖고, 제한된 컨텍스트/툴로 서브태스크를 실행하는 **data plane**

2026년 글/가이드들이 공통으로 강조하는 포인트는 “Supervisor가 똑똑해야 한다”가 아니라, **Supervisor의 런타임 책임이 커질수록 비용과 실패 모드가 Supervisor에 집중된다**는 점입니다. 특히 Supervisor의 컨텍스트가 누적되면 토큰 비용이 Worker보다 Supervisor에서 터지기 쉽다는 지적이 반복됩니다. ([paiteq.com](https://www.paiteq.com/blog/multi-agent-orchestration-patterns/?utm_source=openai))

### 2) 내부 작동 흐름(구조/흐름)
프로덕션에서 Supervisor/Worker는 보통 아래 상태 머신으로 굴립니다.

1. **Intake / Normalize**
   - 입력을 정규화(요구사항, 제약, 산출물 포맷)
   - “이번 요청이 multi-agent가 필요한지”부터 판정(필요 없으면 single-agent fast path) ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))

2. **Plan / Route**
   - 현재 상태(state)로부터 “다음 Worker 타입”을 선택
   - 여기서 핵심은 “LLM이 자유롭게 라우팅”하게 두는 게 아니라,
     - **구조화된 출력(예: JSON)**으로 라우팅 결정을 만들고
     - 코드가 이를 검증해 **결정성을 끌어올리는 것**입니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/))

3. **Execute (Worker call)**
   - Worker는 제한된 입력만 받아 수행 (컨텍스트 축소)
   - 실패 시 예외를 던지기보다 **구조화된 error state**로 반환 → Supervisor가 복구 전략을 선택(재시도/다른 Worker/중단)

4. **Evaluate / Synthesize**
   - 결과가 합격 기준을 만족하면 종료
   - 아니면 “추가 Worker 호출” 또는 “리뷰/검증 Worker” 호출로 루프

5. **Loop guard / Termination**
   - 2026년에도 가장 흔한 장애는 **무한 루프**와 **state 비대화**입니다. 실무 글에서는 iteration counter와 max iteration을 state에 넣어 강제 종료하라고 강하게 권합니다. ([lifetideshub.com](https://www.lifetideshub.com/langgraph-supervisor-pattern-examples-2026/?utm_source=openai))

### 3) 다른 접근과의 차이점: Handoffs / Swarm / Pipeline
- **Supervisor(Agents-as-tools)**: manager가 대화 주도권을 유지하고 specialist를 “툴처럼 호출”합니다. 최종 답/가드레일을 중앙에서 통제하기 좋습니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/))
- **Handoffs**: triage가 “누가 다음 턴의 주체인지”를 넘깁니다. 라우팅 자체가 워크플로우의 핵심일 때 유리합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/))
- **Swarm**: 에이전트들이 서로 handoff하며, 메시지 컨텍스트를 공유하는 구조가 일반적입니다. 중앙 오케스트레이터 없이 로컬 의사결정으로 흘러가지만, 병렬 tool call 등에서 예기치 못한 동작이 생길 수 있어 설정(예: parallel tool calls 제어)이 중요하다는 문서가 있습니다. ([microsoft.github.io](https://microsoft.github.io/autogen/0.7.3/user-guide/agentchat-user-guide/swarm.html))
- **Pipeline**: 순서가 고정된 조립 라인. 변동성이 적으면 가장 운영하기 쉽고 평가하기도 쉽습니다(하지만 예외 케이스 처리에 약함).

---

## 💻 실전 코드
아래 예제는 “사내 문서/PRD를 받아 **실제 운영 가능한 기술 설계 초안 + 구현 태스크 분해 + 리스크 체크**”를 만드는 시나리오입니다. 핵심은 **Supervisor가 라우팅/루프 종료/에러 복구**를 책임지고, Worker는 좁은 책임만 수행한다는 점입니다.

- Supervisor: `ArchitectSupervisor`
- Worker 1: `RetrieverWorker` (RAG/문서 검색)
- Worker 2: `DesignerWorker` (아키텍처 설계 초안)
- Worker 3: `RiskReviewerWorker` (보안/운영/비용 리스크 검토)
- Worker 4: `TaskPlannerWorker` (Jira 수준 구현 태스크 분해)

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install "openai-agents>=0.14.0" pydantic python-dotenv
export OPENAI_API_KEY="..."
```

### 1) Supervisor/Worker 오케스트레이션 (OpenAI Agents SDK: agents as tools 스타일)
OpenAI Agents SDK 문서에서 “Agents as tools(매니저가 컨트롤 유지)”와 “Handoffs(라우팅 후 주체 교체)”를 명확히 구분합니다. 여기서는 Supervisor 패턴에 맞게 **Agents as tools**로 갑니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/))

```python
# file: supervisor_worker_blueprint.py
import asyncio
from typing import Literal, Optional, List
from pydantic import BaseModel, Field

from agents import Agent, Runner

# ---- 1) Shared state (loop guard 포함) ----
class BlueprintState(BaseModel):
    prd: str
    iteration: int = 0
    max_iterations: int = 8

    # artifacts
    retrieved_notes: Optional[str] = None
    architecture: Optional[str] = None
    risks: Optional[str] = None
    tasks: Optional[str] = None

    # control
    last_error: Optional[str] = None
    done: bool = False


# ---- 2) Structured routing decision ----
class RouteDecision(BaseModel):
    next: Literal["retrieve", "design", "review_risks", "plan_tasks", "finish"]
    rationale: str = Field(..., description="Why this step is next")
    # Supervisor가 Worker에게 전달할 최소 컨텍스트만 명시
    worker_input: str


# ---- 3) Workers ----
RetrieverWorker = Agent(
    name="RetrieverWorker",
    instructions=(
        "You retrieve relevant implementation constraints and prior art from the given PRD.\n"
        "Return concise notes with headings: Assumptions, Constraints, Non-goals, Open Questions."
    ),
)

DesignerWorker = Agent(
    name="DesignerWorker",
    instructions=(
        "You are a staff engineer. Propose an architecture blueprint.\n"
        "Output sections: Overview, Components, Data Flow, APIs, Storage, Observability."
    ),
)

RiskReviewerWorker = Agent(
    name="RiskReviewerWorker",
    instructions=(
        "You are a security+reliability reviewer.\n"
        "Identify risks and mitigations: Security, Privacy, Reliability, Cost, Vendor Lock-in."
    ),
)

TaskPlannerWorker = Agent(
    name="TaskPlannerWorker",
    instructions=(
        "You are a tech lead. Break the solution into implementation tasks.\n"
        "Output a numbered backlog with estimates (S/M/L) and acceptance criteria."
    ),
)


# ---- 4) Supervisor ----
ArchitectSupervisor = Agent(
    name="ArchitectSupervisor",
    instructions=(
        "You orchestrate workers to produce a production-ready blueprint.\n"
        "Rules:\n"
        "- You MUST output a JSON matching the RouteDecision schema.\n"
        "- Minimize context passed to workers (only what they need).\n"
        "- If iteration >= max_iterations, choose finish.\n"
        "- Finish only when architecture + risks + tasks are all present and coherent.\n"
    ),
    output_type=RouteDecision,  # SDK가 structured output을 지원하는 형태로 가정
)


async def call_worker(worker: Agent, text: str) -> str:
    # Worker 호출은 try/except로 감싸고, 예외는 상위에서 state로 흡수하는 형태가 운영에 유리
    result = await Runner.run(worker, text)
    return result.final_output


async def run_blueprint(prd: str) -> BlueprintState:
    state = BlueprintState(prd=prd)

    while not state.done:
        state.iteration += 1

        if state.iteration > state.max_iterations:
            state.done = True
            break

        # Supervisor에게는 "현재까지의 산출물 요약"만 준다.
        supervisor_input = f"""
PRD:
{state.prd}

Current artifacts:
- retrieved_notes: {bool(state.retrieved_notes)}
- architecture: {bool(state.architecture)}
- risks: {bool(state.risks)}
- tasks: {bool(state.tasks)}
last_error: {state.last_error}
iteration: {state.iteration}/{state.max_iterations}

Decide the next step.
""".strip()

        decision = (await Runner.run(ArchitectSupervisor, supervisor_input)).final_output

        try:
            if decision.next == "retrieve":
                state.retrieved_notes = await call_worker(RetrieverWorker, decision.worker_input)
            elif decision.next == "design":
                state.architecture = await call_worker(DesignerWorker, decision.worker_input)
            elif decision.next == "review_risks":
                state.risks = await call_worker(RiskReviewerWorker, decision.worker_input)
            elif decision.next == "plan_tasks":
                state.tasks = await call_worker(TaskPlannerWorker, decision.worker_input)
            elif decision.next == "finish":
                state.done = True
            state.last_error = None
        except Exception as e:
            # 예외를 죽이지 말고 state로 흡수 → 다음 루프에서 복구 라우팅 가능
            state.last_error = f"{type(e).__name__}: {e}"

        # 종료 조건(코드로도 보강): 핵심 아티팩트가 다 있으면 finish 유도
        if state.architecture and state.risks and state.tasks:
            state.done = True

    return state


async def main():
    prd = """
We need an internal service that summarizes support tickets daily,
clusters by root cause, and opens Jira issues for high-impact clusters.
Data source: Zendesk export + internal incident DB.
Constraints: must run in VPC, no PII leakage, cost < $200/month.
""".strip()

    state = await run_blueprint(prd)

    print("\n=== ARCHITECTURE ===\n", state.architecture)
    print("\n=== RISKS ===\n", state.risks)
    print("\n=== TASKS ===\n", state.tasks)

if __name__ == "__main__":
    asyncio.run(main())
```

### 예상 출력(요약)
- ARCHITECTURE: “ingestion job → embedding/RAG store → clustering job → LLM summarizer → Jira integration” 같은 **컴포넌트/데이터 플로우가 명시된 설계 초안**
- RISKS: PII redaction, VPC egress 통제, 비용 상한(토큰/런 수), 평가/관측(로그/trace) 등
- TASKS: “데이터 파이프라인”, “클러스터링”, “Jira 생성”, “평가셋 구축”까지 포함한 백로그

이 예제의 포인트는:
- Supervisor는 **라우팅 결정만 JSON으로 내리고**, 실제 제어(루프/종료/에러처리)는 코드가 잡습니다. (SDK 문서에서도 코드 기반 오케스트레이션이 더 결정적/예측 가능하다고 명시) ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/))
- 루프 가드는 필수입니다(무한 루프/상태 비대화는 2026년에도 대표 장애). ([lifetideshub.com](https://www.lifetideshub.com/langgraph-supervisor-pattern-examples-2026/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Supervisor 컨텍스트는 “요약 상태”만**
- Supervisor가 모든 Worker 결과 원문을 계속 들고 있으면, 토큰 비용과 지연이 Supervisor에서 폭발합니다(실무 가이드에서 반복되는 경고).  
- 패턴: `raw_output`는 스토리지에 저장하고, Supervisor에는 `artifact_present + short summary + pointers(id/url)`만 전달. ([paiteq.com](https://www.paiteq.com/blog/multi-agent-orchestration-patterns/?utm_source=openai))

2) **Structured routing + code validation**
- “다음은 A 해”를 자연어로 받지 말고, `next_step`을 enum으로 제한하세요.
- 오케스트레이션의 핵심은 LLM의 창의성이 아니라 **운영 가능성**입니다. (문서도 LLM 오케스트레이션과 코드 오케스트레이션을 구분해 설명) ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/))

3) **실패를 예외가 아니라 상태로 다루기**
- Worker에서 타임아웃/툴 실패가 나면, Supervisor가 “재시도/대체 Worker/중단”을 선택할 수 있게 **에러를 구조화**하세요.
- “에러가 나면 전체 run fail”은 multi-agent에서 MTTR을 악화시킵니다.

### 흔한 함정/안티패턴
- **Supervisor가 모든 일을 다 한다**: Worker가 이름만 Worker고 실질적으로 Supervisor가 긴 프롬프트로 다 처리하면, 비용/평가/재사용성이 최악이 됩니다.
- **무한 루프**: 종료 조건이 “LLM이 알아서 finish”면 새벽 2시에 터집니다. iteration cap은 기본, 가능하면 “finish 조건”을 코드로도 강제하세요. ([lifetideshub.com](https://www.lifetideshub.com/langgraph-supervisor-pattern-examples-2026/?utm_source=openai))
- **Swarm/Peer handoff를 ‘자유’로 착각**: peer-to-peer는 강력하지만, tool calling 병렬성/컨텍스트 공유로 인해 예기치 않은 동작이 생길 수 있고 설정이 중요합니다. ([microsoft.github.io](https://microsoft.github.io/autogen/0.7.3/user-guide/agentchat-user-guide/swarm.html))

### 비용/성능/안정성 트레이드오프
- **안정성↑**: Supervisor를 더 “규칙 기반(코드)”으로 만들수록 재현성과 평가가 좋아집니다.
- **비용↓**: Worker에 전달하는 컨텍스트를 최소화하고, Supervisor state를 요약하면 단가가 내려갑니다.
- **성능(품질)↑/비용↑**: 리뷰/검증 Worker(critic)를 붙이면 품질은 오르지만, 2~3회 루프가 기본이 되며 비용이 곱으로 늘어날 수 있습니다. (특히 debate류는 비용 배수가 커질 수 있다는 실무 글도 존재) ([digitalapplied.com](https://www.digitalapplied.com/blog/multi-agent-orchestration-5-patterns-that-work?utm_source=openai))
- 추가로 2026년 연구는 “모델 선택보다 topology 선택이 성능에 더 큰 영향”을 주장하며, 작업 DAG에 따라 병렬/순차/계층을 동적으로 고르는 프레임까지 제안합니다. 즉, Supervisor/Worker도 “항상 고정 패턴”이 아니라 **작업 형태에 따라 변형**하는 쪽으로 진화 중입니다. ([arxiv.org](https://arxiv.org/abs/2602.16873))

---

## 🚀 마무리
Supervisor/Worker 패턴을 2026년에 “프로덕션 답”으로 쓰려면 핵심은 하나입니다: **Supervisor를 똑똑하게 만들기보다, Supervisor를 운영 가능하게 만들기**.

- 도입 판단 기준
  - (도입) 작업이 분해 가능하고, 결과 검증/합성이 중요하며, 실패 격리가 필요하다 → Supervisor/Worker 적합
  - (보류) 절차적/결정적 작업이거나 사실상 단일 에이전트+툴 호출이면 → single-agent + 코드 오케스트레이션부터 ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))
  - (주의) peer handoff/swarm는 강력하지만 운영 난이도가 올라갈 수 있음 → 팀의 관측/평가/디버깅 역량이 준비됐는지 먼저 점검 ([microsoft.github.io](https://microsoft.github.io/autogen/0.7.3/user-guide/agentchat-user-guide/swarm.html))

- 다음 학습 추천(순서)
  1) OpenAI Agents SDK의 “agents as tools vs handoffs” 구분과 예제 패턴 ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/))
  2) 루프/종료/에러를 “상태 머신”으로 모델링하는 방식(무한 루프/상태 비대화 방지) ([lifetideshub.com](https://www.lifetideshub.com/langgraph-supervisor-pattern-examples-2026/?utm_source=openai))
  3) 작업 DAG 기반으로 topology를 선택/혼합하는 관점(고정 패턴에서 적응형 오케스트레이션으로) ([arxiv.org](https://arxiv.org/abs/2602.16873))

원하면, 위 예제를 **(1) LangGraph로 동일 기능 구현**, 또는 **(2) Handoffs로 “티켓 분류 → 담당 전문 에이전트가 사용자 응답까지 소유”**하는 형태로 변형한 버전도 같이 만들어드릴게요.