---
title: "Rust 1.100 채택 전략: 빌드·린트·포매팅 계약 고정"
description: "Rust 1.100으로 인한 Cargo 캐시·MSRV·Clippy·Rustfmt 변동을 흡수하려면, ‘버전 업’이 아니라 ‘팀 계약 고정’으로 접근해야 합니다."
date: 2026-11-26 16:31:38 +0900
categories: ["Languages", "Rust"]
tags: ["rust", "toolchain-pinning", "msrv", "monorepo", "ci-cache", "clippy-rustfmt"]
render_with_liquid: false
---

## Rust 1.100에서 팀이 실제로 흔들리는 지점

Rust 1.100.0은 2026-11-12에 릴리스됐고, 릴리스 공지에서 Cargo 쪽 변화가 유난히 실무 지점을 정확히 때립니다. `cargo::unused_dependencies`가 기본 `warn`으로 들어오고, `build-dir` 충돌을 줄이기 위한 내부 레이아웃 변경과 캐시 충돌 감소가 함께 들어왔습니다. 의도는 빌드 신뢰성/성능 개선인데, 모노레포·CI·캐시·사내 스크립트가 기대하던 불문율을 깨는 방식으로 도착합니다.[^1]

언어 레벨에서는 never type(`!`)가 안정화되면서 `Infallible`이 `!`의 type alias가 됐고, 그 과정에서 2015/2018/2021 edition까지 never type fallback이 `()`에서 `!`로 바뀌었습니다. “대부분 티 안 난다”가 맞는 경우가 많지만, 팀 차원에서는 “컴파일러가 이번 주에 추가로 unreachable을 잡아냈다” 같은 형태로 경고/린트 기준이 달라지고, 특히 `-D warnings`를 걸어 둔 CI는 실패할 수 있습니다.[^1]

도구 체인도 같이 움직입니다. rustfmt 1.11.0(같은 날짜)에 “Potential breaking changes”로 doc comment formatting 변화(특히 macro 내부) 같은 게 명시돼 있고, 이건 포매팅을 강제하는 저장소에서는 곧바로 PR 폭탄이 됩니다.[^2]

Clippy도 마찬가지입니다. 1.100 릴리스에 맞춰 새 lint가 추가되고 동작이 바뀌는데, 팀이 “Clippy는 그냥 습관적으로 돌리는 도구”로 취급하면 매 릴리스 때마다 CI가 흔들립니다. 결국 1.100은 기념 버전이라기보다, 그동안 미뤄 둔 **toolchain contract**를 다시 쓰라는 신호에 가깝습니다.[^3]

## 버전 업이 아니라 계약 고정으로 본다

내가 정의하는 계약은 대략 다음을 한 덩어리로 묶는 겁니다.

- `rustc`/`cargo` 버전
- `clippy`/`rustfmt` 버전(= 해당 toolchain에 포함된 컴포넌트)
- Cargo의 resolver/registry 정책(예: `global-min-publish-age`)
- Cargo lint 정책(예: `[lints.cargo] unused_dependencies`)
- Clippy의 MSRV 인지 설정(`msrv`)
- rustfmt의 style 관련 설정

핵심은 “사람이 기억하는 정책 문서”가 아니라, 리포지토리에 들어 있는 파일이 계약의 single source of truth가 되게 만드는 것입니다.

Rust는 이걸 위해 `rust-toolchain.toml`을 제공합니다. `channel`, `components`, `targets`, `profile`까지 포함할 수 있고, 프로젝트 디렉터리에 두면 rustup이 자동으로 해당 toolchain을 사용합니다.[^4]

이 방식이 특히 중요한 이유는, Rust의 릴리스 주기(6주) 자체가 빠른데다 “1.x니까 괜찮겠지”라고 넘기기 쉬운 기본값 변화가 누적되기 때문입니다. 나는 예전에는 “CI만 고정하면 되지 않나”에 가까웠는데, 실제로는 로컬/CI/프리커밋 훅이 서로 다른 버전을 쓰는 순간부터 계약이 무너집니다. systemd가 Rust 옵션을 도입한 이후에 빌드 계약이 어떻게 흔들리는지 따로 정리한 적이 있는데, 같은 형태의 문제가 언어/툴체인에서도 반복됩니다[^5].

