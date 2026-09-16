---
title: "systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드"
description: "systemd v261.3·v260.5 안정 릴리스 타이밍에 맞춰, 배포판 백포트와 자체 업그레이드의 경계·장애 경로·롤백/검증 시나리오를 정리합니다."
date: 2026-09-16 13:14:58 +0900
categories: ["News", "Systems"]
tags: ["systemd", "linux", "release-management", "rollback", "regression-testing", "operations"]
render_with_liquid: false
---

## v261.3·v260.5가 운영 이슈가 되는 지점
2026-09-10 전후로 systemd-stable v261.3와 v260.5가 upstream 릴리스로 게시됐습니다. GitHub Releases 기준으로 v261.3는 2026-09-10에, v260.5도 같은 날짜에 게시되어 있습니다.[^1] Release Alert도 두 버전이 2026-09-10에 Stable로 찍힌 것을 확인할 수 있습니다.[^2]

이 타이밍이 골치 아픈 이유는 대체로 세 가지입니다.

첫째, systemd는 PID 1만이 아닙니다. journald, networkd, resolved, logind, udevd, nspawn 등 “OS의 기본 동작”과 직접 맞물려 있습니다. 따라서 운영팀 관점에서는 단순 패키지 업데이트가 아니라 **platform contract** 변경으로 보는 편이 사고 비용이 낮습니다.

둘째, 배포판 업데이트(백포트)와 컨테이너 베이스 이미지 갱신이 같은 윈도우에 겹칩니다. 특히 Arch 같은 롤링 계열은 261.3 패키지가 이미 올라와 있고 빌드/업데이트 시점이 2026-09-10~11로 잡혀 있어, “이미 내일의 기본값”이 되는 속도가 빠릅니다.[^3]

셋째, v261 계열은 운영적으로 민감한 변화가 몇 개 섞여 있습니다. 예를 들어 networkd의 DHCP relay 관련 설정 구조 변경/폐기 예고, libsystemd 링크 특성 변경으로 인한 로깅 데몬 크래시 같은 전파 경로가 눈에 띕니다.[^4]

이 글의 초점은 릴리스 노트 번역이 아니라, (1) 운영팀이 systemd를 패키지로만 볼지 계약으로 볼지의 기준, (2) unit/로그/네트워크 변경이 장애로 이어지는 구체 경로, (3) 롤백/검증 시나리오를 운영 절차로 제안하는 것입니다.

## systemd를 “패키지 업데이트”로 취급할 때 생기는 구멍
systemd 프로젝트는 안정성과 호환성에 대한 문서를 따로 두고, 무엇이 stable interface이고 무엇이 그렇지 않은지 선을 긋습니다. 동시에 “문서와 다르게 동작하던 버그를 고치면 동작이 바뀔 수 있다”는 점도 명시합니다.[^5]

여기서 운영 관점의 함정은 이렇습니다.

- 패키지 업데이트로만 보면, 보통 “서비스 재시작/리부트 한 번”으로 끝납니다.
- platform contract로 보면, “부트/서비스 그래프/로깅 파이프라인/네트워크 bring-up” 전체를 검증 범위로 잡습니다.

systemd는 후자가 맞습니다. 이유는 단순합니다. PID 1이 바뀌면 실패 모드가 “어떤 서비스가 죽었다”가 아니라 “서버가 부팅에 실패했다”가 될 수 있습니다. journald/networkd/resolved는 더 노골적입니다. 장애가 나면 애플리케이션 레벨의 health check가 아니라, 노드 전체가 조용히 망가집니다(네트워크 단절, 로그 수집 단절, DNS 해석 꼬임).

내 경우 운영 절차에서 systemd 업데이트를 kernel 업데이트와 같은 레벨의 change로 분류합니다. 예전에 정리한 커널 롤아웃 체크리스트를 그대로 적용하고(테스트 범위만 systemd 특성에 맞게 바꾸고), Terraform 같은 도구 업그레이드 때 했던 것처럼 버전 고정만 믿지 않고 “검증 가능한 관측치”를 먼저 정의합니다.

- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)
- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)

systemd 업데이트도 결국 “관측치가 정의된 변경”이어야 합니다. 부팅 성공/실패만 보지 말고, 아래를 최소 관측치로 잡는 편이 현실적입니다.

