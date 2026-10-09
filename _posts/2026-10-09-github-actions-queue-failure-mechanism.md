---
title: "GitHub Actions 장애에서 본 CI 큐 붕괴 메커니즘"
description: "부분 네트워크 장애가 GitHub-hosted runner 할당을 막을 때, job start SLO·큐 적체 흡수·셀프호스티드 플랜·재시도 폭풍 방지 패턴을 정리합니다."
date: 2026-10-09 11:26:07 +0900
categories: ["News", "DevOps"]
tags: ["github-actions", "ci-reliability", "queued-jobs", "self-hosted-runners", "concurrency"]
render_with_liquid: false
---

## 무슨 일이 있었나: “DB/스토리지로 가는 길이 끊기면, runner가 있어도 job은 못 뜬다”

GitHub Status는 2026년 10월 5일 18:48~22:49 UTC 동안 GitHub Actions와 GitHub-hosted runners에서 성능 저하가 있었다고 공지했습니다. 원인은 “온프렘 데이터센터 리전(on-premises datacenter regions)과 일부 클라우드 호스팅 regional database / storage 서비스 간 연결 장애”였습니다.[^1]

수치가 이번 건을 더 실전적으로 만듭니다.

- 전체 사고 구간(18:48~22:49 UTC) 동안 GitHub-hosted runner를 쓰는 workflow run의 14.3%가 실패했고, 개별 job 기준으로 26.5%가 **5분 내 시작하지 못했습니다.**[^1]
- 영향이 가장 컸던 약 90분 구간에서는 workflow run의 47.0%가 실패했고, 개별 job의 71.9%가 5분 내 시작하지 못했습니다.[^1]
- GitHub Status는 “Self-hosted runners는 영향을 받지 않았다”고 명시했습니다.[^1]

시간대를 KST로 바꾸면 더 감이 옵니다(UTC+9).

- 장애 시작: 2026-10-05 18:48 UTC = 2026-10-06 03:48 KST
- Actions/Hosted Runners 회복 시각: 2026-10-05 21:54 UTC = 2026-10-06 06:54 KST
- 전체 회복: 2026-10-05 22:49 UTC = 2026-10-06 07:49 KST

개발팀 입장에서는 “새벽에 PR이 쌓이고, 아침 출근 전에 돌려둔 빌드/테스트가 5분은커녕 1시간 넘게 queued로 서 있다”가 됩니다. 이때 사람들은 대개 두 가지 행동을 합니다.

1) rerun / retry를 누르기 시작합니다.
2) 병렬도를 올리거나(매트릭스 확장), 새 커밋을 여러 번 푸시하면서 “어차피 다시 돌 거”라는 식으로 큐를 더 태웁니다.

이 글의 초점은 “GitHub가 잘못했다”가 아니라, 이런 유형의 장애가 다시 왔을 때 워크플로 설계가 어떻게 달라져야 하는지입니다.

## 배경과 맥락: 퍼블릭 CI(SaaS)의 실패 모드는 ‘실행 실패’보다 ‘시작 실패’가 먼저 온다

CI 장애를 단순화하면 보통 세 단계입니다.

- Trigger 실패: push/PR 이벤트가 workflow run으로 안 만들어짐
- Start 실패: run은 생겼는데 job이 runner에 배정되지 못해 queued에 오래 머뭄
- Execute 실패: runner에서 job은 시작했는데, checkout/artifact/cache/registry 같은 외부 의존성에서 실패

이번 공지에서 GitHub가 선택한 지표가 “5분 내 시작”입니다. 즉, 실행 시간보다 **job start**가 먼저 무너졌고, 그 자체가 서비스 품질을 대표한다고 판단했다는 의미입니다.[^1]

여기서 중요한 포인트는 “부분 네트워크 실패(partial networking failure)”라는 표현입니다. 전면 장애가 아니라 경로 일부가 망가진 형태는 관측도 어렵고, 자동 복구도 늦어지기 쉽습니다. 특히 “온프렘↔클라우드 managed DB/스토리지”처럼 서로 다른 운영 도메인(장비, 라우팅, 보안 정책, 장애 감지 체계)이 만나는 경계면이 끊기면, 증상은 애매해집니다.

