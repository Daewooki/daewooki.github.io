---
title: "Debezium 3.7 Beta2: 커넥터 성숙도와 CDC 확장"
description: "CockroachDB 커넥터의 incubating 졸업을 운영 체크리스트로 해석하고, Milvus·SQLite 소스 CDC가 요구하는 스키마·순서·체크포인트 전략을 재정의합니다."
date: 2026-09-17 10:21:48 +0900
categories: ["News", "Data"]
tags: ["debezium", "cdc", "cockroachdb", "milvus", "sqlite", "kafka-connect"]
render_with_liquid: false
---

## 2026-09-15에 실제로 바뀐 것
Debezium 3.7.0.Beta2는 2026-09-15에 공개됐고, 릴리스 포인트가 명확합니다. CockroachDB 커넥터가 incubating 표기를 떼고 production-ready로 올라갔고, Milvus와 SQLite는 소스 커넥터가 “첫 공식 릴리스”로 들어왔습니다.[^1]

여기서 중요한 구분이 하나 있습니다.

- CockroachDB는 **incubating → production-ready**로 이동했습니다. 릴리스 노트는 incubating 안내문이 문서와 README에서 제거됐고, 플러그인 아카이브의 설치 가이드에서도 incubating suffix가 사라졌다고 적습니다.[^1]
- Milvus는 “incubating source connector”로 추가됐습니다. Milvus가 외부에 change stream API를 제공하지 않기 때문에, 내부 MQ 채널을 직접 읽고 etcd checkpoint + timestamp ordering으로 재시작 가능한 순서를 만든다고 설명합니다. 또한 Milvus 2.5+와 Kafka MQ 백엔드를 요구합니다.[^1]
- SQLite도 “incubating source connector”로 추가됐습니다. SQLite는 서버 프로세스도 없고 WAL 같은 트랜잭션 로그를 CDC 관점에서 바로 붙잡기 어렵기 때문에, 트리거가 유지하는 CDC log table을 읽어서 Debezium change event로 번역하는 접근을 택했습니다.[^1]

이 조합은 “새 커넥터가 늘었다”가 아니라 CDC 파이프라인의 경계가 바뀌었다는 신호로 읽히는 쪽이 더 정확합니다. CockroachDB는 분산 SQL의 native changefeed를 Debezium envelope로 정규화해 운영 가능한 단계로 올라왔고, Milvus/SQLite는 각각 벡터DB/엣지 단일 파일 DB까지 CDC를 확장하면서, 스키마·순서·체크포인트의 정의를 소스별로 다시 써야 하는 구간에 들어왔습니다.

## incubating과 production-ready를 “운영 계약”으로 다시 정의
Debezium 문서에서 incubating은 “preview 목적이며, 항상 backward compatible하지 않을 수 있는 변경이 들어갈 수 있다”로 정의됩니다.[^2]

이 문장 하나가 현장에서는 곧바로 운영 계약으로 변환됩니다.

- incubating: “정확성/성능/관측 가능성”의 어떤 축이든 아직 완결되지 않았을 수 있고, 업그레이드가 곧 마이그레이션이 될 수 있습니다.
- production-ready: 최소한 업그레이드·장애·재시작·스키마 변경·대량 스냅샷 같은 운영 이벤트가 반복적으로 발생해도, 커넥터가 약속한 동작을 유지할 가능성이 높아졌다는 의미입니다.

다만 production-ready가 “내 파이프라인이 production-ready”를 보장하지는 않습니다. 예를 들어 Debezium CockroachDB 커넥터 문서에는 Quay에서 받는 Debezium 컨테이너 이미지가 “엄격한 테스트나 보안 분석을 거치지 않으며, 프로덕션 용도가 아니다”라는 경고가 그대로 들어 있습니다. 즉 커넥터 성숙도가 올라가도 배포물/런타임/운영체계는 별도의 성숙도 축입니다.[^3]

이번 Beta2의 상징성은 여기 있습니다. CockroachDB 커넥터가 incubating을 졸업했다는 사실을 “이제 써도 된다”로 받아들이면 반쪽이고, “이 커넥터에 대해 Debezium이 어떤 운영 계약을 더 강하게 커밋하기 시작했는가”를 체크리스트로 뽑아야 실제 가치가 생깁니다.

## 커넥터 성숙도(incubating→production-ready) 운영 체크리스트
아래는 내가 CDC 운영에서 “커넥터가 production-ready로 불릴 때 최소한 무엇을 더 믿을 수 있어야 하는가”를 체크리스트로 고정해 둔 항목입니다. 이번 CockroachDB 건은 이 리스트를 실제로 적용해 보기 좋은 사례입니다.

