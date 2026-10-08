---
title: "Python 3.10 EOL과 보안-only 전환이 멀티 런타임 운영을 강제한다"
description: "3.10 EOL과 3.13 보안-only 전환은 업그레이드를 ‘언젠가’가 아니라 ‘지금’ 일정으로 바꿉니다."
date: 2026-10-08 14:24:39 +0900
categories: ["News", "Languages"]
tags: ["python", "runtime-lifecycle", "dependency-compatibility", "upgrade-rings", "container-build", "aws-lambda"]
render_with_liquid: false
---

Python Insider가 2026-10-01에 Python 3.10.22·3.11.17·3.12.15·3.13.16·3.14.8을 한 번에 공지했습니다. 공지문에는 두 가지 운영상 강제 조건이 같이 들어 있습니다. 첫째, Python 3.10.22가 3.10의 최종 릴리스이며 2026-10-01부로 EOL이라 **추가 보안 업데이트가 더는 없습니다**. 둘째, Python 3.13.16은 3.13 라인의 “last full maintenance”라서 이후 3.13은 security fixes only로만 갑니다. 게다가 3.10.22·3.11.17·3.12.15는 source-only(Windows/macOS installer 없음)라는 공급 형태의 변화도 동시에 확인됩니다.[^1]

이 조합이 까다로운 이유는, 멀티 런타임(서버/배치/CI/람다 레이어)에서 “Python 버전”이 단지 `python --version` 문자열이 아니라 다음을 한 번에 의미하기 때문입니다.

- 런타임 바이너리의 공급 형태(official installer가 존재하는가, source-only인가)
- 배포 아티팩트의 형태(container image, zip, layer 등)와 그 안에 고정되는 libc/OpenSSL/expat 같은 구성 요소
- dependency compatibility(특히 C extension wheel)와 빌드 파이프라인의 분기
- 운영상 업그레이드 링(카나리→확대)이 돌아가는 단위(서비스별인가, 런타임 베이스 이미지별인가)

결국 “3.10 EOL”과 “3.13 security-only 전환”은 업그레이드를 기능 개선이 아니라 운영 리스크 제거 작업으로 만들어 버립니다.

## 무슨 일이 있었나: 날짜·버전·모드 전환을 운영 일정으로 번역하기

이번 묶음 릴리스에서 운영 관점으로 가장 중요한 사실만 날짜로 다시 적으면 다음과 같습니다.

- 2026-10-01: Python 3.10.22 릴리스. 3.10 라인의 최종 릴리스이며 EOL(이후 보안 업데이트 없음).[^1]
- 2026-10-01: Python 3.11.17 릴리스. 3.11은 security fixes only 단계이며, binary installer가 더는 제공되지 않습니다(3.11.9가 마지막 installer 제공 릴리스).[^2]
- 2026-09-30: Python 3.12.15 릴리스. 3.12도 security fixes only 단계이며, binary installer가 더는 제공되지 않습니다(3.12.10이 마지막 installer 제공 릴리스).[^3]
- 2026-10-01: Python 3.13.16 릴리스. 3.13.16이 마지막 full maintenance(정기 bugfix 릴리스 + binary installer 제공)이고 이후 3.13은 security-only로 전환됩니다. PEP 719에는 3.13.16이 “Final regular bugfix release with binary installers”로 명시돼 있습니다.[^1]
- 2026-09-30: Python 3.14.8 릴리스. 3.14.8은 “expedited security release”로 소개되며(긴급 성격), 3.14 라인은 아직 bugfix 단계입니다.[^4]

이게 왜 운영 일정이 되느냐 하면, EOL은 “취약점 패치가 더는 안 나오는 상태”이고 security-only는 “패치가 나오더라도 공급(installer/바이너리)과 cadence가 달라지는 상태”이기 때문입니다. Python Developer’s Guide는 security 단계에 대해 “2년(3.13 이전은 18개월) 이후에는 security fix만 받고, binary는 더 이상 릴리스하지 않으며, source-only 릴리스를 필요 시점에 낸다”고 정의합니다.[^5]

멀티 런타임 조직에서는 이 전환이 다음처럼 번역됩니다.

- 3.10 서비스: “다음 분기쯤”이 아니라 2026-10-01 이후로는 보안 리스크를 ‘상시 보유’하는 상태로 들어갑니다.
- 3.13 서비스: 당장 EOL은 아니지만, 3.13 유지 전략을 “installer 기반 업그레이드”에서 “source-only + 자체 빌드/검증”으로 바꿀지, 아니면 “3.14로 이동”할지 결정을 강요받습니다.

## 배경: Python 릴리스 수명주기와 ‘바이너리 끊김’의 의미