- API가 전체적으로 죽은 건 아니라서, UI에서 run은 계속 생성됩니다.
- 그러나 runner 할당이나 job 상태 업데이트처럼 DB/스토리지에 강하게 묶인 경로는 지연/실패합니다.
- 그 결과, 개발자는 “왜 run은 생기는데 job이 시작을 안 하지?”를 한참 디버깅하다가 status를 보고서야 납득합니다.

이런 유형의 장애는 “실행 실패”보다 “시작 실패”가 더 파괴적입니다. 시작이 안 되면 다음이 발생합니다.

- SLA가 아니라 SLO 관점에서, 사용자가 체감하는 시간의 대부분이 queued로 소비됩니다.
- queued backlog가 쌓이면서, 장애가 끝난 뒤에도 회복이 지연됩니다(Queue draining 문제).
- 사람 손 rerun이 결합되면 재시도 폭풍(retry storm)이 됩니다.

## “온프렘↔클라우드 DB/스토리지” 경로가 무너지면 왜 CI 큐가 타나: 내가 이해한 붕괴 흐름

GitHub는 내부 아키텍처를 상세히 공개하진 않았고, 이번 사고 보고서도 “어떤 DB, 어떤 storage, 어떤 트래픽”까지는 말하지 않습니다. 그래서 아래는 GitHub가 공개한 원인 문장과 관측된 증상을 연결한 추론입니다. 다만, 추론이 성립하는 이유는 GitHub Actions runner가 “GitHub Actions 서비스로부터 job assignment를 받는다”는 구조적 사실이 있기 때문입니다.[^2][^3]

내가 보는 붕괴 흐름은 다음과 같습니다.

### 1) workflow run은 생성되는데, runner 배정이 늦어진다

GitHub Status 업데이트 로그에서도 증상이 “delays in assigning GitHub-hosted runners, affecting workflow start times”로 반복됩니다.[^1]

job이 runner에 배정되려면 최소한 아래 데이터 흐름이 안정적이어야 합니다.

- job metadata(어떤 repo/sha, 어떤 permissions, 어떤 secrets scope, 어떤 runner label, 어떤 concurrency group, 어떤 timeout 등)
- runner provisioning / allocation 상태
- job-queue / assignment 메시지 전달
- job 시작/진행/종료 상태 기록

이 중 일부가 regional DB나 storage에 의존하면, 네트워크 경로가 부분적으로 끊긴 순간부터 “할당 자체가 실패하거나, 할당 후 상태 업데이트가 실패해서 재할당/재큐잉 루프”로 빠질 수 있습니다.

### 2) “5분 내 시작 못함”이 폭증하면, queued backlog가 자기증폭한다

사고 보고서에서 peak 구간에 71.9%의 job이 5분 내 시작하지 못했다고 했습니다.[^1]

여기서 중요한 건 5분이라는 숫자 자체가 아니라, “대다수 job이 start SLO를 깨는 순간부터” 시스템이 다음 단계를 동시에 맞는다는 점입니다.

- (사용자 행동) rerun/재푸시/매트릭스 확장으로 유입량이 늘어남
- (시스템 반응) 회복을 위해 capacity를 올리거나 failover를 수행하지만, 이미 쌓인 backlog는 즉시 해소되지 않음

GitHub도 완화(mitigation) 조치로 “healthy region/endpoints로 DB·스토리지 트래픽을 shifting”하고 “영향받은 compute 서비스 capacity 증가”를 했다고 밝혔습니다.[^1]

이건 반대로 말하면, 병목이 compute만이 아니라 DB/스토리지 경로였고, 회복 과정에서도 트래픽 우회와 capacity 증설이 동시에 필요할 만큼 큐가 눌려 있었다는 뜻입니다.

### 3) Self-hosted runners가 이번에는 살았지만, 항상 안전한 건 아니다

사고 보고서에는 “Self-hosted runners were not affected”라고 되어 있습니다.[^1]

다만 self-hosted runner의 본질은 “실행 머신을 우리가 소유한다”이지, “오케스트레이션/큐/할당/control plane을 우리가 소유한다”가 아닙니다. runner는 GitHub에 연결해서 job assignment를 받아야 합니다.[^3]

