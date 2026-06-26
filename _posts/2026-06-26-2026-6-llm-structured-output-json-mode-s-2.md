---
title: "2026년 6월 기준 LLM Structured Output “JSON mode + Schema 강제”의 진짜 제약들 (그리고 함수 호출까지 안전하게 붙이는 법)"
date: 2026-06-26 04:20:35 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-06]
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
프로덕션에서 LLM을 “파서가 먹을 수 있는 형태”로 쓰려면 결국 **구조화된 출력(structured output)** 이 핵심입니다. 로그를 보면 장애의 상당수가 모델 성능이 아니라 **출력 포맷 붕괴(필드 누락/타입 불일치/여분 필드/코드펜스/부분 JSON)** 에서 시작하거든요. 그래서 2026년엔 다들 JSON을 요구하는데, 문제는 “JSON”만으로는 부족하다는 것:  
- **JSON mode**: “파싱 가능한 JSON”까지만 보장 (스키마는 보장 안 됨) ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))  
- **Structured Outputs / JSON Schema 강제**: “지정한 schema와 일치”를 보장(혹은 거의 보장) ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))  

언제 쓰면 좋나?
- 다운스트림이 **강타입(typed) 코드**(Pydantic/Zod/DTO)일 때
- **tool/function calling** 파이프라인(에이전트, 워크플로우)에서 “한 필드라도 깨지면 전체가 실패”하는 구조일 때
- 추출/분류/라우팅처럼 **결과를 DB/API 입력으로 바로 연결**할 때

언제 쓰면 안 되나?
- 결과 형태가 매번 바뀌는 **탐색적 대화/브레인스토밍** (스키마가 창의성을 억누르거나, 스키마 설계 비용이 더 큼)
- “정답 글” 자체가 목적이고, 구조화는 부가적인 경우(그럼 본문+별도 JSON을 고려)

---

## 🔧 핵심 개념
### 1) JSON mode vs Schema enforcement의 차이
OpenAI 문서 기준으로 **JSON mode**는 `response_format: { type: "json_object" }`로 “유효한 JSON”을 목표로 합니다. 단, *스키마 일치*는 보장하지 않고, 프롬프트에 “JSON” 명시가 없으면 공백 스트리밍 같은 엣지케이스도 경고합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))  
반면 **Structured Outputs**는 `json_schema`를 주고(일반적으로 strict), **constrained decoding**으로 “스키마에 맞는 토큰만” 생성 가능하게 제한합니다. 즉, 애초에 **불가능한 문자를 못 찍게** 만드는 방식입니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))

### 2) 내부 작동(흐름) 관점: “검증”이 아니라 “생성 자체를 제한”
실무적으로 중요한 포인트는 이것입니다.
- (사후) JSON.parse → validator → retry …가 아니라
- (사전) **decoder 단계에서 가능한 다음 토큰 집합을 스키마로 좁힘**  
이 덕분에 “마크다운 코드펜스” 같은 잡음이 구조적으로 사라집니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))  

### 3) 2026년 6월 ‘스키마 제약’이 생기는 이유: “전체 JSON Schema”가 아니다
여기서 함정이 시작됩니다. OpenAI/Claude/Gemini 모두 “JSON Schema 지원”이라고 말하지만, 실제론 **subset**입니다. 특히 OpenAI 쪽은 “엄격 모드에서 요구되는 형태”가 강합니다(예: 객체의 `additionalProperties: false`, required 강제 등). ([jsonic.io](https://jsonic.io/guides/openai-structured-outputs?utm_source=openai))  
Gemini도 공식 문서에 “subset 지원”을 명시합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/structured-output?utm_source=openai))  
Claude도 Structured Outputs를 “JSON schema나 tool definition에 정확히 맞춘다”고 하지만, 스키마 키워드 지원 폭/동작은 제공 형태에 따라 차이가 생길 수 있습니다. ([claude.com](https://claude.com/blog/structured-outputs-on-the-claude-developer-platform?utm_source=openai))  

결론: **“표준 JSON Schema를 한 번 만들어 멀티벤더에 똑같이 던지기”는 생각보다 잘 안 됩니다.**(CI에서 provider별 lint/정규화가 필요해지는 이유) ([reddit.com](https://www.reddit.com/r/LLMDevs/comments/1tarfl4/i_got_tired_of_digging_through_structured_outputs/?utm_source=openai))  

### 4) 함수 호출(function/tool calling)과의 관계
OpenAI 문서 기준으로 “function calling을 쓰면 JSON mode는 항상 켜진다”는 점이 포인트입니다. ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))  
하지만 **“툴 콜 JSON”이 파싱된다고 해서, 앱에서 기대하는 의미적 계약(필수 필드, enum, 범위)이 지켜지는 건 별개**입니다. 그래서 결국:
- tool schema를 **최소 공통 분모(subset)** 로 설계하고
- 호출 전후로 **서버 측 validator**(Zod/Pydantic) + 리커버리(재시도/휴먼 폴백)를 둬야 합니다.

---

## 💻 실전 코드
시나리오: “온콜 장애 요약 봇”  
- Slack/Email에서 들어온 incident 텍스트를 LLM이 읽고  
- **Jira 티켓 생성 API**에 바로 넣을 JSON을 생성  
- 실패하면 재시도/폴백  
핵심은 “예쁘게 요약”이 아니라 **API 입력 계약을 강제**하는 것입니다.

아래 예제는 **OpenAI Structured Outputs(Pydantic parse)** 형태로 작성합니다(실무에서 가장 빠르게 ‘스키마-코드 동기화’가 됩니다). OpenAI의 Structured Outputs 개요와 `refusal` 같은 응답 처리 개념은 공식 소개 글을 따릅니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))  

