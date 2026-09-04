---
title: "LLM Structured Output의 진짜 난관: “JSON은 맞는데 스키마는 왜 안 맞지?”를 끝내는 Schema 제약 실전 가이드"
description: "LLM을 프로덕션에 붙이면 가장 먼저 터지는 건 “파싱 실패”입니다. 사람이 보기엔 그럴듯한 JSON인데 \" 하나 빠지거나, required 필드가 누락되거나, \"2\"가 2로 와야 하는데 문자열로 오는 식이죠."
date: 2026-08-15 01:41:23 +0900
categories: [AI, LLM]
tags: [ai, llm]
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

LLM을 프로덕션에 붙이면 **가장 먼저 터지는 건 “파싱 실패”**입니다. 사람이 보기엔 그럴듯한 JSON인데 `"` 하나 빠지거나, `required` 필드가 누락되거나, `"2"`가 `2`로 와야 하는데 문자열로 오는 식이죠. 그래서 2024~2026 사이 대부분의 주요 벤더(OpenAI/Anthropic/Gemini)가 **structured output(= schema-constrained generation)**을 강하게 밀고 있고, “JSON mode”는 사실상 **중간 단계**가 됐습니다. OpenAI는 `json_schema + strict: true`로 *스키마 일치 자체*를 강제하는 Structured Outputs를 소개했고(기존 JSON mode와 구분), 스키마를 디코더에 걸어 “불가능한 토큰을 못 내보내는” 방식임을 강조합니다.[^1]

하지만 2026년 8월 기준, 실무에서의 포인트는 단순합니다:

- **언제 쓰면 좋나?**
  - 이벤트/로그 정규화, 문서/영수증/티켓 추출처럼 **정해진 필드로 ETL**해야 할 때
  - Agent에서 Tool 호출 파라미터가 깨지면 바로 장애 나는 **함수 호출(function calling)** 경로
  - 다중 벤더/다중 모델 운영에서 **retry/repair 비용**이 커지는 구간

- **언제 쓰면 안 되나?**
  - 결과 형태가 “진짜” 유동적인 브레인스토밍(결과 다양성이 가치인 작업)
  - 스키마가 너무 거대/복잡해서 **컨텍스트/지연/캐시** 이슈가 더 큰 경우(아래에서 다룸)
  - “구조는 맞지만 의미가 틀린” 문제(semantic correctness)는 여전히 남습니다. 

---

## 🔧 핵심 개념

### 1) JSON mode vs Structured Outputs(= JSON Schema 강제)의 차이
- **JSON mode**: “유효한 JSON”을 내도록 유도. 스키마 적합성은 보장 못 함.
- **Structured Outputs (strict)**: 개발자가 준 JSON Schema에 **정확히 일치하도록** 디코딩 단계에서 강제. OpenAI는 `strict: true`일 때 스키마를 “반드시 맞추게” 한다고 명시합니다.[^1]

핵심은 “프롬프트로 설득”이 아니라 **출력 가능한 토큰 집합 자체를 제한(constrained decoding)**한다는 점입니다.

### 2) 내부 작동 흐름(실무 관점)
프로바이더마다 구현 디테일은 다르지만, 대체로 이런 파이프라인을 탑니다.

1. **Schema 수신**
2. **지원하는 JSON Schema subset으로 컴파일**
   - 지원하지 않는 키워드가 있으면 **400 에러**가 나거나(엄격), 일부 벤더/SDK는 **클라이언트 사이드에서 제거/대체**하기도 합니다(“겉보기엔 동작하지만 제약이 약해지는” 위험). Anthropic 쪽 문서/가이드에서도 SDK가 미지원 제약을 제거하고 클라이언트 검증으로 보완할 수 있음을 언급합니다.[^2]
3. **Grammar/CFG 기반 제약 디코딩**
   - Anthropic은 strict tool use가 schema-valid 토큰만 샘플링하는 *grammar-constrained sampling*이라고 명시합니다.[^3]
4. **캐시/재사용**
   - OpenAI는 “새 스키마 최초 1회는 추가 지연, 이후 캐시로 빨라짐”을 공식적으로 언급합니다.[^1]
   - Anthropic도 strict tool use에서 스키마가 **일시 캐시(예: 24시간)**될 수 있음을 밝힙니다.[^3]

### 3) “스키마 강제”의 실제 제약(2026년 8월 실전 체크리스트)
structured output을 도입할 때 대부분 여기서 막힙니다.

- **JSON Schema 전체가 아니라 ‘subset’만 지원**
  - OpenAI/Google(Gemini) 모두 “subset 지원”을 명시합니다.[^1]
- **객체는 `additionalProperties: false` 강제/권장 레벨이 아니라 사실상 필수인 경우가 많음**
  - Azure OpenAI 문서에서 structured outputs의 제한으로 “objects에서 `additionalProperties: false`가 항상 필요”하다고 못 박습니다.[^4]
  - OpenAI SDK 이슈/커뮤니티에서도 `additionalProperties` 누락이 400 원인으로 반복됩니다.[^5]
