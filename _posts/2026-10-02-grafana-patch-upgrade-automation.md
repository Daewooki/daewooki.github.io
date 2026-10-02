---
title: "Grafana 패치 업그레이드 검증 자동화 설계"
description: "Grafana 13.1.7 같은 잦은 패치에 대응해 플러그인·렌더링·프로비저닝·권한·롤백을 CI로 고정하는 운영 설계와 실행 코드."
date: 2026-10-02 10:37:04 +0900
categories: ["Data", "Grafana"]
tags: ["grafana", "release-engineering", "regression-testing", "plugin-compatibility", "dashboards-as-code", "rollback"]
render_with_liquid: false
---

## 13.1.7 패치가 의미하는 것: 수동 업그레이드의 한계점

Grafana 13.1.7의 릴리스 날짜가 2026-09-29로 표시됩니다[^1]. 이 사실 자체는 특별할 게 없는데, 운영팀 관점에서 중요한 건 **패치 릴리스가 꾸준히 나온다는 점이 ‘업그레이드 주기’를 강제한다**는 데 있습니다.

Grafana는 self-managed 기준으로 MAJOR.MINOR.PATCH 형태의 semantic-like 버전 정책을 설명하고, major는 연 1회 수준, minor는 기능 추가, patch는 버그/보안 수정 중심으로 배포된다고 가이드합니다[^2]. 문서에는 “자주 업그레이드하라”, “업그레이드 전 changelog/guide를 읽어라”, “dev/test에서 먼저 굴려라”, “업그레이드 전에 DB 백업을 떠라” 같은 권고가 반복됩니다. 이 조언은 맞는데, 대규모 대시보드(수백~수천 개)와 플러그인(수십 개), 프로비저닝(파일/terraform), 권한 모델(폴더 ACL/RBAC), 알림(규칙/notification policy)까지 얹히는 순간부터는 사람이 “자주”를 감당하지 못합니다.

수동 업그레이드가 한계에 도달하는 신호는 대략 아래처럼 옵니다.

- 패치를 늦추면 보안 공지가 쌓이고, 어느 순간부터는 “언젠가”가 아니라 “이번 주”가 됩니다.
- 패치를 올릴 때마다 플러그인이 1~2개씩 미세하게 깨지고, 매번 원인 규명이 길어집니다.
- 특정 팀 대시보드만 렌더링이 흐트러지거나(테이블 컬럼 폭, time series legend, threshold 색 등), 특정 브라우저에서만 재현됩니다.
- 프로비저닝으로 만든 폴더/대시보드의 권한 상속이 기대와 달라져서, 접근 제어 이슈가 “기능 장애”가 아니라 “보안 사고 후보”가 됩니다.
- 되돌리기(rollback)가 컨테이너 태그 내리는 걸로 끝나지 않고, DB migration 때문에 “데이터 롤백”이 됩니다.

결국 운영팀이 해야 하는 일은 ‘업그레이드’가 아니라 **업그레이드-검증을 제품 패치 주기와 같은 리듬으로 자동화**하는 겁니다. 이 글은 그 자동화 설계를 운영 관점에서 구체화합니다.

## 13.1.7이 고친 것: 보안 패치가 ‘권한 검증’을 요구한다

GitHub 릴리스 목록에서 13.1.7은 보안 항목으로 CVE 3건을 고쳤다고 표시됩니다[^3]. 각각을 보면 운영 자동화에서 어떤 “검증 포인트”가 생기는지 명확해집니다.

### CVE-2026-13719: 폴더 제한이 비었을 때 alert rules list가 전체를 내준다

요약은 이렇습니다.

- “읽을 수 있는 폴더 목록”이 비어 있을 때 폴더 제한이 떨어져 나가(alert rules API list endpoint에서) 조직의 모든 alert rule이 반환될 수 있었고,
- 13.1.0부터는 folder filter로 트리거할 수 있었다고 합니다.
- 노출되는 건 rule configuration이며 data source credentials는 노출되지 않는다고 명시합니다.
- 고정(fixed) 버전에 13.1.7이 포함됩니다[^4].

이건 “보안 패치니까 빨리 올리자”로 끝나지 않습니다. 운영 자동화 관점에서 더 중요한 건 **우리 조직에서 ‘폴더 접근이 비어 있는’ 상태가 실제로 존재하는가**입니다.

- 신규 입사자/외주 계정/임시 계정이 Viewer로 들어오고, 폴더 권한은 팀 단위로만 주는 조직에서는 충분히 가능합니다.
- service account를 최소 권한으로 만들고 폴더 권한을 별도로 주는 모델에서도 가능합니다.

즉, 이 CVE는 패치 적용 자체도 중요하지만, 업그레이드 검증 파이프라인에 “권한 경계 테스트”를 넣어야 하는 직접적인 근거가 됩니다.

### CVE-2026-81841: paused shared dashboard 토큰이 bootstrap 데이터를 계속 노출

요약은 더 운영 친화적으로 쓰면 다음입니다.

