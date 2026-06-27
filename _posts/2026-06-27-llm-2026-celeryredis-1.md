---
title: "LLM 백엔드 “응답 대기열” 설계 2026: Celery+Redis로 비동기 처리의 병목·중복·유실을 없애는 법"
date: 2026-06-27 04:06:14 +0900
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
LLM을 백엔드에 붙이면 요청-응답이 “느리고 비싸고 변덕스럽다”는 문제가 한꺼번에 옵니다. 특히 (1) 모델 응답이 수 초~수 분까지 늘어나는 tail latency, (2) 재시도/타임아웃으로 인한 **중복 호출(=비용 폭탄)**, (3) 워커 재시작/장애 시 **작업 유실 또는 중복 처리**, (4) 스트리밍/폴링/웹훅 등 전달 방식이 섞이면서 생기는 상태 관리가 대표적입니다.

그래서 “HTTP 요청은 빨리 끝내고, LLM 호출은 큐로 넘겨 워커가 처리”하는 패턴(Queue/Worker)이 여전히 정답인 경우가 많습니다. Celery+Redis는 구현 난이도 대비 생산성이 높지만, LLM 워크로드에서는 **ack, visibility timeout, prefetch, idempotency** 같은 설정이 조금만 어긋나도 3AM 장애를 부릅니다(특히 Redis broker). Celery 문서에서도 Redis를 broker+backend로 쓸 수 있음을 전제하면서도 설정을 명확히 하라고 가이드합니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.0/getting-started/backends-and-brokers/?utm_source=openai))

**언제 쓰면 좋나**
- LLM 호출/후처리(검증, DB write, 파일 생성, vector upsert)가 5초 이상 걸리거나 변동 폭이 큰 경우
- “재시도 + 백오프 + dead-letter(또는 실패 저장)”가 반드시 필요한 경우
- 여러 인스턴스로 워커를 수평 확장해야 하는 경우

**언제 쓰면 안 되나**
- “정말 가벼운” 작업(수백 ms)이고 실패해도 상관 없으며, 단일 프로세스 내 BackgroundTasks 정도로 충분한 경우
- 정확히-한-번(exactly-once) 처리가 절대적으로 필요한데, 이를 위한 idempotency 키/상태 테이블을 설계할 의지가 없는 경우  
  (Celery/Redis 자체가 exactly-once를 보장해주지 않습니다. 결국 애플리케이션 레벨로 올라옵니다.)

---

## 🔧 핵심 개념
### 1) LLM 비동기 처리에서 “큐”가 해결하는 핵심
LLM 호출은 대개 I/O-bound(외부 API 호출)이고, 결과를 저장/후처리하는 단계에서 DB I/O가 붙습니다. 큐/워커 아키텍처는 다음을 분리합니다.

- **API 서버**: 요청 수락, 유효성 검증, job 생성, 즉시 202 반환
- **Queue(Broker)**: job 전달(내구성/재전달)
- **Worker**: LLM 호출 + 후처리 + 결과 저장
- **Result store**: job 상태/결과 조회(폴링, 웹훅, SSE 재연결)

Celery에서는 broker(메시지 전달)와 result backend(결과 저장)를 분리할 수 있고, Redis는 둘 다로 사용할 수 있습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.0/getting-started/backends-and-brokers/?utm_source=openai))

### 2) Celery+Redis에서 실무를 갈라먹는 내부 흐름(ack/visibility/prefetch)
LLM 작업은 “길고” “재시도 가능성 높고” “중복이 곧 돈”이라서, 다음 3개가 사실상 설계의 전부입니다.

- **prefetch**: 워커가 한 번에 가져와 쥐고 있는(task reserved) 메시지 수  
  너무 크면 특정 워커가 긴 LLM 작업을 움켜쥔 채로 다른 작업이 굶고, 장애 시 재전달도 늦어집니다.
- **acks_late**: 작업 시작 시점이 아니라 **작업 성공 후 ack**  
  워커가 죽으면(또는 강제 종료) ack가 안 되니 재전달되어 “at-least-once”로 갑니다.