- **Parallel tool calls와 비호환**
  - OpenAI는 structured outputs가 parallel function calls와 호환되지 않으며 `parallel_tool_calls: false`를 언급합니다.[^1]
- **“스키마는 맞는데 의미는 틀릴 수 있음”**
  - 예: enum은 맞는데 잘못된 선택, 숫자 범위는 맞는데 비즈니스 규칙 위반. 이는 structured output만으로 해결 불가. 
- **대형/복잡 스키마는 컨텍스트/비용/지연 문제**
  - 2026년엔 도구 스키마가 컨텍스트를 잡아먹는 문제가 연구로도 계속 나옵니다(스키마 압축/컴파일 계열).[^6]

---

## 💻 실전 코드

시나리오: **“장애 티켓 요약 → 표준 Incident 레코드(JSON) 생성 → 자동 라우팅(함수 호출)”**

- 입력은 Jira/Slack/메일에서 온 자연어
- 출력은 내부 Incident DB에 넣을 JSON
- 그리고 “라우팅 규칙 엔진”을 Tool로 호출해야 함
- 요구: **스키마 미스는 즉시 장애**이므로 `strict`가 필요

아래 예제는 OpenAI **Responses API** 스타일로 작성합니다(2025~2026 커뮤니티에서 `text.format` 경로가 자주 언급됨).[^7]  
(참고: 코드의 모델명은 조직에서 쓰는 최신 지원 모델로 교체하세요.)

### 0) 의존성/환경
```bash
pip install openai pydantic
export OPENAI_API_KEY="..."
```

### 1) 출력 스키마(Incident 레코드) + Tool 스키마(라우팅)
```python
from pydantic import BaseModel, Field
from typing import Literal, List, Optional

class IncidentRecord(BaseModel):
    incident_id: str = Field(description="ULID/UUID 형태의 내부 incident id")
    severity: Literal["SEV1", "SEV2", "SEV3", "SEV4"]
    service: str = Field(description="영향받은 서비스 식별자 (예: payments-api)")
    summary: str = Field(description="한 줄 요약")
    customer_impact: str = Field(description="고객 영향 설명(외부 공유 가능 문장)")
    suspected_root_cause: Optional[str] = Field(default=None, description="추정 원인(불확실하면 null)")
    signals: List[str] = Field(description="판단 근거가 된 로그/메트릭/증상 키워드 리스트")

# 라우팅 Tool: function calling 입력을 strict로 강제해야 런타임이 안 터짐
route_tool = {
    "type": "function",
    "function": {
        "name": "route_incident",
        "description": "Incident를 담당 온콜/큐로 라우팅한다",
        "strict": True,  # OpenAI tool strict
        "parameters": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["SEV1", "SEV2", "SEV3", "SEV4"]},
                "service": {"type": "string"},
                "queue": {"type": "string", "enum": ["oncall-core", "oncall-data", "oncall-platform", "triage"]},
                "reason": {"type": "string"}
            },
            "required": ["severity", "service", "queue", "reason"],
            "additionalProperties": False  # 실무에서 누락 시 400 빈번
        }
    }
}
```

### 2) LLM 호출: (a) Incident JSON 강제 → (b) Tool 호출 강제(선택)
```python
from openai import OpenAI
import json

client = OpenAI()

ticket_text = """
[PagerDuty] payments-api latency spike.
- 시작: 02:13 UTC
- 증상: p95 8s, error rate 12%
- 영향: checkout 실패 증가 (EU)
- 변경사항: 01:50 UTC에 DB connection pool 설정 배포
- 로그: "too many connections" / "timeout acquiring connection"
"""

resp = client.responses.parse(
    model="gpt-4o",  # 조직 정책에 맞게 교체
    input=[
        {
            "role": "system",
            "content": (
                "너는 SRE이다. 입력 티켓을 내부 IncidentRecord로 정규화하라. "
                "추측은 하되 불확실하면 suspected_root_cause는 null로 둬라."
            ),
        },
        {"role": "user", "content": ticket_text},
    ],
    # Responses API에서의 structured output 포맷(스키마 강제)
    text_format=IncidentRecord,
    tools=[route_tool],
)

incident: IncidentRecord = resp.output_parsed
print("=== IncidentRecord ===")
print(incident.model_dump_json(indent=2))

# 다음 단계: Tool 호출이 필요하면 모델에게 tool_choice를 강제하거나
# incident를 기반으로 서버에서 규칙엔진을 호출해도 됨.
```

#### 예상 출력(예시)
```json
{
  "incident_id": "01J...ULID",
  "severity": "SEV1",
  "service": "payments-api",
  "summary": "payments-api DB 커넥션 고갈로 checkout 실패 및 지연 급증",
  "customer_impact": "일부 지역(EU)에서 결제/체크아웃 실패 및 응답 지연이 발생했습니다.",
  "suspected_root_cause": "DB connection pool 설정 변경 이후 커넥션 누수 또는 상한 설정 불일치로 커넥션 고갈",
  "signals": [
    "p95 latency 8s",
    "error rate 12%",
    "too many connections",
    "timeout acquiring connection",
    "배포: DB connection pool 설정 변경"
  ]
}
```

