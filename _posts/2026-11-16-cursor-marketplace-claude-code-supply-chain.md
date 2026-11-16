---
title: "Cursor 마켓플레이스 악성 Claude Code 확장 사고 분석"
description: "Fireworks AI 키 유출이 Cursor 마켓플레이스 캐시 침해로 이어지며 악성 Claude Code 확장이 배포됐다. 확장 공급망 방어 설계를 정리합니다."
date: 2026-11-16 11:23:40 +0900
categories: ["News", "Tools"]
tags: ["cursor", "vscode-extensions", "supply-chain", "incident-response", "ssh", "open-vsx"]
render_with_liquid: false
---

## 확인된 사실: 무엇이 일어났고, 언제까지였나

이번 사건은 한 문장으로 줄이면, **외부 벤더(추론/학습 인프라)의 키 유출 → IDE 확장 유통 채널(마켓플레이스 캐시) 변조 → 개발자 워크스테이션에 SSH 지속성(persistence) 심기**로 이어진 공급망 공격입니다.

Cursor가 공개한 2주 조사 결과 업데이트(게시일 2026-11-13) 기준으로, 공격 흐름은 다음처럼 정리됩니다. (언론 보도는 2026-11-14~15에 확산됐지만, 1차 소스에서 날짜를 먼저 잡는 게 맞습니다.)[^1]

- 2026-10-06: Fireworks가 내부 자격 증명 무단 사용을 탐지했고, 일부 고객 계정의 evaluation job 환경 변수에 접근이 있었다고 공지했습니다.[^2]
- 2026-10-29: Cursor의 VS Code extension marketplace에서 Anthropic.claude-code 확장(2.1.312 / 2.1.313) 변조본이 약 11시간 제공됐습니다. Cursor 공지 기준 노출 구간은 PT 02:27 ~ 13:35입니다.[^3]
  - KST로 환산하면(PT가 10월 말 기준 UTC-7로 동작한다고 가정) 대략 2026-10-29 18:27 KST ~ 2026-10-30 05:35 KST 구간입니다. Cursor 쪽도 UTC 기준으로 09:27~20:35로 표현하는 자료들이 많아, 이 창이 워크스테이션 조사에서 가장 중요한 시간축이 됩니다.[^4]
- 2026-10-30: Cursor는 IoC/점검/정리 스크립트를 포함한 보안 공지를 내고, 영향을 받은 사용자·팀 관리자에게 알림과 메일을 시작했다고 밝혔습니다.[^1]
- 2026-11-01: Cursor가 관측한 마지막 공격자 활동 시점이며, 이 활동은 차단됐다고 합니다.[^1]
- 2026-11-09: Fireworks는 10월 공지의 후속 업데이트에서, 조사 범위가 확장되며 account/billing 정보 영향, 일부 계정에서 secrets/datasets/미완성 모델 접근 등을 추가로 언급했습니다.[^5]
- 2026-11-13(업데이트 게시): Cursor는 Fireworks에서 노출된 키로 공유 버킷(read-only storage bucket) 데이터가 복사됐고, 그 안의 과거 coding agent traces(대부분 2025년) 일부에 redaction 되지 않은 credential이 섞여 있었으며, 그것을 발판으로 일부 SaaS 도구와 아카이브된 비프로덕션 소스 코드 저장소, 고객 지원 데이터 일부 등에 접근이 있었다고 밝혔습니다.[^1]

여기서 Cursor가 직접 못 박은 포인트가 하나 있습니다. 공격자가 Open VSX에 악성 확장을 올려서 퍼뜨린 게 아니라, Cursor가 확장을 서빙하는 캐시에 악성 копy를 직접 올렸고(Open VSX에는 악성 파일이 없었다)라는 주장입니다. 이건 확장 생태계를 공급망으로 볼 때 신뢰 경계(trust boundary)를 어디에 두어야 하는지를 바꿉니다.[^1]

## 공격 체인: 확장 하나가 워크스테이션 지속성이 되는 방식

Cursor의 10/29 공지는 악성 확장이 하는 일을 비교적 명확히 설명합니다. 호스트/유저 정보 수집 후, SSH backdoor 설치와 reverse SSH tunnel 시도, 그리고 그 지속성이 핵심입니다.[^3]

