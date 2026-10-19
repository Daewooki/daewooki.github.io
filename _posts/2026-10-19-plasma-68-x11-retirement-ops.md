---
title: "KDE Plasma 6.8의 X11 세션 퇴역이 바꾸는 데스크톱 운영 전략"
description: "Wayland 전환의 핵심은 기능이 아니라 배포·드라이버·원격지원 런북이다. Plasma 6.8 이후 운영 계약이 달라진다."
date: 2026-10-19 10:02:25 +0900
categories: ["News", "Systems"]
tags: ["kde", "plasma-6-8", "wayland", "x11", "remote-desktop", "runbook"]
render_with_liquid: false
---

## 2026-10-14 Plasma 6.8 릴리스: 변화의 핵심은 “로그인 화면”이다
KDE는 2026년 10월 14일에 Plasma 6.8을 “30th Anniversary Edition”으로 공식 릴리스했습니다.[^1] 30주년 기념이라는 표면적 메시지보다, 운영 관점에서 더 큰 사건은 Plasma 자체의 X11 세션이 더 이상 제공되지 않는다는 흐름이 사실상 확정 단계로 들어갔다는 점입니다. (KDE 쪽에서는 2025년 말부터 “6.8은 Wayland-only”를 예고해 왔고, 2026년 중반에는 “6.8에서 로그인 화면에 X11 세션이 없다”는 형태로 더 구체화됐습니다.)[^2]

여기서 말하는 “X11 세션 퇴역”은 X11 앱이 당장 동작하지 않는다는 의미가 아닙니다. Plasma 팀이 계속 반복해서 강조하는 포인트는, Plasma가 X11 위에서 실행되는 **데스크톱 세션 자체를 더 이상 제공하지 않는다**는 뜻이고, XWayland를 통해 X11 앱은 계속 실행된다는 구분입니다.[^3]

운영자 입장에서 이 구분이 중요한 이유는 간단합니다.

- 기능 호환성(대부분의 앱은 돌아간다)보다 더 치명적인 실패는 “세션이 아예 안 뜨는” 상황입니다.
- 조직 단위 롤아웃에서 가장 위험한 구간은 배포 직후 첫 로그인, 그리고 원격 업그레이드 도중 화면이 끊기는 순간입니다.
- Wayland 전환의 실패는 기능 버그보다도 **드라이버/디스플레이 매니저/원격지원 채널 설계**에서 발생합니다.

Ars Technica도 이번 릴리스의 포인트를 “X11 farewell”로 정리하면서, X11 앱은 XWayland로 계속 실행된다는 선을 함께 그었습니다.[^4]

## “X11 마지막 지원”을 기능 이슈로 보면 놓치는 것
Wayland 이슈를 논할 때 흔히 떠올리는 건 IME, fractional scaling, 화면 공유, input emulation 같은 기능 단위 체크리스트입니다. 지금 타이밍(2026-10-19 KST 기준)에서 Plasma 6.8을 계기로 재정의해야 하는 건 다른 축입니다.

1) **세션 제공자의 변화**
- 과거: Plasma(X11)가 “데스크톱 세션 제공자”였고, X11은 그 기반 인프라였습니다.
- 이후: Plasma(Wayland)가 유일한 세션 제공자이고, X11은 XWayland로 “앱 호환 레이어”로만 남습니다.[^3]

2) **운영 계약(SLO/SLA)의 단위가 바뀜**
기능 검증은 보통 “특정 앱이 정상인가”로 끝납니다. 운영 계약은 “업그레이드 과정에서 원격으로 복구 가능한가”, “로그인 전/후에 지원 채널이 살아있는가”, “GPU 드라이버 교체 시 페일세이프가 있는가”로 정의됩니다.

3) **런북의 기본 가정이 깨짐**
X11 시절 런북은 너무 많은 걸 ‘당연’으로 두고 작성되었습니다.
- 로그인 전 상태에서 x11vnc 같은 도구로 화면을 붙는다
- 장애 시 DISPLAY를 잡고 xrandr로 화면을 살린다
- WM/컴포지터가 죽어도 X 서버에 최소한의 수단이 남는다

