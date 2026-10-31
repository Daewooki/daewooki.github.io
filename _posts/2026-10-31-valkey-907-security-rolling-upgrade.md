---
title: "Valkey 9.0.7 보안 릴리스 롤링 업그레이드 체크리스트"
description: "Valkey 9.0.7 SECURITY 패치를 클러스터·레플리카·클라이언트 조합에서 안전하게 롤링하는 실전 체크리스트."
date: 2026-10-31 10:27:56 +0900
categories: ["News", "Database"]
tags: ["valkey", "security-release", "rolling-upgrade", "valkey-cluster", "acl", "redis-migration"]
render_with_liquid: false
---

## 2026-10-26~27에 무슨 일이 있었나: 9.0.7은 ‘기능 릴리스’가 아니라 사고 대응 릴리스

Valkey 9.0.7은 릴리스 노트에서 업그레이드 긴급도를 **SECURITY**로 명시했습니다.[^1]

이 문구가 과장이 아닌 이유는, 이번 건이 “특정 명령의 edge case”가 아니라 클러스터 모드의 Pub/Sub 경로에서 heap buffer overflow가 발생하는 결함이기 때문입니다. 9.0.7 릴리스에는 GHSA-f4q9-j22m-xqq9가 포함되고, 클러스터 Pub/Sub 메시지 구성 과정의 heap buffer overflow를 수정했다고 적혀 있습니다.[^1]

날짜가 26~27로 엇갈리는 것도 정상입니다. GitHub 릴리스 본문은 “Released Mon 26 October 2026”로 표기되지만, 태그가 공개된 시각은 10월 27일로 보일 수 있습니다.[^1]  또한 valkey.io의 릴리스 목록은 9.0.7을 2026-10-27로 적고 있습니다.[^2]  KST 기준으로는 2026-10-26 늦은 밤~2026-10-27 새벽에 공개된 것으로 해석하는 게 자연스럽습니다.

여기서 중요한 건 날짜보다도 “이번 주 배포 윈도우에 태울지” 결정을 위한 팩트입니다.

* 취약점은 GHSA-f4q9-j22m-xqq9로 2026-10-26에 공개되었습니다.[^3]
* 영향 범위는 9.0.6 이하(9.0 계열)이며 9.0.7에서 패치되었습니다.[^3]
* 클러스터 모드에서만 영향이 있고, 클러스터 모드를 켜지 않은 서버는 영향을 받지 않습니다.[^3]

이 글은 “업데이트하세요”로 끝내지 않고, Redis→Valkey 전환/병행 중인 팀이 실제로 롤링 업그레이드를 안전하게 수행할 때 어디서 깨지는지(프로토콜·모듈·ACL·백업·리드 레플리카 검증까지) 기준을 남깁니다.

## GHSA-f4q9-j22m-xqq9 한 줄 요약: 클러스터 Pub/Sub 경로의 길이 truncation → overflow

보안 권고문은 영향(Impact)을 꽤 구체적으로 씁니다.

* 공격자는 “클러스터 모드에서 채널에 publish할 수 있는 authenticated 사용자”입니다.[^3]
* 공격이 성공하면 (1) 서버 프로세스를 안정적으로 crash 시킬 수 있고, (2) overflow 바이트를 공격자가 통제할 수 있어 권고문은 RCE 가능성까지 언급합니다.[^3]
* CVSS v3.1 base score는 8.8(High)로 기재되어 있습니다.[^3]

원인은 단순합니다. 클러스터 노드가 `PUBLISH`/`SPUBLISH`를 다른 노드로 전파할 때 메시지 전체 길이를 `size_t`로 계산하고, 이 길이를 `uint32_t`를 받는 함수로 넘기면서 `UINT32_MAX`를 초과하면 길이가 조용히 truncate 됩니다. 그 뒤 `memcpy`가 “전체 메시지 길이만큼” 복사하면서 heap buffer overflow가 납니다.[^3]

세부 조건이 하나 더 있습니다.

* 직접 클라이언트 요청으로 4GiB+ payload를 만들기는 `proto-max-bulk-len` 기본값(512MB) 때문에 불가능하다고 권고문은 짚습니다.
* 대신 스크립트가 서버 내부에서 거대한 문자열을 구성할 수 있고, 그 문자열을 publish 경로로 흘려보내면 문제가 됩니다.[^3]

즉, “클러스터 + Pub/Sub + 스크립팅(EVAL/FCALL/FUNCTION) 허용”이 겹치면 위험도가 급상승합니다. 여기서 팀별로 판단이 갈립니다.

## ‘이번 주에 태울지’ 판단을 갈라놓는 4가지 질문

보안 패치의 우선순위를 정할 때 나는 아래 4가지를 먼저 확인합니다. (이 순서가 실제 롤링 설계 순서이기도 합니다.)

### 1) cluster-enabled 인가

권고문은 “클러스터 모드에서만 영향”이라고 못 박습니다.[^3]

