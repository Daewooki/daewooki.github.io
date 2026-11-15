---
title: "systemd Rust 옵션 이후의 빌드 계약: -Drust=auto가 흔드는 지점"
description: "systemd의 -Drust=auto는 Rust 도입 논쟁이 아니라, 배포판·CI의 빌드 입력과 아티팩트를 분기시키는 계약 문제입니다."
date: 2026-11-15 11:12:58 +0900
categories: ["Systems", "Systemd"]
tags: ["systemd", "meson", "rust", "packaging", "reproducible-builds", "ci"]
render_with_liquid: false
---

## PR #44324가 바꾼 것은 언어가 아니라 빌드의 분기점입니다

systemd는 2026-10-24에 PR [rust: support programs written in Rust #44324](https://github.com/systemd/systemd/pull/44324)를 main 브랜치에 머지했습니다.[^1]  이 PR은 흔히 말하는 “Rust로 재작성”과는 성격이 다릅니다. 시스템 전체를 Rust로 옮기는 계획이 아니라, **새로운 leaf program(다른 구성요소가 의존하지 않는 프로그램)** 을 Rust로 작성할 수 있도록 build-system 인프라를 추가하는 작업입니다. PR 본문에서도 libsystemd-shared/libsystemd, NSS/PAM 모듈 등 핵심은 C로 남고, Rust로 작성한 프로그램은 기존 C 프로그램과 동일하게 libsystemd-shared를 동적 링크하는 쪽으로 제한합니다.[^1]

이 선택이 기술적으로 흥미로운 지점은 언어 자체보다 다음 세 가지입니다.

1) Rust toolchain의 존재 여부에 따라 빌드가 갈라지는 방식

* Rust 지원은 Meson 옵션 `-Drust=`로 켜고 끄며, 기본값은 `auto`입니다.[^1]  즉 “빌드 머신에 rustc/bindgen이 있으면 켜지고, 없으면 꺼지는” 분기점을 시스템이 공식적으로 도입한 셈입니다.

2) Cargo를 쓰지 않는 Meson 통합

* PR은 Rust 표준 라이브러리(std)를 포함하지 않게 하고, 외부 crate를 쓰지 않는 정책을 강조합니다. “Rust 코드는 core만 사용한다”, “std는 없고, alloc crate도 쓰지 않는다”, “외부 crate는 없다”가 PR 설명에 직접 등장합니다.[^1]  build가 Cargo 중심으로 흘러가지 않도록 의도적으로 막은 구조입니다.

3) 배포판/CI에서의 “옵션 고정” 문제

* PR은 이미 다운스트림에서 깨지는 사례를 구체적으로 언급합니다. Arch와 openSUSE OBS 빌드가 `--auto-features=enabled`로 systemd를 빌드하면서 rustc/bindgen을 BuildRequires에 넣지 않아 실패한다고 콕 집어 말합니다.[^1]  이건 단순한 의존성 추가가 아니라, “빌드 계약이 옵션 자동감지에 의해 뒤집힐 수 있다”는 신호입니다.

