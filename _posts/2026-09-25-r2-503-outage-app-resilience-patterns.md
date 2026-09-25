---
title: "Cloudflare R2 503 장애 대응: 객체 스토리지 의존성 분해"
description: "R2/S3 객체 스토리지에서 503이 터질 때 업로드·다운로드·presigned URL·백그라운드 작업을 분리하고 재시도/큐잉/캐시/멀티리전/서킷브레이커 패턴을 정리합니다."
date: 2026-09-25 10:03:09 +0900
categories: ["News", "Cloud"]
tags: ["cloudflare-r2", "object-storage", "resilience", "retry-backoff", "circuit-breaker", "multi-region"]
render_with_liquid: false
---

## 사건 정리: 2026-09-23 SYD R2 503 상승

Cloudflare Statuspage에는 **"Elevated number of R2 503 errors in Australian Eastern Coast region"** 사건이 기록돼 있습니다. 해당 인시던트는 2026-09-23 04:08 UTC에 Investigating으로 시작해, 04:09 UTC에 Identified, 04:22 UTC에 Monitoring, 04:25 UTC에 Resolved로 종료됐습니다.[^1]  
KST(UTC+9)로 환산하면 2026-09-23 13:08~13:25 KST 구간입니다.

영향 범위는 Statuspage 기준으로 *Oceania (Sydney, NSW, Australia - (SYD))* 및 *Cloudflare Sites and Services (R2)*로 표시돼 있습니다.[^1]

이 사건이 재밌는 이유는 두 가지입니다.

첫째, 17분 남짓으로 짧게 끝난 장애였지만, 객체 스토리지를 동기식으로 붙여둔 애플리케이션은 “짧은 503 스파이크”를 그대로 앱 장애로 증폭시키기 쉽습니다.

둘째, R2는 S3-compatible API를 제공하기 때문에(즉, SDK/미들웨어가 이미 재시도 같은 내구성 로직을 갖고 있기 때문에) 설계가 방심으로 흐르기 쉽습니다. 하지만 SDK 재시도만 믿고 앱 경계(critical path)를 정리하지 않으면, 503은 여전히 서비스 전체를 멈춥니다.

이 글은 상태페이지 사건을 계기로, R2/S3류 객체 스토리지에서 503이 터질 때 앱이 무너지는 지점을 분리하고, 재시도·큐잉·캐시·멀티리전·서킷브레이커를 어디에 두는지 런북 관점에서 정리한 기록입니다.

