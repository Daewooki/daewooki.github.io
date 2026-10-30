---
title: "Atlantis 0.49.0: Terraform/OpenTofu 번들 제거의 파장"
description: "Atlantis 0.49.0부터 컨테이너 이미지에서 Terraform/OpenTofu가 빠지면서, 업그레이드는 ‘버전업’이 아니라 ‘IaC 엔진 공급망/재현성/정책’ 문제로 바뀝니다."
date: 2026-10-30 11:12:00 +0900
categories: ["DevOps", "Atlantis"]
tags: ["atlantis", "terraform", "opentofu", "supply-chain", "reproducible-builds", "kubernetes"]
render_with_liquid: false
---

## Docker 이미지에서 Terraform/OpenTofu가 빠졌다는 말의 실제 의미
Atlantis v0.49.0(릴리스 날짜 2026-10-25)부터 `ghcr.io/runatlantis/atlantis`의 Alpine/Debian 기반 기본 이미지에 Terraform/OpenTofu 바이너리가 더 이상 포함되지 않습니다. 릴리스 노트에 breaking change로 명시되어 있고, 기존 `latest`, `vX.Y.Z`, `vX.Y.Z-debian` 같은 태그가 전부 영향을 받습니다.[^1]

이 변화는 단순히 “이미지가 가벼워졌다”가 아니라, 운영자가 그동안 암묵적으로 의존하던 전제가 깨졌다는 뜻입니다.

- 과거: Atlantis 업그레이드 = Atlantis 서버 바이너리/이미지 업그레이드(대개는 내부에 포함된 `terraform`/`tofu`까지 같이 움직임)
- 지금: Atlantis 업그레이드 = Atlantis 서버 업그레이드 + “실행 엔진(Terraform/OpenTofu)을 어떤 경로로 제공할지”를 같이 결정해야 함

v0.49.0 릴리스 노트에는 서버가 시작 단계에서 `terraform not found in $PATH. Set --default-tf-version ...` 같은 형태로 거부할 수 있다고 적혀 있습니다.[^1] 또한 공식 문서(Deployment/Server Configuration)에도 이제 기본 이미지가 Terraform/OpenTofu를 싣지 않기 때문에 `--default-tf-version`/`--default-tf-distribution`을 설정하거나, 다운로드가 막힌 환경이면 운영자가 직접 `PATH`에 바이너리를 제공하라고 박아 두었습니다.[^2]

이제부터 Atlantis의 컨테이너 이미지는 “IaC 엔진까지 포함한 실행 환경”이 아니라, “IaC 엔진을 외부에서 주입받아 shell-out 하는 컨트롤 플레인”에 가까워졌습니다.

## ‘IaC 실행 계약’이 어디에서 어디로 이동했나
내가 말하는 IaC 실행 계약은 대충 이런 것들의 묶음입니다.

1. 어떤 바이너리를 실행하는가: Terraform vs OpenTofu
2. 어떤 버전을 실행하는가: 정확한 버전/제약 조건/업데이트 정책
3. 바이너리를 어디서 가져오는가: 이미지 번들 vs 런타임 다운로드 vs 내부 미러 vs 사전 주입
4. 실행 시점에 무엇이 변할 수 있는가: 네트워크 가용성, 릴리스 서버 장애, 캐시 유실, 스케줄링에 따른 warm/cold start
5. 감사/정책의 기준점이 어디인가: 이미지 SBOM 기준인지, 런타임 다운로드 아티팩트까지 포함인지

번들 이미지 시대에는 1~3번이 컨테이너 이미지 태그에 상당 부분 “붙어” 있었습니다. 취약점 스캐너가 “Atlantis 이미지에서 Terraform CVE가 나온다”고 말하면, 그게 실제로 내가 쓰는 Terraform 버전과 일치하는지와 별개로 운영 이슈가 되는 구조였습니다. Atlantis 프로젝트가 번들을 제거한 이유도 바로 그 지점입니다. PR #7014의 why 섹션을 보면 “번들된 어떤 Terraform/OpenTofu 버전에 대한 advisory든 이미지 스캔 결과에 뜨고, 그 서드파티 바이너리 보안 라이프사이클이 Atlantis 릴리스 속도에 묶인다”는 논리로 정리돼 있습니다.[^3]

