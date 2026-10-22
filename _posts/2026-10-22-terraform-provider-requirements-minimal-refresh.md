---
title: "Terraform 1.17 RC2: provider 요구사항 변수화와 minimal refresh"
description: "required_providers에 variables/locals가 들어오면서 모듈·정책·리뷰 기준이 바뀌고, -minimal-refresh는 drift 탐지 계약을 분리시킵니다."
date: 2026-10-22 10:02:53 +0900
categories: ["Infrastructure", "Terraform"]
tags: ["terraform", "iac", "providers", "drift-detection", "ci-cd", "platform-engineering"]
render_with_liquid: false
---

## RC2에서 눈여겨볼 변화가 파이프라인 계약을 건드리는 지점

Terraform v1.17.0-rc2 릴리스 노트에는 두 줄이 특히 크게 보입니다. 

- `required_providers`(provider requirements) 안에서 variables와 locals를 지원
- `terraform plan`/`apply`에 `-minimal-refresh` 옵션 추가

이 두 기능은 기능 자체보다도, 지금까지 조직이 Terraform을 운영하면서 무의식적으로 기대해 온 IaC 파이프라인의 계약을 바꿉니다. v1.17.0-rc2가 2026-10-14에 공개됐고, 해당 기능이 명시되어 있습니다.[^1]

여기서 말하는 계약은 대략 아래입니다.

- `terraform init`은 **구성 파일만 보고**(그리고 lock file을 보고) 항상 같은 provider를 내려받는다.
- `terraform plan`은 기본적으로 refresh를 수행하므로, drift가 있으면 어느 정도는 드러난다.
- 모듈의 `required_providers`는 literal 기반이라, 모듈 코드만 리뷰해도 대략의 호환성 범위를 읽을 수 있다.

v1.17에서는 이 전제가 흔들립니다.

- provider 선택이 “코드 + const variables + locals + 그 값이 어디서 주입되는가”로 확장됩니다.[^2]
- 계획 단계의 비용을 줄이는 대신, drift 탐지를 별도의 운영 루틴으로 격리해야 합니다.[^3]

## provider requirements에 variables/locals가 들어오면 무엇이 달라지나

### Terraform 언어 레벨에서의 의미

기존 Terraform 언어 문서에는 `terraform` 블록의 인자들이 named object(예: input variables)를 참조할 수 없다고 안내합니다.[^4]

그런데 v1.17.0-rc2에서는 릴리스 노트에 “provider requirements에서 variables와 locals를 지원”한다고 못 박았습니다.[^1] 이 변화는 Terraform core가 initialization 단계에서 provider 의존성을 해결하는 워크플로우를 더 그래프 기반으로 만들고, 그 과정에서 **const variable**과 locals를 평가할 수 있게 만든 결과로 보입니다. PR #39153의 설명에 usage가 들어 있습니다.[^2]

핵심은 여기입니다.

- variables라고 해서 다 되는 게 아니라, **const = true**인 변수만 init 시점에 평가 대상으로 들어갑니다.[^2]
- locals는 그 const variables로부터 계산된 값이라면 함께 쓸 수 있습니다.[^2]
- 값은 plan 단계의 동적 결과(리소스 속성, data source 결과 등)에 의존하면 안 됩니다. PR #39153에서 “values can't depend on any dynamic results from a plan step”라고 명시합니다.[^2]

이 조합은 provider requirement가 더 이상 단순한 static 선언이 아니라, “init-time evaluated expression”이 됩니다.

### 모듈 재사용성 관점: 재사용을 돕는가, 해치는가

Terraform 공식 문서에서는 오래전부터 모듈의 provider version constraint에 대해 강한 입장을 유지해왔습니다.

- 재사용될 모듈은 `~>` 같은 상한 제약을 넣지 말고, 최소 버전만 명시하고 루트 모듈이 상한을 관리하라는 권고가 있습니다.[^5]

v1.17에서 변수/로컬을 허용하면 모듈 작성자는 아래 같은 유혹을 받습니다.

- “환경별로 provider 버전을 다르게 쓰고 싶다” → locals/const var로 분기
- “조직 표준 provider set을 중앙에서 강제하고 싶다” → 루트에서 const var로 내려보내기

