---
title: "LLM 백엔드 비동기 처리, “Celery + Redis”로 끝내도 될까? (2026년 5월 기준 Queue/Worker 아키텍처 심층 분석)"
date: 2026-05-11 04:11:04 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-05]
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
LLM을 백엔드에 붙이면 금방 이런 병목이 생깁니다.

- 요청 1건이 **수 초~수 분** 걸림(Reasoning/Tool 호출/멀티스텝)
- 외부 API(LLM, 검색, RAG, 사내 시스템) 호출이 많아 **I/O bound**가 됨
- 트래픽이 몰릴 때 Web 프로세스가 붙잡혀 **timeout / 스레드 고갈 / DB 커넥션 고갈**
- “재시도/중복 방지/취소/진행률/감사 로그” 같은 **운영 요구사항**이 갑자기 튀어나옴

이때 Queue/Worker는 “느린 작업을 웹 요청 경로에서 떼어내고”, **재시도와 격리**로 시스템을 안정화하는 가장 현실적인 선택입니다.

언제 쓰면 좋은가
- LLM 호출이 **느리거나 변동성이 큰** 경우(간헐적 429/5xx, 네트워크 끊김)
- “요청-응답”이 아니라 **job 기반**(요약 배치, 문서 인덱싱, 평가, 리포트 생성)
- **재시도/지연 실행/스케줄링/분산 워커**가 필요한 경우

언제 쓰면 안 되는가
- 결과가 “지금 당장” 필요하고, 1~2초 내 끝나는 작업(그냥 동기 + timeout/서킷브레이커가 단순)
- 작업이 아주 가볍고 신뢰성이 덜 중요(예: “로그 적재” 정도) → 큐 운영비가 더 큼
- “정확히 한 번(exactly-once)”을 강제해야 하는 금융/정산 성격의 핵심 트랜잭션(이건 워크플로/사가 + idempotency가 더 중요)

추가로 2026년 5월 기준, LLM 제공 API 자체도 비동기 옵션을 강화했습니다. 예를 들어 OpenAI Responses API의 **background mode**(장시간 작업을 비동기로 시작하고 polling/stream 재접속)나 **Batch API**(대량 요청을 24시간 윈도우로 처리, 비용 절감/별도 rate limit pool)는 “우리 큐가 해야 할 일을 일부 대체”할 수 있습니다. 다만 이건 “벤더 내부 큐”이고, 우리 시스템의 관측/재처리/도메인 워크플로까지 커버하진 않습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))

---

## 🔧 핵심 개념
### 1) LLM 비동기 처리에서 Queue/Worker가 실제로 해결하는 것
LLM 호출을 단순히 background thread로 보내는 것과 “큐 시스템”의 차이는 다음 4가지입니다.

1. **Backpressure**: 웹 요청은 빨리 반환하고, 큐 길이/동시성으로 부하를 제어  
2. **Retry & Delay**: 429/timeout/일시 장애에 대해 지수 백오프, 지연 재시도  
3. **Isolation**: 느린 job이 웹/DB/다른 작업을 끌어내리지 않게 워커 풀로 격리  
4. **Observability**: “무슨 job이 어디서 막혔는지” 추적(상태 저장, 이벤트/로그)

### 2) Celery + Redis 조합의 내부 흐름(중요 포인트만)
Celery에서 Redis를 broker로 쓰면(리스트 기반 transport), task message는 Redis에 들어가고 worker가 가져가서 실행합니다. 여기서 “LLM 작업”에서 가장 크게 터지는 지점은 보통 **ack(확인) 타이밍**과 **visibility timeout**입니다.

- `task_acks_late=True`  
  “작업을 다 끝낸 뒤 ack” → 워커가 죽으면 작업이 다시 실행될 수 있어 신뢰성이 올라가지만, **중복 실행** 가능성이 커집니다(LLM 비용/부작용 주의).
- Redis broker의 `visibility_timeout`  
  워커가 메시지를 가져갔는데 ack가 없으면 일정 시간 뒤 “다른 워커에게 재전달”될 수 있습니다. 문서에서도 visibility timeout을 설정할 수 있지만, 너무 공격적으로 설정하면 오히려 신뢰성/중복 실행/재큐잉 폭풍을 만들 수 있다고 경고합니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html?utm_source=openai))