### 1) 초기 셋업
```bash
pip install openai pydantic python-dotenv
export OPENAI_API_KEY="..."
```

### 2) 스키마(Pydantic) + 호출 + 예상 출력
```python
from __future__ import annotations

import os
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, HttpUrl, conint
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

Severity = Literal["SEV1", "SEV2", "SEV3"]

class AffectedService(BaseModel):
    name: str = Field(description="서비스/컴포넌트 이름 (예: payments-api)")
    region: Optional[str] = Field(default=None, description="리전 (예: us-east-1)")

class JiraIncidentTicket(BaseModel):
    project_key: str = Field(description="Jira project key (예: SRE)")
    summary: str = Field(description="Jira summary 한 줄")
    severity: Severity
    customer_impact: str = Field(description="고객 영향 (구체적으로)")
    start_timestamp_utc: str = Field(description="ISO-8601 UTC, 예: 2026-06-26T02:13:00Z")
    detected_by: Literal["alert", "customer_report", "engineer", "unknown"]
    affected_services: List[AffectedService]
    external_status_page: Optional[HttpUrl] = None
    suggested_labels: List[str] = Field(description="Jira labels (snake/kebab 권장)")
    confidence: conint(ge=1, le=5) = Field(description="추출 신뢰도(1~5)")
    needs_human_review: bool = Field(description="티켓 자동생성 전 사람 확인 필요 여부")

def build_ticket(incident_text: str) -> JiraIncidentTicket:
    # Responses API의 parse 헬퍼를 쓰는 패턴(스키마==코드).
    # 실제 프로젝트에선 request_id, tracing, retry 정책을 함께 두세요.
    resp = client.responses.parse(
        model="gpt-4o-mini",  # 조직 표준 모델로 교체
        input=[
            {
                "role": "system",
                "content": (
                    "You are an SRE assistant. Output MUST be valid JSON matching the schema. "
                    "Do not include markdown fences. If unknown, use null/unknown and set needs_human_review=true. "
                    "You must include the word JSON in context."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Convert the incident report into a Jira ticket payload.\n\n"
                    f"INCIDENT REPORT:\n{incident_text}"
                ),
            },
        ],
        text_format=JiraIncidentTicket,  # Pydantic schema로 강제 파싱
    )

    # 안전: refusal/finish_reason 등은 SDK/엔드포인트에 따라 노출 형태가 다를 수 있어
    # 실제론 resp.output_text / resp.refusal 등을 확인하는 가드가 필요합니다.
    return resp.output_parsed

if __name__ == "__main__":
    incident = """
    At 02:13 UTC, payment checkout latency spiked in us-east-1. Alerts fired (p95 > 4s).
    We saw elevated 502s from payments-api due to upstream redis cluster failover.
    Customer support reported failed checkouts. Mitigation: scaled redis + disabled a new feature flag.
    Status page: https://status.example.com/incidents/abc123
    """
    ticket = build_ticket(incident)
    print(ticket.model_dump_json(indent=2))
```

예상 출력(예시):
```json
{
  "project_key": "SRE",
  "summary": "SEV2: Checkout latency and 502s due to Redis failover in us-east-1",
  "severity": "SEV2",
  "customer_impact": "Some customers experienced failed or slow checkout during the incident window.",
  "start_timestamp_utc": "2026-06-26T02:13:00Z",
  "detected_by": "alert",
  "affected_services": [
    { "name": "payments-api", "region": "us-east-1" },
    { "name": "redis", "region": "us-east-1" }
  ],
  "external_status_page": "https://status.example.com/incidents/abc123",
  "suggested_labels": ["checkout", "latency", "redis-failover", "us-east-1"],
  "confidence": 4,
  "needs_human_review": false
}
```

