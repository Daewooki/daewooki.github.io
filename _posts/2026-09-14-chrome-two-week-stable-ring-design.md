---
title: "Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영"
description: "Chrome 153부터 Stable이 2주마다 나온다. E2E·호환성 검증·엔터프라이즈 정책 링을 4주 전제에서 다시 짠다."
date: 2026-09-14 13:31:12 +0900
categories: ["News", "Web"]
tags: ["chrome", "enterprise", "release-management", "e2e-testing", "qa", "security-patching"]
render_with_liquid: false
---

## 2026-09-08: Chrome 153 롤아웃과 함께 Stable 주기가 2주로 바뀌었다

2026년 9월 8일(공식 게시일 기준) Chrome 153 Stable이 데스크톱(Windows/Mac/Linux) Stable 채널로 승격되면서, Stable “major milestone” 릴리스 주기가 기존 4주에서 2주로 전환됐습니다. Google은 이 변화를 Chrome 153부터 적용한다고 명시했습니다.[^1]

이 전환이 실무에 주는 신호는 단순합니다.

- Stable = 매달 1번 “큰 업데이트”가 아니라, **2주마다 정기적으로 기능/변경이 들어오는 업데이트 스트림**이 됐습니다.[^1]
- 발표문 자체도 “scope per release가 더 작아져서 regression isolation이 쉬워진다”는 식으로, 업데이트를 더 잘게 쪼개 빈도를 높이는 방향을 강조합니다.[^1]

이번 전환을 “보안 패치가 2배 빨라진다(4주→2주)”로만 보면 반쪽입니다. 운영 관점에서는 ‘패치=곧 배포’로 밀어붙이기 위해 QA/릴리즈 캘린더, 링(ring), 테스트 인프라가 구조적으로 바뀌는 쪽이 더 큽니다.

추가로 Chrome 153 자체도 변경 폭이 작지 않습니다. 예를 들어:

- `<camera>`, `<microphone>` capability elements가 추가됐고[^2]
- XSLT가 아닌 시나리오에서 XML parsing 엔진을 Rust 구현으로 교체했습니다.[^2]

이런 종류의 변경은 “우리 서비스가 새 API를 쓰지 않으면 상관없다”로 끝나지 않을 때가 있습니다. DOMParser/responseXML을 쓰는 레거시 코드, SVG 파이프라인, 혹은 특정 브라우저 엔진 버그를 우회해 온 코드가 있으면 실제 호환성 이슈로 돌아옵니다.

## 패치가 ‘릴리스’가 되는 순간: QA 캘린더가 무너지는 지점

4주 cadence에서 많은 조직이 암묵적으로 운영하던 건 다음의 3단계였습니다.

1) Stable 나오는 주에 보안/취약점 공지 확인
2) 다음 주에 E2E 전체 회귀 + 핵심 플로우 수동 점검
3) 그 다음 주에 파일럿 배포 → 전체 배포

이게 2주 cadence로 바뀌면, 2)와 3)이 끝나기도 전에 다음 Stable이 나옵니다. 즉 “릴리스마다 풀 리그레션”이라는 프레임을 유지하면, 조직은 필연적으로 **항상 1개(혹은 2개) 버전 뒤처진 상태**가 됩니다.

문제는 뒤처짐 자체가 아니라, 뒤처짐이 ‘의도한 정책’이 아니라 ‘운영 부채’로 발생한다는 점입니다.

- 뒤처짐이 정책이면: 테스트 범위/배포 기준/예외 처리가 문서화되고, 영향도(보안, 기능, 표준 지원)도 계산됩니다.
- 뒤처짐이 운영 부채면: “일정이 밀려서 아직 못 올림”이 표준이 되고, 그 순간부터 브라우저 업데이트는 항상 긴급 작업으로만 들어옵니다.

Google은 “Chrome 154 Beta는 이미 테스트 가능하고, 154 Stable은 9월 22일 예정”이라고 같이 박았습니다.[^1] 이 말은 2주 cadence가 달력에 박히는 순간부터, 조직의 QA 달력이 브라우저 달력에 종속된다는 뜻입니다.

## 보안팀이 원하는 그림: patch gap이 줄어드는 대신 운영비가 오른다