문제는 실무에서 “클러스터 모드”가 단지 Valkey Cluster만 의미하지 않는다는 점입니다.

* Valkey Cluster를 운영 중이면 당연히 해당.
* 운영은 Sentinel인데도 일부 환경에서 cluster-enabled를 켜고 사용하는 경우가 있습니다(특히 개발/테스트에서 구성 드리프트가 자주 생깁니다).

최소한 배포 전에 전 노드에서 `CONFIG GET cluster-enabled` 또는 `INFO`를 수집해 “진짜로 클러스터 모드가 켜져 있는지”를 스냅샷으로 남겨두는 게 좋습니다.

### 2) Pub/Sub 노출면이 외부(또는 다중 테넌트)에 열려 있나

권고문은 “채널에 publish 가능한 authenticated user”를 공격자로 가정합니다.[^3]

여기서 ‘authenticated’는 안전의 의미가 아닙니다. 다음 케이스면 충분히 공격 경로가 됩니다.

* 여러 서비스가 같은 Valkey Cluster를 공유하고, 서비스별로 ACL이 느슨한 경우
* SaaS에서 고객별 워커/잡을 Pub/Sub로 흘리는 구조
* 내부 시스템이라도, 공격자가 침투했을 때 lateral movement가 쉬운 네트워크 토폴로지

반대로 “단일 서비스 전용 클러스터 + 네트워크 레벨로 완전히 격리 + ACL로 Pub/Sub와 scripting을 통제”라면 우선순위가 떨어질 수 있습니다.

### 3) 스크립팅(EVAL/FCALL/FUNCTION)을 허용하고 있나

이번 취약점은 `proto-max-bulk-len` 기본값 때문에 클라이언트가 직접 4GiB+ argument를 보내기 어렵고, 권고문은 스크립트로 구성 가능성을 명확히 적습니다.[^3]

내 경험상, Redis/Valkey를 쓰는 팀이 스크립팅을 ‘명시적으로 쓰는지’와 ‘실제로 열려 있는지’가 다릅니다.

* 개발자는 Lua/Functions를 안 쓴다고 생각하지만, 라이브러리(특히 rate limiting, distributed lock, queue visibility 같은 영역)가 내부적으로 EVAL을 쓰는 경우가 흔합니다.
* ACL은 `+@all -@dangerous` 형태로 잡아두고 “대충 위험한 건 뺐다”고 믿는 경우가 많습니다.

Valkey ACL 문서 자체가 `+@all`은 모듈 커맨드까지 포함해 미래 커맨드까지 열릴 수 있다고 경고합니다.[^4]

### 4) 롤링 중 ‘부분 패치 상태’를 감당할 수 있나

이 취약점은 “클러스터 전체가 패치되면 안전”이 아닙니다. 롤링 중에는 구버전 노드가 남아 있고, 그 노드는 여전히 crash/RCE 가능 경로를 품고 있습니다.

이게 왜 중요하냐면, 롤링 업그레이드는 보통 “장애를 피하려고” 하는데 보안 패치 롤링은 반대로 “롤링하는 그 기간 자체가 공격 윈도우”가 될 수 있기 때문입니다.

따라서 보안 릴리스는 롤링 시간을 최소화하는 쪽으로 설계(동시 shard 수, 배포 파이프라인 병렬도, 사전 검증 자동화)하는 게 맞습니다.

## 9.0.7에 같이 묶여 들어온 것들: 보안 이슈는 1개지만 운영 리스크는 여러 축

릴리스 노트 기준으로 9.0.7에는 보안 수정 1개와 여러 bug fix가 들어 있습니다.[^1]

내가 이번 롤링에서 특히 신경 쓰는 항목만 뽑으면 아래입니다.

* Streams 관련 커맨드들이 consumer-group/PEL 상태를 바꿔도 `WATCH`와 client-side tracking invalidation을 트리거하지 않던 문제를 고쳤습니다.[^1]
  * 트랜잭션/optimistic locking을 쓰는 워크로드에서는 “고쳐져야 할 버그”지만, 관측 가능한 동작이 바뀝니다.
* `CLIENT PAUSE WRITE` 또는 `CLUSTER FAILOVER` 등으로 서버가 write pause 상태일 때 module write 커맨드를 reject하도록 바꿔 crash를 막았습니다.[^1]
  * 모듈을 적극적으로 쓰는 팀은 롤링 중 failover와 모듈 동작이 동시에 발생할 때의 영향을 봐야 합니다.
* `RESTORE` payload의 string length overflow로 서버 abort가 나던 케이스를 “bad data로 reject”하도록 바꿨습니다.[^1]
  * 백업/복구 파이프라인에서 `RESTORE`를 직접 쓰거나, 마이그레이션 도구가 `RESTORE`를 쓰는 경우 영향이 있습니다.
* `valkey-check-aof`가 multipart AOF에서 RDB base file의 `VALKEY` signature를 인식하지 못해 잘못 invalid로 보고하던 문제를 수정했습니다.[^1]
  * 운영 중 AOF 무결성 점검을 자동화해 둔 팀이면 false alarm이 줄어듭니다.

