---
title: "NVIDIA Network Operator v26.1.0: Spectrum‑X GA와 SOS 운영 가이드"
description: "Spectrum‑X GA·SOS 리포트 도입을 ‘클러스터 네트워킹 릴리스’로 다루기 위한 업그레이드 검증·배포·자동화 실전 가이드"
date: 2026-10-12 11:32:05 +0900
categories: ["Hardware", "NVIDIA Network Operator"]
tags: ["nvidia", "network-operator", "spectrum-x", "kubernetes", "sriov", "sosreport"]
render_with_liquid: false
---

## 버전 표기부터 정리: 26.10.0 문서, 26.1.0 릴리스, 26.10.0-beta 태그

이번 건은 이름부터 운영자가 헷갈리기 쉬운 구조입니다.

- NVIDIA 공식 PDF는 문서 제목이 **NVIDIA Network Operator v26.1.0**이고, Release Notes 테이블도 26.1.0 변경 사항을 적고 있습니다.[^1]
- 그런데 문서 URL 경로가 `kubernetes2610`이고, 커뮤니티 스타일 문서 사이트( `mellanox.github.io/network-operator-docs` )는 상단에 `v26.10.0 documentation` 같은 표기를 붙입니다.[^2]
- Spectrum‑X Quick Start에서는 Helm 차트 버전에 `--version 26.10.0-beta.3` 같은 태그가 예시로 등장합니다.[^2]

즉, 운영에서 결정을 내려야 하는 버전은 보통 다음 3가지를 분리해 보는 편이 안전합니다.

1) **Network Operator Helm chart 버전** (Helm install/upgrade에 박는 값)
2) **컨테이너 컴포넌트 태그** (예: `network-operator-v26.1.0`, DOCA driver tag 등)
3) **문서 사이트의 빌드 버전** (문서 경로/헤더의 26.10.0 같은 값)

이 글에서는 “Spectrum‑X GA 표기 + SOS report 스크립트 추가”라는 변화 자체를 업그레이드 이벤트로 다루는 방법을 중심으로 정리합니다. Spectrum‑X 쪽 구체적인 배포 패턴은 Quick Start에 적힌 Single‑Plane 워크플로우를 기준으로 설명하되, 그 워크플로우가 특정 릴리스(문서에는 Network Operator 26.7.0 기준이라고 명시)에서 정리됐다는 점을 함께 전제로 둡니다.[^2]

## 이번 릴리스를 ‘클러스터 네트워킹 릴리스’로 다뤄야 하는 이유

Release Notes에서 눈에 띄는 항목은 크게 두 가지입니다.

- Spectrum‑X Ethernet Networking Platform 지원이 Kubernetes에서 **[GA]**로 표기됐습니다.[^1]
- 운영 관점 도구로 SOS report 수집 스크립트가 추가됐습니다.[^1]

이 둘은 성격이 다릅니다.

Spectrum‑X는 “기능 하나 추가”가 아니라, 쿠버네티스 클러스터의 네트워크를 구성하는 기본 전제를 바꿉니다. 특히 AI 인프라에서 네트워크는 다음으로 직결됩니다.

- 성능: all-reduce / parameter sync가 느려지면 GPU는 바로 idle이 됩니다. 네트워크는 GPU 사용률을 만드는 하한선이 됩니다.
- 장애: SR-IOV/OVS/switchdev 계열은 (1) 노드 재부팅, (2) 커널 업데이트, (3) 펌웨어/driver 미스매치에서 장애가 자주 납니다.
- 보안: RDMA 디바이스가 namespace에 어떻게 노출되는지(격리 모델)부터가 보안/멀티테넌시 전제입니다.

그리고 SOS는 “문제 생기면 사람 붙어서 수집”에서 “장애 대응 프로세스에 수집이 내장”으로 바꾸는 장치입니다. SOS 스크립트는 클러스터 구성/로그/상태/진단 출력까지 한 번에 모아 아카이브로 만들도록 설계됐고, 이전 버전 Network Operator에도 동작하도록 backward compatible를 강조합니다.[^3]

