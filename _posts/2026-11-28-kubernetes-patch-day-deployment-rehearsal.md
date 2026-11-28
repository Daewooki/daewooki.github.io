---
title: "Kubernetes 1.35.11·1.36.7·1.37.3: 패치일을 배포 리허설로"
description: "세 유지 브랜치 동시 패치를 월간 배포 이벤트로 운영하기 위한 버전 스큐·애드온·노드 이미지·런타임·롤백 체크리스트를 정리합니다."
date: 2026-11-28 13:13:58 +0900
categories: ["News", "DevOps"]
tags: ["kubernetes", "release-engineering", "upgrade", "sre", "devops"]
render_with_liquid: false
---

## 2026-11-25에 무슨 일이 있었나: 세 유지 브랜치 동시 패치

2026-11-25에 Kubernetes 패치 릴리스가 세 유지 브랜치에서 동시에 게시됐습니다. GitHub 릴리스 기준으로 v1.37.3, v1.36.7, v1.35.11이 같은 날 올라왔고, 각 릴리스는 kubernetes-announce 메일링 리스트와 CHANGELOG를 보라고 안내합니다. 같은 날짜에 여러 유지 브랜치가 함께 움직인 달은 패치를 단순 업데이트로 취급하기 어려워집니다. 이 날 자체가 조직에겐 배포 이벤트가 됩니다.

