---
title: "Splunk SOAR 59건 취약점 패치: 업그레이드 이벤트로 다루기"
description: "SVD-2026-1108(2026-11-18)로 공개된 Splunk SOAR 59건 취약점을 PR/UI 조건 기반으로 우선순위화하고 운영 영향·롤백까지 묶어 다룹니다."
date: 2026-11-22 11:34:29 +0900
categories: ["News", "Security"]
tags: ["splunk-soar", "svd-2026-1108", "vulnerability-management", "patch-runbook", "rce", "soar-operations"]
render_with_liquid: false
---

## 2026-11-18에 공개된 내용의 핵심은 “59건”과 “8.8.0”입니다
Splunk는 2026-11-18에 Splunk SOAR 다수 취약점을 묶은 보안 공지 **SVD-2026-1108**을 게시했습니다. 최고 CVSSv3.1은 9.9로 표시되어 있고, 해결책은 단일 문장으로 정리됩니다: Splunk SOAR를 8.8.0 이상으로 업그레이드하라는 것입니다.[^1]

이 공지가 운영 입장에서 까다로운 이유는, 한두 개 CVE를 “막고 끝내는” 성격이 아니라는 점입니다.

- 공지 제목 자체가 “Security Vulnerabilities in Splunk SOAR - November 2026”로 제품 단위 묶음입니다.[^1]
- CVE가 59개로 표시됩니다(공지는 CVE 목록을 59건으로 제시).[^2]
- “Mitigations and Workarounds: None”가 반복됩니다. 현실적으로는 업그레이드 외에 공식 우회로가 없다는 얘기입니다.[^1]

그중에서도 즉시 눈에 들어오는 건 두 축입니다.

1) App Wizard를 통한 RCE(CVE-2026-131253, CVSS 9.9)
- 인증된 사용자이면서 `Apps` edit, `Containers` edit, `Playbooks` execute 권한을 가진 역할이면, App Wizard로 SOAR를 구동하는 OS 사용자 권한으로 임의 코드 실행이 가능합니다.[^1]
- CVSS 벡터는 `AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H`로 표시됩니다. 즉 네트워크 경유, 낮은 권한, 사용자 상호작용 없음, 스코프 변경입니다.[^1]

2) Playbook/소스 저장소 경계를 건드리는 RCE(CVE-2026-131287, CVSS 9.6)
- `Playbooks` 권한(뷰/편집/실행/삭제)을 가진 사용자가, cross-repository playbook reference가 공격자가 통제하는 playbook 코드를 실행하도록 유도할 수 있다는 설명입니다. 삭제된 repository 이름 재사용 시 바인딩이 뒤틀릴 수 있는 구조적 문제로 읽힙니다.[^1]

오늘이 2026-11-22(KST)라면, 공지 게시(2026-11-18) 이후 4일이 지난 시점입니다. 이 정도 시차에서는 “긴급 패치할지 말지”가 아니라, 이미 업그레이드 작업이 진행 중이어야 운영 리스크가 줄어듭니다.[^1]

## SOAR 패치는 기능팀 패치가 아니라 ‘권한이 강한 허브’ 패치입니다
SOAR는 특성상 다음을 한 박스에 들고 있습니다.

- 각종 시스템으로 나가는 credential(EDR, firewall, IAM, ticketing, cloud 등)
- 사람이 하던 승인/변경 흐름(Approval, Workbook/Case)
- 자동화 실행 엔진(Playbook, Custom Function)
- 앱 설치/검증/업데이트 파이프라인(App Wizard, app validation, dependency 설치)

그래서 SOAR에서 “RCE 1건”은 단순히 웹앱 RCE가 아니라, (1) 내부망 lateral movement의 발판, (2) 보안 운영 프로세스 자체의 변조, (3) 연동 자격 증명 탈취로 이어지기 쉽습니다.

이번 공지에서 그 성격이 특히 강합니다.

