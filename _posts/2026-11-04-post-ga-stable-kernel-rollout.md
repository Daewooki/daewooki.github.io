---
title: "Linux stable 브랜치 EOL과 커널 롤아웃 계약"
description: "메인라인 GA 이후 stable/EOL 타이밍이 운영 리스크를 키웁니다. 롤아웃 링과 회귀 대응을 계약으로 고정해야 합니다."
date: 2026-11-04 11:46:31 +0900
categories: ["News", "Systems"]
tags: ["linux-kernel", "stable-branch", "eol", "canary-rollout", "regression-response", "livepatch"]
render_with_liquid: false
---

## 7.3.1(2026-10-30)과 7.2.15(EOL, 2026-11-01): 사건 자체는 작고, 파장은 크다

kernel.org에는 2026-10-30에 stable 7.3.1이 게시됐고, 2026-11-01에 stable 7.2.15가 게시되면서 7.2.y가 EOL로 표시됐습니다. kernel.org 프론트페이지와 `releases.json` 모두에서 같은 사실을 확인할 수 있습니다.[^1]

여기서 중요한 건 7.3.1이 나왔다는 사실 그 자체보다, 같은 화면에 7.2.15가 **EOL**로 찍혀 있다는 점입니다. stable 브랜치는 본질적으로 짧게 유지되는 경우가 흔하고, kernel.org FAQ도 stable이 EOL이 될 수 있으며 EOL이면 더 이상 버그픽스 릴리스가 없다고 명시합니다.[^2]

7.2.15가 마지막이라는 메시지는 Greg Kroah-Hartman의 릴리스 공지에도 직접 들어갔고(LWN이 메일을 그대로 실어둠), 거기에는 7.2.y가 비교적 빨리 EOL이 된 이유로 stable 큐의 압박과 동시에 너무 많은 브랜치를 유지해야 하는 운영 부담이 언급됩니다. 아래 인용은 문장 수를 줄여 핵심만 가져온 것입니다.

> Note, this is the LAST 7.2.y kernel release. After this one the 7.2.y kernel tree is end-of-life.

이 한 줄이 운영팀 입장에서는 SLA를 바꾸는 트리거가 됩니다.[^3]

또 하나의 신호는 7.3.1 공지의 톤입니다. 7.3.1 공지에도 “7.3 유저는 업그레이드해야 한다”는 강한 표현이 들어갑니다. stable 업데이트가 기능 추가가 아니라 버그/보안 픽스라는 의미이기도 하지만, 운영 관점에서는 롤아웃을 멈출 근거가 아니라 오히려 롤아웃을 자동화하고 계약화해야 할 근거가 됩니다.[^4]

## 메인라인 GA 이후가 더 위험해지는 구조

내가 실제로 겪는 커널 리스크는 두 부류로 나뉩니다.

- x.y.0(메인라인 GA) 직후: 기능 변화가 크고, 성능/호환성 편차가 눈에 띄게 튑니다.
- x.y.z(stable 포인트 릴리스) 구간: 겉으로는 버그픽스만 쌓이는데, 운영 사고는 여기서 더 자주 터집니다.

이게 역설처럼 보이는 이유는 많은 조직에서 “GA 검증”만이 정식 프로세스로 존재하기 때문입니다. GA에서 한 번 큰 캠페인을 돌려 통과하면, 그 다음은 unattended 업데이트나 이미지 리빌드 파이프라인을 통해 stable 포인트 릴리스를 상대적으로 무의식적으로 흘려보냅니다. 그러다 회귀가 들어오면 현장에서 처음 관측합니다.

stable 포인트 릴리스가 안전하다고 믿고 싶어지는 배경에는 -stable 규칙이 있습니다. -stable에 들어가는 패치는 이미 mainline에 존재해야 하고, 명백히 올바르고 테스트되어야 하며, 대체로 작은 크기(문서에는 100라인 제한까지 명시)여야 한다고 규정돼 있습니다. 이런 규칙은 위험을 낮추지만, 위험을 0으로 만들지는 못합니다.[^5]

