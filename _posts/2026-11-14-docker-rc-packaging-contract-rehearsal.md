---
title: "Docker Engine 29.10.0 RC로 패키징 계약을 먼저 고정하는 법"
description: "29.10.0-rc.1로 설치 소스·sha256 검증·RHEL 계열 표준 런북을 GA 전에 고정한다."
date: 2026-11-14 14:13:17 +0900
categories: ["DevOps", "Docker"]
tags: ["docker-engine", "packaging", "supply-chain", "rhel-family", "ci-cd", "upgrade-rehearsal"]
render_with_liquid: false
---

RC는 기능보다 패키징이 먼저 흔들립니다. 특히 Docker처럼 설치 경로가 apt/yum/정적 tar로 갈라지고, 같은 “Docker 설치”가 사실상 다른 공급망을 의미하는 제품은 더 그렇습니다. 

2026-11-14 KST 시점에서 확인되는 사실만 놓고 보면, Docker Engine 29.10.0-rc.1은 이미 여러 채널에 흔적을 남겼고(정적 테스트 아카이브 업로드, `docker/packaging` 릴리스), 동시에 “정식 GA 전에 설치 계약을 고정할 창”을 열어줍니다. 

- Linux 정적 테스트 채널에는 `docker-engine_29.10.0-rc.1.tgz`와 함께 **`.sha256` 파일이 동일 타임스탬프(2026-11-06)로 추가**돼 있습니다.[^1]
- Ubuntu `test` 풀에도 `29.10.0~rc.1` deb가 올라와 있습니다(예: Ubuntu 24.04 noble).[^2]
- RHEL 계열 rpm은 `test/Packages`에 `29.10.0~rc.1`이 올라와 있습니다(예: RHEL 9, CentOS 10).[^3]
- 다운로드 루트에 Alma/Oracle/Rocky가 **별도 디렉터리로 생겼고(최소 alma/oracle은 2026-11-06), Rocky는 2026-11-12 기준으로 확인**됩니다.[^4]

내가 “RC가 나온 주”에 하는 일은 기능 검증이 아니라 **설치 계약(installation contract)**을 먼저 맞추는 것입니다. 기능은 GA 직전에도 바뀔 수 있지만, 설치 계약이 한번 깨지면 다운스트림 운영/보안/컴플라이언스가 같이 흔들립니다. 예전에 Atlantis 번들 제거가 IaC 실행 계약을 흔든 사례나[^5], zlib의 사소한 변경이 다운스트림 빌드/패키징을 무너뜨린 사례[^6]를 이미 겪었습니다. Docker도 똑같이 접근해야 합니다.

## 설치 소스(apt/yum/정적 tar) 진실 맞추기

Docker Engine 설치는 한 문장으로 “Docker 설치”라고 부르기 쉽지만, 운영에서 중요한 건 **어떤 저장소/어떤 채널/어떤 검증 규칙으로 설치되느냐**입니다. Docker 문서도 Linux 설치에서 `stable`과 `test` 두 채널을 명시합니다.[^7]

여기서 첫 번째 작업은 “현재 우리 조직이 Docker를 어디서 어떻게 받고 있는지”를 사실로 확정하는 것입니다. 이 작업을 건너뛰면 RC 검증을 해도 GA 이후 실제 운영 채널에서 다른 패키지가 들어오고, 결과적으로 리허설이 무의미해집니다.

### 1) Debian/Ubuntu: `docker.io`와 `docker-ce`는 같은 Docker가 아닙니다

Ubuntu 계열에서 흔한 사고는 다음입니다.

- OS 기본 저장소의 `docker.io`(Ubuntu 패키지)와
- Docker 공식 저장소의 `docker-ce`(Docker CE 패키지)

이 둘이 한 호스트에 섞여 들어오는 것.

이때 소켓 충돌(`/var/run/docker.sock`), systemd unit 충돌, 업그레이드 경로 꼬임이 같이 옵니다. RC 주간에 해야 하는 건 “RC를 설치해본다”가 아니라 **RC를 설치할 때도 설치 소스가 단일하게 유지되는지**를 확인하는 일입니다.

