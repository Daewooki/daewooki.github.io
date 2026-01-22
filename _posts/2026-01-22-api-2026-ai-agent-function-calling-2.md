---
title: "도구를 “API”로 바꾸는 순간: 2026년형 AI Agent Function Calling 구현 패턴 심층 분석"
date: 2026-01-22 02:26:44 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-01]
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
2026년 1월 기준, AI Agent를 “대화형 모델”로만 쓰는 팀은 점점 줄고 있습니다. 제품 요구사항이 **검색(Web Search)**, **사내 지식(File Search)**, **업무 시스템 액션(ERP/CRM/DB)**, **브라우저 조작(Computer Use)** 같은 *실제 도구 사용*으로 이동했기 때문입니다. OpenAI는 2025년 3월부터 Responses API + Tools + Agents SDK를 “Agents 플랫폼 빌딩 블록”으로 제시했고, Assistants API는 Responses API와의 기능 동등성 이후 **2026년 8월 26일 종료**가 공지된 상태라(즉, 지금은 마이그레이션이 현실 과제) 구현 패턴도 빠르게 표준화되고 있습니다. ([help.openai.com](https://help.openai.com/en/articles/8550641-assistants-api-v2-faq%23.eot?utm_source=openai))

이 글은 “Agent가 툴을 호출하고 → 결과를 받아 → 최종 응답을 만든다”를 넘어서, **Function Calling을 안정적으로 운영하는 패턴(스키마, 루프 제어, 병렬 호출, 검증/재시도)**까지 깊게 파고듭니다.

---

## 🔧 핵심 개념
### 1) Tool use vs Function Calling: “행위”와 “프로토콜”
- **Tool use**: 에이전트가 외부 능력을 쓰는 *행위(의도/정책)*  
- **Function Calling**: 모델이 “어떤 함수를 어떤 인자(JSON)로 호출할지”를 내보내는 *프로토콜(표현/출력 형식)*

현장에서 중요한 건 용어보다도 **“스키마 준수 + 실행 안전성 + 루프 제어”**입니다.

### 2) Structured Outputs(`strict: true`)는 “파싱”이 아니라 “계약”
OpenAI Function Calling에서 `strict: true`를 켜면, 모델이 생성하는 tool arguments가 **제공한 JSON Schema와 정확히 일치**하도록 강제됩니다. 이건 단순히 파서가 편해지는 수준이 아니라, *에이전트-애플리케이션 간 계약(Contract)*을 갖게 된다는 의미입니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))

다만 한계가 있습니다.
- Structured Outputs는 JSON Schema의 **일부 서브셋만 지원**합니다.
- **parallel tool calls와 호환되지 않음**: 병렬 호출이 켜져 있으면 스키마 불일치가 발생할 수 있어 `parallel_tool_calls: false`가 권장됩니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))

### 3) Tool choice 강제와 루프(무한 호출) 문제
Agent에 툴을 “등록”했다고 해서 모델이 항상 툴을 쓰진 않습니다. OpenAI Agents SDK(JS)에서는 `toolChoice`로 강제할 수 있고(`auto/required/none/특정 tool`), 툴 호출 이후 기본적으로 `tool_choice`를 다시 `auto`로 되돌려 **무한 루프를 방지**합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))

