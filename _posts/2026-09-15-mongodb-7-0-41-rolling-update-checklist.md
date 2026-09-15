---
title: "MongoDB 7.0.41 패치 적용 가이드: 롤링 업데이트에서 확인할 것들"
description: "7.0.41은 CVE 다발과 복구·모니터링·세션 경로 수정이 섞인 패치입니다. 롤링 업데이트에서 실패하는 지점을 절차로 고정합니다."
date: 2026-09-15 12:55:21 +0900
categories: ["Database", "MongoDB"]
tags: ["mongodb", "rolling-upgrade", "replica-set", "sharding", "fcv", "security-patch"]
render_with_liquid: false
---

## 7.0.41은 왜 ‘그냥 패치’로 보면 위험한가

MongoDB 7.0.41은 커뮤니티 공지에서 “7.0.40 이후의 fixes만 포함하며 7.0 사용자에게 권장 업그레이드”로 안내됐습니다[^1]. 공지 자체는 전형적인 패치 릴리스 톤인데, 운영 관점에서 중요한 건 고쳐진 코드 경로가 어디냐입니다.

7.0.41 릴리스 노트는 “security and reliability improvements”를 전면에 두고, CVE 목록이 함께 나옵니다[^2]. 같은 사실을 MongoDB Alerts도 “7.0.0 affects versions prior to 7.0.41” 같은 형태로 정리합니다[^3].

여기서 패치의 성격이 갈립니다.

- 기능 추가가 아니라도 **보안 패치**가 섞이면, 테스트 부족보다 더 위험한 게 “미적용 상태로 노출되는 시간”입니다.
- “reliability fix”의 대상이 startup recovery, replication recovery, admission control 같은 경로면, 롤링 재시작 자체가 트리거가 됩니다.
- 지표 수집이나 상태 확인 명령이 바뀌면(예: collStats), 평소에는 조용하다가 점검 자동화/모니터링이 업그레이드 윈도우에 부하를 추가하면서 사고가 납니다.

또 한 가지. 문서에서 7.0.41 날짜가 2026-09-08로 표기되는 반면[^2], 커뮤니티 공지는 2026-09-09 게시입니다[^1]. 이런 어긋남은 흔히 문서 반영 시점/타임존 차이로 생기지만, 운영 체크리스트 관점에서는 “언제부터 패치가 공개돼 있었는지”보다 “내가 지금 적용하려는 바이너리가 정확히 어떤 빌드인지”가 더 중요합니다. 패치 윈도우에서는 패키지 매니저에서 실제로 내려받는 버전 문자열과 빌드 정보를 기준으로 움직여야 합니다.

그리고 2026-09-15 KST 시점에는 7.0.43이 2026-09-11 날짜로 릴리스 노트에 올라와 있습니다[^2]. 보안/안정성 패치의 흐름상, 현실적으로는 7.0.41만 올릴 계획이었더라도 “왜 7.0.43이 아닌가”를 내부에서 설명할 수 있어야 합니다.

## 7.0.41 수정 목록을 운영 리스크로 번역하기

릴리스 노트에 나오는 이슈 ID는 많습니다. 여기서는 “롤링 업데이트 중 실제로 밟는 경로”와 “문제 발생 시 조사 난이도”를 기준으로 묶습니다.

### 1) unclean shutdown → startup recovery → replica set startup recovery

