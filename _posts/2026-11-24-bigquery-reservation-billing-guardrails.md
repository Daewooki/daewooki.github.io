---
title: "BigQuery 비용 가드레일: reservation_override_mode·disable_on_demand_billing"
description: "BigQuery regional option 두 개가 GA가 되면서, 온디맨드 폭주를 조직 표준으로 차단하고 예약 기반 상한선을 코드로 고정할 수 있게 됐습니다."
date: 2026-11-24 18:27:09 +0900
categories: ["Data", "BigQuery"]
tags: ["bigquery", "finops", "reservations", "terraform", "governance", "cost-guardrails"]
render_with_liquid: false
---

## GA로 바뀐 지점: 운영 정책으로 박을 수 있게 된 이유
2026-11-23자 BigQuery release notes에 `reservation_override_mode`와 `disable_on_demand_billing`이 GA로 올라왔습니다. 문장 자체는 짧지만, 의미는 큽니다. 이제 BigQuery 비용 통제에서 가장 지저분했던 영역(“예약을 써야 하는데 누군가가 언제든 온디맨드로 빠져버리는 구멍”, “예약 할당이 빠진 프로젝트가 기본값으로 온디맨드를 태워버리는 구멍”)을 실험적 기능이 아니라 표준 운영 정책으로 고정할 수 있게 됐습니다.[^1]

내가 이걸 “FinOps 도구”로 보는 이유는 단순합니다. BigQuery 비용 사고는 대개 쿼리 한두 번이 아니라, (1) 같은 실수가 반복 실행되거나 (2) 자동화가 폭주하거나 (3) 도구/팀이 늘면서 통제가 무력화되는 순간에 커집니다. 비용이 커진 뒤에 원인을 찾는 루프는 이미 늦습니다. 비용 상한선을 “쿼리를 못 돌리게” 강제하는 형태로 가져가야 사고가 줄어듭니다.

이번 GA의 핵심은 옵션 자체가 아니라, 조직/프로젝트 레벨에서 regional default configuration으로 강제할 수 있다는 점입니다. `ALTER ORGANIZATION SET OPTIONS`, `ALTER PROJECT SET OPTIONS`로 “지역 단위” 정책을 박고, `INFORMATION_SCHEMA`로 감사를 자동화할 수 있는 구성이 완성됩니다.[^1]

## 어떤 비용 사고를 막는가: ‘온디맨드 폭주’의 전형
BigQuery에서 비용 사고가 나는 패턴은 크게 두 갈래입니다.

첫째는 온디맨드 모델의 특성입니다. 온디맨드는 처리한 bytes 기반으로 과금되기 때문에, SQL이 “얼마를 스캔하는지”가 곧 비용입니다. 실수로 파티션 필터가 빠지거나, 조인이 폭발하거나, view 체인이 생각보다 두꺼워지거나, external table에서 컬럼 프루닝이 깨지면 요금이 한 번에 튑니다. 이런 류의 문제는 BigQuery 문서에서도 `INFORMATION_SCHEMA.JOBS` 같은 뷰로 원인을 조사하라고 안내합니다.[^2]

둘째는 예약(capacity-based) 환경에서의 우회입니다. 원래는 “이 워크로드는 예약 슬롯에서만 돌려서 월 비용을 고정한다”가 목표인데, 누군가가 세션/잡 레벨에서 예약을 바꿔 온디맨드로 보내거나(혹은 아예 예약 할당이 안 된 프로젝트에서 실행) 다시 bytes 기반 과금이 터집니다. 워크로드가 많아질수록 이 우회는 팀/도구 단위로 생깁니다.

기존에도 “프로젝트를 예약에 할당하면 된다”는 말은 가능했지만, 현실은 달랐습니다.

- 프로젝트가 하나라도 빠지면 그 프로젝트는 기본값으로 온디맨드를 씁니다. “전체 폴더/조직에 할당했으니 괜찮겠지”라고 생각해도, `None` 할당을 섞거나(의도적으로든 실수로든) 새 프로젝트가 엉뚱한 위치에 생기면 구멍이 납니다. BigQuery는 “예약이 없으면 온디맨드”가 기본 동작입니다.[^3]
- 반대로 예약이 있어도, 런타임에 예약을 override하는 기능이 있습니다. 이걸 모르는 상태에서 BI 도구나 SDK가 설정을 건드리면, 예약 기반 비용 상한선이 의미 없어집니다.

