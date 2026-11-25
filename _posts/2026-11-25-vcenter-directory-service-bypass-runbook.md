---
title: "vCenter Directory Service 인증 우회 대응 런북: 노출 식별부터 HA/롤백까지"
description: "CVE-2026-123890 패치는 시작일 뿐입니다. 외부 노출 자산 식별→버전 매핑→우회 경로 차단→탐지→HA/롤백 순으로 대응 품질을 올립니다."
date: 2026-11-25 16:43:38 +0900
categories: ["News", "Security"]
tags: ["vmware", "vcenter", "incident-response", "asset-inventory", "vcf", "detection"]
render_with_liquid: false
---

## 2026-11-19 VMSA-2026-0009 정리: “인증 우회”는 패치 공지가 아니라 경계 붕괴 사건입니다

Broadcom/VMware는 2026-11-19에 [VMSA-2026-0009](https://support.broadcom.com/web/ecx/support-content-notification/-/external/content/securityadvisories/0/39495)를 공개했고(2026-11-20에 업데이트), 그 안에 vCenter Directory Service 인증 우회인 **CVE-2026-123890 (CVSS 9.8)** 이 포함되어 있습니다. Workaround는 없고, 네트워크로 도달 가능하면(“network access to vCenter”) 인증을 우회해 비인가 접근이 가능하다고 명시되어 있습니다.[^1]

이번 공지는 “vCenter만”의 문제가 아닙니다. 같은 VMSA에 SDDC Manager 3건(CVE-2026-123891/123892/123893)과 VMware Tools for Windows 1건(CVE-2026-123894)도 같이 들어있습니다. 특히 VCF(Cloud Foundation) 환경에서는 vCenter/SDDC Manager/Tools가 운영적으로 한 묶음으로 굴러가는 경우가 흔해서, 공지 문장을 그대로 받아 적는 방식으로는 런북이 완성되지 않습니다.[^1]

또 하나 중요한 변화가 있습니다. vCenter Quick Patch로 해결할 수 없습니다. VMSA-2026-0009 Q&A는 이번 업데이트가 vCenter Quick Patch 대상이 아니라고 못 박습니다.[^2]

이 글은 “패치를 어떻게 누르나”보다, 패치의 전제 조건이자 실패했을 때 복구 가능한 구조를 만드는 순서로 런북을 구성합니다.

- 외부 노출 자산 식별
- 버전 매핑
- 우회 가능 경로 차단(패치 전/후 공통)
- 탐지(로그/네트워크)
- HA/롤백(그리고 Directory Service가 깨졌을 때의 점검 포인트)

## 공격 맥락: vCenter Directory Service가 뚫렸을 때 실제로 벌어지는 일

Broadcom VMSA는 “Directory Service 인증 우회” 이상을 상세히 말해주지 않습니다. 대신, 실제 침해 관점의 실마리는 Google Threat Intelligence/Mandiant 분석에서 더 분명해집니다.

Google Cloud의 위협 인텔리전스 글은 ARMORY CASTLE이 2026년 9월 초(early September 2026)에 CVE-2026-123890을 악용했다고 밝히고, 악용 경로가 vCenter의 Directory Service(vmdird) DCE/RPC 인터페이스(포트 2012) 쪽 `rpc_srp_verifier` 서비스와 연결된다고 설명합니다. 이 취약점으로 `administrator@vsphere.local` 세션을 만들 수 있다고까지 적혀 있습니다.[^3]

또한 동일 글에서, 공격 도구(BONESAW/SAWSNAKE)가 하는 일을 구체적으로 나열합니다.

- vmdir의 LMDB(예: `data.mdb`)를 빼감
- STS SAML signing key를 뽑아냄
- SSO admin 계정을 생성
- 이후 SAML token 위조(일종의 Golden SAML 흐름)로 vCenter 세션 쿠키를 만듦[^3]

이 흐름이 의미하는 바는 단순합니다.

1) vCenter는 “가상화 관리 UI”가 아니라 control plane입니다.
2) Directory Service/SSO/STS 계층이 깨지면, 이후 단계는 계정/토큰/키 문제로 번집니다.
3) 그래서 패치 적용 자체보다, **도달 경로를 닫고(노출면 축소), 침해 흔적을 찾고(탐지), 실패 시 되돌릴 수 있어야(HA/롤백)** 합니다.

