---
title: "Chrome 제로데이 주간에 브라우저 업데이트를 배포 파이프라인으로 굴리는 방법"
description: "링 배포·업데이트 정책·강제 재시작·E2E 최소 세트를 묶어, 제로데이 공지를 운영 체계로 바꾸는 설계"
date: 2026-09-05 12:46:00 +0900
categories: ["Testing", "Browser Update Testing"]
tags: ["chrome", "rollout-rings", "enterprise-policy", "playwright", "e2e-smoke", "security"]
render_with_liquid: false
---

## 제로데이 공지에서 시작하면 항상 늦습니다

보안팀 공지를 보고 “업데이트 하세요”로 끝나는 조직은, 사건이 있을 때마다 같은 혼란을 반복합니다. 브라우저 업데이트는 사용자의 자율 영역처럼 보이지만, 실제로는 (1) OS 패치처럼 강제력이 필요하고 (2) 앱 호환성 리스크가 있고 (3) 적용 완료를 측정해야 하며 (4) 실패 시 빠르게 되돌릴 수 있어야 합니다. 결국 배포 파이프라인 문제입니다.

이번 이슈는 그 사실을 다시 확인시켜 줍니다. 2026-09-03에 올라온 Chrome Stable Channel 업데이트 공지에는 Windows/Mac이 152.0.7977.82/.83, Linux가 152.0.7977.82로 업데이트되며, CVE-2026-85046이 V8의 type confusion이고 “exploit exists in the wild” 문구가 명시돼 있습니다. 그리고 버그 상세는 다수 사용자가 업데이트할 때까지 제한될 수 있다고도 적혀 있습니다.[^1]

이런 공지는 정보가 부족한 상태에서 속도를 요구합니다. 그때 필요한 건 공지 해석 능력이 아니라, 다음을 이미 갖춘 운영 설계입니다.

- Canary/Dev/Stable (필요하면 Beta/Extended Stable까지)로 사용자 풀을 나누는 링 구조
- 자동 업데이트를 강제하면서도 업무 시간/업무 특성에 맞게 유예하는 정책
- 브라우저 버전이 바뀌어도 비즈니스가 죽지 않는지 빠르게 확인하는 E2E 최소 세트

이미 Chrome 152 제로데이 건을 따로 정리한 글이 있습니다. 사건 자체와 패치 프로세스 강제력의 관점은 그 글로 충분합니다. 여기서는 그 다음 단계, 즉 실제로 배포 파이프라인에 넣는 구현을 다룹니다.

- [Chrome 152 제로데이 공지가 패치 프로세스를 강제하는 방식](https://daewooki.github.io/posts/chrome-152-zero-day-forces-patching-process/)

## 링 설계: “채널”과 “링”을 일부러 분리합니다

Chrome에는 Stable/Extended Stable/Beta/Dev/Canary라는 release channel이 있습니다. 관리자는 사용자를 채널에 배치해서 업데이트 시점을 조절할 수 있습니다. Chrome 관리 문서에서도 5개 채널을 소개하고, 대부분은 Stable에, 일부는 Beta/Dev에 두라고 권합니다.[^2]

하지만 현장에서 바로 부딪히는 문제는 이겁니다.

- 채널은 브라우저 공급자(Chrome)의 릴리스 흐름입니다.
- 링은 우리 조직의 위험 허용도/업무 중요도/테스트 커버리지에 맞춘 배포 단위입니다.

채널=링으로 1:1 매핑하면, “Dev는 개발자만”, “Stable은 전사” 같은 단순화에 갇힙니다. 제로데이 대응에서는 특히 곤란합니다. 이유는 두 가지입니다.

1) 제로데이는 Stable에서 터집니다. Dev/Canary는 조기 경보(Early warning)에는 좋지만, 긴급 패치가 Stable로 나올 때는 Stable 자체를 빨리 당겨야 합니다.
2) 업무 중요도는 직군이 아니라 시스템/권한/데이터 민감도로 결정되는 경우가 많습니다. 결제/정산/CS/인사 같은 영역은 브라우저가 멈추면 바로 손실이 납니다.

내가 권하는 구조는 “채널”은 Chrome이 제공하는 그대로 쓰되, “링”은 조직 설계로 따로 정의하는 방식입니다.

### 링 예시(현실적인 타협 버전)

