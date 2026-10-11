---
title: "VS Code 1.140의 에이전트 워크플로 표준화"
description: "Copilot harness·멀티 폴더 세션·엔터프라이즈 AI 정책을 개발자 도구가 아닌 팀 운영 정책 관점에서 해석합니다."
date: 2026-10-11 14:04:19 +0900
categories: ["Tools", "VS Code"]
tags: ["vscode", "copilot-harness", "agent-host", "worktree", "enterprise-policy", "mcp"]
render_with_liquid: false
---

VS Code 1.140(Stable, 2026-09-30)은 릴리스 하이라이트에서 Copilot harness, Multi-folder sessions(Experimental), Shared worktree folders(Experimental), Enterprise controls를 한 묶음으로 전면에 배치했습니다.[^1]

이 조합이 의미하는 변화는 기능 추가가 아니라 책임 소재의 이동입니다. 예전에는 IDE가 개인 생산성의 영역이었고, 조직은 대체로 extension allowlist·telemetry·업데이트 채널 같은 간접 통제만 걸었습니다. 이제는 에이전트 실행이 별도 프로세스(Agent Host)로 분리되고, 세션이 창/표면을 넘나들며, 하나의 세션이 여러 폴더/여러 worktree를 동시에 다룹니다. 이 상태에서 “개발자가 버튼 눌러 쓰는 도구”로만 취급하면 통제가 불가능해집니다. 운영 정책으로 다뤄야 하는 이유가 거기에 있습니다.

내 기준에서 이번 전환점은 세 가지 질문을 강제로 팀에 던집니다.

- 에이전트가 실행되는 **환경을 재현 가능하게** 만들 것인가(Dev Container, remote host, sandbox, tool approvals).
- 에이전트가 수정하는 저장소 상태를 **재사용 가능한 단위**로 만들 것인가(worktree 전략, shared ignored folders).
- 조직이 AI를 **허용/차단/로깅**할 때 어디까지를 중앙에서 강제하고, 어디부터를 개발자 선택으로 남길 것인가(device policy vs Copilot enterprise-managed settings vs GitHub org/enterprise settings).

이 글은 VS Code 내부 구현을 뜯는 대신, 팀 운영 정책으로 바로 연결되는 설계 포인트를 중심으로 정리합니다.

## Agent Host와 AHP: “세션”이 IDE UI에서 분리될 때 생기는 운영 경계

VS Code는 2026-08-26에 Agent Host를 소개하면서, 장기 실행되는 에이전트 세션을 “창(윈도우)과 extension host에 묶어두는 구조” 자체가 한계라고 명시했습니다. Copilot harness를 GitHub Copilot SDK 기반으로 통일하려는 목표와, 창을 닫아도 계속 돌아가는 세션을 만들려는 목표가 합쳐지면서, 세션 상태/기본 도구/워크스페이스 능력을 별도 프로세스로 떼어냈다는 설명입니다.[^2]

핵심은 세 가지입니다.

1) **세션이 창에 귀속되지 않는다.**
- 세션을 소유하는 주체가 VS Code window가 아니라 Agent Host가 됩니다. 따라서 editor window에서 시작한 세션을 Agents window로 “복제”가 아니라 “동일 세션에 attach”하는 형태로 이어갈 수 있습니다.[^2]

2) **표준화 지점이 모델/추론이 아니라 상태 동기화다.**
- AHP(Agent Host Protocol)는 “에이전트가 어떻게 생각하는지”가 아니라, 여러 클라이언트가 동일 세션을 안전하게 관측/승인/취소/재연결하기 위한 state-first 프로토콜입니다. host가 authoritative state를 갖고, 클라이언트는 action 스트림을 재생(replay)해 같은 뷰로 수렴하게 만든다는 접근이 명확합니다.[^2]

3) **운영팀이 손댈 수 있는 지점이 늘어난다.**
- 세션이 별도 프로세스가 되면 “개발자 UI에 보이는 설정”과 “실제 실행 런타임에서 강제되는 정책”을 분리하기가 쉬워집니다. 이게 곧 sandbox·MCP·tool approval·telemetry 같은 통제의 실효성을 높입니다.

VS Code 1.140 릴리스 노트가 Copilot harness를 소개하면서 “Agent Host Protocol(AHP) 기반의 dedicated agent host process에서 실행되고, 여러 VS Code window에서 같은 agent session에 연결할 수 있다”고 요약한 이유가 여기입니다.[^1]

운영 정책 관점에서 보면, 이제 “세션”은 사람의 집중 단위가 아니라 조직의 변경 단위가 됩니다. 세션을 오래 살려두는 기능은 생산성 기능처럼 보이지만, 실제로는 (1) 장기 실행 프로세스의 네트워크/파일 접근, (2) 장기 누적 컨텍스트의 데이터 관리, (3) 세션 간 권한 상속과 승인 로그 같은 운영 이슈를 동반합니다.

