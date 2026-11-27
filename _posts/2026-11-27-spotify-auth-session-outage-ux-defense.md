---
title: "Spotify 로그인 장애에서 본 인증·세션 실패의 클라이언트 방어 패턴"
description: "인증·세션 장애가 로그인 실패를 넘어 재시도 폭풍과 UX 붕괴로 이어질 때, 클라이언트가 할 수 있는 최소 방어를 정리합니다."
date: 2026-11-27 16:52:19 +0900
categories: ["News", "Infrastructure"]
tags: ["incident-analysis", "sre", "auth", "session", "graceful-degradation", "retries"]
render_with_liquid: false
---

## 2026-11-24 Spotify 장애에서 관측된 것

2026년 11월 24일(화) Spotify에서 로그인 실패와 세션 관련 이슈가 동시다발적으로 보고됐고, 짧은 시간 내에 복구 공지가 나왔습니다. 라이브 업데이트 형태로 상황을 따라간 매체들이 공통적으로 적은 증상은 다음과 비슷했습니다.

- 갑자기 로그아웃됨(모바일/데스크톱)
- 재로그인이 안 됨(loading screen, generic error)
- 기존 비밀번호가 틀렸다고 나오거나, 이메일이 계정과 연동되지 않았다고 나옴
- 일부 환경에서는 웹은 되는데 앱은 실패
- 이미 로그인된 상태를 유지한 경우 offline download는 재생되는 듯 보임

Android Authority는 장애 초기에 “강제 로그아웃 + 로그인 차단”이 핵심 증상이며, 로그인 상태를 유지한 사용자는 offline download는 재생될 수 있다고 정리했습니다. 또한 비밀번호 리셋/재설치 같은 사용자의 불필요한 행동을 피하라는 톤으로 안내했습니다[^1].

타임라인은 매체마다 약간의 차이가 있습니다. TechRadar는 Downdetector 스파이크가 대략 6:15am ET(= 11:15am GMT) 즈음 시작했다고 적었고[^2], Tom’s Guide는 5:30am ET(= 11:30am GMT)부터 보고가 급증했다고 적었습니다[^3]. 관측 기반 기사에서 시간 차이가 나는 건 흔합니다. 중요한 포인트는 “미국 동부 시간으로 이른 아침대(대략 5:30~6:15am ET)부터 로그인 이슈가 폭발적으로 표면화됐고, 1~2시간 이내에 완화/복구 흐름이 보였다”는 점입니다.

USA TODAY(재배포된 AOL 기사)는 Downdetector 기준 6:45am ET 무렵 16,000건 이상의 리포트가 있었다고 적었고, 7am ET 직전에 Spotify Status 계정이 문제 인지(We’re aware…)를 올린 뒤 곧바로 “Everything’s looking much better now”류의 후속 공지가 나왔다고 정리했습니다[^4].

KST로 환산하면(ET가 UTC-5인 시기 기준) 5:30am ET는 11월 24일 7:30pm KST, 6:15am ET는 8:15pm KST입니다. 한국 시간으로는 퇴근 전후 피크에 해당합니다. 글로벌 consumer 서비스 장애는 한 지역의 새벽이 다른 지역의 프라임타임이 되면서, 같은 결함이 훨씬 큰 사용자 경험 이슈로 증폭되는 경우가 많습니다.

한 가지 더 눈에 띄는 점은, Spotify의 Atlassian Statuspage 기반 상태 페이지에는 Nov 24에 “No incidents reported”로 보인다는 것입니다(2026-11-27 KST에 재확인 기준). 즉, 많은 사용자들이 실시간으로 겪은 장애와 별개로, 공식 status page에는 사건이 남지 않았거나(혹은 다른 커뮤니케이션 채널로만 운영됐거나) 장애 범위가 status page가 다루는 컴포넌트 정의 밖이었을 가능성이 있습니다[^5].

반면 Spotify Community의 Ongoing Issues에는 “Issues logging in / randomly getting logged out”가 Under investigation으로 올라와 있습니다[^6]. 이 조합은 SRE 관점에서 커뮤니케이션 채널 분산이 사용자 불안을 키우는 전형적인 모양새입니다. status page는 조용한데 앱은 로그아웃시키고, 사용자는 해킹을 의심하며, 결국 OTP/비밀번호 리셋/재설치를 반복합니다.

## 인증·세션 장애가 클라이언트 UX로 번지는 메커니즘

로그인 장애를 단순히 “인증 서버가 죽었다”로 요약하면 놓치는 게 많습니다. 인증·세션 계층에서 생긴 문제가 사용자 UX로 확산되는 경로는 대략 세 가지가 엮이면서 만들어집니다.

1) 서버 측 불능(또는 부분 불능)

- token endpoint가 5xx를 뱉거나, 내부적으로 rate limit에 걸려 429를 뱉는 상황
- session store/계정 DB/권한 체크 같은 하위 의존성이 느려져 타임아웃을 유발하는 상황
- 어떤 장애에서는 “정상적인 인증 실패(401/invalid_grant)”처럼 보이는 오류가 잘못 발생해, 클라이언트가 ‘자격 증명 문제’로 오판하는 상황

