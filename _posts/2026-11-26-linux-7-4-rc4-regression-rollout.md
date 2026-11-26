---
title: "Linux 7.4-rc4 공개가 배포 조직의 회귀 테스트 일정을 앞당겨야 하는 이유"
description: "Linux 7.4-rc4는 드라이버 비중이 크고 수정 범위가 넓습니다. 연말 릴리스 전 RC 단계에서 CI·카나리·롤백 계약을 재점검할 시점입니다."
date: 2026-11-26 13:38:38 +0900
categories: ["News", "Systems"]
tags: ["linux-kernel", "regression-testing", "ci", "canary-rollout", "kexec", "kselftest"]
render_with_liquid: false
---

## Linux 7.4-rc4 공개: 날짜와 “크다”라는 신호

Linux 7.4-rc4는 2026-11-22 23:22 UTC에 커널 배포 시스템을 통해 공개되었습니다. 배포 시스템 공지에는 tarball과 이전 릴리스 대비 패치, 변경 요약 링크가 함께 걸려 있습니다.[^1]

운영 관점에서 더 중요한 건 릴리스 노트가 아니라, Linus Torvalds가 RC 공지에서 남긴 톤입니다. 7.4-rc4는 “huge”라는 표현이 붙었고, 변경의 절반이 drivers이며 특히 GPU와 networking이 늘 눈에 띈다고 요약했습니다. 나머지는 core kernel, mm, filesystems, networking, selftests, arch 전반으로 퍼져 있다고 했습니다.[^2]

여기서 배포 조직이 읽어야 하는 메시지는 단순합니다.

- “RC 후반으로 갈수록 패치가 줄어든다”는 전제가 항상 성립하지 않습니다.
- drivers 중심의 RC는 하드웨어 조합이 많은 환경에서 회귀 리스크를 기하급수로 늘립니다.

KST 기준으로 보면 2026-11-23 아침(UTC+9)에 해당 릴리스가 풀린 셈입니다. “오늘(2026-11-26 KST)” 시점에서 이미 RC4가 나온 뒤 3~4일이 지나 테스트 착수를 미룰 명분이 약해졌습니다.

## “연말 메이저”가 만드는 일정 압력: RC4가 배포 조직의 분기점인 이유

kernel.org의 릴리스 프로세스 설명은 꽤 명확합니다.

- mainline 릴리스 후 2주 merge window
- merge window 종료 후 7주 안정화 기간(주간 RC)
- 보통 rc7이 마지막(필요하면 rc8+)
- 전체 mainline 릴리스 주기는 대략 9~10주

이게 배포 조직 일정에 주는 함의는 “대충 연말쯤” 같은 감이 아니라, 역산 가능한 캘린더라는 점입니다.[^3]

7.4는 rc1이 2026-11-01에 찍혀 있고, rc4가 2026-11-22에 나왔으니(주간 cadence 유지), 지금은 안정화 구간의 정확히 중간쯤입니다. 이 구간부터는 새 기능을 기대하는 게 아니라, 이미 합쳐진 변경들이 내 워크로드에서 어떤 회귀를 일으키는지 찾아내는 싸움으로 바뀝니다.

내 경험상 RC 테스트 착수 시점을 rc6~rc7 근처로 미루면 다음 문제가 터집니다.

1) 회귀를 발견해도 upstream에 의미 있는 리포트를 넣기엔 늦습니다. (재현/로그/설명까지 갖추기 어렵고, maintainers도 릴리스 임박 상태에서 큰 수정을 꺼립니다.)

2) downstream에서만 막는 임시 대응이 늘어납니다. 즉, “우리 배포 파이프라인만 복잡해지고, 다음 사이클에 또 같은 문제를 만나는” 패턴이 강화됩니다.

그래서 rc4는 기술적으로 “중간 RC”일 뿐인데, 배포 조직 관점에서는 회귀 비용을 낮출 수 있는 마지막 현실적 시점에 가깝습니다.

## RC 단계의 변화가 CI·커널 롤아웃 계약을 흔드는 지점

예전에 나는 커널 롤아웃을 일종의 계약으로 정의해 운영 기준을 정리해 둔 적이 있습니다.

