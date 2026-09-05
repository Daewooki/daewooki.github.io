---
title: "Chrome 152 제로데이 공지가 패치 프로세스를 강제하는 방식"
description: "V8 타입 혼동 제로데이가 ‘실제 악용’으로 공지되면 링 배포·강제 재시작·정책이 어떻게 운영을 바꾸는지 정리합니다."
date: 2026-09-05 09:38:00 +0900
categories: ["News", "Security"]
tags: ["chrome", "v8", "zero-day", "patch-management", "enterprise-policy", "relaunch"]
render_with_liquid: false
---

## 무슨 일이 있었나: 152.0.7977.82/.83와 ‘exploit in the wild’ 문장 하나
2026-09-03(목) Google은 Desktop Chrome Stable을 **152.0.7977.82/.83(Windows, Mac), 152.0.7977.82(Linux)**로 업데이트했다고 공지했습니다. 이 빌드는 “앞으로 며칠/몇 주에 걸쳐 순차 롤아웃”된다고 명시되어 있고, 12건의 보안 수정이 포함됩니다. 그중 **CVE-2026-85046(V8 타입 혼동)**에 대해 “Google is aware that an exploit for CVE-2026-85046 exists in the wild.”를 박아 넣었습니다. 즉, 공지 시점에 이미 현실 공격이 존재한다는 뜻입니다. [Chrome Releases 공지](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html)[^1]

이번 건에서 운영 관점으로 중요한 숫자와 문자열은 아래 두 줄로 요약됩니다.

- 영향 버전: 152.0.7977.82 미만(“prior to 152.0.7977.82”)이 취약한 것으로 정리되어 있습니다. [Debian CVE 트래커의 설명](https://security-tracker.debian.org/tracker/CVE-2026-85046)[^2]
- 공격 상태: exploit in the wild(실제 악용) — 재현 코드가 공개되어 있느냐와 무관하게, 이미 누군가는 쓰고 있다는 신호입니다. [Chrome Releases 공지](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html)[^1]

보안팀이 패치 우선순위를 올리는 건 여기까지로도 충분합니다. 다만 조직 전체 패치 프로세스가 실제로 강제되는 지점은 “업데이트가 배포됨”이 아니라 “패치가 적용된 프로세스가 실행되기 시작함”입니다. 브라우저는 특히 그 경계가 뚜렷합니다.

## CVE-2026-85046이 말하는 공격 가능 범위: V8 타입 혼동과 ‘sandbox 내부 코드 실행’
이번 CVE는 V8의 타입 혼동(type confusion)이고, Chrome 152.0.7977.82 이전에서 “crafted HTML page”만으로 원격 공격자가 “sandbox 내부에서 임의 코드 실행”을 할 수 있다고 요약되어 있습니다. [Debian CVE 트래커](https://security-tracker.debian.org/tracker/CVE-2026-85046)[^2]

여기서 자주 헷갈리는 지점이 있습니다.

- “sandbox 내부에서 코드 실행”은 대개 renderer 프로세스(격리된 프로세스) 기준으로 이해하는 게 자연스럽습니다. 이 단계만으로도 계정 탈취, 세션 토큰 탈취, 브라우저 내 민감정보 접근 같은 2차 피해가 충분히 현실적입니다.
- 그러나 많은 조직이 더 크게 두려워하는 건 sandbox escape(권한 상승/브라우저 밖 탈출)입니다. 공지문은 escape 여부를 말하지 않습니다. 보통은 “in the wild”로 표시된 시점에는 상세를 아낍니다.

Chrome 릴리스 공지에는 “버그 상세/링크는 대다수 사용자가 업데이트할 때까지 제한될 수 있다”는 문장이 함께 붙습니다. 공격 난이도나 체인을 외부에서 역공학하기 어려운 상태를 유지하려는 전형적인 패턴입니다. [Chrome Releases 공지](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html)[^1]

이 지점부터 운영의 게임이 바뀝니다. “무슨 취약점인가”보다 “패치 적용이 느려지는 구조는 무엇인가”가 더 중요해집니다.

## 브라우저 업데이트에서 자주 놓치는 사실: 설치와 적용은 다르다
운영 현장에서 브라우저 패치가 늦어지는 가장 흔한 원인은 업데이트 배포 자체가 아니라, 사용자가 브라우저를 오래 켜 두는 습관입니다.

Chrome 업데이트는 대체로 다음 단계로 진행됩니다.

1) 백그라운드에서 새 버전이 다운로드/설치됨
2) “재시작하면 적용된다” 상태로 대기
3) 사용자가 relaunch(브라우저 재시작)해야 실행 중인 프로세스가 새 바이너리/새 엔진으로 교체됨

