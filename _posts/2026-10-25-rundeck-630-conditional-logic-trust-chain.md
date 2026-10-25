---
title: "Rundeck 6.3.0: Conditional Logic와 Docker 신뢰 체인 운영"
description: "Conditional Logic GA로 잡 복제를 줄이고, eMudhra intermediate CA 사고 같은 신뢰 체인 이슈를 배포 파이프라인에서 검증·재배포로 표준화합니다."
date: 2026-10-25 12:44:40 +0900
categories: ["DevOps", "Rundeck"]
tags: ["rundeck", "runbook-automation", "conditional-logic", "docker", "tls", "supply-chain-security"]
render_with_liquid: false
---

Self-hosted Runbook Automation/Rundeck 6.3.0이 2026-10-22에 조기 릴리스되었습니다. 평소 순서(대개 SaaS → self-hosted)와 다르게 self-hosted가 먼저 나온 이유가 명확합니다. 공식 Docker 이미지의 CA trust store가 eMudhra intermediate CA compromise를 그대로 신뢰하고 있었고, 6.3.0에서 “신뢰하지 않도록” 패치된 이미지가 제공됐기 때문입니다. 또한 5.20.0부터 Early Access로 존재하던 Conditional Logic가 6.3.0에서 GA로 전환되면서(그리고 기본 활성화되면서) 운영 자동화의 설계 방식이 바뀔 지점이 생겼습니다.[^1]

오늘은 2026-10-25 KST 기준으로, 내가 Rundeck를 운영 자동화 오케스트레이터로 쓰면서 실제로 겪었던 두 가지 비용을 6.3.0의 변화로 어떻게 줄일지에 집중합니다.

- 워크플로가 복잡해질수록 **잡 복제(job copy/paste)** 가 설계 부채가 되는 문제
- 내가 만든 애플리케이션 코드와 무관하게, **Docker 이미지의 신뢰 체인(trust store)** 이 깨지는 사건이 터졌을 때 “검증 → 재배포”를 파이프라인 표준으로 만들지 못하면 복구가 매번 수작업이 되는 문제

## 6.3.0에서 실제로 바뀐 것: GA 기능과 운영 리스크가 같이 들어왔다

6.3.0 릴리스 노트의 요약은 단순합니다. Conditional Logic GA, 보안 하드닝, 그리고 eMudhra intermediate CA 이슈로 인한 공식 Docker 이미지 패치가 핵심입니다. 특히 “SaaS는 영향 없음, self-hosted Docker 배포는 6.3.0으로 올리고 재배포하라”는 문장이 이 릴리스의 성격을 규정합니다.[^1]

여기서 중요한 포인트는 두 가지입니다.

1) Conditional Logic는 기능이 아니라 운영 방식의 변화입니다. “옵션 값/노드 속성/이전 스텝의 출력”을 기반으로 UI/워크플로 엔진이 분기할 수 있으면, 잡을 분기별로 따로 만들 필요가 줄어듭니다. 6.3.0에서는 Runbook Automation 기준으로 기본 활성화가 됐고, 5.20.0~6.2.x에서는 feature flag가 필요했습니다.[^1]

2) eMudhra 사건은 코드 취약점이 아니라 “컨테이너가 들고 있는 trust store가 현실을 따라가지 못해서 생기는 리스크”를 상기시킵니다. 릴리스 노트/보안 권고 모두 “컨테이너 안에서 apt-get upgrade 하는 건 지속적인 해결책이 아니고, 업데이트된 공식 이미지를 pull해서 재배포하라”고 못 박고 있습니다.[^2]

게다가 6.3.0에는 작지만 은근히 깨지는 변경도 있습니다. `${job.serverUrl}` 컨텍스트 변수가 더 이상 trailing slash(`/`)로 끝나지 않습니다. 기존에 `${job.serverUrl}api/...` 같은 식으로 붙여 쓰던 스텝은 조용히 깨집니다.[^1]

## 잡 복제가 왜 비용이 되는가: 실패는 실행 중이 아니라 “수정 중”에 난다

Rundeck를 오래 쓰면, 조직의 운영 요구사항이 잡의 개수로 직접 반영됩니다.

- dev/staging/prod 환경별
- blue/green/canary/rolling 배포 전략별
- 노드군(ASG, k8s node pool, 온프레미스 랙)별
- 승인(approvals)/점검(precheck)/롤백(rollback) 유무별

