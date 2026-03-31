---
title: "2026년 3월 기준, AI Agent의 “Tool Use + Function Calling”을 제대로 구현하는 법: 스키마·오케스트레이션·관측성까지"
date: 2026-03-31 03:18:32 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-03]
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
2026년 들어 “Agentic workflow”가 실서비스로 더 많이 들어오면서, 단순 챗봇을 넘어 **모델이 외부 시스템을 호출해 실제 일을 끝내는 구조**가 표준이 됐습니다. 문제는 여기서부터입니다.  
Function Calling 자체는 흔해졌지만, 막상 운영 환경에서는 (1) tool schema가 커져 프롬프트가 비대해지고, (2) 모델이 잘못된 인자를 만들거나, (3) tool output이 다음 턴을 오염시키거나(prompt injection), (4) 여러 번의 tool call을 거치며 상태/로그가 엉키는 일이 반복됩니다.

최근 OpenAI는 Responses API + Agents SDK를 “에이전트 플랫폼 빌딩 블록”으로 정리하면서, **tool orchestration / tracing / built-in tools**를 하나의 흐름으로 묶고 있습니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/)) 또한 Agents SDK 쪽에서는 **deferred tool loading(= tool search)** 같은 패턴을 공식 가이드로 내놓으며 “모든 tool schema를 매번 다 보내지 마라”를 명시적으로 권장합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tools/))

---

## 🔧 핵심 개념
### 1) Tool Use / Function Calling의 본질: “비결정적 모델 ↔ 결정적 시스템” 계약
Anthropic이 표현한 것처럼 tools는 **결정적 시스템과 비결정적 agent 사이의 contract**입니다. 모델은 “언제/어떤 도구를/어떤 인자로” 호출할지 추론하지만, 실행은 deterministic하게 이뤄집니다. ([anthropic.com](https://www.anthropic.com/engineering/writing-tools-for-agents))  
따라서 구현의 초점은 “모델이 똑똑하길 기대”가 아니라, **계약을 강제(스키마/검증/권한)하고 실패를 설계(재시도/거절/관측)**하는 데 있습니다.

### 2) 2026년 패턴의 중심: Structured Outputs + JSON Schema 강제
OpenAI 쪽에서는 function calling에 **Structured Outputs(`strict: true`)**를 붙여 “모델이 만든 arguments가 JSON Schema와 정확히 일치”하도록 강제하는 흐름을 강조합니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api%23.eps))  
이게 중요한 이유는:
- “인자 누락/타입 불일치”가 운영 장애로 직결
- tool 호출 전 validation이 가능해지고, 자동 retry 전략을 세우기 쉬움

### 3) Tool schema 폭발 문제: Deferred Tool Loading(= Tool Search)
Tool이 30개, 100개로 늘면 매 요청마다 schema를 전송하는 비용(토큰/지연/혼선)이 커집니다. Agents SDK 문서에는 이를 해결하는 공식 해법으로:
- tool에 `deferLoading: true`를 걸고
- 런타임에 **tool search**로 필요한 tool만 로드
- 관련 tool은 `toolNamespace()`로 묶어 “도메인 단위 검색”을 가능하게
를 제시합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tools/))  
즉 2026년의 “확장 가능한 Agent”는 **(A) tool을 얇게 보내고 (B) 필요할 때만 불러오는 구조**가 기본입니다.

### 4) 오케스트레이션/상태관리: Responses API + Agents SDK의 “item-based” 흐름
OpenAI는 Responses API를 “Chat Completions 단순성 + Assistants 도구사용”을 합친 superset으로 설명하고, 단일 API call에서 다중 tool/다중 턴까지 풀어가는 방향을 강조합니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/))  
Agents SDK의 running 가이드에서는 `previousResponseId`/`conversationId` 기반으로 다음 호출 입력을 준비하는 방식, 그리고 “reasoning item id” 정책 같은 세부까지 다룹니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/running-agents/))  
이 포인트는 한 마디로: **대화 히스토리/도구 호출/중간 결과를 ‘아이템’으로 추적하며, 재현 가능한 실행 단위를 만든다**입니다.

---

## 💻 실전 코드
아래 예시는 **OpenAI Agents SDK(JS)** 스타일로, (1) Zod 기반 schema, (2) `strict`에 준하는 강한 validation 의도, (3) `deferLoading` + `toolSearchTool()`로 tool 폭발을 방지하는 2026년형 패턴을 보여줍니다(실행 환경에 맞춰 API 키/모델명은 조정하세요). Tool search 및 deferred loading 개념은 공식 가이드에 기반합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tools/))

