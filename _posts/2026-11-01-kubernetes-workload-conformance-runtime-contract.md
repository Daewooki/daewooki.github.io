---
title: "Kubernetes Workload Conformance로 만드는 워크로드 계약서"
description: "Workload Conformance WG의 목표를 조직 내부 표준으로 번역해, 골든패스·정책·템플릿을 하나의 계약으로 묶는 방법을 정리합니다."
date: 2026-11-01 11:26:56 +0900
categories: ["Architecture", "Kubernetes"]
tags: ["kubernetes", "platform-engineering", "conformance", "policy-as-code", "golden-path", "opa-rego"]
render_with_liquid: false
---

## WG 신설이 의미하는 것: 클러스터가 아니라 워크로드를 검증한다

2026-10-27(화)에 Kubernetes 프로젝트가 **Workload Conformance** Working Group(WG) 신설을 공식 블로그로 공지했습니다. 오늘이 2026-11-01 KST라면, 공지 시점은 KST 기준으로 5일 전입니다(사용자 입력에는 7일로 되어 있는데, 날짜만 놓고 보면 10/27 → 11/01은 5일입니다). 공지의 핵심은 간단합니다. 기존의 conformance는 “클러스터가 Kubernetes API와 동작을 만족하는가”에 초점이 있었고, 그 위에서 돌아가는 “워크로드가 런타임에서 어떤 기대 동작을 가져야 하는가”에 대해 커뮤니티 공통의, 반복 가능한 표준과 테스트가 없다는 문제의식입니다.[^1]

WG가 말하는 deliverable도 꽤 명확합니다.

- Kubernetes minor version별로 워크로드 런타임 동작에 대한 specification을 만든다.
- 각 requirement를 “실행 중인 워크로드”에 대해 테스트할 수 있는 방법을 정의한다.
- 그 테스트를 구현한 upstream conformance tooling을 만든다.

그리고 무엇보다도 “subjective한 규칙은 스펙에 들어가지 않는다, objective test가 있어야만 requirement가 된다”를 초기에 못 박습니다.[^1]

이 지점이 플랫폼 팀에게는 그냥 커뮤니티 뉴스가 아니라, 내부 표준화를 재정렬할 명분이 됩니다. 내부에서 이미 하고 있는 일(Helm chart 템플릿, Backstage 골든패스, namespace baseline, OPA/Gatekeeper나 Kyverno, 각종 lint, 운영 체크리스트)을 “취향”이나 “운영자 경험칙”으로 남겨두면 조직이 커질수록 설명 비용이 커집니다. 반대로, 계약으로 정리해 두면 “왜 이게 필요한가”가 기술 부채가 아니라 설계 선택으로 남습니다.

WG의 스펙은 아직 작성 중이고, 당연히 지금 당장 가져다 쓸 문서가 있는 단계는 아닙니다. WG charter 자체도 “스펙과 툴링은 SIG Architecture 산하 subproject로 넘어가며, WG는 cross-SIG forum이고 코드를 소유하지 않는다”는 구조를 갖습니다.[^2] 이 말은 즉, 당분간은 각 조직이 자기 식으로 ‘사실상 표준’을 운영할 텐데, 그 ‘사실상 표준’을 커뮤니티가 따라갈 수 있는 형태로 만들겠다는 선언에 가깝습니다.

## “워크로드 런타임 계약”으로 번역하면 플랫폼 팀의 일이 된다

WG charter는 scope를 이렇게 잡습니다.

- security posture
- disruption 상황에서의 operational resilience
- resource footprint
- networking
- storage
- API usage
- observability

그리고 “어떻게 실행되는가(how it runs)”를 다루지, “무엇을 하는가(what it does)”는 다루지 않는다고 선을 긋습니다. 워크로드의 비즈니스 로직은 out of scope입니다.[^2]

이걸 조직 내부로 가져오면, 정의는 더 단순해집니다.

- 개발 팀: “이 워크로드는 이런 런타임 계약을 만족한다”를 선언한다.
- 플랫폼 팀: “이 플랫폼은 이 계약을 만족하는 워크로드를 예측 가능하게 운영한다”를 보장한다.

여기서 계약이 다루는 건 대부분 ‘리소스/라이프사이클/경계조건’입니다. 예를 들면 아래 같은 질문들입니다.

- Restart: crash loop가 났을 때 어떤 backoff/복구가 가능한가, 최소 replica는 얼마인가
- Termination: SIGTERM을 처리하는가, 종료 grace period는 충분한가, node drain에서 안전한가
- Resource: requests/limits는 있는가, QoS class는 무엇이 되는가
- Network: 어떤 포트/프로토콜이 열려야 하는가, egress는 어디까지 나가는가
- Volume: 데이터는 ephemeral인가 persistent인가, access mode는 무엇이 필요한가

