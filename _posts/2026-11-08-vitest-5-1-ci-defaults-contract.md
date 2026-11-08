---
title: "Vitest 5.1 업그레이드: 기본값 변화로 CI 계약 고정"
description: "Vitest 5.1의 기본값·리포팅 변화가 CI에 미치는 영향과 이를 팀 규칙으로 고정하는 설정/워크플로를 정리합니다."
date: 2026-11-08 14:05:05 +0900
categories: ["Testing", "Vitest"]
tags: ["vitest", "testing", "ci", "upgrade", "reporting", "nodejs"]
render_with_liquid: false
---

## 테스트 프레임워크 업그레이드를 CI 안정성 계약으로 해석해야 하는 이유

Vitest 업그레이드를 이야기하면 보통 빠른 실행 시간, 더 나은 watch 경험 같은 성능/UX 포인트부터 떠올립니다. 그런데 내가 여러 조직에서 테스트 러너 교체·업그레이드를 겪으면서 더 크게 체감한 리스크는 다른 쪽에 있습니다. **기본값(defaults)의 변화가 CI 안정성의 계약을 바꾼다**는 점입니다.

테스트 러너는 개발자의 로컬에서만 쓰는 도구가 아니라, 다음을 동시에 만족해야 하는 계약 집합입니다.

- CI에서 항상 종료한다(무한 대기/무한 watch 금지)
- 실패를 “같은 방식으로” 보여준다(로그 파서, 리포트 수집, flaky triage가 기대하는 형태)
- 아티팩트 경로가 예측 가능하다(업로드/보관/비교 파이프라인이 깨지지 않는다)
- 병렬성/격리의 기본값이 바뀌어도 의미가 유지된다(순서 의존 테스트가 표면화되는 방식 포함)
- 런타임(Node)·빌드 도구(Vite)·브라우저 모드의 호환성 범위가 맞물린다

Vitest 5.1은 2026-11-02에 공식 블로그로 공개됐고, minor임에도 이런 “계약”의 단서가 되는 변화들이 여럿 들어 있습니다.[^1]

이번 글의 결론은 단순합니다.

- Vitest 5.1을 올릴 때 성능 향상은 부수 효과로 보고,
- **변경된 기본값/리포팅을 팀 규칙으로 명시해 고정**하고,
- 런타임/브라우저 모드/아티팩트 경로를 CI 파이프라인에서 검증 가능한 형태로 잠그는 것이 우선입니다.

## 먼저 잠가야 하는 호환성 범위: Node와 Vite

Vitest 5.x는 “테스트 러너만” 올리는 업그레이드가 아닙니다. Node와 Vite의 하한이 같이 올라갑니다.

- Vitest는 Node >= 22.12.0, Vite >= 6.4.0를 요구합니다.[^2]
- vitest 패키지의 engines.node는 `^22.12.0 || ^24.0.0 || >=26.0.0`로 선언돼 있습니다.[^3]
- peerDependencies에서 vite는 `^6.4.0 || ^7.0.0 || ^8.0.0` 범위를 가집니다.[^3]

여기서 실무적으로 중요한 포인트가 두 가지입니다.

첫째, “로컬은 되고 CI만 깨지는” 케이스가 굉장히 흔해집니다. 개발자 로컬은 이미 최신 Node를 쓰는데 CI runner나 self-hosted runner는 여전히 Node 20/22.11 같은 조합일 수 있습니다. 이 경우 npm/pnpm은 설치 단계에서 엔진 불일치 경고 또는 실패(설정에 따라)를 만들고, 팀은 테스트 실패로 오인하거나 임시 플래그로 우회합니다. 우회는 결국 공급망 리스크로 돌아옵니다. 이 관점은 예전에 정리한 런타임 정책 글들과 연결됩니다.

