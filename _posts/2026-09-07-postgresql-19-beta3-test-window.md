---
title: "PostgreSQL 19 Beta 3 검증 윈도우: 확장·호환성·회귀"
description: "베타는 feature-frozen 시점이라 리스크가 가장 싸게 드러납니다. extensions·드라이버·플랜·복제·백업을 CI로 묶어 회귀를 릴리스 전에 잡습니다."
date: 2026-09-07 12:53:56 +0900
categories: ["Database", "PostgreSQL"]
tags: ["postgresql", "beta-testing", "extensions", "rds-preview", "ci", "performance"]
render_with_liquid: false
---

## 베타가 가장 싼 이유: feature freeze 이후에만 가능한 테스트

PostgreSQL 베타는 기능이 계속 추가되는 알파가 아니라 **feature-frozen** 상태에서 버그/회귀를 잡기 위해 배포되는 프리릴리스입니다. 즉 “지금 돌린 테스트 결과”가 GA까지 의미를 유지할 확률이 가장 높습니다. PostgreSQL 쪽도 베타/RC를 공개하는 이유를 명확히 적어 두었는데, 베타/RC는 새로운 기능을 더 넣지 않는(feature-frozen) 단계이며 프로덕션 사용이 목적이 아니라 커뮤니티가 워크로드로 회귀를 찾아 달라는 성격입니다.[^1]

이번 타이밍이 실무적으로 좋은 이유가 하나 더 있습니다.

* PostgreSQL 19 Beta 3는 2026-08-13에 공개됐고, 같은 날 공식 발표문에도 19 Beta 3가 포함돼 있습니다.[^2]
* AWS RDS Database Preview Environment에서 PostgreSQL 19 Beta 3를 2026-08-18부터 제공하기 시작했습니다.[^3]

로컬에서 “호환성/기능/플랜 변화”를 잡는 것과, 매니지드 환경(RDS)에서 “파라미터·스토리지·백업·복제·운영 제약”을 같이 밟아 보는 것은 비용 구조가 다릅니다. 베타 단계에서는 둘 다 병렬로 굴려야 싸게 끝납니다.

## 테스트 범위는 기능 목록이 아니라 의존성 그래프에서 나온다

베타 검증에서 제일 흔한 실패는 “19의 새 기능을 체험해 봄”으로 끝나는 겁니다. 실무에서 터지는 건 새 기능이 아니라 다음 범주에서 나옵니다.

1) extensions 로딩/업그레이드/동작

2) 드라이버/ORM/Pooler/Proxy의 프로토콜 호환

3) planner 및 실행기 변경으로 인한 쿼리 플랜 변화(성능 회귀)

4) 복제(physical/logical), 장애조치, 슬롯/피드백의 모서리 케이스

5) 백업/복구(특히 PITR, incremental, verify, restore), 그리고 운영 툴 체인

이 범주를 한 번에 다 잡으려면 “우리 서비스의 Postgres 의존 지점”을 인벤토리로 만들고, 그것을 테스트 케이스/CI 잡으로 분해해야 합니다.

내 경우는 아래 쿼리/설정에서 인벤토리가 거의 다 나왔습니다.

### extensions 인벤토리

```sql
-- 설치된 extensions
SELECT extname, extversion, extrelocatable
FROM pg_extension
ORDER BY 1;

-- preload 필요한 것(환경별로 다름)
SHOW shared_preload_libraries;
SHOW session_preload_libraries;
```

여기서 중요한 건 `extname` 목록 자체가 아니라, 각 extension이 어떤 타입/함수/연산자/인덱스 접근 방법을 제공하는지까지 같이 기록하는 겁니다. C extension은 로딩은 되는데 특정 타입/연산자 경로에서만 크래시가 나는 경우가 흔합니다.

### 애플리케이션/ORM 인벤토리

