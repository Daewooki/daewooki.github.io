---
title: "Firefox 160 배포를 위한 브라우저 업그레이드 계약 재작성"
description: "Firefox 160에서 바뀐 Web API·보안·엔터프라이즈 정책을 배포 관점의 테스트 항목으로 재구성합니다."
date: 2026-11-14 11:56:17 +0900
categories: ["News", "Web"]
tags: ["firefox", "enterprise", "release-notes", "webtransport", "webdriver-bidi", "browser-upgrades"]
render_with_liquid: false
---

## 릴리스 사실관계: 2026-11-10 Stable, Enterprise, 보안 공지까지 한 묶음으로 보기
Firefox 160은 Release 채널에 2026-11-10에 최초 제공되었습니다. 공식 릴리스 노트에 버전/날짜가 명시되어 있고, 같은 문서에서 Web Platform 항목으로 개발자 영향도가 큰 변경(예: Web Speech API `SpeechRecognition` 지원, `::-webkit-input-placeholder` alias 지원)도 함께 언급됩니다. 배포 일정 커뮤니케이션에서는 이 한 줄이 기준점이 됩니다: [Firefox 160 릴리스 노트](https://www.firefox.com/en-US/firefox/160.0/releasenotes/).

엔터프라이즈 배포 관점에서는 “Firefox 160”이라는 이름 아래 실제로 3개의 서로 다른 문서가 동시에 의미를 가집니다.

- 개발자 영향(사내 웹앱/프론트엔드 코드/테스트 도구)을 정리한 문서: [MDN Firefox 160 developer release notes](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/160).[^1]
- 조직 배포/정책 영향(특히 정책 동작 변화)을 정리한 문서: [Firefox admin docs: Firefox 160 release notes](https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-160/).[^2]
- Firefox Enterprise 패키지/관리 콘솔 쪽 변경과 운영 이슈를 정리한 문서: [Firefox Enterprise 160 릴리스 노트](https://www.firefox.com/en-US/firefox/enterprise/160.0/releasenotes/).[^3]

여기에 보안 공지가 하나 더 붙습니다. Firefox 160에서 수정된 취약점은 MFSA 2026-125로 공지되며, 발표일도 2026-11-10으로 동일하고 Impact는 high로 표기되어 있습니다. CVE가 매우 많이 나열되어 있어(그래픽/DOM/네트워킹/JS 등 전 범위) “이번 릴리스는 기능 추가가 적으니 천천히”라는 판단을 하기 어려운 쪽에 가깝습니다. [MFSA 2026-125 (Firefox 160 fixed)](https://www.mozilla.org/en-US/security/advisories/mfsa2026-125/).[^4]

오늘이 2026-11-14 KST라면, Release 채널 배포(2026-11-10) 이후 4일이 지난 시점입니다. 내 경험상 이 구간이 배포 템플릿(체크리스트/승격 규칙)을 업데이트하기 가장 좋습니다. 이유는 단순합니다. 아직 사내에 대규모로 승격되기 전이라 변경을 흡수할 수 있고, 외부에서도 이슈 리포트/패치가 본격화되기 전이라 내가 가진 테스트 체계의 빈틈을 드러내기 쉽습니다.

## 기능이 아니라 “기본값/정책/자동화”가 장애를 만든다는 전제
최근 브라우저 릴리스에서 장애를 만드는 패턴은 대체로 세 가지입니다.

1) Web API가 바뀌어 런타임 에러가 터지는 경우
2) 보안/프라이버시 관련 기본값이 달라져서 인증/네트워크/권한 프롬프트가 어긋나는 경우
3) 자동화(WebDriver 계열)의 이벤트/헤더/타이밍이 바뀌어 E2E가 흔들리는 경우

Firefox 릴리스는 특히 3)에서 체감이 큽니다. 개발자 노트에 WebDriver BiDi 변경이 꾸준히 올라오고, 엔터프라이즈 쪽은 정책 한 줄이 배포 파이프라인을 그대로 멈추게 만들 때가 있습니다. Firefox Enterprise 160에서 `DisableDeveloperTools`가 “재시작 없이 remote automation(WebDriver BiDi, Marionette)을 끌 수 있게” 된 건 전형적으로 배포 장애의 씨앗입니다.[^3]