- 부팅 후 critical-chain의 상위 N개(부팅 지연/순환 의존/timeout)
- enabled unit의 실패율(특히 oneshot)
- journald 디스크 사용량/레이트 리밋/forwarding 상태
- DNS 해석 경로(resolved 사용 여부에 따라 /etc/resolv.conf link가 바뀔 수 있음)
- network bring-up(DHCP, VLAN, bond/bridge, RA, 정책 라우팅)

## 배포판 백포트와 자체 업그레이드의 경계: 무엇을 “책임”으로 볼 것인가
운영팀이 systemd 업데이트를 관리할 때 핵심 질문은 하나입니다.

> 이 변경의 책임 주체를 배포판(벤더)로 둘 것인가, 우리로 둘 것인가.

나는 여기서 **백포트**와 자체 업그레이드를 단순히 “버전이 낮다/높다”의 문제가 아니라, 책임 분리 모델로 봅니다.

### 배포판 백포트가 유리한 경우
배포판 백포트는 대개 “동작 변화 최소화 + 보안/치명 버그 픽스”에 집중합니다. systemd처럼 주변 컴포넌트와 결합이 센 패키지는, 벤더가 커널/udev 규칙/부트로더/네트워크 설정 도구(netplan 등)와의 조합을 이미 테스트했을 가능성이 큽니다.

예를 들어 Ubuntu 26.04 LTS는 systemd가 특정 버전대로 올라가고, SysV script 호환성 같은 경계가 릴리스 노트에 명시됩니다.[^6] 이런 배포판은 “업그레이드 가능한 단위”가 패키지 하나가 아니라 배포판 릴리스 단위로 설계되어 있는 편입니다.

따라서 아래 조건이라면 백포트를 우선합니다.

- (책임) 장애가 났을 때 “우리가 upstream systemd를 들고 와서 깔았다”는 서사가 리스크가 되는 조직
- (결합) initrd/부트로더/TPM attestation까지 systemd 체인에 걸려 있는 환경
- (규모) 동일 이미지/동일 커널/동일 네트워크 템플릿으로 수백~수천 대를 굴리는 환경
- (관측) 장애 시 원인 분석을 journald/syslog/metrics 기반으로 해야 하는데, 로깅 파이프라인이 systemd 변화에 민감한 환경

이 경우는 “배포판이 제공하는 v260.x 또는 v259.x 계열의 backported fix”가 가장 안전한 선택이 됩니다.

### 자체 업그레이드(Upstream stable 채택)가 유리한 경우
반대로 자체 업그레이드는 “우리가 systemd를 플랫폼으로 정의하고, 그 버전을 우리가 고른다”는 선언에 가깝습니다. 이 모델은 시스템이 이미 이미지 기반(immutable)로 굴러가고 있고, 노드 교체/롤백이 자동화되어 있을 때 유효합니다.

대표적으로 아래 조건이면 자체 업그레이드가 오히려 비용이 낮습니다.

- (이미지) 베이스 이미지가 컨테이너/VM 이미지로 고정되어 있고, 롤백이 이미지 단위로 가능
- (표준화) unit 파일/override/journald 설정/network 설정이 코드로 관리되고, drift가 작음
- (실험) v261의 신규 기능(예: 특정 cgroup/cpuset, ConditionFraction 기반 staged rollout 같은 운영 패턴)을 쓰려는 명확한 이유가 있음[^4]
- (격리) systemd-networkd/resolved를 적극적으로 쓰거나, 반대로 아예 안 쓰는 등 경계를 분명히 그어둔 환경

중요한 점은 “최신이니까 올린다”는 이유는 자체 업그레이드의 근거로 빈약하다는 것입니다. systemd는 커널/컨테이너/네트워크와 붙어 있어 회귀 테스트 가치가 큰 대신, 회귀 테스트 비용도 큽니다.

## v261 계열 변화가 장애로 이어지는 현실적인 전파 경로
v261.3는 stable point release이지만, 실무에서는 “지금 이미지/배포판이 v261으로 점프하느냐”가 더 큰 이슈가 됩니다. v261의 NEWS에는 운영 관점에서 건드리기 싫은 변화들이 몇 개 명시돼 있습니다.[^4]

여기서는 장애 경로를 unit / 로그 / 네트워크 3개 축으로 나눠 적습니다.

### 1) unit 파일/부팅 그래프: 작은 기본값이 대규모 재부팅 사고로 번지는 방식
#### (a) 컨테이너에서의 PID 1 동작이 달라지는 경우
v261.3 릴리스 노트(릴리스 페이지 텍스트)에는 “manager가 기본 unit 파일 세트를 바이너리에 내장하고, 디스크에서 unit 파일을 못 읽을 때 fallback으로 쓴다”는 내용이 들어 있습니다. 또한 “작은 컨테이너를 위한 statically linked PID1/executor 단일 바이너리로 빌드 가능”하다고 적혀 있습니다.[^7]