초기에는 잡을 복제해서 빠르게 쌓는 게 속도가 납니다. 문제는 “다음 수정”부터입니다.

- 공통 로직이 20개 잡에 흩어지면, 보안 패치나 옵션 추가 같은 변경이 20번 발생합니다.
- 어느 잡이 최신인지 애매해져서 운영자가 보수적으로 행동합니다. 결과적으로 배포 리드타임이 늘어납니다.
- 잡 스펙이 SCM으로 관리되더라도, 분기별 잡이 많으면 리뷰 비용이 증가합니다.

나는 이걸 개발 코드의 중복보다 더 위험하다고 봅니다. 개발 코드는 테스트/빌드 파이프라인이 강제하지만, 운영 잡은 “성공한 이력”이 신뢰를 만들어서 쉽게 방치되기 때문입니다.

Conditional Logic는 여기서 “잡 복제 대신 분기 표현을 워크플로 자체에 넣는” 선택지를 제공합니다. 5.20.0에서 Early Access로 나온 뒤, 6.1.0에서 Node First 전략까지 확장됐고, 6.2.0에서 invertLogic(AND/OR 그룹 토글) 같은 유지보수용 장치가 추가됐으며, 6.3.0에서 GA+기본 활성화로 자리 잡았습니다.[^3]

## Conditional Logic가 줄여주는 중복의 종류: “잡 수”보다 “정책 수”를 줄인다

Conditional Logic는 크게 두 축으로 나뉩니다.

- Node Conditional Logic: 노드마다 조건을 평가해서 노드 단위로 분기합니다. 예를 들어 `node.tags`에 `db`가 있으면 DB용 스텝만 수행합니다.[^4]
- Workflow Conditional Logic: 실행 전체에서 한 번 조건을 평가해 분기합니다. 예를 들어 `${option.env}`가 `prod`인 경우에만 Change Ticket 생성/승인을 수행합니다.[^4]

그리고 조건식을 만들 때, 단순히 option만 보는 게 아니라 “이전 스텝 출력(prior step outputs)”을 참조할 수 있게 되는 게 운영적으로 큽니다. 6.3.0에서 Prior Steps 탭과 built-in step output capture가 가능해졌고, 플러그인이 `@PluginOutput`을 노출하는 경우 log filter 없이도 조건식에서 참조할 수 있습니다. 커맨드/스크립트라면 log filter의 `${data.<name>}` 또는 `${<stepNum>:exec.exitCode*}` 같은 형태로 연결할 수 있다고 문서에 명시돼 있습니다.[^4]

이 기능을 “if/else”로만 보면 큰 감흥이 없습니다. 실제로는 정책을 모델링하는 비용을 줄입니다.

- 배포 전략이 3개면 잡을 3개 만들지 않고, `strategy` 옵션 하나로 흡수합니다.
- 환경별로 다른 보호 장치(예: prod는 승인 필수, dev는 생략)를 잡 복제가 아니라 분기 정책으로 표현합니다.
- 동일한 잡을 호출하는 외부 시스템(ChatOps, PagerDuty, Jira, GitHub Actions 등)이 있어도, 엔드포인트/잡 ID를 늘리지 않고 옵션만 바꿉니다.

이건 “잡 수 감소”보다 “잡 API surface 감소”가 핵심입니다.

## Conditional Logic를 적용하면 안 되는 경우: 분기 수가 아니라 책임 경계가 먼저다

Conditional Logic가 만능은 아닙니다. 문서에도 제한이 분명합니다.

- Ruleset 워크플로 전략에서는 지원하지 않습니다. (Sequential/Parallel/Node First에서만 동작)[^5]
- JSON/YAML 포맷에서는 지원하지만 XML은 지원하지 않습니다. 이미 XML 기반으로 잡을 관리하고 있다면 포맷 전환 비용이 먼저 발생합니다.[^4]
- Conditional nesting은 무한이 아닙니다. (문서상 1단계 중첩 제한이 명시돼 있습니다.)[^4]

내 경험 기준으로는 다음 상황에서 Conditional Logic로 억지로 합치면 더 망가집니다.