나는 이걸 **양날의 검**이라고 봅니다.

- 장점: 조직 표준화를 위해 wrapper(Terragrunt, 스크립트 템플릿, envsubst 등)를 억지로 끼워 넣던 자리에 Terraform core 기능으로 들어올 수 있습니다.
- 단점: 모듈 단독으로는 호환성 범위를 해석하기 어려워집니다. provider requirement가 변수에 의해 바뀔 수 있으니, “모듈 코드를 읽어서 version range를 판단”하던 리뷰 습관이 깨집니다.

정리하면, v1.17 이후에는 모듈 재사용성의 단위가 “모듈 코드”에서 “모듈 코드 + const variable 계약 + 그 값을 배포/주입하는 체계”로 커집니다.

### 정책(허용 버전 범위) 관점: 코드 정책에서 입력 정책으로 이동

기존에는 policy가 비교적 단순했습니다.

- `required_providers`의 `version`이 literal이라, 정규식/OPA/Sentinel/Policy-as-code에서 파일을 파싱해 “허용 범위”를 강제하기 쉬웠습니다.

하지만 이제는 정책이 두 갈래로 나뉩니다.

1) 코드 정책: `required_providers`에서 변수를 허용하되, 어떤 변수명만 쓸지, locals에서 어떤 패턴만 쓸지
2) 입력 정책: const variables 값(예: `TF_VAR_provider_version_constraint`)이 조직 허용 범위 안인지

여기서 함정이 하나 더 있습니다. Terraform variable validation은 “plan을 만들 때” 평가된다는 점입니다.[^6] 즉, const variable을 init 시점에 provider requirements에 사용하더라도, 그 변수에 대한 validation이 init 전에 동작한다는 보장은 약합니다(문서 기준으로는 plan 시점). 이 말은 아래와 같은 상황을 만들 수 있습니다.

- `terraform init`이 먼저 provider를 다운로드/선택
- 그 다음 단계에서야 validation 실패

조직 정책 입장에서는 “정책 위반을 빠르게 실패시키고 싶다”가 목표인데, init이 선행되는 순간 정책 실패의 비용(네트워크/시간)이 커집니다.

그래서 v1.17부터는, provider 정책을 HCL에만 묶어두기보다 **파이프라인 입력 계층**(var files, workspace vars, 환경변수, 실행 컨텍스트)까지 정책 범위에 넣는 게 현실적입니다.

### 리뷰 기준: `required_providers` diff만 보던 시대가 끝남

리뷰 기준이 달라지는 대표적인 케이스는 이겁니다.

- PR에서 `required_providers`는 안 바뀌었는데, CI에서 주입하는 `TF_VAR_org` 값이 바뀜
- 결과적으로 provider `source`가 바뀌고, lock file entry(fully-qualified provider address)도 바뀜

dependency lock file은 provider selection을 기록하는 파일이고, `.terraform.lock.hcl`에 provider 주소와 버전/해시가 들어갑니다.[^7] 즉, provider requirements가 변수화되면 lock file이 “코드 변경의 부산물”이 아니라 “입력 변경의 부산물”이 될 가능성이 커집니다.

이 지점에서 나는 v1.16.2 업그레이드 때 정리했던 체크리스트를 다시 떠올리게 됩니다. 버전 고정만으로는 부족하고, **실행 컨텍스트를 계약으로 묶어야** 예측 가능한 운영이 됩니다.

- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)

## provider requirements 변수화의 실전 패턴: “조직 표준 provider set”을 어떻게 설계할지

나는 provider requirements 변수화를 무작정 모듈에 퍼뜨리는 쪽에는 회의적입니다. 대신, “조직이 무엇을 표준화하려는가”를 기준으로 패턴을 분리하는 편이 낫습니다.

### 패턴 A: 모듈은 최소 버전만 literal로 유지, 루트에서 lock file로 고정

가장 보수적인 접근입니다.

- 모듈: `version = ">= x.y.z"` 정도의 최소 버전만 선언
- 루트: `.terraform.lock.hcl`를 VCS에 포함하고, provider upgrade는 별도 PR로만