- 공유(공개) 대시보드를 pause했는데도, 프론트엔드 bootstrap 데이터를 주는 엔드포인트에서는 토큰이 계속 유효했고,
- 링크를 가진 누구나 인증 없이 data source configuration을 가져갈 수 있었으며,
- 특히 browser access를 쓰는 data source의 stored credentials까지 포함될 수 있었다고 합니다.
- 삭제(delete)는 토큰을 revoke하지만, pause만으로는 충분하지 않았다는 얘기입니다.
- 13.1.7에서 고쳐졌다고 명시되어 있습니다[^5].

여기서 자동화 포인트는 두 가지입니다.

1) 공유 대시보드를 기능적으로 쓰는 조직이라면, 업그레이드 검증에서 “pause 이후 접근 차단”이 실제로 막히는지 회귀 테스트가 필요합니다.

2) 공유 대시보드를 원천적으로 금지하거나 제한하는 조직이라면, “설정이 의도대로 적용되어 있는지”를 정기적으로 검증해야 합니다. 패치가 잦을수록 구성 drift가 늘어나고, drift는 공유 토큰/권한/보안 헤더 같은 데서 먼저 사고가 납니다.

### CVE-2026-13720: 대시보드 API를 통한 file-provisioning provenance 위조

13.1.7이 CVE-2026-13720도 수정했다고 표시되어 있고[^3], advisory 페이지 제목은 “Editor can forge file-provisioning provenance on dashboards via the dashboard API”입니다[^6].

내가 이걸 운영 관점에서 중요하게 보는 이유는, Grafana에서 dashboard provisioning은 단순 편의 기능이 아니라 운영 모델이기 때문입니다.

- GitOps로 대시보드를 파일로 관리하고,
- UI 수정은 금지하거나(allowUiUpdates=false)
- 변경은 PR로만 들어오게 만들면

대시보드 변경 추적과 책임소재가 깔끔해집니다. 그런데 “file-provisioning provenance”가 위조 가능했다는 건, 최소 권한을 Editor 수준으로 넓게 준 조직에서 “as-code로 관리되는 것처럼 보이지만 실은 UI/API로 바뀐” 상태가 생길 수 있다는 뜻입니다. 이건 기능 장애보다 더 나쁩니다. 운영자가 눈치채기 어렵고, 나중에 사고가 났을 때 조사 비용이 폭발합니다.

그래서 패치 릴리스에 맞춘 자동화는 “렌더링이 깨지나?”보다 한 단계 위로 올라가서, **대시보드 as-code의 무결성**을 자동으로 점검하는 쪽으로 설계해야 합니다.

## 패치 릴리스에 맞춘 업그레이드 파이프라인의 기본 골격

내가 대규모 Grafana 운영에서 “패치 업그레이드”를 안전하게 만드는 방법은 결국 4가지 자동화를 묶는 것입니다.

- **플러그인 호환성 스캔**: 업그레이드 후보 버전에 대해 설치된 플러그인들이 요구하는 Grafana 버전 범위를 만족하는지, 서명 정책을 위반하지 않는지, 그리고 플러그인 업데이트가 암묵적으로 끼어들지 않는지 확인합니다.
- **대시보드 렌더링 회귀 테스트**: 실제 데이터 소스를 붙인 상태에서 렌더 결과가 유의미하게 변했는지(또는 깨졌는지) 이미지 기반으로 검출합니다.
- **프로비저닝/권한 모델 검증**: 파일 프로비저닝이 덮어쓰는 규칙, 폴더 구조 생성, 폴더 권한/대시보드 권한의 우선순위가 기대와 같은지 계약 테스트(contract test)로 잡아냅니다.
- **롤백 플랜**: 컨테이너 태그 롤백이 아니라 DB/스토리지/플러그인/캐시까지 포함한 되돌리기 절차를 “실제로 실행해본 형태”로 문서화하고 자동화에 포함합니다.

Grafana 문서도 업그레이드 전 테스트/백업을 반복해서 권고합니다[^7][^2]. 중요한 건 권고를 “사람의 체크리스트”로 두지 말고 “CI/CD의 게이트”로 옮기는 겁니다.

아래는 내가 많이 쓰는 형태의 파이프라인 단계입니다.

1) 새 패치 릴리스 감지
- GitHub 릴리스 또는 다운로드 페이지를 폴링해서 13.1.x의 신규 patch가 나오면 버전 bump PR 생성

2) ephemeral 환경에서 후보 버전 부팅
- 같은 프로비저닝(대시보드/데이터소스/알림/플러그인/권한)을 넣고 boot

3) 자동 검증
- 플러그인 스캔
- 렌더링 회귀
- 프로비저닝/권한 계약 테스트

4) canary → stage → prod 순서의 롤아웃
- stage에서 일정 시간 관찰 후 prod canary

5) 실패 시 롤백
- “되돌리기 가능한 지점”이 어디인지(특히 DB migration) 명확히 하고, 자동화된 복구(runbook)로 실행

