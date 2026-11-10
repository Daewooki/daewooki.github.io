---
title: "ClickHouse 26.10: 회귀 테스트로 업그레이드 리스크를 수치화하는 법"
description: "26.10의 플래너·조인·집계, 캐시/스토리지, 백업·롤링 변화가 실제 워크로드에 미치는 영향을 회귀 테스트 항목으로 쪼갭니다."
date: 2026-11-10 12:26:05 +0900
categories: ["News", "Database"]
tags: ["clickhouse", "release-notes", "regression-testing", "query-planner", "rolling-upgrade", "benchmarking"]
render_with_liquid: false
---

## 26.10에서 실제로 벌어진 일: 공개일, 변화량, 그리고 “테스트 재료”

ClickHouse가 2026-11-06에 [ClickHouse release 26.10](https://clickhouse.com/blog/clickhouse-release-26-10)을 공개했습니다. 릴리스 블로그는 이 버전을 “104 new features, 225 performance optimizations, 739 bug fixes”로 요약합니다. 월간 릴리스의 고질적인 특성(변경점이 많고, 기능/성능/버그픽스가 뒤섞임)이 그대로 드러나는 숫자입니다.

흥미로운 부분은 날짜 레이어가 하나 더 있다는 점입니다.

* ClickHouse 소스 트리의 2026 changelog는 26.10의 릴리스를 “2026-10-22”로 잡고, Backward Incompatible Change를 별도 섹션으로 정리합니다. 이 문서가 사실상 업그레이드 실패의 80%를 미리 알려주는 체크리스트에 가깝습니다. [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)
* 패키지 저장소에는 stable 라인으로 `26.10.3.7` 같은 패치 버전이 올라와 있고, 릴리스 날짜도 따로 찍혀 있습니다. 운영 관점에서는 “26.10”이라는 월간 태그보다 “내가 올릴 정확한 patch build가 무엇인가”가 더 중요합니다. [ClickHouse packages](https://packages.clickhouse.com/)

이 글에서 26.10을 지금 다루는 이유는 단순히 기능이 늘어서가 아닙니다. 26.10은 (1) 플래너/조인/집계, (2) 스토리지/캐시, (3) 운영(백업·롤링) 축에서 동시에 변경이 들어왔고, 공식 문서와 발표 자료에 **성능 수치와 관측 지표(ProfileEvents, system.query_log 활용)**까지 같이 제시되어 있습니다. 즉, “업그레이드 리스크를 정량화할 회귀 테스트 항목”을 이번 주에 바로 쪼개서 추가하기 좋은 상태입니다.

## 축 1) 쿼리 플래너/조인/집계: 성능 개선이 ‘정답 변화’로 이어질 때를 잡아내기

### Analyzer 경로 정리: mixed-version 클러스터가 깨지는 방식이 문서로 박혔습니다

26.10에서 가장 운영 친화적인(반대로 말하면 사고 친화적인) 문장은 다음입니다.

* “The query analysis that preceded the analyzer is removed … set `enable_analyzer = 1` on every server before upgrading any of them.” [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

여기서 중요한 포인트는 “26.10부터 analyzer 이전 분석 경로가 완전히 제거”라는 사실 자체보다, 이게 **mixed-version에서 ‘initiator가 구버전’일 때 `NOT_FOUND_COLUMN_IN_BLOCK` 같은 형태로 터질 수 있다**는 구체적 실패 모드입니다. 실패가 query correctness 이슈로 보이는 순간, 온콜은 원인 파악에 시간을 날립니다.

회귀 테스트 관점에서는 다음 두 가지를 분리해야 합니다.

1) 단일 노드/동일 버전에서 결과가 바뀌는가(semantic change)
2) 분산 쿼리에서 initiator/worker 버전 조합에 따라 결과 컬럼명이 달라져 깨지는가(protocol/analysis mismatch)

26.10 업그레이드 계획에 “분산 쿼리 initiator를 먼저 올리지 않는다” 같은 규칙을 넣는 것만으로는 부족합니다. 실제 워크로드에 있는 distributed query 패턴을 뽑고, “initiator=old, worker=new” 조합에서 **실패하는 쿼리 셋**을 별도 케이스로 만들어야 합니다.

### JOIN: ‘임의 조건 JOIN’은 기능이 아니라 플래너 fallback 경로를 늘립니다

26.10은 “JOINs with arbitrary `ON` conditions”를 넣었습니다. `LIKE` 같은 조건을 `ON` 절에 둘 수 있고, 블로그도 URL 패턴 매칭 예제로 보여줍니다. [ClickHouse release 26.10](https://clickhouse.com/blog/clickhouse-release-26-10)

다만 블로그가 바로 경고합니다. equality가 없는 JOIN은 결국 block nested loop join 같은 최후의 수단으로 떨어질 수 있고, 비용이 cross join 급이 될 수 있습니다. 이 기능은 SQL 표현력 확장이라기보다, “실수로 느린 JOIN을 만들 가능성”을 키우는 변화이기도 합니다.

회귀 테스트 항목을 이렇게 추가하는 편이 안전합니다.

* 프로덕션 쿼리 로그에서 JOIN이 들어간 쿼리를 뽑고, EXPLAIN으로 join algorithm이 무엇으로 계획되는지 비교
* 특히 `ON` 절에 `LIKE`, `position`, `startsWith` 류가 들어가 있는 쿼리를 별도 분류
* 해당 분류는 latency뿐 아니라 read rows/read bytes가 급증하는지까지 같이 본다(조인이 느릴 때 대개 I/O도 같이 커진다)

### Merge JOIN 병렬화(기본 ON): ‘해당되는 팀’은 체감이 큰데, 해당 여부가 워크로드 의존입니다

26.10 changelog에 다음이 들어갑니다.

* `query_plan_join_shard_by_pk_ranges`가 기본으로 enabled
* `full_sorting_merge` 혹은 `parallel_full_sorting_merge` JOIN에서, join key가 양쪽 테이블 primary key의 prefix를 포함하면, single-thread merge join이 아니라 **PK range로 sharding된 독립 merge join을 all threads로** 실행 [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

발표 자료는 이걸 더 과감한 숫자로 밀어붙입니다. 200M ⋈ 50M 같은 규모에서 hash join보다 빠르고 메모리도 적게 쓰는 그림을 제시합니다. [ClickHouse: Release 26.10 Call](https://presentations.clickhouse.com/2026-release-26.10/)

이 개선은 다음 조건에서만 의미가 큽니다.

* 사실상 “두 테이블이 같은 key로 정렬되어 있고(ORDER BY), 그 prefix로 JOIN한다”는 모델
* 즉, dimension table을 event table의 PK prefix로 맞춰서 관리하는 팀, 또는 ETL 단계에서 정렬 키를 강제한 팀

반대로 대부분의 ClickHouse 사용자는 PK prefix JOIN을 엄격히 지키지 않습니다. 그래서 회귀 테스트/벤치 계획도 “전체 쿼리 평균”으로 보면 안 되고, 아래처럼 분할해야 합니다.

* PK prefix JOIN이 맞는 쿼리군(merge join candidate)
* 일반 hash join 쿼리군
* dictionary 기반 lookup(사실상 JOIN 대체) 쿼리군

merge join candidate는 업그레이드 후에 latency 개선이 크게 나올 수 있으니, 이 군은 “개선이 맞는지”도 확인해야 합니다. 개선이 안 나오면 schema/ORDER BY 정렬 키가 어긋났다는 신호일 수 있습니다.

### GROUP BY: Top-K dynamic filtering과 LowCardinality 최적화는 ‘읽는 양’이 바뀝니다

26.10의 집계 쪽에서 눈에 띄는 변화는 “GROUP BY가 빨라졌다” 같은 단일 문장이 아니라, 읽는 양(read rows/read bytes)을 바꾸는 최적화가 여러 개 들어왔다는 점입니다.

* `GROUP BY key LIMIT n` 및 `GROUP BY key ORDER BY key LIMIT n`에서 top-K heap 경계(boundary)를 read 단계로 전달해, boundary 밖의 row를 다른 컬럼 읽기 전에 드롭하고, PK/minmax index로 granule skipping까지 유도 (`enable_group_by_top_k_dynamic_filtering`) [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)
* `LowCardinality` 다중 키 GROUP BY에서 dictionary 기반 직렬화/상태 캐싱으로 CPU/메모리 개선(블로그에 26.9 vs 26.10 비교 수치 포함) [ClickHouse release 26.10](https://clickhouse.com/blog/clickhouse-release-26-10)

이런 최적화는 대체로 결과는 동일하지만, 다음 케이스에서 “동작 경계”가 바뀌는 경우가 있습니다.

* LIMIT/OFFSET 조합이 들어간 top-K 계열
* PK/skip index가 의도와 다르게 작동하는 테이블(ORDER BY 설계가 애매한 경우)
* `Nullable`, `LowCardinality`, `Map`, `JSON` 계열 복합 타입이 끼어 있을 때 plan이 바뀌며 예외가 다르게 터지는 경우

그래서 26.10 회귀 테스트는 “p95 latency”만 보면 놓칩니다. 아래 지표를 같이 수집하는 게 맞습니다.

* `read_rows`, `read_bytes`의 변화량
* `ProfileEvents`에서 top-K 관련 이벤트(가능하면)
* peak memory(메모리 최적화가 들어온 만큼, 다른 쪽 병목이 튀는지 확인)

### 해시 테이블 메모리 2x 절감: 좋은 소식인데, 운영 용량 계획은 다시 해야 합니다

26.10 changelog에는 “Large hash tables used for `GROUP BY`, `uniqExact`, and `JOIN` now use up to two times less memory”가 명시되어 있습니다. [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

발표 자료는 더 직설적입니다.

* GROUP BY 10M keys, 1B rows, 48 threads: 24.7GB → 16.3GB
* uniqExact 100M distinct: 13.5GB → 4.6GB, 1.33s → 0.31s [ClickHouse: Release 26.10 Call](https://presentations.clickhouse.com/2026-release-26.10/)

이 변화는 “같은 서버에서 더 많은 동시 쿼리를 받아도 된다”로 바로 번역하면 위험합니다. 메모리 사용량이 내려가면, 다음이 올라오는 패턴이 자주 나옵니다.

* CPU가 bottleneck으로 바뀐다
* disk spill 경로가 바뀐다
* background merge와 query의 경쟁 구도가 달라진다

따라서 업그레이드 직후 capacity를 늘리기보다는, 기존 QPS를 넣고 시스템 전체의 병목이 어디로 이동했는지부터 확인하는 게 낫습니다.

## 축 2) 스토리지/캐시: “캐시가 늘었다”가 아니라, 캐시가 관측과 회귀를 가능하게 만들었습니다

### query cache가 disk에 올라갑니다: 재시작 후 성능이 달라지는 시대

26.10은 query cache 결과를 filesystem cache를 backend로 해서 disk에 저장할 수 있습니다.

* `query_cache_on_disk_cache_name` 및 on-disk 관련 settings 추가
* “survive server restarts”, “distributed filesystem cache로 서버 간 공유 가능” [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

발표 자료는 구체적인 설정 예시와 재시작 후 성능 수치를 같이 보여줍니다. [ClickHouse: Release 26.10 Call](https://presentations.clickhouse.com/2026-release-26.10/)

이 변화는 성능 최적화 포인트이기도 하지만, 회귀 테스트 관점에서 더 중요합니다.

* 업그레이드 전/후를 비교할 때 “cold start”와 “warm cache”를 분리하지 않으면 결과 해석이 깨집니다.
* 운영 사고 관점에서 “재시작 직후 성능”이 **캐시 persistence**에 의해 달라집니다.

즉, 26.10부터는 벤치 계획에 “restart 후 동일 쿼리 재실행”을 포함시키는 것이 기본이 됩니다.

### query condition cache가 now()/today() 필터까지 커버: 대시보드 쿼리의 체감이 달라집니다

26.10 발표 자료는 query condition cache가 `now()` 조건을 time grid로 snap해서 캐시 가능해졌다는 그림을 포함합니다. [ClickHouse: Release 26.10 Call](https://presentations.clickhouse.com/2026-release-26.10/)

대시보드 워크로드는 `WHERE ts >= now() - INTERVAL 1 HOUR` 같은 형태가 흔합니다. 이전에는 이런 쿼리는 cache eligibility에서 빠지는 경우가 많았고, 팀들은 애플리케이션에서 time boundary를 파라미터로 넣는 방식으로 우회했습니다.

ClickHouse 쪽 자료도 query cache/condition cache를 다룰 때 “nondeterministic functions”가 캐시에 미치는 영향을 반복적으로 언급합니다. [ClickHouse concurrency: how to size for user-facing analytics](https://clickhouse.com/resources/engineering/high-concurrency-sizing-user-analytics%5C)

회귀 테스트에선 이걸 “좋아졌다”로만 보면 안 됩니다.

* 기존에 애플리케이션이 강제로 time bucket을 만들어서 캐시를 유도하고 있었다면, 26.10 이후에는 중복 최적화가 될 수 있습니다.
* 반대로, now()/today() 캐시가 들어오면서 stale tolerance를 어디까지 허용할지 정책을 다시 써야 합니다.

### columns cache(실험): filesystem cache/OS page cache와 경쟁하는 ‘세 번째 레이어’

26.10은 “experimental columns cache”를 추가합니다.

* wide `MergeTree` part의 deserialized column을 메모리에 유지
* `use_columns_cache`로 enable
* 메모리 압박 시 캐시가 메모리를 쿼리로 반환한다는 동작 설명 [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

블로그는 실제로 `system.query_log`와 `ProfileEvents['ColumnsCacheHits']`를 이용해 효과를 측정하는 예시를 제공합니다. [ClickHouse release 26.10](https://clickhouse.com/blog/clickhouse-release-26-10)

이게 회귀 테스트 재료로 좋은 이유는 두 가지입니다.

1) 이 캐시는 “결과”가 아니라 “디코딩된 컬럼 데이터”를 캐시하므로, 같은 데이터를 반복해서 읽는 다양한 쿼리군에 파급됩니다.
2) 효과가 CPU/메모리/latency에 걸쳐 분산되기 때문에, 기존 벤치가 “latency만” 보는 구조면 변화 원인을 놓칩니다.

columns cache를 켠 벤치는 반드시 다음을 같이 기록해야 합니다.

* 캐시 hit/miss (ProfileEvents)
* peak memory
* CPU time(가능하면 system.query_log의 ProfileEvents 기반)

### String filter pushdown 기본 ON: LIKE의 peak memory가 바뀌는 대신, scan 단계 비용 모델이 바뀝니다

26.10에서 `apply_string_filters_during_scan`이 기본 enabled가 됩니다. PREWHERE의 substring 조건을 column scan으로 내리고, non-matching value를 “empty string without copying”으로 처리합니다. [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

블로그는 이 최적화가 peak memory를 크게 줄이는 예시를 제공합니다. [ClickHouse release 26.10](https://clickhouse.com/blog/clickhouse-release-26-10)

여기서 회귀 포인트는 “정답이 같은가”가 아니라 “자원 사용이 어떻게 바뀌었나”입니다.

* LIKE가 많은 워크로드에서 이전에는 memory spike 때문에 OvercommitTracker에 걸리던 쿼리가, 26.10에서는 살아남을 수 있습니다.
* 살아남는다면, 그 쿼리가 이제는 CPU/disk를 더 오래 점유하면서 다른 쿼리를 밀어낼 수도 있습니다.

따라서 LIKE-heavy 쿼리는 “단일 쿼리 latency”뿐 아니라 “동시성 부하” 조건에서 함께 측정해야 합니다.

### IN subquery set spill 기본 동작: 메모리 안전장치가 I/O 리스크로 이동합니다

26.10 changelog에는 다음이 명시되어 있습니다.

* `IN` subquery set이 기본적으로 disk spill
* default ratio가 `max_bytes_ratio_before_external_set = 0.5`로 설명됨 [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

릴리스 블로그도 “IN subqueries can spill to disk”를 별도 항목으로 다루고, 메모리 제한 하에서 쿼리를 완주시키는 방향임을 보여줍니다. [ClickHouse release 26.10](https://clickhouse.com/blog/clickhouse-release-26-10)

운영적으로는 이게 “OOM이 줄어든다”로 끝나지 않습니다.

* spill이 일어나면 local disk가 병목이 될 수 있습니다.
* 특히 Kubernetes에서 ephemeral disk가 느리거나, hostPath 정책이 빡센 환경이면 업그레이드 후에 latency tail이 늘어날 수 있습니다.

회귀 테스트는 다음 체크를 포함해야 합니다.

* `IN (subquery)`가 있는 쿼리를 분류
* 동일 쿼리를 낮은 `max_memory_usage`로 돌려 spill 경로를 강제로 타게 만든 뒤, latency/bytes written/temp disk 사용량(가능하면)을 관측

### adaptive codec selection: 저장 효율/merge 비용의 trade-off를 다시 계산해야 합니다

26.10 changelog는 adaptive codec selection 개선을 여러 번 언급합니다. 특히 `enable_adaptive_codec_selection`이 incompressible data에서 `NONE`과 default codec 중 더 작은 쪽을 선택하도록 확장된 내용이 들어있습니다. [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

이건 장기적으로 disk footprint를 줄일 수 있지만, 단기적으로는 다음 테스트가 필요합니다.

* merge/mutation이 많은 테이블에서 merge CPU가 늘지
* 실제로 disk가 줄어드는지(데이터 특성에 따라 compressible 정도가 달라서, 개선이 체감이 없을 수 있음)

## 축 3) 운영(백업·롤링): 업그레이드 실패가 “쿼리 오류”가 아니라 “서버 부팅 실패”로 나타나는 지점들

### Backward Incompatible Change를 ‘업그레이드 전 점검’이 아니라 ‘회귀 테스트 항목’으로 바꾸기

26.10 changelog의 Backward Incompatible Change에는 운영 작업으로 흡수해야 하는 항목이 들어있습니다.

* analyzer 이전 분석 경로 제거, mixed cluster에서 오류 가능, `enable_analyzer` 사전 세팅 필요 [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)
* `system.metric_log`의 기본 schema가 bucketed로 바뀌고, upgrade 시 기존 테이블이 `metric_log_0`로 rename될 수 있으며, wide schema 유지 옵션(`schema_type`)이 제시됨 [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)
* `seccomp` filter가 기본적으로 더 강하게 적용될 수 있고, sandbox가 `seccomp` syscall을 거부하면 업그레이드 전에 설정을 바꾸라고 명시 [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

여기서 중요한 건 “문서를 읽고 조심하자”가 아닙니다. Backward Incompatible Change는 회귀 테스트 항목으로 바꿀 수 있습니다.

* metric_log schema 변경은 “내 대시보드/내 알람 쿼리가 깨지는가”를 테스트할 수 있는 케이스
* seccomp는 “내 배포 환경에서 server가 정상 기동되는가”를 테스트할 수 있는 케이스
* analyzer는 “mixed-version 분산 쿼리가 실패하는가”를 테스트할 수 있는 케이스

### 백업/복구는 업그레이드 작업의 일부로 포함시켜야 합니다

ClickHouse 공식 문서는 backup/restore를 다음처럼 못 박습니다.

* replication은 인간 실수나 소프트웨어 버그까지 막지 못한다
* restore를 실제로 해보지 않은 백업은 쓸모가 없다
* 정기적으로 spare cluster에 restore를 자동화하고 연습하라 [Backup and restore in ClickHouse](https://clickhouse.com/docs/concepts/features/backup-restore/overview)

또한 backup/restore 명령은 `ASYNC`가 가능하고, 동시 실행 제한을 config로 제어할 수 있으며, named collections를 통해 자격 증명을 숨길 수 있다고 명시합니다. [Backup and restore in ClickHouse](https://clickhouse.com/docs/concepts/features/backup-restore/overview)

그리고 문서에 “26.10 이전에는 row policies/settings profiles/quotas가 RESTORE 후 즉시 적용되지 않을 수 있어서 `SYSTEM RELOAD USERS`가 필요”하다는 문장이 들어있습니다. [Backup and restore in ClickHouse](https://clickhouse.com/docs/concepts/features/backup-restore/overview)

이건 26.10 업그레이드와 직접 연결됩니다.

* 업그레이드 전 restore drill을 하는 순간, access entity 복구가 실제로 적용되는지까지 검증해야 합니다.
* 특히 롤링 업그레이드 중 권한/정책이 어긋나면 “일부 노드에서만 쿼리 실패” 같은 형태로 지옥이 열립니다.

내 경우 롤링 업그레이드를 “패치도 릴리스처럼” 다루면서 contract test를 붙이는 쪽으로 운영을 굳혔는데, ClickHouse처럼 월간 릴리스가 큰 시스템은 더더욱 이 패턴이 맞습니다. [ClickHouse 패치도 릴리스처럼 다루는 롤링 업그레이드 설계](https://daewooki.github.io/posts/clickhouse-patch-rolling-upgrade-contract-tests/)

### 월간 릴리스 운영의 현실: 업그레이드 ‘창’은 짧아지고 검증 자동화는 더 필요해집니다

월간 릴리스 cadence에서는 “백포트 vs 업그레이드” 논쟁이 반복됩니다. systemd 같은 프로젝트도 결국 비슷한 결정을 요구하고, 실무 기준은 점점 “업그레이드를 전제로, 자동화로 리스크를 낮춘다”로 이동합니다. [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)

Discourse나 Grafana처럼 월간/패치 업그레이드를 운영 절차로 흡수한 사례도 결국 공통 결론은 같습니다.

* 검증은 checklist가 아니라 자동화된 테스트/벤치로 남아야 한다
* 업그레이드 창을 짧게 만들수록, “무엇을 테스트해야 하는지”가 더 명확해야 한다

관련해서 내가 이전에 정리한 운영 글들은 ClickHouse에도 그대로 적용됩니다.

* [Discourse 월간 릴리스에 맞춘 셀프호스팅 업그레이드 운영](https://daewooki.github.io/posts/discourse-monthly-release-selfhost-upgrade-automation/)
* [Grafana 패치 업그레이드 검증 자동화 설계](https://daewooki.github.io/posts/grafana-patch-upgrade-automation/)
* [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)

## 26.10용 회귀 테스트/벤치 계획: “내 워크로드”를 세 축으로 쪼개서 측정하기

여기부터는 기능 나열이 아니라, 26.10의 변화가 실제로 영향을 주는 지점을 테스트로 만들기 위한 설계입니다.

### 1) 프로덕션에서 쿼리 셋 추출: normalized query hash로 ‘패턴’ 단위로 잡습니다

ClickHouse는 `system.query_log` 기반으로 회귀 테스트 셋을 만드는 게 현실적입니다. 릴리스 블로그도 columns cache 예시에서 `system.query_log`를 직접 씁니다. [ClickHouse release 26.10](https://clickhouse.com/blog/clickhouse-release-26-10)

아래 SQL은 “최근 7일” 기준으로 패턴을 뽑는 형태입니다. 필드명은 환경에 따라 다를 수 있으니, 우선 `DESCRIBE TABLE system.query_log`로 확인하고 맞춥니다.

```sql
/* 1) 자주 실행되는 query pattern */
SELECT
  normalized_query_hash,
  anyHeavy(replaceRegexpAll(normalized_query, '\\s+', ' ')) AS sample_query,
  count() AS executions,
  quantile(0.50)(query_duration_ms) AS p50_ms,
  quantile(0.95)(query_duration_ms) AS p95_ms,
  quantile(0.99)(query_duration_ms) AS p99_ms,
  sum(read_rows) AS read_rows_sum,
  sum(read_bytes) AS read_bytes_sum,
  max(memory_usage) AS max_mem_bytes
FROM system.query_log
WHERE type = 'QueryFinish'
  AND event_date >= today() - 7
  AND is_initial_query = 1
  AND query_kind = 'Select'
  AND length(normalized_query) > 0
  AND NOT startsWith(normalized_query, '/* regression */')
GROUP BY normalized_query_hash
ORDER BY executions DESC
LIMIT 200;
```

이 결과를 그대로 테스트에 넣으면 안 됩니다. 분류가 필요합니다.

* JOIN 포함 여부
* `GROUP BY ... LIMIT` / `ORDER BY ... LIMIT` top-K 계열 여부
* LIKE/substring filter 포함 여부
* `IN (subquery)` 포함 여부
* distributed query 여부(예: `Distributed` 테이블, `clusterAllReplicas`, `remote`, `s3` 등)

26.10 변화점이 대부분 이 분류 축에 걸리기 때문에, 분류가 곧 테스트 계획이 됩니다.

### 2) A/B 환경: “버전 2개 + 동일 데이터 + 동일 설정”으로 고정합니다

현실적인 A/B의 핵심은 “데이터와 설정을 못 박는 것”입니다. 26.10은 캐시 관련 변화가 많아서, 설정이 흔들리면 숫자가 의미가 없습니다.

여기서는 Docker Compose 예시로 적습니다. 이미지 태그는 조직 표준에 맞춰 pin합니다(패키지 저장소의 stable build 번호를 그대로 쓰는 쪽이 사고가 적었습니다). [ClickHouse packages](https://packages.clickhouse.com/)

```yaml
services:
  ch_old:
    image: clickhouse/clickhouse-server:26.9
    ports:
      - "8123:8123"
      - "9000:9000"
    volumes:
      - ./volumes/ch_old:/var/lib/clickhouse
      - ./config/common.xml:/etc/clickhouse-server/config.d/common.xml:ro

  ch_new:
    image: clickhouse/clickhouse-server:26.10
    ports:
      - "18123:8123"
      - "19000:9000"
    volumes:
      - ./volumes/ch_new:/var/lib/clickhouse
      - ./config/common.xml:/etc/clickhouse-server/config.d/common.xml:ro
```

여기서 `common.xml`에 다음을 고정합니다.

* `max_threads`, `max_memory_usage` 같은 제한
* query log/profile event logging
* (가능하면) 동일한 filesystem cache 설정

특히 26.10은 query cache on disk가 들어오므로, A/B 둘 다 filesystem cache를 동일하게 구성하거나, 둘 다 꺼야 비교가 됩니다.

### 3) 현실적인 데이터셋: event 로그 + dimension table 조합으로 ‘조인/집계/필터’를 동시에 때립니다

장난감 예제는 26.10의 최적화를 건드리지 못합니다. 최소한 아래 조합이 필요합니다.

* 큰 fact 테이블(시간 파티셔닝 + LowCardinality dimension + String payload)
* 작은 dimension 테이블(조인 키, 패턴 매칭용 rule 테이블)

아래는 numbers 기반으로 “광고/로그 분석에서 흔한 형태”를 만드는 예시입니다.

```sql
CREATE DATABASE IF NOT EXISTS bench ENGINE = Atomic;

CREATE TABLE bench.events
(
  ts DateTime,
  event_date Date MATERIALIZED toDate(ts),
  user_id UInt64,
  project_id LowCardinality(String),
  country LowCardinality(String),
  path String,
  bytes UInt32
)
ENGINE = MergeTree
PARTITION BY event_date
ORDER BY (project_id, event_date, user_id, ts)
SETTINGS index_granularity = 8192;

-- dimension table: URL category rules (arbitrary JOIN condition용)
CREATE TABLE bench.path_rules
(
  pattern String,
  category LowCardinality(String)
)
ENGINE = TinyLog;

INSERT INTO bench.path_rules VALUES
('/docs/%', 'docs'),
('/blog/%', 'blog'),
('/pricing', 'pricing');
```

데이터 주입은 “적어도 수천만 row”는 되어야 합니다. 아래는 50M rows 예시입니다.

```sql
INSERT INTO bench.events
SELECT
  now() - (number % 86400) AS ts,
  (number % 1000000) AS user_id,
  ['p1','p2','p3','p4'][1 + (number % 4)] AS project_id,
  ['US','KR','JP','DE','FR'][1 + (number % 5)] AS country,
  if(number % 20 = 0,
     concat('/docs/', toString(number % 1000)),
     if(number % 33 = 0,
        concat('/blog/', toString(number % 5000)),
        concat('/x/', toString(number % 100000)))
  ) AS path,
  toUInt32(number % 65536) AS bytes
FROM numbers_mt(50000000);
```

### 4) 26.10 변화점을 직접 때리는 쿼리 묶음

아래 쿼리들은 “실무에서 실제로 자주 있는 형태”이면서, 26.10의 최적화 포인트를 명확히 건드립니다.

#### (A) LowCardinality GROUP BY: dictionary 기반 최적화 확인

```sql
/* regression: lc-group-by */
SELECT
  project_id, country,
  count() AS c,
  avg(bytes) AS avg_bytes
FROM bench.events
GROUP BY project_id, country
FORMAT Null;
```

#### (B) GROUP BY + ORDER BY + LIMIT: top-K dynamic filtering 확인

```sql
/* regression: group-by-topk */
SELECT
  user_id,
  count() AS c
FROM bench.events
WHERE project_id = 'p1'
GROUP BY user_id
ORDER BY c DESC
LIMIT 100;
```

여기서 중요한 건 “시간”이 아니라 “얼마나 덜 읽었는지”입니다. `read_rows/read_bytes`를 반드시 비교합니다.

#### (C) arbitrary JOIN condition: 기능 + 플래너 fallback 확인

```sql
/* regression: join-like */
SELECT
  r.category,
  sum(e.bytes) AS total_bytes
FROM bench.events e
LEFT JOIN bench.path_rules r
  ON e.path LIKE r.pattern
WHERE e.project_id = 'p1'
GROUP BY r.category
ORDER BY total_bytes DESC;
```

이 쿼리는 잘못 쓰면 비용이 크게 튑니다. 업그레이드 전/후에 EXPLAIN까지 포함해서 “계획이 왜 그렇게 나왔는지”를 남기는 게 맞습니다.

#### (D) LIKE scan pushdown: peak memory/throughput 변화 확인

```sql
/* regression: like-scan */
SELECT count()
FROM bench.events
WHERE path LIKE '%/docs/%';
```

#### (E) IN subquery set spill: 낮은 메모리 제한에서 완주하는지 확인

```sql
/* regression: in-subquery */
SELECT count()
FROM bench.events
WHERE user_id IN (
  SELECT user_id
  FROM bench.events
  WHERE project_id = 'p2'
  GROUP BY user_id
)
SETTINGS max_memory_usage = '2G';
```

### 5) 측정: system.query_log를 “성능 로그”가 아니라 “업그레이드 회귀 판정 데이터”로 씁니다

릴리스 블로그가 columns cache 측정에 사용한 패턴(로그 comment를 넣고 `system.query_log`에서 뽑기)은 그대로 회귀 테스트에 적용할 수 있습니다. [ClickHouse release 26.10](https://clickhouse.com/blog/clickhouse-release-26-10)

예를 들어 아래처럼 쿼리에 comment를 넣습니다.

```sql
/* regression: group-by-topk run=1 */
SELECT ...
SETTINGS log_queries = 1, log_profile_events = 1;
```

그리고 실행 후에 아래로 뽑습니다.

```sql
SYSTEM FLUSH LOGS;

SELECT
  query_start_time,
  query_duration_ms,
  read_rows,
  read_bytes,
  memory_usage,
  ProfileEvents['SelectedRows'] AS selected_rows,
  ProfileEvents['QueryConditionCacheHits'] AS qcc_hits,
  ProfileEvents['QueryConditionCacheMisses'] AS qcc_misses,
  ProfileEvents['ColumnsCacheHits'] AS col_cache_hits,
  ProfileEvents['ColumnsCacheMisses'] AS col_cache_misses
FROM system.query_log
WHERE type = 'QueryFinish'
  AND hasToken(lowerUTF8(query), 'regression:')
ORDER BY query_start_time DESC
LIMIT 200;
```

### 6) 리스크를 수치화하는 기준: “몇 % 느려지면 fail인가”를 쿼리군마다 다르게 잡습니다

26.10 같은 릴리스는 일부 쿼리는 빨라지고, 일부는 변동이 거의 없고, 일부는 악화합니다. 평균을 내면 아무 것도 보이지 않습니다.

내가 추천하는 방식은 쿼리군별로 다음을 정의하는 것입니다.

* correctness: 결과 row count / checksum 비교(가능하면)
* latency regression: p95 기준 +20% 같은 단일 기준 대신, **쿼리군별**로 다르게
  * dashboard/top-K: p95가 중요
  * batch ETL: wall time + read bytes가 중요
* resource regression: peak memory, spill 발생 여부, read bytes

그리고 fail 조건을 “하나라도 fail이면 업그레이드 중단”이 아니라, “업그레이드 리스크 점수”로 만들면 실제 운영에서 의사결정이 쉬워집니다.

예시 스코어(개념):

* correctness fail: +100
* p95 +50% 이상: +30
* read_bytes +100% 이상: +20
* peak memory +30% 이상: +10

이런 식으로 점수를 만들면, 26.10처럼 최적화가 많이 들어온 릴리스에서 “어떤 쿼리군이 위험을 주도하는지”가 바로 드러납니다.

## 반론과 회의론: 26.10의 성능 숫자를 그대로 믿으면 안 되는 이유

* 발표 자료의 수치는 특정 하드웨어/특정 데이터 분포/특정 설정에서 나옵니다. 내 데이터가 다르면 hash table 메모리 절감이 체감되지 않을 수 있고, 오히려 CPU 병목이 앞당겨질 수 있습니다. [ClickHouse: Release 26.10 Call](https://presentations.clickhouse.com/2026-release-26.10/)
* 캐시가 늘어날수록 벤치가 어려워집니다. query cache on disk, query condition cache, columns cache, filesystem cache, OS page cache가 동시에 존재하면 “왜 빨라졌는지”를 모르면 재현이 안 됩니다. 26.10은 특히 query cache가 재시작을 넘어서 지속될 수 있어서, 실험 설계가 더 까다롭습니다. [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)
* 최적화는 종종 edge-case bugfix와 같이 들어옵니다. changelog에는 query condition cache/top-K 관련 wrong result fix도 여럿 보입니다. 이런 릴리스에서는 correctness 회귀를 우선순위 1로 둬야 합니다. [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

## 앞으로 지켜볼 것: 26.10에서 ‘바로 켜기’보다 ‘테스트 재료로 쓰기’가 먼저인 기능들

* columns cache는 실험 기능으로 들어왔고, wide MergeTree part/UUID가 있는 DB 등 적용 조건이 명시되어 있습니다. 지금 당장 전면 도입하기보다, 내 워크로드의 “반복 읽기” 패턴에서 CPU가 병목인지 확인하는 도구로 쓰는 편이 낫습니다. [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)
* query cache on disk는 운영 측면에서 상당히 매력적이지만, 캐시 persistence는 항상 디버깅 비용을 동반합니다. “재시작하면 느려지는 시스템”이 “재시작해도 빠른 시스템”이 되는 대신, “왜 빨랐는지”가 불투명해질 수 있습니다. [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)
* merge join 병렬화(기본 ON)는 해당되는 워크로드에선 강력하지만, 해당 여부를 잘못 판단하면 벤치 시간을 낭비합니다. PK prefix JOIN 후보군을 먼저 찾아내는 게 순서입니다. [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)

## 지금 할 수 있는 일: 26.10 업그레이드를 “성공/실패”가 아니라 “수치”로 관리하기

1) `system.query_log`에서 쿼리 패턴을 뽑고, JOIN/top-K/LIKE/IN subquery 중심으로 분류합니다.
2) A/B 환경을 구성해 동일 데이터/동일 설정에서 (a) cold start, (b) warm cache, (c) restart 후를 나눠 측정합니다.
3) 26.10 Backward Incompatible Change 항목(metric_log schema, seccomp, analyzer mixed-version)을 회귀 테스트 케이스로 바꿉니다.
4) 결과는 “평균 latency”가 아니라 correctness/latency/read bytes/peak memory를 함께 보고, 쿼리군별 리스크 점수로 정리합니다.

26.10은 기능과 성능이 같이 들어온 달이라서 위험도 커졌지만, 동시에 ClickHouse 쪽에서 성능 수치와 관측 방법을 공식 자료로 충분히 제공했습니다. 이 조합은 업그레이드를 감으로 하는 단계를 끝내고, 내 워크로드 기준으로 리스크를 수치화해 결정을 내릴 수 있는 상태에 가깝습니다.

## 참고 자료

- [ClickHouse release 26.10](https://clickhouse.com/blog/clickhouse-release-26-10)
- [ClickHouse v26.10 Release Webinar](https://clickhouse.com/videos/clickhouse-release-26-10)
- [ClickHouse: Release 26.10 Call](https://presentations.clickhouse.com/2026-release-26.10/)
- [ClickHouse CHANGELOG.md](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/CHANGELOG.md)
- [Backup and restore in ClickHouse](https://clickhouse.com/docs/concepts/features/backup-restore/overview)
- [ClickHouse packages](https://packages.clickhouse.com/)
- [ClickHouse concurrency: how to size for user-facing analytics](https://clickhouse.com/resources/engineering/high-concurrency-sizing-user-analytics%5C)
- [ClickHouse 패치도 릴리스처럼 다루는 롤링 업그레이드 설계](https://daewooki.github.io/posts/clickhouse-patch-rolling-upgrade-contract-tests/)
- [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)
- [Discourse 월간 릴리스에 맞춘 셀프호스팅 업그레이드 운영](https://daewooki.github.io/posts/discourse-monthly-release-selfhost-upgrade-automation/)
- [Grafana 패치 업그레이드 검증 자동화 설계](https://daewooki.github.io/posts/grafana-patch-upgrade-automation/)
- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
