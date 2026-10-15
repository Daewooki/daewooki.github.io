---
title: "PostgreSQL 19 RC 기간 확장에 맞춘 테스트 윈도우 재설계"
description: "PostgreSQL 19 GA가 11/19로 이동하면서 RC 기간이 길어졌습니다. 확장·드라이버, 플랜 회귀, pg_upgrade 리허설 순서를 다시 짭니다."
date: 2026-10-15 10:02:05 +0900
categories: ["News", "Database"]
tags: ["postgresql", "release-management", "extensions", "query-plans", "pg-upgrade", "ci-cd"]
render_with_liquid: false
---

## 일정 변경 요약: RC1 유지, RC2 신설, GA 11/19

2026-10-10에 release team이 pgsql-hackers에 PostgreSQL 19 릴리스 일정 업데이트를 공유했습니다. 핵심은 세 가지입니다.

- RC1은 2026-10-15(목요일)로 유지
- RC2를 2026-11-12(목요일)로 추가
- GA를 2026-11-19(목요일)로 이동

원문 메일에서 RC2를 넣은 이유를 명확히 말합니다. back branches에 들어간 fixes의 양이 많아서, 그걸 RC2로 한 번 더 묶어 배포한 다음 GA로 가겠다는 판단입니다. 일정의 목적도 “안정성과 신뢰성”으로 표현합니다.[^1][^2]

이 업데이트는 2026-09-28에 공유된 기존 계획(“RC1 10/15, GA 10/29”)을 사실상 폐기합니다.[^3][^4]

PostgreSQL wiki의 Open Items 페이지도 같은 “Current schedule”로 정리되어 있습니다.[^5][^5]

GA를 “planned scheduled update release” 1주 뒤로 옮겼다고 언급하는데, 여기서 update release는 PostgreSQL 프로젝트가 분기별(2/5/8/11월, 보통 둘째 목요일)로 잡아두는 minor release 일정 맥락입니다. roadmap에 2026-11-12가 찍혀 있습니다.[^6][^6]

## 왜 ‘GA 연기’보다 ‘RC 기간 확장’이 더 중요해졌나

내가 이걸 “연기”로 받아들이지 않는 이유는, 일정이 밀렸다는 사실보다 RC의 성격이 바뀌었기 때문입니다.

기존(9/28 공지)의 RC 모델은 “RC1 → 2주 관찰 → GA”에 가깝습니다. 이 흐름에서 RC는 거의 최종 빌드의 확인 단계고, 팀 관점에서는 **짧은 베타/RC 테스트로 ‘크게 터질 것’만 걸러내는** 방식이 됩니다.[^4]

반면 10/10 공지 이후의 모델은 “RC1 → RC2 → GA”입니다. RC2는 단순히 날짜를 늘린 게 아니라, back branches로 들어간 수정(양이 많다고 직접 말합니다)을 한 번 더 모아서 배포한다는 선언입니다. 즉 RC1에서 끝까지 품질을 끌어올릴 자신이 없어서가 아니라, RC1~RC2 사이에 실제로 내용물이 더 들어올 가능성을 전제로 한 설계입니다.[^2]

이럴 때 팀이 흔히 저지르는 실수는 다음입니다.

- RC1에서 한 번 크게 테스트하고 “통과”로 처리
- RC2/GA에서 다시 잡히는 호환성 문제를 운영 일정으로 떠안음

RC 기간이 길어졌다는 건, 그 기간 동안 커뮤니티가 더 많이 움직인다는 뜻이기도 합니다. 테스트 전략도 “한 번에 끝내는 대규모 검증”이 아니라 “**비용이 비싼 검증을 앞에 두고, 반복 가능한 검증을 뒤로 미루는**” 쪽이 됩니다.

나는 이 유형의 상황을 .NET RC adoption ring을 설계할 때도 비슷하게 봤습니다. RC는 안정화 구간이지만, 동시에 내용이 바뀔 수 있는 구간이라서, 비싼 검증을 언제 고정시키느냐가 전체 리스크를 좌우합니다.[^7]

## 테스트 윈도우를 3개 트랙으로 쪼개기: 호환성/플랜/업그레이드