이 글의 코드는 2)~3)을 로컬에서도 재현 가능하게 만든 최소 단위입니다.

## 플러그인 호환성 스캔: plugin.json과 서명 정책을 CI에서 고정하기

플러그인은 Grafana 업그레이드를 어려워지게 하는 1순위입니다. 이유는 간단합니다.

- Grafana core는 patch에서 API payload가 거의 안 바뀐다 하더라도, 플러그인은 UI/SDK/빌드 체인 변화에 더 취약합니다.
- 플러그인이 깨지면 증상이 대시보드에 나타나서, 원인이 core인지 plugin인지 구분이 늦어집니다.

### plugin.json의 grafanaDependency를 정적 분석으로 체크

Grafana 플러그인은 metadata로 plugin.json을 갖고, 거기에 dependencies가 정의됩니다. 공식 문서에서 `dependencies.grafanaDependency`는 “Required Grafana version for this plugin”으로 설명합니다[^8].

그래서 업그레이드 검증의 첫 관문은 이겁니다.

- 현재 설치된 플러그인들의 grafanaDependency를 수집
- 업그레이드 목표 버전(여기서는 13.1.7)이 제약을 만족하는지 확인

아래 파이썬 스크립트는 서버의 플러그인 디렉터리를 스캔해서 plugin.json을 읽고, `grafanaDependency`가 있는 플러그인만 대상으로 호환성 체크를 합니다.

> 전제: 플러그인 디렉터리가 `/var/lib/grafana/plugins`이고, 각 플러그인 폴더에 `plugin.json`이 있다고 가정합니다.

`requirements.txt`
```txt
semantic_version==2.10.0
```

`scan_plugins.py`
```python
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional, List

from semantic_version import Version, NpmSpec

PLUGIN_DIR = os.environ.get("GRAFANA_PLUGIN_DIR", "/var/lib/grafana/plugins")
TARGET_GRAFANA = os.environ.get("TARGET_GRAFANA", "13.1.7")

@dataclass
class PluginCheck:
    plugin_id: str
    name: str
    grafana_dependency: Optional[str]
    ok: bool
    reason: str

def load_plugin_json(path: str) -> Optional[dict]:
    plugin_json = os.path.join(path, "plugin.json")
    if not os.path.exists(plugin_json):
        return None
    with open(plugin_json, "r", encoding="utf-8") as f:
        return json.load(f)

def iter_plugins(plugin_dir: str):
    if not os.path.isdir(plugin_dir):
        raise RuntimeError(f"Plugin dir not found: {plugin_dir}")

    for entry in sorted(os.listdir(plugin_dir)):
        full = os.path.join(plugin_dir, entry)
        if not os.path.isdir(full):
            continue
        meta = load_plugin_json(full)
        if meta is None:
            continue
        yield entry, meta

def check_one(plugin_folder: str, meta: dict, target: Version) -> PluginCheck:
    plugin_id = meta.get("id", plugin_folder)
    name = meta.get("name", plugin_id)
    deps = meta.get("dependencies", {}) or {}
    grafana_dep = deps.get("grafanaDependency")

    if not grafana_dep:
        # grafanaDependency를 안 적는 플러그인도 있고, core plugin은 아예 다르다.
        return PluginCheck(plugin_id, name, None, True, "no grafanaDependency")

    try:
        spec = NpmSpec(grafana_dep)
    except Exception as e:
        return PluginCheck(plugin_id, name, grafana_dep, False, f"invalid grafanaDependency spec: {e}")

    ok = spec.match(target)
    reason = "matched" if ok else f"target {target} not in spec {grafana_dep}"
    return PluginCheck(plugin_id, name, grafana_dep, ok, reason)

def main() -> int:
    target = Version(TARGET_GRAFANA)

    results: List[PluginCheck] = []
    for folder, meta in iter_plugins(PLUGIN_DIR):
        results.append(check_one(folder, meta, target))

    bad = [r for r in results if not r.ok]

    print(f"Target Grafana: {target}")
    print(f"Plugin dir: {PLUGIN_DIR}")
    print(f"Checked: {len(results)} plugins")

    for r in results:
        dep = r.grafana_dependency or "-"
        status = "OK" if r.ok else "BAD"
        print(f"[{status}] {r.plugin_id} | dep={dep} | {r.reason}")

    if bad:
        print(f"\nFAILED: {len(bad)} plugin(s) incompatible")
        return 2

    print("\nPASSED: all plugin constraints satisfied")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

실행 예시:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export GRAFANA_PLUGIN_DIR=/var/lib/grafana/plugins
export TARGET_GRAFANA=13.1.7
python scan_plugins.py
```

이 스캔이 유효한 이유는 단순합니다. 업그레이드 당일에 플러그인이 깨지는 대표적인 경우는 “플러그인이 지원하는 Grafana 범위를 벗어난 업그레이드”이기 때문입니다. 이건 사람이 릴리스 노트를 읽어도 놓치고, CI가 잡기 제일 쉬운 유형입니다.

