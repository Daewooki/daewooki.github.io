---
title: "GitHub SSH에서 ssh-rsa(SHA-1) 차단이 남기는 운영 과제"
description: "ssh-rsa 차단은 키 타입 교체만으로 끝나지 않습니다. org 전체에서 SSH 키·클라이언트·자동화 경로를 자산화하고 교체·검증하는 런북이 필요합니다."
date: 2026-09-29 11:21:37 +0900
categories: ["News", "Security"]
tags: ["ssh-rsa", "rsa-sha2", "deploy-keys", "key-rotation", "github-actions", "git-automation"]
render_with_liquid: false
---

GitHub가 2026-09-22에 SSH 보안 강화를 발표하면서, RSA에서 SHA-1을 쓰는 `ssh-rsa` 서명 타입을 제거(차단)하는 일정을 명확히 걸었습니다. 동시에 `diffie-hellman-group-exchange-sha256` KEX 제거, 신규 업로드 RSA 키 최소 3072-bit 요구, 그리고 `mlkem768x25519-sha256`(post-quantum KEX) 지원까지 한 번에 묶였습니다. 발표 자체보다 위험한 지점은, 많은 조직에서 이 변화가 **어느 날 갑자기 `git pull/push`가 실패**하는 형태로 터진다는 점입니다.[^1]

이번 변경의 핵심 일정은 다음과 같습니다.

- 2026-10-14: 신규로 업로드되는 RSA SSH 키는 최소 3072-bit 이상이어야 함
- 2026-11-04: `ssh-rsa`(RSA+SHA-1) 서명 타입과 `diffie-hellman-group-exchange-sha256`에 대해 brownout
- 2026-12-09: 동일 대상 brownout 2차
- 2027-01-13: `ssh-rsa`(RSA+SHA-1) 서명 타입과 `diffie-hellman-group-exchange-sha256` 완전 제거[^1]

문제는 “키 타입을 ed25519로 바꾸세요”로 끝나지 않습니다. 키를 바꿀 사람이 한두 명이면 단순한 작업이지만, org 단위 운영에서는 다음이 동시에 얽힙니다.

- 사람의 개인키(노트북/데스크톱)
- repo 단위 Deploy key
- 머신 유저(봇 계정)의 키
- CI 컨테이너 이미지/빌드 에이전트에 박힌 키
- 서브모듈/배포 서버/레거시 Git 클라이언트(또는 SSH 라이브러리)

결국 이건 “암호 알고리즘 변경 공지”가 아니라 “자산화 → 교체 → 검증 → 사고 대비” 운영 플랜 문제입니다.

## 이번 공지에서 헷갈리기 쉬운 부분: key type과 signature type은 다릅니다
GitHub 공지에서 가장 중요한 문장이 하나 있습니다. 기존 RSA 키를 쓰는 사람에게 “새 키를 반드시 만들 필요는 없다”는 내용입니다.

- GitHub가 제거하는 것은 RSA 키 자체가 아니라, RSA로 SHA-1 해시를 써서 서명하는 **signature type** `ssh-rsa`입니다.
- 같은 RSA 개인키라도, 클라이언트가 `rsa-sha2-256`/`rsa-sha2-512`로 서명하면 계속 동작할 수 있습니다.
- 문제는 “내가 쓰는 SSH 클라이언트/라이브러리가 RSA SHA-2 서명을 기본으로 선택할 수 있느냐”입니다.[^1]

RFC 관점에서 RSA SHA-2 서명 알고리즘(`rsa-sha2-256`, `rsa-sha2-512`)은 이미 표준화되어 있습니다(RFC 8332).[^2]

운영에서 이 구분이 중요한 이유는 단순합니다.

- 어떤 팀은 “RSA 키가 있으니 괜찮다”고 생각하지만, 실제로는 빌드 에이전트의 libssh2가 낡아서 SHA-2 RSA 서명 자체를 못 합니다.
- 반대로 어떤 팀은 “RSA 키를 다 ed25519로 바꾸자”고 밀어붙이지만, 규제/호환성(FIPS 정책, 특정 장비/라이브러리 제약) 때문에 ed25519를 못 쓰는 곳이 남습니다.

