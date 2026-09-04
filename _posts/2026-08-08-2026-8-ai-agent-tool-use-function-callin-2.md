---
title: "도구를 “호출”이 아니라 “실행”하게 만들기: AI Agent Tool Use & Function Calling 구현 심층 가이드"
description: "2026년의 AI Agent는 “대화 잘하는 모델”이 아니라 도구(tool)를 안전하게 실행하는 런타임에 가깝습니다. 실무에서 부딪히는 문제는 늘 비슷합니다."
date: 2026-08-08 02:06:21 +0900
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
2026년의 AI Agent는 “대화 잘하는 모델”이 아니라 **도구(tool)를 안전하게 실행하는 런타임**에 가깝습니다. 실무에서 부딪히는 문제는 늘 비슷합니다.

- 모델이 **툴을 잘못 고르거나**(wrong tool)  
- 인자를 **잘못 구성**하거나(bad args)  
- 네트워크/타임아웃으로 **재시도 중 중복 실행**을 만들거나(duplicate side-effect)  
- 멀티턴에서 **call_id 연결이 끊겨** 디버깅이 불가능해지는 문제

2026년 8월 기준, OpenAI 쪽은 Responses API를 중심으로 “tool-calling / multi-turn / programmatic tool calling”까지 하나의 표준 흐름으로 묶었고, Agents SDK는 이를 “Runner + Tool + Guardrails + HITL”로 감싸 **실행 제어**를 제공합니다. 특히 “program items / program-issued function calls / call_id & caller linkage” 같은 디테일은 이제 선택이 아니라 운영 필수에 가깝습니다.[^1]

### 언제 쓰면 좋나
- 외부 API/DB/사내 시스템을 **반복적으로 호출**하며 멀티스텝 작업을 해야 할 때
- “툴 실행”이 실패했을 때 **복구 가능한 루프(recoverable loop)** 가 필요할 때
- 승인(approval), 입력 검증(guardrails), allowlist 등 **거버넌스가 필요한 프로덕션**

### 언제 쓰면 안 되나
- 단발성 Q&A/요약처럼 **툴 호출이 본질이 아닌** 작업
- side-effect(결제/발송/삭제)가 큰데도 idempotency/승인/감사로그 없이 “에이전트가 알아서” 하게 만들려는 경우(운영 사고로 갑니다)
- 10개 이상 분기/조건을 그래프로 억지로 표현하려는 경우: 결국 “LLM 붙은 state machine”이 되고, 변경 비용만 올라갑니다(이건 LangGraph류든 직접 구현이든 동일)

---

## 🔧 핵심 개념
### 1) Function Calling = “구조화된 실행 계약(Contract)”
Function Calling은 “모델이 JSON을 예쁘게 뱉는다”가 아니라,
- **툴 이름 선택**
- **스키마 기반 인자 생성**
- **실행 결과를 다시 컨텍스트로 주입**
- **그 후속 추론**
을 하나의 계약으로 만들고, 애플리케이션은 이 계약을 **검증/실행/감사**하는 구조입니다.

OpenAI Agents SDK는 Python 함수의 signature/docstring에서 **툴 스키마를 자동 생성**하고, 실행은 Runner가 맡습니다.[^2]

### 2) 2026년의 관전 포인트: “Programmatic Tool Calling(PTC)”
최근 흐름은 “JSON tool call”을 반복하는 대신, 모델이 **program(코드) 형태로 여러 툴 호출을 조합**하는 패턴이 확산 중입니다. OpenAI 문서도 PTC를 별도 도구로 소개하며, 앱은 `program`/`program_output` 및 `call_id`, `caller` 링크를 보존해야 한다고 명시합니다.[^1]  
즉, 이제는 “툴 1회 호출”이 아니라 **툴 호출 그래프를 런타임이 추적**하는 시대입니다.

### 3) 실패를 전제로 한 실행 모델: “Recoverable loop”
프로덕션에서는 모델이 존재하지 않는 툴을 부르거나(오타/환각), 런타임의 allowlist 밖 툴을 부를 수 있습니다. Agents SDK는 기본적으로 이런 경우 `ModelBehaviorError`로 터뜨리지만, 옵션으로 **에러를 모델에게 반환하고 다른 툴/답변으로 회복**시키는 모드를 제공합니다.[^3]  
이게 중요한 이유는 “툴 실패 = 사용자 실패”가 아니라, **툴 실패를 포함한 플로우 설계**가 가능해지기 때문입니다.