2) 클라이언트의 과잉 반응

- refresh 실패를 “세션 무효”로 해석하고 즉시 로그아웃 처리
- 앱 시작/포그라운드 복귀/네트워크 전환 때마다 refresh를 즉시 재시도
- 멀티 디바이스(폰, 태블릿, 노트북) + 멀티 탭(웹)에서 동시에 refresh가 중복 발생

3) 사용자 행동의 증폭

- 비밀번호 리셋, OTP 코드 재전송, 앱 삭제 후 재설치, 소셜 로그인 연동 해제/재연동
- 이 행동 자체가 인증·세션 계층에 추가 부하를 얹어, 복구를 더 늦추는 방향으로 작동

이게 왜 무서운지에 대한 설명은 Google SRE Book이 훨씬 직설적입니다. 장애가 일부 컴포넌트에서 시작해, “재시도”라는 이름의 트래픽 증폭을 거치며 전체 시스템으로 전이되는 cascading failure를 경고합니다[^7]. Handling Overload 챕터는 더 구체적으로, 백엔드가 이미 과부하인데 클라이언트가 재시도를 계속하면 정상 복구가 더 어려워지고, 백엔드는 “don’t retry” 또는 degraded response를 반환해야 한다는 식으로 패턴을 적습니다[^8].

나는 이걸 로그인 장애에서 특히 자주 봅니다. 인증 계층은 기능적으로는 “서비스의 입구”인데, 트래픽 관점에서는 “모든 기능의 공통 의존성”이기 때문입니다. 입구가 막히면 단순히 로그인만 막히는 게 아니라, 이미 로그인한 사용자까지 같이 흔들립니다.

## 재시도 폭풍: 토큰 refresh가 가장 위험한 이유

이번 Spotify 케이스가 정확히 어떤 내부 원인인지 공개되지 않았습니다(지금까지는 원인/교훈이 적힌 공식 RCA를 확인하지 못했습니다). 그럼에도 SRE 관점에서 “가장 비용이 큰 실패 모드”는 꽤 예측 가능합니다. 인증 장애에서 서비스가 더 나빠지는 순간은, 클라이언트가 token refresh를 **retry storm**으로 만들어버릴 때입니다.

여기서 핵심은 “재시도가 원인을 가린다”가 아닙니다. 재시도는 시스템이 살아남는 마지막 구명줄이기도 합니다. 문제는 아래 조건이 겹칠 때입니다.

- 재시도 대상이 idempotent하지 않거나(예: OTP 발송, 세션 생성) 비용이 큰 작업인 경우
- retry interval이 동기화되어(thundering herd) 짧은 주기로 몰리는 경우
- 복구 구간에서 재시도가 폭발해, 회복해야 할 컴포넌트를 다시 눌러버리는 경우

Google Cloud Blog의 “self-inflicted DDoS” 글은 지수 백오프와 jitter가 없으면 복구 구간에 트래픽이 동기화되어 다시 장애를 만든다는 현실적인 교훈을 적었습니다[^9]. AWS Builders’ Library도 같은 결론을 더 실무적인 언어로 풀어냅니다. timeouts/retries/backoff/jitter가 함께 설계되어야 하고, 특히 retry는 시스템을 돕기도 하지만 더 나쁘게 만들기도 한다는 점을 반복해서 강조합니다[^10].

프로토콜 관점에서도 힌트가 있습니다. HTTP Semantics(RFC 9110)는 503에서 서버가 Retry-After로 적절한 재시도 타이밍을 제시할 수 있음을 명시합니다[^11]. 429 Too Many Requests 역시 Retry-After와 함께 쓰일 수 있고, MDN 문서는 그 의미를 비교적 명확히 정리합니다[^12].

인증 계층에 한정해도 가이드는 존재합니다. Microsoft Entra의 클라이언트 앱 resilience 가이드는 token endpoint가 429/5xx를 반환하면 fast retry loop에 들어가지 말고, Retry-After가 없으면 최소 5초부터 시작하는 exponential backoff를 구현하라고 적습니다[^13].

이걸 로그인 UX로 번역하면, 아래와 같은 의사결정이 갈립니다.

- “로그인에 실패했으니 바로 로그아웃하고 로그인 화면으로 보낸다”
- “인증이 불능 상태일 수 있으니, 세션을 유지하고 기능을 줄이며 재시도를 늦춘다”

전자는 보안적으로 깔끔해 보이지만, 대규모 장애에서는 사용자 행동을 폭발시키는 방향으로 가기 쉽습니다.

## 클라이언트에서 만드는 최소 방어: 장애 친화적 UX 패턴

서버를 고치는 건 서버 팀의 일입니다. 다만 대규모 consumer 서비스에서는, 클라이언트가 방어하지 않으면 서버가 복구해도 UX가 회복되지 않는 구간이 생깁니다. 로그인/세션 장애는 특히 그렇습니다.