따라서 키를 갈아엎는 접근과 클라이언트를 업그레이드하는 접근을 분리해야 합니다.

## 실제 장애는 어디서 터지나: 사람보다 자동화가 먼저 깨집니다
사람의 개발 환경은 최신 OS 업데이트와 함께 OpenSSH 버전이 같이 올라가는 경우가 많아서, 이미 RSA SHA-2를 사용 중일 확률이 큽니다. 반면 자동화는 반대입니다.

- 오래된 Docker 이미지(예: 수년간 고정된 CI 이미지)
- 사내 Jenkins/TeamCity 에이전트의 내장 SSH 라이브러리
- 배포 서버의 `git`/`ssh`가 OS 업그레이드에서 제외됨
- 레거시 JSch/libssh2 기반 툴(내장 업그레이드가 어렵거나, 업그레이드가 제품 업데이트에 묶임)

GitHub는 영향을 받는 소프트웨어의 “RSA with SHA-2를 기본 구성으로 robust하게 지원하는 최소 버전”을 명시했습니다.

- OpenSSH: 7.2p1
- JSch: 특정 fork의 0.1.66
- TeamCity: 2021.2.3
- Go SSH: 0.16.0
- libssh2: 1.11.0
- PuTTY: 0.82[^1]

이 표는 운영 플랜에서 우선순위를 정하는 데 쓸모가 큽니다. “누가 어떤 키를 쓰는가”만이 아니라 “누가 어떤 SSH 스택을 쓰는가”가 장애를 결정하기 때문입니다.

추가로, GitHub는 과거에도 Git 프로토콜/SSH 보안을 단계적으로 강화했고, brownout로 충격을 분산시키는 방식을 사용했습니다. 과거 패턴을 보면 이번에도 “사실상 테스트 윈도우가 두 번 주어진다”로 해석하는 게 맞습니다.[^3]

## 어떤 에러로 보이나: 현장에서 자주 보는 실패 메시지들
현장에서 이 류의 이슈는 “암호 알고리즘 불일치”가 아니라 “Git이 갑자기 안 된다”로 접수됩니다. 증상이 단순해서 원인 추적이 더 늦어집니다.

가장 전형적인 형태는 아래 흐름입니다.

1) 평소처럼 `git pull` 또는 `git fetch` 실행
2) SSH 인증 단계에서 실패
3) Git은 보통 `Permission denied (publickey)` 정도로만 요약 출력
4) `ssh -vvvT git@github.com`로 보면 힌트가 나오는데, 여기서 `no mutual signature algorithm` 또는 `sign_and_send_pubkey: no mutual signature supported` 류가 등장합니다.

이 메시지는 OpenSSH가 `ssh-rsa`(SHA-1) 서명을 더 이상 사용하지 못하거나(클라이언트 정책), 반대로 서버가 `ssh-rsa` 서명을 받지 않아서(이번 GitHub 변경) 생길 수 있습니다. 이번 케이스는 “서버가 차단”이라서, 클라이언트에서 `PubkeyAcceptedAlgorithms +ssh-rsa` 같은 임시 우회가 통하지 않는 쪽으로 이해해야 합니다.[^4]

## 지금 주(2026-09-29 KST)에 해야 하는 일: 키 인벤토리 런북을 먼저 만든다
키를 교체하는 작업은 손이 많이 갑니다. 반면 인벤토리(자산화)는 더 귀찮고 더 중요합니다. 특히 org 단위에서는 “누가 어떤 키를 어디에 박아뒀는지” 모르는 상태에서 교체를 시작하면, 교체 도중에 더 큰 장애를 만들 확률이 높습니다.

내 기준으로는 이번 이슈를 다음 세 덩어리로 나눠서 런북을 만듭니다.

1) GitHub에 등록된 키(사람 키, Deploy key, 머신 유저 키)
2) GitHub로 접속하는 실행 지점(노트북/배포 서버/CI/서브모듈 빌드 등)
3) 그 실행 지점이 쓰는 SSH 스택(OpenSSH 버전, libssh2/JSch 버전, Go crypto/ssh 버전)

