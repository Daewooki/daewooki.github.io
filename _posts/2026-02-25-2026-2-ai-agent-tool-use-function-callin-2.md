---
title: "2026년 2월 기준: AI Agent의 “Tool Use + Function Calling” 구현 패턴, 어디까지 표준화됐나"
date: 2026-02-25 02:49:46 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-02]
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
2024~2025년을 거치며 “Agent”는 더 이상 마케팅 용어가 아니라, **LLM이 외부 세계(데이터/시스템/실행환경)와 상호작용하는 소프트웨어 아키텍처**로 굳어졌습니다. 특히 실무에서 LLM을 “유용하게” 만드는 핵심은 모델이 똑똑한가보다 **언제/어떤 도구(tool)를/어떤 인자(schema)로 호출할지**를 안정적으로 설계·운영하는가에 달려 있습니다.

2026년 2월 현재 업계에서 사실상 합의된 방향은 다음입니다.

- “대화 생성” API와 “도구 호출”을 분리하지 말고 **하나의 실행 루프(run loop)**로 묶는다(= tool calling을 1급 시민으로 취급).
- 도구 입력은 자유 텍스트가 아니라 **JSON Schema 기반의 structured arguments**로 강제해 장애/오작동을 줄인다(Structured Outputs의 `strict` 같은 개념). ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-updates?utm_source=openai))
- 멀티 에이전트도 결국은 “에이전트를 도구처럼 호출”하는 **Manager(Orchestrator) 패턴**으로 수렴한다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))
- 그리고 OpenAI 진영에서는 2025년 “Responses API + Agents SDK”가 그 표준 런타임으로 자리잡는 흐름이며(Assistants → Responses로 중심 이동), 도구 사용/추적(tracing)까지 묶어 제공합니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))

이 글은 “2026년 2월 시점에서 가장 실전적인 Function Calling/Tool Use 구현 패턴”을 **원리 중심**으로 정리하고, 곧바로 가져다 쓸 수 있는 실행 코드까지 제공합니다.

---

## 🔧 핵심 개념
### 1) Tool use / Function calling의 본질: “모델 출력”이 아니라 “프로그램 인터럽트”
Function calling을 제대로 쓰면, 모델은 단순히 `텍스트를 생성`하는 대신 **(1) 도구 호출 요청(tool call)** 을 “구조화된 이벤트”로 내보냅니다. 런타임(당신의 앱)은 그 이벤트를 받아서:

1. JSON Schema로 입력 검증(guardrail)
2. 실제 함수/외부 API 실행(side effect)
3. 결과를 다시 모델에 주입(2차 추론/요약)

즉, 에이전트 루프는 “LLM → Tool → LLM”의 반복이며, 운영 안정성은 **스키마/검증/재시도/승인(approval) 게이트**에서 결정됩니다.

### 2) Structured Outputs(Strict schema)의 의미: “파싱 성공”이 아니라 “계약 준수”
JSON mode는 “JSON으로 파싱 가능”만 보장하고, 필드 누락/타입 오류는 여전히 발생합니다. 반면 Structured Outputs의 `strict` 계열은 **모델이 생성하는 arguments가 JSON Schema와 정확히 일치하도록** 강제하는 방향입니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-updates?utm_source=openai))  
실무적으로 이는 “tool input validation 실패율”을 낮추고, 재시도 정책을 단순화합니다.

### 3) Orchestrator(Manager) 패턴: 도구가 많아질수록 ‘중앙집권’이 이득
OpenAI Agents SDK 문서가 명시적으로 권장하는 멀티 에이전트 패턴 중 하나가 **Manager(agents as tools)** 입니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))  
핵심은:
- “대화의 주인”은 Manager 한 명
- 전문 기능은 **도구(함수) 혹은 서브 에이전트(agents as tools)** 로 캡슐화
- Manager가 최종 응답을 “요약/정책 적용/감사 로그”까지 책임

이 구조는 보안·감사·비용·성능(캐싱) 관점에서 실전성이 높습니다.

