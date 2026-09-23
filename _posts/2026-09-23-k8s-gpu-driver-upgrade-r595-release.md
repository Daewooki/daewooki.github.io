---
title: "NVIDIA R595 드라이버 업데이트를 쿠버네티스 릴리스로 다루기"
description: "R595 595.91.07 릴리스 노트 기반으로 커널·드라이버·런타임 매트릭스, MIG/MPS·DCGM 호환, 롤링 업데이트 체크리스트를 정리합니다."
date: 2026-09-23 12:50:55 +0900
categories: ["Hardware", "NVIDIA GPU Driver"]
tags: ["kubernetes", "nvidia", "gpu-driver", "gpu-operator", "dcgm", "mig"]
render_with_liquid: false
---

## 595.91.07을 ‘패키지 업데이트’가 아니라 ‘릴리스’로 봐야 하는 이유

2026-09-21에 업데이트된 NVIDIA Data Center GPU Driver R595 릴리스 노트(595.91.07 Linux / 596.86 Windows)는 내용 자체도 크지만, 운영 관점에서 더 큰 변화는 “업데이트를 걸어야 하는 전제조건”이 문서에 명확히 박혀 있다는 점입니다. 이 전제조건들은 보통 커널 stable 업데이트(노드 재부팅)나 클러스터 롤링 작업과 같은 주간 작업과 겹칠 때 장애 확률을 올립니다.

우선 기준점을 박아두면, 이 문서가 말하는 드라이버 릴리스 날짜는 2026-08-03이고, 릴리스 노트 문서 자체의 마지막 업데이트는 2026-09-21입니다.[^1]

내가 이번 주에 “설계/검증”을 먼저 하자는 쪽으로 기울게 만드는 항목은 아래입니다.

- **DCGM 최소 버전 하한이 고정**되어 있습니다. R595 595.91.07은 DCGM 4.3.x 이상만 호환이고, 그 이전 버전은 호환되지 않는다고 못 박습니다. 이건 모니터링과 autoscaling 파이프라인이 DCGM/NVML에 걸려 있는 클러스터에서는 사실상 “드라이버와 DCGM을 한 덩어리로 롤링”하라는 의미입니다.[^1]
- Hopper 특정 리비전에서 **VBIOS 게이트**가 있습니다. “Hopper GPUs subrevision = 3”이면서 VBIOS가 96.00.68.00.xx 미만이면 이 드라이버는 초기화에 실패할 수 있다고 되어 있습니다. 이건 노드 재부팅 후 `nvidia.ko` 로딩 단계에서 터질 수 있는 종류라서, 실패하면 해당 노드는 GPU capacity가 통째로 빠집니다.[^1]
- Blackwell에서 cuTensorMapEncode 계열 사용 시 **스포라딕 MMU fault(Xid 13)/illegal access** 가능성과 워크어라운드가 릴리스 노트에 직접 제시되어 있습니다. 드라이버 업데이트만으로 해결되는 종류가 아니라, 앱/라이브러리 조합에 따라 “특정 텐서 크기/레이아웃에서만” 터질 수 있다는 점이 더 위험합니다.[^1]
- GB200에 대해 CDMM(Coherent Driver-Based Memory Management)를 도입했고, Kubernetes 클러스터에서 **memory over-reporting을 해결하기 위해 CDMM 활성화를 권장**합니다. 한편 CDMM은 `modprobe.d` 옵션 추가 후 드라이버 reload가 필요하므로, 노드 롤링 업데이트 계획 안에 포함되어야 합니다.[^1]
- RHEL 10 특정 커널(6.12.0-55.29.1.el10_0.x86_64)에서 `doca-ofed`가 `ib_umad.ko`를 포함하지 않아 Fabric Manager가 실패할 수 있다고 나옵니다. NVSwitch 계열(HGX 등)에서는 Fabric Manager 실패가 곧 노드 가용성 문제로 이어질 수 있습니다.[^1]

즉, 이번 드라이버는 “업데이트 해도 되나?” 수준이 아니라 “업데이트할 때 무엇을 같이 업데이트해야 하나, 무엇을 먼저 점검해야 하나, 업데이트 중 워크로드를 어떻게 다룰 건가”가 릴리스 엔지니어링의 형태로 정리돼야 합니다.

---

## 커널/드라이버/컨테이너 런타임 매트릭스: 문서 기반으로 ‘합의된 지원 조합’을 만든다