이제는 IaC 실행 계약의 1~3번이 이미지 태그에서 떨어져 나와, 운영자가 설정(`--default-tf-version`, `--default-tf-distribution`, `--tf-download`, `--tf-download-url`)과 배포 방식(다운로드 허용/차단, 바이너리 주입)으로 다시 조립해야 합니다.[^4]

여기서 중요한 함정이 하나 있습니다. Atlantis는 Terraform/OpenTofu를 내부 라이브러리로 링크해서 쓰는 게 아니라 “외부 바이너리 실행”을 합니다. 즉, 실행 엔진의 공급망이 흔들리면 Atlantis 자체의 보안/재현성도 같이 흔들립니다. v0.49.0 업그레이드를 단순 패치로 취급하면 운영에서 깨지는 지점이 여기서 나옵니다.

## 바이너리를 어디서 가져올지: 3가지 패턴과 트레이드오프
이제 운영 선택지는 크게 3가지로 정리됩니다.

### 1) Atlantis 자동 다운로드를 정식 경로로 쓰기
공식 문서는 이제 이 경로를 “기본값”처럼 안내합니다. 핵심은 이 두 플래그/환경변수입니다.

- `--default-tf-version` / `ATLANTIS_DEFAULT_TF_VERSION`
- `--default-tf-distribution` / `ATLANTIS_DEFAULT_TF_DISTRIBUTION` (Terraform 또는 OpenTofu)

문서에 따르면 Atlantis는 기본 버전을 `<data-dir>/bin/terraform<version>` 같은 위치로 다운로드하며, `PATH`에 없으면 내려받는 식으로 동작합니다.[^4]

장점은 단순합니다.

- 커스텀 이미지 유지보수 부담이 작아집니다.
- repo별로 `terraform_version`(atlantis.yaml) 또는 `required_version`(HCL constraint)로 다양하게 굴릴 때 운영이 편합니다.[^5]

단점은 계약이 네트워크/캐시로 퍼집니다.

- Atlantis Pod가 재스케줄링되거나 `data-dir` 볼륨이 날아가면 첫 실행이 다시 “다운로드”가 됩니다. `data-dir`은 락/체크아웃/플랜/다운로드 바이너리를 같이 들고 있기 때문에 휘발되면 운영 성격이 바뀝니다.[^4]
- 릴리스 서버 장애/차단/프록시 설정 실수는 곧바로 plan/apply 장애로 전이됩니다.

네트워크를 열어두는 환경(예: egress 허용된 EKS)이라면 이 경로가 가장 비용이 낮습니다. 반대로 규제/보안으로 egress가 막힌 환경은 2) 또는 3)으로 가야 합니다.

### 2) 바이너리를 이미지에 포함시켜, Atlantis는 다운로드하지 않게 만들기
공식 문서에서도 “다운로드가 막힌다면 `PATH`에 바이너리를 직접 넣어라(마운트하거나 커스텀 이미지로 COPY)”를 대놓고 권합니다. 그리고 이 케이스에서는 `--tf-download=false`로 Atlantis가 런타임 다운로드를 시도하지 않게 하는 구성이 자연스럽습니다.[^1]

장점은 재현성/감사 관점이 훨씬 명확해진다는 점입니다.

- 이미지 digest(또는 내부 레지스트리에 올린 아티팩트)가 곧 실행 엔진 버전까지 포함한 고정점이 됩니다.
- 사내 취약점 스캐너/승인 프로세스를 “컨테이너 이미지” 단위로 돌리기 쉬워집니다.

단점은 운영자가 Terraform/OpenTofu 바이너리 공급망을 떠안는다는 점입니다.

- Terraform은 HashiCorp 릴리스 서버에서 zip과 SHA256SUMS/SHA256SUMS.sig를 제공하며, HashiCorp 문서는 GPG로 서명 파일을 검증하는 절차를 안내합니다.[^6]
- OpenTofu는 GitHub Releases 기반 다운로드를 안내하면서 SHA256SUMS 검증 후, Cosign으로 체크섬 파일 자체를 검증하는 절차를 안내합니다.[^7]