(Cloudflare 장애가 SLO를 깨는 경로 자체는 예전에 쓴 [Cloudflare Ashburn(IAD) 구간 5xx 급증이 SLO를 깨는 방식](https://daewooki.github.io/posts/cloudflare-iad-pop-outage-slo/)에서 다뤘으니, 여기서는 객체 스토리지 의존성에만 집중합니다.)

## 배경 맥락: R2의 “리전”과 앱이 기대하는 것의 간극

Cloudflare R2는 API 표면이 세 갈래로 나뉩니다.

- Workers binding을 통한 Workers API
- `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` 형태의 S3-compatible API
- Cloudflare REST API(대시보드/Wrangler가 쓰는 관리/제어용)

Cloudflare 공식 문서에 이렇게 정리돼 있습니다.[^2]

또 하나의 중요한 포인트는 “데이터 위치”입니다. R2는 버킷 생성 시 기본값이 Automatic이고, 상황에 따라 Location Hint 또는 Jurisdictional Restriction을 설정할 수 있습니다. Location Hint로는 `oc`(Oceania) 같은 값을 줄 수 있습니다.[^3]

여기서 앱이 흔히 착각하는 지점이 있습니다.

- “R2는 Cloudflare라서 PoP마다 데이터가 있고, 사실상 CDN처럼 어느 리전 장애는 크게 티가 안 나겠지”라는 기대
- “객체 스토리지는 어차피 durable하니까, 장애는 데이터 유실이 아니라 잠깐의 503이고, SDK가 재시도하면 끝”이라는 기대

R2의 durability 설명을 보면, 업로드된 객체는 복제/erasure coding으로 여러 사본이 만들어지고, 하드웨어는 *특정 geographic region 내 여러 data center에 분산*된다고 설명합니다. 즉, durability가 “리전 내부 분산”을 전제합니다.[^4]

따라서 특정 지역(이번 케이스로는 SYD)에 503이 치솟았다는 것은, 데이터가 안전하냐와 별개로 “그 리전에 매달린 앱의 요청 성공률이 급격히 흔들릴 수 있다”는 얘기입니다. 이때 앱이 R2를 어떻게 호출하느냐가 승패를 가릅니다.

## 왜 중요한가: 503은 저장소가 아니라 사용자 여정에서 터진다

R2 503은 앱 코드 관점에서 다음 네 가지로 번역됩니다.

1. 업로드 실패(사용자 생성 콘텐츠 유입이 막힘)
2. 다운로드 실패(이미 업로드된 콘텐츠 제공이 막힘)
3. presigned URL 흐름의 오해(서명 URL은 발급되는데 업로드가 안 됨)
4. 백그라운드 작업 정체(재시도 폭주로 큐가 터지고, 복구 후에도 backlog가 남음)

여기서 정말 치명적인 건 2번입니다. 업로드는 UX로 설득이 되지만(재시도/나중에 다시), 다운로드 실패는 바로 “서비스가 깨졌다”로 인지됩니다.

그리고 3번이 운영을 곤란하게 만듭니다. Cloudflare 문서 기준, R2 presigned URL은 AWS SigV4로 생성하며 **R2와 통신 없이 서버 측에서 생성**됩니다.[^5]  
즉, R2가 503을 뿜고 있어도 서버는 presigned URL을 멀쩡히 발급할 수 있습니다. 그러면 모니터링이 이렇게 왜곡됩니다.

- API 서버는 200을 잘 준다(겉보기 정상)
- 사용자의 업로드 PUT은 503으로 죽는다(실제 장애)

이 괴리를 흡수하는 설계를 해두지 않으면, 장애 분석이 늦어지고, 책임 소재가 엉키고, 무엇보다 “동일한 장애의 재발”을 막을 런북이 업데이트되지 않습니다.

## 503이 앱을 무너뜨리는 지점: 업로드/다운로드/서명/배치의 경계

### 업로드: 동기 트랜잭션에 PUT을 섞는 순간부터 진다

가장 흔한 안티패턴은 이겁니다.

- `POST /posts`(DB insert) 중간에 R2 `PutObject`를 호출하고
- 업로드가 성공해야만 DB 커밋을 하고
- 실패하면 전체 요청을 5xx로 던진다

이 방식은 “짧은 503”을 “DB write 차단”으로 증폭합니다. 결과적으로 장애가 스토리지에서 시작해 API 전체로 전파됩니다.

여기서 분리해야 하는 건 **업로드를 비즈니스 트랜잭션에서 떼어내는 것**입니다.

- DB에는 “업로드 의도(upload intent)”만 기록하고
- 실제 업로드는 presigned URL로 클라이언트가 직접 R2에 수행하고
- 업로드 완료 후 별도 콜백/검증 루틴이 상태를 `READY`로 바꿉니다.

Cloudflare 문서도 “브라우저/모바일이 Worker를 경유하지 않고 R2에 직접 업로드하려면 presigned URL을 발급하라”는 가이드를 갖고 있습니다.[^6]

여기서 중요한 운영 포인트가 하나 더 있습니다. presigned URL은 **custom domain에서 동작하지 않고 S3 API 도메인에서만 동작**합니다.[^5]  
즉, “다운로드는 커스텀 도메인 + 캐시로 안정화”를 하더라도 “업로드는 S3 API 엔드포인트 의존”이 남습니다. 이 분리가 설계 문서에 명확히 들어가야 합니다.

### 다운로드: R2를 직접 때리는지, 캐시를 두는지가 안정성을 가른다

R2의 가장 큰 장점 중 하나는 “Cloudflare Cache를 앞에 둘 수 있다”는 점입니다. Public bucket을 custom domain으로 붙이면 캐시를 사용할 수 있고, `r2.dev` 개발 URL은 프로덕션에 부적절하다고 문서에 명시돼 있습니다(레이트 리밋, WAF/캐시 미지원 등).[^7]

다운로드 경로를 이렇게 두 갈래로 분리하는 게 운영이 쉽습니다.

- **Hot path**: 사용자-facing 다운로드(이미지, JS, 첨부파일)는 custom domain + CDN cache를 기본으로 둔다
- **Cold path**: 내부 처리/백오피스/배치 다운로드는 S3 API 또는 Workers binding으로 직접 읽되, 큐 기반 재시도로 다룬다

여기서 캐시는 단순히 성능이 아니라 “장애 완충재” 역할을 합니다.

- R2가 잠깐 503을 내도, 캐시에 남아 있는 객체는 계속 서빙된다
- `stale-if-error` 같은 정책을 쓰면, 원본 fetch가 5xx를 내는 동안에도 캐시된 응답을 내보낼 수 있다

Cloudflare Workers 캐시 설정 문서에는 `stale-if-error`가 “Worker가 refresh 중 5xx를 반환할 때 이전 캐시를 돌려주는” 동작으로 설명돼 있습니다.[^8]

다만 R2는 “R2 자체의 strong consistency”와 “캐시를 앞에 둔 consistency”가 다릅니다. R2는 강한 일관성을 강조하지만, custom domain + 캐싱을 켜면 캐시 때문에 삭제/갱신이 즉시 반영되지 않을 수 있고, 404조차 캐싱될 수 있다고 공식 문서가 경고합니다.[^9]

다운로드 경로에 캐시를 넣는 순간, 운영 관점에서는 “스토리지는 strong consistent인데 서빙은 eventual-ish”가 됩니다. 이건 나쁜 게 아니라, 장애 내성을 얻기 위한 대가입니다.

### presigned URL: “발급”과 “성공”을 분리해서 관측해야 한다

R2 presigned URL은 서버에서 로컬로 생성하며 R2와 통신하지 않습니다.[^5]  
이 특성 때문에 장애 시에 다음이 동시에 벌어집니다.

- `POST /upload-intents`는 계속 200
- 실제 PUT은 503

따라서 모니터링을 이렇게 분리하는 게 낫습니다.

- presigned URL 발급 성공률(서버 로직/인증 문제)
- 실제 업로드 성공률(클라이언트의 PUT 결과 수집)

내 경우 “업로드 성공률”은 클라이언트가 업로드 후 `upload-complete` API를 호출할 때, 서버가 `HeadObject`로 확인하는 방식으로 잡았는데, 이때도 장애 시 `HeadObject`가 503을 내면서 false negative가 됩니다. 그래서 `upload-complete`는 **즉시 확인하지 않고 비동기 검증 잡으로 넘기는** 쪽이 운영이 편했습니다.

### 백그라운드 작업: 503이 “큐 붕괴”로 전이되는 전형적인 경로

객체 스토리지가 잠깐 흔들릴 때 제일 많이 망가지는 건 배치/워커입니다.

- 워커가 `GetObject`에서 503을 맞고
- 즉시 재시도(또는 많은 동시성)로 스토리지를 더 때리고
- 재시도 폭주가 스토리지/네트워크/워커를 함께 태우고
- 장애가 끝나도 backlog가 남아 몇 시간 동안 지연이 이어집니다

AWS 쪽 문서들도 503에 대해 “exponential backoff로 재시도하라”고 반복해서 말합니다. 예를 들어 S3 성능 패턴 문서는 503(특히 Slow Down)에 대해 exponential backoff를 권장합니다.[^10]  
AWS SDK 전반의 retry behavior 문서도 지터(jitter)가 있는 exponential backoff를 표준으로 설명합니다.[^11]

R2를 S3 SDK로 접근할 때도 같은 원칙이 먹히지만, 워커 레벨에서는 한 단계가 더 필요합니다.

- SDK retry는 “요청 하나”의 성공률을 올려준다
- 워커 설계는 “요청 폭주”를 막아준다

즉, 워커에는 (1) 재시도, (2) 동시성 제한, (3) 서킷브레이커, (4) 큐 지연(재예약) 이 네 가지가 같이 있어야 합니다.

## 패턴 정리: 재시도·큐·캐시·멀티리전·서킷브레이커를 어디에 둘까

이 섹션은 구성요소별로 “무엇을 어디에 두는 게 좋은가”를 정리합니다. 핵심은 **503을 처리하는 로직을 한 군데에 몰아넣지 않는 것**입니다.

### 1) Retry는 “클라이언트/서버/워커”에 서로 다른 책임으로 둔다

- 브라우저/모바일 클라이언트: 업로드 PUT 재시도(네트워크 단절/503) + 진행률 유지(가능하면 multipart)
- API 서버: presigned URL 발급은 빠르게, 저장소 호출은 최소화. 필요하면 짧은 재시도만
- 백그라운드 워커: 긴 재시도는 워커에서. 대신 지수 백오프 + 최대 지연 + 잡 재예약으로 처리

AWS Well-Architected Framework는 재시도를 하더라도 backoff/jitter/최대 재시도 한도를 두라고 강조합니다.[^12]  
이 내용은 객체 스토리지에 특히 잘 맞습니다. 503은 대개 “잠깐 쉬어달라”는 신호고, 동시에 몰리면 더 악화됩니다.

### 2) Queueing은 “업로드 이후 단계”에 강제로 넣는다

업로드는 사용자 행위라 실시간성이 강하지만, 업로드 이후는 대부분 비동기 처리로 밀어도 UX 손실이 상대적으로 적습니다.

- 바이러스 스캔
- 이미지 리사이즈
- 썸네일 생성
- 메타데이터 추출
- secondary storage로 복제

장애가 났을 때도 큐가 있으면 “유입”과 “처리”를 분리할 수 있습니다. 유입이 유지되면 비즈니스는 산다 쪽이고, 처리 지연은 복구 후 따라잡으면 됩니다.

### 3) Cache는 다운로드뿐 아니라 “메타데이터/리스트”에도 쓴다

R2는 strong consistency이지만, 목록 조회나 존재 확인 같은 메타 연산을 request path에서 자주 때리면 장애 시에 함께 죽습니다.

- 요청마다 `HeadObject`를 하는 패턴
- 페이지 렌더링마다 `ListObjectsV2`를 때리는 패턴

이런 건 캐시나 DB 인덱스로 흡수합니다.

- 오브젝트 키/사이즈/콘텐츠 타입 같은 메타는 DB에 저장
- 사용자의 파일 목록은 DB를 소스로 만들고, 스토리지는 내용(payload)만 담당

R2는 `List`도 strong consistent라고 문서에 써 있지만[^9], 장애 때는 consistency가 아니라 availability가 문제입니다.

### 4) Multi-region은 “복제 전략”을 명시하지 않으면 환상이다

R2는 버킷 생성 시 `oc` 같은 Location Hint를 줄 수 있고[^3], 객체는 geographic region 내 여러 데이터센터로 복제된다고 설명합니다.[^4]  
하지만 여기서 말하는 복제는 “그 리전 내부” 이야기입니다. SYD에서 503이 터질 때 다른 대륙에서 자동으로 읽히는 형태를 앱이 기대하면 안 됩니다.

따라서 멀티리전은 다음 중 하나를 선택해야 합니다.

- active-passive: Primary 버킷(oc) + Secondary 버킷(enam 등)을 두고, 장애 시 읽기만 failover
- dual-write: 업로드 시점에 두 버킷에 모두 업로드(두 개의 presigned URL)하고, 읽기는 가까운 쪽/살아있는 쪽을 선택
- multi-provider: R2 + 다른 S3-compatible 스토리지(Backblaze B2 등)로 복제

내 경험상 현실적인 최소선은 active-passive입니다. dual-write는 성공 조건이 복잡해지고, 사용자 네트워크 품질까지 성공률에 영향을 줍니다.

멀티리전 라우팅은 Cloudflare Load Balancing 같은 도구로 할 수 있지만(Active-Passive failover 구성 예시가 문서로 제공됩니다)[^13], “스토리지 엔드포인트” 레벨의 failover는 단순 웹 오리진 failover보다 애매합니다. 결국 앱이 두 버킷을 이해하고 있어야 합니다.

### 5) Circuit breaker는 “서버와 워커”에 둔다. 클라이언트엔 신중하게

브라우저 클라이언트가 회로를 끊어버리면 UX가 너무 쉽게 무너집니다. 반대로 서버/워커는 회로를 끊어야 합니다.

- 서버: 업로드 발급은 가능하면 계속. 다만 서버가 R2 `HeadObject` 같은 확인을 한다면, 실패율이 높을 때는 확인 단계를 생략하고 “검증 대기”로 돌린다
- 워커: 503 비율이 일정 수준을 넘으면 즉시 실패(잡 재예약)로 전환하고 동시성을 낮춘다

Boto3의 standard retry mode 설명에는 circuit-breaking 기능이 포함된다고 명시돼 있습니다.[^14]  
SDK가 어느 정도 해주더라도, 워커 잡 단위에서 “재시도 쿼터를 다 써서 CPU만 태우는” 일을 막는 건 애플리케이션 책임입니다.

## 구현 예시: presigned 업로드 + DB 상태기계 + 워커 재시도(로컬 실행 가능)

아래 예시는 다음을 목표로 합니다.

- 업로드를 request transaction에서 분리
- presigned URL 발급은 저장소 호출 없이 수행
- 업로드 성공 확인은 비동기(워커)로 수행
- 워커는 SDK retry + 앱 레벨 재예약(backoff)로 503을 흡수

R2가 아니라도 S3-compatible이면 그대로 동작하므로, 로컬에서는 MinIO로 재현합니다. R2로 붙일 때는 endpoint/credential만 바꾸면 됩니다(Cloudflare R2 S3 endpoint 형식은 공식 문서에 나옵니다).[^15]

### docker-compose.yml

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_USER: postgres
      POSTGRES_DB: app
    ports:
      - "5432:5432"

  minio:
    image: minio/minio:RELEASE.2024-12-18T00-00-00Z
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: minio123456
    ports:
      - "9000:9000"
      - "9001:9001"

  createbucket:
    image: minio/mc:RELEASE.2024-12-16T17-35-00Z
    depends_on:
      - minio
    entrypoint: ["/bin/sh", "-c"]
    command: >
      "mc alias set local http://minio:9000 minio minio123456 &&
       mc mb -p local/uploads &&
       mc anonymous set download local/uploads || true"

  api:
    build: .
    environment:
      DATABASE_URL: postgres://postgres:postgres@postgres:5432/app
      S3_ENDPOINT: http://minio:9000
      S3_ACCESS_KEY_ID: minio
      S3_SECRET_ACCESS_KEY: minio123456
      S3_BUCKET: uploads
    ports:
      - "3000:3000"
    depends_on:
      - postgres
      - minio

  worker:
    build: .
    command: ["node", "dist/worker.js"]
    environment:
      DATABASE_URL: postgres://postgres:postgres@postgres:5432/app
      S3_ENDPOINT: http://minio:9000
      S3_ACCESS_KEY_ID: minio
      S3_SECRET_ACCESS_KEY: minio123456
      S3_BUCKET: uploads
    depends_on:
      - postgres
      - minio
```

### DB 스키마(간단 버전)

```sql
create table if not exists upload_intents (
  id uuid primary key,
  object_key text not null,
  status text not null, -- PENDING | UPLOADED | VERIFIED | FAILED
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists jobs (
  id bigserial primary key,
  type text not null, -- verify_upload | replicate | ...
  payload jsonb not null,
  run_at timestamptz not null default now(),
  attempts int not null default 0,
  max_attempts int not null default 20,
  last_error text,
  locked_at timestamptz,
  finished_at timestamptz
);

create index if not exists idx_jobs_runnable
  on jobs (finished_at, locked_at, run_at);
```

### S3 client 구성(Node.js, AWS SDK v3)

AWS SDK v3는 `maxAttempts` 또는 `StandardRetryStrategy`로 재시도 횟수를 지정할 수 있습니다.[^16]

```ts
// src/s3.ts
import { S3Client } from "@aws-sdk/client-s3";
import { StandardRetryStrategy } from "@aws-sdk/config-retryStrategy";

export function makeS3() {
  const endpoint = process.env.S3_ENDPOINT!;
  return new S3Client({
    region: "auto", // R2도 boto3/SDK에서 관례적으로 auto를 사용
    endpoint,
    credentials: {
      accessKeyId: process.env.S3_ACCESS_KEY_ID!,
      secretAccessKey: process.env.S3_SECRET_ACCESS_KEY!,
    },

    // SDK 레벨 재시도(요청 단위)
    // 1회 요청 + 4회 재시도 = 최대 5 attempts
    retryStrategy: new StandardRetryStrategy(5),
  });
}
```

### API: 업로드 인텐트 생성 + presigned PUT 발급

Cloudflare R2 presigned URL 문서는 PUT/GET/HEAD/DELETE를 지원하고, 만료는 1초~7일, 그리고 presign 생성은 R2와 통신 없이 이뤄진다고 명시합니다.[^5]

```ts
// src/api.ts
import express from "express";
import { randomUUID } from "crypto";
import { Pool } from "pg";
import { makeS3 } from "./s3";
import { PutObjectCommand, HeadObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const app = express();
app.use(express.json());

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const s3 = makeS3();
const bucket = process.env.S3_BUCKET!;

app.post("/upload-intents", async (req, res) => {
  // 실제 서비스라면 userId, contentType, size 제한, ACL, malware scan 여부 등을 함께 받습니다.
  const id = randomUUID();
  const objectKey = `user-uploads/${id}`;

  await pool.query(
    "insert into upload_intents(id, object_key, status) values ($1,$2,$3)",
    [id, objectKey, "PENDING"],
  );

  const cmd = new PutObjectCommand({
    Bucket: bucket,
    Key: objectKey,
    // ContentType을 강제하면 클라이언트가 동일 헤더로 업로드해야 서명이 유효합니다.
    // 운영에서는 보안상 강제하는 편이 낫지만, 실패율 관찰/지원 비용이 올라갑니다.
    ContentType: req.body?.contentType ?? "application/octet-stream",
  });

  const url = await getSignedUrl(s3, cmd, { expiresIn: 10 * 60 });

  res.json({
    uploadId: id,
    objectKey,
    putUrl: url,
    expiresInSec: 600,
  });
});

app.post("/upload-complete", async (req, res) => {
  const uploadId = req.body?.uploadId;
  if (!uploadId) return res.status(400).json({ error: "uploadId required" });

  // 여기서 HeadObject로 즉시 확인하는 패턴은, 장애 시 false negative가 되기 쉽습니다.
  // 대신 verify job을 큐에 넣습니다.
  await pool.query(
    "insert into jobs(type, payload) values ($1, $2)",
    ["verify_upload", { uploadId }],
  );

  // 사용자는 즉시 성공으로 돌려보내고, 후속 처리는 비동기로 합니다.
  res.status(202).json({ status: "ACCEPTED" });
});

app.get("/healthz", (_req, res) => res.json({ ok: true }));

app.listen(3000, () => console.log("api listening on :3000"));
```

### 워커: verify_upload 잡 처리(503 흡수 + 재예약)

워커는 두 겹의 내구성을 가집니다.

- SDK retry(요청 단위)
- 잡 재예약(backoff, 잡 단위)

503이 올라오는 동안 워커가 무한히 돌아가며 CPU를 태우는 걸 막고, run_at을 뒤로 미는 방식으로 압력을 줄입니다.

```ts
// src/worker.ts
import { Pool } from "pg";
import { makeS3 } from "./s3";
import { HeadObjectCommand } from "@aws-sdk/client-s3";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const s3 = makeS3();
const bucket = process.env.S3_BUCKET!;

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function backoffMs(attempts: number) {
  // truncated exponential backoff + 간단 jitter
  const base = Math.min(30_000, 200 * Math.pow(2, Math.min(attempts, 10)));
  const jitter = Math.floor(Math.random() * 250);
  return base + jitter;
}

async function claimJob() {
  const client = await pool.connect();
  try {
    await client.query("begin");

    const { rows } = await client.query(
      `select id, type, payload, attempts
       from jobs
       where finished_at is null
         and locked_at is null
         and run_at <= now()
       order by id
       limit 1
       for update skip locked`,
    );

    if (rows.length === 0) {
      await client.query("commit");
      return null;
    }

    const job = rows[0];
    await client.query("update jobs set locked_at = now() where id=$1", [job.id]);

    await client.query("commit");
    return job;
  } catch (e) {
    await client.query("rollback");
    throw e;
  } finally {
    client.release();
  }
}

async function finishJob(id: number) {
  await pool.query(
    "update jobs set finished_at=now(), locked_at=null where id=$1",
    [id],
  );
}

async function retryJob(id: number, attempts: number, err: unknown) {
  const delay = backoffMs(attempts);
  await pool.query(
    `update jobs
     set locked_at=null,
         attempts=attempts+1,
         last_error=$2,
         run_at=now() + ($3 || ' milliseconds')::interval
     where id=$1`,
    [id, String(err), delay],
  );
}

async function runVerifyUpload(job: any) {
  const uploadId = job.payload.uploadId as string;
  const { rows } = await pool.query(
    "select object_key, status from upload_intents where id=$1",
    [uploadId],
  );
  if (rows.length === 0) return;

  const { object_key: objectKey, status } = rows[0];
  if (status === "VERIFIED") return;

  // HeadObject는 실제로 R2/S3를 때립니다. 장애 중이면 503이 여기서 터집니다.
  await s3.send(
    new HeadObjectCommand({
      Bucket: bucket,
      Key: objectKey,
    }),
  );

  await pool.query(
    "update upload_intents set status=$2, updated_at=now() where id=$1",
    [uploadId, "VERIFIED"],
  );
}

async function loop() {
  for (;;) {
    const job = await claimJob();
    if (!job) {
      await sleep(200);
      continue;
    }

    try {
      if (job.type === "verify_upload") {
        await runVerifyUpload(job);
      }
      await finishJob(job.id);
    } catch (e: any) {
      // retry 한도를 넘기면 실패로 마킹하고 종료 처리하는 편이 운영에 낫습니다.
      if (job.attempts + 1 >= 20) {
        await pool.query(
          "update jobs set finished_at=now(), locked_at=null, last_error=$2 where id=$1",
          [job.id, String(e)],
        );
      } else {
        await retryJob(job.id, job.attempts + 1, e);
      }
    }
  }
}

loop().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

### 실행

```bash
docker compose up -d

# api/worker 빌드(예: ts -> dist) 절차는 프로젝트 구성에 따라 다르지만,
# 일반적으로는 다음 순서입니다.
npm ci
npm run build

a) 업로드 인텐트 생성
curl -s -X POST http://localhost:3000/upload-intents \
  -H 'content-type: application/json' \
  -d '{"contentType":"text/plain"}' | jq

b) putUrl로 업로드
# (출력된 putUrl을 그대로 사용)
curl -X PUT "<PUT_URL>" \
  -H 'content-type: text/plain' \
  --data-binary 'hello'

c) 업로드 완료 통지
curl -s -X POST http://localhost:3000/upload-complete \
  -H 'content-type: application/json' \
  -d '{"uploadId":"<UPLOAD_ID>"}' | jq
```

이 구조의 포인트는 다음입니다.

- 업로드 트랜잭션과 R2 PUT을 분리했기 때문에, R2 503이 떠도 API 서버는 핵심 기능(게시물 생성/결제 등)을 함께 잃지 않습니다.
- 장애 중 `verify_upload`가 계속 실패하더라도, 워커가 backoff로 느려지면서 스토리지에 가하는 압력을 줄입니다.

## 함정과 트레이드오프: “견고함”은 공짜가 아니다

### 재시도는 성공률을 올리지만, 장애를 길게 만들 수도 있다

AWS 문서들이 말하는 exponential backoff는 필수지만[^10], 운영에서는 다음도 같이 봐야 합니다.

- 최대 재시도 시간(예: 30초 내에서 포기)
- 최대 attempts(예: 5~10)
- 재시도 대상(503/500/timeout만)
- 멱등성(idempotency)

특히 업로드는 멱등성 설계가 없으면 “중복 객체/중복 과금/중복 이벤트”로 돌아옵니다.

- 키를 UUID로 만들면 중복은 줄지만, 같은 파일을 두 번 업로드하게 됩니다.
- 키를 content hash로 만들면 중복 업로드를 줄일 수 있지만, 해시 계산 비용과 개인정보/추론 리스크가 생깁니다.

### 캐시는 장애를 숨기지만, 최신성을 희생한다

R2는 strong consistency를 강조하지만[^9], custom domain + 캐시를 올리는 순간 “삭제/갱신 즉시 반영”은 깨질 수 있습니다.

- 삭제했는데 캐시에 남아 계속 내려간다
- 이전 버전이 TTL 동안 계속 내려간다
- 404 캐시 때문에 업로드 직후에도 404가 보인다

이건 운영 정책으로 다뤄야 합니다.

- 삭제/권한 변경은 purge를 강제
- 파일 업데이트는 버저닝된 키로만(immutable object)

### 멀티리전은 비용이 아니라 복잡성이 비싸다

버킷을 두 개로 늘리면 비용보다 운영 복잡성이 먼저 옵니다.

- 어떤 요청을 어느 버킷으로 보내는가
- secondary가 lagging일 때 어떤 일관성을 보장할 것인가
- 장애가 났을 때 failback은 자동인가 수동인가

R2가 버킷 location hint를 제공한다고 해서[^3] 자동 복제가 따라오는 건 아닙니다. 결국 앱이 복제/라우팅을 갖고 있어야 하고, 그게 진짜 비용입니다.

## 반론과 회의론: “503은 드물다”, “SDK가 알아서 한다”

### “503은 드물고 짧다. 굳이?”

이번 사건도 17분 수준이었고[^1], 대다수 서비스는 사용자에게 티가 안 났을 수 있습니다. 하지만 객체 스토리지가 서비스의 정적 자산/미디어/첨부파일을 쥐고 있다면, 17분은 충분히 고객센터를 폭발시키는 시간입니다.

게다가 짧은 장애는 대응이 더 어렵습니다.

- 재현이 안 되고
- 관측이 늦으면 이미 끝나 있고
- 포스트모템도 흐지부지됩니다

그래서 “짧은 장애를 기준으로 설계”하는 게 더 실용적입니다.

### “AWS SDK가 exponential backoff로 재시도해준다”

맞습니다. AWS SDK 문서는 표준 모드가 지터가 있는 exponential backoff를 쓴다고 설명합니다.[^11]  
그리고 AWS SDK v3에서도 `maxAttempts`/`StandardRetryStrategy`로 retry 설정을 할 수 있습니다.[^16]

하지만 SDK 재시도는 다음을 해결하지 못합니다.

- 잘못된 동시성(워커 500개가 동시에 재시도)
- 동기 트랜잭션 설계(업로드 실패가 DB write를 막음)
- 관측 분리 실패(presign 200, PUT 503)
- 캐시/서빙 경로 부재(다운로드를 매번 스토리지에 의존)

SDK는 도구고, 장애 내성은 경계 설계 문제입니다.

## 앞으로 지켜볼 것: R2의 지역성 기능과 장애 공지 신뢰도

이번 사건 자체에 대해 Cloudflare가 원인 분석(RCA)을 공개했는지는 Statuspage 본문만으로는 알 수 없었습니다(업데이트는 Investigating/Identified/Monitoring/Resolved의 타임라인뿐입니다).[^1]

운영 관점에서는 다음을 계속 지켜보게 됩니다.

- R2의 데이터 위치 옵션(Automatic, Location Hints, Jurisdictional Restriction)과 실제 장애 도메인이 어떻게 매핑되는지[^3]
- “public bucket + cache”를 써서 다운로드를 흡수할 때, consistency 문제가 실제 장애/복구 구간에서 어떻게 나타나는지[^9]
- Statuspage 장애 공지가 짧은 장애에서도 얼마나 빠르게 올라오는지(실시간 대응은 결국 자체 SLI로 해야 하지만, 외부 커뮤니케이션도 중요)

## 지금 할 수 있는 일: 객체 스토리지 의존성 런북 업데이트 체크리스트

이번처럼 리전 단위로 503이 오르는 사건을 기준으로 런북을 업데이트할 때, 나는 다음을 우선순위로 둡니다.

1. **요청 경로 분리**
   - 업로드는 presigned URL 기반으로 전환하고, DB 트랜잭션과 분리한다[^5]
   - 다운로드는 custom domain + 캐시를 기본으로 두고, 내부용 접근만 S3 API로 남긴다[^7]

2. **관측 분리**
   - presigned URL 발급 성공률
   - PUT/GET 실제 성공률(클라이언트 측 이벤트 수집 또는 서버 측 비동기 검증)
   - 워커 큐 지연/실패율

3. **재시도 정책 표준화**
   - HTTP 503/500/timeout만 재시도
   - exponential backoff + jitter + max attempts를 문서화(서비스마다 제각각이면 사고 때 더 망가짐)[^10]

4. **워커 동시성/서킷브레이커**
   - 스토리지 503 비율이 일정 임계치를 넘으면 워커는 실패-재예약으로 전환
   - backlog가 쌓일 때는 처리량을 올리는 게 아니라, 입력을 제어(큐 길이 기반 rate limit)

5. **캐시 운영 규칙**
   - 업데이트/삭제는 immutable key 또는 purge로 다룬다
   - 404 캐시로 인한 “업로드 직후 404”가 발생할 수 있음을 장애 대응 시나리오에 포함[^9]

6. **멀티리전은 목표가 아니라 시나리오로**
   - “SYD가 죽었을 때 무엇을 포기하고 무엇을 지킬지”를 먼저 결정
   - 읽기만 failover할지, 쓰기도 failover할지
   - secondary의 데이터 freshness를 어느 정도로 요구할지

이 정도가 정리돼 있으면, 다음 번에 비슷한 503 스파이크가 와도 “장애가 어디까지 번지는지”를 통제할 수 있습니다. 결론적으로 객체 스토리지는 503을 완전히 없애는 대상이 아니라, 503이 와도 핵심 플로우가 무너지지 않게 경계를 설계하는 대상입니다.

## 참고 자료

- [Cloudflare Statuspage 사건 기록: Elevated number of R2 503 errors in Australian Eastern Coast region](https://cloudflare.statuspage.io/incidents/x86v1qk8yp5v)
- [Cloudflare R2 API 개요](https://developers.cloudflare.com/r2/api/)
- [Cloudflare R2 S3 API 시작하기](https://developers.cloudflare.com/r2/get-started/s3/)
- [Cloudflare R2 API tokens / S3 endpoint 및 jurisdiction endpoint](https://developers.cloudflare.com/r2/api/tokens/)
- [Cloudflare R2 Presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)
- [Cloudflare R2 Upload objects(직접 업로드 권장 패턴)](https://developers.cloudflare.com/r2/objects/upload-objects/)
- [Cloudflare R2 Data location(Automatic/Location Hint/Jurisdiction)](https://developers.cloudflare.com/r2/reference/data-location/)
- [Cloudflare R2 Durability(리전 내 복제/erasure coding)](https://developers.cloudflare.com/r2/reference/durability/)
- [Cloudflare R2 Consistency model(캐시 사용 시 일관성 주의)](https://developers.cloudflare.com/r2/reference/consistency/)
- [Cloudflare R2 Public buckets(커스텀 도메인과 캐시)](https://developers.cloudflare.com/r2/buckets/public-buckets/)
- [Cloudflare Cache: Enable cache in an R2 bucket](https://developers.cloudflare.com/cache/interaction-cloudflare-products/r2/)
- [Cloudflare Workers Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/)
- [Cloudflare Workers Cache configuration(stale-if-error)](https://developers.cloudflare.com/workers/cache/configuration/)
- [Amazon S3 성능 패턴: 503은 exponential backoff 재시도](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html)
- [AWS SDKs Retry behavior(지터 포함 backoff)](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)
- [AWS Well-Architected Framework(재시도 한도/지터/메타안정성)](https://docs.aws.amazon.com/pdfs/wellarchitected/2023-10-03/framework/wellarchitected-framework-2023-10-03.pdf)
- [AWS SDK for JavaScript v3: CLIENTS.md(retryStrategy / maxAttempts)](https://github.com/aws/aws-sdk-js-v3/blob/main/supplemental-docs/CLIENTS.md)
- [Cloudflare Load Balancing common configurations(Active-Passive failover)](https://developers.cloudflare.com/load-balancing/load-balancers/common-configurations/)

[^1]: <https://cloudflare.statuspage.io/incidents/x86v1qk8yp5v>
[^2]: <https://developers.cloudflare.com/r2/api/>
[^3]: <https://developers.cloudflare.com/r2/reference/data-location/>
[^4]: <https://developers.cloudflare.com/r2/reference/durability/>
[^5]: <https://developers.cloudflare.com/r2/api/s3/presigned-urls/>
[^6]: <https://developers.cloudflare.com/r2/objects/upload-objects/>
[^7]: <https://developers.cloudflare.com/r2/buckets/public-buckets/>
[^8]: <https://developers.cloudflare.com/workers/cache/configuration/>
[^9]: <https://developers.cloudflare.com/r2/reference/consistency/>
[^10]: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html>
[^11]: <https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html>
[^12]: <https://docs.aws.amazon.com/pdfs/wellarchitected/2023-10-03/framework/wellarchitected-framework-2023-10-03.pdf>
[^13]: <https://developers.cloudflare.com/load-balancing/load-balancers/common-configurations/>
[^14]: <https://docs.aws.amazon.com/boto3/latest/guide/retries.html>
[^15]: <https://developers.cloudflare.com/r2/get-started/s3/>
[^16]: <https://github.com/aws/aws-sdk-js-v3/blob/main/supplemental-docs/CLIENTS.md>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
