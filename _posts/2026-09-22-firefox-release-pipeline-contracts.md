---
title: "Firefox 156을 배포 파이프라인에 넣는 계약 설계"
description: "2주 릴리스로 바뀐 Firefox 156을 계기로, 브라우저 업데이트를 정책·테스트·롤백 계약으로 재구성합니다."
date: 2026-09-22 13:19:13 +0900
categories: ["News", "Web"]
tags: ["firefox", "rapid-release", "enterprise-policy", "e2e-testing", "rollout", "security-updates"]
render_with_liquid: false
---

2026-09-22(KST) 기준으로 Firefox 156.0은 2026-09-15에 Release 채널에 제공됐습니다. 릴리스 노트에도 “Version 156.0, first offered to Release channel users on September 15, 2026”로 명시돼 있습니다.[^1]

이 날짜 자체보다 중요한 건, Mozilla가 Desktop/Android를 2주 릴리스로 옮겼다는 사실입니다. Mozilla Support Blog는 2026-08-19 글에서 “Firefox is moving to a two-week release cycle”이고, 그 첫 릴리스가 Firefox 155(2026-09-01)라고 못 박았습니다.[^2]

2주 릴리스는 기능이 두 배로 늘어난다는 뜻이 아니라, 업데이트 파동이 두 배로 자주 온다는 뜻입니다(그리고 dot release가 사라지는 것도 아닙니다).[^2] 문제는 많은 조직이 아직도 브라우저 업데이트를 “사용자가 알아서” 또는 “헬프데스크 이슈가 쌓이면” 처리하고 있다는 점입니다. 이 운영 방식은 2주 릴리스에서 QA/보안/지원의 병목을 빠르게 터뜨립니다.

Firefox 156을 소재로 삼되, 릴리스 노트 기능 나열 대신 “브라우저 업데이트를 배포 파이프라인에 편입”하려면 무엇을 계약으로 고정해야 하는지 정리합니다.

## Firefox 156에서 조직 운영을 건드리는 변화만 추려보기

Firefox 156의 사용자용 릴리스 노트는 소소한 UX 항목과 성능/미디어/네트워크 수정이 섞여 있습니다. 조직 관점에서 체크할 포인트는 “사용자 기능”보다, **테스트 표면적이 늘어나는 변화**와 **정책으로 통제 가능한 레버가 늘어나는 변화**입니다.

먼저, Web/미디어 쪽은 다음 두 줄이 운영과 QA에 영향을 줍니다.

- Windows ARM64에서 WebRTC video call이 H264 hardware decoding을 사용할 수 있게 됐다는 변경이 있습니다. 이전에는 software로 fallback됐을 수 있습니다. ARM64 디바이스를 쓰는 콜센터/키오스크/현장 단말이 있다면, CPU 사용률/발열/배터리뿐 아니라 드라이버/코덱 조합에서 재현되는 미디어 버그가 새로 생길 수 있습니다.[^1]
- MDN 개발자 릴리스 노트에는 `RTCPeerConnection()`의 configuration에 `alwaysNegotiateDataChannels`가 추가됐다고 나옵니다. `true`로 두면 SDP에 data channel m-line을 항상 포함시켜, 나중에 `createDataChannel()`을 호출해도 재협상이 필요 없게 만들 수 있습니다. 기본값은 `false`이며 `setConfiguration()`으로 바꿀 수 없고 `getConfiguration()`에서 반환된다는 제약도 같이 적혀 있습니다.[^3]

이 두 항목은 WebRTC 기반 기능(음성/영상/실시간 상담/화상 면접)이 있는 서비스팀에선 “새 기능”이 아니라 “테스트 행렬의 축이 하나 더 생김”으로 해석하는 게 맞습니다. 내 블로그에서 WebRTC를 파이프라인/전송 관점으로 정리한 글이 있는데(구현 디테일은 반복하지 않겠습니다), 실시간 기능은 브라우저 업데이트에 가장 취약한 축입니다.

