---
title: "AWS Tools Installer V2로 개발자 머신과 CI의 AWS 툴 설치를 표준화하기"
description: "AWS CLI와 AWS Tools for PowerShell을 ‘공식 설치 루트’로 통일해 버전 드리프트와 재현성 문제를 줄이는 표준화 설계."
date: 2026-09-10 09:39:55 +0900
categories: ["Cloud", "AWS"]
tags: ["aws", "awscli", "powershell", "ci", "toolchain", "standardization"]
render_with_liquid: false
---

조직이 커질수록 AWS 관련 툴이 운영 리스크가 되는 지점은 대개 기능이 아니라 설치 방식입니다. 개인 노트북에서는 “일단 되면” 넘어가지만, CI와 운영 자동화로 넘어오면 설치의 불일치가 그대로 장애의 불일치로 번집니다. 특히 awscli는 경로(PATH) 충돌이 잦고, PowerShell 쪽은 모듈 버전이 어긋나면 로딩/Import 단계에서 미묘한 실패가 나옵니다.

이번 타이밍이 표준화를 걸기 좋은 이유는 두 축이 동시에 정리됐기 때문입니다.

- AWS Tools for PowerShell 쪽은 AWS.Tools.Installer V2가 GA로 올라오면서(공식 발표일 2026-08-04) 설치 성능/신뢰성과 함께 오프라인 설치, prerelease 설치, self-update 같은 운영 친화 기능이 정리됐습니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)에 V2의 변화가 구체적으로 적혀 있습니다.
- AWS CLI v2는 install script(install.sh / install.ps1)와 `aws update`를 함께 내면서 “공식 설치 루트”를 한 단계 단순화했습니다. (공식 블로그 2026-07-28) [AWS CLI 단일 명령 설치/업데이트 발표](https://aws.amazon.com/blogs/developer/installing-and-updating-the-aws-cli-with-single-line-commands/)와 [AWS CLI 설치 문서](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), 그리고 `aws update`의 제약을 적어둔 [update 커맨드 레퍼런스](https://docs.aws.amazon.com/cli/latest/reference/update/)를 같이 봐야 합니다.

사용자가 적어둔 “2026-09-02 GA”는 날짜가 섞였을 가능성이 큽니다. AWS Developer Tools Blog의 Announcements 목록을 보면 2026-09-02는 다른 글(예: S3 PowerShell Drive)이고, Tools Installer V2 GA 글은 2026-08-04로 표시됩니다. [Announcements 카테고리 목록](https://aws.amazon.com/blogs/developer/category/post-types/announcements/)에서 날짜를 직접 확인할 수 있습니다.

## “각자 설치한 awscli”가 왜 운영 리스크가 되는가
내가 여러 팀을 거치며 반복해서 봤던 패턴은 이렇습니다.

1) 개발자 A는 Windows에서 MSI로 설치했고, 개발자 B는 예전에 Python/pip로 설치한 awscli v1이 PATH 앞에 남아 있고, 개발자 C는 WSL에서만 awscli를 쓰고, CI는 컨테이너 이미지 안의 awscli를 씁니다. 이 상태에서 같은 `aws s3 sync`가 “되는 사람/안 되는 사람”이 생깁니다.

2) `aws --version`이 서로 다른 건 흔한데, 더 위험한 건 같은 버전처럼 보여도 설치 방식이 다르면 업데이트/롤백 루틴이 달라서 사고가 납니다. `aws update`는 공식 installer/install script로 설치된 케이스에서만 지원된다고 명시돼 있습니다. 즉, 설치 루트가 섞인 순간 업데이트 루트도 섞입니다. [update 레퍼런스](https://docs.aws.amazon.com/cli/latest/reference/update/)

3) PowerShell은 더 직접적으로 깨집니다. AWS.Tools는 서비스별 모듈이 쪼개져 있고, 설치/업데이트가 중간에 꼬이면 Common 모듈과 서비스 모듈 버전이 어긋나 Import 충돌을 만납니다. AWS.Tools.Installer 문서 자체가 “모듈 버전을 sync한다”는 점을 강조합니다. [AWS Tools for PowerShell 설치 문서](https://docs.aws.amazon.com/powershell/v5/userguide/ps-installing-awstools.html)

그래서 표준화의 목표는 단순합니다.

- awscli는 **공식 설치 스크립트/공식 installer로만 설치**되게 만들고, 그 외 경로(pip, distro package, 누군가가 받아둔 zip 수동 설치)는 조직 표준에서 제외합니다.
- PowerShell은 AWS.Tools.Installer V2를 기준으로 설치 루틴을 고정하고, legacy 모듈(AWSPowerShell 등)을 제거하는 방향으로 수렴시킵니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)