- Ring 0 (실험/감시): Canary 또는 Dev
  - 목적: 다음 주/다음 달에 깨질 것을 미리 발견
  - 대상: IT, QA, SRE, 프론트엔드 리드, 자동화 테스트 운영자
- Ring 1 (조기 적용): Beta 또는 Stable(조기 적용 그룹)
  - 목적: Stable 패치가 나왔을 때, 전사 강제 전에 실제 사용자 환경에서 빠르게 확인
  - 대상: 자원자 + 업무 영향이 상대적으로 낮은 팀 + 자동화 커버리지가 높은 조직
- Ring 2 (표준): Stable
  - 목적: 대부분의 사용자
- Ring 3 (업무 연속성 특수군): Stable 또는 Extended Stable
  - 목적: 키오스크, 콜센터, 의료/제조 현장, 특정 플러그인/레거시 웹앱 의존
  - 대상: 업데이트는 받아야 하지만, 재시작/업무 중단 비용이 큰 군

Chrome 문서에서 “대부분 Stable”, “일부 Beta(예: 5%)”, “IT는 Beta/Dev” 같은 추천이 나오는데, 이 권장사항을 링 설계의 출발점으로 삼을 수 있습니다.[^2]

중요한 건 퍼센트 자체가 아니라, 링이 다음 조건을 만족하도록 설계하는 것입니다.

- Ring 1은 “작지만 결정적(deterministic)”이어야 합니다.
- Ring 1은 “관측 가능(observable)”해야 합니다. (버전 분포, 재시작 완료율, 핵심 플로우 실패율)
- Ring 1은 “업무적으로 방어 가능한 실패”를 허용해야 합니다.

## 업데이트 정책: 강제와 유예를 같이 설계합니다

브라우저 업데이트를 파이프라인으로 만들려면, 다음 두 가지가 동시에 필요합니다.

- 업데이트를 “받게” 만드는 정책
- 업데이트를 “적용하게” 만드는 정책(= 재시작/리런치)

받기만 하고 적용을 안 하면, 취약점은 그대로입니다. Windows에서 특히 흔합니다. 사용자는 Chrome을 며칠씩 켜 두고, 업데이트가 백그라운드로 내려와도 프로세스 리런치를 미룹니다.

### Windows: Google Update를 운영 대상으로 봅니다

Windows에서 Chrome 업데이트는 Google Update로 관리할 수 있습니다. 공식 문서에도 Windows 관리자가 Group Policy로 Google Update를 관리한다고 명시돼 있고, 설정값은 chrome://policy에서 확인하라고 되어 있습니다. 또한 도메인 조인 또는 MDM 관리가 되어 있어야 정책이 제대로 적용된다는 점을 문서에서 강조합니다.[^3]

여기서 “강제/유예”의 핵심은 두 가지 축입니다.

1) 업데이트 체크 빈도
2) 업데이트 억제(업무 시간 회피) 구간

예를 들어 “Time period in each day to suppress auto-update check”는 매일 특정 시각부터 일정 기간 업데이트 체크를 억제할 수 있고, 문서에는 22:00 시작에 480분이면 8시간 억제된다고 예시까지 들어 있습니다.[^3]

이걸 단순히 “업무 시간에는 업데이트하지 마라”로 쓰면, 제로데이 때는 바로 역효과가 납니다. 그래서 링별로 정책 강도를 다르게 가져가야 합니다.

- Ring 0/1: 억제 구간을 짧게(또는 아예 없게) 두고, 체크 빈도도 촘촘히
- Ring 2: 업무 시간 억제 구간을 두되, 제로데이 주간에는 일시적으로 완화
- Ring 3: 억제 구간/재시작 윈도우를 강하게 두되, 강제 기한은 더 짧게(업데이트는 빨리, 중단은 계획적으로)

그리고 채널 전환도 운영에서 중요합니다. Windows 문서에는 “Target Channel override”로 stable/extended를 설정하고, 즉시 안정 채널로 전환하려면 “Rollback to Target version”을 같이 쓰라고 안내합니다.[^3]

이 조합은 “평소에는 Extended Stable로 운영하지만, 제로데이 주간에는 Stable로 당겨야 하는가?” 같은 의사결정에서 카드가 됩니다. 다만 채널을 바꾸는 건 조직 커뮤니케이션 비용이 큽니다. 내 경험상, **채널 전환은 빈번한 제로데이 대응 수단이 아니라 마지막 수단**으로 남기는 쪽이 낫습니다.