내 경우 GPU driver 업그레이드를 쿠버네티스 릴리스 이벤트로 묶어서 운영해 왔는데(예: [NVIDIA R595 드라이버 업데이트를 쿠버네티스 릴리스로 다루기](https://daewooki.github.io/posts/k8s-gpu-driver-upgrade-r595-release/)), Network Operator/Spectrum‑X도 같은 급으로 묶는 편이 결과적으로 장애 비용이 낮았습니다. 네트워크는 특히 “조용히 성능만 떨어지는” 형태가 많아서, 배포/업그레이드 전후 검증 루틴이 없으면 몇 주 뒤에야 손으로 더듬게 됩니다.

## 업그레이드 전 점검: 드라이버/CRD/DaemonSet 스냅샷

Network Operator 업그레이드는 대개 아래 축이 함께 움직입니다.

- CRD: Operator가 관리하는 API 그룹이 늘거나, 스키마가 바뀌거나, v1alpha1/v1alpha2가 갈립니다.
- DaemonSet: 드라이버/에이전트/디바이스 플러그인/secondary network 컴포넌트가 노드 전역에 깔려 있고, 여기서 재시작이 곧 데이터패스 변경입니다.
- Host 변화: SR-IOV enablement, devlink param, switchdev, OVS bridge, udev rule 같은 것들은 “쿠버네티스 리소스 apply”가 결국 호스트 상태 변화를 유발합니다.

스냅샷을 남길 때 핵심은 “문제 생겼을 때 diff를 만들 수 있는 형태”입니다. 나는 다음을 최소 세트로 봅니다.

- Helm release 메타 (chart 버전/values)
- 설치된 CRD 목록 + 관심 CR instance YAML
- nvidia-network-operator namespace의 Deployment/DaemonSet 이미지 태그
- 노드 라벨 (특히 NFD 기반)

### 스냅샷 수집 스크립트

아래 스크립트는 bastion(운영자가 kubectl/helm을 실행하는 머신)에서 실행하는 전제입니다.

```bash
#!/usr/bin/env bash
set -euo pipefail

NS="nvidia-network-operator"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="netop-preflight-${TS}"

mkdir -p "${OUT}"

# 1) Helm 메타/values
helm -n "${NS}" list -a > "${OUT}/helm-list.txt" || true
helm -n "${NS}" status network-operator > "${OUT}/helm-status.txt" || true
helm -n "${NS}" get values network-operator -a > "${OUT}/helm-values.yaml" || true
helm -n "${NS}" get manifest network-operator > "${OUT}/helm-manifest.yaml" || true

# 2) CRD / API 리소스 목록
kubectl api-resources > "${OUT}/api-resources.txt"
kubectl get crd > "${OUT}/crd-all.txt"

# Network Operator/SR-IOV 관련 CRD는 이름이 길어서 grep으로 추가 추출
kubectl get crd | egrep -i '(mellanox\.com|nvidia\.com|sriovnetwork|multus|networkattachmentdefinition|nv-ipam)' \
  > "${OUT}/crd-filtered.txt" || true

# 3) 네임스페이스 리소스 스냅샷
kubectl -n "${NS}" get all -o wide > "${OUT}/ns-all.txt" || true
kubectl -n "${NS}" get ds,deploy,po -o wide > "${OUT}/workloads.txt" || true

# 4) 핵심 CR 인스턴스 덤프
kubectl -n "${NS}" get nicclusterpolicy -o yaml > "${OUT}/nicclusterpolicy.yaml" 2>/dev/null || true
kubectl -n "${NS}" get nicnodepolicy -o yaml > "${OUT}/nicnodepolicy.yaml" 2>/dev/null || true

# 5) 노드 라벨/상태
kubectl get nodes -o wide > "${OUT}/nodes.txt"
kubectl get nodes --show-labels > "${OUT}/nodes-labels.txt"

echo "[OK] wrote ${OUT}/"
```

예상 출력은 다음처럼 단순해야 합니다.

```text
[OK] wrote netop-preflight-20261012-091500/
```

이 스냅샷은 업그레이드 후 스냅샷과 diff를 떠서 “무슨 변화가 실제로 일어났는지”를 보는 용도입니다. 단순하지만 이 단계가 없으면, 장애 시점에 “원래 저 이미지 태그가 뭐였지?” 같은 질문부터 시작하게 됩니다.

### Host 선행 조건: Spectrum‑X를 염두에 둔다면 더 엄격하게

Spectrum‑X Quick Start에는 worker 노드에 두 가지 host 설정을 요구합니다.

- SR-IOV 관련 IOMMU/VF 설정은 플랫폼/펌웨어/커널 cmdline 레벨에서 선행되어야 하고, 재부팅이 필요합니다.[^2]
- RDMA subsystem을 namespace-exclusive 모드로 전환하기 위해 `ib_core netns_mode=0` 설정을 추가하고 재부팅하라고 명시합니다. 이 설정이 없으면 RDMA 디바이스가 Pod 단위로 격리되지 않고, 다른 Pod의 RDMA 디바이스가 보이는 문제가 생길 수 있다고 경고합니다.[^2]

여기서 중요한 건 “Operator 업그레이드 이벤트”와 “노드 재부팅 이벤트”를 분리하면 운영이 더 힘들어진다는 점입니다. 네트워크/드라이버 계열은 재부팅이 개입되는 순간 롤백 난이도가 급상승합니다. 그래서 나는 보통 다음처럼 릴리스 범위를 나눕니다.

- Phase A: Operator/CRD/DaemonSet 업그레이드 (재부팅 없는 범위)
- Phase B: 노드 재부팅이 필요한 host 설정 반영 (rack/노드 그룹 단위)

한 번에 같이 처리하면 좋지만, 실패했을 때 blast radius가 커지기 때문에 인프라 규모가 커질수록 분리하는 편이 낫습니다.

## 업그레이드 실행: Helm/CRD/롤링 전략

### Helm chart 설치/업그레이드의 기본 뼈대

Spectrum‑X Quick Start는 NVIDIA NGC Helm repo를 추가하고 설치하는 흐름을 사용합니다.[^2]

```bash
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
helm repo update

# 업그레이드라면 install 대신 upgrade
helm -n nvidia-network-operator upgrade --install network-operator nvidia/network-operator \
  --create-namespace \
  --version <TARGET_CHART_VERSION> \
  -f values.yaml \
  --wait
```

여기서 `<TARGET_CHART_VERSION>`은 조직 표준으로 “고정”해야 합니다. Quick Start에 `26.10.0-beta.3` 예시가 있다는 사실은 “문서 작성 시점에 베타 태그를 사용했다”는 의미이지, 프로덕션에서 베타를 써도 된다는 뜻이 아닙니다.[^2]

### CRD 업데이트를 업그레이드에서 분리할지 판단

Helm chart로 CRD를 배포하는 경우가 많은데, CRD 업데이트는 Kubernetes API 레벨에서 실패하면 롤백이 깔끔하지 않습니다. 특히 v1alpha1 → v1alpha2 같이 GroupVersion이 갈리면 더 위험합니다.

내 기준은 이렇습니다.

- CRD 변경이 없거나 단순 추가라면: Helm upgrade에 포함
- CRD 스키마가 바뀌거나, 버전이 갈리거나, admission webhook이 얽히면: CRD를 별도 apply로 분리하고 사전 diff/검증

Network Operator 쪽은 릴리스마다 CRD와 컴포넌트가 동시에 커지는 경향이 있어서(예: `NicNodePolicy` 같은 새 CRD 추가), 업그레이드 노트를 “네트워킹 릴리스 노트”로 따로 읽는 습관이 필요합니다.[^4]

### 업그레이드 중단/롤백 기준을 먼저 만든다

업그레이드 실행 자체보다 중요한 건 “언제 멈출지”입니다. 네트워킹은 상태가 반쯤 망가져도 클러스터가 살아 있는 것처럼 보일 때가 많습니다.

내가 보통 잡는 중단 기준은 세 가지입니다.

1) 노드 단위로 DS가 Ready로 복귀하지 않음 (드라이버/OVS 계열은 특히)
2) SR-IOV 리소스가 노드에서 사라짐 (Device Plugin 리소스가 0으로 떨어지는 상황)
3) east-west 테스트 트래픽(간단한 iperf가 아니라 RDMA 또는 VF 기반 트래픽)이 실패