OpenSourceMalware, StepSecurity, Microsoft Security Blog 등 후속 분석에서 공통적으로 확인되는 행위는 다음과 같습니다.

- `~/.ssh/authorized_keys`에 공격자 키를 `svc-telemetry` 코멘트로 추가 (사용자 계정 SSH ingress 경로 확보)[^3]
- reverse SSH forwarding(`ssh -N -R '*:0:localhost:22'`) 패턴으로 외부 서버에 터널을 열어, 결과적으로 피해자 로컬 22번(ssh)로 들어오는 길을 만들려고 시도[^6]
- 외부 인프라(예: `134.209.82.225`)로의 통신 및 beacon 형태의 정보 보고[^6]
- OS별 지속성
  - macOS: `~/Library/LaunchAgents/com.apple.sysmond.plist` 및 `~/.config/.smt`, `~/.config/.smtk` 같은 아티팩트[^6]
  - Linux: `~/.config` 하위 파일 + crontab `@reboot` 지속성[^6]
  - Windows: Scheduled Task `SysMon` 시도, Startup folder 등[^6]

이 유형이 까다로운 이유는, 확장 자체를 제거해도 남는 게 많기 때문입니다. Cursor도 공지에서 uninstall만으로는 충분하지 않으며, 확장 외부에 떨어뜨린 persistence가 계속 동작할 수 있다고 적습니다.[^3]

StepSecurity 분석에서 눈여겨볼 만한 부분은, 주입(loader) 자체가 큰 프레임워크를 추가하는 방식이 아니라 매우 작은 덩어리를 앞에 끼워 넣어(수 KB 규모) 정상 코드 로딩은 계속되게 만들었다는 점입니다. 즉 기능적으로는 정상 확장처럼 보여서 사용자 체감 신호가 약합니다.[^7]

## 마켓플레이스 캐시/프록시 모델: 확장 유통 채널을 어디까지 신뢰할 것인가

Cursor 문서에는 Cursor가 Open VSX를 사용하지만, 검색/다운로드를 직접 passthrough하지 않고 자체 marketplace proxy(`marketplace.cursorapi.com`)를 통해 서빙하고, 거기서 악성코드/공급망 분석을 수행한다고 설명돼 있습니다.[^8]

이 구조는 보통 다음 목적을 위해 선택됩니다.

- 사용자/조직 관점: 짧게 올라왔다가 사라지는 악성 확장에 대해 완충 지대를 둔다(스캔·차단·쿨다운).
- 운영자 관점: 레지스트리(Open VSX) 장애나 품질 이슈를 프록시에서 흡수한다.

그런데 이번 사고는 이 프록시/캐시 계층이 곧 공급망의 단일 실패 지점이 될 수 있음을 보여줍니다. Cursor는 공격자가 Open VSX에 악성 확장을 올린 게 아니라, Cursor가 마켓플레이스를 서빙하는 캐시에 악성 копy를 직접 배치했다고 했습니다.[^1]

이 주장이 사실이라면 결론은 단순합니다.

- Open VSX의 namespace 검증/퍼블리셔 신원(verified/unverified), Open VSX가 제공하는 서명, 마켓플레이스 스캔 같은 레지스트리 레벨의 안전장치가, Cursor 사용자에게 도달하기 전에 우회됐습니다.
- 캐시는 더 이상 성능 최적화 계층이 아니라, 아티팩트 레포지토리(artifact repository) 그 자체로 취급해야 합니다.

즉, 캐시를 설계할 때도 CI/CD 아티팩트 저장소와 똑같이 다뤄야 합니다.

- write path 권한(누가 캐시에 쓸 수 있는가)
- immutability(한 번 올라간 버전이 수정 가능한가)
- provenance(이 VSIX가 어디에서 왔는가)
- integrity(이 VSIX가 서명/해시로 원본과 동일함이 증명되는가)

이 네 가지 중 하나라도 느슨하면, 공격자는 가장 값싼 credential 하나만으로도 사용자 단말까지 직행합니다.

## 서명과 검증: publisher identity만으로는 부족하고, repository signing만으로도 부족하다

