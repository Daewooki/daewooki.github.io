---
title: "Octoverse 2026이 굳힌 에이전트 PR 운영 계약"
description: "Octoverse 2026의 ‘에이전트 PR 초안’ 통계를 리뷰·라이선스·보안 스캔·감사 규칙으로 변환해 운영 정책으로 고정합니다."
date: 2026-10-29 10:43:08 +0900
categories: ["News", "Tools"]
tags: ["github", "octoverse", "copilot", "agentic-workflows", "code-review", "policy-as-code"]
render_with_liquid: false
---

## 2026-10-28 Octoverse 2026: PR 초안의 주체가 통계로 박혔다

GitHub가 2026-10-28에 공개한 Octoverse 2026은 한 줄로 요약하면 개발자의 기본 동작이 바뀌었다는 보고서였습니다. 숫자가 확정되면 팀은 논쟁을 끝내고 계약을 씁니다.

Octoverse 본문에서 가장 강한 문장은 이것입니다. 2026년 9월 기준, GitHub의 pull request 중 **40%** 이상이 에이전트의 first draft로 시작됐고, 2026년 3월은 17%였습니다. 2026년 9월 한 달에만 에이전트가 시작한 PR이 1억 1천만 건이라고도 적었습니다. (Octoverse의 기간 정의는 2025-10-01부터 2026-09-30까지입니다.)

- [Octoverse 2026 원문: 에이전트와 함께 쌓인 활동량](https://github.blog/news-insights/octoverse/octoverse-commits-pushes-reach-new-highs-in-2026-as-developers-build-with-agents/)

이 통계를 그대로 팀 현실에 대입하면, PR의 첫 커밋이 사람이냐 에이전트냐는 더 이상 예외 처리 항목이 아닙니다. PR 리뷰가 예외가 아니라 기본 작업이 된다는 뜻이고, 리뷰 기준이 글로 남지 않은 팀은 속도와 품질 중 하나를 잃습니다.

Octoverse는 agent-started pull request를 “감지 가능한 coding agent가 만든 first draft에서 출발한 PR”로 정의합니다. 감지되지 않는 에이전트 사용이 있다는 점까지 같이 명시하므로(telemetry의 floor), 실제 비중은 더 높을 수 있습니다.

동시에 PR의 성격도 조금 변했습니다.

- 에이전트가 관여한 PR은 여러 파일을 바꾸는 비율이 더 높다고 합니다(에이전트 관여 87%, 비관여 79%).
- 2주 내 merge 비율은 2026년 9월 기준 에이전트 관여 PR이 90%, 비교군이 86%로 적혀 있습니다.

이 조합은 위험합니다. 리뷰 부담은 커지는데 merge는 빨라집니다. 팀이 스스로 안전장치를 더 촘촘히 설치하지 않으면, 빠른 merge가 빠른 사고로 변환될 확률이 올라갑니다.

## 모델 다변화: 표준 모델을 정하던 방식이 무너졌다

에이전트 PR 비중만으로도 프로세스는 흔들리는데, Octoverse 2026은 모델 쪽도 팀 운영을 어렵게 만드는 숫자를 같이 던졌습니다.

- 2026년 9월에 Copilot에서 사용자가 모델을 직접 골라 쓰는 케이스 중 61%가 세션 전반에서 2개 이상 모델을 썼습니다.
- 유료 Copilot 플랜 사용자가 쓴 distinct model 수가 2026년 5월 29개에서 2026년 9월 47개로 늘었다고 합니다.
- 2026년 9월에는 단일 모델이 전체 요청의 25%를 넘지 못했다고 적혀 있습니다.

- [Octoverse 2026의 model choice 섹션](https://github.blog/news-insights/octoverse/octoverse-commits-pushes-reach-new-highs-in-2026-as-developers-build-with-agents/)

이건 단순히 선택지가 늘었다는 얘기가 아닙니다.

1) “팀에서 표준 모델을 정해두고, 그 모델의 성향에 맞춘 프롬프트/가이드만 다듬으면 된다”는 접근이 더는 현실적인 기본값이 아닙니다.

2) 동일한 개발자가 같은 작업을 하더라도, 초안을 만든 모델과 수정/리팩터링에 관여한 모델이 달라질 수 있습니다. 결과물의 스타일, 실수 유형, 보안 취약점의 패턴이 흔들립니다.

