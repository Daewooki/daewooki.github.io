---
title: "Forgejo 템플릿 리포지토리 RCE: 공격 경로와 방어선"
description: "Forgejo 16.0.4 보안 릴리스로 드러난 template repo RCE 경로와 셀프호스트 운영 방어선을 정리합니다."
date: 2026-09-14 10:27:12 +0900
categories: ["OpenSource", "Forgejo"]
tags: ["forgejo", "rce", "self-hosted-git", "ci-runner", "hardening"]
render_with_liquid: false
---

## 2026-09-10 보안 릴리스가 보여준 것
Forgejo 릴리스 페이지에 따르면 v16.0.4는 2026-09-10에 공개됐고(Stable), 같은 날 v15.0.8(LTS)도 함께 나왔습니다. v16.0의 Stable 지원 종료일은 2026-10-29로 표기돼 있습니다.[^1]

이 타이밍이 중요한 이유는 단순히 RCE 하나가 뚫렸다/막혔다가 아니라, 셀프호스트 Git이 자주 밟는 함정을 정면으로 건드렸기 때문입니다.

- template repository는 UI 상에서는 편의 기능이지만, 구현은 **서버가 공격자-controlled 파일 트리를 만들고, 거기에서 Git을 실행**하는 흐름에 가깝습니다.
- CI runner(Actions)는 기능 정의 자체가 원격 코드 실행입니다. Forgejo 문서도 “Actions의 목적은 RCE”라고 못 박습니다.[^2]
- webhook/mirroring/migration 같은 외부 연동은 “코드 호스팅이 외부 네트워크와 통신하는 권한”을 얻게 만듭니다.

결국 “Git 호스팅”이 “프로덕션 권한”을 자연스럽게 흡수합니다. 내가 운영하면서 가장 자주 본 사고는, Git 서버가 *원래는* 개발 생산성 도구였는데 어느 날부터 배포 키, 레지스트리 토큰, 사내망 접근 경로가 한데 붙어버리는 유형입니다.

이번 v16.0.4 이슈는 그 결합 지점 중 template repo가 얼마나 위험한지, 그리고 격리·권한·정책을 어디에 세워야 하는지 정리하기 좋은 계기입니다.

## CVE-2026-89094의 핵심: “template expansion mishandled”가 왜 RCE가 되나
공식 CVE 레코드(공개된 CNA 데이터)를 보면 CVE-2026-89094는 다음 한 줄로 정리돼 있습니다.

- *Forgejo before 16.0.4 allows remote code execution via a crafted template repository because template expansion on files in .forgejo/template is mishandled.*
- 영향 범위는 `16.0.0 <= version < 16.0.4`, 그리고 `version < 15.0.8`로 기재돼 있습니다.
- CVSS 3.1 기준 Base score 9.9(critical)입니다.[^3]

여기서 “mishandled”가 추상적으로 들리는데, 공격이成立하는 방식은 template 기능의 내부 동작 순서와 Git의 정상 동작이 맞물리는 형태로 이해하는 게 제일 빠릅니다.

1) Forgejo는 template repo로부터 새 리포지토리를 생성할 때, `.forgejo/template`(혹은 `.gitea/template`)에 명시된 파일에 대해 변수 치환(template expansion)을 수행합니다.

2) 이 변수 치환이 **파일 내용뿐 아니라 파일 경로에도 적용**되는 구조일 때(또는 경로가 결과적으로 변형될 수 있을 때), 공격자가 “치환 결과가 `.git/...`가 되는 경로”를 의도적으로 만들어낼 수 있습니다.

3) 이후 Forgejo가 해당 디렉터리에서 `git init` 같은 Git 명령을 실행하는 순간, `.git`이 공격자에 의해 재구성돼 있으면 Git이 그것을 “기존 리포지토리”로 취급해 그대로 받아들일 수 있습니다.

CVE 문구는 “.forgejo/template에 대한 template expansion이 mishandled”라고만 말하지만, 운영자 관점에서는 이렇게 해석하는 게 실전적입니다.

- **template repo는 단순 복사가 아니라, 서버가 공격자 입력을 바탕으로 파일 트리를 다시 쓰는 기능**입니다.
- “서버에서 Git을 실행한다”는 사실 자체가 공격 표면입니다. Git은 설정과 훅, 외부 헬퍼를 통해 프로세스 실행과 간접적으로 연결될 수 있습니다.

