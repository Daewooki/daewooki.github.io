---
title: "Kubernetes 1.35.10 패치 릴리스: 정기 패치를 운영 계약으로 바꾸는 법"
description: "패치 릴리스는 버튼 클릭이 아니라 deadline·검증 윈도우·애드온 회귀 테스트·업그레이드 링으로 재설계해야 합니다."
date: 2026-10-16 12:49:57 +0900
categories: ["News", "DevOps"]
tags: ["kubernetes", "patch-releases", "release-engineering", "regression-testing", "upgrade-rings"]
render_with_liquid: false
---

## 1.35.10이 던지는 신호: 날짜가 적힌 순간부터 이미 운영 이슈입니다

2026-10-16 KST 시점에서 Kubernetes 1.35 라인의 패치 일정은 문서에 꽤 구체적으로 적혀 있습니다. Kubernetes 1.35 릴리스 시리즈 페이지는 다음 패치로 **cherry-pick deadline 2026-10-09, target date 2026-10-13**인 1.35.10을 표기합니다.[^1]

문제는 이 날짜를 “그 주에 한 번 올리면 되겠네”라고 해석하는 순간, 패치 릴리스가 기술 이벤트가 아니라 사람/프로세스의 실패 요인이 된다는 점입니다. 날짜가 박히면 그 날짜를 중심으로 역산되는 활동이 생기고(검증, 승인, 커뮤니케이션), 그 활동이 빠지면 업그레이드 자체가 도박이 됩니다.

여기서 한 가지를 먼저 정리해야 합니다. 1.35.10은 문서에는 target date로 잡혀 있지만, 같은 날에 실제 릴리스가 “완료”됐는지는 별개입니다. 패치 릴리스는 지연될 수 있고, 실제 릴리스 여부는 GitHub Releases의 태그와 kubernetes-announce 공지로 확인하는 게 가장 안전합니다. 패치 릴리스가 일정 사유로 1주 미뤄진 사례도 공식 채널에 올라옵니다.[^2]

2026-10-16 KST에 내가 확인한 범위에서는, kubernetes/kubernetes GitHub Releases 목록에 v1.35.10이 보이지 않고 v1.35.9까지만 노출됩니다.[^3]

그럼에도 1.35.10을 지금 다루는 이유는 충분합니다. 운영 관점에서 중요한 건 “실제로 10/13에 릴리스가 나왔나”보다 “10/13을 target으로 upstream이 움직이고 있고, cherry-pick deadline이 10/09로 고정돼 있다는 사실”입니다. 이건 내부 운영 일정(검증/승인/점검/변경관리)을 그 레일 위에 올릴 수 있다는 뜻입니다.[^1]

추가로, v1-35 문서 스냅샷(버전 고정 문서)은 이미 정적 스냅샷이며 더 이상 actively maintained가 아니라고 명시합니다. 여기만 보고 있으면 패치 히스토리가 2026-03 부근에서 멈춘 것처럼 보이는 착시가 생깁니다.[^4]

정리하면, 1.35.10 자체보다 중요한 사건은 이것입니다.

- 패치 릴리스가 “월간 정기 이벤트”로 돌아갑니다(대체로 monthly cadence).[^5]
- upstream은 그 월간 이벤트에 cherry-pick deadline을 걸고, 그 deadline 전후로 freeze/검증 구간을 운영합니다.[^5]
- 이 리듬을 내부 운영 계약으로 가져오지 않으면, 패치는 계속 “할 수도 있고 못 할 수도 있는 일”로 남습니다.

## cherry-pick deadline을 내부 캘린더로 가져오면 생기는 변화

Kubernetes 패치 릴리스에서 cherry-pick은 단순한 Git 작업이 아니라, 릴리스 팀이 리스크를 제어하기 위한 시간 설계입니다.

공식 Patch Releases 문서는 cherry-pick이 “deadline 전에 merge-ready + 라벨/CI 조건을 갖추고” 있어야 하며, 이 deadline이 보통 릴리스 2일 전이라고 설명합니다.[^5]

또한 SIG Release의 release-manager handbook은 패치 릴리스 며칠 전 cherry-pick freeze를 걸어야 한다고 적고, freeze의 목적을 꽤 명확히 씁니다.

- accepted patch의 문제를 발견할 최소 시간 확보
- release branch의 CI가 HEAD를 따라잡을 시간 확보
- serial 같은 느린 테스트가 HEAD에서 반복 실행되어 안정성을 확인할 시간 확보