7.0.41에는 `Handle missing index idents during replica set startup recovery after unclean shutdown`이 들어 있습니다([MongoDB 7.0 릴리스 노트](https://www.mongodb.com/docs/manual/release-notes/7.0/), SERVER-104464).

이게 왜 롤링 업데이트와 맞물리냐면, 패치 적용 자체는 계획된 재시작이지만 현실의 재시작은 종종 “unclean shutdown처럼 보이는 상황”을 동반합니다.

- systemd stop timeout으로 SIGKILL이 떨어지는 케이스
- 스토리지 레이어 I/O stall로 shutdown이 길어지는 케이스
- 노드 재부팅 중 커널 패닉/클라우드 호스트 이슈

MongoDB 소스 트리의 스토리지 문서에도 “unclean shutdown이 체크포인트 이전에 일어나면 catalog entry가 참조하는 ident가 없을 수 있다”는 취지의 설명이 있습니다[^4].

즉, 7.0.41은 “이런 상황이 나쁜 징조”가 아니라 “현실에서 실제로 일어나는 모드”라는 걸 전제로 코드를 다듬은 릴리스에 가깝습니다. 그러면 운영자는 반대로 생각해야 합니다.

- 롤링 업데이트 중 노드 하나가 unclean shutdown처럼 내려가도, 새 버전이 그 상황에서 더 잘 버티는지 확인해야 합니다.
- 반대로, 구버전에서 우연히 지나가던 손상이 7.0.41에서 더 일찍 드러날 수도 있습니다(예: 더 엄격한 검증, 더 명확한 에러). 이건 “7.0.41이 망가뜨렸다”가 아니라 “7.0.41이 숨김을 걷어냈다”에 가까운데, 장애 대응자는 이 프레임을 공유해야 합니다.

### 2) replSetGetStatus를 치는 타이밍과 index build 경로의 충돌

`Index Build Merging Spills conflicts with replSetGetStatus` (SERVER-111885)도 7.0.41에 포함됩니다[^2].

롤링 업데이트 자동화에서 가장 흔한 루프가 이겁니다.

1. secondary 내림
2. 패키지 업그레이드
3. mongod 올림
4. `rs.status()` 또는 `replSetGetStatus`로 SECONDARY 복귀 확인

이 확인 루프가 내부적으로 부하를 만들거나 특정 코드 경로와 경쟁하면, “업그레이드 자체는 됐는데 상태 확인이 흔들려서 자동화가 멈추는” 패턴이 나옵니다. 7.0.41에서 이 충돌을 고친 건, 운영 자동화 안정성에 직결됩니다.

여기서 얻을 결론은 단순합니다.

- 상태 확인 커맨드는 “가볍다”고 가정하지 않습니다.
- 상태 확인 실패는 “노드가 죽었다”보다 “상태 확인이 실패했다”일 수도 있습니다.
- 그래서 사전 점검 스크립트는 `rs.status()` 하나에 올인하지 말고, 최소한 `hello`/TCP 연결/로그 tail 같은 대체 루트를 둬야 합니다.

### 3) collStats가 갑자기 커질 수 있다

`Add configuration to collstats to return full wiredtiger data source metrics` (SERVER-111573)도 운영에서 체감이 큰 편입니다[^2].

이 이슈는 겉으로는 기능 추가인데, “패치 릴리스는 기능 변화가 거의 없다”는 운영 습관을 흔드는 대표 사례입니다. collStats는 모니터링/점검에서 많이 씁니다. 어떤 팀은 shard별로 모든 컬렉션에 대해 주기적으로 collStats를 긁어 시계열 DB로 넣기도 합니다.

여기서 7.0.41 적용 시 확인해야 하는 건 두 가지입니다.

- 기존에 사용하던 collStats 호출이 “새 옵션/새 결과”로 인해 payload가 커져 네트워크/CPU를 더 쓰지 않는지
- 업그레이드 윈도우(특히 mixed-version window)에서 모니터링이 예전보다 더 공격적으로 노드를 때려 재시작 시간을 늘리지 않는지

WiredTiger가 어떤 통계를 어떻게 기록하는지 자체는 WiredTiger 문서에 별도로 정리돼 있습니다[^5]. 서버 측에서 “어떤 통계를 얼마나 노출하느냐”가 바뀌면, 모니터링 비용과 장애 조사 방식이 같이 바뀝니다.

### 4) session refresh가 admission control에 덜 막히도록

7.0.41에는 `Make session refresh have kExempt admission priority` (SERVER-127346)도 포함됩니다[^2].

MongoDB 7.0부터는 overload 상황에서 storage engine transaction tickets를 동적으로 조정하는 기본 알고리즘이 들어갔다고 문서에 명시돼 있습니다[^6].

sessions는 더 아래 레이어에서 “앱이 체감하는 정상성”을 좌우합니다.

- driver는 logical session을 기본으로 활용합니다.
- 세션이 refresh에 실패하거나 지연되면, 애플리케이션은 “DB가 느리다/간헐적으로 에러”처럼 느낍니다.
- 특히 인증/권한/세션 갱신 경로는 트래픽이 피크일 때 같이 피크가 뜨기 때문에, admission control에 같이 묶이면 문제가 커집니다.

세션 자체와 관련 커맨드는 server sessions 문서에 정리돼 있습니다[^7]. 7.0.41은 “세션 refresh는 막히지 않게 하자” 쪽으로 우선순위를 조정한 셈인데, 이런 류의 변경은 부하 상황에서 tail latency가 어떻게 바뀌는지로 검증해야 합니다.

### 5) 7.0.41은 CVE 묶음 릴리스다

릴리스 노트는 7.0.41에 여러 CVE가 포함됐다고 나열합니다[^2]. MongoDB Alerts에서도 7.0.41 미만 버전이 영향을 받는 CVE들이 2026-09-08 날짜로 여러 개 올라와 있습니다[^3].

이 경우 운영 절차가 바뀝니다.

- “장애 위험”만 보는 업그레이드가 아니라, “노출 위험”까지 같이 보는 업그레이드입니다.
- staging burn-in을 길게 잡는 게 항상 정답이 아닙니다. 서비스 노출 면이 크면, 안전성 향상보다 패치 지연이 더 위험할 수 있습니다.

결국 결론은 하나로 모입니다. 7.0.41은 “패치니까 대충 롤링 재시작”이 아니라, “패치이지만 보안/복구/운영 경로가 바뀌는 릴리스”로 취급하는 게 맞습니다.

## 패치 롤링 업데이트에서 고정해야 할 3가지: driver, FCV, mixed-version window

### driver 호환성은 “대체로 된다”가 아니라 “표로 증명한다”

MongoDB 공식 driver compatibility 문서는 “클라이언트 라이브러리가 특정 MongoDB Server major 버전과 호환되면, 특별히 명시되지 않는 한 그 major의 minor/patch에도 호환된다”고 적고 있습니다[^8].

이 문장 하나로 “패치니까 driver는 괜찮겠지”가 정당화되기도 하는데, 프로덕션에서는 이렇게 쪼개는 편이 안전합니다.

- 서버-드라이버 프로토콜 호환: 대체로 유지(문서의 원칙)
- 특정 기능 경로 호환: 예외가 나올 수 있음(예: Queryable Encryption/FLE 경로, auth 메커니즘, Atlas Search 연동 등)
- 런타임/JDK/프레임워크 호환: 앱 레이어에서 더 자주 깨짐(예: Spring Data가 요구하는 JDK 레벨)

그래서 패치 적용 전에 “driver를 먼저 올린다”는 원칙을 문서에 적힌 순서 그대로 적용하는 게 안전합니다. MongoDB도 self-managed patch upgrade 절차에서 “인증을 쓰는 배포는 drivers를 먼저 업그레이드”를 단계로 둡니다[^9].

### FCV는 패치에서 건드릴 이유가 거의 없다

패치 업그레이드(7.0.40 → 7.0.41)에서 FCV를 바꿀 일은 보통 없습니다. FCV는 major upgrade/downgrade의 안전장치에 가깝고, `setFeatureCompatibilityVersion` 커맨드 자체도 “7.0 FCV를 올리거나, 6.0으로 내려서 downgrade를 준비”하는 흐름으로 문서화돼 있습니다[^10].

FCV가 무엇을 보장하는지 더 깊게 보려면, MongoDB 소스 저장소의 FCV/feature flag 설계 문서가 도움이 됩니다[^11].

패치에서 중요한 건 오히려 이겁니다.

- 패치 업그레이드 전후에 FCV가 의도치 않게 바뀌지 않았는지(자동화 스크립트 실수)
- mixed-version window 동안 FCV 관련 경고/에러가 나오지 않는지

### mixed-version window를 줄이는 게 안전의 절반이다

롤링 업데이트에서 가장 취약한 시간은 “한 노드만 새 버전”인 시간과 “절반이 새 버전”인 시간의 합입니다. 이 시간에는 다음이 동시에 벌어질 수 있습니다.

- election/stepdown이 발생할 수 있음
- driver가 primary/secondary를 재탐색(SDAM)하면서 연결 churn이 커질 수 있음
- balancer/AutoMerger/metadata refresh 같은 백그라운드가 동시에 움직일 수 있음

MongoDB는 SDAM 스펙에서 “에러는 문자열이 아니라 숫자 코드로 매칭하라” 같은 안정성 규칙을 강조합니다[^12]. mixed-version window에서는 이런 edge condition이 더 자주 발현됩니다.

운영 절차는 결과적으로 한 가지 방향으로 수렴합니다.

- 노드별 업그레이드 후 검증을 빠르게 끝내고 다음 노드로 넘어가 mixed-version window를 줄인다.
- 단, “빨리”는 “대충”이 아니라 “검증을 자동화해서 빨리”여야 합니다.

## Replica Set: 7.0.41 롤링 업데이트 절차에서 ‘진짜로’ 확인할 것들

MongoDB 문서의 패치 업그레이드 절차는 replica set에서 secondaries를 먼저 올리고 primary를 마지막에 올리라고 정리합니다[^9]. 이 순서는 바뀌지 않습니다.

다만 프로덕션에서는 “순서”보다 “각 단계에서 무엇을 확인해야 하는지”가 결과를 가릅니다.

### 0) 업그레이드 직전에 확인할 상태(업그레이드하면 더 늦는 것들)

- replication lag이 평소보다 튀어 있지 않은지
- `ROLLBACK`, `RECOVERING`, `STARTUP2` 같은 비정상 상태가 없는지(업그레이드를 시작하면 더 오래 걸립니다)
- 장시간 실행 중인 index build/TTL batch가 없는지
- 디스크/파일시스템에서 IO wait이 이미 높지 않은지(재시작 recovery 시간이 늘어납니다)

여기서 7.0.41과 직접 연결되는 포인트는 “unclean shutdown 후 startup recovery”입니다. 재시작이 잦은 작업인데, 이미 IO가 불안정하면 unclean shutdown처럼 보이는 종료가 나올 확률이 올라갑니다.

### 1) secondaries부터 올릴 때의 함정: election과 read traffic

secondaries 업그레이드는 보통 다음과 같이 진행됩니다.

1. 특정 secondary를 drain
2. mongod stop
3. 패키지/바이너리 교체
4. mongod start
5. SECONDARY 복귀 확인

여기서 실제 장애가 나는 지점은 1번과 5번입니다.

- 1번에서 “secondary로 가던 read가 primary로 몰리면서 primary latency가 튀는” 케이스가 흔합니다.
- 5번에서 “SECONDARY 복귀는 했는데 catch-up이 덜 됐고, 그 상태에서 다음 노드를 내려 replica set이 불안정해지는” 케이스가 흔합니다.

그래서 SECONDARY 복귀 확인을 다음처럼 분리합니다.

- 상태 머신: SECONDARY인가
- 데이터 동기화: primary와 optime 차이가 허용 범위인가

### 2) primary 업그레이드의 핵심: stepDown을 ‘의도적으로’ 만든다

문서도 primary에서는 `rs.stepDown()`으로 의도적 failover를 만들라고 안내합니다(major upgrade 문서지만 흐름은 동일합니다: secondaries → stepDown → primary)[^13].

패치에서도 같은 전략을 쓰는 이유는 단순합니다.

- primary를 내리면 write가 멈춥니다.
- 멈추는 시간을 “예측 가능하게” 만들면, 앱 레이어에 graceful degradation을 넣을 수 있습니다.

stepDown을 쓰면 선거가 “언제 일어날지”를 운영자가 통제합니다. 운영에서 통제 가능한 실패는 통제 불가능한 실패보다 훨씬 싸게 끝납니다.

### 3) 7.0.41에서 특히 신경 쓰는 검증 포인트

- 재시작 로그에서 unclean shutdown 감지 및 recovery 메시지 확인(평소보다 과도하게 오래 걸리는지)
- `rs.status()`/`replSetGetStatus` 확인 루프가 비정상적으로 실패하지 않는지(7.0.41이 관련 충돌을 고쳤지만, 자동화가 과도하게 치면 여전히 문제를 만들 수 있습니다)
- 세션 관련 에러/경고가 갑자기 늘지 않는지(세션 refresh 우선순위 변경의 반작용을 빠르게 감지)

## Sharded Cluster: 7.0.41 롤링 업데이트에서 order가 중요한 이유

MongoDB는 patch upgrade 문서에서 sharded cluster 업그레이드 순서를 명시합니다.

1) balancer 비활성화
2) config servers 업그레이드
3) shards 업그레이드
4) mongos 업그레이드
5) balancer 재활성화