Rapid7 역시 “exploited in the wild”를 명시했고, 2026-11-19 VMSA 공개와 함께 emergency change로 취급해야 한다고 씁니다.[^4]

## 영향을 받는 조합을 먼저 묶어 봐야 합니다: vCenter / VCF(SDDC Manager) / VMware Tools

이번 이슈를 런북으로 만들 때, 자산을 “제품명”으로만 나누면 빠지는 구멍이 생깁니다. 내가 운영에서 자주 보는 실패 패턴은 다음입니다.

- “vCenter만 급하게 올리자” → VCF에서는 SDDC Manager lifecycle과 충돌
- “VCF 관리 도메인만 올리자” → workload domain vCenter가 따로 있고, 그쪽이 노출됨
- “vCenter는 올렸으니 됐다” → 게스트 운영에서 VMware Tools 취약점(CVE-2026-123894)을 그대로 방치

VMSA-2026-0009의 Response Matrix를 기준으로, 최소한 다음 고정점을 런북에 박아야 합니다.

- vCenter fixed: 9.1.x는 9.1.1.0200, 9.0.x는 9.0.2.0200, vCenter 8.0은 8.0 U3m
- vCenter 7.0은 “extended support contract가 있으면 Support 문의”
- VCF 5.x는 fixed로 5.2.5를 제시하며, async patching KB를 안내[^1]

VMSA Q&A는 vSphere 6.5/6.7/7.0처럼 downlevel(지원 종료) 계열에 대해 “리스트에 없더라도 영향 있다고 가정”하라고 적습니다. 지원 종료 버전을 “영향 없음”으로 분류하는 순간, 런북은 사고를 부릅니다.[^2]

또한 VCF 업그레이드 진행 중인 환경은 변수 하나가 더 있습니다. VMSA Q&A는 이번 패치가 “Back-in-Time” 업그레이드 이슈를 만들었고, vCenter 8.0 U3m / 9.0.2.0200이 VCF 9.1.1 업그레이드를 막을 수 있다고 적습니다(VCF 9.1.2에서 해소).[^2]

즉, 패치 계획은 보안 우선순위 + 업그레이드 경로를 같이 보는 운영 의사결정입니다.

## Step 1. 외부 노출 자산 식별: “인터넷에서 보이는 vCenter”를 먼저 끝냅니다

패치 우선순위를 정하기 위해서, 먼저 “인터넷에서 들어올 수 있나”를 확정해야 합니다. CVE-2026-123890은 “network access to vCenter”만 있으면 된다고 되어 있고, 실제 공격 분석은 vmdird 관련 포트(2012, 389/636 등)의 접근 가능성이 치명적 변수임을 보여줍니다.[^1]

내 기준으로는 다음 조건이면 “긴급”이 아니라 “즉시 격리”입니다.

- vCenter(또는 VCF management domain vCenter)가 인터넷에서 직접 접근 가능
- VPN 뒤에 있더라도, 광범위한 사내 네트워크(예: 사용자 VLAN)에서 vCenter management plane으로 접근 가능
- 포트 5480(VAMI)나 2012/389/636이 예상 외 대역에서 열려 있음

### 포트 기준(현실적인 최소 셋)

공격 분석 글은 CVE-2026-123890이 port 2012의 `rpc_srp_verifier` 서비스와 연결된다고 명시합니다.[^3]

또한 동일 글에서 공격자가 VAMI API로 SSH를 켰다고 적는데, 이건 “관리 plane HTTP API가 노출돼 있으면 공격 후반이 빨라진다”는 뜻입니다.[^3]