이번 GA 두 옵션은 이 두 구멍을 각각 겨냥합니다.

## 옵션의 실제 동작 1: reservation_override_mode가 막는 것
`reservation_override_mode`는 “쿼리가 할당된 예약을 런타임에 override할 수 있는지”를 제어하는 regional option입니다. 값은 세 가지가 핵심입니다.

- `ALLOW_ANY_OVERRIDE`: 모든 override 허용. 여기에는 온디맨드 강제(`'none'`)도 포함됩니다.
- `DENY_OVERRIDE_TO_NONE`(default): 다른 예약으로 override하는 건 허용하지만, 명시적으로 온디맨드 override(`'none'`)는 실패합니다.
- `DENY_ANY_OVERRIDE`: 어떤 override도 실패합니다.

이 정의는 BigQuery GoogleSQL DDL(`ALTER PROJECT/ORGANIZATION SET OPTIONS`) 옵션 목록에 명확히 나옵니다.[^4]

여기서 중요한 포인트는 “온디맨드로 빠지는 경로”가 단일하지 않다는 점입니다. 대표적으로 두 가지가 있습니다.

1) SQL 스크립트/세션에서 `@@reservation`을 건드리는 경로

BigQuery에는 `@@reservation`이라는 system variable이 있고, 이 값을 바꾸면 이후 쿼리들이 어느 예약에서 돌지 선택할 수 있습니다. 그리고 여기서 `'none'`을 지정하면 온디맨드 과금으로 강제됩니다. 문서에 “`'none'`을 주면 on-demand로 강제하며, 이 동작은 `reservation_override_mode=ALLOW_ANY_OVERRIDE`가 필요하다”라고 적혀 있습니다.[^5]

2) API/클라이언트에서 job configuration의 reservation 라우팅을 건드리는 경로

REST API `jobs.query`에도 `reservation` 필드가 있고, `none`을 주면 온디맨드로 강제하며 역시 `reservation_override_mode=ALLOW_ANY_OVERRIDE`가 필요하다고 문서에 나옵니다. 즉, “어떤 팀이 어떤 SDK를 쓰는지”와 무관하게, 플랫폼 레벨에서 허용/차단을 통일할 수 있습니다.[^6]

FinOps 관점에서 내가 보는 `reservation_override_mode`의 역할은 단순합니다.

- 조직 전체는 `DENY_OVERRIDE_TO_NONE`로 두고, 예약 기반 비용 상한선을 지킨다.
- 다만 “아예 override 자체를 원천 봉쇄”해야 하는 규제/감사 성격의 워크로드(예: 재무 마감 집계, 청구 근거 산출)라면 `DENY_ANY_OVERRIDE`까지 고려한다.

여기서 `DENY_ANY_OVERRIDE`를 쓰면 운영이 더 빡빡해집니다. 장애 대응 시 임시로 별도 예약으로 라우팅하거나, 특정 사용자/서비스 계정만 다른 reservation으로 보내는 운영 패턴이 막힙니다. 그래서 나는 기본값은 `DENY_OVERRIDE_TO_NONE`에 가깝다고 봅니다.

## 옵션의 실제 동작 2: disable_on_demand_billing이 막는 것
`disable_on_demand_billing`은 더 직설적입니다. regional option으로 `true`를 주면 “온디맨드 billing 자체를 비활성화”합니다. 문서 표현은 “`true`면 모든 쿼리는 assigned reservation을 써야 하며, 그렇지 않으면 실패한다”입니다.[^4]

이 옵션이 특히 강력한 이유는, BigQuery의 기본 동작을 뒤집기 때문입니다.

- 원래: 예약이 없으면 온디맨드로 실행된다.[^3]
- 이제(옵션 on): 예약이 없으면 실패한다.

이게 비용 사고를 막는 방식은 간단합니다.