Google이 2주 cadence를 밀어붙이는 이유 중 하나는 보안입니다. “automated AI discovery tools와 커뮤니티 리포트로 patch volume이 늘었고, 짧은 release cycle이 security fixes를 관리하기 쉽다”, “N-day patch gap을 줄인다”는 논리를 공개적으로 씁니다.[^1]

Chrome 153 Stable 데스크톱 업데이트 공지에서 눈에 띄는 건 두 가지입니다.

- 이번 업데이트에 “230 security fixes”가 포함됐다고 적습니다.[^3]
- “CVE-2026-87491 exploit이 wild에 존재한다”는 문장이 들어가 있습니다.[^3]

실무에서 이 조합이 의미하는 건, 브라우저 업데이트를 ‘정기 업데이트’로 취급할수록 보안 리스크가 커진다는 점입니다. 패치량이 많고, in-the-wild가 섞일 수 있으며, Stable cadence가 2주면 “다음 정기 배포 때 반영” 같은 접근이 점점 설 자리를 잃습니다.

내 블로그에서 예전에 썼던 [Chrome 제로데이 주간에 브라우저 업데이트를 배포 파이프라인으로 굴리는 방법](https://daewooki.github.io/posts/chrome-zero-day-rollout-pipeline/)과 [Chrome 152 제로데이 공지가 패치 프로세스를 강제하는 방식](https://daewooki.github.io/posts/chrome-152-zero-day-forces-patching-process/)에서 얘기했던 것도 결국 같은 결론이었습니다. 브라우저는 애플리케이션이라기보다 “사용자 단말의 핵심 런타임”이어서, 패치 속도 자체가 정책/운영 구조를 강제합니다.

2주 cadence는 그 강제가 평시에도 적용되는 상태에 가깝습니다.

## Extended Stable이 생존선인가: 8주 milestone + 주간 보안 refresh

Google은 2주 Stable을 “most secure choice”로 두면서도, 엔터프라이즈가 따라오기 어렵다는 걸 인정합니다. 그래서 Extended Stable 채널을 공식적으로 대안으로 제시합니다.[^1]

Extended Stable의 핵심은 “feature는 8주마다”인데 “보안 수정은 가능한 한 backport해서 주 단위로 refresh한다”는 점입니다.

- Stable은 2-week release cycle
- Extended Stable은 8-week release cycle
- milestone의 첫 2주 동안은 Stable과 Extended Stable이 동일
- 이후 6주 동안 Extended Stable은 weekly refresh로 security fixes를 받음(단, 복잡한 변경이나 큰 보안 개선 기능은 Stable에만 있을 수 있음)[^4]

이 모델은 “우린 8주마다만 브라우저를 바꾼다”가 아니라, “feature milestone은 8주마다지만 weekly security refresh는 계속 받는다”로 이해해야 합니다. 특히, backport가 기술적으로 불가능한 케이스가 생길 수 있다는 단서가 중요합니다.[^4]

또 하나 현실적인 제약이 있습니다.

- Extended Stable은 (문서 기준) managed Chrome browser의 Windows/Mac에서 강조됩니다.[^4]
- Chrome 153 2주 전환은 Desktop/Android/iOS에 적용된다고 Google이 명시합니다.[^1]

즉 모바일까지 포함해 “조직 전체를 Extended Stable로 통일”은 구조적으로 어렵고(혹은 불가능하고), 대개는 데스크톱에만 선택적으로 적용하는 형태가 됩니다. 이때부터 링 설계가 필요해집니다.

## E2E 테스트를 다시 정의해야 한다: ‘릴리스-기반’에서 ‘채널-기반’으로

2주 cadence에서 E2E의 목표를 “새 버전이 나왔으니 검증한다”로 잡으면 항상 늦습니다. 목표를 다음으로 바꿔야 합니다.

- Stable이 바뀌는 속도에 맞춰 **호환성 신호를 지속적으로 수집**한다.
- 그 신호를 기반으로 “누구에게, 어떤 속도로, 어떤 예외로” 배포할지 결정한다.

여기서 핵심은 Beta 채널입니다. Google은 2주 cadence에서 “Chrome 154 Beta는 이미 available, Stable은 9/22 예정” 같은 식으로 Beta를 명시적으로 테스트 선행 채널로 둡니다.[^1]

운영적으로는 이렇게 재구성하는 편이 맞습니다.

- PR/커밋 단위: 빠른 E2E(수 분~수십 분)를 Stable 기준으로 돌려 “우리 변경이 현재 Stable에서 깨지지 않음”을 보장
- Nightly(또는 하루 2~4회): 같은 E2E를 Beta 기준으로 돌려 “2주 뒤 Stable에서 깨질 가능성”을 조기에 탐지
- Stable release day(2주마다): 전체 회귀를 다시 돌리는 게 아니라, **Beta에서 이미 확인한 결과를 근거로** ‘배포 링을 당길지/늦출지’만 결정

이 구조는 테스트 총량을 무조건 늘리기보다는, “테스트를 일정 이벤트(Stable 릴리스)에 묶어두는 비용”을 줄여줍니다. 릴리스 당일에 갑자기 바빠지는 게 아니라, 평소에 Beta로 물을 대고 있어야 합니다.

## 링(ring) 설계: 시간 기반 링에서 리스크 기반 링으로

4주 cadence에서 흔히 하던 “1주 파일럿 + 1주 확대”는 2주 cadence에 그대로 이식이 안 됩니다. 2주짜리 주기 안에 2주짜리 링을 넣을 수 없기 때문입니다.

2주 cadence에서 링은 ‘시간’을 쪼개는 장치가 아니라, ‘리스크’를 분산하는 장치가 됩니다. 내가 권하는 형태는 다음처럼 역할 중심으로 나누는 것입니다.

### Ring 0: Preview 링 (Beta 중심)

- 대상: Web platform 담당(프론트 플랫폼/공통 컴포넌트), QA의 소수, “브라우저 호환성이 곧 제품 품질”인 팀
- 목적: 2주 뒤 Stable 영향 탐지
- 도구: Beta 자동 업데이트 또는 CI에서 Beta로 주기 테스트

이 링의 KPI는 “배포율”이 아니라 “탐지 리드타임”입니다. Stable 출시 전에 깨짐을 발견해, 내부 Web app 또는 polyfill/feature flag로 대응 시간을 벌어야 합니다.

### Ring 1: Fast Stable 링 (최신 Stable 빠른 적용)

- 대상: IT/보안/개발 조직, 그리고 장애 시 복구가 쉬운 사용자군
- 목적: 보안 patch gap 최소화
- 정책: Stable 출시 후 0~3일 내 적용

2주 cadence로 오면 이 링은 사실상 “보안 기준선”이 됩니다. Ring 1이 잘 굴러가면, Ring 2/3이 뒤처지더라도 조직 전체 위험도를 계산 가능한 형태로 만들 수 있습니다.

### Ring 2: Broad Stable 링 (대다수 사용자)

- 대상: 대부분의 일반 사용자
- 목적: 안정성과 운영비 균형
- 정책: Stable 출시 후 4~10일 내 확대 적용

여기서 중요한 건 “다음 Stable이 나오기 전에 끝낸다”가 아닙니다. 다음 Stable이 나오기 전에 100%가 다 따라오지 못해도 괜찮습니다. 대신 Ring 2는 **한 번에 하나의 버전만** 따라가도록 만들면 됩니다.

- 오늘 기준 최신 Stable이 153이면
- Ring 2는 153을 따라가고
- 다음 Stable 154가 나오면, Ring 2는 154로 넘어갈지/보류할지 결정

즉, Ring 2는 ‘릴리스마다 즉시 반영’이 아니라 ‘릴리스마다 의사결정’입니다.

### Ring 3: Hold 링 (Extended Stable 또는 버전 핀)

- 대상: 레거시/벤더 종속(VDI, ERP 플러그인, 사내 SSO 에이전트 등)으로 브라우저 버전 민감도가 높은 사용자군
- 목적: “기능 업데이트”의 빈도를 낮추고, 대신 보안은 가능한 한 따라감

여기서 선택지는 두 갈래입니다.

1) Extended Stable 채널로 이동
- feature milestone 8주, weekly security refresh는 계속[^4]
- TargetChannel policy로 관리 가능[^4]

