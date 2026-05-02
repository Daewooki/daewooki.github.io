---
title: "Supervisor/Worker 패턴으로 멀티 에이전트 오케스트레이션 “운영 가능”하게 만들기 (2026년 5월 기준)"
date: 2026-05-02 03:35:44 +0900
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

멀티 에이전트 오케스트레이션을 실제 서비스에 붙이면, 대부분 “에이전트가 똑똑한가”보다 **누가 언제 무엇을 시키고(라우팅), 결과를 어떻게 합치며(합성), 실패를 어떻게 복구하는가(내구성)**에서 망합니다. 특히 작업이 길어질수록 (RAG + 외부 API + 코드 실행 + 문서 편집 등) 단일 에이전트는 **컨텍스트/권한/도구 범위**가 비대해지고, 디버깅도 불가능해집니다.

이때 2026년에도 가장 실용적으로 살아남는 구조가 **Supervisor/Worker**(또는 manager/specialists, hierarchical orchestration) 패턴입니다. 상위 Supervisor가 작업을 분해/할당하고, 하위 Worker들이 제한된 책임 범위에서 결과를 내며, Supervisor가 최종 응답/의사결정을 “소유”합니다. LangGraph의 supervisor 아키텍처나 OpenAI Agents SDK의 “Agents as tools”/handoffs가 사실상 같은 문제공간을 겨냥합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))

**언제 쓰면 좋은가**
- 한 요청이 “조사→판단→작성→검증”처럼 **단계가 명확**하거나, 여러 전문성이 필요한 경우(예: 고객지원, 주문/추천/트러블슈팅 분리) ([d1.awsstatic.com](https://d1.awsstatic.com/onedam/marketing-channels/website/aws/en_US/solutions/approved/documents/architecture-diagrams/multi-agent-orchestration-on-aws.pdf?refid=sl_card))
- 안전/컴플라이언스/가드레일을 한 곳(Supervisor)에 모아 **정책 집행 지점**을 만들고 싶은 경우 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))
- 워커를 병렬로 돌려 레이턴시를 줄이되, 결과 통합은 중앙에서 하고 싶은 경우(예: 다중 소스 조사) ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))

**언제 쓰면 안 되는가**
- 작업이 사실상 단일 함수 호출 수준(간단한 분류/요약/폼 채우기)이라면 오케스트레이션 오버헤드가 더 큽니다.
- 워커 간 상호작용이 잦고 자유대화에 가깝다면(“회의형 swarm”) Supervisor가 병목/혼란의 근원이 되기 쉽습니다. 이 경우는 역할/메시지 스키마/턴 제한을 먼저 설계하지 않으면 품질이 급락합니다(“대화가 길어질수록 망가짐”). ([augmentcode.com](https://www.augmentcode.com/guides/swarm-vs-supervisor?utm_source=openai))

---

## 🔧 핵심 개념

### 1) 개념 정의 (실무 관점)
- **Supervisor**: “다음에 누구를 실행할지”를 결정하고, 워커 출력물을 **검증/병합**하여 최종 결과를 소유하는 컨트롤 플레인(control plane).
- **Worker**: 특정 도메인/툴셋에 최적화된 실행 유닛. 입력/출력 계약(contract)이 명확해야 하며, 가능하면 **구조화된 출력(typed output)**을 반환합니다.
- **Shared State**: 멀티 에이전트의 진짜 난제는 “지능”이 아니라 **상태 일관성**입니다. Supervisor/Worker는 상태를 중앙에서 관리(또는 체크포인트)해 워커 간 충돌을 줄입니다. ([d1.awsstatic.com](https://d1.awsstatic.com/onedam/marketing-channels/website/aws/en_US/solutions/approved/documents/architecture-diagrams/multi-agent-orchestration-on-aws.pdf?refid=sl_card))

### 2) 내부 작동 방식(흐름)
운영 가능한 Supervisor/Worker는 보통 아래 루프를 갖습니다.

1. **Intent/Plan 단계**: Supervisor가 요청을 보고 “필요한 워커 목록 + 순서/병렬 여부 + 예산(시간/토큰)”을 결정  
2. **Dispatch 단계**: 워커 실행(일부는 병렬 fan-out). 이때 워커에게는 *전체 대화*가 아니라 **필요한 컨텍스트만** 전달(컨텍스트 슬라이싱)  
3. **Reduce 단계**: 워커 결과를 Supervisor가 수집/정규화/중복 제거/충돌 해결  
4. **Decide 단계**: (a) 충분하면 최종 응답 생성, (b) 부족하면 추가 워커 호출/재시도, (c) 예산 초과면 degrade(단일 에이전트/요약 모드로 다운그레이드)

OpenAI Agents SDK 문서가 말하는 “Agents as tools(매니저가 전문 에이전트를 tool처럼 호출)”과 “handoffs(라우팅 후 전문 에이전트가 다음 턴을 소유)”는 이 루프를 구현하는 서로 다른 선택지입니다. 실무에서는 둘을 섞어 씁니다(초기 triage는 handoff, 세부 작업은 agents-as-tools). ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))

또한 2026년 관점에서 중요한 변화는 “오케스트레이션 = 프롬프트”가 아니라, **내구성(durable execution)과 샌드박스 격리**가 점점 표준화된다는 점입니다. OpenAI는 Agents SDK에서 스냅샷/rehydration, 샌드박스 인지 오케스트레이션을 강조합니다. 즉 Supervisor/Worker는 이제 “아키텍처 패턴”을 넘어 **실행 인프라 패턴**으로 봐야 합니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk))