### 1) 업그레이드 내구성: 설정/메시지/오프셋의 안정성
incubating 커넥터가 무서운 지점은 기능 부족이 아니라 “형태가 바뀌는 것”입니다.

- 설정 키가 바뀌면 배포 자동화가 깨집니다.
- emitted message format이 바뀌면 sink/consumer가 깨집니다.
- offset 포맷이 바뀌면 재시작이 “이어서 읽기”가 아니라 “재스냅샷”으로 변질됩니다.

Debezium이 Milvus 커넥터 문서에 “format of emitted messages may change… production use not recommended”를 박아 둔 것도 같은 맥락입니다.[^4]

오프셋 저장 자체는 Kafka Connect가 제공하는 내부 메커니즘에 기대는 경우가 많습니다. Kafka Connect distributed mode에서는 `offset.storage.topic`에 오프셋을 저장하고(compaction 권장), `config.storage.topic`/`status.storage.topic`도 별도 내부 토픽으로 유지합니다.[^5]

즉 production-ready로 본다는 건 최소한 다음 질문에 “크게 흔들리지 않는 답”이 있어야 합니다.

- 업그레이드 후에도 같은 커넥터 이름/논리 파티션에서 offset resume가 되는가
- snapshot→streaming handoff가 정확히 정의돼 있고, 재시작 시 duplicate/loss가 관리 가능한가
- 메시지 envelope의 필드(특히 ordering에 쓰는 source metadata)가 버전 간 안정적인가

### 2) 장애 복원력: 재시작·재연결·백프레셔에서의 일관된 동작
운영에서 CDC는 “끊겼다 이어졌다”가 일상입니다.

CockroachDB 커넥터는 문서에서 “마지막 resolved timestamp를 기록하고, 재시작 시 그 지점부터 재개한다”라고 설명합니다.[^6]

Milvus 커넥터는 더 노골적으로 동작을 문서화합니다.

- 최초 실행 시 etcd에 있는 pchannel checkpoint에서 `guarantee_ts`와 MQ offset을 읽고, snapshot을 그 시점에 고정한 뒤 streaming이 그 offset에서 이어지도록 설계합니다.[^4]
- streaming에서는 vchannel별 timetick watermark를 이용해 재정렬하고, offset 업데이트는 dispatch 이후에만 진행해 “내보내지 않은 이벤트의 offset commit”을 피합니다.[^4]
- vchannel timetick이 멈추면 stall timeout 이후 강제 flush로 무한 대기를 피합니다(대신 ordering/완전성 관점에서 트레이드오프가 생길 수 있는 지점이라 운영자가 알아야 합니다).[^4]

이 수준의 “실패 모드 문서화”는 production-ready의 핵심 신호입니다. 기능이 많아지는 것보다, 실패했을 때 어디까지가 보장이고 어디부터가 운영자의 책임인지가 먼저 고정돼야 합니다.

### 3) 순서 보장 모델: Kafka의 partition order와 소스의 순서가 합쳐질 때
CDC에서 순서는 3겹입니다.

1) 소스가 보장하는 commit order
2) 커넥터가 읽고 재정렬/완충하면서 만들어내는 order
3) Kafka 토픽/파티션이 제공하는 per-partition order

CockroachDB changefeed는 “resolved timestamp message”를 별도로 내보내며, 어떤 resolved timestamp t를 받으면 t 이전 timestamp의 레코드는 그 뒤에 나오지 않는다는 형태의 진행 보장을 설계 단계에서 명시해 왔습니다.[^7]

동시에 CockroachDB RFC는 “cross-row/cross-table order guarantee는 주지 않는다”고도 못 박습니다.[^7]

즉 CockroachDB 커넥터가 production-ready가 되었다는 건 “순서가 완벽해졌다”가 아니라, **어떤 수준의 순서가 계약인지가 운영 가능한 형태로 고정됐다**에 가깝습니다.

Milvus는 정반대 방향입니다. 여러 vchannel이 하나의 pchannel에 섞여 들어오고, 물리적으로는 arrival order가 commit order와 다를 수 있다고 문서가 인정합니다. 그래서 timetick을 watermark로 삼아 strict TSO order로 내보내는 ordering engine이 핵심 구성 요소가 됩니다.[^4]

