---
title: "Firefox 159 조직 배포: 기능보다 중요한 변화 포인트"
description: "Firefox 159.0을 정책·업데이트·호환성·점진 롤아웃 관점에서 재해석하고, 배포 전에 확인할 검증 포인트를 정리합니다."
date: 2026-10-30 14:24:00 +0900
categories: ["News", "Web"]
tags: ["firefox", "enterprise-deployment", "browser-policy", "rollout", "web-compat", "webdriver"]
render_with_liquid: false
---

Firefox 159.0이 2026-10-27 Release 채널에 제공됐습니다. 릴리스 노트 상으로도 “Version 159.0, first offered to Release channel users on October 27, 2026”라고 명시돼 있습니다.[^1]

조직 단위로 Firefox 자동 업데이트를 켜 둔 환경이라면, 금요일(2026-10-30 KST)인 지금 시점은 이미 주말~다음 주 초 사이에 플릿 전반으로 159가 확산될 수 있는 타이밍입니다. 여기서 문제는 ‘새 기능’이 아니라 배포 운영 관점의 변수가 늘어난다는 점입니다.

- Release 채널은 2026년 9월부터 2주 주기로 major가 나옵니다.[^2]
- Firefox는 릴리스 단위로도 progressive roll out(일부 사용자부터 점진 활성화)과 실험/feature gate를 운영합니다. 릴리스 노트에 Smart Window의 `/watch`가 “part of a progressive roll out”이라고 적혀 있는 것 자체가 운영 불확실성의 신호입니다.[^1]

이번 글은 [Firefox 159 릴리스 노트](https://www.firefox.com/en-US/firefox/159.0/releasenotes/)와 [MDN의 Firefox 159 for developers](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/159), 그리고 [Firefox admin docs의 Firefox 159 엔터프라이즈 릴리스 노트](https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-159/)를 기준으로, 조직 배포 관점에서 “이번 주에 확인할 것”으로 재구성합니다.[^1]

## 2026-10-27에 ‘무슨 일’이 있었나: 릴리스 채널과 보안 공지부터 확정

Firefox 159.0은 2026-10-27에 Release 채널에 올라갔고, FTP에도 같은 날짜에 159.0 디렉터리가 생성돼 있습니다. 이건 “누가 언제 빌드를 만들었는지”를 배포 파이프라인에서 확인할 때 꽤 유용한 근거가 됩니다.[^3]

보안 측면에서는 MFSA 2026-118이 2026-10-27에 공지됐고 Impact가 high로 표기돼 있습니다. Release 노트의 “Various security fixes.”는 조직 운영 관점에서 정보가 부족하니, 배포 승인 프로세스는 MFSA를 기준으로 도는 게 맞습니다.[^4]

여기서 중요한 포인트는 다음입니다.

1) **배포 시점이 늦어질수록 ‘패치 미적용 기간’이 곧바로 리스크로 계량**됩니다. Release 채널 브랜치는 다음 릴리스가 나오면 곧바로 EOL로 취급되는 구조라서(Release 가지의 보안 지원 기간이 짧음), “다음 버전 나올 때 같이 올리자”가 잘 안 먹힙니다. (Release branch 159의 지원 종료가 2026-11-10으로 표기돼 있습니다.)[^5]

2) 반대로 너무 급하게 밀면, 실제 조직에서 문제를 만드는 건 보통 “보안 패치 그 자체”가 아니라 UI/동작/정책의 경계 변화입니다. 이번 159는 딱 그 케이스가 섞여 있습니다.

## 정책 변화: 릴리스 노트보다 admin docs를 먼저 읽어야 하는 이유

Firefox 159의 엔터프라이즈 변경점은 admin docs에 정리돼 있고, “이 변경은 Firefox 159 / Firefox ESR 153.6.0 / Firefox Enterprise 159에 적용된다”는 형태로 명시돼 있습니다. 즉, 지금 Release 채널만의 이야기가 아니라 ESR 업데이트에도 섞여 들어갈 수 있다는 뜻입니다.[^6]

이번 버전에서 운영 관점으로 제일 위험한 건, 기능이 아니라 정책의 “적용 타이밍”이 달라지는 종류입니다.

### **Cookies 정책: Block 리스트 적용 시 쿠키가 매번 정리됨**

