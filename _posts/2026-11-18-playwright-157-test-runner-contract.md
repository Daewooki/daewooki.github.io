---
title: "Playwright 1.57 업그레이드 체크리스트: 테스트 러너 계약 점검"
description: "1.57의 Chrome for Testing 전환을 계기로 CI 비용과 플레이키를 줄이려면 runner·브라우저·아티팩트·병렬화 계약을 다시 고정해야 합니다."
date: 2026-11-18 15:51:12 +0900
categories: ["Testing", "Playwright"]
tags: ["playwright", "ci", "flaky-tests", "sharding", "test-artifacts"]
render_with_liquid: false
---

## 2026-11-18 KST 기준: “1.57이 막 나왔다”는 착시부터 정리

2026-11-18 KST 시점에 PyPI의 `playwright` 프로젝트 페이지에서 “Released: Nov 14, 2026”로 보이는 값은 **1.57.0이 아니라 1.65.2** 릴리스입니다. [PyPI의 playwright 프로젝트 페이지](https://pypi.org/project/playwright/)에는 최신 릴리스가 2026-11-14로 표시됩니다.[^1]  
반대로 **`playwright==1.57.0` 자체는 2025-12-09 업로드**로 확인됩니다. [PyPI의 playwright 1.57.0 버전 페이지](https://pypi.org/project/playwright/1.57.0/)에 업로드 날짜가 2025-12-09로 노출됩니다.[^2]

그럼에도 1.57을 지금 다시 꺼내 점검할 이유는 명확합니다. 1.57은 “테스트 러너 계약이 조용히 바뀌는” 대표적인 분기점이었고, 그때 생긴 균열이 이후 버전 업에서도 반복됩니다. 특히 1.57의 핵심 변화인 Chrome for Testing 전환은, 겉으로는 “기존 테스트는 계속 통과할 것”이라고 하지만 실제로는 CI 비용·아티팩트 크기·플레이키 양상이 같이 움직입니다. [Playwright 1.57 릴리스 노트](https://playwright.dev/docs/release-notes)에도 해당 전환이 명시되어 있습니다.[^3]

내가 말하는 테스트 러너 계약은 대략 아래 다섯 가지를 “명시적으로 고정해 두는 규칙”입니다.

- 어떤 브라우저 바이너리(채널/빌드)를 돌리는가
- headless/headed 조합이 무엇이고, 둘의 차이를 허용하는가
- trace/screenshot/video를 언제 만들고 언제 버리는가
- 병렬화(내부 parallel)와 분산(shard)을 어디까지 허용하는가
- flaky를 어디로 격리하고, CI 게이팅과 관측 비용을 어떻게 분리하는가

1.57을 계기로 이 계약들을 한 번에 재정의하면, 다음 업그레이드(1.58~1.65…)에서 회귀가 나도 “테스트가 깨진 건지, 계약을 어긴 건지”를 분리해서 대응할 수 있게 됩니다.

## 1.57의 브라우저 스위치가 의미하는 것: Chrome for Testing과 headless shell

1.57에서 Playwright는 Chromium 대신 **Chrome for Testing 빌드 기반으로 동작**하도록 바뀌었습니다. 그리고 같은 “chromium” 계열이라도 실행 모드에 따라 바이너리가 갈립니다.

- headed 모드: `chrome`
- headless 모드: `chrome-headless-shell`

이 내용은 [Playwright 1.57 릴리스 노트](https://playwright.dev/docs/release-notes)와 [.NET 릴리스 노트](https://github.com/microsoft/playwright/blob/main/docs/src/release-notes-csharp.md) 둘 다에 같은 취지로 들어가 있습니다.[^3]

릴리스 노트는 “기능적 변화는 없을 것”이라고 말하지만, 테스트 러너 관점에서 기능 변화가 없어도 행동 변화는 생깁니다.

- OS 레벨 폰트/렌더링/안티앨리어싱 차이로 screenshot diff가 튀는 케이스
- headless가 `chrome-headless-shell`로 갈라지면서 “로컬 headed로만 재현되던 문제”가 CI headless에서만 튀는 케이스
- 실행 파일·캐시 구성 변화로 CI 캐시 적중률이 흔들리는 케이스

그리고 1.57 노트에는 중요한 예외가 붙어 있습니다.

- **Arm64 Linux에서는 계속 Chromium을 사용**

즉, 같은 `browserName: 'chromium'`을 쓴다고 해도 amd64 Linux와 arm64 Linux가 “서로 다른 계열(Chrome for Testing vs Chromium)”을 밟을 수 있습니다. 1.57 릴리스 노트에 그대로 적혀 있습니다.[^3]

여기서부터가 계약 이야기입니다. 업그레이드가 아니라 “환경이 바뀐 것”으로 취급해야 합니다.

- CI가 amd64라면: 로컬도 amd64 Docker/VM로 맞춰 재현 비용을 줄이는 편이 낫습니다.
- CI에 arm64가 섞이면: 동일 테스트에 대해 아키텍처별 차이를 허용할지(분리) 금지할지(통일) 결정을 해야 합니다.

이 결정 없이 그냥 업그레이드만 하면, 플레이키가 늘어도 원인을 “테스트 코드 탓”으로 오판하게 됩니다.

## 브라우저 채널을 고정한다는 말의 의미: “번들드” vs “시스템”

Playwright에서 “채널 고정”이라고 하면 두 층위가 섞입니다.

1) Playwright가 다운로드해 제공하는 번들드 브라우저를 쓸 것인가  
2) OS에 설치된 branded 브라우저(Chrome/Edge 등)를 `channel`로 붙일 것인가

Playwright의 `channel` 옵션은 문서에 정리되어 있고, `chrome`, `chrome-beta`, `chrome-dev`, `chrome-canary`, `msedge` 계열을 선택할 수 있습니다. [TestOptions.channel 문서](https://playwright.dev/docs/api/class-testoptions)와 [params.md의 browser-option-channel](https://github.com/microsoft/playwright/blob/main/docs/src/api/params.md)에 같은 내용이 있습니다.[^4]

여기서 트레이드오프가 뚜렷합니다.

- 번들드(Playwright가 내려받는) 브라우저: Playwright 버전에 종속되며, 업그레이드가 곧 브라우저 업그레이드입니다.
- 시스템 브라우저(`channel`): OS 패키지/회사 정책/업데이트 링에 종속됩니다. 테스트 러너 업그레이드와 브라우저 업그레이드를 분리할 수 있지만, 반대로 말하면 “브라우저 업데이트 운영”을 직접 해야 합니다.

브라우저 업데이트 운영을 파이프라인으로 굴리는 쪽을 선택했다면, 예전에 내가 정리한 [Chrome 제로데이 주간에 브라우저 업데이트를 배포 파이프라인으로 굴리는 방법](https://daewooki.github.io/posts/chrome-zero-day-rollout-pipeline/)이나 [Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영](https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/)처럼, 브라우저를 의존성으로 다루는 계약이 필요합니다.

Playwright 1.57에서 Chrome for Testing로 바뀐 순간부터는, 번들드 브라우저조차 “사실상 branded Chrome 계열”이 됩니다. 그래서 아래 같은 식의 원칙을 팀 규칙으로 못 박는 게 낫습니다.

- E2E는 기본적으로 번들드 브라우저만 허용한다(Playwright 업그레이드로만 브라우저가 바뀐다)
- 시스템 `channel`은 특정 프로젝트(예: enterprise 정책 검증)에서만 허용한다
- `channel`을 쓰는 프로젝트는 브라우저 업데이트 링/롤백 절차를 문서화한다

이 원칙이 없으면 “업그레이드 후 갑자기 CI에서만 실패”가 나왔을 때, 범인을 Playwright로 볼지 Chrome 정책으로 볼지부터 싸우게 됩니다.

## trace/screenshot/video 수집 정책: 아티팩트도 비용 모델로 관리합니다

Playwright는 trace/screenshot/video를 기본으로는 꺼 둡니다. 대신 `use` 옵션에서 정책을 코드로 고정할 수 있고, `retain-on-failure` 같은 모드가 문서에 정의돼 있습니다. [test-use-options 문서](https://playwright.dev/docs/test-use-options)와 [Trace viewer 문서](https://playwright.dev/docs/trace-viewer)에 `retain-on-failure`가 설명되어 있습니다.[^5]

여기서 중요한 건 “무조건 많이 남기자”가 아니라, 실패를 분류하는 비용을 줄이자는 쪽입니다.

- screenshot은 싸고 빠릅니다. UI가 깨진 건지, 네비게이션이 잘못된 건지 1차 분류에 충분합니다.
- video는 용량이 커지지만, 애니메이션/전환/hover 같은 타이밍 문제를 잡는 데 도움이 됩니다.
- trace는 가장 무겁지만, 네트워크·DOM 스냅샷·스텝 단위 정보를 제공해서 “CI에서만 재현” 문제를 가장 빨리 끝냅니다.

내 기준의 계약은 이렇습니다.

- PR(게이트)에서는: 실패·재시도에 대해서만 trace를 남긴다.
- main(머지 후)에서는: 실패에 대해서는 video도 남긴다.
- nightly(관측)에서는: trace를 더 넓게 남기되, 보관 기간을 짧게 한다.

그리고 플레이키를 잡을 때 가장 중요한 건 “실패한 첫 시도”와 “재시도에서 통과한 시도”를 비교하는 겁니다. 이게 되면 flaky 원인이 앱인지 테스트인지, 혹은 리소스인지 분류가 빨라집니다.

Playwright는 릴리스 노트에서 trace 모드로 `'retain-on-failure-and-retries'`를 언급하며, 플레이키 비교에 좋다고 설명합니다. [릴리스 노트(1.58 섹션 상단의 개선점)](https://playwright.dev/docs/release-notes)에서 해당 모드가 소개됩니다.[^3]

또한 현재 문서의 TestOptions에는 trace 모드로 `'retain-on-failure-and-retries'`가 정의되어 있습니다. [TestOptions.trace 문서](https://playwright.dev/docs/api/class-testoptions)에도 동일 모드가 나옵니다.[^4]

정리하면, 아티팩트 정책은 기능이 아니라 비용/관측 계약입니다. 이걸 코드로 못 박아 두면, 업그레이드 때마다 “이번엔 trace 켜서 봐야 하나?” 같은 회의가 사라집니다.

## 1.57의 숨은 플레키 감소 포인트: webServer.wait로 준비 신호를 계약화

1.57의 변화 중 내가 실제로 플레키를 가장 많이 줄였던 건, 화려한 브라우저 전환이 아니라 `webServer.wait`입니다.

Playwright Test의 `testConfig.webServer`에 `wait` 필드가 추가됐고, stdout/stderr 로그가 정규식에 매칭될 때까지 기다릴 수 있습니다. [Playwright 1.57 릴리스 노트의 “Waiting for webserver output”](https://playwright.dev/docs/release-notes)에 예제가 그대로 있습니다.[^3]

CI 플레키에서 빈도가 높은 유형이 아래입니다.

- 서버 프로세스는 떴는데 준비가 안 됐다(DB migration, warm-up, cache 준비)
- 포트가 가변인데 baseURL은 고정으로 박혀 있다
- readiness endpoint가 없거나, 프록시/게이트웨이 뒤에 있어 health check가 신뢰할 수 없다

`webServer.wait`는 readiness를 HTTP가 아니라 로그로 잡을 수 있어서, “서버 준비 전 페이지 접근”류의 플레이키를 통째로 줄입니다.

아래는 실제로 돌릴 수 있는 구성 예시입니다. Express로 E2E 전용 서버를 띄우고(포트 0), 로그에서 포트를 캡처해 baseURL을 맞춥니다.

### 실행 가능한 예시: Express + Playwright Test + webServer.wait

#### 1) package.json

```json
{
  "name": "pw157-runner-contract-demo",
  "private": true,
  "type": "commonjs",
  "scripts": {
    "start:e2e": "node server/app.js",
    "test:e2e": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "^1.57.0",
    "typescript": "^5.7.0"
  },
  "dependencies": {
    "cookie-parser": "^1.4.6",
    "express": "^4.19.2",
    "uuid": "^11.0.3"
  }
}
```

#### 2) server/app.js

```js
const express = require('express');
const cookieParser = require('cookie-parser');
const { v4: uuidv4 } = require('uuid');

const app = express();
app.use(express.urlencoded({ extended: false }));
app.use(cookieParser());

// 아주 단순한 세션 저장소(데모용). 실제 서비스라면 redis/db로 갑니다.
const sessions = new Map();

app.get('/healthz', (req, res) => {
  res.status(200).send('ok');
});

app.get('/login', (req, res) => {
  res.status(200).send(`
    <html>
      <body>
        <h1>Login</h1>
        <form method="post" action="/login">
          <label>
            Email
            <input name="email" type="email" />
          </label>
          <label>
            Password
            <input name="password" type="password" />
          </label>
          <button type="submit">Sign in</button>
        </form>
      </body>
    </html>
  `);
});

app.post('/login', async (req, res) => {
  // 로그인 과정에서 외부 의존성이 있다고 가정하고 지연을 조금 섞습니다.
  await new Promise(r => setTimeout(r, 150));

  const { email, password } = req.body;
  if (!email || !password) return res.status(400).send('missing credentials');

  const sessionId = uuidv4();
  sessions.set(sessionId, { email, createdAt: Date.now() });
  res.cookie('sid', sessionId, { httpOnly: true });
  res.redirect('/');
});

app.get('/', async (req, res) => {
  const sid = req.cookies.sid;
  const sess = sid ? sessions.get(sid) : null;
  if (!sess) return res.redirect('/login');

  // 렌더링 전에 API 호출이 있다고 가정한 지연
  await new Promise(r => setTimeout(r, 100));

  res.status(200).send(`
    <html>
      <body>
        <h1>Dashboard</h1>
        <p data-testid="user-email">${sess.email}</p>
        <a href="/logout">Logout</a>
      </body>
    </html>
  `);
});

app.get('/logout', (req, res) => {
  const sid = req.cookies.sid;
  if (sid) sessions.delete(sid);
  res.clearCookie('sid');
  res.redirect('/login');
});

// 핵심: 포트 0으로 띄우고, stdout 로그로 “준비 완료”를 선언합니다.
const server = app.listen(0, '127.0.0.1', () => {
  const addr = server.address();
  console.log(`Listening on port ${addr.port}`);
});
```

#### 3) playwright.config.js (1.57의 webServer.wait 적용)

```js
const { defineConfig } = require('@playwright/test');

const isCI = !!process.env.CI;

module.exports = defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: isCI,

  // CI 리소스는 명시적으로 제한하는 편이 재현성과 비용에 유리합니다.
  workers: isCI ? 4 : undefined,
  retries: isCI ? 1 : 0,

  // 아티팩트 정책(계약)
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },

    screenshot: 'only-on-failure',
    video: 'retain-on-failure',

    // flaky를 보려면 “실패 시도 + retry 시도”를 같이 남기는 게 핵심입니다.
    trace: 'retain-on-failure-and-retries'
  },

  webServer: {
    command: 'npm run start:e2e',
    reuseExistingServer: !isCI,

    // 1.57에서 추가된 wait: stdout 정규식 매칭까지 대기
    wait: {
      stdout: /Listening on port (?<my_server_port>\d+)/
    }
  },

  // @quarantine 같은 토큰은 테스트 타이틀에서 추출할 수 있습니다.
  // (격리 전략은 뒤에서 설명합니다)
  projects: [
    {
      name: 'e2e',
      grepInvert: /@quarantine/
    },
    {
      name: 'quarantine',
      grep: /@quarantine/,
      retries: 2
    }
  ]
});
```

`webServer.wait` 예제에서 named capture group을 쓰면 Playwright가 해당 값을 environment variable로 제공할 수 있고, 릴리스 노트는 `MY_SERVER_PORT` 형태로 접근하는 예시를 보여줍니다. [Playwright 1.57 릴리스 노트의 동일 섹션](https://playwright.dev/docs/release-notes)에 그대로 있습니다.[^3]

#### 4) tests/login.spec.ts

```ts
import { test, expect } from '@playwright/test';

const baseURL = `http://127.0.0.1:${process.env.MY_SERVER_PORT ?? '3000'}`;

test.use({ baseURL });

test('user can sign in and see dashboard', async ({ page }) => {
  await page.goto('/login');

  await page.getByLabel('Email').fill('dev@example.com');
  await page.getByLabel('Password').fill('pw');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByTestId('user-email')).toHaveText('dev@example.com');
});

test('quarantine example: logout is flaky in CI @quarantine', async ({ page }) => {
  // 의도적으로 격리 태그를 달아 둔 테스트(데모)
  await page.goto('/login');
  await page.getByLabel('Email').fill('dev@example.com');
  await page.getByLabel('Password').fill('pw');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await page.getByRole('link', { name: 'Logout' }).click();
  await expect(page.getByRole('heading', { name: 'Login' })).toBeVisible();
});
```

#### 5) 실행

```bash
npm ci
npx playwright install --with-deps --only-shell
npm run test:e2e
```

Playwright의 브라우저 설치는 `npx playwright install --with-deps`로 문서에 안내돼 있고, headless shell만 필요할 때는 `--only-shell`로 전체 브라우저 다운로드를 줄일 수 있습니다. 이는 [Installation/Intro 문서](https://playwright.dev/docs/intro)와 [Browsers 문서](https://playwright.dev/docs/browsers)에 각각 언급되어 있습니다.[^6]

이 구성을 넣고 나면, 서버 준비 타이밍 때문에 나는 플레이키는 “테스트 문제”가 아니라 “계약 위반(ready 전에 시작)”으로 분류되어 사라집니다.

## shard/parallel 전략: 비용을 줄이려다 플레이키를 늘리는 흔한 패턴

Playwright에서 병렬화는 두 종류입니다.

- 한 머신 내부 worker 병렬화(`workers`, `fullyParallel`)
- 여러 머신/잡으로 나누는 sharding(`--shard`)

Playwright는 공식 문서에서 sharding을 CI에서의 확장 방법으로 설명하고, `--shard` 사용 예시를 제공합니다. [Continuous Integration 문서](https://playwright.dev/docs/ci)에 sharding 언급이 있고, 별도 페이지로 [Sharding 문서](https://playwright.dev/docs/test-sharding)가 있습니다.[^7]

특히 sharding 문서는 “균형 잡힌 분배를 원하면 `fullyParallel: true`를 권장”한다고 적습니다. 이게 중요한 이유는 기본 shard 단위가 “테스트 파일”이라, 파일당 테스트 수/시간 편차가 크면 shard 간 편차가 바로 비용으로 변하기 때문입니다. [Sharding 문서의 권장 사항](https://playwright.dev/docs/test-sharding)에 그대로 나옵니다.[^8]

여기서 러너 계약은 단순합니다.

- CI에서는 `workers`를 자동(코어 기반)으로 두지 말고 상한을 고정합니다.
- shard를 늘릴수록, 개별 shard의 `workers`는 낮춰 “동시 브라우저 수”의 총합을 제어합니다.
- 앱이 병렬 부하를 못 버티면(공유 DB, rate limit, 외부 SaaS), 빨간불을 테스트가 대신 맞습니다. 이건 flaky가 아니라 환경 제약입니다.

### GitHub Actions 예시: 4 shards + workers 4

```yaml
name: e2e
on:
  pull_request:

jobs:
  playwright:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        shardIndex: [1, 2, 3, 4]
        shardTotal: [4]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 24

      - run: npm ci

      - run: npx playwright install --with-deps --only-shell

      - name: Run shard
        run: npx playwright test --project=e2e --shard=${{ matrix.shardIndex }}/${{ matrix.shardTotal }}

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: pw-report-${{ matrix.shardIndex }}
          path: |
            playwright-report
            test-results
```

이 방식의 장점은 단순합니다. shard별로 실패/trace/video가 분리되어 올라오니, 실패 분석을 shard 단위로 자를 수 있습니다. 단점은 보고서 머지가 필요해지는 순간부터 추가 작업이 생긴다는 점입니다. 1.57 릴리스 노트에 `testConfig.tag`가 merge-reports에 유용하다고 적혀 있는데, 이런 분산 실행을 염두에 둔 기능입니다. [Playwright 1.57 릴리스 노트의 New APIs 섹션](https://playwright.dev/docs/release-notes)에 `testConfig.tag`가 언급됩니다.[^3]

## flaky quarantine: 재시도는 기술이 아니라 운영 정책입니다

Playwright는 retries를 공식 기능으로 제공합니다. 설정은 `retries` 또는 `test.describe.configure()`로 줄 수 있고, 문서에 동작과 결과 분류가 정리되어 있습니다. [Retries 문서](https://playwright.dev/docs/test-retries)와 [test-configuration 문서](https://playwright.dev/docs/test-configuration)에 설정 방법이 있습니다.[^9]

여기서 흔한 사고는 이겁니다.

- “CI에서만 가끔 실패한다” → retries를 2~3으로 올린다 → CI는 계속 초록인데, 실제로는 flaky가 방치된다

그래서 quarantine을 계약으로 정의합니다.

- 게이트에 포함되는 테스트는 retries를 최소(보통 0~1)로 둡니다.
- retry가 1회라도 발생하면, 그 사실이 관측돼야 합니다(리포트/로그/지표).
- “불안정하지만 가치가 있는 테스트”는 quarantine으로 보내고, 게이트에서 제외하되 흔적(trace/video/screenshot)은 남깁니다.

Playwright는 테스트에 `skip/fixme/fail` 같은 annotation을 제공하고, `fixme`는 “느리거나 crashy”할 때 쓰라고 문서에 적혀 있습니다. [Annotations 문서](https://playwright.dev/docs/test-annotations)에서 `fixme`의 용도를 설명합니다.[^10]

다만 annotation은 “테스트를 안 돌리는 방법”이고, quarantine은 “테스트를 돌리되, 게이트에서 분리하는 방법”입니다. 성격이 다릅니다.

내가 자주 쓰는 실전 패턴은 두 단계입니다.

1) 타이틀에 `@quarantine`를 붙여 grep 기반으로 분리
2) quarantine 프로젝트는 retries를 올리되, trace는 실패+재시도를 전부 남기게 유지

Playwright는 `@` 토큰을 타이틀에서 추출해 tags로 들고 갈 수 있다고 문서에 적어둡니다. [TestCase.tags 문서](https://playwright.dev/docs/api/class-testcase)는 tags가 타이틀의 `@` 토큰에서도 추출된다고 밝힙니다.[^11]

이 패턴의 핵심은 “플레이키를 숨기지 말고 격리한다”입니다. 그래야 업그레이드 직후에 실패가 늘어도, 게이트 실패와 관측 실패를 분리해서 비용 폭발을 막습니다.

## 리소스 제약(arm64 Linux 포함)을 러너 계약에 포함시키는 방법

1.57에서 Arm64 Linux는 Chromium을 계속 사용한다고 명시되어 있습니다. 즉, 같은 Playwright 버전에서도 아키텍처가 다르면 브라우저 계열이 갈릴 수 있습니다. [Playwright 1.57 릴리스 노트](https://playwright.dev/docs/release-notes)에 그대로 있습니다.[^3]

여기서 선택지는 세 가지입니다.

1) E2E는 amd64만 허용한다(가장 단순, 재현성 최고)
2) arm64도 허용하되, 스냅샷/비주얼 테스트는 아키텍처별로 분리한다
3) 모든 실행을 Docker 이미지로 통일한다(로컬 재현성 강화)

Docker는 특히 “로컬에서 CI 재현”에 가장 직결됩니다. Playwright는 공식 Docker 이미지를 문서로 제공합니다. [Docker 문서](https://playwright.dev/docs/docker)에 `mcr.microsoft.com/playwright` 사용 예시가 있습니다.[^12]

또한 MCR 태그에는 arm64 변형 태그가 따로 존재합니다. [Microsoft Artifact Registry의 Playwright 이미지 태그 목록](https://mcr.microsoft.com/product/playwright)에서 arm64 태그를 확인할 수 있습니다.[^13]

중요한 건 “arm64에서 돈이 싸다”가 아니라, **테스트 러너 계약에 아키텍처를 포함시키느냐**입니다. 포함시키지 않으면 다음 현상이 생깁니다.

- 개발자는 x86 로컬에서만 확인한다
- CI는 arm64에서만 돌린다
- 실패는 arm64에서만 난다
- 원인은 브라우저 계열/폰트/라이브러리인데, 테스트 코드만 계속 만진다

이건 낭비입니다. 업그레이드로 인한 플레이키가 아니라, 계약 부재가 만든 플레이키입니다.

## 1.57에서 같이 바뀐 것들: Node 버전, Speedboard, 그리고 “느린 테스트”의 비용화

1.57 릴리스 노트에는 Playwright Docker 이미지의 Node.js 버전이 바뀌었다는 언급도 있습니다. 1.57에서 “Playwright docker images switched from Node.js v22 to Node.js v24 LTS”라고 적혀 있습니다. [Playwright 1.57 릴리스 노트](https://playwright.dev/docs/release-notes)에 들어가 있습니다.[^3]

이 변화는 “내 테스트가 Node API에 의존”하거나, “Docker 이미지 안에서 빌드까지 같이” 하는 경우에만 의미가 있습니다. 테스트 실행만 하고 빌드는 밖에서 한다면 영향이 제한적입니다. 하지만 mono repo에서 “테스트 러너 = 빌드 런타임”으로 묶어 쓰는 팀은 Node 업그레이드 회귀가 E2E 플레이키처럼 보일 수 있습니다.

또 하나. 1.57은 HTML reporter에 Speedboard 탭을 추가합니다. 느린 테스트를 정렬해서 보여준다고 릴리스 노트가 설명합니다. [Playwright 1.57 릴리스 노트의 Speedboard 항목](https://playwright.dev/docs/release-notes)이 근거입니다.[^3]

Speedboard는 단순한 UI가 아니라 shard 비용을 줄이는 도구입니다.

- 어떤 테스트 파일이 느린지(= 특정 shard를 망가뜨리는지)
- “왜 느린지”가 wait/timeout 남발인지, 서버 준비 지연인지

이런 걸 정량적으로 보게 해줍니다. 이후에 할 일은 보통 두 가지로 떨어집니다.

- 진짜 느린 경로(앱 성능/DB 성능)를 고친다
- 테스트 구조를 바꿔 느린 테스트의 분산을 개선한다(파일 분리, fullyParallel, shard 수 조정)

업그레이드 직후에 CI 비용이 갑자기 오르면, 많은 팀이 “workers를 줄인다”부터 시작합니다. 그런데 workers를 줄이면 느려질 뿐이고, 플레이키의 원인을 숨기기도 합니다. Speedboard로 느린 지점을 먼저 드러내는 게 순서가 맞습니다.

## 점검 리스트: 1.57을 계기로 “테스트 러너 계약”을 문서+코드로 고정

아래 항목을 만족하면, 업그레이드 이후 회귀/플레이키가 나도 원인 범위를 초반에 줄일 수 있습니다.

### 1) 브라우저/채널 계약

- 1.57부터 chromium 계열이 Chrome for Testing 기반으로 바뀐다는 사실을 팀 문서에 명시합니다.[^3]
- Arm64 Linux는 1.57 기준으로 Chromium을 쓴다는 예외를 계약에 포함합니다.[^3]
- `channel`을 쓸지 말지 결정하고, 쓴다면 허용 범위(`chrome`, `msedge` 등)를 config로 고정합니다.[^4]

### 2) headless/headed의 동일성 계약

- CI는 headless를 기본으로 두되, 로컬 재현도 headless로 맞출 수 있게 스크립트를 제공합니다.
- screenshot diff가 중요한 팀은 viewport를 고정합니다(렌더링 변수를 줄입니다).

### 3) 아티팩트 수집 계약

- `screenshot: 'only-on-failure'`, `video: 'retain-on-failure'`, `trace: 'retain-on-failure-and-retries'` 같은 정책을 config에 박습니다.[^5]
- trace viewer로 조사한다는 전제를 운영 문서에 넣습니다.[^14]

### 4) 병렬화/샤딩 계약

- sharding을 쓸 경우 `fullyParallel: true`를 기본으로 두고, shard/job 설계를 비용 모델로 관리합니다.[^8]
- CI에서는 workers를 “자동”이 아니라 “상수”로 제한합니다.

### 5) flaky quarantine 계약

- retries를 올려 초록을 만드는 게 아니라, quarantine으로 분리해 초록과 관측을 분리합니다.[^9]
- annotation(`fixme/skip`)은 “아예 안 돌리는 테스트”에만 씁니다.[^10]
- `@quarantine` 같은 토큰을 grep로 분리하고, tags 추출 규칙을 이용해 프로젝트를 나눕니다.[^11]

### 6) webServer readiness 계약

- 1.57의 `webServer.wait`를 써서 준비 신호를 stdout/stderr 기반으로 고정합니다.[^3]

이 리스트를 “업그레이드 체크리스트”로만 쓰면 효과가 제한적입니다. **테스트 러너 계약**은 문서로 남기고, config/CI 스크립트로 강제할 때 비용과 플레이키가 동시에 줄어듭니다.

## 참고 자료

- [Playwright 릴리스 노트](https://playwright.dev/docs/release-notes)[^3]
- [Playwright .NET 릴리스 노트(release-notes-csharp.md)](https://github.com/microsoft/playwright/blob/main/docs/src/release-notes-csharp.md)[^15]
- [Playwright PyPI 프로젝트 페이지](https://pypi.org/project/playwright/)[^1]
- [Playwright 1.57.0 PyPI 버전 페이지](https://pypi.org/project/playwright/1.57.0/)[^2]
- [Playwright Sharding 문서](https://playwright.dev/docs/test-sharding)[^8]
- [Playwright CI 문서](https://playwright.dev/docs/ci)[^7]
- [Playwright parallelism 문서](https://playwright.dev/docs/test-parallel)[^16]
- [Playwright test-use-options 문서(trace/video/screenshot 정책)](https://playwright.dev/docs/test-use-options)[^5]
- [Playwright Trace viewer 문서](https://playwright.dev/docs/trace-viewer)[^14]
- [Playwright retries 문서](https://playwright.dev/docs/test-retries)[^9]
- [Playwright annotations 문서](https://playwright.dev/docs/test-annotations)[^10]
- [Playwright TestOptions.channel 문서](https://playwright.dev/docs/api/class-testoptions)[^4]
- [browser-option-channel 파라미터 정의(params.md)](https://github.com/microsoft/playwright/blob/main/docs/src/api/params.md)[^17]
- [Playwright browsers 문서(--only-shell, --with-deps)](https://playwright.dev/docs/browsers)[^18]
- [Playwright Docker 문서](https://playwright.dev/docs/docker)[^12]
- [Microsoft Artifact Registry: Playwright 이미지 태그](https://mcr.microsoft.com/product/playwright)[^13]

[^1]: <https://pypi.org/project/playwright/>
[^2]: <https://pypi.org/project/playwright/1.57.0/>
[^3]: <https://playwright.dev/docs/release-notes>
[^4]: <https://playwright.dev/docs/api/class-testoptions>
[^5]: <https://playwright.dev/docs/test-use-options>
[^6]: <https://playwright.dev/docs/intro>
[^7]: <https://playwright.dev/docs/ci>
[^8]: <https://playwright.dev/docs/test-sharding>
[^9]: <https://playwright.dev/docs/test-retries>
[^10]: <https://playwright.dev/docs/test-annotations?trk=public_post_comment-text>
[^11]: <https://playwright.dev/docs/api/class-testcase>
[^12]: <https://playwright.dev/docs/docker>
[^13]: <https://mcr.microsoft.com/product/playwright>
[^14]: <https://playwright.dev/docs/trace-viewer>
[^15]: <https://github.com/microsoft/playwright/blob/main/docs/src/release-notes-csharp.md>
[^16]: <https://playwright.dev/docs/test-parallel>
[^17]: <https://github.com/microsoft/playwright/blob/main/docs/src/api/params.md>
[^18]: <https://playwright.dev/docs/browsers>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
