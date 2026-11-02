---
title: "Prometheus 3.16.0-rc.2를 운영 리허설로 쓰는 마이그레이션 테스트 계획"
description: "3.16.0-rc.2에서 Remote Write/Receiver·metadata·대시보드 회귀를 GA 전에 잡는 운영 리허설 테스트를 정리합니다."
date: 2026-11-02 11:31:54 +0900
categories: ["News", "Data"]
tags: ["prometheus", "remote-write", "observability", "migration", "rc-testing", "promql"]
render_with_liquid: false
---

2026-10-27에 Prometheus **3.16.0-rc.2**가 공개됐고, 오늘은 2026-11-02(KST)입니다. 이 타이밍이 좋은 이유는 단순합니다. GA로 올라가기 전에, 바뀐 동작이 내 운영의 어느 부분을 건드리는지 계측하고, 스키마/쿼리/대시보드/알럿 룰 회귀를 잡을 수 있는 시간이기 때문입니다. 다운로드 페이지에도 3.16.0-rc.2가 2026-10-27 프리릴리스로 노출되어 있습니다.

Prometheus는 안정성 보장을 강조하지만, 실제 운영에서 깨지는 지점은 API보다도 주변부에 많았습니다. Remote write queue metric이 사라져서 대시보드가 비고, receiver 쪽에서 metadata가 빠져서 type/unit 기반 셀렉터가 어긋나고, 롤백을 하려다 WAL 호환성에 걸려서 시간을 태우는 식입니다. RC를 체험판처럼 써 버리면 이런 종류의 문제는 GA 이후에야 터집니다.

아래는 3.16.0-rc.2를 기준으로, RC 기간에만 효율이 큰 운영 리허설 계획을 테스트 항목 형태로 정리한 것입니다. 내 블로그에서 Prometheus 3.15 업그레이드 포인트(특히 PromQL과 런타임 로그 레벨)는 이미 다뤘고, 이번 글은 그 내용을 반복하지 않고 RC 리허설 프레임에만 집중합니다.

- 이전 글: [Prometheus 3.15.0 업그레이드 포인트: PromQL과 런타임 로그 레벨](https://daewooki.github.io/posts/prometheus-315-upgrade-promql-runtime-log-level/)
- RC 테스트 윈도우 운영 감각은 DB 쪽에서 정리한 방식과 비슷합니다: [PostgreSQL 19 RC 기간 확장에 맞춘 테스트 윈도우 재설계](https://daewooki.github.io/posts/postgresql-19-rc-window-redesign/)

## 3.16.0-rc.2에서 리허설 우선순위가 높은 변경
RC 리허설에서 중요한 건 “모든 변경을 다 보기”가 아니라, 운영에 영향이 큰 축을 먼저 고르는 일입니다. 3.16.0-rc.2 릴리스 노트에서 내가 우선순위를 준 항목은 다음입니다.

1) Remote write 2.0 queue에서 deprecated metadata metric을 더 이상 노출하지 않음

- 릴리스 노트에 명시적으로, Remote Write 2.0 queue에서 아래 metric을 중단한다고 적혀 있습니다. (`prometheus_remote_storage_metadata_total`, `prometheus_remote_storage_metadata_failed_total`, `prometheus_remote_storage_metadata_retried_total`, `prometheus_remote_storage_metadata_bytes_total`)[^1]
- 이건 기능 변경이라기보다 운영 레이어 변경입니다. Grafana 대시보드, 알럿 룰, SLO 계산식이 metric 이름에 의존하는 순간 “기능은 정상인데 모니터링이 망가지는” 케이스가 나옵니다.

2) Remote write receiver: metadata 없이 들어온 샘플 카운팅 방식 변경

- `prometheus_api_remote_write_without_metadata_appended_samples_total`의 카운팅이 `metadata-wal-records`가 꺼져 있어도 동작하도록 바뀌었습니다.[^1]
- 이 metric 자체는 운영 리허설에 꽤 유용합니다. sender가 metadata를 제대로 실어 보내는지(그리고 receiver가 그것을 제대로 붙여 ingest하는지)를, 트래픽을 흘리면서 숫자로 확인할 수 있기 때문입니다.
- 코드 레벨에서 해당 metric이 어떤 의미인지도 확인할 수 있습니다. Prometheus의 remote write handler에는 `remote_write_without_metadata_appended_samples_total`이라는 counter가 있고, “metadata 없이 ingest된 remote write sample/histogram sample 수”로 정의돼 있습니다.[^2]

