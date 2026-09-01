---
title: "프롬프트 캐싱으로 LLM 비용 30~80% 줄이기: OpenAI vs Anthropic(2026년 9월 기준) 실전 설계/히트율 튜닝"
date: 2026-09-01 04:44:29 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-09]
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
LLM 비용이 새는 대표 구간은 “매 요청마다 반복되는 긴 prefix(시스템 지시문, tool schema, 코드베이스 요약, 정책, 예시 few-shot)”를 매번 full price로 다시 prefill하는 순간입니다. Prompt caching은 바로 이 **prefill(KV cache) 재사용**을 공급자 측에서 해 주고, 그만큼을 **할인 과금**으로 돌려주는 기능입니다. OpenAI는 특정 모델에서 **자동(prefix 기반) 캐싱**을 적용하며, 1,024 tokens 이상 공통 prefix가 있을 때 캐시된 입력을 할인합니다. ([openai.com](https://openai.com/index/api-prompt-caching/)) Anthropic은 기본적으로 **명시적(cache_control) 캐싱**이고, 캐시 write는 더 비싸지만(hit)은 훨씬 싸게 책정되어 “제대로만 설계하면” 절감 폭이 큽니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc))

언제 쓰면 좋나:
- 멀티턴 agent/코드 리뷰/대화형 분석처럼 **같은 system+tools+정책이 반복**되고, 사용자 질문만 바뀌는 구조
- RAG를 하더라도 “매번 바뀌는 문서”가 아니라 **고정 지식(규정/매뉴얼/코드베이스 인덱스)** 비중이 큰 경우
- latency(특히 TTFT)도 같이 줄이고 싶은 경우(캐시 hit면 prefill이 줄어듦)

언제 쓰면 안 되나(혹은 기대치 낮추기):
- 요청이 짧아 **캐시 임계값을 못 넘는** 워크로드(OpenAI는 1,024 tokens 이상에서 의미 있게 작동) ([openai.com](https://openai.com/index/api-prompt-caching/))
- 매번 system prompt/tool 정의가 조금씩 달라지는(버전 문자열, 타임스탬프, 정렬 불안정한 JSON 등) 경우 → 히트율이 0%로 떨어지기 쉽습니다
- “출력 토큰”이 비용 대부분인 워크로드(캐싱은 기본적으로 **input 쪽** 최적화)

---

## 🔧 핵심 개념
### 1) Prompt caching이 실제로 캐싱하는 것: “가장 긴 prefix”
Transformer는 입력 prefix를 처리하며 KV cache를 쌓습니다. 동일한 prefix가 다시 오면 이 KV를 재사용할 수 있고, 그게 prompt caching의 본질입니다(정확히는 공급자 내부에서 prefix 해시/세그먼트 단위로 관리). OpenAI는 “최근에 본 prompt의 **longest prefix**”를 캐싱하며, **1,024 tokens에서 시작해 128-token 단위로 증가**하는 방식으로 prefix 캐싱을 적용한다고 명시합니다. ([openai.com](https://openai.com/index/api-prompt-caching/))

Anthropic은 더 노골적으로 “`tools`, `system`, `messages` 순서로 프롬프트를 구성하고, `cache_control`로 지정된 블록까지의 **전체 prefix를 캐싱**”한다고 문서화합니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc)) 즉, **어디까지를 고정(prefix)로 만들지**를 개발자가 설계할 수 있습니다.

### 2) 가격 모델 차이(2026년 9월 관점에서 중요한 포인트)
- **OpenAI(자동 캐싱)**: 공통 prefix가 캐시되면 해당 입력 토큰이 할인됩니다(과거 발표 기준 “50% discount” 같은 형태로 안내). ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai)) 즉 “캐시를 켜는 버튼”보다 **prefix를 안정화**하는 게 핵심입니다.
- **Anthropic(명시적 캐싱)**: 캐시에 “써 넣는(write)” 비용이 기본 input 대비 **25% 더 비싸고**, 캐시 “hit/read”는 기본 input의 **10% 수준**으로 싸게 책정됩니다. ([claude.com](https://claude.com/blog/prompt-caching?_bhlid=66199afc6a7e020dea1966993a4a8d61fd9b4f40&utm_source=openai)) 또한 기본 TTL은 5분이고, 1시간 TTL 옵션도 “추가 비용”으로 제공합니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc))  
  → 결론: **hit율이 일정 수준 이상** 나오면 폭발적으로 이득, 반대로 **캐시가 자주 깨지면(write만 내고) 손해**입니다.

### 3) “캐시 히트율”을 시스템적으로 다루는 관점
캐시 최적화는 모델이 아니라 **프롬프트 엔지니어링 + 빌드/배포 규율** 문제에 가깝습니다.

- 캐시 가능한 영역(Stable Prefix): 정책/역할/툴 스키마/출력 스키마/고정된 few-shot/코드베이스 요약
- 캐시 깨뜨리는 영역(Volatile Suffix): 사용자 질의, RAG로 가져온 top-k 문서(매번 달라짐), 동적으로 생성되는 날짜/버전/요청ID

따라서 구조는 항상:
1) **변하지 않는 것들을 앞(prefix)로** 최대한 몰아넣고  
2) **변하는 것들은 뒤(suffix)로** 보내며  
3) “변하지 않는 것”이 실제로 *항상 동일 바이트열*로 렌더링되도록(정렬/공백/키 순서/숫자 포맷) 강제합니다.

---

## 💻 실전 코드
아래는 “사내 코드리뷰 agent” 현실 시나리오입니다.  
- 고정: 리뷰 정책, tool schema(리포지토리 파일 읽기/검색), 출력 JSON schema  
- 변동: PR diff, 질문, 추가 컨텍스트  
목표: 매 요청마다 10k~30k tokens급 고정 prefix를 재사용해 비용을 줄이고, `usage`에서 cached_tokens(혹은 Anthropic의 cache read 관련 usage)를 로깅해 히트율을 계측합니다.

### 1) 공통 준비: “고정 prefix를 안정적으로 직렬화”
```python
# python
import json
from dataclasses import dataclass
from typing import Any, Dict

def stable_json(obj: Any) -> str:
    # 캐시 히트율 최적화의 1순위: 동일 데이터는 항상 동일 문자열로 렌더링
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

@dataclass(frozen=True)
class PromptParts:
    system: str
    tools_json: str
    output_schema_json: str
```

### 2) Anthropic(Messages API) — explicit cache_control로 “여기까지 캐싱” 선언
Anthropic은 `tools/system/messages`의 prefix를 `cache_control`이 붙은 블록까지 캐싱합니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc)) 아래는 **정책+툴+스키마**를 캐싱하고, PR diff는 매번 바뀌니 뒤로 둡니다.

