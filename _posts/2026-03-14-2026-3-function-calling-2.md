---
title: "도구를 “잘 쓰는” 에이전트 만들기: 2026년 3월 기준 Function Calling 구현 심층 분석"
date: 2026-03-14 02:42:20 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-03]
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
2026년 들어 AI Agent는 단순 Q&A를 넘어, **외부 시스템을 호출(tool use)해 실제 작업을 끝내는** 방향으로 빠르게 표준화되고 있습니다. 문제는 “모델이 똑똑하게 말하느냐”가 아니라, **언제 어떤 도구를 어떤 인자로 호출하고, 실패를 어떻게 복구하며, 호출 결과를 어떻게 상태로 축적하느냐**에서 품질이 갈린다는 점입니다. 커뮤니티에서도 “에이전트는 추론보다 tool calling에서 더 자주 실패한다”는 경험담이 반복되고, 실제로 `tool_choice` 같은 파라미터 하나로 도구를 아예 안 부르는 경우도 빈번합니다. ([reddit.com](https://www.reddit.com/r/aiagents/comments/1rjlzsk/tool_calling_is_where_agents_fail_most/?utm_source=openai))

또한 OpenAI는 Responses API를 중심으로 “단일 호출에서 여러 tool turn을 오케스트레이션”하는 설계를 강화하고, 컴퓨터 환경/런타임(컨테이너)까지 제공해 장기 실행 에이전트를 밀고 있습니다. 즉, 2026년 3월의 구현 포인트는 **Function Calling 자체**보다, “오케스트레이션 + 검증 + 상태 + 안전장치”입니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Function Calling vs Tool Use
- **Function Calling**: 모델이 “호출 의도 + JSON arguments”를 생성하고, 실제 함수 실행은 **애플리케이션(런타임)이 담당**합니다. (모델이 직접 API를 때리지 않습니다.)
- **Tool Use**: Function Calling을 포함한 상위 개념으로, Web Search/File Search/Computer Use 같은 **호스팅 도구**까지 포함해 “모델이 도구를 선택하고 결과를 받아 다음 행동을 결정”하는 루프 전체를 의미합니다. OpenAI는 Responses API에서 이를 통합적으로 제공하는 방향입니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))

### 2) JSON Schema 기반 “Typed Tool Contract”
2026년 실전에서 가장 중요한 건 도구 정의를 “문서”가 아니라 **계약(contract)** 으로 다루는 겁니다.
- OpenAI 진영: **Structured Outputs**(예: `strict: true`)로 “도구 인자(JSON)가 스키마와 정확히 일치”하도록 강제하는 흐름이 핵심입니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))
- Anthropic 진영도 tool 정의에 `input_schema`(JSON Schema)를 중심으로 시스템 프롬프트가 구성되고, 메시지 블록에 `tool_use`/`tool_result`가 오가도록 설계돼 있습니다. 즉, 스키마 중심 설계는 사실상 업계 공통 방향입니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use?utm_source=openai))

### 3) 오케스트레이션 루프(Agent Loop)의 표준 형태
구현을 단순화하면 다음 4단계가 반복됩니다.
1. 사용자 입력 + 현재 상태(state) + 도구 목록(tools)을 모델에 전달  
2. 모델 출력이 (a) 일반 텍스트인지 (b) tool call인지 판별  
3. tool call이면 **검증(validate) → 실행(execute) → 결과를 tool_result로 주입**  
4. 충분한 정보가 쌓이면 최종 답변 생성  

여기서 실패 지점은 거의 항상 2~3단계(“도구를 안 부름 / 인자가 틀림 / 같은 도구를 무한 반복 / 실패를 성공으로 오해”)에서 터집니다. ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1q9vzsi/agent_calling_tools_multiple_times/?utm_source=openai))

---

## 💻 실전 코드
아래는 “2026년형”으로 최소한의 안전장치를 포함한 **tool calling 런타임 루프 예제**입니다. (Python, OpenAI Responses API 스타일의 개념을 따르되, 핵심은 *패턴*입니다)

