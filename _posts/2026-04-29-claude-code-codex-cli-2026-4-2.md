---
title: "Claude Code × Codex CLI 에이전트, 2026년 4월 기준 “터미널 자동화 워크플로”로 써먹는 법"
date: 2026-04-29 03:51:03 +0900
categories: [AI, Coding]
tags: [ai, coding, trend, 2026-04]
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
CLI 기반 AI 코딩 에이전트가 해결하는 문제는 명확합니다. **(1) 레포를 읽고 (2) 명령을 실행하고 (3) 파일을 수정하고 (4) 테스트/린트까지 돌린 뒤 (5) 결과를 요약**하는 반복 루프를 사람이 “컨텍스트 스위칭” 없이 터미널에서 끝내는 겁니다. 2026년엔 이게 단순 코드 생성이 아니라 **workflow automation**(리팩터링→테스트→리포트→PR 초안)으로 확장됐고, Claude Code와 OpenAI Codex CLI는 각각 다른 강점을 갖습니다. ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop))

**언제 쓰면 좋은가**
- CI가 무겁고 로컬에서 재현이 어려운 프로젝트에서, *에이전트가 수행한 작업 로그/결과를 표준 출력(JSON)으로 남기고* 사람이 리뷰하는 형태가 필요한 경우(예: 보안 스캔→수정 제안→테스트 실행). ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage))  
- “툴 호출”이 핵심인 작업(테스트 러너, 린터, git, 내부 API/DB 조회 등)을 **일관된 인터페이스로 연결**해 자동화하고 싶은 경우(특히 MCP 같은 표준을 통해). ([modelcontextprotocol.io](https://modelcontextprotocol.io/docs/learn?utm_source=openai))

**언제 쓰면 안 되는가**
- 레포/인프라 권한이 정리되지 않은 상태에서 “그냥 자동으로 고쳐줘”를 기대하는 경우: 에이전트는 결국 shell/file access를 쓰기 때문에, **권한·가드레일 설계가 없으면 비용/보안 리스크가 먼저 터집니다.** 특히 MCP 생태계는 빠르게 커졌지만, 최근 보안 이슈(구현/서플라이체인 포함)도 같이 보고됩니다. ([tomshardware.com](https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropics-model-context-protocol-has-critical-security-flaw-exposed?utm_source=openai))  
- “정답이 하나인 코딩 문제”가 아니라, 제품/도메인 의사결정이 섞인 작업(예: 이벤트 스키마 재설계, API 계약 변경): 이건 자동화보다 **인간이 먼저 설계를 고정**하고 에이전트는 실행 담당으로 쓰는 편이 낫습니다.

---

## 🔧 핵심 개념
### 1) Agent loop: CLI 에이전트의 진짜 본체
Codex CLI 쪽 문서가 이 부분을 비교적 투명하게 공개합니다. 핵심은 “에이전트”가 마법이 아니라, 아래 루프를 **반복 오케스트레이션**한다는 점입니다.

1. 사용자의 목표를 prompt로 구성  
2. 모델 inference  
3. 모델이 tool call(명령 실행/파일 편집 등)을 요청  
4. 실행 결과(observation)를 다시 모델에 주입  
5. 계획 업데이트 후 반복 → 최종 산출물/요약 반환 ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop))  

이 구조를 이해하면 “왜 가끔 엉뚱한 커맨드를 치는지”, “왜 테스트가 오래 걸리는지”, “왜 작은 수정도 여러 번 왕복하는지”가 설명됩니다. 즉, 성능/비용/안정성 최적화 포인트가 **모델 자체**보다 **loop 설계(툴 제한, 승인 정책, 출력 구조화, 캐시)**에 있습니다.

### 2) Claude Code의 차별점: Permission gating + 플러그인/MCP + 원격 제어
Anthropic의 Claude Code CLI는 단순 대화형 CLI가 아니라, **서브에이전트(agents)**, **plugin**, **MCP 연결(claude mcp)**, 그리고 **remote-control 서버 모드** 같은 “운영 기능”이 눈에 띕니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage))  
특히 “auto mode”는 위험한 툴 호출을 분류/차단하는 쪽으로 설계되어 있고(기본 규칙을 JSON으로 확인 가능), 연구에서도 **권한 게이팅(permission system)**을 중요한 설계 요소로 다룹니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage))  

정리하면:
- Codex CLI는 **agent loop(하네스) 구조 공개 + 비동기 위임 워크플로**에 무게 ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop))  
- Claude Code는 **CLI 운영성(plugins, MCP, remote-control) + 권한 게이팅**에 무게 ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage))  

