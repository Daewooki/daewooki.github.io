---
title: "Gitea v28: Git 네트워크 작업이 내부 프록시로 라우팅될 때 운영에서 깨지는 것들"
description: "Gitea v28.0.0의 Git egress 경로 변경은 방화벽·프록시·감사로그·성능까지 흔듭니다."
date: 2026-10-03 10:36:59 +0900
categories: ["News", "OpenSource"]
tags: ["gitea", "self-hosting", "egress", "proxy", "actions", "upgrade-checklist"]
render_with_liquid: false
---

## 2026-09-29~09-30에 실제로 바뀐 것: Git 네트워크 작업이 내부 프록시를 탄다

KST 기준 오늘은 2026-10-03입니다. Gitea는 v28.0.0을 2026-09-29(UTC) 무렵에 정리해 태그/배포했고, 릴리스 안내 글은 2026-09-30에 올라왔습니다.[^1][^2]

이번 글에서 중요한 변화는 한 줄로 정리됩니다.

- **migrations, mirrors 등 Gitea가 수행하는 Git 네트워크 작업이 내부 프록시(internal proxy)를 통해 나가도록 바뀌었습니다.** 이 내부 프록시는 egress 정책을 적용하고, (외부 프록시가 설정되어 있다면) 그쪽으로 체인 연결도 합니다.[^1][^3]

이게 왜 breaking change냐면, “Gitea 서버가 바깥으로 나가는 네트워크 경로”가 바뀌기 때문입니다. 웹 UI나 Git over SSH/HTTP로 들어오는 트래픽(ingress)은 기존 reverse proxy(Nginx/HAProxy/Ingress) 구성의 영향이 크고, 이번 변화는 기본적으로 egress 쪽을 때립니다. 

그런데 셀프호스팅 Git 서비스에서 egress는 보안만의 문제가 아닙니다.

- 방화벽/보안팀이 만든 outbound 정책(어느 호스트/포트로 나갈 수 있나)
- HTTP proxy, SOCKS proxy 강제 여부
- egress 관측(감사로그, NetFlow, 프록시 로그, eBPF 기반 로깅)
- 미러링/마이그레이션의 성능(대역폭, 연결 수, 타임아웃)

이 축들이 한 번에 연결되어 있어서, “Git 작업이 내부 프록시로 라우팅된다”는 문장이 운영에서는 꽤 큰 진동으로 들어옵니다.

## 배경: 왜 Gitea가 Git egress에 손을 대기 시작했나

Gitea는 예전부터 webhook, OAuth2 callback 등 서버가 외부로 나가는 기능에 대해 allowlist류 설정을 제공해 왔습니다. 다만 Git 자체의 네트워크 동작은 (특히 migration/mirror 영역에서) 구현상 Git CLI가 직접 네트워크를 만지는 경우가 많고, 그 경로는 정책 적용이 뒤늦게 따라붙기 쉽습니다.

Gitea v28.0.0에서 내부 프록시를 도입한 PR 설명에는, 이 프록시가 “git calls의 scanner로 동작하는 작은 forward proxy”라는 문장이 들어갑니다.[^3]

이 변화는 기능 추가라기보다, Git CLI를 호출하는 경로를 SSRF 같은 클래스의 문제에서 더 안전하게 만들고, 설정을 통합된 egress 정책으로 수렴시키려는 성격이 강합니다. PR 커밋 메시지에도 “raw git calls를 SSRF vector로 만들지 않기 위해 git proxy를 추가한다”는 표현이 직접적으로 등장합니다.[^3]

실제로 2026년에 올라온 Gitea 보안 권고 중에는, migration URL 검증을 통과시킨 뒤 Git이 HTTP redirect를 따라가면서 최종 목적지가 정책 검증 밖으로 빠져나갈 수 있다는 류의 문제가 언급됩니다. 이런 건 결국 “검증은 애플리케이션이 했는데, 실제 네트워크는 다른 구성 요소가 했다”의 전형적인 균열입니다.[^4]

내 경우 운영에서 이런 케이스가 가장 무섭습니다.

- 설정은 했다고 믿고 있었는데(allowlist), 실제 데이터 경로는 그 설정을 우회했다.
- 그 우회가 내부망(메타데이터 서비스, loopback, RFC1918 등)으로 연결되면 사고가 된다.