Wayland-only 세션에서는 이 가정이 그대로 유지되지 않습니다. 세션이 살아있어야, 포털/파이프라인/권한 모델이 의미를 갖습니다.

## Plasma 6.8에서 확인 가능한 “운영 친화적” 변화: Remote Desktop을 전면에 둠
KDE 공식 Plasma 6.8 발표문에서 눈에 띄는 건 Remote Desktop을 꽤 상단에서 다룬다는 점입니다. Plasma 내장 Remote Desktop 서버(현행 Wayland 세션 기반)에 대해 다음을 명시합니다.

- 느린 네트워크/빠르게 변하는 화면에 맞춰 latency와 responsiveness를 우선하는 품질 개선
- Exclusive mode: 서버 화면을 잠그고, 클라이언트 창 크기에 맞는 virtual screen 제공
- Bi-directional clipboard sync

이 내용은 KDE 공식 발표문에 그대로 들어가 있습니다.[^1]

또한 6.8 개발 과정에서 RDP 세션 종료 후 자동 lock 같은 운영 친화 기능을 다듬고 있다는 언급도 있었고, 로그인 매니저가 사용자별로 마지막 세션을 기억하는 개선도 함께 진행됐습니다. 이런 건 단순 UX가 아니라, “재부팅 후 재접속” 같은 원격지원 흐름에서 빈번히 만나는 마찰을 줄이는 조치입니다.[^5]

나는 KDE가 X11 세션을 내리는 타이밍에 맞춰 Remote Desktop을 전면으로 끌어올린 것이, 기술 방향성 선언이라기보다 운영 리스크를 줄이기 위한 보험 성격도 있다고 봅니다. Wayland는 보안 모델 때문에 “원격 제어/캡처”가 더 어렵고, 그래서 이 영역이 약하면 곧바로 엔터프라이즈 채택 장벽이 됩니다.

## 배포 관점에서 X11 세션 퇴역이 만드는 실패 모드
X11 세션이 사라졌다는 사실 자체보다, 그로 인해 “배포 후 어떤 실패 모드가 새로 생기고, 어떤 복구 루트가 막히는지”가 더 중요합니다.

### 1) 원격 업그레이드 중 GUI가 끊길 때, 되돌아갈 세션이 없다
원격에서 패키지 업그레이드를 하다가(특히 GPU driver, Mesa, KWin, Plasma workspace) 화면이 끊기는 건 흔한 사고입니다.

- 이전에는 “다시 접속해서 X11 세션으로 올린 다음 조치” 같은 우회로가 있었습니다.
- Plasma 6.8 이후에는 그 우회로가 “Plasma의 세션 선택지”로는 존재하지 않습니다. (다른 DE의 X11 세션을 따로 깔아서 우회하는 건 가능하지만, 그 자체가 이미 운영 정책 영역입니다.)[^3]

### 2) startkde/startplasma-x11 같은 진입점이 깨질 수 있다
Plasma 6.8 changelog에는 “Drop x11 session and startkde paths” 같은 항목이 명시돼 있습니다.[^6]

이건 다음과 같은 형태로 실제 사고를 만들 수 있습니다.

- 사내 이미지가 오래된 스크립트로 `startplasma-x11` 또는 `startkde` 계열을 호출
- kiosk/VDI 템플릿이 특정 .desktop 세션 파일을 하드코딩
- xinitrc/자동 로그인/실험용 세션 래퍼가 X11 경로를 가정

이류의 문제는 “기능 버그”가 아니라 “부팅/로그인 실패”로 나타납니다. 즉 장애 등급이 바로 올라갑니다.

### 3) 로그인 이전(pre-login)의 원격지원 채널을 재설계해야 한다
X11 환경에서는 greeter 이전/이후가 생각보다 매끄럽습니다. Wayland-only에서는 보통 다음 둘 중 하나를 선택해야 합니다.