### macOS: Keystone(plist)로 ‘업데이트를 끄는 조직’을 막습니다

macOS는 Google Software Update(Keystone)로 업데이트 정책을 관리합니다. 공식 문서에 따르면 전역 정책과 앱별 정책이 있고, `com.google.Keystone.plist`에 설정한 뒤 MDM(Jamf 등)로 배포할 수 있습니다.[^4]

문서에는 `UpdateDefault` 값을 0으로 두면 자동 업데이트(권장)를 켠다고 설명합니다. 반대로 업데이트를 끄는 시나리오도 다루는데, “권장하지 않으며, 끄면 보안 패치가 적용되지 않아 위험하다. 끄더라도 제때 업데이트하는 프로세스가 필요하다”는 경고가 포함되어 있습니다.[^4]

macOS에서 중요한 건 사용자에게 업데이트 UI를 맡기지 않는 것입니다. MDM으로 업데이트 정책을 통제하고, 강제 리런치 정책까지 이어져야 파이프라인이 됩니다.

### Extended Stable의 함정: 보안 패치가 ‘항상’ 동일하지 않을 수 있습니다

Extended Stable은 “기능 업데이트는 늦추되 보안은 따라가자”에 가깝습니다. Chrome 문서에서도 milestone branch를 추가 6주 유지하면서 중요한 보안 수정들을 backport해서 8주마다 새 milestone을 제공한다고 설명합니다.[^5]

다만 같은 문서에서 “가능한 모든 critical/high/medium을 backport하려 노력하지만, 복잡한 변경이나 큰 기능 기반 보안 개선은 Stable에만 있을 수 있다. Stable이 가장 안전하다”는 취지의 문장이 들어가 있습니다.[^5]

즉 Extended Stable은 ‘보안 패치를 늦게 받는다’가 아니라, ‘보안 패치를 다 받지 못할 수도 있다’가 위험 포인트입니다. Ring 3 같은 특수군에만 제한적으로 두고, 제로데이 주간의 대응은 Ring/리런치 정책으로 해결하는 게 더 단단합니다.

## 강제 재시작(리런치): 업데이트 적용률을 SLO로 만들어야 합니다

업데이트 다운로드는 보안팀이 좋아하는 지표고, 리런치 완료율은 실제 보안 수준에 가까운 지표입니다. “업데이트 했어요?”라는 질문을 “업데이트 버전으로 리런치된 프로세스 비율이 목표를 넘었어요?”로 바꾸면 운영이 달라집니다.

Chrome은 이를 위한 정책 세트를 공식으로 제공합니다. “Notify users to restart to apply pending updates” 문서에서 대표적으로 아래 정책들을 조합하라고 설명합니다.[^6]

- RelaunchNotification
  - recommended: 권장 알림
  - required: 기한 내 리런치 강제
- RelaunchNotificationPeriod
  - 알림/유예 기간을 ms로 설정
  - 기본값 604,800,000ms(7일)
- RelaunchWindow
  - 리런치가 일어나는 시간대(시작 시각과 duration)

문서에는 “RelaunchNotification을 required로 두고, RelaunchNotificationPeriod로 리런치 시간을 설정하라”는 식으로 강제 리런치를 안내합니다.[^6]

여기서 현장 적용의 포인트는 세 가지입니다.

1) 전사 강제는 한 번에 하면 반발이 큽니다. 링별로 기한을 다르게 줘야 합니다.
2) 강제 리런치가 업무를 끊을 수 있으니, 링별로 “업무 중단 비용”을 고려한 window가 필요합니다.
3) 제로데이 문구가 뜨면, window를 유지하되 기한(period)을 줄여서 속도를 올리는 편이 낫습니다.

예시로 정리하면 이렇게 가져갈 수 있습니다.

- Ring 0: required, 4~12시간
- Ring 1: required, 12~24시간
- Ring 2: required, 24~48시간
- Ring 3: required, 24시간(또는 더 짧게) + window를 명확히(예: 02:00~04:00)

