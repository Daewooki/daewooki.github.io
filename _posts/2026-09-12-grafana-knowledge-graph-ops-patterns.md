---
title: "Grafana Knowledge Graph 이후: 서비스 의존성 그래프를 운영에 쓰는 법"
description: "지표·로그·트레이스를 서비스 의존성 그래프로 묶어 장애 전파 추적, 소유권 라우팅, 변경 영향 분석을 SLO·온콜에 연결합니다."
date: 2026-09-12 09:28:16 +0900
categories: ["Data", "Grafana"]
tags: ["grafana", "observability", "knowledge-graph", "service-graph", "slo", "oncall"]
render_with_liquid: false
---

## Knowledge Graph 기본 포함이 바꾸는 전제

2026년 9월 7일 Grafana Labs는 Grafana Cloud의 신규 조직에서 Application Observability가 Knowledge Graph 기반 경험으로 **기본 포함**되며, classic Application Observability plugin을 대체한다고 공지했습니다. 환경 분리 규칙도 기본으로 들어가고(`deployment.environment`, `deployment.environment.name`), services catalog/서비스 상세 화면/전역 설정 위치도 Knowledge Graph 중심으로 재편됐습니다. [공지 원문](https://grafana.com/whats-new/2026-09-07-application-observability-now-includes-the-knowledge-graph-by-default/)에 적힌 변화는 단순 UI 업데이트가 아니라, “관측 데이터의 기본 인덱스가 time series가 아니라 entity graph”로 이동했다는 뜻에 가깝습니다.[^1]

같은 문서 흐름에서 Application Observability powered by the knowledge graph 문서는 2026년 9월 7일 이전에 온보딩된 조직은 classic 문서를 보라고 명시합니다. 날짜가 박혀 있다는 건 마이그레이션 과정에서 기능/메뉴/용어가 공존한다는 신호입니다. 운영 프로세스 설계를 할 때도 이 날짜를 기준으로 “팀 내부 문서/온콜 런북/알림 라우팅 템플릿”을 분기해야 혼란이 줄어듭니다.[^2]

다만 제품이 그래프를 제공한다고 해서, 팀이 그 그래프를 운영의 기본 언어로 사용하게 되지는 않습니다. 내 경험상 의존성 그래프는 도입 직후에 가장 많이 망가집니다. 이유는 단순합니다.

- 그래프는 그럴듯한데, alert/triage/ownership/change management의 “결정 지점”에 들어가지 못합니다.
- 그러면 그래프는 dashboard의 한 종류가 되고, 시간이 지나면 dashboard가 늘어나는 실패 패턴으로 회귀합니다.

이 글은 Knowledge Graph가 기본 포함이 된 지금(한국 시간 2026-09-12) “그래프를 운영의 결정을 만드는 도구로 붙이는 방법”을 정리합니다.

## 그래프 기반 관측이 실패하는 전형적인 이유

의존성 그래프가 있는 조직과, 의존성 그래프를 운영에 쓰는 조직은 다릅니다. 실패 패턴을 먼저 고정해두면 설계가 쉬워집니다.

### 그래프가 triage를 대신하지 못한다

그래프 화면은 보통 두 가지 질문에 답해야 합니다.

1) 지금 이 증상이 어디에서 시작됐는가
2) 지금 이 증상이 어디까지 전파됐는가

그런데 실제 온콜에서는 질문이 조금 다릅니다.

- “내가 지금 깨워야 하는 사람은 누구인가”
- “이 이슈가 SLO를 언제/얼마나 태울 것인가”
- “롤백이 맞는가, 우회가 맞는가, 아니면 기다릴 근거가 있는가”

그래프가 위 질문과 연결되지 않으면, 결국 triage는 원래 방식(알림 메시지 + 몇 개의 대시보드 + 경험자 호출)으로 돌아갑니다.

### 그래프의 node가 ‘서비스’가 아니거나, 서비스가 ‘팀’이 아니다

Knowledge Graph는 entity(서비스/Pod/노드/DB 등)와 relationship을 모델링합니다. [개요 문서](https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/introduction/)도 entities/관계/insights를 핵심으로 둡니다.[^3]

하지만 현실에서는 다음이 자주 어긋납니다.

- `service.name`이 프로세스 이름/Helm release/namespace 섞인 문자열로 난잡합니다.
- 멀티 클러스터/멀티 환경에서 `deployment.environment.name`가 빠져 “unknown”으로 빨려 들어갑니다.
- 서비스는 있는데 소유 팀 정보가 없습니다. 결국 온콜 라우팅은 “대충 플랫폼 팀”으로 수렴합니다.

이 상태에서 그래프를 아무리 예쁘게 그려도, 운영 의사결정은 못 합니다.

### 변경 이벤트와 그래프가 연결되지 않는다

운영에서 제일 싸고 강력한 RCA는 “직전에 뭐가 바뀌었는가”입니다. Knowledge Graph의 use case에도 ‘Track recent changes and their effects’가 들어가 있습니다.[^4]

그런데 변경 이벤트는 보통 CI/CD, feature flag, config repo, autoscaling, DB migration 등으로 흩어져 있습니다. 변경이 그래프의 entity와 동일한 key로 join되지 않으면, 변경 영향 분석은 사람 머리로만 남습니다.

