---
title: "Claude Code × Codex CLI 에이전트: 2026년 7월 기준 “터미널 자동화 워크플로”로 진짜 생산성 뽑는 법"
date: 2026-07-14 03:14:52 +0900
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
CLI 기반 AI 코딩 에이전트가 해결하는 문제는 명확합니다. **(1) 레포 탐색/이해 → (2) 수정 → (3) 테스트/실행 → (4) PR 품질 체크**를 사람 손으로 왕복하던 루프를, 터미널에서 “도구 호출(tool-call) + 권한 승인(approval) + 세션 지속(session)”으로 묶어 **반복 비용을 낮추는 것**입니다.

**언제 쓰면 좋은가**
- 변경 범위가 “파일 여러 개 + 테스트/빌드/린트”까지 걸리는 **중간 규모 작업**(버그 수정, 리팩터링, 마이그레이션)
- 팀 규칙(커밋 메시지, CI 규칙, 린트 규칙)이 확고해서 에이전트의 산출물을 **자동 검증**하기 쉬울 때
- 사람이 하기엔 귀찮은 **반복 작업**(로그 분석, 실패한 테스트 원인 추적, 릴리즈 노트 초안 등)

**언제 쓰면 안 되는가**
- 요구사항이 불명확하거나, “어떤 아키텍처가 맞는지”를 먼저 정해야 하는 **탐색 단계**(에이전트가 코드를 너무 빨리 고쳐서 오히려 방향을 흐림)
- 레포/조직 보안 정책상 **로컬 파일 접근/명령 실행** 자체가 민감한 환경(권한 모델/감사 로깅 준비 없으면 위험)
- “한 줄 바꾸면 끝” 수준의 작업(사람이 더 빠름)

2026년 7월 시점에서 실무적으로 중요한 포인트는, Claude Code 쪽은 **MCP(Model Context Protocol)와 권한/도구 제어 플래그**가 자동화에 유리하고, Codex CLI는 **로컬에서 동작하는 경량 에이전트 + 승인 워크플로**로 빠르게 굴릴 수 있다는 점입니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))

---

## 🔧 핵심 개념
### 1) “CLI 에이전트”의 본질: REPL이 아니라 **에이전트 루프**
Claude Code CLI는 `claude`를 REPL로 시작할 수도 있지만, 자동화 관점에서 핵심은 **print 모드(-p) + 구조화 출력(JSON/stream-json)** 입니다. 즉, “자연어 → (필요시) 파일 읽기/편집/쉘 실행 → 응답”의 루프를 **스크립트가 다시 감쌀 수 있는 형태**로 꺼내주는 게 포인트입니다. `--output-format json`, `--max-turns` 같은 플래그가 이 목적에 맞습니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))

Codex CLI도 비슷하게 “터미널에서 코드를 읽고/수정하고/실행하는 에이전트”를 지향하며, 설치와 시작이 가벼운 편입니다. ([help.openai.com](https://help.openai.com/en/articles/11096431?utm_source=openai))

### 2) 안전장치의 차이: **권한 승인(approval) = 자동화의 브레이크**
자동화에서 가장 자주 실패하는 지점이 “에이전트가 파일 삭제/대량 수정/위험한 명령 실행”을 해버리는 경우입니다. Claude Code는 권한 프롬프트를 스킵하는 `--dangerously-skip-permissions`를 제공하지만, 이름 그대로 **자동화 파이프라인에 기본값으로 넣으면 사고 확률이 급증**합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))  
대신 “허용 도구 allowlist” 중심으로, 예를 들어 `git diff`, `pnpm test` 같은 *읽기/검증 위주*만 무프롬프트로 열어두고, 쓰기/실행은 단계적으로 승인하게 설계하는 게 현실적입니다(`--allowedTools`, `--disallowedTools`). ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))

Codex CLI 역시 “승인 워크플로(Approval modes)”를 전면에 두고 있어, 완전 무인화보다는 **인간-인더-루프**를 기본 철학으로 둡니다. ([help.openai.com](https://help.openai.com/en/articles/11096431?utm_source=openai))

### 3) MCP로 “에이전트의 손발”을 붙인다
Claude Code CLI에는 `claude mcp`가 있고, 이는 외부 도구/서비스를 **표준 프로토콜로 붙이는 확장 지점**입니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))  
이게 실무에서 의미 있는 이유는:
- GitHub/이슈 트래커/사내 API 등을 “프롬프트로 복붙”하지 않고
- **구조화된 tool-call**로 접근하게 만들 수 있어서,
- 로그/아티팩트/결과물을 자동으로 모으는 워크플로를 만들기 쉽습니다.

