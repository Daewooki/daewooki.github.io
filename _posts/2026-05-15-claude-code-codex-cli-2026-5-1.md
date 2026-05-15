---
title: "Claude Code + Codex CLI 에이전트로 “터미널에서 끝나는” 자동화 코딩 워크플로 만들기 (2026년 5월 기준)"
date: 2026-05-15 04:06:13 +0900
categories: [AI, Coding]
tags: [ai, coding, trend, 2026-05]
---

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>

## 들어가며
CLI 기반 AI 코딩 에이전트가 진짜로 가치가 나는 지점은 “IDE에서 한 번 질문하고 끝”이 아니라, **반복되는 엔지니어링 업무를 파이프라인/스크립트로 굳히는 순간**입니다. 예를 들면:

- PR 들어올 때마다: 변경 영향 범위 분석 → 테스트 보강 → 릴리즈 노트 초안 생성
- 매일/매주: 의존성 업데이트 → 빌드/테스트 → 실패 원인 triage → 이슈 생성
- 장애 대응: 로그/메트릭 요약 → 재현 시나리오 구성 → 수정 PR 초안

2026년 5월 시점에서 흥미로운 변화는, **Claude Code가 “대화형 CLI”를 넘어 “Headless/Agent SDK(= `claude -p`)”로 자동화 워크플로에 더 직접 들어온다는 점**입니다. 특히 `--bare`, `--allowedTools`, `--output-format`, `--bg` 같은 플래그 조합이 “CI에서 안정적으로 굴릴 수 있는 에이전트” 쪽으로 기능을 정리해주고 있어요. ([code.claude.com](https://code.claude.com/docs/en/headless))

반대로, 다음 상황이면 당장 도입을 말립니다.

- **요구사항이 자주 바뀌는 핵심 비즈니스 로직**을 에이전트가 마음대로 수정하게 두는 경우(회귀/규정 위반 비용이 큼)
- **권한/보안 경계가 불명확한 저장소**(토큰/키가 섞여 있고, 어떤 커맨드가 실행될지 통제 불가)
- “한 번에 대규모 리팩터링”처럼 **세션이 길어지고 산출물이 커지는 작업**(길어질수록 instruction adherence가 떨어진다는 실험 결과도 있음) ([arxiv.org](https://arxiv.org/abs/2605.10039?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Claude Code의 “CLI 에이전트 루프”를 자동화로 끌어오는 방법: `claude -p`(Headless)
Claude Code 문서에서 명시적으로, **Agent SDK가 Claude Code를 구동하는 동일한 도구/agent loop/context management를 제공**한다고 설명합니다. 즉, 대화형 CLI에서 하던 “읽기→수정→커맨드 실행→검증” 루프를 **비대화형 실행**으로 가져오는 게 핵심입니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

- `claude -p "..."` : non-interactive(출력만 받고 끝)
- `--allowedTools "Read,Edit,Bash(...)"` : “허용된 행동만” 자동 승인(중요)
- `--output-format` : 구조화 출력(파이프라인에 붙이기 좋음)
- `--continue` : 동일 디렉터리 컨텍스트에서 대화 이어가기
- `--bg` : background agent로 돌리고 세션 ID를 받아 추적 ([code.claude.com](https://code.claude.com/docs/en/headless))

여기서 중요한 관점은: **CLI 에이전트를 ‘똑똑한 사람’으로 쓰지 말고 ‘권한이 제한된 자동화 작업자’로 써야** CI/CD에서 사고가 안 납니다.

### 2) 재현성과 속도를 만드는 `--bare`
자동화에서 제일 자주 터지는 문제가 “내 노트북에서는 됐는데 CI에서 다르게 동작”입니다. Claude Code는 기본적으로 훅/스킬/플러그인/MCP 서버/메모리/CLAUDE.md 등 프로젝트+사용자 환경을 읽어 컨텍스트를 구성하는데, 이게 **머신마다 달라질 수 있는 요인**입니다.

`--bare`는 그걸 통째로 스킵해서 **항상 같은 시작 조건**으로 만듭니다(대신 훅/MCP/메모리/CLAUDE.md 기반의 편의 기능도 꺼짐). CI에는 보통 이 모드가 더 맞습니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

### 3) “Claude Code vs OpenAI Codex CLI”를 같이 보는 이유
요구 주제에 “Claude Code + Codex CLI 에이전트 활용”이 같이 들어간 건, 2026년에는 많은 팀이 **단일 벤더 에이전트**가 아니라 “오케스트레이터 + 전문 에이전트” 형태로 갑니다.

- **Codex CLI**: 로컬 터미널에서 읽고/고치고/실행하는 OpenAI 코딩 에이전트. “오픈소스, Rust 기반”을 강점으로 전면에 내세웁니다. ([codex-console.com](https://codex-console.com/cli))
- **Claude Code(Agent SDK 포함)**: `claude -p`, `--bare`, `--bg` 같은 자동화 지향 플래그가 정리되어 있고, “permission 통제”를 워크플로 설계의 중심에 둡니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

실무에서는 “PR 리뷰/테스트 보강은 Claude Code”, “특정 리포의 반복 수정은 Codex CLI”처럼 **작업 특성에 맞춰 붙이는** 방식이 점점 자연스러워지고 있습니다(특히 병렬 에이전트 운영이 일반화되는 흐름). ([code.claude.com](https://code.claude.com/docs/en/cli-reference))

---

## 💻 실전 코드
아래는 “CI에서 PR 단위로 **변경 파일 기반 테스트 보강 + 빠른 안전 리뷰**”를 돌리는 현실적인 예시입니다.

전제:
- repo는 Node/TypeScript 모노레포(예: `apps/api`, `packages/shared`)
- PR에서 바뀐 파일을 기준으로 영향 범위를 요약하고,
- **테스트가 약한 부분만** 추가 테스트를 생성/수정하고,
- 마지막에 **git diff를 사람이 리뷰**할 수 있게 만든다.

### 1) 초기 셋업: 권한/재현성 우선 CLI 래퍼
```bash
#!/usr/bin/env bash
set -euo pipefail

# scripts/ai/claude_pr_guard.sh
# 목적: PR에서 변경된 영역에 대해 테스트 보강 + 안전 리뷰를 "권한 제한" 하에 수행

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY is required}"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BASE_REF="${1:-origin/main}"

CHANGED_FILES=$(git diff --name-only "$BASE_REF"...HEAD | tr '\n' ' ')
if [[ -z "${CHANGED_FILES// }" ]]; then
  echo "No changed files."
  exit 0
fi

echo "Changed files: $CHANGED_FILES"

# (핵심) bare 모드로 환경 의존성을 제거하고,
# allowedTools로 실행 커맨드를 최소화해 "자동화 사고"를 줄인다.
claude --bare -p \
  --allowedTools "Read,Edit,Bash(git diff *),Bash(git status *),Bash(npm test *),Bash(pnpm test *),Bash(bun test *),Bash(node *),Bash(npm run test *),Bash(pnpm run test *)" \
  --exclude-dynamic-system-prompt-sections \
  "You are a CI coding agent.
Repository: $ROOT
Base ref: $BASE_REF
Changed files: $CHANGED_FILES

Task:
1) Inspect diffs (git diff) and identify the highest-risk changes.
2) Add/modify tests ONLY where coverage is missing or regression risk is high.
3) Run the smallest relevant test command (prefer targeted tests).
4) Do not refactor unrelated code.
5) Output: summarize what you changed and why, and list the exact commands you ran."
```

예상 출력(요지):
- 변경 위험 요약(예: auth 로직 변경, edge case 누락)
- 수정된 테스트 파일 목록
- 실행한 테스트 커맨드(npm/pnpm/bun 중 1~2개)
- 남은 리스크(“통합 테스트 환경 없어서 여기까지만 확인”)  

여기서 포인트는 **“변경 파일만 주고 agent가 repo 전체를 방황하지 않게”** 만드는 겁니다. 또한 `--bare`로 훅/MCP/메모리 영향 제거, `--exclude-dynamic-system-prompt-sections`로 멀티 유저/멀티 머신에서 프롬프트 캐시 재사용성을 높여 비용/지연을 줄이는 방향입니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

### 2) 확장: 백그라운드 에이전트로 병렬 실행(긴 작업 분리)
테스트 생성은 짧게 끝나지만, “플레이키 테스트 조사” 같은 건 오래 걸립니다. 이때 `--bg`로 세션을 분리하면 CI가 타임아웃에 덜 취약해집니다. ([code.claude.com](https://code.claude.com/docs/en/cli-reference))

```bash
# scripts/ai/claude_flaky_triage.sh
#!/usr/bin/env bash
set -euo pipefail
: "${ANTHROPIC_API_KEY:?}"

cd "$(git rev-parse --show-toplevel)"

claude --bare --bg \
  --allowedTools "Read,Bash(git log *),Bash(git diff *),Bash(pnpm test *),Bash(npm test *),Bash(bun test *)" \
  "Investigate the flaky test failures in CI.
- Identify the most likely root cause
- Propose a minimal fix OR a quarantine strategy
- Provide reproduction steps and commands"
```

출력으로 세션 ID/관리 커맨드가 나오고, 별도 잡/로컬에서 추적하는 식으로 운영할 수 있습니다. ([code.claude.com](https://code.claude.com/docs/en/cli-reference))

### 3) (선택) Codex CLI를 “보조 작업자”로 붙이는 패턴
Codex CLI는 설치/실행 플로우가 단순하고(로그인 후 `codex` 실행), 로컬에서 빠르게 반복 수정하는 작업에 붙이기 좋습니다. ([codex-console.com](https://codex-console.com/cli))

```bash
# 예: 동일 변경사항을 다른 에이전트로 교차검증(“리뷰 전용”)
codex <<'EOF'
Review the current git diff. Focus on security and backward compatibility.
Do not suggest large refactors. Output a checklist of risks.
EOF
```

실무적으로는 **한 에이전트가 만든 diff를 다른 에이전트가 “리뷰 전용”으로 재검증**하는 방식이 사고를 많이 줄여줍니다(특히 권한을 분리할수록).

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) `--allowedTools`는 “화이트리스트 최소화”가 정답
자동화에서 가장 큰 리스크는 “에이전트가 불필요한 커맨드를 실행”하는 겁니다. `Bash(*)` 같은 광범위 허용은 금지하고, 위 예시처럼 **허용할 커맨드 패턴을 좁혀야** 합니다. ([code.claude.com](https://code.claude.com/docs/en/cli-reference))

### Best Practice 2) CI는 `--bare`, 로컬은 컨텍스트 풀옵션(필요 시)
로컬 개발에서는 CLAUDE.md/훅/스킬/MCP가 생산성을 올리지만, CI에서는 변동 요인입니다. CI는 `--bare`로 고정하고, 로컬은 “팀 표준 훅/스킬”만 제한적으로 쓰는 식으로 경계를 나누세요. ([code.claude.com](https://code.claude.com/docs/en/headless))

### Best Practice 3) 긴 세션/큰 산출물은 쪼개라(품질/순응도 이슈)
세션이 길어지고 한 번에 생성하는 코드 단위가 늘수록 instruction adherence가 떨어질 수 있다는 보고가 있습니다. 큰 리팩터링을 “한 방에” 시키기보다,
- (1) 영향 분석
- (2) 테스트 보강
- (3) 최소 수정
처럼 **단계별로 끊고 사람 리뷰 포인트를 박아두는 게** 안전합니다. ([arxiv.org](https://arxiv.org/abs/2605.10039?utm_source=openai))

### 흔한 함정) “편해 보이는 자동 권한 스킵”에 의존
`--dangerously-skip-permissions` 류는 편하지만, 자동화/공유 러너 환경에서 사고 가능성이 큽니다. 권한 스킵이 필요하면 오히려 “무슨 툴을 왜 허용했는지”를 문서화하고 `--allowedTools`로 통제하는 쪽이 운영 친화적입니다. ([code.claude.com](https://code.claude.com/docs/en/cli-reference))

### 비용/성능/안정성 트레이드오프
- 비용: `-p`로 자주 호출하면 호출량이 늘어 **월 비용이 튈 수 있음**. 게다가 Claude Code 문서에 따르면 **2026-06-15부터 구독 플랜에서 Agent SDK/`claude -p` 사용이 별도 월간 Agent SDK credit을 사용**합니다(인터랙티브와 분리). 자동화를 크게 붙이려면 이 날짜를 기준으로 비용 계획을 다시 잡아야 합니다. ([code.claude.com](https://code.claude.com/docs/en/headless))  
- 성능: `--bare`는 스타트업 시간을 줄이고 재현성을 올리지만, 프로젝트별 컨텍스트(스킬/MCP/메모리)를 못 써서 “한 번에 똑똑하게”는 덜할 수 있음.
- 안정성: 병렬(`--bg`)은 처리량을 올리지만, **결과 동기화/세션 관리**(세션 ID 추적, 실패 재시도 설계)가 필요합니다.

---

## 🚀 마무리
핵심은 “Claude Code/Codex CLI를 잘 쓰는 법”이 아니라, **내 워크플로에서 ‘에이전트가 맡아도 되는 일’을 권한/재현성/검증 관점으로 재분배**하는 겁니다.

도입 판단 기준(현실 체크리스트):
- CI에서 **재현 가능하게** 돌릴 수 있는가? (`--bare`, 입력/출력 고정)
- 에이전트가 실행할 수 있는 행동이 **화이트리스트로 통제**되는가? (`--allowedTools`)
- 결과물이 **항상 diff로 남고**, 사람이 승인할 수 있는가?
- 세션이 길어지기 쉬운 작업은 **분할**되어 있는가? (품질/순응도 저하 방지)

다음 학습 추천:
- Claude Code Agent SDK(특히 headless 운용과 CI 연동) 문서와 CLI reference를 정독하고, 팀 표준 “allowedTools 정책”부터 합의하세요. ([code.claude.com](https://code.claude.com/docs/en/headless))
- Codex CLI는 “오픈소스/로컬 반복 수정” 강점을 살려, Claude Code와 **교차 리뷰/교차 실행** 구조로 붙이면 실무 안정성이 좋아집니다. ([codex-console.com](https://codex-console.com/cli))