SQLite는 더 다릅니다. SQLite 자체가 서버형 로그 스트림을 제공하지 않으니, “트리거가 쌓는 log table”이 순서의 기준이 됩니다. 이 모델은 RDBMS WAL 기반 CDC에 비해 순서·중복·누락의 위험이 커 보이지만, 대신 엣지에서 Kafka 없이도(예: Debezium Engine/Server를 붙여서) 일관된 change event 형태로 빼낼 수 있다는 장점이 생깁니다. SQLite 커넥터가 log table + trigger 기반임은 릴리스 공지와 커넥터 저장소 README가 같은 방향으로 말합니다.[^1]

### 4) 스키마 처리: “DDL 이벤트”가 없는 세계에서의 schema fidelity
RDBMS CDC는 보통 schema history topic 같은 내부 저장소를 두고(커넥터별로 필요 여부가 다름), 스키마 변화를 복구 가능한 형태로 기록합니다. Debezium 설치 문서도 schema history topic의 운영 권장사항(파티션 1, retention 길게 등)을 별도 항목으로 다룹니다.[^8]

Milvus 커넥터는 관계형 스키마 히스토리 모델과 다르게 움직입니다.

- schema snapshot을 따로 뜨지 않고, snapshot/streaming 중에 metadata API나 첫 insert event를 통해 동적으로 schema를 resolve합니다.[^4]
- schema change topic을 만들지 않습니다.[^4]

즉 downstream에서 “스키마 변화 감지/승인/적용”을 어떤 레이어에서 할지 재설계해야 합니다. vector field dimension 같은 정보가 이벤트 스키마에 들어온다는 건 장점이지만, 그 변화가 있을 때의 대응은 RDBMS보다 자동화가 어렵습니다(어느 순간 dimension이 바뀌는 것은 사실상 breaking change에 가깝습니다). Milvus 커넥터가 “vector dimension까지 schema fidelity로 실어준다”고 릴리스 공지가 강조하는 이유도 그 맥락입니다.[^1]

SQLite는 스키마가 “파일” 안에 있고, CDC는 “트리거가 남긴 기록”을 커넥터가 읽는 구조입니다. 여기서는 DDL을 했을 때 트리거/로그 테이블이 어떻게 따라가야 하는지가 곧 운영 리스크가 됩니다. 릴리스 공지는 include/exclude filter와 offset resume 정도까지만 보장 범위로 명시합니다.[^1]

### 5) 관측 가능성: 지표가 “원인”을 말해주는가
production-ready로 올라오면 가장 먼저 체감되는 건 기능이 아니라 디버깅 비용입니다.

- Milvus 커넥터는 watermark lag 같은 Milvus 특화 지표를 JMX로 노출한다고 README가 설명합니다.[^9]
- CockroachDB 커넥터는 문서에 transient connection failure(예: serialization failure SQL state 40001)에 대한 retry 로직과 설정 키를 명시합니다.[^3]

이런 항목이 문서에 등장하기 시작하면 “운영을 해본 흔적”으로 읽힙니다.

## CockroachDB 커넥터 incubating 졸업: 무엇이 운영을 쉽게 만들었나
릴리스 공지가 말하는 변화는 단순히 라벨 제거입니다. README/문서의 incubating notice 삭제, 플러그인 아카이브 명칭에서 incubating suffix 제거.[^1]

이 변화는 실무에서 다음 의미를 가집니다.

1) “이 커넥터를 써도 되는가”가 아니라 “이 커넥터를 운영 문서/표준 스택에 포함해도 되는가”의 문제로 넘어갑니다. 조직에서 스택 표준화는 보통 문서/지원 체계/업그레이드 정책과 묶입니다.

2) CockroachDB CDC는 WAL tailing이 아니라 native changefeed 기반입니다. Debezium CockroachDB 커넥터 문서는 changefeed가 intermediate Kafka로 이벤트를 푸시하고, 커넥터가 그것을 소비해 Debezium envelope로 변환한 뒤 output Kafka로 내보내는 구조를 설명합니다.[^6]

3) changefeed의 진행/일관성은 resolved timestamp 모델로 사고해야 합니다.

- CockroachDB 문서는 `resolved` timestamp가 “별도 메시지”로 나간다고 명시합니다.[^10]
- RFC는 “resolved notification 이후에 더 작은 timestamp 레코드가 오지 않는다”는 보장을 위해, resolved를 내보내기 전에 progress를 동기 기록해야 한다는 설계 의도를 밝힙니다.[^7]

4) 순서 보장은 애초에 한계가 있습니다. RFC가 cross-row/cross-table ordering을 보장하지 않는다고 못 박기 때문에, downstream에서 전역 순서를 기대하는 아키텍처는 구조적으로 부적합합니다.[^7]

