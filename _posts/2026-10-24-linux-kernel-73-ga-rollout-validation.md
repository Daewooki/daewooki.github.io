---
title: "Linux 커널 7.3 메인라인 이후 GA 롤아웃 검증 체크리스트"
description: "Linux 7.3 메인라인 확정 이후 RC 회귀 테스트를 GA 캔리 롤아웃 검증으로 전환하는 운영 체크리스트를 정리합니다."
date: 2026-10-24 12:40:33 +0900
categories: ["News", "Systems"]
tags: ["linux-kernel", "release-engineering", "canary-rollout", "drivers", "storage", "regression-testing"]
render_with_liquid: false
---

## 2026-10-18 Linux 7.3 메인라인 릴리스: 사실관계와 운영상 의미

Linux 커널 7.3은 kernel.org 기준으로 **2026-10-18**에 mainline로 릴리스되어 배포 아티팩트(tarball/patch/PGP signature)가 올라왔습니다.[^1] 이 타임스탬프가 운영 관점에서 중요한 이유는 단순히 “버전이 올라갔다”가 아니라, 지난 7.3-rcN 기간에 하던 검증이 ‘개발 사이클의 리그레션 탐지’에 치우쳐 있었다면 이제는 ‘내 조직이 실제로 배포 가능한 형태의 아티팩트’로 커널을 취급해야 하기 때문입니다.

커널 릴리스 모델을 kernel.org는 Prepatch(-rc), Mainline, Stable, Longterm으로 구분합니다. -rc는 “새 기능이 들어가 있고 테스트가 필요해서 enthusiasts/개발자 중심”이라고 못 박고, mainline이 릴리스된 뒤에는 그 mainline을 “stable로 간주”한다고 설명합니다.[^2] 여기서 stable은 우리가 흔히 말하는 “운영용으로 안전하다”의 의미가 아니라, “해당 mainline 버전 라인에 대해 bugfix가 backport되는 단계로 들어간다”에 가깝습니다.

그래서 커널을 제품 장애와 1:1로 연결해서 보는 조직(스토리지 어플라이언스, 가상화 호스트, GPU 워크로드 노드, HCI, Telco edge 등)에서는 mainline=stable이라는 문장만으로는 의사결정을 내리면 안 됩니다. 내 기준에서는 이렇게 정리하는 편이 덜 위험합니다.

- RC 단계: upstream이 리그레션을 잡도록 돕는 테스트(발견/보고/재현/바이섹션/패치 검증)
- GA 단계(내 조직): 롤백 가능하고, 관측 가능하고, 장애 반경이 통제되는 배포(캔리/링 배포/driver·storage 집중)

Linux 7.3에서 언급된 변화 폭 자체도 운영 전환의 근거가 됩니다. LWN은 7.3이 18,765 non-merge commits, 3,021 developers, 807 first-time contributors로 “record-breaker”였다고 정리했고, 눈에 띄는 변화로 group-scheduling(대형 시스템 성능), failfs, fchroot(), BPF per-CPU data, sched_ext subscheduler 완성, VM working-set tracking, ntfs3 alternate data streams, SMB server 개선 등을 언급합니다.[^3] KernelNewbies 역시 sched_ext/cgroup scheduling, ext4/btrfs 성능, failfs+fchroot(), userfaultfd working set, FUSE io_uring, RWF_DONTCACHE, ksmbd(Time Machine) 등을 prominent feature로 올려 두었습니다.[^4]

이런 사이클에서는 “RC 때 테스트를 했으니 GA는 그냥 릴리스 버전으로 치환”이 성립하지 않습니다. RC는 기능/리그레션의 탐지이고, GA는 배포의 공학입니다.

## RC 회귀 테스트에서 GA 롤아웃 검증으로 바뀌는 것

