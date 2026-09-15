---
title: "Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다"
description: "1.16.2는 작은 패치처럼 보이지만, 팀 단위 IaC 파이프라인에서는 lockfile·plan 재현성·import/state 감시·롤백을 묶어 업그레이드 윈도우를 설계해야 합니다."
date: 2026-09-15 10:10:21 +0900
categories: ["News", "Infrastructure"]
tags: ["terraform", "iac", "upgrade-checklist", "provider-lockfile", "plan-reproducibility", "rollback"]
render_with_liquid: false
---

## 2026-09-09에 나온 Terraform 1.16.2가 의미하는 것
Terraform 1.16.2는 2026-09-09에 릴리스된 1.16 라인의 patch 릴리스이고, 릴리스 노트 상으로는 **모듈 설치 과정에서 invalid module call을 만났을 때 panic이 발생하던 문제**를 고친 것이 전부입니다.[^1]

이 한 줄이 팀 단위 IaC 파이프라인에서는 작지 않습니다. 운영에서 Terraform 업그레이드가 막히는 지점은 대개 “새 기능이 필요해서”가 아니라 “init/plan이 CI에서 가끔 죽어서”입니다. patch 릴리스의 버그픽스가 업그레이드 윈도우를 다시 여는 순간은, 해당 버그가 파이프라인의 실패 모드에 직접 연결될 때입니다.

여기서 말하는 업그레이드 윈도우는 단순히 `required_version`을 올리는 PR을 의미하지 않습니다. 다음을 동시에 만족해야 팀이 한 번에 넘어갈 수 있습니다.

- provider/plugin이 어떤 머신에서 돌려도 같은 바이너리를 잡는가
- 같은 커밋을 같은 변수로 plan했을 때 결과가 재현되는가
- import block이 state를 바꾸는 이벤트를 가시화하고 있는가
- 문제가 생겼을 때 롤백이 “가능”이 아니라 “실제로 해본 절차”로 준비돼 있는가

결국 1.16.2 자체보다도, 1.16 라인으로 표준화 결정을 내릴 수 있는지의 문제입니다.

## 1.16.0~1.16.2에서 팀 파이프라인에 걸리는 변화
1.16.2 얘기를 하려면 1.16.0과 1.16.1을 같이 봐야 합니다. 팀이 1.16.2로 올린다는 말은, 실제로는 “1.16.0에서 들어온 변화들을 운영에 들인다”는 뜻이기 때문입니다.

- 1.16.0에서 `import` blocks inside modules가 지원됐습니다.[^2]
- 1.16.1에서 `for_each`/`count`로 여러 instance에 import를 걸 때 일부 import block이 무시되던 버그가 수정됐습니다. 그리고 import identity가 sensitive value를 참조할 때의 panic, `state show` panic, `create_before_destroy` ordering 이슈 등이 함께 정리됐습니다.[^3]
- 1.16.2는 모듈 설치(module installation) 쪽 panic을 추가로 정리했습니다.[^1]

내 경우 업그레이드 판단에서 1.16.1의 import 관련 버그픽스가 핵심이었고, 1.16.2는 “init/모듈 설치가 터지면 파이프라인 전체가 무너진다”는 관점에서 마지막 걸림돌을 하나 더 제거한 릴리스로 읽힙니다.

## 버전 고정만으로는 부족한 이유: Terraform에서 고정해야 하는 것은 4겹이다
Terraform 업그레이드에서 흔히 나오는 결론이 “Terraform 버전 고정합시다”인데, 이것만으로는 팀 파이프라인이 안정화되지 않습니다. Terraform은 core binary 하나로 끝나는 도구가 아니라, 실행 결과가 다음 요소에 의해 함께 결정됩니다.

1) Terraform CLI(binary) 자체

2) provider 바이너리(플러그인)와 그 체크섬

3) provider 설치 경로(Registry/Mirror/Plugin cache)와 동시성