정리하면 CockroachDB 커넥터의 성숙도 상승은 “기술적으로 더 신기해졌다”가 아니라, changefeed 기반 CDC의 계약(특히 resolved timestamp와 ordering의 한계)이 Debezium 스타일 운영 모델로 충분히 수렴했다는 쪽에 가깝습니다.

## Milvus 소스 커넥터: 벡터DB CDC가 요구하는 새로운 정의
Milvus 커넥터는 Debezium의 기존 CDC 세계관(로그 기반, 테이블 기반, DDL 히스토리 기반)과 다른 출발점에서 설계된 게 문서에 그대로 드러납니다.

### Milvus는 change stream API가 없고, 내부 MQ를 읽는다
Milvus 커넥터 문서는 Milvus가 gRPC API로 change stream을 제공하지 않기 때문에, 모든 write가 내부 MQ 채널로 먼저 publish된다는 점을 전제로 커넥터가 MQ를 직접 읽는다고 설명합니다. 이 때문에 커넥터는 Milvus gRPC endpoint, MQ backend, 그리고 etcd(채널 checkpoint 저장)를 모두 직접 접근해야 합니다.[^4]

릴리스 공지도 같은 내용을 요약하고, Milvus 2.5+ + Kafka MQ backend 조건을 명시합니다.[^1]

이건 단순한 “커넥터 하나 추가”가 아니라, 운영 경계가 늘어났다는 뜻입니다.

- RDBMS CDC는 대개 DB + Kafka(+Connect)로 끝납니다.
- Milvus CDC는 Milvus + (Milvus 내부 MQ용 Kafka) + etcd + (Debezium output Kafka)까지 연결되기 쉽습니다. 문서도 Milvus가 사용하는 Kafka와 Kafka Connect가 쓰는 Kafka가 보통은 분리된다고 적습니다.[^4]

### snapshot→streaming handoff가 “etcd checkpoint에 고정된 consistent read”로 정의된다
Milvus 커넥터의 snapshot 단계는 운영에서 가장 중요한 문장 하나로 요약됩니다.

- etcd checkpoint에서 `guarantee_ts`와 MQ offset을 읽고
- snapshot query를 `guarantee_ts`에 pinning해서 “그 시점의 상태”를 읽은 뒤
- streaming은 해당 MQ offset에서 시작한다

이 조합이 snapshot/streaming 전환에서 loss/duplicate를 막는 핵심으로 문서에 명확히 적혀 있습니다.[^4]

RDBMS CDC에서 흔히 보는 “LSN을 읽고 테이블을 스캔하고 LSN부터 스트리밍” 패턴을 Milvus 방식으로 재구성한 것입니다. 차이는 LSN이 DB 내부 로그가 아니라 etcd checkpoint + MQ offset + TSO로 분해돼 있다는 점입니다.

### 순서: timetick watermark를 최소 단위로 이해해야 한다
Milvus는 vchannel 여러 개가 하나의 pchannel에 섞여 들어옵니다. 문서는 pchannel/vchannel 개념과, vchannel이 주기적으로 timetick 메시지를 발행해 watermark처럼 동작한다고 설명합니다.[^4]

커넥터는 다음을 합니다.

- pchannel에서 raw 메시지를 폴링
- vchannel별로 이벤트를 버퍼링
- “모든 vchannel의 timetick 중 최소값”을 global watermark로 잡고
- watermark 뒤쪽(안전 구간)의 이벤트를 strict TSO order로 flush

이 설계는 “Kafka partition ordering”과는 다른 결의 ordering입니다. Kafka는 파티션 단위 순서만 보장하므로(전역 순서는 별도 설계 필요), Milvus 커넥터는 애초에 전역(정확히는 해당 pchannel 범위 내) ordering을 만들어서 내보내려는 쪽입니다.

문서에는 timetick stall 시 force flush 옵션과 backpressure 설정까지 포함돼 있습니다. 운영에서 “정확성 vs 지연 vs 메모리”가 트레이드오프라는 걸 커넥터가 안고 들어오는 형태입니다.[^4]

### 업데이트가 `op=u`가 아닐 수 있다: upsert는 delete+insert로 관측된다
Milvus 커넥터는 업데이트 이벤트를 내지 않습니다. Milvus upsert가 delete 후 insert로 구현되기 때문에, 커넥터도 그 관측을 그대로 내보낸다고 문서와 README가 명시합니다. delete는 before 이미지가 PK만 있고, 나머지는 null이 됩니다.[^4]

이 차이는 sink 쪽 설계를 바꿉니다.

