---
title: "SvelteKit 배포 장애 체크리스트: Node·prerender·Vercel 라우팅 계약"
description: "SvelteKit과 어댑터가 동시에 움직일 때 터지는 Node 버전·prerender 경로 escaping·Vercel 라우팅 불일치를 실전 점검합니다."
date: 2026-11-12 15:15:22 +0900
categories: ["Frontend", "SvelteKit"]
tags: ["sveltekit", "vercel", "adapter-vercel", "prerender", "nodejs", "deployment"]
render_with_liquid: false
---

## Nov 10 릴리스 묶음이 바꾼 것: 프레임워크보다 배포 산출물

2026-11-10 전후에 SvelteKit 관련 패키지가 한 번에 움직인 흔적은 릴리스 인덱스에서 바로 확인됩니다. releases.sh 인덱스는 2026-11-10에 SvelteKit 묶음 릴리스가 잡혔다고 정리하고 있습니다.[^1]

실제 GitHub 릴리스 페이지를 보면 2026-11-10에 `@sveltejs/kit@3.2.0`, `@sveltejs/adapter-vercel@7.0.3`, `@sveltejs/adapter-node@6.0.2` 같은 태그가 같은 타임스탬프(봇 릴리스)로 찍혀 있습니다. 특히 adapter-vercel은 이 날짜에 (1) Node 런타임 문자열 검증, (2) `paths.base`가 있을 때 prerendered page 서빙이라는 배포 레이어의 핵심을 건드렸습니다.[^2]

이런 “동시 릴리스”가 위험한 이유는 SvelteKit의 런타임 동작 자체보다, 어댑터가 만들어내는 **호스팅 플랫폼용 산출물**이 바뀌기 때문입니다. SvelteKit은 배포 전에 반드시 adapter를 선택해야 하고, adapter는 build 결과물을 입력으로 받아 배포 타깃에 맞는 파일/라우팅/함수 구성을 생성합니다.[^3]

프레임워크 코어는 같은데 배포가 깨지는 전형적인 패턴은 여기서 나옵니다.

- 같은 SvelteKit 코드가 로컬/Preview에서는 정상인데 Production에서만 404가 터진다.
- 어떤 경로는 캐시가 먹고 어떤 경로는 함수로 떨어져 cold start가 늘어난다.
- 롤백했는데도 동일한 증상이 지속된다(혹은 롤백이 실패한다).

이 글은 2026-11-10 묶음을 트리거로, “SvelteKit은 프레임워크 자체보다 어댑터/호스팅과 맞물릴 때 장애가 난다”는 관점에서 세 가지를 실전 점검 가이드로 정리합니다.

- Node 버전 정책
- prerender 산출물 경로(정확히는 라우팅 패턴) escaping
- Vercel 라우팅 패턴과 adapter contract 불일치

## adapter contract: SvelteKit이 아니라 플랫폼이 깨지는 순간

Vercel을 예로 들면, adapter-vercel은 Vercel Build Output API 스펙에 맞춰 `.vercel/output` 디렉터리를 생성합니다. Build Output API는 “파일 시스템 기반 스펙”이고, 라우팅 규칙/함수/정적 파일을 이 디렉터리 구조로 표현합니다.[^4]

여기서 contract는 대략 이런 계층으로 생깁니다.

1. SvelteKit 라우팅 모델(+page/+layout/+server)
2. prerender crawl/entries가 산출하는 “정적 페이지 목록”
3. adapter가 이를 Vercel routing table(`.vercel/output/config.json`)로 번역
4. Vercel이 그 routing table을 해석(정규식/우선순위/캐시/서비스 라우팅 포함)

Vercel Build Output의 `config.json`에서 `routes`는 `src`가 PCRE-compatible regular expression입니다. 즉, “경로 문자열”이 아니라 “정규식”입니다.[^5]

이 한 문장 때문에 장애 포인트가 생깁니다.

