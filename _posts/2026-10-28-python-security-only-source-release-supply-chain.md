---
title: "Python security-only 릴리스에서 공급망이 흔들리는 지점"
description: "Python 3.13.18처럼 source-only 보안 릴리스가 떴을 때, 런타임 공급·서명 검증·패치 리드타임을 줄이는 실전 설계를 정리합니다."
date: 2026-10-28 11:00:39 +0900
categories: ["Languages", "Python"]
tags: ["python", "security-release", "supply-chain", "sigstore", "reproducible-builds", "ci-cd"]
render_with_liquid: false
---

## Python 3.13.18이 던지는 신호: 보안 릴리스인데 “No installers”

2026-10-25에 공개된 Python 3.13.18은 3.13 series의 security bugfix 릴리스로 공지됐고, 릴리스 페이지에 **No installers**가 명시되어 있습니다. 릴리스 설명은 “compromised eMudhra intermediate CA keys” 대응을 위해 `ssl` module이 해당 intermediate CA key들을 block 한다고 적고, `pip`를 포함한 TLS 연결이 OS trust store 업데이트가 늦더라도 마지막 방어선으로 보호될 수 있다는 취지로 적혀 있습니다. 이는 전형적인 “ecosystem 전체가 OS trust store 업데이트 타이밍에 종속되는” 상황에서, 언어 런타임이 임시로 전면에 나서는 케이스입니다.[^1]

이 릴리스에서 중요한 건 CVE 목록 자체만이 아닙니다. 릴리스 artifact가 “source tarball + 서명/검증 자료 + SBOM” 중심으로 제공되고(릴리스 페이지의 Files 섹션에 Sigstore, SBOM, GPG가 같이 노출), Windows/macOS installer가 빠진 상태로 보안 릴리스가 “정상 동작”했다는 점이 조직의 Python 공급 체계가 어디까지 자동화돼 있는지, 어디서부터 수동 개입이 필요한지, 무엇이 암묵적으로 python.org installer에 기대고 있었는지를 드러냅니다.[^1]

내가 운영 관점에서 더 크게 보는 변화는 이것입니다.

- “보안 패치가 떴는데 바이너리가 없다”는 상황이 예외가 아니라 lifecycle 상의 규칙이 됐다.
- 조직이 Python을 어떻게 공급하느냐(런타임 이미지/베이스 OS/pyenv/CI toolcache)가 보안 리드타임을 결정한다.
- 이제는 소스 tarball을 **신뢰 가능한 방식으로** 가져와서 **재현 가능한 방식으로** 빌드하고, 그 결과물을 **서명/검증 가능한 내부 artifact**로 바꿔 공급하는 쪽이 기본값이 된다.

이 글의 전제는 명확합니다. “왜 어떤 보안 릴리스는 installer/wheel이 없고 source-only인가”를 이해한 다음, (1) 조직 내 Python 공급 전략, (2) 재현 가능한 빌드/서명 검증, (3) 패치 적용 리드타임 단축을 기술적으로 묶어야 합니다.

## 왜 source-only인가: lifecycle이 security phase로 들어가면 ‘binaries stop’

CPython의 lifecycle 문서에서 핵심 문장은 단순합니다. security 단계에서는 “only security fixes are accepted and no more binaries are released. New source-only versions can be released as needed.”라고 정리돼 있습니다. 여기서 “binaries stop”이 정책입니다.[^2]

이건 PEP 602의 연간 릴리스 사이클 설명과도 일관됩니다. 일정 기간 bugfix 릴리스(대략 2년)를 제공한 뒤, 그 이후 수년은 security update만 제공하고 source-only 릴리스를 필요 시 배포한다는 구조입니다.[^3]

3.13에 대해서는 PEP 719가 훨씬 직접적으로 이야기합니다.

- 3.13.16이 “Final regular bugfix release with binary installers”로 명시돼 있고
- 그 이후 “Source-only security fix releases” 구간에 3.13.17, 3.13.18이 배치돼 있습니다.[^4]

여기서 3.13.17이 “exceptionally with binary installers”로 표시돼 있는 점도 의미가 있습니다. 즉, installer 제공은 규칙이 아니라 예외로 바뀌었습니다.[^4]

