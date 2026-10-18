---
title: "VS Code 1.142: 에이전트를 운영 가능한 기능으로 만드는 캔버스·채팅 이동·관리자 제어"
description: "VS Code 1.142는 에이전트 도입을 막던 컨텍스트 이동·워크플로 공유·권한 통제를 제품 기능으로 흡수했다."
date: 2026-10-18 12:29:07 +0900
categories: ["News", "Tools"]
tags: ["vscode", "copilot", "agent-host", "enterprise-policy", "agent-canvas", "chat-migration"]
render_with_liquid: false
---

## 2026-10-14에 무엇이 바뀌었나: 기능 추가가 아니라 운영 가능한 상태로의 전환
Visual Studio Code 1.142 Stable은 2026-10-14에 릴리스됐고, 릴리스 하이라이트 자체가 에이전트의 운영 이슈를 정면으로 다룹니다. Canvases(Preview)로 에이전트 워크플로를 공유 가능한 형태로 만들고, 진행 중인 대화를 다른 폴더나 새 Git worktree로 옮겨 컨텍스트를 이어가며, 기업 환경에서 에이전트 권한/샌드박싱 정책을 강제하고 개발자가 선택할 수 있는 permission mode까지 통제할 수 있게 했습니다.[^1]

개별 기능을 보면 “편의 기능”처럼 보일 수 있는데, 1.142의 메시지는 다릅니다. 에이전트는 이제 prompt 잘 쓰는 사람만 잘 쓰는 실험 기능이 아니라, 팀 단위로 배포/통제/감사할 수 있는 제품 표면을 갖추기 시작했습니다. 특히 1.142가 강조하는 Enterprise 항목은, 정책이 걸린 순간 Local harness로는 규칙을 집행할 수 없다는 사실을 제품이 인정하고, 그 갭을 **Agent Host 강제 라우팅**으로 메워버립니다.[^1]

여기서의 “운영”은 단순히 설정을 잠그는 수준이 아닙니다.

- 대화 컨텍스트가 저장되는 단위(채팅)와 코드가 존재하는 단위(workspace/worktree)가 달라졌고, 둘 사이를 옮기는 절차가 생겼습니다.[^2]
- 워크플로는 텍스트 prompt가 아니라, extension 기반 artifact(캔버스)로 배포될 수 있는 길이 열렸습니다.[^1]
- 권한 통제는 “auto approve 끄기” 같은 단일 토글이 아니라, permission mode를 제품 UI에서 제거/허용하는 형태로 내려오기 시작했습니다.[^1]

## 1.140이 표준화의 언어를 만들었다면, 1.142는 표준을 운영물로 바꿨다
나는 1.140 계열에서의 변화를 “에이전트 워크플로 표준화”로 정리해 왔습니다. 표준화는 보통 문서와 규칙을 먼저 만들고, 그다음 도구가 따라오는 식으로 진행됩니다. 그런데 에이전트는 반대였습니다. 도구가 먼저 자라면서 규칙이 뒤늦게 따라왔고, 그 과정에서 팀 도입을 막는 병목은 기능 부족이 아니라 운영 부담으로 이동했습니다.

이 흐름을 VS Code 쪽 릴리스 노트만 놓고 봐도 연결이 됩니다.

- 1.141에는 legacy VS Code policy를 Agent Host managed settings 쪽으로 옮기라는 메시지가 들어가 있습니다. 즉 “이제부터는 host-side에서 통제해야 한다”는 방향성이 먼저 제시됐습니다.[^3]
- 1.142는 그 방향성을 전제하고, policy가 켜진 환경에서 Local harness를 사실상 안전하게 운용할 수 없다는 점을 제품 동작으로 반영합니다(자동 마이그레이션).[^1]

여기서 중요한 관점은 “개발자 경험”이 아니라 “표준 IDE 운영”입니다. 회사 입장에서 IDE는 다음을 만족해야 합니다.

- 정책이 적용됐는지 확인 가능해야 하고(진단/리포트)
- 우회 경로가 있으면 안 되고(모드 차단)
- 예외(escape hatch)는 있어야 하지만, 예외를 쓰는 순간 보안 경계가 어떻게 무너지는지 제품이 명시해야 합니다.