이걸 도입하면 “Atlantis 업그레이드”와 “Terraform/OpenTofu 업그레이드”가 완전히 분리됩니다. 팀이 원하는 쪽(안정성 우선 vs 최신 우선)으로 업그레이드 캘린더를 분리할 수 있다는 의미이기도 합니다.

### 3) 런타임 다운로드는 하되, 사내 미러를 통해 공급하기
Terraform은 Atlantis에 `--tf-download-url`이 있어서 `releases.hashicorp.com`을 직접 못 때리는 환경에서도 미러를 붙일 수 있습니다. 문서에 따르면 디렉터리 구조가 HashiCorp 릴리스 서버와 같아야 하고, `--tf-download=false`면 이 설정은 의미가 없습니다.[^4]

하지만 지금 시점에서 OpenTofu는 `--tf-download-url`이 지원되지 않는다고 문서에 명시돼 있습니다.[^4] 즉, OpenTofu를 사내 미러로 “Atlantis 자동 다운로드 기능 그대로” 공급하는 그림은 막혀 있고, OpenTofu 쪽은 2)처럼 바이너리를 주입하는 쪽이 더 현실적입니다.

이 차이는 실제 운영에서 꽤 크게 다가옵니다.

- Terraform만 쓰는 조직: 미러링으로 중간 타협 가능
- OpenTofu를 기본으로 쓰는 조직: 이미지 번들/마운트 방식으로 계약을 고정시키는 방향이 더 자연스럽습니다.

## 버전 결정 로직을 다시 읽어야 하는 이유
번들 이미지 시대에는 “이미지가 들고 있는 Terraform minor 몇 개 + 기본 심볼릭 링크” 정도로만 이해해도 대충 굴러갔습니다. 지금은 Atlantis의 버전 선택 로직이 곧 실행 계약이 됩니다.

### default-tf-version은 ‘폴백’이 아니라 ‘부트 스트랩’입니다
Server Configuration 문서에 “과거에는 공식 Docker 이미지가 `terraform`을 `PATH`에 넣어줘서 이 플래그 없이도 서버가 시작했지만, 이제는 이미지가 바이너리를 싣지 않기 때문에 없으면 시작을 거부한다”는 behavioral change가 적혀 있습니다.[^4]

즉, `--default-tf-version`은 “repo가 특별히 버전을 요구하지 않을 때 쓰는 기본값”이기도 하지만, 컨테이너 이미지에 바이너리가 없는 상황에서 Atlantis가 스스로를 기동하기 위한 전제 조건이 됩니다.

### repo/project에서의 버전 지정 우선순위
Terraform Versions 문서에는 핵심 규칙이 적혀 있습니다.

- `atlantis.yaml`의 `terraform_version`이 `--default-tf-version`과 HCL의 `required_version`보다 우선합니다.
- `required_version`이 constraint(예: `~> 1.2`)일 경우 Atlantis는 “그 제약을 만족하는 최신 버전”을 자동 다운로드해 사용합니다.
- OpenTofu를 쓰는 경우(프로젝트가 `terraform_distribution: opentofu`이거나 서버 기본 distribution이 opentofu인 경우) `.tofu`/`.tofu.json`에서도 `required_version`을 읽습니다.[^5]

여기서 재현성 관점의 함정은 constraint입니다.

- `required_version = "~> 1.16"` 같은 형태는 “오늘의 최신 patch”로 변합니다.
- Atlantis가 자동으로 최신을 고르는 순간, 실행 계약은 “코드 저장소 + 릴리스 시점의 외부 저장소 상태”의 함수가 됩니다.

나는 이 문제를 Terraform 업그레이드 체크리스트 글에서 “버전 고정만으로는 부족하다”는 관점으로 다뤘는데, Atlantis v0.49.0 변화 이후에는 이게 더 직접적입니다.

- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)

constraint를 쓰더라도, CI에서 “이번 분기에는 1.16.6까지만 허용” 같은 정책이 필요하면 Atlantis가 바이너리를 어디서 가져오는지를 포함해서 통제해야 합니다.

