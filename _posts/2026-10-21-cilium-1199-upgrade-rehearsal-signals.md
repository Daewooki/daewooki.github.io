---
title: "Cilium 1.19.9 업그레이드 리허설: 실패를 시그널로 바꾸기"
description: "1.19.9 버그픽스를 ‘우리 클러스터에서 재현·탐지 가능한 관측 신호’로 번역해 업그레이드 리허설을 설계합니다."
date: 2026-10-21 12:47:24 +0900
categories: ["Networking", "Cilium"]
tags: ["cilium", "kubernetes-networking", "iptables", "observability", "hubble", "canary-upgrade"]
render_with_liquid: false
---

## 1.19.9에서 운영을 건드리는 변경: 증상이 아니라 메커니즘을 본다

Cilium 1.19.9(릴리스: 2026-10-15)는 겉으로는 patch release인데, 릴리스 노트에 적힌 bugfix 성격이 네트워킹 운영 리스크를 직접 건드립니다. 특히 아래 3개는 증상이 애플리케이션 레벨에서 늦게 나타나거나(정책 미적용/간헐 드롭), 원인이 “조용히” 묻히기 쉬운 계열입니다.[^1]

- endpoint/restore: reserved internal endpoint(health, ingress) 복구 경로에서 불필요한 cleanup 대기(skip)[^1]
- endpoint GC: GC된 endpoint의 ID가 재사용될 때, 다음 GC iteration에서 새 endpoint를 잘못 삭제할 수 있는 버그 수정[^1]
- ip6tables: 체인 rename 실패가 iptables reconciliation 중에 silently ignored 되던 버그 수정(IPv6 룰 리컨실 실패가 경고로만 남거나, 아예 실패가 드러나지 않던 케이스)[^1]
- selector cache: 드물지만 data race로 agent panic까지 갈 수 있는 케이스 수정[^1]

여기서 중요한 포인트는 “버그가 있었다/없었다”가 아니라, **업그레이드 리허설에서 실패를 관측 가능한 형태로 강제 변환**해야 한다는 점입니다. 네트워킹 계층의 실패는 보통 아래 순서로 도착합니다.

1) datapath/agent 내부에서 작은 불일치가 생김
2) 어느 시점부터 드롭/정책 미적용/간헐 타임아웃이 발생
3) 앱/서비스에서 지표가 흔들리기 시작
4) 이미 확산된 다음에야 원인을 추적함

리허설 문서는 (2)~(3)을 기다리지 않고 (1) 단계에서 잡아내는 쪽으로 설계하는 게 가치가 큽니다.

## 리허설의 목표를 “관측 신호”로 정의한다

내 경우 업그레이드 리허설은 “무사히 올라갔는지” 확인하는 문서가 아닙니다. “망했을 때, 어디서 먼저 망하는지”를 미리 구조화하는 문서입니다. 목표를 다음처럼 바꿔야 합니다.

- 릴리스 노트의 문장을 우리 클러스터에서 관측 가능한 것으로 번역
  - 메트릭: 무엇이 증가/감소하면 위험인지
  - 로그: 어떤 패턴이 나오면 의심할지
  - 플로우: Hubble에서 무엇이 보이면 정책/라우팅 문제인지
- silent failure를 noisy failure로 바꾸는 장치 추가
  - DaemonSet rollout 제어(가능하면 OnDelete)
  - canary workload를 node label로 고정
  - “정상 기준선”을 수치로 찍어둠(업그레이드 전후 비교)

Cilium 관측 신호의 1차 소스는 Cilium 자체가 제공합니다.

- Cilium /metrics: endpoint restore, regeneration 등 운영 핵심 메트릭[^2]
- Hubble metrics: drop_total, flows_processed_total 같은 조기 이상 징후[^2]
- Cilium Upgrade Guide: patch 먼저 올리고, minor 올리라는 운영 원칙(rollback 포함)[^3]

그리고 DaemonSet rollout을 조절하지 못하면 canary가 canary가 아닙니다. Cilium Helm chart는 DaemonSet `updateStrategy`를 values로 받을 수 있게 템플릿이 열려 있습니다.[^4]

## 리허설 환경에서 canary를 만드는 방법: OnDelete로 순서를 내가 잡는다

Kubernetes DaemonSet에는 `RollingUpdate`와 `OnDelete` 두 전략이 있고, `OnDelete`는 템플릿을 업데이트해도 내가 pod를 지우기 전까지는 교체가 진행되지 않습니다. 즉, “어느 노드부터 새 Cilium을 띄울지”를 사람이 결정할 수 있습니다.[^5]