즉, 장애가 “hosted runner provisioning 영역”에만 걸리면 self-hosted가 구명정이 될 수 있지만, 장애가 “Actions 서비스 자체(큐·할당·토큰 발급·상태 저장)”를 치면 self-hosted도 같이 멈출 수 있습니다. 이 구분을 워크플로 설계에서 분리해두지 않으면, self-hosted를 구축해도 기대한 복원력이 안 나옵니다.

## 왜 중요한가: job start SLO를 ‘우리 CI의 외부 의존성 허용치’로 격상해야 한다

내가 운영 관점에서 가장 크게 느낀 건 이겁니다.

- 대부분 팀의 CI SLO는 “빌드가 10분 내 끝난다” 같은 execution 중심입니다.
- 그런데 SaaS CI에서는 start(queued→in_progress)가 execution보다 먼저 깨집니다.

GitHub도 이번 사고에서 “5분 내 start 못한 비율”을 핵심 지표로 박았습니다.[^1]

그러면 팀 입장에서도 최소한 다음 두 SLO를 분리해서 잡아야 합니다.

- Job start SLO: queued 상태에서 시작까지 p95/p99가 얼마인지
- Job execution SLO: in_progress 이후 완료까지 p95/p99가 얼마인지

GitHub는 Actions Metrics에서 평균 queue time과 실패율을 제공합니다.[^4]

평균(avg)은 장애에 둔감합니다. 하지만 지금 당장 쓸 수 있는 베이스라인으로는 충분합니다.

- 평시 평균 queue time이 5~10초인 repo는, 2~3분만 되어도 이미 “비정상”입니다.
- 평시 평균 queue time이 1~2분인 repo는, 5분이 넘는 순간부터 “SaaS 의존성 장애 모드”로 들어간 겁니다.

그리고 이 SLO는 단지 모니터링이 아니라, 워크플로 설계를 갈라야 하는 기준이 됩니다.

- start SLO가 깨지면: “유입량을 줄이고, 큐를 흡수하고, 사람의 재시도를 제어”하는 설계가 필요
- execution SLO가 깨지면: “캐시/아티팩트/레지스트리/테스트 병렬도/리소스” 설계가 필요

## 큐 적체를 흡수하는 설계: concurrency는 ‘락’이 아니라 ‘backpressure’다

GitHub Actions의 concurrency는 흔히 “배포 중복 방지” 수준으로만 씁니다. 그런데 SaaS 장애 모드에서는 concurrency가 backpressure 도구가 됩니다.

### 1) obsolete run을 버리는 것이 큐 보호의 시작이다

PR에서 같은 브랜치에 커밋이 연속으로 올라오면, 이전 커밋에 대한 CI 결과는 가치가 급락합니다. 이때 queued backlog가 쌓이면, 최신 커밋 검증까지 밀려서 개발이 멈춥니다.

그래서 PR 성격의 workflow는 기본값을 “최신만 살린다”로 두는 편이 낫습니다.

- `cancel-in-progress: true`로 같은 그룹의 in-progress까지 취소
- 그룹 키는 `workflow + PR number` 정도로 고정