나는 이전에 Firefox 릴리스를 “배포 파이프라인에 넣는 계약” 형태로 다룬 적이 있고, Chrome 쪽은 2주 Stable 리듬과 승격 후 48시간 리듬을 별도 계약으로 분리해서 운영한 적이 있습니다.
- [Firefox 156을 배포 파이프라인에 넣는 계약 설계](https://daewooki.github.io/posts/firefox-release-pipeline-contracts/)
- [Firefox 159 조직 배포: 기능보다 중요한 변화 포인트](https://daewooki.github.io/posts/firefox-159-enterprise-deployment-checklist/)
- [Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영](https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/)
- [Chrome 157 Stable 승격 후 48시간 배포 리듬 재설계](https://daewooki.github.io/posts/chrome-157-stable-enterprise-rollout-pattern/)

이번 글에서는 그 내용을 반복하지 않고, Firefox 160에서 실제로 문서에 적힌 변화만을 재료로 “브라우저 업그레이드 계약”을 다시 쓰는 데 필요한 테스트 항목을 재구성합니다.

## Web Platform 변화 → 사내 웹앱 호환성 테스트 항목으로 바꾸기
MDN developer release notes는 변경을 “추가/수정/제거”로 서술합니다. 배포 담당자가 해야 하는 일은 이를 “깨질 수 있는 계약”으로 변환하는 것입니다. 내가 쓰는 방식은 간단합니다.

- (A) 런타임에서 예외를 만들 수 있는가
- (B) UI/레이아웃의 미묘한 차이로 회귀를 만들 수 있는가
- (C) 권한/보안 프롬프트로 사용자 플로우가 바뀌는가
- (D) 코드 수정 없이도 탐지 가능한가(정적 분석/feature detection)

### `::-webkit-input-placeholder` alias 지원: 회귀가 생기는 곳은 스타일 “우선순위”
Firefox 160에서 `::-webkit-input-placeholder`가 `::placeholder`의 alias로 지원됩니다. 목적은 호환성이고, 변경 내용 자체는 단순합니다.[^1]

문제는 사내 웹앱에서 placeholder 스타일을 어떻게 구성했느냐에 따라 회귀 양상이 달라진다는 점입니다.

- 기존에 `::placeholder`를 기준으로 theme를 얹고 있었고, 일부 레거시 컴포넌트가 `::-webkit-input-placeholder`를 별도로 썼다면, 이제 Firefox에서도 둘 다 매칭됩니다.
- 둘이 동시에 매칭될 때 “어느 규칙이 이기는지”는 selector specificity/소스 순서에 의해 결정됩니다. 즉, 같은 브라우저 안에서 placeholder가 갑자기 더 연해지거나 더 진해지는 식의 시각 회귀가 생깁니다.

테스트 항목으로는 다음 정도가 실용적입니다.

- 로그인/검색/결제/사내폼의 핵심 input에서 placeholder 대비가 UI 가이드 기준을 만족하는지(스크린샷 diff)
- placeholder 스타일을 커스터마이즈한 컴포넌트 라이브러리(사내 design system)의 “placeholder 관련 selector”가 한 브라우저에서 중복 매칭되는지

이건 단위 테스트로는 잡기 어렵고, 결국 visual regression 쪽에 가까워집니다.

### WebTransport: 이번 릴리스의 실질적인 breaking change
Firefox 160에서 WebTransport 변경이 여러 개 들어왔고, 그중 하나는 명시적으로 breaking change입니다.

- `WebTransport()` constructor가 `headers` 옵션을 받아 extended `CONNECT` 요청에 커스텀 헤더를 붙일 수 있게 됐고, 서버 응답 헤더를 `WebTransport.responseHeaders`로 노출합니다.[^1]
- `WebTransport.exportKeyingMaterial()`이 스펙에 맞게 변경되어 `context` 인자가 필수가 되었고, `outputLength` 인자가 추가되었습니다. 기존에는 32 bytes 고정 반환이었습니다. 인자를 생략하면 코드가 깨집니다.[^1]
- `WebTransportDatagramDuplexStream`의 `incomingHighWaterMark`/`outgoingHighWaterMark`가 제거되고 표준 이름인 `incomingMaxBufferedDatagrams`/`outgoingMaxBufferedDatagrams`로 교체되었습니다.[^1]
- `datagramsReadableType: 'bytes'`로 `transport.datagrams.readable`을 readable byte stream으로 만들고 BYOB로 버퍼 재사용이 가능해졌습니다.[^1]

WebTransport 자체가 모든 조직에서 흔한 기술은 아닙니다. 다만 “쓰는 조직은 진짜로 쓰는” 영역입니다. 예를 들어 브라우저 기반 저지연 스트리밍, 사내 음성/영상, 원격 제어, 공장/현장 단말, 웹 기반 게임/시뮬레이터 같은 것들입니다. 이런 시스템은 브라우저 업그레이드에서 API 한 줄이 바로 장애로 연결됩니다.

Firefox 160의 exportKeyingMaterial 변경은 W3C 스펙과 align 하는 방향이고, Bugzilla에서도 스펙 변경(w3c/webtransport 이슈) 추종을 근거로 정리되어 있습니다.[^5]

배포 계약의 테스트 항목으로 바꿔 쓰면 이렇게 됩니다.

- WebTransport를 쓰는 코드가 있는지 “정적”으로 탐지한다.
- `exportKeyingMaterial()` 호출이 3-인자 형태(`label, context, outputLength`)인지 확인한다.
- 제거된 datagram property(`incomingHighWaterMark`, `outgoingHighWaterMark`)를 참조하는지 확인한다.
- 런타임에서는 WebTransport 지원 여부(feature detection)와 실패 시 fallback 경로가 존재하는지 확인한다.

여기서 포인트는 **WebTransport는 통신 계층이라 E2E만으로는 원인 파악이 늦어지기 쉽다**는 점입니다. 실패가 “네트워크 flaky”로 보이기 때문입니다. 나는 이런 건 배포 파이프라인 초입에서 정적 검사로 먼저 걸러내는 편이 낫다고 봅니다.

### Web Speech API: `SpeechRecognition`의 데스크톱 지원이 의미하는 것
Firefox 160에서 Web Speech API의 `SpeechRecognition` 인터페이스가 데스크톱에서 지원되며, on-device 실시간 speech-to-text를 40개 언어에서 제공한다고 명시되어 있습니다. Android는 미지원이고, remote(cloud) recognition도 미지원입니다.[^1]

이 변화는 기능 자체보다 “권한/프롬프트/오류 모드”가 운영을 흔듭니다.

- 사내 웹앱이 이미 Chrome 기준으로 `SpeechRecognition`을 사용하고 Firefox에서는 graceful degradation을 하고 있었다면, 이제 Firefox에서도 코드 경로가 바뀝니다.
- 마이크 권한 프롬프트가 뜨는 타이밍, 권한이 거부되었을 때의 에러 타입/메시지, 사용자 제스처 요구 여부가 브라우저마다 달라서, 플로우가 예기치 않게 깨질 수 있습니다.
- 자동화 환경(헤드리스/가상 데스크톱)에서는 마이크 디바이스가 없거나 권한이 차단되어 있어서, 기능이 “지원됨”으로 보이더라도 실제 실행이 실패합니다.

테스트 항목으로는 ‘동작’ 검증보다 ‘플로우 안정성’ 검증이 우선입니다.

- `window.SpeechRecognition || window.webkitSpeechRecognition` 존재 여부에 따라 UI가 분기되는지
- 시작 실패 시 사용자에게 안내/대체 입력이 제공되는지
- E2E에서 해당 기능을 끄거나 mocking 할 수 있는지(권한 설정, feature flag)

### `MozScrolledAreaChanged` 이벤트 제거: 레거시/사내용 코드가 의외로 밟는 지뢰
Firefox 160에서 비표준 이벤트 `MozScrolledAreaChanged`가 웹 페이지로는 더 이상 dispatch되지 않습니다. UI 내부에서만 남고, 필요하면 `layout.scrolled-area-changed.content.enabled=true`로 되살릴 수 있다고 MDN에 적혀 있습니다.[^1]

이건 일반 서비스에서는 드문데, 사내 시스템에서는 가끔 밟습니다.

- 오래된 사내 위젯/프레임워크가 특정 Firefox 버전에서만 동작하게 만들어둔 코드가 남아 있는 경우
- “스크롤 영역이 늘어날 때 무언가를 재계산” 같은 기능을 resize/MutationObserver가 아니라 이 이벤트에 걸어둔 경우

테스트 항목은 단순합니다.

- 코드베이스에서 `MozScrolledAreaChanged` 문자열을 grep한다.
- 발견되면 대체 구현을 강제한다(ResizeObserver + scrollHeight polling 조합 등).
- 단기적으로 pref로 살리는 해법은 엔터프라이즈 배포 계약에 넣지 않는다. pref는 다음 버전에서 더 강하게 막히는 경우가 잦고, 결국 부채만 됩니다.

## WebDriver BiDi 변화 → E2E 깨짐 포인트를 “테스트 케이스”로 고정
MDN developer release notes에는 WebDriver BiDi/Marionette 관련 변경이 여러 개 있습니다.[^1]

이 영역은 대개 앱 코드가 아니라 테스트 harness가 깨집니다. 그래서 “사내 웹앱 호환성 테스트”와는 별도의 계약으로 떼어놓는 게 편합니다.

### 헤더 처리 변화: `Set-Cookie`의 개행 분리
Firefox WebDriver BiDi에서 `Set-Cookie` 응답 헤더 처리에 변화가 있습니다. `\n`으로 분리된 값들이 이전처럼 하나로 merge된 문자열이 아니라, 개별 entry로 보이도록 고쳐졌고, `proxy-authenticate`, `www-authenticate` 같은 “newline-merged” 헤더도 동일하게 적용된다고 MDN에 적혀 있습니다.[^1]

이게 왜 E2E를 깨냐면, 테스트 코드가 이런 식으로 작성되어 있는 경우가 있기 때문입니다.

- “응답 헤더 문자열에 특정 쿠키 이름이 substring으로 포함되는지”를 검사한다.
- 혹은 헤더 값을 split하는 로직이 merge된 형태를 전제한다.

테스트 항목으로 바꾸면 다음입니다.

- WebDriver/BiDi로 수집한 응답 헤더에서 `Set-Cookie`를 **배열**로 처리하는지 확인
- 프록시 인증/WWW-Authenticate 헤더를 읽는 테스트가 있다면 동일하게 배열 처리로 회귀 확인

이건 제품 코드가 아니라 테스트 프레임워크 개선이 필요합니다.

### `script.message`의 context id 수정: flaky를 “고치지만”, 기존 workaround를 깨기도 함
preload script가 `window.open`으로 트리거될 때 `script.message` 이벤트의 `context` 필드가 올바른 browsing context id를 반환하도록 수정되었다고 되어 있습니다.[^1]

이런 종류의 수정은 보통 좋은데, 실무에서는 “잘못된 값을 전제로 한 workaround”가 있을 수 있습니다. 예를 들어:

- context id가 잘못 나오는 걸 감안해서 이벤트를 무시하거나 재매핑하는 코드가 있었던 경우
- 특정 타이밍에만 발생하는 버그를 피하기 위해 window.open 흐름을 감지해 스킵하던 경우

테스트 항목은 “수정된 동작을 확인”이 아니라, 기존 workaround가 있다면 제거/단순화로 이어지게 만드는 게 핵심입니다.

### 네트워크 이벤트 모니터링 성능 변경: 타임아웃/순서 의존성 점검
네트워크 이벤트 모니터링에서 “사용되지 않는 security details 계산을 중단”했고, 페이지 로드 중 성능에 가시적 영향을 줄 수 있다고 되어 있습니다.[^1]

여기서 위험은 두 갈래입니다.

- 좋은 방향: 성능 개선으로 인해 이벤트 타이밍이 달라져 flaky가 줄어들 수 있음
- 나쁜 방향: 보안 세부 정보가 “기대하던 시점”에 채워지지 않는 것으로 보이면서, 특정 assertion이 실패할 수 있음

배포 계약에서는 “네트워크 이벤트 기반 assertion이 있는 테스트”를 별도 태그로 묶어 Firefox 160에서 우선 실행하도록 두는 편이 낫습니다. E2E 전체가 아니라, 깨질 확률이 높은 subset만 먼저 때리는 방식입니다.

### Enterprise 160의 핵심: `DisableDeveloperTools`로 remote automation이 즉시 꺼질 수 있음
Firefox Enterprise 160 릴리스 노트에서 가장 눈에 띄는 문장은 이겁니다.

- `DisableDeveloperTools`가 재시작 없이 remote automation(WebDriver BiDi, Marionette)을 disable할 수 있게 됨[^3]

이건 보안팀이 “Developer Tools 차단”을 목적으로 정책을 켰다가, QA/자동화 파이프라인이 하루아침에 멈추는 시나리오를 만들 수 있습니다. 이전에는 재시작이 필요했기 때문에 “정책 적용 → 다음 재시작 시점”이라는 완충이 있었는데, 이제 그 완충이 사라집니다.

테스트 항목으로는 다음 두 가지가 들어가야 합니다.

- Firefox Enterprise 정책 세트에서 `DisableDeveloperTools`를 켜는 경우, 자동화용 ring은 반드시 별도 빌드/별도 정책/별도 프로파일로 분리한다.
- 자동화 실행 전 preflight에서 “remote automation이 가능한지”를 빠르게 체크하고, 불가능하면 정책/환경 문제로 분류해 즉시 fail-fast 한다.

이 항목은 앱 호환성과 무관하게 배포 체계를 멈추는 종류라서, 계약의 상단(최우선 게이트)에 두는 게 맞습니다.

## Enterprise 정책/운영 변화: 배포 계약에서 “정책 재적용”과 “프로파일”을 1급 객체로
Firefox 160 enterprise admin release notes에는 정책 동작 변화가 몇 가지 들어 있습니다.[^2]

### macOS: `DisableMacOSUserPolicies` 추가
Firefox 160에서 `DisableMacOSUserPolicies` 정책이 추가되었고, macOS에서 사용자 preferences/user-scope configuration profiles의 정책을 무시한다고 되어 있습니다.[^2]

이건 macOS 환경에서 정책의 “출처”가 여러 개인 조직에서 의미가 큽니다.

- 회사 MDM으로 기기 수준 정책을 내리면서, 동시에 사용자 범위(profile)로도 뭔가가 내려가는 환경
- BYOD/공용 Mac에서 사용자 범위 프로파일이 섞여 들어가는 환경

배포 계약 관점에서 이건 “새 기능”이 아니라 “정책 우선순위/충돌 모델이 바뀔 수 있음”입니다.

테스트 항목은 이런 식으로 쓰는 게 현실적입니다.

- macOS에서 동일 키가 device-scope와 user-scope에 동시에 존재할 때 최종 정책이 어떻게 되는지(DisableMacOSUserPolicies on/off 각각)
- 보안/프록시/인증서/SSO 관련 정책은 macOS에서 특히 회귀가 크므로, 정책 출처를 명확히 로깅한다

### `Cookies` 정책: Block 목록이 “정책 적용 때마다” clearing
`Cookies` 정책에서 `Block`에 들어간 호스트의 cookies를 “목록이 바뀔 때만” 지우던 동작이, 이제는 “정책이 적용될 때마다” 지우는 것으로 바뀌었다고 명시되어 있습니다.[^2]

이 변화는 보안 측면에서는 납득이 됩니다. 다만 운영에서는 다음 두 가지가 바로 떠오릅니다.

- 정책이 수시로 재적용되는 환경(관리 콘솔, 로그인 시점, 네트워크 변경 시점 등)에서 SSO가 반복 로그아웃처럼 보일 수 있음
- 내부 서비스가 “쿠키 존재”를 세션의 일부로 전제할 때 사용자 불만/헬프데스크 티켓이 폭증할 수 있음

배포 계약에 넣을 테스트는 “쿠키가 지워지는지” 자체가 아니라, 쿠키가 지워져도 서비스 플로우가 견딜 수 있게 되어 있는지를 보는 쪽이 맞습니다.

- 주요 SSO(예: Kerberos/Negotiate 기반 intranet) 재인증 흐름이 UX/에러 없이 복구되는지
- 쿠키 삭제 이후에도 저장된 폼/작업물이 날아가지 않는지

여기서 Firefox 160 릴리스 노트에 intranet NTLM/Kerberos(Negotiate) 로그인 시 프리징이 수정됐다는 항목도 같이 엮습니다. 이런 건 “정책 변화로 재인증이 잦아져도 브라우저가 덜 멈춘다”는 쪽으로 체감이 연결될 수 있습니다.[^6]

### Firefox Enterprise에서 telemetry upload가 locked on
Admin docs에는 Firefox Enterprise에서 `datareporting.healthreport.uploadEnabled`가 locked on이 되고, 사용자가 about:config나 user.js로 끌 수 없으며, Enterprise 보안 이벤트가 이를 통해 전송된다고 적혀 있습니다. 또한 `DisableTelemetry`는 여전히 unsupported라고 명시합니다.[^2]

이건 기술 이슈라기보다 컴플라이언스/내부 정책 이슈로 번지기 쉬운 항목입니다.

- 보안 이벤트 전송(조직 보안 관제) 측면에서는 필요할 수 있음
- 그러나 어떤 조직은 “telemetry라는 이름” 자체를 리스크로 보고 전면 차단을 요구합니다

내 경험상 이런 건 릴리스 직후에 배포 계약에 문장으로 박아두지 않으면, 배포가 한참 진행된 후에 법무/보안 감사에서 되돌아옵니다. 계약에는 “이 설정은 더 이상 사용자가 끌 수 없음”을 적고, 예외 절차(ESR 유지/별도 브라우저 등)를 별도의 운영 문서로 분리하는 쪽이 낫습니다.

### Enterprise 160 릴리스 노트의 “프로파일” 관련 변경
Firefox Enterprise 160에는 운영에 직접적인 변경이 몇 개 더 있습니다.

- Profile management가 비활성화되고 `browser.profiles.enabled`가 locked off[^3]
- primary password controls가 비활성화되고 profile encryption으로 대체[^3]
- Nimbus studies/rollouts, Firefox Labs, Normandy, CFR recommendations 비활성화[^3]
- “More from Mozilla”, `about:welcome` onboarding, address bar interventions 비활성화[^3]

프로파일/암호 관련 변경은 대개 “사용자 지원 문서”, “헬프데스크 스크립트”, “디버깅 가이드”를 깨는 쪽으로 파급됩니다.

- `about:profiles` 기반의 지원 절차가 있었다면, 이제 그 경로가 막힐 수 있습니다.
- primary password(옛 master password) 기능을 안내하던 내부 문서가 있다면 더 이상 맞지 않습니다.

이건 앱 호환성보다 “조직 운영”의 계약에 넣어야 하는 내용입니다.

## 반론과 회의론: 이번 릴리스는 ‘기업 웹앱’ 입장에서 과장된 리스크일 수도 있음
Firefox 160의 developer release notes를 보면 HTML/JavaScript 변화는 “No notable changes”로 되어 있습니다. CSS도 placeholder alias 하나가 눈에 띄는 정도입니다.[^1]

그래서 다음 같은 반론이 가능합니다.

- 우리 조직은 WebTransport를 안 쓴다. 그러면 breaking change는 없다.
- `MozScrolledAreaChanged` 같은 이벤트는 사용자가 거의 없다.
- Web Speech API는 있어도 안 쓰면 그만이다.

이 반론은 절반은 맞습니다. 실제로 많은 조직에서 앱 코드가 깨질 가능성은 높지 않습니다.

다만 내가 “브라우저 업그레이드 계약”을 굳이 다시 쓰자고 주장하는 이유는, 리스크가 앱 코드가 아니라 배포/정책/자동화에서 터지기 때문입니다.

- MFSA 2026-125는 Impact high로 공지되어 있고, CVE가 다수 나열되어 있어 보안 패치 관점에서 업데이트 압력이 강합니다.[^4]
- Enterprise 정책 동작 변화(특히 telemetry locked on, Cookies 재적용 clearing)는 사용자 경험/내부 규정으로 이어집니다.[^2]
- `DisableDeveloperTools`의 remote automation 즉시 disable은 테스트 파이프라인 자체를 끊을 수 있습니다.[^3]

즉 “앱이 안 깨질 것”과 “업그레이드가 안전하다”는 동치가 아닙니다.

## 앞으로 지켜볼 것: progressive roll out과 정책/자동화의 결합
Firefox 160 릴리스 노트에는 일부 기능이 progressive roll out이라고 표기되어 있습니다.[^6]

progressive roll out이 엔터프라이즈에 주는 문제는 재현성입니다.

- 같은 버전(160.0)인데도 사용자 A/B의 UI가 다를 수 있고, 헬프데스크가 “160.0인데 왜 메뉴가 다르죠?”를 받게 됩니다.
- 자동화가 UI 텍스트/메뉴 구조에 의존하면, 점진 배포가 곧 flaky의 원인이 됩니다.

여기에 Enterprise 정책이 결합하면, “버전+정책+rollout 상태”가 계약의 키가 됩니다. 지금 시점에서 확실히 할 수 있는 건 하나입니다. 배포 계약의 식별자에 Firefox 버전만 넣지 말고, 정책 세트의 해시(또는 Git commit)까지 포함시키는 게 맞습니다.

또 하나는 WebTransport 같은 스펙 추종 API의 churn입니다. W3C 스펙이 변하면 브라우저 구현이 따라오고, 그 결과가 breaking change가 됩니다. Firefox 160의 exportKeyingMaterial 변화는 정확히 그 케이스입니다.[^1]

## 지금 계약서에 바로 넣을 “Firefox 160 업그레이드 테스트 항목” 템플릿
내가 실제로는 문서/리포지토리로 관리하는 형태를, 여기서는 바로 복사해 쓸 수 있는 템플릿으로 적습니다. 형식은 Markdown + 체크리스트를 선호합니다. Jira 티켓으로 옮겨도 구조가 유지되기 때문입니다.

### 1) 릴리스 식별
- 대상 버전: Firefox 160.0 (Release 채널 최초 제공 2026-11-10) — [Firefox 160 릴리스 노트](https://www.firefox.com/en-US/firefox/160.0/releasenotes/)[^6]
- 엔터프라이즈 문서 기준: [MDN Firefox 160 developer release notes](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/160), [Firefox admin docs: Firefox 160](https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-160/)[^1]
- 보안 공지: [MFSA 2026-125](https://www.mozilla.org/en-US/security/advisories/mfsa2026-125/)[^4]

### 2) 호환성 게이트(사내 웹앱)
- placeholder 스타일 회귀
  - `::placeholder` vs `::-webkit-input-placeholder` 중복 매칭으로 placeholder 색/opacity가 달라지지 않는지
  - 핵심 폼(로그인/검색/결제/업무등록) 스크린샷 diff
  - 근거: Firefox 160에서 `::-webkit-input-placeholder` alias 지원[^1]

- WebTransport 사용 여부 및 breaking change 대응
  - 코드베이스에서 `exportKeyingMaterial(` 호출 탐지
  - 호출이 3-인자 형태인지(`label, context, outputLength`)
  - `incomingHighWaterMark`/`outgoingHighWaterMark` 참조 금지
  - 근거: Firefox 160 WebTransport 변경 및 breaking change[^1]

- 음성 입력 UI/권한 플로우
  - `SpeechRecognition` 지원 시 UI 경로가 활성화되면서도 권한 거부/디바이스 없음에서 안전하게 실패하는지
  - 근거: Firefox 160 데스크톱 Web Speech API 지원[^1]

- 레거시 이벤트 제거
  - `MozScrolledAreaChanged` 참조가 남아 있으면 차단
  - 근거: Firefox 160에서 웹 페이지로 dispatch 중단[^1]

### 3) 자동화 게이트(E2E)
- WebDriver BiDi 헤더 파싱
  - `Set-Cookie`를 string 하나로 가정하는 assertion 제거
  - `www-authenticate`, `proxy-authenticate`도 동일
  - 근거: Firefox 160 WebDriver BiDi 헤더 처리 변경[^1]

- preload + `window.open` 관련 이벤트 라우팅
  - `script.message`의 context id workaround 존재 여부 점검
  - 근거: Firefox 160 WebDriver BiDi 변경[^1]

- 성능/타임아웃
  - 네트워크 이벤트 기반 테스트 타임아웃 재평가
  - 근거: security details 계산 중단으로 인한 성능/타이밍 변화 가능[^1]

- remote automation 차단 정책
  - `DisableDeveloperTools` 적용 시 자동화가 즉시 끊길 수 있으므로, automation ring은 별도 정책 세트 사용
  - 근거: Firefox Enterprise 160 변경[^3]

### 4) 엔터프라이즈 정책 게이트
- macOS 정책 출처 충돌
  - `DisableMacOSUserPolicies` on/off 각각에서 최종 정책이 기대대로인지
  - 근거: Firefox 160 정책 추가[^2]

- Cookies 정책 재적용 효과
  - `Cookies.Block` 대상 도메인이 정책 재적용 때마다 로그아웃/세션 파괴를 유발하는지
  - 근거: Firefox 160 정책 동작 변화[^2]

- telemetry locked on
  - 내부 규정/가이드 문서에 반영(기술적으로 사용자가 끌 수 없음)
  - 근거: Firefox Enterprise 정책 변화[^2]

- 프로파일/암호 UX
  - profile management 비활성화로 내부 지원 절차/문서가 깨지지 않는지
  - 근거: Firefox Enterprise 160 변경[^3]

## 계약을 강제하는 최소 자동화: 정적 스캔 + 런타임 스모크(실행 가능한 코드)
WebTransport 같은 항목은 “실제 서버 붙여서 통합 테스트”가 가장 정확하지만, HTTP/3 환경까지 포함하면 준비 비용이 큽니다. 배포 직후 4일(지금 시점)에는 일단 다음 두 층을 깔아두는 게 효율이 좋습니다.

- 1층: 정적 스캔으로 breaking change 가능성이 있는 코드를 빠르게 찾기
- 2층: Firefox를 실제로 띄우는 런타임 스모크로 UI/이벤트/권한 모델의 급격한 변화를 감지

아래 예시는 “사내 웹앱 모노레포(프론트엔드 패키지 여러 개)”를 가정한 형태입니다. Node 기반으로 CI에 넣기 쉽고, 로컬에서도 그대로 재현됩니다.

### 디렉터리 구조
```text
firefox160-contract-check/
  package.json
  scripts/
    scan-webtransport.mjs
    run-smoke.mjs
  smoke-app/
    server.mjs
    public/
      index.html
      placeholder.html
      scroll-event.html
      speech.html
```

### 1) WebTransport breaking change 정적 스캔
`scripts/scan-webtransport.mjs`
```js
import fg from 'fast-glob';
import fs from 'node:fs/promises';

const targets = process.argv.slice(2);
if (targets.length === 0) {
  console.error('Usage: node scripts/scan-webtransport.mjs "src/**/*.{js,ts,tsx}"');
  process.exit(2);
}

const files = await fg(targets, {
  onlyFiles: true,
  ignore: ['**/node_modules/**', '**/dist/**', '**/build/**', '**/.next/**'],
});

const findings = [];

for (const file of files) {
  const text = await fs.readFile(file, 'utf8');

  // 1) exportKeyingMaterial 호출에서 인자 개수 추정(정교한 AST까지는 아니더라도 1차 게이트로 충분)
  //    Firefox 160부터 (label, context, outputLength) 3개가 사실상 필수.
  const reEKM = /\.exportKeyingMaterial\s*\(([^\)]*)\)/g;
  for (const m of text.matchAll(reEKM)) {
    const inside = m[1].trim();
    // 쉼표 개수로 대충 인자 수 추정(문자열/객체 리터럴에 쉼표가 들어가면 오탐 가능)
    const argc = inside === '' ? 0 : inside.split(',').length;
    if (argc < 3) {
      findings.push({
        file,
        kind: 'webtransport-exportKeyingMaterial-argc',
        detail: `exportKeyingMaterial() called with ~${argc} arg(s): (${inside.slice(0, 80)}...)`,
      });
    }
  }

  // 2) 제거된 non-standard datagram property 사용 탐지
  for (const prop of ['incomingHighWaterMark', 'outgoingHighWaterMark']) {
    if (text.includes(prop)) {
      findings.push({ file, kind: 'webtransport-removed-datagram-prop', detail: prop });
    }
  }

  // 3) 새 표준 property로의 마이그레이션 여부 힌트(참고용)
  for (const prop of ['incomingMaxBufferedDatagrams', 'outgoingMaxBufferedDatagrams']) {
    if (text.includes(prop)) {
      findings.push({ file, kind: 'webtransport-standard-datagram-prop', detail: prop });
    }
  }
}

if (findings.length === 0) {
  console.log('OK: no WebTransport contract violations found');
  process.exit(0);
}

console.log(`FOUND: ${findings.length} item(s)`);
for (const f of findings) {
  console.log(`- ${f.kind}: ${f.file} :: ${f.detail}`);
}

// 배포 계약에서는 “의심 항목 발견 시 fail”이 기본값이 낫다.
process.exit(1);
```

이 스크립트가 커버하는 사실 근거는 명확합니다.

- Firefox 160에서 `exportKeyingMaterial()`이 스펙에 맞게 바뀌면서 `context` 필수, `outputLength` 추가(32 bytes 고정 반환 종료)[^1]
- `incomingHighWaterMark`/`outgoingHighWaterMark` 제거 및 표준 property로 교체[^1]

실무에서는 여기서 한 단계 더 나가서 AST 기반으로 인자 개수를 정확히 계산하거나(예: TypeScript compiler API), 호출 결과를 32 bytes 전제로 쓰는 코드 패턴까지 잡기도 하는데, Firefox 160 대응 초기에는 이 정도의 fail-fast가 충분히 효과가 있습니다.

### 2) 런타임 스모크: Selenium으로 Firefox를 실제로 띄워서 확인
Playwright도 선택지이지만, “조직이 배포한 Firefox 160”을 그대로 대상으로 삼으려면 시스템 Firefox + geckodriver 조합이 CI에서 다루기 더 예측 가능합니다.

`smoke-app/server.mjs`
```js
import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
app.use(express.static(path.join(__dirname, 'public')));

const port = process.env.PORT ? Number(process.env.PORT) : 3100;
app.listen(port, '127.0.0.1', () => {
  console.log(`smoke app listening on http://127.0.0.1:${port}`);
});
```

`smoke-app/public/placeholder.html`
```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>placeholder smoke</title>
    <style>
      input {
        font-size: 20px;
        padding: 10px;
        width: 420px;
      }

      /* 의도적으로 둘 다 정의: Firefox 160부터 ::-webkit-input-placeholder가 매칭될 수 있음 */
      input::placeholder { color: rgb(0, 128, 0); opacity: 1; }
      input::-webkit-input-placeholder { color: rgb(255, 0, 0); opacity: 1; }
    </style>
  </head>
  <body>
    <h1>placeholder</h1>
    <input id="i" placeholder="Type here" />
  </body>
</html>
```

`smoke-app/public/scroll-event.html`
```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>MozScrolledAreaChanged smoke</title>
    <style>
      body { margin: 0; }
      #log { font-family: monospace; padding: 12px; }
      #spacer { height: 200vh; background: linear-gradient(#eee, #ccc); }
    </style>
  </head>
  <body>
    <div id="log">waiting...</div>
    <div id="spacer"></div>

    <script>
      let fired = 0;
      document.addEventListener('MozScrolledAreaChanged', () => {
        fired++;
        document.querySelector('#log').textContent = 'MozScrolledAreaChanged fired: ' + fired;
      });

      // 대체 경로: ResizeObserver가 존재하면 그걸로도 로그를 남김
      if ('ResizeObserver' in window) {
        const ro = new ResizeObserver(() => {
          document.querySelector('#log').textContent =
            'ResizeObserver tick (MozScrolledAreaChanged should be absent on Firefox 160)';
        });
        ro.observe(document.documentElement);
      }

      // 일부러 DOM을 늘려서 scroll area 변화를 유도
      setTimeout(() => {
        const extra = document.createElement('div');
        extra.style.height = '50vh';
        extra.style.background = '#fdf6e3';
        document.body.appendChild(extra);
      }, 300);

      window.__getMozScrolledAreaChangedCount = () => fired;
    </script>
  </body>
</html>
```

`scripts/run-smoke.mjs`
```js
import { spawn } from 'node:child_process';
import { Builder, By, until } from 'selenium-webdriver';
import firefox from 'selenium-webdriver/firefox.js';

// 1) 로컬 서버 기동
const server = spawn(process.execPath, ['smoke-app/server.mjs'], {
  stdio: ['ignore', 'pipe', 'pipe'],
  env: { ...process.env, PORT: '3100' },
});

const waitForLine = (stream, pattern, timeoutMs = 8000) =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('server start timeout')), timeoutMs);
    stream.on('data', (buf) => {
      const s = buf.toString('utf8');
      if (s.includes(pattern)) {
        clearTimeout(timer);
        resolve();
      }
    });
  });