Python은 PEP 602의 annual release cycle(10월 정기 릴리스)을 기반으로 “5년 지원” 프레임을 유지합니다. 다만 PEP 602에는 중요한 주석이 하나 있습니다. 3.13부터는 full support(bugfix + binaries) 기간이 2년으로 늘었고, 3.9~3.12는 18개월 full support 후 42개월 security fixes라는 체계였다는 점입니다.[^6]

이 배경이 이번 공지와 만나면 함정이 하나 생깁니다.

- 3.10 EOL은 “지원 끝”이라 직관적입니다.[^7]
- 3.13 security-only 전환은 “지원은 계속됨”이라 심리적으로 미뤄지기 쉽습니다.

그런데 보안-only 전환에서 진짜로 바뀌는 것은 지원 여부가 아니라 공급망 형태입니다.

- bugfix 단계: 정기적으로 source + Windows/macOS installer 같은 binary가 같이 나오고(Devguide 표현으로 roughly every two months), CI/개발환경/빌드가 공식 공급물을 그대로 받아 쓸 수 있습니다.[^5]
- security 단계: binary가 끊깁니다. 그리고 릴리스 cadence가 고정이 아닙니다.[^5]

이번 공지문이 이 변화를 아주 노골적으로 보여줍니다. 3.10.22·3.11.17·3.12.15가 source-only라 “Windows/macOS installer 없음”이 공지 자체에 박혀 있습니다.[^1]

운영에서 이게 뜻하는 바는 단순합니다.

- 그동안 “Python patch upgrade = 패키지 매니저/installer 업그레이드”였던 팀은, 이제 “Python patch upgrade = 런타임 자체를 빌드하는 파이프라인 + 그 결과물의 서명/검증 + 배포”로 바뀝니다.
- 특히 CI가 Windows/macOS runner에서 official installer를 당연하게 쓰고 있었다면(그리고 그 버전의 patch까지 테스트하길 원했다면), source-only 릴리스는 테스트 전략까지 바꿔야 합니다.

이 지점에서 3.13이 security-only로 내려가는 순간, “3.13을 계속 쓰겠다”는 선택은 “Python을 계속 빌드해서 배포하겠다”는 선택과 거의 동치가 됩니다.

## 왜 중요한가: 멀티 런타임에서 ‘업그레이드 단위’가 깨진다

멀티 런타임 환경에서 가장 흔한 실패는 업그레이드 단위를 서비스 단위로만 잡는 것입니다. 서버는 서버대로, 배치는 배치대로, CI는 CI대로 따로 움직입니다. 그러다가 수명주기 이벤트(EOL/security-only)가 오면 다음 문제가 한꺼번에 터집니다.

1) 서버 런타임은 container image로 굳어 있는데, 그 베이스 이미지의 Python이 EOL이거나 source-only로 전환되어도 팀이 체감하지 못합니다.

2) 배치 작업은 dependency가 서버와 거의 같은데도 lock/constraints가 분리돼 있어서, Python minor 업그레이드 시점에 서로 다른 의존성 그래프가 만들어집니다.

3) CI는 더 오래된 Python을 잡고 있습니다. “CI가 제일 안전해야 한다”는 착각 때문에, 오히려 CI가 업그레이드의 발목을 잡는 경우가 많습니다.

4) Lambda layer나 zip 배포는 런타임이 사실상 “빌드 머신의 Python + wheel”로 결정되는데, 이쪽이 가장 supply-chain 영향(예: OpenSSL)과 아키텍처(x86_64/arm64)에 민감합니다.

이번 공지에서 OpenSSL 업데이트가 3.13.16/3.14.8에 들어갔다는 사실은, 운영 아티팩트가 단순히 Python만이 아니라 “내부 번들”까지 같이 움직인다는 것을 상기시킵니다. 공지문에는 3.13.16이 Windows/macOS/Android에서 OpenSSL 3.0.21에서 3.5 LTS 계열(3.5.9)로 이동한다고 적혀 있습니다.[^1]

즉, 멀티 런타임에서는 업그레이드 단위를 다음 중 어디로 고정할지 결정해야 합니다.

- (A) 서비스 단위
- (B) 런타임 베이스 단위(“Python 런타임 이미지/레이어”)
- (C) dependency 세트 단위(“lockfile + wheelhouse”)

내 경험상 수명주기 이벤트가 오면 (B)를 중심으로 재정렬하는 쪽이 비용이 낮았습니다. 런타임을 한 번 만들고, 그 위에 서버/배치/람다를 같은 방식으로 얹는 구조가 되면, 업그레이드 링도 “런타임 링”으로 통합되기 때문입니다.

