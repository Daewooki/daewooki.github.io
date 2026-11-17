---
title: "PostgreSQL 마이너 업그레이드: 확장·REINDEX·플랜 회귀 체크리스트"
description: "18.7/17.12/16.16/15.20/14.25 보안 릴리스에서 서버만 올리고 끝내면 깨지는 지점을 운영 절차로 재정리합니다."
date: 2026-11-17 15:51:05 +0900
categories: ["News", "Database"]
tags: ["postgresql", "minor-upgrade", "extensions", "reindex", "cve", "query-plans"]
render_with_liquid: false
---

## 2026-11-12 동시 릴리스가 던진 운영 전제

2026년 11월 12일에 PostgreSQL 18.7, 17.12, 16.16, 15.20, 14.25가 동시에 릴리스됐고, PostgreSQL 19 RC2도 함께 나왔습니다. 공식 발표문에도 이 묶음 릴리스가 같은 날 공개됐다는 점이 명시돼 있습니다. [PostgreSQL 18.7, 17.12, 16.16, 15.20, 14.25, and 19 RC 2 Released!](https://www.postgresql.org/about/news/postgresql-187-1712-1616-1520-1425-and-19-rc-2-released-3442/)

이번 타이밍이 운영 관점에서 더 불편한 이유는 두 가지가 겹쳐서입니다.

첫째, 릴리스 노트에 CVE 수정이 다수 포함돼 있습니다. 대표적으로 authenticated RCE 성격의 CVE-2026-6460가 이 릴리스 묶음에서 고쳐졌습니다. [CVE-2026-6460 보안 공지](https://www.postgresql.org/support/security/CVE-2026-6460/)를 읽어보면 공격 표면이 단순히 네트워크 입력 검증 같은 문제가 아니라, DDL과 타입/캐시/값 추적 같은 코어 내부 동작에 걸려 있습니다.

둘째, 14.25는 14 메이저 라인의 마지막 릴리스입니다. PostgreSQL은 메이저 버전을 최초 릴리스 후 5년 지원하고, 이후 최종 마이너 릴리스를 내고 EOL로 전환한다는 정책을 갖고 있습니다. [Versioning Policy](https://www.postgresql.org/support/versioning/)에 그대로 나옵니다. 즉, 14를 아직 운영 중이라면 14.25 적용 자체가 끝이 아니라, 메이저 업그레이드로 넘어가는 로드맵을 확정해야 하는 전환점입니다.

오늘은 2026-11-17 KST 기준으로, 이 동시 릴리스 묶음을 계기로 **마이너 업그레이드=서버 바이너리만 패치**라는 운영 습관을 재점검해 보려고 합니다. 특히 “서버만 올리고 끝내면 실제로 어디서 깨지는가”를 확장, REINDEX, 쿼리 플랜 회귀 관점으로 정리하고, 마이너 릴리스 윈도우를 운영 이벤트로 만드는 체크리스트를 남깁니다.

## ‘서버만 올리고 끝’이 깨지는 세 가지 축

마이너 릴리스는 원칙적으로 “dump/restore나 pg_upgrade 없이 바이너리 교체 + 재시작”으로 충분하다고 안내됩니다(이번 발표문에도 같은 톤이 있습니다). 다만 운영에서 체감되는 리스크는 다른 차원에 있습니다.

1) 확장(extensions)
- 서버는 패치됐는데 extension 패키지(특히 third-party C extension)는 그대로인 상태가 흔합니다.
- extension은 “바이너리(.so)”와 “SQL 오브젝트(함수/타입/연산자/캐스트/인덱스 메서드/오퍼레이터 클래스 등)”가 분리돼 있고, 둘의 업데이트 경로도 분리됩니다.
- 이번 릴리스는 extension 스크립트/치환(substitution)과 관련된 보안 이슈가 포함돼 있어, extension을 운영 절차에서 제외하면 취약점을 그대로 끌고 갈 가능성이 커집니다.

2) REINDEX(및 인덱스 무결성)
- 이번 릴리스 노트는 여러 버전 라인에서 “인덱스 손상 가능성이 있었으니 REINDEX 언급 항목을 확인하라”를 명시합니다(15.20/16.16/17.12/14.25/18.7 모두 같은 유형의 문구가 보입니다). 예를 들어 [PostgreSQL 15.20 릴리스 노트](https://www.postgresql.org/docs/15/release-15-20.html)에도 “REINDEX 언급 항목을 확인하라”가 마이그레이션 섹션에 들어가 있습니다.
- 버그가 수정됐다고 해서 이미 손상된 인덱스가 자동 복구되지는 않습니다. 이걸 구분 못 하면 “패치했는데도 여전히 간헐적으로 wrong result / missing row / internal error”가 나옵니다.

3) 쿼리 플랜(성능/정확성 회귀)
- 릴리스 노트에 planner 관련 수정이 포함되면, 플랜이 바뀌는 건 자연스럽습니다.
- “플랜 변경은 성능 문제”로만 보는 경우가 많은데, 이번 릴리스 노트에는 “wrong answers” 수준의 설명이 섞여 있습니다. 예를 들어 14.25/15.20/16.16/18.7 계열 노트에는 lateral reference나 PlaceHolderVar, join planning 계열의 버그 수정이 다수 포함돼 있고(14.25/15.20의 planner bug fix 항목을 보면 톤이 강합니다), 17.12는 join removal 구현 자체를 parse tree 기반으로 바꿨다고 설명합니다. [PostgreSQL 17.12 릴리스 노트](https://www.postgresql.org/docs/17/release-17-12.html)

이 세 축은 서로 연결돼 있습니다. extension 업데이트가 미묘하게 실패하면(권한/치환/스키마/오브젝트 이름 규칙 강화 등), 그 extension이 제공하는 오퍼레이터 클래스나 함수가 깨지고, 그 결과 플랜이 바뀌거나 쿼리가 에러로 터집니다. 인덱스 손상이 남아 있으면 플랜이 “정상”이어도 결과가 빠집니다.

## 확장: 바이너리 업데이트와 ALTER EXTENSION UPDATE는 별개입니다

PostgreSQL에서 extension은 크게 두 레이어입니다.

- OS/이미지 레벨(파일 시스템): `$libdir` 아래의 공유 라이브러리(.so), extension control 파일(.control), extension SQL 파일들
- DB 카탈로그 레벨: `pg_extension`, `pg_proc`, `pg_type`, `pg_operator`, `pg_opclass` 등

운영에서 자주 나오는 실패 모드는 이렇습니다.

- 서버 패키지(`postgresql-16` 같은 것)만 업데이트
- extension 패키지(`postgresql-16-postgis-3`, `postgresql-16-pgvector`, `postgresql-16-pg_cron` 같은 것)를 업데이트하지 않음
- 또는 파일은 업데이트됐는데 DB 안의 SQL 오브젝트는 옛 버전 그대로(`ALTER EXTENSION ... UPDATE`를 안 함)

이 상태는 “재시작은 된다”는 점이 함정입니다. 재시작이 된다고 해서 extension이 기대하는 SQL 오브젝트/권한/버전이 일치한다는 보장은 없습니다.

### 이번 릴리스에서 extension이 운영 절차에 들어와야 하는 이유

이번 릴리스에는 extension 설치/업데이트 스크립트를 둘러싼 보안 이슈가 포함돼 있습니다.

- extension script substitutions를 통한 SQL injection을 더 강하게 차단하는 수정(CVE-2026-120153)이 들어갔습니다. [CVE-2026-120153 보안 공지](https://www.postgresql.org/support/security/CVE-2026-120153/)와 [PostgreSQL 18.7 릴리스 노트](https://www.postgresql.org/docs/18/release-18-7.html) / [PostgreSQL 17.12 릴리스 노트](https://www.postgresql.org/docs/17/release-17-12.html)에도 직접 연결됩니다.
- `CREATE EXTENSION` 경로에서 스키마 rename/temporary schema 악용으로 newly-installed extension을 손상시키는 공격(CVE-2026-6467)도 같은 묶음 릴리스에 들어가 있습니다. 이건 “확장은 편의 기능”이 아니라 “DDL + 보안 경계”라는 현실을 다시 상기시킵니다. [PostgreSQL 18.7 릴리스 노트](https://www.postgresql.org/docs/18/release-18-7.html)

즉, 이번 릴리스는 “서버만 올리면 CVE 끝”이 아니라, extension 설치/업데이트가 포함된 DDL 표면 자체를 손보는 성격입니다. 운영 절차에서 extension을 빼면, 서버 패치 이후에도 조직 내부의 권한 모델(예: 앱 롤이 CREATE를 갖고 있는지, 내부 툴이 임시 스키마를 쓰는지)에 따라 “CVE가 닫히지 않거나”, “이전과 달리 설치/업데이트가 실패하는” 양쪽 가능성이 동시에 생깁니다.

### third-party extension은 별도 릴리스 리듬을 갖습니다: pgvector 사례

여기에 third-party extension은 코어 PostgreSQL과 릴리스 리듬이 다릅니다. 이번 기간에 같은 News Archive 피드에 올라온 예로 pgvector 0.8.7 릴리스가 있습니다. PostgreSQL News Archive(2026-10-05)에 따르면 pgvector 0.8.7은 IVFFlat index build에서의 buffer overflow(CVE-2026-103484)를 수정합니다. [pgvector 0.8.7 Released](https://www.postgresql.org/about/news/pgvector-087-released-3392/)

원문 이슈도 “IVFFlat 인덱스를 만들 수 있는 DB 유저”가 out-of-bounds write로 RCE까지 갈 수 있다고 명시합니다. [Buffer overflow with IVFFlat index build (pgvector #1036)](https://github.com/pgvector/pgvector/issues/1036)

이 조합이 왜 운영에서 위험하냐면, 실제로는 이런 시나리오가 가능합니다.

- PostgreSQL을 18.7로 올리면서 코어 CVE(예: CVE-2026-6460)는 막았다고 생각함
- 그런데 pgvector는 그대로 0.8.6 이하로 남아 있음
- 결과적으로 “PostgreSQL은 패치됨” 상태인데도, 실제 공격 표면은 여전히 열려 있음

내 경우 AI 프로토타이핑 환경에서는 vector extension을 금방 붙이는 편이라, 이 케이스를 단순히 보안 공지로만 보기가 어렵습니다. 마이너 업그레이드를 운영 이벤트로 다루는 이유가 여기서도 나옵니다.

### ALTER EXTENSION UPDATE가 해주는 것과 못 해주는 것

`ALTER EXTENSION ... UPDATE`는 DB 카탈로그 레벨의 SQL 오브젝트를 업데이트합니다. 문서에도 “extension이 적절한 update script를 제공하면 UPDATE가 가능하다”고 설명돼 있습니다. [ALTER EXTENSION 문서](https://www.postgresql.org/docs/current/sql-alterextension.html)

반대로, `ALTER EXTENSION`은 OS 패키지를 업데이트하지 못합니다. 즉 순서는 보통 이렇게 잡아야 합니다.

1) OS/이미지에서 extension 패키지 업데이트(= 파일 업데이트)
2) DB에서 `ALTER EXTENSION ... UPDATE`(= 카탈로그 오브젝트 업데이트)

이 순서가 뒤집히면 `ALTER EXTENSION`이 “새 버전 파일을 못 찾아서” 실패하거나, 더 미묘하게는 “default_version이 예전으로 보이는 상태”로 남습니다.

## REINDEX: 버그 수정과 데이터 구조 복구는 다른 단계입니다

이번 릴리스 묶음에서 눈에 띄는 문구는 반복됩니다.

- “A dump/restore is not required… However… could result in index corruption… mention REINDEX…”

이건 운영자가 “패치=끝”으로 처리하면 안 된다는 힌트에 가깝습니다. 대표적으로 다음 이슈들이 눈에 띕니다.

### 1) REINDEX CONCURRENTLY + TOAST 인덱스 업데이트 누락 → missing chunk number

18.7/17.12/16.16/15.20/14.25 릴리스 노트에는 공통으로 TOAST-table index와 `REINDEX CONCURRENTLY` 조합에서 relation cache가 기대하지 못한 상태가 생겨 index update가 누락될 수 있고, 그 결과 `missing chunk number` 에러가 날 수 있었다는 설명이 나옵니다. 예를 들어 [PostgreSQL 18.7 릴리스 노트](https://www.postgresql.org/docs/18/release-18-7.html)와 [PostgreSQL 14.25 릴리스 노트](https://www.postgresql.org/docs/14/release-14-25.html)에 동일한 계열 설명이 들어가 있습니다.

중요한 포인트는 두 가지입니다.

- TOAST 테이블 자체는 괜찮을 수 있고, 인덱스만 손상됐을 수 있음(= REINDEX로 복구 가능)
- “이미 손상된 인덱스”는 패치 후에도 그대로 남음

이건 패치 이후에도 갑자기 터질 수 있습니다. 특히 `REINDEX TABLE CONCURRENTLY`를 습관적으로 쓰는 팀일수록, “그때는 조용했는데 몇 주 후 특정 업데이트 경로에서 missing chunk number”가 등장하는 식으로 나오기 쉽습니다.

### 2) pg_trgm GiST 인덱스(gist_trgm_ops) 손상 가능 → REINDEX 필요

17.12/16.16/15.20/14.25 릴리스 노트에는 `contrib/pg_trgm`의 GiST 인덱스에서 특정 조합 시 검색이 매칭 행을 놓칠 수 있고, 기존 인덱스는 자동으로 고쳐지지 않으니 `REINDEX`가 필요하다는 설명이 들어갑니다. [PostgreSQL 16.16 릴리스 노트](https://www.postgresql.org/docs/16/release-16-16.html), [PostgreSQL 17.12 릴리스 노트](https://www.postgresql.org/docs/17/release-17-12.html), [PostgreSQL 15.20 릴리스 노트](https://www.postgresql.org/docs/15/release-15-20.html)

내 경험상 pg_trgm은 “검색 기능 붙이기”에서 생각보다 쉽게 도입됩니다. 그리고 운영에서 제일 무서운 장애는 “검색 결과가 조용히 빠지는 장애”입니다. 에러 로그도 없고, SLA도 바로 안 깨지고, 고객 신뢰만 잠식합니다.

### 3) planner bug fix는 성능 문제가 아니라 정확성 문제로 이어질 수 있음

14.25와 15.20 릴리스 노트에는 lateral reference/PlaceHolderVar 등 플래너 계열 수정이 있고, “wrong answers” 또는 내부 에러까지 언급합니다. 이건 REINDEX와 직접 연결되진 않지만, 업그레이드 윈도우에서 “정확성 검증” 체크리스트가 꼭 필요하다는 근거로 충분합니다. [PostgreSQL 14.25 릴리스 노트](https://www.postgresql.org/docs/14/release-14-25.html), [PostgreSQL 15.20 릴리스 노트](https://www.postgresql.org/docs/15/release-15-20.html)

## 확장/인덱스를 운영 절차에 끼워 넣는 실전 점검 SQL

여기부터는 내 쪽에서 실제로 운영 점검에 넣는 형태로 정리한 스크립트입니다. 핵심은 “업그레이드 전/후에 같은 스크립트를 돌려서 차이를 남긴다”입니다. 스냅샷이 없으면 회고도 없고, 다음 윈도우가 더 빨라지지도 않습니다.

아래 예시는 `psql` 기준입니다.

### 1) 설치된 extension과 버전, 업데이트 필요 여부

```sql
-- 파일: 10_extensions_audit.sql
\pset pager off
\x on

SELECT
  now() AS captured_at,
  version() AS server_version;

SELECT
  extname,
  extversion
FROM pg_extension
ORDER BY 1;

-- default_version과 installed extversion 비교
SELECT
  e.extname,
  e.extversion AS installed_extversion,
  a.default_version AS file_default_version
FROM pg_extension e
JOIN pg_available_extensions a
  ON a.name = e.extname
WHERE e.extname NOT IN ('plpgsql')
  AND e.extversion IS DISTINCT FROM a.default_version
ORDER BY 1;
```

실행:

```bash
psql "$DATABASE_URL" -f 10_extensions_audit.sql
```

예상 출력(형태 예시):

```text
captured_at            | 2026-11-17 12:34:56.789+09
server_version         | PostgreSQL 18.7 ...

extname                | extversion
----------------------+----------
pg_trgm                | 1.6
amcheck                | 1.4
pg_stat_statements     | 1.11
...

extname                | installed_extversion | file_default_version
----------------------+----------------------+---------------------
pg_stat_statements     | 1.10                 | 1.11
```

이 결과가 중요한 이유는, “서버 패치만 했다” 상태에서 흔히 `file_default_version`이 이미 바뀌어 있는데 `installed_extversion`이 그대로인 경우가 나오기 때문입니다. 이건 거의 항상 `ALTER EXTENSION UPDATE` 누락입니다.

### 2) extension을 일괄 업데이트(실패를 로그로 남기는 방식)

`ALTER EXTENSION`은 실패할 수 있습니다. update script가 없는 extension도 있고, 권한/오브젝트 상태 때문에 막히는 경우도 있습니다. 그래서 나는 “그냥 DO 블록으로 돌려서 다 올린다”를 기본으로 하지 않고, 대상 리스트를 만든 뒤 순차 실행 + 로그를 선호합니다.

```bash
# 파일: 20_alter_extension_update.sh
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"

psql "$DATABASE_URL" -Atc "
SELECT format('ALTER EXTENSION %I UPDATE;', extname)
FROM pg_extension
WHERE extname NOT IN ('plpgsql')
ORDER BY 1;" \
| while read -r stmt; do
    echo "==> $stmt";
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "$stmt";
  done
```

예상 출력(형태 예시):

```text
==> ALTER EXTENSION amcheck UPDATE;
ALTER EXTENSION
==> ALTER EXTENSION pg_stat_statements UPDATE;
ALTER EXTENSION
...
```

여기서 실패하면 실패 자체가 운영 이벤트의 일부입니다. 실패하는 extension이 “업그레이드 윈도우의 블로커인지”, “기능 미사용이라 제거 가능한지”, “다음 윈도우까지 위험을 감수할지”를 의사결정해야 합니다.

문서적으로 `ALTER EXTENSION UPDATE` 동작은 [extension 업데이트 관련 문서](https://www.postgresql.org/docs/current/extend-extensions.html)와 [ALTER EXTENSION 문서](https://www.postgresql.org/docs/current/sql-alterextension.html)를 기준으로 보는 게 안전합니다.

### 3) pg_trgm GiST(gist_trgm_ops) 인덱스 존재 여부 확인

```sql
-- 파일: 30_indexes_trgm_gist.sql
\pset pager off
\x on

SELECT
  n.nspname AS index_schema,
  c.relname AS index_name,
  tn.nspname AS table_schema,
  t.relname AS table_name
FROM pg_class c
JOIN pg_index i ON i.indexrelid = c.oid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_namespace tn ON tn.oid = t.relnamespace
JOIN pg_opclass oc ON oc.oid = ANY(i.indclass)
WHERE oc.opcname = 'gist_trgm_ops'
ORDER BY 1, 2;
```

이 쿼리는 “이번 릴리스 묶음에서 REINDEX를 요구한 유형의 인덱스를 운영 DB가 실제로 쓰고 있나”를 빠르게 확인합니다. 관련 근거는 각 버전의 릴리스 노트에 “기존 인덱스는 고쳐지지 않으니 REINDEX”가 명시된 부분입니다. [PostgreSQL 17.12 릴리스 노트](https://www.postgresql.org/docs/17/release-17-12.html), [PostgreSQL 16.16 릴리스 노트](https://www.postgresql.org/docs/16/release-16-16.html)

### 4) REINDEX를 실제로 실행할 때의 원칙

`REINDEX`는 CPU/IO/디스크를 동시에 갈아 넣는 작업입니다. `CONCURRENTLY`를 붙이면 락 영향은 줄지만, 전체 소요시간/리소스 사용량/실패 시 재시도 복잡도가 올라갑니다. 문서에 동작과 제약이 정리돼 있습니다. [REINDEX 문서](https://www.postgresql.org/docs/18/sql-reindex.html)

내가 마이너 업그레이드 윈도우에서 REINDEX를 다루는 방식은 이렇습니다.

- “전량 REINDEX”는 기본값이 아닙니다. 릴리스 노트가 특정한 범위(예: gist_trgm_ops)로 좁혀주는 경우가 많습니다.
- 다만 TOAST/missing chunk number 계열은 “증상이 있었으면 반드시”로 둡니다. 릴리스 노트 자체가 그 톤입니다. [PostgreSQL 18.7 릴리스 노트](https://www.postgresql.org/docs/18/release-18-7.html)
- REINDEX를 실행하기 전에, 먼저 인덱스 점검(amcheck)을 태울 수 있는 환경이면 태웁니다. btree 계열은 특히 그렇습니다. [amcheck 문서](https://www.postgresql.org/docs/18/amcheck.html)

REINDEX 실행 SQL 생성 예시(위 30_indexes_trgm_gist.sql 결과를 기반으로):

```sql
-- 파일: 40_reindex_trgm_gist_generate.sql
\pset pager off
\pset tuples_only on

SELECT
  format(
    'REINDEX INDEX CONCURRENTLY %I.%I;',
    n.nspname,
    c.relname
  )
FROM pg_class c
JOIN pg_index i ON i.indexrelid = c.oid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_opclass oc ON oc.oid = ANY(i.indclass)
WHERE oc.opcname = 'gist_trgm_ops'
ORDER BY 1;
```

실행:

```bash
psql "$DATABASE_URL" -f 40_reindex_trgm_gist_generate.sql \
  | tee reindex_trgm.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f reindex_trgm.sql
```

이 방식의 장점은 “실제로 무엇을 REINDEX 했는지”가 파일로 남는다는 점입니다. 운영 사고는 늘 “기억”에서 시작해서 “기록 부재”로 커집니다.

## 쿼리 플랜 회귀: 릴리스 노트가 ‘정확성/내부 에러’까지 말하는 구간

플랜 회귀를 성능 관점으로만 보면 업그레이드 리허설이 얇아집니다. 이번 릴리스 노트에서 플래너/실행기 관련 수정은 “내부 에러”나 “wrong answers” 같은 표현을 동반합니다. [PostgreSQL 14.25 릴리스 노트](https://www.postgresql.org/docs/14/release-14-25.html), [PostgreSQL 15.20 릴리스 노트](https://www.postgresql.org/docs/15/release-15-20.html)

그리고 17.12 릴리스 노트에는 join removal을 기존의 fragile한 방식에서 parse tree 기반으로 교체했다고 설명합니다. 이건 결과적으로 플랜이 바뀌는 게 정상입니다. [PostgreSQL 17.12 릴리스 노트](https://www.postgresql.org/docs/17/release-17-12.html)

플랜이 바뀐다고 해서 다 문제가 되는 건 아닙니다. 문제는 “바뀐 걸 모르고 지나가는 것”입니다. 그래서 나는 업그레이드 윈도우에서 다음 두 가지를 최소 단위로 둡니다.

- top-N 쿼리(보통 pg_stat_statements 기준) 재실행 + latency 비교
- 동일 쿼리에 대한 EXPLAIN(JSON) 스냅샷 비교

내 블로그에서 RC 테스트 윈도우를 따로 운영 이벤트로 설계했던 이유도 결국은 같은 결입니다. [PostgreSQL 19 RC 기간 확장에 맞춘 테스트 윈도우 재설계](https://daewooki.github.io/posts/postgresql-19-rc-window-redesign/)

### EXPLAIN(JSON) 스냅샷을 남기는 파이썬 스크립트

이건 “업그레이드 전” 한 번, “업그레이드 후” 한 번 돌려서 JSON 파일을 만들고 diff하는 방식입니다. 장난감처럼 보일 수 있는데, 실제 운영에서 가장 유용한 건 “다음에 같은 방법으로 반복 가능하냐”입니다.

의존성(버전 범위로 고정):

```bash
python -m venv .venv
. .venv/bin/activate
pip install "psycopg[binary]>=3.2,<3.3"
```

쿼리 파일 구성:

```text
plan-audit/
  queries/
    001_hot_path.sql
    010_batch_job.sql
  capture_plans.py
```

`queries/001_hot_path.sql` 예시(실제 서비스 쿼리를 넣는 자리):

```sql
/* name: hot_path */
SELECT /* your real query here */ 1;
```

`capture_plans.py`:

```python
import json
import os
import pathlib
from datetime import datetime, timezone

import psycopg

DATABASE_URL = os.environ["DATABASE_URL"]
QUERIES_DIR = pathlib.Path(__file__).parent / "queries"
OUT = pathlib.Path(__file__).parent / "plans.json"

def read_queries():
    items = []
    for p in sorted(QUERIES_DIR.glob("*.sql")):
        sql = p.read_text(encoding="utf-8")
        items.append({"file": p.name, "sql": sql})
    return items

def main():
    captured_at = datetime.now(timezone.utc).isoformat()

    with psycopg.connect(DATABASE_URL) as conn:
        conn.autocommit = True

        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            server_version = cur.fetchone()[0]

        results = {
            "captured_at": captured_at,
            "server_version": server_version,
            "items": [],
        }

        for q in read_queries():
            explain_sql = "EXPLAIN (FORMAT JSON, SETTINGS, VERBOSE) " + q["sql"]
            with conn.cursor() as cur:
                cur.execute(explain_sql)
                plan = cur.fetchone()[0]  # a JSON value

            results["items"].append(
                {
                    "file": q["file"],
                    "plan": plan,
                }
            )

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"server_version={results['server_version']}")
    print(f"queries={len(results['items'])}")

if __name__ == "__main__":
    main()
```

실행:

```bash
export DATABASE_URL='postgresql://...'
python capture_plans.py
```

예상 출력:

```text
wrote plans.json
server_version=PostgreSQL 18.7 ...
queries=2
```

이 결과물을 업그레이드 전/후로 남기면, 플랜이 바뀐 쿼리를 “느낌”이 아니라 파일 diff로 찾을 수 있습니다. 플랜이 바뀌었다고 무조건 되돌릴 이유는 없지만, 바뀐 사실을 모른 채로 지나가면 장애가 났을 때 원인 규명이 늦어집니다.

## 보안 릴리스에서 ‘확장 포함’ 원칙을 더 강하게 적용해야 하는 이유

이번 릴리스 묶음은 CVE 숫자 자체가 많습니다. 나는 “CVE가 많다”는 사실 자체로 공포 마케팅을 하진 않지만, 운영 절차를 바꾸게 만드는 유형의 CVE는 별개로 봅니다.

### CVE-2026-6460: DDL/타입 경계에서의 RCE는 운영 모델을 찌릅니다

CVE-2026-6460는 “ALTER ... SET DATA TYPE 등”을 통해 type confusion으로 OS 유저 권한에서 arbitrary code execution이 가능하다고 설명합니다. 즉, 공격의 핵심은 네트워크 입력이 아니라 DB 내부 오브젝트 생성/변경 권한입니다. [CVE-2026-6460 보안 공지](https://www.postgresql.org/support/security/CVE-2026-6460/)

여기서 자주 나오는 현실적인 구멍은 이렇습니다.

- 멀티테넌트가 아니더라도, 내부 툴/배치/마이그레이션 롤에 CREATE/DDL 권한을 넓게 주는 경우
- “개발 편의”로 staging과 prod의 권한 모델이 달라지고, 그 차이가 운영자가 통제하는 범위를 넘어가는 경우

이런 환경에서는 “서버만 패치”가 아니라 “권한/DDL 경로 점검 + 확장 설치/업데이트 절차 고정”이 함께 가야 합니다.

### CVE-2026-120153: extension update/install 스크립트는 공격 표면입니다

CVE-2026-120153은 extension-script substitutions에서 object name을 통한 SQL injection 가능성을 다룹니다. CREATE 권한이 있는 공격자가 schema/owner name의 특수 문자열로 bootstrap superuser로 arbitrary code execution까지 이어질 수 있다고 설명합니다. [CVE-2026-120153 보안 공지](https://www.postgresql.org/support/security/CVE-2026-120153/)

이건 운영팀이 “확장은 DBA만 설치하니까 괜찮다”고 생각하는 순간 위험해집니다.

- CI/CD나 migration tool이 extension을 만지는 경우
- 템플릿 DB/프로비저닝 자동화에서 extension 설치를 수행하는 경우
- 여러 앱이 한 클러스터를 공유하면서 role 정책이 일관되지 않은 경우

이런 경우에는 마이너 업그레이드 윈도우가 곧 “권한 경계 재검증 이벤트”입니다.

### CVE-2026-120144 같은 코어 내부 수정은 ‘패치지만 동작이 바뀔 수 있다’ 쪽에 가깝습니다

이번 릴리스에는 type cache 관련 보안 수정(CVE-2026-120144)도 포함됩니다. [CVE-2026-120144 보안 공지](https://www.postgresql.org/support/security/CVE-2026-120144/)를 보면 “type-cache invalidation” 같은 내부 동작이 직접 언급됩니다. 이런 종류는 운영에서 “패치=무조건 안전”이라기보다, “패치=정확성/안정성은 올라가지만, 특정 워크로드에서는 부작용이 있을 수 있음”으로 분류하는 게 맞습니다.

이건 결국 플랜 리허설/회귀 테스트의 필요성을 강화합니다.

## ‘마이너 릴리스 윈도우’를 운영 이벤트로 만드는 체크리스트

체크리스트는 길수록 좋지만, 길기만 하면 아무도 실행하지 않습니다. 나는 단계별로 “산출물”이 남게 만들고, 그 산출물이 다음 윈도우의 입력이 되게 만드는 쪽을 선호합니다. 예전에 Terraform 업그레이드를 다루면서도 “버전 고정만으로는 부족하다”를 같은 맥락에서 정리한 적이 있습니다. [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)

아래는 이번 PostgreSQL 18.7 / 17.12 / 16.16 / 15.20 / 14.25 계열에 맞춰 내가 다시 다듬은 버전입니다.

### T-7일: 범위 확정과 위험 분류

- 릴리스 노트에서 “Updating / Migration” 섹션을 먼저 읽고, REINDEX 요구 여부를 체크합니다.
  - 18.7: [PostgreSQL 18.7 릴리스 노트](https://www.postgresql.org/docs/18/release-18-7.html)
  - 17.12: [PostgreSQL 17.12 릴리스 노트](https://www.postgresql.org/docs/17/release-17-12.html)
  - 16.16: [PostgreSQL 16.16 릴리스 노트](https://www.postgresql.org/docs/16/release-16-16.html)
  - 15.20: [PostgreSQL 15.20 릴리스 노트](https://www.postgresql.org/docs/15/release-15-20.html)
  - 14.25: [PostgreSQL 14.25 릴리스 노트](https://www.postgresql.org/docs/14/release-14-25.html)
- 적용 대상 클러스터 목록을 고정합니다. “나중에 하나 더”가 들어오는 순간 운영 이벤트가 무너집니다.
- 14 계열은 “이번이 마지막”이라는 사실을 운영 계획에 반영합니다. 공식 지원 종료 정책은 [Versioning Policy](https://www.postgresql.org/support/versioning/)가 기준입니다.

산출물
- 클러스터별: 현재 서버 버전/OS 패키지/확장 목록/인덱스 위험 목록/롤백 방법 문서

### T-2일: staging 리허설(서버+확장+REINDEX+플랜)

- prod 스냅샷을 staging에 복원(가능하면 동일한 데이터 볼륨/통계 상태)
- 서버 패치 적용 + 재시작
- 확장 패키지 업데이트 + `ALTER EXTENSION ... UPDATE` 수행
- 릴리스 노트에서 언급된 인덱스 유형에 대해 REINDEX 리허설
- EXPLAIN(JSON) 스냅샷을 남기고, top-N 쿼리를 재실행해서 latency 비교

산출물
- extension update 성공/실패 로그
- REINDEX 실행 목록과 소요시간
- 플랜 스냅샷(before/after) 및 바뀐 쿼리 리스트

### T(점검 윈도우): 실행 순서 고정

나는 마이너 업그레이드 윈도우에서 순서를 고정합니다.

1) 사전 상태 캡처
- extension audit SQL 실행
- `pg_settings` diff를 원하면 설정도 덤프

2) 서버 바이너리/패키지 업데이트 + 재시작
- 여기서 서비스가 올라오는지만 보면 안 됩니다. “올라온 다음의 후속 작업”이 핵심입니다.

3) 확장 업데이트
- OS 패키지 업데이트(컨테이너라면 이미지에 포함)
- `ALTER EXTENSION UPDATE` 수행

4) 인덱스 복구 작업
- 릴리스 노트 범위에 해당하는 인덱스부터
- `CONCURRENTLY` 여부는 트래픽/락 민감도에 맞춰 결정

5) 플랜/성능/정확성 스모크
- top-N 쿼리 실행
- EXPLAIN 스냅샷 재캡처

산출물
- 업그레이드 타임라인(시각별)
- 실패 시점과 롤백 결정 근거

### T+1시간: 안정화 관측

- 에러 로그에서 `missing chunk number` 같은 시그널 검색(TOAST 인덱스 계열)
- replication 지연, autovacuum backlog, 체크포인트/IO 스파이크 관측
- extension 관련 에러(함수 없음, 심볼 로드 실패, permission denied) 관측

산출물
- 관측 대시보드 스냅샷
- 주요 에러/경고 카운트

### T+24시간: “다음 윈도우”를 위한 회고 데이터 정리

- staging 리허설과 실제 prod 수행의 차이를 정리
- REINDEX 소요시간/영향을 다음에 반영
- 바뀐 플랜 중에서 성능에 영향을 준 쿼리만 추려서 튜닝 backlog에 넣기

산출물
- 체크리스트 업데이트 PR(문서라도)

## 이번 동시 릴리스에서 내가 다시 세운 원칙

- 마이너 릴리스는 “기술적으로는 바이너리 교체”가 맞지만, 운영 이벤트로는 **확장과 인덱스 복구를 포함한 변경**입니다.
- 릴리스 노트에 REINDEX가 언급된 순간부터는, “업데이트”가 아니라 “복구”까지 끝내야 패치가 완료됐다고 보는 게 맞습니다.
- 플랜 회귀는 성능 사건이기도 하지만, 이번 릴리스 노트 톤을 보면 정확성/내부 에러 관점에서도 다뤄야 합니다.
- third-party extension은 코어 PostgreSQL의 마이너 릴리스와 별개로 취약점이 터집니다. pgvector IVFFlat 사례처럼 “서버는 패치됐는데 확장이 뚫리는” 상태가 쉽게 만들어집니다.

결국 마이너 업그레이드의 단위는 “postgres 프로세스”가 아니라 “클러스터가 의존하는 실행 가능한 구성요소 전체(서버+확장+인덱스+검증 루틴)”로 잡는 게 일관됩니다.

## 참고 자료

- [PostgreSQL 18.7, 17.12, 16.16, 15.20, 14.25, and 19 RC 2 Released!](https://www.postgresql.org/about/news/postgresql-187-1712-1616-1520-1425-and-19-rc-2-released-3442/)
- [PostgreSQL 18.7 릴리스 노트](https://www.postgresql.org/docs/18/release-18-7.html)
- [PostgreSQL 17.12 릴리스 노트](https://www.postgresql.org/docs/17/release-17-12.html)
- [PostgreSQL 16.16 릴리스 노트](https://www.postgresql.org/docs/16/release-16-16.html)
- [PostgreSQL 15.20 릴리스 노트](https://www.postgresql.org/docs/15/release-15-20.html)
- [PostgreSQL 14.25 릴리스 노트](https://www.postgresql.org/docs/14/release-14-25.html)
- [CVE-2026-6460 보안 공지](https://www.postgresql.org/support/security/CVE-2026-6460/)
- [CVE-2026-120153 보안 공지](https://www.postgresql.org/support/security/CVE-2026-120153/)
- [CVE-2026-120144 보안 공지](https://www.postgresql.org/support/security/CVE-2026-120144/)
- [Versioning Policy](https://www.postgresql.org/support/versioning/)
- [ALTER EXTENSION 문서](https://www.postgresql.org/docs/current/sql-alterextension.html)
- [Packaging Related Objects into an Extension](https://www.postgresql.org/docs/current/extend-extensions.html)
- [REINDEX 문서](https://www.postgresql.org/docs/18/sql-reindex.html)
- [amcheck 문서](https://www.postgresql.org/docs/18/amcheck.html)
- [PostgreSQL News Archive (2026-10-05)](https://www.postgresql.org/about/newsarchive/-/20261005/)
- [pgvector 0.8.7 Released](https://www.postgresql.org/about/news/pgvector-087-released-3392/)
- [Buffer overflow with IVFFlat index build (pgvector #1036)](https://github.com/pgvector/pgvector/issues/1036)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
