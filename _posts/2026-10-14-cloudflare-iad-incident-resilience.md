---
title: "Cloudflare IAD 성능 이슈가 전 서비스 에러로 번지는 패턴"
description: "IAD 네트워크 성능 저하가 타임아웃·에러 폭증으로 번질 때, 우리 서비스에서 재현·탐지·완화하는 설계를 정리합니다."
date: 2026-10-14 13:14:37 +0900
categories: ["News", "Cloud"]
tags: ["cloudflare", "cdn", "outage", "multi-cdn", "resilience", "routing"]
render_with_liquid: false
---

## 사건 요약: status page 한 줄이 말해주지 않는 것

Cloudflare는 **2026-10-13 16:39~17:07 UTC** 구간에 Major incident로 *Cloudflare Service Issues*를 공지했고, 원인을 “IAD의 network performance 이슈 → Cloudflare services 전반의 errors 증가”로 적었습니다. 사용자는 Cloudflare 네트워크/서비스로의 접근에서 error 또는 timeout을 경험할 수 있었다는 수준에서 사건이 닫혔습니다.[^1]

여기서 중요한 포인트는 두 가지입니다.

- 이 사건은 “특정 제품(Workers, R2, WAF 등) 단독 장애”가 아니라, **엣지 네트워크 성능 저하가 여러 서비스의 오류율을 동시에 끌어올리는 형태**였습니다.[^1]
- 같은 날(UTC) 더 이른 시간대에 *Network performance issues in Ashburn, US (IAD)* 라는 별도 incident가 **2026-10-13 04:00~14:56 UTC** 동안 Minor로 열려 있었고, 업데이트 본문에 third-party circuit maintenance, capacity restoration 등의 표현이 등장합니다. “IAD 주변부에서 성능/용량 변동이 있었고, 그 여파가 다른 형태(전 서비스 오류 증가)로 재등장할 수 있다”는 리스크 신호로 읽을 수 있습니다.[^2]

KST로 바꿔 적어두면 감이 더 정확해집니다(오늘이 2026-10-14 KST인 이유도 여기서 연결됩니다).

- Major incident(Cloudflare Service Issues)
  - 시작: **2026-10-13 16:39 UTC = 2026-10-14 01:39 KST**
  - 해소: **2026-10-13 17:07 UTC = 2026-10-14 02:07 KST**[^1]
- 같은 날 IAD 성능 이슈(Minor)
  - 시작: **2026-10-13 04:00 UTC = 2026-10-13 13:00 KST**
  - 해소: **2026-10-13 14:56 UTC = 2026-10-13 23:56 KST**[^2]

status page 한 줄만 보면 “28분짜리 Major incident”로 끝나지만, 실제 운영 관점에서는 “네트워크 성능 저하가 관측되는 구간이 길었고(최소 수 시간), 그 사이에 전면 장애로 보이는 구간이 다시 튀어나올 수 있다”는 쪽이 더 실전적인 해석입니다.