Terraform은 `terraform init` 시점에 version constraint를 만족하는 최신 버전을 선택하고, lock file에 기록합니다.[^7] 이 모델에서는 변수화의 이점이 크지 않습니다.

### 패턴 B: provider `source`만 변수화 (내부 registry/외부 registry 전환)

이 패턴은 v1.17에서 매력적입니다.

- 내부 환경(예: HCP Terraform private registry)에서는 `source`가 사내 호스트네임/주소를 사용
- 외부/오픈 환경에서는 public registry 주소를 사용

HCP Terraform private registry는 public registry와 유사하게 providers/modules를 조직 내에서 공유하도록 설계되어 있고, private registry를 쓰면 version constraints와 검색 가능한 마켓플레이스가 장점이라고 설명합니다.[^8]

다만 provider source를 변수화하면 lock file에 기록되는 provider 주소도 바뀌므로, 환경 간 lock file 재사용 전략을 다시 생각해야 합니다.

- 환경별로 repo가 갈라지는 구조라면: 환경별 lock file이 자연스럽습니다.
- 단일 repo에서 workspace만 나뉜 구조라면: lock file을 하나로 유지할지, 환경별로 분리할지 선택해야 합니다.

### 패턴 C: provider `version`을 변수화 (환경별 상한/하한을 다르게)

나는 이 패턴을 가장 조심해야 한다고 봅니다.

Terraform 문서가 오랫동안 강조해온 방향은, reusable module은 상한을 모듈에 박지 말고 루트가 상한을 관리하라는 것입니다.[^5]

버전 변수를 허용하면, 루트가 상한을 관리하는 것 자체는 가능해지지만 그 방식이 “코드에 드러나는 상한”이 아니라 “입력으로 주입되는 상한”이 됩니다. 리뷰 가능성이 떨어집니다.

그래도 필요하다면, 아래 전제를 만족시키는 쪽이 낫습니다.

- version constraint를 담는 const variable을 루트에서만 정의하고
- 모든 child module은 그 값을 그대로 받기만 하고
- 그 값이 들어있는 var file을 코드 리뷰 대상으로 강제

그리고 tooling 관점에서, `terraform providers` 커맨드가 이제 `-var`/`-var-file` 옵션을 받아 provider requirements를 해석할 수 있게 되어 있습니다.[^9] 이건 “입력까지 포함한 provider graph를 리뷰/검증”하는 자동화 포인트가 됩니다.

## 코드로 보는 required_providers variables/locals: 멀티 모듈 + const variable 전파

아래 예시는 Docker를 대상으로 합니다. 클라우드 자격증명이 필요 없고, 컨테이너를 일부러 손대서 drift를 만들기 쉽습니다.

- Terraform: v1.17.0-rc2 이상
- Docker Desktop 또는 Docker Engine

디렉토리 구조는 이렇게 둡니다.

```text
.
├── main.tf
├── providers.tf
├── variables.tf
└── modules
    └── containers
        ├── main.tf
        ├── providers.tf
        └── variables.tf
```

### 루트 모듈: providers.tf / variables.tf

`required_providers`에서 **const variable과 locals를 섞어 쓰는 것**이 포인트입니다. (v1.17 이전에는 이 위치에서 locals/vars 참조 자체가 막혀 있었습니다.)[^1]

`variables.tf`

```hcl
variable "env" {
  type  = string
  const = true
}

variable "docker_provider_source" {
  type    = string
  const   = true
  default = "kreuzwerker/docker"
}

variable "docker_provider_version_base" {
  type    = string
  const   = true
  default = "~> 3.0"
}
```

`providers.tf`

```hcl
locals {
  # prod는 patch까지 고정하고, non-prod는 minor 범위를 따라간다는 식의 분기.
  # 여기서는 예시로만 보여주고, 실제로 = x.y.z 고정은 lock file과 함께 쓰는 편이 낫습니다.
  docker_provider_version = var.env == "prod" ? var.docker_provider_version_base : var.docker_provider_version_base
}

terraform {
  required_providers {
    docker = {
      source  = var.docker_provider_source
      version = local.docker_provider_version
    }
  }
}

provider "docker" {
  # Docker Desktop / Linux docker.sock 기준
  host = "unix:///var/run/docker.sock"
}
```