- [Linux 7.2.6 stable 릴리스: 작은 패치가 운영에선 큰 리스크가 되는 이유](https://daewooki.github.io/posts/linux-kernel-stable-rollout-contract/)
- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)
- [Linux 커널 7.3 메인라인 이후 GA 롤아웃 검증 체크리스트](https://daewooki.github.io/posts/linux-kernel-73-ga-rollout-validation/)

그 글들의 내용을 반복하진 않겠습니다. 대신 7.4-rc4 같은 “drivers 비중이 절반”인 RC가 왜 계약을 흔드는지, 배포 조직 시선에서 더 구체적으로 적습니다.

배포 조직의 커널 롤아웃 계약은 보통 다음을 포함합니다.

- 카나리 단위(호스트/랙/리전/풀)
- 롤백이 보장되는 시간(rollback SLO)
- 관측 항목(부팅 성공률, NIC link flap, IO error rate, p99 latency, soft lockup, RCU stall)
- 실패 시의 자동 조치(자동 drain, 자동 reboot, 자동 롤백)
- 실패 원인에 대한 증거 수집(커널 로그, crash dump, perf/ftrace 스냅샷)

문제는 RC에서 drivers와 filesystems/networking이 동시에 흔들리면, 위 계약의 전제들이 깨진다는 점입니다.

- “롤백은 곧바로 된다”는 전제는 kdump/kexec 준비가 없으면 성립하지 않습니다.
- “관측 지표로 이상을 빨리 감지한다”는 전제는, 변화가 NIC/스토리지/FS/트레이싱까지 퍼지면 원인 분리가 안 됩니다.
- “카나리로 충분히 대표성을 확보한다”는 전제는, GPU/USB/IIO/NVMe처럼 장비 의존성이 큰 영역이 커지면 무너집니다.

그래서 RC 테스트는 단순히 “새 커널 부팅해 보기”가 아니라, 계약 문구 자체(카나리 설계와 롤백 경로)를 다시 쓰는 작업이 됩니다.

## 이번 rc4에서 배포에 직접 닿는 변화의 성격: drivers / filesystems / networking

Linus가 말한 “drivers 절반”은 감상이 아니라 운영 리스크의 종류를 규정합니다.[^2]

### drivers: GPU만이 아니라 USB/IIO/NVMe/사운드까지 같이 흔들린다

drivers가 크면, “서버는 headless니까 GPU는 상관없다”로 끝나지 않습니다.

- 일부 서버는 BMC 콘솔, KVM, iGPU, SR-IOV, DP/HDMI가 얽혀 있고
- 사내 하드웨어 랩은 USB NIC, USB storage, 각종 센서(IIO), 특수 HBA/SmartNIC를 물고 있으며
- NVMe 관련 코드는 storage stack의 중심입니다.

rc4에 들어온 DRM 쪽만 봐도, 단순히 한두 줄 fix가 아니라 서브드라이버별로 다양한 영역에 패치가 걸립니다. Dave Airlie가 보낸 drm fixes pull 요청 요약에는 amdgpu/xe/i915/vmwgfx 등 다양한 드라이버 및 동기화/타이머/리셋/VRR 관련 이슈가 섞여 있습니다.[^4]

이런 변경은 다음 두 가지 이유로 배포 조직의 CI를 흔듭니다.

1) “대표 장비” 선정이 더 어려워집니다. 가령 i915 회귀는 특정 세대/해상도 조합에서만 재현될 수 있고, 그 조합이 프로덕션에 없더라도 사내 CI 노드(빌드 서버, 관측 에이전트, 개발 워크스테이션)에 존재할 수 있습니다.

2) 커널이 바뀌면 userspace가 아니라 “장비 자체의 동작 모드”가 바뀝니다. 모니터링 대시보드는 p99 latency만 보고 있는데, 실제 문제는 display pipeline 리셋이나 PCIe 에러 처리일 수 있습니다.

서버 운영팀이 GPU를 무시할 수 없어진 이유는, 커널을 “워크로드만 받쳐주는 OS”가 아니라 “하드웨어를 조립하는 펌웨어에 가까운 층”으로 취급해야 하기 때문입니다.

### filesystems / storage: XFS/FUSE/NVMe처럼 운영 워크로드와 바로 맞닿는다