- **로그인 전 원격지원은 SSH/시리얼/Out-of-band**로 제한하고, GUI 원격은 로그인 이후로 미룬다.
- 로그인 전에도 GUI가 필요하면, 그건 이제 “데스크톱 기능”이 아니라 “원격관리 제품/아키텍처”를 얹는 문제(Sunshine, vendor remote KVM, mesh agent, 하드웨어 KVM/IP 등)로 바뀝니다.

KDE 쪽에서도 headless/single-user 시나리오는 맞추겠지만, 다중 사용자 동시 접속 같은 서버형 요구는 당장 목표가 아니라고 선을 긋고 있습니다.[^7]

## 운영 계약으로서의 Wayland 전환: 체크리스트의 축을 바꿔야 한다
조직 롤아웃에서 “Wayland 기본 전환”은 다음 3개의 계약을 새로 맺는 일에 가깝습니다.

1) **Driver 계약**: 어떤 GPU/드라이버 조합을 지원 범위로 정할 것인가
2) **배포 계약**: 업그레이드/롤백/핀ning 전략을 어떻게 표준화할 것인가
3) **원격지원 계약**: 로그인 전/후를 포함한 원격 지원 루트를 무엇으로 고정할 것인가

Plasma 6.8이 X11 세션을 빼면서, 이 3개를 “선택사항”이 아니라 “필수 설계”로 만들었습니다.

아래는 기능 체크 대신 운영 체크로 재구성한 항목들입니다.

### Driver 계약: 최소 보장선을 정해야 한다
Wayland는 KMS/DRM 기반 스택에 훨씬 더 강하게 기대는 경향이 있고, GPU vendor 별로 리스크 프로파일이 다릅니다. 그래서 조직 단위에서는 “지원 GPU/드라이버 매트릭스”가 먼저 나와야 합니다.

- NVIDIA proprietary driver를 허용할 것인가, 허용한다면 어느 버전을 기준선으로 둘 것인가
- AMD/Intel은 어떤 커널 라인(배포판 커널 vs HWE/백포트)에서 고정할 것인가
- VM(virtio-gpu, vmwgfx)에서 Wayland 세션이 기본 운영 대상인지, 아니면 VDI는 별도 스택(xrdp+Xorg 등)으로 분리할 것인지

이때 중요한 건 “개별 사용자 불만 처리”가 아니라 “표준 이미지가 깨지지 않는 최소 기준”입니다.

### 배포 계약: 업그레이드는 GUI가 아니라 TTY/SSH를 기준으로 설계한다
내 경우 데스크톱 롤아웃을 운영할 때, GUI 업그레이드는 항상 실패한다는 전제로 잡습니다. Plasma 6.8 같은 전환기에는 더 그렇습니다.

- 원격 업그레이드는 기본적으로 SSH(또는 serial console, iDRAC/iLO 같은 OOB)로 수행
- 업그레이드 전에 “다음 부팅에서 자동 로그인/자동 시작이 정상인지”를 검증
- GUI가 죽어도 최소한 패키지 롤백을 넣을 수 있는 경로 확보

X11 세션이 있던 시절에는 “안 되면 X11로 부팅” 같은 애매한 우회가 있었지만, 이제는 그런 식의 기대를 문서에서 제거해야 합니다.

### 원격지원 계약: RDP/VNC/Portal/권한 모델을 인정하고 프로세스를 바꾼다
KDE는 Plasma 6.8에서 내장 Remote Desktop 서버 품질과 기능을 명시적으로 끌어올렸습니다.[^1] 여기서 운영자가 봐야 할 포인트는 기능 자체가 아니라, 이게 곧 “표준 지원 채널”이 될 가능성이 높다는 점입니다.

- 조직 표준: KRDC 같은 클라이언트 + Plasma 내장 서버를 표준으로 둘지
- 또는 Sunshine/Moonlight 같은 게임 스트리밍 계열을 원격지원 채널로 둘지
- 또는 아예 fleet 관리 에이전트(상용)로 전환할지