- “워커 종료”는 운영에서 진짜 중요  
  Redis/SQS처럼 visibility timeout 메커니즘이 있는 broker에서는 Celery가 **soft shutdown**으로 “미처리(unacked) 메시지를 다시 큐로 돌려놓는” 동작을 더 안전하게 만들려는 개선이 들어가고 있습니다(종료 직전에 visibility timeout을 리셋해 re-queue를 돕는 취지). 2026년 Celery 5.6 계열 변경 로그에 이 내용이 명시돼 있습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/stable/changelog.html?utm_source=openai))

핵심 차이점: “Celery는 HTTP async가 아니라 ‘distributed task processing’”
- FastAPI/asyncio는 “요청 처리 모델”의 비동기고,
- Celery는 “프로세스/서버를 넘나드는 작업 실행 모델”의 비동기입니다.

따라서 LLM처럼 **오래 걸리고 실패하는 작업**은 asyncio만으로는 부족하고(재시도/운영/스케일), Celery가 여전히 강합니다. 다만 Celery 자체는 기본적으로 프로세스/스레드 기반 동시성을 쓰기 때문에, “async-native” 워커를 기대하면 설계가 꼬일 수 있습니다(아래 함정 참고).

---

## 💻 실전 코드
아래 예제는 “사용자가 문서를 업로드하면, 백그라운드에서 LLM 요약 + 임베딩 + DB 저장 + 진행률 조회 + 중복 실행 방지”까지 현실적으로 들어간 형태입니다.

### 0) 목표 아키텍처
- Web API(FastAPI): job 생성/상태 조회만 담당
- Redis:
  - Celery broker (queue)
  - 결과/상태 저장(result backend) 또는 별도 상태 저장(권장)
  - idempotency lock(중복 방지)
- Celery worker: LLM 호출(느림), 재시도, 타임아웃, 진행률 업데이트

### 1) 설치/실행
```bash
# Python 3.11+ 가정
python -m venv .venv && source .venv/bin/activate
pip install "celery[redis]>=5.5" fastapi uvicorn redis pydantic httpx sqlalchemy psycopg[binary]

# Redis 실행(로컬)
docker run -p 6379:6379 redis:7-alpine

# 워커 실행
celery -A app.celery_app worker -l INFO -Q llm --concurrency=4

# API 실행
uvicorn app.api:app --reload --port 8000
```

### 2) Celery 설정 (Redis + 신뢰성 옵션)
```python
# app/celery_app.py
from celery import Celery

celery_app = Celery(
    "llm_backend",
    broker="redis://localhost:6379/1",
    backend="redis://localhost:6379/2",
)

celery_app.conf.update(
    task_default_queue="llm",

    # LLM 작업은 길고 비싸므로 prefetch를 낮춰 "한 워커가 과식"하는 걸 막음
    worker_prefetch_multiplier=1,

    # 작업 끝난 뒤 ack: 워커가 죽으면 재전달 가능(중복 실행 대비 필수)
    task_acks_late=True,

    # 워커 죽었을 때 해당 워커가 잡고 있던 task를 다른 워커가 받게 함
    task_reject_on_worker_lost=True,

    # Redis broker visibility timeout (LLM 최대 수행시간 + 여유)
    broker_transport_options={"visibility_timeout": 60 * 30},  # 30분

    # 결과는 무한 저장하지 말 것(운영 비용 폭발). 상태는 DB/별도 스토어 권장
    result_expires=60 * 60,
)
```

