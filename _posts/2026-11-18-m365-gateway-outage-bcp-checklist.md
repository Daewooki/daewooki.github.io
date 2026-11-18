---
title: "Microsoft 365 장애가 드러낸 네트워킹 게이트웨이 SPOF"
description: "게이트웨이 단일 장애점과 retry 폭주가 SaaS 장애를 조직의 업무 중단으로 키운 과정을, 우리 관점 체크리스트로 정리합니다."
date: 2026-11-18 12:30:12 +0900
categories: ["News", "Cloud"]
tags: ["microsoft-365", "outage", "bcp", "retry-storm", "incident-response", "resilience"]
render_with_liquid: false
---

## 11/12~14 Microsoft 365 글로벌 장애: 사실관계부터

이번 장애는 외부에서 보기에는 Outlook/Teams가 동시에 멈춘 사건처럼 보였지만, Microsoft가 공개한 예비 PIR을 보면 **네트워킹 게이트웨이** 한 계층이 광범위한 Microsoft 365 트래픽을 전면에서 받는 구조였고, 그 계층에서 연쇄 실패가 발생한 사건에 가깝습니다.[^1]

Microsoft 예비 PIR(Preliminary Post Incident Report)에 따르면 incident ID는 `EX1550543/MO1550821`이고, incident 시간은 **2026-11-12 16:20 UTC ~ 2026-11-13 16:10 UTC**로 정리되어 있습니다. 이는 KST 기준으로 **2026-11-13 01:20 ~ 2026-11-14 01:10**입니다(UTC+9).[^1]

AP 보도는 “11월 12일(목) 장애 시작 → 11월 14일(토)경 복구 공지” 흐름으로 사건을 전달했습니다. 운영자/사용자가 체감하는 관점에서는 ‘거의 이틀’로 기억될 수 있는 그림입니다.[^2]

예비 PIR이 다루는 영향 범위는 Exchange(Outlook)만이 아니라 Copilot, Teams, SharePoint, OneDrive, Defender, Purview, Intune 등 Microsoft 365 서비스 전반입니다. 다만 사용자 관점에서 가장 치명적인 1차 타격은 Exchange Online mailbox 접근과 메일 딜레이였습니다.[^1]

여기서 중요한 포인트는 “Outlook이 죽었다”가 아니라, 조직의 커뮤니케이션/업무 승인/일정/자동화가 한 묶음으로 묶여 있는 현실에서, SaaS 한 축이 흔들릴 때 업무가 어떻게 멈추는지입니다. 이번 글은 그걸 우리 서비스/조직 관점 체크리스트로 바꾸는 쪽에 초점을 둡니다.

## 네트워킹 게이트웨이: ‘앞단’이 무너지면 뒤는 멀쩡해도 소용없습니다

예비 PIR이 반복해서 지칭하는 구성요소는 “networking gateway that fronts many Microsoft 365 services”입니다. 문장 그대로 해석하면 Microsoft 365의 여러 서비스를 전면에서 받아주는 게이트웨이 계층입니다.[^1]

이런 계층이 가진 위험은 단순합니다.

- 내부적으로는 Exchange, Teams, SharePoint가 서로 다른 서비스/클러스터/데이터스토어를 쓰고 있어도
- 외부에서 들어오는 인증/세션/커넥션 협상, 라우팅이 한 계층을 통과해야 한다면
- **앞단이 막히는 순간, 뒤가 멀쩡해도 전체가 멈춘 것처럼 보입니다.**

이번 건에서 특히 눈에 띄는 대목은 “서비스들이 fail out할 수 있는가”입니다. 예비 PIR은 Teams/OneDrive/SharePoint/Office apps는 게이트웨이 장애 시 다른 경로로 fail out해 상대적으로 먼저 회복된 반면, Exchange Online은 “scale reasons”로 그 게이트웨이에서 fail out하지 못한다고 적고 있습니다. 이게 ‘메일은 최후까지 같이 죽는다’는 형태로 체감되는 이유입니다.[^1]

내가 이 문장을 읽고 든 생각은 한 가지였습니다.

- 우리 서비스에서 “이 기능은 다른 경로로 우회가 된다”라고 믿는 지점이 실제로는 “우회가 되지만 특정 핵심 기능은 우회 못한다”일 가능성이 있고
- 그 ‘특정 핵심 기능’이 조직 업무를 붙잡는 경우가 많다는 점입니다.

메일/캘린더는 조직의 거래·승인·계약·변경관리를 고정시키는 기본 레일이라, 여기가 SPOF가 되면 메신저가 살아 있어도 업무가 멈춥니다.

## 세 가지 조건이 겹친 방식: latent bug + 트래픽 변화 + 14% 용량 감소

Microsoft 예비 PIR의 Root Cause는 “세 가지 요인” 조합입니다.