이 실패 패턴을 막으려면 그래프를 만들고 보는 것을 목표로 삼으면 안 됩니다. 그래프를 “운영 프로세스의 인터페이스”로 다뤄야 합니다.

## Knowledge Graph의 그래프가 실제로 무엇으로 만들어지는가

Grafana Cloud Knowledge Graph를 관통하는 핵심은 “trace → span metrics/service graph metrics → entity graph”로 이어지는 파이프라인입니다. 제품 문서들이 이 흐름을 여러 곳에서 반복해서 강조합니다.

### Service graph metrics는 의존성 그래프의 가장 단단한 바닥

Tempo 문서의 [Service graphs](https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/)는 service graph가 traces를 처리해서 Prometheus metrics로 생성된다고 설명합니다. edge는 `client`, `server` label로 표현되며, 대표적으로 아래 같은 시계열이 만들어집니다.[^5]

- `traces_service_graph_request_total{client="app", server="db"}`
- `traces_service_graph_request_failed_total{client=...,server=...}`
- client/server 관점 duration histogram

이 metrics는 “그래프 UI”와 “알림/집계/쿼리”가 같은 바닥을 공유한다는 점이 중요합니다. 그래프가 운영에 들어가려면, UI가 아니라 이 metrics가 프로세스의 결정 지점에 들어가야 합니다.

### spans pairing의 제약은 운영 설계 제약이다

Service graph 생성은 양쪽 span(예: client span, server span)을 짝지어야 하므로, 동일 trace의 span이 여러 인스턴스로 흩어지면 pairing이 깨질 수 있다고 Tempo 문서는 명시합니다.[^5]

Grafana Alloy의 `otelcol.connector.servicegraph` 문서도 같은 제약을 반복하고, 해결책으로 load balancing exporter를 언급합니다.[^6]

이건 구현 디테일이 아니라 운영 설계 디테일입니다.

- tail sampling을 쓰거나 collector를 수평 확장할 때, service graph의 정확도가 흔들릴 수 있습니다.
- 정확도가 흔들리면 “장애 전파 추적”에서 blast radius가 과소/과대 추정됩니다.
- 그러면 온콜 프로세스에서 신뢰를 잃고, 그래프가 다시 장식물이 됩니다.

그래프 기반 운영을 하려면 “graph accuracy budget”를 따로 잡아야 합니다.

### 환경 분리는 `deployment.environment.name` 하나로 끝내야 한다

Grafana 공지에서 신규 조직은 `deployment.environment`와 `deployment.environment.name` 기반으로 자동 환경 분리 rules가 들어간다고 했고, 텔레메트리에 해당 attribute가 없으면 unknown으로 들어간다고 했습니다.[^1]

OpenTelemetry semantic conventions에서는 `deployment.environment.name`이 stable이고, `deployment.environment`는 deprecated로 명시돼 있습니다.[^7]

Grafana Knowledge Graph prerequisites 문서는 더 노골적으로 경고합니다. 둘을 섞으면 서비스가 metric마다 다른 환경으로 분리되어 scoping이 깨진다고요.[^8]

운영에서는 여기서 타협하면 안 됩니다.

- `deployment.environment.name`만 쓰고
- legacy가 있다면 수집 단계에서 변환하고
- 혼용을 금지해야 합니다.

이걸 못 지키면 그래프 기반 라우팅/분석이 지속적으로 헛발질을 합니다.

### Grafana Cloud 쪽 자동 metrics generation은 편하지만 비용과 통제가 따른다

Knowledge Graph는 Grafana Cloud에서 traces로부터 span metrics/service graph metrics를 생성하는 설정(Traces metrics generation)을 제공합니다. 이 설정은 dimension(어떤 attribute를 label로 승격할지), filter rules, histogram buckets, instance label 여부 등 “비용/카디널리티/정확도”를 직접 건드릴 수 있게 되어 있습니다.[^9]

운영 관점에서 보면 다음이 핵심입니다.

- attribute를 label로 올리는 순간, 그 attribute는 dashboard filter가 아니라 “alert routing key” 후보가 됩니다.
- 반대로 label로 올린 attribute는 비용과 쿼리 성능을 영구히 갉아먹을 수 있습니다.

즉, 그래프 기반 운영은 관측 스키마 설계와 동치입니다.

## 운영 패턴 1: 장애 전파 추적을 SLO triage 루프에 넣기

장애 전파 추적을 “그래프 화면에서 눈으로 따라가는 일”로 남겨두면 결국 쓰지 않습니다. 온콜의 루프에 들어가야 합니다.

내가 권하는 형태는 다음입니다.

1) 감지: SLO burn-rate alert가 먼저 울린다.
2) 분류: alert가 가리키는 서비스의 upstream/downstream을 그래프로 확장한다.
3) 결론: root candidate를 1~3개로 줄이고, 라우팅과 조치를 결정한다.

### SLO를 그래프의 entry point로 삼는 이유

Grafana SLO는 burn-rate alert rule을 자동 생성하고, fast/slow burn을 `grafana_slo_severity` label로 구분한다고 문서에 적혀 있습니다.[^10]

또한 Grafana Cloud SLO 문서는 SLO를 만들 때 labels/annotations를 추가해 라우팅과 컨텍스트를 붙이고, fast/slow burn alert를 만들 수 있다고 설명합니다.[^11]