예전에 내가 썼던 글 중 [Cloudflare Ashburn(IAD) 구간 5xx 급증이 SLO를 깨는 방식](https://daewooki.github.io/posts/cloudflare-iad-pop-outage-slo/)에서 ‘특정 POP/리전의 이상이 애플리케이션 SLO를 어떻게 깨는지’를 길게 다뤘는데, 이번 건은 그 패턴이 “전 서비스 에러”로 확장될 때를 상정해야 합니다. 같은 현상이 내 서비스에서 재발하면, status page를 본 뒤에야 알게 되는 수준으로는 늦습니다.

## IAD 성능 저하가 왜 ‘전 서비스 에러’로 보이나

Cloudflare가 사건 설명에 사용한 문구는 간단합니다.

- “issues with network performance in IAD”
- “resulted in an increase in errors across Cloudflare services”
- “users may have experienced increased errors or timeouts”[^1]

이걸 운영/아키텍처 관점으로 번역하면 대략 아래 3가지 축에서 문제가 커집니다.

### 1) Anycast + 대도시 허브 POP의 ‘부분 성능 저하’는 사용자에게 전면 장애처럼 보인다

대부분의 CDN/엣지 네트워크는 Anycast와 라우팅 정책으로 “가까운 곳”에 붙이려 합니다. 그런데 ‘가까움’은 지리적 거리가 아니라 BGP/피어링/혼잡 상태에 의해 뒤틀립니다. 결과적으로 특정 POP(IAD)에서 **latency↑, packet loss↑, 큐잉↑** 같은 성능 저하가 생기면, 그 POP에 물린 트래픽은 제품이 무엇이든(캐시, WAF, Workers, API, 대시보드 등) 비슷한 증상을 보일 수 있습니다.

겉보기엔 “API가 죽었나?”, “Workers가 터졌나?”처럼 보이지만, 실제로는 **요청이 POP에 도착한 뒤 다음 홉으로 못 나가거나, 내부/외부 경로가 나빠져서 타임아웃이 늘어나고, 그 결과로 에러가 연쇄**합니다.

Cloudflare가 과거에 공개한 네트워크/오류 계열 incident 보고서를 보면, backbone 혼잡이나 트래픽 엔지니어링(자동/수동) 과정에서 TTFB p99가 튀고 오류율이 상승하는 타입이 반복적으로 등장합니다(이번과 동일 사건은 아니지만, 메커니즘을 이해하는 데는 도움이 됩니다). 예: [Cloudflare incident on June 20, 2024](https://blog.cloudflare.com/cloudflare-incident-on-june-20-2024/)[^3]

### 2) ‘성능 저하’는 에러로 변환되기 쉽다: timeout budget이 있기 때문

네트워크가 느려지면 처음에는 latency로 보입니다. 하지만 프로덕션에선 latency가 일정 임계치를 넘는 순간부터 **timeout**으로 변환됩니다.

- 브라우저/모바일 SDK의 connect timeout
- CDN edge의 origin connect timeout
- upstream idle/read timeout
- proxy의 per-try timeout
- gRPC deadline

이 timeout은 흔히 재시도(retry)를 유발합니다. 재시도는 순간적으로 트래픽을 2배, 3배로 만들어 혼잡을 더 키웁니다. “성능 저하”가 “오류율 급증”으로 변하는 전형적인 경로입니다.

Cloudflare의 522 문서가 설명하는 것처럼(이건 Cloudflare↔origin 구간의 대표적인 timeout 형태를 정리한 자료지만), timeout은 TCP 연결 전/후 구간에서 서로 다른 타이머로 발생합니다. 즉, 네트워크가 나빠지면 아주 다양한 형태의 timeouts가 섞여 나옵니다. [Error 522](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-522/)[^4]

### 3) “서비스별 장애”가 아니라 “공통 경로 장애”면, 의존 서비스가 많은 쪽이 더 크게 다친다

엣지를 쓰는 이유가 ‘의존성 단순화’가 아니라 ‘의존성 고도화’가 되는 순간이 있습니다.

- 정적 자산: CDN 캐시
- 동적 API: CDN 프록시(보호/WAF/봇)
- 인증/봇: edge에서 판정
- observability: edge 로그/메트릭

이 중 하나만 타격이면 부분 기능 저하로 끝날 수 있지만, POP 성능 저하처럼 공통 경로가 흔들리면 사용자는 “사이트 전체가 죽었다”로 인식합니다.

## 우리 서비스 관점에서의 증상 모델: 에러/타임아웃을 ‘층위’로 분해하기

IAD 성능 저하 같은 사건을 내 서비스에서 다루려면, status page의 “error/timeout 증가”라는 표현을 **계측 가능한 분류 체계**로 바꿔야 합니다.

나는 보통 (A) 사용자 체감, (B) 엣지↔오리진, (C) 오리진 내부 3층으로 나눕니다.

### A. 사용자 체감(브라우저/앱): 실패가 먼저 보이는 지점

- DNS lookup 실패/지연
- TCP connect timeout
- TLS handshake 지연/실패
- HTTP 5xx
- HTTP 4xx(특히 429/403처럼 보호 계층이 과민해질 때)
- “로딩만 도는” 형태(타임아웃이 길면 사용자에겐 멈춘 것처럼 보임)

이 층위는 RUM(Real User Monitoring)이나 앱 로그로 잡아야 합니다. synthetic probe만으로는 “특정 ISP/지역의 경로 문제”가 빠집니다.

### B. 엣지↔오리진: CDN/프록시가 에러를 ‘만드는’ 구간

Cloudflare를 예로 들면, 이 구간에서 522/524/520 계열이 섞여 나옵니다. 특히 522는 “Cloudflare가 origin에 타임아웃”이라는 의미를 분명히 갖습니다. [Error 522](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-522/)[^4]

중요한 건 “우리 오리진이 실제로 느려졌는지”와 “Cloudflare↔오리진 경로가 느려졌는지”를 구분하는 것입니다. IAD 성능 저하 사건은 후자일 확률이 높습니다. 후자라면 오리진 CPU/DB 메트릭은 멀쩡한데 사용자 오류만 튀는, 운영자 입장에서 가장 짜증나는 그림이 됩니다.

### C. 오리진 내부: 장애가 확대 재생산되는 구간

엣지가 느려지면 오리진은 보통 이렇게 망가집니다.

- connection pool 고갈(keep-alive가 깨지고 새 연결이 늘어남)
- thread/worker 점유 증가(타임아웃 대기)
- 큐 적체
- retry storm으로 유입량 증가

결국 오리진이 5xx를 실제로 내기 시작하고, 그러면 엣지가 stale을 못 쓰는 엔드포인트(API 등)는 더 빨리 무너집니다.

## 재현: ‘성능 저하 → 타임아웃 → 재시도 증폭’을 실험으로 확인하기

Cloudflare IAD 같은 POP 성능 저하를 그대로 복제할 수는 없습니다. 대신 “네트워크가 느려졌을 때 시스템이 어떤 모드로 무너지는지”는 충분히 재현 가능합니다.

여기서는 세 가지를 확인하는 실험을 만듭니다.

1) upstream latency가 늘면 timeout이 어떻게 늘어나는지
2) retry가 있으면 오류율이 왜 더 커지는지
3) retry budget/circuit breaker로 얼마나 완화되는지

