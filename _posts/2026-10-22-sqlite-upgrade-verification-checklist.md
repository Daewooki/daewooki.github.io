---
title: "SQLite 업그레이드 검증 체크리스트: 3.54.1이 던진 현실"
description: "SQLite를 라이브러리로 쓰는 서비스에서 쿼리 플랜·확장·플랫폼 버전 분산을 통제해 업그레이드를 안전하게 만드는 체크리스트."
date: 2026-10-22 12:37:53 +0900
categories: ["News", "Database"]
tags: ["sqlite", "upgrade-testing", "query-planner", "loadable-extensions", "mobile"]
render_with_liquid: false
---

## 3.54.1 릴리스에서 확인해야 하는 사실

2026-10-22 KST 기준으로 SQLite 공식 홈의 Latest Release가 **3.54.1 (2026-10-16)** 로 갱신되어 있습니다.[^1]

3.54.1은 기능 추가가 아니라 3.54.0(2026-10-09)의 패치 릴리스입니다. 바뀐 내용의 핵심은 딱 두 줄로 요약됩니다.

- 32-bit 빌드에서 발생 가능한 heap-buffer overflow 수정(64-bit는 영향 없음)[^2]
- 3.54.0에서 사용자들이 보고한 기타 문제 수정(세부는 check-in timeline에 흩어져 있음)[^2]

이 정도만 보면 “패치니까 바로 올리면 끝”이라는 반응이 나오기 쉬운데, 내 경험상 임베디드 DB 업그레이드는 여기서부터가 진짜 시작입니다. 이유는 3.54.1이 작아서가 아니라, “지금이 다운스트림들이 버전 정렬을 할 명분이 생긴 타이밍”이기 때문입니다.

- 3.54.0은 query planner 개선, temp file 생성 방식 변경(O_TMPFILE), Windows 지원 범위 변화 같은 운영 영향도가 큰 변경을 포함합니다.[^3]
- 3.54.1은 메모리 안전성 이슈(32-bit)를 정리하면서 “올릴 수 있는 가장 최신”이라는 기준점을 새로 찍었습니다.[^3]

업그레이드 검증은 보통 늦게 시작할수록 비싸집니다. 릴리스 직후에 움직이면, (1) 내가 가진 버전 분산(모바일/데스크톱/서버)을 표면화할 수 있고 (2) 계획을 세운 뒤에 3.54.2 같은 다음 패치가 와도 같은 파이프라인으로 반복할 수 있습니다.

## ‘임베디드 DB는 업그레이드가 쉽다’는 말이 자주 틀리는 이유

SQLite는 “파일 포맷 호환이 오래 유지된다”는 점에서 업그레이드가 쉬운 편인 건 맞습니다. 다만 서비스에서 SQLite를 ‘라이브러리 의존성’으로 쓰기 시작하면, 업그레이드는 파일 포맷 문제보다 아래 세 가지가 더 자주 발목을 잡습니다.

첫째, query planner는 같은 결과를 내면서도 다른 실행 전략을 선택할 수 있고, 그 변화가 성능 회귀로 곧장 이어질 수 있습니다. 3.54.0만 해도 “expr OR TRUE/FALSE 최적화”, “IN 우변 SELECT의 DISTINCT 무시”, “LIMIT 1인 UNION의 메모리/속도 개선”이 들어갔습니다.[^3]

둘째, 서비스가 사용하는 SQLite는 ‘SQLite 코어’ 하나가 아닙니다. FTS5, JSON, loadable extension, 암호화 래퍼(SQLCipher 같은 포크), ICU, custom tokenizer 등 확장과 빌드 옵션이 실제 제품의 DB 기능 집합을 정의합니다. 컴파일 옵션에 따라 JSON이 빠지거나(load-time이 아니라 compile-time에서 OMIT) extension loading 자체가 제거될 수도 있습니다.[^4]

셋째, 조직이 커질수록 SQLite 버전이 “플랫폼이 제공하는 것”으로 흩어집니다.

- Android는 OS 버전에 따라 프레임워크 SQLite 버전이 달라집니다.[^5]
- 서버는 distro 패키지/컨테이너 베이스 이미지에 따라 달라지고, 예를 들어 Alpine은 edge 브랜치에서 3.54.1-r0가 2026-10-17에 빌드된 것으로 보입니다(업스트림 릴리스 직후 반영).[^6]
- 데스크톱/번들 앱은 “시스템에 있는 libsqlite3”를 링크하거나, 제품 내에 정적으로/동적으로 번들합니다.

이 3가지가 합쳐지면, 업그레이드는 “버전 하나 올리기”가 아니라 “플랜/확장/플랫폼 조합을 하나의 제품 규격으로 수렴시키는 작업”이 됩니다. 예전에 systemd 안정 릴리스 운영 기준을 정리하면서 백포트 vs 자체 업그레이드의 경계가 결국 검증 체계의 유무로 갈린다고 썼는데, SQLite도 똑같이 적용됩니다: [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)

## 체크리스트 1: 쿼리 플랜/성능 회귀 테스트를 ‘리뷰 가능한 산출물’로 만들기

내가 SQLite 업그레이드에서 가장 크게 데인 지점은 “성능 회귀를 사전에 자동으로 잡지 못한 것”이었습니다. SQLite는 서버가 없으니 롤아웃이 쉬울 거라 생각했는데, 실제로는 앱/SDK/툴체인 곳곳에서 올라가고, 한 번 올라간 다음에는 되돌리기 어렵습니다(특히 모바일).

