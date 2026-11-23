---
title: "NSA 기밀 통신망 장애가 남긴 과제: 내부망 SLO와 복구 체계"
description: "NSA 내부 기밀 통신망 장애를 계기로, 내부망도 SLO·Incident Command·의존성 분해로 운영 설계해야 하는 이유를 정리합니다."
date: 2026-11-23 15:40:58 +0900
categories: ["News", "Infrastructure"]
tags: ["infrastructure", "slo", "incident-management", "resilience", "ics", "operations-design"]
render_with_liquid: false
---

## 이번 NSA 내부망 장애에서 확인된 사실

2026년 11월 17일(미국 현지 시각) AP는 NSA의 기밀 통신에 쓰이는 내부 네트워크가 오프라인 상태가 됐다고 보도했습니다. AP 기사에서 확인되는 포인트는 의외로 단순합니다. “routine maintenance” 이후 내부망이 내려갔고, NSA는 “scheduled routine maintenance 중 temporary degradation”라고 설명했으며, 영향 범위나 구체 원인은 추가로 공개하지 않았습니다. NSA는 “mission-critical capabilities remain fully operational”이라는 문장을 넣으면서, 인프라가 “multiple layers of redundancy”로 설계되어 있다고 덧붙였습니다.[^1]

이런 종류의 사건에서 개발자 관점으로 더 중요한 건, 장애가 ‘공격’이었는지 ‘실수’였는지보다도 “내부 전용망/분리망도 외부 SaaS처럼 다운된다”는 관측이 공론장으로 올라온 순간입니다. 외부 고객이 보는 status page가 없고, 상세를 공개하지 않는 조직일수록, 사용자(내부 사용자 포함)는 더 강하게 불안을 체감합니다. 같은 기사에서 AP는 FAA ground stop, JPMorgan Chase의 기술 이슈, 항공사 내부 시스템 장애 같은 동시다발적인 디지털 장애를 같이 언급했습니다. 한 주에 사건이 겹치면, 원인 상관관계가 없더라도 조직의 리더십은 “전반적으로 신뢰가 흔들리는 상황”으로 받아들이게 됩니다.[^1]

장애의 종료 시점과 복구 상태에 대해서는 매체별로 톤이 다르지만, 11월 20일(미국 현지 시각) The Record는 NSA가 “normal conditions”로 돌아왔다는 대변인 코멘트를 인용했고, 동시에 직원 안내 음성 메시지에 “normal conditions, with exceptions”라는 표현이 있었다고 전했습니다. “exceptions”와 “Code Orange” 같은 표현은, 기술적으로 서비스가 떠 있더라도 운영적으로는 정상 상태로 간주하기 어렵다는 현실을 보여줍니다.[^2]

원인에 대해서는, 여기서는 추정 대신 ‘보도된 문장’만 분리해서 다룹니다. The Record는 “patches to a commonly-used programming language”가 내부 통신망 크래시와 연관되어 있다는 서술을 포함합니다.[^2] 이게 사실이든 아니든, 운영 설계의 교훈은 바뀌지 않습니다. 패치/업그레이드/정기 점검은 내부 인프라에서 가장 흔한 변경이고, 가장 흔한 장애 원인입니다. 문제는 ‘패치를 했느냐’가 아니라, 패치가 실패했을 때 조직이 어떤 SLO와 어떤 지휘 체계로 손실을 통제하느냐입니다.

## 내부망/전용망을 외부 서비스처럼 SLO로 다뤄야 하는 이유

내부망을 “보안 때문에 분리된 특수 네트워크”로 정의하는 순간, 운영의 언어가 보안 통제로만 수렴하는 경향이 생깁니다. 하지만 운영의 현실은 반대입니다. 분리망일수록 다음 특성이 강해집니다.

- 의존성이 더 ‘고정’되어 있습니다. 인터넷으로 빠져나가 우회하는 경로가 의도적으로 차단됩니다.
- 변경 창구가 더 ‘중앙집중’되어 있습니다. 승인, 반입, 반출, 검증의 단계가 늘어납니다.
- 장애 시 관측 가능성이 더 낮습니다. telemetry 반출이 제한되거나, 로그 접근이 계층화됩니다.

