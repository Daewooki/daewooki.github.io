---
title: "CISA KEV로 패치 우선순위 엔진 만들기"
description: "KEV JSON ingest→자산 매칭→dueDate 기반 티켓·알림·배포 링을 자동 생성하는 실전 설계와 코드."
date: 2026-09-16 10:26:58 +0900
categories: ["Tools", "Security Automation"]
tags: ["kev", "vulnerability-management", "security-automation", "cmdb", "jira", "python"]
render_with_liquid: false
---

KEV를 운영에 붙이려면 ‘KEV에 있으면 무조건 즉시 패치’ 같은 구호가 아니라, **기한을 놓치지 않는 시스템**을 먼저 만들어야 합니다. KEV는 JSON 한 파일이지만, 그 파일이 의미하는 것은 변경관리(change management), 대체통제(compensating controls), 자산 인벤토리 정확도, 그리고 배포 역량입니다.

2026-09-16 KST 시점에 `cisagov/kev-data`의 카탈로그 버전은 `2026.09.14`, `dateReleased`는 `2026-09-14T19:00:02.426Z`이며 엔트리 수는 1710개입니다. 이 릴리스 시각은 KST로는 2026-09-15 04:00:02 근처라서, 한국 시간 기준으로 보면 새벽에 데이터가 바뀌는 패턴이 자주 보입니다[^1].

이 글의 목표는 다음 파이프라인을 제안하고, 그대로 실행 가능한 코드/스키마까지 같이 정리하는 것입니다.

- (1) KEV JSON을 주기적으로 ingest (diff 포함)
- (2) 자산 인벤토리(CMDB/클라우드 리소스) + 취약점 스캔 결과와 매칭
- (3) `dueDate`를 내부 SLA로 변환해 알림/티켓/배포 링을 자동 생성

---

## `dueDate`를 “패치 마감” 대신 “결정 마감”으로 재정의

KEV 엔트리에는 `dateAdded`와 `dueDate`가 같이 들어옵니다. 스키마에도 두 필드가 명시되어 있습니다[^2].

- `dateAdded`: 카탈로그에 추가된 날짜
- `dueDate`: “required action”의 기한

여기서 중요한 점은, 2026년 기준 KEV의 규범적 배경이 BOD 22-01만이 아니라 BOD 26-04로 확장/진화했다는 사실입니다. `kev-data` README도 KEV 추가/삭제 요청을 GitHub에서 받지 않으며, KEV는 CISA가 직접 관리하고 BOD 26-04 권한에 기반한다고 명시합니다[^3].

BOD 26-04는 “리스크 기반으로 보안 업데이트를 우선순위화”하는 프레임을 제시하면서, 판단 축을 4개로 정리합니다.

- Asset Exposure: 취약 자산이 publicly exposed인가
- KEV Status: 해당 CVE가 KEV에 포함되는가
- Exploit Automation: 공격자가 exploitation 단계를 자동화 가능한가
- Technical Impact: exploitation 이후 partial/total control을 얻는가

또 하나의 핵심 문장은 운영 관점에서 치명적입니다. BOD 26-04 Appendix A는 타임라인이 “동적인 사실”이며, 예컨대 인터넷에서 제거하면 요구 타임라인이 바뀔 수 있고(노출도 값이 바뀜), KEV에 새로 추가되면 타임라인이 더 짧아질 수 있다고 못박습니다[^4].

이 전제를 받아들이면, KEV `dueDate`를 사내 정책에서 그대로 “패치 완료”로 고정하기 어렵습니다. 대신 다음처럼 재정의하는 편이 시스템을 만들기 쉽습니다.

- **Decision SLA(결정 SLA)**: `dueDate`까지 반드시 “처리 방식”을 확정한다.
  - (A) 패치/업그레이드로 제거
  - (B) 완화(mitigation) + 잔존 리스크 승인
  - (C) 서비스 중단/폐기
  - (D) 예외(waiver) 승인 + 만료일 설정
- Remediation SLA(제거 SLA): 결정된 방식에 따라 배포 링/변경창에 맞춰 완료한다.

이렇게 하면 `dueDate`를 놓치는 문제(사람이 triage하다가 달력에서 사라짐)를 “자동으로 티켓이 생기고, 자동으로 에스컬레이션되는 문제”로 바꿀 수 있습니다.

---

## ingest의 목표는 “최신 상태”가 아니라 “변경 이력”과 idempotency

`cisagov/kev-data`는 KEV가 업데이트되면 GitHub 저장소도 수 분 내 동기화되며, 업데이트는 통상 미국 동부 업무 시간의 평일에 일어난다고 설명합니다[^3].

