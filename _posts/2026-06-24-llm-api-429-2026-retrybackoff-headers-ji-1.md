---
title: "LLM API 429에 지지 않는 법: 2026년형 Retry/Backoff 패턴(Headers 기반 + Jitter + 큐/동시성 제어)"
date: 2026-06-24 04:12:48 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-06]
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
LLM API를 운영에 붙이면 “가끔 느려짐”이 아니라 **특정 순간에 429(Too Many Requests)가 연쇄적으로 터지며 장애처럼 보이는 현상**을 자주 겪습니다. 특히 트래픽이 bursty(짧은 시간에 몰림)한 서비스(챗봇/에이전트, 비동기 배치, 이미지/음성처럼 요청당 비용이 큰 작업)에서 더 심합니다. OpenAI는 rate limit이 **RPM/TPM처럼 분 단위로 보이지만 더 짧은 구간(예: 1 RPS 형태)에서도 적용**될 수 있다고 명시합니다. 그래서 “분당 60회 제한인데 1초에 10번 쏘면 왜 막히지?”가 실제로 일어납니다. ([help-lb.openai.com](https://help-lb.openai.com/en/articles/5955604-how-can-i-solve-429-too-many-requests-errors))

이 글은 “그냥 exponential backoff 하세요” 수준이 아니라, **내 프로젝트에 적용 가능한 판단 기준**을 제공합니다.

- 언제 쓰면 좋나:  
  - 외부 LLM API를 **동기 요청 경로**(유저 요청-응답)에 넣었고 SLO(지연/실패율)가 중요한 경우  
  - 대량 배치/팬아웃(한 요청이 여러 LLM 호출로 분기)처럼 **429가 연쇄 폭발**하기 쉬운 구조  
- 언제 쓰면 안 되나(또는 별도 설계가 먼저):  
  - 429가 아니라 “모델 과부하/일시 장애(5xx/529)”가 본질인데 무작정 재시도만 늘리는 경우(오히려 비용/지연만 증가)  
  - 사용자별/테넌트별 공정성이 중요한데 **전역 backoff만**으로 해결하려는 경우(핵심은 큐/limiter 설계)

---

## 🔧 핵심 개념
### 1) Rate limit은 “하나”가 아니라 “여러 버킷”이다
2026년 현재 주요 LLM 벤더들은 대체로 **요청 수(RPM) + 토큰(TPM 계열)**을 함께 제한합니다.

- **OpenAI**: 응답 헤더로 requests/tokens limit, remaining, reset 정보를 제공합니다. 예:  
  `x-ratelimit-limit-requests`, `x-ratelimit-remaining-tokens`, `x-ratelimit-reset-tokens` 등. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/usage-tiers))  
- **Anthropic(Claude)**: `retry-after`와 함께, requests/tokens/input/output 토큰까지 세분화한 reset 헤더를 제공합니다. 특히 `anthropic-ratelimit-*-reset`은 **RFC3339 timestamp**로 “언제 완전히 회복되는지”를 직접 알려줍니다. ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits))  

결론: **429 한 번**을 “요청을 조금 늦추면 되겠지”로 보면 실패합니다. 지금 막힌 원인이 requests인지 tokens인지에 따라 *대기 시간과 제어 지점*이 달라집니다.

### 2) Retry는 “재시도 루프”가 아니라 “제어 시스템”이다
공식 문서가 공통적으로 권장하는 건 **randomized exponential backoff**입니다. 이유는 간단합니다.

- exponential backoff: 초반엔 빠르게 복구를 시도하되, 계속 실패하면 대기 시간을 급격히 늘려 **자기 보호**  
- jitter(랜덤): 여러 워커가 동시에 429를 맞고 동시에 재시도하면 **thundering herd**가 발생 → 랜덤으로 흩어야 함 ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/usage-tiers))  

또 한 가지 중요한 경고: **실패한 요청도 per-minute limit에 포함**될 수 있으므로, “빠르게 계속 재시도”는 문제를 악화시킵니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/usage-tiers))

### 3) “Headers-first backoff”가 2026년형 정답에 가깝다
2026년 기준, 단순 expo backoff보다 운영 친화적인 패턴은 다음 순서입니다.

