---
title: "LLM 비용을 “반으로” 줄이는 Prompt Caching 실전 설계 (Anthropic Claude + OpenAI)"
description: "LLM을 프로덕션에 붙이면 비용이 터지는 지점은 대개 동일합니다. 매 요청마다 “거의 안 바뀌는 긴 프롬프트(prefix)”—system prompt, tool definitions, 정책/가드레일, 프로젝트 컨텍스트, 긴 대화 히스토리—를 계속 재전송/재계산하기 때문이죠."
date: 2026-08-17 01:45:55 +0900
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
LLM을 프로덕션에 붙이면 비용이 터지는 지점은 대개 동일합니다. **매 요청마다 “거의 안 바뀌는 긴 프롬프트(prefix)”**—system prompt, tool definitions, 정책/가드레일, 프로젝트 컨텍스트, 긴 대화 히스토리—를 계속 재전송/재계산하기 때문이죠. Prompt caching은 이 “안 바뀌는 prefix”를 **서버 측 KV cache 형태로 재사용**해서 **지연(latency)과 입력 토큰 비용**을 줄입니다. OpenAI는 최근에 본 입력 토큰을 재사용하면 **cached input에 50% 할인**을 적용하고, 캐시는 보통 5~10분 비활성 후 정리되며 1시간 내 제거된다고 명시합니다.[^1]

**언제 쓰면 좋은가**
- 멀티턴 chat/agent처럼 **같은 컨텍스트를 여러 번 반복**하는 워크로드
- 코드베이스/정책 문서/규칙 등 **긴 고정 컨텍스트 + 잦은 질의**
- tool calling이 많은 앱(툴 스키마가 길고 자주 반복됨)

**언제 쓰면 안 되는가(혹은 ROI가 낮은가)**
- 요청이 대부분 “원샷(one-off)”이고 재사용이 거의 없음 (cache write만 만들고 hit가 안 남)
- 프롬프트 상단(prefix)에 timestamp/uuid 등 **매번 달라지는 값이 섞여** 캐시가 사실상 깨지는 구조
- 보안/프라이버시 상 **같은 조직/프로젝트 내에서도 컨텍스트 공유를 최소화**해야 하는 경우(테넌시/키 분리 전략부터 잡아야 함)

---

## 🔧 핵심 개념
### 1) Prompt caching이 “무엇을” 캐시하나: KV cache(=prefill 결과)
LLM 호출 비용은 크게
- **prefill**: 입력(prompt)을 토큰 단위로 처리하며 attention KV를 쌓는 구간(긴 프롬프트일수록 비쌈)
- **decode**: 출력 토큰을 생성하는 구간  
으로 나뉩니다.

Prompt caching은 반복되는 prefix에 대해 prefill 결과(K/V 텐서)를 저장해두고, 다음 요청에서 **동일한 prefix가 오면 prefill을 건너뛰거나 대폭 줄여** 성능/비용을 절감합니다. 핵심은 “의미가 같음”이 아니라 **토큰/바이트 레벨로 동일한 prefix**가 필요하다는 점입니다(실무에서 캐시 히트율을 망치는 1순위).

### 2) OpenAI: “가장 긴 공통 prefix” 자동 캐싱 + 캐시 유지 시간
OpenAI는 지원 모델에서 **프롬프트 길이가 1,024 tokens 이상이면**, 과거에 계산된 프롬프트의 **가장 긴 prefix**를 캐시로 재사용하며, 이 prefix는 1,024부터 시작해 **128-token 단위로 증가**한다고 설명합니다.[^1]  
또한 응답 `usage`에 `cached_tokens`가 포함되어 **캐시로 할인된 토큰이 얼마나 되었는지** 모니터링할 수 있습니다.[^1]

정리하면 OpenAI는:
- 개발자가 별도 마킹을 하지 않아도 “공통 prefix”가 반복되면 자동으로 혜택을 줌
- 대신 **prefix 안정성(항상 같은 앞부분)**을 설계로 확보해야 히트가 난다
- 캐시는 보통 5~10분 비활성 후 정리, 1시간 내 제거[^1]