Cilium chart는 `updateStrategy` 값을 그대로 DaemonSet spec에 넣습니다.[^4]

리허설(특히 prod-like staging)에서 나는 Cilium을 아래처럼 올리는 쪽을 선호합니다.

- helm upgrade로 새 버전 리소스를 apply
- DaemonSet updateStrategy는 OnDelete로 고정
- canary 노드 1~2개에서만 cilium-agent pod를 수동 삭제 → 새 버전 기동
- 시그널이 깨끗하면 그 다음 노드로 확장

Helm values 예시는 아래처럼 잡습니다(실제 값은 클러스터별로 다르니 최소한의 골격만).

```yaml
# cilium-override.yaml
prometheus:
  enabled: true

# 리허설에서 제일 중요한 설정. 교체 순서를 내가 잡는다.
updateStrategy:
  type: OnDelete

# configmap 바뀔 때 자동으로 전체를 흔들지 않는다.
rollOutCiliumPods: false

# hubble은 뒤 섹션에서 다루지만, 리허설에서는 metrics를 켜두는 편이 좋다.
hubble:
  enabled: true
  metrics:
    enabled:
      - drop
      - flow
      - dns
```

여기서 `rollOutCiliumPods=true`는 configmap 변경 시 agent pod를 점진적으로 재시작하는 옵션인데, 리허설에서 “의도치 않은 흔들림”을 줄이려면 꺼두고 내가 지우는 방식이 더 통제됩니다. `rollOutCiliumPods` 자체는 공식 configuration 문서에 언급되어 있습니다.[^6]

업그레이드 가이드는 `--reuse-values`를 minor/patch 업그레이드에서 경계합니다. 기존 values는 파일로 저장해서 새 chart의 renamed/deprecated 값을 확인하고, 파일로 넣는 편이 사고가 덜 납니다.[^3]

## (1) endpoint restore/GC 계열: “나중에 터지는” 문제를 즉시 보이게 만든다

1.19.9의 endpoint 관련 수정은 형태가 다르지만 공통점이 있습니다.

- node reboot / agent restart / endpoint churn 같은 이벤트 이후에 터지기 쉽고
- 파편화된 증상이 먼저 나오며(DNS 실패, TTL exceeded, 외부 통신 불가)
- 원인 진단이 늦으면 애플리케이션 문제로 오해하기 쉽습니다.

### reserved internal endpoint cleanup 대기: restore가 길어질 때의 시그널

`endpoint/restore: skip cleanup for reserved internal endpoints`는 health/ingress 같은 reserved endpoint에 대해 restore 과정에서 불필요하게 cleanup을 기다리던 부분을 건드립니다. 이 변경의 핵심은 “restore가 쓸데없이 길어지는 시간”을 줄이는 것입니다.[^7]

이 계열을 리허설에서 번역하면, 관측 포인트는 두 가지입니다.

- restart 이후 endpoint restoration이 길어지는지
- 그 시간이 실제 datapath 불안정으로 연결되는지

Cilium은 endpoint restoration 메트릭을 제공합니다.

- `cilium_endpoint_restoration_endpoints{phase, outcome}`
- `cilium_endpoint_restoration_duration_seconds{phase}`[^2]

리허설에서 내가 확인하는 패턴은 이렇습니다.

- canary 노드에서 cilium-agent 재시작(또는 pod 삭제 → 재생성)
- 재시작 직후 `endpoint_restoration_duration_seconds`의 tail이 늘어나는지
- 그 동안 canary workload에서 DNS/egress 실패가 동반되는지

PromQL은 대략 아래처럼 시작합니다(phase 이름은 버전에 따라 달라질 수 있으니 먼저 메트릭을 실제로 열어 확인하는 게 안전합니다).

```promql
# restoration phase별 p99를 보고, 재시작 직후 꼬리가 길어지는지 확인
histogram_quantile(
  0.99,
  sum by (le, phase) (rate(cilium_endpoint_restoration_duration_seconds_bucket[5m]))
)
```

이 메트릭이 리허설에서 유효하려면 “재시작 이벤트”와 결합돼야 합니다. 그래서 canary 노드에서만 재시작을 만들고, 그 노드에 pinning된 canary workload를 둡니다.

### endpoint GC에서 ID reuse로 새 endpoint가 삭제되는 버그: 로그 패턴이 이미 정답에 가깝다