조직 입장에서 1)만으로는 위험이 거의 줄지 않습니다. 실제 공격은 “실행 중인 Chrome 프로세스가 취약한가”로 결정됩니다. 그리고 제로데이의 현실은 “업데이트 배포 후 며칠 동안은 취약 프로세스가 조직 내에 대량으로 잔류한다”는 데 있습니다.

Google이 Enterprise 문서에서 relaunch 정책을 별도 항목으로 다루는 이유도 여기에 있습니다. Chrome은 업데이트가 **pending update**인 상태에서 사용자에게 relaunch를 알리거나, 일정 시간이 지나면 강제 relaunch까지 할 수 있도록 정책을 제공합니다. [RelaunchNotification 정책 문서](https://chromeenterprise.google/policies/relaunch-notification/)[^3]

이 구조 때문에 브라우저 업데이트는 서버 패치와 다른 종류의 운영 장애를 만듭니다.

- 서버 패치는 “업데이트 자체”가 장애 위험(재시작, 커널 패치, connection drain)입니다.
- 브라우저 패치는 “업데이트를 미루는 것”이 장애 위험(보안 사고, 계정 침해, 랜섬웨어 확산의 초기 진입)입니다.

결국 브라우저 업데이트는, 보안팀이 아니라 운영팀의 언어로 말하면 운영 장애 예방 수단에 가깝습니다.

## ‘exploit in the wild’ 한 줄이 조직의 패치 프로세스를 강제하는 방식
“실제 악용”이 붙는 순간, 조직의 평상시 패치 원칙은 대부분 무력화됩니다. 평소에는 아래 이유로 브라우저 업데이트를 느슨하게 가져가는 팀이 많습니다.

- 새 버전이 특정 웹서비스(ERP, 그룹웨어, 보안 모듈)와 충돌할 수 있다.
- 재시작 강제는 업무 중단을 만든다.
- 롤아웃이 느리면, 천천히 모니터링하면서 가도 된다.

하지만 ‘exploit in the wild’는 위 논리를 뒤집습니다.

- 충돌 리스크는 “업데이트로 인한 일부 사용자 불편”의 문제인데,
- 제로데이 리스크는 “조직 전체 계정/단말이 동시에 털릴 수 있는 확률”의 문제입니다.

운영 의사결정이 여기서부터 달라집니다.

- 평상시: 기능/호환성 리스크 중심(서비스 오작동이 곧 장애)
- 제로데이: 침해 리스크 중심(브라우저 업데이트 지연이 곧 장애)

그리고 이 판단을 실제 액션으로 바꾸는 스위치가 정책(Policy)과 배포 링(Ring)입니다.

이 블로그에서 예전에 Chrome의 보안/정책/운영 관점을 다룬 글[^4]도 결론은 비슷했습니다. 모델/기능 자체보다 운영·정책·보안 체계가 최종 승부를 가릅니다. 그때는 AI 기능의 운영성이었고, 이번에는 제로데이가 운영을 흔듭니다.

## 롤아웃이 “며칠/몇 주” 걸린다는 문장이 의미하는 것: 링 배포를 다시 설계해야 하는 이유
Chrome Stable 공지는 “roll out over the coming days/weeks”를 반복해서 씁니다. 즉, 같은 Stable이라도 전 단말이 동시에 152.0.7977.82/.83을 받지 않습니다. [Chrome Releases 공지](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html)[^1]

이때 조직은 두 가지 선택지 사이에 놓입니다.

1) Google의 자연 롤아웃에 맡긴다.
- 장점: 갑작스러운 대규모 호환성 사고를 피한다.
- 단점: 제로데이 국면에서는 “취약 버전 잔류 기간”이 길어진다.

