---
title: "Edge Stable 업데이트를 엔터프라이즈에서 검증하는 방법: CVE 우선순위·버전 준수율·재시작 정책"
description: "Edge Stable 154.0.4258.62 배포를 사례로, Chromium 보안 인제스트를 조직에서 놓치지 않게 만드는 계측·정책·운영 기준을 정리합니다."
date: 2026-10-10 13:53:14 +0900
categories: ["News", "Web"]
tags: ["microsoft-edge", "chromium", "cve", "intune", "defender-xdr", "patch-management"]
render_with_liquid: false
---

## 2026-10-05 배포 사실과 타임라인: 154.0.4258.62는 어떤 릴리스인가

Microsoft Learn의 보안 릴리스 노트는 2026-10-05에 Stable 버전 **154.0.4258.62**가 배포되었고, “Chromium 프로젝트의 최신 Security Updates를 포함한다”고 적고 있습니다. 동시에 “CVE는 이용 가능해지는 대로 추가된다”는 문구가 같이 붙습니다.[^1]

Stable 채널의 기능/비보안 릴리스 노트(아카이브)는 같은 버전을 “Update 3”로 표시하면서, 내용은 “버그/성능 수정 + 보안 업데이트는 보안 릴리스 노트를 보라”로 정리합니다.[^2]

여기서 중요한 포인트가 하나 더 있습니다. 내가 글을 쓰는 시점(사용자가 준 기준으로 2026-10-10 KST)에는 Stable이 이미 155 메이저로 넘어간 상태입니다. Stable 릴리스 노트의 최신 섹션은 2026-10-08에 Stable 155.0.4283.45가 배포됐다고 적습니다.[^3]

즉, 154.0.4258.62는 “최신 Stable”은 아니지만, 현실의 엔터프라이즈에서는 여전히 대표적인 점검 샘플이 됩니다.

- 업데이트 링(ring)으로 점진 배포 중이라, 일부 풀에서는 아직 154 메이저를 유지합니다.
- TargetVersionPrefix로 메이저를 고정하거나(예: 154.*), 특정 버전까지 고정해 두는 조직이 있습니다.[^4]
- VDI(특히 non-persisted)에서는 golden image로 버전을 관리하고 auto-update를 꺼두는 것이 권장되기도 합니다.[^5]

추가로 “배포가 실제로 있었는지”를 Microsoft Learn만으로 확인하면 불안해하는 조직이 있는데, Windows용 패키지는 Microsoft Update Catalog에서도 2026-10-05 날짜로 Edge Stable 154.0.4258.62 항목을 확인할 수 있습니다.[^6]  
Linux 쪽은 packages.microsoft.com 리포지토리에 `microsoft-edge-stable_154.0.4258.62-1_amd64.deb`가 2026-10-05로 올라온 기록이 보입니다.[^7]

정리하면, 154.0.4258.62는 “154 메이저의 세 번째 마이너 업데이트(Update 3)”이고, 보안 릴리스 노트 관점에서는 “Chromium 보안 인제스트를 포함한 Stable 업데이트”입니다.[^1]

## 자동 업데이트가 있어도 패치가 누락되는 지점: 정책·서비스·이미지 관리

엔터프라이즈에서 브라우저 패치 누락의 원인은 대개 “업데이트 메커니즘이 없다”가 아니라 “업데이트 메커니즘을 일부 집단에서 예외로 만들어 둔 것”입니다. 문제는 예외가 항상 문서화되지 않고, 시간이 지나면 예외가 기본값처럼 굳는다는 점입니다.

### 1) 버전 고정(TargetVersionPrefix)과 채널 고정(TargetChannel)

Edge Update 정책 문서는 TargetVersionPrefix가 “auto-update가 활성화돼 있을 때 지정한 버전으로 업데이트한다”고 명시합니다. 또한 디바이스에 더 최신 버전이 이미 있으면 다운그레이드하지 않는다는 동작도 같이 적습니다.[^4]

- 버전 고정은 호환성 이슈(사내 레거시 웹앱, 키오스크, 특정 확장 프로그램) 때문에 현실적으로 필요할 때가 있습니다.
- 다만 버전을 고정해두면 “Chromium 보안 인제스트가 들어오는 경로”를 스스로 막는 셈이라, 별도 프로세스로 흡수해야 합니다.

TargetChannel 역시 정책으로 문서화돼 있고 Stable/Beta/Dev/Extended Stable로 고정 가능합니다.[^4]

여기서 운영상 함정은 “채널 고정”과 “버전 고정”이 섞이면서, 어느 시점엔가 특정 풀만 오래된 메이저에 남아버리는 시나리오입니다.

