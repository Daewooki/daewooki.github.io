---
title: "LLM 앱이 “왜 이상하게” 동작하는지 30분 안에 잡아내는 관측성: LangSmith vs Langfuse 심층 분석 (디버깅·비용·추적)"
description: "2026년 3월 기준 LLM 애플리케이션 운영의 본질은 “모델 성능”이 아니라 “시스템 성능”입니다. 같은 prompt라도 컨텍스트(툴 호출, RAG 검색 결과, 재시도, 라우팅, 캐시, 모델 버전)에 따라 결과가 출렁이고, 장애는 대개 코드가 아니라 오케스트레이션(Agent graph…"
date: 2026-03-01 02:58:29 +0900
categories: [AI, MLOps]
tags: [ai, mlops]
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
2026년 3월 기준 LLM 애플리케이션 운영의 본질은 “모델 성능”이 아니라 “시스템 성능”입니다. 같은 prompt라도 **컨텍스트(툴 호출, RAG 검색 결과, 재시도, 라우팅, 캐시, 모델 버전)**에 따라 결과가 출렁이고, 장애는 대개 코드가 아니라 **오케스트레이션(Agent graph)와 외부 의존성**에서 터집니다. 그래서 프로덕션에서 필요한 건 로그가 아니라 **trace 중심의 observability**입니다.

이때 대표 선택지가 LangSmith(상용 SaaS 중심)와 Langfuse(오픈소스/자체 호스팅 친화)인데, 둘 다 “trace 보기”를 넘어서 **디버깅(원인 추적)**, **비용/토큰 추적(재무 관점의 SLO)**, 그리고 **표준화(OpenTelemetry)**로 가고 있다는 점이 핵심 변화입니다. LangSmith는 SDK 단계까지 end-to-end OpenTelemetry 지원을 확장했고(2025-03), 비용 추적 대시보드를 공식 문서로 체계화했습니다.[^1] Langfuse는 JS 생태계에서 OpenTelemetry 기반 SDK v4로 재구성하며(2025-08 공지), OTEL export 도구(@langfuse/otel)까지 제공해 “표준 파이프라인”에 올라탔습니다.[^2]

---

## 🔧 핵심 개념
### 1) Trace / Span / Context propagation
- **Trace**: “사용자 요청 1건”의 end-to-end 실행 단위(대개 request 단위).
- **Span**: trace 내부의 단계(LLM call, retriever query, tool call, rerank, postprocess 등).
- **Context propagation**: 분산 환경(웹 서버 → 워커 → 툴 서비스)에서도 동일 trace로 연결되게 하는 메커니즘.

LangSmith는 OpenTelemetry를 통해 “LLM 단계 + 인프라 단계”를 한 뷰로 묶는 방향을 강조합니다. 특히 LangChain/LangGraph 기반 앱에서 OTel을 표준 수집 포맷으로 쓰도록 지원을 강화했습니다.[^1]  
Langfuse 역시 OpenTelemetry 기반으로 span을 수집/가공하는 도구 체인을 확장하고 있고, 외부 시스템(예: Databricks MLflow로 export)과 연결되는 흐름이 점점 강해지는 중입니다.[^3]

### 2) LLM 디버깅에서 “관측성”이 필요한 이유: 재현 가능성
LLM 장애의 흔한 유형은:
- 특정 tool 호출이 timeout → fallback이 다른 경로로 흘러 prompt 구성이 달라짐
- RAG에서 retrieval 결과가 0개 → hallucination 증가
- 토큰 폭증 → latency 급증 + 비용 급증

이건 “에러 로그 1줄”로 해결이 안 됩니다. **어떤 span에서 input이 무엇이었고, output token이 얼마나 나왔고, 재시도가 몇 번 발생했는지**가 보이는 trace가 필요합니다.

### 3) 비용 추적(Cost tracking)의 두 층: “자동” vs “수동”
LangSmith는 비용을 (a) token count + 모델 가격표로 **자동 파생**하거나, (b) run에 cost를 **수동으로 주입**하는 두 경로를 명시합니다.[^4]  
실무적으로는:
- OpenAI/Anthropic 등 표준 과금 모델은 자동이 편함
- 자체 호스팅 모델/번들 과금/툴 호출 비용까지 합산하려면 수동 주입이 필수

### 4) 2026년 선택 기준의 본질: “OTel 파이프라인을 누가 주도하나”
- LangSmith 쪽은 “LangChain/LangGraph 앱을 빠르게 운영” + LangSmith UI/평가/모니터링에 최적화(OTel도 지원).[^1]
- Langfuse 쪽은 “OpenTelemetry 기반으로 다양한 프레임워크/SDK에서 span을 모아” Langfuse(또는 다른 OTLP backend)로 보내는 옵션이 강해지는 중. 특히 Node.js 20+ 중심으로 OTEL export 유틸(@langfuse/otel)이 명확합니다.[^5]