3) Agent mode에서 `metadata-wal-records` 지원

- Agent를 쓰는 구간이 있다면 의미가 큽니다. 릴리스 노트에 Agent가 `metadata-wal-records`를 지원한다고 적혀 있습니다.[^1]
- 원격으로 장거리 전송을 하는 아키텍처에서는 Agent + remote write가 흔한데, 그 구성에서 metadata가 빠지면 type/unit 기반으로 운영하는 쿼리/룰이 조용히 망가집니다.

4) type/unit 라벨 체계(Feature flag)와 metadata WAL

- Prometheus feature flag 문서에는 `--enable-feature=metadata-wal-records`가 “Remote write 2.0으로 metadata를 보내려면 필요하다”고 명시돼 있습니다.[^3]
- 같은 문서에서 `--enable-feature=type-and-unit-labels`는 `__type__`, `__unit__`를 reserved label로 주입한다고 설명합니다.[^3]

5) receiver 자체를 운영에 쓰는 경우의 주의점

- Prometheus 문서에서도 remote write receiver는 “push 기반 대체”로 쓰기엔 적합하지 않고 low-volume에 주의해서 쓰라고 경고합니다.[^4]
- 이 경고는 기능상의 제한이라기보다, 운영 리스크(부하/비용/장애 전파)를 스스로 떠안는다는 의미에 가깝습니다. 그래서 RC 기간에 receiver 부하를 실제로 한 번 만들어 보는 게 값어치가 있습니다.

## RC를 단순 프리뷰가 아니라 운영 리허설로 취급하는 이유
내가 RC 기간을 “운영 리허설”이라고 부르는 건, 이때만 현실적으로 가능한 검증이 몇 가지 있기 때문입니다.

- GA 이후엔 “최신 버전으로 올려서 고치자”가 정치적으로 쉬워집니다. 반대로 RC 때는 “아직 GA도 아닌데 왜 올려?”라는 저항이 크고, 그래서 운영에 가까운 실험을 할 수 있는 범위가 오히려 명확해집니다. 즉, 실험 설계가 깔끔해집니다.
- RC 기간에는 upstream도 회귀 제보를 받아줄 동기가 있습니다. GA 이후에 발견하면 결국 내가 workaround를 만들 확률이 올라갑니다.
- 무엇보다도, **롤백**을 진짜로 연습할 수 있는 구간이 RC입니다. GA로 들어가면 업그레이드 자체가 목표가 되고, 롤백은 계획에서 빠지기 쉽습니다.

Prometheus는 “버전 올리면 잘 된다”보다 “올리고 나서도 관측 가능해야 한다”가 더 중요합니다. Remote write와 metadata는 특히 그렇습니다. 데이터는 들어오는데 의미가 바뀌면, 성공처럼 보이는 실패가 됩니다.

## 리허설 환경 구성: sender/receiver를 분리하고, v3.15.1과 비교축을 만든다
리허설은 항상 비교축이 있어야 합니다. 이번 리허설에서 비교축은 3.15.1(2026-10-21)과 3.16.0-rc.2(2026-10-27)입니다. 다운로드 페이지에도 3.15.1이 Latest로, 3.16.0-rc.2가 Pre-release로 동시에 노출됩니다.[^5]

구성은 최소 단위로 다음을 둡니다.

- sender: Prometheus Agent (remote_write v2 사용)
- receiver: Prometheus Server (remote write receiver 활성화)
- metric source: node-exporter (현실적인 metadata/TYPE/HELP가 있는 대표 타깃)

아래 docker-compose는 “진짜로 실행 가능한 수준”을 목표로 만들었습니다. 내가 이 형태를 좋아하는 이유는, PRW(Remote Write) 문제는 Kubernetes에서만 재현하려고 하면 변수가 너무 많아져서 원인 추적이 늦어지기 때문입니다.

### docker-compose.yml