이 기준이 없으면 업그레이드가 “언제 끝났는지”가 애매해지고, 애매하면 보통 사고가 납니다.

## 업그레이드 전후 검증 항목: 드라이버/CRD/DaemonSet

여기서는 “검증 항목”을 실제로 체크 가능한 형태로 쪼갭니다. Spectrum‑X까지 갈 생각이면 더 촘촘해야 합니다.

### 1) CRD 존재/버전/스키마: 최소한 이름이라도 확인

```bash
kubectl get crd | egrep -i '(mellanox\.com|configuration\.net\.nvidia\.com|nv-ipam\.nvidia\.com|spectrumx\.nvidia\.com|sriovnetwork)' \
  | sort
```

여기서 포인트는 “뭐가 생겼는지/사라졌는지”입니다.

- Spectrum‑X Quick Start는 `NicInterfaceNameTemplate`( `configuration.net.nvidia.com/v1alpha1` )를 사용해 rail 별 인터페이스 네이밍을 고정합니다.[^2]
- 26.1.0 PDF에도 `NicInterfaceNameTemplate`가 나오며, PCI 주소-rail 매핑과 네이밍 템플릿을 적고, udev rules 파일을 생성한다고 설명합니다.[^1]

CRD가 있는지 확인하지 않고 YAML을 apply하면, “apply는 됐는데 아무 일도 안 일어남” 같은 시간이 가장 많이 낭비됩니다.