RC 기간이 늘어났을 때, 내가 운영 일정에서 먼저 바꾸는 건 “테스트 항목”이 아니라 “테스트의 순서”입니다. 여기서는 세 트랙을 분리합니다.

1) Extension·Driver compatibility matrix
2) Query plan regression(= 플랜 변화 탐지)
3) pg_upgrade rehearsal

이 순서는 취향이 아니라 dependency입니다.

- extension/driver가 깨지면, 그 위에서 돌리는 모든 테스트(플랜, 업그레이드)가 “실패 이유를 분리하기 어려운” 상태가 됩니다.
- 플랜 회귀는 데이터/통계/설정/쿼리 형태에 민감해서, 재현 환경을 빨리 고정해두는 편이 유리합니다.
- pg_upgrade는 마지막에 해야 하는 테스트처럼 보이지만, 실제로는 가장 시간이 오래 걸리는 runbook 작업이 같이 딸려옵니다. 그래서 RC1에서 착수해 RC2에 끝내는 게 맞습니다.

이 글에서는 각 트랙을 어떤 순서로 돌려야 RC2를 추가한 일정(10/15 → 11/12 → 11/19)을 리스크 감소로 바꿀 수 있는지에 집중합니다. 일정 자체는 메일과 wiki에서 확인됐고, 그 사실을 전제로 얘기합니다.[^2]

## (1) Extension·Driver compatibility matrix: “많이 돌리기”가 아니라 “먼저 고정하기”

호환성 매트릭스는 넓히면 끝이 없습니다. RC 기간 확장 상황에서 중요한 건 범위가 아니라 고정 지점입니다.

### RC1에서 고정해야 하는 것: ‘지원 선언’의 최소 단위

내 기준에서 RC1에서 고정해야 하는 항목은 다음 세 덩어리입니다.

- **연결 계층**: libpq 기반(예: psql/pg_dump/pg_restore), JDBC, Npgsql, psycopg
- **DB 내부 의존성**: 꼭 필요한 extensions(특히 shared_preload_libraries가 필요한 것)
- **마이그레이션 도구**: schema migration tool(Flyway/Liquibase 등), ORM의 DDL 생성 패턴

여기서 “고정”이란 단순히 목록을 적는 게 아니라, “19에서 깨지면 업그레이드를 멈추는 조건”을 정한다는 뜻입니다. 예를 들어,

- JDBC에서 SCRAM auth 연결 실패
- Npgsql에서 timestamp/DateTime mapping의 예외
- 필수 extension 설치/업데이트 실패

같은 건 기능 회귀로 즉시 중단 조건이 됩니다. 반대로, 특정 extension의 성능 이슈는 중단이 아니라 대응(설정 변경/쿼리 수정)으로 분류합니다.

### RC2에서 해야 하는 것: ‘추가된 fixes’에 대한 재검증 단축

10/10 메일은 “back branches에 많은 fixes가 들어갔다”를 RC2 신설 이유로 듭니다. 이 말은 RC2에서 다시 호환성 이슈가 튀어나올 확률이 의미 있게 있다는 뜻입니다.[^2]

따라서 RC2에서는 매트릭스를 확장하지 않고, RC1에서 고정한 축을 그대로 재실행합니다. 여기서 속도를 만드는 방법은 두 가지입니다.

- 컨테이너/CI로 “버튼 한 번에 재실행” 가능하게 만들기
- 결과 비교를 “성공/실패”가 아니라 “변화 감지”로 바꾸기

### 실행 가능한 예시: Postgres 이미지 스왑형 매트릭스 러너

아래는 내가 실제로 자주 쓰는 형태의 skeleton입니다.

- Postgres 버전을 image tag로 바꿔 끼우고
- core extensions를 활성화한 뒤
- 드라이버 테스트(여기서는 psycopg3 + pytest)를 반복 실행합니다.

이 예시는 “드라이버가 실제로 DB에 붙어 CRUD/transaction/prepare/COPY를 돌릴 수 있는가”까지를 확인합니다. 테스트가 통과한 뒤에야 애플리케이션 전체 통합 테스트로 넘어갑니다.

#### 1) compose.yaml