- prerender로 수집된 URL이 그대로 route pattern에 들어가면, URL에 포함된 `.` `+` `(` `)` `[` `]` 같은 메타문자가 정규식으로 해석됩니다.
- base path를 붙여 서비스 라우팅을 하는 경우(`/docs/*`), adapter가 base를 고려한 라우팅을 생성하지 않으면 정적 파일이 존재해도 request가 함수로 떨어지거나 404가 납니다.
- Node 런타임 버전은 “내 repo의 engines”, “CI의 Node”, “Vercel 프로젝트 설정”, “adapter의 runtime 옵션/검증”이 서로 다른 contract로 얽혀 있습니다.

이걸 “SvelteKit 버그”라고 부르면 대응이 늦어집니다. 실제로는 adapter contract가 깨진 겁니다.

## Node 버전 정책: Vercel Node 26 전환과 런타임 문자열 검증

### 2026-10-29: Vercel의 Node 26 기본 전환이 먼저 터졌다

2026-10-29 Vercel은 Node.js 26 LTS가 GA(Generally Available)이며, 새 프로젝트의 default가 Node 26이라고 공개했습니다. 또한 기존 프로젝트도 `engines.node` 범위가 26을 허용하면 다음 배포에서 자동 업그레이드가 될 수 있다고 설명합니다.[^6]

여기서 중요한 건 “자동 업그레이드” 문장입니다.

- `engines.node: ">=20"` 같은 넓은 범위를 썼던 팀은, 의도하지 않게 build/runtime가 Node 26으로 올라갈 수 있습니다.
- 로컬이 Node 24인데 Vercel이 Node 26이면, 같은 lockfile이어도 네이티브 addon, optional dependency, 번들러(특히 Rollup/Rolldown/Vite 계열) 주변에서 미묘한 차이가 나기 쉽습니다.

나는 Node 버전 정책 글을 따로 정리해 둔 적이 있는데(사내 런타임 정책 관점), 배포 장애 예방만 놓고 보면 결론은 간단합니다. Node major를 “자동 상승 가능” 상태로 두지 않는 게 기본값이어야 합니다.

