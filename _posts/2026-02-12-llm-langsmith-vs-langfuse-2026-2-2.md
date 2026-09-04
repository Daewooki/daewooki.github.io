---
title: "LLM 앱에서 “어디서 터졌고, 왜 비싸졌는지” 끝까지 추적하기: LangSmith vs Langfuse (2026년 2월 관점)"
description: "LLM 애플리케이션은 전통적인 APM(Application Performance Monitoring)만으로는 운영이 어렵습니다. 이유는 단순합니다."
date: 2026-02-12 02:55:15 +0900
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
LLM 애플리케이션은 전통적인 APM(Application Performance Monitoring)만으로는 운영이 어렵습니다. 이유는 단순합니다. 장애가 “HTTP 500”처럼 명확하지 않고, 품질 저하도 “정답/오답”으로 떨어지지 않으며, 비용은 “토큰/캐시/리트라이/툴 호출”처럼 실행 경로에 따라 분산되기 때문입니다.  
그래서 2025~2026년의 LLM Observability는 **trace 중심(요청 1건의 실행을 트리 형태로)**으로 빠르게 수렴했고, 그 위에 **디버깅 + 비용 추적 + 품질 평가(evals)**를 한 화면에서 묶는 쪽으로 진화했습니다.

이 글에서는 2026년 2월 기준으로 현업에서 가장 자주 비교되는 **LangSmith**와 **Langfuse**를 “모니터링/디버깅/비용 추적” 관점에서 깊게 파고들고, 실제로 바로 붙여볼 수 있는 코드를 제공합니다. (둘 다 핵심 키워드는 이제 **OpenTelemetry(OTel)** 입니다.)[^1]

---

## 🔧 핵심 개념
### 1) LLM Observability에서 “Trace”가 의미하는 것
LLM 앱에서 trace는 보통 다음을 포함합니다.

- **request(유저 입력) → prompt 구성 → LLM call → tool call/DB/RAG → 후처리 → 응답**
- 각 단계의 **latency**, **error**, **token usage**, **model name**, **retry** 정보
- 단계 간 부모-자식 관계(트리)가 있어 “병목이 어디인지”가 한눈에 보임

LangSmith는 이를 “Run(스팬에 해당)” 트리로 강하게 모델링하고, 비용/토큰을 트리 상에서 집계하는 UX가 탄탄합니다.[^2]

### 2) OpenTelemetry(OTel)가 왜 갑자기 중요해졌나
과거엔 툴마다 고유 SDK로만 계측하는 경우가 많았는데, LLM 앱이 커지면 다음 문제가 생깁니다.

- 서비스가 여러 개로 쪼개지면서 **분산 트레이싱**이 필요
- LLM 단계만이 아니라 **API Gateway, worker, DB, queue**까지 같은 Trace ID로 엮고 싶음
- 특정 벤더에 종속되지 않고 exporter만 바꿔서 이관하고 싶음

LangSmith는 “LangChain/LangGraph” 생태계에 강점이 있고, 2025년에는 **SDK 레벨 end-to-end OTel 지원**을 강조했습니다(네이티브 포맷 대비 약간의 overhead가 있을 수 있다고도 명시).[^1]  
Langfuse도 2025년부터 **OTel span ingest**를 전면으로 내세워 다양한 프레임워크 연결을 확장했습니다.[^3]

### 3) 비용 추적의 본질: “토큰 집계”가 아니라 “실행 경로 비용 회계”
현장에서 비용 추적이 실패하는 패턴은 대개 이겁니다.

- “LLM 호출 비용”만 보고, **tool call / retrieval / rerank / embedding / retry** 비용은 누락
- trace 트리의 자식 스팬에 thread/session 메타데이터가 빠져서 **대화 단위 집계가 틀어짐**
- reasoning 모델(o1 계열 등)처럼 **output token이 복잡**한 경우, 문자열로 토큰을 역추정하면 비용이 어긋남

LangSmith는 major provider에 대해 토큰/비용을 자동 기록하고, **custom cost**도 run 단위로 넣어 “단일 비용 뷰”를 만들 수 있게 가이드합니다. 또한 thread 메타데이터 누락 시 집계가 깨질 수 있음을 문서에서 명확히 경고합니다.[^2]  
Langfuse 쪽은 OpenAI o1 계열처럼 “token counts 없이는 비용 추정 불가” 케이스를 명확히 언급했고, wrapper/integration을 쓰지 않으면 usage를 명시적으로 넣어야 하는 사례가 커뮤니티에서 반복적으로 등장합니다.[^4]