- **visibility_timeout**(Redis transport): ack가 안 된 메시지를 “다른 워커가 다시 집어가도 되는 시간”  
  기본이 1시간으로 알려져 있고(문서/레퍼런스에 언급), LLM이 길어지거나 워커가 죽었을 때 재전달 타이밍에 직접 영향이 있습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/_/downloads/en/4.4.1/pdf/?utm_source=openai))  
  이 값이 기대대로 동작하지 않는 사례/질문도 지속적으로 나옵니다(운영에서 자주 밟는 지뢰). ([stackoverflow.com](https://stackoverflow.com/questions/78368062/celery-with-redis-doesnt-seem-to-honor-visibility-timeout?utm_source=openai))

**결론:** LLM 워커는 보통
- `worker_prefetch_multiplier=1`
- `task_acks_late=True`
- `visibility_timeout`은 “최대 작업 시간 + 여유”로 잡되, 너무 크게 잡아 장애 복구를 늦추지 않게 설계(= 작업을 더 잘게 쪼개거나 heartbeat/상태 저장)  
…가 기본 뼈대가 됩니다.

### 3) “큐로 비동기” vs “LLM 제공사의 비동기(Background mode)”
2026년 기준 OpenAI Responses API에는 **background mode**가 있어, 장시간 작업을 연결 유지 없이 비동기로 돌리고 `response.id`를 폴링/취소할 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))  
이건 “LLM 호출 자체”의 타임아웃/연결 문제를 크게 완화하지만, 여전히 우리 시스템에는:
- DB 트랜잭션/부작용(side effects) 처리
- 재시도 정책(모델/네트워크 오류)
- 멱등성 키, 비용 가드레일, rate limit
- 멀티스텝 파이프라인(요약→검증→저장→후속 작업)
이 남습니다. 즉 background mode는 **워커를 대체하기도** 하지만, 많은 팀에선 “워커 내부에서 LLM 호출을 더 안전하게” 만드는 옵션에 가깝습니다. (또한 background mode는 응답을 잠시 저장해 폴링하게 해주며, 저장/보존 제약이 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai)))

---

## 💻 실전 코드
현실적인 시나리오:  
“사용자가 문서를 업로드하면 → 비동기로 LLM이 구조화 추출(JSON) + 규정 준수 검증 → 결과를 DB에 저장 → 완료 시 webhook/SSE로 알림”.

아래는 **FastAPI + Celery + Redis + PostgreSQL** 조합 예시입니다. 핵심은:
1) API는 job row를 만들고 Celery task를 enqueue
2) 워커는 `job_id` 기준으로 **멱등성**(중복 실행 방지)을 보장
3) LLM 호출은 길어질 수 있으니(선택) OpenAI background mode를 사용해 폴링
4) 실패는 retry/backoff 하되, “이미 성공한 job”에는 부작용을 반복하지 않음

### 0) 의존성/실행
```bash
pip install fastapi uvicorn celery redis sqlalchemy psycopg[binary] openai
export REDIS_URL="redis://localhost:6379/0"
export DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/app"
export OPENAI_API_KEY="..."
```

### 1) Celery 설정 (prefetch/acks/timeout이 핵심)
```python
# celery_app.py
import os
from celery import Celery

REDIS_URL = os.environ["REDIS_URL"]

celery = Celery(
    "llm_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,  # 규모 커지면 backend는 DB/별도 Redis로 분리 권장
)

celery.conf.update(
    task_acks_late=True,                 # 성공 후 ack (워커 죽으면 재전달)
    worker_prefetch_multiplier=1,        # LLM 작업은 1이 안전
    task_reject_on_worker_lost=True,     # 워커 유실 시 requeue 쪽으로
    broker_transport_options={
        # Redis에서 "ack 안 된 메시지 재전달" 타이밍에 관여
        "visibility_timeout": 60 * 30,   # 30분 (작업 최대시간에 맞춰 조정)
    },
    task_default_queue="llm",
    task_routes={"tasks.process_document": {"queue": "llm"}},
)
```

### 2) Job 테이블(멱등성/상태머신)
```python
# db.py
import os
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)              # UUID
    status = Column(String, nullable=False)            # queued|running|succeeded|failed
    input_ref = Column(String, nullable=False)         # S3 key 등
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

def init_db():
    Base.metadata.create_all(bind=engine)
```