2) Stable에 남되 TargetVersionPrefix 등으로 핀/롤백 운영
- 특정 major에 고정하거나(짧은 기간)
- 문제 생기면 롤백

내 경험상, Hold 링을 “아예 업데이트 안 함”으로 두면 결국 더 큰 사고로 돌아옵니다. Hold 링은 ‘업데이트 속도’가 아니라 ‘업데이트 방식’을 바꾸는 게 맞습니다.

## 엔터프라이즈 정책: “버전”과 “속도”를 분리해서 설계한다

링 설계가 잘 안 되는 조직의 공통점은, “몇 %에게 배포할지”와 “무슨 버전을 깔지”를 한 덩어리로 운영하는 경우가 많습니다. 2주 cadence에서는 이걸 분리해야 합니다.

- 버전: TargetChannel, TargetVersionPrefix, RollbackToTargetVersion 같은 정책으로 통제
- 속도(rollout): 조직 단위/OU 단위/fast/slow rollout 같은 배포 레버로 통제

Google의 관리 문서에서도 “Major/Minor version rollout을 general/fast/slow로 조정”하는 식의 rollout 제어를 안내합니다.[^5]

### TargetChannel로 Stable vs Extended Stable을 링에 매핑

Extended Stable은 TargetChannel policy로 관리할 수 있다고 문서에 적혀 있습니다.[^4]