```yaml
services:
  db:
    image: ${PG_IMAGE:-postgres:18.6}
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_USER: app
      POSTGRES_DB: appdb
    ports:
      - "55432:5432"
    command: >
      -c shared_preload_libraries=pg_stat_statements
      -c pg_stat_statements.track=all
      -c jit=off
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d appdb"]
      interval: 2s
      timeout: 3s
      retries: 30
```

- `jit=off`는 성능을 보려는 목적이 아니라, 드라이버/쿼리 계층 호환성 검증에서 변수를 줄이기 위한 선택입니다.
- shared_preload_libraries는 `pg_stat_statements`처럼 실제 운영에서 켜는 core extension을 대상으로 합니다.

#### 2) tests/requirements.txt

```txt
psycopg[binary]==3.2.3
pytest==8.3.3
```

#### 3) tests/test_smoke.py

```python
import os
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://app:postgres@localhost:55432/appdb")

def test_txn_and_extensions():
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

            cur.execute("CREATE TABLE IF NOT EXISTS t(id bigserial primary key, payload text)")
            cur.execute("INSERT INTO t(payload) VALUES (%s), (%s)", ("a", "b"))
            cur.execute("SELECT count(*) FROM t")
            assert cur.fetchone()[0] >= 2

            # prepared statement + parameter type inference
            cur.execute("PREPARE q(bigint) AS SELECT payload FROM t WHERE id = $1")
            cur.execute("EXECUTE q(%s)", (1,))
            cur.fetchone()

            # verify pg_stat_statements view exists and is queryable
            cur.execute("SELECT count(*) FROM pg_stat_statements")
            cur.fetchone()
```

#### 4) run_matrix.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# 예: postgres:19rc1 이미지가 올라오면 여기서만 스왑
PG_IMAGES=(
  "postgres:18.6"
  "postgres:19rc1"  # 없으면 실행 실패하므로, 팀 환경에 맞게 바꿉니다.
)

PSYCOPG_VERSIONS=(
  "3.2.3"
)

for img in "${PG_IMAGES[@]}"; do
  echo "=== PG_IMAGE=${img} ==="
  export PG_IMAGE="$img"

  docker compose up -d --wait

  for v in "${PSYCOPG_VERSIONS[@]}"; do
    echo "--- psycopg=${v} ---"
    (cd tests && python -m venv .venv && source .venv/bin/activate && \
      pip install -r requirements.txt && \
      DATABASE_URL="postgresql://app:postgres@localhost:55432/appdb" pytest -q)
  done

  docker compose down -v
  echo

done
```

#### 실행 명령

```bash
chmod +x run_matrix.sh
./run_matrix.sh
```

#### 예상 출력(성공 시)

```text
=== PG_IMAGE=postgres:18.6 ===
--- psycopg=3.2.3 ---
1 passed in 1.12s