핵심은 “업무 시간에는 재시작하지 않게”가 아니라, “업무를 끊지 않으면서도 기한 내 적용되게”입니다. 윈도우를 강하게 잡는 링(키오스크/콜센터)은 오히려 기한을 더 짧게 줘야 합니다. 그래야 밤 사이에 확실히 적용됩니다.

추가로 Chrome Enterprise 정책에는 “outdated가 오래되면 유예를 2시간으로 override”하는 류의 정책(RelaunchFastIfOutdated)이 있고, outdated 상태가 기준 일수를 넘으면 RelaunchNotificationPeriod를 2시간으로 덮어쓴다고 설명되어 있습니다.[^7]

이걸 Ring 2/3에 켜면, “계속 미루는 사용자”가 제로데이 때 방어선 밖으로 남는 걸 줄일 수 있습니다. 대신 강제성이 강해지는 만큼, 사내 커뮤니케이션/헬프데스크 대응(재시작 후 세션 복구, 확장 프로그램 이슈)이 따라와야 합니다.

## 테스트 설계: 브라우저 업그레이드용 E2E 최소 세트는 별개입니다

E2E 테스트를 많이 돌리면 안전해질 것 같지만, 브라우저 업데이트 대응에서는 보통 반대입니다.

- 테스트가 많으면 느립니다.
- 느리면 링 배포가 느립니다.
- 느리면 패치 갭이 커집니다.

제로데이 주간의 목표는 “완벽한 회귀”가 아니라 “가장 큰 돈이 오가는 플로우가 브라우저 업데이트로 즉시 죽지 않는지”를 빠르게 확인하는 겁니다.

내가 운영에서 최소 세트로 고정하는 축은 보통 3개입니다.

1) 로그인
- SSO든 이메일/비밀번호든, 결국 세션이 만들어지는지 확인해야 합니다.
- SameSite/Cookie/Storage/redirect 변화가 브라우저 업데이트 때 자주 터집니다.

2) 결제
- 카드 결제/간편결제/3DS/리다이렉트는 브라우저 변화에 취약합니다.
- 결제 성공률이 떨어지면 바로 매출/CS로 연결됩니다.

3) 파일 업로드
- 프론트 업로드는 drag&drop, file picker, multipart, presigned URL 등 브라우저 API/보안 정책 변화의 영향을 받습니다.

이 세 가지는 “브라우저가 바뀌면 비즈니스가 멈추는” 구간을 대표합니다. 그래서 이 세트를 “브라우저 업그레이드 전용 smoke”로 따로 빼고, 나머지 E2E는 정기 회귀로 두는 게 낫습니다.

Chrome 쪽에서도 enterprise testing을 이야기할 때 dev/beta 채널을 조기 경보로 쓰라고 하고, deterministic한 소수 사용자(예: 5~10%)를 dev/beta에 배치하라고 권합니다. 이게 곧 링과 테스트 자동화를 묶을 수 있다는 뜻입니다.[^8]

## 파이프라인 구현: “브라우저 바이너리”를 CI 입력으로 만듭니다

링 배포가 조직/정책 설계라면, 테스트는 파이프라인 설계입니다. 제로데이 주간에 중요한 건 “현재 Stable이 뭔지”가 아니라, “업데이트 전/후 버전을 둘 다 같은 조건에서 돌려 비교”하는 것입니다.

여기서 유용한 게 Chrome for Testing(CfT)입니다. 공식 문서에는 `@puppeteer/browsers` CLI로 Stable 또는 특정 버전의 Chrome for Testing 바이너리를 다운로드하는 예시가 그대로 들어가 있습니다.[^9]

- `npx @puppeteer/browsers install chrome@stable`
- `npx @puppeteer/browsers install chrome@116.0.5793.0`

이 방식의 장점은 “CI에서 특정 버전 브라우저를 재현”할 수 있다는 점입니다. 제로데이 주간에는 보통 아래 두 버전을 돌리고 싶습니다.

- 현재 사내 표준 버전(= 아직 링 2에 남아 있는 버전)
- 새 패치 버전(= 152.0.7977.82 같은 보안 픽스 포함)

### 구현 컨셉

- (A) 버전 감지: Chrome Releases 공지에서 버전과 CVE를 읽어옴
- (B) 바이너리 확보: CfT로 해당 버전 Chrome 다운로드
- (C) smoke 실행: 로그인/결제/업로드를 (구 버전, 신 버전) 각각 실행
- (D) 게이트: 결과가 OK면 링별 정책을 tighten(유예 축소, 강제 리런치)