이 구조를 쓰면 “증상 기반 알림(에러율/latency 임계치)”보다 훨씬 운영적으로 안정적입니다.

- fast burn: 지금 당장 사용자 영향이 커졌다는 신호
- slow burn: 점진적 퇴행이 쌓이고 있다는 신호

그래프 기반으로 triage할 때도 fast/slow burn은 다른 그래프 탐색 전략을 갖습니다.

- fast burn은 ‘전파 경로’가 중요하고
- slow burn은 ‘변경 영향’이 중요합니다.

### 장애 전파 추적을 표준화된 6단계로 만든다

온콜 런북에서 “그래프를 보세요”는 지시가 아닙니다. 체크리스트가 필요합니다. 아래는 내가 팀 프로세스로 굳히는 형태입니다.

1. **SLO alert가 가리키는 서비스(entity)를 고정**합니다.
   - 이때 entity key는 `service.name + service.namespace + deployment.environment.name` 정도가 가장 현실적입니다.

2. 해당 서비스의 inbound/outbound dependency를 1-hop으로 펼칩니다.
   - 근거 데이터는 `traces_service_graph_request_total` 같은 service graph metrics입니다.[^5]

3. 각 edge에 대해 “에러 전파인지, latency 전파인지”를 분리합니다.
   - outbound에서 upstream이 느려졌는데 inbound latency만 튄 경우(대기 증가)
   - outbound 에러가 증가했는데 inbound 에러도 튄 경우(전파)

4. 그래프에서 2-hop까지 확장합니다.
   - 1-hop에서 root가 나오지 않는 경우가 많습니다.
   - 단, 3-hop 이상은 사람의 집중력이 무너지고, noise도 폭증합니다.

5. root candidate를 1~3개로 줄입니다.
   - “변경이 있었던 node”
   - “에러가 upstream에서 먼저 터진 node”
   - “virtual node(비계측 구간)가 생긴 edge”

6. 라우팅과 액션을 동시에 결정합니다.
   - root 팀 호출
   - 우회(traffic shaping)
   - 롤백
   - dependency 차단(circuit breaker)

이게 되려면, 그래프가 단순 topology가 아니라 “시간축의 전파”를 읽을 수 있어야 합니다. Knowledge Graph는 entity graph를 1분마다 업데이트한다고 문서에 적습니다.[^12]

그래프 기반 장애 전파 추적의 운영 가치는, 이 6단계가 5분 안에 끝난다는 데 있습니다.

### Knowledge Graph UI를 쓸 때도 ‘metrics 기반 검증’을 같이 둔다

그래프 UI는 관계를 직관적으로 보여주지만, 온콜에서 중요한 건 “의심을 검증할 수 있는 PromQL/TraceQL/LogQL 링크”입니다.

Grafana Tempo의 service graph view 문서는 service graph를 span metrics/RED 신호 관점에서 drilldown하고, node 클릭으로 traces를 탐색할 수 있다고 설명합니다.[^13]

즉, 운영 프로세스에서는 아래 2가지를 동시에 가져가야 합니다.

- UI에서 root candidate를 좁힌다
- metrics query로 “정말 그 edge에서 실패율/지연이 증가했는지” 확인한다

그래프만 보고 판단하면, sampling/계측 누락/virtual node 때문에 오판하기 쉽습니다.

## 운영 패턴 2: 소유권 라우팅을 그래프에서 자동화하기

그래프 기반 운영이 실패하는 가장 흔한 이유는 “그래프를 봐도 누구를 깨울지 모르겠다”입니다. 이건 기술 문제가 아니라 책임 모델 문제입니다.

### 라우팅 단위는 ‘서비스 팀’이 아니라 ‘서비스의 책임 범위’로 잡는다

여기서 흔히 하는 실수는 service → team을 1:1로 고정하는 겁니다. 현실에서는 아래가 더 일반적입니다.

- same codebase, multiple ownership (예: API는 product 팀, infra는 platform 팀)
- shared dependency (예: auth, payment, messaging)
- migration 중인 서비스 (dual-run)

그래프 기반 라우팅은 1:1 매핑이 아니라, “이 edge의 failure mode는 누가 책임지는가”를 모델링해야 합니다.

Knowledge Graph 자체는 entities/relationships를 기반으로 한다고 설명합니다.[^3] 여기서 ownership은 제품이 알아서 주지 않습니다. 결국 조직이 태깅/카탈로그로 넣어야 합니다.

### Grafana Alerting과 OnCall에서 label 기반 라우팅을 통일한다

Grafana Alerting은 notification policies가 label matchers 트리로 라우팅된다고 문서에 명시합니다.[^14]

Grafana OnCall 역시 routes가 routing templates로 조건을 평가해 escalation chain을 선택하고, Grafana Cloud에서는 labels variable을 사용한 label 기반 라우팅이 가능하다고 문서에 적습니다.[^15]

여기서 중요한 설계 원칙은 하나입니다.

- alert label schema를 조직 표준으로 만들고
- Alerting과 OnCall이 그 schema를 그대로 소비하게 만든다

그래프 기반 라우팅은 이 label schema가 없으면 불가능합니다.

#### 내가 쓰는 최소 label 세트

