---
title: "LLM API 429 지옥에서 살아남기: 2026년 5월 기준 Rate Limit Retry/Backoff “정답 패턴” 심층 분석"
date: 2026-05-09 03:42:29 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-05]
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
LLM API를 프로덕션에 붙이면, 성능 최적화보다 먼저 “호출 안정화”에서 막힙니다. 특히 **HTTP 429(Too Many Requests)** 는 단순히 “잠깐 기다렸다가 다시” 수준이 아니라, **동시성(Parallelism)**, **Burst 트래픽**, **토큰 기반 제한(TPM/ITPM/OTPM)**, **Retry 폭풍(thundering herd)** 이 얽히면서 장애를 유발합니다. OpenAI는 429 대응으로 **randomized exponential backoff(지터 포함)** 를 공식 가이드로 안내하고, 실패한 요청도 분당 제한에 포함될 수 있어 무한 재시도는 악수라고 명시합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff%20.eot?utm_source=openai))

**언제 쓰면 좋은가**
- 사용자 요청이 실시간이지만, *수백 ms~수 초 수준의 지연*을 허용할 수 있는 서비스(챗, 요약, 분류 등)
- 워커/큐 기반으로 처리하지만, 외부 요인(다른 인스턴스, 스파이크) 때문에 429가 간헐적으로 발생하는 환경
- 다중 LLM 공급자(OpenAI/Anthropic/Gemini 등)를 혼용하며 공통 retry 정책이 필요한 경우

**언제 쓰면 안 되는가(혹은 backoff만으로는 부족)**
- “정해진 시간 안에 반드시 응답”해야 하는 하드 리얼타임 성격(이 경우는 *fallback 모델/캐시/결과 재사용*이 우선)
- 429가 “간헐적”이 아니라 “지속적”으로 발생하는데도 무작정 재시도만 하는 경우(= 지연만 늘고 성공률은 그대로)
- 동시성 폭증을 **client-side pacing**(토큰 버킷/슬라이딩 윈도우) 없이 retry로만 해결하려는 경우(큐가 없으면 backoff는 폭탄 돌리기)

---

## 🔧 핵심 개념
### 1) Rate limit은 보통 “요청 수”가 아니라 “요청 수 + 토큰”의 조합이다
OpenAI는 RPM/TPM 등 복수 축으로 제한을 걸고, 모델/조직/프로젝트 단위로 적용될 수 있으며, 일부 모델은 shared limit을 갖습니다. 또한 `max_tokens` 설정이 토큰 제한에 영향을 줄 수 있으니 “최대치로 크게”는 안정성 측면에서 손해입니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff%20.eot?utm_source=openai))  
Anthropic도 RPM + (입력/출력) 토큰 계열로 제한하며, 짧은 구간에서 더 촘촘히(예: 60 RPM이 1 RPS처럼) 적용될 수 있다고 명시합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/api/rate-limits?utm_source=openai))

**실무 함의**
- “요청은 적은데 왜 429?” → 대개 **토큰 축**(혹은 `max_tokens`)이 원인
- “큐로 속도 조절했는데도 429?” → 다중 인스턴스/다중 워커가 **공유 쿼터**를 경쟁하거나, 서버가 더 짧은 버킷으로 쪼개서 보는 경우

### 2) `Retry-After`는 “힌트”가 아니라 사실상 “계약”에 가깝다
Anthropic은 429에서 `retry-after`를 제공하고, 추가로 남은 요청/토큰/리셋 시간 헤더를 제공합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/api/rate-limits?utm_source=openai))  
OpenAI도 rate limit 대응 문서에서 backoff를 권장하면서, 무작정 재전송하면 안 되고(실패도 제한에 기여), 재시도 지연을 늘려야 한다고 설명합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff%20.eot?utm_source=openai))

**핵심 패턴**
1. 응답에 `Retry-After`가 있으면 **최우선으로 존중**
2. 없으면 **exponential backoff + jitter**
3. 둘 다 하더라도, 최종적으로는 **재시도 예산(retry budget)** 을 둬서 “포기”할 줄 알아야 함

### 3) Exponential backoff의 목적은 “성공할 때까지”가 아니라 “동기화된 재시도 폭풍을 깨기”
OpenAI가 지터(jitter)를 강조하는 이유는 여러 클라이언트가 동일한 backoff 곡선을 타면 **같은 타이밍에 다시 몰려** 또 429를 만들기 때문입니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff%20.eot?utm_source=openai))  
즉, backoff는 “운이 좋아지면 성공”이 아니라, **경합을 분산**해 시스템 전체 성공률을 올리는 설계입니다.