이 흐름이 되면 보안팀 공지는 “티켓 생성 트리거”가 아니라 “파이프라인 실행 트리거”가 됩니다.

## Playwright로 ‘브라우저 업그레이드 smoke’를 실제로 돌리는 코드

테스트 러너는 Playwright를 예시로 듭니다. 이유는 단순합니다.

- 프로젝트(projects) 기능으로 같은 테스트를 여러 브라우저 설정으로 반복 실행하기 좋습니다.[^10]
- branded browser(Chrome)도 채널로 지정해 실행할 수 있습니다.[^11]

다만 Playwright는 “bundled Chromium과 가장 잘 맞는다”는 점과 “executablePath는 주의해서 써라”고 문서에서 경고합니다.[^12]

그래서 여기서의 포지셔닝은 명확합니다.

- 이 smoke는 “정밀한 브라우저 자동화 호환성 보장”이 아니라
- “브라우저가 바뀌었을 때 핵심 플로우가 즉시 죽는지”를 빠르게 잡는 안전장치입니다.

### 디렉터리 구조

```text
browser-upgrade-smoke/
  package.json
  playwright.config.ts
  tools/
    fetch-chrome.sh
    print-chrome-path.mjs
  tests/
    01-login.spec.ts
    02-checkout.spec.ts
    03-upload.spec.ts
```

### 의존성

- Node.js 20+
- `@playwright/test`
- `@puppeteer/browsers` (CfT 다운로드용)

```bash
npm init -y
npm i -D @playwright/test @puppeteer/browsers
npx playwright install --with-deps
```

`npx playwright install`은 Playwright가 번들로 쓰는 브라우저를 설치합니다. 우리는 CfT Chrome도 별도로 내려받을 거라, CI 이미지/캐시 전략에 따라 조정해야 합니다.

### CfT Chrome 다운로드 스크립트

공식 CfT 문서의 CLI를 그대로 씁니다.[^9]

`tools/fetch-chrome.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:?Usage: fetch-chrome.sh <chrome_version_or_channel>}"

# 예: 152.0.7977.82 또는 stable
npx @puppeteer/browsers install "chrome@${VERSION}" --path .cache/cft
```

다운로드 후 경로가 플랫폼마다 달라서, Node 스크립트로 실제 실행 파일 경로를 찾는 쪽이 실전에서 덜 깨집니다.

`tools/print-chrome-path.mjs`

```js
import fs from 'node:fs';
import path from 'node:path';

const base = path.resolve('.cache/cft');

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else {
      if (process.platform === 'linux' && e.name === 'chrome') console.log(p);
      if (process.platform === 'darwin' && e.name === 'Google Chrome for Testing') console.log(p);
      if (process.platform === 'win32' && e.name.toLowerCase() === 'chrome.exe') console.log(p);
    }
  }
}

walk(base);
```

Linux에서는 보통 `.../chrome-linux64/chrome`가 잡힙니다.

### Playwright 설정: 두 버전 Chrome을 프로젝트로 나눕니다

`playwright.config.ts`

```ts
import { defineConfig } from '@playwright/test';

const baseURL = process.env.BASE_URL || 'https://staging.example.internal';

// 실행 파일 경로는 CI에서 주입합니다.
const chromeOld = process.env.CHROME_OLD_EXE;
const chromeNew = process.env.CHROME_NEW_EXE;

export default defineConfig({
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  projects: [
    {
      name: 'chrome-old',
      use: {
        browserName: 'chromium',
        executablePath: chromeOld
      }
    },
    {
      name: 'chrome-new',
      use: {
        browserName: 'chromium',
        executablePath: chromeNew
      }
    }
  ]
});
```

여기서 `executablePath`는 Playwright 문서가 “extreme caution”을 권하는 옵션입니다.[^12] 그럼에도 이 방식을 쓰는 이유는, 제로데이 주간에 “브라우저 버전 차이”를 입력으로 삼아 smoke를 돌리는 게 목적이기 때문입니다. 테스트가 깨지면 “앱이 깨졌다”일 수도 있고 “러너-브라우저 조합이 미세하게 깨졌다”일 수도 있습니다. 그래서 이 smoke의 실패는 곧바로 배포 중단이 아니라, Ring 1에서의 관측/수동 확인을 촉발하는 신호로 써야 합니다.