- [“실시간 음성 에이전트” 구현의 승부처는 모델이 아니라 파이프라인과 전송(WebRTC) 이다](https://daewooki.github.io/posts/2026-8-webrtc-1/)
- [말 끊김 없이 “대화가 되는” 2026년형 실시간 음성 에이전트: STT/TTS 파이프라인 vs Speech-to-Speech, WebRTC로 끝내기](https://daewooki.github.io/posts/2026-stttts-vs-speech-to-speech-webrtc-2/)

보안/프로토콜 쪽은 더 노골적입니다.

- MDN에 따르면 Firefox 156에서 TLS handshake 시 `ffdhe2048`, `ffdhe3072` finite-field Diffie-Hellman group을 기본으로 더 이상 offer하지 않습니다. 오직 이 그룹만 지원하는 서버는 연결 협상이 실패할 수 있고, “거의 모든 서버는 ECDHE를 지원한다”고 덧붙입니다.[^3]

이건 “보안 강화”라서 좋은 변화일 수 있지만, 기업 내부의 오래된 TLS terminate 장비/레거시 Java 스택/특수망 장비가 여전히 ffdhe만 열어놓고 있을 때는 장애로 표현됩니다. 2주 릴리스에서는 이런 변화가 누적되며, 어느 날 갑자기 사내 일부 서비스가 Firefox에서만 접속이 안 되는 티켓으로 올라옵니다.

그리고 Firefox 156 Enterprise 릴리스 노트는 업데이트 운영 관점에서 더 직접적입니다. Firefox 156 및 Firefox ESR 153.3.0에 적용되는 변경이라고 명시돼 있고(단, 항목마다 “Firefox 156 only”, “ESR에는 미적용” 같은 예외가 섞입니다), 특히 눈여겨볼 건 `SitePolicies`에 `DisableServiceWorkers` 옵션이 추가된 점입니다. “특정 사이트가 service worker를 register하거나 사용하는 것을 막는다”는 설명이 붙어 있고, “Firefox 156 only”라고 적혀 있습니다.[^4]

이 항목은 기능이 아니라 운영 레버입니다.

- service worker 캐시/업데이트 꼬임으로 장애가 났을 때, 코드 hotfix가 준비되기 전까지 “Firefox 쪽에서만” 응급조치로 SW를 무력화할 수 있는 여지가 생긴 겁니다.
- 다만 “Firefox 156 only”면, 2주 뒤 157에서 동작/정책 형태가 바뀌거나 ESR에는 없을 수도 있습니다. 따라서 정책을 운영 레버로 쓰려면 “버전별 가용성”까지 계약에 넣어야 합니다.

마지막으로 Firefox 156 릴리스 노트는 “Various security fixes”를 한 줄로 처리하지만, 같은 날짜(2026-09-15)에 MFSA 2026-90 보안 권고가 올라왔고, “Impact: high”, “Fixed in: Firefox 156”로 게시됐습니다. 그리고 Mozilla가 advisory 게시 방식(메모리 안전 버그를 묶어서 1개 CVE로 내던 방식)을 바꿨다고 공지합니다.[^5]

조직이 브라우저 업데이트를 배포 파이프라인에 넣는다는 건, 결국 이 MFSA 같은 신호를 “개발팀이 읽는 뉴스”가 아니라 “배포 트리거”로 바꿔서 SLA에 연결하는 일입니다.

## 2주 릴리스에서 먼저 고정해야 하는 계약: 지원 버전과 책임

브라우저 업데이트 운영을 망치는 가장 흔한 원인은, “정책”이 아니라 “계약 부재”입니다. 여기서 계약은 법무 계약이 아니라, 서비스팀/QA/보안/IT가 공유하는 운영 합의입니다.

내가 여러 조직에서 봤던 실패 패턴은 거의 항상 이 순서로 터졌습니다.

1) 브라우저는 사용자 환경이라 IT 소관이라고 생각함
2) E2E 테스트는 애플리케이션 릴리스마다만 돌리면 된다고 생각함
3) 보안은 CVE가 Critical일 때만 긴급 업데이트를 말함
4) 장애가 나면 지원팀이 “브라우저 최신으로 업데이트해보세요” 템플릿으로 응대함
5) 2주 릴리스에서 이 4개의 가정이 동시에 깨짐

그래서 첫 번째 계약은 지원 범위를 명문화하는 겁니다.

### 지원 버전 계약: N, N-1, ESR 중 무엇을 기준으로 할지

Firefox는 Enterprise 문서에서 업데이트 채널을 Rapid Release와 ESR로 구분합니다. Rapid Release는 자주 업데이트되며, ESR은 장기 지원 트랙입니다.[^6] 또한 “ESR은 rapid release에는 없는 추가 정책을 사용할 수 있다”고도 적습니다.[^6]

조직이 선택해야 하는 건 단순합니다.

- 사내 표준 브라우저를 ESR로 고정할지
- Rapid Release를 쓰되, 내부 롤아웃을 ring으로 쪼갤지
- 둘 다 허용하되(예: 일반 직원은 ESR, 개발/QA는 Rapid Release), 서비스의 지원 범위를 어디까지 약속할지

여기서 중요한 건 “지원”이라는 단어를 티켓 처리 관점이 아니라, 테스트/배포 관점으로 정의하는 겁니다.

