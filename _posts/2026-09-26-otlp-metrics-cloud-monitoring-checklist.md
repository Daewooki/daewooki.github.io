---
title: "Telemetry API 이후 Cloud Monitoring OTLP 메트릭 파이프라인 체크리스트"
description: "Telemetry API(OTLP metric ingest) GA 이후, OTel Collector 기반으로 Cloud Monitoring에 OTLP 메트릭을 안정적으로 올리는 체크리스트를 정리합니다."
date: 2026-09-26 10:20:25 +0900
categories: ["Cloud", "Google Cloud Monitoring"]
tags: ["google-cloud", "cloud-monitoring", "opentelemetry", "otel-collector", "otlp-metrics", "prometheus"]
render_with_liquid: false
---

## GA가 바꾼 전제: 2026-08-05 이후엔 “프리뷰라서 못 쓴다”가 안 통한다

Cloud Monitoring 릴리스 노트 기준으로 Telemetry API의 metric ingestion이 **2026-08-05에 GA**로 전환됐습니다. 이때부터 “OpenTelemetry Collector + OTLP exporter + Telemetry API로 OTLP metrics를 Cloud Monitoring에 ingest할 수 있다”가 공식 문장으로 박혔습니다.[^1]

여기서 중요한 변화는 기능 존재 여부가 아니라 운영 책임의 주체가 바뀐 점입니다.

- 프리뷰에서는 “제약이 있을 수 있다”가 방패였는데, GA 이후에는 쿼터/카디널리티/비용 폭발, metric name drift, 대시보드/알람 마이그레이션 실패가 전부 팀 책임이 됩니다.
- Google 문서도 Collector 배포 가이드, OTLP ingest 규칙, 마이그레이션 가이드가 연결되면서 파이프라인 설계의 기준점이 생겼습니다.[^2]

내가 현장에서 체크리스트를 따로 적는 이유는 간단합니다. OTLP는 vendor-neutral 포맷이지만, 비용과 장애는 vendor-neutral이 아닙니다. OTLP로 쏘기 시작하는 순간 Cloud Monitoring의 quota model과 billing model로 빨려 들어가고, 그때부터는 label 1개가 곧 돈이고 장애입니다.

## OTLP 메트릭이 Cloud Monitoring에서 “Prometheus time series”가 되는 방식

Telemetry API로 들어간 OTLP metric은 Cloud Monitoring 내부에서 Prometheus time-series 형식으로 변환됩니다. 공식 문서가 “Metric data: Prometheus time series로 매핑된다”를 명시합니다.[^2]

변환 규칙에서 운영에 직접 영향을 주는 포인트만 뽑으면 다음과 같습니다.

### 1) metric type이 prometheus.googleapis.com으로 귀결된다
OTLP metric 이름은 변환 후 `prometheus.googleapis.com/{metric_name}/{suffix}` 형태로 저장됩니다. suffix는 OTLP point kind에 따라 붙습니다.[^2]

이 말은 비용 모델과 쿼터 모델이 “Prometheus-format Monitoring data”의 그것으로 간다는 뜻이고, 나중에 PromQL 기반 운영(Recording Rules, managed rule eval)과도 자연스럽게 붙습니다.

### 2) resource마다 target_info가 자동으로 생긴다
각 unique OpenTelemetry resource마다 `target_info` metric이 추가됩니다(단, `service.name`, `service.instance.id`, `service.namespace`는 제외).[^2]

이게 운영에서 제일 위험합니다.

- resource attribute를 마구 넣으면 `target_info`가 “리소스 메타데이터 덤프용 high-cardinality metric”이 됩니다.
- 특히 `k8s.pod.uid`, `process.pid`, ephemeral container id, 노드/파드마다 바뀌는 값이 resource에 붙으면 `target_info`가 time series 생성 공장으로 변합니다.

### 3) UTF-8 / 허용 문자 제한으로 ingest reject가 실제로 발생한다
Cloud Monitoring 쪽 제약 때문에 OTLP metric이 reject될 수 있습니다.

- metric name 정규식: `[a-zA-Z][a-zA-Z0-9_:./-]*`
- label key(= OTLP attribute key) 정규식: `[a-zA-Z_][a-zA-Z0-9_.]*`

문서에서 아예 이런 reject를 피하려면 `replace_pattern`로 변환하라고 못 박습니다.[^2]

여기서 자주 터지는 케이스는 두 가지입니다.

- 팀 내부 metric naming 규칙에 `@`, 공백, 한글 등이 섞여 있는 경우
- attribute key에 `-`(dash) 같은 문자가 섞여 있는 경우(OTel 쪽에서는 흔하지만 Cloud Monitoring 제약과 충돌)

### 4) endpoint는 “root URL”만 넣고, /v1/metrics는 자동으로 붙는다
Collector 설정에서 `endpoint: https://telemetry.googleapis.com`처럼 root만 지정하면 OTel이 signal 타입에 따라 `/v1/metrics` 등을 자동으로 append합니다.[^3]

이걸 모르고 `/v1/metrics`까지 박아버리면, exporter가 다시 append해서 경로가 꼬일 여지가 생깁니다. 프로덕션에서 이런 실수는 “어제까진 들어오던 데이터가 오늘 0이 된” 사고로 연결됩니다.

## 프로덕션 아키텍처를 Collector 기준으로 잡는 이유

Telemetry API는 OTLP transport를 `grpc`, `http/protobuf`, `http/json`로 지원합니다. 다만 애플리케이션에서 직접 export할 때는 gRPC OTLP exporter를 권장하며, 이유로 “많은 SDK의 HTTP exporter는 dynamic token refreshing을 지원하지 않는다”를 듭니다.[^2]