즉 upstream 입장에서도 **검증 윈도우**는 선택이 아니라 필수 안전장치입니다.[^6]

여기서 운영 조직이 놓치기 쉬운 포인트는 “deadline은 upstream용이고, 우리는 릴리스 뜨면 적용만 하면 된다”라는 착각입니다. 내 경험상 오히려 반대입니다.

- upstream의 cherry-pick deadline은 내부 검증을 시작할 가장 좋은 트리거입니다.
- 실제 릴리스 날짜(announcement)가 내부 배포의 시작점이 되면, 시간은 부족하고 품질은 흔들립니다.

패치를 **운영 계약**으로 가져오려면, 내부 캘린더에도 최소한 다음 두 개의 마일스톤이 생겨야 합니다.

1) upstream cherry-pick deadline(D) : 내부에서 “이 패치에 들어갈 변화량이 사실상 확정되는 시점”으로 본다.

2) upstream target date(R) : 내부에서 “릴리스 아티팩트 확정 + 공급망 서명/이미지 digest 확정 + 최종 배포 승인”의 시점으로 본다.

Kubernetes 1.35.10의 경우 문서에 D=2026-10-09, R=2026-10-13이므로, 내부 검증은 10/09~10/13 사이에 최소 1회 돌려야 의미가 생깁니다.[^1]

여기서 KST 이슈가 끼어듭니다. 문서가 날짜만 적고 시간대를 명시하지 않기 때문에, 실제 공지/아티팩트 배포가 UTC 기반으로 늦게 뜨면 한국에선 2026-10-14로 넘어갈 수 있습니다. 그래서 “R 다음날 오전에 배포하자”처럼 상대 날짜로 이야기하면 팀 간 커뮤니케이션이 깨집니다. 변경관리 문서와 점검 캘린더에는 절대 시간을 박는 쪽이 낫습니다.

## 패치가 바꾸는 것은 코드만이 아닙니다: 이미지와 dependency가 실무 리스크가 됩니다

패치 릴리스가 안정적이라는 인식이 있지만, 실무에서 장애를 내는 건 종종 “코드 변화”보다 “주변부 변화”입니다. Kubernetes 패치 릴리스는 커뮤니티가 고친 버그를 backport(cherry-pick)해서 모으는 형태라서, 머리로는 작은 변화라고 생각하기 쉽습니다.

그런데 공식 문서가 이미 말해줍니다.

- 월간 cadence로 나가지만, critical bug fix는 cadence 밖에서도 나갈 수 있습니다.[^5]
- 릴리스 시리즈가 maintenance mode로 들어가면, CVE가 있는 취약점, dependency 문제(베이스 이미지 업데이트 포함), 핵심 컴포넌트의 critical 이슈를 위해 유지보수 릴리스가 나갈 수 있습니다.[^5]

실제로 Kubernetes 1.35 시리즈 페이지에는 1.35.2가 “Go CVE 대응을 위한 out-of-band 릴리스이며 다른 변화는 없다”라고 명시돼 있습니다.[^1]

이 문장을 운영 관점으로 번역하면 다음이 됩니다.

- 패치 릴리스는 종종 “runtime/compiler/base image”의 변화일 수 있습니다.
- 이때 리스크는 Kubernetes 자체보다, 그 주변(특히 CNI/CSI/Ingress와 노드 OS/Kernel 조합)의 미묘한 호환성에서 터집니다.

따라서 패치 릴리스 대응을 “컨트롤 플레인 교체 작업”으로만 보면 구조적으로 놓칩니다. 패치 릴리스 대응은 결국 이미지/애드온/노드까지 포함한 회귀 테스트 설계 문제로 바뀝니다.

이 블로그에서 예전에 정리했던 etcd 업그레이드/백업/복구 리허설 글을 링크하는 이유도 동일합니다. 패치든 마이너든 업그레이드는 결국 저장소/컨트롤플레인/노드 이미지까지 엮이기 때문에, “릴리스 노트만 읽고”는 운영 품질이 나오지 않습니다.