### 2) UpdateDefault / AutoUpdateCheckPeriodMinutes로 업데이트를 사실상 끊는 경우

Edge Update 정책 문서는 UpdateDefault 값의 의미를 꽤 명확하게 적어 둡니다.

- 0: Updates disabled
- 1: Always allow updates (recommended)
- 2: Manual updates only
- 3: Automatic silent updates only

그리고 AutoUpdateCheckPeriodMinutes를 0으로 두면 Edge Update의 “주기적 네트워크 트래픽” 자체를 끊을 수 있다고 경고합니다(권장하지 않음).[^4]

이 조합이 자주 나오는 조직 내 패턴이 있습니다.

- “키오스크는 트래픽 제한 때문에 업데이트를 끄자” → UpdateDefault=0
- “VDI 풀은 버전 불일치가 싫으니 업데이트를 끄자” → UpdateDefault=0 + 이미지 업데이트로만 갱신[^5]
- “업데이트 창이 귀찮다” → Manual only(2)로 바꿔놓고 이후 수동 업데이트가 안 돌아감

### 3) 업데이트 서비스 자체가 비활성화되거나 동작이 깨진 경우

업데이트가 “정책상 허용”돼 있어도, 실제로 업데이트 컴포넌트가 깨진 경우가 있습니다.

Microsoft의 트러블슈팅 문서는 Edge 설치/업데이트/롤백 실패 시 관련 컴포넌트로 Microsoft Edge Update 서비스(`msedgeupdate`)를 명시합니다.[^8]

현장에서 체감하는 대표 증상은 다음과 같습니다.

- 버전이 바뀌지 않는다
- 업데이트가 다운로드된 것 같지만 적용되지 않는다
- 특정 보안 에이전트/애플리케이션 제어 솔루션이 updater 프로세스 실행을 막는다

이때 “업데이트 체인이 살아 있는지”를 검증하려면 (1) 정책 (2) 서비스/작업 스케줄러 (3) 네트워크(프록시, TLS)까지 같이 봐야 합니다.

### 4) VDI/non-persisted는 auto-update를 꺼두는 게 권장인 점이 더 위험하다

Microsoft의 VDI 문서는 non-persisted VDI 환경에서 “best practice는 automatic updates를 disable하고 golden image를 업데이트하는 방식”이라고 분명히 적습니다.[^5]

이 권장사항 자체는 합리적입니다.

- 풀 내 VM마다 버전이 제각각이면 헬프데스크가 감당이 안 됩니다.
- 업데이트 도중 재부팅/세션 중단이 치명적일 수 있습니다.

하지만 이 방식을 택한 순간부터 “브라우저 자동 업데이트”는 존재하지 않는 것이고, golden image 업데이트 SLA가 곧 보안 SLA가 됩니다. 즉, 버전 준수율을 endpoint 기준으로 재는 게 아니라 image 기준으로 재야 합니다.

## CVE 기반 배포 우선순위: ‘Chromium 보안 인제스트’를 어떻게 위험도로 바꿀 것인가

Edge 보안 릴리스 노트가 2026-10-05 버전에 대해 “Chromium의 최신 보안 업데이트를 포함한다”라고만 쓰고 CVE를 바로 나열하지 않는 것은, 보안팀 입장에서는 상당히 불친절합니다.[^1]

그렇다고 “CVE 목록이 나올 때까지 기다리자”는 선택지는 보통 틀립니다. 브라우저는 공격 표면이 크고, 공지 직후 며칠이 가장 위험합니다.

여기서 필요한 건 “CVE 목록이 완성되기 전에” 배포 우선순위를 결정할 수 있는 규칙입니다.

### 1) 신호(시그널)를 세 단계로 나눠서 본다

내가 운영에서 쓰는 접근은 다음 세 가지 신호를 분리하는 것입니다.

1) **Edge 보안 릴리스 노트의 ‘Exploit in the wild’ 언급**

예를 들어 2026-09-24에 배포된 Edge 154.0.4258.37은 Chromium 팀이 CVE-2026-87491에 대해 exploit in the wild를 보고했으며, 이 업데이트에 fix가 포함된다고 명시합니다. 또한 Edge-specific fix(CVE-2026-85892)도 같이 적습니다.[^1]

이런 문장은 P0에 가깝습니다. “지금 공격 중이거나 공격 준비가 끝났다”는 신호이기 때문입니다.

2) “Chromium 보안 인제스트가 들어간 새로운 빌드가 나왔는가”

2026-10-05 Stable 154.0.4258.62는 이 범주입니다. CVE 목록이 당장 없더라도, 신규 보안 픽스가 들어왔다는 사실 자체가 위험 신호입니다.[^1]