이걸 ‘전사 채널 전환’으로 쓰기보다는, Hold 링 사용자군에만 TargetChannel=EXTENDED_STABLE을 적용하는 패턴이 현실적입니다.

- Ring 1/2: Stable 유지
- Ring 3: Extended Stable

이렇게 하면 모바일(Extended Stable 비지원)과 데스크톱의 정책 모델도 자연스럽게 분리됩니다.

### TargetVersionPrefix + RollbackToTargetVersion: “문제 났을 때의 시간”을 버는 장치

Windows/Mac 업데이트 관리 문서에서 TargetVersionPrefix와 RollbackToTargetVersion을 조합해 롤백/버전 고정을 안내합니다.[^6]

2주 cadence에서 이 조합이 특히 중요한 이유는, “장애 발생”과 “다음 Stable 출시” 사이의 간격이 짧기 때문입니다.

- 장애가 나면 예전에는 ‘다음 달에 고치자’가 통했는데
- 이제는 2주마다 환경이 바뀌어서 ‘고치기 전까지 고정’이 곧 운영 전략이 됩니다.

다만 여기서 자주 나오는 착각이 있습니다.

- TargetVersionPrefix로 특정 major에 고정하면, “그 major에서 나오는 보안 패치까지 다 놓친다”고 오해하는 경우

실제로는 minor/patch 레벨 업데이트는 별개로 굴 수 있고(정책 조합에 따라), 무엇보다 Extended Stable은 weekly refresh로 보안 패치를 backport하려고 합니다.[^4] 다만 backport가 100% 보장되는 게 아니라는 문구가 있기 때문에, Hold 링의 보안 위험도를 별도로 평가해야 합니다.[^4]

### chrome://policy를 ‘운영 대시보드’로 취급

정책 기반 운영에서 가장 중요한 건 “내가 의도한 정책이 실제 단말에 먹혔는가”입니다. Google도 크롬에서 chrome://policy로 최종 정책 값을 확인하라고 안내합니다.[^5]

링 재구성 이후에는, 최소한 다음을 상시 점검하는 편이 낫습니다.

- Ring별 TargetChannel/TargetVersionPrefix 적용률
- 업데이트가 실제로 일어나고 있는지(특히 크롬은 실행/재시작 조건, 사용자 행동에 영향 받는 구간이 있어서 ‘배포했다’와 ‘적용됐다’가 다를 때가 많습니다)

## 실전 예시: Chrome for Testing으로 Stable/Beta를 CI에서 동시에 돌린다

2주 cadence에서 “E2E를 더 자주 돌리자”는 말은 쉬운데, 브라우저 버전을 CI에 안정적으로 가져오는 게 먼저 막힙니다. 여기서 Chrome for Testing(CfT)이 꽤 쓸모가 있습니다.