### 3) MCP(Model Context Protocol): “툴/데이터 연결”을 표준화한 레이어
MCP는 Claude가 제안한 **오픈 표준**로, AI 앱(호스트)이 여러 MCP 서버에 연결해 **Resources/Tools/Prompts**를 표준 형태로 제공받는 클라이언트-서버 구조입니다. 전송은 주로 stdio 또는 HTTP(SSE) 등으로 구성됩니다. ([modelcontextprotocol.io](https://modelcontextprotocol.io/docs/learn?utm_source=openai))  
의미는 간단합니다: “Jira 하나 붙이려고 SDK 만들고, Notion 붙이려고 또 만들고…” 같은 N×M 통합 지옥을 줄입니다.

다만 2026년 4월 기준으로는 MCP 관련 보안 이슈가 연속적으로 보도되고 있어, “표준=안전”으로 착각하면 안 됩니다. **원격 도구 호출/프롬프트 인젝션/서플라이체인** 관점에서 별도 위협 모델링이 필요합니다. ([tomshardware.com](https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropics-model-context-protocol-has-critical-security-flaw-exposed?utm_source=openai))  

---

## 💻 실전 코드
아래는 “현실적인 시나리오”로, **모노레포에서 특정 서비스의 flaky test를 자동으로 줄이고(재현→원인 후보 추출→수정→테스트), 결과를 PR-ready 형태로 요약**하는 워크플로를 CLI에서 굴리는 예시입니다.

전략:
- Codex CLI: *레포 수정/테스트 루프*에 집중(에이전트 루프 강점)
- Claude Code: *MCP로 외부 도구(Jira/DB/내부 API)를 붙이거나*, remote-control로 *비대화형 실행*을 운영에 붙이기

### 0) 전제: 리포지토리 규칙을 “에이전트가 지키게” 만들기
Codex 쪽은 AGENTS.md 같은 규칙 파일을 따르도록 설계되어 있습니다(“테스트 실행”, “커밋 방식” 등). 팀 룰을 여기로 끌어내리면 성공률이 올라갑니다. ([openai.com](https://openai.com/index/introducing-codex/))  

예: `services/payments/AGENTS.md`
```text
- Always run: pnpm -C services/payments test -- --runInBand
- If you change src/, also run: pnpm -C services/payments lint
- Do not touch lockfiles unless explicitly asked.
- Summarize flaky test root cause hypotheses in the PR message.
```

### 1) (Codex CLI) 격리된 작업 공간 + 반복 루프 자동화
실무에선 에이전트가 워크트리를 더럽히는 게 가장 큰 스트레스입니다. 그래서 “격리된 worktree”를 기본값으로 두는 패턴을 추천합니다.

```bash
# 1) 작업용 worktree 생성
git worktree add -b agent/flaky-fix ./wt-agent HEAD
cd ./wt-agent/services/payments

# 2) 에이전트에게 "재현→수정→테스트→요약"을 명시적으로 지시
# (실제 codex cli의 세부 커맨드는 배포판/버전에 따라 다를 수 있으니,
# 설치된 codex cli의 --help에 맞춰 조정하세요)
codex \
  --model codex-mini-latest \
  "CI에서 간헐적으로 실패하는 테스트를 로컬에서 재현해.
   최근 20회 실행 중 실패율이 높은 테스트를 우선순위로 잡고,
   원인 후보를 2~3개로 좁힌 뒤 가장 보수적인 수정으로 안정화해.
   변경 후 아래를 순서대로 실행:
   1) pnpm test -- --runInBand
   2) pnpm lint
   마지막에 변경 요약 + 왜 이 수정이 안전한지 + 남은 리스크를 출력해."
```

**예상 출력(요지)**
- 에이전트가 테스트 실행 로그를 관찰하고(observation)  
- 실패 케이스를 기준으로 코드 수정→재실행  
- 마지막에 요약(변경 파일, 재현 커맨드, 리스크) 형태로 정리  
이 흐름 자체가 Codex가 설명한 agent loop 구조입니다. ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop))  

> 포인트: “무엇을 실행할지”를 구체 커맨드로 박아넣으면, loop가 헤매는 시간이 줄고 토큰/시간이 절약됩니다.

### 2) (Claude Code) MCP 서버 연결로 “조사/증거 수집” 자동화
수정 자체보다, **근거 수집(최근 배포, 에러율, 관련 티켓, DB 상태)**가 실무에선 더 중요합니다. Claude Code는 `claude mcp`로 MCP 서버를 붙여 외부 컨텍스트를 도구로 제공합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage))  

```bash
# 예시: GitHub MCP 서버를 stdio로 연결 (실제 서버/이름은 조직 환경에 맞게)
claude mcp add --transport stdio github -- npx -y @modelcontextprotocol/server-github
```