### 2) DaemonSet 롤아웃: Ready 숫자만 보지 말고 이미지 태그를 본다

```bash
NS=nvidia-network-operator
kubectl -n ${NS} get ds -o wide
kubectl -n ${NS} get ds -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.numberReady}{"/"}{.status.desiredNumberScheduled}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  | column -t
```

네트워크 계열 DS는 “Ready가 찍히는데 성능/기능은 깨진” 상태가 가능합니다. 그래서 아래를 추가로 봅니다.

- driver DS (DOCA-OFED 등) pod 로그에서 커널 모듈 로딩/검증 실패가 없는지
- SR-IOV config daemon이 NIC 설정을 반복해서 뒤집는지(= flapping)

특히 Spectrum‑X Quick Start는 SR-IOV Network Operator의 Mellanox plugin을 끄지 않으면 동일 상태를 두 군데가 동시에 설정해서 flapping이 난다고 직접 경고합니다. `disablePlugins: [mellanox]`가 그 대응이고, 이것이 “배포 패턴”에서 매우 중요한 결정점입니다.[^2]

### 3) 드라이버/펌웨어: Operator 업그레이드가 곧 드라이버 이벤트인지 확인

26.1.0 PDF의 `NicClusterPolicy` 예시는 `ofedDriver`에 DOCA driver 이미지를 쓰고, tag는 `doca3.3.0-26.01-1.0.0.0-0`처럼 별도 버전 체계를 씁니다.[^1]

즉, Network Operator 업그레이드가 곧바로 driver 컨테이너 업그레이드로 이어질 수 있고, 이때 커널 호환성 이슈가 발생합니다. 실제로 26.1.1 PDF의 known limitations에는 DOCA driver 컨테이너가 검증된 커널 범위(예: 6.8.0-100까지) 언급과 “그 이상은 보장되지 않는다”는 취지의 문장이 있습니다.[^5]

GPU driver 때와 동일하게, 네트워크 driver도 “클러스터 릴리스 이벤트”로 묶어 운영하는 게 결국 싸게 먹힙니다. 업그레이드 압박이 커졌다는 얘기는 이미 여러 번 했지만[^6], 네트워크 쪽은 그 압박이 성능/장애로 바로 튀어나오는 편입니다.

## Spectrum‑X 배포 패턴: Single‑Plane을 기준으로 쪼개서 이해하기

Spectrum‑X Quick Start의 Single‑Plane 워크플로우는 구성 요소를 잘 드러내서, 운영자가 “어디서 문제가 났는지”를 계층적으로 찾기 좋습니다.[^2]

이 패턴의 핵심은 한 줄로 요약하면 이렇습니다.

- rail 단위로 PF/VF를 만들고
- rail 단위로 IPAM 풀을 주고
- rail 단위로 Pod에 secondary network를 붙이고
- 그 rail을 schedulable resource로 노출해서 워크로드가 “rail 0, rail 1 각각 1개” 같은 식으로 요청하게 만든다

Quick Start에는 Single‑Plane이 “one PF per rail, one CIDRPool per rail, one network per rail”이라고 명시합니다.[^2]

### (1) SR-IOV Network Operator의 역할을 줄이고, NIC Configuration Operator로 몰아준다

Quick Start의 values.yaml 예시는 SR-IOV Network Operator를 켜되, Mellanox plugin을 disable해서 NIC 상태(펌웨어/NV config/SR-IOV enablement)를 NIC Configuration Operator가 주도하게 합니다.[^2]

이 설계의 운영적 의미는 큽니다.