이 조합은, 외부 서비스보다 내부망이 더 안전하다는 결론이 아니라, 내부망이 더 쉽게 “운영적으로 깜깜해질 수 있다”는 결론로 이어집니다. 그래서 내부망은 보안 통제와 별개로, 신뢰성 목표를 수치로 정의해야 합니다.

Google SRE는 SLO를 “서비스를 제대로 운영하기 위해, 어떤 행동이 중요하고 어떻게 측정할지 이해해야 한다”는 문제로 정의합니다. 그리고 그 ‘사용자’가 외부 고객이든 내부 API 사용자든 상관없다고 못 박습니다. 내부망/전용망도 마찬가지로, 내부 사용자(분석가, 운영요원, 보안요원, 의사결정자)에게 제공되는 하나의 서비스입니다. **SLO**는 그 서비스를 운영하는 최소 단위의 계약(법적 SLA가 아니라 운영 계약)입니다.[^3]

내부망에서 SLO를 명시하지 않으면, 장애 대응에서 항상 같은 패턴이 반복됩니다.

1) “중요하니 무조건 100%”라는 말이 튀어나옵니다.
2) 100%를 목표로 삼는 순간, 패치/교체/정비가 ‘예외 상황’으로 밀립니다.
3) 예외로 밀린 변경이 쌓이면, 어느 순간 변경 1회당 blast radius가 커집니다.
4) 결국 큰 장애가 나고, 다시 1)로 돌아갑니다.

Google SRE가 error budget을 도입하는 이유가 여기 있습니다. error budget은 “완벽을 목표로 삼는 대신, 허용 가능한 실패량을 정의하고 그 안에서 속도와 안정성을 교환”하게 만듭니다. error budget이 소진되면 변경을 멈추는 규칙이 생기고, 규칙이 생기면 ‘누가 멈추라고 했느냐’ 같은 정치적 소모가 줄어듭니다.[^4] 여기서 핵심은 **error budget**이 단지 모니터링 지표가 아니라, 변경 승인 체계(릴리스, 패치, 점검)와 결합해야 한다는 점입니다.

내부망의 SLO 정의에서 자주 놓치는 포인트는 “운영자 관측(healthy)과 사용자 체감(usable)이 다를 수 있다”는 점입니다. Google은 availability를 정의할 때도 “측정이 사용자 기대와 비즈니스 목표에 맞아야 한다”는 이야기를 반복합니다. 내부망에서 NOC 대시보드가 녹색이어도, 실제 사용자 세션이 인증에 실패하거나, DNS가 지연되거나, 특정 enclave에서만 경로가 끊기면 그건 장애입니다.[^5]

내부망 SLO를 외부 서비스처럼 다루는 건 내부망을 외부처럼 공개하자는 뜻이 아닙니다. 내부망이야말로 “공개가 어렵기 때문에” 더 엄격한 내부 SLO와 더 엄격한 사후검증이 필요합니다. 공개 포스트모템이 불가능하면, 내부에서라도 SLO 기반으로 어떤 손실이 발생했는지(몇 시간, 몇 퍼센트, 어떤 사용자 경로)가 숫자로 남아야 합니다.

## 복구 우선순위는 기술 문제가 아니라 ‘조직의 약속’ 문제입니다

보안/국방 조직의 인프라는 복구 우선순위를 “기술적으로 먼저 살릴 수 있는 것”으로 결정하기 쉽습니다. 내부망이 복잡할수록, 손이 먼저 닿는 장비와 팀이 먼저 움직입니다. 그런데 이 방식은 재난 상황의 전형적인 실패 패턴입니다. 복구가 진행될수록, 가장 중요한 업무가 아니라 “가장 복구가 쉬운 업무”가 먼저 살아납니다.

NIST SP 800-34(Contingency Planning)는 애초에 IT contingency planning의 목표를 “요구사항과 우선순위를 결정”하는 것으로 잡습니다. 즉, 장애가 난 다음에 복구 우선순위를 회의로 결정하는 게 아니라, 장애가 나기 전에 우선순위를 문서로 고정해야 한다는 뜻입니다.[^6]