- [kubernetes/kubernetes GitHub Releases](https://github.com/kubernetes/kubernetes/releases?after=v1.14.10)

이 날짜가 우연은 아닙니다. Kubernetes 공식 패치 릴리스 캘린더는 월간 타깃을 공개하고, 2026년 11월의 Target Date를 11월 25일로 잡아둡니다. 동시에 Cherry Pick Deadline도 11월 20일로 명시돼 있습니다. 즉 11월 25일은 릴리스 엔지니어링 관점에서 릴리스 컷을 치고, 체리픽을 닫고, 아티팩트를 뽑는 날로 설계된 날짜입니다.

- [Kubernetes Patch Releases 일정](https://kubernetes.io/releases/patch-releases/)

여기서 중요한 건, 업스트림이 월간 패치를 달력에 박아 넣는 순간부터 패치는 운영팀의 달력이 됩니다. 특히 1.35/1.36/1.37처럼 지원되는 세 마이너 라인에서 같은 날 패치를 찍어내면, 조직 내부에서도 같은 날 배포 리허설을 돌리기가 가장 자연스럽습니다.

## 패치 릴리스는 왜 단순 업데이트가 아닌가

패치 릴리스는 API 레벨에서 큰 변화가 없다는 의미의 patch일 뿐, 운영 레벨에서의 변화가 작다는 뜻은 아닙니다. 내 경험상 월간 패치가 배포 이벤트가 되는 이유는 크게 네 가지입니다.

첫째, 패치는 코드 변경량이 작아도 변경의 위치가 깊습니다. kube-apiserver, kubelet, kube-proxy, client-go 같은 핵심 컴포넌트의 결함 수정은 표면적 기능 변화가 적어도 장애 모양새를 바꿉니다. 특히 kubelet이나 네트워크 계층의 수정은 재현이 어려운 종류가 많아서, 작은 패치가 큰 운영 리스크로 전이됩니다.

둘째, 패치는 Kubernetes만 바뀌지 않습니다. 조직이 실제로 운영하는 건 Kubernetes + 애드온 + 노드 이미지 + 런타임 + 보안 정책 + 관측 스택의 묶음입니다. 업그레이드는 늘 이 묶음 전체를 흔듭니다.

셋째, 패치 릴리스는 업스트림의 릴리스 컷을 그대로 반영합니다. 패치 릴리스 프로세스는 체리픽이 제때 merge-ready여야 하고 라벨과 CI를 통과해야 한다는 운영 규칙을 갖습니다. 이 규칙은 업스트림 컨트리뷰터만을 위한 게 아니라, 다운스트림인 우리에게도 그대로 적용됩니다. 내부 릴리스도 비슷한 동결, 체리픽, 검증이라는 흐름을 갖게 되기 때문입니다.

- [Patch release 체리픽 요구사항(라벨/CI/데드라인)](https://github.com/kubernetes/website/blob/main/content/en/releases/patch-releases.md)

넷째, 월간 패치는 인력과 권한 구조를 고정시킵니다. 업스트림 SIG Release 문서에서 릴리스 매니저가 patch 포함 릴리스 컷과 브랜치 관리, 체리픽 조율을 책임진다고 정의합니다. 내부에서도 결국 누군가는 릴리스 오너가 돼야 합니다.

- [SIG Release Release Manager handbook](https://github.com/kubernetes/sig-release/blob/master/release-engineering/handbooks/release-manager.md)

나는 예전에 패치 릴리스를 운영 계약으로 바꾸는 관점을 정리한 적이 있습니다. 그 글은 주로 패치의 의미를 조직의 약속으로 만들기 위한 프레이밍에 집중했고, 이번 글은 그 관점을 배포 이벤트로 굳히는 체크리스트와 실행 단계를 더 밀어붙이는 쪽입니다.

- [Kubernetes 1.35.10 패치 릴리스: 정기 패치를 운영 계약으로 바꾸는 법](https://daewooki.github.io/posts/kubernetes-patch-release-ops-contract/)

## 연말 리듬 점검 포인트: 1.35 유지보수 전환이 만드는 압력

이번 타이밍이 연말 점검에 특히 맞는 이유는 1.35의 라이프사이클 변화가 바로 앞에 있기 때문입니다.

Kubernetes 1.35 릴리스 시리즈 페이지는 Maintenance Mode Start Date가 2026-12-28이고 End Of Life Date가 2027-02-28이라고 밝힙니다. 즉 2026-11-25 패치 이후로 한 달 남짓 지나면 1.35는 actively supported에서 maintenance 모드로 들어갑니다.

- [Kubernetes 1.35 릴리스 시리즈 상태(maintenance/EOL)](https://kubernetes.io/releases/1.35/)
- [Kubernetes Patch Releases에서 1.35 지원 기간](https://kubernetes.io/releases/patch-releases/)

여기서 조직이 흔히 착각하는 지점이 있습니다.

- maintenance 모드는 배포를 멈추라는 신호가 아니라, 업스트림에서 backport의 우선순위가 달라지고 기대 가능한 변경의 종류가 달라진다는 신호입니다.
- EOL 날짜는 달력의 숫자가 아니라, 취약점/버그가 고쳐져도 더 이상 내 버전에는 안 내려올 수 있다는 뜻입니다.

게다가 Kubernetes는 기본적으로 최근 세 개 마이너 버전에 대해 릴리스 브랜치를 유지한다는 정책을 문서로 명시합니다. 따라서 1.35가 빠지는 순간, 지원되는 라인이 1.36/1.37/1.38으로 바뀌고, 내부 플랫폼의 기본선도 바뀝니다.

- [Version Skew Policy 문서의 “최근 세 마이너 유지” 언급](https://kubernetes.io/releases/version-skew-policy/)

연말에 패치일을 배포 리허설로 돌려야 하는 이유는 여기서 생깁니다. 1.35를 계속 가져갈 조직이라면 maintenance 모드 진입 전 마지막으로 리듬을 다져야 하고, 1.36+로 넘어갈 조직이라면 버전 스큐와 애드온 업그레이드 순서를 점검해야 합니다.

## 버전 스큐가 체크리스트의 중심이 되는 이유

패치 릴리스가 배포 이벤트로 느껴지는 핵심 이유는 결국 version skew 때문입니다. 실제 운영은 다음 네 종류의 스큐가 동시에 존재합니다.

1) control plane 내부 스큐: HA 구성에서 kube-apiserver가 동시에 같은 버전이 아닐 수 있음
2) control plane ↔ node 스큐: kubelet, kube-proxy
3) 클라이언트 스큐: kubectl, CI에서 쓰는 client-go
4) 애드온 스큐: CNI, CoreDNS, CSI, ingress controller, service mesh, observability

Kubernetes는 컴포넌트 간 최대 허용 스큐를 문서로 박아두고, 특히 kube-apiserver와 kubelet 사이, kube-apiserver와 kubectl 사이에 대한 규칙을 상세히 씁니다. 이 문서가 체크리스트의 첫 페이지가 돼야 합니다.

- [Kubernetes Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/)

여기서 운영적으로 자주 터지는 실수는 두 가지입니다.

- **스큐는 허용되지만, 업그레이드 순서는 강제된다**는 걸 잊는 경우
- 스큐 허용 범위를 “평상시에도 그렇게 둬도 된다”로 오해하는 경우

스큐 정책은 업그레이드를 가능하게 하려고 제공하는 안전장치이지, 상시 방치해도 된다는 의미가 아닙니다. 스큐가 커질수록 업그레이드 창은 짧아지고, 장애시 디버깅 비용은 커집니다.

특히 HA control plane에서 일부 apiserver만 먼저 올라가면, 그 순간부터 kubectl 허용 범위가 더 좁아질 수 있다는 경고가 문서에 등장합니다. 나는 이 문장을 체크리스트의 “업그레이드 순서” 항목에 그대로 적어둡니다.

## 체크리스트를 Kubernetes 밖으로 확장해야 하는 이유

패치 릴리스를 월간 배포 리허설로 취급하려면, 체크리스트는 반드시 Kubernetes 버전 숫자 밖으로 확장돼야 합니다. 내 기준에서 체크리스트 범위는 다섯 레이어입니다.

### 1) 클러스터 구성요소: control plane, kubelet, kube-proxy, kubectl

여기서 하는 일은 단순합니다.

- 현재 control plane 버전 확인
- 노드별 kubelet 버전 확인
- 관리 워크스테이션/CI의 kubectl 버전 확인
- kube-proxy(daemonset) 이미지 태그 확인

이건 한 줄짜리 작업 같지만, 패치일에 이것들을 한 번에 모아 표 형태로 남기면 다음 달부터 변화량이 눈에 보이기 시작합니다. 나는 이 표를 월간 릴리스 리포트의 1페이지로 고정합니다.

### 2) 애드온 호환성: CNI/CoreDNS/CSI/Ingress/Observability

업스트림 패치는 업스트림 기준으로 안전합니다. 조직이 직접 설치한 애드온은 그 안전함에 포함되지 않습니다.

특히 다음 타입은 패치업에서 문제가 나면 blast radius가 큽니다.

- CNI: 네트워크 단절은 곧 장애
- CSI: 노드 롤링 중 PV detach/attach 이슈가 나면 복구 시간이 급격히 길어짐
- CoreDNS: 장애 모양새가 애플리케이션 장애로 보임
- Ingress/controller: HTTP 레이어 장애는 즉시 SLA로 연결

체크리스트에는 “애드온이 돌아간다”가 아니라, “애드온이 어떤 Kubernetes minor/patch 범위를 지원하는가”가 들어가야 합니다. 현실적으로는 Helm chart 버전, 이미지 태그, 그리고 upstream compatibility 문서 링크를 함께 적게 됩니다.

여기서 중요한 운영 감각은, 애드온 업그레이드를 Kubernetes 패치와 같이 묶으면 리스크가 커진다는 점입니다. 그래서 나는 월간 배포 리허설을 두 단계로 분리하는 편을 선호합니다.

- 1단계: Kubernetes patch만 반영 (애드온은 고정)
- 2단계: 애드온 patch/minor 반영 (Kubernetes는 고정)

둘을 같은 날 하면 원인 추적이 지옥이 됩니다.

### 3) 노드 이미지: OS/kernel/cgroup/sysctl/GPU driver

Kubernetes patch는 control plane 바이너리만 바꾸는 게 아닙니다. 대부분의 조직에서 실제 변경의 무게중심은 노드 이미지로 이동합니다.

- OS 패키지 업데이트
- 커널 업데이트
- iptables/nftables 동작 변화
- cgroup 설정 및 systemd 동작 변화
- GPU driver/NVIDIA stack 업데이트

패치일을 리허설로 만들려면, “Kubernetes patch + node image patch”를 한 묶음으로 취급하는 습관이 필요합니다. 노드 이미지가 고정돼 있지 않으면, 매달 다른 기저 상태에서 kubelet이 올라가고 내려옵니다. 이건 월간 리허설이 아니라 월간 도박에 가깝습니다.

### 4) 컨테이너 런타임: containerd/CRI-O, CRI v1, 설정 드리프트

Kubernetes는 CRI를 통해 런타임과 결합을 끊었지만, 운영 현장에선 런타임이 패치 이벤트의 핵심 리스크입니다.

- kubelet이 재시작하는 순간 CRI 호환이 맞지 않으면 노드는 Ready가 되지 않습니다.
- 런타임 설정이 드리프트돼 있으면, 일부 노드만 문제를 일으켜 장애가 불규칙하게 보입니다.

Kubernetes 문서는 프로덕션 환경에서 사용하는 컨테이너 런타임을 정리하고 있고, CRI 지원이 필수라는 걸 여러 문서에서 반복합니다.

- [Kubernetes Container Runtimes 문서](https://kubernetes.io/docs/setup/production-environment/container-runtimes/)
- [kubeadm 설치 문서의 cri-dockerd 언급](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/)
- [Kubernetes CRI 개념 문서](https://kubernetes.io/docs/concepts/containers/cri/)

런타임 쪽에서 내가 특히 중요하게 보는 근거는 containerd의 릴리스 정책 문서입니다. containerd는 Kubernetes가 n-3 마이너만 지원한다는 점을 전제로, 지원되는 Kubernetes마다 지원되는 containerd가 항상 존재하도록 하겠다고 명시합니다. 이 말은 뒤집으면, Kubernetes가 지원하지 않는 마이너를 들고 있으면 런타임과의 호환성도 같이 흔들린다는 뜻입니다.

- [containerd RELEASES.md](https://github.com/containerd/containerd/blob/main/RELEASES.md)

### 5) Go/toolchain과 supply chain

패치 릴리스에서 종종 벌어지는 일은 “Go 버전만 올리는 out-of-band patch”입니다. Kubernetes 1.35 릴리스 시리즈 페이지는 1.35.2가 Go CVE를 해결하기 위해 out-of-band로 나갔고 다른 변경이 없었다고 적어둡니다. 이 유형은 운영팀에게 굉장히 불편합니다. 기능 변화가 없는데도 배포해야 하는 이유가 보안 한 줄로 요약되기 때문입니다.

- [Kubernetes 1.35 패치 히스토리(Go CVE 목적 out-of-band 언급)](https://kubernetes.io/releases/1.35/)

그래서 체크리스트에는 “이번 달 패치가 보안/툴체인 성격인가”를 분류하는 항목이 들어가야 합니다. 툴체인 성격이면 애드온 업그레이드는 더더욱 분리하는 편이 낫습니다.

## ‘정기 패치일’이 배포 이벤트가 되도록 만드는 운영 설계

패치일을 배포 이벤트로 만든다는 말은, 그냥 긴장해서 배포한다는 뜻이 아닙니다. 다음 네 가지를 고정하겠다는 뜻입니다.

1) 릴리스 컷: 변경을 어떤 시점에 자르고, 무엇을 고정할지 정의
2) 링/카나리: 어디까지를 같은 이벤트로 묶고, 어디서 멈출지 정의
3) 검증 게이트: 어떤 신호가 OK면 다음 단계로 가는지 정의
4) 롤백: 실패했을 때 되돌릴 수 있는 레이어를 명확히 정의

업스트림도 결국 이 구조로 굴러갑니다. 패치 릴리스 일정 문서에는 체리픽이 merge-ready여야 하고 라벨과 CI를 통과해야 한다고 적습니다. 이것이 업스트림의 검증 게이트입니다.

- [Patch release 체리픽 요구사항(라벨/CI/데드라인)](https://github.com/kubernetes/website/blob/main/content/en/releases/patch-releases.md)

또한 SIG Release 역할 문서들은 patch를 포함한 릴리스 컷의 책임과 타이밍을 설명합니다. 업스트림의 릴리스 매니저가 하는 일을 조직 내부 플랫폼 오너가 그대로 해야 합니다.

- [SIG Release Release Manager handbook](https://github.com/kubernetes/sig-release/blob/master/release-engineering/handbooks/release-manager.md)

나는 릴리스 컷오프와 동결을 팀 프로세스로 고정하는 방법을 별도 글로 정리해둔 적이 있습니다. 이번 글에서는 그 내용을 반복하지 않고, 패치일 체크리스트가 어떤 지점에서 그 동결 프로세스와 연결되는지에만 쓰겠습니다.

- [Kubernetes Code Freeze로 배우는 릴리스 컷오프 운영법](https://daewooki.github.io/posts/kubernetes-release-cutoff-freeze-ops/)

## 월간 배포 리허설 체크리스트: 링/카나리/롤백 중심으로

체크리스트는 항목 수가 많아질수록 가치가 떨어집니다. 항목을 늘리는 대신, 실행 순서를 링으로 고정하는 편이 낫습니다. 아래는 내가 실제로 쓰는 형태를 일반화한 버전입니다.

### 링 정의

- Ring 0: 전용 스테이징 클러스터(가능하면 production과 동일한 노드 이미지/런타임)
- Ring 1: production 내 소수 노드풀(예: stateless 위주, 트래픽 1~5%)
- Ring 2: production 내 대부분 노드풀
- Ring 3: 가장 민감한 워크로드(예: stateful, GPU, 레거시, 규제)

Ring 0에서 control plane까지 검증하는 게 이상적이지만, 조직 상황에 따라 어렵습니다. 그 경우에도 최소한 Ring 0에서 node image + kubelet + 런타임 조합은 태워봐야 합니다. kubelet 재시작은 런타임 호환 문제가 가장 많이 드러나는 순간입니다.

### 배포 이벤트를 구성하는 고정 순서

1) 릴리스 컷: 이번 달 대상 버전, 대상 클러스터/노드풀, 동결 시점 확정
2) 사전 인벤토리: 버전 스큐/노드 이미지/런타임/애드온 현황 스냅샷
3) Ring 0 적용: 패치 적용 → smoke test → 기본 SLO 신호 확인
4) Ring 1 적용: 제한된 노드풀 롤링 → 에러 버짓 신호 확인
5) Ring 2/3 확장: 동일 절차 반복
6) 사후 리포트: 실제 변경된 것(버전 숫자와 이미지 다이제스트) 기록

여기서 롤백은 두 레이어로 나눠서 정의하는 게 현실적입니다.

- 클러스터 레벨 롤백: control plane 롤백은 쉽지 않으므로, 가능한 범위를 명확히 문서화(대부분은 etcd snapshot 기반 복구)
- 노드 레벨 롤백: 노드 이미지/런타임을 이전으로 되돌릴 수 있어야 함(ASG/머신풀 롤백, 이미지 pin)

나는 패치일 운영에서 “control plane 롤백 계획”을 과대평가하지 않습니다. 대개는 되돌리는 것보다 앞으로 나아가는 것이 더 빠릅니다. 대신 etcd snapshot과 재구성(runbook)을 실제로 실행 가능한 수준으로 유지합니다.

## 실전: 월간 패치 리허설 파이프라인(자체 kubeadm 클러스터 기준)

아래 예시는 kubeadm으로 구성한 self-managed 클러스터를 기준으로 합니다. managed Kubernetes(EKS/GKE/AKS 등)는 control plane 업그레이드가 API로 추상화돼 있어도, 노드 이미지와 애드온 호환성 때문에 결국 동일한 리허설이 필요합니다.

특히 EKS 문서는 커스텀 AMI를 쓰는 경우, AMI에 포함된 Kubernetes 버전이 control plane 버전과 맞는지 EKS가 검증하지 않으며 사용자가 version skew 정책을 지켜야 한다고 명시합니다. 이 유형의 책임 전가는 월간 리허설을 강제합니다.

- [Amazon EKS User Guide(PDF)의 커스텀 AMI/버전 스큐 책임](https://docs.aws.amazon.com/pdfs/eks/latest/userguide/eks-ug.pdf)

### 전제

- OS: Ubuntu 계열(노드)
- control plane: kubeadm
- 도구: kubectl, jq, bash, python3

아래는 리허설을 위한 디렉터리 구조 예시입니다.

```text
k8s-monthly-patch-rehearsal/
  scripts/
    00-inventory.sh
    01-version-skew-check.py
    02-etcd-snapshot.sh
    10-upgrade-control-plane.sh
    20-upgrade-workers.sh
    90-postcheck.sh
  config/
    target.env
    rings.env
  out/
    inventory-YYYYMMDD.json
    skew-report-YYYYMMDD.txt
    etcd-snapshot-YYYYMMDD.db
```

`config/target.env`는 이번 달 목표를 고정합니다.

```bash
# config/target.env
TARGET_K8S_VERSION="v1.37.3"
# 예: v1.36.7 또는 v1.35.11도 가능
```

`config/rings.env`는 링을 노드 라벨로 정의합니다.

```bash
# config/rings.env
RING1_SELECTOR='node-role.kubernetes.io/worker=,patch-ring=ring1'
RING2_SELECTOR='node-role.kubernetes.io/worker=,patch-ring=ring2'
RING3_SELECTOR='node-role.kubernetes.io/worker=,patch-ring=ring3'
```

### 1) 인벤토리 수집: 버전/노드 이미지/런타임을 JSON으로 고정

`scripts/00-inventory.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d)"
OUT="out/inventory-${STAMP}.json"

mkdir -p out

kubectl version -o json > "out/kubectl-version-${STAMP}.json"

kubectl get nodes -o json | jq '{
  collectedAt: now | todate,
  nodes: [.items[] | {
    name: .metadata.name,
    labels: .metadata.labels,
    kubeletVersion: .status.nodeInfo.kubeletVersion,
    kubeProxyVersion: .status.nodeInfo.kubeProxyVersion,
    containerRuntimeVersion: .status.nodeInfo.containerRuntimeVersion,
    osImage: .status.nodeInfo.osImage,
    kernelVersion: .status.nodeInfo.kernelVersion,
    architecture: .status.nodeInfo.architecture
  }]
}' > "${OUT}"

echo "Wrote ${OUT}"
```

실행:

```bash
bash scripts/00-inventory.sh
```

예상 출력(형태만 예시):

```text
Wrote out/inventory-20261128.json
```

이 파일이 다음 달 리허설의 비교 기준이 됩니다. 패치일을 이벤트로 운영하면, 이 JSON이 단순 기록이 아니라 변경 승인의 증거가 됩니다.

### 2) Version skew 검사: 정책을 코드로 박아 넣기

스큐 정책은 문서로 읽는 순간에는 쉽고, 배포 중에는 쉽게 잊습니다. 그래서 나는 스큐 규칙을 파이프라인에서 실패 조건으로 강제합니다.

`scripts/01-version-skew-check.py`

```python
#!/usr/bin/env python3
import json
import re
import sys

INV_PATH = sys.argv[1] if len(sys.argv) > 1 else None
if not INV_PATH:
    print("usage: 01-version-skew-check.py out/inventory-YYYYMMDD.json", file=sys.stderr)
    sys.exit(2)

with open(INV_PATH, "r", encoding="utf-8") as f:
    inv = json.load(f)

# kubeletVersion: "v1.37.2" 형태를 가정
semver_re = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")

def parse(v: str):
    m = semver_re.search(v)
    if not m:
        return None
    return tuple(int(x) for x in m.groups())

nodes = inv["nodes"]

# control plane 버전은 여기서 직접 가져오기 어렵기 때문에,
# 운영에서는 별도 수집(kubectl version -o json)과 결합시키는 편이 안정적입니다.
# 이번 예시는 kubelet 버전 분포가 '과도하게' 갈라졌는지(드리프트)만 잡습니다.

versions = {}
for n in nodes:
    kv = n.get("kubeletVersion")
    if kv:
        versions.setdefault(kv, 0)
        versions[kv] += 1

print("kubelet version distribution:")
for v, c in sorted(versions.items()):
    print(f"  {v}: {c}")

parsed = [parse(v) for v in versions.keys()]
parsed = [p for p in parsed if p is not None]
if not parsed:
    print("ERROR: could not parse kubelet versions", file=sys.stderr)
    sys.exit(1)

min_v = min(parsed)
max_v = max(parsed)

# 운영적으로 위험한 신호: 노드가 patch를 넘어 minor까지 섞여 있는 상태
if (min_v[0], min_v[1]) != (max_v[0], max_v[1]):
    print("ERROR: kubelet minor versions are mixed across nodes; treat this as a failed precheck", file=sys.stderr)
    sys.exit(1)

# patch만 섞인 경우에도 과도한 분산은 롤링 업그레이드 리스크를 키웁니다.
if max_v[2] - min_v[2] >= 3:
    print("ERROR: kubelet patch skew >= 3 detected; likely drifted fleet", file=sys.stderr)
    sys.exit(1)

print("OK: no dangerous kubelet drift detected")
```

실행:

```bash
python3 scripts/01-version-skew-check.py out/inventory-20261128.json
```

예상 출력(형태만 예시):

```text
kubelet version distribution:
  v1.37.2: 42
OK: no dangerous kubelet drift detected
```

이 스크립트는 문서의 모든 스큐 규칙을 구현하진 않습니다. 핵심은 “스큐를 허용하는 것”과 “스큐를 방치하는 것”을 분리하는 실패 조건을 파이프라인에 심는 것입니다. 문서 기반의 엄밀한 규칙은 [Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/)를 근거로 단계적으로 코드화합니다.

### 3) etcd snapshot: 롤백을 약속이 아니라 파일로 만들기

control plane 업그레이드에서 가장 현실적인 안전장치는 etcd snapshot입니다. kubeadm 기반에서 etcd가 static pod로 떠 있다면, kubectl exec로 snapshot을 뜰 수 있습니다.

`scripts/02-etcd-snapshot.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d)"
OUT="out/etcd-snapshot-${STAMP}.db"

mkdir -p out

# 환경에 따라 etcd Pod 이름/컨테이너 이름이 다를 수 있습니다.
# kubeadm HA 구성이라면 멤버별로 snapshot을 뜨는 전략이 필요합니다.
ETCD_POD="$(kubectl -n kube-system get pods -l component=etcd -o jsonpath='{.items[0].metadata.name}')"

kubectl -n kube-system exec "${ETCD_POD}" -- sh -c '
  export ETCDCTL_API=3
  etcdctl version
' >/dev/null

kubectl -n kube-system exec "${ETCD_POD}" -- sh -c '
  set -e
  export ETCDCTL_API=3
  # kubeadm 기본 경로를 가정합니다.
  etcdctl \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key \
    snapshot save /tmp/etcd-snapshot.db
' >/dev/null

kubectl -n kube-system cp "${ETCD_POD}:/tmp/etcd-snapshot.db" "${OUT}"

echo "Wrote ${OUT}"
```

실행:

```bash
bash scripts/02-etcd-snapshot.sh
```

예상 출력:

```text
Wrote out/etcd-snapshot-20261128.db
```

여기까지가 롤백 체크리스트의 최소선입니다. 롤백을 runbook에만 적어두면 대부분 실행되지 않습니다. 파일로 남겨두면 실행됩니다.

### 4) 업그레이드 실행: 링 단위로 노드를 롤링

kubeadm 업그레이드는 기본적으로 control plane 먼저, 그 다음 워커 노드 롤링이라는 순서를 강제합니다. 이 순서 자체가 스큐 정책의 구현입니다.

- [kubeadm 클러스터 생성/운영 문서에서의 스큐 권고](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/create-cluster-kubeadm/)

아래는 “노드풀을 selector로 잡아 drain → 패키지 업그레이드 → kubeadm upgrade node → uncordon” 흐름을 자동화하는 예시입니다. 패키지 설치 방식(apt/yum), kubelet/kubeadm 버전 고정 방식은 환경마다 달라서, 핵심 명령의 뼈대만 남깁니다.

`scripts/20-upgrade-workers.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

source config/target.env
source config/rings.env

SELECTOR="${1:?usage: 20-upgrade-workers.sh '<label-selector>'}"

NODES=( $(kubectl get nodes -l "${SELECTOR}" -o name | sed 's|node/||') )

echo "Target Kubernetes: ${TARGET_K8S_VERSION}"
echo "Nodes: ${#NODES[@]}"

for n in "${NODES[@]}"; do
  echo "--- upgrading ${n} ---"

  kubectl drain "${n}" --ignore-daemonsets --delete-emptydir-data --grace-period=60 --timeout=10m

  # 여기서부터는 노드 접근 방식(ssh/SSM/daemonset)이 조직마다 다릅니다.
  # 예시는 ssh가 된다고 가정합니다.
  ssh "${n}" "sudo kubeadm upgrade node" 
  ssh "${n}" "sudo systemctl restart kubelet"

  kubectl uncordon "${n}"

  kubectl wait --for=condition=Ready "node/${n}" --timeout=5m
  echo "OK ${n} is Ready"
done
```

이 스크립트의 핵심은 기능이 아니라 구조입니다.

- 링 단위로 selector를 바꾸면 Ring 1, Ring 2, Ring 3을 같은 코드로 돌릴 수 있습니다.
- drain/uncordon이 표준화되면, 노드 이미지/런타임 변경도 같은 파이프라인에 끼울 수 있습니다.

### 5) 사후 점검: 성공 기준을 숫자로 고정

패치일의 실패는 대부분 배포 직후에 드러나지 않습니다. 그래서 사후 점검은 “정상 동작 확인”이 아니라 “다음 24시간에 장애로 이어질 조짐”을 숫자로 보는 쪽이 낫습니다.

`scripts/90-postcheck.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

kubectl get nodes -o wide
kubectl get pods -A --field-selector=status.phase!=Running || true

# control plane readiness 신호
kubectl get --raw='/readyz?verbose' | head -n 50

# kube-system에서 CrashLoopBackOff 유무를 먼저 봅니다.
kubectl -n kube-system get pods -o wide
```

여기서 더 중요한 건, 이 결과를 “배포 리포트”로 남기는 것입니다. 월간 리허설이 쌓이면, 패치일이 진짜 배포 이벤트가 됩니다. 이벤트가 된다는 말은 조직이 그 이벤트를 반복적으로 수행할 수 있는 형태로 기억한다는 뜻입니다.

## 반론과 회의론: 매달 리허설이 과한가

패치일을 배포 이벤트로 만들자고 하면 바로 나오는 반론이 있습니다.

- patch는 원래 안전한데 왜 이렇게 무겁게 하느냐
- 매달 하면 피로도가 누적된다
- 우리 조직은 managed Kubernetes라서 필요 없다

내 판단은 반대입니다.

1) patch는 기능 변화가 작을 뿐, 운영 위험이 작지 않습니다. 패치에서 가장 위험한 건 기능이 아니라 운영 기저(노드/런타임/애드온)와의 조합입니다.

2) 피로도는 이벤트를 크게 잡아서 생깁니다. 링을 나누고, 애드온과 Kubernetes patch를 분리하고, 실패 조건을 자동화하면 피로도는 줄어듭니다. 사람을 갈아 넣는 배포가 아니라, 절차를 갈아 넣는 배포가 돼야 합니다.