RC 기반 테스트는 내가 예전에 정리한 [Linux 7.3 RC 회귀 테스트·드라이버 검증 자동화 설계](https://daewooki.github.io/posts/linux-kernel-rc-regression-pipeline/)에서 다뤘던 영역입니다. 그 글이 “리그레션을 더 빨리 찾고 upstream에 더 잘 전달하는 파이프라인”에 가깝다면, 이번 글은 그 파이프라인의 출력물을 받아 “운영 배포 가능”으로 바꾸는 단계에 집중합니다.

RC와 GA의 핵심 차이는 ‘성공 기준’입니다.

- RC 성공 기준: 새 커널이 이전 RC 대비 나빠지지 않았는가(리그레션 중심), upstream에 제출 가능한 재현/로그/바이섹션이 있는가
- GA 성공 기준: 내 서비스 SLO/SLA 관점에서 안전하게 점진 배포가 가능한가, 롤백이 자동화되어 있는가, driver/스토리지 관련 장애가 캔리 링에서 충분히 드러나도록 설계되어 있는가

운영에서 커널 사고는 대체로 다음 경로로 터집니다.

1) 커널 코드 자체 버그
2) 커널-펌웨어 상호작용(특정 NVMe FW, NIC FW, RAID HBA FW, GPU FW)
3) out-of-tree 모듈(DKMS, 벤더 드라이버)과의 ABI/심볼/서명 문제
4) 부팅 경로(UEFI/secure boot/모듈 서명/initramfs) 문제
5) 성능 회귀(스케줄러/NUMA/메모리 reclaim/I/O 스케줄링)로 인한 사실상 장애

RC 테스트는 1)에 강하고, GA는 2)~5)까지를 “배포 시스템” 관점에서 같이 잡아야 합니다. kernel.org가 릴리스 모델을 time-based rolling으로 설명하고(-rc는 주간 단위로 나오고 최종 릴리스가 되면 다음 merge window로 넘어감)[^5], regzbot 같은 시스템으로 회귀를 추적하는 문화가 자리 잡은 것도 결국 이 규모의 변화에서 ‘사람이 수동으로 다 못 본다’는 전제가 깔려 있습니다.[^6]

GA 전환 시점에서 제일 흔한 착각은 “커널이 GA면 안정적이다”가 아니라 “테스트가 GA면 안정적이다”입니다. 커널은 mainline일 뿐이고, 안정성을 만드는 건 배포 설계와 관측 설계입니다.

## 7.3에서 운영 검증 축을 다시 잡아야 하는 이유(드라이버·스토리지 중심)

7.3의 기능 리스트를 전부 다 파고드는 건 목적이 아닙니다. 다만 운영 검증 관점에서는 “어느 축이 바뀌었는지”가 체크리스트의 우선순위를 정합니다.

### 스케줄러/대형 시스템: 캔리에서 성능 회귀를 장애로 취급해야 하는 영역

7.3에는 대형 시스템 성능을 겨냥한 group-scheduling 작업과 sched_ext 관련 진전이 언급됩니다.[^3] 이런 변화는 기능 장애보다 “tail latency 상승 → 큐 적체 → 타임아웃/재시도 폭증 → 스토리지/네트워크 증폭” 같은 2차 장애로 터지는 편입니다. 특히 스토리지 노드나 DB 노드에서는 커널 스케줄링 변화가 blk-mq/IO submission 패턴과 만나서 현상이 더 심해집니다.

그래서 GA 전환 체크리스트에서는, 성능은 벤치마크 점수로만 판단하지 말고 “장애 신호”로 넣어야 합니다. 예를 들면 p99 I/O latency, soft lockup 여부, scheduler 관련 WARN, runqueue imbalance 같은 지표를 롤백 트리거로 넣는 식입니다.

### 파일시스템/블록 계층: 속도 개선이 곧 안정성 개선은 아니다

KernelNewbies와 외부 기사들은 ext4/btrfs 성능 개선, FUSE io_uring 성능 개선, 블록 디바이스에 RWF_DONTCACHE 지원 같은 변화를 prominent하게 다룹니다.[^4] 속도 개선은 대체로 fast-path가 바뀌었다는 의미고, 운영에서 fast-path 변경은 리그레션이 숨어 있을 확률이 올라갑니다. 내 경험상 “성능이 좋아졌다”는 릴리스 노트가 뜨는 사이클은 오히려 GA 검증을 더 길게 잡습니다.

### SMB/ksmbd: 커널 내 파일 서버를 쓰는 조직은 커널 업그레이드가 곧 서비스 업그레이드

