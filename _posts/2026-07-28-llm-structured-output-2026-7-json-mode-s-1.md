---
title: "LLM Structured Output: JSON mode만으론 부족한 “Schema 강제”의 현실적 제약과 함수 호출 설계법"
description: "프로덕션에서 LLM을 “파서 앞에 세우는” 순간, 실패의 대부분은 모델 지능이 아니라 인터페이스 계약(contract) 에서 터집니다."
date: 2026-07-28 03:18:41 +0900
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
프로덕션에서 LLM을 “파서 앞에 세우는” 순간, 실패의 대부분은 모델 지능이 아니라 **인터페이스 계약(contract)** 에서 터집니다. 예를 들어 “주문서 추출 → DB upsert → 결제/메일 발송” 같은 파이프라인에서 JSON이 한 글자만 깨져도 장애고, 더 흔하게는 **JSON은 유효한데 schema를 안 지켜서**(필수 필드 누락, 타입 틀림, enum 위반) 다운스트림이 터집니다.

2026년 7월 기준, 주요 벤더는 크게 3단계를 제공합니다.

- **JSON mode**: “유효한 JSON”까지만 보장(스키마 일치는 보장 X). OpenAI도 JSON mode는 schema 준수 보장이 없고, “json” 지시가 없으면 공백 스트리밍 같은 엣지케이스가 있어 방어가 필요하다고 명시합니다.[^1]  
- **Structured Outputs / strict schema**: **JSON Schema에 맞게 토큰 생성 자체를 제한(= constrained/grammar decoding)** 해서 형태를 강제. OpenAI는 `strict: true`로 함수 호출 인자(schema) 강제를 제공한다고 설명합니다.[^2]  
- **Tool input strict**(Anthropic): tool 입력을 schema-valid로 강제하며, 내부적으로 schema를 grammar로 컴파일해 샘플링을 제한한다고 밝힙니다.[^3]  

### 언제 쓰면 좋나
- LLM 출력이 **바로 코드 실행/DB write/외부 API 호출**로 이어지는 경우(“파싱 실패 = 장애”인 곳)
- 에이전트가 여러 툴을 오가며 **중간 상태를 구조화 데이터로 전달**해야 하는 워크플로
- 다국어/자유서술 입력에서 **추출(extraction) + 검증(validation)** 이 중요한 경우

### 언제 쓰면 안 되나
- 최종 산출물이 사람에게 읽히는 **자유형 텍스트**가 본질인 기능(보고서/요약/브레인스토밍). 억지 schema는 사고를 “칸 채우기”로 바꿔 품질을 깎을 수 있음.
- schema가 잦게 바뀌고 실험이 빠른 단계에서, 매번 strict schema를 붙이면 **프롬프트/스키마 버전 관리 비용**이 먼저 폭발함.

---

## 🔧 핵심 개념
### 1) JSON mode vs Schema 강제(Structured Outputs)의 차이
- **JSON mode**는 “파싱 가능한 JSON”만 목표. 즉 `{ "a": "1" }` 같은 JSON은 나오지만, `a`가 number여야 한다거나 `required`가 뭔지까지는 보장하지 않습니다. OpenAI Help Center도 이 구분을 명확히 합니다.[^1]  
- **Structured Outputs(Strict)** 는 **모델의 토큰 선택 공간을 schema에 맞는 토큰으로 좁혀** “형태적으로” schema에 맞게 만듭니다. OpenAI는 이를 “developer-supplied JSON Schemas에 정확히 맞춘다”고 설명하며, 함수 호출에서는 `strict: true`로 tool arguments가 schema에 “exactly match” 되게 한다고 말합니다.[^2]  
- Anthropic도 동일하게 **grammar-constrained sampling**이라는 표현으로 “샘플링을 schema-valid 출력으로 제한”한다고 밝힙니다.[^3]  

핵심은 “프롬프트로 부탁”이 아니라, **디코딩 레벨에서 출력 언어를 제한**한다는 점입니다.

### 2) 내부 작동 흐름(실무 관점)
실제로는 대개 이런 파이프라인입니다.

1. **JSON Schema(일부 subset)** 를 받음  
2. 벤더가 schema를 **grammar(생성 규칙)** 로 컴파일  
3. 생성 중 매 토큰마다 “지금 이 토큰을 내면 grammar 위반인가?”를 체크해 위반 토큰을 확률 0으로 만듦  
4. 결과적으로 **문법적으로 schema-valid** 한 JSON만 생성

이 방식의 장점은 “재시도/후처리 정규식”을 크게 줄이지만, 대신 **(a) schema subset 제한**, **(b) schema가 클수록 지연/비용**, **(c) semantic correctness(의미적 정합성)는 별개**라는 트레이드오프가 생깁니다. “JSON Schema로 파싱 실패는 줄어도 안전하고 올바른 트랜잭션인지까지 결정해주진 않는다”는 연구도 같은 맥락을 지적합니다.[^4]  