- 새 프로젝트가 생성되었는데 예약 할당을 깜빡했다 → 과거에는 조용히 온디맨드가 타면서 비용이 쌓였고, 보통 월말에 발견합니다.
- 이제는 쿼리가 바로 실패하니, 장애 티켓이 먼저 뜹니다. 비용 티켓이 아니라 운영 티켓으로 바뀝니다.

대신 부작용도 뚜렷합니다.

- “샌드박스에서 잠깐 보려고”라는 이유로 온디맨드를 쓰던 문화는 사라집니다.
- 예약이 없는 지역(예: `US`는 예약 있는데 `asia-northeast1`은 없다)에서 쿼리가 돌 수 있던 흐름이 끊깁니다.

이건 나쁘다기보다, 정책으로 의도해야 하는 변화입니다.

## 프로젝트/워크로드별 예약 설계: 상한선은 슬롯에서 나온다
`disable_on_demand_billing=true`는 “온디맨드 과금 폭주”를 막아주지만, 그 자체로 비용 상한선을 만들어주지는 않습니다. 비용 상한선은 결국 예약 슬롯의 크기에서 나옵니다.

BigQuery workload management의 기본 모델은 온디맨드(바이트 과금)와 capacity-based(슬롯 시간 과금) 두 가지이고, 예약/커밋먼트는 후자를 조직적으로 운영하기 위한 장치입니다.[^7]

내가 FinOps 관점에서 추천하는 예약 설계의 목표는 아래 두 가지를 동시에 만족하는 겁니다.

1) 워크로드별로 “최대 소모 가능 컴퓨트”를 예측 가능하게 만든다.
2) 팀 간에 서로의 폭주가 전염되지 않도록 격리한다.

여기서 중요한 도구가 세 가지입니다.

- reservation 단위의 baseline slots / autoscaling / max_slots(예측 가능성)
- assignment(프로젝트/폴더/조직을 어떤 reservation으로 보낼지)
- project caps(= scheduling policies): 프로젝트별 최대 슬롯/동시성 제한

BigQuery 문서에서도 project caps(최대 슬롯, 최대 동시성)가 “특정 프로젝트가 예약 슬롯을 과도하게 소비하지 못하게 한다”고 설명합니다.[^3]

### (1) 조직 전체 기본 reservation + workload별 reservation
현실적인 구조는 보통 이렇습니다.

- `bq-admin`(관리 프로젝트): 커밋먼트/예약을 소유
- `prod-analytics-*`: 서비스/도메인별 쿼리 프로젝트
- `prod-etl-*`: 배치 파이프라인
- `prod-ml-*`: feature/학습
- `sandbox-*`: 실험

여기서 조직/폴더에 default reservation을 깔고, workload별로 별도 reservation을 두는 패턴이 운영 난이도 대비 효과가 좋습니다. 이유는 “새 프로젝트가 늘어나는 속도”를 사람이 못 따라가기 때문입니다.

- 폴더/조직 레벨에 default reservation을 할당해두면, 새 프로젝트는 기본적으로 예약으로 들어갑니다.
- `disable_on_demand_billing=true`면, 예약이 없는 프로젝트는 애초에 쿼리를 못 돌립니다.

예약을 어디까지 쪼갤지는 트레이드오프입니다.

- 너무 크게 묶으면(예약 1개): 팀 A 폭주가 팀 B SLA에 바로 영향을 줍니다.
- 너무 잘게 쪼개면(예약 N개): 커밋먼트/슬롯 운영이 과도하게 복잡해지고, idle slots 공유의 이점을 놓칩니다.

이 균형점은 조직 규모/쿼리 패턴에 따라 다른데, 나는 최소한 “인터랙티브 분석”과 “배치 ETL”은 분리하는 쪽이 안전하다고 봅니다.

### (2) None assignment는 ‘예외’를 만드는 칼이다
BigQuery에서는 assignee를 `None`으로 할당해서 “상위(폴더/조직)의 예약 할당에서 제외”할 수 있습니다. 문서에도 “조직을 예약에 할당하고 일부 프로젝트를 `None`으로 opt-out할 때 유용하다”고 나옵니다.[^3]