### 3) API: enqueue 후 202 반환 + 상태 조회
```python
# api.py
import uuid
from fastapi import FastAPI, HTTPException
from db import SessionLocal, Job, init_db
from celery_app import celery

app = FastAPI()

@app.on_event("startup")
def _startup():
    init_db()

@app.post("/v1/documents/{doc_id}/extract", status_code=202)
def enqueue_extract(doc_id: str):
    job_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(Job(id=job_id, status="queued", input_ref=f"s3://bucket/{doc_id}.pdf"))
        db.commit()

    celery.send_task("tasks.process_document", args=[job_id])
    return {"job_id": job_id, "status": "queued"}

@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        return {"job_id": job.id, "status": job.status, "result_json": job.result_json, "error": job.error}
```

### 4) 워커: DB 기반 멱등성 + OpenAI background mode(선택)
```python
# tasks.py
import json
import time
from celery import shared_task
from sqlalchemy import text

from celery_app import celery
from db import SessionLocal, Job

from openai import OpenAI

client = OpenAI()

def _atomic_mark_running(db, job_id: str) -> bool:
    # "queued -> running"을 원자적으로 바꿔서 중복 실행 방지
    # 이미 running/succeeded면 False
    res = db.execute(
        text("UPDATE jobs SET status='running' WHERE id=:id AND status IN ('queued','failed')"),
        {"id": job_id},
    )
    return res.rowcount == 1

@shared_task(bind=True, name="tasks.process_document", max_retries=5, default_retry_delay=10)
def process_document(self, job_id: str):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return

        # 멱등성 가드: 이미 성공한 job이면 부작용 반복 금지
        if job.status == "succeeded":
            return

        if not _atomic_mark_running(db, job_id):
            db.commit()
            return
        db.commit()

    try:
        # (예시) input_ref로 파일을 읽어 텍스트를 추출했다고 가정
        document_text = "....(extracted text)...."

        # OpenAI Responses API background mode: 긴 작업을 연결 유지 없이 수행 ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))
        resp = client.responses.create(
            model="gpt-4.1-2025-04-14",
            input=[
                {"role": "system", "content": "You extract structured fields as JSON."},
                {"role": "user", "content": f"Extract fields from:\n{document_text}\nReturn JSON only."},
            ],
            background=True,
            store=True,  # background는 store 요구(문서 제한 확인 필요)
        )

        # 폴링 (실무에선 backoff + deadline 권장)
        deadline = time.time() + 60 * 10
        while time.time() < deadline:
            r = client.responses.retrieve(resp.id)
            if r.status in ("completed", "failed", "cancelled"):
                resp = r
                break
            time.sleep(2)

        if resp.status != "completed":
            raise RuntimeError(f"LLM not completed: {resp.status}")

        result_text = resp.output_text
        payload = json.loads(result_text)

        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job and job.status != "succeeded":
                job.status = "succeeded"
                job.result_json = json.dumps(payload, ensure_ascii=False)
                job.error = None
                db.commit()

    except Exception as e:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error = str(e)
                db.commit()
        # 네트워크/429/5xx는 retry, 파싱 오류는 바로 실패 등으로 분기하는 게 이상적
        raise self.retry(exc=e)
```

**예상 동작**
- `/extract` 호출 즉시 `202`와 `job_id` 반환
- 워커가 LLM 처리 후 `jobs.status = succeeded`로 갱신
- `/jobs/{job_id}` 폴링 시 결과 JSON 확인

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “중복 실행은 반드시 일어난다”를 전제로 멱등성 설계
`acks_late=True`면 워커가 죽었을 때 재전달될 수 있습니다. 이건 장점(유실 방지)이지만, LLM 호출/DB write가 **중복 실행**될 수 있다는 뜻입니다.  
해결은 간단합니다: **job_id 단위의 상태머신 + 원자적 전이(queued→running) + succeeded면 즉시 return**. 위 예제처럼 DB UPDATE rowcount로 잠금 없이도 기본 방어가 됩니다.

