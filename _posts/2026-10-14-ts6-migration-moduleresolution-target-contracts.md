---
title: "TypeScript 6.0 마이그레이션: moduleResolution·target 기본값이 빌드를 깨는 경로"
description: "TS 6.0은 타입 기능보다 빌드 계약을 바꿉니다. node10 deprecate와 기본값 변화가 모노레포 툴체인에 퍼지는 경로를 실전 예제로 정리합니다."
date: 2026-10-14 10:09:37 +0900
categories: ["Frontend", "TypeScript"]
tags: ["typescript-6", "moduleresolution", "tsconfig", "monorepo", "esm-cjs"]
render_with_liquid: false
---

## TS 6.0을 타입 기능 업데이트로 보면 놓치는 것
TypeScript 6.0은 언어 기능보다 설정과 출력물의 계약(contract)을 손보는 릴리스에 가깝습니다. Microsoft의 공식 발표에서도 TS 6.0을 TypeScript 7.0(Go 기반 native port)로 가는 전환 릴리스로 규정하고, 6.0에서 deprecate된 옵션들이 7.0에서 제거된다고 못 박았습니다. [Announcing TypeScript 6.0](https://devblogs.microsoft.com/typescript/announcing-typescript-6-0/)[^1]

이 관점이 중요한 이유는, TSConfig 한 줄이 바뀌면 다음 레이어를 연쇄적으로 흔들기 때문입니다.

- tsc의 module graph 구성 방식이 바뀌고(어떤 파일이 “같은 모듈”로 엮이는지)
- emit된 JavaScript의 module format / syntax baseline이 바뀌며
- bundler가 기대하는 import specifier 규칙이 바뀌고
- test runner(Jest/Vitest) 및 Node 런타임 실행 방식(type: module, exports/imports, extension 규칙)이 바뀌며
- monorepo에서는 각 패키지의 boundary(rootDir/outDir, project references)가 달라져서 빌드가 깨집니다.

내 경우 TS 6.0 마이그레이션은 “에러 고치기”가 아니라 **빌드 파이프라인에서 누가 module resolution을 책임지는지**를 명시적으로 선언하는 작업이었습니다. 그 선언이 없으면, TS 6.0의 deprecation과 기본값 변경은 “조용한 업그레이드”가 아니라 CI를 멈추는 업그레이드가 됩니다.

## moduleResolution=node/node10 deprecate: 단순 경고가 아니라 빌드 차단으로 들어온다
TS 6.0에서 `--moduleResolution node`(alias로서의 node10)가 deprecate된 건 단순한 “옛날 알고리즘이니 바꾸세요” 수준이 아닙니다. release notes에 명시적으로 `--moduleResolution node`(즉 node10)가 deprecated라고 적혀 있고, 권장 이행 경로로 `nodenext`(Node를 직접 타겟팅하는 경우) 또는 `bundler`(bundler/Bun을 쓰는 경우)를 제시합니다. [TypeScript 6.0 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html)[^2]

실제로 TS 6.0 계열에서는 `moduleResolution=node10`이 “deprecation warning”이 아니라 에러 코드(TS5107)로 CI를 막는 케이스가 꽤 빨리 등장했습니다. GitHub 이슈에서도 `moduleResolution=node10` deprecate가 에러로 보고됩니다.[^3]

여기서 실무적으로 중요한 포인트는 두 가지입니다.

1) `ignoreDeprecations`는 임시 연명 장치다

공식 발표는 TS 6.0에서 deprecation을 무시하기 위해 `"ignoreDeprecations": "6.0"`를 설정할 수 있다고 말하지만, 동시에 TS 7.0에서 deprecated 옵션이 지원되지 않는다고 못 박습니다. [Announcing TypeScript 6.0](https://devblogs.microsoft.com/typescript/announcing-typescript-6-0/)[^1]

즉 `ignoreDeprecations`는 “업그레이드에 성공했다”가 아니라 “미지급 부채를 숨겼다”에 가깝습니다.

2) node10을 유지하려는 의사결정 자체가 계약 위반이 되는 순간이 온다

`moduleResolution=node10`은 Node.js 10의 resolution을 모델링합니다. TS 팀은 이게 현대 Node의 동작을 반영하지 못하니 더 이상 좋은 표현이 아니라고 설명합니다. [TypeScript 6.0 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html)[^2]