3) 책임 소재도 흐려집니다. 사람이 쓴 코드라도 리뷰 규칙이 약하면 사고가 나는데, 모델이 47개로 분산되면 코드의 출처와 의도 추적이 더 어려워집니다.

여기서 팀이 붙잡아야 하는 축은 모델이 아니라 계약입니다. 모델은 도구이고 계약은 시스템 경계입니다.

## 통계를 **팀 개발 프로세스 계약**으로 바꾸는 프레임

에이전트가 코드를 만들든 사람이 만들든, 운영 관점에서 PR은 항상 동일한 4가지 질문으로 귀결됩니다.

1) 이 변경은 무엇을 바꾸나
2) 그게 맞다는 근거는 무엇인가(테스트/재현/관측)
3) 이 변경의 출처/권리/라이선스는 무엇인가
4) 문제가 생기면 무엇을 기준으로 되돌릴 것인가(rollback)

Octoverse 2026의 숫자는 (1)과 (2)를 PR 코멘트 몇 줄로 해결하던 시대가 끝났다는 신호입니다. 이제는 (3)과 (4)까지 같이 강제해야 합니다. 나는 이걸 **검증·감사·롤백** 3단 계약으로 묶는 편입니다.

- 검증: merge 전에 실패해야 하는 조건을 자동화한다.
- 감사: 나중에 책임 소재를 추적할 수 있게 근거를 남긴다.
- 롤백: 문제가 생기면 손이 덜 가는 형태로 되돌릴 수 있게 만든다.

이 프레임으로 보면 “에이전트 코드를 허용/금지”는 너무 이른 결론입니다. 팀이 실제로 필요한 건, 에이전트가 만든 결과를 운영 가능한 변경으로 바꾸는 절차입니다.

아래 내용은 GitHub 생태계에 있는 기능을 그대로 계약 조항으로 번역한 것입니다.

## 리뷰 규칙: 에이전트 여부가 아니라 변경 위험도를 기준으로 차단한다

Octoverse가 말하는 핵심은 PR을 여는 비용이 내려갔다는 겁니다. 비용이 내려가면 PR 수는 늘고, 리뷰는 병목이 됩니다. 그래서 리뷰 규칙은 “누가 썼나”가 아니라 “무엇이 바뀌나”로 작성해야 오래 갑니다.

GitHub에서 리뷰 규칙을 팀 계약으로 고정하는 방식은 크게 세 가지를 같이 씁니다.

- CODEOWNERS로 책임 구역을 만든다.
- branch protection / rulesets로 merge 조건을 강제한다.
- PR template로 사람이 남겨야 하는 근거를 표준화한다.

### CODEOWNERS로 책임 소재를 코드로 고정

CODEOWNERS는 소유권을 법적으로 선언하는 문서가 아니라, 리뷰 라우팅과 승인 강제를 위한 메커니즘입니다. GitHub 문서에도 “required reviews를 켠 경우, code owner 승인 요구를 걸 수 있다”가 명시돼 있습니다.

- [GitHub Docs: CODEOWNERS 개념과 동작](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)

예시는 아래 정도면 시작점으로 충분합니다.

```text
# .github/CODEOWNERS

# 전역: 최소 1개 팀이 항상 책임을 지도록 고정
*       @my-org/core-reviewers

# 보안/인프라 민감 파일
.github/workflows/   @my-org/platform
infra/               @my-org/platform
terraform/           @my-org/platform
k8s/                 @my-org/platform

# 런타임 핵심 코드
src/auth/            @my-org/security
src/payments/        @my-org/payments

# 의존성/빌드 파일
package.json         @my-org/core-reviewers
pnpm-lock.yaml       @my-org/core-reviewers
Dockerfile           @my-org/platform
```

에이전트가 PR을 열었을 때 팀이 힘들어지는 이유는, 에이전트가 바꾸는 범위가 넓어지기 쉽기 때문입니다(Octoverse에서 multiple files 비중이 더 높다고 적은 부분). 그래서 구역별 책임이 먼저 있어야 합니다.

