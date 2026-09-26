---
title: "AT&T 10DLC MMS 지연 장애와 앱 레이어 런북"
description: "통신사/벤더 의존 지연 장애를 메시지 상태 모델, 재시도·중복 억제, 사용자 커뮤니케이션, 라우팅 전략으로 흡수하는 런북을 정리합니다."
date: 2026-09-26 13:04:25 +0900
categories: ["News", "Networking"]
tags: ["10dlc", "mms", "att", "incident-response", "idempotency", "bandwidth"]
render_with_liquid: false
---

## 사건 요약: 2026-09-23 AT&T 목적지 10DLC MMS 지연

Bandwidth는 2026-09-23 12:30~18:45 UTC 동안(한국 시간 2026-09-23 21:30 ~ 2026-09-24 03:45 KST) AT&T 목적지로 발송된 10DLC MMS에서 “significant delivery delays”가 발생했다고 공지했습니다. 이 장애는 MMS 타입 중에서도 10DLC로 AT&T 가입자에게 가는 outbound 트래픽에 국한됐고, 다른 carrier나 다른 message type은 영향이 없었다고 명시합니다. ([Bandwidth 장애 공지/포스트모템](https://bandwidth.statuspage.io/incidents/kjsz31ktkz27)[^1], [Bandwidth Incident Report](https://www.bandwidth.com/support/en/articles/17141313-20260923-messaging-at-t-10dlc-mms-delivery-delays)[^2])

Statuspage 업데이트에는 “**off-network industry condition**”이라는 표현이 들어가는데, 이 문장이 실무적으로 중요합니다. 우리 애플리케이션이 아무리 정상이어도, 그리고 CPaaS/BSP 벤더가 아무리 성실해도, 최종 carrier 구간에서 생긴 조건 때문에 delivery time이 늘어날 수 있다는 뜻입니다. ([Bandwidth statuspage 업데이트](https://bandwidth.statuspage.io/incidents/kjsz31ktkz27)[^1])

Bandwidth가 2026-09-24에 게시한 Incident Report는 지연의 최대치가 “up to an hour or more”였다고 적고, 원인이 AT&T 네트워크의 configuration change로 인한 “processing channels” mismatch라서 메시지가 queueing 되었다고 설명합니다. 해결은 AT&T가 설정 불일치를 수정하고 채널을 복구하는 방식이었고, 복구 이후 관측된 최대 지연이 30초 미만으로 떨어졌다고 보고합니다. ([Bandwidth Incident Report](https://www.bandwidth.com/support/en/articles/17141313-20260923-messaging-at-t-10dlc-mms-delivery-delays)[^2])

여기서 앱 개발자가 얻어야 하는 포인트는 원인 자체가 아니라, 증상이 “실패”가 아니라 “지연”으로 나타났다는 점입니다. 지연형 장애는 모니터링·재시도·UX 커뮤니케이션에서 가장 처리하기 까다로운 클래스입니다.

---

## 지연형 장애가 까다로운 이유: 202 Accepted, webhook, DLR 시간창

Bandwidth Messaging API는 메시지 생성 시점에 `HTTP 202 - Accepted`를 반환하며, 이는 “message has been placed in the queue”를 의미한다고 문서에 적혀 있습니다. 즉, 202는 delivery 성공도 아니고 carrier handoff 성공도 아닙니다. ([Bandwidth Messaging API 문서](https://dev.bandwidth.com/docs/messaging/)[^3])

이 모델에서 우리 서비스의 상태 추적은 결국 webhook 기반이 됩니다. Bandwidth는 webhook에 대해 `HTTP 2xx`를 받을 때까지 재시도하고, 24시간이 지나도 2xx가 아니면 더 이상 전달을 시도하지 않는다고 명시합니다. webhook 전달은 “at-least-once”에 가까운 성격을 갖고, 장애 시 중복 이벤트가 생길 수 있으며, 반대로 우리 endpoint 장애로 인해 최종 이벤트를 영영 못 받을 수도 있습니다. ([Bandwidth Messaging API 문서의 Webhooks 섹션](https://dev.bandwidth.com/docs/messaging/)[^3])

또 하나는 DLR(Delivery Receipt) 시간창입니다. Bandwidth는 2026-07-06부터 DLR wait time을 2시간에서 73시간으로 늘렸고, 그 결과 message-delivered / message-failed webhook이 발송 후 최대 73시간 뒤까지 올 수 있다고 공지했습니다. ([Bandwidth: callbacks 및 DLR wait time 변경](https://www.bandwidth.com/support/en/articles/15606778-changes-to-message-delivery-callbacks-and-dlr-wait-time)[^4])

이 73시간은 단순히 벤더 내부 정책이 아니라, Bandwidth DLR FAQ에서 “carriers have up to 73 hours to return a delivery receipt”가 업계 관행으로 받아들여진다고 설명합니다. 그리고 73시간 내에 DLR이 오지 않으면 902/9902 같은 expired DLR을 받으며, 이는 “Bandwidth doesn't know the delivery state”일 수 있다고 못 박습니다. ([Bandwidth: Delivery Receipt (DLR) FAQs](https://www.bandwidth.com/support/en/articles/12823161-delivery-receipt-dlr-faqs)[^5])

carrier 레벨에서도 비슷한 시간 단위가 반복됩니다. AT&T의 소비자 지원 문서에는 단말이 꺼져 있거나 coverage 밖에 있으면 MMS가 “stored for up to 72 hours” 후 단말이 가능해지면 전달된다고 설명되어 있습니다. AT&T 약관/정책 문서에서도 메시지 delivery를 보장하지 않으며 72시간 내 미전달 시 삭제될 수 있다는 취지의 문구가 확인됩니다. ([AT&T MMS 동작 설명](https://www.att.com/support/article-modal/wireless/KM1041906/)[^6], [AT&T Consumer Service Agreement](https://www.att.com/legal/terms.consumerServiceAgreement.html)[^7])

정리하면, 지연형 장애에서 메시지는 아래 상태들을 오갑니다.

- 우리 시스템은 “보냈다”고 생각했지만 실제로는 202(큐에 적재)일 뿐
- carrier handoff는 됐지만 단말 전달은 늦어질 수 있음
- delivered/failed는 최대 73시간 늦게 올 수 있음
- webhook은 최대 24시간까지만 재시도될 수 있음

이 조건을 그대로 UX에 반영하지 않으면, 지연을 실패로 오인해서 중복 발송을 만들거나, 고객에게 잘못된 안내를 하게 됩니다.

---

## 포스트모템에서 읽어야 하는 것: “채널 mismatch”가 만든 대기열

이번 Incident Report는 원인을 “AT&T messaging platform”에서 발생한 configuration change가 “number of processing channels”와 기대치 간 mismatch를 만들어 queueing이 생겼다고 설명합니다. 즉, 네트워크가 완전히 끊긴 게 아니라 throughput/capacity가 줄어들면서 대기열이 쌓인 형태에 가깝습니다. ([Bandwidth Incident Report](https://www.bandwidth.com/support/en/articles/17141313-20260923-messaging-at-t-10dlc-mms-delivery-delays)[^2])

이 패턴은 운영 관점에서 꽤 불편합니다.

- failure rate는 크게 튀지 않을 수 있습니다(결국 도착하니까).
- 반대로 latency(P95/P99)는 급격히 늘어납니다.
- “일부 메시지만” 늦어지는 분포가 나오기 쉽습니다(큐/채널/샤딩/지역별 경로 때문에).

그리고 이런 사건은 특정 carrier, 특정 product(여기서는 AT&T + 10DLC + MMS)에서만 나타날 수 있습니다. Incident Report도 “AT&T destinations only”와 “No other carriers or message types were affected”를 별도로 강조합니다. ([Bandwidth Incident Report](https://www.bandwidth.com/support/en/articles/17141313-20260923-messaging-at-t-10dlc-mms-delivery-delays)[^2])

이 문장 하나 때문에 런북의 방향이 갈립니다. “전면 장애”면 전체 스로틀/차단/공지로 갈 수 있지만, “carrier 한정 지연”이면 라우팅·기능 제한·대상 사용자 커뮤니케이션이 더 적합합니다.

---

## 메시지 상태 모델: 지연 장애를 실패로 바꾸지 않기

지연형 장애에서 가장 먼저 손봐야 하는 건 상태 모델입니다. 상태가 빈약하면 운영이 반드시 실패합니다. 내 경우 메시지 상태를 최소 아래처럼 쪼개는 쪽으로 정리했습니다.

### 상태는 “송신”이 아니라 “관측 가능한 경계”로 나눕니다

Bandwidth 문서를 기준으로 관측 가능한 경계는 대략 이런 순서로 나뉩니다.

- **Accepted(202)**: Bandwidth 내부 큐에 적재됨 (아직 carrier handoff 전) ([Bandwidth Messaging API 문서](https://dev.bandwidth.com/docs/messaging/)[^3])
- message-sent(옵션): downstream handoff 확인이지만 carrier 처리/단말 전달을 보장하지 않음 ([Bandwidth callbacks 변경 공지](https://www.bandwidth.com/support/en/articles/15606778-changes-to-message-delivery-callbacks-and-dlr-wait-time)[^4])
- message-delivered / message-failed: DLR 기반 최종 상태(단, 73시간까지 지연 가능) ([Bandwidth callbacks 변경 공지](https://www.bandwidth.com/support/en/articles/15606778-changes-to-message-delivery-callbacks-and-dlr-wait-time)[^4])

여기서 중요한 건, message-sent도 “delivered”가 아니라는 점입니다. Bandwidth가 문서에서 transport level receipt이라고 못 박고 있습니다. ([Bandwidth callbacks 변경 공지](https://www.bandwidth.com/support/en/articles/15606778-changes-to-message-delivery-callbacks-and-dlr-wait-time)[^4])

### 상태 설계 예시

아래는 운영과 UX를 같이 고려한 상태 집합입니다.

- `CREATED`: 우리 DB에 메시지 생성(아직 벤더 전송 전)
- `SUBMITTING`: 벤더 API 호출 중
- `ACCEPTED_BY_VENDOR`: 202를 받고 벤더 큐에 들어감
- `HANDED_OFF`: message-sent(또는 intermediate DLR 성격의 이벤트) 관측
- `DELIVERED`: delivered 관측
- `FAILED_FINAL`: 실패 확정(명확한 error code + 재시도해도 의미 없는 케이스)
- `DELAY_SUSPECTED`: SLA를 넘어섰지만 실패라고 단정할 수 없는 지연 의심
- `UNKNOWN_EXPIRED`: 73시간 경과 후에도 최종 상태를 못 받음(902/9902 같은 expired DLR 성격) ([Bandwidth DLR FAQ](https://www.bandwidth.com/support/en/articles/12823161-delivery-receipt-dlr-faqs)[^5])

내가 `DELAY_SUSPECTED`와 `UNKNOWN_EXPIRED`를 분리하는 이유는 커뮤니케이션 때문입니다. “실패”라고 말하면 사용자는 재시도를 누르고, 시스템은 중복 발송을 만들고, 그 중복은 비용과 컴플라이언스를 동시에 망가뜨립니다.

---

## 재시도·중복 억제·지연 감지: 앱 레이어 런북(구체)

여기부터는 장애 대응을 “실무 런북” 형태로 정리합니다. 목표는 간단합니다.

1) carrier 지연을 실패로 오판하지 않습니다.
2) 재시도는 하되 중복 발송은 억제합니다.
3) 사용자에게는 ‘모르는 상태’를 ‘모른다’고 표현합니다.

### 1) 감지: latency 기반 SLO를 먼저 세웁니다

Bandwidth도 Messaging Insights에서 “Latency / Delivery Time”을 핵심 지표로 언급합니다. carrier 지연형 장애는 delivery rate보다 latency가 먼저 흔들립니다. ([Bandwidth: Messaging Insights Overview](https://www.bandwidth.com/support/en/articles/12823189-messaging-insights-overview)[^8])

운영적으로는 아래 두 종류를 분리해서 봅니다.

- 우리 시스템 → 벤더(202까지) 시간
- 벤더 → carrier handoff(message-sent/중간 DLR까지) 시간

Bandwidth는 message-sent callback을 “Bandwidth confirms the handoff of your message downstream”로 정의하면서, 이 신호로 end-to-end latency 추적과 큐 reconciliation을 하라고 적습니다. 이 문장이 런북의 근거가 됩니다. ([Bandwidth callbacks 변경 공지](https://www.bandwidth.com/support/en/articles/15606778-changes-to-message-delivery-callbacks-and-dlr-wait-time)[^4])

권장 알람(예시):

- AT&T 목적지 + MMS + 10DLC에서 `ACCEPTED_BY_VENDOR` 상태가 10분을 넘는 비율이 1% 초과
- AT&T 목적지 + MMS + 10DLC에서 `DELAY_SUSPECTED` 진입 건수/분이 평시 대비 5배 이상

carrier 한정 장애는 전체 평균으로 보면 숨습니다. 항상 carrier slice로 잘라야 합니다.

### 2) 재시도는 “벤더 호출 실패”에만 적용합니다

재시도를 무조건 delivery failure에 걸면, 지연 장애에서 중복 발송이 폭발합니다. 재시도는 아래 두 층으로 분리해야 합니다.

- (A) 벤더 API 호출 자체가 실패했거나 타임아웃 난 경우: 재시도 필요
- (B) 벤더에 accepted 되었으나 delivered가 늦는 경우: 재시도 금지(지연을 기다림)

(A) 계층에서 핵심은 idempotency입니다. 네트워크 오류 때문에 응답을 못 받았지만, 벤더는 이미 요청을 처리했을 수 있습니다. 이때 안전하게 재시도하려면 “같은 요청을 한 번만 처리”하는 장치가 필요합니다.

Stripe는 idempotency key를 이용해 같은 key의 요청에 대해 최초 응답을 저장하고 이후 재시도에 동일 결과를 돌려주는 방식으로 중복 실행을 막는다고 설명합니다. 메시징 벤더 API가 idempotency를 제공하지 않더라도, 우리 내부에서 동일한 원칙을 구현할 수 있습니다. ([Stripe: Idempotent requests](https://docs.stripe.com/api/idempotent_requests)[^9], [Stripe 엔지니어링 블로그: idempotency](https://stripe.com/blog/idempotency)[^10])

구현 포인트:

- “사용자 액션 1회”에 대해 `idempotency_key`를 만들고 DB에 unique로 고정
- 벤더 전송 job은 이 key를 기준으로 중복 실행을 차단
- 재시도는 `SUBMITTING` 단계에서만 수행

### 3) webhook consumer는 at-least-once로 가정하고 중복을 제거합니다

Bandwidth는 webhook을 2xx 받을 때까지 여러 번 전달하고 최대 24시간 재시도한다고 적습니다. 같은 이벤트가 여러 번 올 수 있다는 뜻입니다. ([Bandwidth Messaging API 문서](https://dev.bandwidth.com/docs/messaging/)[^3])

이 구조는 Amazon SQS standard queue가 “at-least-once delivery”라서 consumer를 idempotent하게 설계해야 한다고 말하는 것과 완전히 같은 결입니다. webhook도 결국 메시지 큐의 delivery semantics로 취급해야 합니다. ([AWS SQS: at-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html)[^11])

중복 억제는 애플리케이션 코드에서 if문으로 하는 게 아니라, DB unique constraint로 박는 게 편합니다.

- `provider_event_id`(또는 payload hash)를 unique key로 잡고 insert가 실패하면 ignore
- 이벤트 처리 함수는 “현재 상태보다 더 진전된 상태만” 적용하는 monotonic update로 작성

### 4) 지연 감지는 “carrier 특이 + 타입 특이” 룰로 둡니다

이번 사건은 AT&T + 10DLC + MMS로만 제한됐습니다. ([Bandwidth Incident Report](https://www.bandwidth.com/support/en/articles/17141313-20260923-messaging-at-t-10dlc-mms-delivery-delays)[^2])

따라서 지연 감지 룰은 아래처럼 carrier/type 별로 다르게 주는 게 좋습니다.

- SMS: 지연 감지 임계가 짧아도 됨
- MMS: payload fetching/encoding/size 제한/단말 다운로드 등 변수가 많아서 임계가 더 길어야 함

Bandwidth도 MMS는 size limit이 carrier별로 다르다고 표로 공개합니다(AT&T 10DLC MMS 1MB 등). MMS는 원래 변동성이 더 큽니다. ([Bandwidth: MMS size limits](https://www.bandwidth.com/support/en/articles/12823216-mms-size-limits)[^12])

---

## 실행 가능한 구현 예시: Postgres 기반 outbox + webhook idempotency

아래 코드는 “벤더 의존 지연 장애”를 앱 레이어에서 다루기 위한 최소 골격입니다.

- Postgres에 메시지와 이벤트를 저장합니다.
- 전송 worker는 `FOR UPDATE SKIP LOCKED`로 job을 claim합니다.
- webhook endpoint는 DB unique constraint로 중복 이벤트를 제거합니다.
- 메시지가 `ACCEPTED_BY_VENDOR` 상태로 오래 머물면 `DELAY_SUSPECTED`로 바꿉니다.

`FOR UPDATE SKIP LOCKED`는 작업 큐 구현에서 흔히 쓰는 방식이고, Postgres 문서의 explicit locking 주제에서 이런 잠금이 애플리케이션 레벨 동시성 제어에 쓰인다고 설명합니다. ([PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/17/explicit-locking.html)[^13])

### 로컬 실행 환경

- Python 3.12
- PostgreSQL 16

#### docker-compose.yml

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_USER: postgres
      POSTGRES_DB: msg
    ports:
      - "5432:5432"

  api:
    image: python:3.12-slim
    working_dir: /app
    volumes:
      - ./:/app
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:postgres@db:5432/msg
      # 실제 Bandwidth 연동 시 아래를 채웁니다.
      BW_ACCOUNT_ID: ""
      BW_USERNAME: ""
      BW_PASSWORD: ""
      BW_APPLICATION_ID: ""
      PROVIDER: mock  # mock | bandwidth
    command: bash -lc "pip install -r requirements.txt && uvicorn app.api:app --host 0.0.0.0 --port 8000"
    ports:
      - "8000:8000"
    depends_on:
      - db

  worker:
    image: python:3.12-slim
    working_dir: /app
    volumes:
      - ./:/app
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:postgres@db:5432/msg
      PROVIDER: mock
    command: bash -lc "pip install -r requirements.txt && python -m app.worker"
    depends_on:
      - db
```

#### requirements.txt

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.34
psycopg[binary]==3.2.1
pydantic==2.9.2
requests==2.32.3
```

#### 실행

```bash
docker compose up -d
```

### 스키마

```sql
-- schema.sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS outbound_message (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL,
  idempotency_key text NOT NULL,

  to_number text NOT NULL,
  from_number text NOT NULL,
  text_body text NOT NULL,
  media_url text,

  provider text NOT NULL,
  provider_message_id text,

  state text NOT NULL,
  attempt_count int NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  last_error text,

  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_outbound_state_due
  ON outbound_message (state, next_attempt_at);

CREATE TABLE IF NOT EXISTS message_event (
  id bigserial PRIMARY KEY,
  provider text NOT NULL,
  provider_event_id text NOT NULL,
  message_id uuid NOT NULL REFERENCES outbound_message(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  payload jsonb NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_event_id)
);
```

적용:

```bash
docker compose exec -T db psql -U postgres -d msg < schema.sql
```

### API 서버(app/api.py)

```python
# app/api.py
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

app = FastAPI()

class SendMMSRequest(BaseModel):
    tenant_id: str
    idempotency_key: str
    to_number: str
    from_number: str
    text_body: str
    media_url: str | None = None

@app.get("/health")
def health():
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    return {"ok": True}

@app.post("/v1/messages/mms")
def send_mms(req: SendMMSRequest):
    provider = os.getenv("PROVIDER", "mock")

    # idempotent create
    with engine.begin() as c:
        row = c.execute(
            text(
                """
                SELECT id, state
                FROM outbound_message
                WHERE tenant_id=:tenant_id AND idempotency_key=:k
                """
            ),
            {"tenant_id": req.tenant_id, "k": req.idempotency_key},
        ).fetchone()

        if row:
            return {"message_id": str(row.id), "state": row.state, "idempotent": True}

        msg_id = uuid.uuid4()
        c.execute(
            text(
                """
                INSERT INTO outbound_message
                  (id, tenant_id, idempotency_key, to_number, from_number, text_body, media_url, provider, state)
                VALUES
                  (:id, :tenant_id, :k, :to_n, :from_n, :body, :media, :provider, 'CREATED')
                """
            ),
            {
                "id": msg_id,
                "tenant_id": req.tenant_id,
                "k": req.idempotency_key,
                "to_n": req.to_number,
                "from_n": req.from_number,
                "body": req.text_body,
                "media": req.media_url,
                "provider": provider,
            },
        )

    return {"message_id": str(msg_id), "state": "CREATED", "idempotent": False}

class BandwidthWebhook(BaseModel):
    # Bandwidth webhook payload은 실제로 더 많은 필드가 있습니다.
    # 여기서는 최소 필드만 받아서 저장합니다.
    type: str
    message: dict

@app.post("/webhooks/bandwidth")
async def bandwidth_webhook(request: Request):
    payload = await request.json()

    # provider_event_id는 실제 Bandwidth payload 필드를 기준으로 잡아야 합니다.
    # 여기서는 예시로 type + message.id + timestamp 조합을 사용합니다.
    # 운영에서는 벤더가 제공하는 고유 이벤트 ID가 있으면 그걸 쓰는 게 안전합니다.
    try:
        msg_id = payload.get("message", {}).get("id")
        if not msg_id:
            raise ValueError("missing message.id")

        provider_event_id = payload.get("eventId") or f"{payload.get('type')}:{msg_id}:{payload.get('time') or ''}"
        event_type = payload.get("type") or "unknown"
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    with engine.begin() as c:
        internal = c.execute(
            text("SELECT id, state FROM outbound_message WHERE provider_message_id=:pmid"),
            {"pmid": msg_id},
        ).fetchone()

        if not internal:
            # 아직 provider_message_id 매핑을 못했거나, 다른 계정 메시지일 수 있습니다.
            # 실무에서는 별도 DLQ 테이블로 보내고 2xx를 반환해 webhook 재시도를 막는 선택도 합니다.
            return {"ok": True, "ignored": True}

        # Deduplicate events by unique(provider, provider_event_id)
        try:
            c.execute(
                text(
                    """
                    INSERT INTO message_event(provider, provider_event_id, message_id, event_type, payload)
                    VALUES(:p, :eid, :mid, :t, :payload::jsonb)
                    """
                ),
                {
                    "p": "bandwidth",
                    "eid": provider_event_id,
                    "mid": internal.id,
                    "t": event_type,
                    "payload": request._body.decode("utf-8") if hasattr(request, "_body") else str(payload),
                },
            )
        except Exception:
            # unique violation 등은 중복 이벤트로 간주
            return {"ok": True, "duplicate": True}

        # Monotonic state update
        new_state = None
        if event_type == "message-sent":
            new_state = "HANDED_OFF"
        elif event_type == "message-delivered":
            new_state = "DELIVERED"
        elif event_type == "message-failed":
            new_state = "FAILED_FINAL"

        if new_state:
            c.execute(
                text(
                    """
                    UPDATE outbound_message
                    SET state=:s, updated_at=now()
                    WHERE id=:id AND state NOT IN ('DELIVERED', 'FAILED_FINAL')
                    """
                ),
                {"s": new_state, "id": internal.id},
            )

    return {"ok": True}
```

주의할 점이 하나 있습니다. 위 webhook payload 구조는 단순화한 것이고, 실제 Bandwidth webhook의 정확한 필드명/구조는 [Bandwidth Messaging API 문서](https://dev.bandwidth.com/docs/messaging/)와 webhooks 섹션을 기준으로 맞춰야 합니다. 문서가 말하는 핵심은 “웹훅은 2xx까지 재시도하며 24시간이 지나면 중단”이라는 점입니다. endpoint는 느리거나 불안정하면 안 됩니다. ([Bandwidth Messaging API 문서](https://dev.bandwidth.com/docs/messaging/)[^3])

### 전송 worker(app/worker.py)

```python
# app/worker.py
import os
import time
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

PROVIDER = os.getenv("PROVIDER", "mock")

BW_ACCOUNT_ID = os.getenv("BW_ACCOUNT_ID", "")
BW_USERNAME = os.getenv("BW_USERNAME", "")
BW_PASSWORD = os.getenv("BW_PASSWORD", "")

BW_BASE = f"https://messaging.bandwidth.com/api/v2/users/{BW_ACCOUNT_ID}" if BW_ACCOUNT_ID else ""

# 지연 의심 기준(예시): accepted 이후 10분
DELAY_THRESHOLD = timedelta(minutes=10)

def submit_to_bandwidth(row):
    # Bandwidth는 POST /messages에 대해 202 Accepted를 반환하고, 이후 상태는 webhook으로 온다고 문서에 적혀 있습니다.
    #[^3]
    if not BW_BASE:
        raise RuntimeError("BW_ACCOUNT_ID is empty")

    url = f"{BW_BASE}/messages"

    body = {
        "from": row.from_number,
        "to": [row.to_number],
        "text": row.text_body,
    }
    if row.media_url:
        body["media"] = [row.media_url]

    resp = requests.post(url, json=body, auth=(BW_USERNAME, BW_PASSWORD), timeout=10)
    if resp.status_code != 202:
        raise RuntimeError(f"bandwidth non-202: {resp.status_code} {resp.text}")

    data = resp.json()
    # 응답의 message id 필드명은 Bandwidth API 스펙을 따라야 합니다.
    provider_message_id = data.get("id") or data.get("messageId")
    if not provider_message_id:
        raise RuntimeError(f"cannot find provider message id: {data}")

    return provider_message_id

def submit_mock(row):
    # mock provider는 provider_message_id만 만들어줍니다.
    return f"mock-{row.id}"

def main_loop():
    while True:
        # 1) due message claim
        with engine.begin() as c:
            claimed = c.execute(
                text(
                    """
                    WITH picked AS (
                      SELECT id
                      FROM outbound_message
                      WHERE state IN ('CREATED', 'RETRY_WAIT')
                        AND next_attempt_at <= now()
                      ORDER BY created_at
                      FOR UPDATE SKIP LOCKED
                      LIMIT 10
                    )
                    UPDATE outbound_message m
                    SET state='SUBMITTING', attempt_count=attempt_count+1, updated_at=now()
                    FROM picked
                    WHERE m.id = picked.id
                    RETURNING m.*
                    """
                )
            ).fetchall()

        for row in claimed:
            try:
                if PROVIDER == "bandwidth":
                    pmid = submit_to_bandwidth(row)
                else:
                    pmid = submit_mock(row)

                with engine.begin() as c:
                    c.execute(
                        text(
                            """
                            UPDATE outbound_message
                            SET state='ACCEPTED_BY_VENDOR', provider_message_id=:pmid, updated_at=now()
                            WHERE id=:id
                            """
                        ),
                        {"pmid": pmid, "id": row.id},
                    )
            except Exception as e:
                # exponential backoff (최대 5분)
                backoff_sec = min(300, 2 ** min(row.attempt_count, 8))
                with engine.begin() as c:
                    c.execute(
                        text(
                            """
                            UPDATE outbound_message
                            SET state='RETRY_WAIT',
                                next_attempt_at=now() + (:sec || ' seconds')::interval,
                                last_error=:err,
                                updated_at=now()
                            WHERE id=:id
                            """
                        ),
                        {"sec": backoff_sec, "err": str(e), "id": row.id},
                    )

        # 2) delay suspected marking
        with engine.begin() as c:
            c.execute(
                text(
                    """
                    UPDATE outbound_message
                    SET state='DELAY_SUSPECTED', updated_at=now()
                    WHERE state='ACCEPTED_BY_VENDOR'
                      AND now() - updated_at > (:thr || ' seconds')::interval
                    """
                ),
                {"thr": int(DELAY_THRESHOLD.total_seconds())},
            )

        time.sleep(1)

if __name__ == "__main__":
    main_loop()
```

위 worker는 “지연은 실패가 아니다”라는 원칙을 코드 레벨로 강제합니다.

- 벤더 호출 실패는 재시도
- 벤더 accepted 이후는 retry하지 않고 `DELAY_SUSPECTED`로만 표시

Bandwidth가 202를 큐 적재로 정의하고, delivery는 webhook에서 관측된다고 문서화했기 때문에 가능한 설계입니다. ([Bandwidth Messaging API 문서](https://dev.bandwidth.com/docs/messaging/)[^3])

---

## 사용자 커뮤니케이션: “지연”을 제품 언어로 번역하기

carrier 지연형 장애는 기술적으로는 `DELAY_SUSPECTED`지만, 제품 언어로는 번역이 필요합니다.

### 상태를 과하게 단정하지 않습니다

Bandwidth DLR FAQ는 expired DLR이 와도 “메시지가 실제로 전달됐을 수도 있다”고 설명합니다. 즉, 시스템이 모르는 상태가 존재합니다. 이걸 UI에서 “실패”로 단정하면 재시도/중복 발송으로 이어집니다. ([Bandwidth DLR FAQ](https://www.bandwidth.com/support/en/articles/12823161-delivery-receipt-dlr-faqs)[^5])

권장 UX 표현(예시):

- `ACCEPTED_BY_VENDOR` 0~N분: “전송 중”
- N분 초과(지연 의심): “전송 지연(통신사 영향)”
- 73시간 초과: “상태 확인 불가(통신사 응답 없음)”

이 표현은 사용자에게 재시도를 부추기지 않으면서도, 문제가 사용자 기기 탓이 아니라 네트워크 조건일 수 있음을 전달합니다.

### 공지 템플릿은 “대상/타입/시간창”을 박아야 합니다

이번 사건처럼 영향 범위가 좁을수록 공지에서 핵심은 범위 명시입니다.

- 대상 carrier: AT&T
- 타입: 10DLC MMS outbound
- 현상: delivery delay(최대 1시간 이상 관측 가능)
- 시간: 2026-09-23 12:30~18:45 UTC (KST로도 병기)

이 형식은 Bandwidth Incident Report 자체가 그렇게 쓰여 있기 때문에 그대로 따라가면 됩니다. ([Bandwidth Incident Report](https://www.bandwidth.com/support/en/articles/17141313-20260923-messaging-at-t-10dlc-mms-delivery-delays)[^2])

---

## 라우팅/벤더 다변화: 가능한 것과 불가능한 것

carrier 지연이 반복되면 본능적으로 “failover”를 떠올립니다. 다만 메시징은 이메일처럼 단순히 MX를 바꾸는 문제가 아닙니다. 번호, campaign, 등록(10DLC) 같은 규제가 routing을 강하게 묶습니다.

### 10DLC는 라우팅 단위를 단순화하지 않습니다

Bandwidth의 10DLC 관련 문서들만 훑어도, 10DLC는 캠페인 승인/전화번호(TN) 연결/심사(vetting) 프로세스가 있고, 승인 상태가 아니면 blocking될 수 있음을 명확히 적고 있습니다. 즉, 긴급 시 임의로 sender route를 바꾸면 deliverability가 더 떨어질 수 있습니다. ([Bandwidth: 10DLC FAQ](https://www.bandwidth.com/support/en/articles/12823085-10dlc-faq)[^14], [Bandwidth: 10DLC campaign vetting](https://www.bandwidth.com/support/en/articles/12823080-10dlc-campaign-vetting-and-phone-number-provisioning-process)[^15])

또 비용 측면에서도 carrier surcharge가 sender type/등록 여부에 따라 달라질 수 있습니다. AT&T 10DLC MMS surcharge 같은 항목이 문서에 그대로 공개되어 있습니다. 비용은 장애 대응 중에 악화되기 쉽습니다. ([Bandwidth: Carrier surcharges](https://www.bandwidth.com/support/en/articles/12823178-carrier-surcharges)[^16])

### 그럼에도 다변화가 의미 있는 지점

내가 다변화를 고려하는 지점은 크게 두 가지입니다.

1) **벤더 장애**와 **carrier 장애**를 분리해낼 수 있을 때
2) 같은 carrier라도 벤더별 interconnect/파트너/경로가 실제로 다를 때

이번 사건은 Bandwidth가 “off-network industry condition”이라고 썼고, root cause도 AT&T 네트워크 설정 변경으로 적었습니다. 이런 사건은 벤더 다변화가 즉각적인 해결책이 아닐 수 있습니다. 다만 “carrier 구간”이 아니라 “벤더 구간”이 병목인 사건(예: 벤더 내부 큐 과부하, webhook 전달 장애 등)이라면 다변화는 효과가 큽니다. ([Bandwidth statuspage](https://bandwidth.statuspage.io/incidents/kjsz31ktkz27)[^1])

실무 런북에서는 아래 기준으로 failover를 “자동”이 아니라 “수동 승인”으로 두는 편이 안전합니다.

- 지연이 특정 carrier로 제한되는가?
- 지연이 특정 message type(MMS)에만 제한되는가?
- 벤더 API 202까지도 느려졌는가?
- webhook 수신이 정상인가?

carrier 한정 지연이면, failover보다 ‘지연 상태를 제품으로 노출하고, 재시도를 억제하고, 사용자 기대치를 조정’하는 쪽이 사고를 줄입니다.

---

## 회의론: “메시징은 원래 best-effort인데 뭘 더 하나”

통신사 메시징은 약관/정책에서도 delivery를 보장하지 않는다고 쓰는 경우가 많고(AT&T 약관에도 “does not guarantee delivery”가 들어갑니다), 단말이 꺼져 있으면 72시간 저장 후 삭제될 수 있다는 식의 운영 규칙도 있습니다. ([AT&T Consumer Service Agreement](https://www.att.com/legal/terms.consumerServiceAgreement.html)[^7])

이 관점에서 보면 앱 레이어가 할 수 있는 게 없어 보입니다. 다만 장애 대응 관점에서 보면 할 수 있는 일이 꽤 많습니다.

- 지연을 실패로 오판하지 않는 상태 모델
- 중복 발송을 억제하는 idempotency/unique constraint
- webhook at-least-once에 대한 consumer 설계
- “모름”을 “모름”으로 표현하는 커뮤니케이션

그리고 이 것들은 네트워크 품질을 올리는 게 아니라, 장애 비용(중복 과금, 사용자 혼란, CS 폭증, 규정 위반 리스크)을 줄입니다. 나는 이 비용 절감이 메시징 시스템의 핵심 ROI라고 봅니다.

---

## 앞으로 지켜볼 것: 지연형 장애를 ‘관측 가능’하게 만드는 체크리스트

### (1) message-sent 콜백을 켤지 여부

Bandwidth는 2026-07-06부터 message-sent callback을 도입했고, 기존 message-sending callback은 2027-01-06에 retire된다고 공지했습니다. message-sent는 handoff 관측을 가능하게 하므로 지연형 장애 분석에 가치가 큽니다. ([Bandwidth callbacks 변경 공지](https://www.bandwidth.com/support/en/articles/15606778-changes-to-message-delivery-callbacks-and-dlr-wait-time)[^4])

### (2) webhook endpoint의 24시간 SLA

Bandwidth는 webhook을 24시간까지만 재시도한다고 문서에 명시합니다. 이건 우리가 endpoint 장애로 24시간을 넘기면 “영구히 상태를 잃을 수 있다”는 뜻입니다. 이 특성 때문에 webhook receiver는 다른 API보다도 가용성/관측성을 높게 잡아야 합니다. ([Bandwidth Messaging API 문서](https://dev.bandwidth.com/docs/messaging/)[^3])

### (3) DLR 73시간을 제품 정책으로 흡수

DLR이 73시간까지 늦을 수 있다는 사실은, ‘메시지 성공/실패를 언제 확정할 것인가’를 제품 정책으로 끌어올립니다. Bandwidth는 이 73시간이 업계 관행이라고까지 적고 있습니다. ([Bandwidth DLR FAQ](https://www.bandwidth.com/support/en/articles/12823161-delivery-receipt-dlr-faqs)[^5])

따라서 메시지 전송 기능이 중요한 서비스라면, “최대 3일 동안 상태가 바뀔 수 있음”을 시스템 설계에 포함시키는 게 맞습니다. 그걸 무시하고 5분 안에 실패 처리하면 지연 장애에서 중복 발송이 필연입니다.

### (4) carrier/type 별 latency 대시보드

Bandwidth는 Messaging Insights에서 throughput/latency/error를 모니터링할 수 있다고 설명합니다. 벤더 대시보드가 있더라도, 우리 내부 지표에서도 carrier/type slice를 반드시 만들어야 합니다. ([Bandwidth: Messaging Insights Overview](https://www.bandwidth.com/support/en/articles/12823189-messaging-insights-overview)[^8])

지연형 장애는 평균이 아니라 꼬리에서 시작합니다. P95/P99와 “상태 전이까지 걸린 시간” 분포가 런북의 출발점입니다.

---

## 참고 자료

- [Bandwidth statuspage: AT&T MMS Incident](https://bandwidth.statuspage.io/incidents/kjsz31ktkz27)
- [Bandwidth Incident Report: 20260923 | Messaging AT&T – 10DLC MMS Delivery Delays](https://www.bandwidth.com/support/en/articles/17141313-20260923-messaging-at-t-10dlc-mms-delivery-delays)
- [Bandwidth: Changes to message delivery callbacks and DLR wait time](https://www.bandwidth.com/support/en/articles/15606778-changes-to-message-delivery-callbacks-and-dlr-wait-time)
- [Bandwidth API Docs: Messaging](https://dev.bandwidth.com/docs/messaging/)
- [Bandwidth: Delivery Receipt (DLR) FAQs](https://www.bandwidth.com/support/en/articles/12823161-delivery-receipt-dlr-faqs)
- [Bandwidth: Messaging Insights Overview](https://www.bandwidth.com/support/en/articles/12823189-messaging-insights-overview)
- [AT&T Support: About Picture and Video Messaging](https://www.att.com/support/article-modal/wireless/KM1041906/)
- [AT&T Legal: Consumer Service Agreement](https://www.att.com/legal/terms.consumerServiceAgreement.html)
- [AWS SQS Developer Guide: Standard queues at-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html)
- [Stripe API Docs: Idempotent requests](https://docs.stripe.com/api/idempotent_requests)
- [Stripe Engineering Blog: Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency)
- [PostgreSQL Documentation: Explicit Locking](https://www.postgresql.org/docs/17/explicit-locking.html)
- [Bandwidth: MMS size limits](https://www.bandwidth.com/support/en/articles/12823216-mms-size-limits)
- [Bandwidth: Carrier surcharges](https://www.bandwidth.com/support/en/articles/12823178-carrier-surcharges)
- [Bandwidth: 10DLC FAQ](https://www.bandwidth.com/support/en/articles/12823085-10dlc-faq)
- [Bandwidth: 10DLC campaign vetting and phone number provisioning process](https://www.bandwidth.com/support/en/articles/12823080-10dlc-campaign-vetting-and-phone-number-provisioning-process)

[^1]: <https://bandwidth.statuspage.io/incidents/kjsz31ktkz27>
[^2]: <https://www.bandwidth.com/support/en/articles/17141313-20260923-messaging-at-t-10dlc-mms-delivery-delays>
[^3]: <https://dev.bandwidth.com/docs/messaging/>
[^4]: <https://www.bandwidth.com/support/en/articles/15606778-changes-to-message-delivery-callbacks-and-dlr-wait-time>
[^5]: <https://www.bandwidth.com/support/en/articles/12823161-delivery-receipt-dlr-faqs>
[^6]: <https://www.att.com/support/article-modal/wireless/KM1041906/>
[^7]: <https://www.att.com/legal/terms.consumerServiceAgreement.html>
[^8]: <https://www.bandwidth.com/support/en/articles/12823189-messaging-insights-overview>
[^9]: <https://docs.stripe.com/api/idempotent_requests?...=>
[^10]: <https://stripe.com/blog/idempotency>
[^11]: <https://docs.aws.amazon.com/en_gb/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html>
[^12]: <https://www.bandwidth.com/support/en/articles/12823216-mms-size-limits>
[^13]: <https://www.postgresql.org/docs/17/explicit-locking.html>
[^14]: <https://www.bandwidth.com/support/en/articles/12823085-10dlc-faq>
[^15]: <https://www.bandwidth.com/support/en/articles/12823080-10dlc-campaign-vetting-and-phone-number-provisioning-process>
[^16]: <https://www.bandwidth.com/support/en/articles/12823178-carrier-surcharges>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
