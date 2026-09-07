---
title: "Kubernetes 1.37 DRA 업데이트: GPU 운영팀이 보는 GA급 변화"
description: "Extended Resource GA, 표준 NUMA 속성, Device metadata·taints가 GPU/가속기 운영의 스케줄링·드라이버 표준화에 미치는 영향을 정리합니다."
date: 2026-09-07 09:56:56 +0900
categories: ["News", "DevOps"]
tags: ["kubernetes", "dra", "gpu-ops", "scheduling", "numa", "device-drivers"]
render_with_liquid: false
---

## 2026-09-03에 무엇이 바뀌었나

Kubernetes 공식 블로그에 2026-09-03 게시된 [Kubernetes v1.37: DRA Updates](https://kubernetes.io/blog/2026/09/03/kubernetes-v1-37-dra-updates/)의 핵심은 한 줄로 요약됩니다. **DRA Extended Resource 지원이 GA(Stable)로 올라가면서, 기존 `example.com/gpu`(혹은 `nvidia.com/gpu`) 스타일의 Pod spec을 “그대로” 두고도 DRA 드라이버로 할당 경로를 바꿀 수 있게 됐습니다.**

이 글에서 GPU/가속기 운영팀 관점으로 GA급 변화 포인트를 세 덩어리로 나눠 봅니다.

1) 스케줄링 경로 변화: “Pod → (extended resource) → DRA”가 기본 선택지로 들어온 것
- v1.37에서 DRA Extended Resource가 GA로 승격되었습니다. Pod가 extended resource를 요청하면 DeviceClass의 `extendedResourceName` 매핑을 통해 DRA 디바이스로 할당이 가능합니다. 워크로드 쪽에서 ResourceClaim을 직접 만들지 않아도 된다는 게 포인트입니다. [DRA 업데이트 블로그](https://kubernetes.io/blog/2026/09/03/kubernetes-v1-37-dra-updates/)와 [DRA API Objects 문서의 Extended resource allocation by DRA](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/dra-api/#extended-resource-allocation-by-dra)에 동일한 방향이 정리돼 있습니다.

2) NUMA 표준화: `resource.kubernetes.io/numaNode`가 “표준 이름”으로 자리 잡은 것
- v1.37에서 `resource.kubernetes.io/numaNode` 표준 device attribute가 안정화된 것으로 소개됩니다. (KEP 성격상 feature gate나 동작 변경이 아니라 “이름/의미의 표준화”에 가깝기 때문에 stable로 바로 들어간 맥락도 설명돼 있습니다.) [DRA 업데이트 블로그](https://kubernetes.io/blog/2026/09/03/kubernetes-v1-37-dra-updates/), [Standard Device Attributes](https://kubernetes.io/docs/reference/node/dra-standard-device-attributes/), [KEP-6072](https://github.com/kubernetes/enhancements/blob/master/keps/sig-node/6072-dra-standard-numanode/README.md).

3) 드라이버/운영 표준화: device taints(Stable), device metadata(Beta) 같은 운영 기능이 “기본 구성 요소”로 굳어지는 것
- device 단위의 점검/격리/퇴출을 운영자가 API로 제어할 수 있는 device taints & tolerations가 v1.37 Stable입니다. [Device Taints and Tolerations](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/device-taints/), [v1.37 릴리스 블로그](https://kubernetes.io/blog/2026/08/26/kubernetes-v1-37-release/).
- 컨테이너에서 할당된 디바이스의 metadata(JSON)를 well-known path로 읽을 수 있는 device metadata 기능이 v1.37 Beta로 문서화돼 있습니다. [Access DRA Device Metadata](https://kubernetes.io/docs/tasks/configure-pod-container/assign-resources/access-dra-device-metadata/)와 v1.37 DRA 업데이트 블로그에서 의도(특히 CDI 마운트 경로/형식)가 설명됩니다.

내가 보기에 이 업데이트는 기능 몇 개가 추가된 수준이 아니라, “GPU 운영을 Kubernetes에 붙이는 방식”을 다시 정렬하는 신호에 가깝습니다. 기존 device plugin 기반 운영이 당장 사라지지는 않지만, 최소한 **운영팀이 DRA를 ‘실험 기능’으로만 취급할 근거는 점점 줄어듭니다.**

## DRA Extended Resource GA가 바꾸는 스케줄링: Pod spec을 고정하고, 운영이 경로를 바꾼다

GPU 운영에서 가장 현실적인 목표는 “앱 팀의 manifest 변경을 최소화”입니다. DRA 자체는 오브젝트가 늘어나고(ResourceSlice/DeviceClass/ResourceClaim…), 파이프라인도 길어집니다. 그래서 운영팀이 DRA를 도입하려고 하면 항상 충돌이 납니다.

- 앱 팀: `resources.limits: nvidia.com/gpu: 1`에서 벗어나기 싫다
- 운영팀: topology/NUMA/MIG/vGPU/격리/점검 같은 운영 요구사항을 device plugin으로는 표현하기 어렵다

v1.37에서 GA가 된 “Extended resource allocation by DRA”는 이 충돌을 가장 실용적으로 풀어줍니다. DeviceClass에 `extendedResourceName`만 매핑하면, Pod는 기존 extended resource를 요청하되 실제 할당은 DRA가 수행할 수 있습니다. 이 동작은 [DRA API Objects 문서](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/dra-api/#extended-resource-allocation-by-dra)와 [DeviceClass API 레퍼런스의 `extendedResourceName`](https://kubernetes.io/docs/reference/kubernetes-api/resource/device-class-v1/)에서 확인할 수 있습니다.

운영 관점에서 중요한 건 “편의성”이 아니라 “스케줄링 모델이 바뀐다”는 사실입니다.

- 기존 extended resource(device plugin)는 Node의 allocatable에 숫자를 올려서 스케줄러가 숫자 비교만 합니다.
- DRA extended resource는 스케줄러가 DeviceClass/ResourceSlice를 보고 실제 디바이스 후보를 평가하는 경로가 됩니다(동적 할당 플러그인).

KEP-5004는 스케줄러 내부적으로 extended resource 요청을 위해 “특수한 ResourceClaim을 생성”하는 설계를 분명히 적습니다. 즉, Pod spec은 단순해지지만 클러스터 내부에서는 ResourceClaim이 늘어납니다. 이 부분은 quota/관측/권한에 직격탄입니다. [KEP-5004](https://github.com/kubernetes/enhancements/blob/master/keps/sig-scheduling/5004-dra-extended-resource/README.md)에서 “scheduler would create a special resource claim”이라는 설명과 함께 quota 카운팅이 왜 바뀌어야 하는지 예시까지 들어갑니다.

이게 GPU 운영팀의 관점에서 좋은 이유는 명확합니다.

- 앱 팀이 `ResourceClaim`을 이해하지 않아도 된다.
- 운영팀은 DeviceClass를 통해 “어떤 GPU가 `nvidia.com/gpu`로 보일지”를 정책화할 수 있다.
- 한 클러스터에서 어떤 노드는 device plugin, 어떤 노드는 DRA 드라이버로 점진적 전환이 가능하다는 점이 KEP의 목표로 박혀 있습니다. [KEP-5004](https://github.com/kubernetes/enhancements/blob/master/keps/sig-scheduling/5004-dra-extended-resource/README.md), [DRA API Objects 문서](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/dra-api/#extended-resource-allocation-by-dra).

반대로 위험도 분명합니다.

- DeviceClass가 “클러스터 스코프”라서, 잘못 만들면 전 클러스터의 `nvidia.com/gpu` 의미를 바꿉니다.
- `extendedResourceName`이 중복되면 “나중에 생성된 DeviceClass가 선택된다” 같은 결정 규칙이 문서에 있습니다. 운영 실수로 충돌이 나면 재현이 어려운 유형의 장애가 됩니다. [DeviceClass API 레퍼런스](https://kubernetes.io/docs/reference/kubernetes-api/resource/device-class-v1/).
- 스케줄러가 ResourceClaim을 생성하는 경로는 API server/APF(priority and fairness)/quota/RBAC에 더 민감해집니다. KEP-5004는 “높은 비율로 Pod 생성 + APF 제한이 낮으면 claim 생성 실패” 가능성을 테스트 항목으로 박아놨습니다. 운영에서는 이게 곧 on-call 이슈입니다. [KEP-5004](https://github.com/kubernetes/enhancements/blob/master/keps/sig-scheduling/5004-dra-extended-resource/README.md).

## NUMA 관점: `resource.kubernetes.io/numaNode` 표준화는 ‘GPU+NIC+스토리지’ 묶음 스케줄링의 전제 조건이다

GPU 클러스터에서 NUMA는 성능 최적화라기보다 “성능 편차/장애 티켓”의 원인이 됩니다.

- 같은 모델의 GPU인데 노드/슬롯에 따라 PCIe root, NUMA proximity가 달라서 latency가 튄다
- RDMA NIC과 GPU를 같은 socket에 붙이지 않으면 통신이 흔들린다
- NVMe local cache를 GPU와 가깝게 두지 않으면 I/O가 병목이 된다

device plugin 시대에도 NUMA-aware 배치를 하려는 시도는 있었지만, “표준 속성 이름”이 없어서 벤더별로 제각각이 됐습니다. DRA의 `matchAttribute`는 **동일한 attribute 이름**을 요구하는데, 드라이버마다 이름이 다르면 교차 드라이버 NUMA co-location이 불가능합니다.

v1.37의 변화 포인트는 “스케줄러가 NUMA를 이해하게 됐다”가 아닙니다. **각 드라이버가 NUMA locality를 표준 이름 `resource.kubernetes.io/numaNode`로 발행하면, `matchAttribute`로 교차 드라이버 co-location이 가능해진다**가 본질입니다. 이 맥락은 [DRA 업데이트 블로그](https://kubernetes.io/blog/2026/09/03/kubernetes-v1-37-dra-updates/), [Standard Device Attributes](https://kubernetes.io/docs/reference/node/dra-standard-device-attributes/), [KEP-6072](https://github.com/kubernetes/enhancements/blob/master/keps/sig-node/6072-dra-standard-numanode/README.md)에 일관되게 나옵니다.

특히 운영팀 입장에서 좋은 점은 “동일 노드 내 co-location”을 넘어서, **드라이버가 달라도 동일한 문법으로 정책을 걸 수 있다**는 점입니다.

- GPU driver가 `resource.kubernetes.io/numaNode` 발행
- NIC driver도 같은 이름으로 발행
- ResourceClaim에서 `constraints.matchAttribute: resource.kubernetes.io/numaNode` 한 줄로 묶음 할당

그리고 KEP-6072는 list type attribute까지 연결합니다. 단일 NUMA node로 떨어지지 않는(혹은 “같은 socket” 정도로만 정의 가능한) 토폴로지에서 list 형태를 쓰면, 스케줄러는 “set intersection”으로 매칭할 수 있게 설계돼 있습니다. [Standard Device Attributes](https://kubernetes.io/docs/reference/node/dra-standard-device-attributes/), [KEP-5491](https://www.kubernetes.dev/resources/keps/5491/), [KEP-6072](https://github.com/kubernetes/enhancements/blob/master/keps/sig-node/6072-dra-standard-numanode/README.md).

여기서 함정은 두 가지입니다.

- NUMA 정보가 OS에서 `-1`로 나오면(affinity 없음) 표준 속성을 “발행하지 말아야 한다”는 규칙이 있습니다. 즉, 운영자가 `matchAttribute`를 강제하면 일부 노드/디바이스가 통째로 후보에서 빠질 수 있습니다. [Standard Device Attributes](https://kubernetes.io/docs/reference/node/dra-standard-device-attributes/).
- list type attribute는 아직 feature gate(`DRAListTypeAttributes`)가 필요한 알파 라인입니다. 즉, “표준 이름은 stable”인데 “표현 형식(list)”은 운영 판단이 필요합니다. [Feature Gates 문서](https://kubernetes.io/docs/reference/command-line-tools-reference/feature-gates/), [KEP-5491](https://www.kubernetes.dev/resources/keps/5491/).

운영 결론은 단순합니다.

- v1.37 업그레이드 시점에 당장 list type까지 켜지 않더라도, `resource.kubernetes.io/numaNode` 표준 이름으로 가는 건 장기적으로 이득이 큽니다.
- 다만 NUMA가 제대로 노출되는지(펌웨어/BIOS/커널/PCIe 토폴로지 포함)와 “속성이 누락되는 케이스”를 먼저 측정해야 합니다.

## 드라이버 표준화 관점: Device metadata(Beta) + device taints(Stable)가 운영 체계를 바꾼다

### device taints: “GPU 하나만” 격리하는 API가 생겼다

GPU 운영에서 가장 반복되는 작업은 “문제 있는 GPU를 빼는 것”입니다.

- ECC error가 누적되는 GPU
- 링크 다운/재협상 반복
- 온도/전력 스로틀링
- MIG/vGPU 모드 전환 작업

node taint로는 해결이 안 됩니다. 노드에는 GPU가 여러 개고, 하나만 문제인 경우가 흔합니다.

v1.37에서 Stable인 device taints & tolerations는 이 요구를 API로 모델링합니다. 핵심 문서는 [Device Taints and Tolerations](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/device-taints/)이고, 운영자가 DRA 드라이버를 수정하지 않고도 `DeviceTaintRule`을 만들어 taint를 걸 수 있다는 점이 중요합니다. 해당 문서는 `DRADeviceTaints`, `DRADeviceTaintRules`가 v1.37에서 stable이고(더 이상 opt-out 불가한 locked behavior), DeviceTaintRule로 admin이 taint를 적용할 수 있다고 설명합니다.

또한 `DeviceTaintRule` 자체가 `resource.k8s.io/v1`에 들어가 있어(클러스터 운영 API로 취급할 수 있어) 정책/권한/감사 체계에 넣기가 쉬워졌습니다. [DeviceTaintRule API 레퍼런스](https://kubernetes.io/docs/reference/kubernetes-api/resource/device-taint-rule-v1/).

### device metadata: 컨테이너에서 “할당된 디바이스의 사실”을 읽는다

운영팀 관점에서 device metadata(Beta)는 두 갈래로 중요합니다.

1) KubeVirt/VM passthrough 같은 시나리오에서, VM 내부로 넘길 디바이스 식별자(PCI address 등)를 workload가 알아야 한다.
2) 관측/진단에서, “이 Pod가 실제로 어떤 GPU를 잡았는지”를 workload 로그/내부 에이전트로 남기고 싶다.

v1.37에서 문서화된 동작은 이렇습니다.

- 드라이버가 claim prepare 단계에서 metadata를 채우면
- 프레임워크가 JSON 파일로 쓰고(CDI 경로로 마운트)
- 컨테이너는 well-known path에서 `*-metadata.json`을 읽는다

이 경로는 [Access DRA Device Metadata](https://kubernetes.io/docs/tasks/configure-pod-container/assign-resources/access-dra-device-metadata/)에 명시돼 있습니다. `ResourceClaim`을 직접 참조하면 `/var/run/kubernetes.io/dra-device-attributes/resourceclaims/<claimName>/<requestName>/<driverName>-metadata.json` 형태입니다.

이게 드라이버 표준화인 이유는, 지금까지 GPU 운영에서 “디바이스 식별자/모델/드라이버 버전” 같은 사실이 필요하면 대개

- node exporter 류에서 node 기준으로 모으거나
- 별도 컨트롤러가 ResourceSlice/ResourceClaim을 watch해서 Pod에 annotation을 써주거나
- 앱 이미지 안에 vendor CLI를 넣고 노드 권한을 줘야 했습니다.

device metadata는 이걸 “Kubernetes 경로/스키마”로 정리하려는 움직임입니다.

다만 보안/멀티테넌시에서는 양날입니다.

- 어떤 metadata를 노출할지(예: PCI address가 테넌트 간 side channel이 될 수 있는지)
- 이 JSON을 읽는 애플리케이션이 이를 신뢰해도 되는지(스푸핑/변조 경로는 없는지)

같은 논의가 필요합니다. DRA가 status 업데이트 권한을 세분화한 것도 같은 방향입니다.

## 실제 운영 시나리오 1: `nvidia.com/gpu` 요청을 DRA로 받는 DeviceClass 구성

여기서부터는 “업그레이드 전에 준비할 매니페스트/정책” 관점으로, 실제로 적용 가능한 최소 구성을 적습니다.

전제

- Kubernetes v1.37
- DRA가 이미 enable된 클러스터(기본적으로 DRA는 stable locked behavior로 알려져 있고, DRA 관련 API group을 비활성화하면 동작이 꼬일 수 있습니다. 클러스터 설정은 [Set Up DRA in a Cluster](https://kubernetes.io/docs/tasks/configure-pod-container/assign-resources/set-up-dra-cluster/) 참고)
- NVIDIA 쪽은 예시로 [DRA Driver for NVIDIA GPUs 문서](https://dra-driver-nvidia-gpu.sigs.k8s.io/docs/reference/resourceslice-attributes/)에서 설명하는 `gpu.nvidia.com` 드라이버를 기준으로 합니다. 이 드라이버는 하나의 드라이버 이름(`gpu.nvidia.com`) 아래에서 node별 pool을 두고, DeviceClass로 `gpu.nvidia.com`(full GPU), `mig.nvidia.com`, `vfio.gpu.nvidia.com`을 제공하는 형태로 설명돼 있습니다.

### 1) DeviceClass에 `extendedResourceName`을 매핑한다

DeviceClass의 `extendedResourceName`은 v1 API에서 제공됩니다. [DeviceClass API 레퍼런스](https://kubernetes.io/docs/reference/kubernetes-api/resource/device-class-v1/)는 `extendedResourceName`이 extended resource 요청을 DRA 디바이스로 만족시키기 위한 필드이며, 동일 이름이 충돌하면 “나중에 생성된 DeviceClass가 선택된다” 같은 규칙을 명시합니다.

운영적으로는 충돌 방지를 위해 다음을 권합니다.

- `extendedResourceName`을 부여하는 DeviceClass는 클러스터에서 딱 하나만 유지
- GitOps에서 apply 순서를 보장(동일 이름 충돌이 있을 경우 결과가 바뀔 수 있음)

예시: full GPU만 `nvidia.com/gpu`로 제공

```yaml
apiVersion: resource.k8s.io/v1
kind: DeviceClass
metadata:
  name: nvidia-gpu-dra
spec:
  # 핵심: 기존 Pod spec의 extended resource 이름을 여기에 연결
  extendedResourceName: nvidia.com/gpu

  # selectors는 “어떤 디바이스가 이 클래스에 속하는지”를 정의
  # 아래 표현은 NVIDIA DRA 드라이버의 attribute 모델(도메인 접근)을 기준으로 함
  selectors:
  - cel:
      expression: |
        device.driver == 'gpu.nvidia.com' &&
        device.attributes['gpu.nvidia.com'].type == 'gpu'
```

이렇게 하면 워크로드는 여전히:

```yaml
resources:
  limits:
    nvidia.com/gpu: "1"
```

로 요청하지만, 내부 할당은 DRA가 담당할 수 있게 됩니다. 이 동작 자체는 [DRA API Objects 문서](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/dra-api/#extended-resource-allocation-by-dra)에 “Pod에서 ResourceClaim 없이도 DeviceClass를 통해 할당”이 가능하다고 설명돼 있습니다.

### 2) 스케줄러가 ResourceClaim을 생성한다는 사실을 운영 지표로 잡는다

KEP-5004는 스케줄러가 extended resource 요청에 대해 “특수한 ResourceClaim을 생성”하며, 그 때문에 quota 카운팅도 조정돼야 한다고 예시를 듭니다. 이건 운영에서 굉장히 중요합니다. Pod spec이 단순해지는 대가로, 컨트롤 플레인 오브젝트 수가 늘어납니다. [KEP-5004](https://github.com/kubernetes/enhancements/blob/master/keps/sig-scheduling/5004-dra-extended-resource/README.md).

또한 KEP 본문은 스케줄러가 해당 claim을 식별하기 위해 annotation을 사용한다고 설명합니다. 이 값을 기반으로 “extended resource 경로에서 생성된 claim”만 따로 모니터링하는 게 가능합니다. [KEP-5004](https://github.com/kubernetes/enhancements/blob/master/keps/sig-scheduling/5004-dra-extended-resource/README.md).

실제 점검 커맨드 예시(클러스터마다 annotation 값/형식이 다를 수 있으니 KEP/코드 기준으로 검증 필요):

```bash
# extended resource 요청으로 인해 생성된 ResourceClaim을 찾아본다
kubectl get resourceclaims -A -o json | \
  jq -r '
    .items[]
    | select(.metadata.annotations["resource.kubernetes.io/extended-resource-claim"] != null)
    | [.metadata.namespace, .metadata.name, .metadata.annotations["resource.kubernetes.io/extended-resource-claim"]]
    | @tsv
  '
```

여기서 운영 포인트는 “이게 보이면 성공”이 아니라, 다음을 함께 봐야 한다는 점입니다.

- claim 생성 실패율(스케줄러 이벤트)
- claim 개수 증가에 따른 etcd 부담
- quota/RBAC가 claim 생성 경로를 막는지

## 실제 운영 시나리오 2: NUMA를 강제하는 ResourceClaimTemplate(동일 NUMA GPU 2장)

GPU 2장 이상을 묶어서 쓰는 워크로드(LLM tensor parallel, multi-GPU training, NCCL 통신)는 “같은 노드”만으로 부족하고, 가능하면 같은 socket/NUMA에 붙여야 편차가 줄어듭니다.

v1.37에서 강조되는 포인트는 `resource.kubernetes.io/numaNode` 표준 속성입니다. 이 속성은 [Standard Device Attributes](https://kubernetes.io/docs/reference/node/dra-standard-device-attributes/)에 정의돼 있고, 스케줄러의 `matchAttribute`에서 list type일 때 set intersection으로 동작한다는 점까지 문서에 들어가 있습니다.

NVIDIA DRA 드라이버는 ResourceSlice에 `resource.kubernetes.io/numaNode`를 발행한다고 명시하고, `matchAttribute: resource.kubernetes.io/numaNode` 예시도 제공합니다. [NVIDIA DRA driver ResourceSlice attributes](https://dra-driver-nvidia-gpu.sigs.k8s.io/docs/reference/resourceslice-attributes/).

아래 매니페스트는 “Pod마다 claim을 생성”하는 형태로, 앱 팀이 Pod spec을 수정할 수 있는 경우에 가장 정석적인 DRA 사용입니다.

```yaml
apiVersion: resource.k8s.io/v1
kind: ResourceClaimTemplate
metadata:
  name: same-numa-2x-gpu
spec:
  spec:
    devices:
      requests:
      - name: gpus
        exactly:
          deviceClassName: gpu.nvidia.com
          allocationMode: ExactCount
          count: 2
      constraints:
      - requests:
        - gpus
        matchAttribute: resource.kubernetes.io/numaNode
---
apiVersion: v1
kind: Pod
metadata:
  name: llm-worker
spec:
  resourceClaims:
  - name: accel
    resourceClaimTemplateName: same-numa-2x-gpu

  containers:
  - name: worker
    image: ubuntu:24.04
    command: ["bash","-lc"]
    args:
    - |
      echo "claim-based scheduling done";
      sleep 3600
    resources:
      claims:
      - name: accel
        request: gpus
```

이 방식은 extended resource GA 경로와 다릅니다.

- extended resource GA: 앱은 `nvidia.com/gpu`만 알면 됨(대신 디바이스 selection/NUMA 제약을 앱 spec에서 표현하기 어려움)
- ResourceClaimTemplate: NUMA, PCIe root, 특정 속성 선택 같은 디바이스 정책을 workload spec에 넣을 수 있음

운영팀이 두 방식을 같이 가져가야 하는 이유도 여기에 있습니다. “앱 변경 없이 전환”은 extended resource 경로가 강하지만, “성능/토폴로지 제약을 앱이 명시”하려면 claim 경로가 필요합니다.

## 실제 운영 시나리오 3: DeviceTaintRule로 특정 GPU를 격리(노드 전체가 아니라 디바이스 하나)

device taints는 Stable이고, admin이 `DeviceTaintRule`을 생성해 드라이버 수정 없이 taint를 적용할 수 있습니다. [Device Taints and Tolerations](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/device-taints/).

`DeviceTaintRule`의 selector는 최소한 `driver`, `pool`, `device`를 조합할 수 있습니다. 특히 `device`는 `slice.spec.devices[].name`과 대응한다고 API 레퍼런스에 명시돼 있습니다. [DeviceTaintRule API 레퍼런스](https://kubernetes.io/docs/reference/kubernetes-api/resource/device-taint-rule-v1/).

문제는 “GPU-0” 같은 디바이스 이름이 노드마다 반복될 수 있다는 점입니다. 그래서 운영에서는 pool까지 같이 넣어야 재현성이 생깁니다.

- 많은 node-local 드라이버가 node name을 pool name으로 쓰는 패턴을 권장합니다. 실제로 공식 문서도 pool을 더하면 단일 노드로 제한할 수 있다고 설명합니다. [Device Taints and Tolerations](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/device-taints/).

먼저 pool 이름을 확인합니다.

```bash
# 특정 드라이버의 ResourceSlice에서 pool 이름 목록을 본다
kubectl get resourceslices -o json | \
  jq -r '.items[]
    | select(.spec.driver=="gpu.nvidia.com")
    | .spec.pool.name' | sort -u
```

이제 특정 pool(예: worker-03)에서 `gpu-0`를 NoSchedule로 격리하는 예시입니다.

```yaml
apiVersion: resource.k8s.io/v1
kind: DeviceTaintRule
metadata:
  name: isolate-worker03-gpu0
spec:
  deviceSelector:
    driver: gpu.nvidia.com
    pool: worker-03
    device: gpu-0
  taint:
    key: ops.example.com/isolation
    value: maintenance
    effect: NoSchedule
```

이걸 적용하면, 해당 디바이스를 선택해야 하는 ResourceClaim은 할당 단계에서 후보에서 빠지거나(혹은 toleration이 없으면) 스케줄이 막힙니다. 동작 모델은 공식 문서가 node taint와 유사하게 설명합니다. [Device Taints and Tolerations](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/device-taints/).

운영팀이 이 기능을 좋아할 이유는 간단합니다.

- 노드 drain 없이 GPU 1개만 “조용히” 뺄 수 있다
- 격리 상태가 API object로 남아서, 사람이 SSH로 해둔 조치보다 추적이 쉽다

## 확인/점검: v1.37 업그레이드 전에 꼭 봐야 할 매니페스트·드라이버·정책 체크리스트

여기부터는 “지금(2026-09-07 KST) 업그레이드를 준비한다”는 전제로, 내가 운영팀이라면 무엇부터 점검하는지 순서대로 적습니다.

### 1) feature gate / 버전 스큐: stable이라고 해서 ‘항상 켜져 있다’는 뜻은 아니다

v1.37에서 DRA 관련 feature gate 상태는 문서화돼 있습니다.

- `DRAExtendedResource`: v1.37 Stable, 기본값 true
- `DRADeviceTaints`, `DRADeviceTaintRules`: v1.37 Stable
- `DRAResourceClaimDeviceStatus`: v1.37 Stable
- `DRADerivedAttributes`: v1.37 Alpha(기본 off)
- `DRADeviceCompatibilityGroups`: v1.37 Alpha(기본 off)
- `DRAListTypeAttributes`: Alpha(기본 off)

이 표는 [Feature Gates](https://kubernetes.io/docs/reference/command-line-tools-reference/feature-gates/)에서 확인 가능합니다.

운영에서 중요한 건 “클러스터가 업그레이드 중일 때”입니다.

- apiserver/scheduler/kubelet이 한 번에 같이 바뀌지 않습니다.
- DRA는 특히 scheduler와 kubelet이 모두 관여합니다.

그래서 알파 기능(DRAListTypeAttributes, DerivedAttributes 등)을 업그레이드와 동시에 켜는 건 위험합니다. 우선은 “Stable로 올라간 경로만”을 받아들이고, 알파는 별도 실험 클러스터에서 테스트하는 게 현실적입니다.

### 2) DeviceClass 충돌: `extendedResourceName` 중복이 가장 위험한 운영 실수다

DeviceClass의 `extendedResourceName`은 클러스터 전역 의미를 가집니다. 그리고 레퍼런스는 “동일한 이름을 가진 DeviceClass가 2개면 나중에 생성된 게 선택된다”는 규칙을 명시합니다. [DeviceClass API 레퍼런스](https://kubernetes.io/docs/reference/kubernetes-api/resource/device-class-v1/).

운영 체크리스트

- `extendedResourceName: nvidia.com/gpu`를 가진 DeviceClass가 몇 개인지
- GitOps apply 순서가 흔들릴 여지가 있는지
- 테스트/스테이징에서 만든 DeviceClass가 prod에 남아 있지 않은지

확인 커맨드 예시

```bash
kubectl get deviceclasses -o json | \
  jq -r '.items[]
    | select(.spec.extendedResourceName!=null)
    | [.metadata.name, .spec.extendedResourceName] | @tsv'
```

### 3) ResourceQuota: “Pod는 claim을 안 쓰는데 quota는 claim 때문에 막히는” 상황이 생긴다

KEP-5004의 quota 예시는 운영팀이 반드시 읽어야 합니다. 핵심은 이겁니다.

- extended resource 요청도 내부적으로는 ResourceClaim이 생성될 수 있다
- 기존 quota 모델(extended resource quota vs claim quota)이 서로 영향을 준다

이 내용은 KEP에서 매우 구체적으로 다룹니다. [KEP-5004](https://github.com/kubernetes/enhancements/blob/master/keps/sig-scheduling/5004-dra-extended-resource/README.md).

운영 체크리스트

- `requests.nvidia.com/gpu` 류 quota를 쓰고 있다면, DRA 전환 시 어떤 used 값이 늘어날지 사전 계산
- `*.deviceclass.resource.k8s.io/devices` 류 quota가 이미 존재하는지(혹은 기본 정책으로 만들어질지)
- “앱 팀은 똑같이 배포했는데 quota exceeded”가 발생할 가능성

이 부분을 대충 넘기면, 업그레이드 직후 장애 유형이 “GPU가 없어서 스케줄 실패”가 아니라 “quota 때문에 ResourceClaim 생성 실패/할당 실패”로 바뀝니다.

### 4) RBAC/보안: DRA status 권한은 v1.36부터 더 촘촘해졌다

DRA는 ResourceClaim status를 스케줄러/드라이버가 업데이트합니다. 그래서 권한이 넓으면 멀티테넌시에서 위험해집니다.

v1.36부터는 DRA status 업데이트 권한을 synthetic subresource로 쪼개고(node-aware verb 포함) least privilege를 유도합니다. 공식 문서가 하드닝 가이드로 따로 나와 있고, 예시 ClusterRole까지 제공합니다. [Hardening Guide - Dynamic Resource Allocation](https://kubernetes.io/docs/concepts/security/hardening-guide/dynamic-resource-allocation/).

운영 체크리스트

- 스케줄러/할당 컨트롤러가 `resourceclaims/binding` 업데이트 권한을 갖는지
- node-local 드라이버가 `resourceclaims/driver`에 대해 `associated-node:update|patch`로 제한된 권한을 갖는지
- 이전 버전에서 관성적으로 `resourceclaims/status`를 broad하게 열어둔 것이 없는지

특히 GPU 드라이버는 DaemonSet으로 노드에 깔리기 때문에, 그 ServiceAccount 권한은 “노드 경계”를 넘어서는 순간 사고가 됩니다.

### 5) NUMA 표준 속성 적용 여부: attribute가 누락되는 노드를 먼저 찾아야 한다

`resource.kubernetes.io/numaNode` 표준 자체는 stable이지만, “모든 디바이스가 이 속성을 발행할 것”은 보장되지 않습니다.

- Standard attribute 문서는 sysfs에서 NUMA affinity가 `-1`이면 속성을 발행하지 말라고 명시합니다. [Standard Device Attributes](https://kubernetes.io/docs/reference/node/dra-standard-device-attributes/).
- NVIDIA 드라이버 문서도 host에서 `-1`이면 `resource.kubernetes.io/numaNode`를 omit한다고 명시합니다. [NVIDIA DRA driver ResourceSlice attributes](https://dra-driver-nvidia-gpu.sigs.k8s.io/docs/reference/resourceslice-attributes/).

운영 체크리스트

- “NUMA 강제” claim이 실제로 어느 노드에서 실패하는지
- 같은 하드웨어인데 BIOS 설정/PCIe 슬롯이 달라서 -1이 나오는지

NVIDIA 문서가 제공하는 점검 스니펫이 실용적입니다(리소스 슬라이스에서 발행값과 host sysfs를 대조). [NVIDIA DRA driver ResourceSlice attributes](https://dra-driver-nvidia-gpu.sigs.k8s.io/docs/reference/resourceslice-attributes/).

### 6) list type attributes(DRAListTypeAttributes): 켜는 순간 관측 파이프라인이 깨질 수 있다

`DRAListTypeAttributes`는 알파이고, 켜면 같은 의미의 속성이라도 직렬화가 바뀔 수 있습니다.

예를 들어 `resource.kubernetes.io/numaNode`가 기존에는 `int`로 보이다가, list가 enable되면 `ints: [0]` 같은 형태로 보일 수 있습니다. NVIDIA 문서가 이 변화를 명시합니다. [NVIDIA DRA driver ResourceSlice attributes](https://dra-driver-nvidia-gpu.sigs.k8s.io/docs/reference/resourceslice-attributes/).

이건 “스케줄링은 멀쩡한데, 우리 관측/리포트 파서가 깨지는” 유형의 장애를 부릅니다.

운영 체크리스트

- ResourceSlice/ResourceClaim을 파싱하는 내부 툴이 있는지
- `int`만 가정하고 있지 않은지
- `ints`와 `int`를 동시에 처리할 수 있는지

표준 문서도 list일 때 스케줄러 매칭이 set intersection이라고 적고 있어, 운영자가 list를 해석할 때도 이 모델을 따라가는 게 좋습니다. [Standard Device Attributes](https://kubernetes.io/docs/reference/node/dra-standard-device-attributes/).

### 7) device metadata(Beta): 워크로드가 읽기 시작하면, 형식/경로가 ‘계약’이 된다

device metadata는 컨테이너 내부 경로가 well-known으로 고정됩니다. [Access DRA Device Metadata](https://kubernetes.io/docs/tasks/configure-pod-container/assign-resources/access-dra-device-metadata/)는 경로를 명확히 적고 있고, 예시 매니페스트/예상 출력까지 제공합니다.

운영 체크리스트

- workload가 이 JSON을 읽어 특정 동작을 하게 만들 건지(예: NIC MAC 기반 라이선스, GPU UUID 기반 샤딩)
- 그렇다면 드라이버 업그레이드가 metadata 스키마/필드에 어떤 영향을 주는지
- 컨테이너 이미지에 `jq` 같은 도구가 필요한지(필요하면 base image 표준에도 영향)

이걸 한 번 앱이 의존하기 시작하면, 운영팀은 드라이버/클러스터 업그레이드 때 “호환성 계약”을 지키는 역할까지 떠안게 됩니다.

## 반론과 회의론: DRA가 GA급으로 가도 GPU 운영은 여전히 어려운 이유

이 업데이트를 긍정적으로 봐도, 회의적인 지점은 남습니다.

1) “DRA 자체는 stable인데, 내가 필요한 기능은 alpha/beta다”
- 현실적으로 GPU 운영이 원하는 건 topology/partitioning/health/eviction/observability를 한꺼번에 붙이는 겁니다.
- 그런데 v1.37에서도 DerivedAttributes, CompatibilityGroups 같은 기능은 alpha이고 기본 off입니다. [DRA Features](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/dra-features/).

2) 드라이버 생태계가 균일하지 않다
- NVIDIA는 문서/드라이버가 비교적 빠르게 따라오지만, NIC/스토리지/TPU/FPGA는 각자 속도가 다릅니다.
- 결국 “GPU는 DRA, NIC은 SR-IOV device plugin” 같은 혼합 운영이 한동안 계속됩니다.

3) 운영 비용이 줄어드는 게 아니라, 비용의 위치가 이동한다
- 앱 팀의 manifest 부담은 줄어들 수 있지만
- 대신 운영팀은 DeviceClass/RBAC/Quota/Feature gate/파서 호환성까지 관리해야 합니다.

이 회의론이 맞는 부분도 있습니다. 다만 v1.37의 Extended Resource GA는 “DRA를 쓰는 팀이 소수”에서 “DRA가 스케줄링 경로의 한 축”으로 이동하는 전환점이라서, 운영 체계가 그 방향으로 조금씩 끌려갈 가능성이 큽니다.

## 앞으로 지켜볼 것: GA로 굳어지는 것과, 아직 불안정한 것의 경계

v1.37 시점에서 경계를 이렇게 잡는 게 현실적입니다.

- GA/Stable로 굳어지는 축
  - Extended resource allocation by DRA(`DRAExtendedResource`): on by default로 운영 경로에 들어옴. [Feature Gates](https://kubernetes.io/docs/reference/command-line-tools-reference/feature-gates/), [DRA API Objects](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/dra-api/#extended-resource-allocation-by-dra).
  - device taints(`DRADeviceTaints`, `DRADeviceTaintRules`): 운영 API로 정착. [Device Taints and Tolerations](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/device-taints/).
  - 표준 속성(`resource.kubernetes.io/numaNode` 등): 드라이버 간 조합의 기본 단어가 됨. [Standard Device Attributes](https://kubernetes.io/docs/reference/node/dra-standard-device-attributes/).

- 아직 운영 판단이 필요한 축
  - list type attributes(`DRAListTypeAttributes`): 관측/파서/호환성 영향이 커서 쉽게 못 켬. [KEP-5491](https://www.kubernetes.dev/resources/keps/5491/).
  - DerivedAttributes(`DRADerivedAttributes`): 표준화가 늦는 드라이버를 이어주는 강력한 도구지만, 알파이고 정책 복잡도가 올라감. [DRA API Objects](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/dra-api/#derived-attributes).
  - CompatibilityGroups(`DRADeviceCompatibilityGroups`): MIG/vGPU 같은 상호배타 모드에서 매우 유용하지만, 알파이고 드라이버가 얼마나 구현하느냐에 따라 체감이 갈림. [DRA Features - device compatibility groups](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/dra-features/).

운영팀 관점에서 이 경계를 잘못 잡으면, 업그레이드가 “기능 추가”가 아니라 “운영 복잡도 폭발”로 느껴집니다.

## 지금 시점(2026-09-07 KST)에 내리는 도입 판단

Kubernetes v1.37의 DRA 업데이트(2026-09-03)는 GPU 운영에서 가장 정치적인 문제였던 “앱 manifest를 바꾸지 말자”를 기술적으로 풀어주는 카드가 GA로 올라왔다는 데 의미가 큽니다. [Kubernetes v1.37: DRA Updates](https://kubernetes.io/blog/2026/09/03/kubernetes-v1-37-dra-updates/).

다만 이걸 바로 “DRA로 완전 전환”으로 읽으면 위험합니다. extended resource GA 경로는 전환을 쉽게 만들지만, 내부적으로는 ResourceClaim/Quota/RBAC/관측 파이프라인이 더 복잡해집니다. 그리고 NUMA 표준화는 시작점이지, 모든 노드/모든 드라이버가 동일 품질로 `resource.kubernetes.io/numaNode`를 제공해준다는 보장은 없습니다.

그래서 v1.37 업그레이드에서의 현실적인 결론은 이렇습니다.

- Extended Resource GA는 “전환 비용을 낮추는 안전장치”로 먼저 쓴다.
- NUMA는 표준 속성 이름으로 맞추되, 강제 정책은 속성 누락(-1/omit) 분포를 보고 단계적으로 건다.
- device taints와 metadata는 운영 체계에 편입하되, 멀티테넌시/RBAC/정보 노출의 경계를 명시적으로 그어야 한다.

## 참고 자료

- [Kubernetes v1.37: DRA Updates](https://kubernetes.io/blog/2026/09/03/kubernetes-v1-37-dra-updates/)
- [Kubernetes v1.37 릴리스 블로그](https://kubernetes.io/blog/2026/08/26/kubernetes-v1-37-release/)
- [DRA API Objects](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/dra-api/)
- [Feature Gates](https://kubernetes.io/docs/reference/command-line-tools-reference/feature-gates/)
- [Standard Device Attributes for Dynamic Resource Allocation](https://kubernetes.io/docs/reference/node/dra-standard-device-attributes/)
- [Device Taints and Tolerations](https://kubernetes.io/docs/concepts/resource-management/dynamic-resource-allocation/device-taints/)
- [DeviceTaintRule API 레퍼런스](https://kubernetes.io/docs/reference/kubernetes-api/resource/device-taint-rule-v1/)
- [Access DRA Device Metadata](https://kubernetes.io/docs/tasks/configure-pod-container/assign-resources/access-dra-device-metadata/)
- [Hardening Guide - Dynamic Resource Allocation](https://kubernetes.io/docs/concepts/security/hardening-guide/dynamic-resource-allocation/)
- [KEP-5004: DRA Extended Resource](https://github.com/kubernetes/enhancements/blob/master/keps/sig-scheduling/5004-dra-extended-resource/README.md)
- [KEP-6072: DRA standard numaNode attribute](https://github.com/kubernetes/enhancements/blob/master/keps/sig-node/6072-dra-standard-numanode/README.md)
- [KEP-5491: DRA list types for attributes](https://www.kubernetes.dev/resources/keps/5491/)
- [DRA Driver for NVIDIA GPUs: ResourceSlice device attributes](https://dra-driver-nvidia-gpu.sigs.k8s.io/docs/reference/resourceslice-attributes/)
- [GPU 오토스케일링으로 LLM 서빙 비용을 줄이는 Kubernetes 패턴(DRA·KEDA·vLLM·llm-d)](https://daewooki.github.io/posts/gpu-llm-2026-8-kubernetes-drakedavllmllm-1/)
- [GPU가 병목인 LLM 서빙: Kubernetes 오토스케일링 조합](https://daewooki.github.io/posts/gpu-llm-kubernetes-2026-6-2/)
- [Kubernetes·Docker·클라우드 네이티브 업그레이드 압박 맥락](https://daewooki.github.io/posts/2025-12-kubernetesdocker-1/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