또 하나. Python 3.13.18 릴리스 페이지에는 “source-only form until October 2028”이라는 문구가 보이는데, PEP 719는 3.13.0 final(2024-10-07)로부터 5년(대략 2029-10)까지 security 업데이트가 이어진다고 적습니다. 같은 python.org 공식 문서 사이에서도 표기 차이가 존재합니다. 이런 불일치는 운영 자동화를 설계할 때 “정확한 end date에 맞춘 단발성 로직”을 만들면 안 된다는 신호로 봅니다. 정책 문구를 파싱해 조건 분기하는 순간부터 깨지기 쉽습니다.[^1]

source-only의 이유를 실무적으로 풀면 다음 트레이드오프가 있습니다.

1) 빌드/릴리스 인력과 시간의 제약
- Windows installer, macOS installer는 단순히 `./configure && make`가 아닙니다. signing, notarization(플랫폼별 요구), 다양한 환경에서의 QA가 따라옵니다.
- security-only 릴리스는 “필요할 때 즉시”가 중요하고, 이는 “매번 모든 바이너리 채널을 같은 품질로 찍어낸다”와 충돌합니다.

2) downstream 책임 분리
- security-only phase에서 upstream이 모든 플랫폼 바이너리를 계속 제공하면, downstream(배포판, 사내 이미지, CI toolchain)이 ‘업스트림 바이너리’에 더 오래 종속됩니다.
- 반대로 source-only로 전환하면, downstream은 “우리가 실제로 운영하는 runtime”에 책임을 지게 됩니다. 컨테이너/서버 런타임 중심 조직에서는 오히려 이게 현실과 맞습니다.

3) binary-only에만 적용되는 보안 수정은 source-only 채널에 실리지 않을 수 있음
- Python devguide security policy는 “binary installer에만 영향을 주는 security fix는 source-only release stream에 publish되지 않는다”고 명시합니다. 즉, source-only 채널은 본질적으로 ‘소스 기반 소비자’를 위한 채널입니다.[^5]

이쯤에서 결론은 단순합니다. security-only phase에 들어간 Python을 계속 쓸 거라면, 조직은 python.org installer 다운로드를 런타임 공급의 핵심 경로로 두면 안 됩니다.

## CI/배포가 흔들리는 지점: “installer가 없어서”가 아니라 “암묵적 의존성” 때문에

source-only 자체는 문제가 아닙니다. 문제는 조직 내부 어딘가에 다음 같은 암묵적 의존성이 숨어 있다는 점입니다.

### 1) Windows/macOS에서 python.org installer를 직접 받는 스텝
가장 흔한 패턴은 이런 형태입니다.

- Windows CI에서 `python-3.13.18-amd64.exe` 같은 artifact를 받는다
- macOS에서 python.org pkg를 받아 설치한다

security-only phase에서는 이 artifact가 사라집니다. 그러면 파이프라인은 “버전이 없어서”가 아니라 “채널이 바뀌었는데도 기존 채널을 하드코딩했기 때문에” 멈춥니다.[^1]

### 2) GitHub Actions: setup-python은 ‘다른 공급망’이지만, 역시 흔들릴 수 있음
`actions/setup-python`은 python.org에서 installer를 받아 설치하는 방식만 쓰지 않습니다. 문서에 따르면, 이 액션이 쓰는 Python 버전은 `actions/python-versions`(python-versions)에서 생성되며 macOS/Ubuntu 이미지는 source code로부터 빌드된 패키지, Windows는 installation executable을 사용한다고 설명합니다.[^6]

여기서 포인트는 두 가지입니다.

- setup-python이 “python.org installer 유무”에 즉시 종속되진 않더라도, 그 upstream(빌드 파이프라인)은 결국 CPython source tarball과 릴리스 정보를 필요로 합니다.
- 사내 self-hosted runner에서 네트워크 제약이 있거나, toolcache 미리 적재 전략이 없다면, patch 버전이 급히 올라올 때 대응이 느려질 수 있습니다.

setup-python이 제공하는 `mirror` 기능은 이 문제를 정면으로 다룹니다. `versions-manifest.json`과 tarball을 내부 mirror로 제공할 수 있게 설계돼 있습니다. 보안 릴리스 대응 시간을 줄이려면 “우리의 Python 공급 채널”을 setup-python까지 포함해 통제 가능한 경로로 만들어야 합니다.[^6]