### 4) ToolChoice / ToolUseBehavior: 무한 루프를 제어하는 운영 파라미터
현장에서 흔한 장애는 “모델이 도구를 계속 호출하는 루프”입니다. Agents SDK는 tool 사용 후 기본적으로 toolChoice를 `auto`로 되돌려 루프를 완화하고, `toolUseBehavior`로 “첫 도구 호출에서 종료” 같은 전략도 제공합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))  
정리하면:
- **강제 호출(required)** 은 강력하지만, 반드시 종료 조건이 필요
- “첫 tool 결과를 최종 답으로 간주(stop_on_first_tool)”는 특정 워크플로(예: 단일 계산/단일 조회)에 특히 유효

---

## 💻 실전 코드
아래 예제는 “Manager Agent”가 `search_docs`(사내 문서 검색)와 `create_ticket`(티켓 생성) **두 가지 function tool**을 필요할 때만 호출하고, **승인 게이트(approval)** 를 통해 실제 사이드이펙트를 통제하는 최소 실전 루프입니다. (Python, OpenAI Agents SDK 스타일)

```python
import asyncio
from typing import Annotated, Optional, List, Dict, Any
from pydantic import BaseModel, Field

from agents import Agent, function_tool

# -------------------------
# 1) Tool input/output schema
# -------------------------
class SearchDocsInput(BaseModel):
    query: Annotated[str, Field(min_length=3, description="검색 질의(키워드/문장)")]
    top_k: Annotated[int, Field(ge=1, le=10, description="반환 문서 수")] = 5

class DocSnippet(BaseModel):
    doc_id: str
    title: str
    snippet: str

class CreateTicketInput(BaseModel):
    title: Annotated[str, Field(min_length=5, description="티켓 제목")]
    description: Annotated[str, Field(min_length=10, description="티켓 상세")]
    severity: Annotated[str, Field(pattern="^(low|medium|high)$", description="심각도")]

# -------------------------
# 2) Function tools
#    - 실제로는 DB/Vector DB/Jira/ServiceNow 등을 호출
# -------------------------
@function_tool
async def search_docs(input: SearchDocsInput) -> List[Dict[str, Any]]:
    """
    Search internal docs and return top snippets.
    Use when user asks about internal procedures, runbooks, or known issues.
    """
    # demo: 하드코딩 결과 (실무에서는 벡터 검색 + ACL 필터링 필수)
    results = [
        DocSnippet(
            doc_id="RB-102",
            title="On-call 장애 대응 Runbook",
            snippet="우선 영향 범위를 확인하고, 최근 배포/알람을 교차검증한다..."
        ),
        DocSnippet(
            doc_id="KB-77",
            title="API latency 상승 원인 Top 5",
            snippet="캐시 미스, DB 인덱스 누락, 과도한 fan-out, 서킷브레이커 미설정..."
        )
    ]
    return [r.model_dump() for r in results[: input.top_k]]

@function_tool(needs_approval=True)
async def create_ticket(input: CreateTicketInput) -> str:
    """
    Create an incident/support ticket.
    Use only when user explicitly requests a ticket or action is required.
    """
    # demo: 실제로는 외부 티켓 시스템 API 호출
    return f"TICKET-12345 created (severity={input.severity})"

# -------------------------
# 3) Manager Agent
# -------------------------
manager = Agent(
    name="Engineering Manager Agent",
    instructions=(
        "You are a senior engineer.\n"
        "- Use tools when needed.\n"
        "- For create_ticket, only do it if user explicitly asks, and keep it concise.\n"
        "- When using tool results, cite doc_id in the final answer.\n"
    ),
    tools=[search_docs, create_ticket],
    # 실무 포인트: toolChoice를 상황별로 바꾸되, 기본은 auto가 안전
    modelSettings={"toolChoice": "auto"},
)

async def main():
    user_msg = (
        "프로덕션에서 API latency가 올라갔어. 원인 후보랑 점검 순서를 알려주고, "
        "필요하면 high severity로 티켓도 만들어줘."
    )

    result = await manager.run(user_msg)

    # needs_approval=True인 tool이 호출되면 run이 인터럽트될 수 있음
    if result.interruptions:
        # 여기서 사람이 승인/거절을 결정 (예: UI에서)
        state = result.to_state()
        for item in result.interruptions:
            # 데모: 무조건 승인한다고 가정
            state.approve(item)
        result = await manager.run(state)

    print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())
```