## 채택 링: 실험 → 기본 → 강제

나는 Rust toolchain 업그레이드를 “한 번에 올리고 끝”으로 처리하지 않고, 채택 링을 세 단계로 나눕니다.

### 1) 실험(Experiment)

목표는 ‘빌드가 되는지’가 아니라, “계약을 바꿨을 때 어디가 터지는지”를 최대한 빨리 찾는 것입니다.

- 별도 CI 잡에서 `1.100.0`으로만 전체 워크스페이스를 `check/test/clippy/fmt`까지 수행
- Cargo의 새 warning(예: `cargo::unused_dependencies`)이 어느 정도 나오고, false positive가 어떤 패턴인지 확인
- rustfmt 결과가 바뀌는 파일의 유형을 분류
- `target`/`build-dir` 경로를 직접 읽는 스크립트(테스트 러너, 패키징 스크립트, 바이너리 수집 스크립트)가 있는지 점검

Rust 1.100에서 Cargo build intermediate artifacts 레이아웃이 바뀌었고, release notes에 “레이아웃은 stable interface가 아니며, JSON messages를 사용하라”가 정면으로 적혀 있습니다. 이건 실험 링에서 반드시 걸러야 합니다.[^6]

### 2) 기본(Default)

목표는 “새 계약으로 개발은 하되, 강제는 천천히”입니다.

- `rust-toolchain.toml`을 `1.100.0`으로 pin
- CI의 기본 job도 1.100으로 전환
- 단, lint/format은 `warn` 중심으로 두고, `deny`는 단계적으로 올림
- MSRV job은 별도로 유지(아래에서 설명)

Cargo의 unused dependencies는 1.100에서 기본 `warn`이며 `[lints.cargo]`로 제어됩니다. 이건 Default 링에서 `warn`으로 정착시키고, false positive나 워크스페이스 구조 이슈를 정리한 뒤에 강제로 올리는 쪽이 안전합니다.[^1]

### 3) 강제(Enforce)

목표는 “계약에서 벗어나면 merge가 불가능한 상태”입니다.

- `cargo fmt --check`를 필수화
- `cargo clippy ... -- -D warnings`를 필수화
- `[lints.cargo] unused_dependencies = "deny"` 같은 정책을 실제로 켬
- CI 캐시 키/경로 정책을 문서가 아니라 코드로 고정

강제 링은 toolchain pin 없이는 운영이 불가능합니다. Clippy와 rustfmt는 릴리스마다 변하고, 심지어 Rust 1.100의 rustfmt만 해도 doc comment formatting 변화가 “breaking 가능”으로 선언돼 있습니다.[^2]

## Cargo 1.100이 모노레포 캐시/경로에 주는 충격

Rust 1.100 릴리스 공지에서 “Reducing Cargo cache collisions”가 별도 섹션으로 들어간 게 인상적입니다. Cargo의 `build-dir`와 `target-dir` 관계, 그리고 서로 다른 build configuration이 만드는 충돌이 실무에서 충분히 아프다는 걸 인정한 셈입니다. 1.100에서는 build-configuration hash 적용을 더 일관되게 하도록 내부 구성을 바꿨고, 특히 git worktree를 공유할 때 문제가 더 커진다고 명시합니다.[^1]

여기서 내가 중요하게 보는 포인트는 두 가지입니다.

1) “캐시가 좋아진다”가 아니라 “캐시가 달라진다”

CI 캐시를 `target/` 기준으로 잡아두고, 추가로 intermediate artifacts를 따로 만지거나, `target/debug/build/...` 같은 경로를 가정하는 스크립트가 있으면 그대로 깨질 수 있습니다. Cargo book에서도 build-dir 레이아웃은 internal이며 바뀔 수 있다고 못 박고, 1.100에서 레이아웃이 바뀌었다는 note가 들어가 있습니다.[^7]

