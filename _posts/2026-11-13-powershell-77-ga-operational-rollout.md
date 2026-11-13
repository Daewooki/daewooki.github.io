---
title: "PowerShell 7.7 GA: 운영 자동화 롤아웃 설계와 검증"
description: "PowerShell 7.7(.NET 11) 보안 하드닝·리모팅 변경으로 생길 회귀를 잡기 위한 검증 체크리스트와 롤아웃 링 정리."
date: 2026-11-13 15:03:31 +0900
categories: ["News", "Languages"]
tags: ["powershell", "dotnet-11", "remoting", "winrm", "ssh", "security-hardening"]
render_with_liquid: false
---

## 2026-11-10 PowerShell 7.7 GA 발표 내용 요약

PowerShell 팀은 2026년 11월 10일(미국 시간 표기 기준) PowerShell 7.7 GA를 발표했습니다. 이번 릴리스는 STS(Standard Term Support) 라인업이며, 런타임 기반이 .NET 11로 이동했습니다. 발표문이 강조하는 키워드는 세 가지였습니다. 보안 하드닝, 리모팅/엔진 신뢰성, 그리고 소수의 breaking change입니다.[^1]

운영 관점에서 바로 체크해야 하는 변화는 “새 기능”보다도 **안전해진 기본값과 검증 강화**가 만들 실패 모드입니다. 발표문에 적힌 보안 하드닝 항목만 보더라도 Constrained Language Mode 보호 강화, PowerShell remoting에서의 argument/frame validation 강화, CIM cmdlet의 schema validation 복구, updatable help 추출 시 validation 강화, Unix에서 fallback temporary home directory 권한 강화, `Test-Json`의 외부 schema 참조 기본 차단이 포함됩니다.[^1]

breaking change로는 `New-Guid` 기본값이 UUID v7로 바뀌고, `Format-*` 계열에서 `-Property` null/empty 검증이 강화되며, null/empty 검증 예외 타입이 `System.ArgumentException`으로 바뀌고, `Where-Object`의 `-EQ:$false` 같은 명시적 false 스위치 처리가 교정됩니다. 운영 스크립트는 이런 변경이 겉보기엔 사소해도, 예외 타입/메시지에 의존하는 리트라이·알림·파서가 있으면 사고로 이어집니다.[^1]

추가로 “업데이트 알림 기능 제거”가 들어갔습니다. 이건 기능 자체의 손익이 아니라, 조직의 배포 정책에 따라 “사용자가 알아서 올리는” 경로가 사라진다는 의미로 읽는 쪽이 안전합니다.[^1]

## .NET 11 기반 STS가 운영 정책에 주는 신호

PowerShell 7.7이 .NET 11 기반이라는 말은 단순히 성능/기능을 의미하지 않습니다. 운영팀이 책임져야 하는 것은 지원 종료일과 업데이트 주기, 그리고 보안 패치의 “당겨짐”입니다.

.NET 공식 지원 정책에 따르면 .NET 11은 2026년 11월 10일 릴리스된 STS이며, 지원 종료일은 2028년 11월 14일로 표기돼 있습니다.[^2]

PowerShell 지원 수명 주기 문서는 PowerShell의 end-of-support가 “그 PowerShell이 빌드된 .NET 버전의 지원 정책을 따른다”고 명시합니다. 즉, PowerShell 7.7을 조직의 표준 런타임으로 채택하는 순간, 달력 위에 2028년 11월이라는 날짜가 새로 생깁니다.[^3]

여기서 실무적으로 중요한 포인트는 두 가지입니다.

첫째, STS는 “품질이 낮은” 라인이 아니라 지원 기간이 짧은 라인입니다. .NET 쪽도 STS/LTS는 품질과 servicing 정책은 같고 지원 기간만 다르다고 설명합니다.[^4]