rc4 shortlog를 보면 xfs, fuse, nvme 관련 수정이 섞여 있습니다. 예를 들어 xfs 쪽은 flush/extent shifting/dio write checks 등 데이터 경로에 걸친 변경이 여럿 보입니다.[^5]

Phoronix가 강조한 사례 중 하나는 NVMe namespace 제거를 병렬화하는 최적화입니다. 기존에는 namespace를 순차로 제거하면서 RCU grace period 대기를 namespace 수만큼 반복해, 다수 namespace 환경에서 disconnect 시간이 길어질 수 있었고, 이를 async domain 기반으로 겹쳐 기다리도록 바꾼 취지입니다.[^6]

이건 성능 개선 소식처럼 보이지만, 배포 조직 입장에서는 다음 질문으로 바뀝니다.

- fabrics target disconnect/cleanup 시간이 줄어들면서 타임아웃/리트라이 패턴이 바뀌지 않는가?
- multipath나 device-mapper 위에서 teardown 순서가 바뀌어 race가 생기지 않는가?
- “빠르다”는 게 곧 “동기화 타이밍이 바뀐다”는 뜻인데, 내가 가진 운영 스크립트(udev rule, initramfs hook, drain automation)가 그 타이밍을 전제로 하지 않는가?

특히 NVMe namespace를 쓰는 환경은 대개 multi-tenant 격리나 성능 최적화를 하려는 곳이고, 그런 곳일수록 자동화(attach/detach, reprovision)가 공격적으로 돌아갑니다. 즉, 개선이든 회귀든 영향이 커집니다.

### networking: TCP 한 줄 fix도 “롤백 비용”을 키운다

rc4 shortlog에는 tcp fast open listener 재시작 시 NULL pointer dereference를 막는 수정 같은 네트워크 경로의 안정성 패치도 보입니다.[^5]

이런 패치는 “좋은 일”이지만, 배포 조직 관점에선 다음과 같이 해석해야 합니다.

- 지금 RC에 이런 크래시 fix가 들어왔다는 건, rc3까지는 특정 조건에서 커널 크래시가 가능했다는 의미입니다.
- 내가 rc4부터 테스트를 시작하면, rc3 기반으로 했던 테스트는 “의미가 바뀝니다”. (동일 테스트가 이제는 통과할 것이고, 그 통과는 내 환경이 안전해서가 아니라 upstream fix 덕일 수 있습니다.)
- 네트워크 경로의 수정은 증상이 “연결 끊김”이나 “RTT 튐” 같은 형태로 나타나, 애플리케이션 팀이 먼저 신고하고 커널 팀이 뒤늦게 추적하는 흐름을 만들기 쉽습니다.

그래서 networking 변화가 RC에 많을수록, 배포 조직은 “테스트 착수”를 앞당겨서 증거를 쌓아야 합니다. 커널 문제는 재현 가능한 로그가 있느냐 없느냐가 전부입니다.

## 배경: upstream 프로세스는 RC 테스트를 전제로 설계되어 있다

“RC는 커널 개발자용”이라는 말은 맞습니다. kernel.org도 RC(prepatch)는 주로 커널 개발자와 enthusiast를 대상으로 하며, 안정판에 들어가기 전에 테스트가 필요하다고 설명합니다.[^3]

하지만 배포 조직은 이미 upstream의 전제 위에 서 있습니다.

- stable 릴리스는 mainline에서 backport됩니다.[^3]
- -stable에 들어갈 수 있는 변경은 원칙적으로 mainline에 이미 존재해야 하고, “명백히 correct하고 테스트되어야 한다”는 규칙이 문서로 정리돼 있습니다.[^7]

즉, 우리가 연말에 7.4 stable을 받는 순간 이미 “누군가가 RC에서 테스트했을 것”이라는 가정에 올라타는 셈인데, 그 누군가가 내 하드웨어와 내 워크로드를 대신 테스트해 줄 가능성은 낮습니다.

