---
title: "LLM 백엔드 “Queued Forever”를 끝내는 법: Celery + Redis 비동기 워커 아키텍처 심층 분석 (2026년 4월 기준)"
date: 2026-04-18 03:19:14 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-04]
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
LLM 기반 기능(요약/분류/리랭킹/에이전트 실행/대량 평가)은 대체로 **요청 시간 변동이 크고(수 초~수 분), 외부 의존(OpenAI/사내 vLLM/DB/벡터DB)과 rate limit**의 영향을 강하게 받습니다. 이걸 동기 HTTP로 처리하면 곧바로 다음 문제가 터집니다:

- API timeout, 재시도 폭발, 사용자 경험 악화(“로딩만 도는 UI”)
- LLM 공급자 지연/장애 시 웹 서버까지 같이 고갈
- GPU/비용 자원(특히 vLLM) 스케줄링 실패 → tail latency 악화
- “요청은 받았는데 결과가 안 옴”, “Queued 상태로 영원히 대기” 같은 운영 이슈(외부 비동기 API에서도 실제로 보고됨) ([community.openai.com](https://community.openai.com/t/requests-remain-queued-forever/1361233?utm_source=openai))

그래서 **Queue/Worker**로 “웹 요청 수명”과 “LLM 작업 수명”을 분리하는 게 정석입니다. 이 글은 그중 가장 흔한 조합인 **Celery + Redis**를 LLM 백엔드 관점에서 “언제 쓰면 좋은지/언제 피해야 하는지”, 그리고 **정확히 어떤 설정/패턴이 장애를 막는지**까지 다룹니다.

언제 쓰면 좋나
- LLM 호출이 **수 초~수 분**이고, 웹 요청은 **즉시 job id 반환**이 적합할 때
- 작업량이 출렁이고(피크), rate limit/동시성 제어가 필요할 때
- “재시도, 지연 재시도, dead-letter에 준하는 처리”를 앱 레벨에서 설계할 준비가 있을 때

언제 쓰면 안 되나
- **정확히 한 번(exactly-once)** 처리가 필수(결제/정산)인데 idempotency 설계가 불가능할 때
- 장기적으로 **강한 내구성/순서/재처리**가 핵심이라면 Redis broker 대신 RabbitMQ/SQS/Kafka 류를 우선 검토(특히 장애 복구 요구가 높을 때)
- Redis를 이미 캐시/세션으로 빡빡하게 쓰고 있고, 별도 인프라 분리가 어려울 때(메모리 eviction이 곧 데이터 유실 리스크)

---

## 🔧 핵심 개념
### 1) Celery에서 “Redis를 쓴다”는 것의 의미: Broker vs Result Backend
- **Broker(메시지 큐)**: 작업을 “누가 가져가서 처리할지” 전달
- **Result backend(결과 저장소)**: 작업 상태/결과 조회(폴링/콜백/UI 진행률)

Celery는 Redis를 **broker로도, result backend로도** 쓸 수 있습니다. 다만 운영 관점에서 중요한 건 “Redis가 MQ 전용으로 설계된 게 아니다”라는 점입니다. Celery Redis broker는 내부적으로 **ack/재전달을 visibility timeout 기반**으로 구현합니다. 즉 “worker가 작업을 가져갔는데 ack를 못 하면, 일정 시간이 지난 뒤 재전달”이라는 모델입니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.0.0/getting-started/brokers/redis.html?utm_source=openai))

### 2) acks_late + visibility_timeout: LLM 작업에서 제일 많이 터지는 조합
LLM 작업은 길어질 수 있습니다(프롬프트 길이, tool call, 재시도, 네트워크 지연). 이때 우리가 흔히 켜는 옵션이:

- `task_acks_late=True`: **작업 성공 후에 ack** → worker가 죽으면 재처리 가능(내구성↑)
- `broker_transport_options.visibility_timeout=...`: worker가 가져간 메시지를 **얼마나 “안 보이게” 숨길지**(그 안에 ack 없으면 재전달) ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.0.0/getting-started/brokers/redis.html?utm_source=openai))