GPU 노드에서 드라이버 업그레이드가 어려운 이유는, 장애 원인이 드라이버 하나로 수렴하지 않기 때문입니다.

- 커널 stable 업데이트는 “재부팅”을 강제합니다.
- 드라이버 업데이트는 커널 모듈과 user-space 라이브러리(NVML 등)의 조합 문제로 번집니다.
- 컨테이너 런타임은 결국 host driver에 의존합니다. CUDA toolkit이 컨테이너 안에 들어있어도, host driver가 CUDA 요구사항을 못 맞추면 컨테이너는 시작 단계에서 실패할 수 있습니다.[^2]

이 매트릭스는 대단한 자동화가 아니라, “우리 조직이 운영하는 GPU 노드 풀에서 허용하는 조합”을 명시하는 문서입니다. 이 문서를 만들면, 드라이버 업데이트가 ‘작업’에서 ‘릴리스’가 됩니다.

### 1) R595가 말하는 OS 지원 범위와, 커널 버전의 근거를 분리한다

R595 595.91.07 릴리스 노트는 지원 Linux 배포판을 표로 제공하면서도, **커널 버전의 완전한 목록은 CUDA Linux System Requirements 문서를 보라**고 안내합니다.[^1]

여기서 운영자가 해야 할 일은 단순합니다.

- 릴리스 노트 표: “지원 배포판의 큰 범위”를 팀의 기준으로 삼습니다. 예를 들면 Ubuntu 24.04 LTS, Ubuntu 22.04 LTS, RHEL 9.y, RHEL 10.x 등.[^3]
- CUDA Installation Guide(시스템 요구사항 표): “검증된 OS 버전/커널 버전”을 매트릭스의 근거로 삼습니다.

CUDA 13.4 Update 1 기준으로, 예를 들어 Ubuntu 24.04.4 LTS는 x86_64에서 커널 6.17.0-19로 검증되어 있고, RHEL 9.8은 5.14.0-687.15로 표기돼 있습니다.[^4]

이 정보를 왜 쓰냐면, 실제 장애의 상당수가 “드라이버가 OS를 지원하느냐”가 아니라 “우리 노드가 올라간 커널/커널 플래버가 이 조합에서 충분히 검증됐느냐”에 걸리기 때문입니다.

### 2) 컨테이너 런타임 호환성은 ‘CUDA 컨테이너’가 아니라 ‘host driver 하한’으로 표현한다

NVIDIA Container Toolkit 문서와 runtime 문서가 반복해서 말하는 핵심은 다음입니다.

- CUDA 컨테이너를 실행하려면 **host에 NVIDIA driver가 필요**하고, host에 CUDA toolkit이 설치돼 있을 필요는 없습니다.[^5]
- driver는 대체로 backward-compatible지만, **CUDA 버전이 올라가면 최소 driver 버전 하한이 생깁니다.**[^6]
- driver가 부족하면 컨테이너는 시작되지 않습니다.[^2]

그래서 매트릭스는 “컨테이너 이미지 태그”가 아니라, 서비스가 요구하는 CUDA 최소 버전(또는 프레임워크가 번들한 CUDA)과 그에 대한 driver 하한으로 적는 게 낫습니다. CUDA minor version compatibility 표는 이런 하한을 정리해 둡니다.[^7]

### 3) 매트릭스 예시(문서 기반 템플릿)

아래는 내가 운영 문서로 만들 때 쓰는 형태입니다. 값 자체는 클러스터별로 달라지므로 “컬럼이 무엇이어야 하는가”에 집중합니다.

| Node Pool | Distro | Kernel(정책) | Driver Branch | Driver Version | Container Runtime | Container Toolkit | DCGM | MIG | 비고 |
|---|---|---|---|---|---|---|---|---|---|
| gpu-infer-a | Ubuntu 24.04 LTS | 6.17 계열(검증 표 기반) | R595 | 595.91.07 | containerd | nvidia-container-toolkit | >= 4.3.x | mixed | 드라이버/커널 동시 롤링 |
| gpu-train-b | RHEL 9.8 | 5.14.0-687 계열 | R595 | 595.91.07 | containerd | nvidia-container-toolkit | >= 4.3.x | single | Fabric Manager 사용 여부 명시 |

