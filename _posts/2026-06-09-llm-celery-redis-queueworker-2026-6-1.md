---
title: "LLM 요청을 “안전하게” 비동기화하기: Celery + Redis queue/worker 아키텍처 심층 분석 (2026년 6월 기준)"
date: 2026-06-09 04:12:28 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-06]
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
LLM 기반 기능을 프로덕션에 붙이면 금방 마주치는 문제가 있습니다.

- **HTTP 요청-응답 시간 안에 끝나지 않는다**: 문서 요약/대량 평가/에이전트 플로우는 수십 초~수분이 흔합니다.
- **외부 API(LLM) 변동성**: rate limit, 일시 장애, 지연 편차 때문에 **retry/timeout/circuit breaker**가 필요합니다.
- **동시성 제어가 핵심**: “사용자 1명당 1 job”, “조직별 TPS 제한”, “GPU worker는 1개만” 같은 제약이 곧바로 등장합니다.
- **관측/재처리/중단**: 사용자가 “취소”를 누르거나, 결과가 늦어져 “재시도”를 누르거나, 운영자가 “실패 job만 재처리”해야 합니다.

이때 Celery + Redis는 여전히 강력한 선택지입니다. 다만 **언제 쓰면 좋고 / 언제 피해야 하는지**가 중요합니다.

- 쓰면 좋은 경우
  - **분산 worker**가 필요하고(여러 Pod/VM), **재시도/지연 재시도/스케줄링/라우팅/레이트리밋** 같은 “큐 제품급 기능”이 필요할 때
  - LLM 호출이 **I/O + 긴 대기 + 간헐 실패**를 포함하고, “결국 성공해야 한다”는 요구가 있을 때
  - API 서버(FastAPI 등)는 가볍게 유지하고, **워크로드를 별도 worker tier로 격리**하고 싶을 때

- 피하는 게 나은 경우
  - 작업이 정말 가볍고(수백 ms~수 초), **요청 처리 중 BackgroundTasks/내부 async**로도 충분하며, “재시도/내구성” 요구가 약할 때
  - “정확히 한 번(exactly-once)” 처리가 법/정산급으로 강제되는 경우(이건 Celery+Redis 조합만으로는 어렵고, idempotency+트랜잭션 설계가 필요)
  - Redis를 브로커로 쓸 때의 특성(visibility timeout, 중복 실행 가능성)을 팀이 이해/운영할 준비가 없을 때

---

## 🔧 핵심 개념
### 1) LLM 비동기 처리에서 “큐”가 해결하는 것
LLM 비동기 처리의 본질은 “백그라운드에서 오래 걸리는 일을 안전하게 돌리고, 결과를 나중에 전달”입니다. 여기서 큐/워커가 제공하는 핵심은:

- **Durability(내구성)**: 요청이 worker로 넘어가기 전에 서버가 죽어도 작업이 유실되지 않게
- **Retry semantics(재시도 의미론)**: 실패가 ‘일시적’인지 ‘영구적’인지 분리하고, backoff로 재시도
- **Concurrency control(동시성 제어)**: worker 수, queue별 격리, rate limit, priority
- **Observability(관측)**: 상태 저장, 진행률/로그, 실패 원인, 재처리

Scale의 LLM 서비스 예시도 “Gateway → broker queue → Celery worker → result 저장 → client polling” 같은 전형적인 흐름을 사용합니다. ([llm-engine.scale.com](https://llm-engine.scale.com/internal/architecture/?utm_source=openai))

### 2) Celery + Redis에서 반드시 이해해야 할 내부 흐름(ack/visibility timeout)
Redis를 Celery broker로 쓸 때, 가장 큰 포인트는 **visibility timeout**과 **late ack(acks_late)** 입니다.

- **visibility timeout**: worker가 task를 “가져갔는데(consume)” 일정 시간 내 **ack**를 안 하면, broker가 “이 작업은 죽은 것 같아”라고 판단하고 **재전달(redeliver)** 합니다. Celery Redis 문서에 명시돼 있습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.2/getting-started/backends-and-brokers/redis.html?utm_source=openai))
- `task_acks_late=True`: “작업을 성공적으로 끝낸 뒤에 ack 하겠다”는 의미입니다. worker가 중간에 죽으면 ack가 안 되므로, visibility timeout 이후 **다시 큐로 돌아와 재실행**될 수 있습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.2/getting-started/backends-and-brokers/redis.html?utm_source=openai))

중요한 결론:
- Redis broker + acks_late는 **At-least-once**에 가깝습니다.
- 즉, **중복 실행은 ‘버그’가 아니라 정상 시나리오**로 봐야 합니다(특히 LLM 같은 긴 작업에서).

문서도 “visibility_timeout을 너무 길게 잡으면, 강제 종료/전원 장애 시 ‘lost task’의 redelivery가 늦어진다”고 경고합니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.2/getting-started/backends-and-brokers/redis.html?utm_source=openai))

