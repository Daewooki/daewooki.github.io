---
title: "TrailBase CVE에서 배우는 user-controlled key 권한 붕괴"
description: "CVE-2026-119759를 계기로 user-controlled key가 authorization을 무너뜨리는 패턴, 부정 케이스 테스트, 릴리스 노트 트리아지를 정리합니다."
date: 2026-11-23 12:27:58 +0900
categories: ["Backend", "Authorization"]
tags: ["api-security", "authorization", "cve-triage", "negative-testing", "api-gateway"]
render_with_liquid: false
---

## TrailBase CVE-2026-119759가 보여 준 실패 지점

TrailBase 권한 우회 이슈(CVE-2026-119759)는 표면적으로는 IDOR 계열입니다. 다만 “ID가 노출됐다” 같은 이야기로 축약하면, 재발 방지에 필요한 설계 포인트가 사라집니다.

보안 뉴스레터에서 이 CVE가 **CWE-639(Authorization Bypass Through User-Controlled Key)** 로 분류되어 소개됐고, 영향 버전이 `0.28.2 before 0.35.10`으로 정리되어 있습니다. 동일 문서에서 수정 버전으로 `0.35.10` 릴리스 링크를 함께 붙였습니다. [NCSA Newsletter(2026-11-07~2026-11-10)](https://cyber.gov.gr/wp-content/uploads/2026/11/NCSA_Newsletter_2026-11-07_to_2026-11-10.pdf)

VulnCheck의 advisory는 훨씬 구체적으로, `std.FileUpload` 컬럼의 메타데이터에 들어가는 object-store file id를 Record API가 insert/update에서 받아들이면서 ownership validation을 하지 않았다고 설명합니다. 공격자는 자신이 쓸 수 있는 레코드의 파일 메타데이터에 피해자의 file id를 “참조”로 심어두고, 그 결과로 피해자의 파일을 읽거나(바이트를 제공받거나) 삭제/고아화(orphan)까지 유발할 수 있다고 되어 있습니다. 또한 `$like` 필터를 이용해 “stripped id”를 오라클처럼 복구하는 시나리오도 언급됩니다. [VulnCheck advisory: TrailBase IDOR via Record API File Column](https://www.vulncheck.com/advisories/trailbase-idor-via-record-api-file-column)

TrailBase 쪽 릴리스 노트(0.35.10)는 이 이슈를 “read-only file의 internal id가 list API로 오라클링될 수 있고 삭제까지 가능했다”는 문장으로 요약합니다. 한 문장이지만, 설계 관점에서 중요한 단서가 다 들어 있습니다. “read-only”라는 속성(권한 정책), “internal id”(내부 식별자), “list API”(검색/필터), “oracle”(부분 정보 누출을 통한 복구), “deleted”(상태 전이/부작용)입니다. [TrailBase v0.35.10 릴리스 노트](https://github.com/trailbaseio/trailbase/releases/tag/v0.35.10)

이 글의 핵심은 TrailBase 패치 안내가 아닙니다. TrailBase를 쓰지 않더라도, 인증은 통과했는데 권한이 무너지는 이슈는 같은 모양으로 반복됩니다. 내 경험상 이런 사고는 코드 한 줄이 아니라 경계(boundary) 설계가 원인인 경우가 많았습니다.

## user-controlled key가 authorization에 끼어드는 취약점 패턴

CWE-639의 정의는 단순합니다. “한 사용자가 key 값을 바꿔서 다른 사용자 레코드/데이터에 접근한다”입니다. 중요한 건 **key가 반드시 ‘추측 가능한 숫자 ID’일 필요가 없다는 점**입니다. UUID든 base64든, 길고 랜덤해 보여도 권한 검증이 누락되면 본질은 같습니다. [MITRE CWE-639 정의](https://cwe.mitre.org/data/definitions/639.html)

현장에서 자주 보던 패턴을 “user-controlled key”라는 관점으로 분해하면 다음과 같습니다.

### 1) lookup key와 authorization scope가 분리되어 떠다닌다

- lookup key: DB 조회나 object store 조회에 쓰는 값(예: `file_id`, `record_id`, `tenant_id`)
- authorization scope: 권한 판정의 기준이 되는 값(예: `user_id`, `tenant_id`, `role`, `capability`)

문제가 되는 순간은 보통 이렇습니다.

1. 클라이언트가 요청 본문/쿼리/헤더/경로에 key를 넣는다.
2. 서버가 그 key로 조회한다.
3. 서버가 “요청자는 인증됨”을 이유로 조회 결과를 반환하거나, 업데이트/삭제 같은 부작용을 수행한다.
4. key가 가리키는 대상과 요청자(또는 요청자의 scope)가 일치하는지 확인이 누락된다.

TrailBase 건을 일반화하면 “Record API에서 std.FileUpload 메타데이터의 file id가 user-controlled인데, 그 id의 소유권/스코프 검증이 빠졌다”로 요약할 수 있습니다. [VulnCheck advisory](https://www.vulncheck.com/advisories/trailbase-idor-via-record-api-file-column)

### 2) “키가 데이터가 아니라 권한을 대표한다”는 착각

멀티테넌트 시스템에서 테넌트 스코프를 나타내는 값이 특히 위험합니다.

- `X-Tenant-Id` 헤더
- `/tenants/{tenantId}/...` 경로 파라미터
- `tenant_id` JSON 필드

이 값이 사용자 입력으로 들어오면, 그 순간부터 tenant boundary는 클라이언트가 조작 가능한 boundary가 됩니다. API Gateway가 앞단에서 tenant를 라우팅한다 해도, 백엔드가 그 헤더/파라미터를 다시 신뢰하면 동일한 문제가 재현됩니다.

### 3) “read-only 데이터”가 “side-effect를 일으키는 키”로 변한다

TrailBase 릴리스 노트의 “read-only file”이라는 표현이 좋은 예입니다. read-only로 보여지는 대상도, 그 내부 식별자가 다른 엔드포인트에서 delete/update의 키로 재사용되면 read-only가 아닙니다.

- list/read: 파일 메타데이터가 보인다
- update: 파일 메타데이터의 id를 바꿀 수 있다
- delete: 메타데이터 변화가 object store garbage collection이나 cascade delete를 건드린다

결과적으로, read 권한만으로도 “delete를 유발하는 키”를 획득하거나 조립할 수 있습니다.

### 4) “부분 일치 검색/필터”가 오라클이 된다

VulnCheck는 `$like` 필터로 stripped id를 복구할 수 있다고 설명합니다. [VulnCheck advisory](https://www.vulncheck.com/advisories/trailbase-idor-via-record-api-file-column)

내가 보기엔 여기서 중요한 메시지는 “특정 제품의 `$like`가 위험하다”가 아닙니다. “list API의 필터/검색 기능이, 접근은 허용하지만 정보는 숨기려는 설계를 무너뜨릴 수 있다”입니다.

- 숨겼다고 믿은 값(내부 id, 토큰, 키의 일부)이
- 조건 검색(부분 일치, 정렬, 에러 메시지, 응답 크기 차이, 시간 차이)
- 같은 관측 가능 채널을 통해 재구성될 수 있습니다.

이 지점이 authorization 이슈가 단순히 RBAC 테이블 설계가 아니라, API UX/검색 기능/에러 처리까지 포함한 설계 문제라는 이유입니다.

## TrailBase 사례를 “사용자 제공 키 기반 권한”으로 재해석하기

TrailBase Record API는 SQLite 기반 데이터 모델을 HTTP CRUD로 노출하는 성격이 강합니다. 문서에는 Record API가 `TABLE`/`VIEW`를 CRUD로 노출하고, list/read/update/delete를 지원한다고 되어 있습니다. [TrailBase Record APIs 문서](https://trailbase.io/documentation/apis_record/)

또한 `std.FileUpload` / `std.FileUploads` JSON schema constraint로 파일 업로드를 지원하며, 테이블에는 “파일 바이트”가 아니라 “메타데이터”만 저장하고 실제 파일은 object store(로컬 FS 또는 S3)에 저장한다고 설명합니다. 다운로드는 record read가 아니라 별도 endpoint(`/file/...`)로 한다는 점도 분명히 씁니다. [TrailBase Record APIs: File Uploads](https://trailbase.io/documentation/apis_record/)

이 구조가 왜 CWE-639 패턴과 자주 결합하냐면, 파일 업로드/다운로드가 본질적으로 2단계 참조이기 때문입니다.

- 1차 참조: record(row)가 file metadata를 가진다
- 2차 참조: metadata가 object store의 file id를 가리킨다

권한 검증의 기준이 되는 스코프도 2겹입니다.

- row를 읽을 권한
- row가 가리키는 file object를 읽을 권한

여기서 흔히 저지르는 실수는 “row 권한이 있으면 file 권한도 있다”를 디폴트로 놓는 것입니다. 그런데 IDOR류는 보통 “row는 내 것”인데 “file id는 남의 것”인 상태를 만들어 버립니다.

VulnCheck 설명대로라면, 공격자는 자신이 업데이트할 수 있는 레코드에 피해자의 file id를 심을 수 있었고, 그 결과로 피해자 파일 바이트를 읽거나 삭제/고아화를 유발할 수 있었습니다. [VulnCheck advisory](https://www.vulncheck.com/advisories/trailbase-idor-via-record-api-file-column)

TrailBase 릴리스 노트의 “internal id를 list API로 oracled”라는 문장은 위의 “file id를 심는” 동작과 결합될 때 치명적입니다.

- list API가 file id를 숨긴 형태(stripped id, masked id, 일부만 노출된 id)를 응답에 포함한다
- 하지만 list API의 filter가 그 숨겨진 값을 기준으로 매칭/정렬/에러를 다르게 만든다
- 공격자는 반복 요청으로 내부 id를 복구한다

이런 류의 오라클은 보통 단일 코드 버그라기보다 “숨김(masking)” 전략이 설계 단계에서 권한 모델과 분리되어 있는 경우에 생깁니다.

## 설계 원칙: key-scope와 tenant-scope를 분리하는 방법

CWE-639의 mitigation은 결국 “매번 접근 시 권한을 확인하라(complete mediation)”로 귀결됩니다. 하지만 백엔드에서 “매번 확인”이 구체적으로 뭔지 모호해서, 보통 구현이 허술해집니다. [MITRE CWE-639 mitigation](https://cwe.mitre.org/data/definitions/639.html)

내가 실무에서 재사용 가능하다고 느낀 원칙은 다음 4개입니다.

### 원칙 1: scope는 client input이 아니라 auth artifact에서 파생한다

테넌트/사용자/역할/스코프는 요청 payload에 있으면 편합니다. 그러나 authorization을 payload와 분리하지 못하면, 결국 “인증된 사용자가 payload를 조작해서 권한 경계를 바꾼다”가 됩니다.

- tenant_id는 `X-Tenant-Id`가 아니라 token claim(또는 API key 매핑)에서 나온다
- user_id도 마찬가지다

TrailBase 문서도 production에서 레코드 생성/수정/삭제 시 `_REQ_`나 `_ROW_`와 `_USER_.id`를 비교해 impersonation을 막으라고 조언합니다. 즉, “요청 본문에 있는 user_id를 믿지 말고 서버가 알고 있는 user를 기준으로 비교하라”는 방향입니다. [TrailBase Production: API Access](https://trailbase.io/documentation/production/)

### 원칙 2: 참조 키는 opaque token으로 바꾸고, 토큰에 바인딩 정보를 넣는다

file id처럼 “어떤 저장소 객체를 가리키는 키”가 user-controlled가 되는 순간, 모든 검증을 누락하기 쉬워집니다. 가장 깔끔한 방식은 user에게 file id 자체를 주지 않는 것입니다.

- 서버가 `file_ref_token`을 발급한다 (암호화 또는 서명)
- token payload에 `{tenant_id, record_id, column_name, file_id, exp}` 같은 바인딩을 넣는다
- 다운로드/삭제/갱신은 file id가 아니라 token으로만 가능하게 한다

이 접근이 “추측 불가능하게 만들기”와 다른 점은, 단순 난수화가 아니라 **권한 모델(스코프)과 결합된 토큰**이라는 점입니다.

TrailBase도 0.36.0 릴리스에서 “opaque (encrypted) file token”을 도입하고, 토큰을 “특정 record와 column에 bound”한다고 명시합니다. 이 방향은 CWE-639 재발 방지에 매우 직접적으로 닿아 있습니다. [TrailBase v0.36.0 릴리스 노트](https://github.com/trailbaseio/trailbase/releases/tag/v0.36.0)

### 원칙 3: DB row ownership과 object ownership을 따로 저장하고 따로 검증한다

파일 업로드가 있는 시스템은 권한 모델이 최소 두 층입니다.

- “이 row를 업데이트할 수 있는가?”
- “이 파일 객체를 참조/삭제할 수 있는가?”

이 둘을 같은 조건으로 놓으면, row 업데이트 권한만 있으면 파일 권한까지 획득하게 됩니다. 반대로, 파일을 “row에 붙어 있으니 row 소유자다”로 두면, row attachment를 갈아끼우는 순간 스코프가 무너집니다.

권장 패턴은 별도 테이블/메타데이터입니다.

- `files(file_id, tenant_id, owner_user_id, created_at, ...)`
- `records(record_id, tenant_id, owner_user_id, attachment_file_id, ...)`

그리고 update 시 반드시 다음을 확인합니다.

- `records.tenant_id == auth.tenant_id`
- `records.owner_user_id == auth.user_id` (모델에 따라 다름)
- `files.tenant_id == auth.tenant_id` (또는 허용된 share 정책)
- `files.owner_user_id == auth.user_id` (또는 허용된 share 정책)

이 검증은 API Gateway에서 한 번, 백엔드에서 한 번으로 끝나지 않습니다. “권한 판정의 기준이 되는 스코프”와 “데이터 조회에 쓰는 키”를 join해서 확인해야 합니다.

### 원칙 4: list/search API는 “보이는 것만 필터링 가능”해야 한다

오라클을 막는 실전 규칙은 생각보다 단순합니다.

- 응답에서 숨긴 필드는 filter/sort에서 쓰지 못하게 한다
- 혹은 filter/sort에 쓰더라도, 결과 유무/카운트/응답 크기/에러가 숨긴 값에 의해 달라지지 않게 한다

TrailBase의 Record API는 list가 필터 파라미터를 지원한다고 문서에 밝힙니다. [TrailBase Record APIs: List](https://trailbase.io/documentation/apis_record/)

이 기능 자체가 문제라기보다, “숨긴 내부 id”와 결합했을 때 오라클이 되기 쉬운 구조라는 점이 문제입니다.

## API Gateway/백엔드에서 부정 케이스 테스트 체크리스트

보안 이슈를 예방하려면, 정상 케이스 테스트만으로는 부족합니다. 특히 멀티테넌트/파일 참조/레코드 CRUD 시스템은 “권한 붕괴 시나리오”가 대부분 부정 케이스에서 터집니다.

여기서는 (1) user-controlled key가 authorization으로 침투하는 지점을 찾고, (2) API Gateway와 백엔드가 서로 다른 기준을 쓰는 상황을 일부러 만들어 깨뜨리는 테스트 항목을 정리합니다.

### 1) tenant boundary 깨기

- 내 API key/token으로 인증한 뒤
- `X-Tenant-Id: victim` 헤더를 추가/변조한다
- URL path의 `{tenantId}`를 victim으로 바꾼다
- body의 `tenant_id`를 victim으로 넣는다

기대 결과는 403 또는 404입니다. 404를 선택하면 enumeration 리스크가 줄어들지만, 운영 관측(로그/메트릭)에서 원인 분석이 어려워질 수 있습니다.

중요한 건 응답 코드가 아니라, **서버 내부에서 실제로 victim tenant DB/스토리지를 건드리지 않는가**입니다.

### 2) object reference cross-scope

- 내 record에 남의 `file_id`를 넣어 update
- 내 record를 read해서 파일 다운로드 endpoint를 호출
- 내 record를 delete해서 victim file이 삭제/고아화되는지 확인

이 테스트는 “파일 id가 user-controlled인 입력면”을 찾는 것이 먼저입니다. TrailBase의 경우 `std.FileUpload` 컬럼이 바로 그 입력면이었고, Record API가 insert/update에서 메타데이터를 받아들였다는 점이 advisory에 명시되어 있습니다. [VulnCheck advisory](https://www.vulncheck.com/advisories/trailbase-idor-via-record-api-file-column)

### 3) list/search 오라클

- 숨긴 값(내부 id, token, masked id)을 대상으로
- 부분 일치/정규식/범위 검색이 가능한지
- count/total_count가 달라지는지
- 에러 메시지(“invalid id format”)가 달라지는지
- 응답 시간이 달라지는지

TrailBase 0.35.10 릴리스 노트는 “list API로 internal id를 oracled”라는 표현을 써서, list가 정보 복구 채널이 됐음을 암시합니다. [TrailBase v0.35.10 릴리스 노트](https://github.com/trailbaseio/trailbase/releases/tag/v0.35.10)

### 4) Gateway-Backend 불일치(가장 흔한 실전 사고)

- Gateway는 API key로 tenant를 결정하지만, backend는 `X-Tenant-Id`를 신뢰한다
- Gateway는 header를 strip한다고 믿지만, backend는 fallback 로직으로 client header를 허용한다
- Gateway는 JWT claim을 신뢰하지만, backend는 body의 `user_id`도 허용한다

이 케이스는 단순히 “검증이 없다”가 아니라 “검증 기준이 두 개”인 상태입니다. 보안 사고의 상당수가 여기서 납니다.

내 경우, API Gateway 도입 이후 권한 사고가 늘었던 프로젝트가 있었는데, 원인이 “gateway에서 추출한 scope”와 “백엔드에서 재구성한 scope”가 다르게 동작하는 케이스였습니다. 그 이후로는 gateway/백엔드 둘 다에서 “tenant/user는 오직 auth artifact에서만 나온다”를 강하게 고정했습니다.

### 5) 릴리스 기반 회귀 테스트

TrailBase production 문서는 레코드 생성/수정/삭제에서 `_USER_.id` 비교를 권장합니다. [TrailBase Production: API Access](https://trailbase.io/documentation/production/)

이런 조언은 “설정/규칙으로 막아야 하는 클래스의 취약점이 있다”는 뜻이기도 합니다. 제품 업데이트를 할 때는 다음을 자동으로 점검하는 회귀 테스트를 붙이는 쪽이 안전합니다.

- 레코드 소유권 규칙이 실제로 모든 CRUD에 걸려 있는지
- 파일 다운로드 엔드포인트가 row 권한만으로 열리는지
- list filter가 숨김 필드를 참조하지 않는지

이건 인프라/운영 관점에서는 configuration drift 문제로도 이어집니다. 권한 규칙을 “대시보드에서 클릭”으로 관리하면 재현이 어려워집니다. 같은 계열로 Grafana Saved Queries를 Terraform으로 자산화했던 글이 있는데, 권한/정책도 유사하게 코드화하는 게 회귀 테스트를 붙이기 쉽습니다. [Grafana Saved Queries를 Terraform으로 팀 자산화하기](https://daewooki.github.io/posts/grafana-saved-queries-terraform-ops/)

## 실행 가능한 재현 환경: user-controlled key가 터지는 구조와 고친 구조

아래 코드는 TrailBase 자체를 재현하는 목적이 아닙니다. CVE-2026-119759에서 드러난 핵심(파일 메타데이터의 user-controlled key + 소유권 검증 누락 + tenant boundary 붕괴)을, API Gateway/백엔드 분리 환경에서 “부정 케이스 테스트로 잡는” 예제입니다.

구성은 다음과 같습니다.

- `gateway`: 외부 요청을 받고 API key를 auth context로 변환해 내부 JWT(`X-Internal-Auth`)를 생성
- `backend`: 내부 JWT를 검증하고, 레코드/파일 권한을 집행
- `tests`: 공격 시나리오(부정 케이스)가 실패해야 정상

동일 코드베이스에서 `MODE=vuln`과 `MODE=fixed`를 바꿔 실행할 수 있게 해 두었습니다.

### 디렉터리 구조

```text
user-controlled-key-demo/
  docker-compose.yml
  backend/
    Dockerfile
    app.py
    requirements.txt
  gateway/
    Dockerfile
    app.py
    requirements.txt
  tests/
    test_idor.py
    requirements.txt
```

### docker-compose.yml

```yaml
services:
  backend:
    build: ./backend
    environment:
      - MODE=${MODE:-vuln}
      - INTERNAL_JWT_SECRET=dev-internal-secret
    ports:
      - "8002:8000"

  gateway:
    build: ./gateway
    environment:
      - INTERNAL_JWT_SECRET=dev-internal-secret
      - BACKEND_URL=http://backend:8000
    ports:
      - "8001:8000"
    depends_on:
      - backend
```

### gateway/app.py

```python
import os
from typing import Dict

import httpx
import jwt
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

INTERNAL_JWT_SECRET = os.environ["INTERNAL_JWT_SECRET"]
BACKEND_URL = os.environ["BACKEND_URL"]

# 데모용 API key 매핑: key -> (tenant_id, user_id, scopes)
API_KEYS: Dict[str, Dict] = {
    "key-tenant-a-user-1": {"tenant_id": "tenant-a", "user_id": "user-1", "scopes": ["records:rw", "files:rw"]},
    "key-tenant-b-user-9": {"tenant_id": "tenant-b", "user_id": "user-9", "scopes": ["records:rw", "files:rw"]},
}

app = FastAPI()

@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy(path: str, request: Request, x_api_key: str = Header(default="")):
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="invalid api key")

    ctx = API_KEYS[x_api_key]
    internal_jwt = jwt.encode(ctx, INTERNAL_JWT_SECRET, algorithm="HS256")

    # Gateway에서 해야 하는 일: 외부에서 온 tenant/user 관련 헤더는 신뢰하지 않는다.
    # 데모에서는 X-Tenant-Id, X-User-Id를 제거하고 내부 JWT만 전달한다.
    forward_headers = {k: v for k, v in request.headers.items()}
    forward_headers.pop("x-tenant-id", None)
    forward_headers.pop("x-user-id", None)
    forward_headers["x-internal-auth"] = internal_jwt

    body = await request.body()

    async with httpx.AsyncClient(timeout=10.0) as client:
        upstream = await client.request(
            method=request.method,
            url=f"{BACKEND_URL}/{path}",
            params=dict(request.query_params),
            headers=forward_headers,
            content=body,
        )

    return Response(content=upstream.content, status_code=upstream.status_code, headers=dict(upstream.headers))
```

### gateway/requirements.txt

```text
fastapi==0.115.5
uvicorn[standard]==0.32.0
httpx==0.27.2
PyJWT==2.9.0
```

### gateway/Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### backend/app.py

```python
import os
from typing import Dict, Optional

import jwt
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

MODE = os.environ.get("MODE", "vuln")
INTERNAL_JWT_SECRET = os.environ["INTERNAL_JWT_SECRET"]

app = FastAPI()

# 데모용 in-memory object store
FILES: Dict[str, Dict] = {
    # file_id: {tenant_id, owner_user_id, bytes}
    "file-a-111": {"tenant_id": "tenant-a", "owner_user_id": "user-1", "bytes": b"TOP-SECRET-A"},
    "file-b-999": {"tenant_id": "tenant-b", "owner_user_id": "user-9", "bytes": b"TOP-SECRET-B"},
}

# 데모용 records
RECORDS: Dict[str, Dict] = {
    # record_id: {tenant_id, owner_user_id, attachment_file_id}
    "rec-a-1": {"tenant_id": "tenant-a", "owner_user_id": "user-1", "attachment_file_id": "file-a-111"},
    "rec-b-1": {"tenant_id": "tenant-b", "owner_user_id": "user-9", "attachment_file_id": "file-b-999"},
}

def auth_ctx(x_internal_auth: str) -> Dict:
    if not x_internal_auth:
        raise HTTPException(status_code=401, detail="missing internal auth")

    try:
        ctx = jwt.decode(x_internal_auth, INTERNAL_JWT_SECRET, algorithms=["HS256"])
        return ctx
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid internal auth")

class UpdateAttachment(BaseModel):
    # TrailBase std.FileUpload 같은 구조를 흉내 내기 위해
    # 실제 파일 바이트가 아니라 metadata id만 받는 케이스를 만든다.
    attachment_file_id: Optional[str] = None

@app.get("/records/{record_id}")
def read_record(record_id: str, x_internal_auth: str = Header(default="")):
    ctx = auth_ctx(x_internal_auth)
    if record_id not in RECORDS:
        raise HTTPException(status_code=404, detail="record not found")

    rec = RECORDS[record_id]

    # record scope 검증(tenant + owner)
    if rec["tenant_id"] != ctx["tenant_id"]:
        raise HTTPException(status_code=404, detail="record not found")
    if rec["owner_user_id"] != ctx["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    return {"record_id": record_id, **rec}

@app.patch("/records/{record_id}")
def update_record(record_id: str, payload: UpdateAttachment, x_internal_auth: str = Header(default="")):
    ctx = auth_ctx(x_internal_auth)
    if record_id not in RECORDS:
        raise HTTPException(status_code=404, detail="record not found")

    rec = RECORDS[record_id]

    if rec["tenant_id"] != ctx["tenant_id"]:
        raise HTTPException(status_code=404, detail="record not found")
    if rec["owner_user_id"] != ctx["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    if payload.attachment_file_id is None:
        return {"ok": True, "record": rec}

    # === 여기서 MODE에 따라 취약/수정 동작이 갈린다. ===
    if MODE == "vuln":
        # 취약한 설계: file id는 user-controlled인데, 소유권 검증 없이 그냥 교체한다.
        # (CVE-2026-119759의 핵심을 단순화한 형태)
        rec["attachment_file_id"] = payload.attachment_file_id
        return {"ok": True, "record": rec, "mode": MODE}

    # fixed: file id가 존재하는지 + 같은 tenant인지 + 같은 owner인지 확인
    if payload.attachment_file_id not in FILES:
        raise HTTPException(status_code=400, detail="unknown file")

    f = FILES[payload.attachment_file_id]
    if f["tenant_id"] != ctx["tenant_id"]:
        raise HTTPException(status_code=403, detail="cross-tenant file reference")

    # 모델에 따라 owner 비교를 tenant 비교로만 완화할 수 있으나,
    # 데모에서는 '내 파일만 붙인다'로 강하게 둔다.
    if f["owner_user_id"] != ctx["user_id"]:
        raise HTTPException(status_code=403, detail="not your file")

    rec["attachment_file_id"] = payload.attachment_file_id
    return {"ok": True, "record": rec, "mode": MODE}

@app.get("/records/{record_id}/file")
def download_attached_file(record_id: str, x_internal_auth: str = Header(default="")):
    ctx = auth_ctx(x_internal_auth)
    if record_id not in RECORDS:
        raise HTTPException(status_code=404, detail="record not found")

    rec = RECORDS[record_id]
    if rec["tenant_id"] != ctx["tenant_id"]:
        raise HTTPException(status_code=404, detail="record not found")
    if rec["owner_user_id"] != ctx["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    file_id = rec["attachment_file_id"]
    if file_id not in FILES:
        raise HTTPException(status_code=404, detail="file missing")

    f = FILES[file_id]

    # 취약한 시스템은 여기서도 tenant/owner 검증을 생략하는 경우가 많다.
    # fixed 모드에서는 2차 참조(object ownership)까지 확인한다.
    if MODE == "fixed":
        if f["tenant_id"] != ctx["tenant_id"]:
            raise HTTPException(status_code=403, detail="cross-tenant file")
        if f["owner_user_id"] != ctx["user_id"]:
            raise HTTPException(status_code=403, detail="not your file")

    return {"file_id": file_id, "bytes": f["bytes"].decode("utf-8"), "mode": MODE}
```

### backend/requirements.txt

```text
fastapi==0.115.5
uvicorn[standard]==0.32.0
PyJWT==2.9.0
pydantic==2.9.2
```

### backend/Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### tests/test_idor.py

```python
import os
import requests

GATEWAY = os.environ.get("GATEWAY", "http://localhost:8001")

def test_cross_tenant_file_reference_should_fail_in_fixed_mode():
    # tenant-a user가 tenant-b의 file_id를 자기 record에 붙이려는 시도
    headers = {"X-API-Key": "key-tenant-a-user-1"}

    # 1) (취약 모드에서는) 업데이트가 성공한다
    r = requests.patch(
        f"{GATEWAY}/records/rec-a-1",
        json={"attachment_file_id": "file-b-999"},
        headers=headers,
        timeout=5,
    )

    mode = r.json().get("mode")
    if mode == "vuln":
        assert r.status_code == 200

        # 2) (취약 모드에서는) 다운로드에서 tenant-b의 파일이 노출된다
        r2 = requests.get(f"{GATEWAY}/records/rec-a-1/file", headers=headers, timeout=5)
        assert r2.status_code == 200
        assert r2.json()["bytes"] == "TOP-SECRET-B"
        return

    # fixed 모드에서는 update가 막혀야 한다
    assert r.status_code == 403

def test_normal_flow_should_work_in_both_modes():
    headers = {"X-API-Key": "key-tenant-a-user-1"}

    r = requests.get(f"{GATEWAY}/records/rec-a-1", headers=headers, timeout=5)
    assert r.status_code == 200
    assert r.json()["tenant_id"] == "tenant-a"

    r2 = requests.get(f"{GATEWAY}/records/rec-a-1/file", headers=headers, timeout=5)
    assert r2.status_code == 200
    assert r2.json()["bytes"] in ["TOP-SECRET-A", "TOP-SECRET-B"]
```

### tests/requirements.txt

```text
pytest==8.3.3
requests==2.32.3
```

### 실행 방법과 예상 결과

1) 취약 모드로 실행

```bash
cd user-controlled-key-demo
MODE=vuln docker compose up --build
```

다른 터미널에서 테스트:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt
pytest -q
```

예상: `cross tenant file reference` 테스트가 “취약하므로 성공/노출” 분기(vuln 경로)로 들어가서 통과합니다. 즉, 테스트가 “취약함을 재현했기 때문에” green이 됩니다.

2) 수정 모드로 실행

```bash
MODE=fixed docker compose up --build
```

동일하게 pytest 실행.

예상: `cross tenant file reference`에서 update가 403으로 막히며, 다운로드에서도 403/404로 차단됩니다.

이 데모에서 중요한 건 “UUID를 얼마나 랜덤하게 만들었냐”가 아닙니다. file id는 이미 충분히 랜덤한 문자열로 가정해도, 한 번 유출되거나 오라클로 복구되면 끝입니다. 핵심은 user-controlled key가 authorization scope와 결합되지 않은 상태로 write path에 들어오는 순간 무너진다는 점입니다.

## 릴리스 노트 기반 CVE 트리아지: 영향 범위를 좁히는 순서

CVE 대응에서 시간을 가장 많이 잡아먹는 건 “우리에게 해당하나?”입니다. 이걸 빠르게 좁히려면 릴리스 노트를 1차 신호로 쓰는 게 효율적입니다.

TrailBase CVE를 예로 들면, 다음 순서가 실용적이었습니다.

### 1) 릴리스 노트의 한 문장을 “기능 단위”로 분해한다

TrailBase 0.35.10 릴리스 노트의 첫 줄은 다음 요소를 포함합니다.

- 대상: read-only file
- 식별자: internal id
- 유출 채널: list API
- 기술: oracle
- 임팩트: delete 가능

이 한 문장만으로도 “파일 업로드/다운로드 기능과 record list/search 기능이 결합되는 지점”을 먼저 봐야 한다는 결론이 나옵니다. [TrailBase v0.35.10 릴리스 노트](https://github.com/trailbaseio/trailbase/releases/tag/v0.35.10)

여기서 곧장 할 일은 “버전 올리자”가 아니라, 내 서비스에서 다음을 쓰는지 확인하는 것입니다.

- Record APIs 사용 여부
- list API를 외부에 열었는지
- 파일 관련 컬럼/엔드포인트를 썼는지

TrailBase 문서에는 `std.FileUpload` 컬럼을 선언하면 파일 메타데이터를 테이블에 저장하고 object store를 사용한다고 되어 있습니다. [TrailBase Record APIs: File Uploads](https://trailbase.io/documentation/apis_record/)

이건 “파일 기능을 썼는지”의 판별 기준으로 바로 쓸 수 있습니다.

### 2) advisory에서 “전제 조건”을 뽑아낸다

VulnCheck advisory는 공격 전제로 “authenticated attacker”를 명시하고, 피해자 row를 읽을 수 있어야 하며 `$like` 필터로 id 복구가 가능하다고 적습니다. [VulnCheck advisory](https://www.vulncheck.com/advisories/trailbase-idor-via-record-api-file-column)

즉, 아래 조건이 충족되면 위험도가 급상승합니다.

- 서비스가 internet-facing
- 익명/저권한 계정이 레코드 list/read를 어느 정도 할 수 있음
- 파일 업로드 컬럼이 존재

반대로, admin-only 내부 서비스이고 파일 업로드 컬럼을 쓰지 않는다면, 버전이 영향 범위에 있어도 실제 익스플로잇 경로는 닫혀 있을 수 있습니다. 물론 이런 결론을 내릴 때는 “정말로 list/read가 닫혀 있나?”를 테스트로 검증해야 합니다.

### 3) 영향 버전 범위는 OSV 같은 메타 데이터로 빠르게 확인한다

TrailBase의 경우 OSV가 `introduced: 0.28.2`, `fixed: 0.35.10` 범위를 제공합니다. 이건 “어느 버전부터 어느 버전까지?”를 자동화하기에 좋습니다. [OSV: CVE-2026-119759](https://osv.dev/vulnerability/CVE-2026-119759)

여기서 함정은, 영향 버전이 넓다고 해서 항상 위험이 큰 건 아니라는 점입니다. “기능을 쓰는가”가 더 중요합니다.

### 4) 제품 문서에서 “권한 모델을 어디에 두는지”를 확인한다

TrailBase는 production 문서에서 레코드 접근 규칙을 `_USER_.id`와 비교하라고 안내합니다. [TrailBase Production: API Access](https://trailbase.io/documentation/production/)

이 문서를 보고 내가 얻는 정보는 “이 제품은 row-level authorization을 SQL rule로 구성할 수 있고, user id를 서버 컨텍스트로 다룬다”입니다. 즉, 내 구성에서 file object ownership까지 확장해서 규칙을 썼는지 점검해야 합니다.

이 과정이 트리아지의 마지막 단계가 되어야 합니다. 릴리스 노트/어드바이저리/버전 범위를 먼저 정리한 뒤, “우리가 쓰는 기능과 설정이 공격 전제를 충족하는가?”를 좁혀 들어가는 편이 빠릅니다.

## 도입 판단 기준: 패치로 끝낼 것과 재설계로 갈 것

CWE-639 계열은 패치로 끝나는 경우도 있지만, 보통은 패치 이후에도 유사 사고가 재발합니다. 이유는 단순합니다. 코드 한 군데에서 ownership check를 넣어도, 다음 기능이 추가되면 다른 입력면에서 다시 user-controlled key가 authorization으로 침투하기 때문입니다.

내 기준에서 다음 중 하나라도 해당하면 “재설계(토큰화/바인딩/스코프 파생)”가 더 값이 큽니다.

- 파일/객체 참조가 여러 엔드포인트에 걸쳐 재사용된다 (read/list/update/delete)
- list/search 기능이 풍부하다 (부분일치, 정렬, 카운트)
- 멀티테넌트이고, tenant boundary가 헤더/경로/쿼리로 전달된다
- API Gateway와 백엔드가 분리되어 있고, 둘 다 scope를 계산한다

TrailBase가 0.36.0에서 opaque file token을 도입하고 record/column에 바인딩한 건, 단순히 “버그를 고쳤다”를 넘어 “같은 클래스의 재발을 구조적으로 줄이겠다”는 신호로 읽힙니다. [TrailBase v0.36.0 릴리스 노트](https://github.com/trailbaseio/trailbase/releases/tag/v0.36.0)

결국 중요한 건 인증(authentication)이 아니라 authorization입니다. user-controlled key가 authorization 경계에 끼어드는 순간, UUID든 내부 id든 얼마든지 권한 붕괴로 이어지며, 이걸 막는 가장 강력한 방법은 스코프를 auth artifact에서 파생하고 참조를 opaque token으로 바인딩하는 쪽으로 설계를 고정하는 것입니다.

## 참고 자료

- [NCSA Newsletter(2026-11-07~2026-11-10)](https://cyber.gov.gr/wp-content/uploads/2026/11/NCSA_Newsletter_2026-11-07_to_2026-11-10.pdf)
- [TrailBase v0.35.10 릴리스 노트](https://github.com/trailbaseio/trailbase/releases/tag/v0.35.10)
- [VulnCheck advisory: TrailBase IDOR via Record API File Column](https://www.vulncheck.com/advisories/trailbase-idor-via-record-api-file-column)
- [OSV: CVE-2026-119759](https://osv.dev/vulnerability/CVE-2026-119759)
- [MITRE CWE-639 정의](https://cwe.mitre.org/data/definitions/639.html)
- [TrailBase Record APIs 문서](https://trailbase.io/documentation/apis_record/)
- [TrailBase Production: API Access](https://trailbase.io/documentation/production/)
- [TrailBase v0.36.0 릴리스 노트](https://github.com/trailbaseio/trailbase/releases/tag/v0.36.0)
- [Grafana Saved Queries를 Terraform으로 팀 자산화하기](https://daewooki.github.io/posts/grafana-saved-queries-terraform-ops/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