1.19.9의 endpoint GC 수정은 릴리스 노트 한 줄로는 감이 잘 안 오는데, PR 설명은 실패 메커니즘을 아주 직접적으로 말합니다.

- “previously GC’d endpoint의 ID를 재사용한 new healthy endpoint가 다음 GC iteration에서 incorrectly deleted”[^8]

이게 현실에서 어떤 증상으로 보였는지는 관련 이슈가 더 적나라합니다. #43577에서는 node reboot 이후 새 workload가 외부 통신 불가, DNS resolve 실패, node에서 접근하면 TTL exceeded 같은 증상을 보고합니다.[^9]

이슈에 포함된 로그 패턴은 리허설 시그널로 그대로 쓸 만합니다.[^9]

- `JoinEP: Failed to load program` + `Link not found`
- `Removed endpoint`
- `Stray endpoint found. You may be affected by upstream Kubernetes issue #86944.`
- 같은 endpointID가 재사용된 뒤에도 stray로 계속 언급

리허설의 목적은 이 패턴이 prod에서 처음 나오지 않게 만드는 것입니다. 그래서 나는 아래 두 레이어로 “관측 가능한 실패”를 만듭니다.

#### 레이어 A: Loki(또는 유사 로그 스토리지)에서 패턴 기반 알람

아래는 LogQL 예시입니다(라벨은 환경별로 조정).

```logql
# stray endpoint 패턴
{namespace="kube-system", pod=~"cilium-.*"}
  |= "Stray endpoint found"
```

```logql
# endpoint 삭제 이벤트(너무 많아지면 위험)
{namespace="kube-system", pod=~"cilium-.*"}
  |= "Removed endpoint"
```

```logql
# JoinEP loader 계열 실패
{namespace="kube-system", pod=~"cilium-.*"}
  |= "JoinEP: Failed to load program"
```

여기서 중요한 건 “한 번이라도 나오면 무조건 장애”가 아니라, **canary 노드/시간창과 결합**해야 한다는 점입니다.

- canary rollout 직후 10분 동안만 민감하게 보고
- 그 시간에 특정 노드에서만 집중되면 upgrade 영향 가능성을 높게 둠

#### 레이어 B: endpoint regeneration/restore 메트릭에서 이상 징후를 잡는다

Cilium endpoint 계열 메트릭 중 리허설에서 특히 유용한 건 regeneration 카운터입니다.

- `cilium_endpoint_regenerations_total{reason,outcome,error}`[^2]

이 메트릭은 “정책/엔드포인트 재생성 이벤트가 늘었다”를 숫자로 보여줍니다. GC 버그가 직접 regeneration을 올리는지 여부는 케이스마다 다르겠지만, 최소한 upgrade 직후 특정 노드에서 endpoint 재생성이 비정상적으로 튀면 바로 의심 리스트에 올릴 수 있습니다.

예시 PromQL:

```promql
sum by (instance, reason, outcome) (
  increase(cilium_endpoint_regenerations_total[10m])
)
```

#### 리허설에서 재현을 시도하는 방식: node reboot 대신 “endpoint churn + agent restart”로 근사

#43577은 reboot가 트리거였지만, 리허설에서 항상 노드를 재부팅할 수는 없습니다. 대신 비슷한 구조를 만듭니다.

- canary node를 정해서, canary workload를 nodeSelector로 고정
- 그 노드의 cilium-agent를 재시작(daemonset pod 삭제)
- 동시에 그 노드에서만 pod churn(짧은 job을 반복 생성/삭제)
- churn pod는 DNS + HTTP egress를 반복

이렇게 하면 “endpoint가 짧게 많이 생기고, 동시에 agent lifecycle 이벤트가 겹치는” 조건을 만들 수 있습니다. GC/restore/ID reuse 계열은 이런 조건에서 터질 확률이 올라갑니다.

pod churner 예시(현실적인 편의상 단순화했지만, 실행은 됩니다).

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: net-churn
  namespace: net-canary
spec:
  schedule: "*/1 * * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 0
      template:
        spec:
          restartPolicy: Never
          nodeSelector:
            cilium.io/canary: "true"
          containers:
            - name: churn
              image: curlimages/curl:8.10.1
              command: ["/bin/sh","-c"]
              args:
                - |
                  set -e
                  # DNS
                  nslookup kubernetes.default.svc.cluster.local
                  # egress
                  curl -fsS --max-time 2 https://example.com >/dev/null
                  echo ok