확장 생태계에서 많이 착각하는 지점이 있습니다.

- verified publisher 뱃지가 있으면 안전할 것이다
- 마켓플레이스가 signing을 해주면 안전할 것이다

둘 다 절반만 맞습니다.

### 1) publisher identity는 소유권을 말해줄 뿐, 무결성을 보장하지 않는다

Open VSX는 namespace ownership/verification 개념이 있고, 특정 namespace가 verified인 경우 그 namespace에 publish 권한이 있는 사용자에 의해 배포된 버전을 verified로 마크한다고 설명합니다.[^9]

이건 impersonation 방지에는 유효하지만, 다음은 막지 못합니다.

- 퍼블리셔 계정 탈취
- 퍼블리셔 내부 CI에서 빌드 아티팩트가 오염
- 레지스트리를 거치지 않는 중간 유통 계층(프록시/캐시) 오염

이번 건은 (Cursor 주장대로라면) 마지막 케이스가 터진 겁니다.

### 2) repository signing은 유통 채널을 신뢰한다는 전제 위에서만 작동한다

VS Code 쪽은 오래전부터 repository signing을 밀어왔고, Visual Studio Marketplace가 확장을 서명하고 설치 시 검증한다는 접근이 문서로 공개돼 있습니다.[^10]

또 Microsoft는 마켓플레이스 운영 관점에서 악성 확장 스캔, 재스캔, 주기적 스캔 같은 방어 체계를 강조합니다.[^11]

문제는, 서명·검증의 신뢰 경계가 확장 파일을 내려받는 채널까지 포함한다는 점입니다. 즉, 사용자가 설치하는 확장이 Microsoft Marketplace CDN에서 내려오는 것이라는 전제가 흔들리면, repository signing의 의미가 훼손됩니다.

Cursor는 Open VSX를 upstream으로 쓰면서도 자체 프록시를 둡니다.[^8] 그리고 이번 사고는 바로 그 프록시/캐시가 공격 경로가 될 수 있음을 보여줍니다.[^1]

### 3) 그래서 클라이언트 쪽에서 서명 검증을 강제해야 한다

Cursor 문서에는 Enterprise 팀이 Open VSX extension signature verification을 강제할 수 있다고 적혀 있습니다.[^8]

여기서 중요한 관찰은, Cursor가 스스로도 install cooldown과 signature verification을 client-side install control로 정의하고, marketplace-layer 분석을 대체하지 않는다고 적어놨다는 점입니다.[^8]

나는 이 문장을 반대로 읽습니다.

- marketplace-layer 분석이 뚫릴 수 있다는 걸 운영자도 알고 있다.
- 그때 마지막 방어선은 클라이언트 설치 시점의 서명/무결성 검증이다.

이번 사건 유형에서는 특히 더 그렇습니다. 공격자가 캐시에 악성 VSIX를 심었다면, Open VSX의 서명 자산과 매칭되지 않습니다. 서명을 강제하면 설치가 실패해야 정상입니다.

## 워크스테이션 런북: SSH 지속성 제거는 체크리스트가 아니라 순서 문제다

Cursor 공지의 핵심은 `svc-telemetry` 키 존재 여부를 확인하라는 것입니다. macOS/Windows에 대해 단일 커맨드를 제공하고, 키가 발견되면 영향을 받은 것으로 봅니다.[^3]

여기서 실무적으로 중요한 건, 제거(run) 순서와 증거 수집 순서가 뒤집히면 안 된다는 점입니다.

1) 격리(네트워크 차단) → 2) 증거 수집(파일/프로세스/크론/태스크) → 3) 지속성 제거 → 4) 신뢰된 환경에서 credential rotation → 5) 재이미징/복구 판단

Cursor 공지에도 isolate, remove persistence, rotate credentials, rebuild 판단이 순서대로 들어가 있습니다.[^3]

아래는 내가 incident 대응에서 실제로 쓰는 형태로 정리한 로컬 점검 스크립트입니다. Cursor가 제공한 공식 스크립트를 우선으로 두되(공식 IoC/경로가 더 정확할 가능성이 큽니다), 조직 내부 런북에 그대로 옮기기 좋은 형태로 만들었습니다.[^3]

