---
title: "Supervisor가 팀장이고 Worker가 실무자라면, 2026년형 Multi‑Agent Orchestration은 “대화형 LLM을 분산 시스템처럼 운영”하는 문제를 다룹니다"
date: 2026-07-29 03:20:52 +0900
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
2026년 7월 기준 multi-agent orchestration에서 **supervisor/worker 패턴**이 다시 주목받는 이유는 명확합니다. 단일 agent + tools로는 다음이 잘 안 풀립니다.

- **작업이 길고(10~100 step)** 중간에 실패/재시도가 필요함
- 도메인이 여러 개라 **프롬프트/툴 스키마가 비대해져** 모델이 “툴 선택을 망치는” 상황
- 품질을 끌어올리려면 **전문화(compiler, DB, security, writer 등)** 가 필요함
- 비용/지연을 통제하려면 **어떤 step을 어떤 모델로** 돌릴지 강제해야 함

Supervisor/worker는 “한 명이 다 한다”에서 “**오케스트레이션(결정)과 실행(행동)을 분리**”로 바꾸는 구조입니다. LangGraph는 이를 state graph로 명시해 디버깅 가능하게 만들었고(슈퍼바이저 노드가 worker 서브그래프를 라우팅) ([learn.engineering.vips.edu](https://learn.engineering.vips.edu/agent-protocols/langgraph-supervisor-pattern?utm_source=openai)), OpenAI Agents SDK는 manager(agents-as-tools) vs handoffs(위임)라는 두 축으로 오케스트레이션 선택지를 정리했습니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

**언제 쓰면 좋나**
- 워크플로가 “대충 LLM에게 맡기면 되지”가 아니라, **SLA/비용/감사(audit)** 가 있는 서비스(사내 운영 자동화, 티켓 처리, 문서 추출/검증 등)
- 기능별로 **서로 다른 툴/데이터 접근권한** 을 분리해야 하는 경우
- 실패가 잦아 **checkpoint + 재실행** 이 필요한 장기 작업(배치, 리포트 생성, 코드 수정 루프)

**언제 쓰면 안 되나**
- 1~3 step으로 끝나는 단순 Q&A/요약: orchestration 오버헤드가 더 큼
- “정답이 하나”인 deterministic 파이프라인: 그냥 코드로 파이프라인 짜는 게 더 싸고 안정적
- 팀이 observability/평가(Evals)/실패 처리에 투자할 여력이 없다면: multi-agent는 **복잡도를 ‘숨기는’ 게 아니라 ‘이동’** 시킵니다

---

## 🔧 핵심 개념
### 1) Supervisor/Worker 패턴 정의
- **Supervisor(Orchestrator/Manager)**: 현재 상태(state)와 목표를 보고 “다음에 누굴 실행할지” 결정
- **Worker(Specialist)**: 좁은 범위의 책임을 가진 실행 유닛(툴 호출/분석/검증/작성 등)

LangGraph 스타일에서는 supervisor가 **라우터 노드**로 존재하고, worker는 **각각 독립 프롬프트+툴을 가진 노드/서브그래프**로 구성됩니다. 이 구조의 장점은 control flow가 코드/그래프로 고정되어 **재현/리플레이/체크포인팅**이 가능하다는 점입니다. ([learn.engineering.vips.edu](https://learn.engineering.vips.edu/agent-protocols/langgraph-supervisor-pattern?utm_source=openai))

### 2) 내부 작동 방식(흐름)
실무에서 “작동한다” 수준을 넘어서려면, 메시지/상태/결정이 어떻게 흐르는지 명확해야 합니다.

1. **Shared State 준비**
   - 예: `goal`, `artifacts`, `open_items`, `cost_budget`, `audit_log` …
2. **Supervisor step**
   - state를 읽고, 다음 액션을 선택:
     - `dispatch(worker_name, payload)`
     - `request_human_review(...)`
     - `finish(answer, artifacts)`
3. **Worker step**
   - 자신의 전용 컨텍스트(필요 최소 state + 전용 tool schema)만 받아 실행
   - 결과를 `artifacts`에 쓰고, `audit_log`에 근거/출처/툴 호출 기록
4. **Return-to-supervisor**
   - 결과 요약(필수) + 상세 로그(옵션)를 supervisor에게 전달
   - supervisor는 “수용/재시도/다른 worker로 교차검증/종료”를 결정

여기서 2026년 관점의 핵심은 “multi-agent = 메시지 많이 주고받기”가 아니라,
- **Supervisor 컨텍스트는 얇게(오케스트레이션 전용)**
- **Worker 컨텍스트는 두껍게(작업 전용)**
로 나눠서 **컨텍스트 윈도우와 툴 스키마 폭발을 막는 것**입니다. (LangChain의 async-deep-agents도 비슷한 취지로 supervisor와 subagent의 컨텍스트를 분리하는 접근을 설명합니다.) ([github.com](https://github.com/langchain-ai/async-deep-agents?utm_source=openai))

### 3) 다른 접근과의 차이점(선택 기준)
OpenAI Agents SDK 문서 기준으로 보면 크게 두 가지가 자주 쓰입니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

- **Agents as tools (Manager pattern)**  
  Supervisor가 계속 유저-facing “소유권”을 갖고, worker를 tool처럼 호출.  
  - 장점: 단일 톤/가드레일/출력 포맷 유지, 최종 합성 책임이 명확
  - 단점: supervisor가 결과를 계속 읽고 합치면 token이 누적되기 쉬움

- **Handoffs (Decentralized)**  
  triage가 라우팅하면, 그 worker가 해당 턴의 주도권을 가져감. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))  
  - 장점: 각 agent 프롬프트를 극도로 좁게 유지 가능, 장황한 “중간 보고”가 줄어듦
  - 단점: “최종 합성”을 어디서 책임질지 애매해지면 품질 편차/UX 흔들림

Supervisor/worker를 production에 넣을 때는 대체로 **Manager(중앙집권)로 시작**하고, 특정 영역에서만 handoff를 허용하는 식이 운영이 쉽습니다.

---

## 💻 실전 코드
아래는 **현실적인 시나리오**: “사내 incident 티켓(자연어) → 원인 분류 + 영향 범위 확인 + 조치 runbook 추천 + 최종 요약”을 supervisor/worker로 구성합니다.

- Supervisor: 라우팅 + 최종 요약/포맷 통제
- Workers:
  - `log_analyst`: 로그/에러 패턴 요약(여기서는 샘플 로그 파일을 읽는 tool)
  - `kb_retriever`: runbook/운영 지침 검색(여기서는 로컬 KB를 grep)
  - `risk_checker`: 조치의 위험도/권한 검토(정책 룰 기반)
- 기술 스택: **OpenAI Agents SDK (Python)** 의 “agents as tools” 스타일(= supervisor가 worker를 tool로 호출) ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install openai-agents pydantic
export OPENAI_API_KEY="..."
```

샘플 데이터:
```bash
mkdir -p data
cat > data/app.log << 'EOF'
2026-07-28T10:12:01Z ERROR payment-service: timeout calling redis cluster=cache-prod-2
2026-07-28T10:12:02Z WARN  payment-service: retry=1 backoff=200ms
2026-07-28T10:12:06Z ERROR payment-service: circuit_open redis cluster=cache-prod-2
EOF

cat > data/runbooks.md << 'EOF'
# Runbooks

## Redis timeout / circuit breaker
- Check redis latency and node health
- If cluster degraded, failover or scale
- Mitigation: temporarily increase timeout ONLY if error budget allows
- Rollback: revert config, restart pods gradually

## Payment service incident checklist
- Confirm blast radius (regions/tenants)
- Stop the bleeding (rate limit, circuit breaker policy)
- Communicate status to oncall channel
EOF
```

### 1) 실행 코드(단일 파일)
```python
# file: incident_supervisor.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Dict, Any

from agents import Agent, Runner, function_tool

# ---- Tools (현실: 여기서 Datadog, ELK, Confluence, Jira, PagerDuty 등으로 바뀜) ----

@function_tool
def read_app_log(path: str = "data/app.log") -> str:
    """Read recent application logs."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@function_tool
def search_runbooks(query: str, path: str = "data/runbooks.md") -> str:
    """Very small local 'KB search' for demo. Returns matching sections."""
    text = open(path, "r", encoding="utf-8").read()
    # naive section extraction: split by headers
    sections = re.split(r"\n(?=# )", text)
    hits = []
    q = query.lower()
    for s in sections:
        if q in s.lower():
            hits.append(s.strip())
    return "\n\n---\n\n".join(hits) if hits else "NO_HITS"

@function_tool
def policy_check(action: str) -> Dict[str, Any]:
    """Toy policy engine but realistic intent: gate risky actions."""
    risky = any(k in action.lower() for k in ["delete", "drop", "wipe", "disable auth", "prod write"])
    needs_approval = risky or ("increase timeout" in action.lower())
    return {
        "risky": risky,
        "needs_approval": needs_approval,
        "allowed": not risky,  # keep it strict
        "notes": "Timeout changes require SRE approval during incidents." if needs_approval else "OK"
    }

# ---- Workers ----

log_analyst = Agent(
    name="log_analyst",
    instructions=(
        "You are a production incident log analyst.\n"
        "Goal: extract probable cause, affected component, and 2-3 concrete checks.\n"
        "Use read_app_log. Be terse and structured."
    ),
    tools=[read_app_log],
)

kb_retriever = Agent(
    name="kb_retriever",
    instructions=(
        "You are an SRE runbook retriever.\n"
        "Given an incident hypothesis, search relevant runbooks.\n"
        "Use search_runbooks. Return actionable steps and rollback notes."
    ),
    tools=[search_runbooks],
)

risk_checker = Agent(
    name="risk_checker",
    instructions=(
        "You are a change-risk reviewer.\n"
        "Given proposed mitigation steps, call policy_check for each risky step.\n"
        "Output which steps need approval and safe alternatives."
    ),
    tools=[policy_check],
)

# ---- Supervisor (Manager) ----
# 핵심: worker들을 tool처럼 붙여서, supervisor가 "언제/어떤 순서로" 호출할지 결정

supervisor = Agent(
    name="incident_supervisor",
    instructions=(
        "You are the incident commander. You must:\n"
        "1) ask log_analyst to analyze logs\n"
        "2) ask kb_retriever to fetch runbooks based on that analysis\n"
        "3) propose mitigation steps and validate them with risk_checker\n"
        "4) produce FINAL output in Korean with sections:\n"
        "   - 요약\n   - 관측된 증상\n   - 추정 원인\n   - 즉시 조치(승인 필요 여부 표시)\n   - 추가 확인\n   - 롤백\n"
        "Keep tokens low: do not paste full logs/runbooks; summarize."
    ),
    tools=[
        log_analyst.as_tool(tool_name="call_log_analyst"),
        kb_retriever.as_tool(tool_name="call_kb_retriever"),
        risk_checker.as_tool(tool_name="call_risk_checker"),
    ],
)

def main():
    incident_ticket = (
        "결제 API 지연이 급증했고 일부 요청이 실패합니다. "
        "최근 배포는 없었고 캐시(redis) 쪽이 의심됩니다. "
        "지금 당장 뭘 확인하고 어떤 조치를 해야 하나요?"
    )
    result = Runner.run_sync(supervisor, incident_ticket)
    print(result.final_output)

if __name__ == "__main__":
    main()
```

### 2) 예상 출력(요약)
- 로그에서 `redis timeout`, `circuit_open`을 근거로 원인 가설 제시
- runbook에서 체크리스트/완화/롤백 추출
- timeout 상향 같은 조치에 “approval 필요” 플래그

이 예제의 포인트는 “toy 계산”이 아니라, 실제 운영에서 중요한 **(1) 얇은 supervisor, (2) 전용 worker, (3) 정책 게이트**를 최소 코드로 구현한 겁니다. Agents SDK는 이런 오케스트레이션 패턴(agents as tools vs handoffs)을 공식 문서로 정리해두고 있습니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **Worker 계약(Contract)을 ‘입력/출력 스키마’로 고정**
- “좋은 글 써줘”가 아니라 `hypothesis`, `checks`, `mitigations[]` 같은 구조로.
- OpenAI 쪽 가이드도 “컴포넌트를 composable하게” 만들고 프롬프트를 역할 중심으로 좁히라고 강조합니다. ([openai.com](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/?utm_source=openai))

2) **State를 두 층으로 나눠라: flow state vs agent state**
- flow state: 진행단계, 예산, 승인여부, artifacts
- agent state: 각 worker의 내부 chain-of-thought에 해당하는 중간 텍스트는 가급적 저장하지 말고 **요약만** 남기기
- 그래프 기반 접근(LangGraph)은 typed state/체크포인트/리플레이를 강조하는 흐름이 강합니다. ([arxiv.org](https://arxiv.org/abs/2607.19297?utm_source=openai))

3) **Supervisor는 “라우팅 + 합성 + 종료조건”만**
- supervisor가 도메인 세부를 알기 시작하면 컨텍스트가 다시 비대해집니다.
- LangGraph 쪽에서도 tool 기반 supervisor 패턴이 context engineering 제어에 유리하다고 언급합니다. ([reference.langchain.com](https://reference.langchain.com/python/langgraph-supervisor?utm_source=openai))

### 흔한 함정/안티패턴
- **무한 핑퐁 루프**: worker A가 “B에게 물어봐” → B가 “A가 해야” → 비용 폭발  
  → 해결: max steps, loop detector(동일 intent 반복), circuit breaker.
- **모든 worker 출력 원문을 supervisor가 다 읽음**: 결국 단일 agent보다 더 비싸고 느립니다.  
  → 해결: worker는 “근거 링크/핵심 bullet”만 반환, 원문은 artifact store에 저장하고 필요할 때만 fetch.
- **툴 스키마가 supervisor에 다 몰림**: supervisor가 50개 툴을 보게 되면 routing 정확도가 떨어집니다.  
  → 해결: tool은 worker에 캡슐화하고, supervisor는 “worker 호출 툴”만 가진다(위 코드 구조).

### 비용/성능/안정성 트레이드오프
- 비용: 대체로 **2~3배 토큰/호출**이 되는 순간이 많습니다(재시도/중복 요약/핑퐁). 커뮤니티에서도 이 패턴이 반복적으로 언급됩니다. ([reddit.com](https://www.reddit.com/r/LangChain/comments/1sxmbgk/anyone_running_multiagent_setups_in_prod_curious/?utm_source=openai))  
- 성능(지연): 병렬 fan-out(여러 worker 동시 실행)는 빨라지지만, merge/합성에서 다시 병목이 생김
- 안정성: supervisor가 모든 것을 결정하게 하면 “한 모델의 판단 실패”가 전체 실패로 이어짐  
  → 그래서 실무에서는 **결정의 일부를 code로 고정(규칙 라우팅)** 하고, LLM은 애매한 구간에만 쓰는 하이브리드가 많습니다(Agents SDK도 code-orchestrated와 LLM-orchestrated를 혼합 가능하다고 설명). ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

---

## 🚀 마무리
Supervisor/worker 패턴은 “에이전트를 여러 개 붙이면 똑똑해진다”가 아니라, **복잡한 작업을 운영 가능한 형태로 분해**하는 아키텍처입니다.

도입 판단 기준(실무 체크리스트):
- (필수) 실패/재시도/감사 로그가 필요한가?
- (필수) 역할 분리로 **툴/권한/프롬프트를 캡슐화**해야 하는가?
- (권장) state/trace/checkpoint가 없으면 운영이 불가능한가? (장기 작업, 배치성)
- (경고) Evals/관측성에 투자할 수 없으면 multi-agent는 “문제 증폭기”가 될 수 있음

다음 학습 추천:
- OpenAI Agents SDK의 orchestration(agents as tools vs handoffs) 문서로 패턴 선택 기준을 먼저 정리하고 ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))
- LangGraph supervisor 패턴을 state graph로 구현해 **checkpoint/리플레이/디버깅**까지 포함한 운영 모델을 잡는 순서를 추천합니다. ([learn.engineering.vips.edu](https://learn.engineering.vips.edu/agent-protocols/langgraph-supervisor-pattern?utm_source=openai))