* 연결 경로: direct libpq인지, PgBouncer 같은 pooler를 끼는지, 프록시/서비스메시/DB firewall을 끼는지
* 인증/암호화: SCRAM, TLS, GSSAPI, IAM auth 같은 클라우드 특화
* 트랜잭션 사용 패턴: long transaction, idle in transaction, prepared statement, cursor

이건 문서로만 정리하면 누락이 납니다. 실제 런타임에서 집계해야 합니다. 예를 들어 `pg_stat_activity`, `pg_stat_statements`(사용 중이면), 애플리케이션 APM의 DB span 태그를 합치면 “무슨 쿼리가 어떤 드라이버로 어떤 옵션으로 나갔는지”가 꽤 정확히 잡힙니다.

### 운영 기능 인벤토리

* `pg_dump`/`pg_restore`를 쓰는지, physical backup(pgBackRest, wal-g)을 쓰는지
* logical replication을 쓰는지, CDC를 쓰는지
* 업그레이드를 `pg_upgrade`로 하는지, dump/restore로 하는지, 블루/그린인지

여기까지가 “테스트할 것 목록”이고, 이제 “어떻게 싸게 반복할 것”으로 들어갑니다.

## 환경 구성: 로컬 Docker는 빠르고, RDS Preview는 현실적이다

### 로컬 Docker: 가장 싼 회귀 탐지기

공식 Docker 이미지에 PostgreSQL 19 Beta 3 태그가 이미 올라와 있습니다. `postgres:19beta3` 계열 태그가 있고, Debian(trixie/bookworm)와 alpine도 제공됩니다.[^4]

이건 CI에 붙이기 좋습니다. 애플리케이션 테스트(ORM/마이그레이션/기본 쿼리)와 extension smoke test를 가장 싸게 돌릴 수 있습니다.

예시는 아래처럼 잡았습니다.

```yaml
# docker-compose.yml
services:
  pg18:
    image: postgres:18.6-bookworm
    environment:
      POSTGRES_PASSWORD: postgres
    ports:
      - "5418:5432"
    command:
      - "postgres"
      - "-c"
      - "shared_preload_libraries=pg_stat_statements"
      - "-c"
      - "max_connections=200"

  pg19:
    image: postgres:19beta3-bookworm
    environment:
      POSTGRES_PASSWORD: postgres
    ports:
      - "5419:5432"
    command:
      - "postgres"
      - "-c"
      - "shared_preload_libraries=pg_stat_statements"
      - "-c"
      - "max_connections=200"
```

실행:

```bash
docker compose up -d
psql "postgresql://postgres:postgres@localhost:5419/postgres" -c "SELECT version();"
```

예상 출력(버전 문자열은 빌드에 따라 조금 달라집니다):

```text
PostgreSQL 19beta3 ...
```

이 구성의 강점은 빠른 반복입니다. 단점은 운영 커널/파일시스템/스토리지/네트워크 조건이 다르기 때문에 “성능 수치”를 절대값으로 믿으면 안 된다는 점입니다. 플랜 변화, 에러, 확장 로딩 실패, SQL 동작 변화 같은 이슈에 집중해야 합니다.

### RDS Database Preview Environment: 운영 제약까지 포함한 리허설

AWS는 Preview 환경의 성격을 분명히 합니다. Preview 인스턴스는 최대 60일 유지 후 자동 삭제되고, Preview에서 만든 스냅샷은 Preview 안에서만 복구에 쓸 수 있으며, 외부로 데이터 이동은 dump/load 같은 방식이 필요하다고 명시돼 있습니다.[^3]

그리고 PostgreSQL 19 Beta 3가 RDS Preview에서 2026-08-18에 공개됐다는 What’s New 문서가 있습니다.[^3]

이 제약이 오히려 장점인 구간이 있습니다.

* 60일 제한은 “짧은 스프린트 테스트”에 적합합니다. 장기 운영 검증이 아니라, 업그레이드/백업/복제 체인만 찔러보면 충분한 구간이기 때문입니다.
* Preview 스냅샷이 Preview 내부 전용이므로, 데이터 반입/반출 경로를 초반부터 명시적으로 설계하게 됩니다(덤프, logical replication, ETL 중 무엇을 쓸지).