4) plan 결과를 소비하는 주변 툴링(JSON 파서, CI 래퍼, drift 감시기)

실제로 파이프라인을 흔드는 이슈는 “버전이 달라서”가 아니라 “같은 버전인데도 plan이 달라져서” 혹은 “같은 lockfile인데 init이 다른 바이너리를 잡아서” 쪽에서 많이 나옵니다.

특히 provider는 registry에서 내려받는 바이너리이고, Terraform은 설치 과정에서 서명/체크섬 검증을 수행합니다. provider가 어떻게 배포되고 어떤 메타데이터(체크섬/서명 URL)를 제공해야 하는지도 프로토콜로 정의돼 있습니다.[^4]

그리고 plugin cache를 켜면 속도는 빨라지지만, 문서에 명시적으로 “concurrency safe가 보장되지 않는다”고 되어 있습니다. 여러 CI job이 같은 cache 디렉터리를 동시에 건드리는 순간, 재현성 이슈를 ‘내가 만든 적 없는’ 방식으로 만들 수 있습니다.[^5]

결론적으로, 버전 고정의 최소 단위는 이렇습니다.

- Terraform 버전 고정
- `.terraform.lock.hcl` 고정 + readonly 강제
- provider 설치 소스(직접 Registry를 쓸지, mirror를 쓸지, cache를 공유할지) 고정
- plan 아티팩트(또는 plan JSON) 비교로 재현성 테스트 자동화

## 업그레이드 전 체크리스트(팀 표준화 관점)
아래는 1.16.2로 올리기 전, 파이프라인 관점에서 먼저 잠그는 항목들입니다.

### 1) Terraform CLI 공급망 검증: “설치했다”가 아니라 “검증했다”
팀 표준화는 개인 노트북 설치가 아니라 CI 이미지/런타임에 들어가는 바이너리로 결정됩니다.

HashiCorp 문서는 Terraform 설치 시 SHA256SUMS와 서명 파일을 검증할 수 있다고 안내합니다.[^6] 또한 별도의 튜토리얼에서 체크섬 파일과 서명(sig) 파일을 내려받아 검증하는 흐름을 설명합니다.[^7]

릴리스 서버에는 1.16.2 디렉터리와 체크섬/서명 파일이 함께 올라옵니다(예: `terraform_1.16.2_SHA256SUMS`, `terraform_1.16.2_SHA256SUMS.sig`).[^8]

운영에선 다음 중 하나로 고정하는 편이 결과적으로 사고가 덜 납니다.

- (권장) CI용 컨테이너 이미지에 Terraform 1.16.2 바이너리를 포함시키고, 이미지를 digest로 고정
- (차선) 파이프라인 초입에서 바이너리 다운로드 + 체크섬/서명 검증을 수행하고 캐시(artifacts)로 재사용

여기서 중요한 점은 1.16.2로 “올리는 것”보다, 누가 어디에서 실행하든 같은 바이너리를 실행한다는 사실을 확보하는 것입니다.

### 2) provider lockfile을 “readonly로 강제”할 준비
업그레이드 PR에서 lockfile이 같이 변하면 리뷰가 어려워집니다. 반대로 lockfile을 고정하지 않으면, 같은 Terraform 버전에서도 init 시점에 provider 선택이 흔들릴 수 있습니다.

여기서 실무적으로 중요한 체크는 두 가지입니다.

- `.terraform.lock.hcl`이 repo에 커밋되어 있는가
- CI에서 `terraform init`를 `-lockfile=readonly`로 돌리고 있는가

이 조합이 있어야 “우연히 lockfile이 갱신돼서” plan이 바뀌는 일이 사라집니다.