키를 바꿀지/클라이언트를 올릴지는 1~3을 보고 결정하는 게 안전합니다.

아래는 실제로 런북에 넣기 좋은 형태로 정리한 운영 플랜입니다.

## 자산화 1: org 전체에서 “GitHub로 나가는 SSH 경로”를 찾는 방법
키부터 찾기 전에 “SSH로 GitHub를 쓰는 경로”부터 먼저 잡는 게 효율적입니다. https remote는 이번 변경 영향이 없다고 GitHub가 명확히 말했기 때문입니다.[^1]

### Repo 내부에서 SSH remote/서브모듈을 찾기
가장 흔한 SSH 경로는 두 가지입니다.

- `git@github.com:org/repo.git` 형태의 remote
- `.gitmodules`의 submodule URL

다음 스크립트는 로컬에 미러링된 여러 repo에서 SSH URL을 찾아냅니다(현실적으로는 monorepo/멀티repo 환경에서 많이 씁니다).

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"

echo "[scan] root=$ROOT_DIR"

# 1) git remote
find "$ROOT_DIR" -name .git -type d -prune | while read -r gd; do
  repo_dir="$(dirname "$gd")"
  if git -C "$repo_dir" remote -v >/dev/null 2>&1; then
    remotes=$(git -C "$repo_dir" remote -v | awk '{print $2}' | sort -u)
    if echo "$remotes" | grep -E '(^git@github\.com:|^ssh://git@github\.com/)' >/dev/null; then
      echo "\n[repo] $repo_dir"
      git -C "$repo_dir" remote -v | sed 's/^/  /'
    fi
  fi

done

# 2) submodules
find "$ROOT_DIR" -name .gitmodules -type f | while read -r gm; do
  if grep -E 'url\s*=\s*(git@github\.com:|ssh://git@github\.com/)' "$gm" >/dev/null; then
    echo "\n[submodule] $gm"
    sed 's/^/  /' "$gm"
  fi

done
```

예상 출력은 대략 이런 느낌입니다.

```text
[repo] ./services/payment
  origin  git@github.com:my-org/payment.git (fetch)
  origin  git@github.com:my-org/payment.git (push)

[submodule] ./infra/.gitmodules
  [submodule "vendor/legacy"]
    path = vendor/legacy
    url = git@github.com:my-org/legacy-lib.git
```

여기서 중요한 건 “repo URL을 SSH로 쓰는가”이지 “현재 키가 RSA냐 ed25519냐”가 아닙니다. SSH remote가 하나라도 있으면, 그 경로의 실행 환경(빌드/배포/개발)이 전부 후보가 됩니다.

### GitHub Actions에서 SSH 기반 checkout/submodule 패턴 찾기
GitHub Actions는 기본적으로 `GITHUB_TOKEN`을 쓰는 https checkout이 많지만, 다음 패턴이 있으면 SSH 키가 개입합니다.

- `actions/checkout`에 `ssh-key:`를 넣는 케이스
- private submodule을 위해 `ssh-agent` 액션을 쓰는 케이스
- `git@github.com:` URL을 그대로 박아둔 스크립트

워크플로 파일에서 아래처럼 찾습니다.

```bash
grep -R --line-number -E "ssh-key:|webfactory/ssh-agent|git@github\.com:" .github/workflows || true
```

이 결과가 나오면, “해당 workflow가 도는 runner/컨테이너의 SSH 스택 버전”과 “주입되는 키의 관리 방식(Secrets/Vault/파일)”이 같이 조사 대상이 됩니다.

이 과정은 예전에 썼던 CI/CD 글에서 말한 ‘자동화의 신뢰성’과 연결됩니다. 키 회전은 파이프라인 신뢰성을 갉아먹기 쉬운 이벤트라서, 런북/검증/롤백 경로가 없으면 안전한 자동화가 되기 어렵습니다.

- [GitHub Actions로 “안전하고 빠른” CI/CD 파이프라인 구축하는 법 (캐시 v2·OIDC·권한 최소화까지)](https://daewooki.github.io/posts/2025-github-actions-cicd-v2oidc-2/)
- [GitHub Actions로 “안전하고 빠른” CI/CD 파이프라인 구축하는 법 (재사용·캐시·OIDC·배포보호까지)](https://daewooki.github.io/posts/2025-github-actions-cicd-oidc-2/)

## 자산화 2: GitHub에 등록된 Deploy key를 org 단위로 덤프해 “교체 대상 후보”를 뽑기
Deploy key는 repo에 붙어 있고, 만료/회전/소유권이 흐리게 운영되는 경우가 많아서 사고가 자주 납니다.

GitHub REST API로 repo deploy key 목록을 가져올 수 있습니다. `gh` CLI를 쓰면 토큰 관리가 편합니다.

아래 스크립트는 org 내 repo를 순회하면서 deploy key를 모읍니다.

```bash
#!/usr/bin/env bash
set -euo pipefail