- [Node 27 연 1회 메이저에 맞춘 사내 런타임 정책 재설계](https://daewooki.github.io/posts/nodejs-annual-major-enterprise-runtime-policy/)
- [GitHub Actions Node 20 제거 전에 런타임 계약 재정리와 마이그레이션 플랜](https://daewooki.github.io/posts/github-actions-node20-removal-runtime-contract-migration/)

### adapter-vercel이 건드린 건 “지원 버전”이 아니라 “런타임 문자열 검증”이다

2026-11-10 릴리스에서 `@sveltejs/adapter-vercel@7.0.3`는 “Node.js 26부터 모든 Node 버전을 받아들인다(odd 포함)”는 수정이 들어갔습니다.[^2]

이 문장은 얼핏 “Vercel이 odd Node를 지원하나?”로 읽힐 수 있는데, 장애 관점에서는 이렇게 해석하는 편이 안전합니다.

- adapter-vercel 내부에서 `runtime: 'nodejsXX.x'` 같은 문자열을 해석/검증하는 로직이 있고
- 그 로직이 특정 범위를 거부하면 build 결과가 달라지거나(혹은 build 자체가 실패하거나)
- 결과적으로 배포 산출물(contract)이 바뀝니다.

더 직접적인 사례는 2026-11-05의 `@sveltejs/adapter-vercel@6.3.5`입니다. 여기서도 Node 26 지원 및 “모든 Node 버전 수용”이 이미 패치로 들어갔습니다.[^2]

즉 “Nov 10 묶음”은 종종 이런 식으로 발생합니다.

- 2.x 라인(예: kit 2.70.x + adapter-vercel 6.3.x)에서 패치로 contract가 바뀌고
- 3.x 라인(예: kit 3.2.x + adapter-vercel 7.0.x)에서도 같은 방향의 변화가 재등장하며
- 팀은 Renovate/Dependabot이 올린 “묶음 PR”로 한 번에 올려버린다

이때 CI/호스팅 Node 정책이 준비돼 있지 않으면, 장애는 프레임워크가 아니라 배포 contract에서 터집니다.

### 점검 포인트: Node 버전은 4군데를 동시에 고정해야 한다

Vercel에서 SvelteKit을 운영할 때, Node 버전은 보통 다음 네 군데에 존재합니다.

1. repo의 `package.json` → `engines.node`
2. 로컬 개발환경 → `.nvmrc`/Volta/asdf 등
3. CI(GitHub Actions 등) → setup-node
4. Vercel 프로젝트 설정(또는 Vercel이 읽는 engines)

Vercel은 `engines.node`로 major를 선택할 수 있고, 프로젝트 설정과 `package.json`이 충돌할 때 `package.json`이 override될 수 있다고 설명합니다.[^7]

Vercel이 Node 26을 default로 바꾼 시점(2026-10-29) 이후에는 특히 다음이 자주 사고로 이어집니다.

- `engines.node`를 넓게 잡아뒀고(예: `>=20`)
- 로컬/CI는 여전히 Node 24를 쓰며
- Vercel만 Node 26으로 “조용히” 이동

그 상태에서 adapter-vercel/kit를 업그레이드하면, 원인 추적이 “패키지 업그레이드 때문인지, Node major 전환 때문인지” 갈라집니다. 이걸 방지하려면 업그레이드 PR에서 Node major도 함께 고정하고, Vercel 빌드 로그에서 `node -v`를 항상 남기는 편이 낫습니다.

## prerender 산출물 경로 escaping: Vercel routes가 정규식이라는 함정

### 왜 escaping이 배포 장애로 이어지나

Vercel의 `vercel.json`에서 `routes`는 PCRE-compatible regular expressions이고, “점 하나 찍히면 모든 문자를 매칭한다”는 정규식 규칙을 그대로 따릅니다. Vercel 문서도 `atom.xml`을 매칭하려면 `atom\.xml`로 이스케이프해야 한다고 예시를 제공합니다.[^8]

Build Output API의 `config.json`도 같은 규칙을 따릅니다. `routes[].src`는 정규식입니다.[^5]

따라서 adapter가 prerendered paths를 routing rule에 넣을 때 escaping을 빼먹으면, 다음 둘 중 하나가 됩니다.

- 기능적 장애: 특정 URL이 오매칭되어 다른 파일/함수로 라우팅됨 → 404, 잘못된 HTML/JSON, 이상한 캐시
- 보안 이슈: prerender crawl 중 수집된 링크가 정규식으로 해석되어 의도치 않은 rule을 “주입”

이건 추측이 아니라, SvelteKit 보안 권고로도 공개된 내용입니다. 2026-10-29에 게시된 advisory는 “prerender 단계에서 크롤된 링크가 이후 Vercel routing configuration에서 regex로 해석될 수 있다”고 설명합니다.[^9]

### 실제로 패치가 들어간 지점: adapter-vercel / adapter-static

2026-11-05 릴리스에서 `@sveltejs/adapter-vercel@6.3.5`와 `@sveltejs/adapter-static@3.0.11`에 “prerendered paths를 Vercel route patterns에 쓸 때 escape한다”는 패치가 들어갔습니다.[^2]

또한 advisory 관점에서는 `@sveltejs/adapter-vercel`은 `<= 7.0.1`이 영향을 받았고 `7.0.2`에서 패치되었다고 명시합니다.[^9]

즉 11월 초~중순에 kit/adapter를 올리는 팀이 실제로 밟을 수 있는 지뢰밭은 이런 식입니다.

- kit 3으로 올리며 adapter-vercel 7.0.0~7.0.1을 먼저 쓴 팀
- 이후 보안 패치(7.0.2)를 올렸는데, 같은 시기에 Node 26 전환이 겹친 팀
- 그리고 11/10에 7.0.3까지 올라오며 runtime 관련 수정과 `paths.base` 관련 수정까지 같이 들어온 팀[^2]

여기서 장애로 보이는 증상은 대부분 “프리렌더 페이지가 일부만 404” 혹은 “특정 slug에서만 이상한 캐시”로 나타납니다.

### 재현 가능한 시나리오: slug에 `.` `+` `(` `)`가 들어간 프리렌더

CMS/문서/릴리스 노트 페이지를 운영하면 slug에 점이 들어가는 건 흔합니다.

- `v3.2.0`
- `nodejs26.x`
- `kit@3.2.0`

이런 값이 prerender crawl 중 발견되면, adapter는 “이 경로는 정적 파일로 서빙하라”는 라우팅 규칙을 생성해야 합니다. 이때 dot 하나가 escape되지 않으면 정규식 의미로 바뀌어 오매칭을 만들 수 있습니다.

오매칭이 실제 장애로 이어지는 경로는 보통 두 가지입니다.

1) 정적 페이지가 함수로 떨어짐

- routing rule이 기대한 것과 다르게 매칭되어 static asset이 아닌 function으로 요청이 가고
- function은 해당 경로를 SSR로 처리하려다가 base/paths/route mapping에서 404를 낸다

2) 캐시가 잘못 붙음