추가로 1.16.0 릴리스 노트에 `terraform init`에서 `-upgrade`와 `-lockfile=readonly`가 함께 들어가 충돌할 때 더 이른 시점에 에러를 내도록 개선했다는 내용이 있습니다.[^2] 이건 파이프라인에서 잘못된 플래그 조합이 더 빨리 터져서 문제를 빨리 발견하게 해주지만, 동시에 “예전엔 넘어가던 스크립트가 이제 실패한다”로 보일 수 있습니다. 업그레이드 전에 CI 스크립트에서 플래그 조합을 점검하는 이유입니다.

### 3) multi-platform lock 전략: macOS 개발자와 Linux CI가 섞여 있으면 필수
`.terraform.lock.hcl`에는 플랫폼별 체크섬이 들어가고, 팀이 macOS와 Linux를 섞어 쓰면 lockfile이 플랫폼에 의해 계속 변동할 수 있습니다.

이 문제를 정면으로 해결하려면, 팀이 지원하는 플랫폼을 정하고 `terraform providers lock`로 플랫폼들을 함께 잠그는 쪽으로 가야 합니다. (예: `linux_amd64`, `darwin_arm64`, `darwin_amd64`)

업그레이드 전 체크리스트에 “우리 팀 lockfile이 어떤 플랫폼을 포함해야 하는가”를 명시하지 않으면, lockfile PR이 끝없이 흔들립니다.

### 4) plugin cache를 켜는지/어떻게 공유하는지 결정
plugin cache는 속도를 크게 올리지만, 문서에 **동시성 안전이 보장되지 않는다**고 되어 있습니다.[^5]

내가 본 실패 모드는 보통 이렇습니다.

- 여러 job이 같은 `TF_PLUGIN_CACHE_DIR`를 공유
- 동시에 `terraform init`가 실행
- 한 job이 아직 쓰는 중인 파일을 다른 job이 건드리거나, partially-written 바이너리를 집어 듦
- 결과는 init 실패(다운로드/검증 실패) 또는 더 미묘하게는 “어떤 job만 plan이 다르게 나옴”

팀이 cache를 쓰려면 다음 중 하나로 정리하는 편이 덜 고통스럽습니다.

- job 단위로 고유한 cache 디렉터리를 두고(예: workspace 경로 아래), cache 공유를 포기하고 재현성을 택함
- cache를 공유하되, init 실행을 serialize하거나(현실적으로 어렵습니다), cache 계층을 Artifact store로 대체

이 결정을 업그레이드 전에 고정하지 않으면 “버전 업그레이드”가 아니라 “캐시 운영 방식 변경”이 섞여 들어가서 원인 분석이 어려워집니다.

### 5) plan 재현성 테스트: plan이 같아야 apply도 통제된다
Terraform은 사람이 읽는 출력은 언제든 바뀔 수 있다고 문서에서 분명히 말합니다. 예를 들어 `terraform output`도 기본 human-readable 출력은 바뀔 수 있으니 자동화에서는 `-json`을 쓰라고 안내합니다.[^9]

plan도 마찬가지입니다. 팀이 plan을 PR 코멘트로 붙여서 리뷰하는 동안, 실제 안전장치는 “human-readable 텍스트”가 아니라 plan artifact(바이너리 `-out`) 또는 그 JSON 표현입니다. Terraform은 `terraform show -json`으로 plan 파일을 JSON으로 표현할 수 있고, JSON 형식에는 `format_version`이 포함되며 버전 정책(major/minor)도 정의돼 있습니다.[^10]

업그레이드 전에는 최소한 아래를 자동화로 확인해야 합니다.

- 같은 commit, 같은 변수로 plan을 2번 돌려도 `resource_changes`가 같은가
- `.terraform` 디렉터리를 지우고 init부터 다시 해도 같은 결과가 나오는가
- provider lockfile을 readonly로 강제했을 때도 같은 결과가 나오는가

이걸 통과하지 못하면, 업그레이드는 “버전만 올림”이 아니라 “plan 재현성 문제를 버전 문제로 착각”하는 상태가 됩니다.