### 4) 다른 접근과의 차이점(Framework vs Pattern)
- Agents SDK(OpenAI): Runner가 turn/tool/call_id/승인/에러 복구를 “표준 루프”로 제공  
- LangGraph류: 루프를 명시적 그래프로 드러내 제어는 쉬우나, 결국 중요한 건 **툴 경계의 규칙(idempotency/approval/audit)** 을 얼마나 잘 구현하느냐입니다(프레임워크는 부차적).[^4]  
- Anthropic tool-use: “tool을 텍스트 파싱이 아니라 계약으로” 보는 철학이 강하고, tool boundary에서 결정 구조화를 권장합니다.[^5]  

---

## 💻 실전 코드
시나리오: “사내 주문 처리 에이전트”  
- 고객이 “주문 상태 확인 + 필요 시 주소 변경 요청”을 합니다.  
- 주소 변경은 side-effect가 있으므로 **HITL(승인) + idempotency** 가 필요합니다.  
- 존재하지 않는 툴 호출/인자 오류가 나면 **모델에게 에러를 반환해 회복**합니다.

아래 코드는 “toy”가 아니라, 실무에서 바로 쓰는 형태(HTTP 호출, idempotency key, 승인 게이트, 에러 복구, 예상 출력)를 담았습니다.

### 0) 설치/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install "openai-agents>=0.14.0" httpx pydantic
export OPENAI_API_KEY="..."
```
(Agents SDK 업데이트/카테고리 및 Runner 동작은 공식 문서 기준)[^2]

### 1) 기본 셋업: Function tools + 승인(approval) + idempotency
```python
import os
import uuid
import httpx
from pydantic import BaseModel, Field

from agents import Agent, Runner, RunConfig
from agents.tools import function_tool

ORDER_API_BASE = "https://example.internal.api"  # 사내 API라고 가정

class OrderStatus(BaseModel):
    order_id: str
    status: str
    eta_days: int | None = None

class AddressChangeResult(BaseModel):
    order_id: str
    accepted: bool
    message: str

@function_tool
def get_order_status(order_id: str) -> dict:
    """
    Fetch order status from internal Order API.

    Use this when the user asks about delivery status, ETA, or current order state.
    """
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{ORDER_API_BASE}/orders/{order_id}")
        r.raise_for_status()
        data = r.json()

    parsed = OrderStatus(**data)
    return parsed.model_dump()

@function_tool(needs_approval=True)
def request_address_change(order_id: str, new_address: str) -> dict:
    """
    Request address change for an existing order (side-effect).

    Only call this after you have:
    1) confirmed the order_id,
    2) confirmed the full new_address,
    3) explained that a human approval is required.
    """
    # idempotency key: 재시도/중복 실행 방지의 최소 단위
    idem_key = f"addrchg:{order_id}:{uuid.uuid4().hex}"

    with httpx.Client(timeout=8.0) as client:
        r = client.post(
            f"{ORDER_API_BASE}/orders/{order_id}/address-change",
            json={"new_address": new_address},
            headers={"Idempotency-Key": idem_key},
        )
        r.raise_for_status()
        data = r.json()

    parsed = AddressChangeResult(**data)
    return parsed.model_dump()

agent = Agent(
    name="OrderOpsAgent",
    instructions=(
        "You are an operations agent. Prefer tools over guessing.\n"
        "For address changes, always summarize the change and wait for approval.\n"
        "If a tool call fails, recover: ask for missing fields or try an alternative.\n"
    ),
    tools=[get_order_status, request_address_change],
)

async def main():
    user_msg = (
        "주문번호 A-10291 상태 알려주고, 배송지 주소를 "
        "'서울시 강남구 테헤란로 123, 10층'으로 바꿔줘"
    )

    result = await Runner.run(
        agent,
        user_msg,
        run_config=RunConfig(
            tool_not_found_behavior="return_error_to_model",  # 회복 루프
        ),
    )

    # 승인 필요한 경우: interruptions에 쌓이고 run이 pause됨
    if result.interruptions:
        print("=== PENDING APPROVAL ===")
        for it in result.interruptions:
            print(it)

        # 실제 서비스라면: 관리자 UI에서 approve/reject
        state = result.to_state()
        # 데모: 승인한다고 가정
        state.approve_all()

        result = await Runner.resume(state)

    print("=== FINAL ===")
    print(result.final_output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### 2) 예상 출력(형태)
- 첫 run에서 `request_address_change`가 pending approval로 멈추고,
- approve 후 resume하면 최종 답변이 완료됩니다.

```text
=== PENDING APPROVAL ===
<Interruption tool=request_address_change call_id=... reason=needs_approval ...>

=== FINAL ===
주문 A-10291은 현재 "배송 준비중"이며 예상 2일 내 출고 예정입니다.
배송지 변경 요청: "서울시 강남구 테헤란로 123, 10층"으로 변경을 접수했고 승인 완료 후 반영됩니다.
```

여기서 핵심은 “승인 기능이 있다”가 아니라,
- **툴 실행이 멈출 수 있고(pause)**
- 그 상태를 직렬화해(UI/queue로) 넘겼다가
- **같은 call_id 흐름으로 재개(resume)** 할 수 있다는 점입니다. (HITL pause/resume는 SDK가 가이드로 제공)[^2]

### 3) 확장: Programmatic Tool Calling을 고려해야 하는 순간
- “상태 조회 → 정책 확인 → 변경 요청 → 변경 검증” 같은 체인이 길어지면,
  JSON tool-call 왕복이 많아져 토큰/지연이 증가합니다.
- 이때 PTC는 모델이 `program`으로 여러 툴 호출을 묶어 실행하는 방향을 제공합니다(대신 런타임은 `program`/`program_output` 및 `caller` 링크 보존이 필요).[^1]

실무 판단 기준:
- 단순 1~2회 툴 호출이면 일반 function calling이 운영하기 쉽고,
- 5회 이상 연쇄 호출 + 중간 산출물 크기가 크면 PTC를 PoC로 비교해볼 가치가 큽니다(토큰/턴 수/지연/성공률로 벤치마크).[^1]

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 효과 나는 3가지)
1) **Tool boundary에 idempotency를 넣어라**
- 에이전트 재시도는 “가끔”이 아니라 “기본값”입니다(네트워크 타임아웃, 모델 재호출, 스트리밍 중단).
- 결제/발송/삭제 계열은 idempotency 없으면 언젠가 중복 실행이 납니다.