- (지원) 이 버전에서 버그 리포트가 들어오면 재현을 시도한다
- (보증) 이 버전은 배포 파이프라인에서 정기적으로 smoke/E2E를 통과한다
- (허용) 이 버전에서 문제가 나면 사용자에게 업데이트/다운그레이드를 안내한다

대부분 조직은 이 셋을 섞어 쓰다가, 사고가 나면 “우리는 최신만 지원” 같은 문장으로 도망가는데, 2주 릴리스에서는 그 문장이 곧 비용 폭탄이 됩니다. 최신이 2주마다 바뀌면, 지원을 포기하는 순간 고객/내부 사용자는 2주마다 지원에서 탈락합니다.

내 결론은 보통 이렇게 갑니다.

- 외부 고객용 SaaS: N, N-1(또는 N-2)까지 “보증”으로 끌고 가고, ESR은 “지원”까지만(재현은 해보되, 즉시 hotfix를 약속하지는 않음)
- 내부 업무 시스템: 조직이 Firefox ESR을 표준으로 강제할 수 있다면 ESR을 “보증”으로, Rapid Release는 “허용”으로 내린다

Rapid Release를 표준으로 쓰는 조직도 있지만, 그러면 롤아웃 계약이 훨씬 더 중요해집니다.

### 책임 분리 계약: 브라우저 업데이트가 깨뜨린 건 누가 고치나

브라우저 업데이트로 장애가 나면, 실제로는 세 가지 유형이 섞입니다.

- 우리 서비스의 버그(표준 준수 부족, 특정 브라우저 UA 의존 코드)
- 브라우저의 버그(회귀)
- 정책/배포의 버그(업데이트가 잘못 배포되었거나, 정책으로 막아야 할 게 풀렸거나)

2주 릴리스에서 첫 번째를 “개발팀이 즉시 고친다”로 계약하면 개발팀은 상시 on-call 상태가 됩니다. 반대로 “브라우저 버그니까 기다린다”로 계약하면 서비스 신뢰가 빠집니다.

그래서 책임 계약을 다음처럼 나눕니다.

- **회피 가능한 표준/호환성 문제**: 서비스팀이 고친다(예: TLS group 변경으로 특정 레거시 서버가 막힘 → 서버 구성 수정)
- **브라우저 회귀**: 우회 패치(Feature flag, 사용자 가이드) + 롤백/핀으로 대응하고, upstream 버그 리포트는 하되 SLA는 롤아웃 계약으로 흡수한다
- **정책/배포 실수**: IT/플랫폼이 고친다(정책 repo, MDM 배포, 링 설정)

이게 문서 한 장으로 끝나는 게 아니라, 이후 섹션의 “테스트 범위”와 “롤백”이 이 책임 계약을 실행 가능하게 만드는 장치입니다.

## 정책 계약: 업데이트를 막을지, 늦출지, 링으로 흘릴지

2주 릴리스에서 업데이트를 “수동 안내”로 처리하면 거의 반드시 깨집니다. 지원팀이 2주마다 공지하고, 사용자마다 다른 시점에 업데이트하고, 그 결과로 재현이 안 되는 버그가 쌓입니다.

정책 계약은 한 문장으로 요약됩니다.

- 브라우저 업데이트는 사용자 행동이 아니라 시스템 동작으로 만든다.

Firefox는 enterprise policy를 여러 방식으로 적용할 수 있고, policies.json은 크로스 플랫폼이라 다양한 OS가 섞인 환경에서 선호된다고 설명합니다. Linux에서는 설치 디렉터리의 `firefox/distribution` 또는 시스템 전역으로 `/etc/firefox/policies`에 둘 수 있다고도 안내합니다.[^7]

업데이트 제어의 핵심 정책도 문서에 반복해서 등장합니다.

- Automatic update를 끄는 `DisableAppUpdate`
- update가 켜져 있을 때 사용자 승인 없이 silent install을 가능하게 하는 `AppAutoUpdate`

Mozilla의 “Manage Firefox updates” 문서는 “Automatic updates are enabled by default”이며 `DisableAppUpdate`로 비활성화할 수 있고, 반대로 `AppAutoUpdate`를 켜면 사용자 승인 없이 silent로 설치할 수 있다고 설명합니다.[^8]

또한 `AppAutoUpdate` 정책 문서(관리자 문서)에서는 `DisableAppUpdate`로 업데이트를 비활성화해둔 경우 `AppAutoUpdate`는 효과가 없다고 못 박습니다.[^9]

이 조합은 운영 계약에서 굉장히 중요합니다. 많은 조직이 “자동 업데이트는 꺼두고, 필요할 때 조용히 올리자”를 동시에 원합니다. 하지만 그건 모순이고, 정책도 그 모순을 그대로 드러냅니다. 그래서 선택은 셋 중 하나입니다.