```python
# python 3.11+
# pip install openai jsonschema

import json
from jsonschema import validate, ValidationError
from openai import OpenAI

client = OpenAI()

# 1) 도구(함수) 정의: 스키마는 "계약"이다.
GET_WEATHER_SCHEMA = {
    "type": "object",
    "properties": {
        "city": {"type": "string", "minLength": 1},
        "unit": {"type": "string", "enum": ["c", "f"]},
    },
    "required": ["city"],
    "additionalProperties": False
}

def get_weather(city: str, unit: str = "c") -> dict:
    # 실제로는 외부 API 호출. 여기서는 데모.
    temp_c = 18
    temp = temp_c if unit == "c" else (temp_c * 9/5 + 32)
    return {"city": city, "unit": unit, "temp": round(temp, 1), "ok": True}

TOOLS = [{
    "type": "function",
    "name": "get_weather",
    "description": "Get current weather for a city. Use when user asks about weather.",
    "parameters": GET_WEATHER_SCHEMA,
    # OpenAI 계열에서는 Structured Outputs에 해당하는 'strict' 옵션을 쓰는 흐름이 일반적
    # (SDK/버전에 따라 위치/이름은 다를 수 있음. 핵심은 스키마 일치 강제다.)
    "strict": True
}]

def run_agent(user_text: str, max_turns: int = 6) -> str:
    messages = [
        {"role": "system", "content": "You are an agent. Use tools when needed. Return concise final answer."},
        {"role": "user", "content": user_text},
    ]

    # 2) 반복 루프: 모델 출력이 tool call인지 확인 → 실행 → 결과 주입
    for turn in range(max_turns):
        resp = client.responses.create(
            model="gpt-4.1-mini",   # 예시
            input=messages,
            tools=TOOLS,
            tool_choice="auto",     # 중요: 환경/어댑터에 따라 기본값이 none인 사례가 있음
        )

        # (A) 텍스트가 있으면 종료 (SDK마다 접근 방식은 다름)
        if getattr(resp, "output_text", None):
            return resp.output_text

        # (B) tool call 파싱: Responses API는 item 기반으로 tool call이 포함될 수 있음
        tool_calls = []
        for item in resp.output:
            if item.type == "tool_call":
                tool_calls.append(item)

        if not tool_calls:
            # 모델이 도구를 써야 하는데 안 쓴 경우: 재시도/가드 가능
            messages.append({"role": "assistant", "content": "I need to use a tool but no tool call was produced."})
            continue

        for call in tool_calls:
            if call.name != "get_weather":
                # 허용 목록 밖 도구 차단
                messages.append({"role": "tool", "name": call.name, "content": json.dumps({"ok": False, "error": "tool_not_allowed"})})
                continue

            # 3) 인자 검증(필수): 스키마 불일치/추가 필드/타입 오류 방지
            try:
                args = call.arguments if isinstance(call.arguments, dict) else json.loads(call.arguments)
                validate(instance=args, schema=GET_WEATHER_SCHEMA)
            except (json.JSONDecodeError, ValidationError) as e:
                messages.append({
                    "role": "tool",
                    "name": "get_weather",
                    "content": json.dumps({"ok": False, "error": "invalid_arguments", "detail": str(e)[:200]})
                })
                continue

            result = get_weather(**args)

            # 4) tool_result 주입: 성공/실패를 명확히(루프/재호출 방지에 중요)
            messages.append({
                "role": "tool",
                "name": "get_weather",
                "content": json.dumps(result)
            })

        # 다음 턴에서 모델이 tool 결과를 바탕으로 최종 답을 쓰도록 유도
        messages.append({"role": "assistant", "content": "Using the tool result above, respond to the user."})

    return "Failed to complete within max_turns."

if __name__ == "__main__":
    print(run_agent("서울 날씨 어때? 섭씨로 알려줘"))
```

핵심 주석을 다시 보면:
- `tool_choice="auto"`: 도구를 “존재만” 시키고 모델이 절대 안 부르는 구성 실수를 방지합니다. ([reddit.com](https://www.reddit.com/r/n8nforbeginners/comments/1rnfpho/spent_8_hours_on_a_toolcalling_ai_agent_the_tool/?utm_source=openai))  
- JSON Schema 검증: “모델이 만든 JSON”은 신뢰하면 안 됩니다. 스키마 검증 + 실패를 tool_result로 명시해야 에이전트가 복구 루프를 탑니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))  
- tool_result에 `ok`, `error`를 명확히: “첫 호출이 실패했는데 성공으로 오해”하면 같은 도구를 무한 재시도하는 패턴이 나옵니다. ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1q9vzsi/agent_calling_tools_multiple_times/?utm_source=openai))  

