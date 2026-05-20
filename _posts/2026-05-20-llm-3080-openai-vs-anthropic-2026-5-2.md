---
title: "프롬프트 캐싱으로 LLM 비용 30~80% 줄이기: OpenAI vs Anthropic (2026년 5월 실전 최적화)"
date: 2026-05-20 04:16:21 +0900
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

LLM을 프로덕션에 붙이면 비용은 보통 “output”보다 “입력 프롬프트의 반복”에서 먼저 터집니다. 예를 들어:

- 매 요청마다 긴 system prompt(정책/포맷/가드레일/툴 사용 규칙)
- 동일한 도메인 지식(FAQ, 스키마, 코드베이스 요약, 에이전트 운영 규칙)
- RAG를 매번 통째로 다시 붙이는 패턴

이때 **prompt caching**은 “동일한 prefix를 다시 계산하지 않게” 만들어 **입력 토큰 비용과 latency를 같이** 줄입니다. OpenAI는 자동 캐싱/할인 중심, Anthropic은 “내가 캐시할 지점을 명시”하는 설계라 최적화 포인트가 다릅니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

언제 쓰면 좋나
- **긴 공통 prefix가 반복되는 워크로드**: 멀티턴 챗, 코드 리뷰/리라이트, 에이전트(플래너/툴 규칙 고정), 대규모 분류/추출 파이프라인
- **요청이 짧아도** “앞부분이 길고 고정”이면 유리 (단, 벤더별 최소 토큰/조건 확인 필요)

언제 쓰면 안 되나(또는 효과가 작나)
- 매 요청마다 prompt 구조/순서가 크게 달라져 **prefix가 안정적으로 동일하지 않은 경우**
- 캐시 TTL/라우팅 특성 때문에 **재현 가능한 비용 절감**이 핵심인데, 이를 캐시 “운”에 맡기면 안 되는 경우(이 경우엔 앱 레벨에서 컨텍스트를 더 잘 쪼개야 함) ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))

---

## 🔧 핵심 개념

### 1) Prompt caching이 “어떤 비용”을 줄이나
핵심은 **입력(prompt) 토큰의 일부가 cache hit**될 때, 그 토큰들을 “새로 처리”하지 않는다는 점입니다. 그래서:
- 입력 토큰 비용이 내려가고
- time-to-first-token이 줄어 latency가 개선됩니다(OpenAI는 가이드에서 큰 폭의 latency/cost 절감을 언급). ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

다만 output 토큰은 그대로입니다. “응답이 길어서 돈이 많이 든다”면 caching보다 **요약/툴 결과 압축/출력 제한**이 먼저입니다.

### 2) OpenAI: 자동 라우팅 + prefix hash + (선택) prompt_cache_key
OpenAI는 “최근 처리한 동일 prefix”를 다시 요청하면 **서버가 자동으로 캐시 히트를 적용**합니다. 개발자가 별도 저장/조회 API를 호출하는 형태가 아니라, **라우팅과 머신 로컬 캐시**에 가깝습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

구조/흐름(실무적으로 중요한 부분만):
1. 요청이 들어오면 **초기 prefix를 hash**해서 특정 머신(또는 풀)로 라우팅
2. 그 머신에 해당 prefix에 대한 cache가 있으면 hit → cached_tokens로 잡힘
3. (옵션) `prompt_cache_key`를 주면 “같은 prefix라도” 라우팅 키에 영향을 줘 히트율을 끌어올릴 수 있음
4. 단, 같은 prefix+key 조합으로 트래픽이 너무 몰리면(문서에 “약 15 req/min” 수준의 overflow 언급) 캐시 효과가 떨어질 수 있음 ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

**중요 포인트:** OpenAI는 “prefix exact match”가 핵심이라, **고정 텍스트/이미지/툴 정의를 앞에** 몰아두고, 사용자 입력/동적 RAG는 뒤로 빼야 합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

### 3) Anthropic: cache_control로 “캐시 브레이크포인트”를 직접 찍는다
Anthropic은 Messages API에서 content block에 `cache_control: { type: "ephemeral" }` 같은 방식으로 **“여기까지를 캐시해라”**를 명시합니다. 그리고 이후 동일 prefix가 오면 캐시를 읽습니다. 기본 TTL은 5분(문서에 1-hour 옵션도 언급)입니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?utm_source=openai))

구조/흐름:
1. 요청 프롬프트를 모델에 “읽히는” 과정에서
2. cache_control이 붙은 지점까지 내부 상태를 저장(= write)
3. 이후 요청이 동일 prefix면 해당 저장 상태를 재사용(= read)

**OpenAI와의 가장 큰 차이**
- OpenAI: “자동 적용(조건 충족 시), 라우팅 기반”
- Anthropic: “내가 캐시 구간을 설계해야 하고, write/read 개념이 더 명시적”