```yaml
services:
  node-exporter:
    image: quay.io/prometheus/node-exporter:v1.9.0
    command:
      - --path.rootfs=/host
    pid: host
    network_mode: host
    restart: unless-stopped
    volumes:
      - /:/host:ro,rslave

  prom-receiver-316rc2:
    image: prom/prometheus:v3.16.0-rc.2
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --web.enable-remote-write-receiver
      - --web.remote-write-receiver.accepted-protobuf-messages=io.prometheus.write.v2.Request
      - --enable-feature=metadata-wal-records
      - --enable-feature=type-and-unit-labels
    ports:
      - "19090:9090"
    volumes:
      - ./receiver/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./data/receiver316rc2:/prometheus
    restart: unless-stopped

  prom-agent-316rc2:
    image: prom/prometheus:v3.16.0-rc.2
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --agent
      - --enable-feature=metadata-wal-records
    ports:
      - "19091:9090"
    volumes:
      - ./agent/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./data/agent316rc2:/prometheus
    restart: unless-stopped

  prom-receiver-3151:
    image: prom/prometheus:v3.15.1
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --web.enable-remote-write-receiver
      - --web.remote-write-receiver.accepted-protobuf-messages=io.prometheus.write.v2.Request
      - --enable-feature=metadata-wal-records
      - --enable-feature=type-and-unit-labels
    ports:
      - "29090:9090"
    volumes:
      - ./receiver/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./data/receiver3151:/prometheus
    restart: unless-stopped

  prom-agent-3151:
    image: prom/prometheus:v3.15.1
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --agent
      - --enable-feature=metadata-wal-records
    ports:
      - "29091:9090"
    volumes:
      - ./agent/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./data/agent3151:/prometheus
    restart: unless-stopped
```

- receiver에 `--web.enable-remote-write-receiver`를 켜는 건 공식 CLI 문서에 있는 방식입니다.[^6]
- receiver가 v2 메시지를 받도록 `--web.remote-write-receiver.accepted-protobuf-messages=io.prometheus.write.v2.Request`를 명시했습니다. 이 옵션도 같은 문서에 있습니다.[^6]

### receiver/prometheus.yml

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "self"
    static_configs:
      - targets:
          - "localhost:9090"
```

receiver는 사실상 self-scrape만 해도 됩니다. 리허설에서 receiver는 ingest와 query의 대상이지, 무언가를 scrape하는 역할이 핵심이 아닙니다.

### agent/prometheus.yml

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "node"
    static_configs:
      - targets:
          - "host.docker.internal:9100"

remote_write:
  - url: "http://prom-receiver-316rc2:9090/api/v1/write"
    name: "to_receiver_316rc2"
    protobuf_message: io.prometheus.write.v2.Request

  - url: "http://prom-receiver-3151:9090/api/v1/write"
    name: "to_receiver_3151"
    protobuf_message: io.prometheus.write.v2.Request
```

여기서 핵심은 dual write입니다. sender(Agent)가 같은 scrape 결과를 두 receiver로 동시에 보내면, receiver 쿼리 결과를 비교하면서 “3.16에서만 바뀐 것”을 빠르게 분리할 수 있습니다.

Remote write의 내부 동작은 WAL → shard queue → 전송이며, 이 파이프라인이 막히면 샘플이 쌓입니다. Prometheus가 제공하는 원격 쓰기 튜닝 문서도 이 구조를 설명하고, backlog 체크로 `prometheus_remote_storage_samples_pending`을 언급합니다.[^7]

## Remote write/receiver 회귀: 전송·수신·부분 실패를 “지표로” 확인한다
Remote write는 “전송이 된다/안 된다”를 넘어서, 다음 질문에 답할 수 있어야 운영에서 안전합니다.

- sender queue가 밀리기 시작했는가
- receiver가 일부만 받아서 부분 실패를 만들고 있지는 않은가
- metadata가 빠진 샘플이 늘어나고 있지는 않은가

Remote Write 2.0은 partial write 같은 케이스를 스펙으로 다룹니다. receiver는 성공적으로 쓴 샘플 수를 `X-Prometheus-Remote-Write-*-Written` 헤더로 반환할 수 있고, 202(비동기)에서는 생략될 수 있다는 식으로 명세돼 있습니다.[^8]

이 스펙을 “문서로 읽는 것”과 “운영 리허설에서 실제로 때려보는 것”은 다릅니다. RC 기간에는 일부러 장애 상황을 만들어도 부담이 덜하니, 이때 실험을 해 두는 게 이득입니다.

