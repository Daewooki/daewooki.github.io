---
title: "LLM 호출 내부까지 “끝까지” 보이게: 2026년 7월 기준 OpenTelemetry GenAI Tracing으로 LLM Observability 구축하기"
date: 2026-07-16 03:21:37 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-07]
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
LLM 앱을 운영해보면 장애의 원인이 “코드 예외”보다 “모델 호출/프롬프트/툴 체인”에 숨어있는 경우가 더 많습니다. 예를 들어:

- 특정 사용자/테넌트에서만 latency가 튀는데, **LLM 호출인지 vector 검색인지 tool 실행인지** 분해가 안 됨
- “가끔” hallucination이 늘어나는데, **어떤 prompt 변형/컨텍스트/모델 파라미터**에서만 터지는지 재현이 어려움
- 비용이 급증했는데, **어느 route/agent step**이 토큰을 태우는지 추적이 안 됨

2026년 들어 OpenTelemetry(OTel) 쪽에서 GenAI semantic conventions가 정리되면서, LLM 관측(Observability)을 “벤더별 JSON 로그”가 아니라 **표준 tracing/metrics로 정규화**해 가져갈 수 있는 길이 꽤 또렷해졌습니다. 특히 OTel 블로그에서 GenAI tracing 예시를 span tree로 보여주며(LLM call, tool invocation이 자식 span으로 내려감) “LLM 호출을 분해해서 보는” 방식이 공식적으로 설계/전파되고 있습니다. ([opentelemetry.io](https://opentelemetry.io/blog/2026/genai-observability/?utm_source=openai))

### 언제 쓰면 좋나
- LLM 호출이 단순 1회가 아니라 **agent / tool / RAG / multi-step**로 이어지는 프로덕션 서비스
- 벤더(LangSmith/Langfuse/자체 UI 등) 바꿀 가능성이 있고, **lock-in을 피하고 싶은 팀**
- “품질/안전”도 중요하지만, 당장 현실적으로는 **latency/에러/비용(토큰)**을 운영 지표로 잡아야 하는 팀

### 언제 쓰면 안 되나
- PoC 단계에서 **관측 비용(수집/저장/개인정보 리스크)**보다 기능 속도가 훨씬 중요할 때
- LLM 호출을 애초에 외부 SaaS로만 감싸서, 내부 스텝이 거의 없고 장애 분석 요구도 낮을 때
- 프롬프트/응답 내용을 저장하면 안 되는 환경인데(민감정보), **content capture 정책/마스킹 파이프라인**을 아직 설계하지 못했을 때  
  (이건 “하면 안 됨”에 가깝고, 최소한 “no_content + 메타데이터만”으로 시작하는 게 안전합니다. OTel GenAI instrumentation도 content 모드를 분리해서 제공합니다. ([opentelemetry-python-contrib.readthedocs.io](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation-genai/openai.html?utm_source=openai)))

---

## 🔧 핵심 개념
### 1) LLM Observability에서 “Tracing”이 핵심인 이유
LLM 앱의 실패는 대개 **단일 로그 라인**으로는 원인 분리가 안 됩니다. 하나의 사용자 요청이 다음을 연쇄적으로 만들기 때문이죠.

- API gateway → app server span
- “agent run” span
- 1..N개의 LLM call span(chat/completion)
- tool call span(검색/DB/외부 API)
- RAG retriever span(벡터DB, reranker)
- 후처리/검증 span(guardrail, structured output validation)

Tracing은 이걸 **하나의 Trace(=root span 아래의 트리)**로 엮어 “이번 요청”의 병목과 실패 지점을 구조적으로 보여줍니다. OTel Trace API는 span에 attributes/events/status를 붙이고, parent-child 관계로 트리를 구성하는 걸 표준으로 정의합니다. ([opentelemetry.io](https://opentelemetry.io/docs/specs/otel/trace/api/?utm_source=openai))

### 2) GenAI semantic conventions: “LLM용 표준 태그/이벤트”
2026년의 변화 포인트는, LLM 관측에서 가장 골치 아팠던 “필드 네이밍 지옥”을 줄이기 위해 OTel이 `gen_ai.*` 표준을 정리했다는 점입니다. GenAI attributes는 OTel 문서에서 별도 레지스트리로 제공되고(예: provider/model/output type 등), instrumentation은 “최선의 지식”으로 provider를 세팅할 수 있음을 명시합니다. ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/?utm_source=openai))

또한 GenAI span은 “프롬프트/컴플리션을 이벤트로 남길 수도 있고, 안 남길 수도 있음”을 전제로 설계됩니다. 즉 운영 환경에서 **개인정보/GDPR/보안** 때문에 content를 꺼야 하는 요구를 모델링에 포함합니다. ([opentelemetry-semantic-conventions.hexdocs.pm](https://opentelemetry-semantic-conventions.hexdocs.pm/gen-ai-spans.html?utm_source=openai))

핵심은 이거예요:

- **Span = 호출/단계의 경계(시간, 실패, 상하관계)**
- **Attributes = 질의 가능한 메타데이터(모델, 토큰, provider, deployment, route 등)**
- **Events = 프롬프트/응답 같은 “내용” 또는 단계 내 주요 순간(선택적/정책 기반)**

### 3) “LLM provider SDK tracing” vs “OTel tracing”
요즘 프레임워크/SDK들은 각자 tracing을 제공합니다. 예를 들어 OpenAI Agents SDK는 agent run 동안 LLM generations, tool calls, handoffs 등을 포괄적으로 기록하는 built-in tracing을 제공하고, exporter로 OpenAI backend에 배치 전송하는 구조를 갖습니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tracing/?utm_source=openai))

반면 OTel의 장점은:
- 백엔드(Tempo/Jaeger/Uptrace/Honeycomb 등) 교체 가능
- 서비스 전체(HTTP, DB, queue, cache)와 LLM 단계를 **동일 trace id로 연동**
- Collector 레벨에서 **필터링/샘플링/마스킹** 같은 운영 정책을 중앙집중화 가능

실무적으로는 “SDK가 제공하는 rich trace”를 **OTel GenAI conventions로 매핑**해 가져오는 방향이 현실적입니다. 실제로 `opentelemetry-python-contrib`에는 Agents runtime trace를 GenAI semantic conventions로 변환하는 instrumentation도 존재합니다. ([github.com](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/instrumentation-genai/opentelemetry-instrumentation-openai-agents-v2/README.rst?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오로 “FastAPI + OpenAI 호출 + tool(외부 HTTP) + OTel Collector로 OTLP export”를 구성해보겠습니다.

- 목표: **요청 1건**이 `api.request`(root) → `gen_ai.chat` → `tool.http`로 이어지는 span tree로 보이게
- 프롬프트/응답 내용은 운영을 가정해 기본은 꺼두고(메타만), 필요 시 이벤트로 켜는 옵션을 둠

### 1) 초기 셋업: 의존성과 OTel export
```bash
python -m venv .venv
source .venv/bin/activate

pip install fastapi uvicorn httpx "openai>=1.0.0" \
  opentelemetry-api opentelemetry-sdk \
  opentelemetry-exporter-otlp \
  opentelemetry-instrumentation-fastapi \
  opentelemetry-instrumentation-httpx \
  opentelemetry-instrumentation-openai-v2
```

OTel 환경변수(Collector로 보냄):
```bash
export OTEL_SERVICE_NAME="llm-api"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"

# 운영 기본값: content는 꺼두고 메타만
export OTEL_INSTRUMENTATION_GENAI_CONTENT_CAPTURE_MODE="no_content"
```

> 참고: OpenAI용 OTel instrumentation은 content 모드를 `span_only/event_only/span_and_event/no_content`처럼 나눠 제공합니다. 운영에서 “내용을 남기지 않되 토큰/모델/latency는 본다”가 가능해집니다. ([opentelemetry-python-contrib.readthedocs.io](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation-genai/openai.html?utm_source=openai))

### 2) 기본 동작: API → LLM → Tool을 하나의 trace로 엮기
```python
# app.py
import os
import time
import httpx
from fastapi import FastAPI
from openai import OpenAI

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

# ---- OTel SDK 초기화 ----
resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "llm-api")})
provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

# ---- Auto-instrumentation ----
OpenAIInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)

client = OpenAI()

async def call_search_tool(query: str) -> str:
    # “도구 호출”은 보통 외부 HTTP/DB로 이어지므로 별도 span으로 감싸면 분해가 쉬움
    with tracer.start_as_current_span("tool.http", attributes={"tool.name": "duckduckgo-lite"}):
        async with httpx.AsyncClient(timeout=5) as h:
            # 예시용(실서비스에서는 사내 검색/벡터DB/파트너 API 등)
            r = await h.get("https://duckduckgo.com/html/", params={"q": query})
            r.raise_for_status()
            return f"search_html_bytes={len(r.content)}"

@app.get("/answer")
async def answer(q: str):
    start = time.time()
    tool_result = await call_search_tool(q)

    # OpenAIInstrumentor가 LLM 호출 span을 자동으로 만들어주고,
    # GenAI semantic conventions에 맞는 attributes(모델/토큰 등)를 채우는 것을 기대
    # (내용 capture는 환경변수로 제어)
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": "You are a precise assistant."},
            {"role": "user", "content": f"Question: {q}\nTool result: {tool_result}\nAnswer briefly."},
        ],
    )

    elapsed_ms = int((time.time() - start) * 1000)
    # 앱 레벨 메타데이터(테넌트, 실험군, 라우팅 등)는 root span 또는 현재 span에 attribute로 추가
    span = trace.get_current_span()
    span.set_attribute("app.latency_ms", elapsed_ms)
    span.set_attribute("app.route", "/answer")

    return {"answer": resp.output_text, "latency_ms": elapsed_ms}
```

예상 결과(관측 백엔드에서 보게 될 구조):
- `GET /answer` (server span)
  - `tool.http` (tool span)
    - `HTTP GET` (httpx instrumentation span)
  - `gen_ai.*` / LLM 호출 span (OpenAI instrumentation)
    - attributes에 model/provider/token usage 등이 붙고, content capture를 켰다면 prompt/completion 이벤트가 추가될 수 있음 ([opentelemetry-semantic-conventions.hexdocs.pm](https://opentelemetry-semantic-conventions.hexdocs.pm/gen-ai-spans.html?utm_source=openai))

### 3) 확장: “내용 저장” 대신 “참조(URI)만” 남기기
운영에서 prompt/응답 원문을 trace에 박아두면 보안/비용이 터집니다. 최근 Python 쪽 instrumentation은 payload를 직접 넣는 대신, `fsspec` 호환 저장소(S3/GCS/local)에 업로드하고 trace에는 `...messages.ref` 같은 참조만 남기는 옵션을 제공합니다. ([opentelemetry-python-contrib.readthedocs.io](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation-genai/openai.html?utm_source=openai))

이 패턴이 실무에서 강력한 이유:
- trace 쿼리는 가볍게(메타/참조만)
- 원문은 접근통제/보존정책/암호화를 별도로 설계 가능
- “재현 필요할 때만” 원문을 따라가면 됨

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) span 경계를 “운영 질문” 기준으로 자르기
OTel 공식 GenAI 예시에서도 agent run 아래에 `chat`, `execute_tool` 같은 자식 span으로 트리를 보여줍니다. ([opentelemetry.io](https://opentelemetry.io/blog/2026/genai-observability/?utm_source=openai))  
당신의 운영 질문이 보통 이거라면:
- “LLM이 느린가? retriever가 느린가? tool이 느린가?”
- “어느 step이 실패했나?”
- “어느 step이 비용을 태우나?”
그 질문에 맞춰 span을 자르면 됩니다. 반대로 “코드 함수 단위”로 자르면 트레이스는 많아지는데 운영 인사이트는 약해집니다.

### Best Practice 2) content capture는 기본 OFF, 필요 시 정책으로 ON
GenAI conventions는 이벤트 기반 content 기록을 “선택”으로 둡니다. ([opentelemetry-semantic-conventions.hexdocs.pm](https://opentelemetry-semantic-conventions.hexdocs.pm/gen-ai-spans.html?utm_source=openai))  
실무 권장:
- 기본: `no_content`로 운영
- 장애/품질 조사: 특정 테넌트/샘플에만 `event_only`로 제한적 활성화
- 더 나아가면 Collector에서 redaction/필터링(PII 마스킹, 특정 키 제거) 정책을 적용

### Best Practice 3) 벤더 중립을 지키되, 프레임워크 통합 포인트를 활용
LangChain 진영도 OpenTelemetry로 tracing을 붙이는 흐름을 문서화하고 있고(기존 tracer provider를 감지해 재사용), 프레임워크가 만들어주는 span + 당신의 서비스 span을 한 트레이스로 묶는 전략이 현실적입니다. ([docs.langchain.com](https://docs.langchain.com/langsmith/trace-with-opentelemetry?utm_source=openai))

### 흔한 함정 1) “토큰/비용”을 attributes로만 두고 끝내기
attributes로 남기면 “요청 단위 분석”은 쉬운데, 팀/테넌트/모델별 비용 추세는 결국 metrics가 필요합니다. GenAI instrumentation/컨벤션이 토큰/시간 관련 메트릭도 다루는 방향으로 가고 있으니(Agents runtime → GenAI conventions 변환에서 duration/token usage를 기록한다고 명시) trace→metric 파이프라인을 염두에 두세요. ([github.com](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/instrumentation-genai/opentelemetry-instrumentation-openai-agents-v2/README.rst?utm_source=openai))

### 흔한 함정 2) sampling을 늦게 고민해서 비용 폭발
LLM 트래픽은 요청당 스팬 수가 많아지고, content까지 켜면 저장비가 급격히 상승합니다. “항상 100% 수집”으로 시작하면, 한 달 안에 Collector/스토리지 비용이 먼저 터집니다.
- 운영: head sampling(예: 5~10%)
- 장애/에러: 에러는 우선 수집(또는 tail-based로 error trace 보존)
- content: 더 낮은 비율로

### 트레이드오프 요약
- 더 많이 남길수록(특히 content) 디버깅은 쉬워지지만 **보안/비용/법무 리스크**가 커짐
- span을 촘촘히 쪼갤수록 원인 분해는 좋아지지만 **수집량/카디널리티**가 증가
- 표준(Otel GenAI)을 따르면 백엔드 교체는 쉬워지지만, “각 벤더 UI의 특화 기능”은 일부 포기해야 함

---

## 🚀 마무리
2026년 7월 기준으로 LLM observability는 “벤더별 tracing”에서 “OpenTelemetry + GenAI semantic conventions”로 표준화되는 방향이 분명해졌습니다. GenAI spans/attributes/events 모델은 **LLM 호출·툴 호출·agent run을 같은 trace 트리로 엮어**, 운영 질문(지연/실패/비용)을 구조적으로 답하게 해줍니다. ([opentelemetry.io](https://opentelemetry.io/blog/2026/genai-observability/?utm_source=openai))

도입 판단 기준은 간단합니다:
- (YES) 프로덕션에서 multi-step LLM 워크플로를 돌리고, “이번 요청이 왜 이랬지?”를 빠르게 쪼개고 싶다 → OTel tracing부터
- (YES) 프롬프트/응답 원문 저장이 부담된다 → `no_content` + ref(URI) 패턴으로 설계 ([opentelemetry-python-contrib.readthedocs.io](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation-genai/openai.html?utm_source=openai))
- (NO/보류) 아직 PoC이고 운영 질문이 명확하지 않다 → 최소 계측(HTTP/에러/latency)만 하고, LLM span은 나중에

다음 학습 추천:
- OTel GenAI semantic conventions(어떤 필드를 남겨야 “나중에 쿼리 가능한 데이터”가 되는지) ([opentelemetry-semantic-conventions.hexdocs.pm](https://opentelemetry-semantic-conventions.hexdocs.pm/gen-ai-spans.html?utm_source=openai))
- OpenTelemetry 공식 GenAI observability 사례 글(어떤 span tree가 “읽기 좋은지”) ([opentelemetry.io](https://opentelemetry.io/blog/2026/genai-observability/?utm_source=openai))
- 사용 중인 프레임워크(LangChain/Agents SDK 등)의 OTel 연동 포인트(중복 트레이싱/컨텍스트 전파 충돌 방지) ([docs.langchain.com](https://docs.langchain.com/langsmith/trace-with-opentelemetry?utm_source=openai))