그래서 노출 식별은 최소한 아래 포트를 같이 봅니다.

- 443: vCenter UI/API
- 5480: VAMI(일반적으로는 여기로 접근을 최소화해야 함)
- 2012: Directory Service 연관 RPC(공격 분석에서 직접 언급)
- 389/636: LDAP 계열(이전 Directory Service 이슈들과도 엮이는 구간이었고, 공격 분석에서도 비교 대상으로 언급)[^3]

### 실행 가능한 스캔(“존재 확인” 수준)

취약점 테스트 패킷을 던지는 건 금물입니다. 여기서는 “열려 있는가/어디서 열려 있는가”만 확인합니다.

```bash
# 예시: 관리망/DMZ 후보 대역에서 vCenter 관련 포트가 열려 있는 자산만 뽑기
# (공격성 테스트가 아니라 TCP connect 수준의 존재 확인)

TARGETS="10.10.0.0/16 10.20.0.0/16"
PORTS="443,5480,2012,389,636"

nmap -n -Pn -sT --open -p "$PORTS" $TARGETS -oG vcenter-ports.gnmap

# 열려 있는 호스트만 간단히 추출
awk '/Ports:/{print $2"\t"$0}' vcenter-ports.gnmap | sort -u > vcenter-ports-open.txt

head -n 5 vcenter-ports-open.txt
```

예상 출력(형태 예시):

```text
10.10.12.34    Host: 10.10.12.34 () Ports: 443/open/tcp//https///, 2012/open/tcp///
10.20.3.10     Host: 10.20.3.10 () Ports: 443/open/tcp//https///, 5480/open/tcp//https///
```

이 파일이 만들어지면, 이제 “패치 대상 목록”이 아니라 “격리 대상 목록”이 먼저 나옵니다. 특히 5480이나 2012가 사용자 대역에서 열려 있으면, 패치 여부와 무관하게 네트워크 정책부터 뜯어고쳐야 합니다.

## Step 2. 버전 매핑: ‘Fixed Version’과 내 빌드를 자동으로 대조합니다

패치 런북이 실패하는 흔한 이유는 버전 매핑이 “사람의 기억”에 의존하기 때문입니다. VMSA는 fixed version을 명시했으니, 런북은 이를 코드/표로 고정해야 합니다.

VMSA-2026-0009 기준(vCenter 관련):

- VCF/VVF 9.1.x: vCenter 9.1.1.0200
- VCF/VVF 9.0.x: vCenter 9.0.2.0200
- vCenter 8.0: 8.0 U3m
- vCenter 7.0: extended support 계약이 있으면 Support 문의[^1]

### PowerCLI로 vCenter 버전/빌드 수집(현업에서 제일 빨리 굴러갑니다)

VMSA Q&A는 PowerCLI에서 `$global:DefaultVIServer.Build` / `.Version`으로 버전/빌드를 확인할 수 있다고 적습니다.[^2]

아래 스크립트는 “여러 vCenter를 한 번에” 점검하는 용도입니다. vCenter 목록은 CMDB/DNS/위 스캔 결과를 기반으로 넣는 편이 현실적입니다.

```powershell
# Requires: VMware PowerCLI
# Install-Module VMware.PowerCLI -Scope CurrentUser

$ErrorActionPreference = 'Stop'

# 1) 점검 대상 vCenter 목록(예: 관리 도메인 + workload 도메인)
$vcenters = @(
  'vcsa-mgmt-01.example.internal',
  'vcsa-wld-01.example.internal'
)

# 2) 자격 증명(SSO 계정; 환경에 맞게)
$cred = Get-Credential  # 예: administrator@vsphere.local

# 3) 결과 수집
$results = @()

foreach ($vc in $vcenters) {
  try {
    Connect-VIServer -Server $vc -Credential $cred -WarningAction SilentlyContinue | Out-Null

    $version = $global:DefaultVIServer.Version
    $build   = $global:DefaultVIServer.Build

    $results += [pscustomobject]@{
      vCenter = $vc
      Version = $version
      Build   = $build
    }
  }
  catch {
    $results += [pscustomobject]@{
      vCenter = $vc
      Version = 'ERROR'
      Build   = $_.Exception.Message
    }
  }
  finally {
    Disconnect-VIServer -Server $vc -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
  }
}

$results | Sort-Object vCenter | Format-Table -AutoSize
$results | Export-Csv -NoTypeInformation -Encoding UTF8 vcenter-version-inventory.csv
```

