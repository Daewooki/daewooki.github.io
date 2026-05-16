---
title: "Function Calling으로 “에이전트답게” 만들기: 2026년 5월 기준 Tool Use 구현 패턴과 실전 설계"
date: 2026-05-16 03:50:12 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-05]
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

LLM 기반 AI Agent를 실제 서비스에 붙이면 가장 먼저 부딪히는 문제는 **“대답은 그럴듯한데, 행동(action)은 못 한다”** 입니다. DB 조회, 사내 API 호출, 티켓 발행, 결제 취소, 리포트 생성처럼 **외부 시스템과의 상호작용**이 필요한 순간부터, 프롬프트만으로는 한계가 오고 결국 **tool use / function calling**이 필수가 됩니다. OpenAI는 이를 Agents SDK/Responses API의 핵심 축으로 정리했고, “run(loop) + tool call + tool result”라는 표준 형태로 수렴하는 중입니다. ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))

언제 쓰면 좋나:
- **정형 작업**(조회/생성/승인/계산)을 LLM이 “결정”하고, 실제 실행은 **코드가 통제**해야 할 때
- 멀티스텝 업무(예: “고객 환불 요청 → 정책 확인 → 주문 조회 → 승인/반려 → 결과 저장”)를 **오케스트레이션**해야 할 때 ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))
- “WebSearch/FileSearch/Computer” 같은 도구를 섞어 **현실 세계의 상태**를 반영해야 할 때 ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-updates?utm_source=openai))

언제 쓰면 안 되나:
- 단발성 Q&A/요약처럼 **행동이 필요 없는** 경우(툴은 비용/지연/실패면적만 늘립니다)
- 툴이 “만능”처럼 보이지만 사실상 **업무 규칙이 불명확**한 경우(결국 인간 승인/정책 정리가 먼저)
- 보안/비용이 민감한데, 툴 응답에 의해 에이전트가 **무한 루프/비용 증폭**될 수 있는 구조를 통제 못 하는 경우(툴 레이어가 공격면이 됩니다) ([arxiv.org](https://arxiv.org/abs/2601.10955))

---

## 🔧 핵심 개념

### 주요 개념 정의
- **Tool(Function)**: 모델이 호출 가능한 “행동”의 인터페이스. 일반적으로 **JSON Schema로 입력을 엄격히 정의**합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/function-calling?api-mode=chat))
- **Tool call**: 모델이 `name + arguments(JSON)` 형태로 “실행 요청”을 내는 이벤트.
- **Tool result**: 앱이 실제 함수를 실행한 뒤 결과를 모델에 되돌려 주는 메시지.
- **Run(loop)**: 에이전트가 종료 조건에 도달할 때까지 “생각→툴 호출→결과 반영→다음 스텝”을 반복하는 실행 루프. Agents SDK 문서/가이드가 이 구조를 명시적으로 다룹니다. ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))

### 내부 작동 방식(구조/흐름)
프로덕션에서의 안정적인 흐름은 보통 아래 6단계로 고정합니다.

1) **Tool schema 등록**
- 입력 타입을 좁힐수록(예: enum, min/max, format) 모델의 실수 범위가 줄어듭니다.
- OpenAI Agents SDK(Python)는 함수 시그니처/Docstring으로 schema를 자동 생성할 수 있습니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))

2) **모델 호출(“tool_choice=auto” 또는 강제)**
- “자동 선택”은 편하지만, 특정 구간(예: 결제/삭제)은 **강제 tool_choice + 추가 가드**가 낫습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/function-calling?api-mode=chat))

3) **모델이 tool call 생성**
- 여기서의 핵심은 “모델이 실행하지 않는다”는 점. 실행은 당신의 런타임이 합니다.

4) **런타임에서 tool 실행**
- API call, DB query, 큐 enqueue 등. 이때 **timeouts/retries/circuit breaker**는 애플리케이션 책임.

5) **tool result를 모델에 전달**
- 모델이 다음 행동을 결정하도록 충분한 결과(성공/실패/에러코드/부분 데이터)를 구조적으로 돌려줍니다.

6) **종료 조건**
- 최종 답변 출력, 특정 “final-output tool”, max_turn, 에러 등으로 종료. OpenAI 가이드는 “run은 루프이며 종료 조건이 필요”하다고 못 박습니다. ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))

### 다른 접근과의 차이점
- **RAG-only**: 지식 주입은 되지만 “행동”이 약합니다. 업무 시스템 연동은 결국 별도 코딩.
- **Graph DSL(예: 고정 워크플로우)**: 시각화/명시성은 좋지만, 동적 분기/예외가 늘면 그래프가 비대해집니다. OpenAI의 가이드는 Agents SDK를 “code-first로 동적 오케스트레이션”에 강점이 있다고 설명합니다. ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))
- **Computer use(브라우저/OS 조작)**: 범용성이 있지만 비용·지연·불확실성이 큽니다. 가능하면 “API tool”로 먼저 해결하고, UI 자동화는 최후수단으로 두는 편이 안정적입니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))