여기서 `env`, `docker_provider_source`, `docker_provider_version_base`를 const로 둔 이유는 initialization 단계에서 provider requirements 해석에 들어가야 하기 때문입니다. const variable은 init 시점에 사용할 수 있도록 신호를 준다는 설명이 문서에 있습니다.[^10]

### child module로 const variables를 내려보내기

`main.tf`

```hcl
module "containers" {
  source = "./modules/containers"

  docker_provider_source       = var.docker_provider_source
  docker_provider_version_base = var.docker_provider_version_base

  count = 30
  name_prefix = "tf117"
}
```

`modules/containers/variables.tf`

```hcl
variable "docker_provider_source" {
  type  = string
  const = true
}

variable "docker_provider_version_base" {
  type  = string
  const = true
}

variable "count" {
  type = number
}

variable "name_prefix" {
  type = string
}
```

`modules/containers/providers.tf`

```hcl
terraform {
  required_providers {
    docker = {
      source  = var.docker_provider_source
      version = var.docker_provider_version_base
    }
  }
}
```

이 형태는 PR #39153가 보여주는 의도(“nested modules에서도 const variables/locals를 init 단계에서 평가”)와 같은 방향입니다.[^2]

`modules/containers/main.tf`

```hcl
resource "docker_image" "nginx" {
  name = "nginx:1.27"
}

resource "docker_container" "this" {
  for_each = toset([for i in range(var.count) : "${var.name_prefix}-${i}"])

  name  = each.value
  image = docker_image.nginx.image_id

  ports {
    internal = 80
    external = 0
  }
}
```

### 실행 커맨드

const variable이라도 결국 “root module 변수 값”이 필요합니다. 가장 덜 복잡한 방법은 환경 변수 주입입니다.

```bash
export TF_VAR_env=dev

terraform init
terraform apply -auto-approve
```

여기서 `.terraform.lock.hcl`이 생성되고 provider selection이 기록됩니다. lock file은 Terraform이 선택한 provider 버전을 이후에도 재선택하기 위해 사용하는 파일이고, 커밋하는 것이 권장됩니다.[^7]

## -minimal-refresh의 내부 동작: 빠른 plan의 대가가 어디에 청구되는가

### 문서와 PR이 말하는 동작 요약

`-minimal-refresh`는 `terraform plan`/`apply`에서 refresh API 요청을 줄이기 위한 옵션입니다. plan 커맨드 레퍼런스에 동작이 비교적 자세히 들어가 있습니다.[^3]

동작을 한 문장으로 줄이면 이렇습니다.

- prior state와 현재 configuration을 먼저 비교해서 **변경이 없다고 판단되면 해당 리소스 인스턴스 refresh를 생략**합니다.
- 변경이 있다고 판단되면 refresh를 한 번 수행한 후 다시 plan을 계산합니다.[^3]

PR #38953에는 구현 메모가 더 직접적으로 들어 있습니다.

- “초기 plan 호출 결과가 no-op이면 refresh를 건너뛴다”
- “resource 인스턴스가 각자 독립적으로 refresh 여부를 선택한다(의존 리소스까지 연쇄 refresh하지 않는다)”
- “provider schema version upgrade 시에는 항상 refresh한다”
- “destroy plan + deposed/orphaned는 refresh를 하지 않는다”[^11]

문서 측면의 추가 제약은 이것입니다.

- refresh-only 모드에서는 `-minimal-refresh`를 쓸 수 없습니다.[^3]
- `-refresh=false`와 같이 쓸 수 없습니다.[^3]
- provider 업그레이드(스키마 변화 가능) 시에는 `-minimal-refresh`를 피하라고 note가 있습니다.[^3]

### 실제 파이프라인에서의 의미: plan이 더 이상 drift 센서가 아님

Terraform의 기본 동작은 plan/apply 때 in-memory refresh를 수행해서 state와 실제 인프라를 맞춰보는 것입니다. drift 튜토리얼에서도 plan/apply의 기본 refresh를 설명합니다.[^12]

하지만 `-minimal-refresh`는 문서에 명시적으로 “외부 변경을 무시할 수 있어 불완전하거나 잘못된 plan이 될 수 있다”고 말합니다.[^3]