이 변화는 겉으로는 “편의 기능”입니다. 운영에서는 다른 얼굴을 가집니다.

- 기존: 컨테이너에 systemd를 PID 1로 띄우려다 unit 파일이 없으면 실패 → 이미지가 잘못됐다는 신호가 빨리 터짐
- 변경 후: unit 파일이 불완전해도 systemd가 “뭔가”는 띄움 → 이미지 결함이 늦게 터짐(더 나쁜 타이밍에 터짐)

특히 health check가 “PID 1이 떠 있나” 수준이면, 잘못된 컨테이너가 정상으로 분류될 수 있습니다. 그 다음 단계에서 app unit이 enable/start가 안 되면, 서비스가 아니라 배치/cron/timer가 조용히 안 도는 형태로 사고가 납니다.

운영팀이 systemd를 platform contract로 본다면, 컨테이너 베이스 이미지 갱신 시 다음을 계약 조항으로 넣어야 합니다.

- 이미지 빌드 단계에서 `systemd-analyze verify`로 핵심 unit을 정적 검증
- 런타임 단계에서 “기대하는 target에 도달했는지”를 확인(multi-user.target 등)

#### (b) shutdown/reboot 루프에 개입하는 기본 지연
v261에는 MinimumUptimeSec=라는 글로벌 설정이 추가됐고 기본값이 15s로 명시되어 있습니다. “너무 빨리 shutdown되면 부트 루프를 피하기 위해 종료 막판에 지연을 삽입한다”는 설명도 붙어 있습니다.[^4]

이건 데이터센터 서버보다는 자동화 환경에서 더 문제가 됩니다.

- 프로비저닝 파이프라인이 “부팅 → 에이전트 설치 → 재부팅 → 조인” 같은 플로우일 때
- 테스트 환경에서 수 분 단위로 VM을 재기동할 때
- 장애 복구 스크립트가 “재시작이 느리면 실패”로 간주할 때

지연 자체가 장애를 만들지는 않습니다. 다만 “재부팅 시간 SLO”를 깨서 상위 오케스트레이션이 연쇄로 실패할 수 있습니다. 이 계층형 실패는 원인 분석이 어렵습니다. OS 팀은 “정상 종료 지연일 뿐”이라고 보고, 플랫폼 팀은 “노드 조인이 늦다”고 보고, 애플리케이션 팀은 “배포가 멈춘다”고 봅니다.

여기서 필요한 건 기술적 해결보다 계약의 명시입니다.

- systemd 업그레이드 후에는 “reboot 소요시간”을 SLO 항목으로 잡고 배포 파이프라인의 timeout을 재조정
- fast reboot를 전제로 한 테스트는, 실제로는 “systemd 기본값을 포함한 부트 시간”을 계약으로 가져가야 함

### 2) 로그 정책: 로깅 데몬 하나가 죽어도 시스템 전체 관측성이 날아가는 경로
v261 NEWS에는 libsystemd가 더 이상 libm에 링크되는 것을 보장하지 않는다고 적혀 있습니다. 그리고 rsyslog가 libfastjson의 링크 문제 때문에 런치 시 크래시하는 알려진 케이스가 있고, 예전에는 libsystemd가 libm을 링크해서 마스킹됐는데 이제 드러난다는 설명까지 들어 있습니다.[^4]

이 항목은 운영에서 치명적인 이유가 명확합니다.

- rsyslog나 로그 포워더가 죽으면, 애플리케이션 장애가 아니라 “장애를 볼 수 없는 장애”가 됩니다.
- journald → syslog forwarding이 켜져 있거나, 반대로 syslog가 primary pipeline인 조직에서는 사고 성격이 달라집니다.

전파 경로를 현실적으로 쓰면 아래처럼 됩니다.

1) systemd 업그레이드
2) libsystemd 링크 특성 변경(직접 원인이 아니라 트리거)
3) rsyslog 프로세스가 시작 시점에 크래시[^4]
4) 중앙 로그 수집이 끊김
5) “그날의 장애는 데이터가 없다”가 됨

이 유형은 기술적으로는 rsyslog 쪽 링크를 고치거나 패키징을 바로잡으면 끝날 수 있습니다. 운영적으로는 “systemd 업그레이드는 로깅 파이프라인 변경”이라고 계약에 써야 끝납니다.

