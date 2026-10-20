---
title: "Grafana 13.2 Saved Queries를 Terraform으로 팀 자산화하기"
description: "Saved Queries를 쿼리 라이브러리로 표준화하고 Terraform·RBAC·검증을 묶어 팀 운영 자산으로 굳히는 패턴을 정리합니다."
date: 2026-10-20 10:25:54 +0900
categories: ["Data", "Grafana"]
tags: ["grafana", "saved-queries", "terraform", "rbac", "query-library", "workload-identity-federation"]
render_with_liquid: false
---

## 13.2.4가 던진 신호: 대시보드보다 쿼리 라이브러리가 먼저다

Grafana 13.2.4의 릴리스 날짜가 **2026-10-13**으로 표기되어 있고(13.2.x 라인), 지금(2026-10-20 KST) 기준으로 일주일이 지나지 않은 상태입니다. [Grafana 13.2.4 다운로드 페이지](https://grafana.com/grafana/download/13.2.4?edition=oss)와 [GitHub Releases의 13.2.4 아티팩트 타임스탬프](https://github.com/grafana/grafana/releases?after=v4.0.0)에서 날짜/업로드 시각을 같이 확인할 수 있습니다.

이 시점이 흥미로운 이유는 두 가지가 겹쳤기 때문입니다.

- 13.2에서 Saved queries가 GA로 올라오면서, Grafana가 쿼리를 조직 단위 지식으로 다루기 시작했습니다. Saved queries를 command palette에서 바로 열고, Terraform으로 프로비저닝할 수 있다는 메시지를 공식적으로 명시했습니다[^1][^2].
- 같은 13.2 릴리스 하이라이트에 BigQuery/Google Cloud Monitoring에서 Workload Identity Federation 인증을 Grafana Cloud에서 지원한다는 변화가 들어가 있습니다[^1]. 인증이 바뀌는 시기는 운영 표준을 재정의하기 가장 좋습니다.

대시보드는 발표 자료/운영 화면으로서 중요하지만, 팀이 실제로 오래 고생하는 건 대시보드 JSON이 아니라 쿼리 지식의 분산입니다. 쿼리 라이브러리를 먼저 표준화해두면 다음이 달라집니다.

- 온보딩이 대시보드 따라하기에서 쿼리 재사용으로 이동합니다.
- 플랫폼/SRE가 데이터 소스별 쿼리 품질(비용, 성능, 안전성)을 표준화할 수 있습니다.
- 이후 대시보드/알림/자동화가 쿼리 라이브러리를 참조하는 형태로 단순화됩니다.

이 글은 Saved Queries를 팀 자산으로 굳히기 위한 운영 패턴을 IaC(Terraform) 관점에서 정리합니다.

## Saved Queries의 실체: 개인 히스토리와 조직 라이브러리를 분리해서 생각해야 한다

Grafana Explore에는 오래전부터 Query history가 있습니다. Query history는 “내가 최근에 실행한 쿼리”의 흔적이고, 기본 보존 기간이 2주이며, 개인 단위로 저장되고 공유되지 않습니다[^3]. Star를 찍어두면 2주 보존 규칙에서 제외된다는 디테일도 문서에 있습니다[^3].

Saved queries는 방향이 반대입니다.

- Grafana 13.2의 메시지는 Saved queries를 조직이 재사용하는 query library로 격상시키는 쪽입니다[^1].
- Saved queries는 Grafana Enterprise와 Grafana Cloud에서만 제공된다고 명시되어 있습니다[^4][^5].

여기서 자주 생기는 오해가 하나 있습니다. 문서에는 “서버 사이드 query library”와 “브라우저 local storage” 두 가지 저장 방식이 언급됩니다. queryLibrary feature toggle이 켜진 Grafana 12.4+에서 서버 사이드 query library에 저장되고, 그렇지 않으면 로컬 저장소에 저장된다고 설명합니다[^6]. 이 설명만 보면 OSS에서도 토글로 가능해 보이지만, 같은 시기 다른 문서에서는 Saved queries 자체가 Enterprise/Cloud 전용이라고 명시합니다[^4]. 운영 표준을 세울 때는 “팀 자산”이 되는 서버 사이드 query library를 전제로 잡는 편이 안전합니다.

내 결론은 간단합니다.

- Query history는 개인 생산성 도구입니다.
- Saved queries는 조직 표준화 도구입니다.
- 조직 표준화라면 UI에서 저장하는 행위가 아니라, 코드로 관리되는 자산이 되어야 합니다.

## Saved Queries를 팀 자산으로 만들 때의 최소 요건: RBAC + IaC + 검증

Grafana가 Saved queries를 GA로 올리면서, 두 가지를 같이 넣었습니다.

- command palette에서 Saved queries 접근[^1]
- Terraform으로 Saved queries provisioning[^1][^5]

이건 기능 홍보가 아니라 운영 모델 변화에 가깝습니다. 하지만 기능이 생겼다고 자동으로 “팀 자산”이 되지는 않습니다. 팀 자산이 되려면 최소 요건이 있습니다.

1) 권한이 분리되어야 합니다.