여기서 중요한 건, 이게 단순히 “drift를 못 잡을 수 있다”가 아니라 “조직이 drift를 어떤 프로세스로 다루는가”를 바꾸게 만든다는 점입니다.

- 기존: PR plan이 느리지만 drift가 있으면 어느 정도는 눈치챈다.
- 이후: PR plan을 빠르게 만들 수 있지만 drift는 의도적으로 다른 프로세스(주기 실행, refresh-only, HCP drift detection)로 옮겨야 한다.

## -minimal-refresh를 써서 plan 비용을 줄이되 drift 탐지를 어떻게 보완할지

내 경우, drift 탐지는 IaC pipeline의 “정합성 검증”이지 “변경 검토”가 아니라고 봅니다. 둘을 같은 커맨드(plain `terraform plan`)로 처리하는 습관이 있었을 뿐입니다.

v1.17에서 추천할 만한 분리는 아래입니다.

### 1) 변경 검토용 plan: `-minimal-refresh`를 적용 (대신 drift는 별도)

- PR 단위로 여러 번 실행되는 plan은 가장 비싸고, 실패 확률(API rate limit, 일시적 장애)도 큽니다.
- `-minimal-refresh`는 “변경이 없으면 refresh를 생략”해서 비용을 줄입니다.[^3]

다만 변경 검토용 plan을 이렇게 최적화하면 drift가 숨어도 놀라지 말아야 합니다. 그 drift는 아래 절차로 옮깁니다.

### 2) drift 탐지용 plan: `terraform plan -refresh-only`를 별도로 돌린다

Terraform은 refresh-only planning mode를 지원합니다. plan 커맨드 레퍼런스에도 정의가 있고, drift 튜토리얼은 `terraform plan -refresh-only`가 drift를 확인하는 안전한 방법이라고 설명합니다.[^3]

조직이 HCP Terraform을 쓰고 있다면, drift detection은 내부적으로 “non-actionable, refresh-only plans”를 주기적으로 실행하는 방식이라고 문서에 나옵니다.[^13]

즉, drift 탐지 계약은 이미 Terraform 공식 세계관에서도 “refresh-only plan을 별도로 돌리는 것”으로 분리되어 있습니다.

### 3) drift 결과를 파이프라인에서 기계적으로 판단하는 방법

드리프트 전용 커맨드를 추가해달라는 이슈 #39172를 보면, `terraform plan -refresh-only -detailed-exitcode` 조합이 drift가 있을 때 exit code 2를 반환한다는 언급이 있습니다.[^14]

나는 이 방향을 좋아합니다.

- drift 탐지는 사람이 plan diff를 읽는 UI 문제가 아니라, 파이프라인이 실패/알림을 줄 트리거 문제입니다.
- 변경 검토와 섞지 않으면 false positive를 줄일 수 있습니다.

### 4) provider upgrade 주간에는 `-minimal-refresh`를 끈다

`-minimal-refresh` 문서 note에 “provider schema version changes가 있으면 Terraform은 plan 결과와 무관하게 refresh한다”와 함께, provider 업그레이드 시에는 `-minimal-refresh`나 `-refresh=false`를 피하라고 명시합니다.[^3]

운영 정책으로는 간단하게 이렇게 두는 편이 낫습니다.

- 평소 PR plan: `-minimal-refresh`
- provider 버전 변경 PR: `-minimal-refresh` 금지

provider 버전 변경은 `.terraform.lock.hcl` diff로 식별할 수도 있습니다. dependency lock file은 init 시 변경되며, 변경 시 Terraform이 메시지를 출력합니다.[^7]

## 예제로 확인하는 -minimal-refresh의 drift 블라인드 스팟

앞서 만든 Docker 예제에서 drift를 일부러 만들면, 이 옵션이 어떤 의미인지 체감하기 쉽습니다.

1) 컨테이너를 만든 뒤, 임의로 하나를 stop

```bash
docker ps --format '{{.Names}}' | head
# 예: tf117-0, tf117-1 ...

docker stop tf117-10
```

2) refresh를 포함한 plan을 실행

```bash
terraform plan
```