=== PG_IMAGE=postgres:19rc1 ===
--- psycopg=3.2.3 ---
1 passed in 1.20s
```

이런 형태를 RC1에서 만들어두면 RC2 때는 “이미지 태그만 바꾸고 재실행”으로 바뀝니다. RC 기간 확장에서 이게 가장 큰 이득입니다.

### 매트릭스의 함정: ‘extension이 설치된다’와 ‘운영이 된다’는 다르다

extension 호환성에서 초반에 자주 놓치는 건, CREATE EXTENSION 성공만 보고 넘어가는 경우입니다.

- shared_preload_libraries가 필요한 extension은 postmaster restart가 끼어들고, 운영 자동화(runbook, Helm chart, systemd unit)까지 함께 건드립니다.
- extension update는 `ALTER EXTENSION ... UPDATE`가 들어갑니다. 이는 pg_upgrade 이후 단계에서 다시 등장합니다.

그래서 나는 RC1 매트릭스에서 extension을 “설치”가 아니라 “최소 사용 시나리오”까지 포함해 봅니다. 예를 들면 pgcrypto면 digest/uuid 생성, pg_stat_statements면 view 조회까지 포함합니다.

## (2) Query plan 회귀: ‘성능 측정’이 아니라 ‘플랜 변화 탐지’로 바꾼다

RC 기간이 길어지면, “성능이 얼마나 좋아졌나/나빠졌나” 같은 수치 질문을 하기가 더 어려워집니다.

- RC1과 RC2 사이에 fixes가 많이 들어온다고 이미 선언되어 있고[^2]
- 그 fixes는 planner/optimizer 뿐 아니라 executor, stats, catalog, extension까지 영향을 줍니다.

따라서 이 구간에서 현실적인 목표는 “성능 벤치마크”가 아니라 “플랜이 바뀌었는지, 바뀌었다면 왜인지”를 빨리 알아내는 것입니다.

### RC1에서 해야 하는 일: 플랜 baseline을 만들고, 깨지는 패턴을 분류

내가 RC1에서 먼저 하는 건 아래입니다.

- 프로덕션(or production-like)에서 “문제가 될 만한 쿼리 묶음”을 뽑는다
- 그 쿼리를 staging 데이터로 재현 가능하게 만든다
- 18(현재) vs 19(RC)에서 EXPLAIN(JSON)을 저장해 비교한다

이 과정을 빨리 시작해야 하는 이유는, 쿼리 플랜 회귀의 대부분이 Postgres 자체 버그라기보다 “통계/인덱스/쿼리 형태” 쪽의 상호작용으로 튀어나오기 때문입니다. 재현 데이터를 준비하는 시간이 더 오래 걸립니다.

예전 글에서 PostgreSQL 19 Beta 검증 윈도우를 다룰 때도 비슷한 이야기를 했는데, Beta에서 했던 작업을 RC에서 다시 할 때는 “범위 확장”이 아니라 “변화 감지 자동화”로 성격이 바뀝니다.[^8]

### RC2에서 해야 하는 일: 변화 감지 결과를 ‘승인 리스트’로 바꾸기

RC2에서 플랜이 다시 바뀌는 건 자연스럽습니다. 중요한 건 다음 중 어느 쪽인가입니다.

- 플랜이 바뀌었지만 납득 가능한 변화(예: cost model 변화로 index scan이 선택됨)
- 플랜이 바뀌었고, SLA에 영향이 있을 가능성이 큰 변화(예: nested loop 폭발)

RC 기간 확장에서는 “플랜이 바뀌었다”를 이슈로 삼기보다, “바뀐 플랜이 승인됐는가”를 상태로 관리해야 합니다.

### 실행 가능한 예시: EXPLAIN(JSON) fingerprint + diff

아래 스크립트는 내가 내부적으로 자주 쓰는 단순한 형태입니다.

- 쿼리 목록을 파일로 넣고
- 각 쿼리에 대해 `EXPLAIN (FORMAT JSON)` 결과를 저장
- 플랜 트리의 node types를 펼쳐서 fingerprint를 만든 다음
- baseline과 비교해 변경을 보고합니다.

이 방식은 “정밀 성능 비교”는 못 하지만, RC 기간에 필요한 “플랜이 왜 바뀌었는지 조사할 트리거”로는 충분히 쓸 만합니다.

#### 1) queries.sql (현실적인 패턴)

```sql
-- 주문 리스트 + 최신순 페이징
SELECT o.id, o.user_id, o.status, o.created_at
FROM orders o
WHERE o.user_id = $1
ORDER BY o.created_at DESC
LIMIT 50;

-- 이벤트 테이블에서 기간 필터 + 집계
SELECT date_trunc('hour', e.created_at) AS h, count(*)
FROM events e
WHERE e.created_at >= $1 AND e.created_at < $2
GROUP BY 1
ORDER BY 1;

-- 조인 + 조건부 필터
SELECT u.id, u.email, p.plan
FROM users u
JOIN subscriptions s ON s.user_id = u.id
JOIN plans p ON p.id = s.plan_id
WHERE u.deleted_at IS NULL
  AND s.status = 'active'
  AND s.renew_at < $1
ORDER BY s.renew_at ASC
LIMIT 200;
```

#### 2) plan_guard.py

```python
import json
import os
from collections import Counter

import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://app:postgres@localhost:55432/appdb")
QUERIES_FILE = os.environ.get("QUERIES_FILE", "queries.sql")
OUT_DIR = os.environ.get("OUT_DIR", "plans_out")

def flatten_node_types(node, acc):
    acc.append(node.get("Node Type", "?"))
    for k in ("Plans", "InitPlan", "Subplans"):
        for child in node.get(k, []) or []:
            flatten_node_types(child, acc)