여기서 목표는 화려한 오프라인 퍼스트가 아닙니다. 장애가 발생했을 때 “사용자가 더 나쁜 선택을 하지 않게 만들고”, “백엔드 회복을 돕고”, “이미 가지고 있던 가치를 최대한 유지”하는 정도면 됩니다.

### 1) 로그아웃은 마지막 카드로 남긴다

관성적으로 구현된 앱은 refresh 실패만으로 local session을 삭제합니다. 이건 장애 시점에 최악의 선택이 됩니다.

- refresh 실패(5xx/timeout)는 ‘자격 증명 무효’가 아니라 ‘서버 불능’일 수 있습니다.
- “이 사용자는 더 이상 유효하지 않다”를 서버가 확정(예: 401 + 명확한 error code)할 때만 로그아웃이 합리적입니다.

따라서 클라이언트는 “invalid token”과 “token endpoint unreachable”을 구분해야 합니다. HTTP status + error payload taxonomy를 최대한 유지하고, 애매한 오류일수록 로그아웃 대신 제한 모드로 전환해야 합니다.

이 패턴은 UX 측면에서도 효과가 있습니다. 이번 Spotify 장애에서 사용자들이 해킹을 의심한 맥락은, 앱이 갑자기 로그아웃시키고 비밀번호가 틀렸다고 말했기 때문입니다[^2][^1]. 사용자가 비밀번호 리셋을 시작하면 인증 트래픽은 더 늘고, 피해는 더 커집니다.

### 2) refresh는 단일화하고, 예산을 둔다

세션 기반 앱에서 refresh 호출은 “앱 전체의 shared dependency”입니다. 탭마다, 화면마다, 컴포넌트마다 토큰을 새로 받으려 들면 장애가 없어도 언젠가 문제를 만듭니다.

여기서는 구현 패턴이 거의 정해져 있습니다.

- **singleflight**: 같은 프로세스(또는 브라우저 프로파일) 안에서는 refresh in-flight를 공유해서 중복 호출을 없앱니다.
- refresh 시간 예산(time budget): refresh는 무한 재시도가 아니라, “N초 동안 M번”처럼 상한을 둡니다.
- 백오프는 jitter 포함: AWS/Google 모두 같은 결론을 냅니다[^10][^9].
- Retry-After 존중: 서버가 복구 시간을 아는 경우(혹은 rate limit을 건 경우) 클라이언트가 이를 무시하면 안 됩니다[^11].

gRPC 쪽 문서지만, 연결 실패 시 exponential backoff + jitter를 프로토콜로 박아둔 문서가 있습니다. 핵심은 “즉시 재시도하지 말고, 지수적으로 늘리고, jitter로 동기화를 깨라”입니다[^14].

HTTP/REST에서도 동일한 논리가 적용됩니다.

### 3) 인증 장애 시 기능을 줄이는 **auth outage mode**

로그인이 안 되면 아무것도 못 하는 서비스가 있고, 로그인이 안 돼도 일부는 되는 서비스가 있습니다. Spotify 같은 미디어 서비스는 후자에 가까운 설계를 할 여지가 큽니다.

이번 장애를 보도한 Android Authority는 “로그인 상태를 유지한 사용자는 offline download가 재생될 수 있다”고 적었습니다[^1]. 이건 장애 친화적 UX의 핵심 힌트입니다.

인증이 불능일 때 클라이언트가 취할 수 있는 최소한의 모드는 다음과 같습니다.

- read-only로 전환: 계정 설정 변경, 결제/구독, 라이브러리 편집, 팔로우/언팔로우 등 write 작업 UI를 숨기거나 비활성화
- 캐시 기반 browse 허용: 최근 재생, 최근 조회한 플레이리스트/앨범 메타데이터를 캐시에서 보여주기
- 재생은 가능한 범위에서 유지: offline download, 로컬 큐(사용자 기기 내 큐), 마지막으로 성공한 스트림 세션의 재사용 등(서비스 정책/DRM 제약 내에서)
- 명확한 배너: “비밀번호가 틀렸습니다”가 아니라 “현재 로그인/세션 시스템이 불안정합니다”가 맞는 메시지

이 모드를 코드 레벨에서 명확히 분리하는 게 중요합니다. 상태 머신으로 보면 대략 아래처럼 나뉩니다.

- AuthOK
- AuthDegraded(서버 불능/429/5xx/timeout)
- AuthInvalid(정상적인 401 + invalid_grant 등)

AuthDegraded에서 AuthInvalid로 오판하는 순간, 앱은 사용자를 로그인 화면으로 던지고, 사용자는 비밀번호 리셋을 시도합니다. 장애가 UX로 번지는 임계점입니다.

### 4) 캐시는 stale로 버틴다: stale-while-revalidate, **stale-if-error**

