---
title: "Kubernetes Pod-Level Resource Managers: 사이드카와 공존하는 NUMA·전용 코어 설계"
description: "v1.37에서 Beta로 올라온 Pod-Level Resource Managers를 .spec.resources 중심으로 설계하고 PodResources gRPC로 검증합니다."
date: 2026-09-22 10:08:13 +0900
categories: ["DevOps", "Kubernetes"]
tags: ["kubernetes", "kubelet", "numa", "cpu-manager", "topology-manager", "podresources-grpc"]
render_with_liquid: false
---

성능 민감 워크로드를 Kubernetes에 올릴 때 가장 자주 부딪히는 벽이 멀티 컨테이너 Pod입니다. 메인 컨테이너는 전용 코어, NUMA locality, memory affinity가 필요한데, 옆에 붙은 사이드카(telemetry, logging, service mesh)가 그 전제 자체를 깨버립니다. 

Kubernetes v1.37에서 Pod-Level Resource Managers가 Beta로 승격되면서(기본 비활성) 이 문제가 kubelet의 기본 메커니즘 안에서 정리되기 시작했습니다. 2026-09-15에 올라온 Kubernetes 공식 블로그 글이 그 요지를 잘 요약합니다. 사이드카 때문에 integer CPU를 억지로 주거나, 아예 NUMA alignment를 포기해야 했던 이분법을 깨고, Pod 단위로 잡은 예산 안에서 일부 컨테이너만 exclusive slice를 받고 나머지는 Pod 내부 shared pool로 흘려보내는 모델을 kubelet이 지원합니다.[^1]

이 글은 feature gate 켜는 방법을 넘어, `.spec.resources` 중심으로 Pod를 다시 설계했을 때 CPU Manager / Memory Manager / Topology Manager의 배치 판단이 어떻게 달라지는지, 그리고 그 결과를 PodResources gRPC로 어떻게 관측하는지까지 한 번에 연결합니다.

## 사이드카가 전용 코어·NUMA를 망가뜨리는 이유가 kubelet의 모델에 있다
전통적으로 kubelet resource manager들은 container 단위로 움직였습니다. CPU pinning(Static CPU Manager)과 Memory Manager(Static)는 QoS가 Guaranteed인 컨테이너를 대상으로 exclusive 할당을 하고, Topology Manager는 각 hint provider(CPU/Device/Memory)가 낸 힌트를 조합해 NUMA alignment를 맞춥니다.

문제는 사이드카가 붙는 순간, Pod 전체가 사실상 하나의 성능 단위로 동작한다는 점입니다.

- 메인 컨테이너만 전용 코어를 받아도, 사이드카가 다른 NUMA node에서 돌면 cross-NUMA 메모리 접근/캐시 미스가 늘어 메인 성능이 흔들립니다.
- 그래서 single-numa-node 같은 강한 정책을 걸면, Pod 안의 모든 컨테이너가 Guaranteed가 아니면(혹은 integer CPU를 못 맞추면) 아예 admission 단계에서 튕기거나, NUMA alignment를 포기한 채 들어가게 됩니다.
- 결국 운영자는 사이드카에도 억지로 `requests=limits`를 맞춰 전용 코어를 주게 되는데, 이게 코어 낭비로 직결됩니다.

공식 문서도 이전 모델을 사실상 all-or-nothing로 설명합니다. exclusive NUMA-aligned 리소스를 받으려면 Pod의 모든 컨테이너가 Guaranteed여야 했고, 사이드카가 있는 현대 워크로드에서는 이 조건이 낭비를 강제했습니다.[^2]

내 경우, 대형 JVM(혹은 low-latency gRPC 서버)과 OTel Collector, log forwarder가 같은 Pod에 들어가는 패턴이 많았는데, 사이드카에 전용 코어를 주는 순간 노드 utilization이 급격히 나빠졌습니다. 반대로 사이드카를 BestEffort로 두면 메인의 NUMA locality가 깨지고 tail latency가 튀는 경우가 있었습니다.