v28의 내부 프록시 도입은 이런 우회를 줄이기 위한 방향으로 읽힙니다. 대신 운영자는 “정책을 어디에 걸어야 하는지”를 다시 정의해야 합니다.

## egress 설정의 의미가 바뀐다: lax/strict, allowlist 문법, deprecated 설정 정리

v28.0.0의 breaking changes에는 egress 설정의 의미 변화가 여러 개 묶여 있습니다. 릴리스 안내 글에 핵심이 잘 정리되어 있습니다.[^1]

### `external` preset 제거: deny-by-default는 `strict`로 간다

릴리스 노트에서 가장 눈에 띄는 문장은 이겁니다.

- `external` preset이 제거되었습니다.
- deny-by-default를 원하면 `EGRESS_MODE = strict`를 쓰고 allowed list를 명시해야 합니다.
- `[migrations] EGRESS_MODE`는 migrations/mirrors를, `[security] EGRESS_MODE`는 webhooks/OAuth2를 다룹니다.[^1]

여기서 포인트는, egress를 “어떤 기능이 어떤 리스트를 적용받는가”로 분리해서 생각해야 한다는 겁니다.

- mirror sync가 막혔는데 security 쪽만 보고 있으면 답이 안 나옵니다.
- webhook이 특정 사내 도메인으로 못 나가는데 migrations allowlist만 조정하면 의미가 없습니다.

운영 체크리스트에선, 기능별로 egress 정책 적용 범위를 분리해서 적어두는 게 사고를 줄입니다.

### strict 모드에서 포트 생략 시 80/443만 허용

strict 모드에서는 “포트를 안 쓰면 기본 포트만 허용”이라는 룰이 추가로 들어갑니다. 릴리스 노트에선 80/443만 허용한다고 명시합니다.[^1]

이건 미러링 운영에서 실제로 자주 밟습니다.

- 내부 Git 미러가 8443, 10443 같은 비표준 포트를 쓰는 경우
- 온프레미스 아티팩트/패키지 서버가 프록시 뒤에 있고 포트를 다르게 노출하는 경우

이때는 “도메인을 allowlist에 넣었는데도 안 된다”라는 현상으로 나타날 가능성이 큽니다. 이제는 포트를 명시해야 합니다.

### lax 모드의 의미 변화: `[security] ALLOWED_HOST_LIST`가 공인(public) 호스트를 더 이상 제한하지 않는다

릴리스 노트의 세 번째 bullet이 운영자를 가장 헷갈리게 할 부분입니다.

- 기본값인 `lax` 모드에서는 `[security] ALLOWED_HOST_LIST`가 더 이상 public host를 제한하지 않습니다.
- 예전처럼 exclusive allowlist로 쓰고 싶으면 `[security] EGRESS_MODE = strict`로 바꿔야 합니다.
- 리스트만 설정하고 `EGRESS_MODE`를 명시하지 않으면 startup warning이 찍힙니다.[^1][^3]

이건 보안 관점에서도 크지만, 네트워크 비용/정책 관점에서도 큽니다.

- 나는 `[security] ALLOWED_HOST_LIST`로 webhook egress를 제한하고 있다고 생각했는데
- 사실은 공인 IP 대역 전체로는 여전히 나가고 있을 수 있습니다(lax).

반대로, public 쪽은 그냥 두고 사설망/loopback만 막는 게 목적이었다면 lax가 더 맞을 수도 있습니다. 문제는 업그레이드 전의 운영 의도가 무엇이었는지 문서로 남아 있어야 한다는 점입니다.

### wildcard/문법 변화: IP wildcard 금지, `*` 엔트리 금지, 도메인 매칭 룰은 curl 스타일

릴리스 노트에는 allow/block 리스트 문법 변화가 구체적으로 나옵니다.

- IP 주소 엔트리는 wildcard를 더 이상 허용하지 않습니다.
- `*` 자체가 더 이상 유효한 엔트리가 아닙니다.
- 도메인 엔트리는 curl 문법을 따릅니다: `example.com`은 도메인과 모든 서브도메인 매칭, `*.example.com`은 서브도메인만 매칭(루트 도메인 제외), `example.*`은 invalid.[^1][^3]