## 공격 흐름을 운영자가 이해할 수 있는 수준으로 재구성하기
여기서는 PoC를 재현하는 절차를 쓰지 않습니다. 대신 운영자가 방어선을 설계할 수 있을 정도로, 어떤 경로가 열렸는지 개념적으로만 정리합니다.

### 1) template 생성 파이프라인이 ‘파일 시스템 + Git 실행’으로 이어진다
template repo로 새 리포지토리를 만들 때의 전형적인 파이프라인은 아래처럼 이해하면 됩니다.

- template repo 내용을 작업 디렉터리에 가져온다
- “새 리포지토리”를 만들기 위해 기존 `.git`을 제거한다
- `.forgejo/template`에 지정된 파일들에 대해 변수 치환을 수행한다
- 새 리포지토리로 만들기 위해 `git init`, `git add`, `git commit` 같은 Git 명령을 수행한다

이 중 공격자가 영향력을 행사할 수 있는 단계는 “변수 치환 결과로 만들어지는 파일/경로”입니다. CVE도 취약점의 트리거를 `.forgejo/template` 파일들에 대한 expansion에서 찾고 있습니다.[^3]

### 2) 왜 `.git`이 특별한가
`.git`은 “데이터 폴더”가 아니라 Git의 실행 컨텍스트입니다.

- `.git/config`에는 Git 동작을 바꾸는 설정이 들어갑니다.
- `.git/hooks/*`에는 Git이 특정 이벤트(커밋 등)에서 실행하는 스크립트가 들어갈 수 있습니다.
- Git은 여러 설정 키를 통해 외부 프로그램을 호출할 수 있고(예: fsmonitor 계열), 훅 경로도 바꿀 수 있습니다(예: `core.hooksPath`).

Forgejo 자체가 `git init` 이후에 `git add/commit`을 수행한다면, 훅이 실행될 “이벤트”가 자연스럽게 발생합니다. 여기서 서버 프로세스(Forgejo)가 실행하는 Git은 “웹 요청에 의해 트리거되는 서버 사이드 실행”이 됩니다.

### 3) `git init`의 동작이 방아쇠가 된다
Git은 디렉터리에 `.git`이 이미 존재하는 상태에서 `git init`을 실행하면 실패하지 않고 “Reinitialized existing Git repository” 형태로 진행할 수 있습니다. 이건 Git 입장에서는 정상 동작입니다.

이 성질 때문에 “template expansion 전에 `.git`을 지웠다”는 사실만으로는 안전하지 않습니다. expansion 단계가 `.git`을 다시 만들 수 있으면, `git init`은 그 `.git`을 받아들입니다.

## (안전한) 로컬 실험: `git init`이 기존 `.git`을 채택하는지 확인
이건 공격 재현이 아니라, 방어 설계의 기반이 되는 Git 동작 확인입니다. Git의 정상 동작을 직접 눈으로 확인해두면, 왜 “.git을 한 번 더 지워야 하는지”가 즉시 이해됩니다.

테스트 환경
- Ubuntu 24.04 또는 macOS
- git 2.39+ 권장

```bash
mkdir -p /tmp/git-init-adopt && cd /tmp/git-init-adopt

# 가짜 .git 디렉터리를 미리 만들고, config를 임의로 넣습니다.
mkdir -p .git
cat > .git/config <<'EOF'
[core]
	repositoryformatversion = 0
	filemode = true
	bare = false
	logallrefupdates = true
EOF

# 이제 git init을 실행합니다.
git init

# 결과 확인
ls -la .git | head
cat .git/config | sed -n '1,20p'
```

예상되는 관찰 포인트
- `git init`이 “.git이 이미 존재한다”는 이유로 중단되지 않습니다.
- `.git/config`가 완전히 새로 덮어써지지 않을 수 있습니다(환경/버전에 따라 다르지만, 핵심은 “이미 존재해도 에러로 끝나지 않는다”입니다).

운영자 관점 결론은 단순합니다.