운영 자동화에서 ingest는 최신 파일을 가져오는 것보다 아래 두 가지가 더 중요합니다.

1) 언제 바뀌었는지(릴리스 시각, 카탈로그 버전)
2) 무엇이 바뀌었는지(추가/수정/삭제 diff)

이 때문에 저장 전략은 “항상 같은 테이블을 overwrite”가 아니라, 최소한 스냅샷을 남기는 구조가 유리합니다.

- `kev_catalog_snapshot` 테이블: `catalogVersion`, `dateReleased`, `count`, `etag`, `raw_json_sha256`
- `kev_entry` 테이블: `cveID` 기준으로 최신 상태
- `kev_entry_version` 테이블: 스냅샷별 엔트리 해시(필드 단위 변경 감지)

또한 KEV JSON은 스키마에 없는 필드가 추가될 수 있습니다. 2026-09-14 릴리스의 예시 엔트리에는 `forensicTriage`, `cwes` 등이 보이는데, 스키마에는 `cwes`는 정의되어 있지만 `forensicTriage`는 정의되어 있지 않습니다[^1][^2].

따라서 구현은 “스키마 검증으로 ingest를 hard fail”시키기보다,

- 스키마는 기본 구조 보장(필수 필드 존재, 날짜 형식) 정도로만 사용
- 추가 필드는 별도 JSON 컬럼에 보관(관찰 가능하게)

이 접근이 장애를 줄입니다.

---

## 실행 가능한 최소 구현: Postgres + Python 스크립트 4개

아래 구현은 “엔진 골격”에 해당합니다.

- `fetch_kev.py`: KEV JSON + schema fetch, ETag 기반 304 처리, 스냅샷 저장
- `ingest_kev.py`: JSON을 정규화해 DB 적재, 엔트리 해시 생성
- `ingest_assets.py`: CMDB CSV(또는 API 결과)를 자산 테이블로 적재
- `ingest_findings_trivy.py`: Trivy JSON 리포트를 findings로 적재
- `match_and_ticket.py`: KEV×findings×assets 매칭 → SLA 계산 → Jira 티켓 생성

### 로컬 실행을 위한 `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: kev
      POSTGRES_PASSWORD: kev
      POSTGRES_DB: kev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

### `requirements.txt`

```txt
requests==2.32.3
sqlalchemy==2.0.36
psycopg==3.2.3
pydantic==2.9.2
python-dateutil==2.9.0.post0
jsonschema==4.23.0
rich==13.9.4
```

버전은 예시이고, 조직 표준에 맞춰 고정하는 편이 운영에 유리합니다.

### DB 스키마(간단 버전)

```sql
CREATE TABLE IF NOT EXISTS kev_catalog_snapshot (
  id BIGSERIAL PRIMARY KEY,
  catalog_version TEXT NOT NULL,
  date_released TIMESTAMPTZ NOT NULL,
  entry_count INT NOT NULL,
  etag TEXT,
  raw_sha256 TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  raw_json JSONB NOT NULL,
  UNIQUE (catalog_version, date_released)
);

CREATE TABLE IF NOT EXISTS kev_entry (
  cve_id TEXT PRIMARY KEY,
  vendor_project TEXT NOT NULL,
  product TEXT NOT NULL,
  vulnerability_name TEXT NOT NULL,
  date_added DATE NOT NULL,
  due_date DATE NOT NULL,
  known_ransomware_campaign_use TEXT,
  required_action TEXT NOT NULL,
  short_description TEXT NOT NULL,
  notes TEXT,
  cwes JSONB,
  extra JSONB,
  last_seen_catalog_version TEXT NOT NULL,
  last_seen_date_released TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS asset (
  asset_id TEXT PRIMARY KEY,
  asset_type TEXT NOT NULL,
  owner_team TEXT NOT NULL,
  env TEXT NOT NULL,
  internet_exposed BOOLEAN NOT NULL,
  criticality TEXT NOT NULL,
  change_freeze BOOLEAN NOT NULL DEFAULT false,
  tags JSONB
);

CREATE TABLE IF NOT EXISTS finding (
  id BIGSERIAL PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES asset(asset_id),
  scanner TEXT NOT NULL,
  cve_id TEXT NOT NULL,
  detected_at TIMESTAMPTZ NOT NULL,
  details JSONB,
  UNIQUE(asset_id, scanner, cve_id)
);

CREATE TABLE IF NOT EXISTS work_item (
  id BIGSERIAL PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES asset(asset_id),
  cve_id TEXT NOT NULL REFERENCES kev_entry(cve_id),
  kev_due_date DATE NOT NULL,
  decision_due_date DATE NOT NULL,
  ring TEXT NOT NULL,
  status TEXT NOT NULL,
  jira_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(asset_id, cve_id)
);
```