## 이번 릴리스가 던진 보안 메시지: CVE-2026-15310을 예로 들면

이번 다섯 개 릴리스는 공통 보안 수정이 여럿 들어갔고, 그중 운영에서 체감하기 쉬운 케이스가 CVE-2026-15310입니다. 공지문에는 `zipfile`의 bzip2/LZMA(Zstandard 포함) 압축 해제에서 “작은 압축 멤버로부터 unbounded allocation이 가능”했던 문제를 제한하도록 수정했다고 적혀 있습니다. 또한 `_get_decompressor()`를 monkey-patching해서 third-party decompressor를 끼워 넣었는데 `needs_input`이나 2-argument `decompress()`가 없는 구형 API를 쓰면 여전히 취약할 수 있다는 경고도 같이 있습니다.[^1]

Debian security tracker는 이 CVE를 “crafted zip 파일을 decompress할 때 attacker-controlled size로 메모리를 pre-allocate해 memory exhaustion이 날 수 있다”는 식으로 요약합니다.[^8]

여기서 3.10 EOL의 본질이 드러납니다.

- 3.10.22(최종)에 포함된 CVE는 “마지막으로 받아먹은 패치”입니다.
- 다음 분기에 `zipfile`이든 `tarfile`이든 또 다른 CVE가 나왔을 때, 3.10은 그 순간부터 영구적으로 뒤처집니다.

운영 리스크 관점에서는 “지금 당장 악용된다/안 된다”보다 “패치 경로가 존재하는가”가 더 중요합니다. EOL은 패치 경로를 없애 버립니다.

## 멀티 런타임 업그레이드 정리법: ‘런타임 번들’을 제품처럼 다루기

내가 멀티 런타임에서 수명주기 이벤트를 처리할 때 고정하는 핵심 원칙은 하나입니다.

- 런타임을 “환경”이 아니라 “제품”으로 만듭니다.

여기서 제품이란 다음 산출물을 묶어 한 덩어리로 버전 관리한다는 뜻입니다.

- CPython 소스(또는 vendor 빌드) + 빌드 옵션
- OS base + CA certs
- 번들 라이브러리(OpenSSL/expat 등) 영향 범위
- dependency lock/constraints(가능하면 동일 입력)
- wheelhouse(빌드/다운로드한 wheel 집합)
- 배포 형태별 패키징(container image, lambda layer zip)

이걸 “runtime bundle”이라고 부르면, 서버/배치/CI/람다를 각각 업그레이드하는 대신 runtime bundle을 링으로 굴리고, 각 워크로드는 그 번들을 소비만 하게 바꿀 수 있습니다.

### 링 설계: 카나리를 서비스가 아니라 런타임으로 옮기기

업그레이드 링은 대개 서비스 단위로 설계합니다. 그런데 Python 수명주기 이벤트에서는 런타임이 공통 장애점이 됩니다. 그래서 링을 이렇게 재정의합니다.

- Ring 0: CI에서 runtime bundle을 빌드하고, 테스트/정적분석/보안 스캔까지 통과한 번들만 다음 링으로 올립니다.
- Ring 1: 실제 트래픽/실제 배치 입력을 받는 소수의 워크로드(카나리 서비스 1~2개 + 대표 배치 1개)에 runtime bundle을 적용합니다.
- Ring 2: 동일 번들을 나머지 서비스로 확대합니다.
- Ring 3: 기존 런타임을 retire합니다(이미지 태그/레이어 버전/빌드 캐시 정리까지 포함).

이렇게 하면 “3.10을 쓰는 서비스는 다 업그레이드” 같은 체크리스트가 아니라, “3.10 runtime bundle을 더는 배포하지 않는다”로 종료 조건이 바뀝니다. 종료 조건이 명확해집니다.

### 의존성 호환성: ‘해결(resolution)’과 ‘빌드(build)’를 분리하기

Python minor 업그레이드에서 제일 자주 터지는 것은 dependency resolution 실패가 아니라, 빌드 실패입니다. 특히 C extension이 껴 있으면 “해당 Python 버전 wheel이 아직 없다”거나 “manylinux/ABI 문제”가 더 흔합니다.

그래서 나는 의존성 파이프라인을 두 단계로 분리합니다.

- Resolution 단계: `pyproject.toml`/constraints 입력으로 “설치 가능한 버전 집합”을 먼저 고정합니다.
- Build 단계: 고정된 집합으로 wheelhouse를 만들고(다운로드든 소스 빌드든), 그 wheelhouse를 모든 워크로드에서 재사용합니다.