### 3) 컨테이너는 오히려 강점이 될 수 있다: official python image는 source tarball 기반
Docker Official Image인 `python`은 upstream(CPython)과 동일 조직이 제공하는 건 아니지만, 운영 현실에서 사실상 표준 베이스 이미지로 많이 쓰입니다. 이 이미지의 Dockerfile은 CPython tarball을 python.org FTP에서 다운로드하고, SHA-256을 검증하고, `.asc` 서명을 받아 GPG로 verify한 뒤 빌드합니다. 3.13/bookworm Dockerfile에 3.13.18이 반영된 상태가 그대로 노출돼 있습니다.[^7]

즉, python.org installer가 없어도 컨테이너 공급 경로는 그대로 돌아갑니다. 다만 이건 “누군가가 이미 source-only를 받아 빌드해 OCI image로 재포장해 주는” 경로가 있다는 의미입니다. 내 조직이 이 경로를 신뢰할지, 내부에서 동일한 방식으로 재현할지, 혹은 둘을 병행해 canary 검증에 쓸지를 결정해야 합니다.

그리고 실제로 Docker Hub 태그 목록에는 `python:3.13.18-alpine3.24` 같은 태그가 관찰됩니다. source-only라도 컨테이너 artifact는 별도 공급망에서 계속 생성될 수 있다는 증거입니다.[^8]

### 4) “wheel이 없어서”는 대체로 착각이지만, CI는 여전히 흔들린다
보안 릴리스가 source-only라고 해서 PyPI wheel이 같이 사라지는 건 아닙니다. 대부분의 패키지는 Python patch 버전(3.13.17 → 3.13.18) 차이로 wheel을 새로 올리지 않습니다. ABI는 minor(3.13) 기준이기 때문입니다.

그럼에도 CI가 흔들리는 케이스는 많습니다.

- 런타임 자체를 설치 못 해서 venv 생성이 막힌다.
- base image/runner toolcache가 새 patch를 아직 제공하지 않아 테스트 matrix가 멈춘다.
- 조직 정책이 “릴리스 페이지에서 제공되는 installer 링크가 존재해야만 업그레이드한다” 같은 체크를 갖고 있어, 링크 부재를 실패로 처리한다.

결국 문제는 artifact 타입이 아니라, 공급망 설계가 “source-first”를 전제로 했는지 여부입니다.

## 조직 내 Python 공급 전략: 3가지 경로를 분리해야 리드타임이 줄어든다

조직에서 Python을 공급하는 경로는 크게 3개로 분리하는 편이 안정적이었습니다.

### A) Production runtime: OCI base image를 최상위 공급 단위로 둔다
서버/컨테이너 기반 조직이라면, Production 런타임의 배포 단위는 “OS 패키지”나 “python.org installer”가 아니라 OCI image여야 합니다.

- 애플리케이션 이미지는 `FROM <org-python-runtime>:3.13.18-...`처럼 런타임 이미지를 상속한다.
- 런타임 이미지는 CPython 소스 릴리스가 뜨면 자동으로 새 tag를 만들고, SBOM/서명/attestation까지 붙인다.
- 앱 팀은 런타임 업그레이드를 “Docker base digest 변경”으로만 소비한다.

이렇게 분리하면, 보안 릴리스 대응에서 가장 비싼 작업(빌드/검증/서명)을 중앙에서 한 번 하고, 수백 개 서비스는 base image bump로 흡수합니다.

Docker Official Image가 실제로 CPython tarball을 받아 SHA-256 + GPG verify 후 빌드하는 방식은 좋은 레퍼런스입니다. internal runtime image도 이 패턴을 그대로 가져오면 됩니다.[^7]

### B) CI runtime: toolcache를 ‘다운로드’가 아니라 ‘artifact’로 취급한다
CI에서 Python 설치는 흔히 “필요하면 받아서 깐다”로 취급됩니다. security-only phase로 넘어가면 이 접근이 흔들립니다.

