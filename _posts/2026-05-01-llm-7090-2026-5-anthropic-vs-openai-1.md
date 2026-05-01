---
title: "프롬프트 캐싱으로 LLM 비용 70~90% 줄이는 법 (2026년 5월 기준: Anthropic vs OpenAI 실전 설계)"
date: 2026-05-01 04:02:24 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-05]
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
에이전트/챗봇/코드리뷰 같은 “긴 컨텍스트를 매 호출마다 반복”하는 시스템에서, 비용의 본질은 **(1) 출력 토큰**과 **(2) 반복되는 입력 토큰(prefix)** 입니다. 전자는 제품 설계(응답 길이/툴 호출 횟수) 문제고, 후자는 **prompt caching**으로 꽤 직접적으로 깎을 수 있습니다.

- **언제 쓰면 좋나**
  - 매 요청마다 동일한 **system prompt + tool schema + few-shot + 정책/가이드라인 + 장문 문서**를 붙이는 워크로드
  - “한 세션에서 N번 호출” 또는 “유사 템플릿을 초당 수십~수백 번 호출”처럼 **재사용 빈도**가 높은 경우
- **언제 쓰면 안 되나(또는 기대하면 안 되나)**
  - 요청이 짧고(최소 토큰 조건 미달) 매번 내용이 크게 달라 **cache hit rate**가 낮은 경우
  - 캐시가 **짧은 TTL**(특히 5분) 안에 재사용되지 않는 배치성 트래픽
  - 개인정보/규정상 “캐시 자체”가 정책적으로 부담인 조직(대부분은 공급자 문서의 범위 내에서 안전하지만, 내부 컴플라이언스 검토는 필요)

2026년 5월 기준으로, OpenAI와 Anthropic은 둘 다 캐싱을 “입력 토큰 비용 절감”의 핵심 수단으로 밀고 있고, **작동 방식/가격 모델이 꽤 다릅니다**. OpenAI는 “자동 prefix 캐시 + cached_tokens로 측정”에 가깝고, Anthropic은 “내가 cache breakpoint를 선언하고, write/read 과금이 분리”된 구조입니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Prompt caching의 정의: “prefix 재사용”
두 회사 모두 공통적으로 **프롬프트의 앞부분(prefix)** 이 이전 요청과 같으면, 그 구간을 재계산하지 않고(또는 내부 상태를 재사용해) **더 싸고 빠르게 처리**합니다. 중요한 건 “완전히 동일한 요청”이 아니라 **‘앞에서부터 어디까지 동일하냐’** 입니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))

### 2) OpenAI: “자동 prefix 캐시 + 최소 길이 + usage로 계측”
OpenAI는 개발자가 별도 플래그를 넣지 않아도, **최근에 본 프롬프트의 가장 긴 공통 prefix**를 자동 캐시하고, 응답 `usage` 안에 `cached_tokens`(정확히는 `prompt_tokens_details.cached_tokens`)로 히트를 보여줍니다. 캐시는 보통 **5~10분 비활성 시 정리**, 늦어도 **마지막 사용 후 1시간 내 제거**로 안내됩니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))

구조적으로는:
- 동일 org 범위 내에서 “최근 처리한 prefix”를 재사용
- **1,024 토큰 이상** 등 “캐시가 걸리기 위한 최소 길이/단위”가 존재(세부 증분 규칙도 존재) ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))
- 가격표에는 **Cached input 단가**가 별도로 명시(모델별로 할인율이 다름: 2026년 가격표는 cached input이 매우 싸게 책정된 모델들이 있음) ([openai.com](https://openai.com/api/pricing/?utm_source=openai))

핵심 차이점:
- **“캐시 write 비용”을 개발자가 의식하지 않아도 된다**(자동 적용/자동 할인)
- 대신, “내가 어떤 구간을 캐시할지”를 Anthropic만큼 정교하게 통제하기는 어렵고, 결국 **prefix 안정성**(템플릿/정렬/툴 정의 순서)이 승부처입니다.

### 3) Anthropic: “cache_control breakpoint + read/write 분리 과금”
Anthropic은 요청 안의 특정 content block에 `cache_control`을 넣어 **여기까지는 캐시해도 좋다**는 “breakpoint”를 표시합니다. 캐시는 `tools → system → messages` 순서로 prefix가 구성되고, **가장 긴 매칭 prefix**를 찾되, 내부적으로 “이전 블록 경계들”에서도 자동으로 히트 체크를 수행합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))

