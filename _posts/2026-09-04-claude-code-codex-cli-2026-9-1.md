---
title: "Claude Code × Codex CLI 에이전트(2026년 9월): “터미널에서 끝나는” 자동화 코딩 워크플로 설계 가이드"
date: 2026-09-04 04:07:48 +0900
categories: [AI, Coding]
tags: [ai, coding, trend, 2026-09]
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
CLI 기반 AI 코딩 에이전트(Claude Code, Codex CLI)는 “IDE 보조”를 넘어 **리포지토리 단위 작업을 자동화**하는 쪽으로 무게중심이 옮겨왔습니다. 특히 2026년 들어 GitHub가 **GitHub Agentic Workflows**(Markdown으로 정의 → 컴파일 → Actions로 실행)라는 형태로 *에이전트 실행을 워크플로 자산으로 관리*하는 흐름을 만들면서, “로컬 터미널에서 검증된 패턴을 CI로 확장”하는 길이 열렸습니다. ([docs.github.com](https://docs.github.com/en/copilot/how-tos/github-agentic-workflows/creating-github-agentic-workflows?utm_source=openai))

이 글의 목표는 “Claude Code + Codex CLI를 같이 쓰면 뭐가 좋다” 수준이 아니라, **내 프로젝트에 적용 가능한 자동화 워크플로를 어떻게 설계/운영할지** 판단 기준을 주는 것입니다.

- 언제 쓰면 좋은가
  - **반복되는 repo 작업**(changelog/릴리즈 노트, 대규모 리팩터링, 테스트 보강, 보안 취약점 수정 후보 탐색, 문서 동기화)을 *사람 리뷰 포함*으로 자동화할 때
  - “요구사항 → 계획 → 코드 변경 → 테스트/린트 → PR” 같은 **다단계 루프**를 표준화하고 싶을 때
- 언제 쓰면 안 되는가
  - 권한/비밀정보/공급망 리스크를 통제할 체계 없이 “그냥 Actions에서 에이전트 CLI를 풀오토로 돌리려는” 경우  
    (GitHub도 *코딩 에이전트를 Actions에서 직접 실행하는 건 충분한 보안 아키텍처 없이는 비추천*이라고 명시합니다.) ([github.github.com](https://github.github.com/gh-aw/engines/codex/?utm_source=openai))
  - 실패 비용이 큰 운영계 작업(데이터 마이그레이션, 인프라 변경)을 **승인 게이트 없이** 자동 실행하려는 경우

---

## 🔧 핵심 개념
### 1) “에이전트”를 CLI에서 쓸 때 생기는 구조적 이점
CLI 에이전트의 본질은 “코드를 써주는 모델”이 아니라, **로컬/CI 환경에서 도구를 호출하며 목표를 달성하는 런타임**입니다. 그래서 설계 포인트가 IDE 자동완성과 다릅니다.

- **State(상태)**: 대화/스레드/메모리/목표(goal) 같은 작업 상태를 유지
- **Tools(도구)**: 테스트, 린트, 빌드, git, 검색, 외부 시스템(Jira/GitHub API 등) 호출
- **Policy(정책)**: 승인(approval), 권한, 네트워크/파일 접근 제어, “무엇을 자동으로 해도 되는가”

Codex CLI는 repo 가이드라인을 `AGENTS.md`로 계층적으로 합성(개인 전역 → repo 루트 → 서브폴더)하는 패턴을 강조합니다. 이 방식은 “프롬프트를 매번 복붙”하는 대신 **프로젝트 규칙을 코드처럼 버전관리**하게 해줍니다. ([github.com](https://github.com/syntax-syndicate/codex-agentic-cli?utm_source=openai))

### 2) Claude Code ↔ Codex CLI “같이” 쓰는 포인트: 역할 분리
2026년 기준 실무에서 제일 성능이 나오는 조합은 보통 이겁니다.

- **Claude Code**: 상위 설계/리뷰/위험 분석/변경 범위 조절에 강점(“하네스(harness)” 역할)
- **Codex CLI**: repo 내부 변경을 실제로 수행하는 실행기(“작업자(worker)” 역할), CI/비대화형 모드에 강점

여기에 **MCP(Model Context Protocol)**를 붙이면 “에이전트가 쓸 수 있는 도구 목록”을 표준 인터페이스로 외부화할 수 있습니다. Codex CLI도 `config.toml`에 `mcp_servers`를 등록해 MCP 서버를 붙이는 흐름을 제공하고, 실험적으로 `codex mcp`로 Codex 자체를 MCP 서버처럼 띄우는 방식도 언급됩니다. ([github.com](https://github.com/syntax-syndicate/codex-agentic-cli?utm_source=openai))  
즉, **Claude Code(오케스트레이터) → MCP 도구 → Codex CLI(리포 변경)** 같은 구조를 만들 수 있습니다.

### 3) GitHub Agentic Workflows: “에이전트 실행”을 워크플로 자산으로 만들기
GitHub Agentic Workflows는 워크플로를 Markdown으로 쓰고(`.md`), 이를 lock 파일로 컴파일(`.lock.yml`)해서 Actions 트리거로 실행하는 모델입니다. 그리고 엔진으로 **Claude, Codex, Gemini, Copilot** 등을 선택할 수 있습니다. ([docs.github.com](https://docs.github.com/en/copilot/how-tos/github-agentic-workflows/creating-github-agentic-workflows?utm_source=openai))  
여기서 중요한 차이는:

- “Actions에서 임의로 codex 설치하고 실행” vs
- “Agentic Workflows 엔진으로 codex/claude를 지정하고, GitHub가 제공하는 트리거/샌드박스/안전 출력(safe outputs) 패턴을 활용”

후자가 **감사 가능성(auditability)**과 **권한 경계**를 만들기 훨씬 좋습니다. ([github.github.com](https://github.github.com/gh-aw/engines/codex/?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: **매주 월요일 아침**, repo에서 지난 주 변경을 기반으로
1) 변경 요약 리포트 생성  
2) `CHANGELOG.md` 초안 업데이트  
3) 테스트/린트 통과 확인  
4) PR 생성(사람이 최종 리뷰/머지)

여기서는 “로컬에서 Codex CLI로 검증 → GitHub Agentic Workflows로 이관” 2단계로 빌드업합니다.

### (1) 초기 셋업: AGENTS.md로 ‘프로젝트 규칙’을 고정
repo 루트에 `AGENTS.md`:

```text
# AGENTS.md (repo root)

You are a coding agent operating in this repository.

## Non-negotiables
- Never commit secrets. Never print secrets.
- All changes must keep `pnpm test` and `pnpm lint` passing.
- Prefer small, reviewable commits.
- For changelog edits: follow Keep a Changelog style and reference PR numbers if available.

## Workflow
1) Plan briefly (bullets).
2) Implement minimal diff.
3) Run tests+lint.
4) Summarize changes and risks.

## Output format for reports
- Summary (5 bullets max)
- Notable PRs/areas
- Risks/Follow-ups
```

Codex가 `~/.codex/AGENTS.md` → repo `AGENTS.md` → 폴더별 `AGENTS.md`를 합성한다는 점이 핵심입니다. 폴더별로 더 엄격한 규칙(예: `infra/`는 반드시 승인 필요)을 추가할 수 있습니다. ([github.com](https://github.com/syntax-syndicate/codex-agentic-cli?utm_source=openai))

### (2) 로컬에서 Codex CLI “헤드리스 실행”으로 자동 수정 + 검증
예: release 준비용 스크립트 `scripts/release_assistant.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# prerequisites:
# - Node.js installed
# - pnpm installed
# - Codex CLI installed: npm i -g @openai/codex
# - OPENAI_API_KEY exported

git fetch origin
git checkout -B chore/changelog-draft

echo "[1/4] Asking Codex to draft changelog..."
codex exec --full-auto "
Update CHANGELOG.md for the next release.

Constraints:
- Only include changes since the last git tag.
- If you need PR numbers, infer from merge commits when possible.
- Keep entries concise and grouped by Added/Changed/Fixed.

After editing, run: pnpm test && pnpm lint
If tests fail, fix them.
"

echo "[2/4] Show diff:"
git --no-pager diff

echo "[3/4] Commit if there are changes:"
if ! git diff --quiet; then
  git add CHANGELOG.md
  git commit -m "chore: draft changelog for next release"
fi

echo "[4/4] Done. Next: open a PR."
```

- `codex exec --full-auto` 같은 비대화형/CI 스타일 실행은 공식 문서/예시에서도 강조됩니다. ([github.com](https://github.com/syntax-syndicate/codex-agentic-cli?utm_source=openai))
- 예상 출력(요지)
  - “Plan:” (AGENTS.md에서 요구한 플랜)
  - `CHANGELOG.md` diff
  - `pnpm test`, `pnpm lint` 실행 로그
  - 실패 시 재시도 후 성공

여기서 포인트는 **에이전트에게 “편집 + 검증 커맨드”를 같이 묶어** 실제 품질 게이트를 통과하게 만드는 겁니다.

### (3) GitHub Agentic Workflows로 이관: “스케줄 트리거 + PR 생성”을 워크플로 자산화
GitHub Docs가 설명하는 흐름은 “Markdown으로 워크플로 정의 → 컴파일 → Actions 실행”입니다. ([docs.github.com](https://docs.github.com/en/copilot/how-tos/github-agentic-workflows/creating-github-agentic-workflows?utm_source=openai))  
아래는 개념 예시(구체 스키마는 repo에 `gh aw init`로 생성되는 스킬/템플릿에 맞춰 조정):

```yaml
# .github/agentic-workflows/weekly-changelog.md (concept)
---
engine: codex
---

# Weekly Changelog + Report

Generate a weekly engineering report and draft a changelog entry.
- Create a branch: chore/weekly-changelog-{{date}}
- Update CHANGELOG.md
- Generate docs/weekly-report.md
- Run: pnpm test && pnpm lint
- Open a PR with the summary and risks.
```

Codex를 엔진으로 선택하는 방법(워크플로 frontmatter에서 `engine: codex`)과, 인증을 `OPENAI_API_KEY` 또는 `CODEX_API_KEY` 시크릿으로 넣는 패턴이 문서에 나옵니다. ([github.github.com](https://github.github.com/gh-aw/engines/codex/?utm_source=openai))  
또한 Codex를 GitHub Copilot inference로 붙이는 구성도 소개되어(“codex + GitHub as engine”) 비용/정책을 조직 표준에 맞추는 선택지도 생깁니다. ([github.github.com](https://github.github.com/gh-aw/engines/codex/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “승인(approval) 경계”를 작업 단위로 쪼개라
풀오토로 다 밀어붙이면 초반엔 빨라 보이지만, 결국 **리뷰 부하/사고 위험**이 폭발합니다.  
추천 패턴:
- 로컬: `--full-auto`는 *changelog/문서/테스트 보강* 같이 안전한 영역에서만
- CI: PR 생성까지만 자동, merge는 금지(사람 승인)

GitHub도 “Actions에서 코딩 에이전트 CLI를 직접 돌리는 건 보안 아키텍처 없이는 비추천”이라고 못박습니다. 즉, 최소한 **샌드박스/권한/출력 통제**가 가능한 구조로 가져가야 합니다. ([github.github.com](https://github.github.com/gh-aw/engines/codex/?utm_source=openai))

### Best Practice 2) AGENTS.md를 “프롬프트”가 아니라 “운영 규정”으로 다뤄라
- repo 루트에는 *공통 품질 게이트* (테스트/린트/보안)
- 폴더별 AGENTS.md에는 *도메인 규칙* (예: `payments/`는 breaking change 금지, `infra/`는 Terraform plan 첨부 필수)

Codex가 AGENTS.md를 위치별로 합성하는 구조라서, 이 계층화가 곧 “조직의 개발 규칙”이 됩니다. ([github.com](https://github.com/syntax-syndicate/codex-agentic-cli?utm_source=openai))

### Best Practice 3) MCP는 “도구 확장”이 아니라 “권한 모델”로 설계
MCP 서버를 붙이면 에이전트가 더 많은 시스템에 접근할 수 있습니다. 즉,
- 생산성 ↑
- 공급망/권한/데이터 유출 리스크도 ↑

Codex CLI는 `config.toml`에 `mcp_servers`로 MCP 서버를 등록하는 방식을 제공합니다. 여기서 중요한 건 “편의상 npx로 아무 MCP나 붙이기”가 아니라, **허용 도구 목록과 환경변수 범위를 최소화**하는 겁니다. ([github.com](https://github.com/syntax-syndicate/codex-agentic-cli?utm_source=openai))

### 흔한 함정) “테스트 통과”를 에이전트 말로만 믿는 것
에이전트가 “tests passed”라고 말하는 건 로그 위조가 아니라도 **실행 스킵/부분 실행**이 섞일 수 있습니다.  
반드시:
- CI에서 동일 커맨드 재실행
- 결과를 체크섬처럼 남기기(예: junit/xml 업로드, lint 리포트 아카이브)

### 비용/성능/안정성 트레이드오프
- 멀티스텝 작업은 토큰/시간이 길어져 **비용이 선형이 아니라 폭발**하는 구간이 있음(재시도/루프 때문)
- 그래서 “긴 작업 1개”보다 “짧은 작업 N개 + 사람이 합치는 구조”가 더 싸고 안전한 경우가 많습니다.
- GitHub Agentic Workflows는 사용량/추정 비용을 검토하는 흐름을 제공한다고 문서에서 언급합니다(운영 관점에서 유리). ([docs.github.com](https://docs.github.com/en/copilot/concepts/agents/about-github-agentic-workflows?utm_source=openai))

---

## 🚀 마무리
2026년 9월 시점에서 Claude Code와 Codex CLI를 “에이전트”로 제대로 쓰려면, 핵심은 모델 성능보다 **워크플로 아키텍처**입니다.

- **Codex CLI**: `AGENTS.md`로 규칙을 코드화하고, 비대화형 실행으로 “편집+검증” 루프를 자동화하기 좋음 ([github.com](https://github.com/syntax-syndicate/codex-agentic-cli?utm_source=openai))  
- **Claude Code**: 상위 오케스트레이션/리뷰/리스크 제어에 강점을 두고, 필요 시 Codex 작업을 호출하는 구조로 설계
- **GitHub Agentic Workflows**: 에이전트 실행을 Actions에 안전하게 얹기 위한 “공식 프레임”에 가까움(트리거/샌드박스/엔진 선택/비용 가시성) ([docs.github.com](https://docs.github.com/en/copilot/how-tos/github-agentic-workflows/creating-github-agentic-workflows?utm_source=openai))

도입 판단 기준(체크리스트):
1) 반복 작업이 “명확한 입력/출력”으로 정의되는가? (Yes면 적합)  
2) 승인/권한 경계를 설계할 수 있는가? (No면 보류)  
3) 테스트/린트/보안 게이트를 자동으로 강제할 수 있는가? (No면 ROI 낮음)  
4) MCP로 붙일 외부 시스템이 있는가? 있다면 최소 권한으로 통제 가능한가?

다음 학습 추천:
- GitHub Agentic Workflows의 엔진 선택/컴파일/트리거 모델을 먼저 익히고 ([docs.github.com](https://docs.github.com/en/copilot/how-tos/github-agentic-workflows/creating-github-agentic-workflows?utm_source=openai))  
- 그 다음 Codex CLI의 `AGENTS.md` 계층화 + MCP 연결을 통해 “조직 규칙/도구 접근”을 표준화하세요. ([github.com](https://github.com/syntax-syndicate/codex-agentic-cli?utm_source=openai))