7.3.1 ChangeLog를 보면, “버그픽스”라는 말로는 뭉개기 어려운 영역들이 섞여 있습니다. 예를 들면 io_uring, tracing, keyring/security 같은 서브시스템은 데이터센터 워크로드에 직접적인 영향을 주고, 회귀가 나면 디버깅 비용이 급격히 커지는 축입니다.[^6]

그리고 stable 포인트 릴리스는 보통 주간 단위로 나온다는 설명도 공식 문서에 들어갑니다. 즉, 안정성의 이름을 달고 있지만 변경의 리듬은 생각보다 촘촘합니다. 주간 리듬의 변경을 “별일 없겠지”로 처리하면, 별일이 생겼을 때 조직의 대응이 주간 리듬을 못 따라갑니다.[^7]

## stable 브랜치/EOL은 운영 이벤트다: 릴리스 노트보다 타임라인이 먼저다

stable 브랜치 운영에서 중요한 날짜는 세 가지입니다.

1. x.y.0(메인라인 GA)
2. x.y.z(내가 올릴 대상 포인트 릴리스)
3. x.(y-1).last(EOL)

이번 케이스에서는 2026-10-30(7.3.1)과 2026-11-01(7.2.15 EOL)이 거의 붙어 있습니다. 이 간격이 짧을수록 실제 현장에서는 이런 일이 벌어집니다.

- 아직 7.2.y를 운영 중이던 팀은 EOL 통보를 늦게 본다.
- 7.3.y로 올릴 준비가 안 됐는데, 보안/버그픽스 관점에서 더 이상 “기다리는 전략”이 성립하지 않는다.
- 결과적으로 7.3.y 롤아웃을 더 서두르다가 회귀를 맞는다.

EOL이 가까워지면 “업데이트를 늦추는 보수성”이 오히려 리스크가 됩니다. 반대로, EOL이 공지되는 순간에 “업데이트를 서두르는 공격성”도 리스크가 됩니다. 둘 다 리스크라면, 남는 건 프로세스의 정교함입니다.

kernel.org가 `releases.json`을 제공하면서 “스크래핑하지 말고 이 JSON을 보라”고까지 써 둔 것도 같은 맥락입니다. 운영은 사람이 보는 페이지가 아니라 기계가 소비하는 신호로 움직여야 하고, 그 신호를 바탕으로 롤아웃 계약이 자동으로 발동돼야 합니다.[^8]

## 롤아웃 링(카나리→부분→전면)을 ‘운영 계약’으로 못 박는 방법

여기서 말하는 계약은 법무 문서가 아니라, 조직 내에서 뒤집기 어려운 운영 규칙을 의미합니다. 커널 업데이트는 애플리케이션 배포보다 더 하부 레이어이고, 한번 깨지면 관측도 어렵고 복구도 느립니다. 그래서 “우리는 조심해서 올립니다” 같은 선언형 문장을 없애고, 아래 항목을 숫자와 상태 머신으로 고정합니다.

### 1) 링 정의: 퍼센트가 아니라 ‘대표성’이 기준이다

링을 나눌 때 흔히 1%/10%/100%로 적습니다. 커널은 이 방식이 자주 실패합니다. 1%가 특정 하드웨어/특정 NIC/특정 스토리지 타입에 몰려 있으면, 1%에서 아무 일 없었는데 10%에서 터집니다.

내가 권하는 링의 정의는 퍼센트 + 대표성 조건을 같이 둡니다.

- Canary: 노드 수 최소 N대(절대값) + 하드웨어/가상화 타입별 최소 1대
- Partial: 서비스 tier별 최소 1개 셀(cell) 포함
- Broad: 지역/존별 최소 1개 포함
- Full: 전면

이건 SRE에서 말하는 canary의 원리(작게 시작하고 관측 구간을 두고 점진적으로 확장)와도 맞닿아 있습니다. Google SRE 문서에서도 점진적 롤아웃과 검증 스텝을 강조합니다.[^9]

### 2) 게이트 조건: 테스트 통과가 아니라 ‘회귀 탐지 가능성’을 높이는 조건

커널 롤아웃 게이트를 “유닛 테스트 통과”로 두면 현실과 어긋납니다. 커널 회귀는 workload-dependent한 경우가 많고, 재현이 어렵습니다. 게이트는 아래 축으로 설계하는 편이 낫습니다.