커널 칸에 “6.17 계열”처럼 쓰는 이유는, 커널 stable 업데이트가 계속 일어나기 때문입니다. CUDA 문서의 표는 “validated OS versions / kernel” 형태로 제공되므로, 이걸 커널 정책의 기준으로 삼습니다.[^4]

### 4) 매트릭스 검증을 자동화하는 최소 스크립트

여기서부터는 “릴리스 엔지니어링”의 냄새가 나야 합니다. 릴리스 후보(드라이버/커널 조합)를 만들면, 각 노드에서 동일한 검증을 반복하게 만들어야 합니다.

아래 스크립트는 GPU 노드에서 실행해 현재 상태를 수집하고, 컨테이너 런타임이 “드라이버 하한 미달로 기동 실패”하는 상황을 빠르게 잡는 데 초점을 둡니다(컨테이너가 driver 부족이면 시작 자체가 실패할 수 있다는 점을 runtime 문서가 명시합니다).[^2]

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "== host =="
date -Is
uname -a

echo
echo "== driver =="
command -v nvidia-smi >/dev/null
nvidia-smi --query-gpu=name,uuid,driver_version --format=csv,noheader

echo
echo "== runtime =="
containerd --version || true
ctr version || true

echo
echo "== nvidia container stack =="
# nvidia-ctk는 환경에 따라 없을 수 있으니 optional
nvidia-ctk --version || true

echo
echo "== smoke test (CUDA container) =="
# 실제로는 조직 표준 이미지(예: inference base image)로 바꾸는 게 맞습니다.
# driver가 부족하면 런타임 단계에서 컨테이너가 실패할 수 있습니다.
# (nvidia-container-runtime 문서의 설명)
#
# docker가 없다면 nerdctl로 치환합니다.
if command -v nerdctl >/dev/null; then
  nerdctl run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu24.04 nvidia-smi
else
  echo "nerdctl not found; skip"
fi
```

예상 출력 예시는 아래 정도가 나옵니다.

```text
== driver ==
NVIDIA H100 80GB HBM3, GPU-..., 595.91.07

