---
title: "PostgreSQL 19 Beta 4: 확장·플랜 회귀·업그레이드 리허설"
description: "PostgreSQL 19 Beta 4에서 확장 호환성, 쿼리 플랜 회귀, pg_upgrade 리허설을 베타 기간에 끝내는 운영 플랜 정리."
date: 2026-09-30 13:59:28 +0900
categories: ["News", "Database"]
tags: ["postgresql", "beta-testing", "extensions", "query-regression", "pg-upgrade", "ci"]
render_with_liquid: false
---

## 2026-09-24 PostgreSQL 19 Beta 4 공개: 운영 관점에서 봐야 하는 포인트

PostgreSQL Global Development Group이 **2026-09-24**에 [PostgreSQL 19 Beta 4 Released!](https://www.postgresql.org/about/news/postgresql-19-beta-4-released-3386/)를 게시했습니다.[^1]  
오늘은 KST 기준 **2026-09-30**이고, 발표문에는 다음 단계가 **early October**의 release candidate(RC)이며, 테스트 결과에 따라 GA도 10월에 나올 수 있다고 적혀 있습니다.[^1]  
PostgreSQL 프로젝트 로드맵도 “next major release is planned for October 2026”로 정리되어 있어서, 달력 상으로도 지금은 베타 막바지 구간입니다. [PostgreSQL Roadmap](https://www.postgresql.org/developer/roadmap/).[^2]

운영팀/플랫폼팀 입장에서 중요한 건 “Beta 4에 어떤 기능이 추가되었나”보다, **GA 직전에 바뀌는 것들이 실제 운영 비용(장애, 롤백, 핫픽스, 야간 대응)을 얼마나 유발하느냐**입니다.

Beta 4 발표문에는 “several features reverted”가 명시되어 있고, 실제로 SQL/PGQ(property graph query), 온라인 데이터 체크섬 enable/disable, `FOR PORTION OF` 기반 temporal update/delete, partition merge/split 같은 큰 덩어리들이 빠졌습니다.[^1]  
이건 기능 소개 글에서는 아쉬움으로 소비되기 쉬운데, 운영 관점에서는 오히려 신호가 명확합니다.

- 베타 후반부에 들어오면, “크게 넣고 다듬기”보다 “빼고 안정화하기”가 실제로 벌어집니다.[^1]
- 따라서 베타는 기능 구경이 아니라 **회귀를 미리 발견해 비용을 선결제하는 기간**입니다.

그리고 베타는 feature-frozen이며 production 용도가 아니라는 전제가 공식 문서에 반복됩니다. [PostgreSQL Beta Information](https://www.postgresql.org/developer/beta/).[^3]  
즉, 운영팀이 베타에서 해야 하는 일은 “베타를 운영에 올려보기”가 아니라 “GA를 운영에 올릴 때 발생할 일을 베타에서 끝내기”입니다.

## Beta 4가 특히 ‘검증 윈도우’가 되는 이유

베타가 Beta 1, 2, 3… 순서대로 계속 나오면, 체감상은 “아직 베타니까 나중에”가 되기 쉽습니다. 그런데 Beta 4는 성격이 다릅니다.

1) 공식 발표문 자체가 다음 릴리스가 RC라고 못 박습니다.[^1]  
2) 베타 후반에는 open item을 닫기 위해 revert가 실제로 일어납니다. Beta 4에서 이미 큰 revert가 발생했습니다.[^1]  
3) Release Management 쪽 커뮤니케이션도 “Beta 4 release date” 공지에서 commit freeze(2026-09-19 12:00 UTC)를 언급할 정도로, 릴리스 프로세스가 촘촘해집니다. [pgsql-hackers 메일](https://www.postgresql.org/message-id/f515cc05-67ee-4295-bc79-41c48ce2589d%40postgresql.org).[^4]

UTC 2026-09-19 12:00는 KST로는 2026-09-19 21:00입니다. 이 시점 이후에는 “깨진 걸 고치거나 빼는 것” 외의 변화는 더 어려워집니다. 운영팀 입장에서는 이 타이밍이 곧 “계획했던 검증을 실제로 할 수 있는 마지막 구간”에 가깝습니다.

내가 이 시점에 확장/ORM/쿼리 회귀 테스트를 강조하는 이유는 단순합니다.

- 확장과 ORM은 대부분 “내가 만든 코드가 아니라 남이 만든 코드”이고
- 쿼리 플랜 회귀는 대부분 “기능 테스트가 아니라 데이터 분포와 통계, 파라미터 값에서 터지는 성질”이라
- GA 직전/직후로 밀리면, 장애 대응과 같은 시간대에 겹치면서 비용이 기하급수로 커집니다.

예전에 [PostgreSQL 19 Beta 3 검증 윈도우: 확장·호환성·회귀](https://daewooki.github.io/posts/postgresql-19-beta3-test-window/)에서 큰 그림을 한 번 잡았는데, Beta 4에서는 그걸 “실제로 닫는” 쪽으로 바뀝니다. 반복 설명은 생략하고, 이번에는 운영팀이 당장 실행할 수 있는 플랜에만 집중합니다.

## 베타 기간에 끝내야 하는 3가지: 확장, 플랜, 업그레이드 리허설

플랫폼팀 백로그에서 PostgreSQL 메이저 업그레이드는 보통 이렇게 분해됩니다.

- (A) extensions 호환성
- (B) ORM/애플리케이션 레이어(드라이버 포함) 호환성
- (C) 쿼리 성능/플랜 회귀
- (D) 업그레이드 runbook(절차, 롤백, 다운타임 산정)

여기서 (B)는 팀 구조에 따라 앱팀이 가져갈 수 있습니다. 하지만 (A)(C)(D)는 플랫폼/DBA가 끝까지 책임지는 편이 현실적입니다. 

특히 (A)와 (D)는 `pg_upgrade` 경로를 택하는 순간 강하게 결합됩니다. `pg_upgrade`는 외부 모듈의 바이너리 호환성을 “중요하지만 자동으로 체크할 수 없다”고 문서에서 못 박습니다. [pg_upgrade 문서(18)](https://www.postgresql.org/docs/18/pgupgrade.html).[^5]  
즉, extensions 검증은 옵션이 아니라 선행조건입니다.

## extensions 호환성: “SQL-only vs C-extension vs preload”로 쪼개서 다룬다

운영에서 extensions는 “사용 중인지 아닌지”만 보지 말고, 실제로는 3종류로 분리해서 다루는 편이 낫습니다.

### 1) SQL-only extension: 업그레이드 스크립트와 search_path가 핵심

SQL-only extension은 보통 빌드가 필요 없어서 만만하게 보입니다. 그런데 운영에서 사고 나는 지점은 다른 곳입니다.

- extension update 스크립트가 누락되어 `ALTER EXTENSION ... UPDATE`가 막히는 경우
- `MODULE_PATHNAME` 같은 관례를 따르지 않아 경로가 하드코딩된 경우
- extension이 만드는 object들이 `search_path`/권한/기본 schema 가정에 묶여 있는 경우

이 부분은 [Packaging Related Objects into an Extension](https://www.postgresql.org/docs/17/extend-extensions.html) 문서의 “control file/versioned control file” 규칙을 기준으로 점검하는 게 빠릅니다.[^6]

운영팀 체크리스트는 단순합니다.

- `pg_extension`에 설치된 extension 목록과 버전 스냅샷을 뜬다.
- 새 버전에서 `ALTER EXTENSION ... UPDATE`가 가능한지와, 업데이트 후 object/권한이 유지되는지 확인한다.

### 2) C-extension: “컴파일 성공”이 끝이 아니라 시작이다

C-extension은 메이저 업그레이드에서 사실상 “다시 빌드/재배포”입니다. 그리고 `pg_upgrade`는 외부 모듈 ABI를 스스로 검증할 수 없다고 합니다. [pg_upgrade 문서(18)](https://www.postgresql.org/docs/18/pgupgrade.html).[^5]

그래서 접근을 이렇게 잡는 편이 낫습니다.

- 1단계: **빌드 매트릭스**를 만든다.
  - (old) 현재 운영 major 버전 + (old) 현재 extension 패키지
  - (new) v19 beta4 + (new) extension 빌드
- 2단계: “동작”을 보되, 최소한 다음은 자동화한다.
  - extension이 제공하는 SQL regression(test 스크립트)이 있으면 반드시 돌린다.
  - 없으면, 실제 운영에서 쓰는 기능(함수/연산자/인덱스/타입)을 호출하는 smoke test를 만든다.

내 경험상, C-extension은 실패 형태가 다양합니다.

- 빌드는 되는데 로딩에서 `undefined symbol`로 터짐
- 로딩은 되는데 특정 쿼리에서 segfault
- 특정 데이터 타입/인덱스 조합에서만 잘못된 결과

그래서 베타 기간에는 “빌드만 확인” 같은 가벼운 종료조건을 두면 결국 GA 이후에 돈을 내게 됩니다.

### 3) shared_preload_libraries 계열: 업그레이드 리허설에 반드시 포함

`shared_preload_libraries`에 들어가는 확장(예: `pg_stat_statements` 같은 모듈)은 “DB가 뜨기 전에 로드”됩니다. 즉, 호환성 문제가 있으면 DB 자체가 안 뜨는 사고로 연결됩니다.

Beta 4 변경 사항에 `pg_plan_advice` 관련 validation fix가 포함되어 있는 점을 보면, v19에서는 planner 관련 모듈이 추가되는 흐름입니다. Beta 4 발표문에 `pg_plan_advice` 관련 fix가 언급됩니다.[^1]  
릴리스 노트에도 `pg_plan_advice` 모듈 추가가 명시돼 있습니다. [PostgreSQL 19 Release Notes](https://www.postgresql.org/docs/19/release-19.html).[^7]  

이 부류는 업그레이드 리허설에서 “postmaster 기동부터” 재현해야 합니다.

- 새 major 버전에서 서버가 기동되는가
- preload 순서에 민감한 조합이 있는가
- 설정 파라미터가 rename/deprecate되진 않았는가

## ORM/드라이버 호환성: 기능 추가보다 ‘행동 변화’를 본다

ORM 테스트를 “새 문법을 써볼까?”로 접근하면 우선순위가 엇나갑니다. 베타 기간의 목적은 다음입니다.

- (1) 현재 애플리케이션이 생성하는 SQL이 v19에서 같은 결과를 내는가
- (2) 같은 SQL이라도 플랜이 바뀌어 latency/CPU가 튀지 않는가
- (3) 마이그레이션 도구가 DDL을 끝까지 수행하는가(특히 lock/timeout)

PostgreSQL 19 릴리스 노트에는 query command, utility command 변화가 많고, Beta 4 공지에도 `WAIT FOR`, `REPACK`, foreign key check 성능 개선 등 “운영 행동 변화”가 들어 있습니다.[^1]

ORM/드라이버에서 실무적으로 걸리는 지점은 보통 이쪽입니다.

- prepared statement 재사용 패턴이 바뀌면서 generic/custom plan 선택이 달라지는 케이스
- 트랜잭션 격리 수준에서 error message/behavior가 달라져 retry 로직이 어긋나는 케이스
- DDL이 더 공격적으로 lock을 잡는 쪽으로 변한 것처럼 보이는 케이스(실제로는 planner/lock queue 상호작용)

테스트는 “ORM 단위 테스트”가 아니라 “운영 트래픽 형태”로 가져오는 게 맞습니다.

- 배치/cron이 만들어내는 대량 update/delete
- OLTP 트래픽이 만들어내는 짧은 트랜잭션
- 읽기 전용 트래픽이 만드는 join-heavy 쿼리

이건 앱팀과 경계를 잘 정해야 합니다. 플랫폼팀은 “DB 업그레이드로 인해 앱이 깨지는 비용”을 줄여야 하고, 앱팀은 “수정이 필요한 지점이 어디인지”를 빨리 알아야 합니다. 그래서 베타 기간에는 **호환성 문제를 ‘버그 리포트 가능한 형태’로 쪼개는 작업**이 가치가 큽니다.

## 쿼리 플랜 회귀: EXPLAIN을 모으는 게 아니라 ‘재현 가능한 비교’를 만든다

플랜 회귀는 가볍게 시작하면 끝이 없습니다. 반대로, 비교 단위를 잘 잡으면 생각보다 빠르게 닫힙니다.

내가 잡는 최소 단위는 이것입니다.

- 동일 데이터(스냅샷)
- 동일 설정(가능한 한)
- 동일 쿼리(파라미터 포함)
- 동일 방식으로 `EXPLAIN (FORMAT JSON)` 수집
- v18(또는 현재 운영 버전) vs v19 beta4 비교

그리고 “플랜이 바뀌었다”는 사실 자체보다 중요한 것은 “업무적으로 문제를 만드는 바뀜”입니다.

- latency가 SLA를 넘는가
- CPU가 튀는가
- buffer hit/read 패턴이 변했는가
- row estimate 오차가 커졌는가

### pg_plan_advice는 ‘플랜 고정’ 도구가 아니라 ‘회귀 분리’ 도구로 쓴다

PostgreSQL 19에는 `pg_plan_advice` 모듈이 들어갑니다. 릴리스 노트에 추가가 명시돼 있고, 문서도 올라와 있습니다. [pg_plan_advice 문서](https://www.postgresql.org/docs/19/pgplanadvice.html).[^8]  

이걸 운영에서 곧바로 “hint 기능”처럼 쓰는 건 조심스럽습니다. 문서 자체도 “overriding its judgment can easily backfire”로 경고합니다.[^8]  

그럼에도 베타 기간에는 이 모듈이 꽤 유용한데, 이유는 회귀를 분리할 수 있기 때문입니다.

- v19에서 플랜이 바뀐 쿼리 A가 느려졌다
- 원인이 planner의 선택인지, 통계/설정/캐시/IO인지 불명확하다

이때 `pg_plan_advice`로 “이전 플랜을 강제로 재현”해 보면, 원인을 나눌 수 있습니다.

- 이전 플랜을 강제했더니 빨라진다 → planner 선택 변화가 원인일 가능성이 크다
- 이전 플랜을 강제해도 느리다 → executor/IO/캐시/다른 변화일 가능성이 크다

베타 기간에는 이런 분리 작업이 특히 중요합니다. GA 직후에는 “느려졌다”만 남고, 원인을 쪼개는 시간 자체가 줄어듭니다.

### autovacuum scoring 변화는 플랜 회귀처럼 보이는 운영 변화로 이어질 수 있다

PostgreSQL 19 릴리스 노트에는 autovacuum prioritization에 scoring system이 들어갔다고 명시돼 있습니다. [PostgreSQL 19 Release Notes](https://www.postgresql.org/docs/19/release-19.html).[^7]  
그리고 v19 문서에는 “테이블을 점수로 정렬해서 처리하며, weight 파라미터를 0.0으로 두면 이전 전략으로 되돌릴 수 있다”는 설명이 상세히 있습니다. [Routine Vacuuming: Autovacuum Prioritization](https://www.postgresql.org/docs/19/routine-vacuuming.html).[^9]  
관련 weight 파라미터도 runtime config에 정리돼 있습니다. [Vacuuming 설정](https://www.postgresql.org/docs/19/runtime-config-vacuum.html).[^10]  

이 변화는 “특정 쿼리 플랜”의 회귀가 아니라, 다음 형태로 비용이 나옵니다.

- vacuum/analyze 타이밍이 달라져서 통계가 늦게 갱신된다
- 그 결과, 플랜이 흔들리는 것처럼 보인다
- 실제로는 planner 문제가 아니라 통계 freshness 문제다

베타 기간에 여기까지 만져보자는 얘기가 아닙니다. 다만, 플랜 회귀 분석 중에 통계/autoanalyze가 변수로 보이면 v19의 autovacuum scoring 변경을 원인 후보에 올려놓는 게 낫습니다. 

또한 v19에는 autovacuum score를 보여주는 `pg_stat_autovacuum_scores` 뷰가 문서화돼 있습니다. [pg_stat_autovacuum_scores 문서](https://www.postgresql.org/docs/19/monitoring-stats.html).[^11]

## pg_upgrade 리허설: “성공”이 아니라 “반복 가능성”을 산출물로 만든다

Beta 4 발표문은 “이전 버전에서 Beta 4로 업그레이드하려면 메이저 업그레이드와 동일한 전략(`pg_upgrade` 또는 dump/restore)이 필요”하다고 못 박습니다.[^1]  
즉, 베타 테스트의 한 축은 기능 확인이 아니라 업그레이드 경로 검증입니다.

여기서 흔히 하는 실수가 있습니다.

- 한 번 성공하면 끝이라고 착각한다
- 실제로는 사람/환경/옵션이 바뀌면 재현이 안 된다

운영에서 필요한 건 “성공 경험”이 아니라 runbook입니다.

- 어떤 명령을 어떤 순서로 실행했는가
- 실패하면 어떤 로그를 어디서 수집하는가
- 확장/설정/권한/리소스(디스크)에서 전제조건이 무엇인가
- 다운타임을 어떻게 산정할 것인가

그리고 `pg_upgrade`는 한 문장이 꽤 중요합니다.

- `pg_upgrade`는 외부 모듈이 바이너리 호환인지 확인할 수 없다.[^5]

이 한 줄 때문에, 업그레이드 리허설에는 반드시 extensions 설치/업데이트 단계가 포함돼야 합니다.

### 리허설 환경을 “운영과 닮게” 만들 때의 최소 조건

- locale/collation을 운영과 맞춘다(가능하면 동일 OS 이미지)
- `shared_preload_libraries` 포함 주요 GUC를 동일하게 둔다
- extension 설치 목록을 동일하게 둔다
- 애플리케이션이 사용하는 role/privilege 모델을 반영한다

이 중에서 locale/collation은 특히 까다롭습니다. Beta 4 변경사항에 `LC_COLLATE` 관련 revert가 들어가 있을 정도로, 릴리스 막바지에까지 영향을 주는 영역입니다.[^1]

### pg_upgrade --check를 CI에 넣는 이유

리허설을 매번 풀로 돌리는 건 비쌉니다. 하지만 `--check`는 비용 대비 효과가 좋습니다.

- 클러스터 간 컴파일 옵션/호환성 조건이 안 맞으면 초기에 걸러진다
- extension update 필요 여부도 리포트로 남길 수 있다(문서에도 update 스크립트 생성 언급이 있습니다). [pg_upgrade 문서(16)](https://www.postgresql.org/docs/16/pgupgrade.html).[^12]

아래는 로컬/CI에서 반복 가능한 리허설 뼈대입니다.

```bash
#!/usr/bin/env bash
set -euo pipefail

# 예시 경로. 패키지 설치/소스 빌드 방식에 맞게 조정.
OLD_BIN=/usr/lib/postgresql/18/bin
NEW_BIN=/opt/pgsql-19beta4/bin

OLD_DATA=/var/lib/postgresql/18/main
NEW_DATA=/var/lib/postgresql/19beta4/main

# 1) NEW initdb (운영과 동일한 locale/collation을 맞추는 게 핵심)
# 실제 운영에서는 initdb 옵션(encoding, locale provider 등)을 명시적으로 고정하는 편이 안전합니다.

# 2) check-only
$NEW_BIN/pg_upgrade \
  --old-bindir="$OLD_BIN" \
  --new-bindir="$NEW_BIN" \
  --old-datadir="$OLD_DATA" \
  --new-datadir="$NEW_DATA" \
  --check

# 3) 결과물(예: extension update script, analyze script 등)을 아티팩트로 보관
ls -al
```

이 스크립트는 “업그레이드가 된다/안 된다”만 보는 게 아니라, 팀이 반복 실행할 수 있는 형태로 만드는 데 의미가 있습니다.

## Beta 4에서 같이 보는 게 좋은 변경들: REPACK, WAIT FOR

이번 글의 중심은 “검증 플랜”이지만, Beta 4가 고치는 항목들을 보면 왜 지금이 회귀 테스트 윈도우인지가 더 선명해집니다.

Beta 4 공지에서 다음이 명시적으로 언급됩니다.

- `REPACK` 관련 crash/invalid index/materialized view/permission/error-reporting fix들[^1]
- `WAIT FOR` 관련 deadlock fix와 isolation error reporting 개선[^1]

이 둘은 운영 현장에서 “새 기능”이라기보다 “운영 명령/동작의 신뢰성”에 가깝습니다.

### REPACK: VACUUM FULL/CLUSTER와 교체되는 운영 루틴의 변화

v19 문서에는 `REPACK` SQL command가 정식으로 들어가 있고, `CONCURRENTLY` 옵션과 내부 동작(논리 디코딩을 사용해 변경분을 적용하고 swap 시점에만 강한 락)을 설명합니다. [REPACK 문서](https://www.postgresql.org/docs/19/sql-repack.html).[^13]  

운영팀 관점에서 중요한 포인트는 기능 자체가 아니라 위험 프로파일입니다.

- `CONCURRENTLY`는 락 홀드 시간을 줄이지만, 그만큼 내부적으로 복잡한 경로를 탑니다(문서도 MVCC-safe가 아니라고 경고).[^13]
- “베타 후반에 crash/incorrect behavior fix가 들어간다”는 건, 곧 GA 직후까지도 edge case가 남아 있을 가능성이 있다는 뜻입니다.[^1]

따라서 베타 기간에 할 일은 “REPACK을 도입할지”가 아니라, 다음을 확인하는 쪽입니다.

- 기존 운영 루틴이 `VACUUM FULL`/`CLUSTER`에 의존하고 있는가
- 그 루틴이 v19에서 어떤 경로로 치환되는가
- `REPACK` 적용 대상 테이블에서 문서에 나온 제약(예: `CONCURRENTLY` 불가 조건)에 걸리는 게 있는가[^13]

### WAIT FOR: read-your-writes류 요구사항을 SQL로 끌어올린다

v19에는 WAL LSN을 기준으로 기다리는 `WAIT FOR`가 들어갔고, 문서에는 mode(standby_replay/write/flush, primary_flush)와 timeout/no_throw 같은 옵션이 있습니다. [WAIT FOR 문서](https://www.postgresql.org/docs/19/sql-wait.html).[^14]  

운영팀 관점에서는 다음이 포인트입니다.

- 앱이 “replica 읽기”를 하는 구조에서, 대기/타임아웃/에러 처리 패턴이 바뀔 수 있다
- deadlock fix가 베타 후반에 들어간다는 사실은, 앱/프록시/커넥션풀과 결합된 실제 워크로드에서 확인할 가치가 있다는 뜻이다[^1]

WAIT FOR 자체를 당장 서비스 코드에 넣지 않더라도, 베타 기간의 회귀 테스트에서는 “새로운 동기화/대기 경로가 들어오면서 lock/wait 그래프가 달라질 수 있다” 정도는 염두에 두는 편이 낫습니다.

## CI에서 굴리는 현실적인 회귀 테스트 파이프라인: nightly + 3단계 게이트

베타 기간에 사람 손으로 체크리스트를 실행하면 두 가지 문제가 생깁니다.

- 누락이 생긴다
- RC 직전에 시간이 없다

그래서 베타 기간에 가장 가치 있는 산출물은 “테스트 자동화”입니다. PostgreSQL도 베타 테스트를 스크립팅해서 재현 가능하게 만들라고 안내합니다. [HowToBetaTest](https://wiki.postgresql.org/wiki/HowToBetaTest).[^15]

내가 추천하는(이라기보다 내가 운영에서 채택하는) 형태는 다음 3게이트입니다.

- Gate 1: 빌드/부팅/extension load
- Gate 2: pg_upgrade --check
- Gate 3: 핵심 쿼리 플랜/성능 회귀(샘플 데이터 기반)

### Gate 1: Postgres 19 beta4 빌드 + extension build

아래는 Ubuntu 계열 러너에서 소스 빌드하는 뼈대입니다. (조직이 패키지/컨테이너를 어떻게 쓰는지에 따라 바뀝니다.)

```yaml
# .github/workflows/pg19-beta4-regression.yml
name: pg19-beta4-regression

on:
  schedule:
    - cron: "0 18 * * *"   # KST 03:00
  workflow_dispatch: {}

jobs:
  build-and-smoke:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - name: Install build deps
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            build-essential clang llvm \
            bison flex \
            libreadline-dev zlib1g-dev libssl-dev \
            libxml2-dev libxslt1-dev libicu-dev \
            liblz4-dev libzstd-dev \
            python3 python3-venv

      - name: Download PostgreSQL 19 Beta 4
        run: |
          # 실제 조직에서는 아카이브 URL을 고정하거나, 내부 mirror를 둡니다.
          # 여기서는 "공식 다운로드 링크"가 있는 발표문을 기준으로 가져오는 방식만 제시합니다.
          echo "See: https://www.postgresql.org/about/news/postgresql-19-beta-4-released-3386/"

      - name: Configure & build (example)
        run: |
          # 소스 tarball을 받아서 풀고 빌드하는 구간은 조직별로 다릅니다.
          # 핵심은 old/new 모두 동일한 옵션 체계를 문서화하는 것입니다.
          echo "Build steps omitted: wire this to your internal source fetching"

      - name: Initdb & start
        run: |
          echo "Initdb/start omitted: wire this to your CI environment"
```

위 YAML은 “완성된 워크플로”가 아니라, 운영팀이 반드시 고정해야 하는 축(의존성/빌드옵션/실행 옵션)을 CI로 끌고 들어오는 용도입니다. 베타 기간에는 이걸 조직의 표준 템플릿으로 굳히는 편이 낫습니다.

### Gate 2: pg_upgrade --check를 CI에서 매일 돌린다

`pg_upgrade`는 베타/스냅샷 릴리스도 지원한다고 문서에 명시돼 있습니다. [pg_upgrade 문서(18)](https://www.postgresql.org/docs/18/pgupgrade.html).[^5]  
즉, “GA 나오면 해보자”가 아니라 “베타에서 자동화해두자”가 맞습니다.

구현은 단순합니다.

- 운영과 유사한 데이터 스냅샷을 하루 1회 CI가 받아온다(보안/개인정보는 조직 정책대로)
- old cluster를 띄우고 new cluster를 initdb 한다
- `pg_upgrade --check`를 돌린다
- 실패하면 즉시 알람을 건다

이 단계의 장점은, 실패가 대부분 “확장/설정/바이너리 호환”으로 수렴해서 원인 분석이 빠르다는 겁니다.

### Gate 3: 플랜/성능 회귀는 “top query set”으로만 좁힌다

전체 쿼리를 다 재현하는 건 불가능합니다. 대신 “운영 비용을 만드는 쿼리”만 잘라냅니다.

- `pg_stat_statements` 같은 관측 지표로 top N을 추린다
- 그 쿼리들의 파라미터 대표값(혹은 바인딩 값 샘플)을 재현 가능한 fixture로 만든다
- 두 버전에서 EXPLAIN JSON을 떠서 diff한다

v19 릴리스 노트에는 `pg_stat_statements` 개선도 들어 있습니다. [PostgreSQL 19 Release Notes](https://www.postgresql.org/docs/19/release-19.html).[^7]  
이런 변화는 “관측 데이터가 달라진다”로도 나타날 수 있어서, 회귀 테스트와 함께 움직이는 편이 낫습니다.

아래는 두 데이터베이스(예: v18, v19 beta4)에 동일 쿼리를 날리고 EXPLAIN JSON을 저장한 뒤, 상위 필드 몇 개만 비교해 차이를 리포트하는 Python 스크립트 예시입니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install "psycopg[binary]==3.2.9"

# 예:
#   export PG18_DSN='postgresql://...'
#   export PG19_DSN='postgresql://...'
python tools/plan_diff.py --query-file queries/top.sql --out-dir out
```

```python
# tools/plan_diff.py
import argparse
import json
import os
from pathlib import Path

import psycopg

def explain_json(conn, sql: str):
    with conn.cursor() as cur:
        cur.execute("EXPLAIN (FORMAT JSON) " + sql)
        row = cur.fetchone()
        return row[0][0]  # list[dict] 형태

def plan_fingerprint(plan: dict) -> dict:
    # 운영용으로는 더 정교한 fingerprint가 필요하지만, 베타 윈도우에서는
    # 우선 "큰 형태 변화"를 잡는 게 목표입니다.
    p = plan.get("Plan", {})
    return {
        "Node Type": p.get("Node Type"),
        "Join Type": p.get("Join Type"),
        "Total Cost": p.get("Total Cost"),
        "Plan Rows": p.get("Plan Rows"),
        "Relation Name": p.get("Relation Name"),
        "Index Name": p.get("Index Name"),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query-file", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    dsn18 = os.environ["PG18_DSN"]
    dsn19 = os.environ["PG19_DSN"]

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    sql_text = Path(args.query_file).read_text(encoding="utf-8")
    queries = [q.strip() for q in sql_text.split(";\n") if q.strip()]

    with psycopg.connect(dsn18) as c18, psycopg.connect(dsn19) as c19:
        report = []
        for i, q in enumerate(queries, start=1):
            e18 = explain_json(c18, q)
            e19 = explain_json(c19, q)

            fp18 = plan_fingerprint(e18)
            fp19 = plan_fingerprint(e19)

            changed = fp18 != fp19
            report.append({
                "id": i,
                "changed": changed,
                "fp18": fp18,
                "fp19": fp19,
                "query": q,
            })

            (out / f"q{i:03d}.pg18.json").write_text(json.dumps(e18, indent=2), encoding="utf-8")
            (out / f"q{i:03d}.pg19.json").write_text(json.dumps(e19, indent=2), encoding="utf-8")

        (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

        # 콘솔 요약
        total = len(report)
        diff = sum(1 for r in report if r["changed"])
        print(f"plans changed: {diff}/{total}")

if __name__ == "__main__":
    main()
```

예상 출력은 대략 이런 형태입니다.

```text
plans changed: 7/40
```

이 단계에서 중요한 건 diff 개수 자체가 아니라, “변한 7개가 운영 비용을 만드는 7개인지”를 빠르게 식별하는 루프를 만드는 겁니다.

## 반론과 회의론: 베타에 시간을 쓰는 게 과한가

운영 조직에서 실제로 나오는 반론은 보통 이 셋입니다.

### 1) 베타는 어차피 바뀐다

맞습니다. 그리고 PostgreSQL도 베타 기간에는 minor behavior/API가 바뀌거나 기능이 제거될 수 있다고 공식적으로 경고합니다. [PostgreSQL Beta Information](https://www.postgresql.org/developer/beta/).[^3]  
Beta 4에서 실제로 기능이 빠졌습니다.[^1]  

하지만 운영 관점에서 보면 “바뀌기 때문에” 베타에서 하는 게 이득입니다.

- 바뀌는 구간에서 extensions/플랜/업그레이드 절차가 흔들리는 지점을 잡아내면
- GA에서는 그 흔들림이 줄어듭니다

베타에서 기능이 빠지는 사건은 “테스트가 헛수고”가 아니라 “테스트 우선순위가 안정화로 수렴하고 있다”는 신호에 가깝습니다.

### 2) 어차피 RC에서 한 번 더 해야 한다

RC는 “베타보다 GA에 가깝다”는 점에서 반복 테스트가 필요합니다. PostgreSQL도 RC는 원칙적으로 GA와 동일해야 하지만 추가 변경이 있을 수 있다고 적습니다. [PostgreSQL Beta Information](https://www.postgresql.org/developer/beta/).[^3]  

그래도 Beta 4에서 해두면 RC에서 줄어드는 일이 큽니다.

- 확장 빌드/패키징 문제
- pg_upgrade 옵션/절차 문제
- 특정 쿼리의 플랜 급변 문제

RC에서 다시 보는 건 “변경분 확인”이 되지만, Beta 4를 건너뛰면 RC가 “처음 보는 문제 디버깅”이 됩니다.

### 3) GA는 어차피 .1, .2에서 안정화된다

PostgreSQL은 메이저 릴리스 후에도 분기별 minor release로 버그픽스를 제공합니다. [Versioning Policy](https://www.postgresql.org/support/versioning/).[^16]  

그런데 운영 비용은 버그 자체보다 “버그를 맞는 시점”에서 결정됩니다.

- GA 직후에 맞으면, 업그레이드 프로젝트 전체가 흔들립니다.
- minor release까지 기다리면, 이미 결정된 업그레이드 일정과 충돌합니다.

그래서 플랫폼팀은 베타에서 최대한 “알아야 할 것을 일찍 알아야” 합니다.

## 앞으로 지켜볼 것: open items, RC, 그리고 revert의 여파

베타 후반부에서는 공식 릴리스 노트보다 “open items”가 더 실전적일 때가 많습니다. PostgreSQL 위키에는 PostgreSQL 19 Open Items 페이지가 있고, 중요한 일정(Feature Freeze, Beta 일정 등)을 같이 적어둡니다. [PostgreSQL 19 Open Items](https://wiki.postgresql.org/wiki/PostgreSQL_19_Open_Items).[^17]  

내가 베타 후반에 보는 축은 이렇습니다.

- RC1 날짜가 확정되는가(공식 발표문에는 early October로만 표현)[^1]
- Beta 4에서 revert된 기능들이 릴리스 노트에서 어떻게 정리되는가[^1]
- 회귀를 유발할 수 있는 모듈/명령(예: `REPACK`, `WAIT FOR`, autovacuum scoring) 관련 fix가 RC에 더 들어오는가[^1]

그리고 “revert의 여파”는 코드가 아니라 사람 쪽에도 옵니다.

- 어떤 팀은 SQL/PGQ 같은 기능을 전제로 로드맵을 잡아놨을 수 있습니다.
- Beta 4에서 빠졌다는 건, 그 로드맵을 메이저 19가 아니라 이후로 미루라는 의미입니다.[^1]

운영팀은 이런 의사결정이 “기능팀의 아쉬움”으로 남지 않게, 업그레이드 범위/리스크를 다시 정의해야 합니다.

## 지금 시점의 결론: Beta 4는 ‘운영 비용을 줄이는 마지막 넓은 창’이다

Beta 4(2026-09-24)에서 RC(2026-10월 초 예상)까지는 길지 않습니다.[^1]  
이 구간에서 플랫폼팀이 얻을 수 있는 실질적 이득은 세 가지로 정리됩니다.

1) extensions 호환성 문제를 GA 전에 발견하고, 빌드/패키징/설치 절차를 고정한다. (`pg_upgrade`는 외부 모듈 호환을 자동 검증하지 못한다.)[^5]  
2) top query set 기준으로 플랜/성능 회귀를 조기에 분리하고, 필요한 경우 `pg_plan_advice` 같은 도구로 원인을 쪼갠다.[^8]  
3) `pg_upgrade --check`를 CI에 넣어 “업그레이드 가능성”을 매일 측정하고, runbook을 반복 가능한 형태로 완성한다.[^12]

베타 릴리스를 기능 소개로 소비하면 남는 게 적지만, 운영팀 관점에서 확장/플랜/업그레이드를 Beta 4 기간에 닫아두면 RC/GA에서 남는 일은 배포 의사결정뿐입니다.

## 참고 자료

- [PostgreSQL 19 Beta 4 Released!](https://www.postgresql.org/about/news/postgresql-19-beta-4-released-3386/)
- [PostgreSQL 19 Release Notes](https://www.postgresql.org/docs/19/release-19.html)
- [PostgreSQL Beta Information](https://www.postgresql.org/developer/beta/)
- [PostgreSQL 19 Open Items](https://wiki.postgresql.org/wiki/PostgreSQL_19_Open_Items)
- [PostgreSQL 19 Beta 4 release date 메일](https://www.postgresql.org/message-id/f515cc05-67ee-4295-bc79-41c48ce2589d%40postgresql.org)
- [pg_upgrade 문서(18)](https://www.postgresql.org/docs/18/pgupgrade.html)
- [pg_upgrade 문서(16)](https://www.postgresql.org/docs/16/pgupgrade.html)
- [REPACK 문서](https://www.postgresql.org/docs/19/sql-repack.html)
- [WAIT FOR 문서](https://www.postgresql.org/docs/19/sql-wait.html)
- [Routine Vacuuming: Autovacuum Prioritization](https://www.postgresql.org/docs/19/routine-vacuuming.html)
- [Vacuuming 설정](https://www.postgresql.org/docs/19/runtime-config-vacuum.html)
- [pg_stat_autovacuum_scores 문서](https://www.postgresql.org/docs/19/monitoring-stats.html)
- [pg_plan_advice 문서](https://www.postgresql.org/docs/19/pgplanadvice.html)
- [HowToBetaTest](https://wiki.postgresql.org/wiki/HowToBetaTest)
- [PostgreSQL Roadmap](https://www.postgresql.org/developer/roadmap/)
- [Versioning Policy](https://www.postgresql.org/support/versioning/)
- [PostgreSQL 19 Beta 3 검증 윈도우: 확장·호환성·회귀](https://daewooki.github.io/posts/postgresql-19-beta3-test-window/)
- [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)

[^1]: <https://www.postgresql.org/about/news/postgresql-19-beta-4-released-3386/>
[^2]: <https://www.postgresql.org/developer/roadmap/>
[^3]: <https://www.postgresql.org/developer/beta/>
[^4]: <https://www.postgresql.org/message-id/f515cc05-67ee-4295-bc79-41c48ce2589d%40postgresql.org>
[^5]: <https://www.postgresql.org/docs/18/pgupgrade.html>
[^6]: <https://www.postgresql.org/docs/17/extend-extensions.html>
[^7]: <https://www.postgresql.org/docs/19/release-19.html>
[^8]: <https://www.postgresql.org/docs/19/pgplanadvice.html>
[^9]: <https://www.postgresql.org/docs/19/routine-vacuuming.html>
[^10]: <https://www.postgresql.org/docs/19/runtime-config-vacuum.html>
[^11]: <https://www.postgresql.org/docs/19/monitoring-stats.html>
[^12]: <https://www.postgresql.org/docs/16/pgupgrade.html>
[^13]: <https://www.postgresql.org/docs/19/sql-repack.html>
[^14]: <https://www.postgresql.org/docs/19/sql-wait.html>
[^15]: <https://wiki.postgresql.org/wiki/HowToBetaTest>
[^16]: <https://www.postgresql.org/support/versioning/>
[^17]: <https://wiki.postgresql.org/wiki/PostgreSQL_19_Open_Items>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