[^9]

이 순서는 “그게 예쁘니까”가 아니라, config server가 들고 있는 메타데이터/락이 sharded cluster 전체의 일관성을 쥐고 있기 때문입니다.

### 1) balancer: stop 했다고 바로 멈춘 게 아니다

`sh.stopBalancer()`는 “진행 중인 balancing round가 있으면 완료될 때까지 기다린다”고 문서에 적혀 있습니다[^14]. 그리고 `sh.isBalancerRunning()`/`sh.getBalancerState()`로 “enabled vs running”을 구분하라고 합니다[^15].

실전 체크는 이렇게 고정합니다.

- enabled가 꺼졌는가: `sh.getBalancerState() == false`
- 실제 migration이 멈췄는가: `sh.isBalancerRunning() == false`

그리고 7.0부터는 “balancer stop이 AutoMerger도 같이 끈다”는 변경이 있습니다[^14][^15]. 업그레이드 윈도우가 길어지면 이 효과가 누적됩니다.

- chunk 분할/병합이 막히면, 특정 shard에 hot range가 몰린 상태가 더 오래 지속될 수 있습니다.
- 업그레이드 끝나고 balancer를 켰는데도 “원복까지 시간”이 더 필요합니다.

그래서 sharded cluster 패치는 replica set보다 “윈도우를 더 짧게” 가져가야 합니다.

