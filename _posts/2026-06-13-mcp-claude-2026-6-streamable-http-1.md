---
title: "MCP 서버로 Claude 에이전트를 “프로젝트에 안전하게 붙이는” 방법 (2026년 6월 기준: Streamable HTTP, 보안 함정, 확장 패턴)"
date: 2026-06-13 04:27:26 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-06]
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
LLM 에이전트를 실제 서비스에 붙일 때 가장 큰 문제는 “모델이 똑똑한 것”이 아니라 **모델이 접근할 컨텍스트/도구를 어떻게 표준화해서, 재사용 가능하고, 안전하게 제공하느냐**입니다. Model Context Protocol(MCP)은 이 문제를 **client–server 프로토콜**로 분리해 해결합니다. 즉, Claude(또는 MCP client)가 “도구 목록을 발견(discovery)하고 호출(call)”할 수 있도록, 우리가 별도의 MCP server로 tools/resources/prompts를 노출하는 구조입니다. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/))

**언제 쓰면 좋은가**
- IDE/데스크톱/사내 Agent가 **여러 데이터 소스/시스템(Jira, Git, DB, 내부 API)**을 “도구”로 호출해야 할 때
- 팀 단위로 도구를 공용화해야 할 때(서버로 계약(contract)을 고정)
- 모델을 바꿔도 도구 계층은 유지하고 싶을 때(표준 인터페이스)

**언제 쓰면 안 되는가**
- “간단한 단일 기능”만 필요하고 배포/운영이 부담일 때(그냥 앱 내부 tool-calling이 더 싸다)
- 보안 경계가 불명확한 상태에서 **STDIO 기반 로컬 실행**을 광범위하게 허용하려는 경우(아래 보안 섹션 참고)
- 에이전트가 수행하는 작업이 사실상 “원격 코드 실행”에 가까운데, 승인/감사/격리 계획이 없다면 MCP는 오히려 리스크를 표준화해 확산시킵니다(최근 RCE 이슈 논쟁 맥락). ([techradar.com](https://www.techradar.com/pro/security/this-is-not-a-traditional-coding-error-experts-flag-potentially-critical-security-issues-at-the-heart-of-anthropics-mcp-exposes-150-million-downloads-and-thousands-of-servers-to-complete-takeover?utm_source=openai))

---

## 🔧 핵심 개념
### 1) MCP에서의 서버가 의미하는 것: “도구 제공자 + 계약서”
MCP server는 보통 다음 3가지를 노출합니다. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/))
- **Tools**: 실행(action) — 네트워크 호출, 파일 수정, 티켓 생성 등 *side effect* 가능
- **Resources**: 읽기 전용 데이터 — 파일/문서/레코드 조회, 스키마 노출 등
- **Prompts**: 재사용 가능한 프롬프트 템플릿 — 팀 표준 운영절차(SOP) 같은 것

중요한 건 “도구를 몇 개 제공하느냐”보다 **도구 계약(입력 스키마, 출력 형태, 에러 모델, 권한 모델)**을 고정해 **에이전트가 예측 가능하게** 만드는 겁니다. TypeScript SDK가 `zod`를 peer dependency로 강제하는 것도 결국 “스키마를 코드로 고정”하려는 의도에 가깝습니다. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/))

### 2) Transport 선택이 곧 운영 모델
2026년 기준 실무에서 갈리는 지점이 여기입니다.

- **Streamable HTTP (권장, 원격 서버용)**  
  HTTP POST 기반 요청/응답 + (선택적으로) 서버→클라이언트 알림을 스트리밍(SSE 형태로)하는 “현대형” 전송 방식입니다. 세션/재개(resumability), JSON-only 모드 등 운영 옵션이 많습니다. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))
- **stdio (로컬 프로세스 스폰)**  
  Claude Desktop/IDE가 서버 프로세스를 직접 실행하고 stdin/stdout으로 JSON-RPC 메시지를 주고받습니다. 설정은 편하지만, **로컬 실행/권한 경계가 취약**해지기 쉬워서 “개발자 개인 머신” 외 영역으로 확장할 때 함정이 큽니다. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))
- **HTTP+SSE (deprecated)**  
  과거 호환용입니다. 신규 구현은 피하고, 레거시 클라이언트 때문에 필요한 경우에만 “겸용 서버” 형태로 두세요. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))

### 3) 내부 흐름(구조/흐름 관점)
실제 호출 플로우를 “운영 관점”으로 풀면:

1. **Client가 서버에 연결**(stdio면 프로세스 실행, HTTP면 endpoint 연결)
2. **Capability/Tool discovery**: client가 `listTools` 등으로 서버 계약을 읽음
3. 사용자의 목표가 들어오면, client(호스트 앱 내 에이전트 런타임)가  
   - 어떤 tool을 쓸지 결정하고  
   - 입력 스키마에 맞춰 인자를 만들고  
   - `callTool`을 수행
4. 서버는 tool 실행 결과를 **구조화된 형태**로 반환(텍스트/JSON/에러)
5. 필요하면 서버가 “장기 작업”을 task로 내보내거나(실험적), 클라이언트에 추가 입력을 요청(elicitation)할 수 있습니다. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/))

여기서 핵심 차별점은, LangChain류의 “라이브러리/프레임워크 결합”과 달리 MCP는 **프로세스/네트워크 경계를 가진 프로토콜**이라서, 보안·배포·버저닝을 “서비스처럼” 다룰 수 있다는 점입니다. 대신 그만큼 운영 부담도 생깁니다.

---

## 💻 실전 코드
아래는 “toy 예제” 대신, 실제 팀에서 바로 쓸 수 있는 **Agent 확장 서버** 시나리오로 구성합니다.

### 시나리오: “Change Request Gatekeeper” MCP Server
- 목적: 에이전트가 배포/릴리즈 관련 작업을 하려 할 때  
  1) 변경 요청(CR) 정보를 내부 API에서 조회하고  
  2) 정책(시간대/승인자/리스크 레벨)에 맞으면  
  3) 배포 파이프라인 API를 호출해 “승인된 배포”만 수행
- 포인트: **권한/감사/입력검증**을 서버에서 강제해 “에이전트가 마음대로 배포”하지 못하게 합니다.

구현은 TypeScript SDK + Streamable HTTP로 갑니다(원격 운영 전제). SDK가 Streamable HTTP를 권장합니다. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))

### 0) 의존성/프로젝트 셋업

```bash
mkdir mcp-change-gatekeeper && cd mcp-change-gatekeeper
npm init -y
npm install @modelcontextprotocol/sdk zod express
npm install -D tsx typescript @types/node @types/express
```

`package.json`에 실행 스크립트:

```json
{
  "type": "module",
  "scripts": {
    "dev": "tsx src/server.ts"
  }
}
```

### 1) 서버 구현 (Streamable HTTP + 정책 강제 + 감사 로그)