### 서명 정책: unsigned plugin을 allowlist로 굴리는 조직은 특히 자동화가 필요하다

Grafana는 plugin signature verification을 보안 기능으로 설명하고, 서명되지 않은 플러그인은 정책적으로 제한된다는 점을 강조합니다[^9]. 실제 운영에서는

- 사내 플러그인,
- 폐쇄망 환경에서 ZIP로 배포한 플러그인,
- 과거에 설치해 둔 레거시 플러그인

때문에 `allow_loading_unsigned_plugins` 같은 allowlist가 남아있는 경우가 많습니다.

문제는 이 allowlist가 시간이 지날수록 “기술 부채가 아니라 보안 부채”가 된다는 점입니다.

- 패치 릴리스에서 CVE가 터졌을 때, 공격자가 노릴 표면은 core보다 플러그인/확장 지점인 경우가 흔합니다.
- allowlist는 운영자가 “그게 아직도 필요한지” 모르는 상태로 유지됩니다.

그래서 내가 하는 건 단순합니다.

- 운영 레포지토리에 allowlist를 코드로 선언하고(ini/values.yaml)
- CI에서 “allowlist에 있는 플러그인이 실제로 설치되어 있는지”, “설치된 플러그인 중 unsigned를 요구하는 플러그인이 새로 생겼는지”를 diff로 감지합니다.

이 검증은 조직마다 환경차가 크니 여기서는 설계만 적습니다. 핵심은 allowlist를 무조건 줄이는 방향으로 가되, 줄이는 과정은 수동이 아니라 파이프라인 diff로 강제하는 쪽이 비용이 덜 듭니다.

### 플러그인 업데이트를 Grafana 업그레이드와 분리한다

패치 업그레이드가 잦을수록 “이번에 올린 게 Grafana 영향인지, 플러그인 최신 버전이 같이 들어와서 그런지”가 섞입니다. 그래서 운영 자동화에서 나는 플러그인을 이렇게 다룹니다.

- Grafana 버전 bump PR과 플러그인 버전 bump PR을 분리
- 업그레이드 검증 파이프라인에서 플러그인 버전은 고정
- 플러그인 업데이트는 따로 검증 파이프라인을 돌리고 별도 롤아웃

Grafana CLI는 `grafana cli plugins ls` 같은 명령을 공식 문서에 포함하고 있습니다[^10]. 이걸로 현재 상태를 수집하고, 상태를 스냅샷으로 남겨 “업그레이드 전후에 플러그인이 바뀌지 않았는지”를 확인하는 쪽으로 갑니다.

## 대시보드 렌더링 회귀 테스트: 이미지 렌더러를 테스트 하네스로 쓰기

대시보드가 수백 개가 되면, 사람이 UI를 클릭해서 “깨진 것 같은데?”를 찾는 방식은 더 이상 통하지 않습니다. 더 큰 문제는 이런 유형입니다.

- 완전히 깨지지 않는다.
- 하지만 숫자 포맷/축 스케일/legend truncation/threshold 색/테이블 정렬 같은 게 바뀐다.
- 그 변화가 특정 화면 폭/특정 time range에서만 발생한다.

이런 건 로그로도 잘 안 잡히고, 사용자가 먼저 발견합니다. 그래서 나는 렌더링 회귀 테스트를 “시각적 스냅샷 테스트”로 운영합니다.

### Grafana Image Renderer: 플러그인이 아니라 서비스로 고정한다

Grafana는 이미지 렌더링 기능을 설명하면서, 과거에는 plugin 형태였지만 현재는 그 plugin이 deprecated이고 업데이트가 없다고 명시합니다. 대신 renderer service를 쓰는 형태로 가이드를 제공합니다[^11].

또한 `latest` 태그를 제공하긴 하지만, 프로덕션에서는 특정 버전을 pinning하라고 권고합니다[^11]. 업그레이드 검증 자동화 관점에서는 이 문장이 더 중요합니다.

- Grafana patch 업그레이드를 검증할 때, renderer도 함께 흔들리면 결과 해석이 불가능합니다.
- 그래서 renderer는 “고정된 버전”으로 두고, Grafana만 바꿔서 비교하는 테스트가 필요합니다.

### 로컬에서 재현 가능한 렌더링 회귀 환경(docker compose)

아래 구성은 현실적인 최소 단위입니다.

- Prometheus + node-exporter로 실제 time series를 만든다.
- Grafana 13.1.6(기준)과 13.1.7(후보)을 같은 프로비저닝으로 올린다.
- renderer service를 붙여 /render 경로로 PNG를 뽑는다.
- 두 버전의 PNG를 perceptual hash로 비교한다.

