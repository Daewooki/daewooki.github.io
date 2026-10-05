---
title: "Terraform plan JSON: format_version 계약과 소비자 테스트"
description: "Terraform 1.16.3 이후, plan/show JSON을 파싱하는 내부 도구가 깨지지 않게 format_version을 계약으로 다루는 방식과 계약 테스트 설계를 정리합니다."
date: 2026-10-05 13:35:36 +0900
categories: ["Infrastructure", "Terraform"]
tags: ["terraform", "iac", "contract-testing", "ci-cd", "json-schema", "infra-pipeline"]
render_with_liquid: false
---

## plan/json 소비자가 실제 인터페이스가 되는 순간
Terraform CLI 업그레이드는 보통 `required_version`과 바이너리 교체로 끝납니다. 반면 조직 내부의 리뷰 봇, 정책 엔진, 비용 산정기 같은 도구는 한 번 만들어지면 수년간 “조용히” 파이프라인에 붙어 있습니다. 이 부류는 Terraform의 출력(JSON)을 사실상 공개 API처럼 소비합니다.

Terraform 1.16.3(2026-09-16) 릴리스 노트에는 `format_version`을 언급하면서 “소비자가 주의해야 한다”는 취지의 메시지가 들어갔습니다. 릴리스 노트의 문맥은 `terraform version -json`에 `format_version` 필드를 추가한 변경이지만(즉, *plan JSON 그 자체의 필드 추가가 아니라* “JSON 출력 전반을 versioned contract로 다루겠다”는 방향성) 소비자 입장에서는 신호가 같습니다. 기존 툴이 “unknown field는 무시하면 된다”라는 가정 위에 서 있다면, 그 가정이 언제/어떻게 깨지는지를 먼저 따져야 합니다.[^1]

내 경우 Terraform 쪽 릴리스보다 내부 파이프라인 쪽 장애가 더 비쌌습니다. PR 리뷰 코멘트가 사라지거나(리뷰 봇 장애), 정책 단계가 갑자기 fail-open으로 돌아가거나(정책 엔진 예외 처리), 비용 프리뷰가 0으로 표시되는(파서 실패 후 기본값) 식의 사고는 인프라 자체보다 조직 신뢰를 먼저 깎습니다.

이 글은 plan JSON 소비자를 대상으로, `format_version`을 계약으로 다루는 원칙과 “계약 테스트(contract test)”를 CI에 넣는 구체 설계를 중심으로 정리합니다. CLI 업그레이드 체크리스트 성격의 내용은 예전에 쓴 글에서 이미 다뤘으니 반복하지 않습니다.

- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)
- [Terraform 1.16.1 import/panic 버그와 IaC 파이프라인 방어](https://daewooki.github.io/posts/terraform-import-panic-pipeline-guardrails/)

## Terraform이 제공하는 “버전이 붙은 JSON”의 종류
Terraform에서 “JSON을 소비한다”는 말은 실제로 서로 다른 세 가지를 섞어 말하는 경우가 많습니다. 계약을 만들려면 먼저 대상을 구분해야 합니다.

### 1) `terraform show -json <planfile>`: plan/state의 stable JSON
Terraform은 바이너리 plan 파일(`terraform plan -out tfplan`)을 만든 다음 `terraform show -json tfplan`로 plan의 JSON 표현을 뽑아낼 수 있습니다. 이 JSON은 HashiCorp가 “앞으로도 외부 도구가 소비할 수 있는 형식”으로 문서화해 둔 쪽입니다.[^2]

이 JSON 최상위에 `format_version`이 있고, Terraform 문서에서는 major/minor 규칙을 명시합니다.

- minor 증가: backward-compatible한 추가/확장. 소비자는 모르는 필드를 무시해야 forward-compatible.
- major 증가: backward-incompatible. 소비자는 지원하지 않는 major를 거부.

이 규칙 자체가 계약의 출발점입니다.[^3]

현 시점에서 plan JSON의 `format_version` 값은 문서의 예시(`1.0`)에 고정돼 있지 않습니다. 공식 튜토리얼 예시에서는 `format_version`이 `1.2`로 나타나고, Terraform 코드에서도 plan JSON 포맷 버전 상수가 `1.2`로 정의되어 있습니다.[^4]

이 사실이 중요한 이유는 하나입니다. “우리는 `format_version`을 늘릴 수 있다”가 이미 현실에서 진행 중이라는 뜻입니다.

### 2) `terraform plan -json`: machine-readable UI event stream
`terraform plan -json`은 위의 stable plan JSON을 출력하지 않습니다. 대신 장시간 실행 커맨드에 대해 “한 줄에 한 JSON 메시지” 형태로 UI 이벤트 스트림을 흘립니다. 이건 plan 파일이 없어도 동작하는 대신, 메시지 타입별로 스키마가 나뉘고 첫 메시지에 `ui` 버전이 붙습니다.[^5]

여기서도 버전 규칙은 major/minor로 설명되며, 결국 “소비자는 버전 메시지를 읽고 계약을 선택해야 한다”는 구조입니다.[^5]

추가로 Terraform 테스트(`terraform test -json`)의 `test_plan` 메시지는 `plan_format_version`을 포함하는데, 이것도 결국 “plan JSON 스키마 변화는 `plan_format_version`으로 식별한다”는 방향성을 반복합니다.[^5]

### 3) `terraform version -json`: 이제 여기도 `format_version`이 붙는다
Terraform 1.16.3 릴리스 노트에서 언급된 변경은 `terraform version -json` 출력에 `format_version`을 추가한 것입니다. 릴리스 노트는 “unknown field를 무시하는 기존 툴이라면 안 깨지겠지만, 소비자는 앞으로 `format_version`에 주의하라”는 식으로 적고 있습니다.[^1]

PR 설명을 보면 의도가 더 노골적입니다.

- Terraform의 static JSON 출력은 top-level `format_version`으로 버전 관리한다.
- 커맨드마다 output schema 진화 정도가 달라 `format_version` 값도 커맨드별로 다를 수 있다.
- `version` 커맨드는 오래된 JSON 출력이라 그 “규범”을 따르지 못했는데, 이번에 맞춘다.

이건 특정 커맨드의 필드 하나 추가가 아니라, 조직 내부 도구가 “Terraform JSON을 파싱하는 순간 Terraform 릴리스의 간접 영향권에 들어간다”는 경고에 가깝습니다.[^6]

## “unknown field는 무시”가 깨지는 지점들
Terraform 문서의 약속은 단순합니다. minor 증가에서는 모르는 필드를 무시하면 된다. 문제는 현실의 소비자 구현이 이 약속을 지키지 못하는 경우가 많다는 겁니다. 여기서부터가 실제 장애 포인트입니다.

### 1) strict decoder가 기본값인 언어/프레임워크를 쓸 때
Go `encoding/json` 자체는 기본이 “unknown field 무시”라 그나마 안전한 편입니다. 하지만 조직 내부 도구는 종종 다음을 같이 씁니다.

- `Decoder.DisallowUnknownFields()` (의도는 좋은데 forward-compatibility를 버립니다)
- JSON Schema validator에서 `additionalProperties: false`를 습관처럼 켜는 구성
- OpenAPI codegen 모델을 그대로 디코딩에 사용하는 방식

이 방식은 minor 증가(필드 추가)만으로도 바로 깨집니다. Terraform이 약속을 어겨서가 아니라 소비자가 약속을 무시한 겁니다.

특히 정책 엔진/보안 도구는 “정확한 스키마”에 집착하는 경향이 있고, 그 집착이 format evolution과 충돌합니다.

### 2) 필드 추가가 아니라 “enum 확장”이 들어오는 경우
unknown field는 무시하면 되지만, 기존 필드의 값 공간이 늘어나는 건 다른 문제입니다.

예를 들어 plan JSON에서 `resource_changes[].change.actions`는 문자열 배열이고 Terraform 내부 구현 주석을 보면 이미 다양한 액션 조합을 허용하는 방향으로 설계돼 있습니다(교체를 `delete/create` 조합으로 표현하는 이유도 문서화돼 있음).[^7]

여기서 소비자가 `actions == ["create"]|["update"]|["delete"]` 같은 식으로 하드코딩하면, 새로운 액션이 들어오는 순간(또는 기존에도 존재하던 조합을 이제 더 자주 쓰게 되는 순간) 바로 오동작합니다.

이 타입의 파손은 “unknown field 무시”와 무관하게 발생합니다. 그래서 계약 테스트는 “필드 존재 여부”만이 아니라 “값의 도메인”까지 포함해야 합니다.

### 3) round-trip / filter / re-emit 계열 도구의 구조적 한계
`terraform-json` 라이브러리 README는 꽤 직설적입니다.

- 이 라이브러리는 특정 시점의 JSON 포맷 스냅샷이며 Terraform보다 약간 늦을 수 있다.
- unknown attribute를 드랍한다.
- 그래서 read-modify-write(필터링/라운드트립/재출력) 목적에는 부적합하다.

즉, 단순히 파싱만 하고 끝낼 때는 괜찮아도 “일부만 추려 다시 JSON으로 만들어 downstream에 넘기는” 구조라면, 새로운 필드가 추가되는 순간 조용히 데이터가 유실됩니다. 이건 장애가 아니라 더 위험한 데이터 무결성 문제입니다.[^8]

### 4) `null` vs missing의 의미 차이를 소비자가 무시할 때
Terraform plan JSON에는 “unknown value” 표현이 섞입니다. `terraform show -json` 문서에서도 unknown은 null/omission과 구분이 안 될 수 있다고 적어둡니다.[^3]

비용 산정기나 정책 엔진이 `after`에 있는 값을 기준으로 판단할 때, 이 차이를 무시하면 다음이 쉽게 발생합니다.

- 실제로는 “unknown이라 아직 모른다”인데 소비자는 “unset”으로 취급
- 정책이 fail-open으로 동작
- 비용 프리뷰가 0으로 떨어짐

이건 JSON 스키마 문제가 아니라 의미론 문제라서, 계약 테스트가 “의도한 해석이 유지되는지”를 검증해야 합니다.

### 5) plan JSON 자체가 아니라 plan 생성/표시 과정이 바뀌는 경우
`terraform show -json`은 plan/state를 JSON으로 변환하는 과정에서 provider schema, state 업그레이드 여부 등 주변 조건에 영향을 받습니다. `show -json` 문서도 provider schema가 업데이트됐으면 state를 업그레이드하라고 안내합니다.[^2]

즉, 같은 Terraform 버전이라도:

- provider 버전 변경
- state 스냅샷 버전 변경
- 실행 플래그(예: refresh 관련)

에 따라 JSON 구조의 일부(특히 `prior_state`나 schema_version, values 표현)가 달라질 수 있습니다. 계약 테스트는 Terraform 버전만 고정해서는 부족하고, fixture 생성 시점의 provider lockfile까지 같이 고정해야 합니다.

## format_version을 “계약”으로 격상시키는 규칙
여기서 말하는 계약은 “스키마 문서”가 아니라 “소비자 팀이 실제로 지킬 런타임 규칙 + 테스트”입니다. 내 기준으로는 다음 6가지를 최소 계약으로 잡는 게 효과가 있었습니다.

### 1) 최상위 버전 필드를 항상 읽고, 로그/메트릭으로 남긴다
plan JSON이면 `.format_version`과 `.terraform_version`을 읽습니다. 머신 UI 스트림이면 첫 메시지의 `type=version`과 `ui`를 읽습니다.[^5]

이 값을 남기면 “깨졌을 때 원인을 찾는 속도”가 달라집니다. 파서 에러 로그에 입력 JSON 일부만 남기면 보안/민감정보 문제도 생기는데, 버전 필드만 남기는 방식은 안전한 편입니다.

### 2) major는 하드하게 막고, minor는 정책을 선택한다
Terraform 문서의 약속대로 major가 바뀌면 소비자가 거부하는 게 맞습니다.[^3]

minor는 선택지 두 개가 있습니다.

- fail-open: “unknown field 무시”를 믿고 일단 진행(대신 관측을 강화)
- fail-closed: “테스트된 minor만 허용”하고 새 minor는 차단

보안 정책 엔진/승인 게이트라면 fail-closed가 낫고, PR 코멘트 정도면 fail-open이 낫습니다. 같은 조직에서도 컴포넌트별로 다르게 가져가는 게 현실적입니다.

내 경우 “승인/차단을 결정하는 컴포넌트”는 fail-closed, “가시성만 제공하는 컴포넌트”는 fail-open으로 두고, fail-open 컴포넌트에도 SLO 기반 알람을 붙였습니다.

### 3) “필요한 부분만” 파싱하고 나머지는 RawMessage로 둔다
앞으로의 minor 확장은 대부분 필드 추가일 가능성이 큽니다. 소비자가 전체를 strict하게 모델링할 이유가 없습니다.

- top-level 메타(버전, applyable/complete/errored)
- `resource_changes`에서 address/mode/type/provider_name/actions 정도
- 비용 산정이면 after/before 중 필요한 provider-specific subtree

이렇게 범위를 줄이면 format evolution의 영향 면적이 작아집니다.

### 4) 도메인 모델을 Terraform JSON 모델과 분리한다
“Terraform plan JSON 구조”를 그대로 내부 도메인 모델로 쓰면, Terraform 쪽 minor 변화가 내부 전파를 일으킵니다.

- 입력(외부 계약): Terraform JSON
- 내부(업무 모델): `Change{Address, Actions, Tags, …}`
- 출력(내부 인터페이스): 내부 모델

이 경계를 세우면 JSON 필드 추가/재배치가 생겨도 변환 계층만 고치면 됩니다.

### 5) jq 스크립트/정규표현식 파서를 계약에서 제외한다
현장에서 제일 흔한 plan 소비 방식은 `terraform show -json tfplan | jq ...`입니다. jq는 빠르고 좋지만, “스키마 계약”을 만들기 어렵습니다.

- 필드가 missing일 때의 처리
- enum 확장 대응
- 버전 게이트

이게 체계화되지 않으면, 어느 날 jq 필터가 빈 배열을 반환해도 파이프라인은 성공으로 끝납니다. 계약이 깨졌는데도 관측이 안 됩니다.

jq를 쓰더라도 “jq가 기대하는 최소 불변식”을 별도 validator로 검사하고, jq는 그 위에서만 동작하게 두는 게 안전합니다.

### 6) fixture(골든 파일)는 “커밋 가능한 형태”로만 보관한다
Terraform 문서도 경고하지만 plan 파일과 plan JSON에는 민감 정보가 들어갈 수 있습니다. 커밋 금지입니다.[^4]

그래도 계약 테스트를 하려면 골든 파일이 필요합니다. 이 딜레마는 보통 다음 중 하나로 풀립니다.

- 민감 정보가 들어가지 않는 test module을 따로 만든다(로컬 provider 위주)
- golden을 저장하되 redaction을 한 뒤 저장한다(키를 지우는 게 아니라, 구조를 보존한 채 값만 마스킹)
- 조직 내부 저장소(접근 통제)에서만 보관하고, 오픈 저장소에는 스키마 단위 테스트만 둔다

이 글의 예제는 첫 번째(민감 정보 없는 test module)로 갑니다.

## 계약 테스트를 어떻게 설계할지: golden files + 불변식
계약 테스트의 목적은 “Terraform이 바뀌면 깨지는지”가 아니라 “Terraform이 바뀌었을 때 소비자가 어떤 방식으로 깨지는지(또는 조용히 잘못 동작하는지)를 미리 발견”하는 겁니다.

내가 효과를 본 테스트 구성은 다음 3단입니다.

### 1) golden generation: 동일한 Terraform 모듈로 plan JSON을 뽑는다
- 같은 test module
- 같은 `.terraform.lock.hcl`
- Terraform 버전만 바꿔서 plan 생성
- `terraform plan -out=tfplan` → `terraform show -json tfplan`

Terraform Docker 이미지는 태그로 버전을 고정할 수 있어 이 용도에 잘 맞습니다(예: `hashicorp/terraform:1.16.2`, `hashicorp/terraform:1.16.3`).[^9]

### 2) normalization: timestamp, 경로, 실행환경에 따라 바뀌는 값을 제거한다
plan JSON에는 `timestamp` 같은 값이 들어가고, 일부 환경에서는 경로/순서가 달라질 수 있습니다. 그대로 diff를 뜨면 노이즈가 너무 큽니다.

- timestamp 제거
- 정렬이 보장되지 않는 배열은 정렬 키를 정의(예: `resource_changes[].address`)
- 숫자 타입은 `UseNumber`로 float 오염을 막는다

이 normalization은 parser의 일부로 넣기보다, “fixture 생성 단계”에서 별도 스크립트로 처리하는 게 관리하기 좋았습니다.

### 3) invariants: “내 툴이 기대하는 최소 의미론”을 코드로 검증한다
예를 들어 리뷰 봇이라면:

- 최상위 `format_version` major는 1이어야 한다
- `resource_changes`가 있을 때 각 엔트리는 `address`, `change.actions`를 가져야 한다
- actions에는 최소한 하나 이상의 값이 있어야 한다
- 내가 모르는 action이 나오면 실패(또는 경고) 정책을 적용한다

비용 산정기라면:

- `planned_values` 또는 `resource_changes[].change.after`에서 비용 모델링에 필요한 필드가 “unknown”일 때 어떻게 처리할지 계약으로 명시

정책 엔진이라면:

- 태그/라벨 같은 정책 필드가 unknown일 때 fail-open/fail-closed 결정

여기까지 해야 “unknown field 무시”가 아니라 “unknown 의미론 대응”까지 계약이 됩니다.

## 실행 가능한 예제: plan JSON 소비자용 contract test 패키지
아래는 내부 리뷰 봇/정책 엔진이 공통으로 쓸 수 있는 “plan JSON validator”를 작은 패키지로 만드는 예제입니다.

- Terraform 1.16.2와 1.16.3으로 동일한 test module을 plan
- `terraform show -json` 결과를 fixtures로 저장
- Go 테스트에서 fixtures를 읽어 validator 실행
- `format_version` minor가 올라가면 테스트가 먼저 빨갛게 변하도록 구성

### 디렉터리 구조
```text
planjson-contract/
  module-under-test/
    main.tf
    versions.tf
    outputs.tf
  fixtures/
    tf-1.16.2.plan.json
    tf-1.16.3.plan.json
  cmd/
    planjson-validate/
      main.go
  internal/
    planjson/
      validate.go
      decode.go
  Makefile
  go.mod
  internal/planjson/validate_test.go
```

### module-under-test (민감정보 없는 구성)
`random`과 `local`만 사용합니다. plan 단계에서 unknown value도 자연스럽게 생기고, output_changes도 생깁니다.

`module-under-test/versions.tf`
```hcl
terraform {
  required_version = ">= 1.16.0"

  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}
```

`module-under-test/main.tf`
```hcl
provider "random" {}
provider "local" {}

variable "env" {
  type    = string
  default = "dev"
}

resource "random_password" "db" {
  length  = 24
  special = true
}

resource "random_pet" "name" {
  length = 2
  prefix = var.env
}

resource "local_file" "preview" {
  filename = "${path.module}/preview.txt"
  content  = "env=${var.env} name=${random_pet.name.id}"
}
```

`module-under-test/outputs.tf`
```hcl
output "pet" {
  value = random_pet.name.id
}

output "db_password" {
  value     = random_password.db.result
  sensitive = true
}
```

### fixtures 생성 (Terraform Docker 이미지로 버전 고정)
`Makefile`
```make
TF_VERSIONS := 1.16.2 1.16.3

.PHONY: fixtures
fixtures:
	@mkdir -p fixtures
	@for v in $(TF_VERSIONS); do \
		echo "==> generating fixture for terraform $$v"; \
		docker run --rm -v $$PWD/module-under-test:/work -w /work \
			hashicorp/terraform:$$v init -lockfile=readonly; \
		docker run --rm -v $$PWD/module-under-test:/work -w /work \
			hashicorp/terraform:$$v plan -out=tfplan -input=false; \
		docker run --rm -v $$PWD/module-under-test:/work -w /work \
			hashicorp/terraform:$$v show -json tfplan > fixtures/tf-$$v.plan.json; \
		rm -f module-under-test/tfplan; \
		docker run --rm -v $$PWD/module-under-test:/work -w /work \
			hashicorp/terraform:$$v init -lockfile=readonly >/dev/null; \
	done
```

- Docker Hub 태그로 `hashicorp/terraform:1.16.2`, `hashicorp/terraform:1.16.3`가 제공됩니다.[^9]
- 실제 조직에서는 fixtures 생성 시 `.terraform.lock.hcl`을 커밋해 provider 버전까지 고정하는 편이 낫습니다.

### validator가 기대하는 계약(정책)
여기서는 “리뷰 봇이 최소한 변경 요약을 만들 수 있는지”를 계약으로 잡습니다.

- `format_version` major == 1만 허용
- minor는 `<= 2`까지만 허용(테스트된 범위)
- `resource_changes`가 있으면 각 change는 `address`와 `actions`를 가져야 함
- actions에 내가 모르는 값이 나오면 실패(리뷰 봇이라도, 모르는 액션을 요약하면 사람을 오도하기 때문)

이 정책은 conservative합니다. 대신 CI에서 Terraform 버전을 올릴 때 “왜 막혔는지”가 명확해집니다.

### Go 구현: 필요한 부분만 안전하게 decode
`go.mod`
```go
module example.com/planjson-contract

go 1.23
```

`internal/planjson/decode.go`
```go
package planjson

import (
	"bytes"
	"encoding/json"
	"fmt"
)

// Envelope는 Terraform plan JSON의 일부만 모델링합니다.
// 나머지 필드는 Extras로 보존합니다.
type Envelope struct {
	FormatVersion    string `json:"format_version"`
	TerraformVersion string `json:"terraform_version"`

	ResourceChanges json.RawMessage `json:"resource_changes"`

	Extras map[string]json.RawMessage `json:"-"`
}

func DecodeEnvelope(b []byte) (*Envelope, error) {
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()

	var raw map[string]json.RawMessage
	if err := dec.Decode(&raw); err != nil {
		return nil, fmt.Errorf("decode plan json: %w", err)
	}

	e := &Envelope{Extras: map[string]json.RawMessage{}}
	for k, v := range raw {
		switch k {
		case "format_version":
			_ = json.Unmarshal(v, &e.FormatVersion)
		case "terraform_version":
			_ = json.Unmarshal(v, &e.TerraformVersion)
		case "resource_changes":
			e.ResourceChanges = v
		default:
			e.Extras[k] = v
		}
	}
	return e, nil
}
```

`internal/planjson/validate.go`
```go
package planjson

import (
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
)

type Version struct {
	Major int
	Minor int
}

func ParseMajorMinor(s string) (Version, error) {
	parts := strings.Split(s, ".")
	if len(parts) != 2 {
		return Version{}, fmt.Errorf("invalid version %q", s)
	}
	maj, err := strconv.Atoi(parts[0])
	if err != nil {
		return Version{}, fmt.Errorf("invalid major in %q", s)
	}
	min, err := strconv.Atoi(parts[1])
	if err != nil {
		return Version{}, fmt.Errorf("invalid minor in %q", s)
	}
	return Version{Major: maj, Minor: min}, nil
}

type ResourceChange struct {
	Address string `json:"address"`
	Change  struct {
		Actions []string `json:"actions"`
	} `json:"change"`
}

type Policy struct {
	MaxTestedMinor int
	AllowedActions map[string]struct{}
}

func DefaultPolicy() Policy {
	return Policy{
		MaxTestedMinor: 2,
		AllowedActions: map[string]struct{}{
			"no-op":  {},
			"create": {},
			"read":   {},
			"update": {},
			"delete": {},
			"forget": {},
		},
	}
}

func ValidatePlanJSON(plan []byte, p Policy) error {
	env, err := DecodeEnvelope(plan)
	if err != nil {
		return err
	}
	if env.FormatVersion == "" {
		return errors.New("missing format_version")
	}

	v, err := ParseMajorMinor(env.FormatVersion)
	if err != nil {
		return err
	}
	if v.Major != 1 {
		return fmt.Errorf("unsupported format_version major: %d", v.Major)
	}
	if v.Minor > p.MaxTestedMinor {
		return fmt.Errorf("format_version minor %d is newer than tested max %d", v.Minor, p.MaxTestedMinor)
	}

	if len(env.ResourceChanges) == 0 {
		// resource_changes가 없을 수도 있습니다(상태 JSON 등). 여기서는 plan fixture만 다룬다고 가정.
		return errors.New("missing resource_changes")
	}

	var rcs []ResourceChange
	if err := json.Unmarshal(env.ResourceChanges, &rcs); err != nil {
		return fmt.Errorf("decode resource_changes: %w", err)
	}
	for _, rc := range rcs {
		if rc.Address == "" {
			return errors.New("resource_change missing address")
		}
		if len(rc.Change.Actions) == 0 {
			return fmt.Errorf("resource_change %s has empty actions", rc.Address)
		}
		for _, a := range rc.Change.Actions {
			if _, ok := p.AllowedActions[a]; !ok {
				return fmt.Errorf("resource_change %s has unknown action %q", rc.Address, a)
			}
		}
	}
	return nil
}
```

여기서 중요한 포인트는 두 가지입니다.

- unknown field를 “무시”하는 게 아니라, Extras로 **보존**해 두었습니다. 나중에 디버깅/관측/라운드트립이 필요할 때 이 차이가 큽니다.
- 테스트된 minor만 통과시키는 정책을 validator에 넣어, Terraform CLI 업그레이드가 들어오면 CI가 먼저 경고하도록 구성했습니다.

### CLI 도구로도 쓸 수 있게 연결
`cmd/planjson-validate/main.go`
```go
package main

import (
	"fmt"
	"io"
	"os"

	"example.com/planjson-contract/internal/planjson"
)

func main() {
	b, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read stdin: %v\n", err)
		os.Exit(2)
	}

	pol := planjson.DefaultPolicy()
	if err := planjson.ValidatePlanJSON(b, pol); err != nil {
		fmt.Fprintf(os.Stderr, "INVALID: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("OK")
}
```

실행 예시(fixtures가 준비돼 있다는 가정):
```bash
cat fixtures/tf-1.16.3.plan.json | go run ./cmd/planjson-validate
# OK
```

### Go 테스트: golden을 읽어서 계약을 검증
`internal/planjson/validate_test.go`
```go
package planjson

import (
	"os"
	"testing"
)

func TestFixtures(t *testing.T) {
	pol := DefaultPolicy()

	files := []string{
		"../../fixtures/tf-1.16.2.plan.json",
		"../../fixtures/tf-1.16.3.plan.json",
	}

	for _, f := range files {
		b, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read fixture %s: %v", f, err)
		}
		if err := ValidatePlanJSON(b, pol); err != nil {
			t.Fatalf("fixture %s invalid: %v", f, err)
		}
	}
}
```

이 테스트가 하는 일은 단순하지만, 조직에서는 이 정도만으로도 효과가 큽니다.

- Terraform CLI를 올렸더니 plan JSON `format_version` minor가 증가
- validator 정책(`MaxTestedMinor`)과 불일치
- 파이프라인이 “리뷰 봇/정책 엔진/비용 산정기” 릴리스 없이 Terraform만 올리는 걸 차단

이게 “계약 테스트”의 현실적인 역할입니다.

## terraform-json / terraform-exec을 어떻게 다룰지
Terraform 생태계에서는 plan/state JSON을 다루는 Go 라이브러리로 `hashicorp/terraform-json`, `hashicorp/terraform-exec`이 사실상 표준처럼 쓰입니다. 다만 여기에도 함정이 있습니다.

### terraform-json: 편하지만 forward-compatibility를 목표로 하면 곤란해진다
`terraform-json` README는 다음을 명확히 경고합니다.

- 각 버전은 Terraform JSON 포맷의 스냅샷이며 Terraform보다 약간 늦을 수 있다.
- unknown attribute를 드랍한다.
- 따라서 필터링/라운드트립/재출력 목적에는 부적합하다.

plan JSON 소비자가 “그냥 파싱해서 판단하고 끝”이면 쓸 만하지만, 내부 도구가 커지면 결국 “부분 변환 → 저장 → 재처리” 형태로 진화합니다. 그때 unknown drop은 구조적으로 사고를 만듭니다.[^8]

또한 `terraform-json`은 plan 포맷 버전 제약을 코드로 들고 있습니다(예: `< 2.0`). “major가 올라가면 깨진다”는 사실이 라이브러리 레벨에서도 전제라는 뜻입니다.[^10]

### terraform-exec: Terraform CLI를 라이브러리로 감싸는 층도 계약에 포함된다
`terraform-exec`은 CLI 실행을 Go 코드로 감싸는데, 이 라이브러리도 아직 v1.0.0이 아니고 minor에서 breaking이 가능하다고 명시합니다.[^11]

즉, 내부 도구가 `terraform-exec`에 의존한다면 계약 테스트는 Terraform CLI 버전뿐 아니라 `terraform-exec`/`terraform-json` 버전까지 포함하는 “3중 매트릭스”가 됩니다.

내 경우 이 매트릭스를 피하기 위해 “plan JSON의 일부만 커스텀 decode”하는 쪽을 선택했고, 필요한 경우에만 `terraform-json` 타입을 참고 자료처럼 사용했습니다. 커스텀 decode는 귀찮지만, 업그레이드 리스크를 소비자 쪽에서 통제하기가 훨씬 쉽습니다.

## 장애를 미리 당겨오는 운영 패턴: 버전 관측 + 차단 지점 분리
계약 테스트를 넣는다고 모든 문제가 끝나진 않습니다. 실제로는 다음 두 가지 운영 패턴이 같이 가야 합니다.

### 1) 프로덕션 파이프라인에서 format_version 분포를 관측한다
도구가 처리한 plan JSON의 `format_version`/`terraform_version`을 메트릭으로 쌓으면, “조직 안에 어떤 Terraform이 얼마나 섞여 있는지”가 보입니다.

- 특정 워크스페이스만 먼저 올렸는데 리뷰 봇이 그 워크스페이스에서만 깨짐
- 어떤 팀이 CI 캐시 때문에 오래된 Terraform을 계속 사용

이런 케이스가 흔합니다. 계약 테스트는 upgrade 순간의 안전장치이고, 관측은 upgrade 이후의 현실을 보여줍니다.

### 2) fail-closed는 ‘승인/차단’ 경로에만 둔다
리뷰 봇(코멘트 생성)까지 fail-closed로 두면, Terraform minor가 하나 올라가는 것만으로 PR 경험이 박살납니다.

반면 정책 엔진(merge/apply 차단)은 fail-closed가 맞습니다. 그래서 보통은:

- 리뷰 요약/코멘트: fail-open + 관측/알람
- 정책/차단 단계: fail-closed + 계약 테스트 통과한 버전만 허용

이 분리가 되어 있으면, Terraform 측 스키마 진화가 들어와도 “조직이 멈추는 지점”을 통제할 수 있습니다.

Terraform 1.16.3 릴리스 노트의 메시지도 결국 이 얘기입니다. unknown field 추가는 안 깨질 거라고 가정하지만, 그 가정은 소비자가 계약을 제대로 구현했을 때만 성립합니다.[^1]

## 참고 자료
- [Terraform v1.16.3 릴리스 노트](https://github.com/hashicorp/Terraform/releases)
- [PR #38930: version JSON output에 format_version 추가](https://github.com/hashicorp/terraform/pull/38930)
- [Terraform Internals: JSON Output Format](https://developer.hashicorp.com/terraform/internals/json-format)
- [Terraform Internals: Machine-readable UI Output](https://developer.hashicorp.com/terraform/internals/machine-readable-ui)
- [hashicorp/terraform-json README](https://github.com/hashicorp/terraform-json)
- [terraform-json plan.go (PlanFormatVersionConstraints)](https://github.com/hashicorp/terraform-json/blob/main/plan.go)
- [Terraform plan 튜토리얼: plan JSON과 format_version 예시, 민감정보 경고](https://docs.hashicorp.com/terraform/tutorials/cli/plan)
- [hashicorp/terraform Docker 이미지 태그(1.16.2, 1.16.3)](https://hub.docker.com/r/hashicorp/terraform/tags?page=1)

plan/json 소비자는 결국 Terraform의 내부 진화를 외부 계약으로 끌어오는 역할을 하므로, `format_version`을 읽고 테스트로 고정하는 쪽이 비용 대비 가장 확실한 방어였습니다.

[^1]: <https://github.com/hashicorp/Terraform/releases>
[^2]: <https://developer.hashicorp.com/terraform/cli/commands/show>
[^3]: <https://developer.hashicorp.com/terraform/internals/json-format>
[^4]: <https://docs.hashicorp.com/terraform/tutorials/cli/plan>
[^5]: <https://developer.hashicorp.com/terraform/internals/machine-readable-ui>
[^6]: <https://github.com/hashicorp/terraform/issues/38930>
[^7]: <https://github.com/hashicorp/terraform/blob/main/internal/command/jsonplan/plan.go>
[^8]: <https://github.com/hashicorp/terraform-json>
[^9]: <https://hub.docker.com/r/hashicorp/terraform/tags?page=1>
[^10]: <https://github.com/hashicorp/terraform-json/blob/main/plan.go>
[^11]: <https://github.com/hashicorp/terraform-exec>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