VS Code 1.142는 이 운영 요구를 기능으로 흡수하기 시작했습니다.

참고로 릴리스 운영의 관점은 IDE에도 그대로 적용됩니다. 내 기준에서 팀 단위 IDE 업그레이드는 브라우저의 ring 설계와 거의 같은 문제를 갖습니다. 업데이트를 동시에 올리면 생산성 저하가 한 번에 터지고, 너무 늦게 올리면 보안/정책 기능이 뒤처집니다. 이건 예전에 정리한 [Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영](https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/)에서 다룬 방식이 그대로 재사용됩니다.

## 채팅 이동: 컨텍스트는 그대로, 작업 디렉터리만 바꾼다는 발상
1.142의 “Move chats”는 UI 패널을 왼쪽/오른쪽으로 옮기는 얘기가 아닙니다. 진행 중인 agent 채팅을 “다른 폴더” 또는 “새 Git worktree”로 옮기면서도 대화 히스토리를 유지하는 기능입니다.[^1]

### 왜 이게 팀 도입의 병목을 풀어주나
팀 도입에서 자주 터지는 케이스는 이런 흐름입니다.

1) A repo에서 이슈를 조사하면서 agent 채팅이 길어집니다.
2) 실제 구현은 충돌을 피하려고 worktree를 파서 하거나, 아예 다른 repo/폴더에서 해야 합니다.
3) 이때 대화를 새로 시작하면, 조사한 맥락이 날아가고 prompt cache도 깨지며, 결과적으로 비용과 시간이 둘 다 증가합니다.

VS Code 문서도 “이전에는 새 채팅을 시작하고 컨텍스트를 다시 쌓아야 했다”고 명시합니다.[^1]

이 기능이 의미 있는 이유는, 에이전트의 컨텍스트가 “대화”와 “워크스페이스 파일/명령 실행”을 함께 포함하기 때문입니다. 채팅을 옮긴다는 건 단순히 텍스트 로그를 복사하는 게 아니라, 이후 tool call의 기본 작업 디렉터리를 바꾸고, 그 바뀐 공간에서 계속 실행되게 만든다는 뜻입니다.

### 동작 조건과 제약을 있는 그대로 이해해야 한다
이 기능은 아무 채팅에서나 되는 버튼이 아닙니다.

- Agents window에서 수행되며, “agent-tool 요청(prompt)”로 실행됩니다. 별도의 Move 버튼이 아니라 자연어로 “옮겨라”를 요청하는 방식입니다.[^2]
- “Agent Host session + one chat + one local folder” 같은 전제조건이 붙습니다. Copilot harness 또는 Agent Host 쪽 Codex 통합(Experimental)처럼 Agent Host 기반이 기본 가정입니다.[^2]

또한 “폴더로 이동”과 “새 worktree로 격리”는 결과가 다릅니다.

- 폴더 move는 대상 폴더에 이미 있는 파일을 사용하며, 기존 파일을 복사/이동하지 않습니다.[^2]
- worktree는 committed Git state에서 시작합니다. uncommitted 변경은 원래 폴더에 남습니다(다만 include rule로 복사되는 파일은 예외). 그리고 worktree 생성에는 최소 1개의 commit이 필요합니다.[^2]

팀 운영 관점에서는 이 차이가 굉장히 중요합니다.

- “조사/분석 단계에서 바뀐 파일”이 구현 단계에 섞이면, agent가 의도치 않게 drift를 확대시킵니다.
- 반대로 include rule을 잘못 잡으면, 원래 폴더의 민감한 파일이 새로운 격리 환경으로 복사될 수 있습니다.

내가 이 기능을 표준 운영에 넣을 때는, “move는 폴더 이동이 아니라 worktree 격리를 기본값으로”라는 규칙을 먼저 세웁니다. 폴더 이동은 개인 환경에서는 편하지만, 팀 표준에서는 감사를 어렵게 만듭니다. worktree는 최소한 브랜치/폴더/세션 단위로 변경이 분리되어, 나중에 삭제/보관 정책을 세우기가 쉽습니다.

### 실제로 팀에서 쓰게 되는 프롬프트 형태
문서에 나온 프롬프트 예시는 그대로 팀 runbook에 들어갈 만합니다.

```text
Continue this task in a new Git worktree of the current repository before implementing it.
```