3) Chromium(Chrome) 쪽에서 exploit in the wild로 선언했는가

Chromium 취약점은 Chrome 릴리스 블로그에서 “Google is aware that an exploit … exists in the wild” 같은 문장으로 공표되는 경우가 있습니다. 예를 들어 2026-09-03 Chrome Stable 업데이트 글은 CVE-2026-85046에 대해 exploit in the wild를 언급합니다.[^9]

이 신호는 Edge에도 직접적으로 영향을 줍니다. Edge가 Chromium을 기반으로 하고, Edge 보안 릴리스 노트도 반복적으로 “Chromium security updates를 포함한다”는 형태로 공지하기 때문입니다.[^1]

### 2) MSRC(Security Update Guide)로 Chromium CNA CVE가 흡수되는 흐름을 이해한다

Microsoft는 Security Update Guide에 업계 파트너가 할당한 CVE도 싣는다고 설명했고, Chrome이 식별/수정한 Chromium CVE를 “Assigning CNA가 Chrome”으로 표시해 Security Update Guide에 추가한다고 밝혔습니다.[^10]

즉, “Edge 릴리스 노트에 CVE가 아직 없더라도” 결국 MSRC 데이터로 들어오는 경로가 있습니다. 문제는 타이밍이고, 그래서 배포 우선순위는 (앞 절의) 신호 기반 규칙이 먼저 필요합니다.

### 3) 배포 우선순위를 숫자로 내리는 간단한 룰

내가 조직에 제안할 수 있는 실무 룰은 이 정도가 적당합니다.

- P0 (24~72시간 내):
  - exploit in the wild 언급이 있는 CVE를 포함한 브라우저 업데이트
  - 인증/권한경계 우회, 샌드박스 탈출, RCE 계열로 분류되는 브라우저 엔진/렌더러/JS 엔진 취약점
- P1 (1주 내):
  - Chromium security ingest가 포함된 마이너 업데이트(이번 154.0.4258.62 같은 유형)
  - 조직 내에서 외부 웹 접근이 많은 집단(영업/CS/협력사 포털 접속)이면서, EDR 격리나 웹 격리로 보호되지 않는 집단
- P2 (2~4주 내):
  - 기능 플래그 변경/정책 변경이 큰 메이저 업데이트(호환성 검증이 필요한 업데이트)

이 룰이 실제로 유효하려면 “우선순위를 매겼으면, 그 우선순위에 맞게 준수율을 계측”해야 합니다. 계측이 없으면, 우선순위는 회의 자료로 끝납니다.

## 버전 탐지/준수율 계측: ‘설치됨’이 아니라 ‘보안 빌드가 실행 중’까지 재는 방법

브라우저 패치는 OS 패치와 다르게, 설치가 완료돼도 프로세스가 살아 있으면 옛 엔진이 계속 돌 수 있습니다. Microsoft Support 문서도 기본적으로 “Edge는 브라우저를 restart할 때 자동 업데이트된다”는 설명을 합니다.[^11]

그래서 준수율을 두 층으로 나눠야 합니다.

- Installed version 준수율: 디스크에 설치된 msedge.exe 버전이 목표 이상인가
- Effective version 준수율: 실제 사용자 세션에서 목표 빌드가 실행 중인가(= 재시작이 끝났나)

현실적으로 Effective까지 강하게 재려면 EDR/텔레메트리 쪽이 필요하고, Intune만으로는 빈 구멍이 생깁니다.

### 1) Intune Discovered apps의 한계: 기본 refresh가 7일 단위다

Intune의 Discovered apps는 소프트웨어 인벤토리로 유용하지만, 문서에 “일반적으로 디바이스별 refresh는 7일”이라고 명시돼 있습니다(예외로 Win32 앱의 일부 데이터는 IME가 24시간 단위 수집).[^12]

브라우저 보안 패치에서 “공지 직후 며칠”이 중요한데, 7일짜리 인벤토리로 준수율을 재면 결론적으로 이런 문제가 생깁니다.

- 보안팀 관점: 아직도 취약 버전이 깔려 있는 것처럼 보임(실제로는 업데이트 완료)
- IT 운영 관점: 이미 처리했는데 계속 쫓아다님

Discovered apps는 “추세/대략의 분포”에는 좋지만, P0/P1 대응의 근거 데이터로는 부족합니다.

### 2) Defender TVM(DeviceTvmSoftwareInventory)로 시간 해상도를 끌어올린다

조직에 Microsoft Defender Vulnerability Management/Defender XDR이 있다면, `DeviceTvmSoftwareInventory`는 소프트웨어 인벤토리를 비교적 짧은 주기로 제공합니다.

