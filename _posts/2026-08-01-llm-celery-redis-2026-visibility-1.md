---
title: "LLM 백엔드에서 “Celery + Redis 큐 워커”를 2026년식으로 다시 설계하기: 비동기 처리, 중복 실행, 가시성(visibility)까지"
date: 2026-08-01 03:36:36 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-08]
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
LLM 기능을 서비스에 붙이면 요청 처리 시간이 갑자기 “수십 ms”에서 “수 초~수십 초”로 늘어납니다. 문제는 평균 지연이 아니라 **꼬리 지연(tail latency)** 과 **외부 의존성(OpenAI/사내 inference/벡터DB/S3) 변동성**이고, 이게 웹 API 스레드/프로세스를 잠식하면 곧바로 장애로 번집니다. 그래서 LLM 백엔드에서 큐/워커 아키텍처는 “옵션”이 아니라 **격리(isolation)와 재시도(retry), 속도 제한(rate limit), 비용 제어(cost control)** 를 위한 기본 도구가 됩니다.

**언제 쓰면 좋나**
- LLM 호출이 길거나(초 단위), 외부 API 쿼터/레이트리밋이 빡세서 **지연·재시도·백오프가 필요**할 때
- “요청-응답”이 아니라 **job 기반(요약 생성, 임베딩 배치, 문서 인덱싱, 평가/실험 파이프라인)** 으로 설계할 수 있을 때
- 실패/중복 실행을 “시스템적으로” 다룰 준비(멱등성 키, 상태 저장, DLQ)가 있을 때

**언제 쓰면 안 되나**
- 사용자에게 즉시 결과가 필요한데(예: 채팅 스트리밍) 큐잉이 오히려 UX를 망칠 때
- 작업이 너무 가벼워서(수십 ms) 큐 오버헤드가 더 클 때
- “정확히 한 번(exactly-once)”을 시스템이 보장해줄 거라 착각하고 설계를 미루는 경우(대부분의 큐/워커는 기본적으로 at-least-once임)

추가로 2026년 관점에서, “LLM 호출을 꼭 내 워커가 실시간으로 처리해야 하나?”도 다시 봐야 합니다. OpenAI의 **Batch API**는 대량 요청을 비동기 배치로 처리하고(처리 윈도우 24h), 비용 할인까지 제공하므로 “지금 당장 필요 없는 LLM 작업”은 큐 대신 Batch로 보내는 게 더 합리적일 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/api-reference/batch/object?api-mode=responses&utm_source=openai))

---

## 🔧 핵심 개념

### 1) Celery + Redis의 “진짜” 실행 흐름(중요)
Celery를 Redis broker로 쓰면, 겉으로는 “Redis list에 넣고 worker가 pop한다” 정도로 보이지만, 실무에서 중요한 건 다음 세 가지입니다.

1. **prefetch**
   - Celery worker는 기본적으로 “처리 가능한 슬롯 수 × prefetch multiplier”만큼 **미리** 작업을 가져옵니다.
   - LLM 작업처럼 처리 시간이 들쭉날쭉하면 prefetch가 **priority inversion(짧은 작업이 긴 작업 뒤에 갇힘)** 을 만든 주범이 됩니다.
   - 그래서 대부분의 LLM 워커는 `worker_prefetch_multiplier=1`이 출발점입니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/stable/userguide/configuration.html?highlight=task_create_missing_queues&utm_source=openai))

2. **acks_late (late acknowledgment)**
   - `acks_late=True`는 “작업을 **성공적으로 끝낸 뒤에 ack**”하겠다는 의미입니다.
   - 워커가 작업 중 죽으면 브로커는 “미완료”로 보고 재전달(redeliver)할 수 있어 **유실 방지**에 유리합니다.
   - 대신 **중복 실행 가능성**이 올라갑니다(at-least-once). 이걸 감당하려면 멱등성 설계가 필수입니다.

3. **visibility_timeout**
   - Redis/SQS 같은 일부 브로커는 “worker가 잡아간 작업을 일정 시간 후 다시 보이게(재전달) 하는” 가시성 타임아웃을 둡니다.
   - LLM 작업 시간이 이 timeout을 넘어가면, **작업이 아직 잘 돌고 있는데도 다른 워커에 재할당**될 수 있습니다. Airflow 문서도 이 함정을 명확히 경고합니다. ([airflow.apache.org](https://airflow.apache.org/docs/apache-airflow-providers-celery/stable/configurations-ref.html?utm_source=openai))
   - 결론: **timeout은 ‘최장 작업시간 + 여유’** 로 잡고, 그보다 긴 작업은 애초에 쪼개거나(청크/스텝), 하트비트/체크포인트 패턴으로 설계를 바꿔야 합니다. Celery 설정 문서도 visibility timeout 설정과 prefetch 제어를 함께 언급합니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/stable/userguide/configuration.html?highlight=task_create_missing_queues&utm_source=openai))