그리고 특정 폴더로 이동시키는 경우는 absolute path를 쓰는 방식입니다.[^2]

```text
Move this chat to <absolute folder path> and continue the current task there.
```

이때 제품이 요구하는 절차는 “확인(confirm)”이 포함됩니다.

- 목적지 확인
- 폴더를 그대로 쓸지, worktree를 만들지 선택
- tool approval 또는 Workspace Trust 요청이 뜨면 검토

이 확인 흐름이 있다는 사실 자체가 “운영 가능한 기능”에 가깝습니다. 팀에서 문제가 되는 건 기능이 아니라, 기능이 조용히 돌아가서 흔적이 남지 않는 것입니다.

## 캔버스: 워크플로를 prompt에서 artifact로 내리는 첫 번째 UI
Canvases는 채팅 옆에 열리는 인터랙티브 UI 표면입니다. 핵심은 “대화로 조율하는” 방식에서, “같은 artifact를 보면서 수정하는” 방식으로 협업 모델을 바꿨다는 점입니다. 릴리스 노트는 캔버스를 “chat 옆에서 같은 artifact를 inspect/update”하는 방식으로 설명합니다.[^1]

### Kanban은 데모이고, 본질은 extension 기반 배포다
1.142는 Kanban 캔버스를 예로 듭니다. 카드/컬럼을 사람이 직접 움직이고, 에이전트가 태스크를 쪼개고 상태를 업데이트하는 식입니다.[^1]

하지만 팀 운영 관점에서 더 중요한 문장은 따로 있습니다.

- “Every canvas is provided by a canvas extension.”[^4]

즉, 캔버스는 단순한 내장 UI가 아니라 extension으로 공급되는 플러그인 표면입니다. 여기서 표준화의 무게중심이 이동합니다.

- prompt 템플릿 표준화: 사람의 습관과 편차를 통제해야 합니다.
- 캔버스 extension 표준화: 코드 리뷰/버전 관리/배포/회수가 가능합니다.

내가 1.142를 변곡점으로 보는 이유가 여기 있습니다. 워크플로를 “문서”로 배포하는 단계에서 “코드 artifact”로 배포하는 단계로 넘어갈 수 있기 때문입니다.

### 활성화/획득 방법과, 운영에서 걸리는 제약
Canvases는 기본적으로 Preview이며 설정으로 켭니다.

- 설정: `chat.canvases.enabled`[^1]

그리고 캔버스를 얻는 루트는 두 가지로 안내됩니다.

1) `/create-canvas`로 프로젝트에 맞는 canvas extension을 생성하게 하기[^1]
2) GitHub Copilot app에서 canvas extension이 포함된 chat plugin을 설치한 뒤, VS Code에서 사용하기[^1]

운영에서 특히 중요한 제한도 명시되어 있습니다.

- “desktop의 supported local Copilot Agent Host sessions”에서만 가능
- Claude/Codex/extension-host Local sessions/remote Agent Host/web client/auxiliary window hosting에서는 불가[^4]

이 제한은 곧 “사내 표준 IDE”에서의 지원 범위를 정합니다.

- Dev Container/SSH/WSL 같은 Remote 개발 비중이 높은 조직은, Canvases를 곧바로 표준 워크플로 UI로 삼기 어렵습니다.
- 반대로 로컬 개발이 표준인 조직은, 워크플로 공유가 prompt 문서 수준에서 extension artifact 수준으로 올라갈 수 있습니다.

### 캔버스가 워크플로 공유의 해답이 되려면, extension 통제가 먼저다
캔버스는 extension으로 공급됩니다. 따라서 “업무 표준 워크플로를 캔버스로 만든다”는 말은 “업무 표준 extension을 배포한다”로 바뀝니다.

이 순간부터 필요한 건 기능 설명이 아니라 운영 규칙입니다.

- canvas extension 저장소는 어디에 둘지
- 배포 단위는 workspace 내 생성인지, 사내 Marketplace/사설 레지스트리인지
- extension 업데이트/서명/승인 절차를 어떻게 둘지

