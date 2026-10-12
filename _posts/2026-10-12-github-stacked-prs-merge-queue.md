---
title: "GitHub stacked pull requests: 스택 단위 리뷰와 머지 큐"
description: "Stacked pull requests GA 이후, 작은 PR 여러 개를 스택으로 운영하는 규칙을 merge queue·rebase 관점에서 다시 정리합니다."
date: 2026-10-12 13:59:05 +0900
categories: ["News", "Tools"]
tags: ["github", "pull-requests", "merge-queue", "code-review", "rebase", "ai-agents"]
render_with_liquid: false
---

## 2026-10-06 GA로 바뀐 것: PR이 아니라 스택이 운영 단위가 됐다

GitHub가 stacked pull requests를 2026년 10월 6일에 generally available로 전환했습니다. 핵심은 UI 기능 추가가 아니라, **리뷰/머지/자동화의 기본 단위가 pull request 1개에서 stack 1개로 옮겨갔다**는 점입니다. GitHub Changelog가 이번 GA 릴리스에서 강조한 변화도 대부분 “스택을 한 덩어리로 안전하게 굴리기”에 수렴합니다. 예를 들면 merge queue에 스택이 “단일 merge group”으로 들어가고(표현 그대로라면), Rebase stack이 approvals를 최대한 유지하며, 재작성된 커밋도 signed 상태를 유지하고, bypass 권한도 스택에 적용되는 식입니다.[^1]

숫자도 같이 제시됐습니다. public preview 이후 stacked pull requests를 쓰는 repo가 peers 대비 merged code가 9% 증가, top 1% repo 중 2/3가 stacked PRs를 사용, time-to-merge가 5% 개선 같은 문구가 들어갔는데(정확한 측정 방법은 Changelog 문장만으로는 알기 어렵습니다), GitHub가 “이건 취향 기능이 아니라 throughput을 건드리는 운영 기능”으로 포지셔닝하고 있다는 신호로 봤습니다.[^1]

다만 팀 입장에서는 GA가 반가운 동시에 부담이기도 합니다. stacked PRs를 도입하면 기존에 애매하게 섞어 쓰던 규칙—예컨대 merge queue의 batch 정책, required checks의 촘촘함, rebase 허용 범위, “stale approvals dismiss” 같은 리뷰 규칙—을 스택 전제에서 다시 맞춰야 합니다. GitHub Docs도 스택의 merge requirements가 “스택 바닥 PR이 타깃으로 삼는 base branch”의 규칙으로 결정된다고 못박고 있습니다.[^2]

## 작은 PR 여러 개는 팀 생산성 기법이 아니라, 안전장치가 된다

작은 PR을 권장하는 얘기는 오래됐습니다. 그런데 2026년 시점에는 이유가 달라졌습니다. 팀이 빨라지기 때문만이 아니라, AI agent(또는 대량 자동 생성 코드)가 팀의 기본 생산 수단으로 들어오면서 “리뷰가 감당 가능한 단위로 강제 분해되는 구조” 자체가 안전장치가 됩니다.

GitHub Docs도 stacked PRs의 사용 맥락으로 agent/대량 생성 코드를 명시합니다. “한 번에 많은 코드를 생성하는 상황에서, 작업 단위(태스크 단위) = PR 단위”로 쪼개고, 그 의존 관계를 스택으로 표현하는 게 자연스럽다고 설명합니다.[^2]

내 경험 기준으로 agent가 만드는 위험은 대체로 다음 패턴으로 나타납니다.

- 변경량이 크고 넓게 퍼집니다(리팩터링+기능추가+테스트+문서가 한 번에 들어옴).
- 중간 레이어(예: internal API, migration, config)부터 먼저 합쳐져야 하는데, 리뷰는 눈에 띄는 최상단(UI나 endpoint)부터 시작해 흐트러집니다.
- CI는 “전체 변경”에 대해서만 초록이 뜨고, 어떤 레이어가 품질 기준을 어겼는지 추적이 어렵습니다.

스택은 여기서 두 가지를 강제합니다.