await waitForLine(server.stdout, 'listening on');

// 2) Firefox 실행(시스템 Firefox + geckodriver 필요)
// geckodriver가 없거나 Enterprise 정책으로 remote automation이 막혀 있으면 여기서 실패할 수 있음.
const opts = new firefox.Options();
// CI에서 headless가 필요하면 아래 주석 해제
// opts.addArguments('-headless');

let driver;
try {
  driver = await new Builder().forBrowser('firefox').setFirefoxOptions(opts).build();
} catch (e) {
  console.error('FAILED to start Firefox session.');
  console.error('If you are on Firefox Enterprise, check DisableDeveloperTools policy: remote automation may be disabled without restart in 160.0');
  throw e;
}

try {
  // placeholder 스타일 확인
  await driver.get('http://127.0.0.1:3100/placeholder.html');
  const input = await driver.findElement(By.css('#i'));
  await driver.wait(until.elementIsVisible(input), 3000);

  // placeholder는 computedStyle로 바로 읽기 애매해서, 여기서는 “두 selector를 동시에 넣었을 때 눈에 띄는 색 차이”를 수동/스크린샷 기반으로 보도록 유도.
  // 자동화에서 더 강하게 하려면 스크린샷을 찍어 diff 툴로 비교한다.
  const title1 = await driver.getTitle();

  // MozScrolledAreaChanged 제거 확인
  await driver.get('http://127.0.0.1:3100/scroll-event.html');
  await driver.sleep(1200);
  const fired = await driver.executeScript('return window.__getMozScrolledAreaChangedCount()');

  console.log(JSON.stringify({
    placeholderPage: title1,
    mozScrolledAreaChangedFired: fired,
    note: 'On Firefox 160, MozScrolledAreaChanged should not fire for web pages (expect 0).'
  }, null, 2));

  if (Number(fired) !== 0) {
    console.error('UNEXPECTED: MozScrolledAreaChanged fired. Your environment may have the pref enabled.');
    process.exitCode = 1;
  }
} finally {
  await driver.quit();
  server.kill('SIGTERM');
}
```

실행 방법(Windows/macOS/Linux 공통의 최소 형태):

```bash
# Node.js 22+ 권장
npm init -y
npm i express selenium-webdriver fast-glob