이 차이 때문에 Anthropic은 “첫 호출로 cache seed(write) → 이후 병렬 fan-out(read)” 패턴이 특히 강력하고, 반대로 TTL이 짧으면 **rewarm(write 재발생)** 비용이 무시 못 할 수 있습니다(커뮤니티에서도 write/read 비중이 비슷해지는 사례가 언급됨). ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?utm_source=openai))

---

## 💻 실전 코드

아래는 “긴 고정 정책 + 도메인 스키마 + 테넌트별 규칙”이 반복되는 **B2B 티켓 분류/라우팅 서비스** 예시입니다.

목표:
- 공통 prefix(정책/스키마/예시)를 최대한 캐시에 태우고
- 동적 부분(티켓 본문, 최신 고객 데이터)은 뒤로 분리
- 실행 후 **cache hit 지표(cached_tokens / cache read/write tokens)**를 로깅해서 히트율을 튜닝

### 0) 의존성/환경변수

```bash
# Python 3.11+
pip install openai anthropic python-dotenv

# .env
# OPENAI_API_KEY=...
# ANTHROPIC_API_KEY=...
```

### 1) OpenAI: prefix 고정 + prompt_cache_key로 테넌트 단위 히트율 끌어올리기

```python
import os, json, time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

STATIC_PREFIX = """You are a senior support triage agent.
Return JSON only with keys: category, priority, routing_team, rationale.

Company policy:
- P0: security incident, data leak, payment outage
- P1: production outage, major regression
- P2: degraded performance, workaround exists
- P3: questions, minor bugs

Schema:
category: one of ["billing","security","bug","feature","account","performance","other"]
priority: one of ["P0","P1","P2","P3"]
routing_team: one of ["SRE","Security","Billing","CoreApp","Growth","Support"]
rationale: short, <= 2 sentences
Examples:
Input: "We were charged twice..."
Output: {"category":"billing","priority":"P2","routing_team":"Billing","rationale":"..."}
"""

def classify_ticket_openai(tenant_id: str, ticket_text: str):
    # 핵심: 고정 prefix는 최대한 앞에, 변동은 뒤에.
    # prompt_cache_key: 테넌트별로 안정적이면 히트율이 상승(라우팅에 영향을 줌)
    resp = client.responses.create(
        model="gpt-4o-mini",
        prompt_cache_key=f"triage::{tenant_id}",
        input=[
            {"role": "system", "content": STATIC_PREFIX},
            {"role": "user", "content": f"Ticket:\n{ticket_text}\n\nReturn JSON:"}
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    usage = resp.usage
    # OpenAI는 응답 usage에 cached_tokens가 포함됨(문서: prompt_tokens_details.cached_tokens)
    cached = None
    try:
        cached = usage["prompt_tokens_details"]["cached_tokens"]
    except Exception:
        pass

    out = resp.output_text
    return out, {"prompt_tokens": usage.get("prompt_tokens"), "cached_tokens": cached}

if __name__ == "__main__":
    ticket = "Customer reports checkout failing with 500s for 12 minutes. Revenue impact."
    for i in range(3):
        out, meta = classify_ticket_openai("acme-co", ticket)
        print("result:", out)
        print("usage:", meta)
        time.sleep(1)
```

예상 관찰 포인트
- 1회차: `cached_tokens`가 0(또는 매우 낮음)
- 2~3회차: prefix가 같으면 `cached_tokens`가 증가
- prefix가 1024 tokens 미만이면 캐시 이점이 제한적일 수 있음(최소 길이 조건이 문서에 명시). ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

### 2) Anthropic: cache_control로 “캐시 시드 → 병렬 처리” 패턴 만들기

```python
import os, json, time
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

STATIC_BLOCK = """You are a senior support triage agent.
Return JSON only with keys: category, priority, routing_team, rationale.

Company policy:
- P0: security incident, data leak, payment outage
- P1: production outage, major regression
- P2: degraded performance, workaround exists
- P3: questions, minor bugs

Schema:
category: one of ["billing","security","bug","feature","account","performance","other"]
priority: one of ["P0","P1","P2","P3"]
routing_team: one of ["SRE","Security","Billing","CoreApp","Growth","Support"]
rationale: short, <= 2 sentences
"""

def classify_ticket_claude(ticket_text: str):
    # Anthropic은 캐시할 구간에 cache_control을 붙여 “브레이크포인트”를 만든다.
    # Exact match 요구(텍스트/이미지 포함) → 이 블록은 절대 바꾸지 말 것.
    msg = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=200,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": STATIC_BLOCK, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": f"Ticket:\n{ticket_text}\n\nReturn JSON:"},
                ],
            }
        ],
    )

    # 응답에 cache 관련 토큰 카운트가 포함되는 형태(문서/예제에 존재)
    usage = getattr(msg, "usage", None)
    return msg.content[0].text, usage

if __name__ == "__main__":
    ticket = "We suspect an API key leak; unusual traffic and user reports of unauthorized actions."
    for i in range(3):
        out, usage = classify_ticket_claude(ticket)
        print("result:", out)
        print("usage:", usage)
        time.sleep(1)
```

