---
title: "Linux stable 커널 롤아웃 체크리스트: 7.2.4"
description: "stable 업데이트에서 중요한 건 변경점 나열이 아니라, 내 워크로드가 깨질 지점을 사전/사후로 증명하는 검증 템플릿입니다."
date: 2026-09-10 12:50:55 +0900
categories: ["News", "Systems"]
tags: ["linux-kernel", "stable", "rollout", "kexec", "cgroup-v2", "regression-testing"]
render_with_liquid: false
---

## 7.2.4 stable과 7.3-rc2: 이번 주가 위험한 이유

KST 2026-09-10 기준으로, 커널 릴리스 창이 동시에 열려 있습니다. [The Linux Kernel Archives](https://www.kernel.org/)에는 stable로 **7.2.4(2026-09-07)**, mainline으로 **7.3-rc2(2026-09-06)**가 같은 화면에 나란히 올라와 있습니다.[^1]

여기에 더해, stable 트리 미러로 보이는 [linux-kernel/linux-stable GitLab tags](https://gitlab.com/linux-kernel/stable/-/tags)에도 v7.2.4 태그가 2026-09-07로 게시돼 있습니다.[^2]

운영 관점에서 이 조합이 까다로운 이유는 단순합니다.

- stable 라인은 “적은 변경”을 표방하지만, 백포트가 누적될수록 실제로는 서브시스템 전체에 패치가 분산됩니다.
- mainline/rc가 빠르게 전진하는 시기에는, 드라이버/파일시스템/메모리/스케줄링 같은 저수준 변경이 더 자주 섞이고, stable로 내려오는 백포트도 늘어나는 경향이 있습니다.

그래서 커널 업데이트가 잦아질수록 중요해지는 건 “이번에 무엇이 바뀌었는지”가 아니라 “**우리의 어떤 워크로드에서 깨질 수 있는지, 그리고 그걸 배포 전에 어떻게 증명할지**”입니다.

## stable은 왜 안전하다고 말할 수 있고, 왜 그럼에도 깨지는가

-stable이 대체로 안전하다고 말할 근거는 커널 문서에 명시돼 있습니다. stable에 들어가는 패치는 원칙적으로 upstream(mainline)에 이미 존재하는 수정이어야 하고, “obviously correct and tested”를 요구하며, 크기도 제한합니다. 또한 security 패치는 별도 절차로 들어올 수 있다고 문서에 적혀 있습니다. [Everything you ever wanted to know about Linux -stable releases](https://www.kernel.org/doc/html/latest/process/stable-kernel-rules.html)[^3]

그런데 이 규칙은 “패치 단위의 위험”을 낮춰줄 뿐, “내 워크로드 단위의 위험”을 0으로 만들지 못합니다. 운영에서 커널 업데이트가 깨지는 전형적인 경로는 아래처럼 패치 자체가 나쁘다기보다 ‘내 환경의 특이성’에서 터집니다.

- out-of-tree 모듈(DKMS, vendor driver, eBPF probe, 보안 에이전트)이 커널 내부 API/ABI 변화에 민감하다.
- 특정 NIC 오프로딩/TSO/GRO 조합, 특정 스토리지 펌웨어, 특정 ACPI 테이블 같은 “이상하지만 존재하는” 조합에서만 재현되는 문제가 있다.
- cgroup v2 컨트롤러/PSI 기반의 리소스 제어를 적극 사용하면, 스로틀링/리클레임 타이밍 차이가 애플리케이션 SLA로 튄다.
- 파일시스템/블록 레이어의 버그픽스가 “정상 동작”을 바꾸면서, 오히려 기존의 우회 패턴이 실패로 바뀐다.

그래서 stable 롤아웃에서의 핵심 산출물은 changelog 요약이 아니라, **사전/사후 검증 결과(artifact)를 남기는 템플릿**입니다.

## 7.2.4 changelog를 ‘회귀 가능성 레이더’로 읽는 법

[ChangeLog-7.2.4](https://www.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.2.4)의 첫 커밋은 Greg Kroah-Hartman이 태깅한 “Linux 7.2.4”이며, Tested-by가 다수 붙어 있습니다.[^4]

여기서 중요한 포인트는 두 가지입니다.

1) “테스트가 있었다”는 사실은 신뢰도를 올리지만, 그 테스트가 내 프로덕션 워크로드를 대표하지는 않습니다.

2) stable changelog에서 운영자가 찾아야 하는 건 기능 추가가 아니라, 아래 같은 ‘회귀의 힌트’입니다.

- **Fixes:** 태그: 과거 커밋의 부작용을 되돌리는 경우가 많고, 그 과거 커밋이 내 환경에 이미 들어와 있었다면 영향 가능성이 커집니다.
- “broke”, “data corruption”, “hang”, “oops”, “race”, “leak” 같은 단어
- 특정 드라이버/버스/펌웨어/아키텍처 언급(arm-cmn, ACPI resource overlap 등)

7.2.4 changelog 초반부만 봐도 이런 유형이 보입니다.

- platform/chrome sensorhub: 경고 로그 스팸과 이벤트 드롭을 고친다는 커밋 메시지가 있고, “Invalid sensor number 255”가 flooding 됐다는 서술이 나옵니다. 이런 건 서버에 직접 해당이 없더라도, “로그 폭주 → 디스크/에이전트 부하 → 관측 계층 이상” 같은 2차 피해로 이어질 수 있습니다.[^4]
- ACPI scan: resource overlap 처리 로직이 arm-cmn 드라이버를 깨뜨린 사례를 되돌립니다. 즉, “잘못된 방어 로직”이 실존하는 드라이버 기대를 깨는 전형적인 회귀 패턴입니다.[^4]
- selftests/mm: sudo-rs가 상대경로를 canonicalize 하면서 selftest가 거짓 FAIL로 떨어지는 케이스가 들어 있습니다. 이건 프로덕션 커널 동작과는 거리가 있지만, CI/검증 파이프라인을 돌리는 운영 조직이라면 “검증 체계가 깨지는 회귀”가 됩니다.[^4]
- udf: 32-bit에서 __u64와 unsigned long 마스크로 상위 32비트가 날아가는 케이스를 고칩니다. 내가 32-bit 커널을 안 쓴다고 해도, 이런 부류는 “타입/마스크/오버플로” 계열 버그가 실제로 stable에 자주 들어온다는 시그널입니다.[^4]

내 경우엔 changelog를 읽을 때부터 “테스트 항목(드라이버/cgroup/network/fs)과 연결되는 키워드”를 먼저 뽑아냅니다. changelog를 다 읽고 체크리스트를 만드는 순서가 아니라, 체크리스트에 changelog를 매핑하는 방식입니다.

### changelog에서 ‘검증 범위’를 자동으로 뽑는 최소 커맨드

아래는 실제 운영에 쓸 수 있는 수준의 스캐폴딩입니다. 전제는 “업그레이드 후보 버전 범위를 고정(v7.2.3 → v7.2.4)”하고, 범위에서 위험 키워드를 잡아내는 것입니다.

```bash
# 의존성(예시, Ubuntu/Debian)
# sudo apt-get update && sudo apt-get install -y git ripgrep

set -euo pipefail

WORKDIR=${WORKDIR:-/tmp/kernel-stable-audit}
VER_FROM=${VER_FROM:-v7.2.3}
VER_TO=${VER_TO:-v7.2.4}

mkdir -p "$WORKDIR"
cd "$WORKDIR"

if [ ! -d linux-stable ]; then
  git clone --depth 1 --branch linux-7.2.y https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git linux-stable
fi

cd linux-stable

git fetch --tags --depth 1 origin "$VER_FROM" "$VER_TO" || true

# 1) 커밋 메시지 1줄 요약

git log --oneline "${VER_FROM}..${VER_TO}" > ../commits.oneline

# 2) Fixes/Closes/Reported-by/ 드라이버·파일시스템 키워드 필터

git log "${VER_FROM}..${VER_TO}" --pretty=format:'%H%n%s%n%b%n----' \
  | rg -n "^(Fixes:|Closes:|Reported-by:|Cc: stable@|Signed-off-by:)" -B1 -A1 \
  > ../commits.meta

# 3) 위험 키워드 히트

git log "${VER_FROM}..${VER_TO}" --pretty=format:'%H%n%s%n%b%n----' \
  | rg -n "\b(oops|hang|deadlock|data corruption|race|use-after-free|UAF|panic|BUG\(|warning|leak|overflow)\b" -i \
  > ../commits.riskwords || true

wc -l ../commits.oneline ../commits.meta ../commits.riskwords
```

예상되는 출력 형태는 대략 아래처럼 “라인 수 요약”으로 시작합니다.

```text
  3 ../commits.oneline
 98 ../commits.meta
 12 ../commits.riskwords
```

여기서 중요한 건 숫자 자체가 아니라, “riskwords가 한 줄이라도 잡혔다면 검증 케이스를 반드시 매핑한다”는 규칙을 조직에 박는 것입니다.

## ‘검증 가능한 롤아웃’의 정의: 증거(artifact) 중심 템플릿

운영에서 커널 업그레이드가 논쟁으로 흐르는 지점은 늘 비슷합니다.

- “문제 없을 것 같다” vs “문제 날 것 같다”
- “우리 서비스는 괜찮다” vs “저 서비스가 불안하다”

이걸 끝내려면, 주관을 줄이고 증거를 늘리는 수밖에 없습니다. 나는 커널 롤아웃을 “검증 가능한 방식”이라고 부르려면 최소한 아래 artifact가 남아야 한다고 봅니다.

- 업그레이드 전/후의 커널 버전, 커맨드라인, config 차이
- 업그레이드 전/후의 모듈 로딩 상태, out-of-tree 모듈 상태
- 업그레이드 전/후의 sysctl, cgroup 설정(특히 v2), 네트워크 오프로딩 설정
- 업그레이드 전/후의 핵심 워크로드 synthetic test 결과(fio/iperf3/latency probe)
- 부팅 직후/부하 중의 dmesg/journal에서 error/warn/oops 추출 결과

### artifact 수집 스크립트(프로덕션에 넣어도 되는 수준)

```bash
# 의존성(예시)
# sudo apt-get install -y jq fio iperf3 ethtool util-linux procps

set -euo pipefail

OUT=${OUT:-/var/tmp/kernel-rollout-artifacts}
TS=$(date -u +%Y%m%dT%H%M%SZ)
DIR="$OUT/$TS"

mkdir -p "$DIR"
chmod 0755 "$OUT" "$DIR"

# 커널/부팅 정보
uname -a | tee "$DIR/uname.txt"
cat /proc/cmdline | tee "$DIR/proc_cmdline.txt"

# 가능하면 config 보관(배포판 커널 대부분 제공)
if [ -r /proc/config.gz ]; then
  zcat /proc/config.gz > "$DIR/kernel_config"
fi

# 모듈/드라이버
lsmod | tee "$DIR/lsmod.txt"
modinfo -F vermagic $(awk 'NR>1 {print $1}' /proc/modules | head -n 50) 2>/dev/null \
  | head -n 200 > "$DIR/modinfo_vermagic_sample.txt" || true

# cgroup v2 마운트/컨트롤러
mount | grep cgroup | tee "$DIR/mount_cgroup.txt" || true
if [ -r /sys/fs/cgroup/cgroup.controllers ]; then
  cat /sys/fs/cgroup/cgroup.controllers | tee "$DIR/cgroup.controllers.txt"
  cat /sys/fs/cgroup/cgroup.subtree_control 2>/dev/null | tee "$DIR/cgroup.subtree_control.txt" || true
fi

# 네트워크: 링크/오프로딩
ip -details link show | tee "$DIR/ip_link_details.txt"
for dev in $(ls /sys/class/net | grep -v lo); do
  ethtool -k "$dev" > "$DIR/ethtool_k_${dev}.txt" 2>/dev/null || true
  ethtool -i "$dev" > "$DIR/ethtool_i_${dev}.txt" 2>/dev/null || true
  ethtool -S "$dev" > "$DIR/ethtool_S_${dev}.txt" 2>/dev/null || true
done

# sysctl 스냅샷(전체 덤프는 크므로 최소 핵심만)
sysctl -a 2>/dev/null | grep -E '^(net\.|vm\.|kernel\.)' > "$DIR/sysctl_core.txt" || true

# 로그: dmesg/journal 에러/워닝
(dmesg -T || dmesg) > "$DIR/dmesg_full.txt" || true
(dmesg -T || dmesg) | grep -Ei 'error|warn|oops|bug:|panic|taint' > "$DIR/dmesg_alerts.txt" || true

if command -v journalctl >/dev/null 2>&1; then
  journalctl -k -b --no-pager > "$DIR/journalctl_kern_full.txt" || true
  journalctl -k -b --no-pager | grep -Ei 'error|warn|oops|bug:|panic|taint' > "$DIR/journalctl_kern_alerts.txt" || true
fi

echo "artifact_dir=$DIR"
```

이 스크립트의 핵심은 완벽함이 아니라, “전/후 비교 가능한 최소 세트”를 지속적으로 남기는 것입니다. 커널 업그레이드에서 대부분의 분쟁은 재현이 아니라 기록 부재에서 시작합니다.

## 사전 검증 체크리스트: 드라이버 · cgroup · 네트워크 · 파일시스템

여기서부터는 “검증 항목 템플릿”입니다. 내 기준으로는, 커널 롤아웃 전 검증은 4개의 축으로 정리해야 합니다.

- 드라이버/모듈: 부팅과 I/O 경로를 만든다.
- cgroup v2: 리소스 제어의 상한/스로틀링을 만든다.
- 네트워크: 패킷 경로와 CPU 비용을 만든다.
- 파일시스템: 데이터 무결성과 지연시간을 만든다.

### 드라이버/모듈(특히 out-of-tree)

실무에서 커널 업그레이드 장애의 상당수는 “새 커널이 부팅은 되지만, 특정 장치/모듈이 누락되거나 성능이 폭락”으로 나타납니다. stable의 많은 패치가 드라이버 영역에 흩어져 들어온다는 점은 changelog가 그대로 보여줍니다.[^4]

사전 검증에서 반드시 확인할 것:

- initramfs/initrd에 필요한 모듈이 포함되는가(스토리지, NIC, 암호화)
- DKMS 모듈이 새 커널에 대해 빌드/로드되는가
- 커널 vermagic 불일치가 없는가
- firmware 로딩 실패 메시지가 새로 생기지 않았는가

검증 커맨드(부팅 직후):

```bash
uname -r

# DKMS 사용 시
if command -v dkms >/dev/null 2>&1; then
  dkms status || true
fi

# 부팅 실패를 부르는 빈번한 패턴
(dmesg -T || dmesg) | egrep -i 'firmware|failed to load|Unknown symbol|vermagic|taint' || true

# NVMe/블록 장치 확인(환경에 맞게 필터)
lsblk -o NAME,TYPE,SIZE,ROTA,MODEL,SERIAL,FSTYPE,MOUNTPOINTS
```

통과 기준을 문장으로 적으면 모호해집니다. 나는 “Unknown symbol 0건”, “firmware load fail 0건(예외 목록은 화이트리스트)”, “DKMS status가 installed”처럼 숫자로 적습니다.

### cgroup v2(리소스 제어가 곧 장애가 되는 지점)

컨테이너 워크로드에서 cgroup v2는 사실상 커널 업데이트의 충격을 가장 먼저 받는 영역입니다. 특히 memory.high는 OOM을 직접 트리거하지 않고, 스로틀링/리클레임 압력을 통해 작업을 느리게 만드는 성격이라, “죽지는 않는데 SLA가 깨지는” 장애로 변환되기 쉽습니다. [Control Group v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)[^5]

또한 io.max 같은 I/O 제어도 마찬가지로, 커널 내부의 IO cost 모델/스케줄링 변동이 사용자 체감 지연시간으로 바로 튑니다. 같은 문서에서 io.max의 의미를 명확히 정의합니다.[^5]

사전 검증에서 반드시 확인할 것:

- 노드가 unified hierarchy(cgroup v2)로 부팅되는가
- kubelet/container runtime이 기대하는 컨트롤러가 활성화돼 있는가
- memory.high 기반의 스로틀링이 “예상한 방식”으로 나타나는가

아래는 cgroup v2에서 memory.high를 강제로 밟아보는 최소 테스트입니다(루트 권한 필요).

```bash
set -euo pipefail

CG=/sys/fs/cgroup/kernel-precheck
sudo mkdir -p "$CG"

# memory controller가 활성화돼 있어야 함(환경에 따라 상위 트리 설정 필요)
# 예: echo "+memory" > /sys/fs/cgroup/cgroup.subtree_control

echo $((512*1024*1024)) | sudo tee "$CG/memory.high" >/dev/null
echo max | sudo tee "$CG/memory.max" >/dev/null

# 테스트 프로세스 실행: stress-ng가 없으면 python으로 대체 가능
if command -v stress-ng >/dev/null 2>&1; then
  sudo bash -c "echo $$ > $CG/cgroup.procs; stress-ng --vm 1 --vm-bytes 2G --timeout 20s" || true
else
  sudo bash -c "echo $$ > $CG/cgroup.procs; python3 - <<'PY'
import time
buf=[]
try:
  for _ in range(2048):
    buf.append(bytearray(1024*1024))
    time.sleep(0.01)
except Exception as e:
  print('err', e)
PY" || true
fi

# 결과 확인
cat "$CG/memory.current" || true
cat "$CG/memory.events" || true
```

통과 기준은 “아무것도 안 죽었다”가 아니라, memory.events가 high 이벤트를 기록하고, 시스템 전체 OOM으로 번지지 않는지, 그리고 노드의 핵심 프로세스가 예상치 못한 stall을 만들지 않는지입니다.

### 네트워크(성능 회귀는 패킷 경로에서 가장 빨리 온다)

네트워크는 회귀가 생겨도 에러 로그가 남지 않는 경우가 많습니다. 그래서 사전 검증은 synthetic test를 반드시 포함해야 합니다.

- throughput(iperf3)
- p99 latency(서비스 포트에서 실제로 측정)
- 드롭/리트랜스 증가(ethtool -S, ss -s)

간단한 예시(iperf3는 서버/클라이언트 쌍이 필요):

```bash
# 서버
iperf3 -s

# 클라이언트(동일 랙/동일 AZ 등 비교 가능한 구간에서)
iperf3 -c <server_ip> -P 8 -t 30 --json | jq '.end.sum_received.bits_per_second'

# 커널 업그레이드 전/후로 동일 조건 비교
ss -s
netstat -s 2>/dev/null | head -n 50 || true
```

네트워크 쪽은 “기준선 대비 -x% 이상 하락 시 중단” 같은 룰이 없으면, 결국 배포 이후에야 발견됩니다.

### 파일시스템/스토리지(무결성 + tail latency)

stable 패치에서 파일시스템은 늘 등장합니다. 7.2.4 changelog에도 UDF 같은 파일시스템 버그픽스가 포함됩니다.[^4]

프로덕션에서 더 자주 밟는 건 ext4/xfs/btrfs와 overlayfs(컨테이너 이미지 계층)인데, 테스트는 두 축이 필요합니다.

- 무결성: verify가 켜진 fio
- tail latency: iodepth/numjobs를 현실적으로 잡고 p99/p999 확인

아래 fio는 장난감이 아니라, “노드 로컬 NVMe/SSD가 있고, 실제로 랜덤 read/write를 섞는” 현실적인 설정으로 잡았습니다.

```bash
# 의존성
# sudo apt-get install -y fio

set -euo pipefail

TARGET_DIR=${TARGET_DIR:-/var/lib/kernel-precheck}
FILE=${FILE:-$TARGET_DIR/fio-verify.dat}
mkdir -p "$TARGET_DIR"

fio --name=randmix-verify \
  --filename="$FILE" \
  --size=8G \
  --ioengine=io_uring \
  --direct=1 \
  --rw=randrw \
  --rwmixread=70 \
  --bs=4k \
  --iodepth=32 \
  --numjobs=4 \
  --time_based=1 \
  --runtime=60 \
  --group_reporting=1 \
  --verify=crc32c \
  --verify_fatal=1 \
  --write_iops_log="$TARGET_DIR/fio_iops" \
  --write_lat_log="$TARGET_DIR/fio_lat" \
  --output="$TARGET_DIR/fio_output.txt"

tail -n 30 "$TARGET_DIR/fio_output.txt"
```

통과 기준은 “fio가 끝났다”가 아니라, verify error가 0이고, 업그레이드 전 대비 latency tail이 갑자기 튀지 않는지(특히 p99.9)입니다.

## 사후 검증 체크리스트: 부팅 직후 · 부하 중 · 장애 시 수습 루프

사후 검증은 대개 “정상 부팅 확인 → 끝”으로 축소되는데, 커널 회귀는 종종 부하를 걸고 몇 분~몇 시간 뒤에야 드러납니다. 그래서 사후 검증은 3단계로 고정하는 게 낫습니다.

1) 부팅 직후(5분 이내)
- dmesg/journal alert 0건(화이트리스트 제외)
- 주요 인터럽트 폭주/soft lockup 징후 0건
- 필수 데몬 정상(스토리지/네트워크/관측 에이전트)

2) 부하 중(최소 30~60분)
- synthetic: fio/iperf3 반복
- 실제 트래픽: canary 노드에 일부 비율을 실어 p95/p99 비교