내 기준에서는 로컬 Docker에서 회귀 후보를 빠르게 모으고, RDS Preview에서 “정말 우리 운영에서 터질 만한가”를 판정했습니다.

## 업그레이드 리허설은 2단계로 나눠야 빨라진다

베타 검증에서 업그레이드는 목표가 2개입니다.

* (A) 업그레이드 경로 자체가 깨지지 않는지
* (B) 업그레이드 후 동작/성능이 바뀌지 않는지

이 둘을 한 번에 하려다 보면, 매번 `pg_upgrade`까지 돌리느라 시간이 폭발합니다. 그래서 아래처럼 분리하는 편이 유지비가 줄었습니다.

### 1단계: dump/restore 기반의 스키마/데이터 호환성 체크

이건 가장 가볍고, CI에 넣기 좋습니다.

1) 운영 스키마를 “가장 가까운 형태”로 재현합니다(마이그레이션, 스키마 덤프, seed 데이터).

2) 18.6에서 `pg_dump`로 떠서 19beta3에 `pg_restore`로 부어 봅니다.

RDS Preview의 데이터 반출입도 결국 dump/load가 주요 경로라고 AWS가 적어 둔 만큼, 이 단계는 로컬에서도 RDS에서도 공통으로 의미가 있습니다.[^3]

예시 스크립트(현실적인 패턴을 일부 포함: partitioned table, jsonb + GIN, 대량 insert, sequence):

```bash
#!/usr/bin/env bash
set -euo pipefail

PG18_URL="postgresql://postgres:postgres@localhost:5418/postgres"
PG19_URL="postgresql://postgres:postgres@localhost:5419/postgres"

psql "$PG18_URL" -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.events (
  id bigserial PRIMARY KEY,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL,
  type text NOT NULL,
  payload jsonb NOT NULL
) PARTITION BY RANGE (created_at);

CREATE TABLE IF NOT EXISTS app.events_2026_09 PARTITION OF app.events
FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE INDEX IF NOT EXISTS events_payload_gin
ON app.events_2026_09 USING gin (payload);

INSERT INTO app.events (tenant_id, created_at, type, payload)
SELECT
  (g % 2000) + 1,
  '2026-09-01'::timestamptz + ((g % 86400) || ' seconds')::interval,
  CASE WHEN g % 10 = 0 THEN 'purchase' ELSE 'view' END,
  jsonb_build_object('user_id', (g % 1000000), 'amount', (g % 50000), 'path', '/items/'||(g%10000))
FROM generate_series(1, 500000) AS g;

ANALYZE app.events;
SQL

rm -f /tmp/app.dump
pg_dump "$PG18_URL" --format=custom --file=/tmp/app.dump

# 깨끗한 복원 대상 DB
psql "$PG19_URL" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS app CASCADE;"
pg_restore --dbname="$PG19_URL" --exit-on-error /tmp/app.dump

psql "$PG19_URL" -v ON_ERROR_STOP=1 <<'SQL'
SELECT count(*) FROM app.events;
SELECT
  tenant_id,
  count(*)
FROM app.events
WHERE payload @> '{"type": "view"}'::jsonb OR type = 'purchase'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 5;
SQL
```

예상 결과:

* `pg_restore`가 깨지지 않고 끝나야 합니다.
* 위 쿼리가 에러 없이 실행돼야 합니다.
* count가 500000으로 나와야 합니다.

이 단계에서 잡히는 건 “업그레이드 메커니즘 문제”가 아니라, 타입/연산자/인덱스/함수/확장 등 호환성 문제입니다.

### 2단계: pg_upgrade 리허설은 Nightly로 빼는 편이 낫다

`pg_upgrade`는 운영 업그레이드 경로가 그 방식일 때만 필수입니다. 하지만 dump/restore가 통과해도 `pg_upgrade`가 실패하는 케이스가 있기 때문에, 업그레이드 방식이 pg_upgrade라면 베타 기간에 반드시 밟아야 합니다.

