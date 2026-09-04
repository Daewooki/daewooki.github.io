---
title: "확장 가능한 AI 애플리케이션 아키텍처 설계 패턴: “RAG + Agent + Workflow”로 가는 이유"
description: "2024~2025년의 “RAG(벡터DB+LLM)” 중심 앱은 빠르게 확산됐지만, 2026년 1월 시점의 실무 요구는 훨씬 복잡해졌습니다."
date: 2026-01-29 02:41:40 +0900
categories: [Backend, Architecture]
tags: [backend, architecture]
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
2024~2025년의 “RAG(벡터DB+LLM)” 중심 앱은 빠르게 확산됐지만, 2026년 1월 시점의 실무 요구는 훨씬 복잡해졌습니다. 단순히 문서를 찾아 답을 생성하는 수준을 넘어, **여러 시스템을 조회하고(권한 포함), 여러 단계로 계획하고, 실패를 복구하며, 비용/지연시간을 통제**하는 “제품”을 만들어야 합니다.  
이 흐름에서 눈에 띄는 변화는 두 가지입니다.

1) **Agentic architecture의 부상**: 단일 RAG 파이프라인 대신, 계획(Planner)과 실행(Executor), 도구 호출(Tool calling), 관측/평가(Tracing/Evals)가 결합된 구조가 표준이 되어가고 있습니다. OpenAI는 Responses API와 웹/파일/컴퓨터 사용 같은 내장 도구를 “에이전트 앱의 기본 부품”으로 제시합니다.[^1]  
2) **스케일을 위한 “구조화 출력(Structured Outputs)”**: LLM을 시스템 컴포넌트로 쓰려면 “텍스트”가 아니라 **검증 가능한 contract(JSON Schema)** 가 필요합니다. OpenAI와 Azure OpenAI는 `strict: true` 기반의 구조화 출력을 핵심 안정장치로 다룹니다.[^2]

이 글에서는 2026년 1월 기준으로 “확장 가능한 AI 앱”을 만들 때 반복적으로 등장하는 설계 패턴을 **원리 중심**으로 정리하고, 바로 적용 가능한 예제 코드를 제공합니다.

---

## 🔧 핵심 개념
### 1) “Pipeline RAG”에서 “Agentic Workflow”로
전통적 RAG는 (질의 → 검색 → 컨텍스트 삽입 → 생성)으로 단순합니다. 하지만 엔터프라이즈에서 문제는:
- 데이터가 여러 시스템에 흩어져 있고, 권한/감사 로그/최신성이 중요
- 한 번 검색으로 끝나지 않고, **질문 재구성, 재검색, 교차검증, 후처리**가 필요

그래서 “고정 파이프라인” 대신 **워크플로우를 동적으로 조립**하는 접근(Planner가 모듈을 선택)이 뜹니다. 이 방향은 연구/실무 모두에서 “adaptive/agentic RAG”로 강화되고 있습니다.[^3]

### 2) 확장 가능한 Agent 설계 패턴 3종
1) **Supervisor(라우터) 패턴**: 단일 Supervisor가 요청을 분류해 Specialist에게 위임. 운영 난이도 대비 효과가 좋아 “기본값”으로 많이 씁니다.[^4]  
2) **Hierarchical 패턴**: 팀/도메인이 커지면 Supervisor의 책임을 계층화(상위가 팀을 관리).[^4]  
3) **Planner–Executor 패턴**: 계획은 Plan schema로 고정(Structured), 실행은 tool 기반으로 유연. “검증 가능한 계획” 덕분에 운영/디버깅이 쉬워집니다.

### 3) Structured Outputs = 계약(Contract) 기반 운영
LLM이 만든 결과를 다음 컴포넌트(검색기, DB, 결제, 티켓 발행)가 그대로 사용하려면 **형식이 100% 맞아야** 합니다. OpenAI는 JSON Schema를 강제하는 Structured Outputs를 제공하고, Azure 문서에서도 `strict: true`와 `parallel_tool_calls=false` 같은 운영 제약을 명시합니다.[^2]  
즉, 2026년형 AI 앱은 “프롬프트 잘 쓰기”보다 **스키마/상태/재시도/관측성**이 핵심입니다.

### 4) 메모리/상태는 “대화 로그”가 아니라 “압축 + 구조화”
장기 대화/개인화가 필요하면, 전체 대화를 토큰으로 들고 가는 방식은 즉시 비용/지연 문제로 붕괴합니다. 최근 연구들은 **세션 요약 + 구조화된 사용자 모델(KG 등)** 같이, 메모리를 “저장/검색 가능한 형태”로 분리합니다.[^5]

---

## 💻 실전 코드
아래는 **Supervisor(라우터) + Planner(구조화 출력) + Executor(툴 호출)** 형태의 최소 뼈대입니다.  
- Planner는 JSON Schema로 “실행 계획”을 고정
- Executor는 계획에 따라 함수를 호출
- 실패 시 재시도/폴백을 넣기 쉬운 형태