### 3) 다른 접근과의 차이점
- **Prompt chaining(단일 프롬프트에 단계 지시)**: 구현은 쉽지만 관측/재시도/부분 실패 복구가 어렵고, 도구 권한이 한 덩어리로 커져 위험합니다.
- **Swarm(동등 에이전트 자유 상호작용)**: 창의적 협업엔 좋지만, 제품/운영에선 “책임 소재”와 “상태 일관성”을 잃기 쉽습니다. ([augmentcode.com](https://www.augmentcode.com/guides/swarm-vs-supervisor?utm_source=openai))
- **Supervisor/Worker**: 중앙 통제와 전문성 분리로 운영성을 얻는 대신, Supervisor가 병목이 되기 쉬우며 “라우팅 품질”과 “계약 설계”가 성패를 좌우합니다.

---

## 💻 실전 코드

아래 예제는 **“B2B SaaS 장애 티켓 자동 처리”** 시나리오입니다.  
요구사항은 현실적으로 다음을 포함합니다.

- 티켓을 읽고: (1) 즉시 답변 가능한지, (2) 로그 분석이 필요한지, (3) 계정/과금 이슈인지 분기
- 워커는 각각 **툴/권한이 다름**(예: Billing은 결제 API만, SRE는 로그만)
- Supervisor는 결과를 합쳐 “최종 답변 + 사용자에게 요청할 추가 정보 + 내부 실행 액션”을 생성
- 워커 출력은 **구조화(typed JSON)**로 강제해 reduce가 가능해야 함

여기서는 OpenAI Agents SDK 스타일(“agents as tools + 코드 오케스트레이션”)로 작성합니다. 멀티 에이전트 오케스트레이션에서 “LLM이 라우팅까지 전부 결정”하게 두면 비결정성이 커져 운영이 힘들기 때문에, **라우팅은 structured output으로 받아 코드에서 검증**하는 쪽이 실무적으로 유리합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))

### 0) 설치/환경
```bash
npm init -y
npm i @openai/agents zod
export OPENAI_API_KEY="..."
```