def explain_json(cur, sql):
    cur.execute("EXPLAIN (FORMAT JSON) " + sql)
    raw = cur.fetchone()[0]
    # psycopg가 JSON을 python object로 줄 때/문자열로 줄 때 둘 다 처리
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw

def fingerprint(explain_doc):
    # EXPLAIN(JSON)은 리스트로 감싸진 top-level 구조
    plan = explain_doc[0]["Plan"]
    types = []
    flatten_node_types(plan, types)
    cnt = Counter(types)
    # node type 카운트를 정렬해 fingerprint 문자열로
    return "|".join(f"{k}:{cnt[k]}" for k in sorted(cnt.keys()))

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(QUERIES_FILE, "r", encoding="utf-8") as f:
        chunks = [q.strip() for q in f.read().split(";")]
        queries = [q for q in chunks if q]

    results = []

    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            for i, q in enumerate(queries, start=1):
                doc = explain_json(cur, q)
                fp = fingerprint(doc)
                path = os.path.join(OUT_DIR, f"q{i:03}.json")
                with open(path, "w", encoding="utf-8") as out:
                    json.dump(doc, out, ensure_ascii=False, indent=2)
                results.append((i, fp, path))

    for i, fp, path in results:
        print(f"q{i:03} fingerprint={fp} file={path}")

if __name__ == "__main__":
    main()
```

#### 실행 명령

```bash
python -m venv .venv
source .venv/bin/activate
pip install "psycopg[binary]==3.2.3"