이 범주는 WG가 공식 블로그에서 예시로 든 “node drain에서 깨져서 처음 알게 된다”, “deprecated API에 의존한다”, “불필요하게 privileged하다”, “요청만 크게 잡고 쓰지 않는다”와도 정확히 맞물립니다.[^1]

내가 플랫폼 팀 역할을 오래 하면서 느낀 건, 대부분의 골든패스는 결국 “계약을 내장한 템플릿”입니다. 문제는 계약이 문서/정책/템플릿/운영자 지식으로 흩어져 있어서, 새 팀이 들어올 때마다 같은 내용을 다른 말로 반복하게 된다는 점입니다. 워크로드 conformance 시도가 좋은 핑계가 되는 이유가 여기 있습니다.

## 계약서를 만들 때 먼저 정해야 하는 경계: in-scope / out-of-scope

WG charter는 out-of-scope를 꽤 강하게 선언합니다.

- certification program을 운영하지 않는다(CNCF 범위)
- 워크로드 내부 비즈니스 로직은 테스트하지 않는다
- 특정 packaging/배포 포맷(Helm, Operator 등)을 강제하지 않는다
- 특정 policy engine/스캐너/벤더 툴을 강제하지 않는다
- cluster infrastructure layer를 다시 테스트하지 않는다(기존 conformance가 커버)
- AI/ML readiness 같은 “클러스터가 어떤 클래스의 워크로드를 돌릴 수 있는가”는 다른 프로그램이 커버

[^2]

조직 내부 계약서에서도 이 경계를 그대로 가져오는 게 좋습니다. 특히 아래 두 가지를 혼동하면 계약서가 바로 무너집니다.

1) “우리 서비스는 결제 정합성이 중요하다” 같은 비즈니스 요구를 계약서에 넣는 순간, 플랫폼 팀이 검증할 수 없는 문장이 됩니다. 계약서는 runtime behavior로 번역 가능한 문장이어야 합니다.

2) “우리 클러스터는 어떤 CNI/CSI를 쓰니까 이건 된다/안 된다”를 계약서에 박아 넣으면, 계약이 워크로드가 아니라 인프라 구현에 붙어 버립니다. WG에서도 core infra component(CNI, CSI driver, CoreDNS 같은 것)를 어떻게 다룰지 논의가 있었는데, 결론은 기능을 테스트하는 게 아니라 shape/런타임 특성을 다룬다는 선을 유지하려는 방향입니다.[^2]

내가 권하는 내부 경계는 다음입니다.

- 계약서: 워크로드가 “스스로” 지켜야 하는 것(명시/선언 가능, 검증 가능)
- 플랫폼 표준: 플랫폼이 “보장”하는 것(예: NetworkPolicy enforcement 유무, default StorageClass, admission policy 레벨)
- 워크로드별 예외: 계약서에 적는 게 아니라 예외 등록 프로세스로 빼는 것(승인/만료 포함)

이렇게 나누면, 계약서가 조직의 운영 체계를 삼키지 않고, 오히려 운영 체계를 정리하는 레일이 됩니다.

## ‘워크로드 런타임 계약서’ 템플릿: 문장을 테스트 가능한 단위로 쪼갠다

WG가 요구하는 “objective test가 있어야 requirement가 된다”는 원칙을 내부에도 그대로 적용하는 게 좋습니다. 문장 형태는 “~해야 한다”가 아니라 “~로 검증된다”에 가까워야 합니다.

아래는 내가 실제로 템플릿을 만든다면 넣을 섹션들입니다. 전부 워크로드 실행 시점의 관찰/검증으로 떨어져야 합니다.

### 1) Kubernetes API / 버전 호환 계약

- 사용하는 resource의 apiVersion이 Kubernetes deprecation policy를 위반하지 않는다.
- deprecated API 사용을 모니터링할 수 있는 신호(예: audit annotation, apiserver metric)를 운영 표준으로 둔다.

deprecation 자체는 Kubernetes가 강한 호환성 약속을 하되, 정책에 따라 제거가 발생한다는 것을 전제로 합니다.[^3]

이 파트는 예전 글에서 다룬 “업그레이드 압박”과 연결됩니다. (같은 내용을 반복하진 않겠습니다.)