Saved queries는 RBAC를 지원하고, Writer/Reader 역할로 관리할 수 있습니다. Saved queries가 기본적으로 공유되고, Writer만 create/update/delete가 가능하며 Reader는 재사용만 가능하다는 설명이 있습니다[^7]. 또한 기본 역할과 고정 역할의 매핑에서 `fixed:queries:reader`, `fixed:queries:writer`가 등장합니다[^8].

2) IaC로 동일성이 보장돼야 합니다.

Saved queries는 저장 시 validation이 수행되지 않는다고 문서가 명시합니다. 즉 UI 저장은 실수의 비용이 큽니다[^4]. 대신 Terraform으로 리소스로 만들 수 있고, provider 최소 버전도 안내합니다[^5].

3) 검증이 파이프라인으로 묶여야 합니다.

Saved queries는 저장 시 validation이 없고, 최대 1000개 제한도 명시되어 있습니다[^4]. 팀 자산이 되려면 “저장할 수 있다”가 아니라 “저장되면 안전하다”가 되어야 합니다. 그래서 PR 단계에서 형식/비용/권한/데이터 소스 drift를 묶어야 합니다.

## Terraform 리소스로 본 Saved Queries의 내부 구조: grafana_apps_queries_query_v1

Grafana가 Saved queries를 Terraform으로 관리할 수 있게 만든 방식은 기존 `/api` 계열 legacy endpoint를 직접 두드리는 접근이 아니라, App Platform API 리소스로 노출하는 접근입니다. Terraform 리소스 이름이 이를 노골적으로 보여줍니다.

- `grafana_apps_queries_query_v1` (Saved Queries / Query Library)

공식 가이드는 Saved queries를 Terraform으로 관리하는 방법을 그대로 제공합니다[^5]. 여기서 핵심은 Saved query가 “데이터 소스별 쿼리 JSON”을 raw JSON string으로 들고 있다는 점입니다.

- `targets.properties_json`는 datasource query를 `jsonencode()`로 문자열로 넣습니다[^5].
- Terraform provider 문서(소스 리포지토리의 생성된 문서)에는 더 구체적으로, `targets.variables_json`, `vars.value_list_definition_json`도 raw JSON string이라는 점이 명시되어 있습니다[^9].

스키마에서 운영적으로 중요한 필드를 뽑으면 다음입니다.

- `metadata.uid`: 쿼리의 영구 식별자입니다. UI에서 제목을 바꿔도 UID는 유지되어야 합니다[^9].
- `metadata.folder_uid`: Saved queries도 폴더에 귀속될 수 있음을 시사합니다(리소스에 필드가 존재). 지원 여부는 리소스별 문서를 확인하라고 되어 있습니다[^9].
- `spec.is_locked`: UI 편집을 막는 표시지만, 보안 기능이 아니라고 문서가 분명히 말합니다[^5][^9].
- `options.manager_identity`: 어떤 Terraform workspace가 관리하는지 스탬프를 바꿀 수 있습니다. 여러 팀/환경이 한 Grafana를 공유하면 이게 생각보다 중요합니다[^9].
- `options.overwrite`: “같은 UID/폴더 내 같은 title” 등의 충돌 상황에서 overwrite 동작을 제어합니다[^9].