CfT는 Stable/Beta/Dev/Canary별로 “last-known-good-versions(-with-downloads).json” 같은 엔드포인트를 제공하고, 다운로드 URL까지 내려줍니다.[^7]

아래는 Ubuntu 러너에서 다음을 자동화하는 예시입니다.

- CfT에서 Stable/Beta의 linux64 Chrome을 다운로드
- 같은 Playwright E2E를 Stable/Beta 두 번 실행
- Beta에서만 깨지면 2주 뒤 이슈로 분류(사전 대응), Stable에서 깨지면 즉시 핫픽스/롤백 판단

테스트 대상은 OWASP Juice Shop을 로컬 Docker로 띄워서 씁니다. Juice Shop은 “UI+API+auth+DB” 구조를 갖고 있고, 프로젝트 자체도 E2E 테스트(Cypress)를 공식적으로 포함하고 있다고 문서화돼 있습니다.[^8]

### 1) 준비물

- Docker
- Node.js 20+ (Playwright 최신 계열이 Node LTS를 요구하는 편이라, CI에서는 Node LTS를 전제로 둡니다)
- `unzip`, `jq`(선택)

Playwright는 예시 작성 시점 기준 npm에 `@playwright/test` 최신 버전이 1.63.0으로 표기돼 있습니다. 이 글의 예시도 1.63.0을 고정합니다.[^9]

### 2) Juice Shop 실행

Docker Hub 태그 기준으로 `v20.2.0`이 제공됩니다.[^10]

```bash
docker run -d --name juice-shop -p 3000:3000 bkimminich/juice-shop:v20.2.0

# 기동 확인
curl -I http://localhost:3000/ | head
```

예상 출력(환경에 따라 다르지만 핵심은 200/301 같은 정상 응답입니다).

```text
HTTP/1.1 200 OK
```

### 3) 프로젝트 생성 및 Playwright 설치

```bash
mkdir chrome-cadence-e2e
cd chrome-cadence-e2e

npm init -y
npm i -D @playwright/test@1.63.0

# Playwright가 OS 의존 라이브러리를 설치하도록(ubuntu 러너에서 특히 유용)
npx playwright install-deps chromium
```

### 4) CfT에서 브라우저 다운로드하는 스크립트

`tools/fetch-cft.mjs`

```js
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createWriteStream } from 'node:fs';
import { pipeline } from 'node:stream/promises';
import unzipper from 'unzipper';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const channel = process.argv[2]; // Stable | Beta
const platform = process.argv[3] ?? 'linux64';

if (!channel || !['Stable', 'Beta'].includes(channel)) {
  console.error('Usage: node tools/fetch-cft.mjs <Stable|Beta> [linux64]');
  process.exit(1);
}

// CfT JSON API는 공식 repo README에 문서화돼 있습니다.
// last-known-good-versions-with-downloads.json 에서 채널별 버전과 다운로드 URL을 가져옵니다.
const cftUrl = 'https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json';

const res = await fetch(cftUrl);
if (!res.ok) throw new Error(`Failed to fetch CfT JSON: ${res.status}`);

const json = await res.json();
const info = json.channels[channel];
const version = info.version;

const chromeDownloads = info.downloads.chrome;
const asset = chromeDownloads.find(x => x.platform === platform);
if (!asset) throw new Error(`No chrome download for platform=${platform}`);

const downloadUrl = asset.url;

const cacheDir = path.resolve(__dirname, '..', '.cache', 'cft', channel, version);
await fs.mkdir(cacheDir, { recursive: true });

const zipPath = path.join(cacheDir, `chrome-${platform}.zip`);
const markerPath = path.join(cacheDir, '.unzipped');

try {
  await fs.access(markerPath);
  console.log(JSON.stringify({ channel, version, cacheDir, reused: true }));
  process.exit(0);
} catch {}

console.log(`Downloading ${channel} ${version} from ${downloadUrl}`);

const dl = await fetch(downloadUrl);
if (!dl.ok) throw new Error(`Download failed: ${dl.status}`);

await pipeline(dl.body, createWriteStream(zipPath));

await fs.createReadStream(zipPath)
  .pipe(unzipper.Extract({ path: cacheDir }))
  .promise();

await fs.writeFile(markerPath, 'ok');

console.log(JSON.stringify({ channel, version, cacheDir, reused: false }));
```

