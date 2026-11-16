---
title: "Vite 초고빈도 릴리스 대응: minor 고정과 릴리스 링"
description: "Vite 8.3.8 패치에 섞인 @types/node v26 같은 변화까지 흡수하는 버전·CI·릴리스 링 운영 템플릿."
date: 2026-11-16 14:44:40 +0900
categories: ["Frontend", "Vite"]
tags: ["vite", "semver", "monorepo", "ci", "types-node-v26", "release-management"]
render_with_liquid: false
---

## v8.3.8 패치 릴리스에서 드러난 운영 리스크의 성격

Vite `v8.3.8`은 2026-11-11에 릴리스되었고, 릴리스 노트의 항목 중 하나가 `deps: update dependency @types/node to v26`입니다. 패치 릴리스인데도 타입 생태계의 메이저 업데이트가 같이 들어온 셈입니다. 이런 종류의 변경은 런타임 동작(예: dev server/HMR)보다도, CI에서 더 먼저 터집니다. `tsc --noEmit`, `vite build`, `vitest`가 얽혀 있는 프로젝트라면 특히 그렇습니다. [Vite v8.3.8 릴리스 노트](https://github.com/vitejs/vite/releases/tag/v8.3.8).[^1]

여기서 중요한 포인트는 “Vite가 패치에서 무리한 일을 했다”가 아닙니다. 패치 릴리스의 변경량이 작더라도, 프론트엔드 빌드 체인은 **외부 생태계 변화가 타입/툴체인 레이어를 타고 들어오면서** 체감 파급이 커질 수 있다는 쪽이 더 현실적입니다. Vite 릴리스 문서에서도 TypeScript definitions의 non-semver 성격을 별도로 다룹니다. 즉, 이 문제는 사건이 아니라 구조입니다. [Vite Releases 문서](https://vite.dev/releases).[^2]

이 글에서의 전제는 세 가지입니다.

- Vite는 지원 라인을 여러 개 유지하고, 중요한 수정/보안 패치를 백포트합니다.
- semver range와 lockfile은 같은 문제를 푸는 도구가 아니며, 역할을 분리해야 합니다.
- 빌드 도구는 “업데이트”가 아니라 “운영”의 대상이고, 릴리스 링으로 다루는 편이 비용이 낮습니다.

## Vite의 지원 라인과 백포트 정책을 입력값으로 두기

Vite는 고정된 릴리스 주기가 없고, 패치 릴리스는 보통 매주 나옵니다. 이 말은 곧 “패치만 열어두면 알아서 최신이 되겠지”가 아니라, “패치만 열어둬도 매주 무엇인가가 들어올 수 있다”에 가깝습니다. [Vite Releases 문서](https://vite.dev/releases).[^2]

지원 라인은 문서에 요약이 명확히 적혀 있습니다.

- 정기적인 패치는 `vite@8.3`
- 중요한 수정과 보안 패치 백포트: `vite@7.3`, `vite@8.2`
- 보안 패치만 백포트: `vite@6.4`, `vite@8.1`

이 정책이 운영 관점에서 의미하는 바는 단순합니다.

1) “어느 minor에 있을지” 자체가 안정성/변경량을 결정하는 전략이 됩니다. (8.3 라인은 더 자주 변합니다)

2) “보안 패치만 받을 수 있는 라인”을 Vite가 공식적으로 제공합니다. 빌드 도구에서 이 정도의 백포트 체계를 문서에 박아두는 프로젝트는 흔치 않습니다. 운영자가 선택할 수 있는 폭이 넓습니다.

3) 반대로, 지원 종료된 버전은 아무리 lockfile로 고정해도 장기 운영에서 불리합니다. 취약점이 떠도 upstream에서 더 이상 패치를 안 줍니다.

내 경우 프론트엔드 툴체인은 “업그레이드 속도”가 아니라 “문제 발생 시 복구 속도”가 비용을 좌우했습니다. Vite의 백포트 정책은 그 복구 속도를 구조적으로 끌어올릴 수 있는 레버입니다. 다만 그 레버를 쓰려면, semver range/lockfile/CI를 백포트 정책에 맞춰 재설계해야 합니다.