---

## 💻 실전 코드
아래 예제는 “한 번의 사용자 요청”을 trace로 묶고, 내부에서 LLM 호출/추가 작업(span)을 남기며, **비용/토큰 폭증과 같은 운영 이슈를 나중에 역추적**할 수 있게 만드는 최소 단위입니다.

### (A) LangSmith: OpenTelemetry 활성화 + LangChain 호출 (Python)
LangSmith는 `langsmith[otel]` 설치 및 환경변수로 OTel 기반 tracing을 켤 수 있습니다.[^1]

```python
# python
import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# 1) 환경 변수로 LangSmith + OTel tracing 활성화
# (운영에서는 Secret Manager로 주입 권장)
os.environ["LANGSMITH_OTEL_ENABLED"] = "true"
os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_API_KEY"] = os.getenv("LANGSMITH_API_KEY", "<YOUR_LANGSMITH_API_KEY>")
os.environ["LANGSMITH_PROJECT"] = "prod-llm-observability"

# 2) 애플리케이션 코드: 체인 실행이 trace로 자동 수집되도록 구성
prompt = ChatPromptTemplate.from_template(
    "You are a strict assistant. Answer briefly.\nQuestion: {q}"
)
model = ChatOpenAI(model="gpt-4o-mini")  # 예시

chain = prompt | model

def handle_request(user_question: str) -> str:
    # 이 함수 1회 호출이 보통 '요청 1건' = trace 1개로 연결됨(구성에 따라 다를 수 있음)
    result = chain.invoke({"q": user_question})
    return result.content

if __name__ == "__main__":
    print(handle_request("Explain why RAG can increase latency."))
```

포인트:
- “LLM call이 어디서 얼마나 느린지”, “어떤 prompt가 비용을 폭증시키는지”는 **span의 attributes/token/cost**가 쌓여야 보입니다.
- LangSmith는 비용 추적을 자동 파생/수동 주입 모두 지원한다는 점을 문서로 명확히 합니다.[^4]

### (B) Langfuse: OpenTelemetry Span Processor를 붙여 Node에서 export (TypeScript)
Langfuse는 JS SDK를 OpenTelemetry 기반으로 재구성했고, `LangfuseSpanProcessor`를 제공하는 `@langfuse/otel` 패키지를 제공합니다(마스킹/필터링/미디어 처리 포함).[^5]