둘째, PowerShell 7.7은 STS이면서 동시에 .NET 11 STS 위에 얹혀 있습니다. PowerShell을 **운영용 런타임**으로 본다면, 이중으로 “빠른 이동”이 요구됩니다. 내 경험상 이런 타입의 업그레이드는 기능 검증보다 운영 프로세스(링, 관측, 롤백)가 먼저 잡혀 있어야 버틸 수 있습니다. 관련해서는 예전에 정리한 [.NET 11 GA 이후 메이저 런타임 업그레이드를 연 1회로 운영하는 법](https://daewooki.github.io/posts/dotnet-11-ga-annual-upgrade-operating-model/)에서 “캘린더 중심 운영”을 다뤘고, 이번에도 결론은 같습니다. 달력이 바뀌면 운영 모델이 바뀝니다.

## 보안 하드닝이 운영 스크립트에 만드는 회귀 지점

### Constrained Language Mode 강화: ‘보안 기능’이 아니라 ‘런타임 제약’

발표문에 “Constrained Language Mode 추가 보호(특히 non-core object에 대한 property assignment)”가 명시돼 있습니다.[^1]

Constrained Language Mode 자체는 PowerShell이 시스템 application control 정책 아래에서 자동으로 동작 모드를 낮추는 메커니즘이고, 현재 세션의 모드는 `$ExecutionContext.SessionState.LanguageMode`로 확인할 수 있습니다.[^5]

운영에서 이게 위험한 이유는, 대부분의 스크립트가 CLM을 ‘명시적으로 켜지’ 않기 때문입니다. WDAC/AppLocker 같은 정책이 켜진 서버/VDI/빌드 러너에서 갑자기 CLM이 걸리고, 그 상태에서만 터지는 코드가 생깁니다. 특히 다음 패턴들이 취약합니다.

- 외부 cmdlet이 반환한 객체(대개 non-core type) 위에 런타임에 속성을 덧씌우는 코드
- 파이프라인 중간에 계산용 필드를 심기 위해 `ForEach-Object { $_.X = ...; $_ }` 같은 형태를 쓰는 코드
- 암묵적으로 “추가 속성 주입이 가능하다”는 전제 아래, 이후 단계에서 그 속성을 참조하는 코드

이런 코드는 로컬 개발자 PC에서는 FullLanguage로 잘 돌아가고, 정책이 강한 서버에서만 폭발합니다. 따라서 7.7 검증은 “모든 환경에서 똑같이 돌려보기”가 아니라 “정책이 강한 환경을 대표 샘플로 확보하기”가 핵심입니다.

### `Test-Json` 기본 동작 변화: 외부 schema 참조가 막히는 쪽이 기본값

발표문에 따르면 `Test-Json`은 기본적으로 외부 schema reference를 resolve하지 않으며, 원할 때만 하도록 바뀌었습니다.[^1]

이 변화는 보안팀에게는 좋은 소식이지만, 운영 자동화에게는 회귀 포인트입니다.

- OpenAPI/JSON Schema 검증을 스크립트로 해두고 `$schema` 또는 `$ref`를 URL로 가리키는 경우
- 조직 내부 schema registry를 HTTP로 노출해두고, 배포 파이프라인에서 검증하는 경우
- 네트워크가 제한된 환경에서 “어차피 못 가져오니 실패해야 정상”이었던 파이프라인이, 7.7에서 갑자기 성공/실패 양상이 바뀌는 경우

여기서 교훈은 간단합니다. `Test-Json`을 쓰고 있다면 “외부 참조를 허용하는지”를 스크립트 레벨에서 명시해야 합니다. 런타임 기본값에 맡겨두면, 런타임 업그레이드가 정책 변경으로 번역됩니다.

### updatable help 추출 시 validation 강화: 프록시/미러 환경이 먼저 깨진다

PowerShell은 help를 업데이트 가능한 구조로 운영해 왔고, 발표문은 “updatable help 추출 시 stricter validation”을 명시합니다.[^1]

이건 대개 다음 환경에서 먼저 문제가 드러납니다.

- 프록시 뒤에서 `Update-Help`를 돌리는 서버
- 내부 mirror를 두고 help 컨텐츠를 캐시하는 환경
- 아예 인터넷 차단 환경에서 help 패키지를 별도로 가져와 배포하는 운영

조직에서 help 업데이트를 운영 표준에 포함시키는지 여부와 상관없이, “help가 깨졌을 때 PowerShell host가 뻗는가”는 신뢰성 이슈입니다. 7.7은 `powershell.config.json`이 손상돼도 시작이 막히지 않도록 바꿨다고도 했는데, 이런 류의 개선은 체감상 “운영 자동화 런타임”에 필요한 방향입니다.[^1]

## 리모팅/셸 신뢰성 변경이 드러나는 곳: WinRM, SSH, 그리고 PSRP

### WinRM(WSMan) 리모팅은 여전히 기본 모델이고, 포트/권한은 운영 현실이다

PowerShell remoting의 기본 전송은 WinRM(WS-Management)이며, 보안 문서는 기본 포트가 HTTP 5985 / HTTPS 5986이고, 기본적으로 Administrators 그룹에 대해서만 허용되는 점 등을 정리합니다.[^6]

7.7 발표문은 “PowerShell remoting에서 stronger argument and frame validation”을 명시합니다.[^1]

이 문장을 운영 관점으로 번역하면 이런 뜻입니다.

- 지금까지는 “이상한 입력(깨진 frame, 예상 밖 타입, boundary case)”이 들어와도 대충 통과했던 경로가 있었고
- 앞으로는 그게 더 빨리/명확하게 예외로 바뀔 가능성이 높다

즉, 원격 실행이 “조용히 이상하게 성공”하던 상태에서 “명확하게 실패”로 바뀌는 쪽이 기본값이 됩니다. 보안적으로는 선호되지만, 운영 자동화에서는 실패율이 갑자기 올라간 것으로 관측될 수 있습니다.

### SSH remoting은 멀티플랫폼의 현실적 해법이지만, 기능 격차가 존재한다

PowerShell remoting over SSH 문서는 WinRM이 기본이고 SSH가 멀티플랫폼 remoting을 가능하게 한다고 설명합니다. 동시에 SSH 기반 remoting은 WinRM이 제공하는 endpoint configuration 및 JEA를 현재 지원하지 않는다고도 못 박습니다.[^7]

조직에 Linux 대상 운영이 있거나, Windows라도 WinRM을 열기 어려운 네트워크 토폴로지라면 SSH remoting은 운영상 의미가 큽니다. 대신 7.7 검증 체크리스트에는 “SSH로 붙었을 때만 가능한 시나리오 / WinRM에서만 가능한 시나리오”를 분리해서 넣어야 합니다.

명령 레벨에서는 `New-PSSession`, `Enter-PSSession`, `Invoke-Command`가 SSH용 parameter set을 제공하며, `-SSHTransport` 또는 `-HostName` 중심으로 동작합니다.[^8]

### CIM cmdlet schema validation 복구는 ‘조용히 받아주던 입력’이 깨지는 변화다

발표문은 CIM cmdlet의 schema validation을 복구했다고 언급합니다.[^1]

이 변화는 다음 케이스에서 회귀로 등장하기 쉽습니다.

- 내부에서 CIM 호출을 래핑하는 모듈이 있고, payload를 느슨하게 만들어 보내던 경우
- 오래된 장비/에이전트가 표준에서 벗어난 응답을 보내는데, 지금까지는 파싱이 되던 경우
- 특정 벤더의 WMI/CIM 구현이 edge case에서 schema 위반을 하던 경우

“validation 강화”는 보통 ‘새 기능’이 아니라 ‘거짓 양성(success) 제거’입니다. 성공하던 게 실패로 바뀌는 쪽이 기본입니다.

## 호환성 검증 체크리스트: 사내 PowerShell을 런타임으로 다루기

여기서 말하는 호환성은 “문법이 돌아가냐”가 아니라, 사내 자동화 자산이 갖는 계약(입력/출력/실패 방식)이 유지되는지입니다. 체크리스트는 크게 스크립트/모듈/원격 실행/패키징으로 나눕니다.

### 1) 버전·지원 정책 체크: ‘언제까지 쓸 건지’부터 적는다

- PowerShell 7.7이 STS라는 점과 .NET 11 기반이라는 사실을 기록합니다.[^1]
- PowerShell의 end-of-support가 .NET 지원 정책을 따른다는 점을 운영 문서에 박아 둡니다.[^3]
- “조직 기본 PowerShell”을 7.6 LTS로 유지할지, 7.7로 당길지, 혹은 혼용할지 결정합니다. PowerShell 지원 수명 주기 문서는 LTS/Stable/Preview 구분과 현재 버전들을 안내합니다.[^3]

### 2) breaking change 직접 타격 구간 점검

발표문에 적힌 breaking change는 적지만, 운영 자동화는 보통 “소수의 스크립트”가 아니라 “수백/수천의 실행 지점”을 갖습니다. 아래는 실제로 검색을 걸어 회수할 만한 항목입니다.[^1]

- `New-Guid` 호출부: 생성된 GUID의 랜덤성에 의존하는 코드(예: shard 분산, 샘플링) 여부
- `Format-Table|Format-List|Format-Custom -Property`에 동적으로 배열을 만드는 코드: null/empty가 들어갈 수 있는지
- “null/empty validation 예외 타입”을 문자열로 비교하는 코드: `ArgumentException`으로 바뀌었는지 감안
- `Where-Object -EQ:$false` 같은 형태를 쓰는 필터: 기존 동작을 우회하고 있었는지

### 3) Constrained Language Mode 영향을 받는 코드 스캔

CLM 강화가 들어갔다는 사실 자체가 중요한 게 아니라, 조직 내에서 CLM이 실제로 걸리는 실행 지점이 어디인지가 중요합니다. 발표문은 non-core object property assignment 보호를 명시했고, language mode는 런타임에서 확인 가능합니다.[^1]

- WDAC/AppLocker 적용 서버, VDI, jump host, 빌드 러너를 목록화
- 그 지점에서 실행되는 PowerShell 작업(작업 스케줄러, 에이전트, 배포 도구)을 자산으로 매핑
- 스크립트/모듈에서 “객체에 속성을 주입하는 패턴”을 정적 검색

정적 검색은 완벽하지 않아도 효과가 있습니다. 특히 파이프라인 중간에 `$_`에 속성을 박아넣는 코드가 많은 조직은 여기서 꽤 많이 걸립니다.

### 4) WinRM 리모팅 호환성 체크

WinRM remoting은 포트/방화벽/권한/인증의 문제로 운영 환경에서 자주 깨집니다. 기본 포트와 기본 정책은 문서에 명확합니다.[^6]

7.7에서 remoting validation이 강화된다고 했으므로, 적어도 아래는 회귀 테스트로 고정하는 편이 안전합니다.[^1]

- `Invoke-Command`로 스크립트 블록 실행: 문자열 인자/배열/PSCustomObject 같은 자주 쓰는 입력 타입
- 파일 전송 패턴(예: `Copy-Item -ToSession` / `-FromSession` 사용 조직이라면)
- 원격 세션에서 `Clear-Host` 같은 콘솔 동작(7.7에서 수정 언급이 있음)[^1]
- CIM cmdlet 호출이 있는 자동화: schema validation 복구의 영향 가능성[^1]

### 5) SSH 리모팅 호환성 체크

SSH remoting 문서는 SSH 기반 remoting이 멀티플랫폼을 가능하게 하지만 WinRM 모델과 동일한 endpoint configuration/JEA를 제공하지 않는다고 밝힙니다.[^7]

조직이 SSH remoting을 쓰는 경우(또는 도입 예정인 경우) 다음을 별도 체크합니다.

- `New-PSSession -HostName` 기반 세션 생성과 인증(키/패스워드)
- 원격 PowerShell subsystem 경로: Windows OpenSSH의 subsystem 경로 제약 같은 운영 이슈(경로에 공백이 들어가면 문제)[^7]
- SSH 기반 remoting에서 “WinRM에서만 되던 기능”을 기대하는 코드가 있는지(대표적으로 JEA 설계)

### 6) Windows PowerShell 5.1 모듈 호환성(Compatibility feature) 점검

현실적으로 많은 조직은 아직 `%windir%\system32\WindowsPowerShell\v1.0\Modules` 안의 Windows PowerShell 5.1 모듈을 운영 자동화에서 사용합니다.

PowerShell 문서는 Windows PowerShell Compatibility 기능이 “PowerShell 7에서 Windows PowerShell 5.1 모듈을 background Windows PowerShell 5.1 프로세스(WinPSCompatSession)로 띄워 implicit remoting 방식으로 제공한다”고 설명합니다. 또한 `Import-Module -UseWindowsPowerShell`로 명시적으로 유도할 수 있다고도 정리합니다.[^9]

7.7에서 “implicit remoting protections이 resolved alias에도 적용”된다는 항목이 발표문에 포함돼 있기 때문에, Compatibility feature를 많이 쓰는 조직은 특히 이 축을 테스트로 잡아두는 편이 낫습니다.[^1]

### 7) 패키징/설치 채널별 차이를 운영 계약으로 만든다

GitHub 릴리스(v7.7.0)에는 Windows zip, msixbundle, 각종 Linux 패키지와 함께 sha256 목록이 함께 제공됩니다. 운영 환경에서 설치 채널이 여러 개라면(예: 서버는 zip 고정, 개발자 PC는 store/msix) 채널별 차이를 “허용된 변형”으로 문서화해야 합니다.[^10]

릴리스 노트에는 “Appx manifest를 업데이트해 PS7 실행 중 업데이트를 허용하지 않도록” 바꿨다는 항목도 들어가 있습니다. 이건 MSIX/스토어 계열로 설치하는 조직에서 롤아웃 타이밍과 충돌 가능성을 줄이는 방향이긴 한데, 반대로 말하면 설치 채널별로 동작이 조금씩 다르다는 증거이기도 합니다.[^11]

## 롤아웃 링 설계: ‘새 버전 배포’가 아니라 ‘런타임 교체’로 취급하기

내가 PowerShell을 운영용 런타임으로 본다는 말은, Python/Node/.NET 런타임처럼 “버전이 올라가면 코드가 깨질 수 있다”는 전제를 운영에 반영한다는 뜻입니다. 이 전제를 반영하면 롤아웃은 보통 아래 형태가 됩니다.

### 링 0: CI/검증 전용 런타임

- PowerShell 7.7을 “시스템 설치”가 아니라 “버전 고정된 portable runtime(zip/tar.gz)”로 내려받아 경로를 고정합니다. GitHub 릴리스는 Windows zip과 sha256 목록을 제공합니다.[^10]
- CI는 항상 `pwsh`를 PATH에서 찾지 않고, 지정된 절대 경로를 사용합니다.
- 여기서 실패하는 케이스는 운영 반영 전에 전부 소거하는 게 목표입니다.

### 링 1: 자동화 영향이 적은 내부 작업(비핵심 잡)

- 예: 사내 리포트 생성, 캐시 정리, 알림 집계처럼 “실패해도 복구 가능한” 잡
- 성공률/실패율, 평균 실행 시간, 원격 세션 생성 실패율 같은 지표를 붙여서 관측합니다.

### 링 2: 원격 실행이 많은 운영 잡(배포·패치·계정)

- WinRM/SSH 세션을 다루는 스크립트는 링 2에서 충분히 시간을 둡니다.
- remoting validation 강화는 “에러가 더 잘 드러나는” 쪽으로 기울 수 있으므로, 링 2에서 실패 패턴을 수집해야 합니다.[^1]

### 링 3: 개발자 워크스테이션/점프호스트 표준화

- 개발자 PC의 PowerShell은 스크립트 실행 환경이면서 동시에 도구 체인(PSResourceGet 등)입니다.
- 7.7은 PSResourceGet과 Archive 같은 모듈 업데이트를 포함한다고 했고, GitHub 릴리스 노트에는 PSResourceGet 업데이트가 포함돼 있습니다.[^1]
- 개발자 PC에 먼저 들어가면 “운영과 다른 런타임에서 스크립트를 작성하는” 역전이 발생합니다. 반대로 개발자 PC를 마지막에 두면 현장 마찰이 늘어납니다. 조직 상황에 맞춰 의식적으로 선택해야 합니다.

### 롤백은 기능이 아니라 설계다

런타임 업그레이드에서 롤백은 “패키지 삭제”가 아니라 “실행 경로 스위치”로 설계하는 편이 안전합니다.

- `pwsh` 호출을 래핑하는 스크립트/에이전트를 만들고, 버전을 config로 선택
- 원격 실행은 “클라이언트 런타임 업그레이드”와 “서버 endpoint 업그레이드”를 분리
- WinPSCompatSession(Windows PowerShell Compatibility)을 쓰는 경우, 5.1 프로세스 호출이 포함되므로 롤백 경로가 더 복잡해질 수 있다는 점을 감안[^9]

이 구조는 예전에 정리한 [WordPress 업그레이드 윈도우 TOCTOU RCE: 업데이트 순간을 공격면으로 보지 않기](https://daewooki.github.io/posts/wordpress-upgrade-window-rce-defense/)에서 말한 것과 같은 맥락입니다. 업그레이드 그 자체가 리스크 이벤트입니다.

## CI에서 굴리는 검증 하네스 예시: GitHub 릴리스 아티팩트 고정 + Pester

아래 예시는 “조직의 사내 스크립트/모듈 리포지토리”에 그대로 넣어 CI에서 돌리는 형태를 가정합니다.

- 설치 관리자는 필요 없습니다.
- GitHub 릴리스에서 아티팩트와 `hashes.sha256`를 받아 해시 검증을 합니다.
- 런타임 경로를 고정합니다.
- Pester로 breaking change 관련 회귀 테스트를 먼저 걸어둡니다.

PowerShell 7.7.0 릴리스에는 Windows용 `PowerShell-7.7.0-win-x64.zip`와 `hashes.sha256`가 제공됩니다.[^10]

### 리포지토리 구조

```text
repo/
  tools/
    Fetch-PowerShellRelease.ps1
    Use-Pwsh.ps1
  tests/
    BreakingChanges.Tests.ps1
  src/
    Corp.Automation/
      Corp.Automation.psd1
      Corp.Automation.psm1
```

### tools/Fetch-PowerShellRelease.ps1

- GitHub API로 릴리스 태그를 조회합니다.
- `hashes.sha256`와 원하는 런타임(zip)을 내려받습니다.
- sha256을 대조해 supply chain 리스크를 낮춥니다.

```powershell
[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [string]$Tag,              # 예: v7.7.0

  [Parameter(Mandatory)]
  [ValidateSet('win-x64','win-arm64')]
  [string]$Platform,

  [Parameter(Mandatory)]
  [string]$OutDir
)

$ErrorActionPreference = 'Stop'

$assetName = switch ($Platform) {
  'win-x64'   { 'PowerShell-7.7.0-win-x64.zip' }
  'win-arm64' { 'PowerShell-7.7.0-win-arm64.zip' }
}

# 1) 릴리스 메타데이터
$releaseApi = "https://api.github.com/repos/PowerShell/PowerShell/releases/tags/$Tag"
$release = Invoke-RestMethod -Uri $releaseApi -Headers @{ 'User-Agent' = 'corp-runtime-fetcher' }

# 2) assets에서 download URL 확보
$hashAsset = $release.assets | Where-Object name -eq 'hashes.sha256' | Select-Object -First 1
if (-not $hashAsset) {
  throw "hashes.sha256 asset not found in release $Tag"
}

$zipAsset = $release.assets | Where-Object name -eq $assetName | Select-Object -First 1
if (-not $zipAsset) {
  throw "runtime asset '$assetName' not found in release $Tag"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$hashPath = Join-Path $OutDir 'hashes.sha256'
$zipPath  = Join-Path $OutDir $assetName

Invoke-WebRequest -Uri $hashAsset.browser_download_url -OutFile $hashPath
Invoke-WebRequest -Uri $zipAsset.browser_download_url  -OutFile $zipPath

# 3) sha256 검증
$expected = (Get-Content $hashPath) |
  Where-Object { $_ -match [regex]::Escape($assetName) } |
  ForEach-Object {
    # 일반적으로 "<HASH>  <FILENAME>" 형식
    ($_ -split '\s+')[0]
  } |
  Select-Object -First 1

if (-not $expected) {
  throw "No hash entry found for $assetName in hashes.sha256"
}

$actual = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash
if ($actual.ToUpperInvariant() -ne $expected.ToUpperInvariant()) {
  throw "SHA256 mismatch. expected=$expected actual=$actual"
}

# 4) 압축 해제(버전 디렉토리 고정)
$versionDir = Join-Path $OutDir ($Tag.TrimStart('v'))
if (Test-Path $versionDir) { Remove-Item -Recurse -Force $versionDir }
New-Item -ItemType Directory -Force -Path $versionDir | Out-Null

Expand-Archive -Path $zipPath -DestinationPath $versionDir

$pwsh = Join-Path $versionDir 'pwsh.exe'
if (-not (Test-Path $pwsh)) {
  throw "pwsh.exe not found after extraction: $versionDir"
}

Write-Host "OK: $pwsh" -ForegroundColor Green
& $pwsh -NoLogo -NoProfile -Command '$PSVersionTable | Format-List PSVersion,PSEdition,GitCommitId'
```

위 스크립트는 “7.7.0 전용 파일명”으로 작성했습니다. 운영에서는 `$assetName`을 태그 기반으로 구성하거나, assets 목록에서 regex로 선택하는 형태로 일반화하는 편이 낫습니다.

### tools/Use-Pwsh.ps1

CI 단계에서 “어떤 pwsh로 테스트를 돌릴지”를 표준화하는 래퍼입니다.

```powershell
[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [string]$PwshPath,

  [Parameter(Mandatory)]
  [string]$ScriptPath,

  [Parameter(ValueFromRemainingArguments)]
  [string[]]$ScriptArgs
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $PwshPath)) { throw "pwsh not found: $PwshPath" }
if (-not (Test-Path $ScriptPath)) { throw "script not found: $ScriptPath" }

& $PwshPath -NoLogo -NoProfile -File $ScriptPath @ScriptArgs
exit $LASTEXITCODE
```

### tests/BreakingChanges.Tests.ps1

발표문에 적힌 breaking change 중 “운영 스크립트에 바로 영향을 주기 쉬운” 것들을 먼저 잠급니다.[^1]

```powershell
# Pester 5.x 기준
$ErrorActionPreference = 'Stop'

Describe 'PowerShell 7.7 breaking changes smoke tests' {

  It 'New-Guid should be UUID v7 by default (version nibble = 7)' {
    $g = New-Guid

    # GUID 버전은 3번째 그룹(4 hex) 첫 nibble에 들어감: xxxxxxxx-xxxx-Vxxx-....
    $parts = $g.Guid.Split('-')
    $versionNibble = $parts[2].Substring(0,1)

    $versionNibble | Should -Be '7'
  }

  It 'Format-Table -Property $null should throw ArgumentException' {
    { Get-Process | Select-Object -First 1 | Format-Table -Property $null } |
      Should -Throw -ExceptionType ([System.ArgumentException])
  }

  It 'Export-Csv should not accept -Append with -NoHeader' {
    $dir = Join-Path $TestDrive 'csv'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null

    $path = Join-Path $dir 'out.csv'

    [pscustomobject]@{ A = 1 } | Export-Csv -Path $path -NoTypeInformation

    { [pscustomobject]@{ A = 2 } | Export-Csv -Path $path -Append -NoHeader -NoTypeInformation } |
      Should -Throw
  }

  It 'Where-Object -EQ:$false should behave predictably' {
    # 의도: 명시적 false 스위치 처리가 교정됨.[^1]
    $xs = 1..5

    # 예시로 -eq를 명시적으로 $false로 주면 필터링이 꺼진 것처럼 동작하면 안 됨.
    # (여기서 정확한 기대값은 조직 코드에 맞춰 조정하는 편이 안전합니다.)
    $r = $xs | Where-Object -EQ:$false { $_ -eq 3 }

    # 최소한 “예외 없이” 동작하는지를 잠그는 수준의 스모크 테스트
    $r.Count | Should -BeGreaterThanOrEqual 0
  }
}
```

이 테스트는 ‘문서에 적힌 변화가 실제로 반영되었는지’를 빠르게 확인하는 용도입니다. 조직 자동화에서는 여기서 한 단계 더 가서 “우리 코드의 계약”을 테스트로 옮겨야 합니다. 예를 들면 GUID의 랜덤성이 필요한 워크로드라면 `New-Guid` 사용 금지 룰을 lint로 만들고, `[guid]::NewGuid()`로 강제하는 쪽이 낫습니다.[^1]

## 회의론과 반론: 실제로는 영향이 작을 수 있는 이유

이번 릴리스의 발표문은 “breaking change가 소수”라고 분명히 말합니다.[^1]

또, 7.7의 주요 변화가 보안 하드닝/validation 강화 쪽에 몰려 있다는 점은, 역설적으로 “정상 입력만 주고받는 조직”에서는 체감 회귀가 작을 수 있음을 의미합니다. remoting frame validation 같은 변경은, 오히려 기존에 묻혀 있던 비정상 상태(깨진 입력, 중간 프록시의 변형, 모듈의 잘못된 직렬화)를 더 빨리 실패로 만드는 쪽일 가능성이 큽니다.[^1]

즉, 다음 조건을 만족하면 위험은 상대적으로 낮습니다.

- 모든 운영 실행 지점이 FullLanguage이고, CLM이 걸리는 지점이 없다
- remoting을 거의 쓰지 않거나, 써도 단순 문자열/단일 값 위주다
- `Test-Json`을 외부 schema와 결합해 쓰지 않는다
- `Export-Csv`/`Format-*` 같은 포맷팅/리포트 스크립트가 운영 핵심 경로에 없다

다만 이 조건이 현실에서 자주 성립하지 않습니다. 특히 “운영 자동화”가 어느 정도 자라면 CSV/JSON은 어디에나 있고, remoting은 결국 들어갑니다.

## 앞으로 지켜볼 것: 7.7.x 패치와 문서 정리

1) Microsoft Learn의 “What’s New in PowerShell 7.7” 문서는 현재도 preview 기준 문구(예: 7.7.0-preview.5, .NET 11 rc runtime)를 포함하고 있습니다. GA가 나온 뒤에도 문서가 즉시 정리되지 않는 경우가 흔하므로, 조직 운영 문서는 발표문과 GitHub 릴리스 노트를 1차로 두는 편이 안전합니다.[^12]

2) PowerShell 7.7.0 GitHub 릴리스 노트에는 빌드/패키징 관점 변화가 함께 들어가 있습니다. 예를 들면 .NET SDK 11.0.100으로 업데이트, Appx manifest 업데이트 등이 그렇습니다. 설치 채널을 여러 개 운영하는 조직은 이 부분이 실제 장애 포인트가 됩니다.[^11]