이 코드에서 중요한 건 “도구 함수 구현”보다도:
- **입력 스키마를 얼마나 엄격히 정의하는지**
- **side effect가 있는 tool에 승인 게이트를 거는지**
- **run 중단/재개(pause/resume) 흐름을 제품에 어떻게 녹이는지**
입니다. Agents SDK는 “approval gates”와 “에이전트를 도구로 노출” 같은 패턴을 문서화해, 런타임 레벨에서 이 문제를 풀도록 유도합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/?utm_source=openai))

---

## ⚡ 실전 팁
1) **Tool은 ‘작게, 단일 책임’으로 쪼개라**  
도구가 커질수록 모델은 “입력 생성”을 어려워하고, 실패 시 재시도 비용이 커집니다. JS Agents SDK 가이드도 “One responsibility per tool”을 베스트 프랙티스로 강조합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/tools/?utm_source=openai))

2) **Schema는 곧 운영 계약(SLO)이다: 제약을 ‘Field’로 박아라**  
min/max, pattern, enum을 스키마에 넣으면 (a) 모델이 더 정확히 호출하고 (b) 런타임에서 즉시 차단됩니다. Python SDK는 Pydantic `Field` 기반으로 제약을 표현하는 흐름을 제시합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/?utm_source=openai))

3) **무한 루프 방지: toolChoice 강제는 “종료 정책”과 세트**  
특정 작업에서 `required`는 유용하지만, “tool 결과를 최종 답으로 볼지” 정책이 없으면 반복 호출이 나옵니다. Agents SDK의 `toolUseBehavior`/toolChoice reset 동작은 이 함정을 직접 언급합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))

4) **승인 게이트는 ‘보안’이 아니라 ‘제품 품질’ 기능**  
티켓 생성, 결제, 삭제 같은 작업은 오탐 한 번이 치명적입니다. `needs_approval` 같은 Human-in-the-loop는 규제 대응뿐 아니라 사용자 신뢰(“내가 원할 때만 실행”)를 만듭니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/?utm_source=openai))

5) **멀티 에이전트는 “에이전트 수”가 아니라 “Skill/Tool 라이브러리”가 핵심**
최근에는 “도메인별로 에이전트를 계속 늘리기보다, 재사용 가능한 skill/tool 묶음으로 일반 에이전트를 강화”하자는 관점도 힘을 얻고 있습니다. ([businessinsider.com](https://www.businessinsider.com/anthropic-researchers-ai-agent-skills-barry-zhang-mahesh-murag-2025-12?utm_source=openai))  
실무적으로는: (에이전트 10개)보다 (검증된 tool 30개 + 강한 orchestrator 1개)가 유지보수가 쉽습니다.

---

## 🚀 마무리
2026년 2월 기준으로 AI Agent의 tool use/function calling 구현은 “프롬프트 트릭”이 아니라, **스키마 기반 계약 + 실행 루프 + 승인/추적/종료정책**을 갖춘 소프트웨어 엔지니어링 문제로 정리되고 있습니다. 특히 OpenAI는 Responses API와 Agents SDK를 통해 “도구 사용을 위한 표준 런타임”을 제공하는 방향을 분명히 했고, function calling의 안정성은 Structured Outputs(엄격한 스키마) 쪽으로 진화했습니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))

다음 학습으로는:
- “agents as tools(Manager 패턴)”로 서비스 경계를 나누는 방법
- tool 결과에 대한 **output validation / post-processing**
- tracing 기반으로 “어떤 프롬프트/스키마가 tool 실패를 줄이는지” 관측하는 방법  
을 추천합니다.

원하시면, (1) 같은 예제를 **JavaScript/TypeScript(@openai/agents)** 버전으로 변환하거나, (2) “Responses API 단독(Agents SDK 없이)”으로 순수 루프를 직접 구현하는 패턴(재시도/백오프/캐싱 포함)으로도 확장해 드릴게요.