## semver range와 lockfile을 섞어 쓰지 말고 역할을 나누기

먼저, semver range의 기계적인 의미부터 정리해야 합니다.

- `~8.3.8`은 `>=8.3.8 <8.4.0`(즉 8.3.x 패치만)
- `^8.3.8`은 `>=8.3.8 <9.0.0`(즉 8.x의 minor까지)

이는 npm이 사용하는 `node-semver` 문서에 그대로 정의되어 있습니다. [node-semver의 tilde range 정의](https://github.com/npm/node-semver).[^3]

여기서 **minor 고정**이 필요한 이유는 두 가지입니다.

- Vite가 “TypeScript definitions는 minor 사이에서라도 호환이 깨질 수 있다”고 문서에 명시합니다. 즉, TypeScript를 쓰는 프로젝트는 “minor 자동 추종”이 안전하지 않을 수 있습니다. [Vite Releases의 TypeScript Definitions 섹션](https://vite.dev/releases).[^2]
- 프론트엔드 repo에서 Vite는 종종 “빌드 결과물 계약”입니다. 번들 결과가 바뀌면 캐시 무효화, Sentry sourcemap 경로, CDN 캐시 히트율까지 흔들립니다. 기능 추가 minor가 들어오는 순간부터는 QA 비용이 생깁니다.

그렇다고 해서 `vite`를 완전히 `8.3.8`에 딱 고정하는 것이 최선이냐 하면, 그것도 아닙니다. Vite는 패치가 매주 나온다고 했고, 지원 라인에는 보안/중요 버그 수정이 지속적으로 들어옵니다. 그러면 패치를 막아버리면 “문제 있는 버전을 안 올리는 것”과 함께 “고쳐진 버전도 안 올리는 것”이 됩니다.

그래서 semver range와 lockfile의 책임을 분리하는 쪽이 낫습니다.

- `package.json`의 range: 정책(의도)을 표현합니다. 여기에는 “어느 minor 라인을 타는가”를 명시하는 편이 운영에 유리합니다.
- lockfile: 결과(재현성)를 표현합니다. 여기에는 “이번 배포가 어떤 dependency graph로 만들어졌는가”를 고정해야 합니다.

특히 `pnpm`은 CI 환경에서 lockfile이 있으면 `frozenLockfile`이 기본적으로 `true`가 되도록 설계되어 있습니다. CI에서는 “의도치 않은 재해석(resolution)”이 아니라 “재현(reproducible install)”이 기본값입니다. [pnpm lockfile settings 문서](https://github.com/pnpm/pnpm/blob/main/pnpm/docs/settings/store.md).[^4]

정리하면, 이상적인 조합은 보통 아래처럼 갑니다.

- Vite: `~8.3.8` (minor 고정 + 패치 수용)
- CI: `pnpm install --frozen-lockfile` (해석 금지)
- 업데이트: 별도의 프로세스(리노베이트/수동/스케줄드 잡)에서 lockfile 갱신을 통제

이 조합의 장점은 “매주 패치가 나와도, 매주 배포가 강제되지 않는다”는 점입니다. lockfile이 바뀌지 않는 한, 배포 artifact는 그대로입니다.

## Vite 백포트 라인을 운영 버전 정책으로 번역하기

Vite의 문서는 지원 라인에 대해 “어떤 라인에 어떤 수준의 패치가 들어오는지”를 구분해 둡니다. 여기서 **백포트 라인**을 어떻게 쓸지가 관건입니다. [Vite Supported Versions](https://vite.dev/releases).[^2]

운영 정책으로 번역하면 선택지는 크게 3개로 쪼개집니다.

### 1) Current minor(8.3)를 따른다: 변경을 자주 받는 대신 빨리 고친다

- 장점: 버그 수정이 빨리 들어옵니다. “정기적인 패치”가 들어오는 라인이니까요.
- 단점: 패치 릴리스에 생태계 업데이트가 끼어들 가능성을 감수해야 합니다. v8.3.8의 `@types/node` 메이저 업데이트가 그 예입니다.

이 선택은 “빌드 체인 자체가 제품 경쟁력”인 팀(빌드 시간이 비용이거나, DX가 납기)에서 합리적입니다.

### 2) Previous minor(8.2)로 내려간다: 중요한 수정/보안만 받는다

- 장점: 변경량을 줄이면서도 upstream이 “중요한 것”은 backport 해줍니다.
- 단점: 중요하지 않은(하지만 우리에게는 중요할 수 있는) 버그 픽스는 못 받을 수 있습니다.

현실에서 8.2를 택하는 순간은 대개 “릴리스는 자주 하되, 빌드 도구 업데이트는 덜 하고 싶다”는 상황입니다. 예를 들어 분기마다 대형 캠페인이 있고 그 사이에는 광고 픽스/컨텐츠 수정이 대부분인 경우가 그렇습니다.

### 3) Security-only 라인(8.1, 6.4)으로 내려간다: 리스크를 보안에만 한정한다

- 장점: 기능/동작 변화의 가능성을 더 낮춥니다.
- 단점: 운영 중 발견되는 자잘한 버그(Windows/네트워크/캐시 관련)가 upstream 패치로 해결되지 않을 수 있습니다.

이 선택은 “프론트엔드 빌드 도구를 규제/감사 관점에서 다루는 조직”에서 의미가 있습니다. 다만 프론트엔드 생태계는 보안만 고치고 기능/호환 문제를 방치하면, 장기적으로 비용이 더 커지기도 합니다.

내 경험상 가장 많은 조직이 1)과 2) 사이에서 왔다 갔다 합니다. 중요한 건 “우리 팀이 무엇을 선호한다”가 아니라, **CI에서 어떤 종류의 변화(타입/번들/테스트)를 조기에 잡을 수 있느냐**가 선택을 결정한다는 점입니다.

## 패치에 섞여 들어오는 타입 체인 변화: @types/node v26의 파급 경로

Vite v8.3.8 릴리스 노트에서 `@types/node`가 v26으로 올라갔다는 사실은 하나의 스위치에 불과합니다. 문제는 그 스위치가 어디에 연결돼 있느냐입니다. [Vite v8.3.8 릴리스 노트](https://github.com/vitejs/vite/releases/tag/v8.3.8).[^1]

프론트엔드 프로젝트에서 `@types/node`는 보통 아래 경로로 영향을 줍니다.

1) `vite.config.ts`(또는 `vitest.config.ts`)가 Node 환경에서 실행됩니다.
- `process.env`, `Buffer`, `fs`, `path` 같은 타입이 필요해져서 `@types/node`가 devDependency로 들어옵니다.

2) 번들 대상 코드(브라우저 코드)까지 Node 타입이 섞입니다.
- `tsconfig.json`의 `types` 설정이나, monorepo의 tsconfig 상속 구조 때문에 툴링 타입이 앱 타입 공간까지 들어오는 경우가 많습니다.
- 이때 Node 타입이 DOM 타입과 충돌하거나, 신규 Web API 타입이 추가되면서 기존 선언과 겹칠 수 있습니다.

3) 타입 정의는 단지 IDE 보조가 아니라 “빌드 실패 요인”입니다.
- `skipLibCheck`를 켰더라도, 파싱 자체가 실패하면 `tsc`는 죽습니다.