```typescript
// src/server.ts
import express from "express";
import crypto from "crypto";
import { z } from "zod";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js";

// (예시) 사내 API 호출 유틸 — 실제로는 fetch + mTLS/OAuth 등으로 바꾸세요.
async function callInternalApi<T>(path: string, opts?: { method?: string; body?: unknown }): Promise<T> {
  // 여기서는 데모를 위해 mock
  if (path.startsWith("/cr/")) {
    const id = path.split("/").pop();
    return {
      id,
      service: "payments",
      risk: "medium",
      approver: "oncall-lead",
      windowUtc: { start: "2026-06-13T16:00:00Z", end: "2026-06-13T20:00:00Z" }
    } as T;
  }
  if (path === "/deploy") {
    return { ok: true, deploymentId: "dep_" + crypto.randomBytes(6).toString("hex") } as T;
  }
  throw new Error(`Unknown API path: ${path}`);
}

const server = new McpServer({ name: "change-gatekeeper", version: "1.0.0" });

/**
 * Tool #1: get_change_request
 * - CR 정보를 리소스처럼 제공할 수도 있지만, 실제론 auth/감사/정책과 엮이므로 tool로 두는 편이 운영이 쉽습니다.
 */
server.tool(
  "get_change_request",
  "Fetch a Change Request by id (audited).",
  {
    crId: z.string().min(3),
  },
  async ({ crId }) => {
    const cr = await callInternalApi<any>(`/cr/${crId}`);
    return {
      content: [
        { type: "text", text: JSON.stringify(cr, null, 2) }
      ],
    };
  }
);

/**
 * Tool #2: approve_and_deploy
 * - 핵심: '배포'는 항상 위험한 side effect이므로, 입력값 검증 + 정책 체크 + 감사 ID를 강제합니다.
 */
server.tool(
  "approve_and_deploy",
  "Deploy a service if Change Request satisfies policy (enforced server-side).",
  {
    crId: z.string().min(3),
    gitSha: z.string().regex(/^[0-9a-f]{7,40}$/i),
    environment: z.enum(["staging", "prod"]),
    requestedBy: z.string().min(2), // 클라이언트/호스트가 채우되, 서버에서도 기록
  },
  async ({ crId, gitSha, environment, requestedBy }) => {
    const auditId = "audit_" + crypto.randomBytes(8).toString("hex");

    const cr = await callInternalApi<any>(`/cr/${crId}`);

    // 정책 예시 1) prod는 risk=low만 허용
    if (environment === "prod" && cr.risk !== "low") {
      return {
        isError: true,
        content: [
          { type: "text", text: `[${auditId}] Policy denied: prod deploy requires risk=low (got ${cr.risk})` }
        ]
      };
    }

    // 정책 예시 2) 승인자/윈도우 체크 (현실에선 캘린더/온콜/승인시스템과 연동)
    const now = new Date();
    const start = new Date(cr.windowUtc.start);
    const end = new Date(cr.windowUtc.end);
    if (!(now >= start && now <= end)) {
      return {
        isError: true,
        content: [
          { type: "text", text: `[${auditId}] Policy denied: outside change window (now=${now.toISOString()})` }
        ]
      };
    }

    // 실제 배포 호출
    const deployRes = await callInternalApi<any>("/deploy", {
      method: "POST",
      body: { service: cr.service, gitSha, environment, crId, requestedBy, auditId },
    });

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(
            { auditId, deployed: true, deployment: deployRes, policy: { environment, risk: cr.risk } },
            null,
            2
          ),
        },
      ],
    };
  }
);

// Express 앱: 문서에 나온 것처럼 createMcpExpressApp()은 localhost 바인딩 시 DNS rebinding 보호가 기본으로 걸립니다.
// 실서비스에서 무심코 0.0.0.0으로 열면 방어 기본값이 달라질 수 있으니 의도적으로 설정하세요. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))
const app = createMcpExpressApp({ host: "127.0.0.1" });
app.use(express.json());

// MCP 라우트 마운트 (SDK 제공 방식에 맞춰 연결)
app.use("/mcp", (req, res, next) => {
  // 여기서 사내 인증 헤더 검사(OAuth/JWT/mTLS) 등을 강제하세요.
  // 예: if (!req.header("authorization")) return res.status(401).end();
  next();
});

// connect: Streamable HTTP transport는 SDK 예제 기반으로 구성하는 것이 안전합니다(스펙 옵션이 많음).
// 여기서는 개념 전달을 위해 "Express app + server" 결합까지만 보여주고,
// 실제 연결 코드는 SDK 예제(simpleStreamableHttp.ts)를 복사해 시작하는 걸 권장합니다. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))

const PORT = process.env.PORT ? Number(process.env.PORT) : 8787;
app.listen(PORT, () => {
  // 운영에서는 stdout이 아니라 structured logger로 전환 권장
  console.log(`MCP server listening on http://127.0.0.1:${PORT}/mcp`);
});
```

### 2) (로컬) Claude/Claude Code에 붙이는 감각: config 관점
Claude 계열 클라이언트는 보통 `mcpServers`에 서버를 등록하는 방식이 널리 쓰입니다(예: Claude Desktop 설정 파일에 command/args를 넣는 형태). ([claudewave.com](https://claudewave.com/repo/agentify-sh-desktop?utm_source=openai))  
다만 **원격 Streamable HTTP**를 직접 붙일지, **로컬 stdio로 프로세스를 띄울지**는 클라이언트/제품별 제약이 있으니(특히 Desktop 제품군) “당장 내 클라이언트가 어떤 transport를 지원하는지”부터 확인하고 시작하세요.

### 예상 출력(성공/실패)
- `approve_and_deploy` 성공 시: `{ auditId, deployed: true, deploymentId... }`
- 정책 위반 시: `isError: true` + `[audit_xxx] Policy denied: ...`  
  → 이 `auditId`는 나중에 SIEM/감사로그에서 역추적 키가 됩니다(실무에서 정말 중요).

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “tool 계약”을 API가 아니라 **제품**처럼 버저닝하라
MCP server는 사실상 “에이전트용 백엔드 제품”입니다.  
- 입력 스키마(zod) 변경은 곧 breaking change  
- tool 이름 변경은 더 큰 breaking change  
- 응답 구조를 안정화하고, `version`을 운영 배포 단위로 관리하세요. (SDK가 스키마/타입 안전성을 강조하는 이유) ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/))

### Best Practice 2) side effect tool은 **서버에서 정책을 강제**하고, 클라이언트에 맡기지 마라
에이전트가 “배포해도 돼?”라고 물어보고 yes/no 받는 식(프롬프트 가드)은 쉽게 무너집니다.  
반드시 서버가:
- 시간창, 승인자, 리스크 레벨, 환경(prod/staging) 같은 정책을 체크
- 감사 ID 발급
- 최소 권한(토큰 스코프/리소스 범위)을 강제  
이게 MCP로 “확장”할 때의 핵심 가치입니다.

### Best Practice 3) Transport 선택의 트레이드오프를 명시적으로
- stdio: 설정 쉬움 / 하지만 로컬 실행 경계가 곧 보안 경계가 됨  
- Streamable HTTP: 운영 복잡 / 대신 인증·레이트리밋·관측성·네트워크 격리가 가능

최근 MCP/SDK 설계와 관련된 **RCE 위험**이 보안 이슈로 크게 다뤄졌습니다. 요지는 “에이전트가 연결한 도구(또는 로컬 실행 경로)가 공격 표면이 된다”는 점입니다. 따라서 STDIO 기반 로컬 서버를 무제한으로 붙이는 운영은 특히 조심해야 합니다. ([techradar.com](https://www.techradar.com/pro/security/this-is-not-a-traditional-coding-error-experts-flag-potentially-critical-security-issues-at-the-heart-of-anthropics-mcp-exposes-150-million-downloads-and-thousands-of-servers-to-complete-takeover?utm_source=openai))

### 흔한 함정/안티패턴
- **하나의 tool에 모든 기능을 몰아넣기**: `run_shell(command: string)` 같은 만능 도구는 운영/감사/권한 분리가 불가능
- **0.0.0.0 바인딩 + 인증 없음**: 특히 localhost 서비스는 DNS rebinding 같은 클래스의 공격을 고려해야 합니다(SDK 문서도 이를 직접 언급). ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))
- **에러를 텍스트로만 반환**: 에이전트는 구조화된 실패를 더 잘 처리합니다(예: `code`, `retryable`, `auditId`)

### 비용/성능/안정성 트레이드오프
- Streamable HTTP는 “세션/재개/스트리밍” 옵션이 많아 강력하지만, 그만큼 운영 포인트가 늘어납니다. 단순 CRUD성 도구면 **stateless + JSON-only**가 오히려 안정적일 수 있습니다. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))
- tool 호출은 결국 네트워크 hop을 추가합니다. 내부 API를 여러 번 호출하는 tool은 **서버에서 캐시/배치**를 고려해야 합니다(에이전트가 같은 정보를 반복 조회하는 패턴이 흔함).

---

## 🚀 마무리
정리하면, MCP server 구축의 본질은 “LLM을 똑똑하게”가 아니라 **도구를 제품화(계약/정책/감사/운영)**하는 데 있습니다. 2026년 기준으로는:
- 신규 구현은 **Streamable HTTP**를 중심으로 설계하고(권장 transport), ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))
- side effect tool은 **서버에서 정책을 강제**하며,
- stdio 기반 로컬 실행 확장은 보안 관점에서 특히 보수적으로 접근하는 게 맞습니다(최근 RCE 논쟁이 이를 재확인). ([techradar.com](https://www.techradar.com/pro/security/this-is-not-a-traditional-coding-error-experts-flag-potentially-critical-security-issues-at-the-heart-of-anthropics-mcp-exposes-150-million-downloads-and-thousands-of-servers-to-complete-takeover?utm_source=openai))

**도입 판단 기준**
- “에이전트가 회사 시스템을 건드린다” → MCP server로 계약/정책/감사를 강제할 가치가 큼
- “그냥 개인 자동화” → stdio로 빠르게 시작하되, 배포/공유 단계에서 Streamable HTTP + 인증으로 재설계할 계획을 세워라

**다음 학습 추천**
- MCP TypeScript SDK의 서버 문서에서 **stateless/stateful, JSON-only, DNS rebinding 보호** 섹션을 실제 운영 체크리스트처럼 읽어보세요. ([ts.sdk.modelcontextprotocol.io](https://ts.sdk.modelcontextprotocol.io/documents/server.html))
- Claude 쪽에서 MCP를 붙이는 방식(Agent SDK/Claude Code 설정)도 함께 확인해 “내 클라이언트가 어떤 transport/인증 흐름을 지원하는지”를 초기에 고정하세요. ([anthropic.mintlify.app](https://anthropic.mintlify.app/en/docs/agent-sdk/mcp?utm_source=openai))

원하면 다음 단계로, 위 예제를 **(1) OAuth/JWT 인증 미들웨어**, **(2) tool별 rate limit**, **(3) OpenTelemetry 기반 tracing**, **(4) downstream MCP 서버들을 묶는 mediator 패턴**까지 확장한 “운영형 템플릿”으로 이어서 작성해드릴게요.