admin docs 릴리스 노트에 따르면 `Cookies` 정책에서 “Block에 포함된 host의 cookies가 policy 적용 때마다 clearing 된다(리스트 변경 시에만 지우던 과거와 다름)”로 바뀌었습니다. 그리고 이 변경은 Firefox Enterprise only로 표기돼 있습니다.[^6]

이 변화는 UI에서 보이는 설정이 아니라, “정책 재적용 이벤트”가 발생하는 환경에서 체감 이슈로 바뀝니다.

- 예: Admin Console 기반으로 정책이 더 자주 재적용되는 환경(OU 이동, posture 변화, device policy refresh)에서는, Block 대상 SaaS에 대해 사용자가 계속 로그아웃되는 것처럼 보일 수 있습니다.
- 예: 기존에는 Block을 “앞으로 막는다” 정도로만 쓰던 팀이, 이제는 사실상 “정책 적용 트리거마다 강제 세션 정리”로 인지해야 합니다.

`Cookies` 정책 자체는 origins 단위로 `Allow/AllowSession/Block/Behavior`를 받는 구조이고, Block은 origins(스킴 포함)으로 넣어야 합니다.[^7]

운영 관점 결론은 간단합니다.

- Block은 “접속 차단”이 아니라 “상태 강제 정리(side effect 포함)”로 취급하고, 세션 유지가 필요한 내부 시스템은 `SanitizeOnShutdown` 예외나 별도 설계로 분리하는 게 안전합니다(이 글에서는 `SanitizeOnShutdown`로 확장하지 않습니다).

### Firefox Enterprise: `SignOut`에 Crash.Action 추가

Firefox 159 엔터프라이즈 노트에는 `SignOut` 정책에 `Crash.Action`이 추가됐고, “브라우저 크래시 시 완전 sign-out 할지, 브라우저 lock으로 갈지”를 정한다고 되어 있습니다. 이 역시 Firefox Enterprise only입니다.[^6]

크래시를 “희귀 이벤트”로 가정하는 팀이 많은데, 실제로는 WebGL/미디어/드라이버/확장 조합에서 크래시는 생각보다 자주 나옵니다. 크래시 이후 UX가 “다시 열면 로그인 풀려 있음”이 되면, 사용자는 Firefox 업데이트를 원인으로 인지하고 헬프데스크로 전화합니다. 이 정책이 들어온 배경은 그 운영 비용을 낮추려는 시도로 보입니다.

Firefox Enterprise 자체가 “관리자가 telemetry/crash/Sync/Remote Settings/update까지 조직 인프라로 호스팅한다”는 구조를 전제로 하고 있고, sign-out/lock이 아예 제품 레벨의 관리 포인트로 들어가 있습니다.[^2]

### SkipTermsOfUse: Enterprise 지원 추가(운영상 이득, 컴플라이언스상 비용)

Firefox 159 엔터프라이즈 노트에서 `SkipTermsOfUse`가 Firefox Enterprise에서 지원된다고 적혀 있고, 실제 정책 문서에는 “true면 startup 시 Terms/Privacy Notice를 표시하지 않고, 관리자가 사용자를 대신해 수락 권한이 있음을 represent한다”라고 되어 있습니다.[^6]

이 정책은 대규모 배포에서 ‘첫 실행 화면’ 때문에 발생하는 문의를 줄이는 데 효과가 큽니다. 대신 문서에 적힌 것처럼, 법무/컴플라이언스 프로세스 관점에서는 “관리자가 사용자 대신 수락”을 조직이 감당할 수 있는지 검토가 필요합니다.[^8]

## 사용자 체감 변화가 배포 사고로 바뀌는 지점: progressive roll out과 단축키 이동

Firefox 159 릴리스 노트의 Smart Window `/watch` 기능은 progressive roll out으로 명시돼 있습니다. 조직 배포에서 progressive roll out이 위험한 이유는, 같은 버전(159.0)인데도 특정 기능이 어떤 PC에서는 보이고 다른 PC에서는 안 보이는 상태가 얼마든지 발생하기 때문입니다. QA에서 재현이 안 되고, 헬프데스크 티켓은 늘어나는 전형적인 패턴입니다.[^1]