이 둘을 “개발자 노트북”과 “CI 이미지”에서 같은 방식으로 재현하는 것이 핵심입니다.

## AWS CLI v2: install script + aws update를 표준 루트로 고정
AWS CLI 설치 문서가 최근 흐름에서 분명히 바뀐 부분이 하나 있습니다. install script를 권장하고, 기본 설치 경로까지 정해줍니다.

- macOS/Linux: `curl -fsSL 'https://awscli.amazonaws.com/v2/install.sh' | bash`
  - 기본 설치: `$HOME/.local/share/aws-cli`
  - 기본 symlink: `$HOME/.local/bin`
  - system-wide는 `--system`으로 `/usr/local/aws-cli`, `/usr/local/bin`을 사용합니다. [AWS CLI 설치 문서](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

- Windows: `irm https://awscli.amazonaws.com/v2/install.ps1 | iex`
  - 기본 설치: `%LOCALAPPDATA%\Programs\Amazon\AWSCLIV2`
  - All users 설치는 `-System` 인자를 주고 Administrator 권한으로 실행하는 패턴을 문서가 제공합니다. [AWS CLI 설치 문서](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

업데이트는 2026-07-28 블로그에서 `aws update`를 함께 발표했고, 2.36.0부터 가능하다고 정리돼 있습니다. [AWS CLI 단일 명령 설치/업데이트 발표](https://aws.amazon.com/blogs/developer/installing-and-updating-the-aws-cli-with-single-line-commands/)

여기서 중요한 제약은 운영 설계에 영향을 줍니다.

- `aws update`는 “공식 installer/install script/update 커맨드 자체로 설치된 경우”에서만 지원됩니다.
- “source로 빌드한 배포”나 “container image 같은 다른 배포 메커니즘”은 지원하지 않는다고 못 박혀 있습니다. [update 레퍼런스](https://docs.aws.amazon.com/cli/latest/reference/update/)

즉, 개발자 노트북에서는 `aws update`가 표준 업데이트 루트가 될 수 있지만, CI가 컨테이너 기반이면 같은 방식의 업데이트를 기대하면 안 됩니다. CI는 업데이트가 아니라 이미지 교체(immutable)로 가는 게 일관됩니다.

## AWS Tools for PowerShell: Installer V2가 바꾼 운영 모델
AWS.Tools.Installer V2 GA 글은 V2의 성격을 분명하게 말합니다.

- V2는 다수의 개별 모듈을 하나씩 받는 대신, 단일 zip을 다운로드하고 병렬로 extract해서 설치 시간을 줄이고 신뢰성을 올립니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)
- 오프라인 설치: `-SourceZipPath`로 로컬에 스테이징한 zip에서 설치할 수 있습니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)
- prerelease 설치: `-Prerelease` 파라미터를 지원합니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)
- self-update: `Install-AWSToolsInstaller`, `Uninstall-AWSToolsInstaller`로 installer 모듈 자체 업데이트/제거를 지원합니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)
- 모듈 제거 표준화: metadata를 추가해 `Uninstall-Module` / `Uninstall-PSResource` 같은 표준 PowerShell 제거 루틴과의 궁합을 개선합니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)
- legacy 모듈 제거: AWSPowerShell / AWSPowerShell.NetCore를 PSModulePath 기준으로 cleanup하는 흐름이 들어갔고, 예시로 `Uninstall-AWSToolsModule -CleanUpLegacyScope 'CurrentUser'`가 제시됩니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)