### macOS/Linux: svc-telemetry 및 대표 지속성 점검

```bash
#!/usr/bin/env bash
set -euo pipefail

# scan_svc_telemetry.sh
# 목적: Cursor marketplace 변조 건에서 알려진 대표 IoC(authorized_keys, LaunchAgent/cron, 프로세스)를 빠르게 확인

found=0

say() { printf '%s\n' "$*"; }
flag() { found=1; say "[FOUND] $*"; }

say "== authorized_keys check =="
AK="$HOME/.ssh/authorized_keys"
if [[ -f "$AK" ]] && grep -q "svc-telemetry" "$AK"; then
  flag "svc-telemetry entry in $AK"
else
  say "[OK] no svc-telemetry in $AK"
fi

say "== persistence file check (macOS/Linux common paths reported) =="
# OpenSourceMalware 분석에 언급된 파일들
# macOS: ~/.config/.smt ~/.config/.smtk ~/Library/LaunchAgents/com.apple.sysmond.plist
# Linux: ~/.config/.smt ~/.config/.smtk + crontab @reboot
for p in "$HOME/.config/.smt" "$HOME/.config/.smtk" "$HOME/Library/LaunchAgents/com.apple.sysmond.plist"; do
  if [[ -e "$p" ]]; then
    flag "persistence artifact exists: $p"
  else
    say "[OK] not exists: $p"
  fi
done

say "== cron check (Linux) =="
if command -v crontab >/dev/null 2>&1; then
  if crontab -l 2>/dev/null | grep -E "@reboot|\.smt" -n >/dev/null 2>&1; then
    flag "suspicious crontab entry contains '@reboot' or '.smt'"
    crontab -l 2>/dev/null | grep -E "@reboot|\.smt" -n || true
  else
    say "[OK] no suspicious crontab entry"
  fi
fi

say "== process / network indicator check =="
# 공격 인프라로 언급된 IP/패턴
if ps aux | grep -E "(autossh|ssh).*134\.209\.82\.225|134\.209\.82\.225:8099|svc-telemetry" | grep -v grep >/dev/null 2>&1; then
  flag "process references known indicators (134.209.82.225 / 8099 / svc-telemetry)"
  ps aux | grep -E "(autossh|ssh).*134\.209\.82\.225|134\.209\.82\.225:8099|svc-telemetry" | grep -v grep || true
else
  say "[OK] no suspicious process patterns found"
fi

say "== RESULT =="
if [[ "$found" -eq 1 ]]; then
  say "IMPACTED: artifacts found. Isolate host, collect evidence, then remove persistence and rotate credentials."
  exit 2
else
  say "CLEAN: no artifacts found by this quick scan."
  exit 0
fi
```

예상 출력은 단순합니다.

- 정상: `[OK] ...`만 나오고 `CLEAN`으로 끝납니다.
- 의심: 하나라도 잡히면 `IMPACTED`로 끝나며 exit code 2를 반환합니다.

위 스크립트가 의도적으로 보수적인 이유는, 이 공격의 본질이 IDE 확장 자체보다 SSH ingress 경로 확보이기 때문입니다. 확장은 설치 수단일 뿐이고, 남는 건 authorized_keys/LaunchAgent/cron/Task 같은 OS 레벨 지속성입니다.[^6]

### Windows: 빠른 점검(authorized_keys + Scheduled Task 힌트)

```powershell
# scan_svc_telemetry.ps1
$found = $false

Write-Host "== authorized_keys check =="
$files = @(
  "$HOME\.ssh\authorized_keys",
  "C:\ProgramData\ssh\administrators_authorized_keys"
) | Where-Object { Test-Path $_ }

if ($files.Count -gt 0 -and (Select-String -Path $files -Pattern "svc-telemetry" -Quiet)) {
  Write-Host "[FOUND] svc-telemetry key found in authorized_keys" -ForegroundColor Red
  $found = $true
} else {
  Write-Host "[OK] no svc-telemetry key found"
}

Write-Host "== scheduled task hint =="
try {
  $t = Get-ScheduledTask -TaskName "SysMon" -ErrorAction SilentlyContinue
  if ($null -ne $t) {
    Write-Host "[FOUND] ScheduledTask SysMon exists (review required)" -ForegroundColor Red
    $found = $true
  } else {
    Write-Host "[OK] ScheduledTask SysMon not found"
  }
} catch {
  Write-Host "[WARN] cannot query scheduled tasks: $($_.Exception.Message)"
}

Write-Host "== RESULT =="
if ($found) {
  Write-Host "IMPACTED: artifacts found. Isolate host, collect evidence, then remediate." -ForegroundColor Red
  exit 2
} else {
  Write-Host "CLEAN: no artifacts found by this quick scan." -ForegroundColor Green
  exit 0
}
```

