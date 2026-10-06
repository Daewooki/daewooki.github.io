---
title: "Node.js crypto.parsePKCS12로 PKCS#12 인증서/키 처리 로직 리팩터링"
description: "Node.js 26.10.0의 crypto.parsePKCS12()를 기준으로 PKCS#12 입력 검증·암호화 강제·노출 방지부터 mTLS 회전 운영까지 정리합니다."
date: 2026-10-06 11:41:36 +0900
categories: ["Backend", "Node.js"]
tags: ["nodejs", "crypto", "pkcs12", "mtls", "certificate-rotation", "secrets"]
render_with_liquid: false
---

## PKCS#12를 서비스 코드에 들여오는 순간 생기는 위험한 기본값

PKCS#12(.p12/.pfx)는 현실적으로 “키 + 인증서 체인”을 한 덩어리로 나르기 좋은 컨테이너입니다. Windows나 일부 엔터프라이즈 제품군, Java/비-Java 환경을 넘나들 때 특히 자주 튀어나옵니다. 문제는 이 포맷을 서비스 코드에 넣는 순간, 보안 품질이 포맷이 아니라 구현 선택에 의해 결정된다는 점입니다.

내가 여러 팀 코드베이스에서 반복해서 본 패턴은 대략 아래로 수렴합니다.

- 환경변수에 base64로 .p12를 넣고, 애플리케이션 부팅 시 디코딩한 뒤 TLS 옵션에 `pfx`로 꽂는다.
- 패스워드는 같은 환경변수나 Secret에 넣는다.
- 실패 시 “암호가 틀렸습니다” 같은 로그를 그대로 남긴다(가끔 패스워드 길이/일부를 실수로 포함한다).
- 인증서 만료일, 체인 구성, key type 같은 검증은 런타임 오류가 나기 전까지 하지 않는다.
- 회전은 ‘배포 때마다 갈아끼우기’로만 처리하고, 핫리로드는 포기한다.

이 방식은 작동은 합니다. 다만 보안/운영 관점에서 기본값이 위험한 쪽으로 기울어 있습니다.

- **입력 검증 부재**: PKCS#12는 바이너리 포맷이라 사람이 눈으로 훑고 이상 징후를 잡기 어렵습니다. 실수로 다른 바이너리를 전달해도 코드가 한참 진행된 뒤에야 터집니다.
- **암호화 강제 실패**: “패스워드가 비어 있어도 되는” 흐름을 허용하면 결국 어딘가에서 무암호(.p12에 password 없이)로 굴러가는 아티팩트가 생깁니다.
- **메모리/로그 노출**: 예외 처리와 디버깅 로그가 키/인증서 재료를 유출시키는 통로가 됩니다.
- **표준화 실패**: 팀마다 서로 다른 파서(외부 라이브러리, OpenSSL CLI 호출, 런타임 내장 기능)를 쓰면, 보안 패치/런타임 업그레이드 시 실패 모드가 제각각이 됩니다.

이걸 “언제 쓰면 안 되는지”를 먼저 고르면 정리가 빨라집니다.

- 사용자가 업로드하는 임의의 .p12를 서버가 받아서 파싱하는 모델이라면, 애플리케이션 프로세스에서 바로 파싱하는 것은 피하는 게 낫습니다. Node.js 프로젝트가 PKCS#12(PFX) 처리 경로를 공격자가 악용할 수 있는 CVE 범위로 여러 차례 평가한 바 있고, 공격자가 **특수하게 조작된 PFX**를 제공할 수 있는 상황이면 공격면이 달라집니다.[^1]
- 반대로, 배포 파이프라인이 생성한 키스토어(내부 CA, cert-manager, Vault PKI 등)만 처리하고 입력 경로를 강하게 통제할 수 있다면 “런타임 내부 파서로 통일”하는 게 오히려 사고를 줄입니다.

## Node.js 26.10.0에서 추가된 crypto.parsePKCS12()의 의미

Node.js 26.10.0(Current)은 2026-09-22 릴리스이며, 여기서 (SEMVER-MINOR)로 `crypto.parsePKCS12()`가 추가됐습니다.[^2] 26.10.0 릴리스에는 OpenSSL이 3.5.8로 업데이트된 것도 같이 들어가 있습니다.[^3]

이 함수는 “TLS 설정 옵션에 `pfx`를 바로 꽂는 방식”과는 경계가 다릅니다.

- `tls.createSecureContext({ pfx, passphrase })`는 TLS 컨텍스트를 만들기 위해 내부에서 PKCS#12를 파싱합니다. 문서에서도 `pfx`는 “PFX or PKCS12 encoded private key and certificate chain”이고, 암호화된 경우 `passphrase`로 해제한다고 설명합니다.[^4]
- `crypto.parsePKCS12(bundle[, options])`는 PKCS#12를 파싱해 **KeyObject(privateKey)**, **X509Certificate(certificate/additionalCertificates)**로 돌려주는 “순수 파서”입니다. Node 문서에 추가된 시점도 v26.10.0으로 명시되어 있습니다.[^5]

