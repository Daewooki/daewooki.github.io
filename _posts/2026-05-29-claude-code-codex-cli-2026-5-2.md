---
title: "Claude Code × Codex CLI 에이전트로 “터미널에서 끝내는” 자동화 워크플로 (2026년 5월판)"
date: 2026-05-29 04:21:11 +0900
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
2026년 5월 시점의 CLI 기반 AI 코딩 에이전트는 더 이상 “코드 몇 줄 생성”이 아니라, **리포지토리 안에서 계획→실행→검증(테스트/린트/빌드)→PR용 산출물 생성**까지 묶어서 처리하는 자동화 장치에 가깝습니다. 특히 Claude Code와 OpenAI Codex CLI는 각각 **로컬 터미널/프로젝트 컨텍스트에 밀착된 실행형 에이전트**라는 공통점을 가지되, 안전장치/확장성/운영 방식에서 결이 다릅니다. (OpenAI는 Codex CLI를 포함한 “Codex agent loop” 구조를 공식적으로 풀어 설명했고, 데스크톱 앱/CLI/IDE/클라우드로 경험을 확장 중입니다. ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop/)))

### 이 기술이 해결하는 “구체적 문제”
- PR 리뷰 전에 반복되는 작업(변경 영향 분석, 회귀 테스트, 린트/타입체크, changelog, 릴리즈 노트 초안)을 사람이 매번 수동으로 처리
- CI에서 실패한 로그를 읽고 “원인→재현→수정→재검증” 루프를 짧게 만들기 어려움
- 팀마다 로컬 환경/에이전트 설정이 달라져 결과 재현성이 낮고, hooks/MCP/plugins가 섞이며 예측 불가능해짐(특히 CI에서)

### 언제 쓰면 좋고 / 안 쓰면 좋은가
**좋음**
- “변경 범위가 명확한” 작업: 린트/타입 오류 해결, 특정 모듈 리팩터링, 테스트 추가, 문서/README 정리, 릴리즈 노트 생성
- CI 파이프라인에서 **에이전트를 ‘단발성 함수’처럼** 호출할 때(입력=로그/리포트, 출력=구조화된 진단/패치 제안)

**안 좋음**
- 요구사항이 계속 변하는 초기 기획 단계에서 “자동 커밋/자동 수정”을 과하게 켜는 것(결과가 흔들릴 때 비용만 증가)
- 보안/권한 모델을 이해하지 않고 repo hooks/MCP/plugins를 그대로 신뢰하는 운영(최근 컨텍스트/설정 기반 공격 논의가 많습니다. ([labs.cloudsecurityalliance.org](https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/05/CSA_research_note_SKILL_md_agent_context_poisoning_20260506-csa-styled-1.pdf?utm_source=openai)))

---

## 🔧 핵심 개념
### 1) CLI 에이전트의 기본 구성요소: Agent loop + Tools + Context
OpenAI가 Codex CLI의 핵심으로 명시하는 건 **agent loop**입니다. 요지는 “(1) 사용자 지시를 prompt로 구성 → (2) 모델 inference → (3) 모델이 tool 호출 → (4) tool 결과 관찰 → (5) 계획 갱신 → (6) 종료 또는 반복”의 폐루프 구조입니다. ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop/))  
이 구조가 중요한 이유는, CLI 에이전트의 성능이 “모델 지능”만이 아니라 **도구 설계(무슨 tool을 어떤 제약으로 제공하느냐), 실행 결과 관측(로그/exit code), 컨텍스트 적재(어떤 파일/규칙을 자동 로드하느냐)**에 크게 좌우되기 때문입니다.