실무에서는 allowlist를 급하게 만들면서 `*`를 넣어 “일단 통과” 시켜두는 경우가 있습니다. v28에서는 그 방식이 더 위험해졌습니다. 

- 이전: 실수로 wide open이 되더라도 서비스는 올라왔다.
- v28: 일부 invalid 엔트리는 아예 부팅 실패 요인이 됩니다(특히 migrations의 blocked list).[^1]

운영에서 가장 돈이 많이 드는 장애는 “업그레이드 했더니 특정 기능이 안 됨”이 아니라 “업그레이드 했더니 프로세스가 안 올라옴”입니다.

### migrations 설정 정리: `ALLOWED_DOMAINS/BLOCKED_DOMAINS/ALLOW_LOCALNETWORKS` deprecated

릴리스 노트에선 migrations 쪽 오래된 설정들이 deprecated 처리되었다고 명시합니다.[^1]

- `[migrations] ALLOWED_DOMAINS`, `BLOCKED_DOMAINS`, `ALLOW_LOCALNETWORKS`는 deprecated
- 대신 `[migrations] ALLOWED_HOST_LIST`, `BLOCKED_HOST_LIST`

여기서 중요한 건 “이제 host+port 규칙까지 포함하는 쪽으로 모델이 정리된다”는 흐름입니다. PR도 hostmatcher를 matchlist로 바꿔 port rule을 지원한다고 적고 있습니다.[^3]

운영 문서/설정 템플릿에도 이 변화를 반영해야 합니다. 도메인만 써두면 충분했던 시대가 지나고 있습니다.

## 방화벽/프록시/미러링 구성에 주는 영향: 경로가 바뀌면 관측과 책임도 바뀐다

내부 프록시가 들어오면, “Git이 어디로 연결하느냐”는 질문이 두 층으로 갈립니다.

1) Git CLI는 내부 프록시(로컬 리스너)로 연결한다.
2) 내부 프록시가 실제 목적지로 dial-out 한다(여기서 egress 정책 적용)

이 구조는 보안적으로는 좋은데, 운영 관점에서는 다음이 흔들립니다.

### 1) 방화벽 룰과 egress allowlist의 기준점

기존에는 이런 식으로 단순화해서 설명하기 쉬웠습니다.

- Gitea 서버(또는 Pod/컨테이너)가 GitHub로 443 나간다.

v28 이후에도 “결국은 나간다”는 사실은 같지만, 어떤 코드가 어떤 설정을 적용하며 나가는지 경계가 바뀝니다.

- 예전: git이 나감(프로세스/라이브러리 주체가 git/libcurl 쪽)
- 지금: git은 프록시로만 나가고, 프록시가 정책을 적용해 나감(주체가 Gitea 내부 모듈로 이동)[^3]

이 변화는 “네트워크 계층에서 차이가 없다”고 말할 수도 있지만, 감사/로깅 관점에서는 차이가 생깁니다.

- 프록시 서버에서 보는 User-Agent, CONNECT 패턴, DNS 조회 패턴이 바뀔 수 있습니다(여기서는 바뀔 가능성이 있다는 수준까지만 말할 수 있습니다. Gitea가 내부 프록시에서 어떤 transport를 쓰는지에 따라 달라집니다).
- egress 정책이 애플리케이션 레벨에서 더 많이 적용되면, 방화벽은 deny-by-default를 더 강하게 가져가도 됩니다. 대신 설정 실수는 곧 기능 장애로 이어집니다.

운영 결론은 단순합니다.

- 네트워크 팀이 관리하는 egress 정책(방화벽/프록시)과, Gitea 설정의 egress 정책(`[security]`, `[migrations]`)이 중복/충돌하지 않게 역할을 다시 나눠야 합니다.

### 2) HTTP proxy를 쓰는 환경에서의 함정: “프록시가 있으면 egress list를 프록시 타깃에 적용하지 않는다”

Gitea 문서의 config cheat sheet에는 매우 직접적인 문장이 있습니다.

- proxy가 설정되어 있으면 Gitea는 egress list(`[security]`, `[migrations]`)를 proxied target에 강제하지 않고, proxy 서버가 제한을 맡아야 한다.[^5]

이 말은, “애플리케이션 allowlist로 안전을 확보한다”는 설계를 기대하면 안 된다는 뜻입니다. 프록시를 쓰는 순간, 애플리케이션은 최종 목적지 제한을 포기합니다.

