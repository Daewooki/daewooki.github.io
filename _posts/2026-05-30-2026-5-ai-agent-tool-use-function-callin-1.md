---
title: "2026년 5월 기준: AI Agent “Tool Use + Function Calling”을 프로덕션에 넣는 구현 패턴 (Responses API · Agents SDK · MCP)"
date: 2026-05-30 04:05:24 +0900
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
2026년의 agent 개발에서 가장 자주 터지는 문제는 “모델이 똑똑하냐”가 아니라 **도구 호출(tool call)이 프로덕션 규칙을 깨는 순간**입니다. 예를 들어:

- DB 조회를 해야 하는데 바로 “요약”부터 해버림 (순서 문제)
- 결제/예약 같은 **부작용(side effect)** 툴을 너무 일찍 호출함 (안전성 문제)
- 툴 출력이 길어져 컨텍스트를 잡아먹고 비용이 폭발 (비용/성능 문제)
- 에러가 나면 모델이 “추측으로 메꾸기”를 함 (신뢰성 문제)

2026년 5월 기준 OpenAI 쪽은 **Responses API + Agents SDK**를 장기 방향으로 밀고 있고, tool use는 JSON Schema 기반 function calling(Structured Outputs)과 **MCP(Model Context Protocol)** 기반 “표준화된 도구 연결”로 정리되는 흐름입니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai)) 또한 multi-step agent의 왕복 호출로 생기는 지연을 줄이기 위해 WebSocket 기반 실행 모드도 공개적으로 강조되고요. ([openai.com](https://openai.com/index/speeding-up-agentic-workflows-with-websockets/?utm_source=openai))

**언제 쓰면 좋은가**
- “검색/조회 → 정합성 검증 → 작성/실행”처럼 **여러 시스템을 순차적으로 호출**해야 하는 워크플로우
- 사람이 매번 클릭/복붙하기엔 비싼 운영 업무(리서치, 티켓 분류, 배포 전 체크리스트 등)
- 호출 이력/근거가 남아야 하는 업무(트레이싱, 감사 로그)

**언제 쓰면 안 좋은가**
- 단일 API 한 번 호출로 끝나는 작업(굳이 agent loop를 만들면 오히려 불안정/비용 증가)
- “즉시성”이 핵심인데(예: 음성 인터랙션) tool 호출이 3~5단계 이상 필요한 경우: 설계부터 **latency budget**이 맞는지 먼저 계산해야 합니다. (이 경우 WebSocket/비동기/추측 호출 같은 최적화가 전제) ([infoq.com](https://www.infoq.com/news/2026/05/openai-websocket-responses-api/?utm_source=openai))
- 부작용 툴(결제/메일 발송/권한 변경)을 모델에게 **무제한 위임**해야만 성립하는 제품

---

## 🔧 핵심 개념
### 1) Function Calling의 “2026년형” 정의
- **모델 출력이 텍스트가 아니라 “행동”으로 확장**되는 인터페이스
- 핵심은 “도구 목록(tools) + JSON Schema”로 모델이 `function_call`을 만들고, 런타임이 실행한 뒤 `function_call_output`을 다시 모델에 피드백하는 **폐루프(loop)** 입니다.
- OpenAI Help Center는 `strict: true`를 통한 Structured Outputs(스키마 일치 강제)를 강조합니다. 즉, “대충 JSON 비슷하게”가 아니라 **계약 기반 호출**로 가는 방향입니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))

### 2) 내부 작동 흐름(중요: “메시지”가 아니라 “아이템”)
Responses API 계열에서 실제로는 다음과 같은 이벤트/아이템 흐름을 갖는 것이 포인트입니다:

1. 모델이 생각/출력 중 `function_call`(또는 hosted tool call)을 생성
2. 클라이언트(또는 Agents SDK Runner)가 해당 tool을 실행
3. 실행 결과를 `function_call_output`으로 다시 넣음
4. 모델이 다음 step 결정(추가 tool call or 최종 답)

이 “아이템 스트림” 구조가 **로그/관측/재현성**에 유리합니다(어떤 단계에서 무슨 도구를 왜 호출했는지). ([aiwiki.ai](https://aiwiki.ai/wiki/openai_responses_api?utm_source=openai))

### 3) MCP가 끼어들면서 달라진 점: “도구 연결”의 표준화
2026년에는 function calling이 단순히 “내가 만든 함수 몇 개”가 아니라, **원격 MCP 서버가 제공하는 도구들까지** 한 덩어리로 붙습니다.

- MCP는 “도구와 컨텍스트를 LLM에 제공하는 방법”을 표준화하고, OpenAI Agents SDK 문서에서도 MCP 도구 연결을 1급 시민으로 다룹니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/mcp/?utm_source=openai))
- 다만 MCP 확산과 함께 **보안 이슈(RCE 등)** 도 같이 뉴스로 올라왔습니다. 즉 “표준화 = 안전”이 아니라, **실행 경계/권한/승인/격리**를 제품이 책임져야 합니다. ([tomshardware.com](https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropics-model-context-protocol-has-critical-security-flaw-exposed?utm_source=openai))

### 4) 다른 접근과의 차이점: “루프 기반 tool calling” vs “워크플로우/그래프”
- 가벼운 제품은 여전히 **while-loop + tool dispatcher**가 제일 디버깅하기 쉽습니다.
- LangGraph 같은 그래프 기반은 “병렬/상태/재시도/분기”가 복잡해질 때 값이 커집니다. (그 전엔 오히려 보일러플레이트가 늘 수 있음) ([pyinns.com](https://www.pyinns.com/python/data-sciences/langgraph-multi-agent-patterns-2026-supervisor-hierarchical?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: **B2B SaaS 운영팀용 “장애 요약 + 영향도 + 액션 아이템” 에이전트**
- 입력: Slack/알림에서 온 incident 텍스트
- 도구:
  1) `search_incidents` (최근 유사 장애 조회: 내부 Elasticsearch/DB)
  2) `fetch_runbook` (서비스별 Runbook 문서 조회)
  3) `create_ticket` (Jira/Linear 생성 — *side effect*)
- 요구사항:
  - 티켓 생성은 **승인 게이트**를 통과해야만 실행
  - tool args는 **strict schema**로 강제
  - 모든 tool call은 tracing/logging

아래 예시는 “Agents SDK를 쓰지 않고도” 이해 가능한 형태로, **Responses API 스타일의 tool loop**를 TypeScript로 구현한 뒤, 마지막에 “승인 게이트”를 붙입니다. (실서비스에선 여기서 MCP 도구로도 교체 가능)

### 0) 의존성/환경
```bash
npm i openai zod
export OPENAI_API_KEY="..."
```

### 1) Tool 스키마(엄격한 계약) + Dispatcher
```typescript
import OpenAI from "openai";
import { z } from "zod";

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

/** --- Tool schemas (strict JSON schema에 대응하기 쉽게 Zod로 검증) --- */
const SearchIncidentsArgs = z.object({
  query: z.string().min(5),
  timeRangeHours: z.number().int().min(1).max(720).default(168),
});

const FetchRunbookArgs = z.object({
  service: z.string().min(2),
});

const CreateTicketArgs = z.object({
  projectKey: z.string().min(2),
  title: z.string().min(10),
  severity: z.enum(["SEV1", "SEV2", "SEV3"]),
  descriptionMarkdown: z.string().min(50),
  tags: z.array(z.string()).max(10).default([]),
});

/** --- 실제 프로덕션에서는 DB/ES/Jira SDK 연결 --- */
async function searchIncidents(args: z.infer<typeof SearchIncidentsArgs>) {
  // 예: ES 쿼리 후 top-k 요약해서 반환(원문 로그 전부를 LLM에 주지 말 것!)
  return {
    hits: [
      { id: "INC-18421", when: "2026-05-12T03:11:00Z", summary: "auth token rotation 이후 401 spike" },
      { id: "INC-17702", when: "2026-04-29T18:40:00Z", summary: "redis eviction으로 session drop" },
    ],
    note: "요약만 제공(원문 로그는 별도 링크).",
  };
}

async function fetchRunbook(args: z.infer<typeof FetchRunbookArgs>) {
  return {
    service: args.service,
    steps: [
      "Check error budget burn rate (SLO dashboard).",
      "Inspect deploys in last 2h; rollback if correlated.",
      "If auth-related: validate JWKS cache + token issuer status.",
    ],
  };
}

async function createTicket(args: z.infer<typeof CreateTicketArgs>) {
  // side effect: 실제로는 Jira/Linear 생성
  return {
    ticketKey: `${args.projectKey}-1024`,
    url: `https://tickets.example.com/browse/${args.projectKey}-1024`,
  };
}