운영 관점에서 결론은 이겁니다.

Saved queries는 “PromQL/SQL 문자열”이 아니라 “데이터 소스 플러그인의 쿼리 오브젝트”를 보관합니다. 그래서 팀 표준화는 쿼리 문자열만 lint하는 수준으로 끝나면 안 되고, datasource uid/type, refId, 변수 치환까지 포함한 오브젝트 계약으로 봐야 합니다.

## 운영 패턴: Saved Queries를 코드로 만들고, 온보딩을 PR 머지로 바꾸기

여기서는 Grafana Cloud 또는 Grafana Enterprise를 전제로 합니다(문서에서 Saved queries 제공 범위를 그렇게 정의합니다). 아래 예시는 “대시보드를 먼저 깔아두는” 방식이 아니라 “쿼리 라이브러리를 먼저 깔아두는” 방식입니다.

### 디렉터리 구조

```
./grafana-querylib/
  main.tf
  datasources.tf
  saved-queries.prometheus.tf
  saved-queries.bigquery.tf
  rbac.tf
  outputs.tf
```

- Saved queries는 데이터 소스와 강하게 결합되어 있으니 데이터 소스별 파일로 쪼개는 편이 PR 리뷰가 쉽습니다.
- 쿼리 라이브러리가 먼저고 대시보드는 그 다음입니다. 대시보드 IaC는 별도 리포지토리로 분리해도 됩니다.

### main.tf: provider 고정과 버전 핀

Saved queries 가이드는 provider 버전을 `>= 4.44.0`로 명시합니다[^5]. 운영에서는 “최소 버전”을 그대로 쓰기보다, 팀이 검증한 버전을 pinning하고 계획된 창에서만 올리는 게 안전합니다. 이 부분은 예전에 정리한 체크리스트/방어 기법을 그대로 재사용하는 편이 낫습니다[^10][^11].

```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      # 운영에서는 팀 검증 버전으로 pinning하는 편이 낫습니다.
      version = "~> 4.45" 
    }
  }
}

# 권장: 환경 변수로 주입
# export GRAFANA_URL="https://<your-stack>.grafana.net"
# export GRAFANA_AUTH="<service-account-token>"
provider "grafana" {}
```

- Grafana Cloud/Enterprise에서 service account token 기반으로 provider 인증을 쓰는 흐름은 RBAC Terraform 문서에서도 반복됩니다[^12].

### datasources.tf: datasource uid를 코드에서 고정하기

Saved query는 `datasource.uid`를 직접 들고 있습니다. 운영에서 가장 흔한 사고는 datasource 재생성/이관/이름 변경으로 UID가 바뀌는 순간, 쿼리 라이브러리가 조용히 깨지는 형태입니다.

Terraform provider는 datasource를 data source로 조회할 수 있습니다[^13].

```hcl
# 이미 존재하는 datasource를 name 또는 uid로 조회
# name은 사람이 바꾸기 쉬우니, 가능하면 uid로 조회해 고정합니다.
data "grafana_data_source" "prometheus" {
  uid = var.prometheus_datasource_uid
}

variable "prometheus_datasource_uid" {
  type        = string
  description = "Grafana datasource UID for Prometheus/Mimir"
}
```

이렇게 하면 Saved query 작성자가 `uid`를 하드코딩하지 않고도 참조할 수 있고, 환경(dev/stage/prod)별로 uid가 다르면 변수로 분리할 수 있습니다.

### saved-queries.prometheus.tf: 실제로 쓸만한 Saved query 예시