## v0.49.0이 더 이상 ‘패키징만’ 이슈가 아닌 이유: 보안 수정이 같이 들어왔다
v0.49.0 릴리스 노트는 “Docker 이미지 번들 제거” 외에도 다수의 security advisory fix가 breaking behavior change를 만든다고 강조합니다.[^1]

패키징 변화와 이 보안 수정이 결합되면, IaC 실행 계약의 경계가 달라집니다. 이유는 단순합니다.

- Atlantis는 PR 코멘트/PR 내부 파일(atlantis.yaml 등)로부터 입력을 받아
- 서버 권한으로 외부 바이너리를 실행합니다.

따라서 “어떤 바이너리를 실행하는가”는 보안 모델의 일부입니다.

### (1) `-var-file` allowlist bypass: 파일 읽기 → 결국은 공급망으로 번진다
GHSA-chm7-fjpm-927x는 PR 코멘트로 넘기는 `-var-file` 인자에서 allowlist가 우회돼, Atlantis 프로세스가 읽을 수 있는 임의 파일을 읽고 그 내용이 plan output을 통해 PR로 노출될 수 있다고 설명합니다. 영향 버전은 `< 0.49.0`, 패치는 `0.49.0`입니다.[^8]

이 이슈가 “IaC 엔진 공급망”과 연결되는 지점은 다음입니다.

- 과거 번들 이미지에서는 바이너리가 이미지 레이어에 있었고, `PATH` 오염 가능성이 상대적으로 낮았습니다.
- 이제는 운영자가 `PATH`에 바이너리를 주입하거나, Atlantis가 런타임에 다운로드합니다.

즉, PR 입력이 파일을 읽거나 경로를 건드리는 보안 문제가 터지면 “어떤 파일이 읽힐 수 있나”뿐 아니라 “어떤 바이너리가 실행될 수 있나(바이너리 교체/오염 가능성)”까지 방어 범위가 확장됩니다.

v0.49.0에서는 문서 기준으로도 `-var-file` 규칙이 plan뿐 아니라 apply/import/state rm에도 동일하게 적용된다고 명시돼 있습니다.[^9]

### (2) Plan hijack류 이슈는 ‘apply는 plan bytes를 그대로 적용한다’는 계약을 흔든다
GHSA-5vwh-xc92-8h64(영향 `< 0.49.0`, 패치 `0.49.0`)는 Atlantis가 deterministic한 plan 경로에 저장된 “그 바이트”를 apply 시 그대로 적용하면서, 그 plan이 해당 PR/커밋에서 나온 것인지 바인딩 검증이 없던 점을 문제로 설명합니다.[^10]

v0.49.0 릴리스 노트의 upgrade checklist에 “apply: plans recorded by v0.49.0 are bound to a hash. plan 파일이 plan→apply 사이에 바뀌면 거부되고 re-plan이 필요하다”가 들어간 이유가 여기라고 봅니다.[^1]

이 개선은 Terraform/OpenTofu 바이너리 공급 경로 변화와 맞물려서 중요해집니다.

- 런타임 다운로드는 “실행 시점에 외부에서 가져오는 아티팩트”가 늘어납니다.
- plan/apply 단계의 무결성 바인딩이 약하면, 아티팩트 오염이 곧 인프라 변경으로 이어질 수 있습니다.

## 가장 무난한 마이그레이션: Helm/Kubernetes에서 defaultTFVersion을 ‘명시’하고 data-dir을 영속화
Atlantis 공식 Deployment 문서에는 Helm 기준으로 `defaultTFVersion`을 반드시 설정하라고 적혀 있고, 예시로 `defaultTFVersion: "1.16.6"` 같은 형태까지 제공합니다.[^2]

여기서 중요한 건 “어떤 버전을 고르느냐”보다 “명시하느냐”입니다. 지금 시점(2026-10-30 KST)에 v0.49.0으로 올리면서도 default를 안 박아두면, 서버 기동 자체가 실패하거나, constraint에 의해 생각보다 자주 다운로드가 발생할 수 있습니다.

### values.yaml의 최소 변경 예시
아래는 ‘자동 다운로드’ 모델로 가되, 실행 계약을 최소한으로 고정하는 형태입니다.