현실에서는 `asset_id`를 무엇으로 잡느냐가 승부처입니다. VM이면 instance ID, 컨테이너면 image digest, SaaS면 tenant ID 등으로 달라집니다.

---

## `fetch_kev.py`: ETag로 “매번 다운로드”를 피하고, 스냅샷을 남기기

KEV JSON은 GitHub raw URL 하나로 접근됩니다.

- JSON: [known_exploited_vulnerabilities.json](https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json)
- Schema: [known_exploited_vulnerabilities_schema.json](https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities_schema.json)

스크립트는 다음을 수행합니다.

- DB에서 마지막 `etag`를 읽어 `If-None-Match`로 요청
- 304면 종료
- 200이면 스냅샷 테이블에 raw JSON 그대로 저장
- `catalogVersion`, `dateReleased`, `count`를 메타로 저장

```python
# scripts/fetch_kev.py
import hashlib
import json
import os
from datetime import datetime, timezone

import requests
from sqlalchemy import create_engine, text

KEV_URL = os.getenv(
    "KEV_URL",
    "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json",
)

DB_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://kev:kev@localhost:5432/kev")

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def main():
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kev_catalog_snapshot (
          id BIGSERIAL PRIMARY KEY,
          catalog_version TEXT NOT NULL,
          date_released TIMESTAMPTZ NOT NULL,
          entry_count INT NOT NULL,
          etag TEXT,
          raw_sha256 TEXT NOT NULL,
          fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          raw_json JSONB NOT NULL,
          UNIQUE (catalog_version, date_released)
        );
        """))

        last = conn.execute(text(
            "SELECT etag FROM kev_catalog_snapshot ORDER BY fetched_at DESC LIMIT 1"
        )).fetchone()
        etag = last[0] if last else None

    headers = {}
    if etag:
        headers["If-None-Match"] = etag

    r = requests.get(KEV_URL, headers=headers, timeout=30)
    if r.status_code == 304:
        print("KEV not modified (HTTP 304)")
        return
    r.raise_for_status()

    raw = r.text
    data = r.json()

    catalog_version = data["catalogVersion"]
    date_released = datetime.fromisoformat(data["dateReleased"].replace("Z", "+00:00"))
    entry_count = int(data["count"])

    raw_hash = sha256_str(raw)
    resp_etag = r.headers.get("ETag")

    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("""
          INSERT INTO kev_catalog_snapshot (catalog_version, date_released, entry_count, etag, raw_sha256, raw_json)
          VALUES (:v, :dr, :c, :etag, :h, :raw::jsonb)
          ON CONFLICT (catalog_version, date_released)
          DO NOTHING
        """), {
            "v": catalog_version,
            "dr": date_released,
            "c": entry_count,
            "etag": resp_etag,
            "h": raw_hash,
            "raw": json.dumps(data),
        })

    print(f"Fetched KEV: catalogVersion={catalog_version} dateReleased={date_released.isoformat()} count={entry_count}")

if __name__ == "__main__":
    main()
```

실행:

```bash
docker compose up -d
export DATABASE_URL='postgresql+psycopg://kev:kev@localhost:5432/kev'
python scripts/fetch_kev.py
```

예상 출력(2026-09-16 KST 시점 기준):

```txt
Fetched KEV: catalogVersion=2026.09.14 dateReleased=2026-09-14T19:00:02.426000+00:00 count=1710
```

여기까지는 ingest의 절반입니다. 나머지 절반은 “엔트리 변화 감지”와 “내부 시스템이 쓰기 좋은 형태로 정규화”입니다.

---

## `ingest_kev.py`: 엔트리 해시로 변경을 추적하고, 추가 필드는 `extra`로 보관

KEV 스키마는 필수 필드 세트를 정의합니다[^2]. 하지만 실제 JSON은 필드를 더 가질 수 있고, `notes`는 URL 여러 개가 세미콜론으로 이어진 문자열 형태로 들어오기도 합니다[^1].

정규화에서는 두 가지를 분리합니다.

- “검색/조인 키”: `cveID`, `dueDate`, `dateAdded`, `vendorProject`, `product`
- “설명/참고”: `requiredAction`, `shortDescription`, `notes`, 그리고 알려지지 않은 필드