또 하나는 단축키 변경입니다. 159에서 “열린 탭 검색”이 `Ctrl+Shift+A`(Win/Linux), `Cmd+Shift+A`(macOS)로 들어오면서, 기존 Add-ons Manager 단축키가 이동했고, 대신 `about:keyboard`에서 재매핑할 수 있게 되어 있습니다. 이건 작은 변경처럼 보이지만, 조직 환경에서는 교육 자료/원격지원 스크립트/셀프헬프 문서가 한 번에 낡습니다.[^1]

이 부분은 “사용자 경험 변화”라서 기술적으로는 사소하지만, 배포 운영 비용이 실제로 튀는 구간입니다. 특히 내부 보안 가이드가 “확장 관리 화면 여는 법”을 안내하는 경우가 많아서, 단축키가 바뀌면 지원팀이 제일 먼저 맞습니다.

## Web 호환성: ‘새 API’보다 위험한 건 기본 활성화/제거/파싱 타이밍 변경

MDN의 Firefox 159 for developers 기준으로, Web 앱 호환성에서 체크해야 할 건 크게 4가지입니다.[^9]

### Scroll-driven animations 기본 활성화

Firefox 159에서 scroll-driven animations이 default enabled로 전환됐습니다.[^9]

조직 환경에서 이게 문제가 되는 케이스는 대체로 두 가지입니다.

- 폴리필(또는 사내 UI 프레임워크)이 “해당 기능이 없다”는 전제에서 동작하면서, 새로 native 지원이 생긴 브라우저에서 오히려 중복 적용/충돌이 나오는 경우
- 성능: 스크롤 이벤트와 애니메이션이 얽히면, 특정 페이지에서 GPU/CPU spike가 발생하는데, 이것이 “브라우저 업데이트 이후 느려졌다”로 귀결되는 경우

이번 릴리스 노트에도 메모리/그래픽 관련 fix가 다수 포함돼 있어서, 특정 하드웨어 조합(특히 Linux/AMD)에서는 regression과 improvement가 동시에 관측될 여지가 있습니다.[^1]

### legacy masonry syntax 제거(개발 조직에는 늦게 터지는 지뢰)

MDN에는 “legacy masonry layout syntax가 제거됐다”고 되어 있습니다. 단, 이 문서 자체도 “Nightly에서 pref 뒤로 켜졌던 문법”이라고 설명합니다.[^9]

조직 배포 관점에서 중요한 건 “지금 당장 사용자 화면이 깨지느냐”보다 다음입니다.

- 사내 디자인 시스템/컴포넌트 라이브러리가 masonry 실험을 Nightly에서 했다가 그대로 남겨 둔 코드가 있는지
- “Firefox만 깨진다”로 들어오는 이슈가 사실은 개발자가 숨겨둔 CSS 실험 플래그 때문인지

이건 중앙 QA에서 잡기 어렵고, 특정 팀/특정 사내 페이지에서만 터집니다.

### HTML Sanitizer API의 동작 시점 변경(결과는 같지만 DOM이 달라짐)

Firefox 159에서 HTML Sanitizer API가 “DOM tree를 만든 뒤 청소”가 아니라 “파싱하면서 제거”로 바뀌었다고 합니다. 결과는 같지만, 인접 텍스트가 한 text node로 합쳐지는 등 DOM node 구조가 달라질 수 있다고 명시돼 있습니다.[^9]

이건 사내 제품에서 다음 같은 형태로 문제를 만듭니다.

- 테스트 코드가 `childNodes.length` 같은 구조적 전제에 기대는 경우(특히 e2e에서 snapshot 비슷하게 DOM을 검사하는 팀)
- 보안/정제 레이어를 브라우저 Sanitizer API와 혼합해 쓰는 경우(예: 일부 위젯만 sanitizing하고 나머지는 서버에서 처리)

Sanitizer API 자체는 보안 기능인데, 배포 운영에서의 리스크는 “보안 강화”가 아니라 “테스트/DOM 처리 코드의 전제 붕괴”입니다.

### scoped custom element registries 지원

Firefox 159에서 scoped custom element registries가 지원된다고 MDN에 정리돼 있습니다. shadow tree 내에서 독립 registry를 만들 수 있어 충돌을 회피하는 목적이라고 되어 있고, `customElementRegistry`가 `Document`, `Element`, `ShadowRoot`에서 사용 가능하다고 합니다.[^9]

