---
title: "2026년 6월 기준: AI Agent의 “Tool Use + Function Calling”을 프로덕션에 올리는 구현 패턴 (Agents SDK/Responses API 중심)"
date: 2026-06-30 04:14:02 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-06]
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
AI Agent의 tool use(function calling)는 “모델이 말을 잘하는 것”에서 “모델이 일을 하게 만드는 것”으로 넘어가는 관문입니다. 하지만 2026년에도 현실은 단순하지 않습니다. 데모에서는 잘 되는데, 프로덕션에서는 **(1) 잘못된 tool 선택, (2) schema를 어기는 args, (3) 멀티스텝에서의 누적 오류, (4) 성공(200)했는데 의미 없는 실행** 같은 실패가 반복됩니다. ([agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/11/function-calling-reliability-production-agents-2026?utm_source=openai))

**언제 쓰면 좋은가**
- 외부 시스템(티켓 발행, DB 조회, 결제, 배포, 워크플로 실행 등)과 연결되어 **행동(action)** 이 필요할 때
- “정답 생성”보다 “정확한 API 호출 + 검증 + 재시도/중단”이 가치일 때
- 관찰 가능성(observability)과 감사(trace)가 필요한 업무 자동화

**언제 쓰면 안 좋은가**
- 도구 호출 없이도 답이 충분한데 모델이 “괜히” 호출하는 비용이 큰 경우(툴 호출은 토큰/지연/실패 확률이 같이 증가)  
  실제로 tool necessity(호출이 정말 필요한가) 자체가 주요 연구/벤치마크 주제가 됐습니다. ([arxiv.org](https://arxiv.org/abs/2605.09252?utm_source=openai))
- 도구가 **side effect**(환불/삭제/배포 등)를 만들지만 승인/정책/Idempotency 설계가 없는 경우
- 도구가 너무 많아(예: 100개+) tool definition 자체가 컨텍스트를 잠식하는 경우(설명 토큰 비용이 곧 신뢰성/비용 문제로 직결) ([presenc.ai](https://presenc.ai/research/ai-agent-tool-calling-accuracy-benchmarks-2026?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Tool Use vs Function Calling: “자유도 vs 신뢰성” 계약
현업에서 function calling은 tool use의 특수 케이스로 보는 게 실용적입니다.  
- **tool use**: “모델이 외부 능력을 쓰게 한다”라는 넓은 개념(검색, DB, 실행, 브라우저 등 포함)  
- **function calling**: 모델이 **미리 선언된 함수 목록 중 하나를 고르고**, **JSON Schema에 맞는 인자(arguments)** 를 구조적으로 생성하도록 강제하는 패턴  
→ 자유도를 줄이는 대신 **검증 가능성/관찰 가능성/재현성**이 올라갑니다. ([asoasis.tech](https://asoasis.tech/articles/2026-04-20-0853-function-calling-vs-tool-use-llms/?utm_source=openai))

### 2) 내부 작동 흐름: “Plan → Call → Validate → Execute → Observe → Continue”
2026년 기준, 구현의 핵심은 모델이 아니라 **런타임(오케스트레이터)** 입니다.

1. **Tool catalog 제공**: name/description/JSON Schema로 선언  
2. **모델 응답에서 tool_call 블록 생성**: 함수명 + arguments(JSON)  
3. **런타임 검증(필수)**: schema validation + 정책 체크(권한/횟수/위험도)  
4. **실제 실행**: API/DB/큐/서드파티 호출  
5. **tool_result를 컨텍스트로 주입**  
6. **다음 스텝 진행 / 종료 조건 판단**

OpenAI 쪽은 “오케스트레이션을 앱이 소유할지”에 따라 경로를 나눕니다:
- **Responses API**: “한 번의 모델 호출 + 도구 + 앱 로직” 정도면 충분할 때 ([platform.openai.com](https://platform.openai.com/docs/guides/agents-sdk))  
- **Agents SDK**: 상태/승인/가드레일/툴 실행을 앱이 직접 관리하며 **agent loop**를 코드로 운영할 때 ([platform.openai.com](https://platform.openai.com/docs/guides/agents-sdk))

또한 OpenAI는 2026년 4월에 Agents SDK에 **model-native harness**와 **sandbox execution**을 강조했습니다. “에이전트가 파일을 보고, 명령 실행하고, 코드를 고치는” 워크로드를 안전한 컨테이너/샌드박스에서 돌리려는 흐름입니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/))

### 3) 다른 접근과의 차이점: “프롬프트만으로는 부족해진 지점”
2026년에 많은 팀이 깨닫는 포인트는 이겁니다.

- 프롬프트로 “JSON 잘 만들어”라고 해도, **멀티스텝**으로 가면 정확도가 떨어짐  
- “tool call이 성공했다”와 “의도한 비즈니스 효과가 났다”는 다름(가장 비싼 실패 모드) ([agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/11/function-calling-reliability-production-agents-2026?utm_source=openai))  
- 따라서 **검증 계층(validator) + 정책 계층(policy) + 관측(trace/eval)** 을 별도 컴포넌트로 둬야 합니다 ([agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/11/function-calling-reliability-production-agents-2026?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “고객 지원 티켓 자동화” 시나리오입니다. 단순 검색 toy가 아니라, 실제로 자주 필요한 3가지를 같이 보여줍니다.

- (A) 모델이 `create_ticket`를 호출할지 말지 판단  
- (B) 호출한다면 args를 schema로 검증  
- (C) side effect 전 **policy gate(승인/제한)** 를 적용하고, 실행 결과를 다시 모델에 넣어 최종 응답 생성

### 0) 의존성/환경
```bash
pip install openai jsonschema python-dotenv
export OPENAI_API_KEY="..."
```

### 1) 도구 정의 + 검증/정책/실행 레이어 (핵심)
```python
import os, json, time, uuid
from typing import Any, Dict, Tuple
from jsonschema import validate, ValidationError
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# 1) Tool schema: 모델에게 "계약"을 준다
CREATE_TICKET_SCHEMA = {
    "name": "create_ticket",
    "description": (
        "Create a customer support ticket in our helpdesk system. "
        "Use ONLY when the user reports an issue that needs tracking or follow-up. "
        "Do NOT use for simple FAQ responses."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "customer_email": {"type": "string", "description": "User email", "pattern": r".+@.+"},
            "subject": {"type": "string", "minLength": 5},
            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "product": {"type": "string", "enum": ["billing", "api", "dashboard", "mobile"]},
            "summary": {"type": "string", "minLength": 20},
            "idempotency_key": {"type": "string", "description": "Prevent duplicates for retries"}
        },
        "required": ["customer_email", "subject", "severity", "product", "summary", "idempotency_key"],
        "additionalProperties": False
    }
}

# 2) 정책 계층: '가능한가'를 결정 (모델을 untrusted planner로 취급)
def policy_check(tool_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> Tuple[bool, str]:
    # 예: critical은 사람 승인 필요
    if tool_name == "create_ticket" and args.get("severity") == "critical":
        return False, "severity=critical requires human approval"
    # 예: 동일 세션에서 티켓 생성은 최대 1회
    if state.get("tickets_created", 0) >= 1:
        return False, "ticket creation limit reached (max 1 per session)"
    return True, "ok"

# 3) 실제 실행(여기서는 데모용 in-memory "헬프데스크")
FAKE_DB = {}

def create_ticket(args: Dict[str, Any]) -> Dict[str, Any]:
    # idempotency 처리
    key = args["idempotency_key"]
    if key in FAKE_DB:
        return {"status": "duplicate", "ticket_id": FAKE_DB[key]["ticket_id"]}

    ticket_id = f"TCK-{uuid.uuid4().hex[:10]}"
    FAKE_DB[key] = {
        "ticket_id": ticket_id,
        "created_at": time.time(),
        "payload": args,
    }
    return {"status": "created", "ticket_id": ticket_id}

# 4) tool dispatcher
TOOLS = {
    "create_ticket": create_ticket
}

def validate_tool_args(schema: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        validate(instance=args, schema=schema["parameters"])
        return True, "ok"
    except ValidationError as e:
        return False, f"schema_validation_error: {e.message}"
```

### 2) 에이전트 루프: “모델 응답 → tool_call 처리 → tool_result 주입”
```python
def run_support_agent(user_message: str, customer_email: str):
    state = {"tickets_created": 0}

    tools_for_model = [{
        "type": "function",
        "function": CREATE_TICKET_SCHEMA
    }]

    # 모델에 idempotency_key를 만들도록 강제하지 말고(실수 유도),
    # 앱이 생성해서 주입하는 편이 안정적이다.
    session_idempotency = f"session-{uuid.uuid4().hex}"

    messages = [
        {"role": "system", "content": (
            "You are a senior support engineer. "
            "If a ticket is needed, call create_ticket. "
            "Otherwise answer directly. "
            "Never invent policies; follow tool schema and ask clarifying questions if needed."
        )},
        {"role": "user", "content": user_message},
        {"role": "user", "content": f"Customer email is {customer_email} (trusted)."}
    ]

    # 1) 모델 호출: tool_call이 오면 실행 루프로 들어간다
    resp = client.responses.create(
        model="gpt-5",   # 예시: 실제 사용 모델은 조직 표준으로
        input=messages,
        tools=tools_for_model
    )

    # Responses API는 output items에 tool call이 섞여 올 수 있다 (플랫폼 구현에 따라 다름).
    # 여기서는 가장 흔한 패턴: tool call이 있으면 실행하고, tool_result를 추가한 뒤 다시 호출.
    tool_calls = []
    for item in resp.output:
        if item.type == "tool_call":
            tool_calls.append(item)

    if not tool_calls:
        return resp.output_text

    # 2) tool call 처리 (여기가 프로덕션의 본체)
    for call in tool_calls:
        tool_name = call.name
        args = json.loads(call.arguments)

        # 앱이 생성한 idempotency_key를 덮어쓰기
        args["idempotency_key"] = session_idempotency

        # (a) schema validation
        ok, reason = validate_tool_args(CREATE_TICKET_SCHEMA, args)
        if not ok:
            messages.append({"role": "assistant", "content": f"Tool args invalid: {reason}"})
            break

        # (b) policy gate
        allowed, why = policy_check(tool_name, args, state)
        if not allowed:
            messages.append({"role": "assistant", "content": f"Blocked by policy: {why}. Ask user for approval or downgrade severity."})
            break

        # (c) execute
        result = TOOLS[tool_name](args)
        state["tickets_created"] += 1

        # tool_result 주입
        messages.append({
            "role": "tool",
            "name": tool_name,
            "content": json.dumps(result)
        })

    # 3) 최종 사용자 응답 생성(티켓번호 포함 등)
    final = client.responses.create(
        model="gpt-5",
        input=messages
    )
    return final.output_text


if __name__ == "__main__":
    text = run_support_agent(
        user_message="결제는 됐는데 대시보드에서 플랜이 Free로 보여요. 로그아웃/로그인 해도 동일합니다.",
        customer_email="dev@example.com"
    )
    print(text)
```

### 예상 출력(예)
- 티켓이 생성되면: “TCK-xxxx”가 포함된 안내 + 추가 정보 요청(재현 스텝, 결제 영수증 등)
- 정책에 막히면: “critical은 승인 필요, severity를 high로 낮출까요?” 같은 승인 플로우

이 구조가 중요한 이유는, **모델이 tool_call을 “생성”하는 역할만** 맡고, **검증/승인/실행/관측은 런타임이 책임**지기 때문입니다. 멀티스텝에서의 신뢰성 저하와 “성공했지만 무의미한 실행”을 줄이려면 이 분리가 필수에 가깝습니다. ([agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/11/function-calling-reliability-production-agents-2026?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) Tool schema는 “문서”가 아니라 “모델용 계약서”
- name은 `verb_noun` 형태로 명확히 (`create_ticket`, `search_web`)  
- description에 **언제 쓰고 언제 쓰지 말지**를 박아넣기  
- string free-form을 줄이고 enum/required/additionalProperties로 제약  
→ argument 오류가 흔한 실패 모드라는 지적이 반복됩니다. ([openlegion.ai](https://www.openlegion.ai/en/learn/ai-agent-tool-use?utm_source=openai))

### Best Practice 2) “Validator”와 “Policy gate”를 분리하라
- validator: schema/타입/형식 검증(기계적으로 결정 가능)  
- policy: 권한, 횟수 제한, side effect 승인, 위험도별 라우팅  
이 둘을 섞으면 디버깅이 지옥이 됩니다. (실패 원인이 모델인지, 정책인지, 스키마인지 추적 불가)

### Best Practice 3) Tool set이 커지면 “Router → Executor” 2단으로 쪼개라
툴이 많아질수록 정확도/비용이 동시에 망가집니다. 2026년 벤치마크/실무 글에서 공통적으로 나오는 해법은:
- 1단: router LLM이 관련 tool 5~10개로 축소
- 2단: executor LLM이 축소된 tool만 보고 정확히 호출 ([presenc.ai](https://presenc.ai/research/ai-agent-tool-calling-accuracy-benchmarks-2026?utm_source=openai))

### 흔한 함정/안티패턴
- **“tool_call이 나오면 바로 실행”**: 실제 운영에서 가장 위험. 반드시 validate + policy + timeout + max steps.
- **무한 재시도 루프**: 멀티스텝에서 실패→재시도→실패가 토큰을 태우며 반복. 횟수 상한과 circuit breaker 필요. ([agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/11/function-calling-reliability-production-agents-2026?utm_source=openai))
- **관측 불가능한 에이전트**: 20번 tool call 후 사고가 나도 원인 파악이 안 됨. Agents SDK가 tracing/observability를 강조하는 이유가 여기에 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/agents-sdk))

### 비용/성능/안정성 트레이드오프
- 안정성(검증/승인/추가 스텝)을 올리면 **latency**와 **토큰 비용**이 증가
- router 단을 넣으면 호출이 1번 더 늘지만, 큰 tool set을 그대로 넣는 것보다 총비용이 줄어드는 경우가 많음(컨텍스트 절약 + 실패율 감소)
- sandbox 실행(파일/커맨드)은 강력하지만, 운영 복잡도(격리/권한/감사)가 증가 ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/))

---

## 🚀 마무리
2026년 6월의 결론은 간단합니다. **“Function calling은 모델 기능이 아니라 시스템 설계 문제”** 입니다.
- 도구 호출을 도입할지 판단할 때는  
  1) side effect가 있는가?  
  2) 멀티스텝이 필요한가?  
  3) 검증/정책/관측 레이어를 만들 역량이 있는가?  
를 먼저 보세요.
- 단순 자동화는 Responses API로 시작하고, 상태/승인/샌드박스/추적이 필요해지는 순간 Agents SDK로 자연스럽게 넘어가는 흐름이 OpenAI 문서/발표에서 분명합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/agents-sdk))
- 다음 학습 추천:
  - “tool necessity(언제 호출해야 하는가)” 계열 연구/벤치마크를 보고, 불필요한 호출을 줄이는 전략을 설계(비용 최적화 직결) ([arxiv.org](https://arxiv.org/abs/2605.09252?utm_source=openai))
  - 멀티스텝 tool-use에서 guardrail이 실제로 얼마나 깨지는지(TraceSafe 같은 평가 관점)도 같이 챙기기 ([arxiv.org](https://arxiv.org/abs/2604.07223?utm_source=openai))

원하시면, 위 예제를 **(1) router-executor 2단 구조**, **(2) human approval 인터럽트**, **(3) MCP 기반 외부 툴 디스커버리**까지 확장한 버전으로도 정리해드릴게요.