또한 `broker_transport_options={'visibility_timeout': ...}`로 설정 가능하다고 Celery 설정 문서에 나옵니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.4.0/userguide/configuration.html?utm_source=openai))

### 3) 다른 접근과의 차이점(“async”만으로 해결 안 되는 지점)
- **FastAPI async/BackgroundTasks**: 동일 프로세스/Pod 내에서만 유효하고, 프로세스가 죽으면 작업도 죽습니다. “언젠가 반드시 처리”가 요구되면 한계가 빨리 옵니다.
- **Redis Streams / Consumer Group**: 메시징에 더 강한 모델(ack/pending/claim 등)을 제공하지만, Celery 기본 Redis transport는 “Streams를 native하게 broker로” 쓰는 방식과는 결이 다릅니다. Streams 자체의 개념/운영 포인트(XCLAIM 등)는 따로 학습이 필요합니다. ([systeminternals.dev](https://systeminternals.dev/redis/streams/?utm_source=openai))
- **RabbitMQ/Kafka**: 운영 복잡도는 오르지만, 메시징 의미론이 더 명확해지는 경우가 많습니다(특히 대규모/엄격한 전달 보장).

---

## 💻 실전 코드
아래 예제는 “문서 업로드 → chunking → LLM 요약/분류 → 결과 저장 → 진행률 제공” 같은 **현실적인 LLM 파이프라인**을 가정합니다.

- API 서버(FastAPI)는 **enqueue + 상태 조회**만 담당
- Celery worker는 **LLM 호출 + 재시도 + 진행률 업데이트**
- Redis는 **broker + result backend + 진행률 상태 저장(별도 key)**

### 1) 초기 셋업 (docker-compose)
```bash
# docker-compose.yml
services:
  redis:
    image: redis:7
    ports: ["6379:6379"]

  worker:
    build: .
    command: celery -A app.celery_app worker -l INFO -Q llm --concurrency=4
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on: [redis]

  api:
    build: .
    command: uvicorn app.api:app --host 0.0.0.0 --port 8000
    ports: ["8000:8000"]
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on: [redis]
```

```bash
# requirements.txt (예시)
fastapi==0.115.0
uvicorn[standard]==0.30.6
celery==5.5.2
redis==5.0.8
pydantic==2.8.2
httpx==0.27.0
```

### 2) Celery 설정 + “중복 실행 대비(idempotency)”가 들어간 task
핵심은 3가지입니다.

1) `task_acks_late=True`로 worker 장애 시 재처리 가능하게  
2) `visibility_timeout`을 **LLM 최악 실행시간보다 크게**(너무 크게 잡으면 복구 지연)  
3) task는 **idempotent**하게(동일 job_id면 결과를 중복 생성하지 않도록)

```python
# app/celery_app.py
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "llm_async",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_default_queue="llm",
    task_acks_late=True,                 # 작업 끝나고 ack
    task_reject_on_worker_lost=True,     # worker 죽으면 재큐잉 유도(단, Redis는 visibility_timeout 설정이 중요)
    worker_prefetch_multiplier=1,        # 긴 작업에서 과다 prefetch 방지
    broker_transport_options={
        # Redis broker는 visibility timeout 이후 ack 없는 메시지를 redeliver 할 수 있음
        # Celery 문서에 명시됨 ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.2/getting-started/backends-and-brokers/redis.html?utm_source=openai))
        "visibility_timeout": 60 * 60 * 2,  # 2 hours (업무에 맞게 조정)
    },
    result_expires=60 * 60 * 24,         # 결과 24h 보관(운영 정책에 맞게)
)
```

