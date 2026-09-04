---
title: "도구 호출이 “대충 되는 데”서 “운영 가능한 수준”으로 바뀌는 2026년식 Function Calling 구현 패턴"
description: "2026년 8월 기준, AI Agent의 “도구 사용(tool use)”은 더 이상 데모 기술이 아니라 실제 제품의 신뢰성/비용/보안을 좌우하는 엔지니어링 영역이 됐습니다. 프롬프트를 조금 바꾸면 되겠지…로 접근하면, 결국 운영에서 터집니다."
date: 2026-08-25 01:41:22 +0900
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
2026년 8월 기준, AI Agent의 “도구 사용(tool use)”은 더 이상 데모 기술이 아니라 **실제 제품의 신뢰성/비용/보안**을 좌우하는 엔지니어링 영역이 됐습니다. 프롬프트를 조금 바꾸면 되겠지…로 접근하면, 결국 운영에서 터집니다. 이유는 간단합니다: **LLM은 도구를 ‘호출’하는 텍스트 생성기**이고, 여러분의 시스템은 **부작용(side effect)을 일으키는 실행기**이기 때문입니다.

**언제 쓰면 좋은가**
- 외부 데이터/시스템이 필수인 작업: 주문/예약, 내부 DB 조회, 티켓 생성, 배포/운영 자동화 등
- “설명”이 아니라 “행동”이 필요한 워크플로우: 여러 API를 조합해 최종 산출물을 만들어야 할 때
- 입력/출력 계약(contract)을 강하게 잡아야 하는 경우: JSON Schema 기반 tool args, strict validation

**언제 쓰면 안 되는가**
- 단일 호출로 끝나는 정적 Q&A(툴 필요 없음): 비용만 증가
- 도구 호출이 곧바로 위험한 부작용을 만드는 영역인데, 승인/권한/감사를 설계하지 않은 경우
- “에이전트가 알아서”를 목표로 하고, 실패 시 fallback/재시도/중단 조건이 없는 경우 (운영 장애로 직결)

핵심 결론은 이겁니다: **에이전트는 ‘모델’이 아니라 ‘런타임(실행 루프 + 도구 경계)’에서 완성**됩니다. AWS의 tool-based agent 패턴이 말하는 것도 결국 “LLM이 선택 → 런너가 실행 → 관측값을 다시 넣는 루프”입니다.[^1]

---

## 🔧 핵심 개념
### 1) Tool use / Function Calling의 “진짜” 구성요소
2026년의 표준적인 구조는 아래 4층입니다.

1. **Tool contract(스키마/설명)**  
   - tool name, description, input schema(JSON Schema / Pydantic 등)
   - 여기서 실패하면 호출 자체가 흔들립니다(잘못된 args, 잘못된 tool 선택)

2. **Tool boundary(경계 레이어)**  
   - allowlist(호출 가능한 tool 제한), authz(권한), idempotency, timeout, rate limit
   - “모델이 무엇을 호출할 수 있는가”를 프롬프트가 아니라 **코드**로 고정

3. **Runner(에이전트 루프)**  
   - 모델 출력이 tool call이면 실행 → 결과를 tool_result로 되돌림 → 다음 턴
   - 이 루프를 어떻게 설계하느냐가 안정성을 결정

4. **Observability(추적/평가)**  
   - tool call 성공률, schema pass rate, 재시도 횟수, P95 latency, 비용(토큰+툴)
   - 운영에서는 “정답률”보다 “실패 양상”이 중요합니다

### 2) strict schema의 의미: “JSON을 출력”이 아니라 “args를 강제”
OpenAI 쪽은 function calling에서 `strict: true`를 통해 **스키마 준수 args**를 강제하는 방향을 명확히 했습니다. 스키마가 strict-mode 요건을 만족하지 않으면 요청이 reject될 수 있고, 호환 조합이 아니면 제약 샘플링이 적용되지 않을 수 있습니다.[^2]  
즉, 2026년의 베스트 프랙티스는:
- “모델에게 잘 부탁”이 아니라
- **스키마로 실패를 설계**(fail fast)하고
- 런타임에서 재시도/복구를 설계하는 겁니다.

