---
title: "429 한 번에 무너지지 않는 LLM API: 2026년 4월 기준 rate limit retry/backoff 패턴 실전 설계"
date: 2026-04-23 03:34:36 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-04]
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
LLM API를 프로덕션에서 돌리면 “가끔”이 아니라 “언젠가 반드시” `429 Too Many Requests`(rate limit)와 간헐적 `5xx/overload`를 만납니다. 문제는 대부분의 팀이 **retry를 단순 루프**로 넣고 끝내서, 트래픽이 몰릴 때 **thundering herd(동시 재시도 폭주)** 를 스스로 만들어 장애를 증폭시킨다는 겁니다. AWS는 오래전부터 이를 막기 위해 **exponential backoff + jitter**를 표준 패턴으로 권장해 왔고, retry는 스택의 “한 지점”에서만 수행하라고 강조합니다. ([aws.amazon.com](https://aws.amazon.com/es/blogs/architecture/exponential-backoff-and-jitter/?utm_source=openai))

**언제 쓰면 좋은가**
- 멀티 워커/멀티 스레드로 LLM 호출이 병렬로 발생하고, 피크 트래픽에서 429가 종종 나는 서비스(챗봇, RAG, 에이전트, 배치 요약 등)
- “요청 성공률”이 SLO에 중요하고, 약간의 지연(수백 ms~수 초)을 감수해도 되는 기능
- API 제공자가 `Retry-After` 또는 rate limit reset 힌트를 주는 경우(Anthropic은 429에 `retry-after` 및 reset 헤더들을 제공) ([docs.anthropic.com](https://docs.anthropic.com/en/api/rate-limits?utm_source=openai))

**언제 쓰면 안 되는가(혹은 매우 조심)**
- 사용자 인터랙션이 “즉시성”이 핵심(예: 입력마다 스트리밍으로 즉시 응답)인데, retry로 대기 시간이 길어질 수 있는 경우 → **fallback 모델/캐시/부분 응답**이 더 낫습니다.
- idempotency가 없는 “부작용 요청”을 무작정 재시도하는 경우(결제/저장/티켓 발행 등) → Stripe는 idempotency key를 통한 안전한 재시도를 강하게 전제합니다. ([docs.stripe.com](https://docs.stripe.com/error-low-level?locale=en-GB&utm_source=openai))
- “각 호출마다” 라이브러리 retry + “상위 레이어에서도” retry를 또 하는 중복 구조 → retry 증폭(재시도 폭탄)로 이어집니다. ([aws.amazon.com](https://aws.amazon.com/ar/builders-library/timeouts-retries-and-backoff-with-jitter/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Rate limit은 “QPS”만이 아니다: 다차원 제한
LLM은 보통 **RPM/TPM(요청/토큰)** 같이 다차원 rate limit이 있고, 429는 “요청 수가 많아서”만이 아니라 **토큰 폭주/동시성/서버 보호**로도 발생합니다. Gemini 쪽은 429가 `RESOURCE_EXHAUSTED`로 나타나며 `Retry-After`를 힌트로 주는 케이스가 언급됩니다. ([aifreeapi.com](https://www.aifreeapi.com/en/posts/gemini-api-rate-limit-explained?utm_source=openai))  
Anthropic도 429에 어떤 limit을 넘었는지와 함께 `retry-after` 및 reset 정보를 제공합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/api/rate-limits?utm_source=openai))

### 2) “Retry-After 우선” + “지수 백오프 + jitter”가 기본 골격
패턴의 핵심 흐름은 이렇습니다.

1. **에러 분류(Error classification)**  
   - 재시도 가치가 있는 것: `429`, 일시적 네트워크 오류, 일부 `5xx`, (벤더가 명시하는) overload 계열  
   - 재시도하면 안 되는 것: `400/401/403` 같은 영구 오류, validation 오류, 모델/파라미터 오류 등
2. **서버 힌트 존중(Server hint first)**  
   - 응답에 `Retry-After`(초 단위)가 있으면 **그 값을 최우선**으로 사용  
3. **백오프(Backoff)**  
   - 힌트가 없거나 최소 대기만 준다면: `base * 2^attempt` 형태로 증가 + cap(상한)
4. **jitter(무작위성)**  
   - AWS는 jitter가 없으면 재시도가 한 타이밍에 몰려 다시 제한에 걸리는 “군집”이 생긴다고 설명합니다. 이를 풀기 위해 **Full Jitter / Equal Jitter / Decorrelated Jitter** 같은 변형을 소개합니다. ([aws.amazon.com](https://aws.amazon.com/es/blogs/architecture/exponential-backoff-and-jitter/?utm_source=openai))
5. **retry budget / deadline(총 재시도 예산)**  
   - 재시도는 성공률을 올리지만 시스템 부하를 늘립니다. 그래서 “최대 시도 횟수”뿐 아니라 **총 대기 시간(예: 20초)** 또는 요청 단위 SLO에 맞춘 **deadline**이 필요합니다. (retry budget 개념은 최근 분산시스템 글에서도 강조됩니다.) ([systemoverflow.com](https://www.systemoverflow.com/learn/distributed-primitives/idempotency/retry-policies-exponential-backoff-jitter-and-budgets?utm_source=openai))

### 3) “Queue + client-side rate limiter”가 retry보다 먼저다
retry는 “사후 대응”입니다. 더 큰 효과는 **사전 페이싱(pacing)** 입니다.
- 프로세스/클러스터 전체에서 공유하는 **token bucket(또는 sliding window)** 로 호출을 평탄화
- 큐(예: Redis, SQS)로 스파이크를 흡수하고 worker 수를 조절  
이렇게 해야 429가 “가끔” 수준으로 내려가고, retry는 그 잔여 케이스만 처리합니다.

---

## 💻 실전 코드
아래 예제는 “유저별 챗 기능”을 운영하면서, 내부적으로는 **전역(서비스 전체) 페이싱 + 429/5xx 재시도 + 관측(로그/메트릭)** 을 갖춘 형태입니다.  
(언어는 Python, 실행 단위는 FastAPI/worker 어디든 붙일 수 있는 “호출 유틸”로 구성)

### 1단계: 의존성/설정
```bash
pip install httpx tenacity pydantic-settings
```

환경변수(예시):
```bash
export LLM_API_KEY="..."
export LLM_BASE_URL="https://api.vendor.example"  # OpenAI/Anthropic/Gemini 등으로 교체
```

### 2단계: 전역 rate limiter(간단 토큰버킷) + backoff 래퍼
```python
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx


@dataclass
class TokenBucket:
    # 간단한 in-process 토큰 버킷 (멀티 인스턴스면 Redis 등으로 확장 권장)
    rate_per_sec: float
    capacity: int

    def __post_init__(self):
        self._tokens = float(self.capacity)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now

            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_sec)

            if self._tokens >= tokens:
                self._tokens -= tokens
                return

            need = tokens - self._tokens
            wait = need / self.rate_per_sec
            # lock 밖에서 자는게 이상적이지만, 단순화를 위해 여기서 처리
            await asyncio.sleep(wait)
            self._tokens = 0.0


def parse_retry_after(headers: httpx.Headers) -> Optional[float]:
    ra = headers.get("retry-after")
    if not ra:
        return None
    try:
        return float(ra)
    except ValueError:
        return None


def full_jitter_delay(base: float, cap: float, attempt: int) -> float:
    # AWS가 소개한 "Full Jitter" 아이디어: 0..min(cap, base*2^attempt) 사이 랜덤 ([aws.amazon.com](https://aws.amazon.com/es/blogs/architecture/exponential-backoff-and-jitter/?utm_source=openai))
    upper = min(cap, base * (2 ** attempt))
    return random.random() * upper


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        bucket: TokenBucket,
        timeout_sec: float = 30.0,
        max_retries: int = 6,
        base_backoff: float = 0.5,
        cap_backoff: float = 20.0,
        total_deadline_sec: float = 25.0,
    ):
        self.bucket = bucket
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.cap_backoff = cap_backoff
        self.total_deadline_sec = total_deadline_sec

        self.http = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_sec),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def close(self):
        await self.http.aclose()

    def _is_retryable(self, status: int) -> bool:
        # 벤더별로 조정: 429 + (일부) 5xx를 retry 대상으로
        return status == 429 or status in (500, 502, 503, 504)

    async def chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        start = time.monotonic()
        last_err: Optional[Tuple[int, str]] = None

        for attempt in range(self.max_retries):
            # 1) 사전 페이싱: 전역 버킷으로 호출 평탄화
            await self.bucket.acquire(1.0)

            try:
                resp = await self.http.post("/v1/chat/completions", json=payload)
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                # 네트워크 계열은 retry 후보
                last_err = (-1, repr(e))
                delay = full_jitter_delay(self.base_backoff, self.cap_backoff, attempt)
            else:
                if 200 <= resp.status_code < 300:
                    return resp.json()

                body = resp.text[:500]
                last_err = (resp.status_code, body)

                if not self._is_retryable(resp.status_code):
                    # 영구 오류는 즉시 실패
                    raise RuntimeError(f"LLM call failed: {resp.status_code} {body}")

                # 2) Retry-After 우선
                ra = parse_retry_after(resp.headers)
                if ra is not None:
                    # retry-after를 그대로 따르면 동시 재시도 군집이 생길 수 있어,
                    # 아주 작은 jitter(예: 0~10%)만 추가하는 전략을 자주 씁니다.
                    delay = ra * (1.0 + random.random() * 0.1)
                else:
                    delay = full_jitter_delay(self.base_backoff, self.cap_backoff, attempt)

            # 3) deadline(총 예산) 확인
            elapsed = time.monotonic() - start
            if elapsed + delay > self.total_deadline_sec:
                break

            await asyncio.sleep(delay)

        raise RuntimeError(f"LLM retry exhausted. last_err={last_err}")
```

### 3단계: “현실적인 시나리오”에 붙이기 (동시 요청 + 관측 포인트)
```python
import asyncio
from collections import Counter

async def main():
    bucket = TokenBucket(rate_per_sec=5.0, capacity=10)  # 서비스 전체를 5 RPS로 평탄화
    client = LLMClient(
        api_key="YOUR_KEY",
        base_url="https://api.vendor.example",
        bucket=bucket,
        max_retries=6,
        total_deadline_sec=25.0,
    )

    payload = {
        "model": "some-llm-model",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "지난 24시간 에러 로그를 요약하고 원인 가설 3개를 제시해줘."},
        ],
        "temperature": 0.2,
    }

    # 피크 상황을 흉내: 30개 동시 호출
    results = Counter()

    async def worker(i: int):
        try:
            _ = await client.chat(payload)
            results["ok"] += 1
        except Exception as e:
            results["fail"] += 1
            # 여기서 e를 구조화 로깅(요청ID, attempt, delay, status)으로 남기는 게 핵심
            print(f"[{i}] fail: {e}")

    await asyncio.gather(*[worker(i) for i in range(30)])
    await client.close()
    print("summary:", dict(results))

if __name__ == "__main__":
    asyncio.run(main())
```

**예상 출력(상황에 따라 달라짐)**
- 정상이라면 `summary: {'ok': 30}`  
- 제한이 빡빡하면 일부는 deadline 내 실패: `{'ok': 26, 'fail': 4}`  
이때 중요한 건 “fail이 0이냐”보다, **fail이 어떤 이유로/어떤 구간에서/어떤 비율로** 발생하는지 관측 가능해야 한다는 점입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) `Retry-After`는 “존중하되, 미세 jitter로 분산”
Anthropic처럼 `retry-after`를 주는 API는 그 값을 따르는 게 기본입니다. ([docs.anthropic.com](https://docs.anthropic.com/en/api/rate-limits?utm_source=openai))  
다만 워커가 많으면 모두가 같은 시간에 깨어나 다시 429를 맞을 수 있으니, **0~10% 정도의 작은 jitter**를 얹는 패턴이 실무적으로 안정적입니다(너무 큰 jitter는 회복을 늦춥니다).

### Best Practice 2) retry는 한 레이어에서만 + total deadline을 걸어라
AWS Builders’ Library는 retry를 “스택의 단일 지점”에서 수행하라고 권합니다. ([aws.amazon.com](https://aws.amazon.com/ar/builders-library/timeouts-retries-and-backoff-with-jitter/?utm_source=openai))  
SDK retry + 앱 retry + 잡큐 retry가 겹치면, 장애 시 트래픽이 기하급수로 불어납니다.  
- **해결책**: (1) 어디에서 retry할지 한 군데만 정하고 (2) 요청별 **총 시간 예산(total deadline)** 을 둡니다.

### Best Practice 3) idempotency 없는 “쓰기” 요청은 키 설계를 먼저
LLM 호출 자체는 대부분 읽기/계산이지만, “LLM 결과를 DB에 저장” 같은 파이프라인에서는 중복 저장이 터집니다. Stripe는 idempotency key가 재시도의 안전장치임을 명확히 설명하고, 429는 idempotency 계층보다 앞에서 발생할 수도 있다고 언급합니다. ([docs.stripe.com](https://docs.stripe.com/error-low-level?locale=en-GB&utm_source=openai))  
- **권장**: `request_id`(예: ULID)로 결과 저장을 UPSERT로 만들고, “같은 입력이면 같은 키”가 되게 설계하세요.

### 흔한 함정/안티패턴
- **고정 sleep(예: 1초)로 무한 retry**: 회복도 느리고, 회복 순간에 폭주합니다.
- **jitter 없는 exponential backoff**: AWS가 보여준 것처럼 호출이 “덩어리”로 몰립니다. ([aws.amazon.com](https://aws.amazon.com/es/blogs/architecture/exponential-backoff-and-jitter/?utm_source=openai))
- **429를 모두 같은 원인으로 취급**: 어떤 벤더는 “프로젝트 quota”, 어떤 곳은 “서버 overload”, 어떤 곳은 “토큰 제한”이 섞입니다. 429의 body/헤더(가능하면 reset 시각)를 파싱해 원인을 분리해야 합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/api/rate-limits?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **안정성↑**: 더 많은 retry, 더 큰 backoff cap, 더 긴 deadline
- **지연↑**: 사용자 체감이 나빠질 수 있음 → UI 레벨에서 “재시도 중” 표시, 비동기 처리, fallback 모델 고려
- **비용↑ 가능**: 실패 후 재시도 자체는 호출 수를 늘립니다. 그래서 “사전 페이싱 + retry budget”이 같이 가야 합니다. ([systemoverflow.com](https://www.systemoverflow.com/learn/distributed-primitives/idempotency/retry-policies-exponential-backoff-jitter-and-budgets?utm_source=openai))

---

## 🚀 마무리
핵심은 “429가 났을 때 재시도”가 아니라, **(1) 먼저 호출을 평탄화하고 (2) 그래도 생기는 429/일시적 오류를 Retry-After + exponential backoff + jitter로 흡수하며 (3) deadline과 단일 retry 레이어로 증폭을 막는 것**입니다. AWS는 jitter의 필요성과 다양한 jitter 알고리즘(Full/Equal/Decorrelated)을 정리했고, Anthropic은 429에서 `retry-after` 및 reset 힌트를 제공하는 등 “서버 힌트를 우선하라”는 방향이 뚜렷합니다. ([aws.amazon.com](https://aws.amazon.com/es/blogs/architecture/exponential-backoff-and-jitter/?utm_source=openai))

**도입 판단 기준(빠른 체크리스트)**
- 피크 때 동시 요청이 10개 이상인가? → jitter 없는 retry는 위험
- 429가 주 1회 이상 보이는가? → 사전 rate limiter + 큐를 먼저
- 사용자 요청 SLO(예: p95 2s)가 빡빡한가? → retry보다 fallback/비동기화를 더 고민
- 부작용(write)이 있는가? → idempotency key/UPSERT 없으면 retry 금지

**다음 학습 추천**
- AWS “Exponential Backoff And Jitter”로 jitter 선택(Full vs Decorrelated) 기준 잡기 ([aws.amazon.com](https://aws.amazon.com/es/blogs/architecture/exponential-backoff-and-jitter/?utm_source=openai))
- AWS Builders’ Library “Timeouts, retries, and backoff with jitter”로 retry를 어디에 둘지(단일 지점) 설계 원칙 정리 ([aws.amazon.com](https://aws.amazon.com/ar/builders-library/timeouts-retries-and-backoff-with-jitter/?utm_source=openai))
- 사용하는 LLM 벤더의 429 헤더/에러 스키마(예: Anthropic rate limit 헤더) 파싱해서 “원인별 정책”으로 세분화 ([docs.anthropic.com](https://docs.anthropic.com/en/api/rate-limits?utm_source=openai))