- 권한/승인 흐름이 완전히 다른 잡을 하나로 묶는 경우 (prod 승인과 dev 무승인 같은 수준을 넘어, 감사 로그/권한 모델이 갈라질 때)
- 실패의 의미가 다른 작업을 한 잡으로 합치는 경우 (예: “프로비저닝”과 “배포”를 하나로 묶고 옵션으로 분기)
- 외부 연동(PagerDuty/ServiceNow 등)이 환경마다 다른 테넌트/자격증명을 쓰는데, 키 관리/시크릿 경계가 정리되지 않은 경우

Conditional Logic는 “잡 복제 비용”을 줄이지만, “도메인 경계”를 대신 만들어주지 않습니다.

## 실전 리팩터링: 복제된 배포 잡 6개를 1개로 줄이는 구조

여기서는 Kubernetes에 배포하는 현실적인 패턴을 기준으로 잡을 구성합니다.

- 입력: `env`, `strategy`, `service`, `image`, `chart_version`, `dry_run`
- 공통 단계: preflight(클러스터 컨텍스트/권한/네임스페이스 확인), 배포, 검증, (필요 시) 롤백
- 분기: env가 prod면 승인/추가 검증 포함, strategy가 canary면 canary 단계가 추가

Conditional Logic가 없을 때 흔한 구조는 이렇습니다.

- `deploy-service-dev-rolling`
- `deploy-service-staging-rolling`
- `deploy-service-prod-rolling`
- `deploy-service-dev-canary`
- `deploy-service-staging-canary`
- `deploy-service-prod-canary`

옵션이 늘어나면 이 조합은 기하급수로 커집니다. Conditional Logic로 바꾸면 잡은 “1개+정책”으로 재구성됩니다.

### 잡 정의(YAML): conditional step으로 prod 가드레일과 canary 경로를 넣기

아래 예시는 Rundeck job YAML에서 `type: conditional`을 사용하는 형태입니다. 문서에 나온 구조 그대로 `conditionGroups`(OR), 그룹 내부(AND), `subSteps`를 사용합니다.[^6]

```yaml
- name: deploy-k8s-service
  group: platform/deploy
  description: k8s 배포(rolling/canary), env별 가드레일을 conditional로 분리
  loglevel: INFO
  scheduleEnabled: true
  executionEnabled: true

  options:
    - name: env
      required: true
      values:
        - dev
        - staging
        - prod
    - name: strategy
      required: true
      values:
        - rolling
        - canary
    - name: service
      required: true
    - name: image
      required: true
      description: example.registry.local/myapp@sha256:... 또는 tag
    - name: chart_version
      required: true
    - name: dry_run
      required: true
      values:
        - "false"
        - "true"

  sequence:
    strategy: node-first
    keepgoing: false
    commands:
      # 1) 공통: 배포 준비
      - exec: |-
          set -euo pipefail
          echo "[preflight] env=${option.env} service=${option.service} strategy=${option.strategy}"
          ./scripts/kube-context.sh "${option.env}"
          ./scripts/ns-check.sh "${option.env}" "${option.service}"

      # 2) prod에서만: 실행 전 추가 가드레일
      - type: conditional
        nodeStep: false
        description: prod-guardrails
        invertLogic: false
        conditionGroups:
          - - key: "${option.env}"
              operator: "=="
              value: "prod"
        subSteps:
          - exec: |-
              set -euo pipefail
              echo "[prod] extra checks..."
              ./scripts/require-change-ticket.sh "${option.service}" \
                "${option.image}" "${option.chart_version}"

      # 3) dry_run이면 여기서 종료
      - type: conditional
        nodeStep: false
        description: dry-run-stop
        conditionGroups:
          - - key: "${option.dry_run}"
              operator: "=="
              value: "true"
        subSteps:
          - exec: |-
              echo "[dry-run] stop before deploy"

      # 4) canary 전략
      - type: conditional
        nodeStep: false
        description: canary-path
        conditionGroups:
          - - key: "${option.strategy}"
              operator: "=="
              value: "canary"
        subSteps:
          - exec: |-
              set -euo pipefail
              ./scripts/deploy-canary.sh "${option.env}" "${option.service}" \
                "${option.image}" "${option.chart_version}"
          - exec: |-
              set -euo pipefail
              ./scripts/verify-canary.sh "${option.env}" "${option.service}"
          - exec: |-
              set -euo pipefail
              ./scripts/promote-canary.sh "${option.env}" "${option.service}"

      # 5) rolling 전략
      - type: conditional
        nodeStep: false
        description: rolling-path
        conditionGroups:
          - - key: "${option.strategy}"
              operator: "=="
              value: "rolling"
        subSteps:
          - exec: |-
              set -euo pipefail
              ./scripts/deploy-rolling.sh "${option.env}" "${option.service}" \
                "${option.image}" "${option.chart_version}"

      # 6) 공통: post-verify
      - exec: |-
          set -euo pipefail
          ./scripts/verify-service.sh "${option.env}" "${option.service}"
```