```python
# scripts/ingest_kev.py
import hashlib
import json
import os
from datetime import datetime

from dateutil.parser import isoparse
from sqlalchemy import create_engine, text

DB_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://kev:kev@localhost:5432/kev")

def stable_hash(obj: dict) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def main():
    engine = create_engine(DB_URL)

    with engine.begin() as conn:
        snap = conn.execute(text("""
          SELECT catalog_version, date_released, raw_json
          FROM kev_catalog_snapshot
          ORDER BY fetched_at DESC
          LIMIT 1
        """)).fetchone()

        if not snap:
            raise SystemExit("No snapshot found. Run fetch_kev.py first.")

        catalog_version, date_released, raw_json = snap
        data = raw_json

        # kev_entry table
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kev_entry (
          cve_id TEXT PRIMARY KEY,
          vendor_project TEXT NOT NULL,
          product TEXT NOT NULL,
          vulnerability_name TEXT NOT NULL,
          date_added DATE NOT NULL,
          due_date DATE NOT NULL,
          known_ransomware_campaign_use TEXT,
          required_action TEXT NOT NULL,
          short_description TEXT NOT NULL,
          notes TEXT,
          cwes JSONB,
          extra JSONB,
          last_seen_catalog_version TEXT NOT NULL,
          last_seen_date_released TIMESTAMPTZ NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """))

        upserted = 0
        for v in data["vulnerabilities"]:
            # required fields
            cve_id = v["cveID"]
            vendor_project = v.get("vendorProject", "")
            product = v.get("product", "")
            vuln_name = v.get("vulnerabilityName", "")
            date_added = v["dateAdded"]
            due_date = v["dueDate"]
            required_action = v.get("requiredAction", "")
            short_desc = v.get("shortDescription", "")

            known_ransom = v.get("knownRansomwareCampaignUse")
            notes = v.get("notes")
            cwes = v.get("cwes")

            # keep unknown fields
            known_keys = {
                "cveID","vendorProject","product","vulnerabilityName","dateAdded","dueDate",
                "requiredAction","shortDescription","knownRansomwareCampaignUse","notes","cwes",
            }
            extra = {k: v[k] for k in v.keys() if k not in known_keys}

            conn.execute(text("""
              INSERT INTO kev_entry (
                cve_id, vendor_project, product, vulnerability_name,
                date_added, due_date,
                known_ransomware_campaign_use,
                required_action, short_description,
                notes, cwes, extra,
                last_seen_catalog_version, last_seen_date_released
              ) VALUES (
                :cve_id, :vendor_project, :product, :vuln_name,
                :date_added, :due_date,
                :known_ransom,
                :required_action, :short_desc,
                :notes, :cwes::jsonb, :extra::jsonb,
                :catalog_version, :date_released
              )
              ON CONFLICT (cve_id) DO UPDATE SET
                vendor_project = EXCLUDED.vendor_project,
                product = EXCLUDED.product,
                vulnerability_name = EXCLUDED.vulnerability_name,
                date_added = EXCLUDED.date_added,
                due_date = EXCLUDED.due_date,
                known_ransomware_campaign_use = EXCLUDED.known_ransomware_campaign_use,
                required_action = EXCLUDED.required_action,
                short_description = EXCLUDED.short_description,
                notes = EXCLUDED.notes,
                cwes = EXCLUDED.cwes,
                extra = EXCLUDED.extra,
                last_seen_catalog_version = EXCLUDED.last_seen_catalog_version,
                last_seen_date_released = EXCLUDED.last_seen_date_released,
                updated_at = now()
            """), {
                "cve_id": cve_id,
                "vendor_project": vendor_project,
                "product": product,
                "vuln_name": vuln_name,
                "date_added": date_added,
                "due_date": due_date,
                "known_ransom": known_ransom,
                "required_action": required_action,
                "short_desc": short_desc,
                "notes": notes,
                "cwes": json.dumps(cwes) if cwes is not None else None,
                "extra": json.dumps(extra) if extra else "{}",
                "catalog_version": catalog_version,
                "date_released": date_released,
            })
            upserted += 1

    print(f"Upserted kev_entry rows: {upserted} (catalogVersion={catalog_version})")

if __name__ == "__main__":
    main()
```

실행:

```bash
python scripts/ingest_kev.py
```

이 단계까지 끝나면 “KEV 자체를 내부 DB로 가져오는” 문제는 해결됩니다. 하지만 우선순위 엔진이 되려면 다음 조인이 필요합니다.

- `kev_entry.cve_id` ↔ 자산에서 발견된 `cve_id`

여기서부터는 KEV가 아니라 조직의 관측 능력(자산·스캔·SBOM)이 병목이 됩니다.

---

## 자산 매칭의 핵심은 `cveID`를 공용 조인 키로 만드는 것

KEV는 제품 식별자를 CPE 같은 정규화된 키로 주지 않습니다. `vendorProject`, `product`는 사람이 읽기 좋은 문자열이고, 실자산 조인에는 보통 부족합니다[^2].