```

이 CronJob이 실패하기 시작하는데, 동시에 cilium-agent 로그에서 `Stray endpoint found` 같은 패턴이 보이면 upgrade canary의 early-warning로 충분히 쓸 수 있습니다.

## (2) ip6tables 체인 rename/룰 리컨실: “조용히 잘못된 상태”를 검출한다

1.19.9에서 내가 특히 높게 평가하는 수정은 `Fix ip6tables chain rename errors being silently ignored during iptables rule reconciliation`입니다.[^1]

이게 위험한 이유는 다음과 같습니다.

- iptables 리컨실은 주기적으로 돌아가고, 실패하면 재시도합니다.
- 그런데 특정 실패가 드러나지 않으면(에러 drop), 시스템은 “정상 동작 중”처럼 보일 수 있습니다.
- 결과적으로 IPv6 체인에는 “이전 룰 + 새 룰”이 섞이거나, 기대와 다른 체인이 남아 애매한 드롭/정책 미적용이 나올 수 있습니다.

백포트 PR의 커밋 메시지가 메커니즘을 구체적으로 설명합니다.

- `customChain.rename()`이 ip6tables rename 에러를 drop하고 있었고
- renameChains가 계속 진행한 뒤 installRules에서 IPv6 chain 생성이 실패(이미 남아 있어서)했는데
- 로그는 rename 에러가 아니라 `chain already exists`로 보일 수 있었고
- feeder rules가 비활성화된 hook이면 warning만 찍고 기존 IPv6 chain에 룰을 append해버려서 실패가 report되지 않을 수도 있었다[^10]

이건 운영 관점에서 “관측 불가능한 실패”에 가깝습니다.

### 내가 잡는 관측 포인트 3종 세트

#### 1) agent 로그에서 iptables full reconciliation failure를 별도 알람으로 분리

Cilium 이슈들에서 반복적으로 보이는 에러 문구는 이 형태입니다.

- `iptables rules full reconciliation failed, will retry another one later`[^11]

이 문구는 ip6tables rename 문제에 국한되지는 않지만, “룰 리컨실 실패”라는 공통 관측 신호가 됩니다. 먼저 이걸 알람으로 빼두면, ip6tables rename 같은 케이스도 최소한 noisy하게 만들 수 있습니다.

LogQL 예시:

```logql
{namespace="kube-system", pod=~"cilium-.*"}
  |= "iptables rules full reconciliation failed"
```

그리고 여기서 한 번 더 좁힙니다.

- dual-stack 또는 IPv6를 쓰는 클러스터면, 같은 시간창에 `ip6tables` 관련 키워드가 같이 나오는지
- canary 노드에서만 집중되는지

#### 2) ip6tables 체인 인벤토리를 스냅샷으로 남겨서 diff

silent failure를 막는 가장 확실한 방법은 “현재 상태를 사람이 이해 가능한 형태로 계속 남기는 것”입니다.

- `ip6tables-save` 전체를 저장하면 너무 큽니다.
- 리허설 목적이라면 요약만 남겨도 됩니다.
  - CILIUM_ 체인 개수
  - OLD_CILIUM_ 체인 개수
  - 특정 테이블(nat/filter/raw)에서 Cilium 관련 rule line count

host에서 돌려야 하니, 리허설 클러스터에서는 hostNetwork + privileged DaemonSet 하나를 따로 둡니다.

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: ip6tables-snapshot
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: ip6tables-snapshot
  template:
    metadata:
      labels:
        app: ip6tables-snapshot
    spec:
      hostNetwork: true
      hostPID: true
      tolerations:
        - operator: Exists
      containers:
        - name: snap
          image: alpine:3.20
          securityContext:
            privileged: true
          command: ["/bin/sh","-c"]
          args:
            - |
              apk add --no-cache ip6tables iptables
              while true; do
                ts=$(date -Iseconds)
                echo "--- ${ts} ---"
                ip6tables-save | grep -E '^(\*|:|\-A) ' | grep -E 'CILIUM_|OLD_CILIUM_' | wc -l | xargs echo "ip6tables-save(cilium lines)"
                ip6tables-save | grep -E '^:' | grep -E 'CILIUM_|OLD_CILIUM_' | wc -l | xargs echo "ip6tables(chains)"
                sleep 30
              done
```

이 DaemonSet의 로그를 Loki에 넣고, canary upgrade window에서 chain count가 이상하게 증가/감소하는지 보면 “룰 리컨실이 뭔가 꼬였다”를 훨씬 빨리 잡습니다.

#### 3) 리허설에서 의도적으로 rename 실패를 만들어, 1.19.9에서 실패가 드러나는지 확인