문제는 CI에서 `pg_upgrade`를 자주 돌리면 비용이 커진다는 점입니다. 나는 아래 조건을 붙여 Nightly로 분리했습니다.

* main 브랜치에서만
* 스키마 변경(마이그레이션)이나 extension 변경이 있을 때만
* 실행 시간을 30~60분까지 허용

구현은 “18.6 소스 + 19beta3 소스”를 빌드하는 컨테이너를 하나 만들고, 그 안에서 `pg_upgrade --check`와 실제 업그레이드를 연달아 돌렸습니다. PostgreSQL 소스 트리는 FTP에 `v19beta3` 디렉터리가 제공됩니다.[^5]

여기까지를 코드로 다 싣기 시작하면 글이 과해지는데, 핵심은 다음 두 가지입니다.

* `--check`를 먼저 돌려서 실패를 빨리 보고
* 업그레이드 후 `ANALYZE` / 통계 갱신 / 대표 쿼리 실행까지 자동화해서 “성공/실패”가 아니라 “회귀 여부”를 판정하는 것

## extensions: “설치된다”가 아니라 “업그레이드된다”를 확인한다

extensions에서 실무적으로 까다로운 포인트는 세 가지입니다.

1) 로딩 시점 문제: `shared_preload_libraries`가 필요해 재시작이 필요한 확장

2) 바이너리 호환성: Postgres major가 바뀌면 C extension은 재빌드/재패키징이 거의 필수

3) 업그레이드 경로: `ALTER EXTENSION ... UPDATE`가 실제 데이터/함수/연산자/캐시를 건드리면서 깨지는 경우

### 확장 smoke test를 CI로 만드는 최소 단위

내가 잡은 최소 단위는 이렇습니다.

* 19beta3에서 extension을 `CREATE EXTENSION` 할 수 있어야 함
* `ALTER EXTENSION ... UPDATE`가 에러 없이 끝나야 함(같은 major 내 업그레이드도 포함)
* 그 확장이 제공하는 핵심 연산자/함수 1~3개를 실제로 실행해 볼 것

아래는 “설치된 extension 목록을 기준으로” smoke test를 돌리는 SQL입니다.

```sql
-- extensions-smoke.sql
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN SELECT extname FROM pg_extension ORDER BY 1 LOOP
    RAISE NOTICE 'extension=%', r.extname;
    EXECUTE format('CREATE EXTENSION IF NOT EXISTS %I', r.extname);
  END LOOP;
END$$;

-- 예: pg_stat_statements는 뷰/함수 접근까지 확인
SELECT pg_stat_statements_reset();
```

이 스크립트는 그냥 돌리면 의미가 약합니다. “운영에서 실제로 쓰는 확장”만 골라서, 그 확장과 결합된 대표 쿼리(예: jsonb + gin, trigram, vector 검색)를 같이 실행해야 합니다.

### PostgreSQL 19 자체가 추가한 contrib도 테스트 대상이 된다

19에는 `pg_plan_advice` 같은 새 모듈이 문서에 포함되어 있습니다. `shared_preload_libraries`나 `LOAD`로 로드한 뒤 `EXPLAIN (PLAN_ADVICE)` 옵션을 쓸 수 있고, 계획 고정을 유도하는 미니 언어를 제공합니다.[^6]

이건 “새 기능 소개”보다 더 중요한 실무 의미가 있습니다.

* 베타/업그레이드 기간에 플랜이 흔들릴 때, 문제 재현/원인 규명에 도움
* 반대로 잘못 쓰면 플랜을 고정해 버려서 데이터 분포가 바뀌는 순간 더 큰 장애로 이어짐(문서에서도 오버라이드의 위험을 경고합니다)[^6]