### 테스트 1: 로그인(세션 확립)

`tests/01-login.spec.ts`

```ts
import { test, expect } from '@playwright/test';

test('login: session cookie is issued and dashboard loads', async ({ page }) => {
  const email = process.env.E2E_EMAIL!;
  const password = process.env.E2E_PASSWORD!;

  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  // 앱마다 다르지만, 보통 로그인 성공 후 redirect가 일어납니다.
  await expect(page).toHaveURL(/\/dashboard/);

  // 로그인 이후 API가 정상 호출되는지 간단히 확인
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
});
```

### 테스트 2: 결제(샌드박스 결제 성공까지)

`tests/02-checkout.spec.ts`

```ts
import { test, expect } from '@playwright/test';

test('checkout: create order and mark paid (sandbox)', async ({ page }) => {
  const email = process.env.E2E_EMAIL!;
  const password = process.env.E2E_PASSWORD!;

  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await page.goto('/pricing');
  await page.getByRole('button', { name: 'Buy Pro' }).click();

  // 결제 제공자(예: 3DS, redirect)를 쓰면 여기 로직이 더 복잡해집니다.
  // smoke에서는 “주문 생성 → 결제 완료 상태 반영”까지만 통과하면 충분합니다.

  await page.getByLabel('Card number').fill('4242424242424242');
  await page.getByLabel('Expiry').fill('12/34');
  await page.getByLabel('CVC').fill('123');

  await page.getByRole('button', { name: 'Pay' }).click();

  await expect(page.getByText('Payment succeeded')).toBeVisible();
  await expect(page).toHaveURL(/\/billing/);
});
```

실서비스는 카드 입력 필드가 iframe(Stripe Elements 등)인 경우가 흔하고, locator 전략이 달라집니다. 하지만 본질은 같습니다. 브라우저 업데이트로 (a) iframe postMessage (b) 쿠키/세션 (c) redirect (d) 팝업이 깨지면 결제는 바로 죽습니다.

### 테스트 3: 파일 업로드(presigned URL까지)

`tests/03-upload.spec.ts`

```ts
import { test, expect } from '@playwright/test';
import path from 'node:path';

test('upload: file upload completes and appears in list', async ({ page }) => {
  const email = process.env.E2E_EMAIL!;
  const password = process.env.E2E_PASSWORD!;

  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await page.goto('/files');

  const filePath = path.resolve('fixtures/invoice-sample.pdf');
  await page.setInputFiles('input[type="file"]', filePath);

  await expect(page.getByText('Upload complete')).toBeVisible();
  await expect(page.getByRole('row', { name: /invoice-sample\.pdf/ })).toBeVisible();
});
```

### 실행 커맨드(로컬/CI 공통)

```bash
# 1) 두 버전 다운로드
./tools/fetch-chrome.sh 152.0.7977.75
./tools/fetch-chrome.sh 152.0.7977.82

# 2) 실행 파일 경로 추출(플랫폼에 따라 여러 줄이 나올 수 있어 필터링이 필요할 수 있음)
node tools/print-chrome-path.mjs

# 3) 경로를 환경변수로 주입하고 실행
export CHROME_OLD_EXE="/abs/path/to/.../152.0.7977.75/.../chrome"
export CHROME_NEW_EXE="/abs/path/to/.../152.0.7977.82/.../chrome"

export BASE_URL="https://staging.example.internal"
export E2E_EMAIL="e2e-smoke@example.internal"
export E2E_PASSWORD="***"

npx playwright test
```

예상 출력(예시)

```text
Running 6 tests using 2 workers
  3 passed (chrome-old)
  3 passed (chrome-new)

To open last HTML report run:
  npx playwright show-report
```

이 출력은 “완벽”을 의미하지 않습니다. 최소 세트가 두 버전에서 모두 통과하면, 링 배포의 속도를 올릴 수 있는 근거가 됩니다. 하나라도 깨지면, “업데이트를 멈춘다”가 아니라 “Ring 1에서 더 많은 관측 + 결제/로그인/업로드 담당 팀의 즉시 triage”로 넘어가야 합니다.

## 링 배포와 테스트를 연결하는 운영 규칙

