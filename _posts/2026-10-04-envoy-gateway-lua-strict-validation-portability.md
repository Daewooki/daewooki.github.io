---
title: "Envoy Gateway의 Strict Lua validation과 정책 코드 이식성"
description: "Envoy Gateway 1.9.2의 Strict Lua validation 강화로 레거시 Lua 정책이 깨지는 지점을 이식성 문제로 정리합니다."
date: 2026-10-04 10:56:42 +0900
categories: ["Networking", "Envoy Gateway"]
tags: ["envoy-gateway", "envoy", "lua", "gateway-api", "policy-as-code", "ci"]
render_with_liquid: false
---

## Strict validation이 깨뜨린 것은 Lua 코드가 아니라 배포 모델입니다

2026-09-28에 공개된 Envoy Gateway v1.9.2 릴리스 노트에는, 기본 모드인 **Strict** Lua validation에서 `getfenv/setfenv/newproxy/module` 글로벌을 사용하는 스크립트가 이제 실패한다는 breaking change가 명시돼 있습니다. 오늘(2026-10-04 KST) 기준으로는 이미 업그레이드가 진행되는 조직이 나올 시점이고, Lua 기반 필터/정책을 운영 중이라면 지금 검증하지 않으면 배포 파이프라인에서 처음으로 깨질 가능성이 큽니다.[^1]

이 이슈를 단순히 “Lua 문법/런타임이 바뀌었다”로 보면 대응이 좁아집니다. Envoy Gateway에서 Lua는 단발성 필터 스크립트가 아니라, 다음 성격을 동시에 갖습니다.

- 코드가 Kubernetes 리소스(EnvoyExtensionPolicy 등)로 배포됩니다.
- 코드는 데이터 플레인(Envoy)에서 실행되지만, 일부 검증은 컨트롤 플레인(Envoy Gateway controller)에서 선행됩니다.
- 즉 “정책 코드(policy-as-code)”처럼 버전업/검증/승인/배포가 필요합니다.

내 경우, 이런 종류의 문제를 해결할 때 핵심은 (1) 런타임 호환성만 보지 않고 (2) 컨트롤 플레인 검증기를 포함한 전체 공급망을 고정된 인터페이스로 정의하는 쪽이라고 봅니다. 예전에 AI Agent에서 Strict 스키마 강제가 프로덕션 안정성을 올리는 쪽으로 작동한다는 경험을 정리한 적이 있는데, 여기서도 구조가 같습니다. 단, 이번 건은 “모델 입력 강제”가 아니라 “정책 코드 인터페이스 강제”에 더 가깝습니다: [AI Agent “Tool Use + Function Calling” 구현의 정답: 스키마 강제(Strict)·루프 제어·추적(Tracing)으로 프로덕션까지](https://daewooki.github.io/posts/2026-2-ai-agent-tool-use-function-callin-2/)

## v1.9.2에서 실제로 무엇이 바뀌었나

Envoy Gateway v1.9.2 릴리스 노트의 문장은 짧지만 함의가 큽니다.

- `getfenv`, `setfenv`, `newproxy`, `module` 글로벌을 사용하는 Lua 스크립트가 **Strict** validation에서 실패합니다.
- Strict가 기본(default)입니다.
- 해결책으로는 (a) 스크립트를 해당 글로벌 없이 재작성하거나 (b) `EnvoyProxy.spec.lua.validationType`을 `InsecureSyntax` 또는 `Disabled`로 변경하라고 안내합니다.[^1]

여기서 중요한 포인트는 “Envoy 런타임에서 실행이 안 된다”가 아니라 “Envoy Gateway의 Strict validation 단계에서 리젝트된다”는 것입니다. 즉, 데이터 플레인까지 코드가 내려가기 전에 컨트롤 플레인이 막습니다.

이 breaking change는 동일 릴리스 노트의 Security updates 항목에도 반복되는데, 표현이 더 직접적입니다. Lua validation sandbox를 강화하면서 해당 글로벌을 차단했다고 돼 있습니다.[^1]

이 문장 구조 자체가, 이번 변경이 기능 변경이라기보다 “검증 샌드박스의 방어 범위를 넓힌 것”에 가깝다는 신호입니다.

## `getfenv/setfenv/newproxy/module`이 레거시 스크립트에서 나오는 이유

이번에 막힌 4개 글로벌은 대체로 Lua 5.1 계열 레거시 코드에서 다음 목적으로 자주 쓰입니다.

1) 환경(environment) 조작: `getfenv/setfenv`