## v1.37 Pod-Level Resource Managers가 바꾼 경계: Pod 예산과 Pod shared pool
Pod-Level Resource Managers는 Pod-level resource specification(KEP-2837 계열) 위에, kubelet의 Topology/CPU/Memory manager가 Pod 단위 리소스 선언을 직접 읽고 배치 결정을 내릴 수 있게 확장한 것입니다. v1.37에서 Beta가 되었지만 기본은 꺼져 있고, `PodLevelResources`와 `PodLevelResourceManagers`를 함께 켜야 합니다.[^2]

핵심은 PodSpec에 새로 생긴 `.spec.resources`를 Pod의 총 예산으로 보고, 그 예산을 내부에서 나누는 것입니다.

- `.spec.resources.requests/limits`: Pod 전체에 대한 요청/상한
- container `.resources`: 그 중 일부를 독점(exclusive slice)으로 떼어가고 싶은 컨테이너의 선언

문서에서 이 나뉨을 **Pod shared pool**이라는 개념으로 명확히 정의합니다. Pod에 할당된 리소스 중 exclusive로 떼고 남은 부분이 shared pool이 되고, 이 풀은 Pod 내부 컨테이너끼리는 공유하지만 node-wide shared pool과는 격리됩니다.[^2]

여기서 중요한 설계 포인트가 두 가지 생깁니다.

1) Pod 단위로 NUMA alignment를 한 번만 하고(특히 topologyManagerScope=pod), 그 안에서 쪼갤 수 있다.
2) sidecar는 Guaranteed로 만들지 않아도, Pod 내부 shared pool에 남게 할 수 있다.

공식 튜토리얼은 topologyManagerScope를 `pod`로 두면 kubelet이 `.spec.resources`를 기준으로 Pod 전체를 single NUMA node로 맞춘 뒤, Guaranteed 컨테이너는 exclusive slice를 받고 나머지는 shared pool을 쓴다고 설명합니다.[^3]

반대로 scope를 `container`로 두면, Pod 예산은 상한선으로만 쓰고 특정 컨테이너만 node allocatable에서 직접 exclusive를 받고, 나머지는 node-wide shared pool에서 돈다고 설명합니다(예산은 여전히 Pod limit으로 전체 consumption을 캡).[^2]

이 두 모드가 실제 운영 설계를 갈라놓습니다.

## `.spec.resources` 중심으로 Pod를 다시 설계하면, 배치의 기본 단위가 달라진다
Pod-Level Resource Managers를 켠 뒤부터는 컨테이너별 requests/limits 합으로 Pod의 성격을 만들기보다, Pod 예산을 먼저 정하고 그 안에서 exclusive 컨테이너만 도려내는 방식이 자연스럽습니다.

### pod scope: 사이드카도 NUMA 안에 묶고, 코어는 안 낭비한다
pod scope는 메인+사이드카를 한 NUMA node에 묶어야 하는 경우에 맞습니다.

- 예: 대형 JVM이 NIC/GPU와 locality를 강하게 타고, 사이드카가 같은 process namespace / loopback 경로로 데이터를 주고받는 구조
- 목표: Pod 전체가 single NUMA로 붙되, 메인만 전용 코어를 받고 사이드카는 남는 코어에서 공유

여기서 `.spec.resources`는 Pod bubble(문서 표현으로는 Pod level budget)에 해당합니다. 메인은 `requests=limits`로 Guaranteed를 만들고 integer CPU를 요청하면 Static CPU Manager가 exclusive 할당 대상으로 봅니다. v1.37 코드에서도, Pod-level 리소스를 쓰는 Pod의 컨테이너가 exclusive CPU를 받으려면 container가 Guaranteed 동등 조건을 만족해야 한다는 체크가 들어가 있습니다.[^4]

또 하나의 중요한 제약이 생깁니다. shared pool이 필요한 컨테이너가 하나라도 있는데 exclusive 컨테이너들의 합이 Pod 예산을 정확히 다 먹어버리면, kubelet이 admission에서 거부합니다. 문서에 아예 empty shared pool restriction으로 정리되어 있고, CPU뿐 아니라 memory에도 동일한 검증이 적용됩니다.[^2]

