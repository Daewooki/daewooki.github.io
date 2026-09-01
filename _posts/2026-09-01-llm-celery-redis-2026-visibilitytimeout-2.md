---
title: "LLM 백엔드에서 “Celery + Redis 비동기 큐/워커”를 2026년에 제대로 쓰는 법: 스트리밍·멱등성·visibility_timeout까지"
date: 2026-09-01 04:45:27 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-09]
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
LLM 백엔드의 비동기 처리는 “느린 작업을 요청-응답 경로에서 분리”하는 문제를 해결합니다. 특히 (1) OpenAI/사내 모델 호출이 수 초~수 분 걸리거나, (2) 한 요청이 여러 외부 API/스토리지 왕복을 포함하거나, (3) 실패 시 재시도/지연 재시도가 필요할 때 HTTP 핸들러 안에서 끝내려 하면 타임아웃·리소스 고갈·장애 전파가 발생합니다.

**언제 쓰면 좋은가**
- 사용자에게 즉시 “접수됨(queued)”만 반환하고, 결과는 폴링/웹훅/SSE로 전달해도 되는 작업(문서 생성, 배치 평가, 대량 요약/임베딩 등)
- 재시도/지연(retry/countdown)·우선순위/분리된 큐·수평 확장이 필요한 경우
- 워커를 독립적으로 스케일링하고 싶을 때(웹은 가볍게, 워커는 GPU/CPU 중심으로)

**언제 쓰면 안 되는가**
- “바로 스트리밍으로 토큰을 내보내야 하는” 인터랙티브 응답(이 경우는 요청 스레드/프로세스에서 streaming을 유지하거나 별도 스트리밍 게이트웨이가 필요)
- 정확히 한 번(exactly-once) 보장이 강하게 필요한 금융/결제성 트랜잭션(큐 자체는 at-least-once가 기본)
- 작업이 초경량이며 분산 워커/재시도가 필요 없는 경우(프로세스 내부 async task로 충분)

---

## 🔧 핵심 개념
### 1) Celery + Redis에서 “큐가 실제로” 어떻게 돌아가나
Redis broker에서 Celery는 대체로 **메시지 수신 → 처리 → ACK** 흐름을 따르며, Redis 특성상 ACK를 에뮬레이션합니다. 중요한 포인트는 **`visibility_timeout`** 입니다. 워커가 메시지를 가져갔는데 지정 시간 안에 ACK를 못 하면, Redis는 그 메시지를 “다른 워커가 다시 집어가도 된다”고 판단해 **재전달(redelivery)** 합니다. Celery 공식 문서는 이 값을 “작업이 ACK 되기까지 기다리는 시간”으로 정의하고, 너무 크게 잡는 건 신뢰성에 악영향이 있을 수 있다고 경고합니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html?utm_source=openai))

즉, LLM처럼 **작업 시간이 길고 변동이 큰** 워크로드에서는 다음이 핵심이 됩니다.
- `task_acks_late=True`(성공 후 ACK)로 “처리 중 워커 죽음”에 대비
- 그 대신 `broker_transport_options.visibility_timeout >= 최악의 작업 시간`이 필요  
  (아니면 동일 작업이 중복 실행 루프에 들어갈 수 있음) ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html?utm_source=openai))