```ts
// language: TypeScript
import { Agent, tool, toolNamespace, toolSearchTool } from "@openai/agents";
import { z } from "zod";

/**
 * 핵심 포인트
 * 1) tool schema를 Zod/JSON Schema로 엄격히 정의한다.
 * 2) deferLoading: true로 "필요할 때만" tool 정의를 모델 컨텍스트에 로드한다.
 * 3) toolSearchTool()을 함께 등록해야, 모델이 런타임에 tool을 탐색/로딩할 수 있다.
 */

// (A) 단일 capability로 독립적인 tool: top-level + deferLoading
const getShippingEta = tool({
  name: "get_shipping_eta",
  description: "Look up a shipment ETA by customer identifier.",
  parameters: z.object({
    customerId: z.string().describe("The customer identifier to look up."),
  }),
  deferLoading: true,
  async execute({ customerId }) {
    // 실제로는 내부 배송 API 호출 + timeout/retry + auth가 들어감
    return { customerId, eta: "2026-03-07", carrier: "Priority Express" };
  },
});

// (B) 관련 tool을 도메인으로 묶기: namespace + deferLoading
const crmTools = toolNamespace({
  name: "crm",
  description: "Customer relationship management tools (profile, orders, etc).",
  tools: [
    tool({
      name: "get_customer_profile",
      description: "Fetch a customer's profile.",
      parameters: z.object({
        customerId: z.string(),
      }),
      deferLoading: true,
      async execute({ customerId }) {
        return { customerId, tier: "gold", region: "US-CA" };
      },
    }),
    tool({
      name: "list_recent_orders",
      description: "List recent orders for a customer.",
      parameters: z.object({
        customerId: z.string(),
        limit: z.number().int().min(1).max(20).default(5),
      }),
      deferLoading: true,
      async execute({ customerId, limit }) {
        return {
          customerId,
          orders: Array.from({ length: limit }, (_, i) => ({
            id: `ORD-${i + 1}`,
            amountUsd: 19.99 + i,
          })),
        };
      },
    }),
  ],
});

async function main() {
  const agent = new Agent({
    name: "ops-agent",
    // 모델 선택은 조직/성능/지원 툴링에 맞춰 조정
    // 중요한 건 "tool search를 지원하는 모델"을 쓰는 것(가이드에 명시). 
    // 실제 모델명은 최신 문서를 확인.
    model: "gpt-5.4", // 예시
    instructions: [
      "You are an operations agent.",
      "Use tools when needed. If you call tools, produce a final user-friendly answer.",
      "When returning structured data, ensure it is valid JSON.",
    ].join("\n"),
    tools: [
      // tool search를 켜야 deferLoading tool을 런타임에 로딩 가능
      toolSearchTool(),
      getShippingEta,
      crmTools,
    ],
  });

  // 사용 예: 고객의 주문/배송을 한 번에 해결
  const result = await agent.run(
    "고객 ID CUST-123의 최근 주문 3개와, 현재 배송 ETA를 같이 알려줘."
  );

  console.log(result.output_text);
}

main().catch(console.error);
```

위 코드가 중요한 이유는 “도구를 많이 붙여도”:
- 매번 전체 schema를 넣지 않아 토큰 낭비를 줄이고 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tools/))
- 관련 tool은 namespace로 묶어 탐색 품질을 올리며 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tools/))
- 결국 **Agent를 기능적으로 확장하면서도(Scale), 비용과 혼선을 제어(Control)**하는 구조로 가기 때문입니다.

---

## ⚡ 실전 팁
1) **Tool output은 ‘신뢰 불가 입력’으로 취급하라 (prompt injection 방어)**
Function calling은 “외부에서 온 문자열”을 다시 모델이 읽는 구조라서, tool output이 다음 행동을 조종할 수 있습니다. OpenAI도 “untrusted tool output이 의도치 않은 행동을 유발할 수 있다”는 류의 리스크를 공개적으로 언급한 바 있습니다. ([openai.com](https://openai.com/index/function-calling-and-other-api-updates/?utm_source=openai))  
실무 체크리스트:
- tool 결과를 그대로 system-level instruction처럼 섞지 말고, “DATA:” 같은 채널로 격리
- HTML/Markdown/로그를 그대로 넣지 말고 sanitize
- “다음 단계에서 수행 가능한 액션”을 allowlist로 제한

2) **Schema는 “작고 구체적으로”, Tool은 “겹치지 않게”**
Anthropic도 tool 목적이 겹치거나 모호하면 모델이 어떤 tool을 써야 할지 헷갈린다고 지적합니다. ([anthropic.com](https://www.anthropic.com/engineering/writing-tools-for-agents))  
실무적으로는:
- `get_customer_profile` vs `fetch_customer_data` 같이 뭉뚱그린 이름 금지
- description에 “언제 쓰면 좋은지/입력 제약”을 명확히
- 동일 도메인 tool은 `toolNamespace()`로 묶어 검색 단위를 줄이기 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tools/))

3) **Deferred tool loading은 “대규모 toolset”에서 사실상 필수**
tool이 10개만 넘어가도 모델 컨텍스트에 매번 넣는 전략은 비용이 튑니다. Agents SDK는 `deferLoading` + `toolSearchTool()` 조합을 공식적으로 안내합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tools/))  
다만 함정:
- tool search는 “지원 모델”이 필요(가이드에 GPT-5.4+ 언급) ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tools/))
- 운영에선 “tool이 로딩되지 않아 호출 실패” 케이스를 대비해 fallback(핵심 tool은 non-deferred로 고정 노출)을 고려

4) **관측성(Tracing)을 제품 기능으로 취급하라**
Agent는 “왜 그 tool을 호출했는지”가 디버깅의 전부입니다. OpenAI가 Responses API + Agents SDK와 함께 tracing/observability를 강조하는 이유가 여기 있습니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/))  
추천 전략:
- tool call 단위로 latency/error/재시도 횟수/인자 validation 실패를 로그화
- “성공률”을 task 단위로 정의(예: 주문 조회 성공 + ETA 조회 성공 + 최종 응답 생성)

---

## 🚀 마무리
2026년 3월의 “Agent tool use + function calling 구현”을 한 문장으로 요약하면: **스키마로 강제하고(Structured Outputs), tool은 필요할 때만 로드하며(deferLoading/tool search), 실행 전체를 추적 가능하게 만든다(tracing/item-based orchestration)** 입니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api%23.eps))

다음 학습 추천:
- OpenAI Responses API / Agents SDK의 tool, running, tracing 문서 흐름을 한 번에 읽고, “단일 run에서 다중 tool 호출”을 재현 가능한 상태머신으로 모델링하기 ([openai.com](https://openai.com/index/new-tools-for-building-agents/))
- “tool output prompt injection” 방어 패턴을 팀 코딩 가이드로 고정하기 ([openai.com](https://openai.com/index/function-calling-and-other-api-updates/?utm_source=openai))