- App Wizard RCE는 코드 생성 경로에서 user-supplied identifier 검증이 부족하다는 설명인데, 이 계열은 보통 “개발 편의 기능”이 공격 표면이 되는 전형적인 패턴입니다.[^1]
- app validation workflow가 untrusted code를 trusted environment로 격리하지 못해 임의 코드 실행이 가능하다는 항목(CVE-2026-131269)도 포함됩니다. 앱 설치/검증 루프 자체가 공격면이라는 뜻입니다.[^1]
- multi-tenant asset 경계가 무너져 credential/운영 데이터 노출이나 연동 리다이렉션이 가능하다는 항목(CVE-2026-131252)은, SOAR가 다중 조직/다중 팀을 한 인스턴스에서 운영할 때 폭발 반경이 크게 늘어납니다.[^1]

내가 이런 종류의 패치를 운영에서 다룰 때 기준으로 잡는 건, CVE 단위가 아니라 “업그레이드 이벤트” 단위입니다. 이 관점은 예전에 쓴 [Nexus 9000 Silicon One RCE 대응: 패치 런북](https://daewooki.github.io/posts/nexus9000-siliconone-rce-patch-runbook/)이나 [Chrome 152 제로데이 공지가 패치 프로세스를 강제하는 방식](https://daewooki.github.io/posts/chrome-152-zero-day-forces-patching-process/)에서 다룬 내용과 같은 계열인데, SOAR는 권한이 더 강해서 훨씬 보수적으로 잡는 편이 낫습니다.

## 우선순위화는 CVSS Score가 아니라 PR/UI 조건을 먼저 봅니다
59건을 전부 동일한 속도로 처리하려고 하면, 결국 아무 것도 제때 끝나지 않습니다. 나는 먼저 “공격자가 어떤 조건을 만족해야 하는지”를 PR/UI로 분해해서 1차 컷을 합니다.

- PR(Privileges Required): PR:N, PR:L, PR:H
- UI(User Interaction): UI:N, UI:R
- 그리고 SOAR에서는 S(Scope)도 실무적으로 중요합니다. S:C는 대체로 권한 경계를 넘어서는 가능성을 시사합니다.

이번 공지에서 App Wizard RCE는 `PR:L/UI:N/S:C`로 표기됩니다. 계정 하나만 잡히면 자동화로 바로 악용이 가능한 형태에 가깝습니다.[^1]

반대로, 같은 페이지에 있는 다른 예시(예: CVE-2026-131255)는 벡터가 `PR:N/UI:R/AC:H`로 표기되어, 사용자 상호작용과 높은 공격 복잡도 쪽에 더 무게가 실립니다. 이건 “기술적으로 심각해 보이지만 현실 악용 난이도는 다를 수 있다”는 힌트입니다.[^1]

여기서 흔히 하는 실수는 “UI:R이면 낮다”로 바로 결론내리는 것입니다. SOAR에서는 UI:R이더라도 클릭하는 주체가 SOC analyst, SOAR admin인 경우가 많고, 그 사람이 클릭하는 순간 결과가 production에 반영됩니다. UI:R을 낮추기보다 “누가 상호작용하는가”를 추가로 따져야 합니다.

내가 쓰는 우선순위 티어는 대략 이런 식입니다.

| Tier | 조건(우선) | SOAR에서의 의미 | 예시(이번 공지에서 확인되는 항목) |
|---|---|---|---|
| 0 | PR:N/UI:N 또는 PR:L/UI:N + S:C | 계정 한 개만 잡혀도 자동화/수평 확장 | App Wizard RCE `PR:L/UI:N/S:C`[^1] |
| 1 | 인증 필요(PR:L/UI:N) + credential/asset 경계 영향 | 연동 credential이 흐르는 경계가 깨짐 | cross-tenant asset 변경/삭제로 credential 노출/리다이렉션 가능[^1] |
| 2 | PR:L/UI:R 또는 PR:H/UI:N | 내부자/운영자 실수, 권한 남용과 결합 | 여러 REST API 권한 오류/정보 노출(다수 항목)[^1] |
| 3 | 기능적 오류/가용성(DoS 등) 중심 | 사건 대응 흐름만 흔들 수 있음 | Ingestion Status history 과다 저장으로 admin monitoring 가용성 저하[^1] |

이 티어링은 “패치 안 해도 된다”를 만들기 위한 게 아니라, 업그레이드 윈도우를 잡을 때 검증 순서를 정하기 위한 도구입니다.

## ‘Playbook/앱 설치 플로우’ 관점으로 영향도를 매핑해야 합니다
이번 묶음 패치에서 운영 영향은 크게 3개 축으로 갈립니다.

1) 앱 설치/생성/검증(App Wizard, app validation, dependency 설치)
2) 자동화 실행/참조(Playbook, cross-repository reference, callback)
3) 인증/권한 경계(SSO, tenant boundary, role assignment)