- template pipeline 중간 어디에서든 `.git`이 재등장하면, 그 다음에 실행되는 Git 명령은 “공격자 컨텍스트에서 실행”될 수 있습니다.

## template repo가 ‘자체 Git 호스팅’에서 특히 위험해지는 조건
이번 CVE가 “public Forgejo만 위험”으로 끝나지 않는 이유는, 자체 호스팅에서 흔히 아래 조건을 동시에 만족하기 때문입니다.

### 1) “내부 사용자”가 곧 “공격자 가정”이어야 한다
회사/커뮤니티 Forgejo는 보통 “회원 가입 가능한 내부 서비스”로 굴러갑니다.

- 계정 하나 뚫리면 내부자 권한으로 template 생성/리포 생성/PR 생성이 가능합니다.
- Forgejo Actions 문서도 “authorized user라고 가정하기 쉽지만 그렇지 않다”는 뉘앙스로 2FA 강제 및 계정 점검을 강조합니다.[^2]

즉 “외부 공격자”보다 “계정 1개를 가진 공격자”가 더 현실적인 모델입니다. CVSS에서 `PR:L`(Privileges Required: Low)인 것도 이 맥락과 잘 맞습니다.[^3]

### 2) template repo는 보통 ‘전사 표준 스캐폴딩’이라 신뢰된다
많은 조직에서 template repo는 다음을 포함합니다.

- 표준 CI workflow
- 표준 Dockerfile / Helm chart
- 표준 배포 스크립트
- 표준 webhook 설정 문서

여기서 template가 “권장 경로”가 되는 순간, 공격자는 사회공학 없이도 “누군가가 내 template로 generate 하게 만들기”가 쉬워집니다.

### 3) Git 서버가 가진 파일 접근권이 생각보다 넓다
Forgejo는 Git 저장소 데이터, 업로드(attachments), LFS, 패키지, 각종 캐시를 관리합니다. 이건 곧 “Forgejo 프로세스가 쓸 수 있는 경로가 많다”는 의미입니다.

과거 template repo 관련 취약점에서도 “서버가 접근 가능한 파일에 쓰기/읽기가 가능해져서, 특정 구성에서는 shell access까지 이어질 수 있다”는 식의 조건부 설명이 등장했습니다.[^4]

이번 케이스는 “파일 쓰기”에서 한 단계 더 나아가 “Git 실행 컨텍스트를 오염시켜 프로세스 실행으로 연결”되는 부류로 이해하면 됩니다.

## 같이 커지는 공격 표면: template repo + runner + webhook
여기서부터는 v16.0.4만의 얘기가 아니라, 셀프호스트 Git 운영의 구조적 문제입니다.

### template repo가 열어주는 것
- 서버 파일 시스템에 공격자 영향력이 반영된 트리를 만들 수 있다
- 그 트리에서 서버가 Git 명령을 실행한다

### runner(Actions)가 열어주는 것
Forgejo 문서가 말하듯 Actions는 “원래 RCE를 수행하는 기능”입니다.[^2]

문제는 RCE 자체가 아니라 RCE가 아래와 결합하는 순간입니다.

- runner가 같은 호스트/같은 네트워크에 있다
- runner가 Docker socket을 물고 있다
- runner가 사내망에 붙어 있다
- runner가 “배포 키/클라우드 키/레지스트리 토큰”을 쉽게 읽을 수 있다

이러면 “코드 호스팅에서 코드 실행”이 “인프라 권한 획득”이 됩니다.

### webhook이 열어주는 것
webhook은 보통 Jenkins/ArgoCD/내부 배포 API로 날아갑니다.

- webhook endpoint가 내부망에 있고
- webhook secret이 Forgejo DB에 저장돼 있고
- payload가 신뢰돼서 자동 배포/자동 권한 요청으로 이어지면

Forgejo는 사실상 “외부 트리거가 가능한 배포 컨트롤 플레인”이 됩니다.

따라서 이 글의 핵심 방침은 하나입니다.

- **코드 호스팅이 곧 프로덕션 권한이 되지 않게** 경계를 다시 그립니다.

## 방어선 0: 업그레이드는 조건이 아니라 전제
CVE-2026-89094는 “16.0.4 이전은 취약, 16.0.4에서 수정”으로 적혀 있습니다.[^3]

