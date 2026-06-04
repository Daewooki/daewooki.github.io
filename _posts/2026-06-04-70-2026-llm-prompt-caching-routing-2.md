---
title: "토큰을 70% 줄이는 2026년식 LLM 비용 최적화: **Prompt Caching + 모델 Routing** 실전 설계"
date: 2026-06-04 05:01:25 +0900
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
LLM API 비용이 폭증하는 패턴은 꽤 정형적입니다.

- **(1) 입력 토큰이 계속 중복**된다: 긴 system prompt, tool schema, 정책/규칙, 코드베이스 요약, “항상 붙는” 컨텍스트
- **(2) 모든 요청을 비싼 모델에 던진다**: 분류/정규화/간단 QA도 “그냥 제일 좋은 모델”로 처리
- **(3) 대화가 길어질수록 컨텍스트가 비대**해져서, “작은 기능 추가”가 “전체 비용의 2배”가 된다

2026년 6월 기준, 비용 최적화의 핵심은 더 이상 “프롬프트 짧게 써요” 수준이 아니라 **(A) Prompt Caching으로 중복 입력을 시스템적으로 제거**하고, **(B) Router로 “난이도에 따라 모델을 갈아타는” 정책을 코드로 고정**하는 것입니다. OpenAI는 cached input 가격이 일반 input 대비 크게 할인되고(예: GPT 계열에서 cached input 단가가 10배 저렴한 구간 존재) ([openai.com](https://openai.com/api/pricing/?utm_source=openai)), Anthropic은 캐시 “write/read”가 별도 과금 구조라 최적화 방식이 다릅니다. ([platform.claude.com](https://platform.claude.com/docs/en/about-claude/pricing?hsLang=en&utm_source=openai))

### 언제 쓰면 좋은가
- 트래픽이 있고(반복 호출), system/tool/policy가 길며, 요청의 60% 이상이 “중간/저난이도”인 서비스
- multi-agent/툴콜이 많아 turn 수가 늘어나는 워크로드(캐시가 특히 잘 먹힘) ([arxiv.org](https://arxiv.org/abs/2601.06007?utm_source=openai))

### 언제 쓰면 안 되는가
- 요청이 모두 **희소**(재사용 거의 없음)하거나, 매번 system prompt가 크게 달라 캐시 prefix가 깨지는 경우
- “무조건 최고 품질”이 핵심이라 routing으로 품질 변동을 감당 못 하는 경우(법률 최종본, 의료 최종판 등)

---

## 🔧 핵심 개념
### 1) 비용의 본질: “토큰”이 아니라 “prefill(입력 처리) + decode(출력 생성)”
대부분의 과금은 input/output token 기반이지만, 실제 비용 최적화는 **입력(prefill) 중복 제거**가 지배합니다. Prompt Caching은 “같은 prefix”의 KV cache를 재사용해 prefill을 줄이는 방식입니다(구현은 다르지만 결과는 동일: 입력 토큰 비용과 TTFT 감소). OpenAI는 **1024 tokens 이상**에서 캐시가 의미 있게 적용되고, **exact prefix match**가 핵심입니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

### 2) Prompt Caching의 내부 작동 흐름(Provider별 차이 포함)
#### OpenAI (자동 캐시 + cached_tokens 관찰)
- 요청이 들어오면 **prefix hash 기반으로 서버 라우팅** → 해당 머신의 캐시에서 prefix lookup ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))  
- 캐시 히트면 `usage.prompt_tokens_details.cached_tokens`가 증가하고, 해당 부분이 **cached input 단가**로 청구됩니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))
- 추가로 `prompt_cache_key`, `prompt_cache_retention(in_memory/24h)`로 히트율을 조절할 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))  
  - 실무적으로는 “**요청 템플릿 단위로 cache_key를 고정**”하면 라우팅 분산(overflow)로 인한 히트율 하락을 줄이기 좋습니다(문서상 대략 15 req/min 이상이면 overflow 가능). ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