패치 적용 자체는 “8.8.0 이상 업그레이드”지만, 실제 장애는 대개 기능 변경/의존성 변경/권한 정책 변경에서 납니다. 그래서 나는 CVE 목록을 다음과 같이 운영 체크리스트로 번역합니다.

### 1) App Wizard와 app validation은 ‘개발 기능’이 아니라 ‘빌드 파이프라인’입니다
- App Wizard RCE는 App Wizard가 생성하는 connector code에 user-supplied identifier가 들어가는데, 검증 없이 코드에 포함된다는 설명입니다.[^1]
- Python dependencies를 통한 RCE(CVE-2026-131269)는 “설치된 앱을 validate할 때” untrusted code를 격리하지 못해 임의 코드 실행이 가능하다고 적혀 있습니다.[^1]

여기서 운영적으로 중요한 질문은 두 가지입니다.

- 우리 조직에서 App Wizard를 실제로 쓰는가?
- 앱 설치/업데이트/검증을 누가, 어느 권한으로, 어느 네트워크에서 수행하는가?

만약 App Wizard를 거의 쓰지 않더라도, “권한이 있는 사용자가 존재한다”는 사실만으로 공격 표면은 유지됩니다. 그리고 이 권한을 가진 계정이 피싱/세션 탈취/IdP 침해로 넘어가는 순간, SOAR host에서 코드 실행까지 이어질 수 있습니다.[^1]

