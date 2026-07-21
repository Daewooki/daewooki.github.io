---
title: "429가 “가끔”이 아니라 “구조적으로” 터지는 시대: 2026년 7월 LLM API Rate Limit 대응 Retry/Backoff 패턴 심층 분석"
date: 2026-07-21 03:27:37 +0900
categories: [Backend, API]
tags: [backend, api, trend, 2026-07]
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
LLM API를 프로덕션에서 돌리다 보면 429(Too Many Requests / RESOURCE_EXHAUSTED)은 “내가 분당 한도를 넘겼다” 수준의 단순 문제가 아닙니다. **짧은 버스트(burst)로 인한 quantization**, **토큰 기반 제한(TPM/ITPM/OTPM)과 요청 기반 제한(RPM)의 동시 작동**, **조직/워크스페이스 단위 bucket**, **스펜드(spend) 기반 제한**까지 겹치면서 “대시보드상 여유가 있어도 429가 나는” 상황이 흔합니다. OpenAI는 한도가 더 짧은 구간으로 쪼개져 집행될 수 있음을 명시하고, 해결책으로 exponential backoff를 권장합니다. ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai)) Anthropic은 token bucket 기반임을 문서에 적고, 429에 `retry-after`가 포함될 수 있음을 명시합니다. ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits?utm_source=openai)) Google Gemini도 429/503에 대해 exponential backoff(+jitter)를 권장하고, SDK에 기본 retry가 들어있다고 안내합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/troubleshooting?utm_source=openai))

**언제 쓰면 좋은가**
- 멀티 워커/멀티 스레드로 LLM 호출이 몰리는 서비스(에이전트, 배치, 검색+생성 파이프라인)
- 429/503이 “간헐적”이고, 기다리면 대부분 회복되는 트래픽 패턴
- 비용/지연을 약간 늘려서라도 성공률을 끌어올려야 하는 워크로드

**언제 쓰면 안 되는가(혹은 retry를 매우 제한해야 하는가)**
- 사용자 인터랙션이 강한 요청(예: 1~2초 SLA)에서 무제한 retry로 tail latency가 폭발하는 경우
- 400/401/403처럼 **영구 실패(permanent failure)** 인데 무의미하게 재시도하는 경우(키/권한/파라미터 문제)
- “이미 시스템이 과부하”인데 동시 재시도 폭풍으로 더 악화시키는 구조(특히 jitter 없는 backoff)

---

## 🔧 핵심 개념
### 1) Rate limit은 “한 가지 숫자”가 아니다
2026년 기준 주요 LLM API는 보통 **요청 수(RPM)** 와 **토큰(입력/출력 TPM)** 을 동시에 제한합니다. Anthropic은 이를 명시적으로 RPM/ITPM/OTPM으로 설명하고, 내부적으로 token bucket 알고리즘으로 집행한다고 밝힙니다. ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits?utm_source=openai)) OpenAI도 분당 한도라도 더 짧은 시간 단위로 “quantized enforcement” 될 수 있어 순간 버스트에 취약함을 적고 있습니다. ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai))

즉, “분당 60RPM”이어도 실제로는 “초당 1RPS”처럼 동작할 수 있고, 여기에 토큰 제한이 겹치면 **요청 수는 괜찮은데 토큰이 먼저 바닥나서 429**가 나기도 합니다.

### 2) 429의 핵심은 “언제 다시 보내면 되나”다: `Retry-After`
가장 좋은 클라이언트는 429를 받았을 때 **(1) 서버가 주는 `retry-after`를 최우선으로 존중**하고, 없으면 **(2) 지수 backoff + jitter**로 “군집 재시도(thundering herd)”를 피합니다. Anthropic 문서에는 429에 `retry-after`가 포함될 수 있고 “그 전에 재시도하면 실패한다”고 명확히 적혀 있습니다. ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits?utm_source=openai))  
Gemini도 429/503에 대해 exponential backoff(+jitter)를 권장합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/troubleshooting?utm_source=openai))

여기서 중요한 차이:
- **Retry-After 우선 패턴**: “정확히 언제 capacity가 돌아오는지” 서버가 힌트를 주는 경우 최적
- **Exponential backoff 패턴**: 서버 힌트가 없거나, 분산 환경에서 동시 재시도를 완화하는 일반 해법
- **Jitter**: backoff의 필수 구성요소(특히 다중 워커일수록). 같은 수식으로 재시도하면 모두가 같은 타이밍에 다시 몰립니다.