또한 Forgejo 릴리스 페이지에서 2026-09-10에 v16.0.4가, 같은 날 LTS인 v15.0.8이 공개된 것으로 보아(표기 기준) 해당 보안 수정이 양쪽에 반영됐다고 보는 게 자연스럽습니다.[^1]

다운로드 페이지에는 예시로 v16.0.4 바이너리/컨테이너 이미지 pull 커맨드가 명시돼 있습니다.[^5]

- 바이너리 예시: `wget .../v16.0.4/forgejo-16.0.4-linux-amd64`
- 컨테이너 예시: `docker pull codeberg.org/forgejo/forgejo:16.0.4`

즉, “지금 다루는 이유”는 정당하고, 운영 액션도 명확합니다. 먼저 올리고, 그 다음에 구조를 고칩니다.

내 경우엔 긴급 RCE류는 장비/네트워크 벤더의 패치 런북과 같은 톤으로 대응합니다. 예전에 [Nexus 9000 Silicon One RCE 대응: 패치 런북](https://daewooki.github.io/posts/nexus9000-siliconone-rce-patch-runbook/)을 쓴 이유와 비슷합니다.

## 방어선 1: template 기능을 ‘권한 + 정책’으로 좁히기
패치를 올려도 template 기능은 계속 공격 표면입니다. 실무적으로는 “template은 편의”이고, 공격자는 편의를 파고듭니다.

여기서의 목표는 “template repo를 없애라”가 아니라, “template repo를 운영자가 통제 가능한 기능으로 격하”시키는 것입니다.

### 1) 리포지토리 생성 자체를 낮은 신뢰 계정에서 떼어내기
Forgejo Actions 보안 가이드에는 아주 직접적인 권고가 있습니다.

- `repository.MAX_CREATION_LIMIT`를 `0`으로 두면 사용자가 예상치 못한 리포지토리를 만들지 못하게 할 수 있다
- fork 제한도 조합해 “악성 workflow 실행” 가능성을 줄일 수 있다[^2]

이 옵션은 Actions 맥락에서 언급되지만, template repo RCE 같은 “리포 생성 파이프라인이 공격 표면”인 이슈에도 동일하게 먹힙니다.

운영 설계로 바꾸면 이런 형태가 됩니다.

- 일반 사용자는 repo 생성 불가
- 승인된 프로젝트(또는 특정 organization)에서만 repo 생성 허용
- template repo는 별도 organization에서만 관리

즉, “template generate”를 ‘인스턴스 전체 기능’이 아니라 ‘승인된 프로젝트의 운영 기능’으로 바꿉니다.

### 2) template repo를 “코드”가 아니라 “배포물”로 취급하기
template repo에는 실행 가능한 요소가 들어가기 쉽습니다.

- workflow
- 스크립트
- Dockerfile
- git hook 관련 파일(의도했든 아니든)

여기서 가장 큰 운영 실수는 “template repo를 그냥 일반 repo처럼 PR로 변경받는 것”입니다.

template repo는 아래 규칙으로 관리하는 편이 안전합니다.

- 변경은 최소한의 승인자만 merge
- 변경 시점마다 “생성 파이프라인에 영향이 있는 파일”을 별도 리뷰(예: `.forgejo/template`, `.git*`로 확장될 수 있는 경로)
- template repo의 clone/generate를 조직 외부에 노출하지 않기

패치가 적용됐더라도, template expansion 로직은 앞으로도 수정될 수 있고 같은 클래스의 취약점이 다시 나올 수 있습니다. 과거에도 template repo 처리에서 symlink/path 관련 취약점이 별도 CVE급으로 다뤄졌습니다.[^4]

### 3) “가입 가능 인스턴스”에서 template을 열어두는 건 비용이 크다
가입이 열려 있거나(커뮤니티), SSO로 누구나 로그인 가능한 인스턴스(기업)에서는 “계정 1개”가 공격 출발점입니다.

Forgejo Actions 문서에서도 2FA 점검을 명시적으로 강조합니다.[^2]

정리하면, template repo는 기능 자체보다 “누가 쓸 수 있나”가 더 중요합니다.

## 방어선 2: 샌드박스/격리로 ‘RCE의 폭발 반경’을 줄이기
패치가 들어가도 RCE는 다시 나옵니다. 특히 Git 호스팅은 외부 입력(리포, 이슈, PR, 첨부, 패키지)을 계속 받기 때문에 “언젠가 한 번은”이라는 관점이 맞습니다.

격리 목표를 분해하면 아래 3개입니다.

1) Forgejo 프로세스 권한을 최소화
2) Forgejo가 접근 가능한 파일 시스템 범위를 최소화
3) Forgejo에서 나갈 수 있는 네트워크(egress)를 최소화