2) 조직 내부에서 배포를 앞당기는 장치를 쓴다.
- 장점: 잔류 기간을 압축한다.
- 단점: 업데이트·재시작으로 인한 사용자 불편이 즉시 표면화된다.

여기서 중요한 건 “링 배포”를 기능 배포처럼 다루면 망한다는 점입니다. 기능 배포는 A/B와 점진적 전환이 합리적이지만, 제로데이는 “노출 구간을 최대한 줄이는 것”이 목적입니다.

내 경우(서버/클라이언트 모두 운영해 본 입장)에는 링을 이렇게 재정의하는 편이 잘 맞았습니다.

- Ring 0: IT/보안팀 + 일부 power user(모니터링 인력이 즉시 대응 가능)
- Ring 1: 일반 사무직(업무 영향이 크지만, 치명적 호환성 이슈가 드물다)
- Ring 2: 콜센터/디자인/영업 등 상시 브라우저 사용 직군(재시작 타이밍이 중요)
- Ring 3: kiosk, VDI, shared PC, 공장/매장 단말(운영시간이 고정)

중요한 건 “누가 먼저 받나”가 아니라 “누가 언제 재시작 당하나”입니다. 브라우저 패치의 병목은 업데이트 설치보다 재시작이기 때문입니다.

## 강제 재시작을 ‘운영 룰’로 고정하는 지점: RelaunchNotification / Period / Window
제로데이에서 조직이 실제로 다루는 건 CVE보다 정책 3종 세트입니다.

- **RelaunchNotification**: relaunch 권고/필수(강제) 여부
- RelaunchNotificationPeriod: relaunch 유예 시간(기본 7일)
- RelaunchWindow: 강제 relaunch를 수행할 시간 창

Google의 정책 문서는 “Required로 설정하면 기간이 지나면 강제 relaunch 된다”고 명확히 씁니다. 기본 기간은 Chrome은 7일이며, 정책으로 변경 가능합니다. [RelaunchNotification 정책 문서](https://chromeenterprise.google/policies/relaunch-notification/)[^3]

관리 콘솔/문서에서도 “Force relaunch after a period”라는 표현으로 동일한 동작을 설명합니다. [pending update 재시작 알림 설정 가이드](https://support.google.com/chrome/a/answer/7679871?hl=en)[^5]

운영 관점에서 이 정책들이 강제하는 변화는 다음입니다.

1) 업데이트는 자동으로 들어가도 되지만, 적용은 자동으로 끝나지 않는다.
2) 적용을 자동으로 끝내려면 “강제 relaunch”를 조직이 감당해야 한다.
3) 강제 relaunch는 곧 운영 장애로 취급되기 쉬우니, 시간 창(RelaunchWindow)과 예외 정책이 필수다.

그리고 이 정책들이 특히 무서운 이유는, 제로데이가 한 번 터지면 “Required + 짧은 Period”가 표준이 되기 쉽다는 점입니다. 한 번 강제해 본 조직은 다음에도 그 룰을 재사용합니다.