실제로 DefinitelyTyped 쪽에서는 `@types/node@26.1.0`에서 TypeScript 5.0의 문법(`const` type parameters)을 사용해서, TypeScript 5.0 미만에서는 `skipLibCheck`로도 회피가 안 되는 파싱 에러가 난다는 논의가 있습니다. [DefinitelyTyped discussion #75225](https://github.com/DefinitelyTyped/DefinitelyTyped/discussions/75225).[^5]

이게 왜 Vite 운영에서 중요하냐면, 팀이 “Vite는 패치만 올렸다”고 생각하는데 실제로는 “타입 체인의 최소 요구사항이 올라갔다”로 해석될 수 있기 때문입니다. 그리고 이 변화는 보통 Vite changelog에는 1줄로만 남습니다.

추가로, Vite monorepo 자체도 `@types/node`를 사용합니다. 레포의 `package.json` 기준으로는 `@types/node`가 `^26.6.6`까지 올라가 있습니다. upstream이 v26을 기준으로 개발/테스트하는 쪽으로 기울고 있다는 신호로 볼 수 있습니다. [vitejs/vite package.json](https://github.com/vitejs/vite/blob/main/package.json).[^6]

여기서의 결론은 단순합니다. **@types/node v26**은 “Node 26을 당장 올려야 한다”가 아니라, “타입 그래프의 전제가 바뀔 수 있다”에 가깝습니다.

### 타입 파급을 줄이는 가장 확실한 구조: tsconfig를 나눈다

프론트엔드에서 가장 흔한 실수는 `tsconfig.json`을 하나로 유지하면서, 툴링 코드(설정 파일)와 앱 코드를 같은 타입 공간에 넣는 것입니다.

추천은 아래처럼 명시적으로 쪼개는 방식입니다.

- `tsconfig.app.json`: 브라우저 앱(React/Svelte/Vue 등)
- `tsconfig.node.json`: Vite/Vitest 설정 및 Node에서 도는 스크립트

예시(실제로 동작 가능한 수준으로, pnpm + Vite + TypeScript 기준):

```json
// tsconfig.app.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,

    "types": ["vite/client"],
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

```json
// tsconfig.node.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022"],
    "module": "ESNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noEmit": true,

    "types": ["node"],
    "skipLibCheck": true
  },
  "include": ["vite.config.ts", "vitest.config.ts", "scripts/**/*.ts"]
}
```

그리고 CI에서는 둘을 분리해서 돌립니다.

```json
// package.json (일부)
{
  "scripts": {
    "typecheck:app": "tsc -p tsconfig.app.json",
    "typecheck:node": "tsc -p tsconfig.node.json",
    "typecheck": "pnpm -s typecheck:app && pnpm -s typecheck:node",
    "build": "vite build"
  }
}
```

이렇게 해두면 `@types/node`가 바뀌었을 때 영향 범위가 “설정/스크립트”로 제한됩니다. 타입 충돌을 겪더라도 앱 자체의 타입 공간이 덜 흔들립니다.

## CI에서 패치 릴리스의 생태계 변화를 조기 탐지하기

Vite는 새 버전을 릴리스하기 전에 `vite-ecosystem-ci`로 생태계 프로젝트를 상대로 통합 테스트를 돌린다고 문서에 적어둡니다. upstream은 upstream대로 “변경이 안전한지”를 확인합니다. 문제는 각 회사의 monorepo는 생태계 CI의 커버리지 밖이라는 점입니다. [vite-ecosystem-ci](https://github.com/vitejs/vite-ecosystem-ci).[^7]

그래서 사내 CI에는 “우리 repo 기준의 ecosystem CI”가 필요합니다. 구현은 어렵지 않고, 핵심은 설치를 2번 돌리는 것입니다.

- 1번: 고정된 lockfile로 설치 + 빌드 (재현성 확인)
- 2번: 의도적으로 드리프트(패치 업데이트/특정 deps 업데이트)를 만든 뒤 빌드 (변화 조기 감지)

여기서 2번이 없으면, `v8.3.8` 같은 패치가 릴리스된 사실을 알아도 “우리에게 어떤 영향이 있는지”를 PR 머지 시점에야 알게 됩니다.

### 구현 예시: GitHub Actions에서 stable + drift 두 링을 돌린다

아래 YAML은 pnpm workspace를 가정합니다. lockfile은 `pnpm-lock.yaml`입니다.

```yaml
# .github/workflows/ci.yml
name: ci

