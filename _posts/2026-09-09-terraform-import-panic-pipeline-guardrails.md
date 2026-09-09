---
title: "Terraform 1.16.1 import/panic 버그와 IaC 파이프라인 방어"
description: "import/for_each/count 무시, sensitive identity panic, create_before_destroy ordering을 운영 실패 모드로 해석하고 방어 장치를 정리합니다."
date: 2026-09-09 13:04:50 +0900
categories: ["Infrastructure", "Terraform"]
tags: ["terraform", "iac", "cicd", "policy-as-code", "terraform-test", "state-management"]
render_with_liquid: false
---

## 1.16.1에서 고쳐진 것의 공통점: “한 번 터지면 복구 비용이 커지는” 계열
Terraform 1.16.1은 2026-09-02에 릴리스됐고, 릴리스 노트에 명시적으로 다음 버그 픽스가 포함돼 있습니다: 
- import identity가 sensitive value를 참조할 때 panic
- `for_each`/`count` 인스턴스 대상으로 여러 `import` 블록을 둘 때 일부가 **조용히 무시**
- 특정 조합에서 `create_before_destroy` ordering이 깨짐
- (부수적으로) `state show` 특정 입력에서 panic, run task 실패+policy evaluation 대기 상태에서 CLI가 멈춤

이 묶음의 성격이 좋지 않은 이유는, 실패가 “plan 단계에서 안전하게 막히는 오류”가 아니라 다음 중 하나로 나타나기 때문입니다.

1) plan이 성공하고 정책도 통과했는데 apply에서 중간 실패(AlreadyExists, dependency error 등)로 state가 부분 갱신됨
2) plan 자체가 Terraform Core crash로 끝나면서 파이프라인이 비정상 종료함
3) apply는 끝났는데 순서가 꼬여서 원격 시스템의 제약에 걸리고, deposed object가 남거나 다음 배포가 연쇄적으로 실패함

Terraform 1.16.1 릴리스 노트는 이 버그들을 “Bug fix”로 한 줄씩 적고 끝나지만, 플랫폼 팀 입장에서는 이걸 실제 운영 파이프라인(Plan→Policy→Apply, 멀티 워크스페이스/스택) 실패 모드로 번역해야 업그레이드 우선순위를 정할 수 있습니다.[^1]

## 실패 모드 1: import blocks + for_each/count에서 일부 import가 무시되는 경우
Terraform 1.16.1 릴리스 노트에는 다음 항목이 박혀 있습니다.

- “import blocks would be ignored when multiple imports targeted different instances of a resource config using `for_each` or `count`.”[^1]

이 문장이 의미하는 운영 리스크는 단순히 “import가 안 된다”가 아닙니다. 더 위험한 포인트는 “무시되는데도 plan이 정상처럼 보인다”는 점입니다.

### 실제 현상: 첫 번째 import만 먹고, 나머지는 create로 계획된다
해당 회귀(regression)는 2026-08-26에 등록된 이슈에서 가장 깔끔하게 재현됩니다. 이슈 요약은 다음과 같습니다.

- Terraform v1.16.0에서 `for_each` 리소스에 대해 `import { ... }` 블록을 2개 두면 첫 번째만 수행되고 두 번째는 경고 없이 버려짐
- 결과적으로 두 번째 대상은 “import”가 아니라 “create”로 plan에 들어감
- `import` 블록 순서를 바꾸면 살아남는 대상도 바뀜(키 순서가 아니라 선언 순서)

이슈 본문에는 provider 없이 재현 가능한 구성(`terraform_data`)과, 1.16.0에서의 plan 출력, 1.15.9에서의 정상 동작 비교가 그대로 들어 있습니다.[^2]

운영에서 이게 왜 치명적이냐면, 대부분의 “마이그레이션 import”는 원격에 이미 존재하는 객체를 state에 편입시키는 작업이기 때문입니다. 즉, create가 계획되는 순간 이미 파이프라인은 파괴 모드로 진입합니다.

- apply가 해당 객체를 새로 만들려고 시도하다가 클라우드 API에서 AlreadyExists 계열 에러로 실패
- 그 전에 실행된 import 일부는 state에 반영되어 버림(부분 갱신)
- 다음 plan에서는 “절반은 managed, 절반은 unmanaged” 같은 상태가 되어, 사람 손으로 정리하지 않으면 진도가 안 나감