```python
# python
# pip install anthropic
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

REVIEW_POLICY = """You are a senior code reviewer.
Rules:
- Focus on correctness, security, performance.
- Output MUST be valid JSON matching the provided schema.
"""

TOOLS = [
  {
    "name": "repo_read_file",
    "description": "Read a file from the repo",
    "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
  },
  {
    "name": "repo_search",
    "description": "Search in repo",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
  }
]

OUTPUT_SCHEMA = {
  "type": "object",
  "properties": {
    "summary": {"type": "string"},
    "risk_level": {"type": "string", "enum": ["low","medium","high"]},
    "findings": {
      "type": "array",
      "items": {"type":"object","properties":{
        "file":{"type":"string"},
        "line":{"type":"integer"},
        "issue":{"type":"string"},
        "fix":{"type":"string"}
      }, "required":["file","issue","fix"]}
    }
  },
  "required": ["summary","risk_level","findings"]
}

def review_pr(pr_diff: str, pr_title: str) -> Dict:
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1200,
        # automatic caching: top-level cache_control로도 가능(문서)
        # 여기서는 explicit breakpoint를 보여주기 위해 content block에 둠
        system=REVIEW_POLICY,
        tools=TOOLS,
        messages=[
            {
              "role":"user",
              "content":[
                # 여기까지를 캐시 prefix로 고정: tools/system + 이 블록(스키마)
                {"type":"text","text":"Output JSON schema:\n"+stable_json(OUTPUT_SCHEMA),
                 "cache_control":{"type":"ephemeral"}},
                # 여기부터는 매번 변동(캐시 suffix)
                {"type":"text","text":f"PR Title: {pr_title}\n\nDIFF:\n{pr_diff}\n\nReview it."}
              ]
            }
        ],
    )
    # usage에서 cache 효과를 반드시 로깅(히트율 계측)
    # 문서상 cached prefix 재사용으로 비용/시간 감소. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc&utm_source=openai))
    print(resp.usage.model_dump())
    return resp.content[0].text

# 예상 출력(예시)
# {'input_tokens':..., 'output_tokens':..., ... cache 관련 필드 ...}
```