그래서 실전에서는 “자산이 무엇을 쓰고 있는지”를 아래 중 하나로 먼저 관측해야 합니다.

- VM/서버: 에이전트 기반 취약점 관리(패키지 버전 → CVE)
- 컨테이너 이미지: 이미지 스캔(레이어 패키지 → CVE)
- 애플리케이션 의존성: SCA(라이브러리 버전 → CVE)

이 글에서는 컨테이너 이미지 스캔을 대표 예제로 잡습니다. 이유는 단순합니다.

- CI에서 반복 실행하기 쉽고
- 결과가 JSON으로 안정적으로 떨어지고
- 자산 식별자(image digest)까지 확보 가능하기 때문입니다.

Trivy는 `--format json` 출력에 `VulnerabilityID` 필드를 포함합니다[^5]. 이 `VulnerabilityID`가 사실상 CVE ID 역할을 하므로 KEV의 `cveID`와 조인이 가능합니다.

### 자산(CMDB) 예시: CSV로 ingest

CMDB가 이미 있다면 API로 당겨오는 편이 낫지만, 파이프라인을 설명할 때 CSV가 구현 난이도가 낮습니다.

`assets.csv`:

```csv
asset_id,asset_type,owner_team,env,internet_exposed,criticality,change_freeze,tags
img:sha256:511a44083d3a23416fadc62847c45d14c25cbace86e7a72b2b350436978a0450,container-image,platform,prod,true,high,false,"{\"repo\":\"payments/api\",\"cluster\":\"eks-prod\"}"
img:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,container-image,search,prod,false,medium,true,"{\"repo\":\"search/api\"}"
```

`ingest_assets.py`는 이 CSV를 그대로 `asset` 테이블로 올립니다(코드는 길이 관계로 생략하고, 핵심은 `asset_id`를 안정적인 식별자로 고정하는 것입니다).

### findings 예시: Trivy로 이미지 스캔하고 JSON 저장

```bash
trivy image --format json --output trivy.json debian:12
```

Trivy JSON에는 `Results[].Vulnerabilities[].VulnerabilityID` 형태로 CVE가 들어옵니다[^5].

`ingest_findings_trivy.py`는 다음을 합니다.

- 입력 JSON에서 CVE 목록 추출
- `asset_id`(예: image digest)로 귀속
- `finding(asset_id, scanner='trivy', cve_id)` upsert

이 과정을 통해, KEV와 자산을 이어주는 조인 키(`cve_id`)가 내부 DB에 생깁니다.

---

## `dueDate` → 내부 SLA 변환: 링(ring)과 에스컬레이션을 숫자로 만든다

여기서부터가 패치 우선순위 엔진의 본체입니다. 목표는 단순합니다.

- `kev_entry.due_date`를 “사람이 캘린더에 적는 날짜”로 두지 않고
- “시스템이 티켓/알림/배포 순서를 자동 생산”하도록 만드는 것

내부 모델은 다음처럼 잡는 편이 운영에 맞습니다.

- KEV `dueDate`는 외부 기준선이다.
- 내부 Decision SLA는 `dueDate`와 동일하게 잡는다.
- 단, Decision SLA의 의미는 “패치 완료”가 아니라 “처리 방식 확정”이다.

그리고 배포 링은 “긴급도”와 “변경 리스크”를 함께 반영해야 합니다.

- 긴급도는 주로 `dueDate - today`로 계산
- 변경 리스크는 `env`, `criticality`, `change_freeze` 같은 자산 속성으로 계산

예를 들어 다음 규칙은 꽤 실용적입니다.

- Ring0: (인터넷 노출) AND (D-3 이하 또는 이미 past due)
- Ring1: (프로덕션) AND (D-14 이하)
- Ring2: 그 외(정기 패치 사이클)
- Change freeze인 경우 Ring을 올리지 않고, 대신 “완화 + 예외 승인” 플로우로 보낸다.

BOD 26-04가 말하는 “노출도를 제거하면 타임라인이 변할 수 있다”는 지점 때문에[^4], 시스템은 완화조치가 들어오면 자동으로 ring을 재산정할 수 있어야 합니다.

- 예: WAF 룰, 기능 플래그 off, 포트 차단, allowlist 전환
- 예: 퍼블릭 엔드포인트 제거, 사설망으로 이관

즉, 우선순위 엔진은 패치 엔진이기 전에 “상태 머신”입니다.

---

## `match_and_ticket.py`: KEV×자산×findings를 묶어 work item을 만든다

이 단계는 크게 3개의 SQL로 끝납니다.