이 이슈에서도 “실제 인프라에서는 절반만 import되고 나머지는 AlreadyExists로 실패해서 partial state가 남는다”는 맥락이 명시되어 있습니다.[^2]

### 운영 파이프라인에서 깨지는 지점: Plan→Policy→Apply의 ‘정상 흐름’이 함정이 된다
대형 repo에서 흔한 구조를 가정해 보겠습니다.

- 단일 mono-repo에 수십~수백 개 root module(=workspace 단위)이 있고
- PR마다 변경된 디렉터리만 plan을 돌려서
- plan artifact(JSON 포함)를 Policy(OPA/Sentinel/자체 규칙)에 태운 뒤
- 승인되면 apply로 넘어가는 흐름

여기서 import 무시 버그가 끼면, 최악의 경우는 다음입니다.

1) Plan이 성공합니다. (경고 없음)
2) Policy도 통과합니다. (정책은 “create가 나오면 안 된다” 같은 규칙을 별도로 두지 않으면 통과하기 쉽습니다.)
3) Apply에서 중간 실패합니다. 
4) state는 부분 업데이트되고, 같은 PR을 재시도해도 똑같은 지점에서 반복 실패합니다.

가장 문제는 1)~2)에서 “이게 원래 의도한 변화인지”가 시스템적으로 식별되지 않는다는 점입니다. 즉, 사람이 plan 텍스트를 읽어내는 과정으로 회귀합니다.

### 재현 가능한 최소 구성(실전 파이프라인용 카나리로 쓸 수 있는 형태)
이 구성은 실제 클라우드 자원 없이도 Terraform Core가 import를 어떻게 처리하는지 확인하는 smoke test로 쓸 수 있습니다. 이슈에서 제시된 `terraform_data` 기반 재현을 그대로 가져오되, 운영 파이프라인에서 돌리기 좋게 파일을 나눴습니다.[^2]

`main.tf`
```hcl
resource "terraform_data" "t" {
  for_each = toset(["a", "b"])
  input    = each.key
}
```

`imports.tf`
```hcl
import {
  to = terraform_data.t["a"]
  id = "aaa"
}

import {
  to = terraform_data.t["b"]
  id = "bbb"
}
```

실행 명령:
```bash
terraform init
terraform plan
```

Terraform v1.16.0에서의 관측(이슈 본문 그대로): 첫 번째만 “Preparing import”가 뜨고 두 번째는 create로 계획됩니다.[^2]

Terraform v1.16.1에서는 이 버그가 수정됐다고 릴리스 노트에 명시돼 있습니다.[^1]

이 재현 구성이 중요한 이유는, 플랫폼 팀이 “우리 인프라로 직접 테스트”를 하기 전에 Terraform 자체 회귀를 CI에서 빨리 잡는 데 바로 쓸 수 있기 때문입니다.

## 실패 모드 2: import identity가 sensitive value를 참조하면 Terraform Core가 panic
Terraform 1.16.1 릴리스 노트에 “Fix panic when import identity references sensitive value”가 들어 있습니다.[^1]

여기서 포인트는 단순 실패가 아니라 **panic(=Terraform crash)**라는 점입니다. 정상적인 실패(진단 메시지+exit code)와 panic은 파이프라인에서 취급이 다릅니다.

- 일반 실패: plan 실패로 기록되고, 원인 메시지를 정책/리포팅 레이어에서 수집 가능
- panic: 로그는 찍히지만(혹은 잘리지만) “내가 컨트롤할 수 있는 실패”가 아니고, 일부 러너/오케스트레이터에서는 재시도/타임아웃 패턴이 꼬입니다

### 실제 크래시 패턴: cty mark(sensitive) 처리 중 assertUnmarked
이 이슈는 2026-08-12에 등록됐고, import block의 `identity`에 로컬 값(`local.env.q`)을 넣었는데 그 로컬 값이 `sensitive()`로 감싸져 있을 때 plan이 crash 합니다.[^3]

이슈에 포함된 핵심 조각:

- import 블록이 `identity = { zone_id = local.env.q }` 형태
- local은 `.env`를 읽고 `sensitive(tuple[1])`로 마킹
- crash 스택 트레이스에 `panic: value is marked, so must be unmarked first`와 `cty.Value.assertUnmarked`가 등장