NIST SP 800-184(Guide for Cybersecurity Event Recovery)는 복구 계획에서 “자산과 의존성(people/process/technology, external resources 포함)을 식별하고, 상대적 우선순위로 복구를 안내”해야 한다고 말합니다. 또한 복구 계획을 언제 발동할지, 누가 발동 권한을 갖는지, 어떤 마일스톤에서 복구 단계를 종료할지까지 미리 정하라고 권고합니다.[^7]

내부망 장애에서 이 문장들이 특히 중요한 이유는 두 가지입니다.

첫째, 내부망은 “필수 기능”과 “편의 기능”이 같은 네트워크 위에 있을 때가 많습니다. 보안 분리 때문에 망을 더 쪼개지만, 쪼갠 각 구간 안에서는 여전히 여러 업무가 같은 기반 서비스(Identity, DNS, PKI, time sync, endpoint management)에 얽혀 있습니다. 그래서 한 구성요소의 장애가 여러 업무를 동시에 멈춥니다.

둘째, 내부망은 대체 경로가 제한적이어서 “줄 세우기”가 필수입니다. 외부 서비스라면 우회 라우팅, CDN, public cloud region failover로 시간을 벌 수 있지만, 분리망은 그런 옵션이 제한됩니다. 복구가 느린 게 문제가 아니라, 복구 순서가 뒤엉키는 게 치명적입니다.

내가 실제 조직에서 우선순위 모델을 만들 때는 “서비스/시스템 단위”가 아니라 “업무 경로 단위(user journey)”로 쪼갭니다. 예를 들어 내부 기밀 통신망이라면 다음 같은 경로를 먼저 정의합니다.

- 메시지 송수신(작성 → 암호화/서명 → 라우팅 → 수신함 도착)
- 문서 공유(조회/다운로드) 
- 인증/권한(로그인, token 발급, privileged access)
- 운영 통제(배포/패치/정책 배포, endpoint 격리)

그 다음에 각 경로를 지탱하는 공통 기반(Directory, DNS, time, PKI, network routing, VPN/remote access, jump host)을 dependency graph로 연결합니다. 이 그래프가 있어야 “무엇부터 살릴지”가 아니라 “무엇을 살리면 어떤 업무가 같이 살아나는지”가 보입니다.

여기서 자주 나오는 반론은 “대체 통신은 전화나 무전으로 하면 된다”입니다. 맞는 말이지만, 그건 ‘우회’이지 ‘복구’가 아닙니다. 우회 채널을 복구 우선순위에 포함시키려면, NIST SP 800-53의 CP-11(Alternate Communications Protocols) 같은 통제를 실제 운영 설계로 끌어와야 합니다. 장애 상황에서 사용할 대체 통신 프로토콜/채널을 정해두고, 정기적으로 훈련해야 우회가 우회로서 기능합니다.[^8]

## 복구 의사결정 체계: Incident Command를 내부망에 적용해야 하는 이유

내부망 장애는 ‘기술’보다 ‘조직’을 먼저 무너뜨립니다. 특히 보안/국방/금융처럼 이해관계자가 많은 조직은, 장애가 커지면 엔지니어가 기술 대응을 하기 전에 “보고”와 “승인”과 “질문”에 잠식됩니다. 그러면 장애 대응은 사실상 실패합니다.

Google은 incident 대응 체계를 IMAG로 정리하면서, 이것이 미국의 Incident Command System(ICS)에 기반한다고 밝힙니다. 그리고 incident management의 3Cs를 coordinate, communicate, control로 요약합니다. 역할은 Incident Commander(IC), Communications Lead(CL), Operations Lead(OL)가 중심이고, CL이 이해관계자 업데이트를 맡음으로써 OL이 실제 완화와 복구에 집중하게 설계합니다.[^9]

이 패턴을 내부망에 가져오면 무엇이 달라지느냐가 핵심입니다.