이건 [Linux 7.3 RC 회귀 테스트·드라이버 검증 자동화 설계](https://daewooki.github.io/posts/linux-kernel-rc-regression-pipeline/)에서 다룬 내용과도 이어집니다. 당시에도 결론은 단순했습니다. upstream의 폭넓은 테스트는 존재하지만, 내 환경의 회귀는 내가 잡아야 합니다.

## 왜 중요한가: RC부터 계약을 고치면 연말 장애 비용이 줄어든다

배포 조직 관점에서 비용이 가장 큰 커널 장애는 다음 두 종류입니다.

1) “부팅은 된다” + “워크로드에서 천천히 망가진다”
- filesystem corruption, 데이터 손상, silent error, 간헐적 hang
- 이런 건 롤백을 눌러도 이미 비용이 발생합니다.

2) “특정 하드웨어 풀만 망가진다”
- 특정 NIC/펌웨어/PCIe topology에서만 터지는 문제
- 카나리 설계가 하드웨어 대표성을 못 담으면 본배포에서야 드러납니다.

7.4-rc4 같은 릴리스가 배포 조직에 주는 신호는 “drivers 절반”입니다. 이건 곧 2) 유형의 리스크가 커졌다는 의미입니다.[^2]

RC부터 다음을 선행하면 연말 비용이 실제로 줄어듭니다.

- 하드웨어 대표 카나리 풀 재정의
- 롤백 경로(kexec 포함) 검증
- 증거 수집 체계(boot log, dmesg, pstore, vmcore) 정리
- kselftest 같은 upstream 테스트를 내 CI에 붙이는 작업

kselftest 문서 자체가 “커널을 빌드/설치/부팅한 후 실행하는 작은 self test들”이라는 점을 명시하고 있고, mainline의 kselftest를 stable에 돌리는 것도 유의미하다고 설명합니다.[^8]

즉, RC에서 kselftest를 돌리는 건 upstream이 의도한 사용 형태에 더 가깝습니다.

## 반론과 회의론: “RC 테스트는 노이즈만 늘린다”

RC를 CI에 넣으면 실제로 노이즈가 늘어납니다. 부정하긴 어렵습니다.

- upstream의 일시적 회귀(다음 RC에서 바로 고쳐질 것)가 내 파이프라인을 빨갛게 만들 수 있습니다.
- 같은 원인인데 커밋이 쌓이면서 증상이 달라져 triage가 어려워질 수 있습니다.
- downstream(배포판 커널, vendor 커널)을 쓰는 조직은 “어차피 upstream RC와 다르다”는 거리감이 있습니다.

그런데 이 반론은 “연말에 안정판 올라오면 그때 테스트하면 된다”는 가정에 기대는데, 그 가정이 실제 운영에서 자주 깨집니다.

- distro 커널도 결국 mainline 흐름 위에서 움직입니다(단지 backport와 patch stack이 있을 뿐).
- 연말은 조직 전체가 바쁘고, 커널 테스트를 마지막에 몰면 롤백/관측/조치 자동화의 약점을 그대로 끌고 갑니다.
- 무엇보다 커널 장애는 재현이 어렵습니다. 시간이 지나면 workload 패턴/펌웨어/마이크로코드/드라이버가 같이 변해서 “그때 그 증상”을 다시 만들기 힘듭니다.

결국 노이즈를 줄이는 방법은 RC를 피하는 게 아니라, RC를 받아들이되 “배포 조직의 계약을 깨지 않게” 설계하는 쪽입니다.

## 앞으로 지켜볼 것: rc5~rc7에서 바뀌는 것과 backport의 방향

kernel.org 설명대로라면 rc7이 보통 마지막입니다.[^3]

그래서 rc5~rc7 구간에서 내가 보는 포인트는 기능이 아니라 다음입니다.

- rc4에서 “huge”라고 표현된 변경 폭이 rc5~rc6에서 줄어드는가, 아니면 비슷한 크기로 계속 오는가
- 내 환경에서 잡힌 회귀가 upstream에서 받아들여질 만큼 재현 가능하게 정리됐는가
- 내가 임시로 막은 workaround가 -stable에 들어갈 성격인지(작고 명백한 fix인지)

-stable 규칙 문서는 “mainline에 이미 있거나 동등한 fix가 존재해야 한다”, “명백히 correct하고 테스트되어야 한다”, “실사용자가 겪는 문제를 고쳐야 한다” 같은 원칙을 박아두고 있습니다.[^7]