- `service`: 알림의 1차 entity
- `env`: `deployment.environment.name`에 대응
- `team`: 1차 소유 팀
- `tier`: `frontend|backend|data|platform` 같은 비용/우선순위 힌트
- `dependency`: root 후보가 되는 upstream(자동으로 붙이면 좋고, 못 하면 런북에서 계산)

Grafana SLO는 자체적으로 UUID/window/severity label을 붙이지만(`grafana_slo_uuid`, `grafana_slo_window`, `grafana_slo_severity`), 그 외 조직 label은 사용자가 추가할 수 있는 구조입니다.[^10]

### OnCall route는 ‘서비스’가 아니라 ‘그래프 확장 결과’를 조건으로 삼는다

단순 라우팅은 `labels.team == "payments"` 같은 조건이면 충분합니다.[^15]

그래프 기반 라우팅은 한 단계 더 나갑니다.

- SLO가 터진 서비스가 A인데
- root는 B이고
- B의 소유 팀이 깨워져야 한다

이걸 자동화하려면 두 가지가 필요합니다.

1) dependency graph에서 upstream을 계산
2) upstream 소유권을 팀으로 해석

Grafana Cloud Knowledge Graph data source는 Cypher로 entity/relationship을 조회할 수 있고, `/search/cypher` 같은 endpoint도 나열합니다.[^16]

제품 안에서만 해결하려면 Knowledge Graph data source + alert enrichment(혹은 IRM workflow) 쪽 기능을 엮어야 하는데, 이 부분은 조직마다 구현이 달라집니다. 대신 “운영적으로 필요한 인터페이스”는 명확합니다.

- 입력: `service`, `env`
- 출력: upstream 1~2 hop의 `service` 목록 + 각 `team`

이 출력이 OnCall routing template에서 사용할 수 있는 label로 들어가면, 온콜 라우팅이 그래프를 따라갑니다.

### ‘그래프 기반 소유권’에서 가장 중요한 것은 false positive를 줄이는 것

그래프 기반 라우팅은 오작동하면 피해가 큽니다.

- 잘못된 팀을 깨우면 신뢰가 무너집니다.
- 결국 다시 “플랫폼 팀 단일 라우팅”으로 회귀합니다.

그래서 초기에는 이렇게 시작하는 게 안정적입니다.

- primary는 기존 방식대로 라우팅
- secondary로 “suspected root team”을 Slack 채널에만 추가
- 일정 기간(예: 4주) postmortem에서 정확도를 측정

정확도가 올라가면 escalation chain에 실제 paging을 걸면 됩니다.

Grafana IRM은 routing/escalation 개념을 문서로 정리하고 있고, routes/chain이 알림을 어디로 보낼지 결정한다고 설명합니다.[^17]

## 운영 패턴 3: 변경 영향 분석을 그래프 중심으로 재구성하기

변경 영향 분석은 보통 “이번 배포가 어떤 서비스에 영향을 줄까”에서 시작하지만, 운영에서는 반대로 굴러갑니다.

- 장애가 났다
- 최근 변경이 있었다
- 그 변경이 어디까지 영향을 줬는가

Knowledge Graph의 use case 목록에 ‘Track recent changes and their effects’가 별도 워크플로로 들어가 있는 이유가 여기 있다고 봅니다.[^4]

### 변경 이벤트를 그래프에 붙이는 키는 ‘배포 도구’가 아니라 ‘resource attribute’다

CI/CD 이벤트는 툴마다 API가 다르고, 팀마다 툴이 다릅니다. 그래프에 변경을 붙이려면 도구가 아니라 텔레메트리 스키마가 기준이 되어야 합니다.

OpenTelemetry deployment attribute registry는 `deployment.environment.name`, `deployment.id`, `deployment.name`, `deployment.status`를 정의합니다.[^7]

운영 설계에서 핵심은 이겁니다.

- trace/log/metric에 동일한 `deployment.id`(또는 `service.version`)가 들어가면
- 변경 이벤트는 observability 데이터와 join됩니다.

Knowledge Graph는 entities에 properties(환경/버전/클러스터 등)가 붙는다고 설명합니다.[^3] 여기서 version이 정확히 무엇을 기준으로 잡히는지는 조직마다 달라질 수 있으니, “배포 ID를 resource attribute로 강제”하는 게 안전합니다.

### 변경 영향 분석은 3가지 질문으로 고정한다

1) 변경이 발생한 entity는 무엇인가
2) 변경 이후 이상징후(insight/RED/SLO burn)가 시작된 entity는 무엇인가
3) 둘 사이의 최단 경로/전파 경로는 무엇인가

Knowledge Graph는 insights를 “connective tissue”로 설명하고, saturation/anomaly/error/failure/amend 같은 분류를 예로 듭니다.[^3]

이걸 운영 프로세스로 바꾸면 다음처럼 됩니다.

- 배포 후 30분은 dependency graph에서 2-hop 범위의 SLO burn을 감시한다
- anomaly는 참고, error/failure는 즉시 대응
- SLO burn이 0이 아니면 배포를 자동으로 멈추거나, canary를 확대하지 않는다

CI/CD gate를 observability 기반으로 만들려면 결국 그래프가 필요합니다. 단일 서비스만 보면 canary가 안전해 보이는데, downstream의 cache/queue/DB에서 문제가 시작되는 경우가 많기 때문입니다.