== smoke test (CUDA container) ==
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 595.91.07   Driver Version: 595.91.07   CUDA Version: 13.x       |
+-----------------------------------------------------------------------------+
```

여기서 중요한 건 nvidia-smi 출력이 아니라, “컨테이너가 아예 안 뜨는 경우”를 릴리스 후보 단계에서 잡아내는 것입니다.

---

## MIG/MPS·DCGM/모니터링 호환성: 드라이버 업그레이드는 ‘관측 가능성’을 같이 무너뜨린다

GPU 노드에서 드라이버를 바꾸는 순간, 단순히 CUDA 커널이 도는지 여부가 끝이 아닙니다.

- MIG를 쓰면 장치 단위가 바뀝니다.
- MPS나 time-slicing을 쓰면 “컨테이너 단위의 책임소재”가 흐려집니다.
- DCGM은 모니터링/스케일링의 데이터 소스가 될 수 있고, 버전 호환성 제약이 강합니다.

예전에 GPU autoscaling을 DCGM 기반으로 엮는 설계를 다룬 글들이 있는데, 그 글들은 “지표 설계/스케일링 설계”가 중심이었습니다. 이번 글에서는 그 내용을 반복하지 않고, 드라이버 업데이트 시점에 깨지기 쉬운 경계만 다룹니다.

- [Kubernetes에서 LLM 서빙을 GPU 기준으로 오토스케일링하기](https://daewooki.github.io/posts/kubernetes-llm-gpu-kservevllm-keda-dcgm--1/)
- [GPU 오토스케일링 2026: HPA/KEDA/DCGM/DRA/MIG 실전 조합](https://daewooki.github.io/posts/gpu-2026-kubernetes-llm-gpu-hpakedadcgmd-1/)

### 1) R595 595.91.07은 DCGM 4.3.x 미만을 ‘비호환’으로 본다

릴리스 노트에 “이 드라이버는 DCGM 4.3.x 이상하고만 호환된다”고 명시돼 있습니다.[^1]

이 문장이 의미하는 운영 정책은 다음 중 하나로 수렴합니다.

- (정공법) 드라이버 롤링과 동시에 DCGM(및 exporter)을 올립니다.
- (리스크 수용) DCGM을 먼저 올리고(호환 범위 내), 드라이버를 뒤따라 올립니다.

둘 다 가능하지만, “누가 먼저 올라가도 되는가”는 문서가 답을 줍니다. 드라이버는 DCGM 하한을 요구합니다. 즉, 드라이버를 먼저 올렸다가 DCGM이 낮으면 관측이 끊깁니다.

DCGM 문서도 패키지/바이너리가 특정 CUDA 타깃에 맞춰 제공될 수 있음을 설명합니다(패키지 이름에 `-cuda*` suffix로 타깃 user-mode driver major를 표시). 이건 드라이버/쿠다 조합을 관리하는 쪽에서는 생각보다 중요한 힌트입니다.[^8]

### 2) MIG 변경은 “GPU 파티셔닝 변경 작업”이지 “label 변경”이 아니다

GPU Operator 문서는 MIG Manager가 하는 일을 꽤 적나라하게 말합니다.

- MIG를 켜려면 설치 시점에 MIG strategy를 선택해야 하고, MIG Manager가 노드에서 MIG 구성을 관리합니다.[^9]
- MIG Manager는 `nvidia.com/mig.config` label 변화를 감지하면, **device plugin / GPU feature discovery / DCGM exporter를 포함한 GPU 관련 pod를 먼저 멈춘 뒤** 재구성을 적용하고 다시 올립니다.[^9]
- 환경에 따라(특히 CSP) MIG mode/geometry 변경을 위해 노드 reboot이 필요할 수 있고, 문서도 cordon을 언급합니다.[^9]

여기서 드라이버 업데이트와 MIG를 같이 굴리면 어떤 일이 생기냐면, “드라이버 업데이트 때문에 GPU pod가 내려가는데, MIG 재구성 때문에 또 내려간다”가 됩니다. 둘을 동시에 하면 원인 분리가 거의 불가능합니다.

운영적으로는 둘 중 하나로 정리하는 편이 낫습니다.

- 드라이버 업데이트 윈도우에는 MIG geometry를 고정합니다.
- MIG 변경 윈도우에는 드라이버를 고정합니다.

### 3) MPS는 성능/격리 모델뿐 아니라 ‘모니터링 모델’을 바꾼다

NVIDIA MPS 문서가 직접 말하는 핵심은 이겁니다.

- MPS는 여러 CUDA 프로세스/앱의 cooperative 실행을 위한 런타임 서비스이며, `nvidia-cuda-mps-server`가 GPU 스케줄링 리소스를 소유합니다.[^10]
- 그리고 모니터링/어카운팅 관점에서, **MPS client의 동작이 MPS server 프로세스에 귀속될 수 있다**고 명시합니다(`nvidia-smi`, NVML 등).[^11]

즉, MPS를 켜는 순간, “컨테이너별 GPU 사용량”을 깔끔하게 뽑아내는 방식은 약해집니다. 그럼에도 MPS를 쓰는 이유는 워크로드 특성(동시성/효율) 때문이지만, 적어도 드라이버 업데이트 윈도우에는 다음을 같이 체크해야 합니다.

- exporter/agent가 MPS 상황에서 어떤 메트릭을 어떤 차원으로 내보내는가
- autoscaler가 그 메트릭을 신뢰해도 되는가

또 한 가지 운영상 중요한 제약이 있습니다. Kubernetes DRA 기반의 NVIDIA GPU 공유 가이드에서는, MPS가 GPU compute mode를 `EXCLUSIVE_PROCESS`로 바꾸고 time-slicing은 `DEFAULT`를 요구하기 때문에 **MPS와 time-slicing은 같은 physical GPU에서 동시에 활성화될 수 없다**고 말합니다.[^12]

이 제약은 단순 기능 제한이 아니라, 드라이버 업데이트 시에 “GPU 공유 전략이 바뀌면서 스케줄링이 바뀌고, 워크로드 배치가 흔들리는” 케이스로 이어질 수 있습니다.

### 4) time-slicing은 관측 가능성에 비용을 청구한다

NVIDIA k8s device plugin은 time-slicing과 MPS를 모두 GPU sharing 메커니즘으로 지원하며, MPS는 daemon이 메모리/compute 제한을 관리하는 방식이라는 설명을 포함합니다.[^13]

그리고 GPU Operator 문서(공유 비교 섹션)는 time-slicing을 켰을 때 DCGM exporter가 컨테이너에 메트릭을 연관 짓는 데 제한이 있음을 명시합니다.[^14]

이 조합에서 드라이버 업데이트를 하면, “드라이버 업데이트 → DCGM exporter 재기동/업데이트 → 메트릭 차원 변화”까지 한 번에 터질 수 있습니다. 그래서 나는 time-slicing 노드 풀과 non-sharing 노드 풀을 물리적으로 분리해 두는 쪽을 선호합니다. 업데이트 대상이 분리되면, 실패 반경이 확 줄어듭니다.

---

## 노드 롤링 업데이트에서 ‘드레인’을 어떻게 다룰지: GPU Operator와 Kubernetes의 책임 경계를 명확히 한다

드라이버 업데이트를 릴리스로 취급할 때 핵심은, “드레인(drain)을 한다/안 한다”가 아니라 “무엇을 드레인하는가”입니다.

- GPU 워크로드만 비워야 하는가
- 그 노드의 모든 워크로드를 비워야 하는가

GPU Operator의 드라이버 업그레이드 문서는 이걸 아주 노골적으로 경고합니다.

- `driver.upgradePolicy.drain.enable=true`는 노드를 드레인하며, 드레인은 **GPU와 무관한 pod도 포함해 해당 노드의 모든 pod를 evict**하므로 disruptive하다고 합니다.[^15]
- drain은 “gpuPodDeletion으로 GPU pod만 지우는 것으로 충분하지 않을 때만” 켜고, 꼭 써야 한다면 `podSelector`로 evict 대상 pod를 제한하라고 합니다.[^15]

즉, “GPU 드라이버 업그레이드”를 위해 클러스터의 비GPU 워크로드까지 흔들 필요가 없는 경우가 많습니다.

### 1) Kubernetes drain의 실제 동작: Eviction API + PDB

`kubectl drain`은 노드를 unschedulable로 마킹하고, Eviction API를 통해 pod를 퇴거시킵니다.[^16]

그리고 Kubernetes 공식 문서는 매우 중요한 사실을 하나 더 말합니다.

- drain 과정에서 제출되는 eviction 요청은 **일시적으로 거부될 수 있고**, `kubectl`은 실패한 요청을 재시도합니다.[^17]
- PDB는 voluntary disruption에서 최소 가용성을 보장하기 위해 eviction을 거부할 수 있습니다.[^18]

이게 GPU 노드 드라이버 업데이트와 만나면 어떤 일이 생기냐면, “드라이버 업그레이드 컨트롤러는 기다리고, drain은 PDB 때문에 멈추고, 롤링은 늘어지고, 결국 타임아웃/강제 종료” 같은 상황이 됩니다. 그래서 드레인을 “명령”이 아니라 “정책”으로 다뤄야 합니다.

### 2) 드레인을 ‘워크로드 드레인’과 ‘노드 드레인’으로 나눈다

내가 보통 설계하는 방식은 2단계입니다.

1) 워크로드 드레인(서비스 레벨)
- LLM 서빙 같은 온라인 워크로드는 요청 수신을 멈추고(in-flight만 처리), queue나 retry로 트래픽을 다른 replica로 넘깁니다.
- 이 단계가 끝나면 GPU pod 자체를 종료해도 SLO가 깨지지 않습니다.

2) 노드 드레인(인프라 레벨)
- 그 다음에야 `kubectl drain` 또는 Operator drain을 허용합니다.

이걸 분리하면 장점이 명확합니다.

- PDB는 “무작정 drain을 막는 안전장치”가 아니라 “서비스 레벨이 준비되면 자연스럽게 drain이 통과되게 만드는 장치”가 됩니다.
- 드라이버 업그레이드 컨트롤러가 `drain.enable=true`인 상태로 클러스터 전체를 휘젓는 리스크를 줄입니다.

### 3) GPU Operator의 병렬 업그레이드 제한을 ‘용량 계획’으로 바꾼다

GPU Operator 문서는 `maxUnavailable`과 `maxParallelUpgrades`를 같이 쓸 때, `maxUnavailable`이 `maxParallelUpgrades`에 추가 제약을 걸어 “의도한 만큼만 노드가 동시에 빠지게” 만든다고 설명합니다.[^15]

이걸 단순히 “한 번에 1대씩”으로 고정하면 너무 느리고, “한 번에 여러 대”로 풀면 위험합니다. 그래서 나는 다음 순서로 숫자를 정합니다.

- (1) 서비스가 감당 가능한 GPU capacity 감소율을 먼저 정합니다.
- (2) 그 감소율을 node 단위로 환산해 `maxUnavailable`을 정합니다.
- (3) drain/PDB가 길어질 때를 고려해 `maxParallelUpgrades`는 더 보수적으로 둡니다.

드라이버 업데이트를 릴리스로 다룬다는 건 결국 “업데이트 컨트롤러의 파라미터를 SLO/비용 계획의 언어로 번역하는 일”입니다.

---

## R595 595.91.07 롤링 업데이트 체크리스트: 커널·MIG·DCGM·드레인을 한 장에 놓는다

여기부터는 체크리스트 형태로 정리합니다. 각 항목은 “왜 필요한가”까지 포함합니다.

### A. 사전 점검(업데이트 윈도우 전에 끝내야 하는 것)

#### A-1. DCGM 버전 하한 충족
- [ ] DCGM이 4.3.x 이상인지 확인합니다.
- 이유: R595 595.91.07은 DCGM 4.3.x 이상만 호환이고, 이전 버전은 호환되지 않습니다.[^1]

#### A-2. Hopper subrevision=3의 VBIOS 게이트
- [ ] Hopper GPU subrevision=3인 노드가 있는지 분류합니다.
- [ ] 해당 노드의 VBIOS가 96.00.68.00.xx 이상인지 확인합니다.
- 이유: 조건 불충족 시 이 드라이버는 초기화에 실패할 수 있습니다.[^1]

#### A-3. Blackwell cuTensorMapEncode 계열 사용 여부
- [ ] cuTensorMapEncodeTiled / cuTensorMapEncodeIm2col 계열을 쓰는 프레임워크/커널이 있는지 식별합니다.
- [ ] 해당 워크로드가 “128KB 미만 backing allocation + dense non-overlapping이 아닌 텐서”를 만들 가능성이 있는지 점검합니다.
- [ ] 필요 시 릴리스 노트의 workaround 적용 계획(코드 변경/핫픽스)을 별도로 잡습니다.
- 이유: 스포라딕 IMA/MMU fault(Xid 13) 가능성과 workaround가 릴리스 노트에 명시돼 있습니다.[^1]

#### A-4. GB200: CDMM 도입 여부 결정
- [ ] GB200 플랫폼 노드 풀을 분리합니다.
- [ ] CDMM을 켤지 여부를 결정하고, 켠다면 `NVreg_CoherentGPUMemoryMode=driver`를 `modprobe.d`에 반영한 뒤 드라이버 reload(실질적으로는 재부팅)를 계획에 넣습니다.
- [ ] GDRCopy를 쓰는 환경이면 2.5.1 이상인지 확인합니다.
- 이유: CDMM은 GB200에서 driver가 GPU memory를 관리해 OS NUMA 노출/OS onlining을 피하고, Kubernetes에서 memory over-reporting을 해결하기 위해 활성화를 권장하며, GDRCopy 버전 조건이 따라옵니다.[^1]

#### A-5. RHEL 10 + Fabric Manager 계열 이슈 유무
- [ ] RHEL 10 노드에서 커널이 6.12.0-55.29.1.el10_0.x86_64인지 확인합니다.
- [ ] Fabric Manager가 필요한 노드(HGX/NVSwitch 등)에서 `doca-ofed`의 `ib_umad.ko` 누락 이슈 영향이 있는지 점검합니다.
- 이유: 해당 커널에서 Fabric Manager가 startup에 실패할 수 있다고 릴리스 노트가 경고합니다.[^1]

### B. 매트릭스 검증(릴리스 후보 조합을 만들고 통과시켜야 하는 것)

#### B-1. 커널 기준선 확정
- [ ] CUDA Installation Guide의 validated 커널 표를 근거로, 노드 풀별 커널 기준선(또는 허용 범위)을 정합니다.
- 예: Ubuntu 24.04.4 LTS x86_64 검증 커널이 6.17.0-19로 표기되는 식입니다.[^4]

#### B-2. 컨테이너 툴체인 호환성 점검
- [ ] 컨테이너는 host driver가 CUDA 요구사항을 만족해야만 실행된다는 전제를 문서로 박습니다.[^6]
- [ ] CUDA minor version compatibility 표를 기반으로, 서비스가 요구하는 CUDA에 대한 최소 driver 하한을 매트릭스에 넣습니다.[^7]

#### B-3. 스모크 테스트는 “실제 서빙 이미지”로 한다
- [ ] `nvidia-smi`만 돌리는 테스트는 통과 기준에서 제외합니다.
- [ ] 서빙/학습에 쓰는 base image를 그대로 띄워서, 모델 로드/짧은 inference/짧은 training step까지 실행합니다.

이 항목은 문서 인용보다는 경험칙에 가깝습니다. 드라이버 문제는 `nvidia-smi`를 통과하고도 특정 CUDA 커널 경로에서만 터지는 일이 많습니다.

### C. 롤링 업데이트 실행(업데이트 당일에 깨지기 쉬운 것)

#### C-1. 드레인 정책: GPU pod eviction 우선, drain은 최후
- [ ] GPU Operator에서 `driver.upgradePolicy.drain.enable`은 기본적으로 끄고 시작합니다.
- [ ] 정말 필요할 때만 켜되, `podSelector`로 evict 대상을 제한합니다.
- 이유: GPU Operator 문서가 drain을 cluster-wide disruptive operation으로 명확히 경고합니다.[^15]

#### C-2. PDB는 ‘업데이트를 막는 벽’이 아니라 ‘서비스 드레인 후 통과하는 문’이 되게 한다
- [ ] `kubectl drain`이 Eviction API를 쓰고, PDB에 의해 eviction이 거부/재시도될 수 있음을 전제로 runbook을 씁니다.[^17]
- [ ] 단일 replica GPU 서빙은 PDB로 보호하려고 하면 drain이 영원히 안 끝날 수 있으니(구조적으로) 구조를 바꿉니다.

PDB는 결국 “voluntary disruption에서 최소 가용성”을 정의하는 도구입니다. “드라이버 업데이트를 못 하게 하는 보안장치”로 쓰면 운영이 멈춥니다.

#### C-3. MIG 관련 작업과 드라이버 업데이트를 같은 윈도우에 섞지 않는다
- [ ] MIG 변경이 필요한 분기라면, 드라이버 롤링과 분리합니다.
- 이유: MIG Manager는 label 변경 시 GPU 관련 pod를 종료하고 재구성을 적용하며, 경우에 따라 reboot도 필요합니다.[^9]

---

## GPU Operator를 쓴다면: “업그레이드 컨트롤러”를 변경관리 시스템처럼 쓴다

GPU Operator를 쓰는 환경에서는 드라이버 업데이트가 OS 패키지 작업이 아니라, 컨트롤러가 수행하는 상태 기계(state machine) 작업으로 바뀝니다. 문서에서도 노드 label `nvidia.com/gpu-driver-upgrade-state`로 상태를 나타낸다고 설명합니다.[^15]

여기서 운영자가 실수하기 쉬운 지점은 다음입니다.

- 드라이버 업데이트 컨트롤러가 “GPU 관련 pod만” 지울 거라고 착각하는 것
- drain을 켜는 순간, 비GPU 워크로드까지 같이 흔들릴 수 있다는 점을 간과하는 것

문서가 제공하는 원칙은 명확합니다.

- drain은 마지막 카드로 남긴다.[^15]
- 병렬 업그레이드/가용성 제한은 숫자로 명시한다.[^15]

나는 이 원칙을 다음 운영 규칙으로 바꿉니다.

1) “GPU 노드 풀”을 반드시 분리한다
- 드라이버 릴리스가 비GPU 워크로드를 흔들지 않게 하려면, 애초에 같은 노드에 섞지 않는 게 제일 싸게 먹힙니다.

2) “업데이트 실패 반경”을 노드 풀 단위로 고정한다
- MIG 노드 풀, non-MIG 노드 풀, time-slicing 노드 풀을 분리하면 실패 반경이 예측 가능해집니다.

3) “관측 가능성”을 릴리스 합격 조건에 넣는다
- DCGM 버전 하한이 드라이버 릴리스 노트에 명시돼 있는 이상, 모니터링이 정상 동작하는지가 기능 테스트만큼 중요합니다.[^1]

---

## 최종 판단: 드라이버 업데이트를 릴리스로 만들면, 업데이트가 느려져도 장애는 줄어든다

R595 595.91.07은 단순 버그픽스만 있는 드라이버가 아닙니다.

- DCGM 최소 버전 하한, Hopper VBIOS 게이트, Blackwell 텐서맵 워크어라운드 같은 **운영 전제조건**이 드라이버 문서에 직접 들어가 있습니다.[^1]
- GB200 CDMM처럼 Kubernetes 관점의 권장 설정까지 포함돼 있어, 드라이버가 사실상 “플랫폼 동작 방식”을 바꿉니다.[^1]
- GPU Operator의 drain 정책은 잘못 쓰면 비GPU 워크로드까지 흔드는 형태가 될 수 있고, 문서도 이를 경고합니다.[^15]

그래서 내가 내리는 결론은 단순합니다.

드라이버 업데이트는 더 이상 패키지 업데이트가 아니라, 커널/런타임/DCGM/MIG 정책을 포함한 릴리스이며, 매트릭스와 체크리스트가 없으면 속도가 아니라 장애로 비용을 치르게 됩니다.

---

## 참고 자료

- [NVIDIA Data Center GPU Driver R595 595.91.07 릴리스 노트(HTML)](https://docs.nvidia.com/datacenter/tesla/tesla-release-notes-595-91-07/index.html)
- [NVIDIA Data Center GPU Driver R595 595.91.07 릴리스 노트(PDF)](https://docs.nvidia.com/datacenter/tesla/pdf/NVIDIA_Data_Center_GPU_Driver_Release_Notes_595_v3.0.pdf)
- [NVIDIA GPU Operator: GPU Driver Upgrades](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/26.3/gpu-driver-upgrades.html)
- [NVIDIA GPU Operator: GPU Operator with MIG](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/26.3/gpu-operator-mig.html)
- [Kubernetes: kubectl drain](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_drain/)
- [Kubernetes: Disruptions(PodDisruptionBudget, eviction)](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)
- [Kubernetes: Safely Drain a Node](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/)
- [CUDA Installation Guide for Linux(시스템 요구사항/커널 표 포함)](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html)
- [CUDA Compatibility: Minor Version Compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)
- [NVIDIA Container Toolkit 설치 가이드](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/1.12.0/install-guide.html)
- [nvidia-container-runtime README](https://github.com/NVIDIA/nvidia-container-toolkit/blob/main/cmd/nvidia-container-runtime/README.md)
- [NVIDIA MPS 문서](https://docs.nvidia.com/deploy/mps/615/index.html)
- [NVIDIA MPS: When to Use MPS](https://docs.nvidia.com/deploy/mps/615/when-to-use-mps.html)
- [Kubernetes SIGs: DRA Driver for NVIDIA GPUs – MPS 가이드](https://dra-driver-nvidia-gpu.sigs.k8s.io/docs/guides/mps/)
- [NVIDIA/k8s-device-plugin](https://github.com/NVIDIA/k8s-device-plugin)

[^1]: <https://docs.nvidia.com/datacenter/tesla/tesla-release-notes-595-91-07/index.html>
[^2]: <https://github.com/NVIDIA/nvidia-container-toolkit/blob/main/cmd/nvidia-container-runtime/README.md?plain=1>
[^3]: <https://docs.nvidia.com/datacenter/tesla/pdf/NVIDIA_Data_Center_GPU_Driver_Release_Notes_595_v3.0.pdf>
[^4]: <https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html>
[^5]: <https://nvidia.github.io/container-wiki/toolkit/container-images.html>
[^6]: <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/1.12.0/install-guide.html>
[^7]: <https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html>
[^8]: <https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/getting-started.html>
[^9]: <https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/26.3/gpu-operator-mig.html>
[^10]: <https://docs.nvidia.com/deploy/mps/615/index.html>
[^11]: <https://docs.nvidia.com/deploy/mps/when-to-use-mps.html>
[^12]: <https://dra-driver-nvidia-gpu.sigs.k8s.io/docs/guides/mps/>
[^13]: <https://github.com/NVIDIA/k8s-device-plugin>
[^14]: <https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/23.3.1/gpu-sharing.html>
[^15]: <https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/26.3/gpu-driver-upgrades.html>
[^16]: <https://kubernetes.io/docs/reference/kubectl/generated/kubectl_drain/>
[^17]: <https://kubernetes.io/docs/concepts/workloads/pods/disruptions/>
[^18]: <https://kubernetes.io/docs/tasks/run-application/configure-pdb/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
