---
title: "LLM API 비용 70% 줄이는 2026년식 Routing 설계: Prompt Caching + Budget-Aware Model Router"
date: 2026-06-18 04:48:48 +0900
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
2026년 6월 기준, LLM API 비용 최적화는 더 이상 “프롬프트 조금 줄이기”로 해결되지 않습니다. 실제로 비용은 (1) **긴 system/context 재전송**, (2) **불필요하게 비싼 모델 고정 사용**, (3) **출력 토큰 폭주**에서 터집니다. 특히 agent/RAG/코드리뷰처럼 “매 호출마다 비슷한 긴 컨텍스트”를 넣는 워크로드는 토큰이 선형이 아니라 **세션 길이에 따라 기하급수적으로** 새는 구간이 자주 생깁니다.

언제 쓰면 좋나:
- 긴 system prompt(규칙/정책/도메인지식) + 짧은 user input 패턴이 반복되는 제품(코딩 에이전트, 고객지원, 문서 QA, 내부 챗봇)
- 품질 요구가 다양한 요청이 섞인 제품(간단 요약/분류 vs 고난도 reasoning) → **모델 라우팅**으로 이득 큼
- 실시간/비실시간이 섞임(온라인 응답 + 야간 대량 처리) → **Batch**로 절반 할인 가능 ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))

언제 쓰면 안 되나:
- 요청마다 프롬프트 구조가 크게 달라 **prefix가 공유되지 않는** 경우(캐시 효율 낮음)
- “매번 최신 외부 도구 호출 결과”가 system 앞부분에 끼어들어 prefix가 깨지는 에이전트(캐시가 깨짐)
- 품질 실패 비용이 매우 큰 업무(의료/법률/결제 등)에서 라우팅 기준이 빈약한 상태로 무리하게 “싼 모델 우선”을 하면 사고 납니다(guardrail 필요)

---

## 🔧 핵심 개념
### 1) LLM 비용의 진짜 분해: input/output + “캐시가 먹는 구간”
2026년 최적화의 핵심은 “토큰을 덜 쓰자”가 아니라 **비싼 토큰을 싼 토큰으로 바꾸고(캐시), 비싼 모델 호출을 싼 모델로 대체(라우팅)**하는 겁니다.

- **Prompt Caching(Exact-prefix cache)**  
  공급자가 “이전에 본 prompt prefix”를 재사용해 **prefill 비용**을 줄이고, 그만큼 **cached input token을 할인 청구**합니다. OpenAI는 “최근에 본 longest prefix”를 캐시하고, 응답 usage에 `cached_tokens`로 노출합니다. 또한 1,024 토큰 이상부터 prefix 캐시가 적용되고 128 토큰 단위로 확장됩니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
  OpenAI는 cached input에 대해 **50% 할인**을 명시합니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
  (다른 벤더도 캐시/배치 할인 구조가 비슷하게 “반복 컨텍스트가 길수록 이득”으로 설계되어 있습니다. ([swfte.com](https://www.swfte.com/ko/prompt-caching?utm_source=openai)))

- **Batch API(비실시간 24h 비동기 처리)**  
  OpenAI Batch는 24시간 내 완료 조건으로 **입력/출력 모두 50% 할인** + 별도 레이트리밋 풀을 제공합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))  
  즉, “당장 답이 필요 없는 작업”은 라우팅이 아니라 **실행 경로 자체를 Batch로 라우팅**해야 합니다.

### 2) Model Routing: “최적 모델”이 아니라 “최적 정책”
모델 라우팅은 단순히 `cheap_model`/`expensive_model`을 나누는 게 아니라,
- **요청 난이도 추정**
- **실패 시 업그레이드(escalation)**
- **예산(budget)과 SLO(latency/quality) 제약**
을 포함하는 **정책 엔진**입니다.

2026년 트렌드는 “하나의 프롬프트에 모든 걸 때려 넣고 비싼 모델로 끝내기”가 아니라, 아래 3단 분리를 기본으로 봅니다.

1) **Gate(분류/난이도 추정)**: 아주 싼 모델로 “이 요청이 어려운가?”를 판정  
2) **Solve(해결)**: 난이도에 따라 적절한 모델 선택  
3) **Verify(검증/재시도)**: 실패 징후가 있으면 상향 라우팅  
이런 “검증 경제학” 관점은 2026년에 특히 중요하다는 분석이 나옵니다. ([ifitsmanu.com](https://ifitsmanu.com/pdfs/the-cost-of-being-right.pdf?utm_source=openai))

### 3) Token Saving의 본질: “캐시를 깨지 않게 설계”
Prompt caching은 **prefix가 1글자라도 달라지면**(벤더 구현에 따라) 재사용이 깨지기 쉽습니다. 그래서 토큰 절약은 아래 “구조”로 접근해야 합니다.

- **불변 영역(캐시 대상 prefix)**: system instructions, 정책, 도메인 규칙, tool schema, 고정 RAG 서문  
- **가변 영역(캐시 비대상 suffix)**: user message, 최신 검색 결과, per-request metadata(시간/세션 id)  

여기서 흔한 실수는 “매 요청마다 날짜/요청ID/실시간 검색 결과를 system 앞에 넣는 것”입니다. 그러면 prefix가 매번 달라져 캐시가 죽습니다.

---

## 💻 실전 코드
아래 예제는 “실제 서비스”에 가까운 형태로:
- **FastAPI**로 HTTP 엔드포인트 제공
- 요청은 `support_ticket_reply`(고객지원 답변 생성) 시나리오
- **Budget-aware routing**: (1) Gate로 난이도 분류 → (2) 저가 모델 우선 → (3) 실패 시 상향
- **Prompt caching을 살리는 프롬프트 레이아웃**(불변 prefix/가변 suffix 분리)
- OpenAI는 `usage.prompt_tokens_details.cached_tokens`를 보고 캐시 효율을 로그로 남깁니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
- 비실시간 모드는 Batch로 보내는 설계 포인트를 함께 넣습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))