### 1) 제로데이 문구가 뜨는 날의 타임라인을 미리 정합니다

이번 공지(2026-09-03)처럼 “in the wild”가 붙으면, 테스트와 배포의 리드타임을 사람의 의지로 줄일 수 없습니다. 규칙이 있어야 합니다.

권장 타임라인(예시)

- T0 (공지 감지): Chrome Releases 공지에서 CVE + in the wild 여부 + 버전 확보[^1]
- T0+1h: CfT 바이너리 다운로드 + smoke(구/신) 실행[^9]
- T0+3h: Ring 0/1에 업데이트 정책 강화 + 리런치 기한 축소(예: 12시간)
- T0+12h: Ring 1의 리런치 완료율/장애 현황으로 Ring 2 확대 여부 결정
- T0+24~48h: Ring 2/3까지 리런치 완료율 목표 달성

이 타임라인에서 핵심은 “T0+1h에 사람이 모여서 회의”가 아니라, smoke가 돌아가고 결과가 자동 공유되는 구조입니다.

### 2) “테스트 통과”가 “즉시 전사 강제”로 연결되면 조직이 망가집니다

테스트는 확신을 주는 도구가 아니라, 불확실성을 줄이는 도구입니다. 브라우저 업데이트에서는 특히 그렇습니다.

- smoke는 false negative(놓침)가 있을 수 있습니다.
- smoke는 false positive(테스트 환경 문제)도 자주 납니다.

그래서 링 배포는 항상 “관측 가능한 작은 링 → 확대”의 형태로 남겨야 합니다. Chrome 문서에서도 일부 사용자를 Beta/Dev에 두는 이유를 “문제 발견과 대응 시간 확보”로 설명합니다.[^2]

### 3) 정책은 링별로 바뀌어야 하고, 정책 변경 자체가 배포 이벤트여야 합니다

업데이트 배포 파이프라인을 만든다는 건 결국 “정책 변경”을 배포한다는 뜻입니다.

- Windows: Google Update 설정(업데이트 체크/억제/채널)
- macOS: Keystone plist
- 공통: 리런치 정책(RelaunchNotification/Period/Window)

정책이 수동 변경이면, 제로데이 주간에는 사람 손이 병목이 됩니다. 정책은 IaC처럼 관리해야 합니다. Admin console을 쓰든, MDM/Intune을 쓰든, 변경 이력과 롤백 경로가 있어야 합니다.

## 함정과 트레이드오프

### Playwright + executablePath는 만능이 아닙니다

Playwright가 경고하는 것처럼, bundled Chromium과의 호환이 가장 좋고, 커스텀 브라우저 경로는 조심해야 합니다.[^12]

그래도 이 설계를 쓰는 이유는, 제로데이 주간에 필요한 건 “브라우저 버전 비교”라는 입력을 가진 자동화이기 때문입니다. 대신 해석을 이렇게 해야 합니다.

- smoke 실패 = 전사 배포 중단이 아니라, Ring 1 관측 강화 + 수동 재현 + vendor bug 여부 확인
- smoke 성공 = 전사 배포 강제의 근거 중 하나

즉 이 smoke는 배포 파이프라인의 gate라기보다, 배포 파이프라인의 속도를 올리기 위한 안전장치입니다.

### Extended Stable은 운영비를 줄이지만, 제로데이 주간에는 의사결정이 더 어려워질 수 있습니다

Extended Stable의 설명 자체에 “Stable이 가장 secure”하다는 문장이 들어가 있습니다.[^5]

조직이 Extended Stable로 가는 순간, 제로데이 주간에는 항상 질문이 생깁니다.

- 지금 이 취약점 패치가 Extended Stable에도 동일하게 backport되었는가?
- backport가 늦거나 불가능하면, Stable로 당길 것인가?

이 질문에 답하려면 정보가 필요하고, 정보는 제로데이 초기에 부족합니다. 그래서 나는 Extended Stable을 “테스트 시간이 필요한 조직을 위한 기본값”이 아니라, “업무 연속성 특수군을 위한 예외”로 두는 편이 낫다고 봅니다.

### 강제 리런치는 보안이 아니라 사용자 경험을 깨뜨리는 작업이기도 합니다

RelaunchNotification을 required로 두면, 사용자는 결국 브라우저가 닫히는 경험을 하게 됩니다.[^6]