- “update는 update로 들어온다”를 가정하는 sink는 깨집니다.
- compacted topic에서 tombstone/삭제를 어떻게 다룰지도 영향을 받습니다.
- 벡터 인덱스 동기화를 하는 sink라면 delete+insert 사이의 짧은 공백을 허용할지(검색 품질), 임시 상태를 어떻게 처리할지(캐시/서빙), 같은 고민이 생깁니다.

## SQLite 소스 커넥터: 엣지 CDC의 비용을 어디에 지불하는가
SQLite 소스 커넥터의 핵심은 “트랜잭션 로그를 읽지 않는다”가 아니라, “트랜잭션 로그가 없으니 애플리케이션 DB에 CDC를 위한 구조물을 심는다”입니다.

릴리스 공지는 다음을 명확히 말합니다.

- SQLite 파일을 대상으로 initial snapshot 이후 insert/update/delete를 스트리밍한다.
- SQLite에는 서버 프로세스나 transaction log가 없어서, DB 트리거가 유지하는 CDC log table을 통해 변경을 캡처한다.
- table/column include/exclude, offset 기반 resume를 지원한다.
- 표준 `sqlite-jdbc` 드라이버로 동작하며 외부 서비스가 필요 없다.

[^1]

커넥터 저장소 README도 “change-data-capture log table + triggers” 구조를 같은 방향으로 재확인합니다.[^11]

이 모델을 운영 관점에서 보면 비용을 지불하는 지점이 바뀝니다.

- WAL 기반 CDC의 비용은 “DB 설정/권한/로그 유지/슬롯 관리/디스크 압박”에 주로 나갑니다.
- SQLite 트리거 기반 CDC의 비용은 “트리거의 정확성, 로그 테이블의 성장/청소, 스키마 변경 시 트리거 재생성, 트랜잭션 경계 표현” 쪽으로 옮겨갑니다.

즉 SQLite 커넥터는 엣지에서 CDC를 가능하게 하지만, 그 대가로 “소스 DB 내부에 CDC 장치를 넣는 것”이 운영 계약에 포함됩니다.

## CDC 범위가 RDBMS에서 AI/엣지로 확장될 때: 스키마·순서·체크포인트 전략 재정의
여기부터가 이번 릴리스의 변곡점입니다. Debezium의 강점은 “어떤 소스든 Debezium envelope로 정규화한다”인데, Milvus/SQLite는 정규화 이전의 물리 세계가 너무 다릅니다. 그래서 똑같이 Kafka로 내보낸다고 해도, 스키마·순서·체크포인트를 동일한 규칙으로 취급하면 운영에서 반드시 사고가 납니다.

아래는 내가 CDC 파이프라인을 설계할 때 3가지를 “소스별로 다시 정의”하는 방식으로 정리한 것입니다.

### 1) 스키마 전략: schema history가 없는(혹은 의미가 약한) 소스에 대비하기
Debezium Engine 문서는 커넥터/엔진이 오프셋 저장 외에도 일부 커넥터에서 internal schema history 저장이 필요하다고 명시합니다(MySQL/SQL Server/Oracle/Db2 등).[^12]

Debezium 설치 문서도 schema history topic 운영 권장사항을 별도 항목으로 다룹니다.[^8]

하지만 Milvus는 schema change topic 자체를 만들지 않고, schema를 동적으로 resolve합니다.[^4]

이 상태에서 운영자가 해야 하는 일은 “schema를 Kafka 밖에서 다시 강제하는 것”입니다. 접근은 대략 두 부류입니다.

- 스키마를 이벤트 자체에 더 넣는다: 예를 들어 consumer가 “현재 컬렉션 스키마 버전”을 메시지에서 읽고 처리하도록 만들거나, 이벤트를 별도의 스키마 레지스트리/메타스토어에 연결합니다.
- 스키마를 sink에 강제한다: sink가 받는 스키마를 엄격히 제한하고, 변화가 감지되면 실패시키고 사람/자동화 승인 뒤에 재개합니다.

Milvus는 특히 vector dimension이 스키마에 들어가는 만큼, dimension 변경은 “그냥 컬럼 추가”가 아니라 인덱스/서빙 쿼리까지 영향을 주는 변경이기 때문에, 스키마 변화를 자동 반영하는 쪽이 오히려 위험합니다. 릴리스 공지가 schema fidelity로 vector dimension을 강조한 건 장점이지만, 동시에 변경 파급을 크게 만든다는 뜻이기도 합니다.[^1]