```python
# Python 3.11+
# pip install openai pydantic

from typing import Literal, List, Optional
from pydantic import BaseModel, Field
from openai import OpenAI

client = OpenAI()

# 1) 실행 계획(Contract): LLM이 반드시 이 스키마로만 계획을 내도록 강제
class Step(BaseModel):
    action: Literal["search_docs", "lookup_user", "draft_answer"]
    query: Optional[str] = None
    user_id: Optional[str] = None

class Plan(BaseModel):
    intent: Literal["qa", "support", "report"]
    steps: List[Step] = Field(min_length=1, max_length=6)

# 2) Tool(실제 시스템 연동은 여기로)
def search_docs(query: str) -> str:
    # TODO: vector DB / keyword search / enterprise search 연동
    return f"[DOCS] results for: {query}"

def lookup_user(user_id: str) -> str:
    # TODO: DB/CRM 조회 + 권한 체크 + 감사 로그
    return f"[USER] profile for: {user_id}"

def draft_answer(context: str) -> str:
    # 실제로는 모델 호출(최종 응답)로 갈 수 있음
    return f"Answer draft based on context:\n{context}"

# 3) Planner: Structured Outputs로 Plan 생성
def make_plan(user_message: str) -> Plan:
    resp = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": "You are a planner. Output ONLY a JSON object that matches the schema."},
            {"role": "user", "content": user_message},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "Plan",
                "schema": Plan.model_json_schema()
            }
        },
    )
    # response_format을 쓰면 모델이 스키마에 맞춘 JSON을 반환하도록 유도/강제
    plan_json = resp.choices[0].message.content
    return Plan.model_validate_json(plan_json)

# 4) Executor: 계획대로 실행(상태를 누적)
def run_plan(plan: Plan) -> str:
    context_parts = []
    for step in plan.steps:
        if step.action == "search_docs":
            context_parts.append(search_docs(step.query or ""))
        elif step.action == "lookup_user":
            context_parts.append(lookup_user(step.user_id or ""))
        elif step.action == "draft_answer":
            joined = "\n".join(context_parts)
            return draft_answer(joined)
    # draft_answer가 계획에 없으면 안전 폴백
    return draft_answer("\n".join(context_parts))

if __name__ == "__main__":
    user_message = "사용자 u-102의 최근 문의 이력을 참고해서 환불 정책을 안내해줘. 필요한 문서도 찾아봐."
    plan = make_plan(user_message)
    print("PLAN:", plan.model_dump())
    result = run_plan(plan)
    print(result)
```

핵심은 “LLM이 곧 코드”가 아니라, **LLM은 계획/분류/결정**을 하고 **실제 실행은 tool/서비스 레이어**가 맡는다는 점입니다. 이 분리가 확장성(Scaling)과 운영성을 만듭니다.[^1]

---

## ⚡ 실전 팁
- **Pattern 1: parallel_tool_calls는 신중히**  
  구조화 출력과 tool calling을 동시에 쓰면 제약이 생깁니다. Azure 문서에서도 structured outputs 사용 시 병렬 호출 제한을 명시합니다.[^6]  
  실무 팁: “Planner 단계는 반드시 단일 호출 + schema 강제”, “Executor 단계에서만 병렬화”가 안전합니다.

- **Pattern 2: RAG는 ‘인덱싱’보다 ‘최신성/권한’이 병목**  
  Google Cloud 아키텍처는 ingestion/serving을 분리하고 event-driven으로 최신성을 줄이며, 메타데이터로 검색 품질을 올리는 방향을 강조합니다.[^7]  
  실무 팁: 문서 chunking 튜닝보다 **메타데이터 설계(tenant, ACL tag, 문서 타입, 버전)** 가 먼저입니다.

- **Pattern 3: “Agent가 모든 걸 한다”는 환상 금지**  
  엔터프라이즈는 완전 자율보다, 좁은 워크플로우를 강하게 통제하는 방향으로 간다는 논의가 많습니다.[^8]  
  실무 팁: (1) intent 범위 제한 (2) tool allowlist (3) 실행 전 계획 검증 (4) 관측/감사 로그를 기본값으로.

- **Pattern 4: Memory는 토큰이 아니라 데이터 구조로 저장**  
  장기 대화는 “요약 + 구조화된 사용자 모델”로 분리해야 비용이 선형으로 폭증하지 않습니다.[^5]  
  실무 팁: “session summary(짧게)” + “facts/preferences(구조화)” + “retrieval” 3단으로 두세요.

---

## 🚀 마무리
2026년 1월 기준 AI 애플리케이션 아키텍처의 큰 흐름은 **고정 RAG 파이프라인 → Agentic Workflow**, 그리고 이를 운영 가능하게 만드는 **Structured Outputs(계약), Tooling(실행 분리), Memory(요약+구조화), 관측성(Tracing/Evals)** 로 정리됩니다.[^1]  

다음 학습 추천:
- “Planner–Executor + JSON Schema contract”를 팀 표준으로 정하기
- RAG를 “벡터DB 구축”이 아니라 “최신성/권한/메타데이터” 문제로 재정의하기[^7]
- Multi-agent 패턴(Supervisor/Hierarchical)을 작은 범위에 먼저 적용해 운영 루프(로그/리플레이/평가)를 만들기[^4]

[^1]: <https://openai.com/index/new-tools-for-building-agents//>
[^2]: <https://openai.com/index/introducing-structured-outputs-in-the-api/>
[^3]: <https://arxiv.org/abs/2508.01005>
[^4]: <https://jangwook.net/en/blog/en/langgraph-multi-agent/>
[^5]: <https://arxiv.org/abs/2512.12686>
[^6]: <https://learn.microsoft.com/en-us/%20azure/ai-services/openai/how-to/structured-outputs>
[^7]: <https://cloud.google.com/architecture/rag-genai-agentspace-vertexai>
[^8]: <https://www.techradar.com/pro/rag-is-dead-why-enterprises-are-shifting-to-agent-based-ai-architectures>