/** --- tool registry --- */
type ToolName = "search_incidents" | "fetch_runbook" | "create_ticket";

const tools = [
  {
    type: "function",
    function: {
      name: "search_incidents",
      description: "Search similar incidents from internal incident DB and return short summaries.",
      // OpenAI Structured Outputs에 맞춘 JSON Schema를 붙이는 영역(여기서는 개념적으로 표시)
      parameters: {
        type: "object",
        properties: {
          query: { type: "string" },
          timeRangeHours: { type: "integer", minimum: 1, maximum: 720 },
        },
        required: ["query"],
        additionalProperties: false,
      },
      strict: true,
    },
  },
  {
    type: "function",
    function: {
      name: "fetch_runbook",
      description: "Fetch the runbook steps for a given service.",
      parameters: {
        type: "object",
        properties: { service: { type: "string" } },
        required: ["service"],
        additionalProperties: false,
      },
      strict: true,
    },
  },
  {
    type: "function",
    function: {
      name: "create_ticket",
      description: "Create a ticket in the tracking system. SIDE EFFECT: requires approval.",
      parameters: {
        type: "object",
        properties: {
          projectKey: { type: "string" },
          title: { type: "string" },
          severity: { type: "string", enum: ["SEV1", "SEV2", "SEV3"] },
          descriptionMarkdown: { type: "string" },
          tags: { type: "array", items: { type: "string" } },
        },
        required: ["projectKey", "title", "severity", "descriptionMarkdown"],
        additionalProperties: false,
      },
      strict: true,
    },
  },
] as const;