여기서 실무적으로 가장 위험한 착각은 “어차피 Git diff로 리뷰하면 된다”입니다. 에이전트 워크플로가 multi-folder/worktree로 확장되면, diff가 여러 변경 단위로 분산되고, 승인/실행 로그는 세션 단위로 흩어집니다. 상태 모델 자체를 팀 정책으로 잡지 않으면 리뷰가 형식만 남습니다.

## Copilot harness: 개인 취향이 아니라 ‘행동 일관성’의 표준화

VS Code 1.140에서 Copilot harness는 “Copilot SDK로 구동되며 Copilot CLI, standalone GitHub Copilot app 등 다른 Copilot 제품들과 behavior/capabilities가 일관된다”는 점이 강조됩니다.[^1]

이 문장을 팀 운영 정책으로 번역하면 다음이 됩니다.

- **훈련 비용(교육, 문서, 운영 가이드)이 클라이언트별로 갈라지지 않는다.**
  한동안은 “에디터 안 Copilot”, “CLI 에이전트”, “별도 앱”이 서로 다른 승인 흐름/툴 세트/세션 모델을 갖고 있어서 운영 가이드가 분기했습니다. Copilot harness의 목표는 그 분기를 줄이는 쪽입니다.

- **통제 지점도 크로스-클라이언트로 올라간다.**
  VS Code device policy만으로는 VS Code 밖(예: Copilot CLI)을 막지 못합니다. 반대로 GitHub/Copilot 쪽 managed settings는 여러 클라이언트에 걸쳐 적용될 여지가 생깁니다. VS Code도 “AI 관리 3계층”을 공식 문서에서 분리해 설명합니다: (1) Copilot enterprise-managed settings, (2) VS Code device policies, (3) GitHub org/enterprise settings.[^3]

- **세션/승인/툴 호출 로그의 해석이 표준화된다.**
  표준화가 곧 완벽한 감사(audit)를 의미하진 않지만, 최소한 “어느 클라이언트에서 돌렸는지”보다 “어떤 tool을 어떤 scope에서 승인했는지”가 중심이 됩니다.

개발자 경험 관점에서는 harness picker에서 Copilot을 고르는 UX 변화로 보이는데, 조직 관점에서는 “에이전트 실행 런타임이 표준 SDK로 교체되고, 세션이 AHP state 모델로 귀결된다”는 쪽이 더 중요합니다.

## Multi-folder sessions: 폴더/리포지토리가 아니라 ‘세션’이 작업의 컨테이너가 된다

VS Code 1.140의 Multi-folder sessions(Experimental)는 multi-chat session에서 **각 chat이 서로 다른 folder 또는 worktree를 가질 수 있게** 만드는 기능입니다. 이전에는 multi-chat session의 모든 chat이 같은 folder/checkout을 공유했고, 그 탓에 “연구용 옆채팅”과 “실제 수정 채팅”이 섞이면 변경이 새는 문제가 구조적으로 있었습니다. 1.140에서는 “각 chat이 자체 terminal/tasks/changes/PR/Agent merge state를 해당 폴더 단위로 가진다”고 명시합니다.[^1]

이게 팀 운영 정책을 어떻게 바꾸는지부터 정리하는 게 좋습니다.

### 변경 단위의 재정의: ‘PR 1개’가 아니라 ‘폴더×채팅’의 조합

기능 설명에 “각 chat은 자신의 folder를 terminal, tasks, changes, pull request, Agent merge state에 사용한다”고 박혀 있습니다.[^1]

즉, 같은 세션 안에서 다음이 동시에 가능합니다.

- repo A는 chat #1이 작업하면서 PR을 만들고,
- repo B는 peer chat #2가 다른 PR을 만들며,
- 같은 repo라도 worktree를 분리해 peer chat #3/#4가 서로 다른 브랜치에서 실험합니다.

릴리스 노트가 예시로 든 사용 케이스도 “여러 repo에 걸친 기능 구현”, “서로 다른 worktree에서 접근 비교”입니다.[^1]

이 모델을 받아들이면, 운영팀은 더 이상 “에이전트 세션=repo 하나”라고 가정할 수 없습니다. 세션이라는 상위 컨테이너가 여러 변경 단위를 동시 수용합니다. 보안/감사/비용을 보려면, 결국 다음을 기록해야 합니다.

- 세션 ID (장기 실행 컨텍스트)
- chat ID (대화/의도 단위)
- workspace folder 또는 worktree (파일 변경 단위)
- tool approvals (실행 권한 단위)

### 실험 플래그: 숨겨진 설정이 ‘조직 표준’이 되기 전 단계

Multi-folder sessions는 기본적으로 꺼져 있고, Settings UI에도 노출되지 않으며 user-scoped `settings.json`에서 harness별 설정을 `true`로 켜야 합니다.