### 3) 확장: “함수 호출까지” 붙일 때의 권장 아키텍처
- LLM이 만든 JSON을 **바로 Jira에 POST**하지 말고
- 서버에서 `JiraIncidentTicket`로 재검증 → 라벨 정규화 → 위험 필드는 정책으로 덮어쓰기(예: project_key 고정)  
이렇게 하면, 설령 provider의 structured output이 “문법적으로는 맞는데 의미적으로 이상한 값”을 넣어도 방어가 됩니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **additionalProperties 차단 + required를 “전부”로 두기(닫힌 세계 가정)**  
OpenAI Structured Outputs 쪽은 객체 스키마를 “닫힌 형태”로 설계하는 게 안정적입니다(여분 필드가 downstream을 망가뜨리는 걸 원천 차단). ([jsonic.io](https://jsonic.io/guides/openai-structured-outputs?utm_source=openai))  

2) **멀티벤더면 ‘공통 스키마’가 아니라 ‘Provider별 컴파일 타깃’을 두기**  
Gemini도 subset JSON Schema임을 공식적으로 밝히고, OpenAI/Claude도 지원 키워드/동작이 1:1 호환이 아닙니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/structured-output?utm_source=openai))  
실무적으로는 “도메인 모델(내부 표준) → provider별로 변환/린트 → 런타임 검증”이 가장 덜 아픕니다. ([reddit.com](https://www.reddit.com/r/LLMDevs/comments/1tarfl4/i_got_tired_of_digging_through_structured_outputs/?utm_source=openai))  

3) **refusal/중단/부분 응답을 ‘정상 플로우’로 취급하고 설계**  
OpenAI는 Structured Outputs에서도 안전 정책에 따라 refusal이 가능하며, 이를 감지하기 위한 필드를 제공한다고 설명합니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))  
즉 “스키마만 맞으면 끝”이 아니라, **거절/불완전 응답을 상태 머신으로 다뤄야** 장애가 줄어듭니다.

### 흔한 함정/안티패턴
- “JSON mode면 스키마도 맞겠지”라는 기대: 문서상 명확히 아니고, 결국 validator+retry 지옥으로 갑니다. ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))  
- 스키마를 과하게 복잡하게 만들기: 스키마가 커질수록 모델이 채워야 할 결정 수가 늘고, 성능/정확도에 부담이 생길 수 있습니다(구조화가 ‘reasoning tax’가 될 수 있다는 연구들도 이 지점을 다룹니다). ([arxiv.org](https://arxiv.org/abs/2606.09410?utm_source=openai))  
- “provider가 보장하니 서버 검증 생략”: 멀티모델/멀티리전/버전 변경에서 가장 먼저 터집니다. (게이트웨이에서 정규화/검증한다는 현장 경험담이 반복됩니다.) ([reddit.com](https://www.reddit.com/r/LLMDevs/comments/1ufap2m/we_sent_the_same_json_schema_to_gpt55_claude/?utm_source=openai))  

### 비용/성능/안정성 트레이드오프
- **안정성↑**: 파싱 실패/재시도 감소 → 전체 지연시간/비용이 내려가는 경우가 많음  
- **유연성↓**: 스키마 설계/버전 관리 비용 증가, “예외 케이스” 표현이 어려워짐  
- **성능(정확도)↔**: 스키마가 복잡하면 모델의 여유 용량을 잡아먹어 품질이 떨어질 수 있음(모델/태스크에 따라 체감이 큼). ([arxiv.org](https://arxiv.org/abs/2606.09410?utm_source=openai))  

---

## 🚀 마무리
2026년 6월 시점의 결론은 간단합니다.

- “JSON을 뱉어라”는 이제 기본이고, **진짜 프로덕션은 schema enforcement**가 기준입니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))  
- 다만 “JSON Schema”라고 해서 표준 전체가 아니라 **provider별 subset + 제약**이 존재합니다(특히 객체의 닫힌 세계/required 강제 같은 형태가 실무 안정성에 직결). ([jsonic.io](https://jsonic.io/guides/openai-structured-outputs?utm_source=openai))  
- 함수 호출/에이전트 파이프라인에서는 “스키마 강제 + 서버 검증 + provider별 변환” 3단 방어가 가장 현실적입니다. ([reddit.com](https://www.reddit.com/r/LLMDevs/comments/1ufap2m/we_sent_the_same_json_schema_to_gpt55_claude/?utm_source=openai))  

도입 판단 기준(추천):
- 다운스트림이 typed/엄격하고, 자동화로 비용을 아끼고 싶다면 → **Structured Outputs 우선**
- 출력 형태가 유동적이고 실험이 우선이면 → **JSON mode + 느슨한 validator**(혹은 아예 비정형)로 시작, 이후 계약이 굳으면 스키마화

다음 학습 추천:
- OpenAI Structured Outputs의 constrained decoding/제약(공식 소개 + 가이드) ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))  
- Gemini structured output 문서(지원 키워드 subset 확인) ([ai.google.dev](https://ai.google.dev/gemini-api/docs/structured-output?utm_source=openai))  
- Claude structured outputs(툴 정의/스키마 기반 강제 출력 전략) ([claude.com](https://claude.com/blog/structured-outputs-on-the-claude-developer-platform?utm_source=openai))