2) “경로를 읽지 말고 메시지를 읽어라”

release notes는 build-dir을 검사하는 도구는 Cargo JSON messages를 쓰라고 합니다. Cargo book에도 `--message-format=json`의 artifact 메시지 구조가 정리돼 있습니다. 나는 이걸 “내 스크립트가 target 디렉터리를 뒤지는 순간, 이미 부채가 생겼다”로 받아들입니다.[^6]

예를 들어, CI에서 “방금 빌드된 바이너리 경로를 찾아서 업로드”하려고 `target/debug/mybin`을 고정 문자열로 쓰는 건 아직은 버틸 수 있습니다. 하지만 proc-macro/build-script 산출물이나, 플랫폼 매트릭스, `--target` 빌드가 들어가면 경로 가정은 바로 한계가 옵니다. JSON 메시지에서 `compiler-artifact`의 `executable` 필드를 읽는 쪽이 장기적으로 안전합니다.[^8]

## Rust 1.100의 Cargo lint: unused dependencies를 팀 정책으로 만들기

Rust 1.100에서 Cargo가 unused dependencies를 직접 경고하기 시작합니다. rustc의 `unused_crate_dependencies`는 Cargo 워크스페이스 구조에서 false positive가 있었고, Cargo는 이를 별도의 lint(`cargo::unused_dependencies`)로 풀었습니다. 기본값은 `warn`이고, `[lints.cargo]`로 제어합니다.[^1]

이 기능을 “깔끔하게 정리하자”로만 보면 반쪽입니다. 모노레포에서는 다음 효과가 더 큽니다.

- 의도치 않은 dependency 추가(복사/붙여넣기, feature 실험 후 방치)가 즉시 표면화
- 빌드 시간이 줄고, 특히 CI cold build에서 비용이 감소
- 단, 워크스페이스의 타깃 선택에 따라 경고가 보였다가 안 보였다가 하는 구간이 존재

Cargo book은 이 lint가 특정 상황에서만 emit 되고, `[dev-dependencies]`는 현재 체크되지 않는다고 분명히 씁니다. 따라서 “CI에서만 보이는 경고”가 생길 수 있고, 이건 팀 내에서 ‘로컬에서는 괜찮은데 CI가 왜 깨지지?’로 번지기 쉽습니다. 나는 강제 링 전에 반드시 `--workspace --all-targets`를 표준 명령으로 박아 두는 편입니다.[^9]

## dependency cooldowns: 보안 정책이 빌드 재현성을 건드리는 방식

Rust 1.100은 Cargo의 `min-publish-age`(dependency cooldowns)를 안정화했습니다. `.cargo/config.toml`에 `global-min-publish-age = "3 days"` 같은 값을 주면, Cargo resolver가 “너무 최근에 publish된 버전”을 자동으로 무시합니다. 릴리스 공지에서는 새로 publish된 악성/문제 버전이 며칠 내에 잡히는 경우가 많다는 점을 배경으로 듭니다.[^1]

이걸 팀에서 채택할 때 흔히 생기는 오해가 있습니다.

- 오해: “이걸 켜면 supply chain 공격은 막힌다.”
- 현실: Cargo 쪽에서도 ‘완전한 방어는 아니다’라고 못 박습니다.

릴리스 공지에 “complete defense가 아니다”가 명시돼 있고, `cargo install`은 cooldown을 무시한다고도 씁니다. 즉, CI의 `cargo build`는 보호해도, 개발자 머신에서 `cargo install cargo-audit` 같은 걸로 설치하는 바이너리는 별개입니다.[^1]

운영 관점에서 더 중요한 건, cooldown이 “빌드 재현성”에도 영향을 준다는 점입니다.

- `Cargo.lock`가 없거나 새로 resolve하는 타이밍에만 영향이 큼
- “오늘 publish된 패치 버전”이 당장 필요할 때는 오히려 업데이트가 지연됨