```python
# app/tasks.py
import json
import os
import time
import hashlib
import httpx
import redis
from celery import shared_task, states
from celery.exceptions import Ignore

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def progress_key(job_id: str) -> str:
    return f"job:{job_id}:progress"

def result_key(job_id: str) -> str:
    return f"job:{job_id}:result"

def lock_key(job_id: str) -> str:
    return f"job:{job_id}:lock"

def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

async def call_llm(prompt: str) -> str:
    # 예시: 외부 LLM API 호출(실무에선 timeout/retry/circuit breaker 더 강화)
    # 여기선 형태만 보여주기 위해 더미 엔드포인트 느낌으로 구성
    async with httpx.AsyncClient(timeout=60) as client:
        # resp = await client.post("https://api.vendor.com/v1/chat", json={...})
        # resp.raise_for_status()
        # return resp.json()["output"]
        await httpx.AsyncClient().aclose()
    return f"SUMMARY::{stable_hash(prompt)[:16]}"

@shared_task(bind=True, max_retries=6, default_retry_delay=10)
def summarize_document(self, job_id: str, document_text: str, user_id: str):
    """
    현실적인 포인트:
    - Redis broker는 중복 실행 가능(visibility_timeout / worker crash 등)
    - 따라서 job_id 기반으로 '이미 끝난 작업이면 즉시 반환'하는 idempotency가 필요
    """
    # 0) 이미 결과가 있으면(이전에 성공) 그대로 반환 -> 중복 실행 방지
    existing = r.get(result_key(job_id))
    if existing:
        return json.loads(existing)

    # 1) 동시 중복 실행 방지(soft lock). 완벽한 exactly-once는 아니지만 중복 폭발을 크게 줄임.
    #    lock TTL은 visibility_timeout보다 약간 짧거나, 작업 최악 시간보다 길게 잡는 식으로 조정.
    got_lock = r.set(lock_key(job_id), self.request.id, nx=True, ex=60 * 60 * 2)
    if not got_lock:
        # 다른 worker가 처리 중. 상태만 보고 빠져도 되고, 약간 기다렸다가 결과 확인해도 됨.
        raise self.retry(countdown=5)

    try:
        r.set(progress_key(job_id), json.dumps({"step": "chunking", "pct": 5}), ex=60 * 60 * 24)

        # 2) chunking (예: 토큰 기준/문단 기준). 여기선 간단히 분할.
        chunks = [document_text[i:i+4000] for i in range(0, len(document_text), 4000)]
        r.set(progress_key(job_id), json.dumps({"step": "summarizing", "pct": 10, "chunks": len(chunks)}), ex=60*60*24)

        summaries = []
        for idx, chunk in enumerate(chunks, start=1):
            # 외부 API 실패는 흔함 -> retry 전략 필요
            try:
                # sync task 안에서 async 호출을 안전하게 하려면 별도 이벤트루프 전략이 필요하지만,
                # 여기선 예시로 "외부 호출이 있다"는 현실만 반영(실무에선 asyncio.run / anyio 등 팀 표준 사용).
                # time.sleep으로 네트워크 대기 상황을 모사
                time.sleep(1.2)
                summaries.append(f"chunk{idx}:{stable_hash(chunk)[:12]}")
            except Exception as e:
                raise self.retry(exc=e, countdown=min(120, 2 ** self.request.retries))

            pct = 10 + int(70 * idx / max(1, len(chunks)))
            r.set(progress_key(job_id), json.dumps({"step": "summarizing", "pct": pct}), ex=60*60*24)

        r.set(progress_key(job_id), json.dumps({"step": "postprocess", "pct": 85}), ex=60*60*24)

        # 3) 최종 결과 구성(메타 포함)
        result = {
            "job_id": job_id,
            "user_id": user_id,
            "summary": "\n".join(summaries),
            "chunks": len(chunks),
        }

        # 4) 결과 저장(원자적으로)
        r.set(result_key(job_id), json.dumps(result), ex=60*60*24)
        r.set(progress_key(job_id), json.dumps({"step": "done", "pct": 100}), ex=60*60*24)
        return result

    except Exception as e:
        # 실패 상태 기록(클라이언트가 확인 가능하게)
        r.set(progress_key(job_id), json.dumps({"step": "failed", "pct": 100, "error": str(e)}), ex=60*60*24)
        self.update_state(state=states.FAILURE, meta={"error": str(e)})
        raise Ignore()
    finally:
        # lock 해제는 “내가 잡은 락인지 확인”이 더 안전하지만, 예제에선 단순화
        r.delete(lock_key(job_id))
```

### 3) API: enqueue + 진행률/결과 조회
```python
# app/api.py
import uuid
import json
import os
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.tasks import summarize_document, progress_key, result_key

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI()

class SubmitReq(BaseModel):
    user_id: str
    document_text: str

@app.post("/jobs")
def submit(req: SubmitReq):
    job_id = str(uuid.uuid4())
    # task_id는 Celery 내부 식별자, job_id는 비즈니스 식별자(권장)
    summarize_document.delay(job_id=job_id, document_text=req.document_text, user_id=req.user_id)
    r.set(progress_key(job_id), json.dumps({"step": "queued", "pct": 0}), ex=60*60*24)
    return {"job_id": job_id}

@app.get("/jobs/{job_id}")
def get_status(job_id: str):
    prog = r.get(progress_key(job_id))
    if not prog:
        raise HTTPException(404, "unknown job_id")

    result = r.get(result_key(job_id))
    return {
        "job_id": job_id,
        "progress": json.loads(prog),
        "result": json.loads(result) if result else None,
    }
```

예상 동작:
- `POST /jobs` → 즉시 `job_id` 반환 (응답 빠름)
- `GET /jobs/{job_id}` → `queued → chunking → summarizing → postprocess → done` 진행률 확인
- worker 장애/재시작이 있어도 `task_acks_late + visibility_timeout` 조합으로 재처리될 수 있음(중복 실행 대비는 코드에서 `result_key`/lock으로 흡수)