API 시그니처에서 중요한 지점은 두 가지입니다.

1) 입력은 “DER-encoded PKCS#12 bundle”이며, `.p12`/`.pfx`를 의미합니다.[^5]

2) `options.passphrase`를 생략하면 `''`를 전달한 것과 같다고 되어 있습니다.[^5]

이 두 번째 문장이 보안 리팩터링에서 핵심입니다. 기존 코드가 `passphrase`를 옵션으로 취급하고 “없으면 생략”해도 된다고 설계돼 있으면, parse 경로로 옮기는 순간 **무암호 번들(혹은 빈 문자열 암호)**을 자연스럽게 허용하는 기본값이 됩니다. 즉, 새 API를 도입한다고 저절로 안전해지지 않습니다.

내 결론은 단순합니다.

- parsePKCS12()를 도입하는 목적을 “외부 라이브러리 제거”에 두면 얻는 게 제한적입니다.
- 목적을 “PKCS#12 처리 경로를 표준화하고, 입력 검증/암호화 강제/노출 방지를 코드 레벨 계약으로 만들기”에 두면, 이 함수는 충분히 값이 있습니다.

그리고 이 표준화는 런타임 업그레이드 작업 방식과도 연결됩니다. 예전에 [Node.js 26.8.2 업그레이드를 공급망 위험으로 해석하기](https://daewooki.github.io/posts/nodejs-runtime-supply-chain-risk/)에서 적었듯이, 런타임은 기능 추가보다 “의존 체인(특히 OpenSSL) 변화에 대한 실패 모드가 어떻게 바뀌는지”가 더 중요하게 작동하는 경우가 많습니다.

## 입력 검증: 파서 호출 전에 잘라내야 하는 것들

PKCS#12는 “암호화된 비밀 묶음”이라는 인식 때문에, 종종 입력 검증이 느슨해집니다. 하지만 실제 공격/사고는 암호화 여부보다 **입력 경로 통제 실패**에서 시작하는 경우가 잦습니다.

내가 서비스 코드에서 PKCS#12 처리를 표준화할 때, 파서 호출 전에 강제하는 검증 규칙은 다음과 같습니다.

### 1) 타입을 문자열로 받지 않는다

`crypto.parsePKCS12()`는 `Buffer`/`TypedArray`/`ArrayBuffer`를 받습니다.[^5]

문제는 팀이 “편의” 때문에 base64 문자열을 환경변수로 넣고, 코드가 `Buffer.from(str, 'base64')`로 바꿔치는 패턴입니다. 이 자체가 무조건 나쁜 건 아니지만, 문자열은 로깅/에러 메시지/모니터링 시스템을 떠돌 가능성이 훨씬 큽니다.

정책을 이렇게 잡는 편이 운영 안정성이 좋았습니다.

- 애플리케이션 입력은 **파일 경로**(Secret volume mount)만 허용한다.
- 정말 환경변수로 받아야 한다면 base64는 예외로 두되, 모듈 경계에서만 디코딩하고 즉시 overwrite(후술)한다.

### 2) 크기 제한을 둔다

PFX는 정상이어도 수~수십 KB가 대부분입니다. 체인이 길고 인증서가 여러 개 들어가도 수백 KB면 충분합니다. 그런데 제한이 없으면 “실수로 다른 바이너리(예: zip, log archive)를 마운트”하는 형태로 사고가 납니다.

- 운영 환경: 예를 들어 256KB~1MB 상한.
- 개발/테스트: 조금 더 여유.

이건 보안뿐 아니라 장애 격리 관점에서 의미가 있습니다. 특히 Node는 OpenSSL을 통해 파싱하는 경로가 많고(26.10.0은 OpenSSL 3.5.8)[^3], 크고 이상한 입력을 넣었을 때의 비용은 “생각보다 비쌀 수” 있습니다.

### 3) passphrase는 옵션이 아니라 필수로 취급한다

문서상 `passphrase` 생략은 `''`와 같습니다.[^5] 즉, “생략 가능” 설계는 곧 “빈 패스워드 허용” 설계가 됩니다.

내 경우는 다음 중 하나로 고정합니다.

- **Strict 모드(권장)**: `passphrase`가 비어 있으면(길이 0) 즉시 실패.
- Legacy 모드(이행 기간): 특정 서비스/특정 Secret에 대해서만 빈 passphrase를 허용하되, 로그/메트릭으로 카운팅하고 제거 시점을 못 박는다.

여기서 중요한 건 “PKCS#12가 암호화돼 있는지” 자체를 런타임에서 완벽하게 판별하려고 하지 않는 겁니다. 그 판별은 구현/라이브러리/옵션에 따라 흔들립니다. 대신 **정책적으로 ‘우리는 passphrase 없는 번들을 운영하지 않는다’**를 코드 계약으로 강제하는 게 안정적입니다.

### 4) 파싱 결과를 검증한다

`parsePKCS12()`는 아래 오브젝트를 반환합니다.[^5]

- `privateKey`: bundle의 첫 private key 또는 `null`
- `certificate`: `privateKey`와 매칭되는 인증서 또는 `null`
- `additionalCertificates`: 나머지 인증서들

즉, “인증서만 들어 있는 .p12”도 들어올 수 있고, “키만 들어 있는 이상한 묶음”도 가능합니다. 서비스마다 허용 규칙이 명확해야 합니다.

- mTLS client identity로 쓸 거면 `privateKey`/`certificate` 둘 다 필수
- trust store로만 쓸 거면 `privateKey`는 없어도 되고 `additionalCertificates`가 최소 1개 이상

또한 X509Certificate는 `validFrom/validTo`를 제공하고[^5], `toString()`이 PEM 인코딩을 반환합니다.[^5] 즉 “외부 x509 파서”를 더 붙이지 않고도 최소한의 검증/변환을 할 수 있습니다.

## 암호화 강제와 레거시 PFX 탈출: OpenSSL 3 시대의 현실적인 합의

PKCS#12는 표준이지만, 실제 현장에서는 “레거시 암호 알고리즘으로 만든 PFX”가 오래 살아남습니다. OpenSSL 문서에서도 레거시 PFX(예: RC2-40-CBC)를 로딩할 때 문제가 생기면 `-legacy` 옵션을 시도하라고 직접 언급합니다.[^6]

여기서 Node.js의 현실은 다음과 같습니다.

- Node 26.10.0은 OpenSSL 3.5.8을 포함합니다.[^3]
- OpenSSL 3에서는 provider 모델 때문에 “기본 provider에 없는 레거시 알고리즘”을 읽다가 `ERR_OSSL_UNSUPPORTED` 류로 터지는 케이스가 흔합니다.
- 이 문제는 Node.js 코드의 잘못이라기보다 “운영 중인 PFX가 레거시로 생성되어 있다”는 신호인 경우가 많습니다.

따라서 리팩터링 목표는 단순합니다.

- 런타임에서 레거시 provider를 억지로 켜서 과거 포맷을 계속 받아주는 쪽으로 가지 않는다.
- PFX를 생성/배포하는 쪽(보통 CI/CD, PKI 발급 파이프라인, 운영 문서)을 손봐서 **현대적인 암호로 다시 export**한다.

OpenSSL 문서 기준으로도 기본 암호 알고리즘은 AES-256-CBC + PBKDF2라고 적혀 있습니다.[^6] 반대로 `-legacy`를 켜면 certificate 암호화가 RC2/3DES로 내려가는 동작이 명시돼 있습니다.[^6]

이 차이를 서비스 리팩터링의 체크리스트로 바꾸면 아래처럼 됩니다.

- “서비스 코드 개선”으로 해결할 문제인가? 
  - 대부분은 아니다. PFX 아티팩트 자체를 현대 암호로 바꾸는 게 비용 대비 효과가 좋다.
- “운영 문서/발급 파이프라인 개선”으로 해결할 문제인가?
  - 대부분은 그렇다.

### 패스워드 인코딩 함정(UTF-8)

OpenSSL의 `PKCS12_parse()` 문서에는 passphrase가 UTF-8 문자열로 해석되며, 유효한 UTF-8이 아니면 ISO8859-1로 간주한다고 되어 있습니다.[^7] 그리고 로케일 문자셋(Windows code page 포함)에서 UTF-8 변환이 필요할 수 있다고도 말합니다.[^7]

이게 서비스 코드에 주는 시사점은 명확합니다.

- “사람이 타이핑한 패스워드”를 여기저기 복사/붙여넣기로 전달하면, 환경/터미널/로케일에 따라 **같은 글자가 다른 바이트**가 될 수 있습니다.
- 따라서 passphrase를 사람이 수동으로 관리하는 모델(운영자가 Slack에서 복사해 붙여넣는 방식)은 PKCS#12에서 특히 사고가 납니다.

나는 여기서 운영 합의를 이렇게 가져갑니다.

- 패스워드는 사람이 직접 다루지 않게 한다. Secret manager(또는 최소한 sealed secret/SOPS)에서만 생성/회전.
- 패스워드는 ASCII 범위로 제한(특히 이행기에는). 조직 합의가 어렵다면 최소한 “NFKC normalize” 같은 변환을 넣는 것도 고려 대상이지만, 이건 또 다른 호환성 이슈가 생깁니다.

### 레거시 인코딩 호환을 위한 heuristic은 MT-safe가 아니라는 경고

OpenSSL `openssl pkcs12` 문서에는, 과거 비-ASCII 패스워드 인코딩 호환을 위해 레거시 인코딩을 시도하는 heuristic 접근이 들어 있으며, 이 접근은 MT-safe가 아니라고 적혀 있습니다. 운영에서 PKCS#12를 쓴다면 변환을 권장한다고까지 말합니다.[^6]

이 문장은 “서버 프로세스가 pkcs12를 파싱할 때 무조건 thread-unsafe하다” 같은 식으로 단정하면 곤란하지만, 최소한의 메시지는 받는 게 좋습니다.

- 레거시 호환성에 기대는 운영은 비용이 계속 증가한다.
- ‘변환(재-export)’은 보안과 운영 안정성을 같이 올리는 방향이다.

## 실행 가능한 리팩터링: parsePKCS12()로 mTLS 클라이언트 자격증명 파이프라인 고정하기

여기서는 “내부 서비스가 외부(혹은 사내) API를 mTLS로 호출하는” 케이스를 기준으로, PKCS#12를 읽어 `https.Agent`에 넣을 수 있는 형태로 변환하고, 회전까지 고려한 구조로 정리합니다.

요점은 이렇습니다.

- PKCS#12는 `crypto.parsePKCS12()`로 딱 한 번만 파싱한다.
- 파싱 결과는 검증하고, 로그에는 fingerprint만 남긴다.
- TLS 옵션에는 결국 key/cert/ca(PEM)를 넣되, 변환 과정에서 노출 면적을 최소화한다.

### 테스트용 인증서/키스토어 만들기(OpenSSL)

Node TLS 문서에도 `.pfx/.p12` 생성 예시가 `openssl pkcs12 -export` 형태로 들어 있습니다.[^4] 여기서는 좀 더 현실적으로 CA를 만들고 server/client cert를 각각 발급합니다.

아래는 macOS/Linux 기준입니다.

```bash
mkdir -p certs
cd certs

# 1) Root CA
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -subj "/CN=local-dev-ca" \
  -out ca.crt

# 2) Server key/cert
openssl genrsa -out server.key 2048
openssl req -new -key server.key -subj "/CN=localhost" -out server.csr
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 365 -sha256

# 3) Client key/cert
openssl genrsa -out client.key 2048
openssl req -new -key client.key -subj "/CN=mtls-client" -out client.csr
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out client.crt -days 90 -sha256

# 4) Client PKCS#12 (암호화 필수)
# OpenSSL 문서상 기본 암호 알고리즘은 AES-256-CBC + PBKDF2 입니다.[^6]
export P12_PASSWORD='dev-password-change-me'

openssl pkcs12 -export \
  -out client.p12 \
  -inkey client.key \
  -in client.crt \
  -certfile ca.crt \
  -passout pass:"$P12_PASSWORD"

# 패스워드를 파일로도 저장(쿠버네티스 Secret 마운트 흉내)
printf "%s" "$P12_PASSWORD" > client.p12.pass
chmod 600 client.p12.pass
```

여기서 생성한 `client.p12`는 다음 내용을 포함합니다.

- private key 1개
- client leaf certificate 1개
- additionalCertificates: ca.crt

### 프로젝트 구성

Node 26.10.0 이상을 가정합니다.

```bash
mkdir -p pkcs12-demo
cd pkcs12-demo
npm init -y
npm pkg set type=module
npm pkg set engines.node=">=26.10.0"

mkdir -p src
cp -R ../certs ./certs
```

`package.json`에 스크립트를 추가합니다.

```json
{
  "name": "pkcs12-demo",
  "private": true,
  "type": "module",
  "engines": {
    "node": ">=26.10.0"
  },
  "scripts": {
    "server": "node src/mtls-server.mjs",
    "client": "node src/mtls-client.mjs",
    "inspect": "node src/inspect-p12.mjs"
  }
}
```

### PKCS#12 로더 모듈(src/pkcs12-loader.mjs)

- 입력은 파일 경로만 받습니다.
- passphrase는 “필수”로 강제합니다.
- 파싱 직후 원본 p12 Buffer와 passphrase Buffer는 `fill(0)`로 overwrite합니다(완벽한 보안 삭제는 아니지만, 노출면을 줄이는 방향입니다).
- 인증서 PEM은 `X509Certificate.toString()`을 사용합니다.[^5]

```js
// src/pkcs12-loader.mjs
import { parsePKCS12, createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

function trimSingleTrailingNewline(s) {
  // Secret volume에 마운트된 파일은 마지막에 \n이 붙는 경우가 많습니다.
  return s.replace(/\r?\n$/, '');
}

export async function loadIdentityFromPkcs12({
  p12Path,
  passphrasePath,
  maxBytes = 256 * 1024,
  requirePassphrase = true,
}) {
  const [p12Buf, passBuf] = await Promise.all([
    readFile(p12Path),
    readFile(passphrasePath),
  ]);

  try {
    if (p12Buf.byteLength === 0) {
      throw new Error('PKCS#12 bundle is empty');
    }
    if (p12Buf.byteLength > maxBytes) {
      throw new Error(`PKCS#12 bundle is too large: ${p12Buf.byteLength} bytes`);
    }

    let passphrase = trimSingleTrailingNewline(passBuf.toString('utf8'));

    // Node 문서: passphrase 생략은 ''과 동일[^5]
    // 그래서 여기서는 정책으로 강제합니다.
    if (requirePassphrase && passphrase.length === 0) {
      throw new Error('Passphrase is required by policy');
    }

    const { privateKey, certificate, additionalCertificates } = parsePKCS12(p12Buf, {
      passphrase,
    });

    if (!privateKey) {
      throw new Error('PKCS#12 bundle does not contain a private key');
    }
    if (!certificate) {
      throw new Error('PKCS#12 bundle does not contain a matching certificate');
    }

    // X509Certificate API: validTo/validToDate 제공[^5]
    const now = Date.now();
    const notAfter = certificate.validToDate?.getTime?.() ?? Date.parse(certificate.validTo);
    if (Number.isFinite(notAfter) && notAfter < now) {
      throw new Error(`Certificate already expired at ${certificate.validTo}`);
    }

    // 로깅은 fingerprint만
    const fingerprint256Hex = createHash('sha256').update(certificate.raw).digest('hex');

    // TLS/https는 일반적으로 PEM을 기대합니다.
    // tls.createSecureContext() 문서에도 key/cert는 PEM 기반 설명이 우선입니다.[^4]
    const keyPem = privateKey.export({
      format: 'pem',
      type: 'pkcs8',
    });

    // X509Certificate.toString()은 PEM을 반환합니다.[^5]
    const leafCertPem = certificate.toString();
    const chainPem = additionalCertificates.map((c) => c.toString()).join('');

    return {
      fingerprint256Hex,
      keyPem,
      certPem: leafCertPem + chainPem,
      // 이 예제에서는 additionalCertificates를 그대로 CA로도 사용합니다.
      // 실제 운영에서는 "server trust"와 "client chain"을 분리하는 편이 안전합니다.
      caPemList: additionalCertificates.map((c) => c.toString()),
      notAfter: certificate.validTo,
      keyType: privateKey.asymmetricKeyType,
      additionalCertCount: additionalCertificates.length,
    };
  } finally {
    // best-effort overwrite
    p12Buf.fill(0);
    passBuf.fill(0);
  }
}
```

이 로더는 일부러 “편의 기능”을 넣지 않았습니다.

- base64 환경변수를 받아주기 시작하면 입력 경로가 늘고, 로그/오류 메시지/관측 도구에서 노출 가능성이 급증합니다.
- passphrase를 optional로 두면 결국 빈 문자열이 운영에 들어옵니다(문서상 생략 = `''`).[^5]

### PKCS#12 내용 점검 도구(src/inspect-p12.mjs)

운영에서는 이런 도구가 종종 필요합니다.

- 어떤 키 타입인지
- 체인이 몇 개인지
- 만료가 언제인지

단, 여기서도 **키/인증서 전체를 출력하지 않는 것**이 중요합니다.

```js
// src/inspect-p12.mjs
import { loadIdentityFromPkcs12 } from './pkcs12-loader.mjs';