결론적으로 9.0.7은 “보안 패치 1개”만 보고 태우면 곤란하고, 롤링 전에 최소한 Streams/WATCH, 모듈, 백업/복구 경로의 회귀 테스트가 필요합니다.

## 호환성 축을 쪼개서 본다: 서버↔서버, 서버↔클라이언트, 데이터↔버전

Redis→Valkey 전환 중인 팀은 특히 “서버 버전만 올리면 끝”이 아닙니다. 혼종 조합이 필연적으로 생깁니다.

Valkey 공식 마이그레이션 문서는 Valkey가 Redis OSS 7.2 및 이전과의 호환성을 유지한다고 설명하고, 프로토콜·데이터 포맷·설정·CLI·INFO·모듈 호환을 항목별로 나눠 정리합니다.[^5]

여기서 롤링 업그레이드와 직접 충돌하는 지점만 정리하면 다음 3가지입니다.

### 서버↔클라이언트: RESP2/RESP3, Cluster redirection, Pub/Sub semantics

Valkey는 RESP를 사용하고 RESP2/RESP3를 모두 지원합니다.[^6]

문제는 “지원한다”는 것과 “운영에서 안전하다”는 게 다르다는 점입니다.

* 클라이언트가 `HELLO 3`로 RESP3로 협상하는지
* Cluster client가 MOVED/ASK redirection을 제대로 처리하는지
* Pub/Sub 사용 방식이 단순 subscribe인지, sharded Pub/Sub(`SPUBLISH`)까지 쓰는지

Valkey 문서는 RESP가 Pub/Sub에서 push semantics로 바뀐다는 점을 분명히 설명합니다.[^6]

롤링 업그레이드 중에는 재연결과 리다이렉션이 평소보다 빈번해지므로, “평시엔 잘 되던 클라이언트”가 롤링 중에만 깨지는 일이 발생합니다.

### 서버↔서버: cluster bus, failover, 복제 offset

Valkey Cluster는 클라이언트 포트 외에 cluster bus 포트를 사용하고, 기본으로 data port + 10000을 씁니다.[^7]

또한 cluster bus는 기본적으로 메시지 인증을 하지 않으니 네트워크 격리가 필수라고 문서가 경고합니다.[^7]

이번 취약점은 cluster mode에서만 발생합니다. 즉, “클러스터를 쓰는 순간” cluster bus 보안/네트워크 격리/ACL 모델까지 같이 봐야 합니다.

### 데이터↔버전: RDB/AOF 호환, multipart AOF, 복구 도구

Valkey 마이그레이션 문서는 Valkey가 Redis OSS 7.2와 호환되는 RDB/AOF를 읽고 쓰며, Redis CE 7.4+가 만든 RDB는 호환되지 않는다고 명확히 씁니다.[^5]

이건 “마이그레이션 때만 중요”한 게 아닙니다.

* 롤링 중 노드 교체/재조인이 생기면, snapshot에서 새 노드를 띄우는 시나리오가 많습니다.
* 사고가 나면 결국 RDB/AOF를 가지고 복구합니다.

따라서 롤링 체크리스트에는 항상 “백업을 떴나”가 아니라 “백업으로 복구 리허설을 했나”가 들어가야 합니다.

## 롤링 업그레이드 사전 체크리스트: ‘노드 교체’가 아니라 ‘시스템 변경’으로 취급

여기부터는 실전 체크리스트입니다. 내가 플릿 업그레이드를 굴릴 때는 각 항목에 담당자를 박습니다. 그게 아니면 결국 “다 했겠지”가 됩니다.

### 1) 인벤토리: 어떤 노드가 어떤 역할이며 어떤 버전인가

* `valkey_version` / `server_name` 수집: Valkey는 호환성을 위해 `INFO`에 `redis_version:7.2.4`를 보고할 수 있고, 실제 버전은 `server_name`과 `valkey_version`으로 확인하라고 문서가 씁니다.[^5]
* cluster topology 스냅샷: `CLUSTER NODES`, `CLUSTER INFO`, `ROLE` 출력 보관
* feature flag 스냅샷: `CONFIG GET *`를 다 저장하는 게 아니라, 아래만 뽑아서 diff가 잘 보이게 합니다.
  * `cluster-enabled`, `cluster-announce-*`, `tls-*`, `tls-cluster`
  * `aclfile` 경로 및 운영 방식
  * `appendonly`, `aof-use-rdb-preamble`, `aof-load-truncated`
  * `proto-max-bulk-len`

`proto-max-bulk-len`은 기본이 512mb라는 설명이 기본 설정 파일에도 들어 있습니다.[^8]  이번 GHSA의 mitigation이 “이 값을 올리지 말라”이기 때문에 더더욱 기록을 남겨야 합니다.[^3]

### 2) 노출면 줄이기: 롤링 기간 동안만이라도 공격 비용을 올린다