Envoy는 이런 실험에 적합합니다. retry budget과 circuit breaker를 문서로 명확히 정의하고 있어서, 정책을 코드로 고정할 수 있습니다. [Envoy circuit breakers proto](https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto.html)[^5]

### docker-compose 구성

- origin: Python FastAPI(느린 응답을 의도적으로 만들 수 있는 API)
- toxiproxy: origin 앞단에 latency 주입
- envoy: 클라이언트가 붙는 프록시(재시도/타임아웃/서킷 브레이커 적용)

#### 1) 파일: `compose.yaml`

```yaml
services:
  origin:
    image: python:3.12-slim
    working_dir: /app
    command: bash -lc "pip install -q fastapi uvicorn && python origin.py"
    volumes:
      - ./origin.py:/app/origin.py:ro
    ports:
      - "8000:8000"

  toxiproxy:
    image: ghcr.io/shopify/toxiproxy:2.7.0
    ports:
      - "8474:8474"   # toxiproxy API
      - "9001:9001"   # proxy listen

  envoy:
    image: envoyproxy/envoy:v1.32.0
    depends_on:
      - toxiproxy
    ports:
      - "8080:8080"
      - "9901:9901"  # admin
    volumes:
      - ./envoy.yaml:/etc/envoy/envoy.yaml:ro
```

#### 2) 파일: `origin.py`

```python
from fastapi import FastAPI
import time
import os

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/v1/item/{item_id}")
def get_item(item_id: str, delay_ms: int = 0):
    # 실전에서의 DB/외부 API 지연을 흉내냅니다.
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    return {"item_id": item_id, "delay_ms": delay_ms}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

#### 3) 파일: `envoy.yaml` (의도적으로 “나쁜 기본값”부터)

- per-try timeout 700ms
- 2회 retry
- gateway-error/connect-failure 계열에서 retry

```yaml
static_resources:
  listeners:
    - name: listener_http
      address:
        socket_address: { address: 0.0.0.0, port_value: 8080 }
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: ingress_http
                route_config:
                  name: local_route
                  virtual_hosts:
                    - name: origin
                      domains: ["*"]
                      routes:
                        - match: { prefix: "/" }
                          route:
                            cluster: origin_cluster
                            timeout: 1s
                            retry_policy:
                              retry_on: "connect-failure,refused-stream,gateway-error,reset"
                              num_retries: 2
                              per_try_timeout: 700ms
                http_filters:
                  - name: envoy.filters.http.router
  clusters:
    - name: origin_cluster
      type: STRICT_DNS
      connect_timeout: 200ms
      lb_policy: ROUND_ROBIN
      load_assignment:
        cluster_name: origin_cluster
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: toxiproxy
                      port_value: 9001
admin:
  access_log_path: /tmp/admin_access.log
  address:
    socket_address: { address: 0.0.0.0, port_value: 9901 }
```

### 실행

```bash
docker compose up -d

# toxiproxy에 origin으로 가는 upstream 등록
curl -sS -X POST http://localhost:8474/proxies \
  -H 'Content-Type: application/json' \
  -d '{"name":"origin","listen":"0.0.0.0:9001","upstream":"origin:8000"}' | jq

# 정상 응답 확인
curl -sS "http://localhost:8080/v1/item/123?delay_ms=10" | jq
```

예상 출력(형태):

```json
{
  "item_id": "123",
  "delay_ms": 10
}
```

### 장애 주입: latency 900ms 추가

```bash
# downstream(Envoy->origin) 경로에 지연을 추가
curl -sS -X POST http://localhost:8474/proxies/origin/toxics \
  -H 'Content-Type: application/json' \
  -d '{"name":"latency","type":"latency","stream":"downstream","attributes":{"latency":900,"jitter":100}}' | jq