Lua 5.1 매뉴얼에서 `getfenv`는 함수가 사용하는 environment를 얻고, `setfenv`는 함수 environment를 바꾸는 용도로 정의돼 있습니다. `f=0` 같은 특수 케이스도 언급됩니다.[^2]

실무에서 이게 나오는 패턴은 보통 두 가지입니다.

- (A) “가짜 sandbox” 구현: `_G` 접근을 막기 위해 제한된 테이블을 environment로 주입
- (B) 모듈 시스템/의존성 주입: 호출자 environment에 심볼을 주입하는 커스텀 로더

그런데 이런 패턴은 검증기 관점에서는 곧바로 우회 포인트가 됩니다. environment를 바꿀 수 있으면, 검증이 설정한 제한된 글로벌 테이블을 다시 더 넓은 테이블로 갈아끼우는 식의 우회가 가능해집니다. 

2) 구식 모듈 시스템: `module`

Lua 5.1에서 `module(name, ...)`은 모듈 테이블을 만들고, `package.loaded[name]`를 세팅하고, 더 나아가 “현재 함수의 environment”를 그 모듈 테이블로 바꾸는 동작까지 포함합니다. 결과적으로 `require`가 그 테이블을 반환하도록 만드는 흐름입니다.[^2]

문제는 이 방식이 글로벌을 많이 건드리고, environment 조작과 결합되는 경우가 많다는 점입니다.

3) `newproxy`

`newproxy`는 Lua 5.1/LuaJIT 계열에서 userdata proxy를 만들고 메타테이블을 붙이는 데 쓰이는 레거시 기능으로 알려져 있습니다. 정책 코드에서 흔하진 않지만, “finalizer 비슷한 동작”을 억지로 만들거나(특히 테이블에 `__gc`가 없던 시절) 리소스 정리 흉내를 내는 코드에서 나오기도 합니다.

4) 왜 5.2 이야기가 같이 나오나

Lua 5.2 매뉴얼의 incompatibility 섹션에서는 `module`이 deprecated라고 정리돼 있고, `setfenv/getfenv`는 환경 모델 변경으로 인해 removed라고 못 박습니다.[^3]

즉, 이번 breaking change는 Envoy Gateway가 Lua 5.2로 “업그레이드”한 문제가 아닙니다. Envoy는 LuaJIT(대체로 5.1 호환)를 사용한다고 문서에 명시하고 있고[^4], Envoy Gateway의 Strict validation은 또 다른 구현체 위에서 별도로 돌아갑니다.

내가 보기엔 이번 사건의 본질은 이것입니다.

- 레거시 Lua 기능을 활용한 스크립트는 “특정 Lua 런타임에 결박된 코드”입니다.
- Envoy Gateway의 Strict validation은 “배포 가능한 정책 코드”에 허용되는 하위 집합을 정의합니다.
- 그 하위 집합이 더 좁아졌고, 좁아진 이유는 보안과 멀티테넌시(혹은 namespace 경계) 때문입니다.

## Envoy Gateway Strict validation이 돌아가는 위치와 위협 모델

Envoy Gateway API 문서(Extension types)에는 Lua validation 모드에 대한 설명이 꽤 노골적으로 적혀 있습니다.

- Strict 모드는 EnvoyExtensionPolicy(EEP) 리소스의 Lua를 gateway controller에서 실행하여 검증합니다.
- controller는 여러 namespace의 EEP를 watch하기 때문에, 권한이 약한 사용자가 자기 namespace에 EEP를 만들어 “controller 프로세스에서 임의 Lua 실행”을 유발할 수 있다고 경고합니다.
- 그래서 안전장치가 있고, unsafe code는 validation 실패로 데이터 플레인으로 내려가지 못하게 한다고 합니다.[^5]

이 설명을 읽으면, Strict validation은 단순한 “syntax check”가 아니라 컨트롤 플레인 보호 메커니즘의 일부입니다. 그리고 이번 v1.9.2 변경(특정 글로벌 차단)은 그 보호 메커니즘을 강화한 것으로 해석하는 게 자연스럽습니다.

여기에 더해, Envoy Gateway의 Lua Extensions 문서는 데이터 플레인 관점의 위험도 같이 못 박습니다. Lua 스크립트는 Envoy proxy 프로세스 안에서 실행되고, 강한 sandbox가 없다고 경고합니다.[^6]

