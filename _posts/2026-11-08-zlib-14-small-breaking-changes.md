---
title: "zlib 1.4의 ‘작은’ 변경이 다운스트림 빌드·패키징을 깨는 방식"
description: "zlib 1.4에서 MSVC 산출물 이름이 바뀌면서, ABI보다 배포 계약이 먼저 깨지는 지점을 정리합니다."
date: 2026-11-08 11:17:05 +0900
categories: ["News", "OpenSource"]
tags: ["zlib", "packaging", "cmake", "msvc", "ci"]
render_with_liquid: false
---

## 2026-11-04 zlib 1.4: 릴리스는 보안보다 먼저 배포 파이프라인을 건드립니다

zlib 1.4는 upstream 기준 2026년 11월 4일 릴리스로 공지되었습니다[^1][^2].[^1]  
GitHub 릴리스 태그는 2026년 11월 5일 07:17에 게시된 것으로 보입니다[^3].[^3]

이 릴리스는 분량으로만 보면 전형적인 “보안 고쳐서 빨리 올리자” 쪽에 가깝습니다. 실제로 릴리스 노트도 Security fixes가 눈에 띄고, 외부 기사에서도 “10개 이상 보안 이슈”가 먼저 요약됩니다[^4].[^4]

그런데 CI/패키징 관점에서 더 먼저 터지는 건 보안 수정이 아니라 **빌드 산출물의 이름과 빌드 시스템의 기본값 변화**입니다. zlib 1.4 릴리스 노트의 Breaking changes 첫 줄에 CMake 관련 변경이 나오고, 그 안에 MSVC 산출물 파일명이 들어가 있습니다[^3].[^3]

특히 Windows에서 “라이브러리 파일 이름이 바뀌었다”는 문장은, 소스 수정이 아니라 배포 계약이 깨진다는 뜻입니다. 다운스트림에서 가장 흔한 장애는 다음처럼 터집니다.

- 컴파일은 된다.
- 링크 단계에서 갑자기 `LNK1104 cannot open file 'z.lib'` 류가 난다.
- 패키징 스텝에서 `copy z.dll ...`이 실패한다.
- 런타임에서 `libz.dll`을 못 찾는다.

이 글은 zlib 1.4의 보안 수정 자체를 풀이하지 않습니다. 대신 MSVC에서 `z` → `libz`로 바뀐 변화가, “ABI가 유지되더라도” 다운스트림 빌드/배포 파이프라인을 어떻게 깨는지에 초점을 둡니다. (공급망 관점의 더 큰 틀은 예전에 쓴 [Node.js 업그레이드를 공급망 위험으로 해석하기](https://daewooki.github.io/posts/nodejs-runtime-supply-chain-risk/), [Python security-only 릴리스에서 공급망이 흔들리는 지점](https://daewooki.github.io/posts/python-security-only-source-release-supply-chain/) 쪽에서 이미 다뤘고, 여기서는 반복하지 않습니다.)

---

## “파일명”이 API가 되는 이유: 링크 입력은 소스 호환보다 먼저 깨집니다

C/C++ 생태계에서 “호환성”을 말할 때 흔히 API/ABI를 떠올립니다. 하지만 운영 현실에서 더 자주 문제를 일으키는 건 **배포 아티팩트의 식별자**입니다.

- ELF 세계에서 `-lz`가 의미하는 건 “링커가 `libz.so` 또는 `libz.a`를 찾는다”는 규칙입니다.
- Windows/MSVC에서 `target_link_libraries(app PRIVATE z)`는 “링커 입력으로 `z.lib`를 넘긴다”에 가깝습니다.
- 패키징 스크립트는 대개 파일명으로 움직입니다. `install(FILES zlib1.dll ...)`, `Copy-Item z.dll ...` 같은 형태는 사실상 계약입니다.

따라서 upstream이 산출물 이름을 바꾸면, API/ABI 변경이 없어도 다운스트림은 깨집니다. 이때 중요한 건 “깨지는 레이어가 어디냐”입니다.

1) upstream 소스
2) upstream 빌드 시스템(CMake, Makefile.msc 등)
3) 패키지 레시피(Windows zip 배포, MSYS2 패키지, distro spec)
4) 소비자 빌드 시스템(CMake find 모듈/Config, Bazel rule, Meson wrap)
5) CI 캐시/아티팩트 저장소