# 이제 요청은 timeout/5xx가 섞여 나오기 시작합니다.
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8080/v1/item/123?delay_ms=50"
done
```

여기서 관측하고 싶은 건 단순히 “실패한다”가 아닙니다.

- timeout이 늘면서 재시도가 붙고
- 재시도가 붙으면서 origin으로 들어가는 시도 횟수가 늘고
- 이게 다시 혼잡/지연을 키우는 피드백이 생기는지

이 실험은 POP 성능 저하를 “네트워크 지연”으로 단순화했지만, 운영에서 흔히 보는 장애 확대 경로를 그대로 보여줍니다.

### 완화 1: retry budget / circuit breaker 적용(프록시 계층)

Envoy는 retry를 무제한으로 허용하지 않도록 retry budget을 둘 수 있습니다. retry budget은 “활성 요청 수 대비 동시 retry 수 비율” 같은 방식으로 제한을 겁니다. [Envoy circuit breakers proto](https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto.html)[^5]

또한 transient failure 대응에서 retry budget을 어떻게 써야 하는지 FAQ 형태로 가이드가 있습니다. [How do I handle transient failures?](https://www.envoyproxy.io/docs/envoy/v1.32.0/faq/load_balancing/transient_failures)[^6]

위 `envoy.yaml`에 아래처럼 circuit breakers를 추가하는 방식으로 실험을 이어갈 수 있습니다.

```yaml
  clusters:
    - name: origin_cluster
      # ... 기존 설정 생략 ...
      circuit_breakers:
        thresholds:
          - priority: DEFAULT
            max_connections: 100
            max_pending_requests: 100
            max_requests: 200
            retry_budget:
              budget_percent: { value: 20 }
              min_retry_concurrency: 3
```

이걸 적용한 뒤 다시 latency toxic을 켠 상태에서 반복 호출을 하면, “재시도로 인해 전체가 더 망가지는” 속도가 확실히 느려집니다. POP 성능 저하 같은 사건에서 내가 원하는 건 보통 이겁니다.

- 일부 사용자는 느려지거나 실패하더라도
- 시스템이 자기 증폭으로 전면 장애로 번지지는 않는다

결국 **“성능 저하를 장애로 키우지 않는 정책”**이 핵심입니다.

## 탐지: status page + 우리 관측 + 라우팅 신호를 합치는 방법

Cloudflare 상태 페이지를 보는 것 자체는 시작점입니다. 그러나 ‘탐지’로 쓰려면 자동화된 형태가 되어야 하고, 무엇보다 우리 서비스의 관측과 결합되어야 합니다.

여기서는 세 가지 입력을 결합합니다.

1) Cloudflare Status API(공식)
2) 우리 서비스의 synthetic probe(멀티 리전)
3) 우리 서비스의 실사용자 오류율/타임아웃(RUM/앱 로그)

### 1) Cloudflare Status API로 “공급자 incident”를 구조화해서 받기

Cloudflare Status는 HTML 스크래핑 대신 API 사용을 권장합니다. summary/status/components/incidents가 v2 엔드포인트로 열려 있습니다. [Cloudflare Status API](https://www.cloudflarestatus.com/api)[^7]

예: 최근 incident 목록

```bash
curl -sS https://www.cloudflarestatus.com/api/v2/incidents.json \
  -H 'User-Agent: my-monitor/1.0 (+mailto:ops@example.com)' | jq '.incidents[0].name'