이 제약은 설계에 영향을 줍니다.

- 메인이 3코어, metrics가 1코어를 전용으로 가져가면(총 4) logging이 shared pool을 요구하는 순간 Pod가 거부됩니다.
- 즉, sidecar를 shared pool로 보내려면 Pod 예산에서 반드시 여유를 남겨야 합니다.

또 다른 트레이드오프도 문서에 명시됩니다. pod scope에서 Pod 예산을 과하게 잡으면, 그 남는 리소스는 Pod가 살아있는 동안 그대로 예약되어 낭비될 수 있습니다.[^2]

### container scope: 인프라 사이드카만 NUMA·전용, 나머지는 일반 풀로
container scope는 Pod 안 컨테이너들의 운명을 반드시 묶지 않아도 되는 경우에 맞습니다.

- 예: DPDK/특정 NIC 접근이 필요한 인프라 사이드카만 NUMA alignment가 필요하고, 워커 프로세스는 일반 shared pool에서 돌아도 되는 구조
- 목표: 필요한 컨테이너만 exclusive + NUMA, 나머지는 node-wide shared pool

공식 문서는 container scope에서 “exclusive 컨테이너는 컨테이너 레벨로만 보고되고(Pod-level은 비움), shared pool 컨테이너는 node shared pool에서 돈다”고 설명합니다.[^5]

이 모드는 sidecar가 메인을 방해하지 않게 분리하기 쉽지만, 메인과 sidecar를 같은 NUMA로 묶는 효과는 약해질 수 있습니다. 그래서 low-latency 메인+sidecar 조합에는 pod scope가 더 직관적이었습니다.

## kubelet과 클러스터 설정: feature gate가 전부가 아니라 policy 조합이 핵심이다
이 기능은 kubelet 내부에서만 동작하는 부분이 크지만, `.spec.resources`를 API로 받아들이고 워크로드가 실제로 그 필드를 쓰려면 컨트롤 플레인과 워커 노드에서 feature gate를 함께 켜라고 공식 튜토리얼이 명시합니다.[^3]

그리고 리소스 매니저 정책 조합이 맞지 않으면 아무 일도 일어나지 않습니다. 개념 문서에서 이 기능이 구현된 범위를 명확히 제한합니다.

- CPU Manager: `static` 정책에서만 의미가 있습니다.
- Memory Manager: `Static` 정책에서만 의미가 있습니다.
- OS: Linux에서만 지원합니다.[^2]

Topology Manager 설정도 중요합니다. kubelet config API에서 topologyManagerScope는 `container` 또는 `pod`가 유효값이며 기본은 `container`입니다.[^6]

### kubelet config 예시 (pod scope)
아래는 systemd로 kubelet을 돌리는 노드에서 `/var/lib/kubelet/config.yaml`(환경마다 다름)에 들어갈 법한 현실적인 설정 조합입니다. 핵심은 featureGates + static policy + topologyManagerPolicy/scope를 동시에 맞추는 것입니다.

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration

featureGates:
  PodLevelResources: true
  PodLevelResourceManagers: true

cpuManagerPolicy: static
# 운영에서는 full physical core 강제를 켜는 경우가 많습니다.
# cpuManagerPolicyOptions:
#   full-pcpus-only: "true"

memoryManagerPolicy: Static

# Memory Manager Static은 reservedMemory가 사실상 필수입니다.
# (evictionHard 기본값 100Mi 때문에 더더욱)
reservedMemory:
  - numaNode: 0
    limits:
      memory: "1Gi"
  - numaNode: 1
    limits:
      memory: "1Gi"