이게 나쁜 설계라기보다 현실적인 타협입니다.

- forward proxy를 쓰는 조직에서는 최종 목적지 제어는 proxy 정책(PAC, ACL, URL filtering, SNI filtering)로 하는 게 정석입니다.
- 애플리케이션이 프록시 이후의 목적지까지 완전히 검증하려면, CONNECT/절대경로 요청을 해석하고 TLS 내부까지 들여다봐야 하는데, 그건 애플리케이션 책임으로 가져가기 어렵습니다.

하지만 셀프호스팅 Git 서비스는 종종 “프록시는 단순히 인터넷 나가기 위한 문” 정도로만 운영되는 경우도 있습니다. 그런 환경에서는 이 문장 하나가 보안 모델을 바꿉니다.

- 프록시를 켠 순간, Gitea의 allowlist는 생각보다 덜 의미가 있을 수 있다.

따라서 v28 업그레이드 타이밍에는, 프록시 운영 성숙도가 낮다면 차라리 Gitea 쪽 `strict`만으로 풀려는 유혹이 생길 텐데, 문서/조직 구조상 어느 쪽이 책임을 가져가는지 명확히 해야 합니다.

### 3) 미러링/마이그레이션은 “성공/실패”가 아니라 “어느 경로로 나갔는가”를 검증해야 한다

migrations/mirrors는 v28에서 직접 언급됩니다.[^1]

이 둘은 운영에서 다음 특성이 있습니다.

- 트래픽이 크다(대형 monorepo, LFS 포함 시 더 큼)
- 평소에는 안 돌다가, 누군가 신규 마이그레이션을 할 때만 튄다
- 장애가 “지금 당장” 드러나지 않는다(야간 미러 sync 실패, 주간에 발견)

그래서 업그레이드 전후에는 성공 여부만 보지 말고, 경로를 검증해야 합니다.

- 방화벽 로그에서 목적지/포트가 정책대로만 나가는가
- 프록시를 쓰면 프록시 로그에 해당 트래픽이 찍히는가
- Gitea 로그에서 egress 관련 warning/deny가 생기는가(릴리스 노트에 startup warning이 언급됩니다)[^1]

## Actions/runner 네트워크: Gitea 서버의 egress와 runner의 egress는 별개로 봐야 한다

이번 breaking change는 “Gitea 서버가 수행하는 Git 네트워크 작업”을 다룹니다. Actions의 실제 네트워크 고통은 보통 runner 쪽에서 발생합니다.

- runner는 workflow를 실행하면서 action을 다운로드하고(`uses:`), repo checkout을 하고, container build를 하면서 외부로 나갑니다.
- 이때 proxy/no_proxy 처리가 runner 환경과 job container 환경에 걸쳐서 복잡해집니다.

Gitea runner 문서에는 proxy 설정을 환경 변수 형태로 안내하고, 특히 Dockerfile action 빌드 단계에 build-arg로 전달된다는 점까지 언급합니다.[^6]

즉, v28 업그레이드 주간에 자주 터지는 패턴은 이런 조합입니다.

- 서버는 egress 정책이 바뀌어서 migration/mirror가 실패한다.
- runner는 원래도 proxy/no_proxy가 불안정해서 `actions/checkout`이 실패한다.

둘은 원인이 다르지만, 체감상 “업그레이드 했더니 Git이 안 된다”로 뭉개져서 들어옵니다. 업그레이드 검증 체크리스트에서 경로를 분리해야 합니다.

### 덤으로 같이 들어온 breaking change: Actions run retention 기본 만료

v28 릴리스 노트에는 Actions run retention 동작 변경도 breaking change로 올라와 있습니다.

- 완료된 Actions run이 기본 400일 후 삭제
- `cleanup_action_runs` cron이 기본적으로 자정에 동작
- 영구 보존하려면 `[actions] RUN_RETENTION_DAYS = 0`을 업그레이드 전에 설정
- 그리고 `RUN_RETENTION_DAYS`, `LOG_RETENTION_DAYS`, `ARTIFACT_RETENTION_DAYS`에서 `0`의 의미가 “keep forever”로 바뀜[^1]

