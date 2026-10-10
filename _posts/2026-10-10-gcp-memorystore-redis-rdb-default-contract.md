---
title: "GCP Memorystore for Redis RDB 스냅샷 기본 활성화 이후 운영 계약 재정의"
description: "콘솔 기본값으로 켜진 RDB snapshots가 Managed Redis의 RPO/RTO, 성능, 복구 리허설, Terraform 표준을 바꿉니다."
date: 2026-10-10 11:28:14 +0900
categories: ["Cloud", "GCP Memorystore"]
tags: ["gcp", "memorystore", "redis", "terraform", "disaster-recovery", "cmek"]
render_with_liquid: false
---

## 기본값이 바뀐 지점: 콘솔 경로에서만 persistence가 기본이 됐다
2026-10-08 릴리스 노트에 따르면, Google Cloud console에서 Memorystore for Redis 인스턴스를 생성할 때 RDB snapshots가 기본 활성화(GA)되었습니다. 문구 자체가 “console로 생성할 때(enabled by default when you create an instance using the Google Cloud console)”라서, API나 gcloud, Terraform까지 무조건 기본값이 바뀌었다고 단정하면 위험합니다. 다만 운영에서 중요한 건 “어떤 경로로든 인스턴스가 만들어질 수 있다”는 사실이고, 콘솔 기본값 변화는 IaC를 갖춘 조직에서도 실제 비용/성능 이슈로 직결됩니다. [Memorystore for Redis release notes](https://docs.cloud.google.com/memorystore/docs/redis/release-notes)

문제가 되는 패턴은 대체로 이렇습니다.

- 개발/PoC는 콘솔로 빨리 만들고, 나중에 Terraform으로 흡수합니다.
- Terraform 모듈이 persistence 관련 설정을 노출하지 않고, “기본값에 맡긴다”로 설계돼 있습니다.
- 인스턴스가 생성된 뒤에야 latency 이상이나 메모리 압박(OOM 근접)을 관측합니다.

결론적으로 **운영 계약**을 “Managed Redis는 기본적으로 휘발성”으로 적어 둔 조직은, 2026-10-08 이후 그 전제가 깨집니다. persistence가 켜졌다는 사실 자체보다, “기본값 변화로 인해 팀/환경마다 설정이 섞이는 것”이 더 큰 리스크입니다.

## Memorystore RDB snapshots는 어떤 persistence인가: 내부 복구용, 마지막 1개, best effort
Memorystore for Redis의 RDB snapshots는 open source Redis의 RDB 개념을 기반으로 하지만, 운영자가 흔히 기대하는 “내가 접근 가능한 백업 세트”와는 다릅니다.

- 스냅샷은 내부 시스템 복구용이며 사용자가 접근할 수 없습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- 특정 시점에 **마지막으로 성공한 스냅샷 1개만** 유지됩니다(수동 복원/특정 시점 선택 불가). [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- 스냅샷 주기는 1h~24h 범위에서 선택합니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- Standard Tier는 기본적으로 replica로 failover하는 것이 1차 복구 메커니즘이며, snapshot에서 복구는 “replica 복구가 실패하는 경우”에 쓰입니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- Standard Tier에서 스냅샷은 primary가 아니라 replica에서 생성됩니다(기본적으로 primary의 CPU/메모리 영향을 줄이기 위해). [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- RDB snapshots는 인스턴스 과금에 “추가 비용이 없다”고 문서에 명시돼 있습니다. 즉, 스냅샷 자체로 라인아이템이 늘어나진 않지만, 성능/헤드룸 때문에 더 큰 용량 tier로 올리면 비용이 바뀝니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- Memorystore for Redis(인스턴스 제품)는 AOF persistence를 지원하지 않습니다. durability를 올리고 싶어도, 옵션이 RDB뿐이라는 제약이 운영 설계를 제한합니다. [Memorystore for Redis overview](https://docs.cloud.google.com/memorystore/docs/redis/memorystore-for-redis-overview)

여기서 핵심은 “기본 persistence가 켜졌다”를 “이제 Redis를 durable store처럼 써도 된다”로 해석하면 사고가 난다는 점입니다. 스냅샷은 best effort이고, 실패하면 임의로 오래된 스냅샷만 남을 수도 있습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

## RPO/RTO 기대치를 다시 써야 한다: 숫자 하나가 아니라 상한/조건의 조합
RPO/RTO를 계약 문장으로 쓰다 보면 흔히 이렇게 단정합니다.

- “Standard Tier니까 RPO는 거의 0에 가깝다.”
- “failover 30초니까 RTO는 30초다.”
- “스냅샷이 있으니 최악에도 데이터는 살아 있다.”

문서 기반으로 현실적인 계약 문장으로 바꾸면 다음처럼 형태가 달라집니다.

### Standard Tier의 RTO: failover와 snapshot recovery는 성격이 다르다
Standard Tier에서 failover는 평균 30초 정도의 unavailable 구간이 발생할 수 있고(유지보수 이벤트는 평균 15초), 연결이 끊기므로 애플리케이션은 재연결 로직이 있어야 합니다. [High availability for Memorystore for Redis](https://docs.cloud.google.com/memorystore/docs/redis/high-availability-for-memorystore-for-redis)

반면 snapshot에서 복구하는 경우는 “인스턴스가 snapshot을 로드하는 동안 unavailable”이며, 복구 시간은 스냅샷 크기에 좌우됩니다. 이 복구 시간은 failover 시간(수십 초)과 같은 축으로 비교하면 안 됩니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

운영 계약에서 RTO를 하나로 쓰기보다는, 아래처럼 케이스를 분리하는 편이 안전합니다.

- Failover(HA 경로) RTO: 평균 30초 수준 + 재연결/재시도 정책이 흡수해야 하는 시간
- Snapshot recovery RTO: 스냅샷 크기/로드 속도에 따라 변동(모니터링 지표 기반 예측 필요)

### RPO: “스냅샷 주기 = RPO”가 아니다
RDB snapshots의 worst case 데이터 손실은 “마지막 정상 스냅샷이 시작된 시점 이후로, 다음 스냅샷을 저장하는 데 걸리는 시간까지의 합”이라고 문서에 적혀 있습니다. 그리고 스냅샷은 지정한 간격에 맞춰 best effort로 시도되지만 보장되지는 않습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

즉, 1h interval로 설정했다고 RPO ≤ 1h라고 적는 순간 거짓말이 될 수 있습니다. 스냅샷이 연속 실패하면 마지막 정상 스냅샷은 임의로 오래되어 있을 수 있고, 그때의 RPO는 사실상 상한이 없어집니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

RPO는 “설정값”이 아니라 “관측값”을 포함해야 합니다.

- 스냅샷 staleness는 `last_success_age` 같은 지표로 관측합니다. [Supported monitoring metrics](https://docs.cloud.google.com/memorystore/docs/redis/supported-monitoring-metrics?hl=en)
- 계약 문장은 “RPO는 snapshot interval을 목표로 하되, snapshot 실패를 탐지하는 알림과 운영 대응 시간을 포함한다”처럼 써야 합니다.

### HA가 durability를 보장하지 않는다는 문장을 계약에 포함해야 한다
Standard Tier가 제공하는 HA는 “대부분의 장애/유지보수에서 availability를 올려주는 것”이지, catastrophic event(예: region 단위 이슈)까지 포함한 durability를 보장하지 않습니다. 문서에서도 cross-region replication 미지원이며, regional resilience가 필요하면 Memorystore for Valkey를 권합니다. [High availability for Memorystore for Redis](https://docs.cloud.google.com/memorystore/docs/redis/high-availability-for-memorystore-for-redis)

이 문장을 운영 계약에 넣지 않으면, persistence 기본 활성화 같은 변화가 “Redis도 이제 DB처럼 다루자”로 조직 문화가 이동하기 쉽고, 그 끝은 항상 비용 폭증 또는 데이터 사고입니다.

## 스냅샷 스케줄(주기/시작 시간)을 운영 기준으로 만들기: 성능 창과 헤드룸을 같이 설계
RDB snapshots의 주기는 1h/6h/12h/24h 중 선택(문서/도구마다 표현은 다르지만 의미는 동일)하며, 시작 시간을 지정할 수 있습니다. [Manage RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/manage-rdb-snapshots?hl=en) [google_redis_instance (Terraform)](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/redis_instance.html)

스케줄을 설계할 때, 운영에서 중요해지는 건 “복구 목표”보다 “평시 성능/메모리”입니다.

### RDB 생성은 copy-on-write를 전제로 한 fork 기반 작업이다
Redis의 RDB 생성(BGSAVE 계열)은 fork + copy-on-write 특성을 가집니다. Memorystore의 Export/Import 문서는 export 동작이 BGSAVE와 유사하고, high write load에서 메모리 사용량이 최악 2배까지 증가할 수 있다고 명시합니다. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)

클러스터 문서이긴 하지만, RDB snapshots가 fork와 copy-on-write 메커니즘을 사용하며 메모리 풋프린트가 데이터 크기 대비 최대 2배가 될 수 있다는 설명이 더 직접적입니다. [Best practices for Memorystore for Redis Cluster](https://docs.cloud.google.com/memorystore/docs/cluster/general-best-practices?hl=en)

Standard Tier에서 스냅샷이 replica에서 생성된다고 해도, 그 replica가 메모리 압박을 받으면 스냅샷이 실패하거나 replica 품질이 흔들릴 수 있습니다. 결국 primary로 failover가 일어나면 “그 순간의 성능”과 “데이터 일관성”이 같이 흔들립니다.

### 스냅샷 주기 선택은 RPO보다 ‘쓰기 패턴’이 먼저다
내 경우, Redis를 queue/stream처럼 쓰기 시작하는 순간(예: Celery broker, job dedup, idempotency key 저장소) 쓰기 패턴이 “항상 존재”로 바뀌고, 스냅샷/Export 같은 작업이 평시 성능을 침범하기 시작합니다. 같은 Redis라도 cache-only일 때와 운영 난이도가 달라집니다. 이 지점은 예전에 썼던 [Celery + Redis 비동기 워커 아키텍처 심층 분석](https://daewooki.github.io/posts/llm-queued-forever-celery-redis-2026-4-1/)에서 다룬 “Redis를 어디까지 상태 저장소로 볼 것인가”와 연결됩니다.

주기 선택은 아래 질문을 통과해야 합니다.

- 쓰기 QPS가 높은 시간대가 매일 반복되는가
- 하루 중 트래픽 저점이 명확한가
- 스냅샷/Export 작업이 latency에 미치는 영향(특히 tail latency)을 허용할 수 있는가

문서도 “트래픽이 낮은 시간에 스냅샷을 스케줄하라”고 직접 언급합니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

### KST 기준으로 시작 시간을 잡을 때 생기는 함정: RFC3339 UTC 정렬
gcloud/Terraform은 `rdb_snapshot_start_time`을 RFC3339 UTC(Zulu)로 받습니다. [Manage RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/manage-rdb-snapshots?hl=en) [google_redis_instance (Terraform)](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/redis_instance.html)

KST로 “매일 03:00”에 스냅샷을 뜨고 싶으면, UTC로는 전날 18:00Z가 됩니다. 이런 변환을 운영자가 매번 수동으로 하면, 환경/팀마다 start time이 어긋납니다. 그래서 start time은 “정책 값”으로 고정하고, IaC에서만 계산하거나(예: locals로 Zulu 문자열 고정), 차라리 24h interval + start time을 UTC로 고정하는 방식이 더 안전합니다.

### 메모리 헤드룸을 운영 정책으로 적어야 한다
read replica 문서에서 replication과 snapshot 생성이 항상 성공하도록 하려면, export/scaling 같은 중요한 작업 중에는 메모리 사용률을 50% 미만으로 유지하라고 조언합니다. [About read replicas](https://docs.cloud.google.com/memorystore/docs/redis/about-read-replicas)

이 조언은 꽤 공격적인 기준이지만, “fork + copy-on-write가 최악 2배까지 간다”는 설명과 일관됩니다. headroom을 남기지 않으면 스냅샷은 “있을 수도 있고 없을 수도 있는 기능”으로 전락합니다.

운영 계약에 다음을 명시하는 편이 좋습니다.

- Redis 데이터셋 메모리 사용률 목표(예: steady state 60~70% 이하)
- 스냅샷/Export 시간대에는 더 낮은 목표(예: 50% 이하)로 운영하거나, 그 시간에는 write-heavy 작업을 피한다

## 저장 위치를 다시 정의: internal snapshot은 ‘어딘가에 저장’일 뿐이고, 내가 통제할 수 있는 건 Export다
운영 문서에서 “스냅샷 저장 위치”를 요구할 때, RDB snapshots와 Export를 구분하지 않으면 답이 꼬입니다.

### RDB snapshots(내부 복구용)의 저장 위치/보존
- persistent storage에 저장되지만 사용자가 접근할 수 없습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- 마지막 성공 스냅샷 1개만 남습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

여기에는 “버킷 위치”, “스토리지 클래스”, “보존 기간”, “객체 잠금” 같은 개념을 적용할 수 없습니다. 운영 계약에 적을 수 있는 건 “주기/시작 시간/모니터링/알림/복구 기대치” 정도입니다.

### Export/Import(내가 통제 가능한 백업)의 저장 위치/보존
Export는 Cloud Storage 버킷에 RDB 파일을 저장합니다. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting) 그리고 gcloud도 `gs://.../*.rdb`로 export를 지원합니다. [gcloud redis instances export](https://docs.cloud.google.com/sdk/gcloud/reference/redis/instances/export)

운영 관점에서 “저장 위치”를 말할 수 있는 건 Export입니다.

- 성능 최적화를 위해 인스턴스와 같은 region의 버킷을 권장합니다. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)
- Export 중에도 read/write는 가능하지만 admin 작업(스케일링/업데이트/구성 변경 등)은 불가하고, latency가 증가할 수 있습니다. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)
- Import는 인스턴스가 unavailable이며, 성공 시 기존 데이터는 overwrite됩니다. 실패 시 데이터가 flush될 수도 있다는 문구가 매우 중요합니다. “복구 작업이 추가 사고로 이어질 수 있다”는 뜻입니다. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)

운영 계약에서 “백업 보존(예: 30일)” 같은 요구는 RDB snapshots가 아니라 Export 파이프라인으로 충족해야 합니다.

## 암호화(Encryption) 요구사항 재정의: persistence가 켜지면 ‘at-rest 대상’이 늘어난다
persistence가 꺼져 있을 때도 Memorystore는 네트워크/접근 통제가 핵심이지만, persistence가 켜지는 순간 “disk에 내려가는 데이터”가 생깁니다. 이때부터 암호화 요구가 현실적인 체크리스트로 바뀝니다.

### CMEK로 보호되는 범위: Backups + Persistence + 일부 보안 메타데이터
Memorystore for Redis는 CMEK(Cloud KMS)를 지원하며, persistent storage에 저장되는 고객 데이터를 CMEK로 암호화할 수 있다고 설명합니다. 특히 다음 데이터가 CMEK 대상으로 명시됩니다.

- Backups
- Persistence(RDB persistence snapshots)
- AUTH와 in-transit encryption 같은 보안 관련 메타데이터

[CMEK 문서](https://docs.cloud.google.com/memorystore/docs/redis/about-cmek)

여기서 운영적으로 중요한 제약도 같이 따라옵니다.

- CMEK는 새 인스턴스에만 적용할 수 있고, 기존 인스턴스에 사후 적용은 불가합니다. [CMEK 문서](https://docs.cloud.google.com/memorystore/docs/redis/about-cmek)
- 키 접근이 revoke되면 인스턴스가 중단(suspend)될 수 있습니다. 즉, 키 운영(rotate, disable, IAM 변경)이 Redis availability와 직결됩니다. [CMEK 문서](https://docs.cloud.google.com/memorystore/docs/redis/about-cmek)

### Export된 RDB 파일의 암호화는 ‘인스턴스 CMEK’가 아니라 ‘버킷 암호화 설정’이 결정한다
문서에 “Backups는 Cloud Storage로 export되며, export된 데이터의 암호화는 대상 버킷의 암호화 설정이 제어한다”는 취지의 설명이 있습니다. 따라서 인스턴스에 CMEK를 붙였다고 해서 Export 파일까지 자동으로 같은 키로 보호되는 구조가 아닙니다. Export 파이프라인을 운영한다면, 버킷 CMEK를 별도로 설계해야 합니다. [CMEK 문서](https://docs.cloud.google.com/memorystore/docs/redis/about-cmek)

### In-transit encryption도 계약에 포함해야 한다
persistence와 별개로, 클라이언트-서버 구간 TLS는 켜는 편이 운영에서 덜 흔들립니다. gcloud 기준으로 `--transit-encryption-mode=SERVER_AUTHENTICATION`를 지원합니다. [Manage in-transit encryption](https://docs.cloud.google.com/memorystore/docs/redis/manage-in-transit-encryption)

persistence가 기본 활성화되면서 “어차피 데이터 중요하니까 스냅샷은 켜자”로 가면, 그 다음 줄은 보통 “TLS는 나중에”가 되는데, 운영 난이도는 TLS를 나중에 켜는 쪽이 훨씬 큽니다. 특히 클라이언트 인증서 배포/CA rotation까지 감안하면 더 그렇습니다. [Manage in-transit encryption](https://docs.cloud.google.com/memorystore/docs/redis/manage-in-transit-encryption)

## 장애/데이터 손상 시 복구 리허설: 내부 스냅샷은 훈련 대상이 아니다
RDB snapshots는 내부 복구용이라 “내가 버튼 눌러서 특정 스냅샷으로 복원” 같은 리허설을 만들 수 없습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

그래서 복구 리허설은 Export/Import 기반으로 설계하는 편이 현실적입니다. 이 방식은 다음 장점이 있습니다.

- 내가 통제 가능한 artifact(gs://.../*.rdb)가 생깁니다.
- 특정 시점 복원(= 특정 export 파일 import)이 가능합니다.
- 복구 절차를 runbook으로 고정할 수 있습니다.

단점도 분명합니다.

- Import 중 인스턴스 unavailable. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)
- Import 실패 시 데이터 flush 가능. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)

그래서 리허설(runbook)은 “기존 인스턴스에 import”가 아니라 “새 인스턴스를 만들고 import 후 트래픽을 전환” 형태로 만드는 게 안전합니다. 이는 RDB snapshots 문서에서도 “복구가 너무 오래 걸리면 새 인스턴스를 만들고 트래픽을 돌린 뒤, 나중에 데이터를 옮기는 방법”을 제안하는 방향과도 일치합니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

### 리허설 시나리오(현실적인 형태)
- 운영 인스턴스: `redis-prod`
- 백업 버킷: `gs://redis-prod-backups/` (인스턴스와 동일 region 권장) [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)
- 리허설 인스턴스: `redis-restore-drill-YYYYMMDD`

#### 1) Export 수행(운영 영향이 적은 시간대)
```bash
# 예: us-central1
# 목적지 오브젝트는 반드시 .rdb 확장자
export TS=$(date -u +%Y%m%dT%H%M%SZ)
export BUCKET=gs://redis-prod-backups
export INSTANCE=redis-prod
export REGION=us-central1

gcloud redis instances export \
  ${BUCKET}/${INSTANCE}-${TS}.rdb \
  ${INSTANCE} \
  --region=${REGION}
```
참고로 export는 read/write는 가능하지만 admin 작업이 막히고 latency가 늘 수 있습니다. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)

#### 2) 복구 대상 인스턴스 생성(Terraform 또는 gcloud)
리허설 인스턴스는 운영과 같은 설정(tier, size, auth, TLS, CMEK, persistence)을 최대한 복제해야 “복구 시간/성능 특성”을 관측할 수 있습니다.

gcloud를 쓰면(예시):
```bash
export RESTORE=redis-restore-drill-20261010
export SIZE=20

# CMEK나 TLS, AUTH까지 포함하면 플래그가 늘어납니다.
# 아래는 persistence 관련 플래그가 포함될 수 있다는 점을 보여주는 수준입니다.

gcloud redis instances create ${RESTORE} \
  --region=${REGION} \
  --tier=standard \
  --size=${SIZE} \
  --persistence-mode=rdb \
  --rdb-snapshot-period=12h \
  --rdb-snapshot-start-time=2026-10-10T18:00:00Z
```
인스턴스 생성 플래그는 `--persistence-mode`, `--rdb-snapshot-period`, `--rdb-snapshot-start-time`를 지원합니다. [gcloud redis instances create](https://docs.cloud.google.com/sdk/gcloud/reference/redis/instances/create)

#### 3) Import 수행(다운타임을 감안)
```bash
export RDB=${BUCKET}/${INSTANCE}-${TS}.rdb

gcloud redis instances import ${RESTORE} \
  --region=${REGION} \
  --input-url=${RDB}
```
Import 동작은 인스턴스가 unavailable이며, 실패하면 데이터가 flush될 수 있습니다. “리허설 인스턴스”에서만 해야 하는 이유입니다. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)

#### 4) 검증(데이터 무결성 + 애플리케이션 관점의 기능 검증)
Redis는 결국 캐시/세션/큐/레이트리밋 등 “용도별 의미”가 다릅니다. 리허설 체크는 key count 같은 기계적 수치보다, 애플리케이션 기능 단위로 짜는 편이 맞습니다.

- 세션: 랜덤 샘플 사용자 n명을 골라 로그인/권한 체크가 동작하는가
- idempotency key: 중복 결제가 발생하지 않는가
- queue: pending job이 재처리돼도 문제가 없는가(중복 허용 여부 포함)

스냅샷이 point-in-time라는 사실 자체가 “중복 처리/유실 처리에 대한 애플리케이션 정책”을 요구합니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

## 모니터링과 알림: 스냅샷은 ‘설정’이 아니라 ‘건강 상태’를 감시해야 한다
persistence가 기본 활성화되면, 모니터링은 선택이 아니라 계약의 일부가 됩니다. 스냅샷은 실패할 수 있고, 연속 실패하면 마지막 정상 스냅샷은 매우 오래될 수 있습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

필수로 보는 지표는 다음 축으로 나뉩니다.

### 스냅샷 freshness/성공 여부
- `redis.googleapis.com/rdb/snapshot/last_status`: 최근 스냅샷 상태
- `redis.googleapis.com/rdb/snapshot/last_success_age`: 마지막 성공 스냅샷 시작 이후 경과 시간
- `redis.googleapis.com/rdb/snapshot/time_until_next_run`: 다음 스냅샷까지 남은 시간

[Supported monitoring metrics](https://docs.cloud.google.com/memorystore/docs/redis/supported-monitoring-metrics?hl=en)

여기서 `last_success_age`는 RPO 계약의 현실을 보여주는 숫자입니다. 이 값이 snapshot period보다 길어지는 순간, 이미 운영 계약이 깨진 상태입니다.

### 복구 시간 예측(장애 시 RTO 추정)
- `redis.googleapis.com/rdb/recovery/estimated_recovery_time`
- `redis.googleapis.com/rdb/recovery/estimated_remaining_time`

[Supported monitoring metrics](https://docs.cloud.google.com/memorystore/docs/redis/supported-monitoring-metrics?hl=en)

### 알림 정책 예시(의미 중심)
- 스냅샷 실패가 1회 발생: 경고(관측)
- 스냅샷 실패가 2회 연속 발생 또는 `last_success_age`가 2×period 초과: 장애급(대응)
- recovery 지표가 일정 시간 이상 지속: 장애급(우회 플랜 가동)

문서가 추천하는 관측/알림 방향도 `last_status`, `last_success_age` 기반입니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)

## Terraform로 표준화: 기본값에 기대지 않고, persistence를 ‘명시적으로’ 고정
콘솔 기본값이 바뀌었을 때 가장 먼저 해야 할 일은 “Terraform 모듈 인터페이스를 바꾸는 것”입니다. 인스턴스 생성 경로가 콘솔이든 IaC든, 결과 상태가 같아야 drift가 줄어듭니다.

Terraform의 `google_redis_instance`는 `persistence_config`로 RDB persistence를 설정할 수 있습니다. [google_redis_instance (Terraform)](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/redis_instance.html)

아래 예시는 “운영 기본 템플릿”으로 쓸 수 있도록, persistence뿐 아니라 삭제 방지, TLS, AUTH, 라벨까지 함께 잡는 형태입니다. (네트워크/PSA 구성은 조직마다 달라서 여기서는 authorized network가 이미 준비되어 있다는 전제로 씁니다.)

### Terraform 예시: 운영용 Memorystore for Redis 표준 리소스
```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source = "hashicorp/google"
      # 조직 표준 버전에 맞춰 pinning 하는 편이 안전합니다.
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# API 활성화
resource "google_project_service" "redis" {
  project = var.project_id
  service = "redis.googleapis.com"
}

resource "google_redis_instance" "main" {
  depends_on = [google_project_service.redis]

  name           = var.name
  display_name   = var.display_name
  region         = var.region

  tier           = var.tier                 # "STANDARD_HA" 권장(운영)
  memory_size_gb = var.memory_size_gb
  redis_version  = var.redis_version        # 예: "REDIS_7_2"

  authorized_network = var.authorized_network

  # 보안: TLS
  transit_encryption_mode = var.transit_encryption_mode  # "SERVER_AUTHENTICATION"

  # 보안: AUTH
  auth_enabled = var.auth_enabled

  # CMEK: 새 인스턴스만 가능. 키 운영이 availability에 영향을 줍니다.
  customer_managed_key = var.customer_managed_key

  # 콘솔 기본값 변화와 무관하게 persistence를 명시
  persistence_config {
    persistence_mode    = var.persistence_mode           # "RDB" 또는 "DISABLED"
    rdb_snapshot_period = var.persistence_mode == "RDB" ? var.rdb_snapshot_period : null
    rdb_snapshot_start_time = var.persistence_mode == "RDB" ? var.rdb_snapshot_start_time : null
  }

  labels = merge(var.labels, {
    "managed-by" = "terraform"
    "service"    = var.service
    "env"        = var.env
  })

  # 운영에서 실수로 destroy 하지 않기
  deletion_protection = true

  lifecycle {
    prevent_destroy = true
  }
}
```

필드 자체는 공식 provider 문서에 나와 있습니다. `persistence_config.persistence_mode`는 `DISABLED`/`RDB`를 지원하고, `rdb_snapshot_period`는 `ONE_HOUR`, `SIX_HOURS`, `TWELVE_HOURS`, `TWENTY_FOUR_HOURS`를 지원합니다. [google_redis_instance (Terraform)](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/redis_instance.html)

### 운영에서 중요한 포인트 3가지
1) persistence는 “켜고 끄는 토글”이 아니라, 운영 계약의 일부입니다. 최소한 모듈 입력으로 노출하고, 서비스별로 선택하게 해야 합니다.

2) DISABLED를 원할 때도 “아무 설정도 안 한다”로 남기면, 콘솔/버전 변화로 결과가 달라질 수 있습니다. 의도적으로 끄는 서비스는 `persistence_mode = "DISABLED"`를 명시하는 편이 안전합니다.

3) 스냅샷을 끄면 기존 스냅샷이 삭제됩니다. 이 동작은 운영에서 데이터 마지막 보루를 스스로 지우는 것이므로, 변경 관리 대상으로 올려야 합니다. [Manage RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/manage-rdb-snapshots?hl=en)

### 기존 콘솔 인스턴스를 Terraform으로 흡수할 때의 체크
콘솔로 만든 인스턴스를 나중에 Terraform으로 가져오면, persistence_config가 drift의 시작점이 됩니다. provider 문서에 import 예시가 있고, 실제 운영에서도 흡수 시점에 `terraform state show`로 현재 persistence 설정을 확인한 뒤 코드에 “그 상태를 그대로” 옮기는 게 우선입니다. [google_redis_instance (Terraform)](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/redis_instance.html)

## 비용/성능/복구 전략을 한 덩어리로 묶어 다시 쓰는 기준
persistence 기본 활성화 이후 바뀌는 건 “RDB를 켰다/껐다”가 아니라, Redis를 바라보는 시스템 설계 언어입니다.

### 비용
- RDB snapshots 자체는 “인스턴스 과금에 추가 비용이 없다”로 문서에 적혀 있습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- 하지만 copy-on-write 기반 스냅샷/Export는 메모리 headroom을 요구하므로, 결과적으로 더 큰 memory tier를 선택하게 만들 수 있습니다. 가격은 GiB-hour 기반이며 tier/region에 따라 다릅니다. [Memorystore for Redis pricing](https://cloud.google.com/memorystore/docs/redis/pricing)

내가 보는 운영 비용의 본질은 “스냅샷이 공짜”가 아니라 “스냅샷이 안정적으로 돌도록 여유를 사는 비용”입니다.

### 성능
- 스냅샷은 워크로드 패턴에 따라 latency에 영향을 줄 수 있고, 트래픽이 낮은 시간에 스케줄하라는 권고가 있습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- Export는 명시적으로 latency 증가 가능, high write load에서 메모리 2배 증가 가능이 문서에 적혀 있습니다. [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)

### 복구 전략
- Standard Tier는 failover 중심이며, failover 시 연결이 끊기고 평균 30초 unavailable 구간이 생깁니다. [High availability for Memorystore for Redis](https://docs.cloud.google.com/memorystore/docs/redis/high-availability-for-memorystore-for-redis)
- snapshot recovery는 별도의 경로이며, 스냅샷 크기에 따라 오래 걸릴 수 있고 복구 실패 시 데이터 없이 올라올 수 있습니다. [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- cross-region replication이 필요한 DR이라면 Memorystore for Redis 자체가 아니라 Valkey 같은 다른 선택지를 문서가 권합니다. [High availability for Memorystore for Redis](https://docs.cloud.google.com/memorystore/docs/redis/high-availability-for-memorystore-for-redis)

여기까지를 한 줄로 정리하면, 2026-10-08 이후 Memorystore for Redis 운영 계약은 “기본 persistence가 켜져도 Redis는 여전히 cache/near-cache 중심이며, durability는 모니터링 가능한 best effort이고, 내가 통제 가능한 백업/복구는 Export/Import로 따로 설계한다”로 다시 써야 합니다.

## 참고 자료
- [Memorystore for Redis release notes](https://docs.cloud.google.com/memorystore/docs/redis/release-notes)
- [Memorystore for Redis overview](https://docs.cloud.google.com/memorystore/docs/redis/memorystore-for-redis-overview)
- [About RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/about-rdb-snapshots)
- [Manage RDB snapshots](https://docs.cloud.google.com/memorystore/docs/redis/manage-rdb-snapshots?hl=en)
- [Supported monitoring metrics](https://docs.cloud.google.com/memorystore/docs/redis/supported-monitoring-metrics?hl=en)
- [About importing and exporting data](https://docs.cloud.google.com/memorystore/docs/redis/about-importing-exporting)
- [gcloud redis instances export](https://docs.cloud.google.com/sdk/gcloud/reference/redis/instances/export)
- [gcloud redis instances create](https://docs.cloud.google.com/sdk/gcloud/reference/redis/instances/create)
- [About customer-managed encryption keys (CMEK)](https://docs.cloud.google.com/memorystore/docs/redis/about-cmek)
- [Manage in-transit encryption](https://docs.cloud.google.com/memorystore/docs/redis/manage-in-transit-encryption)
- [High availability for Memorystore for Redis](https://docs.cloud.google.com/memorystore/docs/redis/high-availability-for-memorystore-for-redis)
- [About read replicas](https://docs.cloud.google.com/memorystore/docs/redis/about-read-replicas)
- [google_redis_instance (Terraform)](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/redis_instance.html)
- [Memorystore for Redis pricing](https://cloud.google.com/memorystore/docs/redis/pricing)
- [Best practices for Memorystore for Redis Cluster](https://docs.cloud.google.com/memorystore/docs/cluster/general-best-practices?hl=en)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