1.19.9 변경은 “에러를 drop하지 말고 반환해서 reconciler가 retry하게 만든다”가 핵심입니다.[^10]

리허설에서 확인하고 싶은 건 이겁니다.

- rename이 실패하면, 이제는 실패가 로그/상태로 드러나는가
- 실패가 드러난 뒤 retry로 정상 상태로 회복되는가

rename 실패를 가장 단순하게 만드는 방식은 “목표 이름의 OLD_ 체인이 이미 존재하도록” 만들어 충돌을 일으키는 것입니다.

예시 절차(노드 1개에서만 진행):

```bash
# 1) canary 노드를 정한다
NODE=<canary-node-name>

# 2) 해당 노드의 cilium-agent pod를 찾는다
POD=$(kubectl -n kube-system get pod -l k8s-app=cilium -o wide | awk -v n="$NODE" '$7==n {print $1; exit}')

# 3) 일부 OLD_ 체인을 미리 만들어 둔다(이미 있으면 skip)
kubectl -n kube-system exec "$POD" -c cilium-agent -- sh -c '
  ip6tables -t filter -N OLD_CILIUM_INPUT 2>/dev/null || true
  ip6tables -t nat    -N OLD_CILIUM_POST_nat 2>/dev/null || true
  echo prepared
'

# 4) 이제 그 노드의 cilium-agent를 재시작해서 리컨실을 유도한다
kubectl -n kube-system delete pod "$POD"

# 5) 재기동 후 로그에서 iptables/ip6tables 관련 에러가 어떻게 찍히는지 확인
kubectl -n kube-system logs -l k8s-app=cilium -c cilium-agent --since=5m | grep -E "iptables|ip6tables|reconcil"
```

이때 “정확히 어떤 에러 문자열이 찍힌다”를 내가 단정해서 문서화하면 위험합니다(환경별로 다릅니다). 대신 리허설 체크리스트를 이렇게 씁니다.

- 예전에는 rename 원인이 묻히고 `chain already exists` 같은 2차 증상으로 보일 수 있었다[^10]
- 1.19.9에서는 rename 실패가 리컨실 실패로 드러나야 한다[^10]
- 리컨실 실패가 드러났다면, retry로 정상 상태(OLD_ 정리, CILIUM_ 체인 재생성)로 돌아오는지까지 확인한다

## (3) selector cache data race/panic: “재현”보다 “조기 감지”가 우선이다

1.19.9의 selector cache 수정은 PR 설명이 솔직합니다.

- chance가 tiny이고, 재현을 진지하게 시도해보진 않았으며
- 그래도 data race는 좋지 않고, 드물게 agent panic으로 이어질 수 있다[^12]

이런 타입은 리허설에서 100% 재현하려고 시간을 쓰는 게 효율이 낮습니다. 대신 canary에서 “panic이 나면 3분 안에 알아차리기”가 목표가 돼야 합니다.

### 관측 포인트: Kubernetes가 이미 제공하는 신호로 충분히 빨리 잡힌다

- `kube_pod_container_status_restarts_total`로 cilium-agent restart 급증 감지
- `kube_daemonset_status_number_unavailable`로 cilium DaemonSet unavailable 감지
- 노드 taint(예: `node.cilium.io/agent-not-ready`)가 빠르게 증가하는지 확인

Cilium은 `agent-not-ready-taint-key` 같은 설정이 configmap에 존재하고, 운영에서는 이런 taint가 실제로 “앱 장애로 번역되기 전”의 조기 신호가 됩니다(값 자체는 환경에서 확인).[^13]

PrometheusRule 예시(메트릭 이름은 kube-state-metrics 기준):

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: cilium-upgrade-canary
  namespace: monitoring