---

## 💻 실전 코드
아래 예시는 “최소 코드 변경으로” **OTel로 계측하고**, “LLM 호출 + tool 비용”을 같은 trace에 묶어 **디버깅/비용 추적**까지 가능하게 만드는 형태에 집중합니다.

### 예제 1) LangSmith: OTel 기반 tracing + 커스텀 비용(툴 호출) 추가
```python
# python
"""
목표:
- LangSmith로 OpenTelemetry 기반 tracing 활성화
- LangChain 실행을 trace로 수집
- (중요) LLM 비용 외에 'tool 비용'을 custom cost로 같이 기록하는 패턴 제시

사전 준비:
pip install "langsmith[otel]" langchain langchain-openai

환경변수:
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true
LANGSMITH_OTEL_ENABLED=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
"""

import os
import time
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# LangSmith/LangChain은 env로 tracing을 켜면 자동 계측이 들어간다.[^1]

def expensive_tool_call(query: str) -> str:
    # 예: 외부 검색 API, rerank, 크롤링 등 LLM 외부 비용이 발생하는 컴포넌트
    time.sleep(0.2)
    return f"[tool-result for {query}]"

def main():
    prompt = ChatPromptTemplate.from_template(
        "Use the tool result to answer.\nTool result: {tool}\nQuestion: {q}"
    )
    model = ChatOpenAI(model="gpt-4o-mini")  # 예시

    # 1) tool 호출
    tool_result = expensive_tool_call("langsmith vs langfuse")

    # 2) LLM 호출 (LangChain 실행은 trace로 수집)
    chain = prompt | model
    out = chain.invoke({"tool": tool_result, "q": "비용 추적에서 가장 흔한 함정은?"})
    print(out.content)

    # 3) "툴 비용"을 같은 trace에 붙이려면:
    #    - LangSmith는 run 단위로 custom cost를 제출할 수 있도록 가이드한다.[^2]
    #    - 여기서는 개념 예시로만 남긴다(실제론 langsmith Client로 run_id에 cost를 업데이트하는 형태로 구현).
    #
    # 핵심: LLM token 비용만 보지 말고 tool/retrieval/retry 비용을 반드시 같은 execution tree에 합산해야
    #       "왜 비싸졌는지" 디버깅이 된다.

if __name__ == "__main__":
    main()
```

### 예제 2) Langfuse: OTel 철학(표준 컨텍스트 전파) 기반으로 “누락 없는 계측” 만들기
Langfuse는 2025년부터 OTel 기반 SDK 방향을 강하게 밀고 있고, OTel의 장점(표준 context propagation, 서드파티 계측과의 결합)을 강조합니다.[^5]

아래는 “핵심 아이디어” 예시입니다.

```python
# python
"""
목표:
- OpenTelemetry 컨텍스트 전파가 되는 구조로 span을 쪼개서
  LLM step / tool step을 한 trace로 묶는 패턴을 만든다.
- (중요) token/cost가 자동으로 안 잡히는 케이스가 있으므로,
  wrapper/통합을 쓰거나 usage를 명시적으로 넣는 전략을 준비한다.[^6]
"""

from opentelemetry import trace

tracer = trace.get_tracer("llm-app")

def tool_step():
    with tracer.start_as_current_span("tool:search") as span:
        # 여기에 tool latency, error, cost 등을 attribute로 기록
        span.set_attribute("tool.name", "search-api")
        span.set_attribute("tool.cost_usd", 0.002)  # 예시: tool 비용을 명시
        return "tool-result"

def llm_step(prompt: str):
    with tracer.start_as_current_span("llm:generate") as span:
        span.set_attribute("gen_ai.system", "openai")  # 표준/준표준 속성 계열
        span.set_attribute("llm.model_name", "gpt-4o-mini")
        # 주의: 모델/SDK 조합에 따라 token usage가 자동 수집되지 않을 수 있음[^6]
        # 가능하면 Langfuse wrapper/integration(LangChain, LlamaIndex, LiteLLM 등)을 활용하거나,
        # usage를 명시적으로 기록하는 경로를 마련해야 한다.
        return "answer"

def main():
    with tracer.start_as_current_span("request") as root:
        tool = tool_step()
        ans = llm_step(f"tool={tool}")
        print(ans)

if __name__ == "__main__":
    main()
```