topologyManagerPolicy: single-numa-node
topologyManagerScope: pod
```

reservedMemory 문법은 Memory Manager 문서에 예시가 그대로 있습니다. `numaNode`별로 `limits.memory`를 주는 구조입니다.[^7]

적용은 결국 kubelet 재시작이 필요합니다.

```bash
sudo systemctl restart kubelet
sudo systemctl status kubelet --no-pager
```

공식 튜토리얼도 동일하게 kubelet 재시작을 전제로 설명합니다.[^3]

### 운영에서 신경 써야 하는 downgrade/rollback 포인트
이 기능은 state checkpoint 파일 포맷과 엮입니다. 문서에 따르면 v1.36에서는 feature를 사용하면 checkpoint가 구버전 kubelet이 못 읽는 포맷으로 저장되어 downgrade 시 kubelet이 시작에 실패할 수 있었고, v1.37에서는 forward-compatible 포맷으로 이 문제가 완화되었다고 정리돼 있습니다.[^2]

즉, v1.37에서 켠 뒤 v1.36으로 내리는 시나리오는 “kubelet이 죽지는 않지만 pod-level 할당 정보는 복구되지 않는다” 쪽으로 위험이 옮겨갑니다. 이건 단순한 설정 토글이 아니라, 성능 프로파일 노드 풀을 운영한다면 노드 롤링/드레인 계획에 넣어야 하는 변화입니다.

KEP에도 enable/disable 절차와 downgrade 시 동작이 정리돼 있습니다(특히 gate는 kubelet 설정으로 제어).[^8]

## 실제 Pod 설계: 대형 JVM + OTel + Fluent Bit을 NUMA에 묶고, 코어는 메인에만 준다
여기서는 pod scope를 기준으로 설명합니다. 이유는 간단합니다. 내가 이 기능을 켜고 싶은 1순위는 “사이드카도 NUMA locality 안으로 묶고 싶은데, 사이드카에 전용 코어는 주기 싫다”는 케이스입니다.

### 목표 상태
- Pod 전체는 `.spec.resources`로 CPU/Memory 예산을 선언하고 single NUMA에 붙습니다.
- 메인 컨테이너만 `requests=limits`로 Guaranteed를 만족시키고 integer CPU를 받아 exclusive slice를 받습니다.
- OTel Collector, Fluent Bit은 container-level resources를 명시하지 않아(또는 Guaranteed를 만족시키지 않아) Pod shared pool로 들어갑니다.

공식 문서의 예시는 `pause` 이미지를 쓰지만, 여기서는 실제로 돌릴 수 있는 구성으로 바꿉니다. 다만 이미지/옵션은 조직 표준에 따라 바뀌어도 설계 포인트는 같습니다.

### Pod manifest 예시
아래 YAML에서 중요한 지점은 세 가지입니다.

1) `spec.resources`가 Pod-level 예산입니다.
2) `main`만 container-level로 Guaranteed를 만들어 exclusive 후보가 됩니다.
3) sidecar들은 자원 명세를 생략해 shared pool로 흘립니다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: jvm-with-sidecars
  namespace: plrm-demo
spec:
  # Pod-level 예산
  resources:
    requests:
      cpu: "6"
      memory: "12Gi"
    limits:
      cpu: "6"
      memory: "12Gi"

  containers:
    - name: main
      image: eclipse-temurin:21-jre
      command: ["bash", "-lc"]
      args:
        # 간단히 CPU를 태우고, 프로세스가 계속 살아있게 만듭니다.
        - |
          java -version
          echo "burn";
          while true; do
            python3 - <<'PY'
import time
x=0
for i in range(20000000):
  x+=i*i
print(x)
time.sleep(0.2)
PY
          done
      resources:
        requests:
          cpu: "4"
          memory: "8Gi"
        limits:
          cpu: "4"
          memory: "8Gi"

    - name: otel
      image: otel/opentelemetry-collector:0.127.0
      args: ["--config=/etc/otel/config.yaml"]
      volumeMounts:
        - name: otel-config
          mountPath: /etc/otel

    - name: fluentbit
      image: fluent/fluent-bit:3.1
      args: ["-i", "dummy", "-o", "stdout"]

  volumes:
    - name: otel-config
      configMap:
        name: otel-collector-config
```

이 예시에서 `.spec.resources.cpu=6`인데 메인이 4를 독점으로 가져가고, sidecar들이 남은 2를 shared pool에서 공유하는 구성이 됩니다. 공식 튜토리얼이 설명한 패턴을 그대로 현실 이미지로 옮긴 것입니다.[^3]