7.3에서 ksmbd가 Apple Time Machine 관련 확장을 지원한다는 언급이 반복됩니다.[^4] ksmbd를 실제 운영에 쓰는 곳은 커널 업그레이드가 곧 SMB 서버 업그레이드입니다. 이런 경우 GA 검증은 커널 smoke test로 끝나지 않고, SMB workload replay(특히 metadata-heavy, small file, durable handle 같은 케이스)까지 들어가야 합니다.

### BPF: 관측/정책이 커널에 더 붙어 있는 조직일수록 업그레이드 리스크가 커진다

LWN은 BPF 프로그램을 위한 global per-CPU data를 변화 포인트로 언급합니다.[^3] 내 경우는 eBPF를 “관측 도구” 정도로만 쓰면 영향이 제한적이지만, tc/XDP, LSM, runtime policy 등으로 쓰는 조직은 커널 업그레이드 검증에 “BPF 프로그램 호환성”이 독립된 트랙이 됩니다.

정리하면 7.3의 변화는 ‘driver/스토리지만 보면 된다’가 아니라, driver/스토리지 장애가 스케줄러/FS/BPF 변화와 결합해 더 복잡한 형태로 나온다는 쪽에 가깝습니다.

## GA 전환 체크리스트 1: “내가 배포하는 커널”의 아티팩트를 고정한다

GA 검증은 기능보다 먼저 아티팩트를 고정하는 일입니다. 여기서 삐끗하면 이후 체크리스트가 전부 의미가 없어집니다.

### 1) upstream 소스/서명 검증을 파이프라인 시작점에 넣는다

kernel.org는 릴리스 tarball과 detached PGP signature를 제공합니다.[^1] 운영 파이프라인에서 최소한 다음은 자동화하는 편이 낫습니다.

- tarball 다운로드
- signature 다운로드
- 검증에 쓰는 공개키 체인 준비
- 검증 결과를 빌드 메타데이터에 저장

커널 릴리스 서명 검증 절차는 kernel.org 문서에 예시가 있습니다.[^7]

### 2) config를 “테스트 대상”으로 취급한다

커널 업그레이드 사고의 절반은 사실 config 사고입니다.

- distro kernel을 그대로 쓰는 조직: distro의 config가 바뀌는 것도 업그레이드 리스크
- self-build 하는 조직: Kconfig 변경으로 동일한 .config가 다른 의미를 갖는 경우가 발생

따라서 GA 체크리스트는 커널 버전뿐 아니라, 아래를 고정해야 합니다.

- .config(원본 파일)
- toolchain 버전(gcc/clang/binutils)
- packaging 방식(커스텀 deb/rpm, initramfs 생성 방식)
- kernel cmdline

이 고정이 되어야 캔리에서 터졌을 때 “커널 탓”인지 “패키징/부팅 경로 탓”인지 분리가 됩니다.

### 3) out-of-tree 모듈 리스트를 사전에 확정한다

운영에서 커널을 올릴 때 가장 자주 깨지는 건 NVIDIA/OFED 같은 유명한 것만이 아닙니다. 스토리지 HBA, NIC, 보안 에이전트, 스토리지 필터, EDR, 커스텀 filesystem 등 out-of-tree 모듈이 하나라도 있으면 커널은 사실상 “플랫폼 ABI”가 됩니다.

GA 전환 체크리스트에는 최소한 이 목록이 들어가야 합니다.

- out-of-tree 모듈 식별(패키지/경로/DKMS 여부)
- 모듈 서명/secure boot 정책
- 모듈 로드 실패 시 부팅 영향도(early boot에 필요한가)
- 모듈이 접근하는 storage path 여부(blk/FS에 붙는지)

## GA 전환 체크리스트 2: 캔리 링 설계를 driver·스토리지 중심으로 바꾼다

RC 테스트는 “넓게” 커버하는 게 장점이지만, GA 캔리는 “좁고 깊게”가 장점입니다. 특히 driver/스토리지 리그레션은 특정 조합에서만 나오기 때문에, 링 설계가 하드웨어 매트릭스를 대표하지 못하면 아무 의미가 없습니다.

### 링 설계(예시): 기능 검증 링과 장애 반경 제어 링을 분리한다