export DATABASE_URL="postgresql://app:postgres@localhost:55432/appdb"
export QUERIES_FILE="queries.sql"
export OUT_DIR="plans_pg19rc1"
python plan_guard.py
```

#### 예상 출력(형태)

```text
q001 fingerprint=Index Scan:1|Limit:1|Sort:1 file=plans_pg19rc1/q001.json
q002 fingerprint=Aggregate:1|Seq Scan:1|Sort:1 file=plans_pg19rc1/q002.json
q003 fingerprint=Hash Join:2|Limit:1|Sort:1 file=plans_pg19rc1/q003.json
```

이 출력이 baseline(예: `plans_pg18/`)과 달라지면, 그 쿼리만 집중 조사 대상으로 올립니다.

### 플랜 회귀에서 자주 터지는 실제 함정

- `default_statistics_target`나 `random_page_cost` 같은 설정 차이
- ANALYZE 타이밍 차이(데이터는 같지만 통계가 다름)
- extension의 operator class나 함수 inlining 변화

RC 기간 확장 상황에서는 “Postgres가 느려졌다” 결론을 빨리 내리기보다, 이 함정부터 제거하는 편이 비용이 덜 듭니다.

## (3) pg_upgrade 리허설: RC1에서 시작해서 RC2 전에 끝낸다

pg_upgrade는 많은 팀에서 “GA 나오면 그때 해보자”로 미뤄집니다. RC 기간이 길어졌을 때 이 판단은 특히 위험해집니다.

- RC2가 생겼다는 건, RC1 이후에도 많은 fixes가 들어온다는 뜻이고[^2]
- fixes는 catalog / system view / extension script / pg_dump 출력 같은 곳에도 영향을 줍니다.

pg_upgrade는 실제로 “업그레이드 툴을 실행해보는 테스트”가 아니라, 아래를 한 묶음으로 끌고 옵니다.

- 다운타임 예측
- 롤백 전략(특히 logical replication/physical replica 포함)
- extension update 순서
- post-upgrade analyze/vacuum, reindex 여부

그래서 나는 RC1에서 일단 리허설 파이프라인을 만들고, RC2에서는 “같은 파이프라인을 다시 돌려서 결과가 안정적인지” 확인합니다.

### 순서: 호환성 매트릭스 → 플랜 변화 탐지 → pg_upgrade

여기서 순서가 중요한 이유는 단순합니다.

- extension/driver가 깨진 상태로 pg_upgrade를 하면, 실패 원인이 “업그레이드”인지 “확장”인지 “드라이버”인지 분리가 안 됩니다.
- 플랜 회귀 탐지의 baseline은 “업그레이드 전/후” 비교가 아니라 “버전 간” 비교여야 합니다. pg_upgrade 이후에는 vacuum/analyze/cluster 상태가 섞여서 플랜 비교가 더 어려워집니다.

즉, pg_upgrade는 마지막이 아니라 “앞의 두 트랙을 통과한 다음에, 운영 절차를 완성하는 단계”로 두는 게 맞습니다.

### 실행 가능한 리허설 스크립트: 로컬 2클러스터 + pg_upgrade --check

19 RC 패키징/이미지 상황은 팀마다 다릅니다. 이 글에서는 “두 버전의 바이너리가 같은 머신에 설치되어 있다”는 가장 보수적인 형태로 작성합니다. RC1/RC2를 소스 빌드로 들고 가든, 패키지로 들고 가든, 결국 `oldbindir/newbindir` 경로만 바뀝니다.

PostgreSQL은 versioning policy에서 major/minor 릴리스 모델을 정리하고 있고, minor는 분기 단위로 나옵니다. 이 전제 때문에 GA가 11/19로 움직이면서 11/12 update release(= minor) 다음 주에 GA를 두는 형태가 됐다고 해석할 수 있습니다.[^9][^6][^9]

#### pg_upgrade_rehearsal.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# 환경에 맞게 조정
OLD_PG_BINDIR=${OLD_PG_BINDIR:-/usr/lib/postgresql/18/bin}
NEW_PG_BINDIR=${NEW_PG_BINDIR:-/usr/lib/postgresql/19/bin}

BASE_DIR=${BASE_DIR:-$PWD/pg_upgrade_lab}
OLD_DATA=$BASE_DIR/data_old
NEW_DATA=$BASE_DIR/data_new
SOCKDIR=$BASE_DIR/socket
LOGDIR=$BASE_DIR/log

mkdir -p "$BASE_DIR" "$SOCKDIR" "$LOGDIR"
rm -rf "$OLD_DATA" "$NEW_DATA"

echo "[1] init old cluster"
"$OLD_PG_BINDIR"/initdb -D "$OLD_DATA" -U postgres >/dev/null

echo "[2] start old cluster"
"$OLD_PG_BINDIR"/pg_ctl -D "$OLD_DATA" -l "$LOGDIR/old.log" -o "-k $SOCKDIR" start

echo "[3] seed minimal schema + extensions"
"$OLD_PG_BINDIR"/psql -h "$SOCKDIR" -U postgres -d postgres <<'SQL'
CREATE DATABASE appdb;
\c appdb
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE orders(
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON orders(user_id, created_at DESC);

INSERT INTO orders(user_id, status)
SELECT (random()*1000000)::bigint, 'ok'
FROM generate_series(1, 500000);
ANALYZE;
SQL

echo "[4] stop old cluster"
"$OLD_PG_BINDIR"/pg_ctl -D "$OLD_DATA" stop

echo "[5] init new cluster"
"$NEW_PG_BINDIR"/initdb -D "$NEW_DATA" -U postgres >/dev/null

echo "[6] pg_upgrade --check"
"$NEW_PG_BINDIR"/pg_upgrade \
  --old-bindir "$OLD_PG_BINDIR" \
  --new-bindir "$NEW_PG_BINDIR" \
  --old-datadir "$OLD_DATA" \
  --new-datadir "$NEW_DATA" \
  --username postgres \
  --check \
  --socketdir "$SOCKDIR" \
  --logdir "$LOGDIR"

echo "[7] pg_upgrade run"
"$NEW_PG_BINDIR"/pg_upgrade \
  --old-bindir "$OLD_PG_BINDIR" \
  --new-bindir "$NEW_PG_BINDIR" \
  --old-datadir "$OLD_DATA" \
  --new-datadir "$NEW_DATA" \
  --username postgres \
  --socketdir "$SOCKDIR" \
  --logdir "$LOGDIR"

echo "[8] start new cluster"
"$NEW_PG_BINDIR"/pg_ctl -D "$NEW_DATA" -l "$LOGDIR/new.log" -o "-k $SOCKDIR" start

echo "[9] quick sanity"
"$NEW_PG_BINDIR"/psql -h "$SOCKDIR" -U postgres -d appdb -c "SELECT count(*) FROM orders;"

"$NEW_PG_BINDIR"/pg_ctl -D "$NEW_DATA" stop

echo "OK"
```