검증 항목을 최소로 잡으면 이렇습니다.

- 업그레이드 후 `systemctl status rsyslog` (또는 사용하는 로거) 가 Active인지
- journald의 disk-usage가 급격히 증가하지 않는지
- 로그 포워딩이 기대대로 되는지(샘플 로그를 실제로 보내서 end-to-end 확인)

### 3) 네트워크 스택: networkd 설정의 폐기 예고가 “다음 분기 장애”가 되는 방식
v261 NEWS에는 systemd-networkd에 DHCP relay agent 지원을 위한 새로운 backend가 추가됐고, 그 과정에서 기존 [DHCPServer] 설정 일부가 deprecated 되며 [Network]의 DHCPRelay= 및 [DHCPRelay] 섹션으로 대체된다고 명시되어 있습니다.[^4]

이건 오늘 즉시 망가지는 변경이라기보다, 운영팀이 흔히 놓치는 “미래 장애” 유형입니다.

- 지금은 동작하지만 deprecated 경고가 쌓임
- 다음 업그레이드(예: v262 또는 배포판의 큰 점프)에서 동작이 바뀌거나 제거됨
- 네트워크 장애는 원격 접근 자체를 끊어버려 롤백 비용을 크게 올림

따라서 networkd를 쓰는 환경에서는 systemd 업그레이드 검증을 “네트워크가 붙는다/안 붙는다”로 끝내면 안 됩니다.

- (정적) config 파서 경고/폐기 경고를 CI에서 실패로 취급
- (동적) DHCP/RA/route/MTU/ethtool offload까지 최소 스모크 테스트
- (장애 복구) 네트워크가 안 붙은 상태에서의 out-of-band 접근 경로(콘솔, iDRAC, EC2 SSM 등)를 롤백 플랜에 포함

## v260.x → v261.x 점프가 특히 위험한 이유: “기능 추가”가 아니라 “경계 재설정”
v260은 큰 정리 성격이 강한 릴리스로 알려져 있습니다. 예를 들어 SysV init script 지원 제거, 최소 커널 버전 상향(5.4→5.10), 의존성/내부 구조 변경 같은 굵은 변화가 기사/요약에 반복해서 등장합니다.[^8]

v261도 마찬가지로 굵은 변화가 많습니다. Help Net Security 요약만 봐도 udev DB v0 제거(=v247 이전에서 live upgrade 경로 끊김), nspawn 옵션 rename(--user=→--uid=) 같은 “스크립트가 깨지는 종류”가 언급됩니다.[^9]

이 조합이 왜 위험하냐면, 운영에서 버전 점프는 대개 아래 두 가지 이벤트와 함께 일어나기 때문입니다.

- 배포판 릴리스 업그레이드(LTS → next LTS)
- 베이스 이미지 교체(컨테이너 런타임/쿠버네티스 노드 이미지)

즉 “systemd만 올린다”가 아니라, “커널/유저랜드/네트워크 도구/로그 도구가 동시에 바뀐다”가 되기 쉽습니다. 그러면 사고가 났을 때 원인 분석이 거의 불가능해집니다.

그래서 나는 systemd를 패키지로 취급하지 않고, platform contract로 취급하면서도, 실제 릴리스 적용은 다음 원칙으로 단순화합니다.

- v260.x에서 v260.5로 가는 것은 “동일 메이저 내 안정 릴리스”로 분류하고, 배포판 백포트 우선
- v260.x에서 v261.3로 가는 것은 “플랫폼 경계가 바뀌는 업그레이드”로 분류하고, 이미지 기반 롤아웃 + 강한 회귀 테스트를 전제

v261.3와 v260.5가 같은 날짜에 나온 것은 운영 입장에서는 “선택을 강요하는 신호”에 가깝습니다. 같은 주에 컨테이너 베이스 이미지가 갱신되면, 의도치 않게 v261로 점프할 수 있기 때문입니다.[^2]

## 검증 시나리오: systemd 업그레이드를 ‘재부팅 한 번’에서 ‘증거 기반’으로 바꾸기
아래 시나리오는 “우리 조직 표준”이 아니라, 일반적인 리눅스 서버/쿠버네티스 노드/이미지 기반 운영에서 통하는 형태로 적습니다. 핵심은 두 가지입니다.

