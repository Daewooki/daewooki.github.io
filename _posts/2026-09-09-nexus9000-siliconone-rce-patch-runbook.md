---
title: "Nexus 9000 Silicon One RCE 대응: 패치 런북"
description: "CVE-2026-20212 크리티컬 RCE를 계기로, Nexus 9000을 애플리케이션처럼 패치하는 운영 런북을 정리합니다."
date: 2026-09-09 09:43:50 +0900
categories: ["News", "Networking"]
tags: ["cisco", "nexus-9000", "nx-os", "cve-2026-20212", "patch-management", "runbook"]
render_with_liquid: false
---

## 무슨 일이 있었나: CVE-2026-20212의 기술적 성격

Cisco PSIRT는 2026-09-02 16:00 GMT(한국 시간 2026-09-03 01:00 KST)에 **Cisco Nexus 9000 Series Switches Silicon One Remote Code Execution Vulnerability**(Advisory ID: cisco-sa-n9k-s1-rce-EH8dEtr)를 게시했습니다.[^1]  
이 어드바이저리는 CVE-2026-20212로 추적되며 CVSS 9.8(AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H)로 분류됩니다.[^1]

요지는 단순합니다.

- Silicon One integration(문서 표현 그대로)에서, **기본 default L3 VRF에서 TCP 43210, 43211 포트가 접근 가능**한 상태로 노출됩니다.[^1]
- 해당 포트로 원격에서 crafted input을 보내면, 인증 없이 root privilege로 code execution이 가능하다고 적시합니다.[^1]
- “S1HAL process”가 크래시하면서 장비가 reload로 이어질 수 있다고 명시합니다. 즉 RCE가 안정적으로 안 되더라도, 원격 DoS로도 충분히 위험합니다.[^1]

영향 범위는 “Nexus 9000 전체”가 아니라 **Silicon One ASIC이 들어간 특정 PID**에 한정되어 있습니다. Cisco가 게시 시점에 Silicon One ASIC을 포함한다고 적어 둔 PID 목록은 다음과 같습니다.[^1]

- N9324C-SE1U
- N9348Y2C6D-SE1U
- N9364E-SG2-O
- N9364E-SG2-Q
- N9396T12C-SE1
- N9348Y12C-SE1
- N9396Y12C-SE1
- N9336C-SE1
- N9K-C9804
- N9K-C9808

그리고 “이 목록 외 Nexus 9000”, “Nexus 9000 ACI mode”, “Nexus 3000/7000” 등은 영향이 없다고 명시합니다.[^1]

어드바이저리에는 “공개적으로 알려진 악용/악성 사용을 인지하지 못했다”는 문장도 함께 들어가 있습니다.[^1]  
다만 이 문장은 보안 운영 관점에서 안전 신호가 아니라, 결정을 미룰 핑계가 되기 쉽습니다. PoC가 공개되는 순간부터는 “패치 난이도”가 아니라 “장애 반경”이 운영팀을 압박하게 됩니다.

## 왜 이번 건은 ‘스위치도 애플리케이션처럼 패치해야 한다’로 귀결되는가

내가 이번 건을 운영 관점에서 불편하게 보는 이유는 CVE 자체보다 조건이 운영 현실과 잘 맞물리기 때문입니다.

1) **default L3 VRF에서 접근 가능**하다는 전제가, 데이터센터 네트워크에서 흔합니다. 스위치를 OOB 관리망으로만 관리한다고 해도, underlay(예: loopback, p2p 링크), SVI, vPC keepalive, 서비스 단 네트워크 등으로 인해 장비는 default VRF에 IP를 갖는 경우가 많습니다. 이때 “관리 평면”은 OOB mgmt0만 의미하지 않습니다. “장비 자신으로 향하는 트래픽” 전체가 관리 평면이 됩니다.

2) 포트가 43210/43211로 특정되면, 공격자는 스캐너를 돌립니다. 서버 VLAN에서 L3로 붙어 있는 leaf/ToR의 SVI, 또는 spine의 loopback이 관측되면 바로 타겟이 됩니다. “외부에서 들어오지 않는다”는 가정만으로는 부족합니다. 내부 위협, 감염된 워크로드, 잘못 열려 있는 방화벽 룰이 현실적인 트리거입니다.

3) 코어/리프 장비는 패치 지연이 곧 장애 리스크로 변합니다. 여기서 말하는 장애는 “취약점 악용으로 인한 장애”만이 아닙니다.

- 급하게 패치하려다 준비 부족으로 upgrade 실패 → 더 큰 장애
- 임시 iACL을 급히 넣다가 기존 control-plane 트래픽 차단 → BGP/OSPF/BFD 문제로 장애
- 일부만 패치하고 일부를 방치 → 네트워크의 동작이 비대칭이 되면서 트러블슈팅 비용 상승