핵심 함정:
- `acks_late=True`를 켰는데 **visibility_timeout < 실제 작업 시간(p95/p99)** 이면, “아직 실행 중인데” 메시지가 다시 풀려 **중복 실행**이 발생합니다. 이건 Redis/SQS 계열에서 특히 치명적이고, `acks_late`가 visibility timeout을 “자동으로 해결해주지 않는다”는 지적도 실제 커밋/문서 수정으로 이어졌습니다. ([mail-archive.com](https://www.mail-archive.com/commits%40airflow.apache.org/msg497170.html?utm_source=openai))

LLM에서는 중복 실행이 곧 비용/레이트리밋/데이터 오염(중복 저장)으로 직결되므로, **(1) 충분히 긴 visibility_timeout** + **(2) idempotency 키**가 사실상 필수입니다.

### 3) “Async”의 두 층: (A) 웹 레벨 비동기, (B) 워커 내부 비동기
많은 팀이 “FastAPI async니까 Celery task 안에서 async로 OpenAI 호출하면 더 빠르지 않나?”를 고민합니다.

- Celery worker는 기본적으로 **prefork(프로세스)** 기반이 많고, 각 task 함수는 동기 함수로 동작하는 게 표준입니다.
- 워커 내부에서 async HTTP를 쓰고 싶다면 (a) gevent/eventlet 풀, (b) 별도 async 실행기, (c) 아예 다른 워커(예: arq/dramatiq/custom asyncio worker) 고려가 필요합니다.

현실적으로 LLM I/O 병목(외부 API)이라면 **“워커 프로세스 수/동시성” + “rate limit 토큰 버킷”**이 더 중요하고, 무리한 async 혼합은 디버깅 난이도만 올리기 쉽습니다. 대신 **작업을 쪼개고(오케스트레이션), 외부 호출 timeout/재시도 전략**을 명확히 하는 게 효과가 큽니다.

### 4) 사내 LLM(vLLM)까지 고려하면: 워커는 “GPU 큐의 전단”이다
vLLM은 내부적으로 비동기 엔진(AsyncLLMEngine)과 OpenAI-compatible server에서 이를 사용합니다. ([docs.vllm.ai](https://docs.vllm.ai/design/arch_overview.html?utm_source=openai))  
즉, Celery 큐는 “GPU inference 큐 앞단에서” 다음을 책임지게 됩니다:

- 요청 admission control(동시 요청 제한)
- 배치/우선순위/사용자별 quota(앱 레벨)
- 실패 시 재시도/대체 모델 라우팅
- 결과 저장/streaming 변환(SSE/WebSocket으로 전달)

---

## 💻 실전 코드
아래는 “LLM 작업을 비동기 job으로 실행하고, 상태 조회 + 결과 저장 + 중복 실행 방지(idempotency)”까지 포함한 **현실적인 골격**입니다. (toy 예제처럼 print만 하고 끝내지 않겠습니다.)

### 0) 의존성/구성(로컬 기준)
```bash
# Python 3.11+ 권장 (Celery 5.6에서 3.8 지원 제거 흐름 참고) ([docs.celeryq.dev](https://docs.celeryq.dev/en/main/history/whatsnew-5.6.html?utm_source=openai))
python -m venv .venv
source .venv/bin/activate

pip install "celery[redis]" redis fastapi uvicorn httpx pydantic
docker run -p 6379:6379 --name redis -d redis:7
```

### 1) Celery 앱 설정 + “LLM 작업” (idempotency 포함)
```python
# worker.py
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import httpx
import redis
from celery import Celery
from celery.exceptions import Ignore

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RESULT_TTL_SEC = int(os.getenv("RESULT_TTL_SEC", "86400"))

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

celery_app = Celery(
    "llm_worker",
    broker=REDIS_URL,          # broker도 Redis
    backend=REDIS_URL,         # result backend도 Redis(간단화)
)

# LLM 작업은 길어질 수 있으므로 visibility_timeout을 “p99 작업시간보다 길게”
# Redis broker의 visibility timeout 의미/주의는 공식 문서에 명시됨. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.0.0/getting-started/brokers/redis.html?utm_source=openai))
celery_app.conf.update(
    task_acks_late=True,                 # 성공 후 ack (worker 죽으면 재전달)
    task_reject_on_worker_lost=True,     # worker lost 시 재큐잉(중복 가능성은 idempotency로 상쇄)
    broker_transport_options={
        "visibility_timeout": 60 * 60 * 2,   # 2시간 (예시: p99이 20분이면 여유 있게)
    },
    result_expires=RESULT_TTL_SEC,
)

def _job_key(model: str, prompt: str, user_id: str) -> str:
    raw = json.dumps({"m": model, "p": prompt, "u": user_id}, ensure_ascii=False, sort_keys=True)
    return "job:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

@celery_app.task(bind=True, max_retries=5, default_retry_delay=5)
def run_llm(self, *, model: str, prompt: str, user_id: str) -> dict[str, Any]:
    """
    현실 포인트:
    - idempotency: 동일 입력은 동일 job_key로 dedupe
    - 외부 LLM 호출은 timeout 필수
    - 중복 실행이 와도 “이미 완료된 결과”면 즉시 반환
    """
    job_key = _job_key(model, prompt, user_id)
    done_key = f"{job_key}:done"
    lock_key = f"{job_key}:lock"

    # 이미 완료된 작업이면 즉시 반환 (중복 실행 방지의 핵심)
    cached = r.get(done_key)
    if cached:
        return json.loads(cached)

    # 분산 락: 동시에 여러 worker가 같은 작업을 집어도 1개만 실행
    # (Redis broker 특성상 중복 실행은 언제든 발생 가능하다고 가정)
    got_lock = r.set(lock_key, "1", nx=True, ex=60 * 60 * 2)
    if not got_lock:
        # 다른 워커가 처리 중 → 빠르게 종료(또는 재시도)
        raise Ignore()

    try:
        t0 = time.time()

        # 예시: OpenAI 호환 엔드포인트든, 사내 게이트웨이든 “동기 호출 + 타임아웃”을 강제
        # (실무에서는 circuit breaker, 429 backoff 등을 추가)
        llm_url = os.getenv("LLM_URL", "http://localhost:8001/v1/chat/completions")
        llm_api_key = os.getenv("LLM_API_KEY", "dev")

        with httpx.Client(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            resp = client.post(
                llm_url,
                headers={"Authorization": f"Bearer {llm_api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        result = {
            "job_key": job_key,
            "model": model,
            "user_id": user_id,
            "output": data,
            "latency_sec": round(time.time() - t0, 3),
        }

        # 완료 결과 저장(조회 API는 여기만 보면 됨)
        r.set(done_key, json.dumps(result, ensure_ascii=False), ex=RESULT_TTL_SEC)
        return result

    except (httpx.TimeoutException, httpx.HTTPError) as e:
        # LLM은 일시 장애/429가 흔함 → 재시도 가치가 높음
        raise self.retry(exc=e, countdown=min(60, 2 ** self.request.retries))
    finally:
        r.delete(lock_key)
```

**실행**
```bash
# worker 실행
celery -A worker.celery_app worker --loglevel=INFO --concurrency=4
```

### 2) FastAPI: “enqueue → job id 반환 → 상태/결과 조회”
```python
# api.py
from __future__ import annotations

import json
import os
from fastapi import FastAPI, HTTPException
import redis

from worker import run_llm, _job_key

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI()

@app.post("/llm/submit")
def submit(model: str, prompt: str, user_id: str):
    job_key = _job_key(model, prompt, user_id)
    done_key = f"{job_key}:done"

    cached = r.get(done_key)
    if cached:
        return {"status": "done", "job_key": job_key}

    # Celery enqueue
    async_result = run_llm.delay(model=model, prompt=prompt, user_id=user_id)
    return {"status": "queued", "job_key": job_key, "task_id": async_result.id}

@app.get("/llm/result/{job_key}")
def result(job_key: str):
    done_key = f"{job_key}:done"
    cached = r.get(done_key)
    if not cached:
        return {"status": "pending", "job_key": job_key}
    return {"status": "done", "job_key": job_key, "result": json.loads(cached)}
```

**API 실행**
```bash
uvicorn api:app --reload --port 8000
```

**예상 흐름**
1) `/llm/submit` → `{status:"queued", job_key:...}`
2) 워커 처리 후 `/llm/result/{job_key}` → `{status:"done", result:{...}}`

> 포인트: “Celery task id로 폴링”이 아니라, **업무 키(job_key)** 로 조회하게 만들면  
> - 중복 요청 dedupe  
> - 재시도/재큐잉/중복 실행에도 결과 일관성 유지  
> - UI/DB 모델링이 단순해집니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) visibility_timeout은 “작업 시간”이 아니라 “최악의 재시작 시나리오”로 잡아라
Redis broker에서 visibility_timeout은 “ack가 없으면 재전달”의 기준입니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.0.0/getting-started/brokers/redis.html?utm_source=openai))  
LLM은 p99가 쉽게 튀고, 배포/노드 장애로 작업이 멈춘 채로 남을 수 있습니다. 따라서:
- `visibility_timeout >= (작업 p99) + (최대 배포/재시작 시간) + 여유`
- `acks_late=True`를 쓰면 이 값이 **너무 짧을 때 중복 실행**이 발생합니다. ([securityboulevard.com](https://securityboulevard.com/2024/12/a-deep-dive-into-celery-task-resilience-beyond-basic-retries/?utm_source=openai))

### Best Practice 2) idempotency를 “큐 레벨”이 아니라 “도메인 레벨”로 해결
LLM 작업은 대부분 **side effect**(DB 저장, 결제 아님이라도 로그/과금/사용량 차감)가 있습니다.  
따라서 “중복 실행이 가능하다”는 전제에서:
- 입력(모델/프롬프트/유저/파라미터) 기반 `job_key`
- `SET NX` 락 + 완료 캐시(done_key)
- 결과 저장을 트랜잭션/업서트 형태로 설계

이 3개가 있어야 Redis broker 특성, 워커 재시작, 네트워크 이슈를 견딥니다.

### Best Practice 3) Redis 메모리 eviction 정책을 무시하면 “작업 유실”을 자초한다
Celery Redis broker 문서에서 **evict 설정**을 경고합니다(메모리 부족 시 키가 날아가면 큐/상태가 망가질 수 있음). ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.0.0/getting-started/brokers/redis.html?utm_source=openai))  
실무 권장:
- broker Redis는 가능하면 **전용 인스턴스/클러스터**로 분리
- `maxmemory-policy`를 업무 특성에 맞게(최소한 “중요 키가 eviction되지 않게”) 검토
- 결과 TTL(result_expires)로 backend 메모리 압박을 관리