이 경우 Terraform은 기본적으로 refresh를 수행하며, drift 튜토리얼이 보여주듯 drift가 있으면 “Objects have changed outside of Terraform” 류의 메시지를 plan/apply 흐름에서 관찰할 수 있습니다.[^12]

3) `-minimal-refresh`로 plan을 실행

```bash
terraform plan -minimal-refresh
```

문서가 말하는 동작대로라면, configuration이 바뀌지 않아 no-op로 판단되는 리소스 인스턴스는 refresh를 생략할 수 있고, 그 결과 외부 변경(여기서는 컨테이너 상태 변화)을 무시해 불완전한 plan이 될 수 있습니다.[^3]

이 예제는 일부러 drift를 눈에 띄게 만들었지만, 실제 운영에서는 훨씬 미묘한 drift(태그/라벨, policy가 관심 있는 보안 속성, IAM 바인딩 등)가 더 위험합니다.

## 조직 표준까지 포함한 v1.17 마이그레이션 가이드

여기서 말하는 마이그레이션은 단순히 terraform 바이너리 업그레이드가 아니라, **운영 계약을 v1.17에 맞게 재서명**하는 작업입니다.

### 1) “init 입력”을 계약으로 승격: const variables 값을 어디서 주입하는가

provider requirements가 const variable에 의존하기 시작하면, init 단계의 입력이 중요해집니다.

- 변수 값 주입 방법(환경변수, tfvars, CLI flags 등)은 변수 문서에 정리되어 있습니다.[^10]
- const variables는 init 단계에서 사용할 수 있도록 하는 장치입니다.[^6]

조직 표준으로는 보통 둘 중 하나가 덜 사고가 납니다.

- repo에 `env/dev.tfc.auto.tfvars` 같은 형태로 고정된 파일을 두고, 실행 컨텍스트가 그 파일만 읽게 만든다
- HCP Terraform/Terraform Enterprise workspace variable sets로 고정한다

HCP/TFE에서 variable definition file을 쓰는 방식은 지원 문서에도 있습니다.[^15]

### 2) lock file을 더 강하게 다룬다: “선택”이 아니라 “감사 로그”

나는 `.terraform.lock.hcl`을 단순한 캐시가 아니라 감사 가능한 변경 이력으로 취급하는 편이 낫다고 봅니다.

- lock file은 provider selection을 기록하고, init은 기본적으로 lock file의 선택을 재사용합니다.[^7]
- provider requirements를 변수화하면, lock file 변경 원인이 코드 변경이 아닐 수도 있습니다.

그래서 파이프라인에서는 다음이 필요해집니다.

- lock file 변경이 발생하면, 그 PR은 “provider upgrade PR”로 분류
- provider upgrade PR에서는 `-minimal-refresh`를 금지하고, 최소 1회는 full refresh plan으로 검증

예전 글에서 plan JSON의 format_version을 계약으로 보는 얘기를 했는데, lock file도 성격이 비슷합니다. 파이프라인 소비자(사내 도구)가 있는 순간, 무조건 테스트가 필요합니다.