내가 커널 롤아웃에서 자주 쓰는 방식은, 링을 두 축으로 나눕니다.

- 기능 링: 새 기능을 실제로 쓰는 워크로드(예: ksmbd를 쓰는 링, FUSE를 쓰는 링, 특정 BPF 프로그램을 쓰는 링)
- 장애 반경 링: 같은 기능을 쓰더라도 blast radius가 작은 노드/테넌트부터 배포

driver/스토리지는 보통 “장애 반경 링”이 더 중요합니다. 이유는 간단합니다. 스토리지/driver 사고는 대부분 hard failure로 오기 때문에, 기능을 ‘조금만’ 쓰는 노드에서도 치명적입니다.

### 하드웨어 매트릭스: 스토리지 경로를 기준으로 분류한다

서버 fleet에서 대표성을 잡는 기준을 CPU 세대나 메모리 크기로 잡으면 스토리지 리그레션이 잘 안 잡힙니다. 나는 다음 축을 우선합니다.

- 부트 디바이스 경로(NVMe/SATA/RAID/HBA)
- 데이터 디바이스 경로(로컬 NVMe, JBOD+HBA, NVMe-oF, iSCSI)
- 파일시스템(ext4/xfs/btrfs)
- 암호화 계층(dm-crypt/LUKS)
- RAID 계층(mdraid, dm-raid, hw raid)
- multipath 여부

이 축이 커버되면, 7.3에서 파일시스템/블록 계층의 변화가 실제 운영에서 어떤 형태로 나타나는지 더 빨리 볼 수 있습니다.[^4]

### 롤백: “패키지 롤백”이 아니라 “부팅 롤백”이 되어야 한다

커널은 패키지만 되돌린다고 해결되지 않습니다. 다음 상태를 항상 보장해야 합니다.

- 이전 커널로 부팅 가능한 부트 엔트리 존재
- 자동 롤백이 실패해도 원격 콘솔/시리얼/Out-of-band로 복구 가능
- initramfs까지 포함한 원자적 전환(부분 업데이트 방지)

이건 RC 테스트에서는 거의 신경 쓰지 않는 영역이지만 GA에서는 가장 중요합니다.

## GA 전환 체크리스트 3: 부팅/서명/initramfs 경로를 실제 배포처럼 검증한다

kernel.org는 tarball/patch/서명을 제공하고, signature를 검증하는 문서도 제공합니다.[^1] 하지만 운영에서 더 흔한 장애는 “커널이 문제”가 아니라 “커널을 로딩하는 과정”이 문제인 경우입니다.

### secure boot + 모듈 서명 정책을 캔리 1단계에서 확정한다

secure boot를 켠 환경에서는 다음이 반드시 체크리스트로 들어가야 합니다.

- vmlinuz 서명 방식이 기존과 동일한가
- 모듈 서명 키(조직 키/벤더 키)와 MOK enrollment 정책
- initramfs 안에 들어가는 모듈이 서명 정책을 위반하지 않는가

이 경로는 RC에서 통과했어도 GA에서 자주 깨집니다. RC는 보통 개발자가 로컬에서 부팅해 보지만, 운영은 이미지 빌더/서명/배포/부트로더까지 전부 파이프라인으로 묶여 있기 때문입니다.

### initramfs 구성 변경을 “스토리지 리그레션”으로 오인하지 않는다

스토리지 장애처럼 보이는 부팅 실패의 많은 비율이 initramfs에 필요한 모듈이 누락된 케이스입니다.

- NVMe 드라이버가 initramfs에 없어서 rootfs를 못 찾음
- dm-crypt 모듈/키스크립트 누락으로 LUKS unlock 실패
- RAID 어셈블 스크립트 변경으로 mdraid가 assemble되지 않음

GA 체크리스트에서 중요한 건 “부팅 실패의 원인이 커널 코드인지”를 분리하는 진단 루틴입니다. 이 분리가 안 되면 캔리 링에서 실패했을 때 롤백은 빨라지지만, 원인 분석은 느려집니다.

## GA 전환 체크리스트 4: 드라이버·스토리지 검증을 smoke test에서 ‘증상 기반’으로 확장한다