- [Kubernetes·Docker·클라우드 네이티브 판이 “업그레이드 압박” 국면으로 들어간 이유](https://daewooki.github.io/posts/2025-12-kubernetesdocker-1/)

### 2) Lifecycle / 종료 계약 (drain, rollout, preStop)

Pod termination은 단순히 “프로세스 죽임”이 아니라, kubelet이 SIGTERM을 보내고 grace period를 적용하며 preStop hook이 있다면 실행하는 식으로 단계가 있습니다.[^4]

계약서 문장 예시는 이런 형태가 됩니다.

- 워크로드는 SIGTERM을 수신하면 N초 이내에 신규 요청을 중단하고 진행 중 요청을 정리한다.
- terminationGracePeriodSeconds는 (서비스 유형별) 상한/하한을 가진다.
- readiness probe는 termination 시점에 엔드포인트에서 제거되는 흐름과 충돌하지 않게 설계한다.

이걸 플랫폼 표준으로 내리면, 결국 템플릿/정책으로 떨어집니다.

### 3) Disruption 계약 (PDB, replica, eviction)

node drain은 “자발적(voluntary) disruption”의 대표 케이스이고, Kubernetes 문서도 애플리케이션 오너가 PodDisruptionBudget(PDB)를 만들 것을 전제합니다.[^5]

계약서에서 내가 최소로 요구하는 건 다음입니다.

- Deployment/StatefulSet 등 controller를 쓰는 워크로드는 PDB가 존재한다.
- PDB가 drain을 영구적으로 막지 않도록(minAvailable=replicas 같은 실수 방지) 설계한다.
- 문서에서 권장하는 Unhealthy Pod Eviction Policy를 적용할지 여부를 조직 표준으로 결정한다(운영 철학에 따라 달라진다).[^5]

PDB를 표준화하면 좋은 점은 “업그레이드/노드 교체”가 곧바로 워크로드 품질 이슈를 드러내는 진단 도구로 바뀐다는 겁니다. 단, 아래에서 따로 쓰겠지만 PDB는 만능이 아니고, autoscaler/maintenance automation과 충돌도 잦습니다.

### 4) Resource 계약 (requests/limits, QoS, eviction)

Kubernetes는 Pod의 requests/limits 조합으로 QoS class(Guaranteed/Burstable/BestEffort)를 부여하고, 노드 자원 압박 시 eviction 우선순위에도 영향을 줍니다.[^6]

계약서에서는 “요청/제한을 넣어라” 같은 도덕 문장보다, 결과 중심이 낫습니다.

- 이 워크로드는 최소 Burstable 이상이어야 한다.
- latency-sensitive 서비스는 Guaranteed를 요구한다(혹은 반대로, Guaranteed는 비용이 크므로 예외만 허용한다).
- CPU limit은 기본 금지/기본 허용 등 조직 입장을 정하고, 예외는 티켓으로 남긴다.

이걸 표준으로 묶는 순간, 리소스 설정이 운영의 취향이 아니라 비용/안정성 트레이드오프가 됩니다.

### 5) Network 계약 (ingress/egress, isolation, 기본 거부)

NetworkPolicy는 Kubernetes 자체 API이지만, “기본적으로 pod는 egress non-isolated”이고, explicit deny 같은 표현은 모델상 제공되지 않는다는 제약이 있습니다.[^7]

그래서 계약서는 보통 아래 두 층으로 갈라집니다.

- 워크로드 선언: “나는 어디로 나가야 한다(egress destination set)” / “나는 누가 들어와야 한다(ingress source set)”를 명시
- 플랫폼 표준: “namespace default-deny + allow-list”를 enforce할지, 아니면 서비스 메시/egress gateway 같은 다른 통제로 갈지 결정

여기서 중요한 건, NetworkPolicy는 ‘표준 API’라도 실제 enforcement는 CNI 구현과 운영 표준에 붙어 있다는 점입니다. 계약서에는 “정책을 어떻게 구현하는가”가 아니라 “정책이 만족해야 하는 관찰 가능한 결과”를 써야 합니다.

### 6) Storage 계약 (PVC, access mode, binding, retention)

스토리지는 조직에서 가장 자주 사고 나는 영역인데, 이유는 간단합니다. “볼륨은 붙어야 한다”라는 문장은 너무 추상적이고, Kubernetes의 storage 모델은 명시해야 하는 선택지가 많습니다.

- PV/PVC accessModes는 매칭에 쓰이지만, 그 자체가 물리적 제약을 강제하지는 않는다는 점까지 문서에 명시돼 있습니다.[^8]
- ReadWriteOnce는 ‘단일 pod’가 아니라 ‘단일 node’ 관점이라는 함정을 자주 밟습니다(같은 node에서 여러 pod가 붙을 수 있음).[^9]
- StorageClass의 volumeBindingMode=WaitForFirstConsumer는 스케줄링과 바인딩 타이밍을 바꿉니다.[^10]
- StatefulSet은 volumeClaimTemplates와 PVC retention policy 같은 lifecycle 옵션이 있습니다.[^11]

계약서에 들어갈 문장 예시는 이런 형태가 됩니다.

- 이 워크로드는 RWO/RWX 중 무엇이 필요한가
- 스케줄링 지연을 허용하는가(WaitForFirstConsumer를 전제로 하는가)
- StatefulSet 삭제/스케일다운 시 PVC를 보존해야 하는가

### 7) Security posture 계약 (securityContext)

securityContext는 계약서에서 가장 “정책화”하기 쉬운 파트입니다. Kubernetes 문서에 runAsNonRoot, readOnlyRootFilesystem, capabilities drop/add 같은 필드가 매우 구체적으로 정리돼 있습니다.[^12]

여기서 중요한 건 “보안이 중요하다”가 아니라 “이 워크로드는 어떤 권한이 없어도 동작해야 한다”로 써야 한다는 점입니다.

- privileged 금지
- runAsNonRoot 강제
- readOnlyRootFilesystem 기본값
- 추가 capability 허용 목록

이런 문장들은 admission policy로 곧장 옮길 수 있고, 워크로드 팀 입장에서도 대응이 명확합니다.

### 8) Observability 계약 (로그/메트릭/상태)

WG charter에는 observability가 들어가 있습니다.[^2] 내부 계약서에서는 보통 아래를 강제합니다.

- readiness/liveness/startup probe의 존재 여부와 기준
- structured logging 포맷까지 강제할지 여부(강제하면 마찰이 크다)
- 메트릭 endpoint의 네이밍/port 규약

여기서도 “메트릭을 내라”가 아니라 “운영 중 확인 가능한 신호”로 써야 정책/테스트로 내려갑니다.

## 계약서를 문서로 끝내지 않는 방법: 템플릿, 정책, 테스트로 쪼갠다

계약서를 만들면 플랫폼 팀이 하고 싶은 일은 보통 세 가지로 나뉩니다.

1) **Golden Path**: 신규 서비스는 계약을 자동으로 만족하는 형태로 시작한다(템플릿/스캐폴딩)
2) Guardrail: 계약 위반은 배포 단계에서 막는다(admission)
3) Continuous verification: 운영 중에도 계약이 유지되는지 확인한다(테스트/진단)