spec:
  groups:
    - name: cilium-canary
      rules:
        - alert: CiliumAgentRestartSpike
          expr: sum(increase(kube_pod_container_status_restarts_total{namespace="kube-system", container="cilium-agent"}[5m])) > 0
          for: 0m
          labels:
            severity: critical
          annotations:
            summary: "cilium-agent restarted (possible panic/data race)"

        - alert: CiliumDaemonSetUnavailable
          expr: kube_daemonset_status_number_unavailable{namespace="kube-system", daemonset="cilium"} > 0
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "cilium DaemonSet unavailable"
```

리허설에서는 “이 알람이 제대로 울리는지”까지 포함해서 검증하는 편이 낫습니다. 실제 운영 사고는 버그보다 경보 미설정/미연결/노이즈 때문에 더 길어지는 경우가 많습니다.

## iptables/endpoint 문제가 앱 레벨로 번역되기 전에 잡는 방법: canary workload + Hubble

업그레이드에서 내가 기대하는 최종 결과는 “정책이 의도대로 적용되고, 드롭이 없다”가 아니라, “정책/드롭/패킷손실이 생기면 canary에서 몇 분 안에 드러난다”입니다.

여기서 Hubble이 강한 이유는 간단합니다.

- policy decision(허용/거부) 자체가 flow event로 올라옵니다.
- `--verdict DROPPED`로 정책/라우팅 실패를 실시간으로 본다.

Cilium 공식 블로그의 troubleshooting 가이드도 policy drop을 Hubble로 먼저 보라고 설명합니다.[^14]

### Hubble metrics를 켜서 “드롭 급증”을 수치로 만든다

Hubble metrics 문서에는 `drop_total`, `flows_processed_total` 등이 정의되어 있고, drop의 기본 카운팅 동작(기본적으로 Policy denied만 카운트하는 등)도 설명합니다.[^2]

리허설에서 최소한 아래 두 개는 켭니다.

- `hubble_drop_total{reason,protocol}`
- `hubble_flows_processed_total{protocol,type,subtype,verdict}`[^2]

그리고 canary namespace를 따로 만들어서, 업그레이드 전후로 “canary에서만” 드롭이 튀는지 봅니다. labelsContext를 잘 설계하면 source/destination namespace까지 라벨로 얹을 수 있는데, 무작정 많이 붙이면 cardinality가 터집니다. 리허설이라면 namespace 정도까지만 우선 붙이고 시작하는 편이 안전합니다.[^2]

PromQL 예시:

```promql
# canary namespace에서 policy denied가 튀는지
sum by (reason) (
  rate(hubble_drop_total{reason="POLICY_DENIED"}[5m])
)
```

```promql
# 전체 flows 대비 DROPPED 비율이 증가하는지
sum(rate(hubble_flows_processed_total{verdict="DROPPED"}[5m]))
/
sum(rate(hubble_flows_processed_total[5m]))
```

### canary에서 정책 미적용을 조기 포착: “기대 결과가 있는 테스트”를 둔다

정책 미적용은 드롭이 아니라 “원래 막혀야 할 트래픽이 통과”로 나타납니다. 이건 Hubble drop만 보면 놓칩니다. 그래서 canary namespace에 ‘기대 결과가 명확한’ 정책을 하나 둡니다.

- canary client는 canary echo로만 통신 가능
- canary client의 egress는 DNS + 특정 외부 도메인만 허용
- 나머지는 deny

그 다음 canary probe job이

- 허용 트래픽은 200
- 금지 트래픽은 timeout(또는 drop)

을 계속 확인하게 둡니다. 이때 Hubble에서 `policy-verdict` 이벤트가 같이 따라오는지까지 보면 더 빠릅니다(최소한 리허설 구간에는).

## canary 노드에서 조기 탐지의 핵심 도구: cilium connectivity test를 노드 고정으로 돌린다

`cilium connectivity test`는 단순 핑이 아니라, 서비스/정책/다양한 경로를 종합적으로 확인하는 테스트 셋입니다. troubleshooting 문서에서도 이 테스트가 어떤 subsystem을 확인하는지 표로 설명합니다.[^15]

중요한 건 canary 노드에만 테스트 pod를 띄우는 기능이 있다는 점입니다.

- `--node-selector`로 특정 label이 붙은 노드에만 테스트 pod를 제한할 수 있습니다.[^16]

리허설 절차에서 나는 이 옵션을 중심에 둡니다.

1) canary 노드 라벨 부여

```bash
kubectl label node <canary-node-name> cilium.io/canary=true
```

2) canary 노드에서만 connectivity test 실행

```bash
cilium connectivity test \
  --node-selector cilium.io/canary=true \
  --print-flows \
  --request-timeout 10s
```

3) 실패 시에는 `--pause-on-fail`로 멈춰서, 그 상태에서 Hubble observe / cilium-dbg로 바로 본다.

```bash
cilium connectivity test \
  --node-selector cilium.io/canary=true \
  --pause-on-fail \
  --print-flows
```

이걸 “업그레이드 전 1회”, “canary 노드에 새 agent 올라온 뒤 1회”, “다음 노드 확장 전 1회”로 고정하면, 패킷 손실/정책 미적용이 앱 지표로 번역되기 전 단계에서 잡힐 확률이 확 올라갑니다.

## 업그레이드 리허설 실행 순서: 1.19.9를 ‘관측 가능한 변경’으로 만든다

아래는 내가 실제로 문서에 적어두는 체크리스트 스타일입니다. 리허설은 재현보다 “반복 가능성”이 더 중요해서, 명령어는 가능한 한 구체적으로 남깁니다.

### 1) 현재 설치 상태를 파일로 고정

```bash
helm get values cilium -n kube-system -o yaml > cilium-values.before.yaml
kubectl -n kube-system get cm cilium-config -o yaml > cilium-config.before.yaml
```

### 2) Upgrade Guide 원칙: patch 최신으로 맞춘 뒤 진행

Cilium upgrade 문서는 minor 업그레이드 전에 해당 minor의 최신 patch로 먼저 올리라고 권합니다. 이건 rollback 관점에서도 유리합니다.[^3]

이번 케이스는 1.19.x 내 patch 이동(예: 1.19.8 → 1.19.9)이라도, 나는 동일한 원칙으로 갑니다.

### 3) helm upgrade는 values를 파일로 넣고, upgradeCompatibility를 명시

upgrade 문서는 datapath disruption을 줄이기 위해 `upgradeCompatibility`를 “처음 설치된 버전”으로 맞추라고 합니다.[^3]

```bash
helm repo add cilium https://helm.cilium.io/
helm repo update

helm upgrade cilium cilium/cilium \
  -n kube-system \
  --version 1.19.9 \
  -f cilium-values.before.yaml \
  -f cilium-override.yaml \
  --set upgradeCompatibility=1.19
```

### 4) OnDelete 전략으로 canary 노드부터 교체

- 먼저 canary 노드 1개에서만 cilium pod 삭제
- 재기동 후 10~15분 관측
  - endpoint restoration 메트릭 tail
  - endpoint regeneration 증가
  - stray endpoint / removed endpoint 로그
  - iptables reconciliation failure 로그
  - Hubble drop_total 증가

노드 단위로 pod 삭제는 per-node config 문서에도 예시가 있습니다.[^17]

```bash
NODE=<canary-node-name>
POD=$(kubectl -n kube-system get pod -l k8s-app=cilium -o wide | awk -v n="$NODE" '$7==n {print $1; exit}')