---

## 💻 실전 코드

아래 예시는 “CS 환불 에이전트”에 가까운 형태로, **주문 조회 → 환불 가능성 판단 → 환불 실행 → 감사 로그 적재**까지를 tool로 엮습니다. toy가 아니라, 실제 서비스에서 흔한 **정책/DB/API/로그** 구성을 최소 단위로 담았습니다.

### 0) 설정/의존성

```bash
python -m venv .venv
source .venv/bin/activate

pip install openai-agents pydantic httpx
export OPENAI_API_KEY="..."
```

> `openai-agents`는 OpenAI Agents SDK(Python) 기준. “함수→툴 래핑, run loop, tracing” 같은 에이전트 런타임을 제공하는 방향으로 업데이트되고 있습니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))

### 1) 초기 셋업: 도메인 Tool 3개 정의 (조회/실행/로그)

```python
# refund_agent.py
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field
from agents import Agent, Runner, function_tool

# ---- Domain models (현실적인 출력 구조) ----
class Order(BaseModel):
    order_id: str
    user_id: str
    status: Literal["PAID", "SHIPPED", "DELIVERED", "CANCELED"]
    amount_usd: float
    paid_at: str
    delivered_at: Optional[str] = None

class RefundResult(BaseModel):
    ok: bool
    refund_id: Optional[str] = None
    reason: Optional[str] = None

# ---- Tools ----
@function_tool
def get_order(order_id: str) -> Order:
    """
    Fetch an order from the Order Service (mocked).
    Args:
      order_id: The order identifier.
    """
    # 실제라면: DB 조회 or internal API call
    # 여기서는 예시 데이터를 리턴
    if order_id == "ord_1001":
        return Order(
            order_id="ord_1001",
            user_id="u_77",
            status="DELIVERED",
            amount_usd=129.0,
            paid_at="2026-05-01T10:12:00Z",
            delivered_at="2026-05-03T19:22:00Z",
        )
    return Order(
        order_id=order_id,
        user_id="u_77",
        status="PAID",
        amount_usd=49.0,
        paid_at="2026-05-14T08:00:00Z",
    )

@function_tool
def issue_refund(order_id: str, amount_usd: float, reason: str) -> RefundResult:
    """
    Issue a refund via Payments Service (mocked).
    Args:
      order_id: The order id.
      amount_usd: Refund amount in USD.
      reason: Human-readable reason for audit.
    """
    # 실제라면: 결제 PG/사내 결제 API 호출 + idempotency key 필수
    if amount_usd <= 0:
        return RefundResult(ok=False, reason="amount_usd must be > 0")
    return RefundResult(ok=True, refund_id=f"rf_{order_id}_001")

@function_tool
def write_audit_log(event: str, order_id: str, details: dict) -> None:
    """
    Write an audit log event (mocked).
    Args:
      event: Event name.
      order_id: Related order id.
      details: JSON-serializable details.
    """
    # 실제라면: append-only log store (BigQuery/ELK/Kafka) 등에 적재
    print(f"[AUDIT] event={event} order_id={order_id} details={details}")
```

### 2) 에이전트 구성: “정책 판단은 모델, 실행은 툴”

```python
from agents import ModelSettings

policy = """
You are a customer support refund agent.
Rules:
- Never guess order status; always call get_order first.
- Refund is allowed only if:
  - status is PAID or SHIPPED (not delivered), OR
  - delivered within last 7 days and user claims defect.
- If refund is approved, call issue_refund then write_audit_log.
- If not approved, explain why and suggest next steps.
Return a concise final answer in Korean.
"""

agent = Agent(
    name="refund_agent",
    instructions=policy,
    tools=[get_order, issue_refund, write_audit_log],
    model_settings=ModelSettings(tool_choice="auto"),
)

if __name__ == "__main__":
    user_msg = "주문 ord_1001 환불해줘. 제품이 불량이야."
    result = Runner.run_sync(agent, user_msg)
    print("\n=== FINAL ===")
    print(result.final_output)
```

### 3) 예상 출력(예시)

```text
[AUDIT] event=refund_issued order_id=ord_1001 details={'refund_id': 'rf_ord_1001_001', 'amount_usd': 129.0, 'reason': 'Defective item within 7 days of delivery'}

=== FINAL ===
주문(ord_1001)은 2026-05-03에 배송완료로 확인되며, 배송 후 7일 이내 불량 주장으로 환불 진행 가능합니다. 환불이 접수되었고 환불 ID는 rf_ord_1001_001 입니다. 영업일 기준 처리 상황이 업데이트되면 안내드리겠습니다.
```

이 예제에서 포인트는:
- 에이전트가 **반드시 get_order를 먼저 호출**하도록 규칙을 강제(“추측 금지”)
- 환불 실행은 `issue_refund`로만 하며, 감사 로그는 별도 tool로 남겨 **감사 가능성**을 확보
- 최종 응답은 사용자 친화적이되, 정책 근거(7일)를 함께 출력