이 스크립트는 `unzipper` 패키지를 쓰므로 추가 설치가 필요합니다.

```bash
npm i -D unzipper
```

### 5) Playwright 설정: 실행 파일 경로를 주입받아 실행

`playwright.config.ts`

```ts
import { defineConfig } from '@playwright/test';

type Channel = 'Stable' | 'Beta';

const channel = (process.env.CHROME_CHANNEL as Channel) ?? 'Stable';
const cacheDir = process.env.CHROME_CACHE_DIR;

if (!cacheDir) {
  throw new Error('CHROME_CACHE_DIR is required. Run fetch-cft first.');
}

// CfT zip을 풀면 linux64 기준으로 chrome-linux64/chrome 실행 파일이 생깁니다.
const executablePath = `${cacheDir}/chrome-linux64/chrome`;

export default defineConfig({
  timeout: 60_000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:3000',
    browserName: 'chromium',
    launchOptions: {
      executablePath,
      args: [
        '--no-first-run',
        '--no-default-browser-check'
      ]
    }
  },
  reporter: [['list'], ['html', { open: 'never' }]],
  metadata: { channel }
});
```

### 6) E2E 테스트(회원가입 → 로그인 → 상품 검색)

Juice Shop은 신규 고객이 `#/register`로 이동해 등록할 수 있다고 문서에 명시돼 있습니다.[^11]

`tests/juice-shop-happy-path.spec.ts`

```ts
import { test, expect } from '@playwright/test';

function randEmail() {
  const n = Math.floor(Math.random() * 1e9);
  return `e2e_${n}@example.com`;
}

test('register -> login -> search works', async ({ page }) => {
  // 홈 진입
  await page.goto('/');

  // 쿠키 배너/웰컴 모달이 떠 있을 수 있어 방어적으로 닫습니다.
  const cookieDismiss = page.locator('a[aria-label="dismiss cookie message"]');
  if (await cookieDismiss.isVisible().catch(() => false)) {
    await cookieDismiss.click();
  }

  // 회원가입
  const email = randEmail();
  const password = 'pw_12345!';

  await page.goto('/#/register');

  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/^password/i).fill(password);
  await page.getByLabel(/repeat password/i).fill(password);

  // Security Question 선택 (UI가 바뀔 수 있어서 role 기반)
  await page.getByRole('combobox', { name: /security question/i }).click();
  await page.getByRole('option').first().click();

  await page.getByLabel(/^answer/i).fill('seoul');

  await page.getByRole('button', { name: /register/i }).click();

  // 로그인
  await page.goto('/#/login');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /log in/i }).click();

  // 로그인 후 상단 Account 메뉴에 이메일이 노출되는 패턴을 기대합니다.
  await expect(page.getByRole('button', { name: /account/i })).toBeVisible();

  // 검색 (Juice Shop 쪽 helper 문서에서도 #searchQuery input 같은 셀렉터를 예시로 씁니다)
  // 여기서는 label/role이 불안정할 수 있어서 id 기반 접근도 같이 둡니다.
  const searchInput = page.locator('#searchQuery input');
  await expect(searchInput).toBeVisible();
  await searchInput.fill('apple');

  // 결과가 0개는 아닐 것이라는 아주 약한 보장(테스트 환경에 따라 상품 구성이 바뀔 수는 있음)
  await expect(page.locator('mat-card')).toHaveCountGreaterThan(0);
});

declare global {
  namespace PlaywrightTest {
    interface Matchers<R> {
      toHaveCountGreaterThan(count: number): R;
    }
  }
}

expect.extend({
  async toHaveCountGreaterThan(locator, count: number) {
    const c = await locator.count();
    const pass = c > count;
    return {
      pass,
      message: () => `expected locator count > ${count}, got ${c}`
    };
  }
});
```