### 3) “재시도”만으로는 부족하다: 클라이언트 측 페이싱(pacing) + 동시성 제어
실전에서 안정화는 보통 2단입니다.

1) **사전 페이싱**: 전역 token bucket / leaky bucket으로 호출을 고르게 분산  
2) **사후 복구**: 429/503 발생 시 retry-after 기반 sleep + exp backoff + jitter

OpenAI가 말하는 “짧은 버스트가 한도 에러를 만든다”는 문제는, retry만으로는 근본 해결이 안 됩니다(계속 버스트를 만들면 계속 맞습니다). ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “현실적인” 시나리오로, **(a) 큐에 쌓이는 작업**을 **(b) 다중 워커가 처리**하되, **(c) 전역 페이싱**과 **(d) 429/503에 대한 retry-after 존중 + exp backoff + jitter**를 함께 적용합니다.

- 언어: Python (FastAPI/worker 어디든 이식 가능)
- 외부 의존성: `httpx`, `tenacity`
- 가정: LLM 공급자는 429에 `Retry-After`를 줄 수도/안 줄 수도 있음(Anthropic은 준다고 명시, Gemini/OpenAI는 상황별) ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits?utm_source=openai))

### 1) 설치/실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install httpx tenacity
```

### 2) “전역 페이서 + 재시도” 워커 구현
```python
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt

# --------- Exceptions ---------
class RetryableLLMError(Exception):
    def __init__(self, status_code: int, retry_after_s: Optional[float], body: str):
        super().__init__(f"retryable llm error status={status_code} retry_after={retry_after_s} body={body[:200]}")
        self.status_code = status_code
        self.retry_after_s = retry_after_s
        self.body = body


# --------- Global pacer (token bucket-ish, simplified) ---------
class GlobalPacer:
    """
    전역 요청 속도를 "부드럽게" 제한하는 페이서.
    - RPM 기반: min_interval = 60 / rpm
    - 여러 워커가 공유할 때도 burst를 줄이기 위해 락으로 직렬화
    """
    def __init__(self, rpm: float):
        self.min_interval = 60.0 / rpm
        self._lock = asyncio.Lock()
        self._next_ts = 0.0

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            if now < self._next_ts:
                await asyncio.sleep(self._next_ts - now)
            # 약간의 랜덤 지터로 동기화 현상 완화(동일 배포 시점/동일 워커 수에서 특히 유효)
            jitter = random.uniform(0.0, 0.05)
            self._next_ts = max(self._next_ts, time.monotonic()) + self.min_interval + jitter


# --------- Backoff policy ---------
@dataclass
class BackoffPolicy:
    base: float = 0.5       # 초기 backoff
    cap: float = 30.0       # 최대 backoff
    jitter: float = 0.25    # +/- 지터 비율
    max_attempts: int = 6   # 너무 길게 늘어지지 않도록 상한


def compute_backoff(policy: BackoffPolicy, attempt_idx: int) -> float:
    # exp backoff: base * 2^attempt
    delay = min(policy.cap, policy.base * (2 ** attempt_idx))
    # jitter: [delay*(1-j), delay*(1+j)]
    j = policy.jitter
    return random.uniform(delay * (1 - j), delay * (1 + j))


# --------- LLM call with retry-after preference ---------
def parse_retry_after(headers: httpx.Headers) -> Optional[float]:
    ra = headers.get("retry-after")
    if not ra:
        return None
    try:
        return float(ra)
    except ValueError:
        # HTTP-date 형태는 여기선 단순화: 필요하면 parsedate_to_datetime로 처리
        return None


async def call_llm_raw(client: httpx.AsyncClient, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = await client.post(url, json=payload, timeout=60.0)
    if r.status_code in (429, 503, 408) or 500 <= r.status_code <= 599:
        raise RetryableLLMError(
            status_code=r.status_code,
            retry_after_s=parse_retry_after(r.headers),
            body=r.text,
        )
    r.raise_for_status()
    return r.json()


def make_retry_decorator(policy: BackoffPolicy):
    async def sleep_fn(retry_state):
        exc = retry_state.outcome.exception()
        attempt = retry_state.attempt_number - 1  # 0-index
        if isinstance(exc, RetryableLLMError) and exc.retry_after_s is not None:
            # 서버가 준 retry-after를 최우선(여기에 작은 지터 추가)
            delay = exc.retry_after_s + random.uniform(0.0, 0.2)
        else:
            delay = compute_backoff(policy, attempt)
        await asyncio.sleep(delay)

    return retry(
        retry=retry_if_exception_type(RetryableLLMError),
        stop=stop_after_attempt(policy.max_attempts),
        reraise=True,
        sleep=sleep_fn,
    )


# --------- Realistic worker ---------
async def worker(name: str, queue: asyncio.Queue, pacer: GlobalPacer, client: httpx.AsyncClient, url: str):
    policy = BackoffPolicy(base=0.7, cap=45.0, jitter=0.3, max_attempts=6)
    retry_call = make_retry_decorator(policy)

    while True:
        job = await queue.get()
        try:
            # 1) 사전 페이싱: 버스트 억제 (OpenAI의 quantization 이슈를 실무에서 가장 많이 줄여줌) ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai))
            await pacer.acquire()

            payload = {
                "input": job["prompt"],
                # 현실 포인트: max tokens를 과하게 잡으면 "예상 사용량"이 커져 rate limit에 불리할 수 있음(OpenAI 권고) ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai))
                "max_output_tokens": job.get("max_output_tokens", 512),
                "temperature": job.get("temperature", 0.2),
                "metadata": {"job_id": job["id"], "worker": name},
            }

            # 2) 사후 복구: 429/503면 retry-after 우선 + exp backoff + jitter (Gemini 권고) ([ai.google.dev](https://ai.google.dev/gemini-api/docs/troubleshooting?utm_source=openai))
            @retry_call
            async def _do():
                return await call_llm_raw(client, url, payload)

            result = await _do()
            print(f"[{name}] done job={job['id']} => keys={list(result.keys())}")

        except RetryableLLMError as e:
            # max_attempts 초과
            print(f"[{name}] FAILED job={job['id']} after retries: {e}")
        except Exception as e:
            # 400/401/403 등은 보통 retry하면 안 됨
            print(f"[{name}] NON-RETRY error job={job['id']}: {e}")
        finally:
            queue.task_done()


async def main():
    # 예: 조직 전체로 120 RPM 정도가 안전한 상황이라고 가정
    pacer = GlobalPacer(rpm=120)

    # 현실 시나리오: 검색/요약/분류 등 비동기 작업이 큐로 쌓임
    queue: asyncio.Queue = asyncio.Queue()
    for i in range(50):
        await queue.put({
            "id": f"doc-{i}",
            "prompt": f"Summarize incident report #{i} with action items and owner.",
            "max_output_tokens": 350,
            "temperature": 0.1
        })

    # LLM endpoint는 예시 URL(프로바이더별로 바꿔 끼우는 구조 권장)
    url = "https://example-llm-provider.com/v1/generate"

    async with httpx.AsyncClient(headers={"Authorization": "Bearer YOUR_KEY"}) as client:
        workers = [
            asyncio.create_task(worker(f"w{i}", queue, pacer, client, url))
            for i in range(6)
        ]
        await queue.join()
        for t in workers:
            t.cancel()

if __name__ == "__main__":
    asyncio.run(main())
```

### 3) 예상 출력(예시)
```text
[w0] done job=doc-0 => keys=['output', 'usage', 'id']
[w3] done job=doc-1 => keys=['output', 'usage', 'id']
[w2] FAILED job=doc-7 after retries: retryable llm error status=429 retry_after=2.0 body=...
...
```

이 코드의 핵심은 “재시도”가 아니라:
- **버스트를 먼저 줄이고(GlobalPacer)**
- 429가 나면 **Retry-After를 가장 먼저 신뢰**하고(Anthropic이 명시) ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits?utm_source=openai))
- 없으면 **지수 backoff + jitter**로 분산시키는 점입니다(Gemini 권고). ([ai.google.dev](https://ai.google.dev/gemini-api/docs/troubleshooting?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “Retry-After 우선, 없으면 exp backoff”를 표준화하라
- Anthropic은 429에 `retry-after`가 오며 “그 전에 재시도하면 실패한다”고 적습니다. ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits?utm_source=openai))  
- 공급자별로 헤더가 없거나 불완전한 경우가 있어, **fallback backoff**가 필요합니다.

**판단 기준**: `retry-after`가 있으면 “내가 계산한 backoff”보다 서버가 더 정확합니다(특히 token bucket reset 타이밍).

### Best Practice 2) 전역(프로세스/클러스터) 단위로 “페이싱”을 걸어라
OpenAI는 분당 한도라도 짧은 구간으로 쪼개 집행되어 버스트에 의해 429가 날 수 있다고 명시합니다. ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai))  
따라서 “429 뜨면 재시도”만으로는 부족하고, 애초에 호출을 고르게 분산해야 합니다.

**현실 팁**
- 단일 인스턴스: 위 예시처럼 락 기반 pacer
- 다중 인스턴스: Redis 기반 전역 token bucket(슬라이딩 윈도우/리키 버킷)로 확장

### Best Practice 3) max_output_tokens(혹은 max_tokens)를 “필요한 만큼만” 잡아라
OpenAI는 max tokens 값이 “예상 사용량”에 영향을 주고, 과도하게 잡으면 rate limit에 불리해질 수 있다고 조언합니다. ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai))  
실무에서는 “대부분 200~400 토큰 나오는데 2000으로 열어둔” 설정이 흔한데, 이게 429 체감 빈도를 올립니다.

---

### 흔한 함정/안티패턴
1) **jitter 없는 exponential backoff**
- 모든 워커가 `1s, 2s, 4s…`로 동시에 깨어나 **재시도 스파이크**를 만듭니다.
- Gemini도 jitter 추가를 권장합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/troubleshooting?utm_source=openai))

2) **429를 무시하고 “즉시 다른 워커로 재시도”**
- 분산 시스템에서 이 패턴은 rate limit을 더 악화시키고, 결국 전체 성공률이 떨어집니다.
- 해결: 같은 job에 대해 “단일 플라이트(single-flight)” + 중앙 재시도 정책

3) **재시도 대상 오류를 넓게 잡기**
- 400/401/403 같은 클라이언트 오류는 retry로 해결되지 않습니다.
- 429/408/5xx 위주로 제한하고, 공급자 문서가 명시한 코드만 허용하는 편이 안전합니다(Gemini 가이드도 “특정 에러만 재시도” 권장). ([ai.google.dev](https://ai.google.dev/gemini-api/docs/troubleshooting?utm_source=openai))

---

### 비용/성능/안정성 트레이드오프
- **안정성↑**: 페이싱 + backoff + jitter + retry-after 준수
- **지연(latency)↑**: 특히 429 구간에서 tail latency가 늘어납니다(사용자 요청 경로면 더 치명적)
- **비용↑/↓ 둘 다 가능**
  - 재시도 자체는 호출 수를 늘려 비용↑
  - 반대로 “불필요한 max tokens 축소”로 토큰 비용↓ 가능(OpenAI 조언) ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai))

실무적으로는 “대화형(온라인) 경로”는 재시도를 1~2회로 제한하고, “비동기 배치/큐”에서 충분히 재시도하는 **경로 분리**가 가장 안전합니다.

---

## 🚀 마무리
정리하면 2026년 7월 기준 LLM API 안정화의 핵심은 “429가 나면 잠깐 기다리자”가 아니라:

1) **버스트를 없애는 전역 페이싱**(quantization/짧은 구간 집행 대응) ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai))  
2) **Retry-After가 있으면 최우선 준수**(특히 Anthropic은 명시) ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits?utm_source=openai))  
3) 없으면 **exponential backoff + jitter**(Gemini 포함 다수 가이드가 권장) ([ai.google.dev](https://ai.google.dev/gemini-api/docs/troubleshooting?utm_source=openai))  
4) **max tokens를 현실적으로 줄여** 토큰 기반 제한과 비용을 같이 관리 ([help.openai.com](https://help.openai.com/en/articles/6891753-api-rate-limit-advice?utm_source=openai))

**도입 판단 기준**
- 동시성(워커 수)과 트래픽 버스트가 존재한다 → “retry만” 말고 “pacer+retry”로 가야 합니다.
- 429가 하루 종일 지속된다/즉시 429가 난다 → 단순 backoff로는 해결이 안 될 수 있으니, 키/조직/티어/스펜드 제한/엔드포인트 특이 제한을 함께 점검해야 합니다(Gemini는 spend 기반 429도 문서화). ([ai.google.dev](https://ai.google.dev/gemini-api/docs/rate-limits?authuser=2&utm_source=openai))

**다음 학습 추천**
- 공급자별 rate limit 헤더/Limit API를 읽고(Anthropic은 Rate Limits API와 헤더를 문서화) ([platform.claude.com](https://platform.claude.com/docs/en/api/rate-limits?utm_source=openai)), 내 서비스에 맞는 “전역 페이싱(분산 레이트리미터)”를 설계해보세요.
- 장기적으로는 “클라이언트 측 제어 알고리즘” 연구도 흥미롭습니다(백오프 대비 429를 크게 줄이는 접근을 다루는 최근 연구가 나와 있습니다). ([arxiv.org](https://arxiv.org/abs/2510.04516?utm_source=openai))