1) 브라우저 자체 업데이트를 켜고(AppAutoUpdate 포함), 배포 링으로 단계적 적용을 운영한다
2) 브라우저 자체 업데이트를 끄고(DisableAppUpdate), MDM/패키징 시스템으로 버전을 강제한다
3) 혼합: 직원군마다 1)과 2)를 나눠 운영한다(예: 키오스크/콜센터 단말은 2, 일반 PC는 1)

Firefox 2주 릴리스에서 1)이든 2)이든, 핵심은 “배포 파이프라인에 넣었을 때 되돌릴 수 있냐”입니다. 브라우저는 애플리케이션보다 롤백이 어렵기 때문에, 정책 계약은 곧 롤백 계약으로 이어져야 합니다.

### 링 계약: canary, pilot, broad의 의미를 브라우저에 맞게 재정의

내가 권하는 링 구성은 웹 서비스 배포 링과 비슷하지만, 브라우저에서는 관찰 지표가 다릅니다.

- Canary(1~5%): 개발/QA/IT + 내부에서 장애를 발견해도 복구가 빠른 그룹
- Pilot(10~30%): 실제 업무 사용자이되, helpdesk 대응력이 있는 조직(예: HQ)
- Broad(나머지): 전체

관찰 지표는 “에러 로그”가 아니라, 브라우저 업데이트로 흔들리는 지표를 잡아야 합니다.

- 로그인 성공률, SSO redirect completion
- 결제/전자서명/다운로드 같은 보안 민감 플로우 성공률
- WebRTC call setup time, media permission grant rate, call drop rate
- service worker update 실패율(특히 오프라인 캐시를 쓰는 서비스)

Firefox 156만 봐도 WebRTC hardware decoding 변화(Windows ARM64) 같은 건 에러 로그가 아니라 사용자 체감(발열/끊김)으로 먼저 드러납니다.[^1]

이 지표가 없으면 링은 의미가 없어지고, 업데이트는 “그냥 배포”가 됩니다.

## 테스트 계약: E2E를 줄이지 말고, ‘범주’를 다시 나눠야 한다

2주 릴리스로 들어가면 흔히 나오는 요구가 “E2E가 너무 비싸니 줄이자”입니다. 방향이 반대입니다. E2E 자체를 늘리면 비용이 터지니, E2E를 구성하는 테스트를 계약 관점으로 재분류해야 합니다.

내가 쓰는 분류는 크게 세 가지입니다.

### 1) 브라우저 계약 테스트(Contract Smoke)

목적은 “이번 Firefox 업데이트로 우리 서비스가 **기본 동작**을 유지하는지”를 확인하는 겁니다. 기능 커버리지가 아니라, 브라우저 변경이 자주 부딪히는 표면적을 찍습니다.

- TLS/네트워크: 로그인 도메인, API 도메인, 파일 다운로드 도메인에 대한 handshake/redirect
  - Firefox 156에서 ffdhe group 비제공으로 협상이 실패할 수 있다는 변경이 있으니, 레거시 장비가 낀 사내망이라면 특히 이 테스트가 의미가 있습니다.[^3]
- Storage/Service worker: 최초 로드, SW 등록, 업데이트 시나리오, 캐시 무효화
  - 정책 레버로 `SitePolicies.DisableServiceWorkers`가 들어왔다는 건, Mozilla도 이 영역을 운영 리스크로 보고 있다는 신호로 읽습니다.[^4]
- Media/WebRTC: 마이크 권한, 기기 선택, ICE 연결, 30초 유지
  - Firefox 156은 WebRTC 하드웨어 디코딩 및 `alwaysNegotiateDataChannels` 같은 변경이 있습니다.[^1]

이 테스트는 모든 기능을 눌러보지 않습니다. 대신 실패하면 “업데이트 링을 멈출 근거”가 되는 최소 증거를 만듭니다.

### 2) 제품 E2E(Feature E2E)

여기서부터는 서비스팀의 책임입니다. 제품의 핵심 플로우(구매, 상담, 문서 작성 등)를 검증합니다. 다만 2주 릴리스에서는 이 E2E가 브라우저 업데이트마다 전체를 도는 순간 비용이 감당이 안 됩니다.

그래서 제품 E2E는 다음 원칙을 둡니다.

- 브라우저 계약 테스트가 통과하면, 제품 E2E는 “변경 가능성이 큰 영역”만 리그레션으로 돌린다
- 브라우저 계약 테스트가 실패하면, 제품 E2E를 늘리는 게 아니라 업데이트 배포를 멈추고 원인을 좁힌다

즉, E2E는 더 정교한 계층 구조가 돼야 하고, 그 계층의 첫 단추가 계약 테스트입니다.

### 3) 브라우저 도구체인 테스트(WebDriver/Automation)