핵심 포인트:
- `cache_control`이 붙은 “스키마 블록”이 **prefix의 끝(=breakpoint)** 입니다.
- PR diff는 뒤로 보내서 매번 바뀌어도 **캐시 prefix는 동일**하게 유지.
- TTL(기본 5분) 안에서 동일 prefix를 재사용하면 refresh가 되며, 필요하면 1-hour TTL을 고려합니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc))

### 3) OpenAI — 자동 prefix 캐싱을 “먹게” 만드는 프롬프트 빌드
OpenAI는 지원 모델에서 prompt caching을 자동 적용하고, 1,024 tokens 이상 공통 prefix에서 캐시가 동작하며 `usage`에 `cached_tokens`가 표시됩니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
즉 구현 포인트는 API 파라미터가 아니라 **prefix 안정화 + 길이 확보**입니다.

```python
# python
# pip install openai
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SYSTEM_PREFIX = """You are a senior code reviewer.
Rules:
- Focus on correctness, security, performance.
- Output MUST be valid JSON matching the provided schema.
"""

def openai_review_pr(model: str, pr_diff: str, pr_title: str):
    # 고정 prefix는 항상 같은 순서/문자열로 구성
    schema = stable_json(OUTPUT_SCHEMA)
    tools = TOOLS  # stable_json 쓰는 걸 추천(여기서는 개념상 생략)

    resp = client.responses.create(
        model=model,
        input=[
          {"role":"system","content": SYSTEM_PREFIX + "\nOutput JSON schema:\n" + schema},
          {"role":"user","content": f"PR Title: {pr_title}\n\nDIFF:\n{pr_diff}\n\nReview it."}
        ],
        # tool 사용이 있다면 tools를 여기에 넣되 "항상 동일 직렬화"를 강제
        # tools=...
        max_output_tokens=1200,
    )
    # cached token 계측
    # OpenAI는 usage에 cached_tokens를 노출. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))
    print(resp.usage)
    return resp.output_text

# 예상 출력(예시)
# usage: { input_tokens:..., output_tokens:..., input_tokens_details:{cached_tokens: N}, ... }
```

운영 팁:
- “고정 prefix가 1,024 tokens를 넘는지”부터 확인하세요(안 넘으면 캐시가 사실상 0). ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))
- `cached_tokens / input_tokens` 비율을 SLI로 잡으면, 캐싱 회귀(조용히 비용 증가)를 빨리 잡을 수 있습니다(커뮤니티에서도 이 포인트를 경고). ([community.openai.com](https://community.openai.com/t/how-are-reasoning-tokens-cached-tokens-input-tokens-and-output-tokens-counted-for-billing/1386849/2?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “캐시 친화적 프롬프트 레이아웃”을 강제하라
- 앞(prefix): system 정책 + tool 정의 + 출력 스키마 + 고정 few-shot
- 뒤(suffix): user query + RAG 결과 + diff/첨부파일
Anthropic은 캐시가 `tools/system/messages` 전체 prefix를 본다고 명시하므로, **tools를 동적으로 생성**하면 히트율이 바로 무너집니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc)) OpenAI도 longest-prefix 방식이므로 동일 원칙이 적용됩니다. ([openai.com](https://openai.com/index/api-prompt-caching/))

### Best Practice 2) “문자열 동일성(byte-level)”을 깨는 사소한 변동을 제거
캐시는 “의미가 같음”이 아니라 **prefix가 동일**해야 hit입니다(특히 Anthropic은 cache_control까지 100% 동일 prefix를 요구한다고 문서/가이드가 반복해서 강조). ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc))  
실무에서 자주 깨는 것들:
- JSON key 순서, float 포맷, 공백/개행, 날짜 삽입
- tool schema에 빌드 버전/환경명 주입
- “요약 캐시”를 만들었는데 매 배포마다 문구가 달라지는 경우