### 1) 컨테이너를 쓰더라도 ‘rootless’와 ‘호스트 마운트 최소화’가 핵심
Forgejo 다운로드 페이지에는 rootless 컨테이너 이미지 이야기가 직접 있진 않지만, 최소한 공식적으로 컨테이너 이미지 배포는 안내합니다.[^5]

여기서 실무적으로 중요한 건 다음입니다.

- `/var/run/docker.sock`를 Forgejo 컨테이너에 절대 넣지 않는다
- Forgejo 데이터 볼륨은 “필요한 것만”
- 설정 파일(app.ini)은 read-only
- 업로드/attachments/LFS/packages 경로를 분리해서 권한을 나눈다

template repo가 RCE로 이어진다 해도, “컨테이너 밖”으로 나가는 경로가 없으면 사고는 거기서 멈춥니다.

### 2) SSH 키/authorized_keys 경로는 특히 조심한다
과거 template repo 관련 취약점 릴리스 노트에서는, 특정 설정 조합에서 shell access까지 이어질 수 있는 조건 중 하나로 “Forgejo가 `authorized_keys` 파일을 관리하는 구성”이 언급된 바 있습니다.[^4]

이번 v16.0.4 이슈의 직접 조건은 CVE 문구만으로는 확정할 수 없지만, 운영자 관점에서는 이 교훈이 계속 유효합니다.

- Forgejo 프로세스가 `~git/.ssh/authorized_keys` 같은 민감 파일에 쓰기 권한을 가지면, “어떤 방식으로든 파일 쓰기”가 결국 SSH 접근으로 승격될 수 있습니다.
- 그러면 Git 호스팅 RCE는 곧바로 호스트 장악으로 이어집니다.

따라서 권장하는 구조는 다음 중 하나입니다.

- SSH는 Forgejo가 직접 파일을 만지지 않는 구조로 분리
- Forgejo 컨테이너/프로세스의 파일 쓰기 권한 범위를 Git 데이터 디렉터리로 강하게 제한

### 3) 네트워크 egress를 막는 것이 webhook/runner 사고의 ‘마지막 안전장치’다
Forgejo v16.0 공지에서 “mirroring의 SSRF hardening”을 언급하며, 관리자 설정으로 접근 가능한 호스트를 제한하는 키들이 소개됩니다.[^6]

mirroring뿐 아니라 webhook, runner까지 포함하면 결론은 같습니다.

- 애플리케이션 설정만으로는 egress를 완전히 통제할 수 없습니다.
- 최종 방어선은 네트워크 레벨(방화벽, security group, Kubernetes NetworkPolicy)입니다.

Forgejo가 RCE를 당하더라도, 나갈 수 있는 목적지가 “DB + object storage + SMTP + 내부 webhook gateway” 정도로 제한돼 있으면 공격자는 수평 이동을 하기 어렵습니다.

## 방어선 3: runner를 “Git 호스팅과 다른 신뢰 구역”으로 분리
Forgejo Actions 보안 문서의 첫 문장이 사실상 결론입니다.

- Actions는 목적이 RCE이며, self-hosted runner 배포에는 많은 보안 고려사항이 있다[^2]

여기서 흔한 실패는 “Forgejo와 runner를 같은 VM에 두고, Docker-in-Docker 편하게 쓰자”입니다.

### 1) runner는 Forgejo와 같은 호스트에 두지 않는다
runner가 같은 호스트에 있으면 다음이 한 번에 붙습니다.

- 코드 호스팅 취약점 → 호스트 사용자 권한
- runner의 캐시/워크스페이스 → 민감 파일
- Docker socket → 호스트 root로의 계단