배포 조직 입장에서 이 문서를 읽어야 하는 이유는, RC에서 발견한 회귀를 어떻게 “backport 가능한 형태”로 압축할지 감이 생기기 때문입니다. 버그 리포트를 “증상 설명”으로 끝내면 해결되지 않습니다. 최소한 어떤 커밋 범위에서 들어왔는지(bisect), 어떤 장비/커널 config/재현 절차인지까지 포함돼야 합니다.

이 지점에서 syzbot 같은 자동 fuzzing 시스템이 왜 강력한지도 연결됩니다. syzbot 문서도 “계속 fuzzing하면서 발견된 버그를 메일링 리스트에 자동 리포트한다”는 운영 모델을 설명합니다.[^9]

우리 조직이 syzbot처럼 할 수는 없더라도, RC 테스트를 “가능한 한 자동화된 증거 수집”으로 바꾸는 방향은 현실적인 투자가 됩니다.

## 지금 할 수 있는 일: RC 커널을 ‘카나리/롤백 가능’하게 다루는 실행 계획

여기서부터는 배포 조직 관점의 실행 계획입니다. 핵심은 **RC를 프로덕션에 올리자**가 아니라, RC를 다루는 방법을 “배포 계약 안”으로 가져오는 겁니다.

### 1) RC 전용 카나리 풀을 “하드웨어 축”으로 쪼갠다

drivers 변경이 절반이면, 카나리는 서비스 축(웹/배치)보다 하드웨어 축이 먼저입니다.

- NIC vendor/세대/firmware
- NVMe vendor/controller/namespace 구성
- CPU vendor/microcode 세대
- 가상화(KVM/TDX/SEV), IOMMU 켠 상태

서비스별 카나리는 그 다음입니다. 내 경우 “워크로드 대표성”은 쉽게 잡히지만, “하드웨어 대표성”은 쉽게 빠집니다.

rc4 같은 주간 RC는 속도가 중요해서, 카나리 풀도 “일주일에 한 번 재부팅해도 괜찮은 장비”로 별도 분리하는 게 운영적으로 안정적입니다.

### 2) 부팅 시간을 비용으로 취급하고, kexec를 회귀 테스트 도구로 쓴다

kexec는 원래 crash dump(kdump)에서 핵심 메커니즘으로 쓰입니다. kdump 문서는 kexec를 이용해 패닉 시 dump-capture kernel로 빠르게 부팅하고, 메모리 이미지를 보존하는 구조를 설명합니다.[^10]

또한 man-pages에는 일반 kexec(KEXEC_ON_CRASH가 아닌 경우)에서 세그먼트가 로드되고, 실제 복사는 kexec reboot 시점에 일어난다는 식의 동작 개요가 정리돼 있습니다.[^11]

배포 조직이 여기서 얻는 건 한 가지입니다.

- RC 테스트의 병목(재부팅에 걸리는 시간)을 줄이면, 같은 기간에 더 많은 하드웨어/워크로드 조합을 훑을 수 있습니다.

물론 kexec는 만능이 아닙니다.

- 펌웨어/BIOS 초기화가 생략되므로, cold boot에서만 드러나는 문제는 잡기 어렵습니다.
- 일부 드라이버는 kexec 경로에서 정리/재초기화가 깔끔하지 않을 수 있습니다.

그래도 “RC 회귀 테스트”에서는 cold boot 한 번 + kexec N번이라는 조합이 비용 대비 효율이 좋습니다. cold boot 회귀는 별도 체크로 떼어내고, 대부분의 커널 변경은 kexec로 충분히 흔들어 볼 수 있습니다.

### 3) kselftest를 “전부”가 아니라 “내가 흔들리는 경로”만 묶어 돌린다

kselftest 문서가 말하듯 selftests는 경로별 작은 테스트입니다. 전체를 매번 다 돌리면 시간이 너무 길고, RC 주간 cadence에 맞추기 어렵습니다.[^8]

그래서 나는 다음처럼 접근합니다.

- 커널 업그레이드로 가장 먼저 깨질 수 있는 부분(네트워크, filesystems, cgroup, bpf, tracing)을 우선순위로 잡고
- 그 범위의 kselftest를 “필수 smoke”로 설정한 뒤
- 나머지는 야간/주간 배치로 돌립니다.

## 실행 가능한 예시: 7.4-rc4를 빌드하고 kexec 카나리로 굴리는 최소 구성