이 기능은 폴리필/번들러/마이크로프론트엔드 환경에서 “같은 tag name을 서로 다른 컴포넌트가 정의하는 충돌”을 줄일 수 있습니다. 다만 조직 배포에서 당장 문제를 만드는 쪽은 보통 반대입니다.

- 사내 런타임이 custom element 관련 탐지 로직을 가지고 있고, 브라우저 지원이 없다는 전제에서 fallback을 넣어 둔 경우
- 특정 라이브러리가 scoped registry를 감지하고 코드 path를 바꾸면서, Firefox에서만 동작이 달라지는 경우

결국 배포 체크리스트에는 “기능 사용 여부”가 아니라 “기능이 켜짐으로 인해 코드 path가 바뀌는지”가 들어가야 합니다.

## 자동화/테스트 인프라: WebDriver 변경이 CI를 깨는 방식

MDN의 WebDriver 섹션에 운영 관점에서 바로 영향을 주는 변경이 두 가지 있습니다.[^9]

1) recommended preferences를 user value가 아니라 default value로 설정하도록 바뀌었다고 되어 있습니다. 그 결과, 비정상 종료 시 `prefs.js`에 남지 않는다고 명시돼 있습니다.[^9]

이건 조직의 테스트 파이프라인에서 흔히 쓰는 패턴과 충돌합니다.

- 테스트가 끝난 뒤 profile 디렉터리를 아카이빙하고, `prefs.js` diff로 “이번 런에서 어떤 설정이 바뀌었는지”를 추적하는 팀
- 크래시/강제 종료가 발생한 이후, `prefs.js`를 보고 원인을 역추적하는 팀

이제는 `prefs.js`에 “남아 있다/없다”로 상태를 판단하면 오판할 수 있습니다.

2) `--remote-allow-system-access` 커맨드라인 인자가 제거됐고, 시스템 접근을 허용하려면 `MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1` 환경 변수를 설정하라고 되어 있습니다.[^9]

이건 CI에서 runner가 firefox를 띄울 때 쓰던 실행 옵션이 갑자기 무효가 되는 형태라서, 배포 전에 테스트 파이프라인부터 먼저 깨질 수 있습니다. 특히 Windows runner에서 환경 변수 전달이 스크립트 레벨에서 통일돼 있지 않으면, 플랫폼별로만 실패하는 형태로 나타납니다.

## 업데이트/롤아웃 전략: ESR vs Release, 그리고 ‘업데이트를 통제하는 정책’이 먼저다

Mozilla의 admin docs에는 조직이 선택할 수 있는 채널을 Firefox / ESR / Firefox Enterprise로 나누어 설명하고 있고, Release 채널은 2주 cadence, ESR은 연 1회 major + 그 사이 보안/선별된 quality fix 형태로 설명합니다.[^2]

실제로 운영에서 중요한 포인트는 “어떤 버전을 쓰느냐”보다 “업데이트를 어느 레이어에서 통제하느냐”입니다.

- 브라우저 자체 auto update를 그대로 둘 것인가
- OS/MDM(예: Intune, Jamf, SCCM) 패치 파이프라인으로 통제할 것인가
- 사내 update 서버로 pinning/승격을 할 것인가

Firefox는 업데이트 자체가 in-app에서 어떻게 동작하는지 문서화돼 있고(update XML 조회, staging, 상태 파일 등), 이 레이어를 이해하면 장애 시 원인 분리가 쉬워집니다.[^10]

정책 관점에서는 다음이 기본 축입니다.

- `DisableAppUpdate` / `AppAutoUpdate` / `BackgroundAppUpdate`로 자동 설치와 백그라운드 설치를 분리해 제어할 수 있습니다.[^11]
- `AppUpdatePin`은 “특정 버전 이상으로는 올라가지 않게 막는” 안전장치로 쓸 수 있습니다(값은 점으로 끝나야 함).[^12]
- `AppUpdateURL`로 커스텀 업데이트 서버를 지정할 수 있습니다.[^12]

내 경우(브라우저를 배포 파이프라인으로 굴려 본 경험 기준)에는, “자동 업데이트를 완전히 끄는 것”은 조직의 성숙도가 높지 않으면 결국 보안 부채를 키우는 방향으로 흘렀습니다. 그래서 업데이트를 끄기보다는, ring을 나누고 pin을 걸고, 짧은 주기로 승격하는 형태가 더 안정적이었습니다. 이 방식은 예전에 [Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영](https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/)에서 정리한 구조와 비슷한데, Firefox도 2주 cadence로 넘어온 지금은 똑같이 적용됩니다.[^2]