`compose.yml`
```yaml
services:
  prometheus:
    image: prom/prometheus:v2.55.0
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro

  node_exporter:
    image: prom/node-exporter:v1.8.2
    ports:
      - "9100:9100"

  renderer:
    image: grafana/grafana-image-renderer:latest
    ports:
      - "8081:8081"

  grafana_1316:
    image: grafana/grafana-enterprise:13.1.6
    ports:
      - "3001:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_RENDERING_SERVER_URL: http://renderer:8081/render
      GF_RENDERING_CALLBACK_URL: http://grafana_1316:3000/
      GF_USERS_DEFAULT_THEME: dark
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro

  grafana_1317:
    image: grafana/grafana-enterprise:13.1.7
    ports:
      - "3002:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_RENDERING_SERVER_URL: http://renderer:8081/render
      GF_RENDERING_CALLBACK_URL: http://grafana_1317:3000/
      GF_USERS_DEFAULT_THEME: dark
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
```

`prometheus/prometheus.yml`
```yaml
global:
  scrape_interval: 5s

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ["prometheus:9090"]

  - job_name: node
    static_configs:
      - targets: ["node_exporter:9100"]
```

Grafana provisioning은 공식 문서에서 파일로 대시보드/데이터소스를 공급하고, UI에서 저장한 변경이 이후 프로비저닝 소스 업데이트로 덮어써진다고 설명합니다[^12]. 이 성질이 렌더링 회귀 테스트에서 중요합니다.

- 기준 버전/후보 버전이 “완전히 동일한 대시보드 JSON”을 쓰게 만들 수 있습니다.
- 즉, 렌더 결과 차이는 Grafana core 또는 플러그인 렌더링 차이로 좁혀집니다.

`grafana/provisioning/datasources/datasources.yml`
```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

`grafana/provisioning/dashboards/dashboards.yml`
```yaml
apiVersion: 1

providers:
  - name: "provisioned"
    orgId: 1
    folder: "Infra"
    type: file
    disableDeletion: true
    editable: false
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: false
```

대시보드 예시는 node-exporter 메트릭으로 CPU idle을 time series로 그리는 형태로 두었습니다. “장난감” 대신 실제 운영에서 흔히 있는 패턴(프로메테우스 + 노드 메트릭)을 선택한 이유는 렌더러/시간축/legend/단위 포맷 변화가 비교적 잘 드러나기 때문입니다.

`grafana/dashboards/node-cpu.json`
```json
{
  "uid": "nodecpu",
  "title": "Node CPU",
  "schemaVersion": 39,
  "version": 1,
  "refresh": "10s",
  "time": { "from": "now-30m", "to": "now" },
  "panels": [
    {
      "id": 1,
      "type": "timeseries",
      "title": "CPU idle % (avg)",
      "gridPos": { "x": 0, "y": 0, "w": 24, "h": 10 },
      "targets": [
        {
          "refId": "A",
          "expr": "100 * avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m]))",
          "legendFormat": "idle"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "min": 0,
          "max": 100
        },
        "overrides": []
      }
    },
    {
      "id": 2,
      "type": "timeseries",
      "title": "CPU usage % (100-idle)",
      "gridPos": { "x": 0, "y": 10, "w": 24, "h": 10 },
      "targets": [
        {
          "refId": "A",
          "expr": "100 - (100 * avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m])))",
          "legendFormat": "usage"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "min": 0,
          "max": 100,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 70 },
              { "color": "red", "value": 90 }
            ]
          }
        },
        "overrides": []
      }
    }
  ]
}
```

실행:
```bash
docker compose up -d
# Grafana 기동 대기
curl -u admin:admin http://localhost:3001/api/health
curl -u admin:admin http://localhost:3002/api/health
```

### 렌더링 스냅샷 생성과 비교 코드

이제 두 Grafana 인스턴스에서 같은 패널을 렌더링해서 비교합니다.

`requirements.txt`
```txt
requests==2.32.3
pillow==10.4.0
imagehash==4.3.1
```

`render_regression.py`
```python
import os
import sys
import time
import requests
from PIL import Image
import imagehash

BASELINE = os.environ.get("BASELINE", "http://localhost:3001")  # 13.1.6
CANDIDATE = os.environ.get("CANDIDATE", "http://localhost:3002") # 13.1.7
USER = os.environ.get("GRAFANA_USER", "admin")
PASS = os.environ.get("GRAFANA_PASS", "admin")

# dashboard uid/slug는 URL에 들어간다. slug는 title 기반이라 바뀔 수 있으니
# 운영에서는 고정 slug 정책(또는 API로 slug 조회)을 잡는 편이 낫다.
DASH_UID = "nodecpu"
DASH_SLUG = "node-cpu"

PANELS = [
    1,
    2,
]

OUT_DIR = os.environ.get("OUT_DIR", "./out")
THRESHOLD = int(os.environ.get("PHASH_THRESHOLD", "6"))

def render_panel(base_url: str, panel_id: int) -> bytes:
    # Grafana의 렌더링 엔드포인트는 이미지 렌더러 설정(GF_RENDERING_*)이 되어 있어야 동작한다.
    url = (
        f"{base_url}/render/d-solo/{DASH_UID}/{DASH_SLUG}"
        f"?orgId=1&panelId={panel_id}&width=1400&height=700&tz=UTC"
    )
    r = requests.get(url, auth=(USER, PASS), timeout=120)
    r.raise_for_status()
    return r.content