### 4) Retry는 ‘오류 분류(classification)’가 80%다
실무에서 안정화가 안 되는 팀은 보통:
- 429, 408, 502/503/504, 네트워크 timeout 등 “transient”를 구분하지 못하거나
- 400/401/403/404 같은 “permanent”에도 재시도하거나
- 429 중에서도 **quota 부족(= 영구적에 가까움)** vs **순간적 rate limit**을 섞어 재시도합니다

---

## 💻 실전 코드
아래 예제는 “toy”가 아니라, **다중 워커/다중 사용자** 환경에서 흔히 필요한 구성(큐 + 글로벌 rate limit + provider별 Retry-After 존중 + 지터 backoff + 관측성)을 한 파일에 담은 실전형 샘플입니다.

### 시나리오
- FastAPI 서버가 유저 요청을 받으면 내부적으로 LLM 호출 작업을 큐에 넣음
- 워커는 **글로벌 토큰 버킷(분산 가능하도록 Redis 사용)** 으로 pacing
- LLM 호출은 429/5xx/timeout에만 재시도
- 429에서는 `Retry-After` 우선, 없으면 exponential backoff + jitter
- 재시도는 **최대 시도 횟수 + 최대 총 대기시간**(budget)으로 제한

#### 1) 의존성/실행
```bash
pip install fastapi uvicorn httpx tenacity redis
# (선택) 로컬 Redis
docker run -p 6379:6379 redis:7
```