#### 실행 명령

```bash
chmod +x pg_upgrade_rehearsal.sh
OLD_PG_BINDIR=/usr/lib/postgresql/18/bin \
NEW_PG_BINDIR=/usr/lib/postgresql/19/bin \
./pg_upgrade_rehearsal.sh
```

#### 예상 출력(성공 시, 최소 보장)

```text
[6] pg_upgrade --check
[7] pg_upgrade run
[9] quick sanity
 count
--------
 500000
OK
```

이 정도 형태를 RC1에서 만들면 RC2에서 하는 일은 단순해집니다.

- NEW_PG_BINDIR만 RC2 빌드로 교체
- 같은 스크립트를 재실행
- 결과가 같으면 runbook이 굳어짐

### pg_upgrade 리허설에서 반드시 같이 체크하는 것

- `shared_preload_libraries`가 필요한 extension을 포함했는지
- upgrade 후 `ANALYZE`/`REINDEX` 정책을 어떻게 둘지
- `pg_dump`/`pg_restore` 기반 롤백 플랜(논리 롤백)이 가능한지

나는 이걸 “업그레이드 테스트”가 아니라 “복구/롤백 테스트”에 더 가깝다고 봅니다. 성공한 업그레이드보다, 실패했을 때의 복구가 운영을 결정합니다.

## 왜 중요한가: 10/15~11/19 사이에 팀의 실패 패턴이 바뀐다

일정이 바뀌면, 그냥 캘린더만 바뀌는 게 아닙니다.

- RC1(10/15) 이후 4주 가까이 “바뀔 수 있는 준최종 버전”이 존재합니다.[^5]
- RC2(11/12)가 추가되면서, RC1에서 발견한 문제를 “GA 전에 고쳐질 확률”이 생겼습니다. 동시에 RC2에서 새로운 회귀가 들어올 수도 있습니다.[^2]
- GA(11/19)가 11월 minor release 다음 주로 붙으면서, 조직의 change freeze/연말 운영 체계와 더 자주 충돌합니다.

이때 개발팀이 흔히 하는 최악의 선택은 “GA가 늦어졌으니 우리도 미룬다”입니다. RC 기간이 늘어난 상황에서는, 미루는 동안 문제가 사라지지 않습니다. 대신 문제를 발견할 시간이 줄어듭니다.

RC 기간 확장은 “테스트를 더 오래 할 수 있다”가 아니라, “RC2라는 재테스트 지점이 생겼다”로 해석해야 합니다.

## 반론과 회의론: RC2가 있어도 팀 리스크는 자동으로 줄지 않는다

RC2 신설이 무조건 좋은 신호냐는 질문에는 절반만 동의합니다.

좋은 점은 분명합니다.

- fixes를 더 모아서 한 번 더 candidate로 내놓겠다는 건, 품질을 우선순위로 두겠다는 뜻입니다.[^2]

다만 운영 리스크는 그대로 남습니다.

- RC1에서 통과한 테스트가 RC2에서 다시 깨질 수 있습니다(특히 extensions, planner 관련).
- 팀이 RC1에서 “대규모 일회성 테스트”를 다 해버리면 RC2에서 다시 재현 환경을 못 맞추는 경우가 많습니다.
- GA 직후(11/19)에도 바로 production에 올리기엔 부담이 큽니다. major release는 GA 직후 첫 minor들(예: 19.1, 19.2)에서 안정화되는 패턴이 반복됐고, 이건 PostgreSQL이 quarterly minor를 강하게 가져가는 정책과도 연결됩니다.[^9][^9]

결국 RC2는 “시간이 더 생겼다”가 아니라 “재테스트를 해야 할 이유가 생겼다”입니다.

## 앞으로 지켜볼 것: RC1→RC2 사이에 확인할 신호들

RC 기간 확장에서 내가 보는 신호는 기능 목록이 아니라 “어디가 흔들리고 있는가”입니다.

- Open Items wiki에서 특정 범주(planner/replication/storage)의 이슈가 계속 남아 있는지
- RC1 이후 back branches에 들어가는 fix 성격이 “crash/data corruption”류인지, “behavior change”류인지
- RC2가 “fix를 더 넣기 위한 RC2”인지, “막판 회귀를 잡기 위한 RC2”인지

