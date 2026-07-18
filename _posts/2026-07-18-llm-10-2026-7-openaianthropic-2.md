---
title: "프롬프트 캐싱으로 LLM 비용 10배 줄이기: 2026년 7월 기준 OpenAI·Anthropic “캐시 히트율” 실전 최적화"
date: 2026-07-18 03:14:56 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-07]
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

LLM 비용이 폭발하는 가장 흔한 패턴은 “매 요청마다 같은 긴 prefix(시스템 프롬프트, 툴 정의, 정책, 코드베이스 요약, Few-shot 예시)를 다시 읽게 만드는 것”입니다. 이때 **prompt caching**은 모델이 이미 본 **prompt prefix의 KV cache(또는 동등한 내부 표현)** 를 재사용하게 해서, 입력 토큰 비용과 TTFT(Time To First Token)를 동시에 낮춥니다. OpenAI는 공통 prefix 재사용 시 **캐시 입력 50% 할인**을 제공한다고 공개했고, Anthropic은 **cache hit(리드)가 기본 입력 가격의 10%** 수준으로 책정되어 “히트율”만 확보하면 비용 구조가 아예 달라집니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))

언제 쓰면 좋은가
- **에이전트/코드어시스턴트/긴 대화**처럼, 매 턴마다 *같은 시스템 지시문 + 같은 툴 스키마 + 같은 프로젝트 컨텍스트*가 반복되는 워크로드
- RAG에서 “문서 묶음”이 자주 재사용되는 케이스(예: 동일 고객의 계약서/매뉴얼을 계속 참조)