내 경우에는 App Wizard와 앱 검증은 production SOAR에서 수행하지 않고, staging SOAR를 따로 두고 app artifact를 검증한 다음 production에 반영하는 구조로 정리했습니다. 이 결론은 [Forgejo 템플릿 리포지토리 RCE: 공격 경로와 방어선](https://daewooki.github.io/posts/forgejo-template-repo-rce-defense/)에서 다뤘던 “코드 생성/배포 경계에 RCE가 붙는다”는 패턴과 동일하게 가져가면 정리가 잘 됩니다.

### 2) Playbook reference와 소스 저장소는 ‘코드 공급망’으로 봐야 합니다
CVE-2026-131287 설명은 cross-repository playbook reference가 공격자 제어 playbook code를 실행할 수 있다는 취지입니다. 삭제된 repository 이름이 재사용될 때 바인딩이 바뀔 수 있다는 설명은, 운영에서 “repo name은 재사용하지 않는다” 같은 규약을 강제하지 않으면 사고가 날 수 있는 지점입니다.[^1]

이 계열은 패치 적용 전후로 다음을 확인하는 편이 안전합니다.

- SOAR에서 playbook을 소스 저장소와 연동하는지 여부
- repository 삭제/재생성, 이름 재사용의 운영 습관
- playbook 참조가 “이름”으로만 연결되는지, immutable identifier로 연결되는지

패치가 들어가면 동작이 “안전한 쪽으로” 바뀌겠지만, 그 과정에서 기존 참조가 깨지는 것도 운영 사고로 이어질 수 있습니다. 그래서 업그레이드 이벤트로 묶고, playbook 실행 경로를 테스트 케이스로 고정해 두는 쪽이 낫습니다.

### 3) SSO와 multi-IdP는 ‘침해된 IdP 운영자’까지 위협 모델에 넣어야 합니다
CVE-2026-131297은 SSO authentication bypass로 분류되어 있고, 설명이 꽤 구체적입니다.

- 2개 이상의 외부 identity provider가 설정되어 있고(trust domain이 다름)
- 한 IdP의 operator가 다른 IdP에 매핑된 기존 username으로 인증할 수 있으면
- 그 계정이 Administrator 역할일 때 SOAR 전체를 제어할 수 있다는 내용입니다.

원인은 “외부 사용자 계정을 provisioning한 IdP와 바인딩하지 않고 username만으로 인증한다”는 식으로 적혀 있습니다. 벡터는 `AV:N/AC:H/PR:N/UI:N`로 표시됩니다.[^1]

이건 전형적인 pre-auth RCE 같은 형태는 아니지만, 조직 구조에 따라 위험도가 급격히 바뀝니다.

- B2B, MSSP, 분리된 계열사 등으로 IdP가 여러 개 붙는 구조
- 외부 파트너가 특정 IdP 운영을 실질적으로 담당하는 구조

이 경우에는 “SOAR를 인터넷에 노출하지 않는다”만으로 해결이 안 됩니다. 내부 신뢰 경계를 어디까지로 볼지를 다시 그려야 합니다.

### 운영 영향도 매핑 템플릿
나는 59개 CVE를 전부 읽고 표로 옮기기보다, 제품 운영 구성요소를 먼저 정리한 뒤 “이 구성요소를 건드리는 CVE가 하나라도 있으면 해당 플로우를 테스트한다”로 단순화합니다.

| 플로우 | 실패 시 증상 | 이번 공지에서 근거가 되는 항목 예시 | 업그레이드 후 반드시 할 테스트 |
|---|---|---|---|
| App Wizard로 커넥터 생성 | 임의 코드 실행/connector 코드 오염 | App Wizard RCE[^1] | staging에서 App Wizard 생성/빌드/실행, 생성물 diff |
| 앱 검증(validate) | 임의 코드 실행/검증 과정에서 host 오염 | app validation 격리 실패로 RCE 가능[^1] | 앱 validate 수행 시 네트워크/파일 변경 모니터링 |
| Asset/tenant 관리 | credential 유출/연동 트래픽 리다이렉션 | cross-tenant asset 변경/삭제 가능[^1] | tenant별 asset CRUD, secret masking 확인 |
| Playbook repo/reference | 공격자 코드 실행/참조 깨짐 | cross-repo reference 바인딩 문제로 RCE[^1] | repo 삭제/재추가/이름 변경 시 참조 안정성 테스트 |
| SSO(multi-IdP) | 타 IdP operator가 username 충돌로 takeover | SSO auth bypass 설명 및 조건[^1] | IdP별 동일 username 케이스, group/role 매핑 테스트 |
| 진단 로그/번들 | password reset credential 노출 | Observer role이 diagnostic log bundle에서 credential 접근 가능[^1] | diag bundle 생성/보관/접근제어 점검 |

이 표를 먼저 만들면, 59건이든 590건이든 “테스트 대상”이 먼저 결정됩니다.

## 59건을 실제로 다루기 위한 자동화: 공지 HTML을 파싱해서 PR/UI로 정렬하기
Splunk 공지는 CVE별로 CVSS 벡터를 제공합니다. 이걸 사람이 손으로 옮기면 하루가 깨집니다. 나는 보통 “공지 페이지를 파싱해서 CSV로 떨군 다음, PR/UI로 필터링하고, 구성요소 키워드로 라벨링”합니다.

아래는 로컬 워크스테이션에서 바로 돌릴 수 있는 스크립트입니다(운영 서버가 아니라 분석용 PC에서 실행하는 전제입니다).

```bash
python -V
# Python 3.12+ 권장

python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install requests beautifulsoup4 pandas
```

```python
# file: soar_svd_2026_1108_triage.py
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup

ADVISORY_URL = "https://advisory.splunk.com/advisories/SVD-2026-1108"

def extract_vector_fields(vector: str) -> dict:
    # Example: CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H
    fields = {}
    for part in vector.split("/"):
        if ":" in part:
            # CVSS:3.1
            continue
        if ":" in part:
            continue
        if part.count(":") == 1:
            k, v = part.split(":", 1)
            fields[k] = v
    # If above didn't work due to split, parse with regex too
    for k in ["AV", "AC", "PR", "UI", "S", "C", "I", "A"]:
        m = re.search(rf"{k}:([A-Z])", vector)
        if m:
            fields[k] = m.group(1)
    return fields

def main():
    res = requests.get(ADVISORY_URL, timeout=20)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    # Strategy:
    # - Each CVE section contains text 'CVSSv3.1 Vector:' followed by the vector link text.
    # - We'll iterate headings that include 'CVE-' and scan forward for Score/Vector.

    rows = []

    # Headings look like: ### CVE-2026-131253: ...
    for h in soup.find_all(["h3"]):
        text = " ".join(h.get_text(" ", strip=True).split())
        if "CVE-" not in text:
            continue
        cve_match = re.search(r"(CVE-\d{4}-\d+)", text)
        if not cve_match:
            continue
        cve = cve_match.group(1)
        summary = re.sub(r"^.*?:\s*", "", text).strip()

        # Walk siblings until next h3, collect score/vector/severity if present
        score = None
        vector = None
        severity = None

        node = h
        while node is not None:
            node = node.find_next_sibling()
            if node is None:
                break
            if getattr(node, "name", None) == "h3":
                break
            t = " ".join(node.get_text(" ", strip=True).split())
            if t.startswith("CVSSv3.1 Score:"):
                # e.g. "CVSSv3.1 Score: 9.9, Critical"
                m = re.search(r"Score:\s*([0-9.]+),\s*(\w+)", t)
                if m:
                    score = float(m.group(1))
                    severity = m.group(2)
            if "CVSS:3.1/" in t:
                m = re.search(r"(CVSS:3\.1/[^\s]+)", t)
                if m:
                    vector = m.group(1)

        if vector:
            vf = extract_vector_fields(vector)
        else:
            vf = {}

        rows.append({
            "cve": cve,
            "summary": summary,
            "severity": severity,
            "score": score,
            "vector": vector,
            "PR": vf.get("PR"),
            "UI": vf.get("UI"),
            "S": vf.get("S"),
        })

    df = pd.DataFrame(rows)

    # Prioritize: PR asc (N < L < H), UI asc (N < R), Scope C first
    pr_order = {"N": 0, "L": 1, "H": 2}
    ui_order = {"N": 0, "R": 1}
    s_order = {"C": 0, "U": 1}

    df["pr_rank"] = df["PR"].map(pr_order).fillna(9).astype(int)
    df["ui_rank"] = df["UI"].map(ui_order).fillna(9).astype(int)
    df["s_rank"] = df["S"].map(s_order).fillna(9).astype(int)

    df = df.sort_values(["pr_rank", "ui_rank", "s_rank", "score"], ascending=[True, True, True, False])

    out_csv = "svd-2026-1108-triage.csv"
    df.to_csv(out_csv, index=False)

    print(f"wrote: {out_csv}")
    print(df[["cve", "severity", "score", "PR", "UI", "S", "summary"]].head(15).to_string(index=False))

if __name__ == "__main__":
    main()
```

```bash
python soar_svd_2026_1108_triage.py
# 예상 결과:
# - PR=L/UI=N/S=C 같은 항목이 상단에 몰림
# - severity/score와 별개로 '운영상 먼저 손대야 하는 흐름'이 드러남
```

이 방식의 장점은, 59건 전체를 “한 번에” 읽지 않아도 된다는 점입니다. PR/UI로 정렬한 뒤 상위 10~15개만 읽어도, 어떤 구성요소가 반복적으로 흔들리는지 감이 잡힙니다.

## 업그레이드 이벤트 설계: 백업·검증·롤백이 한 덩어리여야 합니다
Splunk가 제시하는 공식 해결책은 8.8.0 이상 업그레이드입니다.[^1]

여기서 운영이 망가지는 패턴은 거의 정해져 있습니다.

- 업그레이드를 “보안팀 작업”으로만 취급해서, Playbook/앱 운영자와 단절된 채로 진행
- 복구점(restore point)을 “백업 파일 하나”로만 생각하고, 실제 복구 리허설이 없음
- 업그레이드 직후에는 정상처럼 보이다가, 몇 시간~하루 뒤에 automation runtime migration 같은 비동기 작업이 돌면서 깨짐

Splunk 문서 자체도 업그레이드 전에 full backup을 만들라고 못 박고 있고, VM 단일 인스턴스면 snapshot도 언급합니다.[^3]

### On-premises: 백업은 ibackup 체인과 “복구 가능성”을 같이 봅니다
Splunk SOAR (On-premises) 문서에는 `ibackup` 기반 백업 절차가 안내되어 있습니다.

- 준비 단계에서 `/opt/phantom/bin/phenv ibackup --setup` 같은 커맨드가 등장합니다.[^4]
- full backup은 `phenv ibackup --backup --backup-type full`로 생성한다고 명시되어 있고, 산출물이 `/opt/phantom/data/backup/...tar`로 떨어지는 예시가 있습니다.[^4]
- 중요한 문장 하나: incremental 백업을 만들 때 SOAR를 offline으로 내릴 필요가 없다고 적혀 있습니다(운영 윈도우 설계에 도움이 됩니다).[^4]

내가 여기서 반드시 확인하는 건 두 가지입니다.

1) 백업 산출물이 “한 파일”로 존재하더라도, 실제 restore에 필요한 외부 의존성(PostgreSQL externalization, object storage, KMS 등)이 더 없는지
2) 클러스터 구성이면 “같은 노드에서 백업 커맨드를 쳐야 한다” 같은 제약이 있는지