### rulesets로 merge 조건을 법적 계약처럼 강제

GitHub rulesets 문서는 규칙 목록을 꽤 직접적으로 제공합니다. 중요한 지점은 “status check를 요구할 수 있다”, “code owner review를 요구할 수 있다”, “code scanning 결과를 요구할 수 있다”, “license compliance 결과를 요구할 수 있다” 같은 항목들이 한 화면에서 결합된다는 점입니다.

- [GitHub Docs: rulesets에서 쓸 수 있는 규칙들](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)

내 경험상 rulesets의 진짜 가치는 규칙 자체보다 예외를 줄이는 데 있습니다. 사람이 늘어나고 에이전트 PR이 섞이면, merge 버튼을 누르는 사람이 규칙을 기억할 가능성은 빠르게 0으로 수렴합니다. 시스템이 기억해야 합니다.

여기서 **ruleset**을 팀 계약으로 번역하면 대략 이런 문장들이 됩니다.

- PR은 최소 N명의 승인 없이는 merge할 수 없다.
- owned path가 포함되면 code owner 승인이 필수다.
- CI / security scan / dependency review가 성공하지 않으면 merge할 수 없다.
- (Enterprise라면) license compliance 정책 위반이 있으면 merge할 수 없다.

이 조항들은 에이전트가 만든 PR만을 겨냥하지 않습니다. 사람이 만든 위험한 PR도 같이 막아줍니다. 그게 중요합니다.

### PR template로 에이전트 PR의 필수 증빙을 강제

PR template은 조직 문화 문서가 아니라 UI에 강제로 박히는 입력 폼입니다. GitHub 문서에도 `.github/pull_request_template.md` 같은 경로가 정확히 나옵니다.

- [GitHub Docs: PR template 만드는 방법과 위치](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository)

에이전트 PR 시대의 PR template은 체크리스트가 아니라 “감사 가능한 증빙”을 수집하는 포맷이어야 합니다.

```md
<!-- .github/pull_request_template.md -->

## 변경 요약
- 

## 변경 동기 / 배경
- 

## 검증 방법
- [ ] 로컬에서 재현/실행함 (명령어/환경을 아래에 기록)
- [ ] 테스트 추가 또는 기존 테스트로 커버됨
- [ ] 관측 지표/로그로 영향 확인 가능

### 실행 명령 / 결과
```bash
# 예: Node
node -v
npm ci
npm test
```

예상 출력(또는 핵심 라인):
```text
PASS  ...
Test Suites: 42 passed, 42 total
```

## 위험도 분류
- [ ] config-only
- [ ] dependency-change
- [ ] security-sensitive
- [ ] data-migration
- [ ] rollout-needed

## 에이전트/모델 사용 여부(감사 목적)
- [ ] 에이전트가 first draft를 생성함
- [ ] Copilot / Cursor / Codex / Claude Code / 기타: 
- 모델(알고 있는 범위): 
- 자동 모델 선택 사용 여부: 

## 라이선스/출처
- [ ] Copilot public-code matching을 Block로 사용함
- [ ] public-code match reference가 있었고, 링크/라이선스를 확인함
- 참고 링크:
  - 

## 롤백 계획
- 롤백 커밋/토글/플래그:
- 롤백 시 데이터 정합성 이슈:
```

이 템플릿에서 핵심은 “에이전트를 썼다/안 썼다”가 아니라, (a) 검증, (b) 출처/권리, (c) 롤백이 빈칸으로 merge되는 걸 막는 것입니다.

## 저작권/라이선스: public-code matching을 팀 단위로 다룬다

에이전트 PR이 늘면 저작권/라이선스 리스크가 올라간다는 말은 흔하지만, 운영으로 번역되면 결국 선택지는 두 가지뿐입니다.

- 차단(Block): 유사 코드를 아예 안 보여준다.
- 허용(Allow): 유사 코드가 나오면 출처와 라이선스를 확인하고 기록한다.