이 기능은 유용하지만, 비용 사고 관점에서는 칼날입니다.

- 누군가가 프로젝트를 `None`으로 빼버리면, 그 프로젝트는 온디맨드를 쓰게 됩니다(옵션을 안 걸어두면).
- 그래서 `disable_on_demand_billing=true`와 함께 써야 “None으로 빼도 온디맨드로 폭주하지 않고 즉시 실패”로 끝납니다.

즉, `None assignment`는 “예약에서 제외”이지 “온디맨드 허용”이 아닙니다. 이 차이를 정책으로 강제해야 운영이 깨지지 않습니다.

## 온디맨드 차단의 부작용: 기능/팀별 예외를 어디에 둘 것인가
가드레일은 항상 부작용이 있고, 이 부작용을 설계하지 않으면 우회가 생깁니다.

여기서 말하는 예외는 “정책을 풀어주는 프로젝트/워크로드”를 의미합니다. 예외를 설계할 때 내가 보는 축은 세 가지입니다.

1) 기술적 예외: 기능이 실제로 막히는가
2) 운영적 예외: 장애 대응/마이그레이션에서 임시로 필요한가
3) 조직적 예외: 특정 팀만 온디맨드 권한을 가져야 하는가

### (1) reservation_override_mode가 막는 기능: @@max_staleness_override 같은 설정
BigQuery system variable 문서에 `@@max_staleness_override`는 “프로젝트/조직에 `reservation_override_mode=ALLOW_ANY_OVERRIDE`가 필요”하다고 적혀 있습니다.[^5]

이건 흥미로운 충돌입니다.

- FinOps는 `ALLOW_ANY_OVERRIDE`를 싫어합니다. (온디맨드 override `'none'`까지 열리기 때문)
- 성능/비용 최적화 측면에서는 staleness override 같은 기능이 쓸모가 있을 수 있습니다.

나는 이런 류의 기능이 필요하면 “기능을 위해 가드레일을 푸는” 방식이 아니라, 프로젝트를 분리하는 쪽이 더 낫다고 봅니다.

- 기본 프로젝트(대부분): `DENY_OVERRIDE_TO_NONE`
- staleness override 같은 고급 기능이 필요한 실험 프로젝트: 별도 프로젝트 + 별도 감사 + 별도 예산

### (2) disable_on_demand_billing이 만드는 운영 리스크: 지역/할당 누락은 곧 장애
regional option이라는 점을 과소평가하면 바로 사고가 납니다.

- `region-us.disable_on_demand_billing=true`로 걸었는데
- 실제 쿼리 job location이 `europe-west6`로 실행되거나(데이터셋/커넥션/목적 테이블에 의해 결정)
- 그 지역에는 예약/할당이 없다

그러면 “원래 돌아가던 파이프라인이 갑자기 실패”가 됩니다. BigQuery는 job location이 리소스 위치에 의해 정해질 수 있다고 문서에서 강조합니다.[^8]

그래서 나는 이 옵션을 켤 때 순서를 고정합니다.

1) 지역별 예약/할당을 먼저 완성한다.
2) `disable_on_demand_billing`을 켠다.
3) `INFORMATION_SCHEMA`로 실제 effective 옵션을 점검한다.

### (3) 조직 내 예외는 ‘기술’이 아니라 ‘거버넌스’ 문제다
정책이 강해질수록, 예외는 반드시 생깁니다. 문제는 예외가 기술로 생기면(개별 SDK 설정, 개인용 프로젝트 생성, 임시 스크립트) 추적이 안 된다는 겁니다.

예외는 오히려 표준화해야 합니다.

- 예외 프로젝트는 이름 규칙이 있어야 합니다.
- 접근 권한(누가 쓸 수 있는지)이 제한돼야 합니다.
- 예외의 비용은 별도 예산/별도 chargeback으로 보이게 해야 합니다.

이 흐름은 예전에 내가 LLM structured output에서 “스키마 강제”를 운영 가드레일로 다뤘던 것과 결이 같습니다. 도구가 똑똑해져도, 가드레일을 플랫폼으로 끌어올리지 않으면 사고는 결국 사람이 칩니다.
- `JSON mode + Schema 강제` 관련 정리: `https://daewooki.github.io/posts/llm-structured-output-2026-7-json-mode-s-1/`

