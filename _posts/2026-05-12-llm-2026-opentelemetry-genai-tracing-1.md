---
title: "LLM 앱이 ‘왜/어디서’ 무너지는지 한 번에 추적하기: 2026년 OpenTelemetry GenAI Tracing 실전 가이드"
date: 2026-05-12 03:54:11 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-05]
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
LLM 앱이 프로덕션에 올라가면 장애 형태가 전통적인 웹/백엔드와 달라집니다. “요청이 느리다”가 아니라 **어떤 프롬프트/도구 호출/검색 결과 조합에서** 지연·비용 폭증·환각·루프(반복 tool call)·컨텍스트 누락이 발생합니다. 이때 로그만으로는 원인 추적이 거의 불가능하고, 벤더별 대시보드만으로는 **서비스 전체(HTTP → queue → worker → DB/vectorDB → LLM → tool)** 흐름을 하나의 실행 맥락으로 보기도 어렵습니다.

그래서 2025년 말~2026년 초에 업계가 빠르게 합의한 방향이 **OpenTelemetry(OTel) tracing + GenAI semantic conventions**입니다. LLM 호출을 “특수한 외부 API”가 아니라, 분산 트레이스의 **표준 span**으로 모델/토큰/캐시/안전필터/툴 호출까지 구조적으로 남겨서, Jaeger/Tempo/Uptrace/SigNoz/LangSmith 등 어디로든 보낼 수 있게 만드는 접근입니다. ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/?utm_source=openai))

**언제 쓰면 좋나**
- RAG/Agent처럼 단계가 많고(검색→정제→LLM→툴→재질문…), 장애가 “특정 단계”에서 난다.
- 비용(토큰/호출 수)과 latency(p95/p99)가 동시에 중요하다.
- LLM 벤더/프레임워크를 자주 바꾸거나(멀티 LLM, 라우팅), 팀/서비스 경계(마이크로서비스, 워커, 메시지큐)를 넘는다.

**언제는 오히려 독이 되나**
- PII/기밀 프롬프트가 많고, 조직적으로 “content capture 금지”가 확고한데(감사/컴플라이언스) 아직 redaction 파이프라인이 없다. GenAI conventions는 프롬프트/완성 텍스트를 event로 남길 수 있어 위험합니다. ([uptrace.dev](https://uptrace.dev/blog/opentelemetry-ai-systems?utm_source=openai))
- 트래픽이 너무 큰데(대량 챗봇) 샘플링/필터링 없이 span을 모두 수집하려 한다 → 비용/성능이 관측 자체 때문에 터집니다(collector/스토리지 포함).

---

## 🔧 핵심 개념
### 1) “LLM observability”를 tracing으로 풀 때의 모델
핵심은 **한 사용자 요청(Request)** 을 trace로 잡고, 그 안에 다음을 **부모-자식 span**으로 계층화하는 것입니다.

- `HTTP POST /chat` (server span)
  - `retrieval`(vector search / DB query spans)
  - `embeddings`(optional)
  - `chat openai` 같은 LLM client span
  - `tool` 실행 spans(HTTP/DB/내부 함수…)
  - `rerank/summarize` 같은 후처리 spans

이 구조가 있어야 “느린 원인이 LLM이냐 retrieval이냐”, “비용이 폭증한 구간이 어디냐(반복 루프 포함)”를 시간축/트리로 바로 봅니다.

### 2) GenAI semantic conventions: ‘표준 필드’가 중요한 이유
OTel은 원래 HTTP/DB 같은 범용 semantic conventions가 강합니다. GenAI는 여기에 **LLM 전용 속성/이벤트 규약**을 추가해, 백엔드가 달라도 동일한 차트/필터링을 가능하게 합니다. 예를 들어:
- `gen_ai.operation.name` (chat, embeddings 등)
- `gen_ai.system` (openai, anthropic 등)
- `gen_ai.request.model` (요청한 모델)
- (선택) prompt/completion content를 span event로 남기는 구조(프라이버시 이슈로 기본 비활성 권장) ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/?utm_source=openai))