### 3) Anthropic: cache_control로 “여기까지 캐시해”를 명시 + TTL/비용 모델
Anthropic Claude는 messages의 **content block**(system/tool/messages 등)에 `cache_control: { type: "ephemeral" }`을 달아 **캐시 breakpoint**를 명시합니다. TTL은 기본 5분이며, 필요 시 `ttl: "1h"`로 1시간 캐시도 가능(추가 비용)합니다.[^2]  
또한 Anthropic은 **cache write/ read 가격을 분리**해 공개합니다. 예를 들어(표준 티어 기준) base input 대비:
- 5m cache write: **1.25×**
- 1h cache write: **2×**
- cache hits & refreshes(read): **0.1×** 수준(문서/가이드에서 “~0.1×”로 설명)[^3]

이 구조 때문에 Anthropic은 “캐시를 쓰면 무조건 싸다”가 아니라,
- **write(저장) 비용을 먼저 내고**
- 이후 요청에서 read(히트)로 회수  
하는 **break-even 계산**이 중요합니다. GitHub 가이드에선 5분 TTL은 보통 2회 호출부터 손익분기, 1시간 TTL은 3회 이상 재사용이 필요하다는 식으로 설명합니다.[^3]

### 4) 다른 접근(요약/RAG/압축)과의 차이
- RAG/압축: “프롬프트를 짧게” 만들어 prefill 자체를 줄임
- Prompt caching: “긴 프롬프트를 그대로 보내되” 반복되는 prefix의 prefill을 재사용

실무에선 둘 다 씁니다. **캐싱은 히트율이 떨어지면 바로 무력화**되므로, 캐싱만 믿고 프롬프트가 계속 비대해지면 비용이 다시 폭증합니다.

---

## 💻 실전 코드
아래는 “SaaS 코드리뷰/정책 검증 agent” 같은 현실적 시나리오입니다.

- 고정 prefix: system 규칙 + tool schema + repo 정책(수천 토큰)
- 매 요청 변화: PR diff 요약, 질문, 최근 tool 결과 일부

### 0) 설치/환경
```bash
pip install openai anthropic python-dotenv
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
```

### 1) Anthropic Claude: cache_control로 breakpoint 2개(시스템/정책, 툴 스키마)
```python
# anthropic_prompt_caching_demo.py
import os, json, time
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_RULES = """You are a senior code reviewer.
Follow our security policy and output a JSON report with:
- risk_level
- findings[]
- suggested_patch (unified diff if needed)
"""

REPO_POLICY = open("repo_policy.md", "r", encoding="utf-8").read()  # 예: 보안/아키텍처 규칙 3~10k tokens

TOOLS = [
  {
    "name": "get_file",
    "description": "Fetch file content by path",
    "input_schema": {
      "type": "object",
      "properties": {"path": {"type": "string"}},
      "required": ["path"]
    }
  },
  {
    "name": "search_repo",
    "description": "Search codebase for a pattern",
    "input_schema": {
      "type": "object",
      "properties": {"query": {"type": "string"}},
      "required": ["query"]
    }
  }
]

def review_pr(diff_text: str, question: str, ttl: str = "5m"):
    # 핵심: "변하지 않는 덩어리"에 cache_control을 붙이고,
    # "자주 변하는 덩어리(diff/question)"는 캐시 뒤에 둔다.
    # Anthropic은 ttl을 1h로 줄 수 있음.[^2]
    resp = client.messages.create(
        model="claude-sonnet-4.6",  # 예시
        max_tokens=800,
        system=[
            {
                "type": "text",
                "text": SYSTEM_RULES,
                "cache_control": {"type": "ephemeral", "ttl": ttl},
            },
            {
                "type": "text",
                "text": REPO_POLICY,
                "cache_control": {"type": "ephemeral", "ttl": ttl},
            }
        ],
        tools=TOOLS,  # 툴 정의가 길면 이것도 캐싱 breakpoint 고려(가이드상 블록에 붙일 수 있음)[^3]
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "PR diff:\n" + diff_text},
                    {"type": "text", "text": "Question:\n" + question},
                ],
            }
        ],
    )

    # 콘솔에서 캐시 효과 확인(필드명은 SDK/플랫폼에 따라 다를 수 있음)
    usage = getattr(resp, "usage", None)
    print("usage:", usage)

    print(resp.content[0].text[:500])
    return resp

if __name__ == "__main__":
    diff = open("sample_pr.diff", "r", encoding="utf-8").read()

    # 1차: cache write(비용이 더 들 수 있음) + 이후 hit로 회수
    review_pr(diff, "Any auth bypass risk? Provide patch if needed.", ttl="5m")
    time.sleep(2)

    # 2차: 같은 system/policy가 동일하면 cache hit 기대
    review_pr(diff, "Check for SQL injection and logging of secrets.", ttl="5m")
```

**예상 관찰**
- 첫 호출: cache write가 발생(Anthropic은 write가 base input보다 비쌈)[^3]
- 두 번째 호출(5분 내): system/policy prefix가 동일하면 cache read로 전환되어, 고정 컨텍스트 비용이 급감

### 2) OpenAI: “prefix 안정성”으로 자동 히트율 만들기 + cached_tokens 관측
OpenAI는 공통 prefix를 자동 캐싱하고, `usage.cached_tokens`로 관측합니다.[^1]

실전 포인트는 “매번 바뀌는 값은 절대 앞에 두지 말 것”입니다. (예: request_id, timestamp, user_id를 system에 넣으면 캐시가 깨짐)

```python
# openai_prompt_caching_demo.py
import os, json, time
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

STATIC_SYSTEM = """You are a compliance-aware code review agent.
Always produce JSON with keys: risk_level, findings, recommended_actions.
Do not include any user identifiers in output.
"""

STATIC_TOOLING = """Available tools:
- get_file(path): returns file content
- search_repo(query): returns matches
Tool calling policy: use tools only when necessary.
"""

# "고정 prefix"를 앞에, "동적 내용"을 뒤에.
def ask(diff_text: str, question: str):
    prompt = (
        STATIC_SYSTEM
        + "\n\n"
        + STATIC_TOOLING
        + "\n\n"
        + "Repository policy:\n"
        + open("repo_policy.md", "r", encoding="utf-8").read()
        + "\n\n"
        + "PR diff:\n"
        + diff_text
        + "\n\n"
        + "Question:\n"
        + question
    )

    r = client.responses.create(
        model="gpt-4o-2024-08-06",
        input=prompt,
        max_output_tokens=800,
    )

    # docs에 따르면 cached_tokens로 모니터링 가능[^1]
    print("usage:", r.usage)
    print(r.output_text[:500])
    return r

if __name__ == "__main__":
    diff = open("sample_pr.diff", "r", encoding="utf-8").read()

    ask(diff, "List top 5 security risks.")
    time.sleep(2)
    ask(diff, "Focus on auth/session risks and propose patch.")
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “캐시 가능한 prefix”를 설계로 분리하라
- **맨 앞(prefix)**: system rules / tool schema / 정책 문서 / 장기 컨텍스트
- **맨 뒤(suffix)**: 유저 질문, 최신 diff, runtime state, tool 결과

Anthropic은 breakpoint를 블록 단위로 찍을 수 있고(최대 4개)[^3], OpenAI는 공통 prefix 자동 매칭이므로 **prefix 안정성 자체가 제품 설계**입니다.

### Best Practice 2) 캐시 히트율은 “토큰 기준”으로 봐라
요청 수 기준 hit rate만 보면 착시가 생깁니다. 정말 중요한 건:
- `cached_tokens / prompt_tokens` (OpenAI)[^1]
- “고정 prefix 토큰 중 몇 %가 read로 빠졌는가”(Anthropic도 usage 계측 가능)

운영 지표로는:
- cache-read 토큰 비중
- p95 latency(캐시 히트 시 prefill이 줄어드는지)
- “캐시 무효화 이벤트”(system prompt 변경 배포, tool schema 변경 배포) 시점의 비용 스파이크

### Best Practice 3) Anthropic은 break-even을 계산해서 TTL을 고르라
Anthropic은 5m/1h TTL이 **무료가 아니라 write premium**이 있습니다.[^3]  
- 트래픽이 “짧은 버스트”면 5m이 유리(적은 write premium로 빠른 회수)
- 세션 간 간격이 길면 1h로 hit를 살릴 수 있지만, **재사용 횟수가 적으면 손해**일 수 있음

### 흔한 함정/안티패턴
- **system prompt에 datetime/uuid/request_id**를 넣기 → 캐시가 매번 깨짐(Anthropic 가이드에서도 대표적인 silent invalidator로 경고)[^3]
- tool schema를 사용자마다 다르게 생성(순서/직렬화 불안정 포함) → prefix 불일치
- “정책 문서”를 자주 바꾸는데 버저닝 없이 바로 덮어쓰기 → 캐시 무효화로 비용 급등 + 회귀 분석 어려움  
  (해결: 정책을 버전 문자열로 분리하고, 변경 주기를 운영 이벤트로 취급)

### 비용/성능/안정성 트레이드오프
- 캐시는 비용을 줄이지만, **프롬프트 구조를 고정**시키는 압력이 생깁니다(자잘한 문구 수정도 캐시 미스 유발).
- 너무 긴 prefix를 캐시로만 커버하려 하면, 캐시가 식는 순간(세션 공백/배포/트래픽 패턴 변화) **비용이 “원복”이 아니라 “폭증”**처럼 체감될 수 있습니다.
- 그래서 결론은: **캐싱 + 프롬프트 슬리밍(불필요 규칙 제거) + RAG로 “진짜 필요한 것만”**이 함께 가야 합니다.

---

## 🚀 마무리
Prompt caching은 2026년 현재 “옵션 최적화”가 아니라, **멀티턴/에이전트형 제품에서 비용을 통제하기 위한 필수 설계 요소**에 가깝습니다. OpenAI는 1,024+ 토큰에서 공통 prefix를 자동 캐싱하고 `cached_tokens`로 관측 가능하며, 캐시는 보통 5~10분 비활성 후 정리되고 1시간 내 제거됩니다.[^1] Anthropic은 `cache_control`로 breakpoint/TTL(5m, 1h)을 명시하고, cache write/read가 분리된 가격 모델이어서 **히트율과 재사용 횟수 기반 ROI 계산**이 중요합니다.[^2]

**도입 판단 기준(실무 체크리스트)**
- 내 요청의 입력 토큰 중 “고정 prefix”가 50% 이상인가?
- 같은 prefix가 **5분(또는 1시간) 내 2~3번 이상** 재사용되는가?
- system/tooling/policy를 **결정론적으로(deterministic)** 만들 수 있는가(직렬화/정렬/버전 관리)?
- 배포/정책 변경이 잦다면, 캐시 미스 비용을 감당할 관측/알림이 준비됐는가?

**다음 학습 추천**
- OpenAI Prompt Caching 동작(1,024 + 128 increments, cached_tokens 모니터링)[^1]
- Anthropic Prompt caching 문서(5m/1h TTL, cache_control 사용 규칙)[^2]
- Anthropic의 실전 invalidator/모델별 최소 캐시 길이/경제성 정리(오픈 가이드)[^3]

[^1]: <https://openai.com/index/api-prompt-caching/>
[^2]: <https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching?trk=psm_a134p000006gBL6AAM>
[^3]: <https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/prompt-caching.md>
