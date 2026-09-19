---
title: "Cloudflare Ashburn(IAD) 구간 5xx 급증이 SLO를 깨는 방식"
description: "PoP 단위 5xx는 글로벌 지표에 묻히지만 특정 네트워크에선 체감이 폭발합니다. 라우팅·멀티-CDN·지역 SLO 설계로 다룹니다."
date: 2026-09-19 10:14:25 +0900
categories: ["News", "Networking"]
tags: ["cloudflare", "pop-outage", "multi-cdn", "slo", "error-budget", "traffic-steering"]
render_with_liquid: false
---

## 사건 타임라인: 2026-09-18 Ashburn(IAD) 경유 5xx 증가

Cloudflare Status의 incident 페이지에는 다음이 명시돼 있습니다. 2026-09-18 17:13~17:28 UTC 동안 Ashburn(IAD)을 경유하는 트래픽에서 5xx HTTP error 비율이 증가했고, 이후 해결됐으며 IAD 영향이 완화됐다는 내용입니다. [Cloudflare Status incident](https://cloudflare.statuspage.io/incidents/3czg2lc9y1t8)

KST(UTC+9)로 바꾸면 2026-09-19 02:13~02:28 KST입니다. 사용자가 한국이든, 한국 사용자 비중이 크든, 장애 자체가 짧게 보이기 때문에 사후 분석과 설계 변경을 밀어두기 쉽습니다. 그런데 이 유형은 “짧고 국소적”이라는 이유로 오히려 구조를 계속 방치하게 만들고, 다음 번에는 더 크게 맞게 됩니다.

이번 건이 흥미로운 이유는 ‘Cloudflare 전체가 다운’ 같은 글로벌 이벤트가 아니라, **특정 PoP(Ashburn, IAD) 경유 트래픽**에서만 5xx가 올라간 사건이라는 점입니다. 이런 사건은 모니터링/알림/라우팅이 대부분 글로벌 평균을 전제로 설계돼 있을 때 SLO를 깨는 전형적인 경로를 보여줍니다.

비슷한 표현의 IAD 5xx 증가 incident가 2026-09-15(20:55~21:52 UTC)에도 올라와 있습니다. 즉, “한 번 특이하게 발생한 사고”로만 보기 어렵습니다. [Cloudflare Status(동일 문구의 IAD incident)](https://cloudflare.statuspage.io/)

여기서부터는 Cloudflare 내부 원인(RCA)이 공개되지 않았다는 전제에서, 관측 가능한 사실과 네트워크/엣지 아키텍처의 일반적인 동작 원리를 기반으로 “왜 이런 것이 SLO를 깨는지”, “어떻게 설계를 바꿔야 하는지”를 정리합니다.

## ‘특정 PoP 장애’가 사용자 체감을 국소적으로 폭발시키는 이유

Cloudflare는 Anycast 기반 네트워크로 알려져 있고, proxied 레코드는 Cloudflare의 Anycast IP 대역으로 들어가며 방문자 요청은 가까운 데이터센터로 라우팅된다는 설명을 공식 문서에서도 반복합니다. [Cloudflare IP addresses 개념 문서](https://developers.cloudflare.com/fundamentals/concepts/cloudflare-ip-addresses/), [Traffic flow through Cloudflare](https://developers.cloudflare.com/fundamentals/concepts/traffic-flow-cloudflare/), [Anycast 설명(Cloudflare Learning Center)](https://www.cloudflare.com/learning/cdn/glossary/anycast-network/)

여기서 흔히 생기는 오해가 하나 있습니다.

- “Anycast면 가까운 곳으로 가니까, 특정 PoP가 아프면 자동으로 다른 PoP로 갈 것”

현실은 더 거칩니다. Anycast의 ‘가까움’은 지리적 거리보다 BGP 경로 선택(정책/피어링/비용/AS-path 등)에 의해 결정됩니다. 같은 도시의 사용자라도 ISP가 다르면 전혀 다른 PoP로 들어가고, 반대로 다른 주/다른 나라의 사용자도 특정 PoP에 붙을 수 있습니다. 연구/측정 관점에서도 Anycast 경로는 “안정적인 편이지만(자주 바뀌지 않지만) 라우팅에 의존하므로 catchment가 사람이 직관적으로 상상하는 지리 경계와 다를 수 있다”는 점이 반복해서 관찰됩니다. [A First Look at Anycast CDN Traffic (arXiv)](https://arxiv.org/abs/1505.00946)

이게 부분 장애에서 사용자 체감이 폭발하는 첫 번째 이유입니다.

- 특정 ASN/특정 ISP/특정 리졸버를 타는 사용자 묶음이 IAD로 “고정”되어 있고,
- 그 집단은 장애 기간 동안 5xx를 집중적으로 맞으며,
- 다른 집단은 아무 일도 없었던 것처럼 보입니다.

같은 오류율이라도 “분산된 0.2%”와 “어느 네트워크에서는 30%, 나머지는 0%”는 고객지원/매출/브랜드 타격이 완전히 다릅니다. 평균은 비슷해 보이는데 국소 버스트가 생기면, 체감은 평균이 아니라 최악값으로 결정됩니다.

두 번째 이유는 “PoP 단위 장애”가 실제로는 “PoP 자체의 다운”이 아니라 “그 PoP를 경유하는 경로/장비/피어링/내부 패브릭의 일부 구간” 문제로 나타나는 경우가 많기 때문입니다. Cloudflare도 네트워크/서비스 resilience 문서에서 PoP를 개별적으로 격리하고, 필요하면 트래픽을 다른 데이터센터로 이동시키며, 이를 위해 Traffic Manager가 지속적으로 probing하여 CPU overload 등의 조건에서 트래픽을 이동시킨다고 설명합니다. [Cloudflare network and services resilience (PDF)](https://cf-assets.www.cloudflare.com/slt3lc6tev37/7ad0dpR3YyqxMlikPfbBgn/020b7450909f03ccf3c7dcfb0e99fc2e/Resilience_Whitepaper.pdf), [Meet Traffic Manager (Cloudflare Blog)](https://blog.cloudflare.com/meet-traffic-manager/)

즉, “전체 다운”처럼 단순히 100% 실패로 떨어지지 않고, 애매한 degraded 상태(일부 요청만 5xx, 특정 경로만 5xx, 특정 프로토콜만 5xx)로 나타나기 쉽습니다. 이 애매함이 헬스체크/알림/자동 우회 로직을 계속 속입니다.

세 번째 이유는 연결 재사용과 프로토콜 특성입니다.

- HTTP/2, HTTP/3(QUIC) 환경에서는 하나의 연결 위로 많은 요청이 multiplexing 됩니다.
- 어떤 사용자는 “좋은 경로/좋은 엣지”에 붙어 있고 어떤 사용자는 “나쁜 경로/나쁜 엣지”에 붙어 있으면, 후자는 짧은 시간에도 연속 실패를 맞기 쉽습니다.

결과적으로, PoP 단위 partial failure는 “전체적으로는 미미한 에러율 상승”처럼 보이면서, 특정 사용자 집단에서는 로그인/결제/업로드 같은 핵심 흐름이 통째로 무너지는 형태로 터집니다.

## 글로벌 SLI가 부분 장애를 숨기는 방식

대부분의 서비스 SLO는 아래 형태로 시작합니다.

- 전 구간 성공률 SLO: `good / total >= 99.9%` (30일)

이 자체는 나쁘지 않습니다. 문제는 관측/집계가 대부분 글로벌 합산을 기본값으로 둔다는 점입니다.

예를 들어 트래픽을 단순화해서 다음처럼 가정해 보겠습니다.

- 전세계 10개 리전(또는 대륙)에서 트래픽이 고르게 발생
- 특정 PoP(IAD)에 붙는 집단이 전체 트래픽의 2%를 차지
- 그 2%에서 15분 동안 50%가 5xx
- 나머지 98%는 정상

글로벌 합산에서의 오류율은 `0.02 * 0.5 = 1%`가 아니라, “15분이라는 시간 요소”까지 포함되면 더 낮게 보입니다(월 단위 SLO면 더 작아집니다). 그런데 IAD에 붙는 집단에게는 15분 동안 사실상 절반이 실패입니다. 이 상황에서 글로벌 합산만 보면

- 대시보드에서는 작은 스파이크
- 알림은 안 울림(혹은 ticket만 생성)
- CS는 폭주

가 됩니다.

이 지점은 예전에 GPU autoscaling을 다뤘던 글에서 “GPU% 같은 글로벌 평균 지표가 SLO를 대변하지 못한다”는 문제와 본질적으로 같습니다. 병목/실패는 평균이 아니라 ‘국소적인 포화/큐/실패’에서 생깁니다. [GPU 오토스케일링 글](https://daewooki.github.io/posts/gpu-2026-5-gpu-kv-cachequeueslo-1/)

네트워크/엣지에서는 그 ‘국소성’이 AS/PoP/리졸버/모바일 캐리어 단위로 나타난다는 점만 다릅니다.

따라서 PoP 단위 partial outage를 다룰 때는 SLO를 “하나”로 끝내면 거의 항상 진다는 결론이 나옵니다.

## (1) 라우팅/헬스체크: PoP 단위 장애를 감지하고 우회하는 신호 설계

여기서 말하는 라우팅은 두 층위가 있습니다.

1) CDN 내부(Cloudflare의 Anycast/Traffic Manager)가 어떻게 알아서 피해주길 기대하는 층위
2) 내 서비스가 Cloudflare를 “하나의 공급자”로 보고, 필요 시 다른 공급자/다른 경로로 보내는 층위

2)로 갈수록 내 통제력이 커지지만 비용/복잡도가 빠르게 증가합니다.

### 헬스체크가 실패하는 전형적인 패턴

부분 장애에서 헬스체크가 실패하는 이유는 대부분 다음 중 하나입니다.

- 헬스체크가 너무 단순하다(ICMP ping, TCP connect)
- 헬스체크가 “내 유저가 타는 경로”를 대표하지 못한다(프로브 위치/ASN 편향)
- 헬스체크가 너무 느리다(간격/timeout/판정 로직)
- 판정이 글로벌 합산이다(국소 실패를 평균으로 희석)

특히 Anycast 기반 서비스는 “내가 서울에서 찍으면 정상인데, 버지니아/특정 ISP에서는 죽는다” 같은 상황이 매우 흔합니다. Anycast는 라우팅으로 ‘가까운’ 곳으로 가지만, 그 가까움은 사용자/ISP마다 다르게 구현됩니다. [Anycast 설명(Cloudflare)](https://www.cloudflare.com/learning/cdn/glossary/anycast-network/)

### ‘사용자 경로’를 반영하는 synthetic check

내가 선호하는 기준은 이렇습니다.

- 헬스체크는 반드시 HTTPS fetch여야 합니다.
- 대상은 “실제 서비스의 대표 URL(정적 파일 1개가 아니라 인증/캐시/WAF/오리진까지 엮인 경로)”여야 합니다.
- 응답 본문에 최소한의 checksum 또는 marker를 넣어, 200이지만 잘못된 페이지(차단 페이지, 오류 캐시, 다른 CDN의 fallback)를 잡아냅니다.

multi-CDN 가이드 쪽에서도 “단일 노드 ping은 health가 아니다”, “실제 object를 HTTPS로 가져오고 status code와 content checksum을 검증하라”는 식의 조언이 반복됩니다. [Multi-CDN failover 가이드](https://www.cdnworld.com/guide/multi-cdn-failover-setup)

### ‘여러 관측점’과 ‘다수결’이 필수

PoP/리전 부분 장애는 관측점이 한두 곳이면 재현이 안 됩니다. 나는 최소 아래를 기본값으로 둡니다.

- 관측점: 북미 동부/서부, 유럽, 아시아 등 4~6개
- 가능하면 ASN이 다른 관측점(같은 클라우드 리전의 VM 여러 대는 생각보다 동질적)
- 판정: 단일 관측점 실패로 전체 failover를 트리거하지 말고, N개 중 M개 실패(또는 실패율/지연의 동시 조건)

이 설계는 “한 관측망의 라우팅 이슈/패킷로스” 때문에 정상 CDN을 불필요하게 배제하는 것을 막습니다.

### Cloudflare Load Balancing 문서에서 가져올 수 있는 힌트

Cloudflare Load Balancing은 원래 “Cloudflare → origin” 쪽의 라우팅(풀/엔드포인트) 문제를 다루는 기능이지만, 부분 장애에서 우리가 원하는 ‘판정/우회’의 개념을 문서에서 꽤 구체적으로 볼 수 있습니다.

- Traffic steering은 “pool/endpoint health”를 1순위로 놓고, 그 다음 pool set, global steering, local steering 순서로 결정을 내린다고 설명합니다. [Traffic steering 문서](https://developers.cloudflare.com/load-balancing/understand-basics/traffic-steering/)
- health monitor region을 여러 개 선택하면, 각 region에서 여러 데이터센터가 probe를 보낸다는 식으로 “다지역 관측”을 기본 설계로 둡니다. [How endpoints and pools become unhealthy](https://developers.cloudflare.com/load-balancing/understand-basics/health-details/)
- health check interval 사이의 상태 변화(짧은 partial failure)를 다루기 위한 adaptive routing이 있고, 특정 error code에서만 재시도/zero-downtime failover를 트리거한다는 제한도 명시돼 있습니다. [Adaptive routing 문서](https://developers.cloudflare.com/load-balancing/understand-basics/adaptive-routing/)

특히 adaptive routing의 “어떤 오류 코드에서만 retry/failover를 한다”는 제한은, 부분 장애에서 자동 우회가 왜 기대만큼 동작하지 않는지 설명하는 좋은 예시입니다. 장애가 5xx로 보이더라도 코드 종류/발생 위치에 따라 자동 우회가 걸리지 않을 수 있습니다.

## Cloudflare Status를 파이프라인에 넣기: incident를 ‘사후 보고’가 아니라 ‘신호’로 쓰기

Status page는 사람 읽기용 페이지로 끝내면 가치가 떨어집니다. Cloudflare는 상태 정보를 API로 제공하고, 자동화된 접근은 HTML 스크래핑이 아니라 API를 사용하라고 명확히 적어 두고 있습니다. [Cloudflare Status API 문서](https://www.cloudflarestatus.com/api)

또한 Status page 자체가 Cloudflare 인프라와 독립적으로 알림을 전달하도록 설계돼 있어, Cloudflare 자체가 흔들려도 알림이 간다는 설명도 있습니다. [Cloudflare Status 지원 문서](https://developers.cloudflare.com/support/cloudflare-status/)

이걸 어떻게 쓰느냐가 관건인데, 나는 두 가지로 씁니다.

- incident 발생 시점(또는 resolved 시점)을 내 장애 타임라인에 자동으로 끼워 넣는다(사후 분석 속도)
- “우리 서비스의 지역 SLI 이상”과 “공급자 incident”를 자동으로 상호참조한다(원인 분류)

아래는 Cloudflare Status API의 `incidents.json`을 주기적으로 가져와서, 최근 N일 내 incident 중 IAD/Ashburn 관련 항목을 뽑는 스크립트 예시입니다. 이 정도는 실제 운영에 바로 붙일 수 있는 수준이어야 합니다.

```bash
# tested with Python 3.11+
python -m venv .venv
source .venv/bin/activate
pip install requests

python fetch_cloudflare_incidents.py --days 14 --match "Ashburn|IAD"
```

```python
# fetch_cloudflare_incidents.py
import argparse
import datetime as dt
import re
import sys

import requests

API = "https://www.cloudflarestatus.com/api/v2/incidents.json"

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--match", type=str, default="")
    return p.parse_args()

def iso(ts: str) -> dt.datetime:
    # e.g. 2026-09-18T17:15:00.000Z
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))

def main():
    args = parse_args()
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)

    headers = {
        "User-Agent": "daewooki-status-monitor/1.0 (+https://daewooki.github.io/)"
    }

    r = requests.get(API, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()

    incidents = data.get("incidents", [])

    pattern = re.compile(args.match) if args.match else None

    out = []
    for inc in incidents:
        created = iso(inc["created_at"])
        if created < since:
            continue
        name = inc.get("name", "")
        if pattern and not pattern.search(name):
            continue
        out.append(inc)

    out.sort(key=lambda x: x["created_at"])

    for inc in out:
        name = inc.get("name")
        status = inc.get("status")
        created = iso(inc["created_at"]).isoformat()
        updated = iso(inc["updated_at"]).isoformat()
        impact = inc.get("impact")

        latest = ""
        if inc.get("incident_updates"):
            latest = inc["incident_updates"][0].get("body", "").strip().replace("\n", " ")

        print("-")
        print(f"name   : {name}")
        print(f"status : {status} (impact={impact})")
        print(f"created: {created}")
        print(f"updated: {updated}")
        if latest:
            print(f"latest : {latest}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
```

예상 출력은 아래 형태입니다(incident 본문은 Cloudflare가 쓰는 원문이 그대로 들어옵니다).

```text
-
name   : Network Performance Issues in Ashburn
status : resolved (impact=minor)
created: 2026-09-18T17:15:00+00:00
updated: 2026-09-18T17:15:00+00:00
latest : Between 17:13-17:28UTC on 2026-09-18, Cloudflare experienced an elevated rate of 5xx HTTP errors affecting traffic passing through Ashburn (IAD). The issue has been resolved, and impact to the IAD location is mitigated.
```

이 스크립트 자체는 간단하지만, 운영적으로는 다음이 중요합니다.

- “공급자 incident가 떴다”가 아니라, “우리 SLI에서 특정 지역/ASN이 나빠졌다”가 먼저여야 합니다.
- 그 다음에 공급자 incident를 붙여 “원인 후보를 축소”하는 용도로 써야 합니다.

Status page는 공지이자 증거지만, 내 사용자 체감의 선행지표는 아닙니다. 특히 부분 장애는 status 업데이트가 늦거나, 영향 범위가 제한적이라 표현이 뭉뚱그려질 수 있습니다.

## (2) 멀티-CDN: 부분 장애에서 ‘국소 폭발’을 완충하는 방법

멀티-CDN은 “Cloudflare가 죽으면 Fastly로 간다”처럼 단순한 문장이지만, 실제로는 ‘steering’이 설계의 대부분입니다. 멀티-CDN 설계에서 반복되는 핵심은 아래 한 줄입니다.

- steering control plane은 두 CDN 중 어느 쪽에도 종속되면 안 됩니다.

이건 멀티-CDN failover 가이드에서도 노골적으로 강조합니다. steering이 장애 난 공급자 위에 있으면 같이 죽습니다. [Multi-CDN failover 가이드](https://www.cdnworld.com/guide/multi-cdn-failover-setup)

### DNS steering이 기본이지만, DNS의 한계는 그대로 따라옵니다

DNS 기반 steering은 구현/운영 난이도 대비 효과가 좋아서 기본값이 됩니다. 동시에 DNS의 단점도 그대로 가져옵니다.

- TTL과 resolver cache 때문에 failover가 “초 단위”가 아니라 “초~분 단위”가 됩니다.
- 사용자 위치가 resolver 위치로 근사되는 문제(EDNS Client Subnet이 있더라도 완벽하지 않음)

DNS steering vs client-side switching 비교에서도, DNS의 캐시/지연과 resolver 위치 문제는 핵심 약점으로 반복됩니다. [DNS steering versus client-side switching](https://www.cdnworld.com/article/dns-steering-vs-client-switching)

그럼에도 PoP 단위 부분 장애에는 DNS steering이 강한 편입니다. 이유는 간단합니다.

- 부분 장애는 “특정 ASN/특정 지역에서만” 터지고,
- DNS 정책(geo/ASN 기반)으로 그 구간을 잘라서 다른 CDN으로 보낼 수 있기 때문입니다.

여기서 중요한 건 “글로벌 failover”가 아니라 “국소 steering”입니다. IAD 문제가 있을 때 전세계 트래픽을 다 바꾸면 오히려 2차 사고가 납니다. IAD catchment만 빼내는 게 목표입니다.

### RUM 기반 steering이 부분 장애에 더 강한 이유

부분 장애의 본질은 “내 유저가 실제로 타는 경로”가 망가지는 것입니다. 그래서 synthetic probe만으로는 놓치기 쉽고, RUM을 steering 입력으로 쓰는 접근이 강해집니다. RUM steering 가이드는 “RUM이 가장 정직한 신호”라는 관점을 밀고 갑니다. [RUM data 기반 steering 가이드](https://www.cdnworld.com/guide/steer-on-rum-data)

내 경험상 RUM steering은 확실히 강력하지만, 바로 도입하기 어려운 이유도 분명합니다.

- 개인정보/규제/보안(특히 네트워크/금융/헬스케어)
- 샘플링과 편향(트래픽이 적은 지역은 데이터가 얇음)
- steering 로직이 잘못되면 사용자 경험을 더 흔듦(플랩)

그래서 현실적인 경로는 보통 이렇습니다.

1) synthetic를 다지역/다ASN으로 늘려 “부분 장애 감지”를 먼저 안정화
2) RUM을 관측용으로 붙여 “어느 ASN/어느 리졸버에서 터지는지”를 파악
3) 충분히 패턴이 누적되면, 일부 트래픽 클래스부터 RUM-driven steering을 제한적으로 적용

### 멀티-CDN의 가장 비싼 부분은 ‘기능’이 아니라 ‘동등성’

부분 장애에서 멀티-CDN이 실제로 작동하려면 아래가 동등해야 합니다.

- TLS 인증서/키 배포(동일 hostname)
- WAF/봇/레이트리밋 정책
- 캐시 키/헤더/압축/이미지 최적화 같은 edge 변환
- 로그/모니터링 스키마(사고 때 비교가 가능해야 함)

이런 항목은 멀티-CDN 가이드들에서도 “두 번째 CDN을 사는 게 쉬운 일이고, 실제로 쓸 수 있게 만드는 게 어려운 일”이라고 요약됩니다. [Multi-CDN Traffic Steering & Failover 가이드](https://www.continuuly.io/blog/multi-cdn-traffic-steering-failover-guide)

여기까지 맞춰야 “IAD 부분 장애에서만 국소적으로 다른 CDN으로 빼는” 설계가 의미를 가집니다.

## (3) 지역별 SLO/에러버짓: 부분 장애를 ‘숫자’로 다루는 방식

부분 장애는 기술적으로도 까다롭지만, 조직적으로는 더 까다롭습니다. 글로벌 SLO 하나만 있으면 제품/비즈니스 관점에서 이해하기 쉽지만, 그 SLO가 실제 사용자 체감을 대표하지 못합니다.

나는 아래처럼 계층을 나눠 잡는 쪽이 현실적이라고 봅니다.

- Global SLO: 회사/제품이 말하는 대표 숫자
- **Regional guardrail SLO**: 특정 지역/특정 ASN에서 바닥이 무너지는 걸 막는 안전장치

여기서 guardrail SLO는 “전 지역 동일 숫자”가 아니라, 트래픽 규모/사업 중요도/대체 경로 유무를 반영해 다르게 가져가는 게 자연스럽습니다.

### 에러버짓은 ‘균형 장치’이지, 도덕 교과서가 아니다

Google SRE 쪽 문서가 좋은 이유는, SLO/에러버짓을 ‘운영 의사결정 도구’로 명확히 정의한다는 점입니다. 에러버짓을 다 쓰면 릴리스를 멈추는 식의 정책은 “신뢰성을 기능 개발 속도와 거래하기 위한 장치”로 설명됩니다. [Error Budget Policy](https://sre.google/workbook/error-budget-policy/), [Service Level Objectives(SRE Book)](https://sre.google/sre-book/service-level-objectives/)

부분 장애에 이 관점을 적용하면 결론이 또렷해집니다.

- 글로벌 SLO를 만족했다고 해서 “문제 없다”가 아닙니다.
- 특정 지역 guardrail이 계속 깨지면, 그 지역의 사용자는 이미 기능 개발과 무관하게 제품을 떠납니다.

### Burn rate alert를 ‘지역별’로 쪼개는 게 포인트

SRE Workbook은 SLO 기반 alerting에서 burn rate를 설명하고, 특정 비율로 에러버짓이 소모되는 상황을 탐지하는 패턴을 제시합니다. [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)

부분 장애에서 이걸 그대로 쓰려면, 분모/분자를 “region/colo/ASN label”로 쪼개야 합니다.

예를 들어 edge 로그나 gateway 로그를 Prometheus에 넣어 다음 라벨을 붙인다고 가정합니다.

- `region`(대륙/국가)
- `colo`(가능하면 PoP 코드)
- `asn`(가능하면)

그 다음 SLI를 아래처럼 만듭니다.

- `good = total - 5xx`
- `sli = good / total`

그리고 burn rate alert를 region 단위로 돌립니다.

아래는 PromQL 예시입니다(구현에 따라 metric 이름은 달라집니다).

```promql
# 5xx ratio, 5m window, by colo
sum by (colo) (rate(http_requests_total{status=~"5.."}[5m]))
/
sum by (colo) (rate(http_requests_total[5m]))
```

```yaml
# alert rules (example)
# objective: 99.9% success (error budget 0.1%) over 30d
# fast-burn page: 36x budget burn over 1h window (Workbook 스타일)

groups:
- name: slo-pop-guardrail
  rules:
  - alert: PopFastBurn5xx
    expr: |
      (
        sum by (colo) (rate(http_requests_total{status=~"5.."}[1h]))
        /
        sum by (colo) (rate(http_requests_total[1h]))
      ) > (36 * 0.001)
    for: 10m
    labels:
      severity: page
    annotations:
      summary: "Pop {{ $labels.colo }} is fast-burning error budget (5xx)"
```

핵심은 “global로 한 번”이 아니라 “colo별로”를 기본 단위로 두는 것입니다. IAD 같은 사건은 global 합산에서 임계치를 못 넘을 수 있지만, colo 단위 burn rate에서는 튀어야 정상입니다.

### 지역 SLO를 넣으면 알림이 폭발한다는 반론에 대해

맞는 말입니다. 그래서 guardrail SLO를 도입할 때는 스코프를 조절해야 합니다.

- 트래픽이 충분히 큰 지역부터
- 매출/핵심 고객이 몰린 지역부터
- 멀티-CDN/우회 경로가 준비된 지역부터

그리고 metric cardinality(특히 ASN까지 붙이면 폭발)를 관리해야 합니다. 초기에는 `region`과 `colo`까지만으로도 큰 효과가 납니다.

## Cloudflare 5xx를 볼 때 ‘원인 계층’을 빨리 가르는 방법

Cloudflare는 5xx 오류에 대해 공식 troubleshooting 문서를 제공하고, Error analytics에서 URL, source IP, Cloudflare data center 등의 정보를 모으라고 적어 둡니다. [Cloudflare 5xx errors](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/)

또한 Cloudflare가 생성하는 오류 응답에 대해 machine-readable format, retryability, `Retry-After` 헤더 같은 동작을 정리해 둔 문서도 있습니다. [Error responses](https://developers.cloudflare.com/fundamentals/reference/error-responses/)

PoP 단위 partial outage에서 중요한 건 “내 오리진이 죽었다”와 “엣지/네트워크 구간이 죽었다”를 빨리 분리하는 것입니다.

- 특정 colo에서만 52x가 늘어난다 → 네트워크/엣지/피어링/경로 쪽 가능성이 커짐
- 모든 colo에서 521/522가 같이 늘어난다 → 오리진/방화벽/용량 쪽 가능성이 커짐

이번 사건은 status 상으로 “traffic passing through Ashburn(IAD)”라고 표현돼 있습니다. 즉, 사용자 체감은 내 오리진이 정상이어도 깨질 수 있는 사건입니다. [Cloudflare Status incident](https://cloudflare.statuspage.io/incidents/3czg2lc9y1t8)

## 반론과 회의론: 부분 장애에 과잉대응하면 더 큰 사고를 부른다

부분 장애가 나올 때마다 설계를 복잡하게 만드는 건 위험합니다. 특히 멀티-CDN은 잘못 도입하면 다음 문제가 생깁니다.

- steering 플랩: health signal이 흔들리면 트래픽이 양쪽으로 왔다 갔다 하며 더 나빠짐
- 보안 정책 불일치: 한쪽 CDN으로 우회했더니 bot/WAF가 달라져 오히려 피해 확대
- 캐시/압축/헤더 차이로 성능/기능 차이가 드러남
- 운영권한/온콜/비용 배분이 복잡해짐

그래서 멀티-CDN은 “보험을 들었다”가 아니라 “두 개의 프로덕션을 운영한다”에 가깝다고 보는 게 안전합니다.

지역별 SLO도 마찬가지입니다.

- 너무 촘촘하면 알림이 소음이 되고,
- 팀이 그걸 운영할 준비가 안 됐으면, 결국 무시하게 됩니다.

따라서 설계의 목표는 ‘완벽한 자동화’가 아니라 ‘국소 폭발을 조기에 포착하고, 의사결정 비용을 낮추는 것’이어야 합니다.

## 앞으로 지켜볼 것: IAD 반복성과 ‘원인 공개’의 부재

이번 2026-09-18 incident 페이지는 한 문장 요약만 있고, 원인/완화/재발 방지 같은 RCA는 공개돼 있지 않습니다. [Cloudflare Status incident](https://cloudflare.statuspage.io/incidents/3czg2lc9y1t8)

Cloudflare가 과거에 큰 사건에 대해 상세 타임라인을 올린 적은 있습니다. 예를 들어 2025-08-21 incident에 대해서는 Cloudflare Blog에 사건 흐름을 시간 단위로 적었습니다(그 글에도 Ashburn(IAD) 언급이 들어갑니다). [Cloudflare incident on August 21, 2025](https://blog.cloudflare.com/cloudflare-incident-on-august-21-2025/)

이번 건도 후속 포스트모템이 공개될지, 아니면 status 수준에서 끝날지에 따라 “공급자 리스크를 어떻게 수치화할지”가 달라집니다. 공개가 없다면, 결국 내 SLO 설계에서 공급자 incident를 원인으로 자동 면책하기는 더 어려워집니다.

또 하나는 반복성입니다. Status 페이지에는 2026-09-15에도 IAD 경유 5xx 증가 incident가 올라와 있습니다. [Cloudflare Status(2026-09-15 IAD incident 포함)](https://cloudflare.statuspage.io/)

두 건이 같은 근본 원인인지, 단순히 IAD라는 교통 요지에서 서로 다른 이유로 발생한 것인지, 외부에서 단정할 근거는 없습니다. 다만 운영 설계 관점에서는 “IAD 같은 특정 거점에 트래픽이 집중되는 사용자 집단이 있고, 그 거점의 부분 장애가 체감을 폭발시킨다”는 사실만으로도 설계를 바꿀 충분한 이유가 됩니다.

## 지금 할 수 있는 일: ‘부분 장애’를 전제로 설계를 다시 그리기

이 유형의 사건 직후에 바꾸기 좋은 것들을 내 기준으로 정리하면 다음과 같습니다.

1) 관측을 글로벌 합산에서 분해합니다.
   - colo/region 단위 5xx ratio 대시보드
   - 상위 ASN/상위 리졸버(가능하면)별 에러율

2) synthetic check를 사용자 경로 기준으로 재정의합니다.
   - HTTPS fetch + marker 검증
   - 다지역 + 다ASN 관측점
   - 다수결/히스테리시스 기반 판정으로 플랩 방지

3) 멀티-CDN은 “전체 failover”가 아니라 “국소 steering”부터 설계합니다.
   - geo/ASN 기반으로 IAD catchment만 우회 가능한지부터 검증
   - steering control plane의 독립성 확보
   - TLS/WAF/cache parity를 ‘필수 스펙’으로 둠

4) 지역별 guardrail SLO를 추가하고, burn rate alert를 colo 단위로 넣습니다.
   - global SLO는 유지하되, 특정 지역의 바닥이 무너지는 걸 별도로 감지
   - 알림 폭발을 피하기 위해 트래픽/매출 상위 지역부터 단계적 적용

5) 공급자 상태 알림을 운영 시스템에 붙입니다.
   - Cloudflare는 Status API 제공 및 자동 접근을 권장합니다. [Cloudflare Status API 문서](https://www.cloudflarestatus.com/api)
   - Status page 알림은 Cloudflare 인프라와 독립적으로 전달된다고 설명돼 있습니다. [Cloudflare Status 지원 문서](https://developers.cloudflare.com/support/cloudflare-status/)
   - Cloudflare Dashboard의 Notifications도 incident/maintenance를 받을 수 있고, plan에 따라 webhook/PagerDuty 같은 채널이 열립니다. [Notifications 문서](https://developers.cloudflare.com/notifications/), [Available Notifications(Cloudflare Status 항목)](https://developers.cloudflare.com/notifications/notification-available/)

부분 장애는 재현이 어렵고, 한 번 지나가면 조직이 잊기 쉽습니다. 그래서 설계는 “다음 번에 같은 유형이 왔을 때 어떤 지표가 먼저 튀고, 어떤 자동화가 어떤 범위에서 작동해야 하는가”를 숫자와 경계로 고정하는 쪽으로 가는 게 맞습니다.

## 참고 자료

- [Cloudflare Status incident: Network Performance Issues in Ashburn (2026-09-18)](https://cloudflare.statuspage.io/incidents/3czg2lc9y1t8)
- [Cloudflare Status 메인 페이지(incident 요약 및 과거 IAD incident 포함)](https://cloudflare.statuspage.io/)
- [Cloudflare Status API 문서](https://www.cloudflarestatus.com/api)
- [Cloudflare Status 지원 문서: Cloudflare Status](https://developers.cloudflare.com/support/cloudflare-status/)
- [Cloudflare Notifications 문서](https://developers.cloudflare.com/notifications/)
- [Cloudflare Notifications: Available Notifications(Cloudflare Status 섹션)](https://developers.cloudflare.com/notifications/notification-available/)
- [Cloudflare IP addresses 개념 문서](https://developers.cloudflare.com/fundamentals/concepts/cloudflare-ip-addresses/)
- [Traffic flow through Cloudflare](https://developers.cloudflare.com/fundamentals/concepts/traffic-flow-cloudflare/)
- [Anycast 개념(Cloudflare Learning Center)](https://www.cloudflare.com/learning/cdn/glossary/anycast-network/)
- [Cloudflare network and services resilience (PDF)](https://cf-assets.www.cloudflare.com/slt3lc6tev37/7ad0dpR3YyqxMlikPfbBgn/020b7450909f03ccf3c7dcfb0e99fc2e/Resilience_Whitepaper.pdf)
- [Meet Traffic Manager (Cloudflare Blog)](https://blog.cloudflare.com/meet-traffic-manager/)
- [Cloudflare 5xx errors troubleshooting](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/)
- [Error responses(Cloudflare)](https://developers.cloudflare.com/fundamentals/reference/error-responses/)
- [Adaptive routing (Cloudflare Load Balancing)](https://developers.cloudflare.com/load-balancing/understand-basics/adaptive-routing/)
- [Traffic steering (Cloudflare Load Balancing)](https://developers.cloudflare.com/load-balancing/understand-basics/traffic-steering/)
- [How endpoints and pools become unhealthy (Cloudflare Load Balancing)](https://developers.cloudflare.com/load-balancing/understand-basics/health-details/)
- [Multi-CDN failover: a working setup, step by step (CDN World)](https://www.cdnworld.com/guide/multi-cdn-failover-setup)
- [DNS steering versus client-side switching (CDN World)](https://www.cdnworld.com/article/dns-steering-vs-client-switching)
- [RUM data 기반 steering 가이드 (CDN World)](https://www.cdnworld.com/guide/steer-on-rum-data)
- [A First Look at Anycast CDN Traffic (arXiv)](https://arxiv.org/abs/1505.00946)
- [Google SRE: Error Budget Policy](https://sre.google/workbook/error-budget-policy/)
- [Google SRE: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Google SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