systemd 263에 포함될 가능성이 높다는 얘기는 Phoronix 기사에서도 확인됩니다. [systemd Merges Support For Rust Programs](https://www.phoronix.com/news/systemd-Merges-Rust-Programs)[^2]  아직 “안정 릴리스에 Rust가 필수가 됐다”는 단계는 아니지만, base image/CI/배포판 패키징 입장에서는 지금부터 계약을 고정하지 않으면 6개월 뒤에 디버깅 비용이 커지는 유형의 변화입니다. (이 감각은 예전에 썼던 [zlib 1.4의 ‘작은’ 변경이 다운스트림 빌드·패키징을 깨는 방식](https://daewooki.github.io/posts/zlib-14-small-breaking-changes/)과 결이 같습니다.)

## -Drust=auto의 의미: “자동”은 선택이 아니라 입력값입니다

`-Drust`가 Meson `feature` 옵션으로 들어왔다는 점이 핵심입니다. `feature`는 `enabled/disabled/auto` 3상태고, 기본값은 `auto`입니다. Meson 자체 구현에서도 feature 옵션의 기본값이 `auto`임이 드러납니다.[^3]  systemd의 `meson_options.txt`에서도 `rust`는 feature로 정의되어 있고 설명은 “Rust로 작성된 프로그램 지원(rustc/bindgen 필요)”입니다.[^4]

문제는 많은 패키징 환경이 “auto를 그대로 auto로 두지 않는다”는 점입니다.

Meson에는 전역 옵션 `auto_features`가 있고 기본값은 `auto`입니다. 그런데 packager가 `auto_features=enabled`를 주면 프로젝트의 모든 `auto` feature가 사실상 “가능하면 켠다”로 바뀝니다. Meson 문서도 이 동작을 packager의 통제 수단으로 명시합니다.[^5]  NixOS 쪽에서도 이 설정이 “auto-detected feature를 전부 켜버리는” 변화로 다뤄졌습니다.[^6]

systemd PR #44324가 바로 여기에서 다운스트림 파열을 만들었습니다.

* systemd의 `-Drust=auto` 자체는 “toolchain이 있으면 켠다”입니다.[^1]
* 많은 배포판/사내 빌드 레시피는 Meson에 `--auto-features=enabled`를 기본으로 주거나, 유사한 정책을 갖습니다.
* 그러면 rustc/bindgen이 build root에 우연히 존재하는 순간(직접 의존성으로 넣었든, 다른 패키지 때문에 들어왔든), systemd의 rust feature가 켜지면서 빌드 입력과 출력이 바뀝니다.

이 상황에서 “빌드가 깨졌다”는 증상은 두 가지로 갈립니다.

* 하드 실패: `-Drust=enabled`를 주는데 toolchain이 없어서 configure 단계에서 죽음. PR에서도 `-Drust=enabled`는 “없으면 크게 실패(fails loudly)”라고 못 박습니다.[^1]
* 소프트 실패(더 나쁨): `-Drust=auto`인데 빌드 머신의 상태가 바뀌면서 어떤 CI에서는 Rust가 켜지고, 어떤 CI에서는 꺼짐. 이때는 “빌드는 성공하지만 아티팩트가 달라지는” 쪽으로 진행합니다.

내 경험상 운영/패키징에서 진짜 비용을 만드는 건 전자가 아니라 후자입니다. 전자는 바로 고치면 끝나지만, 후자는 “언제부터 달라졌는지”와 “왜 여기서만 달라졌는지”를 추적하는 데 시간이 들어갑니다. systemd 같은 핵심 컴포넌트는 그 비용이 조직 전체로 전파됩니다. ([systemd 262 업그레이드 실전 가이드](https://daewooki.github.io/posts/systemd-262-upgrade-ops-checklist/)에서 옵션 변화가 운영 계약을 깨는 패턴을 다뤘는데, 이번 건 그 패턴이 build-system 레벨로 내려온 사례입니다.)

## “도구가 있으면 켠다”가 CI를 흔드는 방식: 입력이 숨어 있기 때문입니다

`-Drust=auto`가 흔드는 건 단순히 “Rust 코드가 빌드된다/안 된다”가 아닙니다. build graph가 바뀌고, 그 결과 설치되는 파일/테스트/문서가 달라질 수 있습니다. PR에서도 `HAVE_RUST`가 unit, man page, test에서 Rust 프로그램의 빌드 여부를 조건으로 삼는다고 설명합니다.[^1]

즉 systemd는 이제 다음을 갖게 됩니다.

* 같은 systemd 소스 트리
* 같은 Meson 옵션 세트라고 생각했는데
* build root의 상태(rustc/bindgen/meson 버전)에 따라
* 결과물이 달라질 수 있음

PR은 또 “meson >= 1.4.0이 rust module의 bindgen() 통합에 필요하다”고 말합니다.[^1]  그리고 “트리는 기존 meson floor를 유지하고, 오래된 meson에서는 -Drust=auto가 자동으로 꺼진다”고도 합니다.[^1]  이건 packager에게 좋은 소식처럼 들리지만, CI 관점에서는 “환경에 따라 silent downgrade가 발생한다”는 의미이기도 합니다.

### 배포판 빌드가 실제로 바뀌는 징후

Arch 쪽에서는 systemd 패키지 PKGBUILD에 rust와 rust-bindgen이 makedepends로 들어간 흔적이 메일링 아카이브에 남아 있습니다.[^7]  이 변화는 PR #44324의 설명(Arch 빌드가 실패한다)과도 결이 맞습니다.[^1]

이게 의미하는 바는 간단합니다.

* “systemd는 C 프로젝트”라는 전제가 깨졌고
* 빌드 계약 관점에서 rustc/bindgen/clang(libclang)이 systemd의 간접 입력이 됐습니다.

사내 베이스 이미지가 “빌드용 이미지”와 “런타임 이미지”가 분리돼 있더라도, CI가 multi-stage build를 쓰거나 builder image를 재활용하면 어느 날 rustc가 들어오고(또는 빠지고) systemd 결과가 달라질 수 있습니다.

## Cargo 미사용이 주는 이득과, 그 때문에 더 중요해지는 재현성/TCB 포인트

systemd가 Cargo를 사용하지 않는 선택은 다운스트림 입장에서 장단이 분명합니다.

### 장점: 네트워크/공급망 측면에서의 압력 감소

대부분의 배포판 빌드는 네트워크 접근을 금지하거나 극도로 제한합니다. Fedora는 빌드 시스템이 인터넷 접근이 없는 chroot에서 동작하며, 빌드 중 외부에서 소스를 다운로드하면 안 된다는 가이드를 명시합니다.[^8]  Debian도 Rust 생태계를 패키징할 때 crate를 소스 패키지로 쪼개고 오프라인으로 빌드하도록 정책화하고 있습니다.[^9]

이 상황에서 Cargo 기반 빌드는 결국 두 갈래로 수렴합니다.

* crate vendoring(예: `cargo vendor`)을 통한 완전 오프라인 빌드
* 배포판이 crate를 패키징해 제공하고 Cargo가 로컬 registry를 보게 하는 방식

둘 다 구축 비용이 있습니다. systemd는 “외부 crate 없음”과 “Cargo 없음”으로 아예 그 비용을 회피했습니다. PR에서도 외부 crate를 쓰지 않는다고 못 박습니다.[^1]

### 단점: build-time code generation과 toolchain 편차가 TCB가 됩니다

Cargo를 안 쓰면 “의존성 해결”은 단순해집니다. 하지만 systemd가 Rust를 받아들이는 방식은 다음 구성요소를 빌드 시점 신뢰경계 안으로 끌어들입니다.

1) bindgen을 통한 바인딩 생성

PR은 “libsystemd-shared 바인딩을 빌드 시점에 bindgen으로 생성한다”고 설명합니다.[^1]  그리고 더 중요한 문장이 뒤에 붙습니다.

* rustc 최소 버전 1.85, bindgen 최소 버전 0.71.1
* bindgen 0.72.0은 “컴파일되지 않는 코드를 생성하기 때문에 거부”[^1]

즉 Rust 코드 자체의 안정성뿐 아니라 “바인딩 생성기의 버전/버그”가 빌드 성공과 결과물에 영향을 줍니다. 이건 C 세계의 `bison/flex` 버전 차이로 재현성이 흔들리는 것과 유사한 계열입니다.

2) bindgen의 런타임 libclang 의존

PR은 “bindgen은 런타임에 libclang을 로드하므로, 바이너리가 존재한다고 바인딩 생성이 되는 게 아니다. configure 시점에 한 번 실행해 검증한다”는 취지로 적습니다.[^1]  build root에 clang 패키지가 들어왔는지, libclang ABI가 맞는지, cross 환경인지까지 영향을 받습니다.

3) Meson rust module 자체의 계약