- 업그레이드 전 스냅샷(증거)을 남긴다.
- 업그레이드 후 동일 항목을 다시 수집해 비교한다.

### 1) 업그레이드 전 스냅샷 수집 스크립트
다음 스크립트는 root로 실행하는 것을 전제합니다. distro에 따라 일부 명령이 없을 수 있으니, 실패해도 전체가 죽지 않게 작성했습니다.

```bash
#!/usr/bin/env bash
set -euo pipefail

OUT_DIR=${1:-"/var/tmp/systemd-upgrade-snapshot-$(date -u +%Y%m%dT%H%M%SZ)"}
mkdir -p "$OUT_DIR"

log() { printf "[%s] %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$OUT_DIR/run.log"; }
run() {
  local name="$1"; shift
  log "RUN $name: $*"
  ( "$@" ) >"$OUT_DIR/$name.out" 2>"$OUT_DIR/$name.err" || true
}

log "Snapshot dir: $OUT_DIR"

run 00_uname uname -a
run 01_systemd_version systemd --version
run 02_kernel_cmdline bash -lc 'cat /proc/cmdline'

# Unit/override 관점
run 10_systemctl_failed systemctl --no-pager --failed
run 11_list_unit_files systemctl --no-pager list-unit-files
run 12_list_units systemctl --no-pager list-units --all
run 13_systemd_delta systemd-delta --type=extended

# 유효 설정(merge 결과) - systemd-analyze cat-config가 있으면 가장 좋음
run 20_cat_config_system bash -lc 'systemd-analyze cat-config systemd/system.conf || true'
run 21_cat_config_journald bash -lc 'systemd-analyze cat-config systemd/journald.conf || true'
run 22_cat_config_resolved bash -lc 'systemd-analyze cat-config systemd/resolved.conf || true'
run 23_cat_config_networkd bash -lc 'systemd-analyze cat-config systemd/networkd.conf || true'

# 부팅 성능/그래프
run 30_analyze_time systemd-analyze time
run 31_analyze_critical_chain systemd-analyze critical-chain

# journald 관측치
run 40_journal_disk_usage journalctl --disk-usage
run 41_journal_verify journalctl --verify
run 42_journal_tail bash -lc 'journalctl -b --no-pager -n 300 -o short-iso'

# 네트워크 관측치 (networkd/resolved 사용하는 경우)
run 50_networkctl_status bash -lc 'networkctl status --no-pager || true'
run 51_networkctl_list bash -lc 'networkctl list --no-pager || true'
run 52_resolvectl_status bash -lc 'resolvectl status --no-pager || true'

# 파일시스템/마운트(부팅 그래프와 자주 엮임)
run 60_findmnt findmnt --json
run 61_fstab bash -lc 'cat /etc/fstab || true'

log "Done"

tar -C "$OUT_DIR" -czf "$OUT_DIR.tar.gz" .
log "Packed: $OUT_DIR.tar.gz"
```

예상 출력은 `/var/tmp/systemd-upgrade-snapshot-...tar.gz`가 생기고, 그 안에 `systemd --version`, `systemd-delta`, `systemd-analyze critical-chain`, `journalctl --verify` 등이 들어가는 형태입니다.

이 스냅샷은 “장애 났을 때만 보는 자료”가 아닙니다. 업그레이드가 성공했는지 여부를 “증거 비교”로 바꾸는 도구입니다.

### 2) 업그레이드 후 검증: PID 1이 아니라 ‘목표 상태’를 체크
업그레이드 후 검증은 순서를 잘못 잡으면 시간을 버립니다.

- `systemd --version`만 확인하는 것은 의미가 약합니다.
- `systemctl is-system-running`도 환경에 따라 degraded가 정상인 경우가 있어 애매합니다.

나는 다음 순서가 낫다고 봅니다.

1) 부팅 직후 실패 unit 존재 여부
2) 부팅 그래프가 바뀌었는지(critical-chain)
3) 네트워크/DNS가 기대대로 붙었는지
4) 로깅 파이프라인이 살아있는지

검증 커맨드를 최소로 줄이면 이렇습니다.

```bash
# 1) 실패 unit
systemctl --no-pager --failed

# 2) 부팅 그래프(부팅 지연/순환 의존/timeout 단서)
systemd-analyze critical-chain

# 3) 네트워크/DNS
networkctl list --no-pager || true
resolvectl status --no-pager || true

# 4) journald 무결성/용량
journalctl --verify
journalctl --disk-usage
```