2주 릴리스에서 자주 놓치는 건 “우리 제품은 멀쩡한데 CI가 깨지는” 사건입니다. Firefox 156은 WebDriver 쪽에서도 변경이 있고(예: 서버 시작 실패 시 exit code 69 사용), 자동화 스택이 이 exit code를 crash로 분류하거나 재시도 정책에 영향을 줄 수 있습니다.[^3]

이건 제품팀이 아니라 플랫폼/QA 자동화 담당의 계약 범주입니다.

- 어떤 Firefox 버전에서 어떤 geckodriver/WebDriver BiDi 조합을 공식 지원할지
- CI 런타임에서 브라우저 바이너리를 어떻게 가져올지(캐시, 무결성)
- 브라우저가 업데이트되어도 테스트 러너는 얼마나 버텨야 하는지

2주 릴리스에서는 이 자동화 계약이 없으면, 제품 릴리스와 무관하게 CI가 흔들려 개발 속도가 같이 무너집니다.

## 배포 파이프라인 계약: 브라우저를 ‘의존성 artifact’로 취급하기

브라우저 업데이트를 파이프라인에 넣는다고 하면, 많은 팀이 곧바로 “MDM에서 자동 업데이트 켜면 되지 않나”로 끝내려고 합니다. 그건 업데이트가 아니라 통제 포기입니다.

파이프라인은 최소한 다음을 포함해야 합니다.

1) 관찰: 새 버전 등장 감지
2) 평가: 계약 테스트 수행
3) 승인: 변경 등급 분류(보안 긴급/일반/보류)
4) 배포: 링 기반 단계적 적용
5) 회복: 롤백 또는 정책 기반 완화

Firefox 156은 릴리스 노트에서 보안 수정이 있다고만 말하지만, 실제로는 MFSA 2026-90이 같은 날 게시됐고 Impact high로 표시됩니다.[^5] 즉, “새 버전 등장 감지”는 릴리스 노트 RSS를 읽는 문제가 아니라 보안 권고/릴리스 캘린더/정책 릴리스 노트를 묶어 이벤트로 만들 문제입니다.

### 현실적인 구현: 버전 이벤트를 하나로 합치기

내가 실제로 쓰는 방식은 “세 문서”를 하나의 릴리스 이벤트로 합칩니다.

- 사용자 릴리스 노트(변경의 방향)
- MDN 개발자 릴리스 노트(Web/API/보안 프로토콜의 구체 변경)
- Enterprise 릴리스 노트(정책 레버와 관리 측면 변경)

Firefox 156은 이 세 문서가 모두 존재합니다.