WG도 “테스트 바이너리가 objective하게 검증할 수 있어야 한다”는 방향이라, 내부도 1) 선언(문서/메타데이터) 2) 정적 검증(CI) 3) 동적 검증(런타임 테스트)로 나누는 게 정리됩니다.

여기서 정책 엔진(Rego 등)은 수단일 뿐입니다. WG charter가 특정 엔진을 강제하지 않는다고 못 박는 이유도 동일합니다.[^2] 조직 내부에서도 “Rego로 해야 한다”가 아니라, “검증이 재현 가능하고 리뷰 가능해야 한다”가 핵심이어야 합니다.

아래 예시는 내가 내부 템플릿을 만들 때 실제로 넣을 법한 최소 구현입니다.

## 실행 가능한 예시 1: ‘워크로드 런타임 계약서’ 스키마 + CI 검증

계약서를 YAML로 받되, JSON Schema로 검증하면 도구 선택이 쉬워집니다. (CUE로 가도 되지만, 여기서는 의존성이 단순한 쪽으로 잡습니다.)

### 파일 구조

```text
workload-contract/
  contract.schema.json
  contracts/
    payments-api.yaml
  scripts/
    validate.py
  requirements.txt
```

### contract.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["apiVersion", "kind", "metadata", "spec"],
  "properties": {
    "apiVersion": {"const": "platform.mycorp.io/v1alpha1"},
    "kind": {"const": "WorkloadRuntimeContract"},
    "metadata": {
      "type": "object",
      "required": ["name", "owner"],
      "properties": {
        "name": {"type": "string", "minLength": 1},
        "owner": {"type": "string", "minLength": 1},
        "tier": {"type": "string", "enum": ["critical", "standard", "batch"]}
      },
      "additionalProperties": false
    },
    "spec": {
      "type": "object",
      "required": ["lifecycle", "resources", "network", "storage", "security"],
      "properties": {
        "kubernetes": {
          "type": "object",
          "properties": {
            "minMinor": {"type": "integer", "minimum": 1},
            "maxMinor": {"type": "integer", "minimum": 1},
            "forbiddenAPIs": {
              "type": "array",
              "items": {"type": "string"}
            }
          },
          "additionalProperties": false
        },
        "lifecycle": {
          "type": "object",
          "required": ["terminationGracePeriodSeconds", "handlesSigterm"],
          "properties": {
            "terminationGracePeriodSeconds": {"type": "integer", "minimum": 1, "maximum": 600},
            "handlesSigterm": {"type": "boolean"},
            "pdb": {
              "type": "object",
              "properties": {
                "enabled": {"type": "boolean"},
                "minAvailable": {"type": "string"},
                "maxUnavailable": {"type": "string"}
              },
              "additionalProperties": false
            }
          },
          "additionalProperties": false
        },
        "resources": {
          "type": "object",
          "required": ["qosTarget", "requests"],
          "properties": {
            "qosTarget": {"type": "string", "enum": ["guaranteed", "burstable"]},
            "requests": {
              "type": "object",
              "required": ["cpu", "memory"],
              "properties": {
                "cpu": {"type": "string"},
                "memory": {"type": "string"}
              },
              "additionalProperties": false
            },
            "limits": {
              "type": "object",
              "properties": {
                "cpu": {"type": "string"},
                "memory": {"type": "string"}
              },
              "additionalProperties": false
            }
          },
          "additionalProperties": false
        },
        "network": {
          "type": "object",
          "required": ["exposes", "egress"],
          "properties": {
            "exposes": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["name", "port", "protocol"],
                "properties": {
                  "name": {"type": "string"},
                  "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                  "protocol": {"type": "string", "enum": ["TCP", "UDP"]}
                },
                "additionalProperties": false
              }
            },
            "egress": {
              "type": "object",
              "required": ["mode"],
              "properties": {
                "mode": {"type": "string", "enum": ["default-deny", "unrestricted"]},
                "allowFQDNs": {"type": "array", "items": {"type": "string"}}
              },
              "additionalProperties": false
            }
          },
          "additionalProperties": false
        },
        "storage": {
          "type": "object",
          "required": ["mode"],
          "properties": {
            "mode": {"type": "string", "enum": ["ephemeral", "persistent"]},
            "pvc": {
              "type": "object",
              "properties": {
                "accessMode": {"type": "string", "enum": ["RWO", "RWX", "ROX"]},
                "size": {"type": "string"}
              },
              "additionalProperties": false
            }
          },
          "additionalProperties": false
        },
        "security": {
          "type": "object",
          "required": ["runAsNonRoot", "readOnlyRootFilesystem"],
          "properties": {
            "runAsNonRoot": {"type": "boolean"},
            "readOnlyRootFilesystem": {"type": "boolean"},
            "allowPrivileged": {"type": "boolean"}
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### contracts/payments-api.yaml

```yaml
apiVersion: platform.mycorp.io/v1alpha1
kind: WorkloadRuntimeContract
metadata:
  name: payments-api
  owner: fin-platform
  tier: critical
spec:
  kubernetes:
    minMinor: 35
    maxMinor: 40
    forbiddenAPIs:
      - policy/v1beta1
  lifecycle:
    terminationGracePeriodSeconds: 45
    handlesSigterm: true
    pdb:
      enabled: true
      minAvailable: "50%"
  resources:
    qosTarget: guaranteed
    requests:
      cpu: "500m"
      memory: "1Gi"
    limits:
      cpu: "500m"
      memory: "1Gi"
  network:
    exposes:
      - name: http
        port: 8080
        protocol: TCP
    egress:
      mode: default-deny
      allowFQDNs:
        - "db.internal.example"
        - "otel-collector.platform.svc"
  storage:
    mode: persistent
    pvc:
      accessMode: RWO
      size: "100Gi"
  security:
    runAsNonRoot: true
    readOnlyRootFilesystem: true
    allowPrivileged: false
```

여기서 forbiddenAPIs 같은 항목을 넣는 이유는 간단합니다. Kubernetes API deprecation은 정책에 따라 제거가 발생하고, 실제로 제거되면 “배포 도구/차트/매니페스트가 깨지는” 형태로 사고가 납니다.[^3] 계약서가 이 리스크를 표준 언어로 끌어내는 장치가 됩니다.

### scripts/validate.py

```python
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python scripts/validate.py <schema.json> <contract.yaml>")
        return 2

    schema_path = Path(sys.argv[1])
    contract_path = Path(sys.argv[2])

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))

    v = Draft202012Validator(schema)
    errors = sorted(v.iter_errors(contract), key=lambda e: e.path)
    if errors:
        print(f"INVALID: {contract_path}")
        for e in errors:
            path = ".".join([str(p) for p in e.path])
            print(f"- {path}: {e.message}")
        return 1

    print(f"OK: {contract_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

### 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/validate.py contract.schema.json contracts/payments-api.yaml
```

requirements.txt는 최소로 잡습니다.

```text
PyYAML==6.0.2
jsonschema==4.24.0
```

예상 출력은 다음 형태입니다.

```text
OK: contracts/payments-api.yaml
```

이 단계까지 오면 계약서는 “문서”가 아니라 “아티팩트”가 됩니다. 리뷰 대상이 되고, diff가 남고, 표준화가 가능한 단위로 내려옵니다.

## 실행 가능한 예시 2: Kubernetes ValidatingAdmissionPolicy로 계약의 일부를 강제

계약서 전체를 admission으로 강제하면 보통 실패합니다. 이유는 두 가지입니다.

- 어떤 건 런타임 관찰(예: drain 시나리오) 없이는 검증할 수 없다.
- 어떤 건 조직 정책/인프라 구현에 따라 달라서(예: NetworkPolicy enforcement) admission에 넣으면 이동성이 깨진다.

그래도 “명백하게 막아야 하는 것”은 있습니다. 예를 들면 runAsNonRoot, readOnlyRootFilesystem 같은 항목은 securityContext에 직접 매핑됩니다. Kubernetes도 CEL 기반 admission policy(ValidatingAdmissionPolicy)를 제공하고, 정책은 API server에서 평가된다는 점을 문서로 안내합니다.[^13]

아래는 Deployment/StatefulSet의 Pod template에 대해 기본 보안 계약을 강제하는 예시입니다.

### 1) ValidatingAdmissionPolicy

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: workload-contract-security-baseline
spec:
  matchConstraints:
    resourceRules:
      - apiGroups: ["apps"]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["deployments", "statefulsets"]
  validations:
    - expression: >-
        object.spec.template.spec.containers.all(c,
          has(c.securityContext) &&
          has(c.securityContext.runAsNonRoot) &&
          c.securityContext.runAsNonRoot == true
        )
      message: "containers must set securityContext.runAsNonRoot=true"
    - expression: >-
        object.spec.template.spec.containers.all(c,
          has(c.securityContext) &&
          has(c.securityContext.readOnlyRootFilesystem) &&
          c.securityContext.readOnlyRootFilesystem == true
        )
      message: "containers must set securityContext.readOnlyRootFilesystem=true"
    - expression: >-
        !has(object.spec.template.spec.hostNetwork) || object.spec.template.spec.hostNetwork == false
      message: "hostNetwork is not allowed by the baseline contract"
```

### 2) Binding

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: workload-contract-security-baseline
spec:
  policyName: workload-contract-security-baseline
  validationActions: ["Deny"]
```

여기서 내가 중요하게 보는 포인트는 두 가지입니다.

- 정책 엔진을 무엇으로 쓰든, 규칙이 결국 “Pod template의 어떤 필드를 어떤 값으로 강제한다”로 내려와야 합니다.
- 계약서 템플릿과 admission 규칙의 연결은 1:1일 필요가 없습니다. 계약서 전체 중 “플랫폼이 강제해야 하는 최소 안전선”만 admission으로 가져옵니다.

securityContext 문서는 이 매핑을 매우 직접적으로 제공해 줍니다.[^12]

## 실행 가능한 예시 3: drain 시나리오를 계약 테스트로 만든다(kind 기반)

WG가 지향하는 방향은 “실행 중인 워크로드에 대해 테스트한다”입니다.[^1] 내부 계약서도 이 흐름을 따라가면, 결국 smoke test가 필요합니다.

여기서는 가장 흔한 사고 지점인 drain을 테스트로 고정합니다. Kubernetes 문서가 말하는 것처럼, voluntary disruption에는 PDB가 중요한 도구입니다.[^5]

### 1) kind 클러스터 준비(2 worker)

```yaml
# kind.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
  - role: worker
```

```bash
kind create cluster --config kind.yaml --name wc
kubectl get nodes
```

예상 출력(노드 이름은 환경마다 다름):

```text
NAME              STATUS   ROLES           AGE   VERSION
wc-control-plane  Ready    control-plane   1m    v1.xx.x
wc-worker         Ready    <none>          1m    v1.xx.x
wc-worker2        Ready    <none>          1m    v1.xx.x
```

### 2) 테스트 대상 워크로드: PDB 포함 Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: drain-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: drain-demo
  template:
    metadata:
      labels:
        app: drain-demo
    spec:
      terminationGracePeriodSeconds: 20
      containers:
        - name: app
          image: nginx:1.27
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 50m
              memory: 64Mi
          securityContext:
            runAsNonRoot: true
            readOnlyRootFilesystem: true
          # nginx는 기본적으로 101 유저로 동작하지 않아서 이 예시는 그대로면 실패할 수 있습니다.
          # 실제 조직 템플릿에서는 이미지/유저/FS 전략까지 패키징해야 합니다.
          # 여기서는 drain 테스트 흐름만 보여주려는 목적입니다.
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: drain-demo
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: drain-demo
```

PDB 스펙은 tasks 문서에 정리돼 있고, 잘못 설정하면 drain이 실패할 수 있다는 경고도 문서에 나옵니다.[^14]

```bash
kubectl apply -f drain-demo.yaml
kubectl get pod -l app=drain-demo -o wide
kubectl get pdb drain-demo
```

### 3) drain 실행과 관찰 포인트

```bash
# 한 worker를 drain
kubectl drain wc-worker --ignore-daemonsets --delete-emptydir-data

# 워크로드가 다른 노드에서 다시 올라오는지 확인
kubectl get pod -l app=drain-demo -o wide --watch
```

이 테스트를 계약으로 만들 때의 포인트는 “성공/실패 기준을 계약서에 적는다”입니다.

- drain 완료가 N분 이내여야 한다
- eviction이 PDB에 의해 영구적으로 막히지 않아야 한다
- terminationGracePeriodSeconds 때문에 drain이 불필요하게 늘어나지 않아야 한다

Pod lifecycle과 termination 흐름 자체는 Kubernetes 문서에 정리돼 있으니, 계약 문장은 해당 흐름에 맞춰야 합니다.[^4]

## 함정과 트레이드오프: 계약을 표준화하면 반드시 부딪히는 것들

### PDB는 운영의 안전장치이자 운영 자동화의 장애물이다

PDB를 표준으로 강제하면 “drain에서 죽는 서비스”는 줄어듭니다. 대신, autoscaler나 노드 교체 자동화가 PDB에 자주 걸립니다. Kubernetes 문서도 PDB가 drain과 강하게 연결되어 있음을 전제합니다.[^5]

내 결론은 이렇습니다.

- tier=critical은 PDB가 필수다.
- tier=standard는 PDB를 권장하되, replica/트래픽 패턴에 따라 템플릿을 다르게 제공해야 한다.
- batch/one-shot 작업(Job 류)은 PDB 강제가 오히려 의미가 없거나 해롭다.

즉, 계약은 하나라도 profile은 여러 개여야 합니다. WG 쪽에서도 conformance를 profile로 묶는 아이디어가 자연스럽게 나올 텐데, 이미 Gateway API 같은 곳은 conformance profiles로 기능 묶음을 다룹니다.[^15]

### QoS를 표준화하면 비용 표준화까지 같이 온다

QoS class는 요청/제한 조합으로 결정되고, eviction 우선순위에도 영향을 줍니다.[^6]

Guaranteed를 기본으로 잡으면 안정성은 좋아지지만, requests=limits를 강제하는 순간 평균 사용률이 낮은 서비스에서 비용이 올라갑니다. 반대로 Burstable을 기본으로 두면 비용은 낮아지지만, 노드 압박 상황에서의 tail latency가 튀기 쉽습니다.

그래서 계약서에는 “우리는 Guaranteed가 표준이다” 같은 결론형 문장보다, tier별 선택 기준과 예외 프로세스를 같이 넣는 편이 현실적입니다.

### NetworkPolicy는 표준 API지만 결과는 표준이 아니다

NetworkPolicy는 “기본 egress 허용”이고, deny-only 같은 모델은 제공하지 않습니다.[^7]

그런데 조직은 흔히 “default-deny가 보안 기본값”이라는 합리적 목표를 갖습니다. 이 간극을 메우는 방식은 각 조직마다 다릅니다.

- CNI 레벨에서 default deny를 enforce하고 allow-list를 운영한다
- 서비스 메시/egress gateway로 제어한다
- admission으로 “NetworkPolicy가 없는 namespace 배포 금지” 같은 룰을 둔다

이 중 무엇이든 가능하지만, 계약서에는 “어떤 도구를 쓸 것”이 아니라 “어떤 egress/ingress 경계를 갖는가”를 워크로드 관점에서 먼저 적어야 합니다.

### Storage 계약은 ‘정답’보다 ‘결정 기록’이 중요하다

PV/PVC access mode가 무엇을 의미하는지, WaitForFirstConsumer가 언제 필요한지, StatefulSet의 PVC retention을 어떻게 할지 같은 선택지는 문서에 있지만, 조직 표준으로 안 박혀 있으면 서비스마다 제각각이 됩니다.[^10]

스토리지 파트는 특히 “한 번 정하면 바꾸기 어렵다”가 아니라 “바꾸려면 데이터 마이그레이션이 필요하다”는 점이 문제입니다. 그래서 계약서는 스펙을 강제하기보다, 최소한의 분류와 그에 따른 운영 책임을 명시하는 게 먼저입니다.

- mode=ephemeral이면 백업/복구 SLA는 워크로드가 아니라 시스템이 책임지지 않는다
- mode=persistent이면 PVC lifecycle(보존/삭제)와 백업 책임을 계약서에 명시한다

## 도입 판단 기준: WG의 목표를 내부 로드맵으로 바꾸는 순서

WG는 “2~3 Kubernetes release cycles 내에 첫 stable spec과 working tests를 목표”로 이야기합니다.[^16] 이 속도감은 내부 표준화에도 힌트가 됩니다. 한 번에 다 하려고 하면 실패합니다.

내가 내부에서 순서를 잡는다면 이렇게 갑니다.

1) 계약서 스키마부터 만든다(문서가 아니라 아티팩트로 만든다). 이 단계는 조직 합의 비용을 낮춥니다.
2) admission으로 강제할 최소 baseline을 정한다(securityContext, resource requests 같은 즉시 효과 영역). ValidatingAdmissionPolicy 같은 내장 수단이 있으면 먼저 쓰는 편이 단순합니다.[^13]
3) drain 테스트 하나를 고정한다. PDB/termination/sigterm은 대부분의 서비스에 공통이고, 사고도 많이 납니다. Pod lifecycle과 disruption 문서를 ‘정답’으로 삼고 계약 문장을 거기에 맞춥니다.[^4]
4) Network/Storage는 표준 API를 그대로 강제하기보다, profile로 분리하고 “결정 기록”을 먼저 강제합니다.

이렇게 하면 플랫폼 팀의 골든패스/템플릿/정책이 “흩어진 모범사례”에서 “계약을 구현한 제품”으로 변합니다. WG가 표준화를 어디까지 끌고 갈지와 상관없이, 이 방향은 내부 운영 복잡도를 줄이는 쪽으로만 작동합니다.

## 참고 자료

- [Announcing the Workload Conformance Working Group](https://kubernetes.io/blog/2026/10/27/announcing-workload-conformance-wg/)
- [WG Workload Conformance (Kubernetes Contributors)](https://www.kubernetes.dev/community/community-groups/wg/workload-conformance/)
- [WG Workload Conformance Charter (kubernetes/community)](https://github.com/kubernetes/community/blob/master/wg-workload-conformance/charter.md)
- [Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)
- [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
- [Pod Quality of Service Classes](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/)
- [Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Storage Classes](https://kubernetes.io/docs/concepts/storage/storage-classes/)
- [StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Configure a Security Context for a Pod or Container](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/)
- [Kubernetes Deprecation Policy](https://kubernetes.io/docs/reference/deprecation-policy/)
- [Deprecated API Migration Guide](https://kubernetes.io/docs/reference/using-api/deprecation-guide/)
- [Explore Validating and Mutating Admission Policies](https://kubernetes.io/docs/tutorials/cluster-management/admission-policies/)
- [Validating Admission Policy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)
- [Conformance (Gateway API)](https://gateway-api.sigs.k8s.io/docs/concepts/conformance/)

[^1]: <https://kubernetes.io/blog/2026/10/27/announcing-workload-conformance-wg/>
[^2]: <https://github.com/kubernetes/community/pull/9139/files>
[^3]: <https://kubernetes.io/docs/reference/deprecation-policy/>
[^4]: <https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/?stream=top>
[^5]: <https://kubernetes.io/docs/concepts/workloads/pods/disruptions/>
[^6]: <https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/>
[^7]: <https://kubernetes.io/docs/concepts/services-networking/network-policies/>
[^8]: <https://kubernetes.io/docs/concepts/storage/persistent-volumes/>
[^9]: <https://kubernetes.io/docs/concepts/storage/persistent-volumes/?source=post_page--------------------------->
[^10]: <https://kubernetes.io/docs/concepts/storage/storage-classes/>
[^11]: <https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/>
[^12]: <https://kubernetes.io/docs/tasks/configure-pod-container/security-context/>
[^13]: <https://kubernetes.io/docs/tutorials/cluster-management/admission-policies/>
[^14]: <https://kubernetes.io/docs/tasks/run-application/configure-pdb/>
[^15]: <https://gateway-api.sigs.k8s.io/docs/concepts/conformance/>
[^16]: <https://kubernetes.io/blog/2026/10/27/announcing-workload-conformance-wg/?trk=article-ssr-frontend-pulse_little-text-block>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