- “누가 제일 잘 아느냐”가 아니라, **Incident Commander**가 선언되고 권한을 갖습니다.
- 기술팀이 root cause 분석을 하더라도, 그건 OL의 일이고 IC의 일은 ‘목표/범위/우선순위/리스크 승인’입니다.
- CL이 없으면, 기술팀은 복구보다 ‘설명’에 끌려다닙니다.

Google의 Secure and Reliable Systems 문서에서도 incident 선언 시점에 “우리는 X와 관련된 incident를 선언하고, 내가 IC다” 같은 명시적 선언을 강조합니다. 그리고 handover를 공식화하라고 말합니다. 내부망 장애는 며칠 가는 경우가 있기 때문에, 교대/인수인계가 부실하면 기술적으로 회복해도 운영적으로 다시 무너집니다.[^10]

ICS 자체의 기본 구조는 FEMA의 NIMS 문서에서 반복해서 설명하는데, command 아래에 operations/planning/logistics/finance-admin이 모듈형으로 확장되는 구조입니다. IT incident에서도 planning(다음 2시간 계획, 다음 12시간 계획)을 분리하지 않으면 즉흥 대응만 남고, logistics(장비/인력/승인)를 별도로 떼지 않으면 OL이 사람/권한/조달 문제에 발이 묶입니다.[^11]

분리망/기밀망에서 특히 중요한 건 “커뮤니케이션이 제한된 환경에서도 CL 역할을 분리해야 한다”는 점입니다. 외부 status page가 없더라도, 내부에서는 업데이트 채널이 필요합니다. The Record가 언급한 “Code Orange”나 “delayed openings” 같은 운영 조치는 기술적 복구가 늦어질 때 내부 리스크를 줄이는 완화책입니다. 이 조치가 혼선 없이 작동하려면, CL이 어떤 메시지를 어떤 채널로 어떤 주기로 내보낼지 이미 설계되어 있어야 합니다.[^2]

## 단일 벤더/단일 구성요소 의존을 줄이는 운영 설계 프레임

이번 주제를 “국가급 망도 다운된다”라는 문장으로 끝내면, 결론은 늘 운/불운이 됩니다. 운영 설계 관점에서는 단일 사건을 ‘운영 구조의 취약성’으로 번역해야 합니다. 나는 이걸 세 층으로 나눕니다.

1) 구성요소 수준의 SPOF(단일 장비/단일 링크/단일 인증 서버)
2) 변경 수준의 SPOF(패치 파이프라인, 배포 도구, 정책 배포)
3) 벤더/생태계 수준의 동조화된 실패(correlated failure)

세 번째가 특히 요즘 문제입니다. 분리망은 외부 인터넷을 안 쓰니 안전할 것 같지만, 실제로는 내부 표준 스택이 훨씬 단조롭습니다. “한 벤더의 OS + 한 벤더의 directory + 한 벤더의 endpoint management + 한 종류의 언어 런타임” 같은 형태가 흔합니다. 이 구조는 취약점 패치가 ‘동시에’ 들어오고, ‘동시에’ 배포되며, ‘동시에’ 실패하는 형태로 폭발합니다.

NIST SP 800-160 Vol.2(Developing Cyber-Resilient Systems)는 cyber resiliency design principles로 Diversity, Segmentation, Non-Persistence 등을 포함합니다. 여기서 Diversity는 단지 취향 문제가 아니라, 같은 취약점/같은 버그/같은 운영 실수로 한 번에 무너지는 monoculture 리스크를 줄이는 설계 원칙입니다.[^12]

영국 정부의 Organisational Resilience Guidance도 resilience 설계 원칙으로 redundancy, diversity, modularity, adaptability를 명시합니다. ‘정부 조직’이라는 점이 중요한데, 이런 원칙은 민간 SaaS에서만 유효한 게 아니라는 뜻입니다. 내부망/전용망도 조직 회복탄력성의 일부로 다뤄야 한다는 방향성이 문서로 이미 정리되어 있습니다.[^13]