드라이버/스토리지 검증을 “fio 한 번 돌려서 OK”로 끝내면, 실제 사고 형태(리셋/타임아웃/큐 정지/간헐 오류)를 놓치기 쉽습니다. 특히 스토리지 경로 리그레션은 다음처럼 나옵니다.

- 평상시 정상 → GC/trim/재시도 조건에서 급격히 느려짐
- 고부하에서 queue timeout → 장치 리셋 → filesystem remount ro
- 특정 전원관리 상태에서 링크 재훈련 → 디바이스 재인식

### (실행 가능한 예시) 부팅 직후 커널 스모크 + I/O 증상 체크 스크립트

아래 스크립트는 “캔리 노드가 새 커널로 부팅한 직후”에 돌려서, 부팅 경로와 스토리지 경로에서 흔히 보이는 증상들을 빠르게 잡는 용도입니다. 파괴적 테스트를 피하기 위해 raw device에는 쓰지 않고, 지정한 디렉터리에 파일을 만들어 fio를 돌립니다.

- 대상: Ubuntu/Debian 계열 기준(다른 배포판도 유사)
- 의존성: fio, jq

```bash
#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=${TEST_DIR:-/var/lib/kernel-ga-smoke}
TEST_SIZE=${TEST_SIZE:-2G}
RUNTIME=${RUNTIME:-30}

mkdir -p "$TEST_DIR"

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }

log "uname: $(uname -a)"

# 1) 커널 taint 체크 (0이 이상적)
if [[ -r /proc/sys/kernel/tainted ]]; then
  TAINT=$(cat /proc/sys/kernel/tainted)
  log "kernel.tainted=$TAINT"
fi

# 2) dmesg에서 스토리지/드라이버 계열 증상 키워드 스캔
# 운영에서는 키워드 기반만으로 결론 내리면 안 되지만, 캔리 게이트로는 유용합니다.
DMESG_OUT="$TEST_DIR/dmesg.txt"
dmesg -T > "$DMESG_OUT" || true

KEYWORDS='I/O error|blk_update_request|Buffer I/O error|EXT4-fs error|XFS .* ERROR|BTRFS error|nvme .* timeout|nvme .* reset|AER:|ata.*failed|SAS:.*reset|scsi.*aborted command|hung task|soft lockup|hard lockup|rcu_sched detected stalls'
HITS=$(grep -E -n "$KEYWORDS" "$DMESG_OUT" || true)
if [[ -n "$HITS" ]]; then
  log "dmesg keyword hits found:"
  printf '%s\n' "$HITS" | tail -n 200
  # 캔리에서는 여기서 실패로 처리하는 게 대체로 맞습니다.
  exit 2
fi

# 3) 블록 디바이스/마운트 요약(관측용)
lsblk -J > "$TEST_DIR/lsblk.json"
jq -r '.blockdevices[] | [.name,.type,(.size//""),(.mountpoint//"-")] | @tsv' "$TEST_DIR/lsblk.json" \
  | sed $'s/\t/\t|\t/g' \
  | while read -r line; do log "lsblk | $line"; done

# 4) fio: 파일 기반 랜덤 read/write. 데이터 디렉터리만 확인하면 파일시스템/스토리지 경로에서
#    기본적인 timeout/에러는 잡힙니다.
if ! command -v fio >/dev/null 2>&1; then
  log "fio not found. Install: apt-get install -y fio"
  exit 3
fi

FIO_JOB="$TEST_DIR/fio.job"
cat > "$FIO_JOB" <<EOF
[global]
ioengine=io_uring
thread=1
direct=1
time_based=1
runtime=${RUNTIME}
size=${TEST_SIZE}
filename=${TEST_DIR}/fio.testfile
group_reporting=1

[randrw]
rw=randrw
bs=4k
iodepth=32
EOF

log "running fio (${RUNTIME}s, ${TEST_SIZE}) in ${TEST_DIR}"
fio "$FIO_JOB" | tee "$TEST_DIR/fio.out"

# 5) fio 이후에도 dmesg에 새로 찍힌 에러가 없는지 재확인
DMESG_OUT2="$TEST_DIR/dmesg.after.txt"
dmesg -T > "$DMESG_OUT2" || true
HITS2=$(grep -E -n "$KEYWORDS" "$DMESG_OUT2" || true)
if [[ -n "$HITS2" ]]; then
  log "post-fio dmesg keyword hits found:"
  printf '%s\n' "$HITS2" | tail -n 200
  exit 4
fi

log "GA smoke test: PASS"
```