### 1) sender에서 queue backlog를 숫자로 본다

```bash
curl -s http://localhost:19091/metrics | grep -E 'prometheus_remote_storage_samples_pending|prometheus_remote_storage_'
```

- 리허설 초반에는 backlog가 0 근처로 유지되는지 확인합니다.
- receiver를 일부러 느리게 만들고(예: CPU 제한, IO 제한), backlog가 어떤 기울기로 증가하는지 봅니다.
- 이때 중요한 건 “장애를 만들었을 때 어떤 알럿이 먼저 울려야 하는지”를 결정하는 것입니다. 문서에서도 remote write는 endpoint가 느리면 뒤처진다고 설명합니다.[^7]

운영 리허설의 산출물은 결국 알럿 룰과 runbook입니다. backlog를 만들어 보지 않으면, 임계치가 의미를 가질 수 없습니다.

### 2) receiver에서 remote write receiver 경로가 살아있는지 확인한다

remote write receiver 엔드포인트는 `/api/v1/write`입니다. 공식 API 문서에 명시돼 있습니다.[^4]

리허설에서는 “정상 ingest가 되면 receiver에서 쿼리가 된다”까지를 확인합니다.

```bash
# receiver(3.16 rc.2)에서 node-exporter 대표 metric을 조회
curl -sG 'http://localhost:19090/api/v1/query' \
  --data-urlencode 'query=node_cpu_seconds_total' \
  | jq '.data.result[0].metric'
```

여기서 중요한 건 값 자체가 아니라 labelset이 예상대로인지입니다. 특히 `type-and-unit-labels`를 켰다면 `__type__`, `__unit__`이 들어오는지까지가 체크 포인트가 됩니다. 이 기능은 feature flag 문서에 설명돼 있습니다.[^3]

## metadata 리허설: 빠진 metadata를 “운영에서 감지 가능”하게 만든다
Prometheus remote write에서 metadata는 애매한 영역이었습니다. v1 스펙은 metadata를 reserved로 두고 있고(실험적), v2 스펙은 metadata를 구조적으로 포함합니다.[^9][^8]

그런데 실제 운영에서 중요한 건 스펙이 아니라 구현입니다. Prometheus가 metadata를 remote write에 싣기 위해서는 `metadata-wal-records`가 필요하다고 명시돼 있습니다.[^3]

또, OpenTelemetry Collector 쪽의 remote write receiver 구현 문서에서도 같은 경고를 합니다. metadata(Type/Unit/Help)가 WAL에 기록되지 않으면 OTLP 변환에 필요한 정보가 없어서 동작이 성립하지 않는다는 식으로 설명합니다.[^10]

여기서 3.16.0-rc.2의 포인트는, receiver가 metadata 없이 ingest된 샘플을 `prometheus_api_remote_write_without_metadata_appended_samples_total`로 더 일관되게 카운팅하게 됐다는 점입니다.[^1]

### 1) metadata-wal-records OFF/ON A/B 실험
리허설 환경에서 가장 빠른 검증은 “일부러 잘못 구성해보기”입니다.

- prom-agent-316rc2에서 `--enable-feature=metadata-wal-records`를 끄고 기동
- receiver에서는 다음을 확인
  - `prometheus_api_remote_write_without_metadata_appended_samples_total`이 증가하는지
  - 기대하던 `__type__`, `__unit__`이 빠지는지(옵션을 켠 경우)

실제로 receiver의 /metrics에서 해당 카운터를 확인할 수 있습니다.

```bash
curl -s http://localhost:19090/metrics | grep -E 'prometheus_api_remote_write_without_metadata_appended_samples_total'
```

이 카운터가 증가한다는 건, receiver가 ingest한 샘플 중 metadata가 매칭되지 않은 샘플이 있었다는 뜻입니다. 코드의 help 텍스트도 같은 의미로 정의돼 있습니다.[^2]

운영에서는 이 숫자를 “절대 0이어야 한다”로 두기보다는, 배포/롤링 중에 잠깐 튈 수 있는지를 포함해서 베이스라인을 잡는 게 맞습니다. 그래야 false positive를 줄일 수 있습니다.

### 2) type/unit 라벨은 쿼리/룰 호환성까지 같이 본다
`--enable-feature=type-and-unit-labels`는 reserved label `__type__`, `__unit__`을 주입합니다. 문서에 “유저가 같은 이름으로 라벨을 줘도 override된다”고까지 적혀 있습니다.[^3]