문제는 여기서 끝나지 않습니다. 현대 생태계는 `package.json`의 `exports`/`imports`에 강하게 기대고 있고, 이건 `node16`/`nodenext`/`bundler` 쪽 알고리즘이 더 “정답에 가까운 시뮬레이션”을 제공합니다. `moduleResolution` 옵션 문서도 `node10`은 구형 Node를 위한 것이고 modern code에서 필요 없을 가능성이 높다고 못 박습니다. [TSConfig moduleResolution](https://www.typescriptlang.org/tsconfig/moduleResolution.html)[^4]

## TS 6.0 기본값 변화: “명시하지 않은 설정”이 빌드의 암묵 계약이 된다
TS 6.0에서 특히 체감이 큰 건 “명시하지 않은 옵션들”입니다. release notes는 다음과 같은 기본값 변경을 언급합니다.

- `strict` 기본값이 true
- `module` 기본값이 `esnext`
- `target` 기본값이 “최신 ECMAScript 버전(현재는 es2025)”로 떠 있는 값
- `rootDir` 기본값이 tsconfig.json이 있는 디렉터리로 고정

이 중 글의 주제인 `target`과 `rootDir`은 특히 모노레포에서 사고가 납니다. `rootDir` 기본값 변경은 release notes에 명시돼 있고, 6.0부터는 rootDir이 항상 tsconfig.json의 디렉터리로 잡힌다고 적혀 있습니다. [TypeScript 6.0 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html)[^2]

`module`/`target` 기본값 변화는 더 교묘합니다.

- 타입 체크는 통과하는데 emit이 바뀌어서 런타임이 죽습니다.
- “이 패키지는 Node에서 실행되는 스크립트였나, bundler가 먹는 라이브러리였나”가 tsconfig에 남아 있지 않으면, TS 6.0은 ESM 쪽으로 밀어버립니다.
- test runner는 emit 결과물 또는 transform 경로에 따라 ESM/CJS를 다르게 다루기 때문에(특히 Jest 계열) `module`/`target`의 default drift는 테스트만 깨는 형태로도 나타납니다.

결론부터 말하면 TS 6.0에서는 **tsconfig에서 ‘기본값에 기대는 습관’이 리스크가 됐습니다.**[^2]

## bundler vs nodenext: moduleResolution이 바뀌면 import specifier 규칙부터 달라진다
`moduleResolution`은 단순히 “node_modules에서 찾는 방식” 정도가 아닙니다. 어떤 specifier가 유효한지, `exports`/`imports`를 어떻게 해석하는지, 확장자 요구사항을 어떻게 다루는지까지 포함해 module graph의 규칙을 바꿉니다.

공식 문서는 각 모드의 성격을 이렇게 설명합니다.

- `node16`/`nodenext`: 현대 Node의 ESM/CJS 규칙을 모델링(출력 JS에서 Node가 보게 될 `import`/`require`에 따라 resolution이 갈라짐)
- `bundler`: bundler 환경을 모델링하며, Node resolution 모드와 달리 relative import에서 file extension을 강제하지 않는다
- `node10`: 구형 Node(CJS) 모델

이 요약만으로도 “웹 프론트엔드 번들링 앱”과 “Node에서 직접 실행되는 코드”를 같은 `moduleResolution`로 묶는 게 왜 위험한지 드러납니다. [TSConfig moduleResolution](https://www.typescriptlang.org/tsconfig/moduleResolution.html)[^4]

추가로 TS 6.0에서 현실적인 이행 경로를 열어준 변화가 하나 있습니다. `moduleResolution=bundler`가 원래는 `module=esnext/preserve`에서만 허용되었는데, TS 6.0에서 `module=commonjs`와 함께 쓸 수 있게 됐습니다. 이는 `moduleResolution=node10` deprecate로 인해 bundler 기반 프로젝트가 “당장 ESM emit으로 넘어가지 않고도” resolution만 옮길 수 있는 경로를 만든 셈입니다. [TypeScript 6.0 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html)[^2]

이 조합은 종종 프론트엔드 모노레포에서 유용합니다.

- declaration emit, type-check는 bundler 관점의 resolution을 따르게 하고
- 실제 런타임 emit(module)은 단계적으로 옮기거나(혹은 bundler가 처리)
- Node 스크립트나 테스트는 별도 tsconfig로 nodenext/cjs를 분리

## 실전 예제: pnpm 모노레포에서 TS 6.0 업그레이드가 CI를 멈추는 형태
예제는 “웹 앱 + UI 라이브러리 + Node 스크립트”를 함께 가진 흔한 모노레포로 잡습니다.

- `@acme/shared`: 공용 유틸
- `@acme/ui`: React 컴포넌트 라이브러리(번들러가 먹음)
- `@acme/app`: Vite 같은 번들러 기반 앱
- `@acme/scripts`: CI에서 실행되는 Node 스크립트(tsc로 빌드해서 node로 실행)

### 디렉터리 구조
```bash
repo/
  package.json
  pnpm-workspace.yaml
  tsconfig.base.json
  packages/
    shared/
      src/
        index.ts
      tsconfig.json
    ui/
      src/
        Button.tsx
        index.ts
      tsconfig.json
    app/
      src/
        main.tsx
      tsconfig.json
    scripts/
      src/
        build-manifest.ts
      tsconfig.json
      package.json
```

### (업그레이드 전) 문제를 품은 tsconfig.base.json
핵심은 “구성에 의도가 드러나지 않는다”는 점입니다.

```json
{
  "compilerOptions": {
    "composite": true,
    "declaration": true,
    "declarationMap": true,

    "moduleResolution": "node",

    "outDir": "dist",
    "skipLibCheck": true
  }
}
```

- `moduleResolution`이 사실상 node10 alias에 걸려 있습니다. TS 6.0에서 deprecate 대상입니다.[^2]
- `target`, `module`, `rootDir`를 명시하지 않았습니다. TS 6.0에서 기본값이 바뀌면 emit과 경계가 흔들립니다.[^2]

이 상태에서 TS 6.0으로 올리면 대체로 다음 3가지 중 하나가 터집니다.

1) 즉시 컴파일 에러(TS5107)로 멈춘다: moduleResolution=node10 deprecate
2) 빌드는 되는데 outDir 구조가 바뀌거나 TS6059로 멈춘다: rootDir default 변경
3) 빌드는 되는데 런타임이 죽는다: module/target default drift로 emit이 바뀜