아래 예시는 “하드웨어 랩의 베어메탈 1대”를 기준으로, 7.4-rc4를 설치한 뒤 kexec로 RC 부팅 → 테스트 → 원복까지 자동으로 끝내는 흐름입니다.

- 배포판: Debian/Ubuntu 계열(커널을 .deb로 만들기 쉬움)
- 전제: /boot에 known-good 커널(예: distro kernel)이 이미 존재
- 목표: RC 커널은 “일시적으로 부팅해서 테스트만 하고” 다시 known-good로 돌아오기

### 0) 빌드 머신 준비(패키지)

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential bc bison flex libssl-dev libelf-dev \
  dwarves rsync git \
  fakeroot \
  kexec-tools

# 선택: 메뉴 설정이 필요하면
sudo apt-get install -y libncurses-dev
```

kexec-tools는 distro 패키지로 설치합니다. kexec syscalls 자체는 커널 설정(CONFIG_KEXEC 등)에 달려 있지만, 일반적인 서버/데스크톱 배포판 커널은 대개 kexec를 켜 둡니다. (꺼져 있으면 이 설계는 성립하지 않습니다.)

### 1) 7.4-rc4 소스 확보

kernelthread 공지에 걸린 tarball을 그대로 받습니다.[^1]

```bash
mkdir -p ~/src && cd ~/src
curl -LO https://git.kernel.org/torvalds/t/linux-7.4-rc4.tar.gz

tar -xzf linux-7.4-rc4.tar.gz
cd linux-7.4-rc4
```

### 2) 커널 설정: “운영 커널 설정을 최대한 따라가되, 디버그는 분리”

가장 흔한 실패는 “RC 커널을 빌드하면서 config를 과하게 바꾸는 것”입니다. 회귀 테스트의 목적은 커널 기능 실험이 아니라, 업그레이드 자체의 리스크를 측정하는 겁니다.

```bash
# 현재 머신의 설정 기반
cp -v /boot/config-$(uname -r) .config

# 새 옵션은 기본값으로
make olddefconfig

# 로컬 빌드 식별자(운영과 구분)
scripts/config --set-str LOCALVERSION "-rc4-canary"

# (선택) 커널 디버그 옵션은 별도 빌드로 분리하는 편이 낫습니다.
```

### 3) .deb 패키지로 빌드(설치/제거/롤백을 단순화)

```bash
# 병렬 빌드
make -j"$(nproc)" bindeb-pkg

# 상위 디렉터리에 linux-image, linux-headers .deb가 생성됩니다.
cd ..
ls -1 *.deb
```

이 방식의 장점은 “커널 설치가 패키지 단위로 관리”된다는 점입니다. 배포 조직에서 가장 피곤한 건, RC 테스트가 끝난 뒤 흔적이 남는 겁니다.

### 4) 대상 노드에 설치

빌드와 테스트가 같은 머신이면 바로 설치합니다.

```bash
sudo dpkg -i ./linux-image-7.4.0-rc4-rc4-canary_*.deb ./linux-headers-7.4.0-rc4-rc4-canary_*.deb

# 설치 확인
ls -1 /boot/vmlinuz-*7.4.0-rc4* || true
ls -1 /boot/initrd.img-*7.4.0-rc4* || true
```

### 5) RC 부팅 후 자동으로 smoke 테스트를 돌리고, 테스트가 끝나면 known-good로 돌아오는 systemd unit

핵심은 “RC로 부팅한 순간 사람이 붙어 있지 않아도” 결과와 원복이 되게 하는 겁니다.

#### (1) smoke 스크립트

```bash
sudo tee /usr/local/sbin/rc74-smoke.sh > /dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

OUT_BASE=/var/log/rc74
TS=$(date -Is)
OUT_DIR="$OUT_BASE/$TS"
mkdir -p "$OUT_DIR"

{
  echo "== uname =="
  uname -a

  echo "== cmdline =="
  cat /proc/cmdline

  echo "== dmesg (tail) =="
  dmesg -T | tail -n 300
} | tee "$OUT_DIR/boot.txt"