즉, 컨트롤 플레인(validator 실행 환경)과 데이터 플레인(Envoy 런타임) 양쪽 모두가 보안 경계입니다.

- Strict validation을 약하게 만들면: 컨트롤 플레인에서의 “검증 실행”은 줄어들 수 있지만(모드 구현에 따라 다름), 결과적으로 데이터 플레인으로 더 위험한 코드가 내려갈 수 있습니다.
- 반대로 Strict validation을 강하게 만들면: 배포 파이프라인에서 리젝트가 늘어날 수 있지만, 허용되는 정책 코드의 형태가 명확해지고 업그레이드 시 예측 가능성이 올라갑니다.

## Strict / InsecureSyntax / Disabled 모드의 의미와 선택 기준

EnvoyProxy 스펙에서 Lua validation 타입은 `Strict / InsecureSyntax / Disabled` 3가지 enum으로 정의돼 있고, 기본값이 Strict라고 명시돼 있습니다.[^7]

또한 같은 문서/코드 주석에는 각 모드의 의도가 비교적 명확히 적혀 있습니다.

- Strict: 표준 Envoy Lua stream handle API만 쓰는 스크립트에 권장. controller에서 스크립트를 실행하며 보안 샌드박스가 적용됨.
- InsecureSyntax: Lua syntax error만 체크. 외부 라이브러리 사용 시 유용할 수 있으나, runtime validation이 없고 보안 조치가 적용되지 않는다고 경고.
- Disabled: 모든 validation 비활성. syntax validation도 없고 보안 조치도 없다고 경고.[^5]

여기서 흔히 나오는 오해가 하나 있습니다.

- InsecureSyntax는 이름 때문에 “보안이 조금 약해짐” 정도로 받아들이기 쉽습니다.
- 실제 문서 뉘앙스는 “실행 기반 검증/샌드박스 자체를 포기한다”에 가깝습니다.[^5]

내가 권하는 의사결정 기준은 다음처럼 “조직의 신뢰 경계”로 나누는 겁니다.

### 1) Strict를 유지해야 하는 케이스

- EEP 같은 리소스를 여러 팀/여러 namespace에서 만들 수 있는 구조(멀티테넌트 클러스터)
- Gateway 팀이 모든 Lua 정책 코드를 코드리뷰/승인하지 못하는 구조
- Lua를 사실상 “확장 언어”로 열어두면 안 되는 조직

Strict를 유지하면 v1.9.2 같은 강화가 들어와도 대응은 “정책 코드 리팩터링”으로 수렴합니다. 즉, 장기적으로는 좋습니다.

### 2) InsecureSyntax가 합리적인 케이스

- Lua가 외부 라이브러리를 로드해야 하고(예: `require` 기반 모듈화), Strict validator가 그 라이브러리를 이해하지 못해 false negative를 내는 상황
- 정책 코드는 단일 팀에서만 관리되고, EEP 생성 권한이 엄격히 제한돼 있는 상황

여기서 중요한 건, InsecureSyntax는 단지 개발 편의 기능이 아니라 “검증기의 행위가 바뀐다”는 점입니다. 허용하더라도 RBAC/리소스 생성 경로를 같이 조여야 합니다.

### 3) Disabled는 정말 제한적으로

Disabled는 문서가 경고하는 그대로 “검증을 포기”합니다.[^5]

내 기준에서는 다음 중 하나라도 걸리면 Disabled는 빼는 편이 낫습니다.

- 운영 장애 시 누구든 빠르게 EEP를 고쳐 넣을 수 있는 문화(= 검증 없는 핫픽스가 침투할 가능성)
- proxy Pod에 Secret mount가 있는 구조
- Lua가 파일/환경변수 접근을 시도할 유인이 있는 구조(예: 인증 토큰 캐시, 커스텀 루트 인증서 로드, 디버깅 편의 코드)

## v1.9.2 breaking change를 “이식성”으로 재정의하기

이번에 막힌 글로벌들은 단순히 위험한 API라서 막힌 게 아니라, “정책 코드가 어떤 런타임/검증기에서도 동일한 의미를 갖는가”라는 문제를 건드립니다.

- Envoy 런타임은 LuaJIT 기반이고, 모듈 로딩을 위해 `package_paths/package_cpaths` 같은 설정을 제공합니다. Envoy 공식 문서도 `require`를 쓰려면 이 검색 경로를 추가하라고 설명합니다.[^8]
- 반면 Envoy Gateway Strict validation은 controller에서 스크립트를 실행해보며, 보안 샌드박스와 mock API로 동작을 제한합니다.[^5]