zlib 1.4의 MSVC 산출물 이름 변경은 2)~5)를 넓게 건드립니다.

---

## zlib 1.4의 MSVC 산출물 이름 변경: z → libz

zlib.net의 1.4 요약에 Breaking changes로 명시되어 있습니다.

- “Library file names changed on MSVC: `z` is now `libz`, as in `libz.dll`, `libz.lib`, and the static `libzs.lib`”
- minizip도 같은 방식으로 바뀌었다

[^1][^3].[^1]

이 한 줄이 의미하는 건 단순히 파일명이 바뀌었다가 아닙니다.

- (이전) MSVC 빌드 산출물이 `z.dll`, `z.lib`, 정적은 `zs.lib` 같은 패턴이었다는 전제가 깔립니다.
- (이후) 동적 라이브러리/임포트 라이브러리/정적 라이브러리의 기본 이름이 각각 `libz.*`, `libzs.lib` 계열로 바뀝니다.

CMakeLists.txt에서도 이 의도가 코드로 박혀 있습니다. `if(MSVC) ... OUTPUT_NAME libz ... else OUTPUT_NAME z` 형태로 분기하고, 정적 라이브러리는 `ARCHIVE_OUTPUT_NAME libz${suffix}`를 사용합니다[^5].[^5]

여기서 중요한 포인트가 하나 있습니다.

- 이건 “Windows에서 Unix와 비슷하게 맞추자”는 통일성 개선처럼 보일 수 있습니다.
- 하지만 다운스트림 입장에서는 “패키지가 제공하는 파일명 contract가 바뀌었다”는 뜻입니다.

**MSVC 파일명 변경은 ABI 변경보다 더 자주 CI를 깨뜨립니다.**

왜냐하면 ABI는 대개 컴파일·링크까지는 통과시키고 런타임에서만 문제를 만들기도 하지만, 파일명은 링크 단계에서 즉시 실패하기 때문입니다.

---

## 어디서 깨지나: 다운스트림 실패 포인트를 레이어별로 쪼개기

### 1) CMake 소비자가 `z`를 직접 링크하는 경우

가장 흔한 패턴은 이런 형태입니다.

```cmake
# (안티패턴) Unix 감각으로 -lz를 의식하면서 z를 직접 링크
target_link_libraries(my_app PRIVATE z)
```

이 코드는 zlib를 “패키지”로 소비하는 게 아니라 “파일명 규칙”으로 소비합니다. MSVC에서 zlib 1.4를 올리면, zlib 쪽 산출물은 `libz.lib`가 기본이 되고, 소비자는 `z.lib`를 찾다가 그대로 링크 실패합니다[^3].[^3]

이 안티패턴이 오래 살아남는 이유는 간단합니다.

- Linux/macOS에서는 `z`라는 logical name이 안정적입니다.
- Windows에서 한 번 “돌아가던” 설정이 CI 템플릿으로 굳습니다.

zlib 1.4는 이 부분을 정면으로 건드립니다.

### 2) `find_library()`로 파일명을 탐색하는 경우

다음 패턴도 매우 흔합니다.

```cmake
find_library(ZLIB_LIB NAMES z zlib)
# ...
target_link_libraries(my_app PRIVATE ${ZLIB_LIB})
```

이건 얼핏 “유연한 탐색”처럼 보이지만, 사실상 downstream이 upstream 파일명 변화를 따라 수동으로 이름 목록을 유지하는 구조입니다.

- 1.4 이후 MSVC 기본은 `libz.lib`입니다.
- 탐색 목록에 `libz`가 없으면 깨집니다.