어느 쪽이든 Wayland에서는 “화면 캡처/입력 주입”이 OS/컴포지터 레벨 정책이므로, 개인별 편법(xdotool류)로 해결되는 영역이 줄어듭니다.

## 원격 업그레이드 런북: Plasma 6.8 이후 권장하는 절차(현실형)
아래 절차는 특정 배포판에 종속되지 않게 작성했지만, 핵심은 동일합니다.

- 업그레이드 행위 자체는 GUI 세션 밖(SSH/TTY)에서 한다
- 업그레이드 직후 “Wayland 세션이 실제로 뜨는지”를 확인한다
- 실패했을 때의 복구 루트는 미리 준비한다

### 1) 사전 점검(Preflight) 스크립트
아래는 현재 세션이 X11인지 Wayland인지, 원격 접속 경로가 SSH 기반으로 살아있는지, 그리고 다음 부팅에서 확인해야 할 로그 포인트를 정리해 주는 예시입니다.

```bash
#!/usr/bin/env bash
set -euo pipefail

say() { printf '\n[%s] %s\n' "$(date -Is)" "$*"; }

say "Session detection"
if [ -n "${XDG_SESSION_TYPE:-}" ]; then
  echo "XDG_SESSION_TYPE=$XDG_SESSION_TYPE"
fi
if [ -n "${WAYLAND_DISPLAY:-}" ]; then
  echo "WAYLAND_DISPLAY=$WAYLAND_DISPLAY"
fi
if [ -n "${DISPLAY:-}" ]; then
  echo "DISPLAY=$DISPLAY"
fi

say "loginctl"
loginctl show-session "${XDG_SESSION_ID:-self}" -p Type -p Remote -p State 2>/dev/null || true

say "GPU/DRM quick view"
ls -l /dev/dri 2>/dev/null || echo "/dev/dri not present"

say "KWin / Plasma binaries"
command -v kwin_wayland >/dev/null && echo "kwin_wayland: OK" || echo "kwin_wayland: MISSING"
command -v startplasma-wayland >/dev/null && echo "startplasma-wayland: OK" || echo "startplasma-wayland: MISSING"
command -v startplasma-x11 >/dev/null && echo "startplasma-x11: present (legacy)" || echo "startplasma-x11: not found (expected after 6.8)"

say "Remote access safety"
ss -lntp | awk 'NR==1 || /:22\b/' || true

say "Log pointers (use after reboot if GUI fails)"
echo "journalctl -b -u sddm --no-pager"
echo "journalctl -b --grep=kwin --no-pager"
echo "journalctl -b --grep=wayland --no-pager"
```

이 스크립트가 멋진 진단을 해주진 않습니다. 대신 업그레이드 운영에서 중요한 “상태를 기록”하게 만듭니다. 장애가 터졌을 때 필요한 건 영웅적인 디버깅이 아니라, 재현 가능한 타임라인입니다.

### 2) 업그레이드 실행은 TTY/SSH에서, 화면 공유는 끊어도 된다
원격지원 관점에서 가장 많이 하는 실수는 “GUI 원격 세션을 유지한 채로” 업그레이드를 진행하는 것입니다.

- Plasma/Qt/KWin을 올리는 순간, 원격 세션(특히 화면 캡처 기반)이 끊기는 건 정상입니다.
- 문제는 끊겼을 때 복구할 수 있느냐입니다.

그래서 런북에서 “원격 GUI 세션 유지”를 목표로 삼지 말고, “SSH 유지”를 목표로 삼는 게 안전합니다.

### 3) 업그레이드 직후 검증은 ‘앱’이 아니라 ‘세션’이다
Plasma 6.8 전환기에서 첫 번째 합격 기준은 다음입니다.

- 부팅 후 로그인 화면이 뜬다
- 로그인 후 Wayland 세션이 뜬다
- 최소한의 입력(키보드/마우스)과 출력(모니터)이 정상
- 원격지원 채널(RDP/VNC/상용 에이전트)이 정책대로 동작