### 2) config server는 ‘특별한 replica set’이다

config server는 shard metadata, 인증/권한 관련 일부 설정, distributed lock을 저장합니다[^16].

이 문서에서 운영자가 바로 써먹는 제약 조건은 다음입니다.

- config server replica set은 arbiter를 둘 수 없습니다[^16].

즉, shard 쪽에는 PSA 구성이 남아 있을 수 있지만, config server는 애초에 PSA로 버티는 식의 “대충 고가용성”을 허용하지 않습니다. 업그레이드 자동화에서 config server를 shard와 같은 취급으로 묶으면 사고가 납니다.

### 3) mongos는 마지막에 올린다: 캐시와 타임아웃

patch upgrade 문서도 mongos는 마지막에 올리라고 합니다[^9]. 7.0.41 릴리스 노트에는 `mongos`의 pre-auth streamable hello 최소 timeout 관련 수정(SERVER-132650)도 포함돼 있습니다[^2].

mongos는 성격상 “서버”라기보다 “routing tier”이고, 내부적으로 config server metadata를 캐시합니다[^16]. mixed-version window에서 mongos가 구버전이면, 새 버전 config/shard와 상호작용하는 경계에서 이상 행동이 나오기 쉽습니다. 그래서 마지막에 올리되, 마지막에 올릴 때는 빠르게 모두 올려 routing tier의 버전 분산 시간을 줄이는 쪽이 낫습니다.