- 네트워크 장애/레이트리밋/미러 정책에 영향받는다.
- 소스 릴리스가 떴는데 toolcache에 반영되기까지 시간이 걸릴 수 있다.

`actions/setup-python`은 “다운로드 가능한 Python 버전은 GitHub Releases(actions/python-versions)에 있고, 필요하면 mirror를 둘 수 있다”는 형태로 공급망을 이미 모델링하고 있습니다. 이 모델을 그대로 받아들이고, 내부 mirror(사내 GitHub Enterprise, Artifactory, 단순 Nginx static)로 toolcache artifact를 고정해 두는 편이 운영 리드타임이 짧았습니다.[^6]

### C) Developer workstation: pyenv(소스 빌드) + 별도 배포판(바이너리)로 양분한다
개발자 노트북은 Production과 조건이 다릅니다.

- 빠른 설치가 중요하다.
- OS별 컴파일 툴체인 차이가 크다.

여기서 나는 두 갈래를 같이 둡니다.

1) pyenv (source build)
- installer 유무와 무관하게 source tarball만 있으면 설치할 수 있습니다.
- pyenv는 기본적으로 소스에서 빌드한다는 점을 문서에 명시하고 있습니다.[^9]

2) uv 같은 별도 배포판 기반(바이너리)
- uv 문서는 “Python does not publish official distributable binaries. As such, uv uses distributions from … python-build-standalone”라고 못 박습니다. 즉, python.org installer에 기대지 않는 “별도 공급망”입니다.[^10]

이 경로는 보안 릴리스가 source-only로 나와도 개발자의 설치/업데이트 경험이 흔들리지 않는 장점이 있습니다. 대신 이건 “우리가 신뢰하는 upstream이 CPython이 아니라 Astral 배포판이 된다”는 의미이기도 해서, 조직의 threat model에 따라 선택이 갈립니다.

여기서 중요한 건 무엇을 쓰느냐가 아니라, **공급 경로를 하나로 몰지 않는 것**입니다. Production은 internal OCI image, CI는 내부 toolcache, 개발자는 pyenv/uv 중 선택. 이 분리가 돼 있으면 source-only 보안 릴리스가 떠도 한 경로가 흔들릴 때 다른 경로로 완충할 수 있습니다.

## 서명 검증과 재현 가능한 빌드: “소스를 받았다”에서 끝내지 않는다

source-only 릴리스가 기본이 되면, 운영의 핵심은 “다운로드”가 아니라 “검증된 입력으로 빌드했다”를 증명하는 쪽으로 이동합니다.

### 1) CPython 릴리스 artifact는 Sigstore 서명을 제공한다
Python.org의 Sigstore 안내는 다음을 명확히 합니다.

- CPython 릴리스 artifact는 `.sigstore` bundle을 제공한다.
- 검증은 “artifact + bundle”을 다운받고, release manager identity(email)와 OIDC issuer를 알고 있어야 한다.
- 3.13 release manager는 `thomas@python.org`, issuer는 `https://accounts.google.com`로 표에 정리돼 있다.
- `python -m sigstore verify identity ...`로 검증하며 성공 시 `OK: ...`가 출력된다.

이 가이드는 python.org가 공식적으로 “다운스트림 소비자(consumer)”의 검증 절차를 문서화한 것입니다.[^11]

3.13.18 릴리스 페이지도 artifact 테이블에서 `.sigstore`와 SBOM(SPDX), GPG(SIG), SHA-256를 같이 제공합니다. “source-only라서 검증 자료가 없다”가 아니라, 오히려 검증 재료는 더 구조화되어 있습니다.[^1]

### 2) OpenPGP(GPG)도 여전히 쓸 수 있지만, 장기적으로는 Sigstore로 수렴한다
python.org 다운로드 페이지는 “3.11.0/3.10.7/3.9.14부터 Sigstore로 서명되며, 3.14부터는 OpenPGP를 drop했다”는 흐름을 설명하면서 PEP 761을 참고로 제시합니다.[^12]

즉, 3.13 같은 버전에서는 GPG와 Sigstore가 같이 존재하지만, 운영 자동화는 Sigstore 중심으로 재편하는 게 자연스럽습니다. GPG key 관리와 keyserver 신뢰 문제를 release manager 개인에게 오래 부담시키는 게 비효율이라는 점이 PEP 761의 동기에서 명시됩니다.[^13]