/** --- dispatcher with approval gate --- */
async function runTool(name: ToolName, rawArgs: unknown, ctx: { approvedTicket: boolean }) {
  switch (name) {
    case "search_incidents": {
      const args = SearchIncidentsArgs.parse(rawArgs);
      return await searchIncidents(args);
    }
    case "fetch_runbook": {
      const args = FetchRunbookArgs.parse(rawArgs);
      return await fetchRunbook(args);
    }
    case "create_ticket": {
      if (!ctx.approvedTicket) {
        return { blocked: true, reason: "Ticket creation requires human approval." };
      }
      const args = CreateTicketArgs.parse(rawArgs);
      return await createTicket(args);
    }
  }
}
```

### 2) Agent Loop(핵심): “tool call → output → 다음 step”
```typescript
type LoopOptions = {
  approvedTicket: boolean;   // human-in-the-loop
  maxSteps: number;
};

export async function triageIncident(incidentText: string, opts: LoopOptions) {
  const system = `
You are an SRE triage agent.
Goal: summarize incident, assess likely impact, propose next actions.
Rules:
- Prefer tools over guessing.
- Never create a ticket unless necessary AND tool output indicates clear next step.
- If create_ticket is needed, call it and accept it may be blocked.
- Keep outputs concise; do not paste large logs.
`;

  // Responses API 스타일을 흉내: 실제 SDK/HTTP에서 response.output item을 순회하는 느낌으로 구현
  let input: any[] = [
    { role: "system", content: system },
    { role: "user", content: incidentText },
  ];

  const ctx = { approvedTicket: opts.approvedTicket };

  for (let step = 1; step <= opts.maxSteps; step++) {
    const resp = await client.responses.create({
      model: "gpt-5",           // 예시
      input,
      tools: tools as any,
    });

    // 1) 텍스트 출력 누적
    const text = resp.output_text?.trim();
    if (text) {
      // 모델이 최종 답을 내면 종료
      return { done: true, step, text, raw: resp };
    }

    // 2) tool call 찾기
    const toolCalls = resp.output?.filter((it: any) => it.type === "function_call") ?? [];
    if (toolCalls.length === 0) {
      return { done: false, step, text: "", raw: resp, error: "No text and no tool calls." };
    }

    // 3) tool 실행하고 output을 다시 input에 붙여 다음 턴으로
    for (const call of toolCalls) {
      const name = call.name as ToolName;
      const args = call.arguments ? JSON.parse(call.arguments) : {};
      const result = await runTool(name, args, ctx);

      input.push({
        role: "assistant",
        content: [
          // Responses API에서 tool output을 넣는 구조를 단순화한 표현
          { type: "function_call_output", call_id: call.call_id, output: JSON.stringify(result) },
        ],
      });
    }
  }

  return { done: false, error: "maxSteps exceeded" };
}
```

### 3) 실행 예시(승인 전/후)
```typescript
const incident = `
[ALERT] 5xx spike on api-gateway
- started: 2026-05-30 01:12 UTC
- correlation: deploy auth-service v2.18.4 10 minutes earlier
- symptoms: /v1/orders returns 401 then retries lead to 503
What happened and what should we do next?
`;

