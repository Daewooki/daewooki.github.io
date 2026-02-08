---
title: "2026년 2월, AI Agent “Tool Use + Function Calling” 구현의 정답: 스키마 강제(Strict)·루프 제어·추적(Tracing)으로 프로덕션까지"
date: 2026-02-08 03:24:19 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-02]
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
2026년 2월 기준, “AI Agent가 도구를 호출해 실제 일을 한다”는 말은 더 이상 데모가 아닙니다. 하지만 프로덕션에서 진짜 문제가 되는 지점은 모델 성능이 아니라 **통제(control)** 입니다.  
- 모델이 **언제(tool selection)**, **무엇을(arguments)**, **몇 번이나(loop)** 호출할지  
- 호출 결과를 **어떻게 관찰/디버깅(tracing)** 할지  
- 외부 시스템과 연결이 늘어날수록 생기는 **N×M 통합 지옥**을 어떻게 줄일지  

최근 OpenAI는 Agents SDK/Tracing을 중심으로 “tool use를 워크플로우로 운영”하게 만들고 있고, Function Calling에는 `strict: true` 기반 **Structured Outputs**로 “JSON 스키마 준수”를 사실상 표준으로 못 박았습니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api%23.eps?utm_source=openai))  
또한 업계는 MCP(Model Context Protocol)처럼 “도구 연결을 표준화”해 통합 비용을 줄이려는 흐름이 강해지고 있습니다. ([wired.com](https://www.wired.com/story/openai-anthropic-and-block-are-teaming-up-on-ai-agent-standards?utm_source=openai))  

---

## 🔧 핵심 개념
### 1) Tool Use vs Function Calling
- **Function Calling**: LLM이 “이 함수(도구)를 호출하겠다”는 결정을 내리고, 그 **arguments를 JSON**으로 생성하는 패턴  
- **Tool Use**: Function Calling을 포함해, 에이전트 런타임이 **도구 실행 → 결과 반영 → 다음 턴 진행**을 관리하는 상위 개념

OpenAI 쪽에서 중요한 변화는 “함수 정의에 `strict: true`를 켜면, 모델이 생성하는 arguments가 **JSON Schema와 정확히 일치**하도록 보장”한다는 점입니다(Structured Outputs). 즉, 재시도/파싱 지옥을 크게 줄입니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api%23.eps?utm_source=openai))  

### 2) “Schema-first”가 2026년의 기본기
이제 프롬프트로 “정확히 이 형태로 내”라고 비는 대신:
- 도구 입력을 **JSON Schema로 고정**
- 모델은 그 스키마를 만족하는 arguments만 생성(= `strict: true`)
- 애플리케이션은 **검증/보안/관측**을 그 스키마 경계에서 수행

이 패턴이 자리 잡으면, 에이전트는 “텍스트 생성기”가 아니라 **타입이 있는 호출자(typed invoker)** 처럼 다룰 수 있습니다.

### 3) 무한 루프(Loop)와 Tool Choice 제어
Tool을 붙였다고 항상 도구를 호출하진 않습니다. 반대로 강제하면 무한 반복 위험이 있습니다. OpenAI Agents SDK(JS)는 `toolChoice`로 자동/필수/금지/특정 도구 강제를 제공하고, 도구 호출 후 기본적으로 `toolChoice`를 다시 `auto`로 리셋해 **무한 루프를 예방**합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))  

또한 `toolUseBehavior`로 “첫 tool 결과에서 종료” 같은 런 정책을 걸 수 있어, **에이전트가 ‘생각→도구→생각→도구…’**로 끝없이 가는 상황을 런타임 차원에서 자를 수 있습니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))  

### 4) Tracing은 선택이 아니라 필수
프로덕션 장애의 80%는 “모델이 왜 그 도구를 호출했는지/무슨 입력을 만들었는지”를 못 봐서 생깁니다. OpenAI Agents SDK는 기본으로 **LLM generation, tool call, handoff, guardrail**까지 span 단위로 추적합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tracing/?utm_source=openai))  
즉, “로그 몇 줄”이 아니라 **워크플로우 관측 가능성(observability)** 을 SDK가 제공하는 쪽으로 패러다임이 이동했습니다.

---

## 💻 실전 코드
아래 예시는 **OpenAI Agents SDK (Python)** 스타일로, “DB 조회 도구 + 승인(approval) + 스키마 기반 입력 + 추적”을 한 번에 엮는 최소 실행 뼈대입니다. (실제 배포에서는 DB/권한/네트워크는 여러분 환경에 맞게 교체)