### Linux(파일 정책) 예시: relaunch 강제 + 24시간 유예
Linux에서 Chrome 정책은 /etc/opt/chrome/policies/managed 아래 JSON으로 배포할 수 있습니다. [pending update 재시작 알림 설정 가이드](https://support.google.com/chrome/a/answer/7679871?hl=en)[^5]

예를 들어 24시간(86,400,000ms) 유예로 강제 relaunch를 걸면 다음 형태가 됩니다.

```json
// /etc/opt/chrome/policies/managed/relaunch.json
{
  "RelaunchNotification": 2,
  "RelaunchNotificationPeriod": 86400000
}
```

이 설정은 “업데이트가 설치됐는데 사용자가 브라우저를 안 껐다”라는 상태를 오래 끌지 못하게 만듭니다.

### Windows에서 update 자체를 막아둔 조직이 가장 위험하다: Google Update 정책
제로데이에서 종종 터지는 함정은 “Chrome은 설치되어 있는데 Google Update 정책이 꺼져 있는” 케이스입니다. 이 경우 사용자는 영원히 취약 버전을 유지합니다.

Windows에서는 Google Update(GPO)에서 업데이트 정책을 제어할 수 있고, 권장값은 Allow updates 입니다. 문서가 꽤 직설적으로 “업데이트를 끄는 건 권장하지 않으며, 보안 패치가 적용되지 않아 위험하다”고 말합니다. [Manage Chrome updates (Windows)](https://support.google.com/chrome/a/answer/6350036?hl=en)[^6]

이 문서가 중요한 이유는 “브라우저 업데이트 = 운영 장애 예방”이라는 프레임을 공식 문서가 사실상 인정하고 있기 때문입니다. 업데이트를 끄면 기능이 안정되는 게 아니라, 취약점/크래시가 누적된 상태로 운영이 이어집니다.

## 이번 주 안에 룰을 정리해야 하는 이유: 패치 우선순위 상향은 ‘버전’이 아니라 ‘재시작’이 목표다
2026-09-03 공지 이후, 조직이 실제로 달성해야 하는 목표는 보통 두 개입니다.

- 설치 버전이 152.0.7977.82 이상이 되게 할 것
- 실행 중인 Chrome 프로세스가 152.0.7977.82 이상이 되게 할 것

첫 번째는 배포 도구가 해결합니다.
두 번째는 운영 룰과 사용자 경험 설계가 해결합니다.

그리고 두 번째가 안 되면, 첫 번째는 의미가 약해집니다.

이때 제로데이 공지 한 줄이 강제하는 프로세스 변화는 대체로 아래 순서로 발생합니다.

1) 보안팀이 “긴급”을 선언한다(이미 in the wild).
2) IT가 auto-update를 더 공격적으로 만든다(체크 주기/업데이트 허용 정책).
3) 그래도 적용이 느리면 relaunch 강제로 넘어간다.
4) 강제 relaunch가 반발을 부르면, 시간 창과 예외(업무 중요 단말, kiosk, 발표용 PC)를 설계한다.
5) 정책 적용 여부를 측정하기 시작한다(버전 컴플라이언스).

이 흐름이 한 번 열리면, 이후에는 브라우저 패치가 서버 패치처럼 “SLO가 있는 운영 작업”으로 굳습니다.

## 실제로 동작하는 점검 코드: ‘최소 버전 미만 단말’을 배포 도구에 먹이기
현실적인 시나리오는 이렇습니다.

- Intune/SCCM/Jamf/스크립트로 “설치된 Chrome 버전”을 읽는다.
- 최소 버전(이번에는 152.0.7977.82)을 만족하지 않으면 비준수로 표시한다.
- 비준수 단말은 강제 업데이트 링으로 이동시키거나, 네트워크 접근 정책(조건부 접근)과 연동한다.

여기서 핵심은 “CVE를 이해하는 코드”가 아니라 “버전 비교를 정확히 하는 코드”입니다.

### Windows PowerShell: chrome.exe 파일 버전으로 컴플라이언스 판정
아래 스크립트는 Windows에서 일반적인 설치 경로의 chrome.exe ProductVersion을 읽고, 최소 버전과 비교해 exit code로 결과를 반환합니다.