여기서 `#searchQuery input` 같은 셀렉터 스타일은 Juice Shop의 자체 문서(튜토리얼 스크립트 예시)에도 등장합니다.[^12]

### 7) 실행 스크립트

`package.json`의 scripts 예시:

```json
{
  "scripts": {
    "fetch:stable": "node tools/fetch-cft.mjs Stable linux64",
    "fetch:beta": "node tools/fetch-cft.mjs Beta linux64",
    "test:stable": "node -e \"const j=require('child_process').execSync('node tools/fetch-cft.mjs Stable linux64',{encoding:'utf8'}); console.log(j);\" && node -e "
  }
}
```

위처럼 억지로 넣기보다, CI에서는 다음처럼 단계별로 실행하는 편이 관리가 쉽습니다.

```bash
# Stable
STABLE_JSON=$(node tools/fetch-cft.mjs Stable linux64)
STABLE_DIR=$(echo "$STABLE_JSON" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>console.log(JSON.parse(d).cacheDir));")
CHROME_CHANNEL=Stable CHROME_CACHE_DIR="$STABLE_DIR" npx playwright test

# Beta
BETA_JSON=$(node tools/fetch-cft.mjs Beta linux64)
BETA_DIR=$(echo "$BETA_JSON" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>console.log(JSON.parse(d).cacheDir));")
CHROME_CHANNEL=Beta CHROME_CACHE_DIR="$BETA_DIR" npx playwright test
```

예상 결과는 대략 이런 형태입니다.

```text
Running 1 test using 1 worker
  ✓  tests/juice-shop-happy-path.spec.ts: register -> login -> search works (12.3s)

1 passed (13.0s)
```

이 예시는 “브라우저 버전이 바뀌는 이벤트를 트리거로 테스트를 돌리는” 대신, “항상 Stable/Beta를 같이 돌려서 변화 신호를 얻는” 쪽으로 프레임을 바꿉니다. 2주 cadence에서는 이게 운영비가 덜 듭니다.

## 반론: 릴리스가 잦으면 오히려 안정적이지 않나

Google은 2주 cadence로 가면 scope가 작아져 회귀 원인 격리가 더 쉽다고 주장합니다.[^1] 이 주장은 꽤 설득력이 있습니다.

- 변경이 작으면: 원인 추적이 쉽고, 롤백 판단도 단순해집니다.
- 릴리스가 잦으면: “큰 업데이트”로 느끼는 심리적 저항이 줄어듭니다.

그런데 엔터프라이즈 운영에서 진짜 비용은 ‘변경량’보다는 ‘검증/승인/커뮤니케이션’에서 나옵니다.

- 사내 웹앱 호환성 검증: 테스트 자체보다 “누가 승인하는가”, “어디까지를 통과로 볼 것인가”가 병목
- 배포 링 운영: 기술보다도 정책(예외/정책 위반 처리/감사)이 병목

2주 cadence는 이 병목을 숨겨주지 않습니다. 변경량이 작아져도 승인 프로세스가 그대로면 결국 운영 부채로 밀립니다.

또 하나의 회의론은 “Extended Stable이 있으면 되지 않나”인데, Extended Stable 문서에도 backport가 항상 가능하지 않을 수 있다고 적혀 있습니다.[^4] 즉 Extended Stable은 ‘운영 편의’를 위한 옵션이지, ‘보안 리스크를 0으로 만드는 옵션’은 아닙니다.

## 앞으로 지켜볼 것: 2주 cadence에서 ‘진짜 깨지는 순간’은 따로 온다

내가 특히 신경 쓰는 관측 포인트는 3개입니다.

1) Stable 릴리스가 2주마다 오면서, “변경 공지/릴리스 노트 소화”가 조직에서 실제로 가능한가
- 릴리스 노트는 더 자주, 더 짧게 읽게 될 겁니다.[^2]

2) Extended Stable의 8주 milestone 경계에서 생기는 충격
- Extended Stable은 8주마다 feature milestone이 점프합니다.[^4]
- 결국 “안 바꾸던 걸 한 번에 바꾸는 날”이 생기고, 그 날이 더 위험합니다.