1) **서버가 준 힌트**를 최우선으로 존중  
- OpenAI: `x-ratelimit-reset-*`이 “얼마나 남았는지(duration)”로 제공 ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/usage-tiers))  
- Anthropic: `retry-after`(초) + `*-reset`(timestamp) 둘 다 제공 ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits))  

2) 힌트가 없거나 신뢰가 낮을 때만 exponential + jitter로 폴백  
(일부 엔드포인트/상황에서 Retry-After가 없거나, vendor/엔드포인트별로 일관되지 않을 수 있음. 커뮤니티에서도 “기다렸는데도 429가 난다” 같은 케이스가 보고됩니다. ([discuss.ai.google.dev](https://discuss.ai.google.dev/t/429-errors-despite-waiting-after-retrydelay/96899?utm_source=openai)))

3) “재시도”와 “동시성/큐”를 분리  
- backoff는 **개별 요청의 실패 회복**  
- limiter/queue는 **시스템의 평시 안정성(429 자체를 줄임)**

---

## 💻 실전 코드
아래 예제는 “유저 요청이 몰리면(팬아웃 포함) 429가 터지는 API 서버”를 가정합니다. 포인트는:

- **(A) 로컬/분산 limiter로 평시 속도 제어**
- **(B) 429에서는 headers 기반으로 정확히 sleep**
- **(C) 그래도 부족하면 jitter 포함 expo로 폴백**
- **(D) 동시성(cap)로 burst를 눌러서 토큰 버킷을 보호**

### 0) 의존성/실행 방법
```bash
python -m venv .venv
source .venv/bin/activate
pip install openai httpx tenacity anyio
export OPENAI_API_KEY="..."
python llm_stable_client.py
```

### 1) “Headers-first + Jitter backoff + 동시성 제어” 클라이언트
```python
# llm_stable_client.py
import os
import random
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple

import anyio
import httpx
from openai import OpenAI
from openai import RateLimitError, APIError, APITimeoutError

# ---- 튜닝 포인트(서비스에 맞게 조정) ----
MAX_CONCURRENCY = 8             # 워커 동시 실행 상한 (burst 완화)
MAX_RETRIES = 6                 # 요청 단위 재시도 횟수
BASE_BACKOFF = 0.5              # seconds
MAX_BACKOFF = 30.0              # seconds
JITTER_RATIO = 0.2              # +/- 20% jitter
# -------------------------------------

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@dataclass
class RetryHint:
    sleep_seconds: float
    reason: str

def _parse_openai_reset_headers(headers: httpx.Headers) -> Optional[RetryHint]:
    """
    OpenAI는 x-ratelimit-reset-requests: 1s, x-ratelimit-reset-tokens: 6m0s 처럼 duration을 줄 수 있음. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/usage-tiers))
    여기서는 더 보수적으로 tokens reset을 우선(토큰이 병목인 경우가 많기 때문).
    """
    def parse_duration(s: str) -> Optional[float]:
        # 예: "1s", "6m0s"
        try:
            total = 0.0
            num = ""
            for ch in s.strip():
                if ch.isdigit() or ch == ".":
                    num += ch
                else:
                    if not num:
                        continue
                    v = float(num)
                    if ch == "s":
                        total += v
                    elif ch == "m":
                        total += v * 60
                    elif ch == "h":
                        total += v * 3600
                    num = ""
            return total if total > 0 else None
        except Exception:
            return None

    tok = headers.get("x-ratelimit-reset-tokens")
    req = headers.get("x-ratelimit-reset-requests")
    # tokens reset을 우선, 없으면 requests
    if tok:
        d = parse_duration(tok)
        if d:
            return RetryHint(sleep_seconds=d, reason=f"openai x-ratelimit-reset-tokens={tok}")
    if req:
        d = parse_duration(req)
        if d:
            return RetryHint(sleep_seconds=d, reason=f"openai x-ratelimit-reset-requests={req}")
    return None

def _parse_retry_after(headers: httpx.Headers) -> Optional[RetryHint]:
    ra = headers.get("retry-after")
    if not ra:
        return None
    try:
        sec = float(ra)
        if sec >= 0:
            return RetryHint(sleep_seconds=sec, reason=f"retry-after={ra}")
    except Exception:
        return None
    return None

def _with_jitter(seconds: float) -> float:
    # full jitter가 아니라, 운영에서 예측 가능성/디버깅을 위해 +- 비율 jitter를 주는 방식(팀 취향)
    delta = seconds * JITTER_RATIO
    return max(0.0, seconds + random.uniform(-delta, delta))

async def call_chat_stable(
    *,
    messages: list[dict[str, str]],
    model: str = "gpt-4.1-mini",
    timeout_s: float = 30.0,
) -> Tuple[str, Dict[str, Any]]:
    """
    반환: (text, meta)
    meta에 backoff 이유/총 대기시간 등을 남겨 운영 관측에 사용.
    """
    meta: Dict[str, Any] = {"retries": 0, "sleeps": [], "reasons": []}

    for attempt in range(MAX_RETRIES + 1):
        try:
            # OpenAI SDK가 내부 retry를 제공할 수 있어도,
            # 운영에서는 "우리 시스템의 정책"을 일관되게 적용하는 게 보통 더 낫다.
            resp = await anyio.to_thread.run_sync(
                lambda: client.responses.create(
                    model=model,
                    input=messages,
                    timeout=timeout_s,
                )
            )
            # responses API 기준 간단 추출(프로젝트에 맞게 파서 교체)
            text = resp.output_text
            return text, meta

        except RateLimitError as e:
            meta["retries"] += 1

            # 1) headers-first: 서버가 준 reset/retry-after를 최우선
            hint = None
            if hasattr(e, "response") and e.response is not None:
                h = e.response.headers
                hint = _parse_retry_after(h) or _parse_openai_reset_headers(h)

            # 2) 힌트가 없으면 expo backoff로 폴백 (jitter 포함)
            if hint is None:
                sleep_s = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** attempt))
                hint = RetryHint(sleep_seconds=_with_jitter(sleep_s), reason="expo+jitter(fallback)")

            # 3) 0초 재시도는 limit을 더 악화시킬 수 있으니 최소 200ms
            sleep_s = max(0.2, _with_jitter(hint.sleep_seconds))

            meta["sleeps"].append(sleep_s)
            meta["reasons"].append(hint.reason)

            await anyio.sleep(sleep_s)

        except (APITimeoutError, APIError) as e:
            # 429가 아닌 일시 오류는 짧은 expo로 제한적으로만 재시도
            meta["retries"] += 1
            sleep_s = min(10.0, BASE_BACKOFF * (2 ** attempt))
            sleep_s = _with_jitter(sleep_s)
            meta["sleeps"].append(sleep_s)
            meta["reasons"].append(f"transient_error:{type(e).__name__}")
            await anyio.sleep(sleep_s)

    raise RuntimeError(f"Exceeded retries. meta={meta}")

async def main():
    # 현실적인 시나리오: 동시에 여러 유저 요청이 들어오고, 각 요청이 LLM 1~2회 호출한다고 가정
    prompts = [
        [{"role": "user", "content": "지난 7일간 결제 실패 사유를 유형별로 요약하고, 우선순위 조치안을 제안해줘."}],
        [{"role": "user", "content": "로그 포맷을 보고 P95 latency가 튄 원인을 3가지 가설로 정리해줘."}],
        [{"role": "user", "content": "이번 배포에서 위험한 변경점을 찾아 롤백 기준을 제시해줘."}],
        [{"role": "user", "content": "고객 문의 30건을 자동 태깅하기 위한 규칙/프롬프트 설계를 만들어줘."}],
    ] * 5  # burst

    sem = anyio.Semaphore(MAX_CONCURRENCY)

    async def worker(i: int, msgs):
        async with sem:
            t0 = time.time()
            text, meta = await call_chat_stable(messages=msgs)
            dt = (time.time() - t0) * 1000
            print(f"[{i}] done {dt:.0f}ms retries={meta['retries']} reasons={meta['reasons'][-2:]}")
            return text

    async with anyio.create_task_group() as tg:
        for i, msgs in enumerate(prompts):
            tg.start_soon(worker, i, msgs)

if __name__ == "__main__":
    anyio.run(main)
```

#### 예상 출력(예시)
- 트래픽이 덜하면 `retries=0`
- burst에서 429가 나면 일부 작업만 `retries>0`, reason에 `retry-after=...` 또는 `x-ratelimit-reset-tokens=...`가 찍히는 형태

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “재시도”보다 먼저 “429를 안 나게” 만들어라: 큐 + 동시성 상한
OpenAI도 “짧은 burst로도 제한에 걸릴 수 있다”고 명시합니다. ([help-lb.openai.com](https://help-lb.openai.com/en/articles/5955604-how-can-i-solve-429-too-many-requests-errors))  
즉, **백오프는 사후 처리**이고, 운영의 승패는 **동시성(cap) + 큐잉**이 가릅니다.

- 동시성 상한: 모델/엔드포인트별로 다르게(텍스트 vs 이미지/오디오)  
- 큐: user-facing은 짧게, 배치는 길게(우선순위 큐를 추천)

### Best Practice 2) headers를 “관측”에 써라 (단순 sleep 용도 이상)
OpenAI는 remaining/reset을 헤더로 제공합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/usage-tiers))  
Anthropic은 reset을 timestamp로도 제공합니다. ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits))  