운영에서 흔히 하는 실수는 `.spec.resources`를 메인의 exclusive 요구량과 똑같이 맞추는 것입니다. 그러면 sidecar가 shared pool로 들어갈 때 empty shared pool restriction에 걸려 admission에서 거부될 수 있습니다.[^2]

### 생성/확인 명령

```bash
kubectl create ns plrm-demo
kubectl -n plrm-demo create configmap otel-collector-config --from-file=config.yaml=./otel-config.yaml
kubectl -n plrm-demo apply -f ./pod.yaml

kubectl -n plrm-demo get pod -o wide
kubectl -n plrm-demo describe pod jvm-with-sidecars
```

여기까지는 평범한 Pod처럼 보이지만, 실제 핵심은 kubelet이 어떤 cpuset/memory topology를 할당했는지입니다. 그 검증 지점이 PodResources gRPC입니다.

## PodResources gRPC로 검증: Pod 단위 cpu_ids/memory가 보이는 순간이 전환점이다
PodResources gRPC는 원래 device assignment 관측을 위해 시작됐고, kubelet이 UNIX socket(`/var/lib/kubelet/pod-resources/kubelet.sock`)으로 제공합니다. KEP-606이 이 경로와 List API를 설명합니다.[^9]

v1.37에서는 `PodLevelResourceManagers`가 켜져 있으면 PodResources 응답에 “Pod-level cpu_ids / memory”가 포함됩니다. 공식 블로그도 Beta 변경점으로 이걸 콕 집어 말합니다.[^1]

또 proto 정의를 보면 `ContainerResources`에는 `cpu_ids`와 `memory`가 있고, memory는 `ContainerMemory`(type/size/topology) 형태로 내려옵니다.[^10]

### 노드에서 grpcurl로 직접 보기
가장 단순한 방법은 노드에서 직접 `grpcurl`을 실행하는 것입니다. PodResourcesLister v1의 List를 때리면 됩니다.

```bash
# 노드에서
sudo grpcurl -plaintext unix:///var/lib/kubelet/pod-resources/kubelet.sock \
  podresources.v1.PodResourcesLister/List
```

`grpcurl` 커맨드에서 unix socket을 저렇게 쓰는 예시는 Kubernetes 이슈에서 실제로 사용된 형태를 참고하면 됩니다.[^11]

### DaemonSet으로 관측 에이전트 만들 때의 마운트 함정
운영에서는 노드에 직접 들어가서 치기보다, node-local agent(DaemonSet)가 PodResources를 읽어 메트릭을 만들거나 검증합니다.

이때 kubelet.sock 파일 자체를 마운트하면 kubelet 재시작 시 inode가 바뀌어 연결이 끊길 수 있습니다. Kubernetes 공식 Device Plugins 문서가 “socket 파일 대신 디렉터리(`/var/lib/kubelet/pod-resources/`)를 마운트하라”고 명시합니다.[^12]

이 디테일이 별거 아닌 것 같아도, 성능 노드 풀에서 kubelet을 롤링 재시작할 때 관측이 동시에 멎어버리면 장애 대응이 어려워집니다.

### pod scope에서 Pod-level cpu_ids/memory가 어떻게 보이는가
v1.37 reference 문서가 표로 정리해둔 내용이 실전에서 가장 유용합니다.

- pod scope에서 exclusive 컨테이너가 존재하면, Pod-level `cpu_ids`/`memory`가 “Pod 전체 할당”으로 채워지고, 컨테이너 레벨에는 각 컨테이너의 subset이 채워집니다.
- container scope에서는 Pod-level 필드는 비고, 컨테이너 레벨에만 값이 들어옵니다.
- shared pool 컨테이너는 컨테이너 레벨 `cpu_ids`/`memory`가 비어 있는 게 정상입니다(공유니까).[^5]

이게 의미하는 바는 명확합니다.

