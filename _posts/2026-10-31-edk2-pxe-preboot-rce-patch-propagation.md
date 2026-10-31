---
title: "EDK II PXE pre-boot RCE: 패치 전파 지연을 운영으로 줄이는 법"
description: "EDK II PXE pre-boot RCE를 두고 업스트림 머지→벤더 릴리스→플릿 업데이트 지연을 줄이는 대응 흐름을 정리합니다."
date: 2026-10-31 13:33:56 +0900
categories: ["Hardware", "UEFI"]
tags: ["uefi", "edk2", "pxe", "firmware-security", "sbom", "incident-response"]
render_with_liquid: false
---

## GHSA-99cj-7hg9-mp4m이 의미하는 노출 범위

2026-10-22(UTC 기준 GitHub 표시) tianocore/edk2 GitHub Security Advisory로 **GHSA-99cj-7hg9-mp4m**이 공개됐습니다. 패키지는 NetworkPkg이고, “Affected versions”는 `EDK II master as of 2026-09-14`, “Patched versions”는 `Not patched currently`로 표기돼 있습니다. 이 표기 자체가 이 사건의 운영 난이도를 그대로 보여줍니다. 업스트림에서 코드 수정이 진행돼도, 안정 릴리스 태그나 벤더 펌웨어 릴리스로 내려오지 않으면 현장에서는 패치가 존재하지 않는 것과 비슷하게 작동합니다. [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m). 

취약점의 핵심 조건은 단순합니다.

- 시스템이 IPv4 또는 IPv6로 PXE boot를 수행하는 동안
- 공격자가 해당 클라이언트로 unicast ICMP error message를 전달할 수 있으면
- DXE phase 메모리 손상 및 OS 로드 이전 arbitrary code execution 가능

이건 OS 위의 EDR, kernel hardening, container isolation 같은 계층이 개입하기 전 단계입니다. advisory는 “Secure Boot 또는 measured boot가 OS 컴포넌트를 verify/measure 하기 전”이라는 표현을 명시합니다. [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m).