- 테이블 설명: 네트워크 디바이스에 설치된 소프트웨어 인벤토리(End of support 포함)
- 컬럼: `SoftwareVendor`, `SoftwareName`, `SoftwareVersion` 등[^13]

또한 Defender Vulnerability Management의 소프트웨어 인벤토리는 “데이터가 3~4시간마다 업데이트된다”고 안내합니다.[^14]

브라우저 패치 체인 점검에는 이 정도 해상도가 실무적으로 의미가 큽니다.

#### KQL 예시: Edge 버전 분포와 목표 버전 미달 장비 찾기

아래 쿼리는 “Microsoft Edge”가 깔린 장비의 버전 분포를 뽑는 기본 형태입니다. (조직에 따라 `SoftwareName` 표기가 조금 다를 수 있어 `has` 기반으로 시작합니다.)[^13]

```kusto
DeviceTvmSoftwareInventory
| where SoftwareVendor =~ "Microsoft"
| where SoftwareName has "Edge"
| summarize Devices=dcount(DeviceId) by SoftwareName, SoftwareVersion
| order by Devices desc
```

목표 버전을 “154.0.4258.62 이상”으로 두고 미달 장비를 찾으려면 버전 비교가 필요합니다. KQL에서 문자열 버전을 단순 비교하면 틀릴 수 있으니, 운영에서는 보통 4파트로 쪼개 정수화합니다.

```kusto
let target = dynamic([154,0,4258,62]);
DeviceTvmSoftwareInventory
| where SoftwareVendor =~ "Microsoft"
| where SoftwareName has "Microsoft Edge" or SoftwareName has "Edge"
| extend parts = split(SoftwareVersion, ".")
| extend v0 = toint(parts[0]), v1 = toint(parts[1]), v2 = toint(parts[2]), v3 = toint(parts[3])
| extend isBelow = case(
    v0 < target[0], true,
    v0 > target[0], false,
    v1 < target[1], true,
    v1 > target[1], false,
    v2 < target[2], true,
    v2 > target[2], false,
    v3 < target[3], true,
    false)
| where isBelow
| project DeviceName, OSPlatform, OSVersion, SoftwareName, SoftwareVersion
| order by SoftwareVersion asc
```

이걸로 “154.0.4258.62 미만”이 남아 있는지 바로 확인할 수 있습니다.

다만 여기서 한 단계 더 가야 합니다. 미달 장비가 발견됐을 때, 그 원인이 무엇인지 분류해야 대응이 빨라집니다.

- 정책으로 업데이트가 막혔는가(UpdateDefault=0, AutoUpdateCheckPeriodMinutes=0, TargetVersionPrefix)
- 서비스/작업 스케줄러/네트워크 문제로 업데이트가 실패하는가[^8]
- VDI 풀이라 원래 golden image 관리 대상인가[^5]

### 3) 엔드포인트에서 ‘업데이트 체인 상태’를 수집하는 PowerShell 스크립트

Intune/ConfigMgr/VDI 스크립팅 어떤 방식이든, 결국엔 엔드포인트에서 아래 데이터를 한 번은 뽑아야 합니다.

- msedge.exe 경로/버전
- EdgeUpdate 정책 레지스트리(`HKLM\SOFTWARE\Policies\Microsoft\EdgeUpdate`)
- Edge 재시작 유도 정책(`HKLM\SOFTWARE\Policies\Microsoft\Edge`)
- EdgeUpdate 서비스 상태

아래 예시는 “버전 + 정책 키 + 서비스 상태”를 JSON으로 출력합니다. Intune proactive remediation이나, RMM 에이전트 커스텀 인벤토리 수집에 그대로 넣기 편합니다.

```powershell
#requires -Version 5.1

$edgePath = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" -ErrorAction SilentlyContinue)."(default)"
if (-not $edgePath) {
  $edgePath = (Get-Command msedge.exe -ErrorAction SilentlyContinue)?.Source
}

$edgeVersion = $null
if ($edgePath -and (Test-Path $edgePath)) {
  $edgeVersion = (Get-Item $edgePath).VersionInfo.ProductVersion
}

$edgePolicyPath = "HKLM:\SOFTWARE\Policies\Microsoft\Edge"
$edgeUpdatePolicyPath = "HKLM:\SOFTWARE\Policies\Microsoft\EdgeUpdate"

function Get-RegValues($path) {
  if (-not (Test-Path $path)) { return @{} }
  $item = Get-ItemProperty $path
  $props = $item.PSObject.Properties | Where-Object {
    $_.Name -notin @('PSPath','PSParentPath','PSChildName','PSDrive','PSProvider')
  }
  $h = @{}
  foreach ($p in $props) { $h[$p.Name] = $p.Value }
  return $h
}

$edgePolicies = Get-RegValues $edgePolicyPath
$edgeUpdatePolicies = Get-RegValues $edgeUpdatePolicyPath

$svc = @("edgeupdate","edgeupdatem","msedgeupdate") | ForEach-Object {
  $s = Get-Service -Name $_ -ErrorAction SilentlyContinue
  if ($s) {
    [pscustomobject]@{ Name=$s.Name; Status=$s.Status.ToString(); StartType=$s.StartType.ToString() }
  }
}

[pscustomobject]@{
  CollectedAt = (Get-Date).ToString("o")
  EdgePath = $edgePath
  EdgeVersion = $edgeVersion
  EdgePolicies = $edgePolicies
  EdgeUpdatePolicies = $edgeUpdatePolicies
  Services = $svc
} | ConvertTo-Json -Depth 6
```