### 3) 함수 호출(Function calling)과 구조화 출력의 역할 분담
구조화 출력이 두 갈래로 갈립니다.

- **Tool input schema 강제**: 모델이 툴을 호출할 때 `arguments`가 schema-valid여야 함  
  - OpenAI: 함수 정의에 `strict: true`를 켜면 tool arguments가 schema에 정확히 맞게 생성[^2]  
  - Anthropic: tool 정의에 `strict: true`로 tool input을 schema-valid로 강제[^3]  
- **Final answer를 JSON으로 강제**: “최종 응답” 자체를 JSON schema로 받기(벤더별 API 형태는 다름)

실무에서 안정적인 패턴은 보통:
- **중간 단계는 tool call로만 이동(모델이 임의 JSON을 말하지 못하게)**  
- 최종 단계도 가능하면 **schema 강제된 JSON**으로 받고, UI/보고서는 서버가 렌더링

---

## 💻 실전 코드
현실적인 시나리오: “인보이스(자유 텍스트) → ERP 입력용 JSON → (검증) → 벤더 API 호출”  
아래 예제는 **OpenAI 함수 호출 + strict schema**를 통해 “ERP에 넣을 페이로드”를 강제합니다. (중요: schema 강제는 ‘형태’ 보장이지 ‘정답’ 보장이 아니라서, 서버 검증은 계속 합니다.)

### 0) 의존성/환경
```bash
pip install openai pydantic
export OPENAI_API_KEY="..."
```

### 1) Pydantic로 스키마 정의(= 단일 진실 소스)
```python
from pydantic import BaseModel, Field, conlist, condecimal
from typing import Literal

class LineItem(BaseModel):
    sku: str = Field(min_length=1)
    qty: int = Field(ge=1, le=1000)
    unit_price: condecimal(gt=0, max_digits=10, decimal_places=2)
    currency: Literal["USD", "EUR", "KRW"]

class ErpInvoiceUpsert(BaseModel):
    vendor_name: str = Field(min_length=1)
    invoice_number: str = Field(min_length=1)
    invoice_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")  # YYYY-MM-DD
    payment_terms_days: int = Field(ge=0, le=180)
    items: conlist(LineItem, min_length=1, max_length=50)
```

### 2) 함수(tool)로 “업서트 요청”만 허용
```python
from openai import OpenAI
import json

client = OpenAI()

TOOLS = [{
    "type": "function",
    "function": {
        "name": "erp_invoice_upsert",
        "description": "Upsert an invoice into ERP. Must be schema-valid.",
        "strict": True,  # 핵심: tool arguments schema 강제
        "parameters": ErpInvoiceUpsert.model_json_schema()
    }
}]

def call_llm_extract(invoice_text: str):
    resp = client.chat.completions.create(
        model="gpt-4o",   # 실제 사용 모델은 조직/프로젝트 표준에 맞게
        messages=[
            {"role": "system", "content": "Extract ERP invoice payload. Output ONLY via tool call."},
            {"role": "user", "content": invoice_text},
        ],
        tools=TOOLS,
        tool_choice={"type": "function", "function": {"name": "erp_invoice_upsert"}},  # 강제 호출
    )

    msg = resp.choices[0].message
    tool_call = msg.tool_calls[0]
    args = json.loads(tool_call.function.arguments)
    return args

raw = """
Invoice #A-19381
Vendor: ACME Supplies Inc.
Date: 2026/07/12
Terms: Net 30
Items:
- SKU: CAB-USB-C-2M Qty 12 Unit $7.50 USD
- SKU: DOCK-TB4 Qty 2 Unit $189.99 USD
"""

payload = call_llm_extract(raw)
print(json.dumps(payload, indent=2))
```

### 3) 서버측 “의미 검증” + idempotency
```python
from pydantic import ValidationError

def upsert_to_erp(payload: dict):
    try:
        model = ErpInvoiceUpsert.model_validate(payload)  # 최종 방어선
    except ValidationError as e:
        # 여기서 재시도/휴먼리뷰/격리 큐
        raise RuntimeError(f"Schema-valid output expected, but validation failed: {e}")

    # 의미 검증(예: invoice_number 중복, vendor whitelist, SKU 존재 여부)
    # idempotency_key = hash(vendor_name + invoice_number)
    # ERP API call...

upsert_to_erp(payload)
```

**예상 출력(형태 예시)**  
- `invoice_date`는 `2026-07-12`로 정규화  
- items는 1~50개, qty/unit_price/currency가 타입/제약에 맞게 생성