네트워크 글에서 retention을 왜 끌고 오냐면, 업그레이드 주말에 운영팀이 제일 많이 하는 일이 “문제 생기면 로그로 본다”이기 때문입니다.

- 업그레이드 직후 runner가 네트워크 문제로 실패
- 근데 retention 정책이 바뀌면서 예전과 동일한 방식으로 로그/아티팩트가 남는다고 가정하면 곤란해집니다

이건 보안/감사 관점에서도 마찬가지입니다. run 삭제는 감사 추적을 약하게 만들 수 있으니, 정책을 정하고 명시적으로 설정해 두는 편이 안전합니다.

## 업그레이드 전후 검증 체크리스트: clone/push부터 mirror/migration/LFS까지

여기서는 “v28 내부 프록시로 인해 깨질 수 있는 것”을 중심으로 적습니다. 다만 업그레이드 윈도우에서 사람들은 Git의 모든 경로를 한 번에 때리기 때문에, ingress(클론/푸시) 쪽도 최소 검증 세트에 포함합니다.

아래 시나리오는 staging에서 먼저 돌리고, production에선 canary org/repo로 축소해서 다시 돌리는 구성을 전제로 합니다. 업그레이드 운영 프로세스 자체는 예전에 정리한 글들과 방향성이 같습니다.[^7][^8][^9][^10]

### A. 업그레이드 전에 먼저 해야 하는 설정/환경 점검

1) Git 최소 버전

v28은 Git 2.25 미만이면 시작 자체를 거부합니다. 업그레이드 전에 서버/이미지에서 확인해야 합니다.[^1]

- systemd 서비스라면: Gitea가 실제로 참조하는 PATH에서 `git --version`
- 컨테이너라면: 실행 이미지 안에서 `git --version`

2) egress 정책 의도를 명문화

- webhook/OAuth2 egress를 막고 싶은가, 사설망만 막고 싶은가
- migrations/mirror egress를 어디까지 허용할 것인가
- HTTP proxy를 사용 중인가(사용한다면 allowlist 책임이 어디에 있는가)

3) allow/block list 문법에 wildcard/`*`/port 생략이 섞여 있는지 정리

릴리스 노트에서 문법 변경이 직접 언급됩니다.[^1]

- IP wildcard 제거
- `*` 엔트리 제거
- 도메인 매칭은 curl 스타일로 재검토
- strict 모드에서 비표준 포트는 반드시 명시

4) migrations의 deprecated 설정 제거 계획

- `ALLOWED_DOMAINS/BLOCKED_DOMAINS/ALLOW_LOCALNETWORKS`에서 `ALLOWED_HOST_LIST/BLOCKED_HOST_LIST`로 옮깁니다.[^1]

바로 치환하면 되는 수준이 아니라, “도메인 단위로만 관리하던 정책을 host:port 정책으로 내리느냐”를 선택해야 할 수 있습니다.

### B. v28 업그레이드 후 즉시 확인: 부팅/경고/정책 적용

1) Gitea가 정상 부팅되는지

- 특히 `[migrations] BLOCKED_HOST_LIST`에 invalid가 있으면 부팅이 막힐 수 있다고 릴리스 노트에 적혀 있습니다.[^1]

2) startup warning 유무

- `[security] ALLOWED_HOST_LIST`를 설정해 두고 `EGRESS_MODE`를 명시하지 않으면 경고가 찍힌다고 되어 있습니다.[^1][^3]

경고가 있다는 건 “운영자가 의도한 정책이 아닐 수 있다”는 신호이므로, 넘어가면 결국 사고가 납니다.

### C. Git ingress(클론/푸시) 검증: 내부 프록시 변경의 직접 대상은 아니지만, 업그레이드 윈도우에서 같이 깨진다

아래는 v28 내부 프록시 변경과 직접 연관이 약할 수 있습니다. 그래도 실제 운영에서 Git 서비스 업그레이드 후 고객이 체감하는 1순위는 ingress 성공 여부입니다.

#### 1) HTTPS clone/push

```bash
# client machine
export GITEA_URL="https://git.example.com"
export REPO="test-org/net-path-check"

git clone "${GITEA_URL}/${REPO}.git"
cd net-path-check

echo "upgrade-$(date -u +%Y%m%dT%H%M%SZ)" >> upgrade.txt
git add upgrade.txt
git commit -m "upgrade check"
git push origin HEAD:refs/heads/upgrade-check
```