- Copilot: `chat.agentHost.copilotAgent.multiRootEnabled`
- Claude: `chat.agentHost.claudeAgent.multiRootEnabled`
- Codex: `chat.agentHost.codexAgent.multiRootEnabled`

또한 “peer chat의 folder를 UI로 고르는 기능이 없으니 main chat에 요청해서 peer chat을 만들고 repo/worktree를 설명하라”고 되어 있습니다.[^1]

운영 정책 관점에서는 이게 중요한 신호입니다.

- 지금은 실험 기능이라 개인이 몰래 켜서 쓰는 성격이 강합니다.
- 그런데 표준화가 진행되면, 이런 플래그들이 곧 “조직이 허용하는 작업 모드”가 됩니다.
- 따라서 초기에는 ‘허용 범위’를 폴더 단위로 좁히고, tool approvals·network filter·MCP registry 정책 같은 안전장치를 먼저 깔아야 합니다.

내 경험상 이런 “숨겨진 설정 기반의 실험 기능”은, 한 번 맛을 보면 팀이 순식간에 의존합니다. 그때 정책이 비어 있으면, 나중에 막는 순간 생산성 반발이 바로 옵니다.

## 실행 환경 재현성: Dev Container와 원격 Agent Host를 ‘표준 실행면’으로 보는 이유

에이전트 워크플로의 운영 난이도는 결국 재현성에서 터집니다. 사람은 “내 맥북엔 되는데?”라고 말하면 끝이지만, 에이전트는 실행 실패가 곧 반복 비용입니다.

VS Code 1.140 릴리스 노트는 Agent Host 세션에서 Dev Container를 다루는 항목을 별도로 넣었습니다. “모든 세션이 비활성화되면 5분 후 container를 stop하고, 계속 작업하면 재시작되며, 마지막 세션을 done/delete하면 container를 제거한다”는 식으로 수명주기까지 적어놨습니다.[^1]

여기서 포인트는 “개발자가 컨테이너를 쓰느냐”가 아니라 “에이전트 실행면을 컨테이너로 고정할 수 있느냐”입니다.

- 개발자는 로컬에서 자유롭게 도구를 깔아도 됩니다.
- 에이전트는 팀이 승인한 Dev Container에서만 돌게 만들면, 실행 실패/환경 차이/토큰 유출 리스크를 동시에 줄일 수 있습니다.

VS Code의 AI settings reference는 “Dev Container를 쓸 수 있는 로컬/SSH/Tunnel/WSL 폴더에서 Use Dev Container를 노출하고, Agent Host 세션을 프로젝트의 Dev Container에서 실행”하는 옵션을 언급합니다.[^4]

운영 정책으로는 보통 다음 순서가 현실적입니다.

1) “에이전트가 실행할 수 있는 repo”를 좁힌다(예: build/test가 Dev Container에서 재현되는 repo만).
2) repo마다 devcontainer를 표준화한다(언어 런타임·패키지 매니저·기본 툴링).
3) tool approvals를 “Dev Container 내부 실행”에 맞춰 세밀화한다(예: `pnpm -r test`는 허용, 임의 curl은 ask).

이게 갖춰지면, 에이전트는 사람보다 더 일관되게 실행됩니다. 사람은 컨테이너를 꺼버릴 수도 있지만, 정책은 그렇지 않습니다.

## 저장소(worktree) 재사용: worktree가 ‘격리’에서 ‘캐시 재활용’으로 확장된다

에이전트 워크플로에서 worktree는 원래 격리를 위한 장치였습니다. 에이전트가 한 번에 여러 작업을 병렬로 돌리면, 동일 repo라도 브랜치/파일 변경을 분리해야 합니다. VS Code는 세션/채팅 개념 문서에서 “두 세션이나 채팅이 같은 folder/worktree를 쓰면 edits가 같은 파일에 영향을 준다”고 명확히 못 박습니다.[^5]

문제는 격리를 하면 비용이 커진다는 겁니다.

- worktree를 새로 만들면 `node_modules/`, `.venv/`, `.gradle/` 같은 무거운 디렉터리를 다시 설치합니다.
- 에이전트가 worktree를 늘릴수록 CI 이전 단계에서 로컬 리소스가 먼저 터집니다.

VS Code 1.140은 이 지점을 “Shared worktree folders(Experimental)”로 정면에서 다룹니다. 그리고 Git worktree 문서에서, ignored 폴더를 worktree 간에 복사하지 말고 symlink로 재사용하라고 기능을 분리해 설명합니다.

`git.worktreeSymlinkFolders`는 “현재 checkout에서 Git이 무시하는 폴더 중, tracked file이 없는 폴더를 패턴으로 지정하면 VS Code가 새 worktree를 만들 때 symlink한다”고 되어 있습니다. 예시로 `node_modules/`를 그대로 듭니다.[^6]

운영 정책으로 해석하면 다음과 같습니다.