const identity = await loadIdentityFromPkcs12({
  p12Path: 'certs/client.p12',
  passphrasePath: 'certs/client.p12.pass',
  requirePassphrase: true,
});

console.log(JSON.stringify({
  fingerprint256: identity.fingerprint256Hex,
  keyType: identity.keyType,
  notAfter: identity.notAfter,
  additionalCertCount: identity.additionalCertCount,
}, null, 2));
```

예상 출력은 대략 이런 형태입니다.

```json
{
  "fingerprint256": "...",
  "keyType": "rsa",
  "notAfter": "Dec 31 23:59:59 2026 GMT",
  "additionalCertCount": 1
}
```

### mTLS 서버(src/mtls-server.mjs)

서버는 client cert를 요구하도록 구성합니다.

```js
// src/mtls-server.mjs
import https from 'node:https';
import { readFileSync } from 'node:fs';

const server = https.createServer({
  key: readFileSync('certs/server.key'),
  cert: readFileSync('certs/server.crt'),

  // client 인증서 검증
  requestCert: true,
  rejectUnauthorized: true,
  ca: [readFileSync('certs/ca.crt')],
}, (req, res) => {
  res.writeHead(200, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ ok: true }));
});

server.listen(8443, '127.0.0.1', () => {
  console.log('mTLS server listening on https://127.0.0.1:8443');
});
```

### mTLS 클라이언트(src/mtls-client.mjs)

클라이언트는 `parsePKCS12()`로 client identity를 로딩한 뒤, 그 결과로 agent를 구성합니다.

```js
// src/mtls-client.mjs
import https from 'node:https';
import { loadIdentityFromPkcs12 } from './pkcs12-loader.mjs';