### 1) 타입 계약 정의 + 워커 구현
```typescript
// file: triage-supervisor.ts
import { Agent, Runner } from "@openai/agents";
import { z } from "zod";

// ---- 1) Worker output contracts (핵심: reduce 가능한 형태) ----
const SreResult = z.object({
  suspected_root_cause: z.string(),
  evidence: z.array(z.string()),
  next_actions: z.array(z.string()),
  confidence: z.number().min(0).max(1),
});

const BillingResult = z.object({
  account_issue: z.boolean(),
  summary: z.string(),
  required_customer_inputs: z.array(z.string()),
  confidence: z.number().min(0).max(1),
});

const SupportDraft = z.object({
  customer_message: z.string(),
  internal_notes: z.array(z.string()),
});

// ---- 2) Workers (각자 책임/툴 범위가 좁아야 함) ----
const sreWorker = new Agent({
  name: "sre_worker",
  instructions: [
    "You are an SRE specialist.",
    "Analyze the incident based on provided logs/snippets only.",
    "Return JSON that matches the SreResult schema.",
    "If evidence is insufficient, say so explicitly and propose next_actions to gather signals.",
  ].join("\n"),
  outputType: SreResult,
});

const billingWorker = new Agent({
  name: "billing_worker",
  instructions: [
    "You are a billing specialist for a B2B SaaS.",
    "Decide if this is likely billing/account-related based on the ticket text.",
    "Return JSON that matches the BillingResult schema.",
    "Do NOT guess payment provider internals; ask for exact invoice id / workspace id if needed.",
  ].join("\n"),
  outputType: BillingResult,
});

const writerWorker = new Agent({
  name: "writer_worker",
  instructions: [
    "You write a customer-facing reply and internal notes.",
    "Use inputs: ticket, SRE findings, billing findings.",
    "Be concise, actionable, and include next steps + what we need from customer.",
    "Return JSON matching SupportDraft.",
  ].join("\n"),
  outputType: SupportDraft,
});

// ---- 3) Supervisor routing contract ----
const RoutePlan = z.object({
  // 병렬로 돌릴 워커 목록 (운영에선 예산/timeout도 같이 둠)
  run_sre: z.boolean(),
  run_billing: z.boolean(),
  rationale: z.string(),
});

const supervisor = new Agent({
  name: "supervisor",
  instructions: [
    "You are the supervisor for customer support automation.",
    "Your job: decide which specialists to consult and synthesize a final answer.",
    "First produce a routing plan as JSON (RoutePlan).",
    "Think about cost/latency: don't call workers unnecessarily.",
  ].join("\n"),
  outputType: RoutePlan,
});

async function main() {
  const runner = new Runner();

  // 현실적인 티켓 예시(장애/과금 경계가 애매한 케이스)
  const ticket = `
