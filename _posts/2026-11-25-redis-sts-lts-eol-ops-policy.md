---
title: "Redis 8.0 STS EOL: 버전 수명이 운영 보안 계약이 되는 순간"
description: "Redis 8.0 STS는 2026-12-01 EOL입니다. Redis를 기능이 아니라 STS/LTS와 보안 패치 가용성으로 운영하는 업그레이드 정책을 정리합니다."
date: 2026-11-25 13:43:38 +0900
categories: ["Database", "Redis"]
tags: ["redis", "redis-software", "sts-lts", "eol", "upgrade", "security-patching"]
render_with_liquid: false
---

Redis database version 8.0이 STS로 분류되고 2026-12-01에 EOL이라는 사실은, 운영 관점에서 Redis를 바라보는 단위를 바꿉니다. 기능/성능이 아니라 지원 모델(STS/LTS)과 보안 패치 가용성을 기준으로 “어떤 라인을 언제 올릴지”를 결정해야 하고, 그 결정이 곧 운영 보안 계약이 됩니다.

Redis Software release notes에도 Redis 8.0 database version이 2026-12-01에 EOL이며, 그 이후에는 해당 버전으로 운영 중인 database는 어떤 Redis Software cluster version 위에 있더라도 security patch / bug fix를 받지 못한다고 명시되어 있습니다. [Redis Software release notes 8.0.x](https://redis.io/docs/latest/operate/rs/release-notes/rs-8-0-releases/)

오늘이 2026-11-25 KST이면 EOL까지 남은 시간은 6일입니다. 이 시점에서 필요한 것은 업그레이드를 하겠다는 의지가 아니라, (1) 어떤 target으로 갈지, (2) rehearsal을 어디까지 했는지, (3) 실패했을 때 어디로 되돌아갈지, (4) 이 모든 것을 누가 어떤 순서로 실행할지입니다.

## EOL은 장애가 아니라 보안 패치 중단 이벤트입니다
EOL은 서비스를 즉시 멈추게 만들지 않습니다. 하지만 운영에서 중요한 건 “지금 멀쩡히 도는가”보다 “내일 취약점 공지가 떠도 패치할 수 있는가”입니다.

Redis Software 문서는 STS가 EOL에 도달하면 cluster가 아직 support 기간 안이더라도 database version 자체가 지원을 잃는다고 못 박습니다. 즉, cluster를 최신으로 유지하고 있어도 특정 database version이 EOL이면 그 database version은 패치 대상에서 제외됩니다. [Redis Software product lifecycle](https://redis.io/docs/latest/operate/rs/installing-upgrading/product-lifecycle/)

여기서 운영의 현실적인 의미는 다음과 같습니다.

- 침투 사고나 규제 대응에서 “패치 가능 상태를 유지했다”를 증명하려면, 버전이 support window 안에 있어야 합니다.
- 보안팀/감사팀이 묻는 질문이 “CVE가 있나요?”가 아니라 “패치 받을 수 있는 버전인가요?”로 바뀝니다.
- 결국 Redis는 “버전 = 기능”이 아니라 **버전 = 지원 계약의 단위**가 됩니다.

Redis 8.0 STS EOL(2026-12-01)은 이 전환을 강제로 일으키는 촉매입니다.

## Redis Software에서는 cluster version과 database version이 서로 다른 수명 주기를 가집니다
Redis Software(구 Redis Enterprise)에서 운영이 헷갈리는 지점은 버전이 두 겹이라는 점입니다.

- Redis Software cluster version: 관리 plane / 운영 기능 / packaging / 번들된 feature sets
- Redis database version: 실제 데이터 plane에서 명령을 처리하는 Redis 엔진(그리고 그 버전)

Redis Software에서 database upgrade는 “cluster upgrade”와 별개의 작업입니다. Database는 cluster가 번들로 제공하는 버전들 중 하나로 올릴 수 있고, 기본값을 따르거나(대개 최신) 명시적으로 버전을 고를 수 있습니다. [Upgrade a Redis Software database](https://redis.io/docs/latest/operate/rs/installing-upgrading/upgrading/upgrade-database/)

그리고 이번 이슈는 cluster version EOL이 아니라 database version EOL입니다.

Redis Software product lifecycle의 database version EOL schedule을 보면 Redis 8.0은 STS로 2026-12-01 EOL, Redis 8.2는 LTS로 2030-09-01 EOL입니다. [Redis Software product lifecycle](https://redis.io/docs/latest/operate/rs/installing-upgrading/product-lifecycle/)

이 구분은 업그레이드 전략을 바꿉니다.

- cluster version은 “어떤 번들을 쓸지(운영 기능/플랫폼 지원/보안 패치 포함)”에 대한 선택입니다.
- database version은 “내 서비스가 어떤 Redis command semantics / protocol / module 동작을 기반으로 도는지”에 대한 선택입니다.

둘을 한 덩어리로 보면서 “Redis 8.0을 8.2로 업그레이드”라고 말하기 시작하면, 계획이 금방 무너집니다. 실제로는 (a) cluster가 어떤 버전을 제공하는지, (b) 그 안에서 database를 어떤 버전으로 올릴지, (c) 그 과정에서 modules/feature sets가 어떻게 움직이는지를 나눠서 확인해야 합니다.

## STS/LTS를 운영 정책으로 바꾸면, 업그레이드가 ‘행사’에서 ‘주기’가 됩니다
STS/LTS를 제대로 운영에 반영하면, 업그레이드는 분기별 행사로 떨어지고 “버전 선택” 자체가 정책이 됩니다.

내가 권하는 프레임은 단순합니다.

- Production: LTS만 허용
- Staging/Pre-prod: STS를 허용(오히려 강제)해서 다음 breaking change를 조기 흡수
- 개발팀: 기능이 아니라 “지원 상태”를 기준으로 올라갈 라인을 결정

Redis 문서에서도 STS는 다음 minor release 이후 6개월 지원이라는 모델을 명시하고, 장기간 동일 버전으로 운영하려면 LTS(예: Redis 8.2)를 사용하라고 안내합니다. [Redis Software product lifecycle](https://redis.io/docs/latest/operate/rs/installing-upgrading/product-lifecycle/)

이 정책이 주는 효과는 세 가지입니다.

1) Production이 “EOL 임박” 상태에 빠지는 일이 줄어듭니다. LTS의 EOL은 길기 때문에 일정이 예측 가능합니다.

2) STS에서 나오는 변화(예: 내부 프로토콜 변경, module 동작 변경, tooling/metrics 변경)를 staging에서 먼저 맞고, production은 major boundary만 대응하면 됩니다.

3) 업그레이드 리허설이 표준화됩니다. 매번 새로 만드는 runbook이 아니라, 분기마다 반복하는 체크리스트가 됩니다.

Redis를 Celery broker/backing store로 쓰는 경우(내 블로그의 LLM queue/worker 연재에서 다뤘던 형태)에는 특히 이 접근이 중요합니다. 큐 시스템은 “기능 추가”보다 “멈추지 않는 운영”이 훨씬 가치가 크고, 보안 패치 불가 상태는 큐 시스템에서 치명적입니다.

- [LLM 백엔드 “Queued Forever”를 끝내는 법: Celery + Redis 비동기 워커 아키텍처 심층 분석](https://daewooki.github.io/posts/llm-queued-forever-celery-redis-2026-4-1/)
- [LLM 요청을 “안전하게” 비동기화하기: Celery + Redis queue/worker 아키텍처 심층 분석](https://daewooki.github.io/posts/llm-celery-redis-queueworker-2026-6-1/)

## 이번 업그레이드에서 현실적인 target: Redis 8.2 LTS
Redis 8.0 STS EOL을 피하는 가장 보수적인 선택은 같은 major(8.x) 안에서 LTS로 옮기는 것입니다.

Redis Software lifecycle 기준으로 보면:

- Redis 8.0: STS, EOL 2026-12-01
- Redis 8.2: LTS, EOL 2030-09-01
- Redis 8.4: STS, EOL 2027-01-01

즉, 8.4로 올리는 건 EOL을 한 달 남짓 미루는 것에 불과합니다. 이 상황에서 production에서 8.4를 선택할 이유가 거의 없습니다. [Redis Software product lifecycle](https://redis.io/docs/latest/operate/rs/installing-upgrading/product-lifecycle/)

여기서 중요한 포인트가 하나 더 있습니다. Redis Software에서 database upgrade를 실행할 때 “기본값”이 항상 운영 정책과 일치하지 않습니다.

Redis Software database upgrade 문서에 따르면, 업그레이드 시 기본은 “cluster가 번들한 최신 Redis version”이며, 버전을 고르고 싶으면 `redis_version`을 명시하라고 되어 있습니다. 그리고 표에 따르면 Redis Software 8.0.20이나 8.2.0 기준 default DB version이 8.6으로 잡혀 있습니다. [Upgrade a Redis Software database](https://redis.io/docs/latest/operate/rs/installing-upgrading/upgrading/upgrade-database/)

정리하면 이렇게 됩니다.

- 버튼만 누르면 8.6으로 갈 가능성이 큽니다(기본값).
- 하지만 8.6은 STS입니다.
- 지금 목표는 “EOL 리스크 제거”이지 “최신 minor로 이동”이 아닙니다.

따라서 production policy가 LTS라면, 이번 작업은 target을 명시적으로 Redis 8.2로 고정해야 합니다.

## 업그레이드 전, 깨지는 변경을 어디서 흡수할지부터 결정합니다
Redis 8.0 → 8.2(같은 major 내부)는 문서상 “minor versions within a major version don't introduce breaking changes”라는 약속이 있습니다. [Redis Software product lifecycle](https://redis.io/docs/latest/operate/rs/installing-upgrading/product-lifecycle/)

하지만 운영에서 “breaking change가 없다”는 말은 “아무 준비도 필요 없다”는 뜻이 아닙니다. 특히 Redis Software는 Redis engine뿐 아니라 modules/feature sets/관리 plane까지 한 번에 움직일 수 있습니다.

나는 깨지는 변경을 다음처럼 분류해서 흡수 지점을 고정합니다.

### 1) protocol/clients 변화: 애플리케이션 계층에서 흡수
Redis 7.2 업그레이드에서 대표적으로 이야기되는 이슈가 RESP3 관련입니다. Redis Software database upgrade 문서에도 Go-Redis, Lettuce 같은 클라이언트가 Redis Stack commands를 사용할 때 RESP2로 고정하라는 안내가 들어가 있습니다. [Upgrade a Redis Software database](https://redis.io/docs/latest/operate/rs/installing-upgrading/upgrading/upgrade-database/)

이건 Redis가 해결해주지 못합니다. 애플리케이션이 프로토콜 협상/파싱에 의존하기 때문입니다.

따라서 major boundary(예: 6.2 → 7.2)를 넘는 업그레이드는 “infra 작업”이 아니라 애플리케이션 변경/배포를 포함한 프로젝트로 다뤄야 합니다. Redis 7.2의 breaking changes는 별도 문서로 정리되어 있습니다. [Redis 7.2 release notes and breaking changes](https://redis.io/docs/latest/operate/rc/changelog/version-release-notes/7-2/)

### 2) Lua / scripts / ACL semantics 변화: 테스트 계층에서 흡수
Redis 7.2 breaking changes에는 Lua에서 `print()` 제거 같은 항목이 포함되어 있습니다. 이런 류의 변경은 staging에서 스크립트 회귀 테스트를 돌려야 잡힙니다. [Redis 7.2 release notes and breaking changes](https://redis.io/docs/latest/operate/rc/changelog/version-release-notes/7-2/)

### 3) module/feature sets 동작: 데이터 계층에서 흡수
Redis Software는 Redis Search, JSON, Time series 같은 capabilities가 묶여 있습니다. Redis 8에서 database를 만들거나 올리면 특정 capabilities가 자동 enable될 수 있다는 문서가 있습니다. [Install and upgrade modules](https://redis.io/docs/latest/operate/rs/installing-upgrading/modules/)

자동 enable 자체가 문제라기보다, “운영 중인 인덱스/메모리/latency profile이 바뀌는 변화”라는 점이 핵심입니다. 이건 infra에서 흡수할 게 아니라 workload 측정과 capacity planning으로 흡수해야 합니다.

## 오늘(2026-11-25 KST) 기준으로 잡는 현실적인 일정
EOL이 2026-12-01로 고정되어 있으니, 일정은 역산입니다. 여기서는 Redis 8.0 database를 Redis 8.2 LTS로 올린다는 가정으로 잡습니다.

- D-6 (11/25): inventory + 영향 범위 확정 + target 고정(8.2)
- D-5 (11/26): staging rehearsal 1회(완주가 목표)
- D-4 (11/27): staging rehearsal 2회(롤백 포함)
- D-3 (11/28): production canary(traffic 일부 or 특정 tenant)
- D-2 (11/29): production main upgrade window
- D-1 (11/30): 잔여 DB 처리 + 모니터링/대시보드 업데이트
- D-day (12/01): EOL 도달. 이 날은 업그레이드가 아니라 “미완료분이 없는지 확인”만 남겨야 합니다.

이 일정이 촉박해 보이지만, 촉박한 일정에서 유일하게 통하는 방식은 “한 번에 성공”이 아니라 rehearsal을 통해 실패를 이미 경험해두는 것입니다.

## Redis Software에서 가능한 업그레이드 경로: cluster와 database를 분리해서 설계
이번에 해야 하는 업그레이드는 크게 두 종류가 섞일 수 있습니다.

1) database version 업그레이드 (Redis 8.0 → 8.2)
2) cluster version 업그레이드 (예: Redis Software 7.x → 8.2.x)

둘 중 무엇이 필요한지는 현재 설치 상태에 따라 달라집니다.

### cluster version 업그레이드가 필요한지 확인
Redis Software는 지원되는 cluster upgrade path가 정해져 있습니다. 예를 들어 6.2.x에서 8.2.x로 바로 못 가고, 중간 버전을 거쳐야 하는 경우가 생깁니다. 이 표는 공식 문서에 있습니다. [Supported upgrade paths for Redis Software](https://redis.io/docs/latest/operate/rs/references/upgrade-paths/)

운영 현실에서는 이 표가 일정의 상한선을 결정합니다.

- cluster를 못 올리면, 원하는 database version(예: 8.2)을 번들로 제공받지 못합니다.
- 반대로 cluster가 이미 8.0.20/8.2.x라면, database만 올리면 됩니다.

### database version 업그레이드는 cluster가 제공하는 버전들 안에서 결정
Redis Software database upgrade 문서에는 cluster version별로 번들된 database versions와 default DB version이 표로 정리되어 있습니다. 예를 들어 Redis Software 8.0.20은 6.2/7.2/7.4/8.0/8.2/8.4/8.6을 번들하고 default DB version은 8.6입니다. [Upgrade a Redis Software database](https://redis.io/docs/latest/operate/rs/installing-upgrading/upgrading/upgrade-database/)

이 표를 보고 production policy에 맞게 “업그레이드 target DB version”을 확정해야 합니다.

## 실행 가능한 preflight + inventory 스크립트 (REST API 기반)
Redis Software는 Cluster API를 제공합니다. 문서에도 node 정보를 `GET /nodes`로 조회해서 `supported_database_versions`를 확인하라고 되어 있습니다. [Upgrade a Redis Software database](https://redis.io/docs/latest/operate/rs/installing-upgrading/upgrading/upgrade-database/)

여기서는 운영에서 바로 써먹을 수 있는 inventory 스크립트를 제시합니다.

### 의존성
- bash
- curl
- jq 1.6+

### 목적
- 어떤 database가 Redis 8.0으로 떠 있는지 찾습니다.
- cluster가 어떤 database versions를 지원하는지 확인합니다.
- 업그레이드 target(8.2)이 가능한 상태인지 확인합니다.

### 스크립트

```bash
#!/usr/bin/env bash
set -euo pipefail

# Redis Software Cluster Manager API endpoint
# 예: https://cm.example.internal:9443
: "${RS_API_BASE:?set RS_API_BASE}"
: "${RS_USER:?set RS_USER}"
: "${RS_PASS:?set RS_PASS}"

AUTH="${RS_USER}:${RS_PASS}"

# 1) cluster가 지원하는 database versions 확인 (/nodes)
# 문서 기준: supported_database_versions 필드 확인
curl -sk -u "$AUTH" "$RS_API_BASE/v1/nodes" \
  | jq -r '
      (.[0].supported_database_versions // []) as $v
      | "supported_database_versions=" + ($v|join(","))
    '

# 2) database 목록과 각 Redis engine version 출력 (/v1/bdbs)
# /v1/bdbs의 스키마는 배포/버전에 따라 조금씩 다를 수 있어 필드는 방어적으로 조회합니다.
# 여기서는 "redis_version" 또는 "version" 계열 필드를 우선 탐색합니다.

curl -sk -u "$AUTH" "$RS_API_BASE/v1/bdbs" \
  | jq -r '
      .[]
      | {
          id: (.uid // .bdb_uid // .id),
          name: (.name // "-"),
          endpoint: (.endpoint // .dns_name // "-"),
          redis_version: (.redis_version // .version // .database_version // "unknown")
        }
      | [ .id, .name, .endpoint, .redis_version ]
      | @tsv
    ' \
  | column -t

# 3) Redis 8.0인 DB만 필터
echo
echo "Databases on Redis 8.0 (needs upgrade before 2026-12-01 EOL):"

curl -sk -u "$AUTH" "$RS_API_BASE/v1/bdbs" \
  | jq -r '
      .[]
      | {
          id: (.uid // .bdb_uid // .id),
          name: (.name // "-"),
          redis_version: (.redis_version // .version // .database_version // "unknown")
        }
      | select(.redis_version | tostring | startswith("8.0"))
      | [ .id, .name, .redis_version ]
      | @tsv
    ' \
  | column -t
```

### 실행 예시(예상 출력 형태)

```text
supported_database_versions=6.2,7.2,7.4,8.0,8.2,8.4,8.6
1  queue-prod   queue.prod.internal   8.0.2
2  cache-prod   cache.prod.internal   8.2.1

Databases on Redis 8.0 (needs upgrade before 2026-12-01 EOL):
1  queue-prod  8.0.2
```

실제 필드명은 설치 버전/환경에 따라 다를 수 있으니, 첫 실행에서는 `jq`에서 필드가 unknown으로 나오는지부터 확인하고, 운영 환경 스키마에 맞게 한 번만 손보면 됩니다.

이 inventory가 중요한 이유는 단 하나입니다. 업그레이드는 버튼을 누르는 작업이 아니라, 대상 식별이 80%입니다.

## database 업그레이드 런북: 리허설 가능한 형태로 쪼갭니다
Redis Software 문서가 제시하는 database upgrade 방법은 UI / rladmin / REST API 세 가지입니다. 운영 자동화 관점에서는 rladmin 또는 REST API가 재현성이 좋습니다. [Upgrade a Redis Software database](https://redis.io/docs/latest/operate/rs/installing-upgrading/upgrading/upgrade-database/)

여기서는 “리허설→프로덕션 실행”까지 동일한 커맨드로 갈 수 있는 형태를 기준으로 정리합니다.

### 0) 준비: 백업/복제 없이는 업그레이드가 아니라 도박입니다
문서는 업그레이드 전 데이터 손실 방지를 위해 export/replication/persistence 중 하나를 확보하라고 권합니다. [Upgrade a Redis Software database](https://redis.io/docs/latest/operate/rs/installing-upgrading/upgrading/upgrade-database/)

운영에서 내가 선호하는 우선순위는:

1) Replica + failover를 활용한 무중단에 가까운 upgrade (가능한 경우)
2) export(외부 저장소) + blue/green
3) persistence only (AOF restore가 느릴 수 있음)

큐/세션/캐시처럼 데이터 성격이 다양한 Redis에서는 “이 데이터는 버려도 되는가”가 DB마다 다릅니다. 버려도 되는 캐시까지 똑같이 replication/persistence를 강제하면 비용과 복잡도가 올라갑니다. 대신 업그레이드 정책에서 DB를 등급화하는 편이 낫습니다.

- Tier A: 영속 데이터(Streams 기반 job state 등) → replication + export 둘 다
- Tier B: 중요하지만 재생성 가능 → export만
- Tier C: pure cache → export 생략 가능, 다만 롤백용 empty DB는 준비

### 1) staging에서 rladmin으로 1회 완주
`rladmin upgrade db`는 database의 Redis version과 modules를 업그레이드합니다. 문서에 옵션(예: `redis_version`, `preserve_roles`)과 예시 출력이 나와 있습니다. [rladmin upgrade](https://redis.io/docs/latest/operate/rs/references/cli-utilities/rladmin/upgrade/)

staging에서 먼저 성공시켜야 하는 최소 시나리오는:

- target DB version을 명시(8.2)
- `preserve_roles`로 shard role/placement 흔들림 최소화
- upgrade 직후 health/latency 확인
- read/write workload smoke test

예시:

```bash
# 현재 DB 목록 확인
rladmin status databases extra all

# queue-stg DB를 Redis 8.2로 업그레이드
rladmin upgrade db queue-stg redis_version 8.2 preserve_roles

# 업그레이드 후 버전 확인
rladmin status databases extra all | grep -E "queue-stg|redis_version"
```

여기서 중요한 것은 “업그레이드가 된다/안 된다”가 아니라, 업그레이드 중 어떤 로그/이벤트가 찍히는지, 모니터링에서 어떤 패턴이 보이는지, 애플리케이션이 어떤 오류를 내는지까지 기록하는 것입니다. 그 기록이 production runbook이 됩니다.

### 2) production은 canary를 먼저 만든 뒤, 동작을 확인하고 넓힙니다
Redis 단독 업그레이드는 성공해도 애플리케이션이 깨질 수 있습니다. 특히 client library가 error string이나 특정 reply shape를 가정하는 경우가 많습니다(Streams, Lua, ACL 조합에서 흔합니다). Redis 7.2 breaking changes 문서가 “업그레이드가 기능을 깨뜨릴 수 있으니 breaking changes를 읽고 애플리케이션을 업데이트하라”고 못 박는 이유입니다. [Redis 7.2 release notes and breaking changes](https://redis.io/docs/latest/operate/rc/changelog/version-release-notes/7-2/)

이번 작업이 8.0 → 8.2로만 끝난다면 major boundary는 넘지 않지만, 운영에서는 canary를 생략할 이유가 없습니다.

canary 전략은 두 가지가 현실적입니다.

- traffic 분할이 가능한 경우: 애플리케이션 레벨에서 일부 요청만 canary DB endpoint로 보냅니다.
- 분할이 어려운 경우: tenant/user group 단위로 endpoint를 다르게 줍니다.

Celery broker처럼 endpoint가 사실상 하나인 시스템에서는, “broker endpoint 교체”가 전체 영향이라 canary가 어렵습니다. 이 경우엔 production과 동일 규모의 pre-prod를 따로 두고, worker 부하까지 재현한 뒤 진행해야 합니다(이 부분은 내 블로그의 queue/worker 설계 글들과 겹치니 여기서는 반복하지 않습니다).

## 롤백을 ‘다운그레이드’로 생각하면 실패합니다
Redis database version 업그레이드는 일반적으로 “올리는 것”은 공식 경로가 있지만, “내리는 것”은 운영에서 거의 불가능에 가깝습니다. 다운그레이드가 되더라도 데이터 포맷/명령 semantics가 얽혀 위험합니다.

그래서 롤백은 다음 중 하나로 정의해야 합니다.

- (A) 업그레이드 이전 시점의 snapshot/export로 신규 DB를 만들고 endpoint를 다시 돌린다
- (B) blue/green으로 기존 DB를 유지한 채 새 DB를 붙이고, 문제가 생기면 트래픽을 원래 DB로 되돌린다

나는 (B)를 기본값으로 잡습니다. 이유는 단순합니다.

- rollback이 빠릅니다.
- rollback이 “복원 작업”이 아니라 “라우팅 변경”이 됩니다.
- 장애 원인 분석을 업그레이드 직후에도 계속할 수 있습니다(새 DB를 보존).

Redis Software에서 가능한 구체적 구현은 환경마다 다르지만, 최소한 다음 원칙은 동일합니다.

1) endpoint 전환이 가능한 구조로 만들어둔다(DNS, service discovery, config flag)
2) 업그레이드 직전 export를 1회 찍는다
3) 업그레이드 후 일정 시간 동안 old DB를 삭제하지 않는다

이 원칙이 없으면, EOL 대응 업그레이드가 “보안 리스크를 줄이려다 가용성 리스크를 키우는” 이벤트가 됩니다.

## STS EOL을 계기로 운영 정책을 문서화할 때 넣어야 하는 항목
이번 사건이 지나가도 다음 STS EOL은 다시 옵니다. Redis lifecycle 문서 자체가 STS/LTS 모델을 계속 굴리겠다는 선언이기 때문입니다. [Redis Software product lifecycle](https://redis.io/docs/latest/operate/rs/installing-upgrading/product-lifecycle/)

운영 정책 문서(내부 runbook/ADR)에 최소한 아래는 들어가야 합니다.

### 1) Production 허용 라인
- Production: LTS only (현재 8.2)
- 예외: STS 기능이 필요한 특정 워크로드만, 기간 제한/owner 지정

### 2) EOL D-30 규칙(최소)
EOL 30일 전에는 최소한 아래가 완료되어야 합니다.

- inventory에서 대상 DB가 0개가 되거나, 업그레이드 날짜가 확정됨
- rehearsal 1회 이상 완료
- rollback 경로(blue/green 또는 export restore)가 문서화됨

지금은 D-6이니, 이 규칙을 지키지 못했을 가능성이 큽니다. 그렇더라도 이번 한 번은 예외로 처리할 수 있지만, 예외를 반복하면 매번 D-6에 몰립니다.

### 3) major boundary 업그레이드 원칙
Redis 6.2 → 7.2 같은 major boundary 업그레이드에는 breaking changes 체크리스트가 필요합니다. Redis는 7.2 breaking changes를 공식 문서로 제공합니다. [Redis 7.2 release notes and breaking changes](https://redis.io/docs/latest/operate/rc/changelog/version-release-notes/7-2/)

이때 운영 정책은 이렇게 잡는 편이 깔끔합니다.

- major boundary 업그레이드는 분기 상시 작업이 아니라 “프로젝트”로 분류
- 애플리케이션 변경(클라이언트 설정/RESP 버전 고정/스크립트 수정)이 포함되면, infra 티켓으로 처리하지 않고 릴리즈 프로세스를 탄다

## CVE는 Redis engine에만 생기지 않습니다: 8.0.20-154의 CVE-2026-111497 사례
EOL이 보안 계약이라는 말이 추상적으로 들릴 수 있습니다. 이번에 추천 검색어로 제시된 CVE-2026-111497는 그 반례를 실제로 보여줍니다.

Redis Software 8.0.20-154 릴리스 노트에는 CVE-2026-111497 보안 수정이 포함되어 있고, Brotli decoder out-of-bounds write로 인해 memory corruption 및 잠재적 RCE가 가능하다고 설명합니다. 또한 이 수정은 Node.js/Envoy 업그레이드로 들어갔다고 나옵니다. [Redis Software release notes 8.0.20-154](https://redis.io/docs/latest/operate/rs/release-notes/rs-8-0-releases/rs-8-0-20-154/)

이게 중요한 이유는 간단합니다.

- 취약점이 Redis command 처리 로직(redis-server)만의 문제가 아닙니다.
- 운영 제품(Redis Software)은 관리 plane, proxy, envoy, node runtime 등 더 넓은 컴포넌트를 포함합니다.
- 그래서 “Redis database version만 올리면 안전하다” 같은 사고는 틀립니다.

반대로도 마찬가지입니다.

- cluster version을 패치했더라도, database version이 EOL이면 그 database version에 대해서는 패치 제공이 끊깁니다. [Redis Software release notes 8.0.x](https://redis.io/docs/latest/operate/rs/release-notes/rs-8-0-releases/)

결국 운영에서 안전하다는 의미는 “둘 다”입니다.

- cluster version: 보안 패치가 포함된 최신 maintenance release로 유지
- database version: support window 안의 LTS를 기본으로 유지

## 결론: Redis를 ‘버전 기능’이 아니라 ‘지원 모델’로 운영해야 합니다
Redis 8.0 STS EOL(2026-12-01)은 단지 특정 minor 버전의 지원 종료가 아닙니다. Redis를 운영하는 방식이 “필요한 기능이 있는 버전”에서 “보안 패치 가용성이 보장되는 버전 라인”으로 이동해야 한다는 신호입니다.

이번 업그레이드에서 핵심은 최신으로 가는 것이 아니라, 정책에 맞는 라인으로 가는 것입니다. production에서 LTS만 허용한다면 target은 Redis 8.2로 고정하고, 버튼 기본값(8.6) 같은 비정책적 선택을 제거해야 합니다. cluster와 database를 분리해 업그레이드 경로를 설계하고, rehearsal/롤백을 포함한 runbook을 남기면, 다음 EOL은 더 이상 비상 작업이 아니라 주기 작업이 됩니다.

## 참고 자료
- [Redis Software release notes 8.0.x](https://redis.io/docs/latest/operate/rs/release-notes/rs-8-0-releases/)
- [Redis Software product lifecycle](https://redis.io/docs/latest/operate/rs/installing-upgrading/product-lifecycle/)
- [Supported upgrade paths for Redis Software](https://redis.io/docs/latest/operate/rs/references/upgrade-paths/)
- [Upgrade a Redis Software database](https://redis.io/docs/latest/operate/rs/installing-upgrading/upgrading/upgrade-database/)
- [rladmin upgrade](https://redis.io/docs/latest/operate/rs/references/cli-utilities/rladmin/upgrade/)
- [Redis 7.2 release notes and breaking changes](https://redis.io/docs/latest/operate/rc/changelog/version-release-notes/7-2/)
- [Install and upgrade modules](https://redis.io/docs/latest/operate/rs/installing-upgrading/modules/)
- [Redis Software release notes 8.0.20-154](https://redis.io/docs/latest/operate/rs/release-notes/rs-8-0-releases/rs-8-0-20-154/)
- [Redis Software release notes 8.2.x](https://redis.io/docs/latest/operate/rs/release-notes/rs-8-2-releases/)
- [Redis Software Support Policy](https://redis.io/legal/software-support-policy/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