## 실제로 실행하는 사전 점검 스크립트(mongosh)

아래 스크립트는 “패치 롤링 업데이트를 시작해도 되는지”를 최소 조건으로 판정합니다.

- replica set이면: member state, lag, FCV, 버전
- mongos로 접속하면(sharded cluster): balancer 상태

### 1) precheck.mjs

```javascript
// precheck.mjs
// 실행 예:
// mongosh "mongodb://admin:***@rs0-1,rs0-2,rs0-3/admin?replicaSet=rs0&authSource=admin" --quiet --file precheck.mjs
// mongosh "mongodb://admin:***@mongos-1/admin?authSource=admin" --quiet --file precheck.mjs

function fail(msg, ctx = {}) {
  print(JSON.stringify({ ok: false, msg, ...ctx }, null, 2));
  quit(2);
}

function safeAdmin(cmd) {
  try {
    return db.adminCommand(cmd);
  } catch (e) {
    fail("adminCommand failed", { cmd, error: e.toString() });
  }
}

const hello = safeAdmin({ hello: 1 });
const buildInfo = safeAdmin({ buildInfo: 1 });
const fcv = safeAdmin({ getParameter: 1, featureCompatibilityVersion: 1 });

const out = {
  ok: true,
  isMongos: hello.msg === "isdbgrid",
  serverVersion: buildInfo.version,
  fcv: fcv.featureCompatibilityVersion,
  host: hello.me,
  setName: hello.setName || null,
  isWritablePrimary: !!hello.isWritablePrimary,
};

// replica set 상태 점검
if (hello.setName && !out.isMongos) {
  const st = safeAdmin({ replSetGetStatus: 1 });
  const members = (st.members || []).map((m) => ({
    name: m.name,
    stateStr: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate,
    lastHeartbeatMessage: m.lastHeartbeatMessage,
  }));

  const badStates = new Set(["ROLLBACK", "RECOVERING", "STARTUP2"]);
  const unhealthy = members.filter((m) => m.health !== 1);
  const bad = members.filter((m) => badStates.has(m.stateStr));

  if (unhealthy.length) {
    fail("Some members are unhealthy", { unhealthy, serverVersion: out.serverVersion });
  }
  if (bad.length) {
    fail("Some members are in a risky state", { bad, serverVersion: out.serverVersion });
  }

  out.replicaSet = { members };
}

// sharded cluster 점검( mongos로 접속한 경우 )
if (out.isMongos) {
  // sh.* helpers는 mongos에서만 의미가 있습니다.
  let balancer = {};
  try {
    balancer = {
      enabled: sh.getBalancerState(),
      running: sh.isBalancerRunning(),
    };
  } catch (e) {
    fail("Failed to query balancer state", { error: e.toString() });
  }

  out.balancer = balancer;
}

print(JSON.stringify(out, null, 2));
quit(0);
```