예상 출력(형태 예시):

```text
vCenter                         Version     Build
------                         -------     -----
vcsa-mgmt-01.example.internal   8.0.3       257xxxx
vcsa-wld-01.example.internal    8.0.3       25934264
```

이 결과를 VMSA fixed version과 대조해 “취약 가능”을 태깅하면 됩니다. 이때 중요한 운영 규칙은 하나입니다.

- “8.0.3이면 안전” 같은 분류를 하면 안 됩니다. VMSA는 8.0 “U3m”처럼 업데이트 레벨이 핵심입니다.[^1]

## Step 3. 우회 가능 경로 차단: 패치 전에도, 패치 후에도 남겨야 합니다

이번 유형의 취약점은 패치가 나와도 “노출된 control plane”이라는 구조 문제가 남습니다. 그래서 런북은 패치 적용과 별개로 네트워크 차단을 기본 상태로 만들어야 합니다.

내가 권하는 원칙은 단순합니다.

- vCenter는 사용자 네트워크에서 접근하면 안 됩니다.
- vCenter/SDDC Manager/VAMI는 bastion(점프 호스트) 경유만 허용합니다.
- Directory Service 관련 포트는 “정말 필요한 시스템”만 허용합니다.

Google 분석에서 CVE-2026-123890이 port 2012의 서비스와 연결된다고 했으니, 최소한 2012는 “관리 plane 내부에서만” 살아 있어야 합니다.[^3]

또한 공격자가 VAMI API로 SSH를 켰다는 대목은, 5480/VAMI 및 관련 API 경로 접근 통제를 강하게 해야 한다는 힌트입니다.[^3]

### 방화벽 정책(예시: 의사코드 수준)

- Source: bastion subnet / 운영자 VPN egress
- Destination: vCenter management IP
- Allow: 443
- Allow(필요 시): 5480 (운영자만)
- Deny(기본): 2012, 389, 636은 “관리 컴포넌트 간 통신만” 예외 허용

여기서 중요한 점은, vCenter HA(vCHA)나 ELM/연동 구성에 따라 내부 통신 예외가 필요할 수 있다는 것입니다. 예외를 “그냥 다 열기”로 처리하는 순간, control plane은 다시 평평해집니다.

## Step 4. 탐지(로그/네트워크): 침해는 ‘패치 여부’가 아니라 ‘행위’로 잡힙니다

이번 케이스는 이미 wild exploitation 정황이 있고(Rapid7), 구체 TTP까지 공개되어 있습니다.[^4]

그래서 탐지 포인트는 “CVE 트리거”가 아니라, vCenter 운영에서 평소 거의 일어나지 않는 행위를 잡는 방향이 효율적입니다.

### 네트워크 기반 탐지

1) vCenter로 향하는 TCP 2012 연결
- 평소에 누가 쓰는지 조직마다 다릅니다. 중요한 건 “예상치 못한 소스”에서의 접근입니다.
- 내부 Linux appliance(보안 에이전트 없는 구간)에서 갑자기 vCenter 2012로 붙는 패턴이 보이면 우선순위를 올립니다. (Google 분석의 현실적 공격 경로와도 맞습니다.)[^3]

