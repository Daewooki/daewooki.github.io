---
title: "Linux 7.2.6 stable 릴리스: 작은 패치가 운영에선 큰 리스크가 되는 이유"
description: "7.2.4→7.2.6처럼 촘촘한 stable 업데이트에서 회귀 탐지·롤백·NVIDIA 드라이버 상호작용을 운영 계약으로 정리합니다."
date: 2026-09-23 09:48:55 +0900
categories: ["News", "Systems"]
tags: ["linux", "linux-kernel", "stable", "regression", "canary-rollout", "nvidia"]
render_with_liquid: false
---

## 7.2.6이 나온 뒤, 바로 “체감 회귀”가 보고된 흐름

Linux 7.2.y stable 라인은 2026-09-07에 7.2.4, 2026-09-11에 7.2.5, 2026-09-14에 7.2.6이 태깅됐습니다. GitLab 미러의 태그 타임라인만 봐도 1주 안에 세 번 움직인 셈입니다. [linux-stable 태그 목록](https://gitlab.com/linux-kernel/stable/-/tags)에서 7.2.4/7.2.5/7.2.6 날짜가 그대로 보입니다.[^1]

7.2.6 자체는 Greg Kroah-Hartman이 2026-09-14 13:58:26 +0200에 릴리스를 공지했고(메일 본문에 “I’m announcing …” 형태), 7.2.y git tree 위치를 함께 안내했습니다. 운영자 입장에서는 이 메일이 “업스트림 stable이 공식적으로 굳었다”는 1차 신호입니다. [Linux 7.2.6 발표 메일(LWN 아카이브)](https://lwn.net/Articles/1093986/)에 날짜/Message-ID/대상 리스트가 정리돼 있습니다.[^2]

문제는 릴리스 직후입니다. 2026-09-16 전후로 커뮤니티에서 “전체 시스템이 버벅인다”, “스크롤이 stutter 난다”, “마우스 포인터까지 끊긴다” 같은 체감형 회귀 의심 보고가 곧바로 올라왔습니다. Void Linux 사용자가 7.2.4에서는 문제가 없었는데 7.2.6(그리고 NVIDIA 드라이버 버전 업)을 한 뒤 Firefox/Zed 스크롤과 포인터 이동까지 lag/stutter를 겪었다고 적었고, 같은 글에서 7.2.4로 부팅하면 정상이라고도 기록했습니다. 다만 글 말미에는 다음 날 재부팅 후에는 정상으로 돌아왔다고 편집돼 있어 원인 규명이 더 애매해집니다. [Void Linux: 7.2.6 stuttering/lagging 스레드](https://www.reddit.com/r/voidlinux/comments/1whjyik/linux_726_stutteringlagging/)가 그 사례입니다.[^3]

같은 시기, NVIDIA open GPU kernel modules 이슈 트래커에도 “특정 드라이버 버전에서 compositor 시작 시 hang” 같은 형태의 장애 리포트가 올라왔고, 리포트에는 커널 릴리스가 7.2.4-arch1-2와 7.2.6-arch2-1로 명시돼 있습니다. 여기는 stutter보다 더 강한 증상(멈춤/화면 깨짐)이지만, 운영 관점에서는 공통점이 하나 있습니다.

- stable 커널 마이너 업데이트 직후
- 그래픽 드라이버와 조합이 바뀐 상태에서
- “바로” 사람 손에 체감되는 이상이 튀어나옴

이게 운영에 위험한 이유는 단순합니다. 체감 회귀는 모니터링 그래프에서 잘 안 보이고, 한 번 터지면 “사용자 경험”을 즉시 깎아먹으며, 원인 분리가 어렵습니다. 그리고 하필이면 이런 류의 이슈가 이번 주(2026-09-23 KST 기준)처럼 롤아웃 윈도우에 걸리기 쉽습니다. 즉, 배포 일정과 “업스트림 stable 주기”가 충돌하면 사고 확률이 올라갑니다.

## stable 업데이트가 운영에서 ‘계약 변경’이 되는 순간

내가 stable 커널 업데이트를 **“패치 적용”이 아니라 “운영 계약 변경”**으로 보는 이유는 다음 3가지입니다.

첫째, 커널은 라이브러리와 달리 링크 타임 호환성으로 격리되지 않습니다. 같은 user-space라도 스케줄러/메모리/IO/드라이버 경계에서 결과가 흔들리면 서비스 SLO가 바뀝니다. 성능 회귀가 “버그가 아니다”라고 주장되는 순간, 운영자는 더 곤란해집니다. 장애가 아니라면 롤백 근거도 애매해지기 때문입니다.

둘째, stable은 “작은 패치의 집합”이지 “작은 변경”이 아닙니다. Linux stable 규칙 문서에는 패치 크기 기준(예: 100줄 제한 등)이 있고, upstream에 이미 존재해야 하며, 명백히 올바르고 테스트돼야 한다는 요건이 적혀 있습니다. 하지만 여기서 중요한 문장이 따로 있습니다.

stable 규칙 문서에는 “notable performance or interactivity issue”를 고치는 패치도 고려될 수 있지만, 이런 수정은 미묘한 회귀 위험이 더 크므로 배포판 커널 메인테이너가 제출하고 사용자 영향과 버그 링크를 덧붙여야 한다고 명시돼 있습니다. 즉, 업스트림도 “성능/인터랙션”은 위험도가 다르다는 것을 규칙 레벨에서 인정합니다. [Linux stable rules 문서](https://cdn.kernel.org/doc/html/latest/process/stable-kernel-rules.html)에서 해당 항목을 그대로 확인할 수 있습니다.[^4]

셋째, 커널 업데이트는 “리부트”를 동반합니다. 롤백도 리부트를 동반합니다. 애플리케이션 롤백과 다르게, 커널은 장애 순간에 원격 접속까지 잃을 수 있습니다. 그래서 “롤백이 가능하다”는 말은 운영 계약으로는 부족합니다. “롤백이 자동화되어 있고, 롤백 조건이 명시돼 있고, 롤백 후 상태 검증까지 정의돼 있다”가 계약 문장입니다.

이 관점에서 7.2.4→7.2.6 같은 촘촘한 stable 업데이트는, ‘릴리스 노트 한 줄’이 아니라 ‘계약서 부속 합의서’에 가깝습니다.

## 7.2.6은 정말 ‘작은 패치’였나: ChangeLog가 말해주는 변경량

릴리스 공지 메일(LWN 아카이브)을 보면 7.2.6에 포함된 파일 리스트가 매우 길게 이어집니다. 메일 본문은 단순하지만, 그 아래로 커밋/파일 변경이 쭉 나열됩니다. [Linux 7.2.6 발표 메일](https://lwn.net/Articles/1093986/)은 이 “길이 자체”가 운영자에게 힌트입니다.[^2]

더 직접적인 근거는 ChangeLog입니다. kernel.org(CDN)에는 7.2.6 ChangeLog가 plain text로 올라와 있고, 첫 커밋은 `Linux 7.2.6` 태그 커밋(500df175…)입니다. 그 바로 아래부터 수많은 backport 커밋이 이어집니다. [ChangeLog-7.2.6](https://cdn.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.2.6) 파일을 열어보면 첫 줄부터 릴리스 커밋/테스트 정보/서명과 함께 시작합니다.[^5]

커뮤니티에서는 “stable incremental patch도 생각보다 크다”는 관찰이 종종 나오는데, 7.2.5→7.2.6 incremental patch의 용량을 언급한 글도 있었습니다(바이트 단위 언급). 이런 수치는 과장으로 보일 수 있지만, ChangeLog가 수만 라인인 걸 한 번만 확인하면 “작은 패치”라는 직감이 왜 깨지는지 충분합니다. 또한 미러 디렉터리 인덱스에서도 ChangeLog-7.2.6가 MB 단위로 잡히는 것이 보입니다.[^6]

여기서 운영자가 착각하기 쉬운 포인트가 있습니다.

- 패치 “하나”는 작다.
- 하지만 stable 릴리스는 패치 “묶음”이다.
- 운영에서 리스크는 패치 크기보다 “경계 횡단 개수”에 비례한다.

7.2.6 ChangeLog 앞부분만 훑어도 `ksmbd`, `perf`, `ACPI` 등 서로 다른 영역이 섞여 들어옵니다. [ChangeLog-7.2.6](https://cdn.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.2.6)에서 실제 커밋 타이틀이 그렇게 흘러갑니다.[^5]

경계 횡단이 많아지면, 회귀의 형태는 두 갈래로 나타납니다.

- “명백한” 회귀: 부팅 실패, kernel panic, 특정 장치가 아예 인식 안 됨
- “체감형” 회귀: stutter, 입력 지연, frame pacing 불안정, suspend/resume 후 간헐적 버벅임

명백한 회귀는 빠르게 잡히지만, 체감형 회귀는 canary가 대표성을 못 가지면 놓칩니다. 7.2.6에서 실제로 논의가 나온 건 후자에 가깝습니다.

## NVIDIA(특히 DKMS)와 stable 커널 업데이트가 충돌하는 지점

NVIDIA는 운영에서 항상 “경계 조건”입니다. 이유는 간단합니다.

- 배포판이 제공하는 in-tree 드라이버와 달리 out-of-tree 모듈인 경우가 흔하고
- kernel headers/빌드 체인/서명/secure boot/lockdown 등 커널 바깥 요소에 얽히며
- Xorg/Wayland/compositor/DRM 설정과 결합해 “체감형”으로 터집니다.

이번 7.2.6 전후의 커뮤니티 사례도 그 전형을 따릅니다.

Void Linux 사례에서 사용자는 커널과 NVIDIA 드라이버를 함께 올린 뒤 stutter를 경험했고, 7.2.4로 내리면 정상이라고 적었습니다. 다만 이후 “다시 7.2.6으로 부팅했더니 정상”이라고 편집돼 있어, 원인이 커널인지 드라이버인지, 아니면 shader cache/컴포지터 설정/초기 로딩 타이밍인지 단정하기 어렵습니다. 이런 애매함이 바로 운영 리스크입니다. “재현이 안 된다”는 말은 “탐지 자동화가 어렵다”와 동의어가 됩니다.[^3]

NVIDIA open-gpu-kernel-modules 이슈는 조금 더 운영 친화적인 형태로 적혀 있습니다. 하드웨어(RTX 4060), 모니터 구성(DP 2대, 2560x1440@180), compositor(Hyprland), 드라이버 버전, 커널 릴리스(7.2.4/7.2.6)가 정리돼 있고, “특정 드라이버 버전에서는 hang, 이전 버전으로 내리면 해결” 같은 롤백 효과도 기록돼 있습니다. 커널과 드라이버는 서로 다른 축으로 움직이는데, 실제 장애는 “조합”에서만 나타나는 케이스가 많습니다. [NVIDIA open GPU kernel modules 이슈 #1367](https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1367)이 그 예입니다.[^7]

여기서 중요한 건 “NVIDIA가 문제다”가 아닙니다. 운영 계약 관점에서는 아래 문장을 계약서에 박아 넣어야 합니다.

- 커널 stable 업데이트는 NVIDIA 모듈 빌드/로딩/초기화 타이밍을 바꿀 수 있다.
- 드라이버 업데이트는 같은 커널에서도 증상을 바꿀 수 있다.
- 따라서 커널 롤아웃은 NVIDIA 드라이버 버전과 묶어서 승인하거나, 반대로 명시적으로 분리해서 승인해야 한다.

이걸 문서로 안 박아두면, 실제 사고가 났을 때 회고가 “왜 같이 올렸냐 / 왜 따로 올렸냐” 수준에서 끝납니다.

## stable-rc와 “짧은 간격 업데이트”가 의미하는 것

stable은 종종 `stable-review`(rc) 형태로 리뷰 큐를 먼저 공개합니다. 7.2.6도 review 메일/아카이브가 존재하고, 그 안에는 stable-review 패치 번들 위치와 linux-stable-rc.git 같은 정보가 등장합니다. [LKML 아카이브의 7.2.6-rc1 review 관련 메일](https://lkml.iu.edu/2609.1/12896.html)처럼, 운영자는 “정식 릴리스 전에 이미 큐가 굴러가고 있다”는 사실을 파악할 수 있습니다.[^8]

이게 운영에서 중요한 이유는 하나입니다.

- 정식 stable 릴리스 공지를 보고 준비를 시작하면 늦다.

특히 7.2.4→7.2.6처럼 간격이 짧으면, 배포판이 stable을 흡수하는 속도도 빨라집니다. 예를 들어 Debian 쪽에서도 7.2.6 소스 패키지가 unstable로 들어가는 흐름이 공개적으로 기록됩니다. 이런 기록은 “이번 커널은 금방 각 배포판 채널로 흘러 들어가겠구나”를 예측하게 해 줍니다. [Debian unstable로 linux 7.2.6-1 accepted](https://tracker.debian.org/news/1799140/accepted-linux-726-1-source-into-unstable/) 같은 트래커 공지가 그 신호입니다.[^9]

업스트림에서 7.2.6이 2026-09-14에 태깅되고 공지된 뒤, kernel.org의 “Latest Release” 페이지는 이후 7.2.7(2026-09-21)을 stable로 올려놓았습니다. 즉, 2026-09-23 시점에서는 “7.2.6이 최신 stable”조차 아닙니다. 그런데 운영 현장에서는 7.2.6이 롤아웃 윈도우에 걸려 그대로 배포될 수 있습니다. 이 시차가 사고를 만들기도 합니다. [kernel.org 릴리스 페이지](https://www.kernel.org/)에서 stable 7.2.7 날짜를 확인할 수 있습니다.[^10]

짧은 간격 업데이트에서 운영 계약이 더 중요해지는 이유는, “이번 주에 올릴 커널”이 “이번 주에 나온 커널”과 일치하지 않는 일이 더 잦아지기 때문입니다.

## 회귀(regression) 탐지·롤백을 ‘운영 계약’으로 쓰는 방식

내가 말하는 운영 계약은 법무 문서가 아닙니다. 운영팀/플랫폼팀/보안팀/개발팀이 같은 단어로 의사결정하도록 만드는 합의문에 가깝습니다. stable 커널 업데이트에 이걸 적용하면, 최소한 아래 항목이 계약 조항이 됩니다.

### 1) 회귀의 정의: “부팅 실패”만 회귀가 아니다

커널 업데이트에서 흔히 정의되는 실패는 “부팅이 안 됨”입니다. 하지만 7.2.6 전후 사례는 stutter/lag처럼 체감형이었습니다. 그래서 회귀 정의를 두 층으로 나눕니다.

- Hard regression: boot fail, kernel panic, 파일시스템 오류, 데이터 손상, 네트워크 down, GPU 모듈 로딩 실패
- Soft regression: p99 스케줄링 지연 증가, input latency 증가, compositor frame pacing 악화, 오디오 crackle, 스크롤 stutter

Soft regression은 모니터링 설계가 없으면 “개인의 느낌”으로 떨어집니다. 그 순간 계약이 깨집니다. 누군가는 “문제 없다”고 하고, 누군가는 “못 쓰겠다”고 합니다.

### 2) 탐지 신호를 먼저 합의한다: 무엇을 보면 ‘멈출지’

SRE 쪽에서는 canary를 “부분적이고 시간 제한이 있는 배포 + 평가”로 정의합니다. 핵심은 평가 기준이 사전에 있어야 한다는 겁니다. [Google SRE Workbook: Canarying Releases](https://sre.google/workbook/canarying-releases/)가 이 부분을 비교적 구체적으로 설명합니다.[^11]

커널 canary에서 내가 최소로 합의하는 신호는 대략 이런 것들입니다.

- 부팅 후 `dmesg`에서 특정 키워드(soft lockup, GPU reset, NVRM, IOMMU fault 등)
- `systemd` 부팅 실패 유닛 수, 부팅 시간 증가
- 스케줄링 지연(서버는 `cyclictest`, 데스크톱은 frame pacing 지표를 별도로)
- NVIDIA라면 `nvidia-smi` 기반의 디바이스 인식, 모듈 로딩 상태

여기까지가 계약의 “관측 가능성” 파트입니다.

### 3) 롤백은 ‘기술’이 아니라 ‘절차’다

커널 롤백은 대부분 GRUB에서 이전 커널로 부팅하는 겁니다. 이 자체는 어렵지 않습니다. 진짜 어려운 건 다음입니다.

- 장애 상황에서 원격 접속이 살아있을까?
- 누가, 언제, 어떤 조건에서 롤백을 실행할까?
- 롤백 후에도 NVIDIA DKMS가 재빌드되면서 또 다른 문제를 만들지 않을까?

그래서 롤백을 계약 문장으로 쓰면 아래 요소가 들어가야 합니다.

- 롤백 트리거: hard regression은 자동, soft regression은 수동 승인 등
- 롤백 책임자: on-call/플랫폼/데스크톱 운영 등
- 롤백 시간 제한: canary soak 30분/2시간/1일 등
- 롤백 후 검증: 커널 버전 확인 + 핵심 드라이버 로딩 확인 + 기본 기능 점검

### 4) NVIDIA 상호작용은 “조합 승인” 또는 “변수 고정” 둘 중 하나

Void Linux 사례처럼 커널과 드라이버를 동시에 올리면 원인 분리가 안 됩니다. 반대로 커널만 올리면 DKMS 빌드가 실패하거나, 드라이버가 커널 내부 변화에 민감해서 결과적으로 장애가 날 수 있습니다.

그래서 운영 계약에서는 아래 둘 중 하나로 명시해야 합니다.

- 조합 승인: (커널 X, NVIDIA Y) 조합 단위로 승인하고, 다른 조합은 금지
- 변수 고정: 커널 업데이트 주간에는 NVIDIA를 고정(또는 반대로)하고, 바꾸는 주간을 분리

NVIDIA open 모듈 이슈처럼 “드라이버 버전만 바꿨더니 hang이 사라졌다” 같은 리포트가 존재하는 현실에서는, 조합을 계약 단위로 삼는 게 가장 깔끔합니다.[^7]

## 실제 운영에 쓰는 canary/자동 롤백 가드 예시 (GRUB + systemd)

아래는 Debian/Ubuntu 계열(일반적인 GRUB2 + systemd 환경)에서 내가 쓰는 패턴을 “커널 롤아웃 가드” 형태로 정리한 것입니다. 핵심 컨셉은 이것입니다.

- 새 커널로 1회 부팅(one-shot)
- 부팅 직후 healthcheck 통과 시에만 새 커널을 기본값으로 고정
- 실패하면 이전 커널을 기본값으로 되돌리고 재부팅

이 방식은 “사람이 GRUB 화면에서 커널을 고르는 행위”를 운영 계약에서 제거합니다. 다시 말해 롤백을 인간의 기억력에 의존하지 않게 합니다.

### 환경/의존성

- GRUB2 (`grub-reboot`, `grub-set-default`, `grub-editenv`)
- systemd
- (선택) NVIDIA 환경이면 `nvidia-smi`가 설치돼 있어야 함
- (선택) 지연 측정용 `rt-tests` 패키지의 `cyclictest`

Debian 기준 설치 예:

```bash
sudo apt-get update
sudo apt-get install -y rt-tests
```

### 1) 부팅 항목(menuentry) 자동 탐색 + one-shot 부팅 설정

`/usr/local/sbin/kernel_canary_stage1.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

TARGET_VER="${1:-}"
if [[ -z "${TARGET_VER}" ]]; then
  echo "usage: $0 <kernel-version-substring>" >&2
  echo "example: $0 7.2.6" >&2
  exit 2
fi

GRUB_CFG="/boot/grub/grub.cfg"
GRUB_ENV="/boot/grub/grubenv"

if [[ ! -r "${GRUB_CFG}" ]]; then
  echo "cannot read ${GRUB_CFG}" >&2
  exit 1
fi

CURRENT_UNAME="$(uname -r)"

# grub.cfg에서 menuentry 이름을 뽑습니다.
# Debian/Ubuntu는 일반적으로 "Advanced options" 하위에 커널 버전별 entry가 있습니다.
mapfile -t ENTRIES < <(grep -E "^menuentry '" "${GRUB_CFG}" | sed -E "s/^menuentry '([^']+)'.*$/\1/")

TARGET_ENTRY=""
for e in "${ENTRIES[@]}"; do
  if [[ "${e}" == *"${TARGET_VER}"* ]]; then
    TARGET_ENTRY="${e}"
    break
  fi
done

if [[ -z "${TARGET_ENTRY}" ]]; then
  echo "no grub menuentry matched kernel version substring: ${TARGET_VER}" >&2
  echo "hint: check /boot/grub/grub.cfg" >&2
  exit 1
fi

# 롤백을 위해 현재 커널 버전도 grubenv에 기록해 둡니다.
# (이 값은 stage2 healthcheck에서 사용)
sudo grub-editenv "${GRUB_ENV}" set canary_prev_uname="${CURRENT_UNAME}"
sudo grub-editenv "${GRUB_ENV}" set canary_target_entry="${TARGET_ENTRY}"

# one-shot 부팅: 다음 부팅 1회만 TARGET_ENTRY로 부팅
sudo grub-reboot "${TARGET_ENTRY}"

echo "current kernel : ${CURRENT_UNAME}"
echo "target entry  : ${TARGET_ENTRY}"
echo "next reboot will boot the target entry once."
```

실행 예:

```bash
sudo bash /usr/local/sbin/kernel_canary_stage1.sh 7.2.6
sudo reboot
```

예상 출력(환경마다 entry 문자열은 다릅니다):

```text
current kernel : 7.2.4-amd64
target entry  : Debian GNU/Linux, with Linux 7.2.6-amd64
next reboot will boot the target entry once.
```

### 2) 부팅 직후 healthcheck + 성공 시 고정 / 실패 시 롤백

`/usr/local/sbin/kernel_canary_stage2.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

GRUB_ENV="/boot/grub/grubenv"

TARGET_ENTRY="$(grub-editenv "${GRUB_ENV}" list | awk -F= '$1=="canary_target_entry"{print $2}')"
PREV_UNAME="$(grub-editenv "${GRUB_ENV}" list | awk -F= '$1=="canary_prev_uname"{print $2}')"

CURRENT_UNAME="$(uname -r)"

if [[ -z "${TARGET_ENTRY}" || -z "${PREV_UNAME}" ]]; then
  echo "missing canary metadata in grubenv" >&2
  exit 1
fi

# 1) 커널 버전이 target으로 부팅됐는지 확인
#    (target entry 문자열과 uname -r이 1:1로 매칭되지 않는 배포판도 있어 substring으로만 확인)
if [[ "${TARGET_ENTRY}" != *"${CURRENT_UNAME}"* ]]; then
  echo "booted kernel (${CURRENT_UNAME}) does not look like target (${TARGET_ENTRY})" >&2
  echo "treat as failure" >&2
  exit 10
fi

# 2) NVIDIA 환경이면 최소 신호 확인(설치돼 있지 않으면 스킵)
if command -v nvidia-smi >/dev/null 2>&1; then
  if ! nvidia-smi -L >/dev/null 2>&1; then
    echo "nvidia-smi failed" >&2
    exit 20
  fi
fi

# 3) cyclictest로 scheduler latency를 간단히 체크(rt-tests 설치돼 있으면)
#    기준은 환경마다 다르므로, 여기서는 '극단적으로 큰 값'만 fail 처리합니다.
if command -v cyclictest >/dev/null 2>&1; then
  # 3초만 측정
  OUT="$(cyclictest -q -D 3s -p99 -m -S 2>/dev/null || true)"
  # 출력 예: "T: 0 (  99) P:99 I:1000 C:  3000 Min:      5 Act:    7 Avg:    8 Max:     95"
  MAX_US="$(echo "${OUT}" | awk '{for(i=1;i<=NF;i++){if($i=="Max:"){print $(i+1)}}}')"
  MAX_US="${MAX_US:-0}"

  # max latency 2000us(2ms) 초과면 실패 처리(예시 기준)
  if [[ "${MAX_US}" -gt 2000 ]]; then
    echo "cyclictest max latency too high: ${MAX_US} us" >&2
    echo "raw: ${OUT}" >&2
    exit 30
  fi
fi

# 통과: 이제 이 커널을 기본 부팅으로 고정
sudo grub-set-default "${TARGET_ENTRY}"

# 메타데이터 정리
sudo grub-editenv "${GRUB_ENV}" unset canary_prev_uname
sudo grub-editenv "${GRUB_ENV}" unset canary_target_entry

echo "canary healthcheck passed; pinned default kernel to: ${CURRENT_UNAME}"
```

systemd 유닛(`/etc/systemd/system/kernel-canary-health.service`):

```ini
[Unit]
Description=Kernel canary healthcheck and pin/rollback
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/kernel_canary_stage2.sh

# 실패하면 곧바로 롤백하도록 후속 액션을 걸어둡니다.
# (롤백 방식은 조직마다 다르지만, 여기서는 '이전 커널을 기본값으로 되돌리고 재부팅' 패턴을 사용)
ExecStopPost=/bin/bash -c 'echo "kernel canary failed; reverting to saved previous kernel"; PREV=$(grub-editenv /boot/grub/grubenv list | awk -F= '$1=="canary_prev_uname"{print $2}'); if [[ -n "$PREV" ]]; then echo "prev uname=$PREV"; fi; grub-set-default 0; reboot'

[Install]
WantedBy=multi-user.target
```

활성화:

```bash
sudo systemctl daemon-reload
sudo systemctl enable kernel-canary-health.service
```

이 예시는 두 가지를 고정합니다.

- “새 커널 부팅”을 자동화한다.
- “새 커널을 기본값으로 채택”하는 순간을 healthcheck 통과 뒤로 미룬다.

이 두 가지가 들어가면, stable 커널 업데이트를 운영 계약으로 다룰 때 가장 흔한 빈 구멍(새 커널로 부팅만 해놓고 다음날 잊어버리는 문제)을 줄일 수 있습니다.

## 반론과 회의론: stable인데 이렇게까지 해야 하나

### “stable은 검증된 거 아닌가?”

stable은 upstream mainline에 이미 들어간 수정 중에서 backport 가능한 것들을 모읍니다. 그리고 stable 규칙은 꽤 보수적입니다. 하지만 그 규칙 문서조차 “성능/인터랙션 수정은 더 미묘하고 회귀 위험이 높다”는 점을 별도 항목으로 분리해 경고합니다. 즉, stable이라고 해서 운영 리스크가 0이 되는 건 아닙니다.[^4]

### “커뮤니티 stutter는 재현도 안 됐다는데?”

맞습니다. Void Linux 스레드도 결국 “다음 날엔 정상”으로 끝났습니다. 그런데 운영은 “재현이 안 됐다”가 끝이 아닙니다. 재현이 안 되는 회귀는 더 위험합니다.

- canary에서 놓치기 쉽고
- 전면 롤아웃 뒤에 특정 사용자/특정 GPU/특정 모니터/특정 compositor에서만 터지며
- 로그가 남지 않을 확률이 높기 때문입니다.

그래서 계약 문장에 “체감 회귀의 증거 기준”을 넣어야 합니다. 예를 들면 “frame pacing 지표가 X 이상 흔들리면 회귀”처럼 수치화가 필요합니다.

### “보안 때문에 무조건 올려야 한다”

릴리스 공지 메일에는 “All users … must upgrade” 같은 문장이 들어갑니다. stable은 보안 수정이 섞이기도 하고, 업스트림은 업그레이드를 강하게 권고합니다.[^2]

하지만 운영자의 의무는 “올리는 것”이 아니라 “올린 뒤에도 서비스가 정상”인 것입니다. 그래서 보안 패치가 포함돼 있더라도, canary/롤백/관측을 계약으로 못 박지 않으면 결과적으로 보안 조치가 운영 장애로 상쇄됩니다.

## 앞으로 지켜볼 것: 7.2.7 이후와 ‘문서화된 회귀’로의 수렴

2026-09-23 시점에서 kernel.org는 stable 최신을 7.2.7(2026-09-21)로 올려두었습니다. 즉 7.2.6은 이미 “바로 다음 stable로 덮인” 상태입니다. 운영에서 이 상황은 두 가지를 의미합니다.

- 7.2.6의 체감 이슈가 “커널 레벨 회귀”였다면, 7.2.7에서 수정/완화가 들어갔을 가능성이 있다.
- 반대로 7.2.6의 체감 이슈가 “조합 문제”였다면, 7.2.7로 올라가도 재발할 수 있다.

여기서 내가 보는 관전 포인트는 3가지입니다.

1) 7.2.6 관련 회귀가 regzbot(회귀 트래킹)나 메일링 리스트에서 ‘정식 regression’으로 승격되는지
2) 배포판 커널 메인테이너가 stable 규칙 문서가 요구하는 수준(사용자 영향/버그 링크)을 갖춰 backport/추가 수정 요청을 올리는지
3) NVIDIA(open/proprietary) 쪽에서 “특정 커널/특정 드라이버 조합의 알려진 문제”로 문서화되는지

regzbot 자체는 “메일링 리스트 기반 회귀 트래킹”을 위해 만들어졌고, `#regzbot` 커맨드로 회귀를 추적하는 방식과 대시보드가 공개돼 있습니다. 이 생태계가 활발해질수록, 운영자가 “커뮤니티 체감 글”을 “추적 가능한 회귀”로 변환할 여지가 커집니다. [regzbot 저장소](https://github.com/kernelci/regzbot)와 [stable/longterm 대시보드](https://linux-regtracking.leemhuis.info/regzbot/stable/)가 공개돼 있습니다.[^12]

## 지금 할 수 있는 일: 7.2.4→7.2.6 같은 업데이트를 ‘계약’으로 고정하는 템플릿

내 기준으로, stable 커널 마이너 업데이트의 운영 계약은 아래 문장들로 구성됩니다.

- 대상/범위: (커널 버전) + (배포판 패키지 릴리스) + (NVIDIA 드라이버 버전) 조합을 1개의 변경 단위로 정의한다.[^7]
- canary 링: 최소 1대는 실제 사용자 워크로드(특히 GPU/멀티모니터/Wayland)를 그대로 가진 host로 고정한다. 커널 canary는 “서버 canary”와 “데스크톱 canary”를 분리한다.[^11]
- 관측 신호: hard regression 신호와 soft regression 신호를 분리하고, soft regression은 수치화된 지표 1개 이상을 필수로 둔다(예: cyclictest max latency, compositor frame pacing, input latency).[^4]
- 승인 게이트: stable-rc 공개 시점에 1차 영향 평가를 시작하고, 정식 stable 공지 시점에는 “배포 준비가 끝나 있어야 한다”.[^8]
- 롤백 조건: 부팅 실패/드라이버 로딩 실패는 자동 롤백, 체감형 회귀는 canary soak 내 재현 + 지표 악화로 롤백을 트리거한다.
- 롤백 수단: GRUB one-shot + 부팅 후 healthcheck로 “기본 커널 고정” 여부를 결정한다. 즉, **롤백은 옵션이 아니라 기본 동작**이다.

7.2.6 건은 “stable이니까 안전하다”가 아니라 “stable이라도 운영에서는 계약으로 다뤄야 한다”를 다시 확인시켜 줍니다. 작은 패치가 모이면 큰 변경이고, 큰 변경은 결국 관측과 롤백 설계의 문제로 귀결됩니다.

## 참고 자료

- [linux-stable 태그 목록(GitLab 미러)](https://gitlab.com/linux-kernel/stable/-/tags)
- [Linux 7.2.6 발표 메일(LWN 아카이브)](https://lwn.net/Articles/1093986/)
- [Linux 7.2.6 ChangeLog](https://cdn.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.2.6)
- [Linux stable rules 문서](https://cdn.kernel.org/doc/html/latest/process/stable-kernel-rules.html)
- [Void Linux: 7.2.6 stuttering/lagging 스레드](https://www.reddit.com/r/voidlinux/comments/1whjyik/linux_726_stutteringlagging/)
- [NVIDIA open GPU kernel modules 이슈 #1367](https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1367)
- [LKML 아카이브: 7.2.6-rc1 review 관련 메일](https://lkml.iu.edu/2609.1/12896.html)
- [kernel.org 릴리스 페이지](https://www.kernel.org/)
- [Debian unstable로 linux 7.2.6-1 accepted](https://tracker.debian.org/news/1799140/accepted-linux-726-1-source-into-unstable/)
- [Google SRE Workbook: Canarying Releases](https://sre.google/workbook/canarying-releases/)
- [regzbot 저장소](https://github.com/kernelci/regzbot)
- [regzbot stable/longterm 대시보드](https://linux-regtracking.leemhuis.info/regzbot/stable/)
- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)
- [Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영](https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/)
- [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)

[^1]: <https://gitlab.com/linux-kernel/stable/-/tags>
[^2]: <https://lwn.net/Articles/1093986/>
[^3]: <https://www.reddit.com/r/voidlinux/comments/1whjyik/linux_726_stutteringlagging/>
[^4]: <https://cdn.kernel.org/doc/html/latest/process/stable-kernel-rules.html>
[^5]: <https://cdn.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.2.6>
[^6]: <https://ftp.metu.edu.tr/pub/mirrors/ftp.kernel.org/pub/linux/kernel/v7.x/>
[^7]: <https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1367>
[^8]: <https://lkml.iu.edu/2609.1/12896.html>
[^9]: <https://tracker.debian.org/news/1799140/accepted-linux-726-1-source-into-unstable/>
[^10]: <https://www.kernel.org/>
[^11]: <https://sre.google/workbook/canarying-releases/>
[^12]: <https://github.com/kernelci/regzbot>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
