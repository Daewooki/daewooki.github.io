---
title: "Cloudflare 인증서 프로비저닝 장애가 운영 장애로 번지는 경로"
description: "인증서 발급·배포 지연은 평소엔 안 보이지만 온보딩·갱신·배포·모니터링을 동시에 무너뜨리는 숨은 의존성입니다."
date: 2026-11-12 12:41:22 +0900
categories: ["News", "Cloud"]
tags: ["cloudflare", "tls", "certificate-provisioning", "acme", "runbook", "monitoring"]
render_with_liquid: false
---

## 사건: “배포가 안 되는” 2시간 22분이 남기는 것

Cloudflare 상태 이력에 **‘SSL Certificate Provisioning Issue’**가 2026-11-11(UTC)로 기록되어 있습니다. 공식 incident 페이지 기준으로 시작 시각은 2026-11-11 07:45 UTC, 종료 시각은 10:07 UTC, 총 2시간 22분입니다. 해당 업데이트에는 “subset of Custom certificates를 deploying 하는 과정에 문제가 있어 조사 중이며, 해결될 때까지 certificate redeployments를 잠시 멈추라”는 안내가 포함되어 있습니다. 또한 “이미 production에 있는 SSL certificates는 영향이 없고 정상 동작한다”는 문장도 함께 있습니다. [Cloudflare incident 페이지](https://www.cloudflarestatus.com/incidents/21vwp89eiyjx)

KST(UTC+9)로 환산하면 2026-11-11 16:45 KST부터 19:07 KST까지입니다. 사용자가 2026-11-12 KST 기준으로 보고 있는 상황이라면, 이 장애는 바로 전날 저녁에 끝난 셈입니다.

여기서 중요한 포인트는 “Cloudflare 장애”가 아니라 “인증서 프로비저닝 레이어 장애”라는 점입니다. CDN이 죽어서 5xx가 터지는 종류와 달리, 인증서 레이어는 대부분의 요청이 정상인 상태로도 시스템을 천천히 무너뜨릴 수 있습니다. 즉시 영향은 없다고 느끼다가, 다음과 같은 지점에서 운영이 먼저 깨집니다.

- 신규 도메인/서브도메인 온보딩이 멈추거나 SLA를 어긴다.
- 자동 갱신이 실패했는데 눈치채지 못하고, 만료 시각에 맞춰 장애가 폭발한다.
- 배포/롤백이 인증서 상태 머신에 걸려서 change freeze가 길어진다.
- 모니터링이 “만료 임박”만 보고 있어서, “발급/배포 대기열”이 길어지는 징후를 놓친다.

이번 incident 문구가 딱 “redeployments를 멈추라”고 말하는 것도 그 맥락입니다. 인증서 시스템에서 redeploy는 보통 “재시도 버튼”이 아니라 “대기열을 더 쌓는 버튼”이 되는 순간이 있습니다.

## 인증서 프로비저닝을 ‘발급’과 ‘배포’로 갈라서 봐야 하는 이유

운영 관점에서 인증서 흐름을 단순화하면 다음 두 단계를 분리해서 보는 게 안전합니다.

1) Issuance (CA가 서명한 cert를 만드는 단계)
- DCV(Domain Control Validation) 성공 여부, CAA, ACME challenge, delegation 등과 엮입니다.

2) Deployment (Cloudflare edge에 cert를 전개하는 단계)
- “발급은 됐는데 edge에서 안 보인다”, “일부 PoP에서만 늦다”, “priority 규칙 때문에 다른 cert가 서빙된다” 같은 운영 함정이 여기서 터집니다.