2) vCenter로 향하는 5480/443의 비정상 호출
- 특히 “SSH enable/disable” 같은 관리 plane 설정이 API로 토글되는지 봅니다.
- Google 분석은 공격자가 VAMI API로 `/rest/appliance/access/ssh`에 PUT을 날려 SSH를 켰다고 씁니다. 이 엔드포인트 호출은 정상 운영에서도 빈도가 낮은 편이라, 탐지 신호로 가치가 있습니다.[^3]

3) LDAP(389/636)로 vCenter에 붙는 비정상 흐름
- Google 분석은 이전 취약점(CVE-2026-59309) 비교에서 389/636을 직접 언급합니다. 조직 내부에서 이 포트가 열려 있다면 “왜 열려 있는지”부터 문서화해야 합니다.[^3]

### vCenter 로그 기반 탐지(최소 셋)

vmdird 로그 위치는 Broadcom KB에서 반복적으로 언급됩니다.

- `/var/log/vmware/vmdird/vmdird-syslog.log`[^5]

그리고 “Directory Service가 깨질 때” 같이 봐야 하는 로그가 몇 개 더 있습니다.

- `/var/log/vmware/vmon/vmon.log` (서비스 기동/의존성 문제 확인에 필요)[^6]
- `/var/log/vmware/applmgmt/update_microservice.log` (업데이트 precheck/replication check 실패 확인에 등장)[^7]

내 경우 SIEM에는 “vCenter 로그 전체를 다 넣는 것”보다, 아래 형태로 줄여 넣었습니다.

- vmdird state가 NORMAL에서 이탈하는 이벤트
- VAMI에서 SSH 토글 관련 API 호출 로그(가능하면 reverse proxy/WAF/접근 로그에서)
- 비정상 시간대의 vCenter 관리자 로그인/SSO admin 계정 추가

Google 분석에는 공격자가 `sps-<...>@vsphere.local` 같은 계정을 만들었다는 사례가 있으니, 계정 생성/권한 부여 이벤트를 별도로 감시하는 편이 낫습니다.[^3]

## Step 5. HA/롤백: “패치 성공률”을 올리는 게 아니라 “실패 비용”을 낮춥니다

보안 패치는 항상 운영 장애 리스크를 동반합니다. 이번 VMSA는 Workaround가 없고 Quick Patch도 안 되므로, 실제로는 업데이트 작업이 더 무겁습니다.[^1]

런북에서 HA/롤백을 뒤로 미루면, 패치 일정이 곧바로 “서비스 중단 공포”와 연결되고, 결국 미뤄집니다. 그래서 순서를 의도적으로 HA/롤백까지 끌고 와야 합니다.

### 최소 롤백 단위: 파일 기반 백업/복구를 기본으로 둡니다

vCenter는 “문제 생기면 스냅샷 되돌리면 되지”가 항상 통하지 않습니다. 특히 Directory Service/SSO/인증서 계층이 꼬인 상태에서 스냅샷 롤백은 상황을 더 나쁘게 만드는 케이스를 여러 번 봤습니다.

공식 문서에서도 restore 실패 시 부분적으로 복구된 VM을 삭제해야 한다는 식의 강한 제약을 언급합니다. 복구 절차는 “확실한 1회성 복원”으로 설계해야 합니다.[^8]