### 3) “중복 방지 + 재시도 + 진행률”이 들어간 실제 Task
```python
# app/tasks.py
import os
import json
import time
import random
from dataclasses import dataclass

import httpx
import redis
from celery import shared_task
from celery.exceptions import Ignore

r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

@dataclass
class JobProgress:
    phase: str
    percent: int
    detail: str

def set_progress(job_id: str, p: JobProgress):
    r.hset(f"job:{job_id}", mapping={
        "phase": p.phase,
        "percent": str(p.percent),
        "detail": p.detail,
        "updated_at": str(int(time.time())),
    })

def acquire_idempotency_lock(job_id: str, ttl_sec: int = 3600) -> bool:
    # SET key value NX EX ttl
    return bool(r.set(f"joblock:{job_id}", "1", nx=True, ex=ttl_sec))

def release_idempotency_lock(job_id: str):
    r.delete(f"joblock:{job_id}")

@shared_task(
    bind=True,
    autoretry_for=(httpx.TimeoutException, httpx.NetworkError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
    soft_time_limit=60 * 25,
    time_limit=60 * 28,
)
def summarize_and_index(self, job_id: str, document_text: str):
    """
    현실 포인트:
    - acks_late + retry 조합이면 "중복 실행"이 아주 쉽게 발생한다.
    - 그래서 idempotency lock + 외부 부작용(예: DB insert)은 upsert로 설계한다.
    """
    if not acquire_idempotency_lock(job_id, ttl_sec=60 * 60):
        # 이미 처리 중/처리 완료 가능. 중복 실행을 조용히 무시.
        raise Ignore()

    try:
        set_progress(job_id, JobProgress("summarizing", 10, "Calling LLM summarization"))

        # 예시로 OpenAI Responses API를 호출(동기 호출이지만 워커에서 실행)
        # 실제로는 background mode나 vendor batch를 섞을지 판단 가능
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        payload = {
            "model": "gpt-5.2-mini",
            "input": [
                {"role": "system", "content": "You are a precise technical summarizer."},
                {"role": "user", "content": f"Summarize and extract key entities:\n\n{document_text}"},
            ],
            "temperature": 0.2,
        }

        with httpx.Client(timeout=60) as client:
            resp = client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # (간단 처리) output_text만 사용
        summary = data.get("output_text", "")

        set_progress(job_id, JobProgress("indexing", 60, "Indexing to DB (simulated)"))

        # 여기서 DB upsert / vector store upsert를 해야 함 (중복 실행 대비)
        # 데모용: 랜덤 지연
        time.sleep(random.uniform(0.3, 1.2))

        r.hset(f"job:{job_id}", mapping={
            "status": "done",
            "summary": summary,
        })
        set_progress(job_id, JobProgress("done", 100, "Completed"))

        return {"job_id": job_id, "summary": summary}

    except Exception as e:
        r.hset(f"job:{job_id}", mapping={"status": "failed", "error": str(e)})
        raise
    finally:
        release_idempotency_lock(job_id)
```

### 4) FastAPI: job 생성/조회 (웹은 절대 LLM을 기다리지 않는다)
```python
# app/api.py
import uuid
import redis
from fastapi import FastAPI
from pydantic import BaseModel

from app.tasks import summarize_and_index

app = FastAPI()
r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)

class CreateJobReq(BaseModel):
    document_text: str

@app.post("/jobs")
def create_job(req: CreateJobReq):
    job_id = str(uuid.uuid4())
    r.hset(f"job:{job_id}", mapping={"status": "queued", "phase": "queued", "percent": "0"})
    summarize_and_index.delay(job_id, req.document_text)
    return {"job_id": job_id, "status": "queued"}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    data = r.hgetall(f"job:{job_id}")
    return {"job_id": job_id, **data}
```

예상 동작
- `POST /jobs`는 즉시 job_id를 반환
- worker에서 LLM 요약 → 인덱싱 → `job:{id}`에 진행률/결과 저장
- `GET /jobs/{id}`로 polling(또는 WebSocket/SSE로 확장)

여기서 중요한 연결점:
- OpenAI의 **background mode**를 쓰면 “LLM 호출 자체를 vendor 쪽에서 비동기로 돌리고 polling”할 수 있습니다. 하지만 우리는 여전히 “우리 도메인 작업(인덱싱/권한/감사/재처리)”을 orchestrate해야 해서 Celery 같은 워커가 유효합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))
- 대량/비실시간 처리(예: 하루치 문서 전수 요약)는 OpenAI **Batch API**로 비용/레이트리밋을 분리해 먹는 게 훨씬 유리할 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “acks_late + idempotency”는 세트로 가져가라
`task_acks_late=True`는 신뢰성을 올리지만, 워커 재시작/네트워크/timeout 상황에서 **동일 job이 2번 실행**될 수 있습니다. LLM 비용은 즉시 2배가 됩니다.  
대응:
- job_id 기반 **idempotency lock**
- DB/Vector DB는 **upsert**(INSERT ON CONFLICT UPDATE)
- 외부 부작용(메일 발송 등)은 outbox 패턴/중복 방지 키를 반드시 적용

