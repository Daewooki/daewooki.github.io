---
title: "2026년 6월 기준, “Agent tool use + Function Calling”을 프로덕션에 넣는 법: Agents SDK/Responses API 패턴 심층 분석"
date: 2026-06-14 04:54:15 +0900
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
LLM을 제품에 붙이다 보면 빠르게 “텍스트 생성”을 넘어 “행동”이 필요해집니다. 예를 들어 **내부 DB 조회**, **권한이 필요한 사내 API 호출**, **배치 실행**, **파일 편집/패치**, **웹 리서치**, **워크스페이스에서 코드 실행** 같은 것들입니다. 이때 가장 큰 문제는 두 가지입니다.

1) **모델이 언제 어떤 도구를 써야 하는지**를 안정적으로 결정하게 만들기  
2) **도구 호출 결과를 다시 컨텍스트로 안전하게 합쳐** 다음 스텝을 진행하기

2026년의 실무 해법은 대체로 “tool use loop(think → call tool → observe → repeat)”를 **Function Calling(= JSON Schema 기반 도구 호출)**로 표준화하고, 그 루프를 돌리는 **harness(런타임)** 를 갖추는 쪽으로 수렴했습니다. OpenAI는 이를 Agents SDK/Responses API 중심으로 “모델이 자연스럽게 일하는 패턴”에 맞춘 런타임을 제공하는 방향을 강조합니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk))

### 언제 쓰면 좋나
- **불확실한 입력 + 복수의 시스템 연동**(CRM/결제/재고/티켓 등)에서 “조건 분기 + 실행”이 필요한 경우
- 사람 대신 “툴을 쓰는” 작업(리서치, triage, 운영 자동화, 코드 수정/테스트)을 만들고 싶은 경우
- 관찰 가능성(tracing), 승인(approval), 중단/재개(pause/resume) 같은 **운영 기능**이 중요한 경우 ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))

### 언제 쓰면 안 되나
- 순수 생성(카피라이팅/요약)처럼 **툴 호출이 필요 없는 문제**
- “항상 같은 순서로 같은 API를 호출”하는 **결정적 워크플로우**(이건 일반 백엔드 오케스트레이션이 더 단순/저렴)
- 도구 호출이 곧 **리스크(금융/삭제/권한 상승)** 인데 승인/가드레일/감사 로그 없이 “모델에게 맡기려는” 경우

---

## 🔧 핵심 개념
### 1) Tool use와 Function Calling의 역할 분리
- **Tool use**: “모델이 행동을 선택하고 결과를 이용해 다음 행동/응답을 만든다”는 루프 전체
- **Function Calling**: 그 행동을 **정형화된 wire format(JSON Schema)** 로 표현해, 런타임이 실제 함수를 실행하도록 만드는 인터페이스

즉, Function Calling은 *프로토콜/표현*이고, Tool use는 *오케스트레이션 패턴*입니다. 2026년 프레임워크들은 대부분 여기로 수렴했습니다. ([taskade.com](https://www.taskade.com/wiki/ai/tool-use?utm_source=openai))

### 2) “Agent harness”가 하는 일 (왜 SDK가 필요한가)
OpenAI가 2026년 4월 발표에서 강조한 포인트는 “개발자 glue code를 줄이고, 장기 실행/다도구/파일/샌드박스 작업을 모델의 자연스러운 패턴에 맞춰” 돌리는 **표준 런타임(harness)** 입니다. 여기에는 memory, sandbox-aware orchestration, 파일 도구, MCP, shell/apply_patch 같은 프리미티브가 포함됩니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk))

실무적으로 harness는 다음을 책임집니다.
- 도구 스키마 등록/노출(최소권한, progressive disclosure)
- 도구 호출 요청 파싱/검증/실행
- 에러 전달(재시도 가능 형태로)
- 승인 게이트/중단-재개
- 트레이싱(어느 턴에서 어떤 툴을 왜 썼는지)

### 3) 오케스트레이션: LLM이 할 일 vs 코드가 할 일
OpenAI Agents SDK 문서가 명확히 나누는 기준이 있습니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))

- **Orchestrating via LLM(자율)**  
  장점: 유연, 복잡한 문제에 강함  
  단점: 비용/지연/비결정성 증가, 디버깅 난이도  
- **Orchestrating via code(결정적)**  
  장점: 속도/비용/예측 가능성  
  단점: 분기 폭발, 새로운 예외에 취약

프로덕션에서 자주 쓰는 절충안은:
- “라우팅/승인/재시도/타임아웃” 같은 **제어-plane은 코드**
- “파라미터 구성/요약/해석” 같은 **데이터-plane은 LLM**

### 4) Multi-agent에서 “Agents as tools” vs “Handoffs”
Agents SDK는 대표 패턴을 두 개로 정리합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))
- **Agents as tools(매니저-워커)**: 매니저가 대화 소유권을 유지하고, 전문 에이전트를 `asTool()`로 호출
- **Handoffs(트리아주-전문가)**: 트리아주가 라우팅 후 전문 에이전트가 대화 소유권을 가져감