관련 문서: [Concurrency 개념](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency), [Workflow concurrency 제어](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

예시:

```yaml
name: pr-ci
on:
  pull_request:

concurrency:
  group: pr-ci-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm test
```

이 패턴은 장애가 없을 때도 비용을 줄이지만, 장애가 있을 때는 “queue length 자체를 줄여서 start SLO를 방어”합니다.

### 2) 순차 실행이 필요한 흐름은 `queue: max`로 ‘기다리게’ 만들되, 상한을 의식한다

GitHub Actions는 concurrency 그룹에서 기본적으로 pending 1개만 허용하고, 새 run이 오면 이전 pending을 취소합니다.[^5]

그런데 2026년 5월부터 `queue: max`로 동일 그룹에서 최대 100개까지 pending을 줄 세울 수 있게 바뀌었습니다.[^6]

여기서 내가 보는 사용처는 딱 하나입니다.

- “절대 취소되면 안 되는 run”을 줄 세워서 유실을 막되,
- backlog 상한을 100으로 걸어 시스템을 보호한다.

예를 들어 production deploy 같은 흐름은 최신만 남기는 게 아니라, 순서대로 나가야 할 때가 있습니다(릴리스 노트/체인지로그/마이그레이션 스크립트/고객 커뮤니케이션). 이때는 cancel보다 queue가 낫습니다.

```yaml
name: deploy-prod
on:
  push:
    branches: [ main ]

concurrency:
  group: deploy-prod
  cancel-in-progress: false
  queue: max

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - run: ./scripts/deploy-prod.sh
```

주의할 점도 문서에 명시되어 있습니다.

- `queue: max`의 상한은 100입니다.[^5]
- workflow run 자체에도 rate limit이 있습니다. repo당 10초에 500 runs를 넘기면 “queued가 아니라 blocked”가 됩니다.[^7]

SaaS 장애 상황에서 사람들이 rerun을 누르기 시작하면, concurrency로 막는 것만으로는 부족하고 “rerun을 누르지 않게 만드는 제어 장치”가 필요합니다. 그게 다음 섹션의 재시도 폭풍 방지입니다.

## 재시도 폭풍을 막는 패턴: retry를 ‘기능’이 아니라 ‘부하’로 취급한다

장애가 났을 때 많은 팀이 “실패하면 3번 재시도”를 자동화합니다. 평시에는 유용합니다. 하지만 시작 실패(start failure) 유형에서는 retry가 부하 증폭기입니다.

- queued가 쌓여서 start가 늦어지는 상황에서 retry는 queued를 더 늘립니다.
- 더 나쁜 건 “사람 손 rerun + 자동 retry”가 같이 돌 때입니다.

GitHub는 workflow rerun 횟수에도 상한을 둡니다(한 run당 최대 50 reruns).[^7]

이 상한은 보호장치이긴 한데, 그 전에 이미 팀은 CI를 신뢰하지 못하게 됩니다.

### 1) workflow/job 레벨 “자동 재시도”는 장애 모드에서 꺼지는 스위치가 있어야 한다

내가 선호하는 방식은 retry 자체를 없애라는 게 아니라, **circuit breaker** 형태로 바꾸는 겁니다.

- 평시: 네트워크 flake, 레지스트리 429 같은 transient error에만 제한적으로 retry
- 장애 모드: retry를 즉시 중단하고, backlog가 빠지는 걸 기다림

장애 모드를 감지하는 신호로는 GitHub Status의 API를 쓸 수 있습니다.

- GitHub Status는 `/api/v2/incidents/unresolved.json` 같은 엔드포인트를 제공합니다.[^8]
- Atlassian Statuspage 자체도 webhook/구독 API가 있지만, 최소 구현은 “공개 JSON 폴링”이면 됩니다.[^9]

여기서 중요한 전제는, “Actions 자체가 멎어서 workflow가 시작조차 안 되는 상황”을 이걸로 해결할 수는 없다는 점입니다. 다만 다음 두 경우에는 효과가 있습니다.

- Actions가 느리지만 job은 시작되는 상황(peak가 지나 회복 중, 또는 일부 repo만 영향)
- 외부 스케줄러에서 workflow_dispatch를 쏘는 구조(뒤에서 다룸)

### 2) (실행 가능한 예시) GitHub Status 기반 preflight gate 스크립트

Python 3.11 기준, 의존성은 `requests` 하나로 끝냅니다.

`gha_status_gate.py`:

```python
#!/usr/bin/env python3
import argparse
import sys
import time
import requests

GITHUB_STATUS_UNRESOLVED = "https://www.githubstatus.com/api/v2/incidents/unresolved.json"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--component", default="Actions", help="Component name to match, e.g. Actions, Pages")
    ap.add_argument("--max-age-seconds", type=int, default=900, help="Ignore incidents older than this")
    args = ap.parse_args()

    r = requests.get(GITHUB_STATUS_UNRESOLVED, timeout=10)
    r.raise_for_status()
    data = r.json()

    now = time.time()
    incidents = data.get("incidents", [])

    matched = []
    for inc in incidents:
        # created_at example: 2026-10-05T19:11:00.000Z
        created_at = inc.get("created_at")
        # naive parse: drop fractional + Z
        ts = None
        if created_at and created_at.endswith("Z"):
            created_at = created_at.replace(".000Z", "Z")
            try:
                ts = time.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
                ts = time.mktime(ts)
            except Exception:
                ts = None

        if ts and (now - ts) > args.max_age_seconds:
            continue

        name = inc.get("name", "")
        status = inc.get("status", "")  # investigating/identified/monitoring
        impact = inc.get("impact", "")  # minor/major/critical

        # component list may not include names consistently, so match on incident name too.
        if args.component.lower() in name.lower():
            matched.append((name, status, impact, inc.get("shortlink")))

    if matched:
        for (name, status, impact, shortlink) in matched:
            print(f"DEGRADED: {name} status={status} impact={impact} link={shortlink}")
        # exit 2 => caller decides to stop dispatch/retry
        return 2

    print("OK: no recent unresolved incidents matching component filter")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

실행:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
python gha_status_gate.py --component Actions
```

예상 출력:

- 정상일 때

```
OK: no recent unresolved incidents matching component filter
```

- 장애가 열려 있을 때(예시)

```
DEGRADED: Incident with Actions status=investigating impact=major link=http://stspg.co/...
```

이 스크립트는 “Actions 장애가 열려 있으면 exit code 2”를 반환합니다. 이 exit code를 이용해 다음을 막는 쪽으로 씁니다.

- 외부에서 workflow_dispatch를 쏘는 자동화
- 내부에서 retry를 수행하는 단계(예: flaky test rerun)

## 셀프호스티드 러너/미러 플랜: ‘runner를 갖는 것’과 ‘control plane을 갖는 것’을 분리한다

이번 사고 보고서만 놓고 보면, self-hosted runner는 구명정처럼 보입니다. 실제로 GitHub는 “Self-hosted runners were not affected”라고 못 박았습니다.[^1]

하지만 팀이 의사결정을 하려면, self-hosted의 보호 범위를 더 잘게 나눠야 합니다.

### 1) self-hosted가 잘 듣는 장애: hosted runner 할당/프로비저닝 병목

GitHub-hosted runner는 GitHub가 VM/컨테이너를 준비해서 job을 실행시킵니다. 이 경로에 장애가 있으면 queued가 길어집니다. 이때 self-hosted는 “이미 켜져 있는 실행 노드”이므로 start SLO를 방어할 여지가 있습니다.

다만 이것도 “Actions 서비스가 job을 self-hosted에게 할당할 수 있는 상태”라는 전제가 붙습니다. self-hosted runner는 GitHub에 연결해 job assignment를 받는 구조입니다.[^3]

### 2) self-hosted가 못 막는 장애: GitHub Actions control plane 자체의 병목

runner가 아무리 많아도 다음이 깨지면 job은 못 뜹니다.

- 큐/할당 서비스
- job token/permissions 발급
- run 상태 저장

이 영역은 runner 소유권과 무관하게 GitHub가 제공합니다. 그래서 self-hosted는 “컴퓨팅의 소유권”이지 “오케스트레이션의 소유권”이 아닙니다.

### 3) 그래서 미러 플랜은 2단계가 된다

내가 권하는 미러 플랜은 대체로 아래 2단계입니다.

- Plan A: GitHub Actions + GitHub-hosted runners
- Plan B: GitHub Actions + self-hosted runners(ARC/scale set 등으로 자동 확장)
- Plan C: GitHub Actions 자체가 아니라 다른 CI control plane(예: Buildkite/Jenkins/GitLab CI 등)

Plan B는 “hosted runner 경로 장애”에 강해집니다. Plan C는 “GitHub control plane 장애”까지 포함해서 방어합니다.

Plan B 구현에서 최근 현실적인 선택지는 runner scale set 기반입니다.

- GitHub 문서에서 runner scale set 개념을 설명합니다.[^10]
- Kubernetes를 쓴다면 Actions Runner Controller(ARC)의 runner scale set 배포 문서가 있고, `minRunners`/`maxRunners`로 warm pool을 줄 수 있습니다.[^11]

여기서 장애 관점의 핵심은 `minRunners`입니다.

- `minRunners=0`이면 완전 idle 상태에서 첫 job은 cold start 비용을 먹습니다(이미지 pull, runner registration 등).
- start SLO를 방어하려면 “항상 1~N대는 대기”를 걸어야 합니다.

ARC 문서도 `minRunners`를 “항상 지정 개수만큼 active and available”하게 만드는 장치로 설명합니다.[^11]

## 워크플로 설계는 어떻게 달라져야 하나: job start SLO를 중심에 놓고 나누기

여기부터는 “지금 당장 레포에 적용할 수 있는 설계 변화”입니다. 예전 글에서 Actions의 재사용/보안/속도 같은 베스트 프랙티스를 많이 다뤘는데, 이 글은 장애 모드에 한정합니다.

- 배포까지 포함한 end-to-end 관점은 예전 글[^12]에 더 자세히 정리해뒀습니다.
- 보안/재사용/캐시/OIDC 설계는 별도 글[^13][^14]로 분리되어 있습니다.

### 1) workflow를 “빠른 것”과 “무거운 것”으로 분리하고, 장애 시에는 빠른 것만 남긴다

SaaS 장애에서 가장 치명적인 건 “모든 run이 동일한 큐에서 동일한 우선순위로 밀린다”는 점입니다. GitHub Actions는 내부 우선순위를 사용자에게 공개하지 않으므로, 팀이 할 수 있는 건 논리적 분리입니다.

- fast checks: lint/unit 정도(개발 흐름 유지)
- heavy checks: integration/e2e/perf/build image 같은 것(장애 시 중단해도 개발은 계속)

이 분리는 평시에도 유효합니다. queued가 늘어났을 때 heavy가 fast를 눌러버리는 걸 막습니다.

### 2) “queued backlog를 줄이기 위한 취소”와 “순서를 보장하기 위한 큐잉”을 구분한다

- PR 검증: 취소(cancel-in-progress)가 기본
- deploy/release: 큐잉(queue: max) + 상한(100) + 명확한 운영 룰

이걸 섞어 쓰면 장애 시에 복구가 더 늦어집니다.

### 3) rerun 버튼을 누르기 전에 자동으로 ‘중복 run’을 자르는 guard를 둔다

concurrency만으로는 “이미 생성된 run”을 다 줄이지 못합니다. 특히 다음이 문제입니다.

- 서로 다른 workflow 파일이 같은 변경에 의해 동시에 트리거
- 동일 workflow라도, 다른 이벤트(push + pull_request)가 중복으로 트리거

이때는 첫 job에서 “내가 최신이 아니면 조용히 종료”하는 guard가 유효합니다. 이건 장애가 없어도 queue를 얕게 만듭니다.

(예시) PR에서 최신 커밋이 아니면 이후 job을 실행하지 않는 구조:

```yaml
name: pr-ci-guarded
on:
  pull_request:

concurrency:
  group: pr-ci-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  guard:
    runs-on: ubuntu-latest
    outputs:
      is_latest: ${{ steps.check.outputs.is_latest }}
    steps:
      - name: Check whether this run targets the latest PR head SHA
        id: check
        env:
          GH_TOKEN: ${{ github.token }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          THIS_SHA: ${{ github.sha }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          latest_sha=$(gh api \
            -H "Accept: application/vnd.github+json" \
            "/repos/${REPO}/pulls/${PR_NUMBER}" \
            --jq .head.sha)

          if [ "${latest_sha}" = "${THIS_SHA}" ]; then
            echo "is_latest=true" >> "$GITHUB_OUTPUT"
            echo "latest PR SHA matches: ${THIS_SHA}"
          else
            echo "is_latest=false" >> "$GITHUB_OUTPUT"
            echo "not latest: this=${THIS_SHA} latest=${latest_sha}"
          fi

  test:
    needs: [guard]
    if: needs.guard.outputs.is_latest == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm test
```

이 패턴은 “내가 최신이 아닐 때도 run 자체는 생성”되기 때문에, start SLO가 박살 난 상태에서 완벽한 해결책은 아닙니다. 하지만 장애 전/후 경계에서 backlog를 얕게 만들고, 개발자가 rerun을 덜 누르게 만드는 효과는 있습니다.

### 4) 외부 스케줄러로 workflow_dispatch를 쏘는 작업은, Status gate로 재시도를 제어한다

정기 배치/레포트/야간 빌드처럼 “실패했을 때 자동 재시도”가 붙는 작업은 SaaS 장애 때 가장 먼저 재시도 폭풍을 만들기 쉽습니다.

GitHub Actions의 `schedule` 트리거는 GitHub 내부 스케줄러에 의존합니다. 장애 때 스케줄이 늦어지면 사람들이 수동 실행을 누르고, 그 사이 스케줄이 살아나면 중복 실행이 됩니다.

내가 선호하는 방식은 다음입니다.

- (A) 스케줄은 외부에서 관리(예: cron, EventBridge, Cloud Scheduler 등)
- (B) 외부 스케줄러가 GitHub Status를 먼저 확인
- (C) 상태가 정상일 때만 workflow_dispatch 호출

여기서 앞의 `gha_status_gate.py`를 그대로 쓸 수 있습니다. “Actions 장애가 열려 있으면 dispatch를 아예 안 쏜다”가 핵심입니다. GitHub Actions가 느린 상황에서 “내가 재시도를 자동화했기 때문에 더 느려진다”는 자기모순을 끊어야 합니다.

GitHub Status는 공개 API로 unresolved incidents를 제공합니다.[^8]

## 반론과 회의론: “이 정도 장애면 그냥 다른 CI로 옮겨야 하는 거 아닌가?”

이 반응이 나오는 건 정상입니다. 특히 이번 사고는 “일부 job이 느려졌다”가 아니라 peak 구간에 workflow run 실패 47%가 찍혔습니다.[^1]

다만 단기/중기/장기로 나눠보면 판단이 조금 달라집니다.

### 1) 단기: 워크플로 설계를 바꾸면 체감 피해는 크게 줄어든다

- PR workflow는 최신만 남기고 취소
- deploy/release는 큐잉하되 상한을 두고, heavy와 fast를 분리
- retry는 gate를 달아서 장애 모드에서 멈추게

이건 CI 플랫폼을 바꾸지 않고도 가능한 변화입니다.

### 2) 중기: self-hosted는 비용 절감/성능뿐 아니라 “start SLO 방어” 수단이 된다

이번처럼 hosted runner provisioning 쪽이 흔들린 장애에서는 self-hosted가 효과를 볼 수 있습니다(이번 사고 보고서에서도 self-hosted는 영향이 없었다고 명시).[^1]

하지만 self-hosted는 운영 부담이 생깁니다.

- runner 버전 enforcement, 최소 버전 강제 같은 운영 이벤트에 끌려갑니다.[^15]
- cold start를 줄이려면 `minRunners` 같은 상시 대기 비용이 듭니다.[^11]

### 3) 장기: control plane까지 분리하려면 결국 멀티 CI(또는 탈 GitHub)가 된다

GitHub Actions는 코드/PR/권한/토큰/시크릿/리뷰 흐름과 밀접하게 붙어 있고, 이 결합이 생산성을 만듭니다. 동시에 이 결합이 장애 전파 경로가 됩니다.

“GitHub가 멎으면 CI도 멎는다”를 구조적으로 피하려면, runner만이 아니라 control plane을 분리해야 합니다. 이건 단순 마이그레이션이 아니라, 조직의 SDLC 자체를 다시 설계하는 프로젝트가 됩니다.

## 앞으로 지켜볼 것: GitHub가 말한 ‘네트워크 경로 회복력’이 어디까지 개선되는가

GitHub는 이번 사고의 후속으로 “클라우드 제공자와 협력해 network-path resilience, detection, recovery를 개선하겠다”고 밝혔습니다.[^1]

여기서 내가 보고 싶은 건 세 가지입니다.

1) “부분 네트워크 실패” 감지의 민감도: 어느 시점에 자동 우회가 시작되는가
2) DB/스토리지 트래픽 shifting이 자동화되는가, 운영자 수동 개입이 필요한가
3) hosted runner assignment 지연이 발생했을 때, 사용자에게 제공되는 신호(메트릭/로그)가 더 좋아지는가

