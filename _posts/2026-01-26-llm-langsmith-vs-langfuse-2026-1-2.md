---
title: "LLM 앱 운영의 현실: LangSmith vs Langfuse로 “디버깅·비용·품질”을 한 번에 잡는 법 (2026년 1월 관점)"
date: 2026-01-26 02:32:48 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-01]
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
LLM 애플리케이션은 “잘 동작한다/안 한다”로 끝나지 않습니다. 같은 입력에도 출력이 흔들리고(비결정성), 한 번의 요청이 여러 단계(Agent planning → tool → retrieval → LLM → rerank…)로 분기되며, 비용은 호출 단위가 아니라 **워크플로 전체**에서 새어 나갑니다. 그래서 운영 단계에서 진짜 필요한 건 단순 logging이 아니라 **Observability(관측 가능성)** 입니다: “어떤 프롬프트가”, “어떤 컨텍스트로”, “어떤 모델을”, “얼마나 쓰고”, “어디서 실패했는지”를 **요청 단위(trace)** 로 재구성할 수 있어야 합니다.

2025~2026 흐름에서 가장 큰 변화는 두 제품 모두 **OpenTelemetry(OTel) 기반으로 ‘엔드-투-엔드 분산 트레이싱’** 을 밀고 있다는 점입니다. LangSmith는 SDK 수준의 OTel 지원을 “완성된 파이프라인”으로 확장했고(기존엔 ingestion 포맷 중심이었다는 맥락), Langfuse는 OTLP 엔드포인트 + OTEL-native SDK(v3)로 언어/프레임워크 호환성을 넓혔습니다. ([blog.langchain.com](https://blog.langchain.com/end-to-end-opentelemetry-langsmith?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Trace / Span / Observation: “한 요청을 재조립하는 단위”
- **Trace**: 사용자 요청 1번의 end-to-end 실행 단위. LLM 호출, tool, retrieval, rerank 등 여러 이벤트를 포함합니다. LangSmith도 trace를 “단일 실행”으로 정의합니다. ([langchain.com](https://www.langchain.com/pricing?utm_source=openai))
- **Span**(OTel): 분산 트레이싱의 기본 단위. 부모-자식 관계로 중첩되어 호출 트리를 만듭니다.
- **Observation( Langfuse )**: Langfuse는 수신한 OTel span을 자체 모델(스팬/제너레이션/이벤트 등)로 매핑합니다. GenAI semantic convention이 진화 중이라 “속성 매핑(property mapping)”을 제공한다는 점이 포인트입니다. ([langfuse.com](https://langfuse.com/docs/opentelemetry/get-started?utm_source=openai))

결론: LLM Observability에서 가장 중요한 능력은 **컨텍스트 전파(Context Propagation)** 입니다. 모듈이 갈라지고 비동기/멀티스레드가 섞여도 “이 tool 호출이 어느 사용자 요청에 속하는지”가 자동으로 이어져야 합니다. Langfuse SDK v3가 OTel 기반으로 “표준화된 컨텍스트 전파”를 전면에 내세운 이유도 여기에 있습니다. ([langfuse.com](https://langfuse.com/changelog/2025-05-23-otel-based-python-sdk?utm_source=openai))

### 2) 디버깅의 본질: “프롬프트/컨텍스트/출력” + “중간 단계”
LLM 앱 장애는 보통 아래 중 하나로 귀결됩니다.
- 프롬프트 템플릿/시스템 메시지 변경으로 성능 붕괴
- retrieval 품질 저하(인덱스, 필터, top-k, rerank)
- tool I/O 스키마 불일치(모델이 만든 JSON이 깨짐)
- latency 병목(특정 외부 API, 특정 모델)
따라서 트레이스는 **LLM 호출만** 찍으면 부족하고, **툴/리트리벌/비즈니스 로직 스팬까지 같은 트리**에 있어야 합니다. 이 지점에서 OTel이 “벤더 중립 표준”으로 힘을 얻고, Langfuse가 OTLP 엔드포인트로 다양한 프레임워크를 수용하는 방향이 자연스럽습니다. ([langfuse.com](https://langfuse.com/changelog/2025-02-14-opentelemetry-tracing?utm_source=openai))

### 3) 비용 추적의 난점: “토큰 비용 + 비토큰 비용(툴/검색/외부 API)”
2026년 운영 관점에서 비용은 “LLM 토큰”만이 아닙니다.
- LLM: input/output token, cache read, reasoning token, multimodal token 등 세분화
- Tool: 외부 API 과금, 벡터DB 쿼리 비용, 크롤링 비용
LangSmith는 2025년 12월에 “full-stack cost tracking”을 강조했고, UI 곳곳(trace tree / stats / dashboards)에서 토큰·비용 breakdown을 보여주는 구조를 갖췄습니다. ([changelog.langchain.com](https://changelog.langchain.com/announcements/unified-cost-tracking-for-llms-tools-retrieval?utm_source=openai))  
또한 LangSmith는 자동 계산(토큰+가격표) + 수동 제출(커스텀 비용)을 모두 지원합니다. ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))

Langfuse도 OTEL-native SDK v3에서 **token usage, cost tracking, scoring** 같은 LLM 특화 헬퍼를 “OTel 위 thin layer”로 제공한다고 명시합니다. ([langfuse.com](https://langfuse.com/docs/opentelemetry/get-started?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “우리 앱 코드는 OTel로만 계측하고, 백엔드는 Langfuse 또는 LangSmith로 바꿔 끼울 수 있게” 만드는 접근입니다. 핵심은 **OTLP exporter 설정 + span attribute에 GenAI/비용 정보를 실어 보내기** 입니다.

```python
# Python 3.11+
# pip install opentelemetry-sdk opentelemetry-exporter-otlp openai
#
# 목적:
# 1) OTel로 trace/span 생성
# 2) LLM 호출/툴 호출을 같은 trace 트리에 넣음
# 3) token/cost(가능하면)를 span attribute로 남겨 운영 분석 가능하게 함
#
# 백엔드 선택:
# - Langfuse: OTLP endpoint로 ingest 가능 (/api/public/otel).  ([langfuse.com](https://langfuse.com/integrations/native/opentelemetry?utm_source=openai))
# - LangSmith: OTel 기반 tracing을 지원(자체 파이프라인/가이드 존재). ([docs.langchain.com](https://docs.langchain.com/langsmith/trace-with-opentelemetry?utm_source=openai))

import os
import time
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# ---------- 1) OTLP Exporter 설정 ----------
# Langfuse를 쓴다면 예시:
#   OTEL_EXPORTER_OTLP_ENDPOINT="https://<langfuse-host>/api/public/otel"
#   OTEL_EXPORTER_OTLP_HEADERS="x-langfuse-public-key=... ,x-langfuse-secret-key=..."
#
# 실제 헤더 키/형식은 Langfuse 문서에 맞추세요. (여기선 구조만 제시)
# LangSmith의 경우도 OTel exporter 구성이 가능하며, LangChain/LangGraph는 자동 계측 옵션도 있습니다. ([docs.langchain.com](https://docs.langchain.com/langsmith/trace-with-opentelemetry?utm_source=openai))

endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")

resource = Resource.create({
    "service.name": "llm-app",
    "deployment.environment": os.environ.get("APP_ENV", "dev"),
})

provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
provider.add_span_processor(BatchSpanProcessor(exporter))

tracer = trace.get_tracer(__name__)

# ---------- 2) 비즈니스 로직: LLM + Tool ----------
def fake_tool_search(query: str) -> dict:
    # 툴 호출도 span으로 감싸면, 어느 요청의 어느 단계인지 한눈에 보입니다.
    with tracer.start_as_current_span("tool.search") as span:
        t0 = time.time()
        time.sleep(0.05)
        span.set_attribute("tool.name", "fake_search")
        span.set_attribute("tool.query", query)
        # 비토큰 비용(외부 API 과금 등)이 있으면 attribute로 남기거나
        # (LangSmith는 tool run에 total_cost를 넣는 패턴도 지원) ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))
        span.set_attribute("cost.usd", 0.0003)
        span.set_attribute("latency.ms", int((time.time() - t0) * 1000))
        return {"docs": ["doc1 about " + query, "doc2 about " + query]}

def call_llm(prompt: str) -> str:
    with tracer.start_as_current_span("llm.call") as span:
        t0 = time.time()
        # 실제로는 OpenAI/Anthropic SDK 호출
        # 여기선 예시로 고정 응답
        completion = f"Answer based on: {prompt[:40]}..."

        # 운영에 중요한 최소 속성들
        span.set_attribute("llm.model", os.environ.get("LLM_MODEL", "gpt-*"))
        span.set_attribute("llm.prompt_chars", len(prompt))
        span.set_attribute("latency.ms", int((time.time() - t0) * 1000))

        # 토큰/비용은 공급자 응답에서 usage를 파싱해 넣는 게 정석입니다.
        # LangSmith는 usage_metadata 기반으로 자동/수동 비용 계산을 지원합니다. ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))
        # (OTel-only로 간다면 attribute에 남겨도 분석에 도움이 됩니다.)
        span.set_attribute("tokens.input", 120)
        span.set_attribute("tokens.output", 80)
        span.set_attribute("cost.usd", 0.0021)

        return completion

def handle_request(user_query: str, user_id: str) -> str:
    # Trace의 최상위 span: request 단위
    with tracer.start_as_current_span("request") as span:
        span.set_attribute("user.id", user_id)
        span.set_attribute("request.query", user_query)

        ctx = fake_tool_search(user_query)
        prompt = f"Q: {user_query}\nContext: {ctx['docs']}\nA:"
        answer = call_llm(prompt)

        span.set_attribute("result.len", len(answer))
        return answer

if __name__ == "__main__":
    print(handle_request("LangSmith와 Langfuse 차이?", "user-123"))
```

이 방식의 장점은 “계측은 OTel 표준으로 고정”하고, 백엔드는 조직 상황에 따라 Langfuse(오픈소스/셀프호스트) 또는 LangSmith(평가/플랫폼 통합 포함)로 선택지를 남길 수 있다는 점입니다. 두 제품 모두 OTel을 핵심 축으로 강화하는 추세라, 장기 유지보수에도 유리합니다. ([blog.langchain.com](https://blog.langchain.com/end-to-end-opentelemetry-langsmith?utm_source=openai))

---

## ⚡ 실전 팁
1) **Sampling을 ‘환경별’로 다르게**
- dev/staging: 100% trace
- prod: 에러/지연/고비용 요청은 100%, 나머지는 샘플링  
OTel 파이프라인을 쓰면 표준적인 방식으로 sampling 전략을 적용할 수 있습니다(벤더 종속 최소화).

2) **비용 추적은 “자동 + 수동” 혼합이 현실적**
- LLM 비용은 토큰 usage가 잘 나오면 자동 집계가 편합니다(LangSmith는 모델 가격표/세부 토큰 타입까지 매핑 가능). ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))
- tool/retrieval/외부 API는 **수동 비용 제출** 또는 span attribute로 남겨서 “워크플로 총비용”을 완성하세요. LangSmith는 tool run에 `total_cost` 같은 형태로 비용을 붙이는 가이드를 제공합니다. ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))

3) **컨텍스트 전파가 깨지는 지점을 먼저 의심**
- 비동기 작업, 백그라운드 큐, 멀티프로세스에서 trace가 끊어지는 경우가 많습니다.
- Langfuse SDK v3가 OTel 기반으로 “자동 컨텍스트 전파/중첩(span nesting)”를 강조하는 이유가 여기 있습니다. ([langfuse.com](https://langfuse.com/changelog/2025-05-23-otel-based-python-sdk?utm_source=openai))

4) **보관(retention)과 과금 모델을 운영 정책에 맞춰라**
- LangSmith는 trace 보관 기간에 따라 base/extended로 구분되며 가격이 다릅니다(14일 vs 400일). 장애 분석이 “최근 2주”인지 “장기 품질 추적”인지에 따라 선택이 달라집니다. ([langchain.com](https://www.langchain.com/pricing?utm_source=openai))
- 또한 LangSmith는 “달러 기준 spend limit”이 아니라 “trace 수 제한”을 설정하는 구조라는 점이 함정 포인트입니다(예산 통제를 숫자 변환해서 운영해야 함). ([docs.langchain.com](https://docs.langchain.com/langsmith/pricing-faq?utm_source=openai))

5) **GenAI semantic conventions는 아직 진화 중: attribute 네이밍을 정해두기**
Langfuse도 명시하듯 GenAI용 OTel 속성 규약은 계속 변합니다. ([langfuse.com](https://langfuse.com/docs/opentelemetry/get-started?utm_source=openai))  
팀 내부 표준(예: `llm.model`, `tokens.input`, `cost.usd`, `rag.top_k`, `tool.name`)을 먼저 고정해두면, 백엔드/라이브러리 변경에도 데이터가 “비교 가능”하게 유지됩니다.

---

## 🚀 마무리
2026년 1월 기준으로 LangSmith와 Langfuse의 공통된 큰 방향은 명확합니다: **OTel을 중심으로 LLM Observability를 “분산 시스템 관측”의 세계로 끌어오는 것**. LangSmith는 평가/대시보드/비용 집계를 제품 내에서 강하게 통합하고(특히 full-stack cost tracking), Langfuse는 OTLP 수신 + OTEL-native SDK로 “호환성과 오픈 생태계”를 넓히는 전략이 두드러집니다. ([changelog.langchain.com](https://changelog.langchain.com/announcements/unified-cost-tracking-for-llms-tools-retrieval?utm_source=openai))

다음 학습 추천:
- OTel에서 **context propagation**(async, background job) 제대로 잡기
- “비용”을 LLM 토큰에 한정하지 않고 **tool/retrieval까지 합산**하는 데이터 모델 설계
- Prod에서의 **sampling/PII 마스킹/retention 정책**까지 포함한 운영 설계

원하시면, (1) LangSmith 전용 코드( `langsmith[otel]`, `LANGSMITH_OTEL_ENABLED` 기반)로 완전히 맞춘 예제, (2) Langfuse SDK v3(`observe`, `get_client`) 스타일 예제로도 각각 따로 정리해 드릴게요. ([docs.langchain.com](https://docs.langchain.com/langsmith/trace-with-opentelemetry?utm_source=openai))