1) **Latent defect**: 2026년 7월부터 배포되기 시작한 변경이 특정 부하 조건에서 lock contention을 유발했고, 내부 Windows 프로세스에서 CPU/메모리를 소진해 서버가 unresponsive가 되는 결함으로 이어졌다고 합니다. 테스트에서 못 잡은 이유로 “트래픽 믹스 / SKU(하드웨어 조합)가 랩과 달랐다”, 특히 더 많은 코어/신형 하드웨어에서 contention이 더 악화된다고 적었습니다.[^1]

2) **Surge in load (Teams failover)**: Microsoft 365 내부에서 두 개의 독립적이고 heterogeneous한 네트워크 게이트웨이 시스템을 운영한다고 설명하면서도, 사고 15시간 전 Teams 트래픽이 alternative gateway에서 primary gateway(Exchange Online도 지원)로 failover 되었다고 적습니다. 이로 인해 primary의 로드와 트래픽 패턴이 바뀌었습니다.[^1]

3) **Reduced capacity (~14%)**: 동시에 게이트웨이 서버 용량의 약 14%가 전날의 별도 이슈로 out of service 상태였다고 합니다. 단독으로는 헤드룸이 있어 영향이 없었지만, 위 두 조건과 결합되면서 결정타가 되었습니다.[^1]

이 조합이 무서운 이유는 “세 가지가 다 나쁘다”가 아니라, 각각은 현실에서 흔히 일어나는 사건이라는 점입니다.

- latent bug는 언제든 있습니다(특히 대규모/장기 운영에서).
- 서비스 간 failover는 정상 동작이고, 종종 더 나쁜 곳으로 넘어가기도 합니다.
- 14% 용량 감소는 대규모 fleet에서는 그 자체로는 종종 흡수 가능합니다.

그런데 이 세 개가 겹치면 “평소엔 잘 되던 것”이 “갑자기 전 세계가 죽는 것”으로 변합니다.

여기에 연쇄 실패를 키운 증폭 메커니즘이 붙었습니다.

- 서버가 연결성을 잃으면 트래픽 매니지먼트가 healthy endpoint로 자동 라우팅(평소 resiliency의 핵심)
- 그러나 이번에는 라우팅된 트래픽이 남은 endpoint에서도 동일한 문제를 유발해 server-to-server cascading failure
- 2시간 이내에 fleet 전체에서 80% 이상 서버가 unresponsive
- 원래는 capacity unit/region 단위로 bulkhead가 있어야 하는데, 별도의 문제로 partition 간 bulkhead가 cascading failure를 막지 못해 글로벌로 확산

이 내용은 예비 PIR에 비교적 직설적으로 적혀 있습니다.[^1]

SaaS 장애 분석을 할 때 자주 놓치는 부분이 바로 여기입니다.

- “버그가 있었다”는 결론은 누구나 말할 수 있고
- 실제로는 “자동 복원/자동 라우팅/자동 재시도”가 장애를 더 크게 만들기도 하며
- bulkhead가 설계 문서에만 있고 사고 순간에 작동하지 않으면, ‘지역 장애’는 ‘글로벌 장애’로 바뀝니다.

이번 사건은 네트워크 게이트웨이를 중심으로 이 패턴이 그대로 재현됐습니다.

## 복구가 길어진 이유: ‘기다리던 트래픽’과 ‘롤백 불능’이 함께 왔습니다

예비 PIR에서 복구가 지연된 이유로 읽히는 포인트는 크게 세 가지입니다.

첫째, “서버를 살리면 바로 또 죽는다” 문제입니다. 예비 PIR은 서버가 서비스로 돌아오자마자 기다리던 트래픽에 즉시 overwhelmed되어 다시 unresponsive가 되었다고 적습니다. 복구는 단순히 “재시작”이 아니라 “트래픽을 다시 먹여도 안 죽는 상태”를 만들어야 합니다.[^1]

둘째, 자동화된 복구 프로세스의 전제 붕괴입니다. “이 정도로 광범위하게 unresponsive인 상태”에서 서비스 복원을 하도록 자동 복구가 설계되어 있지 않았다고 합니다. (평시에는 일부 서버가 죽고 일부가 살아 있는 상태에서 자동 조치가 먹힙니다.)[^1]

셋째, 롤백/flight/feature flag가 통하지 않는 유형의 변경이었다는 점입니다. “수개월 전 latent bug”라는 특성 때문에 정상적인 롤백 경로로 빠르게 되돌리기 어려웠고, 엔지니어가 known good state로 되돌리는 업데이트를 만들어 서버 그룹 단위로 적용(예: region의 50%+)하면서 천천히 올렸다고 되어 있습니다.[^1]

이건 우리에게 꽤 불편한 시사점을 줍니다.

- 장애는 종종 “릴리스 직후”가 아니라 “몇 달 뒤 특정 조합”에서 터집니다.
- 그 시점에는 배포 파이프라인과 운영자 머릿속에서 변경이 사라져 있고
- 롤백은 기술적으로 가능하더라도 운영적으로 느립니다(데이터/프로토콜/상태가 이미 바뀐 뒤일 수 있음).

