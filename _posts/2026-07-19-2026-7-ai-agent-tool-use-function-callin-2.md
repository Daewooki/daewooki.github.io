---
title: "**2026년 7월, AI Agent의 “Tool Use + Function Calling”을 프로덕션에 넣는 법: 루프·계약·오케스트레이션 패턴 총정리**"
date: 2026-07-19 03:35:08 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-07]
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
2026년 기준으로 Agent를 “똑똑한 챗봇”에서 “업무를 실제로 처리하는 소프트웨어”로 끌어올리는 핵심은 **tool use(function calling)** 입니다. 모델이 자연어로만 답하는 게 아니라, **정형화된 호출(JSON Schema)로 외부 시스템(DB/HTTP/파일/큐/브라우저)을 실행**하고 그 결과를 다시 추론에 반영하는 구조죠. OpenAI는 Agents SDK/Responses API를 중심으로 에이전트 실행·도구·추적(Tracing) 인프라를 표준화했고, “샌드박스/워크스페이스에서 안전하게 파일·커맨드·툴을 다루는 harness”를 강조합니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/?utm_source=openai))

하지만 프로덕션에서 바로 마주치는 현실은 이겁니다.

- 도구 호출이 늘수록 **latency, token, 실패 지점**이 기하급수로 늘어남(“tool-use tax”). ([arxiv.org](https://arxiv.org/abs/2605.00136?utm_source=openai))  
- 모델이 *도구를 호출할 수 있다* ≠ *항상 도구를 올바른 순서/형식으로 호출한다* (오케스트레이션/가드레일 필요).
- “에이전트가 알아서”에 맡기면 디버깅이 악몽이 되므로, **루프·상태·계약**을 코드로 명시해야 함. ([platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works?utm_source=openai))

### 언제 쓰면 좋은가
- **실시간 진실 소스**가 필요한 작업(가격/재고/정책/사용자 데이터)  
- **부작용(side effect)** 이 있는 업무(예약, 결제, 배포, 티켓 발행)를 “사람이 승인하는 단계”와 결합할 때  
- 내부 시스템이 많은 조직에서 **하나의 자연어 인터페이스로 업무 자동화**를 하고 싶을 때

### 언제 쓰지 말아야 하는가
- 답이 모델 내부 지식/추론만으로 충분하고, 도구 호출이 오히려 비용/지연만 키우는 경우  
- 도구 호출 1회당 비용·지연이 큰데(외부 API/DB), 정확도 이득이 불확실한 경우(“tool-use tax” 구간) ([arxiv.org](https://arxiv.org/abs/2605.00136?utm_source=openai))  
- “항상 deterministic 해야 하는” 파이프라인(정산, 회계)에서 **모델이 호출 순서를 결정**하게 두는 경우

---

## 🔧 핵심 개념
### 1) Tool Use/Function Calling은 “계약(Contract)”이다
도구 호출은 *모델이 코드를 실행하는 것*이 아니라, 모델이 **“이 이름의 tool을 이 JSON args로 호출해줘”**라고 요청하면 **애플리케이션이 실행하고 결과를 되돌려주는 계약**입니다. 이때 신뢰의 경계(trust boundary)는 명확합니다: 모델은 실행 권한이 없고, 실행은 항상 당신의 런타임/인프라에서 합니다. ([platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works?utm_source=openai))

OpenAI 쪽에서 실무적으로 중요한 포인트는:
- tool은 “설명+스키마”로 정의되고, Agents SDK는 Python 함수 시그니처/Docstring에서 스키마를 자동 생성할 수 있음 ([openai.github.io](https://openai.github.io/openai-agents-python/tools/?utm_source=openai))  
- **Structured Outputs(strict: true)** 를 쓰면, 모델이 생성하는 tool args가 스키마와 정확히 일치하도록 강제 가능(= 파서/검증 비용과 실패를 줄이는 핵심 장치) ([help.openai.com](https://help.openai.com/en/articles/8555517?utm_source=openai))

### 2) 내부 작동 방식: “agentic loop”가 본체다
도구 사용 에이전트는 결국 다음 루프로 구현됩니다.

1. 모델 호출 → 응답에 tool call이 있으면
2. 애플리케이션이 tool 실행
3. tool result를 다시 모델에 제공
4. 더 이상 tool call이 없을 때까지 반복

Anthropic 문서가 이 루프를 **`while stop_reason == "tool_use"`** 형태로 아주 명확히 설명하는데, 이 구조가 사실상 업계 표준에 가깝습니다. ([platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works?utm_source=openai))  
OpenAI Agents SDK도 “running agents”에서 **tool_execution(동시성 제한 등)** 같은 실행 레벨 설정을 제공하면서, 결국 같은 문제(루프/동시성/실패)를 SDK 차원에서 다루게 합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/running_agents/?utm_source=openai))

여기서 실전 차이를 만드는 건 “루프가 있냐 없냐”가 아니라:

- **병렬 tool call**을 허용할지(속도↑, 그러나 실패/리트라이/순서 제어 난이도↑)
- **도구 선택을 모델에 맡길지** vs **라우팅 계층(규칙/분류/정책)** 을 둘지
- **side effect 도구**를 어떻게 “2-phase(Plan → Confirm → Commit)”로 만들지

### 3) 다른 접근과의 차이점
- **프롬프트 기반(“API를 호출했다고 가정하고…” )**: 빠르고 싸지만, 진실 소스/부작용/감사 추적이 필요하면 즉시 한계.
- **워크플로우 엔진(LangGraph류) 기반**: 모델의 자유도를 줄이고 상태 기계로 안정성을 얻는 방향. tool calling이 가능한 모델을 노드로 두고, persistence/debugging/배포를 강점으로 내세움. ([langchain-ai.github.io](https://langchain-ai.github.io/langgraph/how-tos/tool-calling/?h=tool&utm_source=openai))  
- **Agents SDK 기반**: OpenAI 모델/Responses API에 맞춘 도구/실행/추적 표준화 쪽. “컴퓨터/워크스페이스 harness”와 샌드박스 실행을 제품 방향으로 강하게 밀고 있음. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “고객 지원 티켓 자동 처리” 시나리오입니다. 핵심은 **(1) 의도 분류 → (2) 필요한 데이터 조회/수정 도구 호출 → (3) side effect는 반드시 Confirm gate** 를 두는 패턴입니다.  
(장난감 예제처럼 “날씨 조회”가 아니라, 실제 서비스에서 흔한 “DB 조회 + 상태 변경 + 감사 로그” 흐름을 최소 단위로 구성합니다.)

### 0) 셋업
```bash
python -m venv .venv
source .venv/bin/activate
pip install "openai-agents>=0.14.0" pydantic
export OPENAI_API_KEY="..."
```
(OpenAI Agents SDK는 tool/agent 실행과 tracing을 포함한 인프라를 제공하는 방향으로 진화 중입니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/?utm_source=openai)))

### 1) 기본 동작: “의도 분류 tool”로 라우팅 강제
- 많은 팀이 겪는 문제: 모델이 바로 `close_ticket()` 같은 side effect tool을 호출해버림  
- 해결: **첫 호출을 intent tool로 강제**하고, 백엔드가 허용된 다음 단계 tool set을 “단계별로” 열어줌

```python
# app.py
from __future__ import annotations

from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

from agents import Agent, Runner, function_tool

# --- (가짜) 데이터 스토어 ---
TICKETS: Dict[str, Dict[str, Any]] = {
    "TCK-1042": {"status": "open", "priority": "p2", "customer_tier": "pro", "summary": "결제 영수증이 안 보여요"},
    "TCK-1043": {"status": "open", "priority": "p1", "customer_tier": "enterprise", "summary": "SSO 로그인 실패(긴급)"},
}

AUDIT_LOG = []


class Intent(BaseModel):
    intent: Literal["triage", "answer_only", "request_more_info", "close_ticket"] = Field(
        description="사용자 요청을 처리하기 위한 1차 의도. side effect(종결)는 바로 하지 말고 close_ticket 의도로만 분류."
    )
    ticket_id: Optional[str] = Field(default=None, description="티켓 ID가 있으면 추출")
    reason: str = Field(description="왜 이 의도인지 한 줄 근거(감사/디버깅용)")


@function_tool
def classify_intent(user_message: str) -> dict:
    """
    고객지원 티켓 처리에서 1차 의도를 분류한다.
    - 정책: 상태 변경(종결/우선순위 변경)은 바로 실행하지 않는다. 우선 intent만 반환한다.
    """
    # 실제로는 LLM이 이 tool을 호출하도록 하고, 이 함수는 '분류 결과를 스키마로 반환'하는 역할이 아니라
    # tool 자체가 분류를 수행하는 게 아니라 "계약 예시"임.
    # 데모에서는 단순 룰로 흉내낸다.
    msg = user_message.lower()
    ticket_id = None
    for key in TICKETS.keys():
        if key.lower() in msg:
            ticket_id = key

    if "닫아" in user_message or "close" in msg:
        intent = "close_ticket"
        reason = "사용자가 티켓 종결을 명시적으로 요청"
    elif "어떻게" in user_message or "방법" in user_message:
        intent = "answer_only"
        reason = "정보 제공 요청"
    else:
        intent = "triage"
        reason = "문제 상황 파악 및 라우팅 필요"

    return Intent(intent=intent, ticket_id=ticket_id, reason=reason).model_dump()


@function_tool
def get_ticket(ticket_id: str) -> dict:
    """티켓 정보를 조회한다. 읽기 전용."""
    if ticket_id not in TICKETS:
        return {"ok": False, "error": "NOT_FOUND", "ticket_id": ticket_id}
    return {"ok": True, "ticket_id": ticket_id, "ticket": TICKETS[ticket_id]}


@function_tool
def propose_close_ticket(ticket_id: str, closing_note: str) -> dict:
    """
    티켓 종결을 '제안'만 한다. 실제 종결은 commit_close_ticket에서만 수행한다.
    """
    return {
        "ok": True,
        "proposal": {
            "action": "close_ticket",
            "ticket_id": ticket_id,
            "closing_note": closing_note,
        },
    }


@function_tool
def commit_close_ticket(ticket_id: str, closing_note: str, approved_by: str) -> dict:
    """
    실제 side effect: 티켓 상태를 closed로 변경한다.
    - 운영 정책상 인간/시스템 승인이 있어야만 호출되도록(가드레일) 설계한다.
    """
    if ticket_id not in TICKETS:
        return {"ok": False, "error": "NOT_FOUND"}

    TICKETS[ticket_id]["status"] = "closed"
    AUDIT_LOG.append(
        {"event": "ticket_closed", "ticket_id": ticket_id, "note": closing_note, "approved_by": approved_by}
    )
    return {"ok": True, "ticket_id": ticket_id, "new_status": "closed"}


triage_agent = Agent(
    name="support-triage-agent",
    instructions=(
        "너는 고객지원 티켓 처리 에이전트다.\n"
        "반드시 먼저 classify_intent를 호출해서 intent를 결정하라.\n"
        "intent가 close_ticket이어도 commit_close_ticket은 절대 직접 호출하지 말고 propose_close_ticket까지만 수행하라.\n"
        "티켓 ID가 없으면 사용자에게 요청하라."
    ),
    tools=[classify_intent, get_ticket, propose_close_ticket],
)

# 승인 후에만 열리는 별도 에이전트(혹은 동일 에이전트라도 tool set을 단계별로 다르게 주는 게 핵심)
commit_agent = Agent(
    name="support-commit-agent",
    instructions=(
        "너는 승인된 변경만 수행한다. 입력으로 proposal과 approved_by를 받으면 commit_close_ticket을 실행한다."
    ),
    tools=[commit_close_ticket],
)


def main():
    user = "TCK-1042 이거 이제 해결됐으니 닫아줘. 사용자에게 안내도 남겨줘."
    result = Runner.run_sync(triage_agent, user)
    print("=== agent output ===")
    print(result.final_output)

    # 현실적인 패턴: final_output(JSON)에서 proposal을 추출 → 승인 UI/정책엔진 → commit_agent 호출
    # 여기서는 데모로 항상 승인한다고 가정
    if isinstance(result.final_output, dict) and result.final_output.get("proposal"):
        proposal = result.final_output["proposal"]
        approved_by = "oncall_lead@company.com"

        commit_input = {
            "ticket_id": proposal["ticket_id"],
            "closing_note": proposal["closing_note"],
            "approved_by": approved_by,
        }
        commit_res = Runner.run_sync(commit_agent, f"{commit_input}")
        print("=== commit output ===")
        print(commit_res.final_output)

    print("=== ticket state ===")
    print(TICKETS["TCK-1042"])
    print("=== audit ===")
    print(AUDIT_LOG)


if __name__ == "__main__":
    main()
```

### 예상 출력(개략)
- 1단계(agent): close 제안(proposal)까지만 생성  
- 2단계(commit): 승인자 정보와 함께 실제 종결 수행 + 감사 로그

이 구조의 포인트는 “모델이 알아서 안전하게 호출하겠지”가 아니라,
- **도구를 단계별로 분리(propose vs commit)** 하고
- **tool surface를 런타임에 통제**해서(1단계엔 commit tool을 아예 주지 않음)
- 실수/오용을 구조적으로 막는다는 점입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “strict schema + 의미 있는 description”에 시간을 써라
OpenAI는 `strict: true`(Structured Outputs)로 스키마 적합성을 강제할 수 있다고 명시합니다. 이걸 안 쓰면 args 파싱 실패/유효성 검증/리트라이로 비용이 새나갑니다. ([help.openai.com](https://help.openai.com/en/articles/8555517?utm_source=openai))  
또, Agents SDK는 docstring/시그니처에서 스키마를 자동 생성하니(편함) “설명 문구가 곧 모델의 UI”라는 감각으로 작성해야 합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/tools/?utm_source=openai))

### Best Practice 2) Tool calling은 “오케스트레이션”이 절반이다
- 모델에게 모든 선택을 맡기면, 재현 불가한 실패 케이스가 쌓입니다.
- 대신 **(a) 의도 분류 단계**, **(b) 단계별 tool set**, **(c) 정책 엔진/승인 게이트**를 넣으면 안정성이 급상승합니다.
- LangGraph 같은 상태기계/그래프 오케스트레이션도 같은 문제의 해법을 제공(상태, 디버깅, persistence). ([langchain-ai.github.io](https://langchain-ai.github.io/langgraph/how-tos/tool-calling/?h=tool&utm_source=openai))

### Best Practice 3) 동시성/리트라이/타임아웃은 “모델 밖”에서 결정
Anthropic의 tool-use loop 설명이 말해주듯, tool은 결국 애플리케이션이 실행합니다. 그러면 **타임아웃, circuit breaker, idempotency key** 같은 건 전통적인 분산시스템 규칙을 그대로 적용해야 합니다. ([platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works?utm_source=openai))  
OpenAI Agents SDK도 tool_execution으로 로컬 function tool 실행 동시성을 제한하는 식의 제어 포인트를 제공합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/running_agents/?utm_source=openai))

### 흔한 함정/안티패턴
- **“도구를 많이 달면 더 똑똑해지겠지”**: 오히려 tool-use tax로 성능이 떨어질 수 있음(프로토콜/노이즈/왕복 비용). ([arxiv.org](https://arxiv.org/abs/2605.00136?utm_source=openai))  
- **side effect tool을 단일 함수로 제공**: `close_ticket()` 같은 도구 하나만 주면, 잘못된 호출이 곧 사고입니다. *propose/commit 분리*가 기본.
- **도구 실패를 모델에게만 떠넘김**: “다시 시도해”를 모델이 말하게 두지 말고, 백엔드에서 재시도 정책/백오프/대체 경로를 설계하세요.

### 비용/성능/안정성 트레이드오프
- tool call 1회는 보통 **LLM 왕복 + 외부 IO**라서 latency가 커집니다.
- 병렬화는 빨라지지만, **부분 실패 처리**(어떤 tool 결과만 도착, 어떤 건 타임아웃) 때문에 상태 관리가 어려워집니다.
- “도구 호출을 줄이는 방향”(캐시, 사전 질의, lightweight classifier로 라우팅)은 연구/현업 모두에서 반복되는 최적화 포인트입니다. ([arxiv.org](https://arxiv.org/abs/2605.00136?utm_source=openai))

---

## 🚀 마무리
2026년 7월 시점의 Agent tool use/function calling 구현에서 중요한 건 “어떤 모델/SDK를 쓰냐”보다도:

1) **Tool은 계약**이고, 실행/정책/안전은 애플리케이션 책임 ([platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works?utm_source=openai))  
2) **agentic loop**는 필수이며, 실패/동시성/상태를 코드로 다뤄야 함 ([openai.github.io](https://openai.github.io/openai-agents-python/running_agents/?utm_source=openai))  
3) 프로덕션에서는 **propose/commit**, **단계별 tool surface**, **승인 게이트**로 side effect를 통제해야 함  
4) 도구가 많아질수록 좋아지는 게 아니라, **tool-use tax**로 악화될 수 있으니 “정확도 이득 vs 왕복 비용”을 측정해야 함 ([arxiv.org](https://arxiv.org/abs/2605.00136?utm_source=openai))

### 도입 판단 기준(실무 체크리스트)
- 우리 문제는 “최신 데이터/부작용 작업”이 핵심인가?
- 도구 호출 실패가 나도 **안전하게 롤백/재시도** 가능한가?
- propose/commit, 승인, 감사 로그까지 포함한 **운영 설계**가 준비됐는가?
- tool call 수를 줄이는 최적화(캐시/라우팅/단계별 tool set)를 넣을 수 있는가?

### 다음 학습 추천
- OpenAI Agents SDK의 tool 카탈로그/실행 옵션(특히 tool types, running agents, sandbox/harness 방향) ([openai.github.io](https://openai.github.io/openai-agents-python/tools/?utm_source=openai))  
- Anthropic의 tool-use loop 문서(루프/stop_reason 중심으로 설계를 정리하는 데 도움) ([platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works?utm_source=openai))  
- “tool-use tax”류 연구를 참고해, 도구 호출이 실제로 이득인지 평가 지표를 먼저 만들 것 ([arxiv.org](https://arxiv.org/abs/2605.00136?utm_source=openai))

원하시면, 위 예제를 **(1) DB 트랜잭션 + idempotency key**, **(2) 병렬 tool call + 부분 실패 처리**, **(3) LangGraph 스타일 상태기계로 재구성**한 버전으로 확장해 드릴게요.