### 6) import block / 상태 변동 감시: import는 코드 변경이 아니라 state 변경이다
Terraform 문서는 import가 “같은 객체를 여러 번 import하면 원치 않는 동작”이 나올 수 있다고 경고합니다.[^11]

`import` block은 더 위험합니다. 장점은 plan/apply workflow 안에 import가 들어오면서 리뷰와 감사가 쉬워진다는 점이지만, 동시에 다음이 가능합니다.

- PR이 merge되면, apply 시점에 state가 구조적으로 바뀜
- 그 순간 drift 감시/정책 평가/정적 분석기의 기준이 바뀔 수 있음

그리고 1.16.1에서 실제로 `for_each`/`count` 다중 instance import에서 일부 import block이 무시되는 버그가 있었고, 이게 1.16.1에서 고쳐졌습니다.[^3] 즉 1.16 라인을 쓴다는 건 import block을 적극적으로 쓰는 팀에게 특히 “state 변동 이벤트”를 파이프라인에서 감시해야 한다는 뜻입니다.

이 단계에서 필요한 것은 원칙적으로 두 가지입니다.

- import 전/후의 `terraform state pull` 결과를 아티팩트로 남기고 diff를 남김
- import block을 apply 이후 제거하는 기준을 팀 규칙으로 둠(계속 남겨두면 다음 plan에서 계속 평가됩니다)

### 7) 롤백 전략: “이전 버전으로 다시 plan만 해도 되는가”를 먼저 확인
Terraform 업그레이드의 롤백은 단순히 바이너리를 내리는 문제가 아닙니다.

- 이미 새로운 Terraform로 state가 기록됐는가
- import block이 state를 이동시켰는가
- 1.16.0에서 들어온 기능(예: modules 안의 import block)을 사용했는가[^2]

이 조건에 따라 “구버전이 state를 읽고 plan할 수 있는지”가 달라집니다. 그래서 롤백은 항상 다음 두 가지로 분리됩니다.

- (빠른 롤백) apply를 멈추고, CI에서 plan만 구버전으로 되돌림
- (무거운 롤백) state 자체를 백업에서 복원하거나, moved/import에 의해 바뀐 주소 체계를 되돌림

실무에서는 빠른 롤백만 가능한 상태로 업그레이드를 시작하는 경우가 많은데, import가 섞이면 빠른 롤백이 성립하지 않는 케이스가 늘어납니다.

## 업그레이드 후 체크리스트(1.16.2 반영 이후)
업그레이드 후 체크리스트는 “적용이 끝났다”가 아니라 “다음 업그레이드까지 흔들리지 않게 잠근다”에 가깝습니다.

### 1) init을 항상 같은 조건으로 실행하도록 표준화
- `terraform init -lockfile=readonly`를 기본값으로 박아 두고
- lockfile을 갱신해야 하는 파이프라인은 별도의 수동 job(또는 별도 repo)로 분리

이렇게 나누면, lockfile 변경이 일어나는 이벤트가 명확해지고 감사가 쉬워집니다.

또한 plugin cache를 쓰는 경우, cache 디렉터리 정책(공유 범위, 보관 기간, cleanup)을 문서가 아니라 코드(파이프라인 스크립트)로 고정하는 편이 결과가 좋습니다.[^5]

### 2) plan artifact를 보관하고, JSON으로 요약해 diff를 남긴다
`terraform show -json`은 plan/state를 JSON으로 표현할 수 있고, 그 JSON 형식의 버전 정책도 문서로 정의돼 있습니다.[^10]

내가 권하는 방식은 “plan 바이너리와 plan 요약 JSON을 동시에 남기는 것”입니다.

- plan 바이너리(`-out=tfplan`)는 apply 검증에 쓸 수 있고
- 요약 JSON은 PR diff로 사람이 보고, 머신이 비교할 수 있습니다.

이게 있어야 “업그레이드 이후 어느 날 plan이 달라졌다”를 재현할 수 있습니다.