또한 운영 정책으로는 “백업이 성공했는지 검증”이 들어가야 합니다. 이 주제는 예전에 내가 썼던 [Cisco ISE CVE-2026-76460 패치 전후 운영 검증](https://daewooki.github.io/posts/cisco-ise-cve-2026-76460-patch-verification/)에서 “패치보다 검증이 먼저인 이유”를 다른 제품 사례로 정리해 둔 적이 있는데, vCenter도 같은 원칙이 적용됩니다.

### VCF(특히 5.x)에서는 ‘비동기 패치’ 경로를 런북에 고정합니다

VMSA-2026-0009의 Response Matrix는 VCF 5.x의 fixed version을 5.2.5로 적고, async patching guide(KB 88287)를 추가 문서로 연결합니다.[^1]

이건 운영적으로 큰 차이를 만듭니다.

- standalone vCenter: VAMI/일반 업데이트 절차 중심
- VCF: SDDC Manager의 LCM, async patch tool, BOM/compatibility 제약이 중심

패치 런북에 “우리 환경은 어느 쪽인지”가 1줄로 박혀 있어야, 새벽 장애 때 사람들의 방향성이 맞습니다.

### 업그레이드 진행 중이면 Back-in-Time 이슈를 체크포인트로 둡니다

VMSA Q&A는 이번 패치가 “Back-in-Time” 업그레이드 이슈를 만들 수 있고, vCenter 8.0 U3m / 9.0.2.0200이 VCF 9.1.1 업그레이드를 막는다고 명시합니다(VCF 9.1.2에서 해소).[^2]

보안 관점에서는 패치를 미룰 근거가 되기 어렵지만, 운영 관점에서는 “업그레이드가 멈추는 비용”을 미리 계량해야 합니다. 내 결론은 다음이었습니다.

- 외부 노출/횡적 이동 위험이 있으면: 업그레이드 경로가 막혀도 패치가 먼저
- 내부 격리가 이미 강하고, 업그레이드 중단 비용이 치명적이면: VCF 9.1.2 등 해소 버전까지의 브릿지 플랜을 같이 세우되, 그동안 네트워크 차단/탐지를 강화

이 선택을 기술적으로 가능하게 만드는 게 앞단의 “노출 식별→차단”입니다.

## Directory Service가 깨질 때(업데이트 전/후 공통): 가장 먼저 보는 6가지

현장에서 “Directory Service가 깨졌다”는 표현은 대개 아래 현상으로 관측됩니다.

- vCenter 업데이트 precheck에서 VMDir not normal
- vSphere UI 로그인/SSO 실패
- vpxd/vpxd-svcs 등 다른 서비스가 vmdird 의존성 때문에 연쇄적으로 안 뜸

아래는 내가 런북에 고정해 두는 점검 순서입니다. 핵심은 “복구 시도”보다 “원인 범주를 빠르게 좁히기”입니다.

### 1) vmdird가 실제로 어떤 상태인지: NORMAL / Read-Only / Standalone / Failure

Broadcom KB들은 반복적으로 vmdird state(NORMAL 여부)를 업데이트/기능 장애의 분기점으로 씁니다.

- 업데이트 실패 메시지: “VMDIR Service Is Not in 'NORMAL' State”[^9]
- replication status 변화 및 부팅 후 revert 등 상태 이슈[^10]

상태 확인 도구는 환경마다 다를 수 있지만, KB는 `service-control`로 vmdird를 재기동하는 예시를 제공합니다.[^10]

```bash
# 서비스 상태 일괄 확인
service-control --status --all

# vmdird만 재기동(원인 파악 없이 무한 반복하는 건 금물)
service-control --stop vmdird && service-control --start vmdird
```

여기서 중요한 건, 재기동으로 “일시적으로 NORMAL”이 되더라도 재부팅 후 다시 깨질 수 있다는 케이스가 있다는 점입니다. 상태가 유지되지 않으면, 그 다음 항목(복제/머신 계정/디스크)을 봐야 합니다.[^10]

### 2) 업데이트 precheck/replication partner 체크에서 막히는지 확인

업데이트 과정에서 replication partner status check가 실패하면서 VMDir not normal로 떨어지는 사례가 KB에 있습니다. 해당 KB는 `update_microservice.log`에서 `vdcrepadmin ... showpartnerstatus` 호출 직후 실패하는 패턴을 보여줍니다.[^7]

이 경우 “Directory Service 자체가 망가졌다”기보다, 로컬 머신 계정 기반 SASL 인증이 실패하는 계열일 수 있습니다.

### 3) 로컬 머신 계정 패스워드 불일치(SASL -13) 계열을 의심

여러 KB에서 동일한 에러 시그니처가 반복됩니다.

- vmdird 로그에서 SASL authentication failure, error -13
- precheck에서 VMDir not normal
- 원인: 로컬 머신 계정 패스워드 불일치로 인해 로컬 vmdird에 SASL로 붙지 못함[^7]

KB는 이 불일치 문제를 해결하기 위해 내장 스크립트(`reset_machine_pw.sh`)를 언급합니다(해당 KB는 별도 문서로 안내).[^7]

이 계열은 운영자가 “서비스 재기동”만 반복하면 시간을 잃는 타입입니다. 원인이 계정/인증 레이어이기 때문입니다.

### 4) vpxd/vpxd-svcs 연쇄 장애면 ‘증상’이 아니라 ‘의존성’으로 본다

vpxd/vpxd-svcs가 안 뜨는 건 흔히 “vCenter가 망가졌다”로 보이지만, KB는 vmdird database state가 NORMAL로 복구되면 vpxd-svcs가 시작될 수 있다고 설명합니다. vmon.log에서 LDAP bind 실패가 같이 보일 수 있습니다.[^6]

즉, 이 경우 vpxd를 두드리는 게 아니라 vmdird state를 정상화하는 쪽으로 원인 제거를 해야 합니다.

### 5) 로그가 비어 있으면 ‘문제 없음’이 아니라 ‘로깅 파이프 문제’일 수 있다

vmdird 로그 파일 경로는 KB에서 제시되는데, 또 다른 KB는 vmdird-syslog.log에 “현재 로그가 안 찍히면 rsyslog 이슈일 수 있다”고 말합니다.[^11]

침해 대응/장애 대응에서 로그 공백은 곧 관측 불능이므로, 로깅 파이프가 정상인지(파일이 갱신되는지) 자체를 체크리스트에 넣는 편이 낫습니다.

### 6) 디스크/DB 파티션 문제는 ‘인증’ 문제처럼 보이기도 한다

인증서/VECS/VMAFD 계열 이슈는 결국 Directory Service/인증 계층과 엮이면서, 표면 증상이 “로그인 실패”로 나옵니다. Broadcom KB에는 VECS/Certificate Manager가 vecs-cli 문제, DB 업데이트 실패 등으로 깨지는 사례가 꾸준히 있습니다.[^12]

이 구간은 함부로 “수정 스크립트”를 돌리기 전에, 최소한 아래를 확인합니다.

- `/storage/db` 및 관련 파티션 여유 공간
- 최근에 hostname/PNID 변경 작업 여부(머신 계정/인증서/디렉터리와 같이 무너질 수 있음)[^13]

## 패치 적용을 런북의 마지막으로 미루는 이유: 패치만 하면 끝나는 사건이 아니기 때문

이번 이슈는 “인증 우회”이고, Google/Mandiant 분석이 보여준 후속 행위는 control plane 장악(SSO admin 생성, STS key 탈취, 토큰 위조 등)로 이어집니다.[^3]

그래서 내 결론은 항상 같습니다.

- 패치 적용은 필요조건이지만 충분조건이 아닙니다.
- 대응 품질은 패치 속도가 아니라 **노출면을 정확히 접고, 버전 매핑을 자동화하며, 우회 경로를 차단하고, 관측(로그/네트워크)을 확보하고, 실패했을 때 되돌릴 수 있는지**로 결정됩니다.

이 순서를 런북으로 고정하면, “긴급 패치 공지”가 와도 조직은 공포가 아니라 절차로 움직이게 됩니다.

## 참고 자료

- [VMSA-2026-0009: VMware vCenter, Tools, and SDDC Manager updates](https://support.broadcom.com/web/ecx/support-content-notification/-/external/content/securityadvisories/0/39495)
- [VMSA-2026-0009 Q&A (vcf-security-and-compliance-guidelines)](https://github.com/vmware/vcf-security-and-compliance-guidelines/blob/main/security-advisories/vmsa-2026-0009/README.md)
- [Rapid7 이메일 공지: CVE-2026-123890 exploited in the wild](https://information.rapid7.com/index.php/email/emailWebview?email=NDExLU5BSy05NzAAAAGllNw6EZYMuOSXuRok4gIP5C3hFYIjAIk1-lhgGacE_WEDGuyFk75jFO1t3lxr8G0_pm6sCjWxQopF_Q8HuYkYE6Q4GY25a8qtNAE)
- [ARMORY CASTLE Exploits vSphere (Google Cloud Threat Intelligence)](https://cloud.google.com/blog/topics/threat-intelligence/armory-castle-exploits-vsphere)
- [Applying individual product updates to VMware Cloud Foundation environments using Async Patch (KB 88287)](https://knowledge.broadcom.com/external/article?legacyId=88287)
- [Attempting to update vCenter Server Appliance fails with VMDIR not NORMAL (KB)](https://knowledge.broadcom.com/external/article/378328/attempting-to-update-vcenter-server-appl.html)
- [vCenter Server upgrade precheck fails: VMDir not normal, SASL -13 (KB)](https://knowledge.broadcom.com/external/article/433192/vcenter-server-upgrade-fails-precheck-wi.html)
- [vCenter replication status change / vmdir status reverts (KB)](https://knowledge.broadcom.com/external/article/369323/vcenter-server-replication-status-change.html)
- [vpxd/vpxd-svcs fails to start due to vmdird DB state (KB)](https://knowledge.broadcom.com/external/article/443407/vcenter-server-vpxdsvcs-fails-to-start-d.html)
- [The VMware Directory Service (vmdird) logs location (KB)](https://knowledge.broadcom.com/external/article/322199/the-vmware-directory-service-vmdird-is-e.html)
- [vCenter Server Installation and Setup: restore operation note (VMware Docs)](https://www.vmware.com/docs/vsphere-vcenter-802-installation-guide)
- [Introducing VCF PowerCLI 9.0 (Cloud Foundation Blog)](https://blogs.vmware.com/cloud-foundation/2025/06/24/introducing-vcf-powercli-9-0/)

[^1]: <https://support.broadcom.com/web/ecx/support-content-notification/-/external/content/securityadvisories/0/39495>
[^2]: <https://github.com/vmware/vcf-security-and-compliance-guidelines/blob/main/security-advisories/vmsa-2026-0009/README.md>
[^3]: <https://cloud.google.com/blog/topics/threat-intelligence/armory-castle-exploits-vsphere?hl=en>
[^4]: <https://information.rapid7.com/index.php/email/emailWebview?email=NDExLU5BSy05NzAAAAGllNw6EZYMuOSXuRok4gIP5C3hFYIjAIk1-lhgGacE_WEDGuyFk75jFO1t3lxr8G0_pm6sCjWxQopF_Q8HuYkYE6Q4GY25a8qtNAE>
[^5]: <https://knowledge.broadcom.com/external/article/322199/the-vmware-directory-service-vmdird-is-e.html>
[^6]: <https://knowledge.broadcom.com/external/article/443407/vcenter-server-vpxdsvcs-fails-to-start-d.html>
[^7]: <https://knowledge.broadcom.com/external/article/433192/vcenter-server-upgrade-fails-precheck-wi.html>
[^8]: <https://www.vmware.com/docs/vsphere-vcenter-802-installation-guide>
[^9]: <https://knowledge.broadcom.com/external/article/378328/attempting-to-update-vcenter-server-appl.html>
[^10]: <https://knowledge.broadcom.com/external/article/369323/vcenter-server-replication-status-change.html>
[^11]: <https://knowledge.broadcom.com/external/article/316338/vmware-directory-service-failed-to-delet.html>
[^12]: <https://knowledge.broadcom.com/external/article/410607/corrupted-vecscli-executable-impacts-cer.html>
[^13]: <https://knowledge.broadcom.com/external/article/324595>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