- 의존성: Windows PowerShell 5.1+ 또는 PowerShell 7+
- 실행: 관리자 권한 불필요(읽기만)

```powershell
# Check-ChromeVersion.ps1
$Minimum = [version]"152.0.7977.82"

$Candidates = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe"
)

$ChromePath = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ChromePath) {
  Write-Host "ChromeNotInstalled"
  exit 2
}

$ActualString = (Get-Item $ChromePath).VersionInfo.ProductVersion
$Actual = [version]$ActualString

Write-Host "ChromePath=$ChromePath"
Write-Host "ChromeVersion=$Actual"
Write-Host "Minimum=$Minimum"

if ($Actual -lt $Minimum) {
  Write-Host "NonCompliant"
  exit 1
}

Write-Host "Compliant"
exit 0
```

예상 출력(취약 버전 예시):

```text
ChromePath=C:\Program Files\Google\Chrome\Application\chrome.exe
ChromeVersion=152.0.7977.76
Minimum=152.0.7977.82
NonCompliant
```

예상 출력(패치 완료):

```text
ChromePath=C:\Program Files\Google\Chrome\Application\chrome.exe
ChromeVersion=152.0.7977.83
Minimum=152.0.7977.82
Compliant
```

이 코드는 “업데이트가 설치되었는가”만 봅니다. “사용자가 재시작했는가”는 별도의 신호가 필요합니다. 조직에 따라서는 브라우저 프로세스의 실행 버전을 따로 수집하기도 합니다(EDR/자산 수집 도구가 흔히 제공합니다).

### Linux Bash: google-chrome --version 기반 판정
Linux는 배포판/패키징마다 다르지만, Chrome을 설치했다면 `google-chrome --version`이 통하는 경우가 많습니다.

```bash
#!/usr/bin/env bash
set -euo pipefail

MINIMUM="152.0.7977.82"

if ! command -v google-chrome >/dev/null 2>&1; then
  echo "ChromeNotInstalled"
  exit 2
fi

ACTUAL_RAW=$(google-chrome --version)  # e.g. "Google Chrome 152.0.7977.82"
ACTUAL=$(echo "$ACTUAL_RAW" | awk '{print $3}')

echo "ChromeVersion=$ACTUAL"

echo "$MINIMUM" | awk -v a="$ACTUAL" -F. '{print}' >/dev/null

# version compare using sort -V
LOWEST=$(printf "%s\n%s\n" "$MINIMUM" "$ACTUAL" | sort -V | head -n 1)
if [ "$LOWEST" != "$MINIMUM" ]; then
  echo "NonCompliant"
  exit 1
fi

echo "Compliant"
exit 0
```

이 수준의 점검만 있어도 “이번 주 안에 최소 버전으로 올렸다”는 보고는 자동화할 수 있습니다.

## 운영 장애 예방 관점에서의 정책 적용 포인트: 링 배포·강제 재시작·정책 검증
실무에서 제로데이 패치의 실패는 보통 “업데이트를 안 했다”가 아니라 “업데이트를 했는데도 취약 프로세스가 남았다”에서 시작합니다. 그래서 포인트가 세 군데로 갈립니다.

### 1) 링 배포: 업데이트 트래픽이 아니라 ‘재시작 충격’을 분산한다
서버의 링 배포는 트래픽/에러율을 보지만, 브라우저는 재시작이 업무에 미치는 충격을 봐야 합니다.

- 상시 업무용 브라우저는 2am 강제 relaunch가 오히려 안전합니다.
- 24시간 운영 콜센터는 오프라인 창구(교대 시간)에 맞춘 RelaunchWindow가 필요합니다.
- kiosk/공장 단말은 “업데이트는 받아도 실행은 안 바뀌는” 상태가 최악입니다. 무조건 창구를 만들어야 합니다.