1) KEV에 존재하는 CVE 중, 자산에서 발견된 CVE를 찾기
2) `dueDate` 기반으로 `decision_due_date`, `ring` 계산
3) Jira 티켓이 없다면 생성하고 `work_item.jira_key`에 기록

### Jira 티켓 생성: `duedate` 필드를 쓰되 프로젝트 설정을 의심한다

Jira Cloud REST API의 이슈 생성 예시는 `fields.duedate`를 날짜 문자열(`YYYY-MM-DD`)로 받는 샘플을 포함합니다[^6].

다만 팀 관리 프로젝트(team-managed)에서는 UI의 Due date가 실제로는 커스텀 필드로 매핑되는 경우가 있고, REST 응답의 `duedate`가 null로 보이며 `customfield_xxxxx`로 저장되는 케이스가 있습니다[^7].

그래서 자동화에서 안전한 방식은 다음 중 하나입니다.

- 회사 표준 프로젝트(회사 관리)로 보안 티켓을 받는다.
- 또는 `createmeta`로 필드 스키마를 조회하고, 실제 due date 필드 ID를 환경별로 설정한다.

코드는 단순화를 위해 `duedate`를 직접 쓰는 버전으로 제시합니다.

```python
# scripts/match_and_ticket.py
import os
from datetime import date, datetime

import requests
from sqlalchemy import create_engine, text

DB_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://kev:kev@localhost:5432/kev")

JIRA_BASE = os.getenv("JIRA_BASE")  # e.g. https://your-domain.atlassian.net
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT = os.getenv("JIRA_PROJECT", "SEC")
JIRA_ISSUE_TYPE = os.getenv("JIRA_ISSUE_TYPE", "Task")

def compute_ring(internet_exposed: bool, env: str, days_left: int, change_freeze: bool) -> str:
    if change_freeze:
        return "freeze"
    if internet_exposed and days_left <= 3:
        return "ring0"
    if env == "prod" and days_left <= 14:
        return "ring1"
    return "ring2"

def jira_create(summary: str, description: str, due: date, labels: list[str]) -> str:
    url = f"{JIRA_BASE}/rest/api/3/issue"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT},
            "issuetype": {"name": JIRA_ISSUE_TYPE},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                ],
            },
            "duedate": due.isoformat(),
            "labels": labels,
        }
    }

    r = requests.post(url, json=payload, auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()["key"]

def main():
    if not all([JIRA_BASE, JIRA_EMAIL, JIRA_API_TOKEN]):
        raise SystemExit("Missing JIRA_* env vars")

    engine = create_engine(DB_URL)
    today = date.today()

    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS work_item (
          id BIGSERIAL PRIMARY KEY,
          asset_id TEXT NOT NULL,
          cve_id TEXT NOT NULL,
          kev_due_date DATE NOT NULL,
          decision_due_date DATE NOT NULL,
          ring TEXT NOT NULL,
          status TEXT NOT NULL,
          jira_key TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE(asset_id, cve_id)
        );
        """))

        rows = conn.execute(text("""
          SELECT
            a.asset_id,
            a.env,
            a.internet_exposed,
            a.change_freeze,
            a.criticality,
            k.cve_id,
            k.vendor_project,
            k.product,
            k.vulnerability_name,
            k.short_description,
            k.required_action,
            k.due_date
          FROM finding f
          JOIN asset a ON a.asset_id = f.asset_id
          JOIN kev_entry k ON k.cve_id = f.cve_id
        """)).fetchall()

        for r in rows:
            asset_id, env, internet_exposed, change_freeze, criticality, cve_id, vendor, product, vuln_name, short_desc, required_action, due_date = r
            days_left = (due_date - today).days

            ring = compute_ring(internet_exposed, env, days_left, change_freeze)
            decision_due = due_date

            # upsert work_item
            wi = conn.execute(text("""
              INSERT INTO work_item (asset_id, cve_id, kev_due_date, decision_due_date, ring, status)
              VALUES (:asset_id, :cve_id, :kev_due, :decision_due, :ring, 'new')
              ON CONFLICT (asset_id, cve_id) DO UPDATE SET
                kev_due_date = EXCLUDED.kev_due_date,
                decision_due_date = EXCLUDED.decision_due_date,
                ring = EXCLUDED.ring,
                updated_at = now()
              RETURNING id, jira_key
            """), {
                "asset_id": asset_id,
                "cve_id": cve_id,
                "kev_due": due_date,
                "decision_due": decision_due,
                "ring": ring,
            }).fetchone()

            wi_id, jira_key = wi
            if jira_key:
                continue

            summary = f"[KEV] {cve_id} on {asset_id} (due {due_date.isoformat()})"
            desc = (
                f"asset_id: {asset_id}\n"
                f"env: {env}, internet_exposed: {internet_exposed}, change_freeze: {change_freeze}, criticality: {criticality}\n\n"
                f"KEV: {vendor} / {product}\n"
                f"vulnerabilityName: {vuln_name}\n\n"
                f"shortDescription: {short_desc}\n\n"
                f"requiredAction: {required_action}\n"
            )
            labels = ["KEV", cve_id, ring, env]

            key = jira_create(summary, desc, decision_due, labels)
            conn.execute(text("UPDATE work_item SET jira_key=:k, status='ticketed', updated_at=now() WHERE id=:id"), {"k": key, "id": wi_id})
            print(f"Created Jira issue: {key} for {asset_id} {cve_id} ring={ring}")

if __name__ == "__main__":
    main()
```