## SQL로 정책 박기: ALTER ORGANIZATION/PROJECT SET OPTIONS
이 옵션들은 콘솔에서 클릭으로도 바꿀 수 있지만, 운영 표준으로 만들려면 결국 코드(혹은 최소한 DDL)로 남겨야 합니다.

### (1) 조직 레벨: 기본 가드레일을 regional option으로 고정
조직 설정은 `ALTER ORGANIZATION SET OPTIONS`로 박습니다. 이 DDL은 “현재 프로젝트가 속한 조직”에 적용된다고 문서에 나옵니다.[^9]

아래 예시는 US 멀티리전(`region-us`)을 기준으로, 온디맨드를 원천 차단하고(`disable_on_demand_billing=true`), 예약을 온디맨드로 override하지 못하게 막는(`reservation_override_mode=DENY_OVERRIDE_TO_NONE`) 구성입니다.

```sql
-- BigQuery GoogleSQL
ALTER ORGANIZATION
SET OPTIONS (
  `region-us.disable_on_demand_billing` = TRUE,
  `region-us.reservation_override_mode` = 'DENY_OVERRIDE_TO_NONE'
);
```

정책 적용 권한은 `bigquery.config.update`가 필요하고, 문서에서는 보통 `roles/bigquery.admin`을 전제로 설명합니다.[^8]

### (2) 프로젝트 레벨: 예외를 ‘명시적으로’ 만든다
프로젝트 예외는 `ALTER PROJECT ... SET OPTIONS`로 덮어씌웁니다. 프로젝트 설정이 조직 설정을 override한다는 점도 문서에 적혀 있습니다.[^9]

예를 들어 “break-glass” 성격의 예외 프로젝트에서만 온디맨드를 허용하고 싶다면, 해당 프로젝트에서만 `disable_on_demand_billing=false`로 내립니다.

```sql
ALTER PROJECT `analytics-breakglass`
SET OPTIONS (
  `region-us.disable_on_demand_billing` = FALSE,
  `region-us.reservation_override_mode` = 'ALLOW_ANY_OVERRIDE'
);
```

여기서 `ALLOW_ANY_OVERRIDE`까지 줄지는 고민이 필요합니다.

- 온디맨드를 “기본”으로 쓰게 하고 싶으면 굳이 `@@reservation='none'` override가 필요 없습니다. (그냥 예약 할당을 안 하면 됩니다.)
- 하지만 조직/폴더 레벨에서 예약이 상속되는 구조라면, 예외 프로젝트는 상속을 끊기 위해 `None` assignment를 쓰거나, override 모드를 열어야 하는 상황이 생깁니다.

나는 보통 예외 프로젝트는 “상속을 끊고(None assignment) + 온디맨드 허용(disable=false)” 쪽이 더 명확하다고 봅니다. override 모드까지 여는 순간, 예외의 표면적이 커집니다.

### (3) bq CLI로 실행: CI/CD에 붙이기 쉬운 형태
BigQuery 문서에서도 설정 변경을 `bq query --use_legacy_sql=false`로 실행하는 예시를 제공합니다.[^9]

```bash
# Cloud SDK가 설치돼 있고, bq가 로그인돼 있다고 가정
bq query --use_legacy_sql=false \
  'ALTER ORGANIZATION SET OPTIONS (
     `region-us.disable_on_demand_billing` = TRUE,
     `region-us.reservation_override_mode` = "DENY_OVERRIDE_TO_NONE"
   );'

bq query --use_legacy_sql=false \
  'ALTER PROJECT `analytics-breakglass` SET OPTIONS (
     `region-us.disable_on_demand_billing` = FALSE
   );'
```

실행 결과는 DDL이라 결과 셋이 의미 있게 나오진 않지만(성공/실패가 핵심), 이후 `INFORMATION_SCHEMA`로 검증하면 됩니다.