on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        ring: [stable, drift]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 24

      - name: Enable corepack
        run: corepack enable

      - name: Install (stable)
        if: matrix.ring == 'stable'
        run: pnpm install --frozen-lockfile

      - name: Install + drift update (drift)
        if: matrix.ring == 'drift'
        run: |
          pnpm install --frozen-lockfile
          # lockfile은 건드리지 않고, 워크스페이스에만 임시로 최신 패치를 풀어봅니다.
          # --no-save를 쓰면 package.json은 안 바뀌고, pnpm은 node_modules만 재구성합니다.
          pnpm update -r --latest --no-save vite
          pnpm update -r --latest --no-save @types/node

      - name: Typecheck
        run: pnpm -r run typecheck

      - name: Build
        run: pnpm -r run build

      - name: Test
        run: pnpm -r run test
```

이 방식의 장점은 명확합니다.

- stable 링이 초록이면 “지금 배포 가능한 상태”가 보장됩니다.
- drift 링이 초록이면 “지금 당장 패치/타입 업데이트가 들어와도 버틸 가능성”이 올라갑니다.
- drift 링이 빨강이면, 의존성 업데이트 PR이 오기 전에 이미 어떤 축이 깨질지 알 수 있습니다.

반대로 단점도 있습니다.

- `pnpm update --no-save`는 lockfile을 안 바꾸지만, node_modules 트리를 바꾸므로 CI 시간은 늘어납니다.
- 패치 드리프트가 너무 공격적이면(예: 모든 deps를 `--latest`) 매번 빨강이 되어 신뢰도가 떨어집니다.

그래서 drift 링의 scope는 “빌드 체인의 축”으로 제한하는 편이 좋았습니다.

- Vite
- Rollup/ESBuild/SWC 같이 번들러 핵심에 가까운 것
- TypeScript
- `@types/node`

패치 릴리스의 체감 위험은 대개 이 네 축에서 나옵니다.

### drift의 해석을 자동화할 때: diff를 남긴다

drift 링은 실패해도 됩니다. 대신 실패 로그가 “원인 추적 가능한 형태”여야 합니다.

내가 자주 넣는 단계는 다음입니다.

- `pnpm why @types/node`
- `pnpm list vite --depth 0` (워크스페이스마다 Vite가 분산되어 있으면 특히)
- `node -p "process.version"` (런타임 차이로 인한 타입/번들 변화인지 분리)

이런 정보는 “패치 릴리스가 문제다”가 아니라 “우리 repo의 타입/툴 계약이 어디서 새고 있다”를 보여줍니다.

## 릴리스 링으로 빌드 도구를 운영하는 템플릿

Vite 릴리스 문서는 pre-release(베타/알파)를 프로덕션에서 쓰지 말고, 쓴다면 정확한 버전으로 pin 하라고 말합니다. [Vite Releases의 Pre Releases 섹션](https://vite.dev/releases).[^2]

이 문장을 팀 운영으로 번역하면 **릴리스 링** 모델이 됩니다.

- canary: pre-release 또는 next patch를 먼저 맞아본다
- stable: 현재 minor 라인의 패치를 통제된 속도로 반영한다
- extended/backport: 한 단계 낮은 지원 라인(예: 8.2)을 운용하며 중요한 수정/보안만 받는다

여기서 핵심은 “링을 코드베이스로 분리할 것인가, CI 잡으로 분리할 것인가”입니다. 나는 CI 잡으로 분리하는 쪽이 덜 번거로웠습니다. 코드는 하나이고, 설치/해석만 다르게 가져가면 되기 때문입니다.

### 템플릿 1) ring별로 lockfile을 분리한다

링별 lockfile을 아예 분리하면, 같은 커밋에 대해 서로 다른 의존성 그래프를 “버전으로” 관리할 수 있습니다.

- `pnpm-lock.yaml` (stable)
- `pnpm-lock.canary.yaml` (canary)

pnpm은 lockfile을 하나만 쓰는 워크플로가 일반적이지만, 링 운영에서는 두 lockfile이 실제로 도움이 됩니다. 특히 canary lockfile은 머지되지 않아도 됩니다. 목적이 “조기 경보”이기 때문입니다.

이 경우 CI에서 canary 링은 이런 식으로 만듭니다.

```bash
# stable
pnpm install --frozen-lockfile