즉, SaaS 공급자가 아무리 성숙해도 ‘긴 장애’는 나올 수 있고, 우리는 그걸 0으로 만들 수 없습니다.

## SaaS 장애를 ‘업무 중단’으로 키우는 조직 내부 의존성

Microsoft 365 장애는 Microsoft의 문제였지만, “업무가 멈추는 방식”은 우리 문제입니다.

조직 내부에서 흔한 결합 지점은 대체로 다음 네 가지입니다.

1) 커뮤니케이션 채널 결합
- 공지(전체 메일) = Exchange
- 실시간 논의/회의 = Teams
- 장애 대응 브릿지 = Teams
- 온콜 호출 = Teams mention

Teams가 멀쩡하더라도 Exchange가 죽으면 공지가 막히고, Exchange가 멀쩡하더라도 Teams가 죽으면 브릿지가 막힙니다. 둘 다 같은 벤더/같은 IDP/같은 네트워크 게이트웨이 앞단을 공유한다면, “둘 중 하나”가 아니라 “둘 다”가 같이 흔들릴 수 있습니다.[^1]

2) 메일/캘린더를 업무 트랜잭션으로 쓰는 결합
- 승인 메일이 증빙
- 캘린더 invite가 변경관리
- 회의록 링크가 Teams/SharePoint

메일/캘린더가 멈추면 단지 소통이 막히는 게 아니라 변경이 멈춥니다.

3) 인증/토큰 계층 결합
- Microsoft Graph, Exchange API, Teams API, SharePoint API를 한 제품으로 묶어 쓰면서
- 토큰 갱신 실패가 각종 백오피스 잡, 알림, 워크플로 전체 장애로 확산

4) 재시도 폭주 결합
- SDK 기본 retry + 앱 레벨 retry + 큐 레벨 retry + 작업 스케줄러 retry가 중첩
- 장애 시점에 “우리도 모르게” 트래픽이 튀어, 회복을 더 늦춥니다.

이번 장애는 공급자 내부에서도 “자동 라우팅이 cascading failure를 증폭”했다고 적고 있습니다. 우리 쪽 클라이언트/통합 시스템도 똑같은 증폭기를 가질 수 있습니다.[^1]