Cargo config 문서에는 `registry.global-min-publish-age`와 함께, 이를 무시하는 환경변수(`CARGO_RESOLVER_INCOMPATIBLE_PUBLISH_AGE`)와 resolver 옵션이 정리돼 있습니다. 나는 이걸 “긴급 탈출 핸들”로 문서에만 적지 않고, 스크립트/CI job에 명시적으로 넣어둡니다.[^10]

## MSRV를 ‘정책’이 아니라 ‘빌드 요구사항’으로 만들기

MSRV는 대개 “우리는 1.7x까지 지원합니다” 같은 말로만 남고, 실제로는 `Cargo.toml` 어디에도 기록되지 않은 경우가 많습니다. Rust의 tooling은 `rust-version` 필드를 기준점으로 삼기 시작했고, 이 값은 (적어도 의도상) 도구들이 활용하도록 설계돼 있습니다.[^11]

Cargo book의 `rust-version` 문서가 좋은 점은, 단순히 “버전 적어라”가 아니라 사용 시나리오를 구체적으로 적어둔 것입니다.

- 지원하지 않는 toolchain에서 컴파일할 때, 더 직접적인 오류를 내서 기대를 명확히 함
- `cargo add`가 MSRV에 맞는 dependency 버전을 자동 선택할 수 있음
- resolver가 Rust version을 고려할 수 있음

그리고 “MSRV를 찾는 도구로 `cargo-msrv` 같은 서드파티 도구가 있다”는 언급도 들어가 있습니다.[^11]

여기서 Rust 1.100 채택과 연결되는 포인트는 두 가지입니다.

1) toolchain pin은 ‘개발용 최신’을 고정하고, MSRV는 ‘배포/라이브러리 지원 범위’를 고정한다

둘은 같은 숫자일 필요가 없습니다. 예를 들어 팀이 Rust 1.100으로 개발하더라도, 외부에 배포하는 library crate는 MSRV를 1.90으로 유지할 수 있습니다(대신 CI에서 1.90을 실제로 돌려야 합니다).

2) Clippy에도 MSRV를 알려야 한다

Clippy는 `msrv` 설정을 통해 “너희가 지원하는 Rust 버전에 없는 API로 바꾸라고 제안하지 않도록” 조절할 수 있습니다. Clippy 문서에 `msrv = "1.30.0"` 같은 형태로 설정하는 방법이 명시돼 있습니다. 나는 MSRV를 관리한다면 Clippy msrv도 같이 관리해야 한다고 봅니다.[^12]

## Rustfmt/Clippy를 계약에 넣을 때 생기는 비용

여기서부터는 팀 취향이 갈립니다. 하지만 “계약” 관점에서 보면 선택지는 두 개뿐입니다.

- rustfmt/Clippy를 CI에서 강제한다
- 강제하지 않는다(= 사람과 에디터 설정에 맡긴다)

중간 지대(“가끔 돌린다”)는 모노레포에서 가장 비용이 큽니다. 포매팅 PR이 뒤늦게 터지고, lint가 나중에 한꺼번에 쌓여서 빚이 됩니다.

Rust 1.100에 맞춰 rustfmt 1.11.0 changelog를 보면, doc comments in macros 쪽의 포매팅이 더 일관되게 바뀌었고, block doc-comment closer 포매팅 변화 같은 “Potential breaking changes”가 들어가 있습니다. 즉, 이전에 rustfmt를 강제하고 있었다면 1.100 채택 PR 자체가 대량 diff를 포함할 확률이 높습니다.[^2]

Clippy는 “새 lint 추가”가 일상이고, 1.100에서도 새 lint/개선이 다수 들어갔습니다. 여기서 toolchain pin이 없으면, 같은 커밋이 요일에 따라 통과했다가 실패하는 상황이 생깁니다.[^3]

나는 rustfmt/Clippy를 강제하는 편이지만, 대신 다음을 같이 합니다.

