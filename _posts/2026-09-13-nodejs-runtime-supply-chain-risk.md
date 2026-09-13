---
title: "Node.js 26.8.2 업그레이드를 공급망 위험으로 해석하기"
description: "Node.js 26.8.2는 기능보다 OpenSSL/Undici/npm/corepack 업데이트가 본질입니다. 운영 기준을 위험 관리 관점에서 다시 잡아봅니다."
date: 2026-09-13 09:57:37 +0900
categories: ["News", "Languages"]
tags: ["nodejs", "openssl", "undici", "supply-chain", "npm", "corepack"]
render_with_liquid: false
---

## 2026-09-09 Node.js 26.8.2에서 실제로 바뀐 것

2026-09-09에 Node.js 26.8.2(Current)가 릴리스됐고, Notable Changes에 올라온 항목은 네 가지뿐입니다. 그중 운영에 직접적으로 의미가 큰 건 세 가지입니다. [Node.js 26.8.2 릴리스 노트](https://nodejs.org/en/blog/release/v26.8.2)

- OpenSSL 3.5.8로 업데이트
- Undici 8.10.2로 업데이트
- 실험 기능에 대한 보안 취약점 처리 태도 정리

그리고 커밋 목록에는 운영팀이 체감하는 파급이 더 큰 두 항목이 숨어 있습니다.

- npm 11.19.1로 업데이트
- corepack 0.36.0으로 업데이트

이 조합이 의미하는 바는 단순합니다. 이번 패치 업그레이드는 JavaScript 언어 런타임을 올리는 행위가 아니라, **crypto/http client/package manager라는 공급망 경계**를 한 번에 재정렬하는 이벤트입니다. 기능 릴리스처럼 다루면 이 경계에서 발생하는 회귀(regression)와 재현성 붕괴를 뒤늦게 맞게 됩니다.

## Current 라인에서 패치 업그레이드가 더 위험해지는 구조

Node.js 26은 2026-05-05에 26.0.0(Current)로 시작했고, 프로젝트는 Current 기간이 약 6개월이며 10월에 LTS로 전환된다고 반복해서 말해왔습니다. [Node.js 26.0.0 릴리스 노트](https://nodejs.org/en/blog/release/v26.0.0)

Release WG의 일정 표에서도 26.x Current 기간과 LTS 전환 시점이 명시돼 있습니다. (일정은 변경될 수 있으니 원문 표를 기준으로 봐야 합니다.) [Node.js Release Working Group 일정](https://github.com/nodejs/Release)

Current 라인은 “변화를 빨리 받는 대신, 업그레이드 비용을 자주 낸다”는 선택입니다. 보통 기능 변화는 앱 레벨에서 테스트로 잡히는 편인데, 문제는 런타임이 끌어안고 있는 다음 두 덩어리입니다.

1) crypto(OpenSSL) 변경

- TLS handshake, certificate parsing, cipher suite 처리, 서명/검증 경로가 바뀌면 애플리케이션 코드는 그대로인데 운영 트래픽에서만 실패합니다.
- 특히 mTLS, 프록시 체인, 오래된 중간 인증서, 비표준 확장 등을 만나는 순간 증상이 튀어나옵니다.

2) HTTP client(Undici) 변경

- Node 내장 fetch의 실질 구현체가 바뀌는 것과 같습니다.
- keep-alive, connection pooling, proxy, redirect, header parsing, WebSocket, 압축 해제, 캐시 인터셉터 같은 면적에서 취약점과 회귀가 같이 움직입니다.

여기에 npm/corepack까지 동시 업데이트가 걸리면, 런타임 업그레이드가 CI/CD의 재현성에도 바로 영향을 줍니다. 이 지점에서 업그레이드를 “기능”으로 보는 관점이 무너집니다.

## OpenSSL 3.5.8: Node 패치 하나가 TLS를 바꿔버리는 이유

Node.js는 OpenSSL을 외부 라이브러리로 단순 링크하는 제품이 아니라, 배포물에 OpenSSL을 포함해서 움직이는 런타임에 가깝습니다. 그래서 Node 26.8.2의 OpenSSL 3.5.8 반영은, 서비스 입장에서 “OS 업데이트”가 아니라 “애플리케이션 런타임 업데이트”로 들어옵니다. [Node.js 26.8.2 릴리스 노트](https://nodejs.org/en/blog/release/v26.8.2)

OpenSSL 3.5.8은 2026-08-25에 나온 릴리스로, OpenSSL 3.5(LTS) 라인에 속합니다. 다운로드 페이지에는 3.5가 LTS이며 지원 종료가 2030-04-08로 표시되어 있습니다. [OpenSSL 다운로드 페이지(3.5.8 포함)](https://www.openssl-library.org/source/)

OpenSSL은 2026-08-25에 보안 권고(Security Advisory)도 함께 공지했고, 타임라인에 3.5.8과 Security Advisory가 같이 나열되어 있습니다. [OpenSSL Release and Advisory Timeline](https://mirror.openssl-library.org/news/timeline/)

이번 조합에서 운영자가 봐야 하는 건 “3.5.8로 올라갔다”가 아니라 “Node 26.8.2가 2026-09-09에 3.5.8을 포함했다”는 속도입니다. OpenSSL 권고가 나온 지 2주 남짓 후에 런타임이 따라잡은 겁니다. 공급망 관점에서는 장점이고, 회귀 관점에서는 리스크가 됩니다.

구체적으로 OpenSSL 3.5.8 보안 권고에는 CMS_decrypt() 경로에서의 heap out-of-bounds write(고정 크기 8바이트, 주로 DoS로 이어짐) 같은 내용이 포함되어 있습니다. [OpenSSL Security Advisory(2026-08-25, oss-security 미러)](https://www.openwall.com/lists/oss-security/2026/08/25/3)

또 다른 항목으로는 Raw Public Key 관련 취약점(CVE-2026-14457)이 타임라인에 등장합니다. 이게 내 서비스에 직접 해당되는지는 별개지만, 핵심은 “TLS/crypto는 취약점 공지와 런타임 업그레이드가 묶여서 움직인다”는 사실입니다. [OpenSSL Release and Advisory Timeline](https://mirror.openssl-library.org/news/timeline/)

내 경우 OpenSSL 업그레이드를 다룰 때는 다음 질문을 먼저 던집니다.

- 내 서비스는 mTLS를 쓰는가
- 프록시/게이트웨이가 TLS를 terminate하는가(그리고 어디까지가 내 책임인가)
- certificate chain이 표준대로 정리돼 있는가(사내 CA 포함)
- 특정 cipher suite나 signature algorithm을 고정하고 있는가
- OpenSSL 3.0 EOL 같은 이벤트에 대비해 런타임 퇴역 시나리오가 있는가

OpenSSL 3.0 EOL 이후 런타임을 어떻게 퇴역시키는지에 대해서는 예전에 운영 설계를 따로 정리한 적이 있습니다. 이 글의 맥락에서 다시 필요한 부분만 연결해두면, “OpenSSL이 바뀌면 런타임을 같이 바꿔야 한다”는 구조가 유지된다는 점입니다. [OpenSSL 3.0 EOL 이후 런타임을 안전하게 퇴역시키는 운영 설계](https://daewooki.github.io/posts/retire-openssl-3-0-safely/)

## Undici 8.10.2: 내장 fetch를 ‘의존성 업데이트’로 취급하면 생기는 착시

Node.js 26.8.2는 Undici를 8.10.2로 올렸습니다. 이건 단순히 “내장 fetch 버그 픽스”가 아니라, HTTP 스택의 보안 모델이 바뀌는 쪽에 가깝습니다. [Node.js 26.8.2 릴리스 노트](https://nodejs.org/en/blog/release/v26.8.2)

Undici 자체 릴리스 기준으로 보면 8.10.2는 2026-09-04에 릴리스됐고, 릴리스 노트의 첫 머리부터 Security fixes가 정리돼 있습니다. [Undici v8.10.2 릴리스](https://github.com/nodejs/undici/releases/tag/v8.10.2)

릴리스 노트를 읽으면 이 버전이 무엇을 “고쳤다”가 아니라 무엇을 “막았다”에 초점이 있다는 게 드러납니다.

- cache/deduplication interceptor가 dispatcher origin 대신 caller-controlled metadata를 사용해 cross-origin cache poisoning과 데이터 노출로 이어질 수 있었고, 이를 막기 위해 interceptor identity를 dispatcher origin에서 유도하도록 바꿨습니다.
- BalancedPool이 연결 옵션을 복제할 때 function-valued 옵션(예: custom TLS certificate validation callback)을 떨어뜨릴 수 있었고, connect/tls 옵션 보존으로 수정됐습니다.
- WebSocket handshake 과정에서 요청되지 않은 subprotocol을 선택할 수 있어 uncaught TypeError로 프로세스 종료까지 갈 수 있었고, 핸드셰이크를 프로토콜 에러로 거절하도록 바뀌었습니다.
- shared cache가 Set-Cookie가 포함된 응답을 저장/재생해 쿠키가 다른 호출자에게 노출될 수 있었고, Set-Cookie 포함 응답을 shared cache에서 배제하도록 바뀌었습니다.

이런 성격의 변화는 두 가지 운영 결론으로 이어집니다.

1) 최신 Undici로 올리는 건 기능이 아니라 공격 표면을 줄이는 행위입니다.

Undici 8.10.2 릴리스의 대부분은 “정상적인 트래픽에서 거의 안 보일 수도 있는 케이스”를 다룹니다. 그런데 이런 케이스는 공격자가 좋아하는 케이스이기도 합니다. 보안 패치가 잦은 HTTP client를 런타임에 내장해 쓰는 순간, 런타임 업그레이드는 곧 HTTP 공급망 패치가 됩니다.

2) 동시에 회귀 가능성이 넓습니다.

cache interceptor, retry interceptor, decompression 같은 건 서비스에 따라 사용 여부가 갈립니다. 그런데 조직 내 어딘가에서는 이미 쓰고 있을 확률이 높습니다. “우리 서비스는 fetch만 쓴다”는 말이 더 이상 안전한 축약이 아닙니다. 같은 Node 버전이라도 어떤 팀은 undici를 직접 import해서 interceptor를 쓰고, 다른 팀은 내장 fetch만 쓰고, 또 다른 팀은 프록시 환경에서만 장애를 겪습니다.

Undici의 이런 변화는 애플리케이션 레벨 unit test로는 잘 잡히지 않습니다. synthetic monitoring이나 canary에서야 튀어나오는 유형입니다.

## npm 11.19.1: 런타임 업그레이드가 설치 정책을 바꾸는 순간

Node.js 26.8.2 커밋 목록에는 npm 11.19.1 업그레이드가 포함됩니다. [Node.js 26.8.2 릴리스 노트](https://nodejs.org/en/blog/release/v26.8.2)

npm 11.19.1은 2026-08-25자로 changelog에 올라와 있고, allow-directory 관련 버그 픽스와 몇 가지 의존성 업데이트가 명시돼 있습니다. [npm CLI v11 changelog(11.19.1)](https://docs.npmjs.com/cli/v11/using-npm/changelog/)

여기서 공급망 관점으로 눈에 띄는 건, npm 자체가 네트워크 스택을 내장하고 있다는 사실이 다시 드러난다는 점입니다. npm 11.19.1의 Dependencies에는 undici@6.28.0 업데이트가 포함돼 있습니다. [npm CLI v11 changelog(11.19.1 Dependencies)](https://docs.npmjs.com/cli/v11/using-npm/changelog/)

즉 Node 26.8.2를 올리면 HTTP 관련 변경이 두 갈래로 들어옵니다.

- 런타임 내장 fetch/undici: Undici 8.10.2
- npm이 사용하는 undici: 6.28.0

운영에서 이게 왜 중요하냐면, 장애의 표면이 애플리케이션 요청뿐 아니라 “빌드/배포 파이프라인의 네트워크 요청”까지 같이 흔들리기 때문입니다. artifact download가 프록시를 통과한다거나, 사내 registry가 특이한 TLS 구성을 갖는다거나, 패키지 무결성 검증이 강해지는 순간 설치가 깨집니다.

또 하나는 install script 정책입니다. npm v11 changelog에는 approve-scripts/deny-scripts, allowScripts 같은 설치 단계의 정책 기능이 꾸준히 언급됩니다. 예를 들어 approve-scripts/deny-scripts가 dotted/versioned args를 매칭한다거나, ignore-scripts 모드에서 pending scripts를 나열한다거나 하는 변화가 있습니다. [npm CLI v11 changelog(approve-scripts/allowScripts 관련 항목)](https://docs.npmjs.com/cli/v11/using-npm/changelog/)

이 변화는 보안적으로는 좋은 방향이지만, 운영적으로는 재현성의 적이 될 수도 있습니다.

- 어떤 환경에서는 install script를 더 강하게 차단해서 빌드가 실패하고
- 어떤 환경에서는 허용해서 빌드가 통과하며
- 결과적으로 lockfile은 같아도 산출물은 달라지는 상황이 생깁니다.

내가 런타임 업그레이드 체크리스트에 npm 버전을 반드시 포함하는 이유가 여기 있습니다. Node를 올렸는데 빌드만 깨지는 문제는 “CI 문제”가 아니라 “공급망 업데이트를 숨긴 런타임 업데이트 문제”인 경우가 많습니다.

## corepack 0.36.0: 재현성 도구가 보안 도구가 되는 지점

Node.js 26.8.2는 corepack도 0.36.0으로 올렸습니다. [Node.js 26.8.2 릴리스 노트](https://nodejs.org/en/blog/release/v26.8.2)

corepack 0.36.0 자체 릴리스는 2026-08-28에 올라왔고, 릴리스 노트에 Features/Bug Fixes가 비교적 자세히 정리돼 있습니다. [corepack v0.36.0 릴리스](https://github.com/nodejs/corepack/releases/tag/v0.36.0)

이 버전에서 운영 관점으로 읽을 만한 항목은 다음 쪽입니다.

- COREPACK_ON_UNVERIFIED_DOWNLOAD 환경변수 추가
- version endpoint에서 dist.signatures가 없을 때 package-root metadata로 fallback
- registry URL 처리에서 trailing slash 제거
- devEngines 범위를 사용해 package manager 버전을 선택

corepack은 원래 재현성을 위한 도구로 많이 소개되지만, 실제 운영에서는 “조직이 어떤 package manager 바이너리를 실행하게 되는지”를 통제하는 보안 도구에 가깝습니다. 특히 corepack이 다운로드하는 바이너리는 Node 릴리스 아티팩트가 아니라, corepack이 해석한 메타데이터/서명/무결성 모델에 의해 결정됩니다.

한편 corepack의 배포 형태는 시기별로 혼선이 있었습니다. Node.js API 문서의 corepack 페이지는 현재 corepack GitHub로 리다이렉트되고, 그 README에는 “Node.js 14.19.0부터 25.0.0 미만까지 배포된다”는 문장이 들어 있습니다. [corepack README](https://github.com/nodejs/corepack)

그럼에도 Node 26.8.2 릴리스 노트에는 corepack 업데이트가 명시돼 있습니다. 이건 현실적인 운영 결론으로 이어집니다.

- 환경마다 corepack이 “있다/없다/있지만 비활성” 상태가 다를 수 있고
- Node 버전을 올렸다는 사실만으로 패키지 매니저 실행 경로가 바뀔 수 있으며
- 따라서 corepack은 Node 업그레이드의 부속물이 아니라 독립된 검증 대상이 됩니다.

## ‘실험 기능 보안 태도’ 정리: 취약점으로 다루지 않겠다는 선언의 의미

Node.js 26.8.2의 Notable Changes 중 하나는 “실험 기능에 대한 보안 취약점 처리 태도”를 다듬었다는 항목입니다. [Node.js 26.8.2 릴리스 노트](https://nodejs.org/en/blog/release/v26.8.2)

이 변화는 PR #65438에서 배경이 설명돼 있습니다. 핵심은 기존 정책이 runtime-flag로 gated 된 experimental 기능의 취약점도 유효한 보안 취약점으로 취급해왔고, 그게 개발/운영에 마찰을 만든다는 문제의식입니다. [nodejs/node PR #65438](https://github.com/nodejs/node/pull/65438)

PR 대화/커밋 메시지에 따르면 다음 방향으로 완화합니다.

- stability 1.0/1.1 범주의 runtime gated experimental 기능은, 안정 기능을 직접 침해하거나 우회로를 제공하는 경우가 아니면 보안 취약점으로 보지 않을 수 있다
- --experimental-* runtime flag로만 활성화되는 진행 중 기능에 대한 vuln report를 거절할 여지를 만든다
- QUIC/H3는 복잡성과 활발한 개발을 이유로, 당분간 vuln coverage에서 명시적으로 제외한다

이건 보안이 약해진다는 선언이라기보다, “Node.js 프로젝트의 threat model에서 무엇을 책임질 것인가”를 다시 그은 겁니다.

Node 저장소의 Security Policy에도 experimental/flagged 기능에 대한 유사한 관점이 이미 존재합니다. 예를 들어 compile-time flag나 V8 flag 뒤에 있는 기능 이슈는 bug bounty 대상이 아니라는 식으로, 실험 기능이 production ready가 아니며 보안 하드닝이 불완전할 수 있음을 인정합니다. [nodejs/node Security Policy](https://github.com/nodejs/node/security/policy)

운영 입장에서 이 변화가 중요한 이유는 따로 있습니다.

- “실험 기능은 취약점 대응 SLA가 다를 수 있다”는 신호가 더 명시적으로 드러났고
- 런타임에 실험 기능을 켜는 순간, 그 기능은 공급망 패치의 우선순위에서 밀릴 수 있으며
- 결국 실험 기능 사용 여부 자체가 운영 위험도에 직접 반영돼야 합니다.

나는 --experimental-* 플래그를 기능 플래그처럼 취급하지 않습니다. 운영에서는 그 자체가 보안 정책 플래그이기도 합니다.

## 운영에서의 업그레이드 기준: ‘자주 올리되, 자동으로 올리지 않는다’

Current 라인 패치 릴리스는 잦습니다. “잦다”는 사실 자체가 기준을 필요로 합니다. 특히 OpenSSL/Undici 같은 의존성 업데이트는 누적되기 전에 정리해야 합니다.

내가 Node Current 라인을 운영에 들고 있을 때 잡는 기준은 다음 축으로 나뉩니다.

### 1) 취약점 공지와 런타임 반영의 시간차를 SLO로 둔다

OpenSSL 3.5.8(2026-08-25)이 Node 26.8.2(2026-09-09)에 반영된 사례처럼, 런타임이 빠르게 따라오는 구간이 있습니다. [OpenSSL 다운로드/릴리스 정보](https://www.openssl-library.org/source/)와 [Node.js 26.8.2 릴리스 노트](https://nodejs.org/en/blog/release/v26.8.2) 사이의 시간차는 대응 속도 관점에서 참고할 만합니다.

다만 그 속도를 그대로 production rollout 속도로 가져가면 회귀를 맞습니다. 나는 “릴리스 반영 속도”와 “운영 반영 속도”를 분리합니다.

### 2) HTTP client 변경은 애플리케이션 테스트가 아니라 트래픽 기반 테스트로 본다

Undici 8.10.2의 변경들은 cache, WebSocket, decompression, retry, TLS 옵션 보존 같은 영역에 걸쳐 있습니다. [Undici v8.10.2 릴리스](https://github.com/nodejs/undici/releases/tag/v8.10.2)

이 영역은 unit test보다 canary, synthetic probe, 실제 외부 연동 API에 대한 계약 테스트에서 더 잘 잡힙니다.

### 3) npm/corepack은 빌드 재현성을 별도 산출물로 검증한다

Node 26.8.2는 npm 11.19.1과 corepack 0.36.0을 같이 움직였습니다. [Node.js 26.8.2 릴리스 노트](https://nodejs.org/en/blog/release/v26.8.2)

이 변화는 다음을 건드립니다.

- install script 정책(approve-scripts/allowScripts)
- npm 내부 네트워크 스택(undici 6.28.0)
- corepack이 다운로드하는 package manager의 신뢰 모델

그래서 런타임 업그레이드 PR 하나로 “빌드 산출물 재현성 검증”이 같이 따라야 합니다.

## 회귀를 재현하는 현실적인 점검 코드

아래는 내가 최소한으로 두는 회귀 점검 골격입니다. 핵심은 두 가지입니다.

- 런타임 자체의 crypto/http 스택 버전을 로그로 고정한다
- 실제 운영에서 자주 터지는 TLS/HTTP 실패 형태를 의도적으로 만들어서 비교한다

테스트는 로컬에서 재현 가능해야 하고, 외부 인터넷에 덜 의존해야 합니다.

### 프로젝트 구성

- Node.js: 26.8.2에서 실행(비교군은 26.8.1 등 직전 버전)
- 의존성: 없음(내장 모듈만)

파일 구조는 다음처럼 둡니다.

```text
runtime-probe/
  package.json
  probes/
    versions.mjs
    tls-server.mjs
    tls-client.mjs
    http-server.mjs
    http-client.mjs
```

### package.json

```json
{
  "name": "runtime-probe",
  "private": true,
  "type": "module",
  "engines": {
    "node": ">=26.0.0"
  },
  "scripts": {
    "probe:versions": "node probes/versions.mjs",
    "probe:tls:server": "node probes/tls-server.mjs",
    "probe:tls:client": "node probes/tls-client.mjs",
    "probe:http:server": "node probes/http-server.mjs",
    "probe:http:client": "node probes/http-client.mjs",
    "probe:all": "npm run probe:versions && node probes/tls-server.mjs & sleep 1 && node probes/tls-client.mjs && node probes/http-server.mjs & sleep 1 && node probes/http-client.mjs"
  }
}
```

macOS/Linux 기준으로 background 실행을 섞었고, Windows에서는 터미널을 두 개 열어 server/client를 나눠 실행하는 편이 낫습니다.

### 1) versions.mjs: 공급망 버전 스냅샷

```js
// probes/versions.mjs
import { execFileSync } from 'node:child_process';

function tryCmd(cmd, args) {
  try {
    return execFileSync(cmd, args, { encoding: 'utf8' }).trim();
  } catch {
    return null;
  }
}

const npmVersion = tryCmd('npm', ['-v']);
const corepackVersion = tryCmd('corepack', ['--version']);

const v = process.versions;

console.log(JSON.stringify({
  node: process.version,
  versions: {
    node: v.node,
    openssl: v.openssl,
    uv: v.uv,
    v8: v.v8,
    zlib: v.zlib,
    undici: v.undici ?? null
  },
  tools: {
    npm: npmVersion,
    corepack: corepackVersion
  },
  platform: {
    platform: process.platform,
    arch: process.arch
  }
}, null, 2));
```

예상 출력(예시는 형태만 보여줍니다. 실제 값은 실행 환경에 따라 달라집니다).

```json
{
  "node": "v26.8.2",
  "versions": {
    "node": "26.8.2",
    "openssl": "3.5.8",
    "uv": "...",
    "v8": "...",
    "zlib": "...",
    "undici": "8.10.2"
  },
  "tools": {
    "npm": "11.19.1",
    "corepack": "0.36.0"
  },
  "platform": {
    "platform": "linux",
    "arch": "x64"
  }
}
```

여기서 undici가 null로 나오면, 적어도 내장 버전이 process.versions에 노출되지 않는 형태라는 뜻이고, 그 자체가 “무엇을 검증해야 하는가”를 다시 정하게 만듭니다.

### 2) TLS 서버/클라이언트로 handshake 경로를 단순 검증

OpenSSL 회귀는 외부 환경 변수(프록시, 사내 CA, 중간 인증서)와 결합될 때 잘 터지므로, 로컬 테스트는 최소한으로 둡니다. 대신 로컬에서라도 다음은 확인합니다.

- 인증서 파싱
- ALPN 협상
- 세션 재사용/keep-alive와 결합된 기본 동작

간단한 self-signed TLS 서버와 클라이언트를 만듭니다.

```js
// probes/tls-server.mjs
import tls from 'node:tls';

// 테스트용 키/인증서는 실제 운영에서는 파일로 관리하는 게 맞습니다.
// 여기서는 예시를 위해 짧게 넣습니다. (자체 생성 후 교체 권장)
const key = `-----BEGIN PRIVATE KEY-----
MIIBVgIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEAu9...
-----END PRIVATE KEY-----`;

const cert = `-----BEGIN CERTIFICATE-----
MIIBqTCCAU+gAwIBAgIUE8...
-----END CERTIFICATE-----`;

const server = tls.createServer({
  key,
  cert,
  ALPNProtocols: ['h2', 'http/1.1']
}, (socket) => {
  socket.write('ok');
  socket.end();
});

server.listen(8443, '127.0.0.1', () => {
  console.log('tls-server listening on 127.0.0.1:8443');
});
```

인증서/키는 실제로는 `openssl req -x509 ...`로 생성한 것을 커밋하지 않고 내부 저장소나 secret manager로 관리하는 편이 낫습니다. 여기서는 코드 구조만 보여주고, 실행 가능한 형태를 유지하기 위해 placeholder를 넣었습니다.

클라이언트는 아래처럼 둡니다.

```js
// probes/tls-client.mjs
import tls from 'node:tls';

const socket = tls.connect({
  host: '127.0.0.1',
  port: 8443,
  servername: 'localhost',
  rejectUnauthorized: false,
  ALPNProtocols: ['h2', 'http/1.1']
}, () => {
  const alpn = socket.alpnProtocol;
  const cipher = socket.getCipher();
  const proto = socket.getProtocol();

  console.log(JSON.stringify({
    alpn,
    tlsProtocol: proto,
    cipher
  }, null, 2));
});

socket.setEncoding('utf8');
let data = '';

socket.on('data', (chunk) => { data += chunk; });
socket.on('end', () => {
  console.log('server-said:', data);
});

socket.on('error', (err) => {
  console.error('tls-client error:', err);
  process.exitCode = 1;
});
```

이 테스트는 OpenSSL 보안 패치의 직접 영향까지 잡지는 못하지만, “업그레이드로 인해 TLS 레벨에서 뭔가 즉시 깨지는가”를 빨리 거를 수 있습니다.

### 3) HTTP keep-alive와 헤더 처리의 기본 동작 확인

Undici 회귀의 단골은 connection reuse와 헤더 파싱입니다. 내장 http 모듈로 간단한 서버를 만들고, 내장 fetch로 keep-alive가 엮인 요청을 반복합니다.

```js
// probes/http-server.mjs
import http from 'node:http';

const server = http.createServer((req, res) => {
  if (req.url === '/cookie') {
    res.setHeader('Set-Cookie', 'sid=abc; HttpOnly');
    res.end('cookie');
    return;
  }

  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify({
    method: req.method,
    url: req.url,
    headers: req.headers
  }));
});

server.listen(8080, '127.0.0.1', () => {
  console.log('http-server listening on 127.0.0.1:8080');
});
```

```js
// probes/http-client.mjs
const base = 'http://127.0.0.1:8080';

// 1) 기본 요청
{
  const r = await fetch(`${base}/hello`, {
    headers: {
      'User-Agent': 'runtime-probe'
    }
  });
  const j = await r.json();
  console.log('hello:', j.method, j.url);
}

// 2) Set-Cookie 응답을 한 번 받아서, 클라이언트가 어떤 식으로 다루는지 관찰
{
  const r = await fetch(`${base}/cookie`);
  console.log('cookie status:', r.status);
  console.log('set-cookie header:', r.headers.get('set-cookie'));
}

// 3) 반복 요청으로 connection reuse가 얽힌 상황에서 오류가 발생하는지 확인
{
  for (let i = 0; i < 50; i++) {
    const r = await fetch(`${base}/hello?i=${i}`);
    if (!r.ok) {
      throw new Error(`unexpected status: ${r.status}`);
    }
    await r.arrayBuffer();
  }
  console.log('repeated fetch: ok');
}
```

Undici 8.10.2의 cache interceptor/Set-Cookie 관련 보안 수정은 이 테스트만으로 재현되지는 않습니다. 그렇지만 최소한 “fetch가 정상 요청에서 예외를 뿜고 죽는지” 같은 1차 필터로는 쓸 수 있습니다.

내가 진짜로 신경 쓰는 건 이 다음입니다. 실제 운영 환경에서 쓰는 프록시 설정, DNS, mTLS, 외부 API 엔드포인트 목록을 환경변수로 주입하고, 동일한 probe를 canary에서 주기적으로 돌려 “에러율/지연/handshake 실패율”을 비교합니다.

## 반론과 회의론: Current 라인을 굳이 이렇게까지 따라가야 하나

이 글의 관점은 Current 라인 업그레이드를 적극 옹호하는 게 아닙니다. 오히려 Current 라인을 운영에 쓰는 순간 비용이 구조적으로 발생한다는 점을 인정하는 쪽입니다.

### “Current는 실험이다. LTS만 써라”

맞는 말입니다. 특히 규제가 있는 환경(금융, 공공, 의료)이나 서드파티 인증 체계(FIPS 등)와 강하게 묶인 조직은, OpenSSL 업데이트를 런타임 패치로 자주 들여오는 게 부담스럽습니다.

다만 조직이 이미 Node 26 Current를 쓰고 있다면, 그 순간부터는 “업그레이드를 미루는 전략”도 위험 관리 전략이어야 합니다. OpenSSL/Undici는 시간이 갈수록 취약점 공지와 버전 갭이 벌어지고, 어느 순간 한 번에 크게 올리는 방식으로만 남습니다.

### “최신이 항상 더 안전하다. 빨리 올려라”

보안 패치 관점에서는 매력적이지만, 운영 리스크를 과소평가하는 결론이 되기 쉽습니다. Undici 8.10.2만 해도 보안 수정이 다수 들어갔고, 이런 수정은 곧 행동 변화(behavior change)를 동반합니다. [Undici v8.10.2 릴리스](https://github.com/nodejs/undici/releases/tag/v8.10.2)

안전하다는 말은 “취약점이 줄었다”와 “장애가 줄었다”가 동시에 성립해야 합니다. 런타임 업그레이드는 둘을 동시에 만족시키기 어렵습니다.

## 앞으로 지켜볼 것

1) Node 26의 LTS 전환 타이밍

Node 26.0.0 릴리스에서 10월 LTS 전환을 언급했고, Release WG 일정에도 전환 시점이 잡혀 있습니다. [Node.js 26.0.0 릴리스 노트](https://nodejs.org/en/blog/release/v26.0.0), [Node.js Release Working Group 일정](https://github.com/nodejs/Release)

LTS로 전환되면 조직 내부의 업그레이드 압력과 기대치가 바뀝니다. Current 때는 “변화가 잦다”로 정당화되던 것이, LTS에서는 “안정적이어야 한다”로 바뀝니다.

2) OpenSSL 권고와 Node 반영 속도의 패턴

이번에는 OpenSSL 3.5.8(2026-08-25)이 Node 26.8.2(2026-09-09)에 들어왔습니다. 다음 권고에서도 이 속도가 유지되는지, 아니면 특정 조건에서 지연이 생기는지를 봅니다. [OpenSSL Release and Advisory Timeline](https://mirror.openssl-library.org/news/timeline/)

3) Undici 보안 릴리스의 성격 변화

Undici 8.10.2 릴리스 노트는 보안 수정의 비중이 매우 큽니다. 이 흐름이 계속되면, Node 내장 fetch는 사실상 “보안 패치가 잦은 네트워크 클라이언트”가 됩니다. 운영은 그 속도를 감당할 준비가 돼 있어야 합니다. [Undici v8.10.2 릴리스](https://github.com/nodejs/undici/releases/tag/v8.10.2)

4) 실험 기능 취약점 정책과 실제 CVE 처리의 경계

PR #65438은 정책의 언어를 바꾸는 것이고, 실제 사고에서는 해석이 중요합니다. --experimental-*를 켠 기능이 안정 기능에 영향을 주는 경로를 만들면, 그 순간부터는 “실험 기능”이라는 꼬리표로 방어하기 어려워집니다. [nodejs/node PR #65438](https://github.com/nodejs/node/pull/65438), [nodejs/node Security Policy](https://github.com/nodejs/node/security/policy)

## 지금 할 수 있는 일: 업그레이드 기준을 문서가 아니라 파이프라인에 박아 넣기

여기서 말하는 기준은 사람의 체크리스트가 아니라, 파이프라인의 산출물이어야 합니다.

- Node 업그레이드 PR에서 versions.mjs 출력(JSON)을 아티팩트로 남긴다.
- canary에서 fetch/TLS probe를 주기적으로 돌려, Node 버전별로 지표를 분리한다.
- npm/corepack은 “버전만 확인”이 아니라 “동일 lockfile로 동일 산출물이 나오는지”를 검증한다.
- --experimental-* 사용 여부를 런타임 플래그 수준에서 수집하고, 켜진 서비스는 취약점 SLA를 별도로 본다.

Current 라인에서 이걸 하지 않으면 업그레이드는 계속 이벤트로 남고, 이벤트는 결국 장애로만 기억됩니다.

## 판단

Node.js 26.8.2는 기능 릴리스라기보다 OpenSSL 3.5.8과 Undici 8.10.2, 그리고 npm 11.19.1/corepack 0.36.0까지 묶인 공급망 업데이트입니다. 이 묶음은 취약점 대응 속도를 끌어올리는 대신 TLS/HTTP/설치 재현성의 회귀 확률을 동시에 올립니다. Current 라인을 운영에서 쓰는 순간 업그레이드는 기능이 아니라 위험 관리 프로세스가 되고, 26.8.2는 그 사실을 가장 깔끔하게 드러낸 릴리스입니다.

## 참고 자료

- [Node.js 26.8.2 릴리스 노트](https://nodejs.org/en/blog/release/v26.8.2)
- [Node.js 26.0.0 릴리스 노트](https://nodejs.org/en/blog/release/v26.0.0)
- [Node.js Release Working Group 일정](https://github.com/nodejs/Release)
- [Undici v8.10.2 릴리스](https://github.com/nodejs/undici/releases/tag/v8.10.2)
- [npm CLI v11 changelog](https://docs.npmjs.com/cli/v11/using-npm/changelog/)
- [corepack v0.36.0 릴리스](https://github.com/nodejs/corepack/releases/tag/v0.36.0)
- [nodejs/node PR #65438](https://github.com/nodejs/node/pull/65438)
- [nodejs/node Security Policy](https://github.com/nodejs/node/security/policy)
- [OpenSSL 다운로드 페이지(3.5.8 포함)](https://www.openssl-library.org/source/)
- [OpenSSL Release and Advisory Timeline](https://mirror.openssl-library.org/news/timeline/)
- [OpenSSL Security Advisory(2026-08-25, oss-security 미러)](https://www.openwall.com/lists/oss-security/2026/08/25/3)
- [OpenSSL 3.0 EOL 이후 런타임을 안전하게 퇴역시키는 운영 설계](https://daewooki.github.io/posts/retire-openssl-3-0-safely/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