- 오매칭된 rule이 “더 넓은 범위”를 잡아버리면
- 원래 SSR이어야 할 경로가 정적으로 서빙되거나, 반대로 정적이어야 할 경로가 함수로 서빙되며
- 동일 URL인데도 Preview/Prod에서 캐시 키가 달라져 롤백이 먹히지 않는 것처럼 보인다

SvelteKit 자체도 HTML/JSON을 구분하기 위해 `Vary: Accept`를 포함시키는 등 캐시 분리를 전제로 합니다. 라우팅이 어긋나면 이 설계 가정이 깨집니다.[^10]

## `paths.base`와 Vercel 라우팅: 정적 파일은 있는데 404가 나는 케이스

### 7.0.3의 핵심 수정: base path가 있는 프리렌더 페이지 서빙

`@sveltejs/adapter-vercel@7.0.3`에는 “`paths.base`가 설정된 경우 prerendered pages를 서빙한다”는 수정이 들어갔습니다.[^2]

이 패치는 기능 설명만 보면 단순하지만, 실제 장애는 여기서 많이 납니다.

- `paths.base`는 앱이 루트(`/`)가 아닌 서브패스(`/docs`)에 서빙될 때 필요한 설정입니다.
- Vercel은 프로젝트 단위로는 보통 루트에 앱을 붙이지만, monorepo/서비스 라우팅/리버스 프록시 구성을 하면 서브패스에 앱을 매달 수 있습니다.
- 이때 adapter가 생성하는 라우팅 테이블이 base를 반영하지 않으면, 빌드 산출물 디렉터리에 HTML이 있어도 요청은 그 파일로 가지 않습니다.

SvelteKit 설정에서 `paths.base`는 “루트-상대 경로이며 `/`로 시작하고 끝나면 안 된다”고 정의돼 있고, 링크를 만들 때 `$app/paths`의 `resolve()`를 쓰는 걸 권장합니다.[^11]

즉 앱 내부 링크가 base를 전제로 구성되는데, 플랫폼 라우팅이 base를 무시하면 404가 납니다. 이건 프론트엔드 라우팅 문제로 보이지만 실제로는 배포 라우팅 테이블 생성 문제입니다.

### Vercel에서 base path 운영이 특히 까다로운 이유

Vercel routing은 `vercel.json`의 `routes/rewrites/redirects` 같은 고수준 규칙과, Build Output API의 `config.json` 라우트가 합쳐져 최종 테이블을 구성합니다. Build Output 쪽은 정규식 기반이고, 규칙 순서가 의미를 가집니다.[^5]

이 조합에서 흔히 생기는 사고는 다음입니다.

- 외부에서 `/docs/:path*`를 특정 서비스로 rewrite한다.
- 서비스 내부에서 SvelteKit은 `paths.base = '/docs'`로 구성되어 있고 prerender 결과도 `/docs/...`를 전제로 생성된다.
- 그런데 adapter가 생성한 정적 서빙 규칙이 base를 포함하지 않거나, 포함했지만 우선순위가 밀려 rewrite에 먹힌다.
- 결과는 “정적 파일은 존재하지만 404” 또는 “SSR로 떨어져서 __data.json만 404” 같은 형태가 된다.