이 출력물을 중앙으로 모으면 “버전 미달”을 다음처럼 자동 분류할 수 있습니다.

- `UpdateDefault = 0`인 집단(의도된 고정)
- `TargetVersionPrefix*`가 잡힌 집단(의도된 버전 고정)
- 서비스가 Disabled/Stopped인 집단(의도/비의도 혼재)
- 정책은 정상인데 버전만 낮은 집단(네트워크/권한/보안 에이전트 간섭, 또는 재시작 미완료)

버전 준수율은 이 분류가 끝나야 의미가 생깁니다. “몇 %가 낮다”는 숫자만으로는 실행 계획이 안 나옵니다.

## 재시작/세션 복구 정책: 보안 업데이트 적용의 마지막 1마일

브라우저 업데이트 운영에서 가장 많이 발생하는 착시는 “업데이트 다운로드는 됐지만 적용은 안 됐다”입니다. 그리고 적용의 마지막 1마일은 재시작 정책입니다.

### 1) RelaunchNotificationPeriod: 재시작 요구 알림 기간을 짧게 가져가는 기준

Microsoft Edge 정책 문서는 `RelaunchNotificationPeriod`가 “pending update를 적용하기 위해 Edge를 relaunch 해야 한다는 알림을 반복적으로 보여주는 기간(ms)”이라고 정의합니다. 기본값이 604800000ms(= 1주)라는 것도 문서에 적혀 있습니다.[^15]

1주 기본값은 사용자 경험은 좋지만, 보안 관점에서는 길게 느껴지는 경우가 많습니다. 특히 exploit in the wild급 이슈에서는 “1주 동안 재시작 안 해도 된다”는 메시지로 읽힙니다.

운영적으로는 이런 식으로 구간을 나누는 편이 낫습니다.

- P0 (exploit in the wild): 24h~72h로 당김
- P1 (Chromium security ingest): 3~7일
- VDI/키오스크: 사용자 알림 대신 운영창구(점검 시간)에 강제 재시작

### 2) RelaunchWindow: 강제 적용의 시간을 업무 외 시간으로 밀어 넣는다

`RelaunchWindow` 문서는 “RelaunchNotification / RelaunchNotificationPeriod 기반으로 강제 재시작이 일어날 수 있고, 그 종료 시점을 특정 시간 창으로 defer할 수 있다”고 설명합니다. 또한 “업데이트 적용을 지연시킬 수 있다”는 경고를 같이 적습니다.[^16]

여기서 트레이드오프는 명확합니다.

- 보안팀: 빨리 적용하고 싶다
- 운영팀: 업무 시간에 브라우저 강제 재시작하면 장애 콜이 폭증한다

내 경우 조직 합의를 만들 때 “업무 시간 강제 재시작은 금지하되, 야간 창을 반드시 마련한다”로 정리했습니다. 강제 적용 자체를 포기하면 준수율이 다시 무너집니다.

예시 값(문서의 포맷 그대로):[^16]

```json
{"entries": [{"duration_mins": 240, "start": {"hour": 2, "minute": 15}}]}
```

### 3) 세션 복구(restore) 정책: 재시작을 강하게 걸수록 ‘업무 탭을 복원’해야 한다

재시작을 적극적으로 밀면, 사용자 불만의 80%는 “탭/세션이 날아간다”로 수렴합니다. 특히 Web SaaS/내부 포털 중심 업무는 브라우저가 사실상 IDE/ERP 클라이언트입니다.

Edge의 `RestoreOnStartup` 정책 문서는 다음 옵션을 명시합니다.

- last session 복원
- 특정 URL 목록 열기
- (Edge 125부터) last session + URL 목록 동시 적용 옵션[^17]