즉 “코드 호스팅=프로덕션 권한”이 되는 가장 빠른 길입니다.

### 2) runner는 ephemeral을 기본값으로 본다
Forgejo Actions 문서에는 Ephemeral runner가 목차 레벨로 존재하고, runner 설정/컨테이너 제한까지 상세히 다룹니다.[^2]

실무에서는 이걸 다음처럼 번역합니다.

- 한 job이 끝나면 VM/컨테이너를 폐기
- 캐시는 중앙 캐시로 빼되 권한을 최소화
- job 컨테이너의 privileged 금지
- job 컨테이너 네트워크 제한

Git 호스팅이 뚫렸을 때 runner까지 연쇄로 무너지는 걸 막으려면, “runner는 원래부터 불신 구역”이어야 합니다.

### 3) “임의 workflow 실행”을 설계로 막는다
Actions 보안 문서는 repository 생성 제한, fork 제한을 통해 “임의 workflow 실행”을 막는 아이디어를 명시합니다.[^2]

이건 운영자 정책으로 구현해야 합니다.

- PR에서 workflow를 실행하지 않는다(또는 승인된 사용자만)
- 외부 기여 PR은 별도 격리 runner에서만
- secrets는 protected branch에서만 주입

이걸 하지 않으면 “누가 template generate를 했나”를 막아도, 결국 “누가 workflow를 실행시켰나”에서 터집니다.

## 웹훅은 ‘직접 배포 트리거’가 아니라 ‘검증된 메시지 전달’이어야 한다
webhook은 대개 다음 흐름으로 운영됩니다.

- push/tag/release 이벤트
- webhook → CI/CD 도구
- CI/CD 도구 → 배포

여기서 실전 방어는 webhook을 “프로덕션을 직접 조작하는 호출”로 쓰지 않는 것입니다.

권장 구조는 중간에 얇은 gateway를 둡니다.

- Forgejo → webhook gateway(단일 목적, 서명 검증, allowlist)
- gateway → message queue 또는 내부 CI

Forgejo가 RCE를 당해도 “배포 API를 직접 때릴 네트워크 경로”가 없으면, webhook은 데이터 유출·스팸 정도로 끝나고 배포 장악으로 이어지기 어렵습니다.

## 추가로 같이 고쳐진 취약점: draft release attachment 접근 제어
v16.0.4에는 template RCE만 있는 게 아닙니다.

Fossies에 올라온 v16.0.4 소스 패키지의 릴리스 노트 조각 중 하나는 다음 문제를 설명합니다.

- public repo에서 인증되지 않은 호출자 포함 read 권한만 가진 사용자가 draft release의 attachment 메타데이터/내용을 가져올 수 있었고
- `GetReleaseAttachment` API와 웹 다운로드 라우트(`ServeAttachment`)가 draft 여부를 체크하지 않았다는 내용입니다.
- upstream(Gitea)에서는 CVE-2026-27660, GHSA-q9pg-jj6x-j9p6과 같은 클래스라고 언급합니다.[^7]

이건 RCE와 결이 달라 보이지만, 운영자 입장에서는 연결됩니다.

- Git 호스팅은 “코드” 말고도 artifact/attachment/package 같은 2차 산출물을 저장합니다.
- 접근 제어 버그는 곧바로 “비공개 산출물 유출”로 이어집니다.

즉, Forgejo를 운영한다는 건 Git만 운영하는 게 아니라 “작은 소프트웨어 공급망”을 운영하는 것입니다.

## (실행 가능한) template repo 위험 신호를 정적 스캔하는 스크립트
여기서는 “현재 내 인스턴스에 어떤 template repo가 있는지”를 Forgejo API로 자동 열거하는 부분은 다루지 않습니다(API 필드/권한은 인스턴스 설정과 버전에 따라 달라질 수 있습니다). 대신 운영자가 현실적으로 바로 쓸 수 있는 형태로, *template repo 후보를 로컬에서 clone한 뒤 위험 신호를 찾는* 정적 스캐너를 제공합니다.

이 스캐너의 목표는 취약점 재현이 아니라 다음을 빠르게 찾는 것입니다.

- `.forgejo/template` 또는 `.gitea/template` 존재 여부
- 템플릿 대상(glob) 중에 “경로 치환으로 `.git`가 만들어질 가능성”이 있는 패턴