이 YAML이 현실적인 이유는 두 가지입니다.

- Node First 전략을 기준으로 잡으면, 한 노드에서 워크플로 전체를 끝내고 다음 노드로 넘어가므로 배포/검증이 섞여서 레이스가 나는 걸 피할 수 있습니다. Conditional Logic는 6.1.0에서 Node First에서도 동작하도록 확장됐습니다.[^7]
- prod 가드레일을 “잡 분기”가 아니라 “워크플로 정책”으로 넣으면, 외부 호출자(예: ChatOps)가 prod 잡을 따로 찾지 않아도 됩니다. 운영 정책이 UI 상에서도 한 잡 안에 보이기 때문에 리뷰/감사 관점에서도 낫습니다.

### 실행 가능한 스크립트(예시): canary/rolling을 실제 kubectl/helm로 돌리기

아래는 로컬에서도 동작하는 수준으로 쪼갠 스크립트 예시입니다. (환경별 kubeconfig/context를 잡는 방식은 조직마다 달라서, 여기서는 context 이름만 매핑한다고 가정합니다.)

`scripts/kube-context.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

ENV="$1"
case "$ENV" in
  dev)     CTX="k8s-dev" ;;
  staging) CTX="k8s-staging" ;;
  prod)    CTX="k8s-prod" ;;
  *) echo "unknown env=$ENV" >&2; exit 2 ;;
 esac

echo "[kube] use-context $CTX" >&2
kubectl config use-context "$CTX" >/dev/null
```

`scripts/deploy-rolling.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

ENV="$1"
SVC="$2"
IMAGE="$3"
CHART_VERSION="$4"

NAMESPACE="$SVC"
RELEASE="$SVC"

helm upgrade --install "$RELEASE" "./charts/$SVC" \
  --namespace "$NAMESPACE" \
  --version "$CHART_VERSION" \
  --set image.ref="$IMAGE" \
  --atomic --timeout 10m

kubectl -n "$NAMESPACE" rollout status deploy/"$SVC" --timeout=10m
```

`scripts/verify-service.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

ENV="$1"
SVC="$2"
NAMESPACE="$SVC"

# 예시: readiness + 간단한 HTTP health check
kubectl -n "$NAMESPACE" get pod -l app="$SVC" -o wide

# 포트포워딩은 Rundeck 실행 노드/네트워크에 따라 다르니,
# 여기서는 Ingress/Service endpoint를 curl로 확인한다고 가정
URL="https://${SVC}.${ENV}.example.internal/health"

echo "[verify] curl $URL" >&2
curl -fsS "$URL" | head -c 200
echo
```

이런 스크립트 분해가 Conditional Logic와 잘 맞는 이유는, 분기 자체는 Rundeck에서 표현하고, 실행 단위는 script로 관리하면 스텝 재사용이 쉬워지기 때문입니다. 스크립트는 CI에서 lint/test도 가능해집니다.

## 6.3.0 마이그레이션에서 놓치기 쉬운 함정: job.serverUrl trailing slash 제거

6.3.0에서 `${job.serverUrl}`이 더 이상 `/`로 끝나지 않습니다. 릴리스 노트의 설명은 “절대 경로를 안전하게 붙일 수 있게 하기 위해서”입니다. 예시도 `${job.serverUrl}/api/50/projects`처럼 “슬래시를 명시적으로 넣어라”는 방향입니다.[^1]

깨지는 패턴은 명확합니다.

- 이전: `${job.serverUrl}api/50/...` (serverUrl이 `/`로 끝났다는 전제)
- 이후: `${job.serverUrl}api/50/...` → `https://rundeck.example.comapi/50/...` 같은 형태가 되어 실패

운영에서 더 곤란한 건, 이게 “컴파일 에러”가 아니라 “런타임에서 외부 호출 실패”로 터진다는 점입니다. 특히 webhook callback URL을 job.serverUrl 기반으로 만들거나, Rundeck API를 자기 자신에게 호출하는 형태(자기 참조)를 썼던 잡은 한 번에 잡아야 합니다.