Function Calling 관점에서 중요한 차이는:
- *as tools*는 “전문가를 **함수처럼** 부르는 것”이라 반환값을 구조화하기 쉽고, 가드레일을 한 곳에 집중하기 좋습니다.
- *handoff*는 “대화 자체를 넘긴다”는 의미라 UX는 좋아지지만, 매니저가 강제하는 정책/형식을 유지하려면 설계를 더 해야 합니다.

---

## 💻 실전 코드
아래 예제는 “사내 Incident(장애/이슈) 자동 triage + 완화(runbook 실행) + 티켓 업데이트”를 가정합니다. **toy**가 아니라, 실제로 운영에 넣을 때 필요한 요소(승인, idempotency, 에러/재시도, 툴 결과 요약)를 포함합니다.

- 런타임: Python
- 핵심: `function_tool`로 도구 스키마 노출 + 에이전트가 필요 시 호출
- 시나리오: “결제 실패율 급증” 알림이 오면 최근 지표 조회 → 원인 후보 분석 → 완화 조치(토글/레이트리밋) 제안 → **승인 후** 실행 → 티켓 코멘트

> 참고: OpenAI Agents SDK의 tool 분류/승인 게이트/Runner 패턴은 공식 문서에 기반합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))

```bash
# 의존성(예시)
pip install openai-agents pydantic httpx
export OPENAI_API_KEY="..."
```