## 로컬 재현: traces에서 service graph를 만들고 blast radius를 계산하기

Grafana Cloud의 Knowledge Graph를 그대로 로컬에서 재현하는 건 범위가 큽니다. 대신 “그래프 기반 운영”에 필요한 최소 재료를 로컬에서 만들면, 팀 설계 논의를 훨씬 구체적으로 할 수 있습니다.

여기서는 다음을 구성합니다.

- 두 개의 HTTP 서비스(`checkout`, `payment`)가 서로 호출
- OpenTelemetry로 traces를 OTLP로 전송
- Grafana Alloy에서 `otelcol.connector.servicegraph`로 service graph metrics 생성[^6]
- Prometheus가 metrics를 scrape
- Python 스크립트가 Prometheus HTTP API로 edge를 읽고 blast radius 계산

버전은 다음을 기준으로 잡습니다.

- Grafana OSS 13.2.0 (2026-08-18 릴리스)[^18]
- Grafana Alloy v1.18.0 (ArtifactHub에 노출된 이미지 태그)[^19]
- Prometheus 3.14.0 (2026-08-17 latest)[^20]

### 1) docker-compose.yml

```yaml
services:
  grafana:
    image: grafana/grafana:13.2.0
    ports:
      - "3000:3000"
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning

  prometheus:
    image: prom/prometheus:v3.14.0
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro

  alloy:
    image: grafana/alloy:v1.18.0
    command:
      - run
      - /etc/alloy/config.alloy
      - --server.http.listen-addr=0.0.0.0:12345
    ports:
      - "4317:4317"   # OTLP gRPC
      - "12345:12345" # Alloy UI/metrics
      - "8889:8889"   # Prometheus scrape endpoint (otelcol.exporter.prometheus)
    volumes:
      - ./alloy/config.alloy:/etc/alloy/config.alloy:ro

  checkout:
    build: ./services/checkout
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4317
      - OTEL_EXPORTER_OTLP_PROTOCOL=grpc
      - OTEL_SERVICE_NAME=checkout
      - OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=local,service.namespace=shop
      - PAYMENT_URL=http://payment:8000
    ports:
      - "8001:8000"
    depends_on:
      - alloy
      - payment

  payment:
    build: ./services/payment
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4317
      - OTEL_EXPORTER_OTLP_PROTOCOL=grpc
      - OTEL_SERVICE_NAME=payment
      - OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=local,service.namespace=shop
      - ERROR_RATE=0.2
    ports:
      - "8002:8000"
    depends_on:
      - alloy

  loadgen:
    image: curlimages/curl:8.10.1
    depends_on:
      - checkout
    command: ["sh", "-c", "while true; do curl -sS http://checkout:8000/checkout >/dev/null || true; sleep 0.2; done"]
```

위 구성에서 `deployment.environment.name`을 명시적으로 넣습니다. Grafana Knowledge Graph도 이 attribute로 환경 스코핑을 한다고 문서에 적고, 누락되면 unknown으로 들어가며 혼용하면 깨진다고 경고합니다.[^8] 그리고 OpenTelemetry 쪽에서도 `deployment.environment.name`이 표준이며 `deployment.environment`는 deprecated입니다.[^7]

### 2) Alloy config: traces → servicegraph → prometheus exporter

`./alloy/config.alloy`

```hcl
// OTLP receiver
otelcol.receiver.otlp "ingest" {
  grpc {
    endpoint = "0.0.0.0:4317"
  }

  output {
    traces = [otelcol.connector.servicegraph.default.input]
  }
}

// Service graph connector (wrapper over upstream OTel Collector servicegraph)
otelcol.connector.servicegraph "default" {
  output {
    metrics = [otelcol.exporter.prometheus.sg_metrics.input]
  }
}

// Expose metrics for Prometheus to scrape
otelcol.exporter.prometheus "sg_metrics" {
  forward_to = []
  endpoint   = "0.0.0.0:8889"
}
```

이 구성은 trace 저장소를 두지 않고도 service graph metrics를 만들 수 있게 해줍니다. `otelcol.connector.servicegraph`가 traces를 받아 edge metrics를 만든다고 Alloy 문서에 명시되어 있습니다.[^6]

여기서 운영적으로 중요한 제한은, service graph는 edge의 양쪽 span을 pairing해야 해서 spans가 여러 Alloy 인스턴스로 흩어지면 신뢰도가 떨어진다는 점입니다. Alloy 문서도 load balancing을 해결책으로 적어둡니다.[^6]

### 3) Prometheus scrape 설정

`./prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 5s

scrape_configs:
  - job_name: "alloy-servicegraph"
    static_configs:
      - targets: ["alloy:8889"]
```

### 4) FastAPI 서비스 (현실적인 수준의 계측)

`./services/payment/requirements.txt`

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
opentelemetry-sdk==1.31.0
opentelemetry-exporter-otlp==1.31.0
opentelemetry-instrumentation-fastapi==0.52b0
opentelemetry-instrumentation-requests==0.52b0
```

`./services/payment/main.py`

```python
import os
import random
from fastapi import FastAPI, HTTPException

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = FastAPI()

ERROR_RATE = float(os.getenv("ERROR_RATE", "0.0"))
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "payment")

