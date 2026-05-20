---
title: "LLM 앱이 “조용히” 망가질 때: 2026년 5월 기준 LangSmith vs Langfuse로 모니터링·디버깅·비용 추적까지 설계하기"
date: 2026-05-20 04:15:20 +0900
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
LLM 앱 운영에서 진짜 골칫거리는 **장애처럼 티 나게 죽는 문제**가 아니라, “그럴듯하게 동작하지만” 아래가 서서히 망가지는 상황입니다.

- 특정 세션/사용자군에서만 hallucination 증가
- RAG 검색 품질 저하로 재시도(retry) 폭증 → **비용이 먼저 터짐**
- 프롬프트/모델 버전 변경 후 latency p95 악화
- 멀티스텝(agent/tool/RAG) 파이프라인에서 병목 지점이 로그로는 안 보임

이때 필요한 게 **LLM Observability**(trace tree + 비용/토큰 + 품질 신호)이고, 실무에서 가장 많이 비교하는 조합이 **LangSmith**(LangChain 생태계 친화, 상용)와 **Langfuse**(OpenTelemetry 기반, 오픈소스/셀프호스트 가능)입니다. Langfuse는 SDK가 **OpenTelemetry(OTel) 위에 구축**되어 컨텍스트 전파(부모/자식 span)가 강점이고, trace/observation/score를 ClickHouse 등으로 분석 친화적으로 가져갑니다. ([langfuse.com](https://langfuse.com/docs/observability/sdk/overview?utm_source=openai)) LangSmith도 **OTel 포맷 ingest**를 지원해 표준 파이프라인으로 붙일 수 있습니다. ([langchain.com](https://www.langchain.com/blog/opentelemetry-langsmith?utm_source=openai))

### 언제 쓰면 좋나
- LLM 호출이 “1회”가 아니라 **RAG→rerank→generation→postprocess→tool**처럼 다단계일 때
- 비용이 매출/트래픽에 비례해 커져서 **per-feature/per-tenant 비용 배분**이 필요한 시점
- “디버깅 가능성”을 위해 **재현 가능한 입력/모델/프롬프트/버전/메타데이터**를 남겨야 할 때

### 언제 쓰면 안 되나
- 완전한 PoC 단계에서, 사용자 데이터/프롬프트를 외부로 보내면 안 되는데 셀프호스트 역량도 없을 때(이 경우는 최소 로깅+샘플링부터)
- 단일 모델 단일 호출만 있는 매우 단순한 워크로드에서 “툴 도입 비용(학습/운영/데이터 마스킹)”이 더 클 때
- 고보안 환경인데 “마스킹 정책/PII 처리/보관기간” 설계 없이 무턱대고 모든 입력/출력을 저장하려는 경우(관측이 아니라 리스크가 됨)

---

## 🔧 핵심 개념
### 1) Trace / Span(Observation) / Generation / Score
두 제품 모두 본질은 같습니다.

- **Trace**: 한 유저 요청의 end-to-end 실행 단위(루트)
- **Span/Observation**: trace 내부 단계(예: retrieval, rerank, tool call, parse)
- **Generation**: LLM 호출을 표현하는 특수 span(모델/파라미터/토큰/비용을 붙이는 핵심)
- **Score**: 품질 신호(LLM-as-a-judge, human annotation, 규칙 기반 등)

Langfuse는 OTel 개념을 그대로 가져오되, **Generation에 model/usage_details(tokens)/cost_details** 같은 필드를 얹어 “LLM 전용 관측”으로 다룹니다. ([langfuse.com](https://langfuse.com/docs/observability/sdk/overview?utm_source=openai)) 이 구조 덕분에 “왜 비용이 늘었는지”가 보통 **(a) 호출 횟수 증가**인지 **(b) 프롬프트 길이 증가**인지 **(c) 특정 단계가 비싼 모델로 바뀌었는지**로 쪼개져 보입니다.

### 2) 컨텍스트 전파(Context propagation)가 디버깅 품질을 결정한다
실무에서 흔한 실패는 “로그는 남는데 서로 연결이 안 되는 것”입니다.

- async/queue 작업에서 trace가 끊김
- tool 호출이 별도 모듈이라 trace에 안 묶임
- 같은 요청인데 span parent가 엉킴

Langfuse는 SDK가 OTel 기반이라 **현재 활성 span의 자식으로 자동 연결**되는 흐름을 강조합니다. ([langfuse.com](https://langfuse.com/docs/observability/sdk/overview?utm_source=openai)) LangSmith도 OTel 기반으로 추적을 구성할 수 있어, “표준 OTel 파이프라인”을 공통 기반으로 잡으면 두 제품 모두에 전략적으로 대응 가능합니다. ([langchain.com](https://www.langchain.com/blog/opentelemetry-langsmith?utm_source=openai))

### 3) 비용 추적: “토큰”보다 중요한 건 비용 귀속(allocation)
2026년 운영에서 비용 최적화는 대개 “토큰 줄이기”보다 아래가 더 큽니다.

- 어떤 tenant / endpoint / agent가 비용을 태우는지
- 실패(retry, fallback, tool loop)로 비용이 새는지
- A/B 프롬프트/모델 전환이 비용 대비 품질 개선인지

Langfuse는 Prompt Management에서 **A/B 라벨(prod-a/prod-b)**로 실트래픽 비교를 하고, latency/cost/token/평가 지표를 버전별로 보게 합니다. ([langfuse.com](https://langfuse.com/docs/prompt-management/features/a-b-testing?utm_source=openai)) 또한 self-host 시 아키텍처가 Postgres+ClickHouse+S3(Blob)+Redis로 분리되어, 대량 이벤트 처리(큐잉/배치 ingest)를 비용/성능 관점에서 설계해둔 편입니다. ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai))  
반면 LangSmith는 팀/조직에서 빠르게 쓰기 좋은 SaaS 성격이 강하고, 플랜은 좌석/트레이스 기준 과금이 명확히 제시돼 있습니다. ([langchain.com](https://www.langchain.com/pricing?utm_source=openai))

---

## 💻 실전 코드
아래는 “현실적인” 시나리오로, **FastAPI 기반 RAG API**에서 다음을 한 번에 해결합니다.

- 요청 단위 trace 생성(루트)
- retrieval / rerank / generation을 child span으로 분리
- userId/sessionId/tenant/version/tag로 비용 귀속 키를 박음
- LLM 호출 토큰/비용을 관측(가능한 경우 SDK/인스트루먼테이션이 자동 수집)

### 0) 의존성/환경변수
```bash
pip install fastapi uvicorn httpx opentelemetry-sdk opentelemetry-api

# Langfuse 예시(문서 기준)
npm install @langfuse/tracing @langfuse/otel @opentelemetry/sdk-node
# (여기선 Python 예시를 보여주지만, Langfuse는 OTel 기반이라는 점이 핵심)
```

> 노트: Langfuse는 JS/TS 쪽에서 `@langfuse/otel`을 명시적으로 안내하며 OTel 기반을 강조합니다. ([langfuse.com](https://langfuse.com/docs/observability/sdk/overview?utm_source=openai))  
> LangSmith는 OTel 포맷 ingest를 지원하므로 “OTel exporter 목적지”만 바꾸는 형태로 통합하는 전략이 가능합니다. ([langchain.com](https://www.langchain.com/blog/opentelemetry-langsmith?utm_source=openai))

### 1) FastAPI + OTel로 trace 뼈대 만들기
```python
# app.py
import os
import time
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, Header, Request
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# 실제로는 OTLP exporter를 붙여 Langfuse/LangSmith(OTel ingest)로 보냅니다.
# 여기서는 "실행 가능한" 예제를 위해 Console exporter를 사용합니다.
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

# ---------- Tracing setup ----------
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("rag-api")

app = FastAPI()


# ---------- Business logic (realistic-ish) ----------
async def retrieve(query: str) -> List[Dict[str, Any]]:
    # 예: 벡터DB 검색을 흉내(실무에선 Pinecone/Weaviate/pgvector 등)
    await httpx.AsyncClient().aclose()
    return [
        {"doc_id": "kb:123", "text": "Langfuse는 OpenTelemetry 기반 SDK로 trace/span을 구성한다."},
        {"doc_id": "kb:456", "text": "LangSmith는 OTel ingest를 지원해 표준 파이프라인을 구성할 수 있다."},
    ]


def rerank(query: str, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # 예: cross-encoder rerank 자리(실무에선 별도 모델 호출일 수 있음)
    return sorted(docs, key=lambda d: d["doc_id"])


async def call_llm(prompt: str) -> str:
    # 실무에선 OpenAI/Anthropic/Bedrock/Vertex 등을 호출
    # 여기서는 네트워크 없이 실행 가능하도록 mock
    time.sleep(0.2)
    return f"요약 답변: {prompt[:80]}..."


@app.post("/ask")
async def ask(
    req: Request,
    x_tenant_id: str = Header(default="tenant-demo"),
    x_user_id: str = Header(default="user-unknown"),
    x_session_id: str = Header(default="sess-unknown"),
):
    body = await req.json()
    query = body["query"]

    # 루트 span = 한 요청(Trace)
    with tracer.start_as_current_span("rag.request") as root:
        # 비용 귀속/필터링을 위한 공통 태그(실무에서 가장 중요)
        root.set_attribute("tenant.id", x_tenant_id)
        root.set_attribute("user.id", x_user_id)
        root.set_attribute("session.id", x_session_id)
        root.set_attribute("app.version", os.getenv("APP_VERSION", "2026.05.20"))
        root.set_attribute("route", "/ask")

        with tracer.start_as_current_span("rag.retrieve") as s1:
            s1.set_attribute("query.len", len(query))
            docs = await retrieve(query)
            s1.set_attribute("docs.count", len(docs))

        with tracer.start_as_current_span("rag.rerank") as s2:
            ranked = rerank(query, docs)
            s2.set_attribute("top.doc_id", ranked[0]["doc_id"])

        # LLM 호출은 별도 span으로 분리 (Generation으로 매핑되는 지점)
        with tracer.start_as_current_span("rag.generation") as gen:
            context = "\n\n".join([d["text"] for d in ranked[:2]])
            prompt = f"질문: {query}\n\n근거:\n{context}\n\n한국어로 짧게 답해줘."
            gen.set_attribute("llm.model", os.getenv("LLM_MODEL", "mock-gpt"))
            gen.set_attribute("prompt.chars", len(prompt))

            answer = await call_llm(prompt)
            gen.set_attribute("answer.chars", len(answer))

        return {"answer": answer, "citations": [d["doc_id"] for d in ranked[:2]]}
```

#### 실행
```bash
uvicorn app:app --reload --port 8000
curl -X POST http://localhost:8000/ask \
  -H 'content-type: application/json' \
  -H 'x-tenant-id: acme' -H 'x-user-id: u-42' -H 'x-session-id: s-99' \
  -d '{"query":"Langfuse와 LangSmith를 비용/디버깅 관점에서 어떻게 비교해?"}'
```

#### 예상 출력(요지)
- API 응답: `{"answer":"요약 답변: 질문: ...", "citations":[...]}`
- 콘솔: `rag.request` 아래에 `rag.retrieve` → `rag.rerank` → `rag.generation` span 트리가 출력

### 2) “제품 선택”을 돕는 연결 방식
- **Langfuse로 보낼 때**: OTel exporter(OTLP) 목적지를 Langfuse ingest로 설정하고, Langfuse가 권장하는 속성/Generation 매핑을 사용합니다(OTel 기반, 컨텍스트 전파 강점). ([langfuse.com](https://langfuse.com/docs/observability/sdk/overview?utm_source=openai))
- **LangSmith로 보낼 때**: OTel 포맷을 LangSmith endpoint로 export합니다(OTel ingest 지원). ([langchain.com](https://www.langchain.com/blog/opentelemetry-langsmith?utm_source=openai))

이렇게 하면 앱 코드는 “OTel 중심”으로 안정화되고, 특정 벤더 기능(프롬프트 관리/평가 UI 등)만 선택적으로 얹는 구조가 됩니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) 비용 귀속 키를 “루트에 강제”하라
`tenant.id`, `user.id`, `session.id`, `app.version`, `route`, `feature_flag` 같은 키는 **루트 span에 무조건** 박고, 하위 span에도 자동 전파되게 해야 합니다. Langfuse는 `propagate_attributes()` 같은 “하위 관측으로 속성 전파” 컨셉을 명시합니다. ([langfuse.com](https://langfuse.com/docs/observability/sdk/overview?utm_source=openai))  
이게 없으면 “대시보드 예쁘게 보기”는 가능해도 **FinOps/원가 배분**이 안 됩니다.

### Best Practice 2) 오프라인 평가(Experiment)와 온라인 모니터링을 루프로 묶어라
Langfuse는 Dataset 기반 Experiment(오프라인)와 live trace scoring(온라인)을 **지속 개선 루프**로 설명합니다. ([langfuse.com](https://langfuse.com/docs/evaluation/concepts?utm_source=openai))  
운영 팁은 단순합니다: “장애 케이스”를 발견하면 그 입력을 Dataset으로 승격시켜 다음 배포에서 regression을 막습니다.

### Best Practice 3) 프롬프트 변경은 A/B(또는 카나리)로 비용까지 같이 보라
프롬프트가 좋아져도 답변이 길어지면 토큰/비용이 늘 수 있습니다. Langfuse는 프롬프트 버전 라벨로 A/B를 돌리며 **latency/cost/token/eval**을 같이 비교하는 흐름을 제공합니다. ([langfuse.com](https://langfuse.com/docs/prompt-management/features/a-b-testing?utm_source=openai))  
“품질↑ 비용↑” 상황에서 의사결정이 빨라집니다.

### 흔한 함정 1) “전부 다 trace”가 오히려 비용 폭탄이 된다
OTel 기반은 강력하지만, 잘못 붙이면 **의도치 않은 라이브러리/백그라운드 span까지** 모두 빨아들여 이벤트가 폭증합니다. 특히 “전역 TracerProvider에 붙어서 전부 캡처” 류 이슈는 커뮤니티에서도 자주 언급됩니다(진위/상황은 환경마다 다르지만, 위험 신호로 보세요). ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1rs2r2u/psa_check_your_langfuse_traces_their_sdk/?utm_source=openai))  
대책:
- 중요한 엔드포인트만 샘플링(또는 특정 tenant만)
- LLM 관련 instrumentation scope만 포함
- PII/대용량 payload는 마스킹/비저장(또는 S3 분리 저장)

### 흔한 함정 2) 셀프호스트는 “무료”가 아니다
Langfuse 셀프호스트는 Postgres/ClickHouse/Redis/S3(Blob) 등 구성으로, 운영 난이도와 비용(백업/업그레이드/모니터링)이 생깁니다. ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai))  
보안/데이터 레지던시가 핵심이면 셀프호스트가 답이지만, 단순히 “SaaS 비용 아끼려고” 들어가면 TCO가 역전될 수 있습니다.

### 트레이드오프 정리(비용/성능/안정성)
- **LangSmith**: 팀이 빠르게 붙여서 “지금 당장 디버깅/평가/협업”을 하기에 편함. 대신 플랜 구조상 좌석/트레이스 기준으로 비용이 커질 수 있어, 규모가 커질수록 **trace 설계(샘플링/보관기간)**가 중요해집니다. ([langchain.com](https://www.langchain.com/pricing?utm_source=openai))
- **Langfuse**: OTel 네이티브 + 오픈소스/셀프호스트로 데이터 통제력이 좋고, 대규모 분석(ClickHouse) 친화적. 대신 인프라 운영/업그레이드/보안 설정이 “제품 기능”의 일부가 됩니다. ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai))

---

## 🚀 마무리
2026년 5월 기준으로 LangSmith와 Langfuse를 “기능 나열”로 비교하면 결론이 흐립니다. 대신 **내 프로젝트에 적용 가능한 판단 기준**은 아래 3개입니다.

1) **OTel 중심으로 계측(Instrumentation) 표준화할 수 있는가?**  
→ 가능하면 벤더 락인을 줄이고, Langfuse/ LangSmith(OTel ingest) 모두로 유연하게 갈 수 있습니다. ([langfuse.com](https://langfuse.com/docs/observability/sdk/overview?utm_source=openai))

2) **데이터 레지던시/보안 때문에 셀프호스트가 필수인가?**  
→ 필수면 Langfuse 쪽이 자연스럽고, ClickHouse/Postgres/S3/Redis 운영을 감당할 준비가 되어야 합니다. ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai))

3) **비용 추적의 목표가 ‘대시보드’인가, ‘원가 배분/최적화’인가?**  
→ 후자라면 trace에 tenant/user/session/version을 강제하고, 프롬프트 A/B와 평가(Score)를 비용과 함께 묶어 의사결정 루프를 만들어야 합니다. ([langfuse.com](https://langfuse.com/docs/prompt-management/features/a-b-testing?utm_source=openai))

### 다음 학습 추천
- (공통) OpenTelemetry 컨텍스트 전파/샘플링 전략을 먼저 정리
- (Langfuse) Prompt Experiments + Dataset 루프를 팀 개발 프로세스에 넣기 ([langfuse.com](https://langfuse.com/docs/evaluation/features/prompt-experiments?utm_source=openai))
- (LangSmith) OTel ingest + Annotation queue를 통한 human feedback 파이프라인 설계 ([langchain.com](https://www.langchain.com/blog/opentelemetry-langsmith?utm_source=openai))

원하시면, 당신의 현재 스택(예: LangGraph/CrewAI/Vercel AI SDK, 모델 프로바이더, 트래픽, 보안 요구사항)을 기준으로 **(a) 어떤 span을 어떤 이름/속성으로 쪼갤지 (b) 샘플링/보관기간 정책 (c) 비용 귀속 키 설계**까지 “바로 적용 가능한” 템플릿으로 구체화해 드릴게요.