Windows 경로/커맨드는 Cursor 공지가 제시한 authorized_keys 위치와 `svc-telemetry` 키 확인 방식과 맞춰 두었습니다.[^3]

### 제거(remediation)의 핵심: 키 삭제보다 먼저 할 일

1) 터널/SSH 프로세스가 살아 있는지(autossh/ssh) 확인하고, 네트워크를 끊은 뒤 증거를 확보합니다.
2) authorized_keys 라인을 지우는 것만으로 끝내면 안 됩니다. LaunchAgent/cron/Task/Startup 등 재주입(reinstall) 경로를 먼저 제거해야 합니다.[^6]
3) credential rotation은 감염 가능성이 있는 워크스테이션에서 하면 의미가 없습니다. Cursor 공지도 trusted system에서 rotate 하라고 명시합니다.[^3]

SSH backdoor 유형에서 내 경험상 가장 흔한 실패는, 키만 지우고 안심한 뒤 며칠 후 다시 심겨 있는 걸 발견하는 겁니다. 지속성이 남아 있으면 당연히 재발합니다.

## 조직 차원의 방어 설계: allowlist·해시 pinning·감사 로그를 현실적으로 묶기

Cursor 사고를 Cursor만의 문제로 보면 교훈이 작아집니다. 이번 사건은 에이전트/IDE 확장 생태계를 공급망으로 보는 쪽이 맞습니다.

조직 방어 관점에서 나는 3개의 층으로 나눠 설계합니다.

1) 설치를 막는다(allowlist)
2) 설치돼도 실행을 늦추거나 실패시킨다(cooldown, signature verification)
3) 그래도 실행되면 빨리 찾고 복구한다(telemetry, audit logs, endpoint runbook)

### 1) allowlist: 확장을 dependency처럼 취급하는 쪽이 결국 이긴다

Cursor의 Enterprise 가이드에는 Allowed Extensions(allowlist), install cooldown, signature verification이 함께 등장합니다.[^8]

현실적인 설계는 다음 정도가 상한선입니다.

- 팀 단위로 Allowed Extensions를 강제해서, 개인이 임의 확장을 설치하지 못하게 합니다.
- 예외는 업무적으로 꼭 필요한 것만, 그리고 publisher/extension ID를 동시에 좁힙니다.

여기서 중요한 건, allowlist는 보안팀이 단독으로 만들면 망한다는 점입니다. 개발 생산성을 박살내고 결국 우회가 생깁니다. 대신 분기별로 재검토하는 소유권 체계를 만듭니다.

- 플랫폼팀: 기본 베이스(언어/포맷터/린터) 패키지 유지
- 제품팀: 제품별 필수 확장 추가
- 보안팀: 신규 확장 심사(정적 분석 + 권한/네트워크 행위 확인) 프로세스 제공

Cursor 문서 자체도 “extension ID는 dependency처럼 취급하라”고 적습니다.[^8]

### 2) install cooldown: 짧은 시간 배포/철회형 공격에 강하다

Cursor는 Marketplace Install Cooldown을 팀 설정에서 fleet-wide로 강제할 수 있다고 설명합니다.[^12]

이번 사건처럼 노출 시간이 11시간 수준이면, cooldown을 24시간으로 걸어두는 것만으로도 조직 전체가 자동 설치/업데이트로 맞는 확률을 크게 줄일 수 있습니다. 다만 트레이드오프는 명확합니다.

- 장점: 단기 공급망 공격에 대한 완충
- 단점: 정상적인 보안 패치 확장도 하루 늦게 들어옴

