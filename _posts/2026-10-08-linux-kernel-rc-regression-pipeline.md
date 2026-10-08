---
title: "Linux 7.3 RC 회귀 테스트·드라이버 검증 자동화 설계"
description: "RC 커널은 기능보다 회귀 대응이 핵심입니다. 부팅/네트워크/스토리지 최소 세트, eBPF·LSM·컨테이너 조합, kexec 롤백 canary를 한 파이프라인으로 묶습니다."
date: 2026-10-08 11:36:39 +0900
categories: ["Systems", "Linux Kernel"]
tags: ["linux-kernel", "regression-testing", "canary-rollout", "kexec", "ebpf"]
render_with_liquid: false
---

## RC를 프로덕션에 들이기 전, 목표를 다시 정의합니다

2026-10-08 KST 시점에 kernel.org의 mainline은 v7.3-rc6이고, 태그 날짜는 2026-10-04로 표시됩니다.[^1]

RC에서 중요한 것은 새 기능을 따라가는 속도가 아니라, 내 환경에서 발생하는 회귀를 얼마나 빨리 잡아내고, 얼마나 싸게 되돌릴 수 있는지입니다. 내가 운영에서 RC를 만질 때의 기준은 단순합니다.

- “부팅이 된다”는 수준이 아니라, **부팅 이후에 필수 기능이 일정 시간 안에 정상 상태로 수렴**해야 합니다.
- 드라이버는 “모듈이 로드된다”가 끝이 아니라, **디바이스 열거·링크 업·I/O·리셋 경로**까지 봐야 합니다.
- eBPF/LSM/컨테이너 런타임은 개별 컴포넌트가 아니라 조합에서 터집니다. 특히 BTF/CO-RE, LSM stacking, cgroup v2, overlayfs, seccomp, network namespace가 한 묶음입니다.
- 롤백은 문서상 플랜이 아니라, 자동화된 버튼이어야 합니다. 부팅 이전 실패(커널 패닉/드라이버 하드락)와 부팅 이후 실패(기능 회귀)를 나눠서 경로를 설계해야 합니다.

이 글은 v7.3-rc6 “소스 변경점 소개”가 아니라, RC를 받아서 정식 릴리스 대응 속도를 끌어올리는 테스트/검증 시스템 설계에 집중합니다.

관련해서 stable 커널 롤아웃의 운영 계약(무엇을 보장해야 하는지)과 체크리스트는 예전에 정리해 둔 글이 있어서 반복하지 않습니다.

- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)
- [Linux 7.2.6 stable 릴리스: 작은 패치가 운영에선 큰 리스크가 되는 이유](https://daewooki.github.io/posts/linux-kernel-stable-rollout-contract/)

---

## 전체 파이프라인을 “링”으로 나눕니다: 빨리 실패시키는 구조

RC 검증은 모든 것을 한 번에 돌리는 형태로 가면 항상 망합니다. 오래 걸리고, 실패했을 때 원인 분리가 안 되고, 어느 순간부터는 “이번 주는 바빠서 스킵”이 됩니다.

나는 RC 검증을 다음 링으로 분해해서 설계합니다.

1. Ring-0 (Smoke): 5~10분 내로 끝나는 부팅/네트워크/스토리지 최소 세트
2. Ring-1 (Subsystem): kselftest를 중심으로 net/bpf/filesystem 등 핵심 타깃만 선별
3. Ring-2 (Integration): eBPF+LSM+컨테이너 런타임 조합 회귀
4. Ring-3 (Soak/Load): fio/네트워크 부하/컨테이너 churn 같은 지속 부하
5. Ring-4 (Canary): 실제 프로덕션 워크로드의 아주 작은 비율로 관찰 + 롤백 자동화

kselftest는 커널 소스 트리의 `tools/testing/selftests/` 아래에 있고, 개별 코드 경로를 작게 찌르는 형태의 테스트 집합으로 설명됩니다. 또한 mainline의 kselftest를 stable에서도 돌리는 “test rings” 운영이 존재한다는 점을 문서가 직접 언급합니다.[^2]

여기서 핵심은 “전 링이 통과하면 다음 링으로 올라간다”는 gate를 만드는 겁니다. Ring-0가 실패하는데 Ring-2를 돌리는 건 비용만 태웁니다.

운영 관점에서 RC 파이프라인이 가져야 하는 기능은 네 가지입니다.

- 재현성: 커널 아티팩트(이미지/모듈/headers)와 테스트 아티팩트를 묶어 보관
- 관측성: 실패했을 때 dmesg, journal, 장치 상태를 자동 수집
- 격리성: 실패한 노드를 자동으로 제외(quarantine)해 다음 단계 오염 방지
- 복구성: 롤백 경로(kexec + 부트로더 fallback + 원격 전원 제어)를 자동화

---

## 커널 RC 아티팩트 전략: “빌드”보다 “식별 가능성”

RC는 배포 가능한 형태로 만들었을 때부터 운영 대상이 됩니다. tarball을 받아서 로컬에서 `make` 하는 수준이면, 실패했을 때 “그때 그 커밋이 뭐였지?”가 됩니다.

권장 구조는 다음처럼 단순하게 잡습니다.

- source: `linux.git`에서 tag checkout (예: `v7.3-rc6`)
- build output: 동일한 `.config`와 toolchain으로 재빌드 가능해야 함
- package: 배포 단위는 distro 패키지(deb/rpm) 또는 전용 initramfs bundle
- provenance: 커널 버전 문자열에 CI 빌드 번호/짧은 git SHA를 박아 추적

v7.3-rc6가 실제로 tag로 존재한다는 근거는 tag 정보에서 확인할 수 있습니다.[^3]

### 예시: Debian 계열에서 RC 커널을 패키징(현실적인 기본형)

아래는 “장난감 예제”가 아니라, 실제로 서버 팜에서 굴리기 쉬운 기본형입니다.

- 빌드 머신: Ubuntu/Debian
- 결과물: `linux-image-*.deb`, `linux-modules-*.deb`, `linux-headers-*.deb`

```bash
# 0) 소스 확보 (tag 고정)
mkdir -p ~/src && cd ~/src
git clone --depth=1 --branch v7.3-rc6 https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git linux-7.3-rc6
cd linux-7.3-rc6

# 1) config 준비
# - 프로덕션에서 쓰는 config를 기반으로 시작하고
# - RC 검증용으로 KASAN/LOCKDEP 같은 디버그 옵션을 켠 별도 flavor를 하나 더 둡니다.
cp /boot/config-$(uname -r) .config
yes "" | make olddefconfig

# 2) 버전 식별자 추가 (빌드 번호/짧은 SHA)
# LOCALVERSION에 CI 식별자를 박아두면, dmesg 한 줄로 추적됩니다.
export LOCALVERSION="-rcpipe+$(git rev-parse --short HEAD)"

# 3) 패키지 빌드 (멀티코어)
# build-essential, flex, bison, libssl-dev, libelf-dev, dwarves(pahole) 등 필요
make -j"$(nproc)" bindeb-pkg

# 4) 산출물 확인
ls -al .. | egrep 'linux-(image|modules|headers).*\.deb'
```

예상 출력은 환경마다 다르지만 최소한 `../linux-image-7.3.0-rc6...deb` 같은 형태의 아티팩트가 생성됩니다.

이 단계에서 중요한 포인트는 “패키지를 만들었다”가 아니라, **동일한 입력으로 동일한 커널을 다시 만들 수 있게** 입력(소스 tag, .config, toolchain, 빌드 스크립트)을 통제하는 것입니다.

---

## (1) 부팅/네트워크/스토리지 최소 검증 세트: 실패를 10분 안에 확정합니다

Ring-0는 RC를 “프로덕션에 넣어도 되는가”가 아니라 “다음 링을 돌릴 자격이 있는가”를 판정합니다. 여기서 자주 나오는 실패는 다음입니다.

- 부팅이 멈춘다(early boot hang, initramfs, rootfs 마운트, IRQ/ACPI, GPU 콘솔)
- NIC가 링크 업은 되는데 DHCP/ARP/IPv6에서 이상이 생긴다
- 스토리지가 보이지만, multipath/NVMe reset/queueing에서 오류가 난다

검증 세트는 최소한으로 유지하되, 운영에서 페이지를 부르는 지점을 정확히 찌릅니다.

### Boot smoke: “서비스가 떠 있다”를 기계적으로 증명

운영에서 의미 있는 “부팅 성공” 기준을 다음처럼 정의합니다.

- systemd가 `multi-user.target`까지 도달
- root filesystem이 read-write로 전환
- `dmesg`에 Oops/BUG/panic 급 이벤트가 없음
- `/sys/kernel/tainted` 값이 의도치 않게 올라가지 않음

이건 커널 회귀가 있을 때 가장 싸게 깨지는 지표입니다.

예시로, 부팅 직후 실행되는 systemd unit을 하나 박아둡니다.

`/usr/local/sbin/rc-smoke.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

OUT=/var/log/rc-smoke
mkdir -p "$OUT"

# 1) 커널 식별
uname -a | tee "$OUT/uname.txt"
cat /proc/cmdline | tee "$OUT/cmdline.txt"

# 2) systemd 상태
systemctl is-system-running --wait | tee "$OUT/systemd-state.txt"
systemctl --failed | tee "$OUT/systemd-failed.txt" || true

# 3) 커널 taint
cat /sys/kernel/tainted | tee "$OUT/tainted.txt"

# 4) dmesg에서 치명 이벤트 탐지(가벼운 룰)
dmesg -T | tee "$OUT/dmesg.txt"
if dmesg -T | egrep -i "Kernel panic|Oops|BUG:|Unable to handle|rcu_sched detected stalls"; then
  echo "FATAL: kernel log indicates crash" | tee "$OUT/fatal.txt"
  exit 2
fi

echo "OK" | tee "$OUT/ok.txt"
```

`/etc/systemd/system/rc-smoke.service`

```ini
[Unit]
Description=Kernel RC smoke test
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/rc-smoke.sh

[Install]
WantedBy=multi-user.target
```

Ring-0에서 중요한 건 “정교한 판단”이 아니라 “확실한 실패 판정”입니다. 애매하면 일단 실패로 처리하고, 원인을 사람이 봅니다.

### Network smoke: L2/L3/L4를 각 1개씩만 증명

네트워크는 테스트 범위를 욕심내면 끝이 없습니다. Ring-0에서는 다음만 잡습니다.

- L2: 링크 업 + 에러 카운터 급증 없음 (`ethtool -S`)
- L3: default route 확보 + ICMP 1-hop, 2-hop 성공
- L4: TCP connect가 되는지(예: test endpoint 443/22) + DNS resolve

여기서 실패하면 Ring-2의 컨테이너 네트워킹은 의미가 없습니다.

### Storage smoke: “마운트/쓰기/동기화”를 짧게

스토리지 회귀는 드라이버, 블록 레이어, filesystem, NVMe quirks 등 어디서든 나옵니다. Ring-0에서 다음만 봅니다.

- 블록 디바이스 열거가 정상 (`lsblk -o NAME,SIZE,TYPE,MODEL,SERIAL`)
- 핵심 볼륨 1개를 마운트/언마운트
- 작은 fio job으로 write + fsync

예시 fio job:

```ini
; /root/fio-smoke.fio
[global]
ioengine=libaio
direct=1
runtime=20
time_based=1
group_reporting=1

[fsync-smoke]
filename=/mnt/testvol/.fio-smoke
rw=randwrite
bs=4k
iodepth=4
numjobs=1
size=256M
fsync=1
```

실행:

```bash
mount /dev/<your_device> /mnt/testvol
fio /root/fio-smoke.fio
umount /mnt/testvol
```

Ring-0에서 fio를 오래 돌리면 Ring-3와 역할이 겹칩니다. 20초~1분 안에서 “즉사하는 회귀”만 잡습니다.

---

## 드라이버 검증 자동화: “디바이스가 살아 있다”를 데이터로 비교합니다

드라이버 회귀는 두 가지 형태로 자주 옵니다.

- 하드 실패: 부팅 중 hang/panic (보통 스토리지/NIC/GPU/ACPI)
- 소프트 실패: 부팅은 되지만 특정 장치 기능이 죽음(링크 플랩, DMA 에러, suspend/resume, SR-IOV VF 생성 실패)

자동화에서 어려운 부분은 “정답이 환경마다 다르다”는 점입니다. 그래서 나는 드라이버 검증을 절대값 기준이 아니라 **기준 커널(reference kernel) 대비 변화 탐지**로 설계합니다.

### 장치 열거 레퍼런스: kselftest의 devices/exist를 적극적으로 씁니다

커널 문서에는 kselftest 기반으로 “known-good kernel에서 reference를 생성하고, 이후 커널에서 존재 여부를 비교하는” 형태의 device testing이 설명되어 있습니다.[^4]

이 방식은 운영에 잘 맞습니다.

- 레퍼런스는 내 장비 풀마다 1번만 만들면 됨
- 이후 RC가 바뀌어도 “사라진 디바이스 노드/경로”를 빨리 잡음

실제로는 다음 흐름으로 굴립니다.

1. LKG(last known good) 커널에서 레퍼런스 생성
2. RC 커널에서 exist 테스트 실행
3. diff 결과를 실패 조건으로 반영(단, 허용 목록 allowlist 적용)

여기서 “allowlist”가 중요합니다. 예를 들어 커널 버전이 바뀌면 모듈 이름이나 sysfs 경로 일부가 바뀌는 경우가 있습니다. 그런 변화는 실패로 잡되, 한 번 승인되면 allowlist에 넣고 다음부터는 노이즈가 되지 않게 해야 합니다.

### 모듈/펌웨어 로드 관측: 성공/실패를 구조화

dmesg grep만으로는 부족합니다. 최소한 다음은 구조화해서 저장합니다.

- `lsmod` 스냅샷
- `modinfo <driver>`의 버전/alias
- `/lib/firmware` 로딩 실패 메시지(자주 놓침)
- PCIe AER/EEH 같은 하드웨어 에러 카운터

운영에서 의미 있는 체크는 보통 “이 NIC가 XDP를 켜고도 RX drop이 안 늘어났나”, “이 HBA가 queue depth 협상에 실패하지 않았나” 같은 구체적인 지표인데, 그건 Ring-3나 canary에서 봅니다. Ring-0/1에서는 “장치가 보이고, 핵심 인터페이스가 up 되고, 최소 I/O가 된다”만 보장하면 됩니다.

---

## (2) eBPF/LSM/컨테이너 런타임 조합 회귀: 단일 테스트가 아니라 ‘교차점’을 찌릅니다

내 경험상 커널 RC에서 실제 사고로 이어지는 회귀는 “eBPF만”, “컨테이너만”처럼 단독으로 터지기보다, 다음 교차점에서 나옵니다.

- BTF/CO-RE + bpftool/libbpf + 커널 타입 변화
- LSM stacking + securityfs + 컨테이너 파일 접근/exec 경로
- cgroup v2 + namespaces + overlayfs + seccomp
- (CNI가 eBPF 기반이면) TC/XDP hook + conntrack + iptables/nftables

이 교차점을 빠르게 검증하는 현실적인 방법은 커널이 제공하는 selftests를 활용해 “내가 감당 가능한 subset”을 고르는 것입니다.

### kselftest를 CI에서 실패 조건으로 다루는 방법

kselftest 문서는 subset 실행을 `TARGETS`로 제어할 수 있고, 설치 후에는 `run_kselftest.sh`로 실행할 수 있다는 점을 명시합니다.[^2]

특히 CI에서 유용한 옵션이 `FORCE_TARGETS=1`입니다. 기본 동작은 “하나라도 빌드되면 성공”이기 때문에, CI에서는 부분 실패를 놓치기 쉽습니다. 문서에서 `FORCE_TARGETS=1`을 주면 타깃 빌드 실패 시 즉시 실패하도록 바뀐다고 설명합니다.[^2]

빌드 머신에서 테스트 번들을 만들어 배포하는 흐름은 다음이 기본형입니다.

```bash
# 커널 소스 트리에서 selftests 설치 번들 생성
cd ~/src/linux-7.3-rc6
make -C tools/testing/selftests install INSTALL_PATH=/opt/kselftest

# /opt/kselftest 디렉터리를 tar로 묶어 아티팩트로 보관
tar -C /opt -czf kselftest-v7.3-rc6.tar.gz kselftest
```

DUT(테스트 대상 노드)에서는:

```bash
mkdir -p /opt
tar -C /opt -xzf kselftest-v7.3-rc6.tar.gz
cd /opt/kselftest

# 예시: net + bpf만 실행
./run_kselftest.sh -c net -c bpf
```

여기서 kselftest 전체를 돌리면 항상 시간이 폭발합니다. 운영 조직이 감당할 수 있는 subset부터 시작해, 실패를 많이 잡아내는 타깃 위주로 늘리는 게 맞습니다.

### BPF selftests: “config 정렬”이 통과율을 좌우합니다

BPF 쪽은 특히 통과율이 커널 config에 크게 의존합니다. 커널 문서는 BPF selftests를 최대한 통과시키려면 커널 `.config`가 `tools/testing/selftests/bpf`의 config fragment와 최대한 맞아야 한다고 명시합니다.[^5]

BPF selftests는 `test_progs`를 중심으로 구성되고, `vmtest.sh` 같은 실행 스크립트가 있다는 내용도 selftests README에 정리되어 있습니다.[^6]

운영 파이프라인에서는 두 가지 모드로 나눠서 가져가는 편이 안전합니다.

- Host mode: 실제 DUT에서 `test_progs`를 돌려 “내 커널/내 하드웨어”에서 깨지는지 본다.
- VM mode: QEMU VM 기반으로 빠르게 반복하며, 커널 config/툴체인 문제를 분리한다.

Host mode는 리소스를 먹고 flaky할 수 있습니다. 대신 “프로덕션에서 깨질 회귀”를 잘 잡습니다.

### LSM BPF: BTF, attach/detach, hook 경로를 테스트합니다

LSM BPF Programs 문서는 `/sys/kernel/btf/vmlinux`를 build/deploy 환경이 일치할 때 BTF 입력으로 쓸 수 있고, `bpftool`로 `vmlinux.h`를 생성하는 흐름을 설명합니다. 또한 `bpftool gen skeleton`으로 skeleton header를 만들고, libbpf helper로 로드/attach하는 방식도 예시로 나옵니다.[^7]

RC 회귀에서 자주 보는 유형이 “이전에는 로드되던 BPF 프로그램이 verifier에서 거부된다”입니다. 이건 커널이 바뀌면서 verifier 룰이 바뀌거나, BTF 타입 정보가 달라지면서 CO-RE relocation이 깨지는 형태로 나옵니다.

그래서 Ring-2에서는 다음을 조합으로 봅니다.

- (1) BTF 존재: `/sys/kernel/btf/vmlinux`가 있고 bpftool이 읽는다
- (2) 최소 LSM BPF 프로그램 attach: 예를 들어 `lsm/file_mprotect` 같은 훅에 attach/detach가 된다
- (3) 컨테이너에서 exec/mount/file access 경로를 거칠 때 정책이 기대대로 동작한다

LSM BPF 문서는 detach가 `bpf_link__destroy`로 가능하다는 점도 명시합니다. 이건 “테스트가 시스템을 오염시키지 않고 원복할 수 있나”를 설계할 때 꽤 중요합니다.[^7]

### 컨테이너 런타임 회귀: runC 성공 여부가 아니라 “커널 기능 사용 경로”

컨테이너 런타임은 결국 커널 기능 조합입니다.

- namespaces (pid/net/mount/user)
- cgroup v2
- overlayfs
- seccomp
- LSM(AppArmor/SELinux/BPF LSM 등)

Ring-2에서 내가 최소로 확인하는 체크는 다음과 같습니다.

1. 컨테이너가 뜬다 (OCI lifecycle)
2. overlayfs 기반 rootfs에서 파일 I/O가 된다
3. veth + namespace 기반 통신이 된다
4. cgroup v2로 CPU/memory 제한이 먹는다
5. (사용한다면) LSM 정책이 컨테이너 안/밖에서 기대대로 enforce된다

Kubernetes 전체 e2e를 돌리는 건 Ring-4 canary에서나 의미가 있습니다. Ring-2는 “커널/런타임 조합 회귀”를 빠르게 찾는 데 초점을 둡니다.

---

## (3) kexec/롤백 경로를 포함한 canary 설계: 실패를 ‘복구 가능한 실패’로 바꿉니다

RC를 프로덕션에 넣는 순간부터 문제는 기술이 아니라 운영 리스크가 됩니다. 리스크를 줄이는 방법은 하나뿐입니다.

- 실패가 나더라도 자동으로 되돌아올 것
- 실패한 노드가 영향 범위를 확장시키지 않을 것

여기서 롤백은 두 층입니다.

1. 부트로더 기반 롤백: “다음 부팅에서 LKG로 돌아간다”
2. 런타임 기반 롤백: “지금 커널에서 즉시 LKG로 갈아탄다(kexec)”

### kexec를 롤백 도구로 쓰는 이유와 한계

`kexec`는 현재 실행 중인 커널에서 다음 커널 이미지를 로드해 두고(loading), 재부팅 없이 그 커널로 점프(execution)하는 메커니즘입니다. 사용자 공간 도구는 `kexec(8)`로 제공됩니다.[^8]

운영에서 kexec가 유용한 경우는 다음입니다.

- Ring-0/1/2 테스트에서 “이 커널은 아닌 것 같다”가 확정되면, 빠르게 LKG로 되돌려 노드 수용량을 복구
- 원격지 장비에서 재부팅 시간이 비싼 환경(펌웨어 POST가 긴 서버, 원격 전원 제어가 느린 장소)

다만 한계는 명확합니다.

- 커널이 부팅 초기에 멈추거나 hard lock이 걸리면 kexec까지 도달하지 못합니다.
- kexec 경로 자체도 커널 기능이므로, kexec가 회귀하면 롤백 경로가 같이 죽을 수 있습니다.

그래서 kexec는 “유일한 롤백”이 아니라 “두 번째 롤백”이어야 합니다.

### kdump를 ‘관측 가능한 롤백’의 일부로 넣습니다

커널 패닉이 나면 단순히 재부팅되는 것과, vmcore가 남는 것은 운영 비용이 다릅니다. Kdump 문서는 kdump가 kexec를 사용해 패닉 시 dump-capture kernel로 빠르게 부팅한다고 설명합니다.[^9]

RC canary에서는 kdump를 기본으로 켜 두는 편이 좋습니다.

- 패닉이 난 순간의 메모리 덤프가 남으면, 회귀 분석 속도가 달라집니다.
- 특히 드라이버/메모리 서브시스템 문제는 로그만으로는 한계가 많습니다.

kdump 설정은 배포판마다 다르고(예: crashkernel 예약, initramfs 구성), 이 글에서 배포판별 절차를 다 풀어쓰기 시작하면 주제가 흐려집니다. 대신 설계 포인트만 적습니다.

- canary 노드 풀은 crashkernel 예약을 기본으로 포함
- vmcore 저장 경로는 로컬 디스크만 믿지 말고(디스크 드라이버 회귀 가능), 네트워크 저장도 함께 고려

### kexec 롤백의 실행 플로우(현실적인 구현)

운영에서 가장 단순하게 구현하는 방식은 다음입니다.

- LKG 커널/ initrd / cmdline을 미리 확보
- RC 부팅 후 smoke 테스트 실패 시, 즉시 LKG로 kexec

예시:

```bash
# 1) LKG 커널을 로드 (파일 기반 로드가 가능한 환경이면 kexec_file_load를 사용)
# kexec(8) 문서는 KEXEC_FILE_LOAD syscall을 사용하도록 하는 옵션을 설명합니다.
# (배포판 kexec-tools 빌드/커널 설정에 따라 동작이 달라질 수 있어, 파이프라인에서 사전 검증합니다.)

kexec -l /boot/vmlinuz-LKG \
  --initrd=/boot/initrd.img-LKG \
  --command-line="$(cat /proc/cmdline | sed 's/rcpipe/rollback/')"

# 2) 실패하면 즉시 점프
kexec -e
```

`kexec -l/-e` 모델은 `kexec(8)` 매뉴얼의 기본 동작과 일치합니다.[^8]

실제로는 위 커맨드를 직접 치지 않고, systemd unit으로 묶어 “smoke 실패 → rollback service 실행” 형태로 만듭니다. 중요한 건 kexec가 성공해도 실패해도, 다음 부팅은 부트로더 fallback 정책에 의해 LKG로 가도록 이중 안전장치를 넣는 것입니다.

---

## canary 롤아웃: 커널 RC를 배포하는 게 아니라 ‘실험’을 배포합니다

커널 RC canary는 애플리케이션 canary와 성격이 다릅니다.

- 커널은 노드의 공통 기반이라 blast radius가 큽니다.
- 실패가 나면 보통 노드 단위 장애로 나타납니다.
- 드라이버/하드웨어 특성 때문에 “특정 SKU에서만” 터집니다.

그래서 canary 설계에서 중요한 것은 비율이 아니라 분할 방식입니다.

### 1) 하드웨어 프로파일로 쪼갭니다

다음 축으로 canary pool을 나눕니다.

- NIC 벤더/칩셋/펌웨어 버전
- 스토리지(NVMe, SATA HBA, RAID, multipath)
- CPU 세대/마이크로코드
- 가상화 여부(baremetal vs KVM guest)

RC 회귀는 특정 드라이버에서 시작해, 특정 워크로드에서만 재현되는 경우가 많습니다. 동일 워크로드 canary라도 하드웨어가 섞여 있으면 원인 분리가 늦습니다.

### 2) “통과 조건”은 지표로 정의합니다

canary에서 흔히 하는 실수는 “알람이 없으면 OK”입니다. 커널 회귀는 알람을 안 울리면서 손실로 나타나는 경우가 있습니다.

- 네트워크 drop 증가
- softirq CPU 증가
- IO latency tail 악화(p99/p999)
- conntrack table 이상

그래서 canary gate는 다음처럼 정의합니다.

- 노드 health: 부팅/에이전트/핵심 데몬 정상
- 커널 에러: dmesg error/warn rate, 새로운 call trace
- 성능: p99 latency baseline 대비 허용 범위
- 롤백: 실패 시 자동 롤백이 실제로 동작했는지

이 부분은 Grafana 검증 자동화 글에서 이야기했던 “패치 업그레이드 검증의 핵심은 지표와 판정의 자동화”와 구조가 같습니다.

- [Grafana 패치 업그레이드 검증 자동화 설계](https://daewooki.github.io/posts/grafana-patch-upgrade-automation/)

커널도 결국 아티팩트 업그레이드고, 업그레이드를 자동으로 판정할 수 있어야 운영 속도가 나옵니다.

---

## 실패했을 때 빠르게 원인을 남기는 수집 설계: 로그는 증거여야 합니다

RC 파이프라인에서 제일 아까운 실패는 이겁니다.

- 실패는 했는데, 로그가 없다
- 실패한 노드는 reboot 되었고, dmesg ring buffer는 날아갔다
- 재현이 잘 안 된다

최소한 다음을 자동 수집 대상으로 잡습니다.

- `journalctl -b -0` 전체(또는 커널/네트워크/스토리지 단위)
- `dmesg` 원문
- `/proc/cmdline`, `uname -a`, `/sys/kernel/tainted`
- `lspci -nn`, `lsusb`, `lsblk`, `ip -s link`, `ethtool -S`
- (가능하면) pstore(커널이 남긴 마지막 로그)
- (canary면) kdump vmcore 메타데이터(파일 크기, 저장 성공 여부)

이 수집은 사람의 ssh 접속을 전제로 하면 늦습니다. smoke가 끝나는 순간 자동으로 중앙 저장소(S3/MinIO/NFS 등)로 올려야 합니다.

운영에서 효과가 좋았던 패턴은 “노드가 실패하면 그 노드는 격리되고, 그때의 아티팩트와 로그가 티켓처럼 남는다”입니다. 그 다음은 사람이 분석하든, bisect를 붙이든 선택입니다.

---

## 언제 RC를 프로덕션에 들이면 안 되는가: 반론과 회의론을 운영 기준으로 바꿉니다

RC를 프로덕션에 넣는 건 거의 항상 반대 의견이 있습니다. 그 반대는 대부분 타당합니다.

- RC는 깨질 수 있다
- 드라이버가 불안정할 수 있다
- 보안 정책(secure boot, module signing 등)과 충돌할 수 있다

그래서 “RC를 넣을지 말지”는 신념 문제가 아니라, 아래 질문으로 결정됩니다.

1. 현재 stable에서 해결되지 않는 문제가 있어 RC에서만 검증 가능한가
2. 롤백이 자동이고 빠르며, 실패가 서비스 전체 장애로 번지지 않는가
3. 하드웨어 프로파일별 검증이 가능하고, 실패 시 영향 범위를 제한할 수 있는가
4. kselftest/BPF selftests 같은 자동 테스트를 돌려 회귀를 조기에 찾을 수 있는가

특히 2번이 안 되면 RC canary는 해서는 안 됩니다. 테스트가 아니라 도박이 됩니다.

---

## 도입 판단 기준: RC 대응 속도를 만드는 체크포인트

v7.3-rc6 같은 시점(정식 릴리스 직전 구간)에서 파이프라인을 세팅하면 좋은 이유는 단순합니다.

- RC 동안에는 회귀가 발견되면 upstream에 올릴 시간 창이 있습니다.
- 정식 릴리스가 뜬 뒤에 급하게 “우리 환경에서만 깨지네요”가 나오면, 그때부터는 운영 비용이 급등합니다.

내가 RC 파이프라인을 “완성”으로 보지 않는 기준은 다음과 같습니다.

- Ring-0이 10분 내로 끝나고, 실패하면 자동 롤백이 된다.
- Ring-1에서 최소한 `net`/`bpf`/핵심 filesystem 테스트 subset을 꾸준히 돌린다.
- Ring-2에서 eBPF+LSM+컨테이너 런타임의 교차점을 찌르는 시나리오가 있다.
- canary에서 실패하면 노드는 자동 격리되고, 로그가 자동 업로드된다.

이 조건이 갖춰지면, 커널 버전이 바뀌어도 “사람이 하는 일”은 주로 실패 분석과 allowlist 조정으로 줄어듭니다. 그 상태가 운영 가능한 자동화입니다.

---

## 참고 자료

- [The Linux Kernel Archives](https://www.kernel.org/)
- [Linux Kernel Selftests](https://docs.kernel.org/dev-tools/kselftest.html)
- [Device testing with kselftest](https://docs.kernel.org/dev-tools/testing-devices.html)
- [HOWTO interact with BPF subsystem](https://docs.kernel.org/bpf/bpf_devel_QA.html)
- [tools/testing/selftests/bpf/README.rst](https://github.com/torvalds/linux/blob/master/tools/testing/selftests/bpf/README.rst)
- [LSM BPF Programs](https://docs.kernel.org/bpf/prog_lsm.html)
- [Documentation for Kdump - The kexec-based Crash Dumping Solution](https://docs.kernel.org/admin-guide/kdump/kdump.html)
- [kexec(8) - Linux manual page](https://man7.org/linux/man-pages/man8/kexec.8.html)
- [Linux 7.3-rc6 (LWN.net)](https://prodcs.lwn.net/Articles/1098475/)
- [refs/tags/v7.3-rc6 - torvalds/linux.git](https://linux.googlesource.com/linux/kernel/git/torvalds/linux.git/%2B/refs/tags/v7.3-rc6)

[^1]: <https://www.kernel.org/>
[^2]: <https://docs.kernel.org/dev-tools/kselftest.html>
[^3]: <https://linux.googlesource.com/linux/kernel/git/torvalds/linux.git/%2B/refs/tags/v7.3-rc6>
[^4]: <https://docs.kernel.org/dev-tools/testing-devices.html>
[^5]: <https://docs.kernel.org/bpf/bpf_devel_QA.html>
[^6]: <https://github.com/torvalds/linux/blob/master/tools/testing/selftests/bpf/README.rst>
[^7]: <https://docs.kernel.org/bpf/prog_lsm.html>
[^8]: <https://man7.org/linux/man-pages/man8/kexec.8.html>
[^9]: <https://docs.kernel.org/admin-guide/kdump/kdump.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