- worktree를 “격리된 변경 단위”로 쓰되,
- 비용이 큰 의존성 설치는 “격리 대상”에서 제외해 공용 캐시로 돌린다.

다만 이건 보안/재현성/오염 가능성과 맞교환입니다. 그래서 팀 정책에서 “어떤 폴더는 공유해도 되는가”를 명시해야 합니다.

- 공유 후보: `node_modules/`(락파일로 결정되며, 보통 repo 내부 코드와 분리), `.pnpm-store/`(구조가 패키지 해시 기반)
- 애매한 후보: `.venv/`(경로/플랫폼 민감), `.gradle/`(캐시 충돌 가능)
- 공유 금지에 가까운 것: `.git/` 관련, repo 내부 생성물 중 실행 결과가 소스에 섞이는 것

### 재현 가능한 데모: worktree 격리 + node_modules 공유

아래는 “하나의 mono-repo에서 에이전트가 두 접근을 병렬 실험하는 상황”을 의도한 구성입니다. 에이전트 없이도 그대로 재현됩니다.

#### 1) 준비: repo 생성

```bash
mkdir acme-platform && cd acme-platform

git init
npm init -y
npm i -D typescript vitest

mkdir -p packages/api packages/web

cat > packages/api/package.json <<'JSON'
{
  "name": "@acme/api",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run"
  },
  "devDependencies": {
    "vitest": "^3.0.0"
  }
}
JSON

cat > packages/web/package.json <<'JSON'
{
  "name": "@acme/web",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run"
  },
  "devDependencies": {
    "vitest": "^3.0.0"
  }
}
JSON

cat > packages/api/vitest.config.ts <<'TS'
import { defineConfig } from 'vitest/config'
export default defineConfig({ test: { environment: 'node' } })
TS

cat > packages/web/vitest.config.ts <<'TS'
import { defineConfig } from 'vitest/config'
export default defineConfig({ test: { environment: 'node' } })
TS

cat > packages/api/sample.test.ts <<'TS'
import { expect, test } from 'vitest'

test('api basic', () => {
  expect(1 + 1).toBe(2)
})
TS

cat > packages/web/sample.test.ts <<'TS'
import { expect, test } from 'vitest'

test('web basic', () => {
  expect('ok').toBe('ok')
})
TS

cat > package.json <<'JSON'
{
  "name": "acme-platform",
  "private": true,
  "type": "module",
  "workspaces": ["packages/*"],
  "devDependencies": {
    "typescript": "^5.6.0",
    "vitest": "^3.0.0"
  }
}
JSON

cat > .gitignore <<'TXT'
node_modules/
.vscode/
TXT

git add .
git commit -m "init mono repo"

npm install
```

테스트 실행 예상 출력은 환경마다 다르지만, 핵심은 두 패키지가 모두 통과하는지입니다.

```bash
npm -w @acme/api test
npm -w @acme/web test
```

#### 2) VS Code 설정: worktree 간 node_modules 공유

VS Code user settings에 아래를 추가합니다.

```json
{
  "git.worktreeSymlinkFolders": [
    "node_modules/"
  ]
}
```

이 설정은 VS Code가 새 worktree를 생성할 때, 현재 checkout에서 Git이 무시하는(ignored) 대상 중 해당 패턴과 일치하는 폴더를 symlink로 연결하는 방식입니다.[^6]

#### 3) worktree 생성: 두 접근 병렬 실험용

```bash
cd ..
mkdir acme-wt

# 메인 checkout을 acme-platform로 이동
mv acme-platform acme-wt/main
cd acme-wt/main

# 두 실험 브랜치용 worktree 생성

git checkout -b experiment/a
cd ..

git worktree add -b experiment/b ./b main
git worktree add -b experiment/c ./c main
```

이제 `../b`, `../c`는 서로 다른 checkout이지만, VS Code가 worktree를 만들었다면 `node_modules/`를 재사용(symlink)할 수 있습니다. “VS Code가 worktree를 만들 때 symlink한다”는 조건이 있으니, 정책적으로는 팀이 worktree 생성을 VS Code로 유도할지, 또는 개발자가 `git worktree`로 만들 때도 별도 스크립트로 맞춰줄지 결정이 필요합니다.

#### 4) 검증: 중복 설치 비용이 줄었는지 확인

worktree 디렉터리에서 `node_modules`가 실제 디렉터리인지 링크인지 확인합니다.

```bash
cd ../b
ls -l | grep node_modules || true
```

여기서 symlink가 확인되면, 에이전트가 worktree를 늘릴수록 “clone + install”이 아니라 “checkout + build/test”로 비용 구조가 바뀝니다.

이게 팀 운영 정책으로 중요한 이유는 명확합니다.

- multi-folder sessions가 “worktree를 쉽게 늘리는 방향”이라면[^1]
- shared worktree folders는 “늘어난 worktree의 비용을 감당 가능하게” 만듭니다.[^6]