- lint 기준을 ‘점진 강화’로 운영(처음엔 warn, 이후 deny)
- MSRV가 있는 코드베이스는 Clippy msrv를 반드시 설정
- rustfmt은 `style_edition` 같은 옵션을 무작정 최신으로 올리지 않고, 팀이 diff를 감당할 때만 올림

## 실제 적용 예시: Rust 1.100.0으로 계약 고정하기

아래는 “서비스 바이너리 + CLI + 공용 라이브러리”가 있는 워크스페이스를 가정합니다. 장난감보다는 실무에서 흔한 모양(공용 crate를 여러 바이너리가 공유)으로 잡았습니다.

### 1) rust-toolchain.toml

리포지토리 루트에 둡니다.

```toml
# rust-toolchain.toml
[toolchain]
channel = "1.100.0"
profile = "minimal"
components = ["clippy", "rustfmt"]
```

`rust-toolchain.toml`에서 `components`를 지정할 수 있다는 건 rustup book에 문서화돼 있습니다. 이 파일이 있으면 개발자 머신에서 `cargo build`만 쳐도 해당 버전으로 스위치됩니다.[^4]

### 2) .cargo/config.toml: build-dir/target-dir와 cooldowns

Rust 1.100에서 build-dir 레이아웃이 바뀐 만큼, 나는 “workspace마다 intermediate artifacts를 더 강하게 분리”하는 쪽을 선호합니다. Cargo config는 `build.build-dir`에 템플릿 변수를 지원합니다.[^10]

```toml
# .cargo/config.toml
[build]
# 최종 산출물은 workspace의 target로 고정
# (캐시/아티팩트 업로드 경로가 한 곳으로 모이게)
target-dir = "{workspace-root}/target"

# intermediate artifacts는 CARGO_HOME 아래로 분리
# worktree / 다중 체크아웃 / 모노레포에서 충돌 확률을 낮추려는 의도
build-dir = "{cargo-cache-home}/build/{workspace-path-hash}"

[registry]
# dependency cooldowns (Rust 1.100에서 안정화)
# 조직 정책에 맞게 0 / 3 days / 7 days 같은 값을 선택
global-min-publish-age = "3 days"
```

`global-min-publish-age`는 Rust 1.100+에서 적용된다고 Cargo config 문서에 명시돼 있습니다.[^10]

여기서 트레이드오프가 있습니다.

- `build-dir`을 CARGO_HOME 쪽으로 빼면, CI 캐시 경로에 그 디렉터리를 포함해야 효과가 납니다.
- GitHub Actions 기준으로 `~/.cargo` 캐시를 잡지 않으면, 오히려 매번 새로 빌드합니다.

내 경우에는 “`target/` + `~/.cargo/`”를 같이 캐시하는 방식이 일반적이라서, `build-dir`을 분리해도 캐시 효율이 유지됩니다.

### 3) Cargo.toml: workspace + rust-version + Cargo lints

Rust 1.100에서 Cargo lints가 들어왔기 때문에, 나는 `unused_dependencies`를 최소한 `warn`으로는 명시합니다.

```toml
# Cargo.toml (workspace root)
[workspace]
resolver = "2"
members = [
  "crates/common",
  "crates/service",
  "crates/admin-cli",
]

[workspace.package]
edition = "2024"
# 이 워크스페이스가 내부 제품이라면 MSRV를 toolchain과 동일하게 가도 되고,
# 외부 배포용이면 더 낮게 잡고 별도 CI로 검증합니다.
rust-version = "1.100"

[workspace.lints.cargo]
# 1.100에서는 기본 warn이지만, 팀이 의도를 드러내려면 적어두는 편이 낫습니다.
unused_dependencies = "warn"
```

Cargo lints는 `[lints.cargo]`로 제어한다는 점이 1.100 릴리스 공지와 release notes에 함께 나옵니다.[^1]

### 4) clippy.toml: MSRV를 Clippy에도 알려준다