```python
import os
import time
import httpx
from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

from openai_agents import Agent, Runner
from openai_agents.tools import function_tool

# ---- (1) 현실적인 외부 시스템 어댑터들 ----

INCIDENT_API = os.environ.get("INCIDENT_API", "https://incident.example.internal")
METRICS_API = os.environ.get("METRICS_API", "https://metrics.example.internal")
CHANGE_API = os.environ.get("CHANGE_API", "https://change.example.internal")

class MetricPoint(BaseModel):
    ts: int
    value: float

class FailureRateResponse(BaseModel):
    service: str
    window_minutes: int
    points: list[MetricPoint]

class MitigationPlan(BaseModel):
    action: Literal["enable_fallback", "rate_limit", "rollback", "no_change"]
    reason: str
    params: Dict[str, Any] = Field(default_factory=dict)
    risk: Literal["low", "medium", "high"]

# ---- (2) Function tools: JSON Schema로 노출되는 “행동” ----

@function_tool
async def get_payment_failure_rate(service: str, window_minutes: int = 30) -> dict:
    """Fetch payment failure rate time series for the given service and window."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(
            f"{METRICS_API}/v1/failure_rate",
            params={"service": service, "window": window_minutes},
        )
        r.raise_for_status()
        data = r.json()
    # 스키마 안정성을 위해 Pydantic으로 검증 후 dict 반환
    parsed = FailureRateResponse.model_validate(data)
    return parsed.model_dump()

@function_tool
async def post_ticket_comment(ticket_id: str, comment: str) -> dict:
    """Post a comment to an incident ticket."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(
            f"{INCIDENT_API}/v1/tickets/{ticket_id}/comments",
            json={"comment": comment},
        )
        r.raise_for_status()
        return r.json()

@function_tool(needs_approval=True)
async def apply_mitigation(ticket_id: str, plan: MitigationPlan, idempotency_key: str) -> dict:
    """
    Apply a mitigation action (dangerous). Requires approval.
    Uses idempotency_key so retries won't double-apply.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{CHANGE_API}/v1/mitigations/apply",
            headers={"Idempotency-Key": idempotency_key},
            json={"ticket_id": ticket_id, "plan": plan.model_dump()},
        )
        r.raise_for_status()
        return r.json()

# ---- (3) 에이전트: “무엇을 어떤 순서로 호출할지”를 모델이 결정 ----

instructions = """
You are an on-call SRE assistant. Goal: triage incidents and propose safe mitigations.
Rules:
- Use tools to fetch metrics before proposing changes.
- Never call apply_mitigation unless you have:
  (1) a clear plan with risk assessment
  (2) a rollback or exit condition
- After actions, always post a concise ticket comment with:
  observed evidence, decision, and next checks.
- If uncertain, choose no_change and ask for specific missing signals.
"""

agent = Agent(
    name="oncall-triage-agent",
    instructions=instructions,
    tools=[get_payment_failure_rate, post_ticket_comment, apply_mitigation],
)

async def main():
    ticket_id = "INC-18421"
    alert_text = "Payment API failure rate spiked to 7% in last 10 minutes. User reports checkout errors."

    # (A) 1차 실행: 모델이 툴 호출/계획 수립
    result = await Runner.run(
        agent,
        input=f"[ticket_id={ticket_id}] Alert: {alert_text}",
        max_turns=8,
    )

    # (B) 승인 필요한 툴이 있으면 중단되고 interruptions에 남음
    if result.interruptions:
        # 운영 UI에서는 여기서 사람에게 plan/risk를 보여주고 approve/reject 받는다.
        state = result.to_state()

        # 예시: 자동 승인 정책(데모용) — 실제로는 human-in-the-loop 권장
        for intr in result.interruptions:
            # idempotency key는 “티켓+액션+시간창” 같은 것으로 구성
            state.approve(intr.item_id, extra={"idempotency_key": f"{ticket_id}:{int(time.time())}"})

        # (C) 승인 후 재개
        result2 = await Runner.run(state)
        print(result2.final_output)
    else:
        print(result.final_output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### 예상 출력(예시)
- (1차) 모델이 `get_payment_failure_rate(service="payment-api")` 호출 → 급증 구간 확인  
- 완화안(plan) 제시 후 `apply_mitigation(...)`은 **승인 필요**로 중단  
- 승인 후 재개 → 변경 적용 결과 수신  
- `post_ticket_comment(...)`로 티켓에 “증거/결정/다음 체크” 코멘트 남김

이 패턴에서 중요한 점은 “위험한 행동”을 **항상 tool로 분리**하고, 승인/멱등성/타임아웃을 런타임에서 강제하는 것입니다. Agents SDK는 승인 게이트와 pause/resume를 1급으로 다룹니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **툴 스키마는 ‘모델을 위한 API’로 설계하라**
- name/description은 “사람이 읽는 문서”가 아니라 **모델의 선택 확률**을 좌우합니다.
- 파라미터는 넓게 두기보다 “안전한 범위”를 스키마로 제한(Enums, min/max, required)하세요. (결국 입력 검증 비용을 줄입니다)

2) **제어-plane을 코드로 고정: retries/timeout/circuit breaker**
- 툴 에러를 그대로 던지지 말고, “재시도 가능/불가능”을 구분해 모델에게 전달하세요.
- Agents SDK 문서도 툴 구현에서 `Runner.run`을 호출해 고급 오케스트레이션(조건부 재시도/폴백/체이닝)을 하라고 가이드합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))

3) **Agents as tools vs Handoffs를 섞어라**
- 사용자 응답은 한 에이전트(매니저)가 통제하고, 전문 작업만 서브에이전트를 tool로 호출하는 구성이 운영 난이도가 낮습니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))  
- 라우팅 UX가 핵심(상담/CS)이라면 handoff가 낫지만, 정책 강제(톤/형식/규정)는 별도 계층이 필요합니다.

### 흔한 함정/안티패턴
- **“한 번에 모든 걸 하는 만능 에이전트”**: 툴이 5개만 넘어가도 선택 오류가 급증하고, 실패가 실행 이후에야 드러납니다(특히 잘못된 툴 선택은 비용/사고로 직결). 최근 연구들도 “툴 선택 오류는 실행 전에는 잘 안 보인다”는 문제의식을 다룹니다. ([arxiv.org](https://arxiv.org/abs/2605.07990?utm_source=openai))
- **승인/멱등성 없는 변경 툴**: 재시도 한 번에 중복 적용됩니다. `Idempotency-Key`는 거의 필수입니다.
- **툴 결과를 컨텍스트에 ‘원문 그대로’ 붙이기**: 토큰 폭발 + 민감정보 노출. “요약/정규화된 결과”만 반환하거나, 결과를 파일/DB에 저장하고 “핵심 핸들”만 모델에 주는 방식을 고려하세요(비용/보안 모두 개선).

### 비용/성능/안정성 트레이드오프
- **LLM 자율 루프**는 구현은 빠르지만, 운영 단계에서 토큰/지연이 증가합니다.
- **코드 오케스트레이션**은 빠르고 싸지만, 예외 케이스를 사람이 계속 추가해야 합니다.
- 현실적인 결론: *“라우팅/승인/안전장치=코드, 파라미터/요약/해석=LLM”* 로 경계선을 긋는 게 가장 유지보수성이 좋습니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))

---

## 🚀 마무리
정리하면, 2026년 6월의 “AI Agent tool use + Function Calling 구현”은 단순히 function schema를 붙이는 문제가 아니라, **agent loop를 돌리는 harness**(승인, 중단/재개, 샌드박스, 트레이싱, 메모리)까지 포함한 운영 설계 문제로 이동했습니다. OpenAI도 Agents SDK를 “모델의 자연스러운 작업 패턴에 맞춘 런타임”으로 강화하는 방향을 명확히 하고 있습니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk))

### 도입 판단 기준(체크리스트)
- 도구 호출이 2개 이상이고, **분기/예외**가 많다 → Agent tool use 적합
- 변경/결제/삭제 등 위험 액션이 있다 → 승인 게이트 + 멱등성 + 감사로그 없으면 도입 보류
- 장기 실행/파일 작업/격리 실행이 필요 → sandbox 기반 설계 고려(Agents SDK의 방향성 참고) ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk))

### 다음 학습 추천
- Agents SDK의 **Tools / Orchestration / 승인(pause-resume)** 흐름을 먼저 체화한 뒤 ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))  
- “단일 에이전트 + 툴 추가”로 시작하고, 병목이 생길 때 **Agents as tools(매니저-워커)** 로 확장하는 순서를 권합니다. ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))