Cloudflare 문서도 이 관점을 강하게 깔고 있습니다. Certificate status는 Initializing → Pending Validation → Pending Issuance → Pending Deployment → Active 순으로 바뀐다고 명시돼 있습니다. 즉, Pending Deployment는 “발급이 끝났는데 edge 전개가 안 끝난 상태”를 뜻하는 자리입니다. [Certificate statuses](https://developers.cloudflare.com/ssl/reference/certificate-statuses/)

게다가 Cloudflare는 Universal SSL 같은 Cloudflare-managed cert에 대해 “renewal 시도는 auto renewal period부터 시작해서 만료 24시간 전까지 계속되며, 실패하더라도 다른 valid cert가 있으면 마지막 24시간 내에 그 cert로 전개한다”는 식의 fallback 정책을 설명합니다. 이 얘기는 반대로 말하면, 배포 파이프라인이 흔들릴 때 운영팀이 보기엔 정상처럼 보일 수 있다는 뜻입니다. [Validity periods and renewal](https://developers.cloudflare.com/ssl/reference/certificate-validity-periods/)

이번 incident의 문구가 “deploying a subset”을 직접 언급한 것도, 이 이벤트가 issuance 자체(예: DCV/CA 서명)보다 deployment 쪽에 가까운 문제였을 가능성을 시사합니다. 다만 Cloudflare가 공개한 내용만으로는 root cause를 확정할 수는 없습니다. 상태 페이지는 symptom 위주이고, 대기열/실패율/영향 범위가 수치로 제공되지 않는 경우가 많습니다.

## 연쇄 실패 1) 신규 도메인 온보딩: “TLS ready”가 온보딩 파이프라인의 gate가 될 때

신규 온보딩은 대개 다음 중 하나의 형태입니다.

- (A) Zone 단위: 새 zone 추가 후 Universal SSL 또는 Advanced Certificate Manager(ACM) cert가 Active가 될 때까지 기다렸다가 프록시 전환
- (B) Custom certificate 업로드: EV/OV, 특정 CA 사용 요구 등으로 직접 업로드
- (C) Cloudflare for SaaS: Custom Hostnames에 고객 도메인을 붙이고 SSL for SaaS가 cert lifecycle을 처리

각 모델은 “인증서 프로비저닝 지연”에 대한 실패 모양이 다릅니다.

### Zone + Universal SSL
Cloudflare 문서는 partial(CNAME) setup에서 Universal SSL이 “DNS record가 proxied 되었을 때 provision되며, DCV record를 넣지 않으면 brief downtime 이후 validate될 수 있다”는 식으로 설명합니다. 온보딩에서 ‘프록시를 켜는 순간’이 인증서 플로우를 트리거한다는 뜻이고, provisioning 지연 시에는 “프록시를 켰는데 브라우저에 TLS 에러가 뜬다”로 체감됩니다. [Enable Universal SSL certificates](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/enable-universal-ssl/)

운영적으로 문제는 여기서부터입니다.

- 온보딩 자동화가 “프록시 켜기 → 5분 대기 → health check” 같은 고정 타이머를 갖고 있으면, provisioning backlog가 생기는 날에 false failure가 폭증합니다.
- 실패 처리(rollback)가 “프록시 끄기”로 설계되어 있으면, 다음 재시도 때 다시 provisioning을 재트리거해서 backlog를 키웁니다.

### Custom certificates
Cloudflare 문서는 Custom certificates를 쓰면 issuance/renewal은 Cloudflare가 관리하지 않으며 사용자가 직접 만료를 모니터링해야 한다고 못 박습니다. 즉, 운영팀의 책임 범위가 넓어집니다. [Custom certificates](https://developers.cloudflare.com/ssl/edge-certificates/custom-certificates/)

이번 incident처럼 “Custom certificates 배포”가 막히면 신규 도메인 온보딩은 다음 경로로 죽습니다.

- 새 cert 업로드/교체는 성공했는데 status가 Pending Deployment에 붙는다.
- 고객 트래픽 전환 시점이 다가오는데 Active가 안 된다.
- 온보딩을 늦추거나, 임시로 Universal SSL에 기대거나(가능하면), 최악은 무인증서 상태로 공개된다.

여기서 자주 나오는 착각이 “업로드는 됐으니까 끝”입니다. Cloudflare API 모델에도 pending_deployment, deployment_timed_out 같은 상태가 명시돼 있고, 만약 이 상태를 모니터링하지 않으면 온보딩 SLA는 인증서 레이어에서 먼저 깨집니다. [Certificate Packs API](https://developers.cloudflare.com/api/resources/ssl/subresources/certificate_packs/)

### Cloudflare for SaaS (Custom Hostnames)
Cloudflare 문서가 가장 명확하게 말하는 부분이 하나 있습니다. Custom hostname은 준비 완료 판단을 “hostname activation status == active AND ssl.status == active AND customer DNS가 SaaS target을 가리킴”까지 묶어서 보라고 합니다. 즉, ‘도메인 연결 완료’의 정의가 인증서 상태 머신을 포함합니다. [Certificate statuses](https://developers.cloudflare.com/ssl/reference/certificate-statuses/)

따라서 provisioning 장애는 SaaS 온보딩에서 곧바로 전면 장애로 전파됩니다.

- 고객이 CNAME은 넣었는데 ssl.status가 pending_deployment에 멈춘다.
- 고객은 앱이 죽었다고 신고한다(사실은 cert가 없다).
- 서포트팀은 앱 로그를 뒤지다가 시간을 버린다(사실은 edge cert가 없다).

내 경우, 이런 유형의 장애는 인프라 팀이 아니라 “온보딩 자동화 + 서포트”가 먼저 붕괴합니다. 장애의 첫 신호가 Sentry가 아니라 Zendesk/Intercom으로 들어오는 게 특징입니다.

## 연쇄 실패 2) 자동 갱신: “갱신 실패”가 장애로 보이지 않는 구간이 길다

Cloudflare-managed cert(Universal SSL, ACM 등)는 자동 갱신이 돌아가고, Universal SSL은 90-day validity에 30일 전부터 renewal을 시도한다고 문서화돼 있습니다. [Validity periods and renewal](https://developers.cloudflare.com/ssl/reference/certificate-validity-periods/)

문제는 이 자동화가 운영자에게 두 가지 착시를 준다는 점입니다.

1) 평소에는 신경을 안 쓴다.
- “Cloudflare가 알아서 해준다”는 심리가 생기고, 만료 모니터링이 약해집니다.

2) 실패해도 트래픽이 멀쩡해 보인다.
- 문서에 따르면, 어떤 cert가 실패하더라도 동일 hostname에 다른 valid cert가 있으면 마지막 24시간에 그 cert를 deploy할 수 있습니다. 이 fallback이 오히려 “갱신 실패를 늦게 발견”하게 만들 수 있습니다. [Validity periods and renewal](https://developers.cloudflare.com/ssl/reference/certificate-validity-periods/)

그리고 이번 incident처럼 provisioning(deployment) 레이어가 흔들리면, renewal은 다음 모양으로 연쇄 실패합니다.

- CA 서명 자체는 받아왔는데 Pending Deployment에서 막힌다.
- 기존 cert는 아직 유효하므로 외부 트래픽은 정상이다.
- 운영자는 아무도 모른다.
- 만료 D-1에 “deploy할 valid cert”가 사실상 없거나, 배포가 계속 밀리면 그때 장애가 폭발한다.

즉, 인증서 장애는 “현재 요청 에러율”로는 잘 안 잡히고 “시간에 따른 폭탄”이 됩니다.

여기서 더 위험한 케이스는 Custom certificates입니다. Cloudflare는 Custom certificates에 대해 사용자가 직접 만료를 모니터링해야 한다고 말합니다. 이건 “자동 갱신 실패”가 아니라 “갱신 자체가 없다”는 구조입니다. provisioning 장애가 겹치면, 교체 배포가 늦어지는 동안 old cert 만료 시점이 다가오는 레이스 컨디션이 됩니다. [Custom certificates](https://developers.cloudflare.com/ssl/edge-certificates/custom-certificates/)

## 연쇄 실패 3) 배포/롤백: 상태 머신을 모르고 버튼을 누르면 더 망가진다

인증서 배포는 변경 관리(change management)와 직접 연결됩니다. 특히 ACM rotation이나 custom cert 교체는 “새 cert가 Active가 될 때까지 old cert를 지우지 말라”는 원칙이 있고, Cloudflare도 동일한 원칙을 문서로 강제합니다. [Rotate ACM certificate packs](https://developers.cloudflare.com/ssl/reference/certificate-rotation/)

여기서 provisioning 장애가 나면 다음 문제가 연달아 생깁니다.

### (1) “새 팩 생성 + old 팩 유지” 전략이 멈춘다
ACM은 in-place update가 아니라 새 pack을 만들고 Active를 기다린 뒤 old pack을 삭제하라고 합니다. 그런데 Pending Deployment가 장시간 지속되면, Active까지 못 가서 old pack을 계속 끌고 가야 합니다. 이 기간 동안:

- 새 hostnames 추가 온보딩이 지연되고
- 인증서 quota/팩 한도에 걸릴 수 있고
- change window가 길어집니다

### (2) rollout 중간에 rollback을 시도하면 대기열이 불어난다
이번 incident가 “redeployments를 pause 하라”고 한 이유가 여기로 해석됩니다. deployment 파이프라인이 막혀 있을 때 재배포/재시도는 종종:

- 같은 작업을 중복 enqueue
- 우선순위를 뒤집거나
- 상태를 재초기화

하는 방향으로 작동합니다. 외부에서 보면 “버튼 몇 번 눌렀는데 더 늦어진다”가 됩니다.

### (3) Pending Cleanup이 의미하는 것
Cloudflare는 cert replacement 시 Pending Cleanup을 언급합니다. old cert가 새 cert가 성공적으로 issued/activated 될 때까지 삭제되지 않는다고 설명합니다. 이건 운영자 입장에서는 안전장치입니다. 그런데 provisioning 장애로 새 cert가 Active로 못 가면, old cert는 살아있어서 서비스는 정상이고, 운영자는 문제를 더 늦게 알아차릴 수 있습니다. [Certificate statuses](https://developers.cloudflare.com/ssl/reference/certificate-statuses/)

### (4) Enterprise에서 staging environment의 가치가 커진다
Cloudflare는 Enterprise 고객에게 staging environment(beta)를 제공하며, custom (modern) certificate를 staging에 올리고 curl --resolve로 edge 테스트한 뒤 production으로 push하라고 안내합니다. 더 중요한 문장은 “production에 올렸다가 문제가 생기면 deactivate로 edge에서 제거하고 staging으로 다시 밀어 넣어 추가 테스트가 가능하다”입니다. 이건 인증서 변경을 애초에 ‘배포’로 취급한다는 뜻입니다. [Staging environment](https://developers.cloudflare.com/ssl/edge-certificates/staging-environment/)

이번처럼 deployment 레이어가 흔들리는 사건을 겪으면, 인증서도 애플리케이션처럼 staging → production → rollback이 필요하다는 결론으로 수렴합니다.

## 연쇄 실패 4) 모니터링과 알림: “만료 임박”만 보면 이미 늦다

인증서 운영 모니터링을 흔히 “expires_on만 체크”로 끝냅니다. 그런데 provisioning 장애의 핵심은 expires_on이 아니라 status입니다.

Cloudflare는 certificate pack과 custom hostname에 대해 status enum을 매우 상세하게 제공합니다. pending_validation, pending_issuance, pending_deployment뿐 아니라 issuance_timed_out, deployment_timed_out, holding_deployment 같은 운영용 상태가 존재합니다. [SSL API 모델](https://developers.cloudflare.com/api/resources/ssl/)와 [Custom Hostnames API](https://developers.cloudflare.com/api/go/resources/custom_hostnames/methods/create/)에서 이를 확인할 수 있습니다.

따라서 모니터링은 최소한 다음 3축으로 나뉘어야 합니다.

1) Expiration axis: expires_on이 가까운가
- 특히 Custom certificates는 Cloudflare가 renewal을 안 해줍니다. [Custom certificates](https://developers.cloudflare.com/ssl/edge-certificates/custom-certificates/)

2) Provisioning axis: status가 Active로 수렴하는가
- pending_deployment가 N분 이상이면 이상징후
- *_timed_out 상태는 즉시 incident급으로 분류

3) Validation axis: DCV token이 stale/expired 되었는가
- Cloudflare for SaaS 문서에서 DCV token 유효기간(예: Let’s Encrypt 7일, Google Trust Services/SSL.com 14일)을 직접 언급하며, stale/expired 시 PATCH로 recheck를 트리거하라고 안내합니다. [Troubleshooting (Cloudflare for SaaS)](https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/security/certificate-management/issue-and-validate/validate-certificates/troubleshooting/)

여기에 하나를 더 얹으면 status page 신호입니다.

Cloudflare는 HTML을 스크래핑하지 말고 Status API를 쓰라고 공식적으로 가이드합니다. summary.json, incidents.json, unresolved.json 같은 endpoint가 있고 User-Agent를 명시하라는 운영 지침도 들어 있습니다. [Cloudflare Status API](https://www.cloudflarestatus.com/api)

또한 Cloudflare는 상태 페이지 incident alert를 Cloudflare Notifications로 받을 수 있다고 설명합니다. RSS/Atom도 제공합니다. [Cloudflare Status (Support docs)](https://developers.cloudflare.com/support/cloudflare-status/)

알림 설계에서 중요한 건, “Cloudflare incident가 떴다” 자체가 아니라 “우리 조직이 지금 무엇을 하고 있었는가”를 연결하는 것입니다.

- 지금 신규 온보딩이 진행 중인가
- 지금 cert rotation(change)이 진행 중인가
- 지금 custom hostname을 대량 생성하고 있는가

이걸 연결하지 않으면, status page는 단순 참고 정보로 끝나고 피해는 줄지 않습니다.

## 장애 중 런북: 멈춰야 하는 작업과 계속해야 하는 작업

Cloudflare incident 본문 자체가 “pause certificate redeployments”를 권고했으니, 런북의 1번은 그 문장을 그대로 실행하는 것입니다. [Cloudflare incident 페이지](https://www.cloudflarestatus.com/incidents/21vwp89eiyjx)

다만 운영에서 redeploy의 의미가 서비스마다 다릅니다. 나는 다음처럼 분류합니다.

### 즉시 멈추는 것(대기열/상태 머신을 더 망가뜨릴 가능성이 큰 작업)

- Custom certificate 교체(Replace) 반복 실행
- ACM certificate pack rotation(새 pack 주문/old pack 삭제)
- Cloudflare for SaaS에서 custom hostname 대량 생성/수정(특히 ssl.method 변경)
- Universal SSL을 껐다 켜는 식의 강제 재발급 트리거(환경마다 다르지만 결과적으로 provisioning 작업을 더 생성할 가능성이 큼)

### 계속하는 것(영향을 제한하고, 상황 가시성을 높이는 작업)

- Status API 구독 및 incident 업데이트 추적
- 우리 계정/zone에서 pending_* 상태 객체 수량 집계(증가율 포함)
- 만료 D-30/D-7 임계 구간 객체 목록 고정(snapshot) 및 교체 우선순위 재정렬
- 고객 커뮤니케이션 템플릿 가동(특히 SaaS custom domain 제공하는 경우)

“멈춘다/계속한다”를 나누지 않으면, 장애 상황에서 가장 흔한 행동은 “뭔가를 눌러서 해결하려고 시도”이고, 이게 인증서 쪽에서는 실제로는 더 악화시키는 방향으로 가기 쉽습니다.

이 패턴은 이전에 정리했던 ‘Cloudflare IAD 성능 이슈가 전 서비스 에러로 번지는 패턴’에서도 비슷한 결로 나타났는데, 이번 건은 HTTP 에러가 아니라 운영 플로우가 먼저 무너진다는 차이가 있습니다. [Cloudflare IAD 성능 이슈가 전 서비스 에러로 번지는 패턴](https://daewooki.github.io/posts/cloudflare-iad-incident-resilience/)

## 운영 분해: ACME/Custom/Keyless/SSL for SaaS가 한 번에 흔들리는 지점

인증서 레이어 장애를 크게 보면 “어떤 종류의 certificate object가 영향을 받았는가”로 나눌 수 있습니다.

### ACME(DNS-01) 기반 자동 발급(외부 CA)
이건 Cloudflare가 CA가 아니라 DNS provider로 들어오는 형태가 많습니다. 예를 들어 Kubernetes에서는 cert-manager가 Cloudflare API token으로 DNS-01 TXT를 넣습니다. [cert-manager Cloudflare DNS01 문서](https://cert-manager.io/docs/configuration/acme/dns01/cloudflare/)

이 모델에서 Cloudflare의 “SSL Certificate Provisioning” 장애가 직접적으로 영향을 주는지 여부는 케이스별입니다.

- Cloudflare가 DNS만 제공하고 인증서 termination은 origin에서 하면, Cloudflare의 edge cert provisioning 장애와는 분리돼 있을 수 있습니다.
- 반대로 Cloudflare edge에서 cert를 서빙해야 하는 구조(Cloudflare for SaaS, edge termination 강제, custom cert upload 등)면, DCV가 끝나도 edge 배포가 막혀서 장애가 납니다.

운영적으로는 “ACME는 돌아가는데 접속은 안 된다” 같은 형태가 가능해집니다. 이때 사람은 ACME를 의심하지만 실제 병목은 edge 배포일 수 있습니다.

### Custom certificates(직접 업로드)
Cloudflare 문서에서 명시하듯 renewal 책임이 사용자에게 있습니다. [Custom certificates](https://developers.cloudflare.com/ssl/edge-certificates/custom-certificates/)

이 모델은 provisioning 장애가 “교체 실패 → 만료 레이스 컨디션”으로 발전합니다. 특히 문서상 업로드 요건에 “14일 이내 만료 cert는 업로드 불가”가 들어 있으니, 만료가 임박한 상태에서 배포 지연까지 겹치면 선택지가 급격히 줄어듭니다. [Manage custom certificates](https://developers.cloudflare.com/ssl/edge-certificates/custom-certificates/uploading/)

### Keyless SSL
Keyless SSL은 private key를 Cloudflare에 주지 않고, TLS handshake 중 key operation을 고객의 key server로 넘기는 모델입니다. Cloudflare 문서에 “key server는 TCP 2407을 열어야 하고, TLS handshake 시 Cloudflare가 key server에 접근해야 한다”고 되어 있습니다. [Keyless SSL](https://developers.cloudflare.com/ssl/keyless-ssl/) 및 [Keyless glossary](https://developers.cloudflare.com/ssl/keyless-ssl/glossary/)

이번 incident가 “subset of Custom certificates deploying”이라고 했으니, keyless 자체(handshake 경로)가 아니라 “keyless에서 사용하는 cert를 교체/재배포하는 순간”에 운영이 흔들릴 여지가 생깁니다. production에 이미 있는 cert는 영향이 없다고 했으니, 신규 배포나 교체 작업이 막히는 쪽이 더 현실적인 위험입니다. [Cloudflare incident 페이지](https://www.cloudflarestatus.com/incidents/21vwp89eiyjx)

### SSL for SaaS(Custom Hostnames)
Cloudflare는 custom hostname의 ssl.status를 API로 모니터링할 수 있게 설계해 두었습니다. status 값에 pending_deployment, deployment_timed_out 같은 상태가 들어 있습니다. [Custom Hostnames API (Python)](https://developers.cloudflare.com/api/python/resources/custom_hostnames/)

SaaS에서는 “인증서 발급/배포 지연”이 곧 “고객 온보딩 장애”입니다. 이건 기술 문제가 아니라 매출/서포트 비용 문제로 바로 연결됩니다.

## 코드: status page + Cloudflare API로 ‘발급/배포 대기열’을 숫자로 만들기

아래 코드는 장난감 예제가 아니라, 내가 실제로 운영에 넣는 방식(주기적 폴링 → 임계치 기반 알림)을 기준으로 구성했습니다.

- Cloudflare Status API에서 SSL Certificate Provisioning 컴포넌트/incident를 가져옵니다.
- Cloudflare API에서 zone별 certificate packs의 status 분포와 pending 상태의 개수를 집계합니다.
- Cloudflare for SaaS를 쓰는 경우 custom hostnames의 ssl.status 분포도 같이 봅니다.

인증서 장애는 “특정 시간에 폭발”하므로, 단발성 조회보다 “pending 객체 수의 증가율”이 더 중요합니다.

### 1) 준비물

- Python 3.12+
- 패키지: requests

```bash
python -V
# Python 3.12.7

python -m venv .venv
source .venv/bin/activate
pip install requests
```

환경 변수:

- CF_API_TOKEN: Cloudflare API token
- CF_ZONE_IDS: 콤마로 구분된 zone_id 목록

권한은 최소화합니다.

- certificate packs 조회: `Zone - SSL and Certificates - Read`(계정 정책에 맞게)
- custom hostnames 조회: `Zone - Custom Hostnames - Read`

권한 이름은 조직마다 토큰 템플릿이 달라질 수 있으니 실제 Cloudflare 대시보드에서 scope를 확인하는 게 맞습니다.

### 2) 실행 코드

```python
#!/usr/bin/env python3
import os
import sys
import time
import requests
from collections import Counter

CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_STATUS_SUMMARY = "https://www.cloudflarestatus.com/api/v2/summary.json"

def http_get(url, headers=None, timeout=20):
    r = requests.get(url, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def cf_get(path, token, timeout=30):
    url = f"{CF_API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"Cloudflare API error: {data}")
    return data

def summarize_status_page():
    # Cloudflare 권고대로 명시적인 User-Agent를 둡니다.
    headers = {"User-Agent": "daewooki-cert-monitor/1.0 (+https://daewooki.github.io/)"}
    s = http_get(CF_STATUS_SUMMARY, headers=headers)

    components = s.get("components", [])
    incidents = s.get("incidents", [])

    comp_map = {c["name"]: c["status"] for c in components}

    interesting = [
        "SSL Certificate Provisioning",
        "SSL for SaaS Provisioning",
    ]

    out = {
        "page_status": s.get("status", {}).get("description"),
        "components": {name: comp_map.get(name) for name in interesting},
        "open_incidents": [
            {
                "name": i.get("name"),
                "status": i.get("status"),
                "impact": i.get("impact"),
                "created_at": i.get("created_at"),
                "shortlink": i.get("shortlink"),
            }
            for i in incidents
        ],
    }
    return out

def summarize_certificate_packs(zone_id, token):
    data = cf_get(f"/zones/{zone_id}/ssl/certificate_packs", token)
    packs = data.get("result", [])

    pack_status = Counter([p.get("status") for p in packs])
    pack_type = Counter([p.get("type") for p in packs])

    # Pending 계열을 개별로 뽑아 두면 런북에 바로 쓰기 좋습니다.
    pending_like = {
        k: v
        for k, v in pack_status.items()
        if k and (
            k.startswith("pending_")
            or k.endswith("_timed_out")
            or k in ("holding_deployment",)
        )
    }

    # certificate 개별 만료(expires_on)는 packs.result[].certificates[]에 들어있습니다.
    # API 스키마에 expires_on이 정의되어 있습니다.
    # https://developers.cloudflare.com/api/resources/ssl/
    soon_expiring = []
    now = time.time()
    for p in packs:
        for cert in (p.get("certificates") or []):
            exp = cert.get("expires_on")
            if not exp:
                continue
            # RFC3339 파싱은 구현 단순화를 위해 생략하고 문자열만 저장합니다.
            # 운영에서는 dateutil/parser로 epoch 변환 후 임계치 비교를 권장합니다.
            soon_expiring.append(
                {
                    "pack_id": p.get("id"),
                    "pack_type": p.get("type"),
                    "pack_status": p.get("status"),
                    "cert_id": cert.get("id"),
                    "cert_status": cert.get("status"),
                    "expires_on": exp,
                    "hosts": cert.get("hosts"),
                }
            )

    return {
        "zone_id": zone_id,
        "pack_status": dict(pack_status),
        "pack_type": dict(pack_type),
        "pending_like": pending_like,
        "certs_with_expires_on": soon_expiring,
    }

def summarize_custom_hostnames(zone_id, token, per_page=100):
    # Custom Hostnames는 계정/플랜에 따라 비어 있을 수 있습니다.
    # API는 ssl_status 필터/정렬을 지원합니다.
    # https://developers.cloudflare.com/api/python/resources/custom_hostnames/

    page = 1
    ssl_status_counter = Counter()
    hostname_status_counter = Counter()
    stuck = []

    while True:
        data = cf_get(
            f"/zones/{zone_id}/custom_hostnames?per_page={per_page}&page={page}",
            token,
        )
        items = data.get("result", [])
        if not items:
            break

        for it in items:
            hostname_status_counter[it.get("status")] += 1
            ssl = it.get("ssl") or {}
            ssl_status_counter[ssl.get("status")] += 1

            # 운영상 위험한 상태만 샘플로 남깁니다.
            if ssl.get("status") in (
                "pending_validation",
                "pending_issuance",
                "pending_deployment",
                "validation_timed_out",
                "issuance_timed_out",
                "deployment_timed_out",
                "holding_deployment",
                "expired",
            ):
                stuck.append(
                    {
                        "id": it.get("id"),
                        "hostname": it.get("hostname"),
                        "hostname_status": it.get("status"),
                        "ssl_status": ssl.get("status"),
                        "verification_errors": it.get("verification_errors"),
                        "validation_errors": ssl.get("validation_errors"),
                    }
                )

        # pagination
        info = data.get("result_info") or {}
        if page >= (info.get("total_pages") or page):
            break
        page += 1

    return {
        "zone_id": zone_id,
        "custom_hostname_status": dict(hostname_status_counter),
        "custom_hostname_ssl_status": dict(ssl_status_counter),
        "stuck_samples": stuck[:20],
    }

def main():
    token = os.getenv("CF_API_TOKEN")
    zone_ids = os.getenv("CF_ZONE_IDS", "").strip()

    if not token or not zone_ids:
        print("Usage: CF_API_TOKEN=... CF_ZONE_IDS=zone1,zone2 python cf_cert_watch.py", file=sys.stderr)
        sys.exit(2)

    zones = [z.strip() for z in zone_ids.split(",") if z.strip()]

    print("# status_page")
    print(summarize_status_page())

    for z in zones:
        print(f"\n# zone {z}: certificate_packs")
        print(summarize_certificate_packs(z, token))

        print(f"\n# zone {z}: custom_hostnames")
        print(summarize_custom_hostnames(z, token))

if __name__ == "__main__":
    main()
```

실행:

```bash
CF_API_TOKEN="***" \
CF_ZONE_IDS="<zone_id_1>,<zone_id_2>" \
python cf_cert_watch.py
```

예상 출력(형태):

- status_page에서 `SSL Certificate Provisioning`이 `degraded_performance` 같은 값으로 바뀌면 바로 신호가 됩니다(정확한 상태 문자열은 summary.json 응답에 따릅니다). [Cloudflare Status API](https://www.cloudflarestatus.com/api)
- zone별 pack_status에서 pending_deployment, deployment_timed_out 같은 값이 0이 아닌 순간을 잡아냅니다. [SSL API](https://developers.cloudflare.com/api/resources/ssl/)
- SaaS를 쓰면 custom_hostname_ssl_status에서 pending_*가 증가하는지 봅니다. [Custom Hostnames API](https://developers.cloudflare.com/api/python/resources/custom_hostnames/)

이 코드는 “장애를 탐지하는” 목적보다는 “장애를 운영 지표로 정리하는” 목적에 가깝습니다. 실제 알림은 다음처럼 구성합니다.

- pending_deployment 개수 증가율이 일정 임계치 이상이면 경보
- *_timed_out이 1개라도 나오면 경보(즉시 런북 실행)
- 만료 임박(expires_on) 대상이 많고 동시에 pending 상태가 증가하면 change freeze 발동

## 반론과 회의론: “프로덕션 cert는 영향이 없었다”로 끝내면 안 되는 이유

이번 incident 본문에는 분명히 “SSL certificates already in production remain unaffected”라고 적혀 있습니다. [Cloudflare incident 페이지](https://www.cloudflarestatus.com/incidents/21vwp89eiyjx)

이 문장은 기술적으로는 “현재 트래픽 장애는 제한적일 수 있다”는 의미지만, 운영적으로는 위험한 함정이 있습니다.

- 신규 온보딩/갱신/교체는 production이 아니라 change window에서 발생합니다.
- incident가 발생한 그 순간에 “우연히” cert 관련 작업이 없었을 뿐, 다음 재발 때도 없다는 보장은 없습니다.
- SaaS 커스텀 도메인 기능을 제공하는 조직은, cert 프로비저닝 장애가 곧바로 customer-facing 장애가 됩니다.

즉 “현재 요청이 정상”이라는 사실과 “운영이 정상”이라는 사실은 완전히 다릅니다. 나는 이런 사건을 ‘숨은 의존성의 가시화 이벤트’로 분류합니다. AT&T 10DLC MMS 지연 장애를 런북 관점에서 정리했던 것처럼, 지연은 정상처럼 보이기 때문에 런북이 없으면 더 크게 터집니다. [AT&T 10DLC MMS 지연 장애와 앱 레이어 런북](https://daewooki.github.io/posts/att-10dlc-mms-delay-runbook/)

## 앞으로 지켜볼 것: status에 없는 숫자(백로그/분포/영향 범위)

상태 페이지에서 얻을 수 있는 정보는 제한적입니다. 이번 incident도 타임라인(Investigating → Identified → Monitoring → Resolved)과 “subset of Custom certificates 배포 이슈”라는 설명까지만 있습니다. [Cloudflare incident 페이지](https://www.cloudflarestatus.com/incidents/21vwp89eiyjx)

운영 관점에서는 다음 수치가 없으면 의사결정이 어렵습니다.

- Pending Deployment에 걸린 객체 수(백로그)
- 배포 지연의 p50/p95/p99(“몇 분이 정상인지” 정의)
- 특정 리전/PoP/CA 조합에서만 재현되는지
- 재시도(redeploy)가 백로그에 어떤 영향을 주는지

이걸 Cloudflare가 공개해주지 않아도, 우리 쪽에서 관측 가능한 신호가 있습니다.

- certificate pack status 분포(Active vs pending_* 비율)
- custom hostname ssl.status 분포
- “기대 시간 대비 지연”을 SLO로 정의(예: pending_deployment 15분 초과 비율)

여기까지 만들어두면, status incident가 뜨는 순간부터 대응이 “기다린다”가 아니라 “우리 대기열이 지금 증가 중인지 감소 중인지”로 바뀝니다.

## 지금 정비할 것: 런북과 알림을 ‘발급/배포’ 기준으로 재작성

나는 인증서 런북을 다음 네 개의 문장으로 시작합니다.

1) 인증서 문제는 발급(issuance)과 배포(deployment)로 나뉜다.
2) 운영 장애는 대개 deployment에서 먼저 드러난다.
3) pending_*는 장애의 전조이고, *_timed_out은 이미 장애다.
4) 만료 모니터링은 필요조건이고, provisioning 모니터링이 충분조건이다.

Cloudflare 문서/모델을 기준으로 런북에 반드시 넣어야 하는 항목은 다음입니다.

- certificate statuses 상태표(Initializing/Pending Validation/Pending Issuance/Pending Deployment/Active, 그리고 timed_out 계열) [Certificate statuses](https://developers.cloudflare.com/ssl/reference/certificate-statuses/)
- Universal SSL의 renewal 시도 기간과 “만료 24시간 전까지 계속 시도” 정책 [Validity periods and renewal](https://developers.cloudflare.com/ssl/reference/certificate-validity-periods/)
- Custom certificates는 Cloudflare가 renewal을 관리하지 않는다는 전제 [Custom certificates](https://developers.cloudflare.com/ssl/edge-certificates/custom-certificates/)
- status page는 HTML 스크래핑 대신 Status API를 써야 한다는 규칙 [Cloudflare Status API](https://www.cloudflarestatus.com/api)

여기에 조직별로 추가되는 항목이 있습니다.

- Cloudflare for SaaS를 쓰는 조직: custom hostname 준비 완료 정의(active+active+DNS)와 DCV token 재검증 절차 [Troubleshooting (Cloudflare for SaaS)](https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/security/certificate-management/issue-and-validate/validate-certificates/troubleshooting/)
- Keyless SSL을 쓰는 조직: key server 가용성(2407), cert 교체 시점의 위험 [Keyless SSL](https://developers.cloudflare.com/ssl/keyless-ssl/)

인증서는 보안 요소이기도 하지만, 운영 요소로 봐야 피해가 줄어듭니다. 이번 사건은 그 사실을 다시 확인시켜 주는 로그였습니다.

## 참고 자료

- [Cloudflare incident: SSL Certificate Provisioning Issue](https://www.cloudflarestatus.com/incidents/21vwp89eiyjx)
- [Cloudflare Status API](https://www.cloudflarestatus.com/api)
- [Cloudflare Status 구독/알림 안내](https://developers.cloudflare.com/support/cloudflare-status/)
- [Certificate statuses](https://developers.cloudflare.com/ssl/reference/certificate-statuses/)
- [Validity periods and renewal](https://developers.cloudflare.com/ssl/reference/certificate-validity-periods/)
- [Enable Universal SSL certificates](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/enable-universal-ssl/)
- [Custom certificates](https://developers.cloudflare.com/ssl/edge-certificates/custom-certificates/)
- [Manage custom certificates](https://developers.cloudflare.com/ssl/edge-certificates/custom-certificates/uploading/)
- [Rotate ACM certificate packs](https://developers.cloudflare.com/ssl/reference/certificate-rotation/)
- [SSL API: Certificate Packs](https://developers.cloudflare.com/api/resources/ssl/subresources/certificate_packs/)
- [Custom Hostnames API (Python)](https://developers.cloudflare.com/api/python/resources/custom_hostnames/)
- [Cloudflare for SaaS: Validate certificates troubleshooting](https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/security/certificate-management/issue-and-validate/validate-certificates/troubleshooting/)
- [Keyless SSL](https://developers.cloudflare.com/ssl/keyless-ssl/)
- [cert-manager: Cloudflare DNS01](https://cert-manager.io/docs/configuration/acme/dns01/cloudflare/)
- [Staging environment](https://developers.cloudflare.com/ssl/edge-certificates/staging-environment/)
- [Certificate Transparency Monitoring](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/certificate-transparency-monitoring/)
- [Certificate Transparency Monitoring GA (Cloudflare Blog)](https://blog.cloudflare.com/certificate-transparency-monitoring-ga)
- [RFC 9162: Certificate Transparency v2](https://www.rfc-editor.org/rfc/rfc9162.pdf)
- [Cloudflare IAD 성능 이슈가 전 서비스 에러로 번지는 패턴](https://daewooki.github.io/posts/cloudflare-iad-incident-resilience/)
- [AT&T 10DLC MMS 지연 장애와 앱 레이어 런북](https://daewooki.github.io/posts/att-10dlc-mms-delay-runbook/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