권고문은 mitigation으로 scripting 커맨드를 제한하고(`EVAL`, `FCALL`, `FUNCTION` 등), `proto-max-bulk-len`을 기본값 이상으로 올리지 말라고 권합니다.[^3]

여기서 현실적인 선택지는 2개입니다.

* (A) 스크립팅을 원래 안 써야 하는 서비스라면, 롤링 전에 ACL로 `@scripting`을 끕니다.
  * Valkey ACL 문서에서 `ACL CAT`로 `scripting` 카테고리를 확인할 수 있습니다.[^4]
* (B) 스크립팅을 쓰는 서비스라면, 최소한 “누가 쓸 수 있는지”를 줄입니다.
  * 예: 워커 전용 계정만 scripting 허용, API 서버 계정은 deny.

나는 (A)가 가능한 팀은 이번 배포 윈도우에서 바로 9.0.7을 태우는 쪽이 총 위험이 낮다고 봅니다. (B)인 팀은 롤링 시간을 줄이는 게 핵심입니다.

### 3) 백업/복구 계획: 롤링은 ‘되돌릴 수 있어야’ 한다

9.0.7은 보안 릴리스라서 “급하게 올리고 나중에 정리”를 하고 싶어집니다. 그런데 Valkey/Redis 계열은 한번 삐끗하면 데이터 복구 비용이 급증합니다.

최소한 다음은 롤링 시작 전에 끝내는 편이 낫습니다.

* RDB snapshot 1회 + AOF 파일 세트(사용 중이면) 보관
* 복구 리허설: 별도 격리 환경에서 snapshot으로 노드 1개를 띄우고, 애플리케이션의 핵심 read path가 정상인지 확인
* `valkey-check-aof`를 자동화해 둔 팀이면, 9.0.7에서 multipart AOF 인식이 바뀌는 점을 감안해 “업그레이드 전후” 알람 노이즈를 점검[^1]

### 4) 관측(Observability) 기준: ‘성공’ 정의가 없으면 롤링은 끝나지 않는다

내 기준으로 롤링 성공은 “버전이 올랐다”가 아닙니다.

* cluster state가 `ok`
* failover 이후에도 p99 latency가 정상 범위
* replica lag이 허용 범위 내
* Pub/Sub drop / consumer lag이 폭증하지 않음
* 클라이언트 에러(MOVED/ASK, timeout, connection reset) 비율이 베이스라인으로 회귀

이걸 정의하지 않으면 롤링은 마지막에 “그냥 끝”이 됩니다.

## Valkey Cluster 롤링 업그레이드 절차: 문서의 7단계를 ‘운영 체크포인트’로 바꾼다

Valkey 공식 cluster tutorial은 롤링 업그레이드 절차를 shard 단위(Primary + Replicas)로 정리합니다. 핵심은 “replica를 먼저 업그레이드하고, manual failover로 primary를 바꾼 뒤, 구 primary를 업그레이드한다”입니다.[^7]

문서에 적힌 1~7단계를 그대로 따라도 되지만, 실무에서는 각 단계의 ‘검증 포인트’를 추가해야 안전해집니다.[^7]

### 단계 0: shard를 업그레이드하기 전에 ‘변수’를 고정한다

* 롤링 중에는 resharding을 하지 않습니다.
* 롤링 중에는 ACL을 동시에 크게 바꾸지 않습니다.
* 롤링 중에는 `proto-max-bulk-len` 같은 안전장치를 만지지 않습니다.

바꾸고 싶으면 업그레이드 전날 바꾸거나, 업그레이드가 끝난 다음에 바꿉니다. 변경을 섞으면 장애 원인 분리가 안 됩니다.

### 단계 1: (선택) 패치 버전 노드를 새 replica로 먼저 붙인다

문서는 “업그레이드된 노드를 새 replica로 추가”하는 방식을 옵션으로 소개합니다.[^7]

이 방식의 장점은 단순합니다.

* 롤링 중 replica 수를 깎지 않고도 노드를 교체할 수 있습니다.

단점도 명확합니다.

* 비용이 듭니다(추가 노드).
* 네트워크/인증/TLS/ACL 같은 “붙이는 과정의 리스크”가 생깁니다.

보안 릴리스에서는 나는 이 방식을 더 선호합니다. 이유는 “업그레이드 중 일부 노드가 취약한 기간”을 줄이는 데 유리하기 때문입니다. 구 노드를 내리기 전에 패치 노드를 올려두면, shard의 복제 여력이 커지고 failover 시도도 공격적으로 할 수 있습니다.

### 단계 2: 기존 replica를 9.0.7로 교체/재시작

문서는 replica 업그레이드는 “중지 후 새 버전으로 재시작”이면 된다고 말합니다.[^7]

운영에서는 이때 아래를 자동으로 확인합니다.

* 프로세스가 살아났는가(health check)
* `INFO REPLICATION`에서 `master_link_status:up` 인가[^7]
* replica lag이 급증하지 않는가
* 클라이언트 read 트래픽이 replica로 분산되어 있으면, read error 비율이 튀지 않는가