즉, 같은 Lua 코드라도 다음 세 환경이 서로 다릅니다.

1) 개발자가 로컬에서 돌리는 lua/luajit
2) Envoy proxy 프로세스 내부의 LuaJIT + Envoy stream handle API
3) Envoy Gateway controller 내부의 Strict validator(모의 API + 샌드박스)

이식성(portability) 문제는 “3번 환경에서의 정책 코드 인터페이스”를 기준으로 정의해야 합니다. 그렇지 않으면, 조직 내부에 이미 배포된 Lua 정책이 늘어날수록 업그레이드 때마다 예외 처리가 쌓입니다.

v1.9.2의 변화는 그 기준을 명확히 합니다.

- `getfenv/setfenv/module/newproxy` 같은 레거시 글로벌을 쓰는 순간, 그 코드는 Strict 모드의 정책 코드 인터페이스 밖으로 밀려납니다.[^1]

## 레거시 스크립트 이행 전략: 기능 치환보다 구조를 바꾸는 편이 빠릅니다

금지된 4개 글로벌은 단순 치환이 어렵습니다. 특히 `getfenv/setfenv/module`은 “코드를 로드하고 심볼을 주입하는 방식” 자체를 바꾸라고 요구하는 경우가 많습니다.

내가 실무에서 안전하게 옮길 때 쓰는 순서는 다음입니다.

### 1) 먼저 정책 코드의 경계를 쪼갭니다

Envoy Lua 정책은 대개 한 파일에 다음이 뒤섞여 있습니다.

- Envoy entrypoint (`envoy_on_request`, `envoy_on_response`)
- 라우트별 파라미터 처리
- 비즈니스 규칙(헤더 검증, 인증/인가, 테넌트 라우팅 등)
- 유틸 함수(문자열 파싱, base64, json, 캐시 등)

Strict validator 관점에서 안정적인 부분은 entrypoint와 stream handle API 상호작용입니다. 그래서 다음처럼 분리하는 쪽이 이행이 쉽습니다.

- `main.lua`: entrypoint만 두고, 나머지 정책 로직은 “순수 함수”로 분리
- `policy/*.lua`: Envoy API를 직접 호출하지 않거나, 호출하더라도 얇은 wrapper를 통해서만 호출

이렇게 해두면, 금지 글로벌을 쓰는 부분이 보통 “로더/모듈 시스템” 쪽으로 모여서 제거가 쉬워집니다.

### 2) `module()` 패턴은 return table로 바꿉니다

Lua 5.1의 `module()`은 environment를 바꾸는 동작이 섞여 있어서, Strict 모드가 싫어할 가능성이 높습니다. Lua 5.2에서 `module`이 deprecated로 정리된 것도 같은 맥락입니다.[^3]

대신 다음 패턴으로 정리합니다.

- 각 파일은 `return { ... }`로 모듈 테이블을 반환
- entrypoint는 `local policy = require("policy")`처럼 명시적으로 받아서 씀

Envoy는 `require`를 위해 `package_paths`를 설정할 수 있다고 문서에 적어놨습니다.[^8]

중요한 제약은, Envoy Gateway Strict validator(컨트롤 플레인)에서도 동일하게 모듈을 로드할 수 있느냐입니다. Strict 모드는 파일 접근/환경변수 접근을 제한하는 샌드박스를 갖고 있고, 허용 경로를 따로 설정할 수 있다는 설명이 스펙 주석에 있습니다.[^7]

즉, 모듈화를 하고 싶다면 다음 중 하나를 선택해야 합니다.

- (A) 모듈 로딩 자체를 포기하고, 한 파일로 번들링해서 inline_string으로 배포
- (B) StrictValidation의 allowedPaths 설계를 포함해 “정책 코드 배포 방식”을 정식으로 운영

조직 규모가 커질수록 (B)를 원하지만, 실제로는 (A)로 시작해서 코드 생성/번들링 파이프라인을 붙이는 편이 장애가 적었습니다.

### 3) `getfenv/setfenv`는 의존성 주입 방식으로 치환합니다

`setfenv`를 쓰는 코드의 목적은 대개 “글로벌에 심볼을 박아 넣어 편하게 쓰기” 또는 “제한된 환경에서 실행시키기”입니다.