ORG="$1"
LIMIT="${2:-200}"

# gh auth login 이 되어 있어야 합니다.

gh repo list "$ORG" --limit "$LIMIT" --json nameWithOwner -q '.[].nameWithOwner' \
| while read -r full; do
  echo "[repo] $full"
  gh api "repos/$full/keys" --paginate \
    -q '.[] | {id: .id, title: .title, read_only: .read_only, key: .key}' \
    | while read -r line; do
        # key prefix를 보고 대략적인 키 알고리즘을 분류합니다.
        # 주의: 이번 이슈의 본질은 '키 알고리즘'이 아니라 '서명 알고리즘(sha1 vs sha2)'이지만,
        # ssh-rsa 키가 깔려있는 repo는 자동화가 오래됐을 확률이 높아서 우선순위 힌트가 됩니다.
        prefix=$(echo "$line" | sed -n 's/.*"key":"\([a-z0-9-]*\) .*/\1/p')
        echo "  $line" | sed "s/\"key\":\"$prefix [^\"]*\"/\"key\":\"$prefix ...\"/"
      done

done
```

이 덤프는 두 가지 용도로 씁니다.

- “deploy key가 붙은 repo 목록” 자체가 인벤토리다
- `ssh-rsa` prefix가 많은 영역(레거시 자동화)부터 먼저 점검한다

다만 다시 강조하면, `ssh-rsa` prefix(키 타입)만 보고 이번 차단을 판단하면 안 됩니다. RSA 키는 SHA-2로 서명할 수도 있고, GitHub 공지에서도 같은 RSA 키를 그대로 유지할 수 있다고 못 박고 있습니다.[^1]

## 자산화 3: 실행 지점의 SSH 스택 버전을 “증거 기반”으로 수집한다
키 교체만으로 해결될 것 같은 이슈가 실제로는 클라이언트 업그레이드 이슈인 경우가 많습니다.

특히 GitHub가 “최소 버전”을 명시했기 때문에, 이건 취향 문제가 아니라 증거 수집 문제입니다.[^1]

### OpenSSH를 쓰는 환경(대부분의 Linux/macOS)
다음 명령을 런북에 넣고, 배포 서버/빌드 서버/중요 배치 서버에서 수집합니다.

```bash
ssh -V

# 내가 가진 클라이언트가 어떤 signature 알고리즘을 지원하는지(버전에 따라 출력이 다를 수 있음)
ssh -Q key
ssh -Q key-sig
ssh -Q kex