# 1) 빠른 커널 selftest (시간 제한을 두는 편이 안전)
# kselftest 문서에 따르면 selftests는 tools/testing/selftests 아래에 있으며,
# 부팅 후 실행하도록 설계되어 있습니다.
# 여기서는 '네트워크/파일시스템/타이밍'처럼 운영에 직접 닿는 것부터 최소로 실행합니다.
# 실제 선택은 조직 워크로드에 맞게 조정합니다.

if [ -x /usr/lib/kselftest/run_kselftest.sh ]; then
  timeout 30m /usr/lib/kselftest/run_kselftest.sh \
    -c net \
    -c filesystems \
    -c timers \
    | tee "$OUT_DIR/kselftest.txt" || true
else
  echo "kselftest not installed" | tee "$OUT_DIR/kselftest.txt"
fi

# 2) 간단한 I/O / 네트워크 스모크(현실에선 fio/iperf3 등 조직 표준으로 대체)
{
  echo "== nvme list =="
  command -v nvme >/dev/null 2>&1 && nvme list || echo "nvme-cli not installed"

  echo "== ss =="
  ss -s
} | tee "$OUT_DIR/smoke.txt"

# 결과 마커
echo "OK" > "$OUT_DIR/result"

# 3) known-good 커널로 kexec 롤백
# - kdump 문서가 설명하듯 kexec는 빠른 커널 전환 메커니즘입니다.
# - 여기서는 crash kernel이 아니라 일반 kexec 경로를 사용합니다.

KNOWN_GOOD_VER=$(ls -1 /boot/vmlinuz-* | grep -v '7.4.0-rc4' | head -n 1 | sed 's#/boot/vmlinuz-##')

if [ -n "$KNOWN_GOOD_VER" ] && [ -f "/boot/initrd.img-$KNOWN_GOOD_VER" ]; then
  echo "Rolling back to $KNOWN_GOOD_VER" | tee "$OUT_DIR/rollback.txt"
  kexec -l "/boot/vmlinuz-$KNOWN_GOOD_VER" --initrd="/boot/initrd.img-$KNOWN_GOOD_VER" --command-line="$(cat /proc/cmdline)"
  sync
  kexec -e
else
  echo "No known-good kernel/initrd found, rebooting" | tee "$OUT_DIR/rollback.txt"
  reboot
fi
EOF

sudo chmod +x /usr/local/sbin/rc74-smoke.sh
```

이 스크립트는 극도로 보수적으로 구성했습니다.

- 실패하더라도 로그를 남기고
- kselftest가 없으면 없다고 기록하고
- known-good 커널을 못 찾으면 그냥 reboot

현실에서는 known-good 버전을 명시적으로 고정하고(예: 환경 변수나 설정 파일), grep 기반 자동 탐색은 제거하는 편이 안전합니다.

#### (2) systemd unit

```bash
sudo tee /etc/systemd/system/rc74-smoke.service > /dev/null <<'EOF'
[Unit]
Description=Linux 7.4-rc4 canary smoke test and rollback
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/rc74-smoke.sh
TimeoutStartSec=3600

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable rc74-smoke.service
```

### 6) known-good 커널에서 RC 커널로 kexec 진입

```bash
RC_VER=$(ls -1 /boot/vmlinuz-*7.4.0-rc4* | head -n 1)
RC_INITRD=$(ls -1 /boot/initrd.img-*7.4.0-rc4* | head -n 1)