이 코드는 “KEV에 있고, 자산에서 발견되었고, 아직 티켓이 없으면 만든다” 수준의 최소 기능입니다. 실제 운영에서는 추가로 아래가 필요합니다.

- 티켓 dedup: `asset_id + cve_id`를 Jira 쪽에도 키로 심기(이슈 property 또는 커스텀 필드)
- 상태 동기화: Jira가 Done이면 work_item도 closed
- 예외 흐름: ring=freeze면 패치 티켓 대신 “완화/예외 승인” 티켓으로 분기

---

## 알림과 에스컬레이션: Slack은 ‘발생’이 아니라 ‘초과’에 반응해야 한다

사람이 KEV를 매일 읽는 방식은 결국 한계가 옵니다. 이유는 단순합니다.

- 들어오는 속도가 사람의 처리량을 이긴다.
- `dueDate`는 계속 다가온다.

Slack 알림을 붙일 때 실전에서 가장 흔한 실패는 “새 work item이 생길 때마다 다 쏘는 것”입니다. 이렇게 하면 며칠 지나지 않아 알림이 무시됩니다.

알림은 상태 변화에 반응해야 합니다.

- D-7 진입
- D-3 진입
- Past due 전환
- internet_exposed 값이 false→true로 변경
- change_freeze=true로 인해 예외 티켓이 필요한데 아직 없을 때

또한 KEV 데이터는 평일 미국 동부 업무시간에 업데이트될 가능성이 높습니다[^3]. 한국 조직이라면 새벽에 업데이트된 항목이 오전 업무 시작 시점에 이미 D-2 같은 상태로 들어올 수 있습니다. 알림 윈도우를 “한국 시간” 기준으로 설계하지 않으면 초반부터 밀립니다.

---

## 배포 링 자동 생성: patch를 “동시다발 작업”에서 “파이프라인 작업”으로 바꾼다

링을 만든다는 것은 단지 우선순위를 매기는 게 아니라, 배포 파이프라인의 형태를 강제한다는 뜻입니다.

- Ring0: hotfix 레인(긴급 패치, blast radius 최소화)
- Ring1: 표준 레인(다음 정규 배포에 포함)
- Ring2: 정기 레인(월간/분기 패치)
- Freeze: 완화/예외 레인(패치가 아니라 리스크 처리)

이 글의 예시는 Jira 티켓만 만들지만, 링 값이 DB에 남으면 다음 자동화가 열립니다.

- Ring0 티켓은 canary 배포 작업을 자동 생성
- Ring1 티켓은 다음 릴리스 브랜치에 패치 PR 포함 여부를 체크
- Ring2 티켓은 정기 패치 보드로 이동

중요한 점은, 링 자동화가 “배포 도구”보다 먼저 “자산 소유권”을 강제한다는 사실입니다. `asset.owner_team`이 비어 있으면 어떤 자동화도 끝까지 갈 수 없습니다.

---

## 함정과 트레이드오프: KEV 자동화가 실패하는 지점들

### 1) `dueDate`를 단일 SLA로 쓰면 change freeze와 충돌한다

프로덕션은 항상 변화창이 있는 게 아니라, 특정 기간에는 변경을 멈춥니다. 이때 `dueDate=3일`이 들어오면 시스템은 패치를 강제하지만, 조직은 실제로는 “완화 후 일정 조정”을 선택할 수밖에 없습니다.

따라서 `change_freeze`는 단순 속성이 아니라 정책 엔진의 분기 조건입니다.

- freeze 동안에도 Decision SLA는 유지
- Remediation SLA는 예외로 미룰 수 있으나, 그 근거와 만료일이 자동으로 남아야 함

### 2) KEV는 제품 문자열을 주지만, 조인은 CVE로 해야 한다