```ts
// typescript
// Node.js 20+ 권장(패키지 설명 기준). 실제 프로젝트에선 dotenv/secret manager 사용.
import { NodeSDK } from "@opentelemetry/sdk-node";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";
import { LangfuseSpanProcessor } from "@langfuse/otel";
import { trace } from "@opentelemetry/api";

// 1) Langfuse 인증/호스트 설정 (Cloud 또는 self-hosted)
process.env.LANGFUSE_HOST = process.env.LANGFUSE_HOST ?? "https://cloud.langfuse.com";
process.env.LANGFUSE_PUBLIC_KEY = process.env.LANGFUSE_PUBLIC_KEY ?? "<PUBLIC_KEY>";
process.env.LANGFUSE_SECRET_KEY = process.env.LANGFUSE_SECRET_KEY ?? "<SECRET_KEY>";

const sdk = new NodeSDK({
  instrumentations: [getNodeAutoInstrumentations()],
  // 핵심: LangfuseSpanProcessor로 OTEL span을 Langfuse로 export
  spanProcessors: [
    new LangfuseSpanProcessor({
      // 운영 팁: 마스킹/필터링 정책을 여기서 강제해 PII 유출을 막는 식으로 사용
      // (구체 옵션은 Langfuse 문서/레퍼런스에 따름)
    }),
  ],
});

async function main() {
  await sdk.start();

  // 2) 수동 span 예시: "요청 1건"을 최상위 span으로 감싸고 내부 작업을 자식 span으로 구성
  const tracer = trace.getTracer("llm-app");

  await tracer.startActiveSpan("chat.request", async (rootSpan) => {
    try {
      rootSpan.setAttribute("env", "production");
      rootSpan.setAttribute("feature", "support-chat");

      await tracer.startActiveSpan("llm.call", async (span) => {
        // 여기에서 OpenAI SDK/LangChain 호출 등을 수행
        // token/cost는 SDK 통합 또는 attribute로 기록(도구/통합 방식에 따라 다름)
        span.setAttribute("model", "gpt-4o-mini");
        await new Promise((r) => setTimeout(r, 150)); // 예시 지연
        span.end();
      });

      rootSpan.end();
    } catch (e) {
      rootSpan.recordException(e as Error);
      rootSpan.setStatus({ code: 2 }); // ERROR
      rootSpan.end();
      throw e;
    }
  });

  await sdk.shutdown();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

포인트:
- Langfuse의 방향성은 “OTel로 들어오는 span을 Langfuse에서 해석/시각화”하는 표준 파이프라인에 가깝습니다.
- Databricks 문서는 Langfuse trace를 OTEL 기반으로 외부로 export하는 예를 공식 가이드로 제공하고 있어, “Langfuse에만 묶이지 않는 운영”이 가능합니다.[^3]

---

## ⚡ 실전 팁
1) **Trace 비용 폭탄의 1차 원인은 ‘샘플링 부재’**
- 모든 요청을 100% trace하면 디버깅엔 좋지만, 비용/저장/PII 리스크가 폭발합니다.
- 권장: `error` 또는 `slow request`는 100%, 정상 트래픽은 확률 샘플링(예: 1~5%) + 특정 고객/기능은 고정 샘플링.

2) **“요청 1건 = trace 1개”로 과금/지표를 맞추는 습관**
LangSmith는 플랜에서 trace 단위 과금/포함량을 명확히 제시하고 있습니다(무료/Plus 포함 trace, 초과 과금 등).[^6]  
실무에선 trace 정의가 흔들리면 KPI도 흔들립니다.
- API Gateway / Backend entry에서 root span을 만들고
- 내부 chain/agent 단계는 child span으로만 쪼개기

3) **비용 추적은 “LLM만”이 아니라 “툴 호출까지” 합산해야 의미가 생김**
LangSmith 문서도 수동 비용 주입을 명시한 이유가 여기 있습니다.[^4]  
예: 웹 검색(tool) 호출, reranker, OCR, DB 쿼리, GPU inference 등 “LLM 외 비용”이 더 큰 서비스가 흔합니다.

4) **OTel을 채택하면 ‘벤더 락인’이 아니라 ‘벤더 스위칭 비용’이 줄어듦**
LangSmith가 end-to-end OTel을 강조하는 것도 “표준 계층”을 확보해 observability를 스택 전체로 확장하려는 흐름입니다.[^1]  
Langfuse는 OTel 기반 SDK/processor로 그 흐름을 더 강하게 탑니다.[^5]  
결론: 지금 새로 설계한다면 “도구를 무엇을 쓰든” **OTel 컨텍스트/attribute 규칙을 팀 표준으로 먼저 정하는 게** 장기적으로 이깁니다.

5) **PII/프롬프트 유출 방지는 ‘마스킹’이 아니라 ‘기본 비수집’으로**
- “필요할 때만 verbose”가 안전합니다.
- Langfuse exporter 계열 문서에서도 보안상 일부 내용을 기본 마스킹하고 verbose 옵션으로 노출하는 패턴이 보입니다.[^7]

---

## 🚀 마무리
LangSmith와 Langfuse를 2026년 3월 시점에서 보면, 경쟁 포인트는 UI나 기능 몇 개가 아니라 **표준(OpenTelemetry) 위에서 디버깅/비용/평가를 얼마나 운영 친화적으로 묶어주느냐**입니다.  
- LangSmith: LangChain/LangGraph 중심 팀이 “빠르게 tracing+cost dashboard”까지 가는 데 강점(OTel end-to-end 지원, 비용 추적 가이드/대시보드).[^1]  
- Langfuse: 오픈소스/자체 호스팅/OTel 파이프라인 중심으로 “수집→가공→외부 export”까지 유연성을 확보하는 방향(OTEL JS SDK v4, @langfuse/otel).[^2]

다음 학습 추천은 2가지입니다.
1) 팀 표준으로 **trace attribute 규약(model, feature, customer_tier, session_id, prompt_version, retriever_topk, cache_hit 등)**을 정하고,  
2) OTel Collector를 중간에 두는 구조(샘플링/리다이렉트/마스킹 중앙집중)를 설계해 “도구 교체 가능한 관측성”을 완성하세요. LangSmith도 OTel 기반 분산 tracing 흐름을 적극적으로 안내하고 있습니다.[^8]

[^1]: <https://blog.langchain.com/end-to-end-opentelemetry-langsmith>
[^2]: <https://github.com/orgs/langfuse/discussions/8403>
[^3]: <https://docs.databricks.com/aws/en/mlflow3/genai/tracing/third-party/langfuse>
[^4]: <https://docs.langchain.com/langsmith/cost-tracking>
[^5]: <https://www.npmjs.com/package/%40langfuse/otel>
[^6]: <https://www.langchain.com/pricing>
[^7]: <https://docs.koog.ai/opentelemetry-langfuse-exporter/>
[^8]: <https://blog.langchain.com/opentelemetry-langsmith>