### 4) “두 에이전트 조합”이 뜨는 이유: Plan vs Execute 분리
2026년 들어 업계에서 자주 보이는 패턴은:
- Claude Code: 계획/리뷰/리팩터링 방향(설명력, 맥락 유지)
- Codex CLI: 실제 파일 수정/테스트 반복(그라인딩, 빠른 반복)

즉 **Planner/Executor 분리**입니다. 이 조합 자체를 다루는 비공식 글/논의도 보이지만, 검증은 본인 팀의 코드베이스/테스트 환경에서 해봐야 합니다(레포 규모/언어/테스트 속도에 따라 체감이 달라짐). ([codex.danielvaughan.com](https://codex.danielvaughan.com/2026/04/18/codex-cli-claude-code-working-together/?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “현실적인 시나리오”로, **Node/TypeScript 모노레포**에서 특정 서비스의 장애(메모리 누수 의심)를 수정한다고 가정합니다.

목표:
1) Claude Code로 “문제 원인 후보 + 수정 전략 + 변경 파일 리스트 + 검증 커맨드”를 **JSON으로 뽑기**
2) 그 JSON을 기반으로 Codex CLI가 실제 수정을 수행(여기서는 `codex` 바이너리가 있다고 가정)
3) 마지막에 Claude Code가 `git diff`와 테스트 로그를 입력으로 받아 **PR 설명/리스크**를 정리

### 0) 사전 준비
- Claude Code 설치(예: npm 글로벌 설치) ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/getting-started?utm_source=openai))
- Claude Code는 `--output-format json` 지원 ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))
- Codex CLI는 `npm install -g @openai/codex`로 설치하는 흐름(문서 기준) ([help.openai.com](https://help.openai.com/en/articles/11096431?utm_source=openai))

### 1) “계획 생성”을 Claude Code로 구조화 출력하기 (bash)
```bash
#!/usr/bin/env bash
set -euo pipefail

# 1) 장애 상황/관찰 로그(예: 최근 OOM)와 레포 컨텍스트를 함께 넣고,
# 2) Claude Code가 "수정 계획"을 JSON으로 내보내게 만든다.
PLAN_JSON=$(
  claude -p --output-format json --max-turns 2 \
'You are a senior backend engineer.
Repo: Node.js + TypeScript, pnpm, services/api.
Problem: production pods OOM after 2-3h. Heap snapshots suggest unbounded cache growth.
Task:
- Identify likely root cause in services/api
- Propose minimal-risk patch
- Provide exact commands to verify (unit + integration)
Return STRICT JSON with keys:
- suspected_causes: string[]
- files_to_check: string[]
- patch_plan: string[]
- verify_commands: string[]
- rollback_notes: string[]'
)

echo "$PLAN_JSON" | jq .
echo "$PLAN_JSON" > .ai/plan.json
```

예상 출력(요지):
- `files_to_check`: `services/api/src/cache/*`, `services/api/src/middlewares/*` 등
- `verify_commands`: `pnpm -C services/api test`, `pnpm -C services/api lint`, 특정 재현 스크립트 등

### 2) Codex CLI로 “실제 수정 + 테스트 반복” (bash)
```bash
#!/usr/bin/env bash
set -euo pipefail

PLAN="$(cat .ai/plan.json)"

# Codex에게는 "무엇을 어떻게 바꿀지"를 구체적으로 주고,
# 결과물로는 반드시 테스트/린트 통과 증거를 남기게 한다.
codex <<EOF
You are an execution-focused coding agent.
Read this JSON plan and implement the patch.
Constraints:
- Keep changes minimal.
- Add/adjust tests if needed.
- Run verify commands and paste summaries.
Plan JSON:
$PLAN

When done:
- show git diff summary
- show test command outputs (short)
EOF
```

여기서 중요한 운영 팁:
- Codex가 “실행 결과”를 텍스트로만 남기면 CI에서 재현이 어려우니, **출력 로그를 파일로 저장**하도록 유도하는 게 좋습니다(예: `tee .ai/test.log`).

### 3) Claude Code로 PR 품질 체크(리뷰어 모드) (bash)
```bash
#!/usr/bin/env bash
set -euo pipefail

DIFF="$(git diff)"
TEST_LOG="$(test -f .ai/test.log && cat .ai/test.log || echo 'NO_TEST_LOG')"

claude -p --output-format text --max-turns 2 <<EOF
Act as a strict code reviewer.
Inputs:
- git diff:
$DIFF

- test log:
$TEST_LOG

Deliver:
1) PR description (problem, root cause, fix)
2) Risk assessment (what could break)
3) Rollback plan
4) Suggested follow-ups (metrics/alerts)
EOF
```

이 3단계가 돌아가면, “계획 → 수정 → 검증/PR정리”가 **터미널 자동화 파이프라인**으로 고정됩니다. 핵심은 Claude Code의 `--output-format json` 같은 *기계 친화 출력*이 오케스트레이션에 실질적인 도움을 준다는 점입니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3가지)
1) **JSON을 계약(Contract)으로 써라**
- 1단계에서 Claude가 내는 산출물을 “사람이 읽기 좋은 글”로 받으면, 2단계 실행 에이전트가 흔들립니다.  
- `files_to_check`, `verify_commands` 같은 키를 고정해서 **에이전트 간 handoff를 데이터로** 하세요. Claude Code는 print 모드에서 JSON 출력을 지원합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))