- 한쪽에서 `devlink` param을 바꾸고, 다른 쪽에서 다시 되돌리는 형태의 미세한 경쟁 상태를 줄입니다.
- NIC 설정의 source of truth가 `NicConfigurationTemplate`/`NicInterfaceNameTemplate` 같은 CRD로 모입니다.

### (2) NicInterfaceNameTemplate로 네이밍을 고정한다

Spectrum‑X는 rail 단위로 디바이스를 다루는데, 리눅스의 기본 네이밍(enpXsYfZ…)은 장비/BIOS/펌웨어/커널에 따라 흔들릴 수 있습니다.

- 26.1.0 PDF는 `NicInterfaceNameTemplate`가 템플릿 기반으로 udev rules를 생성하고, `/etc/udev/rules.d/` 아래에 rules 파일을 쓴다고 설명합니다.[^1]
- Quick Start도 rail별로 `net_rail0`, `rdma_rail0` 같은 네이밍을 예시로 사용합니다.[^2]

이 네이밍이 고정되면, 이후 검증/모니터링이 현실적으로 가능해집니다. 예를 들어 “rail0 VF에서 PFC drop이 늘었다” 같은 이야기가 로그/메트릭에서 숫자로 묶이기 시작합니다.

### (3) NicConfigurationTemplate에서 Spectrum‑X 튜닝을 켠다

NIC Configuration Operator의 CRD 스키마 문서에는 `spectrumXOptimized`가 있고, linkType이 Ethernet이고 numVfs가 1일 때 동작한다는 제약이 문서에 있습니다.[^7]

이 제약은 배포 설계에 영향을 줍니다.

- 무작정 VF를 여러 개 만들고 Pod에 여러 개 붙여서 throughput을 올리려는 설계는 Spectrum‑X 최적화와 충돌할 수 있습니다.
- “rail 별로 1 VF” 같은 방식이 먼저 정리되는 이유가 여기 있습니다.

### (4) CIDRPool + rail 리소스로 Pod 스케줄링까지 연결한다

Quick Start는 rail마다 `CIDRPool`을 만들고(NV-IPAM), `SpectrumXRailPoolConfig`로 rail 리소스를 노출한 뒤, Pod에서 `resources.requests`로 `nvidia.com/rail0: 1` 같은 형태로 rail을 요청합니다.[^2]

이건 단순히 네트워크를 “붙이는” 문제가 아니라, 워크로드 placement 문제로 올라옵니다. GPU/AI 인프라에서는 topology-aware placement가 성능의 절반이고, 네트워크 rail도 그 topology의 일부입니다. 나는 GPU 오토스케일링을 다룰 때도 같은 결론에 도달했는데[^8], 네트워크까지 들어오면 결국 리소스 모델링이 운영 난이도를 좌우합니다.

## Spectrum‑X에서 자주 걸리는 지점: SR‑IOV/OVS/devlink

Release Notes에 같이 들어 있는 항목들이 힌트입니다.

- SR-IOV Network Operator에서 `esw_multiport`(NIC multiport firmware parameter) 를 devlinkParams로 설정할 수 있게 됐다고 적혀 있습니다.[^9]
- OVS bridge grouping 설정을 지원해서 NIC PF들을 단일 OVS bridge로 묶을 수 있게 됐다고도 나옵니다.[^9]

이건 “스펙트럼‑X가 결국 switchdev + OVS + devlink를 진하게 쓴다”는 현실을 반영합니다.

### devlink/esw_multiport는 ‘설정 방식’ 자체가 장애 포인트다

Linux kernel 문서에서 devlink param은 runtime/driverinit/permanent처럼 적용 모드가 있고, 어떤 값은 reload나 하드 리셋이 필요합니다.[^10]

또 mlx5 문서에는 `esw_multiport`가 multiport e-switch를 제어하는 파라미터라고 설명합니다.[^11]

운영 관점에서 중요한 건 이겁니다.

- “값을 set했다”와 “값이 실제 데이터패스에 적용됐다”가 다를 수 있습니다.
- 적용 시점이 드라이버 로드 전후/스위치dev 전후에 걸리면, 노드 재부팅/드라이버 재로딩이 개입될 수 있습니다.

Spectrum‑X 구성요소 문서(Architecture/Components 쪽)는 `esw_multiport=true`가 Hardware Multiplane에서 rail의 planes를 하나의 e-switch로 묶는 용도라고 설명합니다. 그리고 `manageSoftwareBridges` feature gate가 있어야 SR-IOV Network Operator가 OVS bridge를 만들어 준다고도 적습니다.[^12]