```yaml
# values.yaml

# Atlantis image는 v0.49.0부터 terraform/tofu 바이너리가 없습니다.
image:
  repository: ghcr.io/runatlantis/atlantis
  tag: v0.49.0

# Atlantis가 기본으로 내려받아 쓸 버전
# (예시는 문서에 등장하는 숫자 형태를 따르되, 조직 표준으로 바꿔야 합니다)
environment:
  ATLANTIS_DEFAULT_TF_VERSION: "1.16.6"
  ATLANTIS_DEFAULT_TF_DISTRIBUTION: "terraform"  # opentofu를 기본으로 쓰면 "opentofu"

# data-dir 영속화(예: PVC 사용) 없으면 다운로드 캐시/plan/lock이 같이 날아갑니다.
# chart에 따라 data volume 설정 키는 다를 수 있으니 현재 사용 중인 chart 버전을 확인해야 합니다.
```

- `defaultTFVersion`/`environment: ATLANTIS_DEFAULT_TF_VERSION` 같은 설정이 문서에 직접 나옵니다.[^2]
- Atlantis의 `--data-dir`은 “DB, 체크아웃, plan, 다운로드한 Terraform binaries”를 같이 저장하며, 유실되면 locks와 unapplied plans가 날아갈 수 있다고 경고합니다.[^4]

내 경우엔 Atlantis를 stateless하게 굴리려고 했던 시기가 있었는데, v0.49.0 이후에는 최소한 “다운로드 캐시 + plan/lock” 때문에라도 data-dir을 영속화하는 편이 운영 비용이 낮아집니다. 특히 여러 repo/여러 project가 섞인 환경에서 constraint 기반 자동 다운로드를 켜면 cold start 비용이 눈에 띄게 올라갑니다.

## egress 차단/준차단 환경: ‘런타임 다운로드’ 대신 ‘검증된 바이너리 주입’으로 계약을 고정
네트워크 정책상 Atlantis Pod에서 외부 릴리스 호스트로 나가면 안 되는 환경이 흔합니다. 이때 v0.49.0 이후 선택지는 둘 중 하나입니다.

- Terraform만 필요: `--tf-download-url`로 내부 미러 제공 가능[^4]
- OpenTofu 포함: `--tf-download-url`이 OpenTofu에선 지원되지 않으므로, 바이너리를 직접 주입하는 설계가 더 현실적[^4]

여기서는 “Atlantis는 다운로드를 하지 않는다”를 전제로, 이미지에 바이너리를 포함시키는 방식(패턴 2)을 예제로 잡습니다.

### Dockerfile: Atlantis v0.49.0 베이스 + Terraform/OpenTofu를 고정 버전으로 포함
아래 예시는 네트워크가 되는 빌드 환경(예: 사내 빌드 러너)에서만 다운로드를 수행하고, 런타임(클러스터)에서는 외부 다운로드를 하지 않는 형태입니다.

- Terraform은 HashiCorp 문서의 checksum/signature 검증 절차를 그대로 따릅니다.[^6]
- OpenTofu는 OpenTofu 문서의 SHA256SUMS 검증 및 Cosign 검증 아이디어를 반영합니다.[^7]