Strict 모드 관점에서는 둘 다 우회 포인트가 되기 쉬운 형태입니다. 그래서 이행 시에는 편의성을 포기하고 인터페이스를 노골적으로 만드는 게 빠릅니다.

- 글로벌 함수/테이블에 기대지 말고, `local` 변수로 캡처
- 설정/상수는 `filter_context` 같은 공식 통로로 전달

Envoy Lua 필터는 route 레벨의 `filter_context`를 노출하고, 읽을 때는 wrapper 객체의 `get()`을 쓰라고 문서에 적어 둡니다.[^8]

즉, 레거시 코드에서 environment로 “주입하던 값”을 filter_context로 옮기면, 이식성 관점에서 정식 인터페이스로 갈아타는 셈입니다.

### 4) `newproxy`는 정책 코드에서 제거하는 쪽이 낫습니다

정책 코드는 요청/응답 흐름에서 빠르게 실행되고, 보통 상태를 오래 들고 있을 이유가 없습니다. finalizer 비슷한 패턴이 필요해지는 순간, 그 Lua는 필터를 넘어 “애플리케이션”이 됩니다.

성능/안정성 요구가 커지면 Envoy 문서가 말하는 것처럼 native C++ 필터나 다른 확장(예: Wasm/dynamic modules)로 넘어가는 게 장기적으로 맞는 경우가 많습니다. Lua는 고성능/복잡한 용도에는 적합하지 않다는 취지의 언급이 Envoy 문서에 반복됩니다.[^9]

## 배포 스펙 관점에서의 모드 전환: EnvoyProxy에 무엇을 적을 것인가

v1.9.2 릴리스 노트는 “`EnvoyProxy.spec.lua.validationType`을 바꿔라”라고 안내합니다.[^1]

스펙 정의를 보면 과거 필드(`luaValidation`)는 deprecated 처리돼 있고, 새 구조는 `lua.validationType` 형태로 옮겨가고 있습니다.[^7]

즉, 업그레이드 대응은 두 단계로 보는 편이 안전합니다.

1) 단기 핫픽스(필요한 조직만): validationType을 InsecureSyntax로 낮춰 배포를 막지 않기
2) 중기 정리: Strict로 되돌릴 수 있게 정책 코드 구조를 재정비

여기서 중요한 점 하나.

- Strict validator는 Envoy의 최신 stream handle API 변화에 늦을 수 있습니다.

실제로 외부 문서이긴 하지만, Envoy Gateway v1.8에서 Envoy 1.38의 `handle:stats()` API를 Strict validation이 받아들이지 못해 InsecureSyntax로 내려야 했다는 사례가 공개돼 있습니다.[^10]

이건 “Strict가 항상 더 낫다”가 아니라, Strict를 유지하되 업그레이드 시점에 (a) validator의 지원 범위와 (b) 실제 Envoy 런타임 API의 갭을 체크하는 절차가 필요하다는 뜻입니다.

## 재현 가능한 코드: Envoy 런타임에서는 되는데 Strict에서 깨지는 패턴을 분리합니다

여기서는 Envoy Gateway 리소스 매니페스트까지 완성형으로 재현하기보다(문서 페이지를 더 깊게 열어서 예제 YAML 필드 단위까지 확인해야 하는데, 이 글에서는 v1.9.2 breaking change의 구조를 설명하는 데 집중합니다), 다음 두 레벨을 분리합니다.

- (1) Envoy 런타임(LuaJIT)에서의 동작 테스트: 정책 코드의 기능 회귀를 잡는 테스트
- (2) Envoy Gateway Strict에서의 호환성 테스트: 금지 글로벌/샌드박스/지원 API 범위를 잡는 테스트

(1)을 잡아두면, (2)에서 깨졌을 때 “정책 의미가 바뀌었나”와 “배포 인터페이스가 바뀌었나”를 분리해서 판단할 수 있습니다.

### docker-compose로 Envoy + httpbin에서 정책 동작을 고정

아래 예제는 장난감이라기보다는, 현업에서 흔한 “요청 헤더 기반 정책”을 Lua로 구현한 형태입니다.

- `x-tenant-id`가 없으면 403
- 허용된 테넌트 목록에 없으면 403
- 통과하면 upstream으로 라우팅

#### 디렉터리 구조

```text
.
├── docker-compose.yaml
├── envoy.yaml
└── lua
    ├── main.lua
    └── policy.lua
```