```

이번 글의 대상 incident도 여기에서 그대로 확인됩니다(incident id: `z7vongh8rqc1`).[^2]

또 한 가지: status page 자체 알림도 webhook을 지원합니다. (Cloudflare 내부 인프라가 흔들려도 알림은 status page 시스템에서 전달된다는 설명이 명시되어 있습니다.) [Status Page Notifications](https://www.cloudflarestatus.com/docs/notifications)[^8]

나는 “공급자 incident가 열림/업데이트됨” 자체를 paging 조건으로 쓰지는 않습니다. 대신 아래처럼 취급합니다.

- incident는 **상관관계(correlation) 힌트**
- 실제 트래픽 영향은 우리 synthetic/RUM으로 확정

### 2) 우리 관측에서 ‘IAD 같은 POP 이슈’를 잡는 지표 설계

IAD 성능 이슈는 “오리진이 죽어서 5xx”가 아니라 “경로가 나빠져서 timeout이 늘고, 그게 5xx/사용자 실패로 변환”되는 쪽이 더 흔합니다.

그래서 synthetic는 단순히 `/health` 200 확인으로는 부족합니다. 최소한 아래를 포함해야 합니다.

- **실제 사용자 경로와 같은 hostname**으로 요청(캐시/보안 정책이 동일해야 함)
- 1개 API가 아니라 핵심 플로우 2~3개(로그인, 결제, 콘텐츠 조회 등)
- 응답 코드뿐 아니라 TTFB, connect, TLS handshake 분리(가능하면)
- 응답 본문 checksum(에러 페이지를 200으로 받아도 걸러야 함)

multi-CDN을 진지하게 할 생각이면, health check는 “각 CDN을 통해 같은 오브젝트를 가져오는지”를 검사해야 합니다. 이런 관점을 단계별로 적어둔 글이 있어 참고가 됩니다. [Multi-CDN failover: a working setup, step by step](https://www.cdnworld.com/guide/multi-cdn-failover-setup)[^9]

### 3) 라우팅 신호: POP/colo 단위로 문제를 ‘묶어서’ 본다

Cloudflare를 쓰면 요청/응답 헤더나 로그에서 colo(데이터센터) 단서가 나옵니다. 문제는 “IAD에 붙은 사용자만 실패한다” 같은 형태가 흔해서, 전체 평균 오류율만 보면 늦습니다.

내가 보통 쓰는 방식은 이렇습니다.

- 사용자 오류 이벤트에 colo 힌트를 붙인다(가능한 범위에서)
- colo/리전별 error rate가 임계치를 넘으면 “부분 장애”로 승격
- 승격되면 자동 완화(아래 섹션들)

Cloudflare 쪽 로그/관측 기능 자체도 시간이 지나며 계속 변합니다. 예를 들어 Log Explorer는 R2에 저장되는 로그를 SQL로 조회하는 모델을 명시하고 있습니다. [Log Search](https://developers.cloudflare.com/log-explorer/log-search/)[^10]

## 완화 설계 1: 리전 라우팅(오리진 관점) — IAD 경로가 나빠져도 살아남기

IAD 성능 저하가 ‘전 서비스 에러’로 보이는 가장 흔한 이유는, 오리진이 us-east-1 단일 리전이거나, 동부 리전에 과도하게 몰려 있기 때문입니다.

이때 완화는 “Cloudflare를 어떻게 고칠까”가 아니라 “Cloudflare에서 us-east로 가는 경로가 나빠져도 서비스가 유지되나”로 접근해야 합니다.

### 오리진 다중 리전의 최소 조건

- 읽기 트래픽은 active-active가 가능해야 함
- 쓰기는 단일 리전 고정이더라도, 읽기 fallback은 가능해야 함
- 정적/준정적 응답은 캐시 가능한 형태로 설계해야 함

이 얘기는 단순하지만, 실제로는 데이터 모델/일관성/캐시 무효화가 발목을 잡습니다. 그래서 나는 API를 아래처럼 분해합니다.

- 강일관성 쓰기 API(결제, 주문): 리전 고정 + 강한 idempotency
- 읽기 API: 다중 리전 + CDN 캐시 + stale 전략
- 비동기 처리: 큐 기반 + 지연 허용

Cloudflare 장애 대응을 다루면서도 결국 “의존성 분해”로 귀결되는 이유가 여기 있습니다. 예전에 썼던 [Cloudflare R2 503 장애 대응: 객체 스토리지 의존성 분해](https://daewooki.github.io/posts/r2-503-outage-app-resilience-patterns/)도 같은 결론으로 끝났습니다.

### Cloudflare Load Balancing을 ‘오리진 페일오버’에만 쓰는 방식

Cloudflare LB 문서는 active-passive failover 구성을 설명하고, 모니터의 timeout/retries가 failover 시간을 어떻게 결정하는지 구체적으로 적습니다. [Common configurations](https://developers.cloudflare.com/load-balancing/load-balancers/common-configurations/), [Manage monitors](https://developers.cloudflare.com/load-balancing/monitors/create-monitor/)[^11]

다만 이번 케이스처럼 “Cloudflare 자체가 흔들릴 수 있는 사건”에서 Cloudflare LB가 만능이라고 보긴 어렵습니다. 그래도 오리진 다중화가 아직 없는 팀이라면, 현실적으로 가장 빨리 ‘리전 failover’를 구현할 수 있는 수단이 되기도 합니다.

내 결론은 보통 이렇습니다.

- Cloudflare LB는 **오리진 장애**에는 유효
- Cloudflare POP/네트워크 장애에는 **multi-CDN이나 클라이언트 측 완화가 별도로** 필요

## 완화 설계 2: multi-CDN — “구성은 쉬운데, 운영이 어렵다”를 전제로 설계하기

multi-CDN은 대개 “장애 시 Cloudflare에서 Fastly/CloudFront로 넘기면 되지 않나?”로 시작합니다. 실제로는 이 두 가지가 가장 어렵습니다.

- 전환 기준(health definition)
- 구성 동기화(parity)

그래서 나는 multi-CDN을 ‘기능’이 아니라 ‘제품’처럼 취급합니다. 런북과 훈련이 없으면 성공률이 급격히 떨어집니다.

### DNS failover가 가장 현실적인 1차 레이어

권장 아키텍처는 단순합니다.

- DNS 트래픽 매니저(예: Route 53)
- primary CDN / secondary CDN
- 두 CDN을 통해 같은 헬스체크 오브젝트를 받아서 판단

Route 53은 health check와 failover 라우팅에서 “레코드를 고르고, unhealthy면 다른 레코드를 고른다”는 동작을 문서로 설명합니다. [How health checks work in simple Amazon Route 53 configurations](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-simple-configs.html)[^12]

여기에 회의론이 하나 있습니다.

- DNS TTL/캐시 때문에 failover가 느릴 수 있다

이건 맞는 지적이고, 그래서 실전에서는 아래를 같이 씁니다.

- TTL을 아주 낮추는 대신, **전환 횟수/조건을 보수적으로** 잡아 flapping을 막는다
- 전환이 필요한 사건은 “수 초”가 아니라 “수 분” 이상 지속되는 유형을 대상으로 한다
- 수 초 단위가 목표라면 DNS만으로는 어렵고 L7 프록시/클라이언트 전략이 들어간다

### Terraform 예시: Route 53 failover 레코드(실행 가능한 뼈대)

아래는 `api.example.com`을 primary/secondary로 failover하는 구성의 뼈대입니다. 실제로는 primary/secondary가 각각 CDN 도메인(CNAME) 또는 ALB/CloudFront(ALIAS)일 수 있는데, 여기서는 이해를 위해 A 레코드(IP)로 적습니다.

```hcl
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1" # Route 53 health check은 글로벌이지만 API 호출 리전은 필요
}