### 0) 의존성 / 실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pydantic openai tiktoken
export OPENAI_API_KEY="..."
uvicorn app:app --reload --port 8000
```

### 1) app.py (routing + 캐시 친화 prompt + 상향 라우팅)
```python
# app.py
from __future__ import annotations

import os
import time
from typing import Literal, Optional, Dict, Any

import tiktoken
from fastapi import FastAPI
from pydantic import BaseModel, Field
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
app = FastAPI()

# ---- 모델 선택 예시(조직별로 실제 사용하는 모델명으로 교체) ----
# 핵심은 "Gate는 매우 저렴/빠르게", "Solve는 난이도별로", "Fallback은 상향" 구조.
GATE_MODEL = "gpt-5.4-mini"      # 게이트(난이도/리스크 분류)
CHEAP_MODEL = "gpt-5.4"          # 기본 해결
EXPENSIVE_MODEL = "gpt-5.5"      # 상향(고난도/고정확)

# ---- 캐시를 살리기 위한 불변 prefix ----
# 매 요청마다 바뀌는 값(시간, 티켓ID, 사용자 이름 등)은 절대 여기 넣지 말 것.
SYSTEM_PREFIX = """You are a senior customer support engineer.
Follow company policy strictly.

Company policy (must-follow):
1) Never request passwords or OTP.
2) If user asks for refunds: ask for order id and purchase date.
3) If user reports billing issue: request invoice number, last 4 digits only.
4) Be concise, actionable, and include next steps.

Product facts (stable):
- Product: AcmeCloud
- Auth: SSO + email login
- Billing cycles: monthly, annual
- SLA: 99.9%
"""

# ---- 가변 suffix 템플릿: 여기에 요청별 데이터 배치 ----
USER_TEMPLATE = """Ticket meta:
- channel: {channel}
- priority: {priority}
- customer_tier: {tier}

Ticket content:
{content}

Your task:
Write a reply email in Korean.
- Ask only for necessary info.
- Provide 3 bullet next steps.
- If you need escalation, say so.
"""

enc = tiktoken.get_encoding("o200k_base")

def count_tokens(text: str) -> int:
    return len(enc.encode(text))

class TicketRequest(BaseModel):
    channel: Literal["email", "chat", "phone_followup"]
    priority: Literal["low", "normal", "high"]
    tier: Literal["free", "pro", "enterprise"]
    content: str = Field(min_length=10)
    mode: Literal["realtime", "offline"] = "realtime"

class TicketResponse(BaseModel):
    model_used: str
    escalated: bool
    reply: str
    usage: Dict[str, Any]
    prompt_tokens_estimate: int

def gate_decision(req: TicketRequest) -> Dict[str, Any]:
    """
    Gate: 싼 모델로 난이도/리스크를 분류한다.
    여기서 중요한 건 '완벽한 분류'가 아니라, 비싼 모델 호출을 줄일 만큼만.
    """
    gate_prompt = f"""
Classify the ticket difficulty and risk.

Return JSON with fields:
- difficulty: easy|medium|hard
- risk: low|high  (high if policy-sensitive, legal/billing, or escalation likely)
- reason: short

Ticket:
{req.content}
""".strip()

    r = client.responses.create(
        model=GATE_MODEL,
        input=[
            {"role": "system", "content": "You are a strict classifier. Output only JSON."},
            {"role": "user", "content": gate_prompt},
        ],
        # gate는 짧게 끝내야 비용/지연이 줄어듦
        max_output_tokens=120,
    )
    # 안전하게 파싱(실무에선 json schema validation 추천)
    text = r.output_text
    return {"raw": text}