## 반론과 회의론: 결국 ESR 쓰면 되는 것 아닌가

ESR로 가면 많은 문제가 줄어드는 건 사실입니다. Mozilla도 ESR을 “안정성과 장기 호환성이 필요한 배포 환경에 이상적”이라고 직접 적고 있습니다.[^2]

다만 현실에서는 ESR로만 해결이 안 되는 경우가 있습니다.

- 사내 웹 앱이 최신 Web platform 동작(예: scroll-driven animations 지원 전환)과 맞물려 있고, Firefox만 ESR로 고정하면 개발/QA 환경과 프로덕션 사용자 환경이 벌어짐
- 특정 보안 요구사항 때문에 패치 TAT가 더 짧아야 하고, ESR의 major 고정이 오히려 운영을 복잡하게 만드는 경우
- Firefox Enterprise(관리형 제품)로 가려는 조직은, ‘기능 고정’보다 ‘관리 통제’가 목적이라서 ESR만으로는 요구사항을 못 채움(중앙 정책/SSO/posture/DLP/logging 같은 축).[^13]

결론적으로 ESR은 “업데이트 횟수 감소”에는 강하지만, “조직 요구사항의 다양한 통제”를 대체하지는 못합니다.

## 앞으로 지켜볼 것: Firefox Enterprise의 정책 변동성과 기능의 분산 활성화

Firefox 159의 엔터프라이즈 노트는 ‘양’이 많지 않은데도, 성격이 좋지 않습니다. Cookies처럼 의미가 바뀌는 정책, SignOut처럼 사고(크래시) 처리 정책, SkipTermsOfUse처럼 법무적 함의가 있는 정책이 동시에 들어왔습니다.[^6]

또한 release notes에서 progressive roll out이 공공연히 언급되는 시점이면, 기능의 분산 활성화가 더 늘어날 가능성이 큽니다. 배포 조직 입장에서는 “버전 숫자”를 기준으로 상태를 단정하기가 점점 어려워지고, 기능 플래그/실험/정책의 조합까지 포함한 관측 체계가 필요해집니다.[^1]

## 지금 할 수 있는 일: 159 배포 전 최소 검증(코드 포함)

여기서는 159에서 실제로 깨지기 쉬운 포인트(호환성 + 테스트 인프라 + 정책)를 짧은 시간에 확인하는 형태로 구성합니다. “장난감”이 아니라, 사내 스테이징 URL을 넣어 돌릴 수 있는 형태로 만들었습니다.

### 1) Canary용 Firefox 159.0 바이너리 확보 + 무결성 확인

Linux 기준으로 FTP에서 159.0 tarball과 체크섬을 가져와 검증합니다(아래 경로는 실제 159.0 릴리스 디렉터리에 존재합니다).[^3]

```bash
set -euo pipefail

VER="159.0"
BASE="https://ftp.mozilla.org/pub/firefox/releases/${VER}"

curl -fsSLO "${BASE}/SHA256SUMS"
curl -fsSLO "${BASE}/linux-x86_64/en-US/firefox-${VER}.tar.bz2"

# SHA256 검증: 파일명으로 라인을 골라 체크
grep " linux-x86_64/en-US/firefox-${VER}.tar.bz2$" SHA256SUMS | sha256sum -c -

sudo mkdir -p /opt/firefox-${VER}
sudo tar -xjf "firefox-${VER}.tar.bz2" -C /opt/firefox-${VER} --strip-components=1

/opt/firefox-${VER}/firefox --version
```

예상 출력은 다음 형태입니다.

```text
linux-x86_64/en-US/firefox-159.0.tar.bz2: OK
Mozilla Firefox 159.0
```

### 2) (선택) AI Chatbot 노출을 조직 정책으로 닫기

159 릴리스 노트에는 AI chatbot의 Summarize 동작이 “페이지 텍스트가 아니라 주소를 provider에 보낸다”는 변경이 들어가 있습니다. 텍스트를 보내는 것보다 정보량이 줄 수는 있어도, URL 자체가 민감정보인 조직이 훨씬 많습니다(사내 위키, 케이스 관리, 장애 티켓, 고객 테넌트 URL 등).[^1]