1) **의존성 방향**: 위 레이어가 아래 레이어에만 의존해야 합니다(위에서 아래로만 기반이 깔리는 구조). GitHub는 “한 레이어가 다른 레이어에 의존하면, 그 의존성은 같은 브랜치 또는 더 아래 브랜치에 있어야 한다”는 원칙을 문서로 명시합니다.[^2]

2) **diff의 국소화**: 각 PR은 “바로 아래 브랜치와의 차이(layer diff)”만 보여야 합니다. 리뷰어가 보는 범위가 물리적으로 줄고, “최상단 PR만 봐서는 이해가 안 되는 코어 변경”도 아래 PR에서 먼저 다루게 됩니다.[^2]

이 두 가지가 결합되면, agent가 만든 변경을 리뷰할 때도 레이어별로 안정장치를 걸 수 있습니다. 예컨대 아래에서부터 “schema/migration → core API → endpoint → UI → observability”처럼 쌓아두면, 각 레이어별 승인 기준을 만들기 쉬워집니다.

## 스택의 merge requirements: 바닥 PR의 base branch가 모든 것을 결정한다

stacked PRs를 “그냥 PR 링크 기능” 정도로 생각하면 도입이 망합니다. GitHub의 스택은 규칙 적용이 명확합니다.

- 스택의 각 PR이 충족해야 하는 merge requirements는 “바닥 PR이 타깃으로 하는 base branch(대개 main)”의 규칙으로 결정됩니다.[^2]
- CODEOWNERS 승인 같은 branch protection이 스택 중간 PR에도 동일하게 적용됩니다.[^2]
- default branch 대상으로 돌던 CI checks도 스택의 모든 PR에 대해 실행되도록 동작한다고 설명합니다(“바닥 PR만”이 아니라 “전체 PR”).[^2]

이 모델은 조직에 따라 희비가 갈립니다.

- 장점: 스택 중간 PR도 “진짜 기준(main 기준)”으로 품질 게이트를 통과해야 하므로, 레이어별로 품질이 무너지는 걸 막습니다.
- 단점: required checks가 무겁고 느린 조직에서는, PR 수가 늘어나는 만큼 CI 비용/대기 시간이 증가할 수 있습니다. 이건 stacked PRs가 해결해주는 문제가 아니라, merge queue와 CI 구조를 같이 손봐야 하는 문제로 넘어갑니다.

그리고 한 가지 더 중요한 조건이 있습니다. 스택이 merge되려면 “linear history”여야 합니다. GitHub Docs의 merge requirements에 “The stack has a linear history”가 들어가 있고, 선형이 깨지면 Rebase stack 버튼으로 스택을 다시 직선으로 만들어야 합니다.[^3]

즉, stacked PRs를 도입하면 팀은 사실상 “리베이스를 운영 절차로 받아들이는 팀”이 됩니다. “우리는 merge commit만 하고 rebase는 싫다”는 팀이라면, stacked PRs를 UI에서 켠다고 바로 운영될 가능성은 낮습니다.

## merge queue와 스택: ‘함께 들어가지만, 반드시 한 번에 내려오진 않는다’

### GitHub이 말하는 목표 상태

GitHub Changelog는 GA 개선점 중 하나로 “A stack now enters and lands through the merge queue as a single merge group”를 넣었습니다.[^1]

문장을 그대로 읽으면 “스택이 merge queue에 들어갈 때도, queue를 통과해 실제 main에 반영될 때도, 단일 merge group처럼 다룬다”는 뜻에 가깝습니다. 즉, 스택이 queue에서 분해되지 않고 한 덩어리로 테스트/머지된다는 기대를 만들기 쉽습니다.

### Docs가 말하는 실제 동작 조건

그런데 GitHub Docs는 merge queue와 스택을 조금 더 현실적으로 다룹니다.

- 스택을 merge queue로 머지할 때, “스택을 함께 유지하기 위해 merge group의 최대 크기를 최대 50%까지 초과하도록 허용”합니다.[^3]
- 그 50% 버퍼를 넘어가면 스택이 “다음 merge group으로 넘어가며 단일 유닛으로 처리”된다고 설명합니다.[^3]

즉 “항상 한 방에 끝난다”가 아니라, queue의 group size 제약을 넘으면 **연속된 여러 group으로 쪼개져 내려올 수 있다**는 얘기입니다. 게다가 GitHub Docs(gh stack CLI 명령 레퍼런스)에는 더 직접적인 문장이 있습니다.