- [Firefox 156 Release Notes](https://www.firefox.com/en-US/firefox/156.0/releasenotes/)[^1]
- [MDN: Firefox 156 for developers](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/156)[^3]
- [Firefox 156 release notes for enterprise admins](https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-156/)[^4]

여기에 보안 트리거로 [MFSA 2026-90](https://www.mozilla.org/en-US/security/advisories/mfsa2026-90/)를 붙입니다.[^5]

이렇게 “릴리스 이벤트”를 정의해두면, 내부 승인 프로세스가 기능 나열이 아니라 계약 항목 체크리스트로 바뀝니다.

- TLS/PKI 영향: ffdhe 비제공(레거시 장비 영향)[^3]
- WebRTC 영향: ARM64 hardware decode, data channel negotiation 옵션[^1]
- Policy 영향: DisableServiceWorkers 같은 응급 레버 추가[^4]
- Security 영향: Impact high advisory 게시, 게시 방식 변경(개별 bug 단위 CVE)[^5]

### “브라우저 다운로드”를 CI에서 즉흥적으로 하지 말아야 하는 이유

2주 릴리스에서 가장 안 좋은 패턴은 CI가 매번 외부에서 브라우저를 받아서 돌고, 그 브라우저가 언제 바뀌는지 모르는 상태입니다.

- 오늘 통과한 테스트가 내일 같은 커밋에서 실패할 수 있습니다.
- 실패가 제품 회귀인지 브라우저 업데이트인지 구분이 안 됩니다.
- 장애 대응 중에 “재현 환경”을 만들 수 없습니다.

그래서 브라우저 바이너리를 의존성 artifact로 취급합니다.

- 내부 캐시(artifact repository)에 저장
- 버전 고정
- 체크섬 검증
- 테스트 러너가 “버전”을 로그로 남김

아래는 Linux에서 Firefox를 버전 고정으로 내려받아(실제 URL은 조직 표준에 맞게 내부 미러로 바꾸는 걸 전제로) Playwright에서 특정 executablePath로 실행하는 예시입니다. URL 규칙은 Mozilla Archive 관례를 따르되, CI 단계에서 404를 검증해 실패하도록 만들어 “틀린 가정이 조용히 흘러가지 않게” 합니다.

```bash
# 요구사항
# - Node.js 20+
# - Ubuntu 22.04/24.04 계열
# - 사내 네트워크에서 외부 다운로드가 막혀 있다면, FIREFOX_TARBALL_URL을 내부 미러로 바꿉니다.

mkdir -p tools/firefox
cat > tools/fetch-firefox.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

: "${FIREFOX_VERSION:?set FIREFOX_VERSION, e.g. 156.0}"

ARCH="linux-x86_64"
LANG="en-US"

# Mozilla archive의 일반적인 경로 관례를 사용합니다.
# 이 URL의 유효성은 아래 curl -I로 검증합니다.
FIREFOX_TARBALL_URL="https://archive.mozilla.org/pub/firefox/releases/${FIREFOX_VERSION}/${ARCH}/${LANG}/firefox-${FIREFOX_VERSION}.tar.bz2"

echo "[fetch] ${FIREFOX_TARBALL_URL}"

# URL이 바뀌었거나 버전이 존재하지 않으면 즉시 실패
curl -fsSI "${FIREFOX_TARBALL_URL}" > /dev/null

rm -rf "tools/firefox/${FIREFOX_VERSION}"
mkdir -p "tools/firefox/${FIREFOX_VERSION}"

curl -fsSL "${FIREFOX_TARBALL_URL}" \
  | tar -xj -C "tools/firefox/${FIREFOX_VERSION}"

# tarball은 firefox/ 디렉터리를 포함합니다.
FIREFOX_BIN="$(pwd)/tools/firefox/${FIREFOX_VERSION}/firefox/firefox"
"${FIREFOX_BIN}" --version

echo "FIREFOX_BIN=${FIREFOX_BIN}" > tools/firefox/${FIREFOX_VERSION}/env
EOF
chmod +x tools/fetch-firefox.sh

export FIREFOX_VERSION=156.0
./tools/fetch-firefox.sh
```

예상 출력은 대략 이런 형태입니다.

```text
[fetch] https://archive.mozilla.org/pub/firefox/releases/156.0/linux-x86_64/en-US/firefox-156.0.tar.bz2
Mozilla Firefox 156.0
```

그리고 Playwright를 “설치된 Firefox”로 실행합니다.

```bash
npm init -y
npm i -D @playwright/test

cat > playwright.config.ts <<'EOF'
import { defineConfig } from '@playwright/test';

export default defineConfig({
  timeout: 60_000,
  use: {
    headless: true,
  },
});
EOF

mkdir -p tests
cat > tests/contract-smoke.spec.ts <<'EOF'
import { test, expect } from '@playwright/test';

const baseURL = process.env.BASE_URL;
const firefoxBin = process.env.FIREFOX_BIN;

test('preflight', async () => {
  expect(baseURL, 'BASE_URL is required (e.g. https://staging.example.com)').toBeTruthy();
  expect(firefoxBin, 'FIREFOX_BIN is required (downloaded pinned Firefox path)').toBeTruthy();
});

test('contract smoke: login page loads and sets expected security headers', async ({ playwright }) => {
  const browser = await playwright.firefox.launch({
    executablePath: firefoxBin,
    headless: true,
  });
  const context = await browser.newContext();
  const page = await context.newPage();

  const resp = await page.goto(`${baseURL}/login`, { waitUntil: 'domcontentloaded' });
  expect(resp?.ok()).toBeTruthy();

  // 예: 최소한의 보안 헤더 존재 확인(조직마다 다름)
  const headers = resp!.headers();
  expect(headers['content-security-policy']).toBeTruthy();

  await browser.close();
});
EOF

# fetch 단계에서 저장해둔 env 로드
source tools/firefox/156.0/env
export BASE_URL="https://staging.example.com"

npx playwright test --reporter=line
```

이 테스트 자체는 단순하지만, 핵심은 “Firefox 156.0으로 고정된 실행”과 “BASE_URL만 바꿔 실제 스테이징에서 계약 테스트를 돈다”입니다. 장난감 페이지를 테스트하는 게 아니라, 조직의 실제 서비스 계약을 확인하는 테스트로 바꿔야 의미가 생깁니다.

## 롤백 계약: 브라우저는 되돌리기 어렵다는 사실을 전제로 설계

웹 서비스는 보통 blue/green이나 canary를 통해 롤백이 상대적으로 쉽습니다. 브라우저는 다릅니다.

- 사용자 데이터/프로필/확장
- OS별 설치 체계
- 자동 업데이트와 패키지 매니저의 충돌
- 다운그레이드 시 프로필 호환성 문제

그래서 “롤백”을 단일 동작으로 두지 않고, 단계별로 계약합니다.

### 1단계: 정책/서버 측 완화

Firefox 156 enterprise 변경 중 `SitePolicies.DisableServiceWorkers`는 장애 대응 플레이북에 넣을 만합니다. 특정 도메인에서 SW를 꺼서 캐시/업데이트 루프를 끊을 수 있기 때문입니다. 단, “Firefox 156 only”라는 제약이 있으니, 이 레버를 쓸 수 있는 버전 범위를 같이 기록해야 합니다.[^4]

또한 TLS 변경 같은 경우(예: ffdhe 미제공)는 브라우저를 롤백하기보다 서버의 cipher suite/group 설정을 고치는 게 더 현실적입니다.[^3]

이 단계의 목표는 “업데이트를 되돌리는 것”이 아니라 “서비스 가용성을 먼저 복구”하는 겁니다.

### 2단계: 링 중단 및 버전 핀

링을 설계했다면, 사고가 났을 때 해야 할 일은 명확합니다.

- broad 배포를 멈춘다
- pilot에서 관찰 지표를 확인한다
- canary에서 재현/원인 분리를 한다

여기서 버전 핀 정책을 무엇으로 구현할지는 조직의 선택(브라우저 자체 업데이트 vs MDM 강제)에 달려 있습니다. 중요한 건 “핀은 사건이 터졌을 때 즉흥적으로 만드는 게 아니라, 평상시에 훈련된 동작”이어야 한다는 점입니다.

### 3단계: 다운그레이드(최후 수단)

다운그레이드는 비용이 큽니다. 그래서 계약서에 “다운그레이드는 최후 수단이며, 언제 실행하는지”를 조건으로 적어둡니다.

예를 들면 이런 조건입니다.

- broad 배포 이후 P0 장애가 확인되고
- 정책/서버 완화로 4시간 내 복구가 불가능하며
- 영향 사용자가 10% 이상이고
- MFSA 수준의 보안 이슈가 아닌 기능 회귀로 판단될 때

여기까지 오면 “업데이트 운영을 망치지 않는 법”이 아니라 “업데이트 운영이 망가진 뒤 피해를 제한하는 법”으로 넘어갑니다. 2주 릴리스에서는 이 단계로 가는 빈도를 낮추는 게 목표입니다.

## 반론과 회의론: 2주 릴리스가 품질을 떨어뜨릴까

2주 릴리스로 바뀌면 조직 내부에서 두 가지 반론이 나옵니다.

1) “Mozilla 규모에서 2주마다 안정성을 유지할 수 있나”
2) “업데이트가 너무 자주 오면 우리 QA가 못 따라간다”