특히 사용자 입장에서 실질적으로 도움이 되는 건 3)입니다. queued가 늘어날 때 “내 설정 문제인지/서비스 문제인지”를 5분 빨리 알면, 재시도 폭풍 자체가 줄어듭니다.

## 지금 할 수 있는 일: 장애를 전제로 워크플로를 재설계하는 체크리스트

여기까지를 팀 액션으로 바꾸면 다음 순서가 됩니다.

1) job start SLO를 명문화합니다. GitHub가 이번 사고에서 쓴 5분을 그대로 가져와도 됩니다(예: p95 start < 1분, p99 start < 5분). 사고 보고서에 5분 지표가 명시되어 있어, 내부 설득이 쉬워집니다.[^1]

2) GitHub Actions Performance Metrics에서 workflow/job별 평균 queue time을 보고, 평시 베이스라인을 잡습니다.[^4]

3) PR workflow는 cancel-in-progress를 기본값으로 바꿉니다. concurrency는 락이 아니라 backpressure로 봅니다.[^5]

4) 배포/릴리스 workflow는 `queue: max`를 검토하되, 100 상한과 run rate limit(10초 500 run)을 같이 문서화합니다.[^5][^7]

5) 자동 retry는 circuit breaker로 바꿉니다. GitHub Status API를 이용해 장애 모드에서는 retry/dispatch를 멈추는 스위치를 넣습니다.[^8]