이걸 운영 중에 발견하면 대개 Vercel 측 라우팅을 먼저 의심하게 되는데, 7.0.3 릴리스 노트에 base path 관련 fix가 들어간 걸 보면, adapter 레벨의 contract였던 케이스가 맞습니다.[^2]

## 롤백이 실패하는 조건: 캐시 + 산출물 불변성 + Node 전환

배포 장애에서 체감상 가장 괴로운 건 “롤백을 했는데도 안 고쳐지는” 순간입니다. SvelteKit/Vercel 조합에서는 이게 몇 가지 조건에서 현실로 나타납니다.

### 1) Node major 전환이 롤백의 의미를 바꾼다

Vercel이 Node 26을 default로 만들었고, engines 범위가 허용하면 자동 업그레이드될 수 있다고 했습니다.[^6]

따라서 “코드/패키지 버전은 롤백했는데 Node는 롤백되지 않았다”는 상태가 가능합니다.

- 이전 배포는 Node 24에서 빌드/동작했고
- 현재 배포는 Node 26에서 빌드/동작하는데
- 롤백은 “소스 상태”만 되돌리고 “호스팅 런타임 선택”은 그대로 유지

이 경우 증상이 그대로 남을 수 있습니다.

### 2) 정적 asset 서빙이 “빌드 시점에 기록된 목록”을 따른다

SvelteKit v3 마이그레이션 문서에는 adapter-node 변화로 “static assets are served from a list recorded at build time; files added to the output directory afterwards are not served, and replaced ones keep their old size and ETag”라는 설명이 들어 있습니다.[^12]

이걸 장애 대응 관점으로 번역하면 이렇습니다.

- 배포 산출물 디렉터리에 파일을 급히 넣는 방식의 핫픽스는 기대대로 동작하지 않을 수 있습니다.
- 롤백도 결국 “그 시점의 산출물/목록”으로 되돌아가므로, 플랫폼 캐시/라우팅/ETag가 기대와 어긋나면 체감상 롤백이 실패한 것처럼 보일 수 있습니다.

### 3) prerender 기반 라우팅 오매칭은 캐시를 더럽힌다

prerendered paths escaping 이슈는 기능적 장애와 보안 이슈를 동시에 내포합니다. advisory는 “크롤 과정에서 수집된 링크가 regex로 해석될 수 있다”고 말합니다.[^9]

만약 오매칭된 rule이 특정 범위를 잡아 static/SSR 경계를 흔들면, 캐시 계층(브라우저/CDN/플랫폼 내부)의 키가 뒤섞여 장애가 장기화될 수 있습니다.

나는 이 문제를 “롤백 실패”로 보기보다는 “라우팅 테이블이 잘못 생성되어 배포 단위가 깨졌다”로 분류하는 편이 낫다고 봅니다.

## 실전 점검 가이드: 업그레이드 전후에 확인할 것

여기부터는 실제로 팀에서 바로 적용 가능한 형태로 정리합니다. Nov 10 묶음(kit 3.2.0 + adapter-vercel 7.0.3 전후)을 올리기 전/후로 체크하는 걸 전제로 합니다.

### 1) 업그레이드 계획을 ‘버전 매트릭스’로 적는다

SvelteKit은 adapter가 플랫폼 산출물을 만들기 때문에, 프레임워크 버전만 올리는 게 아니라 “조합”을 올리는 겁니다. 최소한 아래는 한 줄로 기록해야 합니다.

- SvelteKit: 예) `@sveltejs/kit@3.2.0`[^2]
- adapter-vercel: 예) `@sveltejs/adapter-vercel@7.0.3`[^2]
- Node build/runtime: 예) “Vercel Node 26” (전환 공지 확인)[^6]