즉, Spectrum‑X 배포에서 devlink/OVS는 “있으면 좋은 최적화”가 아니라, 모드에 따라서는 동작 조건입니다.

### OVS-CNI / VF representor: 노드 재부팅이 들어가면 자주 깨진다

26.1.1 PDF의 known limitation에는 “노드 재부팅 후 stale VF representor가 삭제되지 않는 제한”과 workaround(직접 stale representor를 삭제)가 언급됩니다.[^5]

이 유형의 문제는 운영에서 두 가지를 강제합니다.

- 재부팅이 들어가는 변경은, 변경 자체뿐 아니라 “재부팅 후 정리 작업”까지 자동화하거나 런북에 넣어야 합니다.
- 업그레이드 후 검증 항목에 “OVS bridge/port가 깨끗한지”가 들어가야 합니다.

## 업그레이드 후 검증: Spectrum‑X Single‑Plane 최소 검증 루틴

나는 검증을 “계층별로” 쪼갭니다. 아래는 Quick Start 흐름을 그대로 검증 포인트로 바꾼 것입니다.

### Layer 0: 노드 준비 상태

- `ib_core netns_mode=0` 적용 여부(재부팅 포함)
- SR-IOV 가능 라벨이 제대로 붙었는지

Quick Start는 `feature.node.kubernetes.io/network-sriov.capable: "true"` 라벨을 nodeSelector로 쓰는 예시를 넣습니다.[^2]

```bash
kubectl get nodes -L feature.node.kubernetes.io/network-sriov.capable \
  | column -t
```

### Layer 1: Operator 컴포넌트 readiness

```bash
kubectl -n nvidia-network-operator get pods -o wide
kubectl -n nvidia-network-operator get ds,deploy -o wide
```

여기서는 단순 Ready가 아니라 restart loop 여부, 특정 노드에서만 실패하는지(펌웨어/PCI 토폴로지/BIOS 차이)까지 봅니다.

### Layer 2: CRD 기반 구성 리소스 상태

`NicInterfaceNameTemplate`, `NicConfigurationTemplate`, `CIDRPool`, `SpectrumXRailPoolConfig` 같은 리소스가 “생성됐다”가 아니라 “Status가 정상으로 수렴했는지”가 중요합니다. Quick Start는 이 CR들을 apply하는 흐름으로 구성을 진행합니다.[^2]

```bash
kubectl -n nvidia-network-operator get nicinterfacenametemplate
kubectl -n nvidia-network-operator get nicconfigurationtemplate
kubectl -n nvidia-network-operator get cidrpool
kubectl -n nvidia-network-operator get spectrumxrailpoolconfig
```

(리소스 이름/그룹은 설치 릴리스에 따라 달라질 수 있어서, `kubectl api-resources | grep -i spectrum` 같은 탐색을 먼저 하는 편이 안전합니다.)

### Layer 3: 워크로드에서 rail 리소스가 실제로 할당되는지

Quick Start의 테스트 Pod는 secondary network annotation으로 `rail0,rail1` 같은 네트워크를 붙이고, resource request로 rail 리소스를 요청합니다.[^2]

검증 포인트는 두 가지입니다.

- Pod가 뜨는가 (스케줄링 + 리소스 할당)
- Pod 안에서 RDMA 디바이스/네트워크 디바이스가 rail 단위로 분리돼 보이는가

Quick Start는 예시로 `rdma link`를 실행합니다.[^2]

```bash
kubectl -n default exec -it spectrum-x-test -- rdma link
```

예상 출력은 환경마다 다르지만, 최소한 rail 기반 네이밍을 했다면 `rdma_rail0`, `rdma_rail1` 같은 식별자가 보이고 state가 DOWN이 아닌지까지 확인하는 편이 낫습니다.

## SOS report를 운영 도구로 만들기: 수집·보관·자동 실행

26.1.0 릴리스 노트에 SOS report 스크립트 추가가 명시돼 있고, 문서에는 설치/요구사항/옵션/무엇을 수집하는지/보안 고려사항까지 정리돼 있습니다.[^1]

핵심 특성은 세 가지입니다.