여기까지 통과하면, 그 다음에야 앱 호환성으로 들어가도 됩니다.

## KDE가 남긴 안전판: XWayland 유지, LTS로의 회피로
KDE는 X11 세션을 내리면서도 다음 두 가지 안전판을 명시했습니다.

- XWayland는 계속 유지되며, X11 앱은(특수 케이스를 제외하면) 계속 실행된다.[^3]
- 정말로 X11 세션이 필요하면 LTS 배포판에서 구버전 Plasma를 유지하는 전략이 유효하다.[^2]

특히 KDE 블로그에서는 Plasma 6.8에서 X11 세션이 빠지는 시점(early 2027까지 지원될 수 있다는 당시 전망)과 함께, AlmaLinux 같은 장기 지원 배포판 예시까지 언급했습니다.[^2]

이 메시지는 개인 사용자에게는 “버티면 된다”로 읽히지만, 조직 운영자에게는 다른 의미입니다.

- 전환을 미루는 선택지가 공식적으로 정당화됐다
- 대신 미루는 동안 “보안 패치/브라우저/커널” 같은 다른 축의 업데이트 정책과 충돌할 수 있다

결국 LTS 회피는 기술적 선택이 아니라 비용/리스크 선택입니다.

## 반론과 회의론: X11이 제공하던 운영 편의가 실제로 있었다
X11은 오래됐고, 구조적으로 보안에 불리한 면이 있다는 평을 받아왔습니다. 하지만 운영 편의가 있었던 것도 사실입니다.

- 네트워크 투명성/원격 실행 개념은 X11 시절의 사고방식에 강하게 남아 있습니다.
- 스크립팅(특히 input emulation, window automation)에서 X11 도구 생태계는 여전히 크고, Wayland는 같은 방식의 접근을 의도적으로 막는 방향입니다.
- 장애 시 “일단 X가 뜨면 화면을 잡고 어떻게든 한다”는 복구 감각이 있었습니다.

Plasma 6.8이 X11 세션을 내리면서, 이런 운영 편의를 계속 쓰고 싶다면 이제 선택지는 둘 중 하나로 정리됩니다.

- KDE/Wayland의 공식 채널(Portal, compositor API, 내장 Remote Desktop)에 맞춰 런북을 재작성
- 또는 데스크톱 운영을 더 이상 “리눅스 데스크톱 패키지”로 해결하지 않고, VDI/원격지원 솔루션 계층을 별도로 도입

나는 이게 건강한 분리라고 봅니다. 다만 전자의 길을 택하면 각종 자동화 스크립트와 관성적 도구를 걷어내야 하고, 후자의 길을 택하면 비용이 듭니다.

## 앞으로 지켜볼 것: X11 코드 정리보다 무서운 건 ‘운영 공백’이다
Plasma 6.8에서 X11 세션이 빠진 이후, 기술적으로는 X11 관련 코드 정리가 진행될 겁니다. 이미 개발자 글에서는 “X11-specific code paths 제거” 같은 표현으로 방향을 명확히 했습니다.[^3]

운영 관점에서 더 중요한 관찰 포인트는 다음입니다.

- headless/원격지원이 “로그인 이후”에만 머무를지, 로그인 전 단계까지 확장될지
- 내장 Remote Desktop이 어느 정도까지 third-party(기업용) 요구사항을 흡수할지
- Union 같은 테마 엔진 통합이 데스크톱 표준 이미지(테마/브랜딩)를 운영하는 조직에 어떤 영향을 줄지

특히 Union은 Plasma 6.8에서 QtQuick뿐 아니라 QtWidgets까지 다루려는 방향이 명시돼 있고, 공식 발표문에서도 “Qt Widgets app까지 스타일링”을 강조합니다.[^1] 이건 UX 이야기처럼 보이지만, 조직 환경에서는 “표준 테마/표준 폰트/브랜딩” 유지 비용에 직결됩니다.