Open Items 페이지는 날짜뿐 아니라 실제로 남은 이슈를 연결해두고 있어서, RC2가 어떤 성격이 될지 가늠하는 데 도움이 됩니다.[^5][^5]

## 10/15~11/19 캘린더를 이렇게 다시 나눈다: 반복 비용이 싼 것부터 굳히기

내가 팀 캘린더를 다시 짤 때는 “테스트를 빨리 끝내기”가 아니라 “RC2에서 재실행할 수 있게 만들기”를 목표로 둡니다.

- 10/15~10/22: compatibility matrix skeleton을 만들고 CI화
- 10/22~11/05: 플랜 baseline을 만들고, 회귀 후보 쿼리를 줄여나감
- 11/05~11/12: pg_upgrade rehearsal을 1회 이상 끝내고 runbook을 문서화
- 11/12(RC2): 세 트랙을 동일 절차로 재실행(범위 확장 금지)
- 11/13~11/19: GA go/no-go는 기술적 결론이 아니라 운영 결론(다운타임/롤백/extension 업데이트 순서)로 결정

여기서 핵심은 하나입니다.

- RC1에서 “자동화 틀”을 만들고
- RC2에서 “그 틀을 다시 돌려” 안정성을 확인합니다.

이렇게 접근하면 일정 변경이 리스크가 아니라 완충 장치가 됩니다.

## 지금 시점에서의 결론

2026-10-10 공지는 PostgreSQL 19의 GA가 2026-11-19로 이동했다는 사실보다, RC2(2026-11-12)가 추가되면서 RC 기간이 재테스트 구간으로 확장됐다는 점이 더 본질적입니다.[^2]

RC 기간 확장에서는 extension/driver 호환성 매트릭스를 먼저 고정하고, 그 위에서 플랜 변화 탐지를 자동화한 다음, pg_upgrade 리허설을 RC2 전에 끝내는 쪽이 리스크를 가장 싸게 줄입니다. 이 순서가 뒤집히면 RC2는 오히려 재작업 비용을 늘리는 이벤트가 됩니다.

## 참고 자료

- [Updated PostgreSQL RC / GA dates](https://www.postgresql.org/message-id/f161fbb7-e193-42eb-bec7-4cfc1af74a50@postgresql.org)
- [PostgreSQL 19 RC1 and GA release dates](https://www.postgresql.org/message-id/915517c4-d0ee-49f9-bbeb-c683ef2b9d3f@postgresql.org)
- [PostgreSQL 19 Open Items](https://wiki.postgresql.org/wiki/PostgreSQL_19_Open_Items)
- [PostgreSQL Roadmap](https://www.postgresql.org/developer/roadmap/)
- [Versioning Policy](https://www.postgresql.org/support/versioning/)
- [PostgreSQL 19 Beta 3 검증 윈도우: 확장·호환성·회귀](https://daewooki.github.io/posts/postgresql-19-beta3-test-window/)
- [.NET 11 RC1 채택 전략: Go-live RC와 업그레이드 링 설계](https://daewooki.github.io/posts/dotnet-11-rc1-go-live-adoption-strategy/)

[^1]: <https://www.postgresql.org/message-id/f161fbb7-e193-42eb-bec7-4cfc1af74a50@postgresql.org>
[^2]: <https://www.postgresql.org/message-id/f161fbb7-e193-42eb-bec7-4cfc1af74a50%40postgresql.org>
[^3]: <https://www.postgresql.org/message-id/915517c4-d0ee-49f9-bbeb-c683ef2b9d3f@postgresql.org>
[^4]: <https://www.postgresql.org/message-id/915517c4-d0ee-49f9-bbeb-c683ef2b9d3f%40postgresql.org>
[^5]: <https://wiki.postgresql.org/wiki/PostgreSQL_19_Open_Items>
[^6]: <https://www.postgresql.org/developer/roadmap/>
[^7]: <https://daewooki.github.io/posts/dotnet-11-rc1-go-live-adoption-strategy/>
[^8]: <https://daewooki.github.io/posts/postgresql-19-beta3-test-window/>
[^9]: <https://www.postgresql.org/support/versioning/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