첫 번째는 사용자의 불안이고, 두 번째는 조직의 현실입니다. Mozilla Support Blog는 “features를 두 배로 출시하는 게 아니라 더 자주 업데이트를 내는 것”이라고 설명합니다.[^2] 즉, 릴리스 단위의 변경량이 줄어드는 방향이라면 오히려 회귀가 줄어야 한다는 기대도 가능합니다.

하지만 그 기대는 “업데이트가 자동으로 안전해진다”가 아니라 “업데이트를 다루는 방식이 바뀌어야 안전해진다”로 해석해야 합니다. 릴리스 단위 변경량이 줄어도, 업데이트 빈도가 늘면 조직의 운영 부하는 그대로 증가합니다.

내 경험상, 2주 릴리스가 품질을 떨어뜨리느냐는 브라우저 벤더의 문제가 아니라 조직의 계약 문제로 귀결됩니다.

- 지원 버전 계약이 없으면 품질이 아니라 재현성이 떨어집니다.
- 링이 없으면 품질이 아니라 장애 반경이 커집니다.
- 계약 테스트가 없으면 품질이 아니라 탐지 시간이 늘어납니다.

그리고 보안 관점에서는 오히려 “자주 올리는 능력”이 방어력입니다. Firefox 156의 MFSA 문서만 봐도, advisory 게시 방식이 바뀌며 개별 버그 단위로 CVE/advisory를 발행한다고 밝힙니다.[^5] 이런 환경에서 “업데이트를 늦게 하는 운영”은 점점 더 설명하기 어려워집니다.

## 앞으로 지켜볼 것: 문서가 힌트로 주는 운영 신호

2주 릴리스에서 내가 보는 신호는 릴리스 노트의 기능 나열이 아니라, 문서가 반복해서 말하는 운영 포인트입니다.