- [etcd v3.7.2 운영 리허설: 업그레이드·백업·복구·이미지 전략까지](https://daewooki.github.io/posts/etcd-372-kubernetes-ops-rehearsal/)

## CNI/CSI/Ingress 회귀 테스트를 패치 릴리스의 1급 시민으로 만들기

패치 릴리스 프로세스를 재설계할 때, 내가 가장 먼저 바꾸는 건 테스트의 우선순위입니다.

- “Kubernetes 기능 테스트”는 이미 upstream CI가 상당 부분 커버합니다.
- 반면 “우리 클러스터가 실제로 의존하는 조합(CNI/CSI/Ingress + 인증/정책 + 노드 이미지 + 커널)”은 우리만 테스트할 수 있습니다.

여기서 중요한 오해가 하나 있습니다. conformance(E2E) 돌리면 다 잡힐 것 같지만, conformance는 어디까지나 공통분모이며 운영 특화 구성은 빠집니다.

Sonobuoy 문서는 Sonobuoy가 Kubernetes conformance 테스트를 포함한 플러그인 기반 진단 도구라고 소개하고, 기본적인 실행 흐름(sonobuoy run / retrieve / results)을 제시합니다.[^7]

CNCF의 Certified Kubernetes Software Conformance 설명은 “동일한 오픈소스 conformance 앱(Sonobuoy)으로 누구나 확인 가능”하다고 말합니다. 이건 운영 팀에게도 힌트가 됩니다. conformance는 ‘통과하면 끝’이 아니라 ‘최저선’입니다.[^8]

그래서 패치 릴리스에서 내가 요구하는 테스트 레이어는 보통 3단입니다.

### 1) 클러스터 공통: Sonobuoy quick 또는 smoke

Sonobuoy는 `--mode quick`가 “단일 테스트로 설정/기본 동작을 빠르게 확인”하는 모드라고 문서에 명시합니다.[^7]

이건 패치 직후(또는 preflight)에도 부담이 적어서, 링별로 반복하기 좋습니다.

### 2) 애드온 공통: CNI/CSI/Ingress 기능 회귀

여기부터가 본게임입니다. 패치 릴리스에서 장애를 만드는 흐름은 대개 다음 중 하나입니다.

- CNI: Node 간 트래픽, kube-proxy 대체(eBPF) 경로, NetworkPolicy enforcement, DNS
- CSI: attach/mount, volume expansion, snapshot/restore, fsType/SELinux/권한, NodePublishVolume token 처리
- Ingress: endpoint publish, leader election, webhook, HTTP/2/GRPC, LB health check

이걸 “문서 체크리스트”로만 운영하면 사람마다 결과가 달라집니다. 커맨드로 자동화해서 **애드온 회귀 테스트**를 배포 파이프라인의 gate로 만들어야 합니다.

### 3) 우리 서비스 특화: 플랫폼 공통 워크로드 1~2개를 링에서 굴리기

여기서는 “모든 서비스”가 아니라 “플랫폼 공통”을 잡습니다.

예를 들어, GPU가 있는 클러스터면 device plugin + runtimeclass + 스케줄링 정책 쪽이 패치에 민감합니다. 이건 예전에 내가 정리했던 글에서처럼, 오토스케일링과 스케줄링의 경계에서 장애가 많이 나기 때문입니다.

- [GPU가 병목인 LLM 서빙, Kubernetes에서 오토스케일링하는 법](https://daewooki.github.io/posts/gpu-llm-kubernetes-2026-6-2/)

## (실행 가능한) 패치 릴리스 검증 러너: Sonobuoy + 애드온 스모크

아래는 “패치 릴리스가 예정된 주”에 canary 링에서 실제로 돌릴 수 있는 형태로 만든 스모크 러너 예시입니다. 전제는 간단합니다.

- 이미 존재하는 canary 클러스터(또는 staging 클러스터)가 있고
- 그 클러스터가 업그레이드된 뒤
- 아래 커맨드가 CI runner(또는 ops bastion)에서 실행됩니다.

### 의존성

- kubectl (클러스터 버전에 맞춰 설치)
- sonobuoy CLI
- bash, jq

Sonobuoy의 기본 사용법은 공식 문서에 그대로 나옵니다.[^7]

### 디렉터리 구조

```text
patch-verify/
  Makefile
  scripts/
    00-preflight.sh
    10-sonobuoy-quick.sh
    20-addon-smoke.sh
  manifests/
    cni/
      netpol.yaml
      pod-a.yaml
      pod-b.yaml
      svc.yaml
    csi/
      pvc.yaml
      pod-writer.yaml
    ingress/
      deploy.yaml
      svc.yaml
      ingress.yaml
```

### 0) Preflight: “업그레이드가 끝났는지”부터 기계적으로 확인

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "[preflight] context=$(kubectl config current-context)"

echo "[preflight] kubectl client/server"
kubectl version --short

echo "[preflight] nodes"
kubectl get nodes -o wide

echo "[preflight] kube-system pods (not-ready check)"
NOT_READY=$(kubectl get pods -n kube-system \
  --no-headers \
  | awk '$3 != "Running" && $3 != "Completed" {print $0}' || true)

if [[ -n "${NOT_READY}" ]]; then
  echo "[preflight] kube-system has not-ready pods:" >&2
  echo "${NOT_READY}" >&2
  exit 2
fi

echo "[preflight] OK"
```

실행:

```bash
bash scripts/00-preflight.sh
```

예상 출력(형태):

```text
[preflight] context=canary
[preflight] kubectl client/server
Client Version: v1.35.x
Server Version: v1.35.x
[preflight] nodes
... Ready ...
[preflight] kube-system pods (not-ready check)
[preflight] OK
```

여기서 중요한 건 “버전 숫자”가 아니라, kube-system이 안정 상태로 돌아왔는지(특히 CNI/CSI가 정상인지)를 빨리 판별하는 것입니다.

### 1) Sonobuoy quick: 싸게 자주 돌리는 기본선

```bash
#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="sonobuoy"

echo "[sonobuoy] run (quick)"
sonobuoy run --mode quick --wait

echo "[sonobuoy] retrieve"
RESULTS_TGZ=$(sonobuoy retrieve)

echo "[sonobuoy] results=${RESULTS_TGZ}"
sonobuoy results "${RESULTS_TGZ}"

echo "[sonobuoy] cleanup"
sonobuoy delete --wait

echo "[sonobuoy] OK"
```

실행:

```bash
bash scripts/10-sonobuoy-quick.sh
```

예상 출력(형태):

```text
[sonobuoy] run (quick)
...
[sonobuoy] retrieve
...
[sonobuoy] results=...tar.gz
Plugin: e2e
Status: complete
Total: 1
Passed: 1
Failed: 0
...
[sonobuoy] cleanup
[sonobuoy] OK
```

quick 모드 자체가 “단일 테스트로 빠르게 확인”하는 목적이라는 점은 Sonobuoy 문서에 명시돼 있습니다.[^7]

### 2) 애드온 스모크: CNI/CSI/Ingress를 최소 단위로 찌르기

이 단계는 환경 의존이 큽니다. 그래서 “우리 조직의 표준”을 박아야 합니다.

- 표준 CNI가 있으면 NetworkPolicy enforcement를 포함
- 표준 CSI가 있으면 PVC provision + mount + 재시작 후 데이터 유지
- 표준 Ingress가 있으면 Ingress routing 200 확인

아래 스크립트는 세 영역을 순서대로 수행하고, 실패 시 즉시 exit 합니다.

```bash
#!/usr/bin/env bash
set -euo pipefail

NS="patch-smoke"

echo "[addon] create namespace=${NS}"
kubectl create ns "${NS}" 2>/dev/null || true

cleanup() {
  echo "[addon] cleanup namespace=${NS}"
  kubectl delete ns "${NS}" --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[addon] (CNI) apply netpol + pods"
kubectl -n "${NS}" apply -f manifests/cni/

echo "[addon] (CNI) wait for pods"
kubectl -n "${NS}" wait --for=condition=Ready pod/pod-a --timeout=180s
kubectl -n "${NS}" wait --for=condition=Ready pod/pod-b --timeout=180s

echo "[addon] (CNI) connectivity test: pod-a -> svc"
kubectl -n "${NS}" exec pod-a -- sh -c 'wget -qO- --timeout=2 http://svc-b:8080/healthz | grep ok'

echo "[addon] (CNI) netpol test: should deny pod-a -> pod-b (direct)"
set +e
kubectl -n "${NS}" exec pod-a -- sh -c 'wget -qO- --timeout=2 http://pod-b:8080/healthz'
RC=$?
set -e
if [[ $RC -eq 0 ]]; then
  echo "[addon] netpol did not block traffic (unexpected)" >&2
  exit 3
fi

echo "[addon] (CSI) create PVC + writer pod"
kubectl -n "${NS}" apply -f manifests/csi/

kubectl -n "${NS}" wait --for=condition=Bound pvc/smoke-pvc --timeout=180s
kubectl -n "${NS}" wait --for=condition=Ready pod/pvc-writer --timeout=180s

echo "[addon] (CSI) write & verify"
kubectl -n "${NS}" exec pvc-writer -- sh -c 'date > /data/ts && sync && cat /data/ts'

echo "[addon] (CSI) restart pod and re-verify"
kubectl -n "${NS}" delete pod pvc-writer
kubectl -n "${NS}" wait --for=condition=Ready pod/pvc-writer --timeout=180s
kubectl -n "${NS}" exec pvc-writer -- sh -c 'test -f /data/ts && cat /data/ts'

echo "[addon] (Ingress) apply ingress test objects (optional)"
if kubectl get ns ingress-nginx >/dev/null 2>&1; then
  kubectl -n "${NS}" apply -f manifests/ingress/
  kubectl -n "${NS}" wait --for=condition=Available deploy/echo --timeout=180s

  echo "[addon] (Ingress) port-forward controller and curl"
  PF_PID=""
  kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 18080:80 >/tmp/pf.log 2>&1 &
  PF_PID=$!
  sleep 2

  set +e
  curl -sS -H 'Host: echo.local' http://127.0.0.1:18080/ | grep echo
  RC=$?
  set -e

  kill "$PF_PID" >/dev/null 2>&1 || true

  if [[ $RC -ne 0 ]]; then
    echo "[addon] ingress routing failed" >&2
    exit 4
  fi
else
  echo "[addon] ingress-nginx namespace not found; skipping ingress smoke"
fi

echo "[addon] OK"
```

여기서 포인트는 두 가지입니다.

- 이 테스트는 “기능 테스트”가 아니라 “회귀 탐지”입니다. 빠르게 실패하고, 실패했을 때 조사 가능한 상태를 남겨야 합니다.
- CNI/CSI/Ingress를 다루지만, 각 영역의 진짜 문제는 대개 Kubernetes 코어 버그가 아니라 호환성/구성/이미지 교체에서 터지므로, 패치 릴리스 파이프라인에 이 레이어가 반드시 들어가야 합니다.

Kubernetes가 “최신 패치 릴리스를 prompt하게 올리라”고 권고하는 이유는 보안/지원 측면에서 타당하지만, 운영자는 그 문장만 믿고 무작정 올릴 수는 없습니다. 그래서 ‘올릴 수 있게 만드는 테스트’가 먼저입니다.[^9]

## 업그레이드 링을 패치 캘린더와 결합하면, 운영 계약이 숫자로 바뀝니다

패치 릴리스를 “정기 작업”으로 만들려면, 배포의 단위를 ‘클러스터 한 개’가 아니라 ‘링’으로 바꿔야 합니다. 링은 결국 다음을 가능하게 합니다.

- 실패를 “전체 실패”가 아니라 “카나리 실패”로 제한
- 검증 비용을 링 단계별로 분배
- 변경관리 문서가 추상적 약속이 아니라, 실제 캘린더/체크리스트/승인 게이트로 내려옴

내가 현실적으로 운영 가능한 링 설계를 잡을 때 쓰는 규칙은 이렇습니다.

1) canary 링은 “트래픽이 존재해야” 합니다. 트래픽이 없는 canary는 버그를 못 잡습니다.

2) canary 링은 프로덕션과 동일한 애드온 조합(CNI/CSI/Ingress, admission, policy)을 가져야 합니다. 다르면 또 못 잡습니다.

3) canary 링은 복구가 쉬워야 합니다. 여기서 중요한 건 클러스터 롤백이 아니라, 워크로드를 다른 링으로 옮길 수 있는지(즉, 장애가 나도 고객 영향이 최소인지)입니다.

4) 링 전환 조건은 사람이 아니라 테스트 결과여야 합니다. 위에서 만든 Sonobuoy + 애드온 스모크가 이 역할을 합니다.

Kubernetes의 Version Skew Policy는 kube-apiserver/kubelet 간 허용 스큐를 정의합니다. 패치 릴리스는 기본적으로 같은 minor 안에서 움직이므로 스큐 문제가 덜해 보이지만, 링 기반 운영은 이 정책을 기반으로 “업그레이드 순서(컨트롤플레인 → 노드)”를 강제하는 데 도움이 됩니다.[^10]

여기서 “운영 계약”이란 말을 구체화하면 결국 아래 문장들이 됩니다.

- R(릴리스 공지) 이후 N일 이내에 canary 링은 패치 버전을 적용한다.
- canary 링에서 T시간 이상 관찰하고, 핵심 SLI(에러율/latency/노드 불안정)를 넘지 않으면 다음 링으로 간다.
- 프로덕션 링 적용은 특정 요일/시간대에만 하며, 예외는 CVE/긴급 릴리스일 때만 허용한다.

이런 계약은 문서로만 만들면 아무 의미가 없습니다. upstream이 이미 cherry-pick deadline과 freeze로 시간을 설계해둔 만큼, 내부도 D~R 구간에 검증을 배치하고 R 이후엔 링 전개만 남겨야 일정이 버텨집니다.[^6]

## 회의론: 패치는 원래 안전한데 왜 이렇게까지 하느냐

패치 릴리스 대응 프로세스를 무겁게 만들면, 보통 두 가지 반발이 나옵니다.

### “패치인데, 이렇게 테스트하면 비용이 너무 크다”

맞는 말입니다. 그래서 conformance 전체를 매번 돌리자는 얘기가 아닙니다. Sonobuoy도 quick 모드를 따로 제공하는 이유가 있습니다.[^7]

비용을 줄이는 핵심은 두 가지였습니다.

- canary 링에만 상대적으로 무거운 테스트를 몰아넣고, 나머지 링은 더 얇은 스모크로 간다.
- 애드온 회귀 테스트는 “최소 기능”만 확인하고, 고급 기능(예: snapshot, topology spread 등)은 주간/월간 별도 스위트로 돌린다.

테스트를 줄이는 게 아니라, 반복 가능한 형태로 압축하는 쪽이 운영 품질이 올라갔습니다.

### “upstream CI가 다 보는데, 우리는 왜 또 돌려야 하느냐”

upstream CI는 upstream이 아는 조합을 봅니다. 우리 조합은 안 봅니다.

특히 패치 릴리스에서 위험한 건 다음입니다.

- 노드 OS 이미지의 사소한 변화
- container runtime/containerd의 정책 변화
- CNI/CSI/Ingress가 사용하는 Kubernetes API의 엣지 케이스

게다가 patch releases 문서 자체가 말합니다. critical bug fix나 dependency 이슈는 cadence 밖에서도 나올 수 있고, maintenance mode에서도 dependency/base image 업데이트가 릴리스 사유가 됩니다.[^5]

이 말은 곧 “패치라도 주변부 변동성이 생각보다 크다”는 뜻입니다.

## 앞으로 지켜볼 것: 1.35 라인의 남은 시간과, 문서 스냅샷의 함정

Kubernetes 1.35 릴리스 시리즈 페이지에는 maintenance mode 시작일(2026-12-28)과 EOL(2027-02-28)이 같이 표기돼 있습니다.[^1]

이 두 날짜는 패치 릴리스 프로세스에도 직접 영향을 줍니다.

- maintenance mode에 들어가면 “월간 정기 패치”가 계속 나오리라고 기대하면 안 됩니다.
- 대신 보안(CVE), dependency, critical core 이슈 중심으로만 나올 수 있습니다.[^5]

그리고 운영자가 실제로 더 자주 밟는 함정이 하나 있습니다.

- v1-35 문서는 “정적 스냅샷”이라고 밝히고, 패치 히스토리도 특정 시점에서 멈춰 있습니다.[^4]
- 반면 kubernetes.io의 릴리스 시리즈 페이지(다국어 포함)는 최신 패치/예정 패치 표를 유지하는 경우가 있습니다.[^1]

결론적으로, “어떤 문서를 기준으로 운영 일정과 계약을 잡을지” 자체가 운영 설계의 일부가 됩니다.

## 지금 할 수 있는 일: 패치를 ‘정기 배포’가 아니라 ‘정기 검증’으로 정의하기

1.35.10이 실제로 2026-10-13에 릴리스되었는지 여부와 관계없이, 문서에 박힌 deadline/target date는 그대로 프로세스에 쓸 수 있습니다.[^1]

내가 권하는(그리고 실제로 효과가 있었던) 재정의는 이것입니다.

- 패치 릴리스 대응을 배포 작업으로 정의하지 않고, 검증 작업으로 정의한다.
- 배포는 검증의 결과물로 자동으로 흘러가게 만든다.

구체적으로는 아래 3가지가 한 덩어리로 움직여야 합니다.

1) upstream cherry-pick deadline 기반 사전 검증 윈도우

- D(예: 2026-10-09)부터 canary에서 “다음 패치에 들어갈 변화량”을 기준으로 사전 검증을 돌립니다.
- upstream이 freeze를 거는 이유(HEAD 안정화, 느린 테스트 반복)를 내부에서도 그대로 이용합니다.[^6]

2) 이미지/애드온 회귀 테스트

- Sonobuoy quick로 기본선 확인 후, CNI/CSI/Ingress 스모크로 운영 리스크를 찌릅니다.[^7]
- 이 테스트는 “한 번 만들고 계속 재사용”되는 운영 자산이 됩니다.

3) 업그레이드 링과 연동

- canary → (pre-prod) → production으로 흘러가는 링 전개를 캘린더에 박습니다.
- 링 전환은 테스트 결과로만 가능하게 합니다.

이 조합이 만들어지면, 패치 릴리스는 더 이상 “그냥 올리는 것”이 아니라, deadline을 기준으로 리스크를 시간으로 분해하고, 링으로 영향 범위를 제한하는 운영 시스템이 됩니다.

결국 정기 패치는 기술 트렌드가 아니라, 조직이 리스크를 다루는 방식 자체를 운영 계약으로 고정시키는 장치입니다.

## 참고 자료

- [Kubernetes 1.35 릴리스 시리즈(패치 일정/1.35.10 target date 포함)](https://kubernetes.io/vi/releases/1.35/)
- [kubernetes/kubernetes GitHub Releases(v1.35.9 등 태그 확인)](https://github.com/kubernetes/kubernetes/releases)
- [Kubernetes Patch Releases(월간 cadence, cherry-pick deadline, 지원 기간/maintenance mode 개요)](https://kubernetes.io/releases/patch-releases/)
- [Kubernetes SIG Release release-manager handbook(패치 릴리스 freeze의 목적)](https://github.com/kubernetes/sig-release/blob/master/release-engineering/handbooks/release-manager.md)
- [Kubernetes v1.35 문서의 Patch Releases 페이지(정적 스냅샷 안내)](https://v1-35.docs.kubernetes.io/releases/patch-releases/)
- [Kubernetes Version Skew Policy(컴포넌트 버전 스큐 정책)](https://v1-35.docs.kubernetes.io/releases/version-skew-policy/)
- [Kubernetes 클러스터 업그레이드 문서(최신 패치로 올리라는 권고)](https://v1-35.docs.kubernetes.io/docs/tasks/administer-cluster/cluster-upgrade/)
- [Sonobuoy 공식 문서(quick 모드 포함)](https://sonobuoy.io/docs/main/)
- [CNCF Certified Kubernetes Software Conformance(Sonobuoy 기반 conformance 설명)](https://www.cncf.io/training/certification/software-conformance/)
- [Kubernetes patch releases 지연 공지 사례(kubernetes-announce)](https://groups.google.com/g/kubernetes-announce/c/Za8HIS-L198)
- [Kubernetes v1.35 릴리스 블로그(릴리스 팀 공식 포스트)](https://v1-35.docs.kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/)

[^1]: <https://kubernetes.io/vi/releases/1.35/>
[^2]: <https://groups.google.com/g/kubernetes-announce/c/Za8HIS-L198>
[^3]: <https://github.com/kubernetes/kubernetes/releases>
[^4]: <https://v1-35.docs.kubernetes.io/releases/patch-releases/>
[^5]: <https://kubernetes.io/releases/patch-releases/>
[^6]: <https://github.com/kubernetes/sig-release/blob/master/release-engineering/handbooks/release-manager.md>
[^7]: <https://sonobuoy.io/docs/main/>
[^8]: <https://sitelet.easiiodev.ai/sitelet?url=https%3A%2F%2Fwww.cncf.io%2Ftraining%2Fcertification%2Fsoftware-conformance%2F>
[^9]: <https://v1-35.docs.kubernetes.io/docs/tasks/administer-cluster/cluster-upgrade/>
[^10]: <https://v1-35.docs.kubernetes.io/releases/version-skew-policy/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