그래서 결론은 늘 비슷합니다. **취약점 대응이 ‘보안 이벤트’가 아니라 ‘배포 이벤트’가 되도록** 런북을 가져가야 합니다.

## 영향 범위를 실무적으로 자르는 방법: “장비 목록”이 아니라 “노출 경로”로 자르기

Cisco는 PID 목록을 제시했지만, 운영에서 필요한 질문은 3개로 쪼개집니다.

1) 우리 DC에 해당 PID가 있는가?
2) 그 장비로 “장비 자신을 향한” 트래픽이 들어올 수 있는가? (43210/43211 포함)
3) 패치(또는 임시 완화) 없이도 운영을 지속할 수 있는 시간이 얼마인가?

이 3가지를 빠르게 답하려면, **자산 인벤토리 → reachability 측정 → 업그레이드 가능성(ISSU/윈도우/롤백) 평가**를 한 번에 묶어야 합니다.

### PID로 1차 필터링: show module로 끝내지 말고, CMDB에 “실제 PID”를 남기기

어드바이저리 자체가 “PID를 show module로 확인하라”고 안내합니다.[^1]  
문제는 운영에서 show module 결과가 매번 사람 손을 타면, ‘이번 주 안에’ 의사결정이 불가능해진다는 점입니다.

실무에서 내가 권하는 최소 단위는 “장비 1대 = PID + NX-OS train + 관리 IP + underlay loopback + default VRF로 들어오는 경로”입니다. 이 네 가지를 한 줄로 뽑을 수 있어야 합니다.

아래는 Netmiko로 show module / show version을 수집해 “영향 PID 여부”를 표시하는 스크립트 예시입니다. 장난감이 아니라, 운영에서 바로 쓰는 형태를 목표로 했습니다.

#### 실행 환경

- Python 3.12
- Linux/macOS jump host(사내 접근 정책 준수)
- SSH 접근(읽기 전용 계정 권장)

`requirements.txt`

```txt
netmiko==4.4.0
pyyaml==6.0.2
rich==13.9.2
``` 

`inventory.yml`

```yaml
devices:
  - name: leaf-01
    host: 10.10.0.11
    username: netops_ro
    password: "${N9K_PASSWORD}"
  - name: leaf-02
    host: 10.10.0.12
    username: netops_ro
    password: "${N9K_PASSWORD}"
```

`collect_cve_2026_20212_scope.py`

