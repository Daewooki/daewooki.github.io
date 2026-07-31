---
title: "Claude Code × Codex CLI 에이전트, 2026년 7월 기준 “터미널 자동화 워크플로”로 굴리는 법"
date: 2026-07-31 03:36:54 +0900
categories: [AI, Coding]
tags: [ai, coding, trend, 2026-07]
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
CLI 기반 AI 코딩 에이전트(Claude Code, Codex CLI)가 진짜로 해결하는 문제는 “코드 작성” 자체가 아니라 **반복되는 변경 작업의 실행 루프**입니다. 예: 레거시 모듈 리팩터링 → 테스트/린트 실행 → 실패 원인 분석 → 패치 → PR 메시지/체인지로그 정리까지의 흐름을 사람이 매번 끊어 읽고 판단하던 비용을 줄입니다. Claude Code는 로컬에서 레포를 직접 만지며 **권한을 요청하고 단계별로 서술**하는 스타일이고, Codex는 비교적 **자율 실행(autonomy) 성향**이 강한 CLI 에이전트로 포지셔닝되는 비교가 많습니다. ([zapier.com](https://zapier.com/blog/codex-vs-claude-code/?utm_source=openai))

언제 쓰면 좋은가:
- **다단계 변경**(여러 파일/여러 커맨드/테스트 반복)인데, 변경의 규칙이 명확한 작업: 대규모 rename, API 마이그레이션, lint 규칙 일괄 적용, 테스트 실패의 기계적 수정 등
- “내가 의도한 방향”을 문서로 고정할 수 있는 팀: AGENTS.md / SKILL.md / 가이드라인이 갖춰진 레포

언제 쓰면 안 되는가:
- **요구사항이 불명확**하고 제품/도메인 의사결정이 핵심인 작업(결국 사람이 책임져야 해서 에이전트가 시간을 더 잡아먹을 수 있음)
- 보안/규정상 로컬 파일 접근, 명령 실행, 외부 전송이 민감한 환경(특히 secrets 스캔/격리 없이 돌리는 경우)
- “작은 수정 1개”만 필요한데 에이전트가 과하게 움직이는 경우(오히려 diff가 커짐)

---

## 🔧 핵심 개념
### 1) 주요 개념 정의
- **CLI agent loop**: (1) 목표 해석 → (2) 레포 컨텍스트 수집 → (3) 계획 수립 → (4) tool 호출(파일 편집/커맨드 실행) → (5) 결과 관찰 → (6) 재시도/수정의 반복 루프.
- **권한/가드레일**: Claude Code는 로컬에서 작업하며 민감한 동작에 대해 “허용”을 요구하는 흐름이 강조됩니다. “완전 자율”보다 **협업형 에이전트**에 가깝게 설계된 이유가 여기서 나옵니다. ([zapier.com](https://zapier.com/blog/codex-vs-claude-code/?utm_source=openai))
- **Agents(서브에이전트) 구성**: Claude Code는 CLI에서 에이전트를 JSON 형태로 주입해(예: reviewer, implementer) 역할을 나누는 패턴을 공식 문서에 명시합니다. ([code.claude.com](https://code.claude.com/docs/en/cli-usage?utm_source=openai))

### 2) 내부 작동 방식(구조/흐름)
Claude Code를 “터미널 챗봇”으로 쓰면 효율이 제한됩니다. 2026년의 실전형 패턴은 대개 아래 구조로 갑니다.

1. **레포 규칙을 텍스트로 고정**  
   에이전트는 매번 새 세션에서 “팀 룰/아키텍처 의도”를 추론하려고 하면 토큰을 태우고, 잘못 추론하면 대형 사고가 납니다. 그래서 `AGENTS.md`(또는 유사 파일)로 다음을 박아 둡니다.
   - 코드 스타일/금지사항
   - 테스트 실행법
   - 마이그레이션 가이드
   - PR 규칙(커밋 메시지, changelog 등)

2. **역할 기반 서브에이전트로 분업**  
   - implementer: 실제 코드 변경/테스트 수행  
   - reviewer: diff 리뷰 + 위험 지점 체크리스트  
   - release-notes: 변경 요약/마이그레이션 노트  
   Claude Code CLI에서 `--agents`로 주입 가능한 형태가 문서에 나옵니다. ([code.claude.com](https://code.claude.com/docs/en/cli-usage?utm_source=openai))

3. **비대칭 멀티모델 운영(Claude Code ↔ Codex CLI)**
   실무에서 흥미로운 포인트는 “둘 중 하나 고르기”가 아니라 **교차 검증(cross-model review)** 입니다. 커뮤니티/비교 글에서도 “Claude로 설계/오케스트레이션, Codex로 빠른 수정/리뷰”처럼 역할을 나눠 쓰는 사례가 반복해서 등장합니다. ([agentsroom.dev](https://agentsroom.dev/blog/claude-code-vs-codex-cli?utm_source=openai))  
   이 접근의 핵심은:
   - 같은 모델에 self-review를 시키면 **확증 편향**이 남는다
   - 다른 모델로 “반대 심문”을 시키면 결함이 드러날 확률이 올라간다(물론 비용/시간 증가)

### 3) 다른 접근과의 차이점
- IDE inline autocomplete(GitHub Copilot류)는 “지금 커서 주변”에 강하지만, **테스트 실행/여러 파일 편집/커밋** 같은 workflow는 약합니다.
- Codex는 종종 “샌드박스/자율 실행” 쪽으로 비교되고, Claude Code는 “로컬+권한 요청+서술”의 협업적 플로우로 비교됩니다. 결국 **신뢰/감사(audit) 가능성**에서 체감 차이가 납니다. ([zapier.com](https://zapier.com/blog/codex-vs-claude-code/?utm_source=openai))
- 그리고 연구/사례에서도 에이전트의 실패는 “모델이 코드를 몰라서”가 아니라 **tool invocation/command execution 단계**에서 많이 발생한다는 분석이 있습니다. 즉, wrapper/가드레일/재시도 전략이 생산성의 대부분을 좌우합니다. ([arxiv.org](https://arxiv.org/abs/2603.20847?utm_source=openai))

---

## 💻 실전 코드
목표: **모노레포에서 Node/TypeScript 서비스들의 의존성 취약점 패치**를 “계획 → 구현 → 테스트 → 리뷰”까지 자동화 파이프라인으로 굴립니다. toy가 아니라, 실제 팀에서 자주 터지는 상황(패키지 업데이트로 테스트 깨짐, 변경 범위 커짐)을 전제로 합니다.

### 0) 전제/의존성
- `claude`(Claude Code CLI) 설치 및 로그인
- `codex`(Codex CLI) 설치 및 OpenAI API 설정(또는 ChatGPT 플랜/환경에 맞는 방식)
- 레포 루트에 아래 파일 추가:
  - `AGENTS.md` (팀 규칙/테스트 커맨드)
  - `scripts/agent_patch_deps.sh` (오케스트레이션 스크립트)

> Claude Code CLI는 `claude -p`로 비대화형 실행, `-c`로 동일 디렉터리 대화 이어가기, `-r`로 세션 재개 등의 흐름을 공식 문서에서 제공합니다. ([code.claude.com](https://code.claude.com/docs/en/cli-usage?utm_source=openai))

### 1) AGENTS.md (에이전트가 “팀 룰”을 매번 재추론하지 않게)
```markdown
# AGENTS.md

## Goal
- Patch vulnerable deps for packages/* services with minimal diff.
- Never change runtime behavior without tests proving it.

## Commands
- Install: pnpm -r install
- Test: pnpm -r test
- Lint: pnpm -r lint
- Typecheck: pnpm -r typecheck

## Rules
- Prefer smallest semver bump that fixes the CVE.
- If tests fail, explain root cause in PR notes.
- Do not touch .env*, secrets, CI tokens.
- When editing lockfiles, keep changes scoped to affected packages.
```

### 2) Claude Code에 “구현+실행”을 맡기고, Codex로 “반대 심문 리뷰”를 거는 스크립트
```bash
#!/usr/bin/env bash
set -euo pipefail

# scripts/agent_patch_deps.sh
# Usage: bash scripts/agent_patch_deps.sh "CVE summary or advisory text"

ADVISORY="${1:-}"
if [[ -z "$ADVISORY" ]]; then
  echo "Provide advisory text or CVE summary"
  exit 1
fi

echo "== Step 1) Claude: plan + implement + run tests =="

claude -p "
You are the implementer agent.
Read AGENTS.md and follow it strictly.

Task:
- Identify vulnerable dependencies described below.
- Apply minimal upgrades across packages/*.
- Run: pnpm -r install, pnpm -r typecheck, pnpm -r test
- If failures occur, fix them with minimal code changes.
- Output:
  1) A concise PLAN
  2) Commands you ran and their results
  3) A final DIFF summary (files changed)
Advisory:
${ADVISORY}
"

echo "== Step 2) Codex: adversarial review of the diff =="

# 실제 환경에 맞게 diff 범위를 조정하세요(예: main..HEAD, 또는 working tree)
DIFF_TEXT="$(git diff --stat && echo '---' && git diff)"

printf "%s" "$DIFF_TEXT" | codex -p "
You are the reviewer.
Given the git diff, look for:
- behavior changes not covered by tests
- risky transitive upgrades
- lockfile churn
- missing changelog / migration notes
Return:
- Top 5 risks
- Suggested minimal fixes
- A 'ship/no-ship' decision with rationale
"

echo "== Step 3) Claude: apply reviewer feedback =="

# Step2의 출력은 실제로는 파일로 저장해 다시 Claude에 입력하는 게 안정적입니다.
# 여기선 단순화를 위해 '최근 출력 내용을 반영'하라고 지시합니다.
claude -c -p "
Continue in this repo context.
Apply the reviewer feedback from the previous step (I pasted/ran it in the terminal).
Make minimal changes, re-run pnpm -r test, and summarize final status.
"
```

### 3) 예상 출력(현실적인 형태)
- Step 1에서 Claude가:
  - “취약 패키지 X는 packages/a와 packages/b에 있고, 최소 업데이트는 1.2.3→1.2.5” 같은 계획
  - `pnpm -r test` 실패 시 실패 로그 요약 + 원인(예: breaking change로 mock 수정 필요)
  - 최종 변경 파일 목록(`package.json`, `pnpm-lock.yaml`, 특정 테스트 파일)
- Step 2에서 Codex가:
  - lockfile churn 과다 여부, 불필요한 major bump 경고
  - “ship/no-ship” 결론 + 추가 체크 제안
- Step 3에서 Claude가:
  - reviewer 지적을 반영한 최소 수정 + 테스트 재통과 로그

이게 “둘을 같이 쓰는” 핵심 가치입니다. Claude Code의 로컬 오케스트레이션/실행 루프 + Codex의 교차 리뷰를 결합해, 에이전트가 만든 변경을 에이전트가 다시 검증하는 구조를 만듭니다. 커뮤니티에서도 stdout/stderr 파이핑으로 상호 검증 루프를 스크립팅하는 패턴이 반복됩니다. ([reddit.com](https://www.reddit.com/r/ClaudeCode/comments/1rh0kuo/anyone_else_using_claude_code_codex_together_way/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **AGENTS.md / 규칙 파일을 “테스트 커맨드까지” 포함해 강제**
- 에이전트 실패의 많은 부분이 tool/command 단계에서 발생한다는 연구 결과처럼, “무슨 커맨드를 어떤 순서로”가 생산성을 좌우합니다. ([arxiv.org](https://arxiv.org/abs/2603.20847?utm_source=openai))

2) **작업을 ‘기능’이 아니라 ‘검증 가능한 산출물’로 쪼개기**
- “리팩터링 해줘”가 아니라 “(a) 타입체크 통과 (b) 테스트 통과 (c) diff < N files (d) 마이그레이션 노트 생성”처럼 Definition of Done을 명시해야, 에이전트가 과하게 확장하지 않습니다.

3) **교차 모델 리뷰는 ‘필수 구간’에만 걸기**
- 모든 커밋마다 Claude↔Codex 핑퐁을 하면 비용/시간이 폭발합니다.
- 추천: dependency bump, auth/payment, data migration, CI 변경처럼 **리스크 높은 PR에만** 교차 리뷰를 적용.

### 흔한 함정/안티패턴
- **에이전트에게 “전체 레포를 개선” 같은 무한 과제를 주기**: diff 폭발 + 리뷰 불가 + 롤백 어려움.
- **lockfile을 무조건 재생성**: 실제로는 취약점 패치가 목적이라면 “영향 범위 최소화”가 더 중요합니다.
- **테스트 실패를 ‘AI가 알아서’로 방치**: 실패 로그를 사람이 30초만 읽고 “진짜 원인”을 짚어주면, 에이전트의 재시도 루프를 크게 줄일 수 있습니다(토큰/시간 절약).

### 비용/성능/안정성 트레이드오프
- Claude 쪽은 큰 컨텍스트/긴 작업에서 강점으로 언급되지만, 컨텍스트가 커질수록 “불필요한 파일까지 읽고” 토큰이 늘어나는 역효과가 생깁니다(큰 컨텍스트는 양날의 검). ([zapier.com](https://zapier.com/blog/codex-vs-claude-code/?utm_source=openai))
- Codex는 빠른 편집 루프에 강점으로 회자되지만, 장기 작업에서의 오케스트레이션 표면(중간 확인/명령/서브에이전트) 차이가 체감 포인트가 될 수 있습니다. ([agentsroom.dev](https://agentsroom.dev/blog/claude-code-vs-codex-cli?utm_source=openai))
- 결론적으로 “모델 성능”보다 **wrapper(재시도, 스키마 검증, 권한/가드레일, 프롬프트 캐싱)**가 실패율을 결정한다는 경험담도 많습니다. ([reddit.com](https://www.reddit.com/r/GeminiCLI/comments/1t0raoe/cli_gemini_vs_claude_code_vs_codex/?utm_source=openai))

---

## 🚀 마무리
2026년 7월 기준으로 Claude Code와 Codex CLI는 둘 다 “터미널에서 레포를 읽고, 파일을 고치고, 커맨드를 실행하는” 수준까지는 상향 평준화됐습니다. 차이는 결국 **워크플로 설계**에서 납니다:  
- Claude Code는 로컬 기반 협업형 에이전트로서 “권한/서술/에이전트 구성”이 강점으로 비교되고 ([zapier.com](https://zapier.com/blog/codex-vs-claude-code/?utm_source=openai))  
- Codex CLI는 빠른 실행/리뷰 루프와 OpenAI 생태계 결합에서 장점이 자주 언급됩니다. ([agentsroom.dev](https://agentsroom.dev/blog/claude-code-vs-codex-cli?utm_source=openai))  

도입 판단 기준(내 프로젝트에 적용할지):
1) **반복 작업이 ‘명령+검증’으로 표현 가능한가?** (테스트/린트/타입체크가 있는가)
2) **레포 룰을 문서로 고정할 의지가 있는가?** (AGENTS.md 같은 계약이 없으면 장기적으로 품질이 흔들림)
3) **리스크 높은 구간에 교차 리뷰를 걸 필요가 있는가?** (그렇다면 “Claude로 실행, Codex로 반대 심문”이 투자 대비 효과가 큼) ([arxiv.org](https://arxiv.org/abs/2607.21656?utm_source=openai))

다음 학습 추천:
- Claude Code 공식 CLI/commands 문서(세션 재개, 비대화형 모드, agents 주입)를 먼저 정독하고 ([code.claude.com](https://code.claude.com/docs/en/cli-usage?utm_source=openai))  
- 팀 레포에 “에이전트 계약(AGENTS.md)”을 도입한 뒤, 위 스크립트를 PR 템플릿/CI와 결합해 “고위험 PR만 교차 리뷰”로 운영해보면 시행착오가 가장 적습니다.