2) **allowlist 중심으로 권한을 설계**
- 자동화에서 가장 위험한 건 “편의상 권한 스킵”입니다. `--dangerously-skip-permissions`는 정말 마지막 수단이고, 보통은 `--allowedTools`로 읽기/검증 계열만 열어두는 식이 안전합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))

3) **검증 커맨드를 ‘빠른 것→느린 것’ 순으로 계층화**
- 예: `lint → unit → integration → e2e`  
- 에이전트는 종종 느린 테스트부터 돌리며 시간을 날립니다. `verify_commands`를 계층화해서 “먼저 실패를 빨리 발견”하게 만드세요.

### 흔한 함정/안티패턴
- **세션 컨텍스트를 프롬프트에 매번 풀로 재주입**: 토큰/비용 증가 + 잡음 누적. 대신 “변경점(diff) + 테스트 로그 + 목표”처럼 *증거 기반 입력*으로 줄이세요.
- **에이전트에게 ‘리팩터링도 하고 기능도 추가하고…’를 한 번에 시킴**: diff가 커지면 리뷰/롤백 비용이 폭증합니다. “버그 패치”와 “개선”을 분리하세요.
- **승인 워크플로를 무시한 무인화**: CLI 에이전트는 로컬 파일/쉘에 손이 닿는 순간부터 위험도가 올라갑니다. 승인/로그/아티팩트 저장이 없으면 운영 불가입니다.

### 비용/성능/안정성 트레이드오프
- **성능(속도)**: `--max-turns`로 루프를 제한하면 비용/시간을 잡을 수 있지만, 복잡한 작업은 중간에 끊겨 “애매한 반쪽 수정”이 나올 수 있습니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))  
- **안정성**: 승인을 촘촘히 두면 안전하지만 느려집니다. 실무에서는 “CI에서 자동 검증 가능한 작업(린트/테스트)”은 더 자동화하고, “파일 삭제/대규모 리네임” 같은 작업은 사람 승인으로 남기는 하이브리드가 현실적입니다.
- **보안**: Codex CLI는 로컬에서 동작하는 CLI 에이전트임을 강조합니다(소스가 외부로 나가지 않도록 통제 가능하다는 주장). 다만 실제로는 모델 호출/인증/전송 경로가 있으니, 조직 정책에 맞춰 네트워크/로그/레드액션을 점검해야 합니다. ([help.openai.com](https://help.openai.com/en/articles/11096431?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 7월 기준 “Claude Code × Codex CLI”를 실무에 적용하는 가장 강력한 방식은 **단일 에이전트 만능주의가 아니라, 터미널 파이프라인에서 역할을 분리**하는 것입니다.

도입 판단 기준:
- 레포에 **테스트/린트/CI가 제대로** 갖춰져 있나? (에이전트 산출물을 자동 검증할 수 있어야 함)
- “승인/권한/로그/아티팩트”를 남기는 **운영 설계**가 가능한가? (가능하면 도입 가치 높음)
- 반복 작업이 많고, 사람이 컨텍스트 스위칭으로 시간을 버리고 있나? (그렇다면 효과가 큼)

다음 학습 추천:
- Claude Code의 CLI 플래그(특히 print 모드, JSON/stream-json, allowedTools/disallowedTools)를 기준으로 **자기 조직의 ‘안전한 자동화 프로파일’**을 먼저 정의하세요. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))  
- 이후 MCP 확장(사내 시스템 연결)을 붙여 “프롬프트 복붙”을 제거하면, CLI 에이전트가 단순 코딩 도우미를 넘어 **워크플로 자동화 엔진**으로 올라갑니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage?utm_source=openai))

원하시면, 사용 중인 스택(언어/테스트 러너/CI, 모노레포 여부, 배포 방식)에 맞춰 위 3단계 스크립트를 “그대로 복사해 돌아가는” 형태로 커스터마이즈해 드릴게요.