또한 last session 복원이 “일부 설정(종료 시 데이터 삭제, 세션 전용 쿠키 등)과 충돌할 수 있다”고 명시합니다.[^17]

여기서 운영상 결론은 간단합니다.

- 보안을 위해 재시작을 강제하는 조직이라면, 최소한 “세션 복구가 정책으로 일관되게 동작”해야 합니다.
- 동시에 “종료 시 데이터 삭제” 같은 정책을 강하게 밀고 있다면, last session 복원과 설계 충돌이 납니다.

그리고 Web 관점에서 하나 더 짚어야 할 것이 있습니다. 154 메이저 릴리스 노트에는 unload event의 신뢰성 문제와 deprecation 방향이 꽤 상세히 적혀 있습니다.[^3]

브라우저가 unload를 안 불러도 살아남는 설계를 해야 하고, 그렇지 않으면 재시작 강제 정책이 곧 애플리케이션 데이터 유실 이슈로 이어집니다. 이 부분은 예전에 정리했던 “업데이트 프로세스가 운영을 강제하는 방식”과 같은 맥락이라 링크로 대체합니다.

- [Chrome 152 제로데이 공지가 패치 프로세스를 강제하는 방식](https://daewooki.github.io/posts/chrome-152-zero-day-forces-patching-process/)
- [Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영](https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/)

## ‘Chromium 보안 인제스트’를 조직의 데이터 파이프라인으로 넣는 방법(현실적인 수준)

Edge 보안 릴리스 노트가 CVE를 바로 나열하지 않는 경우가 있어도, 엔터프라이즈가 할 수 있는 일은 꽤 많습니다.

### 1) MSRC(Security Update Guide) API(CVRF)로 월 단위 CVE를 자동 수집한다

MSRC는 Security Update Guide API에서 인증/API Key 요구를 제거해 접근을 단순화했다고 공지했습니다.[^18]

또한 GitHub에 MSRC CVRF API의 swagger 정의가 공개돼 있습니다.[^19]

이 API는 “월 단위(yyyy-mmm) CVRF 문서”를 가져오는 형태가 기본이라, 브라우저의 2주/수시 릴리스와 1:1 매칭되지는 않습니다. 그럼에도 다음 목적에는 충분히 쓸모가 있습니다.

- Edge(Chromium-based) 항목으로 분류되는 CVE(특히 Chrome CNA로 들어오는 항목)를 조직 DB로 가져오기
- Exploitability 평가나 제품 태그를 같이 저장해 우선순위 산정 근거로 사용

예시로 MSRC Security Update Guide의 월별 릴리스 노트 페이지는 Edge(Chromium-based)와 Chrome CNA로 republishing되는 CVE 목록을 같이 보여줍니다.[^20]

### 2) ‘빌드 목표’는 릴리스 노트 기반으로 먼저 확정한다

CVE 목록이 늦게 붙는다고 해서 “목표 버전”을 늦게 잡으면 안 됩니다. 목표 버전은 릴리스 노트/배포 사실 기반으로 즉시 확정하고, CVE는 사후에 근거를 보강하는 방식이 낫습니다.

예시로, 154 메이저 트레인에 대한 최소 목표를 이렇게 잡을 수 있습니다.

- Stable 154 트레인 유지 집단: 154.0.4258.62 이상(2026-10-05 Update 3)[^2]
- 최신 Stable 추종 집단: 155.0.4283.45 이상(2026-10-08 메이저 릴리스)[^3]

이렇게 목표 버전을 먼저 잡아두면, 준수율 계측(Defender TVM/Intune/스크립트)이 먼저 돌아가기 시작합니다.

### 3) VDI/non-persisted는 “디바이스 준수율” 대신 “이미지 준수율”로 바꾼다

VDI 문서가 권장하는 방식(자동 업데이트 비활성화 + golden image 업데이트)을 따르면, 디바이스별로 버전을 올리는 자동화는 원천적으로 막힙니다.[^5]

따라서 VDI 풀에서는 준수율 정의 자체를 바꿔야 합니다.

- (잘못된 질문) VDI VM 1,000대 중 몇 %가 154.0.4258.62인가?
- (맞는 질문) 현재 프로덕션 풀에 배포된 golden image의 Edge 버전은 무엇이며, 교체 작업이 언제 끝나는가?

VDI를 예외로 인정하되, 예외는 “누락”이 아니라 “다른 단위의 준수율”로 계측돼야 합니다.

## 반론과 회의론: 브라우저를 빨리 올리면 장애가 난다

이 반론은 사실입니다. 특히 키오스크/VDI/업무망 내부 시스템은 브라우저 업데이트가 곧 장애로 이어질 수 있습니다. 그리고 Microsoft의 VDI 문서도 “non-persisted는 자동 업데이트를 끄고 이미지로 관리”를 권장합니다.[^5]

하지만 여기서 결론이 “그러니 업데이트를 늦추자”로 끝나면, 실제로는 다음이 발생합니다.

- 버전 고정이 영구화된다(TargetVersionPrefix가 제거되지 않는다)[^4]
- UpdateDefault=0이 유지된다[^4]
- 재시작 정책이 없어 실제 적용이 지연된다[^15]

결국 “장애 회피를 위한 예외”가 “취약점 상시 노출”을 만든다는 게 핵심입니다.

현실적인 균형점은 다음처럼 잡는 게 낫습니다.

- 버전 고정/업데이트 차단을 허용하되, 반드시 만료일을 둔다(예: 2주/4주)
- 예외 집단은 golden image/오프라인 패키지(카탈로그/MSI)로 별도 패치 체인을 운영한다[^6]
- 재시작 강제 정책은 업무 외 시간 창과 세션 복구 정책을 묶어서 적용한다[^16]

## 앞으로 지켜볼 것: 릴리스 속도 자체가 조직의 패치 설계를 바꾼다

Microsoft Edge는 2주 cadence로 업데이트된다는 공지가 릴리스 노트에 포함돼 있습니다.[^3]

이 속도에서는 “모든 버전을 충분히 검증하고 올리는 방식”이 현실적으로 불가능해집니다. 내 경험상 가능한 선택지는 둘 중 하나입니다.

- (A) 링을 촘촘히 만들고, 링 간 SLA를 짧게 가져가며, 문제 발생 시 롤백/고정을 빠르게 한다
- (B) 대규모 예외(VDI/키오스크)를 제외하고는 Stable을 따라가되, 재시작/세션복구/호환성 테스트 자동화를 강화한다

그리고 최신 릴리스 흐름을 보면 2026-10-08에 155가 나왔고, 이어서 2026-10-05에는 154의 Update 3가 있었습니다. 이런 겹침은 “조직 내 일부는 154, 일부는 155”가 되는 기간을 만들어냅니다.[^3]

이 기간의 보안 운영은 “최신 버전 하나로 통일”이 아니라, “두 개 이상의 목표 버전/정책을 병행”하는 형태가 됩니다.

## 지금 할 수 있는 일: Edge 154.0.4258.62를 샘플로 업데이트 체인을 점검하는 체크리스트

1) 목표 버전을 확정합니다.