VS Code가 직접 “canvas는 extension이다”라고 못 박은 이상, 캔버스 도입은 extension governance 없이는 위험해집니다. 특히 에이전트와 결합된 extension은 tool surface를 넓히기 쉽고, tool 결과는 prompt injection의 통로가 될 수 있습니다. VS Code 문서가 URL fetch에 대해 two-step approval(도메인 신뢰 후, 가져온 내용의 리뷰)을 넣어둔 것도 같은 맥락입니다.[^5]

## 정책/권한/샌드박싱: 1.142의 핵심은 자동 마이그레이션과 모드 통제
1.142 Enterprise 섹션은, 지금까지 현장에서 가장 많이 부딪히던 질문에 답합니다.

- “정책을 걸었는데 왜 어떤 사람은 Local에서 돌아가고, 어떤 사람은 Copilot에서 돌아가나?”
- “Assisted는 허용하고 싶은데 Allow all은 막고 싶다.”

### 정책이 켜진 순간, VS Code가 Local을 고집하지 않게 됐다
1.142는 조직이 다음 중 하나를 구성하면, Copilot harness in Agent Host가 “full chat sessions”에 필요하다고 명시합니다.

- managed settings의 `permissions`가 nonempty
- 또는 `sandbox.enabled`가 `true`[^1]

그리고 이 조건이 충족되면, 기존의 Local chat을 Copilot으로 “자동 이동”시킵니다.

- transcript와 unsent draft(attachment 포함)를 보존
- 자동으로 뭔가를 전송하지는 않음
- 새 채팅이 정상적으로 열려야 원본을 archive 처리[^1]

이 동작은 팀 운영에선 굉장히 큰 변화입니다. 정책을 걸어도 실제 집행면이 Local에 남아있으면, 규정 준수는 문서로만 존재합니다. 1.142는 이 회색지대를 제품이 스스로 지워버립니다.

다만 대가도 큽니다.

- 정책이 적용되는 동안 Claude/Codex/terminal chat이 unavailable
- editor inline chat은 제한된 read/edit 용도로는 가능[^1]

즉, “정책 집행”과 “다양한 harness 실험”을 동시에 가져가기는 어렵습니다. 조직이 어떤 것을 표준으로 삼을지 먼저 정해야 합니다.

### 임시 우회로는 있다: 다만 우회가 곧 보안 경계 붕괴다
관리자가 전환 시간을 벌기 위해 Local harness를 유지시키는 설정도 추가됐습니다.

- `vscode.temporaryDefaultToLocalHarness: true`를 unified managed settings에 설정[^1]

하지만 릴리스 노트는 바로 아래에 경고를 붙입니다.

- 이 opt-out은 “managed sandbox/permission 설정에 의해 요구되는 라우팅”까지 override한다
- Local은 runtime-only rules를 enforce하지 않는다
- enforcement는 Copilot Agent Host에서만 unchanged로 유지된다[^1]

운영 가이드 관점에서 이건 명확합니다. 임시 우회는 “정책 적용 전환”을 위한 window로만 쓰고, 표준 상태로 남기면 안 됩니다.

### permission mode를 UI에서 지우는 방식으로 통제하기
1.142는 Copilot permission picker에 대해 “Assisted는 허용하지만 Allow all은 차단” 같은 조합을 명시적으로 지원합니다. 그리고 설정 예시를 그대로 제공합니다.[^1]

```json
{
  "permissions": {
    "disableBypassPermissionsMode": "disable",
    "disableAssistedPermissionsMode": false
  }
}
```

여기서 운영 관점의 핵심은 두 가지입니다.

1) 개발자에게는 “선택지가 보이는 UI”가 곧 정책입니다. picker에서 사라지는 순간, 교육 비용이 크게 줄어듭니다.
2) 정책은 “defaultMode 지정”만으로는 부족하고, “허용/차단 모드의 목록”을 관리해야 합니다.

또한 주의 문구도 같이 읽어야 합니다.

- Assisted permissions는 현재 `permissions.{allow,ask,deny}`와 호환되지 않으며, 사용 중이면 `

[^1]: <https://code.visualstudio.com/updates/v1_142>
[^2]: <https://code.visualstudio.com/docs/agents/run/sessions/manage-sessions>
[^3]: <https://code.visualstudio.com/updates/v1_141>
[^4]: <https://code.visualstudio.com/docs/agents/run/agent-harnesses>
[^5]: <https://code.visualstudio.com/docs/agents/run/security>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