def save(path: str, content: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)

def phash_of(path: str):
    img = Image.open(path)
    return imagehash.phash(img)

def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    failures = 0

    for pid in PANELS:
        b_png = render_panel(BASELINE, pid)
        c_png = render_panel(CANDIDATE, pid)

        b_path = os.path.join(OUT_DIR, f"baseline_panel_{pid}.png")
        c_path = os.path.join(OUT_DIR, f"candidate_panel_{pid}.png")

        save(b_path, b_png)
        save(c_path, c_png)

        b_hash = phash_of(b_path)
        c_hash = phash_of(c_path)
        dist = b_hash - c_hash

        print(f"panel={pid} baseline={b_hash} candidate={c_hash} dist={dist}")

        if dist > THRESHOLD:
            failures += 1
            print(f"  FAIL: dist {dist} > threshold {THRESHOLD}")
        else:
            print("  OK")

    if failures:
        print(f"\nFAILED: {failures} panel(s) changed beyond threshold")
        return 2

    print("\nPASSED: rendering regression within threshold")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

실행:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python render_regression.py
ls -al ./out
```

운영에서 이 방식을 쓰면 좋은 점은 명확합니다.

- 사람이 UI를 훑지 않아도 된다.
- 실패하면 “어떤 패널이 바뀌었는지”로 범위가 줄어든다.
- 버전이 잦을수록(패치 주기가 짧을수록) 테스트 대상 패널을 ‘핵심 대시보드’로 좁혀도 된다.

핵심 대시보드를 고르는 방법은 팀마다 다르지만, 나는 서비스 의존성 그래프를 운영에 연결해 “핵심 서비스의 SLO 대시보드”부터 우선순위를 두는 방식이 비용 대비 효과가 좋았습니다[^13].

## 프로비저닝/권한 모델 검증: as-code가 깨질 때의 형태를 잡아내기

Grafana 프로비저닝은 “초기 세팅 자동화”를 넘어 운영 모델이 됩니다. 문서가 명시한 성질만 봐도 그렇습니다.

- 프로비저닝된 대시보드를 UI에서 저장해도, 이후 프로비저닝 소스가 업데이트되면 DB의 대시보드는 프로비저닝 파일로 항상 overwrite된다고 설명합니다[^12].
- `foldersFromFilesStructure` 옵션으로 Git/FS의 폴더 구조를 Grafana 메뉴 폴더 구조로 자동 반영할 수 있다고 설명합니다[^12].

이런 동작은 업그레이드에서 두 군데가 위험합니다.

1) “프로비저닝을 믿고” UI에서 뭔가를 고친 뒤 잊는다.
- 업그레이드 때 프로비저닝 리로드/재적용이 일어나고, UI 수정이 사라진다.
- 결과적으로 업그레이드 직후에 “갑자기 바뀐” 것처럼 보이는 장애가 난다.

2) as-code 폴더/대시보드의 권한 기대치가 바뀐다.
- Grafana 문서는 as-code로 생성된 폴더는 “설정에 명시한 권한 + Admin 기본 권한”만 가진다고 명시합니다[^14].
- 즉, UI로 만든 폴더와 as-code 폴더의 기본 권한 형태가 다를 수 있고, 업그레이드 과정에서 폴더 생성 방식이 바뀌면 권한 형태도 같이 흔들릴 수 있습니다.

대규모 운영에서는 이걸 사람이 기억하는 순간부터 사고가 납니다. 그래서 검증 파이프라인에 “프로비저닝 계약 테스트”를 넣습니다.

### Admin API로 프로비저닝 리로드를 테스트 단계에 포함

Grafana는 Admin HTTP API에서 provisioning reload 엔드포인트를 제공합니다.

- `/api/admin/provisioning/dashboards/reload`
- `/api/admin/provisioning/datasources/reload`
- `/api/admin/provisioning/plugins/reload`
- `/api/admin/provisioning/access-control/reload`
- `/api/admin/provisioning/alerting/reload`

문서에는 “리로드는 새 엔티티가 DB에 저장될 때까지 반환하지 않는다”, “대시보드는 polling을 멈췄다가 재시작한다”는 동작이 명시되어 있습니다[^15].

이건 운영 자동화에서 바로 쓸 수 있는 도구입니다.

- 업그레이드 후보 버전 부팅 후,
- 리로드 API를 호출해서
- “프로비저닝이 끝난 상태”를 강제로 만든 다음
- 렌더링/권한 검증을 돌립니다.

아래는 compose 환경에서 두 Grafana에 대해 리로드를 호출하는 예시입니다.

```bash
# baseline
curl -u admin:admin -X POST http://localhost:3001/api/admin/provisioning/datasources/reload
curl -u admin:admin -X POST http://localhost:3001/api/admin/provisioning/dashboards/reload