# github.com 대상으로 최종적으로 어떤 설정이 적용되는지
ssh -G github.com | egrep -i 'pubkeyacceptedalgorithms|hostkeyalgorithms|kexalgorithms'
```

여기서 최소한 확인하고 싶은 것은 아래입니다.

- `key-sig`에 `rsa-sha2-256`/`rsa-sha2-512`가 보이는가
- github.com에 대해 pubkey signature가 `ssh-rsa`에 의존하지 않는가

### libssh2/JSch/Go crypto/ssh 같이 “라이브러리”가 SSH를 하는 환경
여기가 더 위험합니다.

- 애플리케이션은 잘 돌아가는데, 내부에 링크된 libssh2가 오래되어 RSA SHA-2 서명이 안 됨
- Gradle/Maven 플러그인, 사내 배포 도구, Git 기능이 내장된 제품(IDE, 빌드 서버)이 JSch를 내장

GitHub는 아예 특정 라이브러리의 최소 버전을 박았습니다. 특히 `libssh2 1.11.0`, `Go SSH 0.16.0` 같은 숫자는 런북에서 하드 컷 기준으로 써도 됩니다.[^1]

JSch 쪽은 “OpenSSH 8.8부터 RSA/SHA1이 디폴트로 꺼졌다”는 맥락을 명시하고 있고, RSA 키 자체는 SHA-2 서명으로 계속 동작할 수 있다고 설명합니다.[^5]

## 교체 전략: ‘키를 바꾸는 팀’과 ‘클라이언트를 올리는 팀’을 분리한다
여기서부터는 조직 설계 문제입니다. 나는 보통 다음처럼 2트랙으로 나눕니다.

### 트랙 A: 클라이언트 업그레이드로 해결(기존 RSA 키 유지)
조건은 단순합니다.

- 현재 RSA 개인키를 바꾸기 어렵거나(사내 HSM/승인 프로세스)
- 키를 바꾸면 영향 범위가 너무 크고
- 해당 실행 지점의 SSH 클라이언트를 올릴 수 있다

이 경우 목표는 “RSA 서명을 SHA-2로 하게 만들기”입니다. GitHub도 “RSA 키는 모든 해시 알고리즘으로 서명 가능하니 키를 새로 만들 필요가 없다”고 말합니다.[^1]

실무에서 이 트랙이 잘 먹히는 곳은 다음입니다.

- 배포 서버(패키지 업그레이드 가능)
- self-hosted runner(이미지 리빌드 가능)
- 컨테이너 기반 잡(베이스 이미지 교체 가능)

### 트랙 B: 키 타입 자체를 ed25519/ECDSA로 전환(클라이언트 제약 회피)
GitHub가 제시한 대안이기도 합니다. 오래된 소프트웨어를 못 올리는 경우, RSA SHA-2 지원이 빈약한 구현에서 벗어나려면 ed25519/ECDSA로 가는 게 빠릅니다. GitHub는 신규 키는 ed25519를 권장한다고 말합니다.[^1]

다만 무조건 ed25519로 몰면 다음이 걸립니다.

- 특정 규제 환경에서 ed25519를 허용하지 않는 정책(FIPS 류)
- 네트워크 장비/어플라이언스/구형 Java 런타임에서 ed25519가 막히는 호환성 문제

그래서 트랙 B는 “사람 키부터”가 아니라 “자동화 키부터(범위가 작은 곳부터)” 적용하는 편이 낫습니다.

## 실행 계획: 자산화 → 교체 → 검증을 한 장으로 붙이는 런북 템플릿
아래는 내가 실제로 런북에 넣는 구조입니다. 이번 이슈는 특히 2026-11-04 / 2026-12-09 brownout이 있어서, 그 날짜를 검증 윈도우로 적극적으로 씁니다.[^1]

### 1) 범위 선언: “GitHub로 SSH 하는 트래픽”을 시스템 단위로 쪼갠다
조직마다 이름은 다르지만, 결국 다음 6개로 나뉩니다.

- Developer workstation(사람)
- CI hosted runner(GitHub-hosted)
- CI self-hosted runner(사내)
- Build agent(TeamCity/Jenkins 등)
- Deploy server(배포 서버가 git clone/pull 함)
- Runtime node(서비스 노드가 startup에 git을 당김: 개인적으로는 이 패턴을 줄이는 편)

각 시스템마다 “SSH 스택”과 “키 주입 방식”이 다릅니다. 시스템 단위로 오너를 지정해두지 않으면 키 회전이 공중분해합니다.

### 2) 인벤토리 산출물 정의: 최소한 이 3가지는 표로 남긴다
나는 엑셀이든 노션이든 상관없이 아래 칼럼을 강제합니다.

- 접속 경로: repo URL / 서브모듈 / clone 방식
- 실행 지점: 어떤 서버/러너/이미지/제품
- 인증 수단: Deploy key / 머신 유저 / 사람 키 / 다른 대안(HTTPS token, GitHub App)

여기에 추가로 넣으면 좋은 칼럼은 두 가지입니다.

- SSH 스택 버전(OpenSSH, libssh2, JSch, Go SSH)
- 교체 방식(클라이언트 업그레이드 vs 키 타입 전환)

이 표가 만들어지면 교체 작업은 티켓화가 가능합니다.

### 3) “키를 바꿀지 말지”의 기준을 문장으로 적는다
키 회전은 보안 이벤트이자 운영 이벤트입니다. 기준이 문장으로 없으면, 담당자에 따라 결론이 달라져서 더 위험합니다.

나는 보통 이렇게 씁니다.

- OpenSSH/라이브러리를 최소 버전 이상으로 올릴 수 있으면: 기존 RSA 키 유지 + 클라이언트 업그레이드
- 업그레이드가 불가능하면: 해당 경로는 ed25519 키로 전환 또는 https+token으로 전환
- 신규로 GitHub에 업로드되는 RSA 키는 3072-bit 이상만 허용(2026-10-14 이후)[^1]

### 4) 교체 작업: Deploy key / 머신 유저 / 개인키를 분리해서 수행한다
키를 바꿀 때 가장 흔한 실수는 “한 번에 다 바꾼다”입니다. 실제로는 교체 단위가 다릅니다.

#### Deploy key 교체
Deploy key는 repo 단위로 귀속됩니다. 교체는 다음 순서가 안전합니다.

1) 새 키 생성(가능하면 ed25519, 필요하면 RSA 3072+)
2) GitHub repo에 새 Deploy key 추가(read-only / write 권한 정확히)
3) 키를 쓰는 실행 지점(서버/러너/컨테이너)에 새 개인키 배포
4) canary job으로 `git ls-remote` 수행
5) 문제 없으면 이전 Deploy key 제거

생성 예시는 아래입니다.

```bash
# ed25519 권장
ssh-keygen -t ed25519 -a 100 -f ./deploy_key_ed25519 -C "deploy@my-org:repo"