둘이 같이 있어야 조직 단위 표준으로 굴러갑니다.

## 조직 단위 AI 컨트롤: VS Code가 제시한 3계층을 그대로 받아들이는 게 현실적이다

VS Code는 엔터프라이즈에서 AI 설정을 관리하는 방법을 세 레이어로 분리합니다.

- Copilot enterprise-managed settings(크로스-클라이언트 가드레일)
- VS Code device policies(에디터/디바이스 단위 강제)
- GitHub organization/enterprise settings(계정/서비스 단위)

그리고 “겹치는 컨트롤은 한 시스템에서만 설정하라”, “우선순위를 이해하라” 같은 운영 원칙까지 문서에 적어놨습니다.[^3]

이 프레임을 그대로 팀 정책으로 옮기면 설계가 깔끔해집니다.

### 1) GitHub org/enterprise settings: 좌석/모델/콘텐츠 범위

이 레이어는 “누가 Copilot을 쓸 수 있는가”, “어떤 모델/기능이 계정에 열려 있는가”, “콘텐츠 제외(content exclusion) 같은 서버 사이드 정책”에 가깝습니다. VS Code 클라이언트만 막아서는 의미가 없는 것들입니다.

### 2) Copilot enterprise-managed settings: 승인/샌드박스/툴 권한을 크로스-클라이언트로

Copilot managed settings는 특히 `permissions.deny/ask/allow`의 의미가 큽니다. VS Code에서 Agent Host 기반 세션에 이 규칙이 적용된다는 점이 GitHub 문서에 직접 언급됩니다.[^7]

- deny는 어떤 소스에서든 걸리면 무조건 차단
- ask는 매번 fresh approval 요구(이전 승인 재사용 불가)
- allow는 “선언한 소스들 간 교집합(intersection)”으로만 유효

이 조합은 운영팀이 좋아하는 형태입니다. 여러 팀/여러 배포 채널이 섞여도 “가장 보수적으로 수렴”하기 쉽기 때문입니다.[^7]

또한 `permissions.disableBypassPermissionsMode`는 흔히 말하는 YOLO/allow-all(무승인 실행)을 원천 차단합니다. GitHub 문서는 이 설정이 VS Code의 global auto-approve 설정을 끄고 재활성화도 막는다고 적습니다.[^7]

운영 정책으로는 결론이 단순해집니다.

- managed settings로 “승인 없는 실행”을 기본적으로 금지한다.
- 허용이 필요한 팀은 enterprise team override로 예외를 준다(문서상 per-team override 메커니즘이 존재).[^3]

### 3) VS Code device policies: 에디터 표면에서 보이는 스위치/기본값 강제

VS Code는 정책을 Intune/Group Policy/MDM/리눅스 JSON 파일로 배포할 수 있고, 정책이 설정되면 user/workspace 설정을 override한다고 명시합니다.[^8]

특히 리눅스는 `/etc/vscode/policy.json`로 강제할 수 있습니다(최소 1.106부터).[^8]

이 레이어는 “조직이 승인한 GitHub org 계정만 AI 활성화”, “Agent mode 자체를 끔”, “MCP를 off로 꺼버림”, “extension tools를 금지” 같은 즉시 효과가 필요한 것에 적합합니다. VS Code 문서는 예로 `ChatApprovedAccountOrganizations`를 들어, 승인된 GitHub organization에 속한 계정으로 로그인하기 전까지 AI 기능을 fail-closed로 비활성화한다고 설명합니다.[^3]

또한 VS Code는 enterprise controls로 “최소 버전 요구 사항을 설명하고 업데이트 행동을 안내하는 UX”를 1.140에 추가했습니다. 강제 자체는 기존과 동일하고, 사용자에게 필요한 버전/설치된 버전을 보여주는 방향으로 정비한 것입니다.[^9]

이건 운영팀에게 중요한데, 정책의 목표가 “막기”가 아니라 “업데이트를 강제해 샌드박스/보호 기능을 최신으로 유지하기”로 이동하기 때문입니다.

## 허용/차단/승인 설계: MCP·툴·네트워크를 같은 표로 관리해야 한다

에이전트의 위험은 모델이 아니라 도구입니다. 파일 읽기/쓰기, shell, 네트워크, 외부 MCP 서버가 결합되면 사실상 RPA에 가깝습니다.

VS Code 문서는 AI 보안을 “approval scopes, agent sandboxing, enterprise policies, warning banners”로 다루면서, 구체적으로 어떤 정책이 필요한지까지 예시로 듭니다.

- MCP server sources를 `ChatMCP` 정책으로 `registryOnly`로 제한하거나 `off`로 끈다
- private MCP registry는 `McpGalleryServiceUrl`로 지정한다
- extension-contributed tools는 `ChatAgentExtensionTools`로 차단한다
- global auto-approval은 `ChatToolsAutoApprove`로 금지한다
- 특정 툴은 `ChatToolsEligibleForAutoApproval`로 수동 승인을 강제한다
- terminal auto-approval은 `ChatToolsTerminalEnableAutoApprove`로 끈다