### 단계 3: 승격할 patched replica를 고르고, replication offset을 확인

문서는 primary와 replica의 `master_repl_offset`을 비교하라고 안내합니다.[^7]

내 경험상 여기서 자주 나오는 함정이 있습니다.

* 쓰기 트래픽이 지속되는 시스템은 offset이 “완전히 같아지는 순간”이 없습니다.
* 그렇다고 대충 승격하면, 승격 순간의 write blocking이 길어지고 애플리케이션 timeout이 늘어납니다.

나는 “승격 대상 replica의 lag이 특정 임계치 이하(예: 50ms~200ms 등 서비스 성격에 맞게)”를 조건으로 걸고, 그 임계치 이하로 떨어질 때까지 기다리는 쪽이 안정적이었습니다.

### 단계 4: 승격 대상 replica가 클러스터 전체에 인지되었는지 확인

문서는 `CLUSTER NODES`를 각 노드에서 확인하라고 합니다.[^7]

이걸 대충 넘기면, failover election이 지연되거나 실패해서 롤링 시간이 늘어납니다.

### 단계 5: `CLUSTER FAILOVER`로 manual failover 수행

Valkey 문서는 manual failover가 “데이터 손실을 피하는 방식으로” 진행되고, replica가 primary replication stream을 다 처리했을 때 전환한다고 설명합니다.[^7]

이 단계에서 애플리케이션은 다음을 겪습니다.

* primary로 들어오던 write가 순간적으로 block
* 일부 클라이언트는 MOVED/ASK를 맞고 재라우팅

따라서 클라이언트 드라이버(특히 cluster client)의 redirection 처리 품질이 롤링 체감 품질을 결정합니다.

### 단계 6: 전환 완료 확인

문서는 `ROLE`, `INFO REPLICATION`, `CLUSTER NODES`로 role 변화를 확인하라고 합니다.[^7]

운영 체크포인트로는 아래까지 봅니다.

* 새 primary에서 write 성공률이 정상인지
* 구 primary가 replica로 내려왔는지
* cluster state가 `ok`인지

### 단계 7: 구 primary(이제 replica)를 업그레이드

여기서 중요한 운영 원칙 하나.

* shard 단위 롤링에서 “구 primary 업그레이드”를 미루면, 취약 노드가 오래 남습니다.

보안 릴리스에서는 shard 하나 끝냈으면 그 shard의 구버전을 바로 치우는 편이 맞습니다.

## 롤링 중 ‘호환성’ 사고가 나는 지점: 클라이언트 드라이버와 운영 커맨드

Valkey는 “Redis 7.2 wire protocol을 말하는 클라이언트는 대부분 코드 변경 없이 붙는다”고 말합니다.[^9]

이 말이 틀리진 않지만, 롤링 업그레이드 관점에서는 문장을 조금 다르게 읽어야 합니다.

* 평시에 붙는 것 ≠ failover/rolling 시나리오에서 안전

나는 클라이언트를 다음 3그룹으로 분류합니다.

### 1) Cluster aware client

MOVED/ASK를 처리하고 slot map을 유지하는 클라이언트입니다.

Valkey Cluster spec은 클라이언트가 -ASK redirection까지 처리해야 “완전한 Cluster client”라고 말합니다.[^10]

롤링 업그레이드에서 가장 중요한 건 “재시도 정책”입니다.

* MOVED/ASK를 만나면 몇 번까지 재시도하는가
* 연결이 끊기면 백오프가 어떻게 동작하는가
* timeout이 짧아 failover 순간에 요청이 폭발하지는 않는가

### 2) 단일 엔드포인트만 바라보는 client + 프록시/서비스 디스커버리

Sentinel 또는 별도 프록시(혹은 Kubernetes Service) 뒤에서 단일 엔드포인트만 쓰는 경우입니다.

이 경우 롤링 업그레이드의 리스크는 “드라이버 기능”보다 “전환 시점의 커넥션 처리”에 있습니다.

* keepalive / connection pool이 전환을 따라오는가
* DNS TTL과 캐시가 전환을 방해하지 않는가

### 3) Pub/Sub 소비자

Valkey 프로토콜 문서가 말하듯 Pub/Sub는 request-response가 아니라 push semantics로 바뀝니다.[^6]

롤링 업그레이드에서 Pub/Sub 소비자는 재연결 시점에 메시지 유실을 겪기 쉽습니다. Pub/Sub를 “이벤트 전달의 유일한 채널”로 써 온 팀은 롤링 자체가 기능적으로 위험할 수 있습니다.

내 블로그에서 Celery + Redis 기반의 비동기 워커 아키텍처를 여러 번 다뤘는데, 이런 계열의 시스템은 결국 “큐(데이터 구조) + 이벤트(상태 변화) + 레이스 컨디션”의 조합입니다. Pub/Sub를 어디에 쓰고 있는지(혹은 라이브러리가 몰래 쓰는지)를 모르면 롤링 사고가 납니다.