- 부팅/초기화 단계에서의 오류 징후 없음(oops, soft lockup, hung task)
- 핵심 syscall 실패율 상승 없음(특히 io_uring, futex, epoll, sendmsg 계열은 워크로드에 따라)
- 스토리지/네트워크의 tail latency 변화 감시(평균이 아니라 p99/p999)
- 컨테이너 런타임/ebpf/observability가 동시에 살아있음

“카나리 기간 30분” 같은 고정 시간도 위험합니다. 트래픽이 없으면 30분은 아무 의미가 없습니다. 게이트는 시간과 트래픽/이벤트 양을 함께 요구해야 합니다.

### 3) 중단 권한: 롤백보다 먼저 ‘중단’이 가능해야 한다

실제 사고에서 가장 먼저 필요한 권한은 “더 이상 퍼지지 않게 멈추는 것”입니다. 롤백은 그 다음입니다. 이 권한이 change manager나 운영위원회에만 묶이면, 커널 회귀처럼 빠르게 퍼지는 타입에서 항상 늦습니다.

계약에 아래 한 줄을 넣는 걸 선호합니다.

- SRE/oncall은 게이트 조건 위반 시 변경을 즉시 중단할 권한을 가진다.

조직 문화 이야기가 아니라, 변경 시스템에 Stop 버튼을 누구나 누를 수 있게 만드는 구현 문제입니다.

## 회귀 대응을 옵션이 아니라 계약 조항으로 만들기: revert / pin / livepatch

stable 업데이트를 운영한다는 건, “업데이트”를 잘하는 게 아니라 “회귀를 빨리 죽이는 방법”을 여러 개 확보한다는 뜻입니다. 대응 옵션은 최소 3개가 필요합니다.

### 1) revert: 이전 커널로 되돌리는 경로를 자동화한다

커널 회귀의 가장 강력한 완화는 이전 버전으로의 부팅입니다. 여기서의 함정은 두 가지입니다.

- 이전 커널이 디스크에 남아 있지 않다(이미지/패키지 정리 정책)
- 부팅 엔트리 선택이 사람 손을 탄다(원격/무인 환경에서 특히)

이 문제를 해결하는 계약 조항은 단순합니다.

- 모든 노드는 최소 2개의 부팅 가능한 커널을 유지한다.
- 롤아웃 시스템은 1회성 부팅 엔트리 전환(grub-reboot 등)을 지원한다.

### 2) pin: 고정은 부끄러운 게 아니라 생존 전략이다

회귀가 터진 순간의 최악은 “업데이트가 계속 들어오는 상태”입니다. 특히 자동 업데이트가 켜져 있으면, 장애 조치 중에 또 다른 커널로 올라가 버립니다.

그래서 pin은 임시 변칙이 아니라 표준 동작이어야 합니다.

- 회귀 탐지 시점에 즉시 pin
- 원인 규명/패치 적용/정상 확인 후 unpin

kernel.org FAQ도 EOL이면 다음 버전으로 업그레이드를 고려해야 한다고 명시합니다. 즉, pin은 영구 해결책이 아니고, 시간을 버는 수단입니다.[^2]

### 3) livepatch: 쓸 수 있으면 좋지만, ‘커버리지 착시’를 경계한다

라이브패치는 매력적입니다. 재부팅을 줄여 uptime을 높여주기 때문입니다. 커널 문서에서도 reboot를 꺼리는 상황에서 function call redirection으로 수정하는 개념을 설명합니다.[^10]

다만 운영에서 라이브패치는 두 층으로 나뉩니다.

- upstream 기능(Livepatch 서브시스템): 기술적으로 가능
- 배포 가능한 패치 스트림(벤더 제공): 실무적으로 가능

그리고 “가능”과 “전체 커널 리스크를 흡수”는 다릅니다. Red Hat 문서도 kpatch가 모든 CVE를 다루지 않으며 제한 사항이 있음을 명확히 경고합니다.[^11]

즉, livepatch는 revert/pin을 대체하는 무기가 아니라, 재부팅 윈도우를 조절하는 도구에 가깝습니다.

## 7.3.1 ChangeLog에서 바로 보이는 운영 리스크 포인트