# RSA가 필요하면(호환성/정책): 3072-bit 이상
ssh-keygen -t rsa -b 3072 -a 100 -f ./deploy_key_rsa3072 -C "deploy@my-org:repo"

# 키 길이 확인
ssh-keygen -lf ./deploy_key_rsa3072.pub
```

2026-10-14 이후에는 신규 업로드 RSA 키가 3072-bit 미만이면 정책상 막힙니다. 키를 만들 때부터 길이를 강제하는 이유가 여기에 있습니다.[^1]

#### 머신 유저(봇 계정) 키 교체
머신 유저는 접근 범위가 커서 사고의 블라스트 반경이 큽니다. 이 경우는 “키 교체”보다 “권한 축소”가 먼저인 경우도 많습니다.

- 가능하면 repo별 Deploy key 또는 GitHub App으로 쪼갭니다.
- 당장 못 쪼개면, 최소한 봇 계정의 SSH 키는 별도 이름/별도 용도(예: `id_ed25519_github_ci`)로 분리합니다.

#### 개인키(사람) 교체
사람은 각자 환경이 달라서 런북이 단일하지 않습니다. 그래도 다음 두 가지는 공통으로 강제할 만합니다.

- 새 키는 ed25519로 만들고, agent/Keychain/Windows agent 정책을 문서화
- `ssh -T git@github.com`으로 확인한 로그(버전/알고리즘)를 티켓에 첨부

GitHub 문서도 ed25519 생성 커맨드를 기본으로 보여줍니다.[^6]

## 검증: “git clone이 된다”가 아니라 “RSA SHA-2로 서명했다”를 확인한다
단순 성공/실패만 보면, 우연히 다른 키가 잡혀서 성공한 뒤에 나중에 터지는 경우가 생깁니다. 검증은 의도적으로 알고리즘을 확인하는 쪽이 낫습니다.

### 1) 최소 검증 커맨드: `ssh -vT`와 `git ls-remote`

```bash
# SSH 연결 자체 확인
ssh -vT git@github.com