```toml
# clippy.toml
msrv = "1.100"
```

Clippy 설정에서 `msrv`를 지정할 수 있다는 건 공식 문서에 있습니다. MSRV가 더 낮다면 그 값으로 맞춥니다.[^12]

### 5) rustfmt.toml: 포매팅 계약을 명시한다

rustfmt이 바뀌는 건 피할 수 없지만, “우리는 어떤 옵션을 쓴다”는 고정할 수 있습니다.

```toml
# rustfmt.toml
edition = "2024"
# 팀이 hard_tabs 같은 옵션을 쓴다면
# 1.11.0에서 binary operator indentation이 바뀔 수 있다는 걸 릴리스 노트에서 확인하고
# 채택 PR에서 같이 정리합니다.
```

rustfmt 1.11.0에서 doc comment formatting 변화 같은 항목이 “Potential breaking changes”로 들어가 있으니, toolchain bump PR은 rustfmt diff를 포함할 가능성이 큽니다.[^2]

## Rust 1.100에서 CI 스크립트가 깨지는 전형적인 패턴

### build-dir을 뒤지는 스크립트

Rust 1.100 release notes는 intermediate build artifacts 디렉터리 레이아웃이 바뀌었고, build-dir 레이아웃은 stable interface가 아니라고 강조합니다. 따라서 다음과 같은 스크립트는 수명이 짧습니다.

- `target/debug/build/<crate>/out/...`에서 생성물을 직접 찾는다
- `target/debug/deps/*.rlib`를 glob으로 읽어 뭔가를 한다

이런 스크립트는 JSON message 기반으로 바꾸는 게 맞습니다.

Cargo book의 External tools 문서에 따르면 `--message-format=json`는 artifact 정보를 포함하며, line-delimited JSON으로 출력됩니다.[^8]

예시(바이너리 경로만 뽑는 간단한 jq 파이프라인):

```bash
cargo build --message-format=json \
  | jq -r 'select(.reason=="compiler-artifact") | .executable // empty'
```

이 방식은 build-dir이 어떻게 바뀌든 살아남습니다.

### `cargo fmt` 결과가 바뀌면, 포매팅 PR이 폭발한다

rustfmt 1.11.0은 macro 내부 doc comment 포매팅 일관화 같은 변화가 들어갑니다. 실무에서는 아래 형태가 터집니다.

- 기존에는 `cargo fmt`를 강제했지만, 개발자들이 포매팅을 미루다가 릴리스 업그레이드 때 한꺼번에 터짐
- 혹은 반대로, 원래 포매팅을 강제하지 않다가 업그레이드와 함께 강제하기 시작해 diff가 걷잡을 수 없음

나는 toolchain bump PR을 두 단계로 나누는 편입니다.

1) 1.100으로 bump + rustfmt/clippy 결과 반영(기계적 변경)
2) 실제 코드 변경/리팩터링 PR

같은 릴리스라도 “계약 변경”과 “의미 변경”을 섞으면 리뷰가 불가능해집니다.

## GitHub Actions 예시: toolchain pin + 캐시 + 채택 링 구현

GitHub Actions에서 toolchain pin을 구현하는 방법은 여러 가지가 있는데, 핵심은 “workflow에 버전을 하드코딩하지 말고 `rust-toolchain.toml`을 따라가게”입니다.

아래 예시는 dtolnay/rust-toolchain 액션을 사용하되, 원칙은 동일합니다(조직 표준이 다르면 액션만 바꿉니다).

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  test-1100:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Rust (pinned)
        uses: dtolnay/rust-toolchain@stable

      - name: Cache cargo
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}

      - name: Build
        run: cargo build --workspace --all-targets

      - name: Test
        run: cargo test --workspace

      - name: Fmt (check)
        run: cargo fmt --all --check

      - name: Clippy
        run: cargo clippy --workspace --all-targets --all-features -- -D warnings