### 3) “한 번에 여러 툴 호출” vs “매 호출마다 LLM round-trip”
2026년에 특히 눈여겨볼 변화는 **Programmatic Tool Calling(PTC)** 류의 접근입니다. OpenAI Agents SDK 문서에서도, 모델이 JavaScript를 생성해 **루프/분기/병렬 호출을 모델 round-trip 없이 수행**하고 마지막 결과만 모델로 돌리는 패턴을 명시합니다. (제한된 V8 환경, 네트워크/FS 접근 불가, allow된 tool만 호출 가능)[^3]  
이건 단순 최적화가 아니라 “아키텍처 선택”입니다:
- 일반 tool loop: *모델-툴-모델-툴* (디버깅 쉬움, 비용/지연 큼)
- PTC/프로그램 오케스트레이션: *모델 1회 + 툴 다회* (비용/지연↓, 경계 설계가 더 중요)

### 4) 다른 접근과의 차이점: LangGraph류의 그래프 오케스트레이션
LangGraph는 ToolNode 같은 구성 요소로 “도구 실행 노드”를 그래프에 배치해, **결정적 흐름 + 에이전트적 흐름을 섞는** 설계를 제공합니다.[^4]  
정리하면:
- **SDK 루프(단순 ReAct)**: 빠르게 시작, 복잡해지면 조건문 지옥
- **Graph(명시적 상태/분기)**: 복잡한 업무 프로세스/장기 실행/상태 관리에 강함
- **PTC(프로그램 오케스트레이션)**: “작은 워크플로우 다발”에서 latency/토큰 최적화에 강함[^3]

---

## 💻 실전 코드
아래 예제는 “현실적인 시나리오”로 **고객 환불(refund) 처리 에이전트**를 만듭니다.

요구사항(현업에서 흔함):
- 주문 조회 → 결제 취소 → 티켓 생성(사유 기록)까지 **3개 시스템** 연동
- 동일 요청이 중복 들어와도 **idempotent**
- 모델이 임의로 고위험 도구를 남발하지 못하도록 **권한/정책**을 코드로 고정
- tool args는 **스키마 검증(Pydantic)** 으로 fail fast

### 0) 설치/환경
```bash
pip install openai-agents pydantic httpx
export OPENAI_API_KEY="..."
```

### 1) 도구 정의 (스키마 + 정책을 “도구 경계”에 박기)
```python
from __future__ import annotations

import time
import uuid
from typing import Literal, Optional, Dict, Any

import httpx
from pydantic import BaseModel, Field, conint

from agents import Agent, Runner
from agents.decorators import tool

# ---- Tool I/O Schemas ----
class Order(BaseModel):
    order_id: str
    user_id: str
    status: Literal["PAID", "REFUNDED", "CANCELED"]
    amount_cents: conint(ge=0)
    currency: Literal["USD", "KRW"]

class RefundResult(BaseModel):
    order_id: str
    refund_id: str
    refunded_amount_cents: int
    processor: Literal["stripe", "adyen", "internal"]
    idempotency_key: str

class TicketResult(BaseModel):
    ticket_id: str
    order_id: str
    category: Literal["refund"]
    summary: str

# ---- In-memory idempotency store (demo). In production: Redis/DB ----
IDEMPOTENCY: Dict[str, Dict[str, Any]] = {}

def _idem_get(key: str) -> Optional[Dict[str, Any]]:
    return IDEMPOTENCY.get(key)

def _idem_put(key: str, value: Dict[str, Any]) -> None:
    IDEMPOTENCY[key] = value

# ---- Tools ----
@tool
def get_order(order_id: str) -> Order:
    """
    Fetch order from Order Service.
    Use this before attempting refunds.
    """
    # demo: pretend to call internal API
    # r = httpx.get(f"https://orders/api/orders/{order_id}", timeout=2.0).json()
    if not order_id.startswith("ord_"):
        raise ValueError("invalid order_id format")

    return Order(
        order_id=order_id,
        user_id="usr_123",
        status="PAID",
        amount_cents=2599,
        currency="USD",
    )

@tool
def refund_payment(
    order_id: str,
    amount_cents: int,
    reason: str,
    idempotency_key: str,
) -> RefundResult:
    """
    Refund a payment. High-risk side effect.
    Policy:
      - amount_cents must be <= original amount (enforced by caller after reading Order)
      - requires idempotency_key (caller must generate and reuse per request)
      - only allowed for PAID orders (caller must check)
    """
    # idempotency: return previous result if already processed
    prev = _idem_get(idempotency_key)
    if prev:
        return RefundResult(**prev)

    # demo: payment processor call
    # httpx.post("https://payments/refund", json=..., headers={"Idempotency-Key": idempotency_key})
    refund_id = f"rf_{uuid.uuid4().hex[:10]}"
    result = RefundResult(
        order_id=order_id,
        refund_id=refund_id,
        refunded_amount_cents=amount_cents,
        processor="stripe",
        idempotency_key=idempotency_key,
    )

    _idem_put(idempotency_key, result.model_dump())
    return result

@tool
def create_refund_ticket(
    order_id: str,
    user_id: str,
    summary: str,
) -> TicketResult:
    """
    Create a support ticket for audit trail.
    Low risk, but required for compliance.
    """
    ticket_id = f"tkt_{uuid.uuid4().hex[:10]}"
    return TicketResult(ticket_id=ticket_id, order_id=order_id, category="refund", summary=summary)
```