이건 문서에 “clustered deployment에서는 모든 backup command를 동일 노드에서 수행” 같은 제약이 들어가는 형태라서, 런북에 박아두지 않으면 실수가 나옵니다.[^4]

#### (실행 예시) On-premises full backup
```bash
# SOAR 서버에 SSH
ssh <username>@<phantom_hostname>

# 보통 설치 경로가 /opt/phantom인 경우가 많음
cd /opt/phantom/bin

# (최초 1회) backup 준비
/opt/phantom/bin/phenv ibackup --setup

# full backup 생성
phenv ibackup --backup --backup-type full

# 산출물 확인
ls -al /opt/phantom/data/backup
```

### 업그레이드 전 사전점검: 디스크/경로/스케줄러가 사고를 만듭니다
Splunk 업그레이드 prerequisites 문서에 최소 조건이 구체적으로 들어가 있습니다.

- `/tmp`에 최소 5GB 여유 공간
- `<$PHANTOM_HOME>/data/`에 PostgreSQL 업그레이드를 감당할 수 있는 여유 공간
- `<$PHANTOM_HOME>`가 보통 `/opt/phantom`이라는 언급
- warm standby 사용 시 끄라고 안내
- scheduled backup(cron 등)을 업그레이드 중에는 꺼 두라고 안내