GitHub는 Copilot 정책에서 “block suggestions matching public code”를 켜면 주변 코드 약 150 characters와 함께 public code를 대조하고, 매칭이면 제안을 숨긴다고 문서에 씁니다.

- [GitHub Docs: Copilot 정책에서 public code match Allow/Block](https://docs.github.com/en/copilot/how-tos/manage-your-account/manage-policies)

그리고 Allow 모드에서는 IDE에서 매칭된 suggestion을 accept했을 때, 매칭 file URL과 감지된 license를 기록한다고 명시합니다. 또 match는 1% 미만에서 발생한다고도 적어두었습니다.

- [GitHub Docs: IDE에서의 code reference 기록(license/URL)](https://docs.github.com/en/copilot/concepts/copilot-surfaces/copilot-in-ides)

여기서 팀 계약은 기술이 아니라 회계 처리에 가깝습니다.

### 계약 조항 1: Block/Allow는 개인 취향이 아니라 저장소 정책이다

개인 설정으로 두면 팀이 깨집니다.

- A 개발자는 Block이라 출처 리스크를 낮추고,
- B 개발자는 Allow라서 reference를 남기지만,
- C 개발자는 제품/서피스에 따라 Block이 지원되지 않아 reference 로그가 남지 않을 수 있습니다.

그러면 PR을 리뷰하는 사람 입장에서는 같은 팀의 PR이 서로 다른 기준으로 들어옵니다. 에이전트 PR 비중이 40%를 넘는 순간부터 이 불일치는 운영 리스크가 됩니다.

현실적인 선택은 보통 둘 중 하나입니다.

- 기본은 Block
- 예외적으로 Allow가 필요하면 PR template에 “reference 확인/기록”을 강제

나는 기본 Block을 선호합니다. 이유는 단순합니다. 팀은 법무팀이 아니고, PR마다 라이선스 감사를 수행할 체력이 없습니다. Allow로 갈 경우엔, “reference가 없는 PR은 라이선스 감사가 불가능하다”는 사실을 먼저 받아들여야 합니다.

### 계약 조항 2: Allow를 허용할 때는 reference를 PR 본문에 복사해 남긴다

IDE에 남는 로그만 믿으면 안 됩니다. PR이 merge된 뒤, 누가 어떤 근거로 들어갔는지 남기려면 PR 본문에 남아야 합니다.

- 매칭된 repository URL
- 해당 코드의 license(감지된 범위)
- 그 코드를 그대로 쓰지 않았다는 근거(수정 범위, 대체 구현 근거)

이건 분쟁을 대비하려는 목적도 있지만, 더 현실적으로는 “몇 달 뒤에 누가 지웠는지”가 아니라 “왜 들어갔는지”를 남기는 작업입니다.

### 계약 조항 3: dependency license는 별도의 자동 게이트로 막는다

Copilot의 public-code matching은 “코드 조각의 유사성” 문제이고, dependency license는 “공급망 계약” 문제입니다. 같은 폴더에 넣어 관리하면 반드시 누락이 납니다.

GitHub는 Enterprise + GitHub Code Security 조건에서 open source license compliance를 제공하고, rulesets로 enforcement가 가능하다고 문서에 명시합니다.

- [GitHub Docs: open source license compliance 개념](https://docs.github.com/en/code-security/concepts/supply-chain-security/open-source-license-compliance)

조직이 이 기능을 쓸 수 있는 상태라면, 에이전트 PR 시대에는 도입 논리가 더 강해집니다. 에이전트가 새로운 라이브러리를 가져오는 빈도가 올라가고, 리뷰어가 “이게 MIT인지 GPL인지”를 매번 확인할 수 없기 때문입니다.

## 보안 스캔: status check를 통과 의식이 아니라 차단 장치로 만든다

Octoverse 2026은 보안 관련 수치도 같이 던집니다. push protection이 2026년 한 해 동안 58억 번 스캔되었고, 2025년 대비 거의 4배라고 적습니다.

- [Octoverse 2026의 push protection 언급](https://github.blog/news-insights/octoverse/octoverse-commits-pushes-reach-new-highs-in-2026-as-developers-build-with-agents/)

push protection은 GitHub 문서에서 secret scanning의 한 기능이며, push 시점에서 secret을 막는다고 설명합니다.

- [GitHub Docs: push protection 개념과 동작](https://docs.github.com/en/code-security/concepts/secret-security/push-protection)

에이전트 PR이 늘면 보안 스캔은 더 중요해집니다. 이유는 간단합니다.

- 에이전트는 사람이 생각하지 않은 경로로 파일을 생성합니다.
- 설정 파일, 예제 코드, 디버그 출력, 임시 키를 PR에 포함시키는 실수가 늘어납니다.
- 특히 멀티 파일 변경 비중이 높은 PR은, 리뷰어가 모든 diff를 실제로 읽지 못할 때가 많습니다.

그래서 팀 계약은 “보안 도구를 쓴다”가 아니라 “보안 도구가 실패하면 merge가 불가능하다”여야 합니다.

### dependency review: PR 단계에서 공급망 변화를 실패로 만든다

GitHub의 dependency review는 PR에서 dependency 변화와 보안 영향을 보여주는 기능이고, GitHub는 이를 Actions로도 강제할 수 있게 `actions/dependency-review-action`을 제공합니다.

- [GitHub Action: dependency-review-action](https://github.com/actions/dependency-review-action)
- [GitHub Docs: dependency review 개념](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review)

실제로 동작하는 최소 workflow는 아래 수준입니다.

```yaml
# .github/workflows/dependency-review.yml
name: Dependency Review
on:
  pull_request:

permissions:
  contents: read

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Dependency Review
        uses: actions/dependency-review-action@v5
        with:
          fail-on-severity: moderate
          # 라이선스/패키지 정책은 팀 상황에 맞게
          deny-licenses: GPL-3.0, AGPL-3.0
```

이 workflow가 성공/실패를 내면, rulesets에서 해당 check를 required status check로 묶어 merge를 차단할 수 있습니다.

### secret scanning을 PR에서도 실패로 다루기

push protection은 push 시점 방어고, PR은 이미 올라온 변경을 리뷰하는 자리입니다. PR 본문/코멘트/리뷰 코멘트에 secret이 섞이는 경우도 현실에서 종종 나옵니다.

GitHub는 `advanced-security/secret-scanning-review-action`을 제공하고, PR에 secret scanning alert가 도입되면 status check를 실패시킬 수 있다고 설명합니다.

- [GitHub Action: secret-scanning-review-action](https://github.com/advanced-security/secret-scanning-review-action)

```yaml
# .github/workflows/secret-scanning-review.yml
name: Secret Scanning Review
on:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  secret-scan-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Secret scanning review
        uses: advanced-security/secret-scanning-review-action@v1
        with:
          token: ${{ secrets.SECRET_SCAN_REVIEW_GITHUB_TOKEN }}
          fail-on-alert: true
```

여기서 함정은 권한과 플랜입니다. private/internal repo에서 돌릴 때 GitHub Advanced Security 같은 조건이 걸릴 수 있습니다(이 액션 README에도 private/internal에서 GHAS가 필요하다고 적혀 있습니다). 그래서 이 조항은 “기능을 쓴다”가 아니라 “쓸 수 있는 플랜인지 확인하고, 못 쓰면 대체를 문서화한다”까지 포함해야 계약이 됩니다.

### CodeQL / code scanning: 사람이 리뷰할 수 없는 부분을 기계로 채운다

GitHub의 code scanning advanced setup은 기본적으로 PR과 push 시점에 스캔이 돌도록 CodeQL workflow를 구성한다고 문서에 명시합니다.

- [GitHub Docs: code scanning advanced setup 구성](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configuring-advanced-setup-for-code-scanning)

최소 수준의 CodeQL workflow 예시는 아래처럼 시작합니다.

```yaml
# .github/workflows/codeql.yml
name: CodeQL

on:
  pull_request:
  push:
    branches: [ main ]

permissions:
  actions: read
  contents: read
  security-events: write

jobs:
  analyze:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        language: [ javascript-typescript ]

    steps:
      - uses: actions/checkout@v6
      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
      - name: Autobuild
        uses: github/codeql-action/autobuild@v3
      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
```

이제 남는 건 계약 조항 하나입니다.

- code scanning check가 실패하면 merge 불가

rulesets 문서에도 “Require code scanning results” 규칙이 있고, 특정 severity 이상을 막는 형태로 설정할 수 있다고 명시합니다.

- [GitHub Docs: rulesets의 code scanning 강제 옵션](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)

에이전트 PR이 늘어날수록, 리뷰어가 읽을 수 없는 양이 늘고, 그 빈자리를 메우는 건 정적 분석/스캔/게이트입니다.

## 감사·롤백: provenance 없이는 에이전트 PR을 운영할 수 없다

에이전트 PR이 인간 PR보다 더 위험한 이유는 “모른 채 merge할 수 있는 범위”가 커지기 때문입니다. 그걸 줄이는 방법은 두 가지입니다.

- merge 전에 더 많이 검증
- merge 후에는 더 쉽게 추적하고 되돌림

여기서 GitHub가 제공하는 실전 도구가 artifact attestations입니다.

GitHub 문서에는 Actions로 provenance를 만드는 방법이 단계별로 적혀 있고, `actions/attest@v4`를 사용하라고 명시합니다.

- [GitHub Docs: artifact attestations로 provenance 만들기](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub Action: actions/attest](https://github.com/actions/attest)

이 기능은 에이전트 PR 자체를 검증하지는 않습니다. 대신 “이 바이너리/이미지가 어떤 소스와 어떤 빌드에서 나왔는지”를 남깁니다. 에이전트가 코드 생성 속도를 높일수록, 배포 artifact의 출처를 남기는 비용을 낮춰야 합니다.

컨테이너 이미지를 빌드하고 attestation을 남기는 workflow는 아래처럼 구성됩니다.

```yaml
# .github/workflows/build-and-attest.yml
name: Build and Attest
on:
  push:
    branches: [ main ]

permissions:
  id-token: write
  contents: read
  attestations: write
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:sha-${{ github.sha }}

      - name: Attest image
        uses: actions/attest@v4
        with:
          subject-name: ghcr.io/${{ github.repository }}
          subject-digest: ${{ steps.build.outputs.digest }}
          push-to-registry: true
```

이 상태에서 팀 계약은 롤백을 더 단순하게 만들 수 있습니다.

- 문제가 생기면 “어떤 PR이 원인인가”를 찾기 전에, 먼저 “어떤 artifact가 문제인가”를 잡는다.
- 그 artifact의 provenance로 소스/빌드/커밋을 역추적한다.
- 커밋 단위가 아니라 artifact 단위로 롤백을 실행한다.

에이전트 시대에는 “커밋이 많아지는 것” 자체가 정상이 됩니다. Octoverse도 agent configuration file이 있는 새 repo가 없는 repo보다 평균 commit이 8배라는 식의 설명을 붙였습니다. commit이 많아지면 사람은 commit 단위로 추적하지 못합니다. artifact 단위로 운영을 바꿔야 합니다.

여기서 **artifact attestation**은 PR 리뷰를 대체하는 게 아니라, 사고 대응 시간을 줄이는 장치입니다.

## 회의론: 통계는 정책을 강제하지 않고, 정책은 비용을 만든다

Octoverse 2026 통계를 근거로 바로 규정을 강화하면 반발이 생깁니다. 반발 지점은 보통 네 가지입니다.

1) agent-started PR은 감지 가능한 first draft 기준이고, 에이전트 사용 전체를 대표하지 않는다.

2) PR 개수 비중이 높아도, 코드 라인/중요 변경 비중이 같다는 보장은 없다. 문서 PR, 의존성 업데이트 PR, 린트 수정 PR이 포함될 수 있다.

3) 게이트가 늘면 CI 비용이 늘고, merge가 느려진다.

4) 규정은 지키는 사람이 아니라 회피하는 사람을 만든다. 템플릿은 빈칸 채우기 놀이가 될 수 있다.

그래서 계약은 기술 스펙이 아니라 비용 모델을 포함해야 합니다.

- 어떤 종류의 PR에서 어떤 게이트를 mandatory로 둘 것인가
- 어떤 종류의 PR은 “사람이 읽는 리뷰” 대신 “스캔 통과 + 책임자 승인”으로 단축할 것인가
- 어떤 팀이 Actions minutes / runner 비용을 소유할 것인가

나는 에이전트 PR이 늘어날수록 “모든 PR 동일 규칙”은 오래 못 간다고 봅니다. 대신 “위험도 분류를 PR template로 강제하고, 분류에 따라 required check 세트가 달라지는 구조”로 가는 게 자연스럽습니다.

GitHub rulesets는 점점 이런 운영을 전제로 진화하고 있습니다. rulesets 문서에 license compliance, code scanning, code coverage 같은 조건들이 나열되는 이유도 여기에 있습니다.

## 앞으로 지켜볼 것: Fusion, agentic workflows, 그리고 저장소 내부의 자동화

Octoverse 2026의 모델 다변화 통계는 도구가 더 복잡해질 가능성을 말해줍니다. 특히 Octoverse는 Project HydraFusion이 Copilot Fusion으로 GA가 됐다고 서술하고, Copilot Fusion 문서에서는 “Copilot Fusion은 사용한 모델 각각에 대해 과금된다”와 “2026-11-30까지 30% 할인” 같은 조건을 명시합니다.

- [GitHub Docs: Copilot Fusion의 과금과 2026-11-30 할인](https://docs.github.com/en/enterprise-cloud@latest/copilot/concepts/models/copilot-fusion)

멀티 모델 오케스트레이션이 기본값이 되면, 팀 정책은 더더욱 모델 리스트를 직접 관리하는 방식에서 멀어져야 합니다. 대신 결과물을 검증하는 자동 게이트를 강화하는 쪽이 유지비가 낮습니다.

그리고 GitHub Agentic Workflows 같은 저장소 내부 자동화는 “에이전트가 PR을 열어주는 기능”을 넘어서, “저장소가 에이전트 실행 환경을 규정하는 기능”으로 발전하고 있습니다. GitHub 문서에는 agentic workflow가 `.github/workflows/` 아래의 markdown 파일이며, YAML frontmatter + 자연어 지시문으로 구성되고, `.lock.yml`로 컴파일해 함께 커밋한다고 적어두었습니다.

- [GitHub Docs: GitHub Agentic Workflows 생성 방식](https://docs.github.com/en/copilot/how-tos/github-agentic-workflows/creating-github-agentic-workflows)

이 흐름은 팀 계약을 코드로 박기 좋은 환경을 만듭니다. 에이전트에게 “이 repo에서는 어떤 규칙을 따라야 하는가”를 문서가 아니라 실행 가능한 형태로 남길 수 있기 때문입니다.

내 경우 이 영역은 예전에 정리한 글들에서 Rules/Agents/MCP 기반 운영으로 다뤘고, 여기서는 반복하지 않겠습니다.

- [Rules/Agents/MCP로 도구를 프로젝트에 붙이는 운영 흐름](https://daewooki.github.io/posts/cursorcopilotwindsurf-2026-7-rulesagents-1/)
- [에이전트가 일하는 저장소를 만드는 repo-side 구성](https://daewooki.github.io/posts/cursorcopilotwindsurf-2026-8-1/)

## 지금 할 수 있는 일: repo-level 계약 템플릿으로 고정

Octoverse 2026이 던진 건 “에이전트가 늘었다”가 아니라 “기본이 됐다”입니다. 기본이 되면 표준이 필요합니다. 표준은 문서가 아니라 차단 장치여야 합니다.

아래는 실제로 저장소에 커밋 가능한 최소 구성입니다.

### 1) PR template 커밋

- `.github/pull_request_template.md`
- 위험도 분류 + 검증 근거 + 라이선스/출처 + 롤백 계획을 강제

GitHub가 template 위치/동작을 문서화해 두었으니, 팀이 합의한 포맷을 그대로 저장소에 박으면 됩니다.

- [GitHub Docs: PR template 파일 위치와 적용 방식](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository)

### 2) CODEOWNERS 커밋 + code owner 승인 강제

- `.github/CODEOWNERS`
- rulesets에서 “Require review from code owners”를 켠다

- [GitHub Docs: CODEOWNERS와 required review](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)

### 3) 필수 스캔 workflow 3종 커밋

- CodeQL (가능하면)
- dependency-review-action
- secret scanning review action (플랜/권한이 되는 경우)

각 workflow는 “켜는 것”이 목적이 아니라 “rulesets에서 required check로 묶을 수 있는 이름을 제공하는 것”이 목적입니다.

- [GitHub Action: dependency-review-action](https://github.com/actions/dependency-review-action)
- [GitHub Action: secret-scanning-review-action](https://github.com/advanced-security/secret-scanning-review-action)
- [GitHub Docs: code scanning advanced setup](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configuring-advanced-setup-for-code-scanning)

### 4) Copilot public-code matching 정책을 조직 단위로 통일

- 기본 Block
- Allow는 예외로 두고 reference를 PR 본문에 남기게 강제

- [GitHub Docs: public code match Allow/Block 정책](https://docs.github.com/en/copilot/how-tos/manage-your-account/manage-policies)
- [GitHub Docs: 매칭 suggestion의 license/URL 기록](https://docs.github.com/en/copilot/concepts/copilot-surfaces/copilot-in-ides)

### 5) 배포 artifact가 있는 저장소는 provenance까지 포함

- build-and-attest workflow 추가
- 문제가 생겼을 때 PR이 아니라 artifact를 기준으로 rollback

- [GitHub Docs: artifact attestations 사용법](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)

## 정리: 에이전트 PR은 기능이 아니라 운영 대상이다

2026-10-28 공개된 Octoverse 2026은 에이전트가 PR 초안을 쓰는 흐름이 실험 단계를 넘어섰다는 걸 수치로 못 박았습니다. 2026년 9월에 PR의 40% 이상이 에이전트 first draft에서 시작되고, 모델은 47개로 분산되며, 단일 모델이 과반을 점유하지 못하는 환경에서는 “허용/금지” 같은 단일 스위치로 팀을 방어할 수 없습니다.

팀이 할 일은 에이전트를 통제하는 게 아니라, 변경을 통제하는 것입니다. PR template, CODEOWNERS, rulesets, 보안 스캔, provenance를 조합해 리뷰를 계약으로 바꾸는 순간부터, 에이전트는 위험 요소가 아니라 처리량을 올리는 도구가 됩니다.

## 참고 자료

- [Octoverse 2026: Commits, pushes, reach new highs in 2026 as developers build with agents](https://github.blog/news-insights/octoverse/octoverse-commits-pushes-reach-new-highs-in-2026-as-developers-build-with-agents/)
- [GitHub Docs: About GitHub Copilot Fusion](https://docs.github.com/en/enterprise-cloud@latest/copilot/concepts/models/copilot-fusion)
- [GitHub Docs: Creating GitHub Agentic Workflows](https://docs.github.com/en/copilot/how-tos/github-agentic-workflows/creating-github-agentic-workflows)
- [GitHub Docs: Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [GitHub Docs: Creating a pull request template for your repository](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository)
- [GitHub Docs: About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- [GitHub Docs: Managing GitHub Copilot policies as an individual subscriber](https://docs.github.com/en/copilot/how-tos/manage-your-account/manage-policies)
- [GitHub Docs: GitHub Copilot in IDEs](https://docs.github.com/en/copilot/concepts/copilot-surfaces/copilot-in-ides)
- [GitHub Docs: Push protection](https://docs.github.com/en/code-security/concepts/secret-security/push-protection)
- [GitHub Docs: Configuring advanced setup for code scanning](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configuring-advanced-setup-for-code-scanning)
- [GitHub Action: actions/dependency-review-action](https://github.com/actions/dependency-review-action)
- [GitHub Action: advanced-security/secret-scanning-review-action](https://github.com/advanced-security/secret-scanning-review-action)
- [GitHub Docs: Using artifact attestations to establish provenance for builds](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub Action: actions/attest](https://github.com/actions/attest)
- [GitHub Docs: About open source license compliance](https://docs.github.com/en/code-security/concepts/supply-chain-security/open-source-license-compliance)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