- 예전에는 “메인은 전용 코어를 받았는데 sidecar는 어디서 도는지”를 확실히 정의/관측하기 어려웠습니다.
- 이제는 “Pod 예산이 어느 NUMA node에 묶였는지”가 Pod-level로 떨어지고, “메인이 실제로 어떤 core set을 받았는지”가 container-level로 동시에 떨어집니다.
- 모니터링 에이전트 입장에서는 double counting을 피하기 쉬워집니다. Pod-level 항목과 container-level 항목이 의도적으로 겹치거나 비도록 설계돼 있다는 설명이 proto 코멘트에도 들어 있습니다.[^10]

### 예상 출력 형태(형태만)
아래는 실제 코어 ID가 노드마다 달라서 값은 예시로만 봐야 하지만, “어떤 필드가 채워지고 비는지”는 그대로 나옵니다.

```json
{
  "podResources": [
    {
      "name": "jvm-with-sidecars",
      "namespace": "plrm-demo",
      "cpuIds": [2,3,4,5,6,7],
      "memory": [
        {"memoryType":"memory","size":"12884901888","topology":{"nodes":[{"ID":0}]}}
      ],
      "containers": [
        {"name":"main","cpuIds":[2,3,4,5],"memory":[...]},
        {"name":"otel","cpuIds":[],"memory":[]},
        {"name":"fluentbit","cpuIds":[],"memory":[]}
      ]
    }
  ]
}
```

여기서 sidecar들의 `cpuIds`가 빈 게 오히려 목표한 상태입니다. 이 상태에서 sidecar는 Pod shared pool로 들어가고, 메인은 전용 slice를 받습니다.

## CPU/Memory/Topology Manager 관점에서 해석: 어떤 순서로 무슨 결정을 하나
문서만 보면 “pod 예산 → slice 분할”로 끝나지만, 운영에서 중요한 건 장애/성능 이슈가 났을 때 어느 매니저의 결정이 원인인지 가르는 것입니다.

### Topology Manager: 정렬을 Pod로 한 번만 하느냐, 컨테이너마다 하느냐
Topology Manager는 여러 hint provider의 힌트를 조합해 “어느 NUMA node에 붙일지”를 결정하는 소스 오브 트루스 역할을 한다고 정리돼 있습니다.[^13]

pod scope로 바꾸는 순간, 정렬의 기본 입력이 “컨테이너들의 합”이 아니라 `.spec.resources`가 됩니다. 튜토리얼이 “Toplogy Manager가 `.spec.resources`를 평가해서 Pod를 single NUMA에 할당한다”고 명시합니다.[^3]

이 차이가 사이드카 문제를 푸는 이유입니다.

- 예전: sidecar가 Guaranteed가 아니면 힌트가 약해지고, 결국 메인이 원하던 정렬이 흔들립니다.
- 지금: Pod 예산으로 정렬을 먼저 확정하고, 그 안에서 메인만 독점 slice를 받으니 sidecar 때문에 정렬이 깨질 여지가 줄어듭니다.

### CPU Manager(static): exclusive slice와 shared pool의 경계가 생긴다
개념 문서는 mixed workload에서 kubelet이 isolation을 다르게 enforce한다고 정리합니다.

- exclusive 컨테이너: CPU CFS quota를 꺼서 throttling 없이 전용 코어에서 돌게 합니다.
- Pod shared pool 컨테이너: CFS quota를 켜서 leftover Pod budget을 넘지 않게 합니다.[^2]

이 설명은 “전용 코어를 받았는데도 limit 때문에 throttle 걸린다” 같은 흔한 오해를 정리하는 데 도움이 됩니다. static policy에서의 전용 코어는 결국 cpuset 기반이고, shared pool은 quota 기반으로 묶이는 쪽이 자연스럽습니다.

또, 코드 레벨에서도 Pod-level 리소스를 쓰는 Pod에 대해 feature gate가 꺼져 있으면 allocation을 스킵한다는 로그/조건이 들어가 있습니다. 즉, YAML만 바꿔서는 아무 일도 안 일어날 수 있고, kubelet gate와 policy 조합이 맞아야 합니다.[^4]