- SUMO 글에서 “첫 10일간 지원 문의가 평균 30% 증가”한다고 말합니다. 업데이트 파동이 잦아지면 지원 파동도 잦아집니다. 즉, 브라우저 업데이트는 IT의 일이 아니라 지원/운영의 일입니다.[^2]
- Firefox 156 enterprise 릴리스 노트가 “Firefox 156과 ESR 153.3.0에 적용” 같은 문장으로 시작하는 것도 운영 신호입니다. 정책/관리 관점의 변화는 release와 ESR이 서로 엮입니다.[^4]
- MDN 릴리스 노트가 TLS, DOM, WebRTC 같은 “앱을 깨뜨리는 축”을 계속 적는다는 건, 결국 브라우저 업데이트가 API 계약 변화라는 뜻입니다.[^3]

이 신호를 보고도 브라우저 업데이트를 사용자 자율에 맡기면, 2주마다 조직이 같은 일을 반복하게 됩니다.

## 지금 당장 할 일: 체크리스트가 아니라 ‘운영 계약서’로 만들기

여기서 말한 내용을 실행 가능한 형태로 줄이면, 체크리스트가 아니라 계약서 템플릿이 됩니다.

1) 지원 버전 계약
- “보증”하는 Firefox 범위(N, N-1, ESR 여부)
- OS/아키텍처 범위(Windows ARM64 포함 여부는 특히 WebRTC/미디어에서 의미가 큼)[^1]

2) 정책 계약
- 업데이트를 브라우저 자체로 할지(자동), MDM/패키징으로 할지(강제)
- `DisableAppUpdate`와 `AppAutoUpdate`의 관계(동시에 만족하려는 모순 제거)[^9]
- policies.json 배포 경로와 소유권(누가 merge/승인하는지)[^7]

3) 테스트 계약
- 계약 테스트(Contract Smoke)의 최소 항목: TLS/SSO, SW, WebRTC, 다운로드
- 제품 E2E는 계약 테스트의 결과에 따라 범위를 조절
- WebDriver/CI 도구체인 안정성 테스트를 별도 소유

4) 롤백 계약
- “정책/서버 완화 → 링 중단/핀 → 다운그레이드”의 단계 정의
- Firefox 156에서 추가된 `DisableServiceWorkers` 같은 응급 레버의 가용 버전과 적용 범위 기록[^4]

5) 보안 계약
- MFSA 게시를 트리거로 삼아, “최대 지연 허용 시간”을 정한다
- advisory가 개별 버그 단위로 쪼개지는 추세를 감안해, CVE 개수로 우선순위를 매기지 않는다[^5]

결국 Firefox 156은 “업데이트가 더 자주 온다”는 현실을 공식화한 첫 구간 중 하나이고, 2주 릴리스 체계에서 살아남는 방법은 릴리스 노트 읽기보다 지원/정책/테스트/롤백을 계약으로 고정하는 쪽이 비용이 덜 듭니다.

## 참고 자료
- [Firefox 156 Release Notes](https://www.firefox.com/en-US/firefox/156.0/releasenotes/)
- [MDN: Firefox 156 release notes for developers](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/156)
- [Firefox 156 release notes for enterprise admins](https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-156/)
- [MFSA 2026-90: Security Vulnerabilities fixed in Firefox 156](https://www.mozilla.org/en-US/security/advisories/mfsa2026-90/)
- [Firefox new release cadence and what to expect](https://blog.mozilla.org/sumo/2026/08/19/firefox-new-release-cadence-and-what-to-expect/)
- [Choose a Firefox update channel](https://support.mozilla.org/en-US/kb/choosing-firefox-update-channel)
- [Manage Firefox updates](https://support.mozilla.org/en-US/kb/managing-firefox-updates)
- [Customize Firefox using policies.json](https://support.mozilla.org/en-US/kb/customizing-firefox-using-policiesjson)
- [AppAutoUpdate policy documentation](https://firefox-admin-docs.mozilla.org/reference/policies/appautoupdate/)

브라우저 업데이트는 더 이상 사용자 환경 변수가 아니라, 서비스 운영 계약의 일부로 고정해야 하는 배포 파이프라인 구성 요소입니다.

[^1]: <https://www.firefox.com/en-US/firefox/156.0/releasenotes/>
[^2]: <https://blog.mozilla.org/sumo/2026/08/19/firefox-new-release-cadence-and-what-to-expect/>
[^3]: <https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/156>
[^4]: <https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-156/>
[^5]: <https://www.mozilla.org/en-US/security/advisories/mfsa2026-90/>
[^6]: <https://support.mozilla.org/en-US/kb/choosing-firefox-update-channel>
[^7]: <https://support.mozilla.org/en-US/kb/customizing-firefox-using-policiesjson>
[^8]: <https://support.mozilla.org/en-US/kb/managing-firefox-updates>
[^9]: <https://firefox-admin-docs.mozilla.org/reference/policies/appautoupdate/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