### 2) Agent + 실행 루프 (현실적인 프롬프트: “도구 사용 규칙”을 명시)
- 핵심은 “도구를 써라”가 아니라 **어떤 순서/조건으로 쓰는지**를 정책으로 적는 겁니다.
- Anthropic 문서도 “툴을 쓰게 하려면 가벼운 지시를 추가”할 수 있고, 아예 `tool_choice`로 강제할 수도 있다고 설명합니다.[^5]  
(OpenAI/Anthropic 모두 프롬프트만으로 100% 강제는 어렵고, 결국 런타임 정책이 필요합니다.)

```python
POLICY = """
You are a refund automation agent.

Rules (must follow):
1) Always call get_order(order_id) first.
2) Only refund if order.status == "PAID".
3) Refund amount must be <= order.amount_cents.
4) Always call create_refund_ticket after a successful refund.
5) Do not invent IDs. Use only returned values.
6) Use JSON-like concise tool arguments.
"""

agent = Agent(
    name="RefundAgent",
    model="gpt-5.6",
    instructions=POLICY,
    tools=[get_order, refund_payment, create_refund_ticket],
)

def run_refund_flow(order_id: str, request_id: str) -> str:
    # request_id는 API gateway에서 내려주는 trace/request id라고 가정
    # idempotency_key는 "요청 단위"로 안정적으로 재현 가능해야 함
    idempotency_key = f"refund:{order_id}:{request_id}"

    user_msg = f"""
Process a refund for order_id={order_id}.
Refund full amount unless policy blocks it.
Use idempotency_key="{idempotency_key}" when calling refund_payment.
"""

    result = Runner.run_sync(agent, user_msg)
    return result.final_output

if __name__ == "__main__":
    out = run_refund_flow("ord_9f12ab34", request_id="req_20260825_0001")
    print(out)
```

### 예상 출력(예시)
- 최종 응답은 자연어로 오지만, 내부에서는 대략:
  - get_order 호출 → refund_payment 호출 → create_refund_ticket 호출 순으로 진행
- 결과 텍스트 예:
  - “주문 ord_…(USD 25.99)에 대해 전액 환불을 처리했고(refund_id …), 감사 추적을 위해 티켓 tkt_…를 생성했습니다.”

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) Tool schema를 “작게” 쪼개고, description을 정책 문서처럼 쓴다
도구가 커질수록 모델은 args를 틀리고, 호출 타이밍도 흔들립니다. AWS도 “툴 메타데이터(이름/타입/설명)가 선택과 args 구성에 들어간다”고 정리합니다.[^1]  
실무 팁:
- tool 하나가 “조회+수정+감사로그”를 다 하면 실패율이 늘어납니다.
- “조회 tool”과 “side effect tool”을 분리하고, side effect tool엔 **정책/전제조건**을 써두세요.