동시에, 노출이 “항상” 열려 있는 유형은 아닙니다. Red Hat은 이 취약점이 “네트워크 부팅 시퀀스 중 PXE driver가 네트워크 패킷을 처리할 때만” 노출된다고 정리합니다. 즉, VM/서버가 평상시 로컬 디스크로 부팅하고, PXE를 켜 두었더라도 실제로 네트워크 부팅 경로에 들어가지 않으면 트리거 창이 닫혀 있습니다. 다만 운영에서 중요한 건 “평상시”가 아니라 “예외”입니다. 장애 복구, 디스크 교체, 자동 프로비저닝, 원격 Boot override 같은 이벤트가 대개 PXE를 호출합니다. [Red Hat CVE-2026-97631](https://access.redhat.com/security/cve/cve-2026-97631).

## 어떤 코드가 깨졌는지: 504-byte buffer와 ICMP error 처리

advisory가 기술하는 결함은 `NetworkPkg/UefiPxeBcDxe`의 PXE Base Code driver가 ICMP error message를 수신·복사하는 로직입니다.

- driver는 네트워크 부팅 중 ICMP error message 수신을 위해 receive request를 열어 둡니다.
- 수신한 ICMP error message를 내부 private context 구조체의 `Mode.IcmpError`라는 고정 크기 504-byte 필드로 복사합니다.
- IPv4/IPv6 handler(`PxeBcIcmpErrorDpcHandle`, `PxeBcIcmp6ErrorDpcHandle`)에서 copy loop의 bounds handling이 잘못되어, 504 bytes를 넘는 메시지에서도 attacker-controlled bytes가 필드 바깥으로 써집니다.

핵심은 “복사 대상이 고정 크기 구조체 필드”라는 점입니다. pre-boot 네트워크 스택은 일반적인 user-space 네트워크 라이브러리처럼 성숙한 방어적 코딩, sanitizer, ASLR 기반 완화가 기대하기 어렵고, DXE phase에서의 메모리 손상은 곧바로 펌웨어 실행 흐름을 흔들어 버립니다. advisory는 (a) DoS/hang, (b) target firmware build를 아는 공격자라면 DXE phase에서 event dispatch까지 이어질 수 있다고 적습니다. [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m).

이 사건에서 운영 관점으로 특히 거슬리는 지점은 공격자 요구 조건입니다.

- “같은 L2” 같은 제약이 아니라, “클라이언트 IP로 unicast ICMP error message만 전달 가능하면 된다”
- “any network distance”라는 표현을 advisory가 직접 씁니다.

즉, PXE VLAN이 L3로 열려 있거나, 라우팅·ACL·방화벽 정책이 느슨한 환경이면 “프로비저닝 망”이 곧바로 원격 공격 표면이 됩니다. [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m).

업스트림 패치 내용을 보면 결함의 성격이 더 분명해집니다.

- PR #13302는 “ICMP buffer overflow”를 명시하고, IPv4/IPv6 handler에 boundary check 및 offset 계산 교정을 넣었다고 설명합니다. [edk2 PR #13302](https://github.com/tianocore/edk2/pull/13302).
- 커밋 `64c7b0c`의 메시지는 root cause로 “Incorrect buffer copy logic”를, resolution으로 “proper boundary checks” 및 “corrected buffer offset calculations”를 씁니다. [Commit 64c7b0c](https://github.com/tianocore/edk2/commit/64c7b0c).
- 후속 커밋 `c2dc75d` / `fa78907`은 ICMP error buffer를 `ZeroMem`으로 초기화해 stale bytes가 남지 않도록 합니다. 보안 취약점 수정은 단순히 overflow를 막는 것뿐 아니라, 이처럼 데이터 잔존·재사용 같은 부수 문제를 같이 정리하는 게 보통입니다. [Commit c2dc75d](https://github.com/tianocore/edk2/commit/c2dc75d), [Commit fa789071ff0b29f1e568bfe153ef7f3d76bd60e4](https://github.com/tianocore/edk2/commit/fa789071ff0b29f1e568bfe153ef7f3d76bd60e4).

이 취약점이 “오래된 코드”라는 점도 공개 이슈에서 확인됩니다. 2026-09-14 기준 master에 존재하며, 결함이 2008년부터 존재한다고 적혀 있습니다. 이런 유형은 특정 버전 범위를 찍기보다, 공급망 전체가 영향을 받을 확률이 높습니다. [edk2 Issue #13169](https://github.com/tianocore/edk2/issues/13169).

## 타임라인이 보여주는 현실: 머지는 10/15, advisory는 10/22, 그런데 “Not patched”

이번 건을 “패치 전파” 관점에서 보면 날짜들이 의미심장합니다.

- 2026-09-14: advisory가 기준으로 삼는 취약 상태의 master 시점. [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m).
- 2026-10-15: PR #13302가 master로 merge. merge 커밋은 `fa789071ff0b29f1e568bfe153ef7f3d76bd60e4`로 표시됩니다. [edk2 PR #13302](https://github.com/tianocore/edk2/pull/13302).
- 2026-10-22: GHSA 공개(critical, CVSS 9.5)인데 “Patched versions: Not patched currently”로 남아 있음. [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m).
- 2026-10-28: oss-security 메일링 리스트에도 advisory 내용이 전파됩니다. Debian tracker에서 아직 fix가 없다는 언급이 함께 붙습니다. [oss-security 포워딩](https://mail-archive.com/oss-security@lists.openwall.com/msg04892.html).
- 2026-10-31(KST): 지금 시점은 다수 벤더/다운스트림이 영향 평가를 시작하는 타이밍입니다.

여기서 “왜 merge가 됐는데 patched versions가 없나?”가 핵심 질문이 됩니다. 기술적으로는 master가 고쳐졌습니다. 하지만 운영에서 필요한 건 master가 아니라 다음입니다.

1) 제품이 실제로 사용하는 downstream codebase에 backport가 되었는지
2) 그 codebase로 빌드된 펌웨어/OVMF/BIOS 이미지가 릴리스되었는지
3) 그 릴리스를 고객 플릿이 실제로 올렸는지

UEFI 공급망은 이 전파 단계가 길어질 수밖에 없는 구조를 어느 정도 공식 문서에서도 인정합니다. UEFI 생태계에서 패치가 SiP/IFV/OEM을 거치며 유기적으로 늦어지고, OSS(TianoCore EDK2) 입력이 하위 공급망의 안정 태그를 기준으로 소비된다는 흐름이 정리돼 있습니다. 이 구조에서는 upstream merge가 “시작 신호”일 뿐 “종결 신호”가 아닙니다. [Decoding UEFI Firmware 문서](https://uefi.org/sites/default/files/resources/Decoding%20UEFI%20Firmware-Aug24-2023-Final_v2_0.pdf).

이 지연은 소프트웨어 팀에게는 익숙하지만, 펌웨어에서는 비용이 더 큽니다.

- 릴리스 주기가 길고(분기 단위가 흔함)
- 업데이트가 리부트를 요구하며
- 업데이트 실패 시 물리 작업(현장 방문)로 이어질 수 있고
- 고객 내부 change window, 검증 절차가 더 길다

그래서 이번 건의 정답은 “PR 링크 공유”가 아니라, 이 지연을 전제로 한 대응 흐름을 운영에 박아 넣는 쪽입니다.

## 영향 범위를 먼저 자르는 질문: 우리 환경에서 PXE가 언제 켜지나

이번 건은 “전사 모든 서버가 바로 RCE” 같은 형태로 단정하면 운영이 망가집니다. 대신, 시스템 단위로 노출 조건을 체크해 우선순위를 세우는 편이 빠릅니다.

내가 실무에서 PXE/UEFI 취약점을 다룰 때 가장 먼저 묻는 질문은 두 가지입니다.

1) 이 서버/VM은 정상 상태에서 네트워크 부팅을 실제로 하도록 설계됐나
2) 예외 상태에서 네트워크 부팅으로 떨어질 수 있나

두 번째 질문이 더 중요합니다. “평소에 안 씀”은 취약점의 완화가 아니라, 운 좋게 트리거 윈도우에 안 들어간다는 의미에 가깝습니다.

대표적으로 이런 케이스에서 PXE가 열립니다.

- 베어메탈 자동 프로비저닝(재설치, 스케일 아웃)
- 디스크 장애 후 교체 및 OS 재설치
- OS가 부팅 실패해서 firmware가 다음 부팅 옵션(네트워크)으로 넘어감
- BMC에서 원격으로 one-time PXE boot를 걸어 둠
- 보안팀/운영팀이 “긴급 복구 이미지”를 네트워크로 부팅시키는 런북을 이미 가지고 있음

따라서 대응도 두 갈래로 나눕니다.

- “PXE를 써야 하는 시스템”: PXE가 열리는 네트워크 경계를 좁히고, 신뢰된 provisioning path만 남깁니다.
- “PXE를 쓰지 않는 시스템”: firmware에서 network boot 자체를 꺼 버립니다.

이 구분을 빠르게 만들려면 자산 인벤토리에서 다음 필드가 필요합니다.

- 하드웨어 모델/세대(서버 SKU)
- BIOS/UEFI 버전과 릴리스 날짜
- 현재 boot order
- network boot 관련 설정(UEFI network stack, PXE enable, IPv4/IPv6 PXE enable)

문제는 대부분의 조직이 “OS 인벤토리”는 있어도 “firmware 설정 인벤토리”는 빈약하다는 점입니다.

## 펌웨어 버전 식별과 SBOM: 안 되는 이유부터 인정하고 시작하기

**업스트림 패치가 있어도 펌웨어는 안 고쳐진다**는 말은 감상문이 아니라, 식별 불가능성에서 출발합니다.

- 서버 BIOS 릴리스 노트는 “업스트림 커밋 ID”를 거의 공개하지 않습니다.
- 같은 BIOS 버전 문자열이라도 지역/옵션/마이크로코드 번들링으로 내부 구성물이 다를 수 있습니다.
- CVE 스캐너는 OS 패키지처럼 `edk2==x.y`를 읽을 방법이 없습니다.

그래서 SBOM을 “문서”가 아니라 “증거 체인”으로 취급해야 합니다.

### 1) 먼저 수집할 수 있는 것: SMBIOS/DMI 기반 버전 증거

Linux라면 다음 정도는 대부분 수집 가능합니다.

```bash
sudo dmidecode -t system -t baseboard -t bios

# 또는 권한이 제한된 환경에서는
cat /sys/class/dmi/id/sys_vendor
cat /sys/class/dmi/id/product_name
cat /sys/class/dmi/id/bios_version
cat /sys/class/dmi/id/bios_date
```

Windows는 PowerShell로 비슷하게 뽑습니다.

```powershell
Get-CimInstance Win32_ComputerSystemProduct | Select-Object Vendor, Name, Version
Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate
```

이 정보는 취약점의 “직접 판별”에는 부족하지만, 벤더 커뮤니케이션에서 필수입니다. 문의할 때 “모델 + BIOS 버전 + 릴리스 날짜”가 있어야 벤더 내부에서 추적이 가능합니다.

### 2) 업데이트 경로가 있는 곳: LVFS/fwupd

클라이언트/일부 서버는 LVFS/fwupd 경로가 열려 있기도 합니다. 다만 데이터센터 서버 플릿 전체가 fwupd로 관리되는 경우는 흔치 않았습니다. 그럼에도 fwupd를 쓰는 환경이라면, 장점이 큽니다.

- “현재 펌웨어 버전”과 “업데이트 가능한 버전”의 기계 판별
- 배포 자동화(capsule update)

이번 글은 특정 벤더의 fwupd 지원 여부를 단정하지 않습니다. 중요한 건 fwupd든 벤더 전용 도구든 “펌웨어 업데이트를 자동화할 레일이 있는지”를 먼저 점검하는 것입니다.

### 3) 진짜 SBOM이 필요해지는 지점: EDK2 구성요소 단위의 확인

CVE-2026-97631은 `NetworkPkg/UefiPxeBcDxe`에 걸립니다. [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m).

하지만 제품 SBOM이 없으면, 다음을 확인할 길이 없습니다.

- 해당 BIOS가 EDK2 기반인지
- EDK2 기반이라면 NetworkPkg를 포함했는지
- 포함했다면 취약한 구현인지(2026-09-14 기준 master와 동일 계열인지)
- PR #13302의 변경이 backport 되었는지

여기서 현실적인 접근은 “SBOM을 당장 받겠다”가 아니라, “패치 포함 여부를 증명 가능한 형태로 받겠다”입니다.

- PR #13302 기준으로는 merge가 2026-10-15에 이루어졌습니다. [edk2 PR #13302](https://github.com/tianocore/edk2/pull/13302).
- 해당 PR에 포함된 변경을 식별할 수 있는 커밋으로는 `560ed9b5b146ed622d7eb7c40254a9099bd65b84`(핵심 수정), `fa789071ff0b29f1e568bfe153ef7f3d76bd60e4`(ZeroMem), `14cdbb86a1a4f9bcce0d6cb78b04af58f226cf48`(테스트 추가) 등이 공개돼 있습니다. [Commit 560ed9b5b146ed622d7eb7c40254a9099bd65b84](https://github.com/tianocore/edk2/commit/560ed9b5b146ed622d7eb7c40254a9099bd65b84), [Commit fa789071ff0b29f1e568bfe153ef7f3d76bd60e4](https://github.com/tianocore/edk2/commit/fa789071ff0b29f1e568bfe153ef7f3d76bd60e4), [Commit 14cdbb86a1a4f9bcce0d6cb78b04af58f226cf48](https://github.com/tianocore/edk2/commit/14cdbb86a1a4f9bcce0d6cb78b04af58f226cf48).

이 커밋들을 “고객이 직접 펌웨어에서 찾아라”는 건 불가능에 가깝습니다. 대신 벤더로부터 “이 BIOS 빌드는 PR #13302의 변경을 포함한다”는 확인을 문서(PSIRT advisory, 릴리스 노트, 서포트 케이스 답변)로 받아야 합니다.

여기서 도움 되는 흐름 중 하나가 연구 커뮤니티에서도 제안됩니다. downstream 리포지토리들에 upstream 패치가 전파됐는지 근거 기반으로 판별하는 도구(SPIDER4TianoCore) 같은 시도가 나옵니다. 이게 바로 “패치 전파 증거”를 자동화하려는 방향입니다. [SPIDER4TianoCore 논문(arXiv)](https://arxiv.org/abs/2608.23755).

## 지금 당장 줄일 수 있는 위험: 네트워크 부팅을 ‘기능’이 아니라 ‘정책’으로 다루기

이번 취약점의 장점(?)은 노출 조건이 명확하다는 점입니다. “PXE boot 중에만” 열린다면, 대응도 PXE의 사용 범위와 네트워크 경계를 조이면 됩니다. [Red Hat CVE-2026-97631](https://access.redhat.com/security/cve/cve-2026-97631).

완화책은 크게 3단계로 나눕니다.

### 1) PXE를 안 쓰는 서버: firmware에서 network boot를 끄기

이게 가장 비용 대비 효과가 좋습니다.

- boot order에서 UEFI IPv4/IPv6 PXE 항목 제거
- one-time PXE boot 기능(원격 Boot override)이 있다면 권한/워크플로우를 잠그기
- “디스크 부팅 실패 시 네트워크로 fallback” 같은 동작이 있으면 끄기

실제 적용은 벤더마다 설정 항목이 다릅니다. 중요한 건 “수동으로 BIOS 들어가서 끄자”가 아니라, 플릿 단위 정책으로 내리는 것입니다.

가장 흔한 구현 레일은 Redfish입니다. 표준화가 완벽하진 않지만, 적어도 다음 정도는 공통으로 접근 가능합니다.

- 현재 BIOS/Boot 설정 조회
- 변경 요청을 job/commit로 예약
- 다음 리부트에서 적용

아래는 “일단 읽어오는 것”부터 자동화하는 예시입니다.

#### Redfish BIOS 인벤토리 수집 스크립트(실행 가능)

의존성은 Python과 `requests`만 둡니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
```

`targets.json` 예시:

```json
[
  {
    "name": "rack1-node01",
    "base_url": "https://10.0.10.11",
    "username": "REDFISH_USER",
    "password": "REDFISH_PASS"
  },
  {
    "name": "rack1-node02",
    "base_url": "https://10.0.10.12",
    "username": "REDFISH_USER",
    "password": "REDFISH_PASS"
  }
]
```

`redfish_bios_inventory.py`:

```python
#!/usr/bin/env python3
import csv
import json
import sys
import urllib.parse
import requests

requests.packages.urllib3.disable_warnings()  # self-signed BMC cert가 흔해서 경고만 제거

def get_json(session: requests.Session, url: str) -> dict:
    r = session.get(url, verify=False, timeout=15)
    r.raise_for_status()
    return r.json()

def first_system_id(service_root: dict) -> str:
    systems = service_root.get("Systems", {})
    odata_id = systems.get("@odata.id")
    if not odata_id:
        raise RuntimeError("No Systems collection")
    return odata_id

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} targets.json", file=sys.stderr)
        sys.exit(2)

    targets = json.load(open(sys.argv[1], "r", encoding="utf-8"))

    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "name",
            "system_id",
            "manufacturer",
            "model",
            "bios_version",
            "boot_source_override_enabled",
            "boot_source_override_target",
            "uefi_target_boot_source_override",
        ],
    )
    writer.writeheader()

    for t in targets:
        base = t["base_url"].rstrip("/")
        s = requests.Session()
        s.auth = (t["username"], t["password"])
        s.headers.update({"Accept": "application/json"})

        root = get_json(s, base + "/redfish/v1/")
        systems_coll = get_json(s, base + first_system_id(root))

        members = systems_coll.get("Members", [])
        if not members:
            raise RuntimeError(f"{t['name']}: no Systems members")

        sys_odata = members[0].get("@odata.id")
        system = get_json(s, base + sys_odata)

        bios = system.get("Bios", {})
        bios_odata = bios.get("@odata.id")
        bios_data = get_json(s, base + bios_odata) if bios_odata else {}

        boot = system.get("Boot", {})

        writer.writerow(
            {
                "name": t["name"],
                "system_id": sys_odata,
                "manufacturer": system.get("Manufacturer"),
                "model": system.get("Model"),
                "bios_version": bios_data.get("Version"),
                "boot_source_override_enabled": boot.get("BootSourceOverrideEnabled"),
                "boot_source_override_target": boot.get("BootSourceOverrideTarget"),
                "uefi_target_boot_source_override": boot.get("UefiTargetBootSourceOverride"),
            }
        )

if __name__ == "__main__":
    main()
```

실행:

```bash
python redfish_bios_inventory.py targets.json > bios_inventory.csv
head -n 5 bios_inventory.csv
```

예상 출력 형태:

```text
name,system_id,manufacturer,model,bios_version,boot_source_override_enabled,boot_source_override_target,uefi_target_boot_source_override
rack1-node01,/redfish/v1/Systems/System.Embedded.1,Dell Inc.,PowerEdge R750,1.18.2,Disabled,None,
```

이 CSV만으로 취약 여부를 판정하진 못합니다. 대신 다음 작업이 빨라집니다.

- “PXE를 안 쓰는 시스템인데 Boot override가 열려 있네?” 같은 구성이 보입니다.
- 벤더 티켓에 넣을 식별자(모델/BIOS 버전)를 바로 뽑습니다.

### 2) PXE를 쓰는 서버: PXE 네트워크를 격리하고, ICMP error를 ‘필요 최소’로 제한

advisory가 말하는 공격 트리거는 “ICMP error message”입니다. PXE 자체가 ICMP에 본질적으로 의존하는 프로토콜은 아닙니다. DHCP/TFTP/HTTPBoot를 위해 ICMP error가 꼭 필요하다고 보기 어렵습니다(특히 provisioning VLAN 내부에서는). 따라서 네트워크 장비/방화벽에서 다음을 목표로 정책을 짭니다.

- provisioning VLAN으로 들어오는 ICMP/ICMPv6 error를 드롭
- provisioning VLAN은 외부 라우팅을 최소화(가능하면 L2 only)
- PXE 서버/infra로 들어오는 트래픽만 allowlist

현장에서 즉시 적용 가능한 레일 중 하나는 “PXE VLAN의 default gateway”나 “ToR 앞단 방화벽”에 정책을 박는 것입니다.

예를 들어 Linux 기반 라우터/방화벽에서 nftables로 ICMP error를 드롭하는 형태는 이런 식입니다(정교화는 환경별로 다릅니다).

```bash
# 예시: provisioning VLAN(10.50.0.0/16)으로 향하는 ICMP/ICMPv6 error를 드롭
sudo nft add table inet pxe_guard
sudo nft 'add chain inet pxe_guard forward { type filter hook forward priority 0; policy accept; }'

# ICMPv4 error types: destination-unreachable(3), time-exceeded(11), parameter-problem(12), redirect(5)
sudo nft add rule inet pxe_guard forward ip daddr 10.50.0.0/16 icmp type { destination-unreachable, time-exceeded, parameter-problem, redirect } drop

# ICMPv6 error types: destination-unreachable(1), packet-too-big(2), time-exceeded(3), parameter-problem(4)
sudo nft add rule inet pxe_guard forward ip6 daddr fd50::/16 icmpv6 type { destination-unreachable, packet-too-big, time-exceeded, parameter-problem } drop

sudo nft list ruleset | sed -n '1,120p'
```

이 완화책은 트레이드오프가 있습니다.

- PMTUD 같은 동작이 깨질 수 있습니다.
- provisioning VLAN을 통해 다른 트래픽도 같이 흘리고 있으면 영향 범위가 커집니다.

그래서 나는 “PXE는 PXE만 하는 망”으로 분리하고, 그 망에서만 이런 차단을 넣는 쪽을 선호합니다. PXE가 필요한 시스템은 원래도 “신뢰된 부팅 경로”를 갖춰야 하고, 그 경로가 네트워크로 열려 있으면 그 자체가 공격 표면입니다.

### 3) Secure Boot가 켜져 있어도 방심하지 말아야 하는 이유

이번 advisory가 직접 언급하듯, 공격은 Secure Boot/Measured Boot의 OS component 검증/측정 이전에 수행될 수 있습니다. 즉 Secure Boot가 켜져 있다는 사실은 이번 취약점의 직접 완화책이 아닙니다. [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m).

이 지점은 과거 Secure Boot bypass류(CA/DBX/bootloader revocation) 사건과 달라 보이지만, 운영자의 체감은 비슷합니다. “부팅 체인의 신뢰를 만든다”와 “부팅 체인의 구현이 안전하다”는 별개의 문제입니다.

## 벤더 커뮤니케이션을 런북으로 만들기: 질문을 표준화해야 시간이 줄어든다

펌웨어 취약점 대응에서 시간은 기술보다 커뮤니케이션에서 녹습니다. 특히 아래 4개 주체가 섞입니다.

- upstream: tianocore/edk2
- IBV: AMI/Insyde/Phoenix 등(또는 Project Mu 기반)
- OEM: Dell/HPE/Lenovo/Supermicro 등
- 고객(우리): 최종 플릿 운영자

이 구조는 “누가 내 질문에 답할 수 있는가” 자체가 모호합니다. 그래서 질문 세트를 표준화해, 어느 벤더에게 보내도 의미가 통하게 만들어야 합니다.

내가 이번 건(CVE-2026-97631 / GHSA-99cj-7hg9-mp4m)에서 실제로 던질 질문 템플릿은 다음과 같습니다.

### (A) 영향 확인 질문

- 귀사 제품의 UEFI/BIOS가 EDK II 기반이며 `NetworkPkg/UefiPxeBcDxe` PXE Base Code driver를 포함합니까?
- 기본 설정 또는 특정 설정에서 IPv4/IPv6 PXE boot가 enabled 상태입니까?
- “로컬 디스크 부팅 실패 시 네트워크 부팅으로 fallback”하는 동작이 있습니까?

근거 링크는 벤더가 스스로 내부 티켓을 만들 수 있도록 같이 붙입니다.

- [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m)
- [Red Hat CVE-2026-97631](https://access.redhat.com/security/cve/cve-2026-97631)

### (B) 패치 포함 여부 질문(증거 기반)

- 귀사의 수정/완화는 PR #13302에 해당하는 변경을 포함합니까?
- 포함한다면, 어떤 펌웨어 릴리스(버전 문자열)부터 포함됩니까?
- backport라면, PR #13302의 핵심 커밋(`560ed9b...`, `fa78907...`)과 기능적으로 동등하다는 증거를 제공할 수 있습니까?

근거:

- PR이 2026-10-15에 master에 merge 되었다는 사실은 고객이 확인 가능합니다. [edk2 PR #13302](https://github.com/tianocore/edk2/pull/13302).
- 커밋 메시지에 root cause와 resolution이 적혀 있다는 것도 확인 가능합니다. [Commit 64c7b0c](https://github.com/tianocore/edk2/commit/64c7b0c).

### (C) 완화 옵션 질문(패치 전까지)

- 펌웨어 설정에서 PXE를 비활성화하는 정책적 권고가 있습니까?
- 원격 관리(BMC)에서 one-time PXE boot를 제한하는 권고가 있습니까?
- 네트워크 측면(ACL/segmentation)에서 권고하는 완화가 있습니까?

여기서 중요한 건, 벤더의 답변이 “업데이트 하세요”로 끝나면 안 된다는 점입니다. advisory가 “Patched versions: Not patched currently”인 상황에서는 “업데이트 할 게 없는데요”가 되기 때문입니다. [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m).

### (D) ETA 질문(가장 민감하지만 가장 필요)

- (1) IBV 코드 수정 수령 시점
- (2) OEM 펌웨어 릴리스 ETA
- (3) 고객 배포 권고 방식(긴급/정규)

이 ETA를 받아내지 못하면, 고객은 “PXE를 계속 끌 것인지”를 결정하기 어렵습니다. PXE는 프로비저닝/복구에 필요할 수 있어서, 완전 비활성화는 운영 리스크가 됩니다.

내 경우, 네트워크/부팅 취약점 런북을 만들 때는 과거에 작성했던 RCE 대응 런북들과 구조를 맞춥니다. 기술은 달라도 운영은 비슷하게 굴러갑니다. 예를 들어 네트워크 장비 RCE 패치 런북을 작성할 때도(패치 확인 → 릴리스 수집 → 배포 계획 → 롤백) 흐름은 동일했습니다. [Nexus 9000 Silicon One RCE 대응: 패치 런북](https://daewooki.github.io/posts/nexus9000-siliconone-rce-patch-runbook/).

## 다운스트림/고객 배포 지연을 줄이는 운영 체크리스트

여기부터는 “당장 우리가 내부적으로 줄일 수 있는 지연”에 집중합니다.

### 1) 자산 그룹핑: “모델+BIOS 버전”으로 묶고, 우선순위를 매긴다

우선순위는 보통 이렇게 잡힙니다.

- Tier 0: 자동 프로비저닝/복구에 PXE를 상시 사용하는 베어메탈 풀
- Tier 1: 평상시는 로컬 부팅이지만, 디스크 장애 시 PXE 복구 경로가 있는 장비
- Tier 2: PXE를 쓰지 않고, PXE가 꺼져야 정상인 장비(가장 빨리 risk 제거 가능)

Tier 2는 “기능 제거”로 바로 위험을 닫을 수 있어 성과가 빨리 나옵니다.

### 2) PXE 환경을 ‘신뢰된 설치 파이프라인’으로 재정의한다

PXE 환경이 외부에서 접근 가능한 일반 네트워크처럼 굴면, 그 순간부터는 firmware 취약점이 아니라 “설치 파이프라인 전체가 공격 표면”이 됩니다.

- PXE DHCP/TFTP/HTTPBoot 서버를 별도 VLAN에 두고
- 라우팅을 최소화하고
- 접근을 allowlist로 제한하고
- provisioning 때만 일시적으로 열거나, 최소한 provisioning 대상만 들어오게 한다

이 접근은 이번 취약점뿐 아니라, PXE/부팅 체인에 반복적으로 등장하는 문제(예: provisioning path hijack)를 같이 줄입니다.

### 3) “패치가 나왔을 때”를 미리 준비한다

펌웨어 업데이트는 OS 패치처럼 “나오면 바로 적용”이 잘 안 됩니다.

- 리부트가 필요합니다.
- firmware update 자체가 실패할 수 있습니다.
- fleet에 따라 maintenance window가 다릅니다.

그래서 준비는 반대로 합니다.

- 적용 대상 리스트(모델/BIOS 버전)를 먼저 고정
- 업데이트 레일(수동/자동, iDRAC/iLO/XClarity/현장)을 먼저 고정
- 롤백 가능성(이전 BIOS로 downgrade 가능한지)을 먼저 확인

이 과정이 되어 있어야, 벤더가 “fixed BIOS 릴리스”를 내는 날에 지연이 줄어듭니다.

## 가상화(OVMF/edk2 패키지)는 다른 게임: 우리가 직접 당겨올 수 있는 구간

이번 건은 베어메탈 펌웨어가 핵심이지만, CVE-2026-97631은 edk2가 가상화 펌웨어(OVMF)에도 쓰인다는 점에서 VM 환경에도 의미가 있습니다. Debian security tracker는 edk2가 여러 릴리스에서 vulnerable로 표기돼 있고, 당시 fix가 없다고 적습니다. [Debian edk2 소스 패키지 트래커](https://security-tracker.debian.org/tracker/source-package/edk2). 

Ubuntu의 CVE 페이지는 참고 커밋과 PR 링크를 같이 제공합니다. 즉, VM 환경에서는 “벤더 BIOS 기다리기”가 아니라 “패키지 업데이트 또는 직접 빌드”로 시간을 당길 수 있습니다. [Ubuntu CVE-2026-97631](https://ubuntu.com/security/CVE-2026-97631).

SUSE도 OVMF 패키지 단위로 affected 상태를 보여줍니다. [SUSE CVE-2026-97631](https://www.suse.com/security/cve/CVE-2026-97631.html).

여기서는 “PXE를 쓰는 VM”이 실제로 얼마나 있는지가 중요합니다. 클라우드 이미지 부팅만 한다면 영향이 낮고, 네트워크로 부팅하는 템플릿/프로비저닝이 있다면 우선순위가 올라갑니다.

### edk2에서 OVMF를 직접 빌드해 고정 버전으로 쓰는 절차(현실적인 시나리오)

환경: Ubuntu/Debian 계열 Linux, QEMU/KVM 호스트에서 OVMF를 직접 관리하는 상황.

#### 1) 빌드 의존성 설치

```bash
sudo apt-get update
sudo apt-get install -y git build-essential uuid-dev iasl nasm python3
```

#### 2) edk2 클론 및 특정 커밋 체크아웃

PR #13302가 merge된 커밋 `fa789071ff0b29f1e568bfe153ef7f3d76bd60e4`는 공개돼 있습니다. [Commit fa789071ff0b29f1e568bfe153ef7f3d76bd60e4](https://github.com/tianocore/edk2/commit/fa789071ff0b29f1e568bfe153ef7f3d76bd60e4).

```bash
git clone https://github.com/tianocore/edk2.git
cd edk2

git checkout fa789071ff0b29f1e568bfe153ef7f3d76bd60e4
```

#### 3) BaseTools 빌드

```bash
make -C BaseTools
```

#### 4) OvmfPkg 빌드

edk2 빌드는 환경 변수가 중요합니다.

```bash
export EDK_TOOLS_PATH="$PWD/BaseTools"
source edksetup.sh

# DEBUG 대신 RELEASE도 가능. 운영에서는 RELEASE를 쓰는 편이 자연스럽습니다.
build -a X64 -t GCC5 -p OvmfPkg/OvmfPkgX64.dsc -b RELEASE
```

#### 5) 결과물 확인

보통 결과물은 `Build/OvmfX64/RELEASE_GCC5/FV/` 아래에 생성됩니다.

```bash
ls -al Build/OvmfX64/RELEASE_GCC5/FV | head
```

이 단계가 가능한 조직이라면, 베어메탈 BIOS는 못 당겨도 가상화 펌웨어는 당길 수 있습니다. 특히 “프로비저닝을 VM으로 검증하고 베어메탈로 내리는” 파이프라인을 갖고 있다면, VM 쪽의 패치 적용은 베어메탈 패치 검증에도 도움이 됩니다.

다만 VM의 경우에도 “PXE를 진짜로 쓰는가”를 먼저 확인해야 합니다. Red Hat이 말하듯 네트워크 부팅 시에만 노출되는 유형이기 때문입니다. [Red Hat CVE-2026-97631](https://access.redhat.com/security/cve/cve-2026-97631).

## 공개된 PoC/하네스가 의미하는 것: 공격 가능성보다 ‘운영 시간축’이 바뀐다

2026-10-31 기준, GitHub에는 “로컬 랩 전용”을 명시한 headless harness 형태의 리포지토리도 올라와 있습니다. README는 로컬 QEMU/OVMF에서 PXE 진입을 자동화하고 ICMP error를 발생시키는 구조를 설명합니다. 동시에, 테스트한 OVMF에서는 DHCP Discover가 나가지 않아 트리거가 안 걸렸다고 한계를 명시합니다. 이게 중요합니다.

- 이 취약점은 “이론상 RCE”에서 멈추지 않고
- 재현·검증을 시도하는 코드가 공개되며
- 다운스트림/벤더가 “실제로 영향이 있나?”를 더 빨리 검증할 수 있는 상태가 됩니다.

즉, 공격자에게만 유리한 게 아니라, 방어자도 “패치 검증 속도”를 올릴 수 있는 구간이 열립니다. 다만 그만큼 조직 내부의 대응도 “느긋한 펌웨어 이슈”에서 “평범한 critical RCE” 쪽으로 시간축이 당겨집니다. [slabbdev/uefi-pxe-cve-2026-97631](https://github.com/slabbdev/uefi-pxe-cve-2026-97631).

내가 이 지점을 강조하는 이유는 단순합니다. “업스트림 fix는 이미 공개돼 있었다” 같은 서사보다, 현장에서 체감하는 변화는 이쪽이기 때문입니다.

- 패치가 느리게 내려와도
- 공격 표면(프로비저닝 네트워크)은 계속 열려 있고
- 재현 코드가 존재하면 내부 보안팀/레드팀/감사 요구가 빨라집니다.

따라서 “펌웨어 패치 기다리기”만으로는 대응이 되지 않습니다.

## 결론: 이번 건의 목표는 ‘패치 적용’이 아니라 ‘패치 전파 지연을 견딜 수 있는 구조’다

CVE-2026-97631 / GHSA-99cj-7hg9-mp4m은 기술적으로는 명확한 buffer overflow이고, PR #13302로 수정이 master에 merge됐습니다. [edk2 PR #13302](https://github.com/tianocore/edk2/pull/13302).

하지만 2026-10-31(KST) 시점의 운영 현실은 GHSA의 메타데이터 한 줄로 요약됩니다. “Patched versions: Not patched currently.” [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m).

이 문장은 단지 불편함이 아니라, 펌웨어 보안의 기본 전제를 강제합니다.

- upstream 머지와 제품 보안은 다른 사건이고
- 벤더 릴리스와 고객 플릿 업데이트는 또 다른 사건이며
- 그 사이 지연을 줄이려면 기술 패치 외에 자산 식별, 정책적 완화, 커뮤니케이션 표준화가 필요합니다.

PXE는 기능이 아니라 정책으로 다뤄야 하고, 그 정책이 구현돼 있어야만 “펌웨어는 느리게 고쳐진다”는 전제가 치명적인 운영 리스크로 변하지 않습니다.

## 참고 자료

- [GitHub Advisory GHSA-99cj-7hg9-mp4m](https://github.com/tianocore/edk2/security/advisories/GHSA-99cj-7hg9-mp4m)
- [edk2 PR #13302](https://github.com/tianocore/edk2/pull/13302)
- [Commit 64c7b0c](https://github.com/tianocore/edk2/commit/64c7b0c)
- [Commit 560ed9b5b146ed622d7eb7c40254a9099bd65b84](https://github.com/tianocore/edk2/commit/560ed9b5b146ed622d7eb7c40254a9099bd65b84)
- [Commit fa789071ff0b29f1e568bfe153ef7f3d76bd60e4](https://github.com/tianocore/edk2/commit/fa789071ff0b29f1e568bfe153ef7f3d76bd60e4)
- [Commit 14cdbb86a1a4f9bcce0d6cb78b04af58f226cf48](https://github.com/tianocore/edk2/commit/14cdbb86a1a4f9bcce0d6cb78b04af58f226cf48)
- [edk2 Issue #13169](https://github.com/tianocore/edk2/issues/13169)
- [Red Hat CVE-2026-97631](https://access.redhat.com/security/cve/cve-2026-97631)
- [Debian edk2 소스 패키지 트래커](https://security-tracker.debian.org/tracker/source-package/edk2)
- [Ubuntu CVE-2026-97631](https://ubuntu.com/security/CVE-2026-97631)
- [SUSE CVE-2026-97631](https://www.suse.com/security/cve/CVE-2026-97631.html)
- [oss-security 포워딩](https://mail-archive.com/oss-security@lists.openwall.com/msg04892.html)
- [slabbdev/uefi-pxe-cve-2026-97631](https://github.com/slabbdev/uefi-pxe-cve-2026-97631)
- [SPIDER4TianoCore 논문(arXiv)](https://arxiv.org/abs/2608.23755)
- [Decoding UEFI Firmware 문서](https://uefi.org/sites/default/files/resources/Decoding%20UEFI%20Firmware-Aug24-2023-Final_v2_0.pdf)
- [Nexus 9000 Silicon One RCE 대응: 패치 런북](https://daewooki.github.io/posts/nexus9000-siliconone-rce-patch-runbook/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