여기서 포인트는, “정상”을 선언하기 전에 반드시 journald가 정상인지 확인하는 것입니다. v261에서 언급된 libsystemd 링크 특성 변화가 rsyslog 같은 구성요소를 건드릴 수 있다는 점을 감안하면, 로그가 멀쩡한 상태에서 기능 검증을 시작해야 합니다.[^4]

### 3) unit 파일 변경이 장애로 이어지는 것을 사전에 끊는 방법
unit 파일은 대개 `/usr/lib/systemd/system`(패키지 제공)과 `/etc/systemd/system`(로컬 override)의 조합으로 최종 결과가 나옵니다. distro 업그레이드/패키지 업그레이드 때 위험한 부분은 “패키지 쪽 unit이 바뀌고, 로컬 override가 그 변화를 상쇄하거나 더 꼬아버리는” 케이스입니다.

이때 `systemd-delta`가 매우 유용합니다.

- override가 많은 호스트는 systemd 업그레이드의 회귀 가능성이 높습니다.
- override가 0인 호스트는 “배포판 테스트 범위”에 더 가깝습니다.

업그레이드 윈도우에서 다음을 원칙으로 잡는 편이 좋습니다.

- `systemd-delta` 출력이 일정 임계치 이상이면(예: override/drop-in 30개 이상) canary 그룹에서만 먼저 업그레이드
- drop-in에서 deprecated directive가 발견되면 바로 수정(경고를 다음 분기의 장애로 넘기지 않기)

## 롤백 시나리오: systemd는 “패키지 downgrade”만으로는 부족할 때가 많다
systemd 업데이트의 롤백을 “패키지 downgrade”로만 설계하면, 네트워크 단절/부팅 실패 시에 손이 묶입니다. 따라서 롤백은 반드시 2계층으로 준비해야 합니다.

- 논리 롤백: 패키지를 이전 버전으로 되돌린다.
- 물리 롤백: 노드/이미지를 이전 상태로 되돌린다(스냅샷/이미지 교체).

나는 systemd 변경에서는 물리 롤백이 주 롤백이고, 논리 롤백은 보조라고 봅니다.

### 1) 이미지 기반(Immutable) 환경의 롤백
가장 깔끔합니다.

- v261.3 베이스 이미지와 기존 이미지(v260.x 또는 이전 v261.x)를 동시에 유지
- canary → 10% → 50% → 100%로 확장
- 문제 발생 시 트래픽/워크로드를 이전 이미지 풀로 되돌림

여기서는 systemd의 다양한 변화(부팅 그래프/네트워크/로깅)가 있어도 롤백 비용이 일정합니다.

v261에는 ConditionFraction= 같은 staged rollout을 위한 기능이 들어가 있습니다.[^4] 이런 기능을 활용하면 “서비스 단위의 단계적 활성화”를 systemd 레벨에서 할 수 있지만, 나는 systemd 업그레이드 자체의 롤아웃에는 여전히 이미지/노드 단위의 canary가 더 안전하다고 봅니다. ConditionFraction은 유닛 배치 정책을 분산시키는 도구이지, PID 1 교체의 위험을 줄여주지는 않습니다.

### 2) 패키지 기반(전통 서버) 환경의 롤백
패키지 기반은 현실적인 제약이 많습니다.

- systemd는 PID 1이라 재부팅이 사실상 필수
- downgrade 자체가 성공해도, 이미 바뀐 state(로그/런타임 파일/udev DB 등)가 남을 수 있음

v261에서 udev DB v0 지원 제거가 언급되는데, 이는 아주 오래된 버전에서의 live upgrade 경로를 끊는 변화입니다.[^4] 이 유형은 downgrade 시나리오에서도 같은 종류의 함정을 만듭니다. 즉 “되돌리면 되겠지”가 통하지 않는 영역이 존재합니다.

따라서 패키지 기반이라면 롤백 플랜에 아래가 꼭 포함돼야 합니다.

- out-of-band 콘솔 접근
- 부팅 실패 시 rescue.target / emergency shell 진입 경로
- 부팅 로더에서 이전 커널+이전 initramfs로 부팅 가능 여부(커널과 systemd가 함께 바뀌면 특히 중요)

## 배포판 백포트 vs 자체 업그레이드 판단 기준(운영 의사결정 표)
여기서는 “정답”이 아니라, 운영팀이 결정을 재사용할 수 있는 기준을 적습니다.