여기서는 SRE/플랫폼 팀이 공통으로 쓰는 “요청량/오류율/지연” 계열을 예로 듭니다. 장난감 예제가 아니라, 실제로 팀에서 쿼리 재사용 가치가 큰 타입입니다.

```hcl
resource "grafana_apps_queries_query_v1" "http_rps" {
  metadata {
    uid = "svc-http-rps"
  }

  options {
    manager_identity = "platform-querylib"
    overwrite        = true
  }

  spec {
    title       = "HTTP requests per second"
    description = "서비스별 RPS. 대시보드/알림에서 공통으로 재사용하는 표준 쿼리."

    # UI에서 수정 불가처럼 보이게 만들지만, 보안 기능이 아닙니다.
    # 권한 통제는 RBAC로 해야 합니다.
    is_locked  = true
    is_visible = true

    tags = ["sre", "http", "golden-signal", "prometheus"]

    vars {
      key            = "service"
      default_values = ["api"]

      # 변수 값 목록을 어떻게 채울지는 datasource마다 다르기 때문에 raw JSON입니다.
      # 여기서는 예시로만 두고, 실제 팀 환경의 conventions에 맞게 정의하는 편이 낫습니다.
      # value_list_definition_json = jsonencode({...})
    }

    targets {
      properties_json = jsonencode({
        refId = "A"
        expr  = "sum by (service) (rate(http_requests_total{service=\"$service\"}[$__rate_interval]))"
        datasource = {
          type = data.grafana_data_source.prometheus.type
          uid  = data.grafana_data_source.prometheus.uid
        }
      })
    }
  }
}
```

이 리소스 형태는 Grafana 공식 가이드의 구조를 그대로 따릅니다[^5]. 또한 `options.manager_identity`, `options.overwrite`, `is_locked`의 의미는 provider 리소스 문서에서 확인할 수 있습니다[^9].

### 실행

```bash
export GRAFANA_URL="https://<your-stack>.grafana.net"
export GRAFANA_AUTH="<service-account-token>"

terraform init
terraform plan -out tfplan
terraform apply tfplan
```

예상되는 결과는 “Saved query 리소스가 1개 생성”되는 단순한 형태입니다.

```
Plan: 1 to add, 0 to change, 0 to destroy.
...
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

이 단계에서 운영적으로 중요한 건 apply 결과가 아니라, 이 Saved query가 UI에서 “팀이 찾을 수 있는 위치”에 나타나고, command palette에서도 검색 가능해지는 동작 자체입니다. Grafana는 Saved queries를 command palette에서 접근할 수 있다고 13.2 하이라이트에 명시합니다[^1].

## 권한 모델: fixed:queries:*를 팀 단위로 끊고, Editor 기본 권한은 그대로 믿지 않는다

Saved queries가 팀 자산이 되는 순간, 가장 먼저 터지는 갈등은 “누가 쓰게 할 것인가”가 아니라 “누가 고치게 할 것인가”입니다.

문서 기준으로 Saved queries에는 기본적으로 Reader/Writer 역할이 있고[^4], 고정 역할 정의에 `fixed:queries:reader`, `fixed:queries:writer`가 존재합니다[^8].

여기서 함정은, 기본 조직 역할(Editor 등)이 이미 `fixed:queries:writer`를 포함할 수 있다는 점입니다(기본 역할 매핑 테이블에 Editor가 `fixed:queries:writer`를 포함한다고 나옵니다)[^8]. 즉, 조직 내 Editor가 많은 환경이라면 쿼리 라이브러리가 금방 공동 편집장 상태가 됩니다.

내가 선호하는 운영 패턴은 다음 중 하나입니다.

- **패턴 A: Curator 팀을 만들고, Saved queries Writer를 그 팀에만 부여**
  - 대부분의 사용자는 Reader
  - Curator만 Writer
  - 조직 역할은 Viewer로 두고, 필요한 기능은 고정 역할로 쌓아 올리는 방식
- 패턴 B: Editor는 유지하되, Saved queries 변경은 Terraform만 허용하는 운영 규율
  - 기술적으로 완전 강제는 어렵지만(사람 권한이 살아있으면 UI 수정이 가능), 조직 문화로 막는 방식

강제력이 필요한 팀이면 패턴 A가 맞습니다. 이때 RBAC를 Terraform으로 관리하면, Saved queries와 권한을 같은 PR에서 묶을 수 있습니다.

Grafana는 RBAC를 Terraform으로 프로비저닝하는 공식 문서를 제공합니다[^12]. 여기에는 팀 생성(`grafana_team`)과 역할 할당(`grafana_role_assignment`) 예시가 들어 있습니다[^12].

```hcl
resource "grafana_team" "query_curators" {
  name = "query-curators"
}