---

## ⚡ 실전 팁 & 함정
### Best Practice (현업에서 바로 체감되는 것)
1) **중복 실행을 전제로 idempotency를 설계**
- Redis broker는 visibility timeout 기반 redelivery로 인해 **중복 실행이 자연스럽게 발생**할 수 있습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.2/getting-started/backends-and-brokers/redis.html?utm_source=openai))  
- “LLM 호출은 돈”이기 때문에, `job_id` 기반 결과 캐시/락/DB upsert 같은 **중복 방지 장치**를 반드시 넣으세요.
- 특히 “사용자가 새로고침/재시도”를 누르는 UX에서는 중복 enqueue도 흔합니다.

2) **긴 작업 + Redis broker라면 `worker_prefetch_multiplier=1`은 거의 고정값**
- prefetch가 크면 한 worker가 여러 개를 “미리 잡아” 대기시키고, 다른 worker는 놀 수 있어 **tail latency**가 폭발합니다.
- LLM 작업은 편차가 크므로, 공정 분배가 더 중요합니다.

3) **visibility_timeout은 ‘최악 실행시간 + 여유’로 잡되, 너무 길게 잡지 말 것**
- 너무 짧으면 “아직 돌고 있는데 redeliver”되어 중복 실행이 늘고,
- 너무 길면 “진짜로 worker가 죽었을 때 복구가 늦어집니다”는 점을 Celery 문서가 경고합니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.2/getting-started/backends-and-brokers/redis.html?utm_source=openai))

### 흔한 함정/안티패턴
- **“acks_late 켰으니 exactly-once겠지” 착각**
  - 아닙니다. at-least-once에 가까우며, 중복은 현실입니다.
- **결과 backend를 Redis에 무한정 쌓기**
  - `result_expires`/TTL 정책 없이 쌓으면 메모리/비용이 터집니다.
  - LLM 결과는 길이가 길어 Redis 메모리에 더 치명적입니다(요약/원문/trace를 모두 넣지 마세요).
- **API 서버가 job 상태를 Celery backend만으로 해결하려는 시도**
  - Celery result는 “결과 저장”엔 좋지만, “진행률/중간 상태/취소 플래그”는 별도 저장소(예: Redis key, DB)가 더 깔끔합니다.

### 비용/성능/안정성 트레이드오프(LLM 관점)
- **성능**: concurrency를 높이면 throughput은 오르지만, 외부 LLM rate limit에 걸려 실패/재시도 폭발 → 오히려 비용 증가
- **안정성**: retry는 필수지만, 무제한 retry는 장애 시 “LLM API에 DDoS”가 됩니다(최대 재시도/백오프/상한 필요)
- **비용**: 중복 실행 방지(락/캐시)는 “성능 최적화”가 아니라 “비용 통제”입니다

---

## 🚀 마무리
Celery + Redis로 LLM 백엔드를 비동기화할 때의 핵심은 “돌아간다”가 아니라:

- Redis broker의 **visibility timeout + acks_late**가 만드는 실행 의미론을 이해하고(중복 가능), ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.2/getting-started/backends-and-brokers/redis.html?utm_source=openai))
- 그 위에 **idempotency / 진행률 저장 / 동시성 제어 / TTL 정책**을 얹어,
- “LLM 비용(중복 호출) + 장애 복구(재처리) + 사용자 UX(상태 조회)”를 함께 만족시키는 것입니다.

도입 판단 기준(현업 체크리스트):
- 작업이 10초 이상이며 실패/지연 변동이 크다 → 큐/워커 고려
- “실패해도 언젠가 처리돼야 한다” → Celery 같은 분산 큐 강력 추천
- 중복 실행을 감당 못 한다 → 먼저 idempotency/업서트/락 설계를 할 수 있는가?
- 운영 복잡도를 감당하기 어렵다 → Celery 대신 더 단순한 async-native queue(arq 등)나 managed queue(SQS 등)도 검토(단, 의미론/운영 모델이 달라짐)

다음 학습 추천:
- Celery Redis transport의 visibility timeout/ack 동작(문서) 정독 ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.2/getting-started/backends-and-brokers/redis.html?utm_source=openai))
- “LLM pipeline”에서 **job state model**(queued/running/succeeded/failed/canceled)과 저장 전략 설계
- 대규모로 가면 Redis broker 한계를 느낄 수 있으니, RabbitMQ/SQS 같은 broker로의 전환 기준도 미리 정의

원하면, 위 예제를 “취소(cancel) 지원”, “조직별 rate limit”, “WebSocket으로 진행률 push”, “DB에 job metadata 영속화(재시작 후에도 조회)”까지 확장한 버전으로 이어서 작성해드릴게요.