#### 2) 코드 (Python)
```python
import asyncio
import os
import random
import time
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis
from tenacity import retry, retry_if_exception, stop_after_attempt

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ---- 간단한 분산 토큰 버킷 (요청 단위) ----
# 실무에서는 "요청 수" + "토큰"을 함께 제어해야 하지만,
# 여기서는 구조를 보여주기 위해 요청 버킷을 예시로 둡니다.
class RedisTokenBucket:
    def __init__(self, redis: Redis, key: str, capacity: int, refill_per_sec: float):
        self.redis = redis
        self.key = key
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec

    async def acquire(self, tokens: int = 1) -> float:
        """
        tokens만큼 바로 쓸 수 있으면 0을 반환.
        부족하면 '기다려야 하는 초'를 반환 (caller가 sleep).
        """
        now = time.time()
        # Lua로 원자적 갱신 (remaining, last_ts)
        lua = """
        local key = KEYS[1]
        local cap = tonumber(ARGV[1])
        local refill = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local need = tonumber(ARGV[4])

        local data = redis.call("HMGET", key, "remaining", "ts")
        local remaining = tonumber(data[1])
        local ts = tonumber(data[2])

        if remaining == nil then
          remaining = cap
          ts = now
        end

        local elapsed = math.max(0, now - ts)
        local refill_amt = elapsed * refill
        remaining = math.min(cap, remaining + refill_amt)
        ts = now

        if remaining >= need then
          remaining = remaining - need
          redis.call("HMSET", key, "remaining", remaining, "ts", ts)
          return 0
        else
          local deficit = need - remaining
          local wait = deficit / refill
          redis.call("HMSET", key, "remaining", remaining, "ts", ts)
          return wait
        end
        """
        wait = await self.redis.eval(lua, 1, self.key, self.capacity, self.refill_per_sec, now, tokens)
        return float(wait)

# ---- 오류 분류 ----
class RetryableError(Exception):
    def __init__(self, status_code: int, retry_after: Optional[float], message: str):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after

def is_retryable(exc: Exception) -> bool:
    return isinstance(exc, RetryableError)

def parse_retry_after(headers: httpx.Headers) -> Optional[float]:
    ra = headers.get("retry-after")
    if not ra:
        return None
    try:
        return float(ra)
    except ValueError:
        return None

async def openai_chat_call(client: httpx.AsyncClient, user_text: str) -> str:
    url = f"{OPENAI_BASE_URL}/responses"
    payload = {
        "model": MODEL,
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": user_text}]}
        ],
        # max_tokens를 과도하게 크게 두면 토큰 축 limit에 먼저 걸릴 수 있음
        "max_output_tokens": 300,
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    try:
        r = await client.post(url, json=payload, headers=headers, timeout=30.0)
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
        raise RetryableError(status_code=0, retry_after=None, message=f"network/timeout: {e}") from e

    if r.status_code == 429:
        raise RetryableError(429, parse_retry_after(r.headers), f"rate limited: {r.text}")
    if r.status_code in (500, 502, 503, 504):
        raise RetryableError(r.status_code, None, f"server error: {r.text}")

    if r.is_error:
        # 4xx 대부분은 재시도해도 해결되지 않는 경우가 많음
        raise HTTPException(status_code=502, detail=f"upstream error {r.status_code}: {r.text}")

    data = r.json()
    # responses API의 output text 합치기(단순화)
    out = []
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") in ("output_text", "text"):
                out.append(c.get("text", ""))
    return "\n".join(out).strip()

def compute_backoff(attempt: int, retry_after: Optional[float]) -> float:
    """
    attempt: 1부터 시작
    Retry-After가 있으면 우선.
    없으면 exp backoff + full jitter.
    """
    if retry_after is not None:
        # Retry-After도 동시 재시도 동기화가 생길 수 있어, 소량의 지터를 추가하는 편이 안전
        return max(0.0, retry_after) + random.uniform(0, 0.25)

    base = 0.5  # seconds
    cap = 20.0  # seconds
    exp = min(cap, base * (2 ** (attempt - 1)))
    # full jitter: [0, exp]
    return random.uniform(0, exp)

async def call_with_budgeted_retry(user_text: str) -> str:
    max_attempts = 6
    max_total_sleep = 30.0  # 전체 지연 예산
    slept = 0.0

    async with httpx.AsyncClient() as client:
        for attempt in range(1, max_attempts + 1):
            try:
                return await openai_chat_call(client, user_text)
            except RetryableError as e:
                if attempt == max_attempts:
                    raise HTTPException(status_code=503, detail=f"LLM unavailable after retries: {e}") from e

                delay = compute_backoff(attempt, e.retry_after)
                if slept + delay > max_total_sleep:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Retry budget exceeded (slept={slept:.1f}s, next={delay:.1f}s): {e}",
                    ) from e

                await asyncio.sleep(delay)
                slept += delay

    raise HTTPException(status_code=503, detail="unreachable")

# ---- 앱: 큐 + 글로벌 rate limit ----
app = FastAPI()
queue: asyncio.Queue[str] = asyncio.Queue()
redis = Redis.from_url(REDIS_URL, decode_responses=True)
bucket = RedisTokenBucket(redis, key="llm:global_rpm", capacity=60, refill_per_sec=1.0)  # 예: 60 RPM ~= 1 RPS

class Req(BaseModel):
    user_id: str
    text: str

@app.on_event("startup")
async def startup():
    asyncio.create_task(worker_loop())

@app.post("/ask")
async def ask(req: Req):
    # 유저별 제한도 보통 별도로 둠(여기서는 생략)
    await queue.put(req.text)
    return {"queued": True, "queue_depth": queue.qsize()}

async def worker_loop():
    while True:
        text = await queue.get()

        # 1) 먼저 "보내도 되는지" pacing (retry보다 앞단!)
        wait = await bucket.acquire(1)
        if wait > 0:
            await asyncio.sleep(wait)

        # 2) 실제 호출은 retry/backoff로 마무리
        try:
            result = await call_with_budgeted_retry(text)
            print("LLM OK:", result[:120])
        except Exception as e:
            print("LLM FAIL:", repr(e))
        finally:
            queue.task_done()
```