sudo kexec -l "$RC_VER" --initrd="$RC_INITRD" --command-line="$(cat /proc/cmdline)"
sudo sync
sudo kexec -e
```

예상 흐름은 다음입니다.

1) known-good 커널에서 kexec로 RC 부팅
2) RC 부팅 직후 rc74-smoke.service가 실행
3) 로그를 /var/log/rc74/타임스탬프/ 아래에 남김
4) 테스트가 끝나면 다시 known-good로 kexec 롤백

이렇게 해 두면, RC 테스트가 “사람이 붙어 있는 이벤트”가 아니라 “매주 자동으로 굴러가는 작업”이 됩니다. 주간 RC cadence를 받아들이려면 결국 이 형태로 가야 합니다.

## 정리: rc4부터 회귀 테스트를 시작해야 하는 이유는 ‘기술’이 아니라 ‘조직 비용 구조’다

Linux 7.4-rc4는 2026-11-22 UTC에 공개됐고, Linus 스스로 drivers 비중이 절반인 큰 RC라고 못 박았습니다.[^1]

kernel.org가 설명하는 9~10주 릴리스 주기와 주간 RC 안정화 모델을 감안하면, rc4는 “이제 테스트해도 늦지 않은 시점”이 아니라 “지금부터는 테스트하지 않으면 연말에 비용이 커질 시점”에 더 가깝습니다.[^3]

RC를 올리는 목적은 새 기능을 먼저 쓰려는 게 아닙니다. drivers/filesystems/networking 변화가 동시에 밀려올 때 CI·카나리·롤백 계약이 깨지지 않게, 회귀를 조기에 발견하고 증거를 남겨 upstream과 downstream 양쪽에서 비용을 줄이려는 겁니다. kexec/kselftest 같은 도구를 회귀 테스트의 “속도와 증거”를 올리는 방향으로 연결하면, RC 테스트는 불확실성을 키우는 활동이 아니라 연말 장애를 선불로 갚는 활동이 됩니다.

## 참고 자료

- [Linux kernel 7.4-rc4 released (kernelthread 공지)](https://kernelthread.org/t/20261122232244.release-7.4-rc4%40kdist.linux.kernel.org)
- [Linux 7.4-rc4 공지 메일(LWN 재게시)](https://lwn.net/Articles/1108899/)
- [Active kernel releases / Releases FAQ(커널 릴리스 cadence)](https://www.kernel.org/releases.html)
- [Linux 7.4-rc4 Released: "It's Huge. What A Surprise."(Phoronix)](https://www.phoronix.com/news/Linux-7.4-rc4-Released)
- [Linux 7.4 To Remove NVMe Namespaces In Parallel For Faster Results(Phoronix)](https://www.phoronix.com/news/Linux-7.4-NVMe-NS-Parallel)
- [[git pull] drm fixes for 7.4-rc4(Linux-Kernel Archive)](https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2611.2/18676.html)
- [Linux 7.4-rc4 shortlog(Linux-Kernel Archive)](https://lkml.iu.edu/2611.2/21681.html)
- [Everything you ever wanted to know about Linux -stable releases(stable-kernel-rules.rst)](https://github.com/torvalds/linux/blob/master/Documentation/process/stable-kernel-rules.rst)
- [Linux Kernel Selftests(kselftest 문서)](https://docs.kernel.org/dev-tools/kselftest.html)
- [Documentation for Kdump - The kexec-based Crash Dumping Solution](https://docs.kernel.org/admin-guide/kdump/kdump.html)
- [kexec_load/kexec_file_load man-pages(PDF)](https://www.kernel.org/pub/linux/docs/man-pages/book/man-pages-6.8.pdf)
- [syzbot 문서(google/syzkaller)](https://github.com/google/syzkaller/blob/master/docs/syzbot.md)
- [KernelCI 문서: Bisection](https://github-wiki-see.page/m/kernelci/kernelci-doc/wiki/Bisection)

RC 단계에서부터 회귀 테스트를 시작하는 판단은 커널의 “안정성”을 신뢰하느냐의 문제가 아니라, 내 조직이 연말에 지불할 장애 비용을 어떤 방식으로 분할 납부할지에 대한 결정입니다.

[^1]: <https://kernelthread.org/t/20261122232244.release-7.4-rc4%40kdist.linux.kernel.org>
[^2]: <https://lwn.net/Articles/1108899/>
[^3]: <https://www.kernel.org/releases.html>
[^4]: <https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2611.2/18676.html>
[^5]: <https://lkml.rescloud.iu.edu/2611.2/21681.html>
[^6]: <https://www.phoronix.com/news/Linux-7.4-NVMe-NS-Parallel>
[^7]: <https://github.com/torvalds/linux/blob/master/Documentation/process/stable-kernel-rules.rst>
[^8]: <https://cdn.kernel.org/doc/html/latest/dev-tools/kselftest.html>
[^9]: <https://github.com/google/syzkaller/blob/master/docs/syzbot.md>
[^10]: <https://www.kernel.org/doc/html/v6.0/admin-guide/kdump/kdump.html>
[^11]: <https://www.kernel.org/pub/linux/docs/man-pages/book/man-pages-6.8.pdf>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
