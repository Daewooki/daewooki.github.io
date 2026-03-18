---
title: "LangSmith vs Langfuse: 2026년 3월, LLM 앱 모니터링/디버깅/비용 추적을 “Trace 표준(OTel)”로 통합하는 법"
date: 2026-03-18 02:52:18 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-03]
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
2026년의 LLM 앱은 “모델 호출 한 번”으로 끝나지 않습니다. Agent가 tool을 여러 번 호출하고, RAG가 retrieval을 반복하며, streaming 응답 중간에 재시도/폴백이 발생합니다. 이때 장애의 원인은 대개 **프롬프트/모델**이 아니라 **실행 그래프 어딘가의 상태 전파 실패, 타임아웃, 잘못된 캐시, 과도한 토큰 사용** 같은 “시스템 문제”로 나타납니다.

그래서 요즘 LLM Observability의 핵심은 단순 로그가 아니라 **Trace(분산 추적)** 입니다. 특히 **OpenTelemetry(OTel)** 로 표준화하면, LLM 앱 내부 실행(프롬프트·tool·retrieval)과 인프라 계층(HTTP, DB, queue)을 **한 개의 trace_id로 이어 붙여** 병목/오류/비용을 같이 봅니다. LangSmith는 OTel 기반 end-to-end 지원을 공식적으로 강화했고, Langfuse는 “OpenTelemetry 기반”을 전면에 내세우며 SDK/통합을 확장하는 흐름입니다. ([blog.langchain.com](https://blog.langchain.com/end-to-end-opentelemetry-langsmith?utm_source=openai))

---

## 🔧 핵심 개념
### 주요 개념 정의
- **Trace / Span**: 한 사용자 요청(Request) = 1 trace, 그 안의 단계(LLM call, tool call, retrieval 등) = span. span에는 latency, error, attributes(예: model, prompt version, user_id), 그리고 **token/cost** 같은 도메인 지표를 붙입니다.
- **Context propagation**: async/멀티서비스 환경에서 “지금 이 span이 어떤 trace에 속하는지”를 자동으로 이어주는 메커니즘. Agent/worker로 넘어가도 trace가 끊기면 디버깅이 급격히 어려워집니다.
- **Semantic conventions(GenAI)**: LLM 호출/프롬프트/응답/토큰을 span attribute로 표준화하려는 시도. LangSmith는 OpenLLMetry 등 OTel 포맷 기반 ingest를 지원하고, OTel GenAI 컨벤션 진화에 맞춰 확장하겠다는 방향을 명시했습니다. ([blog.langchain.com](https://blog.langchain.com/opentelemetry-langsmith/?utm_source=openai))
- **Ingest vs SDK instrumentation**
  - *Ingest*: “OTel로 만든 trace를 받아서 대시보드에 보여줌”
  - *Instrumentation*: “SDK가 앱 코드를 계측해서 trace를 만듦”
  LangSmith는 초기엔 ingest 중심 → 이후 SDK 레벨의 end-to-end OTel 지원을 강화했습니다. ([blog.langchain.com](https://blog.langchain.com/end-to-end-opentelemetry-langsmith?utm_source=openai))
  Langfuse는 관측 데코레이터/드롭인 wrapper 패턴으로 nested call을 자동 링크하는 경험을 강조합니다. ([langfuse.com](https://langfuse.com/?utm_source=openai))

### 어떻게 작동하는지 (LLM 비용 추적까지)
1. 요청 진입 시 root span 생성(예: `handle_request`)
2. LLM 호출마다 child span 생성(예: `openai.chat.completions`)
3. span attribute에 `model`, `prompt`, `input_tokens`, `output_tokens` 등을 기록
4. 비용은 (a) SDK가 제공하는 비용 계산/추정치를 쓰거나, (b) 토큰/요금표 기반으로 “내부 계산한 cost”를 attribute로 남겨 대시보드에서 집계합니다  
5. 중요한 포인트: **비용은 “LLM 호출 수”가 아니라 “trace 그래프에서 어디서 토큰이 폭증했는지”로 봐야 최적화가 가능합니다.** 이게 Trace-first의 이유입니다.

---

## 💻 실전 코드
아래 예시는 **Langfuse**의 `@observe()`로 request 단위를 trace로 만들고, “드롭인 OpenAI wrapper”로 LLM span을 자동 생성하는 형태입니다(중첩 호출 자동 링크). 또한 trace 메타데이터에 사용자/릴리즈 정보를 태깅해 **디버깅과 비용 분석의 필터 축**으로 씁니다. ([langfuse.com](https://langfuse.com/?utm_source=openai))

```python
# python
# requirements:
#   pip install langfuse openai
# env:
#   LANGFUSE_PUBLIC_KEY=...
#   LANGFUSE_SECRET_KEY=...
#   LANGFUSE_HOST=... (cloud 또는 self-host URL)

from langfuse import observe
from langfuse.openai import openai  # drop-in wrapper: OpenTelemetry 기반 tracing을 추가 ([langfuse.com](https://langfuse.com/?utm_source=openai))

# 1) "요청 단위"를 trace로 묶는다.
@observe(name="handle_request")
def handle_request(user_id: str, text: str) -> str:
    # 2) 관측 데이터에 필터링 가능한 메타데이터를 남긴다.
    #    (장애 triage에서 user_id, release, route는 거의 필수)
    observe.update_current_observation(
        metadata={
            "user_id": user_id,
            "release": "2026.03.18",
            "route": "/v1/summarize",
        }
    )

    # 3) LLM 호출은 wrapper가 span을 만들고,
    #    토큰/비용 관련 정보를 가능한 범위에서 기록한다.
    res = openai.chat.completions.create(
        model="gpt-5",  # 예시: 실제 사용 모델로 교체
        messages=[
            {"role": "system", "content": "Summarize in one sentence."},
            {"role": "user", "content": text},
        ],
        temperature=0.2,
    )

    # 4) 응답 품질/정책 위반/파서 실패 같은 "도메인 실패"도
    #    로그가 아니라 trace 이벤트/필드로 남겨야 나중에 재현이 쉽다.
    answer = res.choices[0].message.content or ""
    if len(answer) == 0:
        observe.update_current_observation(
            level="ERROR",
            metadata={"reason": "empty_answer"}
        )
        raise RuntimeError("LLM returned empty answer")

    return answer


if __name__ == "__main__":
    out = handle_request("u_123", "Explain why distributed tracing matters for LLM agents.")
    print(out)
```

LangSmith 쪽은 OTel을 “받는 것”을 넘어서, LangChain/LangGraph 앱에서 OTel 기반 end-to-end tracing을 표준화해 **기존 Datadog/Grafana/Jaeger 같은 OTel 생태계와 상호운용**하는 방향을 강조합니다. ([blog.langchain.com](https://blog.langchain.com/end-to-end-opentelemetry-langsmith?utm_source=openai))

---

## ⚡ 실전 팁
- **Trace 표준을 먼저 정하라(OTel)**: “LangSmith냐 Langfuse냐”보다 중요한 건, 조직 내에서 trace_id로 모든 것을 엮는 기준입니다. LangSmith도 OTel 상호운용성을 전면에 두고 있고, Langfuse도 OTel 기반을 명확히 합니다. ([blog.langchain.com](https://blog.langchain.com/end-to-end-opentelemetry-langsmith?utm_source=openai))
- **비용 추적의 함정: ‘의도치 않은 계측 범위’**
  - eval runner, 배치 작업, 다른 라이브러리의 span까지 한 번에 잡히면 **트래픽/스팬이 폭증**하고 비용/저장소가 튈 수 있습니다.
  - 최근 커뮤니티에서도 “SDK가 다른 툴 trace까지 잡아 과금/사용량이 늘 수 있으니 설정을 확인하라”는 경고가 공유되었습니다. 계측 범위를 **route/서비스/샘플링**으로 통제하세요. ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1rs2r2u/psa_check_your_langfuse_traces_their_sdk/?utm_source=openai))
- **PII/시크릿 마스킹은 ‘전송 전’에**: 대시보드 기능을 믿기보다, instrumentation 단계에서 prompt/툴 파라미터를 마스킹하는 게 안전합니다(특히 규제/감사 환경).
- **운영에서는 100% tracing이 답이 아닐 때가 많다**
  - 모든 요청을 full detail로 남기면 비용이 큽니다.
  - “에러/슬로우 요청 100% + 정상 요청 1~5%” 같은 **tail-based sampling** 전략(또는 기능 플래그 기반 샘플링)을 고려하세요.
- **Debugging은 ‘재현 가능한 단위’로**
  - trace 하나가 곧 “재현 스크립트”가 되게: prompt version, retrieval query, tool arguments, model params를 span attribute로 남기면, 장애가 났을 때 같은 입력으로 replay하기 쉬워집니다.

---

## 🚀 마무리
2026년 3월 기준으로 LangSmith와 Langfuse 모두 “LLM Observability = Trace + OTel” 방향성이 뚜렷합니다. LangSmith는 LangChain/LangGraph 중심의 end-to-end OTel 지원과 생태계 상호운용성을 강조하고, Langfuse는 OTel 기반 관측 모델과 드롭인 wrapper/데코레이터로 개발 경험을 강하게 밀고 있습니다. ([blog.langchain.com](https://blog.langchain.com/end-to-end-opentelemetry-langsmith?utm_source=openai))

다음 단계로는:
1) OTel로 trace_id를 서비스 전반에 관통시키고  
2) LLM span에 cost/token/quality 신호를 표준 attribute로 붙인 뒤  
3) 샘플링·PII 마스킹·메타데이터 규칙을 팀 표준으로 고정하는 것  
이 순서가 가장 ROI가 좋습니다.