Ubuntu 설치 절차는 Docker 공식 apt repo를 추가하고(키링 포함) 설치하라고 안내합니다.[^8]

여기서 나는 `apt list`나 `apt-cache policy`보다 “내가 실제로 어떤 `.deb`를 받게 되는지”를 디렉터리 인덱스로도 확인해 둡니다. 예를 들어 Ubuntu 24.04 noble의 `test` 풀에는 `docker-ce_29.10.0~rc.1-1~ubuntu.24.04~noble_amd64.deb`가 2026-11-06 타임스탬프로 보입니다.[^2]

RC 주간에 해두면 좋은 체크리스트는 이 정도입니다.

- `docker.io` 설치 여부를 먼저 확인하고 필요하면 제거한다.
- apt source가 `.list`인지 `.sources`인지(조직 표준) 고정한다.
- `stable`만 쓸지, `test`를 스테이징에서만 열지 정책을 문장으로 확정한다.
- “특정 버전 설치” 명령을 조직 런북에 **복붙 가능한 형태**로 남긴다.

### 2) RHEL 계열: yum/dnf는 repo URL이 곧 계약입니다

RHEL 계열은 더 단순합니다. repo URL이 곧 공급망입니다.

- Docker 문서 기준으로 RHEL은 `download.docker.com/linux/rhel` 루트를 사용합니다.[^9]
- 실제로 RHEL 9 `test/Packages` 디렉터리에 `docker-ce-29.10.0~rc.1-1.el9.x86_64.rpm`이 올라와 있습니다.[^3]
- CentOS 10도 마찬가지로 `test/Packages`에 `29.10.0~rc.1` rpm이 올라와 있습니다.[^10]

이게 중요한 이유는 조직 내부에서 “RHEL 계열 서버”라는 말이 보통 다음을 한데 묶기 때문입니다.

- RHEL (Red Hat subscription)
- Rocky Linux
- AlmaLinux
- Oracle Linux

그런데 과거에는 관행적으로 `centos` 루트(혹은 rhel 루트)를 갖다 쓰는 경우가 많았고, 이 관행은 “지원이 애매한데도 되는 것처럼 보이는” 회색지대를 만들었습니다.

29.10 RC 타이밍에서 눈에 띄는 변화는, 다운로드 루트에 Alma/Oracle/Rocky가 **별도 최상위 디렉터리로 존재**한다는 점입니다.

- Alma: `https://download.docker.com/linux/alma/` (2026-11-06에 `docker-ce.repo`가 보임)[^4]
- Oracle: `https://download.docker.com/linux/oracle/` (2026-11-06에 `docker-ce.repo`가 보임)[^11]
- Rocky: `https://download.docker.com/linux/rocky/` (2026-11-12에 `docker-ce.repo`가 보임)[^12]

이건 단순한 “폴더가 생겼다”가 아니라, **설치 경로를 배포판 ID 기준으로 정규화할 의지가 생겼다**는 신호입니다. RC 주간에 해야 할 일은, 사내 런북에서 “RHEL 계열은 centos repo를 쓴다” 같은 과거 관행 문장을 지우고, **어떤 배포판 ID는 어떤 repo 루트를 쓰는지**를 표로 고정하는 것입니다.

## 정적 tar에 `.sha256`가 붙었다: 공급망 신호를 CI에 반영

정적 바이너리는 Docker 문서에서도 “수동 설치용, 정적으로 링크된 바이너리”로 별도 취급합니다.[^7]

문제는 정적 바이너리가 편하다는 이유로 운영에서 은근히 많이 쓰이는데(특히 air-gapped, minimal OS, 특수 커널/드라이버 조합, 패키지 매니저 정책이 복잡한 조직), 검증을 대충 해버리면 **가장 취약한 설치 경로**가 됩니다.

이번 29.10 RC에서 눈에 띄는 건, Linux 정적 테스트 채널 디렉터리에 `*.tgz.sha256` 파일이 함께 올라왔다는 점입니다.

예를 들어 x86_64 디렉터리에는 다음 조합이 같은 타임스탬프(2026-11-06)로 존재합니다.

- `docker-engine_29.10.0-rc.1.tgz`
- `docker-engine_29.10.0-rc.1.tgz.sha256`