console.log(await triageIncident(incident, { approvedTicket: false, maxSteps: 6 }));
```

**예상 출력(요지)**
- 유사 장애(INC-18421)에서 “token rotation/JWKS cache” 이슈가 있었음을 언급
- runbook 기반으로 “deploy 롤백/키 캐시 확인/SLO burn rate 확인” 액션 제시
- 필요시 티켓 생성 시도 → 승인 없으면 blocked로 반환 → 모델이 “승인 요청 문구 + 생성에 필요한 필드”를 정리

이 구현의 핵심은:
- tool args를 **스키마로 검증(Zod) + strict schema**로 모델 출력부터 강제 ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))
- side effect 툴은 **승인 플래그(또는 정책 엔진)** 로 런타임에서 차단
- tool output은 “필요한 요약만” 반환해 컨텍스트/비용 폭주를 막음

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “도구는 기능이 아니라 계약”으로 설계하라
- tool signature가 애매하면 모델이 **순서를 잘못 호출**했을 때 조용히 망가집니다.
- 파라미터에 “이전 단계 산출물 ID(required)”를 넣어 **잘못된 호출 순서가 스키마에서 실패**하게 만드는 게 효과적입니다(예: `prepare_booking` 결과의 `bundleId` 없으면 `confirm_booking` 불가). Reddit 실전 사례에서도 “순서가 틀리면 graceful fail”을 강조합니다. ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1ths0k2/building_an_ai_agent_with_openai_tool_use/?utm_source=openai))

### Best Practice 2) “승인/권한/스코프”는 모델이 아니라 Dispatcher에서 강제
- create/update/delete, 결제, 메일 발송 같은 툴은 **fail closed**가 기본값이어야 합니다.
- MCP 도입이 늘면서 “연결이 쉬워진 만큼” 실행 경계가 더 중요해졌고, MCP 관련 보안 이슈도 지속적으로 보도됩니다. ([tomshardware.com](https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropics-model-context-protocol-has-critical-security-flaw-exposed?utm_source=openai))  
- 결론: 모델 프롬프트에 “하지 마”라고 쓰는 건 정책이 아닙니다. **코드로 막으세요.**

### Best Practice 3) 관측 가능성(Tracing)을 “기능”으로 취급
- tool call 단위로 span을 남기고, 어떤 tool이 비용/실패를 유발하는지 봐야 합니다.
- OpenAI Agents SDK는 tool call/handoff를 span으로 감싸는 tracing 문서를 제공합니다. ([github.com](https://github.com/openai/openai-agents-python/blob/main/docs/tracing.md?utm_source=openai))  
- 운영에선 “에이전트 정확도”보다 **어떤 tool이 장애를 만드는지**가 더 중요합니다.

### 흔한 함정/안티패턴
- **툴 출력 원문을 통째로 모델에 재주입**: 컨텍스트/비용 폭발 + 정보 누출 위험  
  → “요약+링크+핵심 필드만”을 원칙으로
- **tool description에 정책을 길게 적기**: 실제 실행 정책은 dispatcher가 가져야 하고, description은 모델 라우팅 품질에만 집중
- **루프 무한 실행**: `maxSteps`, 예산(budget), 타임아웃, “StopAtTools(특정 tool 호출 시 정지)” 같은 중단 장치를 두세요(Agents SDK에도 유사 컨셉이 문서화됨). ([openai.github.io](https://openai.github.io/openai-agents-python/ref/sandbox/sandbox_agent/?utm_source=openai))

### 비용/성능/안정성 트레이드오프(2026년 포인트)
- multi-step agent는 HTTP 왕복이 누적되면 체감 latency가 커집니다. OpenAI는 WebSocket 기반 Responses 실행 모드를 성능 개선 축으로 내세웁니다. ([openai.com](https://openai.com/index/speeding-up-agentic-workflows-with-websockets/?utm_source=openai))  
- 반대로 “한 번에 다 계획해서(tool blueprint) 실행”은 빠를 수 있지만, 중간 실패 복구/승인/조건 분기가 어려워집니다. 즉:
  - **인터랙티브/승인 필요**: 짧은 step loop + 스트리밍/웹소켓
  - **배치/ETL형**: 선언적 workflow(그래프/블루프린트) 고려

---

## 🚀 마무리
정리하면, 2026년 5월의 agent tool use 구현은 “function calling 잘 쓰기”를 넘어 **실행 레이어를 설계하는 문제**입니다.

- 도입 추천 기준
  1) 작업이 “조회→검증→작성/실행”으로 **2단계 이상**인가?
  2) side effect가 있는가? 있다면 **승인/권한/스코프**를 코드로 강제할 수 있는가?
  3) tool 출력의 크기/빈도에 대해 **비용 상한**을 설계했는가?
  4) tool call 단위 tracing/로그가 있는가?

다음 학습 추천(실무 순서)
1) Structured Outputs(`strict: true`)로 **스키마 계약**을 먼저 고정 ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))  
2) Responses API의 아이템/툴 호출 흐름을 이해하고, 간단한 loop를 직접 구현 ([aiwiki.ai](https://aiwiki.ai/wiki/openai_responses_api?utm_source=openai))  
3) Agents SDK의 tracing/handoff/sandbox를 붙여 “운영 가능한 런타임”으로 확장 ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/?utm_source=openai))  
4) 도구 확장/상호운용이 필요해지면 MCP로 표준화하되, 보안 경계부터 설계 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/mcp/?utm_source=openai))

원하면 위 예제를 **(1) MCP 서버 도구로 교체**, **(2) WebSocket Responses로 스트리밍/저지연화**, **(3) 승인 게이트를 정책 엔진(OPA 등)로 분리**하는 형태로 2,000~3,000자 추가 확장 버전도 작성해드릴게요.