kubectl -n kube-system delete pod "$POD"
```

### 5) canary connectivity test를 노드 고정으로 실행

```bash
cilium connectivity test --node-selector cilium.io/canary=true --print-flows
```

### 6) ip6tables rename failure를 의도적으로 만들어 “실패가 드러나는지” 확인

앞 섹션의 스텝을 그대로 실행합니다.

- OLD_ 체인을 미리 만들어 rename 충돌 유발
- agent restart 유도
- 리컨실 실패가 로그에서 드러나는지 확인

### 7) canary가 깨끗하면 노드를 늘린다

OnDelete라서 “내가 지운 노드만” 교체됩니다. 이게 리허설의 장점입니다.

- 1노드(관측) → 2노드(관측) → 25% → 50% → 전체

## 반론과 회의론: 이 정도까지 해야 하나

이런 리허설 문서를 만들면 흔히 나오는 반응은 두 가지입니다.

- patch release인데 과한 거 아니냐
- 실제로 재현도 안 되는 걸 왜 체크하냐

내 경험상 네트워킹 구성 요소는 patch release라고 안전하지 않습니다. 이유는 간단합니다.

- patch에서 고쳐지는 건 주로 edge case인데, 운영 장애는 edge case에서 터집니다.
- 특히 “silent failure를 noisy failure로 바꾸는 변경”은, 업그레이드 리허설의 관측 설계가 없으면 그냥 지나갑니다.

selector cache data race처럼 재현이 어려운 건 더더욱 “재현”이 목표가 되면 안 됩니다. 대신 panic이 나면, canary에서 곧바로 탐지해서 rollout을 멈추고, 영향 범위를 그 노드로 가둘 수 있어야 합니다.

이 글의 요지는 버그를 겁주려는 게 아니라, 버그픽스를 운영 자산으로 전환하는 방법입니다.

## 결론: 1.19.9 업그레이드 합격선은 ‘관측 가능성’이다

1.19.9의 endpoint/ip6tables/selector cache 계열 수정은 공통적으로 “장애가 앱 레벨로 늦게 번역되는” 영역을 건드립니다. 업그레이드 리허설의 합격선은 기능 체크가 아니라 관측 가능성으로 잡는 편이 실용적입니다.

- endpoint restore/GC는 `endpoint_restoration_*`, `endpoint_regenerations_total`, 그리고 stray/removed endpoint 로그 패턴으로 조기 탐지한다.[^2]
- ip6tables는 reconciliation failure 로그를 알람으로 빼고, 체인 인벤토리 스냅샷을 diff해서 silent drift를 noisy하게 만든다.[^10]
- selector cache data race는 재현보다 cilium-agent restart spike를 canary 단계에서 즉시 감지하는 게 효율이 높다.[^12]
- canary 조기 포착은 `cilium connectivity test --node-selector`로 노드 고정 테스트를 돌려야 의미가 있다.[^16]

네트워킹 업그레이드는 결국 “올려도 된다”가 아니라 “망하면 바로 멈출 수 있다”가 기준이 됩니다.

## 참고 자료

- [Cilium 1.19.9 릴리스 노트](https://github.com/cilium/cilium/releases/tag/v1.19.9)
- [endpoint/restore: skip cleanup for reserved internal endpoints (PR #48272)](https://github.com/cilium/cilium/pull/48272)
- [Fix incorrect endpoint manager GC handling for endpoint ID reuse (PR #48905)](https://github.com/cilium/cilium/pull/48905)
- [The repeated deletion of cilium endpoint gc affects pod network (Issue #43577)](https://github.com/cilium/cilium/issues/43577)
- [iptables: return the ip6tables error when renaming a chain (PR #49024)](https://github.com/cilium/cilium/pull/49024)
- [v1.19 backport: ip6tables rename error fix (PR #49334)](https://github.com/cilium/cilium/pull/49334)
- [selectorcache: remove global lastSelectorId variable (PR #47733)](https://github.com/cilium/cilium/pull/47733)
- [Cilium Monitoring & Metrics](https://docs.cilium.io/en/stable/observability/metrics/)
- [Cilium Endpoint Lifecycle](https://docs.cilium.io/en/stable/security/policy/lifecycle/)
- [Cilium Upgrade Guide](https://github.com/cilium/cilium/blob/main/Documentation/operations/upgrade.rst)
- [cilium connectivity test CLI 레퍼런스](https://docs.cilium.io/en/latest/cmdref/cilium_connectivity_test/)
- [Cilium troubleshooting 문서(Connectivity test 설명 포함)](https://docs.cilium.io/en/stable/operations/troubleshooting/)
- [Kubernetes DaemonSet update strategy: OnDelete vs RollingUpdate](https://kubernetes.io/docs/tasks/manage-daemon/update-daemon-set/)
- [cilium-agent DaemonSet 템플릿(updateStrategy values 반영)](https://github.com/cilium/cilium/blob/main/install/kubernetes/cilium/templates/cilium-agent/daemonset.yaml)
- [Cilium Configuration: rollOutCiliumPods 언급](https://docs.cilium.io/en/stable/configuration/index.html)
- [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)
- [Discourse 월간 릴리스에 맞춘 셀프호스팅 업그레이드 운영](https://daewooki.github.io/posts/discourse-monthly-release-selfhost-upgrade-automation/)

[^1]: <https://github.com/cilium/cilium/releases/tag/v1.19.9>
[^2]: <https://docs.cilium.io/en/stable/observability/metrics/>
[^3]: <https://github.com/cilium/cilium/blob/main/Documentation/operations/upgrade.rst>
[^4]: <https://github.com/cilium/cilium/blob/main/install/kubernetes/cilium/templates/cilium-agent/daemonset.yaml>
[^5]: <https://kubernetes.io/docs/tasks/manage-daemon/update-daemon-set/>
[^6]: <https://docs.cilium.io/en/stable/configuration/index.html>
[^7]: <https://github.com/cilium/cilium/pull/48272>
[^8]: <https://github.com/cilium/cilium/pull/48905>
[^9]: <https://github.com/cilium/cilium/issues/43577>
[^10]: <https://github.com/cilium/cilium/pull/49334>
[^11]: <https://github.com/cilium/cilium/issues/47956>
[^12]: <https://github.com/cilium/cilium/pull/47733>
[^13]: <https://docs.cilium.io/en/stable/helm-values/>
[^14]: <https://cilium.io/blog/2026/08/16/troubleshooting-kubernetes-networking/>
[^15]: <https://docs.cilium.io/en/stable/operations/troubleshooting/>
[^16]: <https://docs.cilium.io/en/latest/cmdref/cilium_connectivity_test/>
[^17]: <https://docs.cilium.io/en/stable/configuration/per-node-config/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