이때 중요한 운영 포인트는, 업그레이드 링에서 “resolution이 바뀌는가”와 “wheelhouse가 바뀌는가”를 별개 사건으로 취급하는 것입니다.

- resolution이 바뀌면 기능 리스크가 커집니다.
- wheelhouse만 바뀌면(동일 버전 재빌드), 대개는 공급망/빌드 재현성 문제입니다.

수명주기 이벤트 대응에서는 가능하면 “Python만 올리고, resolution은 고정”을 먼저 시도하는 편이 사고가 적었습니다.

## 실제로 돌아가는 정리 시나리오: source-only까지 커버하는 런타임 빌드

3.11/3.12/3.10이 source-only로 가는 흐름은 앞으로 반복될 가능성이 높습니다. Devguide 정의대로라면, security 단계에서는 원칙적으로 binaries가 나오지 않습니다.[^5]

따라서 “우리는 bugfix 단계만 쓸 거라서 괜찮다”는 전략은, 장기적으로는 “우리는 항상 최신 minor로 업그레이드한다”는 전략과 거의 같습니다. 그게 현실적으로 어렵다면, 결국 source-only를 빌드하는 길을 열어둬야 합니다.

아래 예시는 runtime bundle을 만들기 위한 최소 골격입니다.

- CPython 소스는 python.org release 페이지에서 받습니다(보안 릴리스/최종 릴리스가 모두 그 경로로 정리됩니다).[^7]
- SHA-256을 고정해 supply-chain을 최소한으로 방어합니다.
- 이후 애플리케이션은 이 런타임 이미지 위에 올라갑니다.

### 1) runtime 이미지용 Dockerfile (CPython을 소스에서 빌드)

다음 Dockerfile은 “Python을 소스에서 빌드해서 /opt/python에 설치”하는 형태입니다. Debian slim 계열을 가정했지만 핵심은 동일합니다.

```dockerfile
# Dockerfile.runtime
# 목적: source-only 릴리스도 동일한 방식으로 runtime bundle을 만든다.

ARG DEBIAN_VERSION=bookworm
FROM debian:${DEBIAN_VERSION} AS build

ARG PYTHON_VERSION
ARG PYTHON_TARBALL_SHA256

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils \
    build-essential pkg-config \
    libssl-dev zlib1g-dev libbz2-dev liblzma-dev libreadline-dev \
    libsqlite3-dev libffi-dev tk-dev uuid-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp

# python.org 릴리스 tarball을 고정된 해시로 검증
RUN curl -fsSLo Python.tar.xz https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz \
 && echo "${PYTHON_TARBALL_SHA256}  Python.tar.xz" | sha256sum -c -

RUN tar -xJf Python.tar.xz
WORKDIR /tmp/Python-${PYTHON_VERSION}

RUN ./configure \
      --prefix=/opt/python \
      --enable-optimizations \
      --with-lto \
      --with-ensurepip=install \
 && make -j"$(nproc)" \
 && make install

FROM debian:${DEBIAN_VERSION} AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/python /opt/python
ENV PATH="/opt/python/bin:${PATH}"

RUN python -V && python -m pip -V
```

이 방식의 장점은 명확합니다.

- Python이 installer로 나오든 source-only로 나오든 같은 파이프라인을 탑니다.
- 런타임이 만들어지는 순간, 그 결과물은 container digest로 고정돼 재현성이 생깁니다.

단점도 명확합니다.

- 빌드 시간이 늘고 CI 비용이 증가합니다.
- 빌드 툴체인 업데이트가 런타임 공급망의 일부가 됩니다.

그래도 3.10 EOL 같은 이벤트가 오면, “빌드할 수 있다”는 능력 자체가 업그레이드 링의 속도를 결정합니다.

### 2) Python 3.12.15(2026-09-30)로 runtime 이미지 빌드/검증

3.12.15 release 페이지에는 이 릴리스가 security release이며 source-only이고, 3.12.10이 마지막 binary installer 제공 릴리스였다고 적혀 있습니다.[^3]

release 페이지에 SHA-256이 있으니 그 값을 그대로 고정합니다. (예시는 xz tarball 해시를 사용합니다.)[^3]

```bash
export PYTHON_VERSION=3.12.15
export PYTHON_TARBALL_SHA256=c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a

docker build \
  -f Dockerfile.runtime \
  --build-arg PYTHON_VERSION=${PYTHON_VERSION} \
  --build-arg PYTHON_TARBALL_SHA256=${PYTHON_TARBALL_SHA256} \
  -t runtime-python:${PYTHON_VERSION} \
  .

docker run --rm runtime-python:${PYTHON_VERSION} python -V
```

예상 출력은 다음처럼 나옵니다.

