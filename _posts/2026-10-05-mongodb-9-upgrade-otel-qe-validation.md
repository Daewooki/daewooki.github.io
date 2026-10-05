---
title: "MongoDB 9.0 업그레이드 리스크와 Queryable Encryption·OTel 검증"
description: "MongoDB 9.0 GA 이후 운영팀이 실제로 부딪히는 업그레이드 리스크(FCV/드라이버/Atlas 연동)와 암호화·관측성 검증 항목을 정리합니다."
date: 2026-10-05 10:38:36 +0900
categories: ["News", "Database"]
tags: ["mongodb", "upgrade", "fcv", "queryable-encryption", "opentelemetry", "atlas"]
render_with_liquid: false
---

## 2026-09-29 MongoDB 9.0 GA가 운영팀에 남긴 것

MongoDB가 **2026-09-29**에 MongoDB 9.0 GA를 발표했습니다. 공식 제품 업데이트 페이지는 9.0의 핵심을 성능(최대 35% baseline query 성능 개선), Queryable Encryption의 prefix/suffix/substring 검색 GA, “enhanced native OpenTelemetry integration”, 그리고 Atlas에서의 트래픽 급증 보호( Intelligent Workload Management, IWM)로 요약합니다. 
- [MongoDB 9.0 is Now Available](https://www.mongodb.com/products/updates/mongodb-9-0-is-now-available/)

보도자료는 수치까지 더 공격적으로 적습니다. MongoDB 8.0 대비 최대 2x throughput, 35% faster reads, 30% faster updates를 내세웠고, 관측성은 “enhanced OpenTelemetry support”라는 표현으로 언급합니다.
- [MongoDB 9.0 및 Atlas Infinite 발표 보도자료](https://www.mongodb.com/company/newsroom/press-releases/mongodb-launches-mongodb-9-0-the-best-version-ever-built-and-atlas-infinite-for-ai-scale-demand)

한편 MongoDB Server 릴리스 노트는 9.0.0의 날짜를 **2026-09-28**로 표기하고, GA 직후(혹은 거의 동시에) 9.0.1/9.0.2도 2026-09-28로 올라와 있습니다. 운영 관점에서는 “GA 발표일”보다 “내가 어떤 patch를 깔 거냐”가 더 중요하니, 첫 업그레이드 리허설부터 9.0.0 고정으로 가지 말고 9.0.x 최신 patch 기준으로 계획을 잡는 편이 안전합니다.
- [MongoDB 9.0 릴리스 노트](https://www.mongodb.com/docs/manual/release-notes/9.0/)

오늘이 **2026-10-05 KST**이므로, GA(2026-09-29)로부터 7일 이내라는 타이밍은 맞습니다. 지금 착수하기 좋은 이유는 단순합니다.

1) FCV를 포함한 메이저 업그레이드 절차는 언제나 “기술적 난이도”보다 “조직의 변경 관리”가 병목입니다. 시간을 벌수록 성공확률이 올라갑니다.

2) Queryable Encryption의 substring 계열은 기능 소개보다 운영 비용(쓰기 증폭, 메타데이터 컬렉션 증가, 모니터링 신호 변화)을 미리 계산해야 합니다.

3) OpenTelemetry는 도입 자체보다 파이프라인(Collector, TLS, 네이밍, 대시보드 마이그레이션)이 부러지는 지점이 반복됩니다.

이 글은 신기능 소개가 아니라, 운영팀이 업그레이드를 리허설하면서 무엇을 확인해야 하는지(FCV/드라이버/Atlas 연동)와 Queryable Encryption·OTel을 어떻게 검증할지에 집중합니다.

## 업그레이드 경로를 FCV 관점에서 다시 그려야 합니다

MongoDB 업그레이드에서 운영 리스크의 1순위는 “바이너리 업그레이드”가 아니라 FCV입니다. 공식 업그레이드 문서는 9.0으로 올리려면 최소 8.0/8.3 라인에 올라와 있어야 한다고 못박습니다.
- [Upgrade 8.3 Standalone to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-standalone/)

여기서 중요한 포인트는 두 가지입니다.

### 1) 바이너리 업그레이드와 FCV 업그레이드는 분리해야 합니다

MongoDB 문서는 9.0 바이너리로 올린 뒤에도 “바로 FCV를 9.0으로 올리지 말고 burn-in을 두라”는 식의 뉘앙스를 분명히 갖고 있습니다. 업그레이드 문서에는 FCV 9.0 활성화가 downgrade를 복잡하게 만들 수 있고, “확신이 생기면 그때 켜라”는 권고가 들어가 있습니다.
- [Upgrade 8.3 Standalone to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-standalone/)

실무적으로는 다음처럼 두 단계로 나눠 잡습니다.