# canary (별도 lockfile 생성)
cp pnpm-lock.yaml pnpm-lock.canary.yaml
pnpm install --lockfile-only --lockfile-dir .
# (여기서는 pnpm 버전에 따라 lockfile 파일명 직접 지정이 필요할 수 있어,
#  실무에서는 canary 작업 디렉터리를 따로 만들어 운영하는 편이 더 안전합니다.)
```

나는 파일명 커스터마이징은 pnpm 버전/옵션에 따라 흔들릴 여지가 있어, “canary 작업 디렉터리 분리” 쪽을 더 많이 썼습니다.

### 템플릿 2) 링별로 workspace override를 둔다

링 운영에서 자주 필요한 기능은 “특정 dependency만 강제로 고정/교체”입니다. 예를 들면 `@types/node`가 v26으로 올라가면서 TypeScript 파서가 터지는 경우, 전체 업데이트를 되돌리는 대신 `@types/node`만 pin 하고 시간을 벌고 싶을 수 있습니다.

pnpm은 `overrides`로 dependency graph 어디든 버전을 강제할 수 있습니다. 이 기능은 “백포팅”, “단일 버전 강제”, “fork로 교체” 같은 용례를 문서에서 직접 언급합니다. [pnpm overrides 문서](https://github.com/pnpm/pnpm/blob/main/pnpm/docs/settings/dependency-resolution.md).[^8]

예시:

```yaml
# pnpm-workspace.yaml
packages:
  - apps/*
  - packages/*

# 링에서만 일시적으로 타입 체인을 고정하고 싶을 때
overrides:
  "@types/node": "25.999.0"
```

버전 숫자는 예시입니다. 포인트는 “Vite는 올리되, 타입 체인은 잠깐 멈춘다” 같은 선택지가 생긴다는 점입니다. npm 자체도 root `package.json`의 `overrides` 기능을 제공합니다. 즉, pnpm에 한정된 패턴이 아닙니다. [npm package.json overrides 문서](https://docs.npmjs.com/cli/configuring-npm/package-json/).[^9]

이 패턴을 쓰면, v8.3.8 같은 패치 릴리스에 섞인 생태계 업데이트를 “업스트림 정책을 부정하지 않으면서도” 사내 일정에 맞게 흡수할 수 있습니다.

다만 overrides는 빚입니다. 이유를 잊는 순간부터는 내부 fork와 같은 유지보수 비용이 생깁니다. 그래서 overrides를 도입할 때는 PR 설명에 아래 3가지를 강제로 남기는 편이 안전합니다.

- 왜 필요한가(증상/CI 로그)
- 언제 제거할 것인가(조건)
- 누가 소유하는가(담당 팀)

## 실제 버전 정책 제안: Vite minor 고정 + 링 운영 + 타입 체인 분리

앞의 내용을 합쳐서, 운영 가능한 정책 형태로 떨어뜨리면 아래처럼 됩니다.

### 1) package.json의 range는 Vite minor를 고정한다

```json
{
  "devDependencies": {
    "vite": "~8.3.8"
  }
}
```

`^8.3.8`로 두면 다음 minor(`8.4.0`)가 자동으로 들어올 수 있습니다. Vite 문서가 TypeScript definitions의 edge case를 따로 다룬 이상, TypeScript 프로젝트에서 그 선택은 리스크가 됩니다. [Vite Releases](https://vite.dev/releases).[^2]

### 2) CI의 기본은 frozen lockfile이다

- `pnpm install --frozen-lockfile`

pnpm은 CI에서 frozen 설치를 기본값으로 두는 방향입니다. 이는 “버전 범위를 느슨하게 가져가더라도 배포는 고정된 lockfile로 한다”는 운영 모델과 잘 맞습니다. [pnpm lockfile settings](https://github.com/pnpm/pnpm/blob/main/pnpm/docs/settings/store.md).[^4]

### 3) canary/drift 링으로 ‘다음 패치에서 깨질 것’을 미리 본다

- stable 링: frozen lockfile
- drift 링: Vite와 `@types/node`만 `--latest --no-save`로 흔들어 본다

이 링은 실패해도 됩니다. 대신 “깨질 미래를 미리 아는 것”이 목적이어야 합니다.

### 4) tsconfig를 app/node로 분리해 @types/node 파급을 격리한다

`@types/node`가 메이저로 올라가는 순간 타입 공간이 흔들릴 수 있으니, 애초에 타입 공간을 격리해 둡니다.

이 작업은 Vite 업그레이드와 별개로 가치가 있습니다. 예전 글에서 다뤘던 “런타임 계약을 명시적으로 분리한다”는 방향과도 결이 같습니다.

- [Node 27 연 1회 메이저에 맞춘 사내 런타임 정책 재설계](https://daewooki.github.io/posts/nodejs-annual-major-enterprise-runtime-policy/)
- [Vitest 5.1 업그레이드: 기본값 변화로 CI 계약 고정](https://daewooki.github.io/posts/vitest-5-1-ci-defaults-contract/)

## 판단 기준: 업데이트를 ‘막는’ 게 아니라 ‘흡수’하는 구조를 만든다

Vite는 패치가 보통 매주 나오는 쪽을 선택했고, 동시에 지원 라인/백포트 정책을 문서로 명확히 했습니다. 이 조합은 사용자에게 선택지를 줍니다. 아무 생각 없이 `^`로 최신을 추종하면 피곤해지고, 아무 생각 없이 exact pin으로 멈추면 취약해집니다.

운영에서 중요한 건 “우리 팀은 업데이트를 한다/안 한다”가 아니라, 아래 질문에 답이 있느냐입니다.

- 어느 라인(8.3 / 8.2 / 8.1 …)을 기준으로 삼는가
- lockfile을 통해 배포 artifact 재현성을 보장하는가
- 패치 릴리스에 섞여 들어오는 타입/툴체인 변화(`@types/node` 같은)를 별도 링으로 조기 탐지하는가
- 타입 공간을 app/node로 분리해 파급을 줄였는가
- overrides 같은 임시 조치를 “빚”으로 관리할 수 있는가

이 다섯 가지가 갖춰지면, 초고빈도 릴리스는 불안 요소가 아니라 “고쳐진 걸 빨리 가져올 수 있는 선택지”로 바뀝니다.

## 참고 자료

- [Vite v8.3.8 릴리스 노트](https://github.com/vitejs/vite/releases/tag/v8.3.8)
- [Vite Releases 문서](https://vite.dev/releases)
- [vitejs/vite docs/releases.md (GitHub)](https://github.com/vitejs/vite/blob/main/docs/releases.md?plain=1)
- [vite-ecosystem-ci](https://github.com/vitejs/vite-ecosystem-ci)
- [node-semver](https://github.com/npm/node-semver)
- [pnpm overrides 문서](https://github.com/pnpm/pnpm/blob/main/pnpm/docs/settings/dependency-resolution.md)
- [pnpm lockfile settings 문서](https://github.com/pnpm/pnpm/blob/main/pnpm/docs/settings/store.md)
- [npm package.json overrides 문서](https://docs.npmjs.com/cli/configuring-npm/package-json/)
- [@types/node (npm)](https://www.npmjs.com/package/%40types/node)
- [DefinitelyTyped discussion #75225](https://github.com/DefinitelyTyped/DefinitelyTyped/discussions/75225)
- [vitejs/vite package.json](https://github.com/vitejs/vite/blob/main/package.json)

[^1]: <https://github.com/vitejs/vite/releases/tag/v8.3.8>
[^2]: <https://vite.dev/releases>
[^3]: <https://github.com/npm/node-semver>
[^4]: <https://github.com/pnpm/pnpm/blob/main/pnpm/docs/settings/store.md>
[^5]: <https://github.com/DefinitelyTyped/DefinitelyTyped/discussions/75225>
[^6]: <https://github.com/vitejs/vite/blob/main/package.json>
[^7]: <https://github.com/vitejs/vite-ecosystem-ci>
[^8]: <https://github.com/pnpm/pnpm/blob/main/pnpm/docs/settings/dependency-resolution.md>
[^9]: <https://docs.npmjs.com/cli/configuring-npm/package-json/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