---

## ⚡ 실전 팁
### 1) “OTel 채택”은 기능이 아니라 조직 아키텍처 선택이다
- 서비스가 1개고 Python 단일 런타임이면 “벤더 SDK 직결”도 빠릅니다.
- 하지만 API/worker/queue로 갈라지고, 인프라 관측(HTTP, DB)까지 합치려면 OTel이 사실상 정답입니다. LangSmith도 OTel을 “스택 전체를 통합 관측”하는 관점에서 설명합니다.[^1]

### 2) 비용 추적의 함정: “token이 아니라 metadata가 깨져서 집계가 틀어지는” 케이스
LangSmith 문서에서 특히 실무적인 포인트는 **thread/session 메타데이터**입니다. 자식 run에 session/thread 메타데이터가 누락되면 “대화 단위” 집계가 어긋날 수 있다고 못 박습니다.[^2]  
→ 운영 환경에서는 “trace는 찍히는데 비용 대시보드가 이상함”의 1순위 원인이 됩니다.

### 3) reasoning 모델(o1 계열 등)은 “usage 미제공 시 비용 추정 불가”를 전제로 설계하라
Langfuse는 o1 계열에서 **token counts 없이는 cost inference가 불가능**하다고 명시합니다.[^4]  
→ 결론: wrapper/integration을 쓰든, 응답에서 usage를 파싱해 넣든, “usage를 확보하는 경로”가 설계에 포함돼야 합니다.

### 4) 가격 모델 비교는 “과금 단위”를 먼저 맞춰야 한다
- LangSmith: seat + trace 과금(보존 기간에 따라 base/extended) 구조가 명확합니다.[^7]  
- Langfuse: Cloud는 “units/events” 기반 티어가 언급되며(자료마다 수치가 다를 수 있어 공식 확인 권장), self-host 옵션이 강점으로 자주 거론됩니다.[^8]  
→ **“요청 1건당 평균 스팬 수(=trace depth)”**를 먼저 산정하지 않으면, 월 비용 비교는 거의 항상 틀립니다.

---

## 🚀 마무리
2026년 2월 시점에서 LLM 앱 모니터링의 중심축은 확실히 **Trace(트리) + 비용(토큰/툴) + 디버깅(재현 가능한 컨텍스트)**로 자리 잡았습니다. LangSmith는 LangChain 생태계와 촘촘한 UI/가이드(특히 비용/메타데이터 집계)에서 강점을 보이고, OTel도 end-to-end로 끌어안는 방향을 분명히 했습니다.[^1]  
Langfuse는 OTel 표준을 적극 활용해 언어/프레임워크 확장성과 self-host 옵션을 무기로 가져가며, 특히 “usage 미제공 시 비용 추정 실패” 같은 현실적인 포인트를 케이스로 축적해 왔습니다.[^5]

다음 학습 추천은 두 가지입니다.
1) OpenTelemetry context propagation을 “서비스 경계(HTTP/queue)”까지 확장해 end-to-end trace를 완성하기  
2) 비용 추적을 LLM 호출에만 두지 말고, tool/retrieval/rerank/retry를 **같은 execution tree에 회계 처리**하는 구조로 리팩터링하기

[^1]: <https://blog.langchain.com/end-to-end-opentelemetry-langsmith>
[^2]: <https://docs.langchain.com/langsmith/cost-tracking>
[^3]: <https://python-sdk-v2.docs-snapshot.langfuse.com/changelog/2025-02-14-opentelemetry-tracing/>
[^4]: <https://python-sdk-v2.docs-snapshot.langfuse.com/changelog/2024-09-13-openai-o1-models/>
[^5]: <https://github.com/orgs/langfuse/discussions/6993>
[^6]: <https://github.com/orgs/langfuse/discussions/6999>
[^7]: <https://www.langchain.com/pricing>
[^8]: <https://www.linkedin.com/posts/langfuse_recently-we-announced-open-sourcing-of-all-activity-7343300378274226176-TDPs>