# Resource attributes: service.name는 SDK가 다루지만, 환경/namespace는 우리가 강제합니다.
resource = Resource.create({
    "service.name": SERVICE_NAME,
})

provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

FastAPIInstrumentor.instrument_app(app)

@app.get("/charge")
def charge(amount: int = 100):
    if random.random() < ERROR_RATE:
        raise HTTPException(status_code=500, detail="random payment failure")
    return {"ok": True, "amount": amount}
```

`./services/checkout/requirements.txt`

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
requests==2.32.3
opentelemetry-sdk==1.31.0
opentelemetry-exporter-otlp==1.31.0
opentelemetry-instrumentation-fastapi==0.52b0
opentelemetry-instrumentation-requests==0.52b0
```

`./services/checkout/main.py`

```python
import os
import requests
from fastapi import FastAPI

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

app = FastAPI()

PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8000")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "checkout")

resource = Resource.create({
    "service.name": SERVICE_NAME,
})

provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

FastAPIInstrumentor.instrument_app(app)
RequestsInstrumentor().instrument()

tracer = trace.get_tracer(__name__)

@app.get("/checkout")
def checkout():
    with tracer.start_as_current_span("checkout"):
        r = requests.get(f"{PAYMENT_URL}/charge", timeout=0.5)
        return {"payment_status": r.status_code}
```

여기서는 dependency의 존재를 “HTTP client/server span pair”로 만들었습니다. Tempo의 service graph processor가 client/server span.kind를 보고 edge를 만든다고 문서에 설명합니다.[^5]

### 5) 실행

```bash
docker compose up -d --build

# 생성된 service graph metrics가 있는지 확인
curl -sS http://localhost:8889/metrics | grep traces_service_graph_request_total | head

# Prometheus에서 edge가 쌓이는지 확인
curl -sS "http://localhost:9090/api/v1/query?query=traces_service_graph_request_total" | head
```

성공하면 `client="checkout"`, `server="payment"` 형태의 edge series가 생깁니다.

### 6) blast radius 계산 스크립트

이제 “운영 패턴”으로 연결되는 부분을 만듭니다. Prometheus에 저장된 service graph metrics를 읽어 adjacency list를 만들고, 특정 서비스에서 upstream/downstream을 계산합니다.

`./tools/blast_radius.py`

```python
import os
import sys
import requests
from collections import defaultdict, deque

PROM = os.getenv("PROM_URL", "http://localhost:9090")

def prom_query(query: str):
    r = requests.get(f"{PROM}/api/v1/query", params={"query": query}, timeout=5)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "success":
        raise RuntimeError(data)
    return data["data"]["result"]

# traces_service_graph_request_total은 client/server label을 갖습니다.[^5]
EDGE_QUERY = "traces_service_graph_request_total"

def build_graph():
    edges = prom_query(EDGE_QUERY)
    out = defaultdict(set)
    inc = defaultdict(set)

    for ts in edges:
        m = ts.get("metric", {})
        c = m.get("client")
        s = m.get("server")
        if not c or not s:
            continue
        out[c].add(s)
        inc[s].add(c)

    return out, inc

def bfs(start: str, graph, max_hops: int):
    seen = {start: 0}
    q = deque([start])

    while q:
        cur = q.popleft()
        d = seen[cur]
        if d >= max_hops:
            continue
        for nxt in sorted(graph.get(cur, [])):
            if nxt not in seen:
                seen[nxt] = d + 1
                q.append(nxt)
    return seen

def main():
    if len(sys.argv) < 2:
        print("Usage: python blast_radius.py <service> [hops]", file=sys.stderr)
        sys.exit(2)

    start = sys.argv[1]
    hops = int(sys.argv[2]) if len(sys.argv) >= 3 else 2

    out, inc = build_graph()

    down = bfs(start, out, hops)
    up = bfs(start, inc, hops)

    print(f"Service: {start}")
    print(f"Downstream (<= {hops} hops):")
    for svc, d in sorted(down.items(), key=lambda x: (x[1], x[0])):
        if svc == start:
            continue
        print(f"  - {svc} (hop {d})")

    print(f"Upstream (<= {hops} hops):")
    for svc, d in sorted(up.items(), key=lambda x: (x[1], x[0])):
        if svc == start:
            continue
        print(f"  - {svc} (hop {d})")

if __name__ == "__main__":
    main()
```

실행:

```bash
python -m venv .venv
. .venv/bin/activate
pip install requests

python tools/blast_radius.py checkout 2
```

예상 출력(환경에 따라 순서는 달라질 수 있음):

```txt
Service: checkout
Downstream (<= 2 hops):
  - payment (hop 1)
Upstream (<= 2 hops):
```

이 스크립트는 단순해 보이지만, 온콜 프로세스에 넣을 때 강력합니다.

- SLO alert가 `service=checkout`로 왔을 때
- 런북 첫 줄이 `blast_radius.py checkout 2`가 됩니다.
- 여기서 나온 downstream 서비스들의 team을 붙이면, 그래프 기반 라우팅이 시작됩니다.

Grafana Cloud에서는 Knowledge Graph data source로 같은 결과를 Cypher로 뽑는 것도 가능합니다. 예를 들면 다음 같은 형태로 시작할 수 있습니다(쓰기 쿼리는 막히고 read만 허용된다고 문서에 명시).[^16]