### 2) 실행 명령과 기대 출력

replica set 예시:

```bash
mongosh "mongodb://admin:***@rs0-1,rs0-2,rs0-3/admin?replicaSet=rs0&authSource=admin" \
  --quiet \
  --file precheck.mjs
```

기대 출력(예시):

```json
{
  "ok": true,
  "isMongos": false,
  "serverVersion": "7.0.40",
  "fcv": {"version": "7.0"},
  "host": "rs0-1:27017",
  "setName": "rs0",
  "isWritablePrimary": true,
  "replicaSet": {
    "members": [
      {"name": "rs0-1:27017", "stateStr": "PRIMARY", "health": 1},
      {"name": "rs0-2:27017", "stateStr": "SECONDARY", "health": 1},
      {"name": "rs0-3:27017", "stateStr": "SECONDARY", "health": 1}
    ]
  }
}
```

mongos 예시:

```bash
mongosh "mongodb://admin:***@mongos-1/admin?authSource=admin" \
  --quiet \
  --file precheck.mjs
```

기대 출력(예시):

```json
{
  "ok": true,
  "isMongos": true,
  "serverVersion": "7.0.40",
  "fcv": {"version": "7.0"},
  "host": "mongos-1:27017",
  "setName": null,
  "isWritablePrimary": false,
  "balancer": {"enabled": true, "running": false}
}
```

이 스크립트가 통과하지 못하면, 롤링 업데이트는 더 실패하기 쉽습니다. 특히 sharded cluster에서 balancer 상태 확인은 `sh.stopBalancer()`의 효과를 “명령 성공”이 아니라 “실제 멈춤”으로 검증하기 위해 필요합니다[^15].