---

## ⚡ 실전 팁 & 함정

### Best Practice (2~3개)
1) **Tool 입력 스키마를 “좁게” 설계**
- enum/범위/필수값을 최대한 지정하세요. Agents SDK는 함수 시그니처 기반으로 schema를 만들 수 있지만, 애매한 `dict` 남발은 모델의 오입력을 키웁니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))

2) **Idempotency + 재시도 전략을 tool 레이어에 내장**
- LLM은 같은 tool을 재호출할 수 있습니다(네트워크 지연/추론 분기).
- 결제/환불/주문취소 같은 side-effect tool은 **idempotency key** 없으면 사고 납니다.

3) **Run 종료 조건(max_turn/tool budget)을 명시**
- 멀티스텝은 성공확률이 호출 횟수만큼 누적 하락합니다. 그리고 공격/오류로 “비용 증폭”이 가능합니다. run에 turn/tool 제한을 걸고, 실패 시 fallback(사람에게 이관/티켓 생성)을 준비하세요. ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))

### 흔한 함정/안티패턴
- **툴 결과를 자연어로만 반환**: 모델이 다음 스텝에서 파싱하다가 망가집니다. 결과는 구조화(JSON/Pydantic) + 핵심 필드(상태/에러코드)를 고정하세요.
- **툴을 “너무 크게” 만들기**: `do_everything(order_id, user_text)` 같은 만능 툴은 디버깅/권한통제/테스트가 지옥이 됩니다. “조회/판단/실행/로그”처럼 **책임을 분리**하세요.
- **외부 MCP/서드파티 툴을 무검증으로 연결**: 툴 레이어가 공격면이 될 수 있고(스텔스 비용 증폭 등), “정상 payload는 유지하면서도 체인을 늘리는” 형태가 가능하다는 연구가 나와 있습니다. allowlist, 응답 길이 제한, 정책 검사(validator)가 필요합니다. ([arxiv.org](https://arxiv.org/abs/2601.10955))

### 비용/성능/안정성 트레이드오프
- **성능(지연)**: 멀티툴 체인은 느립니다. 실시간 UX면 “비동기 I/O + speculative tool calling” 같은 접근이 연구되고 있습니다(속도↑, 정확도 약간↓). ([arxiv.org](https://arxiv.org/abs/2605.13360))
- **비용**: 툴 호출이 늘수록 토큰/외부 API 비용이 직선적으로 증가합니다. “한 번에 끝내려는” 프롬프트 욕심이 오히려 재시도를 늘려 비용을 키울 수 있습니다.
- **안정성**: tool 호출 성공률이 90%여도 5단계면 전체 성공률이 크게 떨어집니다. 따라서 “필수 단계만 tool로” 만들고, 나머지는 deterministic code로 전환하는 것이 보통 이깁니다(정책 판단도 가능하면 코드화). ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))

---

## 🚀 마무리

2026년 5월 기준, AI Agent의 tool use/function calling은 더 이상 “옵션”이 아니라 **프로덕션 에이전트의 기본 인터페이스**로 굳어지고 있습니다. 핵심은 “모델이 실행하는 게 아니라, 모델은 *요청*하고 런타임이 *통제*한다”는 분리입니다. OpenAI의 가이드/SDK가 말하는 run(loop), tool schema, handoff/agents-as-tools 같은 구성은 결국 **오케스트레이션의 표준화**로 수렴합니다. ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf))

도입 판단 기준:
- 우리 시스템이 “조회/변경/승인” 같은 **명확한 API surface**를 갖고 있는가?
- tool 호출 실패/지연/비용을 **운영 가능한 수준으로 제한**할 수 있는가? (max_turn, timeout, idempotency, audit)
- 모델이 해야 할 일(불확실 판단)과 코드가 해야 할 일(결정적 실행)을 **분리**했는가?

다음 학습 추천(깊이 확장 순서):
- OpenAI “Function calling / Tools” 가이드로 메시지/툴 루프의 wire-level 이해 ([platform.openai.com](https://platform.openai.com/docs/guides/function-calling?api-mode=chat))  
- Agents SDK의 Tools 문서(ComputerTool, function_tool, agents-as-tools)로 런타임 패턴 정리 ([openai.github.io](https://openai.github.io/openai-agents-python/tools/))  
- 툴 체인 보안/비용 공격면(툴 레이어 DoS)과 완화책 설계 ([arxiv.org](https://arxiv.org/abs/2601.10955))  
- 실시간 UX가 필요하면 async/speculative tool calling 연구도 참고 ([arxiv.org](https://arxiv.org/abs/2605.13360))  

원하면, 위 환불 예제를 **(1) DB 트랜잭션 + idempotency 키**, **(2) tool validator(스키마+정책) 계층**, **(3) tracing/observability**까지 포함한 “운영 가능한 형태”로 확장해서 후속 글 형태로 더 구체화해드릴 수 있습니다.