- 예상: clone/push 성공
- 확인: reverse proxy access log, Gitea access log에 200/302 흐름이 정상

#### 2) SSH clone/push

```bash
# client machine
export REPO_SSH="git@git.example.com:test-org/net-path-check.git"

git clone "$REPO_SSH" net-path-check-ssh
cd net-path-check-ssh

echo "ssh-upgrade" >> upgrade.txt
git add upgrade.txt
git commit -m "ssh upgrade check"
git push origin HEAD:refs/heads/ssh-upgrade-check
```

- 예상: clone/push 성공
- 확인: SSH 로그(내장 SSH server 사용 여부에 따라 위치가 다름), 인증 방식(OAuth2/Deploy token) 변화 없음

### D. migrations/mirrors 검증: 내부 프록시 변경의 정중앙

이 파트가 v28에서 깨지면, 대개 현상은 “migration이 갑자기 안 된다”, “mirror sync가 계속 실패한다”로 옵니다.

#### 1) migration: 허용된 외부 Git 서버에서 import

- 사전에 `[migrations] EGRESS_MODE`와 allowlist가 의도대로 구성되어 있어야 합니다. 릴리스 노트에서 migrations/mirrors가 `[migrations]`에 의해 제어된다고 명시합니다.[^1]

검증은 UI로만 하면 재현성이 떨어져서, 운영 환경에선 최소한 대상 URL/프로토콜을 기록으로 남겨야 합니다.

- HTTPS Git remote 1개
- SSH Git remote 1개(가능하면)
- 비표준 포트를 쓰는 remote 1개(8443 등)

strict 모드에서 포트 생략은 80/443만 허용된다고 되어 있으니, 비표준 포트 migration은 여기서 바로 잡힙니다.[^1]

#### 2) mirror pull: 허용된 host로는 되고, 차단된 host로는 실패해야 한다

운영에서 중요한 건 “성공만 확인”이 아니라 “차단이 실제로 차단되는지”까지 확인하는 것입니다. 내부 프록시 도입 목적이 정책 적용 강화 쪽에 있기 때문에, 차단 검증이 빠지면 의미가 절반만 남습니다.[^3]

- allowlist에 넣은 호스트로 mirror pull 성공
- blocked list에 넣은 호스트로 mirror pull 실패
- public host에 대한 behavior는 lax/strict에 따라 달라질 수 있으므로, 업그레이드 전 의도와 동일한지 확인

#### 3) redirect/프록시 환경에서의 추가 확인

migration/mirror 쪽은 redirect를 따라가면서 정책을 우회할 수 있는 종류의 이슈가 이미 문제로 지적된 바 있습니다.[^4]

업그레이드 직후에는 최소한 다음을 남깁니다.

- migration/mirror이 사용하는 remote URL 목록
- 해당 URL의 DNS 결과(업그레이드 시점)
- 프록시를 타는지 여부(프록시 로그 상에서 확인)

“정책은 설정 파일에 있고, 실제 트래픽은 다른 데 찍힌다”는 상태가 제일 위험합니다.

### E. Submodule/LFS 검증: 경로가 여러 개라서 사고가 자주 난다

내부 프록시 변화는 서버의 Git 네트워크 작업 경로를 바꾸는 것이고, submodule/LFS는 조직마다 경로가 달라서 업그레이드 때 같이 터지기 쉽습니다.

#### 1) submodule 포함 repo clone

```bash
# client machine
export GITEA_URL="https://git.example.com"

git clone "${GITEA_URL}/test-org/parent-with-submodule.git"
cd parent-with-submodule

git submodule update --init --recursive
```

- 확인: submodule URL이 내부/외부 도메인 어느 쪽을 가리키는지
- 확인: reverse proxy/인증이 필요한 submodule에서 자격 증명 처리가 정상인지

이건 v28 내부 프록시 변경과 직접 연계가 약할 수 있지만, 업그레이드 주말에 제일 많이 깨지는 영역 중 하나입니다.

#### 2) Git LFS push/pull