3) in-the-wild, 대규모 security fix 물량이 2주 cadence에서 어떻게 운영을 압박하는가
- Chrome 153 공지처럼 in-the-wild 문장이 박히는 순간, “2주 뒤에 반영”은 더 이상 선택지가 아닙니다.[^3]

## 지금 할 수 있는 일: 달력부터 바꾸고, 링을 다시 그린다

2주 cadence에 적응하는 실무 작업은 기술보다도 ‘운영의 형식’을 바꾸는 쪽이 우선입니다.

1) QA/릴리즈 캘린더에서 “브라우저 업데이트 주간”을 없앤다
- 브라우저는 더 이상 이벤트가 아니라 상시 흐름입니다.

2) Beta 기반 preflight를 고정 슬롯으로 만든다
- Nightly Beta E2E를 운영의 기본값으로 두고, 실패를 ‘기술 부채’가 아니라 ‘호환성 인시던트’로 분류합니다.

3) 링을 사용자군 중심으로 다시 나눈다
- Preview(Beta), Fast Stable, Broad Stable, Hold(Extended Stable/핀)
- 링마다 “허용하는 깨짐”과 “복구 SLA”를 다르게 둡니다.

4) 정책은 버전과 속도를 분리해 설계한다
- TargetChannel/TargetVersionPrefix/RollbackToTargetVersion으로 버전을 통제하고[^6]
- rollout fast/slow/OU로 속도를 통제합니다.[^5]

5) Stable=최신, Extended Stable=안전이라는 이분법을 버린다
- Stable이 가장 secure choice라고 Google이 명시하지만[^1],
- 조직은 비용/운영 능력/벤더 종속성 때문에 혼합 모델을 쓸 수밖에 없습니다.
- 그래서 링 설계가 곧 보안 설계가 됩니다.

2주 cadence는 브라우저 업데이트를 ‘정기 작업’에서 ‘항시 운영’으로 바꿉니다. 이 변화를 따라가려면 테스트를 더 많이 하는 게 아니라, 테스트와 배포를 묶는 방식(달력, 승인, 링)을 바꾸는 게 맞습니다.

## 참고 자료

- [Fresher features, faster fixes: The two-week release cycle is here](https://developer.chrome.com/blog/chrome-two-week-start)
- [Get features faster with Chrome's two-week release cycle](https://developer.chrome.com/blog/chrome-two-week-release)
- [Chrome Releases: Stable Channel Update for Desktop (Chrome 153)](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_0808145027.html)
- [Chrome 153 Release notes](https://developer.chrome.com/release-notes/153)
- [Extended Stable channel](https://support.google.com/chrome/a/answer/16942104)
- [Set Chrome policies for users or browsers](https://support.google.com/chrome/a/answer/2657289)
- [Manage Chrome updates (Windows)](https://support.google.com/chrome/a/answer/6350036)
- [Manage Chrome updates (Mac)](https://support.google.com/chrome/a/answer/7591084)
- [Chrome for Testing availability (JSON API endpoints)](https://github.com/GoogleChromeLabs/chrome-for-testing/blob/main/README.md)
- [OWASP Juice Shop repository README](https://github.com/juice-shop/juice-shop)
- [Walking the happy path (Juice Shop)](https://help.owasp-juice.shop/part1/happy-path.html)

[^1]: <https://developer.chrome.com/blog/chrome-two-week-start>
[^2]: <https://developer.chrome.com/release-notes/153?authuser=4>
[^3]: <https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_0808145027.html>
[^4]: <https://support.google.com/chrome/a/answer/16942104?hl=en>
[^5]: <https://support.google.com/chrome/a/answer/2657289?hl=en>
[^6]: <https://support.google.com/chrome/a/answer/6350036?rd=1>
[^7]: <https://github.com/GoogleChromeLabs/chrome-for-testing/blob/main/README.md>
[^8]: <https://help.owasp-juice.shop/part3/codebase.html>
[^9]: <https://www.npmjs.com/package/%40playwright/test?activeTab=versions>
[^10]: <https://hub.docker.com/r/bkimminich/juice-shop/tags>
[^11]: <https://help.owasp-juice.shop/part1/happy-path.html>
[^12]: <https://help.owasp-juice.shop/part3/tutorials.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