그리고 설치/업데이트 시 모듈 버전을 sync하는 특성은 V5 문서에도 직접 적혀 있습니다. 하나를 올리면 나머지를 맞춰준다는 건 “편의성”이 아니라 “조직 표준화에서 강제력”으로 작동합니다. [AWS Tools for PowerShell 설치 문서](https://docs.aws.amazon.com/powershell/v5/userguide/ps-installing-awstools.html)

PowerShell Gallery 쪽을 보면 AWS.Tools.Installer 2.0.5가 2026-09-02에 게시된 것으로 표시됩니다. GA 발표(2026-08-04) 이후 실제로 패키지가 빠르게 업데이트되고 있다는 신호로 읽을 수 있습니다. [AWS.Tools.Installer 2.0.5](https://www.powershellgallery.com/packages/AWS.Tools.Installer/2.0.5)

## 버전 핀과 업데이트 채널을 “도구 기능”이 아니라 “조직 프로세스”로 설계
표준화 얘기에서 가장 많이 오해하는 지점이 업데이트 채널입니다. 도구가 apt처럼 stable/beta 채널을 제공하리라 기대하지만, 현실은 다릅니다.

- AWS CLI는 install script가 “최신”을 설치하는 것이 기본이고, `aws update`도 “최신”으로 올리는 기능입니다. 여기에는 조직이 흔히 원하는 “patch만 자동, minor는 수동” 같은 개념이 기본값으로 들어있지 않습니다. (문서/레퍼런스 어디에도 그런 채널 개념을 보장하지 않습니다.) [AWS CLI 단일 명령 설치/업데이트 발표](https://aws.amazon.com/blogs/developer/installing-and-updating-the-aws-cli-with-single-line-commands/)

- 반대로 AWS.Tools.Installer V2는 버전 핀에 대해 꽤 명확한 메시지를 줍니다. GA 글에서 `Install-AWSToolsModule -Version 5.*`로 minor 범위를 제한하라고 적어둡니다. “breaking changes 위험을 줄이기 위해 -Version을 추가하라”는 문장 자체가 운영 가이드입니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)

여기서 내가 선택하는 설계는 보통 2단계입니다.

### 1단계: 개발자 머신은 “공식 루트 + 느슨한 핀 + 정기 업데이트”
- awscli는 install script로만 설치하고, 업데이트는 월 1회 또는 분기 1회 같은 cadence로 “업데이트 윈도우”를 잡습니다.
- AWS.Tools는 `-Version 5.*`처럼 major 고정 + minor 이동 정도로 잡고, patch는 자동 정렬되게 둡니다.

이 설계는 사람/머신이 섞인 환경에서 운영 비용이 가장 낮습니다.

### 2단계: CI는 “이미지 고정 + 변경은 PR로만”
- CI에서 `aws update` 같은 런타임 업데이트는 재현성을 깨기 쉽습니다.
- CI는 base image를 만들고, 버전 변경은 PR로만 들어오게 해서 diff가 남도록 합니다.

AWS CLI 쪽에서 “container images는 update 지원 대상이 아니다”라고 적어둔 것도 같은 방향의 신호입니다. CI 컨테이너 안에서 업데이트를 기대하지 말고, 이미지 교체로 가는 것이 낫습니다. [update 레퍼런스](https://docs.aws.amazon.com/cli/latest/reference/update/)

## 개발자 노트북 표준화: PATH 충돌 제거부터 시작
개발자 환경에서 가장 값싼 효과는 “현재 실행되는 aws가 무엇인지”를 매번 확정하는 겁니다.

문제의 전형은 이겁니다.

- 설치는 새로 했는데 `aws --version`이 예전 버전을 가리킨다.
- Windows에서는 MSI 설치 위치가 여러 개 남거나, PATH 우선순위가 엉키는 일이 잦습니다.

AWS 쪽 오픈소스 문서(Agent Toolkit for AWS 설정 가이드)에도 이 증상이 직접 언급돼 있고, 해결로 `Get-Command aws -All`로 어떤 바이너리가 잡히는지 확인하라고 씁니다. [Agent Toolkit for AWS setup 문서](https://github.com/aws/agent-toolkit-for-aws/blob/main/setup-instructions/setup.md)

내가 팀에 깔아두는 표준 preflight는 아래 정도입니다.

### macOS/Linux preflight
```bash
set -euo pipefail

command -v aws >/dev/null || { echo "aws not found"; exit 1; }

echo "aws path: $(command -v aws)"
aws --version
```

### Windows preflight
```powershell
$ErrorActionPreference = 'Stop'

$cmds = Get-Command aws -All -ErrorAction SilentlyContinue
if (-not $cmds) {
  throw "aws not found"
}

"aws candidates:" | Write-Host
$cmds | ForEach-Object { "- $($_.Source)" } | Write-Host

aws --version
```

이걸 통과하지 못하면 설치 스크립트를 돌리더라도 “표준화”가 아니라 “또 하나의 설치”가 됩니다.

## 표준 설치 스크립트: 노트북과 CI에서 동일한 엔트리포인트를 만든다
표준화의 핵심은 한 줄 설치가 아니라 “조직이 책임지는 엔트리포인트”입니다. AWS가 제공하는 install script를 직접 개발자가 치게 두면, 결국 각자 shell history와 위키 문서가 진실이 됩니다.

내가 선호하는 형태는 저장소에 `scripts/bootstrap-aws-tools.*`를 두고, 여기만 공식으로 만드는 겁니다.

### (1) macOS/Linux: awscli 설치 + 검증
AWS 문서가 제시하는 설치 방식 그대로 가져가되, 조직 표준 경로를 강제하려면 XDG 변수를 명시합니다. 문서에 기본값과 변경 방법이 정리돼 있습니다. [AWS CLI 설치 문서](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

`scripts/bootstrap-awscli.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-user}" # user|system

if [[ "$MODE" == "system" ]]; then
  curl -fsSL 'https://awscli.amazonaws.com/v2/install.sh' | sudo bash -s -- --system
else
  export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
  export XDG_BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
  curl -fsSL 'https://awscli.amazonaws.com/v2/install.sh' | bash
fi

command -v aws
aws --version
```

예상 출력은 대략 아래 형태입니다(버전/OS 문자열은 환경마다 다릅니다).

```text
/Users/you/.local/bin/aws
aws-cli/2.xx.yy Python/3.11.z Darwin/... exe/... prompt/off
```

여기서 포인트는 “설치 위치를 정했다”가 아니라 “팀이 합의한 방식으로 설치하도록 한 파일을 repo에 고정했다”입니다.

### (2) Windows: awscli 설치 + All users 옵션
Windows는 문서에 아예 “스크립트를 파일로 내려받아 -System으로 실행하고 지운다” 패턴이 들어가 있습니다. 이건 기업 환경에서 감사/운영 관점으로도 좋은 형태입니다. [AWS CLI 설치 문서](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

`scripts/bootstrap-awscli.ps1`
```powershell
$ErrorActionPreference = 'Stop'

param(
  [ValidateSet('User','System')]
  [string]$Scope = 'User'
)

if ($Scope -eq 'User') {
  irm https://awscli.amazonaws.com/v2/install.ps1 | iex
} else {
  $tmp = Join-Path $env:TEMP 'awscli-install.ps1'
  irm 'https://awscli.amazonaws.com/v2/install.ps1' -OutFile $tmp
  try {
    & $tmp -System
  } finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
  }
}

aws --version
```

조직 표준을 “System 설치”로 갈지 “User 설치”로 갈지는 IT 정책과 충돌합니다. 나는 보통 아래처럼 나눕니다.

- 개발자 노트북: User 설치를 기본으로 두고, 보안 제품/권한 이슈를 피합니다.
- CI Windows runner/빌드 에이전트: System 설치로 고정해서 계정이 바뀌어도 도구가 유지되게 합니다.

### (3) PowerShell: AWS.Tools.Installer V2로 모듈 설치를 통일
공식 문서는 Windows/Linux/macOS 모두에서 `Install-Module -Name AWS.Tools.Installer` 후 `Install-AWSToolsModule ... -CleanUp` 패턴을 권장합니다. [Windows 설치 문서](https://docs.aws.amazon.com/powershell/v5/userguide/ps-installing-awstools.html) / [Linux/macOS 설치 문서](https://docs.aws.amazon.com/powershell/v5/userguide/install-aws.tools-on-linux-macos.html)

여기서 표준화 포인트는 두 가지입니다.

- 어떤 서비스 모듈을 “기본 툴체인”으로 볼 것인가
- 버전 핀을 어떻게 둘 것인가

예를 들어, 인프라 운영 자동화가 중심인 팀이라면 EC2/IAM/S3/STS/CloudFormation 정도는 기본으로 깔아도 됩니다.

`scripts/bootstrap-awstools.ps1`
```powershell
$ErrorActionPreference = 'Stop'

param(
  [ValidateSet('CurrentUser','AllUsers')]
  [string]$Scope = 'CurrentUser',

  # 조직 정책으로 major 고정. GA 글에서 5.* 예시가 제시됨
  [string]$ToolsVersion = '5.*'
)

# Installer 설치
Install-Module -Name AWS.Tools.Installer -Scope $Scope -Force

# 필요한 서비스 모듈 설치 + 버전 동기화 + 구버전 정리
Install-AWSToolsModule AWS.Tools.Common,AWS.Tools.S3,AWS.Tools.EC2,AWS.Tools.SecurityToken,AWS.Tools.IdentityManagement,AWS.Tools.CloudFormation -CleanUp -Version $ToolsVersion

# 설치 확인
Get-Module -ListAvailable AWS.Tools.Common | Sort-Object Version -Descending | Select-Object -First 1 | Format-List Name,Version,Path
```

`-Version 5.*` 패턴은 AWS Tools Installer V2 GA 글에서 “breaking changes 위험을 줄이기 위해 minor를 제한”하는 예시로 들어갑니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)

또 하나, V2에서 legacy 제거가 표준화에 중요한 이유는 “기존에 각자 설치해 둔 AWSPowerShell”이 남아 있는 조직이 많기 때문입니다. Installer V2 GA 글에 legacy 모듈 제거가 명시돼 있고 예시 커맨드도 들어 있습니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)

## CI 이미지/개발자 노트북 동기화: ‘같은 방식’과 ‘같은 결과’를 분리
동기화 전략을 세울 때 실수하기 쉬운 건 “개발자 노트북과 CI가 완전히 동일해야 한다”는 집착입니다. 현실적으로는 다음 둘 중 하나가 목적입니다.

- 같은 방식으로 설치된다 (설치 경로와 업데이트 경로가 동일)
- 같은 결과가 나온다 (버전이 동일)

둘 다 달성하면 좋지만 비용이 다릅니다.

### 같은 방식으로 설치: bootstrap 스크립트 단일화
위에서 만든 bootstrap 스크립트를 개발자와 CI가 동일하게 호출하게 만들면, 최소한 문제를 추적할 때 “설치 루트”가 단일해집니다.

- GitHub Actions/Linux runner라면 `bash scripts/bootstrap-awscli.sh system`처럼 호출
- Windows runner라면 `pwsh -File scripts/bootstrap-awscli.ps1 -Scope System` 형태
- PowerShell 모듈은 `pwsh -File scripts/bootstrap-awstools.ps1 -Scope AllUsers`처럼 호출

이 단계만 해도 “누가 pip로 깔았는지” 같은 논쟁이 줄어듭니다.

### 같은 결과(버전)까지 강제: CI는 이미지 교체로, 노트북은 느슨하게
CI에서 버전까지 강제하려면 결국 immutable artifact가 필요합니다.

- 컨테이너 기반 CI: base image를 만들고 그 안에 awscli를 설치한 뒤, 태그를 고정합니다.
- VM 기반 CI(Windows runner): AMI/이미지 빌드 파이프라인에서 awscli 설치 후 이미지 버전을 고정합니다.

여기서 `aws update`를 런타임에 돌리는 건 보통 손해입니다. 문서가 말하듯 `aws update`는 설치 루트가 특정 조건을 만족해야 하고, 컨테이너 이미지에 대해서는 지원하지 않는다고 명시돼 있습니다. [update 레퍼런스](https://docs.aws.amazon.com/cli/latest/reference/update/)

나는 CI에서는 업데이트를 실행하지 않고, “이미지 버전 업데이트 PR”을 만들게 하는 쪽으로 갑니다. PR에 들어가는 변경은 주로 두 가지뿐입니다.

- base image 태그 변경
- (PowerShell) AWS.Tools 설치 버전 정책 변경(예: `5.*` 유지, 또는 특정 minor로 더 좁힘)

## 오프라인/에어갭 환경: V2의 -SourceZipPath를 ‘중앙 배포’로 바꾸기
규제/보안 환경에서는 개발자 노트북이든 CI든 인터넷이 막혀 있는 경우가 있습니다. 이때 PowerShell 모듈 설치에서 가장 취약한 지점이 PSGallery 접근입니다.

Installer V2 GA 글은 `-SourceZipPath`를 오프라인 설치 지원으로 명시합니다. 즉, 조직이 zip를 내부에 스테이징해 두고, 설치는 그 경로를 참조하게 만드는 설계를 할 수 있습니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)

여기서 중요한 건 “오프라인을 지원한다”가 아니라 “배포 단위를 zip로 통제할 수 있다”는 점입니다. 사내 아티팩트 저장소(S3 + VPC endpoint, Nexus/Artifactory 등)에 올려두고, CI/노트북이 그걸 내려받게 만들면 PSGallery 장애나 외부 네트워크 정책에 덜 흔들립니다.

다만 이 글에서는 zip를 어디서 받아 어떤 해시로 검증할지를 단정하지 않습니다. 공식 글이 개념과 파라미터를 소개하는 수준이고, 조직 보안 정책에 따라 “어떤 저장소에 어떤 검증(서명/해시)을 붙일지”가 달라지기 때문입니다. 확실한 건 **V2가 그 경로를 열어줬다는 사실**입니다.

## 함정과 트레이드오프
표준화를 하면서 실제로 터지는 이슈는 설치 커맨드 자체보다 주변 조건입니다.

### awscli가 여러 개 잡히는 문제는 “설치 실패”가 아니라 “관측 실패”다
개발자들이 흔히 말하는 “설치했는데 안 됩니다”의 상당수는 설치가 아니라 PATH 우선순위 문제입니다. Windows에서는 특히 심하고, AWS 쪽 가이드에서도 “이전 설치가 다른 위치에 남아 PATH precedence를 가져간다”는 유형을 명시합니다. [Agent Toolkit for AWS setup 문서](https://github.com/aws/agent-toolkit-for-aws/blob/main/setup-instructions/setup.md)

표준화의 첫 단계는 설치가 아니라 `Get-Command aws -All` / `command -v aws`를 통과시키는 것입니다.

### PowerShell Gallery를 ‘신뢰’할지 말지는 조직이 결정해야 한다
AWS Tools for PowerShell 문서는 PSGallery를 trusted source로 취급하고 설치한다고 적고, 설치 시 untrusted prompt가 나오는 예시까지 보여줍니다. [Windows 설치 문서](https://docs.aws.amazon.com/powershell/v5/userguide/ps-installing-awstools.html)

개발자 개인 머신에서는 `-Force`로 넘어가기도 하지만, 기업 환경에서는 내부 mirror를 두고 승인된 패키지만 설치하도록 막는 경우가 많습니다. 이때 V2의 오프라인 설치 지원이 현실적인 해법이 됩니다.

### “업데이트 채널”은 도구가 아니라 운영이 만든다
AWS.Tools는 `-Prerelease`로 preview 빌드를 설치할 수 있다고 GA 글에서 명시합니다. [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)

이 기능은 강력하지만, 조직 표준에서는 기본값을 prerelease로 두면 안 됩니다. prerelease는 “별도 채널”이라기보다 “별도 위험”입니다.

내가 실제로 쓰는 패턴은 아래처럼 역할을 나누는 겁니다.

- 플랫폼/DevEx 팀: prerelease를 sandbox에서만 검증
- 일반 개발자/CI: stable만 사용

## 도입 판단 기준: 어디까지 표준화할 것인가
도입 결론은 조직의 크기와 CI의 형태에 따라 갈립니다.

- 개발자가 5명 미만이고 CI도 단순하면: awscli는 install script, PowerShell은 Installer V2 + `-Version 5.*` 정도만 걸어도 체감 효과가 큽니다.
- 팀이 여러 개로 나뉘고 Windows가 섞이면: preflight(경로 관측)와 legacy 제거까지 같이 해야 합니다. 그렇지 않으면 표준화가 아니라 “또 다른 설치 가이드”가 됩니다.
- CI가 컨테이너 중심이면: `aws update` 같은 런타임 업데이트에 기대지 말고, base image를 고정하고 교체하는 방식이 맞습니다. `aws update` 지원 범위가 제한적이라는 점은 문서에 분명히 적혀 있습니다. [update 레퍼런스](https://docs.aws.amazon.com/cli/latest/reference/update/)

내 경우 결론은 단순했습니다. 개발자 머신은 공식 설치 루트를 단일화해 drift를 줄이고, CI는 이미지 고정으로 재현성을 잡는 쪽이 비용 대비 효과가 가장 좋았습니다.

## 참고 자료
- [Announcements 카테고리 목록](https://aws.amazon.com/blogs/developer/category/post-types/announcements/)
- [AWS Tools Installer V2 GA 발표](https://aws.amazon.com/blogs/developer/aws-tools-installer-v2-is-now-generally-available/)
- [AWS Tools for PowerShell 설치 문서](https://docs.aws.amazon.com/powershell/v5/userguide/ps-installing-awstools.html)
- [Linux/macOS에서 AWS.Tools 설치 문서](https://docs.aws.amazon.com/powershell/v5/userguide/install-aws.tools-on-linux-macos.html)
- [AWS.Tools.Installer 2.0.5](https://www.powershellgallery.com/packages/AWS.Tools.Installer/2.0.5)
- [AWS CLI 단일 명령 설치/업데이트 발표](https://aws.amazon.com/blogs/developer/installing-and-updating-the-aws-cli-with-single-line-commands/)
- [AWS CLI 설치 문서](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- [update 커맨드 레퍼런스](https://docs.aws.amazon.com/cli/latest/reference/update/)
- [Agent Toolkit for AWS setup 문서](https://github.com/aws/agent-toolkit-for-aws/blob/main/setup-instructions/setup.md)
- [AWS가 ‘멀티클라우드’를 공식 제품으로 만들었다: 클라우드 신규 서비스 트렌드 분석](https://daewooki.github.io/posts/aws-2025-12-1/)
- [AI 에이전트·벡터·관측성으로 재편되는 클라우드 신서비스 전쟁: AWS re:Invent 이후판](https://daewooki.github.io/posts/ai-2025-12-aws-reinvent-1/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