- 최신 Stable 추종 링: 155.0.4283.45 이상(2026-10-08)[^3]
- 154 고정 링: 154.0.4258.62 이상(2026-10-05)[^1]

2) 업데이트 차단/고정 정책을 수집해 “의도된 예외”와 “방치된 예외”를 분리합니다.

- UpdateDefault 값(0/1/2/3)[^4]
- AutoUpdateCheckPeriodMinutes=0 여부[^4]
- TargetVersionPrefix 설정 여부[^4]

3) 준수율은 두 소스로 계측합니다.

- 빠른 계측: Defender TVM(`DeviceTvmSoftwareInventory`)[^13]
- 느린 계측/감사 목적: Intune Discovered apps(7일 주기 한계 인지)[^12]

4) 재시작 정책을 P0/P1로 나눠 적용합니다.

- RelaunchNotificationPeriod 기본 1주를 그대로 두지 않습니다.[^15]
- 야간 창을 RelaunchWindow로 확보합니다(업데이트 지연 위험도 같이 감수).[^16]

5) 세션 복구 정책을 재시작 정책과 함께 설계합니다.

- RestoreOnStartup에서 last session 복원(또는 last session + URLs)을 검토합니다.[^17]
- 종료 시 데이터 삭제 정책과 충돌 가능성을 문서화합니다.[^17]

이 정도까지 하면, “브라우저 자동 업데이트가 있는 조직에서도 패치가 누락되는 문제”는 대부분 숫자로 보이기 시작합니다. 그리고 숫자로 보이기 시작하면, 예외는 누락이 아니라 관리 대상이 됩니다.

## 참고 자료