이후 Claude Code 세션에서:
- “지난 7일간 payments 서비스 관련 PR 중 테스트 flake 언급된 것만 요약”
- “해당 테스트가 건드리는 테이블의 최근 schema 변경 확인”
같은 작업을 “툴 호출”로 처리하게 만들 수 있습니다(MCP의 목적이 여기). ([modelcontextprotocol.io](https://modelcontextprotocol.io/docs/learn?utm_source=openai))  

### 3) (Claude Code) 비대화형 실행: remote-control + CI/크론 연결
Claude Code CLI에는 `claude remote-control` 서버 모드가 있어 “로컬 인터랙션 없이” 제어하는 방향을 지원합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage))  
예를 들어 야간에 레포 상태를 스캔하고(린트/테스트/의존성 취약점), 아침에 요약 리포트를 만들게 하는 식으로 붙일 수 있습니다. (여기서 핵심은 **승인 정책/권한 제한/격리 환경**입니다.)

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “승인(Approval) 정책”을 설계하지 않으면 운영이 불가능해진다
- 파일 쓰기, 네트워크 접근, 패키지 설치, credential 접근을 **행동 단위로 분리**하고 기본은 deny로 두세요.
- Claude Code는 auto mode/권한 게이팅이 중요한 축이고, 연구에서도 false negative가 존재합니다(즉, “자동이니까 안전”이 아님). ([arxiv.org](https://arxiv.org/abs/2604.04978?utm_source=openai))  

### Best Practice 2) 결과물은 항상 “diff + 재현 커맨드 + 로그 요약” 3종 세트로 남겨라
에이전트가 만든 코드를 믿는 게 아니라, **리뷰 가능한 산출물**을 믿는 구조로 가야 합니다. Codex 쪽도 “테스트를 반복 실행해 통과” 같은 루프를 전제로 설계합니다. ([openai.com](https://openai.com/index/introducing-codex/))  

### Best Practice 3) MCP는 “편의성”이 아니라 “공격면 확대”로 먼저 본다
최근 MCP 관련 RCE/서플라이체인/프롬프트 인젝션 류 이슈가 보도되었습니다. 특히 “공식/비공식 MCP 서버”를 손쉽게 붙이는 순간, 에이전트의 tool surface가 폭증합니다. ([tomshardware.com](https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropics-model-context-protocol-has-critical-security-flaw-exposed?utm_source=openai))  
- 가능한 한 **로컬 stdio + allowlist**로 시작  
- remote MCP는 별도 네트워크 세그먼트/토큰 스코프 분리  
- “읽기 전용” 리소스와 “쓰기 가능” 툴을 물리적으로 분리(서버 자체 분리 권장)

### 흔한 함정/안티패턴
- **“한 번에 큰 지시”**: 에이전트 루프가 길어질수록 비용과 실패 확률이 커집니다. “조사 단계”와 “수정 단계”를 나누고, 중간 산출물을 사람이 승인하세요.
- **워크스페이스 오염**: worktree/브랜치 격리 없이 돌리면, 에이전트가 생성한 파일/수정이 섞여 디버깅 비용이 폭발합니다.
- **모델 선택을 감으로**: codex-mini-latest 같은 저지연 모델은 편집/QA에 유리하지만, 복잡한 리팩터링/보안 분석은 더 강한 모델이 필요할 수 있습니다(=시간/비용 증가). Codex는 모델/제품군이 확장되는 추세라, 작업 타입별로 프로파일링이 필요합니다. ([openai.com](https://openai.com/index/introducing-codex/))  

---

## 🚀 마무리
2026년 4월 기준으로 “Claude Code vs Codex CLI”를 도구 비교로 보면 결론이 흐립니다. 대신 **내 워크플로에 어떤 ‘루프’를 자동화할 건지**로 쪼개면 판단이 쉬워집니다.

- **레포 수정→테스트 반복→요약** 같은 *코어 코딩 루프*는 Codex가 공개한 agent loop 관점으로 튜닝 포인트가 명확합니다. ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop))  
- **운영(plugins/MCP/remote-control) + 권한 게이팅**을 기반으로 “조사/증거수집/외부도구 연동”까지 확장하려면 Claude Code의 CLI 기능들이 유효합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage))  
- 다만 MCP/에이전트 생태계는 보안 이슈도 동반 성장 중이라, “연결성”을 늘릴수록 **권한 설계·격리·감사로그**를 먼저 투자해야 합니다. ([tomshardware.com](https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropics-model-context-protocol-has-critical-security-flaw-exposed?utm_source=openai))  

**도입 판단 기준(체크리스트)**
1) 에이전트가 실행할 커맨드/권한을 allowlist로 정의할 수 있는가?  
2) 산출물을 diff+재현커맨드+로그로 리뷰하는 프로세스가 있는가?  
3) MCP/플러그인으로 외부 시스템을 붙일 때 토큰 스코프/네트워크 격리가 가능한가?  

다음 학습은 (1) Codex의 agent loop 글을 기준으로 “툴 호출-관찰-계획 업데이트”를 로그로 추적하는 습관을 들이고, ([openai.com](https://openai.com/index/unrolling-the-codex-agent-loop)) (2) Claude Code의 `claude mcp`, `claude remote-control`, auto mode 규칙 JSON을 실제로 열어보며 “내 조직의 정책”으로 치환하는 것을 추천합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-usage))