## Terraform/정책코드화: 예약은 리소스, 가드레일은 DDL
여기서 현실적인 문제가 하나 있습니다.

- 예약(reservation), 할당(assignment)은 Terraform 리소스로 잘 관리됩니다.
- 그런데 조직/프로젝트의 default configuration option(`ALTER ORGANIZATION/PROJECT SET OPTIONS`)은 (적어도 내가 확인한 범위에서는) Terraform에서 “깔끔한 1st-class 리소스”로 떨어지지 않습니다.

그래서 나는 IaC를 두 레이어로 나눕니다.

- **리소스 레이어**: 슬롯/예약/할당은 Terraform로 관리
- **정책 레이어**: 옵션은 DDL을 실행하는 방식으로 멱등 적용 + drift 감시

### (1) Terraform로 reservation 만들기(예측 가능한 max_slots 포함)
BigQuery 문서에서 Terraform 예시로 `google_bigquery_reservation`을 안내합니다. 예측 가능한 reservation을 위해 `max_slots`, `scaling_mode` 같은 필드를 쓰는 예시도 같이 나옵니다.[^10]

```hcl
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.admin_project_id
  region  = "us-central1"
}

provider "google-beta" {
  project = var.admin_project_id
  region  = "us-central1"
}

# 관리 프로젝트가 소유하는 ETL용 예약
resource "google_bigquery_reservation" "etl" {
  provider          = google-beta
  name              = "etl"
  project           = var.admin_project_id
  location          = "us"

  # baseline
  slot_capacity     = 500
  edition           = "ENTERPRISE"

  # 예측 가능성(상한선)
  ignore_idle_slots = true
  max_slots         = 1500
  scaling_mode      = "AUTOSCALE_ONLY"

  # 동시성은 0이면 BigQuery가 동적으로 조절
  concurrency       = 0
}
```

이 코드는 “ETL이 아무리 폭주해도 최대 1500 슬롯 이상은 못 쓴다”는 상한선을 만듭니다. 이게 결국 비용 상한선의 기반입니다. 반대로 말하면, `max_slots`를 안 걸면 ETL은 idle slot까지 빨아먹을 수 있고, 내부적으로는 다른 팀이 느려졌을 때 그게 ‘비용 사고’가 아니라 ‘SLA 사고’로 번집니다.

### (2) Terraform로 assignment 걸기
assignment는 `google_bigquery_reservation_assignment`로 관리합니다. 문서에서도 이 리소스를 안내하고, `none` 할당이 온디맨드라는 점을 명시합니다.[^11]

```hcl
# ETL 프로젝트를 etl 예약으로 보냄
resource "google_bigquery_reservation_assignment" "etl_project" {
  provider     = google-beta
  project      = var.admin_project_id
  location     = "us"
  reservation  = google_bigquery_reservation.etl.name
  job_type     = "QUERY"

  assignee_type = "PROJECT"
  assignee      = "projects/${var.etl_project_id}"
}
```

여기까지가 리소스 레이어입니다.

### (3) 옵션 가드레일은 ‘DDL 실행’로 멱등 적용
옵션은 결국 SQL DDL입니다. 실행 주체는 세 가지 중 하나로 정리됩니다.

- CI에서 `bq query` 실행
- Terraform에서 `null_resource` + `local-exec`로 실행
- 쿠버네티스 기반이면 Config Connector의 `BigQueryJob` 같은 리소스로 스크립트를 실행

Config Connector `BigQueryJob`은 스크립트 옵션(예: statement byte budget) 같은 job 단위 설정을 지원합니다. 즉 “정책을 적용하는 작업 자체”도 잡으로 다룰 수 있습니다.[^12]

Terraform만으로 끝내고 싶다면 이런 패턴이 현실적입니다.