현업에서는 이 권고를 더 공격적으로 해석하는 편이 안전합니다.

- 애플리케이션 → Telemetry API 직결은 “인증/리트라이/백프레셔/배치/속성 정규화”를 애플리케이션 팀이 직접 구현/검증해야 한다는 뜻입니다.
- Collector를 gateway로 두면 이 책임을 중앙 파이프라인으로 끌어올릴 수 있습니다.

GKE라면 선택지는 세 갈래입니다.

1) Managed OpenTelemetry for GKE: 운영 오버헤드를 줄이는 대신 collector-level 필터링/변환이 제한될 수 있습니다. 문서도 “필터링과 control이 필요하면 Google-Built OpenTelemetry Collector를 쓰라”고 말합니다.[^4]
2) Google-Built OpenTelemetry Collector: Google이 제공하는 보수적인 베이스 구성(특히 k8s metadata 부착, common ingestion issue 방지)을 최대한 유지하는 게 낫습니다.[^5]
3) Upstream OTel Collector(직접 운영): 가능하지만, Google 문서에서 “non-standard collector는 지원하지 않을 수 있다”는 뉘앙스를 줍니다.[^6]

내 경우는 2번 성격(= Google-Built config를 베이스로 가져와서 필요한 processor만 얹는 방식)을 선호합니다. 이유는 단순합니다. OTLP metric ingest는 “동작한다/안 한다”가 아니라 “비용과 장애를 통제할 수 있나”가 본질이라서, 운영자가 이미 맞춰둔 가드레일을 굳이 걷어낼 이유가 없습니다.

## 체크리스트 1: 인증과 quota project를 먼저 고정한다

Telemetry API는 consumer API라서 project와 quota project를 명시하라고 합니다. `googleclientauth` extension 설정 예시가 문서에 그대로 있고, `project`/`quota_project`를 둘 다 넣습니다.[^7]

여기서 빠지면 두 종류의 장애가 납니다.

- 아예 권한 에러로 ingest 실패
- ingest는 되는데 quota project가 의도치 않게 다른 곳으로 잡혀서 비용/쿼터 분석이 꼬임

권한은 문서 기준 두 갈래로 정리됩니다.

- “Telemetry API로 log/metric/trace를 쓰려면” `roles/telemetry.writer`와 `roles/serviceusage.serviceUsageConsumer`를 부여하라고 되어 있습니다.[^7]
- Collector 배포 가이드(GKE 예시)는 `roles/monitoring.metricWriter`, `roles/logging.logWriter`, `roles/telemetry.tracesWriter`를 각각 부여하는 예시를 보여줍니다.[^6]

프로덕션에서는 **권한 모델을 하나로 통일**하는 게 중요합니다.

- metric만 보낼 거면 최소 권한으로 `monitoring.metricWriter`만 주고 싶어지는데, Telemetry API가 로그/트레이스까지 같은 endpoint로 묶여 있고, 파이프라인이 커지면 결국 writer role로 수렴하는 경우가 많습니다.
- 반대로 “우리는 metrics만”이라고 못 박고, traces/logs는 별도 정책으로 가져가는 팀이라면 metricWriter로 잘게 쪼갠 설계가 맞을 수도 있습니다.

정답보다 중요한 건 “서비스 계정/Workload Identity에 부여된 role이 지금 파이프라인의 contract다”를 문서화하는 쪽입니다.

## 체크리스트 2: 리소스/속성 정규화(= time series를 만들기 전에 자르기)

Cloud Monitoring에서 cardinality는 metric label과 resource label 조합으로 time series 수가 늘어나는 구조입니다. 공식 문서도 “label 값 조합마다 time series가 생긴다”를 반복해서 설명합니다.[^8]

OTLP → Prometheus 변환에서는 다음이 사실상 강제됩니다.

- metric datapoint attribute → Prometheus label
- resource attribute → `target_info`를 통해 label로 노출

그래서 OTel Collector에서 제일 먼저 해야 하는 건 “어떤 attribute를 남길지”의 결정을 파이프라인 중앙에서 강제하는 일입니다.

### 2-1) gcp.project_id를 확실히 넣는다
Google 문서는 `resource/gcp_project_id` processor로 `gcp.project_id`를 insert하는 예시를 줍니다.[^7]

이걸 명시적으로 넣어두면, 다음이 편해집니다.

- 멀티 프로젝트 파이프라인(collector 하나가 여러 project로 fan-out)로 확장할 때 기준점이 생김
- “이 datapoint가 어느 project로 가야 하는가”가 resource로 표현됨

### 2-2) resourcedetection은 “붙이는 것”이 아니라 “통제하기 위한 것”이다
문서 예시는 `resourcedetection`에서 `[

[^1]: <https://docs.cloud.google.cn/monitoring/docs/release-notes>
[^2]: <https://docs.cloud.google.com/stackdriver/docs/otlp/overview>
[^3]: <https://docs.cloud.google.com/stackdriver/docs/reference/telemetry/v1.metrics>
[^4]: <https://docs.cloud.google.com/kubernetes-engine/docs/concepts/managed-otel-gke?hl=en>
[^5]: <https://docs.cloud.google.com/stackdriver/docs/instrumentation/opentelemetry-collector-gke?hl=en>
[^6]: <https://docs.cloud.google.com/stackdriver/docs/otlp-metrics/deploy-collector>
[^7]: <https://docs.cloud.google.com/stackdriver/docs/otlp/migrate-collector-to-otlp-exporters?hl=en>
[^8]: <https://docs.cloud.google.com/monitoring/api/v3/metric-model?hl=en>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