그래서 목표를 아래처럼 잡는 게 현실적입니다.

- 목표 1: 업그레이드 전후로 “같은 쿼리의 EXPLAIN QUERY PLAN 결과”를 남기고 diff를 리뷰한다.
- 목표 2: 플랜 diff가 생기면 ‘무조건 실패’가 아니라, 벤치마크/프로파일 결과와 함께 판단한다.
- 목표 3: 성능 측정은 speedtest1 같은 범용 벤치도 참고하되, 최종 판정은 서비스 쿼리로 한다.

SQLite가 자체적으로도 성능 측정을 위해 speedtest1 워크로드를 쓰며, 이 방식의 한계(컴파일러/플랫폼/옵션 의존)를 문서로 명시해 둔 게 중요한 힌트입니다. 즉, 숫자는 참고지만 “내 빌드/내 데이터/내 쿼리”가 기준입니다.[^7]

### 플랜 회귀 테스트의 핵심: 쿼리 결과가 아니라 쿼리 ‘의사결정’을 기록한다

sqllogictest는 쿼리 정답(correctness)을 광범위하게 검증하는 데 특화된 하네스입니다. 다만 문서에 분명히 적혀 있듯이 성능이나 인덱스 사용 같은 측면은 다루지 않습니다.[^8]

그래서 업그레이드 안전성을 높이려면 correctness 테스트(sqllogictest/자체 테스트)와 별개로, 플래너가 어떤 경로를 선택했는지를 기록하고 바뀐 이유를 설명할 수 있어야 합니다.

- EXPLAIN QUERY PLAN은 사람이 읽을 수 있고, CI 산출물로 남기기 쉽습니다.
- 다만 출력은 버전에 따라 텍스트가 바뀌거나, 같은 의미라도 표현이 바뀔 수 있으니 “기계적으로 완전 일치”를 목표로 하면 테스트가 쉽게 파괴됩니다.

내 경우는 “플랜 diff를 PR에서 리뷰하게 만드는 것”을 목표로 두고, 차단 기준은 성능 예산(예: p95 +10% 이내)을 같이 걸었습니다. Grafana 패치 업그레이드 검증 자동화를 설계했던 글에서 ‘diff는 리뷰 대상, 예산은 자동 차단’이라는 분리를 강조했는데, SQLite에서도 동일하게 먹힙니다: [Grafana 패치 업그레이드 검증 자동화 설계](https://daewooki.github.io/posts/grafana-patch-upgrade-automation/)

### 실행 가능한 하네스 예시: 두 버전의 sqlite3를 빌드해 같은 워크로드를 돌린다

아래 예시는 “3.53.4 → 3.54.1” 같은 업그레이드를 가정한 로컬/CI용 하네스입니다.

- 같은 C 코드(bench.c)를 두 버전의 libsqlite3에 링크해 `bench_old`, `bench_new`를 만든다.
- (1) schema+seed로 DB를 만든 뒤 (2) EXPLAIN QUERY PLAN 스냅샷을 뽑고 (3) 같은 쿼리를 여러 번 실행해 wall-clock을 잰다.
- 빌드 옵션은 반드시 프로덕션과 맞춰야 합니다(FTS5/JSON/DBSTAT/THREADSAFE 같은 것).

SQLite 다운로드 페이지는 3.54.1의 autoconf/amalgamation 번들 이름이 `sqlite-autoconf-3540100.tar.gz` 형태임을 보여주고, “3.X.Y는 3XXYY00” 규칙으로 인코딩한다고 적어둡니다.[^9]

#### Dockerfile

```dockerfile
# docker build -t sqlite-upgrade-harness --build-arg OLD=3530400 --build-arg NEW=3540100 .
# docker run --rm -it sqlite-upgrade-harness

FROM ubuntu:24.04

ARG OLD=3530400
ARG NEW=3540100

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# Download SQLite autoconf bundles (binary downloads; URLs are stable by convention)
# OLD=3530400 -> SQLite 3.53.4
# NEW=3540100 -> SQLite 3.54.1
RUN set -eux; \
    mkdir -p /src; \
    curl -fsSL -o /src/sqlite-autoconf-${OLD}.tar.gz https://www.sqlite.org/2026/sqlite-autoconf-${OLD}.tar.gz; \
    curl -fsSL -o /src/sqlite-autoconf-${NEW}.tar.gz https://www.sqlite.org/2026/sqlite-autoconf-${NEW}.tar.gz

COPY bench/ /work/bench/
COPY workload/ /work/workload/
COPY scripts/ /work/scripts/

RUN set -eux; \
    bash /work/scripts/build_sqlite.sh /src/sqlite-autoconf-${OLD}.tar.gz /opt/sqlite-old; \
    bash /work/scripts/build_sqlite.sh /src/sqlite-autoconf-${NEW}.tar.gz /opt/sqlite-new; \
    bash /work/scripts/build_bench.sh /opt/sqlite-old /opt/sqlite-new

CMD ["bash", "/work/scripts/run_all.sh"]
```

#### scripts/build_sqlite.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

TARBALL="$1"     # sqlite-autoconf-*.tar.gz
PREFIX="$2"      # /opt/sqlite-old or /opt/sqlite-new

mkdir -p /tmp/sqlite-build
cd /tmp/sqlite-build

rm -rf src
mkdir -p src

tar -xzf "$TARBALL" -C src --strip-components=1
cd src

# Production-like compile flags (example):
# - FTS5: compile-time opt-in in many build flows
# - DBSTAT: useful for disk usage analysis / some tools depend on it
# - THREADSAFE=1: common default, but make it explicit
export CFLAGS="-O2 -fno-omit-frame-pointer -DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_DBSTAT_VTAB"

./configure --prefix="$PREFIX"
make -j"$(nproc)"
make install

# install provides sqlite3 binary and headers
"$PREFIX/bin/sqlite3" -version
```

#### bench/bench.c

```c
// build: gcc -O2 -I<sqlite>/include -L<sqlite>/lib bench.c -lsqlite3 -o bench

#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static long long now_ns(void){
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (long long)ts.tv_sec*1000000000LL + ts.tv_nsec;
}