```dockerfile
# syntax=docker/dockerfile:1

FROM ghcr.io/runatlantis/atlantis:v0.49.0

USER root

ARG TERRAFORM_VERSION=1.16.6
ARG OPENTOFU_VERSION=1.13.0

# 필수 유틸
RUN apk add --no-cache curl unzip gnupg coreutils ca-certificates \
  && update-ca-certificates

# --- Terraform 설치 (PGP로 SHA256SUMS 검증) ---
# HashiCorp 문서: https://developer.hashicorp.com/terraform/tutorials/cli/verify-archive
RUN set -eux; \
  cd /tmp; \
  base="https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}"; \
  curl -fsSLO "${base}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip"; \
  curl -fsSLO "${base}/terraform_${TERRAFORM_VERSION}_SHA256SUMS"; \
  curl -fsSLO "${base}/terraform_${TERRAFORM_VERSION}_SHA256SUMS.sig"; \
  # HashiCorp PGP key는 환경에 따라 사내 키서버/핀드 키로 운영하는 편이 안전합니다.
  # 여기서는 절차만 예시로 둡니다.
  gpg --keyserver hkps://keyserver.ubuntu.com --recv-keys B0B441097685B676; \
  gpg --verify "terraform_${TERRAFORM_VERSION}_SHA256SUMS.sig" "terraform_${TERRAFORM_VERSION}_SHA256SUMS"; \
  sha256sum -c "terraform_${TERRAFORM_VERSION}_SHA256SUMS" 2>/dev/null | grep "terraform_${TERRAFORM_VERSION}_linux_amd64.zip: OK"; \
  unzip "terraform_${TERRAFORM_VERSION}_linux_amd64.zip"; \
  install -m 0755 terraform /usr/local/bin/terraform; \
  terraform version

# --- OpenTofu 설치 (SHA256SUMS 검증) ---
# OpenTofu 문서: https://opentofu.org/docs/intro/install/standalone/
RUN set -eux; \
  cd /tmp; \
  base="https://github.com/opentofu/opentofu/releases/download/v${OPENTOFU_VERSION}"; \
  curl -fsSLO "${base}/tofu_${OPENTOFU_VERSION}_linux_amd64.zip"; \
  curl -fsSLO "${base}/tofu_${OPENTOFU_VERSION}_SHA256SUMS"; \
  echo "$(grep \"tofu_${OPENTOFU_VERSION}_linux_amd64.zip\" tofu_${OPENTOFU_VERSION}_SHA256SUMS)" | sha256sum -c -; \
  unzip "tofu_${OPENTOFU_VERSION}_linux_amd64.zip"; \
  install -m 0755 tofu /usr/local/bin/tofu; \
  tofu version

# 런타임에서는 Atlantis 다운로드 기능을 끄는 쪽이 계약이 명확합니다.
ENV ATLANTIS_TF_DOWNLOAD=false

USER atlantis
```

이 이미지로 바꾸면, v0.49.0에서 바뀐 패키징 변화(기본 이미지에 바이너리가 없음)를 우리가 의도적으로 되돌리는 셈이지만, 운영 계약 관점에서는 장점이 큽니다.

- 어떤 Terraform/OpenTofu가 실행되는지 이미지 하나로 고정됩니다.
- 런타임 egress 정책과 무관하게 plan/apply가 일관됩니다.

반대로 단점도 명확합니다.

- HashiCorp PGP 키 운영(회전/신뢰 체인/사내 미러링)을 어떻게 할지 결정을 내려야 합니다. HashiCorp는 공식적으로 checksum/signature 검증 절차를 문서로 제공합니다.[^6]
- OpenTofu는 checksum 검증과 더 강한 검증으로 Cosign 기반 검증을 문서로 제공합니다.[^7]

이걸 팀 표준으로 정하면 “Atlantis 업그레이드”의 일부가 아니라 “IaC 엔진 릴리스 엔지니어링”의 일부가 됩니다.

## initContainer로 바이너리 주입하기: 이미지 유지보수 부담을 낮추되 계약은 고정
커스텀 Atlantis 이미지를 유지하기 싫다면, Kubernetes에서는 initContainer + emptyDir 볼륨으로도 계약을 고정할 수 있습니다. 핵심은 다음입니다.

- initContainer는 Terraform/OpenTofu를 다운로드/검증 후 `/tools/bin` 같은 공유 볼륨에 저장
- Atlantis 컨테이너는 `PATH`에 `/tools/bin`을 포함
- Atlantis는 `ATLANTIS_TF_DOWNLOAD=false`로 런타임 다운로드를 하지 않음