### 의존성
- Python 3.11+
- git CLI

### 파일: `scan_template_repo.py`

```python
#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TEMPLATE_FILES = [".forgejo/template", ".gitea/template"]

# Forgejo/Gitea 계열에서 흔히 쓰이는 치환 토큰 형태를 '가능성'으로만 감지합니다.
# (정확한 문법은 버전에 따라 달라질 수 있으므로, 여기서는 공격 재현이 아니라 위험 신호 탐지 목적입니다.)
TOKEN_PATTERNS = [
    re.compile(r"\{\{\s*\.REPO_NAME\s*\}\}"),
    re.compile(r"\{\{\s*\.REPO_OWNER\s*\}\}"),
    re.compile(r"\$\{\s*REPO_NAME\s*\}"),
    re.compile(r"\$\{\s*REPO_OWNER\s*\}"),
]

def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{p.stderr}")
    return p.stdout

def has_tokens(s: str) -> bool:
    return any(p.search(s) for p in TOKEN_PATTERNS)

def read_template_list(repo_dir: Path):
    for tf in TEMPLATE_FILES:
        p = repo_dir / tf
        if p.exists():
            return tf, p.read_text(encoding="utf-8", errors="replace").splitlines()
    return None, []

def list_repo_files(repo_dir: Path):
    out = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo_dir)
    return [line.strip() for line in out.splitlines() if line.strip()]

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <git-clone-url> [<git-clone-url> ...]", file=sys.stderr)
        sys.exit(2)

    urls = sys.argv[1:]

    with tempfile.TemporaryDirectory(prefix="tmplscan-") as td:
        base = Path(td)

        for i, url in enumerate(urls, start=1):
            repo_dir = base / f"repo{i}"
            print(f"\n== Scanning: {url}")

            run(["git", "clone", "--depth", "1", url, str(repo_dir)])

            tmpl_file, tmpl_lines = read_template_list(repo_dir)
            if not tmpl_file:
                print("  - template marker: not found (.forgejo/template or .gitea/template)")
                continue

            print(f"  - template marker: found ({tmpl_file}), {len(tmpl_lines)} line(s)")

            files = list_repo_files(repo_dir)
            files_set = set(files)

            # 위험 신호 1: template 대상이 되는 glob/경로에 토큰이 포함돼 있는지
            token_lines = [ln for ln in tmpl_lines if has_tokens(ln)]
            if token_lines:
                print("  - risk: template list contains substitution tokens (path may become special)")
                for ln in token_lines[:10]:
                    print(f"    * {ln}")
                if len(token_lines) > 10:
                    print(f"    ... ({len(token_lines) - 10} more)")

            # 위험 신호 2: repo 안에 .g* 류 디렉터리가 있고, 토큰 치환으로 .git가 될 가능성
            # (예: .g{{.REPO_NAME}}/config -> .git/config 같은 류의 패턴)
            suspicious = [f for f in files if f.startswith(".g") and ("config" in f or "hooks" in f)]
            if suspicious:
                print("  - risk: suspicious dot-directories present (review paths)")
                for f in suspicious[:20]:
                    print(f"    * {f}")
                if len(suspicious) > 20:
                    print(f"    ... ({len(suspicious) - 20} more)")

            # 위험 신호 3: 저장소에 훅 스크립트로 쓰일 만한 파일이 존재
            hookish = [f for f in files if "hooks/" in f or f.endswith("hook")]
            if hookish:
                print("  - note: repository contains files that look like hooks")
                for f in hookish[:20]:
                    print(f"    * {f}")

            # 위험 신호 4: .git이라는 문자열이 경로에 등장(정상 리포에는 없어야 함)
            git_like = [f for f in files if f.startswith(".git")]
            if git_like:
                print("  - risk: paths starting with .git exist in tree (should be reviewed)")
                for f in git_like:
                    print(f"    * {f}")

            # 참고 출력
            print(f"  - total files: {len(files_set)}")

if __name__ == "__main__":
    main()
```

### 실행 예시

```bash
python3 scan_template_repo.py \
  ssh://git@forgejo.example.internal:2222/platform/template-service.git \
  ssh://git@forgejo.example.internal:2222/platform/template-lib.git
```