이 부분은 실제로 업그레이드 실패 원인의 대부분을 차지합니다.[^3]

### 업그레이드 이후의 지연 폭탄: Python 3.13 migration 타이밍
SOAR는 업그레이드 직후에 끝나지 않는 작업이 있습니다.

문서에 따르면 7.1.0 이후에는 업그레이드 후 24시간 내에 Playbooks/Custom Functions의 automation code를 Python 3.13으로 자동 마이그레이션하려고 시도하며, 업데이트 이후 대략 3:00 AM UTC에 별도 프로세스로 시작된다고 적혀 있습니다.[^3]

여기서 운영 함정은 “업그레이드 직후 테스트는 통과했는데, 다음날 새벽에 코드가 마이그레이션되면서 일부 자동화가 깨진다”입니다.

따라서 업그레이드 이벤트의 완료 조건은 “서비스가 떠 있다”가 아니라, 다음을 만족하는 쪽이 맞습니다.

- 주요 Playbook 실행이 정상
- Custom Function의 런타임 호환이 확인됨
- 마이그레이션이 돌 시간대(3:00 AM UTC)를 지나도 장애가 없었음[^3]

이걸 넣지 않으면, 업그레이드를 했는데도 장애 대응이 며칠 뒤로 미뤄지는 형태가 됩니다.

## 롤백과 격리: “업그레이드 실패”보다 “업그레이드 지연”이 더 비쌉니다
Splunk 공지는 mitigation이 없다고 반복합니다. 즉, 공식 입장은 업그레이드 외의 방어선을 제공하지 않는다는 쪽입니다.[^1]

그렇다고 운영에서 손 놓고 업그레이드만 기다리면, 실제로는 업그레이드 지연 기간이 공격 윈도우가 됩니다. 그래서 나는 업그레이드 전까지는 격리 전략을 같이 씁니다.

### 1) 네트워크 격리: SOAR 관리면은 “업무망”이 아니라 “관리망”으로
- SOAR UI/REST API 접근을 VPN 또는 admin subnet으로 한정
- IdP/SSO 콜백 endpoint가 불가피하게 열려야 하면, 그 외 경로는 막고 접근 로그를 남김
- App Wizard, 앱 설치/검증 같은 고위험 기능은 접근 가능한 사용자/네트워크를 더 좁힘

이건 제품별로 설정 방법이 달라 “Splunk가 이렇게 하라 했다”로 말할 수는 없지만, SOAR의 성격상 이 방향으로 가지 않으면 App Wizard 같은 기능성 RCE는 막기 어렵습니다.[^1]