미디어 서비스에서 인증 장애가 나면, “로그인 성공률”만 떨어지는 게 아닙니다. 앱 홈피드, 추천, 라이브러리, 검색 같은 기능도 연쇄적으로 깨질 수 있습니다. 그럼 홈 화면 자체가 비어 보이고, 사용자는 더 공격적으로 새로고침/재로그인을 시도합니다.

이때 캐시 전략은 UX와 부하 양쪽에 영향을 줍니다.

- stale-while-revalidate: 캐시를 먼저 보여주고, 뒤에서 갱신
- stale-if-error: 갱신이 실패하면(네트워크/서버 에러) 기존 캐시를 더 오래 제공

stale-while-revalidate와 stale-if-error는 RFC 5861에 정의된 캐시 컨트롤 확장입니다[^15]. 웹 쪽에서는 web.dev가 개념과 실제 적용 시점을 비교적 잘 풀어냅니다[^16].

Service Worker 기반이라면 Workbox가 전략의 장단점을 정리해두었습니다[^17]. CDN/에지 계층을 운영한다면 Cloudflare도 stale-while-revalidate/stale-if-error 동작을 비교적 자세히 문서화했습니다[^18].

인증 장애와 캐시가 무슨 상관인가 싶지만, 실제로는 연결됩니다.

- 인증이 불능이면 personalized API 응답이 실패합니다.
- 홈 화면이 비면 사용자는 “앱이 완전히 죽었다”고 판단합니다.
- 사용자가 행동(재로그인/재설치)을 시작하고, 인증 부하가 더 늘어납니다.

따라서 캐시는 단순 성능 최적화가 아니라 장애 완충재입니다.

### 5) 상태 페이지가 조용할 때의 플랜

이번 케이스에서 흥미로운 점은, Spotify Statuspage에는 Nov 24에 “No incidents reported”로 보이지만[^5], Community에는 Under investigation 이슈가 올라와 있다는 점입니다[^6].

이런 상황에서 클라이언트가 상태 페이지만 믿고 UX를 설계하면, 장애 안내가 늦거나 아예 없을 수 있습니다.

내 경우에는 다음 신호를 조합해 “auth outage mode” 진입을 판단하는 쪽으로 설계합니다.

- token endpoint의 5xx/timeout 비율
- 429/Retry-After 존재
- 로그인 성공률(특히 OTP, passkey 같은 보조 채널)
- 특정 에러 문자열(서버가 내려준 structured error code가 최선)
- 짧은 시간에 동일 오류가 다량 발생하는지(로컬/집계)

서버가 제대로 된 상태 신호를 주면 제일 좋습니다. 하지만 커뮤니케이션이 지연되는 현실을 감안하면, 클라이언트 자체적으로 방어적인 state machine을 갖는 편이 복구에 유리합니다.

## 구현 예시: 인증 불능을 세션 무효로 오판하지 않는 TypeScript 클라이언트

아래 코드는 Spotify를 흉내 내는 게 아니라, “token endpoint 장애가 났을 때 클라이언트가 어떻게 덜 망가질 수 있는지”를 재현하기 위한 실행 가능한 샘플입니다. 로컬에서 서버(모의 API)와 클라이언트(모의 앱)를 함께 띄우고, 인증 장애 구간을 시뮬레이션합니다.

구성은 단순하지만 실무 패턴은 그대로 넣었습니다.

- refresh singleflight
- Retry-After 존중
- exponential backoff + jitter
- refresh 예산(time budget)
- read-only 캐시 응답(stale-if-error 유사)

### 실행 환경

- Node.js 20+
- npm 10+

### 1) 프로젝트 생성

```bash
mkdir auth-outage-demo
cd auth-outage-demo
npm init -y
npm i express
npm i -D typescript ts-node @types/node @types/express
npx tsc --init
```

`package.json`에 스크립트를 추가합니다.

```json
{
  "name": "auth-outage-demo",
  "type": "module",
  "scripts": {
    "server": "node --loader ts-node/esm server.ts",
    "client:naive": "node --loader ts-node/esm client_naive.ts",
    "client:resilient": "node --loader ts-node/esm client_resilient.ts",
    "storm": "node --loader ts-node/esm storm.ts"
  }
}
```

### 2) 모의 서버(server.ts)

- `/oauth/token`은 장애 구간에 503 + Retry-After를 반환합니다.
- `/api/library`는 access token이 있어야 하고, token이 없으면 401을 반환합니다.
- 서버는 “장애가 끝난 뒤” 정상 토큰을 발급합니다.