문서에서도 relaunch window 설정이 업데이트 지연을 만들 수 있다고 경고합니다. 즉, 시간 창은 양날의 검입니다. [정책 설정 가이드](https://support.google.com/chrome/a/answer/2657289?hl=en_)[^7]

### 2) 강제 재시작: 강제의 목적은 사용자 통제가 아니라 ‘노출 구간 축소’다
강제 relaunch를 꺼리는 이유는 뻔합니다.

- 폼 입력/미저장 문서가 날아갈 수 있다.
- 수십 개 탭이 열려 있고, 복구가 스트레스다.

그럼에도 제로데이에서는 강제 relaunch가 등장합니다. 이때 운영 원칙은 “강제 횟수를 최소화하면서, 노출 구간은 짧게”입니다.

- Period를 무작정 1시간으로 줄이면 사용자 반발이 폭증합니다.
- Period를 7일로 두면 제로데이 대응이 아닙니다.

실무적으로는 24~72시간 구간이 많이 선택됩니다. 제로데이 대응에서 “이번 주 안에”라는 표현이 조직적으로 의미를 가지는 이유가 여기 있습니다.

### 3) 정책 검증: chrome://policy는 배포 완료 신호일 뿐이다
정책이 내려갔는지 확인하는 가장 확실한 UX는 `chrome://policy`입니다. Google 문서도 정책 적용 후 `chrome://policy`에서 Status=OK를 확인하라고 안내합니다. [pending update 재시작 알림 설정 가이드](https://support.google.com/chrome/a/answer/7679871?hl=en)[^5]

다만 이것도 “정책이 내려왔다”이지 “모든 사용자가 재시작했다”가 아닙니다.

- 정책 배포 → 정책 반영(브라우저 재시작 필요) → 업데이트 설치 → 업데이트 적용(재시작 필요)

브라우저는 재시작이 두 번이나 등장합니다. 운영팀이 체감하는 브라우저 패치의 어려움이 여기서 옵니다.

## 반론과 회의론: 강제 relaunch는 ‘업무 방해’가 아니라 ‘업무 보호’인가
강제 relaunch는 분명 사용자 경험을 망칠 수 있습니다. 특히 다음 환경에서는 더 위험합니다.

- 브라우저가 사실상 thin client(VDI, SaaS-only)인 조직
- 고객 응대/거래/결제 등 “브라우저 중단 = 즉시 매출 영향”인 조직
- SSO/보안 플러그인/사내 에이전트가 끼어 있는 복잡한 인증 체계

이때 회의론은 대체로 “브라우저 하나 때문에 왜 이렇게까지 하냐”로 표현됩니다.

그러나 제로데이에서 브라우저는 단순한 앱이 아닙니다.

- 사용자가 매일 들어가는 외부 입력의 수문장입니다.
- 조직 계정이 붙어 있고, MFA 세션이 붙어 있고, 중요한 SaaS가 다 붙어 있습니다.
- 감염의 시작점이 되면, 이후는 서버 패치/네트워크 분리로도 복구 비용이 커집니다.

즉 강제 relaunch의 목적은 “사용자 통제”가 아니라 “침해 대응 비용 폭발을 미리 방지”하는 것입니다. 운영 장애 예방이라는 관점에서 보면, 강제 relaunch는 장애를 만드는 행위가 아니라 장애를 막는 행위에 더 가깝습니다.

## 앞으로 지켜볼 것: 상세 공개 타이밍, 다운스트림 브라우저, 리포팅 체계
이번 공지는 정보가 제한적입니다. 그래서 운영팀이 지켜볼 포인트도 기술적 디테일보다 일정/파급입니다.

1) Chromium 이슈 트래커 제한 해제 타이밍
- “대다수 사용자가 업데이트할 때까지 제한”이라는 문장이 붙어 있으니, 며칠~몇 주 뒤에 더 많은 정보가 풀릴 수 있습니다. [Chrome Releases 공지](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html)[^1]

2) CVE 데이터베이스의 후속 정리
- Debian 트래커는 이미 요약을 제공하지만, 배포판 패치 적용은 별도의 시간 축으로 움직입니다. [Debian CVE 트래커](https://security-tracker.debian.org/tracker/CVE-2026-85046)[^2]

3) 테스트/자동화 환경의 버전 정합
- CI에서 Chrome을 다운로드해 쓰는 조직은 “Chrome for Testing” 쪽 버전도 함께 맞춰야 합니다. 현재 Stable이 152.0.7977.82로 올라와 있다는 건 자동화 파이프라인에서도 곧 이 버전을 받게 된다는 의미입니다. [Chrome for Testing availability](https://googlechromelabs.github.io/chrome-for-testing/)[^8]

4) update는 됐는데 relaunch가 안 된 단말의 잔류
- 이 잔류가 결국 사고 확률을 결정합니다. 그래서 제로데이 대응은 “배포율”보다 “재시작 완료율”을 지표로 삼는 편이 맞습니다.