여기서 “Node는 그냥 최신 LTS” 같은 문장으로 끝내면, 장애가 났을 때 원인 격리가 안 됩니다.

### 2) Node 버전 고정: engines/node - CI - Vercel을 동시에

다음 셋을 한 번에 고정합니다.

- `package.json`의 `engines.node`
- CI의 setup-node
- Vercel 프로젝트 설정(또는 engines를 신뢰하도록 정책화)

Vercel이 `engines.node`로 override 가능하다는 점을 명시하고 있으니, engines는 “넓게”가 아니라 “의도한 major”로 두는 편이 낫습니다.[^7]

### 3) prerender crawling을 ‘입력 데이터’로 취급한다

prerender는 “정적 파일 생성”만이 아니라 “라우팅 규칙 생성의 입력”입니다.

- 어디서 어떤 링크를 수집하는가
- slug/URL에 어떤 문자가 들어오는가
- base path가 붙는가

이 세 가지가 adapter output을 바꿉니다.

SvelteKit은 `prerender.crawl`, `prerender.entries`, 그리고 `handleInvalidUrl` 같은 훅을 제공합니다. 문서에 `handleInvalidUrl`은 “크롤링 중 파싱할 수 없는 URL을 만났을 때의 동작”을 정의한다고 되어 있습니다.[^11]

내 경험상 “장애가 날 만한 링크는 애초에 prerender 입력으로 들어오지 못하게” 막는 게 낫습니다.

- CMS에서 slug 제약(허용 문자 제한)
- Svelte 컴포넌트에서 `encodeURIComponent` 강제
- `handleInvalidUrl: 'warn'`로 CI에서 로그 감시

### 4) Vercel routing table을 빌드 결과물로 검증한다

Vercel Build Output API에서 `routes`는 정규식입니다.[^5]

이 말을 “문서를 읽고 이해했다”로 끝내지 말고, 실제 산출물 파일을 CI에서 검사하는 게 효과가 큽니다. 특히 escaping 이슈는 “산출물만 보면” 바로 드러납니다.

아래는 재현 가능한 형태의 예시 프로젝트 스니펫입니다. 핵심은 `prerender`로 점이 들어간 slug들을 만들고, build 후 `.vercel/output/config.json`을 검사하는 것입니다.

#### 예시: SvelteKit 3.2.0 + adapter-vercel 7.0.3에서 라우팅 출력 검사

`package.json`

```json
{
  "name": "sk-vercel-contract-check",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "check:vercel-output": "node scripts/check-vercel-output.mjs"
  },
  "engines": {
    "node": "26.x"
  },
  "devDependencies": {
    "@sveltejs/adapter-vercel": "7.0.3",
    "@sveltejs/kit": "3.2.0",
    "@sveltejs/vite-plugin-svelte": "^6.0.0",
    "svelte": "^5.0.0",
    "typescript": "^6.0.0",
    "vite": "^8.0.0"
  }
}
```

- `@sveltejs/kit@3.2.0`와 `@sveltejs/adapter-vercel@7.0.3`는 2026-11-10 릴리스 태그로 확인됩니다.[^2]

`svelte.config.js`

```js
import adapter from '@sveltejs/adapter-vercel';
import { vitePreprocess } from '@sveltejs/kit/vite';

const base = process.env.SK_BASE_PATH ?? '';

export default {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({
			// runtime을 여기서 강제하지 않는 편이 안전합니다.
			// Vercel이 Node 26을 default로 두는 시점부터는
			// 프로젝트 설정/engines와의 일관성이 더 중요해집니다.
			split: false
		}),
		paths: {
			base
		}
	}
};
```

`vite.config.ts`

```ts
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			prerender: {
				crawl: true,
				handleInvalidUrl: 'warn',
				handleHttpError: 'fail'
			}
		})
	]
});
```

- `handleInvalidUrl`/`handleHttpError` 같은 prerender 제어 옵션은 SvelteKit 문서에 정의돼 있습니다.[^11]

`src/lib/release-tags.json`

