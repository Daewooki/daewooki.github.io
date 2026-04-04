---
title: "LLM 앱 모니터링의 “진짜” 2026 스택: LangSmith vs Langfuse, 디버깅·품질·비용을 한 번에 잡는 법"
date: 2026-04-04 02:48:55 +0900
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
LLM 앱을 프로덕션에 올리면 금방 깨닫습니다. 문제는 “모델이 틀렸다”가 아니라, **어느 단계에서 왜 틀렸는지 재현이 안 된다**는 점입니다. RAG라면 retrieval 결과/컨텍스트 길이, agent라면 tool call 순서/파라미터, streaming이라면 중간 토큰과 오류 타이밍까지 얽혀서 단순 로그로는 원인 추적이 불가능해집니다. 그래서 2026년에는 LLM 앱도 전통 APM처럼 **trace 기반 observability**가 기본 전제가 됐고, 그 대표 선택지가 LangSmith(주로 LangChain/LangGraph 생태계)와 Langfuse(오픈소스·self-host 친화)입니다.  
특히 이번 주제의 핵심인 **디버깅 + 비용 추적(cost tracking)** 관점에서 LangSmith는 “full-stack cost tracking”을 강하게 밀고 있고 ([changelog.langchain.com](https://changelog.langchain.com/announcements/unified-cost-tracking-for-llms-tools-retrieval?utm_source=openai)), Langfuse는 OpenTelemetry 기반/아키텍처적으로 대규모 ingestion을 견딜 수 있게 설계된 점이 눈에 띕니다 ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai)).

---

## 🔧 핵심 개념
### 1) Tracing(추적) = LLM 앱의 구조화된 실행 기록
LLM observability에서 trace는 “요청 1건”의 전체 실행을 의미하고, 그 아래에 LLM call, retrieval, tool execution 같은 step이 **계층 구조(run/span)** 로 매달립니다. LangSmith도 “trace 안에 여러 run(steps)이 들어간다”는 정의를 명확히 합니다 ([docs.langchain.com](https://docs.langchain.com/langsmith/observability-quickstart?utm_source=openai)). Langfuse도 trace 아래 observation/span(예: generation/event)이 중첩되는 모델을 제공합니다 ([langfuse.com](https://langfuse.com/docs/observability/overview?utm_source=openai)).

### 2) 디버깅 포인트: “입력/출력”이 아니라 “컨텍스트”를 남겨야 한다
LLM 앱의 버그는 대개 다음에서 터집니다.
- prompt template 버전이 바뀌었는데 캐시/배포 라벨이 섞임
- tool call에 잘못된 인자 전달(스키마 미스매치)
- retrieval 컨텍스트가 너무 길어져 token 폭발 → truncation → 환각
- streaming 중간에 예외 발생했는데 “최종 응답”만 로그로 남음

그래서 trace에는 **prompt/response뿐 아니라 tool call 파라미터, latency, metadata, token usage**가 함께 있어야 “재현 가능한 디버깅”이 됩니다. Langfuse 문서도 tracing이 prompt/response/tool call 관계를 담는 게 핵심이라고 강조합니다 ([langfuse.com](https://langfuse.com/docs/observability/overview?utm_source=openai)).

### 3) 비용 추적(cost tracking): token만으로는 부족, “Other cost”가 본체
2026년 비용 이슈의 본질은 “LLM 호출 비용”보다 **agent workflow 전체 비용**입니다. LangSmith는 LLM token 기반 비용을 자동 산출하면서도, tool/retrieval 같은 non-LLM step에 대해 `usage_metadata`로 **커스텀 비용을 주입**할 수 있게 했습니다 ([changelog.langchain.com](https://changelog.langchain.com/announcements/unified-cost-tracking-for-llms-tools-retrieval?utm_source=openai)). 이게 중요한 이유는:
- vector DB 쿼리/서드파티 API/브라우징 툴 같은 비용은 토큰이 아니라 “호출 단가”로 붙기 때문
- “LLM은 싸게 썼는데 왜 청구가 폭증했지?”가 보통 tool 쪽에서 터짐

반대로 Langfuse는 “token & cost tracking”을 기능으로 제공하고(Cloud/플랜 기준) ([langfuse.com](https://langfuse.com/pricing?utm_source=openai)), self-host 시에도 ClickHouse 기반 OLAP + queued ingestion 같은 구조로 대량 이벤트를 처리하도록 설계했습니다 ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai)). 즉 **비용 계산 로직**의 표현력은 LangSmith가 강하고, **운영/저장/확장**은 Langfuse가 매력적인 그림이 자주 나옵니다.

---

## 💻 실전 코드
아래 예제는 “LLM + tool + 비용 주입”을 **동일한 trace**로 묶어, 나중에 UI에서 병목/비용을 함께 보는 패턴입니다. (Python 3.11+ 가정)

### A) LangSmith: `@traceable` + `usage_metadata`로 tool 비용까지 통합
```python
# pip install langsmith openai
import os
import time
from openai import OpenAI
from langsmith import traceable, get_current_run_tree

os.environ["LANGSMITH_API_KEY"] = os.environ["LANGSMITH_API_KEY"]
os.environ["LANGSMITH_TRACING"] = "true"
# os.environ["LANGSMITH_PROJECT"] = "my-prod-project"  # 선택

client = OpenAI()

@traceable(run_type="tool", name="search_docs")
def search_docs(query: str) -> dict:
    t0 = time.time()
    # (예시) 사내 검색/벡터DB/외부 API 호출이 있다고 가정
    time.sleep(0.15)
    result = {"docs": ["doc1 ...", "doc2 ..."], "query": query, "latency_ms": int((time.time()-t0)*1000)}

    # 핵심: LLM이 아닌 step에도 비용을 넣을 수 있어야 "총비용"이 맞춰짐
    # LangSmith는 tool run에 usage_metadata.total_cost 주입을 지원 ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))
    run = get_current_run_tree()
    run.set(usage_metadata={"total_cost": 0.0008})  # 예: 검색 API 호출 단가

    return result

@traceable(run_type="llm", name="answer_with_context",
           metadata={"ls_provider": "openai", "ls_model_name": "gpt-4.1-mini"})
def answer_with_context(question: str, context_docs: list[str]) -> str:
    messages = [
        {"role": "system", "content": "You are a concise assistant. Use the provided context."},
        {"role": "user", "content": f"Question: {question}\n\nContext:\n- " + "\n- ".join(context_docs)},
    ]

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.2,
    )

    # LangSmith는 major provider의 token/cost 자동 추적을 제공하고 ([changelog.langchain.com](https://changelog.langchain.com/announcements/unified-cost-tracking-for-llms-tools-retrieval?utm_source=openai))
    # 커스텀/비선형 과금이면 usage_metadata에 input_cost/output_cost를 직접 넣는 방식도 가능 ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))
    return resp.choices[0].message.content

@traceable(name="rag_request")  # 최상위 trace(요청 1건)
def rag_request(question: str) -> str:
    docs = search_docs(question)["docs"]
    return answer_with_context(question, docs)

if __name__ == "__main__":
    print(rag_request("우리 제품 환불 정책 요약해줘"))
```

### B) Langfuse: SDK v3에서 trace/span을 “관계”로 제대로 묶는 게 포인트
Langfuse Python SDK는 span/generation/event 같은 observation 타입을 제공하고, 현재 활성 span 컨텍스트에 자식 span이 자동으로 붙어 trace 계층이 유지됩니다 ([langfuse.com](https://langfuse.com/docs/sdk/python?utm_source=openai)). self-host라면 `LANGFUSE_BASE_URL`로 호스트를 지정하는 것도 잊으면 안 됩니다 ([langfuse.com](https://langfuse.com/docs/sdk/python?utm_source=openai)).
```python
# pip install langfuse openai
import os
from openai import OpenAI
from langfuse import Langfuse

os.environ["LANGFUSE_PUBLIC_KEY"] = os.environ["LANGFUSE_PUBLIC_KEY"]
os.environ["LANGFUSE_SECRET_KEY"] = os.environ["LANGFUSE_SECRET_KEY"]
# self-host라면:
# os.environ["LANGFUSE_BASE_URL"] = "https://langfuse.mycompany.internal"  # ([langfuse.com](https://langfuse.com/docs/sdk/python?utm_source=openai))

lf = Langfuse()
client = OpenAI()

def handle_request(question: str) -> str:
    trace = lf.trace(name="rag_request", metadata={"env": "prod"})

    # retrieval을 span으로
    with trace.span(name="search_docs") as span:
        docs = ["doc1 ...", "doc2 ..."]
        span.update(output={"docs": docs})

    # LLM call을 generation으로(모델/파라미터/usage/cost를 담기 좋음) ([langfuse.com](https://langfuse.com/docs/sdk/python?utm_source=openai))
    with trace.generation(name="answer", model="gpt-4.1-mini", input={"question": question, "docs": docs}) as gen:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Use context."},
                {"role": "user", "content": question + "\n\n" + "\n".join(docs)},
            ],
        )
        gen.update(output=resp.choices[0].message.content)

    trace.flush()
    return resp.choices[0].message.content
```

---

## ⚡ 실전 팁
1) **비용 추적을 “표준화된 메타데이터 계약”으로 다뤄라**  
LangSmith는 `usage_metadata`로 LLM뿐 아니라 tool/retrieval 비용까지 한 대시보드에 합칠 수 있습니다 ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai)). 실무에선 “모든 run이 최소한 `total_cost` 또는 (input/output token+price) 중 하나를 가진다”는 팀 규칙을 만들어야, 데이터가 누적될수록 분석이 쉬워집니다.

2) **LangSmith retention을 비용 설계의 일부로 취급**  
LangSmith는 base trace(14일) vs extended trace(400일)로 retention을 나눠 비용을 최적화하라고 가이드합니다 ([langchain.com](https://www.langchain.com/pricing?utm_source=openai)). 운영 팁은 간단합니다:  
- 장애 분석/단기 디버깅은 base로 대량 수집  
- “사용자 피드백이 붙은 케이스”만 extended로 승격(샘플링 + 승격 전략)

3) **Langfuse self-host는 “DB/스토리지”가 곧 제품**  
Langfuse는 Postgres + ClickHouse + Redis + S3/Blob에 기반한 구조와 queued ingestion을 명시합니다 ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai)). 즉 self-host를 선택하는 순간, 관측 데이터의 신뢰도는 “코드”가 아니라 **ClickHouse 운영(파티셔닝/TTL/리소스)** 에 달립니다. 최소한:
- ClickHouse TTL(보관 기간)과 비용(스토리지)을 같이 설계
- trace payload(특히 멀티모달)를 S3로 보내는 구성 점검 ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai))

4) **OpenTelemetry를 쓸 땐 “수집 범위”를 통제하라 (숨은 과금/노이즈 방지)**  
OTel 기반으로 “모든 span을 다 잡는다”는 접근은 편하지만, 백그라운드 span/타 라이브러리 span까지 섞이며 이벤트가 폭증할 수 있습니다. 실제로 커뮤니티에서도 “의도치 않은 trace 캡처로 비용이 늘 수 있다”는 류의 경고가 나옵니다(신뢰도는 낮지만 현상 자체는 충분히 현실적). ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1rs2r2u/psa_check_your_langfuse_traces_their_sdk/?utm_source=openai))  
실무적으로는 샘플링/필터링/namespace 기준으로 “LLM request path만” 남기는 쪽이 운영 안정성이 높습니다.

---

## 🚀 마무리
2026년 4월 기준으로 LangSmith와 Langfuse는 둘 다 “LLM 앱의 로그를 trace로 승격”시키는 도구지만, **관심사의 중심축**이 다릅니다. LangSmith는 token 기반 자동 비용 산출 + `usage_metadata`로 tool/retrieval까지 묶는 “unified cost tracking” 메시지가 강하고 ([changelog.langchain.com](https://changelog.langchain.com/announcements/unified-cost-tracking-for-llms-tools-retrieval?utm_source=openai)), Langfuse는 OpenTelemetry 친화 + self-host 가능한 아키텍처(ClickHouse/S3 기반 ingestion 파이프라인)를 명확히 공개하며 운영 확장성에 강점이 있습니다 ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai)).  

다음 학습 추천은 두 갈래입니다.
- **비용/품질을 동시에**: LangSmith의 cost tracking 문서(`usage_metadata`, 모델 price map 개념)를 팀 표준으로 정리 ([docs.langchain.com](https://docs.langchain.com/langsmith/cost-tracking?utm_source=openai))  
- **플랫폼 운영/프라이버시**: Langfuse self-host 아키텍처를 기준으로 ClickHouse TTL·S3 저장·ingestion 병목을 먼저 설계 ([langfuse.com](https://langfuse.com/self-hosting?utm_source=openai))  

원하면, (1) “동일한 RAG/Agent 앱을 LangSmith와 Langfuse에 동시에 보내는 듀얼 인스트루먼트 패턴” 또는 (2) “비용 폭발을 막는 sampling/upgrade(retention) 정책 템플릿”까지 확장해서 후속 글 형태로 정리해드릴 수 있습니다.