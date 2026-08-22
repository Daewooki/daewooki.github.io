---
title: "2026년 8월, LLM 앱 모니터링의 현실: LangSmith vs Langfuse로 “디버깅·비용·품질”을 한 번에 잡는 설계"
date: 2026-08-22 01:40:52 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-08]
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
LLM 애플리케이션을 운영해보면 문제는 늘 비슷한 형태로 터집니다.

- 같은 입력인데 **가끔만** 답이 이상하다(=재현 어려운 non-determinism)
- Agent/RAG 파이프라인에서 **어느 단계가** 망가졌는지 모른다(도구 호출/리트라이/컨텍스트 길이 폭증)
- 월말에 청구서 보고서야 “비용이 올랐네”를 알지만, **세션/유저/기능 단위로** 왜 올랐는지 모른다(원인-결과 단절)

이때 필요한 게 “로그”가 아니라 **trace 중심의 LLM observability**입니다. LangSmith와 Langfuse는 공통적으로 hierarchical trace로 LLM call, tool invocation, retrieval step을 묶어 보여주고, token/cost/latency를 붙여서 “원인”까지 역추적하게 해줍니다. ([langfuse.com](https://langfuse.com/?utm_source=openai))

언제 쓰면 좋나?
- RAG/Agent처럼 **단계가 여러 개**(retrieval → rerank → synthesize → tool → verify)인 앱
- 운영 중 “품질”을 수치화(Evals/휴먼 피드백)해서 **회귀(regression)** 를 막아야 하는 팀 ([docs.langchain.com](https://docs.langchain.com/langsmith/evaluation-concepts?mode=ui&utm_source=openai))
- “기능/고객/세션” 단위로 **비용을 귀속**(attribution)해야 하는 B2B/멀티테넌트

언제 쓰지 말아야 하나?
- 단발성 PoC인데 호출 수가 적고, 장애 분석을 사람이 수동으로 해도 된다
- 규제/보안상 trace에 payload를 저장할 수 없는데, **데이터 마스킹/저장 전략**이 없는 상태에서 “일단 켜자”
- “모니터링 툴 도입”이 목표가 되어, 정작 **태깅 규약(user_id/session_id/use_case)** 없이 이벤트만 쌓는 경우(대시보드는 예쁘지만 의사결정이 불가능)

---

## 🔧 핵심 개념
### 1) Trace/Span이 아니라 “LLM 앱의 실행 그래프”를 남긴다
전통 APM은 request 단위 trace로 충분했지만, LLM 앱은 한 request 안에서:
- 여러 LLM generation
- 여러 retrieval/embedding
- tool call + retry + fallback
이 반복됩니다. 그래서 LangSmith/Langfuse는 run(혹은 observation) 트리를 만들어 “부모-자식 실행”을 그대로 보존합니다. Langfuse는 이를 hierarchical traces로 설명합니다. ([langfuse.com](https://langfuse.com/?utm_source=openai))

핵심은 **한 트리 안에서** 다음을 같이 보는 겁니다.
- latency: 어느 노드가 느렸는지
- tokens/cost: 어느 노드가 돈을 태웠는지
- input/output: 어느 단계에서 문맥이 깨졌는지(단, 저장/마스킹 정책 필요)

### 2) 비용 추적의 본질: “토큰”이 아니라 “가격 테이블 + 사용량 + 귀속 키”
둘 다 비용을 자동 계산하려면 최소한 다음이 필요합니다.
- model/provider 식별
- usage(입력/출력 토큰 등)
- (선택) 모델 가격 테이블 매핑

LangSmith는 token usage가 들어오면 model/provider와 가격 테이블을 기반으로 cost를 계산하고, trace UI에서 breakdown을 제공합니다. ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))  
Langfuse도 generation/embedding observation에 usage를 기록하고, model definition(usage type별 price)을 통해 cost를 **ingest 또는 infer**로 채웁니다. 또한 ingested 값이 inferred보다 우선입니다. ([langfuse.com](https://langfuse.com/docs/observability/features/token-and-cost-tracking?utm_source=openai))

여기서 실무적으로 더 중요한 건 **귀속(attribution)** 입니다.
- 같은 모델을 써도 “어떤 고객/기능/세션” 때문에 비용이 났는지 알아야 최적화가 됩니다.
- 따라서 tracing SDK/OTel에 **user_id, tenant_id, session_id, feature/use_case tag**를 “호출 전에” 반드시 넣어야 합니다(나중에 붙이면 집계가 어긋남).

### 3) LangSmith vs Langfuse: 설계 철학 차이(선택 기준)
- **LangSmith**
  - LangChain/LangGraph 생태계와 함께 쓰기 편하고, tracing + evals 워크플로우가 강점(자동/규칙 기반 eval, annotation queues 등) ([docs.langchain.com](https://docs.langchain.com/langsmith/evaluation-concepts?mode=ui&utm_source=openai))
  - 가격 모델은 LCU(정규화된 작업 단위)와 retention 선택이 핵심 포인트로 안내됩니다. ([langchain.com](https://www.langchain.com/pricing?utm_source=openai))
  - OTel 연동도 공식 문서로 제공합니다. ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/langsmith/trace-with-opentelemetry?utm_source=openai))

- **Langfuse**
  - “어떤 언어/프레임워크든” OTel 기반으로 붙이고, 비용/토큰/대시보드/프롬프트 관리까지 한 플랫폼으로 가져가는 쪽에 강합니다. ([langfuse.com](https://langfuse.com/?utm_source=openai))
  - self-hosting을 공식적으로 강조하며, 동일한 인프라 스택을 운영한다고 명시합니다. ([langfuse.com](https://langfuse.com/self-hosting?source=post_page-----f67396a2172c--------------------------------&utm_source=openai))
  - prompt management(버전/라벨/런타임 fetch)까지 운영 계층으로 포함시키는 접근이 특징입니다. ([langfuse.com](https://langfuse.com/docs/prompt-management/data-model?utm_source=openai))

정리하면:
- “평가(evals) 중심으로 품질 루프까지 한 제품으로” → LangSmith가 자연스러운 선택인 팀이 많고 ([docs.langchain.com](https://docs.langchain.com/langsmith/evaluation-concepts?mode=ui&utm_source=openai))
- “OTel 표준화 + self-host + 데이터 쿼리 가능/확장성” → Langfuse 쪽이 설계적으로 편합니다(특히 조직 표준 observability가 이미 OTEL인 경우) ([thoughtworks.com](https://www.thoughtworks.com/content/dam/thoughtworks/documents/radar/2026/04/tr_technology_radar_vol_34_en.pdf?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “운영 중인 RAG API”를 가정합니다.

- FastAPI로 `/ask` 제공
- Retrieval(벡터 검색) + LLM 응답 생성
- **Langfuse로 tracing + token/cost tracking**
- 동시에 “우리만의 비용 귀속 키(tenant_id, session_id, feature)”를 태깅
- 추가로 vendor invoice로는 절대 안 나오는 **세션 단위 cost**를 trace에서 바로 뽑을 수 있게 설계

> 포인트: toy가 아니라 “프로덕션에서 필요한 태그/에러/리트라이/메타데이터”를 기본 탑재합니다.

### 0) 의존성/환경 변수
```bash
pip install fastapi uvicorn httpx python-dotenv langfuse opentelemetry-api opentelemetry-sdk
```

`.env`
```bash
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com  # self-host면 내부 URL
OPENAI_API_KEY=...
APP_ENV=prod
```

### 1) 초기 셋업: tracing 컨텍스트(귀속 키) 강제
```python
# app.py
import os, time, uuid
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from langfuse import Langfuse

langfuse = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)

app = FastAPI()

class AskReq(BaseModel):
    question: str
    top_k: int = 5
    session_id: Optional[str] = None

# (예시) 벡터 검색 더미: 실제로는 Pinecone/Weaviate/PGVector 등
def retrieve_docs(q: str, top_k: int) -> List[Dict[str, Any]]:
    # 현실적으로는 latency/결과 수/필터 등을 메타로 남겨야 튜닝이 됩니다.
    time.sleep(0.05)
    return [{"id": f"doc-{i}", "text": f"relevant context {i} for: {q}"} for i in range(top_k)]

# (예시) LLM 호출 더미: 실제로는 OpenAI/Anthropic SDK 사용
def call_llm(prompt: str) -> Dict[str, Any]:
    # 실무에선 response metadata에서 usage(token)를 반드시 뽑아야 cost가 맞습니다.
    # 여기선 예시로 token usage를 가정합니다.
    time.sleep(0.2)
    return {
        "text": "final answer ...",
        "usage": {"input": 850, "output": 220},  # provider가 주는 usage를 그대로
        "model": "gpt-4.1-mini",  # 예시
        # "cost": {...} 를 직접 ingest할 수도 있고(정확), Langfuse가 infer하게 둘 수도 있음
    }

@app.post("/ask")
def ask(req: AskReq, x_tenant_id: str = Header(...), x_user_id: str = Header(...)):
    session_id = req.session_id or str(uuid.uuid4())
    feature = "rag_qa"

    # 1) Trace 시작: “귀속 키”를 최상단에 박아둬야 downstream 집계가 됩니다.
    trace = langfuse.trace(
        name="ask",
        input={"question": req.question, "top_k": req.top_k},
        user_id=x_user_id,
        session_id=session_id,
        tags=[os.environ.get("APP_ENV", "dev"), feature],
        metadata={
            "tenant_id": x_tenant_id,
            "feature": feature,
        },
    )

    try:
        # 2) Retrieval observation
        t0 = time.time()
        docs = retrieve_docs(req.question, req.top_k)
        trace.span(
            name="retrieval",
            input={"query": req.question, "top_k": req.top_k},
            output={"doc_ids": [d["id"] for d in docs]},
            metadata={
                "latency_ms": int((time.time() - t0) * 1000),
                "num_docs": len(docs),
            },
        )

        # 3) Generation observation (token/cost tracking의 핵심)
        context = "\n".join([d["text"] for d in docs])
        prompt = f"Answer the question using the context.\n\nContext:\n{context}\n\nQ:{req.question}"

        llm = call_llm(prompt)

        # Langfuse는 generation/embedding에서 usage+model로 cost를 기록/추론합니다. ([langfuse.com](https://langfuse.com/docs/observability/features/token-and-cost-tracking?utm_source=openai))
        trace.generation(
            name="answer",
            input={"prompt": prompt},
            output={"text": llm["text"]},
            model=llm["model"],
            usage=llm["usage"],  # input/output token
            metadata={
                "temperature": 0.2,
                "provider": "openai",
                "tenant_id": x_tenant_id,  # child에도 반복해서 넣어두면 쿼리가 편해집니다.
            },
        )

        trace.update(output={"answer": llm["text"]})
        trace.flush()

        return {
            "answer": llm["text"],
            "session_id": session_id,
        }

    except Exception as e:
        # 운영에서는 에러도 trace에 남겨야 “가끔만 실패”를 잡습니다.
        trace.event(
            name="error",
            metadata={"error_type": type(e).__name__, "message": str(e)},
        )
        trace.flush()
        raise HTTPException(status_code=500, detail="internal error")
```

예상 결과(운영 관점)
- Langfuse UI에서 `ask` trace를 열면:
  - retrieval span과 answer generation이 트리로 보이고
  - generation에 input/output tokens 및 **USD cost**가 붙습니다(usage를 넣었으므로). ([langfuse.com](https://langfuse.com/docs/observability/features/token-and-cost-tracking?utm_source=openai))
- `tenant_id`, `session_id`, `feature`로 필터링해서 “어느 고객이 비용을 태우는지”가 바로 나옵니다.

### 2) 확장: “우리 가격표”로 STT/TTS/툴 비용까지 같은 트레이스에 합산
Langfuse/LangSmith가 잘하는 건 LLM 토큰 기반 비용입니다. 하지만 실제 운영비는 STT/TTS, 검색 API, 크롤러, DB egress 등 “비토큰 비용”이 큽니다. 이건 **콜 시점에** 자체 price table로 계산해서 trace에 cost 이벤트/메타로 남기는 쪽이 가장 견고합니다(월말 invoice는 계정 단위로 뭉개져서 세션 귀속이 안 됨).

```python
# cost.py
PROVIDER_RATES = {
    "tts": {"usd_per_1k_chars": 0.015},
    "search_api": {"usd_per_call": 0.002},
}

def cost_tts(chars: int) -> float:
    return (chars / 1000.0) * PROVIDER_RATES["tts"]["usd_per_1k_chars"]

def cost_search(calls: int) -> float:
    return calls * PROVIDER_RATES["search_api"]["usd_per_call"]
```

```python
# app.py 중간에 추가(예: retrieval이 외부 search API를 호출했다면)
from cost import cost_search

search_calls = 3
trace.span(
    name="external_search",
    metadata={
        "calls": search_calls,
        "estimated_usd": cost_search(search_calls),
        "pricing_version": "2026-08-01",
    },
)
```

이렇게 하면 “LLM cost + 외부 cost”가 한 trace에 모여서, 기능 단위 unit economics(예: 질문 1건당 평균 원가)를 바로 계산할 수 있습니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **태깅 규약을 코드 레벨에서 강제**
- `tenant_id`, `user_id`, `session_id`, `feature`, `model`, `env`는 “옵션”이 아니라 **스키마**입니다.
- 미들웨어에서 헤더 누락 시 400으로 막거나, 기본값을 만들되 “unknown”으로 분리 집계되게 하세요.
- 이게 없으면 비용 최적화가 “감”으로 돌아갑니다.

2) “비용”은 post-hoc 분석만으로 끝내지 말고 **알림/가드레일**까지 연결
- Langfuse는 usage/cost 데이터를 대시보드/알림/메트릭 API로 활용할 수 있다고 명시합니다. ([langfuse.com](https://langfuse.com/docs/observability/features/token-and-cost-tracking?utm_source=openai))
- 운영에서는 “오늘 특정 tenant의 spend 급증” 같은 룰 기반 알림이 훨씬 가치가 큽니다.

3) Prompt를 런타임에서 바꾸려면 “캐시 + fallback” 설계를 먼저
- Langfuse Prompt Management는 런타임 fetch를 전제로 하며, prompt를 객체(메시지+설정)로 다룹니다. ([langfuse.com](https://langfuse.com/docs/prompt-management/data-model?utm_source=openai))
- 하지만 네트워크/권한/장애 때문에 prompt fetch가 실패할 수 있으니:
  - client-side caching(또는 서버 캐시)
  - 마지막 성공 버전 fallback
  - “production label”로 고정 참조
  이 3개가 없으면 프롬프트 관리가 곧 장애 포인트가 됩니다.

### 흔한 함정/안티패턴
- **샘플링을 너무 일찍 적용**
  - 비용 때문에 trace를 샘플링하기 시작하면, 보통 “리트라이/에러 케이스”가 먼저 잘립니다(가장 보고 싶은 데이터).
  - 해결: 정상 케이스는 요약/축약하고, 에러/고비용 trace는 100% 보존(retention 차등)처럼 계층화하세요. (LangSmith도 trace retention을 선택해 비용/가치를 조절하는 메시지를 강조합니다.) ([langchain.com](https://www.langchain.com/pricing?utm_source=openai))

- **모델 이름 매핑/가격표 불일치**
  - cost가 “0” 또는 터무니없게 나오면 대개 model id가 가격 테이블과 매칭이 안 된 겁니다.
  - LangSmith는 model/provider/token count와 가격 테이블로 cost를 계산한다고 명시합니다. ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))
  - Langfuse도 model definition 매칭으로 infer하며, 커스텀 모델 정의를 추가할 수 있습니다. ([langfuse.com](https://langfuse.com/docs/observability/features/token-and-cost-tracking?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- “더 granular하게 본다” = “더 많은 이벤트를 적재한다” = “관측 비용도 증가”
- 특히 per-event 과금 모델에서는 관측 granularity가 곧 bill이 됩니다.
- 결론: **원시 이벤트는 내 데이터베이스(append-only)** 로도 남길지, 벤더에만 둘지 결정해야 합니다. self-host나 OTel 파이프라인을 고민하는 이유가 여기서 나옵니다(Langfuse가 self-host와 OTel 친화성을 강하게 가져가는 배경). ([langfuse.com](https://langfuse.com/self-hosting?source=post_page-----f67396a2172c--------------------------------&utm_source=openai))

---

## 🚀 마무리
LangSmith/Langfuse를 “모니터링 툴”로만 보면 대시보드 하나 더 생기는 정도로 끝납니다. 하지만 제대로 쓰면:

- 디버깅: 실행 트리로 “어느 단계가 실패/지연/환각”인지 즉시 특정
- 비용: token/cost를 **trace 단위**로 귀속해서 최적화 포인트가 선명해짐 ([langchaindocs.sitemirror.store](https://langchaindocs.sitemirror.store/langsmith/cost-tracking/?utm_source=openai))
- 품질: eval/피드백 루프(특히 LangSmith의 eval 개념/워크플로우)를 붙여 회귀를 막음 ([docs.langchain.com](https://docs.langchain.com/langsmith/evaluation-concepts?mode=ui&utm_source=openai))

도입 판단 기준(현실적인 체크리스트)
- 우리 앱은 “단일 LLM 호출”인가, “RAG/Agent 그래프”인가?
- 비용을 “계정 월합”이 아니라 **tenant/session/feature 단위**로 봐야 하나?
- 이미 OpenTelemetry 기반 observability 표준이 있나(있으면 Langfuse/OTel 경로가 특히 자연스러움) ([thoughtworks.com](https://www.thoughtworks.com/content/dam/thoughtworks/documents/radar/2026/04/tr_technology_radar_vol_34_en.pdf?utm_source=openai))
- self-host/데이터 소유권이 필수인가? (Langfuse는 self-host 스택을 공식 가이드로 전면에 둠) ([langfuse.com](https://langfuse.com/self-hosting?source=post_page-----f67396a2172c--------------------------------&utm_source=openai))

다음 학습 추천
- Langfuse: token & cost tracking 문서(usage ingest vs infer, model definitions) ([langfuse.com](https://langfuse.com/docs/observability/features/token-and-cost-tracking?utm_source=openai))
- LangSmith: cost tracking과 eval 개념(가격 테이블/토큰 기반 비용, 자동 eval 설계) ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))

원하시면, 당신의 스택(언어/프레임워크, 모델 provider, 멀티테넌시 유무, self-host 요구)을 기준으로 **“LangSmith vs Langfuse 선택 표 + 마이그레이션 플랜(2주/1달)”** 형태로 더 구체화해드릴게요.