SQLite는 더 직접적입니다. 스키마 변경이 있을 때 트리거/CDC log table이 어떻게 따라가야 하는지가 스키마 전략에 포함됩니다. 릴리스 공지는 그 세부를 아직 깊게 문서화하진 않지만, “트리거가 유지하는 CDC log table”이 유일한 캡처 경로라는 사실 자체가 스키마 전략의 제약이 됩니다.[^1]

### 2) 순서 전략: “전역 순서”를 포기할지, “전역 순서”를 만드는 비용을 낼지
#### CockroachDB: resolved timestamp + (테이블/키 단위) 재정렬을 기본값으로 둔다
CockroachDB changefeed는 `resolved` 메시지를 별도로 내보내고, enriched envelope에서 commit timestamp를 포함시키는 옵션들이 문서화돼 있습니다.[^10]

한편 설계 문서에서는 cross-table ordering을 보장하지 않는다고 했습니다.[^7]

따라서 CDC 소비자에서 “테이블을 합쳐서 완전한 전역 순서로 처리” 같은 모델은, 애초에 소스가 주지 않는 보장을 파이프라인이 임의로 만들어야 합니다. 그 비용은 보통 stateful stream processing(예: watermark 기반 join)으로 지불합니다.

CockroachDB 커넥터가 production-ready가 됐다는 건, 최소한 여기서 필요한 메타데이터/복원력(마지막 resolved timestamp 저장 등)이 운영 가능한 형태로 자리잡았다는 의미로 읽힙니다.[^6]

#### Milvus: “pchannel 단위로는 strict order를 만든다”를 전제로 downstream을 단순화한다
Milvus 커넥터는 timetick ordering engine으로 strict TSO order를 만들어 냅니다.[^4]

그런데 커넥터가 한 번에 하나의 pchannel만 소비하고, task도 1개만 지원합니다.[^4]

즉 Milvus에서 scale-out을 위해 pchannel을 늘리면(또는 샤딩/토폴로지가 커지면) 커넥터 인스턴스를 여러 개로 늘릴 수밖에 없고, 그 순간 “전역 strict order”는 다시 깨집니다. 이때 필요한 전략은 두 가지 중 하나로 수렴합니다.

- 애초에 “컬렉션/샤드 단위 순서”만 필요하도록 sink/consumer를 설계한다.
- 전역 순서가 필요하다면, pchannel 간 merge를 하는 stateful layer를 추가한다(현실적으로 비용이 큼).

Milvus 커넥터가 제공하는 order는 강력하지만, 그 order의 범위(pchannel/커넥터 인스턴스 경계)를 설계 문서로 박아두지 않으면 나중에 확장 시점에 사고가 납니다.

#### SQLite: log table의 단조 증가 키(또는 커밋 시각)에 순서를 의존하게 된다
SQLite는 변경이 log table에 기록되고 커넥터가 그것을 읽는 구조입니다.[^1]

여기서 순서 전략의 핵심은 “log table의 순서가 트랜잭션 경계와 어떤 관계인지”입니다. WAL 기반 CDC는 보통 LSN/SCN 같은 명확한 로그 포지션이 있고, 오프셋이 곧 순서의 기준이 됩니다. SQLite는 그 기준이 사용자가 만든 log table에 들어갑니다.

이런 구조에서는 순서를 다음처럼 다층으로 보는 편이 안전합니다.

- (강한 순서) 동일 테이블, 동일 PK에 대한 최종 상태 순서
- (약한 순서) 여러 테이블 간 이벤트 순서

엣지/모바일에서는 대부분 전역 순서보다 “최종 상태 동기화”가 더 중요해지고, SQLite 커넥터의 존재 이유도 그 쪽에 가깝습니다.

### 3) 체크포인트 전략: 오프셋이 “어디에 있고 무엇을 의미하는지”를 소스별로 문서화
Kafka Connect는 오프셋을 내부 토픽에 저장합니다. `offset.storage.topic`은 많은 파티션 + replication + compaction이 권장되고, config/status 토픽도 별도로 관리해야 합니다.[^5]

Debezium은 Engine/Server에서 오프셋 저장을 직접 설정해야 한다고 문서화합니다.[^13]

여기서 “오프셋”이 의미하는 바는 소스별로 다릅니다.

- CockroachDB: 커넥터가 마지막 resolved timestamp를 기록한다는 문서 표현을 그대로 받아들여야 합니다.[^6]
- Milvus: 오프셋은 MQ offset + vchannel watermark들이 결합된 형태입니다. snapshot은 etcd checkpoint의 `guarantee_ts`/MQ offset에 고정되고, streaming은 그 MQ offset으로 seek한 다음 watermark ordering으로 진행합니다.[^4]
- SQLite: 오프셋은 log table을 어디까지 읽었는지에 대한 포지션으로 해석될 가능성이 높고, 따라서 log table retention/청소 정책이 곧 체크포인트 안전성의 일부가 됩니다(릴리스 공지가 offset resume를 명시한 만큼, 오프셋이 의미하는 바가 곧 log table cursor라는 점을 운영 문서로 고정해야 합니다).[^1]