```ts
// server.ts
import express from 'express';

const app = express();
app.use(express.json());

// 장애 시뮬레이션: 서버 시작 후 OUTAGE_MS 동안 token endpoint는 503을 반환
const OUTAGE_MS = Number(process.env.OUTAGE_MS ?? 60_000); // 기본 60초
const START = Date.now();

function inOutageWindow() {
  return Date.now() - START < OUTAGE_MS;
}

// 매우 단순한 토큰 모델(데모용)
function issueToken() {
  // 2분짜리 토큰
  const expiresAt = Date.now() + 120_000;
  const token = `demo_${Math.random().toString(16).slice(2)}`;
  return { access_token: token, token_type: 'Bearer', expires_in: 120, expires_at: expiresAt };
}

const validTokens = new Map<string, number>(); // token -> expiresAt

app.post('/oauth/token', (req, res) => {
  if (inOutageWindow()) {
    // token endpoint 불능
    res.setHeader('Retry-After', '10'); // 10초 후 재시도 힌트
    return res.status(503).json({
      error: 'temporarily_unavailable',
      error_description: 'token endpoint is overloaded'
    });
  }

  const t = issueToken();
  validTokens.set(t.access_token, t.expires_at);
  return res.json(t);
});

app.get('/api/library', (req, res) => {
  const auth = req.header('authorization');
  const token = auth?.startsWith('Bearer ') ? auth.slice('Bearer '.length) : undefined;
  if (!token) return res.status(401).json({ error: 'missing_token' });

  const exp = validTokens.get(token);
  if (!exp || exp < Date.now()) return res.status(401).json({ error: 'invalid_token' });

  // 현실적인 payload 흉내
  return res.json({
    playlists: [
      { id: 'p1', name: 'Focus', trackCount: 120 },
      { id: 'p2', name: 'Gym', trackCount: 80 }
    ],
    generatedAt: new Date().toISOString()
  });
});

app.listen(3000, () => {
  console.log(`server listening on :3000 (OUTAGE_MS=${OUTAGE_MS})`);
});
```

### 3) 순진한 클라이언트(client_naive.ts)

장애가 나면 refresh를 빠르게 반복하고, 실패할 때마다 “로그아웃”처럼 토큰을 날려버리는 형태를 일부러 만듭니다.

```ts
// client_naive.ts
const TOKEN_URL = 'http://localhost:3000/oauth/token';
const API_URL = 'http://localhost:3000/api/library';

let accessToken: string | null = null;

async function getTokenFastRetry(): Promise<string> {
  // 문제의 핵심: 지연 없이 5번 연속 재시도
  for (let i = 0; i < 5; i++) {
    const r = await fetch(TOKEN_URL, { method: 'POST' });
    if (r.ok) {
      const data = await r.json();
      return data.access_token;
    }
  }
  throw new Error('token acquisition failed');
}

async function main() {
  for (let tick = 0; tick < 10; tick++) {
    try {
      if (!accessToken) {
        accessToken = await getTokenFastRetry();
      }

      const r = await fetch(API_URL, {
        headers: { authorization: `Bearer ${accessToken}` }
      });

      if (r.status === 401) {
        // 문제의 핵심: 401/503/timeout 구분 없이 토큰 폐기
        accessToken = null;
        console.log('[naive] got 401 -> dropping session');
        continue;
      }

      if (!r.ok) {
        console.log('[naive] api error', r.status);
        continue;
      }

      const data = await r.json();
      console.log('[naive] library ok', data.generatedAt);
    } catch (e: any) {
      accessToken = null;
      console.log('[naive] loop error -> dropping session:', e.message);
    }

    await new Promise(r => setTimeout(r, 1000));
  }
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
```

### 4) 방어적인 클라이언트(client_resilient.ts)

핵심 동작은 다음입니다.

- refresh는 singleflight로 묶어 중복 호출을 방지
- 503/429에서는 Retry-After를 우선 적용
- Retry-After가 없으면 exponential backoff + jitter(최소 5초)로 재시도
- 일정 시간 동안은 auth outage mode로 전환하고, API 호출을 캐시로 대체