예상 출력(형태)

- template marker를 못 찾으면 “해당 repo는 template expansion 경로에 직접 들어가지 않는다”는 의미입니다.
- template marker가 있으면, path token과 dot-directory 패턴을 사람이 리뷰해야 합니다.

이 스크립트는 “취약점을 재현”하지 않습니다. 대신 운영자가 template repo를 *보안 산출물*로 취급하고 리뷰 범위를 좁히는 도구로 쓰기 좋습니다.

## 도입 판단 기준: ‘Git 호스팅’과 ‘실행/배포’의 경계를 어디에 긋나
이번 v16.0.4 이슈(CVE-2026-89094)는 패치로 일단락됐다고 해도, 셀프호스트 Git의 설계 판단을 다시 보게 만듭니다.

내가 지금 시점(2026-09-14 KST)에 Forgejo를 운영하거나 운영 중인 인스턴스를 점검한다면, 아래 기준을 통과하지 못하는 구조는 “언젠가 사고가 나면 커버할 수 없다”로 분류합니다.

1) Forgejo 프로세스가 프로덕션 네트워크에 직접 닿지 않는다
- egress allowlist
- 내부 배포 API 직접 호출 금지

2) runner는 Forgejo와 다른 신뢰 구역이다
- 다른 호스트/다른 클러스터
- ephemeral 기본
- Docker socket/hostPath 금지

3) template repo는 ‘아무나 만드는 리포’가 아니다
- repo creation 제한(필요 시 임시로만 오픈)
- template repo 변경은 제한된 승인 흐름

4) 산출물(attachments/packages/releases)은 “코드와 동급의 민감도”로 관리한다
- draft/secret이 섞일 수 있다
- 접근 제어 버그가 나면 유출로 직결된다[^7]

결국 결론은 단순합니다.

- Forgejo를 “Git 서버”로만 보면 template repo/runner/webhook가 각자 편의 기능으로 보입니다.
- Forgejo를 “내부 공급망의 시작점”으로 보면, 그 편의 기능들은 곧바로 권한 모델과 격리 설계의 문제로 바뀝니다.

## 참고 자료
- [Forgejo 릴리스 목록(v16.0.4, v15.0.8 포함)](https://forgejo.org/releases/)
- [Forgejo 다운로드 및 검증(16.0.4 바이너리/컨테이너)](https://forgejo.org/download/)
- [CVE-2026-89094 공개 레코드(OpenCVE에서 제공하는 CNA 데이터)](https://opencve.flaow.eu/cve/CVE-2026-89094)
- [Forgejo Actions 보안 가이드(Securing Forgejo Actions Deployments)](https://forgejo.org/docs/v15.0/admin/actions/security/)
- [Forgejo v16.0 공지(SSRF hardening 등 보안 관련 변경 언급)](https://forgejo.org/2026-07-release-v16-0/)
- [과거 template repo 관련 보안 릴리스 노트(Out-of-repo symlink destination, 원문 미러)](https://github.com/external-mirrors/forgejo/blob/forgejo/release-notes-published/13.0.2.md)
- [v16.0.4 릴리스 노트 조각: draft release attachment 접근 제어 누락(Fossies)](https://fossies.org/linux/forgejo/release-notes/13934.md)
- [Forgejo 월간 리포트(보안 공지/대응 관련 맥락)](https://forgejo.codeberg.page/2026-05-monthly-report/)
- [Nexus 9000 Silicon One RCE 대응: 패치 런북(관련 런북 스타일 참고용)](https://daewooki.github.io/posts/nexus9000-siliconone-rce-patch-runbook/)

[^1]: <https://forgejo.org/releases/>
[^2]: <https://forgejo.org/docs/v15.0/admin/actions/security/>
[^3]: <https://opencve.flaow.eu/cve/CVE-2026-89094>
[^4]: <https://github.com/external-mirrors/forgejo/blob/forgejo/release-notes-published/13.0.2.md>
[^5]: <https://forgejo.org/download/>
[^6]: <https://forgejo.org/2026-07-release-v16-0/>
[^7]: <https://fossies.org/linux/forgejo/release-notes/13934.md>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
