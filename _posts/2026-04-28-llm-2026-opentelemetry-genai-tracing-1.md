---
title: "LLM 앱은 왜 “느린지”가 아니라 “왜 그런 선택을 했는지”를 추적해야 한다: 2026년형 OpenTelemetry GenAI Tracing 심층 적용기"
date: 2026-04-28 03:52:55 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-04]
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
LLM/Agent 앱을 운영해보면 전통적인 APM(HTTP latency, error rate, DB time)만으로는 장애의 **원인**에 닿기 어렵습니다. 많은 실패가 “500 에러”가 아니라 **의미적 실패(semantic failure)** 로 나타나기 때문입니다. 예를 들어:
- Retrieval이 엉뚱한 문서를 가져와서 답이 틀렸는데 요청은 200 OK
- Tool call이 루프에 빠져 token 비용이 폭증
- 같은 입력인데 모델이 다른 경로를 타서 p95가 튐(비결정성)

이 지점에서 2026년 업계가 수렴하는 방향이 **OpenTelemetry(OTel) 기반 LLM observability + GenAI semantic conventions**입니다. OTel은 vendor-neutral tracing 표준(OTLP/SDK/Collector)이고, GenAI semantic conventions는 “LLM 호출/Agent 단계/Tool 실행/RAG” 같은 AI 워크로드를 span/attribute로 **표준화**하려는 스펙입니다(아직 Development 상태이며 안정화 전 이행 가이드가 존재). ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/))

### 언제 쓰면 좋나
- 서비스가 **멀티서비스/멀티언어**(gateway, worker, tool server 등)로 나뉘어 trace context 전파가 중요한 경우
- “LLM 호출 1번”이 아니라 **agentic workflow**(n-step, tool, retrieval)가 핵심인 경우
- Langfuse/Datadog/Honeycomb/New Relic 등 특정 벤더로 고정하기 전에 **데이터 포맷을 표준화**하고 싶은 경우 ([zylos.ai](https://zylos.ai/research/2026-02-28-opentelemetry-ai-agent-observability))

### 언제는 피하는 게 낫나
- 단일 백엔드에서 단순 chat completion만 하고, 이미 특정 벤더 SDK로 충분히 관측 가능한 경우(OTel 도입 비용이 더 큼)
- prompt/response를 그대로 수집하면 규정 위반 소지가 큰 도메인인데, **마스킹/샘플링/보관정책**이 준비되지 않은 경우(OTel은 “쉽게 많이” 보내는 순간이 가장 위험)

---

## 🔧 핵심 개념
### 1) “LLM observability”에서 trace가 담당하는 것
Trace는 “좋은 답인가?”를 직접 판정하지 않습니다. 대신 **왜 비용이 폭증했는지**, **어느 단계에서 실패/지연/루프가 생겼는지**, **어떤 tool 인자가 이상했는지** 같은 “구조적 원인”을 밝히는 데 강합니다. 즉:
- Traces/Spans: 실행 경로(의사결정 그래프)
- Metrics: p95 latency, token usage histogram 등 집계
- Logs: 텍스트 디버그(하지만 상관관계가 약함)

LLM/Agent는 “한 요청 = 여러 번의 LLM call + tool + retrieval”이므로, 관측 단위가 HTTP request 1개로 끝나지 않습니다. 그래서 GenAI semantic conventions는 **LLM client span / agent span / tool span / event(입출력) / metrics**로 영역을 나눕니다. ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/))

### 2) GenAI semantic conventions의 가장 중요한 현실: “버전/안정성”
OTel GenAI semantic conventions는 2026년 4월 기준 문서에 **Status: Development**로 표시되어 있고, 기존 instrumentations(v1.36.0 이전 문서 기반)의 호환성 이슈를 피하기 위해 `OTEL_SEMCONV_STABILITY_OPT_IN` 같은 opt-in 전략을 권고합니다. 즉, “스펙이 계속 움직인다”가 전제입니다. ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/))  
실무적으로는:
- 저장(backend) 스키마를 “고정”하지 말고, **attribute mapping/normalization 레이어**를 두는 게 안전합니다.
- instrumentation 라이브러리(OpenLLMetry/OpenLIT 등)를 쓸 때 “어느 버전의 semconv를 emit하는지”를 릴리즈 노트/문서로 확인해야 합니다.