내가 적용한 표준은 단순했습니다.

1) 잡 정의를 SCM으로 관리한다면, 레포에서 `${job.serverUrl}api` 패턴을 grep해서 전부 교체합니다.

```bash
grep -R "\${job.serverUrl}api" -n ./rundeck-jobs || true
```

2) 교체 규칙은 하나로 고정합니다.

- 무조건 `${job.serverUrl}/api/...`로 작성
- URL join을 스크립트에서 할 때는 base URL 끝의 `/`를 제거하는 normalize 함수를 둠

3) 잡 실행 노드가 reverse proxy 뒤에 있을 때(특히 TLS termination) URL과 cookie 보안 속성 관련 이슈가 터질 수 있는데, 6.3.0에는 `rundeck-cli` 세션 로그인 관련 리그레션 수정도 포함되어 있었습니다. 이 범주는 “serverUrl 관련 변경은 생각보다 파급이 넓다”는 신호로 봤습니다.[^1]

## eMudhra intermediate CA compromise: 신뢰 체인이 깨지면 ‘업데이트’가 아니라 ‘재배포’가 된다

사건 자체를 요약하면 이렇습니다.

- 2026-10-20에 eMudhra가 운영하는 intermediate CA 8개의 private key가 compromise됐고, “공개된 인증서에서 키를 복구할 수 있다”고 공개되었습니다. Rundeck 문서도 “키는 public certificate에서 복구 가능”하다고 명시합니다.[^2]
- 이 intermediate들은 Mozilla/Microsoft/Apple/Chrome 루트 프로그램에서 신뢰되는 루트들(emSign ECC Root CA - G3 등)로 체인이 이어질 수 있고, on-path 공격자가 TLS 서버를 가장할 수 있습니다.[^2]
- 브라우저는 revocation/CT/OneCRL 같은 메커니즘으로 상대적으로 방어가 되지만, 서버/컨테이너의 non-browser TLS 클라이언트(Java/Go/Python/Node/curl 등)는 trust store 업데이트가 늦으면 그대로 노출됩니다. 이 방향성은 Rundeck 권고와 Mozilla의 공지에서도 일치합니다.[^2]

여기서 Rundeck 관점의 핵심은 “Rundeck 코드가 취약한 게 아니어도, Rundeck가 올라가는 컨테이너 이미지의 trust store가 사고를 포함할 수 있다”는 점입니다. Rundeck 보안 권고는 영향을 받는 범위를 아주 구체적으로 구분합니다.

- 영향 있음: 공식 Rundeck/Runbook Automation Docker 이미지(6.3.0 이전)[^2]
- 영향 없음: Runbook Automation SaaS[^2]
- 케이스 바이 케이스: RPM/DEB/WAR 같이 호스트 설치(호스트 OS/JRE trust store 관리 상태에 달림)[^2]

그리고 remediation은 “업그레이드 후 재배포”입니다. 특히 컨테이너 안에서 `apt-get upgrade`로 해결하려는 습관을 잘라냅니다. 재생성되면 사라지는 변경이라서 운영 표준으로 삼으면 안 됩니다.[^2]

### 검증 커맨드가 ‘curl 한 줄’로 제공될 때의 의미

Rundeck 권고는 검증 방법도 제공합니다. 컨테이너/호스트에서 아래 URL을 curl 했을 때 certificate error가 나야 “더 이상 취약 intermediate를 신뢰하지 않는다”는 뜻입니다. 성공 응답이 오면 아직 신뢰하고 있으니 조치가 필요합니다.[^2]

다만 같은 문서가 즉시 경고합니다. 이 체크는 curl이 OS trust store를 읽기 때문에 “Java trust store는 별개”라는 점입니다. Rundeck가 Java 위에서 동작한다는 사실을 생각하면, 컨테이너 이미지에서는 둘 다 패치돼야 하고, 호스트 설치에서는 OS/JRE 업데이트 루트가 분리될 수 있습니다.[^2]

이 메시지를 운영 규칙으로 번역하면 다음이 됩니다.

- 배포 파이프라인에서 “curl 검증”을 추가하되, 그것을 최종 안전 판정으로 삼지 않는다.
- Java/JRE trust store 업데이트 경로를 별도로 문서화한다.
- 컨테이너 기반 배포에서는 “패치=재빌드/재배포”를 원칙으로 한다.