```cypher
MATCH (s:Service {name: "checkout"})-[:CALLS*1..2]->(d:Service)
RETURN s, d
```

로컬에서는 Prometheus metrics 기반으로 시작하고, Cloud 환경에서는 Knowledge Graph datasource 기반으로 옮기는 전략이 마이그레이션 비용이 적습니다.

## 함정과 트레이드오프: 그래프를 운영에 넣을 때 깨지는 지점

### 1) 카디널리티는 그래프의 기능을 먹고 산다

Grafana Cloud의 Traces metrics generation 설정은 dimensions를 켤 때 cardinality를 보여주고, label을 더 올리면 비용이 증가한다고 경고합니다.[^9]

운영 패턴 관점에서는 이게 “필터가 늘어나는 문제”가 아니라 “라우팅 키가 늘어나는 문제”로 해석됩니다.

- 너무 많은 label을 올리면 alert route가 복잡해져 유지보수성이 무너집니다.
- 너무 적게 올리면 서비스/환경/클러스터 분리가 안 돼서 그래프 탐색이 부정확해집니다.

내 결론은 단순합니다.

- env/namespace/cluster 같은 “운영 스코프”에 해당하는 것만 올리고
- request path/user id 같은 것은 절대 올리지 않습니다.

### 2) sampling은 service graph의 수치 해석을 망가뜨릴 수 있다

Tempo service graph 문서는 sampling이 있을 때 request count가 과소 추정되며, `span_multiplier_key` 같은 옵션으로 스케일링할 수 있다고 설명합니다.[^5]

Grafana Cloud Traces metrics generation 문서도 span multiplier key를 제공하고, sampling이 있을 때 현실적인 수치로 보정할 수 있다고 적습니다.[^9]

운영에서 이게 중요한 이유는 이렇습니다.

- SLO burn-rate는 “절대 실패 수”가 아니라 “비율”이라서 sampling에 상대적으로 강합니다.
- 하지만 blast radius 계산에서 “traffic이 있는 edge/없는 edge” 판단은 sampling에 약합니다.

즉,

- 그래프를 topology로 쓰는 건 괜찮지만
- 그래프 edge의 traffic 크기까지 근거로 쓰려면 sampling 정책과 multiplier를 같이 설계해야 합니다.

### 3) `deployment.environment.name` 혼용은 그래프 운영을 끝장낸다

이건 앞에서 말했지만, 다시 적어둘 가치가 있습니다.

Knowledge Graph prerequisites는 환경 attribute를 섞으면 서비스가 metric마다 다른 환경으로 분리된다고 경고합니다.[^8]

이 상태에서는 다음이 모두 깨집니다.

- 온콜 라우팅: prod/stage가 섞여 불필요한 paging
- 변경 영향 분석: stage 배포가 prod 그래프에 붙음
- SLO: 환경별 SLO가 분리되지 않음

그래프 기반 운영에서 환경 스코핑은 선택이 아니라 전제입니다.

### 4) instrumentation quality는 ‘계측 점수’가 아니라 ‘운영 가능성 점수’다

Application Observability powered by the knowledge graph는 services catalog에 instrumentation quality 개념이 있고, 계측 품질을 평가한다고 설명합니다.[^2]

또한 instrumentation quality 문서는 service graph metrics가 없으면 서비스가 어떻게 통신하는지 보여줄 수 없고, span metrics가 없으면 Service Overview가 비게 된다고 적습니다.[^21]

이걸 운영적으로 번역하면 다음입니다.

- service graph metrics가 없는 서비스는 “전파 추적 대상에서 제외”됩니다.
- 그런 서비스가 핵심 경로에 있으면, 그래프 기반 운영은 그 순간 무너집니다.

그래서 온콜 체계에서 instrumentation quality는 대시보드용 지표가 아니라, SLO/온콜의 prerequisites로 다뤄야 합니다.

- 특정 티어 이상의 서비스는 instrumentation quality 기준을 충족해야 배포 가능
- 충족하지 못하면 최소한 “소유 팀이 책임지고 런북에 수동 절차”를 넣어야 함

## 도입 판단 기준: 그래프를 운영에 쓰는 팀과 쓰지 못하는 팀

그래프 기반 운영은 제품 기능이 아니라 조직의 인터페이스 설계입니다. 아래 조건이 충족되면 성공 확률이 올라갑니다.

1) 서비스 식별자가 정리돼 있다 (`service.name`, `service.namespace`, `deployment.environment.name`).[^7]
2) service graph metrics가 안정적으로 생성된다(collector topology, sampling 보정 포함).[^5]
3) SLO burn-rate가 triage의 entry point다.[^10]
4) alert label schema가 표준화돼 있고, Alerting/OnCall이 같은 schema로 라우팅한다.[^14]
5) 변경 이벤트가 resource attribute로 관측 데이터에 들어가서 그래프와 join된다.[^7]

반대로 아래 중 하나라도 크면, 그래프는 dashboard로 남을 가능성이 큽니다.

- 서비스 소유권이 문서/사람 머리에만 있음
- 환경 스코핑이 흔들림
- oncall 라우팅이 label 기반이 아니라 수동으로 유지됨