variable "zone_id" { type = string }
variable "primary_ip" { type = string }
variable "secondary_ip" { type = string }

resource "aws_route53_health_check" "primary" {
  type              = "HTTPS"
  fqdn              = "api.example.com"
  port              = 443
  resource_path     = "/health"
  request_interval  = 30
  failure_threshold = 3
}

resource "aws_route53_record" "primary" {
  zone_id = var.zone_id
  name    = "api"
  type    = "A"
  ttl     = 30

  records = [var.primary_ip]

  set_identifier = "primary"
  failover_routing_policy {
    type = "PRIMARY"
  }

  health_check_id = aws_route53_health_check.primary.id
}

resource "aws_route53_record" "secondary" {
  zone_id = var.zone_id
  name    = "api"
  type    = "A"
  ttl     = 30

  records = [var.secondary_ip]

  set_identifier = "secondary"
  failover_routing_policy {
    type = "SECONDARY"
  }
}
```

문서 그대로의 “DNS failover”를 코드로 고정하는 수준이지만, 이걸 실제 multi-CDN에 적용하면 건강한 서비스가 됩니다.

- 헬스체크는 CDN을 경유해서 실제 오브젝트를 확인
- primary/secondary는 각각 다른 CDN
- 구성 parity는 IaC로 강제

multi-CDN 아키텍처의 레이어(DNS/L7/클라이언트)를 비교하는 자료도 같이 읽을 만합니다. [Architecture Patterns for Multi-CDN](https://www.cdnhandbook.com/multicdn/architecture-patterns/)[^13]

## 완화 설계 3: 캐시/오리진 — 엣지 성능 저하 때 ‘살아남는 응답’을 늘리기

IAD 성능 이슈가 터졌을 때 모든 요청을 살릴 수는 없습니다. 대신 “살릴 수 있는 요청”의 비율을 늘리면, 사용자 입장에서 전면 장애가 부분 장애로 내려옵니다.

여기서 핵심은 두 가지입니다.

- 오리진으로 가는 요청 수 자체를 줄인다(캐시 적중률↑, 연결 수↓)
- 오리진/경로가 실패해도 stale을 줄 수 있게 한다

### stale-while-revalidate / stale-if-error를 ‘계약’으로 쓰기

HTTP 캐시 확장은 RFC 5861에 표준으로 정의되어 있습니다. [RFC 5861](https://www.rfc-editor.org/info/rfc5861/)[^14]

Cloudflare는 캐시 무효화 가이드에서 “origin이 5xx를 반환하거나 도달 불가면 stale을 제공할 수 있고, `stale-if-error`로 제한할 수 있다”는 동작을 문서로 적어 두었습니다. [Invalidate cached content](https://developers.cloudflare.com/cache/guides/invalidate-cache/)[^15]

여기서 운영적으로 중요한 결론은 이겁니다.

- 장애 시 사용자에게 완전히 빈 화면을 보여줄지
- 1~5분 전 stale라도 보여줄지

이 선택은 제품/정책이지만, 기술적으로는 API 설계에서 결정됩니다. 나는 가능하면 다음을 지킵니다.

- 읽기 API 응답은 `Cache-Control`로 캐시 가능하게 만들고
- 페이지/피드류는 짧은 TTL + `stale-while-revalidate`
- “최신성이 중요하지만 완전 실패보다 낫다”면 `stale-if-error`를 준다

정적 자산은 말할 것도 없고, HTML이나 JSON도 조건만 맞으면 캐시로 서비스 복원력을 크게 올릴 수 있습니다.

### Tiered Cache/오리진 보호는 ‘원인’이 아니라 ‘피해 감소’지만 효과가 크다

이번 사건은 Cloudflare 내부 성능 이슈였지만, 내 서비스 입장에서 결국 문제는 “오리진으로 가는 트래픽”과 “오리진 연결 수”로 증폭됩니다.

Cloudflare는 Smart Shield/Smart Tiered Cache가 upper tier/lower tier 구조로 오리진 요청을 줄인다고 설명합니다. [Cloudflare Smart Shield](https://developers.cloudflare.com/smart-shield/)[^16]

또한 Tiered Cache 문서에서 “lower tier가 miss면 upper tier를 먼저 보고, upper tier만 origin에 간다”는 구조를 명시합니다. [Tiered Cache](https://developers.cloudflare.com/cache/how-to/tiered-cache/)[^17]

이 계열 기능은 POP 성능 저하의 ‘원인’을 제거하진 못해도, 오리진이 2차로 죽어버리는 상황을 줄이는 데는 도움이 됩니다. 즉, incident가 들어왔을 때 내가 할 수 있는 일은 “공급자 네트워크를 고치는 것”이 아니라 “우리 오리진이 같이 죽지 않게 하는 것”입니다.

## 회의론과 반론: multi-CDN/리전 분산이 항상 답인가

### “Cloudflare 장애는 드물다. 과투자다”

단일 공급자에 대한 신뢰는 합리적입니다. 다만 이 유형의 장애는 “드물지만, 발생하면 전면적”입니다. 사용자 기대치가 높은 서비스일수록, 평균 가동률보다 ‘최악의 30분’이 더 큰 비용을 만듭니다.

내 경험상, multi-CDN이 부담스러운 팀이라도 아래는 과투자가 아닙니다.

- timeout/retry budget 정리(클라이언트/프록시)
- stale 전략으로 읽기 트래픽 보호
- synthetic를 실제 플로우로 강화

### “DNS failover는 느리다. 의미 없다”

느립니다. 그런데 느린 것과 무의미한 것은 다릅니다.

- 30초~수 분 내 전환이 의미 있는 장애(수십 분 지속)가 꽤 많습니다.
- DNS failover는 단독이 아니라 ‘최후의 안전장치’로 쓰면 효과가 큽니다.

### “Cloudflare를 쓰면 권한/구성상 다른 CDN으로 즉시 전환이 어렵다”

이건 사실입니다. Cloudflare를 authoritative DNS + 프록시로 깊게 묶어 쓰는 경우, “외부 DNS 트래픽 매니저로 전환”이 구조적으로 어렵거나, Cloudflare for SaaS 같은 별도 설계가 필요해질 수 있습니다.

그래서 나는 multi-CDN을 당장 못 하는 조직에 이렇게 접근합니다.

- 1단계: 앱 레이어(타임아웃/재시도/캐시)로 ‘확대’를 막는다
- 2단계: 오리진 다중 리전으로 ‘경로 리스크’를 줄인다
- 3단계: 가능한 범위에서만 multi-CDN(정적 자산부터)로 늘린다

## 앞으로 지켜볼 것: ‘IAD 성능 이슈 → 오류 증가’가 반복될 때의 신호들

이번 Major incident 페이지는 업데이트가 1개뿐이라, 외부에서 root cause를 단정할 수는 없습니다.[^1]

그럼에도 운영자가 다음을 체크하면 재발 시 대응이 빨라집니다.

- status page에서 “network performance”가 특정 colo(IAD 등)로 열릴 때, 우리 synthetic에서 같은 시간대에 p95/p99 TTFB가 튀는지
- 우리 오류가 5xx인지, timeout(클라이언트/프록시)인지, TLS인지 분류가 되는지
- retry storm 징후(동일 요청의 재시도 증가, QPS 상승, connection churn)가 있는지
- 캐시 적중률 변화(HIT↘, MISS↗)와 오리진 부하의 상관관계

그리고 incident를 수동 확인하는 게 아니라, status API/notification을 시스템 입력으로 넣어야 합니다.

- polling이면 [Cloudflare Status API](https://www.cloudflarestatus.com/api)[^7]
- push면 [Status Page Notifications](https://www.cloudflarestatus.com/docs/notifications)[^8]

## 지금 할 수 있는 일: ‘재현·탐지·완화’ 체크리스트를 코드로 남기기

이 글을 한 문장으로 요약하면 이렇습니다.

- POP/리전의 성능 저하는 생각보다 쉽게 전 서비스 오류처럼 보이고,
- 그때 승패는 공급자 status page가 아니라 **우리 설계(타임아웃/재시도/라우팅/캐시/오리진)**에서 갈립니다.

내가 권하는(그리고 실제로 효과가 있었던) 실행 순서는 아래입니다.

1) proxy/SDK의 timeout budget을 표준화한다(서비스별 제멋대로면 장애 때 무조건 진다)
2) retry는 줄이기보다 “budget으로 제한”한다(Envoy면 retry_budget 같은 기능을 활용)[^5]
3) synthetic는 `/health`가 아니라 핵심 플로우 + checksum으로 바꾼다[^9]
4) 읽기 API는 stale-if-error/stale-while-revalidate를 설계에 포함시킨다[^14]
5) 가능하면 오리진을 다중 리전으로 만들고, 그 다음에 multi-CDN을 논의한다

이번 Cloudflare incident는 28분짜리 사건으로 기록되지만, 같은 형태의 장애는 내 서비스에서 ‘28분 이상의 손실’로 확대되기 쉽습니다. 결국 중요한 건 status page가 아니라, 성능 저하를 장애로 키우지 않는 제어면을 얼마나 많이 갖고 있느냐로 끝납니다.

## 참고 자료

- [Cloudflare Service Issues (incident z7vongh8rqc1)](https://www.cloudflarestatus.com/incidents/z7vongh8rqc1)
- [Cloudflare Status Incident History](https://www.cloudflarestatus.com/history)
- [Cloudflare Status API](https://www.cloudflarestatus.com/api)
- [Status Page Notifications (Cloudflare Status)](https://www.cloudflarestatus.com/docs/notifications)
- [Network performance issues in Ashburn, US (IAD) (incident gqm2xrm9wk8t)](https://www.cloudflarestatus.com/incidents/gqm2xrm9wk8t)
- [Error 522: connection timed out](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-522/)
- [Invalidate cached content (stale behavior 포함)](https://developers.cloudflare.com/cache/guides/invalidate-cache/)
- [RFC 5861: HTTP Cache-Control Extensions for Stale Content](https://www.rfc-editor.org/info/rfc5861/)
- [Cloudflare Smart Shield 개요](https://developers.cloudflare.com/smart-shield/)
- [Tiered Cache](https://developers.cloudflare.com/cache/how-to/tiered-cache/)
- [Cloudflare Load Balancing common configurations](https://developers.cloudflare.com/load-balancing/load-balancers/common-configurations/)
- [Cloudflare Load Balancing monitors (timeout/retries)](https://developers.cloudflare.com/load-balancing/monitors/create-monitor/)
- [How health checks work in simple Amazon Route 53 configurations](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-simple-configs.html)
- [Envoy circuit breakers proto (retry budget 포함)](https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto.html)
- [Envoy FAQ: handling transient failures](https://www.envoyproxy.io/docs/envoy/v1.32.0/faq/load_balancing/transient_failures)
- [Cloudflare incident on June 20, 2024 (네트워크/오류 계열 참고 사례)](https://blog.cloudflare.com/cloudflare-incident-on-june-20-2024/)
- [Multi-CDN failover: a working setup, step by step](https://www.cdnworld.com/guide/multi-cdn-failover-setup)
- [Architecture Patterns for Multi-CDN](https://www.cdnhandbook.com/multicdn/architecture-patterns/)

[^1]: <https://www.cloudflarestatus.com/incidents/z7vongh8rqc1>
[^2]: <https://www.cloudflarestatus.com/api/v2/incidents.json>
[^3]: <https://blog.cloudflare.com/cloudflare-incident-on-june-20-2024/>
[^4]: <https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-522/>
[^5]: <https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto.html?highlight=cluster>
[^6]: <https://www.envoyproxy.io/docs/envoy/v1.32.0/faq/load_balancing/transient_failures>
[^7]: <https://www.cloudflarestatus.com/api>
[^8]: <https://www.cloudflarestatus.com/docs/notifications>
[^9]: <https://www.cdnworld.com/guide/multi-cdn-failover-setup>
[^10]: <https://developers.cloudflare.com/log-explorer/log-search/>
[^11]: <https://developers.cloudflare.com/load-balancing/load-balancers/common-configurations/>
[^12]: <https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-simple-configs.html>
[^13]: <https://www.cdnhandbook.com/multicdn/architecture-patterns/>
[^14]: <https://www.rfc-editor.org/info/rfc5861/>
[^15]: <https://developers.cloudflare.com/cache/guides/invalidate-cache/>
[^16]: <https://developers.cloudflare.com/smart-shield/>
[^17]: <https://developers.cloudflare.com/cache/how-to/tiered-cache/?ref=devstoc.com>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