### Best Practice 2) prefetch=1은 “성능 저하”가 아니라 “지연/공정성/복구” 최적화
LLM 작업은 분산이 큽니다. prefetch를 크게 두면 어떤 워커는 긴 작업을 여러 개 잡고, 다른 워커는 놀아 전체 latency가 늘어납니다. 또한 재시작 시 “잡아둔 작업”이 풀리는 타이밍도 꼬입니다. LLM 워커는 대개 `worker_prefetch_multiplier=1`이 운영적으로 이깁니다.

### Best Practice 3) visibility_timeout은 “최대 실행시간”이 아니라 “복구 목표(RTO)”로 결정
너무 짧으면 정상 실행 중인 작업이 “죽은 것으로 간주”되어 중복 실행이 늘고, 너무 길면 워커가 죽었을 때 재처리가 늦어집니다. Celery/Redis에서 visibility timeout이 운영 이슈로 자주 거론되는 이유가 여기 있습니다. ([stackoverflow.com](https://stackoverflow.com/questions/78368062/celery-with-redis-doesnt-seem-to-honor-visibility-timeout?utm_source=openai))  
권장 접근:
- 단일 작업을 30~120초 단위로 쪼개거나(파이프라인 단계화)
- LLM 호출은 provider의 background/polling으로 안정화하고(가능하면) ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))
- visibility_timeout은 “그 작업이 정말 멈췄다고 판단해도 되는 시간”으로 설정

### 흔한 함정/안티패턴
- **결과를 Celery result backend에만 저장**: Redis eviction/TTL/메모리 정책/운영 실수로 결과가 사라지면 장애 분석이 지옥입니다. “업무 결과”는 DB에 남기고, result backend는 보조로 취급하세요.
- **LLM 응답을 무조건 JSON으로 믿고 파싱**: 파싱 실패는 retry로 해결되지 않습니다. “스키마 검증 실패는 failed 처리 + 재요청(새 프롬프트) 전략”이 필요합니다.
- **재시도를 무조건 5번**: LLM 호출은 429(레이트리밋)과 5xx가 섞입니다. 오류 타입별로 backoff/최대시도/서킷브레이커를 분리해야 비용이 안 샙니다.

### 비용/성능/안정성 트레이드오프
- 안정성(유실 방지)을 위해 at-least-once로 가면 **중복 비용**이 생깁니다 → 멱등성으로 비용을 상쇄
- 처리량을 위해 concurrency를 늘리면 **429 증가** → 큐 분리(고가 작업/저가 작업), rate limiting, 우선순위 전략 필요
- Redis broker는 운영이 쉽지만, “정확한 재전달/내구성” 요구가 커지면 RabbitMQ/SQS 같은 선택지가 더 편할 수 있습니다(팀의 SRE 역량과 장애 허용치에 따라).

---

## 🚀 마무리
LLM 백엔드에서 Celery+Redis 비동기는 “그냥 비동기”가 아니라 **비용과 장애를 통제하는 아키텍처**입니다. 도입 판단 기준은 단순합니다.

- LLM 호출이 길고(>5초) 실패/재시도가 현실적으로 발생한다 → 큐/워커로 분리할 가치가 큼
- 중복 호출이 곧 돈이다 → `acks_late + idempotency + prefetch=1 + visibility_timeout 설계`가 필수
- LLM 호출 자체의 연결/타임아웃이 문제다 → OpenAI Responses API의 background mode 같은 provider 비동기를 워커 내부에서 활용하면 안정성이 올라간다 ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))

다음 학습 추천:
- Celery 공식 문서에서 Redis broker/backend, transport 옵션(visibility timeout)과 worker 설정을 다시 한 번 정독 ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.0/getting-started/backends-and-brokers/?utm_source=openai))
- OpenAI Responses API의 background mode/폴링/취소 플로우를 “우리 job 상태머신”에 어떻게 매핑할지 설계 ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))

원하시면, 위 예제를 기반으로 **(1) webhook 완료 알림**, **(2) SSE로 진행률 스트리밍**, **(3) 큐 분리(cheap vs expensive) + rate limit**, **(4) 작업 단계화(chord/chain)로 visibility_timeout 리스크 줄이기**까지 확장 버전으로 리팩터링해 드릴게요.