* [LLM 백엔드 “Queued Forever”를 끝내는 법: Celery + Redis 비동기 워커 아키텍처 심층 분석](https://daewooki.github.io/posts/llm-queued-forever-celery-redis-2026-4-1/)
* [LLM 요청을 “안전하게” 비동기화하기: Celery + Redis queue/worker 아키텍처 심층 분석](https://daewooki.github.io/posts/llm-celery-redis-queueworker-2026-6-1/)

## ACL·스크립팅·모듈: ‘임시 완화’와 ‘근본 해결(업그레이드)’를 분리한다

GHSA 권고문이 제시한 완화책은 두 가지입니다.

* ACL로 scripting 커맨드를 제한
* `proto-max-bulk-len`을 기본값 이상으로 올리지 않기[^3]

여기서 중요한 건, 이 완화책은 “업그레이드를 대체하지 못한다”는 점입니다. 다만 롤링 도중 취약 노드가 남아 있는 시간을 견디는 데 도움이 됩니다.

### 스크립팅을 끄는 게 가능한가: `@scripting` 카테고리로 확인

Valkey ACL 문서는 커맨드를 카테고리로 묶을 수 있고, `ACL CAT`로 카테고리 목록을 확인할 수 있다고 설명합니다.[^4]

실무에서는 다음 접근이 빠릅니다.

1) staging에서 애플리케이션 계정에서 `EVAL`, `FCALL`, `FUNCTION`을 호출하는지 로그를 잡습니다.
2) 실제로 호출하지 않는다면, production에서 해당 계정에 `-@scripting`을 적용합니다.

스크립팅을 끄면 이번 취약점의 공격 난이도가 크게 올라갑니다(권고문이 말한 4GiB+ payload 구성 자체가 막히기 때문).[^3]

### 모듈을 쓰는 팀: `PUBLISH` 경로가 ‘모듈 publish API’도 포함한다

권고문은 “module publish APIs도 영향”이 있다고 적습니다.[^3]

즉, 다음이 동시에 성립하면 위험합니다.

* 모듈이 (의도했든 아니든) publish를 수행
* 모듈이 서버 내부에서 큰 payload를 구성할 여지가 있음

모듈 워크로드가 있는 팀은 “업그레이드로 수정”이 답이고, ACL 완화는 보조 수단입니다.

추가로, Valkey는 `+@all`을 쓰면 모듈 커맨드까지 전부 열릴 수 있다고 ACL 문서가 경고합니다.[^4]  나는 이 패턴 자체를 운영 계정에는 거의 쓰지 않습니다.

## 백업·복구 관점의 체크: 9.0.7 롤링에서 실제로 해보는 리허설

보안 릴리스에서 자주 놓치는 게 “장애가 났을 때 되돌아오는 능력”입니다. 나는 다음 3가지를 최소 리허설로 잡습니다.

### 1) RDB/AOF 호환성 확인

Valkey는 Redis OSS 7.2 호환 RDB/AOF를 다룬다고 문서에 명시합니다.[^5]

팀이 Redis CE 7.4+ 계열(또는 관리형 서비스의 CE 기반)을 섞어 쓰는 순간, 복구 시나리오가 깨집니다. “지금은 Valkey인데 백업은 다른 곳에서 떴다” 같은 구성이면 더 위험합니다.

### 2) `RESTORE`를 쓰는 마이그레이션/복구 파이프라인이 있는지 확인

9.0.7은 `RESTORE` payload의 overflow 케이스를 reject하는 변경이 들어갔습니다.[^1]

정상 데이터라면 문제될 게 없지만, 운영에서는 종종 “부분 손상된 백업”이 떠돌고, 이전에는 운 좋게 복구되던 것이 이제는 실패할 수 있습니다. 이런 변화는 장애 상황에서만 드러납니다.

복구 리허설에서 `RESTORE` 기반 툴을 쓰는 팀은 9.0.7로 올린 뒤에도 동일한 데이터를 복구할 수 있는지 확인이 필요합니다.

### 3) multipart AOF 점검 자동화가 있는지 확인

9.0.7은 `valkey-check-aof`가 `VALKEY` signature를 인식하도록 바뀌었습니다.[^1]

운영 자동화가 `valkey-check-aof` 결과를 근거로 장애 알람을 쏘고 있다면, 릴리스 후 알람 패턴이 바뀔 수 있습니다. (좋은 쪽으로 바뀌는 경우가 많지만) 배포 윈도우에 같이 바뀌면 원인 추적이 어려워집니다.

## 실전 검증 스크립트: 롤링 전/중/후에 같은 커맨드를 같은 방식으로 때린다

아래는 내가 최소한으로 돌리는 “클러스터 롤링 안전성 점검” 스크립트입니다. 장난감 예제가 아니라, 실제 운영에서 깨지는 지점(MOVED/ASK, Pub/Sub, ACL, replication 상태)을 확인하는 데 초점을 맞췄습니다.

### 전제