Knowledge Graph가 기본 포함이 됐다는 건 출발점이 낮아졌다는 뜻이지, 운영 설계가 자동으로 완성된다는 뜻은 아닙니다. 그래프를 운영에 쓰는 팀은 “그래프를 보는 방법”이 아니라 “그래프를 운영 프로세스의 결정 지점에 넣는 방법”을 설계한 팀입니다.

관련해서 Knowledge Graph를 RAG/GraphRAG 관점으로 다룬 글은 이미 블로그에 정리해둔 바 있습니다. 운영 그래프는 질문 응답을 위한 지식 그래프가 아니라, 의사결정과 책임을 위한 실행 그래프에 가깝고, 그 차이 때문에 스키마/라벨/프로세스가 훨씬 중요해집니다.

- [GraphRAG 구현 가이드: Knowledge Graph로 “멀티홉 질문”을 깨끗하게 푸는 RAG 아키텍처](https://daewooki.github.io/posts/2026-graphrag-knowledge-graph-rag-1/)
- [GraphRAG(2026.7)로 Knowledge Graph RAG를 “프로덕션급”으로 구현하는 법: 인덱싱 비용, Local/Global/DRIFT 설계, Neo4j 연동까지](https://daewooki.github.io/posts/graphrag20267-knowledge-graph-rag-localg-2/)

운영 그래프를 도입할 때는 “질문을 잘 답하는가”보다 “누가 언제 무엇을 결정하는가”가 먼저 고정돼야 하고, 그 결정 지점에 그래프가 들어가면 대시보드는 줄어들기 시작합니다.

## 참고 자료

- [Application Observability now includes the knowledge graph by default](https://grafana.com/whats-new/2026-09-07-application-observability-now-includes-the-knowledge-graph-by-default/)
- [Application Observability powered by the knowledge graph](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/application-observability-kg/)
- [Introduction to the knowledge graph](https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/introduction/)
- [Use cases (Grafana Cloud Knowledge Graph)](https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/use-cases/)
- [Entity graph](https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/troubleshoot-infra-apps/explore-entity-graph/)
- [Knowledge graph data source](https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/reference/datasource/)
- [Configure Traces metrics generation](https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/configure/traces-metrics-generation/)
- [Instrumentation quality](https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/troubleshoot-infra-apps/explore-entity-catalog/instrumentation-quality/)
- [Service graphs (Grafana Tempo)](https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/)
- [Service graph view (Grafana Tempo)](https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/service-graph-view/)
- [otelcol.connector.servicegraph (Grafana Alloy)](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.connector.servicegraph/)
- [Deployment attributes (OpenTelemetry semantic conventions)](https://opentelemetry.io/docs/specs/semconv/registry/attributes/deployment/)
- [Prerequisites (Grafana Cloud Knowledge Graph)](https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/get-started/prerequisites/)
- [Create SLOs (Grafana Cloud)](https://grafana.com/docs/grafana-cloud/observe-and-act/alert-and-measure-reliability/slo/create/)
- [Configure burn-rate notifications (Grafana SLO)](https://grafana.com/docs/plugins/grafana-slo-app/latest/set-up/configure-burn-rate-notifications/)
- [Configure notification policies (Grafana Alerting)](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/create-notification-policy/)
- [Escalation chains and routes for OnCall OSS](https://grafana.com/docs/oncall/latest/configure/escalation-chains-and-routes/)
- [Download Grafana OSS 13.2.0](https://grafana.com/grafana/download?edition=oss&platform=linux)
- [Prometheus downloads (3.14.0, 2026-08-17)](https://prometheus.io/download/)

[^1]: <https://grafana.com/whats-new/2026-09-07-application-observability-now-includes-the-knowledge-graph-by-default/>
[^2]: <https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/application-observability-kg/>
[^3]: <https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/introduction/>
[^4]: <https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/use-cases/>
[^5]: <https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/>
[^6]: <https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.connector.servicegraph/>
[^7]: <https://opentelemetry.io/docs/specs/semconv/registry/attributes/deployment/>
[^8]: <https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/get-started/prerequisites/>
[^9]: <https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/configure/traces-metrics-generation/>
[^10]: <https://grafana.com/docs/plugins/grafana-slo-app/latest/set-up/configure-burn-rate-notifications/>
[^11]: <https://grafana.com/docs/grafana-cloud/observe-and-act/alert-and-measure-reliability/slo/create/>
[^12]: <https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/troubleshoot-infra-apps/explore-entity-graph/>
[^13]: <https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/service-graph-view/>
[^14]: <https://grafana.com/docs/grafana/latest/alerting/configure-notifications/create-notification-policy/?pg=new-in-grafana-6-6-forcing-minimum-alert-evaluation-frequency&plcmt=in-text>
[^15]: <https://grafana.com/docs/oncall/latest/configure/escalation-chains-and-routes/>
[^16]: <https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/reference/datasource/>
[^17]: <https://grafana.com/docs/grafana-cloud/observe-and-act/respond-to-incidents/introduction/routing-and-escalation/>
[^18]: <https://grafana.com/grafana/download?edition=oss&platform=linux>
[^19]: <https://artifacthub.io/packages/helm/grafana/alloy>
[^20]: <https://prometheus.io/download/>
[^21]: <https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/troubleshoot-infra-apps/explore-entity-catalog/instrumentation-quality/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