## 지금 할 수 있는 일: 기능 테스트 대신 운영 리허설을 해야 한다
Plasma 6.8의 X11 세션 퇴역을 계기로, Wayland 전환을 다음 순서로 다루는 게 현실적입니다.

1) **배포 단위로 드라이버 매트릭스를 확정**
- 최소 지원 GPU/드라이버 조합을 정하고, 예외 장비는 별도 풀로 분리합니다.

2) **원격지원 채널을 1개로 고정하고 런북을 강제**
- “각자 편한 원격툴”을 허용하면, 장애 시점에 복구 루트가 분산됩니다.
- KDE 내장 Remote Desktop을 쓸지, 다른 솔루션을 쓸지 결정하고 문서를 고정해야 합니다. Plasma 6.8이 Remote Desktop을 강화한 건, 내장 채널을 표준으로 만들 여지를 키운 사건입니다.[^1]

3) **업그레이드 리허설은 ‘원격 업그레이드’로 한다**
- 로컬에서 버튼 누르고 올리는 건 의미가 없습니다.
- SSH로 올리고, 일부러 GUI를 끊어보고, 복구까지 해봐야 합니다.

4) **세션 진입점 하드코딩을 제거**
- startplasma-x11, startkde 같은 레거시 호출이 남아 있으면 6.8 전환기에 바로 사고로 이어질 수 있습니다. changelog에 명시적으로 제거가 잡혀 있습니다.[^6]

결론적으로 Plasma 6.8은 Wayland 전환을 “기능 검증”에서 “운영 계약”으로 확정 짓는 릴리스입니다. 이제 남은 작업은 Wayland가 더 좋아지길 기다리는 게 아니라, 드라이버·배포·원격지원 런북을 팀 단위로 고정하는 일입니다.

## 참고 자료
- [Plasma 6.8 공식 발표](https://kde.org/announcements/plasma/6/6.8.0/)
- [Plasma 6.8.0 complete changelog](https://kde.org/announcements/changelogs/plasma/6/6.7.5-6.8.0/)
- [EX-11: Prepping for Plasma’s Last X11-Supported Release](https://planet.kde.org/david-edmundson-2026-06-02-ex-11-prepping-for-plasmas-last-x11-supported-release/)
- [Going all-in on a Wayland future](https://blogs.kde.org/2025/11/26/going-all-in-on-a-wayland-future/)
- [This Week in Plasma: Auto-Lock and Unlock for Remote Desktop Sessions](https://blogs.kde.org/2026/07/25/this-week-in-plasma-auto-lock-and-unlock-for-remote-desktop-sessions/)
- [This Week in Plasma: QtWidgets Apps Join the Union](https://blogs.kde.org/2026/08/28/this-week-in-plasma-qtwidgets-apps-join-the-union/)
- [KDE turns 30 with Plasma 6.8, remote upgrades, and an X11 farewell](https://arstechnica.com/gadgets/2026/10/kde-turns-30-with-plasma-6-8-remote-upgrades-and-an-x11-farewell/)
- [KDE/union repository](https://github.com/KDE/union)
- [Union: Summer 2026 Update](https://quantumproductions.info/articles/2026-08/union-summer-2026-update)

[^1]: <https://kde.org/announcements/plasma/6/6.8.0/>
[^2]: <https://blogs.kde.org/2025/11/26/going-all-in-on-a-wayland-future/>
[^3]: <https://planet.kde.org/david-edmundson-2026-06-02-ex-11-prepping-for-plasmas-last-x11-supported-release/>
[^4]: <https://arstechnica.com/gadgets/2026/10/kde-turns-30-with-plasma-6-8-remote-upgrades-and-an-x11-farewell/>
[^5]: <https://blogs.kde.org/2026/07/25/this-week-in-plasma-auto-lock-and-unlock-for-remote-desktop-sessions/>
[^6]: <https://kde.org/announcements/changelogs/plasma/6/6.7.5-6.8.0/>
[^7]: <https://planet.kde.org/david-edmundson-2026-08-25-whats-happening-in-kde-remote-desktop-improved-unattended-mode-and-more/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