스택 트레이스 일부는 아래 라인들이 핵심입니다.[^3]

- `panic: value is marked, so must be unmarked first`
- `github.com/zclconf/go-cty/cty.Value.assertUnmarked`
- `cty.Value.AsString`

Terraform의 sensitive는 “출력에서 값 마스킹”을 넘어 내부 값에 mark를 붙여서 흘려보내는 모델입니다(사용자 문서에서도 sensitive 플래그가 출력 억제에 쓰인다고 설명합니다).[^4]

즉, import identity가 문자열로 평가되는 과정에서(특히 UI hook/diagnostics로 렌더링되는 지점에서) unmark가 누락되면 Core가 크래시할 수 있습니다. 이건 “구성은 합법인데 Core가 죽는다”는 형태라, IaC 파이프라인 관점에서는 가장 예측 불가능한 부류입니다.

### 운영에서 흔한 트리거: identity를 data source/파일/secret에서 만들 때
import block의 `identity`는 provider마다 키/값이 다르고, 문서상 “키/값 쌍으로 리소스를 유일하게 식별”하는 객체입니다.[^5]

현장에서 identity를 다루는 방식은 대개 아래 중 하나입니다.

- 외부 시스템에서 가져온 식별자(예: zone_id, project 번호, subscription id)를 locals로 조합
- `.env`/Vault/Parameter Store 등에서 값을 읽어와서 locals에 저장
- 보안상 출력에 노출되면 안 되니까 `sensitive()`로 감쌈

바로 이 마지막 단계가 crash 트리거가 됩니다. “identity는 민감 정보가 아니다”라고 단정할 수 없는 팀일수록(예: 내부 자원 식별자가 곧 고객 정보이거나, 특정 키가 접근 경로가 되는 경우) 더 자주 밟습니다.

### 1.16.1로 고쳐졌다고 해도, 방어적 구성은 남겨야 한다
패치 버전에서 panic이 고쳐졌더라도, 운영에서는 다음 이유로 방어 구성이 남아야 합니다.

- 동일 패턴이 다른 코드 경로에서 다시 재발할 수 있음(표면적으로는 “import identity”지만, cty mark/unmark는 다른 출력/진단 경로에서도 반복)
- 멀티 워크스페이스에서는 어떤 워크스페이스가 이 패턴을 쓰는지 플랫폼 팀이 한 눈에 모르는 경우가 많음

따라서 “업그레이드하면 끝”이 아니라, **sensitive를 import identity에 흘려보내지 않는 규칙**을 정책/리뷰/자동검사로 박는 편이 안전합니다.

- identity 구성에 들어가는 값은 원칙적으로 non-sensitive로 유지(출력 노출이 걱정이면 plan JSON/policy 단계에서 마스킹 처리)
- 불가피하면 `nonsensitive()`를 적용하되, 그 행위 자체를 코드 리뷰 기준으로 승격(무심코 복호화/노출이 되기 쉬움)

여기서 `nonsensitive()`를 무조건 권장하지 않는 이유는, 그 순간부터는 사람이 “이 값은 진짜 민감하지 않다”는 걸 증명해야 하기 때문입니다. panic을 피하려고 보안 모델을 흔들면, 다른 종류의 사고로 바뀝니다.

## 실패 모드 3: create_before_destroy ordering이 깨질 때 나타나는 증상
Terraform 1.16.1 릴리스 노트에 “Fix create_before_destroy ordering in some combinations of changes”가 들어 있습니다.[^1]

여기서 “some combinations”가 함정입니다. 재현 조건이 좁다는 의미로 읽을 수도 있지만, 플랫폼 팀 입장에서는 반대로 읽어야 합니다.

- ordering 버그는 특정 리소스/특정 provider에서만 터지지 않습니다.
- 그래프 구성(의존성, replace 조합, count/for_each 인덱스 변화, deposed object 유무)이 맞아떨어지는 순간 터집니다.
- 한번 터지면 apply 실패로 끝나거나, 더 나쁘게는 “의도치 않은 순서로 삭제가 먼저 나가서 서비스가 죽는다”로 끝납니다.

### create_before_destroy가 왜 위험한 기능인지(기능 자체의 본질)
Terraform 문서에 따르면 `create_before_destroy`는 replace가 필요한 리소스를 “기본은 delete→create인데, create→delete로 바꾸는” 기능입니다.[^6]