그리고 CLI/전체 번들(`docker-29.10.0-rc.1.tgz`)도 동일 패턴입니다.[^1]

나는 이런 변화를 기능 변경보다 더 진지하게 봅니다. **체크섬 파일이 추가되는 순간, “다운로드→검증→설치”를 자동화할 근거가 생깁니다.** 

정적 tar를 쓰는 조직에서 RC 주간에 해야 할 일은 다음 두 가지입니다.

1) 체크섬 검증이 없는 다운로드 경로를 전부 찾아낸다.
2) 체크섬 검증을 CI(혹은 golden image 빌드 파이프라인)에 강제한다.

### 체크섬 추가가 의미하는 것

- 최소한의 의미: “서버에 복사된 파일이 전송 중 깨지지 않았다”를 보장합니다.
- 실무적 의미: **Artifact를 내부 캐시에 미러링**할 때, 미러가 손상/오염되면 바로 탐지할 수 있습니다.
- 공급망 관점: SLSA 같은 상위 레벨 증명까지는 아니지만, “검증 가능한 고정값”이 생긴 순간부터 파이프라인 설계를 바꿀 수 있습니다.

여기서 중요한 건 “sha256이 있으니 안전하다”가 아니라, “sha256이 있으니 이제부터는 sha256이 없던 시절처럼 운영하면 안 된다”입니다.

## RC 주간에 만드는 CI 작업: 다운로드-검증-설치 리허설

아래 예시는 정적 tar를 기준으로 잡습니다. 이유는 간단합니다.

- 정적 tar는 패키지 매니저보다 검증을 빼먹기 쉽고,
- 테스트 환경에서 “딱 그 버전”을 재현하기 쉬우며,
- 이번 RC에서 `.sha256` 추가가 실제로 확인되기 때문입니다.[^1]

다만 운영이 apt/yum이라면, 같은 아이디어를 “repo snapshot + 패키지 버전 pinning + GPG 강제”로 옮기면 됩니다.

### (A) 정적 tar 검증 스크립트 (실행 가능)

다음 스크립트는 Linux x86_64 기준으로 29.10.0-rc.1을 다운로드하고, `.sha256` 파일을 이용해 검증한 다음, 압축을 풀어 버전 문자열만 확인합니다.

- 의존성: `curl`, `sha256sum`, `tar`
- 실행 환경: Ubuntu/Debian/RHEL 계열 어디든 가능

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="29.10.0-rc.1"
ARCH="x86_64"
BASE="https://download.docker.com/linux/static/test/${ARCH}"

WORKDIR="${WORKDIR:-/tmp/docker-static-verify}"
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# 1) artifact 다운로드
curl -fsSLO "${BASE}/docker-engine_${VERSION}.tgz"
curl -fsSLO "${BASE}/docker-engine_${VERSION}.tgz.sha256"

# 2) sha256 검증
# sha256 파일은 일반적으로 'HASH  FILENAME' 형식이므로 sha256sum -c로 검증한다.
sha256sum -c "docker-engine_${VERSION}.tgz.sha256"

# 3) 설치 대신, 내용만 풀어서 버전 확인(시스템 오염 방지)
mkdir -p extract
# docker-engine tgz는 docker/ 아래에 바이너리를 포함하는 형태가 많아서 strip-components는 상황별로 조정한다.
# 여기서는 일단 그대로 풀고 경로를 탐색한다.
tar -xzf "docker-engine_${VERSION}.tgz" -C extract

# 4) dockerd/docker 버전 확인
# 실제 파일 배치는 아카이브 구조에 따라 달라질 수 있으니 find로 찾는다.
DOCKERD_BIN=$(find extract -type f -name dockerd -perm -111 | head -n 1 || true)
DOCKER_BIN=$(find extract -type f -name docker -perm -111 | head -n 1 || true)

if [[ -z "$DOCKERD_BIN" || -z "$DOCKER_BIN" ]]; then
  echo "dockerd/docker binary not found in archive layout"
  echo "Top-level tree:";
  find extract -maxdepth 3 -type f | sed -n '1,50p'
  exit 2
fi

"$DOCKERD_BIN" --version
"$DOCKER_BIN" --version