```ts
// client_resilient.ts
const TOKEN_URL = 'http://localhost:3000/oauth/token';
const API_URL = 'http://localhost:3000/api/library';

type TokenState = {
  accessToken: string | null;
  expiresAt: number | null;
};

type CacheState = {
  library: any | null;
  cachedAt: number | null;
};

const token: TokenState = { accessToken: null, expiresAt: null };
const cache: CacheState = { library: null, cachedAt: null };

let refreshInflight: Promise<void> | null = null;

// auth outage circuit breaker
let authDegradedUntil = 0;

function now() {
  return Date.now();
}

function sleep(ms: number) {
  return new Promise(r => setTimeout(r, ms));
}

function jitter(ms: number) {
  // +-20%
  const delta = ms * 0.2;
  return ms + (Math.random() * 2 - 1) * delta;
}

function isTokenValid() {
  return token.accessToken && token.expiresAt && token.expiresAt - now() > 10_000; // 10초 여유
}

function inAuthDegraded() {
  return now() < authDegradedUntil;
}

async function refreshTokenWithBudget(timeBudgetMs: number): Promise<void> {
  if (refreshInflight) return refreshInflight;

  refreshInflight = (async () => {
    const deadline = now() + timeBudgetMs;
    let attempt = 0;

    while (now() < deadline) {
      attempt++;

      const r = await fetch(TOKEN_URL, { method: 'POST' });

      if (r.ok) {
        const data = await r.json();
        token.accessToken = data.access_token;
        token.expiresAt = data.expires_at;
        authDegradedUntil = 0;
        return;
      }

      // 503/429는 auth degraded로 취급
      if (r.status === 503 || r.status === 429) {
        const ra = r.headers.get('retry-after');
        const waitMs = ra ? Number(ra) * 1000 : jitter(Math.max(5000, 2 ** Math.min(attempt, 6) * 1000));

        // 장애 모드로 잠깐 전환(이 시간 동안 refresh 호출을 더 줄임)
        authDegradedUntil = Math.max(authDegradedUntil, now() + waitMs);
        await sleep(waitMs);
        continue;
      }

      // 4xx(예: invalid_grant)는 자격 증명 문제로 취급
      if (r.status >= 400 && r.status < 500) {
        token.accessToken = null;
        token.expiresAt = null;
        throw new Error(`token invalid (${r.status})`);
      }

      // 나머지는 backoff
      const waitMs = jitter(Math.max(5000, 2 ** Math.min(attempt, 6) * 1000));
      authDegradedUntil = Math.max(authDegradedUntil, now() + waitMs);
      await sleep(waitMs);
    }

    throw new Error('token refresh budget exceeded');
  })();

  try {
    await refreshInflight;
  } finally {
    refreshInflight = null;
  }
}

async function fetchLibrary(): Promise<any> {
  // 1) auth degraded면 캐시를 우선 사용
  if (inAuthDegraded()) {
    if (cache.library) {
      return { ...cache.library, servedFrom: 'cache(auth-degraded)' };
    }
    return { playlists: [], servedFrom: 'empty(auth-degraded)' };
  }

  // 2) 토큰이 없거나 만료 임박이면 refresh (단, budget 제한)
  if (!isTokenValid()) {
    await refreshTokenWithBudget(25_000);
  }

  const r = await fetch(API_URL, {
    headers: { authorization: `Bearer ${token.accessToken}` }
  });

  if (r.status === 401) {
    // 토큰 무효로 보이면 refresh 1회만 시도하고, 그래도 안 되면 degraded로
    token.accessToken = null;
    token.expiresAt = null;
    try {
      await refreshTokenWithBudget(15_000);
    } catch {
      authDegradedUntil = Math.max(authDegradedUntil, now() + 10_000);
      if (cache.library) return { ...cache.library, servedFrom: 'cache(401->degraded)' };
      return { playlists: [], servedFrom: 'empty(401->degraded)' };
    }

    // 새 토큰으로 1회 재시도
    const r2 = await fetch(API_URL, {
      headers: { authorization: `Bearer ${token.accessToken}` }
    });
    if (!r2.ok) throw new Error(`api failed after refresh (${r2.status})`);

    const data2 = await r2.json();
    cache.library = data2;
    cache.cachedAt = now();
    return { ...data2, servedFrom: 'network(after-refresh)' };
  }

  if (!r.ok) {
    // 네트워크/서버 문제면 캐시로
    authDegradedUntil = Math.max(authDegradedUntil, now() + 10_000);
    if (cache.library) return { ...cache.library, servedFrom: 'cache(api-error)' };
    throw new Error(`api failed (${r.status})`);
  }

  const data = await r.json();
  cache.library = data;
  cache.cachedAt = now();
  return { ...data, servedFrom: 'network' };
}

async function main() {
  for (let tick = 0; tick < 12; tick++) {
    try {
      const lib = await fetchLibrary();
      console.log(`[resilient] ok from=${lib.servedFrom} at=${lib.generatedAt ?? 'n/a'}`);
    } catch (e: any) {
      console.log('[resilient] error', e.message);
    }

    await sleep(1000);
  }
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
```

### 5) 재시도 폭풍 재현(storm.ts)

서버가 60초 동안 token endpoint 503을 뱉게 해두고, 순진한 토큰 획득 로직을 50개 동시 실행하면, “복구를 방해하는 트래픽”이 어떤 모양으로 만들어지는지 감각적으로 확인할 수 있습니다.

```ts
// storm.ts
const TOKEN_URL = 'http://localhost:3000/oauth/token';

async function naiveClient(id: number) {
  let fails = 0;
  for (let i = 0; i < 20; i++) {
    const r = await fetch(TOKEN_URL, { method: 'POST' });
    if (!r.ok) {
      fails++;
      // 즉시 재시도
      continue;
    }
    const data = await r.json();
    return { id, ok: true, token: data.access_token, fails };
  }
  return { id, ok: false, fails };
}

async function main() {
  const N = 50;
  const started = Date.now();
  const results = await Promise.all(Array.from({ length: N }, (_, i) => naiveClient(i)));
  const elapsed = Date.now() - started;
  const ok = results.filter(r => r.ok).length;
  const totalFails = results.reduce((a, r) => a + r.fails, 0);
  console.log({ N, ok, totalFails, elapsedMs: elapsed });
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
```

### 실행 순서와 예상 출력