### 3) import가 들어간 PR은 state diff를 기본 산출물로 둔다
import는 코드가 아니라 state의 사실을 바꾸는 작업이기 때문에, PR 산출물을 다음처럼 강제하는 편이 낫습니다.

- 변경 전 `terraform state pull` → `state.before.json`
- apply 후 `terraform state pull` → `state.after.json`
- `jq -S`로 정렬 후 diff

Terraform 문서가 import를 조심하라고 경고하는 이유는, Terraform이 원래 “각 remote object는 하나의 주소에만 바인딩된다”는 가정을 깔고 있기 때문입니다.[^11]

### 4) JSON을 파싱하는 주변 툴링의 내구성을 점검
1.16.2 자체는 JSON 출력 변경을 말하지 않지만, 바로 다음 prerelease에서 JSON output에 `format_version` 필드가 추가된다는 노트가 이미 등장했습니다.[^2] 그리고 `terraform-json` 라이브러리 쪽에도 `format_version` 필드가 추가된 흔적이 있습니다.[^12]

Terraform JSON 포맷 문서는 unknown field를 무시해 forward-compatible하게 만들라고 명시합니다.[^10] 그런데 조직 내부 툴이 `jq '.terraform_version'` 같은 형태로 느슨하게 파싱하는 게 아니라, struct strict decoding을 해버리면 새 필드 하나에 파이프라인이 깨집니다.

업그레이드 후 체크리스트에 “JSON 파서가 unknown field에 안전한가”를 넣는 이유가 여기 있습니다.

## 반론과 회의론: patch 릴리스인데 이렇게까지 해야 하나
1.16.2의 릴리스 노트만 보면 “panic 하나 고친 릴리스”입니다.[^1] 그래서 다음과 같은 반론이 나옵니다.

- patch는 위험이 낮으니 바로 올리자
- 어차피 `required_version`만 고정하면 된다
- provider는 각 팀이 알아서 고정하면 된다

문제는 팀 단위 IaC에서 위험이 “릴리스 노트에 있는 breaking change”로만 오지 않는다는 점입니다.

- init이 어떤 바이너리를 설치했는지 재현이 안 되면, 동일한 커밋에서 plan이 달라집니다.
- import는 코드 변경이 아니라 state 모델 자체를 바꾸는 작업입니다. Terraform 문서도 동일 객체를 중복 import하지 말라고 경고합니다.[^11]
- plugin cache는 편하지만 동시성 안전이 보장되지 않습니다.[^5]

즉 위험의 대부분은 Terraform core 버전이 아니라, **업그레이드 과정에서 파이프라인이 흔들리며 드러나는 비결정성**에서 나옵니다. 1.16.2를 계기로 업그레이드 윈도우를 열자는 말은 “이제 1.16 라인을 올려도 된다”가 아니라 “올리려면 올릴 수 있는 상태를 만들자”에 가깝습니다.

## 앞으로 지켜볼 것: 1.16 라인을 올린 팀이 다음으로 마주칠 변화
1.16.2 이후에 현실적으로 다음을 지켜보게 됩니다.

### JSON output의 진짜 버전 협상
Terraform JSON 포맷은 `format_version`을 통해 major/minor 정책을 갖고, unknown field 무시를 요구합니다.[^10] 1.17.0-beta1 노트에서 JSON output에 `format_version` 필드가 추가된다는 언급은, 주변 도구가 버전 협상을 진지하게 해야 한다는 신호입니다.[^2]

### import block의 확산과 운영 규칙
1.16.0에서 modules 안에 import block을 둘 수 있게 되면서[^2], import는 더 이상 “일회성 작업을 위해 사람 손으로 state를 만지는 행위”가 아니라 “코드로 리뷰 가능한 state 변경”으로 넘어갑니다.

좋은 방향이지만, 그만큼 운영 규칙이 필요해집니다.