```json
[
  "v3.2.0",
  "nodejs26.x",
  "kit@3.2.0",
  "a(b)c+1"
]
```

`src/routes/releases/+page.server.ts`

```ts
import tags from '$lib/release-tags.json';

export const prerender = true;

export function load() {
	return {
		tags
	};
}
```

`src/routes/releases/+page.svelte`

```svelte
<script lang="ts">
	export let data: { tags: string[] };
</script>

<h1>Release tags</h1>

<ul>
	{#each data.tags as tag}
		<li>
			<a href={`/releases/${encodeURIComponent(tag)}`}>{tag}</a>
		</li>
	{/each}
</ul>
```

`src/routes/releases/[tag]/+page.server.ts`

```ts
import tags from '$lib/release-tags.json';
import { error } from '@sveltejs/kit';

export const prerender = true;

export function entries() {
	return tags.map((tag) => ({ tag }));
}

export function load({ params }) {
	if (!tags.includes(params.tag)) {
		throw error(404, 'unknown tag');
	}

	return {
		tag: params.tag
	};
}
```

`src/routes/releases/[tag]/+page.svelte`

```svelte
<script lang="ts">
	export let data: { tag: string };
</script>

<h1>{data.tag}</h1>
<p>This page is prerendered.</p>
```

`tests`가 아니라 “산출물 검사”를 위한 스크립트가 핵심입니다.

`scripts/check-vercel-output.mjs`

```js
import fs from 'node:fs';
import path from 'node:path';

const output = path.resolve('.vercel/output/config.json');

if (!fs.existsSync(output)) {
	console.error(`[check] missing ${output}`);
	process.exit(2);
}

const config = JSON.parse(fs.readFileSync(output, 'utf8'));
const routes = config.routes ?? [];

// PCRE literal escape(근사치).
// 목적은 "정적 경로가 정규식 메타문자 없이 literal로 들어갔는지"를 확인하는 것입니다.
const escapePcreLiteral = (s) =>
	s.replace(/[\\.^$|?*+()\[\]{}]/g, (m) => `\\${m}`);

const tags = JSON.parse(fs.readFileSync('src/lib/release-tags.json', 'utf8'));
const base = process.env.SK_BASE_PATH ?? '';

const expected = tags.map((t) => `${base}/releases/${encodeURIComponent(t)}`);

const haystack = routes
	.map((r) => (typeof r?.src === 'string' ? r.src : ''))
	.filter(Boolean)
	.join('\n');

let failed = false;

for (const p of expected) {
	const escaped = escapePcreLiteral(p);
	if (!haystack.includes(escaped)) {
		console.error(`[check] route pattern for prerendered path not found (or not escaped): ${p}`);
		console.error(`        expected to include: ${escaped}`);
		failed = true;
	}
}

if (failed) {
	process.exit(1);
}

console.log('[check] vercel output routes look consistent for prerendered paths');
```

실행 순서는 단순합니다.

```bash
corepack enable
pnpm install
pnpm run build
pnpm run check:vercel-output
```

이 스크립트는 “Vercel route가 실제로 정규식이며 escaping이 필요하다”는 사실을 빌드 산출물로 검증합니다. (Vercel 문서가 말하는 `atom\.xml` 같은 규칙이 그대로 적용됩니다.)[^8]

### 5) 업그레이드 직후 관측 포인트를 404가 아니라 ‘경계’로 잡는다

장애 징후는 보통 404로 보이지만, 원인은 “경계”에서 발생합니다.

- 정적 ↔ 함수(SSR) 경계
- base path 경계(`/` ↔ `/docs`)
- HTML ↔ data 요청 경계(SvelteKit은 Accept에 따라 처리 경로가 달라짐)[^10]

따라서 smoke test도 “페이지 몇 개 열어보기”보다 아래처럼 경계를 찌르는 편이 효과가 큽니다.