NCSC의 Secure design principle 문서에서는 10대의 동일한 서버를 load balance하는 경우를 예로 들면서, 랜덤 고장에는 강하지만 동일 취약점에는 약하다고 지적합니다. 내부망도 똑같습니다. 장비를 이중화해도, 동일한 firmware/동일한 자동화/동일한 운영 런북이면 한 번의 실수로 동시에 무너집니다.[^14]

여기서 중요한 건, 기술적으로 “multi vendor”를 외치는 게 아니라 운영 설계를 바꾸는 것입니다. 내가 정리하는 운영 설계 프레임은 다음과 같습니다.

- (A) control plane과 data plane을 분리한다. 
  - 인증/권한, 배포/패치, 모니터링/로그 수집 같은 control plane이 죽으면 복구 자체가 불가능해진다.
- (B) 복구를 돕는 시스템은 ‘더 엄격하게’ 분리한다.
  - out-of-band 관리망, break-glass 계정, 오프라인/타 망 기반의 권한 상승 경로가 여기에 들어간다.
- (C) 다양성은 “기술 선택”이 아니라 “동조화된 변경을 막는 방법”으로 설계한다.
  - 같은 시간에 같은 변경이 전 영역에 배포되지 않도록 ring-based rollout을 설계하는 게 먼저다.
- (D) 모듈성은 네트워크 토폴로지만이 아니라 운영 팀/권한/승인 경로까지 포함한다.
  - 승인 병목이 단일 부서로 몰리면, 장애 시에도 단일 병목이 된다.

이 블로그에서 예전에 다룬 장애 전파 패턴과도 연결됩니다. 예를 들어 [Microsoft 365 장애가 드러낸 네트워킹 게이트웨이 SPOF](https://daewooki.github.io/posts/m365-gateway-outage-bcp-checklist/)에서 정리했던 것처럼, 게이트웨이/인증/네트워크 경계는 내부 인프라든 외부 SaaS든 ‘한 번 무너지면 전 서비스가 죽는 계층’이 됩니다. 그리고 [Cloudflare R2 503 장애 대응: 객체 스토리지 의존성 분해](https://daewooki.github.io/posts/r2-503-outage-app-resilience-patterns/)에서 이야기했던 것처럼, 의존성을 분해하고 우회 경로를 만들어두지 않으면 복구 우선순위는 항상 감에 의존하게 됩니다.

## 내부망 SLO를 실제로 굴리는 방법: 측정-경보-변경 정책의 결합

SLO를 문서로만 쓰면 KPI가 됩니다. 내부망에서 SLO를 운영 설계로 만들려면, 최소 3가지를 같이 묶어야 합니다.

1) 사용자 관점 측정(black-box probing)
2) burn rate 기반 경보(“얼마나 빨리 error budget을 태우는지”)
3) 변경 정책(패치/점검/업그레이드의 게이트)

아래 예시는 “분리망 내부 포털(또는 내부 메시징 게이트웨이)의 가용성”을 측정한다고 가정한 구성입니다. 실제 NSA 같은 환경은 훨씬 복잡하지만, 내부망을 SLO로 운영한다는 감각은 이런 형태로 시작하는 게 빠릅니다.

### docker-compose: Prometheus + blackbox-exporter + 내부 서비스

```yaml
# docker-compose.yaml
services:
  intranet:
    image: nginx:1.27-alpine
    ports:
      - "8080:80"

  blackbox:
    image: prom/blackbox-exporter:v0.26.0
    command:
      - "--config.file=/etc/blackbox_exporter/config.yml"
    volumes:
      - ./blackbox/config.yml:/etc/blackbox_exporter/config.yml:ro
    ports:
      - "9115:9115"

  prometheus:
    image: prom/prometheus:v2.55.1
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prometheus/rules.yml:/etc/prometheus/rules.yml:ro
    ports:
      - "9090:9090"
```

```yaml
# blackbox/config.yml
modules:
  http_2xx:
    prober: http
    timeout: 5s
    http:
      valid_http_versions: ["HTTP/1.1", "HTTP/2.0"]
      valid_status_codes: []  # default: 2xx
      preferred_ip_protocol: "ip4"
```