Meson의 Rust module 문서를 보면 `rust.bindgen()`은 bindgen 바이너리 버전 제약을 걸 수 있고, bindgen이 0.65 이상 필요하다고 설명합니다.[^10]  systemd는 여기에 더해 0.71.1이라는 별도 floor를 요구합니다.[^1]  이런 floor는 패키저가 문서로 고정하지 않으면 “어느 배포판에서는 켜지고, 어느 배포판에서는 꺼지는” 분기를 더 늘립니다.

4) Meson과 Rust의 rpath 관련 함정

PR의 커밋 설명에는 Rust 프로그램의 runpath(rpath) 문제를 피하기 위해 별도 스크립트로 runpath 문자열을 rewrite한다고 나옵니다. Meson이 Rust 프로그램에 rustc sysroot의 라이브러리 디렉터리를 runpath에 남기는데, systemd는 Rust dylib을 쓰지 않으므로 불필요하며, Debian multiarch처럼 pkglibdir가 길면 install이 실패할 수 있다고 설명합니다.[^1]  그리고 이 문제는 실제로 Meson 쪽에서도 이슈가 됐고, Christian Brauner가 Meson에 “Rust dylib을 링크할 때만 sysroot를 rpath에 넣어라”는 취지의 패치를 올린 커밋이 있습니다.[^11]