6) self-hosted runner는 “비용/성능”이 아니라 “start SLO 방어”로 ROI를 다시 계산합니다. ARC/scale set을 쓴다면 `minRunners`로 cold start를 가릴지(비용) 판단합니다.[^11][^10]

결국 이번 사고가 준 교훈은 단순합니다. 퍼블릭 CI(SaaS)를 쓰는 한, CI는 실행 시스템이기 전에 큐 시스템이고, 신뢰성은 “얼마나 빨리 끝나냐”보다 “얼마나 예측 가능하게 시작하냐”가 먼저 무너집니다. 그래서 워크플로 설계의 중심을 execution 최적화에서 job start SLO와 backpressure 설계로 옮기는 쪽이 맞습니다.

## 참고 자료

- [GitHub Status 사고 보고서: Incident with Actions](https://www.githubstatus.com/incidents/3q1yb5m7ltvb)
- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [Concurrency 개념](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency)
- [Workflow concurrency 제어](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [Concurrency 그룹 큐 확장 변경](https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/)
- [GitHub Actions metrics](https://docs.github.com/en/actions/concepts/metrics)
- [GitHub Status API](https://www.githubstatus.com/api/)
- [Statuspage API 문서](https://developer.statuspage.io/)
- [Self-hosted runners](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners)
- [Self-hosted runners reference](https://docs.github.com/en/enterprise-cloud@latest/actions/reference/runners/self-hosted-runners)
- [Runner scale sets](https://docs.github.com/en/actions/concepts/runners/runner-scale-sets)
- [ARC로 runner scale set 배포](https://docs.github.com/en/actions/how-tos/manage-runners/use-actions-runner-controller/deploy-runner-scale-sets)
- [Self-hosted runner 최소 버전 enforcement 타임라인](https://github.blog/changelog/2026-06-12-github-actions-minimum-version-enforcement-timeline-for-self-hosted-runners/)
- [신뢰 가능한 배포 관점의 GitHub Actions](https://daewooki.github.io/posts/2025-github-actions-cicd-2/)
- [재사용·보안·속도 3가지 축](https://daewooki.github.io/posts/2025-github-actions-cicd-3-2/)
- [OIDC/배포보호까지 포함한 구성](https://daewooki.github.io/posts/2025-github-actions-cicd-oidc-2/)

[^1]: <https://www.githubstatus.com/incidents/3q1yb5m7ltvb>
[^2]: <https://docs.github.com/en/actions/concepts/runners/self-hosted-runners>
[^3]: <https://docs.github.com/en/enterprise-cloud@latest/actions/reference/runners/self-hosted-runners>
[^4]: <https://docs.github.com/en/actions/concepts/metrics>
[^5]: <https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency>
[^6]: <https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/>
[^7]: <https://docs.github.com/en/actions/reference/limits>
[^8]: <https://www.githubstatus.com/api/>
[^9]: <https://developer.statuspage.io/>
[^10]: <https://docs.github.com/en/actions/concepts/runners/runner-scale-sets>
[^11]: <https://docs.github.com/en/actions/how-tos/manage-runners/use-actions-runner-controller/deploy-runner-scale-sets>
[^12]: <https://daewooki.github.io/posts/2025-github-actions-cicd-2/>
[^13]: <https://daewooki.github.io/posts/2025-github-actions-cicd-3-2/>
[^14]: <https://daewooki.github.io/posts/2025-github-actions-cicd-oidc-2/>
[^15]: <https://github.blog/changelog/2026-06-12-github-actions-minimum-version-enforcement-timeline-for-self-hosted-runners/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