Firefox Enterprise에서는 `AIChatbot` 정책으로 provider와 prompt를 통제할 수 있습니다. 문서에는 built-in provider를 enable/disable하고, prompt suggestion을 제어할 수 있다고 되어 있습니다.[^14]

`/opt/firefox-159.0/distribution/policies.json`에 아래처럼 넣으면, built-in provider를 전부 끄고 Summarize prompt도 꺼서 조직 내 확산 리스크를 줄일 수 있습니다.

```json
{
  "policies": {
    "AIChatbot": {
      "Providers": {
        "BuiltIn": {
          "ChatGPT": false,
          "Copilot": false,
          "Google Gemini": false,
          "Anthropic Claude": false,
          "HuggingChat": false,
          "Le Chat Mistral": false,
          "localhost": false
        }
      },
      "Prompts": {
        "Enabled": false,
        "BuiltIn": {
          "Summarize": false,
          "Explain": false,
          "Quiz": false,
          "Proofread": false
        }
      }
    }
  }
}
```

이 정책은 Firefox/ESR에서는 지원되지 않고 Firefox Enterprise에서만 지원된다고 문서에 명시돼 있습니다.[^14]

### 3) Web 호환성 스모크 테스트: 159에서 바뀐 동작을 자동으로 확인

아래는 “브라우저 자체 기능 변화로 인해 앱 코드 path가 바뀌는지”를 확인하는 스모크입니다. 핵심은 다음 4개를 런타임에서 체크해 결과를 JSON으로 남기는 것입니다.

- scroll-driven animations 지원 여부(159에서 default enabled)[^9]
- legacy masonry syntax 지원 여부(159에서 제거)[^9]
- Sanitizer API의 파싱 중 제거로 인한 텍스트 노드 구조 변화 가능성(159에서 동작 변경)[^9]
- scoped custom element registries 지원 여부(159에서 지원)[^9]

#### 의존성

- Python 3.11+ (예: Ubuntu 24.04/26.04 기본)
- `selenium` 4.x
- geckodriver는 `webdriver-manager`로 런타임에 받습니다(버전 고정이 필요하면 사내 아티팩트로 핀을 걸어야 합니다).

`requirements.txt`:

```text
selenium>=4.20,<5
webdriver-manager>=4,<5
```

`smoke_ff159_webcompat.py`:

```python
import json
import os
import tempfile
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By

from webdriver_manager.firefox import GeckoDriverManager

HTML = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>ff159-smoke</title>
  </head>
  <body>
    <div id="root"></div>
    <script>
      async function runChecks() {
        const out = {};

        // 1) scroll-driven animations enabled by default in FF159
        out.scroll_driven_animations = {
          supports_animation_timeline_scroll: CSS.supports('animation-timeline: scroll()')
        };

        // 2) legacy masonry syntax removed
        out.legacy_masonry = {
          supports_grid_template_columns_masonry: CSS.supports('grid-template-columns: masonry')
        };

        // 3) Sanitizer API behavior shift: ensure setHTML exists, then check node structure
        out.sanitizer_api = { exists_setHTML: (typeof Element.prototype.setHTML === 'function') };
        if (out.sanitizer_api.exists_setHTML) {
          const host = document.createElement('div');
          // Intentionally include an element likely to be removed by sanitizer.
          // We avoid relying on exact removal list; we only check for text-node shape changes.
          host.setHTML('A<noscript>BLOCK</noscript>B');

          const childNodes = Array.from(host.childNodes).map(n => ({
            nodeType: n.nodeType,
            nodeName: n.nodeName,
            text: n.nodeType === Node.TEXT_NODE ? n.nodeValue : null
          }));

          out.sanitizer_api.child_nodes = childNodes;
          out.sanitizer_api.text_node_count = childNodes.filter(n => n.nodeType === Node.TEXT_NODE).length;
          out.sanitizer_api.text_joined = childNodes.some(n => n.nodeType === Node.TEXT_NODE && n.text === 'AB');
        }

        // 4) scoped custom element registries
        out.scoped_custom_element_registries = {
          has_customElementRegistry_on_shadowroot: ('customElementRegistry' in ShadowRoot.prototype),
          has_customElementRegistry_on_document: ('customElementRegistry' in Document.prototype),
          has_customElementRegistry_on_element: ('customElementRegistry' in Element.prototype),
          can_construct_registry: (typeof CustomElementRegistry === 'function')
        };

        document.getElementById('root').textContent = JSON.stringify(out);
        return out;
      }

      window.__ff159 = { runChecks };
    </script>
  </body>
</html>
"""

def serve(dir_path: Path, port: int):
  os.chdir(dir_path)
  httpd = ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
  httpd.serve_forever()

def main():
  ff_bin = os.environ.get("FIREFOX_BINARY")
  if not ff_bin:
    raise SystemExit("FIREFOX_BINARY env is required, e.g. /opt/firefox-159.0/firefox")

  with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    (d / "index.html").write_text(HTML, encoding="utf-8")

    port = 8008
    t = threading.Thread(target=serve, args=(d, port), daemon=True)
    t.start()

    opts = Options()
    opts.binary_location = ff_bin
    opts.add_argument("-headless")

    driver = webdriver.Firefox(
      options=opts,
      service=webdriver.firefox.service.Service(GeckoDriverManager().install())
    )

    try:
      driver.get(f"http://127.0.0.1:{port}/index.html")
      out = driver.execute_script("return window.__ff159.runChecks()")
      print(json.dumps(out, ensure_ascii=False, indent=2))

      # Fail-fast rules tuned for FF159 expectations
      # - scroll-driven animations should be supported
      # - legacy masonry syntax should be unsupported
      if out["scroll_driven_animations"]["supports_animation_timeline_scroll"] is not True:
        raise SystemExit("Expected scroll-driven animations support in FF159")
      if out["legacy_masonry"]["supports_grid_template_columns_masonry"] is not False:
        raise SystemExit("Expected legacy masonry syntax to be removed in FF159")

    finally:
      driver.quit()

if __name__ == "__main__":
  main()
```

실행:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