static void die(sqlite3 *db, const char *msg){
  fprintf(stderr, "FATAL: %s: %s\n", msg, sqlite3_errmsg(db));
  exit(1);
}

static void exec_sql(sqlite3 *db, const char *sql){
  char *err = NULL;
  if(sqlite3_exec(db, sql, 0, 0, &err)!=SQLITE_OK){
    fprintf(stderr, "SQL error: %s\n", err);
    sqlite3_free(err);
    die(db, "exec_sql");
  }
}

static void run_eqp(sqlite3 *db, const char *sql){
  sqlite3_stmt *st = NULL;
  char *eqp = NULL;
  size_t n = 0;

  // Prepend EXPLAIN QUERY PLAN
  size_t len = strlen(sql);
  char *buf = (char*)malloc(len + 64);
  snprintf(buf, len + 64, "EXPLAIN QUERY PLAN %s", sql);

  if(sqlite3_prepare_v2(db, buf, -1, &st, 0)!=SQLITE_OK) die(db, "prepare EQP");

  printf("-- EQP for: %s\n", sql);
  while(sqlite3_step(st)==SQLITE_ROW){
    int id = sqlite3_column_int(st, 0);
    int parent = sqlite3_column_int(st, 1);
    int notused = sqlite3_column_int(st, 2);
    const unsigned char *detail = sqlite3_column_text(st, 3);
    printf("%d|%d|%d|%s\n", id, parent, notused, detail);
  }
  sqlite3_finalize(st);
  free(buf);
}

static void bench_query(sqlite3 *db, const char *sql, int iters){
  sqlite3_stmt *st = NULL;
  if(sqlite3_prepare_v2(db, sql, -1, &st, 0)!=SQLITE_OK) die(db, "prepare");

  // warm-up
  sqlite3_reset(st);
  while(sqlite3_step(st)==SQLITE_ROW){}

  long long t0 = now_ns();
  long long rows = 0;
  for(int i=0;i<iters;i++){
    sqlite3_reset(st);
    while(1){
      int rc = sqlite3_step(st);
      if(rc==SQLITE_ROW){ rows++; continue; }
      if(rc==SQLITE_DONE) break;
      die(db, "step");
    }
  }
  long long t1 = now_ns();

  double ms = (double)(t1-t0)/1e6;
  printf("BENCH iters=%d rows=%lld time_ms=%.3f sql=%s\n", iters, rows, ms, sql);

  sqlite3_finalize(st);
}