- prerendered page URL 3~5개(점/플러스/괄호 등 특수문자 포함)
- 동일 URL에 대해 `Accept: text/html`과 data fetch가 분리되는지 확인
- base path가 있는 경우 `/docs/release/...`처럼 prefix 포함 경로로만 테스트하지 말고, prefix 없는 경로(`/release/...`)로도 요청을 날려서 rewrite/route 우선순위가 뒤집히는지 확인

## 판단: Nov 10 묶음은 ‘코드 변경’이 아니라 ‘계약 변경’으로 봐야 한다

2026-11-10 전후 SvelteKit/adapter 묶음은 눈에 띄는 breaking change를 전면에 내세우지 않습니다. 그럼에도 배포 장애 위험이 큰 이유는, adapter가 플랫폼 산출물과 라우팅 규칙을 생성하는 방식이 바뀌기 때문입니다.[^3]

- Vercel이 Node 26을 default로 바꾸면서 런타임 선택이 조용히 바뀔 수 있는 상태가 되었고[^6]
- adapter-vercel은 Node runtime 문자열 검증/수용 범위를 수정했으며[^2]
- prerendered paths escaping은 단순 버그가 아니라 “정규식 기반 라우팅”이라는 근본 특성에서 나오는 장애/보안 포인트로 공식 advisory까지 나온 상태입니다.[^9]

그래서 이 시점의 점검은 프레임워크 기능을 공부하는 게 아니라, build output을 계약으로 보고 검증하는 쪽이 맞습니다.

## 참고 자료

- [Svelte 릴리스 인덱스(releases.sh) — 2026-11-10 전후 SvelteKit 릴리스 묶음](https://releases.sh/svelte)[^1]
- [Releasebot의 Svelte 릴리스 노트 피드](https://releasebot.io/updates/sveltejs)[^13]
- [SvelteKit GitHub Releases — kit 3.2.0 / adapter-vercel 7.0.3](https://github.com/sveltejs/kit/releases)[^2]
- [SvelteKit Docs — Adapters](https://svelte.dev/docs/kit/adapters)[^3]
- [SvelteKit Docs — `@sveltejs/kit/vite`의 prerender 옵션](https://svelte.dev/docs/kit/%40sveltejs-kit-vite)[^11]
- [SvelteKit security advisory — prerendered paths가 Vercel route regex로 해석되는 이슈](https://github.com/sveltejs/kit/security/advisories/GHSA-jf9x-2fg2-hx4w)[^9]
- [Vercel Docs — Build Output API](https://vercel.com/docs/build-output-api)[^4]
- [Vercel Docs — Build Output Configuration (`.vercel/output/config.json` routes)](https://vercel.com/docs/build-output-api/configuration)[^5]
- [Vercel Docs — `vercel.json` routes는 PCRE 정규식이며 escaping이 필요함](https://vercel.com/docs/project-configuration/vercel-json)[^8]
- [Vercel Changelog — Node.js 26 LTS GA 및 기본 전환(2026-10-29)](https://vercel.com/changelog/node-js-26-lts-is-now-generally-available-on-vercel)[^6]

[^1]: <https://releases.sh/svelte>
[^2]: <https://github.com/sveltejs/kit/releases>
[^3]: <https://svelte.dev/docs/kit/adapters>
[^4]: <https://vercel.com/docs/build-output-api>
[^5]: <https://vercel.com/docs/build-output-api/configuration>
[^6]: <https://vercel.com/changelog/node-js-26-lts-is-now-generally-available-on-vercel>
[^7]: <https://vercel.com/docs/functions/runtimes/node-js/node-js-versions>
[^8]: <https://vercel.com/docs/project-configuration/vercel-json>
[^9]: <https://github.com/sveltejs/kit/security/advisories/GHSA-jf9x-2fg2-hx4w>
[^10]: <https://svelte.dev/docs/kit/routing?source=post_page-----431ec920fd5d--------------------------------------->
[^11]: <https://svelte.dev/docs/kit/%40sveltejs-kit-vite>
[^12]: <https://svelte.dev/docs/kit/migrating-to-sveltekit-3>
[^13]: <https://releasebot.io/updates/sveltejs>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