그리고 내부적으로는 의존성 그래프의 edge를 뒤집는 방식으로 ordering을 만든다고 설명합니다.[^7]

이 메커니즘은 유용하지만, 운영에서 곧바로 다음 문제로 연결됩니다.

- API 제약 때문에 실제로는 create→delete가 불가능한 리소스(이름이 유일해야 하거나, quota가 빡빡하거나, 동일 attachment가 불가능한 경우)
- create_before_destroy가 전파(implicit)되어 state에 저장되고, 이후 제거해도 흔적이 남는 문제

Terraform lifecycle 문서에도 “의존성 때문에 Terraform이 create_before_destroy를 암묵적으로 활성화하고 state에 저장한다”는 설명이 있습니다.[^8]

즉, ordering은 단지 한 리소스의 속성이 아니라 “그래프 전체”의 속성이고, 그만큼 미묘한 버그가 나올 여지가 큽니다.

### 실패가 남기는 흔적: deposed object와 수동 개입
create_before_destroy가 얽힌 실패에서 자주 등장하는 단어가 deposed object입니다. HashiCorp의 도움말 문서에서도 “plan에 deposed object가 보일 수 있다”고 따로 설명합니다.[^9]

운영 절차에서 deposed object가 무서운 이유는 간단합니다.

- 파이프라인 실패가 “다음 apply에서 자연히 정리”되지 않는 케이스가 생깁니다.
- 결국 state 조작(`state rm`, `import` 재시도, 때로는 원격 수동 삭제/복구)이 필요해집니다.
- 이 순간부터는 플랫폼 팀이 제공하는 표준 파이프라인(승인/정책/감사)이 우회됩니다.

따라서 1.16.1에서 ordering 버그가 고쳐졌다는 한 줄은, “우리는 create_before_destroy를 쓰는 워크스페이스에서 Core patch 업그레이드를 빨리 고려해야 한다”는 신호로 보는 편이 맞습니다.

### policy 단계에서 ordering을 다루는 방법: actions 순서 검증
Sentinel의 `tfplan/v2` import 문서에는 replace 동작의 operation order가 명시돼 있습니다.

- 일반 replace는 `['delete', 'create']`
- create_before_destroy가 붙으면 `['create', 'delete']`

즉, ordering 검증은 “사람이 plan 텍스트를 읽어 판단”이 아니라, plan 데이터 모델에서 `actions` 배열의 순서를 검증하는 형태로 자동화할 수 있습니다.[^10]

이 방식은 Sentinel뿐 아니라 `terraform show -json`으로 덤프한 plan JSON을 OPA/자체 스크립트로 검사할 때도 똑같이 적용됩니다.

## Plan→Policy→Apply 파이프라인에서 버그가 ‘증폭’되는 지점
Terraform Core 버그는 단일 실행에서는 “한 번 실패”로 끝나지만, 파이프라인에서는 구조적으로 증폭됩니다.

### 1) Plan 산출물이 정책 입력으로 쓰이는 순간: “정책은 통과했는데 apply가 터짐”
HCP Terraform의 정책 결과 문서에서도 policy evaluation이 run stage별로 분리돼 있고, Sentinel/OPA가 별도 시점에 평가된다고 설명합니다.[^11]

문제는 import 무시/ordering 같은 버그가 “정책이 보기엔 합법”인 형태의 plan을 만들 수 있다는 점입니다.

- import가 무시되어 create가 들어가도, 정책이 ‘create 금지’ 규칙이 없으면 통과
- ordering이 꼬여도, 리소스 변화 자체는 정상으로 보이므로 통과

결국 apply에서 터지고, state는 부분 업데이트될 가능성이 커집니다.

### 2) 멀티 워크스페이스/스택: 동일 PR에서 일부만 실패하고 state가 갈라짐
대형 플랫폼 팀에서는 동일 PR이 N개 워크스페이스에 영향을 줍니다.

- 공통 module 버전 bump
- provider 버전 bump
- import 마이그레이션(특히 for_each로 여러 리소스를 옮기는 작업)

이때 import 무시 버그는 워크스페이스별로 “무시되는 대상”이 달라질 수 있습니다(선언 순서, 키, 모듈 인스턴스 조합이 다르기 때문). 결과적으로:

- A workspace는 절반 import 후 실패
- B workspace는 다른 절반 import 후 실패
- C workspace는 우연히 import가 한 개뿐이라 성공

이 상황이 가장 골치 아픈 이유는, 이후 수습이 “표준화된 한 가지 절차”가 아니게 된다는 점입니다.

### 3) 파이프라인 러너의 안정성 이슈와 결합
1.16.1에는 “run task failure + pending policy evaluations” 상태에서 CLI가 무한히 멈추는 버그 픽스도 포함돼 있습니다.[^1]

이건 import/panic과 직접 관련은 없지만, 운영에서는 결합해서 터집니다.

- core 버그로 plan/apply가 비정상 상태
- policy/run task 단계가 꼬임
- 러너는 종료되지 않고 hanging
- 결국 타임아웃으로 job이 kill되고, 그 사이에 state/원격은 일부 반영

즉, 업그레이드 우선순위는 “우리 팀이 import를 쓰나?” 같은 기능 플래그로만 판단하면 놓칩니다. 파이프라인 형태(원격 실행, run task, policy gating, 멀티 워크스페이스)까지 포함해 판단해야 합니다.

## 방어법 A: 버전 핀 + 카나리(업그레이드/다운그레이드 모두 포함)
플랫폼 팀이 Terraform 버전을 “각 팀 자율”로 두면, 이번 같은 버그에서 피해 규모가 커집니다. 가장 먼저 해야 할 일은 Terraform 버전의 단일화와, 단일화된 버전의 점진 롤아웃입니다.

### required_version으로 구성 레벨에서 막기
각 root module(혹은 공통 래퍼)에서 최소한 아래 형태로 핀을 걸어 두는 편이 안전합니다.

```hcl
terraform {
  required_version = "~> 1.16.1"
}
```

- `~> 1.16.1`은 1.16.x 패치 범위에서만 움직이게 만듭니다.
- `~> 1.16.0`처럼 minor 초기 태그를 허용하는 핀은 이번 케이스에서 위험합니다(문제 자체가 1.16.0 회귀였기 때문).

### CI 설치 단계도 같이 핀을 걸기
구성 레벨의 핀만으로는 부족합니다.

- 러너가 Terraform 1.16.0을 이미 설치해 둔 상태라면, `required_version`은 plan 자체를 막아 주긴 하지만(=실패), 그 실패가 “모든 워크스페이스에서 동시에” 터집니다.
- 반대로 러너가 최신을 자동으로 받는 구조면, 예고 없이 1.16.0이 들어와서 이미 사고가 납니다.

따라서 설치 단계에서 명시적으로 Terraform 버전을 고정하고, 버전 변경은 PR로만 들어오게 만들어야 합니다.

또한 Terraform 바이너리 배포 경로(공식 릴리스) 자체는 HashiCorp Releases에서 버전 디렉터리로 확인 가능합니다.[^12]

### 카나리 워크스페이스/스택을 “실제 인프라”가 아니라 “Core 회귀”에 맞추기
내 경우 카나리를 실제 프로덕션 인프라의 작은 조각으로 두는 접근은 자주 실패했습니다.

- 실제 인프라는 provider/API 변수가 너무 많아서, 실패 원인이 Core인지 provider인지 분리가 늦습니다.
- core 회귀는 provider가 필요 없는 형태로도 재현되는 경우가 많습니다(이번 import 무시 이슈처럼).[^2]

그래서 카나리 하나는 “클라우드와 무관한 Core 회귀 테스트 모듈”로 두고, 매일 혹은 Terraform 버전 bump PR마다 무조건 실행시키는 쪽이 비용 대비 효과가 좋습니다.

## 방어법 B: terraform test를 ‘모듈 품질’이 아니라 ‘파이프라인 안전장치’로 쓰기
Terraform 테스트 기능은 “모듈 단위 테스트”로만 소개되는 경우가 많지만, 이번 이슈처럼 Core가 특정 패턴에서 무너지는 버그를 잡는 데도 쓸 수 있습니다.

Terraform 테스트는 CLI로 `terraform test`를 실행하며, 테스트 파일에서 정의한 검증이 실패하면 전체 명령이 실패로 종료됩니다.[^13]

### import/for_each 무시 회귀를 잡는 테스트(클라우드 불필요)
앞서 소개한 재현 구성(`terraform_data` + 2개 import 블록)을 그대로 두고, 테스트에서는 “import가 되었으면 id가 지정한 값으로 들어와야 한다”를 검증합니다.