그래서 강제 리런치 도입 전에는 아래를 같이 준비해야 합니다.

- 세션 복구 정책(자동 로그인, 탭 복원, SSO 재인증 UX)
- 확장 프로그램/보안 솔루션 충돌 대응
- 헬프데스크 스크립트(“왜 지금 꺼졌는지”, “어떻게 복구하는지”)

이 준비가 없으면, 제로데이 주간에 보안팀이 이기고 IT가 집니다. 운영 체계는 팀 간 합의 위에서만 굴러갑니다.

## 도입 판단 기준: ‘브라우저 패치’를 제품 배포처럼 다룰 준비가 됐는가

이 설계를 적용할지 여부는 기술 문제가 아니라 운영 성숙도 문제입니다. 다음 체크리스트를 만족하면, 제로데이 주간의 혼란을 구조적으로 줄일 수 있습니다.

- 링이 정의돼 있고, Ring 1이 deterministic하며 관측 가능하다.
- 업데이트 “다운로드”가 아니라 “리런치 완료율”을 목표 지표로 가진다.
- 정책 변경이 수동 클릭이 아니라 배포 가능한 변경(IaC/MDM/Intune 프로파일)이다.
- E2E 최소 세트(로그인/결제/업로드)가 빠르게 돌고, 실패 시 triage 루트가 정해져 있다.
- 제로데이 공지(T0) 이후 24~48시간 내 적용 완료라는 목표가 합의돼 있다.

Chrome 152처럼 “in the wild” 문구가 붙는 순간, 빠르게 굴러가는 조직과 느리게 굴러가는 조직의 차이는 보안 의지가 아니라 파이프라인 유무로 갈립니다. 결국 브라우저 업데이트는 사람에게 부탁하는 작업이 아니라, 링과 정책과 테스트를 엮어 자동으로 굴리는 배포 시스템으로 취급하는 게 맞습니다.

## 참고 자료

- [Stable Channel Update for Desktop (2026-09-03)](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html)
- [Chrome browser release channels](https://support.google.com/chrome/a/answer/9027636)
- [Test Chrome browser channels](https://support.google.com/chrome/a/answer/9300510)
- [Notify users to restart to apply pending updates](https://support.google.com/chrome/a/answer/7679871)
- [Manage Chrome updates (Windows)](https://support.google.com/chrome/a/answer/6350036)
- [Manage Chrome updates (Mac)](https://support.google.com/chrome/a/answer/7591084)
- [Extended Stable channel](https://support.google.com/chrome/a/answer/16942104)
- [Chromium release cycle documentation](https://chromium.googlesource.com/chromium/src/+/master/docs/process/release_cycle.md)
- [Download Chrome for Testing binaries](https://developer.chrome.com/docs/automation-and-testing/download-test-binaries)
- [Chrome for Testing availability (GitHub)](https://github.com/GoogleChromeLabs/chrome-for-testing)
- [Implement testing in your enterprise with Chrome](https://developer.chrome.com/docs/automation-and-testing/implement-testing-in-your-enterprise)
- [Playwright test projects](https://playwright.dev/docs/test-projects)
- [Playwright BrowserType documentation](https://playwright.dev/docs/api/class-browsertype)
- [Playwright browsers documentation](https://playwright.dev/docs/browsers)

[^1]: <https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html?amp=1>
[^2]: <https://support.google.com/chrome/a/answer/9027636?hl=en>
[^3]: <https://support.google.com/chrome/a/answer/6350036?hl=en>
[^4]: <https://support.google.com/chrome/a/answer/7591084?hl=en>
[^5]: <https://support.google.com/chrome/a/answer/16942104?hl=en>
[^6]: <https://support.google.com/chrome/a/answer/7679871?hl=en>
[^7]: <https://chromeenterprise.google/policies/relaunch-fast-if-outdated/>
[^8]: <https://developer.chrome.com/docs/automation-and-testing/implement-testing-in-your-enterprise?authuser=2>
[^9]: <https://developer.chrome.com/docs/automation-and-testing/download-test-binaries?authuser=5&hl=en>
[^10]: <https://playwright.dev/docs/test-projects>
[^11]: <https://playwright.dev/docs/browsers>
[^12]: <https://playwright.dev/docs/api/class-browsertype>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