[^10]

여기서 운영 정책의 설계 포인트는 “각각을 따로따로 설정”이 아니라, 한 장의 표로 threat model을 정리하는 것입니다.

- Built-in tools(파일, diff, PR, 터미널 등) 중 어떤 것은 allow, 어떤 것은 ask
- 네트워크 fetch/browser는 기본 deny + allowlist
- MCP는 registryOnly로 통제하고, 허용된 서버만 allow
- extension tools는 원칙적으로 deny(정 필요 시 특정 publisher/extension만 허용)

이 표가 없으면, 개발자는 “왜 curl은 안 되는데 git은 되지?” 같은 질문을 하고, 운영팀은 “정책이 여기저기 흩어진 상태”에서 일관성 없는 답을 하게 됩니다.

## 로깅과 관측성: OpenTelemetry는 ‘내용’보다 ‘책임 소재’를 위해 쓴다

에이전트 워크플로는 자동화이면서도 최종 책임은 사람에게 남습니다. 그래서 필요한 로깅은 보통 두 층입니다.

1) 운영 로깅: 세션이 어디서 실행됐고(로컬/원격), 어떤 정책이 적용됐고, 어떤 도구 승인이 있었는지
2) 감사 로깅: 특정 사건이 났을 때 “누가 승인했는지”를 추적할 수 있는 최소한의 identity

VS Code 1.140은 enterprise 섹션에서 “Copilot OpenTelemetry에서 user identity를 캡처해 개인 개발자에게 attribution할 수 있다”고 언급합니다. Local chat sessions에서 `user.name` 같은 attribute를 추가하고, policy로 `telemetry.capture.identity`(CopilotOtelCaptureIdentity)로 제어된다는 설명입니다. 또한 정책 해석 방식도 “가장 높은 우선순위 채널의 telemetry block만 적용”으로 바꿨다고 적습니다.[^9]

이 기능은 민감합니다.

- identity 캡처는 운영상 강력하지만, 프라이버시/노사/내부 규정과 바로 충돌할 수 있습니다.
- 반대로 identity가 없으면, 승인 체계가 실질적으로 무력화됩니다. “승인 버튼을 누른 사람”이 항상 남는 구조가 아니면, 책임 소재가 흐려집니다.

내 결론은, identity 캡처는 “항상 켠다/항상 끈다”가 아니라, 승인 체계를 어떤 수준으로 운영할지(예: ask가 많은 조직 vs allow가 많은 조직)에 따라 결정해야 한다는 쪽입니다. ask를 촘촘히 걸수록 identity가 없으면 운영이 붕괴합니다.

추가로 세션 자체의 보관/동기화도 정책 영역으로 들어왔습니다. VS Code의 session history 문서는 “Copilot Business/Enterprise에서 session sync는 GitHub.com enterprise policy(클라우드 저장 허용/차단)와 VS Code group policy `CopilotSessionSync`(로컬 강제) 두 축으로 제어된다”고 씁니다.[^11]

즉, 이제는 대화 기록도 팀 정책 대상입니다.

## 정책 예시: 리눅스 `/etc/vscode/policy.json`으로 ‘최소 안전선’ 강제

VS Code는 리눅스에서 정책 파일을 `/etc/vscode/policy.json`에 두는 방식을 공식 지원합니다.[^8]

아래는 “개발자 PC에서 VS Code로 agent workflow를 허용하되, 조직 안전선은 강제한다”는 목적의 예시입니다.

```json
{
  "ChatApprovedAccountOrganizations": ["contoso"],
  "ChatAgentMode": true,
  "ChatAgentExtensionTools": false,

  "ChatMCP": "registryOnly",

  "ChatToolsAutoApprove": false,
  "ChatToolsTerminalEnableAutoApprove": false,

  "CopilotSessionSync": false
}
```

의도는 다음과 같습니다.

- 승인된 GitHub organization 계정으로 로그인하기 전엔 AI 기능이 fail-closed로 비활성화[^3]
- extension tools를 차단해 “설치된 extension이 몰래 툴을 추가”하는 리스크를 줄임[^10]
- MCP는 registryOnly로 제한해, 조직이 승인한 레지스트리/갤러리 소스 외의 서버 실행을 어렵게 만듦[^10]
- global auto-approval 및 terminal auto-approval을 금지해 무승인 실행을 막음[^10]
- session sync를 꺼서 세션이 클라우드로 나가지 않도록 로컬 고정[^11]

정책 적용 확인은 VS Code의 Developer: Policy Diagnostics로 가능하다고 문서에 적혀 있습니다.[^8]

이 레벨의 강제만으로도 “개발자 개인 설정이 어떻든 최소 안전선은 유지”가 됩니다.