### 3) 재현 가능한 빌드의 현실: “bit-for-bit 동일”보다 “입력/과정/출력을 추적”이 먼저다
CPython을 완전히 reproducible하게 만드는 건 생각보다 어렵습니다.

- 컴파일러/링커 버전, PGO profile, LTO, system library(OpenSSL 등) 차이가 결과물을 바꿉니다.
- 빌드 경로가 debug symbol에 들어가거나, 빌드 시간이 embed되는 요소가 있을 수 있습니다.

그래서 내가 택하는 순서는 이렇습니다.

1) 입력을 고정한다: tarball + Sigstore bundle + SHA-256
2) 빌드 환경을 고정한다: 빌드 컨테이너(이미지 digest pin)
3) 출력에 서명한다: OCI image signing(cosign) 또는 내부 artifact signing
4) 추적 가능하게 남긴다: SBOM + provenance(빌드 로그/commit/tag)

이 흐름은 LLM 보안에서 “trust boundary를 명시적으로 설계해야 한다”는 결론과 구조가 닮아 있습니다. 런타임 공급망에서도 trust boundary가 흐려지면, 누가 무엇을 신뢰해야 하는지가 모호해지고 결국 리드타임이 늘어납니다. (관련 맥락은 예전에 정리한 글에서 trust boundary 관점만 참고했습니다: [프롬프트 인젝션은 trust boundary를 설계하는 문제다](https://daewooki.github.io/posts/trust-boundary-2026-6-llm-guardrail-1/))

## 실전: Python 3.13.18 source tarball을 검증하고 내부 런타임으로 공급하기

아래 예시는 “2026-10-25에 3.13.18이 source-only로 떴다”는 상황을 2026-10-28(오늘 KST) 기준으로 점검하는 목적에 맞췄습니다. 핵심은 2단계입니다.

- 1단계: python.org에서 내려받는 입력을 검증한다(Sigstore + SHA-256)
- 2단계: 검증된 입력을 같은 빌드 환경에서 반복 가능하게 빌드한다(컨테이너 빌드)

### 디렉터리 레이아웃

```text
cpython-31318/
  scripts/
    fetch_verify.sh
  docker/
    Dockerfile
  Makefile
```

### 1) 입력 검증 스크립트 (Sigstore + SHA-256)

`scripts/fetch_verify.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

PYVER="3.13.18"
BASE="https://www.python.org/ftp/python/${PYVER}/"
TARBALL="Python-${PYVER}.tar.xz"
BUNDLE="${TARBALL}.sigstore"

# Python 3.13.18 릴리스 페이지에 올라온 SHA-256 (XZ compressed source tarball)
# abb0102e6d4ae027509bcb82327d9dd85515b44a3ba8ad538cfc5e9847029f68
SHA256="abb0102e6d4ae027509bcb82327d9dd85515b44a3ba8ad538cfc5e9847029f68"

# Sigstore 안내 문서의 3.13 release manager identity / issuer
CERT_IDENTITY="thomas@python.org"
CERT_OIDC_ISSUER="https://accounts.google.com"

mkdir -p dist
cd dist

curl -fL -o "${TARBALL}" "${BASE}${TARBALL}"
curl -fL -o "${BUNDLE}"  "${BASE}${BUNDLE}"

echo "${SHA256} *${TARBALL}" | sha256sum -c -

# verifier는 별도의 Python이 필요합니다.
# 조직에서는 verifier 자체를 고정된 컨테이너(예: internal "verifier" image)로 제공하는 편이 안전합니다.
python -m pip install --disable-pip-version-check --no-cache-dir -q sigstore
python -m sigstore verify identity \
  --bundle "${BUNDLE}" \
  --cert-identity "${CERT_IDENTITY}" \
  --cert-oidc-issuer "${CERT_OIDC_ISSUER}" \
  "${TARBALL}"

# 예상 출력(핵심): OK: Python-3.13.18.tar.xz
```

이 스크립트가 의존하는 사실은 모두 python.org 공식 문서에 있습니다.

- Sigstore 검증은 “artifact + `.sigstore` bundle”을 필요로 한다[^11]
- 3.13 release manager identity/issuer 표가 문서에 제공된다[^11]
- 검증 명령은 `python -m sigstore verify identity ...` 형태이며, 성공 시 `OK: ...`가 출력된다[^11]

여기서 주의할 점은 부트스트랩입니다. “Sigstore를 검증하려면 Python이 필요하다”는 역설이 생깁니다. 그래서 verifier는 다음 중 하나로 분리하는 편이 낫습니다.

- 별도의 verifier 이미지(예: `python:3.15-slim`에 sigstore preinstall)를 고정해 두고 항상 그걸로 검증한다.
- Sigstore 문서가 권장하는 것처럼 standalone binary로 `cosign`을 사용한다.[^11]

### 2) 빌드/패키징: 내부 OCI runtime image로 만든다

컨테이너 기반 운영에서는 가장 빠른 공급 단위가 OCI image입니다. 아래 Dockerfile은 “검증된 tarball을 받아서 빌드한 Python 3.13.18 런타임”을 만드는 예시입니다.

`docker/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1

# verifier/build toolchain을 별도로 고정합니다.
# 여기서는 예시로 python:3.15-slim을 쓰지만, 조직에서는 digest pin을 권합니다.
FROM python:3.15-slim AS verifier
RUN python -m pip install --no-cache-dir sigstore

FROM debian:bookworm-slim AS build

ARG PYVER=3.13.18
ARG CERT_IDENTITY=thomas@python.org
ARG CERT_OIDC_ISSUER=https://accounts.google.com
ARG PY_SHA256=abb0102e6d4ae027509bcb82327d9dd85515b44a3ba8ad538cfc5e9847029f68

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils \
    build-essential pkg-config \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
    libffi-dev liblzma-dev tk-dev uuid-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# 1) 소스 + bundle 다운로드
RUN curl -fL -o Python.tar.xz "https://www.python.org/ftp/python/${PYVER}/Python-${PYVER}.tar.xz" \
 && curl -fL -o Python.tar.xz.sigstore "https://www.python.org/ftp/python/${PYVER}/Python-${PYVER}.tar.xz.sigstore" \
 && echo "${PY_SHA256} *Python.tar.xz" | sha256sum -c -

# 2) Sigstore 검증(검증기는 별도 stage에서 가져옵니다)
COPY --from=verifier /usr/local/bin/python /usr/local/bin/python
COPY --from=verifier /usr/local/lib/python3.15 /usr/local/lib/python3.15
RUN python -m sigstore verify identity \
  --bundle Python.tar.xz.sigstore \
  --cert-identity "${CERT_IDENTITY}" \
  --cert-oidc-issuer "${CERT_OIDC_ISSUER}" \
  Python.tar.xz

# 3) 빌드
RUN mkdir -p /usr/src/python \
 && tar -xJf Python.tar.xz -C /usr/src/python --strip-components=1

WORKDIR /usr/src/python

# 운영에서는 옵션을 표준화해야 합니다.
# --enable-optimizations(PGO) 는 빌드 시간이 늘어나므로 조직 사정에 맞춰 고정합니다.
RUN ./configure \
      --prefix=/opt/python/${PYVER} \
      --enable-optimizations \
      --with-ensurepip \
 && make -j"$(nproc)" \
 && make install

# 4) 런타임 스테이지
FROM debian:bookworm-slim AS runtime
ARG PYVER=3.13.18

# 런타임 의존성은 build stage와 분리합니다.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 zlib1g libbz2-1.0 libreadline8 libsqlite3-0 libffi8 liblzma5 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/python/${PYVER} /opt/python/${PYVER}

ENV PATH="/opt/python/${PYVER}/bin:${PATH}"

# smoke test
RUN python3 -c "import sys; print(sys.version_info)"
# 예상 출력(결정적 부분): sys.version_info(major=3, minor=13, micro=18, releaselevel='final', serial=0)

CMD ["python3", "-V"]
```

이 접근은 docker-library/python이 실제로 하고 있는 것과 같은 철학입니다.

- 입력을 python.org FTP에서 받고
- SHA-256을 검증하고
- (그쪽은 `.asc` + GPG로) 서명을 검증한 다음
- 빌드 옵션을 고정해 이미지를 생성합니다.[^7]

내부 공급망을 만들 때도 이 구조가 가장 이해하기 쉽고 audit이 쉽습니다.

### 3) 실행 명령

```bash
# 1) 로컬에서 입력 검증(개발/검증용)
./scripts/fetch_verify.sh

# 2) OCI image 빌드
docker build -f docker/Dockerfile -t org-python:3.13.18 .

# 3) 확인
docker run --rm org-python:3.13.18
# 예상 출력(결정적 부분): Python 3.13.18
```

## 패치 적용 리드타임을 줄이는 방법: 기술과 프로세스를 분리하지 않는다

source-only 보안 릴리스에서 리드타임을 줄이려면, “보안팀의 SLA”나 “개발팀의 의지”만으로는 부족합니다. 공급망의 병목이 어디인지 드러내고, 그 병목을 자동화해야 합니다.

### 1) 모니터링 신호를 ‘릴리스 페이지’가 아니라 ‘채널’로 본다
python.org는 source release 목록 페이지에서 안정 릴리스들의 source tarball 링크를 제공합니다. 이런 목록 채널이 꾸준히 유지되면, 내부 자동화는 HTML 파싱 대신 “정해진 소스 채널”에 의존할 수 있습니다.[^14]

추가로, 문서 버전 목록(`python.org/doc/versions/`)은 “어떤 버전이 언제 릴리스됐는지”를 확정적으로 제공하는 인덱스 역할을 합니다. 자동화에서 “최신 patch”를 찾는 로직을 짤 때, 특정 페이지 하나에 의존하면 깨집니다. 채널을 2~3개로 중복해두고(릴리스 페이지, source releases 인덱스, 문서 버전 인덱스), 서로 교차 검증하는 편이 안정적이었습니다.[^15]

### 2) 중앙 런타임 빌드 파이프라인과 앱 파이프라인을 완전히 분리한다
보안 릴리스 대응에서 흔히 하는 실수는 “각 서비스 repo에서 알아서 base image를 올리게 하는 것”입니다.

- 그러면 팀마다 대응 시간이 갈립니다.
- 빌드 옵션이 제각각이 됩니다.
- 검증/서명 방식이 균일하지 않습니다.

반대로 중앙 런타임 파이프라인이 다음을 제공하면, 앱 팀은 PR 하나로 끝납니다.

- `org/python-runtime:3.13.18-bookworm` 같은 표준 런타임 이미지
- 해당 이미지의 SBOM과 provenance
- 이미지 서명(예: cosign)과 검증 정책

### 3) 검증을 “사후 감사”가 아니라 “빌드의 전제조건”으로 둔다
Sigstore 검증은 빌드가 시작되기 전에 해야 합니다. “다운로드는 빨리 하고, 검증은 나중에”는 supply chain 사고에서 항상 패배하는 패턴입니다.

Sigstore 가이드는 `.sigstore` bundle 기반 검증이 offline 중심으로 설계돼 있음을 언급합니다. 즉, 검증은 CI에서 충분히 빠르게 수행할 수 있고, 네트워크 의존성을 최소화할 수 있습니다.[^11]

### 4) 설치 채널이 여러 개인 환경에서는 ‘우선순위’를 고정한다
실무에서는 같은 Python minor 버전이라도 출처가 섞입니다.

- OS 패키지 Python
- pyenv로 빌드한 Python
- uv가 제공하는 managed Python
- 컨테이너 내부 Python

이 상태에서 “3.13.18로 올렸다”는 말이 무의미해집니다. 어떤 환경이 어떤 채널을 쓰는지 분류하지 않으면 incident가 생깁니다.

내 기준의 우선순위는 명확합니다.

- Production: internal OCI runtime만 허용
- CI: setup-python은 내부 mirror만 허용(또는 사내 toolcache)
- Dev: 선택 허용(단, 프로젝트 단위로 `.python-version` 또는 uv 설정으로 고정)

여기까지 정리되면, source-only 릴리스는 “불편한 예외”가 아니라 “정상 운영 시나리오”가 됩니다.

## 도입 판단 기준: 언제 source-only 대응 체계를 만들고, 언제 버전을 올릴 것인가

Python 3.13.18은 3.13 series가 security 단계로 넘어간 뒤 나온 보안 릴리스입니다. 이 상태에서 선택지는 두 갈래입니다.

1) 3.13을 유지한다
- 그러면 source-only 보안 릴리스를 흡수할 수 있는 내부 공급망이 필요합니다.
- 장점: minor 업그레이드 리스크를 줄이고, patch 보안 대응만 집중할 수 있습니다.
- 단점: upstream이 제공하는 바이너리 채널(특히 Windows/macOS)과 점점 멀어집니다.

2) 3.14/3.15 같은 bugfix 단계로 올린다
- bugfix 단계는 정기적인 바이너리 릴리스가 제공됩니다(정책 문구상).[^2]
- 장점: installer 기반 워크플로우를 유지할 수 있습니다.
- 단점: minor 업그레이드(언어/stdlib/빌드 변화)를 동반합니다.