### Memory Manager(Static): reservedMemory와 NUMA 그룹이 현실적인 발목을 잡는다
Memory Manager Static은 운영 난이도가 CPU보다 높습니다. 문서가 “Static policy면 reservedMemory 구성이 필수”라고 못 박고, evictionHard 기본값 때문에 더더욱 reservedMemory 없이는 시작이 안 날 수 있음을 설명합니다.[^7]

Pod-level resource managers를 켰을 때 메모리까지 NUMA locality를 제대로 챙기려면, 결국 reservedMemory 설계부터 노드 프로파일로 굳혀야 합니다. CPU는 비교적 쉽게 pinning을 체감하지만, 메모리는 잘못하면 “시작도 안 됨”으로 나타납니다.

## 함정과 트레이드오프: 켜기 전에 알아야 하는 것들
이 기능이 Beta라고 해서 무조건 켜기 좋은 건 아닙니다. 특히 성능 노드는 한 번의 설정 실수로 node admission이 흔들릴 수 있습니다.

### 1) 기본 비활성(Beta지만 off)
Kubernetes v1.37에서 Beta로 승격되었지만 feature gate는 opt-in이며 기본은 꺼져 있습니다.[^1]

이건 메시지 하나로 끝납니다. “운영 편의성이 이미 GA 수준”이면 default on으로 갔을 텐데, 아직은 노드 정책 조합과 관측 체계가 필요한 기능이라는 뜻입니다.

### 2) empty shared pool restriction은 설계 단계에서 잡아야 한다
Pod 예산을 메인 exclusive 합과 같게 잡는 습관이 있으면, sidecar가 shared pool을 요구하는 순간 kubelet admission에서 거부될 수 있습니다. 문서에 명시된 제한이라서, 나중에 튜닝으로 해결할 문제가 아닙니다.[^2]

### 3) pod scope는 낭비를 유발할 수 있다
pod scope에서 Pod 예산을 크게 잡아두고 sidecar가 그걸 다 쓰지 않으면, 남는 리소스는 Pod가 종료될 때까지 예약된 채로 남아 낭비될 수 있다고 문서가 경고합니다.[^2]

성능 노드에서 이건 비용 문제로 직결됩니다. “sidecar 때문에 코어 낭비”를 없애려고 켰는데, “Pod 예산 과대 책정 때문에 낭비”로 바뀌면 본말전도입니다.

### 4) 관측 없이 켜면 문제를 더 늦게 발견한다
이 기능은 결과가 cgroup/cpuset/NUMA affinity로 흩어져 나타납니다. PodResources gRPC로 Pod-level과 container-level을 동시에 읽어야 설계가 맞았는지 판단할 수 있습니다. v1.37에서 PodResources가 Pod-level 필드를 보고하는 게 Beta 변경점으로 들어온 이유가 여기에 있습니다.[^1]

관측을 붙이지 않고 gate만 켜면, “뭔가 빨라진 것 같기도 하고 아닌 것 같기도 한” 상태로 끝나기 쉽습니다.

## 도입 판단 기준: 어떤 노드 풀에, 어떤 scope로, 어떤 형태의 Pod에 쓸 것인가
내 기준에서는 이 기능의 가치는 NUMA와 전용 코어가 의미 있는 노드에서만 발생합니다. 공식 튜토리얼도 NUMA 토폴로지가 있는 worker node를 전제로 잡습니다.[^3]

다음 조건 중 2개 이상이면 켤 이유가 생깁니다.

- 메인 워크로드가 latency-sensitive이고, static CPU pinning을 이미 쓰고 있다.
- sidecar가 반드시 같은 Pod에 있어야 한다(보안/네트워크/배포 단위 때문에).
- node 당 NUMA node가 여러 개고, cross-NUMA로 인한 성능 흔들림을 이미 겪었다.
- GPU 노드처럼 locality가 중요한 리소스를 다루고 있고, sidecar 때문에 정렬을 포기했던 적이 있다.