---

## ⚡ 실전 팁
1) **도구 설명(description)은 “언제/왜/금지조건”까지 써라**  
모델은 도구 선택을 설명 텍스트에 크게 의존합니다. “무엇을 하는지”만 쓰면 과다 호출/오호출이 늘고, “언제 써야 하는지 / 언제 쓰면 안 되는지 / 결과 형태가 무엇인지”를 적으면 안정성이 올라갑니다. (Anthropic도 tool definition을 바탕으로 시스템 프롬프트를 구성한다고 명시합니다.) ([docs.anthropic.com](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use?utm_source=openai))

2) **도구 인자 스키마는 좁게, additionalProperties는 막아라**  
실무에서 가장 흔한 장애는 “모델이 멋대로 필드 추가”하는 경우입니다. `additionalProperties: false` + enum/minLength 같은 제약을 적극 사용하세요. OpenAI의 Structured Outputs 흐름은 이 방향을 강하게 밀고 있습니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))

3) **장기 실행 에이전트는 ‘상태’를 텍스트가 아니라 구조로 관리하라**  
2026년형 에이전트는 한 번의 대화로 끝나지 않고, 컴퓨터 환경/컨테이너/스킬 레이어 등과 결합해 오래 달립니다. 이때 “지금까지의 사실/결정/도구 결과”를 대화 텍스트에만 누적하면 컨텍스트가 비대해지고 오류가 늘어납니다. OpenAI는 Responses API + 런타임/스킬/컨텍스트 컴팩션을 통해 장기 실행을 지원하는 그림을 제시합니다. ([openai.com](https://openai.com/index/equip-responses-api-computer-environment/?utm_source=openai))

4) **관측(Tracing) 없이는 디버깅 불가능**  
툴 호출은 “모델 출력 → 런타임 실행 → 결과 주입”의 멀티 컴포넌트 경로라, 로그/트레이싱 없이 원인 분석이 거의 불가합니다. OpenAI도 Agents SDK와 tracing을 빌딩 블록으로 강조합니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))

5) **도구가 많아질수록 ‘선택’ 문제는 Retrieval로 풀어라**  
수십~수백 개 도구를 한 번에 프롬프트에 넣으면 토큰 비용이 폭발합니다(정의만으로 수만 토큰). 그래서 “관련 도구만 동적으로 주입”하는 접근이 중요해졌고, 이를 다루는 연구도 나옵니다. ([anthropic.com](https://www.anthropic.com/engineering/advanced-tool-use?utm_source=openai))

---

## 🚀 마무리
2026년 3월 시점의 “Function Calling 구현”은 더 이상 단순 API 옵션이 아니라, **Typed contract(JSON Schema) + 오케스트레이션 루프 + 실패 복구 + 관측/추적**의 조합 문제입니다.  
- 스키마로 인자를 강제(Structured Outputs)하고 ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api?utm_source=openai))  
- `tool_choice` 같은 실행 스위치를 명확히 하며 ([reddit.com](https://www.reddit.com/r/n8nforbeginners/comments/1rnfpho/spent_8_hours_on_a_toolcalling_ai_agent_the_tool/?utm_source=openai))  
- tool_result에 성공/실패를 구조적으로 반환해 루프를 안정화하고 ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1q9vzsi/agent_calling_tools_multiple_times/?utm_source=openai))  
- 장기 실행/다도구 환경에선 상태와 도구 주입을 “설계”해야 합니다. ([openai.com](https://openai.com/index/equip-responses-api-computer-environment/?utm_source=openai))  

다음 학습으로는 (1) Responses API 기반 멀티턴 tool orchestration 패턴, (2) 도구 선택을 위한 tool retrieval/라우팅, (3) tracing+evaluation으로 tool accuracy를 계량하는 방법을 추천합니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))