## 실패 1: moduleResolution=node10 deprecate가 “에러”가 되어 CI를 막는다
tsc 실행 시 대표적으로 이런 형태로 터집니다.

```text
error TS5107: Option 'moduleResolution=node10' is deprecated and will stop functioning in TypeScript 7.0.
Specify compilerOption '"ignoreDeprecations": "6.0"' to silence this error.
```

이 메시지 자체가 중요한 계약을 말해줍니다.

- TS 6.0은 7.0에서의 삭제를 전제로 “지금 고치라”는 압력을 줍니다.[^3]
- `ignoreDeprecations`로 숨길 수는 있지만, 공식 발표는 TS 7.0에서 deprecated 옵션을 지원하지 않는다고 못 박습니다. [Announcing TypeScript 6.0](https://devblogs.microsoft.com/typescript/announcing-typescript-6-0/)[^1]

여기서 흔히 하는 실수는 **ignoreDeprecations를 “마이그레이션 완료”로 착각하는 것**입니다. 실제로는 “다음 업그레이드를 더 비싸게 만드는 연기”에 가깝습니다.

### 해결의 첫 갈림길: 이 패키지는 누가 실행하는가
- 번들러가 실행한다(웹 앱, UI 라이브러리): `moduleResolution=bundler` 쪽으로 이동
- Node가 직접 실행한다(스크립트, 서버): `moduleResolution=nodenext`(또는 node16) 쪽으로 이동

이때 참고할 기준은 TS 문서가 직접 제공하는 설명입니다. bundler는 extension 강제를 하지 않는다는 점이 분기점이 됩니다. [TSConfig moduleResolution](https://www.typescriptlang.org/tsconfig/moduleResolution.html)[^4]

## 실패 2: rootDir 기본값 변경이 모노레포 boundary를 깨뜨린다
TS 6.0에서 `rootDir` 기본값은 “모든 입력 파일의 공통 경로를 추론”이 아니라, “tsconfig.json이 있는 디렉터리”로 고정됩니다. release notes에 명시돼 있습니다. [TypeScript 6.0 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html)[^2]

이 변화는 단일 패키지에서는 체감이 약할 수 있지만, 모노레포에서 다음 패턴이 있으면 바로 터집니다.

- app 패키지의 `include`가 다른 패키지의 소스를 직접 물고 있다
- 혹은 scripts 패키지가 다른 패키지의 TS 파일을 직접 참조해 실행 파일을 만든다

예를 들어 `packages/app/tsconfig.json`이 (나쁜 습관이지만 흔히) shared 소스를 직접 include하고 있었다고 가정합니다.

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "dist"
  },
  "include": ["src", "../shared/src"]
}
```

TS 6.0에서는 `rootDir`이 `packages/app`로 고정되면서, `../shared/src` 아래의 파일이 `rootDir` 밖이라고 판정됩니다. 그래서 이런 형태로 빌드가 멈춥니다.

```text
error TS6059: File '.../packages/shared/src/index.ts' is not under 'rootDir' '.../packages/app'.
'rootDir' is expected to contain all source files.
```

`rootDir` 옵션 문서도 rootDir이 outDir에 어떤 경로 구조로 emit되는지를 결정한다고 설명합니다. [TSConfig rootDir](https://www.typescriptlang.org/tsconfig/rootDir.html)[^5]

### rootDir 에러를 “rootDir만 키우면 된다”로 해결하면 더 나빠진다
겉보기 해결은 두 가지입니다.

- A: app의 `rootDir`을 `..`로 올려서 shared까지 포함
- B: shared를 project reference/패키지 dependency로 바꾸고, 소스를 직접 include하지 않기

A는 당장 TS6059를 없앨 수는 있지만, 다음 부작용이 생깁니다.

- app의 emit(outDir) 구조가 shared의 소스 트리까지 삼켜서 깨끗한 배포물이 나오지 않습니다.
- app 빌드가 shared의 구현을 직접 컴파일하기 시작하면서, 패키지 boundary가 무너집니다.
- declaration emit이 중복되거나 경로가 꼬입니다.

TS 6.0의 rootDir 변경은 “추론 비용을 줄이자”는 취지지만, 실무에서는 “경계를 명시하라”는 압력으로 작동합니다.[^2]

내가 권하는 방향은 B입니다. shared는 shared의 tsconfig로 빌드하고(app은 dist나 types만 소비), app은 app만 빌드합니다.

## 실패 3: target/module 기본값 변화가 emit을 바꾸고 런타임이 죽는다
TS 6.0에서 `module` 기본값이 `esnext`, `target` 기본값이 최신 ECMAScript(현재는 es2025)로 이동합니다. release notes가 이 기본값 변경을 직접 언급합니다.[^2]

이 변화가 빌드를 깨는 전형적인 경로는 Node 스크립트 패키지에서 나옵니다.

- 예전에는 우연히 CommonJS emit(혹은 변환)이 나와서 Node가 실행해줬다
- 이제는 기본값으로 ESM emit이 나오고
- 패키지의 `package.json`이 `type: commonjs`(혹은 생략)인 상태라서 Node가 ESM을 못 읽고 죽는다

### packages/scripts/package.json
```json
{
  "name": "@acme/scripts",
  "private": true,
  "type": "commonjs",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "run": "node dist/build-manifest.js"
  }
}
```

### packages/scripts/tsconfig.json (문제 버전: module/target 미명시)
```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "dist"
  },
  "include": ["src"]
}
```

### scripts 실행: build는 되는데 run에서 죽는 형태
```bash
pnpm -C packages/scripts run build
pnpm -C packages/scripts run run
```

런타임에서 이런 류의 에러가 납니다.

```text
SyntaxError: Cannot use import statement outside a module
```

여기서 중요한 건 “TypeScript가 에러를 준 게 아니라 런타임이 죽었다”는 점입니다. TS 6.0의 기본값 변화는 타입 시스템의 변화가 아니라 산출물 계약의 변화고, 그 계약은 결국 Node가 집행합니다.

이 문제는 `target`만의 문제는 아니고, `module`/`moduleResolution`/`package.json type`이 함께 얽혀 있습니다. 다만 `target`이 최신으로 떠버리면 팀 내부에서 “tsc output은 최신 JS를 전제로 한다”는 기대가 생기고, 그것이 CI runner의 Node 버전/테스트 환경과 어긋날 때 뒤늦게 폭발합니다.

## 해결 패턴: repo-level 기본값을 버리고, 패키지별 계약을 고정한다
TS 6.0 이후에는 “루트 tsconfig.base.json 하나로 전부 커버” 전략이 더 자주 실패합니다. 웹 번들 패키지와 Node 실행 패키지는 서로 다른 세계를 살기 때문입니다.

핵심은 다음 두 가지입니다.

1) base는 ‘공통 타입 체크 정책’만 담고
2) module/moduleResolution/target/rootDir/outDir은 패키지의 실행 환경에 맞게 고정한다

### 1) 루트 tsconfig.base.json: strict/품질 중심으로 정리
TS 6.0에서 strict default가 true로 바뀌었다면(명시적이지 않으면 흔들립니다), 차라리 base에서 명시하고 팀의 정책으로 승격시키는 편이 낫습니다. TS 7.0으로 갈 때도 예측 가능성이 올라갑니다.[^6]

```json
{
  "compilerOptions": {
    "strict": true,
    "skipLibCheck": true,

    "declaration": true,
    "declarationMap": true,

    "noUncheckedSideEffectImports": true
  }
}
```

`noUncheckedSideEffectImports`의 default 변경도 release notes에 포함된 변경 중 하나라서, base에서 의도를 고정해 두는 게 낫습니다.[^2]

### 2) 번들러 세계(앱/UI/shared): moduleResolution=bundler를 기본으로
`@acme/ui` 같은 패키지는 Node가 직접 실행하지 않고 bundler가 소비합니다. 이 경우 `moduleResolution=bundler`가 현실과 더 맞습니다.

그리고 TS 6.0부터는 `moduleResolution=bundler`와 `module=commonjs` 조합도 허용되어, “resolution만 먼저 옮기고 emit은 단계적으로”라는 전략이 가능해졌습니다.[^2]

다만 프론트엔드 번들링이라면 나는 `module=esnext` 또는 `module=preserve`로 가는 쪽을 선호합니다. 이유는 두 가지입니다.

- ESM 형태를 유지해야 tree-shaking과 sideEffects 전략이 깨끗해집니다.
- 라이브러리 패키지의 d.ts emit이 더 예측 가능해집니다(특히 `exports` 조건부 매핑을 쓰는 경우).

예:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "module": "esnext",
    "moduleResolution": "bundler",

    "target": "es2022",

    "rootDir": "src",
    "outDir": "dist",

    "composite": true
  },
  "include": ["src"]
}
```