이 헤더들을 로그/metrics에 남기면:
- “우리는 tokens 병목인가 requests 병목인가?”
- “burst가 문제인가 steady-state 용량이 부족한가?”
를 데이터로 판단할 수 있습니다.  
**retry 횟수**만 세면 근본 원인을 놓칩니다.

### Best Practice 3) retry budget을 “비용 예산”으로 다뤄라
실패한 요청도 제한을 소모할 수 있고, 재시도는 곧 비용/지연 증가입니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/usage-tiers))  
따라서:
- 요청 타입별 MAX_RETRIES 분리(예: 검색/요약은 2회, 결제/규정 준수 관련은 0회+즉시 fallback)
- “유저 요청 경로”는 총 대기시간 상한(예: 2초)을 두고, 초과 시 graceful degradation(캐시/더 싼 모델/나중에 알림)

### 흔한 함정/안티패턴
- **429인데 즉시 재시도**: limit을 더 태워서 악화(공식 경고) ([help-lb.openai.com](https://help-lb.openai.com/en/articles/5955604-how-can-i-solve-429-too-many-requests-errors))  
- **모든 에러를 동일하게 재시도**: 4xx(잘못된 요청)까지 재시도하면 비용만 증가  
- **jitter 없는 동시 재시도**: 워커들이 같은 타이밍에 깨어나 또 429 → “주기적 장애” 패턴

### 비용/성능/안정성 트레이드오프
- 공격적으로 재시도하면 “성공률”은 올라가지만 **P95/P99 latency와 비용이 상승**
- 동시성 cap을 낮추면 429는 줄지만 **처리량(throughput)이 감소**
- 최적해는 “유저 경험”에 따라 다름:  
  - 실시간 UX: cap+짧은 budget+fallback  
  - 배치: 긴 budget+queue+정확한 headers-first sleep

---

## 🚀 마무리
정리하면, 2026년 6월 기준 LLM API 안정화에서 가장 재현성 높은 패턴은:

1) **큐/동시성 제어로 burst를 먼저 누르고**  
2) 429에서는 **Retry-After / rate limit reset headers를 최우선으로 존중**(headers-first) ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/usage-tiers))  
3) 힌트가 없을 때만 **randomized exponential backoff + jitter**로 폴백 ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/usage-tiers))  
4) 그리고 retry를 “성공률”이 아니라 **비용·지연 예산**으로 관리

도입 판단 기준:
- 429가 월 1~2회 수준: 간단한 expo+jitter만으로 충분
- 429가 burst 때 반복: **동시성 cap + headers-first + 관측(remaining/reset 로깅)**이 필수
- 429가 아니라 장애/과부하(5xx/529)가 섞임: circuit breaker, provider fallback까지 고려(백오프만으로는 부족)

다음 학습 추천:
- 벤더별 rate limit 헤더 스펙을 운영 로그/대시보드에 반영(특히 reset/remaining)
- “요청 단위 retry”와 “전역 limiter/큐”를 분리한 아키텍처(워크큐, priority queue, per-tenant fairness)
- 실제 트래픽 리플레이로 backoff 파라미터 튜닝(재시도 budget, 동시성, 큐 길이)

원하면, 당신의 시스템 형태(동기 API인지, 배치인지, 팬아웃 구조인지, 벤더 혼용인지)를 기준으로 **파라미터(MAX_CONCURRENCY, retry budget, 큐 전략) 튜닝 가이드**까지 구체적으로 맞춰 드릴 수 있습니다.