따라서 `pg_plan_advice`를 기능으로 도입할지 여부와 상관 없이, “19에서 planner 디버깅/재현 도구가 이렇게 바뀌었다”는 맥락으로 테스트 환경에서 한 번은 만져 보는 편이 낫습니다.

## 드라이버/ORM/Pooler: 베타 기간에만 드러나는 프로토콜 모서리

대부분의 애플리케이션은 “Postgres가 SQL을 실행한다”가 아니라 “드라이버가 프로토콜을 말하고, pooler가 중간에서 조작하고, ORM이 SQL을 생성하고, 서버가 실행한다”의 체인입니다.

PostgreSQL 19 릴리스 노트에는 베타 기간에 프로토콜 호환성 테스트를 위한 libpq 관련 변경이 언급됩니다(일명 protocol grease가 19 베타 기간에 활성화되었다는 설명 포함).[^7]

이런 종류의 변경은 아래에서 터집니다.

* 오래된 드라이버가 “모르는 파라미터/메시지”를 잘못 처리
* PgBouncer/프록시가 알 수 없는 필드를 드롭하거나, 반대로 패스스루를 못 해서 연결이 끊김
* 관측/보안 장비(DB firewall)가 정상 트래픽을 비정상으로 분류

그래서 베타 검증에서 드라이버 테스트는 “단위 테스트”가 아니라 “연결 경로 통합 테스트”여야 합니다.

### CI에서 통합 테스트를 현실적으로 만드는 요령

* 언어별로 대표 1개(예: Java + JDBC, Go + pgx, Python + psycopg/SQLAlchemy)
* pooler가 있으면 반드시 끼운 경로와 direct 경로를 둘 다 둠
* prepared statement를 쓰는 경로와 simple query 경로를 둘 다 밟음

GitHub Actions 기준으로는 서비스 컨테이너를 18.6 / 19beta3로 매트릭스 돌리는 구성이 가장 단순합니다.

```yaml
# .github/workflows/pg-compat.yml
name: pg-compat
on:
  push:
  pull_request:

jobs:
  integration:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        pg_image:
          - postgres:18.6-bookworm
          - postgres:19beta3-bookworm
    services:
      postgres:
        image: ${{ matrix.pg_image }}
        env:
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 20
    steps:
      - uses: actions/checkout@v4

      - name: Python setup
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install deps
        run: |
          python -m pip install -U pip
          pip install sqlalchemy psycopg[binary] pytest

      - name: Run integration tests
        env:
          DATABASE_URL: postgresql+psycopg://postgres:postgres@localhost:5432/postgres
        run: |
          pytest -q
```

이 구성의 포인트는 “베타에서 깨질 수 있는 것”을 테스트 코드가 실제로 밟게 하는 겁니다.

* connection 옵션(sslmode, application_name)
* 트랜잭션 격리 수준 설정
* prepared statement
* 대량 insert (COPY, executemany)

테스트 코드 자체는 서비스마다 다르지만, 위 항목이 빠지면 베타 검증의 효율이 급격히 떨어집니다.

## 쿼리 플랜/성능 회귀: 수치를 믿지 말고 변화량을 믿는다

베타에서 성능 검증은 두 갈래입니다.

* 마이크로: planner/실행기 변경으로 인한 “특정 쿼리” 급락
* 매크로: autovacuum/IO/체크포인트 같은 운영 동작 변경으로 인한 “전체 지표” 이동

이걸 둘 다 수치로만 잡으려 하면 실패합니다. 환경이 완전히 동일하지 않기 때문입니다. 대신 “비교 가능한 형태로 기록”을 남겨서 회귀 후보를 좁히는 쪽이 실제로 빨랐습니다.

### 플랜 변화 감지: EXPLAIN (FORMAT JSON)을 diff 가능한 아티팩트로 남긴다

내가 만든 규칙은 단순했습니다.