3) managed Kubernetes일수록 월간 리허설이 필요해집니다. control plane이 추상화되면 “내가 모르는 변경”이 늘어납니다. 그 상태에서 노드 이미지와 애드온 버전을 내가 관리하면, 책임은 분리돼도 장애는 합쳐져서 옵니다. EKS 문서가 커스텀 AMI의 버전 스큐 책임을 사용자에게 넘기는 구조가 대표적입니다.

- [Amazon EKS User Guide(PDF)의 커스텀 AMI/버전 스큐 책임](https://docs.aws.amazon.com/pdfs/eks/latest/userguide/eks-ug.pdf)

결국 월간 리허설이 과한 조직은, 월간 리허설을 안 해도 되는 구조(예: 노드 이미지/런타임/애드온이 강하게 묶여 테스트된 배포 채널)를 가진 조직뿐입니다. 대부분은 그렇지 않습니다.

## 앞으로 지켜볼 것: 12월 패치와 1.35의 maintenance 진입

업스트림 패치 캘린더는 2026년 12월 타깃을 12월 8일로 잡고 있고, Cherry Pick Deadline을 12월 4일로 둡니다. 즉 11월 25일 릴리스가 끝나자마자 2주도 안 돼 다음 달 패치 사이클이 시작됩니다.

- [Kubernetes Patch Releases 일정(2026년 12월)](https://kubernetes.io/releases/patch-releases/)

1.35는 2026-12-28에 maintenance 모드로 넘어갑니다. 이 날짜 이후에는 1.35를 계속 들고 갈지, 1.36+로 넘어갈지에 대한 결정이 운영 리듬과 직접 결합됩니다.

- [Kubernetes 1.35 릴리스 시리즈 상태(maintenance/EOL)](https://kubernetes.io/releases/1.35/)

내가 보는 관전 포인트는 두 가지입니다.

- 1.35를 유지하는 조직에서 “EOL 직전 마지막 스퍼트”로 위험한 변경(애드온+노드 이미지+Kubernetes)을 한 번에 묶어버리는지
- 1.36/1.37로 넘어가는 조직에서 version skew를 방치한 채 control plane만 먼저 올리는 식의 기술부채가 누적되는지

패치일을 월간 리허설로 운영하면, 이 두 가지가 모두 완화됩니다.

## 결론: 패치 릴리스는 월간 배포 리허설로 운영될 때 가치가 커진다

2026-11-25의 v1.35.11·v1.36.7·v1.37.3 동시 패치는 업스트림의 정기 일정이지만, 조직에겐 배포 이벤트로 취급할 만한 충분한 이유가 있습니다. 지원 브랜치가 동시에 움직이는 달은 릴리스 컷(동결/체리픽/검증)을 팀 프로세스로 고정하기 가장 좋은 달이고, 1.35가 2026-12-28에 maintenance로 전환되는 일정은 연말 리듬을 점검하기에 딱 맞는 압력으로 작동합니다.

패치일 운영의 본질은 Kubernetes 버전 숫자를 올리는 것이 아니라, version skew·애드온 호환성·노드 이미지·컨테이너 런타임·롤백을 하나의 배포 단위로 묶어서 매달 같은 방식으로 실행하는 것입니다. 그 반복이 쌓일수록 정기 패치일은 캘린더의 날짜가 아니라, 조직이 실제로 배포할 수 있다는 사실을 증명하는 이벤트가 됩니다.

## 참고 자료

- [kubernetes/kubernetes GitHub Releases](https://github.com/kubernetes/kubernetes/releases?after=v1.14.10)
- [Kubernetes Patch Releases 일정](https://kubernetes.io/releases/patch-releases/)
- [Kubernetes 1.35 릴리스 시리즈 상태(maintenance/EOL)](https://kubernetes.io/releases/1.35/)
- [Kubernetes 1.36 릴리스 시리즈](https://kubernetes.io/releases/1.36/)
- [Kubernetes 1.37 릴리스 시리즈](https://kubernetes.io/releases/1.37/)
- [Kubernetes Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/)
- [SIG Release Release Manager handbook](https://github.com/kubernetes/sig-release/blob/master/release-engineering/handbooks/release-manager.md)
- [Patch release 체리픽 요구사항(라벨/CI/데드라인)](https://github.com/kubernetes/website/blob/main/content/en/releases/patch-releases.md)
- [Kubernetes Release Cycle](https://kubernetes.io/releases/release/)
- [Kubernetes Container Runtimes 문서](https://kubernetes.io/docs/setup/production-environment/container-runtimes/)
- [Kubernetes CRI 개념 문서](https://kubernetes.io/docs/concepts/containers/cri/)
- [containerd RELEASES.md](https://github.com/containerd/containerd/blob/main/RELEASES.md)
- [Amazon EKS User Guide(PDF)의 커스텀 AMI/버전 스큐 책임](https://docs.aws.amazon.com/pdfs/eks/latest/userguide/eks-ug.pdf)
- [Kubernetes 1.35.10 패치 릴리스: 정기 패치를 운영 계약으로 바꾸는 법](https://daewooki.github.io/posts/kubernetes-patch-release-ops-contract/)
- [Kubernetes Code Freeze로 배우는 릴리스 컷오프 운영법](https://daewooki.github.io/posts/kubernetes-release-cutoff-freeze-ops/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