이건 packaging/TCB 관점에서 꽤 중요한 신호입니다.

* “Cargo를 안 쓴다”는 것만으로 공급망 위험이 0이 되지 않습니다.
* 오히려 Meson/rustc/bindgen/libclang 조합이 systemd 빌드의 새로운 신뢰 기반이 됩니다.
* 특히 rpath 같은 건 보안 리뷰에서 자주 걸립니다. 빌드 도구 경로가 런타임 runpath에 남는 건 일반적으로 원치 않습니다.

### cross-compilation이 당장 어려운 이유도 여기서 나옵니다

PR은 “cross-compilation은 아직 지원하지 않는다. bindgen이 target을 알아야 한다”고 말합니다.[^1]  systemd를 cross로 빌드하는 배포판(임베디드, appliance, 내부 OS)은 여기서 바로 충돌합니다. 이 경우 `-Drust=auto`는 “어떤 환경에서만 켜지고 다른 환경에선 꺼지는” 불안정 요인이 될 가능성이 큽니다.

## 배포판·사내 패키징에서의 핵심 결론: -Drust=auto는 빌드 계약으로 쓰면 안 됩니다

`auto`는 개발자 로컬 빌드에서는 편합니다. 하지만 다운스트림 패키징에서는 “빌드 입력이 환경에 의해 결정되는 옵션”을 남겨두는 순간, 재현성과 검증 가능성을 잃습니다.

PR #44324 자체도 이 긴장을 알고 있습니다.

* `-Drust=enabled`는 toolchain이 안 보이면 실패해서 “조용히 기능이 빠지는” 상황을 피한다고 설명합니다.[^1]
* mkosi 이미지에서 toolchain이 충분히 최신인 배포판은 `-Drust=enabled`로 빌드해서 “quietly dropping Rust”를 막는다고 밝힙니다.[^1]

즉 upstream도 “auto가 조용히 꺼지는 것”이 CI에 좋지 않다는 걸 알고 있고, 최소한 자신들의 CI에서는 enabled로 고정해 감시합니다.

다운스트림(배포판, 사내 베이스 이미지)은 여기서 한 발 더 나가야 합니다.

### 내가 권하는(그리고 실제로 유지보수하기 쉬운) 계약 형태

1) 기본 아티팩트는 `-Drust=disabled`로 고정

* 이유: 지금 단계에서는 Rust 프로그램이 leaf이기 때문에 런타임 기능이 갑자기 사라져도 “핵심 systemd 동작”이 무너지는 건 아닙니다. 반대로 빌드 입력이 늘어나는 비용은 지금 당장 발생합니다.
* PR이 직접 말하듯, Arch/openSUSE처럼 `--auto-features=enabled` 정책이 있으면 rustc/bindgen이 없을 때 빌드가 깨집니다.[^1]  빌드가 깨지는 대신 `-Drust=disabled`로 고정하면 계약이 단순해집니다.

2) “Rust-enabled build”는 별도 아티팩트로 생산하고 테스트에서만 의미를 갖게 하기

여기서 “별도 아티팩트”라는 말은 꼭 사용자가 설치할 패키지를 두 개로 쪼개라는 뜻이 아닙니다. systemd는 충돌 없이 동시에 설치하기 어렵습니다. 대신 다음이 실전적입니다.

* 동일 소스/동일 패치셋
* 서로 다른 build profile
  * profile A: `-Drust=disabled`
  * profile B: `-Drust=enabled`
* CI에서는 둘 다 빌드
* 릴리스/배포는 A만(또는 배포판 정책에 따라 B만)