또한 `toolUseBehavior`로 “툴 결과를 LLM이 다시 읽고 최종 응답 생성(run_llm_again)” vs “첫 툴 결과를 최종 결과로 종료(stop_on_first_tool)” 같은 런타임 정책을 결정할 수 있습니다. ([openai.github.io](https://openai.github.io/openai-agents-js/openai/agents/classes/agent/?utm_source=openai))

### 4) 스키마만으로는 “사용 패턴”을 못 담는다 (그래서 Examples가 먹힌다)
JSON Schema는 타입/필수/enum을 잘 표현하지만, “옵션 필드 간 상관관계”, “도메인 규칙”, “언제 어떤 툴을 선택해야 하는지” 같은 *사용 패턴*은 표현이 약합니다. Anthropic은 이를 해결하기 위해 **Tool Use Examples**를 제안하며 복잡 파라미터 정확도가 크게 개선된다고 언급합니다. (OpenAI에서도 결국 같은 문제가 반복되므로, 예시 기반 가이딩은 벤더와 무관하게 유효한 패턴입니다.) ([anthropic.com](https://www.anthropic.com/engineering/advanced-tool-use?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 **OpenAI Agents SDK (Python)** 스타일로 “Function tool”을 만들고, `strict`에 준하는 강한 스키마/검증을 **애플리케이션 레벨에서 확실히** 가져가는 전형적인 패턴입니다. (SDK가 시그니처/Docstring에서 스키마를 자동 생성해주므로, *스키마 드리프트*를 줄이는 데 유리합니다.) ([openai.github.io](https://openai.github.io/openai-agents-python/tools/?utm_source=openai))

```python
# python 3.11+
# pip install openai-agents pydantic

from __future__ import annotations

import json
from pydantic import BaseModel, Field, ValidationError

# (1) 도구 입력 스키마를 "코드(타입)"로 고정: 계약(Contract)을 코드로 관리
class CreateTicketArgs(BaseModel):
    title: str = Field(..., description="티켓 제목(한 줄 요약)")
    priority: str = Field(..., description="low|medium|high|critical")
    labels: list[str] = Field(default_factory=list, description="kebab-case 권장")
    due_date: str | None = Field(None, description="YYYY-MM-DD (옵션)")

    # 간단 검증 예시
    @staticmethod
    def validate_priority(p: str) -> str:
        allowed = {"low", "medium", "high", "critical"}
        if p not in allowed:
            raise ValueError(f"priority must be one of {sorted(allowed)}")
        return p

    def model_post_init(self, __context):
        self.priority = self.validate_priority(self.priority)

# (2) 툴 구현: 실제 side-effect는 여기서만 발생
def create_ticket(args: CreateTicketArgs) -> dict:
    """
    실제 서비스에서는 DB/CRM/Jira 등을 호출.
    여기선 데모로 '생성된 티켓'을 반환.
    """
    ticket_id = "TCK-20260122-001"
    return {
        "ticket_id": ticket_id,
        "title": args.title,
        "priority": args.priority,
        "labels": args.labels,
        "due_date": args.due_date,
        "status": "created",
    }

# (3) 에이전트 루프(핵심): 모델이 tool call -> 우리 코드가 실행 -> 결과를 다시 모델로
# 실제로는 OpenAI Agents SDK의 Agent/Runner를 쓰면 더 짧아지지만,
# "패턴"을 보여주기 위해 수동 루프 형태로 작성.
def run_agent_simulated(model_output: dict) -> str:
    """
    model_output 예:
    {
      "tool_name": "create_ticket",
      "arguments": {"title":"...", "priority":"high", "labels":["bug"], "due_date":"2026-01-30"}
    }
    """
    # 1) 툴 이름 라우팅 (allowlist)
    if model_output.get("tool_name") != "create_ticket":
        return "지원하지 않는 tool 호출입니다."

    # 2) arguments를 신뢰하지 말고, 반드시 스키마로 검증
    try:
        args = CreateTicketArgs(**model_output["arguments"])
    except (KeyError, ValidationError) as e:
        # 3) 검증 실패 시: 재질문/재시도 전략을 태울 지점
        return f"tool arguments validation failed: {e}"

    # 4) side-effect 실행
    result = create_ticket(args)

    # 5) 여기서 보통은 result를 다시 LLM에 넣어 최종 자연어 응답을 생성(run_llm_again)
    # 데모에서는 JSON 문자열로 마무리
    return json.dumps(result, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    fake_tool_call = {
        "tool_name": "create_ticket",
        "arguments": {
            "title": "결제 모듈에서 간헐적으로 500 발생",
            "priority": "high",
            "labels": ["bug", "payment"],
            "due_date": "2026-01-30",
        },
    }
    print(run_agent_simulated(fake_tool_call))
```

핵심 포인트는 “모델이 준 JSON을 바로 실행하지 말고”:
- **tool allowlist**
- **스키마 검증(Pydantic/Zod/JSON Schema)**
- **side-effect 격리**
- **결과를 다시 모델에게 해석시키는 단계(run_llm_again)**  
를 *패턴으로 고정*하는 것입니다.

---

## ⚡ 실전 팁
1) **parallel tool calls는 ‘성능’보다 ‘정확성’이 먼저인 구간에선 끄기**  
Structured Outputs가 병렬 툴 호출과 충돌할 수 있습니다. 복잡 스키마/중요 액션(결제/권한/삭제)이라면 `parallel_tool_calls: false`로 단일 호출을 강제하는 편이 운영상 안전합니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))

2) **tool 정의는 “설명(description)”에 돈을 쓰는 구간**  
스키마는 구조만 보장합니다. “옵션 필드의 사용 조건”, “날짜 포맷”, “ID 규칙”, “어떤 상황에 이 툴을 써야 하는지”를 description + examples로 명문화하세요. Anthropic이 말하는 Tool Use Examples 접근은 실제로 OpenAI 계열에서도 동일하게 효과가 나옵니다. ([anthropic.com](https://www.anthropic.com/engineering/advanced-tool-use?utm_source=openai))

3) **무한 루프는 ‘모델 탓’이 아니라 ‘런타임 정책 부재’ 탓**  
OpenAI Agents SDK는 기본적으로 툴 호출 후 `tool_choice`를 auto로 되돌리는 식으로 루프를 줄입니다. 하지만 실무에선 추가로
- 최대 tool call 횟수
- 동일 tool+동일 args 반복 감지
- timeout / circuit breaker
를 넣어야 합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=openai))