reserved label이 쿼리에 섞이면 어떤 일이 생기냐가 다음 문제입니다. 3.16.0-rc.2 릴리스 노트에는 `__type__`/`__unit__` 관련 PromQL 버그픽스가 포함돼 있습니다(예: binary operation에서 투명하게 처리, `without` aggregation에서 일관되게 drop). 이 항목은 newreleases 쪽 요약에도 잡혀 있습니다.[^11]

따라서 metadata 리허설은 다음 2단계로 끝나야 합니다.

- (A) labelset이 기대대로 들어오는지
- (B) 들어온 라벨이 쿼리/룰에서 조용히 결과를 바꾸지 않는지

(A)는 curl 한 방으로 되지만, (B)는 룰/대시보드 회귀 테스트 없이는 못 잡습니다.

## 대시보드/알럿 룰 호환성: 삭제된 metric과 PromQL 변화에 맞춘 회귀 테스트
이번 RC에서 가장 현실적으로 터질 가능성이 큰 건 “Prometheus가 죽는다”가 아니라 “관측이 비어 보인다”입니다.

### 1) Remote write metadata metric 제거로 인한 대시보드 구멍
Remote Write 2.0 queue에서 더 이상 노출하지 않는 metric 목록은 릴리스 노트에 박혀 있습니다.[^1]

- `prometheus_remote_storage_metadata_total`
- `prometheus_remote_storage_metadata_failed_total`
- `prometheus_remote_storage_metadata_retried_total`
- `prometheus_remote_storage_metadata_bytes_total`

리허설에서 해야 하는 건 간단합니다.

- 운영에서 쓰는 대시보드/룰 저장소를 grep해서 위 metric 참조가 있는지 찾는다.
- RC 환경에서 sender/receiver의 /metrics를 직접 grep해서 정말로 없어졌는지 확인한다.

```bash
curl -s http://localhost:19091/metrics | grep -E 'prometheus_remote_storage_metadata_(total|failed_total|retried_total|bytes_total)' || true
```

이 검사는 단순하지만 효과가 큽니다. 운영에서는 이 metric이 “0이라서 문제”처럼 보이기도 하고, “그래프가 끊겨서 문제”처럼 보이기도 합니다. 둘 다 결국 oncall 시간을 잡아먹습니다.

### 2) promtool 기반의 룰 회귀 + feature flag 일치
운영 룰 회귀는 promtool 없이 하기 어렵습니다. 게다가 3.16.0-rc.2에서는 `promtool test rules`가 `--enable-feature`를 honor하는 버그픽스가 포함돼 있습니다. 이 변화는 RC 리허설과 직접적으로 연결됩니다. (feature flag가 켜진 상태에서만 발생하는 PromQL/ingest 변화가 있기 때문입니다.)[^11]

리허설에서는 promtool을 “운영과 같은 feature flag 조합”으로 돌려서, 룰이 같은 방식으로 평가되는지 확인해야 합니다.

예시는 다음처럼 가져갑니다.

```bash
# promtool은 Prometheus 이미지에 포함되어 있으니 컨테이너에서 실행
docker run --rm -v "$PWD/rules:/rules:ro" prom/prometheus:v3.16.0-rc.2 \
  promtool test rules \
  --enable-feature=type-and-unit-labels \
  --enable-feature=metadata-wal-records \
  /rules/tests.yml
```

여기서 중요한 건 “테스트 파일이 있다/없다”가 아니라, 운영 리허설 기간에 테스트 케이스를 최소한이라도 만든다는 점입니다.

- Remote write backlog가 발생했을 때 울려야 하는 alert
- receiver에서 metadata 없는 ingest가 증가했을 때 울려야 하는 alert
- `__type__`/`__unit__`이 있는 상태에서 `without()`/binary op 등이 결과를 바꾸지 않는지 확인하는 recording rule

나는 룰 회귀 테스트를 만들 때, 실제 사고로 연결되는 조건만 남깁니다. 룰이 많아지면 유지보수 비용이 폭증하고, RC 리허설의 목표(회귀를 빨리 잡기)와 멀어집니다.