이렇게 하면 “Rust 프로그램이 깨져서 전체 systemd 업데이트가 막히는” 상황을 피하면서도, Rust 쪽 regression을 조기에 발견할 수 있습니다.

3) 기능 매트릭스를 문서화하고, 패키지 메타데이터에 박아 넣기

내가 운영에서 중요하게 보는 건 “의도가 아티팩트에 남아 있느냐”입니다.

* 빌드 로그에 `meson configure` 결과를 저장
* 바이너리에 build-id/패키지 릴리스 노트에 `-Drust` 상태를 기록
* SBOM이나 provenance(가능하면 SLSA 쪽)에도 “Rust-enabled build” 여부를 속성으로 남김

이건 systemd 안정 릴리스 정책을 다룬 글[^12]에서 말했던 것과 같은 철학인데, 이번에는 “버전”이 아니라 “빌드 입력”을 계약의 1급 시민으로 올리는 작업입니다.

## 실제로 CI에서 깨지는 지점: rustc가 아니라 bindgen/meson/auto_features입니다

PR을 읽고 나면 많은 사람이 “Rust 컴파일러만 넣으면 되겠네”라고 생각합니다. 그런데 실전은 다음 순서로 터집니다.

1) `auto_features=enabled` 환경에서 `-Drust=auto`가 사실상 `enabled`처럼 동작

Meson 문서 그대로, `auto_features=enabled`는 `auto` feature를 override합니다.[^5]  즉 `-Drust=auto`를 줬다고 해서 “있으면 켜고 없으면 꺼”가 아니라, “가능하면 켜”로 강해집니다.

2) bindgen이 없거나, bindgen은 있는데 libclang이 없어서 configure에서 실패

PR은 bindgen이 런타임에 libclang을 로드한다고 말합니다.[^1]  그래서 `bindgen` 바이너리만 덩그러니 설치된 상태(또는 PATH에만 잡힌 상태)로는 부족합니다.

3) Meson 버전

systemd는 meson >= 1.4.0을 요구한다고 PR 본문에 명시합니다.[^1]  또한 README에는 “Rust 프로그램을 빌드하려면 meson >= 1.8.0 필요”라고 적혀 있습니다.[^13]  PR 쪽에서는 1.4.0을 언급하고, README는 1.8.0을 언급하는데(둘이 왜 다른지는 실제 코드 경로에 따라 달라질 수 있습니다), 다운스트림 입장에서는 이런 차이 자체가 “문서가 곧 계약”이라는 점을 다시 확인시키는 신호입니다.

4) rpath/runpath

systemd는 Meson이 Rust 타깃에 rustc sysroot 경로를 runpath로 남기는 문제를 회피하기 위해 `fix-rust-rpath.py` 같은 도구를 추가합니다.[^1]  이건 패키징에서 흔히 하는 “불필요한 RPATH 제거” 단계와 충돌할 수 있습니다. RPM의 brp 스크립트, Debian의 dh_strip_nondeterminism류와 같이 build 후처리를 강하게 거는 환경에서는 예상치 못한 차이가 나올 수 있습니다.

## 재현 가능한 빌드 계약을 위한 스크립트: Rust-enabled/disabled를 둘 다 확인하기

아래는 “배포는 Rust-disabled로 고정하되, CI에서 Rust-enabled도 함께 빌드해 깨짐을 조기에 확인한다”는 계약을 구현한 예시입니다.

전제는 단순합니다.

* Meson/Ninja/컴파일러 등 기본 build deps는 이미 준비돼 있음
* Rust-enabled 빌드를 하려면 `rustc >= 1.85`, `bindgen >= 0.71.1`이 있어야 함 (systemd README에도 동일하게 적혀 있습니다)[^13]

### build-contract.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

SYSTEMD_GIT=https://github.com/systemd/systemd.git
# PR #44324가 main에 merge된 날짜(2026-10-24) 직후의 main을 잡는 게 목적이라면
# 실제 CI에서는 배포판이 채택한 tag/commit을 여기에 고정해야 합니다.
# 아래는 PR 페이지에 표시되는 merge commit 예시입니다.
SYSTEMD_COMMIT=0211129

rm -rf ./systemd-src