GPU 쪽은 DRA 변화와 같이 보는 게 맞습니다. 예전 글에서 GPU 운영 관점의 DRA 업데이트를 정리해뒀는데, Pod 단위 리소스 설계는 결국 같은 방향(노드 로컬에서 정밀하게 “무엇을 어디에 붙일지” 통제)으로 수렴합니다.

- [Kubernetes 1.37 DRA 업데이트: GPU 운영팀이 보는 GA급 변화](https://daewooki.github.io/posts/kubernetes-dra-ga-gpu-ops/)

scope 선택은 이렇게 정리하는 편이 안전합니다.

- **pod scope**: 메인과 sidecar를 NUMA까지 한 덩어리로 묶고 싶고, sidecar에 전용 코어는 주기 싫을 때.
- container scope: 특정 컨테이너만 NUMA/exclusive가 필요하고, 나머지는 node-wide shared pool로 보내도 될 때.

결국 이 기능은 “사이드카 때문에 성능 노드 설계를 포기하거나, 코어를 낭비하는” 문제를 kubelet의 모델 안에서 정식으로 해결하는 첫 번째 큰 단추입니다. 다만 `.spec.resources`로 Pod 예산을 먼저 설계하고, empty shared pool 같은 제약을 스펙 단계에서 충족시키며, PodResources gRPC로 배치 결과를 수치로 확인하는 체계를 같이 가져가야 효과가 납니다.

## 참고 자료
- [Kubernetes v1.37: Pod-Level Resource Managers graduated to Beta](https://kubernetes.io/blog/2026/09/15/kubernetes-v1-37-pod-level-resource-managers-beta/)
- [Pod-level resource managers 개념 문서](https://kubernetes.io/docs/concepts/resource-management/pod-level-resource-managers/)
- [Use Pod-Level Resources with kubelet Resource Managers 튜토리얼](https://kubernetes.io/docs/tutorials/cluster-management/use-pod-level-resource-managers/)
- [Pod-level resource managers reference](https://kubernetes.io/docs/reference/node/pod-level-resource-managers/)
- [Kubelet Configuration (v1beta1) - topologyManagerScope](https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/)
- [Control Memory Management Policies on a Node - reservedMemory 문법](https://kubernetes.io/docs/tasks/administer-cluster/memory-manager/)
- [Device Plugins 문서 - PodResources socket 마운트 권장](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/)
- [PodResources gRPC v1 api.proto](https://github.com/kubernetes/kubernetes/blob/master/staging/src/k8s.io/kubelet/pkg/apis/podresources/v1/api.proto)
- [KEP-5526 Pod-Level Resource Managers](https://www.kubernetes.dev/resources/keps/5526/)
- [Topology Manager 개요](https://kubernetes.io/docs/tasks/administer-cluster/topology-manager/)
- [Kubernetes 1.37 DRA 업데이트: GPU 운영팀이 보는 GA급 변화](https://daewooki.github.io/posts/kubernetes-dra-ga-gpu-ops/)

[^1]: <https://kubernetes.io/blog/2026/09/15/kubernetes-v1-37-pod-level-resource-managers-beta/>
[^2]: <https://kubernetes.io/docs/concepts/resource-management/pod-level-resource-managers/>
[^3]: <https://kubernetes.io/docs/tutorials/cluster-management/use-pod-level-resource-managers/>
[^4]: <https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/cm/cpumanager/policy_static.go>
[^5]: <https://kubernetes.io/docs/reference/node/pod-level-resource-managers/>
[^6]: <https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/>
[^7]: <https://kubernetes.io/docs/tasks/administer-cluster/memory-manager/>
[^8]: <https://www.kubernetes.dev/resources/keps/5526/>
[^9]: <https://www.kubernetes.dev/resources/keps/606/>
[^10]: <https://github.com/kubernetes/kubernetes/blob/master/staging/src/k8s.io/kubelet/pkg/apis/podresources/v1/api.proto>
[^11]: <https://github.com/kubernetes/kubernetes/issues/141335>
[^12]: <https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/>
[^13]: <https://kubernetes.io/docs/tasks/administer-cluster/topology-manager/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