커널 stable 릴리스 노트는 길고, 모든 항목을 읽는 건 비효율적입니다. 대신 나는 “내 시스템에서 폭발력이 큰 서브시스템”만 먼저 봅니다. 이번 7.3.1 ChangeLog에서 눈에 띄는 지점 몇 가지를 예로 들면 이렇습니다.

- io_uring: 이벤트 루프/네트워크/스토리지 워크로드에 닿습니다. 안정성 이슈가 나면 증상이 다양하게 나타납니다. 7.3.1 ChangeLog에는 io_uring/poll 관련 수정이 포함됩니다.[^6]
- tracing: 관측 도구와 충돌할 수 있고, 커널 내부 락킹과 얽히면 디버깅이 어려워집니다. 7.3.1에도 tracing 관련 변경이 들어갑니다.[^4]
- livepatch 관련 경로: 나는 livepatch를 직접 쓰지 않더라도, livepatch 관련 변경이 다른 경로에 영향을 줄 수 있다는 점을 신경 씁니다. 7.3.1에는 `pid_namespace: prevent TIF_NOTIFY_SIGNAL from interrupting the reaper` 같은 항목이 보이고, 설명에 `klp_send_signals()`가 등장합니다.[^6]

이런 항목을 보면서 운영적으로 내리는 결론은 하나입니다.

- stable 포인트 릴리스는 “작은 패치”가 아니라 “핵심 경로의 조건문 한 줄”로 서비스 전체를 바꿀 수 있다.

예전에 내가 stable 업데이트를 운영 리스크로 보는 이유를 정리했던 글도 같은 문제의식에서 출발했습니다.