### 3) OpenInference vs OTel GenAI: 왜 둘 다 등장하나
OTel 자체는 범용 tracing 모델이라 attribute가 “의미적으로” 비어있을 수 있습니다. 그래서 AI 영역에서는 두 갈래가 있습니다.
- OTel GenAI semantic conventions: OTel 공식 semconv로 표준화 진행 중 ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/))
- OpenInference: OTel 위에 AI 관측용 attribute/schema를 더 강하게 규정(LLM/AGENT/TOOL/CHAIN 등 span kind taxonomy, 입력/출력/토큰/프라이버시 고려 등) ([arize-ai.github.io](https://arize-ai.github.io/openinference/spec/))

프로젝트 관점의 판단:
- “벤더/플랫폼이 OTel GenAI를 1st-class로 지원한다”면 GenAI semconv 중심
- “AI-specific schema가 더 빨리 필요하고, 도구(Arize 등) 생태계를 쓴다”면 OpenInference도 검토
- 다만 최종적으로는 OTLP로 내보내고, backend에서 매핑하는 구조가 가장 이식성이 좋습니다.

### 4) Langfuse가 말하는 “OTel-native LLM tracing”의 실무 포인트
Langfuse는 OTel spans를 ingest하는 엔드포인트(`/api/public/otel`)를 제공하고, “GenAI semconv가 evolving”이라서 수신한 OTel attribute를 Langfuse 데이터 모델로 매핑한다고 밝힙니다. ([langfuse.com](https://langfuse.com/integrations/native/opentelemetry))  
여기서 중요한 운영 이슈가 하나 더 있습니다:

**Trace-level 속성(userId/sessionId/version/tags/metadata)을 ‘root span에만’ 달면, UI에서 필터/집계가 깨질 수 있다.**  
그래서 Langfuse는 이런 trace-level 속성을 모든 span으로 전파하기 위해 **OpenTelemetry Baggage + BaggageSpanProcessor** 패턴을 권장합니다(단, baggage는 서비스 경계를 넘어 전파되므로 민감정보 금지). ([langfuse.com](https://langfuse.com/integrations/native/opentelemetry))

---

## 💻 실전 코드
시나리오: 프로덕션에 가까운 **RAG + Tool + LLM** 파이프라인(예: “계정 환불 정책” 질의)에 대해
- 하나의 trace에 request 전체를 묶고
- retrieval / tool / llm을 각각 span으로 만들며
- `user.id`, `session.id`, `langfuse.trace.*` 같은 trace-level 속성을 **baggage로 전파**
- OTLP(HTTP/protobuf)로 Collector를 거쳐 백엔드(예: Langfuse OTEL endpoint)로 전송

아래 예시는 “Langfuse를 OTLP backend로” 보내는 구성을 가정합니다(OTLP over HTTP). Langfuse는 `/api/public/otel` 수신 및 헤더 설정을 문서화하고 있습니다. ([langfuse.com](https://langfuse.com/integrations/native/opentelemetry))

### 1) 로컬 실행용: OpenTelemetry Collector + 앱 환경변수
```bash
# (예시) Langfuse Cloud로 OTLP 전송
export OTEL_EXPORTER_OTLP_ENDPOINT="https://us.cloud.langfuse.com/api/public/otel"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${AUTH_STRING},x-langfuse-ingestion-version=4"
export OTEL_SERVICE_NAME="support-agent-api"

# semconv이 evolving인 상황에서, 최신 experimental을 opt-in할지 여부는 팀 정책으로 결정
# (스펙/도구 호환성 확인 후 사용)
export OTEL_SEMCONV_STABILITY_OPT_IN="gen_ai_latest_experimental"
```

### 2) Node.js(TypeScript): RAG + Tool + LLM을 span으로 구조화
```typescript
import { context, trace, SpanStatusCode, propagation } from "@opentelemetry/api";
import { NodeTracerProvider } from "@opentelemetry/sdk-trace-node";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { Resource } from "@opentelemetry/resources";
import { SemanticResourceAttributes } from "@opentelemetry/semantic-conventions";

// Baggage를 span attribute로 복사하는 간단한 processor(팀 정책에 맞게 allowlist 권장)
import { SpanProcessor } from "@opentelemetry/sdk-trace-base";
class BaggageToAttributesProcessor implements SpanProcessor {
  onStart(span: any) {
    const bag = propagation.getBaggage(context.active());
    if (!bag) return;

    // 민감정보 금지. allowlist로 제한하는 게 안전.
    const keys = [
      "user.id",
      "session.id",
      "langfuse.trace.name",
      "langfuse.version",
      "langfuse.release",
      "langfuse.trace.tags",
      "langfuse.trace.metadata.customer_tier",
    ];

    for (const k of keys) {
      const v = bag.getEntry(k)?.value;
      if (v) span.setAttribute(k, v);
    }
  }
  onEnd() {}
  shutdown() { return Promise.resolve(); }
  forceFlush() { return Promise.resolve(); }
}

async function retrieveDocs(query: string) {
  // 실제로는 vector DB 호출
  await sleep(80);
  return [{ id: "doc-17", score: 0.82, text: "Refunds within 14 days..." }];
}

async function callTool(toolName: string, args: any) {
  // 실제로는 내부/외부 API 호출
  await sleep(120);
  return { ok: true, policyId: "refund-v3", region: "US" };
}

async function callLLM(prompt: string) {
  // 실제로는 OpenAI/Anthropic/Bedrock 등 호출 + instrumentation(OpenLLMetry/OpenLIT 등)을 붙이거나
  // 직접 span attribute로 gen_ai.* 를 기록.
  await sleep(300);
  return {
    answer: "You can request a refund within 14 days of purchase if unused.",
    usage: { prompt_tokens: 1200, completion_tokens: 120, total_tokens: 1320 },
    model: "gpt-4.1-mini"
  };
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  // 1) TracerProvider + OTLP exporter
  const provider = new NodeTracerProvider({
    resource: new Resource({
      [SemanticResourceAttributes.SERVICE_NAME]: process.env.OTEL_SERVICE_NAME ?? "support-agent-api",
    }),
  });

  provider.addSpanProcessor(new BaggageToAttributesProcessor());
  provider.addSpanProcessor(
    new BatchSpanProcessor(
      new OTLPTraceExporter({
        url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT,
        headers: Object.fromEntries(
          (process.env.OTEL_EXPORTER_OTLP_HEADERS ?? "")
            .split(",")
            .filter(Boolean)
            .map((kv) => kv.split("=", 2) as [string, string])
        ),
      })
    )
  );

  provider.register();
  const tracer = trace.getTracer("support-agent");

  // 2) “요청” 단위 root span
  const userId = "user-38291";
  const sessionId = "sess-2026-04-28-aaa";

  // baggage 구성(전 서비스 경계 전파 가능 => 민감정보 금지)
  const bag = propagation
    .createBaggage({
      "user.id": { value: userId },
      "session.id": { value: sessionId },
      "langfuse.trace.name": { value: "refund_policy_question" },
      "langfuse.version": { value: "2026.04.28" },
      "langfuse.trace.tags": { value: "rag,support" },
      "langfuse.trace.metadata.customer_tier": { value: "pro" },
    });

  await context.with(propagation.setBaggage(context.active(), bag), async () => {
    await tracer.startActiveSpan("agent.turn", async (rootSpan) => {
      try {
        const question = "I bought it yesterday. Can I get a refund?";
        rootSpan.setAttribute("input.value", question); // backend에 따라 마스킹 필요

        // 2-1) Retrieval span
        const docs = await tracer.startActiveSpan("rag.retrieve", async (span) => {
          span.setAttribute("rag.query", question);
          const result = await retrieveDocs(question);
          span.setAttribute("rag.top_k", 5);
          span.setAttribute("rag.hit_count", result.length);
          span.setAttribute("rag.top1_score", result[0]?.score ?? 0);
          span.end();
          return result;
        });

        // 2-2) Tool span
        const toolResult = await tracer.startActiveSpan("tool.policy_lookup", async (span) => {
          span.setAttribute("tool.name", "policy_lookup");
          span.setAttribute("tool.args.region", "US");
          const result = await callTool("policy_lookup", { region: "US" });
          span.setAttribute("tool.result.ok", result.ok);
          span.setAttribute("tool.result.policyId", result.policyId);
          span.end();
          return result;
        });

        // 2-3) LLM span (직접 기록 or OpenLLMetry/OpenLIT 자동계측)
        const llm = await tracer.startActiveSpan("llm.chat", async (span) => {
          // OTel GenAI semconv는 evolving이므로, 도입 시 attribute 키 표준을 팀 내로 고정/매핑 권장
          span.setAttribute("gen_ai.operation.name", "chat");
          span.setAttribute("gen_ai.request.model", "gpt-4.1-mini");
          span.setAttribute("gen_ai.system", "openai"); // provider
          span.setAttribute("gen_ai.prompt", `Q: ${question}\nCTX: ${docs[0]?.text}`); // 개인정보/PII 마스킹 권장

          const result = await callLLM("...prompt...");
          span.setAttribute("gen_ai.response.model", result.model);
          span.setAttribute("gen_ai.usage.prompt_tokens", result.usage.prompt_tokens);
          span.setAttribute("gen_ai.usage.completion_tokens", result.usage.completion_tokens);
          span.setAttribute("gen_ai.usage.total_tokens", result.usage.total_tokens);
          span.setAttribute("output.value", result.answer);

          span.end();
          return result;
        });

        rootSpan.setAttribute("answer.length", llm.answer.length);
        rootSpan.setStatus({ code: SpanStatusCode.OK });
      } catch (e: any) {
        rootSpan.recordException(e);
        rootSpan.setStatus({ code: SpanStatusCode.ERROR, message: e?.message });
      } finally {
        rootSpan.end();
      }
    });
  });

  // exporter flush
  await provider.shutdown();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

#### 예상 출력(콘솔 출력은 없고, 백엔드에서 확인)
- 하나의 trace(`agent.turn`) 아래에
  - `rag.retrieve`
  - `tool.policy_lookup`
  - `llm.chat`
- 모든 span에 `user.id`, `session.id`, `langfuse.trace.name`, `langfuse.trace.metadata.customer_tier` 등이 붙어 필터/집계 가능  
이 “trace-level 속성 전파”는 Langfuse가 특히 강조하는 운영 포인트입니다. ([langfuse.com](https://langfuse.com/integrations/native/opentelemetry))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “무엇을 span으로 만들지” 기준을 먼저 정하라
LLM 앱에서 span을 무한히 쪼개면 비용/노이즈가 폭증합니다. 추천 기준:
- **비용/지연의 주요 원인 단위**: LLM call, retrieval query, tool call, reranker, embedding
- **실패 모드가 다른 단위**: tool timeout vs retrieval miss vs prompt overflow
- 그 외 “문자열 가공” 같은 건 보통 event/log로 충분

### Best Practice 2) Baggage는 강력하지만 위험하다
Langfuse는 trace-level 속성을 모든 span에 전파하기 위해 baggage를 권장하지만, baggage는 **서비스 경계를 넘어 전파**됩니다. 즉:
- userId/sessionId 같은 식별자는 괜찮을 수 있어도,
- prompt 원문, 이메일, 전화번호 같은 PII를 baggage에 넣으면 최악입니다(전파 + 저장 + 검색 가능성).

따라서:
- baggage key allowlist 고정
- PII는 “export 전 마스킹” 또는 “샘플링 시에만 저장” 같은 정책 필요

### Best Practice 3) semconv가 변한다는 전제를 아키텍처에 반영
OTel GenAI semconv는 Development 상태이며, 기존 버전과의 이행 전략(옵트인 환경변수 등)이 문서에 명시되어 있습니다. ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/))  
실무 대응:
- (1) 앱 내부 attribute key를 “표준 키 + 사내 확장 키”로 나누고
- (2) Collector 혹은 backend ingestion에서 normalization/mapping 레이어를 둬서
- (3) UI/대시보드 쿼리는 “정규화된 필드”만 보게 만들면, 스펙 변화에 덜 흔들립니다.

### 흔한 함정) “trace는 있는데, 쓸모가 없다”
Zylos 쪽 글에서도 전통 관측이 에이전트에 부족한 이유로 “emergent failure”와 “token cost가 runtime variable”을 강조합니다. ([zylos.ai](https://zylos.ai/research/2026-02-28-opentelemetry-ai-agent-observability))  
즉 trace만 켜면 해결되는 게 아니라, 최소한 아래 2개는 같이 해야 합니다:
- retrieval quality 지표(hit rate, top1 score, context length) 같이 기록
- token/cost budget 초과를 “알람 조건”으로 승격(관측 → 통제)

---

## 🚀 마무리
핵심은 “LLM 앱을 HTTP request처럼 보면 망한다”입니다. 2026년 4월 기준의 트렌드는:
- **OpenTelemetry**를 telemetry layer로 깔고(Collector/OTLP/벤더 중립),
- **GenAI semantic conventions / OpenInference** 같은 AI 특화 schema로 “해석 가능한 trace”를 만들며, ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/))
- user/session/version/metadata 같은 trace-level 컨텍스트는 **baggage 기반으로 전파**해 운영 필터/집계를 가능하게 만드는 쪽으로 수렴합니다. ([langfuse.com](https://langfuse.com/integrations/native/opentelemetry))

도입 판단 기준(현실적인 체크리스트):
- 우리 장애의 70%가 “의미적 실패”인가? → Yes면 tracing 투자 가치 큼
- 멀티서비스/툴 서버/비동기 worker가 있는가? → OTel의 context propagation이 진가
- PII/보안/비용(샘플링) 정책이 준비됐는가? → 없다면 먼저 가드레일부터

다음 학습 추천:
- OTel GenAI semantic conventions(특히 stability/opt-in 전략) 문서 정독 ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/))
- OpenInference spec로 “AI span taxonomy를 어떻게 잡을지” 참고 ([arize-ai.github.io](https://arize-ai.github.io/openinference/spec/))
- Langfuse를 쓴다면 OTEL ingest + trace attribute propagation 패턴을 그대로 운영 표준으로 삼기 ([langfuse.com](https://langfuse.com/integrations/native/opentelemetry))