### Best Practice 3) TTL 기반 “캐시 워밍”은 비용-리스크를 보고 결정
- Anthropic: 기본 TTL 5분, 1시간 TTL은 추가 비용. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc))  
  워크로드가 “짧은 burst”면 5분으로도 충분하고, “오래 붙는 세션”이면 1시간 TTL이 유리할 수 있습니다. 다만 TTL을 늘리면 **write 프리미엄**을 더 내는 구조라(모델/티어별 표 참고) 실제 hit율과 세션 패턴으로 계산해야 합니다. ([www-cdn.anthropic.com](https://www-cdn.anthropic.com/files/4zrzovbb/website/3684c2faafb97418665782cea0001f439f74b1d2.pdf))
- OpenAI: 캐시는 보통 5~10분 비활성 시 지워지고, 1시간 내 제거된다고 안내합니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
  → “사용자 한 명당 세션이 길게 이어지는 제품”이면 잘 맞고, “요청이 산발적”이면 기대 절감이 낮습니다.

### 흔한 함정/안티패턴
- **RAG 문서를 prefix에 박아 넣기**: top-k가 매번 달라져 prefix가 흔들리면 캐시가 거의 안 맞습니다. 고정 지식(매뉴얼/정책)만 prefix로, 동적 검색 결과는 suffix로.
- **관측(Observability) 없이 ‘캐싱 켰다’고 믿기**: OpenAI는 `cached_tokens`, Anthropic은 usage 필드(및 비용 항목)로 “읽힌 캐시”가 드러납니다. 이걸 로그/메트릭으로 안 남기면 절감이 아니라 *희망회로*가 됩니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))
- **캐시 write 프리미엄 무시(Anthropic)**: hit율이 낮으면 “더 비싸게 써 놓고 못 읽는” 꼴이 됩니다(가격표에 cache writes가 base input보다 비쌈이 명시). ([www-cdn.anthropic.com](https://www-cdn.anthropic.com/files/4zrzovbb/website/3684c2faafb97418665782cea0001f439f74b1d2.pdf))

비용/성능/안정성 트레이드오프(현실적 결론):
- 캐싱은 **latency와 비용을 같이** 줄여주지만,
- “프롬프트를 제품 코드처럼 버전/직렬화/테스트”하지 않으면 히트율이 출렁이고, 청구서가 조용히 커집니다.
- 특히 Anthropic은 경제성이 hit율에 더 민감(저렴한 hit vs 비싼 write)하므로, 캐시 breakpoint를 “정말 고정된 덩어리”에만 걸어야 합니다. ([claude.com](https://claude.com/blog/prompt-caching?_bhlid=66199afc6a7e020dea1966993a4a8d61fd9b4f40&utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 9월 기준 prompt caching의 승부처는 “API 옵션”이 아니라 **(1) prefix를 얼마나 길고 안정적으로 만들었는지, (2) 히트율을 계측하고 회귀를 잡는지**입니다. OpenAI는 1,024 tokens 이상 공통 prefix를 longest-prefix로 자동 캐싱하고 `cached_tokens`로 관측할 수 있어 “프롬프트 설계”가 핵심입니다. ([openai.com](https://openai.com/index/api-prompt-caching/)) Anthropic은 `cache_control`로 캐시 경계를 명시하고, write 프리미엄/cheap hit/TTL(5m, 1h)을 가격표로 노출해 “설계가 맞으면 절감 폭이 매우 크지만, 캐시가 깨지면 손해” 구조가 더 뚜렷합니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc))

도입 판단 기준(실무용):
- “반복되는 고정 컨텍스트가 2k~30k tokens 이상” + “세션/배치에서 동일 prefix가 3회 이상 반복”이면 우선 후보
- 메트릭: `cached_tokens/input_tokens`(OpenAI) 혹은 cache read 비중(Anthropic)을 대시보드화 할 수 있으면 본격 도입
- 프롬프트를 stable serialization + snapshot test로 관리할 수 없으면(조직/프로세스상) 기대 절감이 유지되기 어렵습니다

다음 학습 추천:
- OpenAI Prompt Caching 동작/임계/usage 필드 문서(캐시가 1,024 tokens부터, 128-step 증가) ([openai.com](https://openai.com/index/api-prompt-caching/))
- Anthropic prompt caching 문서(캐시 순서: tools→system→messages, TTL 5m/1h) 및 공식 가격표에서 write/hit 단가 확인 ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc))