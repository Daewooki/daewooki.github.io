---
title: "429 한 번에 서비스가 무너진다: LLM API rate limit 안정화(retry/backoff) 패턴 심층 분석"
description: "LLM API를 “프로덕션 트래픽”으로 돌리기 시작하면, 기능 버그보다 먼저 터지는 게 rate limit(429) + 일시 장애(5xx) + 재시도 폭풍(retry storm) 입니다."
date: 2026-08-21 01:45:51 +0900
categories: [Backend, API]
tags: [backend, api]
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
LLM API를 “프로덕션 트래픽”으로 돌리기 시작하면, 기능 버그보다 먼저 터지는 게 **rate limit(429) + 일시 장애(5xx) + 재시도 폭풍(retry storm)** 입니다. 특히 배치/에이전트/워크플로우처럼 **동시성이 자연스럽게 올라가는 구조**에서는, 재시도 로직이 빈약하면 “조금 느려지는” 수준이 아니라 **전체 큐가 막히고 비용만 새는** 상황으로 이어집니다.

이 글이 해결하는 문제는 딱 두 가지입니다.

- **429/5xx가 나와도 전체 파이프라인을 안정적으로 완주**하게 만들기  
- 재시도가 오히려 트래픽을 증폭시키는 **thundering herd(동시 재시도)와 비용 폭탄**을 막기

언제 쓰면 좋나?
- 워커/큐 기반 비동기 처리, agent fan-out, 다수 사용자 동시 호출, 멀티 모델/멀티 벤더 라우팅
- “가끔 429가 난다”가 아니라, **피크 시에 반드시 429가 나는** 구조(= 설계상 정상)

언제 쓰면 안 되나?
- 단일 요청-응답의 짧은 흐름에서 “무조건 재시도”는 UX를 망칩니다. (예: 사용자 대기시간이 SLA인 채팅)
- **4xx(잘못된 파라미터/권한/정책 위반)**를 재시도하는 건 낭비입니다. OpenAI/Gemini/Anthropic 모두 “재시도 대상 선별”을 강조합니다.[^1]

---

## 🔧 핵심 개념
### 1) LLM rate limit은 “요청 수”가 아니라 “복수 버킷”이다
요즘 LLM API rate limit은 대개 단일 RPM이 아니라 **여러 차원의 버킷**으로 구성됩니다. Anthropic은 예를 들어 **RPM / Input TPM / Output TPM** 같은 3축을 명시하고, 초과 시 429와 함께 `retry-after`를 내려줍니다.[^2]  
즉 “요청 수를 줄였는데도 429가 난다”가 흔합니다. **토큰 폭증(긴 prompt, 큰 max_tokens, 예상보다 긴 출력)**이 원인이 될 수 있습니다. OpenAI도 max tokens 설정이 rate limit 추정에 영향을 줄 수 있다고 안내합니다.[^1]

**실무 결론**
- retry/backoff는 “마지막 방어선”이고, 그 전에 **요청 크기/동시성/토큰 예산**으로 1차 제어를 해야 합니다.

### 2) 2026년형 retry 우선순위: Retry-After → Reset 헤더 → backoff(+jitter)
여러 벤더의 공식 문서가 공통으로 암시하는 바는:
- 서버가 **기다리라고 알려주면(Retry-After)** 그걸 최우선으로 따르는 게 가장 효율적입니다. Anthropic은 429에서 `retry-after`를 제공한다고 명확히 말합니다.[^2]  
- Gemini도 429/5xx 같은 transient 에러에 대해 **exponential backoff + jitter**를 권장하고, 공식 SDK가 기본 retry를 수행한다고 안내합니다.[^3]  
- OpenAI는 429 대응으로 **exponential backoff**를 공식 베스트 프랙티스로 안내합니다.[^1]  

그리고 2026년 들어 “단순 backoff”만으로는 부족하다는 분석도 많습니다. 멀티 프로바이더 라우팅/페일오버 환경에서는 **비동기 exponential backoff + jitter**가 없으면 fallback API에 재시도 폭풍이 몰려 연쇄 장애가 난다는 시스템 연구도 나옵니다.[^4]

정리하면, 지켜야 할 순서는:

1. **Retry-After가 있으면 그 시간(+작은 jitter)만큼 대기**
2. Retry-After가 없지만 reset 계열 헤더가 있으면 **reset 시각까지 대기**
3. 아무 힌트가 없으면 **exponential backoff + jitter**
4. 재시도 횟수/총 대기시간 상한을 둬서 “영원히 재시도”를 막기

### 3) 왜 jitter가 필수인가 (단순 “권장”이 아니라 “구조적 필요”)
동시에 100개 워커가 429를 맞으면, 모두가 1초 후에 동시에 재시도합니다. 그러면 다시 429 → 다시 동시 재시도… 이게 **retry storm**입니다.  
Gemini 공식 가이드는 jitter를 넣어 “동시에 재시도하지 않게” 하라고 명시합니다.[^3]

**실무 결론**
- “exponential backoff”는 최소 요건이고, **jitter 없는 backoff는 거의 안 한 것과 비슷**한 상황이 흔합니다(특히 큐/배치).

---

## 💻 실전 코드
아래 예제는 “toy”가 아니라, 실제로 운영에서 쓰는 형태를 그대로 가져온 패턴입니다.

- Python + asyncio 기반 워커
- 공통 retry 래퍼(429/5xx만 재시도)
- `Retry-After` 우선
- **동시성 제한(세마포어) + per-host 커넥션 풀**
- idempotency key(가능할 때)로 중복 과금/중복 작업 위험 완화
- 관측(재시도 횟수/대기시간)을 로그로 남김

### 1) 셋업
```bash
python -m venv .venv
source .venv/bin/activate
pip install httpx tenacity
```

### 2) 프로덕션 지향 retry/backoff 래퍼 + 워커 풀
```python
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

@dataclass
class RetryPolicy:
    max_attempts: int = 6
    base_delay_s: float = 0.8
    max_delay_s: float = 30.0
    # 전체 요청에 대해 "무한 대기" 방지용 (SLA/큐 적체 방지)
    max_total_sleep_s: float = 60.0

def _parse_retry_after_seconds(resp: httpx.Response) -> Optional[float]:
    ra = resp.headers.get("retry-after")
    if not ra:
        return None
    try:
        return float(ra)
    except ValueError:
        # HTTP-date 형식인 경우도 있으나, LLM 벤더들은 대체로 seconds를 씀.
        return None

def _full_jitter_delay(policy: RetryPolicy, attempt_idx: int) -> float:
    # Full Jitter: min(cap, base * 2^n) 범위에서 랜덤
    cap = min(policy.max_delay_s, policy.base_delay_s * (2 ** attempt_idx))
    return random.random() * cap

async def call_llm_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    policy: RetryPolicy,
) -> dict[str, Any]:
    slept = 0.0

    for attempt in range(policy.max_attempts):
        t0 = time.time()
        try:
            resp = await client.post(url, headers=headers, json=payload)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            # 네트워크/타임아웃은 transient로 간주
            resp = None
            err = e
        else:
            err = None

        # 성공
        if resp is not None and 200 <= resp.status_code < 300:
            return resp.json()

        # 재시도 불가(대부분 4xx)
        if resp is not None and resp.status_code not in RETRYABLE_STATUS:
            raise RuntimeError(f"Non-retryable error {resp.status_code}: {resp.text[:500]}")

        # 마지막 시도면 종료
        if attempt == policy.max_attempts - 1:
            if resp is None:
                raise RuntimeError(f"Failed after retries (network): {err}")
            raise RuntimeError(f"Failed after retries ({resp.status_code}): {resp.text[:500]}")

        # 1순위: Retry-After 존중
        delay = None
        if resp is not None and resp.status_code == 429:
            ra = _parse_retry_after_seconds(resp)
            if ra is not None:
                # 작은 jitter로 동시성 파동 완화
                delay = ra + random.random() * 0.25

        # 2~3순위: 없으면 지터 포함 exponential backoff
        if delay is None:
            delay = _full_jitter_delay(policy, attempt)

        # 총 sleep 상한
        if slept + delay > policy.max_total_sleep_s:
            raise RuntimeError(
                f"Retry budget exceeded: slept={slept:.2f}s, next_delay={delay:.2f}s"
            )

        dt = time.time() - t0
        status = "network_error" if resp is None else str(resp.status_code)
        print(
            f"[retry] attempt={attempt+1}/{policy.max_attempts} "
            f"status={status} req_time={dt:.2f}s sleep={delay:.2f}s"
        )
        await asyncio.sleep(delay)
        slept += delay

    raise AssertionError("unreachable")

async def worker(name: str, sem: asyncio.Semaphore, client: httpx.AsyncClient, job: dict[str, Any]):
    async with sem:
        url = job["url"]
        headers = job["headers"]
        payload = job["payload"]

        # 가능하면 idempotency key를 넣어 “재시도 중복 처리” 위험을 줄입니다.
        # (벤더/엔드포인트가 지원할 때만 의미가 있음)
        headers = dict(headers)
        headers.setdefault("Idempotency-Key", job["idempotency_key"])

        data = await call_llm_with_retry(
            client=client,
            url=url,
            headers=headers,
            payload=payload,
            policy=RetryPolicy(),
        )
        # 현실적인 후처리: 결과 저장/큐 ack 등을 여기서 수행
        return {"job_id": job["job_id"], "output": data}

async def main():
    # 동시성은 “내 서버” 기준이 아니라 “벤더 rate limit + 토큰 예산” 기준으로 잡아야 함
    concurrency = 8
    sem = asyncio.Semaphore(concurrency)

    timeout = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
    limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        jobs = []
        for i in range(50):
            jobs.append(
                {
                    "job_id": f"batch-{i}",
                    "idempotency_key": f"batch-{i}-v1",
                    "url": "https://api.vendor.example/v1/chat/completions",
                    "headers": {
                        "Authorization": "Bearer $TOKEN",
                        "Content-Type": "application/json",
                    },
                    "payload": {
                        "model": "your-model",
                        "messages": [
                            {"role": "system", "content": "You are a coding assistant."},
                            {"role": "user", "content": f"Summarize log chunk #{i} and extract error causes."},
                        ],
                        # max_tokens는 “예상 출력”과 맞추는 게 rate limit 안정화에 도움
                        # (불필요하게 크게 잡으면 rate limit 추정/버킷에 불리)
                        "max_tokens": 350,
                    },
                }
            )

        results = await asyncio.gather(*(worker("w", sem, client, j) for j in jobs), return_exceptions=True)

        ok = sum(1 for r in results if not isinstance(r, Exception))
        fail = len(results) - ok
        print(f"done: ok={ok}, fail={fail}")

if __name__ == "__main__":
    asyncio.run(main())
```

**예상 출력(예시)**
- 429가 발생하면 `Retry-After` 기반으로 대기하거나, 없으면 jittered backoff로 점진 증가
- 과도한 재시도로 총 대기 예산을 넘기면 빠르게 실패 처리(큐 재스케줄 등으로 넘기는 게 일반적으로 낫습니다)

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “재시도”보다 “사전 스로틀링”이 더 싸고 안정적
OpenAI는 429 회피를 위해 max tokens를 현실적으로 잡고(=불필요한 토큰 예산 제거), 필요하면 usage tier/limits 자체를 올리라고 안내합니다.[^1]  
Anthropic은 rate limit이 다중 버킷(RPM/ITPM/OTPM)임을 명시합니다.[^2]  
→ 즉, 운영에서는 **(1) 동시성 캡 + (2) 토큰 예산 캡 + (3) 큐 페이싱**이 1차 방어선이고, retry/backoff는 2차 방어선입니다.

### Best Practice 2) 429는 “내가 잘못”과 “서버가 바쁨”이 섞여 있다
Gemini/Anthropic 문서 모두 429를 transient로 보고 재시도를 권장하지만, 429의 원인은:
- **진짜 quota/rate limit 초과**
- 특정 엔드포인트/모델의 **일시적인 capacity 문제**
처럼 다를 수 있습니다. 그래서 429가 계속 나면 “재시도만 늘리기”보다:
- **동시성/토큰을 더 줄이고**
- 헤더가 주는 신호(`retry-after`)를 최우선으로 따르고[^2]
- 필요하면 **다른 모델/리전/벤더로 failover**(단, failover에도 backoff+jitter 필수)[^4]
로 접근해야 합니다.

### 함정 1) linear backoff / 고정 sleep
1초 고정 sleep은 피크 구간에서 동기화 파동을 만들기 쉽습니다. Gemini는 jitter를 넣으라고 명시합니다.[^3]  
→ 최소한 **Full Jitter**(위 코드) 또는 **Decorrelated Jitter**를 쓰세요.

### 함정 2) “모든 에러 재시도”
400/401/403 같은 클라이언트 에러를 재시도하면 비용만 낭비합니다. Gemini 가이드는 transient 에러(429/5xx 등)만 재시도하라고 권장합니다.[^3]  
→ “retryable classification”을 코드에 박아 넣고, 로깅/메트릭으로 관측하세요.

### 트레이드오프) 안정성 vs 지연 vs 비용
- 재시도를 늘리면 성공률은 오르지만 **지연(latency)** 과 **비용(중복 요청)** 이 증가합니다.
- 그래서 “최대 시도 횟수”보다 더 중요한 건 **retry budget(총 대기/총 시도 상한)** 입니다.
- 대규모 배치에서는 “한 작업을 오래 붙잡고 재시도”하기보다 **빠르게 실패 → 큐에 재투입(지수적 재예약)**이 전체 처리량에 유리한 경우가 많습니다.

---

## 🚀 마무리
핵심은 하나입니다. **LLM API 안정화는 ‘retry 코드’가 아니라 ‘트래픽 형태를 다듬는 설계’**입니다.

도입 판단 기준(체크리스트):
- 429/5xx가 월 1회라도 나오면: **Retry-After 우선 + backoff+jitter + retry budget**은 바로 넣을 가치가 있습니다.[^1]
- 동시 워커/배치/agent fan-out이 있다면: jitter 없는 backoff는 사실상 미도입에 가깝습니다.
- 멀티 벤더 failover를 고려한다면: backoff+jitter 없이는 **연쇄 retry storm** 위험이 커집니다.[^4]

다음 학습 추천:
- 각 벤더의 rate limit 헤더/에러 타입을 더 정교하게 해석해 **“사전 스로틀링(remaining/reset 기반)”**으로 확장(Anthropic은 `retry-after` 및 rate limit 헤더 기반 스로틀링을 강조하는 문서들이 있습니다).[^2]
- 멀티 리전/멀티 모델 라우팅을 쓴다면, “재시도”가 아니라 **부하 분산 + admission control**까지 포함한 설계를 검토(최근 시스템 연구 흐름도 이 방향입니다).[^5]

[^1]: <https://help.openai.com/en/articles/6891753-rate-limit-advice>
[^2]: <https://support.anthropic.com/en/articles/8243635-our-approach-to-api-rate-limits>
[^3]: <https://ai.google.dev/gemini-api/docs/troubleshooting>
[^4]: <https://arxiv.org/abs/2607.15899>
[^5]: <https://arxiv.org/abs/2510.04516>