- [Node 27 연 1회 메이저에 맞춘 사내 런타임 정책 재설계](https://daewooki.github.io/posts/nodejs-annual-major-enterprise-runtime-policy/)
- [GitHub Actions Node 20 제거 전에 런타임 계약 재정리와 마이그레이션 플랜](https://daewooki.github.io/posts/github-actions-node20-removal-runtime-contract-migration/)

둘째, Vite의 패치 레벨이 기능 플래그의 조건이 되기 시작합니다. Vitest 5.1에서 `api.port: 0`로 OS가 빈 포트를 선택하게 하는 기능은 Vite 8.2.1+이 필요하다고 명시돼 있습니다.[^1]

이런 조건은 “Vitest만 올렸는데 왜 브라우저 모드가 안 떠요?” 같은 이슈로 이어집니다. 업그레이드 PR에서 Node/Vite 범위를 함께 올리고, CI에서 `node --version`, `vite --version`을 아예 로그로 남겨두는 쪽이 낫습니다.

## Vitest 5.1에서 기본값 변화로 봐야 하는 지점

Vitest 5.1 릴리스 노트에서 눈에 띄는 변화는 기능 추가(`--since-last-run`, snapshot review 등)지만, CI 관점에서는 “기본값이 달라진 부분”이 더 중요합니다.

### Browser Mode: Trace View가 실패 시 기본 활성화

Vitest 5.0에서 실험적이었던 Trace View가 5.1에서 stable이 되었고, **실패한 테스트에 대해서는 기본으로 trace를 남기는 `failure-only` 모드가 활성화**됩니다.[^1]

이 변화는 단순히 디버깅이 편해지는 수준이 아니라, 다음을 건드립니다.

- 실패 로그의 형식이 변합니다(실패 원인 뒤에 step timeline이 붙음).
- 브라우저 모드에서 실패 시 “어떤 액션/어떤 locator/어느 소스 위치”에서 멈췄는지가 기본 출력에 포함됩니다.
- HTML reporter를 켜면 trace viewer까지 포함한 산출물을 만들 수 있는 흐름이 자연스럽게 됩니다.[^4]

팀에서 로그 파서나 실패 알림(예: Slack으로 에러 일부를 잘라 보내는 봇)을 운영한다면, 이 변화는 “깨진다/안 깨진다”가 아니라 “이제 실패 메시지의 경계가 달라진다”에 가깝습니다. 그래서 난 trace view를 켜고 끄는 것을 개인 취향이 아니라 CI 계약 항목으로 관리하는 편입니다.

참고로 Trace View 문서에서는 `browser.traceView`의 모드로 `'failure-only'`, `'on'`, `'off'`를 설명합니다.[^4]

### Browser Mode: 기본 포트 변경(63315 → 23315)

Browser Mode의 기본 포트가 `63315`에서 `23315`로 바뀌었습니다. Windows에서 Hyper-V/WSL2/Docker Desktop 등이 포트를 예약해 기존 포트에서 Vitest가 시작 실패하는 사례를 줄이기 위한 변경이라고 설명합니다.[^1]

이건 사소해 보이지만, 조직에서는 다음과 같이 터집니다.

- 방화벽/보안 에이전트가 특정 포트를 허용/차단 목록으로 관리
- e2e처럼 보이는 “컴포넌트 테스트”가 실제로는 내부 네트워크에서 접근되는 경우
- self-hosted runner에서 포트 충돌 재현이 어려움

포트는 기본값을 믿지 말고 명시적으로 고정하는 편이 낫습니다(`api.port`). 5.1의 포트 변경은 그걸 강하게 시사합니다.[^1]

### Browser Mode: 연결 실패 시 무한 대기 → 에러로 실패

브라우저 테스트 파일이 서버에 연결하지 못하면, 예전에는 영원히 기다릴 수 있었는데 5.1부터는 에러로 실패하도록 바뀌었다고 합니다.[^1]

이 변화는 CI 관점에서 긍정적인 기본값입니다. 테스트가 “느리다”가 아니라 “멈춘다”가 가장 비싼 실패 형태이기 때문입니다. 다만 타임아웃과 재시도 정책을 팀 규칙으로 정해두지 않으면, 네트워크 일시 장애가 곧바로 실패로 환원됩니다. 실패 자체보다 실패율이 문제가 됩니다.

### Reporter: 환경에 따른 기본 reporter 자동 선택

Vitest는 `reporters`를 설정하지 않으면 환경에 따라 자동 선택합니다.

- 일반 터미널에서는 `default`
- AI coding agent로 감지되면 `minimal`
- `process.env.GITHUB_ACTIONS === 'true'`이면 `github-actions` reporter가 추가

이 기본 동작은 Reporters 가이드에 명시돼 있습니다.[^5]

여기서 내가 보는 리스크는 두 가지입니다.

- 로컬과 CI의 출력이 다르게 보인다. 사람은 “CI에서만 실패가 다르게 보인다”를 flaky로 오인합니다.
- 특정 도구(예: AI agent, 래퍼 스크립트)가 CI와 유사한 환경 변수를 주입하는 순간, 출력이 바뀐다.

이 문제는 해결이 간단합니다. reporter는 auto-detect에 맡기지 않고 팀이 쓰는 조합을 고정합니다. Vitest도 이를 위해 `configDefaults.reporters`로 기본 조합을 확장하는 패턴을 문서에 제공합니다.[^5]

### Reporter 산출물 경로: `.vitest/`가 사실상의 아티팩트 루트

Vitest는 `.vitest/` 디렉터리를 리포트/아티팩트 저장 위치로 사용하고, `.gitignore`에 추가하라고 안내합니다.[^2]

또한 `json`, `junit`, `html` reporter는 터미널 출력이 아니라 `.vitest/` 아래에 파일을 씁니다.

- json: `.vitest/json/output.json`
- junit: `.vitest/junit/output.xml`
- html: `.vitest/index.html`

이 동작과 경로는 Reporters 가이드에 적혀 있습니다.[^5]

즉, CI 아티팩트 수집에서 `.vitest/` 폴더를 업로드 대상으로 잡으면 “리포트 종류가 늘어도” 수집 규칙은 크게 변하지 않습니다. 반대로, 과거처럼 stdout 파이핑(`vitest --reporter=json > out.json`)에 의존하는 파이프라인은 기본값 변화에 취약해집니다.

### 재시도/반복의 결과 노출 방식 변화: attempts 단위로 쪼개기

5.1에서 `retry`/`repeats`가 걸린 테스트의 결과를 attempts 단위로 접근하는 API(`TestCase.attempts()`)를 노출하고, 기본 reporter도 이를 활용해 재시도 실패 출력이 바뀌었다고 설명합니다.[^1]

이건 flaky triage에서 의미가 큽니다. “한 번 실패했다가 재시도에서 통과” 같은 케이스를 팀 규칙으로 어떻게 다룰지(통과로 볼지, unstable로 분류할지)가 결국 CI 계약이 됩니다.

## 업그레이드 절차를 ‘성능 테스트’가 아니라 ‘계약 업데이트’로 설계하기

내가 추천하는 절차는 보수적으로 보이지만, 대규모 레포/다수 팀이 얽혀 있으면 오히려 총 비용이 줄었습니다.

### 1) 업그레이드 PR에서 런타임 범위를 먼저 확정

Vitest 5.x를 올리려면 Node/Vite 하한이 따라 올라갑니다. 이건 기능의 문제가 아니라 설치/실행 가능성의 문제입니다.

- `package.json`의 engines.node를 팀 표준으로 올립니다.
- CI의 setup 단계에서 Node 버전을 고정합니다.
- Vite도 peer 범위를 만족하는 버전으로 올립니다.

Vitest 5.0 마이그레이션 문서에서도 Node/Vite 하한을 분명히 적고 있습니다.[^6]

### 2) defaults를 config로 승격해서 “팀 규칙”으로 박제

Vitest는 환경을 감지해 reporter를 바꾸기도 하고, 브라우저 모드에서는 포트나 trace 동작이 변합니다. 이걸 팀이 의도적으로 선택한 값으로 고정해야 합니다.

- reporters: `reporters`를 명시하고, 필요한 경우 `configDefaults.reporters`를 기반으로 확장
- output artifacts: `.vitest/`를 CI 아티팩트 루트로 지정
- browser mode port: `api.port`를 명시
- trace view: `browser.traceView` 모드 명시
- timeouts/retry: CI에서만 다르게 가져갈지 여부를 결정

### 3) 리포트 소비자(파서/대시보드/품질 게이트)부터 역으로 맞추기

테스트 결과는 어디서 소비되는지부터 확인해야 합니다.

- GitHub Actions의 annotations에 의존하는가?
- JUnit XML을 Test Management로 올리는가?
- HTML 리포트를 아티팩트로 남겨 QA/프론트가 직접 보는가?

이 소비 흐름이 고정되면, 테스트 실행 커맨드와 reporter 조합은 “변경 금지 계약”이 됩니다.

## 실행 가능한 기준 레포: Vitest 5.1에서 계약을 고정하는 설정

아래 예시는 작은 레포지만, 실무에서 자주 등장하는 요구(로컬/CI 출력 일관성, JUnit 수집, 브라우저 모드 trace, fake timers 안정성)를 한 번에 잡는 쪽으로 구성했습니다.

전제:

- Node는 Vitest가 요구하는 범위(예: 26.x)를 사용합니다.[^3]
- Vite는 최소 하한(>=6.4.0)을 만족합니다.[^2]

### 패키지 구성

```text
.
├─ package.json
├─ vitest.config.ts
├─ .gitignore
├─ src/
│  ├─ sleep.ts
│  └─ sleep.test.ts
└─ browser/
   ├─ index.html
   ├─ counter.ts
   └─ counter.browser.test.ts
```

### package.json

```json
{
  "name": "vitest-5-1-ci-contract-example",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest",
    "test:ci": "vitest run",
    "test:browser:ci": "VITEST_BROWSER=1 vitest run --browser.headless --reporter=html"
  },
  "devDependencies": {
    "vite": "^8.2.1",
    "vitest": "^5.1.0",
    "@vitest/browser-playwright": "^5.1.0",
    "playwright": "^1.49.0",
    "typescript": "^6.0.0"
  }
}
```

여기서 중요한 건 버전 숫자가 아니라 방향입니다.

- vitest가 요구하는 Node/Vite 하한을 맞춘다.[^2]
- 브라우저 모드는 provider 패키지가 추가로 필요하다(예시에서는 Playwright).[^7]

### .gitignore

```gitignore
# Vitest reports and artifacts
.vitest/
```

Vitest 자체도 `.vitest/`를 권장합니다.[^2]

### vitest.config.ts: defaults를 팀 규칙으로 고정

```ts
import { defineConfig } from 'vitest/config'
import { playwright } from '@vitest/browser-playwright'

export default defineConfig({
  test: {
    // 1) reporter 자동선택(환경 감지)에서 벗어나 출력 계약을 고정
    // - GitHub Actions에서 env에 따라 reporter가 추가되는 동작을 원치 않으면 명시적으로 지정
    reporters: [
      // 기본 콘솔 출력은 유지하되 summary는 팀 취향에 맞춰 고정
      ['default', { summary: false }],
      // CI에서 수집하는 표준 포맷은 junit으로 고정
      ['junit', { suiteName: 'unit' }],
    ],

    // 2) junit 산출물 경로를 고정
    // 여러 reporter를 쓸 때는 객체 형태로 개별 파일을 지정할 수 있습니다.
    outputFile: {
      junit: '.vitest/junit/unit.xml',
    },

    // 3) fake timers가 node:timers/promises import를 타더라도 실제 시간을 쓰지 않게 고정
    // 5.1.0+ 옵션
    fakeTimers: {
      fakeNodeBuiltins: true,
    },

    // 4) 브라우저 모드: provider와 인스턴스를 명시해 로컬/CI의 실행 모델을 고정
    browser: {
      provider: playwright(),
      enabled: Boolean(process.env.VITEST_BROWSER),
      instances: [{ browser: 'chromium' }],

      // Trace View는 5.1에서 실패 시 기본 활성화(failure-only)로 바뀌었습니다.
      // 팀에서 켜고/끄고의 기준을 명시적으로 관리하는 편이 안전합니다.
      traceView: 'failure-only',
    },

    // 5) 브라우저 모드 포트 기본값이 바뀌었기 때문에, 포트에 의미가 있으면 명시
    api: {
      port: 23315,
      strictPort: true,
    },

    // 6) CI flaky 관리 정책(재시도)을 코드로 고정
    // 실패를 숨기는 목적이 아니라, 일시적 네트워크/브라우저 변동을 triage 가능한 형태로 남기는 목적입니다.
    retry: process.env.CI ? 1 : 0,
  },
})
```

위 설정에서 “계약 고정”과 직접 관련 있는 레퍼런스는 다음입니다.

- reporter 기본 자동 선택 규칙과 `configDefaults.reporters` 확장 패턴[^5]
- `json/junit/html` reporter의 기본 산출물 경로가 `.vitest/` 아래라는 점, 그리고 `outputFile`로 경로를 고정할 수 있다는 점[^5]
- `fakeTimers.fakeNodeBuiltins`는 5.1.0+이며 기본값은 false라는 점[^8]
- 브라우저 모드 포트가 5.1에서 23315로 바뀌었다는 점[^1]

### Node 환경 테스트: node:timers/promises까지 포함한 fake timers 안정화

`src/sleep.ts`

```ts
import { setTimeout as sleep } from 'node:timers/promises'

export async function sleepThen(value: string, ms: number) {
  await sleep(ms)
  return value
}
```

`src/sleep.test.ts`

```ts
import { expect, test, vi } from 'vitest'
import { sleepThen } from './sleep.js'

test('sleepThen returns value after delay (fake timers)', async () => {
  vi.useFakeTimers()

  const p = sleepThen('ok', 1000)

  await vi.advanceTimersByTimeAsync(1000)
  await expect(p).resolves.toBe('ok')
})
```

Vitest 5.1에서는 `node:timers` / `node:timers/promises`에서 import한 타이머도 fake로 바꾸는 옵션이 추가됐고, 이를 config로 고정해두면 “이 테스트는 원래 1초 걸려야 한다” 같은 해석의 여지를 없앨 수 있습니다.[^1]

실행:

```bash
npm install
npm run test:ci
```

예상 결과(요지):

- 테스트는 거의 즉시 끝납니다(실시간 1초 대기하지 않음).
- `.vitest/junit/unit.xml`이 생성됩니다.

### Browser Mode 테스트: Trace View/포트/리포트 아티팩트를 함께 다루기

`browser/index.html`

```html
<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <title>counter</title>
  </head>
  <body>
    <button id="inc">inc</button>
    <div id="value">0</div>
    <script type="module" src="/browser/counter.ts"></script>
  </body>
</html>
```

`browser/counter.ts`

```ts
let value = 0

const valueEl = document.querySelector<HTMLDivElement>('#value')!
const incBtn = document.querySelector<HTMLButtonElement>('#inc')!

function render() {
  valueEl.textContent = String(value)
}

incBtn.addEventListener('click', () => {
  // 일부러 비동기 DOM 업데이트를 넣어 locator 기반의 waiting/타임아웃이 어떻게 보이는지 확인
  setTimeout(() => {
    value += 1
    render()
  }, 10)
})

render()
```

`browser/counter.browser.test.ts`

```ts
import { expect, test, vi } from 'vitest'
import { page, userEvent } from 'vitest/browser'

test('counter increments', async () => {
  vi.useFakeTimers()

  await page.goto('/browser/index.html')

  await userEvent.click(page.getByRole('button', { name: 'inc' }))

  // 5.1에서 브라우저 locator 액션/expect.element가 fake timers를 진행시키는 동작이 개선됐다고 설명합니다.
  // 여기서는 기다림이 필요한 지점을 의도적으로 만들었습니다.
  await expect.element(page.getByText('1')).toBeVisible()
})
```

5.1 블로그에는 브라우저 모드에서 locator 액션(`click`, `fill`)과 `expect.element`가 대기하는 동안 fake timers를 advance해서, fake `setTimeout` 이후에 등장하는 요소를 제대로 기다릴 수 있게 됐다고 적혀 있습니다.[^1]

실행:

```bash
npm run test:browser:ci
```

예상 결과(요지):

- 실패하면(의도적으로 깨뜨리면) step timeline이 에러 로그 끝에 붙습니다(Trace View failure output).[^1]
- `.vitest/index.html`이 생성됩니다(HTML reporter).[^5]
- Browser Mode 서버 포트는 23315로 바인딩됩니다.[^1]

## `--since-last-run`을 CI가 아니라 개발 워크플로 계약으로 쓰는 법

Vitest 5.1의 눈에 띄는 기능 중 하나는 `--since-last-run`입니다.[^1]

- `--changed`가 Git ref 비교 기반이라면,
- `--since-last-run`은 “지난번 실행 이후 이 테스트가 읽은 파일들의 mtime이 변했는지”로 영향을 판정합니다.

블로그에서는 이 기능이 `experimental.recordDependencies`와 새로운 `mtime` VCS provider에 기반한다고 밝힙니다.[^1]

이걸 CI에서 바로 쓰려 들면, 기대 대비 실망할 가능성이 큽니다. 컨테이너 기반 CI는 보통 매번 깨끗한 작업 디렉터리에서 시작하고, 이전 실행 기록이 남지 않기 때문입니다.

반대로 다음에 잘 맞습니다.

- 로컬 개발에서 빠른 피드백 루프
- AI coding agent가 “수정 → 관련 테스트만 실행”을 반복하는 워크플로

Vitest는 이런 상황을 염두에 두고, Git이 없어도 fresh container/temporary worktree에서도 동일하게 동작한다고 강조합니다.[^1]

다만 이 기능은 계약 관점에서 또 다른 주의점이 있습니다.

- `mtime`은 “테스트를 실행한 머신의 시계”를 전제로 합니다. 문서에서도 경고합니다.[^9]
- clock skew가 있는 CI runner나, 파일이 다른 방식으로 체크아웃/동기화되는 환경에서는 판정이 흔들릴 수 있습니다.

그래서 내 결론은 이렇습니다.

- CI의 gate는 여전히 `vitest run` 전체 실행을 기준으로 두고,
- `--since-last-run`은 개발 생산성 도구로 분리해 문서화하는 편이 안전합니다.

설정 예시(개발 전용):

```ts
// vitest.config.ts 일부
export default defineConfig({
  test: {
    experimental: {
      recordDependencies: true,
      vcsProvider: 'mtime',
    },
  },
})
```

`experimental.vcsProvider`와 `experimental.recordDependencies`의 관계는 config 문서에 정리돼 있습니다.[^10]

## 리포팅을 팀 규칙으로 고정하는 체크리스트

여기부터는 Vitest 5.1에서 특히 “깨지기 쉬운” 지점들을 계약 항목으로 바꾸는 체크리스트입니다.

### 1) reporters는 반드시 명시한다

자동 감지 규칙이 존재한다는 것 자체가 리스크입니다. 특히 `GITHUB_ACTIONS` 같은 환경 변수는 생각보다 쉽게 오염됩니다.

- 로컬과 CI의 출력이 같아야 flaky triage 비용이 줄어듭니다.
- 누군가 개인적으로 `minimal`을 선호해도, 팀은 팀의 기본 조합을 유지해야 합니다.

Vitest 문서가 말하듯, `reporters`를 설정하면 기본 목록을 “대체”합니다.[^5]

### 2) `.vitest/`를 CI 아티팩트 루트로 취급한다

`.vitest/` 아래에 리포트가 모이기 시작하면, 아티팩트 수집 규칙이 단순해집니다.

- junit: `.vitest/junit/`
- json: `.vitest/json/`
- html: `.vitest/index.html`

경로는 Reporters 가이드에 있습니다.[^5]

### 3) stdout 기반 파이프라인은 버린다(특히 json/junit)

Vitest 문서도 `stdout` 옵션이 로그와 섞여 파싱 불가능해질 수 있다고 경고합니다.[^5]

표준 출력으로 XML/JSON을 밀어 넣는 방식은, 테스트 러너가 출력 형식을 조금만 바꿔도 무너집니다. 파일 아티팩트로 남기고 업로드하는 흐름이 장기적으로 훨씬 안정적입니다.

### 4) outputFile은 “유지되지만 영원하진 않다”로 가정한다

지금은 `outputFile`이 config 옵션으로 존재하고 문서에도 있습니다.[^11]

하지만 Vitest 이슈 트래킹에는 `outputFile` 옵션을 다음 major에서 제거하자는 논의가 올라와 있습니다.[^12]

이건 확정 사실이 아니라 제안이지만, CI 계약 측면에서는 다음처럼 준비하는 편이 낫습니다.

- top-level `outputFile`에 과도하게 의존하지 않는다.
- 가능하면 reporter 자체 옵션(`['junit', { outputFile: '...' }]`)도 함께 고려한다(우선순위가 더 높다고 문서에 명시).[^5]

### 5) retry/repeats는 “통과 처리”가 아니라 “신호 수집”으로 사용

5.1에서 attempts 단위 결과 접근과 기본 reporter 출력 변화가 들어온 것은, flaky를 더 잘 보이게 하려는 방향으로 해석할 수 있습니다.[^1]

여기서 팀 규칙이 없으면 결과가 극단으로 갑니다.

- retry=0: 일시 장애가 그대로 red CI를 만들고 개발 속도가 떨어짐
- retry>0: 재시도로 통과하면 문제를 묻어버리고, 진짜 flaky가 누적됨

내 경우는 보통 다음 중 하나로 정했습니다.

- retry는 1회까지만(통신/브라우저/파일시스템 변동에 대한 완충)
- retry로 통과한 테스트는 별도의 리포트(커스텀 reporter)로 수집해 매주 정리

Vitest 5.1 블로그에서 `TestCase.attempts()` 예시까지 제공하는 건, 이런 운영을 염두에 둔 것에 가깝습니다.[^1]

## GitHub Actions에서 계약을 코드로 고정하는 예시

Vitest 자체가 GitHub Actions 환경을 감지해 reporter를 추가할 수 있으니, 난 Actions에서도 “명시”를 원칙으로 둡니다.

```yaml
name: test

on:
  pull_request:
  push:

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '26'

      - name: Install
        run: npm ci

      - name: Unit tests
        run: npm run test:ci

      - name: Upload vitest artifacts
        uses: actions/upload-artifact@v4
        with:
          name: vitest-artifacts
          path: .vitest/

  browser:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '26'

      - name: Install
        run: npm ci

      - name: Browser tests
        run: npm run test:browser:ci

      - name: Upload vitest artifacts
        uses: actions/upload-artifact@v4
        with:
          name: vitest-browser-artifacts
          path: .vitest/
```

이 예시는 단순하지만 효과가 큽니다.

- 브라우저 모드 trace view/HTML 리포트/junit이 모두 `.vitest/`로 모입니다.[^5]
- 포트/trace/reporter가 config로 잠겨 있어 실행 환경에 덜 흔들립니다.[^1]

## 5.1에서 특히 자주 밟는 함정과 트레이드오프

### Browser Mode 포트 변경은 “문제 해결”이면서 “규칙 붕괴”다

63315 → 23315 변경은 Windows에서 흔한 포트 예약 문제를 피하려는 개선입니다.[^1]

하지만 팀이 이미 특정 포트를 기준으로 문서/방화벽/모니터링을 세팅했다면, 개선이 곧 규칙 붕괴가 됩니다. 그래서 포트는 기본값을 신뢰하지 않고 `api.port`를 명시하는 편이 안전합니다.

### Trace View 기본 활성화는 로그/아티팩트 비용을 동반한다

failure-only가 “passing test에는 측정 가능한 비용이 없다”고 설명하더라도, 실패했을 때 출력이 늘고 아티팩트가 늘어납니다.[^1]

- 로그 기반 알림/파서가 있다면, 파서가 “에러 메시지의 끝”을 어떻게 찾는지부터 다시 봐야 합니다.
- HTML 리포트까지 켜면 디버깅은 편해지지만, 아티팩트 보관 비용이 늘어납니다.

### `api.port: 0`는 편하지만 Vite 버전 조건이 추가된다

OS가 free port를 선택하면 충돌은 줄지만, 5.1 기준으로 Vite 8.2.1+이 필요합니다.[^1]

팀 표준 Vite 버전이 아직 7.x라면, 여기서 다시 갈립니다.

- 충돌을 줄이기 위해 `api.port: 0`로 가고 싶다
- 하지만 Vite를 올리면 빌드 파이프라인까지 검증 범위가 커진다

이럴 때는 오히려 포트를 고정하고 충돌을 해결하는 편이 총 비용이 낮을 때가 많았습니다.

### `mtime` 기반 영향 테스트는 “정확성”보다 “재현성”을 먼저 봐야 한다

`--since-last-run`은 생산성 도구로 매우 매력적입니다. 하지만 `mtime`은 머신 시계를 믿는다는 경고가 있습니다.[^9]

그래서 CI gate를 대체하는 용도로 쓰기 시작하면, “왜 어떤 날은 관련 테스트가 안 돌았지?” 같은 신뢰도 문제로 이어질 수 있습니다.

## 업그레이드 도입 판단 기준

내 기준에서 Vitest 5.1 업그레이드는 다음 조건이 갖춰져야 합니다.

- Node/Vite 하한을 올리는 것이 조직 정책과 충돌하지 않는다.[^2]
- `.vitest/`를 아티팩트 루트로 삼고, 리포트 수집이 파일 기반으로 설계돼 있다.[^5]
- Browser Mode를 쓰는 팀은 포트/trace view/연결 실패 처리 방식을 문서와 config로 고정한다.[^1]
- retry 정책은 “통과로 덮기”가 아니라 attempts 단위 관찰/추적이 가능한 형태로 운용한다.[^1]

이 조건을 만족하면, 5.1의 기능 추가는 보너스가 됩니다. 반대로 조건이 없으면, minor 업그레이드가 CI 계약의 미묘한 붕괴로 이어지고 그 비용은 길게 남습니다.

## 참고 자료

- [Vitest 5.1 발표(2026-11-02)](https://vitest.dev/blog/vitest-5-1)
- [Vitest v5.1.0 GitHub Release](https://github.com/vitest-dev/vitest/releases/tag/v5.1.0)
- [Vitest Getting Started: Node/Vite 요구사항과 .vitest 안내](https://main.vitest.dev/guide/)
- [Vitest Migration Guide: 5.0의 Node/Vite 하한](https://main.vitest.dev/guide/migration/)
- [Vitest Reporters Guide: 기본 reporter 선택 규칙과 산출물 경로](https://main.vitest.dev/guide/reporters.html)
- [Vitest outputFile 설정](https://main.vitest.dev/config/outputfile)
- [Vitest fakeTimers.fakeNodeBuiltins (5.1.0+)](https://main.vitest.dev/config/faketimers)
- [Vitest experimental.recordDependencies / vcsProvider(mtime)](https://main.vitest.dev/config/experimental)
- [Vitest Trace View 문서: failure-only 기본 모드](https://vitest.dev/guide/browser/trace-view)
- [Vitest Browser Mode 가이드: 포트 23315 설명](https://main.vitest.dev/guide/browser/)

[^1]: <https://main.vitest.dev/blog/vitest-5-1>
[^2]: <https://main.vitest.dev/guide/>
[^3]: <https://github.com/vitest-dev/vitest/blob/main/packages/vitest/package.json>
[^4]: <https://vitest.dev/guide/browser/trace-view>
[^5]: <https://main.vitest.dev/guide/reporters.html>
[^6]: <https://main.vitest.dev/guide/migration/>
[^7]: <https://main.vitest.dev/guide/browser/>
[^8]: <https://main.vitest.dev/config/faketimers>
[^9]: <https://main.vitest.dev/config/experimental>
[^10]: <https://main.vitest.dev/guide/cli>
[^11]: <https://main.vitest.dev/config/outputfile>
[^12]: <https://github.com/vitest-dev/vitest/issues/11355>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