`vendorProject/product`로 CMDB를 뒤져 매칭하는 방식은 초기에만 동작합니다. 운영 규모가 커지면 결국 CVE 기반 매칭이 필요하고, 그건 스캐너 품질에 종속됩니다.

Trivy는 JSON 리포트에 `VulnerabilityID`를 제공하지만[^5], 스캐너마다 중복/오탐/누락이 존재합니다. 이 문제는 KEV 자동화의 문제가 아니라 관측의 문제라서, “엔진이 거짓말을 하지 않게” 해야 합니다.

- 스캐너 원본 JSON을 그대로 저장(재현 가능성)
- finding을 만들 때 “검증된 근거 링크” 또는 스캔 시각/대상 버전도 같이 저장

### 3) `notes`는 사람이 읽는 필드라서, 기계는 파싱하지 않는 편이 낫다

KEV 엔트리의 `notes`는 URL이 여러 개 들어가기도 하고, 세미콜론 구분으로 나열되기도 합니다[^1]. 이걸 파싱해 자동으로 뭘 하겠다는 욕심은 대개 유지보수 비용만 올립니다.

- `notes`는 티켓 본문에 그대로 넣고
- “자동화에 필요한 필드”는 내부에서 별도로 관리하는 편이 낫습니다.

### 4) 스케줄러는 GitHub Actions로 시작할 수 있지만, 결국 내부 런타임으로 옮기게 된다

처음에는 GitHub Actions `on.schedule`로 충분합니다. 문서도 POSIX cron 문법으로 스케줄 실행을 지원한다고 명시합니다[^8].

다만 KEV ingest는 “한 번 놓치면 dueDate를 놓치는” 형태의 작업이라서, 장기적으로는 아래가 필요해집니다.

- 재시도/백오프
- 실행 이력과 실패 원인 추적
- 부분 성공(ingest는 됐는데 티켓 생성이 실패) 처리

이 시점부터는 Airflow, Argo Workflows, Temporal 같은 내부 오케스트레이터가 더 안정적입니다.

---

## 도입 판단 기준: 언제 이게 과하고, 언제 이게 꼭 필요해지는가

이 엔진이 과한 환경도 있습니다.

- 자산 수가 적고(수십 대)
- 서비스가 거의 외부에 노출되지 않고
- 패치 사이클이 이미 매우 짧으며
- 보안 티켓과 개발 티켓이 같은 큐에서 잘 굴러가는 조직

반대로 아래 조건 중 2개만 만족해도 자동화가 급격히 이득을 냅니다.

- 외부 노출 자산이 많고, 인터넷 exposure 판단이 자주 바뀐다
- 컨테이너/서버/의존성 취약점 데이터가 여러 스캐너로 분산되어 있다
- 변경관리 때문에 패치를 “언제나 즉시” 할 수 없다
- dueDate를 놓쳤을 때 감사/고객 신뢰/사고 대응 비용이 매우 커진다

내 경우에는 KEV ingest 자체보다 “CVE를 자산에 귀속시키는 키 설계(식별자)”와 “예외를 시스템 안으로 끌고 들어오는 것(대체통제, freeze)”이 전체 프로젝트 난이도의 대부분을 차지했습니다. 결국 KEV는 데이터 소스일 뿐이고, 우선순위 엔진은 조직의 운영 규칙을 코드로 고정하는 작업입니다.

---

## 참고 자료

- [cisagov/kev-data README](https://github.com/cisagov/kev-data/blob/develop/README.md)
- [known_exploited_vulnerabilities.json](https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json)
- [known_exploited_vulnerabilities_schema.json](https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities_schema.json)
- [BOD 26-04: Prioritizing Security Updates Based on Risk](https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk)
- [Jira Cloud REST API: Issues](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/)
- [Atlassian Support: due date field not showing 이슈](https://support.atlassian.com/jira/kb/due-date-field-not-showing-in-team-managed-backlog-for-jira-cloud/)
- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [Trivy Reporting 문서](https://www.trivy.dev/docs/v0.53/guide/configuration/reporting/)
- [AWS Tools Installer V2로 개발자 머신과 CI의 AWS 툴 설치를 표준화하기](https://daewooki.github.io/posts/standardize-aws-toolchain-installs/)

[^1]: <https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json>
[^2]: <https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities_schema.json>
[^3]: <https://github.com/cisagov/kev-data/blob/develop/README.md>
[^4]: <https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk>
[^5]: <https://www.trivy.dev/docs/v0.53/guide/configuration/reporting/>
[^6]: <https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/>
[^7]: <https://support.atlassian.com/jira/kb/due-date-field-not-showing-in-team-managed-backlog-for-jira-cloud/>
[^8]: <https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