내 경우 cooldown은 12~24시간 사이가 현실적이었습니다. 72시간을 넘기면 개발자가 체감하는 불편이 급격히 올라가고, 로컬 VSIX 설치 같은 우회가 나오기 시작합니다.

### 3) signature verification: 프록시/캐시가 오염될 때 마지막으로 버틴다

Cursor는 Open VSX extension signatures를 요구하도록 설정할 수 있다고 명시합니다.[^8]

이걸 켜면 어떤 일이 좋아지느냐가 중요한데, 바로 이번 같은 케이스입니다.

- upstream(Open VSX)이 정상이더라도
- Cursor 프록시/캐시가 변조되거나
- 중간 네트워크에서 VSIX가 바뀌더라도

클라이언트 설치 시점에서 서명이 맞지 않으면 설치가 깨져야 정상입니다.

Open VSX 자체도 registry가 서명한 패키지를 검증하는 `ovsx verify` 같은 도구를 제공합니다.[^13]

### 4) 해시 pinning: 기능이 아니라 운영 모델이다

많은 조직이 해시 pinning을 “어떤 기능을 켜면 된다”로 생각하는데, 실제로는 운영 모델입니다.

- 어떤 확장을
- 어떤 버전으로
- 어떤 해시로
- 누가 승인해서
- 어떻게 배포했는지

이 다섯 가지를 남기는 체계가 해시 pinning입니다.

Cursor가 이걸 네이티브로 제공한다는 의미는 아닙니다. 다만 나는 다음처럼 구현합니다.

- allowlist에 있는 확장만 설치 가능하게 막고
- 그 allowlist의 각 항목에 “허용 버전”과 “허용 해시(또는 서명 검증 필수)”를 붙이고
- MDM/로그온 스크립트/주기 작업으로 매일 설치 상태를 점검합니다.

VSIX는 zip이기 때문에, 조직 표준으로는 “VSIX 파일 SHA-256” 또는 “entrypoint 파일 SHA-256” 중 하나를 골라 pinning하면 됩니다. 이번 사건도 `extension.js` 해시를 IOC로 쓰는 접근이 널리 공유됐습니다.[^4]

이 모델의 단점은, 확장 업데이트가 느려지고 운영 비용이 든다는 겁니다. 장점은, 사고가 나면 조사 범위를 즉시 줄일 수 있다는 것입니다.

- 해시가 맞으면: 적어도 해당 공격(해시 기반 IOC)에 대해서는 배제 가능
- 해시가 틀리면: 즉시 격리/조사 대상으로 올림

### 5) 감사 로그: Cursor 로그만으로는 부족하고, OS 이벤트와 합쳐야 한다

Cursor Enterprise 가이드는 audit logs를 SIEM으로 스트리밍하고, OpenTelemetry export로 usage/activity telemetry를 외부 수집기로 보낼 수 있다고 설명합니다.[^14]

하지만 이번 사고의 핵심 행위는 OS 레벨(authorized_keys, LaunchAgent, cron, Scheduled Task)입니다. 따라서 로그 수집은 이렇게 나뉘어야 합니다.

- 컨트롤 플레인(IDE/팀 설정)
  - 누가 어떤 확장을 설치/업데이트했는지
  - 누가 allowlist/cooldown/signature verification을 변경했는지
- 데이터 플레인(워크스테이션)
  - `~/.ssh/authorized_keys` 변경 이벤트
  - LaunchAgent/cron/Task 생성 이벤트
  - `ssh/autossh` 프로세스 실행 + 외부로 나가는 터널링 패턴

Microsoft Security Blog도 hunting 관점에서 authorized_keys 확인과 extension 설치/업데이트 타이밍 추적을 강조합니다.[^15]

## 반론과 회의론: 결국 확장은 위험해서 못 쓴다는 주장에 대해

이 사건 이후 흔히 나오는 반응이 두 가지입니다.

1) IDE 확장/에이전트는 원래 위험해서 회사에서 쓰면 안 된다
2) 마켓플레이스는 뚫릴 수밖에 없으니 답이 없다

둘 다 일부는 맞지만, 운영 결론이 거기서 멈추면 조직은 매번 같은 유형으로 맞습니다.