이 블로그에서 예전에 다룬 [Cloudflare IAD 성능 이슈가 전 서비스 에러로 번지는 패턴](https://daewooki.github.io/posts/cloudflare-iad-incident-resilience/)도 결론은 비슷했습니다. 앞단 한 곳의 이상이 전체 장애로 번질 때, 기술적으로는 ‘캐스케이딩’이고 조직적으로는 ‘경계가 없다’가 본질입니다.

## 체크리스트 1: 대체 커뮤니케이션 채널을 ‘기술’이 아니라 ‘프로세스’로 만들기

대체 채널을 마련하는 건 Slack 계정을 파는 문제가 아닙니다. 장애 때 실제로 작동하는 프로세스로 만들려면 최소한 아래가 필요합니다.

### 1) Out-of-band 공지 채널: 벤더/IDP를 분리합니다

- 1순위: 지금 쓰는 협업툴과 **다른 벤더**(다른 auth, 다른 네트워크)를 씁니다.
- 2순위: 같은 벤더를 쓰더라도, 최소한 사내 IdP/SSO에만 걸려 있지 않은 계정 경로(비상 계정, break-glass)를 둡니다.

이번 Microsoft 365 장애는 “네트워크 게이트웨이” 앞단에서 광범위 영향이 났습니다. 같은 벤더에 공지/브릿지/온콜이 다 묶여 있으면, 장애 공지도 장애가 됩니다.[^1]

### 2) 장애 브릿지 역할을 사람/조직으로 고정합니다

장애 상황에서 채팅방이 없으면 보통 이렇게 됩니다.

- 누가 지휘하는지 모르고
- 같은 얘기가 여러 군데서 반복되고
- 의사결정이 분산됩니다.

내 경우에는 “브릿지 오너(Incident Commander) + 서기(Scribe) + 기술 담당(Ops/Dev) + 비즈니스 담당” 4개 역할을 아예 고정해 두는 편이 낫다고 봅니다. 런북이 없어도 역할만 고정되면 혼란이 크게 줄어듭니다.

런북 관점에서의 더 자세한 형태는 예전에 쓴 [AT&T 10DLC MMS 지연 장애와 앱 레이어 런북](https://daewooki.github.io/posts/att-10dlc-mms-delay-runbook/)의 구조를 그대로 가져오면 됩니다. 내용을 반복하지는 않지만, “장애를 기술 이벤트가 아니라 운영 이벤트로 다루는 양식”이 중요합니다.

### 3) 고객/외부 이해관계자 공지 경로를 분리합니다

내부 협업툴이 죽었을 때, 고객에게 공지할 채널까지 같이 죽는 경우가 많습니다.

- status page가 사내 SSO를 요구한다
- 공지 메일이 Exchange에만 묶여 있다
- 장애 공지가 “다음 주 뉴스레터”로 미뤄진다

이런 것들은 기술 문제가 아니라 준비 부족입니다.

## 체크리스트 2: 메일/캘린더 의존성 분해(업무 설계 차원)

메일/캘린더를 ‘소통 도구’로만 보면 대책이 얕아집니다. 현실에서는 메일/캘린더가 업무 상태 머신입니다.

### 1) 메일이 없으면 멈추는 업무를 식별합니다

- 결재/승인: “메일 회신 = 승인”
- 변경관리: “invite 수락 = 변경 승인”
- 계약/증빙: “메일 스레드 = 증빙”

여기서 중요한 건 “메일이 멈춰도 할 수 있는 대체 절차”가 아니라, “메일을 트랜잭션으로 쓰는 일을 줄이는 것”입니다.

예를 들면:

- 승인/변경관리를 Jira/ServiceNow 같은 단일 시스템으로 옮기고(메일은 알림)
- 알림은 여러 채널로 보내되, 결정 기록은 한 곳에만 남기는 쪽이 낫습니다.

메일은 전파에는 강하지만, 상태의 단일 진실 저장소로는 취약합니다.

### 2) 캘린더 기반 운영(온콜/점검/배포)을 분리합니다

온콜 교대, 점검 일정, 배포 캘린더가 Exchange에만 있으면, Exchange 장애가 곧 운영 장애입니다.

- 온콜 로테이션은 PagerDuty/Opsgenie 같은 전용 도구(또는 최소한 Git repo + CI로 생성)로 분리
- 배포 일정/변경 승인도 캘린더가 아닌 티켓 워크플로로 귀속

캘린더는 “보여주기”에는 편하지만 “운영의 근거”로 쓰면 사고 시점에 같이 무너집니다.

### 3) 외부 메일 송수신의 ‘큐 만료’ 리스크를 인지합니다

이번 사고에서 예비 PIR의 repair item 중 하나가 “delayed messages가 undeliverable로 반환되지 않도록 email delivery window를 연장했다”는 문장입니다. 즉, 큐/재시도/만료 시간 자체가 품질에 영향을 주는 문제였습니다.[^1]

SMTP 세계에서 4xx는 보통 “나중에 다시 시도”지만, 결국은 만료됩니다. Exchange Online에서도 NDR 코드로 `4.4.7 Message expired`가 문서화돼 있습니다.[^3]

이건 SaaS 장애 시에 다음 같은 형태로 조직을 공격합니다.

- 우리 조직은 “메일은 어차피 나중에 가겠지”라고 믿음
- 그런데 상대측(또는 우리 측) 큐 만료/재시도 정책에 따라 메일이 소실/반송
- 장애가 끝난 뒤에도 거래/승인/알림이 누락된 채로 남음

업무적으로는 ‘장애 시간’이 아니라 ‘장애 + 후속 누락 정리 시간’이 비용입니다.

## 체크리스트 3: BCP를 문서가 아니라 ‘작동하는 최소 시스템’으로 만들기

BCP는 보통 “두꺼운 문서”로 끝납니다. 장애 때 필요한 건 문서가 아니라 (1) 누가 결정하는지, (2) 어떤 업무를 중단할지, (3) 어떤 최소 운영을 유지할지입니다.

### 1) 업무를 3등급으로 나눕니다

- Tier 0: 안전/법무/재무/보안 사고 대응(멈추면 안 됨)
- Tier 1: 고객 영향 실시간 업무(부분 축소 운영)
- Tier 2: 내부 편의 업무(즉시 중단 가능)

SaaS 장애가 왔을 때, 전부를 살리려다 전부를 잃는 패턴이 흔합니다. 특히 커뮤니케이션이 죽으면 “계속 확인하느라” 트래픽/회의만 늘고 실작업이 줄어듭니다.

### 2) 장애 시나리오를 ‘벤더 이름’이 아니라 ‘기능 상실’로 씁니다

이번 사건은 Microsoft 365 장애였지만, 우리 입장에서는 다음과 같이 써야 재사용 가능합니다.

- Email access 불가
- Calendar scheduling 불가
- Chat/meeting 불가
- Files/Docs access 불가
- OAuth token 발급/갱신 불가
- SSO login 불가

벤더를 바꿔도 기능 상실은 반복됩니다.

### 3) Tabletop을 ‘연 1회’가 아니라 ‘분기 1회 30분’으로 쪼갭니다

긴 훈련은 잘 안 합니다. 대신 30분짜리로 쪼개서 다음만 확인해도 가치가 큽니다.

- out-of-band 채널로 5분 안에 전사 공지가 가능한가
- 장애 브릿지 역할이 즉시 세팅되는가
- Tier 0 업무가 무엇인지, 누가 중단 결정을 하는지 알고 있는가

내가 운영 조직에서 체감한 바는, 훈련은 “완벽한 절차”가 아니라 “당황하지 않는 근육”을 만듭니다.

## 체크리스트 4: 토큰/세션 재시도 폭주를 막는 구체 설계

이번 사건의 본체는 Microsoft 내부 게이트웨이였지만, 고객 조직에서도 비슷한 형태가 나옵니다.

- Outlook/Teams가 느려짐
- 사내 시스템이 Microsoft Graph/Exchange API 호출에 실패
- 백오피스 배치/알림/동기화가 retry storm을 일으킴
- 결과적으로 (1) 우리 쪽 리소스를 태우고, (2) 외부 API에 더 큰 부하를 주고, (3) 장애가 끝난 뒤에도 backlog가 폭발

여기서 대책은 추상적인 “재시도 잘 하자”가 아니라, 다음 네 가지를 동시에 만족해야 합니다.

### 1) Retry는 스택에서 한 군데만 합니다

AWS Well-Architected는 retry가 여러 레이어에서 중첩되면 retry storm이 된다고 명시적으로 경고합니다.[^4]

- HTTP client가 3회 retry
- SDK가 내부에서 3회 retry
- 작업 큐가 5회 retry

이런 조합은 실제로는 3×3×5가 되고, 타임아웃까지 합쳐지면 장애 시점에 폭발합니다.

내 기준은 단순합니다.

- 네트워크 레이어(Envoy/Ingress)에서 retry를 하면 앱에서는 최소화
- 앱에서 retry를 제어하려면 프록시/SDK retry는 끕니다.

### 2) Exponential backoff + jitter + 상한을 넣습니다

Graph API를 예로 들면, Microsoft는 throttling 시 `429`와 `Retry-After`를 돌려주며, 즉시 재시도하지 말고 `Retry-After`에 맞춰 backoff 하라고 가이드합니다.[^5]

Token 발급/갱신에서도 비슷합니다. MSAL.NET 문서에는 `client_credentials`에서 Entra ID가 `429 Too Many Requests`와 `Retry-After: 60`을 줄 수 있고, token caching이 잘못되면(혹은 캐시가 분산돼 있으면) 더 악화될 수 있다는 취지의 내용이 있습니다.[^6]

요지는 두 가지입니다.

- Retry-After가 있으면 무조건 존중
- 없으면 exponential backoff + jitter + 총 재시도 시간 상한

### 3) 토큰 갱신은 singleflight로 합칩니다

장애 때 제일 흔한 패턴이 이겁니다.

- access token 만료
- N개 워커가 동시에 token refresh
- refresh endpoint가 느려져 time out
- 다시 refresh

이걸 막는 최소 장치는 singleflight(동일 키의 작업은 한 번만 수행)입니다. token을 “각 요청이 알아서 갱신”하게 두면 장애에서 가장 먼저 무너집니다.

### 4) Retry budget / circuit breaker로 ‘재시도 총량’을 제한합니다

Envoy 문서에서도 retry를 너무 많이 허용하면 서비스가 retry 요청에 의해 overwhelmed될 수 있다고 적고, retry budget/circuit breaker로 concurrent retries를 제어하는 접근을 설명합니다.[^7]

이걸 애플리케이션 레벨에서 흉내 내면 이런 형태가 됩니다.

- 외부 의존성이 unhealthy일 때는 빠르게 실패(fail fast)
- 큐에 쌓지 말고, “지금은 실행하지 않는다”로 상태를 노출
- 관리자/사용자가 보고 판단할 수 있게 ‘정직한 실패’를 만든다

장애는 숨기면 길어지고, 드러내면 짧아집니다.

## 예제 코드: Microsoft 365 Service Health를 Graph로 끌어와 out-of-band 알림 만들기

이번 장애 때 반복된 불만 중 하나가 “Admin center도 느리고, status page도 장애 영향권이고, 결국 DownDetector만 본다”였습니다. 예비 PIR에서도 DownDetector 같은 3rd party 신고가 쌓였다고 언급합니다.[^8]

조직 입장에서 할 수 있는 가장 실용적인 일은, Microsoft 365 Service Health를 Graph API로 긁어다가 **우리 쪽 out-of-band 채널**(예: Slack/Discord/SMS/전화 트리)에 뿌리는 것입니다.

Microsoft Graph에는 service communications API가 있고, 특정 issue의 PIR 문서를 내려받는 `incidentReport` API도 있습니다.[^9]

아래는 “특정 incident ID(EX1550543/MO1550821 같은)를 주기적으로 조회해 상태 변경 시 Webhook으로 쏘는” 최소 구현입니다.

### 동작 조건

- Node.js 20+ (내장 fetch 사용)
- Entra ID App registration (Application permission: `ServiceHealth.Read.All`)
- Webhook URL(벤더 독립적인 걸 권장)

### 1) 파일: `m365-health-watch.js`

```js
#!/usr/bin/env node

// Node.js 20+
// 목적: Graph의 /admin/serviceAnnouncement/issues/{id}를 조회해 상태 변경을 webhook으로 알림

import fs from 'node:fs/promises';
import crypto from 'node:crypto';

const {
  TENANT_ID,
  CLIENT_ID,
  CLIENT_SECRET,
  WEBHOOK_URL,
  ISSUE_IDS = 'EX1550543,MO1550821',
  STATE_FILE = './.m365-health-state.json',
} = process.env;

if (!TENANT_ID || !CLIENT_ID || !CLIENT_SECRET || !WEBHOOK_URL) {
  console.error('Missing env. Need TENANT_ID, CLIENT_ID, CLIENT_SECRET, WEBHOOK_URL');
  process.exit(1);
}

const issueIds = ISSUE_IDS.split(',').map(s => s.trim()).filter(Boolean);

async function getAccessToken() {
  const url = `https://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token`;
  const body = new URLSearchParams({
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
    grant_type: 'client_credentials',
    scope: 'https://graph.microsoft.com/.default',
  });

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`token failed: ${res.status} ${text}`);
  }

  const json = await res.json();
  return json.access_token;
}