Gitea는 LFS를 별도 endpoint로 제공하고, LFS는 Git과 다른 HTTP 흐름을 가집니다. LFS 자체는 v28 내부 프록시 변경의 직접 대상이라고 단정할 수는 없지만(릴리스 노트가 그렇게 말하진 않습니다), 업그레이드 검증 범위에서 빼면 안 됩니다.

```bash
# client machine
git lfs install

dd if=/dev/urandom of=large.bin bs=1M count=32

git add .gitattributes large.bin
# .gitattributes에는 예를 들어 "*.bin filter=lfs diff=lfs merge=lfs -text" 같은 규칙이 있어야 합니다.

git commit -m "lfs check"
git push origin HEAD

git lfs fetch --all
```

- 확인: reverse proxy에서 큰 payload 처리(client_max_body_size 등)
- 확인: LFS storage backend(로컬/오브젝트 스토리지) 접근 정상

### F. Webhook/OAuth2 egress 검증: `[security]` 정책 변화 확인

릴리스 노트에서 `[security] EGRESS_MODE`는 webhooks/OAuth2를 커버한다고 분명히 적습니다.[^1]

테스트는 이렇게 나눕니다.

- allowlist된 webhook endpoint로는 delivery 성공
- 차단된(또는 private/loopback) endpoint로는 실패

그리고 proxy를 쓰는 환경이면 더 중요해집니다.

- proxy가 설정되면, Gitea는 proxied target에 대해 egress allowlist를 강제하지 않는다는 문서가 있습니다.[^5]

이 경우에는 Gitea 설정이 아니라 프록시 정책으로 차단 검증을 해야 합니다.

### G. Actions/runner 네트워크 체크: proxy/no_proxy와 내부 도메인 접근

runner의 proxy 설정은 runner 문서에 정리되어 있습니다.[^6]

업그레이드 전후로는 다음을 확인합니다.

- runner가 Gitea에 붙는 경로가 internal URL인지 external URL인지(특히 Docker network/host network 구성)
- job container가 action 다운로드/checkout 시 외부로 나갈 때 proxy가 적용되는지
- `no_proxy`에 Gitea 내부 도메인/클러스터 도메인이 포함되어 있는지(문서 예시에도 `no_proxy=gitea.internal,.example.local` 같은 형태가 나옵니다)[^6]

그리고 retention breaking change 때문에, 장애 분석에 필요한 로그/아티팩트가 400일 보존된다고 막연히 기대하면 안 됩니다. 운영 정책대로 `[actions] RUN_RETENTION_DAYS`를 명시하는 쪽이 맞습니다.[^1]

## 회의론과 반론: 내부 프록시는 결국 복잡도를 올린다

이 변화에 대해 운영 관점에서 나올 수 있는 반응은 크게 두 가지입니다.

### “어차피 방화벽에서 막는데, 앱 레벨 프록시/정책이 왜 필요한가?”

방화벽/프록시는 최종 방어선이고, 조직 성숙도가 높을수록 네트워크 레벨 통제가 강합니다. 그 관점에서는 “애플리케이션이 egress 정책을 가지는 것”이 중복처럼 보일 수 있습니다.

다만 migration/mirror/webhook/OAuth2 같은 기능은 팀 단위로 빠르게 켜졌다 꺼지고, 방화벽 변경은 느립니다. 애플리케이션 정책은 속도를 얻는 대신, 설정 실수가 곧 장애가 됩니다.

v28은 이 두 세계를 강하게 묶었습니다.

- Git 네트워크 작업 자체를 내부 프록시로 통일해 정책 적용을 강화한다.[^1]

운영 결론은 “어느 쪽이든 책임을 명확히 하라”입니다. 이중화는 안전을 주지 않고, 보통은 혼선을 줍니다.

### “프록시 체인이 생기면 성능/디버깅이 나빠진다”

이건 현실적인 걱정입니다.

- 내부 프록시가 들어가면 hop이 늘고, 타임아웃/재시도/커넥션 풀링 동작이 바뀔 수 있습니다.
- 장애 시점에 봐야 할 로그가 늘어납니다(Gitea 로그 + 프록시 로그 + 방화벽 로그).

나는 이 걱정을 반박하지 않습니다. 다만 Git 서비스 운영에서 “보안 경계가 애매한 상태”는 언젠가 사고로 비용을 치르게 됩니다. v28의 방향성은 그 경계를 좀 더 코드 안으로 끌어들이는 쪽입니다.[^3]