- [Microsoft Edge Stable/Extended Stable 릴리스 노트(아카이브): 154.0.4258.62 (2026-10-05)](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-archive-stable-channel)
- [Microsoft Edge 보안 업데이트 릴리스 노트: 2026-10-05 154.0.4258.62](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security)
- [Microsoft Edge Stable/Extended Stable 릴리스 노트(최신)](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-stable-channel)
- [Microsoft Edge Update 정책 문서(UpdateDefault, TargetVersionPrefix 등)](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-update-policies)
- [Microsoft Edge VDI 가이드(non-persisted의 auto-update 비활성화 권장)](https://learn.microsoft.com/en-us/deployedge/edge-for-virtualized-desktop-infrastructure)
- [Intune Discovered apps 문서(리프레시 주기 포함)](https://learn.microsoft.com/en-us/intune/app-management/discovered-apps)
- [Defender XDR Advanced hunting: DeviceTvmSoftwareInventory 테이블](https://learn.microsoft.com/en-us/defender-xdr/advanced-hunting-devicetvmsoftwareinventory-table)
- [Defender Vulnerability Management: Software inventory(업데이트 주기 3~4시간)](https://github.com/MicrosoftDocs/defender-docs/blob/public/defender-vulnerability-management/tvm-software-inventory.md)
- [Edge 재시작 알림 기간 정책: RelaunchNotificationPeriod](https://learn.microsoft.com/deployedge/microsoft-edge-browser-policies/relaunchnotificationperiod)
- [Edge 재시작 시간창 정책: RelaunchWindow](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/relaunchwindow)
- [Edge 시작 시 세션 복구 정책: RestoreOnStartup](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/restoreonstartup)
- [Edge 업데이트 설정(기본적으로 restart 시 업데이트 적용)](https://support.microsoft.com/en-us/edge/microsoft-edge-update-settings)
- [Edge 업데이트/설치/롤백 실패 트러블슈팅(msedgeupdate 컴포넌트 포함)](https://learn.microsoft.com/en-us/troubleshoot/microsoft-edge/manageability/update-install-rollback-failures)
- [Chrome Releases: Stable Channel Update for Desktop(Exploit in the wild 예시)](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html)
- [MSRC 블로그: Security Update Guide API 접근 단순화(인증/키 제거)](https://www.microsoft.com/en-us/msrc/blog/2021/02/continuing-to-listen-good-news-about-the-security-update-guide-api)
- [MSRC 블로그: 업계 파트너(CNA) 할당 CVE를 Security Update Guide에 포함(Chrome CNA 포함)](https://www.microsoft.com/en-us/msrc/blog/2021/01/security-update-guide-supports-cves-assigned-by-industry-partners/)
- [MSRC CVRF API Swagger(GitHub)](https://github.com/microsoft/MSRC-Microsoft-Security-Updates-API/blob/main/docs/swagger.json)
- [Microsoft Update Catalog 검색(Edge Stable 154.0.4258.62 항목 확인)](https://www.catalog.update.microsoft.com/Search.aspx?q=Edge+x64+stable)
- [packages.microsoft.com Edge stable 리포지토리(154.0.4258.62 .deb)](https://packages.microsoft.com/repos/edge/pool/main/m/microsoft-edge-stable/)

[^1]: <https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security>
[^2]: <https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-archive-stable-channel>
[^3]: <https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-stable-channel>
[^4]: <https://learn.microsoft.com/en-us/deployedge/microsoft-edge-update-policies>
[^5]: <https://learn.microsoft.com/en-us/deployedge/edge-for-virtualized-desktop-infrastructure>
[^6]: <https://www.catalog.update.microsoft.com/Search.aspx?q=Edge+x64+stable>
[^7]: <https://packages.microsoft.com/repos/edge/pool/main/m/microsoft-edge-stable/>
[^8]: <https://learn.microsoft.com/en-us/troubleshoot/microsoft-edge/manageability/update-install-rollback-failures>
[^9]: <https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html>
[^10]: <https://www.microsoft.com/en-us/msrc/blog/2021/01/security-update-guide-supports-cves-assigned-by-industry-partners/>
[^11]: <https://support.microsoft.com/en-us/edge/microsoft-edge-update-settings>
[^12]: <https://learn.microsoft.com/en-us/intune/app-management/discovered-apps>
[^13]: <https://learn.microsoft.com/en-us/defender-xdr/advanced-hunting-devicetvmsoftwareinventory-table>
[^14]: <https://github.com/MicrosoftDocs/defender-docs/blob/public/defender-vulnerability-management/tvm-software-inventory.md>
[^15]: <https://learn.microsoft.com/deployedge/microsoft-edge-browser-policies/relaunchnotificationperiod>
[^16]: <https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/relaunchwindow>
[^17]: <https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/restoreonstartup>
[^18]: <https://www.microsoft.com/en-us/msrc/blog/2021/02/continuing-to-listen-good-news-about-the-security-update-guide-api>
[^19]: <https://github.com/microsoft/MSRC-Microsoft-Security-Updates-API/blob/main/docs/swagger.json>
[^20]: <https://msrc.microsoft.com/update-guide/releaseNote/2026-Feb>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