```hcl
resource "null_resource" "org_guardrails_us" {
  # 예약/할당이 먼저 존재해야 disable_on_demand_billing을 켰을 때 장애가 덜 납니다.
  depends_on = [
    google_bigquery_reservation.etl,
    google_bigquery_reservation_assignment.etl_project
  ]

  triggers = {
    # 정책 변경 시에만 재적용되게(멱등이지만 의도 명확화)
    disable_on_demand_billing = "true"
    reservation_override_mode = "DENY_OVERRIDE_TO_NONE"
  }

  provisioner "local-exec" {
    command = <<EOT
bq query --use_legacy_sql=false \
  'ALTER ORGANIZATION SET OPTIONS (
     `region-us.disable_on_demand_billing` = TRUE,
     `region-us.reservation_override_mode` = "DENY_OVERRIDE_TO_NONE"
   );'
EOT
  }
}
```

여기서 핵심은 “DDL을 인프라 리소스처럼 멱등으로 돌린다”입니다. 정책은 결국 상태를 강제해야 하고, BigQuery는 그걸 DDL로 해줍니다.

## 드리프트 감지: INFORMATION_SCHEMA로 ‘정책이 살아 있는지’ 확인
정책을 켰으면, 살아 있는지도 확인해야 합니다. BigQuery는 프로젝트/조직 옵션을 `INFORMATION_SCHEMA`로 조회할 수 있게 해둡니다. 문서에는 세 가지 뷰를 구분해서 설명합니다.

- `PROJECT_OPTIONS`: 프로젝트에 직접 설정된 값
- `EFFECTIVE_PROJECT_OPTIONS`: 조직에서 상속된 값까지 포함한 최종 값
- `ORGANIZATION_OPTIONS`: 조직 설정 값

그리고 “새 설정이 반영되기까지 몇 분 걸릴 수 있다”는 주의도 있습니다.[^8]

### (1) 조직 정책 확인

```sql
-- US 멀티리전 조직 옵션 확인
SELECT
  option_name,
  option_value
FROM
  `region-us`.INFORMATION_SCHEMA.ORGANIZATION_OPTIONS
WHERE
  option_name IN (
    'disable_on_demand_billing',
    'reservation_override_mode'
  );
```

여기서 `disable_on_demand_billing=true`와 `reservation_override_mode=DENY_OVERRIDE_TO_NONE`가 보이면 1차 확인은 끝납니다.

### (2) 프로젝트별 예외/누락 탐지(효과적인 값 기준)
`EFFECTIVE_PROJECT_OPTIONS`는 “조직 + 프로젝트 override 결과”를 보여주기 때문에, 예외 관리에 유리합니다.[^8]

```sql
SELECT
  option_name,
  option_value
FROM
  `region-us`.INFORMATION_SCHEMA.EFFECTIVE_PROJECT_OPTIONS
WHERE
  option_name IN (
    'disable_on_demand_billing',
    'reservation_override_mode'
  );
```

예외 프로젝트에서는 여기 값이 다르게 나와야 합니다. 예외는 “존재 자체가 감사 대상”이기 때문에, 예외 리스트와 이 쿼리 결과를 매칭하는 자동화가 필요합니다.

### (3) 변경 이력까지 감사로 묶기
`PROJECT_OPTIONS_CHANGES`는 “프로젝트 옵션 변경” 이력을 제공합니다. 이 뷰는 2024-01-31 이후 변경부터 반영된다고 문서에 명시돼 있습니다.[^13]

```sql
SELECT
  update_time,
  username,
  changed_options
FROM
  `region-us`.INFORMATION_SCHEMA.PROJECT_OPTIONS_CHANGES
WHERE
  update_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
ORDER BY
  update_time DESC;
```

조직 운영에서 좋은 패턴은 이걸 “보안 이벤트”처럼 다루는 겁니다.

- 누가 가드레일을 껐는지
- 어떤 프로젝트에서 껐는지
- 변경이 티켓/승인 흐름과 연결되는지

이게 비용 사고를 “사후 정산”이 아니라 “사전 통제”로 바꾸는 지점입니다.

## 도입 판단 기준: 언제 켜고 언제 꺼야 하는가
두 옵션을 실제 운영에 넣을 때, 나는 아래 기준으로 결론을 냅니다.

1) 조직이 이미 예약 기반으로 비용을 관리한다면
- `disable_on_demand_billing=true`는 거의 필수에 가깝습니다.
- 단, 지역/프로젝트 할당 설계를 끝내고 켜야 합니다.