def call_solver(model: str, req: TicketRequest) -> Dict[str, Any]:
    """
    Solve: 캐시 친화 구조(불변 prefix + 가변 suffix)로 호출.
    """
    user_msg = USER_TEMPLATE.format(
        channel=req.channel,
        priority=req.priority,
        tier=req.tier,
        content=req.content,
    )

    # 캐시 효과는 'SYSTEM_PREFIX가 길고 반복될수록' 커짐.
    # 매 요청마다 SYSTEM_PREFIX가 동일하면 cached_tokens가 증가.
    r = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PREFIX},
            {"role": "user", "content": user_msg},
        ],
        max_output_tokens=350,
    )
    return {
        "text": r.output_text,
        "usage": r.usage.model_dump() if hasattr(r.usage, "model_dump") else r.usage,
    }

def looks_failed(reply: str) -> bool:
    """
    실패 휴리스틱(예시):
    - 정책 위반 가능
    - 질문에 답하지 않고 횡설수설
    - 'I cannot'만 반복 등
    실무에선 규칙+별도 검증 모델(또는 deterministic checker) 권장.
    """
    bad_signals = ["비밀번호", "OTP", "암호를 알려", "환불 불가", "I can't", "cannot help"]
    return any(s in reply for s in bad_signals) or len(reply.strip()) < 60

@app.post("/support/reply", response_model=TicketResponse)
def support_reply(req: TicketRequest):
    # offline이면 Batch로 보내는 게 정석(여기선 "설계 포인트"로만 표시)
    # OpenAI Batch는 24h 내 처리로 50% 할인. ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))
    if req.mode == "offline":
        return TicketResponse(
            model_used="(send-to-batch)",
            escalated=False,
            reply="This request should be enqueued to Batch API for 50% cost reduction (implementation omitted).",
            usage={},
            prompt_tokens_estimate=count_tokens(SYSTEM_PREFIX) + count_tokens(req.content),
        )

    gate = gate_decision(req)
    # 여기서는 gate JSON 파싱 대신 간단 정책:
    # high priority/enterprise면 기본 상향, 아니면 cheap부터
    prefer_expensive = (req.priority == "high" and req.tier in ("pro", "enterprise"))

    first_model = EXPENSIVE_MODEL if prefer_expensive else CHEAP_MODEL

    t0 = time.time()
    first = call_solver(first_model, req)
    reply = first["text"]
    escalated = False

    if (not prefer_expensive) and looks_failed(reply):
        # 실패 감지 시 상향 라우팅
        second = call_solver(EXPENSIVE_MODEL, req)
        reply = second["text"]
        usage = {"first": first["usage"], "second": second["usage"], "gate": gate}
        escalated = True
    else:
        usage = {"first": first["usage"], "gate": gate}

    # 관측 포인트: cached_tokens를 로깅해서 "캐시가 깨졌는지"를 바로 본다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))
    prompt_est = count_tokens(SYSTEM_PREFIX) + count_tokens(
        USER_TEMPLATE.format(channel=req.channel, priority=req.priority, tier=req.tier, content=req.content)
    )

    _elapsed = time.time() - t0
    return TicketResponse(
        model_used=first_model if not escalated else EXPENSIVE_MODEL,
        escalated=escalated,
        reply=reply,
        usage=usage,
        prompt_tokens_estimate=prompt_est,
    )