#### docker-compose.yaml

```yaml
services:
  envoy:
    image: envoyproxy/envoy:latest
    ports:
      - "10000:10000"
    volumes:
      - ./envoy.yaml:/etc/envoy/envoy.yaml:ro
      - ./lua:/etc/envoy/lua:ro
    command: ["-c", "/etc/envoy/envoy.yaml", "--log-level", "info"]

  httpbin:
    image: kennethreitz/httpbin
    ports:
      - "8080:80"
```

#### envoy.yaml (Lua 필터 + package_paths)

Envoy 문서가 말하는 것처럼 `require`를 쓰려면 `package_paths`를 잡아야 합니다.[^8]

```yaml
static_resources:
  listeners:
  - name: listener_0
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 10000
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress_http
          route_config:
            name: local_route
            virtual_hosts:
            - name: httpbin
              domains: ["*"]
              routes:
              - match: { prefix: "/" }
                route: { cluster: httpbin }
          http_filters:
          - name: envoy.filters.http.lua
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
              package_paths:
                - /etc/envoy/lua/?.lua
              source_code:
                inline_string: |
                  require("main")
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

  clusters:
  - name: httpbin
    connect_timeout: 2s
    type: STRICT_DNS
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: httpbin
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: httpbin
                port_value: 80
```

#### lua/policy.lua (순수 정책 로직)

```lua
local M = {}

local ALLOWED = {
  ["tenant-a"] = true,
  ["tenant-b"] = true,
}

function M.authorize(headers)
  local tid = headers:get("x-tenant-id")
  if tid == nil or tid == "" then
    return false, "missing x-tenant-id"
  end
  if not ALLOWED[tid] then
    return false, "tenant not allowed"
  end
  return true, tid
end

return M
```

#### lua/main.lua (Envoy entrypoint)

Envoy Lua 필터는 `envoy_on_request` / `envoy_on_response` 같은 글로벌 함수 엔트리포인트를 찾습니다.[^11]

```lua
local policy = require("policy")

function envoy_on_request(handle)
  local headers = handle:headers()

  local ok, reason = policy.authorize(headers)
  if not ok then
    handle:respond(
      { [":status"] = "403", ["content-type"] = "text/plain" },
      "forbidden: " .. reason
    )
    return
  end

  -- 통과한 경우에는 추적용 헤더를 추가
  headers:add("x-policy", "lua-tenant-guard")
end
```

#### 실행 명령

```bash
docker compose up -d

# 실패 케이스
curl -i http://localhost:10000/get

# 성공 케이스
curl -i -H 'x-tenant-id: tenant-a' http://localhost:10000/get

docker compose logs -f envoy
```

#### 예상 출력(핵심만)

- 첫 번째 요청은 403이 나옵니다.

```text
HTTP/1.1 403 Forbidden
content-type: text/plain
...

forbidden: missing x-tenant-id
```

- 두 번째 요청은 200이 나오고, upstream(httpbin) 응답 헤더/바디가 내려옵니다. 추가된 `x-policy` 헤더는 upstream으로 전달됩니다.

이 테스트는 어디까지나 “정책 의미가 바뀌지 않았는가”를 고정하는 장치입니다.

### Strict에서 깨지는 레거시 패턴을 별도로 격리

v1.9.2에서 문제되는 건 레거시 글로벌 사용입니다. 예를 들어 아래 같은 코드는 (Lua 5.1 관점에서) 흔히 “현재 파일 환경을 가져와서 뭔가를 주입”하는데 쓰입니다.

```lua
-- legacy_env.lua (예: 기존 조직 코드에서 흔히 보던 패턴)
local env = getfenv(1)

function envoy_on_request(handle)
  -- ...
end
```

이 스크립트는 Envoy 런타임에서 동작할 수 있습니다(환경에 따라). 그러나 Envoy Gateway v1.9.2부터는 기본 Strict validation에서 `getfenv` 사용 자체가 실패 조건으로 박혀 있습니다.[^1]

이 차이를 “런타임 호환성”으로 보면 끝이 없습니다. 배포 가능한 정책 코드 인터페이스가 바뀐 거라서, 정책 코드가 그 경계 밖 기능을 쓰면 깨지는 게 정상입니다.

## 정적 검사와 CI: 금지 글로벌을 파이프라인에 고정합니다