export FIREFOX_BINARY=/opt/firefox-159.0/firefox
python smoke_ff159_webcompat.py
```

예상 출력(환경에 따라 일부 필드는 달라질 수 있으나, 스크롤/메이슨리 체크는 고정 기대값으로 걸어둠):

```json
{
  "scroll_driven_animations": {
    "supports_animation_timeline_scroll": true
  },
  "legacy_masonry": {
    "supports_grid_template_columns_masonry": false
  },
  "sanitizer_api": {
    "exists_setHTML": true,
    "text_node_count": 1,
    "text_joined": true,
    "child_nodes": [
      {"nodeType": 3, "nodeName": "#text", "text": "AB"}
    ]
  },
  "scoped_custom_element_registries": {
    "has_customElementRegistry_on_shadowroot": true,
    "has_customElementRegistry_on_document": true,
    "has_customElementRegistry_on_element": true,
    "can_construct_registry": true
  }
}
```

이 스모크는 “우리 앱이 이 기능을 쓰는지”를 증명하지는 못합니다. 대신 배포 직전의 목적(159에서 브라우저 기본 동작이 바뀌는 포인트가 실제로 canary에서 관측되는지)을 빠르게 충족시킵니다.

### 4) 테스트 러너(WebDriver) 실행 옵션 업데이트

CI에서 Firefox를 `--remote-allow-system-access`로 띄우던 스크립트가 있다면 159에서 깨질 수 있습니다. MDN에 따르면 이 인자는 제거됐고, `MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1`로 옮겨가야 합니다.[^9]

Linux runner 예시는 다음처럼 바꿉니다.

```bash
export MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1
# 이후 webdriver / marionette 구동
```

Windows PowerShell runner라면:

```powershell
$env:MOZ_REMOTE_ALLOW_SYSTEM_ACCESS = "1"
# 이후 테스트 실행
```

또한 recommended preferences가 user prefs가 아니라 default로 들어가면서 `prefs.js` 잔존성에 기대는 진단 로직이 무력화될 수 있으니, 크래시/비정상 종료 이후 조사 플레이북에서 `prefs.js` 기반 체크를 한 단계 뒤로 미루는 게 안전합니다.[^9]

## 정리: 159에서 조직 배포가 흔들리는 지점은 ‘기능’이 아니라 ‘운영 경계’다

Firefox 159.0(2026-10-27)은 릴리스 노트만 보면 macOS share picker, sidebar passwords, Smart Window `/watch` 같은 사용자 기능 업데이트처럼 보입니다.[^1] 하지만 조직 배포 관점에서 진짜 위험한 지점은 따로 있습니다.

- Cookies처럼 정책의 효과가 “리스트 변경 시”에서 “정책 적용 시마다”로 바뀌면, 운영 이벤트(정책 재적용)가 곧 사용자 장애로 변환됩니다.[^6]
- WebDriver 실행 인자 제거처럼 테스트 인프라가 먼저 무너지면, 릴리스 승인 자체가 지연됩니다.[^9]
- scroll-driven animations 기본 활성화, Sanitizer API 내부 동작 변경은 앱 코드가 브라우저 기능 감지를 통해 다른 path로 들어가는 순간에만 터지기 때문에, 사전 스모크로 “브라우저의 변화가 실제로 관측되는지”부터 확인하는 편이 효율적입니다.[^9]

이번 159는 배포 파이프라인 관점에서 “버전 업”이라기보다 “정책/테스트/호환성 경계면이 한 번씩 흔들리는 릴리스”로 보는 게 맞고, canary에서 관측 가능한 신호를 먼저 확보한 뒤 ring 승격을 걸어야 비용이 줄어듭니다.

## 참고 자료

- [Firefox 159 릴리스 노트](https://www.firefox.com/en-US/firefox/159.0/releasenotes/)
- [MDN: Firefox 159 for developers](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/159)
- [Firefox admin docs: Firefox 159 release notes for enterprise admins](https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-159/)
- [MFSA 2026-118: Security Vulnerabilities fixed in Firefox 159](https://www.mozilla.org/en-US/security/advisories/mfsa2026-118/)
- [Firefox admin docs: Choosing a Firefox release channel](https://firefox-admin-docs.mozilla.org/guides/firefox-channels/)
- [Mozilla Support Blog: Firefox new release cadence and what to expect (2026-08-19)](https://blog.mozilla.org/sumo/2026/08/19/firefox-new-release-cadence-and-what-to-expect/)
- [Firefox Source Docs: In-App Update Process](https://firefox-source-docs.mozilla.org/toolkit/mozapps/update/docs/InAppUpdateProcess.html)
- [Firefox admin docs: AIChatbot policy](https://firefox-admin-docs.mozilla.org/reference/policies/aichatbot/)
- [Firefox admin docs: Cookies policy](https://firefox-admin-docs.mozilla.org/reference/policies/cookies/)
- [Firefox admin docs: BackgroundAppUpdate policy](https://firefox-admin-docs.mozilla.org/reference/policies/backgroundappupdate/)
- [Firefox admin docs: SkipTermsOfUse policy](https://firefox-admin-docs.mozilla.org/reference/policies/skiptermsofuse/)
- [Firefox 156을 배포 파이프라인에 넣는 계약 설계](https://daewooki.github.io/posts/firefox-release-pipeline-contracts/)
- [Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영](https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/)

[^1]: <https://www.firefox.com/en-US/firefox/159.0/releasenotes/?redirect_source=mozilla-org>
[^2]: <https://firefox-admin-docs.mozilla.org/guides/firefox-channels/>
[^3]: <https://ftp.mozilla.org/pub/firefox/releases/159.0/>
[^4]: <https://www.mozilla.org/en-US/security/advisories/mfsa2026-118/>
[^5]: <https://end-of-life.org/firefox/>
[^6]: <https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-159/>
[^7]: <https://firefox-admin-docs.mozilla.org/reference/policies/cookies/>
[^8]: <https://firefox-admin-docs.mozilla.org/reference/policies/skiptermsofuse/>
[^9]: <https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/159>
[^10]: <https://firefox-source-docs.mozilla.org/toolkit/mozapps/update/docs/InAppUpdateProcess.html>
[^11]: <https://firefox-admin-docs.mozilla.org/reference/policies/backgroundappupdate/>
[^12]: <https://mozilla.github.io/policy-templates/>
[^13]: <https://firefox-admin-docs.mozilla.org/guides/firefox-enterprise/>
[^14]: <https://firefox-admin-docs.mozilla.org/reference/policies/aichatbot/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