- `kubectl` plugin 형태(`kubectl netop-sosreport`)로 쓰는 방식을 권장합니다.[^3]
- HTML report 생성을 위해 `generate-report.py`와 `report-template.html`이 필요하며, 없으면 GitHub에서 다운로드를 시도하지만 다운로드 실패해도 수집 자체는 진행된다고 합니다.[^13]
- 스크립트는 이전 버전 Network Operator에서도 동작하도록 설계됐고, 없는 리소스는 graceful하게 skip한다고 설명합니다.[^3]

여기서 운영자가 결정해야 하는 건 “실행 위치”입니다.

### 1) 사람 노트북에서 수동 실행은 운영 도구가 아니다

장애 때마다 누가 노트북에서 실행하면, 결국 다음이 불가능해집니다.

- 장애 시점의 동일한 수집 품질 보장
- 접근권한 통제(누가 어떤 클러스터에서 어떤 데이터를 뽑았는지)
- 보관/검색/감사

그래서 나는 SOS를 다음 중 하나로 고정합니다.

- Bastion/ops VM에서 실행 + 결과를 오브젝트 스토리지에 보관
- CI runner(예: Jenkins agent)에서 실행 + 티켓/사고번호로 아카이브

### 2) 가장 단순한 자동화: “수집 + 업로드”만 Cron으로 돌린다

문서 기준으로, 스크립트는 결과물을 tar.gz와 sha256로 만듭니다.[^14]

운영에서 중요한 건 이 두 파일을 “사고 식별자”와 묶어 보관하는 것입니다. 예를 들어:

- `sosreport/<cluster>/<yyyy-mm-dd>/<incident-id>/network-operator-sosreport-<timestamp>.tar.gz`
- `...tar.gz.sha256`

수동 실행을 기준으로 한 예시는 문서에 있습니다.

```bash
./network-operator-sosreport.sh --verbose

tar -xzf network-operator-sosreport-*.tar.gz
cat network-operator-sosreport-*/diagnostic-summary.txt
```

이 흐름 자체가 런북에 들어가야 하고, 사고 때는 거의 자동으로 실행되어야 합니다.[^15]

### 3) Kubernetes Launch Kit을 쓰는 경우: sosreport가 설치물에 포함된다

Kubernetes Launch Kit 문서에는 릴리스 아티팩트에 Network Operator sosreport helper가 포함되고, 설치 경로에 `kubectl-netop_sosreport`가 놓인다고 설명합니다.[^16]

이미 Launch Kit을 쓰고 있다면, sosreport만 따로 배포하는 것보다 “같은 배포 체계 안에서” 가져가는 편이 훨씬 깔끔합니다.

### 4) 자동화에서의 보안 경계: 수집물은 기본적으로 민감하다

SOS 문서에는 보안 고려사항으로 “Secret은 데이터가 아니라 메타데이터만 수집한다”는 취지의 내용이 있고, 로그에는 IP/호스트네임 같은 환경 정보가 포함될 수 있으니 공유 전 검토하라고 적습니다.[^15]

그래서 나는 다음을 정책으로 둡니다.

- sosreport 아카이브는 기본 private 버킷/접근통제
- 티켓에 붙일 때는 그대로 첨부가 아니라 (1) 내부 저장소 링크 + (2) 접근권한 부여로 처리
- 외부 벤더에 공유해야 하면, 최소한 `operator/components/*/pods/*.log`와 `diagnostic-summary.txt`를 우선 검토

이걸 안 하면 sosreport 자동화는 편의 기능이 아니라 데이터 유출 경로가 됩니다.

## 반론과 회의론: “Operator 업그레이드인데 이렇게까지 해야 하나”

이 반론이 나오는 이유는 이해합니다. GPU 쪽도 Operator가 많고, 네트워크까지 릴리스로 묶으면 릴리스 이벤트가 너무 잦아집니다.

그래도 나는 네트워크 쪽은 특히 다음 이유로 “과하다 싶을 만큼” 보수적으로 갑니다.

- 네트워크 장애는 GPU 장애보다 탐지가 늦습니다. GPU는 바로 에러가 나지만, 네트워크는 성능 저하가 먼저 오고 SLO가 서서히 죽습니다.
- Spectrum‑X 계열은 host 레벨 변화(devlink/OVS/switchdev)가 많고, 이는 롤백이 단순한 kubectl apply 롤백이 아닙니다.
- Release Notes가 “기능 추가”가 아니라 “플랫폼 GA”라고 말하는 순간, 그건 기능 릴리스가 아니라 운영 모델의 변화입니다.[^1]

## 내가 보는 도입/업그레이드 판단 기준