- base branch가 merge queue를 쓰면 `gh stack merge`는 직접 merge하지 않고 queue에 추가합니다.
- 이때 queue가 merge method를 선택하므로 `--squash/--rebase/--merge-method` 같은 플래그는 무시된다고 경고합니다.
- 그리고 “선택한 PR들은 함께 queue에 추가되지만, queue가 처리하는 과정에서 separate groups로 landing될 수 있다”고 명시합니다.[^4]

정리하면 내 결론은 이렇습니다.

- 스택은 “의존성을 가진 PR 집합”이고, merge queue는 “main에 들어가기 전에 CI를 선행시키는 게이트”입니다.
- 둘을 붙이면 GitHub는 **스택을 최대한 같이 처리하려고 하되**, merge queue의 운영 파라미터(merge limits, group size, build concurrency 등)에 의해 스택이 여러 번에 나뉘어 내려올 수 있습니다.

이게 나쁘다는 얘기가 아닙니다. 오히려 “스택은 논리적 유닛, queue는 물리적 처리 유닛”이라고 보고 운영 파라미터를 설계하는 게 맞습니다.

### merge queue 자체의 내부 모델과 비용

merge queue는 temporary branch(merge_group 브랜치)를 만들고, base_branch의 최신 커밋 + queue 앞쪽 PR들의 변경 + 대상 PR 변경을 합쳐서 테스트한 뒤 통과하면 base_branch로 머지합니다. GitHub Docs는 이 과정을 `merge_group` 이벤트/temporary branch로 설명합니다.[^5]

이 구조는 stacked PRs에 유리합니다.

- 스택의 아래 레이어가 바뀌면 위 레이어들도 의미상 다시 검증돼야 하는데, merge queue는 “항상 최신 base + 앞선 변경과 합쳐서” 검증하는 모델이라 스택과 궁합이 좋습니다.
- 반대로, merge queue를 쓰지 않으면 stacked PRs는 결국 “PR별 green”과 “main에 들어갔을 때 green” 사이의 간극을 팀이 인력으로 메꾸게 됩니다.

다만 비용과 시간을 같은 자리에서 봐야 합니다. merge queue는 CI를 더 자주 돌릴 수밖에 없습니다. 스택이 늘어나는 조직은 runner 비용, cache 전략, workflow 최적화 같은 운영이 따라오지 않으면 병목이 더 커질 수 있습니다. 이 부분은 예전에 정리해 둔 GitHub Actions 글에서 다룬 내용과 그대로 연결됩니다.