## Replica Set 롤링 업그레이드 자동화: systemd + ssh 기반 최소 스크립트

환경을 특정하지 않는다고 해도, 결국 프로덕션에서 가장 자주 마주치는 형태는 “VM + systemd + 패키지 매니저”입니다. 아래는 그 형태를 전제로 한 최소 스크립트입니다.

핵심은 이겁니다.

- 노드 교체(패키지 업그레이드)와 검증(SECONDARY 복귀)을 한 묶음으로 한다.
- 검증이 끝나기 전에는 다음 노드로 넘어가지 않는다.

### 1) roll-rs-upgrade.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# ===== 사용자가 채워야 하는 값 =====
RS_URI='mongodb://admin:***@rs0-1,rs0-2,rs0-3/admin?replicaSet=rs0&authSource=admin'
SSH_USER='ubuntu'
NODES=(rs0-1 rs0-2 rs0-3)
TARGET_VERSION='7.0.41'

# Debian/Ubuntu라면 예를 들어 이런 식으로 version pin이 됩니다.
# 실제로는 `apt-cache madison mongodb-org-server | grep 7.0.41` 같은 방식으로
# 배포판이 제공하는 정확한 패키지 버전 문자열(7.0.41 또는 7.0.41-1)을 확인해야 합니다.
APT_VERSION_STRING='7.0.41'

# ===== 공통 유틸 =====
log() { echo "[$(date -Is)] $*"; }

mongo_eval() {
  mongosh "$RS_URI" --quiet --eval "$1"
}

wait_member_state() {
  local member="$1" state="$2" timeout_s="$3"
  local start
  start=$(date +%s)

  while true; do
    local cur
    cur=$(mongo_eval "JSON.stringify(rs.status().members.find(m=>m.name==='${member}').stateStr)")
    cur=${cur//"/}

    if [[ "$cur" == "$state" ]]; then
      return 0
    fi

    local now
    now=$(date +%s)
    if (( now - start > timeout_s )); then
      log "timeout waiting ${member} to become ${state}, last=${cur}"
      return 1
    fi

    sleep 2
  done
}

upgrade_node_apt() {
  local host="$1"
  log "upgrading ${host} to ${TARGET_VERSION} via apt"

  ssh -o BatchMode=yes "${SSH_USER}@${host}" bash -s <<'EOSSH'
set -euo pipefail
sudo systemctl stop mongod
sudo apt-get update -y
sudo apt-get install -y "mongodb-org-server='

[^1]: <https://www.mongodb.com/community/forums/t/mongodb-7-0-41-is-released/343299>
[^2]: <https://www.mongodb.com/docs/manual/release-notes/7.0/>
[^3]: <https://www.mongodb.com/resources/products/alerts>
[^4]: <https://github.com/mongodb/mongo/blob/master/src/mongo/db/storage/README.md>
[^5]: <https://source.wiredtiger.com/11.2.0/tool-statistics.html>
[^6]: <https://www.mongodb.com/docs/manual/reference/command/serverStatus/>
[^7]: <https://www.mongodb.com/docs/manual/reference/server-sessions/>
[^8]: <https://www.mongodb.com/docs/drivers/compatibility/>
[^9]: <https://www.mongodb.com/docs/v7.0/tutorial/upgrade-revision/>
[^10]: <https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/>
[^11]: <https://github.com/mongodb/mongo/blob/master/src/mongo/db/repl/FCV_AND_FEATURE_FLAG_README.md>
[^12]: <https://github.com/mongodb/specifications/blob/master/source/server-discovery-and-monitoring/server-discovery-and-monitoring.md>
[^13]: <https://www.mongodb.com/docs/manual/release-notes/7.0-upgrade-replica-set/>
[^14]: <https://www.mongodb.com/docs/manual/reference/method/sh.stopbalancer/>
[^15]: <https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/>
[^16]: <https://www.mongodb.com/docs/manual/core/sharded-cluster-config-servers/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