* 상위 20~50개 쿼리(트래픽 기준)만 고른다.
* 각 쿼리에 대해 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` 결과를 파일로 저장한다.
* 18.6 vs 19beta3 결과를 기계적으로 비교해서 “노드 타입 변화, 인덱스 사용 여부 변화, row estimate 변화”를 잡는다.

실제로는 JSON 전체를 diff하면 노이즈가 많아서, 아래처럼 jq로 핵심 필드만 뽑아 비교하는 편이 낫습니다.

```bash
psql "$PG19_URL" -At -c "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT ..." \
  | jq '.[0].Plan | {NodeType, JoinType, RelationName, IndexName, ActualRows, PlanRows, TotalCost}'
```

여기서 플랜이 바뀌는 건 정상일 수 있습니다. 문제는 “바뀐 이유를 설명할 수 없는 변화”입니다.

* 통계/ANALYZE가 달라졌는지
* operator class 선택이 바뀌었는지
* enable 플래그(예: 새 최적화)가 켜져서 바뀌었는지

PostgreSQL 19 문서에는 `enable_eager_aggregate` 같은 planner 토글이 추가되어 있습니다. 이 설정은 조인을 통과해 aggregation을 부분적으로 밀어 넣는(eager aggregation) 능력을 켜고 끄는 스위치입니다.[^8]

회귀가 의심될 때 이런 토글이 있으면 원인 분리가 빨라집니다.

* 19beta3에서 느려졌다
* `SET enable_eager_aggregate = off`를 해 보니 18.6과 동일한 플랜으로 돌아왔다

이렇게 되면 “데이터/통계 문제가 아니라 새 최적화 경로”에 회귀가 있을 가능성이 커집니다.

### 매크로 성능: autovacuum 변경은 워크로드에서만 보인다

PostgreSQL 19는 autovacuum에 “점수 기반 우선순위”를 도입했고, 점수를 확인하는 `pg_stat_autovacuum_scores` 뷰가 문서에 포함되어 있습니다.[^9]

베타 3에서 AWS가 강조한 기능도 여기에 걸려 있습니다. RDS What’s New는 19 Beta 3의 변화로 `pg_stat_autovacuum_scores`와 parallel autovacuum, 그리고 eager aggregation 등을 언급합니다.[^3]

실무에서 이건 “성능이 좋아질 수도, 나빠질 수도” 있는 변화입니다.

* 좋은 쪽: 진짜로 급한 테이블을 먼저 치우기 시작해서 bloat/latency가 줄어듦
* 나쁜 쪽: 점수 계산/우선순위가 특정 패턴에서 의도치 않게 쏠려, 어떤 테이블이 계속 밀림

여기서 중요한 건 수치 최적화가 아니라 “관찰 가능성”입니다. 18까지는 autovacuum이 왜 저 테이블을 지금 도는지 설명하기가 어려웠는데, 점수/우선순위가 보이면 운영 판단이 쉬워집니다.

그래서 베타 테스트 플랜에 반드시 넣어야 할 항목이 하나 생깁니다.

* 동일 워크로드(대량 insert/update/delete)를 18.6과 19beta3에서 돌린다.
* autovacuum 로그를 동일 기준으로 켠다(`log_autovacuum_min_duration`).
* `pg_stat_autovacuum_scores`를 주기적으로 덤프해서 “어떤 테이블이 높은 점수를 받는지”를 비교한다.

이건 로컬에서도 가능하지만, 스토리지/IO 노이즈를 줄이려면 RDS Preview 같은 매니지드 환경에서 한 번 더 확인하는 편이 안전합니다.

## 복제/백업: 기능 테스트가 아니라 “복구 시나리오 리허설”로 한다

베타 검증에서 복제/백업은 “옵션이 동작한다”가 아니라 “운영 시나리오가 재현된다”가 목표입니다.

### logical replication

PostgreSQL 19 릴리스 노트의 Overview에는 logical replication이 sequence 값을 복제하고, `wal_level=replica`에서 서버 재시작 없이 logical replication을 활성화할 수 있다는 변경이 포함되어 있습니다.[^10]

이건 기능 자체보다도 호환성 포인트가 큽니다.

* sequence 기반 ID를 쓰는 시스템에서 subscriber의 데이터 정합성
* CDC 파이프라인(debezium 등)이 sequence 이벤트를 어떻게 다루는지
* slot, decoding plugin이 빈 prepared transaction 같은 모서리 케이스에서 깨지지 않는지

여기까지는 “테스트 케이스”가 아니라 “장애 상황 리허설”로 해야 잡힙니다.

* publisher에서 prepared transaction을 섞어 본다.
* 트랜잭션이 비어 있는 prepared transaction 같은 극단도 넣는다.
* subscriber 쪽 apply worker가 중간에 죽었다가 다시 붙는 시나리오를 만든다.

베타 3 발표문에는 logical decoding 관련 CVE와 버그 픽스가 포함되어 있어, 이 영역 자체가 최근에 많이 흔들렸음을 암시합니다.[^2]

### physical backup / verify / restore

실무에서 백업 검증은 “백업이 성공했다”가 아니라 “복구가 성공했다”입니다.

* 베타 클러스터에서 base backup 생성
* WAL 아카이브 포함
* 다른 인스턴스에서 복구
* 애플리케이션 리드/라이트가 정상인지 확인

RDS Preview는 스냅샷이 Preview 내부에서만 복구 가능하다는 제약이 있기 때문에, 오히려 dump/load나 logical migration을 같이 설계하게 됩니다.[^3]

## CI 설계: Fast lane과 Slow lane을 분리해야 오래 간다

베타 검증을 CI에 붙일 때 유지비를 결정하는 건 “얼마나 자주, 얼마나 무겁게”입니다.

### Fast lane (PR마다): 호환성/회귀 후보를 빨리 모으는 레일

* Docker로 `postgres:19beta3` 서비스 띄움[^4]
* 마이그레이션 적용
* 대표 쿼리/ORM 테스트
* extension smoke test
* EXPLAIN JSON 아티팩트 저장

이 레일의 목표는 실패를 빨리 만드는 겁니다. 성능 수치까지 여기서 판정하려 하면 CI가 불안정해집니다.

### Slow lane (Nightly/Weekly): 업그레이드·운영 시나리오를 리허설하는 레일

* pg_upgrade 리허설(필요할 때만)
* pgbench 같은 반복 벤치(단, 상대 비교)
* logical replication, 백업/복구 시나리오

RDS Preview까지 얹는 건 비용이 늘어납니다. 대신 “운영에서만 의미 있는 것”만 올리는 편이 낫습니다.

* 파라미터 그룹/스토리지/IO
* 스냅샷/복구 제약
* IAM auth, VPC, 보안그룹

RDS Preview 인스턴스는 최대 60일 유지 후 삭제되므로, 테스트 프로젝트를 6~8주 단위로 끊는 운영이 맞습니다.[^3]

## 회의론: 베타가 바뀌면 테스트가 무의미해지는가

베타 테스트가 무의미해지는 대표 케이스는 두 가지입니다.

1) 베타에서 기능/동작이 또 바뀌는 경우

2) 내 워크로드가 아니라 “남의 벤치”만 돌린 경우

첫 번째는 완전히 피할 수는 없습니다. PostgreSQL도 베타는 프로덕션 용이 아니고, 베타 기간에 호환성이 깨지는 변경이 있을 수 있다고 경고합니다.[^1]

하지만 feature freeze 이후의 변경은 본질적으로 “버그 수정/회귀 수정”에 가깝고, 그래서 지금이 가장 싸게 검증할 수 있는 구간이라는 판단이 성립합니다.

두 번째는 피할 수 있습니다. 그래서 테스트 플랜이 “19의 기능 리스트”가 아니라, 앞에서 정리한 의존성 그래프(extensions/driver/ORM/plan/replication/backup)로 구성돼야 합니다.

## 도입 판단 기준: 통과 조건을 미리 정하면 베타가 끝나도 흔들리지 않는다

베타 테스트의 산출물이 “19로 갈까 말까”가 되려면, 통과 조건이 필요합니다. 나는 아래처럼 정리했습니다.

* extensions: 설치/업데이트/핵심 연산이 모두 성공
* 드라이버/ORM: 연결 경로(직결/pooler), prepared/simple, 트랜잭션 패턴에서 실패 없음
* 플랜: 상위 N개 쿼리에서 플랜 변화가 있더라도 설명 가능(통계/토글/인덱스)
* 성능: 대표 워크로드에서 P95/P99가 명확히 악화되지 않음(절대값이 아니라 변화량)
* 복제/백업: 복구 시나리오 리허설이 성공

PostgreSQL 19 스케줄 측면에서도 베타는 창이 짧습니다. 19의 Feature Freeze가 2026-04-08(UTC)였고, Beta 3가 2026-08-13, Beta 4가 2026-09-24로 잡혀 있습니다.[^11]

내 결론은 단순합니다. 베타는 새 기능을 구경하는 시간이 아니라, 릴리스 후에 가장 비싸게 터질 수 있는 호환성·회귀를 가장 싸게 잡는 시간입니다.

## 참고 자료

- [PostgreSQL Beta Information](https://www.postgresql.org/developer/beta/)
- [PostgreSQL 18.6, 17.11, 16.15, 15.19, 14.24 and 19 Beta 3 Released!](https://www.postgresql.org/about/news/postgresql-186-1711-1615-1519-1424-and-19-beta-3-released-3365/)
- [PostgreSQL 19 Release Notes (19.0)](https://www.postgresql.org/docs/release/19.0/)
- [PostgreSQL 19 Release Notes (Release 19)](https://www.postgresql.org/docs/19/release-19.html)
- [pg_plan_advice 문서](https://www.postgresql.org/docs/19/pgplanadvice.html)
- [enable_eager_aggregate 설정(Query Planning)](https://www.postgresql.org/docs/19/runtime-config-query.html)
- [pg_stat_autovacuum_scores 문서](https://www.postgresql.org/docs/19/monitoring-stats.html)
- [Routine Vacuuming / Autovacuum scoring 문서](https://www.postgresql.org/docs/19/routine-vacuuming.html)
- [PostgreSQL 19 Open Items (schedule)](https://wiki.postgresql.org/wiki/PostgreSQL_19_Open_Items)
- [HowToBetaTest (PostgreSQL wiki)](https://wiki.postgresql.org/wiki/HowToBetaTest)
- [Postgres Docker Official Image (tags 포함)](https://hub.docker.com/_/postgres)
- [PostgreSQL 19 Beta 3 is now available in Amazon RDS Database Preview Environment](https://aws.amazon.com/about-aws/whats-new/2026/08/postgresql-19-beta-3-amazon-rds-database-preview-environment/)
- [Working with the Database Preview environment (Amazon RDS User Guide)](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/working-with-the-database-preview-environment.html)
- [PostgreSQL FTP source browser](https://www.postgresql.org/ftp/source/)

[^1]: <https://www.postgresql.org/developer/beta/>
[^2]: <https://www.postgresql.org/about/news/postgresql-186-1711-1615-1519-1424-and-19-beta-3-released-3365/>
[^3]: <https://aws.amazon.com/about-aws/whats-new/2026/08/postgresql-19-beta-3-amazon-rds-database-preview-environment/>
[^4]: <https://hub.docker.com/_/postgres>
[^5]: <https://www.postgresql.org/ftp/source/>
[^6]: <https://www.postgresql.org/docs/19/pgplanadvice.html>
[^7]: <https://www.postgresql.org/docs/release/19.0/>
[^8]: <https://www.postgresql.org/docs/19/runtime-config-query.html>
[^9]: <https://www.postgresql.org/docs/19/monitoring-stats.html>
[^10]: <https://www.postgresql.org/docs/19/release-19.html>
[^11]: <https://wiki.postgresql.org/wiki/PostgreSQL_19_Open_Items>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