서버를 60초 장애로 띄웁니다.

```bash
OUTAGE_MS=60000 npm run server
```

다른 터미널에서 순진한 클라이언트를 실행하면 장애 구간에 session drop이 반복됩니다.

```bash
npm run client:naive
```

방어적인 클라이언트는 초반 60초 동안 캐시/빈 응답 모드로 버티다가, 장애가 끝나면 자동 회복합니다.

```bash
npm run client:resilient
```

재시도 폭풍은 다음처럼 숫자로 보입니다(환경마다 수치가 달라질 수 있지만, totalFails가 큰 값으로 치솟는 게 핵심입니다).

```bash
npm run storm
# { N: 50, ok: 0, totalFails: 1000, elapsedMs: 1200 } 같은 형태
```

이 데모에서 중요한 결론은 단순합니다. “로그인을 빨리 복구시키려는” 클라이언트의 행동이 실제로는 token endpoint에 부하를 더 얹어서, 복구를 더 늦출 수 있습니다.

## 반론과 회의론: 클라이언트가 버틴다고 항상 좋은가

인증·세션 장애에서 클라이언트가 버티는 전략은 양날의 검입니다.

1) 보안 관점

- 세션을 오래 유지하면(특히 토큰이 만료됐는데도) 리스크가 생깁니다.
- 따라서 AuthDegraded에서는 “계정/결제/권한 변경” 같은 민감 작업을 막는 read-only가 필수입니다.

2) 제품 정책/라이선스

- 미디어 스트리밍은 캐시/오프라인 동작에 제약이 많습니다.
- 결국 가능한 범위는 “이미 다운로드된 컨텐츠 재생” 수준으로 제한될 수 있습니다.

3) 복잡도

- 상태 머신이 생기고, 장애 모드 테스트가 필요해집니다.
- 그래도 대규모 consumer 서비스라면 이 복잡도는 언젠가 치릅니다. 장애는 기능이 아니라 비용입니다.

나는 “로그인 장애는 서버가 고치면 된다”는 주장에 부분적으로 동의합니다. 다만, 서버가 고쳐도 사용자가 이미 비밀번호 리셋을 시작했거나, 앱이 세션을 날려버렸다면 UX는 복구되지 않습니다. 이번 Spotify 장애에서 사용자들이 “계정이 삭제된 것 같다”, “해킹된 것 같다”는 반응을 보인 것은, 시스템 장애가 사용자 신뢰 비용으로 전환되는 순간을 보여줍니다[^6][^2].

## 앞으로 지켜볼 것: 같은 장애가 다시 왔을 때 더 빨리 무너지는 지점

이번 사건은 짧은 시간 내에 완화된 것으로 보도됐지만[^3][^4], 인증·세션 계층의 장애는 반복될 때 더 큰 비용을 냅니다.

- 사용자가 이미 불신을 학습하면, 다음 장애에서 비밀번호 리셋/재설치 같은 행동이 더 빠르게 시작됩니다.
- 앱이 “비밀번호가 틀렸다” 같은 오해 유발 메시지를 반복하면, 재시도 폭풍은 더 빨리 커집니다.
- status page와 in-app 배너의 불일치가 반복되면, 사용자들은 외부 채널(커뮤니티/소셜)을 먼저 찾아가고, 그 과정에서 잘못된 해결법이 퍼집니다.

SRE 관점에서는 “복구”보다 “복구 구간의 트래픽 제어”가 더 중요해질 가능성이 큽니다. Google SRE Book이 overload/cascading failure 문맥에서 말하는 것처럼, backend가 “don’t retry”를 명시하거나 degraded response를 제공해야 클라이언트가 증폭을 멈춥니다[^8][^7].

## 지금 정리되는 운영/설계 체크리스트

이 사건을 Spotify의 특수한 문제로만 보면 아쉽습니다. 인증·세션 장애는 거의 모든 consumer 서비스가 맞게 될 사건입니다.

클라이언트 팀(웹/앱) 관점에서 정리되는 항목은 다음입니다.

- refresh singleflight(프로세스/프로필 단위) 구현
- Retry-After 우선 적용 + exponential backoff with jitter 기본값 내장[^11][^10]
- refresh 예산(time budget)과 최대 시도 횟수 상한
- 401과 5xx/timeout/429를 구분하는 error taxonomy
- 인증 장애 시 read-only + 캐시 기반 탐색 허용(stale-if-error)[^15]
- 계정 보안 UX 문구를 서버 불능과 분리(비밀번호 오류로 오해시키지 않기)

인프라/SRE 관점에서 정리되는 항목은 다음입니다.

- token endpoint의 429/503에서 Retry-After 제공(RCA를 떠나 즉효성 있는 완충재)
- 장애 시 status page / in-app 배너 / 소셜 공지의 일관성 유지(채널 분산 비용 최소화)
- auth 계층의 SLO를 사용자 행동과 연결: “로그인 성공률”만이 아니라 “세션 유지율”, “강제 로그아웃 발생률”, “OTP 발송/검증 지연” 같은 지표