2) 예약 기반 운영이지만 일부 팀이 온디맨드를 꼭 써야 한다면
- “팀 단위 예외”를 만들지 않고, “프로젝트 단위 예외”로 고정합니다.
- 예외 프로젝트는 접근권한/예산/감사를 별도로 둡니다.

3) 예약 override를 어디까지 허용할지
- 기본값은 `DENY_OVERRIDE_TO_NONE`이 운영 친화적입니다. (다른 예약으로 라우팅은 허용, 온디맨드는 차단)[^4]
- 규제/감사 성격이 강한 워크로드만 `DENY_ANY_OVERRIDE`로 더 조입니다.

4) 기능 충돌은 정책으로 인정하고 분리한다
- `@@max_staleness_override`처럼 `ALLOW_ANY_OVERRIDE`를 요구하는 기능이 있다면, 그 기능이 진짜 필요한 프로젝트를 분리하는 쪽이 덜 위험합니다.[^5]

정리하면, `disable_on_demand_billing`은 “온디맨드로 새는 구멍을 막는 스위치”이고, `reservation_override_mode`는 “의도적으로 온디맨드로 빠지는 우회로를 막는 스위치”입니다. 이 둘이 GA가 된 2026-11-23 이후에는, BigQuery 비용 사고를 사람이 주의해서 막는 단계가 아니라, 조직 표준으로 쿼리 경로 자체를 통제하는 단계로 넘어가는 게 맞다고 판단합니다.[^1]

## 참고 자료
- BigQuery release notes: `https://docs.cloud.google.com/bigquery/docs/release-notes`
- Manage default configuration settings: `https://docs.cloud.google.com/bigquery/docs/default-configuration`
- Data definition language (DDL) statements in GoogleSQL: `https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/data-definition-language`
- System variables reference(@@reservation 포함): `https://docs.cloud.google.com/bigquery/docs/reference/system-variables`
- Understand reservations / workload management: `https://docs.cloud.google.com/bigquery/docs/reservations-workload-management`
- Manage workload reservations(Terraform 예시 포함): `https://docs.cloud.google.com/bigquery/docs/reservations-tasks`
- Manage workload assignments(Terraform 예시 포함): `https://docs.cloud.google.com/bigquery/docs/reservations-assignments`
- Estimate and control costs: `https://docs.cloud.google.com/bigquery/docs/best-practices-costs`
- Introduction to INFORMATION_SCHEMA: `https://docs.cloud.google.com/bigquery/docs/information-schema-intro`
- PROJECT_OPTIONS view: `https://docs.cloud.google.com/bigquery/docs/information-schema-project-options`
- PROJECT_OPTIONS_CHANGES view: `https://docs.cloud.google.com/bigquery/docs/information-schema-project-options-changes`
- Method: jobs.query(reservation=none 설명): `https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/query`
- Cloud Changelog(2026-11-23 GA 항목): `https://cloudchangelog.com/gcp/2026-11-23-bigquery-feature`

[^1]: <https://docs.cloud.google.com/bigquery/docs/release-notes>
[^2]: <https://docs.cloud.google.com/bigquery/docs/best-practices-costs>
[^3]: <https://docs.cloud.google.com/bigquery/docs/reservations-workload-management>
[^4]: <https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/data-definition-language?hl=en>
[^5]: <https://docs.cloud.google.com/bigquery/docs/reference/system-variables?hl=en>
[^6]: <https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/query?hl=en>
[^7]: <https://docs.cloud.google.com/bigquery/docs/reservations-intro>
[^8]: <https://docs.cloud.google.com/bigquery/docs/default-configuration>
[^9]: <https://docs.cloud.google.com/bigquery/docs/default-configuration?hl=en>
[^10]: <https://docs.cloud.google.com/bigquery/docs/reservations-tasks?hl=en>
[^11]: <https://docs.cloud.google.com/bigquery/docs/reservations-assignments?hl=en>
[^12]: <https://docs.cloud.google.com/config-connector/docs/reference/resource-docs/bigquery/bigqueryjob>
[^13]: <https://docs.cloud.google.com/bigquery/docs/information-schema-project-options-changes>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