# candidate
curl -u admin:admin -X POST http://localhost:3002/api/admin/provisioning/datasources/reload
curl -u admin:admin -X POST http://localhost:3002/api/admin/provisioning/dashboards/reload
```

여기서 포인트는 “리로드가 성공했는데도 결과가 달라지는가”입니다. 달라지면 업그레이드 리스크가 맞고, 그걸 사람이 아니라 파이프라인이 잡아야 합니다.

### 폴더/대시보드 권한: highest permission과 상속을 전제로 계약 테스트를 만든다

Grafana 문서는 대시보드/폴더 권한을 설정할 때 “사용자가 가진 조직 role, 폴더 permissions, 대시보드 permissions를 함께 고려해야 한다”고 명시합니다. 또한 Grafana는 접근 권한을 평가할 때 “해당 리소스에 대해 사용자가 가진 최고 권한(highest permission)을 적용한다”고 설명합니다[^16].

이 문장 때문에 운영에서 흔히 생기는 사고는 아래입니다.

- 폴더에서 Viewer로 낮춰놨는데, 조직 role이 Editor라서 편집이 된다.
- “폴더에서 막아놨다”는 착각이 생긴다.

그래서 권한 검증은 단순히 “설정 파일이 맞나?”가 아니라, **실제 사용자의 관점에서 접근이 차단/허용되는지**로 검증해야 합니다. 이때 RBAC를 쓰는 조직(Enterprise/Cloud)이라면 action/scope까지 포함해서 점검해야 하고, Grafana 문서는 action/scope 카탈로그를 제공합니다[^17].

내가 권한 검증을 자동화할 때의 결론은 간단합니다.

- API로 완벽히 검증하려고 하면 엔드포인트/모델 변화 비용이 듭니다.
- 반대로 UI e2e만 돌리면 깨지기 쉽습니다.

그래서 “딱 필요한 5~10개의 시나리오”를 정해 계약 테스트로 고정합니다.

- restricted 폴더에 대해 Viewer가 리스트/접근이 안 된다
- Editor가 특정 폴더에서는 편집이 안 된다
- 공유 대시보드 pause 후, 공유 링크로 bootstrap 데이터를 더 이상 가져오지 못한다(CVE-2026-81841 회귀 방지)
- alert rule list가 읽기 불가 폴더의 rule을 반환하지 않는다(CVE-2026-13719 회귀 방지)

이 중 마지막 두 개는 13.1.7 보안 패치의 핵심 리그레션 포인트라서, “이번 패치에 맞춰 자동화해야 하는 이유”를 직접 제공합니다[^4][^5].

## 롤백 플랜: 컨테이너 롤백이 아니라 데이터 롤백이다

Grafana 업그레이드에서 많은 팀이 착각하는 부분이 하나 있습니다.

- 애플리케이션은 stateless로 보이니, 문제가 있으면 이미지 태그만 내리면 된다.

Grafana는 그렇지 않습니다.

- 내부 DB(SQLite/MySQL/Postgres)에 스키마/데이터가 있고,
- 업그레이드 시 마이그레이션이 일어나며,
- 플러그인 데이터/캐시/프로비저닝 결과도 상태를 가집니다.

Grafana 문서가 업그레이드 가이드에서 “백업”을 강조하는 이유도 결국 여기 있습니다[^7][^2].

내가 운영 자동화를 설계할 때 롤백을 이렇게 정의합니다.

1) 롤백의 목표 상태는 “이전 버전 바이너리”가 아니라 “이전 버전 + 이전 DB 상태”다.

2) 롤백이 가능한 단위는 환경에 따라 갈린다.
- SQLite 단일 인스턴스면 파일 스냅샷이 유효하지만, HA나 외부 DB면 다른 전략이 필요합니다.
- RDS 같은 managed DB면 snapshot/restore 시간이 RTO에 들어갑니다.

3) 롤백 계획은 실행 가능한 형태(스크립트/런북)로 남겨야 한다.
- 사람이 ‘대충’ 기억하는 롤백은 실제 장애 때 실패합니다.

### 운영에서 쓸만한 롤백 패턴

- **Blue/Green + DB 분리**
  - 가장 깔끔하지만 비용이 큽니다.
  - Grafana는 쓰기 트래픽이 상대적으로 작다고 해도, 알림/annotation/audit이 엮이면 무시할 수 없습니다.

- **DB snapshot 기반 복구 + 빠른 재기동**
  - 패치 업그레이드에서 현실적인 선택입니다.
  - 업그레이드 직전에 snapshot, 실패 시 snapshot restore.

- **읽기 전용 검증 환경에서 충분히 굴린 뒤, prod에서는 canary로 최소 변경**
  - self-managed 문서가 dev/test에서 먼저 굴리라고 말하는 이유가 이 패턴을 염두에 둔 것으로 보입니다[^2].

여기서 중요한 건 “rollback 버튼”이 아니라 “rollback을 누르게 되는 조건”입니다. 나는 아래를 실패 조건으로 둡니다.

- 핵심 대시보드 렌더링 회귀 테스트 실패
- 권한 계약 테스트 실패(특히 shared dashboard/alert rule 관련)
- 플러그인 호환성 스캔 실패

그리고 이 실패 조건이 자동으로 판단되도록 만들어야, 패치 주기가 짧아져도 운영팀이 소진되지 않습니다.

## 패치 릴리스 주기에 맞춘 운영 자동화의 설계 결론

Grafana 13.1.7은 2026-09-29에 배포됐고[^1], 보안 관점에서 폴더 권한/공유 대시보드 토큰/프로비저닝 provenance 같은 운영 핵심 축을 직접 건드리는 CVE 수정이 포함됩니다[^4][^5][^6].

이런 패치가 잦은 제품에서 수동 업그레이드는 두 가지 이유로 실패합니다.

- 속도: 패치가 1~2주 단위로 나오면, 수동 검증이 끝나기도 전에 다음 패치가 나옵니다.
- 품질: 사람은 렌더링 미세 변화/권한 경계/프로비저닝 무결성을 안정적으로 반복 검증하지 못합니다.

그래서 운영팀이 해야 하는 건 “업그레이드 담당자”가 되는 게 아니라, 업그레이드가 일상적인 이벤트가 되도록 **검증의 형태를 자동화로 고정**하는 것입니다.

내 결론은 아래입니다.

- 패치 주기를 탓하기보다, 패치 주기만큼 빠르게 반복 가능한 검증 세트를 만든다.
- 검증은 플러그인/렌더링/권한/프로비저닝/롤백처럼 ‘사고가 났을 때 비용이 큰 축’에 집중한다.
- 렌더링은 이미지 기반으로, 권한은 시나리오 기반 계약 테스트로, 프로비저닝은 리로드 API를 중심으로 고정한다.
- 롤백은 바이너리 롤백이 아니라 데이터 롤백이라는 전제를 문서와 자동화에 반영한다.

## 참고 자료

- [Grafana 13.1.7 다운로드 페이지](https://grafana.com/grafana/download/13.1.7)
- [grafana/grafana Releases](https://github.com/grafana/grafana/releases?after=v5.0.3)
- [Strategies for upgrading your self-managed Grafana instance](https://grafana.com/docs/grafana/latest/upgrade-guide/when-to-upgrade/)
- [Upgrade Grafana](https://grafana.com/docs/grafana/latest/upgrade-guide/)
- [Admin HTTP API - Reload provisioning configurations](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/admin/?plcmt=products-nav)
- [Provision Grafana](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Folder access control](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/folder-access-control/)
- [Manage dashboard permissions](https://grafana.com/docs/grafana/latest/administration/user-management/manage-dashboard-permissions/)
- [Grafana RBAC permission actions and scopes](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/access-control/custom-role-actions-scopes/)
- [Set up image rendering](https://grafana.com/docs/grafana/latest/setup-grafana/image-rendering/)
- [Plugin metadata (plugin.json)](https://grafana.com/developers/plugin-tools/reference/plugin-json)
- [Plugin signatures](https://grafana.com/docs/grafana/latest/administration/plugin-management/plugin-sign/)
- [CVE-2026-13719 advisory](https://grafana.com/security/security-advisories/cve-2026-13719/)
- [CVE-2026-13720 advisory](https://grafana.com/security/security-advisories/cve-2026-13720/)
- [CVE-2026-81841 advisory](https://grafana.com/security/security-advisories/cve-2026-81841/)
- [Grafana Knowledge Graph 이후: 서비스 의존성 그래프를 운영에 쓰는 법](https://daewooki.github.io/posts/grafana-knowledge-graph-ops-patterns/)

[^1]: <https://grafana.com/grafana/download/13.1.7>
[^2]: <https://grafana.com/docs/grafana/latest/upgrade-guide/when-to-upgrade/>
[^3]: <https://github.com/grafana/grafana/releases?after=v5.0.3>
[^4]: <https://grafana.com/security/security-advisories/cve-2026-13719/>
[^5]: <https://grafana.com/security/security-advisories/cve-2026-81841/>
[^6]: <https://grafana.com/security/security-advisories/cve-2026-13720/>
[^7]: <https://grafana.com/docs/grafana/latest/upgrade-guide/>
[^8]: <https://grafana.com/developers/plugin-tools/reference/plugin-json>
[^9]: <https://grafana.com/docs/grafana/latest/administration/plugin-management/plugin-sign/>
[^10]: <https://grafana.com/docs/grafana/latest/administration/cli/>
[^11]: <https://grafana.com/docs/grafana/latest/setup-grafana/image-rendering/>
[^12]: <https://grafana.com/docs/grafana/latest/administration/provisioning/>
[^13]: <https://daewooki.github.io/posts/grafana-knowledge-graph-ops-patterns/>
[^14]: <https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/folder-access-control/>
[^15]: <https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/admin/?plcmt=products-nav>
[^16]: <https://grafana.com/docs/grafana/latest/administration/user-management/manage-dashboard-permissions/>
[^17]: <https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/access-control/custom-role-actions-scopes/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