중요한 실무 포인트는 과금:
- **Cache write(생성)**: 기본 입력 단가 대비 **프리미엄(예: +25%)**
- **Cache read(히트)**: 기본 입력 단가의 **10% 수준(=90% 할인)**  
즉, Anthropic은 “한 번 써서 캐시 만들고, 여러 번 읽어야” 이득이 커집니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))

또한 TTL은 기본 5분이고, 문서(다국어 페이지 포함) 기준으로 **1시간 TTL 옵션**도 언급됩니다(모델/기능 상태는 계정/지역/시점에 따라 다를 수 있어 운영 전 계측 필수). ([docs.anthropic.com](https://docs.anthropic.com/ru/docs/build-with-claude/prompt-caching?utm_source=openai))

### 4) 캐시 히트율 최적화의 본질: “고정 덩어리를 앞으로, 변동 덩어리를 뒤로”
둘 다 prefix 캐시이므로, 히트율은 사실상 아래로 결정됩니다.

- **앞부분이 얼마나 “정말로 동일”한가**
  - tool schema JSON의 키 순서/공백/설명 문자열이 바뀌면 prefix가 깨질 수 있음
  - system prompt에 “현재 시간” 같은 동적 문구가 들어가면 매 호출마다 달라져 prefix 손실
- **동적 입력(user message, tool result, 검색 결과)을 최대한 뒤로 미루고**
- **정적 컨텍스트(정책/역할/툴 정의/공통 지식/긴 문서)를 최대한 앞으로 당기기**

이건 단순 가이드가 아니라 “비용 모델”로 직결됩니다. 특히 Anthropic은 write/read가 분리 과금이라, **write를 자주 유발하는 구조**(조금만 바뀌어도 매번 새 캐시 생성)는 손해가 날 수 있습니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “고객지원 에이전트” 시나리오입니다.

- 매 요청마다 공통으로 쓰는 것:
  - (1) tool definitions (티켓 조회/환불 정책 조회)
  - (2) system policies (톤/금칙/개인정보 규정)
  - (3) 환불 정책/FAQ 문서(수천~수만 토큰)
- 매 요청마다 바뀌는 것:
  - user의 문의 내용
  - tool result(티켓 데이터)

목표: **공통 prefix를 안정화**해 OpenAI는 `cached_tokens`를 최대화, Anthropic은 `cache_creation_input_tokens`를 1회로 만들고 이후 `cache_read_input_tokens`로 전환.

### 0) 의존성/환경 변수
```bash
pip install openai anthropic fastapi uvicorn
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
```

### 1) “정적 prefix”를 안정적으로 만드는 빌더
- 정적 덩어리는 **문자열/JSON 직렬화 결과가 매번 동일**해야 합니다.
- tool schema는 dict를 즉석 생성하지 말고, **파일로 고정**하거나 `json.dumps(..., sort_keys=True)`처럼 결정적 직렬화를 사용하세요.

```python
# app/prompt_bundle.py
import json
from dataclasses import dataclass

@dataclass(frozen=True)
class StaticBundle:
    system_blocks: list
    tools: list
    policy_doc: str  # 길고 정적인 문서(FAQ/정책 등)

def load_static_bundle() -> StaticBundle:
    # 예: 배포 시점에 고정된 정책 문서(변경되면 캐시 효율이 떨어지는 건 의도된 트레이드오프)
    with open("data/refund_policy.md", "r", encoding="utf-8") as f:
        policy_doc = f.read()

    # tool schema도 고정(키 순서가 변하면 prefix 깨짐)
    with open("data/tools.json", "r", encoding="utf-8") as f:
        tools = json.load(f)

    system_blocks = [{
        "type": "text",
        "text": (
            "You are a customer support agent.\n"
            "Follow company policy strictly.\n"
            "Never request sensitive personal data.\n"
            "If policy is insufficient, ask a clarifying question.\n"
        )
    }]

    return StaticBundle(system_blocks=system_blocks, tools=tools, policy_doc=policy_doc)
```

`data/tools.json`는 예를 들면:
- `get_ticket(ticket_id)`
- `get_refund_eligibility(order_id)`
같은 함수 스키마(실 서비스의 실제 툴에 맞춰 구성)

### 2) Anthropic(Messages API): cache_control breakpoint로 “정책 문서까지 캐시”
핵심은 `cache_control`을 **정적 구간의 끝**에만 걸어 “여기까지 prefix로 캐시”되게 만드는 겁니다.

```python
# app/anthropic_cached_agent.py
import os
from anthropic import Anthropic
from app.prompt_bundle import load_static_bundle

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
STATIC = load_static_bundle()

MODEL = "claude-sonnet-4"  # 예시: 실제 사용 모델로 교체

def answer_with_anthropic(ticket_summary: str, user_message: str) -> dict:
    """
    현실적 시나리오:
    - ticket_summary: DB/툴에서 읽어온 요약(매번 바뀜)
    - user_message: 고객 문의(매번 바뀜)
    """
    # 정적 문서(길이 큼)를 system에 넣고 breakpoint로 캐시 후보 지정
    system = [
        *STATIC.system_blocks,
        {
            "type": "text",
            "text": "=== Refund & Support Policy (static) ===\n" + STATIC.policy_doc,
            "cache_control": {"type": "ephemeral"}  # 기본 5m TTL ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))
        },
    ]

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Ticket summary:\n{ticket_summary}\n\nCustomer says:\n{user_message}"}
            ],
        }
    ]

    resp = client.messages.create(
        model=MODEL,
        max_tokens=600,
        tools=STATIC.tools,  # tools도 캐시 계층에 포함 ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))
        system=system,
        messages=messages,
    )

    # 캐시 계측 포인트(필드명은 SDK/버전에 따라 다를 수 있으니 실제 응답을 로깅)
    usage = getattr(resp, "usage", None)
    return {
        "text": resp.content[0].text if resp.content else "",
        "usage": usage.model_dump() if usage else None,
    }

if __name__ == "__main__":
    out1 = answer_with_anthropic("ticket_id=123, order_id=999, status=delivered", "I want a refund, package is opened.")
    out2 = answer_with_anthropic("ticket_id=124, order_id=999, status=delivered", "Different message but same policy context.")
    print(out1["usage"])
    print(out2["usage"])
```

**예상 출력(형태 예시)**  
- 첫 호출: `cache_creation_input_tokens`가 크고 `cache_read_input_tokens`는 0에 가깝다  
- 두 번째 호출(5분 내): `cache_read_input_tokens`가 커지고, 전체 input 비용이 급감 ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))