## Copilot enterprise-managed settings 예시: deny/ask/allow로 ‘조직 승인 모델’을 만든다

device policy가 “VS Code에서 보이는 스위치”를 강제한다면, Copilot enterprise-managed settings는 더 직접적으로 “에이전트가 어떤 작업을 할 수 있는지”를 규칙으로 표현합니다.

GitHub 문서는 `permissions.deny/ask/allow` 규칙의 우선순위(deny > ask > allow), ask의 성격(매번 fresh approval), allow의 교집합 적용을 상세히 정의합니다.[^7]

아래는 규칙 설계의 형태만 보여주는 예시입니다(실제 키/적용 범위는 GitHub 문서의 최신 스키마를 따라야 합니다).

```json
{
  "permissions": {
    "disableBypassPermissionsMode": "disable",

    "deny": [
      "Shell(git push *)",
      "Domain(*)"
    ],

    "ask": [
      "Shell(npm publish *)",
      "Shell(pip upload *)",
      "Read(//etc/*)",
      "Edit(//etc/*)"
    ],

    "allow": [
      "Shell(git status)",
      "Shell(git diff *)",
      "Shell(npm test *)",
      "Domain(github.com)",
      "Domain(*.company.internal)"
    ]
  }
}
```

- `disableBypassPermissionsMode`로 YOLO/allow-all을 차단해 우회 경로를 봉쇄[^7]
- `Domain(*)` 같은 과격한 deny는 그대로 쓰기 어렵지만, “기본 deny + 필요한 것만 allow” 형태가 가능하다는 점이 중요합니다.
- ask는 “개발 속도”가 아니라 “사고 비용”을 줄이는 장치로 봐야 합니다. 특히 publish 계열은 ask가 맞는 경우가 많습니다.

이 규칙을 세션/툴 승인 UX와 결합하면, 개발자는 “어떤 작업이 조직 정책상 민감한지”를 에이전트 워크플로 안에서 바로 학습합니다. 보안 교육 문서보다 효과가 좋습니다.

## 함정과 트레이드오프: 표준화가 곧 단순화는 아니다

VS Code 1.140이 제시하는 방향은 분명하지만, 팀이 부딪히는 트레이드오프도 명확합니다.

### 1) worktree 재사용은 오염 가능성을 동반한다

`git.worktreeSymlinkFolders`로 `node_modules/`를 공유하면 설치 비용은 줄지만, 브랜치마다 의존성이 달라지는 순간(락파일 변경) 오염이 생길 수 있습니다. 특히 패키지 매니저/락파일 정책이 느슨한 팀은 “에이전트가 만든 worktree”가 “사람이 쓰는 worktree”를 망가뜨리는 형태로 사고가 납니다.

따라서 공유 폴더는 팀의 패키지 관리 규율(락파일 강제, 재현 가능한 install)을 전제로 해야 합니다.

### 2) Multi-folder sessions는 리뷰의 단위를 흐릴 수 있다

세션이 여러 repo/여러 worktree를 포함하면, 변경이 자연스럽게 커집니다. 릴리스 노트가 “세션 hover에서 여러 repo의 PR을 요약”하는 UI를 넣은 이유가 이 복잡도를 완화하려는 의도일 텐데[^1], 팀이 PR discipline을 강제하지 않으면 “세션 하나가 거대한 변경 묶음”이 되는 건 막기 어렵습니다.

### 3) 통제는 늘 비용을 낳는다

- tool approvals를 촘촘히 걸면, 승인 대기 시간이 병목이 됩니다.
- MCP를 registryOnly로 만들면, 팀 내부 MCP 레지스트리 운영이 필요합니다.[^10]
- OpenTelemetry를 켜면 collector 운영과 내부 규정 정합성이 필요합니다.[^9]

이 비용을 감당할 준비 없이 “에이전트는 금지/허용” 같은 단순 정책만 내면, 조직은 곧 우회 도구(Cursor류, 별도 CLI, 개인 계정)를 양산하게 됩니다. 그쪽이 더 통제 불가능합니다.

## 도입 판단 기준: 개발자 기능이 아니라 운영 정책으로 결정할 체크리스트

VS Code 1.140을 계기로 팀이 정해야 할 기준을, 기능 이름이 아니라 정책 질문으로 정리하면 아래처럼 떨어집니다.

### 1) 실행면: 에이전트는 어디서 실행되는가

- 로컬 PC인가, 원격 Agent Host인가(리소스 격리, 네트워크 경계).
- Dev Container를 표준 실행면으로 강제할 것인가(재현성, 보안).

Agent Host가 “로컬 utility process 또는 standalone server로 오래 살아남는 프로세스”라는 점을 감안하면[^2], 실행면이 정해지지 않은 상태에서 세션을 장기화하는 건 운영상 부채가 됩니다.

### 2) 변경 단위: 세션/채팅/폴더(worktree)를 어떻게 매핑할 것인가