업그레이드 직후 여러 프로젝트에서 “내 로컬은 되는데 Windows CI만 깨진다”가 나오기 쉬운 이유가, 로컬 개발자는 vcpkg나 기존 binary 캐시를 쓰고 CI는 소스 빌드를 해서 산출물이 바뀌기 때문입니다.

### 3) 패키징 단계에서 DLL/IMP/STATIC을 파일명으로 복사하는 경우

이쪽이 가장 비용이 큽니다. 빌드가 깨지는 것보다 더 골치 아픈 건 “빌드는 성공했는데 배포가 실패”하는 케이스입니다.

예를 들면 다음 같은 PowerShell이 어디엔가 들어있습니다.

```powershell
Copy-Item $prefix\bin\z.dll  $artifact\bin\
Copy-Item $prefix\lib\z.lib  $artifact\lib\
```

zlib 1.4로 넘어가면 복사 대상이 `libz.dll`, `libz.lib`로 바뀝니다[^1].[^1]

이 스크립트는 소스 코드와 무관하게 깨지고, 조직 내에서는 “빌드 시스템 담당”이 아니라 “릴리스/배포 담당”이 급하게 불려 나옵니다.

### 4) minizip 같이 묶여 올라가는 서브컴포넌트

릴리스 노트에 minizip도 같은 네이밍 변경이 들어갑니다[^3].[^3]

zlib 자체만 쓰는 프로젝트는 그나마 단순하지만, 다음 형태에서는 문제가 증폭됩니다.

- 프로젝트가 zlib와 minizip을 같이 vendor하거나
- 패키지가 “한 번에” 둘을 묶어 배포하거나
- 빌드 캐시가 zlib만 갱신되고 minizip쪽은 그대로인 경우

이때는 실패가 이중으로 발생합니다.

---

## 재현 가능한 실패: Windows CI에서 링크와 패키징이 깨지는 최소 시나리오

여기서는 장난감 예제 대신, 실제로 많이 쓰는 형태(외부 의존성을 별도 prefix에 설치하고 소비)가 깨지는 모습을 재현합니다.

### 환경

- Windows runner에서 MSVC 사용
- zlib 1.4를 CMake로 빌드해 prefix에 설치
- 소비자 프로젝트는 “기존 계약(z.*)”을 가정

zlib 1.4는 CMake 최소 버전도 3.15로 올렸습니다[^1].[^1]  
따라서 CI 이미지에 CMake가 너무 낮으면 빌드 이전에 configure 단계에서 터집니다.

### 1) zlib 1.4 빌드 및 설치

```powershell
# 1) 소스 받기
# (실제 CI에서는 archive를 받아도 되지만, 여기서는 태그를 직접 사용)
git clone --depth 1 --branch v1.4 https://github.com/madler/zlib.git zlib-1.4

# 2) out-of-source 빌드
cmake -S zlib-1.4 -B build-zlib `
  -G "Visual Studio 17 2022" -A x64 `
  -DCMAKE_INSTALL_PREFIX=$pwd\zlib-prefix

# 3) 빌드
cmake --build build-zlib --config Release

# 4) 설치
cmake --install build-zlib --config Release

# 5) 설치된 산출물 확인
Get-ChildItem .\zlib-prefix\bin
Get-ChildItem .\zlib-prefix\lib
```

zlib 1.4 릴리스 노트는 MSVC에서 `libz.dll`, `libz.lib`, 정적은 `libzs.lib`가 된다고 명시합니다[^1][^3].[^1]

즉, 여기서 `zlib-prefix\lib\z.lib`는 존재하지 않는 게 정상입니다.

### 2) 소비자 프로젝트: 예전 계약에 묶여 있는 형태

디렉토리 구조는 이런 식이라고 가정합니다.

```
consumer/
  CMakeLists.txt
  src/main.c
```

`src/main.c`는 zlib 함수를 하나라도 호출하도록 합니다.