> 포인트: 이 방식의 목표는 “예쁜 JSON”이 아니라 **DB insert 가능한 계약(Contract)**입니다. `additionalProperties: false`, `required` 조합이 없으면 필드가 조용히 늘어나거나(모델이 친절하게) 타입이 흔들립니다. Azure OpenAI도 이를 제한사항으로 명시합니다.[^4]

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) 스키마를 “검증 도구”가 아니라 “인터페이스 계약”으로 설계하라
- `additionalProperties: false`는 취향이 아니라 **운영 안정성의 핵심**입니다.
- 스키마를 넓게(allow extra) 잡으면 모델이 “설명 필드”를 계속 추가해 downstream이 흔들립니다.
- OpenAI/Azure 쪽에서 이 필드를 강하게 요구하는 흐름이 반복됩니다.[^4]

### Best Practice 2) Tool schema와 Output schema를 분리해 “단계별 확정”을 하라
- 1단계: IncidentRecord 같은 **정규화 JSON 생성**
- 2단계: 라우팅/조치 같은 **Tool 호출**
- OpenAI는 structured outputs가 parallel tool calls와 비호환임을 언급하므로, 멀티툴 병렬화를 기대하면 설계가 꼬입니다.[^1]  
  → “정규화 → 단일 Tool 호출(또는 서버 룰)” 구조가 보통 더 안정적입니다.

### Best Practice 3) “지원되는 JSON Schema subset”을 CI에서 고정 테스트하라
벤더마다 subset이 다르고, 심지어 SDK가 미지원 제약을 제거해버리면 **운영에서만 제약이 무너진 걸 발견**합니다. Anthropic 쪽에서도 SDK가 unsupported constraints를 제거할 수 있음을 언급합니다.[^2]  
권장:
- (a) 스키마를 provider에 한번 던져 **컴파일/생성 단계가 통과**하는지 테스트
- (b) “의도적으로 제약 위반” 프롬프트를 던져 **정말 막히는지**(adversarial test) 확인

### 흔한 함정 1) “스키마 강제 = 정답 보장” 착각
structured output은 **구문/타입 안정성**을 크게 올리지만, 의미적 정확성은 별개입니다. 연구에서도 “JSON은 맞아도 안전/충실한 트랜잭션이냐”는 다른 문제라고 지적합니다.   
→ 금액/정책/권한 같은 건 **서버 검증 + 재질문 루프**가 필요합니다.

### 흔한 함정 2) 첫 호출 지연/캐시를 무시한 채 스키마를 매 요청마다 동적으로 생성
OpenAI는 새 스키마 최초 요청에 추가 지연과 캐시를 언급합니다.[^1]  
- 스키마를 동적으로 만들면 캐시 히트가 깨져 p95가 튈 수 있습니다.
- 가능한 스키마는 **버전 고정(예: incident_record_v3)**하고, 변경은 배포 단위로 하세요.

### 비용/성능/안정성 트레이드오프
- **스키마가 커질수록**: 입력 토큰 증가 + 컴파일/캐시 비용 + 디코딩 제약으로 인한 **출력 품질 변화** 가능
- 반대로 **스키마가 작을수록**: downstream에서 의미 검증 부담 증가
- 결론: “한 방에 거대 스키마”보다 **2~3단계 파이프라인**이 대체로 싸고 안정적입니다(정규화 → 검증 → 액션).

---

## 🚀 마무리

2026년 8월 기준 structured output의 본질은 “LLM이 JSON을 잘 쓰게 하는 기능”이 아니라, **LLM을 기존 소프트웨어 시스템의 타입 계약(type contract) 안으로 밀어 넣는 장치**입니다.

도입 판단 기준은 이렇게 잡으면 됩니다:

- **반드시 도입**: Tool 호출 파라미터/DB insert/워크플로 엔진 입력처럼 *깨지면 장애*인 경로
- **부분 도입**: 요약/분류처럼 실패해도 재시도 가능한 경로(단, 파싱 실패 비용이 커지면 결국 도입)
- **도입 신중**: 결과 다양성이 가치인 생성 작업, 혹은 스키마가 지나치게 복잡해 컨텍스트/지연이 더 문제인 경우

다음 학습 추천:
- 각 벤더의 **“supported JSON Schema subset / limitations”** 문서를 먼저 읽고(OpenAI는 subset 제한과 병렬 tool call 비호환 등을 공개),[^1]
- 스키마를 고정 버전으로 운영하면서 **CI에서 provider별 schema-compile + adversarial constraint 테스트**를 구축하세요.

[^1]: <https://openai.com/index/introducing-structured-outputs-in-the-api/>
[^2]: <https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/tool-use-concepts.md>
[^3]: <https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use>
[^4]: <https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/structured-outputs?source=recommendations>
[^5]: <https://www.reddit.com/r/LangChain/comments/1lk6cv3>
[^6]: <https://arxiv.org/abs/2605.26165>
[^7]: <https://community.openai.com/t/response-format-not-available-for-the-responses-api/1147369>