## 배포 파이프라인에서 ‘신뢰 체인 사고’를 표준 처리로 만드는 방법

신뢰 체인 사고는 보통 이렇게 터집니다.

- 어느 날 갑자기 외부 API 호출이 TLS handshake 실패로 망가지거나
- 반대로, “원래 실패해야 하는 연결이 성공”하면서 위험한 상태가 생깁니다

Rundeck의 eMudhra 권고는 후자에 가깝습니다. “취약 intermediate를 신뢰하면 curl이 성공한다”가 위험 신호입니다.[^2]

나는 이런 사고를 CI/CD 파이프라인에서 처리할 때, 기술보다 ‘표준 단위’를 먼저 고정했습니다.

- 표준 입력: (image ref, expected policy)
- 표준 출력: (pass/fail, 재배포 티켓/PR 링크)
- 표준 실행 위치: (CI runner, 혹은 전용 검증 노드)

Rundeck를 쓰는 조직에서는 이걸 Rundeck 잡으로 만들 수도 있고, CI에서만 돌릴 수도 있습니다. 핵심은 “사고 대응을 사람이 기억하는 체크리스트로 두지 말고, 실행 가능한 잡/스텝으로 박아두는 것”입니다. 이 방향은 과거에 CISA KEV 기반 패치 우선순위를 자동화했던 글에서 말한 것과 동일한 결론으로 이어집니다. [CISA KEV로 패치 우선순위 엔진 만들기](https://daewooki.github.io/posts/kev-patch-priority-engine/)

### (1) Rundeck 자체 이미지: 태그가 아니라 digest로 고정하고, pull→redeploy를 강제

먼저 “공식 이미지가 어떤 태그로 배포되는지”가 기준점입니다. Docker Hub 기준 rundeck/rundeck에는 `6.3.0`과 빌드 태그 `6.3.0-20261022`가 같이 올라와 있고(같은 digest), 이것이 6.3.0 GA 이미지의 식별자입니다.[^8]

운영 표준은 다음처럼 잡았습니다.

- k8s/compose/nomad 어디든, 태그만 쓰지 말고 digest를 고정한다.
- 업스트림 사고가 났을 때는 digest가 바뀌는 순간을 “변경 이벤트”로 감지한다.

digest를 얻는 건 로컬에서도 됩니다.

```bash
IMAGE="rundeck/rundeck:6.3.0-20261022"

docker pull "$IMAGE"

docker inspect --format '{{index .RepoDigests 0}}' "$IMAGE"
# 예상 출력 형태:
# rundeck/rundeck@sha256:aaaaaaaa....
```

이걸 Helm values나 compose, 혹은 내부 Golden Image Dockerfile에 박습니다.

```Dockerfile
# digest는 위 커맨드로 구한 값을 사용
FROM rundeck/rundeck@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

# (조직 표준) 플러그인/CA 번들/설정 등을 여기에 고정
```

이 단계가 중요한 이유는, “태그는 같지만 이미지가 교체되는” 상황이 실제로 있고, 반대로 “태그가 올라가기 전에 digest만 바뀌는” 내부 레지스트리 미러링 구조도 존재하기 때문입니다.

### (2) CA trust store 검증: 컨테이너 내부에서 curl 체크를 파이프라인 게이트로 둔다

Rundeck 권고의 curl 검증은 그대로 자동화하기 좋습니다. 단, 성공/실패의 의미를 반대로 해석해야 합니다.

- certificate error(실패) = 통과(더 이상 신뢰하지 않음)
- 200 OK(성공) = 실패(아직 신뢰함)

아래는 컨테이너 이미지에 대해 검사하는 실행 가능한 스크립트입니다.

`scripts/check-emudhra-trust.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

IMAGE="$1"

docker run --rm --entrypoint bash "$IMAGE" -lc '
  set -euo pipefail
  URL="https://dv-g3b-emudhra.we-have-a-problem.com/"
  echo "[check] curl $URL" >&2

  if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "FAIL: this image still trusts compromised intermediates" >&2
    exit 10
  else
    echo "PASS: curl failed as expected (distrust)" >&2
  fi
'
```

실행 예:

```bash
chmod +x scripts/check-emudhra-trust.sh

scripts/check-emudhra-trust.sh rundeck/rundeck:6.3.0-20261022
# 예상 출력(개념):
# PASS: curl failed as expected (distrust)
```

이 체크가 공식 문서의 “verification” 섹션과 동일하다는 점이 중요합니다. 사람마다 다른 사이트/방법으로 검증하면, 사고 때마다 결론이 갈리기 쉽습니다.[^2]

### (3) 재배포 표준: “컨테이너 안에서 패치”를 금지하고, redeploy만 허용

Rundeck 권고가 명시적으로 말하는 바는 이겁니다. 실행 중인 컨테이너에서 `apt-get upgrade`로 수정해도 컨테이너를 재생성하면 사라지니 지속적인 해결이 아니라는 것.[^2]

이걸 조직 표준으로 옮기면 이렇게 됩니다.

- (금지) 컨테이너 내부에서 운영자가 손으로 패치
- (허용) 이미지 교체 → 재배포 → 검증 잡 실행 → 변경 이력 남김

이 표준은 Rundeck만의 얘기가 아닙니다. base image의 CA bundle/JRE trust store가 사고를 포함하는 순간, 재빌드/재배포가 유일하게 반복 가능한 복구 시나리오가 됩니다.

나는 이 규칙을 “운영 문서”가 아니라 “파이프라인 정책”으로 구현하는 편을 선호합니다. 개발자 머신/CI에 툴 설치를 표준화했던 방식과 동일한 결론입니다. [AWS Tools Installer V2로 개발자 머신과 CI의 AWS 툴 설치를 표준화하기](https://daewooki.github.io/posts/standardize-aws-toolchain-installs/)

## Conditional Logic로 ‘신뢰 체인 사고 대응’까지 흡수하기: 잡 복제를 줄이면서 표준 대응을 붙인다

여기서 흥미로운 결합이 가능합니다.

- 기존에는 “배포 잡”과 “보안 점검 잡”이 분리되며, 환경별로 또 복제됩니다.
- Conditional Logic가 있으면 “배포 잡 내부”에 신뢰 체인 점검을 옵션 기반으로 붙일 수 있습니다.

예를 들어 `security_precheck=true/false` 옵션을 두고, prod에서는 강제(true)로 고정하고 dev에서는 선택으로 둡니다. 핵심은 “보안 대응 스텝을 별도 잡으로 만들지 않고도 정책을 집어넣을 수 있다”는 점입니다.

Conditional Logic 문서가 말하는 대표 사례(환경/region 조합을 분기 조합으로 만들지 말고 invertLogic으로 관리하라)도 같은 맥락입니다. 조합 수를 늘리지 말고 정책 축을 유지하라는 메시지입니다.[^4]

### 배포 잡에 신뢰 체인 프리플라이트를 붙이는 예시

```yaml
  options:
    - name: security_precheck
      required: true
      values: ["true", "false"]

  sequence:
    commands:
      - type: conditional
        nodeStep: false
        description: force-precheck-on-prod
        conditionGroups:
          - - key: "${option.env}"
              operator: "=="
              value: "prod"
        subSteps:
          - exec: |-
              # prod는 옵션을 무시하고 강제 수행
              ./scripts/check-trust-chain.sh

      - type: conditional
        nodeStep: false
        description: optional-precheck
        conditionGroups:
          - - key: "${option.env}"
              operator: "!="
              value: "prod"
            - key: "${option.security_precheck}"
              operator: "=="
              value: "true"
        subSteps:
          - exec: |-
              ./scripts/check-trust-chain.sh
```

여기서 `check-trust-chain.sh`는 “내가 중요하다고 보는 이미지 목록”에 대해 앞서 만든 curl 검증 같은 것을 일괄 수행하게 만들면 됩니다.

이 구조의 이점은 세 가지입니다.

- 사고가 터졌을 때 배포를 중지시키는 게 아니라, 배포 경로 안에서 프리플라이트를 실패시켜 멈춥니다.
- 운영자가 보안 공지를 읽고 기억해서 실행하는 게 아니라, 잡 실행 자체가 정책을 수행합니다.
- 잡을 환경별로 복제하지 않아도 “prod는 강제, dev는 선택” 같은 정책 차이를 표현할 수 있습니다.

## Conditional Logic 도입 판단 기준: 잡을 합칠지 말지의 기준을 ‘변수’가 아니라 ‘변경률’로 잡는다

Conditional Logic를 도입할지 고민할 때, 나는 다음 질문으로 결정합니다.

1) 이 분기는 앞으로 늘어날 가능성이 큰가?

- 늘어날 가능성이 크면 Conditional Logic로 흡수하는 편이 좋습니다.
- 늘어날 가능성이 낮으면 잡을 분리해서 경계를 명확히 하는 편이 낫습니다.

2) 분기 축이 정책인가, 구현인가?