# 실제 git 프로토콜까지 확인(Repo는 실제 접근 가능한 걸로)
GIT_SSH_COMMAND="ssh -vvv" git ls-remote git@github.com:my-org/my-repo.git HEAD
```

`-vvv` 로그에서 보고 싶은 단서는 이런 류입니다.

- `signing using rsa-sha2-512` 또는 `signing using rsa-sha2-256`
- 반대로 `signing using ssh-rsa`가 보이면(혹은 그 시도를 하다가 실패하면) 2027-01-13 이후엔 막힐 가능성이 큽니다.[^1]

### 2) 강제 옵션으로 “서명 알고리즘”을 고정해 테스트한다
나는 검증 때 아래를 자주 씁니다.

```bash
# RSA 키를 쓰되, 서명 알고리즘을 SHA-2로 강제
GIT_SSH_COMMAND="ssh -o PubkeyAcceptedAlgorithms=rsa-sha2-512 -i ~/.ssh/id_rsa" \
  git ls-remote git@github.com:my-org/my-repo.git HEAD
```

이 테스트가 실패하면 키를 바꿔야 하는 게 아니라, “그 실행 지점의 SSH 스택이 SHA-2 RSA 서명을 못 한다”가 더 유력합니다.

### 3) brownout 날짜를 “조직 단위 리허설”로 쓴다
GitHub가 2026-11-04, 2026-12-09에 brownout을 공지했다는 건, 그 날 실제 차단이 잠깐 들어간다는 뜻입니다.[^1]

운영 관점에서 이건 공짜 테스트 윈도우입니다.

- 주요 파이프라인/배포 작업이 그 시간대에 실패할 수 있다는 리스크는 있지만,
- 반대로 그 실패를 “운영 시간 내에” 재현할 수 있는 기회이기도 합니다.

내 경우엔 brownout 당일에 아래를 자동으로 돌려서 결과를 남깁니다.

- self-hosted runner군별 `git ls-remote`
- 배포 서버군별 `git ls-remote`
- 레거시 제품(TeamCity/Jenkins job)의 샘플 빌드 1회

그리고 실패가 나오면 키 교체 티켓이 아니라 “SSH 스택 업그레이드 티켓”으로 바로 라우팅합니다.

## 반론/회의론: “우린 이미 다 ed25519인데?”가 놓치는 것들
현장에서 자주 듣는 반론을 정리하면 다음입니다.

### 1) 사람 키만 ed25519일 수 있습니다
개발자 노트북은 ed25519인데, 배포 서버는 2018년에 만든 RSA 키 하나로 살아가는 패턴이 흔합니다. 사람은 바뀌고 시스템은 남습니다.

### 2) 키 타입이 아니라 “서명 타입”이 문제라서, 키만 보고 결론 내리기 어렵습니다
GitHub가 명시했듯이, RSA 키 자체는 SHA-2로 서명할 수 있고, 핵심은 클라이언트가 SHA-2를 선택할 수 있느냐입니다.[^1]

그래서 deploy key 목록에서 `ssh-rsa` prefix가 보인다고 해서 즉시 장애라고 단정하면 안 됩니다. 다만 레거시 자동화의 냄새로는 충분합니다.

### 3) known_hosts의 `ssh-rsa`는 다른 문제입니다
GitHub의 SSH host key fingerprints 문서에는 `ssh-ed25519`, `ecdsa-sha2-nistp256`, `ssh-rsa` host key가 함께 나옵니다.[^7]

여기서 `ssh-rsa`는 “서버 호스트키 타입”이고, 이번 변경은 “클라이언트가 로그인할 때 쓰는 서명(signature)에서 SHA-1을 허용하지 않는다”는 이야기입니다. known_hosts에 `github.com ssh-rsa ...`가 있다는 이유만으로 이번 이슈에 걸린다고 보긴 어렵습니다. 혼동을 끊어내야 런북이 덜 흔들립니다.

## 앞으로 지켜볼 것: 표면은 ssh-rsa지만, 실제로는 SSH 스택 현대화 이슈입니다
GitHub 공지는 `ssh-rsa` 차단만이 아니라, KEX 제거, post-quantum KEX 추가, RSA 키 길이 상향까지 묶여 있습니다.[^1]

이 묶음은 메시지가 명확합니다.

- Git/SSH 경로는 더 이상 “그냥 되니까 둔다”로 방치할 수 없다
- 특정 알고리즘에 고정된 레거시 도구는 결국 운영 비용으로 돌아온다

추가로, GitHub가 2026-04-20에 HTTPS/TLS 쪽에서도 SHA-1을 단계적으로 제거한다고 공지했던 점을 같이 보면, 전체적으로 “SHA-1 제거”는 큰 흐름입니다. SSH만의 특이 케이스로 보고 넘기면 반복해서 비슷한 종류의 장애를 맞습니다.[^8]

## 지금 할 수 있는 일: 1주 안에 끝내는 현실적인 체크리스트
실제로는 모든 키를 1주 안에 교체할 수 없습니다. 대신 1주 안에 “터질 곳을 특정하고, 터지기 전에 검증할 체계”는 만들 수 있습니다.

1) org 전체 repo에서 SSH remote / submodule 존재 여부를 스캔해서 목록화
2) GitHub Deploy key를 org 단위로 덤프하고, owner/사용처를 붙여서 자산화
3) self-hosted runner/배포 서버/빌드 에이전트의 `ssh -V` 및 라이브러리 버전을 수집
4) GitHub 공지의 최소 버전 기준(OpenSSH 7.2p1, libssh2 1.11.0 등)과 대조해 “업그레이드 필요” 대상을 먼저 자른다[^1]
5) 2026-11-04 brownout을 리허설로 삼아 canary `git ls-remote`를 자동 실행하도록 배치
6) 업그레이드가 불가한 레거시는 ed25519 키 전환 또는 https 경로 전환으로 격리

이렇게 하면 2027-01-13 완전 제거 시점에는 “갑자기 터졌다”가 아니라 “터질 후보를 이미 알고 있고, 남은 건 실행뿐”인 상태로 들어갈 수 있습니다.[^1]

## 참고 자료
- [Security improvements for SSH](https://github.blog/changelog/2026-09-22-security-improvements-for-ssh/)
- [Generating a new SSH key and adding it to the ssh-agent](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)
- [Checking for existing SSH keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/checking-for-existing-ssh-keys)
- [GitHub's SSH key fingerprints](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)
- [RFC 8332: Use of RSA Keys with SHA-256 and SHA-512 in the Secure Shell (SSH) Protocol](https://datatracker.ietf.org/doc/rfc8332/)
- [OpenSSH release notes](https://www.openssh.org/releasenotes.html)
- [Improving Git protocol security on GitHub](https://github.blog/security/application-security/improving-git-protocol-security-github/)
- [Sunsetting SHA-1 in HTTPS on GitHub](https://github.blog/changelog/2026-04-20-sunsetting-sha-1-in-https-on-github/)
- [mwieDE/jSch README](https://github.com/mwiede/jsch/blob/master/Readme.md)
- [libssh2 issue: RSA public key authentication fails with OpenSSH 8.8](https://github.com/libssh2/libssh2/issues/634)

[^1]: <https://github.blog/changelog/2026-09-22-security-improvements-for-ssh/>
[^2]: <https://datatracker.ietf.org/doc/rfc8332/>
[^3]: <https://github.blog/security/application-security/improving-git-protocol-security-github/>
[^4]: <https://archive.hack.lu/media/hack-lu-2024/submissions/3UBBJQ/resources/hacklu-2024-o_bxYov0q.pdf>
[^5]: <https://github.com/mwiede/jsch/blob/master/Readme.md>
[^6]: <https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent?platform=windows>
[^7]: <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints?ref=softhints-python-linux-pandas>
[^8]: <https://github.blog/changelog/2026-04-20-sunsetting-sha-1-in-https-on-github/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