이 표준화가 없으면 팀마다 `model`, `llm_model`, `openai_model` 같은 태그 난립 → 검색/알람/대시보드가 깨집니다.

### 3) OpenAI Agents SDK / LangChain 생태계의 변화(2026년 5월 관점)
- OpenAI Agents SDK는 tracing 표면을 제공하고, 민감 데이터 포함 여부를 환경변수로 제어하는 등 “기본값은 보수적으로” 설계되어 있습니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tracing/?utm_source=openai))  
- Grafana는 Agents SDK + OTel로 Tempo(또는 Grafana Cloud Traces)로 보내는 예시를 공식 블로그로 안내했습니다. ([grafana.com](https://grafana.com/blog/observing-agentic-ai-workflows-with-grafana-cloud-opentelemetry-and-the-openai-agents-sdk/?utm_source=openai))  
- LangSmith는 OTel을 end-to-end로 지원해, “OTel로 표준화”한 뒤 LangChain 런을 관측하는 흐름을 제공합니다. ([blog.langchain.dev](https://blog.langchain.dev/end-to-end-opentelemetry-langsmith/?utm_source=openai))  
- 관측 글들에서 공통으로 강조하는 포인트는 **content capture/샘플링/컨텍스트 전파**(특히 멀티 워커·큐·멀티 에이전트)입니다. ([uptrace.dev](https://uptrace.dev/blog/opentelemetry-ai-systems?utm_source=openai))

---

## 💻 실전 코드
아래는 “웹 API + 워커” 구조에서 **하나의 trace로** (1) HTTP 요청, (2) RAG retrieval, (3) OpenAI Agents SDK 에이전트 실행, (4) 결과 반환을 연결해 보는 현실형 예제입니다. 백엔드는 **OTel Collector → Grafana Tempo**로 가정합니다(벤더는 Uptrace/SigNoz 등으로 바꿔도 동일). Grafana가 Agents SDK + OTel 내보내기를 안내한 흐름을 그대로 따라가되, RAG span/속성/민감정보 전략까지 포함합니다. ([grafana.com](https://grafana.com/blog/observing-agentic-ai-workflows-with-grafana-cloud-opentelemetry-and-the-openai-agents-sdk/?utm_source=openai))

### 1) 로컬 실행 구성(Collector + Tempo)
```bash
# 1) docker-compose.yml 작성 후 실행 (Tempo/Collector 예시)
cat > docker-compose.yml <<'YAML'
version: "3.9"
services:
  tempo:
    image: grafana/tempo:latest
    command: ["-config.file=/etc/tempo.yaml"]
    volumes:
      - ./tempo.yaml:/etc/tempo.yaml:ro
    ports:
      - "3200:3200"   # tempo query
      - "4317:4317"   # otlp grpc ingest (tempo can ingest, but usually via collector)
  otelcol:
    image: otel/opentelemetry-collector:latest
    command: ["--config=/etc/otelcol.yaml"]
    volumes:
      - ./otelcol.yaml:/etc/otelcol.yaml:ro
    ports:
      - "4317:4317"   # OTLP gRPC receiver
      - "4318:4318"   # OTLP HTTP receiver
    depends_on: [tempo]
YAML

cat > tempo.yaml <<'YAML'
server:
  http_listen_port: 3200
distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo
YAML

cat > otelcol.yaml <<'YAML'
receivers:
  otlp:
    protocols:
      grpc:
      http:

processors:
  batch:
  # 실무에서는 여기서 redaction/필터링/샘플링을 강하게 걸어야 합니다.
  # (tail_sampling, attributes, transform 등)

exporters:
  otlp:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp]
YAML

docker compose up -d
```

### 2) Python 앱: FastAPI + Agents SDK + 수동 RAG span
```python
# app.py
import os
import time
from fastapi import FastAPI
from pydantic import BaseModel

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# OpenAI Agents SDK (tracing surface 제공)
# - SDK 문서에서 tracing 설정/민감데이터 플래그가 언급됨
from agents import Agent, Runner  # 패키지명/사용법은 SDK 버전에 따라 다를 수 있음

# ---- OTel SDK bootstrap ----
resource = Resource.create({
    "service.name": "llm-observability-demo",
    "deployment.environment": os.getenv("ENV", "local"),
})

provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(
    OTLPSpanExporter(endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"), insecure=True)
)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("demo")

# 민감 데이터(프롬프트/응답)를 trace에 포함할지: 기본은 false 권장
# SDK가 환경변수로 제어 가능하다고 명시
os.environ.setdefault("OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA", "0")  # ([openai.github.io](https://openai.github.io/openai-agents-python/tracing/?utm_source=openai))

# ---- App ----
app = FastAPI()

class ChatReq(BaseModel):
    user_id: str
    query: str

def fake_vector_search(query: str):
    # 현실에서는 vectorDB 호출 + topK 문서/스코어
    time.sleep(0.05)
    return [
        {"doc_id": "kb:pricing-2026", "score": 0.82, "snippet": "Pricing tiers ..."},
        {"doc_id": "kb:policy-retention", "score": 0.77, "snippet": "Data retention ..."},
    ]

agent = Agent(
    name="support-agent",
    instructions="You are a support agent. Answer based on provided context.",
    # tools=[...]  # tool 호출이 있다면 여기서 추가(HTTP, DB, 내부 함수 등)
)

@app.post("/chat")
async def chat(req: ChatReq):
    # 1) request 단위 root span(서버 프레임워크 자동 계측을 붙이면 생략 가능)
    with tracer.start_as_current_span("chat.request") as root:
        root.set_attribute("enduser.id", req.user_id)

        # 2) RAG retrieval span: GenAI와 별개로 '내 파이프라인'을 보여주는 핵심
        with tracer.start_as_current_span("rag.retrieve") as s:
            s.set_attribute("db.system", "vector")
            s.set_attribute("rag.top_k", 2)
            docs = fake_vector_search(req.query)
            s.set_attribute("rag.hit_count", len(docs))
            # 문서 내용 전체를 span에 넣는 건 보통 금지(PII/비용). doc_id/score만 남기는 식 추천.

        # 3) LLM/Agent 실행 (Agents SDK tracing이 내부 span을 만들어줌)
        #    목표: 이 span들이 rag.retrieve 아래로 붙어, 한 trace에서 보이게 만들기
        context = "\n".join([f"- ({d['doc_id']}, {d['score']}) {d['snippet']}" for d in docs])

        prompt = f"User question: {req.query}\n\nContext:\n{context}"

        # Runner.run(...) 내부에서 GenAI semantic conventions에 맞는 span/attributes를 내보내는 흐름을 기대
        # (SDK/통합에 따라 자동 계측 수준은 다를 수 있음)
        result = await Runner.run(agent, prompt)

        # 4) 응답 요약 속성(민감정보 제외)
        root.set_attribute("app.answer.length", len(str(result.final_output)))

        return {"answer": result.final_output, "trace_hint": "Check Tempo/your tracing backend"}
```

**예상 출력/관측 포인트**
- Tempo/Jaeger UI에서 하나의 trace 안에 `chat.request` → `rag.retrieve` → (Agents SDK가 생성한) `chat openai`/tool spans가 트리로 보여야 합니다.
- `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=0`이면 prompt/completion 전문이 이벤트로 찍히지 않거나 최소화되어야 합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tracing/?utm_source=openai))

### 3) 확장: “GenAI 표준 속성”을 내 파이프라인 span에도 연결하기
LLM span만 표준화하면 “retrieval이 어떤 모델 호출로 이어졌는지”를 쿼리하기 어렵습니다. 실무에서는 상위 span에 아래 같은 correlation 속성을 같이 넣습니다.
- `gen_ai.request.model`(실제 선택된 모델)
- `gen_ai.operation.name`(chat/embeddings)
- `llm.route`(router 결정: cheap vs smart)
이렇게 하면 “특정 모델 선택 시 retrieval p95가 왜 늘었지?” 같은 교차 분석이 쉬워집니다. GenAI conventions 자체가 표준 키를 제공한다는 점이 이득입니다. ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) content capture는 ‘기술’이 아니라 ‘정책’으로 다뤄라
프롬프트/응답을 trace 이벤트로 남기면 디버깅은 쉬워지지만, 저장·전송·접근권한이 전부 사고 지점이 됩니다. 실무 팁:
- 기본값은 **미수집**(또는 최소 수집)으로 두고, 장애 세션에만 “승인된 토큰/기간”으로 활성화
- Collector에서 **redaction/필터링/샘플링**을 중앙 통제(앱 코드에 흩뿌리지 말기)
Uptrace 쪽 가이드도 “기본 비활성 + redaction/필터링/샘플링”을 강하게 권장합니다. ([uptrace.dev](https://uptrace.dev/blog/opentelemetry-ai-systems?utm_source=openai))

### Best Practice 2) 컨텍스트 전파가 ‘멀티 에이전트/큐’에서 제일 자주 깨진다
요즘 장애의 1순위는 LLM 자체보다 “워크플로우 연결”입니다. 한 에이전트가 다른 워커에 작업을 던지면 trace가 두 동강 나서, 원인 분석이 불가능해집니다. 메시지큐 헤더/메타데이터로 W3C tracecontext를 전파하고, 소비자 쪽에서 parent를 이어붙이세요. 멀티 에이전트에서 이걸 강조하는 글이 많습니다. ([zylos.ai](https://zylos.ai/research/2026-02-28-opentelemetry-ai-agent-observability?utm_source=openai))

### 함정 1) “LLM span만” 찍고 끝내기
LLM 호출 span은 눈에 잘 띄지만, 실제 병목은 retrieval(느린 vector search), rerank, tool(외부 API rate limit), DB 트랜잭션인 경우가 더 많습니다. LLM 주변 단계도 **같은 trace 트리 안에** 있어야 “내가 고칠 지점”이 보입니다.

### 함정 2) 무지성 전수 샘플링(= 비용 폭탄)
LLM 트래픽은 span당 attribute가 많고(모델/토큰/에러/재시도…), 이벤트까지 넣으면 더 커집니다. 해결책:
- head sampling(초기 확률) + tail sampling(오류/느림/고비용 trace만 유지)
- “고비용 조건”을 토큰/호출수로 정의해 tail sampling 조건에 넣기
- BatchSpanProcessor/collector batch 튜닝으로 네트워크 오버헤드 줄이기

---

## 🚀 마무리
2026년 5월 기준 LLM/Agent observability의 실전 해답은 “특정 벤더 툴”이 아니라 **OpenTelemetry tracing 위에 GenAI semantic conventions로 표준화**하는 쪽으로 빠르게 수렴하고 있습니다. ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/?utm_source=openai))  
도입 판단 기준은 간단합니다.

- **워크플로우가 3단계 이상**(RAG/Agent/tool)이고, 장애 원인이 “조합”에서 발생한다 → OTel tracing이 거의 필수
- 프롬프트/응답이 민감하다 → content capture는 기본 off, collector에서 redaction/샘플링 체계를 먼저
- 조직 내 서비스가 여러 개다 → tracecontext 전파(HTTP/queue)까지 설계에 포함

다음 학습으로는 (1) OTel GenAI semantic conventions 문서로 표준 attribute/event를 확정하고, ([opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/?utm_source=openai)) (2) OpenAI Agents SDK tracing 옵션과 민감 데이터 플래그의 동작을 실제로 검증한 뒤 ([openai.github.io](https://openai.github.io/openai-agents-python/tracing/?utm_source=openai)) (3) collector에서 tail sampling + redaction 파이프라인을 구축하는 순서를 추천합니다.