3) .NET 11 자체도 이제 막 GA이므로, 11.0.1/11.0.2 같은 초기 servicing에서 런타임 레벨의 버그/회귀가 나올 수 있습니다. PowerShell 7.7을 “운영 표준”으로 넣는 순간, .NET 11 servicing에도 동기화됩니다. .NET 11이 STS이며 2년 지원이라는 점은 이 리듬을 예측하게 해줍니다.[^2]

## 이번 주에 잡을 만한 검증 계획(내가 실제로 적는 작업 항목)

- (자산) PowerShell 실행 지점 목록부터 업데이트합니다. 배포/운영 스크립트가 “어디서” 도는지 모르면, 릴리스 노트는 읽어도 소용이 없습니다.
- (샘플) CLM이 걸리는 대표 환경 1~2개를 확보합니다. 서버/VDI/러너 중 하나면 됩니다.
- (런타임) GitHub 릴리스 zip을 써서 7.7.0 runtime을 버전 디렉토리에 고정합니다. sha256 검증을 파이프라인에 포함합니다.[^10]
- (테스트) 발표문 breaking change 4개는 스모크 테스트로 먼저 잠급니다.[^1]
- (리모팅) WinRM 세션 생성/명령 실행/파일 전송(조직이 쓰는 경우)을 회귀 테스트로 고정합니다. 기본 포트/권한 모델을 다시 확인합니다.[^6]
- (SSH) SSH remoting을 쓰는 조직이라면, WinRM과 별도로 세션 생성/인증/서브시스템을 검증합니다. 문서가 언급하는 기능 격차(JEA/endpoint configuration 부재)를 운영 설계에서 재확인합니다.[^7]
- (호환) Windows PowerShell 5.1 모듈을 Compatibility feature로 쓰는 경우, WinPSCompatSession이 생성되는 경로를 테스트로 잡고, implicit remoting 관련 변화가 없는지 로그로 남깁니다.[^9]