디렉터리 예시:

```text
.
├─ main.tf
├─ imports.tf
└─ tests
   └─ import_for_each_regression.tftest.hcl
```

`tests/import_for_each_regression.tftest.hcl`
```hcl
run "apply_imports" {
  command = apply

  assert {
    condition     = terraform_data.t["a"].id == "aaa"
    error_message = "terraform_data.t[\"a\"]가 import되지 않았습니다. (id=aaa 기대)"
  }

  assert {
    condition     = terraform_data.t["b"].id == "bbb"
    error_message = "terraform_data.t[\"b\"]가 import되지 않았습니다. (id=bbb 기대)"
  }
}
```

실행 명령:
```bash
terraform init
terraform test
```

- 1.16.0 계열(버그가 있는 버전)에서는 `t["b"]`가 create로 처리될 가능성이 크고, 그 경우 `id == "bbb"` 검증이 실패하며 `terraform test`는 non-zero로 종료됩니다.[^2]
- 1.16.1에서는 릴리스 노트 기준으로 이 버그가 수정됐으므로, 동일 테스트가 통과해야 합니다.[^1]

여기서 중요한 건 “테스트가 클라우드에 무엇을 만들었는가”가 아니라, 파이프라인이 의존하는 Terraform Core의 의미론(semantics)이 깨지지 않았는가입니다.

### sensitive identity panic은 ‘테스트로 잡는다’보다 ‘구성을 금지한다’가 낫다
panic 계열은 테스트로도 잡을 수는 있습니다. 하지만 운영에서는 아래 이유로 테스트보다 정책/정적 검사(deny rule)가 더 비용 대비 효과가 좋습니다.

- panic은 테스트 러너 자체를 비정상 상태로 만들 수 있음
- 어떤 워크스페이스가 해당 패턴을 쓰는지 모르는 경우가 많음

따라서 import block의 `identity` 내부에서 `sensitive()`/민감 locals를 참조하는 패턴 자체를 금지하고, 예외가 필요하면 보안 리뷰를 태우는 형태가 현실적입니다. (이 패턴이 실제로 panic을 유발한 사례는 이슈에 명시되어 있습니다.)[^3]

## 방어법 C: state/plan 검증 자동화를 파이프라인에 내장하기
이번 이슈의 본질은 “plan이 성공했는데 apply가 망가진다”이므로, 방어도 plan을 더 강하게 검증하는 쪽으로 가야 합니다.

### Plan을 JSON으로 고정하고, 그 JSON을 단일 진실로 삼기
Terraform은 plan file을 만든 뒤 `terraform show -json`으로 plan/config/state를 JSON으로 출력할 수 있습니다.[^14]

파이프라인에서 추천하는 기본 형태는 아래입니다.

```bash
set -euo pipefail

terraform init
terraform plan -out=tfplan
terraform show -json tfplan > tfplan.json
```

이 `tfplan.json`은 이후 단계에서 다음 입력으로 재사용합니다.

- Policy(OPA/Sentinel/자체 룰)
- Import/ordering 가드레일(아래 스크립트)
- PR 코멘트/감사 로그(리소스 변경 목록)

### (import 방어) “import 대상인데 create가 계획되면 실패” 가드레일
import 무시 버그의 운영 피해는 “이미 존재하는 것을 만들려 한다”입니다. 따라서 가장 단순한 가드레일은 아래입니다.

- 이번 PR에서 import 대상으로 삼는 리소스 주소 목록을 텍스트로 관리
- plan JSON에서 해당 주소가 `create` 액션으로 나오면 즉시 실패

`import_targets.txt`
```text
terraform_data.t["a"]
terraform_data.t["b"]
```