### 2) “LLM 비동기 처리”에서 큐의 역할은 CPU가 아니라 I/O와 정책
LLM 워커는 흔히 “GPU/CPU를 최대 활용” 같은 얘기를 하지만, 실제로 백엔드에서 더 자주 터지는 건:
- OpenAI/사내 inference endpoint **rate limit**
- 네트워크 타임아웃, 일시적 5xx
- S3/DB/Vector DB I/O 지연
- 특정 테넌트/유저의 과도한 사용(비용 폭탄)

큐/워커는 그래서 “비동기 실행”뿐 아니라,
- **테넌트별 속도 제한**
- **재시도 + 백오프**
- **우선순위 큐(interactive vs batch) 분리**
- **DLQ(Dead Letter Queue)**
를 위한 정책 엔진입니다.

### 3) Redis 자체로 job queue를 만들 수도 있다(Streams)
Redis는 공식 문서/튜토리얼에서 **Redis Streams + Consumer Group**으로 신뢰성 있는 작업 큐(재시도, DLQ 포함)를 만드는 패턴을 직접 안내합니다. ([redis.io](https://redis.io/tutorials/redis-backed-job-queue-for-background-workers/?utm_source=openai))  
Celery가 “표준 배터리 포함”이라면, Streams는 “내가 필요한 의미론을 직접 설계”하는 쪽입니다. LLM 워크플로우가 복잡해질수록(단계적 처리, 체크포인트, 부분 결과 저장) Streams가 더 깔끔해지는 경우도 많습니다.

---

## 💻 실전 코드
아래 예제는 “LLM 요약 작업”을 **HTTP 요청에서 분리**하고, **상태 저장/멱등성/재시도/관측**까지 들어간 형태입니다.

- API 서버: job 생성 + job 상태 조회
- Worker(Celery): Redis 큐에서 job을 받아 OpenAI Responses API 호출(예시), 결과 저장
- Redis: broker + (간단히) 상태 저장 캐시 용도
- 포인트: `acks_late`, `prefetch_multiplier=1`, `visibility_timeout` 튜닝 + **멱등성 키(job_id)** 기반 중복 실행 방지

### 0) 의존성 / 실행
```bash
python -m venv .venv
source .venv/bin/activate

pip install "celery[redis]" fastapi uvicorn redis pydantic openai

# Redis 실행(로컬)
docker run -p 6379:6379 --name redis -d redis:7

# worker 실행
celery -A worker.app worker -l INFO -c 4

# API 실행
uvicorn api:app --reload --port 8000
```

### 1) Celery 앱/워커 설정 (worker/app.py)
```python
# worker/app.py
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "llm_jobs",
    broker=REDIS_URL,
    backend=REDIS_URL,  # 결과 저장을 Celery backend로도 가능(여기선 job 상태는 별도 저장)
)

celery_app.conf.update(
    task_acks_late=True,                 # 작업 완료 후 ack
    worker_prefetch_multiplier=1,        # LLM처럼 변동 큰 작업에서 필수급
    broker_transport_options={
        # 최장 작업시간(예: 10분) + 여유(예: 5분)
        "visibility_timeout": 15 * 60
    },
    task_reject_on_worker_lost=True,     # 워커 죽으면 작업을 다시 큐로
    task_default_queue="llm.default",
)
```

### 2) 현실적인 작업: 요약 생성 + 멱등성 + 재시도 (worker/tasks.py)
```python
# worker/tasks.py
import json
import os
import time
from celery import shared_task
from redis import Redis

# OpenAI SDK는 환경에 맞게 설정(예: OPENAI_API_KEY)
from openai import OpenAI

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = Redis.from_url(REDIS_URL, decode_responses=True)

client = OpenAI()

def job_key(job_id: str) -> str:
    return f"job:{job_id}"

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=6,
    acks_late=True,
)
def summarize_job(self, job_id: str):
    """
    job_id로 멱등성 확보:
    - 이미 DONE이면 중복 실행 방지
    - RUNNING 상태에서 워커가 죽으면 재실행될 수 있으므로,
      '중복 실행 가능'을 전제로 상태 전이를 설계한다.
    """
    k = job_key(job_id)
    raw = r.get(k)
    if not raw:
        # job이 없으면 논리 오류(재시도 의미 없음): 실패로 처리
        raise RuntimeError(f"job not found: {job_id}")

    job = json.loads(raw)

    # 멱등성: 완료면 바로 반환
    if job.get("status") == "DONE":
        return {"job_id": job_id, "status": "DONE", "cached": True}

    # RUNNING 전이(낙관적 락이 필요하면 WATCH/MULTI 사용 권장)
    job["status"] = "RUNNING"
    job["started_at"] = int(time.time())
    r.set(k, json.dumps(job), ex=24 * 3600)

    text = job["payload"]["text"]
    prompt = job["payload"].get("prompt") or "다음 글을 핵심만 요약해줘."

    # (예시) OpenAI Responses API 호출 형태로 작성
    # 실제 모델/파라미터는 조직 정책에 맞춰 조정
    resp = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=[
            {"role": "system", "content": "You are a precise Korean summarizer."},
            {"role": "user", "content": f"{prompt}\n\n---\n{text}"},
        ],
        temperature=0.2,
    )

    summary = resp.output_text  # SDK 버전에 따라 접근 방식은 다를 수 있음

    job["status"] = "DONE"
    job["finished_at"] = int(time.time())
    job["result"] = {"summary": summary}
    r.set(k, json.dumps(job), ex=24 * 3600)

    return {"job_id": job_id, "status": "DONE"}
```

### 3) API: job 생성/조회 (api.py)
```python
# api.py
import json
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis import Redis

from worker.app import celery_app
from worker.tasks import summarize_job, job_key

app = FastAPI()
r = Redis.from_url("redis://localhost:6379/0", decode_responses=True)

class SummarizeRequest(BaseModel):
    text: str
    prompt: str | None = None

@app.post("/jobs/summarize")
def create_job(req: SummarizeRequest):
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "type": "summarize",
        "status": "QUEUED",
        "payload": {"text": req.text, "prompt": req.prompt},
    }
    r.set(job_key(job_id), json.dumps(job), ex=24 * 3600)

    # Celery enqueue
    summarize_job.apply_async(args=[job_id], queue="llm.default")

    return {"job_id": job_id, "status": "QUEUED"}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    raw = r.get(job_key(job_id))
    if not raw:
        raise HTTPException(404, "job not found")
    return json.loads(raw)
```

**예상 동작**
1) `/jobs/summarize` 호출 → 즉시 `job_id` 반환  
2) worker가 Redis 큐에서 job을 가져가 실행  
3) `/jobs/{job_id}`로 상태가 `QUEUED → RUNNING → DONE` 전이

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) “LLM 작업”은 큐를 분리하라 (interactive vs batch)
LLM 백엔드는 작업 시간이 크게 갈립니다. 같은 큐에 섞으면 prefetch를 1로 줄여도 “긴 작업이 짧은 작업을 막는” 현상이 남습니다.
- `llm.interactive`: 사용자 대기 UX에 직결
- `llm.batch`: 야간 인덱싱/리포트/평가
- `llm.embedding`: 고정 비용/고정 처리량