여기서 `target`을 일부러 고정(`es2022`)하는 이유는, TS 6.0의 floating default(es2025)를 그대로 받아들이면 “언제 target이 바뀌는지”가 TypeScript 버전과 연동돼 버리기 때문입니다. floating default는 개인 프로젝트에는 편한데, 조직/모노레포에서는 재현성 측면에서 비용이 큽니다.[^2]

### 3) Node에서 실행되는 scripts: moduleResolution=nodenext + module=nodenext(or commonjs)로 분리
Node 실행 패키지는 `moduleResolution=nodenext`로 옮기는 것이 공식 권장 경로입니다.[^2]

여기서 선택지는 둘입니다.

- 스크립트도 ESM으로 간다: `module=nodenext`, `type=module`로 정렬
- 스크립트는 CJS 유지: `module=commonjs`, 다만 resolution은 현대 Node 규칙을 따르도록 설계

현실적으로 레거시 CI 툴/실행 환경이 많으면 CJS 유지가 이길 때가 있습니다. 대신 그 결정을 “명시”해야 TS 6.0 기본값 변화가 끼어들 여지가 줄어듭니다.

CJS 유지 예:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "module": "commonjs",
    "moduleResolution": "nodenext",

    "target": "es2022",

    "rootDir": "src",
    "outDir": "dist"
  },
  "include": ["src"]
}
```

여기서 `moduleResolution=nodenext`를 쓰면서 `module=commonjs`를 붙이는 게 어색해 보일 수 있는데, 이 구성은 “해석은 현대 Node의 패키지 경로 규칙으로 하되, 출력은 CJS로 한다”는 의도를 담습니다. 이게 맞는지 여부는 번들러가 없는 순수 Node 실행 코드에서 특히 중요합니다.

## 모노레포에서 moduleResolution 변경이 퍼져나가는 실제 경로
`moduleResolution`을 바꾸면, 결국 다음 질문으로 이어집니다.

- 이 패키지가 소비하는 의존성은 `exports`/`imports`를 어떻게 선언하는가
- 타입 선언(.d.ts)은 어떤 조건부 export를 타는가
- relative import에 extension을 요구하는가(또는 bundler가 대신 처리하는가)

TypeScript의 모듈 문서들은 node16/nodenext 계열이 Node의 ESM/CJS 규칙과 얽혀 있고, 그 규칙이 파일 단위 module kind 판정에도 영향을 준다고 설명합니다. [Modules: Theory](https://www.typescriptlang.org/docs/handbook/modules/theory.html)[^7]

이건 곧 “tsc가 어떤 파일을 ESM으로 볼지”가 달라진다는 뜻이고, 그 결과로 다음이 연쇄적으로 바뀝니다.

- `esModuleInterop`가 만들어내는 결과 해석
- default import의 허용/비허용
- declaration emit에서의 import specifier 형태

반대로 bundler 모드는 Node 런타임 규칙을 그대로 강제하지 않습니다. 공식 문서는 bundler 모드가 extension 강제를 하지 않는다고 명시합니다. [TSConfig moduleResolution](https://www.typescriptlang.org/tsconfig/moduleResolution.html)[^4]

즉 **moduleResolution 변경은 “타입이 잘 잡히는가”가 아니라 “이 패키지의 모듈 그래프를 누가 결정하는가”를 묻는 질문**입니다.

- Node가 결정한다면 nodenext로 가야 하고(그리고 extension/exports/imports 규칙에 맞춰 코드를 고쳐야 합니다)
- bundler가 결정한다면 bundler로 가되, Node 실행 경로(테스트/SSR/스크립트)와 분리해야 합니다

## target 기본값 변화가 위험해지는 지점: 컴파일이 아니라 소비 단계에서 깨진다
`target`이 최신 ES로 떠버리면, TS는 더 적게 변환하고 더 많은 최신 문법/내장 API 타입을 허용하는 쪽으로 기웁니다. TS 6.0 발표는 `target`의 기본값이 최신 stable ECMAScript(예: es2025)로 이동한다고 직접 말합니다.[^2]

여기서 실무에서 터지는 문제는 컴파일 에러가 아니라 “소비 단계” 문제입니다.

- 번들러/minifier가 예상한 syntax baseline과 어긋난다
- 테스트 런타임(Node 버전, jsdom 환경)이 기대보다 낮다
- polyfill 전략(core-js, runtime injection)이 ES2019 기준으로 깔려 있는데, emit이 그보다 높아진다

특히 모노레포에서는 “패키지마다 다른 target을 원래 암묵적으로 갖고 있었는데, TS 업그레이드가 그걸 한 값으로 밀어버리는” 형태가 자주 나옵니다. 그래서 나는 TS 6.0에서 `target` 기본값을 받아들이기보다, 패키지군별로 다음 중 하나로 고정하는 쪽을 추천합니다.

- 브라우저(evergreen) 번들: `target=es2022` 또는 팀의 browserlist 전략과 맞춘 값
- Node 20+ 런타임: `target=es2022` 정도로도 충분한 경우가 많음(최신으로 띄우지 않아도 됨)
- 라이브러리 배포: 소비자 환경을 생각해서 더 낮게 가져가거나, dual build를 명시

핵심은 TS 버전 업그레이드가 “target 상향”을 자동으로 동반하지 않도록 막는 것입니다.

## TS 7.0을 앞두고 TS 6.0에서 정리해야 하는 이유
TS 6.0 발표는 TS 6.0이 전환 릴리스이고, 7.0에서 deprecate된 옵션들이 사라질 것이라고 분명히 말합니다.[^1]

실제로 TS 7.0 발표는 TS 6.0과 side-by-side로 운영하기 위한 호환 패키지(`@typescript/typescript6`, `tsc6`) 같은 메커니즘까지 제공합니다. 즉 “한동안 섞어 쓸 수밖에 없는 과도기”가 공식적으로 예정돼 있습니다. [Announcing TypeScript 7.0](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/)[^8]

이 상황에서 TS 6.0의 설정/출력 계약을 정리하지 않으면, 다음 비용이 누적됩니다.

- `ignoreDeprecations`로 숨긴 설정이 TS 7에서 바로 장애로 터짐
- 모노레포 각 패키지의 module boundary가 흐린 상태로 TS 7(컴파일러/언어 서비스 교체)을 맞음
- 빌드가 깨질 때 디버깅 레이어가 많아짐(tsc 문제인지, bundler 문제인지, Node ESM 문제인지 분리가 안 됨)

나는 이걸 “런타임 퇴역 작업과 같은 종류의 정리”로 봅니다. OpenSSL 3.0 EOL 대응을 했을 때도 결국 계약을 문서화하고 경계를 분리하는 것이 비용을 줄였습니다. [OpenSSL 3.0 EOL 이후 런타임을 안전하게 퇴역시키는 운영 설계](https://daewooki.github.io/posts/retire-openssl-3-0-safely/)

## 도입 판단 기준: 어떤 조합을 표준으로 삼을지
프로젝트 전체를 하나의 정답으로 몰아가는 건 보통 실패합니다. 대신 패키지 유형으로 표준을 나누는 게 재현성이 좋았습니다.

### 웹 앱/번들러 소비 패키지(React 앱, UI lib)
- `moduleResolution=bundler`
- `module=esnext` 또는 `module=preserve`
- `target`은 팀 기준으로 고정(나는 es2022 정도를 자주 선택)
- `rootDir`/`outDir` 명시

### Node에서 실행되는 패키지(스크립트, 서버, CLI)
- `moduleResolution=nodenext`(또는 node16)
- `module`은 ESM으로 갈 거면 nodenext, 아니면 commonjs
- package.json의 `type`과 일치시키고, 실행 커맨드(node/tsx/ts-node/ts-jest 등)가 무엇인지 명확히 문서화

### monorepo 공통 원칙
- 다른 패키지의 `src`를 직접 include하지 않는다
- shared는 build artifact(dist/types)로 소비한다
- `rootDir`을 넓혀서 “한 패키지가 다른 패키지를 삼키는 빌드”를 만들지 않는다

이 원칙은 TS 6.0의 rootDir 기본값 변경이 던지는 방향성과도 일치합니다. 즉, 추론을 줄이고 boundary를 명시하는 쪽입니다.[^2]

## 정리
TS 6.0의 핵심은 타입 시스템의 새 기능이라기보다, `tsconfig.json`이 표현하는 빌드 계약을 현대 생태계(ESM, exports/imports, bundler 중심)로 끌고 가는 데 있습니다. `moduleResolution=node10` deprecate는 그 계약 전환을 강제하는 신호탄이고, `target`/`module`/`rootDir` 기본값 변화는 “암묵적 설정”을 더 이상 안전지대로 두지 않습니다. TS 6.0에서 패키지별 실행 환경을 분리하고, module resolution의 책임 소재(Node vs bundler)를 선언해 두면 TS 7.0의 컴파일러 교체는 생각보다 단순한 교체로 끝납니다.

## 참고 자료
- [Announcing TypeScript 6.0](https://devblogs.microsoft.com/typescript/announcing-typescript-6-0/)
- [TypeScript 6.0 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html)
- [TSConfig moduleResolution](https://www.typescriptlang.org/tsconfig/moduleResolution.html)
- [TSConfig rootDir](https://www.typescriptlang.org/tsconfig/rootDir.html)
- [Modules: Theory](https://www.typescriptlang.org/docs/handbook/modules/theory.html)
- [Progress on TypeScript 7 - December 2025](https://devblogs.microsoft.com/typescript/progress-on-typescript-7-december-2025/)
- [Announcing TypeScript 7.0](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/)
- [Deprecate, remove `--moduleResolution node10` (GitHub issue)](https://github.com/microsoft/typescript/issues/62200)
- [Assume `rootDir` is the current configuration directory (GitHub issue)](https://github.com/microsoft/TypeScript/issues/62194)
- [OpenSSL 3.0 EOL 이후 런타임을 안전하게 퇴역시키는 운영 설계](https://daewooki.github.io/posts/retire-openssl-3-0-safely/)

[^1]: <https://devblogs.microsoft.com/typescript/announcing-typescript-6-0/>
[^2]: <https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html>
[^3]: <https://github.com/microsoft/typescript/issues/62365>
[^4]: <https://www.typescriptlang.org/tsconfig/moduleResolution.html>
[^5]: <https://www.typescriptlang.org/tsconfig/rootDir.html>
[^6]: <https://devblogs.microsoft.com/typescript/progress-on-typescript-7-december-2025/>
[^7]: <https://www.typescriptlang.org/docs/handbook/modules/theory.html>
[^8]: <https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