여기서 중요한 운영 원칙은 간단합니다. “오프셋 토픽은 Kafka가 알아서 관리하는 내부 데이터”가 아니라, CDC 파이프라인의 durability 그 자체입니다. Kafka Connect 보안 모델 문서도 connector config/offset/status 토픽을 민감한 토픽처럼 보호해야 한다고 말합니다.[^14]

## (실행 가능한) 운영 점검 코드: 커넥터 성숙도를 배포 파이프라인에서 검증하는 방법
아래는 특정 커넥터에 종속되지 않는 형태로, Kafka Connect 클러스터에서 “운영 계약이 지켜지고 있는지”를 최소한 자동 점검하기 위한 스크립트입니다.

- 커넥터/태스크 상태가 RUNNING인지
- 실패 중인 태스크가 있는지
- Connect 내부 토픽이 지정돼 있는지(환경별로 상이하지만, 누락은 운영 사고로 이어지기 쉬움)

```bash
#!/usr/bin/env bash
set -euo pipefail

CONNECT_URLինակ=${CONNECT_URL:-http://localhost:8083}

echo "[1] connectors list"
curl -fsS "${CONNECT_URL}/connectors" | jq -r '.[]' || true

echo

echo "[2] connector status summary"
for c in $(curl -fsS "${CONNECT_URL}/connectors" | jq -r '.[]'); do
  echo "== ${c} =="
  curl -fsS "${CONNECT_URL}/connectors/${c}/status" | jq '{name:.name, connector:.connector.state, tasks:[.tasks[]|{id:.id,state:.state,trace:(.trace//"")}]}'
  echo
done

echo "[3] worker info (sanity)"
curl -fsS "${CONNECT_URL}/" | jq '{version:.version, commit:.commit, kafka_cluster_id:(.kafka_cluster_id//null)}'
```

이 스크립트는 “데이터가 정확하다”까지 증명하지는 못하지만, 최소한 운영에서 가장 흔한 문제(태스크 일부 다운, 재시작 루프, 배포 후 미기동)를 CI/CD 이후 단계에서 잡아내는 용도로는 충분히 쓸 수 있습니다.

Connect 내부 토픽 설계까지 같이 점검하려면, worker 설정에 `config.storage.topic`, `offset.storage.topic`, `status.storage.topic`이 제대로 들어갔는지와, 해당 토픽이 compaction/replication 정책을 갖는지가 필요합니다. Kafka Connect 사용자 가이드는 이 토픽들을 수동 생성해서 파티션/replication/compaction을 원하는 값으로 맞추는 것을 권장합니다.[^5]

## 반론과 회의론: 아직은 “변곡점”이지 “정착”이 아니다
이번 Beta2를 변곡점으로 보는 관점에는 반론도 자연스럽게 붙습니다.

1) Beta2는 Beta2입니다. Milvus/SQLite는 둘 다 incubating으로 명시되어 있고, behavior/config/message format이 바뀔 수 있다고 릴리스 공지와 문서가 직접 경고합니다.[^1]

2) CockroachDB 커넥터가 production-ready가 되었다고 해도, CockroachDB changefeed 자체의 설계 한계(특히 cross-table ordering 미보장)는 바뀌지 않습니다. 이건 커넥터 문제가 아니라 소스 모델의 특성입니다.[^7]

3) 운영 배포물 문제는 별도 축입니다. Debezium Quay 컨테이너 이미지가 프로덕션 용도가 아니라고 문서에 들어가 있는 이상, 실제 운영에서는 벤더가 관리하는 Connect 이미지/플랫폼을 쓰거나 내부적으로 빌드/스캔/테스트 체계를 갖춰야 합니다.[^3]

결국 이번 릴리스의 의미는 “Debezium이 RDBMS 밖의 CDC를 정식 세계관으로 끌어오기 시작했다”이지, “지금 당장 벡터DB/엣지 CDC를 표준 운영으로 돌려도 된다”는 결론은 아닙니다.

## 앞으로 지켜볼 것: 성숙도 상승이 실제 운영 비용을 줄이는 지점
변곡점 이후에 봐야 하는 건 기능이 아니라 “운영 비용 곡선”입니다.