## 결론: 브라우저 업데이트는 ‘업무 중단’이 아니라 ‘운영 장애 예방’으로 다뤄야 한다
CVE-2026-85046 자체의 디테일은 아직 제한적이지만, 운영에 필요한 사실은 이미 충분합니다. 2026-09-03에 Chrome 152.0.7977.82/.83이 배포됐고, V8 타입 혼동이 실제 악용 중이라고 Google이 명시했습니다. [Chrome Releases 공지](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html)[^1]

이 한 줄은 조직의 패치 프로세스를 다음처럼 강제합니다.

- 링 배포를 “천천히”가 아니라 “재시작 충격을 제어하면서 빨리”로 재설계하게 만든다.
- 업데이트 허용 정책(Google Update)과 적용 정책(RelaunchNotification)을 동시에 만지게 만든다.
- 브라우저 버전 컴플라이언스를 운영 지표로 끌어올린다.

제로데이 대응에서 브라우저는 더 이상 개인 앱이 아니라 조직 인프라의 일부입니다. 그래서 브라우저 업데이트는 기능 배포가 아니라 운영 장애 예방 작업으로 다루는 게 맞습니다.

## 참고 자료
- [Stable Channel Update for Desktop (2026-09-03)](https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html)
- [Debian Security Tracker: CVE-2026-85046](https://security-tracker.debian.org/tracker/CVE-2026-85046)
- [RelaunchNotification 정책 문서](https://chromeenterprise.google/policies/relaunch-notification/)
- [pending update 재시작 알림 설정 가이드](https://support.google.com/chrome/a/answer/7679871?hl=en)
- [정책 설정(관리 콘솔)에서 relaunch 알림을 더 공격적으로 만드는 옵션](https://support.google.com/chrome/a/answer/2657289?hl=en_)
- [Manage Chrome updates (Windows)](https://support.google.com/chrome/a/answer/6350036?hl=en)
- [Auto-update policies (Chrome Enterprise)](https://support.google.com/chrome/a/answer/9049675?hl=en)
- [Chrome for Testing availability](https://googlechromelabs.github.io/chrome-for-testing/)
- [Chromium Security](https://www.chromium.org/Home/chromium-security/)

[^1]: <https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html?amp=1>
[^2]: <https://security-tracker.debian.org/tracker/CVE-2026-85046>
[^3]: <https://chromeenterprise.google/intl/en_us/policies/relaunch-notification/>
[^4]: <https://daewooki.github.io/posts/codex-securityrsp-30gemini-in-chrome-202-1/>
[^5]: <https://support.google.com/chrome/a/answer/7679871?hl=en>
[^6]: <https://support.google.com/chrome/a/answer/6350036?hl=en>
[^7]: <https://support.google.com/chrome/a/answer/2657289?hl=en_>
[^8]: <https://googlechromelabs.github.io/chrome-for-testing/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