## 앞으로 지켜볼 것: v28 보안 상세 공개, 그리고 egress 정책의 실제 운영 사례

릴리스 안내 글에는 “이번 릴리스에는 보안 수정이 포함되어 있고, 업그레이드 시간을 주기 위해 상세는 약 1주 뒤에 추가한다”는 문장이 들어 있습니다.[^1]

내부 프록시/egress 정책 변경이 보안 수정과 같은 묶음으로 움직인다는 건, 이 변화가 단순한 리팩터링이 아니라는 의미로 해석됩니다.

운영 측면에서 앞으로 확인할 포인트는 다음입니다.

- 내부 프록시가 어떤 요청/프로토콜을 어디까지 커버하는가(“other Git network operations”의 범위)
- proxy가 설정된 경우 egress list의 역할을 어떻게 가져가는 게 권장되는가(문서에는 proxy가 있으면 list를 강제하지 않는다고 되어 있음)[^5]
- strict 모드 전환 시, 기존 운영에서 묵시적으로 사용하던 비표준 포트/내부 도메인이 얼마나 있는가

## 지금 당장 할 수 있는 정리: v28 업그레이드 주말에 실패를 줄이는 방법

1) `[migrations]`와 `[security]` egress 정책을 분리해서 문서화합니다. 릴리스 노트가 커버 범위를 정확히 나눠 말하고 있습니다.[^1]

2) `lax`에서 allowlist가 public host를 더 이상 제한하지 않는다는 점을 운영 문서에 박아둡니다. 기존 설정의 의도와 다르면 `strict`로 옮겨야 합니다.[^1][^3]

3) allow/block 리스트에서 `*`, IP wildcard, 도메인 매칭 문법을 전수 점검합니다. 업그레이드 후에 발견하면 대개 부팅/기능 장애로 옵니다.[^1]

4) HTTP proxy를 쓰는 환경이면, egress list로 최종 목적지를 제어할 수 있다고 착각하지 않습니다. 문서에 proxy가 있으면 egress list를 proxied target에 강제하지 않는다고 명시되어 있습니다.[^5]

5) Actions는 서버가 아니라 runner가 네트워크 문제의 중심입니다. runner의 proxy/no_proxy를 별도 체크리스트로 떼어내고, retention breaking change도 함께 반영합니다.[^6][^1]

내 경우 v28의 내부 프록시 도입은 “보안 강화를 위해 운영을 더 엄격하게 만든다” 쪽으로 읽히고, 그래서 업그레이드 주말의 관건은 기능 테스트가 아니라 egress 책임 분리(앱 vs 프록시 vs 방화벽)를 다시 합의하는 데 있다고 판단했습니다.

## 참고 자료

- [Gitea 28.0.0 릴리스 안내](https://blog.gitea.com/release-of-28.0.0/)
- [GitHub 릴리스 v28.0.0](https://github.com/go-gitea/gitea/releases/tag/v28.0.0)
- [PR #39426: fix(git)!: use internal proxy for all git operations](https://github.com/go-gitea/gitea/pull/39426)
- [Gitea Configuration Cheat Sheet](https://docs.gitea.com/administration/config-cheat-sheet/)
- [Gitea Runner proxy 문서](https://docs.gitea.com/runner/proxy/)
- [GitHub Advisory GHSA-82f7-87hm-852x](https://github.com/advisories/GHSA-82f7-87hm-852x)

[^1]: <https://blog.gitea.com/release-of-28.0.0/>
[^2]: <https://github.com/go-gitea/gitea/releases/tag/v28.0.0>
[^3]: <https://github.com/go-gitea/gitea/pull/39426>
[^4]: <https://github.com/advisories/GHSA-82f7-87hm-852x>
[^5]: <https://docs.gitea.com/administration/config-cheat-sheet/>
[^6]: <https://docs.gitea.com/runner/proxy/>
[^7]: <https://daewooki.github.io/posts/discourse-monthly-release-selfhost-upgrade-automation/>
[^8]: <https://daewooki.github.io/posts/grafana-patch-upgrade-automation/>
[^9]: <https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/>
[^10]: <https://daewooki.github.io/posts/etcd-372-kubernetes-ops-rehearsal/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