### Best Practice 2) idempotency는 ‘모델의 기억’이 아니라 ‘시스템의 계약’
에이전트는 같은 tool을 두 번 호출할 수 있습니다(재시도/루프/컨텍스트 손실).  
따라서 결제/배포/삭제 같은 도구에는:
- `idempotency_key`를 **필수 파라미터**로 두고
- 서버(또는 실행기)에서 강제하세요.  
이게 없으면 “가끔 두 번 환불” 같은 사고가 납니다.

### Best Practice 3) 모델에게 자유를 주기 전에, “경계 레이어”를 먼저 만든다
- allowlist(이 에이전트가 쓸 수 있는 tool 목록)
- timeout / retry / circuit breaker
- 입력 검증(Pydantic) + 출력 검증(가능하면)
- 감사 로그(누가/언제/무슨 요청으로 어떤 tool을 몇 번 호출했는지)

### 흔한 함정/안티패턴
- **프롬프트만으로 순서를 강제**하려고 함 → 어느 날 모델 업데이트/컨텍스트 변화로 깨집니다.
- **tool output을 그대로 다음 tool 입력으로 복붙** → 포맷 드리프트가 생기면 연쇄 실패.
- **JSON mode / strict를 “응답 전체 JSON”으로 오해** → 실제로 중요한 건 “tool args의 구조적 제약”입니다. OpenAI는 function call args에 스키마 제약이 적용되는 흐름을 분명히 설명합니다.[^2]

### 비용/성능/안정성 트레이드오프
- 단순 loop는 디버깅이 쉽지만 **모델 round-trip이 많아 latency/비용↑**
- PTC(프로그램 오케스트레이션)는 latency/토큰을 줄일 수 있지만, 실행 환경 제약(V8 sandbox, 네트워크/FS 없음, allow된 tool만) 때문에 **툴 설계가 더 중요**합니다.[^3]
- LangGraph 같은 그래프는 복잡한 상태 머신에 강하지만, 작은 문제에 쓰면 “비싼 if-else”가 되기 쉽습니다(프레임워크가 해결해주지 않는 운영 문제도 많음).

---

## 🚀 마무리
2026년 8월의 Function Calling/Agent tool use 구현에서 중요한 건 “모델이 똑똑해졌다”가 아니라:

- **스키마 기반 계약(가능하면 strict)**
- **도구 경계(권한/멱등/타임아웃/관측)**
- **에이전트 루프(재시도/중단 조건/오류 복구)**
- 그리고 필요하면 **프로그램 오케스트레이션(PTC)로 비용/지연 최적화**[^3]

도입 판단 기준을 한 줄로 요약하면:
- “툴이 1~2개고 부작용이 작다” → 단순 tool loop + strict schema
- “툴이 많고 상태/분기가 복잡하다” → 그래프 오케스트레이션(LangGraph류)
- “짧은 워크플로우를 자주 돌려 비용/지연이 문제다” → PTC 같은 ‘한 번에 여러 툴’ 패턴 검토

다음 학습 추천:
- OpenAI Agents SDK의 Tools/Programmatic Tool Calling 섹션을 읽고, **내 서비스의 tool boundary 레이어**(idempotency/authz/timeout)를 먼저 구현하세요.[^3]
- AWS의 tool-based agent 패턴 문서를 기준으로, “LLM 결정”과 “실행기 책임”을 분리한 아키텍처로 리팩터링해보세요.[^1]

[^1]: <https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/tool-based-agents-for-calling-functions.html>
[^2]: <https://help.openai.com/en/articles/8555517-function-calling-updates>
[^3]: <https://openai.github.io/openai-agents-python/tools/>
[^4]: <https://langchain-ai.github.io/langgraph/reference/agents/?h=create_react>
[^5]: <https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview?c=nerd>