### 2) Claude Code의 ‘스크립트/CI 친화’ 포인트: `-p` + `--bare` + tool allowlist
Claude Code는 non-interactive 실행을 **`claude -p`**로 제공하고, 여기서 실무적으로 가장 중요한 옵션이 **`--bare`**입니다. `--bare`는 hooks/skills/plugins/MCP servers/auto memory/CLAUDE.md 등의 자동 로딩을 건너뛰어 **재현성 있는 CI 실행**에 유리합니다. ([code.claude.com](https://code.claude.com/docs/en/headless))  
또한 `--allowedTools "Read,Edit,Bash"`처럼 allowlist로 **권한 범위를 좁힌 상태에서 자동 승인**을 걸 수 있어, “CI에서 멈춰 서는 에이전트”를 줄이는 쪽으로 설계되어 있습니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

추가로 Claude Code CLI 레퍼런스에는 background session/daemon, `ultrareview` 같은 비대화형 리뷰 작업, `setup-token`(스크립트/CI용 장기 토큰) 등 **운영 기능**이 꽤 두껍게 잡혀 있습니다. ([docs.claude.com](https://docs.claude.com/en/docs/claude-code/cli-reference))

### 3) Codex 쪽 흐름: CLI에서 시작해 “멀티 에이전트 운영”으로 확장
OpenAI는 데스크톱 Codex app을 “agents command center”로 포지셔닝하면서, 여러 에이전트를 병렬로 돌리고(worktrees 포함) diff를 감독하는 흐름을 강조합니다. 그리고 이 경험은 CLI 설정/히스토리와 연동됩니다. ([openai.com](https://openai.com/index/introducing-the-codex-app/))  
즉 실무 관점에서 Codex는 “터미널 단발 호출”뿐 아니라 **여러 작업을 에이전트 스레드로 장기 운영**하는 방향으로 제품군을 확장하고 있고, 이때 근본 코어는 앞서 말한 agent loop/harness입니다. ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop/))

### 4) 다른 접근과의 차이점(왜 CLI 에이전트가 따로 필요한가)
- IDE 내 Copilot류: 타이핑/리팩터링 보조가 강하지만, “빌드/테스트/로그 해석/커밋/PR 산출물”은 사용자가 직접 엮어야 함
- Chat UI: 컨텍스트가 끊기기 쉽고, 실제 repo state와 실행 결과(빌드 로그/exit code) 관측이 빈약
- CLI 에이전트: **실제 명령 실행(Bash), 파일 편집, git diff 관찰**을 루프로 묶어 “변경→검증” 자동화를 만들기 쉬움

---

## 💻 실전 코드
아래는 “실제 팀에서 바로 써먹는” 시나리오: **CI에서 실패한 테스트 로그를 Claude Code로 분석 → 최소 수정 패치 생성 → 로컬에서 재검증 → 결과를 PR 코멘트용 JSON으로 저장** 입니다. 핵심은 **`--bare`로 재현성 확보** + **tool allowlist로 권한 최소화** + **구조화 출력으로 파이프라인 연결**입니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

### 0) 사전 준비
- Claude Code 설치/로그인(환경마다 다르므로 생략)
- CI/로컬에서 다음 환경변수 필요:
  - `ANTHROPIC_API_KEY` (또는 `--settings`의 apiKeyHelper) ([code.claude.com](https://code.claude.com/docs/en/headless))
- 리포지토리 루트에서 실행

### 1) 실패 로그를 에이전트에 “입력 데이터”로 넣기 (파이프)
```bash
# 1) CI에서 저장된 실패 로그(예: jest/pytest/go test 등)를 Claude로 분석
cat ./artifacts/test-failure.log | claude --bare -p \
"당신은 시니어 빌드/테스트 엔지니어입니다.
아래 로그를 근거로:
1) root cause를 한 문단으로 요약
2) 재현 가능한 최소 원인 가설 2개
3) 코드베이스에서 확인해야 할 파일/함수 후보를 우선순위로 5개
를 한국어로 작성하세요." \
--allowedTools "Read" \
--output-format text > ./artifacts/triage.txt
```

- 포인트: **`--bare`**로 로컬 hooks/MCP/plugins/CLAUDE.md에 흔들리지 않게 고정합니다. ([code.claude.com](https://code.claude.com/docs/en/headless))  
- 또한 stdin 파이핑은 지원되지만 크기 제한이 있으니(문서에 cap 언급) 로그는 artifacts로 남기는 습관이 좋습니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

### 2) “패치 생성” 단계: 테스트를 직접 돌리게 하지 말고, 수정 범위를 좁혀 커밋 가능한 diff 만들기
여기서부터는 Read+Edit까지 허용하고, Bash는 **테스트 커맨드만** 허용하는 식으로 단계적으로 여는 게 안전합니다.

```bash
# 2) 실패 원인을 잡기 위한 최소 패치 제안 + 실제 코드 수정(파일 편집)
#    (CI에서는 실제 편집만 하고, 테스트 실행은 별도 job으로 분리하는 것을 권장)
claude --bare -p \
"다음 목표를 수행하세요:
- ./artifacts/triage.txt 내용을 참고해, 실패 원인을 유발하는 코드 위치를 찾아 수정하세요.
- 변경은 '최소 수정' 원칙. 관련 테스트도 필요하면 1개만 추가/수정.
- 수정 후, 변경 이유를 주석이 아니라 커밋 메시지/PR 설명에 쓸 수 있게 요약해 주세요.

제약:
- package 추가 금지
- public API 시그니처 변경 금지
- 파일 편집은 필요한 파일만

출력:
1) 어떤 파일을 왜 바꿨는지 bullet로 설명
2) 마지막에 'NEXT: run <command>' 형태로 추천 테스트 커맨드 1개 제시" \
--allowedTools "Read,Edit" \
--output-format text
```

### 3) 로컬/CI에서 재검증 + PR 코멘트용 JSON 만들기
Claude Code는 `--output-format json`을 지원해서, 파이프라인에서 “에이전트 호출 비용/결과”를 추적하기 좋습니다(문서에 비용 필드가 언급됩니다). ([code.claude.com](https://code.claude.com/docs/en/headless))

```bash
# 3) 추천 테스트 실행(여긴 사람이/CI가 수행)
# 예: npm test / pytest / go test 등
npm test

# 4) 변경 diff를 PR 코멘트로 요약(JSON)
git diff | claude --bare -p \
"아래 diff를 PR 코멘트로 바로 붙일 수 있게 정리하세요.
필수:
- 무엇을 고쳤는지(1~2문장)
- 리스크/영향 범위
- 테스트/검증 방법
- 롤백 전략(간단히)
JSON으로 출력하고, 키는 summary, risks, verification, rollback 로 고정" \
--allowedTools "Read" \
--output-format json > ./artifacts/pr_comment.json
```

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3가지)
1) **CI/스크립트는 무조건 `--bare` 기본값으로 깔기**  
로컬 개발자마다 hooks/MCP/plugins/auto memory/CLAUDE.md가 섞이면 같은 로그를 넣어도 결과가 달라집니다. `--bare`는 이 자동 로딩을 끊어 재현성을 확보합니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

2) **권한은 “단계적으로 개방” (Read → Edit → Bash)**  
처음부터 Bash까지 열면 에이전트가 ‘편한 길’을 택하면서 비용이 폭발하거나(불필요한 전체 테스트 반복), 예기치 않은 side-effect가 생깁니다. triage는 Read-only로 끝내고, 패치 단계에서만 Edit을 허용하세요. ([code.claude.com](https://code.claude.com/docs/en/headless))

3) **출력은 사람이 읽는 text + 파이프라인용 json을 분리**  
사람 검토용은 text가 좋고, PR 자동 코멘트/메트릭/비용 추적은 JSON이 낫습니다. Claude Code는 `--output-format json`을 공식 지원합니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

### 흔한 함정/안티패턴
- **에이전트가 “프로젝트 신뢰 상태”를 path 단위로 기억**하는 유형의 설계에서, repo에 설정 파일이 슬쩍 바뀌면 다음 실행 때 위험해질 수 있습니다. hooks/MCP/plugins 같은 “실행 가능한 설정”을 CI에서 그대로 신뢰하지 말고, `--bare` 또는 별도 검증 단계를 두는 게 안전합니다. ([labs.cloudsecurityalliance.org](https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/05/CSA_research_note_SKILL_md_agent_context_poisoning_20260506-csa-styled-1.pdf?utm_source=openai))
- **“자동 커밋”을 너무 일찍 도입**: 에이전트가 커밋까지 만들게 하면 편하지만, 팀 규칙(커밋 메시지, 변경 단위, 리스크 설명)이 흐려져 리뷰 비용이 증가할 수 있습니다. 커밋은 최소한 “사람 승인 단계”를 남기는 편이 낫습니다.
- **장기 세션/백그라운드 기능을 운영하면서 로그/상태 관리 없이 방치**: Claude Code는 background session/daemon/로그 조회 같은 운영 커맨드가 있으니, 장기 작업을 돌릴수록 “세션 관리”를 프로세스로 편입해야 합니다. ([docs.claude.com](https://docs.claude.com/en/docs/claude-code/cli-reference))

### 비용/성능/안정성 트레이드오프
- 안정성(재현성) ↑ : `--bare`, tool allowlist 최소화, 입력/출력 구조화  
- 자동화 수준 ↑ : Bash/플러그인/MCP/훅을 적극 활용  
- 하지만 자동화 수준을 올릴수록 **보안 표면적**과 **실행 변동성**, 그리고 **토큰/시간 비용**이 같이 올라갑니다. “CI는 결정론적으로, 로컬은 생산성 중심”처럼 환경별 정책을 나누는 게 현실적입니다.

---

## 🚀 마무리
2026년 5월 기준으로 Claude Code와 Codex CLI는 “터미널에서 돌아가는 코딩 도우미”를 넘어, **agent loop + tool 실행 + 컨텍스트 로딩 전략**으로 자동화 워크플로의 일부가 되었습니다. Codex는 agent loop/harness를 전면에 두고 멀티 에이전트 운영까지 확장하는 흐름을 공식적으로 강조하고, ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop/)) Claude Code는 `-p`/`--bare`/allowlist/구조화 출력으로 **스크립트·CI 친화적인 호출 방식**을 명확히 제공합니다. ([code.claude.com](https://code.claude.com/docs/en/headless))

### 도입 판단 기준(실무 체크리스트)
- 우리 팀에 **반복되는 “진단→패치→검증” 루프**가 많나? (있으면 ROI 높음)
- CI에서 **재현성 있는 실행 모드(`--bare`)**로 운영할 준비가 되었나? ([code.claude.com](https://code.claude.com/docs/en/headless))
- hooks/MCP/plugins 같은 확장 기능을 쓸 경우, **보안/신뢰 모델**을 문서화하고 코드리뷰 대상으로 넣을 수 있나? ([labs.cloudsecurityalliance.org](https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/05/CSA_research_note_SKILL_md_agent_context_poisoning_20260506-csa-styled-1.pdf?utm_source=openai))

### 다음 학습 추천
- Codex의 agent loop/harness 설계 글을 읽고(“왜 이런 루프/관측/도구 경계가 필요한지”) 우리 팀의 CI 단계에 맞춰 “단발 함수형 호출”로 쪼개기 ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop/))
- Claude Code는 headless 문서의 `--bare`, `--allowedTools`, `--output-format` 조합을 템플릿화해서 **GitHub Actions/Buildkite 같은 파이프라인에 표준 스텝**으로 박아넣기 ([code.claude.com](https://code.claude.com/docs/en/headless))

원하면, 사용 중인 스택(언어/테스트 러너/CI/모노레포 여부) 알려주시면 위 예제를 “당장 붙여 넣어 동작하는” 형태로(예: GitHub Actions workflow YAML + 에이전트 프롬프트 템플릿 + PR 코멘트 자동화)로 구체화해 드릴게요.