```yaml
# prometheus/prometheus.yml
global:
  scrape_interval: 15s

rule_files:
  - /etc/prometheus/rules.yml

scrape_configs:
  - job_name: blackbox
    metrics_path: /probe
    params:
      module: [http_2xx]
    static_configs:
      - targets:
          - http://intranet:80/
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox:9115
```

```yaml
# prometheus/rules.yml
# 30일 윈도우에서 99.9% 가용성 SLO를 염두에 둔 최소 룰 예시
# (현업에서는 multi-window burn-rate alert까지 확장합니다)
groups:
  - name: intranet-slo
    rules:
      - record: job:probe_success:ratio5m
        expr: avg_over_time(probe_success{job="blackbox"}[5m])

      - record: job:probe_success:ratio30d
        expr: avg_over_time(probe_success{job="blackbox"}[30d])

      - alert: IntranetSLOBurningFast
        expr: (1 - job:probe_success:ratio5m) > 0.01
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "Intranet availability dropping fast"
          description: "5m error ratio > 1% (proxy for fast burn rate)."
```

실행은 다음과 같습니다.

```bash
docker compose up -d
```

- Prometheus: `http://localhost:9090`
- blackbox-exporter: `http://localhost:9115`
- 내부 서비스(예시): `http://localhost:8080`

Prometheus에서 아래 PromQL을 바로 확인할 수 있습니다.

- 현재 탐지 성공 여부(1이면 성공, 0이면 실패)

```promql
probe_success{job="blackbox"}
```

- 5분 단위 성공률(사용자 체감에 가까운 단기 SLI)

```promql
job:probe_success:ratio5m
```

이 예시는 단순하지만, 내부망에서 핵심은 여기서 시작됩니다.

- probe 위치를 “망 경계/zone/enclave마다” 둡니다. 같은 서비스라도 zone별로 SLI가 다를 수 있습니다.
- probe를 ICMP ping 같은 네트워크 레벨만 두지 않습니다. 로그인/토큰 발급/메시지 전송처럼 ‘업무 경로’를 probe해야 합니다.
- 알람은 평균 가용성만 보지 않고, burn rate로 봅니다. 30일 평균 99.9%를 맞출지라도 지금 10분 동안 50%를 기록하면 이미 incident입니다.

Google SRE가 SLO를 내부 API에도 적용한다고 강조하는 이유는, 내부 서비스가 외부 서비스의 의존성이기 때문입니다. 내부망은 그 자체가 “조직 전체의 dependency graph에서 가장 아래 레이어”에 위치합니다. 그래서 SLO 없이 운영하면, 장애는 반드시 상위 레이어로 전파됩니다.[^3]

마지막으로, SLO를 변경 정책에 연결해야 합니다. 예를 들어 “내부 메시징/디렉터리/인증” 같은 기반 서비스의 error budget이 위험 수준이면, 점검/업그레이드를 ‘미루는’ 게 아니라 ‘더 쪼개서’ 진행해야 합니다. 한 번에 끝내는 변경은 보통 “승인/검증 비용이 높아서” 택하는데, 그 비용을 장애 비용으로 바꿔치기한 것에 불과합니다.

## 회의론과 반론: 내부망은 보안이 우선인데 SLO가 현실적인가

내부망 운영에서 흔히 듣는 반론은 대략 네 가지입니다.

### 1) “내부망은 SLA/SLO 같은 민간 용어가 안 맞는다”

SLO는 민간 용어가 아니라 운영의 수학입니다. 가용성, 지연, 오류율은 보안 분류와 무관하게 존재합니다. 외부에 공개하지 않을 뿐, 내부에서는 더 엄격하게 수치로 합의해야 합니다.

### 2) “가용성을 높이면 보안이 약해진다”

보안과 가용성이 충돌하는 경우는 분명 있습니다. 예를 들어 더 강한 검증은 지연을 만들고, 더 강한 격리는 우회를 막습니다. 하지만 그건 SLO를 하지 말아야 한다는 이유가 아니라, SLO를 통해 trade-off를 명시해야 한다는 이유입니다.

