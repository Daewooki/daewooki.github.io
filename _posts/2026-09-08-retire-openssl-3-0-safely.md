---
title: "OpenSSL 3.0 EOL 이후 런타임을 안전하게 퇴역시키는 운영 설계"
description: "OpenSSL 3.0 EOL 이후 패치가 끊긴 런타임을 의존성 트리·FIPS 분기·롤아웃 검증까지 포함해 안전하게 퇴역시키는 방법을 정리합니다."
date: 2026-09-08 09:32:14 +0900
categories: ["Security", "OpenSSL"]
tags: ["openssl", "eol", "fips", "sbom", "containers", "rollout"]
render_with_liquid: false
---

## 2026-09-07 이후: “업그레이드”가 아니라 “퇴역” 문제로 바뀌는 지점

OpenSSL 3.0 LTS는 2026-09-07에 upstream 지원이 끝납니다. OpenSSL Corporation의 lifecycle 문서에 OpenSSL 3.0 LTS의 지원 종료일이 2026-09-07로 명시돼 있고, 3.5 LTS는 2030-04-08까지 지원된다고 적혀 있습니다. 이 시점부터는 OpenSSL 3.0 라인에서 보안 수정이 더 이상 나오지 않는다는 의미가 됩니다. [OpenSSL Corporation lifecycle](https://www.openssl-corporation.org/lifecycle.html)

FIPS까지 얽히면 시간표가 더 빡빡해집니다. OpenSSL Corporation은 2026년 9월에 두 개의 날짜가 고정돼 있다고 못 박습니다. 2026-09-07은 OpenSSL 3.0 EOL, 2026-09-21은 FIPS 140-2 인증(#4282)이 CMVP Historical List로 이동하는 날입니다. 그리고 FIPS 140-3 대체 인증으로 #4985(3.x에서 사용 가능, 2030년 3월까지 유효)를 제시합니다. [FIPS 140-2 sunsets in September 2026](https://openssl-corporation.org/blog/fips-140-2-sunsets-september-2026.html)

여기서 운영 관점의 핵심은 두 가지입니다.

1) OpenSSL은 대부분의 서비스에서 “직접 의존”이 아니라 “간접 의존”입니다. OS 패키지, 언어 런타임, 컨테이너 베이스 이미지 중 어디에 묶였는지 먼저 파악하지 않으면 일정 산정이 불가능합니다.

2) 3.0을 3.x의 더 최신으로 올리는 작업과, 4.0으로 올리는 작업은 성격이 다릅니다. OpenSSL은 semantic versioning과 MAJOR 단위의 API/ABI 파괴를 명시하고 있고, 같은 MAJOR에서는 API/ABI 호환을 보장한다고 밝힙니다. [OpenSSL Release Strategy](https://mirror.openssl-library.org/policies/releasestrat/index.html)

이 글에서 말하는 “안전한 퇴역”은 단순히 libssl을 교체하는 수준이 아니라, **(a) 의존성 트리에서 OpenSSL 3.0이 걸린 지점을 식별하고 (b) FIPS/컴플라이언스 분기에서 목표 상태를 정한 뒤 (c) 단계적 롤아웃과 검증으로 리스크를 흡수하는 것**을 뜻합니다.

## OpenSSL이 묶이는 세 레이어: OS 패키지, 언어 런타임, 베이스 이미지

현장에서 OpenSSL 3.0을 만나는 경로는 크게 세 가지로 수렴합니다. 한 서비스 안에 이 세 가지가 동시에 존재하기도 합니다.

### 1) OS 패키지로 들어온 OpenSSL

가장 흔한 형태는 `libssl.so.3`와 `libcrypto.so.3`가 OS 패키지 매니저로 설치된 경우입니다. 이때 “OpenSSL 버전”은 OS 배포판의 릴리스/보안 업데이트 정책에 묶입니다.

예를 들어 Debian의 경우, 배포판 릴리스별로 OpenSSL 소스 패키지 버전이 정리돼 있습니다. Debian Security Tracker는 bookworm(12)에 3.0.x 계열이, trixie(13)에 3.5.x 계열이 제공되는 것을 보여줍니다. [Debian security tracker: openssl source package](https://security-tracker.debian.org/tracker/source-package/openssl)

Ubuntu 24.04(noble)은 Launchpad에서 openssl 소스 패키지가 3.0.13 계열인 것이 확인됩니다. [Launchpad: openssl source package in Noble](https://launchpad.net/ubuntu/noble/+source/openssl)

이 레이어의 난점은 단순합니다. “우리 서비스는 OpenSSL을 직접 올릴 수 없다”는 말이 곧 “OS 업그레이드가 필요하다”로 번역되기 쉽습니다.

### 2) 언어 런타임이 OpenSSL에 링크되는 경우

Python은 표준 라이브러리 `ssl` 모듈이 OpenSSL 라이브러리를 사용한다고 문서에 명시되어 있고, 런타임에서 `ssl.OPENSSL_VERSION`으로 로딩된 OpenSSL 버전을 확인할 수 있습니다. [Python ssl module](https://docs.python.org/3/library/ssl.html)

Ruby의 OpenSSL extension도 `OPENSSL_VERSION` 상수를 제공해 “어떤 OpenSSL로 빌드됐는지”를 확인할 수 있습니다. [Ruby OpenSSL documentation](https://ruby-doc.org/3.3.1/exts/openssl/OpenSSL.html)

Node.js는 `process.versions`가 “Node.js와 의존성들의 버전 문자열”을 반환한다고 설명하고, 예시 출력에 `openssl: '3.5.4'` 같은 항목이 포함돼 있습니다. [Node.js process.versions](https://nodejs.org/api/process.html#processversions)

이 레이어의 특징은 “패키지 업그레이드”만으로 끝나지 않는다는 점입니다. 같은 서비스라도 Python을 어떻게 배포하느냐(시스템 Python, pyenv 빌드, distroless의 런타임, slim 이미지 등)에 따라 OpenSSL의 출처가 바뀝니다.

### 3) 컨테이너 베이스 이미지가 OpenSSL 버전을 고정하는 경우

컨테이너는 OS 패키지 레이어를 통째로 이미지로 고정해버립니다. Alpine을 예로 들면, Alpine 패키지 인덱스에서 stable 브랜치(v3.17)의 openssl 패키지가 3.0.19로 보입니다. [Alpine v3.17 openssl package](https://pkgs.alpinelinux.org/package/v3.17/main/x86_64/openssl)

반면 edge 브랜치에는 libssl3가 3.5.7로 올라와 있습니다. [Alpine edge libssl3 package](https://pkgs.alpinelinux.org/package/edge/main/x86/libssl3)

이게 실제 운영에서는 “우리 서비스는 코드 변경 없이도 베이스 이미지만 올리면 된다”와 “베이스 이미지 올리면 런타임이 깨진다”가 동시에 참이 되는 구간을 만들곤 합니다. 다음 섹션의 핵심이 바로 그 지점을 정량화하는 방법입니다.

## 1차 인벤토리: SBOM으로 OpenSSL 3.0이 깔린 곳을 먼저 찾는다

OpenSSL 3.0 퇴역 작업에서 가장 위험한 상황은 “어디에 있는지 모르는 OpenSSL 3.0”이 프로덕션에 남는 것입니다. 서비스별로 소스 코드 저장소를 뒤져 `openssl` 문자열을 grep하는 방식은 실패 확률이 높습니다. OpenSSL은 대개 OS 패키지/런타임/베이스 이미지로 들어오고, 심지어 애플리케이션이 아니라 sidecar(예: nginx, envoy, curl, git, package manager)에 묻어 들어오기도 합니다.

내 경우 운영에서 통하는 접근은 SBOM을 “발견 도구”로 쓰는 것입니다. SBOM을 만들고 취약점 스캐너를 얹는 순서가 아니라, SBOM을 통해 “OpenSSL 3.0이 실제로 어디에 배포되어 있는지”를 서비스 단위로 맵핑합니다.

### Syft로 이미지 단위 SBOM 생성

Syft는 컨테이너 이미지나 파일시스템에서 SBOM을 생성하는 CLI 도구로, SPDX/CycloneDX 같은 출력 포맷을 지원합니다. [anchore/syft](https://github.com/anchore/syft)

다음은 “현재 배포 중인 이미지 digest 목록”을 입력으로 받아 openssl 관련 패키지만 뽑아내는 흐름입니다.

```bash
# (1) syft 설치 (Linux)
curl -sSfL https://get.anchore.io/syft | sudo sh -s -- -b /usr/local/bin

# (2) 이미지에서 SBOM 생성 (SPDX JSON)
IMAGE=registry.example.com/payments/api@sha256:...
syft "$IMAGE" -o spdx-json > sbom.spdx.json

# (3) openssl 관련 패키지 필터링 (SPDX JSON 구조는 툴/버전마다 달라질 수 있어, 팀 표준 jq를 고정하는 게 낫습니다)
jq -r '
  .packages[]
  | select(.name | test("^(openssl|libssl3|libcrypto3)$"))
  | [.name, .versionInfo] | @tsv
' sbom.spdx.json
```

이 결과가 `openssl	3.0.xx`처럼 떨어지면 “이 이미지에는 OpenSSL 3.0이 OS 패키지로 들어 있다”는 뜻입니다.

### Trivy로 SBOM 생성/스캔을 함께 묶기

Trivy는 이미지에서 SPDX/CycloneDX 포맷으로 SBOM을 생성할 수 있고, SBOM 파일을 입력으로 다시 스캔할 수도 있습니다. [Trivy SBOM generating](https://trivy.dev/docs/dev/guide/supply-chain/sbom/), [Trivy SBOM scanning](https://trivy.dev/docs/dev/target/sbom/)

```bash
# 이미지에서 SPDX JSON SBOM 생성
trivy image --format spdx-json --output sbom.spdx.json "$IMAGE"

# SBOM을 입력으로 취약점 스캔
trivy sbom sbom.spdx.json
```

여기서 중요한 운영 포인트는 “SBOM 생성 시점”을 배포 파이프라인에 고정하는 것입니다. 프로덕션에서 이미지 digest를 기준으로 SBOM을 함께 저장해두면, 이후 OpenSSL EOL 같은 이벤트가 터졌을 때 “현재 돌아가는 것”을 기준으로 정확히 추적할 수 있습니다.

### SBOM의 신뢰성을 올리는 방법: attestation으로 digest에 묶기

SBOM을 S3나 위키에 저장하면 결국 “이 SBOM이 저 이미지의 것이라는 증명”이 약해집니다. cosign은 SBOM attachment가 deprecated 되고 attestations를 쓰라고 명시합니다. [cosign SBOM spec](https://github.com/sigstore/cosign/blob/main/specs/SBOM_SPEC.md), [sigstore cosign attest docs](https://github.com/sigstore/docs/blob/main/content/en/cosign/signing/other_types.md)

운영에서 정책까지 엮을 생각이라면 “SBOM을 이미지 digest에 묶어 레지스트리에 남기는 체계”가 훨씬 관리가 쉽습니다.

## 2차 인벤토리: 동적 링크와 런타임에서 “실제로” OpenSSL 3.0을 쓰는지 확인한다

SBOM은 OS 패키지/언어 패키지 관점의 inventory입니다. 하지만 OpenSSL 퇴역은 “실제 실행 시 어떤 libssl을 로딩하느냐”가 본질입니다. 특히 아래 케이스가 자주 나옵니다.

- OS 패키지는 3.5인데, 애플리케이션이 `/opt/vendor/lib/libssl.so.3`를 먼저 물고 있다.
- 같은 이미지에 libssl이 두 벌 있고, `LD_LIBRARY_PATH`나 `rpath` 때문에 예상과 다르게 로딩된다.
- 애플리케이션은 OpenSSL이 아니라 다른 TLS 스택을 쓰는데(예: Java 기본 TLS), sidecar가 OpenSSL 3.0을 사용한다.

### ELF 동적 링크 확인(리눅스)

컨테이너 이미지에서 실행 파일이 어떤 libssl을 요구하는지 확인할 때는 `readelf -d`와 `ldd`가 가장 빠릅니다.

```bash
# 이미지 내부에 들어가서 확인
docker run --rm -it --entrypoint sh "$IMAGE"

# 대표 바이너리의 동적 의존성 확인
ldd /usr/bin/curl | grep -E 'libssl|libcrypto'

# NEEDED 엔트리 확인
readelf -d /usr/bin/curl | grep NEEDED
```

이때 `libssl.so.3`를 요구하는 것은 정상입니다. 문제는 “그 libssl.so.3가 어느 경로에서 로딩되는지”입니다.

- `/lib/x86_64-linux-gnu/libssl.so.3` 같이 OS 표준 경로면 OS 패키지 업그레이드로 해결될 가능성이 큽니다.
- `/opt/.../libssl.so.3`처럼 vendor 경로면 별도 퇴역 플랜이 필요합니다.

### 언어 런타임에서 OpenSSL 버전 확인

서비스 팀과 대화할 때 “당신의 런타임은 어떤 OpenSSL을 쓰냐”는 질문을 명령 하나로 끝내야 일정이 나옵니다.

Python:

```bash
python - <<'PY'
import ssl
print(ssl.OPENSSL_VERSION)
PY
```

`ssl` 모듈이 OpenSSL을 사용하며, `ssl.OPENSSL_VERSION`을 제공한다는 것은 Python 문서에 정리돼 있습니다. [Python ssl module](https://docs.python.org/3/library/ssl.html)

Node.js:

```bash
node -p "process.versions.openssl"
```

`process.versions`가 의존성 버전을 보여주고, 예시 출력에 openssl 버전 필드가 있는 것은 Node.js 문서에 그대로 나옵니다. [Node.js process.versions](https://nodejs.org/api/process.html#processversions)

Ruby:

```bash
ruby -ropenssl -e 'puts OpenSSL::OPENSSL_VERSION'
```

Ruby OpenSSL extension이 `OPENSSL_VERSION`을 제공하는 것도 Ruby 문서에 정리돼 있습니다. [Ruby OpenSSL documentation](https://ruby-doc.org/3.3.1/exts/openssl/OpenSSL.html)

이 세 줄을 런북에 넣고, 팀별로 “프로덕션에서 찍힌 문자열”을 티켓에 붙이게 하면, SBOM과 함께 교차검증이 됩니다.

## 목표 버전 선택: 3.5 LTS로 갈 것인가, 4.0으로 갈 것인가

OpenSSL은 같은 MAJOR에서 API/ABI 호환을 보장하고, MAJOR가 바뀌면 호환이 보장되지 않는다고 명시합니다. [OpenSSL Release Strategy](https://mirror.openssl-library.org/policies/releasestrat/index.html), [OpenSSL versioning policy](https://mirror.openssl-library.org/policies/general/versioning-policy/)

운영에서 목표 버전을 잡는 기준은 보통 다음처럼 갈립니다.

### 기본값: OpenSSL 3.5 LTS

OpenSSL Corporation lifecycle 문서에서 3.5가 LTS이며 2030-04-08까지 지원된다고 밝힙니다. 3.0 EOL 직후의 가장 안전한 목표는 “지원 기간이 길고, MAJOR가 그대로인” 3.5 LTS입니다. [OpenSSL Corporation lifecycle](https://www.openssl-corporation.org/lifecycle.html)

여기서 기대하는 효과는 두 가지입니다.

- OS 패키지 업그레이드(혹은 베이스 이미지 업그레이드)만으로 libssl을 3.5로 올려서 3.0을 퇴역할 수 있다.
- 애플리케이션 코드 변경은 ‘없거나 최소’로 가져갈 수 있다(물론 보안 정책/레거시 알고리즘/프로토콜 이슈는 별개입니다).

### 빠르게 4.0을 찍는 선택지(조건부)

OpenSSL 4.0은 2026-04-14에 final release가 나왔고, “잠재적으로 중요하거나 호환되지 않는 변경”을 공개했습니다. 또한 4.0은 LTS가 아니고 2027-05-14까지 지원된다고 안내합니다. [OpenSSL 4.0 Final Release](https://openssl-corporation.org/blog/2026-04-14-openssl-40-final-release.html)

4.0으로의 이동은 “EOL 대응”이라기보다 “플랫폼 리프레시”에 가깝습니다.

- MAJOR 업그레이드이기 때문에, 재컴파일/테스트를 전제로 잡아야 합니다. OpenSSL migration 문서는 4.0이 major release이며 기존 애플리케이션은 최소 재컴파일이 필요하다고 적고, deprecated API를 썼다면 변경이 필요할 수 있다고 말합니다. [OpenSSL migration guide (master)](https://docs.openssl.org/master/man7/ossl-guide-migration/)
- 지원 기간이 3.5 LTS보다 훨씬 짧습니다.

정리하면 “3.0 EOL을 긴급 대응해야 하는 팀”에게 4.0은 보통 목표가 아니라, 3.5 LTS로 올린 뒤에 다음 주기로 검토하는 카드가 됩니다.

## 3.0 → 3.5로 올릴 때 운영에서 깨지는 지점: 레거시 알고리즘, Provider, Security Level

같은 3.x라고 해서 “아무 일도 안 일어난다”는 기대는 위험합니다. OpenSSL 3.0부터 Provider 모델이 도입됐고, 레거시 알고리즘은 기본적으로 제공되지 않으며, 필요하면 legacy provider를 로딩해야 한다는 점이 이미 migration 문서에 들어 있습니다. [OpenSSL 3.0 migration guide](https://docs.openssl.org/3.0/man7/migration_guide/)

### legacy provider: 애매하게 살아있는 레거시의 비용

OpenSSL legacy provider는 “legacy로 간주된 알고리즘 구현”을 제공하며, MD2/MD4/RIPEMD160, DES/RC4 같은 알고리즘들이 포함된다고 문서에 나옵니다. [OSSL_PROVIDER-legacy](https://docs.openssl.org/3.4/man7/OSSL_PROVIDER-legacy/)

운영에서 문제는 이런 식으로 터집니다.

- 오래된 암호화된 데이터 포맷(특히 RC2/RC4/DES 계열)을 복호화해야 하는 배치가 있다.
- 오래된 PKCS#12를 다루는 유틸리티가 내부적으로 legacy 알고리즘에 기대고 있다.
- 특정 빌드 체인이 MD4 같은 해시를 쓰다가 OpenSSL 3.x에서 끊긴다.

레거시가 남아있으면 “일단 legacy provider 켜서 살린다”는 유혹이 생기는데, 그 결정은 업그레이드가 아니라 기술부채의 연장입니다. legacy provider는 retirement home이라는 표현까지 씁니다. [OSSL_PROVIDER-legacy](https://docs.openssl.org/3.4/man7/OSSL_PROVIDER-legacy/)

내 기준으로는 다음 원칙이 운영에서 맞았습니다.

- 프로덕션에서 legacy provider는 “가능하면 끈다”가 기본.
- 단, 외부 시스템과의 상호운용 때문에 당장 끊을 수 없다면, legacy provider를 “서비스 전체”가 아니라 “필요한 프로세스/경로”로 격리한다.

### Security Level: 3.2+에서 기본값이 바뀌면 핸드셰이크가 터진다

OpenSSL의 TLS security level은 핸드셰이크에서 허용되는 키 길이/알고리즘/프로토콜에 직접 영향을 줍니다. OpenSSL 문서는 Level 2가 112-bit security에 해당하며 RSA/DSA/DH 2048-bit 미만을 금지하고, RC4를 금지하며, compression을 끈다고 명시합니다. 그리고 컴파일 시 `-DOPENSSL_TLS_SECURITY_LEVEL`로 기본을 설정하며, 지정하지 않으면 2를 쓴다고 적습니다. [SSL_CTX_set_security_level](https://docs.openssl.org/master/man3/SSL_CTX_set_security_level/)

OpenSSL 3.2 릴리스 준비 글에서는 “default SSL/TLS security level이 1에서 2로 바뀐다”고 명시합니다. [OpenSSL 3.2 Release Candidate post](https://openssl-library.org/post/2023-10-26-ossl-32-beta/)

이 변화는 특히 사내 레거시(mTLS, 오래된 사설 CA, 짧은 RSA 키, SHA1 서명 체인 등)와 맞물릴 때 장애로 이어집니다. 그래서 3.5 LTS로 가더라도, 중간에 3.2/3.3을 거치는 경로든 아니든 간에 “보안 레벨 변화가 실제로 핸드셰이크를 깨는지”는 별도의 검증 항목으로 빼야 합니다.

## FIPS/컴플라이언스 분기: “OpenSSL 업그레이드”가 아니라 “인증 상태”를 업그레이드하는 일

FIPS는 단순히 `fips=1` 같은 플래그로 끝나는 문제가 아닙니다. 감사/심사에서 묻는 건 보통 “FIPS validated module을 쓰고 있나”이며, OpenSSL 버전보다 인증서 번호/상태가 더 중요해지는 순간이 많습니다.

OpenSSL Corporation은 2026-09-21에 FIPS 140-2 인증(#4282)이 Historical List로 이동한다고 적고, FIPS 140-3 대체로 #4985가 있으며 3.x(3.5 포함)에서 사용 가능하다고 설명합니다. [FIPS 140-2 sunsets in September 2026](https://openssl-corporation.org/blog/fips-140-2-sunsets-september-2026.html)

NIST CMVP 사이트에서도 OpenSSL FIPS Provider 관련 인증의 sunset 날짜로 2026-09-21이 표시됩니다. [NIST CMVP certificate 4706 (sunset 표시 예시)](https://csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/4706)

운영 의사결정은 보통 아래처럼 갈립니다.

### A안: FIPS 요구 없음 → 3.0에서 3.5 LTS로 올리고 끝

이 경우 목표는 명확합니다.

- OpenSSL 3.0이 깔린 이미지/호스트를 모두 3.5로 치환
- legacy provider 의존 제거
- 핸드셰이크 실패 모니터링 기반 롤아웃

### B안: FIPS 요구 있음 → “어떤 FIPS 인증서로, 어떤 배포물로, 어떤 설정으로”를 문서화

여기서부터는 질문이 달라집니다.

- “OpenSSL 3.5를 쓰면 된다”가 아니라, “FIPS validated provider(#4985)를 쓰는 형태로 운영 중임”을 증빙해야 합니다.
- OS 배포판이 제공하는 FIPS 패키지를 쓰는지, upstream 제공물을 쓰는지, vendor 배포물을 쓰는지에 따라 심사 대응 난도가 달라집니다.

또 하나 중요한 점은 OpenSSL migration 문서에서, OpenSSL 3.1의 FIPS provider에는 non-validated 알고리즘이 포함될 수 있어 `fips=yes` property query가 필수라고 언급한다는 것입니다. [OpenSSL ossl-guide-migration (3.2)](https://docs.openssl.org/3.2/man7/ossl-guide-migration/)

이 문장을 운영 관점으로 번역하면 이렇습니다.

- “FIPS 모듈을 로딩했다”는 것만으로는 부족할 수 있다.
- 애플리케이션/미들웨어가 provider와 property query를 어떻게 쓰는지까지 점검해야 한다.

실제로는 애플리케이션을 전부 고치기 어려우니, FIPS를 요구하는 서비스는 “FIPS 모드 강제 + 검증 테스트 + 롤백 가능”을 한 묶음으로 다루는 편이 안전합니다.

## 마이그레이션 설계: 베이스 이미지 교체를 중심에 두고, OS 업그레이드/업스트림 패키지/벤더 번들로 갈라탄다

현실적인 경로는 크게 세 가지입니다.

### 1) 베이스 이미지/OS 배포판을 올려서 OpenSSL을 따라올리기

가장 운영 친화적인 방법입니다. 예를 들어 Debian 계열이라면 “bookworm(3.0)”에서 “trixie(3.5)”로의 OS 업그레이드가 OpenSSL 3.0 퇴역을 자연스럽게 포함할 수 있습니다. Debian Security Tracker에서 릴리스별 OpenSSL 버전을 볼 수 있습니다. [Debian security tracker: openssl source package](https://security-tracker.debian.org/tracker/source-package/openssl)

Alpine도 비슷한 사고가 가능합니다. stable 브랜치에 3.0이 남아 있으면, 더 최신 stable로 올리거나(가능하다면) edge를 검토할 수 있습니다. Alpine 패키지 인덱스에서 브랜치별 openssl/libssl3 버전을 직접 확인하는 게 제일 빠릅니다. [Alpine v3.17 openssl package](https://pkgs.alpinelinux.org/package/v3.17/main/x86_64/openssl), [Alpine edge libssl3 package](https://pkgs.alpinelinux.org/package/edge/main/x86/libssl3)

이 경로의 장점은 patch cadence가 OS 보안 업데이트로 흡수된다는 점입니다.

단점은 OS 업그레이드가 OpenSSL만 바꾸지 않는다는 점입니다. glibc, ca-certificates, curl, timezone, coreutils, 컴파일러/런타임까지 같이 변합니다. 그래서 롤아웃/검증을 더 탄탄하게 가져가야 합니다.

### 2) upstream OpenSSL 패키지를 /opt에 사이드로 설치하기

OpenSSL은 공식 .deb/.rpm 패키지를 /opt 아래에 배치하는 형태로 제공하는 저장소를 운영합니다. 배포판 OpenSSL과 공존하도록 설계됐다고 README에 적혀 있습니다. [openssl/packages](https://github.com/openssl/packages)

이 접근은 “OS는 그대로 두고 OpenSSL만 올린다”는 요구가 있을 때 매력적으로 보이지만, 운영 난이도가 꽤 올라갑니다.

- 동적 로더 경로를 조정해야 하고(`LD_LIBRARY_PATH`, `rpath`, `ldconfig`), 실수하면 일부 프로세스만 다른 libssl을 물 수 있습니다.
- 보안팀/감사 대응에서 “왜 OS 공급망을 우회했는가” 질문이 나오기 쉽습니다.

그래도 OS 업그레이드가 불가능한 레거시 호스트가 남아 있다면, 최소한 “어떤 서비스가 이 예외를 쓰는지”를 명시적으로 관리해야 합니다.

### 3) 애플리케이션이 OpenSSL을 vendor 번들로 들고 있는 경우

이 경우는 사실 OpenSSL 업그레이드가 아니라 “벤더 업그레이드”입니다.

- 데이터베이스 클라이언트
- 상용 에이전트
- 하드웨어 관리 툴

이들은 자체 번들된 `libcrypto.so.3`를 `/opt/vendor`에 설치하고, 환경 변수를 건드리기도 합니다. 이런 경우 SBOM만으로는 놓치기 쉽고, 앞에서 말한 동적 링크 점검이 필요합니다.

## 롤아웃/검증 전략: OpenSSL 교체의 실패는 대부분 TLS 핸드셰이크에서 관측된다

OpenSSL 업그레이드는 “기능 테스트 통과”로 끝나지 않습니다. 장애는 대개 트래픽이 몰릴 때, 특정 파트너/특정 레거시 클라이언트에서만 발생합니다.

내가 운영에서 고정으로 가져가는 검증 축은 아래 세 가지입니다.

### 1) 핸드셰이크 실패율을 SLI로 만든다

애플리케이션 계층에서 TLS를 직접 쓰지 않아도, ingress/sidecar가 TLS를 하고 있으면 실패율은 관측 가능합니다.

- 4xx/5xx만 보면 늦습니다. 핸드셰이크 실패는 애플리케이션 로그로 들어오지 않는 경우가 많습니다.
- ingress controller, envoy, nginx, haproxy 같은 계층에서 TLS alert, handshake failure 카운터를 먼저 봐야 합니다.

특히 OpenSSL security level 변화가 들어오면, “특정 클라이언트 인증서가 거절되는지” 같은 일이 생깁니다. OpenSSL 문서는 security level이 certificate key size, DH parameter size 등을 검사하고, 조건을 만족하지 않으면 핸드셰이크를 fatal alert로 중단할 수 있다고 말합니다. [SSL_CTX_set_security_level](https://docs.openssl.org/master/man3/SSL_CTX_set_security_level/)

### 2) canary는 트래픽 샘플링이 아니라 “상대 식별 기반”이 유리하다

일반적인 1% canary는 파트너 시스템/레거시 단말이 희소한 경우 아무 것도 못 잡습니다.

가능하면 아래처럼 “문제가 될 만한 상대를 의도적으로” canary 풀에 넣는 전략이 필요합니다.

- 파트너 ASN/대역 기반
- 특정 mTLS client certificate issuer 기반
- 레거시 기기 User-Agent 기반

이건 OpenSSL 자체 기능이라기보다 트래픽 라우팅 계층의 설계 문제인데, OpenSSL 업그레이드에서 제일 큰 불확실성을 줄여줍니다.

### 3) 롤백은 “이미지 롤백”이지 “libssl만 롤백”이 아니다

운영 중 장애가 났을 때 libssl 패키지만 되돌리는 방식은 종종 더 큰 장애를 만듭니다.

- 컨테이너는 immutable artifact로 롤백하는 게 더 안전합니다.
- 호스트 패키지 롤백이 필요하다면, 최소한 “롤백 가능한 snapshot/AMI/이미지” 단위를 준비해야 합니다.

이 글의 초반에 말한 것처럼, OpenSSL은 OS 패키지/런타임/베이스 이미지에 얽혀 있습니다. 그래서 안전한 롤백 단위도 결국 그 결합 단위로 맞춰야 합니다.

## 실행 가능한 퇴역 플랜 예시: Kubernetes 기반 마이크로서비스(혼합 베이스 이미지)에서 3.0 제거

가정:

- 서비스 A: `python:3.x-slim` 계열(실제로는 Debian 계열 기반)
- 서비스 B: `node:xx-alpine` 계열
- 서비스 C: distroless 기반(직접 OpenSSL이 없다고 가정하면 위험)
- 공통: 이미지 digest 기반 배포

목표:

- 2026-09-07 이후 프로덕션에서 OpenSSL 3.0이 로딩되는 프로세스가 0이 되게 만들기
- FIPS 요구 없음(있으면 다음 섹션의 분기를 추가)

### 단계 1: 배포 중인 모든 이미지 digest 수집

이건 조직마다 다르지만, “현재 배포된 것” 기준으로 수집해야 합니다. CI 최신 태그 기준으로 하면 의미가 없습니다.

- Argo CD면 Application manifest에서
- Kubernetes면 Deployment의 image field에서
- Registry audit log면 digest로

### 단계 2: 이미지별 SBOM 생성 + OpenSSL 3.0 매칭

```bash
# images.txt: 한 줄에 이미지 digest 하나
# registry.example.com/a@sha256:...
# registry.example.com/b@sha256:...

while read -r IMAGE; do
  syft "$IMAGE" -o spdx-json > "sbom.$(echo "$IMAGE" | tr '/:@' '___').json"
  jq -r '
    .packages[]
    | select(.name | test("^(openssl|libssl3|libcrypto3)$"))
    | [.name, .versionInfo] | @tsv
  ' "sbom.$(echo "$IMAGE" | tr '/:@' '___').json" \
  | awk -v img="$IMAGE" '{print img"\t"$0}'
done < images.txt > openssl-inventory.tsv

# 3.0 계열만 필터
awk '$3 ~ /^3\.0\./ {print}' openssl-inventory.tsv > openssl-3.0.tsv
```

이 결과가 “퇴역 대상 이미지 목록”의 1차 버전이 됩니다.

### 단계 3: 상위 10개 이미지에 대해 동적 링크/런타임 확인

SBOM에서 3.0이 잡혔다고 해도, 실제 런타임이 그 libssl을 쓰는지는 확인해야 합니다.

- Python은 `ssl.OPENSSL_VERSION`
- Node는 `process.versions.openssl`
- 바이너리는 `ldd`/`readelf`

이 작업은 자동화가 가능하지만, 처음에는 수동으로 “어디에서 꼬이는지” 감을 잡는 게 더 빠릅니다.

### 단계 4: 서비스별 마이그레이션 경로 선택

- Debian/Ubuntu 기반 서비스: OS 릴리스를 올리는 베이스 이미지 교체가 최우선
  - Ubuntu 24.04가 openssl 3.0.13 계열인 점은 Launchpad/USN에서 확인 가능합니다. [Launchpad: openssl source package in Noble](https://launchpad.net/ubuntu/noble/+source/openssl), [Ubuntu security notice example](https://ubuntu.com/security/notices/USN-6986-1)
- Alpine 기반 서비스: Alpine 브랜치/버전 업그레이드로 3.5 계열을 확보할 수 있는지 확인
  - Alpine 패키지 인덱스에서 브랜치별 버전을 확인하는 것이 가장 확실합니다. [Alpine v3.17 openssl package](https://pkgs.alpinelinux.org/package/v3.17/main/x86_64/openssl)
- distroless 기반 서비스: “OpenSSL이 없을 것”이라는 가정이 깨질 수 있으니 SBOM으로 확인
  - distroless README에서도 베이스 이미지 구성에 대한 주의사항이 지속적으로 갱신됩니다. [distroless base README](https://github.com/GoogleContainerTools/distroless/blob/main/base/README.md)

여기서 핵심은 “서비스 팀이 선택할 수 있는 경로를 1~2개로 줄여주는 것”입니다. 선택지가 많아지면 아무도 결정을 못 내립니다.

### 단계 5: canary → 확대 롤아웃 + 핸드셰이크 관측

- 1일차: 내부 트래픽만 받는 canary
- 2~3일차: 파트너/레거시가 섞인 구간을 의도적으로 포함
- 1주: 전체 롤아웃

이 과정에서 레거시 알고리즘이나 security level 관련 장애가 보이면, 원인을 “legacy provider로 임시 해결”하기 전에 먼저 “상호운용 요구가 실제로 필요한지”를 재검토해야 합니다.

예를 들어 RC4는 security level 2에서 금지되는 항목이며, OpenSSL 문서에 명시돼 있습니다. [SSL_CTX_set_security_level](https://docs.openssl.org/master/man3/SSL_CTX_set_security_level/)

## FIPS 요구가 있는 조직의 추가 단계: 인증서 번호/상태까지 포함한 퇴역 정의

FIPS 요구가 있으면 “OpenSSL 3.0이 남아 있는지”만 보면 불충분합니다. “FIPS 140-2 인증 상태(#4282)”가 2026-09-21에 Historical로 이동한다는 점까지 포함해서 퇴역 정의를 다시 내려야 합니다. [FIPS 140-2 sunsets in September 2026](https://openssl-corporation.org/blog/fips-140-2-sunsets-september-2026.html)

운영 문서(SSP, 설계서, 보안 예외 문서)에 최소한 아래 항목은 들어가야 심사 대응이 쉬워집니다.

- 사용 중인 FIPS 인증서 번호(예: #4985)
- 적용 범위(어떤 서비스/노드/클러스터)
- 구성 방식(OpenSSL config로 provider 로딩인지, 애플리케이션 코드에서 로딩인지)
- `fips=yes` property query 적용 여부(적용이 필요한지 여부 포함)

OpenSSL migration 문서는 `fips=yes` property query가 FIPS approved 동작을 위해 mandatory라고 언급합니다. [OpenSSL ossl-guide-migration (3.2)](https://docs.openssl.org/3.2/man7/ossl-guide-migration/)

이 분기에서는 “서비스 우선순위”가 바뀝니다. 외부 감사 대상/규제 대상 서비스가 먼저 빠져야 합니다. 나머지는 기술적으로는 먼저 옮길 수 있어도, 조직의 우선순위는 보통 그 반대로 움직입니다.

## 정리: OpenSSL 3.0 퇴역은 보안 패치의 문제가 아니라 운영 가시성의 문제다

2026-09-08 KST 시점에서 OpenSSL 3.0은 이미 EOL(2026-09-07)을 지나 “패치가 끊긴 런타임”이 됐습니다. OpenSSL Corporation은 lifecycle과 FIPS 관련 공지에서 이 날짜들을 고정된 사실로 제시하고, 3.5 LTS 같은 지속 가능한 타깃을 명확히 안내합니다. [OpenSSL Corporation lifecycle](https://www.openssl-corporation.org/lifecycle.html), [FIPS 140-2 sunsets in September 2026](https://openssl-corporation.org/blog/fips-140-2-sunsets-september-2026.html)

현장에서 이 작업이 실패하는 이유는 대개 기술 부족이 아니라 “어디에 깔렸는지 모르는 OpenSSL” 때문입니다. SBOM으로 1차 인벤토리를 만들고, 동적 링크/런타임으로 2차 검증을 한 다음, FIPS 요구가 있으면 인증 상태까지 포함해 퇴역 정의를 다시 내려야 합니다. 그 위에서 canary와 핸드셰이크 관측을 중심으로 롤아웃을 설계하면, OpenSSL 업그레이드는 ‘한 번에 끝내는 이벤트’가 아니라 ‘예측 가능한 퇴역 작업’이 됩니다.

## 참고 자료

- [OpenSSL 릴리스 라이프사이클(3.0 EOL, 3.5 LTS 지원 기간)](https://www.openssl-corporation.org/lifecycle.html)
- [FIPS 140-2 sunset 공지(2026-09-07, 2026-09-21, #4282, #4985)](https://openssl-corporation.org/blog/fips-140-2-sunsets-september-2026.html)
- [OpenSSL Release Strategy(API/ABI 호환 원칙)](https://mirror.openssl-library.org/policies/releasestrat/index.html)
- [OpenSSL versioning policy(MAJOR 변경 시 비호환)](https://mirror.openssl-library.org/policies/general/versioning-policy/)
- [OpenSSL 3.0 migration guide(provider 모델, legacy 알고리즘)](https://docs.openssl.org/3.0/man7/migration_guide/)
- [OpenSSL migration guide(4.0 포함, deprecated API 제거 관련)](https://docs.openssl.org/master/man7/ossl-guide-migration/)
- [legacy provider 문서(legacy 알고리즘 목록)](https://docs.openssl.org/3.4/man7/OSSL_PROVIDER-legacy/)
- [TLS security level 문서(Level 2 제약, 기본값)](https://docs.openssl.org/master/man3/SSL_CTX_set_security_level/)
- [OpenSSL 3.2 릴리스 준비 글(default security level 1→2)](https://openssl-library.org/post/2023-10-26-ossl-32-beta/)
- [Debian Security Tracker의 openssl 소스 패키지 버전 목록](https://security-tracker.debian.org/tracker/source-package/openssl)
- [Ubuntu Noble(24.04) openssl 소스 패키지 정보](https://launchpad.net/ubuntu/noble/+source/openssl)
- [Alpine v3.17 openssl 패키지(3.0 계열 예시)](https://pkgs.alpinelinux.org/package/v3.17/main/x86_64/openssl)
- [Alpine edge libssl3 패키지(3.5 계열 예시)](https://pkgs.alpinelinux.org/package/edge/main/x86/libssl3)
- [Python ssl 모듈(OpenSSL 사용, OPENSSL_VERSION)](https://docs.python.org/3/library/ssl.html)
- [Node.js process.versions 예시(openssl 버전 포함)](https://nodejs.org/api/process.html#processversions)
- [Ruby OpenSSL extension 상수(OPENSSL_VERSION)](https://ruby-doc.org/3.3.1/exts/openssl/OpenSSL.html)
- [Trivy SBOM 생성 가이드(SPDX/CycloneDX)](https://trivy.dev/docs/dev/guide/supply-chain/sbom/)
- [Trivy SBOM 스캔 가이드](https://trivy.dev/docs/dev/target/sbom/)
- [Syft 프로젝트(컨테이너/파일시스템 SBOM 생성)](https://github.com/anchore/syft)
- [cosign SBOM attachment deprecation 및 attest 권장](https://github.com/sigstore/cosign/blob/main/specs/SBOM_SPEC.md)
- [cosign attest 사용 예시 문서](https://github.com/sigstore/docs/blob/main/content/en/cosign/signing/other_types.md)
- [이 블로그의 관련 글: 운영·정책·보안이 제품 경쟁력을 좌우하는 흐름](https://daewooki.github.io/posts/codex-securityrsp-30gemini-in-chrome-202-1/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