* Python 3.12+
* `valkey`(valkey-py) 또는 기존 `redis` 계열 드라이버

Valkey는 RESP2/RESP3 모두 지원하고, 기존 Redis client 라이브러리가 Valkey에 붙을 수 있다고 문서가 설명합니다.[^5]

### 1) 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install valkey==6.1.0
```

버전은 예시입니다. 팀에서 고정한 드라이버 버전(그리고 실제로 운영에 배포된 버전)으로 돌리는 게 맞습니다.

### 2) 점검 코드

```python
# file: rolling_precheck.py
# usage: python rolling_precheck.py --seed 10.0.0.10:6379 --user app --password '***'

import argparse
import time
import sys

import valkey

def must(cond: bool, msg: str):
    if not cond:
        raise RuntimeError(msg)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", required=True, help="host:port")
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--ssl", action="store_true")
    args = p.parse_args()

    host, port_s = args.seed.split(":")
    port = int(port_s)

    # Cluster client: 롤링 중 MOVED/ASK 처리 품질이 핵심이므로 cluster=True를 고정.
    rc = valkey.ValkeyCluster(
        host=host,
        port=port,
        username=args.user,
        password=args.password,
        ssl=args.ssl,
        decode_responses=True,
        socket_timeout=1.0,
        socket_connect_timeout=1.0,
        health_check_interval=15,
        max_connections=64,
    )

    # 1) 기본 정보
    info = rc.info(section="server")
    print("server_name=", info.get("server_name"))
    print("valkey_version=", info.get("valkey_version"))
    print("redis_version=", info.get("redis_version"))

    # 2) cluster 상태
    cinfo = rc.execute_command("CLUSTER", "INFO")
    print("CLUSTER INFO\n", cinfo)
    must("cluster_state:ok" in cinfo, "cluster_state is not ok")

    # 3) write/read 경로 (slot 분산을 강제하기 위해 키 prefix를 바꿔가며 set/get)
    for i in range(50):
        k = f"rolling:probe:{i}:{time.time_ns()}"
        rc.set(k, "1", ex=60)
        v = rc.get(k)
        must(v == "1", f"read-after-write mismatch for key={k}")

    # 4) Pub/Sub: subscribe 연결이 재연결 시 깨지는지 확인
    #    (운영에서는 subscriber 프로세스를 별도 컨테이너/호스트에서 돌리는 게 더 낫습니다.)
    pubsub = rc.pubsub()
    ch = "rolling:probe:channel"
    pubsub.subscribe(ch)

    # 구독 설정이 반영될 시간을 조금 준 뒤 publish
    time.sleep(0.2)
    payload = f"hello-{time.time_ns()}"
    rc.publish(ch, payload)

    msg = pubsub.get_message(timeout=1.0)
    must(msg is not None, "no pubsub message")

    # valkey-py는 message type을 dict로 반환
    print("pubsub_message=", msg)

    # 5) scripting 권한이 열려 있는지 확인(운영 정책에 따라 PASS/FAIL 기준이 달라짐)
    #    - 만약 scripting을 금지할 계획이라면 여기서 실패해야 정상.
    try:
        rc.eval("return 1", 0)
        print("scripting=ENABLED")
    except Exception as e:
        print("scripting=DISABLED", repr(e))

    print("OK")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e, file=sys.stderr)
        sys.exit(2)