```c
#include <stdio.h>
#include <string.h>
#include <zlib.h>

int main() {
    const char* msg = "hello zlib";
    uLong src_len = (uLong)strlen(msg);
    uLong dst_len = compressBound(src_len);

    unsigned char out[256];
    if (dst_len > sizeof(out)) return 2;

    int rc = compress2(out, &dst_len, (const Bytef*)msg, src_len, Z_BEST_SPEED);
    if (rc != Z_OK) {
        printf("compress2 failed: %d\n", rc);
        return 1;
    }

    printf("ok: %lu -> %lu bytes (zlib %s)\n", src_len, dst_len, ZLIB_VERSION);
    return 0;
}
```

`CMakeLists.txt`에서 문제를 일부러 만들겠습니다.

```cmake
cmake_minimum_required(VERSION 3.15)
project(consumer C)

add_executable(consumer src/main.c)

# (안티패턴) prefix가 주어졌다고 가정하고 파일명으로 때려박기
set(ZLIB_PREFIX "${CMAKE_SOURCE_DIR}/../zlib-prefix")

target_include_directories(consumer PRIVATE "${ZLIB_PREFIX}/include")

# 예전에는 MSVC 산출물이 z.lib라는 가정이 있었고,
# 이 줄은 zlib 1.4에서 바로 깨진다.
target_link_libraries(consumer PRIVATE "${ZLIB_PREFIX}/lib/z.lib")
```

빌드하면 링크에서 실패합니다. 이 실패는 API/ABI의 문제가 아니라 “배포 아티팩트 이름이 바뀌었다”는 신호입니다.

이 재현은 일부러 hardcode를 했지만, 실제 레거시 CI 스크립트는 hardcode에 가깝게 동작합니다. 특히 사내 binary cache를 만드는 팀은 “이 파일들을 모아서 zip으로 만든다”를 파일명으로 정의하는 경우가 많습니다.

---

## 고치는 방향: 파일명이 아니라 CMake target으로 계약을 옮기기

zlib 1.4의 CMakeLists.txt를 보면 shared 라이브러리에 `ZLIB::ZLIB` alias target을 제공하고, static에도 `ZLIB::ZLIBSTATIC` alias를 둡니다[^5].[^5]

이게 중요한 이유는, downstream이 **링커 입력(파일명)** 대신 **빌드 시스템이 제공하는 logical target**에 의존하도록 바꿀 수 있기 때문입니다.

### 1) Config package를 우선으로 찾기

zlib 1.4 릴리스 노트는 CMake 패키징/설치가 강화되었음을 언급합니다[^1].[^1]

이 경우 소비자 프로젝트는 다음처럼 가져가는 편이 안정적입니다.

```cmake
set(ZLIB_ROOT "${CMAKE_SOURCE_DIR}/../zlib-prefix")
list(PREPEND CMAKE_PREFIX_PATH "${ZLIB_ROOT}")

find_package(ZLIB CONFIG REQUIRED)

add_executable(consumer src/main.c)
target_link_libraries(consumer PRIVATE ZLIB::ZLIB)
```

이렇게 하면 MSVC에서 output name이 `z`든 `libz`든, 소비자가 파일명을 직접 모를 수 있습니다.

### 2) Config가 없는 환경에서는 FindZLIB + 보완

현실적으로는 다음 같은 혼종 환경이 많습니다.

- Linux는 system zlib
- Windows는 vcpkg
- CI는 소스 빌드 + 자체 prefix

이때는 `find_package(ZLIB)`가 플랫폼별로 다른 방식으로 동작할 수 있습니다. 중요한 건 “내가 `z`를 링크했다” 같은 표기가 코드에 남지 않게 만드는 것입니다.

내가 많이 쓰는 정리 방식은, 내부적으로는 무조건 target만 남기고, 파일명 매핑은 가장자리에서 처리하는 겁니다.

```cmake
# 바깥에서 무슨 방법으로 찾든, 안쪽은 항상 ZLIB::ZLIB만 본다
if (NOT TARGET ZLIB::ZLIB)
  find_package(ZLIB REQUIRED)
endif()

add_library(my_zlib INTERFACE)

target_link_libraries(my_zlib INTERFACE ZLIB::ZLIB)
```