git clone --filter=blob:none --no-checkout "$SYSTEMD_GIT" systemd-src
cd systemd-src

git checkout "$SYSTEMD_COMMIT"

echo "== toolchain versions =="
meson --version
ninja --version || true
cc --version | head -n 1 || true

if command -v rustc >/dev/null; then
  rustc --version
else
  echo "rustc: not found"
fi

if command -v bindgen >/dev/null; then
  bindgen --version
else
  echo "bindgen: not found"
fi

echo

echo "== configure: Rust disabled (shipping artifact) =="
rm -rf build-norust
meson setup build-norust -Drust=disabled
meson configure build-norust | sed -n '/^  rust /p'

echo "== build: Rust disabled =="
ninja -C build-norust

echo

echo "== configure: Rust enabled (CI validation artifact) =="
rm -rf build-rust
meson setup build-rust -Drust=enabled
meson configure build-rust | sed -n '/^  rust /p'

echo "== build: Rust enabled =="
ninja -C build-rust

echo

echo "OK: both variants built"
```

### 예상되는 출력 형태

아래는 “형태”만을 보여주는 예시입니다. Meson의 출력 포맷/정렬은 버전에 따라 달라질 수 있습니다.

```text
== configure: Rust disabled (shipping artifact) ==
  rust                            disabled                        [auto, enabled, disabled]
...
== configure: Rust enabled (CI validation artifact) ==
  rust                            enabled                         [auto, enabled, disabled]