- multi-folder sessions를 켤 것인가.
- 켠다면 “세션 하나에 repo는 몇 개까지” 같은 제한을 둘 것인가.
- worktree 전략(격리 vs 재사용)을 어떻게 가져갈 것인가.

### 3) 도구 권한: 무엇을 허용하고 무엇을 승인으로 둘 것인가

- MCP를 허용할지, registryOnly로 제한할지, 아예 off로 둘지.[^10]
- extension tools를 허용할지.
- terminal auto-approval/global auto-approval을 허용할지.[^10]

### 4) 데이터: 세션 기록과 텔레메트리를 어디까지 남길 것인가

- session sync를 허용할지(클라우드 저장).[^11]
- OpenTelemetry에 identity를 넣을지.[^9]

### 5) 거버넌스: 통제 레이어를 어디에 둘 것인가

- VS Code device policy로 막을 것인가.
- Copilot enterprise-managed settings로 크로스-클라이언트로 묶을 것인가.
- GitHub org/enterprise settings로 계정 레벨을 고정할 것인가.

VS Code 공식 문서가 세 레이어를 분리해 설명하는 이유는, 이 셋을 섞어 쓰되 “겹치는 규칙을 여러 곳에 중복 정의하면 운영이 망가진다”는 걸 이미 겪었기 때문이라고 보는 편이 안전합니다.[^3]

정리하면, VS Code 1.140의 변화는 Copilot 기능 강화가 아니라 IDE가 조직의 실행 플랫폼으로 편입되는 과정입니다. Copilot harness와 Agent Host/AHP가 세션을 표준화하고, multi-folder sessions와 shared worktree folders가 작업 단위를 재구성하며, enterprise controls가 그 위에 통제/관측 레이어를 얹습니다. 팀이 이걸 개인 생산성 기능으로 취급하는 순간, 통제는 뒤늦게 따라가며 충돌 비용만 커지고, 운영 정책으로 다루는 순간부터는 오히려 개발 경험이 안정화됩니다.

관련해서 규제/정책의 디테일이 실제 운영을 갈라놓는다는 관점은 예전에 정리한 글[^12]과도 연결되고, 엔터프라이즈 현장에서 Copilot/Agent 확산과 ROI 회의론이 동시에 커지는 흐름[^13]이 왜 도구 기능 논쟁으로만은 설명되지 않는지도 같은 축에서 이해됩니다.

## 참고 자료

- [Visual Studio Code 1.140 릴리스 노트](https://code.visualstudio.com/updates/v1_140)
- [Introducing the Agent Host for persistent, portable agent sessions](https://code.visualstudio.com/blogs/2026/08/26/agent-host-architecture)
- [Manage AI settings in enterprise environments](https://code.visualstudio.com/docs/enterprise/manage-ai-settings)
- [Centrally manage VS Code settings with policies](https://code.visualstudio.com/docs/enterprise/policies)
- [VS Code for enterprise](https://code.visualstudio.com/docs/enterprise/overview)
- [Secure AI-assisted development in VS Code](https://code.visualstudio.com/docs/agents/run/security)
- [Choose and use an agent harness](https://code.visualstudio.com/docs/agents/run/agent-harnesses)
- [Git branches and worktrees in VS Code](https://code.visualstudio.com/docs/sourcecontrol/branches-worktrees)
- [MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
- [Sandbox Copilot Agent Host sessions](https://code.visualstudio.com/docs/agents/run/agent-sandboxing)
- [Sync and query session history](https://code.visualstudio.com/docs/agents/run/sessions/session-history)
- [Enterprise managed settings (GitHub Docs)](https://docs.github.com/en/copilot/reference/enterprise-administrators/enterprise-managed-settings)

[^1]: <https://code.visualstudio.com/updates/v1_140>
[^2]: <https://code.visualstudio.com/blogs/2026/08/26/agent-host-architecture>
[^3]: <https://code.visualstudio.com/docs/enterprise/manage-ai-settings>
[^4]: <https://code.visualstudio.com/docs/agents/reference/ai-settings>
[^5]: <https://code.visualstudio.com/docs/agents/concepts/sessions>
[^6]: <https://code.visualstudio.com/docs/sourcecontrol/branches-worktrees>
[^7]: <https://docs.github.com/en/enterprise-cloud%40latest/copilot/reference/enterprise-administrators/enterprise-managed-settings>
[^8]: <https://code.visualstudio.com/docs/enterprise/policies>
[^9]: <https://code.visualstudio.com/updates/v1_140?trk=article-ssr-frontend-pulse_little-text-block>
[^10]: <https://code.visualstudio.com/docs/agents/run/security>
[^11]: <https://code.visualstudio.com/docs/agents/run/sessions/session-history>
[^12]: <https://daewooki.github.io/posts/2026-3-ai-eu-code-1/>
[^13]: <https://daewooki.github.io/posts/6-ai-copilotagent-vs-roi-1/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