```text
Python 3.12.15
```

### 3) Python 3.11.17(2026-10-01)도 동일하게 빌드

3.11.17 release 페이지 역시 security-only, source-only이며 binary installer는 제공되지 않는다고 명시합니다.[^2]

```bash
export PYTHON_VERSION=3.11.17
export PYTHON_TARBALL_SHA256=bfb74ad39efae27cda510f134ab408e00f9992c56851cfc0b1cdb5646da11599

docker build \
  -f Dockerfile.runtime \
  --build-arg PYTHON_VERSION=${PYTHON_VERSION} \
  --build-arg PYTHON_TARBALL_SHA256=${PYTHON_TARBALL_SHA256} \
  -t runtime-python:${PYTHON_VERSION} \
  .

docker run --rm runtime-python:${PYTHON_VERSION} python -V
```

이렇게 runtime을 만들 수 있게 되면, “security-only로 내려간 라인”을 운영에서 계속 쓸지 말지 선택권이 생깁니다. build 불가능이면 선택권이 없습니다.

### 4) 3.10.22는 ‘마지막으로’ 빌드 가능한 기준선으로 남긴다

3.10.22 release 페이지는 2026-10-01 EOL을 경고로 띄우고, “final security release”이며 “더는 security updates를 받지 않는다”고 명시합니다.[^7]

내가 이 상황에서 3.10.22 runtime 이미지를 빌드하는 이유는 딱 하나입니다.

- 업그레이드가 지연될 때, “우리는 최소한 마지막 보안 릴리스까지는 올려둔 상태다”라는 기준선을 만들기 위해서입니다.

이건 해결책이 아니라 “지연 비용을 줄이는 응급처치”입니다. EOL 이후에는 기준선이 더는 올라가지 않습니다.

## 배포 아티팩트 정리: 이미지/배치/람다 레이어를 한 파이프라인으로 묶는 법

런타임 번들을 만들었다면, 이제 워크로드별 아티팩트를 “동일 입력으로” 뽑아야 합니다.

내가 강제하는 규칙은 다음 두 가지입니다.

- 서버/배치/람다 레이어가 같은 dependency 입력(최소한 constraints)을 공유합니다.
- wheelhouse를 중앙 산출물로 두고, 설치는 항상 wheelhouse에서만 합니다(인터넷 설치 금지).

이렇게 하면 링 프로모션이 “코드 + dependency + 런타임” 묶음으로 움직입니다.

### 서버/배치용 application 이미지

```dockerfile
# Dockerfile.app
ARG RUNTIME_IMAGE
FROM ${RUNTIME_IMAGE}

WORKDIR /app

# wheelhouse는 CI에서 만들어 artifact로 보관했다고 가정
COPY wheelhouse/ /wheelhouse/
COPY pyproject.toml README.md /app/
COPY src/ /app/src/

RUN python -m pip install --no-index --find-links=/wheelhouse -e .

CMD ["python", "-m", "my_service"]
```

빌드/실행은 다음처럼 합니다.

```bash
docker build \
  -f Dockerfile.app \
  --build-arg RUNTIME_IMAGE=runtime-python:3.12.15 \
  -t my-service:py312 \
  .

docker run --rm my-service:py312 python -c "import sys; print(sys.version)"
```

이 구조의 핵심은, “업그레이드”가 `RUNTIME_IMAGE` 값만 바꾸는 변화로 축소된다는 점입니다.

- 3.10 EOL 대응: `runtime-python:3.10.22` → `runtime-python:3.12.15` 같은 치환으로 정의할 수 있습니다.
- 3.13 security-only 대응: 3.13을 유지할 거면 3.13.x runtime을 같은 방식으로 계속 빌드하면 됩니다. 3.14로 갈 거면 런타임만 바꾸면 됩니다.

### Lambda layer: ‘런타임과 분리된 site-packages 번들’로 고정하기

Lambda를 zip 배포로 운영하면 대개 layer가 생깁니다. 이때 흔한 실수는 layer를 개발자 노트북에서 만들거나, CI에서 인터넷 설치로 즉석 생성하는 것입니다.

수명주기 이벤트가 오면 그 방식은 바로 부서집니다.

- 빌드 머신의 Python 버전이 drift합니다.
- 같은 dependency 버전이라도 wheel이 다르면 동작이 달라집니다.

그래서 layer도 wheelhouse 입력을 강제합니다.