예상 관찰 포인트
- 1회차: cache write(시드)
- 2~3회차: cache read(히트)
- TTL(기본 5분)을 넘기면 다시 write가 발생할 수 있어, 트래픽 패턴이 “간헐적”이면 write 비용이 누적될 수 있음 ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?utm_source=openai))

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) “캐시 가능한 prefix”를 제품 구조로 고정해라
히트율은 프롬프트 엔지니어링이 아니라 **소프트웨어 설계** 이슈입니다.

- system prompt/정책/스키마/툴 목록/예시는 **버전 문자열**로 고정
- 동적 데이터(유저 프로필, RAG 결과, 툴 결과)는 **항상 뒤로**
- JSON field 순서, 공백, 줄바꿈까지도 “동일 prefix” 관점에선 리스크(특히 Anthropic은 exact match를 강하게 요구) ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

### Best Practice 2) “캐시 히트율”을 토큰 단위로 측정하라
요청 단위 hit/miss만 보면 착시가 생깁니다. 실제 절감은:
- **(cached prompt tokens / total prompt tokens)** 비율
- TTL로 인한 rewarm 비중(Anthropic은 write/read가 따로 비용/토큰으로 관찰될 수 있음)

OpenAI는 응답 usage에 `cached_tokens`가 나타난다고 문서에 명시돼 있어, 이 값을 메트릭으로 바로 박을 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

### Best Practice 3) Anthropic은 “시드 1회 + 병렬 N회”로 캐시를 돈으로 바꿔라
Anthropic의 `cache_control`은 “여기까지 캐시 저장”이므로, 아래 패턴이 실전에서 강합니다.

- Step A: 긴 prefix를 포함한 요청 1개로 cache seed(write)
- Step B: 같은 prefix를 공유하는 작업을 fan-out(read)로 병렬 처리

반대로, 요청이 드문드문 들어오면 TTL(기본 5분) 때문에 write가 반복되어, read로 이득 볼 타이밍이 줄어듭니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?utm_source=openai))

### 흔한 함정/안티패턴

- **prefix 앞부분에 timestamp/request_id를 넣는 실수**: 캐시를 “매번 깨는” 최악의 패턴
- **툴 정의/함수 스키마를 요청마다 미세하게 바꾸는 패턴**: OpenAI도 “tools는 동일해야” 캐시가 유효하다고 가이드에서 강조 ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))
- **OpenAI에서 과도한 단일 prefix 트래픽**: 동일 prefix+key에 요청이 몰리면 overflow로 캐시 효과가 떨어질 수 있다고 문서에 언급됨 → 라우팅 키/샤딩 전략(tenant별 key 등) 고려 ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- 캐시를 극대화하려고 prefix를 “거대하게” 만들면:
  - 캐시 hit 시엔 이득
  - miss/rewarm 시엔 비용 폭탄 + latency 악화
- 따라서 “캐시될 만한 안정적 구간”만 크게 만들고, 변동 가능성이 있는 지식(RAG)은 **압축 요약** 또는 **서버측 지식 베이스**로 분리하는 게 더 안전합니다.

---

## 🚀 마무리

정리하면, 2026년 5월 기준으로 prompt caching 최적화의 본질은 “프롬프트”가 아니라 **반복되는 prefix를 제품 레벨에서 고정하고, 히트율을 계측해 피드백 루프를 돌리는 것**입니다.

도입 판단 기준(체크리스트)
- 내 요청의 30% 이상이 “매번 반복되는 긴 prefix”인가?
- prefix를 **완전히 동일하게** 유지할 수 있는가(버전 관리 가능)?
- Anthropic이라면 TTL 내에 read가 충분히 발생하는 트래픽 패턴인가?
- OpenAI라면 `cached_tokens` 기반으로 히트율/비용을 관측하고, 필요 시 `prompt_cache_key`로 라우팅을 샤딩할 준비가 되어 있는가? ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))

다음 학습 추천
- OpenAI Prompt Caching 가이드(구조/라우팅/`prompt_cache_key`/overflow 조건) ([platform.openai.com](https://platform.openai.com/docs/guides/prompt-caching?utm_source=openai))
- Anthropic Prompt Caching 문서(`cache_control`, TTL, exact match, 1-hour 옵션) ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching?utm_source=openai))
- “캐시가 깨지는 에이전트” 관점의 연구(롱 호라이즌에서 캐시 전략 비교) ([arxiv.org](https://arxiv.org/abs/2601.06007?utm_source=openai))