int main(int argc, char **argv){
  if(argc<2){
    fprintf(stderr, "usage: %s <dbfile>\n", argv[0]);
    return 2;
  }

  sqlite3 *db = NULL;
  if(sqlite3_open_v2(argv[1], &db, SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE, NULL)!=SQLITE_OK){
    die(db, "open");
  }

  printf("sqlite_version=%s\n", sqlite3_libversion());

  // speed vs determinism: make choices explicit
  exec_sql(db, "PRAGMA journal_mode=WAL;");
  exec_sql(db, "PRAGMA synchronous=NORMAL;");
  exec_sql(db, "PRAGMA temp_store=MEMORY;");

  // schema + seed
  exec_sql(db, "BEGIN;");
  exec_sql(db,
    "CREATE TABLE IF NOT EXISTS events("
    "  event_id INTEGER PRIMARY KEY,"
    "  user_id INTEGER NOT NULL,"
    "  ts INTEGER NOT NULL,"
    "  kind TEXT NOT NULL,"
    "  payload TEXT NOT NULL"
    ");"
    "CREATE INDEX IF NOT EXISTS idx_events_user_ts ON events(user_id, ts DESC);"
    "CREATE INDEX IF NOT EXISTS idx_events_kind_ts ON events(kind, ts DESC);"
    "CREATE TABLE IF NOT EXISTS flags(user_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL);"
  );

  // seed data (deterministic, small but not toy)
  // 200k events, 20k users
  exec_sql(db, "DELETE FROM events;");
  exec_sql(db, "DELETE FROM flags;");

  exec_sql(db,
    "WITH RECURSIVE t(n) AS(SELECT 1 UNION ALL SELECT n+1 FROM t WHERE n<=20000) "
    "INSERT INTO flags(user_id, enabled) "
    "SELECT n, CASE WHEN (n%10)=0 THEN 1 ELSE 0 END FROM t;"
  );

  exec_sql(db,
    "WITH RECURSIVE t(n) AS(SELECT 1 UNION ALL SELECT n+1 FROM t WHERE n<200000) "
    "INSERT INTO events(event_id,user_id,ts,kind,payload) "
    "SELECT n, (n%20000)+1, 1700000000 + n, "
    "       CASE WHEN (n%5)=0 THEN 'login' WHEN (n%5)=1 THEN 'purchase' WHEN (n%5)=2 THEN 'click' WHEN (n%5)=3 THEN 'view' ELSE 'logout' END, "
    "       json_object('n',n,'k', (n%7)) "
    "FROM t;"
  );
  exec_sql(db, "COMMIT;");

  exec_sql(db, "ANALYZE;");

  // workload queries (realistic patterns: feature flags OR-true/false, IN (SELECT DISTINCT), UNION LIMIT 1)
  const char *q1 = "SELECT event_id, ts FROM events WHERE user_id=?1 ORDER BY ts DESC LIMIT 50";
  const char *q2 = "SELECT count(*) FROM events WHERE kind='purchase' AND ts BETWEEN ?1 AND ?2";

  // Feature flag style: (flag.enabled OR condition)
  // Depending on parameterization, planner might simplify OR TRUE/FALSE
  const char *q3 =
    "SELECT e.event_id FROM events e "
    "JOIN flags f ON f.user_id=e.user_id "
    "WHERE (f.enabled OR ?1) AND e.kind='click' "
    "ORDER BY e.ts DESC LIMIT 100";

  // IN (SELECT DISTINCT ...)
  const char *q4 =
    "SELECT e.user_id, max(e.ts) "
    "FROM events e "
    "WHERE e.user_id IN (SELECT DISTINCT user_id FROM events WHERE kind='login') "
    "GROUP BY e.user_id LIMIT 100";

  // UNION LIMIT 1
  const char *q5 =
    "SELECT event_id FROM events WHERE kind='purchase' "
    "UNION "
    "SELECT event_id FROM events WHERE kind='logout' "
    "LIMIT 1";

  // Print EQP snapshots
  run_eqp(db, "SELECT event_id, ts FROM events WHERE user_id=123 ORDER BY ts DESC LIMIT 50");
  run_eqp(db, "SELECT count(*) FROM events WHERE kind='purchase' AND ts BETWEEN 1700100000 AND 1700200000");
  run_eqp(db, "SELECT e.event_id FROM events e JOIN flags f ON f.user_id=e.user_id WHERE (f.enabled OR 0) AND e.kind='click' ORDER BY e.ts DESC LIMIT 100");
  run_eqp(db, "SELECT e.user_id, max(e.ts) FROM events e WHERE e.user_id IN (SELECT DISTINCT user_id FROM events WHERE kind='login') GROUP BY e.user_id LIMIT 100");
  run_eqp(db, "SELECT event_id FROM events WHERE kind='purchase' UNION SELECT event_id FROM events WHERE kind='logout' LIMIT 1");

  // Benchmarks (bind parameters for the ones that matter)
  // For simplicity, we measure a few representative statements.
  bench_query(db, "SELECT event_id, ts FROM events WHERE user_id=123 ORDER BY ts DESC LIMIT 50", 200);
  bench_query(db, "SELECT count(*) FROM events WHERE kind='purchase' AND ts BETWEEN 1700100000 AND 1700200000", 500);
  bench_query(db, "SELECT e.event_id FROM events e JOIN flags f ON f.user_id=e.user_id WHERE (f.enabled OR 0) AND e.kind='click' ORDER BY e.ts DESC LIMIT 100", 200);
  bench_query(db, "SELECT e.user_id, max(e.ts) FROM events e WHERE e.user_id IN (SELECT DISTINCT user_id FROM events WHERE kind='login') GROUP BY e.user_id LIMIT 100", 100);
  bench_query(db, "SELECT event_id FROM events WHERE kind='purchase' UNION SELECT event_id FROM events WHERE kind='logout' LIMIT 1", 2000);

  sqlite3_close(db);
  return 0;
}
```

#### scripts/build_bench.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

OLD_PREFIX="$1"
NEW_PREFIX="$2"

mkdir -p /work/out

gcc -O2 -I"${OLD_PREFIX}/include" -L"${OLD_PREFIX}/lib" /work/bench/bench.c -lsqlite3 -o /work/out/bench_old

gcc -O2 -I"${NEW_PREFIX}/include" -L"${NEW_PREFIX}/lib" /work/bench/bench.c -lsqlite3 -o /work/out/bench_new

ldd /work/out/bench_old || true
ldd /work/out/bench_new || true
```

#### scripts/run_all.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

rm -f /work/out/test.db

echo "== OLD =="
/work/out/bench_old /work/out/test.db | tee /work/out/old.txt

rm -f /work/out/test.db

echo "== NEW =="
/work/out/bench_new /work/out/test.db | tee /work/out/new.txt

echo "== DIFF (EQP/BENCH lines) =="
# naive diff; in real CI, parse and normalize
(grep -E '^-- EQP|^[0-9]+\||^BENCH|^sqlite_version=' /work/out/old.txt) > /work/out/old.summary
(grep -E '^-- EQP|^[0-9]+\||^BENCH|^sqlite_version=' /work/out/new.txt) > /work/out/new.summary