### 2) RBAC 격리: PR:L을 “아무나 가진 PR:L”로 두지 않습니다
App Wizard RCE는 PR:L입니다. 문제는 SOAR에서 PR:L이 굉장히 넓게 분포하기 쉽다는 점입니다. `Apps` edit, `Containers` edit, `Playbooks` execute 같은 권한을 동시에 가진 역할을 최소화하고, 계정 수를 줄여야 합니다.[^1]

또, SSO bypass는 다중 IdP 환경에서 신뢰 경계가 흐려질 때 위험해집니다. 특히 username 기반으로 소유권을 검증하지 않는다는 설명이라, “동일 username이 다른 IdP에서 생성 가능한가”를 운영 규칙으로 막아야 합니다.[^1]

### 3) 롤백은 ‘복구 시간’까지 포함해야 합니다
Splunk 문서가 “full backup”과 VM snapshot을 함께 언급하는 이유는, 실제로는 rollback이 단순히 파일 되돌리기가 아니라 “서비스 복구 시간”의 문제이기 때문입니다.[^3]

내가 롤백을 설계할 때는 다음 두 줄이 핵심입니다.

- rollback 조건: 업그레이드 후 N시간 내에 특정 Playbook/앱 액션 성공률이 기준치 밑으로 떨어지면 롤백
- rollback 목표: RTO를 숫자로 박는다(예: 30분/1시간/2시간)

SOAR는 단순 웹앱이 아니라, 사건 대응 파이프라인 전체가 걸려 있어 RTO가 길어질수록 손실이 커집니다.

## 반론과 회의론: 8.8.0 업그레이드가 ‘단순 패치’가 아닐 수 있습니다
업그레이드 이벤트로 다루자고 하면 항상 나오는 반론이 있습니다.

### “RCE가 다 authenticated 기반이면 급하지 않다”
이번 공지의 핵심 RCE 중 하나(App Wizard)는 인증이 필요하지만 PR:L/UI:N이고 scope가 바뀝니다. 계정이 하나라도 넘어가면, SOAR host에서 코드 실행으로 이어질 수 있는 형태로 적혀 있습니다.[^1]

SOAR에서 authenticated는 방어선이 되기 어렵습니다. SOAR 계정은 보통 장기 세션/SSO/권한 집약이 결합되기 때문입니다.

### “업그레이드가 더 위험하다”
업그레이드가 위험한 건 사실입니다. 특히 SOAR는 Python 런타임 마이그레이션 같은 후속 작업이 있고, 그 타이밍이 문서에 명시되어 있습니다.[^3]

다만 위험의 종류가 다릅니다.

- 업그레이드 위험: 통제된 시간에 발생(maintenance window), 복구 플랜 가능
- 패치 지연 위험: 통제 불가, 침해 시 조사/복구 비용이 급격히 증가

내 경험상 SOAR류 제품은 “기능 장애 2시간”보다 “침해 조사 2주”가 훨씬 비쌉니다. 그래서 업그레이드 위험을 낮추는 쪽(테스트/백업/롤백)을 투자하는 게 낫습니다.

### “SOAR Cloud면 우리가 할 게 없다”
Splunk SOAR (Cloud)는 릴리스 노트에 8.8.0이 2026-10-21 릴리스로 표시됩니다. 즉, 수정이 이미 릴리스에 포함됐고, 공지는 2026-11-18에 나왔다는 시간차가 존재합니다.[^5]

Cloud 사용자는 직접 패치하기보다, (1) 우리 테넌트가 실제로 어느 빌드인지 확인하고, (2) 권한/RBAC/IdP 구성을 점검하고, (3) 앱 설치/검증/Playbook repo 같은 고위험 플로우 운영 규칙을 손보는 게 현실적인 대응이 됩니다.

## 앞으로 지켜볼 것: “악용 관측”보다 먼저 봐야 할 건 ‘운영자 행동’입니다
CyberStack 요약 페이지는 이 공지에 대해 “no exploitation stated”를 언급합니다. 이건 좋은 소식이지만, 결정을 바꿀 정도의 근거는 아닙니다.[^6]

내가 더 중요하게 보는 포인트는 다음입니다.