실행 예시:

```bash
sudo apt-get update
sudo apt-get install -y fio jq
sudo TEST_DIR=/var/lib/kernel-ga-smoke RUNTIME=20 TEST_SIZE=1G bash ./kernel-ga-smoke.sh
```

이 스크립트는 완전한 검증이 아닙니다. 다만 캔리의 1차 게이트로는 효과가 있습니다. 내가 중요하게 보는 건 fio 결과 숫자 자체가 아니라, fio가 “문제를 일으키는 상황을 만들었을 때” dmesg에 timeout/reset/error가 올라오느냐입니다.

### 스토리지 검증에서 자주 빠지는 포인트

- TRIM/discard 경로: 랜덤 write만으로는 안 드러나는 NVMe FW 이슈가 있습니다.
- 작은 파일/metadata 워크로드: DB WAL처럼 순차 write만으로도 문제가 나올 수 있고, 반대로 metadata-heavy가 터지는 경우도 많습니다.
- suspend/resume 또는 PCIe 링크 전원관리: 데이터센터에서도 특정 플랫폼에서 반복됩니다.

여기까지는 “체크리스트”의 영역이고, 이 다음부터는 “내 서비스 워크로드 재현”이 들어가야 합니다.

## 반론과 회의론: mainline(7.3)을 GA로 다루는 게 맞나

이 지점에서 현실적인 반론이 두 가지 나옵니다.

### 1) “mainline은 운영 커널이 아니다”

맞는 말입니다. kernel.org 문서에서도 -rc는 enthusiasts/개발자 대상이고, mainline이 릴리스된 뒤 stable 업데이트가 이어진다고 설명하지만[^2], 여기서 stable은 “운영 적합성 보증”이 아닙니다.

그럼에도 7.3을 GA 관점으로 봐야 하는 조직이 있습니다.

- 자체 배포판/어플라이언스/커널을 직접 빌드해 배포하는 조직
- 특정 하드웨어 enablement를 기다리는 조직
- 커널 기능(예: sched_ext, ksmbd)을 제품 가치로 직접 쓰는 조직[^4]

이 경우 mainline 릴리스 시점이 곧 “내가 GA를 준비해야 하는 시점”이 됩니다.

### 2) “어차피 distro 커널은 backport라 7.3을 바로 못 쓴다”

일반적인 엔터프라이즈 리눅스 운영에서는 더 현실적인 반론입니다. 다만 이 말은 “7.3을 배포하지 않는다”일 뿐 “7.3에서 들어온 변화가 내 운영에 영향을 주지 않는다”가 아닙니다. backport는 시간차를 두고 들어오고, 특히 파일시스템/드라이버 계열은 선별적으로 들어오면서 예상치 못한 조합을 만듭니다.

그래서 나는 커널 mainline 릴리스 때 GA 체크리스트를 정리해 두고, 실제 배포는 distro 커널/HWE/벤더 커널이 그 변화 집합을 들고 들어오는 시점에 맞춰 실행합니다. 이 관점은 예전에 썼던 [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)의 연장선이기도 합니다.

## 앞으로 지켜볼 것: 7.3 이후의 안정화 흐름을 운영 신호로 읽는다

7.3 릴리스 자체보다 중요한 건 “7.3 이후 무엇이 7.3.y로 backport되고, 무엇이 회귀로 남는가”입니다.

- regzbot과 KernelCI의 결합은 회귀 추적을 더 체계화하는 흐름으로 보입니다.[^8] upstream 회귀가 어떤 속도로 닫히는지, 어느 서브시스템에서 오래 걸리는지 자체가 운영의 리스크 모델 입력이 됩니다.
- 7.3의 prominent changes(sched_ext, group-scheduling, filesystems, SMB, virtualization)가 실제로 안정화 과정에서 어떤 유형의 fix를 많이 필요로 하는지 관찰해야 합니다.[^3]
- kernel.org가 정의한 stable 규칙(메인라인에 먼저 들어가야 stable에 backport 가능, stable@vger.kernel.org 프로세스 등)은 “내가 고칠 수 있는 문제”와 “기다려야 하는 문제”를 가르는 기준이 됩니다.[^9]