- 정책(env별 승인/보호 장치, 사고 대응 프리플라이트)은 한 잡 안에서 보이는 편이 운영에 유리합니다.
- 구현(전혀 다른 배포 방식, 전혀 다른 대상 시스템)은 잡 분리가 낫습니다.

3) 외부 호출자(챗봇/CI/PagerDuty)가 잡 ID를 기준으로 연동하는가?

- 잡 ID가 많아질수록 외부 시스템의 라우팅 규칙이 복잡해지고, 이것이 또 다른 운영 부채가 됩니다.

6.3.0에서 Conditional Logic가 GA로 올라오면서(그리고 기본 활성화되면서) “이 기능을 써도 되나?”가 아니라 “이 기능을 쓰지 않으면 잡 복제가 계속 비용이 되나?”로 질문이 바뀌었다고 느꼈습니다.[^1]

## 결론: 6.3.0은 기능 업데이트가 아니라 운영 모델을 교정하는 릴리스다

이번 6.3.0의 결을 한 문장으로 정리하면 이렇습니다.

- Conditional Logic GA는 잡 복제를 줄여서 자동화의 변경 비용을 낮추는 방향이고,[^1]
- eMudhra intermediate CA 대응은 “컨테이너 기반 운영에서 신뢰 체인 사고는 redeploy로 수렴한다”는 현실을 강제합니다.[^2]