v1.9.2 릴리스 노트가 금지 글로벌 4개를 구체적으로 적어준 건, 조직 입장에서는 오히려 기회입니다. 이 목록을 그대로 CI 룰로 가져오면, 다음 업그레이드에서 같은 류의 문제가 재발해도 “배포 직전”이 아니라 “PR 단계”에서 깨지게 만들 수 있습니다.

여기서 내가 선호하는 구성은 2단계입니다.

1) 빠른 정적 검사(cheap check): 금지 토큰 스캔
2) 느린 통합 검사(expensive check): Envoy 런타임 + (가능하면) Envoy Gateway controller 검증까지

이 글에서는 1)과 2)의 Envoy 런타임 테스트까지는 확실히 재현 가능한 형태로 적고, controller Strict validator까지 포함한 e2e는 조직 환경(Kind/실클러스터/권한모델)에 따라 달라져 별도 파이프라인으로 분리하는 쪽을 권합니다.

### (1) 금지 글로벌 스캔 스크립트

`module`은 일반 단어라 오탐이 날 수 있습니다. 그래도 v1.9.2 대응의 1차 방어선으로는 충분합니다. 실제 운영에서는 아래 스캔으로 후보를 잡고, 사람이 “정말 글로벌 `module()` 호출인지”만 확인하는 쪽이 비용이 낮았습니다.

#### scripts/check-eg-lua-portability.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# Envoy Gateway v1.9.2 Strict Lua validation에서 차단된 글로벌
# 출처: v1.9.2 release notes
BANNED=(
  "getfenv"
  "setfenv"
  "newproxy"
  "module"
)

fail=0

# repo 내 lua 파일을 대상으로 스캔
while IFS= read -r f; do
  for w in "${BANNED[@]}"; do
    if rg -n --fixed-strings "$w" "$f" >/dev/null; then
      echo "[FAIL] banned token '$w' found in $f"
      rg -n --fixed-strings "$w" "$f" || true
      fail=1
    fi
  done
done < <(git ls-files '*.lua')

exit $fail
```

#### 로컬 실행

```bash
chmod +x scripts/check-eg-lua-portability.sh
./scripts/check-eg-lua-portability.sh
```

이 스크립트가 막는 건 “정확한 의미의 Strict 호환성”이 아니라 “v1.9.2에서 바로 터지는 대표 패턴”입니다. 그래도 릴리스 노트가 직접 명시한 breaking change를 개발 단계로 당겨오는 효과가 있습니다.[^1]

### (2) Envoy 런타임 통합 테스트를 CI에 포함

위에서 만든 docker-compose 기반 테스트를 CI에 넣으면, 다음과 같은 종류의 리그레션을 잡습니다.

- Lua 리팩터링 과정에서 정책 의미(응답 코드, 헤더 추가)가 바뀐 경우
- `require`/모듈 구조 변경으로 런타임 로딩이 깨진 경우

Envoy의 Lua 필터가 `package_paths`로 모듈 경로를 확장할 수 있다는 점은 공식 문서에 명시돼 있으니, 이 경로를 CI에서 고정하면 됩니다.[^8]

CI에서는 다음 같은 형태가 현실적입니다.

```bash
docker compose up -d --wait

# 403이 나와야 하는 케이스
curl -sf -o /tmp/out -w "%{http_code}" http://localhost:10000/get | grep -q '^403$'

# 200이 나와야 하는 케이스
curl -sf -o /tmp/out -w "%{http_code}" -H 'x-tenant-id: tenant-a' http://localhost:10000/get | grep -q '^200$'