NIST SP 800-184가 강조하는 것도, “diminished capacity로 운영하거나 우선순위에 따라 단계적으로 복구하는 계획”입니다. 즉, 완벽한 복구만이 답이 아니라, 안전한 축소 운영이 복구 전략의 일부입니다.[^7]

### 3) “분리망은 관측(telemetry)이 제한된다”

관측이 제한된 망일수록 black-box probe가 더 중요합니다. 내부 로그를 못 빼더라도, zone 내부에서 probe하고 zone 내부에서 집계할 수는 있습니다. ‘중앙’으로 못 모으면 ‘로컬’로라도 수치가 남아야 합니다.

### 4) “사건 상세를 공개할 수 없는데, SLO 기반 사후검증이 의미 있나”

상세 원인을 공개하지 못해도, 영향과 손실은 남길 수 있습니다. 오히려 원인보다 영향이 조직 학습에 더 중요할 때가 많습니다.

- 어떤 업무 경로가 몇 시간 동안 실패했는가
- 대체 절차가 작동했는가(작동했다면 몇 %를 커버했는가)
- 어떤 승인/지휘 병목이 복구 시간을 늘렸는가

이 데이터는 기밀을 해치지 않고도 남길 수 있고, 남겨야 다음 장애에서 같은 실수를 줄입니다.

## 앞으로 지켜볼 것: 내부망 장애가 남기는 운영 설계 변화

NSA 사건 자체는 상세가 제한될 가능성이 높습니다. AP 기사에서도 NSA는 원인과 범위를 추가로 공개하지 않았습니다.[^1] 이럴수록 바깥 조직이 배울 수 있는 건 “운영 프레임”뿐입니다.

내가 관심 있게 보는 포인트는 다음입니다.

- ‘정기 점검’이 장애로 번졌을 때, 조직이 내부적으로 어떤 SLO를 근거로 리스크 승인을 했는지
- “normal conditions, with exceptions” 같은 상태 표현이, 운영적으로 어떤 제한(시설/업무/권한)을 뜻하는지
- 한 주에 여러 기관/기업 장애가 겹칠 때, 각 조직이 “상관관계 없음”이라는 발표로 끝낼지, 아니면 “동조화된 변경/패치/벤더 종속”이라는 구조적 문제로 접근할지

이 관점은 개별 기관을 비난하려는 게 아니라, 내부 인프라를 ‘안전지대’로 취급하는 조직 문화가 얼마나 위험한지 드러내기 위한 것입니다.

## 지금 당장 내부망 운영에서 바꿀 수 있는 것

나는 내부망/전용망 운영을 맡게 되면, 기술 변경보다 먼저 운영 설계를 아래 순서로 고정합니다.

1) 내부망을 하나의 서비스 카탈로그로 정의하고, 업무 경로 단위로 SLI를 정리합니다.
2) 핵심 기반 서비스(Identity/DNS/PKI/time/remote access/배포·패치 파이프라인)에 내부 SLO를 붙입니다.
3) error budget 소진 시 자동으로 변경을 제동하는 룰을 문서가 아니라 프로세스로 박습니다.
4) incident 시 IC/OL/CL 역할을 분리하고, ‘보고 라인’이 아니라 ‘incident 맥락’으로 사람을 배치합니다.
5) control plane의 break-glass 경로(대체 통신, 대체 인증, out-of-band 운영)를 실전 훈련으로 검증합니다.
6) 단일 벤더/단일 구성요소 의존은 “교체”보다 “동시 변경을 막는 rollout 설계”부터 손댑니다.

결국 내부망도 제품이고, 제품은 SLO로 운영되고, 장애는 ICS 기반으로 지휘되어야 하며, 다양성은 기술 취향이 아니라 운영 설계로 구현된다는 결론입니다.

## 참고 자료