### 1) 업데이트 동기가 보안/권고/컴플라이언스인가
보안 이슈라면 백포트가 대개 맞습니다. systemd는 보안 권고를 GitHub Security Advisory로 올립니다. 예를 들어 2026-08-10에 systemd-oomd의 local unprivileged process kill 이슈가 공지됐고, 패치 버전이 v260.3 등으로 명시돼 있습니다.[^10] 같은 날 systemd-machined 관련 권고도 올라와 패치 버전이 v260.4 등으로 적혀 있습니다.[^11]

이런 경우는 “upstream stable을 들고 와서 올리자”보다 “배포판이 제공하는 보안 업데이트를 적용하자”가 운영적으로 깔끔합니다.

- 배포판이 backport한 패치에는 배포판 수준의 regression test가 포함될 가능성이 높음
- 자체 업그레이드는 “기능 변화”까지 함께 들고 오기 쉽고, 검증 범위가 폭증

### 2) 업데이트 동기가 기능 필요인가
기능이 필요하면 자체 업그레이드가 맞는 경우가 생깁니다.

- v261의 networkd DHCP relay 구조 변경을 실제로 활용하려는 경우[^4]
- 특정 Varlink/D-Bus 인터페이스가 필요한 경우(내부 도구가 이를 전제로 할 때)

다만 이때도 “기능을 켜는 것”과 “버전을 올리는 것”을 분리하는 것이 중요합니다.

- 먼저 버전을 올리고(기능은 off)
- 그 다음 기능을 on

그래야 장애가 났을 때 원인이 “업그레이드”인지 “기능 활성화”인지 분리됩니다.

### 3) systemd를 어디까지 쓰고 있는가(경계의 크기)
systemd를 PID 1만 쓰는 조직이 있고, networkd/resolved/journald까지 적극적으로 쓰는 조직이 있습니다. 후자로 갈수록 업그레이드 리스크가 커집니다.

v261의 NEWS에서 보이는 변화들은 대체로 “OS 레벨 기능 확장”입니다. 예를 들어 IMDS subsystem 추가 같은 항목은, 이미지가 여러 퍼블릭 클라우드를 동시에 타겟팅할 때 유용할 수 있습니다.[^4]

이런 항목을 쓰기 시작하면, systemd를 사실상 “클라우드/부트/네트워크/로그를 묶는 플랫폼”으로 채택하는 셈입니다. 그 순간부터 systemd는 패키지가 아니라 계약이 됩니다.

## 지금 할 수 있는 일: 릴리스 직후 1주 이내에 해야 효과가 큰 것들
2026-09-16 KST(오늘) 기준으로 v261.3·v260.5는 게시 후 1주 이내의 신선한 변경입니다.[^2] 이 구간에서 할 수 있는 일이 몇 가지 있습니다.

### 1) “내 fleet가 지금 실제로 어떤 systemd를 쓰는지”를 먼저 고정
운영에서 가장 흔한 착각은 “우리 배포판은 LTS니까 systemd는 변하지 않는다”입니다. 실제로는 backport로 vXXX.Y가 오르고, 컨테이너 베이스 이미지로는 더 빨리 점프합니다.

- 호스트: `systemd --version` 수집
- 컨테이너 이미지: 빌드 로그에서 systemd 패키지 버전 라벨링
- Kubernetes 노드: 노드풀 별 이미지 digest와 systemd 버전을 매핑

이걸 안 하면 v261.3 이슈인지, v260.5 이슈인지, 아니면 전혀 다른 레이어인지 구분이 안 됩니다.

### 2) journald/rsyslog 경로를 테스트 케이스로 승격
v261에서 언급된 libsystemd 링크 특성 변화는 “로깅 파이프라인이 패키지 의존성으로 깨질 수 있다”는 신호입니다.[^4]

따라서 회귀 테스트에 아래를 넣는 편이 좋습니다.

- rsyslog(또는 사용 중인 syslog) 프로세스가 cold start에서 정상 기동하는지
- 로그 1줄을 실제로 중앙까지 보내서 도착 확인

### 3) networkd를 쓰는 경우 deprecated 설정을 ‘미래 장애’로 분류
v261에서 DHCP relay 설정이 deprecated 되었다면, 당장 장애가 없더라도 backlog가 아니라 incident 예방 항목으로 분류해야 합니다.[^4]

- deprecated 키가 있는지 grep
- 있다면 새로운 섹션 구조로 마이그레이션
- 변경 후 canary에서 DHCP/라우팅 스모크 테스트