레딧 실무 사례에서도 “혼합 워크로드에서 priority inversion이 심해져 큐를 분리했다”는 경험담이 반복됩니다(신뢰도는 낮지만, 현상 자체는 흔합니다). ([reddit.com](https://www.reddit.com/r/Python/comments/1u775lo/choosing_a_python_task_queue_library_in_2026/?utm_source=openai))

### Best Practice 2) `acks_late=True`는 “유실 방지”가 아니라 “중복 실행을 받아들이는 계약”
`acks_late`를 켜면 안정성이 좋아진다고들 하지만, 실제로는:
- 유실은 줄어들 수 있으나
- **중복 실행은 늘어납니다**
따라서 필수 체크리스트:
- job_id 기반 **멱등성 키**
- “이미 DONE이면 반환” 같은 **상태 기반 short-circuit**
- 외부 side-effect(이메일 발송/결제/DB write)는 **outbox 패턴** 또는 “한 번만 실행” 락

### Best Practice 3) visibility_timeout은 “최장 실행시간 + ECS/K8s 종료 시간”까지 고려
Airflow의 Celery provider 문서가 말하듯, 실행 시간이 visibility_timeout을 넘으면 “정상 실행 중인데도 재할당”이 일어납니다. ([airflow.apache.org](https://airflow.apache.org/docs/apache-airflow-providers-celery/stable/configurations-ref.html?utm_source=openai))  
또한 컨테이너 오케스트레이션에서는 scale-down 시 SIGTERM 후 강제 종료까지 시간이 있으므로, **worker 종료 유예(grace period)** 를 최장 작업보다 길게 잡아야 합니다(그렇지 않으면 중간에 죽고 재실행 루프). 관련 논의가 2026년에도 꾸준히 나옵니다. ([reddit.com](https://www.reddit.com/r/Python/comments/1uleyez/celery_on_aws_ecs_prevent_lost_tasks_and_ensure/?utm_source=openai))

### 흔한 함정 1) Celery result backend를 “진짜 상태 저장소”로 쓰기
Celery의 `AsyncResult`/result backend는 편하지만, LLM 시스템의 상태는 보통
- 부분 결과(스트리밍/청크),
- 비용 메타데이터,
- 재시도 횟수/실패 원인 분류,
- 사람이 재처리할 수 있는 DLQ
까지 필요합니다. Celery result는 그 용도에 최적화되어 있지 않습니다(가능은 해도 운영 난이도가 급상승). Celery의 결과 객체/백엔드 API 자체는 참고로 두되, **업무 상태는 별도 저장(예: DB/Redis hash + TTL)** 을 권장합니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/stable/reference/celery.result.html?utm_source=openai))

### 흔한 함정 2) Redis를 “브로커+캐시+락+레이트리밋”까지 한 인스턴스에 몰아넣기
LLM 트래픽이 커지면 Redis는 생각보다 빨리 병목이 됩니다(메모리/네트워크/지연 스파이크). 최소한:
- broker용 DB/클러스터 분리
- 결과/상태 TTL 엄격히
- 완료 job 청소 정책
을 가져가야 합니다. Redis 측에서도 “job queue는 신뢰성 패턴이 중요하고, 가능하면 검증된 라이브러리를 쓰라”고 권합니다. ([redis.io](https://redis.io/docs/latest/develop/use-cases/job-queue/?utm_source=openai))

### 트레이드오프 요약
- Celery(+Redis): 빠른 도입, 풍부한 기능 / 하지만 asyncio-native가 아니고, LLM처럼 “긴 I/O + 변동 큰 작업”에서 튜닝 없으면 비효율
- Redis Streams 직접 구현: 의미론을 원하는 대로(재시도/DLQ/클레임) / 하지만 구현·운영 책임이 내게 옴(튜토리얼 패턴은 훌륭한 출발점) ([redis.io](https://redis.io/tutorials/redis-backed-job-queue-for-background-workers/?utm_source=openai))
- OpenAI Batch: “지금 당장” 필요 없는 작업의 비용/운영 복잡도 절감 / 단, 24h 윈도우 같은 제약이 있음 ([platform.openai.com](https://platform.openai.com/docs/api-reference/batch/object?api-mode=responses&utm_source=openai))

---

## 🚀 마무리
핵심은 “비동기”가 아니라 **격리 + 재시도 + 중복 실행을 전제로 한 설계**입니다. 2026년 8월 기준으로 Celery+Redis는 여전히 유효하지만, LLM 워크로드에서는 반드시:
- `worker_prefetch_multiplier=1`
- `acks_late=True` + 멱등성/상태 전이 설계
- `visibility_timeout`을 최장 작업시간과 배포 환경(종료 유예)까지 포함해 튜닝
을 기본값으로 잡고 시작해야 합니다. ([docs.celeryq.dev](https://docs.celeryq.dev/en/stable/userguide/configuration.html?highlight=task_create_missing_queues&utm_source=openai))

**도입 판단 기준(실무용)**
- “실시간 UX” 중심이면: 큐는 최소화하고(또는 interactive 전용 큐), 스트리밍/취소/타임아웃 설계를 먼저
- “비동기 배치/인덱싱/평가” 중심이면: Celery 또는 Redis Streams, 더 나아가 OpenAI Batch까지 조합 ([platform.openai.com](https://platform.openai.com/docs/api-reference/batch/object?api-mode=responses&utm_source=openai))
- “정확히 한 번”이 필요하면: 큐를 바꾸기 전에 **업무 레벨 멱등성 + outbox + 재처리 툴링(DLQ)** 부터

다음 학습으로는 (1) Celery concurrency/prefetch/acks 설정 문서를 실제 설정값과 함께 정독하고 ([docs.celeryq.dev](https://docs.celeryq.dev/en/stable/userguide/concurrency/index.html?utm_source=openai)), (2) Redis Streams consumer group 기반 job queue 튜토리얼을 한 번 직접 구현해보는 것을 추천합니다(특히 DLQ/claim/retry). ([redis.io](https://redis.io/tutorials/redis-backed-job-queue-for-background-workers/?utm_source=openai))