# Saved queries Writer를 팀에 부여
resource "grafana_role_assignment" "query_curators_writer" {
  role_uid = "fixed:queries:writer"
  teams    = [grafana_team.query_curators.id]
}

# 전사 기본은 Reader로 두고 싶다면, 별도 team을 두거나 IdP 그룹 동기화로 처리합니다.
resource "grafana_team" "everyone" {
  name = "everyone"
}

resource "grafana_role_assignment" "everyone_reader" {
  role_uid = "fixed:queries:reader"
  teams    = [grafana_team.everyone.id]
}
```

이 접근의 장점은 분명합니다.

- Saved queries Writer 권한이 누수되기 시작하면, Grafana 화면이 아니라 Git diff로 추적할 수 있습니다.
- 온보딩은 “당신을 Editor로 올려드립니다”가 아니라 “당신을 Reader 팀에 넣습니다”로 바뀝니다.

Grafana Cloud에서 역할/사용자 온보딩이 SCIM/OIDC 매핑으로 흘러가는 환경이라면, Terraform은 팀/역할 연결만 authoritative하게 들고, “팀에 누가 들어오는지”는 IdP 동기화로 보내는 편이 깔끔합니다. 팀/외부 그룹 동기화를 Terraform으로 다룰 수 있다는 흐름은 Grafana 학습 문서에도 있습니다[^14].

## 검증: Saved queries는 저장 시 검증이 없으니, PR에서 깨뜨릴 수 있어야 한다

Grafana 문서에 “Saved queries 저장 시 validation이 없다”가 명시되어 있습니다[^4]. 팀 자산으로 만들려면, 이 빈칸을 운영이 채워야 합니다.

검증을 “Grafana에 apply한 다음 UI에서 눌러보기”로 끝내면, 쿼리 라이브러리는 결국 대시보드와 똑같은 운명을 맞습니다. PR 단계에서 최소한 다음을 자동화하는 편이 낫습니다.

### 1) 쿼리 형식 검증과 포매팅

데이터 소스별로 포매터/파서가 다릅니다. Saved queries는 멀티 데이터 소스를 담을 수 있으니, 타겟별로 검증기를 붙여야 합니다.

- LogQL은 Loki가 제공하는 `format_query` endpoint를 활용해 “문법적으로 유효한지 + 표준 포맷으로 정규화되는지”를 확인할 수 있습니다[^15].
- PromQL 계열은 Prometheus/Mimir 쪽에서 실행 테스트로 검증하는 게 현실적입니다. Mimir는 Prometheus 호환 query endpoint(`/api/v1/query`, `/api/v1/query_range`)를 문서화합니다[^16].

여기서 포인트는 “Grafana가 Saved query 저장을 막아주지 않는다”는 사실을 받아들이고, 저장 전에 팀이 막겠다는 쪽으로 계약을 바꾸는 것입니다.

### 2) datasource uid/type drift 검증

Saved query는 `datasource.uid`에 묶여 있습니다[^5]. 따라서 PR 검증 단계에서 다음을 체크하는 게 좋습니다.

- `data.grafana_data_source.*.uid`가 실제로 존재하는지
- 같은 이름의 datasource가 여러 개면(이관 과정에서 흔함) name lookup을 금지하고 uid lookup만 허용하기

이 검증은 Terraform plan 자체가 상당 부분 대신해줍니다.

### 3) 변수 치환 계약 검증

Saved queries는 변수 치환을 지원하고, 재사용 시 원래 변수를 대시보드 변수 또는 값으로 매핑할 수 있다고 문서가 설명합니다[^4].

변수 치환이 들어가는 순간, 쿼리 라이브러리는 “재사용성”을 얻는 대신 “가독성/추론 가능성”을 잃습니다. 그래서 운영 규칙을 명시적으로 두는 편이 낫습니다.

- 변수 key 네이밍을 표준화 (`service`, `cluster`, `namespace` 같은 공통 key)
- default_values를 반드시 두기(대시보드에 매핑이 실패해도 Explore에서 즉시 실행 가능)
- 변수의 의미를 description에 포함하기

### 4) API 변화 감시: /api → /apis

Grafana 13부터 `/api` endpoint가 `/apis`로 대체되는 흐름이 문서에 명시되어 있습니다. 기존 `/api`는 당장 깨지지 않지만 더 이상 업데이트되지 않는다고 설명합니다[^17].

이건 Saved queries 운영에도 영향을 줍니다.

- 사내 스크립트로 Grafana API를 직접 때려서 Saved queries를 조작하기 시작하면, 어느 순간 legacy endpoint에 매달려 버립니다.
- Terraform provider가 App Platform API 리소스로 Saved queries를 다루는 이유가 여기서 납득됩니다[^9].

개인적으로는 Saved queries 조작을 “사내 API 클라이언트 개발”로 시작하는 건 지금 시점에서는 손해라고 봅니다. Grafana가 API 버전 전환을 진행 중인 상황에서, 팀 자산은 provider에 태우는 게 유지보수 비용이 낮습니다.

Grafana는 HTTP API 스펙을 Grafana 인스턴스의 `/swagger`에서 확인할 수 있다고 안내합니다[^18]. 어떤 조직은 이걸 이용해 사내 검증기를 만들기도 하지만, 그건 provider가 커버하지 못하는 영역이 남았을 때로 미루는 편이 낫습니다.

## 인증 변화(WIF): long-lived secret를 줄이는 대신, 실행 주체 제약을 운영 계약으로 박아야 한다

Grafana 13.2 하이라이트에는 BigQuery/Google Cloud Monitoring이 Grafana Cloud에서 Workload Identity Federation 인증을 지원한다는 내용이 포함되어 있습니다[^1].

Google Cloud Monitoring 데이터 소스 문서는 WIF를 “Grafana Cloud에서 외부 OIDC IdP 토큰을 Google access token으로 교환해 short-lived credential로 동작”시키는 방식으로 설명합니다[^19].

여기서 Saved queries 운영과 맞물리는 지점은 제약사항입니다. 문서는 WIF 기반 credential이 사용자 세션에 묶여 있어 “사용자 없이 실행되는 기능(alerting, scheduled reports, public dashboards 등)”이 동작하지 않는다고 명시합니다[^19].

이 제약은 Saved queries를 팀 자산으로 만들 때 오히려 좋은 가드레일이 됩니다.

- Saved queries는 재사용을 쉽게 만들지만, 동시에 비용 폭발/권한 오남용의 위험도 키웁니다.
- WIF는 “누가 실행했는지”가 분명해지고, 사람이 없으면 실행이 안 됩니다. 플랫폼 팀이 운영 계약을 정하기 쉬워집니다.

대신 트레이드오프는 분명합니다.

- 팀이 Saved queries를 알림/리포팅으로 자동 재사용하고 싶으면, WIF만으로는 부족하고 service account 계열 인증이 필요해집니다.
- 즉, Saved queries를 팀 자산으로 만들면서 “이 쿼리는 human-in-the-loop 탐색용인지, 자동 실행용인지”를 태그/폴더/권한으로 나누는 모델이 필요합니다.

WIF 자체의 배경(외부 IdP와 federated identity로 short-lived credential을 얻어 long-lived credential 회전을 줄임)은 Google Cloud 문서에서도 반복됩니다[^20].

내 판단은 이렇습니다.

- 탐색/온보딩/트러블슈팅 중심의 query library는 WIF가 잘 맞습니다.
- 자동 실행(알림/리포트/배치)을 염두에 둔 query library라면, WIF 도입과 동시에 실행 주체를 별도로 설계해야 합니다.

## 함정과 트레이드오프: Saved Queries를 표준화할수록 더 위험해지는 것들

1) is_locked는 보안이 아닙니다.

문서가 반복해서 말합니다. `is_locked`는 UI 표시용이고, 권한 통제는 RBAC로 해야 합니다[^5][^9].

2) 저장 시 validation이 없습니다.

즉, UI로 저장하면 망가진 쿼리가 자산으로 영구 보존됩니다[^4]. 이건 Terraform을 써도 해결되지 않습니다. Terraform은 “동일성”을 보장할 뿐 “정당성”을 보장하지 않습니다.

3) 1000개 제한이 있습니다.

Saved queries 최대 1000개 제한이 문서에 있습니다[^4]. 조직 규모가 커지면 금방 닿는 숫자입니다. 그래서 초기에 분류/중복 제거 전략이 필요합니다.

4) query history와 saved queries는 성격이 다릅니다.

Query history는 2주 보존이고 개인 저장입니다[^3]. 반면 Saved queries는 조직 자산이고, RBAC로 관리됩니다[^7]. 이 둘을 혼용하면 “개인 실험”이 “공식 자산”으로 승격되는 순간이 통제되지 않습니다.

내 경우에는 다음 규칙을 둡니다.

- Query history star는 개인 생산성 범위
- Saved queries 등록은 PR 승인 범위

5) Grafana Cloud에서 사용자 조직 역할을 Terraform로 완전히 관리할 수 없다

RBAC Terraform 문서에는 Grafana Cloud에서 `grafana_organization`이 지원되지 않으며, 개별 사용자 org role을 Terraform으로 설정하는 리소스가 없다고 명시합니다[^12]. 따라서 온보딩은 SCIM/OIDC role mapping 같은 IdP 연동과 함께 설계해야 합니다.

## 도입 판단 기준: Saved Queries 표준화가 맞는 팀, 아직 이른 팀

Saved queries를 쿼리 라이브러리로 표준화하는 게 특히 잘 맞는 팀은 다음 특성이 있습니다.

- 데이터 소스가 여러 개고(Prod/Stage, 멀티 클러스터, 멀티 프로젝트), 팀마다 쿼리 관용구가 다르게 굳어져 있다.
- 온보딩 비용이 대시보드 사용법이 아니라 “어떤 metric/log/trace를 믿을 수 있는지”에 묶여 있다.
- 비용/성능 리스크가 큰 데이터 소스(BigQuery 같은)를 Grafana로 탐색하고, 잘못된 쿼리가 곧바로 비용 사고로 이어질 수 있다.
- SRE/플랫폼이 조직 공통 golden signal을 표준화해야 한다.

반대로 아직 이른 팀도 있습니다.

- Grafana 자체의 폴더/대시보드 권한도 정리되지 않았고, 누가 무엇을 소유하는지 합의가 없다.
- 데이터 소스 권한이 광범위하고, Grafana 계정이 곧 데이터 소스 전체 권한으로 이어지는 구조다.
- IaC 파이프라인(버전 핀, 검증, 릴리스 창)이 아직 없다.

Saved queries는 “편하게 저장”이 아니라 “자산화”의 시작입니다. Grafana 13.2가 Saved queries GA와 Terraform provisioning을 같은 문장에서 말한 이유는, 저장 기능이 아니라 운영 체계를 요구하는 기능이기 때문이라고 봅니다[^1].

## 참고 자료

- [What’s new in Grafana v13.2](https://grafana.com/docs/grafana/latest/whatsnew/whats-new-in-v13-2/)
- [Grafana 13.2 릴리스 블로그](https://grafana.com/blog/grafana-13-2-release-all-the-latest-features/)
- [Grafana 13.2.4 다운로드 페이지(Release Date: 2026-10-13)](https://grafana.com/grafana/download/13.2.4?edition=oss)
- [Grafana GitHub Releases (13.2.4 아티팩트 업로드 시각)](https://github.com/grafana/grafana/releases?after=v4.0.0)
- [Manage saved queries using Terraform](https://grafana.com/docs/grafana/latest/as-code/infrastructure-as-code/terraform/manage-saved-queries/)
- [grafana_apps_queries_query_v1 리소스 문서(raw)](https://raw.githubusercontent.com/grafana/terraform-provider-grafana/main/docs/resources/apps_queries_query_v1.md)
- [Query and transform data (Saved queries 섹션)](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/query-transform-data/)
- [Role-based access control for saved queries](https://grafana.com/whats-new/2026-02-17-role-based-access-control-for-saved-queries/)
- [Basic and fixed roles permissions (fixed:queries:reader/writer)](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/access-control/rbac-fixed-basic-role-definitions/)
- [Provisioning RBAC with Terraform](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/access-control/rbac-terraform-provisioning/)
- [Google authentication (Grafana Cloud) - Workload Identity Federation](https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources/google-cloud-monitoring/google-authentication/)
- [Configure Workload Identity Federation with other identity providers (Google Cloud)](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers)
- [Query management in Explore (Query history 보존/성격)](https://grafana.com/docs/grafana/latest/visualizations/explore/query-management/)
- [Query History HTTP API (/api → /apis deprecation note)](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/query_history/)
- [Grafana HTTP API 문서(/swagger 안내)](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/)
- [Grafana Mimir HTTP API (Prometheus 호환 query endpoint)](https://grafana.com/docs/mimir/latest/references/http-api/)
- [Loki HTTP API (format_query)](https://github.com/grafana/loki/blob/main/docs/sources/reference/loki-http-api.md)
- [Grafana 패치 업그레이드 검증 자동화 설계](https://daewooki.github.io/posts/grafana-patch-upgrade-automation/)
- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)
- [Terraform 1.16.1 import/panic 버그와 IaC 파이프라인 방어](https://daewooki.github.io/posts/terraform-import-panic-pipeline-guardrails/)

[^1]: <https://grafana.com/docs/grafana/latest/whatsnew/whats-new-in-v13-2/>
[^2]: <https://grafana.com/blog/grafana-13-2-release-all-the-latest-features/>
[^3]: <https://grafana.com/docs/grafana/latest/visualizations/explore/query-management/>
[^4]: <https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/query-transform-data/>
[^5]: <https://grafana.com/docs/grafana/latest/as-code/infrastructure-as-code/terraform/manage-saved-queries/>
[^6]: <https://grafana.com/docs/grafana/latest/visualizations/simplified-exploration/traces/investigate/save-load-queries/>
[^7]: <https://grafana.com/whats-new/2026-02-17-role-based-access-control-for-saved-queries/>
[^8]: <https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/access-control/rbac-fixed-basic-role-definitions/>
[^9]: <https://raw.githubusercontent.com/grafana/terraform-provider-grafana/main/docs/resources/apps_queries_query_v1.md>
[^10]: <https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/>
[^11]: <https://daewooki.github.io/posts/terraform-import-panic-pipeline-guardrails/>
[^12]: <https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/access-control/rbac-terraform-provisioning/>
[^13]: <https://registry.terraform.io/providers/grafana/grafana/latest/docs/data-sources/data_source>
[^14]: <https://grafana.com/docs/learning-paths/configure-grafana-terraform/create-teams/>
[^15]: <https://github.com/grafana/loki/blob/main/docs/sources/reference/loki-http-api.md>
[^16]: <https://grafana.com/docs/mimir/latest/references/http-api/>
[^17]: <https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/query_history/>
[^18]: <https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/>
[^19]: <https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources/google-cloud-monitoring/google-authentication/>
[^20]: <https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
