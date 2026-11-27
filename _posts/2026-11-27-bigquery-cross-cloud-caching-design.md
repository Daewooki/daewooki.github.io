---
title: "BigQuery borderless Lakehouse cross-cloud caching 설계"
description: "cross-cloud caching(GA)의 캐시 단위·리전·네트워크 경로·비용/적중률 관측(Job 통계)까지 한 번에 정리합니다."
date: 2026-11-27 13:16:19 +0900
categories: ["Cloud", "BigQuery"]
tags: ["bigquery", "lakehouse", "cross-cloud", "caching", "egress-cost", "data-residency"]
render_with_liquid: false
---

## GA가 의미하는 것: 이제 운영 설계의 문제가 됐습니다

2026년 11월 2일 BigQuery 릴리스 노트에 **Lakehouse caching for cross-cloud data access가 GA**로 올라왔습니다. 기능 이름은 Lakehouse caching이지만, 문서에서는 cross-cloud caching으로도 부르고 있고, “disabled by default”라서 켜는 순간부터는 설계 책임이 사용자에게 넘어옵니다. [BigQuery release notes](https://docs.cloud.google.com/bigquery/docs/release-notes)[^1]

타임라인을 정확히 보면, 2026년 8월 31일에는 Preview였고(“caches data blocks locally”), 2026년 11월 2일에 GA로 승격됐습니다. 같은 릴리스 노트에서 cross-cloud connections를 “all BigQuery regions” 대상으로 GA로 안내한 날짜는 2026년 11월 25일입니다. 이 조합이 의미하는 바는 단순합니다. 멀티클라우드 분석에서 이전까지는 “데이터를 옮기느냐(복제/ETL) vs 매번 원격에서 읽느냐(egress)”의 선택지였다면, 이제는 “원격을 읽되, 읽은 조각을 내 리전에 임시로 쌓아두는” 제3의 선택지가 운영 가능한 형태로 굳었습니다. [BigQuery release notes](https://docs.cloud.google.com/bigquery/docs/release-notes)[^1]

여기서부터 핵심은 캐시가 해결해주는 문제가 egress만이 아니라는 점입니다.

- egress 비용: 반복 패턴에서 원격 object storage read를 줄입니다.
- 성능: 인터넷 경로 변동 + 원격 read 레이턴시의 영향을 적중 구간에서 제거합니다.
- 데이터 거주성(리전): 캐시를 켜는 순간, 원격 데이터의 “사본”이 BigQuery 쿼리 실행 리전에 at-rest로 임시 저장됩니다.

이 세 가지는 서로 당깁니다. 성능만 보면 내 BigQuery 워크로드가 돌아가는 곳(대개 US multi-region 또는 특정 region)에 캐시를 두고 싶고, egress만 보면 최대한 적중률을 올리고 싶으며, 거주성은 “애초에 그 리전에 사본을 두면 안 되는 데이터”를 막습니다.

## 아키텍처 관점: cross-cloud data access는 경로가 두 개입니다

borderless Lakehouse의 cross-cloud data access는 “원격 catalog/metadata와 원격 object storage를 읽는 문제”를 한 경로로 퉁치지 않습니다. 문서에서 명시적으로 **background metadata refresh**와 **query data transport**를 분리합니다. [About cross-cloud data access](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

- Metadata layer: Lakehouse runtime catalog가 원격 Apache Iceberg REST catalog endpoint(또는 Glue/Unity Catalog/Snowflake Horizon Catalog 등)로부터 namespace/table metadata를 주기적으로 sync합니다. 이 경로는 기본이 public internet(TLS)이고, 필요하면 `--metadata-service-directory-name`로 Cross-Cloud Interconnect 경로(정확히는 Service Directory 기반 라우팅)로 보낼 수 있습니다. [About cross-cloud data access](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

- Query transport: 실제 쿼리가 원격 object storage(Amazon S3 또는 Azure Blob/ADLS Gen2)에서 파일을 읽는 데이터 경로입니다. 이것도 기본은 public internet(TLS)이고, `--service-directory-name`로 Cross-Cloud Interconnect 라우팅이 가능합니다. [Supported regions and capabilities](https://docs.cloud.google.com/lakehouse/docs/regions-capabilities-cross-cloud-connections)[^3]

여기서 “캐시”는 query transport가 읽어온 내용을 Google Cloud 쿼리 실행 리전에 블록 단위로 저장해두는 기능입니다. 즉, 캐시는 network path의 대체물이 아니라, network read 자체를 줄이는 장치입니다.

## BigQuery cached results와 cross-cloud caching은 완전히 다른 캐시입니다

이 주제를 처음 접하면 대부분 “BigQuery cached results가 이미 있잖아?”에서 출발합니다. 둘은 캐시의 대상, 무효화 기준, 그리고 비용 의미가 다릅니다.

### BigQuery cached results: 쿼리 결과 캐시(논리 캐시)

BigQuery의 cached results는 “동일 쿼리(및 몇 가지 조건)”에서 결과를 임시 테이블 형태로 재사용하는 기능입니다. 캐시에서 결과가 나왔는지 여부는 job 통계 `statistics.query.cacheHit`로 확인하고, cacheHit이면 쿼리 비용이 청구되지 않는다는 점이 중요합니다. [Use cached query results](https://docs.cloud.google.com/bigquery/docs/cached-results)[^4]

특징을 요약하면:

- 캐시 단위: 결과 집합(쿼리 결과)
- 효과: 쿼리 실행 자체를 생략할 수 있음
- 관측: `statistics.query.cacheHit == true`
- 비용: cacheHit이면 “쿼리 비용이 없다”고 문서에 명시
- 제약: destination table 지정 등 캐시 예외가 많고, 24시간 캐시 수명 규칙이 있음(예외 포함)

### cross-cloud caching(Lakehouse caching): 원격 파일 블록 캐시(물리 캐시)

반면 cross-cloud caching은 **원격 object storage에서 읽은 file blocks를 로컬(쿼리 실행 리전) 캐시에 저장**합니다. 이후 “같은 file blocks”를 읽는 다른 쿼리라도 캐시에서 읽힙니다. 즉, SQL 텍스트가 같아야 하는 결과 캐시와 달리, 스캔 패턴이 겹치면 이득이 납니다. [About cross-cloud data access – Intelligent caching](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

특징을 요약하면:

- 캐시 단위: 결과가 아니라 **file blocks**
- 효과: 원격 object storage read(그리고 그에 따른 egress)를 적중 구간에서 제거
- 관측: job 통계의 `objectStorageStats`에서 `cacheBytesRead` / `objectStorageBytesRead`로 확인
- 비용: BigQuery 쿼리 비용은 그대로(캐시는 “쿼리를 공짜로” 만들지 않음)

이 차이를 분명히 해두면, 운영에서 헷갈리는 포인트가 줄어듭니다.

- 결과 캐시는 “쿼리 비용 0”까지도 만들 수 있지만 조건이 까다롭고, cross-cloud egress와는 무관할 때가 많습니다.
- cross-cloud caching은 “원격 read 비용(egress) + 레이턴시”를 줄이지만, compute 비용을 직접 깎는 장치는 아닙니다.

## 캐시는 어떤 단위로, 어디에, 어떤 규칙으로 쌓이나

문서가 반복해서 강조하는 표현이 “file blocks”입니다. “파일 전체”도 아니고 “테이블”도 아닙니다. 이게 의미하는 바는 다음과 같습니다.

### 블록 단위 캐시는 쿼리 패턴에 민감합니다

캐시는 “같은 파일을 또 읽을 때”만 이득이 아니라, “같은 블록을 읽을 때” 이득입니다. 예를 들어 Parquet를 날짜 partition으로 나누고(폴더 프리픽스) 쿼리는 항상 최근 7일만 본다면:

- 첫 쿼리: 최근 7일의 파일 블록들이 원격에서 읽히고, 동시에 캐시에 적재
- 둘째 쿼리(같은 범위): 대부분 캐시 적중
- 셋째 쿼리(최근 14일): 앞 7일은 적중, 뒤 7일은 miss

이런 형태가 되기 때문에, cross-cloud caching은 “반복되는 스캔 윈도우”에서 강합니다.

### 캐시는 Google이 용량/보존/eviction을 관리합니다

cross-cloud caching은 사용자가 캐시 크기나 TTL을 고정하는 모델이 아닙니다. 문서에 “Google automatically manages cache capacity, retention, and eviction”라고 명시돼 있습니다. 이 말은 곧, 적중률은 시간이 지나도 고정값이 아니라 워크로드/캐시 경쟁/리전별 상황에 따라 변동한다는 뜻입니다. [About cross-cloud data access – Intelligent caching](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

### “stale 데이터”를 캐시로 읽는 걸 막기 위한 검증 단계가 있습니다

캐시가 위험해지는 지점은 “원격 파일이 바뀌었는데도 캐시가 예전 블록을 내주는 상황”과 “권한이 회수됐는데 캐시로 우회하는 상황”입니다. 문서는 이 부분을 정면으로 다룹니다.

- 캐시로 서빙하기 전에 **매 쿼리마다 원격 스토리지에서 metadata와 access permissions를 검증**한다고 합니다.

즉, 캐시가 있어도 control-plane 검증이 남아있고, 이 검증이 네트워크/레지스트리 정책에 걸리면 쿼리가 실패할 수 있습니다. 단, 이 검증 덕분에 “캐시 때문에 권한 회수/데이터 변경이 반영되지 않는다”는 종류의 사고를 줄이는 설계입니다. [About cross-cloud data access – Intelligent caching](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

### 캐시는 “쿼리 실행 리전”에 저장됩니다

cross-cloud caching을 켜면, 캐시 데이터는 “connection의 Google Cloud region” 또는 “쿼리 실행 region”에 쌓입니다.

- BigQuery cross-cloud connections 문서는 “connection’s Google Cloud region에 file blocks를 캐시한다”고 씁니다. [Create cross-cloud connections](https://docs.cloud.google.com/bigquery/docs/cross-cloud-connections)[^5]
- Lakehouse 문서는 “Google Cloud query execution region에 캐시한다”고 씁니다. [Query remote data – Monitor cache usage](https://docs.cloud.google.com/lakehouse/docs/query-remote-data?hl=en)[^6]

실무에서는 둘이 같은 결론으로 수렴합니다. **어느 리전에서 쿼리를 실행시키느냐가 곧 캐시의 data residency**를 결정합니다.

## 리전 고정(데이터 거주성): 캐시를 켠 순간, 원격 데이터의 사본이 생깁니다

cross-cloud caching은 비용/성능 최적화 기능이지만, 컴플라이언스에서는 데이터 거주성 이슈로 바로 번역됩니다.

문서는 “캐시를 켜면 원격 파일의 cached copies가 쿼리가 실행되는 Google Cloud region에 at rest로 임시 저장된다”고 명시하고, 다른 관할권(EU 데이터인데 `us-east4`에서 쿼리 같은 경우)이라면 요구사항을 먼저 확인하라고 합니다. [About cross-cloud data access – Data residency](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

여기서 리전 선택은 단순히 레이턴시 문제가 아닙니다.

- (비용/성능) 데이터와 가까운 리전을 고르면 네트워크 비용과 지연이 줄어듭니다.
- (거주성) 데이터가 EU에서 벗어나면 안 되는 규정이라면, 캐시 리전도 EU여야 합니다.

BigQuery cross-cloud connections 문서는 AWS region에 대해 “가장 가까운 BigQuery standard region”을 표로 제공합니다. 이 표는 성능/비용 관점의 권고지만, 컴플라이언스 관점에서는 “허용 가능한 관할권에 있는 region만 후보로 두고, 그중 최단거리”로 재해석하는 게 안전합니다. [Create cross-cloud connections – Region recommendations](https://docs.cloud.google.com/bigquery/docs/cross-cloud-connections)[^5]

### 암호화와 CMEK: 규제 산업에서 걸리는 지점

문서에 따르면 cached data는 Google-owned/Google-managed key로 at-rest 암호화되고, **CMEK는 지원하지 않습니다**. 그리고 조직 정책 `constraints/gcp.restrictNonCmekServices`가 강제돼 있으면, Lakehouse가 자동으로 caching을 비활성화하고(쿼리는 실행되지만 원격에서 직접 읽음) 그 결과로 적중률이 0이 될 수 있습니다. [About cross-cloud data access – Encryption and CMEK](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

이건 설계 상 중요한 함정입니다.

- “캐시 켰는데 비용이 안 줄어요”의 원인이 기술이 아니라 정책일 수 있습니다.
- 정책 때문에 비활성화되면, 동일 쿼리라도 항상 objectStorageBytesRead로만 잡힙니다.

## 인터넷 vs Cross-Cloud Interconnect: 캐시와 경로 선택은 서로 독립이지만 함께 최적화됩니다

cross-cloud caching을 이해할 때 흔한 오해는 “캐시를 켜면 Cross-Cloud Interconnect가 필요 없다”입니다. 캐시는 반복 구간에서 네트워크 read를 없애지만, 아래 이유로 경로 설계가 여전히 중요합니다.

1) 첫 쿼리는 무조건 원격에서 읽어야 캐시가 채워집니다.
2) 캐시 적중이어도, 앞서 말한 원격 metadata/permission 검증이 남아있습니다.
3) 캐시 eviction이 발생하면 다시 원격 read가 시작됩니다.

borderless Lakehouse는 Cross-Cloud Interconnect를 쓸 때도 “query transport”와 “background metadata refresh”를 분리해서 라우팅할 수 있게 해둔 상태입니다. [Supported regions and capabilities](https://docs.cloud.google.com/lakehouse/docs/regions-capabilities-cross-cloud-connections)[^3]

- Query transport만 Interconnect로: object storage read를 전용 경로로 보내 egress/성능 예측성을 개선
- Metadata refresh만 Interconnect로: 원격 catalog endpoint를 private endpoint로 잠가둔 조직에서 필수
- 둘 다 Interconnect로: public internet을 경유하면 안 되는 규정(망 분리/정책)에서 선택

문서가 public internet 경로의 단점으로 “variable latency(라우팅/혼잡에 따라 성능이 덜 예측 가능)”를 명시합니다. 반복 워크로드에서 캐시 적중률이 높아지면 평균 지연은 내려가겠지만, eviction이나 cold start 구간은 여전히 public internet 품질에 끌려갑니다. 그래서 캐시는 평균을 낮추고, Interconnect는 최악치를 줄이는 역할로 보는 편이 맞습니다. [About cross-cloud data access](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

운영에서 자주 만나는 형태는 이렇습니다.

- 개발/PoC 단계: public internet + caching enabled로 egress와 성능 효과를 수치화
- 운영 전환: 규제/망 정책이 있으면 metadata refresh부터 Interconnect로 옮김
- 대규모 반복 분석: query transport도 Interconnect로 옮기고, caching으로 반복 구간을 로컬화

## 비용 모델: egress 절감 vs 캐시 적중률을 어떻게 계산해야 하나

cross-cloud caching은 “켜면 무조건 절감”이 아닙니다. 절감은 적중률 함수이고, 적중률은 워크로드 함수입니다. 문서도 “actual egress cost savings depend on query patterns, how frequently your source files change, and cache retention in the target region”이라고 못 박습니다. [About cross-cloud data access – Intelligent caching](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

여기서 내가 쓰는 단순화 모델은 아래입니다.

- `remote_read_bytes` = `objectStorageBytesRead`
- `cache_read_bytes` = `cacheBytesRead`
- `total_read_bytes` = `remote_read_bytes + cache_read_bytes`
- **cache hit share(바이트 기준)** = `cache_read_bytes / total_read_bytes`

문서가 제공하는 지표가 “바이트”이기 때문에, 적중률도 “쿼리 수 기준 hit ratio”보다 바이트 기준이 더 직접적입니다. egress 비용은 결국 전송량에 비례하는 경우가 많기 때문입니다(정확한 과금은 각 클라우드/계약 조건에 의존).

이제 기대 절감액을 거칠게 보면:

- egress 단가가 `E`($/GiB)라고 할 때
- 반복 실행되는 동일/유사 워크로드의 기간 합산에서
- **절감액 ≈ `cache_read_bytes * E`**

반대로 cross-cloud caching이 비용 절감을 못 만드는 대표 패턴도 같이 봐야 합니다.

- 원격 파일이 자주 바뀌어 블록이 자주 무효화되거나, 결과적으로 같은 블록을 다시 읽지 못하는 경우
- 쿼리마다 스캔 범위가 넓고 변화폭이 커서 블록 재사용이 낮은 경우
- 캐시 retention 경쟁(같은 리전에 많은 팀/잡이 몰림)으로 eviction이 빠른 경우
- 규정/정책(CMEK 제한)으로 캐시가 자동 비활성화된 경우

캐시는 저장 비용이 별도로 청구되는 구조라기보다 managed feature에 가까운데, 그만큼 “내가 캐시 용량을 돈으로 사서 보장한다” 같은 방식이 어렵습니다. 그래서 운영에서는 hit share를 꾸준히 관측하고, 워크로드를 캐시 친화적으로 정리(파티션/클러스터/스캔 윈도우 고정)하는 게 더 중요해집니다.

내가 LLM Prompt Caching을 비용 최적화로 다뤘을 때도 똑같은 결론이었는데, 캐시는 비용 모델이 아니라 워크로드 모델입니다. (관점만 연결해두고, 구체 내용은 예전 글로 남깁니다: [토큰을 70% 줄이는 2026년식 LLM 비용 최적화: **Prompt Caching + 모델 Routing** 실전 설계](https://daewooki.github.io/posts/70-2026-llm-prompt-caching-routing-2/))

## 관측: Job 통계로 “얼마나 캐시를 탔는지”를 숫자로 만들기

cross-cloud caching이 운영에 들어가려면, 콘솔에서 체감이 아니라 숫자로 회계가 돼야 합니다. Google 문서는 관측 방법을 명확히 두 갈래로 제시합니다.

1) BigQuery 콘솔 Job details에서 확인
2) BigQuery API 또는 `bq show`로 `JobStatistics2` 통계를 조회

그리고 cross-cloud caching의 관측 지표는 cached results와 다릅니다.

- cached results: `statistics.query.cacheHit` (boolean) [Use cached query results](https://docs.cloud.google.com/bigquery/docs/cached-results)[^4]
- cross-cloud caching: `statistics.query.objectStorageStats[].cacheBytesRead`, `objectStorageBytesRead` [Query remote data – Monitor cache usage](https://docs.cloud.google.com/lakehouse/docs/query-remote-data?hl=en)[^6]

### 가장 빠른 확인: bq show로 job JSON 보기

Lakehouse 문서는 `bq show --format=prettyjson --job=true JOB_ID`로 확인하라고 안내합니다. [Query remote data](https://docs.cloud.google.com/lakehouse/docs/query-remote-data?hl=en)[^6]

이때 JSON에서 보면:

- `statistics.query.cacheHit`가 `true`면 cached results(결과 캐시)
- `statistics.query.objectStorageStats`에 `cacheBytesRead`가 잡히면 cross-cloud caching(블록 캐시)

둘이 동시에 true가 될 수 있느냐는 질문이 생기는데, 성격이 달라서 이론상 케이스가 꼬일 수 있습니다. 다만 운영에서 중요한 건 “cross-cloud egress 절감”이라면 결과 캐시가 아니라 objectStorageStats를 회계 기준으로 잡는 편이 안전합니다.

### 운영 지표화: INFORMATION_SCHEMA JOBS 뷰로 집계

`bq show`는 단건 확인에 좋지만, 비용/절감 리포트를 만들려면 집계가 필요합니다. BigQuery는 `INFORMATION_SCHEMA.JOBS*` 뷰에 cross-cloud caching 관련 필드를 넣었습니다. 문서에 `object_storage_bytes_read`, `cache_bytes_read`, `cloud_provider`가 표기돼 있습니다. [JOBS view](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs)[^7]

이게 의미하는 바는 큽니다.

- “캐시 적중률이 몇 %였나”를 팀/프로젝트/라벨별로 집계할 수 있습니다.
- “어느 클라우드(AWS/AZURE)에서 원격 read가 많았나”를 분리할 수 있습니다.
- FinOps 관점에서 월간 egress 절감 추정치를 자동 생성할 수 있습니다.

## 실전 예제: cross-cloud connection에 caching을 켜고, Job 통계를 읽어 적중률을 계산

아래는 가장 현실적인 시나리오로 잡았습니다.

- 원격: AWS S3에 Parquet 로그(날짜 프리픽스 partition)
- BigQuery: 표준 region(예: `us-east4`)
- 목적: 같은 기간을 반복 탐색하는 분석(대시보드/리포트)
- 관측: 같은 쿼리를 2회 실행해 `cacheBytesRead` 증가를 확인

예제는 BigQuery cross-cloud connection 기준으로 작성했지만, Lakehouse federated catalog에서도 관측 포인트는 같습니다(결국 job 통계에서 objectStorageStats를 봄).

### 0) 전제

- `gcloud` / `bq` CLI가 설치돼 있고 인증이 되어 있어야 합니다.
- AWS IAM role/trust policy 설정은 프로젝트마다 다르고, 문서의 “Add a trust policy to the AWS role” 단계를 그대로 따라야 합니다. 여기서는 BigQuery 쪽 캐시/관측에 집중합니다. [Create cross-cloud connections](https://docs.cloud.google.com/bigquery/docs/cross-cloud-connections)[^5]

### 1) connection 생성: crossCloudCacheOptions.enabled=true

BigQuery 문서는 `bq mk --connection`에서 `--properties`에 `crossCloudCacheOptions.enabled`를 넣어 caching을 opt-in 하라고 안내합니다. [Create cross-cloud connections](https://docs.cloud.google.com/bigquery/docs/cross-cloud-connections)[^5]

```bash
# 변수 예시
export PROJECT_ID="my-project"
export LOCATION="us-east4"              # 표준 BigQuery region
export CONNECTION_ID="aws-lakehouse"
export AWS_ACCOUNT_ID="123456789012"
export AWS_ROLE_NAME="bqCrossCloudReadRole"

bq mk --connection \
  --connection_type='AWS' \
  --location="${LOCATION}" \
  --project_id="${PROJECT_ID}" \
  --properties='{
    "accessRole": {"iamRoleId": "arn:aws:iam::'"${AWS_ACCOUNT_ID}"':role/'"${AWS_ROLE_NAME}"'"},
    "crossCloudCacheOptions": {"enabled": true}
  }' \
  "${CONNECTION_ID}"
```

여기서 제일 중요한 건 LOCATION입니다.

- BigQuery Omni location이 아니라 **표준 BigQuery location**을 선택해야 합니다. [Create cross-cloud connections](https://docs.cloud.google.com/bigquery/docs/cross-cloud-connections)[^5]
- 그 LOCATION이 곧 캐시가 쌓이는 Google Cloud region이 됩니다.

### 2) external table 생성

S3 Parquet를 외부 테이블로 잡는 예시는 문서에 그대로 있습니다. [Create cross-cloud connections – AWS examples](https://docs.cloud.google.com/bigquery/docs/cross-cloud-connections)[^5]

```sql
-- dataset(schema) 생성: location을 connection과 맞춥니다.
CREATE SCHEMA IF NOT EXISTS `my-project.aws_raw_data`
  OPTIONS (location = 'us-east4');

-- S3 Parquet 외부 테이블
CREATE OR REPLACE EXTERNAL TABLE `my-project.aws_raw_data.sales_parquet`
WITH CONNECTION `us-east4.aws-lakehouse`
OPTIONS (
  format = 'PARQUET',
  uris = ['s3://my-data-bucket/sales/year=2025/*']
);
```

### 3) 쿼리 2회 실행: job_id를 고정해 관측을 단순화

`bq` CLI는 `--job_id` 플래그를 지원합니다. 이걸 쓰면 실행한 잡을 다시 찾기가 쉬워집니다. [bq command-line tool reference](https://docs.cloud.google.com/bigquery/docs/reference/bq-cli-reference)[^8]

```bash
export JOB1="bqjob_crosscloud_cache_test_1"
export JOB2="bqjob_crosscloud_cache_test_2"

bq query \
  --location="${LOCATION}" \
  --use_legacy_sql=false \
  --job_id="${JOB1}" \
  '
  SELECT
    store_id,
    COUNT(*) AS orders,
    SUM(amount) AS gross
  FROM `my-project.aws_raw_data.sales_parquet`
  WHERE order_date >= DATE("2025-11-01")
    AND order_date <  DATE("2025-11-08")
  GROUP BY store_id
  ORDER BY gross DESC
  LIMIT 100
  '

bq query \
  --location="${LOCATION}" \
  --use_legacy_sql=false \
  --job_id="${JOB2}" \
  '
  SELECT
    store_id,
    COUNT(*) AS orders,
    SUM(amount) AS gross
  FROM `my-project.aws_raw_data.sales_parquet`
  WHERE order_date >= DATE("2025-11-01")
    AND order_date <  DATE("2025-11-08")
  GROUP BY store_id
  ORDER BY gross DESC
  LIMIT 100
  '
```

첫 번째 잡은 캐시 cold start라서 `objectStorageBytesRead`가 크고 `cacheBytesRead`는 0에 가깝게 시작하는 게 정상입니다. 두 번째 잡부터 동일 블록을 읽으면 `cacheBytesRead`가 늘어납니다(단, eviction/정책 비활성화/파일 변경이 있으면 예외).

### 4) bq show로 objectStorageStats 읽기

Lakehouse 문서가 안내하는 방식 그대로 갑니다. [Query remote data – Monitor cache usage](https://docs.cloud.google.com/lakehouse/docs/query-remote-data?hl=en)[^6]

```bash
bq --location="${LOCATION}" show --format=prettyjson --job=true "${JOB1}" > job1.json
bq --location="${LOCATION}" show --format=prettyjson --job=true "${JOB2}" > job2.json

# jq가 있으면 핵심만 뽑아서 비교
cat job1.json | jq '.statistics.query.objectStorageStats'
cat job2.json | jq '.statistics.query.objectStorageStats'
```

문서에 따르면 `objectStorageStats`는 cloud provider별 엔트리 리스트이고, 최소한 다음 필드가 나옵니다.

- `cloudProvider`
- `cacheBytesRead`
- `objectStorageBytesRead`

이 필드 의미는 공식 문서에 그대로 정리돼 있습니다. [Query remote data](https://docs.cloud.google.com/lakehouse/docs/query-remote-data?hl=en)[^6]

예상 출력 형태(값은 예시):

```json
[
  {
    "cloudProvider": "AWS",
    "cacheBytesRead": "34359738368",
    "objectStorageBytesRead": "2147483648"
  }
]
```

여기서 바이트 기준 hit share는:

- `34359738368 / (34359738368 + 2147483648) ≈ 94%`

이 수치가 바로 “egress 절감이 가능한 비율”의 1차 근사치가 됩니다.

### 5) INFORMATION_SCHEMA로 기간 집계(대시보드/리포트용)

단건 비교가 끝나면, 운영에서는 JOBS 뷰로 집계합니다. 문서에 `cache_bytes_read` / `object_storage_bytes_read`가 JOBS 뷰 필드로 명시돼 있습니다. [JOBS view](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs)[^7]

아래 쿼리는 “최근 24시간 query jobs”에서 캐시 적중 바이트/원격 바이트를 집계합니다.

```sql
-- LOCATION에 따라 region-us-east4 같은 리전 스코프를 맞춥니다.
-- (예: `region-us-east4`.INFORMATION_SCHEMA.JOBS_BY_PROJECT)

WITH jobs AS (
  SELECT
    job_id,
    creation_time,
    project_id,
    user_email,
    cache_hit,
    labels,
    object_storage_stats
  FROM `region-us-east4`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
  WHERE job_type = 'QUERY'
    AND creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
)
SELECT
  project_id,
  COUNT(*) AS query_jobs,
  SUM((SELECT SUM(s.cache_bytes_read) FROM UNNEST(object_storage_stats) s)) AS cache_bytes_read,
  SUM((SELECT SUM(s.object_storage_bytes_read) FROM UNNEST(object_storage_stats) s)) AS object_storage_bytes_read,
  SAFE_DIVIDE(
    SUM((SELECT SUM(s.cache_bytes_read) FROM UNNEST(object_storage_stats) s)),
    SUM((SELECT SUM(s.cache_bytes_read + s.object_storage_bytes_read) FROM UNNEST(object_storage_stats) s))
  ) AS cache_hit_share_bytes
FROM jobs
GROUP BY project_id
ORDER BY cache_hit_share_bytes DESC;
```

여기서 `cache_hit`은 cached results(결과 캐시) 여부라서, cross-cloud caching 평가에는 보조 지표로만 두는 편이 낫습니다. 핵심은 object_storage_stats의 바이트 집계입니다.

## 함정과 트레이드오프: 세 꼭짓점(egress·성능·거주성)이 충돌하는 지점

### 1) 캐시는 “리전 단위”로 의미가 생깁니다

캐시는 쿼리 실행 리전에 쌓입니다. 그래서 아래 두 문장은 같은 말입니다.

- 캐시 적중률을 올리려면 쿼리 실행 리전을 고정해야 합니다.
- 거주성 규정 때문에 쿼리 실행 리전을 고정해야 합니다.

하지만 그 고정이 성능 최적점과 다를 수 있습니다. 예를 들어 원격 데이터가 `eu-west-1`인데, 분석팀이 `us-east4`에 고정된 BigQuery 프로젝트에서 모두 실행하면, 캐시를 켜는 순간 EU 데이터를 US에 임시 저장하는 꼴이 됩니다. 문서가 딱 그 예시를 들며 주의를 줍니다. [About cross-cloud data access – Data residency](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

### 2) 캐시가 있으면 네트워크가 필요 없어지는 게 아닙니다

캐시는 원격 read를 줄이지만, 캐시 적중 전에 **원격 검증**이 있고, cold start/eviction 이후에는 다시 원격 read가 발생합니다. 네트워크 경로(public internet vs Cross-Cloud Interconnect)는 평균이 아니라 tail latency와 정책 준수에 관여합니다. [About cross-cloud data access](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

### 3) CMEK 강제 조직에서는 캐시가 아예 동작하지 않을 수 있습니다

CMEK 미지원은 규제 산업에서 실제로 기능을 무력화시키는 트리거가 됩니다. 조직 정책 `constraints/gcp.restrictNonCmekServices`가 있으면 Lakehouse가 자동으로 caching을 끕니다. 이 경우 “캐시 enabled” 설정만 보고는 절대 판단할 수 없고, objectStorageStats로 실제 동작을 확인해야 합니다. [About cross-cloud data access – Encryption and CMEK](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

### 4) 파일 변경 빈도가 높으면 캐시가 이득을 못 냅니다

문서가 egress 절감이 query patterns뿐 아니라 “how frequently your source files change”에 달려있다고 못박은 이유가 여기에 있습니다. 파일이 자주 바뀌면 동일 블록 재사용이 줄고, 그 결과 cacheBytesRead가 잘 안 늘어납니다. [About cross-cloud data access – Intelligent caching](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)[^2]

운영에서 내가 보는 실전 처방은 데이터 레이아웃 쪽입니다.

- 자주 바뀌는 작은 파일을 계속 덧붙이는 대신, 일정 주기로 compaction(파일 병합)해서 “바뀌지 않는 과거 구간”을 만드는 것이 캐시 친화적입니다.
- 대시보드가 반복해서 읽는 구간(최근 7일/30일)을 물리적으로 분리하면 블록 재사용이 늘어납니다.

## 도입 판단 기준: 언제 cross-cloud caching이 정답이고, 언제 아닌가

**정답인 경우**

- 멀티클라우드에서 분석 워크로드가 반복되고(대시보드/정기 리포트/피처 스토어 스캔), 같은 기간/같은 파티션을 계속 읽는다.
- 데이터 복제/ETL을 조직 정책이나 비용 때문에 피하고 싶다.
- “원격에 두되 반복 구간은 로컬화”라는 절충이 허용된다.

**아닌 경우**

- 데이터 거주성 규정상 BigQuery 실행 리전에 원격 데이터 사본을 두면 안 된다.
- CMEK 강제가 있어 캐시가 자동 비활성화되는 조직 정책을 피할 수 없다.
- 워크로드가 대부분 ad-hoc 대규모 풀스캔이라 블록 재사용이 낮다.

내 결론은 간단합니다. cross-cloud caching은 멀티클라우드 분석에서 egress 비용을 “한 번 내고 여러 번 쓰는” 구조로 바꾸는 장치인데, 그 대가로 데이터 거주성(리전) 결정이 훨씬 더 중요해졌습니다. 운영 적용은 설정 체크리스트가 아니라, 리전/경로/정책을 포함한 삼각형을 고정하는 설계로 접근하는 편이 맞습니다.

## 참고 자료

- [BigQuery release notes](https://docs.cloud.google.com/bigquery/docs/release-notes)
- [About cross-cloud data access](https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access)
- [Query remote data](https://docs.cloud.google.com/lakehouse/docs/query-remote-data)
- [Create cross-cloud connections](https://docs.cloud.google.com/bigquery/docs/cross-cloud-connections)
- [Supported regions and capabilities](https://docs.cloud.google.com/lakehouse/docs/regions-capabilities-cross-cloud-connections)
- [Use cached query results](https://docs.cloud.google.com/bigquery/docs/cached-results)
- [bq command-line tool reference](https://docs.cloud.google.com/bigquery/docs/reference/bq-cli-reference)
- [JOBS view](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs)
- [Manage jobs](https://docs.cloud.google.com/bigquery/docs/managing-jobs)

[^1]: <https://docs.cloud.google.com/bigquery/docs/release-notes>
[^2]: <https://docs.cloud.google.com/lakehouse/docs/about-cross-cloud-data-access>
[^3]: <https://docs.cloud.google.com/lakehouse/docs/regions-capabilities-cross-cloud-connections>
[^4]: <https://docs.cloud.google.com/bigquery/docs/cached-results>
[^5]: <https://docs.cloud.google.com/bigquery/docs/cross-cloud-connections>
[^6]: <https://docs.cloud.google.com/lakehouse/docs/query-remote-data?hl=en>
[^7]: <https://docs.cloud.google.com/bigquery/docs/information-schema-jobs>
[^8]: <https://docs.cloud.google.com/bigquery/docs/reference/bq-cli-reference>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