echo "OK: ${VERSION} (${ARCH}) tarball verified and binaries are runnable"
```

예상 출력(빌드 ID/커밋 문자열은 환경/아카이브 구성에 따라 달라질 수 있고, 핵심은 버전 스트링이 목적한 RC로 찍히는지입니다):

```text
docker-engine_29.10.0-rc.1.tgz: OK
Docker version 29.10.0-rc.1, build <...>
Docker version 29.10.0-rc.1, build <...>
OK: 29.10.0-rc.1 (x86_64) tarball verified and binaries are runnable
```

이 스크립트를 CI에서 돌릴 때의 포인트는 다음입니다.

- 다운로드 URL을 코드로 고정한다.
- `.sha256` 검증을 통과하지 못하면 바로 실패시킨다.
- tar를 시스템 경로에 설치하지 않고 “검증만” 수행하는 잡을 먼저 만든다.

여기까지가 RC 주간에 해야 할 최소입니다.

### (B) `.sha256`의 존재를 “정책”으로 바꾸기

단순히 sha256 검증 스크립트를 하나 만든 것만으로는 부족합니다. 조직에서 흔히 벌어지는 일은 이런 겁니다.

- A팀은 검증한다.
- B팀은 바쁘니까 그냥 wget으로 받아 설치한다.
- 몇 달 뒤 사고가 나면, 결국 Docker가 아니라 조직이 책임을 진다.

그래서 나는 “정적 tar를 쓰는 경로는 반드시 sha256을 요구한다”를 런북이 아니라 **파이프라인에서 강제**합니다.

- golden image(Packer, Image Builder) 빌드 단계에서 검증 스텝을 mandatory로 둔다.
- 내부 artifact proxy(Nexus/Artifactory/S3)에 업로드하기 전에 sha256 검증을 통과해야만 업로드되게 한다.
- 운영 배포 스크립트는 내부 proxy만 바라보게 하고, proxy에 올라오는 artifact는 무조건 검증을 통과하게 한다.

이건 Docker만을 위한 규칙이 아니라, 공급망을 다루는 조직이라면 공통 규칙으로 만드는 편이 낫습니다.

## `docker/packaging` 릴리스로 보는 “패키징이 무엇을 묶는지”

RC를 다룰 때 릴리스 노트보다 더 먼저 보는 게 `docker/packaging`입니다. Docker Engine 패키징이 어떤 구성요소 버전을 묶고 있는지가 여기서 더 직접적으로 드러납니다.

`docker/packaging` 릴리스 페이지에는 `docker-engine-v29.10.0-rc.1` 이미지/태그와 함께, 해당 패키징 결과물이 어떤 컴포넌트를 포함하는지 요약이 올라옵니다. 여기에는 Engine/CLI뿐 아니라 containerd, runc 버전까지 같이 찍힙니다.[^13]

내 기준에서 이 정보는 두 가지 용도로 쓰입니다.

1) 업그레이드 리허설에서 “Docker만 바뀌는 게 아니다”를 조직에 납득시키는 근거
2) 장애 대응에서 “containerd/runc 조합이 바뀌었다”를 빠르게 인정하기 위한 근거

이번 RC에서 packaging 요약에 containerd/runc 버전이 함께 표기된다는 점은, 패키징 변화의 또 다른 면입니다. 패키징이 단순 배포가 아니라 “의존성 번들링의 정의”가 됩니다.[^13]

## RHEL 계열 표준화 시나리오: Alma/Rocky/Oracle 런북을 지금 고정

이번 RC 사이클에서 가장 실무적으로 큰 변화는, **RHEL 계열을 하나로 뭉개지 않고 배포판 단위로 repo 루트를 제공하기 시작했다는 점**입니다.

확인 가능한 사실:

- `download.docker.com/linux/alma/`가 존재하고, 하위에 8/9/10과 `docker-ce.repo`, `gpg`가 있습니다.[^4]
- `download.docker.com/linux/oracle/`도 동일한 형태로 존재합니다(2026-11-06 타임스탬프).[^11]
- `download.docker.com/linux/rocky/`도 동일 형태로 존재합니다(2026-11-12 기준으로 확인).[^12]

이 변화는 “지원 배포판이 늘었다”는 마케팅 문구보다, 운영에서 더 중요한 의미를 가집니다.

- repo URL이 배포판 ID와 일치하기 시작하면, **호스트가 어떤 OS인지(/etc/os-release의 `ID`)가 곧 패키징 경로**가 됩니다.
- 그 순간부터 “RHEL 계열이면 그냥 centos repo 쓰자”가 더 이상 중립적인 선택이 아닙니다. 

나는 사내 런북을 다음 3단계로 고정하는 편을 택합니다.

### 1) OS ID → repo root 매핑을 코드로 만든다

예시는 Bash로 쓰지만, 실전에서는 Ansible role 변수/Helm values/이미지 빌더 변수로 넣는 게 보통입니다.

```bash
# /usr/local/lib/docker-install/repo-map.sh