Workspace: acme-prod
Issue: Since 09:12 UTC our API calls intermittently fail with 502.
We also saw a "payment required" message once in the dashboard.
Recent change: enabled SSO yesterday.
Logs snippet:
- GET /v1/orders -> 502 (request_id: r-81f2)
- upstream: gateway timeout
Please help, this is impacting production.
`;

  // ---- Step A) Supervisor가 라우팅 결정(구조화 출력) ----
  const plan = await runner.run(supervisor, ticket);
  // plan.output: { run_sre, run_billing, rationale }

  // ---- Step B) 필요 워커를 병렬 실행 ----
  const [sre, billing] = await Promise.all([
    plan.output.run_sre ? runner.run(sreWorker, ticket) : Promise.resolve(null),
    plan.output.run_billing ? runner.run(billingWorker, ticket) : Promise.resolve(null),
  ]);

  // ---- Step C) Writer가 최종 고객 메시지/내부노트 작성 ----
  const synthesisInput = {
    ticket,
    routing_rationale: plan.output.rationale,
    sre: sre?.output ?? null,
    billing: billing?.output ?? null,
  };

  const draft = await runner.run(writerWorker, JSON.stringify(synthesisInput, null, 2));

  console.log("=== ROUTE PLAN ===");
  console.log(plan.output);
  console.log("\n=== CUSTOMER MESSAGE ===");
  console.log(draft.output.customer_message);
  console.log("\n=== INTERNAL NOTES ===");
  console.log(draft.output.internal_notes.join("\n- "));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

### 2) 예상 출력(요약)
- ROUTE PLAN: `run_sre=true`, `run_billing=true` (502 + payment required 단서 혼재)
- SRE 결과: “gateway timeout/업스트림 지연 의심”, “추가로 latency/region/health 체크 필요”
- Billing 결과: “계정 이슈 가능성 낮지만, ‘payment required’ 단서로 invoice/workspace 확인 요청”
- 고객 메시지: “지금 확인 중이며, request_id 제공 요청 + 특정 시간대/리전/재현조건 + 결제/워크스페이스 ID 확인” 등

이 구조의 포인트는 **Supervisor가 최종 텍스트를 직접 쓰지 않는 것**입니다. Supervisor는 라우팅/정책/예산/가드레일을 소유하고, 최종 작성은 writerWorker가 담당해 “역할 분리”를 유지합니다. 또한 SDK 문서가 강조하듯, 병렬화는 LLM 기능이 아니라 코드(예: `Promise.all`)로 하는 편이 예측 가능합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))

---

## ⚡ 실전 팁 & 함정

### Best Practice (운영성에 직결)
1) **Worker 출력은 무조건 typed JSON으로 고정**
- reduce(병합/충돌해결) 단계는 “텍스트를 다시 읽는 LLM”에 맡기면 비용/오류가 폭발합니다.
- structured outputs로 “검증 가능한 중간 산출물”을 만들면, 재시도/캐시/회귀 테스트가 쉬워집니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))

2) **Supervisor가 ‘종료 조건’을 텍스트로 추론하게 두지 말 것**
- “finished인지 LLM이 알아서 판단”은 매우 취약합니다(조금만 프롬프트가 흔들려도 무한루프/조기종료).
- 대신 `budget_remaining`, `max_turns`, `required_fields` 같은 **명시적 stop condition**을 state로 둡니다(프레임워크가 달라도 동일). ([abstractalgorithms.dev](https://www.abstractalgorithms.dev/langgraph-multi-agent-supervisor-pattern?utm_source=openai))

3) **내구성(durable execution)과 격리(sandbox)를 전제로 설계**
- 멀티 에이전트는 실행 시간이 길고 외부 의존성이 많아 “중간 실패”가 정상 케이스입니다.
- 스냅샷/rehydration, 샌드박스 분리 같은 실행 인프라 지원을 적극 활용/모방하세요(체크포인트 저장소, idempotent tool call, 재실행 전략). ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk))

### 흔한 함정/안티패턴
- **모든 워커에 모든 컨텍스트를 전달**: 컨텍스트 비용 증가 + 프롬프트 간섭 + 정책 누수(권한이 넓어짐)
- **Supervisor가 라우팅도 하고 최종 글도 쓰는 “신(神) 에이전트”**: 책임이 섞여 디버깅 불가, 품질 변동이 커짐
- **병렬 워커 결과를 그대로 concat**: 중복/충돌/근거 부족이 그대로 사용자 응답에 섞임 → 반드시 reduce 규칙(우선순위/신뢰도/충돌 해결)을 코드로 두세요

### 비용/성능/안정성 트레이드오프
- Supervisor/Worker는 단일 에이전트보다 **토큰/호출 수가 늘어나는 구조**입니다. 다만 고가치/복잡 작업에서는 전문성 분리로 성공률이 올라 비용을 정당화할 수 있다는 관점이 정리돼 있습니다. ([resources.anthropic.com](https://resources.anthropic.com/hubfs/Building%20Effective%20AI%20Agents-%20Architecture%20Patterns%20and%20Implementation%20Frameworks.pdf))
- 레이턴시는 (1) 병렬화, (2) 라우팅의 과감한 스킵(불필요 워커 호출 금지), (3) 캐시(티켓 유형별 템플릿/결과 재사용)로 줄입니다.
- 안정성은 “LLM 오케스트레이션”보다 “코드 오케스트레이션” 비중을 늘릴수록 올라갑니다(결정성/관측성). ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))

---

## 🚀 마무리

Supervisor/Worker 패턴은 2026년 5월 기준으로도 멀티 에이전트를 **프로덕션에서 통제 가능하게** 만드는 가장 현실적인 설계입니다. 핵심은 “에이전트를 여러 개 둔다”가 아니라:

- 라우팅/종료/예산을 **명시적으로 모델링**하고
- 워커 산출물을 **구조화(typed)**하여 reduce 가능하게 만들고
- 실패/재시도/체크포인트/격리를 포함한 **실행 내구성**을 아키텍처의 일부로 취급하는 것

**도입 판단 기준**
- “한 번의 호출로 끝나지 않는 업무 흐름”이며, 실패 비용이 크고(지원/운영/리스크), 관측/재현/감사가 필요하다 → Supervisor/Worker가 유리
- 요청당 작업이 단순하고 결정적이며, 오버헤드가 아깝다 → 단일 에이전트 + structured output + 코드 후처리로 충분

**다음 학습 추천**
- OpenAI Agents SDK의 multi-agent 가이드에서 “Agents as tools vs handoffs”를 먼저 비교하고, 내 서비스의 “소유권(누가 다음 턴을 갖는가)” 요구에 맞춰 선택하세요. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/))
- LangGraph 기반이라면 체크포인트/상태 모델링을 먼저 설계한 뒤 supervisor를 붙이는 순서가 운영 난이도를 크게 낮춥니다(AWS 참조 아키텍처가 사실상 그 방향을 보여줍니다). ([d1.awsstatic.com](https://d1.awsstatic.com/onedam/marketing-channels/website/aws/en_US/solutions/approved/documents/architecture-diagrams/multi-agent-orchestration-on-aws.pdf?refid=sl_card))