```

### 2) 예상 출력/로그에서 확인할 것
- `usage.first.prompt_tokens_details.cached_tokens` 같은 값이 **0이 아니고 점점 커지는지** 확인하세요. (OpenAI는 `cached_tokens`를 usage에 넣어줍니다.) ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
- 캐시가 계속 0이면 대개:
  - system prefix가 매번 달라지거나
  - system 앞에 timestamp/trace id를 넣거나
  - tool schema를 동적으로 생성해서 매번 달라졌거나
  - 프롬프트 길이가 1,024 토큰 미만이라 캐시 구간이 형성되지 않은 경우입니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “캐시 친화 프롬프트 레이아웃”을 코드로 강제하라
문서에 “system은 고정”이라고 써도, 기능이 늘면 누군가 system 앞에 변수를 넣습니다.  
해결: `SYSTEM_PREFIX`를 상수로 분리하고, 요청별 데이터는 무조건 suffix로만 들어가게 템플릿/코드 리뷰 룰을 만드세요. OpenAI는 longest prefix를 캐시하고 `cached_tokens`로 관측 가능하니, **SLO에 캐시 히트율을 포함**하는 게 효과적입니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))

### Best Practice 2) “라우팅”은 모델 선택만이 아니라 실행 경로 선택이다
- 실시간: sync endpoint
- 비실시간: Batch로 강제  
Batch는 24시간 내 완료 + **50% 할인**이 명확합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))  
대량 문서 분류/임베딩/평가/E2E 리포트 생성은 Batch로 빼는 것만으로도 “모델 라우팅”보다 큰 절감이 나옵니다.

### Best Practice 3) 출력 토큰을 “상한”이 아니라 “정책”으로 다뤄라
대부분의 폭탄은 output입니다(장황한 답변/코드 덤프).  
- `max_output_tokens`를 항상 걸고
- “3 bullets”처럼 형식을 강제하고
- 실패 시 상향 라우팅하되, **상향 시에도 output 한도를 다시 설정**하세요(상향=무제한이 아님)

### 흔한 함정/안티패턴
- **Semantic cache를 무검증으로 붙이기**: 유사 질문에 이전 답을 재사용하면 “그럴듯한 오답”이 섞입니다. 연구/실무 모두 semantic caching은 gate/검증이 중요하다고 봅니다. ([tmls.nyc](https://www.tmls.nyc/research/ai-caching-strategies?utm_source=openai))  
- **캐시 TTL/정책을 모른 채 전제하기**: 벤더별로 캐시 만료/할인/쓰기 비용 구조가 달라, “캐시가 항상 된다”는 가정으로 설계하면 요금이 흔들립니다. (OpenAI는 캐시가 보통 5~10분 inactivity 후 정리되고 1시간 내 제거된다고 설명합니다.) ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  
- **라우팅 기준이 비용만 보는 것**: “싼 모델이 틀리면 다시 부르는 비용” + “재시도 지연”까지 합치면 총비용이 증가할 수 있습니다. 그래서 gate→solve→verify 구조(혹은 escalation 규칙)가 필요합니다. ([ifitsmanu.com](https://ifitsmanu.com/pdfs/the-cost-of-being-right.pdf?utm_source=openai))  

비용/성능/안정성 트레이드오프 정리:
- Prompt caching: 품질 손실 없이(같은 입력이면 같은 처리) 비용↓/TTFT↓ 가능하지만, **prefix 안정성**이 전제입니다. ([tmls.nyc](https://www.tmls.nyc/research/ai-caching-strategies?utm_source=openai))  
- Model routing: 평균 비용은 크게 줄지만, **경계 케이스 품질 저하**와 운영 복잡도(관측/재시도/정책 관리)가 증가합니다.
- Batch: 지연을 비용으로 바꾸는 가장 확실한 레버(단, 24h 윈도우 제약). ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))  

---

## 🚀 마무리
2026년 6월의 LLM 비용 최적화는 “토큰을 줄이는 기술”이 아니라 **(1) 반복 컨텍스트는 prompt caching으로 ‘싼 토큰’으로 만들고, (2) 요청 난이도에 따라 모델/실행 경로를 라우팅하고, (3) 출력 토큰을 정책으로 통제**하는 시스템 설계 문제입니다. OpenAI는 prompt caching의 `cached_tokens` 관측과 cached input 할인(50%)을 제공하고, Batch는 24h 비동기 처리로 입력/출력 50% 할인을 제공합니다. ([openai.com](https://openai.com/index/api-prompt-caching/?utm_source=openai))  

도입 판단 기준(실무 체크리스트):
- 내 서비스 요청 중 **“긴 공통 prefix”**가 반복되는가? → Yes면 caching부터
- 실시간이 꼭 필요 없는 요청이 월 10만 건 이상인가? → Yes면 Batch 라우팅이 1순위
- 간단 요청/어려운 요청이 섞여 있는가? → Yes면 gate→escalation 라우팅
- 캐시/라우팅을 관측할 메트릭(`cached_tokens`, hit rate, escalation rate, cost per success)을 운영할 준비가 됐는가? → No면 먼저 관측부터

다음 학습 추천:
- Prompt caching/semantic caching을 레이어로 나눠 경제성을 비교한 레퍼런스 아키텍처(“exact-prefix는 무손실, semantic은 guarded”) 관점 ([tmls.nyc](https://www.tmls.nyc/research/ai-caching-strategies?utm_source=openai))  
- “검증(verification)이 비용 구조를 바꾼다”는 2026년식 verification economics 관점 ([ifitsmanu.com](https://ifitsmanu.com/pdfs/the-cost-of-being-right.pdf?utm_source=openai))  

원하시면, (1) 당신의 실제 워크로드(요청 샘플 20개) 기준으로 **라우팅 정책/프롬프트 레이아웃을 리팩터링**하거나, (2) `cached_tokens`/비용을 자동 집계하는 **Prometheus/Grafana 대시보드 스키마**까지 포함해 “프로덕션 적용 버전”으로 확장해드릴게요.