#### Anthropic (명시적 cache_control + write/read 과금)
- `cache_control: { type: "ephemeral", ttl: "5m"|"1h" }`로 “어디까지 캐시할지” 구간을 정의 ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?ss_ad_code=usecase3&utm_source=openai))  
- 응답 `usage`에 `cache_creation_input_tokens`, `cache_read_input_tokens`가 별도로 찍혀서 “진짜로 캐시가 됐는지” 검증 가능 ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?ss_ad_code=usecase3&utm_source=openai))
- 가격표도 **Base input / cache writes / cache hits**가 분리되어 있어, “무조건 캐시”가 아니라 “write 비용 대비 read 반복 수”를 따져야 합니다. ([platform.claude.com](https://platform.claude.com/docs/en/about-claude/pricing?hsLang=en&utm_source=openai))

#### 연구/실측 포인트
장기 에이전트 워크로드에서 caching 전략(시스템만 캐시 vs 툴 결과 제외 등)에 따라 **45~80% 비용 절감**이 관찰됩니다. ([arxiv.org](https://arxiv.org/abs/2601.06007?utm_source=openai))  
즉, “전체 컨텍스트를 다 캐시”보다 **동적 툴 결과/로그를 뒤로 몰아 prefix를 안정화**하는 쪽이 이득인 경우가 많습니다. ([arxiv.org](https://arxiv.org/abs/2601.06007?utm_source=openai))

### 3) Routing(모델 라우팅)의 핵심: “싼 모델을 기본값으로, 비싼 모델은 예외로”
2026년엔 소형 모델 성능이 올라서, 많은 요청이 mini급으로도 충분합니다. OpenAI 가격표만 봐도 mini/nano가 매우 저렴하고(입력/출력 모두), cached input 할인까지 결합하면 “기본 운영 단가”를 크게 내릴 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/pricing/?utm_source=openai))  
Routing은 결국 아래 3가지 신호를 조합합니다.

- **Task type**: 분류/추출/요약/생성/코딩/리서치
- **Risk**: 틀리면 큰일인가(계약/결제/정책), 아니면 “추천/초안”인가
- **Complexity**: 입력 길이, 요구되는 추론 깊이(다단계), tool 필요 여부

---

## 💻 실전 코드
아래 예시는 “실제 SaaS”에서 흔한 시나리오로 구성합니다.

- B2B 제품의 **Support 티켓**이 들어옴
- 1) PII 제거/정규화(저비용) → 2) 티켓 분류/라우팅(저비용) → 3) 답변 초안 생성(난이도에 따라 모델 선택)  
- 공통 system/tool 스키마는 **Prompt Caching이 먹도록 prefix에 고정**
- 그리고 요청별 비용을 추적해 **Router 정책을 데이터로 튜닝**할 수 있게 설계

### 0) 의존성/실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install openai tiktoken pydantic python-dotenv
export OPENAI_API_KEY="..."
python app.py
```

### 1) Router + 캐시 친화 프롬프트 템플릿(app.py)
```python
import os
import json
import time
from dataclasses import dataclass
from typing import Literal, Optional

from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# 2026.06 기준: OpenAI Prompt Caching은 exact prefix match가 핵심.
# 따라서 "절대 바뀌지 않는" system/tool 정의는 앞에 고정하고,
# 티켓 본문/유저 메타데이터 같은 변동분은 맨 뒤에 붙인다.  ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

STATIC_SYSTEM = """You are a senior support engineer.
Follow the policy strictly.
- Never request secrets.
- If unsure, ask one clarifying question.
Output must be JSON with keys: category, priority, draft_reply, needs_human.

Company policy (stable):
1) Refund: ... (long)
2) Security: ... (long)
3) Billing: ... (long)
(Imagine this is 2k~10k tokens and stable across requests)
"""

# 현실에서 routing은 "서비스 요구(품질/리스크)"를 기준으로 결정해야 한다.
# 여기서는 간단하지만 실무적인 휴리스틱을 둔다.
@dataclass
class RouteDecision:
    model: str
    reason: str

def route_ticket(ticket_text: str, has_payment_issue: bool, is_enterprise: bool) -> RouteDecision:
    t = ticket_text.lower()
    # 고위험(결제/환불/보안) 또는 엔터프라이즈는 상향
    if any(k in t for k in ["refund", "chargeback", "invoice", "security", "breach"]) or has_payment_issue:
        return RouteDecision(model="gpt-5.4", reason="high_risk_payment_or_security")
    if is_enterprise and len(ticket_text) > 2000:
        return RouteDecision(model="gpt-5.4", reason="enterprise_long_context")
    # 기본은 mini로: 대량 트래픽에서 비용/지연 최적
    return RouteDecision(model="gpt-5.4 mini", reason="default_low_cost")

def call_llm(model: str, cache_key: str, ticket_id: str, ticket_text: str) -> dict:
    # OpenAI는 prompt_cache_key로 라우팅/캐시 히트율을 개선할 수 있다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))
    # cache_key는 "템플릿/정책 버전" 단위로 고정하는 게 실무적으로 안전.
    resp = client.responses.create(
        model=model,
        prompt_cache_key=cache_key,
        prompt_cache_retention="24h",  # 가능한 모델에서 24h 유지 ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))
        input=[
            {"role": "system", "content": STATIC_SYSTEM},
            {"role": "user", "content": f"TICKET_ID={ticket_id}\n\nTICKET_TEXT:\n{ticket_text}\n"}
        ],
        # 비용 폭주 방지: 출력 상한은 필수(특히 고가 모델) 
        max_output_tokens=500,
        # JSON 강제는 파싱 비용(재시도) 절감에 직접적
        response_format={"type": "json_object"},
    )

    usage = resp.usage
    # cached_tokens는 비용 최적화의 KPI: 0이면 프롬프트 구조가 깨진 것 ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))
    cached = 0
    if usage and usage.prompt_tokens_details:
        cached = usage.prompt_tokens_details.cached_tokens or 0

    return {
        "model": model,
        "output_json": json.loads(resp.output_text),
        "usage": {
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "cached_prompt_tokens": cached,
            "output_tokens": usage.completion_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
        }
    }

def main():
    tickets = [
        {
            "ticket_id": "T-10021",
            "text": "We were charged twice on the invoice. Need refund ASAP.",
            "has_payment_issue": True,
            "is_enterprise": True
        },
        {
            "ticket_id": "T-10022",
            "text": "How do I change notification settings for my workspace?",
            "has_payment_issue": False,
            "is_enterprise": False
        },
    ]

    cache_key = "support-policy-v7"  # 정책/도구 정의가 바뀌면 키도 바꿔 캐시 오염 방지

    for t in tickets:
        decision = route_ticket(t["text"], t["has_payment_issue"], t["is_enterprise"])
        r = call_llm(
            model=decision.model,
            cache_key=cache_key,
            ticket_id=t["ticket_id"],
            ticket_text=t["text"]
        )
        print("\n---")
        print("route:", decision)
        print("usage:", r["usage"])
        print("result:", r["output_json"])

if __name__ == "__main__":
    main()
```

### 예상 출력(예시)
- 첫 요청은 cold cache라 `cached_prompt_tokens=0`일 수 있고,
- 동일 템플릿/정책으로 반복 호출하면 cached가 크게 늘어나는 게 정상입니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “캐시가 먹는 프롬프트”는 **prefix 안정성**이 90%
- static(정책/역할/툴 스키마/예시) → 앞
- dynamic(티켓 본문/유저 메타/툴 결과/로그) → 뒤  
이건 OpenAI가 “exact prefix match”를 요구하기 때문에 구조적으로 강제됩니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))  
연구에서도 “동적 툴 결과를 제외/후방 배치” 같은 전략이 캐시 효율을 안정화한다고 보고합니다. ([arxiv.org](https://arxiv.org/abs/2601.06007?utm_source=openai))

### Best Practice 2) Router는 “모델 선택”이 아니라 “실패 시 승격(escalation)”까지 포함
실무에서 가장 안전한 패턴은:
1) mini로 시도
2) 품질 신호(스키마 불일치, 낮은 confidence, 금칙 위반 위험, 사람이 읽어도 애매함) 감지
3) 상위 모델로 **재시도(승격)**

이렇게 하면 평균 비용은 mini에 맞추고, tail-risk만 비싼 모델로 커버합니다. (단, 재시도는 latency 증가이므로 비동기/백그라운드 적용 고려)

### Best Practice 3) 캐시/라우팅 KPI를 “요청 로그”로 남겨 FinOps 가능하게
- `cached_prompt_tokens / prompt_tokens` 비율(캐시 적중률)
- task별 평균 total_tokens
- 모델별 승격률, 재시도율
- 기능/테넌트/엔드포인트 태깅(청구 분해)

특히 “청구가 문서 계산과 안 맞는다” 류의 이슈는 어느 벤더든 반복됩니다. 실제 청구 기반으로 내부 대시보드를 만드는 쪽이 장기적으로 안전합니다(커뮤니티에서도 같은 조언이 반복). ([reddit.com](https://www.reddit.com/r/googlecloud/comments/1r0tyvn/is_google_intentionally_misleading_on_gemini_3/?utm_source=openai))

### 흔한 함정 1) 캐시가 “자동으로” 될 거라고 믿고 검증 안 함
- OpenAI는 `cached_tokens`가 usage에 찍힙니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))  
- Anthropic은 cache read/creation 토큰이 별도 필드로 나옵니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?ss_ad_code=usecase3&utm_source=openai))  
이걸 **프로덕션 로그/메트릭에 필수로** 넣지 않으면, 캐시가 깨져도 몇 주간 모른 채로 돈을 태웁니다.

### 흔한 함정 2) Gateway/OpenRouter류 라우팅에서 캐시 격리/보안 이슈를 무시
최근 연구는 “게이트웨이 아키텍처에서 캐시 격리 보장이 흔들릴 수 있는지”를 문제로 다룹니다. ([arxiv.org](https://arxiv.org/abs/2605.30613?utm_source=openai))  
즉, 비용만 보고 무작정 외부 라우터를 붙이기 전에:
- 캐시가 계정/조직 단위로 격리되는지
- timing/metadata leakage 가능성이 있는지
- 규정(PII/고객데이터) 관점에서 허용되는지  
를 체크해야 합니다.

### 트레이드오프 정리
- **비용↓**: caching + mini-first routing
- **품질/일관성↓ 가능**: 모델이 바뀌면 스타일/정확도가 달라짐 → 승격/검증 레이어 필요
- **지연↑ 가능**: 승격 재시도, 또는 캐시 miss가 잦은 구조
- **복잡도↑**: 하지만 한 번 프레임을 잡아두면 “조직 차원의 비용 방어선”이 됩니다

---

## 🚀 마무리
2026년 6월의 LLM 비용 최적화는 결론적으로 이 2줄입니다.

1) **Prompt Caching이 먹는 프롬프트 구조**로 바꿔라(exact prefix match, static 앞/ dynamic 뒤). ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))  
2) **mini-first + 승격형 routing**으로 “평균 요청” 비용을 강제로 낮춰라(고급 모델은 예외 처리). ([platform.openai.com](https://platform.openai.com/docs/pricing/?utm_source=openai))  

도입 판단 기준(실무 체크리스트):
- system/tool/policy가 1k tokens 이상이며 반복 호출되는가? (Yes면 caching ROI 큼) ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))  
- 요청의 절반 이상이 저/중난이도인가? (Yes면 routing ROI 큼)
- 캐시 적중률/승격률/토큰을 “측정 가능한 형태”로 로그에 남길 수 있는가? (No면 먼저 관측부터)

다음 학습 추천:
- 장기 에이전트에서 caching 전략 비교(툴 결과 제외, 시스템만 캐시 등) 사례: “Don’t Break the Cache” ([arxiv.org](https://arxiv.org/abs/2601.06007?utm_source=openai))  
- 게이트웨이 라우팅/캐시 격리 보안 관점: “CacheProbe” ([arxiv.org](https://arxiv.org/abs/2605.30613?utm_source=openai))  

원하시면, 당신의 서비스 형태(요청 유형/평균 입력 길이/툴 사용 여부/동시성/품질 요구)를 기준으로 **routing 정책 테이블(규칙 기반→통계 기반→bandit)**까지 확장한 버전으로 설계안을 같이 잡아드릴게요.