- 확장은 이미 개발 워크플로의 일부입니다. VS Code 기반 IDE에서 확장 없이 일하자는 건, 브라우저 확장 없이 웹 개발하자는 이야기만큼 현실성이 떨어집니다.
- 마켓플레이스가 뚫릴 수 있다는 전제는 맞습니다. 그래서 클라이언트 검증과 조직 통제가 필요한 겁니다.

나는 이번 사건의 본질을 이렇게 봅니다.

- IDE/에이전트 확장은 소프트웨어 공급망의 말단이 아니라, 개발자 단말이라는 고가치 자산에 직접 닿는 최전선이다.
- 최전선은 prevention만으로 못 막는다. detection과 response를 같이 설계해야 한다.

Cursor도 스스로 shared responsibility를 강조하면서(플랫폼은 Cursor가 지키지만 구성과 채택은 조직 책임), 여러 방어층을 겹쳐야 한다고 문서에 적고 있습니다.[^14]

## 앞으로 지켜볼 것: Cursor/생태계에서 바뀌어야 하는 지점

Cursor가 11/13 업데이트에서 밝힌 후속 조치 중, 공급망 관점에서 의미 있는 건 다음입니다.

- Fireworks inference traffic을 옮기고, 노출된 키를 폐기했다[^1]
- credential rotation을 광범위하게 수행했다[^1]
- 마켓플레이스의 다른 확장들은 정상이었는지 검증하고 스토어를 리뷰·재구축했다[^1]

다만 이번 사건에서 구조적으로 확인해야 할 질문이 남습니다.

- 캐시에 직접 업로드할 수 있는 credential은 어떤 시스템에 있었나
- 캐시가 immutable하지 않았다면, 왜 그랬나
- 프록시/캐시가 upstream(Open VSX) 서명/해시와 동기 검증을 하는 구조였나

이 질문의 답에 따라, 다음 사고가 “또 다른 확장”에서 반복될지, 아니면 동일 유형이 봉쇄될지 갈립니다.

그리고 생태계 전반에서는, repository signing이든 registry signing이든 결국 마지막은 클라이언트 enforce입니다. Cursor가 제공하는 signature verification 강제 옵션은 이 방향과 정합적입니다.[^8]

## 지금 할 수 있는 일: 조직 런북 체크리스트

2026-11-16 KST 기준으로(사용자 요청 날짜), 지금 당장 할 수 있는 일은 과거 노출 구간(2026-10-29~10-30 KST)에 설치/업데이트가 있었는지에 집중하는 겁니다.

1) 설치/업데이트 타임라인 확보
- Cursor 사용자가 2026-10-29 18:27 KST ~ 2026-10-30 05:35 KST 사이에 Anthropic.claude-code 2.1.312 / 2.1.313을 설치 또는 업데이트했는지 확인합니다.[^3]

2) 1분 점검을 전 사용자에게 돌려서, impacted 후보를 빠르게 좁힙니다.
- `svc-telemetry` 키가 있으면 impacted로 간주하는 접근이 Cursor 공지의 기준입니다.[^3]

3) impacted는 즉시 격리하고, persistence를 찾아 제거합니다.
- uninstall만으로 부족할 수 있다는 경고를 그대로 받아들여야 합니다.[^3]

4) credential rotation은 신뢰된 장비에서 수행합니다.
- 특히 SSH key, GitHub/GitLab token, cloud credential은 우선순위가 높습니다.

5) 재이미징(reimage) 기준을 문서화합니다.
- SSH ingress가 열렸던 워크스테이션은, 공격자가 실제로 어떤 행위를 했는지 완전히 증명하기 어렵습니다. 이 불확실성을 어떻게 다룰지(재설치/포렌식/업무 영향)를 사전에 정해야, 사고 때 감정이 들어가지 않습니다.

6) 재발 방지 설정을 강제합니다.
- Allowed Extensions(allowlist)
- Marketplace Install Cooldown
- Require Extension Signature Verification

Cursor가 이 세 가지를 Enterprise 통제로 문서화해 둔 건, 이번 사건 이후 더 중요해졌습니다.[^8]