- 다만 visibility_timeout을 무작정 키우면 “죽은 워커가 들고 있던 작업이 다시 살아나기까지” 지연이 커짐(장애 복구가 느려짐) ([docs.celeryq.dev](https://docs.celeryq.dev/_/downloads/en/4.4.0/pdf/?utm_source=openai))

추가로 2026년에도 여전히 “Celery+Redis에서 연결이 중간에 끊기면 워커가 소비를 멈추거나, long-running task의 ACK가 영영 안 나가는” 류의 이슈가 종종 보고됩니다. 이런 케이스에서 `worker_cancel_long_running_tasks_on_connection_loss` 같은 옵션과 visibility_timeout의 의미(“브로커 redelivery” vs “backend 결과 가시성”)를 구분해서 봐야 합니다. ([github.com](https://github.com/celery/celery/discussions/10415?utm_source=openai))

### 2) LLM 비동기 처리에서 “큐/워커 아키텍처”가 필요한 이유
LLM 요청은 보통 다음 성질을 가집니다.
- **I/O-heavy**: 모델 API, vector DB, object storage, 웹 크롤링 등 대기 시간이 큼
- **부분 실패가 흔함**: rate limit, 502/timeout, 네트워크 끊김
- **중복 실행에 취약**: “같은 이메일 2번 발송” 같은 부작용은 치명적

그래서 큐/워커에서의 설계 단위는 “함수 호출”이 아니라:
- **Job(작업) 레코드**(DB)에 상태를 남기고
- 워커는 “상태 머신”을 전진시키며
- 결과는 캐시/DB에 저장하고
- 클라이언트는 job_id로 조회(또는 웹훅/SSE)하는 형태가 실무적으로 가장 안전합니다.

### 3) 다른 접근과의 차이점(2026년 관점)
- **FastAPI BackgroundTasks / in-process async**: 간단하지만 프로세스 재시작/스케일아웃/재시도/관측성에서 한계
- **Redis Streams 직접 사용**: 더 정교한 스트리밍/컨슈머 그룹을 만들 수 있으나(특히 backpressure), 운영·재시도·DLQ를 직접 구현해야 함. Redis 공식 문서도 “Celery 같은 라이브러리를 쓰라”고 권장합니다. ([redis.io](https://redis.io/docs/latest/develop/use-cases/job-queue/?utm_source=openai))
- **Celery+Redis**: “가장 빨리 프로덕션에 올리기”엔 여전히 강력하지만, **visibility_timeout·prefetch·멱등성**을 이해 못 하면 LLM 워크로드에서 장애가 잘 납니다.

---

## 💻 실전 코드
아래는 “LLM 문서 생성(수 분) + 중간 상태 업데이트 + 멱등성 + 재시도 + 분리 큐”를 전제로 한 예시입니다.  
구성: `FastAPI(요청 접수)` + `PostgreSQL(작업 상태)` + `Celery worker` + `Redis(broker/result)`.

### 1) 초기 셋업 (docker + requirements)
```bash
# requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
celery==5.6.3
redis==5.0.8
sqlalchemy==2.0.32
psycopg[binary]==3.2.1
pydantic==2.8.2
```

```bash
# docker-compose.yml (개념 예시)
services:
  redis:
    image: redis:7
    ports: ["6379:6379"]
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
    ports: ["5432:5432"]
```

### 2) Celery 앱 + 워커 설정 (LLM 장기 작업 기준)
```python
# app/celery_app.py
from celery import Celery

celery = Celery(
    "llm_jobs",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # 핵심: 장기 작업 + 워커 크래시 대비
    task_acks_late=True,                 # 성공 후 ACK (중단 시 재전달)
    task_reject_on_worker_lost=True,      # 워커 죽으면 작업을 다시 큐로

    # 핵심: Redis broker의 재전달 기준(최악의 작업 시간 이상으로)
    broker_transport_options={
        "visibility_timeout": 60 * 30,    # 30분(예: 문서 생성 최악 시간에 맞춤)
        # "confirm_publish": True,        # 환경에 따라 고려(전송 확정)
    },

    # “LLM API 콜이 느린 I/O 작업”이면 prefetch를 낮춰 공정성 확보
    worker_prefetch_multiplier=1,

    # 큐 분리: short vs long
    task_routes={
        "app.tasks.generate_document": {"queue": "llm_long"},
        "app.tasks.quick_enrich": {"queue": "llm_short"},
    },
)
```

> `visibility_timeout`은 “ACK 못 받으면 재전달”이므로, LLM 작업이 10~20분까지 튈 수 있으면 그 이상으로 잡아야 중복 실행 루프를 막습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html?utm_source=openai))  
> 단, 너무 크게 잡으면 워커가 죽었을 때 복구가 느려질 수 있어 트레이드오프입니다. ([docs.celeryq.dev](https://docs.celeryq.dev/_/downloads/en/4.4.0/pdf/?utm_source=openai))

### 3) DB에 Job 상태 머신을 두고 “멱등성”으로 중복 실행을 무력화
```python
# app/models.py
import enum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Enum

class Base(DeclarativeBase): ...

class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class LLMJob(Base):
    __tablename__ = "llm_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)   # UUID를 문자열로
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED)
    input_prompt: Mapped[str] = mapped_column(Text)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

```python
# app/tasks.py
import time
from celery.utils.log import get_task_logger
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.celery_app import celery
from app.models import LLMJob, JobStatus

log = get_task_logger(__name__)
engine = create_engine("postgresql+psycopg://postgres:postgres@localhost:5432/postgres")

def _claim_job(session: Session, job_id: str) -> bool:
    """
    멱등성의 핵심: 같은 job이 중복 실행되어도
    'QUEUED -> RUNNING' 전이가 1번만 성공하게 만든다.
    """
    q = (
        update(LLMJob)
        .where(LLMJob.id == job_id, LLMJob.status == JobStatus.QUEUED)
        .values(status=JobStatus.RUNNING)
    )
    res = session.execute(q)
    return res.rowcount == 1

@celery.task(bind=True, autoretry_for=(TimeoutError,), retry_backoff=True, retry_jitter=True, max_retries=6)
def generate_document(self, job_id: str) -> str:
    with Session(engine) as session:
        if not _claim_job(session, job_id):
            log.info("Job %s already claimed; skip duplicate execution.", job_id)
            return job_id
        session.commit()

    # 여기서 실제 LLM 호출/툴 호출/파일 생성 등을 수행한다고 가정
    try:
        # (예시) 단계별 진행을 DB에 남기고 싶다면 별도 progress 컬럼/테이블 추천
        time.sleep(5)   # 모델 호출 1
        time.sleep(5)   # 모델 호출 2 (RAG)
        result_text = "generated document ..."

        with Session(engine) as session:
            job = session.scalar(select(LLMJob).where(LLMJob.id == job_id))
            job.status = JobStatus.SUCCEEDED
            job.output_text = result_text
            session.commit()

        return job_id

    except Exception as e:
        with Session(engine) as session:
            job = session.scalar(select(LLMJob).where(LLMJob.id == job_id))
            job.status = JobStatus.FAILED
            job.error = repr(e)
            session.commit()
        raise
```

### 4) FastAPI: 즉시 202 + job_id 반환, 클라이언트는 조회
```python
# app/api.py
import uuid
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, select

from app.models import Base, LLMJob, JobStatus
from app.tasks import generate_document

engine = create_engine("postgresql+psycopg://postgres:postgres@localhost:5432/postgres")
Base.metadata.create_all(engine)

app = FastAPI()

class GenerateReq(BaseModel):
    prompt: str

@app.post("/v1/docs", status_code=202)
def create_doc(req: GenerateReq):
    job_id = str(uuid.uuid4())
    with Session(engine) as session:
        session.add(LLMJob(id=job_id, status=JobStatus.QUEUED, input_prompt=req.prompt))
        session.commit()

    generate_document.delay(job_id)
    return {"job_id": job_id, "status": "queued"}

@app.get("/v1/docs/{job_id}")
def get_doc(job_id: str):
    with Session(engine) as session:
        job = session.scalar(select(LLMJob).where(LLMJob.id == job_id))
        if not job:
            return {"error": "not_found"}
        return {"job_id": job.id, "status": job.status, "output": job.output_text, "error": job.error}
```

**예상 동작**
- POST `/v1/docs` → 즉시 `{job_id, queued}`
- 워커가 처리 후 `/v1/docs/{job_id}`에서 `succeeded` + 결과 확인
- 워커가 죽거나 Redis redelivery가 발생해도 `_claim_job()` 때문에 중복 실행이 “실질적으로 무해”해짐(멱등성)

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **visibility_timeout을 “LLM 최악 시간” 기준으로 잡고, 멱등성으로 마무리**
- visibility_timeout은 Redis에서 ACK 지연 시 재전달을 유발합니다. 너무 작으면 LLM 장기 작업이 중복 실행될 수 있습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html?utm_source=openai))  
- 그렇다고 무한정 키우기보다, “중복 실행 가능”을 전제로 **Job 상태 머신 + 멱등성(조건부 업데이트)** 로 방어하는 게 실무적 정답입니다.

2) **worker_prefetch_multiplier=1로 공정성 확보**
- 기본 prefetch가 크면 “긴 작업 몇 개가 한 워커에 몰려” tail latency가 터집니다.
- LLM은 평균보다 p99가 문제라서, 공정성 튜닝이 체감이 큽니다.

3) **큐를 workload 타입별로 쪼개기(short/long, cpu/gpu, paid/free)**
- 섞어두면 priority inversion(짧은 작업이 긴 작업 뒤에 밀림)이 쉽게 발생합니다(운영 난이도는 올라가지만 효과가 큼).

### 흔한 함정/안티패턴
- **ACK/visibility_timeout 이해 없이 “acks_late만 켜기”**  
  → LLM이 2~3분만 넘어도 재전달로 중복 실행/요금 폭탄이 날 수 있습니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html?utm_source=openai))
- **결과 저장을 Celery result backend만 믿기**  
  → LLM 결과는 길고, 재처리/감사 로그가 필요합니다. DB(또는 object storage)에 “정본”을 두고 backend는 보조로.
- **Redis 연결 불안정 시 워커가 멈춘 것처럼 보이는 케이스를 무시**  
  → Celery+Redis 조합에서 연결 리셋/손실 관련 이슈가 보고되며, 장기 작업/late ack에서 더 눈에 띕니다. 운영에서 “워커 헬스체크 + 자동 재시작 + 연결 손실 시 취소/재전달 정책”을 명시해야 합니다. ([github.com](https://github.com/celery/celery/discussions/10303?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **안정성↑**: acks_late + 큰 visibility_timeout + 멱등성 + 상태 DB  
  **대가**: 장애 시 재전달까지 시간이 길어질 수 있음(복구 지연) ([docs.celeryq.dev](https://docs.celeryq.dev/_/downloads/en/4.4.0/pdf/?utm_source=openai))
- **성능↑/처리량↑**: prefetch 증가, 워커 concurrency 증가  
  **대가**: 공정성↓, tail latency↑, 장기 작업에서 “한 워커 독점” 가능
- **비용↓**: 중복 실행 방지(멱등성), 재시도 정책 정교화, “queued/running” 상태에서 사용자에게 기대치 관리

---

## 🚀 마무리
Celery+Redis는 2026년에도 “가장 빨리” LLM 백엔드 비동기 처리를 구축할 수 있는 조합이지만, LLM 워크로드에서는 **(1) at-least-once 전제, (2) visibility_timeout 수학, (3) 멱등성/상태 머신**을 이해한 팀만 편하게 씁니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html?utm_source=openai))

**도입 판단 기준**
- “요청-응답에서 분리해야 하는 느린 작업” + “재시도/분산 워커”가 필요하면: Celery+Redis 적합
- “즉시 스트리밍이 본질”이면: 큐는 후처리(비동기 생성/저장)로 제한하고, 스트리밍 경로는 별도로 설계
- “정확히 한 번”이 필요하면: 큐가 아니라 **DB 트랜잭션 기반 상태 머신 + 멱등성 키**를 중심에 두고, 큐는 실행 트리거로만 사용

**다음 학습 추천**
- Celery Redis broker의 `visibility_timeout`, `acks_late`, redelivery 동작을 문서 기준으로 다시 읽고(특히 장기 작업) ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html?utm_source=openai))
- “연결 손실 시 장기 작업 처리” 옵션과 알려진 이슈/운영 전략을 팀 런북으로 정리 ([docs.celeryq.dev](https://docs.celeryq.dev/en/v5.4.0/userguide/configuration.html?utm_source=openai))
- Redis Streams(컨슈머 그룹)로 backpressure를 직접 설계할지, Celery의 추상화로 충분할지 비교 ([redis.io](https://redis.io/docs/latest/develop/use-cases/job-queue/?utm_source=openai))