최종적으로는 조직의 장애 모델과 성능 목표에 따라 선택이 갈립니다. 나는 아래를 기준으로 결정합니다.

1) 워크로드가 분산 학습/동기 통신 비중이 크면: 네트워크는 곧 GPU 효율이라서 Spectrum‑X 같은 형태의 표준화가 이득이 큽니다.
2) 클러스터 규모가 커지고 재현이 어려워지면: SOS 같은 수집 자동화의 ROI가 급격히 올라갑니다.
3) 커널/드라이버/펌웨어 업데이트 주기가 빠르면: Network Operator 업그레이드를 릴리스 이벤트로 승격시키는 순간부터 사고 비용이 줄어듭니다.

결국 결론은 단순합니다. Spectrum‑X GA와 SOS 도입은 “네트워크 기능 하나 추가”가 아니라, AI 클러스터에서 성능·장애·보안의 기본 비용을 바꾸는 업그레이드 이벤트로 다루는 편이 맞습니다.

## 참고 자료

- [NVIDIA Network Operator v26.1.0 PDF 문서](https://docs.nvidia.com/networking/display/kubernetes2610/nvidia-network-operator-v26-1-0.pdf)
- [NVIDIA Network Operator Release Notes (HTML)](https://docs.nvidia.com/networking/display/kubernetes2612/release-notes.html)
- [Spectrum-X Kubernetes Quick Start](https://mellanox.github.io/network-operator-docs/spectrum-x/quick-start.html)
- [Network Operator SOS-Report Collection Script 문서](https://docs.nvidia.com/networking/display/kubernetes2610/troubleshooting/sosreport.html)
- [NVIDIA Network Operator GitHub 저장소](https://github.com/Mellanox/network-operator)
- [NIC Configuration Operator CRD API reference](https://docs.nvidia.com/networking/display/kubernetes2670/nic-conf-operator/crds.html)
- [Linux kernel 문서: Devlink Params](https://cdn.kernel.org/doc/html/latest/networking/devlink/devlink-params.html)
- [Linux kernel 문서: mlx5 devlink support (esw_multiport)](https://cdn.kernel.org/doc/html/latest/networking/devlink/mlx5.html)
- [NVIDIA DOCA XPlane Service Guide](https://networking-docs.nvidia.com/doca/archive/3-4-0/doca-xplane-service-guide)
- [Kubernetes Launch Kit 설치 문서 (sosreport helper 포함)](https://nvidia.github.io/k8s-launch-kit/user/installation/)
- [NVIDIA R595 드라이버 업데이트를 쿠버네티스 릴리스로 다루기](https://daewooki.github.io/posts/k8s-gpu-driver-upgrade-r595-release/)

[^1]: <https://docs.nvidia.com/networking/display/kubernetes2610/nvidia-network-operator-v26-1-0.pdf>
[^2]: <https://mellanox.github.io/network-operator-docs/spectrum-x/quick-start.html>
[^3]: <https://docs.nvidia.com/networking/display/kubernetes2610/troubleshooting/sosreport.html>
[^4]: <https://mellanox.github.io/network-operator-docs/release-notes.html>
[^5]: <https://docs.nvidia.com/networking/display/kubernetes2611/nvidia-network-operator-v26-1-1.pdf>
[^6]: <https://daewooki.github.io/posts/2025-12-kubernetesdocker-1/>
[^7]: <https://docs.nvidia.com/networking/display/kubernetes2640/nic-conf-operator/crds.html>
[^8]: <https://daewooki.github.io/posts/gpu-llm-kubernetes-2026-6-2/>
[^9]: <https://docs.nvidia.com/networking/display/kubernetes2612/release-notes.html>
[^10]: <https://cdn.kernel.org/doc/html/latest/networking/devlink/devlink-params.html>
[^11]: <https://cdn.kernel.org/doc/html/latest/networking/devlink/mlx5.html>
[^12]: <https://docs.nvidia.com/networking/display/kubernetes2670/spectrum-x/components.html>
[^13]: <https://docs.nvidia.com/networking/display/kubernetes2611/troubleshooting/sosreport.html>
[^14]: <https://mellanox.github.io/network-operator-docs/troubleshooting/sosreport.html>
[^15]: <https://docs.nvidia.com/networking/display/kubernetes2670/troubleshooting/sosreport.html>
[^16]: <https://nvidia.github.io/k8s-launch-kit/user/installation/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