7) audit logs와 endpoint telemetry를 합칩니다.
- Cursor audit logs + OS 레벨 파일/프로세스 이벤트

이걸 합치면, 다음번에는 “어느 날 누가 이상한 확장을 설치했다”가 아니라 “정확히 어떤 확장이 어떤 해시로, 어떤 사용자에 의해, 어떤 노출 창에 설치됐고, 그 직후 어떤 persistence 이벤트가 발생했다”까지 한 번에 내려갈 수 있습니다.

에이전트/IDE 확장 생태계는 앞으로도 더 커지고, 그만큼 공급망 공격자는 더 싸게, 더 자주 시도할 겁니다. 이번 Cursor 사고는 그 공급망의 끝이 개발자 워크스테이션이라는 사실을 다시 확인시켰고, 결국 방어도 워크스테이션 런북과 조직 정책을 같이 설계하는 쪽으로 가는 게 맞습니다.

## 참고 자료

- Cursor: An update on our recent security incident[^1]
- Cursor: Security notice — malicious version of Anthropic.claude-code (2.1.312 and 2.1.313)[^3]
- BleepingComputer: Cursor confirms security breach led to malicious Claude Code extension[^16]
- The Hacker News: Stolen Fireworks AI key led to Cursor marketplace compromise[^17]
- Fireworks AI: Fireworks October 2026 security incident[^2]
- Fireworks AI: Update on October 2026 security incident[^5]
- Microsoft Security Blog: Inside a malicious Claude Code-branded extension and its persistent SSH backdoor[^18]
- OpenSourceMalware: Trojanized Claude Code Extension Plants an SSH Backdoor[^6]
- StepSecurity: Trojanized Claude Code Extension Delivered Persistent SSH Backdoor[^7]
- Cursor Docs: Extensions (Open VSX, proxy, cooldown, signature verification)[^8]
- Cursor Docs: Security and Privacy Hardening (audit logs, SIEM, OpenTelemetry)[^14]
- VS Code Updates v1.74: repository signing/verification 언급[^10]
- Microsoft Developer Blog: Security and Trust in Visual Studio Marketplace[^11]
- Eclipse Open VSX Wiki: Namespace Access (verified namespace)[^9]
- Eclipse Open VSX CLI: ovsx[^13]

[^1]: <https://cursor.com/blog/security-incident-update>
[^2]: <https://fireworks.ai/security/bulletins/october-2026-security-incident>
[^3]: <https://prod.cursor.com/blog/claude-code-extension-security-notice>
[^4]: <https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/10/CSA_research_note_cursor_marketplace_claude_code_extension_trojan_20261031-csa-styled.pdf>
[^5]: <https://fireworks.ai/security/bulletins/october-2026-security-incident-update?trk=public_post_comment-text>
[^6]: <https://opensourcemalware.com/blog/trojanized-claude-code-extension-plants-persistent-ssh-backdoor>
[^7]: <https://www.stepsecurity.io/blog/claude-code-extension-trojanized>
[^8]: <https://prod.cursor.com/help/customization/extensions>
[^9]: <https://github.com/eclipse-openvsx/openvsx/wiki/Namespace-Access>
[^10]: <https://code.visualstudio.com/updates/v1_74>
[^11]: <https://developer.microsoft.com/blog/security-and-trust-in-visual-studio-marketplace/>
[^12]: <https://cursor.com/help/customization/extensions>
[^13]: <https://github.com/eclipse-openvsx/openvsx/blob/main/cli/README.md>
[^14]: <https://prod.cursor.com/docs/enterprise/security-hardening>
[^15]: <https://www.microsoft.com/en-us/security/blog/2026/10/30/inside-malicious-claude-code-branded-cursor-extension-persistent-ssh-backdoor/?trk=public_post_comment-text>
[^16]: <https://www.bleepingcomputer.com/news/security/cursor-confirms-security-breach-led-to-malicious-claude-code-extension/>
[^17]: <https://thehackernews.com/2026/11/stolen-fireworks-ai-key-led-to-cursor.html?hl=en_GB&m=1>
[^18]: <https://www.microsoft.com/en-us/security/blog/2026/10/30/inside-malicious-claude-code-branded-cursor-extension-persistent-ssh-backdoor/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