diff -u /work/out/old.summary /work/out/new.summary || true
```

#### 예상 출력(요약)

- `sqlite_version=3.53.4` vs `sqlite_version=3.54.1`
- EQP detail 텍스트가 일부 달라질 수 있음
- `BENCH ... time_ms=...`가 크게 흔들리면(특히 q3/q4/q5 같은 플래너 민감 쿼리) 업그레이드 리뷰 포인트

이 구조의 장점은 단순합니다.

- 플랜(텍스트)과 시간(숫자)이 같이 남습니다.
- “왜 바뀌었는지”를 PR 리뷰에서 토론할 수 있습니다.
- SQLite를 직접 링크하므로, 언어 바인딩/ORM의 레이어를 걷어내고 엔진 차이를 먼저 볼 수 있습니다.

현실적인 운영에서는 여기서 한 단계 더 갑니다.

- 프로덕션 데이터 샘플(PII 제거)을 seed로 삼고, 서비스의 Top-N 느린 쿼리를 워크로드로 넣습니다.
- `ANALYZE` 결과(sqlite_stat1~)가 성능에 미치는 영향이 크면, 통계를 포함한 DB 스냅샷을 기준으로 삼습니다.
- 플랜은 바뀌어도 괜찮지만, p95 예산을 넘으면 자동 차단합니다.

내가 Terraform이나 Discourse처럼 “릴리스 주기가 빠른 것”을 운영할 때 결국 안정성을 만든 건 버전 고정이 아니라 반복 가능한 검증 파이프라인이었습니다. SQLite는 릴리스 주기가 상대적으로 짧지 않더라도, 다운스트림(모바일/데스크톱 번들)의 지연 때문에 한 번 터지면 파급이 커서 동일한 접근이 필요합니다.

- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)
- [Discourse 월간 릴리스에 맞춘 셀프호스팅 업그레이드 운영](https://daewooki.github.io/posts/discourse-monthly-release-selfhost-upgrade-automation/)

## 체크리스트 2: 확장 호환성 점검(FTS/JSON/loadable extension/암호화 래퍼)

SQLite는 “SQLite 코어 + 선택적 확장 + 빌드 옵션 + 플랫폼 정책”의 곱으로 기능이 결정됩니다. 업그레이드 실패의 대부분은 코어의 SQL 문법 호환이 아니라, 확장/옵션이 달라져서 발생합니다.

### JSON: 내 빌드에 JSON이 ‘있다고 가정’하면 깨진다

JSON 함수는 3.38.0부터 기본 포함(opt-out)이고, `-DSQLITE_OMIT_JSON`으로 제외할 수 있습니다. 즉, 어떤 환경에서는 JSON이 있고 어떤 환경에서는 빠질 수 있습니다.[^10]

업그레이드 체크는 단순한 smoke test로 시작합니다.

- `SELECT json_valid('{"a":1}');`
- `SELECT json_extract('{"a":2}', '$.a');`

여기서 중요한 건 “함수가 존재하는지” 뿐 아니라 “성능/인덱스 전략이 유지되는지”입니다. 예를 들어 JSON 경로를 expression index로 잡아 쓰는 서비스라면, 플래너 변경으로 인해 인덱스가 덜 쓰이거나 더 쓰이는 변화가 실제로 생깁니다(결과는 동일해도 latency가 달라짐). 3.54.0에는 expression index를 가진 테이블 UPDATE에서 “인덱싱되는 값이 안 바뀌면 expression index를 갱신하지 않는다”는 최적화가 들어갔습니다.[^3]

### FTS5: 빌드 플래그와 토크나이저/옵션이 제품 기능이다

FTS5는 amalgamation 소스 트리에는 포함되지만, 빌드 플로우에 따라 `SQLITE_ENABLE_FTS5`가 필요하거나 configure 옵션 `--enable-fts5`가 필요합니다.[^11]

FTS는 특히 “모바일/데스크톱/서버가 다른 SQLite를 쓰는 상황”에서 호환성의 중심이 됩니다.

- 서버는 FTS5 enabled인데, 모바일은 disabled면: 같은 DB 파일을 공유/이동하는 제품에서 재현 불가능한 장애가 나옵니다.
- 같은 FTS5라도 tokenizer(예: trigram, unicode61 옵션) 차이가 있으면 검색 결과가 달라집니다.

체크리스트는 아래를 포함해야 합니다.

- `CREATE VIRTUAL TABLE ... USING fts5(...)`가 성공하는가
- 기존 FTS 테이블을 `INSERT/UPDATE/DELETE`할 때 트리거/콘텐츠 옵션이 정상 동작하는가
- 검색 쿼리(`MATCH`)의 플랜이 바뀌었는가

이건 correctness 테스트로는 안 잡히고, 제품 워크로드로만 잡힙니다.

### loadable extension: 보안 정책/플랫폼 정책 때문에 “있을 수도, 없을 수도”가 된다

확장을 로드해서 쓰는 서비스(암호화 래퍼, 사용자 정의 함수, vector search, ICU 등)는 특히 조심해야 합니다.

- SQLite는 보안 이유로 extension loading이 기본적으로 꺼져 있고, `sqlite3_enable_load_extension()` 또는 `SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION`로 켜야 합니다.[^12]
- 아예 컴파일에서 extension loading 메커니즘을 제거하려면 `SQLITE_OMIT_LOAD_EXTENSION` 옵션을 씁니다.[^4]

즉, 업그레이드 체크는 “새 버전에서 확장 바이너리가 로드되는가”보다 먼저 “그 플랫폼/빌드에서 로딩 기능이 존재하는가”를 확인해야 합니다.

- 1차: `PRAGMA compile_options;`로 `OMIT_LOAD_EXTENSION` 유무 확인(단, introspection pragma를 빼면 이것도 못 봅니다)[^4]
- 2차: 실제 `load_extension()` 호출 smoke test
- 3차: 확장이 제공하는 SQL 함수들에 대한 단위 테스트

### 암호화 래퍼(SQLCipher 등): ‘같은 SQLite’가 아니다

암호화가 들어가면 얘기가 바뀝니다. SQLCipher는 SQLite의 포크로, “같은 major 버전 내에서는 포맷 호환을 유지한다”는 정책을 명시합니다.[^13]

이 말은 반대로 이렇게 읽어야 합니다.

- SQLCipher major가 다르면, 기본 설정 차이 때문에 그대로는 못 열 수 있다.[^13]
- “SQLite를 업그레이드한다”와 “SQLCipher를 업그레이드한다”는 별개의 작업이다.

게다가 SQLCipher는 업스트림 SQLite를 즉시 따라가지 않습니다. 예를 들어 SQLCipher changelog에는 baseline을 SQLite 3.53.4로 업데이트했다는 항목이 보입니다.[^14]

3.54.1이 나왔다고 해서 SQLCipher 기반 앱이 즉시 3.54.1로 올라갈 수 있다는 보장은 없습니다. 조직 내부에서 “서버는 vanilla SQLite 3.54.1, 모바일은 SQLCipher(업스트림 3.53.4 기반)” 같은 분리가 생기면, 동일 스키마/동일 쿼리의 성능 비교가 더 어려워집니다.

여기서 내가 선택하는 전략은 명확합니다.

- 암호화가 필요하면 ‘엔진 다양화’를 피할 수 없다고 보고, 아예 호환성 매트릭스를 문서화합니다.
- 파일 이동/동기화가 있는 제품이면, 포맷 호환(열 수 있음)과 기능 호환(FTS/JSON/함수 존재), 성능 호환(플랜/시간)을 분리해 체크합니다.

## 체크리스트 3: 모바일/데스크톱/서버 버전 동기화 전략

SQLite 업그레이드를 안전하게 만들려면, 먼저 “우리 서비스가 실제로 어떤 SQLite를 쓰는지”를 알아야 합니다. 체감상 많은 팀이 이 단계에서 멈춥니다.

### 1) 조직 내부 SQLite 인벤토리를 먼저 만든다

내가 권하는 인벤토리 단위는 ‘레포’가 아니라 ‘배포 단위’입니다.

- iOS 앱
- Android 앱
- Windows/macOS 데스크톱 앱
- 서버 API
- 배치/워커
- 분석/ETL 툴

각 배포 단위마다 아래를 수집합니다.

- `sqlite_version()` 결과
- `SQLITE_SOURCE_ID`(가능하면)
- 주요 compile options(FTS5/JSON/THREADSAFE/DBSTAT/OMIT_LOAD_EXTENSION 등)

업스트림은 changes 페이지에 각 릴리스의 `SQLITE_SOURCE_ID`를 함께 제공합니다.[^3]

### 2) “플랫폼이 주는 SQLite”를 그대로 받아먹지 말지 결정한다

Android는 문서에 “SQLite 버전은 Android 버전에 따라 다르다”고 못 박아둡니다.[^5]

이 말은 ‘프레임워크 SQLite’에 기대면 조직이 원하는 시점에 올릴 수 없다는 뜻입니다. 반대로 SQLite는 공식 다운로드 페이지에서 Android용 AAR(코어 + Java bindings)을 제공합니다. 즉, 원하면 앱이 SQLite를 직접 들고 갈 수 있습니다.[^9]

여기서 선택지는 크게 두 가지입니다.

- (A) OS/플랫폼 제공 SQLite를 사용: 앱 사이즈/운영 단순화는 좋지만, 버전 정렬은 포기해야 함.
- (B) 앱/제품에 SQLite를 번들: 버전 정렬과 기능 집합 통제가 가능하지만, 보안 패치/업데이트 책임이 제품 팀으로 내려옴.

나는 대개 “버전 정렬이 제품 요구사항이면 번들” 쪽으로 기웁니다. 다만 번들의 대가로 아래가 따라옵니다.

- crash/bug가 났을 때 디버그 심볼/빌드 플래그/패치 상태까지 제품이 책임진다.
- 모바일은 AB 테스트/점진 배포를 해도, 한 번 배포된 버전이 오래 남는다.

이 결정을 할 때 참고가 되는 신호는 “다운스트림의 업데이트 속도”입니다. Alpine edge가 3.54.1을 2026-10-17에 이미 빌드한 흔적은, 서버 쪽은 비교적 빨리 최신을 끌어올릴 수 있다는 단서입니다.[^6]

### 3) 버전 정렬의 목표를 ‘동일 버전’이 아니라 ‘동일한 검증 절차’로 잡는다

대규모 조직에서 iOS/Android/서버/데스크톱이 같은 날 같은 SQLite 버전을 쓰게 만드는 건 비용이 큽니다. 그래서 목표를 두 층으로 나눕니다.

- 1층: 각 플랫폼이 사용하는 SQLite는 달라도 된다.
- 2층: 어떤 버전을 쓰든, 업그레이드할 때 동일한 체크리스트와 자동화 파이프라인을 탄다.

이렇게 하면 “버전 정렬”이 아니라 “업그레이드 품질 정렬”이 됩니다. 업그레이드 리허설과 복구 전략을 먼저 설계해두면 실제 업그레이드는 빨라진다는 점에서, etcd 업그레이드 리허설 글의 결론과도 통합니다: [etcd v3.7.2 운영 리허설: 업그레이드·백업·복구·이미지 전략까지](https://daewooki.github.io/posts/etcd-372-kubernetes-ops-rehearsal/)

## 3.54.0/3.54.1 맥락에서 특히 조심할 변화 포인트

3.54.1 자체는 패치지만, 실제 업그레이드 검증은 3.54.0 변경을 함께 먹게 되는 경우가 많습니다(3.53.x에서 한 번에 올리는 시나리오).

### query planner 변화는 “플랜 스냅샷 + 성능 예산”으로만 안전해진다

3.54.0의 플래너 개선 항목은 전형적으로 제품 쿼리에서 자주 보이는 패턴을 건드립니다.

- feature flag/권한 체크 스타일의 OR 단순화: `expr OR TRUE/FALSE` 최적화[^3]
- `IN (SELECT DISTINCT ...)` 같은 서브쿼리의 불필요한 DISTINCT 무시[^3]
- `UNION ... LIMIT 1` 최적화[^3]

이건 성능이 “개선될 수도 있고, 기존에 우연히 빠르게 동작하던 경로가 바뀌면서 특정 데이터 분포에서 느려질 수도” 있습니다. 그래서 하네스에서 q3~q5 같은 쿼리를 일부러 넣었습니다.

### Windows 지원 범위 변화는 임베디드/레거시 환경에서 바로 폭발한다

3.54.0은 WindowsXP 이하 지원을 드롭하고, Windows에서는 Vista 이상을 요구한다고 명시합니다.[^3]

이 변경의 배경으로 “SRWL(Slim Reader/Writer Locks)을 사용해 mutex 구현을 바꿨다”는 설명이 있고, 포럼에서는 SRWL API 심볼 의존성 때문에 XP에서 프로세스 로딩 자체가 실패할 수 있다는 수준까지 구체적으로 언급합니다.[^15]

레거시 Windows 임베디드 장비(공장 장비, 의료 장비, 키오스크 등)에서 SQLite를 DLL로 링크하고 있다면, 업그레이드 검증의 첫 단계는 쿼리가 아니라 “실행 파일이 로드되는가”입니다.

### .diskused / diskused() 확장: 운영 도구 체인의 교체 비용

3.54.0에서 sqlite3_analyzer가 deprecated 되었고, CLI의 `.diskused` 명령과 `diskused()` 함수가 대체 수단으로 들어갔습니다.[^16]

여기서 포인트는 두 가지입니다.

- 운영자가 쓰던 분석 도구가 바뀐다(문서/가이드/스크립트 업데이트 필요).
- `diskused()`는 “별도 확장”이라서, 서드파티 애플리케이션이 쓰려면 따로 컴파일하고 `sqlite3_load_extension()`으로 로드해야 한다고 문서가 말합니다.[^17]

즉, CLI에서 잘 된다고 해서 라이브러리 내장 환경에서 그대로 될 거라 기대하면 깨집니다.

### SQLITE_LIMIT_SCHEMA / SQLITE_LIMIT_TRIGGER_STEPS: 방어적 설정을 쓰는 서비스는 영향 가능

3.54.0에서 런타임 제한 카테고리에 `SQLITE_LIMIT_SCHEMA`와 `SQLITE_LIMIT_TRIGGER_STEPS`가 추가되었습니다.[^3]

이 자체가 바로 호환성 이슈를 만든다기보다는, 보안/방어 목적(예: 사용자 제공 SQL 실행을 제한)으로 sqlite3_limit를 적극적으로 쓰는 서비스가 “새로 추가된 제한을 어떤 값으로 둘지” 정책 결정을 해야 한다는 의미입니다. limits 문서에도 3.54.0부터 schema object 개수를 cap 할 수 있다고 적혀 있습니다.[^18]

## 반론과 회의론: SQLite는 원래 호환성이 강한데, 이렇게까지 해야 하나

“SQLite는 파일 포맷도 잘 안 바뀌고, 대부분 업그레이드는 문제 없던데?”라는 말은 경험적으로도 절반은 맞습니다. 그런데 업그레이드 사고는 ‘평균적인’ 경로에서 잘 안 납니다.

- 특정 쿼리 + 특정 데이터 분포 + 특정 인덱스 + 특정 플래너 선택이 겹치는 지점에서 납니다.
- 특정 플랫폼(32-bit, 레거시 Windows, extension loading disabled)에서만 납니다.
- 확장(FTS/암호화/커스텀 함수)과 결합될 때 납니다.

그리고 3.54.1의 핵심이 “32-bit heap-buffer overflow 수정”이라는 사실은, “아직도 32-bit가 남아있는 곳이 있다”는 뜻이기도 합니다. 패치 릴리스가 가진 의미는 기능이 아니라 리스크 표면적입니다.[^3]

이런 류의 사고는 한 번 나면 비용이 큽니다. 특히 모바일은 버전 롤백이 기술적으로 가능하더라도 현실적으로 불가능한 경우가 많습니다(스토어 심사/배포 지연/사용자 업데이트 지연).

그래서 결론은 간단합니다.

- 업그레이드가 쉬운 게 아니라, 업그레이드를 쉽게 만들 파이프라인을 갖추면 쉬워집니다.

## 앞으로 지켜볼 것: 3.54.1 이후 다운스트림의 ‘따라오기’ 속도

3.54.1 릴리스 노트와 changes 페이지는 “3.54.0에서 보고된 다른 문제들을 추가로 수정했고, 자세한 건 check-in timeline을 보라”고만 말합니다.[^2]

이 상태에서 내가 보는 관전 포인트는 기술보다 운영입니다.

- 언어 런타임/드라이버가 언제 3.54.1을 번들하기 시작하는가
- 모바일 SDK(특히 OS 제공 SQLite에 의존하는 경우)가 언제 올라오는가
- 보안 스캐너/사내 정책이 “32-bit heap overflow 수정”을 어떤 심각도로 분류하는가

이 변화는 서비스의 계획을 뒤흔듭니다. 업그레이드를 분기별/반기별로 하던 팀도, 특정 CVE/이슈로 인해 일정이 당겨질 수 있습니다. 그때 필요한 건 ‘정보’보다 ‘절차’입니다.

## 정리: 업그레이드의 난이도는 SQLite가 아니라 제품 구조에서 나온다

SQLite 3.54.1은 패치 릴리스라서, 기능 변화만 보면 할 일이 없어 보입니다. 하지만 실제 서비스에서 SQLite는 단일 컴포넌트가 아니라, 빌드 옵션/확장/플랫폼 제공 라이브러리까지 포함한 조합입니다.

내가 3.54.1 타이밍을 업그레이드 윈도우로 보는 이유는 단순합니다.

- 최신 기준점이 생겼고(공식 Latest Release)[^1]
- 3.54.0에 플래너/플랫폼 변화가 들어왔고[^3]
- 3.54.1은 “32-bit에서 터질 수 있는 메모리 안전성 이슈”를 정리했습니다.[^19]

이 시점에 해야 할 일은 버전을 올리는 행위가 아니라, 다음 업그레이드에서도 그대로 재사용할 수 있는 검증 체크리스트와 자동화를 제품에 붙이는 일입니다.

## 참고 자료

- [SQLite Home: Latest Release 3.54.1(2026-10-16)](https://www2.sqlite.org/)
- [SQLite Release History: 3.54.1 / 3.54.0 변경 요약](https://sqlite.org/changes.html)
- [SQLite 3.54.1 Release Log](https://www.sqlite.org/releaselog/3_54_1.html)
- [SQLite Recent News: 3.54.1 패치 릴리스 설명](https://sqlite.org/news.html)
- [SQLite Download Page: 3.54.1 파일명 규칙과 배포 번들](https://www.sqlite.org/download.html)
- [sqllogictest: About](https://www.sqlite.org/sqllogictest/doc/trunk/about.wiki)
- [SQLite: Measuring and Reducing CPU Usage (speedtest1 언급)](https://www.sqlite.org/cpu.html)
- [SQLite JSON Functions And Operators (JSON 기본 포함/OMIT 옵션)](https://www.sqlite.org/json1.html)
- [SQLite FTS5 Extension (빌드/로드 방식)](https://www.sqlite.org/fts5.html)
- [SQLite Compile-time Options (FTS5/OMIT_LOAD_EXTENSION 등)](https://sqlite.org/compile.html)
- [SQLite Run-Time Loadable Extensions](https://www2.sqlite.org/loadext.html)
- [SQLCipher README: Compatibility](https://github.com/sqlcipher/sqlcipher)
- [SQLCipher CHANGELOG: upstream baseline 추적](https://github.com/sqlcipher/sqlcipher/blob/master/CHANGELOG.md)
- [Android frameworks/base: SQLite 버전은 Android 버전에 의존](https://android.googlesource.com/platform/frameworks/base/%2B/3bba35111e844fbc906255e2dead386a96520ae4/core/java/android/database/sqlite/package.html)
- [AOSP external/sqlite: 업그레이드 절차(버전 고정 맥락)](https://android.googlesource.com/platform/external/sqlite/%2Bshow/ee7586af94ee1270504b5aadc88cb09c49a03f5d/README-upgrade.md)
- [Alpine Linux packages: sqlite 3.54.1-r0 빌드 정보](https://pkgs.alpinelinux.org/packages?name=sqlite)
- [sqlite3_analyzer 문서: 3.54.0에서 deprecated, .diskused로 대체](https://www2.sqlite.org/draft/sqlanalyze.html)
- [SQLite CLI 문서: .diskused](https://www3.sqlite.org/cli.html)
- [SQLite diskused() extension 문서](https://www3.sqlite.org/diskusedfunc.html)
- [SQLite limits 문서: SQLITE_LIMIT_SCHEMA 언급](https://www.sqlite.org/limits.html)
- [SQLite 포럼: SRWL 전환과 Windows XP 지원 종료 영향](https://sqlite.org/forum/info/2f3abc1a9d346e4a779003d2e21204255bd7462c99396ffeee46025e22fe0f48)

[^1]: <https://www2.sqlite.org/>
[^2]: <https://www.sqlite.org/releaselog/3_54_1.html>
[^3]: <https://sqlite.org/changes.html>
[^4]: <https://www.sqlite.org/compile.html>
[^5]: <https://android.googlesource.com/platform/frameworks/base/%2B/3bba35111e844fbc906255e2dead386a96520ae4/core/java/android/database/sqlite/package.html>
[^6]: <https://pkgs.alpinelinux.org/packages?name=sqlite>
[^7]: <https://www.sqlite.org/cpu.html>
[^8]: <https://www.sqlite.org/sqllogictest/doc/trunk/about.wiki>
[^9]: <https://www.sqlite.org/download.html>
[^10]: <https://www.sqlite.org/json1.html>
[^11]: <https://www.sqlite.org/fts5.html>
[^12]: <https://www2.sqlite.org/loadext.html>
[^13]: <https://github.com/sqlcipher/sqlcipher>
[^14]: <https://github.com/sqlcipher/sqlcipher/blob/master/CHANGELOG.md>
[^15]: <https://sqlite.org/forum/info/2f3abc1a9d346e4a779003d2e21204255bd7462c99396ffeee46025e22fe0f48>
[^16]: <https://www2.sqlite.org/draft/sqlanalyze.html>
[^17]: <https://www3.sqlite.org/diskusedfunc.html>
[^18]: <https://www.sqlite.org/limits.html>
[^19]: <https://sqlite.org/news.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