`scripts/guardrail_plan.py`
```python
#!/usr/bin/env python3
import json
import sys

def load_targets(path: str) -> set[str]:
    out = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out.add(line)
    return out

def main():
    if len(sys.argv) != 4:
        print("usage: guardrail_plan.py <plan.json> <import_targets.txt> <cbd_targets.txt>")
        return 2

    plan_path, import_targets_path, cbd_targets_path = sys.argv[1:]

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    import_targets = load_targets(import_targets_path)
    cbd_targets = load_targets(cbd_targets_path)

    resource_changes = plan.get("resource_changes", [])
    by_addr = {rc.get("address"): rc for rc in resource_changes if rc.get("address")}

    errors: list[str] = []

    # Guardrail 1: import target must not be planned as create
    for addr in sorted(import_targets):
        rc = by_addr.get(addr)
        if rc is None:
            errors.append(f"import target {addr} not found in plan.resource_changes")
            continue

        actions = (rc.get("change") or {}).get("actions") or []
        # 가장 보수적인 규칙: create가 포함되면 실패
        if "create" in actions:
            errors.append(f"import target {addr} has create action: actions={actions}")

    # Guardrail 2: create_before_destroy target replacement ordering
    # Sentinel tfplan/v2 문서 기준으로 create_before_destroy replace는 ['create','delete']여야 합니다.
    # (일반 replace는 ['delete','create']).
    for addr in sorted(cbd_targets):
        rc = by_addr.get(addr)
        if rc is None:
            continue

        actions = (rc.get("change") or {}).get("actions") or []
        if actions == ["delete", "create"]:
            errors.append(
                f"create_before_destroy target {addr} is planned as delete->create (actions={actions})"
            )

    if errors:
        print("plan guardrail failed:\n- " + "\n- ".join(errors))
        return 1

    print("plan guardrail passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

실행:
```bash
python3 scripts/guardrail_plan.py tfplan.json import_targets.txt cbd_targets.txt
```

이 스크립트는 두 가지를 노립니다.

- import 대상이 create로 떨어지는 순간(=이번 1.16.0 회귀의 핵심 현상) 즉시 파이프라인을 멈춥니다.[^2]
- create_before_destroy 대상 리소스에서 replace ordering이 `['delete','create']`로 나오면 차단합니다. 이 규칙 자체는 Sentinel 문서에 근거합니다.[^10]

이때 `cbd_targets.txt`는 빈 파일이어도 동작합니다.

`cbd_targets.txt`
```text
# 예: module.api.aws_lb.this
```

여기까지 자동화하면, “plan 텍스트를 사람이 읽고 눈치채야 하는 문제”가 “정책/가드레일 실패로 기계가 막는 문제”로 바뀝니다.

### (state 방어) apply 직후 “2nd plan must be empty”를 강제하기
import/ordering 계열 사고의 공통점은, 실패 후 state가 애매한 중간 상태가 된다는 점입니다. 그래서 apply 직후 아래를 강제하는 게 좋습니다.

```bash
terraform apply -auto-approve tfplan