결국 7.7 GA는 “PowerShell이 .NET 11 위로 올라갔다”보다 “보안 하드닝으로 인해 기존 자동화가 기대하던 느슨함이 줄어든다”가 핵심입니다. 운영 자동화는 느슨함 위에 쌓일수록 취약해지므로, 이번 업그레이드는 기능 검증보다 계약 검증과 링 설계가 먼저입니다.

## 참고 자료

- [Announcing PowerShell 7.7 GA Release](https://devblogs.microsoft.com/powershell/announcing-powershell-7-7/)
- [PowerShell v7.7.0 GitHub Release](https://github.com/PowerShell/PowerShell/releases/tag/v7.7.0)
- [.NET and .NET Core official support policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core)
- [Announcing .NET 11](https://devblogs.microsoft.com/dotnet/announcing-dotnet-11/)
- [PowerShell Support Lifecycle](https://learn.microsoft.com/en-us/powershell/scripting/install/powershell-support-lifecycle?view=powershell-7.6)
- [What’s New in PowerShell 7.7](https://learn.microsoft.com/en-us/powershell/scripting/whats-new/what-s-new-in-powershell-77?view=powershell-7.6)
- [PowerShell remoting over SSH](https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/ssh-remoting-in-powershell?view=powershell-7.5)
- [Security considerations for PowerShell Remoting using WinRM](https://learn.microsoft.com/en-us/powershell/scripting/learn/remoting/winrmsecurity?view=powershell-7.3)
- [about_Windows_PowerShell_Compatibility](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_windows_powershell_compatibility?view=powershell-7)
- [about_Language_Modes](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_language_modes?view=powershell-7.5)
- [.NET 11 GA 이후 메이저 런타임 업그레이드를 연 1회로 운영하는 법](https://daewooki.github.io/posts/dotnet-11-ga-annual-upgrade-operating-model/)
- [WordPress 업그레이드 윈도우 TOCTOU RCE: 업데이트 순간을 공격면으로 보지 않기](https://daewooki.github.io/posts/wordpress-upgrade-window-rce-defense/)

[^1]: <https://devblogs.microsoft.com/powershell/announcing-powershell-7-7/>
[^2]: <https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core>
[^3]: <https://learn.microsoft.com/en-us/powershell/scripting/install/powershell-support-lifecycle?view=powershell-7.6>
[^4]: <https://devblogs.microsoft.com/dotnet/announcing-dotnet-11/>
[^5]: <https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_language_modes?view=powershell-7.5>
[^6]: <https://learn.microsoft.com/en-us/powershell/scripting/learn/remoting/winrmsecurity?view=powershell-7.3>
[^7]: <https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/ssh-remoting-in-powershell?view=powershell-7.5>
[^8]: <https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/new-pssession?view=powershell-7.2>
[^9]: <https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_windows_powershell_compatibility?view=powershell-7.1>
[^10]: <https://github.com/PowerShell/PowerShell/releases/tag/v7.7.0>
[^11]: <https://github.com/PowerShell/PowerShell/releases>
[^12]: <https://learn.microsoft.com/en-us/powershell/scripting/whats-new/what-s-new-in-powershell-77?view=powershell-7.6>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