const identity = await loadIdentityFromPkcs12({
  p12Path: 'certs/client.p12',
  passphrasePath: 'certs/client.p12.pass',
  requirePassphrase: true,
});

// 관측은 fingerprint만
console.log(`client identity loaded: sha256=${identity.fingerprint256Hex} keyType=${identity.keyType} notAfter=${identity.notAfter}`);

const agent = new https.Agent({
  key: identity.keyPem,
  cert: identity.certPem,
  ca: identity.caPemList,
  keepAlive: true,
});

const req = https.request({
  method: 'GET',
  host: '127.0.0.1',
  port: 8443,
  path: '/',
  agent,
}, (res) => {
  let body = '';
  res.setEncoding('utf8');
  res.on('data', (chunk) => { body += chunk; });
  res.on('end', () => {
    console.log('status:', res.statusCode);
    console.log('body:', body);
    agent.destroy();
  });
});

req.on('error', (err) => {
  console.error('request failed:', err.message);
  agent.destroy();
});

req.end();
```

실행 순서는 다음입니다.

```bash
# 터미널 1
npm run server

# 터미널 2
npm run client
```

정상이라면 클라이언트에서 200과 `{"ok":true}`가 찍힙니다.

여기까지가 “PKCS#12 파싱 경로를 서비스 코드 내 표준 모듈로 고정”하는 1차 리팩터링입니다.

## 메모리/로그 노출을 줄이는 구현 디테일

PKCS#12 처리는 결국 private key를 다룹니다. Node.js에서 이 문제를 완벽히 해결하는 건 불가능에 가깝습니다(가비지 컬렉션, 문자열/Buffer 복사, 런타임 내부 구현 등). 대신 내가 현실적으로 지키는 규율을 정리하면 다음과 같습니다.

### 1) 키 재료를 문자열로 만들지 않는다

- private key는 `KeyObject`로만 들고 있다가, TLS 옵션에 넣기 위해 export가 필요하면 **Buffer 형태로 export**하고 수명을 짧게 둡니다.
- 인증서는 `toString()`이 PEM 문자열이긴 하지만, 인증서는 공개 정보라(대개) private key보다 민감도가 낮습니다. 그럼에도 운영 로그에 PEM 전체를 남기지 않습니다.

X509Certificate의 `toString()`이 PEM-encoded certificate를 반환한다는 건 Node 문서에 명시돼 있습니다.[^5] 그래서 “외부 라이브러리로 PEM 변환”을 추가할 이유가 줄어듭니다.

### 2) 에러 메시지에 passphrase를 절대 섞지 않는다

PKCS#12 파싱 실패는 흔히 “암호 틀림 / 레거시 알고리즘 / 손상된 번들”입니다. 이때 예외를 감싸면서 디버깅 목적으로 passphrase 길이/일부/해시를 섞는 팀이 있는데, 운영에서 반드시 사고로 이어집니다.

내가 하는 방식은 단순합니다.

- 사용자/외부 호출자에게는 일반화된 에러 코드만.
- 내부 로그에도 passphrase 관련 데이터는 남기지 않음.
- 대신 fingerprint(sha256) + Secret 버전(후술) 같은 **비밀이 아닌 식별자**를 남김.

### 3) 입력 자체를 “가능한 trusted local source”로 제한한다

Node.js 프로젝트의 OpenSSL Advisory Assessment에서도 “Node.js가 PFX(PKCS#12) 파일을 처리하는 방식과 관련된 취약점”이 존재하며, 공격자가 조작된 PFX를 제공해야 트리거된다는 식으로 공격면을 설명합니다. 또한 PFX는 보통 로컬의 신뢰된 소스에서 온다고 덧붙입니다.[^1]

이 문장을 운영 정책으로 바꾸면 아래가 됩니다.

- PKCS#12 입력 경로는 로컬 파일(Secret volume)로 제한.
- 외부 요청으로 받은 파일을 곧바로 parsePKCS12에 넣지 않음.
- CI/CD에서 생성한 artifact만 허용.

### 4) passphrase 파일/버퍼 overwrite는 “완벽한 삭제”가 아니라 “노출 창을 줄이는 조치”로 본다

`Buffer.fill(0)` 같은 overwrite는 best-effort입니다.

- 이미 다른 곳으로 복사됐을 수 있습니다.
- Node 내부로 전달되면서 C++ 레이어에서 별도 복사가 일어날 수도 있습니다.

그럼에도 불구하고 “그냥 둔다”보다 나은 점은 명확합니다.

- 코어 덤프/heap dump/크래시 리포트에서 우연히 노출될 확률을 조금이라도 줄입니다.
- 코드 리뷰에서 “민감정보 수명”을 의식하게 만듭니다.

## 운영 관점: 시크릿 배포/회전, 그리고 무중단 적용

PKCS#12를 코드 레벨에서 안전하게 처리해도, 운영이 따라주지 않으면 결론은 같아집니다. 특히 mTLS client cert 회전은 “서비스 코드 + 배포 도구 + 런타임 재로딩”이 동시에 맞아야 합니다.

여기서 핵심은 두 축입니다.

- 배포/회전 도구는 새로운 Secret을 배포할 수 있어야 한다.
- 애플리케이션은 그 변화를 적용할 수 있어야 한다(재시작 또는 핫리로드).

### Secret 배포 형태: p12 파일과 passphrase 파일을 분리한다

- `client.p12`: 바이너리
- `client.p12.pass`: 짧은 텍스트(개행 포함 가능)

분리하는 이유는 단순합니다.

- 운영자가 passphrase만 바꿔야 하는 경우(키는 그대로, 포맷만 다시 export)가 생깁니다.
- base64 환경변수 하나에 다 넣으면 변경 영향 범위가 커집니다.

### 회전 적용 방식 1: 롤링 재시작(대부분의 팀에 가장 낫다)

핫리로드는 구현 난이도와 장애 가능성이 높습니다. 인증서 회전 주기가 “수 주~수 개월”이라면 롤링 재시작이 압도적으로 단순합니다.

Kubernetes 관점에서도 Secret/CA 데이터가 바뀌면 “결국 파드를 재시작해야 새 Secret을 집어드는” 흐름이 자주 등장합니다. Kubernetes 문서에서도 CA rotation 과정에서 “Secret을 픽업하기 위해 파드를 재시작해야 한다”는 취지의 단계가 명시됩니다.[^8]

여기서 내가 지키는 룰은 다음입니다.

- **Secret 업데이트 → 배포(rolling restart)**를 자동화한다.
- 인증서 만료가 임박해서야 움직이지 않게, notAfter 기준으로 선제 회전을 한다.

### 회전 적용 방식 2: 프로세스 내 핫리로드(필요할 때만)

핫리로드가 필요한 케이스는 보통 아래입니다.

- 수천 파드 롤링이 비용이 큰 플랫폼
- 외부 규정/감사 요구로 client cert를 짧은 주기로 회전
- 단일 프로세스가 수많은 outbound connection을 유지하는 에이전트형 서비스

Node TLS 서버는 `server.setSecureContext()`로 기존 서버의 secure context를 교체할 수 있고, 문서에 “Existing connections … not interrupted”라고 명시돼 있습니다.[^4]

다만 여기에는 함정이 있습니다.

- “기존 연결이 끊기지 않는다”는 건, keep-alive 연결이 오래 유지되면 **예전 인증서로도 꽤 오래 통신할 수 있다**는 뜻입니다.
- client 측 회전에서는 `https.Agent`를 교체하더라도 기존 소켓이 살아 있으면 old identity가 사용될 수 있습니다.

내가 핫리로드를 구현할 때는 대개 아래 전략을 씁니다.

- Secret 업데이트 감지(fs.watch 등) → 새 identity 로딩 → 새 agent/context 생성
- 교체 이후 일정 시간 뒤 old agent를 `destroy()` (또는 keep-alive를 짧게)
- 가능하면 회전 시점에 outbound connection을 한번 drain(요청 실패를 최소화)

핫리로드 구현은 환경마다 파일 이벤트의 신뢰성이 달라서(특히 Secret volume), “감지 실패해도 결국 만료 전에 재시작이 걸리는” 안전장치를 같이 둡니다.

## 반론과 회의론: parsePKCS12()가 TLS의 pfx 옵션을 대체하는가

여기서 흔히 나오는 반론은 정확합니다.

- 이미 Node TLS는 `pfx` 옵션으로 PKCS#12를 처리한다.[^4]
- 굳이 `parsePKCS12()`로 파싱한 뒤 key/cert로 변환하는 게 더 안전하냐는 보장은 없다.

내 판단은 다음에 가깝습니다.

- `pfx` 직결은 “TLS 컨텍스트 생성”이라는 큰 작업 안에 파싱이 숨어 들어가서, **입력 검증/관측/정책 강제**를 걸기가 어렵습니다.
- `parsePKCS12()`는 파싱을 함수 경계로 꺼내주기 때문에, 그 경계에서
  - 크기 제한
  - passphrase 필수 강제
  - 인증서 만료/체인 구성 검증
  - 로깅 정책(PEM 금지, fingerprint만)
  - 회전 정책
  을 일관되게 적용할 수 있습니다.

즉 대체라기보다 “경계 분리”가 핵심입니다.

그리고 이 경계 분리는 런타임 업그레이드 때도 효과가 큽니다. OpenSSL 버전이 바뀌면 레거시 알고리즘 처리/에러 코드가 바뀔 수 있는데, 그런 변화가 TLS 컨텍스트 생성 시점에만 나타나면 트러블슈팅이 어려워집니다. parse 경계를 따로 두면 “파싱 실패”를 더 앞단에서 더 좋은 메시지로 잡을 수 있습니다.

## 도입 판단 기준

정리하면, `crypto.parsePKCS12()`는 다음 조건에서 도입 가치가 큽니다.

1) PKCS#12를 다루는 서비스가 여러 개고, 각자 처리 방식이 제각각이다.

2) 인증서/키가 운영 상 중요한 계약이다.

- mTLS client identity가 실제 보안 경계라면, “키스토어 입력 검증”은 애플리케이션 품질의 일부입니다.

3) 회전(배포/재시작/핫리로드)을 체계로 만들고 싶다.

- 파싱 경계를 분리하면, fingerprint/만료일/체인 카운트 같은 메타데이터를 운영 신호로 만들 수 있습니다.

반대로 아래 상황이면 도입 우선순위가 낮습니다.

- PKCS#12는 한 군데에서만 쓰고, 이미 발급/배포가 안정적이다.
- 실질적인 문제는 PKCS#12 파싱이 아니라 “CA/trust model 정리”다. 이 경우는 예전에 [App Engine(Go)의 TLS 1.1 이하 차단에 대비한 트래픽 계측과 단계적 종료](https://daewooki.github.io/posts/app-engine-tls11-cutoff-traffic-audit/)에서 적었던 것처럼, 런타임 기능보다 트래픽/호환성/정책이 문제의 중심일 때가 많습니다.

결국 `parsePKCS12()`는 기능 하나가 아니라, PKCS#12를 둘러싼 입력 경로와 운영 계약을 서비스 코드로 끌어오는 계기입니다. 그 계기를 살릴지 말지는 “외부 라이브러리 제거”가 아니라 “PKI를 애플리케이션 품질 영역으로 편입할 것인지”에 달려 있습니다.

## 참고 자료

- [Node.js 26.10.0 릴리스 노트](https://nodejs.org/en/blog/release/v26.10.0)
- [nodejs/node GitHub Releases](https://github.com/nodejs/node/releases)
- [Node.js crypto.parsePKCS12() API 문서(crypto.md)](https://github.com/nodejs/node/blob/main/doc/api/crypto.md?plain=1)
- [Node.js TLS 문서(tls.createSecureContext, pfx 옵션)](https://nodejs.org/api/tls.html)
- [Node.js OpenSSL Security Advisory Assessment, January 2026](https://github.com/nodejs/nodejs.org/blob/main/apps/site/pages/en/blog/vulnerability/openssl-fixes-in-regular-releases-jan2026.md)
- [OpenSSL openssl-pkcs12(1) 문서](https://docs.openssl.org/3.3/man1/openssl-pkcs12/)
- [OpenSSL PKCS12_parse(3) 문서](https://docs.openssl.org/3.3/man3/PKCS12_parse/)
- [Kubernetes: Manual Rotation of CA Certificates](https://kubernetes.io/docs/tasks/tls/manual-rotation-of-ca-certificates/)

[^1]: <https://github.com/nodejs/nodejs.org/blob/main/apps/site/pages/en/blog/vulnerability/openssl-fixes-in-regular-releases-jan2026.md>
[^2]: <https://nodejs.org/en/blog/release/v26.10.0>
[^3]: <https://github.com/nodejs/node/releases>
[^4]: <https://nodejs.org/api/tls.html>
[^5]: <https://github.com/nodejs/node/blob/main/doc/api/crypto.md?plain=1>
[^6]: <https://docs.openssl.org/3.3/man1/openssl-pkcs12/>
[^7]: <https://docs.openssl.org/3.3/man3/PKCS12_parse/>
[^8]: <https://kubernetes.io/docs/tasks/tls/manual-rotation-of-ca-certificates/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