# geckodriver 설치 후 PATH에 노출되어 있어야 함
# macOS: brew install geckodriver
# Linux: distro 패키지 또는 GitHub 릴리스
# Windows: Chocolatey 등으로 설치 후 PATH 설정

node scripts/scan-webtransport.mjs "../YOUR_REPO/**/*.{js,ts,tsx}"
node scripts/run-smoke.mjs
```

예상 출력 예시:
```json
{
  "placeholderPage": "placeholder smoke",
  "mozScrolledAreaChangedFired": 0,
  "note": "On Firefox 160, MozScrolledAreaChanged should not fire for web pages (expect 0)."
}
```

이 스모크의 근거는 명시적입니다.

- `MozScrolledAreaChanged`는 Firefox 160에서 더 이상 웹 페이지로 dispatch되지 않음[^1]

그리고 실패 시 진단 메시지에 넣어둔 `DisableDeveloperTools` 관련 문장은 Enterprise 160 릴리스 노트에 근거가 있습니다.[^3]

## 결론: Firefox 160에서 계약서를 다시 쓰게 만드는 건 Web API보다 “정책과 자동화” 쪽이다
Firefox 160을 배포 템플릿 관점에서 요약하면 이렇게 정리됩니다.

- 앱 코드 호환성 측면에서 즉시 깨질 만한 건 WebTransport 쪽이 대표적이고, 그 외는 시각/권한 플로우/레거시 이벤트 제거 같은 유형입니다.[^1]
- 보안 업데이트 압력은 MFSA 2026-125(Impact high)로 명확하게 존재합니다.[^4]
- 엔터프라이즈 배포에서 가장 큰 변곡점은 (1) 정책 재적용의 의미가 달라진 Cookies 동작, (2) telemetry upload locked on, (3) `DisableDeveloperTools`가 remote automation을 즉시 끊을 수 있게 된 점입니다.[^2]

그래서 Firefox 160을 계기로 브라우저 업그레이드 계약을 다시 쓸 때, “웹앱 기능 테스트”보다 먼저 위 3개를 최상위 게이트로 올려놓는 편이 운영 비용을 확실히 줄입니다.

## 참고 자료
- [Firefox 160 release notes for developers (MDN)](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/160)
- [Firefox 160 릴리스 노트](https://www.firefox.com/en-US/firefox/160.0/releasenotes/)
- [Firefox Enterprise 160 릴리스 노트](https://www.firefox.com/en-US/firefox/enterprise/160.0/releasenotes/)
- [Firefox admin docs: Firefox 160 release notes](https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-160/)
- [MFSA 2026-125: Security Vulnerabilities fixed in Firefox 160](https://www.mozilla.org/en-US/security/advisories/mfsa2026-125/)
- [MDN: WebTransport.exportKeyingMaterial()](https://developer.mozilla.org/en-US/docs/Web/API/WebTransport/exportKeyingMaterial)
- [W3C WebTransport Specification](https://www.w3.org/TR/webtransport/)
- [Bugzilla 2079306: WebTransport exportKeyingMaterial spec change follow-up](https://bugzilla.mozilla.org/show_bug.cgi?id=2079306)

[^1]: <https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/160>
[^2]: <https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-160/>
[^3]: <https://www.firefox.com/en-US/firefox/enterprise/160.0/releasenotes/>
[^4]: <https://www.mozilla.org/en-US/security/advisories/mfsa2026-125/>
[^5]: <https://bugzilla.mozilla.org/show_bug.cgi?id=2079306>
[^6]: <https://www.firefox.com/en-US/firefox/160.0/releasenotes/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