docker compose down -v
```

### (3) (선택) Strict validator와의 갭을 관리하는 방식

Envoy Gateway Strict 모드는 controller에서 스크립트를 실행해 검증한다고 문서에 적혀 있습니다.[^5]

이 구조 때문에 “Envoy 런타임에서는 되는데 Strict에서 막히는 케이스”는 앞으로도 반복됩니다. v1.9.2는 금지 글로벌이 명시적이라 쉬운 편이고, 앞으로는 더 미묘한 API/mock 차이로도 깨질 수 있습니다.

이 갭을 운영에서 줄이는 방법은 하나로 정리됩니다.

- 정책 코드가 의존하는 인터페이스를 Envoy stream handle API의 좁은 범위로 제한하고(문서가 권장하는 방향)[^5],
- 외부 라이브러리/메타프로그래밍이 필요해지는 순간 Lua에서 해결하려 하지 말고 다른 확장 포인트로 이관합니다.

## 도입 판단: Strict는 불편하지만 업그레이드 비용을 선불로 냅니다

Envoy Gateway v1.9.2의 breaking change는 단기적으로는 귀찮습니다. 특히 조직 내에 오래된 Lua 조각이 여기저기 박혀 있고, 그 조각들이 “Lua 5.1의 레거시 환경 조작”에 기대고 있었다면 더 그렇습니다.

하지만 이 이벤트를 잘 해석하면, 얻는 게 더 큽니다.

- Envoy Gateway는 Lua를 정책 코드처럼 취급하고, 컨트롤 플레인에서 실행 기반 검증을 하며, 그 샌드박스를 강화하는 방향으로 가고 있습니다.[^5]
- Lua 5.1 레거시 기능(`getfenv/setfenv/module`)은 언어 차원에서도 이미 구식으로 분류돼 있고(Lua 5.2에서 제거/비권장), 이식성을 해치는 기능입니다.[^3]

그래서 내 결론은 다음입니다.

- 모드를 InsecureSyntax/Disabled로 내리는 건 “운영 복구”로는 가능하지만, “정책 코드의 배포 모델”을 불안정하게 만들 수 있습니다.[^5]
- 레거시 스크립트를 Strict 친화적으로 옮기는 작업은, 결국 조직이 Lua를 계속 쓸 수 있는 기간을 늘립니다.
- Lua를 계속 쓸지, 더 강한 샌드박스/타입/배포 체계를 가진 다른 확장으로 옮길지는 조직마다 다르지만, v1.9.2의 메시지는 명확합니다. Lua를 코드로 배포하는 순간, “그냥 필터”가 아니라 정책 코드입니다.

## 참고 자료

- [Envoy Gateway v1.9.2 릴리스 노트](https://gateway.envoyproxy.io/news/releases/notes/v1.9.2/)
- [Envoy Gateway API: Extension types (LuaValidationConfig 포함)](https://gateway.envoyproxy.io/latest/api/extension_types/)
- [Envoy Gateway 문서: Lua Extensions](https://gateway.envoyproxy.io/v1.9/tasks/extensibility/lua/)
- [Envoy 문서: Lua HTTP filter (package_paths, stream handle API)](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/lua_filter)
- [Lua 5.1 Reference Manual (getfenv/setfenv/module 정의)](https://www.lua.org/manual/5.1/manual.html)
- [Lua 5.2 Reference Manual (5.1→5.2 incompatibilities: module deprecated, getfenv/setfenv removed)](https://lua.org/manual/5.2/manual.html)
- [Envoy Gateway v1.9.2 luavalidator 패키지(godoc)](https://pkg.go.dev/github.com/envoyproxy/gateway@v1.9.2/internal/gatewayapi/luavalidator)
- [Envoy Gateway 소스: EnvoyProxy 타입 정의(envoyproxy_types.go)](https://github.com/envoyproxy/gateway/blob/main/api/v1alpha1/envoyproxy_types.go)
- [AMD Enterprise AI 문서: EG Strict Lua validation과 API 갭 사례(handle:stats)](https://enterprise-ai.docs.amd.com/en/latest/aim-engine/admin/envoy-gateway-scale-from-zero.html)
- [Tetrate 문서: Envoy Gateway v1.9.2 릴리스 노트(동일 breaking change 재수록)](https://docs.tetrate.io/envoy-gateway/release-notes/v1.9.2)

[^1]: <https://gateway.envoyproxy.io/news/releases/notes/v1.9.2/>
[^2]: <https://www.lua.org/manual/5.1/manual.html>
[^3]: <https://lua.org/manual/5.2/manual.html>
[^4]: <https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/lua_filter.html?highlight=lua+filter>
[^5]: <https://gateway.envoyproxy.io/latest/api/extension_types/>
[^6]: <https://gateway.envoyproxy.io/docs/tasks/extensibility/lua/>
[^7]: <https://github.com/envoyproxy/gateway/blob/main/api/v1alpha1/envoyproxy_types.go>
[^8]: <https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/lua_filter>
[^9]: <https://www.envoyproxy.io/docs/envoy/v1.27.7/configuration/http/http_filters/lua_filter>
[^10]: <https://enterprise-ai.docs.amd.com/en/latest/aim-engine/admin/envoy-gateway-scale-from-zero.html>
[^11]: <https://www.envoyproxy.io/docs/envoy/v1.12.0/configuration/http/http_filters/lua_filter>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