- [Linux 7.2.6 stable 릴리스: 작은 패치가 운영에선 큰 리스크가 되는 이유](https://daewooki.github.io/posts/linux-kernel-stable-rollout-contract/)

## 7.2.15(EOL) 릴리스가 의미하는 것: 보안보다 더 무서운 건 ‘고아 버전’

7.2.15 ChangeLog 자체는 여러 서브시스템 버그픽스를 포함합니다(Bluetooth, net, SMB 등).[^12]

하지만 운영 관점에서 핵심은 내용이 아니라 EOL입니다.

- 7.2.y는 더 이상 upstream stable 릴리스가 나오지 않습니다.
- 즉, 7.2.y에 대해 새로 발견되는 문제는 “나와 같은 버전 사용자”가 고쳐서 들고 오지 않는 한, 공식 stable 채널에서 해결될 가능성이 낮습니다.

이 상태가 무서운 이유는 CVE 때문만이 아닙니다.

- 장애가 터졌을 때, upstream에 버그 리포트/회귀 리포트를 올릴 명분이 약해집니다(이미 EOL이기 때문).
- 다운스트림(배포판/벤더)이 7.2.y 기반 커널을 유지한다면 거기로 이슈를 넘겨야 하고, 그때부터는 “내가 쓰는 커널은 upstream 7.2가 아니다”라는 세계로 들어갑니다.

kernel.org FAQ도 대시가 붙은 배포판 커널은 배포판 지원 채널을 보라고 명확히 선을 긋습니다.[^7]

결국 EOL은 기술 이벤트가 아니라 계약 이벤트입니다.

- EOL 날짜가 찍히는 순간, 해당 브랜치를 운영하는 팀은 “업그레이드 프로젝트”를 즉시 시작해야 합니다.
- 그렇지 않으면 핀으로 시간을 벌다가, 핀 상태 자체가 누적 리스크가 됩니다.

## 실전 형태로 굳히기: rollout contract를 리포지토리 아티팩트로 만든다

문서로만 존재하는 운영 규칙은 사고 때 무력합니다. 실행 가능한 형태로 남겨야 합니다. 여기서는 내가 실제로 자주 쓰는 형태(계약 YAML + 상태 점검 스크립트 + 롤백/핀 명령 세트)를 예시로 정리합니다.

아래 예시는 upstream kernel을 자체 패키징/배포하거나(혹은 특정 배포판 커널을 내부 채널로 롤아웃하더라도) 구조는 그대로 적용할 수 있습니다.

### 1) upstream 신호를 기계가 읽는다: `releases.json` 기반 상태 체크

kernel.org는 `releases.json`을 제공합니다. kernel.org는 스크래핑 대신 이 JSON을 쓰라고 안내합니다.[^8]

의존성:

- `curl`
- `jq`

`bin/kernel-release-signal.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

KORG_JSON="https://www.kernel.org/releases.json"

json="$(curl -fsSL "$KORG_JSON")"

stable_ver="$(jq -r '.releases[] | select(.moniker=="stable" and .iseol==false) | .version' <<<"$json" | head -n1)"

eol_series="$(jq -r '.releases[] | select(.moniker=="stable" and .iseol==true) | .version' <<<"$json" | head -n1)"

stable_date="$(jq -r --arg v "$stable_ver" '.releases[] | select(.version==$v) | .released.isodate' <<<"$json")"

eol_date="$(jq -r --arg v "$eol_series" '.releases[] | select(.version==$v) | .released.isodate' <<<"$json")"

printf "stable=%s (%s)\n" "$stable_ver" "$stable_date"
printf "eol=%s (%s)\n" "$eol_series" "$eol_date"
```

실행:

```bash
chmod +x bin/kernel-release-signal.sh
./bin/kernel-release-signal.sh
```

예상 출력(2026-11-04 KST 기준):

```text
stable=7.3.1 (2026-10-30)
eol=7.2.15 (2026-11-01)
```

이 출력 한 줄이 change calendar를 밀어붙이는 근거가 됩니다. 감으로는 늦습니다.

### 2) rollout contract: 링, 게이트, 중단/롤백/핀을 한 파일에 묶는다

`rollout/contract.yaml`(예시):

```yaml
kernel_rollout_contract:
  owner:
    platform_team: "infra-platform"
    incident_commander: "oncall-sre"

  triggers:
    - name: "upstream-stable-released"
      source: "kernel.org/releases.json"
      match:
        moniker: "stable"
    - name: "upstream-branch-eol"
      source: "kernel.org/releases.json"
      match:
        moniker: "stable"
        iseol: true

  rings:
    - name: "canary"
      min_nodes: 6
      min_duration_minutes: 240
      represent:
        - dimension: "virt"
          must_include: ["baremetal", "kvm"]
        - dimension: "nic"
          must_include: ["mlx5", "ixgbe"]
        - dimension: "storage"
          must_include: ["nvme", "virtio-blk"]

    - name: "partial"
      percent: 10
      min_duration_minutes: 720

    - name: "broad"
      percent: 50
      min_duration_minutes: 1440

    - name: "full"
      percent: 100

  gates:
    hard_fail:
      - name: "kernel_oops_or_panic"
        query: "journalctl -k -b | egrep -i 'Oops:|panic|BUG:|soft lockup|hung task'"
      - name: "service_slo_breach"
        metric: "error_rate"
        threshold: "baseline + 0.3%"

    soft_fail:
      - name: "tail_latency_regression"
        metric: "p99_latency"
        threshold: "baseline * 1.10"

  mitigations:
    - name: "pause_rollout"
      action: "freeze ring progression"
    - name: "pin_kernel"
      action: "package hold/versionlock"
    - name: "revert_kernel"
      action: "boot previous kernel once, then pin"
    - name: "consider_livepatch"
      action: "vendor livepatch stream if available"

  sla:
    detect_to_pause_minutes: 15
    detect_to_pin_minutes: 30
    detect_to_revert_minutes: 60
```

핵심은 파일 포맷이 아니라, 아래가 하나로 묶여 있다는 점입니다.

- 어떤 신호가 들어오면(7.3.1 릴리스, 7.2 EOL)
- 어떤 링을 어떤 기간으로 굴리고
- 어떤 조건에서 멈추며
- 멈춘 뒤 무엇을 할지

이걸 조직의 “약속”으로 만들려면, PR 리뷰 룰에 넣는 게 가장 빠릅니다. 커널 업데이트 PR은 이 contract 파일을 반드시 참조하도록 바꾸면 됩니다.

내가 예전에 체크리스트를 별도로 정리해 둔 글이 있는데, 그 글을 그대로 복붙하기보다 contract의 게이트/링 정의를 업데이트하는 쪽이 더 실무적으로는 효과가 큽니다.

- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)
- [Linux 커널 7.3 메인라인 이후 GA 롤아웃 검증 체크리스트](https://daewooki.github.io/posts/linux-kernel-73-ga-rollout-validation/)

### 3) canary 노드에서 부팅 직후 10분 안에 할 수 있는 smoke test

의존성:

- Ubuntu/Debian: `stress-ng`, `iperf3`(선택), `jq`

설치:

```bash
sudo apt-get update
sudo apt-get install -y stress-ng jq
```

`bin/kernel-smoke.sh`(예시):

```bash
#!/usr/bin/env bash
set -euo pipefail

duration="${1:-300}"

echo "[info] kernel=$(uname -r)"

echo "[check] kernel log red flags"
if journalctl -k -b --no-pager | egrep -i -q 'Oops:|panic|BUG:|soft lockup|hung task'; then
  echo "[fail] kernel log has red flags"
  exit 2
fi

echo "[check] basic syscalls under stress (${duration}s)"
stress-ng --timeout "${duration}s" --cpu 4 --vm 2 --vm-bytes 70% --io 2 --hdd 1 --hdd-bytes 1G --metrics-brief

echo "[check] re-scan logs after stress"
if journalctl -k -b --no-pager | egrep -i -q 'Oops:|panic|BUG:|soft lockup|hung task'; then
  echo "[fail] red flags appeared after stress"
  exit 3
fi

echo "[pass] smoke test OK"
```

실행:

```bash
chmod +x bin/kernel-smoke.sh
sudo ./bin/kernel-smoke.sh 600
```

예상 출력(환경에 따라 수치는 다름):

```text
[info] kernel=7.3.1
[check] kernel log red flags
[check] basic syscalls under stress (600s)
stress-ng: info:  [12345] dispatching hogs: 4 cpu, 2 vm, 2 io, 1 hdd
stress-ng: info:  [12345] successful run completed in 600.01s
[check] re-scan logs after stress
[pass] smoke test OK
```

이 정도만 해도 “부팅은 됐는데 2시간 뒤 soft lockup” 같은 저질 회귀를 초기에 잡을 확률이 올라갑니다. 여기서부터는 워크로드 특화 테스트(스토리지, 네트워크, 컨테이너 런타임)를 링 게이트에 붙이면 됩니다.

RC 단계에서의 회귀 테스트 자동화 설계는 예전에 더 깊게 썼고, stable에도 같은 방식을 축소 적용하는 편이 낫습니다.

- [Linux 7.3 RC 회귀 테스트·드라이버 검증 자동화 설계](https://daewooki.github.io/posts/linux-kernel-rc-regression-pipeline/)

## 운영 대응 플레이북: “리버트/핀/라이브패치”를 실제 명령으로 준비해 두기

여기서는 배포판/부트로더에 따라 명령이 달라지기 때문에, 조직 표준을 하나 정해 문서화해야 합니다. 아래는 내가 자주 쓰는 형태(개념 증명용이 아니라, 실제로 현장에서 바로 쓸 수 있는 수준)의 예시입니다.

### 1) revert: 다음 부팅만 이전 커널로

Ubuntu/Debian에서 GRUB을 쓰는 경우, `grub-reboot`로 1회성 엔트리를 지정할 수 있습니다(엔트리 이름은 환경마다 다르니 사전에 표준화가 필요합니다).

```bash
sudo grep -n "menuentry" /boot/grub/grub.cfg | head
sudo grub-reboot "Advanced options for Ubuntu>Ubuntu, with Linux 7.3.0"
sudo systemctl reboot
```

리버트 이후에는 반드시 pin까지 같이 해야 합니다. 그렇지 않으면 다음 재부팅에서 다시 문제 버전으로 올라갑니다.

### 2) pin: Ubuntu/Debian(apt) 예시

```bash
# 커널 이미지/헤더가 자동으로 올라가지 않게 hold
sudo apt-mark hold 'linux-image-*' 'linux-headers-*'

# 확인
apt-mark showhold | head
```

운영 계약에는 hold 해제 조건도 들어가야 합니다. hold는 기술적으로 쉬운데, 풀 타이밍이 팀마다 달라지면 fleet이 파편화됩니다.

### 3) pin: RHEL 계열(dnf) 예시(versionlock)

```bash
sudo dnf install -y 'dnf-command(versionlock)'

# 현재 커널을 잠그거나, 특정 버전을 잠금
uname -r
sudo dnf versionlock add kernel\*

sudo dnf versionlock list | head
```

### 4) livepatch: 쓸 수 있으면 쓰되, 범위를 명시한다

upstream 문서의 Livepatch 섹션은 라이브패치가 ftrace 기반의 code redirection을 이용하며 제한 사항이 있음을 설명합니다.[^10]

벤더 livepatch를 쓰는 경우에는, 해당 벤더 문서의 제한 사항을 계약 본문에 인용해서 넣는 편이 안전합니다. Red Hat 문서도 livepatch가 모든 CVE를 다루지 못하고 제한이 있다고 경고합니다.[^11]

운영에서 필요한 건 기술 설명이 아니라, 이 한 문장입니다.

- livepatch는 재부팅을 영구히 없애는 도구가 아니라, 재부팅 시점을 통제하는 도구다.

## 반론과 회의론: 우리에게도 해당되나

### 배포판 커널을 쓰면 upstream stable/EOL을 신경 안 써도 되나

부분적으로만 맞습니다.

- 맞는 부분: 배포판 커널은 버전 문자열에 대시가 붙고, upstream과 다른 백포트 정책을 가집니다. kernel.org도 배포판 커널이면 배포판 지원 채널로 가라고 말합니다.[^7]
- 틀린 부분: 배포판도 내부적으로는 “기반 커널 버전”을 정해 주기적으로 업데이트합니다. 그때 회귀 양상은 upstream stable과 크게 다르지 않습니다. 링/게이트/중단/리버트/핀은 그대로 필요합니다.

즉, upstream stable의 7.2.y EOL은 직접적인 행동 트리거가 아닐 수도 있지만, 안정 브랜치가 갑자기 끝날 수 있다는 사실 자체가 운영 설계의 전제 조건이 됩니다.

### 라이브패치만 있으면 카나리/부분 롤아웃이 필요 없나

그렇지 않습니다.

- 라이브패치는 적용 범위가 제한됩니다(벤더 문서에서도 제한을 명시).[^11]
- 라이브패치로 해결 가능한 유형의 버그만 존재하지 않습니다.
- 더 결정적으로, 라이브패치 자체도 커널 내부 메커니즘(ftrace 기반 redirection, consistency model 등)에 의존합니다.[^10]

라이브패치가 있는 조직일수록 “어차피 reboot 안 해도 되니까 빨리 적용”이라는 유혹이 강해져서, 오히려 링/게이트가 더 중요해집니다.

## 앞으로 지켜볼 것: stable 브랜치 운영이 더 압축되는지

이번 7.2.y EOL 공지에는 “동시에 너무 많은 브랜치를 유지하는 부담”이 직접 언급됩니다.[^3]

이 현상이 구조적으로 반복되면, 운영팀이 기대하던 전통적인 감각(예: stable은 몇 달은 유지될 것)이 깨질 수 있습니다. 그래서 다음을 지표로 봅니다.

- stable 브랜치가 유지되는 평균 기간(체감이 아니라 기록)
- EOL 공지가 언제, 어떤 톤으로 나오는지
- stable 릴리스 주기(공식 설명은 주간이지만, 실제로는 사건에 따라 달라짐)[^7]

그리고 조직 내부적으로는 이걸 확인해야 합니다.

- EOL 공지가 떴을 때, 우리 change calendar가 자동으로 바뀌는가
- 링 progression이 사람 손이 아니라 시스템 상태로 움직이는가
- 리버트/핀 실행이 “권한/절차 문제” 때문에 늦어지지 않는가

## 결론: 커널 업데이트는 릴리스가 아니라 계약의 실행이다

7.3.1(2026-10-30)과 7.2.15(EOL, 2026-11-01)는 단순한 버전 업이 아니라, stable 브랜치가 짧은 호흡으로 끝날 수 있음을 다시 확인시킨 사건입니다.[^1]

메인라인 GA 이후가 더 위험해지는 이유는 기술적 난이도보다 조직의 방심에 가깝습니다. GA 때만 크게 검증하고, stable 포인트 릴리스는 자동으로 흘려보내는 순간, 회귀는 반드시 운영에서 터집니다. -stable 규칙이 엄격하더라도 회귀 가능성은 남고, 릴리스는 보통 주간 단위로 계속 나옵니다.[^5]

그래서 커널 롤아웃은 canary→부분→전면의 링을 운영 계약으로 굳히고, 회귀 대응을 revert/pin/livepatch로 분해해 SLA까지 포함한 실행 계획으로 만들어야 합니다. 메인라인 GA 검증이 끝났을 때가 안전해진 순간이 아니라, 운영 계약이 발효되는 시작점이라고 보는 쪽이 맞습니다.

## 참고 자료

- [kernel.org 프론트페이지(7.3.1, 7.2.15 EOL 표시)](https://www.kernel.org/?lan=english)
- [kernel.org releases.json(기계가 읽는 릴리스 신호)](https://www.kernel.org/releases.json)
- [kernel.org: XZ by default and JSON(releases.json 안내)](https://www.kernel.org/xz-by-default-and-json.html)
- [kernel.org FAQ: stable/EOL 의미와 배포판 커널 안내](https://kernel.org/category/faq.html)
- [kernel.org Active kernel releases: stable 업데이트 주기(보통 주간) 설명](https://www.kernel.org/releases.html)
- [Linux 7.3.1 ChangeLog](https://www.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.3.1)
- [Linux 7.2.15 ChangeLog](https://www.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.2.15)
- [LWN: Linux 7.3.1 릴리스 공지 메일](https://lwn.net/Articles/1104178/)
- [LWN: 7.2 stable 시리즈의 마지막 릴리스(7.2.15, EOL)](https://lwn.net/Articles/1104629/)
- [Linux kernel docs: stable-kernel-rules(-stable 규칙)](https://www.kernel.org/doc/html/latest/process/stable-kernel-rules.html)
- [Linux kernel docs: Livepatch](https://docs.kernel.org/livepatch/livepatch.html)
- [Red Hat docs: Applying patches with kernel live patching(kpatch)](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/managing_monitoring_and_updating_the_kernel/applying-patches-with-kernel-live-patching)
- [Google SRE Book: Release Engineering](https://sre.google/sre-book/release-engineering/)
- [Google SRE Book: Reliable Product Launches(점진적 롤아웃/카나리)](https://sre.google/sre-book/reliable-product-launches/)
- [Linux 7.2.6 stable 릴리스: 작은 패치가 운영에선 큰 리스크가 되는 이유](https://daewooki.github.io/posts/linux-kernel-stable-rollout-contract/)
- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)
- [Linux 커널 7.3 메인라인 이후 GA 롤아웃 검증 체크리스트](https://daewooki.github.io/posts/linux-kernel-73-ga-rollout-validation/)
- [Linux 7.3 RC 회귀 테스트·드라이버 검증 자동화 설계](https://daewooki.github.io/posts/linux-kernel-rc-regression-pipeline/)
- [OpenSSL 3.0 EOL 이후 런타임을 안전하게 퇴역시키는 운영 설계](https://daewooki.github.io/posts/retire-openssl-3-0-safely/)

[^1]: <https://www.kernel.org/?lan=english>
[^2]: <https://kernel.org/category/faq.html>
[^3]: <https://lwn.net/Articles/1104629/>
[^4]: <https://lwn.net/Articles/1104178/>
[^5]: <https://www.kernel.org/doc/html/latest/process/stable-kernel-rules.html>
[^6]: <https://www.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.3.1>
[^7]: <https://www.kernel.org/releases.html>
[^8]: <https://www.kernel.org/xz-by-default-and-json.html>
[^9]: <https://sre.google/sre-book/reliable-product-launches/>
[^10]: <https://docs.kernel.org/livepatch/livepatch.html>
[^11]: <https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/managing_monitoring_and_updating_the_kernel/applying-patches-with-kernel-live-patching>
[^12]: <https://www.kernel.org/pub/linux/kernel/v7.x/ChangeLog-7.2.15>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