### Best Practice 2) Redis visibility_timeout은 “최대 작업시간”이 아니라 “장애 복구 정책”이다
문서에서는 Redis broker의 visibility timeout을 설정할 수 있지만, 신뢰성에 영향이 있고(너무 짧으면 중복 실행/재큐 폭풍), shutdown 시 unacked 메시지를 재큐잉하는 동작도 영향을 받습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html?utm_source=openai))  
권장 판단:
- LLM job의 p99 수행시간 + 네트워크 흔들림 + 워커 shutdown grace를 고려
- “30분짜리 작업”이면 visibility_timeout 30분이 아니라 **40~60분**이 안전한 경우가 많음
- 단, 너무 길면 “죽은 워커가 잡은 작업이 늦게나마 복구”되어 사용자 체감이 나빠짐 → 운영정책 선택 문제

### Best Practice 3) worker_prefetch_multiplier=1은 LLM 워크로드에서 거의 필수
prefetch가 크면 한 워커가 여러 메시지를 미리 잡아두고, 긴 LLM 작업 때문에 **큐는 길어지는데 다른 워커는 놀고** 있는 상황이 생깁니다. LLM은 작업 시간이 길고 분산이 크기 때문에 “공평한 분배”가 중요합니다.

### 흔한 함정) “Celery에서 async def를 자연스럽게 돌리겠지” 기대
Celery는 기본적으로 프로세스/스레드 기반 태스크 실행 모델이고, async-native 워크로드를 그대로 가져오면 이벤트 루프 충돌/복잡도가 올라갑니다. 현실적으로는:
- 워커에서는 **동기 http client**(또는 task 내부에서 명시적으로 asyncio.run)로 단순화
- 정말 I/O heavy이고 async-native가 중요하면 “Celery 유지 + 작업 단위를 줄이기” 또는 async-native 큐(예: Redis 기반 다른 라이브러리)를 검토  
(이 부분은 팀 운영 경험/모니터링 체계에 따라 선택이 갈립니다.)

### 비용/성능/안정성 트레이드오프(LLM 특화)
- **재시도**는 안정성을 올리지만 비용을 폭발시킴 → 429/5xx만 재시도하고, “입력 오류/정책 거절”은 즉시 실패 처리
- **결과 저장(result backend)**를 Redis에 오래 두면 메모리/운영비 증가 → 상태는 DB로, Redis는 캐시/락 용도로 최소화
- **OpenAI background mode / Batch**를 섞으면 워커 부담은 줄지만, 벤더 저장/보관 정책(ZDR 비호환 등)과 TTL(예: background polling용 임시 저장)을 이해해야 함 ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 5월에도 “LLM 백엔드 비동기 처리”에서 Celery + Redis는 충분히 강력하지만, **신뢰성은 설정이 아니라 설계(특히 idempotency)**에서 결정됩니다.

도입 판단 기준(현실 체크리스트)
- 작업이 10초 이상, 실패/재시도가 잦다 → Queue/Worker가 맞다
- 중복 실행이 치명적(비용/부작용) → idempotency/upsert/outbox 없으면 시작하지 말 것
- “대량 비실시간 처리”가 많다 → OpenAI Batch 같은 벤더 비동기와 혼합 설계를 고려 ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))
- 워커 종료/배포가 잦다 → Redis visibility timeout, shutdown 동작(soft shutdown 등)을 운영정책으로 잡아라 ([docs.celeryq.dev](https://docs.celeryq.dev/en/stable/changelog.html?utm_source=openai))

다음 학습 추천
- Celery Redis broker의 visibility timeout/ack/shutdown 동작을 “장애 시나리오”로 재현해보기(워커 kill -9, 네트워크 단절, Redis failover)
- LLM 비용 최적화: (1) 캐시/중복제거, (2) Batch 처리, (3) 실패 분류 기반 재시도 정책
- “상태 저장을 Redis에 둘지 DB에 둘지”를 팀의 운영 역량/데이터 보존 요구로 결정하기

원하시면, 위 예제를 (1) PostgreSQL에 job 테이블로 상태 영속화, (2) 작업 취소(cancel), (3) 우선순위 큐(긴 작업/짧은 작업 분리), (4) OpenAI background mode를 “워커 내부에서 polling”으로 결합하는 형태로 확장한 버전까지 이어서 작성해드릴게요.