#### 예상 동작/출력
- `/ask`로 요청을 여러 개 때려도 워커가 **글로벌 버킷**으로 1차 속도 조절
- 그래도 순간적인 429/5xx가 나면 `Retry-After` 또는 지터 backoff로 2차 완충
- 예산 초과 시 503으로 빠르게 실패(무한 대기 방지)
- 로그에 `LLM OK:` 또는 `LLM FAIL:`가 찍히며, 운영에서는 이를 metrics로 전환

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “Retry”보다 “Pacing(사전 조절)”이 우선이다
StackOverflow/커뮤니티에서 반복적으로 나오는 포인트는, 동시 요청이 한꺼번에 몰리면 backoff는 “지연만 늘리고 결국 경쟁”이 된다는 것입니다. 즉, **큐/토큰버킷/슬라이딩 윈도우** 로 먼저 평탄화하고, retry는 *마지막 안전망*으로 둬야 합니다. ([stackoverflow.com](https://stackoverflow.com/questions/79924021/429-on-vertex-aii-api-calling-nano-banana-pro-3?utm_source=openai))

### Best Practice 2) `Retry-After`/rate limit 헤더를 “관측”하고 정책을 조정하라
Anthropic은 `retry-after` 외에도 remaining/reset 계열 헤더를 제공합니다. 이건 단순 재시도에 쓰는 게 아니라, **대시보드/알람/자동 스로틀링**에 써야 가치가 큽니다. ([docs.anthropic.com](https://docs.anthropic.com/en/api/rate-limits?utm_source=openai))  
(공급자별로 헤더 형태가 다르니, “표준화된 내부 이벤트”로 변환해 로그/메트릭을 쌓는 걸 추천합니다.)

### Best Practice 3) `max_tokens`/출력 상한을 “현실적으로” 잡아라
OpenAI는 토큰 기반 제한이 있으며, `max_tokens`가 제한 소모에 영향을 줄 수 있다고 안내합니다. 응답이 200토큰이면 충분한데 매번 2000으로 열어두면, 동일 RPM에서도 TPM 축으로 먼저 막힙니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff%20.eot?utm_source=openai))

### 흔한 함정/안티패턴
- **인프라 레벨 자동 retry 중복**: LB/SDK/HTTP client가 각자 retry하면 “재시도 폭탄”이 됩니다(애플리케이션에서 한 군데로 통제).
- **429를 전부 같은 429로 취급**: (1) 순간적 rate limit, (2) spend/quota 소진, (3) 특정 엔드포인트/모델의 별도 제한… 해결책이 다릅니다.
- **지터 없는 exponential backoff**: 여러 워커가 같은 곡선을 타면 결국 같은 타이밍에 다시 충돌합니다(OpenAI도 지터를 권장). ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff%20.eot?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- retry를 공격적으로 하면 성공률은 오르지만 **지연/비용**이 늘고, 실패 요청도 rate limit을 소모할 수 있어 **전체 처리량이 오히려 감소**할 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff%20.eot?utm_source=openai))
- 반대로 pacing을 너무 보수적으로 하면 안정적이지만 **p95/p99 latency**가 증가합니다.  
- 실무적으로는 “유저-facing은 짧은 budget(예: 2~6회, 총 10~30초)” + “비동기 배치는 긴 budget”처럼 **워크로드별 정책 분리**가 가장 효과적입니다.

---

## 🚀 마무리
핵심은 하나입니다: **Backoff는 429를 ‘해결’하지 않고, ‘완충’한다.**  
프로덕션 LLM 호출 안정화의 표준 조합은 (1) **사전 pacing(큐/토큰버킷)**, (2) **오류 분류 기반 retry**, (3) **Retry-After 존중 + jitter exponential backoff**, (4) **retry budget로 빠른 포기**, (5) **헤더/지표 기반 관측**입니다. OpenAI는 지터 포함 exponential backoff를 권장하고, Anthropic은 `retry-after` 및 rate limit 헤더를 제공하므로 이를 적극 활용하는 쪽이 2026년 현재 가장 “정답에 가까운” 패턴입니다. ([platform.openai.com](https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff%20.eot?utm_source=openai))

**도입 판단 기준(체크리스트)**
- 429가 “가끔”이면 → backoff 튜닝으로 충분한 경우가 많음
- 429가 “자주/지속적”이면 → backoff가 아니라 **동시성/큐/토큰 상한/모델 선택/티어 업** 문제
- 멀티 인스턴스면 → 로컬 제한이 아니라 **분산 rate limiter(예: Redis)** 가 사실상 필수

**다음 학습 추천**
- 공급자별 rate limit 헤더/쿼터 모델을 정리해 “내부 공통 스키마”로 표준화
- 요청 단위가 아니라 **토큰 단위 예측 기반 limiter**(입력 토큰 추정 + `max_output_tokens`)로 고도화
- fallback 전략(모델 다운그레이드/캐시/결과 재사용)까지 포함한 “SLO 중심 설계”

원하시면 위 코드를 기반으로, (1) 토큰 기반(ITPM/OTPM/TPM)까지 포함한 limiter 확장, (2) OpenAI/Anthropic/Gemini별 헤더 파서 모듈화, (3) Prometheus metrics까지 붙인 프로덕션 템플릿 형태로 더 발전시켜 드릴게요.