- Milvus 커넥터는 단일 task/단일 pchannel이라는 제약이 명확합니다.[^4]
  - 이후 릴리스에서 이 제약이 완화되는지, 아니면 “운영자가 pchannel 단위로 커넥터를 샤딩”하는 형태가 표준이 되는지에 따라, 전역 순서/체크포인트/재처리 설계가 달라집니다.

- SQLite 커넥터는 “트리거 기반 CDC log table”이라는 구조를 택한 이상, DDL/마이그레이션 자동화와 충돌할 소지가 큽니다. Debezium 로드맵에서도 SQLite 소스 커넥터가 다음 분기(3.8) 항목으로 다시 등장하는데, 이는 기능이 ‘끝났다’가 아니라 아직 다듬을 여지가 크다는 신호로 읽힙니다.[^15]

- CockroachDB는 production-ready로 올라갔지만, `snapshot.mode=when_needed` 같은 공통 옵션이 소스별로 동일하게 동작하지 않는 사례는 과거에도 종종 이슈가 됐습니다. 스냅샷/복구 시나리오는 “커넥터 성숙도”와 “플랫폼 성숙도”가 맞물리는 영역이라, release note만 보고 단정하기 어렵습니다. (이 부분은 이번 글에서 추가 확증 없이 확정 결론을 내리지 않는 게 안전합니다.)

정리하면, CockroachDB의 incubating 졸업은 운영 계약이 단단해지는 방향이고, Milvus/SQLite의 추가는 CDC의 적용 범위가 AI/엣지로 넓어지면서 스키마·순서·체크포인트를 소스별로 다시 정의해야 하는 국면이 열렸다는 쪽이 본질입니다.

## 참고 자료
- [Debezium 3.7.0.Beta2 Released](https://debezium.io/blog/2026/09/15/debezium-3-7-beta2-released/)
- [Debezium Release Series 3.7](https://debezium.io/releases/3.7/)
- [Debezium connector for CockroachDB](https://debezium.io/documentation/reference/connectors/cockroachdb.html)
- [Debezium connector for Milvus](https://debezium.io/documentation/reference/connectors/milvus.html)
- [debezium-connector-milvus GitHub README](https://github.com/debezium/debezium-connector-milvus)
- [debezium-connector-sqlite GitHub README](https://github.com/debezium/debezium-connector-sqlite/blob/main/README.md)
- [Changefeed Message Envelope (CockroachDB docs)](https://www.cockroachlabs.com/docs/stable/changefeed-message-envelopes)
- [CockroachDB change data capture RFC (GitHub)](https://github.com/cockroachdb/cockroach/blob/master/docs/RFCS/20180501_change_data_capture.md)
- [Kafka Connect User Guide (offset/config/status topics)](https://kafka.apache.org/25/kafka-connect/user-guide/)
- [Kafka Connect security model (protect internal topics)](https://apache.googlesource.com/kafka/+/HEAD/docs/security/security-model-connect.md)
- [Storing state of a Debezium connector](https://debezium.io/documentation/reference/3.4/configuration/storage.html)
- [Debezium Engine documentation (offset/schema history properties)](https://debezium.io/documentation/reference/development/engine.html)
- [Debezium Roadmap](https://debezium.io/roadmap/)

[^1]: <https://debezium.io/blog/2026/09/15/debezium-3-7-beta2-released/>
[^2]: <https://debezium.io/documentation/reference/1.9/connectors/index.html>
[^3]: <https://debezium.io/documentation/reference/stable/connectors/cockroachdb.html>
[^4]: <https://debezium.io/documentation/reference/connectors/milvus.html>
[^5]: <https://kafka.apache.org/25/kafka-connect/user-guide/>
[^6]: <https://debezium.io/documentation/reference/connectors/cockroachdb.html>
[^7]: <https://github.com/cockroachdb/cockroach/blob/master/docs/RFCS/20180501_change_data_capture.md>
[^8]: <https://debezium.io/documentation/reference/install.html>
[^9]: <https://github.com/debezium/debezium-connector-milvus>
[^10]: <https://www.cockroachlabs.com/docs/stable/changefeed-message-envelopes>
[^11]: <https://github.com/debezium/debezium-connector-sqlite/blob/main/README.md>
[^12]: <https://debezium.io/documentation/reference/development/engine.html>
[^13]: <https://debezium.io/documentation/reference/3.4/configuration/storage.html>
[^14]: <https://apache.googlesource.com/kafka/%2B/HEAD/docs/security/security-model-connect.md>
[^15]: <https://debezium.io/roadmap/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