언제 쓰면 안 되는가(혹은 신중해야 하는가)
- **원샷(one-shot) 요청이 대부분**이라 prefix 재사용이 거의 없는 경우: 캐시가 “할인”이 아니라 “추가 write 비용”처럼 작동할 수 있습니다(특히 명시적 캐시/긴 TTL을 쓰는 설계에서). ([openai.com](https://openai.com/index/previewing-gpt-5-6-sol/?utm_source=openai))
- 프롬프트 상단에 시간/랜덤/세션ID 같은 **휘발성 문자열**을 넣는 구조(캐시 히트율을 0으로 만들기 쉬움)

---

## 🔧 핵심 개념

### 1) 용어 정리: cache write / cache read / breakpoint(캐시 경계)
- **cache write**: “이 prefix를 캐시로 저장”하는 비용. Anthropic은 5분 TTL 기준 **1.25×** write, 1시간 TTL은 더 비싸다고 문서로 명시합니다. ([platform.claude.com](https://platform.claude.com/docs/en/about-claude/pricing?f80ce999_sort_date=desc&fcdaa149_sort_date=desc&gsid=273b0434-5b38-44f6-957d-3159ae3aed2e&utm_source=openai))  
- **cache read(hit)**: 다음 요청에서 동일 prefix를 재사용하는 비용. Anthropic은 **hit가 표준 입력의 10%**라고 명시합니다. ([platform.claude.com](https://platform.claude.com/docs/en/about-claude/pricing?f80ce999_sort_date=desc&fcdaa149_sort_date=desc&gsid=273b0434-5b38-44f6-957d-3159ae3aed2e&utm_source=openai))
- **breakpoint**: 어디까지를 “prefix로 간주해 캐시할지”를 결정하는 경계. Anthropic은 `cache_control`로 “자동/명시” 두 방식을 제공하며, `tools → system → messages` 순서로 prefix를 잡는다고 설명합니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?curius=2015&utm_source=openai))

### 2) 내부 작동 흐름(구조/흐름 관점)
프롬프트 캐싱은 대개 다음 파이프라인을 따릅니다.

1. 요청이 들어오면 provider는 “캐시 가능한 prefix”를 **바이트 단위로 정규화/해시**(개념적으로)  
2. 동일 prefix가 **TTL 내** 존재하면  
   - prefix 구간은 **KV cache를 재사용**(또는 동등한 계산 재사용)  
   - 나머지 suffix(이번 턴의 유저 입력, 최신 tool result 등)만 새로 처리  
3. 동일 prefix가 없으면  
   - 전체를 새로 처리하면서 prefix 부분을 캐시로 “write”  
   - 이후 동일 prefix 요청은 “read(hit)”

Anthropic은 “prefix matching”과 “캐시 경계까지 100% 동일해야 히트”를 명시적으로 강조합니다. 즉, 프롬프트 상단의 *공백 하나, 툴 정의 순서 하나*가 바뀌면 통째로 miss가 납니다. ([claude.com](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything?utm_source=openai))

### 3) OpenAI vs Anthropic: 접근 차이(2026년 7월 기준 관찰 포인트)
- **OpenAI(자동 할인 중심)**: 공통 prefix 재사용 시 자동으로 prompt caching 할인 적용(2024 발표 기준 50% 할인). ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
  또한 2026년 공개된 GPT‑5.6 프리뷰 글에서는 “명시적 cache breakpoint/최소 캐시 수명(30분)” 및 **cache write가 1.25×**, cache read는 **90% 할인(=10% 과금)** 을 언급합니다. ([openai.com](https://openai.com/index/previewing-gpt-5-6-sol/?utm_source=openai))  
- **Anthropic(캐시를 설계 요소로 노출)**: `cache_control`을 요청 구조에 직접 넣어 **프롬프트를 ‘캐시-friendly’하게 재구성**할 수 있고, pricing 문서에서 **hit=10%**, **5m write=1.25×**, **1h write=2×** 등 “손익분기”를 명확히 제시합니다. ([platform.claude.com](https://platform.claude.com/docs/en/about-claude/pricing?f80ce999_sort_date=desc&fcdaa149_sort_date=desc&gsid=273b0434-5b38-44f6-957d-3159ae3aed2e&utm_source=openai))

핵심은 둘 다 “기술적으로는 prefix 재사용”인데, 실무에선 **(1) 어디를 prefix로 고정할지**, **(2) 변동 콘텐츠를 어디에 배치할지**, **(3) TTL과 write 비용까지 포함한 ROI 계산**이 성패를 가릅니다.

---

## 💻 실전 코드

아래는 “코드리뷰 에이전트” 같은 현실적인 워크로드를 가정합니다.

- 고정 prefix:  
  - 프로젝트 규칙(코딩 컨벤션)  
  - 툴 정의(예: `get_diff`, `read_file`)  
  - 리뷰 체크리스트(보안/성능/테스트)
- 변동 suffix:  
  - 이번 PR diff  
  - CI 로그 일부  
  - 질문(이번 변경의 의도)

목표: **prefix는 캐시 히트**, suffix만 매번 새로 태워서 비용을 줄입니다. 또한 매 응답에서 **cache hit 토큰**을 로깅해 히트율을 수치로 관리합니다(“최적화”는 결국 계측이 전부).

### 0) 의존성/환경

```bash
python -m venv .venv
source .venv/bin/activate
pip install anthropic==0.34.0 python-dotenv==1.0.1
export ANTHROPIC_API_KEY="..."
```

### 1) 기본 동작: Anthropic Messages API + explicit breakpoint

```python
import os
import json
import time
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PROJECT_RULES = """
You are a senior reviewer.
Repo conventions:
- Python: ruff + mypy, prefer explicit types
- Security: never log secrets
- Performance: watch N+1 queries
Return JSON with: summary, risks[], suggestions[]
""".strip()

REVIEW_TOOLING = """
Available tools (conceptual):
- get_diff(pr_number) -> unified diff
- read_file(path) -> file contents
- search_repo(query) -> matched snippets
You MUST cite file paths when you mention code.
""".strip()

CHECKLIST = """
Checklist:
1) Correctness regressions
2) Security / injection / secrets
3) Performance hotspots
4) Test gaps
5) API compatibility
""".strip()

def review_pr(pr_number: int, diff_text: str, ci_snippet: str):
    # 핵심: prefix 블록(규칙/툴/체크리스트)에 cache_control을 붙여 "여기까지"를 캐시 대상으로 고정
    # Anthropic 문서상 tools/system/messages 순으로 prefix가 잡히므로, 변동 요소(diff)는 messages 뒤쪽에 둔다.
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1200,
        temperature=0.2,
        system=[
            {
                "type": "text",
                "text": PROJECT_RULES + "\n\n" + REVIEW_TOOLING + "\n\n" + CHECKLIST,
                "cache_control": {"type": "ephemeral"}  # 5-minute cache
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"PR #{pr_number} diff:\n{diff_text}\n\nCI snippet:\n{ci_snippet}\n\nDo the review."}
                ]
            }
        ],
    )

    usage = resp.usage.model_dump()
    # 언어 SDK마다 필드명이 다를 수 있으니 usage 전체를 우선 로깅하는 습관 추천
    print("USAGE:", json.dumps(usage, ensure_ascii=False, indent=2))
    return resp.content[0].text

if __name__ == "__main__":
    # 현실적인 시나리오: 같은 프로젝트 규칙/툴/체크리스트는 고정, diff/CI만 바뀜
    pr = 1842
    diff1 = "diff --git a/app/db.py b/app/db.py\n... (large diff) ..."
    ci1 = "FAILED: test_user_auth.py::test_token_refresh ..."

    out1 = review_pr(pr, diff1, ci1)
    time.sleep(2)

    # 2번째 호출: prefix가 동일하면 cache hit가 잡혀 input 비용이 크게 내려가야 함
    diff2 = "diff --git a/app/api.py b/app/api.py\n... (another diff) ..."
    ci2 = "PASSED: unit tests; FAILED: integration/payment ..."
    out2 = review_pr(pr, diff2, ci2)
```

예상 출력(개념)
- 첫 호출: `cache_*` 관련 토큰이 “write 위주”로 발생
- 두 번째 호출(5분 내): `cache_read_input_tokens` 같은 지표가 증가하고, “일반 input tokens”는 상대적으로 줄어듦  
(정확한 필드명/구조는 모델/SDK 버전에 따라 다를 수 있어, 운영에선 usage JSON 원문을 저장해 대시보드로 파싱하는 걸 권장합니다.) ([github.com](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/prompt-caching.md?utm_source=openai))

### 2) 확장: 캐시 히트율(=비용 절감률) 계측 및 “캐시 안정성” 테스트
실무에서 가장 가치 있는 루프는 “프롬프트 변경이 캐시를 깨는지”를 CI처럼 자동 감지하는 것입니다.

```python
import hashlib

def stable_prefix_fingerprint(system_blocks) -> str:
    # 캐시 히트는 '완전 동일'이 핵심이므로,
    # 실제 요청에 들어가는 문자열을 그대로 해시해서 변경 여부를 감지한다.
    raw = json.dumps(system_blocks, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": PROJECT_RULES + "\n\n" + REVIEW_TOOLING + "\n\n" + CHECKLIST,
        "cache_control": {"type": "ephemeral"}
    }
]

print("prefix_fingerprint:", stable_prefix_fingerprint(SYSTEM_BLOCKS))
```

이 fingerprint를 배포/런타임 로그에 남기면,
- “우리가 의도치 않게 prefix를 바꾸고 있지 않은지”
- “툴 정의 순서가 바뀌어 캐시가 깨지지 않았는지”
를 **정량적으로** 추적할 수 있습니다. (실제로 Claude Code 관련 글에서도 “툴/프롬프트의 작은 변화가 캐시를 깨서 비싸지고 느려진다”를 반복해서 경고합니다.) ([code.claude.com](https://code.claude.com/docs/en/prompt-caching?utm_source=openai))

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) “변동 데이터는 무조건 suffix로 밀어라”
- 프롬프트 상단(prefix)에 시간, 토큰 카운터, 실시간 상태, 요청ID 같은 변동 문자열이 들어가면 **히트율이 0%**가 됩니다.
- 가장 안전한 규칙: **“자주 바뀌는 건 마지막 user 메시지로”**.  
Anthropic은 캐시가 `tools/system/messages`의 prefix를 기준으로 동작하며, breakpoint까지 100% 동일해야 한다고 명확히 말합니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?curius=2015&utm_source=openai))

### Best Practice 2) TTL은 “대화 패턴”으로 결정하라 (5m vs 1h)
Anthropic은 5분 TTL과 1시간 TTL을 제공하고, 1시간이 **write 비용이 더 비싸다**고 밝힙니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?curius=2015&utm_source=openai))  
즉 “오래 간직하면 무조건 이득”이 아니라,
- 재사용 간격이 대부분 수십 초~수분이면 **5m TTL이 최적**
- 세션이 길고 사용자가 자주 자리 비우는 형태면 1h가 유리할 수 있으나, **write 비용 때문에 손익분기(필요 read 횟수)** 를 먼저 계산해야 합니다. ([platform.claude.com](https://platform.claude.com/docs/en/about-claude/pricing?f80ce999_sort_date=desc&fcdaa149_sort_date=desc&gsid=273b0434-5b38-44f6-957d-3159ae3aed2e&utm_source=openai))

### Best Practice 3) 캐싱은 “비용 최적화” 이전에 “구조 최적화”다
최근 연구/사례는 단순히 “전체 컨텍스트를 다 캐시”하면,
- tool result 같은 동적 요소 때문에 miss가 잦아지거나
- 오히려 지연이 증가하는 경우가 있음을 지적합니다.  
따라서 **동적 tool 결과를 캐시 구간 밖으로 분리**하고, “고정된 규칙/툴/정책/프로젝트 컨텍스트”만 캐시하는 쪽이 일관되게 유리합니다. ([arxiv.org](https://arxiv.org/abs/2601.06007?utm_source=openai))

### 흔한 함정 1) “캐시 write 비용”을 무시한 채 히트율만 본다
Anthropic은 cache hit가 10% 수준이라 매우 매력적이지만, 그 앞단에 **write가 존재**합니다(5m=1.25×, 1h는 더 큼). ([platform.claude.com](https://platform.claude.com/docs/en/about-claude/pricing?f80ce999_sort_date=desc&fcdaa149_sort_date=desc&gsid=273b0434-5b38-44f6-957d-3159ae3aed2e&utm_source=openai))  
따라서 KPI는 보통 다음이 현실적입니다.
- `cache_read_input_tokens / total_input_tokens` (히트율)
- “캐시로 절약된 달러” = (uncached_rate - cached_rate) × cache_read_tokens - write_multiplier_penalty × cache_write_tokens

### 흔한 함정 2) 모델/설정 변경이 캐시를 “전부 초기화”한다
캐시는 모델/프롬프트 구조에 강하게 결합됩니다. 예컨대 Anthropic은 “긴 대화에서 Opus로 쌓아둔 캐시가 있는데, 중간에 더 싼 모델로 바꾸면 캐시를 다시 빌드해야 해서 오히려 더 비싸질 수 있다”는 취지의 사례를 공유합니다. ([claude.com](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything?utm_source=openai))  
실무에선 “비용 절감” 때문에 모델을 자주 스위칭하는 라우팅이 **캐시 관점에서 역효과**가 날 수 있습니다.

### 트레이드오프: 비용 vs 안정성 vs 개인정보/정책
- 일부 연구는 provider의 캐시 정책 투명성이 부족하면 **프라이버시 리스크**가 생길 수 있음을 지적합니다(캐시 공유/누수 가능성). 이런 리스크 모델이 있는 조직이라면 ZDR/데이터 통제 옵션, 저장 기간, 캐시 스코프를 반드시 확인해야 합니다. ([arxiv.org](https://arxiv.org/abs/2502.07776?utm_source=openai))
- OpenAI 쪽은 endpoint/설정에 따라 “application state retention” 같은 저장 개념이 얽힐 수 있어(특히 Responses API 계열), 컴플라이언스 요구사항이 있으면 사전에 정책 확인이 필요합니다. ([platform.openai.com](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint?utm_source=openai))

---

## 🚀 마무리

프롬프트 캐싱은 “옵션 하나 켜면 끝”이 아니라, **프롬프트를 제품처럼 설계**하는 영역입니다. 2026년 7월 기준으로 정리하면:

- OpenAI/Anthropic 모두 **prefix 재사용**을 기반으로 비용을 크게 낮출 수 있지만, 효과는 **캐시 히트율**과 **write 비용**에 의해 결정됩니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
- 실무 도입 판단 기준:
  1) 동일한 system/tool/context가 **반복 호출되는가?** (예: 에이전트, 코드리뷰, 긴 챗)  
  2) 변동 데이터(tool 결과/시간/세션 메타)를 **suffix로 분리할 수 있는가?**  
  3) usage에서 `cache_read_*`, `cache_write_*`를 **계측/대시보드화**할 수 있는가?
- 다음 학습 추천:
  - Anthropic의 prompt caching 구조(자동 vs 명시 breakpoint, prefix 범위) 문서 정독 ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?curius=2015&utm_source=openai))  
  - “Claude Code에서 캐시를 깨는 패턴” 사례(툴 정의/중간 편집/컴팩션 전략 등) ([claude.com](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything?utm_source=openai))  
  - 장기 에이전트 워크로드에서의 캐싱 전략 비교 연구(동적 tool 결과 분리) ([arxiv.org](https://arxiv.org/abs/2601.06007?utm_source=openai))

원하면, 당신의 실제 워크로드(대화 길이, 평균 prefix 토큰, 턴 간 간격, 모델, 툴 호출 비율)를 기준으로 **“5m vs 1h TTL 손익분기” 계산식 + 관측 지표 + 프롬프트 재배치 체크리스트**까지 붙여서 최적화 플랜을 같이 만들어드릴 수 있습니다.