나는 “버전을 올릴지 말지”와 “공급망을 갖출지 말지”를 같은 축으로 두지 않습니다.

- 보안 리드타임이 요구사항이라면, 어차피 내부 공급망이 필요합니다. bugfix 단계에서도 공급망은 흔들립니다(레이트리밋, mirror, runner 네트워크, base image 취약점 대응).
- security-only 단계의 source-only 릴리스는 그 사실을 더 노골적으로 드러낼 뿐입니다.

Python 3.13.18 같은 릴리스가 실전 점검에 좋은 이유가 여기 있습니다. installer가 없다는 사실이 불편한 게 아니라, 조직의 Python 공급/검증 체계가 얼마나 암묵적이었는지를 측정할 수 있게 해줍니다. 그 측정 결과를 기준으로 런타임 공급을 OCI artifact 중심으로 재정렬하는 게, 장기적으로 가장 덜 흔들리는 선택입니다.

## 참고 자료

- [Python 3.13.18 릴리스 페이지](https://www.python.org/downloads/release/python-31318/)
- [Python Source Releases 인덱스](https://www.python.org/downloads/source/)
- [Python documentation by version](https://www.python.org/doc/versions/)
- [Python Developer’s Guide: Status of Python versions](https://devguide.python.org/versions/)
- [Python Developer’s Guide: Security policy](https://devguide.python.org/security/policy/)
- [PEP 719 – Python 3.13 Release Schedule](https://peps.python.org/pep-0719/)
- [PEP 602 – Annual Release Cycle for Python](https://peps.python.org/pep-0602/)
- [Sigstore Information (CPython artifact verification)](https://test.python.org/downloads/metadata/sigstore/)
- [OpenPGP verification (legacy)](https://test.python.org/downloads/metadata/pgp/)
- [PEP 761 – Deprecating PGP signatures for CPython artifacts](https://peps.python.org/pep-0761/)
- [docker-library/python: 3.13 bookworm Dockerfile](https://github.com/docker-library/python/blob/master/3.13/bookworm/Dockerfile)
- [actions/setup-python advanced usage](https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md)
- [uv: Installing and managing Python](https://github.com/astral-sh/uv/blob/main/docs/guides/install-python.md)
- [uv: Python versions (managed CPython distributions)](https://docs.astral.sh/uv/concepts/python-versions/)

[^1]: <https://www.python.org/downloads/release/python-31318/>
[^2]: <https://devguide.python.org/versions/>
[^3]: <https://peps.python.org/pep-0602/>
[^4]: <https://peps.python.org/pep-0719/>
[^5]: <https://devguide.python.org/security/policy/>
[^6]: <https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md>
[^7]: <https://github.com/docker-library/python/blob/master/3.13/bookworm/Dockerfile>
[^8]: <https://hub.docker.com/_/python/tags?name=-alpine&page=1>
[^9]: <https://github.com/pyenv/pyenv?ref=opensource>
[^10]: <https://github.com/astral-sh/uv/blob/main/docs/guides/install-python.md>
[^11]: <https://test.python.org/downloads/metadata/sigstore/>
[^12]: <https://test.python.org/downloads/>
[^13]: <https://peps.python.org/pep-0761/>
[^14]: <https://www.python.org/downloads/source/>
[^15]: <https://www.python.org/doc/versions/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