```python
from __future__ import annotations

import csv
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

import yaml
from netmiko import ConnectHandler
from rich.console import Console

console = Console()

AFFECTED_PIDS = {
    "N9324C-SE1U",
    "N9348Y2C6D-SE1U",
    "N9364E-SG2-O",
    "N9364E-SG2-Q",
    "N9396T12C-SE1",
    "N9348Y12C-SE1",
    "N9396Y12C-SE1",
    "N9336C-SE1",
    "N9K-C9804",
    "N9K-C9808",
}

@dataclass
class DeviceResult:
    name: str
    host: str
    nxos_version: str
    pid: str
    affected_pid: bool

def parse_pid(show_module: str) -> str:
    # Example line in Cisco doc:
    # 1    36 ... N9336C-SE1 ok
    m = re.search(r"\s(\w[\w-]+)\s+ok\s*$", show_module, re.MULTILINE)
    if not m:
        return "UNKNOWN"
    return m.group(1)

def parse_nxos_version(show_version: str) -> str:
    # Typical NX-OS: "NXOS: version 10.4(3)" or "system: version ..."
    m = re.search(r"NXOS:\s+version\s+([^\s]+)", show_version)
    if m:
        return m.group(1)
    m = re.search(r"system:\s+version\s+([^\s]+)", show_version)
    if m:
        return m.group(1)
    return "UNKNOWN"

def main() -> int:
    inv_path = sys.argv[1] if len(sys.argv) > 1 else "inventory.yml"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "cve-2026-20212-scope.csv"

    with open(inv_path, "r", encoding="utf-8") as f:
        inv = yaml.safe_load(f)

    results: list[DeviceResult] = []

    for d in inv["devices"]:
        password = d["password"]
        if password.startswith("${") and password.endswith("}"):
            env = password[2:-1]
            password = os.environ.get(env, "")

        params = {
            "device_type": "cisco_nxos",
            "host": d["host"],
            "username": d["username"],
            "password": password,
            "fast_cli": False,
        }

        console.print(f"[cyan]Connecting[/cyan] {d['name']} ({d['host']})")
        with ConnectHandler(**params) as conn:
            show_version = conn.send_command("show version", read_timeout=60)
            show_module = conn.send_command("show module", read_timeout=60)

        pid = parse_pid(show_module)
        nxos_version = parse_nxos_version(show_version)
        affected = pid in AFFECTED_PIDS

        results.append(
            DeviceResult(
                name=d["name"],
                host=d["host"],
                nxos_version=nxos_version,
                pid=pid,
                affected_pid=affected,
            )
        )

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "host", "nxos_version", "pid", "affected_pid"])
        for r in results:
            w.writerow([r.name, r.host, r.nxos_version, r.pid, str(r.affected_pid)])

    console.print(f"[green]Wrote[/green] {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

실행:

```bash
export N9K_PASSWORD='***'
pip install -r requirements.txt
python collect_cve_2026_20212_scope.py inventory.yml
```

예상 출력(CSV):

```csv
name,host,nxos_version,pid,affected_pid
leaf-01,10.10.0.11,10.4(3),N9336C-SE1,True
leaf-02,10.10.0.12,10.4(3),N93180YC-EX,False
```

이 시점에서 운영 의사결정은 절반이 끝납니다. “있다/없다”가 아니라, **어느 랙/어느 팟/어느 vPC pair가 해당되는지**가 보이기 시작합니다.

### 노출도 확인: 43210/43211이 ‘열려 있나’가 아니라 ‘닿을 수 있나’를 확인한다

어드바이저리는 “TCP 43210/43211이 default L3 VRF에서 접근 가능”이라고 말합니다.[^1]  
여기서 운영이 실수하기 쉬운 지점은 “스위치에서 `show socket` 같은 걸로 리스닝을 확인하면 되겠지”라고 생각하는 겁니다.

이 취약점은 운영 관점에서 다음 순서로 접근하는 게 더 빠릅니다.

1) **(가장 먼저) 경로 차단이 가능한가?**
2) 차단 전까지, 내부에서 스캔이 가능한가? (승인된 보안 점검 절차)
3) 차단 후, 차단이 실제로 먹었는가?

승인된 점검 환경에서, jump host에서 reachability를 찍어보는 쪽이 실무적으로 더 유용합니다.

#### nmap로 포트 노출 확인(승인된 환경에서만)

`targets.txt`

```txt
10.20.0.11
10.20.0.12
10.30.0.21
```

실행:

```bash
nmap -Pn -p 43210,43211 -sS --min-rate 500 -iL targets.txt -oA s1hal_ports_$(date +%F)
```

- `-Pn`: ICMP가 막혀도 포트 스캔은 진행
- `--min-rate`: 대규모 환경에서 시간을 줄이되, 내부 정책(IDS/IPS) 고려

이 결과는 “취약/안 취약”이 아니라 “**임시 iACL을 어디에 적용해야 즉시 반경이 줄어드는지**”를 결정하는 데이터가 됩니다.

### Fixed release 확인: 이번 어드바이저리는 표를 주지 않는다

이번 어드바이저리는 “Fixed Software” 섹션에서 **Cisco Software Checker** 사용을 강하게 안내하고, 정적인 fixed release 테이블을 본문에 싣지 않았습니다.[^1]  
운영팀 입장에서는 답답하지만, NX-OS는 train이 많고(10.3, 10.4, 10.5, 10.6 …), 플랫폼/기능 조합에 따라 first fixed가 달라지는 구조라서 “표 하나로 끝”이 잘 안 맞습니다.

그래서 런북에는 아예 다음을 포함해야 합니다.

- 현재 running NX-OS 버전(정확한 문자열)
- 타겟 train(우리가 표준으로 쓰는 recommended release)
- Software Checker에서 CVE-2026-20212에 대한 “First Fixed” 결과 스크린샷/증적
- 실제 다운로드 가능한 이미지 파일명(부팅/언팩 형식 포함)

이 네 가지가 없으면, 변경관리(Change Management)에서 승인도 안 나고, 나중에 “왜 그 버전으로 갔나”를 설명하기도 어렵습니다.

## 임시 완화책을 운영 언어로 바꾸기: iACL과 Live Protect

Cisco는 workaround로 iACL을 제시합니다. 요지는 “필요한 관리/제어 트래픽만 허용하고 나머지 장비 목적 트래픽은 거부” 또는 “목적지 포트 43210/43211을 명시적으로 deny”입니다.[^1]  
그리고 iACL 일반론은 Cisco NX-OS Hardening Guide에도 꽤 자세히 정리되어 있습니다.[^2]

여기서 운영 판단은 두 갈래입니다.

- iACL을 “스위치 자체”에 걸 것인가?
- iACL을 “스위치로 들어오는 경로의 앞단(예: border leaf, 방화벽, 라우터)”에 걸 것인가?

내 경험상, 이 유형의 취약점은 **앞단에서 먼저 자르는 게 안정적**입니다.

- 스위치 자체 ACL은 변경 대상이 ‘바로 그 장비’라서, 적용 실수 시 관리 자체가 끊길 수 있습니다.
- 앞단(예: DC edge, 서비스 존 경계)에서 43210/43211을 막으면, 변경 반경과 롤백이 명확해집니다.

### iACL을 “인프라 주소 대역” 기준으로 설계해야 하는 이유

Hardening Guide가 iACL을 설명할 때 전제를 깔고 있습니다. “인프라 장비 목적 트래픽은 대부분 필요 없고, 허용해야 할 것은 관리/제어 트래픽”이라는 전제입니다.[^2]

이걸 실무적으로 가능하게 만드는 핵심은 IP Addressing입니다.

- loopback, p2p, infra SVI 같은 **인프라 목적 주소를 별도 대역으로 모아둔 경우**: iACL이 잘 먹힙니다.
- 서버/사용자/서비스 주소와 인프라 주소가 섞여 있는 경우: iACL은 급하게 넣을수록 장애 확률이 올라갑니다.

이번 CVE는 “특정 포트(43210/43211) + 장비 목적 트래픽”이라서, 최소한의 iACL로도 임시 방어가 가능합니다.

#### (예시) 방화벽/경계 라우터에서 43210/43211 드랍

- 목적지: Nexus 인프라 주소 대역(예: 10.255.0.0/16)
- 정책: 내부 모든 존에서 해당 포트 차단
- 예외: 없음(현재 기준)

이 한 줄 정책만으로도 “PoC 공개 이후 내부 lateral movement” 류의 리스크를 크게 낮출 수 있습니다.

### Live Protect: 쓸 수 있는 장비와 못 쓰는 장비가 갈린다

Cisco는 이번 CVE에 대해 “Live Protect shield”가 있다고 어드바이저리에 적어 두었습니다.[^1]  
Live Protect는 NX-OS에서 NXSecure를 활성화해 eBPF 기반(Tetragon agent)으로 실시간 커널 레벨 방어(shield)를 적용하는 기능으로 설명됩니다.[^3]

중요한 건, Live Protect는 “모든 Nexus 9K에 쓸 수 있는 만능 임시패치”가 아닙니다.

- Live Protect 자체가 10.6(2)F 등 특정 릴리스 이후를 전제로 합니다.[^3]
- 지원 플랫폼 표에서 **Nexus 9500/9800은 Live Protect not supported**로 명시되어 있습니다.[^3]
- 그런데 이번 CVE 영향 PID에는 N9K-C9804/N9K-C9808이 포함됩니다.[^1]

즉, 어떤 환경에서는 Live Protect가 “임시 방어막”이 아니라, 그냥 선택지 밖입니다. 이런 케이스는 임시 iACL + 빠른 업그레이드로만 해결됩니다.

#### NXSecure 활성화(기능 자체) 참고

Cisco 문서에는 NXSecure(= Live Protect 구현) 활성화가 `feature nxsecure`로 안내됩니다.[^3]

```text
switch(config)# feature nxsecure
```

그리고 정책/패키지 상태는 다음 계열의 show 명령으로 확인합니다.[^3]

```text
switch# show nxsecure packages
switch# show nxsecure policy status
```

운영에서는 “monitoring mode로 먼저 관측 후 enforce mode로 전환”을 권장하고, hit count 기반으로 충돌 여부를 보라고 적어 둡니다.[^3]

이걸 그대로 운영 언어로 바꾸면 다음이 됩니다.

- 임시 방어는 ‘패치 대체’가 아니라 **패치 윈도우를 확보하기 위한 브리지**다.
- enforce 전환은 변경이다. canary 장비에서 먼저 본다.

## 업그레이드 윈도우를 현실적으로 잡는 법: ISSU 가능성, 장애 반경, 그리고 “이번 주”라는 제약

이번 건에서 가장 위험한 판단은 “CVSS가 높으니 오늘 밤 전체 업그레이드”입니다. 코어/리프에서 업그레이드는 보안 이슈이면서 동시에 가용성 이슈입니다.

나는 업그레이드를 3단계로 쪼개서 의사결정하는 편입니다.

1) 즉시(당일): 경로 차단(iACL)로 노출도를 떨어뜨린다.
2) 48시간: canary 업그레이드로 업그레이드 절차/시간/부작용을 수치로 만든다.
3) 1주: wave rollout으로 전체 패치를 끝낸다.

이 구조를 쓰면 “이번 주 안에”라는 제약이 있어도, 첫날에 노출도를 낮춘 상태로 의사결정 시간을 벌 수 있습니다.

### install all을 기본으로 두는 이유

Cisco의 Nexus 9000 업그레이드/다운그레이드 가이드는 `install all`을 권장합니다. 이유는 호환성 체크와 BIOS 업그레이드 등을 자동으로 수행하기 때문이며, boot variable만 바꾸고 reload 하는 방식은 이런 체크를 우회하니 권장하지 않는다고 명시합니다.[^4]

즉, 런북 기본값은 다음이 됩니다.

- “업그레이드”는 `install all`로 한다.
- “사전검증”은 `show install all impact`로 한다.

10.6(x) 업그레이드 문서에도 `show install all impact nxos ...` 예시가 포함되어 있습니다.[^5]

### ISSU(무중단)에 대한 기대치를 먼저 꺾어야 한다

현장에서는 ISSU를 “스위치도 Kubernetes처럼 롤링업데이트 된다”로 오해하는 경우가 많습니다. 문서가 말하는 전제는 훨씬 빡빡합니다.

- ISSU는 “특정 릴리스(예: 7.0(3)I4(1) 이후)” 같은 출발점 조건이 있습니다.[^4]
- 업그레이드 중에는 구성 변경이 사실상 제한되고, 활성 configuration session이 있으면 HA 동작에도 문제가 생길 수 있다는 식의 전제가 들어갑니다.[^4]

그리고 더 중요한 운영 현실 하나가 문서에 박혀 있습니다.

- **In-service software downgrades(ISSD), 즉 non-disruptive downgrade는 지원하지 않는다**고 명시합니다.[^4]

이 문장 하나 때문에, 롤백 전략이 “ISSU 실패하면 다시 되돌린다”가 아니라 “실패하면 결국 reload/downgrade는 disruptive”가 됩니다.

따라서 런북에서는 ISSU 가능 여부를 ‘좋으면 쓰자’가 아니라 ‘기본은 disruptive, 가능하면 ISSU’로 둬야 실제 의사결정이 빨라집니다.

### 롤백은 ‘이미지 롤백’과 ‘구성 롤백’을 분리해야 한다

장비 패치가 실패했을 때 되돌리는 작업은 두 가지가 섞입니다.

- NX-OS 이미지/패키지 상태를 되돌리는 것
- 운영 중에 바뀐 구성(ACL/iACL, 라우팅 정책 등)을 되돌리는 것

구성 롤백 쪽은 NX-OS의 checkpoint/rollback 기능을 표준 절차로 넣는 게 안전합니다. Cisco 문서에서도 checkpoint 생성 명령이 `checkpoint stable` 같은 형태로 예시가 나옵니다.[^6]

또한 롤백 기능 자체를 “running-config 스냅샷을 저장해 나중에 재적용”하는 기능으로 설명합니다.[^7]

이미지/패키지 롤백은 train마다 방식이 다를 수 있으니, 런북에서는 원칙만 고정합니다.

- 업그레이드 전: 기존 이미지 파일을 bootflash에 남긴다.
- 업그레이드 전: `show install all impact` 출력(증적)을 남긴다.
- 업그레이드 후: 일정 시간 동안 기존 이미지로의 복귀 절차(다운그레이드)를 “disruptive”로 준비한다.

SMU/패키지 관점에서는 Cisco가 “패키지를 비활성화 후 commit”으로 이전 상태로 돌아갈 수 있다는 흐름을 문서화해 둡니다.[^8]  
하지만 이번 건을 SMU로 해결하는지, 이미지 업그레이드로 해결하는지는 환경마다 달라질 수 있으니(그리고 Cisco Software Checker 결과에 따라 달라지니), 운영 런북은 ‘원리’와 ‘증적’ 위주로 가져가는 게 낫습니다.

## 네트워크 운영 Runbook: 이번 CVE를 처리하는 표준 절차(체크리스트)

아래는 코어/리프/스파인 공통으로 쓸 수 있도록 구성한 런북입니다. 핵심은 “장비를 애플리케이션처럼 배포한다”를 네트워크 언어로 번역하는 것입니다.

### 0) 의사결정 입력값(오늘 만들고, 이번 주 내내 재사용)

- 영향 PID 여부(위 스크립트/CMDB)
- 장비 역할: spine/leaf/border leaf/서비스 leaf 등
- 리던던시 형태: vPC pair, ECMP, dual-homing 등
- 현재 NX-OS 버전 문자열(정확히)
- Cisco Software Checker에서 확인한 “First Fixed”(증적)
- 업그레이드 방식 후보: disruptive vs ISSU

이 입력값이 없으면, 변경관리에서 “긴급”이라는 말만 남고 실제 결정이 안 나옵니다.

### 1) 즉시 조치(당일): 노출면 줄이기

#### 1-1. iACL로 43210/43211을 먼저 막는다

- 차단 위치: 가능하면 DC 경계(방화벽/라우터), 최소한 affected Nexus로 들어오는 L3 경로의 직전 hop
- 차단 규칙: 목적지 포트 43210, 43211
- 로그: 첫 24~72시간은 drop log를 켜서 스캔 징후를 본다(가능한 범위에서)

Cisco 어드바이저리 자체가 iACL workaround를 권고합니다.[^1]  
그리고 iACL은 “필요 트래픽 허용 후 나머지 인프라 목적 트래픽 차단”이라는 구조로 설명합니다.[^2]

여기서 중요한 운영 원칙 하나.

- 43210/43211 드랍은 “임시 방어”이지만, 이번 건에서는 사실상 **항상 켜 두고 싶은 정책**에 가깝습니다.

이 포트가 정상 운영에 필요한 포트가 아니라는 전제가 있다면(어드바이저리의 서술상 그렇게 읽힙니다), 패치 이후에도 차단을 유지하는 쪽이 낫습니다.

#### 1-2. 탐지 신호를 잡는다(가능한 범위에서)

- 방화벽/라우터 drop log
- NetFlow/telemetry에서 목적지 포트 43210/43211 히트
- Nexus syslog에서 비정상 reload, S1HAL 크래시 징후

어드바이저리는 “S1HAL 프로세스 크래시가 reload로 이어질 수 있다”고 쓰고 있습니다.[^1]  
이 문장을 운영 언어로 바꾸면 “이벤트가 있으면 장애 조사 대상”입니다.

Cisco는 Snort rule(67005)도 함께 링크해 두었습니다.[^1]  
IPS/IDS를 운영 중이라면 이 시그니처 적용 여부도 런북에 들어가야 합니다.

### 2) 48시간 내 조치: canary 업그레이드로 ‘업그레이드 시간’을 숫자로 만든다

네트워크 장비 패치에서 사람을 불안하게 만드는 건 “재부팅하면 얼마나 걸리나”가 아니라 “얼마나 걸릴지 모른다”입니다.

그래서 canary에서 아래를 반드시 측정합니다.

- `install all` 기준 upgrade 소요 시간(분)
- 프로토콜 컨버전스 시간(BGP/OSPF/IS-IS, EVPN 등)
- 장애 징후: 링크 flap, vPC role change, MAC move, BFD down 등
- 변경 후 확인 항목의 실제 출력(증적)

이때 canary 장비는 “제일 안전한 장비”가 아니라, **대표성 있는 장비**를 고릅니다.

- 같은 PID
- 같은 기능 사용(예: VXLAN EVPN, vPC, 멀티테넌트 VRF 등)
- 같은 규모의 테이블/트래픽(가능하면)

### 3) 업그레이드 실행 전 체크(매 장비 공통)

#### 3-1. 사전 영향도 확인: show install all impact

10.6(x) 업그레이드 문서는 `show install all impact`를 예시로 포함하고, 설치가 어떤 모듈에 어떤 영향을 주는지 확인하라고 안내합니다.[^5]

```text
switch# show install all impact nxos bootflash:<target-image.bin>
```

이 출력은 변경관리의 “리스크 평가 증적”이 됩니다.

#### 3-2. 구성 잠금/세션 정리

Nexus 업그레이드 가이드는 업그레이드 전제 조건으로 “업그레이드 중 구성 변경 불가”, “active configuration session 정리”를 명시합니다.[^4]

```text
switch# show configuration session summary
```

그리고 업그레이드 시작 전에 다음을 표준으로 둡니다.

- 자동화 시스템(Ansible, NMS)이 해당 시간에 푸시하지 않도록 일시 정지
- 모니터링 알람 억제(하지만 장비 다운/업 이벤트는 기록)

#### 3-3. 구성 롤백 포인트 생성: checkpoint

NX-OS는 사용자 checkpoint를 만들 수 있고, 이름을 주면 최대 10개까지 보관한다는 식으로 문서화되어 있습니다.[^6]

```text
switch# checkpoint pre_cve_2026_20212
switch# show checkpoint pre_cve_2026_20212
```

이 한 줄이 “업그레이드 실패 시 복구 시간”을 크게 줄입니다. 이미지 롤백이 disruptive라도, 구성은 빠르게 되돌릴 수 있어야 합니다.

### 4) 업그레이드 실행(예시 흐름)

이미지 파일명/버전은 Software Checker 결과에 따라 달라질 수 있으므로, 여기서는 절차 흐름만 고정합니다.

1) 이미지 업로드(SCP/SFTP 등)
2) 해시 검증(가능하면)
3) impact check
4) install all
5) 재부팅/스위치오버/모듈 리로드
6) post-check

`install all`이 권장 방식이라는 점은 Cisco 문서에 명시되어 있습니다.[^4]

```text
switch# install all nxos bootflash:<target-image.bin>
```

이때 운영 측면에서 기억해야 할 현실적인 제약도 문서에 이미 들어 있습니다.

- 업그레이드는 네트워크가 “stable and steady”할 때 하라고 권고합니다.[^4]
- 전원 이슈가 있으면 이미지 손상 가능성이 있습니다.[^4]

급한 패치는 ‘서두르는 게’ 아니라 ‘준비를 줄이는 게’ 사고로 이어집니다.

### 5) post-check: “업그레이드 성공”을 네트워크 기준으로 정의한다

스위치 업그레이드에서 가장 흔한 실패는 “버전은 바뀌었는데, 네트워크는 미묘하게 깨졌다”입니다.

런북에서는 성공 기준을 다음처럼 선언적으로 둡니다.

- control-plane
  - BGP neighbor 정상(Established, prefix 수 정상)
  - underlay adjacency 정상(OSPF/IS-IS)
  - EVPN peer/route type 정상(해당 시)
- data-plane
  - vPC/port-channel 정상(해당 시)
  - 주요 VLAN/VRF의 ARP/ND 정상
  - 특정 서비스 경로(예: LB, DB) synthetic check 통과
- management-plane
  - SSH/SNMP/syslog/telemetry 정상
  - 임시 iACL/정책이 기대한 대로 동작

여기에 이번 CVE 특화 체크를 추가합니다.

- 43210/43211이 외부에서 더 이상 reachability가 없는지 재검증(nmap)
- (가능한 범위에서) 스위치 자체로 향하는 트래픽 정책이 유지되는지 확인

## 반론과 회의론: “이 정도면 괜찮지 않나”가 흔히 틀리는 이유

### “영향 장비가 10개 PID뿐이면 우선순위가 낮다”

PID가 적다는 건 전체 시장 기준이고, 우리 조직 기준이 아닙니다. 데이터센터는 특정 세대/특정 모델을 표준화해 깔아두는 경우가 많아서, “10개 PID”가 곧 “우리 리프의 80%”로 바뀌는 순간이 흔합니다.

### “외부에서 안 들어오는데, 내부는 믿을 수 있다”

이번 취약점의 위험은 외부 인터넷이 아니라 “서버 VLAN/워크로드”입니다. 내부에서 lateral movement가 가능한 환경이라면, 스위치는 공격자에게 ‘가장 좋은 발판’입니다. root privilege RCE는 네트워크 전체에 대한 관찰/가로채기/라우팅 조작 가능성을 의미합니다.

### “일단 iACL로 막았으니 패치는 다음 분기”

Cisco도 iACL을 workaround로 인정하지만, 동시에 “workaround는 임시 솔루션이고 fixed release로 업그레이드하라”는 뉘앙스를 분명히 깔고 있습니다.[^1]  
그리고 iACL은 운영 환경에 따라 기능/성능에 영향을 줄 수 있다는 경고도 같이 들어갑니다.[^1]

iACL을 장기화하면 다음 문제가 생깁니다.

- 시간이 지나면서 예외 룰이 쌓여 정책이 무너짐
- 새 장비/새 VRF가 추가될 때 정책 누락
- “임시”였던 정책이 표준이 되었는데 문서화/테스트가 부족

iACL은 시간을 벌어주지만, 그 시간이 “패치를 미루는 시간”으로 쓰이면 이득이 아니라 부채가 됩니다.

## 앞으로 지켜볼 것: 운영팀 관점의 관측 포인트

1) Cisco 어드바이저리 업데이트(Revision History)
   - 이번 문서는 Version 1.0 Final로 게시되었습니다.[^1]
   - 하지만 실제 현장에서는 “First Fixed가 바뀌거나, 추가 완화책이 생기거나, Live Protect 지원 범위가 바뀌는” 업데이트가 종종 발생합니다.

2) PoC/익스플로잇 유통
   - PSIRT가 “악용을 모른다”고 한 시점은 2026-09-02입니다.[^1]
   - 오늘이 2026-09-09(KST)라면, 딱 일주일입니다. 이 기간이 길지는 않습니다.

3) Live Protect shield의 적용 가능 플랫폼 확대 여부
   - Live Protect 지원 표에서 9800은 not supported로 명시되어 있고,[^3]
   - 영향을 받는 PID에는 9804/9808이 들어갑니다.[^1]  
   이 간극이 좁혀지는지 여부는 “임시 방어 수단”의 현실성을 크게 바꿉니다.

## 지금 할 수 있는 일: 이번 주에 끝내야 할 산출물

오늘(2026-09-09 KST) 기준으로, 이번 주 안에 끝내야 하는 산출물은 기술이 아니라 문서/증적입니다.

- 영향 PID 목록(장비명/역할/위치/vPC pair)
- 포트 노출도 측정 결과(차단 전/후)
- iACL 적용 지점과 룰(롤백 포함)
- Software Checker 기반 First Fixed 증적
- canary 업그레이드 결과(시간/부작용/성공 기준)
- wave rollout 계획(순서/윈도우/담당/롤백)

이걸 끝내면 “긴급 취약점 대응”이 “평소 배포 파이프라인의 특별 케이스”로 내려옵니다. 네트워크 장비는 여전히 특수하지만, 패치 운영은 특수가 아니게 만드는 쪽이 맞습니다.

## 참고 자료

- [Cisco Security Advisory: Cisco Nexus 9000 Series Switches Silicon One Remote Code Execution Vulnerability](https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-n9k-s1-rce-EH8dEtr)
- [Cisco NX-OS Software Hardening Guide](https://sec.cloudapps.cisco.com/security/center/resources/securing_nx_os.html)
- [Cisco Nexus 9000 Series NX-OS Security Configuration Guide: Secure NX-OS with Live Protect](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/106x/configuration/security/cisco-nexus-9000-series-nx-os-security-configuration-guide-release-106x/m-secure-nx-os-with-live-protect.html)
- [Upgrading or Downgrading the Cisco Nexus 9000 Series NX-OS Software (PDF, 10.3(x))](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/103x/upgrade/cisco-nexus-9000-nx-os-software-upgrade-downgrade-guide-103x/m_upgrading_or_downgrading_the_cisco_nexus_9000_series_nx-os_software_101x.pdf)
- [Cisco Nexus 9000 Series NX-OS Software Upgrade and Downgrade Guide: show install all impact 예시(10.6(x))](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/106x/upgrade/cisco-nexus-9000-series-nx-os-software-upgrade-and-downgrade-guide-106x/m-upgrade-or-downgrade-the-nexus-9000-series-nx-os-software.html)
- [Cisco Nexus 9000 Series NX-OS System Management Configuration Guide: Rollback(10.4(x))](https://www.cisco.com/c/en/us/td/docs/switches/datacenter/nexus9000/sw/104x/config-guides/cisco-nexus-9000-series-nx-os-system-management-configuration-guide-release-104x/m-configuring-rollback.html)
- [Cisco Nexus 9000 Series NX-OS System Management Configuration Guide: Creating a Checkpoint 예시(10.2(x))](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/102x/configuration/system-management/cisco-nexus-9000-series-nx-os-system-management-configuration-guide-102x/m-configuring-rollback-10x.html)
- [TechRadar 보도: Cisco patches three critical vulnerabilities…](https://www.techradar.com/pro/security/cisco-patches-three-critical-vulnerabilities-as-part-of-comprehensive-internal-security-review)

[^1]: <https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-n9k-s1-rce-EH8dEtr>
[^2]: <https://sec.cloudapps.cisco.com/security/center/resources/securing_nx_os.html>
[^3]: <https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/106x/configuration/security/cisco-nexus-9000-series-nx-os-security-configuration-guide-release-106x/m-secure-nx-os-with-live-protect.html>
[^4]: <https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/103x/upgrade/cisco-nexus-9000-nx-os-software-upgrade-downgrade-guide-103x/m_upgrading_or_downgrading_the_cisco_nexus_9000_series_nx-os_software_101x.pdf>
[^5]: <https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/106x/upgrade/cisco-nexus-9000-series-nx-os-software-upgrade-and-downgrade-guide-106x/m-upgrade-or-downgrade-the-nexus-9000-series-nx-os-software.html>
[^6]: <https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/102x/configuration/system-management/cisco-nexus-9000-series-nx-os-system-management-configuration-guide-102x/m-configuring-rollback-10x.html>
[^7]: <https://www.cisco.com/c/en/us/td/docs/switches/datacenter/nexus9000/sw/104x/config-guides/cisco-nexus-9000-series-nx-os-system-management-configuration-guide-release-104x/m-configuring-rollback.html>
[^8]: <https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/102x/configuration/system-management/cisco-nexus-9000-series-nx-os-system-management-configuration-guide-102x/m-performing-smu.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