### 3) OpenAI: “아무 설정 없이”도 prefix를 길게/안정적으로
OpenAI는 별도 `cache_control`이 아니라, **동일한 prefix를 반복**하면 자동으로 할인/지표가 잡힙니다. 응답 `usage.prompt_tokens_details.cached_tokens`를 반드시 로깅해서 실제 히트를 확인하세요. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))

```python
# app/openai_cached_agent.py
import os
from openai import OpenAI
from app.prompt_bundle import load_static_bundle

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
STATIC = load_static_bundle()

MODEL = "gpt-5.4"  # 예시. 실제 조직/프로젝트에서 승인된 모델로 교체

def answer_with_openai(ticket_summary: str, user_message: str) -> dict:
    # OpenAI: prefix 캐시이므로 "정적 system + 정책 문서 + 툴 정의"를 앞에 고정
    system_text = (
        STATIC.system_blocks[0]["text"]
        + "\n=== Refund & Support Policy (static) ===\n"
        + STATIC.policy_doc
    )

    # responses API가 아니라 chat.completions를 쓰는 경우도 많지만,
    # 핵심은 usage에서 cached_tokens 확인하는 것 ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": f"Ticket summary:\n{ticket_summary}\n\nCustomer says:\n{user_message}"},
        ],
        # tools를 쓰면 여기에 tools=... 추가(스키마 고정 중요)
    )

    usage = resp.usage.model_dump() if resp.usage else None
    cached = None
    if usage and "prompt_tokens_details" in usage:
        cached = usage["prompt_tokens_details"].get("cached_tokens")

    return {
        "text": resp.choices[0].message.content,
        "cached_tokens": cached,
        "usage": usage,
    }

if __name__ == "__main__":
    a = answer_with_openai("ticket_id=123, order_id=999, status=delivered", "I want a refund, package is opened.")
    b = answer_with_openai("ticket_id=124, order_id=999, status=delivered", "Different message but same policy context.")
    print("cached_tokens:", a["cached_tokens"], b["cached_tokens"])
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “프롬프트를 2계층으로 나눠라”: Static Prefix / Dynamic Tail
- **Static Prefix**: tools, system rules, few-shot, 장문 정책 문서, 고정 템플릿
- **Dynamic Tail**: user message, tool result, 검색 결과, 세션별 state

Anthropic은 breakpoint를 Static 끝에 두면 되고, OpenAI는 그냥 “앞부분이 항상 동일”하면 됩니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))

### Best Practice 2) 캐시 히트율은 “로깅 지표”로 운영하라
- OpenAI: `usage.prompt_tokens_details.cached_tokens`를 p50/p95로 수집 ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))
- Anthropic: `cache_read_input_tokens`, `cache_creation_input_tokens`(및 TTL별 분해 필드가 있으면 같이) 수집 ([docs.anthropic.com](https://docs.anthropic.com/ru/docs/build-with-claude/prompt-caching?utm_source=openai))

이걸 안 하면 “캐시 적용된 줄 알고” 비용이 그대로 나가는 상태로 몇 주를 태우게 됩니다.

### Best Practice 3) “동적 문자열”을 system에 넣지 마라
다음은 캐시를 박살내는 대표 패턴:
- system prompt에 `현재 날짜/시간`, `요청 ID`, `사용자 이름` 같은 값 삽입
- tool schema에 버전/빌드 넘버를 매 요청 갱신
- JSON 직렬화가 비결정적(키 순서 랜덤)인 상태로 tools를 생성

### 흔한 함정 1) Anthropic: “첫 호출이 캐시를 seed하기 전엔 병렬 호출이 다 miss”
Anthropic 문서에 따르면 **캐시 엔트리는 첫 응답이 시작된 뒤에야 사용 가능**합니다. 그래서 같은 정적 prefix로 병렬 10개를 쏘면, 첫 번째가 seed되기 전에 나머지가 miss 날 수 있습니다. 해결책은 “워밍업 1회 후 fan-out” 또는 “큐로 1개 먼저 흘려보내기”입니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))

### 흔한 함정 2) “최소 토큰 조건 미달”로 캐싱이 조용히 안 걸림
- OpenAI는 1,024 토큰 이상에서 캐싱이 본격 적용되는 것으로 안내됩니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))
- Anthropic도 모델별 최소 캐시 가능 토큰 조건이 있고, 그보다 짧으면 `cache_control`을 달아도 캐싱되지 않습니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))

따라서 “짧은 프롬프트” 서비스라면 캐싱보다 **Batch(-50%)**, 출력 축소, retrieval로 프롬프트 자체를 줄이는 게 더 큽니다(OpenAI는 Batch를 가격표에서 별도 안내). ([openai.com](https://openai.com/api/pricing/?utm_source=openai))

### 비용/성능/안정성 트레이드오프(의사결정 기준)
- OpenAI는 자동 할인이라 운영 단순성이 높지만, “내가 캐시 구간을 쪼개 통제”하기는 어렵습니다. 대신 usage로 히트가 보이므로 **관측 기반으로 템플릿을 다듬기** 좋습니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))
- Anthropic은 설계 자유도가 높고 read 단가가 매우 낮아(히트 시 90% 할인) “정적 덩어리 큰 서비스”에서 폭발적인 절감이 가능하지만, **write 프리미엄** 때문에 hit rate이 낮으면 오히려 손해가 될 수 있습니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 5월 시점의 prompt caching 비용 절감은 “기능 사용법”이 아니라 **프롬프트 아키텍처(정적/동적 분리) + 계측(캐시 히트 지표) + 트래픽 패턴(TTL 내 재사용)** 문제입니다.

도입 판단 기준(추천 체크리스트):
1) 매 요청에 반복되는 입력(prefix)이 **1,000~2,000 토큰 이상**인가?  
2) 같은 prefix가 **TTL(5분~) 내에 2회 이상** 재사용되는가? (Anthropic은 특히 중요) ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))  
3) `cached_tokens`(OpenAI) / `cache_read_input_tokens`(Anthropic)가 실제로 올라가는지 관측 가능한가? ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
4) tool schema/system 문서가 “조금만 바뀌어도” 캐시가 깨지는 구조를 감당할 수 있는가?

다음 학습 추천:
- OpenAI의 prompt caching 동작/계측 필드와 TTL 특성(운영 관점) ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
- Anthropic의 breakpoint 설계(도메인 문서/툴 정의/대화 이력의 경계 설계) ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?amp=&e45d281a_page=1&wtime=2418s&utm_source=openai))  
- 장기 에이전트 워크로드에서 “캐시를 깨지 않게” 만드는 프롬프트 구성 전략(연구/평가) ([arxiv.org](https://arxiv.org/abs/2601.06007?utm_source=openai))

원하면, 당신의 실제 워크로드(요청당 평균 system/tool 토큰, QPS, 세션 길이, 모델, TTL 내 재사용 패턴)를 기준으로 **손익분기 hit rate**를 계산하는 템플릿(스프레드시트용 수식/파이썬 스크립트)까지 같이 만들어 드릴게요.