## Remote write receiver 리허설: “받는다”가 아니라 “운영해도 되는지”를 확인한다
Prometheus 문서는 remote write receiver를 low-volume 용도로 신중히 쓰라고 합니다.[^4]

리허설에서 확인해야 할 건 다음 계층입니다.

- 기능 계층: v2 payload를 받고, query로 조회 가능
- 성능 계층: receiver가 query latency를 유지하면서 ingest를 감당하는지
- 격리 계층: receiver 장애가 sender에 어떤 backpressure로 전파되는지

특히 마지막이 중요합니다. sender의 remote write는 WAL 기반이라, receiver가 느려지면 sender 내부에 데이터가 쌓이고 결국 sender 리소스가 터지거나 드롭이 발생합니다. 문서에서도 샤드 큐 구조와 backlog를 설명합니다.[^7]

그래서 RC 리허설은 실제로 receiver를 죽였다가 살리는 실험이 포함돼야 합니다.

- receiver 컨테이너를 10분 내렸다 올리기
- receiver 디스크를 거의 가득 채워 보기
- receiver에 CPU limit을 걸어 ingest를 느리게 만들기

이런 실험은 GA 이후엔 하기 어렵습니다. RC는 “운영에서 할 수 없는 운영 실험”을 해도 되는 창구입니다.

## 롤백 리허설: 데이터/스토리지 단위를 분리해서 되돌릴 수 있게 만든다
운영에서 가장 흔한 실패는 “업그레이드는 했는데 문제가 생겼고, 되돌리려니 되돌릴 길이 없음”입니다.

Prometheus는 on-disk format의 정확한 동일성을 안정성 보장 범위로 두지 않는다고 밝힙니다. 대신 forward compatible하게 처리한다고 설명합니다.[^12]

여기서 내가 RC 리허설에 꼭 넣는 규칙은 하나입니다.

- **롤백은 binary만 바꾸는 이벤트가 아니라, storage 단위도 같이 다루는 이벤트로 본다.**

현실적인 전략은 다음 중 하나로 정리됩니다.

1) canary receiver는 별도의 TSDB path/PV를 쓴다
- 문제 생기면 canary를 버리고 PV를 폐기하면 된다.
- 롤백이 “삭제/재생성”으로 단순해진다.

2) sender(remote write)는 dual write 기간을 길게 가져간다
- receiver 교체가 즉시 안 되더라도 데이터 손실을 최소화한다.
- 대신 비용(네트워크/저장소)이 증가한다.

3) 기능 플래그는 롤백 가능성까지 보고 켠다
- 예를 들어 start timestamp 관련 기능은 WAL/TSDB 포맷에 영향을 주는 면이 있고, 문서에서도 제한 사항을 길게 적고 있습니다.[^13]
- RC 기간에 feature flag 조합을 확정해 두면, GA 때는 변경 변수를 줄일 수 있습니다.

이번 3.16.0-rc.2 자체가 “롤백이 불가능해진다”는 직접적인 문구를 제공하진 않습니다. 그렇기 때문에 더더욱, 롤백을 기술적으로 가능하게 만드는 운영 패턴(별도 PV, dual write, canary)이 필요합니다.

## RC 기간에만 효율이 큰 검증 산출물: 계측 기준과 호환성 목록
RC 리허설의 산출물은 코드가 아니라 문서/체크리스트가 되는 경우가 많습니다. 내 경험상, 이걸 제대로 만들면 GA 때의 변경은 거의 작업이 됩니다.

이번 리허설 산출물을 다음처럼 잡았습니다.

- Remote write/receiver 관측 항목
  - sender backlog를 대표하는 metric과 임계치 근거
  - receiver ingest에서 metadata 누락을 대표하는 metric과 정상 범위
  - 장애 시나리오별(runbook) 조치

- metadata/type/unit 사용 정책
  - `metadata-wal-records`를 어디서 켤지(Agent만? receiver도?)
  - `type-and-unit-labels`를 켰을 때 대시보드/룰이 어떤 영향을 받는지

- 호환성 목록
  - “3.16에서 사라지는 metric 목록”
  - “3.16에서 새로 의미가 생기는 metric 목록”
  - “PromQL 결과가 바뀔 가능성이 있는 구문 목록”(특히 reserved label 관련)