Helm chart values에 `extraPath`가 있고, 시스템 `PATH`에 추가할 수 있게 되어 있습니다.[^11]

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: atlantis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: atlantis
  template:
    metadata:
      labels:
        app: atlantis
    spec:
      volumes:
        - name: tools
          emptyDir: {}
        - name: atlantis-data
          persistentVolumeClaim:
            claimName: atlantis-data

      initContainers:
        - name: iac-tools
          image: alpine:3.24
          command: ["/bin/sh", "-ec"]
          args:
            - |
              apk add --no-cache curl unzip ca-certificates coreutils

              # Terraform 예시(체크섬만): 실운영에선 SHA256SUMS.sig 검증까지 붙이는 편이 안전합니다.
              TF_VER=1.16.6
              curl -fsSLO "https://releases.hashicorp.com/terraform/${TF_VER}/terraform_${TF_VER}_linux_amd64.zip"
              curl -fsSLO "https://releases.hashicorp.com/terraform/${TF_VER}/terraform_${TF_VER}_SHA256SUMS"
              echo "$(grep terraform_${TF_VER}_linux_amd64.zip terraform_${TF_VER}_SHA256SUMS)" | sha256sum -c -
              unzip terraform_${TF_VER}_linux_amd64.zip
              install -m 0755 terraform /tools/bin/terraform

              # OpenTofu 예시
              TOFU_VER=1.13.0
              curl -fsSLO "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VER}/tofu_${TOFU_VER}_linux_amd64.zip"
              curl -fsSLO "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VER}/tofu_${TOFU_VER}_SHA256SUMS"
              echo "$(grep tofu_${TOFU_VER}_linux_amd64.zip tofu_${TOFU_VER}_SHA256SUMS)" | sha256sum -c -
              unzip tofu_${TOFU_VER}_linux_amd64.zip
              install -m 0755 tofu /tools/bin/tofu

              /tools/bin/terraform version
              /tools/bin/tofu version
          volumeMounts:
            - name: tools
              mountPath: /tools

      containers:
        - name: atlantis
          image: ghcr.io/runatlantis/atlantis:v0.49.0
          env:
            - name: ATLANTIS_TF_DOWNLOAD
              value: "false"
            - name: PATH
              value: "/tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
          volumeMounts:
            - name: tools
              mountPath: /tools
            - name: atlantis-data
              mountPath: /home/atlantis/.atlantis