### 흔한 함정 1) “async def task”로 해결하려다 더 꼬임
Celery의 실행 모델(프로세스/풀)과 asyncio는 조합을 신중히 해야 합니다.  
대부분의 LLM 호출은 I/O라서 “워커 concurrency/프리페치/레이트리밋” 조절이 더 큰 레버리지입니다.

### 흔한 함정 2) “Queued forever”는 외부만의 문제가 아니다
OpenAI 같은 외부 비동기 처리에서도 “queued/in_progress가 계속됨” 이슈가 커뮤니티에 보고됩니다. ([community.openai.com](https://community.openai.com/t/requests-remain-queued-forever/1361233?utm_source=openai))  
내 시스템에서도 같은 일이 생깁니다. 대응 체크리스트:
- 워커 healthcheck + autoscaling 조건이 “큐 적체”를 보는가?
- task timeout(soft/hard) + 외부 호출 timeout이 모두 있는가?
- 재시도 폭주 시 rate limit이 어떻게 동작하는가(전역 토큰 버킷 필요)

### 비용/성능/안정성 트레이드오프
- `acks_late=True` + 긴 visibility_timeout: 안정성↑ / 중복 실행↓(idempotency 전제) / 재전달 늦어질 수 있음
- Redis broker: 운영 단순/빠름 / 하지만 MQ 특화 기능(강한 내구성, 정교한 DLQ)은 약함
- 외부 LLM Batch(예: OpenAI Batch API): 대량 처리 비용↓, throughput↑ / 대신 24h 내 완료 같은 제약이 있으므로 “실시간 UX”엔 부적합 ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 4월 시점에서 “LLM 비동기 처리”를 Celery+Redis로 안정화하려면 핵심은 3가지입니다.

1) **acks_late + visibility_timeout을 한 세트로 설계**(p99 기준으로 넉넉히) ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.0.0/getting-started/brokers/redis.html?utm_source=openai))  
2) Redis broker는 중복 실행이 “언제든 가능”하다고 보고, **도메인 idempotency(job_key)로 흡수**  
3) Redis 운영(메모리/eviction/분리)과 워커 운영(healthcheck/timeout/retry/rate limit)을 함께 가져가기 ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.0.0/getting-started/brokers/redis.html?utm_source=openai))  

도입 판단 기준(바로 써도 되는 경우)
- 현재 문제의 80%가 “웹 타임아웃/LLM 지연/레이트리밋”이고
- 작업 결과가 “중복 처리돼도 idempotent하게 만들 수 있으며”
- Redis를 브로커 전용으로 분리하거나, 적어도 메모리 정책/관측을 제대로 할 수 있다

다음 학습 추천
- Celery Redis broker 공식 문서(visibility_timeout/운영 주의) ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.0.0/getting-started/brokers/redis.html?utm_source=openai))
- Celery 최신 changelog에서 Redis 안정성 관련 이슈 추적(특히 Kombu/Redis 연결 안정성) ([docs.celeryq.dev](https://docs.celeryq.dev/en/stable/changelog.html?utm_source=openai))
- 사내 GPU 서빙을 한다면 vLLM AsyncLLMEngine 구조를 이해하고 “큐가 GPU 앞단 admission control”이 되게 설계 ([docs.vllm.ai](https://docs.vllm.ai/design/arch_overview.html?utm_source=openai))