case "${ID:-}" in
  rhel)
    REPO_ROOT="https://download.docker.com/linux/rhel"
    ;;
  rocky)
    REPO_ROOT="https://download.docker.com/linux/rocky"
    ;;
  alma)
    REPO_ROOT="https://download.docker.com/linux/alma"
    ;;
  ol|oracle)
    # Oracle Linux는 /linux/oracle/ 루트가 존재한다.
    REPO_ROOT="https://download.docker.com/linux/oracle"
    ;;
  centos)
    REPO_ROOT="https://download.docker.com/linux/centos"
    ;;
  *)
    echo "Unsupported ID for repo mapping: ${ID:-<empty>}" >&2
    exit 1
    ;;
esac

echo "$REPO_ROOT"
```

이 매핑이 중요한 이유는, OS 팀/보안 팀/플랫폼 팀이 서로 다른 문서를 보고 다른 repo를 추가하는 상황을 없애기 위해서입니다.

### 2) “기존 설치가 어떤 repo에 묶여 있는지”를 진단하고 전환 절차를 런북으로 둔다

download.docker.com 쪽에서 명확히 확인되는 건, 새 repo root가 생겼다는 사실입니다. 그렇다면 조직 입장에서는 “기존 호스트가 어느 루트를 바라보고 있느냐”가 중요해집니다.

RC 주간에 해야 할 전환 리허설은 이런 형태입니다.

- `/etc/yum.repos.d/docker-ce.repo`의 baseurl이 어디인지 확인한다.
- `dnf repolist | grep docker`로 활성 repo를 확인한다.
- repo 파일을 교체하고, `docker-ce-test` 활성화 여부를 정책대로 맞춘다.

(이 절차는 배포판/사내 정책에 따라 달라질 수 있으니, 명령 자체보다 “단계”를 런북에 고정하는 게 목적입니다.)

### 3) 지원/검증 문장도 같이 고정한다

Docker 문서는 “지원되는 설치 플랫폼”과 “기타 파생 배포판은 테스트/검증하지 않는다”는 뉘앙스를 분명히 갖고 있습니다.[^7]

그런데 실제 다운로드 루트에 Alma/Rocky/Oracle이 생겼다는 건, 적어도 패키징/배포 파이프라인에서 이 배포판들을 구분하기 시작했다는 뜻입니다. 내 경험상 이런 변화는 운영 사고를 줄입니다. 왜냐하면 배포판별로 의존성 충돌(runc/containerd/selinux policy 등)이 다르기 때문입니다.

이 지점에서 런북 문장은 이렇게 바뀌어야 합니다.

- (이전) “RHEL 계열은 centos repo를 사용한다.”
- (이후) “RHEL/Rocky/Alma/Oracle은 OS ID에 맞는 Docker repo root를 사용한다. stable/test 채널은 환경(스테이징/운영)별 정책을 따른다.”

## 업그레이드 리허설: GA 전 1주일을 이득으로 만드는 체크

RC 주간에 업그레이드 리허설을 한다는 말은 “운영에 RC를 올린다”가 아닙니다. 내가 하는 리허설은 다음에 가깝습니다.

- 현재 운영 버전(예: 29.9.3 stable)에서
- 29.10.0-rc.1을 “같은 설치 경로”로 올려보고
- 다시 롤백/핀 고정이 가능한지까지 본다.

여기서 “같은 설치 경로”가 핵심입니다.

- 운영이 apt stable이면: 스테이징에서 apt test로 올려보고, GA가 나오면 stable로 갈아타는 경로를 본다.
- 운영이 rpm stable이면: 스테이징에서 `docker-ce-test` enable 상태로 올려보고, disable 후 GA로 가는 경로를 본다.
- 운영이 정적 tar면: 내부 mirror에 RC tar+sha256을 올려두고, 교체/롤백 절차를 본다.

### 릴리스 노트가 29.10을 아직 다루지 않는다는 사실도 신호다

Docker Docs의 “Docker Engine version 29 release notes”는 2026-11-03의 29.9.3까지는 보이지만, 29.10.0-rc.1 항목은 이 페이지에서 아직 확인되지 않습니다(적어도 2026-11-14 KST 기준).[^14]

이건 흔한 패턴입니다.

- 패키지/아카이브는 먼저 올라오고
- 문서화/릴리스 노트는 뒤따라옵니다.

그래서 RC 주간에 패키징을 먼저 고정해두면, GA 시점에 “기능 변경은 릴리스 노트 보고 판단”으로 분리할 수 있습니다. 설치 계약과 기능 계약을 분리하는 겁니다.

### Swarm/방화벽 같이 ‘운영 조건’에 걸리는 변경은 리허설 범위에 포함한다

29.9.3 릴리스 노트에는 firewalld가 Docker iptables 룰을 flush한 이후 Swarm overlay network에서 암호화/스푸핑 방어가 누락될 수 있는 취지의 보안 수정이 언급돼 있습니다.[^14]

이건 29.10 패키징 글에서 왜 나오냐면, 업그레이드 리허설이 결국 “우리 운영 조건이 릴리스에 반영되는지”를 보는 일이기 때문입니다. 

내가 RC 리허설에 포함시키는 테스트는 이런 종류입니다.

- firewalld 활성/비활성 상태에서 Docker 재시작
- Swarm를 쓰는 조직이라면 overlay network 생성/통신 확인
- iptables-nft/iptables-legacy 혼용 여부

이건 기능 테스트가 아니라 운영 조건 테스트입니다.

## 함정과 트레이드오프: 지금 고정하지 않으면 나중에 더 비싸다

### 1) test 채널은 “실험 기능”이 아니라 “패키징 변화”를 먼저 담는다

Docker 문서에서도 test 채널은 pre-release이며 breaking change 가능성을 경고합니다.[^7]

그런데 실제 현장에서는 test 채널을 기능 플래그처럼 취급하는 경우가 있습니다. 내가 보기엔 반대입니다.

- 기능은 앱 팀이 본다.
- 패키징 변화는 플랫폼 팀이 본다.

RC 주간에 패키징을 보는 건, 기능의 안정성을 믿어서가 아니라 **GA 때 조직 전체가 흔들리지 않도록 고정점을 만드는 일**입니다.

### 2) 체크섬을 붙였다고 해서 서명이 생긴 건 아니다

`.sha256` 파일이 추가된 건 분명한 개선이지만, 여기서 과신하면 안 됩니다.

- sha256은 “무결성”에 가깝고
- “진짜 그 공급자가 만든 artifact인가”는 별도의 서명/attestation 문제입니다.

다만 운영 현실에서는, sha256 하나만 생겨도 “내부 미러 오염 탐지”, “전송 오류 탐지”, “재현성 있는 설치” 같은 수준의 개선이 즉시 가능합니다. 지금은 그걸 CI에 반영하는 게 ROI가 큽니다.

### 3) repo 루트가 늘어나면 표준화가 쉬워지는 대신, 표준 선택 비용이 생긴다

alma/oracle/rocky 루트가 생겼다는 건 좋은 소식이지만, 동시에 조직에는 선택지가 생깁니다.

- 기존대로 centos 루트를 계속 쓸 것인가
- 배포판 루트로 갈아탈 것인가

나는 갈아타는 쪽을 선호합니다. 이유는 단순합니다.

- OS ID와 repo root가 일치하면, 장애 시 원인 분리가 쉬워집니다.
- “우리는 Oracle인데 centos repo를 쓴다” 같은 애매한 설명을 줄일 수 있습니다.

그 대신 런북/자동화 코드 수정이 필요합니다. RC 주간은 이 비용을 가장 싸게 치를 수 있는 타이밍입니다.

## 판단: RC 주간에 고정해야 GA가 싸진다

29.10.0-rc.1을 기능 관점에서 평가하는 건 아직 이릅니다. 반면 패키징 관점에서는 이미 충분히 신호가 나왔습니다.

- 정적 테스트 아카이브에 `.sha256`가 붙었고(2026-11-06)[^1]
- Ubuntu `test` 풀에 29.10.0~rc.1 deb가 올라왔고[^2]
- RHEL 계열 `test/Packages`에 rpm이 올라왔으며[^3]
- Alma/Oracle/Rocky repo 루트가 다운로드 트리에 존재합니다.[^4]

이 정도면 RC 주간에 할 일은 결정됩니다.

1) 설치 소스(apt/yum/정적 tar)의 진실을 환경별로 확정한다.
2) sha256 같은 공급망 신호를 CI에 강제 반영한다.
3) RHEL 계열(Alma/Rocky/Oracle) repo 루트 선택과 전환 절차를 런북으로 고정한다.

기능 검증은 그 다음입니다. 설치 계약이 고정되지 않으면, 기능 검증 결과는 조직에 전달될 때 다른 artifact로 바뀌고, 결국 비용만 남습니다.

## 참고 자료

- [docker/packaging 릴리스](https://github.com/docker/packaging/releases)
- [Linux 정적 테스트 채널(x86_64) 인덱스](https://download.docker.com/linux/static/test/x86_64/)
- [Docker Engine 설치 안내(채널: stable/test)](https://docs.docker.com/engine/install)
- [Ubuntu에서 Docker Engine 설치(apt repo, test 채널, pre-release)](https://docs.docker.com/engine/install/ubuntu/)
- [RHEL에서 Docker Engine 설치(rpm repo)](https://docs.docker.com/engine/install/rhel/)
- [Ubuntu 24.04 noble test 풀(29.10.0~rc.1 deb 확인)](https://download.docker.com/linux/ubuntu/dists/noble/pool/test/amd64/)
- [RHEL 9 test Packages(29.10.0~rc.1 rpm 확인)](https://download.docker.com/linux/rhel/9/x86_64/test/Packages/)
- [CentOS 10 test Packages(29.10.0~rc.1 rpm 확인)](https://download.docker.com/linux/centos/10/x86_64/test/Packages/)
- [Alma Linux 다운로드 루트(docker-ce.repo 존재)](https://download.docker.com/linux/alma/)
- [Oracle Linux 다운로드 루트(docker-ce.repo 존재)](https://download.docker.com/linux/oracle/)
- [Rocky Linux 다운로드 루트(docker-ce.repo 존재)](https://download.docker.com/linux/rocky/)
- [Docker Engine version 29 릴리스 노트(29.9.3까지 확인)](https://docs.docker.com/engine/release-notes/29/)

[^1]: <https://download.docker.com/linux/static/test/x86_64/>
[^2]: <https://download.docker.com/linux/ubuntu/dists/noble/pool/test/amd64/>
[^3]: <https://download.docker.com/linux/rhel/9/x86_64/test/Packages/>
[^4]: <https://download.docker.com/linux/alma/>
[^5]: <https://daewooki.github.io/posts/atlantis-0490-iac-execution-contract/>
[^6]: <https://daewooki.github.io/posts/zlib-14-small-breaking-changes/>
[^7]: <https://docs.docker.com/engine/install>
[^8]: <https://docs.docker.com/engine/install/ubuntu/?t=1724364714461>
[^9]: <https://docs.docker.com/engine/install/rhel/>
[^10]: <https://download.docker.com/linux/centos/10/x86_64/test/Packages/>
[^11]: <https://download.docker.com/linux/oracle/>
[^12]: <https://download.docker.com/linux/rocky/>
[^13]: <https://github.com/docker/packaging/releases>
[^14]: <https://docs.docker.com/engine/release-notes/29/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