```python
import asyncio
from typing import TypedDict, Optional

from agents import Agent, Runner, function_tool, trace, RunContextWrapper

# 1) Tool input을 타입/스키마로 고정: schema-first의 출발점
class OrderQuery(TypedDict):
    user_id: str
    status: Optional[str]  # "paid" | "shipped" | ... 같은 enum으로 더 엄격히 해도 좋음
    limit: int

# 2) Tool 함수: docstring/시그니처로부터 schema 생성(Agents SDK가 자동화)
@function_tool
async def fetch_recent_orders(ctx: RunContextWrapper[dict], query: OrderQuery) -> str:
    """
    Fetch recent orders for a user from an internal system.

    Args:
        query: Query parameters including user_id, optional status filter, and limit.
    """
    # ctx.context에는 DB 커넥션/설정 등을 넣어 전달(LLM에 노출되지 않음) ([openai.github.io](https://openai.github.io/openai-agents-python/ref/run_context/?utm_source=openai))
    fake_db = ctx.context["db"]

    user_id = query["user_id"]
    status = query.get("status")
    limit = query["limit"]

    # 예시용 더미 로직
    rows = [o for o in fake_db if o["user_id"] == user_id]
    if status:
        rows = [o for o in rows if o["status"] == status]
    rows = rows[:limit]

    return "\n".join([f"- {r['order_id']} ({r['status']}) ${r['amount']}" for r in rows]) or "(no orders)"

async def main():
    # 3) Agent 구성: 도구 + 지시문(중요: '언제 도구를 써야 하는지'를 정책처럼 작성)
    agent = Agent(
        name="Support Orders Agent",
        instructions=(
            "You are a support agent. "
            "If the user asks about orders, you MUST call fetch_recent_orders. "
            "Ask a clarifying question if user_id is missing."
        ),
        tools=[fetch_recent_orders],
    )

    # 4) Tracing으로 한 번의 워크플로우를 묶어 관측 가능하게 만든다 ([openai.github.io](https://openai.github.io/openai-agents-python/tracing/?utm_source=openai))
    with trace("orders_support_workflow"):
        context = {
            "db": [
                {"user_id": "u-1", "order_id": "o-100", "status": "paid", "amount": 39.0},
                {"user_id": "u-1", "order_id": "o-101", "status": "shipped", "amount": 12.5},
                {"user_id": "u-2", "order_id": "o-200", "status": "paid", "amount": 99.9},
            ]
        }

        result = await Runner.run(
            agent,
            "user_id가 u-1인데 최근 주문 2개만 보여줘. shipped만.",
            context=context,  # LLM이 아니라 Tool/Hook에 전달되는 의존성 컨테이너 ([openai.github.io](https://openai.github.io/openai-agents-python/ref/run_context/?utm_source=openai))
        )
        print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())
```

핵심은 “도구가 반환한 텍스트” 자체가 아니라, **도구 호출의 경계면을 스키마로 고정하고(trace로) 관측**한다는 점입니다. Function Calling을 “프롬프트 트릭”이 아니라 **런타임 아키텍처**로 취급해야 재현성이 생깁니다.

---

## ⚡ 실전 팁
1) **`strict: true`(Structured Outputs)로 arguments 품질을 ‘보장’으로 끌어올리기**  
OpenAI는 Function Calling에서 `strict: true`를 통해 스키마 정확 일치를 보장하는 Structured Outputs를 제공합니다. “JSON 파싱 실패 → 재시도”를 설계에서 제거하세요. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api%23.eps?utm_source=openai))  

2) Tool description은 “설명”이 아니라 **정책(Policy)** 으로 쓴다  
- 언제 호출해야 하는지(트리거 조건)  
- 어떤 경우 호출하면 안 되는지(금지 조건)  
- 실패 시 어떻게 보고할지(에러 표준화)  
이 3가지를 도구 설명/agent instructions에 **명시적으로** 넣으면 호출 안정성이 급상승합니다.

3) **루프 제어는 모델에게 맡기지 말고 런타임에서 끊어라**  
OpenAI Agents SDK(JS)는 `toolChoice` 강제/리셋, `toolUseBehavior`로 루프를 제어할 수 있게 설계되어 있습니다. Python에서도 동일한 사고방식(최대 턴, 종료 조건)을 런 정책으로 가져가야 합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))  

4) Tracing에서 민감 데이터가 섞일 수 있다  
Tracing span에는 generation/tool 입출력이 들어갈 수 있어 민감정보가 섞입니다. OpenAI Agents SDK는 “민감 데이터 포함 여부”를 런 설정으로 제어할 수 있음을 문서에서 언급합니다. 운영 환경에선 기본값을 그대로 믿지 말고, 보안 정책(ZDR 포함)과 함께 설계하세요. ([openai.github.io](https://openai.github.io/openai-agents-python/tracing/?utm_source=openai))  

5) 도구 통합이 커지면 MCP 같은 표준을 고려하라  
도구가 20개를 넘어가면, 에이전트 프롬프트/스키마보다 더 무서운 건 **통합 비용**입니다. MCP는 “모델-도구 연결을 표준화”해 N×M 문제를 완화하려는 흐름으로 채택이 확산 중입니다. ([wired.com](https://www.wired.com/story/openai-anthropic-and-block-are-teaming-up-on-ai-agent-standards?utm_source=openai))  

---

## 🚀 마무리
2026년 2월의 “AI Agent tool use/function calling 구현”은 요약하면 이 3줄입니다.

- **Schema-first**: 도구 입력은 JSON Schema로 고정하고(가능하면 `strict: true`) 재시도/파싱을 설계에서 제거 ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api%23.eps?utm_source=openai))  
- **Runtime control**: toolChoice/루프 종료/최대 턴 같은 제어를 모델이 아니라 런타임 정책으로 관리 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))  
- **Observability**: Tracing으로 “왜 그렇게 동작했는지”를 재현 가능하게 만들 것 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tracing/?utm_source=openai))  

다음 학습으로는 (1) OpenAI Agents SDK의 tool/trace/runner 구성, (2) Structured Outputs의 스키마 설계 요령, (3) MCP 기반 도구 레지스트리/권한 모델까지 확장해 보면, “PoC 에이전트”가 아니라 “운영 가능한 에이전트”에 도달합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/?utm_source=openai))