- (A) 바이너리만 9.0으로 올리고, FCV는 8.3(혹은 8.0)으로 유지하며 1~2주 운영
- (B) 관측성/성능/기능 동작이 “업무적으로” 확인되면 setFeatureCompatibilityVersion으로 FCV 9.0 전환

이 분리를 지키면, 문제가 생겼을 때 rollback의 선택지가 남습니다.

### 2) FCV는 “클러스터가 이해하는 프로토콜/기능 레벨”입니다

MongoDB 내부 문서(소스 레벨 README)는 FCV를 “업그레이드/다운그레이드 안전성을 제공하는 버저닝 메커니즘”으로 설명합니다. 즉, 바이너리를 올렸다고 곧바로 새 기능을 다 쓰는 게 아니라, FCV가 그 기능을 활성화하는 스위치에 가깝습니다.
- [FCV and feature flags (MongoDB 소스)](https://github.com/mongodb/mongo/blob/master/src/mongo/db/repl/FCV_AND_FEATURE_FLAG_README.md)

운영팀 관점에서는 FCV 전환을 다음과 같이 취급하는 편이 맞습니다.

- FCV 전환은 “스키마 변경”에 준하는 변경이다
- FCV 전환은 “되돌리기 비용이 높은 변경”이다
- 따라서 FCV 전환 전후는 반드시 관측성 신호(지표/로그/알람) 기준선을 다시 찍어야 한다

그리고 9.0 업그레이드 문서는 FCV를 9.0으로 올릴 때 `confirm: true`가 필요하다고 명시합니다. 이게 사소한 듯 보이지만, 자동화(Ansible, Helm hook, runbook)에서 실수로 confirm을 빼먹고 실패하는 경우가 반복됩니다.
- [Upgrade 8.3 Standalone to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-standalone/)

## 드라이버/암호화 라이브러리 리스크: “호환”과 “지원”은 다릅니다

업그레이드 체크리스트에서 “드라이버 호환성 확인”이 항상 들어가지만, MongoDB 9.0에서는 Queryable Encryption과 맞물리면서 리스크가 커집니다.

### 드라이버는 Server 9.0과의 기본 호환을 확인해야 합니다

MongoDB는 공식적으로 드라이버/클라이언트 라이브러리와 서버 버전 간 호환 테이블을 제공합니다. 운영에서 중요한 해석은 이것입니다.

- “9.0과 호환”이 확인된 드라이버라도, 팀이 실제로 사용하는 기능(트랜잭션, 압축, CSFLE, QE, 로깅, OTel)이 깨지지 않는지는 별개입니다.
- 호환 테이블은 최소 조건일 뿐, QA 통과를 보장하지 않습니다.

- [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/)

### Queryable Encryption에서 preview → GA 전환은 실제로 breaking change가 됩니다

9.0 호환성 문서는 Queryable Encryption의 `prefixPreview/suffixPreview/substringPreview`가 9.0에서 제거되었고, `prefix/suffix/substring`으로 바꾸라고 못박습니다. 그리고 “text algorithm”에서 “string algorithm”으로 옮기라는 지시까지 포함돼 있습니다.
- [Compatibility Changes in MongoDB 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-compatibility/)

이건 단순 API 이름 변경이 아니라, 다음 운영 리스크를 동반합니다.

- pre-9.0에서 preview 쿼리 타입으로 생성한 encrypted 컬렉션/인덱스/메타데이터가 9.0에서 그대로 쿼리되지 않을 수 있습니다.
- 운영 환경에서 “일부 사용자 검색만 안 된다” 같은 형태로 장애가 나타날 수 있습니다.

따라서 9.0 업그레이드 리허설의 목표는 “서버가 뜬다”가 아니라, **encrypted 필드 기반의 검색 패턴이 그대로 유지되는지**입니다.

### `mongocryptd` deprecation은 배포/운영 형태를 바꿉니다

MongoDB 9.0 릴리스 노트는 `mongocryptd`가 deprecated 되었고 Automatic Encryption Shared Library(crypt_shared)를 쓰라고 명시합니다. 별도 프로세스를 띄우지 않아도 된다는 장점이 있지만, 운영팀 입장에서는 “배포물이 하나 줄었다”가 아니라 “라이브러리 배포/경로/권한/컨테이너 이미지 구성”으로 문제가 옮겨갑니다.
- [MongoDB 9.0 릴리스 노트: mongocryptd Deprecated](https://www.mongodb.com/docs/manual/release-notes/9.0/)

게다가 9.0 릴리스 노트는 `mongosh`로 prefix/suffix/substring 쿼리를 쓰려면 crypt_shared 9.0+를 별도 다운로드해서 `--cryptSharedLibPath`로 지정해야 한다고까지 적어둡니다.
- [MongoDB 9.0 릴리스 노트: QE string queries와 mongosh](https://www.mongodb.com/docs/manual/release-notes/9.0/)

운영에서 이 문장을 “기능 안내”로 읽으면 안 됩니다. 의미는 다음과 같습니다.

- 운영/장애대응에서 `mongosh`로 QE 쿼리를 재현해야 할 일이 생긴다
- 그때 SRE/DBA 노트북, Bastion, Debug Pod에 crypt_shared가 없으면 재현 자체가 막힌다
- 즉, runbook/디버깅 도구체인까지 업그레이드 범위에 포함해야 한다

## Queryable Encryption 검색 확장: substring은 기능이 아니라 비용 모델입니다

MongoDB는 9.0에서 Queryable Encryption이 prefix/suffix/substring 검색을 GA로 지원한다고 발표했습니다.
- [Now GA: Queryable Encryption Prefix, Suffix, and Substring support](https://www.mongodb.com/products/updates/now-ga-queryable-encryption-prefix-suffix-and-substring-support/)

공식 업데이트에서 substring은 “최대 50자 필드”에서 “2~6자 검색어” 같은 제약이 명시되어 있습니다. 운영팀에게 중요한 포인트는 이 제약이 성능 최적화가 아니라, 비용 폭발을 막기 위한 안전장치라는 점입니다.
- [Now GA: Queryable Encryption Prefix, Suffix, and Substring support](https://www.mongodb.com/products/updates/now-ga-queryable-encryption-prefix-suffix-and-substring-support/)

### tag 기반 인덱싱이므로, substring은 쓰기/저장소를 증폭시킵니다

MongoDB 매뉴얼은 Queryable Encryption의 저장소 영향을 “tag 개수(T)”로 모델링합니다. prefix/suffix는 T가 선형으로 증가하지만, substring은 급격히 커집니다. 특히 문서에 명시된 예시 표에서 `strMaxLength=50`, `strMinQueryLength=2` 조건에서 substring은 `strMaxQueryLength`가 6이면 tag가 236까지 늘어납니다.
- [Estimate Queryable Encryption Storage Impact](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-estimate-storage-impact/)

더 위험한 문장은 여기입니다. “각 tag마다 ESC/ECOC에 두 개의 메타데이터 문서를 추가로 쓴다”는 설명이 있습니다. 즉, substring은 읽기만 느려질 수 있는 게 아니라 쓰기 경로에 직접 부하를 겁니다.
- [Estimate Queryable Encryption Storage Impact](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-estimate-storage-impact/)

운영 체크포인트를 이렇게 바꿔야 합니다.

- substring을 켜는 순간, 평소 write TPS가 그대로면 disk/IOPS/CPU가 “갑자기” 올라갈 수 있습니다.
- compaction/WiredTiger cache pressure가 바뀌고, 결과적으로 tail latency가 흔들릴 수 있습니다.
- 특정 컬렉션에만 QE를 적용했더라도, 클러스터 전체 리소스(특히 IO)가 공유라면 다른 워크로드까지 간접 영향이 갑니다.

### Community Edition에서 “QE가 된다”와 “automatic QE가 된다”는 다릅니다

외부 커뮤니케이션에서는 “Queryable Encryption이 Community Edition에서도 가능”처럼 읽히는 문장이 종종 나오는데, 운영팀은 문서의 정확한 구분을 따라가야 합니다.

MongoDB의 설명 페이지는 Community Edition에서 Queryable Encryption은 explicit encryption은 가능하지만 automatic encryption은 지원하지 않는다고 명시합니다.
- [데이터 보호 개요: Queryable encryption 지원 범위](https://www.mongodb.com/resources/basics/data-in-transit)

또한 매뉴얼(8.0 문서지만 개념은 안정적입니다)은 Community Server에서 automatic decryption은 가능하지만, automatic encryption은 Enterprise/Atlas가 필요하다고 못박습니다.
- [Queryable Encryption with Explicit Encryption (Manual Encryption)](https://www.mongodb.com/docs/v8.0/core/queryable-encryption/fundamentals/manual-encryption/)

운영 리스크는 여기서 터집니다.

- 개발팀이 “9.0에서 substring GA니까 Community에서도 crypt_shared만 얹으면 되겠지”라고 접근하면, 기술적으로 되는 듯 보여도 지원/라이선스/운영 책임이 꼬입니다.
- 반대로 Atlas/Enterprise를 쓰는 조직은 crypt_shared 배포 경로를 표준화하지 않으면, 장애 대응 시점에 재현 수단이 사라집니다.

## 암호화 기능 검증: 검색 정확도보다 먼저 저장소·쓰기 예산을 검증합니다

Queryable Encryption의 prefix/suffix/substring을 도입할 때, 검증 순서를 잘못 잡으면 일정이 무너집니다. 보통은 “기능이 된다 → 성능을 본다”로 가지만, substring은 반대가 낫습니다.

1) 저장소/메타데이터 증가량을 계산해 예산을 먼저 확인
2) 쓰기 증폭이 감당 가능한지 부하 테스트
3) 그 다음에 검색 정확도/케이스 민감도/에러 처리

MongoDB는 tag 기반 추정 공식을 문서로 제공합니다. 그 공식을 그대로 코드로 옮겨서, “우리 데이터 분포에서 worst case가 어느 정도인지”를 수치로 잡아두는 게 운영팀에 이득입니다.
- [Estimate Queryable Encryption Storage Impact](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-estimate-storage-impact/)

### (실행 가능한) tag 개수 계산 스크립트

아래는 문서의 공식을 그대로 구현한 Python 스크립트입니다. 운영 리허설에서 QE 스키마 파라미터를 바꾸면서 “T가 얼마나 튀는지”를 빠르게 보는 용도입니다.

```bash
python3 -V
# Python 3.11+ 권장
```

```python
# qe_tag_estimator.py
from dataclasses import dataclass

@dataclass
class PrefixSuffixOpts:
    str_min: int
    str_max: int

@dataclass
class SubstringOpts:
    str_max_length: int
    str_min_query_length: int
    str_max_query_length: int

def tags_equality():
    return 1

def tags_prefix_or_suffix(opt: PrefixSuffixOpts):
    # T = 1 + (strMaxQueryLength - strMinQueryLength + 1)
    return 1 + (opt.str_max - opt.str_min + 1)

def tags_prefix_and_suffix(prefix: PrefixSuffixOpts, suffix: PrefixSuffixOpts):
    return 1 + (prefix.str_max - prefix.str_min + 1) + (suffix.str_max - suffix.str_min + 1)

def tags_substring(opt: SubstringOpts):
    # T = 1 + (strMaxQueryLength - strMinQueryLength + 1) * (2 * strMaxLength + 2 - strMaxQueryLength - strMinQueryLength) / 2
    a = (opt.str_max_query_length - opt.str_min_query_length + 1)
    b = (2 * opt.str_max_length + 2 - opt.str_max_query_length - opt.str_min_query_length)
    return 1 + (a * b) // 2

def esc_ecoc_metadata_docs(tags: int):
    # docs say: 2 metadata documents per tag (one to ESC and one to ECOC)
    return 2 * tags

if __name__ == "__main__":
    # 예시: substring (문서에서 자주 보이는 케이스)
    sub = SubstringOpts(str_max_length=50, str_min_query_length=2, str_max_query_length=6)
    t_sub = tags_substring(sub)

    pre = PrefixSuffixOpts(str_min=2, str_max=6)
    t_pre = tags_prefix_or_suffix(pre)

    print("substring tags(T):", t_sub)
    print("substring metadata docs per write:", esc_ecoc_metadata_docs(t_sub))
    print("prefix tags(T):", t_pre)
    print("prefix metadata docs per write:", esc_ecoc_metadata_docs(t_pre))
```

```bash
python3 qe_tag_estimator.py
```

예상 출력은 대략 이런 형태입니다(파라미터에 따라 바뀝니다).

```text
substring tags(T): 236
substring metadata docs per write: 472
prefix tags(T): 6
prefix metadata docs per write: 12
```

이 수치를 보고 나면, substring을 “검색 기능”으로 접근하기가 어렵습니다. 거의 “쓰기 경로를 확장하는 아키텍처 변경”에 가깝습니다.

### preview에서 GA로 넘어오며 강제로 걸린 제한을 확인해야 합니다

MongoDB 9.0 호환성 문서는 substring preview에서 내부 제한을 무시하던 파라미터(`fleDisableSubstringPreviewParameterLimits`)를 9.0에서 더 이상 override할 수 없다고 명시합니다.
- [Compatibility Changes in MongoDB 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-compatibility/)

운영적으로는 좋은 변화입니다. 다만 “preview 때 가능했던” 튜닝/우회가 9.0에서 막히면서, 업그레이드 이후에 특정 검색 기능이 제한에 걸려 장애처럼 보일 수 있습니다. 이 케이스는 staging에서 반드시 재현해야 합니다.

## OpenTelemetry: “네이티브 통합”은 결국 OTLP를 어디서 내보내느냐의 문제입니다

MongoDB 9.0 관련 문서/발표에서 OpenTelemetry는 두 가지 톤으로 등장합니다.

- 제품 업데이트 페이지: “enhanced native OpenTelemetry integration”
  - [MongoDB 9.0 is Now Available](https://www.mongodb.com/products/updates/mongodb-9-0-is-now-available/)

- 보도자료: “enhanced OpenTelemetry support”
  - [MongoDB 9.0 및 Atlas Infinite 발표 보도자료](https://www.mongodb.com/company/newsroom/press-releases/mongodb-launches-mongodb-9-0-the-best-version-ever-built-and-atlas-infinite-for-ai-scale-demand)

문제는 이 문장만 읽으면 운영 설계가 안 나온다는 점입니다. 운영팀에게 필요한 질문은 구체적입니다.

- metrics/logs/traces 중 무엇을 OTel로 내보내나
- 그 데이터는 Atlas/Ops Manager/드라이버/애플리케이션 중 어디에서 생성되나
- 전송 방식은 OTLP/gRPC 인가, OTLP/HTTP 인가
- TLS/인증/공인 인증서 요구사항이 있나
- 기존 Prometheus 대시보드를 재사용할 수 있나

현재 공식 문서로 확인 가능한 OTel 경로는 크게 네 가지로 나뉩니다.

### 1) Atlas에서 프로젝트/서비스 metrics를 OTel로 export

Atlas는 OpenTelemetry 통합 문서를 제공하며, OTLP endpoint로 metrics를 보낼 수 있습니다. 중요한 제한은 네트워크 요구사항입니다.

- public IP로만 연결
- TLS 강제
- public CA로 서명된 인증서 필요(셀프사인 불가)

- [Atlas: Integrate with OpenTelemetry (OTel)](https://www.mongodb.com/docs/atlas/tutorial/otel-integration/)

이 조합은 “사내 Collector는 private 네트워크에만 있다” 같은 환경에서 바로 발목을 잡습니다. Atlas에서 나가는 통신을 받으려면 DMZ 성격의 Collector 엔드포인트를 별도로 두거나, 벤더가 제공하는 public OTLP ingest를 써야 합니다.

### 2) Atlas 클러스터 시스템 로그를 OTel로 export

Atlas는 M10+에서 시스템 로그를 1분 단위로 OpenTelemetry로 export하는 문서도 제공합니다.
- [Atlas: Export Logs to OpenTelemetry](https://www.mongodb.com/docs/atlas/export-logs-otel/)

운영 관점에서는 이 기능이 “로그를 더 잘 보자”가 아니라 다음을 의미합니다.

- 클러스터 단위의 로그 파이프라인이 기존(S3 export, CloudWatch, vendor agent)과 충돌할 수 있습니다.
- 1분 주기의 로그 export는 incident 대응에서 “거의 실시간”처럼 느껴지지만, burst 상황에서는 backlog/드롭 정책을 같이 봐야 합니다.

### 3) Atlas Activity Feed 이벤트를 OTel log로 export

Atlas는 Activity Feed 이벤트를 외부로 export하면서, OTel log export 타입을 지원합니다. resource attribute의 `service.name`이 `mongodb-atlas-events`로 들어간다는 점까지 문서에 적혀 있어, Collector 라우팅을 설계할 때 힌트가 됩니다.
- [Atlas: Export Activity Feed Events to External Tools](https://www.mongodb.com/docs/atlas/export-events/)

### 4) Ops Manager에서 MongoDB Agent metrics를 OTLP로 push

self-managed 운영에서 현실적인 OTel 경로는 Ops Manager Agent입니다. 문서는 꽤 구체적이고, 운영팀이 좋아할 만한 문장이 많습니다.

- OTel export는 additive이며 기본은 disabled
- Ops Manager로 가는 기존 모니터링 경로는 영향 없음
- Agent가 OTLP/HTTP로 push(기본 30초)
- metric naming은 `mongodb.*` 컨벤션(기존 Prometheus exporter와 다름)
- Prometheus integration의 pull 모델과 다르고, 대시보드 재작성 필요
- backend는 1개만 지원(여러 군데로 보내려면 Collector를 앞단에 둬야 함)
- 설정이 잘못되면 monitoring module이 안 뜨므로 “실패가 시끄럽다”

- [Ops Manager: Send Metrics to OpenTelemetry (OTel)](https://www.mongodb.com/docs/ops-manager/current/tutorial/otel-integration/)

이건 “네이티브 통합”이라는 표현이 과장이 아니라, 운영상 진짜 의미가 있습니다. 이제 더 이상 `mongodb_exporter`를 별도로 붙여 Prometheus로 긁어오는 방식만이 답이 아닙니다. 대신, metric 네이밍/타입/단위가 달라지는 순간 대시보드 마이그레이션이 일감이 됩니다.

### 드라이버/애플리케이션 trace는 별도의 층입니다

MongoDB 쪽 OTel 문맥과 별개로, 애플리케이션에서 MongoDB 호출을 trace로 남기는 것은 드라이버/인스트루먼테이션 문제입니다. 예를 들어 Ruby driver는 OTel tracing 지원 문서를 제공합니다.
- [Ruby Driver: Trace with OpenTelemetry](https://www.mongodb.com/docs/ruby-driver/current/logging-and-monitoring/open-telemetry/)

그리고 OTel 쪽은 MongoDB client semantic convention을 제공합니다.
- [OpenTelemetry semantic conventions: MongoDB client operations](https://opentelemetry.io/docs/specs/semconv/db/mongodb/)

나는 OTel trace 쪽은 이미 여러 번 정리해둔 적이 있어서(특히 LLM/agent 시스템에서) 내용은 반복하지 않겠습니다.
- [LLM 앱이 “느려졌는데 왜 느려졌는지”를 OTel Trace로 끝까지 추적하는 법](https://daewooki.github.io/posts/llm-otel-trace-2026-8-2/)

다만 MongoDB 9.0 업그레이드 리허설에서는 “DB가 OTel을 지원한다”가 아니라, 애플리케이션 trace와 DB metrics/log가 같은 incident 타임라인에서 합쳐지는지까지 확인하는 게 목적이어야 합니다.

## 관측성 검증 플랜: 대시보드보다 먼저 알람이 깨지는 지점을 봅니다

OTel 통합을 할 때 제일 많이 터지는 건 “데이터가 안 온다”보다 “데이터는 오는데 기존 알람이 의미를 잃는다”입니다.

MongoDB 9.0 릴리스 노트에는 운영 관측성에서 미묘하게 영향을 줄 만한 변경이 섞여 있습니다. 예를 들어 change stream pre-image purging 관련 `serverStatus` metrics가 9.0부터는 추정치일 수 있다고 적혀 있습니다.
- [MongoDB 9.0 릴리스 노트](https://www.mongodb.com/docs/manual/release-notes/9.0/)

이런 류의 변화는 다음 형태로 장애를 유발합니다.

- 기존 알람이 “실제 상태 변화”가 아니라 “측정 방식 변화”를 감지하면서 noisy alert로 바뀜
- incident 중에 알람이 도움이 되지 않으니, 운영팀이 OTel 통합 자체를 불신하게 됨

그래서 나는 업그레이드 리허설에서 관측성은 순서를 이렇게 잡습니다.

1) “수집 경로” 검증: OTLP endpoint까지 들어오는지 (TLS, 인증, 네트워크)
2) “스키마/네이밍” 검증: metric name/unit/type이 기대와 맞는지
3) “SLO 알람” 검증: 업그레이드 전 알람을 그대로 옮길 수 있는지, 아니면 재설계가 필요한지
4) “탐색성” 검증: incident에서 root cause까지 도달하는 시간이 줄었는지

Ops Manager Agent의 OTel export는 Prometheus export와 네이밍이 다르고 drop-in replacement가 아니라고 문서에서 못박습니다.
- [Ops Manager: Send Metrics to OpenTelemetry (OTel)](https://www.mongodb.com/docs/ops-manager/current/tutorial/otel-integration/)

이 문장을 무시하면, 업그레이드와 동시에 모니터링 공백이 생깁니다.

## (실제로 돌려보는) 8.3 ↔ 9.0 쿼리 결과 차이 자동 테스트

MongoDB 9.0 호환성 문서에서 운영에 치명적인 유형은 “성능”이 아니라 “쿼리 의미론이 바뀌는 것”입니다. 문서는 dotted path가 array를 지나갈 때 null 비교 의미가 바뀐다고 명시합니다. 그리고 `{ "a.b": { $ne: null } }` 같은 쿼리가 9.0과 이전 버전에서 결과가 반대로 나온다고까지 적어둡니다.
- [Compatibility Changes in MongoDB 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-compatibility/)

이건 애플리케이션에서 “데이터가 사라졌다”로 보이는 장애를 만들 수 있습니다. 따라서 staging에서 자동으로 잡아내는 테스트를 하나 만들어두는 게 값어치가 큽니다.

### docker-compose로 8.3 / 9.0을 같이 띄우기

Docker Official Image는 8.3과 9.0 태그를 제공합니다.
- [mongo Docker Official Image tags](https://hub.docker.com/_/mongo/tags)

아래 compose는 8.3.11과 9.0을 동시에 띄웁니다.

```yaml
# docker-compose.yml
services:
  mongo83:
    image: mongo:8.3.11-noble
    container_name: mongo83
    ports:
      - "27018:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: root
      MONGO_INITDB_ROOT_PASSWORD: root

  mongo90:
    image: mongo:9.0
    container_name: mongo90
    ports:
      - "27019:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: root
      MONGO_INITDB_ROOT_PASSWORD: root
```

```bash
docker compose up -d
```

### 같은 데이터를 넣고, 같은 쿼리를 날려서 diff 보기

```bash
# 8.3에 데이터 삽입
mongosh "mongodb://root:root@localhost:27018/admin" --eval '
  const db2 = db.getSiblingDB("compat");
  db2.t.drop();
  db2.t.insertMany([
    { _id: 1, a: [] },
    { _id: 2, a: [ { b: null } ] },
    { _id: 3, a: [ { b: 1 } ] },
    { _id: 4, a: [ 1, 2, 3 ] },
  ]);
  print("inserted to 8.3");
'

# 9.0에 동일 데이터 삽입
mongosh "mongodb://root:root@localhost:27019/admin" --eval '
  const db2 = db.getSiblingDB("compat");
  db2.t.drop();
  db2.t.insertMany([
    { _id: 1, a: [] },
    { _id: 2, a: [ { b: null } ] },
    { _id: 3, a: [ { b: 1 } ] },
    { _id: 4, a: [ 1, 2, 3 ] },
  ]);
  print("inserted to 9.0");
'
```

이제 `$ne: null` 조건으로 결과를 비교합니다.

```bash
mongosh "mongodb://root:root@localhost:27018/admin" --quiet --eval '
  const db2 = db.getSiblingDB("compat");
  const r = db2.t.find({ "a.b": { $ne: null } }).sort({ _id: 1 }).toArray();
  printjson(r);
'

mongosh "mongodb://root:root@localhost:27019/admin" --quiet --eval '
  const db2 = db.getSiblingDB("compat");
  const r = db2.t.find({ "a.b": { $ne: null } }).sort({ _id: 1 }).toArray();
  printjson(r);
'
```

이 스크립트의 목적은 “정답이 뭐냐”가 아니라, 업그레이드로 인해 결과가 바뀌는 쿼리 패턴이 실제 서비스 코드에 있는지 찾아내는 것입니다. 실제로는 서비스의 query log / slow query / Query Stats에서 후보를 추출해 비슷한 형태로 회귀 테스트를 늘려갑니다.

## 반론과 회의론: 한 번에 많이 바뀌는 업그레이드는 항상 비용을 숨깁니다

MongoDB 9.0 발표는 성능·보안·관측성을 한 번에 묶었습니다. 운영팀이 회의적으로 봐야 하는 지점도 같이 정리해둡니다.

### 1) 성능 수치는 “내 워크로드”와 무관할 수 있습니다

보도자료의 성능 수치는 내부 벤치마크 기반이며, 애플리케이션의 index/쿼리 패턴/데이터 분포/하드웨어/스토리지에 따라 재현되지 않는 경우가 흔합니다.
- [MongoDB 9.0 및 Atlas Infinite 발표 보도자료](https://www.mongodb.com/company/newsroom/press-releases/mongodb-launches-mongodb-9-0-the-best-version-ever-built-and-atlas-infinite-for-ai-scale-demand)

그래서 업그레이드 리허설에서는 “벤치마크 복제”가 아니라 “SLO를 깨는 tail latency 이벤트가 증가하는지”를 봐야 합니다.

### 2) substring QE는 보안이 아니라 비용/성능 결정입니다

substring은 기능적으로 매력적이지만, tag 기반 메타데이터가 쓰기 경로를 확장합니다. 운영팀이 substring을 승인하는 순간, 저장소와 IOPS 예산도 같이 승인한 셈입니다.
- [Estimate Queryable Encryption Storage Impact](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-estimate-storage-impact/)

### 3) GA 직후 patch에 보안/안정성 수정이 들어옵니다

9.0.1 릴리스 노트에는 CVE 수정이 포함돼 있다고 적혀 있습니다. GA 직후 첫 배포를 9.0.0으로 고정하면, 불필요하게 risk를 떠안는 셈이 됩니다.
- [MongoDB 9.0 릴리스 노트](https://www.mongodb.com/docs/manual/release-notes/9.0/)

## 앞으로 지켜볼 것: FCV 전환 시점과 OTel/암호화 구성 표준화

업그레이드 작업에서 “완료”를 선언할 수 있는 시점은 바이너리 업그레이드가 아닙니다. 다음 조건을 만족해야 합니다.

- FCV 9.0 전환까지 끝났고(또는 끝내지 않기로 명시했고)
- Queryable Encryption 적용 컬렉션에서 검색 정확도 + 쓰기/저장소/latency가 예산 내에 있고
- OTel 파이프라인에서 metrics/logs/traces가 끊기지 않으며
- 알람이 새 네이밍/단위/타입에 맞게 재작성되어 있고
- 장애 대응 runbook에 crypt_shared/OTLP endpoint/Collector 라우팅이 반영돼 있고
- 9.0.x patch cadence(특히 초기 릴리스) 대응 계획이 있다

MongoDB 9.0 업그레이드는 “서버 버전 변경”이 아니라, 암호화/관측성/운영 도구체인을 같이 바꾸는 작업입니다. 이걸 분리해 진행하지 않으면, 장애 원인을 좁히는 데 필요한 관측성이 업그레이드와 동시에 흔들립니다.

## 지금 할 수 있는 일: 업그레이드 리허설 runbook 초안

업그레이드 리허설을 실무적으로 굴릴 때, 나는 작업을 3개의 레인으로 나눕니다.

### 레인 A: 업그레이드 안전장치(FCV/rollback)

- 8.0/8.3 → 9.0 업그레이드 경로 확인
  - [Upgrade 8.3 Standalone to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-standalone/)
- 바이너리 업그레이드 후 FCV 유지 burn-in 기간 설정
- setFeatureCompatibilityVersion(9.0, confirm:true) 실행 runbook 작성
- FCV 메커니즘 이해(장애 시 어떤 상태가 위험한지)
  - [FCV and feature flags (MongoDB 소스)](https://github.com/mongodb/mongo/blob/master/src/mongo/db/repl/FCV_AND_FEATURE_FLAG_README.md)

### 레인 B: Queryable Encryption 검증(비용/성능/정확도)

- prefix/suffix/substring이 필요한 필드 수를 1개로 제한하는 방향으로 설계(특히 substring)
- tag 수 추정으로 저장소/IOPS 예산 확인
  - [Estimate Queryable Encryption Storage Impact](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-estimate-storage-impact/)
- preview queryType 사용 이력 점검 후, 9.0에서 제거되는 타입이 있는지 확인
  - [Compatibility Changes in MongoDB 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-compatibility/)
- `mongocryptd`에서 crypt_shared로 전환 계획 수립
  - [MongoDB 9.0 릴리스 노트](https://www.mongodb.com/docs/manual/release-notes/9.0/)

### 레인 C: OTel 파이프라인 점검(metrics/logs/traces)

- Atlas/Ops Manager 중 무엇을 쓰는지에 따라 OTel egress 경로 확정
  - Atlas metrics: [Integrate with OpenTelemetry (OTel)](https://www.mongodb.com/docs/atlas/tutorial/otel-integration/)
  - Atlas logs: [Export Logs to OpenTelemetry](https://www.mongodb.com/docs/atlas/export-logs-otel/)
  - Ops Manager metrics: [Send Metrics to OpenTelemetry (OTel)](https://www.mongodb.com/docs/ops-manager/current/tutorial/otel-integration/)
- OTLP endpoint(TLS/인증서/네트워크) 사전 검증
- metric naming 변경으로 대시보드/알람 재작성 작업량 산정
- 애플리케이션 trace와 DB metrics의 상관관계를 incident 시나리오로 검증

결국 MongoDB 9.0 업그레이드는, FCV를 안전하게 다루는 실행력 + Queryable Encryption의 비용 모델을 계산하는 습관 + OTel 파이프라인을 운영 표준으로 고정하는 능력이 있는 팀이 이득을 가져가는 업그레이드입니다.

## 참고 자료

- [MongoDB 9.0 is Now Available](https://www.mongodb.com/products/updates/mongodb-9-0-is-now-available/)
- [MongoDB 9.0 및 Atlas Infinite 발표 보도자료](https://www.mongodb.com/company/newsroom/press-releases/mongodb-launches-mongodb-9-0-the-best-version-ever-built-and-atlas-infinite-for-ai-scale-demand)
- [MongoDB 9.0 릴리스 노트](https://www.mongodb.com/docs/manual/release-notes/9.0/)
- [Compatibility Changes in MongoDB 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-compatibility/)
- [Upgrade 8.3 Standalone to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-standalone/)
- [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/)
- [Now GA: Queryable Encryption Prefix, Suffix, and Substring support](https://www.mongodb.com/products/updates/now-ga-queryable-encryption-prefix-suffix-and-substring-support/)
- [Estimate Queryable Encryption Storage Impact](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-estimate-storage-impact/)
- [Queryable Encryption with Explicit Encryption (Manual Encryption)](https://www.mongodb.com/docs/v8.0/core/queryable-encryption/fundamentals/manual-encryption/)
- [데이터 보호 개요: Queryable encryption 지원 범위](https://www.mongodb.com/resources/basics/data-in-transit)
- [Ops Manager: Send Metrics to OpenTelemetry (OTel)](https://www.mongodb.com/docs/ops-manager/current/tutorial/otel-integration/)
- [Atlas: Integrate with OpenTelemetry (OTel)](https://www.mongodb.com/docs/atlas/tutorial/otel-integration/)
- [Atlas: Export Logs to OpenTelemetry](https://www.mongodb.com/docs/atlas/export-logs-otel/)
- [Atlas: Export Activity Feed Events to External Tools](https://www.mongodb.com/docs/atlas/export-events/)
- [Ruby Driver: Trace with OpenTelemetry](https://www.mongodb.com/docs/ruby-driver/current/logging-and-monitoring/open-telemetry/)
- [OpenTelemetry semantic conventions: MongoDB client operations](https://opentelemetry.io/docs/specs/semconv/db/mongodb/)
- [mongo Docker Official Image tags](https://hub.docker.com/_/mongo/tags)
- [FCV and feature flags (MongoDB 소스)](https://github.com/mongodb/mongo/blob/master/src/mongo/db/repl/FCV_AND_FEATURE_FLAG_README.md)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