### 4) 컨테이너에서 systemd를 PID 1로 쓰는 팀에게는 “unit 파일 존재성”을 계약으로 박기
v261.3에서 unit 파일 fallback이 들어갔다면(릴리스 노트에 명시), 이제는 “unit 파일이 없어서 실패”가 더 이상 안전장치가 아닐 수 있습니다.[^7]

- 베이스 이미지에 기대하는 unit들이 실제로 존재하는지
- enable 상태가 코드로 관리되는지
- target 도달을 health check에 포함하는지

이 세 가지가 없으면, systemd의 견고함 개선이 오히려 결함 은닉이 될 수 있습니다.

## 정리: v260.5는 배포판 백포트가 기본, v261.3는 플랫폼 업그레이드로 다뤄야 한다
- v260.5는 “같은 메이저 내 안정 릴리스”로 분류하고, 배포판 백포트를 우선하는 것이 운영 책임 분리 측면에서 유리합니다.[^2]
- v261.3는 실제로는 v261 채택 여부를 결정하는 문제에 가깝고, unit/로그/네트워크의 실패 모드가 노드 단위로 커질 수 있습니다. v261의 NEWS에 적힌 변경만 봐도 networkd 설정 구조 변경(미래 제거 포함), libsystemd 링크 특성 변화로 인한 로깅 데몬 크래시 가능성 같은 전파 경로가 분명합니다.[^4]
- systemd를 패키지 업데이트로 취급하면 “재부팅 한 번”으로 끝내려는 압력이 생기고, 그 순간 관측성/네트워크/부팅 그래프의 회귀가 놓치기 쉬워집니다. systemd.io의 안정성 문서가 말하는 것처럼 stable interface가 있더라도 버그 수정은 동작 변화로 이어질 수 있다는 점을 전제로, platform contract로 취급하는 편이 실제 장애 비용을 줄입니다.[^5]

결국 선택 기준은 간단합니다. 보안/치명 버그 대응이면 배포판 백포트가 기본이고, 기능 채택이나 이미지 표준화가 목적이면 v261.3를 플랫폼 업그레이드로 다루면서 스냅샷-비교 검증과 이미지 단위 롤백을 붙이는 쪽이 맞습니다.

## 참고 자료
- [systemd GitHub Releases](https://github.com/systemd/systemd/releases)
- [Release Alert: systemd/systemd](https://releasealert.dev/github/systemd/systemd)
- [systemd v261.3 NEWS (raw)](https://raw.githubusercontent.com/systemd/systemd/v261.3/NEWS)
- [systemd: Portability and Stability](https://systemd.io/PORTABILITY_AND_STABILITY/)
- [systemd-oomd 보안 권고(GHSA-652q-wxr6-h5j6)](https://github.com/systemd/systemd/security/advisories/GHSA-652q-wxr6-h5j6)
- [systemd-machined 보안 권고(GHSA-qwv4-3gwc-w5g8)](https://github.com/systemd/systemd/security/advisories/GHSA-qwv4-3gwc-w5g8)
- [Arch Linux systemd 261.3-1 패키지 정보](https://archlinux.org/packages/core/x86_64/systemd/)
- [systemd 260 릴리스 요약(Phoronix)](https://www.phoronix.com/news/systemd-260-Released)
- [systemd 260 변경 요약(Linuxiac)](https://linuxiac.com/systemd-260-drops-sysv-init-support-in-major-cleanup-update/)
- [systemd 261 릴리스 요약(Help Net Security)](https://www.helpnetsecurity.com/2026/06/22/systemd-261-released/)

[^1]: <https://github.com/systemd/systemd/releases/tag/v261.3>
[^2]: <https://releasealert.dev/github/systemd/systemd>
[^3]: <https://archlinux.org/packages/core/x86_64/systemd/>
[^4]: <https://raw.githubusercontent.com/systemd/systemd/v261.3/NEWS>
[^5]: <https://systemd.io/PORTABILITY_AND_STABILITY/>
[^6]: <https://documentation.ubuntu.com/release-notes/26.04/summary-for-lts-users/>
[^7]: <https://github.com/systemd/systemd/releases>
[^8]: <https://www.phoronix.com/news/systemd-260-Released>
[^9]: <https://www.helpnetsecurity.com/2026/06/22/systemd-261-released/>
[^10]: <https://github.com/systemd/systemd/security/advisories/GHSA-652q-wxr6-h5j6>
[^11]: <https://github.com/systemd/systemd/security/advisories/GHSA-qwv4-3gwc-w5g8>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