- App Wizard/앱 검증처럼 운영자가 자주 만지는 경로가 공격면으로 지목되었는가(이번은 그렇습니다).[^1]
- SSO처럼 조직 구조(다중 IdP)에 따라 갑자기 위험해지는가(이번은 그렇습니다).[^1]
- tenant/asset/approval/log bundle처럼 감사/추적을 약화시키는 항목이 포함되는가(이번은 그렇습니다).[^1]

악용 관측이 뜨면 이미 늦습니다. SOAR는 침해되면 “그날 대응”이 아니라 “다음 분기 감사”까지 흔들립니다.

## 결론: SVD-2026-1108은 ‘패치 적용’이 아니라 ‘SOAR 운영 모델 점검’ 트리거입니다
SVD-2026-1108은 업그레이드 한 번으로 59건을 닫는 형태입니다. 이때 중요한 건 “8.8.0 올렸다”가 아니라, 업그레이드 이벤트를 통해 운영 모델을 어디까지 재정렬할지입니다.[^1]

나는 이 공지를 다음 세 가지 신호로 해석했습니다.

- SOAR의 앱 생성/설치/검증은 사실상 코드 공급망이며, production에서 즉흥적으로 다루면 곧바로 RCE로 이어질 수 있습니다.[^1]
- Playbook reference와 repo 연동은 권한 경계로 취급해야 하고, 이름 재사용/삭제 같은 운영 습관이 보안 결함과 결합하면 치명적이 됩니다.[^1]
- SSO와 다중 IdP는 “조직 간 신뢰”가 깨졌을 때 제품이 어떻게 무너지는지 보여주는 사례입니다.[^1]

그래서 이 건은 취약점 1개를 패치하는 작업이 아니라, SOAR를 업그레이드하면서 권한 설계, 앱 설치 플로우, playbook 공급망, 롤백 체계를 같이 재점검하는 제품 단위 이벤트로 취급하는 게 맞다고 판단합니다.

## 참고 자료
- [Splunk 보안 공지 SVD-2026-1108](https://advisory.splunk.com/advisories/SVD-2026-1108)
- [Splunk SOAR (On-premises) 업그레이드 개요 및 prerequisites](https://help.splunk.com/en/splunk-soar/soar-on-premises/install-and-upgrade-soar-on-premises/8.8.0/upgrade-splunk-soar-on-premises/splunk-soar-on-premises-upgrade-overview-and-prerequisites)
- [Splunk SOAR (On-premises) 백업 절차: ibackup](https://help.splunk.com/en/splunk-soar/soar-on-premises/administer-soar-on-premises/8.8.0/backup-or-restore-your-splunk-soar-on-premises-instance/back-up-a-splunk-soar-on-premises-deployment)
- [Splunk SOAR (Cloud) 릴리스 노트: Fixed issues](https://help.splunk.com/en/splunk-soar/soar-cloud/release-notes/splunk-soar-cloud-release-notes/fixed-issues-for-splunk-soar-cloud)
- [CyberStack Vendor advisory watch(SVD-2026-1108 요약)](https://cyberstack.org/vendor-watch)
- [Splunk App for SOAR 릴리스 노트 8.8.0](https://help.splunk.com/en/splunk-soar/splunk-app-for-soar/splunk-app-for-soar-release-notes/8.8.0/splunk-app-for-soar-release-notes/welcome-to-splunk-app-for-soar)

[^1]: <https://advisory.splunk.com/advisories/SVD-2026-1108>
[^2]: <https://advisory.splunk.com/>
[^3]: <https://help.splunk.com/en/splunk-soar/soar-on-premises/install-and-upgrade-soar-on-premises/8.8.0/upgrade-splunk-soar-on-premises/splunk-soar-on-premises-upgrade-overview-and-prerequisites>
[^4]: <https://help.splunk.com/en/splunk-soar/soar-on-premises/administer-soar-on-premises/8.8.0/backup-or-restore-your-splunk-soar-on-premises-instance/back-up-a-splunk-soar-on-premises-deployment>
[^5]: <https://help.splunk.com/en/splunk-soar/soar-cloud/release-notes/splunk-soar-cloud-release-notes/fixed-issues-for-splunk-soar-cloud>
[^6]: <https://cyberstack.org/vendor-watch>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