...
OK: both variants built
```

이 스크립트는 단순하지만 운영 계약에서 중요한 성질을 갖습니다.

* 배포 아티팩트(build-norust)는 항상 동일한 옵션으로 생성됩니다.
* Rust-enabled(build-rust)는 toolchain이 빠지면 configure 단계에서 즉시 실패합니다. PR이 말하는 “fails loudly”를 CI 계약으로 삼는 셈입니다.[^1]

여기까지 해두면 `-Drust=auto`가 CI에 들어와도 영향 범위를 통제할 수 있습니다. 특히 build root가 변해서 Rust가 “조용히” 켜지는 상황을 원천적으로 없앱니다.

## 문서화해야 하는 기능 매트릭스: 옵션/도구/산출물

systemd는 이제 단순히 “systemd 버전”만 기록해선 부족합니다. 빌드 결과가 환경에 의해 갈리는 옵션이 생겼기 때문입니다.

내가 권하는 매트릭스는 다음 항목을 반드시 포함합니다.

* `-Drust` 값: disabled/auto/enabled
* `--auto-features` 값: auto/enabled/disabled
* meson 버전
* rustc/bindgen/clang(libclang) 버전
* Rust-enabled 여부에 따라 추가/변경되는 산출물 목록(프로그램, unit, man page, test)

여기서 `--auto-features=enabled`는 특히 중요합니다. PR #44324가 다운스트림 실패 원인으로 직접 언급한 플래그이기도 하고[^1], Meson 문서가 packager 목적의 “전역 override”로 설명하는 옵션이기 때문입니다.[^5]

이 매트릭스를 남기는 방식은 조직의 툴체인에 따라 달라질 수 있지만, 중요한 건 “텍스트로만 남기지 말고 아티팩트와 같이 남기는 것”입니다.

* SRPM/.dsc에 `build-contract.json` 같은 파일을 포함
* CI artifact에 `meson configure` 전체 출력 첨부
* container image label에 `org.example.systemd.rust=disabled/enabled` 같은 메타데이터 부여

systemd처럼 다운스트림이 많은 프로젝트는, upstream이 제공하는 `README`의 optional deps 목록만으로는 부족합니다. README에는 rustc/bindgen floor가 명시돼 있지만[^13], 우리 조직이 실제로 “Rust-enabled build를 배포하느냐”는 별개의 계약이기 때문입니다.

## 정리: -Drust=auto는 편의 옵션이 아니라 계약 위반 트리거입니다

PR #44324의 핵심을 한 문장으로 요약하면 “systemd 빌드가 toolchain 존재 여부에 의해 분기할 수 있게 됐다”입니다.[^1]  이 분기는 Rust 찬반 논쟁과 상관없이 패키징/CI의 비용 곡선을 바꿉니다.

* `auto`는 로컬 개발에선 편하지만, 패키징에선 숨은 입력값을 만듭니다.
* Cargo를 배제한 선택은 배포판 제약(네트워크 금지, vendoring 비용)과 잘 맞지만[^8], 그 대신 bindgen/libclang/meson 버전 편차가 빌드 신뢰경계에 들어옵니다.[^1]
* downstream이 해야 할 일은 “Rust를 쓰느냐 마느냐”가 아니라, `-Drust`를 disabled/enabled로 고정하고 Rust-enabled 빌드를 별도 아티팩트로 관리하는 것입니다.

내 결론은 단순합니다. systemd의 Rust 지원은 기술적으로는 leaf program부터 시작하는 보수적인 변화지만, `-Drust=auto`는 빌드 계약 관점에서 공격적인 변화입니다. 그래서 계약을 먼저 고정하는 쪽이 장기 비용이 더 낮습니다.

## 참고 자료

- [rust: support programs written in Rust #44324](https://github.com/systemd/systemd/pull/44324)
- [systemd meson_options.txt](https://github.com/systemd/systemd/blob/main/meson_options.txt)
- [systemd README](https://github.com/systemd/systemd/blob/main/README)
- [systemd Merges Support For Rust Programs](https://www.phoronix.com/news/systemd-Merges-Rust-Programs)
- [Meson: Build options (feature/auto_features)](https://mesonbuild.com/Build-options.html)
- [Meson: Rust module (rust.bindgen)](https://mesonbuild.com/Rust-module.html)
- [Meson: Feature option object](https://mesonbuild.com/Reference-manual_returned_feature.html)
- [Meson 소스: feature 옵션 기본값이 auto임을 보여주는 optinterpreter.py](https://chromium.googlesource.com/external/github.com/mesonbuild/meson/+/b9ad8a0604a49881ca72fb5a3e534c772e4e00f5/mesonbuild/optinterpreter.py)
- [Fedora Packaging Guidelines: Build time network access](https://fedoraproject.org/wiki/User%3ATibbs/SensitiveSpecs)
- [Debian Rust Packaging Policy](https://wiki.debian.org/Teams/RustPackaging/Policy)
- [Debian Rust Team Book: Packaging policy](https://book-df79a1.pages.debian.net/policy.html)
- [Arch systemd 패키징 변경( rust/rust-bindgen makedepends 언급 )](https://www.mail-archive.com/arch-commits%40lists.archlinux.org/msg1249506.html)
- [Meson rpath 관련 커밋(Christian Brauner): Rust dylib 링크 시에만 sysroot를 rpath에 추가](https://chromium.cpp.hybrid-analysis.googlesource.com/external/github.com/mesonbuild/meson/+/c65cf102d587d19d01021230395da0141a18d90a)
- [PSA: Meson now building all auto-detected features (NixOS Discourse)](https://discourse.nixos.org/t/psa-meson-now-building-all-auto-detected-features/3271)

[^1]: <https://github.com/systemd/systemd/pull/44324>
[^2]: <https://www.phoronix.com/news/systemd-Merges-Rust-Programs>
[^3]: <https://chromium.googlesource.com/external/github.com/mesonbuild/meson/%2B/b9ad8a0604a49881ca72fb5a3e534c772e4e00f5/mesonbuild/optinterpreter.py>
[^4]: <https://github.com/systemd/systemd/blob/main/meson_options.txt>
[^5]: <https://mesonbuild.com/Build-options.html>
[^6]: <https://discourse.nixos.org/t/psa-meson-now-building-all-auto-detected-features/3271>
[^7]: <https://www.mail-archive.com/arch-commits%40lists.archlinux.org/msg1249506.html>
[^8]: <https://fedoraproject.org/wiki/User%3ATibbs/SensitiveSpecs>
[^9]: <https://wiki.debian.org/Teams/RustPackaging/Policy>
[^10]: <https://mesonbuild.com/Rust-module.html>
[^11]: <https://chromium.cpp.hybrid-analysis.googlesource.com/external/github.com/mesonbuild/meson/%2B/c65cf102d587d19d01021230395da0141a18d90a>
[^12]: <https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/>
[^13]: <https://github.com/systemd/systemd/blob/main/README>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