이걸 만들 때 좋은 출발점은 릴리스 노트에서 `[CHANGE]` 라벨이 붙은 항목만 뽑는 것입니다. Prometheus도 breaking change는 릴리스 노트에 `[CHANGE]`로 표시한다고 안정성 문서에서 말합니다.[^12]

## 정리: 3.16.0-rc.2는 Remote Write/metadata 운영 품질을 검증할 타이밍을 준다
3.16.0-rc.2(2026-10-27)는 기능 추가보다도 운영에서 흔히 놓치는 접점들을 건드립니다. Remote write 2.0 queue의 deprecated metric 중단은 대시보드/알럿 룰 회귀를 유발하기 좋고, receiver의 metadata 누락 카운팅 개선은 그 회귀를 숫자로 잡을 수 있게 해 줍니다. Agent의 metadata-wal-records 지원까지 합치면, 중앙 집계 아키텍처에서 “샘플은 있는데 의미가 빠진 상태”를 더 빨리 발견할 수 있습니다. RC는 이 변화들을 GA 전에 실트래픽과 비슷한 조건으로 재현하고, 롤백까지 포함한 운영 시나리오를 끝까지 실행해 볼 수 있는 기간입니다.

## 참고 자료
- [Prometheus 다운로드: 3.16.0-rc.2(2026-10-27) 노출](https://prometheus.io/download/)
- [Prometheus v3.16.0-rc.2 릴리스 노트](https://github.com/prometheus/prometheus/releases/tag/v3.16.0-rc.2)
- [newreleases: prometheus/prometheus v3.16.0-rc.2 변경 목록](https://newreleases.io/project/github/prometheus/prometheus/release/v3.16.0-rc.2)
- [Prometheus command-line flags: --web.enable-remote-write-receiver 등](https://prometheus.io/docs/prometheus/latest/command-line/prometheus/)
- [Prometheus HTTP API: Remote Write Receiver(/api/v1/write)](https://prometheus.io/docs/prometheus/latest/querying/api/)
- [Prometheus Remote write tuning 가이드](https://prometheus.io/docs/practices/remote_write/)
- [Prometheus feature_flags.md: metadata-wal-records, type-and-unit-labels](https://github.com/prometheus/prometheus/blob/main/docs/feature_flags.md)
- [Prometheus Remote Write 2.0 spec](https://github.com/prometheus/docs/blob/main/docs/specs/prw/remote_write_spec_2_0.md)
- [Prometheus Remote write spec(v1)](https://github.com/prometheus/docs/blob/main/docs/specs/prw/remote_write_spec.md)
- [Prometheus remote write handler 코드: remote_write_without_metadata_appended_samples_total](https://github.com/prometheus/prometheus/blob/main/storage/remote/write_handler.go)
- [OpenTelemetry Collector contrib: prometheusremotewritereceiver README](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/prometheusremotewritereceiver/README.md)
- [내 글: Prometheus 3.15.0 업그레이드 포인트](https://daewooki.github.io/posts/prometheus-315-upgrade-promql-runtime-log-level/)
- [내 글: PostgreSQL 19 RC 테스트 윈도우 재설계](https://daewooki.github.io/posts/postgresql-19-rc-window-redesign/)

[^1]: <https://github.com/prometheus/prometheus/releases/tag/v3.16.0-rc.2>
[^2]: <https://github.com/prometheus/prometheus/blob/main/storage/remote/write_handler.go>
[^3]: <https://github.com/prometheus/prometheus/blob/main/docs/feature_flags.md>
[^4]: <https://prometheus.io/docs/prometheus/latest/querying/api/>
[^5]: <https://prometheus.io/download/>
[^6]: <https://prometheus.io/docs/prometheus/latest/command-line/prometheus/>
[^7]: <https://prometheus.io/docs/practices/remote_write/>
[^8]: <https://github.com/prometheus/docs/blob/main/docs/specs/prw/remote_write_spec_2_0.md>
[^9]: <https://github.com/prometheus/docs/blob/main/docs/specs/prw/remote_write_spec.md>
[^10]: <https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/prometheusremotewritereceiver/README.md>
[^11]: <https://newreleases.io/project/github/prometheus/prometheus/release/v3.16.0-rc.2>
[^12]: <https://prometheus.io/docs/prometheus/3.11/stability/>
[^13]: <https://prometheus.io/docs/prometheus/latest/feature_flags/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