이 패턴의 포인트는 “LLM이 텍스트로 JSON을 말하게” 두지 않고, **tool call arguments로만** 구조화 데이터를 내게 해서 실패면을 줄이는 것입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Schema를 ‘업무 API 계약’처럼 버전 관리**
- `ErpInvoiceUpsertV1`, `V2`로 분리하고, 다운스트림도 버전 별로 라우팅하세요. strict를 켜면 작은 변경도 곧바로 런타임 실패로 이어지기 쉽습니다.

2) **의미 검증은 반드시 별도로**
- strict/structured outputs는 “문법/구조”를 보장합니다. 하지만 “SKU가 실제 존재하는지”, “금액 합계가 맞는지”, “벤더가 허용 목록인지”는 별개입니다. 구조가 맞는 **환각된 주문**은 여전히 가능합니다(semantic reliability 문제).[^4]  

3) **Tool choice를 강제해 ‘자유 텍스트 탈출’을 막기**
- `tool_choice=...`로 특정 tool을 강제하면, 모델이 설명을 덧붙이거나 반쯤 JSON을 말하는 상황을 줄입니다. OpenAI/Anthropic 모두 “툴 입력을 schema로 강제”하는 방향을 명확히 제공 중입니다.[^2]  

### 흔한 함정/안티패턴
- **“JSON mode면 schema도 대충 맞겠지”**: JSON mode는 유효 JSON만 보장하고 schema 준수는 보장하지 않습니다.[^1]  
- **과도하게 거대한 schema**: nested/enum/anyOf가 폭증하면 (벤더별로) subset 제한/성능 저하/컨텍스트 예산 문제로 실전에서 깨집니다. 툴 스키마가 커질수록 컨텍스트 예산을 잡아먹는 문제는 연구에서도 “tool-context trade-off”로 다룹니다.[^5]  
- **schema에 비밀/PHI를 넣기**: Anthropic은 tool schema가 캐시될 수 있고, PHI를 schema 자체에 넣지 말라고 구체적으로 경고합니다(필드명/enum/pattern 포함).[^3]  

### 비용/성능/안정성 트레이드오프
- strict schema는 재시도를 줄여 **전체 비용을 낮출 수** 있지만, schema 컴파일/제약 디코딩 때문에 **단일 호출 latency가 늘 수** 있습니다.
- 또한 “출력 자유도”를 줄이기 때문에, 복잡한 추론을 해야 하는 작업은 **품질이 떨어질 수** 있습니다(칸을 채우는 최적화로 수렴).

---

## 🚀 마무리
2026년 7월 시점의 결론은 단순합니다.

- **JSON mode는 ‘파싱 가능한 JSON’일 뿐**, schema 계약을 만족시키는 안전장치가 아닙니다.[^1]  
- 프로덕션 에이전트/자동화 파이프라인이라면, 가능한 구간에서 **Structured Outputs(Strict) + 함수 호출(tool use)** 로 “형태”를 강제하고, 서버에서 **의미 검증 + idempotency + 정책 체크**로 “내용”을 방어하는 2중 구조가 가장 비용 대비 효과가 좋습니다.[^2]  
- 다만 벤더별로 **지원하는 JSON Schema subset**이 다르고(예: Gemini도 subset 지원을 명시), portability는 생각보다 낮습니다. 멀티벤더 전략이면 “공통 subset + CI lint + 다운그레이드 경로”를 설계해야 합니다.[^6]  

### 도입 판단 기준(체크리스트)
- 출력이 **코드/DB/외부 호출**로 직결되는가? → Yes면 strict 우선
- schema가 **빈번히 변하는가**? → 변하면 버전 분리/점진적 롤아웃 필요
- semantic 오류가 치명적인가(결제/권한/데이터 삭제)? → 의미 검증/승인 플로우 필수

### 다음 학습 추천
- 벤더별 structured output 문서에서 “지원 keyword/subset” 표를 먼저 정리해, **내 스키마가 어디까지 이식 가능한지**를 초기에 확정하세요. (Gemini도 subset 지원을 명시)[^6]  
- “구조적 정합성(형태)”과 “의미적 정합성(정답/안전)”을 분리하는 테스트(골든셋 + adversarial prompts)를 CI에 넣는 걸 추천합니다.[^4]

[^1]: <https://help.openai.com/en/articles/8555517>
[^2]: <https://openai.com/index/introducing-structured-outputs-in-the-api/>
[^3]: <https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use>
[^4]: <https://arxiv.org/abs/2607.18261>
[^5]: <https://arxiv.org/abs/2605.26165>
[^6]: <https://ai.google.dev/gemini-api/docs/structured-output?authuser=14&hl=en>