2) **tool_not_found / tool_error를 “모델이 이해 가능한 에러”로 반환**
- 기본으로 죽이면 운영자가 새벽에 온콜합니다.
- 회복 모드(`tool_not_found_behavior="return_error_to_model"`) + 에러 메시지 포맷팅으로 “다른 툴을 쓰거나 사용자에게 추가 질문”으로 수습하게 만드세요.[^3]

3) **Approval(승인)을 ‘툴 단위’로 걸어라**
- “최종 답변 전에 승인”은 이미 side-effect가 실행된 뒤일 수 있습니다.
- SDK는 `needs_approval`로 **툴 호출 자체를 pause** 시키는 패턴을 제공합니다.[^2]

### 흔한 함정/안티패턴
- (안티패턴) 툴 설명(docstring)이 빈약해서 모델이 “언제 어떤 툴을 써야 하는지”를 못 배움  
  → 결과적으로 프롬프트에 if-else 규칙이 늘고, 유지보수 비용이 폭증합니다.
- (함정) “툴 호출 결과”를 그대로 컨텍스트에 던져서 토큰 폭발  
  → 툴 응답은 **요약/필터링**해서 반환(특히 로그/HTML/대용량 JSON).
- (함정) 멀티턴에서 call_id 상관관계를 저장하지 않음  
  → 장애 분석 시 “무슨 툴이 언제 왜 호출됐는지”를 재현 못 합니다. (특히 PTC는 `caller` 링크까지 중요)[^1]

### 비용/성능/안정성 트레이드오프
- **Reasoning.effort**를 높이면 성공률이 오를 수 있지만 지연/비용도 같이 오릅니다. 기본은 `medium`에서 시작해 워크로드별로 계측해서 내리는 게 2026년 OpenAI 가이드의 톤입니다.[^1]  
- PTC는 토큰/턴을 줄일 잠재력이 있지만, 런타임 관측/보안 정책(allowlist, sandbox, 감사로그)까지 같이 성숙해야 “이득”이 됩니다.[^1]

---

## 🚀 마무리
정리하면, 2026년 8월의 “Agent tool use 구현”에서 중요한 건 프레임워크가 아니라 **툴 경계의 설계**입니다.

- 단순 자동화: Responses API + 기본 function calling으로 충분
- 운영 자동화/업무 시스템 연결: Agents SDK의 Runner/승인/에러복구로 “실행 제어”를 확보
- 연쇄 호출이 길고 비용이 부담: PTC를 벤치마크로 검토(단, call_id/caller 추적과 정책 집행이 가능한 조직/런타임일 때)

다음 학습 추천:
- OpenAI Agents SDK의 Tools/Running agents 문서에서 **approval pause/resume**, **tool_not_found recovery**, **tool error formatting**을 먼저 마스터하세요.[^2]  
- 그 다음 “programmatic tool calling”을 실제 업무 플로우(5+ 툴 체인)에서 토큰/지연/성공률로 비교 테스트하는 게 가장 빠른 실무 루트입니다.[^1]

[^1]: <https://developers.openai.com/api/docs/guides/latest-model>
[^2]: <https://openai.github.io/openai-agents-python/tools/>
[^3]: <https://openai.github.io/openai-agents-python/running_agents/>
[^4]: <https://arxiv.org/abs/2607.19297>
[^5]: <https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works>