# apply 직후에는 refresh 포함해서도 반드시 깨끗해야 합니다.
terraform plan -detailed-exitcode
# exit code 0이면 OK, 2면 drift/변경 존재(실패 처리), 1이면 오류
```

이 검증은 Terraform이 제공하는 exit code 계약에 기대는 방식이라, JSON 스키마 변화에 덜 민감합니다. (다만 apply가 실패한 경우에는 여기까지 오지 못하므로, 앞단의 plan guardrail과 같이 쓰는 편이 낫습니다.)

## 1.16.0→1.16.1 업그레이드 우선순위 판단 기준
2026-09-09 KST 시점에서, 1.16.1은 릴리스(2026-09-02) 직후 구간입니다. 그럼에도 우선순위를 높여야 하는 팀의 조건은 명확합니다.

### 즉시 우선순위를 높여야 하는 경우
- `import` 블록을 적극적으로 쓰고 있고, 특히 `for_each`/`count` 리소스 컬렉션에 여러 import를 박는 마이그레이션을 한다
  - 1.16.0에서 첫 번째만 import되고 나머지가 create로 계획될 수 있다는 실 사례가 존재합니다.[^2]
- `identity` 기반 import를 쓰며, locals/파일/secret에서 값을 조합할 때 `sensitive()`를 섞을 가능성이 있다
  - 실제로 sensitive local을 identity 값에 넣고 plan이 panic한 사례가 보고돼 있습니다.[^3]
- `create_before_destroy`를 광범위하게 쓰고 있고, replace가 잦은 리소스(네트워크, 인증, 보안 정책, 엔드포인트 등)가 있다
  - 1.16.1에서 ordering fix가 들어갔고, deposed object/ordering은 한 번 꼬이면 수습이 어렵습니다.[^1]

### 상대적으로 여유가 있는 경우
- import를 CLI로만 하고, `import` 블록을 거의 쓰지 않는다
- for_each/count 컬렉션 import가 없다
- create_before_destroy를 거의 쓰지 않으며, replace가 잦지 않다

다만 “여유”가 있다는 건 “업그레이드를 미룬다”가 아니라, “카나리+가드레일을 먼저 깔고 그 다음에 올린다” 정도의 의미입니다.

## 결론: 패치 릴리스라도 IaC 파이프라인을 기준으로 읽어야 한다
Terraform 1.16.1에서 고쳐진 버그들은 각각 따로 보면 사소한 패치처럼 보이지만, 파이프라인 관점에서는 공통적으로 “state/ordering/plan 신뢰”를 깨는 타입입니다. 릴리스 노트의 한 줄을 그대로 받아 적는 게 아니라, 실제 운영 흐름(Plan→Policy→Apply, 멀티 워크스페이스/스택)에서 어떤 실패 모드로 증폭되는지까지 번역해 두면 업그레이드 판단이 빨라집니다. 그 다음은 버전 핀, 카나리, terraform test 기반 회귀 검증, plan/state 자동 검증을 같은 레이어에서 묶어 두는 쪽이 결국 운영 비용을 줄입니다.

## 참고 자료
- [Terraform v1.16.1 릴리스 노트 (GitHub Releases)](https://github.com/hashicorp/Terraform/releases)
- [import blocks 무시 회귀 이슈 #39068](https://github.com/hashicorp/terraform/issues/39068)
- [import identity + sensitive value panic 이슈 #39013](https://github.com/hashicorp/terraform/issues/39013)
- [Terraform import block 문서](https://developer.hashicorp.com/terraform/language/block/import)
- [Terraform `terraform test` 명령 문서](https://developer.hashicorp.com/terraform/cli/commands/test)
- [Terraform 테스트 구성 문서](https://docs.hashicorp.com/terraform/language/tests)
- [Terraform `terraform show -json` 문서](https://developer.hashicorp.com/terraform/cli/commands/show)
- [Terraform JSON output format 문서](https://developer.hashicorp.com/terraform/internals/json-format)
- [HCP Terraform 정책 평가 결과/스테이지 문서](https://docs.hashicorp.com/terraform/cloud-docs/workspaces/policy-enforcement/view-results)
- [create_before_destroy 동작과 ordering 설명(destroying.md)](https://github.com/hashicorp/terraform/blob/main/docs/destroying.md)
- [create_before_destroy와 deposed object 대응(Help Center)](https://support.hashicorp.com/hc/en-us/articles/4409469235603-How-to-handle-issues-due-to-create-before-destroy-and-deposed-object)
- [Sentinel tfplan/v2 import reference (actions ordering)](https://docs.hashicorp.com/terraform/enterprise/workspaces/policy-enforcement/import-reference/tfplan-v2)
- [HashiCorp Releases: Terraform 1.16.1 바이너리 목록](https://releases.hashicorp.com/terraform/1.16.1/)

[^1]: <https://github.com/hashicorp/Terraform/releases>
[^2]: <https://github.com/hashicorp/terraform/issues/39068>
[^3]: <https://github.com/hashicorp/terraform/issues/39013>
[^4]: <https://developer.hashicorp.com/terraform/language/values/variables>
[^5]: <https://developer.hashicorp.com/terraform/language/block/import>
[^6]: <https://github.com/hashicorp/web-unified-docs/blob/main/content/terraform/v1.1.x/docs/language/meta-arguments/lifecycle.mdx>
[^7]: <https://github.com/hashicorp/terraform/blob/main/docs/destroying.md>
[^8]: <https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle%20%20>
[^9]: <https://support.hashicorp.com/hc/en-us/articles/4409469235603-How-to-handle-issues-due-to-create-before-destroy-and-deposed-object>
[^10]: <https://docs.hashicorp.com/terraform/enterprise/workspaces/policy-enforcement/import-reference/tfplan-v2>
[^11]: <https://docs.hashicorp.com/terraform/cloud-docs/workspaces/policy-enforcement/view-results>
[^12]: <https://releases.hashicorp.com/terraform/1.16.1/>
[^13]: <https://developer.hashicorp.com/terraform/cli/commands/test>
[^14]: <https://developer.hashicorp.com/terraform/cli/commands/show>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