async function graphGet(path, token) {
  const res = await fetch(`https://graph.microsoft.com/v1.0${path}`, {
    headers: {
      authorization: `Bearer ${token}`,
      accept: 'application/json',
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`graph GET ${path} failed: ${res.status} ${text}`);
  }

  return res.json();
}

async function maybeDownloadPIR(issueId, token) {
  // PIR 문서는 Stream으로 내려옵니다.
  // 문서가 없으면(아직 PIR 미발행) 에러가 납니다.
  const url = `https://graph.microsoft.com/v1.0/admin/serviceAnnouncement/issues/${issueId}/incidentReport`;
  const res = await fetch(url, {
    headers: { authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    return null;
  }

  const buf = Buffer.from(await res.arrayBuffer());
  const sha = crypto.createHash('sha256').update(buf).digest('hex').slice(0, 12);
  const out = `./pir-${issueId}-${sha}.bin`;
  await fs.writeFile(out, buf);
  return out;
}

async function postWebhook(payload) {
  const res = await fetch(WEBHOOK_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`webhook failed: ${res.status} ${text}`);
  }
}

async function loadState() {
  try {
    const raw = await fs.readFile(STATE_FILE, 'utf-8');
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

async function saveState(state) {
  await fs.writeFile(STATE_FILE, JSON.stringify(state, null, 2));
}

function pickImportantFields(issue) {
  // serviceHealthIssue 모델은 테넌트/상황별로 필드가 조금씩 달라질 수 있습니다.
  return {
    id: issue.id,
    service: issue.service,
    status: issue.status,
    classification: issue.classification,
    feature: issue.feature,
    featureGroup: issue.featureGroup,
    startDateTime: issue.startDateTime,
    lastModifiedDateTime: issue.lastModifiedDateTime,
    impactDescription: issue.impactDescription,
  };
}

async function main() {
  const token = await getAccessToken();
  const prev = await loadState();
  const next = { ...prev };

  for (const id of issueIds) {
    const issue = await graphGet(`/admin/serviceAnnouncement/issues/${id}`, token);
    const important = pickImportantFields(issue);

    const prevHash = prev[id]?.hash;
    const currHash = crypto.createHash('sha256').update(JSON.stringify(important)).digest('hex');

    if (prevHash !== currHash) {
      let pirPath = null;
      try {
        pirPath = await maybeDownloadPIR(id, token);
      } catch {
        // ignore
      }

      await postWebhook({
        text: `M365 Service Health changed: ${id}`,
        issue: important,
        pirDownloadedTo: pirPath,
      });

      next[id] = { hash: currHash, last: important, pirDownloadedTo: pirPath, changedAt: new Date().toISOString() };
      console.log(`changed: ${id}`);
    } else {
      console.log(`no change: ${id}`);
    }
  }

  await saveState(next);
}

main().catch(err => {
  console.error(err);
  process.exit(2);
});
```

### 2) 실행 방법

```bash
node -v
# v20.x 이상 확인

export TENANT_ID='...'
export CLIENT_ID='...'
export CLIENT_SECRET='...'
export WEBHOOK_URL='https://.../webhook'
export ISSUE_IDS='EX1550543,MO1550821'

node m365-health-watch.js
```

예상 출력은 이런 형태입니다.

```text
changed: EX1550543
no change: MO1550821
```

여기서 핵심은 “Microsoft 365가 멈추는 날에도, 우리 조직의 장애 공지 파이프라인은 멈추지 않게” 만드는 것입니다. Microsoft Learn 문서에서도 Service health는 admin center에서 확인하고, tenant에 영향을 주는 incident 알림을 이메일로 받을 수 있다고 안내합니다. 다만 이메일은 이번처럼 Exchange가 흔들릴 때 같이 흔들릴 수 있으니, out-of-band가 필요합니다.[^10]

## 반론과 회의론: 그래도 현실적인 한계는 남습니다

### “SaaS는 어차피 못 막는다”

맞습니다. 못 막습니다. 이번 사건도 결국 Microsoft 내부 게이트웨이/서버 결함/트래픽 패턴/용량 감소가 결합된 문제였고, 고객이 할 수 있는 건 제한적입니다.[^1]

그런데 우리가 막아야 하는 건 “SaaS 장애”가 아니라 “업무 중단으로 번지는 방식”입니다. 이 차이를 구분하지 않으면 대책은 항상 무의미해집니다.

### “대체 채널도 결국 SSO면 같이 죽는다”

맞습니다. 그래서 채널만 분리하면 반쪽짜리입니다.

- 벤더 분리
- 계정/인증 경로 분리
- 최소한의 break-glass 운영

여기까지 들어가야 장애 때 작동합니다.

### “메일/캘린더를 끊을 수는 없다”

끊을 수 없습니다. 다만 ‘메일이 곧 승인/변경관리’인 구조는 줄일 수 있습니다.

이번 예비 PIR이 보여준 것처럼, 어떤 서비스는 fail out되지만 Exchange는 fail out되지 못할 수 있습니다. 그러면 메일/캘린더를 상태 머신으로 쓰는 조직은 가장 늦게 회복합니다.[^1]

## 앞으로 지켜볼 것: 최종 PIR에서 확인해야 할 질문

예비 PIR은 “preliminary이며 변경될 수 있고, 최종 PIR이 5 business days 내 제공된다”고 밝히고 있습니다.[^1]

또한 예비 PIR의 Mitigation/Repair Items 테이블에는 “comprehensive list of repair items”가 **2026-11-20**에 제공될 것이라고 적혀 있습니다.[^1]

최종 PIR에서 내가 확인하고 싶은 질문은 다음입니다.

1) bulkhead가 막지 못한 “separate issue”는 무엇이었나
- 설계상 partition 격리가 있었는데 왜 무력화됐는지
- 재발 방지는 “설정 수정”인지 “아키텍처 변경”인지

2) load testing이 high-core/new hardware에서 취약했던 이유
- 테스트 SKU 선정 기준
- traffic mix/SKU mix를 prod와 맞추는 체계

3) Exchange Online이 fail out 못 하는 구조가 장기적으로 유지되는가
- scale reasons의 구체적 의미
- 고객이 취할 수 있는 우회(예: 하이브리드, 서드파티 continuity 서비스)의 현실성

4) 회복 단계에서 “기다리던 트래픽”을 다루는 표준 절차
- 트래픽 재유입 제어
- backlog drain 전략

이런 질문의 답이 나와야, “큰 회사도 장애는 난다” 수준을 넘어서 우리가 배울 수 있는 내용이 생깁니다.

한편 운영 자동화 관점에서는, PIR이 발행되었는지 여부 자체도 Graph API로 확인 가능합니다. `incidentReport` API는 issue 상태가 `PostIncidentReviewPublished`일 때 PIR이 존재한다고 설명합니다. 즉, PIR 발행을 감시하고 조직 내부에 자동 배포하는 것도 가능합니다.[^11]

## 지금 할 수 있는 일: ‘다음 장애’에 바로 쓰는 체크리스트

아래는 내가 이번 사건을 우리 조직 관점으로 번역하면서 만든 실행 체크리스트입니다.

### A. 커뮤니케이션/지휘

- [ ] out-of-band 공지 채널이 있고, 벤더/인증이 분리돼 있습니다.
- [ ] 장애 브릿지(전화/회의) 개설 방법이 문서가 아니라 “1분 안에 실행”으로 검증돼 있습니다.
- [ ] Incident Commander/Scribe 역할이 지정돼 있고, 교대 규칙이 있습니다.

### B. 업무 설계(메일/캘린더)

- [ ] “메일 회신 = 승인”인 업무를 목록화했고, 시스템 승인으로 옮길 계획이 있습니다.
- [ ] 배포/변경관리의 근거가 캘린더가 아니라 티켓에 남습니다.
- [ ] 외부 메일 지연/만료 리스크(`4.4.7`)를 이해하고, 중요 알림은 다중 채널입니다.[^3]

### C. 통합/자동화(토큰/세션)

- [ ] token refresh는 singleflight/central broker로 합쳐져 있습니다.
- [ ] Retry-After 존중 + backoff/jitter + 재시도 상한이 적용돼 있습니다.[^5]
- [ ] retry는 스택에서 한 레이어만 담당합니다.

### D. 게이트웨이/프록시 레이어(서비스 보호)

- [ ] upstream retry budget/circuit breaker가 설정돼 있습니다(Envoy 등).[^7]
- [ ] 장애 시 외부 의존성 호출을 줄이는 kill switch(기능 플래그)가 있습니다.

### E. 관측/알림

- [ ] Microsoft 365 Service Health를 Graph로 받아 우리 알림 시스템으로 라우팅합니다.[^9]
- [ ] 알림 자체가 Exchange/Teams에만 의존하지 않습니다.

이 체크리스트는 “Microsoft 365 장애를 막자”가 아니라, “Microsoft 365 같은 거대 SaaS의 장애가 우리 조직의 멈춤으로 번역되는 과정을 끊자”에 초점이 있습니다.

## 결론: SPOF는 벤더가 아니라 의존성 묶음에서 생깁니다

이번 사건의 기술적 트리거는 latent bug, Teams 트래픽 failover, 14% 용량 감소, bulkhead 실패 같은 조합이었지만, 조직 입장에서 더 중요한 교훈은 “메일/캘린더/채팅/회의/자동화/온콜이 같은 묶음으로 결합돼 있으면, 앞단 한 번의 실패가 업무 전체를 정지시킨다”는 사실입니다.[^1]

## 참고 자료

- [AP: Is Outlook down? Widespread outage hits Microsoft apps](https://apnews.com/article/6376045281feb430c0b923e3a4b251c2)
- [AP: Microsoft says services fully restored after hourslong global outage](https://apnews.com/article/ca395c0f1e51af784b6d70afb6554f6a)
- [Ars Technica: Three small failures combined to take down Microsoft 365](https://arstechnica.com/gadgets/2026/11/microsoft-details-how-three-problems-combined-for-a-global-outage/)
- [Microsoft 365 예비 PIR (공개 미러 PDF)](https://www.365fanatic.com/wp-content/uploads/2026/11/postincidentreport.pdf)
- [Microsoft Graph: Get serviceHealthIssue (v1.0)](https://learn.microsoft.com/en-us/graph/api/servicehealthissue-get?view=graph-rest-1.0)
- [Microsoft Graph: serviceHealthIssue incidentReport (v1.0)](https://learn.microsoft.com/en-us/graph/api/servicehealthissue-incidentreport?view=graph-rest-1.0)
- [Microsoft Graph: Service communications API overview](https://learn.microsoft.com/en-us/graph/api/resources/service-communications-api-overview?view=graph-rest-beta)
- [Microsoft Graph throttling guidance](https://learn.microsoft.com/en-us/graph/throttling)
- [MSAL.NET: Understanding client and server throttling](https://learn.microsoft.com/en-us/entra/msal/dotnet/advanced/client-and-server-throttling)
- [Exchange Online: Email nondelivery reports (NDRs) and SMTP errors](https://learn.microsoft.com/en-us/troubleshoot/exchange/email-delivery/ndr/non-delivery-reports-in-exchange-online)
- [Envoy: How do I handle transient failures? (retry budget / circuit breaker)](https://www.envoyproxy.io/docs/envoy/v1.40.1/faq/load_balancing/transient_failures)
- [AWS Well-Architected: Control and limit retry calls (REL05-BP03)](https://docs.aws.amazon.com/wellarchitected/2023-04-10/framework/rel_mitigate_interaction_failure_limit_retries.html)

[^1]: <https://www.365fanatic.com/wp-content/uploads/2026/11/postincidentreport.pdf>
[^2]: <https://apnews.com/article/microsoft-outlook-outage-email-teams-6376045281feb430c0b923e3a4b251c2>
[^3]: <https://learn.microsoft.com/en-us/troubleshoot/exchange/email-delivery/ndr/non-delivery-reports-in-exchange-online>
[^4]: <https://docs.aws.amazon.com/wellarchitected/2023-04-10/framework/rel_mitigate_interaction_failure_limit_retries.html>
[^5]: <https://learn.microsoft.com/en-us/graph/throttling>
[^6]: <https://learn.microsoft.com/en-us/entra/msal/dotnet/advanced/client-and-server-throttling>
[^7]: <https://www.envoyproxy.io/docs/envoy/v1.40.1/faq/load_balancing/transient_failures>
[^8]: <https://www.365fanatic.com/wp-content/uploads/2026/11/PostIncidentReport.pdf>
[^9]: <https://learn.microsoft.com/en-us/graph/api/resources/service-communications-api-overview?preserve-view=true&view=graph-rest-beta>
[^10]: <https://learn.microsoft.com/en-us/microsoft-365/enterprise/view-service-health?trk=public_post_comment-text&view=o365-worldwide>
[^11]: <https://learn.microsoft.com/en-us/graph/api/servicehealthissue-incidentreport?view=graph-rest-1.0>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