운영 체크리스트 관점에서는 ‘버그가 있냐 없냐’가 아니라 ‘버그가 있을 때 내가 감당 가능한 범위에서 드러나고, 자동 롤백이 되느냐’가 더 중요합니다.

## 지금 시점(2026-10-24 KST)에 RC→GA 전환으로 해야 하는 결론

Linux 7.3이 2026-10-18에 mainline로 확정되었고[^1], prominent change가 스케줄러/FS/가상화/SMB/BPF까지 넓게 퍼져 있습니다.[^3] 이 상황에서 지난주까지의 RC 회귀 테스트를 그대로 연장하는 건 방향이 다릅니다.

내 결론은 간단합니다.

- RC에서 GA로 넘어가는 순간, 테스트의 주체는 upstream이 아니라 내 조직이고, 대상은 커널 코드가 아니라 배포 시스템이다.
- driver/스토리지 중심 환경에서는 “캔리 설계 + 부팅 롤백 + 증상 기반 관측”이 체크리스트의 앞쪽에 와야 한다.
- 7.3 같은 대형 사이클에서는 성능 회귀를 기능 결함과 같은 급으로 취급해야 하고, 그 판단을 자동화된 게이트로 내리는 편이 안전하다.

## 참고 자료

- [kernel.org 메인 페이지(7.3 릴리스/날짜/아티팩트)](https://www.kernel.org/)
- [kernel.org: Active kernel releases(Prepatch/Mainline/Stable/Longterm 정의)](https://www.kernel.org/releases.html)
- [LWN: The 7.3 kernel has been released](https://lwn.net/Articles/1101143/)
- [LWN: Linux 7.3(LKML 릴리스 메일 아카이브)](https://lwn.net/Articles/1101170/)
- [KernelNewbies: Linux 7.3 changelog](https://kernelnewbies.org/Linux_7.3)
- [GIGAZINE: Linux 7.3 has been released](https://www.gigazine.net/gsc_news/en/20261020-linux-kernel-7-3/)
- [kernel.org 문서: Handling regressions](https://www.kernel.org/doc/html/latest/process/handling-regressions.html)
- [kernel.org 문서: Reporting regressions](https://www.kernel.org/doc/html/latest/admin-guide/reporting-regressions.html)
- [KernelCI 블로그: Regzbot joins KernelCI](https://kernelci.org/blog/2026/05/04/regzbot-joins-kernelci-strengthening-linux-kernel-regression-tracking/)
- [kernel.org 문서: Stable kernel rules](https://www.kernel.org/doc/html/latest/process/stable-kernel-rules.html)
- [Linux 7.3 RC 회귀 테스트·드라이버 검증 자동화 설계](https://daewooki.github.io/posts/linux-kernel-rc-regression-pipeline/)
- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)
- [Linux 7.2.6 stable 릴리스: 작은 패치가 운영에선 큰 리스크가 되는 이유](https://daewooki.github.io/posts/linux-kernel-stable-rollout-contract/)
- [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)
- [PostgreSQL 19 RC 기간 확장에 맞춘 테스트 윈도우 재설계](https://daewooki.github.io/posts/postgresql-19-rc-window-redesign/)

[^1]: <https://www.kernel.org/>
[^2]: <https://www.kernel.org/releases.html>
[^3]: <https://lwn.net/Articles/1101143/>
[^4]: <https://kernelnewbies.org/Linux_7.3>
[^5]: <https://www.kernel.org/doc/html/next/process/2.Process.html>
[^6]: <https://kernel.org/doc/html/next/process/handling-regressions.html>
[^7]: <https://kernel.org/signature.html>
[^8]: <https://kernelci.org/blog/2026/05/04/regzbot-joins-kernelci-strengthening-linux-kernel-regression-tracking/>
[^9]: <https://cdn.kernel.org/doc/html/latest/process/stable-kernel-rules.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