- import block을 어디에 두는가(`imports.tf`로 모을지, resource 옆에 둘지)는 문서에서도 권장 패턴이 언급됩니다.[^13]
- HCP Terraform을 쓸 때는 `terraform import`가 로컬에서 실행되어 remote workspace 변수에 접근하지 못할 수 있다는 제약도 문서에 있습니다.[^14]

## 파이프라인 템플릿: lockfile/plan 재현성/import/state/롤백을 한 덩어리로 묶기
아래 예시는 실제로 실행 가능한 형태로 “업그레이드 윈도우”를 구성하는 스캐폴딩입니다. 클라우드 자격 증명 없이도 재현성/lockfile/import/state diff의 골격을 확인할 수 있도록 `local` provider를 사용합니다.

- 의도: (1) module 안에 있는 리소스를 import 주소로 가리키고, (2) plan JSON을 요약해서 재현성 검사를 돌리고, (3) state pull diff를 남깁니다.
- 주의: 이 예시는 local 파일을 사용하지만, 팀 파이프라인에서 필요한 검증(재현성/readonly lock/state diff)은 클라우드 리소스에서도 동일합니다.

### 디렉터리 구조

```text
.
├─ modules/
│  └─ app-config/
│     ├─ main.tf
│     └─ variables.tf
├─ envs/
│  └─ prod/
│     ├─ main.tf
│     ├─ versions.tf
│     └─ imports.tf
└─ ci/
   ├─ plan_twice_and_compare.sh
   └─ state_diff.sh
```

### Terraform 구성: module 리소스를 대상으로 import block을 걸기
HashiCorp 문서에 따르면 `import` block은 `to`/`id` 등을 지원하고, `imports.tf` 같은 파일로 모으거나 리소스 옆에 두는 패턴을 권장합니다.[^13]

`modules/app-config/main.tf`

```hcl
terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

resource "local_file" "service_config" {
  for_each = var.services

  filename = "${var.out_dir}/${each.key}.conf"
  content  = <<-EOT
  service_name = ${each.key}
  port         = ${each.value.port}
  owner        = ${each.value.owner}
  EOT
}
```

`modules/app-config/variables.tf`

```hcl
variable "out_dir" {
  type = string
}

variable "services" {
  type = map(object({
    port  = number
    owner = string
  }))
}
```

`envs/prod/versions.tf`

```hcl
terraform {
  required_version = "= 1.16.2"
}
```

`envs/prod/main.tf`

```hcl
module "app_config" {
  source = "../../modules/app-config"

  out_dir = "${path.module}/out"

  services = {
    api = {
      port  = 8080
      owner = "platform"
    }
    worker = {
      port  = 9090
      owner = "platform"
    }
  }
}
```

`envs/prod/imports.tf`

```hcl
# 기존에 이미 존재하는 파일(out/api.conf)을 state로 끌어들이는 시나리오.
# import block은 plan/apply workflow로 import를 포함시킬 수 있습니다.

import {
  to = module.app_config.local_file.service_config["api"]
  id = "${path.module}/out/api.conf"
}
```

`local_file`의 import ID는 파일 경로입니다(리소스별로 import ID 의미는 provider가 정의합니다). 이 예시는 “기존 파일이 이미 배포돼 있는데 Terraform state만 없는” 상황을 최소한으로 모사합니다.

### 실행 준비

```bash
# Terraform working dir
cd envs/prod

# (예시) 기존 파일을 먼저 만들어 두고, 이후 import로 state에 편입
mkdir -p out
cat > out/api.conf <<'EOF'
service_name = api
port         = 8080
owner        = platform
EOF
```

### init은 lockfile을 생성하되, 이후에는 readonly로 잠근다
plugin cache를 쓸지 여부는 팀 표준으로 결정해야 하고, plugin cache의 동시성 안전이 보장되지 않는다는 점을 알고 있어야 합니다.[^5]