이렇게 한 번 감싸두면, 프로젝트 안쪽 수십 군데에 퍼져있는 `z` 문자열을 지우는 게 가능합니다.

**핵심은 “파일명 변경을 코드 변경으로 전염시키지 않는 것”입니다.**

---

## MSVC 네이밍 변경이 특히 치명적인 이유: Windows의 .dll/.lib 분업

Linux에서 `libz.so`가 바뀌면 대개 soname/심볼 버전/패키지 의존성으로 추적합니다. Windows/MSVC는 모델이 조금 다릅니다.

- 런타임 로더 관점: `.dll`이 필요
- 링크 타임 관점: import `.lib`이 필요
- 정적 링크 관점: static `.lib`이 필요

zlib 1.4는 이 3종을 동시에 바꿉니다(`libz.dll`, `libz.lib`, `libzs.lib`).[^1]

그래서 CI에서 “어느 단계에서 실패하느냐”가 팀 구성을 찢어놓습니다.

- 링크 실패: 빌드 담당이 대응
- 패키징 실패: 릴리스 엔지니어가 대응
- 런타임 실패: 운영/QA가 먼저 발견

그리고 가장 짜증나는 케이스는 “동적/정적을 바꿔 끼울 때”입니다.

- 어떤 제품은 성능/배포 단순화를 이유로 static zlib를 선호합니다.
- 다른 제품은 license/patching/업데이트 용이성을 이유로 dll zlib를 선호합니다.

파일명이 바뀌면 이 선택지 자체가 CI 레벨에서 조건 분기를 강제하게 됩니다.

---

## zlib 1.4의 다른 Breaking changes가 만드는 2차 장애

MSVC 파일명 변경이 가장 눈에 띄지만, 다운스트림을 흔드는 변경은 더 있습니다.

### 1) 최소 CMake 버전 3.15

zlib 1.4는 최소 CMake 버전을 3.12에서 3.15로 올렸습니다[^1][^3].[^1]

이 변화는 특히 다음 환경을 직격합니다.

- 오래된 enterprise Linux 빌드 이미지
- 에어갭 내부 빌드 팜(도구 업데이트가 느림)
- Bazel/Gradle 같은 상위 빌드가 내부적으로 CMake를 호출하는 구조

재미있는 건, 이 장애는 “보안 릴리스니까 빨리 올리자” 압력과 정반대 방향으로 작동합니다. 보안 패치가 급할수록 도구체인 제약이 발목을 잡습니다.

### 2) `z_off_t` 타입 회귀: 헤더/바이너리 불일치 위험

릴리스 노트에는 `z_off_t`가 1.3.2의 `long long`에서 다시 `long`으로 돌아갔다고 적혀 있습니다[^1].[^1]

이건 겉으로 보기엔 “타입 하나 바뀐 것”이지만, downstream 패키저에게는 매우 위험한 시나리오를 만듭니다.

- 헤더만 갱신되고(예: vendor header roll)
- 라이브러리 바이너리가 갱신되지 않거나(캐시, 서브모듈, 부분 업데이트)
- 반대로 바이너리만 갱신되고 헤더가 남아있을 때

이 조합은 ABI 불일치로 바로 이어질 수 있습니다. 릴리스 노트가 “Windows applications built with 1.3.2 headers should be recompiled”라고 못을 박는 이유도 이 맥락입니다[^3].[^3]

즉, zlib 1.4에서 더 무서운 건 “파일명 깨짐”으로 드러나는 실패가 아니라, “운 좋게 빌드가 되면서 숨어버리는 실패”가 같이 들어온다는 점입니다.

### 3) `deflateReset()` 동작 정합성: 테스트 깨짐

릴리스 노트는 `deflateReset()`이 이제 `deflateSetHeader()`로 설정한 gzip header까지 reset한다고 밝힙니다[^1][^3].[^1]