- [Terraform plan JSON: format_version 계약과 소비자 테스트](https://daewooki.github.io/posts/terraform-plan-json-format-version-contract/)

### 3) 모듈 레지스트리(HCP private registry)와 provider source 변수화의 결합

조직이 private registry를 운영하는 이유는 대체로 이것입니다.

- 모듈/프로바이더를 조직 내부에서 공유
- version constraints를 유지하면서 producers/consumers 모델을 만든다[^8]

v1.17의 provider source 변수화는, 환경에 따라 provider를 public registry에서 가져오거나 private registry에서 가져오는 전환을 HCL 내부에서 처리할 수 있게 만듭니다. PR #39153 예시는 `source = "app.terraform.io/${var.organization}/random"` 형태를 보여줍니다.[^2]

이 조합에서 신경 쓸 포인트는 두 가지입니다.

- provider 주소(hostname/namespace/type)가 바뀌면 lock file entry도 바뀝니다.[^7]
- private registry는 토큰/권한이 엮이므로, 실행 주체(로컬/CI/HCP run)별로 자격증명 체계를 문서화해야 합니다. private registry 개요 문서도 이걸 전제로 깔고 있습니다.[^8]

### 4) 플러그인 캐시/미러: “속도 최적화”의 우선순위 재정렬

`-minimal-refresh`는 plan 단계의 원격 API 호출을 줄여줍니다. 반면, provider 다운로드 자체가 병목인 조직도 많습니다.

Terraform CLI config에서 `plugin_cache_dir`로 플러그인 캐시를 켤 수 있습니다.[^16]

여기서 문서가 경고하는 부분을 그대로 운영 기준으로 옮겨야 합니다.

- plugin cache는 concurrency safe가 보장되지 않고, 여러 `terraform init`가 동시에 돌면 동작이 정의되지 않는다고 되어 있습니다.[^16]

따라서 CI에서 캐시를 쓰려면 아래 중 하나를 선택해야 합니다.

- runner 단위로 격리된 캐시 디렉토리
- init 단계에 전용 락(예: 파일 락, job mutex)
- 아예 filesystem mirror 방식으로 내려받은 provider를 배포하고, `direct`를 차단

provider 설치/플러그인 운영은 CLI config 문서와 plugins 문서에 정리돼 있습니다.[^16]

특히 air-gapped에 가까운 환경이면 `terraform providers mirror`로 필요한 provider를 미리 내려받는 방법이 공식 문서에 있습니다.[^17]

### 5) 실행 권한(Execution permission): drift 탐지와 변경 적용을 분리하는 권한 모델

`-minimal-refresh`를 적극적으로 쓰면, drift 탐지는 별도 job으로 분리됩니다. 이때 권한 모델도 분리하는 편이 안전합니다.

- drift 탐지 job: read-only credential로 `plan -refresh-only`
- apply job: write credential로 apply

HCP Terraform drift detection도 refresh-only plan을 기반으로 동작한다는 점에서 같은 모델입니다.[^13]

이 분리의 부작용은 하나 있습니다.

- drift 탐지 job이 상태를 업데이트할지(예: `apply -refresh-only`) 아니면 보고만 할지 결정해야 합니다. drift 튜토리얼은 refresh-only apply가 state를 갱신하지만 인프라를 바꾸지 않는다는 점을 강조합니다.[^12]

조직마다 답이 다른데, 나는 운영 경험상 “보고”와 “state 갱신”도 분리하는 편이 덜 위험했습니다. state를 바꾸는 행위는 결국 이후 plan/apply의 기반을 바꾸기 때문입니다.

### 6) 파이프라인 단계별 추천 조합

아래는 v1.17 이후 계약을 의식해서 짜는 조합입니다.

- PR plan(속도 우선): `terraform plan -minimal-refresh`
- main merge 검증(정합성 우선): `terraform plan` (full refresh)
- drift 탐지(변경 금지): `terraform plan -refresh-only` (+ exit code 기반 자동판단)
- provider 업그레이드 PR: `-minimal-refresh` 금지, full refresh plan 강제[^3]

이 흐름은 예전에 import/panic 버그 같은 “예외 상황을 pipeline에서 방어”하자는 기조와도 잘 맞습니다. plan 단계가 더 빨라질수록, 예외 상황을 다루는 방어선은 더 앞단(입력/정책/테스트)으로 당겨야 합니다.

- [Terraform 1.16.1 import/panic 버그와 IaC 파이프라인 방어](https://daewooki.github.io/posts/terraform-import-panic-pipeline-guardrails/)

## 도입 판단 기준: 무엇을 먼저 실험하고 무엇을 늦출지

### required_providers 변수화는 “표준화” 목적이 명확할 때만

이 기능을 쓰는 이유가 “할 수 있으니까”가 되면, 모듈 재사용성이 떨어집니다. 반대로 아래 목적이 분명하면 가치가 큽니다.

- 조직이 provider 공급망을 private registry로 통제하고, 동일 코드를 여러 실행 환경(로컬/CI/HCP)에서 같은 방식으로 돌려야 한다
- wrapper/템플릿 레이어를 줄이고, Terraform core 기능으로 흡수하고 싶다

이 경우에도, 변수화 범위를 최소화하는 편이 낫습니다.

- source만 변수화하고 version은 lock file로 고정하는 쪽이 사고가 덜 납니다.

### -minimal-refresh는 “plan 비용”과 “drift 센서”의 트레이드오프를 인정할 때만

`-minimal-refresh`는 분명히 비용을 줄이지만, 문서가 명시하는 대로 drift를 무시할 수 있습니다.[^3] 이걸 수용하려면 drift 탐지 루틴이 독립적으로 있어야 합니다.

조직이 HCP Terraform drift detection을 쓴다면 이미 길이 있습니다.[^13] CLI 기반이면 refresh-only plan을 스케줄링하는 것이 최소선입니다.[^12]

두 기능 모두 결론은 같습니다.

- init/plan을 빠르게 만들수록, 운영 계약은 더 명시적으로 분리되고(변경 vs 정합성), 리뷰 범위는 코드에서 입력과 실행 컨텍스트로 확장됩니다.

## 참고 자료

- [Terraform v1.17.0-rc2 릴리스 노트 (GitHub Releases)](https://github.com/hashicorp/terraform/releases?after=v0.9.11)
- [PR #39153 Implement dynamic provider sources](https://github.com/hashicorp/terraform/pull/39153)
- [PR #38953 plan: Introduce -minimal-refresh flag](https://github.com/hashicorp/terraform/pull/38953)
- [terraform plan 명령 레퍼런스 (-minimal-refresh, -refresh-only)](https://developer.hashicorp.com/terraform/cli/commands/plan)
- [Input variables 문서 (const 변수)](https://developer.hashicorp.com/terraform/language/values/variables)
- [variable 블록 레퍼런스 (const 설명)](https://docs.hashicorp.com/terraform/language/block/variable)
- [Dependency Lock File (.terraform.lock.hcl)](https://developer.hashicorp.com/terraform/language/files/dependency-lock)
- [Terraform CLI configuration file (plugin_cache_dir, provider_installation)](https://docs.hashicorp.com/terraform/cli/config/config-file)
- [Manage Terraform plugins / terraform providers mirror](https://docs.hashicorp.com/terraform/cli/plugins)
- [Manage resource drift (refresh-only)](https://docs.hashicorp.com/terraform/tutorials/state/resource-drift)
- [HCP Terraform drift detection과 refresh-only plan](https://developer.hashicorp.com/terraform/tutorials/cloud/drift-and-policy)
- [HCP Terraform private registry 개요](https://developer.hashicorp.com/terraform/registry/private)
- [terraform providers 명령 레퍼런스 (-var, -var-file)](https://developer.hashicorp.com/terraform/cli/commands/providers)
- [Issue #39172 drift 전용 커맨드 논의](https://github.com/hashicorp/terraform/issues/39172)

[^1]: <https://github.com/hashicorp/terraform/releases?after=v0.9.11>
[^2]: <https://github.com/hashicorp/terraform/issues/39153>
[^3]: <https://developer.hashicorp.com/terraform/cli/commands/plan>
[^4]: <https://developer.hashicorp.com/terraform/language/block/terraform>
[^5]: <https://developer.hashicorp.com/terraform/language/providers/requirements>
[^6]: <https://docs.hashicorp.com/terraform/language/block/variable>
[^7]: <https://developer.hashicorp.com/terraform/language/files/dependency-lock>
[^8]: <https://developer.hashicorp.com/terraform/registry/private>
[^9]: <https://developer.hashicorp.com/terraform/cli/commands/providers>
[^10]: <https://developer.hashicorp.com/terraform/language/values/variables>
[^11]: <https://github.com/hashicorp/terraform/pull/38953>
[^12]: <https://docs.hashicorp.com/terraform/tutorials/state/resource-drift>
[^13]: <https://developer.hashicorp.com/terraform/tutorials/cloud/drift-and-policy>
[^14]: <https://github.com/hashicorp/terraform/issues/39172>
[^15]: <https://support.hashicorp.com/hc/en-us/articles/4416764686611-Using-Terraform-Variable-Definition-Files-in-Terraform-Cloud-Enterprise>
[^16]: <https://docs.hashicorp.com/terraform/cli/config/config-file>
[^17]: <https://docs.hashicorp.com/terraform/cli/plugins>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