```bash
# 최초 1회: lockfile 생성
terraform init

# 이후: 파이프라인 표준(읽기 전용)
terraform init -lockfile=readonly
```

### plan/apply와 import의 결합

```bash
# plan artifact 생성
terraform plan -out=tfplan.bin

# JSON으로 요약(terraform show -json은 JSON format 문서에 정의된 형태를 따릅니다)
terraform show -json tfplan.bin > tfplan.json
```

Terraform JSON 출력 형식은 문서로 정의되어 있고, `format_version`의 major/minor 정책도 명시돼 있습니다.[^10]

apply까지 수행하면 import가 반영되어 `api.conf`가 state에 편입됩니다.

```bash
terraform apply tfplan.bin
```

apply 이후에는 import block을 제거하는 정책을 두는 편이 운영에서 안전합니다. import block이 남아 있으면 다음 plan에서 계속 평가되며, import 대상이 이미 state에 있을 때의 동작은 팀의 기대와 엇갈릴 수 있습니다(문서가 “동일 객체 중복 import”의 위험을 경고하는 이유).[^11]

### plan 재현성 검사(같은 커밋에서 plan이 두 번 같아야 한다)
`ci/plan_twice_and_compare.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

workdir="${1:-envs/prod}"

tmp1="$(mktemp -d)"
tmp2="$(mktemp -d)"

cleanup() {
  rm -rf "$tmp1" "$tmp2"
}
trap cleanup EXIT

copy_tree() {
  local dst="$1"
  mkdir -p "$dst"
  rsync -a --delete ./ "$dst" >/dev/null
}

run_plan() {
  local dir="$1"
  pushd "$dir/$workdir" >/dev/null

  terraform init -lockfile=readonly -no-color >/dev/null
  terraform plan -out=tfplan.bin -no-color >/dev/null

  terraform show -json tfplan.bin \
    | jq -S '{
        format_version,
        terraform_version,
        resource_changes: [.resource_changes[]? | {
          address,
          mode,
          type,
          name,
          index,
          change: {
            actions,
            before,
            after,
            after_unknown
          }
        }]
      }' \
    > plan.summary.json

  cat plan.summary.json

  popd >/dev/null
}

copy_tree "$tmp1"
copy_tree "$tmp2"

p1="$(run_plan "$tmp1")"
p2="$(run_plan "$tmp2")"

if diff -u <(echo "$p1") <(echo "$p2") >/dev/null; then
  echo "OK: plan is reproducible"
else
  echo "ERROR: plan differs between identical runs" >&2
  diff -u <(echo "$p1") <(echo "$p2") >&2
  exit 1
fi
```

이 스크립트는 “두 번의 plan 결과에서 사람에게 중요한 부분(리소스 변경)이 같은가”를 비교합니다. 여기서 plan이 흔들리면, 업그레이드 후에 파이프라인이 비결정적으로 실패하거나 리뷰가 무의미해질 가능성이 큽니다.

### import/state 변동 감시(변경 전/후 state pull diff)
`ci/state_diff.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

workdir="${1:-envs/prod}"

pushd "$workdir" >/dev/null

terraform init -lockfile=readonly -no-color >/dev/null

terraform state pull | jq -S . > state.before.json

terraform plan -out=tfplan.bin -no-color >/dev/null
terraform apply -auto-approve tfplan.bin -no-color >/dev/null

terraform state pull | jq -S . > state.after.json

diff -u state.before.json state.after.json || true

popd >/dev/null
```

이 diff는 import가 실제로 어떤 경로/주소를 state에 추가했고 어떤 속성이 기록됐는지 남기는 역할을 합니다.

## 1.16.2 업그레이드를 “지금” 판단해야 하는 이유를 기술적으로 해석하면
2026-09-15(KST) 시점에서 1.16.2는 릴리스(2026-09-09) 후 7일 이내이고[^1], 팀 단위 표준화는 보통 다음 이벤트에 의해 강제됩니다.