- [GitHub Actions CI/CD 파이프라인: “자동화”를 넘어 “신뢰 가능한 배포”까지](https://daewooki.github.io/posts/2025-github-actions-cicd-2/)
- [GitHub Actions로 “안전하고 빠른” CI/CD 파이프라인 구축하는 법 (캐시 v2·OIDC·권한 최소화까지)](https://daewooki.github.io/posts/2025-github-actions-cicd-v2oidc-2/)

## rebase가 ‘개발자 습관’에서 ‘플랫폼 기능’이 됐다는 신호

stacked PRs를 굴릴 때 가장 피곤한 작업은 cascading rebase입니다. 아래 PR이 리뷰 피드백으로 수정되면 위 PR들은 base가 바뀌고, trunk가 앞으로 가면 전체가 다시 선형이 돼야 합니다.

GitHub는 이걸 “당연한 운영”으로 만들려고 하는 것 같습니다.

- 스택이 선형이 아니면 merge box에 Rebase stack이 뜨고, merge 전에 선형을 회복해야 합니다.[^3]
- Rebase stack이 approvals를 최대한 유지하도록 개선됐고, stale approvals dismiss가 켜져 있어도 unchanged diff면 approvals를 유지한다고 합니다.[^1]
- rebase로 재작성되는 커밋도 signed 상태를 유지하도록 “GitHub가 signed replacement commits를 만든다”는 내용이 GA 개선점에 포함됐습니다.[^1]

이게 중요한 이유는 agent 코드 리뷰와 직결되기 때문입니다.

- agent가 만든 스택은 흔히 “아래부터 쌓아 올린 설계”라기보다, 한 번에 생성한 결과를 사람이 적당히 레이어로 나눠 넣는 형태가 많습니다.
- 이 경우 아래 레이어 수정이 빈번하고, 그때마다 approvals가 무너지고 force push가 반복되면 팀은 스택을 버립니다.
- GitHub가 approvals 유지와 signed commits를 기능으로 박아 넣은 건, “스택 운영의 비용을 낮춰야 스택이 살아남는다”는 판단으로 읽힙니다.

다만 이 편의성은 정책 설계와 같이 가야 합니다. 특히 “dismiss stale approvals”를 켠 조직은 approvals 유지 규칙이 어떤 조건에서 적용/미적용되는지(예: diff 판단 기준, 파일 단위인지 패치 단위인지)를 팀 내에서 합의하지 않으면 분쟁이 생깁니다. 문서/Changelog의 문장만으로는 세부 기준을 완전히 재구성하기 어렵다는 점은 남습니다.[^1]

## gh-stack이 ‘공식 워크플로’가 됐을 때 생기는 운영 변화

stacked PRs의 GA가 의미 있는 이유는 UI 기능 때문만이 아닙니다. GitHub가 `gh stack`을 공식 경로로 밀면서, 로컬에서 스택을 다루는 방법이 사실상 표준화되기 시작했습니다. Changelog도 CLI(worktrees 포함) 개선을 같이 묶어 발표했습니다.[^1]

### 로컬 상태가 어디에 저장되는지부터 팀이 알아야 한다

`github/gh-stack` README에는 로컬 상태 저장 위치가 비교적 명확히 쓰여 있습니다.

- 사용자 단위 timestamp/리마인더 같은 것은 GitHub CLI state 디렉터리 아래 `gh-stack/state.yml`에 YAML로 저장된다고 합니다(기본 경로 예시로 `~/.local/state/gh`를 듭니다).[^6]
- 스택 메타데이터(브랜치 간 연결, 순서, PR 메타 등)는 Git의 common directory 아래 `<common-dir>/gh-stack` JSON 파일에 저장되고, 일반 clone에서는 `.git/gh-stack`이며 repo에 커밋되지 않습니다.[^6]

여기서 중요한 포인트는 “커밋되지 않는 로컬 상태”가 워크플로의 일부가 된다는 점입니다. 그래서 다음 상황에서 운영 리스크가 생깁니다.

- 다른 머신으로 옮길 때 스택 인식이 끊길 수 있습니다.
- worktree/여러 체크아웃에서 common directory를 공유하므로, 동일 repo를 여러 worktree로 운영할 때 기대와 다른 상태가 생길 수 있습니다(이건 장점이기도 합니다).[^6]
- CI에서 `gh stack`을 돌릴 경우 state.yml이 runner의 home/state 디렉터리에 남고, 캐시/아티팩트 정책에 따라 흔적이 남을 수 있습니다.

이건 기술적 문제라기보다 “운영 문서화의 문제”입니다. stacked PRs가 사람 습관이 아니라 툴체인으로 들어오면, 로컬 상태/복구 전략까지 정리돼 있어야 팀이 멈추지 않습니다.

### push가 원자적이지 않다는 점도 알아야 한다

`gh stack push`는 모든 브랜치를 한 번에 `git push`하면서 각 브랜치에 `--force-with-lease`를 걸어 업데이트합니다. 다만 README는 업데이트가 atomic이 아니고, 어떤 브랜치 lease가 실패하면 일부 브랜치만 업데이트될 수 있다고 말합니다.[^6]

스택은 브랜치 간 의존이 있기 때문에 “일부만 push 성공”은 잠깐이라도 이상한 상태를 만들 수 있습니다. 특히 agent가 자동으로 push/submit을 반복하는 환경에서는 더 위험합니다. 그래서 나는 스택 운영에서 아래 규칙을 선호합니다.

- `gh stack push`를 자동화에 넣더라도, 실패 시 즉시 중단하고 재시도는 사람이 판단합니다.
- 스택 상단 레이어일수록 force push 빈도를 낮추고(리뷰 확정에 가까울수록), 아래 레이어에서만 잦은 rebase/force push가 일어나도록 레이어링을 설계합니다.

## 스택/머지큐/리베이스 관점에서 ‘팀 규칙’을 다시 설계하는 법

여기부터는 기능 소개가 아니라 규칙 얘기입니다. stacked PRs를 도입하는 순간 “PR 규칙”이 “스택 규칙”으로 바뀌기 때문에, 기존 규칙이 의도치 않게 공격적으로 변하거나(너무 많은 CI), 반대로 허술해질 수 있습니다(스택 어딘가가 빠져도 merge되는 착시).

### 1) merge method는 개인 취향이 아니라 queue 정책이 된다

merge queue를 쓰면 merge method는 queue 설정이 결정합니다. GitHub Docs의 `gh stack merge` 레퍼런스도 “base branch가 merge queue를 쓰면 queue가 merge method를 선택하고, `--squash/--rebase` 같은 플래그가 무시된다”고 못박습니다.[^4]

즉 팀에서 “우리는 squash만 허용” 같은 결정을 해두었다면, 그건 PR 버튼의 선택지가 아니라 merge queue 설정의 선택지가 됩니다.

이때 stacked PRs와의 궁합은 다음처럼 봅니다.

- **squash**: 레이어별 커밋이 하나로 눌리면 스택의 레이어 의미가 약해질 수 있습니다. 다만 “PR 단위로 남기는 change log”가 필요하면 여전히 유효합니다.
- **merge commit**: 스택 레이어가 PR 단위로 기록에 남는 장점이 큽니다. Changelog도 merge commit 방식에서 “PR마다 하나의 merge commit을 만들도록” 동작이 바뀌었다고 명시합니다.[^1]
- **rebase merge**: 히스토리는 깔끔해지지만, 스택 운영 자체가 rebase에 의존하기 때문에 “누가 언제 무엇을 rebase했는지”가 더 불투명해질 수 있습니다.

개인적으로는 스택을 강하게 쓰는 조직일수록 merge commit 쪽이 사건 추적이 쉬웠습니다. “어느 PR에서 이 behavior가 들어왔는지”가 PR-merge commit로 명확해지는 순간이 많았습니다.

### 2) required checks는 ‘레이어당’으로 설계해야 한다

Docs는 “default branch 대상으로 트리거되던 CI가 스택의 모든 PR에 대해 동작”한다고 설명합니다.[^2]

이게 그대로면, 스택이 8개 레이어면 사실상 8번의 동일한 비싼 CI가 돌 수 있습니다. 그래서 required checks를 설계할 때는 레이어별로 역할을 나누는 편이 낫습니다.

- 하단 레이어: lint, unit, migration 검증, 빠른 contract test 위주
- 중단 레이어: 통합 테스트(다만 런타임을 통제)
- 상단 레이어: e2e나 UI 스냅샷 등 가장 비싼 테스트는 가능한 한 조건부로

이때 “조건부 required”를 GitHub가 기본 제공하진 않아서, 결국 workflow 자체를 분리하고 `paths` 필터링, matrix 축소, 캐시 강화 같은 CI 설계가 필요합니다. 이건 stacked PRs의 문제가 아니라, 스택이 팀의 기본 단위가 될 때 CI가 따라오지 않으면 비용 폭발이 난다는 얘기입니다.

### 3) rebase 정책: ‘언제든 가능’이 아니라 ‘언제 강제’인지 정한다

스택이 merge되려면 linear history여야 하고, linear이 아니면 Rebase stack이 요구됩니다.[^3]

그래서 팀 규칙은 대개 두 방향 중 하나로 가야 합니다.

- trunk가 자주 움직이는 조직: “queue 들어가기 직전에는 반드시 rebase”를 강제하고, rebase는 플랫폼 버튼 또는 `gh stack rebase`로 일원화합니다.
- trunk가 느리게 움직이는 조직: 스택을 오래 들고 가는 대신, rebase 빈도를 낮추고 conflict는 늦게 한 번 크게 해결합니다.

agent 코드가 많은 조직은 첫 번째가 현실적입니다. agent는 작은 레이어를 빨리 만들고 빨리 보내는 쪽에 맞고, 오래 들고 가는 스택은 보통 사람이 더 잘 다룹니다.

### 4) merge queue의 merge limits: 스택이 커질수록 “최대치”가 중요해진다

merge queue에는 “minimum/maximum PRs to merge” 같은 merge limits가 있고, docs는 이게 base branch 머지 시점의 그룹 크기를 조절한다고 설명합니다.[^5]

stacked PRs를 붙이면 여기서 트레이드오프가 생깁니다.

- maximum이 작으면: 스택이 길 때 스택이 여러 번에 나뉘어 내려오고, 레이어 간 간격이 벌어져 관찰이 어렵습니다.
- maximum이 크면: 한 번에 너무 많은 변경이 main에 들어가 deploy risk가 커집니다.

내 결론은 “스택은 레이어를 작게 만들고, queue의 maximum은 그보다 조금 크게 잡되, 스택이 그 maximum을 넘지 않도록 팀 합의를 만든다”입니다. 스택 레이어가 커지는 순간(=리뷰가 다시 커지는 순간)은 대부분 설계가 흐려진 순간이라, 레이어 수가 늘어나는 것보다 레이어가 비대해지는 게 더 위험했습니다.

## 실제로 굴려보면 생기는 패턴: agent 코드 리뷰를 스택으로 ‘격리’한다

여기서는 장난감 예제 대신, 내가 실무에서 흔히 보는 “기능 추가 + migration + 관측성 + 테스트 자동 생성” 시나리오를 stacked PRs로 어떻게 분해하는지 정리합니다. 코드 자체보다, 레이어 분해 기준이 목적입니다.

가정:

- repo는 `main`이 기본 브랜치
- merge queue가 켜져 있고, required checks가 걸려 있음
- 로컬은 macOS/Linux 기준(경로 예시는 gh-stack README 표현을 따름)

### 도구 버전/의존성

- GitHub CLI (`gh`) 설치
- `gh-stack` extension 설치: `gh extension install github/gh-stack`[^6]

```bash
gh --version
# 예상 출력 예시
# gh version 2.xx.x (2026-xx-xx)

gh extension install github/gh-stack
# 이미 설치돼 있으면 install 대신 upgrade가 필요할 수 있습니다.
```

### 레이어 분해 기준(내가 자주 쓰는 방식)

- layer 1 (bottom): schema/migration + backwards compatible change
- layer 2: server core(비즈니스 로직/도메인)
- layer 3: API surface(endpoint/controller) + contract test
- layer 4 (top): agent가 생성한 테스트/리팩터링/문서(격리)

핵심은 “agent 생성물을 top 레이어로 격리”하는 겁니다. agent가 만든 테스트가 실패하면 top만 고치면 되고, 아래 레이어의 승인/검증 흐름을 깨지 않게 됩니다.

### 스택 생성과 브랜치 추가

```bash
# 1) 스택 시작
# 첫 브랜치를 만들고 체크아웃합니다.
gh stack init

# 2) bottom 레이어 작업 (예: migration)
# ... 파일 변경 ...
git add -A
git commit -m "db: add users.status and index"

# 3) 위에 레이어 추가
# 다음 관심사(서버 로직)를 새 브랜치로 쌓습니다.
gh stack add user-status-core
# ... 변경 ...
git add -A
git commit -m "core: compute user status"

# 4) API 레이어
# endpoint + contract test
gh stack add user-status-api
# ... 변경 ...
git add -A
git commit -m "api: expose user status endpoint"

# 5) agent 생성물 격리 레이어
# 예: agent가 생성한 테스트/문서/리팩터링을 여기로 몰아넣음
gh stack add agent-tests
# ... agent가 생성한 변경을 여기서만 커밋 ...
git add -A
git commit -m "test: add agent-generated regression tests"
```

이 흐름은 gh-stack README가 설명하는 “각 PR의 base를 바로 아래 브랜치로 설정해 layer diff만 보이게 한다”는 모델과 일치합니다.[^6]

### PR 생성/스택 제출

```bash
# 모든 브랜치를 push하고, PR을 만들고, GitHub에 stack object로 연결합니다.
# --open을 주면 새 PR을 draft가 아니라 ready로 만듭니다.
gh stack submit --open

# 스택 확인
# 로컬/리모트 스택 상태를 보여줍니다.
gh stack view
```

`submit`이 “브랜치별로 PR 생성 → PR들을 stack으로 링크”까지 수행한다는 점은 GitHub Docs 레퍼런스에 명시돼 있습니다.[^4]

### 상태 저장 위치 확인(운영 시 꼭 한 번은 확인해야 한다)

```bash
# 스택 메타데이터는 .git/gh-stack (커밋되지 않는 JSON)
ls -al .git/gh-stack

# 사용자 상태(state.yml)는 gh의 state directory 아래
# README 예시로는 ~/.local/state/gh/gh-stack/state.yml
ls -al ~/.local/state/gh/gh-stack/state.yml
```

이 저장 모델을 알고 있으면, “어느 순간부터 스택이 깨져 보인다” 같은 문제에서 원인 추적이 빨라집니다.[^6]

### merge queue가 켜져 있을 때 머지 동작

- GitHub Docs는 stacked PRs가 merge queue를 지원하고, 스택 PR들이 올바른 순서로 queue에 들어간다고 말합니다.[^3]
- `gh stack merge`도 base branch가 merge queue면 직접 merge하지 않고 queue에 넣는다고 명시합니다.[^4]

```bash
# queue로 들어가면 merge method는 queue가 결정합니다.
# --squash 같은 플래그는 무시될 수 있습니다.
gh stack merge
```

여기서 팀이 오해하기 쉬운 지점이 하나 있습니다.

- “스택을 머지했다”는 행위는 **즉시 main에 반영**이 아니라 **queue에 올린 것**일 수 있습니다.
- queue 설정(merge limits, build concurrency, group size)에 따라 스택이 한 번에 landing되지 않고, 연속된 여러 group으로 내려올 수도 있습니다.[^3]

## 반론과 회의론: stacked PRs가 항상 이득인 건 아니다

stacked PRs의 가장 큰 반론은 “복잡도가 증가한다”입니다. 이건 맞는 말입니다.

- PR이 1개면 끝날 일을 PR 6개로 쪼개면, 리뷰어 입장에서도 클릭 수가 늘고, 승인/코멘트가 분산됩니다.
- 스택 아래에서 conflict가 나면 cascading rebase로 연쇄 충돌이 나고, 그걸 해결하는 사람은 숙련이 필요합니다.
- merge queue까지 붙으면 “내가 merge 버튼을 눌렀는데 왜 안 들어가나”가 상시 질문이 됩니다.

GitHub가 GA에서 “stack context를 PR header에 항상 노출”하고 timeline에 stack membership lifecycle을 넣은 것도, 이런 복잡도를 UI로 줄이려는 시도입니다.[^1]

또 하나의 회의론은 “스택이 스택답지 않게 운영된다”는 겁니다. 예를 들면 아래 같은 운영이 흔합니다.

- 스택 레이어가 얇아야 하는데, 사람이 귀찮아서 레이어 하나가 거대 PR이 됩니다.
- agent가 만든 변경을 레이어로 잘 격리하지 않고 중간 레이어에 섞습니다.
- 그 결과 아래 레이어가 자주 바뀌고 approvals가 계속 깨지며, 리뷰어가 피로해집니다.

결국 stacked PRs는 툴이 아니라 규율입니다. 팀이 “레이어링 기준”을 합의하지 않으면, stacked PRs는 PR UI를 복잡하게 만드는 기능으로 끝납니다.

## 앞으로 지켜볼 것: GA 문장과 Docs 문장 사이의 시차

GA 발표에는 “Auto-merge for stacks rolling out over the next few weeks”가 포함돼 있습니다.[^1]

그런데 GitHub Docs의 “Merging stacked pull requests” 문서에는 “Auto-merge is not supported for stacked pull requests”라고 적혀 있습니다(2026-10-12 기준으로 이 문장을 확인했습니다).[^3]

이건 흔한 현상입니다.

- Changelog는 롤아웃 중인 기능을 먼저 말하고,
- Docs는 완전 롤아웃/일관된 동작이 확보된 뒤에 문장을 바꾸는 경우가 많습니다.

운영 관점에서는 “Auto-merge를 스택에 기대하고 프로세스를 설계”하면 위험합니다. 실제로 팀 규칙을 바꿀 때는, 본인 조직의 repo에서 Auto-merge UI/behavior가 보이는지부터 확인하고 전환해야 합니다.

또 하나의 포인트는 API입니다.

- 스택 merge는 legacy synchronous merge endpoints로 처리할 수 없고, background에서 돌아가는 방식이며, branch protection/rules는 “merge가 실제로 실행될 때” 평가된다는 문장이 들어가 있습니다.
- 그리고 stack merge request는 atomic(전체가 merge/queue 되거나, 아니면 아무것도 안 됨)이라고 명시합니다.[^7]

automation을 붙이는 조직(예: 스택이 만들어지면 봇이 특정 label 기준으로 queue에 넣는다)이라면 여기서 “polling/비동기” 모델을 반드시 흡수해야 합니다.

## 지금 할 수 있는 일: 스택을 기준으로 규칙을 재정의한다

stacked PRs GA는 기능 켜고 끄는 문제가 아니라, 다음 3가지를 팀이 다시 합의하는 타이밍이라고 봅니다.

1) **스택 레이어링 규칙**

- 아래로 갈수록 “불변에 가까운 기반”(schema/core)이고, 위로 갈수록 “변동성이 큰 변경”(테스트 생성물, 문서, 리팩터링)이 오도록 설계합니다.
- agent 생성 코드는 가급적 최상단 레이어로 격리해, 실패/되돌림이 스택 아래 레이어의 승인 흐름을 방해하지 않게 합니다.

2) **merge queue 파라미터를 스택에 맞춘다**