여기에 `${job.serverUrl}` trailing slash 제거 같은 작은 변경은 “운영 잡이 결국 소프트웨어”라는 사실을 다시 보여줍니다. 자동화가 커질수록, 잡은 더 이상 클릭으로 만드는 운영 문서가 아니라, 리팩터링/검증/배포가 필요한 코드에 가까워집니다.[^1]

내 결론은 단순합니다. Conditional Logic로 잡 복제를 줄인 만큼, 배포 파이프라인에는 trust chain 검증과 redeploy 표준을 같이 넣어야 운영의 총비용이 내려갑니다.

## 참고 자료

- [Runbook Automation/Rundeck 6.3.0 Release Notes](https://docs.rundeck.com/docs/history/6_x/version-6.3.0.html)
- [Recent Updates: Self-Hosted 6.3.0 released ahead of SaaS](https://docs.rundeck.com/docs/history/updates/)
- [Security Advisory: eMudhra Intermediate CA Compromise](https://docs.rundeck.com/docs/history/cves/2026-10-emudhra-ca.html)
- [Conditional Logic Steps 문서](https://docs.rundeck.com/docs/manual/jobs/conditional-logic.html)
- [Using Conditional Logic in a Job 가이드](https://docs.rundeck.com/docs/learning/howto/using-conditional-logic.html)
- [Configuration File Reference: rundeck.feature.earlyAccessJobConditional.enabled](https://docs.rundeck.com/docs/administration/configuration/config-file-reference.html)
- [Rundeck Docker Hub tags (6.3.0 / 6.3.0-20261022)](https://hub.docker.com/r/rundeck/rundeck/tags)
- [Mozilla Bug 2083449: eMudhra intermediate private key compromise](https://bugzilla.mozilla.org/show_bug.cgi?id=2083449)
- [Mozilla Security Blog: Protecting Firefox users following the compromise](https://blog.mozilla.org/security/2026/10/20/protecting-firefox-users-following-the-compromise-of-emudhra-intermediate-certificates/)

[^1]: <https://docs.rundeck.com/docs/history/6_x/version-6.3.0.html>
[^2]: <https://docs.rundeck.com/docs/history/cves/2026-10-emudhra-ca.html>
[^3]: <https://docs.rundeck.com/6.1.0/history/5_x/version-5.20.0.html>
[^4]: <https://docs.rundeck.com/docs/manual/jobs/conditional-logic.html>
[^5]: <https://docs.rundeck.com/docs/learning/howto/using-conditional-logic.html>
[^6]: <https://docs.rundeck.com/docs/manual/document-format-reference/job-yaml-v12.html>
[^7]: <https://docs.rundeck.com/6.1.0/history/6_x/version-6.1.0.html>
[^8]: <https://hub.docker.com/r/rundeck/rundeck/tags>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
