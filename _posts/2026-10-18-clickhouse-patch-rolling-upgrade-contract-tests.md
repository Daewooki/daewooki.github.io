---
title: "ClickHouse 패치도 릴리스처럼 다루는 롤링 업그레이드 설계"
description: "ClickHouse 패치에서도 플랜·머지·리소스가 흔들립니다. 계약 기반 테스트와 mixed-version 롤링 업그레이드, Keeper/replication 배포·롤백 체크리스트를 정리합니다."
date: 2026-10-18 09:52:07 +0900
categories: ["Data", "ClickHouse"]
tags: ["clickhouse", "rolling-upgrade", "regression-testing", "replication", "clickhouse-keeper", "operations"]
render_with_liquid: false
---

## 패치 업그레이드가 바꾸는 것: ClickHouse에서 계약이 깨지는 지점

2026-10-17에 ClickHouse stable 채널 최신 패치로 `26.9.21.9`가 게시되었습니다. 공식 패키지 페이지에 stable `26.9.21.9` / LTS `26.8.30.8`가 같은 날짜로 올라와 있고, tarball/DEB/RPM 모두 그 버전을 가리킵니다. [ClickHouse packages](https://packages.clickhouse.com/)에 stable `26.9.21.9`가 2026-10-17 릴리스로 표시됩니다.[^1]

GitHub 릴리스 자산에서도 `v26.9.21.9-stable`이 2026-10-17에 업로드된 흔적이 보입니다(예: `clickhouse-client-26.9.21.9-amd64.tgz` 타임스탬프). [GitHub Releases: v26.9.21.9-stable](https://github.com/ClickHouse/ClickHouse/releases?after=v20.12.8.5-stable)에서 확인할 수 있습니다.[^2]

문제는 이게 패치라는 점입니다. ClickHouse 문서는 “Minor version upgrades should be adopted often”, “Minor releases do not have breaking changes” 같은 톤으로 말합니다. self-managed upgrade 가이드는 minor를 자주 올리라고 권하고, 중요한 bug fix(보안 포함 가능)를 포함한다고 적습니다. [Self-managed Upgrade](https://clickhouse.com/docs/guides/oss/update)에도 같은 취지의 문장이 있습니다.[^3]

운영 관점에서는 이 문장이 반쯤만 맞습니다.

- DDL 관점의 breaking change가 없을 수는 있습니다.
- 하지만 **쿼리 플랜**, background merge/TTL/compaction의 **머지 동작**, 특정 쿼리의 **메모리/CPU 프로파일**은 패치에서도 충분히 달라집니다.

ClickHouse는 “데이터를 저장하는 엔진”이면서 동시에 “분산 실행 엔진”이고, MergeTree 계열의 내부 작업(머지/압축/마크 파일/인덱스 구조)과 optimizer/analyzer의 변경이 체감 성능을 흔들기 쉽습니다. ClickHouse 쪽에서도 analyzer 변화가 쿼리 성능을 크게 느리게/빠르게 만들 수 있다고 문서에서 직접 언급합니다. [parallel replicas 가이드의 analyzer 관련 주의](https://github.com/ClickHouse/clickhouse-docs/blob/main/docs/deployment-guides/parallel-replicas.mdx)에서 “might significantly slow down or speed up query execution”라고 적어 둔 부분이 그 분위기입니다.[^4]

그래서 나는 ClickHouse 패치 업그레이드를 “패치니까 바로 올린다”가 아니라, **패치도 릴리스처럼 다룬다**로 가져가는 쪽에 가깝습니다. 즉, 업그레이드의 단위를 (1) 계약 정의, (2) 계약 검증 자동화, (3) mixed-version 구간 통제, (4) Keeper/replication 안정성 보장, (5) 롤백 가능성 판단까지 포함한 change management로 놓습니다.

이 글은 아래 세 가지를 실무적으로 정리합니다.

- (1) 패치 릴리스를 ‘스키마/설정 계약’과 함께 테스트하는 방법
- (2) rolling upgrade 중 mixed-version 클러스터에서 주의할 점
- (3) Keeper/replication 환경에서 단계적 배포/롤백 체크리스트

패치 적용 전후에 무엇을 “같아야 한다”로 보고, 무엇이 달라져도 되는지까지 문서화하지 않으면, 테스트는 늘어나기만 하고 결론이 안 납니다.

## 업그레이드를 '설정/스키마 계약'으로 정의하기

내가 ClickHouse 업그레이드에서 말하는 계약은 크게 두 층입니다.

1) **사용자/애플리케이션 계약**: 애플리케이션이 ClickHouse에 기대는 것(스키마, 결과의 의미, 지연/비용 상한선)
2) **클러스터 내부 계약**: replication/keeper/distributed query가 깨지지 않고 굴러가는 조건

### 스키마 계약: DDL이 아니라 “데이터 의미”까지 포함합니다

ClickHouse는 같은 컬럼/타입이라도 엔진 설정, ORDER BY 키, TTL, codec, secondary index(skipping index) 구성에 따라 결과의 지연 특성이 크게 달라집니다. 패치 업그레이드 시 스키마 계약은 보통 아래를 포함해야 합니다.

- 테이블/머티리얼라이즈드 뷰/프로젝션 구성(존재 여부 + 정의문)
- MergeTree 계열의 핵심 설정(예: `index_granularity`, `storage_policy`, TTL 표현식)
- replication 경로 템플릿(특히 `{shard}`, `{replica}` 치환 포함)

DDL을 “그대로” 유지하는 것만으로는 부족합니다. upgrade 과정에서 settings의 default가 바뀌면, 같은 DDL에서도 실제 동작이 바뀌는 경우가 생깁니다.

### 설정 계약: default를 신뢰하지 않는 쪽으로 갑니다

ClickHouse 쪽에서도 업그레이드 리스크를 완화하기 위한 장치로 `compatibility` 같은 개념을 제공합니다.

ClickHouse Cloud 문서에는 `compatibility`를 “이전 버전의 default settings를 쓰도록 하는 장치”로 설명합니다. 서비스가 업그레이드되어도 `compatibility` 값이 유지되면 기존에 존재하던 settings의 default가 바뀌지 않는다는 식의 설명이 있습니다. [ClickHouse Cloud upgrades 문서의 compatibility 설명](https://github.com/ClickHouse/clickhouse-docs/blob/main/docs/cloud/features/06_admin_features/upgrades.md)에서 그 의도를 확인할 수 있습니다.[^5]

다만 여기서 오해하면 안 되는 게 두 가지입니다.

- `compatibility`가 해결하는 건 “쿼리 레벨의 의미 변화/기본값 변화” 쪽입니다.
- on-disk 포맷/replication 프로토콜/feature 제거 같은 건 이걸로 못 막습니다.

ClickHouse 쪽에서도 `compatibility`가 만능이 아니라는 뉘앙스는 여러 논의에서 반복됩니다. 예를 들어 Upgrade Guard 제안 이슈에서는 `compatibility`는 일부 케이스만 커버하고, on-disk format 변화나 protocol 변화는 커버하지 못한다고 명시합니다. [Upgrade Guard 제안](https://github.com/ClickHouse/ClickHouse/issues/97500)에서 그 한계를 분명히 적어 둡니다.[^6]

그래서 운영에서의 결론은 간단합니다.

- default에 기대지 말고, 내가 중요하다고 생각하는 settings는 명시적으로 박습니다.
- 그리고 그 “명시적으로 박힌 값 목록” 자체를 업그레이드 계약의 일부로 취급합니다.

이 접근은 이전에 Grafana 패치 업그레이드를 자동화할 때도 비슷하게 썼습니다. 다만 ClickHouse는 “설정이 성능을 바꾸는 정도”가 Grafana보다 훨씬 강하고, replication과 머지가 얽혀서 blast radius가 더 큽니다.

- [Grafana 패치 업그레이드 검증 자동화 설계](https://daewooki.github.io/posts/grafana-patch-upgrade-automation/)

### 리소스 계약: “정확히 얼마나 빨라야 한다” 보다 “얼마나 더 비싸져도 괜찮나”가 실전입니다

패치 업그레이드는 기능 추가가 아닌 bug fix/최적화가 중심이라, 기대값은 보통 “더 좋아질 수도”입니다. 하지만 운영에서 중요한 건 최선이 아니라 최악입니다.

그래서 리소스 계약은 보통 이런 형태가 더 유용합니다.

- P95 latency가 X% 이상 증가하면 실패
- 동일 쿼리 셋에서 `read_rows`, `read_bytes`가 Y% 이상 증가하면 실패(플랜/프루닝 변화 감지)
- peak memory가 Z% 이상 증가하면 실패(aggregation/joins의 스필 여부 변화 포함)

ClickHouse는 쿼리 플랜이 바뀌면 read amplification이 바뀌고, 그게 CPU/IO를 같이 흔드는 쪽이 많습니다.

## v26.9.21.9-stable 검증용 Contract Test 설계: 결과/플랜/리소스 3종 세트

여기부터는 “실제로 돌릴 수 있는 수준”으로 적습니다. 장난감 예제가 아니라, 운영에서 실제로 자주 보는 형태(이벤트 팩트 테이블 + 차원 테이블 join + top-N + distinct + 세그먼트 집계)를 기준으로 합니다.

테스트의 철학은 단순합니다.

- 결과가 같아야 합니다(의미 계약).
- 플랜이 바뀌면 바뀐 이유를 설명할 수 있어야 합니다(성능 계약의 원인 추적).
- 리소스가 튀면 튄 지점을 수치로 남겨야 합니다(회귀 감지).

아래 harness는 “업그레이드 전”과 “업그레이드 후”에 각각 실행해서 아티팩트를 남기고, CI에서 diff를 보는 구조입니다.

### 전제

- ClickHouse server는 이미 설치되어 있고(클러스터든 단일이든), `clickhouse-client`로 붙을 수 있어야 합니다.
- 테스트는 반드시 prod가 아닌 환경(스테이징/리드 레플리카/카나리 노드)에서 먼저 돌립니다.
- 실데이터를 전부 복제하기 어렵다면, 최소한 아래 조건을 만족하는 샘플이 필요합니다.
  - 최근 24~72시간 데이터
  - 가장 큰 테이블 1~3개(카디널리티와 part 수가 현실적으로 나오는 크기)
  - 대표 쿼리 20~200개(대시보드/배치/서빙 API에서 실제 실행되는 것)

### 파일 레이아웃

```
clickhouse-upgrade-contract/
  sql/
    00_schema.sql
    10_seed.sql
    queries/
      q01_top_pages.sql
      q02_distinct_users.sql
      q03_join_dim.sql
      q04_funnel_like.sql
  run/
    run_snapshot.sh
    diff_snapshot.py
```

### 스키마 + 시드 데이터(현실적인 크기)

아래는 스테이징에서 흔히 하는 방식입니다. `numbers()`를 이용해 빠르게 1,000만 행 정도를 만들고, ORDER BY/partition을 현실적으로 잡습니다.

`sql/00_schema.sql`

```sql
CREATE DATABASE IF NOT EXISTS upgrade_lab;

DROP TABLE IF EXISTS upgrade_lab.events;

CREATE TABLE upgrade_lab.events
(
    event_time DateTime64(3),
    dt Date MATERIALIZED toDate(event_time),
    user_id UInt64,
    session_id UUID,
    page LowCardinality(String),
    ref LowCardinality(String),
    country FixedString(2),
    is_bot UInt8,
    duration_ms UInt32,
    bytes UInt64
)
ENGINE = MergeTree
PARTITION BY dt
ORDER BY (dt, page, user_id, event_time)
SETTINGS index_granularity = 8192;

DROP TABLE IF EXISTS upgrade_lab.page_dim;

CREATE TABLE upgrade_lab.page_dim
(
    page LowCardinality(String),
    page_group LowCardinality(String),
    is_internal UInt8
)
ENGINE = MergeTree
ORDER BY page;
```

`sql/10_seed.sql`

```sql
INSERT INTO upgrade_lab.page_dim
SELECT
    concat('page_', toString(number % 2000)) AS page,
    concat('group_', toString(number % 50)) AS page_group,
    if(number % 20 = 0, 1, 0) AS is_internal
FROM numbers(2000);

INSERT INTO upgrade_lab.events
SELECT
    now64(3) - toIntervalSecond(number % 86400) AS event_time,
    reinterpretAsUInt64(cityHash64(number)) AS user_id,
    generateUUIDv4() AS session_id,
    concat('page_', toString(number % 2000)) AS page,
    concat('ref_', toString(number % 200)) AS ref,
    CAST(multiIf(number % 5 = 0, 'US', number % 5 = 1, 'KR', number % 5 = 2, 'JP', number % 5 = 3, 'DE', 'FR'), 'FixedString(2)') AS country,
    if(number % 97 = 0, 1, 0) AS is_bot,
    toUInt32(10 + (number % 5000)) AS duration_ms,
    toUInt64(200 + (number % 500000)) AS bytes
FROM numbers(10000000);
```

실행 명령:

```bash
clickhouse-client --query "SOURCE sql/00_schema.sql"
clickhouse-client --query "SOURCE sql/10_seed.sql"
```

예상 출력은 환경에 따라 다르지만, `INSERT INTO ... SELECT FROM numbers()`는 수 초~수십 초 안에 끝나는 게 일반적입니다(스토리지/CPU/설정에 따라 달라집니다).

### 대표 쿼리: 결과/플랜/리소스를 동시에 잡습니다

`sql/queries/q01_top_pages.sql`

```sql
SELECT
  page,
  count() AS pv,
  uniqExact(user_id) AS uu
FROM upgrade_lab.events
WHERE dt >= today() - 1
  AND is_bot = 0
GROUP BY page
ORDER BY pv DESC
LIMIT 50;
```

`sql/queries/q02_distinct_users.sql`

```sql
SELECT
  country,
  uniqExact(user_id) AS uu,
  quantileTDigest(0.95)(duration_ms) AS p95_duration
FROM upgrade_lab.events
WHERE dt >= today() - 1
GROUP BY country
ORDER BY uu DESC;
```

`sql/queries/q03_join_dim.sql`

```sql
SELECT
  d.page_group,
  sum(e.bytes) AS sum_bytes,
  count() AS events
FROM upgrade_lab.events e
INNER JOIN upgrade_lab.page_dim d
  ON e.page = d.page
WHERE e.dt >= today() - 1
  AND d.is_internal = 0
GROUP BY d.page_group
ORDER BY sum_bytes DESC
LIMIT 50;
```

`sql/queries/q04_funnel_like.sql`

```sql
WITH
  toStartOfHour(event_time) AS h
SELECT
  h,
  countIf(page = 'page_1') AS view_step,
  countIf(page = 'page_2') AS click_step,
  countIf(page = 'page_3') AS purchase_step
FROM upgrade_lab.events
WHERE dt >= today() - 1
GROUP BY h
ORDER BY h;
```

이 네 개만으로도 패치 업그레이드에서 자주 터지는 변화(필터 푸시다운/LowCardinality 처리/집계 메모리/조인 빌드 전략/정렬/limit)가 어느 정도 잡힙니다.

### 스냅샷 수집 스크립트

`run/run_snapshot.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   OUT_DIR=out/pre  CH_HOST=... CH_USER=... CH_PASSWORD=... ./run/run_snapshot.sh

OUT_DIR=${OUT_DIR:-out/snapshot}
CH_HOST=${CH_HOST:-127.0.0.1}
CH_PORT=${CH_PORT:-9000}
CH_USER=${CH_USER:-default}
CH_PASSWORD=${CH_PASSWORD:-}
CH_DB=${CH_DB:-default}

mkdir -p "$OUT_DIR"

CH=(clickhouse-client --host "$CH_HOST" --port "$CH_PORT" --user "$CH_USER" --password "$CH_PASSWORD" --database "$CH_DB")

# 1) 버전/빌드
"${CH[@]}" --query "SELECT version() FORMAT TabSeparated" > "$OUT_DIR/version.tsv"

# 2) 업그레이드 리스크가 큰 설정: changed=1(명시 오버라이드)만 뽑아도 되고,
#    전체를 저장해두면 diff가 더 강합니다.
"${CH[@]}" --query "SELECT name, value, changed FROM system.settings ORDER BY name FORMAT TSV" > "$OUT_DIR/system_settings.tsv"

# 3) 스키마(테이블/뷰) 정의 덤프: 계약의 핵심
"${CH[@]}" --query "SELECT database, name, engine, create_table_query FROM system.tables WHERE database='upgrade_lab' ORDER BY name FORMAT TSVWithNames" > "$OUT_DIR/system_tables.tsv"

# 4) 쿼리 결과 + 플랜
mkdir -p "$OUT_DIR/results" "$OUT_DIR/plans"

for q in sql/queries/*.sql; do
  base=$(basename "$q" .sql)

  # 결과는 JSONEachRow가 diff가 쉬움
  "${CH[@]}" --multiquery --queries-file "$q" --format JSONEachRow > "$OUT_DIR/results/${base}.jsonl"

  # 플랜은 EXPLAIN JSON을 저장
  # (포맷/키가 버전별로 바뀔 수 있으므로 '그 자체가 signal'이 됩니다.)
  sql=$(cat "$q")
  "${CH[@]}" --query "EXPLAIN JSON $sql" > "$OUT_DIR/plans/${base}.plan.json"

done

# 5) 리소스/프로파일: query_log 기반 (테스트 직후 flush)
"${CH[@]}" --query "SYSTEM FLUSH LOGS" >/dev/null

"${CH[@]}" --query "
SELECT
  query_id,
  query_kind,
  type,
  event_time,
  query_duration_ms,
  read_rows,
  read_bytes,
  written_rows,
  written_bytes,
  memory_usage,
  ProfileEvents['SelectedRows'] AS pe_selected_rows,
  ProfileEvents['SelectedBytes'] AS pe_selected_bytes
FROM system.query_log
WHERE event_time >= now() - INTERVAL 10 MINUTE
  AND current_database = 'default'
ORDER BY event_time DESC
FORMAT JSONEachRow
" > "$OUT_DIR/query_log.jsonl"

# 6) 머지/파츠 상태: 패치에서 가장 많이 달라지는 구간 중 하나
"${CH[@]}" --query "
SELECT
  table,
  count() AS parts,
  sum(rows) AS rows,
  sum(bytes_on_disk) AS bytes_on_disk
FROM system.parts
WHERE active
  AND database='upgrade_lab'
GROUP BY table
ORDER BY table
FORMAT TSVWithNames
" > "$OUT_DIR/parts_summary.tsv"

echo "OK: snapshot written to $OUT_DIR"
```

실행 예시(업그레이드 전/후):

```bash
# 업그레이드 전
OUT_DIR=out/pre ./run/run_snapshot.sh

# (여기서 v26.9.21.9-stable로 업그레이드)

# 업그레이드 후
OUT_DIR=out/post ./run/run_snapshot.sh
```

### diff 스크립트: 실패 조건을 “계약 위반”으로 바꿉니다

`run/diff_snapshot.py`

```python
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def read_text(p: Path) -> str:
    return p.read_text(encoding='utf-8', errors='replace')

def load_json_lines(p: Path):
    out = []
    for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out

def main(pre_dir: str, post_dir: str):
    pre = Path(pre_dir)
    post = Path(post_dir)

    pre_ver = read_text(pre / "version.tsv").strip()
    post_ver = read_text(post / "version.tsv").strip()
    print(f"pre_version={pre_ver}")
    print(f"post_version={post_ver}")

    # 결과 계약: JSONL을 '정렬 가능한 형태'로 canonicalize 후 비교
    # (여기서는 단순히 라인 단위로 비교하지만, 실제로는 key 정렬/타입 정규화가 더 낫습니다.)
    result_dir_pre = pre / "results"
    result_dir_post = post / "results"

    failed = False

    for pre_file in sorted(result_dir_pre.glob("*.jsonl")):
        name = pre_file.name
        post_file = result_dir_post / name
        if not post_file.exists():
            print(f"MISSING in post: {name}")
            failed = True
            continue

        pre_rows = load_json_lines(pre_file)
        post_rows = load_json_lines(post_file)

        if pre_rows != post_rows:
            print(f"RESULT_DIFF: {name} pre_rows={len(pre_rows)} post_rows={len(post_rows)}")
            failed = True

    # 리소스 계약(예시): query_duration_ms / read_rows / memory_usage가 30% 이상 튀면 실패
    # 운영에서는 query_id 매칭이 어렵기 때문에, 테스트 harness에서는 쿼리별로 query_id를 고정하는 게 좋습니다.

    if failed:
        print("FAIL")
        sys.exit(2)

    print("PASS")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: diff_snapshot.py out/pre out/post")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
```

실행:

```bash
python3 run/diff_snapshot.py out/pre out/post
```

이 도구는 완성품이 아니라 “계약 테스트의 형태”를 보여주는 목적입니다. 실제 운영에서는 아래가 추가되어야 합니다.

- 쿼리별 `query_id` 고정(세션/클라이언트에서 지정)
- 결과 비교에서 부동소수/타임존/정렬 안정성 처리
- plan JSON에서 비결정적인 필드(노드 ID 등) 제거 후 비교
- query_log 대신 `system.query_metric_log` 같은 로그를 함께 보는 방식(수집 정책에 따라 다름)

하지만 핵심은 같습니다. 업그레이드 판단을 “감”이 아니라 “계약 위반 여부”로 바꾸는 데 목적이 있습니다.

## Mixed-version 클러스터에서 생기는 일: 분산 쿼리와 ReplicatedMergeTree의 마찰

rolling upgrade는 필연적으로 mixed-version 구간을 만듭니다. 이때 ClickHouse에서 문제가 되는 축은 두 가지입니다.

1) distributed query(원격 읽기/집계)에서의 의미/정확성/성능
2) replication(특히 ReplicatedMergeTree)에서의 프로토콜/머지 결과/체크섬

### 1년 호환 윈도우를 “기술적 가능”으로만 이해하면 위험합니다

ClickHouse 생태계에서는 “1년 이내 버전이면 mixed-version이 대체로 가능” 같은 이야기가 자주 나옵니다. 실제로 업그레이드 가이드도 어느 정도의 윈도우를 전제로 설계를 합니다.

OSSeva가 ClickHouse 문서/정책을 기반으로 정리한 글에서는, self-managed rolling upgrade는 대략 1년 정도의 호환 윈도우를 전제로 설명되고 그 이상 벌어지면 mixed-version을 피하라고 강하게 적습니다. 또한 mixed-version에서는 distributed query가 느려질 수 있고, background 작업에서 retriable error가 나올 수 있으니 빨리 동일 버전으로 수렴시키라고 정리합니다. [OSSeva: Upgrading ClickHouse LTS Releases](https://www.osseva.io/blog/clickhouse-lts-upgrade)에서 이런 관점을 확인할 수 있습니다.[^7]

이 주장은 대체로 맞지만, 운영에서 더 중요한 건 다음입니다.

- 호환된다는 건 “문법이 먹는다”일 수 있고, “운영 의미가 같다”가 아닐 수 있습니다.
- mixed-version 구간은 짧아야 합니다. 짧게 끝낼 수 없는 조직이라면, 업그레이드 설계 자체를 바꿔야 합니다(예: make-before-break 스타일로 capacity를 먼저 늘리고 스위치).

ClickHouse Cloud 문서에서 upgrade 메커니즘을 “make before break”라고 부르는 것도 같은 맥락입니다. 업그레이드 시 새 replica를 먼저 붙이고(old 제거는 나중) 더 매끄럽게 만든다는 설명이 있습니다. [ClickHouse Cloud upgrades 문서](https://github.com/ClickHouse/clickhouse-docs/blob/main/docs/cloud/features/06_admin_features/upgrades.md)에서 이 방향성을 읽을 수 있습니다.[^5]

self-hosted에서도 같은 아이디어를 쓸 수 있습니다. 다만 비용이 듭니다.

### mixed-version에서 replication이 터지는 가장 흔한 형태

mixed-version에서 replication 문제는 “서버가 죽는다”보다 더 지저분한 방식으로 나타납니다.

- replication queue가 밀리기 시작합니다.
- 일부 작업이 재시도 루프에 들어갑니다.
- 로그에는 CHECKSUM mismatch나 파싱 에러 같은 단서가 남지만, 업그레이드 직후에는 다들 그걸 정상으로 착각하기도 합니다.

OSSeva 글에서는 mixed-version 동안 `CHECKSUM_DOESNT_MATCH`가 `MergeFromLogEntryTask` 쪽에서 나타날 수 있고(머지가 바이트 단위로 동일하지 않을 수 있음), 버전이 수렴하면 사라진다고 정리합니다. [OSSeva: Rolling upgrade of replicas](https://www.osseva.io/blog/clickhouse-lts-upgrade) 중 rolling 파트의 설명이 이 포인트를 담고 있습니다.[^7]

이걸 “그냥 잠깐 나는 에러”로 취급하면 안 됩니다.

- **이 에러가 사라지는 전제는 결국 모든 replica가 같은 버전으로 수렴하는 것**입니다.
- 업그레이드를 중간에 멈출 가능성이 있는 조직(승인 지연, 배포 창 제한)이면, mixed-version 상태를 장시간 유지할 수 있고 그때부터는 데이터/운영 리스크가 커집니다.

또 한 가지: ClickHouse 쪽 이슈 트래킹에도 mixed-version/rolling이 항상 매끄럽지 않았던 흔적이 남아 있습니다. 예를 들어 20.9 → 20.12 rolling에서 replication 로그 파싱이 깨지는 사례가 있었고, “rolling이 불가능한가?”라는 질문이 올라온 적이 있습니다. [Cannot do rolling cluster upgrade from 20.9 to 20.12](https://github.com/ClickHouse/ClickHouse/issues/18609) 같은 이슈는 업그레이드 구간에서 프로토콜/로그 포맷이 얽히면 어떤 종류의 장애가 나는지 감을 잡는 데 도움이 됩니다.[^8]

물론 지금은 26.x 라인이라 당시와 그대로 비교할 수는 없지만, 결론은 같습니다.

- mixed-version을 “될 거다”라고 두루뭉술하게 믿지 말고,
- mixed-version 구간에서 어떤 기능을 쓰지 말아야 하는지(혹은 어떤 쿼리를 막아야 하는지)까지 런북에 박아야 합니다.

### distributed query에서 “조용히 틀릴 수 있는” 클래스가 존재합니다

이 부분은 지금 시점의 26.9에 그대로 적용된다고 단정할 수는 없습니다. 다만 ClickHouse 역사에서 mixed-version이 결과 정확도에 영향을 준 사례가 문서에 남아 있습니다.

과거 문서(구버전 문서 PDF)에는 서로 다른 버전이 클러스터에 섞여 있을 때 특정 분산 쿼리 함수들의 결과가 부정확할 수 있다는 언급이 있습니다(예: 분산 분산분산 쿼리에서 일부 통계 함수들). 이건 “mixed-version이 성능만 느려지는 문제”가 아니라 “정확성 문제”가 될 수 있음을 보여주는 사례입니다.[^9]

내가 이걸 지금도 강조하는 이유는, ClickHouse 업그레이드에서 가장 무서운 실패 모드가 “에러가 아니라 조용한 의미 변화”이기 때문입니다. Upgrade Guard 제안 이슈도 비슷한 관점에서 “silent wrong results” 범주의 위험을 따로 분류합니다. [Upgrade Guard 제안](https://github.com/ClickHouse/ClickHouse/issues/97500)에는 이 범주가 명시되어 있습니다.[^6]

따라서 mixed-version 구간에서는 아래를 운영 정책으로 두는 게 안전합니다.

- 결과 정확도가 중요한 배치/지표 쿼리를 mixed-version 시간대에 실행하지 않거나, 실행해도 “신뢰하지 않는 지표”로 표기(내 경우 대시보드에 업그레이드 윈도우 배너를 띄우는 방식으로 해결했습니다).
- distributed query를 한동안 단일 shard/단일 replica로 제한(라우팅/서비스 레이어에서 처리)해서 mixed-version의 조합 폭을 줄입니다.

## Rolling upgrade 런북: shard 단위, replica 단위, 쿼리 라우팅 단위로 쪼개기

rolling upgrade 설계를 할 때, 단순히 “노드를 하나씩 올린다”만 있으면 실패합니다. ClickHouse는 workload가 다양하고, distributed query와 replication이 동시에 걸려서 업그레이드 도중의 조합이 너무 많아집니다.

내가 선호하는 분해는 이렇습니다.

- shard 단위로 격리(한 shard 안에서는 replica 하나는 항상 정상 버전으로 서비스)
- replica 단위로 배포(단, 같은 shard의 모든 replica를 동시에 내리지 않음)
- 쿼리 라우팅 단위로 통제(업그레이드 노드로 갈 수 있는 트래픽의 종류를 제한)

ClickHouse의 replication은 비동기 multi-master입니다. 내부 아키텍처 문서에서도 replication이 asynchronous multi-master이고 ZooKeeper/Keeper를 통해 coordination을 한다고 정리합니다. [ClickHouse architecture: replication](https://github.com/ClickHouse/docs-reference/blob/master/docs/en/development/architecture.md)에서 이 점을 확인할 수 있습니다.[^10]

비동기 multi-master라는 말은 곧 “업그레이드 중에 쓰기가 어디로 들어갔는지”가 중요해진다는 뜻입니다.

### 내가 mixed-version 동안 제한하는 것들

조직/서비스에 따라 다르지만, 공통적으로 제한하면 사고가 줄어드는 것들이 있습니다.

- DDL(특히 replicated DDL): mixed-version에서 DDL 이벤트가 쌓이면 rollback/재시도가 훨씬 어려워집니다.
- 대규모 `OPTIMIZE FINAL`: 업그레이드 구간에 강제 머지를 넣으면, 머지 결과/압축/part 포맷 차이를 건드릴 확률이 올라갑니다.
- “아직 계약 테스트에 들어가지 않은” ad-hoc 분석 쿼리: 업그레이드 기간에 운영자가 임의 쿼리를 날리면 성능 회귀의 원인 추적이 어려워집니다.

이런 제한은 엔지니어 문화적으로 불편합니다. 하지만 패치가 자주 나오고, 업그레이드를 자주 해야 하는 구조라면 오히려 이런 운영 계약이 있어야 업그레이드 속도가 빨라집니다.

이 관점은 Kubernetes 패치 릴리스를 운영 계약으로 바꿨던 방식과도 유사합니다. 다만 ClickHouse는 DB라서 “업그레이드 중 상태 변화(머지/replication)가 지속된다”는 점이 더 까다롭습니다.

- [Kubernetes 1.35.10 패치 릴리스: 정기 패치를 운영 계약으로 바꾸는 법](https://daewooki.github.io/posts/kubernetes-patch-release-ops-contract/)

## Keeper/replication 환경 단계적 배포와 롤백 체크리스트

ClickHouse에서 Keeper는 “업그레이드에서 제일 건드리기 싫은 컴포넌트”입니다. 그런데 replication을 쓰는 순간, Keeper는 업그레이드 리스크의 중심축이 됩니다.

ClickHouse 공식 업그레이드 문서는 서버 업그레이드와 Keeper 업그레이드를 분리하라고 명확하게 말합니다. Keeper 안정성이 업그레이드 과정에서 필요하니, 서버 업그레이드를 먼저 끝내고 Keeper를 고려하라는 문장입니다. [Self-managed Upgrade](https://clickhouse.com/docs/guides/oss/update)에서 이 지침을 확인할 수 있습니다.[^3]

Altinity 쪽 knowledge base에서도 Keeper 관련해서 “Keeper 버전이 server 버전과 꼭 일치할 필요는 없다”, “가능하면 최신 Keeper가 성숙해서 성능이 낫다” 같은 운영 관점을 정리합니다. 특히 23.9 이전에서 업그레이드할 때 async_replication 같은 caveat가 있을 수 있다고 경고합니다. [Altinity KB: Using clickhouse-keeper](https://kb.altinity.com/altinity-kb-setup-and-maintenance/altinity-kb-zookeeper/clickhouse-keeper/)를 참고할 만합니다.[^11]

여기서는 “26.9.21.9-stable 서버 패치 업그레이드”를 전제로, Keeper/replication 환경에서 내가 체크하는 항목을 단계별로 적습니다.

### 0) 배포 전에 반드시 확정해야 하는 것(결정이 늦어지면 업그레이드가 길어집니다)

- 업그레이드 목표 버전: 이번 케이스는 stable `26.9.21.9`입니다.[^1]
- mixed-version 허용 시간: 예) shard 당 30분 이내, 전체 클러스터 3시간 이내
- 롤백 목표: “바이너리만 되돌린다”인지, “데이터 포맷/part 생성까지 되돌릴 수 있어야 한다”인지
  - 후자는 현실적으로 어려울 수 있습니다. Upgrade Guard 논의에서도 “새 포맷으로 데이터가 써지면 downgrade가 불가능해지는 변화”가 가장 위험한 클래스로 분류됩니다. [Upgrade Guard 제안](https://github.com/ClickHouse/ClickHouse/issues/97500)[^6]

나는 보통 롤백 목표를 이렇게 잡습니다.

- 업그레이드 초반(카나리/일부 replica 단계)에는 rollback이 가능해야 한다.
- 전체 shard가 업그레이드되고, 일정 시간(예: 24h) 동안 문제 없으면 그 뒤부터는 rollback보다 “전진(핫픽스/다음 패치)”으로 대응한다.

### 1) 배포 직전 클러스터 상태 점검(서버)

replication을 쓰면 배포 직전 상태 점검이 사실상 필수입니다. 여기서 상태가 불안정하면, 업그레이드가 원인인지 기존 문제가 터진 건지 구분이 안 됩니다.

- `system.replicas`에서 lag/readonly/queue 상태가 깨끗한지
- `system.replication_queue`에 오래된 항목이 쌓여 있지 않은지
- merge backlog가 비정상적으로 길지 않은지(파트 수 급증)

이 쿼리들은 환경마다 컬럼이 다를 수 있어, 런북에 “내가 쓰는 버전에서 유효한 컬럼”으로 고정해 두는 게 좋습니다.

### 2) 배포 순서(서버 → 서버 → … → 서버, Keeper는 마지막)

공식 문서의 권장대로, 서버를 먼저 끝내고 Keeper는 건드리지 않는 게 기본값입니다. [Self-managed Upgrade](https://clickhouse.com/docs/guides/oss/update)[^3]

서버 rolling의 구체적인 순서는 보통 다음 원칙을 씁니다.

- shard마다 “업그레이드에서 마지막까지 남길 replica(안전 replica)”를 하나 지정
- 나머지 replica를 하나씩 업그레이드
- shard의 모든 replica가 새 버전으로 수렴한 뒤 다음 shard로 이동

이렇게 하면 mixed-version의 조합 폭이 줄어듭니다.

### 3) mixed-version 구간 통제 포인트(가장 중요)

mixed-version에서 터지는 문제는 대개 “새 버전 노드가 생성한 무언가”를 “구 버전 노드가 처리 못 하는” 형태입니다. 이건 replication/머지/DDL 어디서든 나올 수 있습니다.

따라서 통제 포인트는 아래 두 가지입니다.

- 업그레이드 중에는 DDL을 동결합니다.
- 업그레이드 중에는 대규모 머지/재정렬을 유발하는 운영 작업을 넣지 않습니다.

그리고 이 통제를 기술적으로 강제하는 쪽이 낫습니다. 예를 들어 배포 윈도우 동안:

- 마이그레이션 파이프라인을 멈추거나
- 운영 계정의 DDL 권한을 임시로 회수하거나
- 배치 작업을 큐에서 hold하는 방식

사람에게 “하지 말아 주세요”는 실패합니다.

### 4) 롤백 체크리스트(서버)

**중요한 전제**: ClickHouse는 업그레이드 후 새 동작/새 포맷으로 데이터가 기록되면, 바이너리를 되돌리는 방식의 downgrade가 불가능해질 수 있습니다. Upgrade Guard 논의는 이 위험을 가장 앞에 둡니다. [Upgrade Guard 제안](https://github.com/ClickHouse/ClickHouse/issues/97500)[^6]

그래서 롤백은 “가능하면 빨리”, “가능한 구간에서만”을 원칙으로 해야 합니다.

- 카나리 replica 업그레이드 직후에 계약 테스트를 돌리고 바로 판정
- 성능/정확성 회귀가 보이면 shard 전체 확산 전에 중단
- mixed-version 상태가 길어지기 전에 원복

롤백 런북에 최소한 아래를 포함합니다.

- 롤백 트리거(수치 기반): P95 latency, error rate, replication queue length, CPU headroom
- 롤백 단위: replica 단위로 원복하되, shard의 quorum/가용성을 깨지 않게
- 롤백 후 검증: 계약 테스트를 다시 돌려 “원복이 성공했는지” 확인

### 5) Keeper 업그레이드(필요할 때만, 서버 수렴 이후)

서버 패치 업그레이드의 목적이 `26.9.21.9-stable`로 올리는 것이라면, Keeper까지 같이 올려야 하는지부터 먼저 따져야 합니다.

- Keeper에 security fix가 포함되어서 급한가?
- Keeper에서 관측되는 병목/버그가 해결되는가?

공식 문서는 “보안 수정이 필요하지 않으면 Keeper를 서버 업그레이드와 같이 올릴 필요가 없다”는 톤입니다. [Self-managed Upgrade](https://clickhouse.com/docs/guides/oss/update)[^3]

Altinity KB도 “Keeper 버전은 server와 같을 필요가 없다”는 운영 관점을 제공합니다. [Altinity KB: Using clickhouse-keeper](https://kb.altinity.com/altinity-kb-setup-and-maintenance/altinity-kb-zookeeper/clickhouse-keeper/)[^11]

결론적으로, 서버 패치 배포의 리스크를 Keeper까지 확장하지 않는 게 일반적으로 유리합니다.

## '어제 나온 stable 패치'를 오늘 올릴지 결정하는 기준

현재 시점은 2026-10-18(KST)이고, stable `26.9.21.9`는 2026-10-17에 게시되었습니다.[^1]

여기서 의사결정은 감정이 아니라, “내 시스템이 업그레이드로 얻는 이득”과 “업그레이드가 만드는 리스크”의 비교로 해야 합니다.

### 바로 올리는 쪽이 유리한 조건

- 해당 패치가 내 장애/성능 문제를 직접 해결하는 게 명확하다(재현 가능한 버그/핫픽스)
- 이미 canary 환경이 있고, 1~2시간 내로 계약 테스트 + 기본 부하 테스트가 끝난다
- mixed-version 윈도우를 짧게 가져갈 수 있다(자동화/배포 창 확보)

ClickHouse는 stable 채널이 빠르게 움직이고, 보안 지원 여부도 특정 라인에만 주는 정책을 운영합니다. GitHub 보안 정책 페이지의 지원 버전 표를 보면 26.9/26.8/26.7/26.3 같은 라인이 지원 대상으로 표시됩니다. [ClickHouse SECURITY.md / supported versions](https://github.com/clickhouse/clickhouse/security)[^12]

보안 관점에서 “지원 라인 안에 머문다”는 것 자체가 운영 비용을 줄입니다.

### 검증 윈도우를 두는 쪽이 유리한 조건

- replication/keeper가 얽힌 대형 클러스터이고, 롤백이 사실상 불가능한 구조다
- 쿼리 워크로드가 광범위하고, 대표 쿼리 셋을 제대로 정의하지 못했다
- 업그레이드 실패 시 비즈니스 임팩트가 큰데, 배포 창이 짧아 수습 시간이 없다

이 경우에는 “지금 바로 최신 패치로 간다”보다 아래가 더 현실적입니다.

- 먼저 LTS 라인을 따라가고(이번엔 `26.8.30.8`이 같은 날짜에 나왔습니다) stable은 스테이징에서만 추적한다.[^1]
- stable을 따라가야 한다면, 최소한 “계약 테스트 자동화”가 갖춰진 뒤에 주기를 짧게 가져간다.

다만 ClickHouse 문서/생태계의 속도를 생각하면, 검증 윈도우를 무한정 늘리면 업그레이드 간격이 벌어지고 다음 업그레이드가 더 위험해집니다. Upgrade Guard 논의에서도 “릴리스 노트를 끝없이 읽어야 하는 구조”가 운영 부담을 키운다고 지적합니다. [Upgrade Guard 제안](https://github.com/ClickHouse/ClickHouse/issues/97500)[^6]

결국 운영적으로는 “패치 업그레이드를 자주 하되, 매번의 비용은 계약 테스트로 낮춘다”가 장기적으로 맞는 방향입니다.

## 참고 자료

- [ClickHouse packages](https://packages.clickhouse.com/)
- [GitHub Releases: v26.9.21.9-stable](https://github.com/ClickHouse/ClickHouse/releases?after=v20.12.8.5-stable)
- [Self-managed Upgrade](https://clickhouse.com/docs/guides/oss/update)
- [ClickHouse SECURITY.md / supported versions](https://github.com/clickhouse/clickhouse/security)
- [Upgrade Guard 제안](https://github.com/ClickHouse/ClickHouse/issues/97500)
- [Cannot do rolling cluster upgrade from 20.9 to 20.12](https://github.com/ClickHouse/ClickHouse/issues/18609)
- [Altinity KB: Using clickhouse-keeper](https://kb.altinity.com/altinity-kb-setup-and-maintenance/altinity-kb-zookeeper/clickhouse-keeper/)
- [OSSeva: Upgrading ClickHouse LTS Releases](https://www.osseva.io/blog/clickhouse-lts-upgrade)
- [parallel replicas 가이드의 analyzer 관련 주의](https://github.com/ClickHouse/clickhouse-docs/blob/main/docs/deployment-guides/parallel-replicas.mdx)
- [ClickHouse architecture: replication](https://github.com/ClickHouse/docs-reference/blob/master/docs/en/development/architecture.md)
- [MongoDB 7.0.41 패치 적용 가이드: 롤링 업데이트에서 확인할 것들](https://daewooki.github.io/posts/mongodb-7-0-41-rolling-update-checklist/)
- [Grafana 패치 업그레이드 검증 자동화 설계](https://daewooki.github.io/posts/grafana-patch-upgrade-automation/)
- [Kubernetes 1.35.10 패치 릴리스: 정기 패치를 운영 계약으로 바꾸는 법](https://daewooki.github.io/posts/kubernetes-patch-release-ops-contract/)

[^1]: <https://packages.clickhouse.com/>
[^2]: <https://github.com/ClickHouse/ClickHouse/releases?after=v20.12.8.5-stable>
[^3]: <https://clickhouse.com/docs/en/operations/update>
[^4]: <https://github.com/ClickHouse/clickhouse-docs/blob/main/docs/deployment-guides/parallel-replicas.mdx>
[^5]: <https://github.com/ClickHouse/clickhouse-docs/blob/main/docs/cloud/features/06_admin_features/upgrades.md>
[^6]: <https://github.com/ClickHouse/ClickHouse/issues/97500>
[^7]: <https://www.osseva.io/blog/clickhouse-lts-upgrade>
[^8]: <https://github.com/ClickHouse/ClickHouse/issues/18609>
[^9]: <https://gonline-file.oss-cn-shenzhen.aliyuncs.com/file/pdf/2024-09-05/79823874c9de4a0f8653f3d5b3ee06bf.pdf>
[^10]: <https://github.com/ClickHouse/docs-reference/blob/master/docs/en/development/architecture.md>
[^11]: <https://kb.altinity.com/altinity-kb-setup-and-maintenance/altinity-kb-zookeeper/clickhouse-keeper/>
[^12]: <https://github.com/clickhouse/clickhouse/security>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