```

### 3) 실행

```bash
python rolling_precheck.py --seed 10.0.0.10:6379 --user app --password '***'
```

이 스크립트는 롤링 전 한 번만 돌리는 용도가 아닙니다.

* shard 하나 업그레이드 직후
* manual failover 직후
* 전체 롤링 종료 직후

같은 커맨드를 같은 방식으로 반복해서 때려야 “어디서부터 이상해졌는지”가 보입니다.

## 반론과 회의론: ‘4GiB 메시지면 현실적으로 불가능한 것 아닌가’에 대한 답

권고문 자체가 “기본 `proto-max-bulk-len` 512MB에서는 클라이언트가 직접 보내기 어렵다”고 적고 있습니다.[^3]

그래서 회의론이 나옵니다.

* 4GiB면 메모리도 엄청 필요한데 공격자가 굳이?
* authenticated user면 이미 뭘 많이 할 수 있지 않나?

여기에 대한 내 해석은 이렇습니다.

1) 보안 사고는 ‘가능성’이 아니라 ‘조합’에서 터집니다. 
   * 스크립팅이 열려 있고, Pub/Sub가 열려 있고, 클러스터 모드라면 “가능한 공격”이 됩니다.[^3]
2) authenticated user는 생각보다 쉽게 만들어집니다.
   * 공유 클러스터에서 ACL이 넓은 경우
   * 내부망에서 서비스 계정 토큰이 유출된 경우
3) crash만으로도 운영은 끝납니다.
   * RCE는 가능성이고, DoS는 확실성에 가깝습니다(권고문도 crash를 ‘reliably’라고 표현).[^3]

따라서 “우리 팀은 RCE까지는 아니지 않나”라고 판단하더라도, 클러스터 프로세스 crash가 가능한 시점에서 이미 우선순위는 높아집니다.

## 앞으로 지켜볼 것: 패치 버전 선택(9.0.7 vs 9.1.3)과 배포 압력

이번 GHSA는 여러 브랜치에 동시에 패치가 나갔습니다.

* 패치 버전: 9.0.7, 9.1.3, 8.1.11, 7.2.15 등[^3]
* 9.1.3 릴리스 노트도 동일 GHSA 수정과 SECURITY 긴급도를 명시합니다.[^11]

즉 “9.0.7으로 올릴 것인가, 9.1.3으로 올릴 것인가”가 팀별로 갈릴 수 있습니다.

나는 원칙적으로 다음을 따릅니다.

* 이미 9.1 계열을 운영 중이면 9.1.3으로 가는 편이 낫습니다(패치가 그 라인에 존재).[^3]
* 9.0 계열을 운영 중이고, 9.1로 올릴 때의 회귀 리스크가 크면 9.0.7으로 먼저 막고 다음 윈도우에 minor 업그레이드를 가져갑니다.

보안 릴리스의 목적은 기능 개선이 아니라 “공격 윈도우를 닫는 것”이므로, 현재 라인의 patched version으로 최소 이동하는 게 합리적입니다.

## 지금 할 수 있는 일: ‘롤링 체크리스트’ 형태로 정리

마지막으로 실제 실행 항목만 압축하면 아래입니다.

1) 영향 판정
   * cluster-enabled 여부 확인[^3]
   * Pub/Sub 사용 범위, sharded Pub/Sub(SPUBLISH) 사용 여부
   * scripting(EVAL/FCALL/FUNCTION) 노출 여부[^3]
2) 롤링 전 완화(가능한 경우)
   * 롤링 기간에 한해 `-@scripting` 또는 최소 권한으로 축소[^3]
   * `proto-max-bulk-len`이 기본값(512mb) 이상으로 올라가 있는지 점검[^3]
3) 롤링 전략 선택
   * Valkey Cluster는 shard 단위 롤링(Replica→Failover→구 Primary 업그레이드)[^7]
   * 보안 릴리스는 “부분 패치 기간”을 줄이도록 배포를 병렬화
4) 클라이언트 검증
   * MOVED/ASK 처리, 재연결, timeout, Pub/Sub 재구독을 롤링 중에 관측[^10]
5) 백업/복구 리허설
   * RDB/AOF 호환성, 복구 도구의 `RESTORE` 경로 확인[^5]

내 결론은 단순합니다. 클러스터 모드를 쓰는 순간 이번 건은 “언젠가 올리자”가 아니라 “언제까지 취약 노드를 남겨둘 수 있나”의 문제로 바뀌고, 그 답은 보통 이번 주 배포 윈도우 쪽으로 기웁니다.

## 참고 자료

- [Valkey 9.0.7 릴리스 노트](https://github.com/valkey-io/valkey/releases/tag/9.0.7)
- [GHSA-f4q9-j22m-xqq9 보안 권고문](https://github.com/valkey-io/valkey/security/advisories/GHSA-f4q9-j22m-xqq9)
- [Valkey 릴리스 목록(9.0.7 날짜 확인)](https://valkey.io/download/releases/)
- [Valkey Cluster tutorial: Manual failover와 롤링 업그레이드 절차](https://valkey.io/topics/cluster-tutorial/)
- [Valkey 마이그레이션 가이드: Redis 호환성과 파일 포맷/INFO/모듈](https://github.com/valkey-io/valkey-doc/blob/main/topics/migration.md)
- [Valkey 프로토콜 문서: RESP2/RESP3 및 Pub/Sub semantics](https://valkey.io/topics/protocol/)
- [Valkey ACL 문서: 카테고리와 @scripting](https://valkey.io/docs/topics/acl/)
- [valkey.conf의 proto-max-bulk-len 기본값(512mb) 설명(패키지 소스)](https://sources.debian.org/src/valkey/8.0.1%2Bdfsg1-1~bpo12%2B1/valkey.conf/)

[^1]: <https://github.com/valkey-io/valkey/releases/tag/9.0.7>
[^2]: <https://valkey.io/download/releases/>
[^3]: <https://github.com/valkey-io/valkey/security/advisories/GHSA-f4q9-j22m-xqq9>
[^4]: <https://valkey.io/docs/topics/acl/>
[^5]: <https://github.com/valkey-io/valkey-doc/blob/main/topics/migration.md>
[^6]: <https://valkey.io/topics/protocol/>
[^7]: <https://valkey.io/topics/cluster-tutorial/>
[^8]: <https://sources.debian.org/src/valkey/8.0.1%2Bdfsg1-1~bpo12%2B1/valkey.conf/>
[^9]: <https://valkey.io/clients/>
[^10]: <https://valkey.io/docs/topics/cluster-spec/>
[^11]: <https://github.com/valkey-io/valkey/releases/tag/9.1.3>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