4) **툴 출력도 스키마를 갖춰라 (특히 상태/에러)**
툴이 실패하면 “에러 문자열”만 던지지 말고 `{ok: false, error_code, retryable, user_message}`처럼 **머신이 처리 가능한 형태**로 반환하세요. 그래야 에이전트가 *재시도/대체 툴/사용자 확인* 플로우를 안정적으로 수행합니다.

5) **Assistants API 신규 개발은 피하고, Responses API/Agents로 설계 전환**
Assistants API는 deprecated이며 종료 일정이 명시되었습니다. 2026년에 신규 투자라면 Responses API + Tools + Agents SDK 중심으로 아키텍처를 잡는 게 비용을 줄입니다. ([platform.openai.com](https://platform.openai.com/docs/assistants/tools?utm_source=openai))

---

## 🚀 마무리
2026년형 AI Agent의 경쟁력은 “말을 잘함”이 아니라 **도구를 정확히 호출하고, 안전하게 실행하며, 결과를 일관된 계약으로 연결하는 능력**에서 나옵니다. 정리하면:

- Function Calling은 *도구 실행의 프로토콜*이고, **Structured Outputs(`strict`)는 계약**이다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))  
- 병렬 호출/루프/옵션 파라미터 상관관계가 **운영 난이도의 80%**를 만든다.  
- 해결책은 “스키마 + 예시 + 런타임 정책(루프 제어, 검증, 재시도)”을 패턴으로 고정하는 것.

다음 학습으로는:
1) OpenAI **Responses API의 tool(웹/파일/컴퓨터 사용)** 조합 패턴과 추적(Tracing) 기반 디버깅 ([openai.com](https://openai.com/index/new-tools-and-features-in-the-responses-api/?utm_source=openai))  
2) LangChain/LangGraph의 structured output 전략(ProviderStrategy vs ToolStrategy) 비교로 “벤더 교체 내성” 확보 ([docs.langchain.com](https://docs.langchain.com/oss/javascript/langchain/structured-output?utm_source=openai))  

을 추천합니다.