이건 API 시그니처는 유지되면서 행위가 바뀌는 타입의 변화입니다.

- 정합성 관점에서는 “문서대로 구현을 맞춘 것”
- 다운스트림 관점에서는 “회귀 테스트가 깨지는 것”

보안 릴리스 타이밍에 이런 변화가 같이 들어오면, 조직 내부에서는 “보안 때문에 올려야 하는데 기능 테스트가 깨진다” 갈등이 커집니다.

---

## 벤더링 업데이트가 이미 시작된 증거: Chromium/Firefox/Yocto 쪽 움직임

오늘이 KST 2026-11-08이라면, upstream 릴리스(2026-11-04) 이후 4일이 지난 시점입니다. 이 4일 안에 이미 메이저 다운스트림이 움직이고 있습니다.

### Chromium: third_party/zlib가 2026-11-06에 v1.4로 업데이트

Chromium 저장소에는 `[zlib] Update to v1.4` 커밋이 2026년 11월 6일자로 올라왔습니다[^6].[^7]

브라우저 벤더가 zlib를 vendor해서 쓴다는 건 새삼스러운 얘기는 아니지만, 문제는 속도입니다. vendor roll이 시작되면 연쇄 반응이 바로 발생합니다.

- Chromium 기반 제품(Chromium embedder)
- Electron류
- 각종 네이티브 SDK

이 라인에서 “다음 릴리스에 zlib 1.4가 들어온다”는 의미가 됩니다.

### Firefox: vendored zlib 업데이트 트래킹

Mozilla Bugzilla에는 `Update zlib to version 1.4` 작업이 올라와 있고, 설명에 “zlib 1.4 was released on 2026-11-04”라고 직접 적혀 있습니다[^8].[^8]

여기서 중요한 건 “Firefox가 zlib를 어떻게 쓰냐”보다, 이런 트래킹이 올라오는 순간 downstream 패키징 팀들이 동일한 티켓을 만들기 시작한다는 점입니다.

### Yocto/OpenEmbedded: 자동 업그레이드 도구가 2026-11-06에 1.4 업그레이드 성공 메일

OpenEmbedded 쪽 메일링 리스트에는 Auto Upgrade Helper가 zlib 레시피를 1.4로 올리는 시도가 성공했다는 알림이 2026년 11월 6일자로 올라왔습니다[^9].[^9]

임베디드/디바이스 쪽은 보통 최신을 빨리 올리는 쪽이 아니라는 편견이 있는데, 여기서는 자동화가 속도를 끌어올립니다. 이 라인에서 문제는 “업그레이드가 된다/안 된다”가 아니라, 업그레이드가 되는 순간 레시피/패치 레이어가 산출물 네이밍을 어떻게 취급하느냐입니다.

### MSYS2: 업데이트 큐에 1.4가 올라옴

MSYS2 패키지 큐에도 zlib가 1.4로 올라갈 준비가 된 항목이 보입니다[^10].[^10]

여기까지 오면 “조만간 Windows에서 GCC/Clang 계열로 zlib를 설치한 환경”과 “MSVC로 빌드한 환경”이 각자 다른 파일명 관습을 갖게 될 여지가 생깁니다. 다운스트림 프로젝트가 이 차이를 파일명으로 흡수하면, 다시 깨지는 미래가 반복됩니다.

### Homebrew: (아직) stable이 1.3.2로 남아있는 예

흥미롭게도 Homebrew core의 zlib stable 버전은 API JSON 기준 1.3.2로 남아 있습니다[^11].[^11]

이건 “느리다”는 의미가 아니라, 많은 패키지 생태계에서 zlib가 사실상 시스템 컴포넌트라는 점을 보여줍니다. Homebrew 페이지에서도 keg-only(운영체제가 제공)로 표시됩니다[^12].[^12]

즉, zlib 1.4가 바로 모든 데스크톱 개발 환경에 깔리는 그림은 아닙니다. 대신 브라우저/OS/런타임 벤더가 먼저 vendor copy를 올리는 쪽이 빠릅니다.