```bash
# build_layer.sh
set -euo pipefail

PYTHON_TAG="$1"        # 예: 3.12.15
LAYER_DIR="build/layer"
SITE_DIR="${LAYER_DIR}/python"

rm -rf "${LAYER_DIR}"
mkdir -p "${SITE_DIR}"

# runtime container 안에서 layer를 생성한다.
docker run --rm \
  -v "$PWD/wheelhouse:/wheelhouse:ro" \
  -v "$PWD/${LAYER_DIR}:/out" \
  runtime-python:${PYTHON_TAG} \
  bash -lc "python -m pip install --no-index --find-links=/wheelhouse -t /out/python -r /wheelhouse/requirements-layer.txt"

(cd "${LAYER_DIR}" && zip -r9 "../layer-${PYTHON_TAG}.zip" .)

ls -lh "build/layer-${PYTHON_TAG}.zip"
```

이 스크립트는 layer를 만드는 “빌드 환경”을 runtime bundle로 고정합니다. 결국 layer도 런타임 링의 일부가 됩니다.

Lambda 운영 체크리스트는 예전에 [Cloudflare Python Workers를 실서비스로 운영하기 위한 체크리스트](https://daewooki.github.io/posts/cloudflare-python-workers-production-checklist/)에서 별도로 다뤘고, 여기서는 반복하지 않겠습니다. 다만 핵심은 같습니다. runtime을 제품처럼 고정하면 edge/serverless도 upgrade ring에 넣을 수 있습니다.

## 함정과 트레이드오프: ‘업그레이드가 빠를수록 좋다’가 아니다

이번 같은 이벤트에서 흔히 나오는 반응은 “그럼 무조건 최신(3.14)으로 가자”입니다. 실제로 3.14는 아직 bugfix 단계라 binaries 공급이 유지됩니다.[^5]

그런데 멀티 런타임에서는 무조건 최신이 최선이 아닙니다.

### 1) security-only 라인을 계속 쓰는 선택의 비용

3.11/3.12는 security-only지만 각각 2027-10, 2028-10까지 security 지원이 남아 있습니다(PEP 664/PEP 693).[^9]

즉, “지원은 남아 있는데 공급이 source-only”라는 상태가 길게 유지됩니다. 이건 곧 선택지입니다.

- 선택 A: 3.12 security-only를 유지한다 → 자체 빌드 파이프라인이 필요해집니다.
- 선택 B: 3.14 bugfix로 이동한다 → 빌드 파이프라인은 단순해질 수 있지만, minor 업그레이드 리스크(언어/stdlib 변화, dependency 호환성)가 늘어납니다.

둘 중 어느 게 싸냐는 조직의 성격에 따라 다릅니다.

- 플랫폼/인프라 팀이 있고 런타임 빌드/서명/스캔을 체계적으로 할 수 있다면, security-only 유지도 현실적입니다.
- 그런 체계가 없다면, 소스 빌드가 오히려 더 큰 위험(재현 불가, 패치 누락, 빌드 플래그 drift)이 됩니다.

### 2) 3.13 라인의 전환은 ‘일정 확보’ 문제다

3.13.16이 last full maintenance라는 것은 “오늘부터 당장 3.13이 끝났다”는 뜻은 아닙니다. 다만 3.13의 다음 릴리스는 security-only 성격이 되고, binaries 공급이 기대되지 않는 쪽으로 정책이 바뀝니다(Devguide의 security 단계 정의 그대로입니다).[^1]

그래서 3.13을 쓰는 서비스는 다음 중 하나를 고정해야 합니다.

- (1) 3.13을 계속 쓸 건데, 이제부터는 source-only를 빌드해서 먹겠다.
- (2) 3.13을 쓰고 싶었지만, binaries/공급 편의성을 유지하려고 3.14로 옮기겠다.

이 결정이 늦어질수록 손해가 커집니다. 이유는 간단합니다.

- 결정이 늦어지면 “3.10 EOL 대응”과 “3.13 전환 대응”이 서로 얽혀 하나의 대형 프로젝트가 됩니다.
- 결정이 빠르면, 3.10→3.12(또는 3.14) 업그레이드를 먼저 끝내고, 그 다음에 3.13 전략을 분리할 수 있습니다.

### 3) patch 업그레이드(3.12.14→3.12.15)도 운영이 어려워진다

source-only는 patch 업그레이드조차 “런타임 빌드”를 요구합니다. 3.12.15 페이지는 binary installer가 더는 제공되지 않는다고 적고 있습니다.[^3]

이건 실무에서 굉장히 중요한 변화입니다.

- 예전에는 “보안 공지 떴다 → patch만 올리자”가 상대적으로 가벼웠습니다.
- 이제는 patch도 CI 파이프라인, 이미지 재빌드, layer 재생성, 롤아웃까지 전부 태워야 합니다.

따라서 “우리는 EOL만 피하면 된다”가 아니라, security-only 진입 시점부터 운영 비용 구조가 바뀐다고 보는 게 맞습니다.

예전에 [OpenSSL 3.0 EOL 이후 런타임을 안전하게 퇴역시키는 운영 설계](https://daewooki.github.io/posts/retire-openssl-3-0-safely/)에서 했던 얘기와 결론이 비슷해집니다. 런타임을 늦게 치우면, 결국 아티팩트 체인 전체가 늦게 따라옵니다.

## 반론과 회의론: 왜 굳이 지금 움직이나

현장에서 실제로 듣는 반론은 대략 다음 세 가지입니다.

### “3.10은 내부망 서비스라 괜찮다”

내부망이라는 말은 대개 다음 두 가정에 기대고 있습니다.

- 외부 입력이 없다.
- 취약점이 있어도 공격자가 없다.

그런데 `zipfile` 같은 이슈는 내부 입력에서도 자주 터집니다. 배치 파이프라인에서 외부 파트너 파일을 받거나, S3에 올라온 데이터를 처리하거나, 심지어 개발자가 올린 artifact를 처리하는 순간 경계가 무너집니다. CVE-2026-15310은 crafted zip 파일로 memory exhaustion이 가능하다는 점을 분명히 합니다.[^8]

EOL 이후에는 이런 유형이 또 나와도 패치가 없습니다. 내부망 여부와 별개로 “수정 가능한가”가 중요합니다.

### “우리는 어차피 distro Python을 쓰니 upstream EOL과 무관하다”

distro가 backport를 해주는 경우는 분명히 있습니다. 다만 이건 운영 관점에서는 ‘변수’입니다.

- backport 범위/속도는 배포판 정책에 종속됩니다.
- 컨테이너/서버리스/CI 등 워크로드마다 distro가 다르면, backport 전략은 일관성을 잃습니다.

이번 공지에서처럼 python.org가 source-only로 전환될 때, 오히려 조직이 “어느 공급망을 신뢰할지”를 더 명시적으로 결정해야 합니다.

### “3.13은 아직 지원인데 왜 움직이나”

지원 종료가 아니라 공급 종료(또는 공급 형태 변화)가 운영을 흔듭니다. security 단계의 정의 자체가 “no more binaries”입니다.[^5]

3.13이 security-only로 내려가면 “업그레이드를 안 해도 된다”가 아니라 “업그레이드 방식이 바뀐다”가 됩니다. 그 방식 전환을 작은 단위로 끝내려면, 3.10 EOL 대응과 섞기 전에 처리하는 게 싸게 먹힙니다.

## 앞으로 지켜볼 것: 릴리스 정책은 ‘예외’를 만든다

이번 묶음 릴리스 공지에는 운영 관점에서 주목할 만한 정보가 더 있습니다.

- 3.10.22는 마지막 릴리스이고, 3.11/3.12도 source-only라는 사실이 공지에 명시돼 있습니다.[^1]
- 3.14.8은 expedited security release로 소개됩니다. 긴급 릴리스가 나온다는 것은, 보안 이슈는 cadence를 깨고도 나온다는 뜻입니다.[^4]

결국 “보안 공지는 정기적으로 온다”는 가정이 깨집니다. security-only로 내려간 라인은 원래도 “as-needed”인데, bugfix 라인에서도 expedited 릴리스가 나오면 운영은 더더욱 ‘상시 대비’가 됩니다.

또 하나는 지원 정책의 단서입니다.

- PEP 602 주석에 따르면 3.13부터 full support가 2년으로 늘었습니다.[^6]

이 정책 변화가 정착되면, 앞으로도 “N 라인이 2년 차가 되는 시점”에 비슷한 강제 이벤트가 반복될 가능성이 높습니다. 멀티 런타임 조직은 이 이벤트를 프로젝트가 아니라 반복 작업으로 설계해야 합니다.

## 지금 할 수 있는 일: 3개의 체크포인트로 끝내기

이 글을 읽는 시점(2026-10-08 KST)에서, 이미 3.10은 2026-10-01부로 EOL입니다.[^7]

그래서 실행 계획은 “완벽한 마이그레이션”이 아니라 체크포인트 기반으로 잡는 게 맞습니다.

### 체크포인트 1: 3.10은 전 서비스에서 ‘더는 배포되지 않게’ 만든다

- 런타임 번들 목록에서 3.10 라인을 deprecated로 표시합니다.
- 신규 배포 파이프라인은 3.10 artifact(이미지/레이어)를 거부하게 합니다.
- 남아 있는 3.10 워크로드는 Ring 1부터 3.12 또는 3.14로 옮깁니다.

여기서 성공 기준은 “코드 변경 0”이 아니라 “3.10 runtime bundle이 프로덕션에 더는 올라가지 않는다”입니다.

### 체크포인트 2: 3.13은 ‘계속 쓸지/올릴지’를 공급망 기준으로 결정한다

- 3.13을 유지한다면: source-only 빌드 파이프라인을 공식화합니다(해시 고정, 서명, 스캔, SBOM).
- 3.14로 옮긴다면: 3.13과 3.14를 한동안 병행하는 링 전략을 먼저 세웁니다(카나리에서 3.14를 검증 후 확대).

여기서 성공 기준은 “3.13.16으로 올렸다”가 아니라 “3.13 security-only 이후에도 patch 적용이 가능한 경로를 확보했다”입니다.[^1]

### 체크포인트 3: CI/배치/람다 레이어를 runtime bundle로 수렴시킨다

- CI에서 `setup-python` 같은 외부 공급을 그대로 쓰더라도, 최소한 릴리스가 source-only로 전환될 때 깨질 수 있다는 전제를 둡니다.
- 배치와 서버의 dependency 입력을 통합하거나, 최소한 constraints를 공유합니다.
- Lambda layer는 wheelhouse 기반으로, runtime container 안에서 생성합니다.

이렇게 해두면 다음 수명주기 이벤트에서 “업그레이드 대상이 12개 서비스”가 아니라 “runtime bundle 2개(현재/다음)”로 축약됩니다.

결론적으로, 2026-10-01의 동시 릴리스는 기능 변화보다 운영 체계의 변화를 요구합니다. 3.10 EOL은 즉시 일정 확정을 강제하고, 3.13의 security-only 전환은 런타임 공급망을 자체 통제할지 여부를 결정하게 만듭니다. 멀티 런타임 조직에서는 업그레이드 링의 단위를 서비스가 아니라 런타임 번들로 옮기는 쪽이 일관된 비용으로 반복 가능한 답이 됩니다.

## 참고 자료

- [Python 3.10.22, 3.11.17, 3.12.15, 3.13.16 and 3.14.8 are now available!](https://blog.python.org/2026/10/python-31022-31117/)
- [Python 3.10.22 릴리스 노트](https://www.python.org/downloads/release/python-31022/)
- [Python 3.11.17 릴리스 노트](https://www.python.org/downloads/release/python-31117/)
- [Python 3.12.15 릴리스 노트](https://www.python.org/downloads/release/python-31215/)
- [Python 3.13.16 릴리스 노트](https://www.python.org/downloads/release/python-31316/)
- [Python 3.14.8 릴리스 노트](https://www.python.org/downloads/release/python-3148/)
- [PEP 619 – Python 3.10 Release Schedule](https://peps.python.org/pep-0619/)
- [PEP 664 – Python 3.11 Release Schedule](https://peps.python.org/pep-0664/)
- [PEP 693 – Python 3.12 Release Schedule](https://peps.python.org/pep-0693/)
- [PEP 719 – Python 3.13 Release Schedule](https://peps.python.org/pep-0719/)
- [PEP 745 – Python 3.14 Release Schedule](https://peps.python.org/pep-0745/)
- [PEP 602 – Annual Release Cycle for Python](https://peps.python.org/pep-0602/)
- [Python Developer’s Guide: Status of Python versions](https://devguide.python.org/versions/)
- [Debian security tracker의 CVE-2026-15310 항목](https://security-tracker.debian.org/tracker/CVE-2026-15310)
- [CPython 이슈: Memory exhaustion via crafted zip file (gh-156002)](https://github.com/python/cpython/issues/156002)
- [OpenSSL 3.0 EOL 이후 런타임을 안전하게 퇴역시키는 운영 설계](https://daewooki.github.io/posts/retire-openssl-3-0-safely/)
- [Cloudflare Python Workers를 실서비스로 운영하기 위한 체크리스트](https://daewooki.github.io/posts/cloudflare-python-workers-production-checklist/)

[^1]: <https://blog.python.org/2026/10/python-31022-31117/>
[^2]: <https://www.python.org/downloads/release/python-31117/>
[^3]: <https://www.python.org/downloads/release/python-31215/>
[^4]: <https://www.python.org/downloads/release/python-3148/>
[^5]: <https://devguide.python.org/versions/?where=caellabwiki>
[^6]: <https://github.com/python/peps/blob/main/peps/pep-0602.rst>
[^7]: <https://www.python.org/downloads/release/python-31022/>
[^8]: <https://security-tracker.debian.org/tracker/CVE-2026-15310>
[^9]: <https://peps.python.org/pep-0664/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