```

여기서 중요한 점은 다음입니다.

- Cargo.lock 해시를 캐시 키로 사용하면, dependency graph 변화에 따라 캐시가 적절히 분리됩니다.
- Rust 1.100에서 build-dir 레이아웃이 바뀌어도 `target/` 캐시 자체는 여전히 의미가 있습니다(다만 내부 구성은 바뀜). build-dir 레이아웃 변경은 Cargo book의 build cache 문서에도 note로 들어가 있습니다.[^7]

채택 링을 CI로 구현하려면 job을 더 나눕니다.

- `experiment-1100`: non-blocking(필수 아님)으로 먼저 돌리고 결과를 축적
- `default-1100`: merge gate
- `enforce-1100`: lint/format deny를 켠 gate

## Rust 1.100 채택 시, MSRV job을 어떻게 같이 운영할지

외부 배포가 있는 워크스페이스(예: 공용 라이브러리)가 섞여 있다면, “개발 toolchain = 최신 pin”과 “지원 범위 = MSRV”는 분리해야 합니다.

Cargo의 `rust-version`은 “지원하는 Rust toolchain 버전”을 선언하는 필드이고, Cargo 자체가 이 값보다 낮은 toolchain에서의 빌드를 에러로 만들 수 있습니다. 즉, MSRV를 선언했다면 그 아래 버전에서 깨지는 게 정상입니다.[^11]

여기서 현실적인 운영 패턴은 이렇습니다.

- 루트 `rust-toolchain.toml`은 팀 개발 표준 버전(예: 1.100.0)
- 각 crate의 `package.rust-version`은 “외부에 약속한 MSRV”
- CI 매트릭스로 MSRV toolchain에서도 `cargo test`를 돌림

MSRV를 실제로 검증하지 않으면 `rust-version`은 선언적 문구로만 남습니다.

Clippy는 MSRV 설정을 통해 lint 제안을 조절할 수 있으니, MSRV job에서는 “새 문법/새 API로 바꾸라”는 제안이 나오지 않게 만드는 게 좋습니다.[^12]

## 1.100에서 추가로 체크하는 게 좋은 호환성 포인트

### never type fallback 변화가 숨어 있는 컴파일 실패

Rust Edition Guide는 “Rust 1.100부터 never type fallback 변화가 edition-specific이 아니게 됐다”고 명시합니다. 즉, 2018/2021 코드를 갖고 있어도 1.100으로 올리면 영향권입니다.[^13]

이 변화는 팀에서 다음 형태로 나타납니다.

- 특정 제네릭 코드에서 type inference가 달라져 컴파일 에러가 새로 발생
- unreachable 경고가 늘어남 → `-D warnings`에서 CI fail

따라서 “Rust 1.100으로 빌드만 해본다”가 아니라, 기존에 `-D warnings`가 있었다면 ‘경고까지 포함해’ 전체 워크스페이스를 통과시키는 게 안전합니다.[^1]

### cargo install의 잠금 기본값 변화

Rust 1.100 release notes에는 `cargo install`이 `.crate` tarball 안의 `Cargo.lock`를 기본으로 사용하게 바뀌어 `--locked`가 사실상 no-op이 됐다고 적혀 있습니다. 개발자 머신에서 tool 설치 방식(특히 내부 mirror/프록시 환경)과 충돌할 수 있는 변화입니다.[^6]

이건 “좋다/나쁘다”보다, 팀이 내부 문서/스크립트에서 `cargo install --locked`를 표준으로 잡아두고 있었다면 의미가 달라진다는 점이 중요합니다. 내부 도구 설치를 표준화하는 이야기는 예전에 AWS CLI 설치 계약을 정리하면서 비슷한 교훈을 얻었습니다[^14].

## 도입 판단: 1.100을 “기념 버전”으로 소비하지 않는 기준

내 결론은 단순합니다.

- Rust 1.100 채택의 본질은 새 기능을 쓰는 게 아니라, toolchain과 CI를 한 묶음의 계약으로 재정의하는 일입니다.
- 모노레포에서는 특히 Cargo build cache 레이아웃 변화, Cargo lints 도입, rustfmt 포매팅 변화가 합쳐져 “조용히” 비용을 만들 수 있습니다.
- 채택 링(실험→기본→강제)을 두고, 계약 파일(`rust-toolchain.toml`, `.cargo/config.toml`, `clippy.toml`, `rustfmt.toml`, `Cargo.toml`)을 리포지토리에 고정하면, 6주 릴리스 주기의 변동성을 팀이 감당 가능한 형태로 바꿀 수 있습니다.

Rust 1.98.1의 miscompile이나 1.99.0의 FFI 관련 변화처럼, 특정 릴리스가 코드 의미 자체를 건드리는 경우도 있습니다. 다만 1.100은 “의미 변화”보다 “팀 운영 변화(Cargo/도구/캐시/정책)”의 비중이 더 크고, 그래서 채택 전략이 더 중요해집니다[^15][^16].

## 참고 자료

- [Announcing Rust 1.100.0](https://blog.rust-lang.org/2026/11/12/Rust-1.100.0/)
- [Rust Release Notes: Version 1.100.0 (2026-11-12)](https://doc.rust-lang.org/stable/releases.html)
- [The rustup book: The toolchain file (rust-toolchain.toml)](https://rust-lang.github.io/rustup/overrides.html)
- [The Cargo Book: Build cache](https://doc.rust-lang.org/stable/cargo/reference/build-cache.html)
- [The Cargo Book: External tools (JSON messages)](https://doc.rust-lang.org/stable/cargo/reference/external-tools.html)
- [The Cargo Book: Lints](https://doc.rust-lang.org/stable/cargo/reference/lints.html)
- [The Cargo Book: Configuration (build.build-dir, global-min-publish-age)](https://doc.rust-lang.org/cargo/reference/config.html)
- [The Cargo Book: Rust Version (rust-version)](https://doc.rust-lang.org/cargo/reference/rust-version.html)
- [Clippy Documentation: Configuration (msrv)](https://doc.rust-lang.org/clippy/configuration.html)
- [rustfmt CHANGELOG 1.11.0 (2026-11-12)](https://github.com/rust-lang/rustfmt/blob/main/CHANGELOG.md)
- [rust-clippy CHANGELOG: Rust 1.100](https://rust.googlesource.com/rust-clippy/+/refs/heads/main/CHANGELOG.md)
- [The Rust Edition Guide: Never type fallback change](https://doc.rust-lang.org/beta/edition-guide/rust-2024/never-type-fallback.html)

[^1]: <https://blog.rust-lang.org/2026/11/12/Rust-1.100.0/>
[^2]: <https://github.com/rust-lang/rustfmt/blob/main/CHANGELOG.md>
[^3]: <https://rust.googlesource.com/rust-clippy/%2B/refs/heads/main/CHANGELOG.md>
[^4]: <https://rust-lang.github.io/rustup/overrides.html>
[^5]: <https://daewooki.github.io/posts/systemd-rust-auto-build-contract/>
[^6]: <https://doc.rust-lang.org/stable/releases.html>
[^7]: <https://doc.rust-lang.org/stable/cargo/reference/build-cache.html>
[^8]: <https://doc.rust-lang.org/stable/cargo/reference/external-tools.html>
[^9]: <https://doc.rust-lang.org/cargo/reference/lints.html>
[^10]: <https://doc.rust-lang.org/cargo/reference/config.html>
[^11]: <https://doc.rust-lang.org/cargo/reference/rust-version.html>
[^12]: <https://doc.rust-lang.org/clippy/configuration.html>
[^13]: <https://doc.rust-lang.org/beta/edition-guide/rust-2024/never-type-fallback.html>
[^14]: <https://daewooki.github.io/posts/standardize-aws-toolchain-installs/>
[^15]: <https://daewooki.github.io/posts/rust-1981-trait-object-vtable-bug/>
[^16]: <https://daewooki.github.io/posts/rust-ffi-variadics-raw-layout/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