---

## 회의론: “파일명 바꾸는 게 뭐가 그렇게 큰 일인가”에 대한 답

파일명 변경은 소스 코드를 건드리지 않으니 사소해 보입니다. 하지만 다운스트림에서 비용이 커지는 이유는 세 가지입니다.

1) 변경이 “교차”로 일어난다
- 빌드 담당이 `target_link_libraries`를 고치면 끝나는 문제가 아닙니다.
- 배포 zip, 설치 스크립트, 런타임 로더 경로까지 같이 움직입니다.

2) 계약이 암묵적이다
- 많은 조직에서 zlib는 “너무 당연해서 문서화되지 않은” 의존성입니다.
- 그 상태에서 파일명은 암묵적 규칙으로 굳습니다.

3) 롤백이 어렵다
- 보안 수정이 많으면 롤백 자체가 리스크가 됩니다.
- 반대로 업그레이드를 받아들이면 CI/배포 계약을 고쳐야 합니다.

이 구조는 예전에 [Atlantis 번들 제거의 파장](https://daewooki.github.io/posts/atlantis-0490-iac-execution-contract/)에서 말했던 “실행 계약이 깨지면, 코드 변경보다 운영 변경이 먼저 터진다”와 닮아 있습니다.

---

## 앞으로 지켜볼 것: 다운스트림이 선택할 수 있는 호환 전략의 갈림길

zlib 1.4의 MSVC 네이밍은 upstream이 분명히 의도를 갖고 바꾼 것입니다. 실제로 CMakeLists.txt에서 MSVC만 `OUTPUT_NAME libz`로 분기해 플랫폼 간 이름을 맞추려는 흔적이 명확합니다[^5].[^5]

다운스트림이 여기서 취할 수 있는 전략은 대략 세 가지로 갈립니다.

### 1) upstream 네이밍을 그대로 수용

- 장점: upstream과의 마찰이 적고, 장기적으로는 문서/관행이 통일될 수 있습니다.
- 단점: 레거시 소비자(파일명 hardcode)가 많은 조직은 단기 비용이 큽니다.

### 2) 패키지 레벨에서 “별칭 파일”을 제공

예를 들어 패키저가 `z.lib`를 `libz.lib`의 복사본/심볼릭 링크로 제공하는 방식입니다.

- 장점: 소비자 코드/스크립트를 바로 안 고쳐도 됩니다.
- 단점: 장기적으로 “둘 다 존재”하는 상태가 남아, 다시 다른 업그레이드에서 혼란을 키웁니다.

Windows에서 심볼릭 링크가 늘 가능한 것도 아니라서, 복사본을 만들면 아티팩트 중복이 생기고, 보안 패치 시 어느 파일을 교체했는지 추적이 어려워집니다.

### 3) 소비자 빌드 시스템을 target 중심으로 재정렬

이건 시간이 걸리지만, 장기적으로는 가장 깔끔합니다. 즉, `z`/`libz`/`zlib` 같은 문자열을 프로젝트에서 지우고, `ZLIB::ZLIB` 같은 target만 남기는 방식입니다. zlib upstream 자체도 alias target을 제공합니다[^5].[^5]

내 경험상 이 재정렬은 “한 번에 끝내기”가 아니라, CI가 한 번씩 깨질 때마다 주변부를 정리해나가는 쪽으로 진행됩니다.

---

## 정리: zlib 1.4는 보안 릴리스처럼 보이지만, 실제 파급은 배포 계약에서 시작됩니다

zlib 1.4는 2026-11-04 릴리스로 공지되었고, 릴리스 노트에 명시적으로 MSVC 라이브러리 파일명이 `z`에서 `libz`로 바뀌었다고 적혀 있습니다[^1][^3].[^1]

이 변화는 코드 레벨 API/ABI보다 먼저, 다운스트림의 링크 입력과 패키징 스크립트를 찢습니다. 게다가 Chromium(2026-11-06)처럼 vendor 업데이트가 빠르게 시작되면서, “언젠가 고치자”가 아니라 “곧 깨진다”로 바뀌었습니다[^6].[^7]

보안 수정의 중요성을 깎아내릴 생각은 없습니다. 다만 운영 현장에서는 보안 패치 적용의 첫 장애물이 종종 취약점이 아니라 **아티팩트 이름**입니다. zlib 1.4는 그 현실을 아주 명확하게 보여주는 릴리스입니다.

## 참고 자료

- [zlib home page](https://www.zlib.net/)
- [zlib 1.4 manual](https://www.zlib.net/manual.html)
- [GitHub release: zlib 1.4](https://github.com/madler/zlib/releases/tag/v1.4)
- [zlib CMakeLists.txt](https://github.com/madler/zlib/blob/develop/CMakeLists.txt)
- [Chromium third_party/zlib: Update to v1.4 커밋](https://chromium.googlesource.com/chromium/src/third_party/zlib/+/be18790d0ed2434ea9ca9f09de0534900f97fb6f)
- [Mozilla Bug 2089618: Update zlib to version 1.4](https://bugzilla.mozilla.org/show_bug.cgi?id=2089618)
- [OpenEmbedded Core: AUH zlib 1.4 업그레이드 성공 메일](https://lore-kernel.gnuweeb.org/openembedded-core/010101a1af72cd24-bb0ab83c-bbf7-4fda-a262-8bcd01ce4825-000000@us-west-2.amazonses.com/)
- [MSYS2 pending updates (ucrt64)](https://packages.msys2.org/queue?repo=ucrt64)
- [Homebrew zlib formula JSON](https://formulae.brew.sh/api/formula/zlib.json)
- [Phoronix: Zlib 1.4 Released With More Than One Dozen Security Fixes](https://www.phoronix.com/news/Zlib-1.4-Released)
- [Helm 4 업그레이드의 난관은 배포 증명 체인이다](https://daewooki.github.io/posts/helm4-upgrade-deployment-attestation-chain/)
- [Node.js 26.8.2 업그레이드를 공급망 위험으로 해석하기](https://daewooki.github.io/posts/nodejs-runtime-supply-chain-risk/)
- [Python security-only 릴리스에서 공급망이 흔들리는 지점](https://daewooki.github.io/posts/python-security-only-source-release-supply-chain/)
- [Atlantis 0.49.0: Terraform/OpenTofu 번들 제거의 파장](https://daewooki.github.io/posts/atlantis-0490-iac-execution-contract/)
- [GNU patch 2.8.1 보안 릴리스: 빌드 도구 취약점이 공급망으로 번지는 경로](https://daewooki.github.io/posts/gnu-patch-toolchain-cve-supply-chain/)

[^1]: <https://www.zlib.net/>
[^2]: <https://www.zlib.net/manual.html>
[^3]: <https://github.com/madler/zlib/releases/tag/v1.4>
[^4]: <https://www.phoronix.com/news/Zlib-1.4-Released>
[^5]: <https://github.com/madler/zlib/blob/develop/CMakeLists.txt>
[^6]: <https://chromium.googlesource.com/chromium/src/third_party/zlib/+/be18790d0ed2434ea9ca9f09de0534900f97fb6f>
[^7]: <https://chromium.googlesource.com/chromium/src/third_party/zlib/%2B/be18790d0ed2434ea9ca9f09de0534900f97fb6f>
[^8]: <https://bugzilla.mozilla.org/show_bug.cgi?id=2089618>
[^9]: <https://lore-kernel.gnuweeb.org/openembedded-core/010101a1af72cd24-bb0ab83c-bbf7-4fda-a262-8bcd01ce4825-000000@us-west-2.amazonses.com/>
[^10]: <https://packages.msys2.org/queue?repo=ucrt64>
[^11]: <https://formulae.brew.sh/api/formula/zlib.json>
[^12]: <https://formulae.brew.sh/formula/zlib>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