3) 장애 시 수습(rollback이 “가능한 상태”인지)
- 이전 커널로 즉시 부팅 가능한가
- crash dump 수집 체계가 살아 있는가(kdump)

여기서 kdump는 단순한 디버깅 도구가 아니라, “업그레이드로 패닉이 났을 때 원인 규명이 가능한가”를 좌우합니다. 커널 문서는 kdump가 kexec를 사용해 dump-capture kernel로 빠르게 부팅하고 vmcore를 확보한다고 설명합니다. [Documentation for Kdump](https://kernel.org/doc/html/latest/admin-guide/kdump/kdump.html)[^6]

## kexec를 ‘롤아웃 도구’로 쓸 때의 조건과 함정

커널 롤아웃에서 kexec를 쓰자는 주장은 대개 “재부팅이 빠르다”로 끝나지만, 운영에서 중요한 건 속도가 아니라 예측 가능성입니다.

kexec의 본질은 “메모리에 다음 커널을 로드한 뒤, 펌웨어 초기화 과정을 건너뛰고 커널로 점프”입니다. man page도 바이오스/펌웨어 초기화가 수행되지 않는다는 점을 명시합니다. [kexec(8)](https://man7.org/linux/man-pages/man8/kexec.8.html)[^7]

즉, kexec는 아래 조건을 만족할 때만 롤아웃에서 의미가 있습니다.

- 서버급 장비/가상머신처럼, 펌웨어 리셋을 건너뛰어도 장치 상태가 안정적으로 초기화되는 환경
- “빠른 재부팅으로 canary 반복 횟수를 늘리고 싶다”는 명확한 목적
- 문제 발생 시 full reboot로 전환하는 가드레일

systemd를 쓰는 배포판이라면 kexec는 kexec.target로 노출돼 있고, systemctl kexec로 트리거 가능합니다. [systemd-kexec.service(8)](https://manpages.debian.org/testing/systemd/systemd-kexec.service.8.en.html), [systemd.special(7)](https://www.man7.org/linux/man-pages/man7/systemd.special.7.html), [systemctl(1)](https://man7.org/linux/man-pages/man1/systemctl.1.html)[^8]

### kexec 기반 재부팅의 현실적인 절차(커널 롤아웃 관점)

아래는 “다음 커널을 미리 로드하고”, “기존 /proc/cmdline을 재사용해 부팅 파라미터 차이로 인한 변수를 줄이고”, “systemd를 통해 shutdown 스크립트를 태운 뒤 kexec”로 넘기는 형태입니다.

```bash
# 전제: /boot에 신규 커널과 initrd가 배치돼 있고, root 권한
# CONFIG_KEXEC가 활성화돼 있어야 함

set -euo pipefail

VMLINUX=/boot/vmlinuz-7.2.4
INITRD=/boot/initrd.img-7.2.4
CMDLINE=$(cat /proc/cmdline)

sudo kexec -l "$VMLINUX" --initrd="$INITRD" --append="$CMDLINE"

# systemd가 있으면 shutdown 경로를 태우는 게 운영적으로 안전
sudo systemctl kexec
```

나는 kexec를 “전체 롤아웃을 빠르게 만든다”기보다는, “canary에서 재부팅-검증 루프를 더 많이 돌린다”에만 제한해서 씁니다. 특히 NIC/스토리지 드라이버 변경이 보이는 stable 업데이트에서는 kexec가 오히려 리스크가 될 수 있습니다. 펌웨어 리셋이 없는 상태에서 장치가 애매하게 남는 경우가 있기 때문입니다.

## 회의론: stable은 원래 안전한데 체크리스트가 과한가

이 질문에 답하려면 stable의 규칙과, 운영의 현실을 분리해야 합니다.

- stable은 “upstream에 있는 명백한 버그픽스”를 백포트하는 데 최적화돼 있습니다. 문서도 그렇게 말합니다.[^3]
- 하지만 운영의 실패는 버그픽스 자체가 아니라, **워크로드 특이성**과 **검증 공백**에서 나옵니다.

그리고 커널 커뮤니티도 “회귀(regression)”를 별도의 범주로 강하게 다룹니다. 회귀 보고/추적을 위한 문서가 따로 있고, regzbot 같은 봇을 언급합니다. [Reporting regressions](https://www.kernel.org/doc./html/next/admin-guide/reporting-regressions.html)[^9]

regzbot 문서 역시 “회귀가 커널에서 깨진 것”이며, 추적을 위해 메일에 #regzbot introduced 같은 커맨드를 넣는 절차를 설명합니다. [regzbot getting started](https://github.com/kernelci/regzbot/blob/main/docs/getting_started.md)[^10]

운영 체크리스트는 커널 커뮤니티의 회귀 대응을 대신하려는 게 아니라, 내 조직이 **회귀를 ‘발견 가능한 상태’로 만들기 위한 준비**입니다.

## 앞으로 지켜볼 것: stable cadence가 빨라질수록 조직이 바꿔야 할 것

내가 보는 관전 포인트는 두 가지입니다.

1) stable 릴리스 간격이 좁아질수록, “업그레이드 안 함”은 더 이상 리스크 회피가 아니라 리스크 누적이 됩니다.

2) 업그레이드가 잦아지면, 배포 자체보다 검증/롤백 자동화가 병목이 됩니다.

이 시점에 stable과 mainline/rc의 간극이 커지는 건 운영 입장에서 자연스럽게 “어느 버전을 기준선으로 삼을지” 고민을 만들고, 결과적으로 canary/관측 체계의 중요도를 끌어올립니다. kernel.org가 같은 화면에서 stable(7.2.4)과 mainline(7.3-rc2)을 동시에 보여주는 것도 이 긴장 관계를 잘 드러냅니다.[^1]

## 7.2.4 롤아웃에 바로 적용 가능한 사전/사후 검증 템플릿

여기까지를 문서로만 끝내면 다시 메타 논쟁으로 돌아갑니다. 그래서 아래는 “체크리스트를 체크했는지”가 아니라 “검증 결과가 artifact로 남는지”에 초점을 둔 템플릿입니다.

### 1) 변경 관리 단위(티켓/PR)에 반드시 포함할 필드

- target_kernel: 7.2.4
- from_kernel: (예: 7.2.3)
- scope: (노드 풀/클러스터/역할)
- workload_profile: (예: Kubernetes worker + NVMe + eBPF observability)
- rollback_plan: (이전 커널 선택 가능 여부, grub default 변경 방식, 자동 롤백 조건)
- artifacts:
  - pre: artifact 디렉터리 경로
  - post: artifact 디렉터리 경로
- pass_fail_criteria:
  - dmesg_alerts == 0 (whitelist 제외)
  - fio verify error == 0
  - iperf3 bps >= baseline * 0.9
  - service p99 latency <= baseline + 10%

### 2) 사전 검증(Pre-flight) 체크리스트

- 드라이버/모듈
  - DKMS status: installed
  - dmesg firmware load fail: 0건(화이트리스트 제외)
  - lsmod 필수 모듈 존재: ok
- cgroup v2
  - /sys/fs/cgroup/cgroup.controllers 존재: yes
  - memory.high 테스트: high 이벤트 발생 + 시스템 OOM 없음
  - io.max 적용된 워크로드: 예상대로 제한(샘플 job으로 검증)
- 네트워크
  - ethtool -k 변경점 비교: offload 플래그가 튀지 않음
  - iperf3 throughput: 기준선 대비 -10% 이내
- 파일시스템/스토리지
  - fio verify: 0 error
  - iostat/util: 기준선 대비 급상승 없음

cgroup v2의 리소스 제어 의미 자체는 커널 문서에 정의돼 있으니, 적어도 memory.high/io.max는 문서 기반으로 “무엇을 테스트하는지”가 명확해야 합니다.[^5]

### 3) 롤아웃 단계(Canary → Batch → Fleet)

- Canary(예: 1% 또는 역할별 1대)
  - full reboot 사용(초기에는 kexec를 배제)
  - 60분 관찰 + synthetic 반복
- Batch(예: 10%)
  - 야간/저부하 시간
  - canary 기준선이 유지될 때만 진행
- Fleet
  - 서비스별 SLO 가드레일을 모니터링에 연결

kexec는 “재부팅 루프를 늘려서 검증 횟수를 늘리려는 목적”일 때만 제한적으로 들어가야 하고, 장치 초기화 리스크는 kexec 문서의 특성(펌웨어 초기화 생략)을 근거로 인정해야 합니다.[^7]

### 4) 사후 검증(Post-flight) 체크리스트

- 즉시
  - artifact 수집 스크립트 실행(전/후 비교 가능하게)
  - dmesg/journal alerts 0건
  - 필수 데몬 health ok
- 60분
  - fio/iperf3 반복
  - 실제 트래픽 p95/p99 비교
- 24시간
  - 재부팅/커널 패닉 0
  - kdump 설정 유지(패닉 시 vmcore 확보 가능)

kdump가 kexec 기반으로 패닉 시 dump-capture kernel로 부팅해 vmcore를 확보하는 동작은 커널 문서에 명확히 설명돼 있으니, “업그레이드가 위험한 이유”를 기술적으로 설득할 때 이 링크가 유용합니다.[^6]

## 결론: stable 릴리스가 잦을수록, 배포의 품질은 체크리스트의 품질로 수렴한다

7.2.4는 2026-09-07에 stable로 게시됐고, 7.3-rc2는 2026-09-06에 mainline로 게시됐습니다. 이 시기엔 변경점 자체보다 “내 워크로드에서 깨질 수 있는 경로”를 사전/사후로 증명하는 템플릿이 더 큰 가치를 가집니다.[^1]

나는 커널 업그레이드를 ‘릴리스 노트를 잘 읽는 이벤트’가 아니라, artifact가 남는 검증 파이프라인으로 취급합니다. 커널 stable이 더 자주 나올수록, 이 관점은 선택이 아니라 기본 운영 역량으로 굳어집니다.

## 참고 자료

- [The Linux Kernel Archives 최신 릴리스 목록](https://www.kernel.org/)
- [Linux 7.2.4 ChangeLog](https://www.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.2.4)
- [linux-kernel/linux-stable GitLab tags](https://gitlab.com/linux-kernel/stable/-/tags)
- [The Linux Kernel Archives(cdn.kernel.org 정렬 페이지)](https://cdn.kernel.org/?s=desc)
- [Everything you ever wanted to know about Linux -stable releases](https://www.kernel.org/doc/html/latest/process/stable-kernel-rules.html)
- [Control Group v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)
- [Reporting regressions](https://www.kernel.org/doc./html/next/admin-guide/reporting-regressions.html)
- [regzbot getting started](https://github.com/kernelci/regzbot/blob/main/docs/getting_started.md)
- [Documentation for Kdump](https://kernel.org/doc/html/latest/admin-guide/kdump/kdump.html)
- [kexec(8)](https://man7.org/linux/man-pages/man8/kexec.8.html)
- [systemd-kexec.service(8)](https://manpages.debian.org/testing/systemd/systemd-kexec.service.8.en.html)
- [Docker Desktop 4.55·GKE Stable 1.33.5 업그레이드/공급망 정리 글](https://daewooki.github.io/posts/docker-desktop-4552025-12-16gke-stable-1-3/)

[^1]: <https://www.kernel.org/?lan=english>
[^2]: <https://gitlab.com/linux-kernel/stable/-/tags>
[^3]: <https://www.kernel.org/doc/html/latest/process/stable-kernel-rules.html>
[^4]: <https://www.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.2.4>
[^5]: <https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html?highlight=freezer>
[^6]: <https://kernel.org/doc/html/latest/admin-guide/kdump/kdump.html>
[^7]: <https://man7.org/linux/man-pages/man8/kexec.8.html>
[^8]: <https://manpages.debian.org/testing/systemd/systemd-kexec.service.8.en.html>
[^9]: <https://www.kernel.org/doc./html/next/admin-guide/reporting-regressions.html>
[^10]: <https://github.com/kernelci/regzbot/blob/main/docs/getting_started.md>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