- 누군가 로컬에서 1.16.x를 이미 사용하기 시작함(특히 1.16.0에서 import/modules 같은 기능을 써버리면 되돌리기 어렵습니다)[^2]
- import block 관련 버그나 panic 회피 때문에 patch로 계속 미뤄야 하는데, 1.16.2에서 init 계열 panic이 정리되며 최소 기준이 생김[^1]

그래서 팀은 “올릴지 말지”가 아니라 “올리되 어떤 윈도우 설계로 올릴지”를 빠르게 결정해야 합니다. 그리고 그 설계의 핵심이 lockfile, plan 재현성, import/state 감시, 롤백입니다.

내 결론은 단순합니다. 1.16.2는 기능 릴리스가 아니라, 1.16 라인으로 표준화할 때 파이프라인 실패 모드를 하나 더 줄여주는 릴리스이며, 이 시점의 업그레이드는 버전 숫자를 올리는 작업이 아니라 업그레이드 윈도우 자체를 프로세스로 고정하는 작업입니다.

## 참고 자료
- [Terraform v1.16.2 릴리스 노트(GitHub Release)](https://github.com/hashicorp/terraform/releases/tag/v1.16.2)
- [Terraform v1.16.1 릴리스 노트(GitHub Release)](https://github.com/hashicorp/terraform/releases/tag/v1.16.1)
- [Terraform 릴리스 목록(GitHub Releases)](https://github.com/hashicorp/Terraform/releases)
- [Terraform Install 문서](https://developer.hashicorp.com/terraform/install)
- [Terraform 릴리스 서버 디렉터리](https://releases.hashicorp.com/terraform/)
- [Terraform archive 검증 튜토리얼](https://docs.hashicorp.com/terraform/tutorials/cli/verify-archive)
- [Terraform CLI configuration: plugin cache 문서](https://docs.hashicorp.com/terraform/cli/config/config-file)
- [Terraform JSON output format 문서](https://developer.hashicorp.com/terraform/internals/json-format)
- [Terraform import 개요](https://developer.hashicorp.com/terraform/cli/import)
- [Terraform import command 문서](https://developer.hashicorp.com/terraform/cli/commands/import)
- [Terraform import block reference](https://developer.hashicorp.com/terraform/language/block/import)
- [Plugin signatures 문서](https://developer.hashicorp.com/terraform/cli/plugins/signing)
- [Provider registry protocol reference](https://docs.hashicorp.com/terraform/internals/provider-registry-protocol)
- [Terraform 1.16.1 import/panic 버그와 IaC 파이프라인 방어](https://daewooki.github.io/posts/terraform-import-panic-pipeline-guardrails/)
- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)

[^1]: <https://github.com/hashicorp/terraform/releases/tag/v1.16.2>
[^2]: <https://github.com/hashicorp/Terraform/releases>
[^3]: <https://github.com/hashicorp/terraform/releases/tag/v1.16.1>
[^4]: <https://docs.hashicorp.com/terraform/internals/provider-registry-protocol>
[^5]: <https://docs.hashicorp.com/terraform/cli/config/config-file>
[^6]: <https://developer.hashicorp.com/terraform/install>
[^7]: <https://docs.hashicorp.com/terraform/tutorials/cli/verify-archive>
[^8]: <https://releases.hashicorp.com/terraform/>
[^9]: <https://docs.hashicorp.com/terraform/cli/commands/output>
[^10]: <https://developer.hashicorp.com/terraform/internals/json-format>
[^11]: <https://developer.hashicorp.com/terraform/cli/import/usage>
[^12]: <https://github.com/hashicorp/terraform-json/blob/main/version.go>
[^13]: <https://developer.hashicorp.com/terraform/language/block/import>
[^14]: <https://developer.hashicorp.com/terraform/cli/import>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