이 블로그에서 예전에 정리했던 “짧은 시간의 오류율 상승이 SLO를 태우는 방식”이나 “의존성이 전 서비스 에러로 번지는 패턴”도 결국 같은 이야기입니다. 다만 인증·세션은 그 전이 속도가 훨씬 빠르고, 사용자 행동이 증폭기로 붙는다는 점이 다릅니다.

- [39분 ChatGPT 오류율 상승이 SLO를 태우는 방식](https://daewooki.github.io/posts/chatgpt-plus-pro-incident-slo/)
- [Cloudflare IAD 성능 이슈가 전 서비스 에러로 번지는 패턴](https://daewooki.github.io/posts/cloudflare-iad-incident-resilience/)

로그인 장애에서 클라이언트가 할 수 있는 최선은, 로그인을 억지로 성공시키는 게 아니라 실패를 통제하는 것입니다.

## 참고 자료

- [TechRadar 라이브 블로그: Spotify down (November 2026)](https://www.techradar.com/news/live/spotify-down-november-2026)
- [Tom’s Guide 라이브 블로그: Spotify outage (November 24, 2026)](https://www.tomsguide.com/news/live/spotify-outage-november-24-2026)
- [USA TODAY/AOL: Is Spotify down? Company gives update after users report issues](https://www.aol.com/articles/spotify-down-company-gives-users-122835000.html)
- [Android Authority: Spotify outage locks thousands of users out of accounts](https://www.androidauthority.com/spotify-outage-login-issues-3738825/)
- [Spotify Statuspage](https://spotify.statuspage.io/)
- [Spotify Community: Issues logging in / randomly getting logged out](https://community.spotify.com/forum/en/discussion/7564092/issues-logging-in-randomly-getting-logged-out)
- [Google SRE Book: Handling Overload](https://sre.google/sre-book/handling-overload/)
- [Google SRE Book: Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/?hl=bg)
- [Google Cloud Blog: How to avoid a self-inflicted DDoS attack](https://cloud.google.com/blog/products/gcp/how-to-avoid-a-self-inflicted-ddos-attack-cre-life-lessons/?m=1)
- [AWS Builders’ Library: Timeouts, retries, and backoff with jitter (PDF)](https://d1.awsstatic.com/builderslibrary/pdfs/timeouts-retries-and-backoff-with-jitter.pdf)
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.pdf)
- [MDN: 429 Too Many Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429)
- [RFC 5861: HTTP Cache-Control Extensions for Stale Content](https://www.rfc-editor.org/pdfrfc/rfc5861.txt.pdf)
- [Microsoft Entra: Increase the resilience of authentication and authorization in client applications](https://learn.microsoft.com/en-us/entra/architecture/resilience-client-app)
- [gRPC: Connection Backoff Protocol](https://github.com/grpc/grpc/blob/master/doc/connection-backoff.md)
- [Workbox: Strategies for service worker caching](https://developer.chrome.com/docs/workbox/caching-strategies-overview/?authuser=8)
- [web.dev: Keeping things fresh with stale-while-revalidate](https://web.dev/articles/stale-while-revalidate?hl=en)
- [Cloudflare Workers docs: Cache configuration](https://developers.cloudflare.com/workers/cache/configuration/)

[^1]: <https://www.androidauthority.com/spotify-outage-login-issues-3738825/>
[^2]: <https://www.techradar.com/news/live/spotify-down-november-2026>
[^3]: <https://www.tomsguide.com/news/live/spotify-outage-november-24-2026>
[^4]: <https://www.aol.com/articles/spotify-down-company-gives-users-122835000.html>
[^5]: <https://spotify.statuspage.io/>
[^6]: <https://community.spotify.com/forum/en/discussion/7564092/issues-logging-in-randomly-getting-logged-out>
[^7]: <https://sre.google/sre-book/addressing-cascading-failures/?hl=bg>
[^8]: <https://sre.google/sre-book/handling-overload/>
[^9]: <https://cloud.google.com/blog/products/gcp/how-to-avoid-a-self-inflicted-ddos-attack-cre-life-lessons/?m=1>
[^10]: <https://d1.awsstatic.com/builderslibrary/pdfs/timeouts-retries-and-backoff-with-jitter.pdf>
[^11]: <https://www.rfc-editor.org/rfc/rfc9110.pdf>
[^12]: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429>
[^13]: <https://learn.microsoft.com/en-us/entra/architecture/resilience-client-app>
[^14]: <https://github.com/grpc/grpc/blob/master/doc/connection-backoff.md>
[^15]: <https://www.rfc-editor.org/pdfrfc/rfc5861.txt.pdf>
[^16]: <https://web.dev/articles/stale-while-revalidate?hl=en>
[^17]: <https://developer.chrome.com/docs/workbox/caching-strategies-overview/?authuser=8>
[^18]: <https://developers.cloudflare.com/workers/cache/configuration/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