```

이 패턴은 “Atlantis 이미지는 공식 그대로 유지”하면서도 “실행 엔진은 내가 책임지고 고정”하는 타협안입니다.

다만 이 방식은 결국 initContainer가 다운로드를 하기 때문에, 클러스터 egress가 막혔다면 동작하지 않습니다. 그 경우 initContainer 이미지를 사내 레지스트리로 굳혀서, initContainer 자체에는 바이너리를 포함(혹은 내부 미러만 접근)시키는 형태로 바뀌어야 합니다.

## ‘공급망’을 운영한다는 뜻: 취약점 스캔, SBOM, 그리고 책임 분리
번들 제거 이후에는 취약점 스캔의 의미가 달라집니다.

- 과거: Atlantis 이미지 스캔 결과에 Terraform/OpenTofu advisory가 섞여 나오고, 실제 사용 버전과 무관한 노이즈가 생김
- 지금: Atlantis 이미지 스캔은 Atlantis + OS userland에 집중되고, Terraform/OpenTofu는 별도 아티팩트(다운로드 캐시 또는 커스텀 이미지 레이어)로 분리됨[^2]

겉으로는 좋아 보이지만, 운영자의 책임은 늘어납니다.

- 자동 다운로드를 택하면, “다운로드된 바이너리”도 취약점/무결성 검증의 범위에 들어갑니다.
- 커스텀 이미지/주입을 택하면, Terraform/OpenTofu 릴리스 검증 절차를 파이프라인에 포함해야 합니다.

HashiCorp는 Terraform zip 아카이브에 대해 checksum과 detached signature를 검증하는 과정을 공식 문서로 제공합니다.[^6] OpenTofu는 SHA256SUMS 검증과 더불어 Cosign으로 체크섬 파일 자체를 검증하는 절차를 문서로 제공합니다.[^7]

이 둘을 “한 번 구성해 두면 끝”이라고 생각하면 실패합니다. 키 회전, 릴리스 호스트 장애, 사내 프록시/미러의 TLS 이슈 같은 것들이 실제로는 더 자주 운영을 흔듭니다. 그래서 v0.49.0 이후 운영에서 중요한 건 도구 선택보다 “계약의 소유권”입니다.

- Atlantis 팀이 IaC 엔진 lifecycle을 책임지지 않기로 했고(번들 제거의 이유)[^3]
- 그 책임이 운영자에게 넘어왔습니다.

## 결론: Atlantis 업그레이드는 이제 ‘실행 엔진 공급 전략’ 결정이다
v0.49.0에서 Docker 이미지에서 Terraform/OpenTofu 번들이 제거되면서, Atlantis는 더 이상 “이미지 하나로 IaC 실행 환경까지 포함”하지 않습니다.[^1]

이 변화 자체는 합리적입니다. Atlantis 프로젝트가 서드파티 바이너리의 보안 라이프사이클까지 끌어안으면, 취약점 스캔 노이즈와 패치 압박이 프로젝트 릴리스 속도를 왜곡합니다. PR #7014의 why가 그걸 정확히 짚습니다.[^3]

하지만 운영자는 이제 선택해야 합니다.

- 런타임 다운로드를 허용하고 `data-dir`을 영속화해서 “편의성”을 얻을지[^4]
- 바이너리를 주입/번들해서 “재현성/감사 가능성”을 얻을지[^6]
- Terraform만이라도 내부 미러로 돌려 네트워크 리스크를 줄일지(`--tf-download-url`)[^4]

내 기준에서, Atlantis를 조직의 핵심 변경 게이트로 쓰고(특히 prod apply를 Atlantis가 들고 있다면) 규제/감사 요구가 있거나 egress 제약이 강한 환경일수록 “바이너리 주입/번들로 계약을 고정”하는 쪽이 운영이 단단해집니다. 반대로 여러 팀/여러 repo가 제약 조건 기반으로 빠르게 움직이고, egress가 관리되는 환경이라면 “Atlantis 자동 다운로드 + data-dir 영속화”가 비용 대비 효율이 높습니다.

## 참고 자료
- [Atlantis v0.49.0 릴리스 노트](https://github.com/runatlantis/atlantis/releases)
- [PR #7014: stop bundling Terraform and OpenTofu in the Docker images](https://github.com/runatlantis/atlantis/pull/7014)
- [Atlantis Deployment 문서(이미지 변형, Helm 설정)](https://www.runatlantis.io/docs/deployment)
- [Atlantis Server Configuration 문서(tf-download, tf-download-url, default-tf-version)](https://www.runatlantis.io/docs/server-configuration)
- [Atlantis Terraform Versions 문서(terraform_version, required_version, OpenTofu .tofu 지원)](https://www.runatlantis.io/docs/terraform-versions.html)
- [GHSA-chm7-fjpm-927x: var-file allowlist bypass advisory](https://github.com/runatlantis/atlantis/security/advisories/GHSA-chm7-fjpm-927x)
- [GHSA-5vwh-xc92-8h64: plan-hijack advisory](https://github.com/runatlantis/atlantis/security/advisories/GHSA-5vwh-xc92-8h64)
- [HashiCorp: Verify Terraform binary archives](https://developer.hashicorp.com/terraform/tutorials/cli/verify-archive)
- [OpenTofu: Installing from GitHub Releases 및 checksum/Cosign 검증](https://opentofu.org/docs/intro/install/standalone/)
- [runatlantis/helm-charts values.yaml(extraPath 등)](https://github.com/runatlantis/helm-charts/blob/main/charts/atlantis/values.yaml)
- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)
- [Terraform plan JSON: format_version 계약과 소비자 테스트](https://daewooki.github.io/posts/terraform-plan-json-format-version-contract/)

[^1]: <https://github.com/runatlantis/atlantis/releases>
[^2]: <https://www.runatlantis.io/docs/deployment>
[^3]: <https://github.com/runatlantis/atlantis/pull/7014>
[^4]: <https://www.runatlantis.io/docs/server-configuration>
[^5]: <https://www.runatlantis.io/docs/terraform-versions.html>
[^6]: <https://docs.hashicorp.com/terraform/tutorials/cli/verify-archive>
[^7]: <https://opentofu.org/docs/intro/install/standalone/>
[^8]: <https://github.com/runatlantis/atlantis/security/advisories/GHSA-chm7-fjpm-927x>
[^9]: <https://github.com/runatlantis/atlantis/blob/main/runatlantis.io/docs/using-atlantis.md>
[^10]: <https://github.com/runatlantis/atlantis/security/advisories/GHSA-5vwh-xc92-8h64>
[^11]: <https://github.com/runatlantis/helm-charts/blob/main/charts/atlantis/values.yaml>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