- merge method는 queue가 결정한다는 사실을 전제로, 히스토리/감사/rollback 관점에서 method를 확정합니다.[^4]
- merge limits(최대 그룹 크기)를 “우리가 허용하는 최대 스택 길이”와 같이 봅니다.[^5]

3) **rebase를 ‘허용’이 아니라 ‘운영’으로 만든다**

- 스택이 선형이 아니면 merge가 막히는 구조이므로, Rebase stack을 언제 누가 수행하는지 역할을 정합니다.[^3]
- approvals 유지/서명 유지 같은 GA 개선점은 팀의 rebase 부담을 줄여주지만, 그만큼 rebase가 더 자주 일어나는 환경이 됩니다.[^1]

이 세 가지가 맞물리면, “큰 변경을 작은 PR 여러 개로 쪼개는 습관”이 팀 생산성 기법을 넘어, agent/자동 생성 코드 시대의 리뷰 안전장치로 작동하기 시작합니다.

## 참고 자료

- [Stacked pull requests generally available](https://github.blog/changelog/2026-10-06-stacked-pull-requests-generally-available/)
- [Stacked pull requests](https://docs.github.com/en/pull-requests/how-tos/stacked-pull-requests)
- [About stacked pull requests](https://docs.github.com/en/pull-requests/get-started/about-stacked-prs)
- [Merging stacked pull requests](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-stacked-pull-requests)
- [Troubleshooting stacked pull requests](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-stacked-pull-requests)
- [Stacked pull requests APIs and webhooks](https://docs.github.com/en/pull-requests/reference/stacked-pull-requests-apis-and-webhooks)
- [Managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
- [GitHub gh-stack extension](https://github.com/github/gh-stack)
- [GitHub docs: stacked PRs CLI commands (source)](https://github.com/github/docs/blob/main/content/pull-requests/reference/stacked-prs-cli-commands.md)

[^1]: <https://github.blog/changelog/2026-10-06-stacked-pull-requests-generally-available/>
[^2]: <https://docs.github.com/en/pull-requests/get-started/about-stacked-prs>
[^3]: <https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-stacked-pull-requests>
[^4]: <https://github.com/github/docs/blob/main/content/pull-requests/reference/stacked-prs-cli-commands.md>
[^5]: <https://github.com/github/docs/blob/main/content/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue.md?plain=1>
[^6]: <https://github.com/github/gh-stack>
[^7]: <https://docs.github.com/en/pull-requests/reference/stacked-pull-requests-apis-and-webhooks>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