- [NSA communications network goes down during maintenance (AP News)](https://apnews.com/article/22dc6be1bf1d1f5f86a7167f016e9526)
- [NSA resumes normal operations following internal network disruptions (The Record)](https://therecord.media/nsa-resumes-normal-operations-following-internal-disruptions)
- [Classified NSA communications network down, people familiar say (Nextgov/FCW)](https://www.nextgov.com/digital-government/2026/11/classified-nsa-communications-network-down-people-familiar-say/417277/)
- [Service Level Objectives (Google SRE Book)](https://sre.google/sre-book/service-level-objectives/)
- [Production Services Best Practices (Google SRE Book)](https://sre.google/sre-book/service-best-practices/)
- [Error Budget Policy (Google SRE Workbook)](https://sre.google/workbook/error-budget-policy/)
- [Incident management guide (Google SRE)](https://sre.google/resources/practices-and-processes/incident-management-guide/)
- [Building Secure and Reliable Systems, Chapter 17 (Google)](https://google.github.io/building-secure-and-reliable-systems/raw/ch17.html)
- [NIMS Appendix A: Incident Command System (FEMA)](https://www.fema.gov/pdf/emergency/nims/nims_appendix.pdf)
- [Contingency Planning Guide for Federal Information Systems (NIST SP 800-34 Rev.1)](https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final)
- [Guide for Cybersecurity Event Recovery (NIST SP 800-184)](https://csrc.nist.gov/pubs/sp/800/184/final)
- [Developing Cyber-Resilient Systems (NIST SP 800-160 Vol.2 Rev.1)](https://csrc.nist.gov/pubs/sp/800/160/v2/r1/final)
- [Organisational Resilience Guidance for UK Government Departments (GOV.UK)](https://www.gov.uk/government/publications/organisational-resilience-guidance-for-uk-government-departments-agencies-and-arms-length-bodies/organisational-resilience-guidance-for-uk-government-departments-agencies-and-arms-length-bodies-albs-html)
- [Secure design principles: Make disruption difficult (NCSC)](https://www.ncsc.gov.uk/collection/cyber-security-design-principles/making-disruption-difficult)

[^1]: <https://apnews.com/article/nsa-computer-network-down-22dc6be1bf1d1f5f86a7167f016e9526>
[^2]: <https://therecord.media/nsa-resumes-normal-operations-following-internal-disruptions>
[^3]: <https://sre.google/sre-book/service-level-objectives/>
[^4]: <https://sre.google/sre-book/service-best-practices/>
[^5]: <https://cloud.google.com/blog/products/gcp/available-or-not-that-is-the-question-cre-life-lessons>
[^6]: <https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final>
[^7]: <https://nvlpubs.nist.gov/nistpubs/specialpublications/nist.sp.800-184.pdf>
[^8]: <https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf?Channel%5B0%5D%5B0%5D=m&Channel%5B0%5D%5B1%5D=ms-side-widget&Channel%5B1%5D=ms-side-widget&apps__c%5B0%5D=it_risk_management&apps__c%5B1%5D=it_risk_management&field_insight_category_target_id=481&field_portal_category_target_id=341&image_url%5B0%5D=cyber-grc-prime-product-overview-lp.jpg&image_url%5B1%5D=cyber-grc-prime-product-overview-lp.jpg&pdf_url%5B0%5D=cyber-grc-prime-product-overview.pdf%C2%AE_subjectline__c%3DCyberGRC%2BPrime&pdf_url%5B1%5D=cyber-grc-prime-product-overview.pdf%C2%AE_subjectline__c%3DCyberGRC%2BPrime&search-key=cyber%2Brisk%2Bquantifications&wtime=%7Bseek_to_second_number%7D>
[^9]: <https://sre.google/resources/practices-and-processes/incident-management-guide/?hl=ca>
[^10]: <https://google.github.io/building-secure-and-reliable-systems/raw/ch17.html>
[^11]: <https://www.fema.gov/pdf/emergency/nims/nims_appendix.pdf>
[^12]: <https://csrc.nist.gov/pubs/sp/800/160/v2/r1/final>
[^13]: <https://www.gov.uk/government/publications/organisational-resilience-guidance-for-uk-government-departments-agencies-and-arms-length-bodies/organisational-resilience-guidance-for-uk-government-departments-agencies-and-arms-length-bodies-albs-html>
[^14]: <https://www.ncsc.gov.uk/collection/cyber-security-design-principles/making-disruption-difficult>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
