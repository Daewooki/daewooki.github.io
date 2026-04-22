---
title: "2026년 4월, Claude용 MCP 서버를 “에이전트 확장 서버”로 제대로 구현하는 법: Streamable HTTP, 버전 호환, 그리고 보안까지"
date: 2026-04-22 03:30:37 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-04]
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
Model Context Protocol(MCP)은 LLM/에이전트가 “외부 세계(데이터/액션)”와 연결되는 표준 인터페이스입니다. 팀마다 GitHub/DB/사내 API/배포 시스템을 각기 다른 방식으로 붙이던 N×M 통합 지옥을, **서버(툴 제공자)–클라이언트(에이전트/IDE)** 구조로 평탄화합니다. Anthropic은 Claude Desktop/Claude Code/Claude.ai에서 MCP를 공식 지원하고 있고, GitHub Copilot SDK나 OpenAI Agents SDK도 MCP 연결을 문서화하기 시작하면서(=클라이언트 다양화) “한 번 서버를 잘 만들면 여러 호스트에서 재사용”이 현실이 됐습니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/mcp?utm_source=openai))

언제 쓰면 좋은가:
- **에이전트가 사내 시스템을 반복 호출**(티켓 조회/배포 승인/런북 실행/로그 검색)해야 하고, 호출 정책·감사·권한을 **서버에서 통제**하고 싶을 때
- IDE/CLI(Claude Code, Cursor, Copilot 등)에서 동일한 툴셋을 공유하고 싶을 때(“사내 Tool API”의 표준화)

언제 쓰면 안 되는가:
- 단발성 스크립트 수준(직접 API 호출이 더 단순)
- “모델이 곧바로 prod 권한을 가져야만” 하는 설계(보안·감사·오남용 리스크가 너무 큼). 2026년 4월 기준 MCP 생태계는 **tool poisoning / prompt injection / 서버 구현 결함** 이슈가 계속 보고되고 있어, 권한 경계 설계를 먼저 해야 합니다. ([techradar.com](https://www.techradar.com/pro/security/this-is-not-a-traditional-coding-error-experts-flag-potentially-critical-security-issues-at-the-heart-of-anthropics-mcp-exposes-150-million-downloads-and-thousands-of-servers-to-complete-takeover?utm_source=openai))

---

## 🔧 핵심 개념
### 1) MCP에서 말하는 “서버”는 무엇인가
MCP server는 크게 3가지를 노출합니다.
- **tools**: 실행 가능한 함수(액션). 예: `deploy_service`, `search_logs`
- **resources**: 읽기 중심의 데이터 핸들(문서/DB/파일)
- **prompts**: 재사용 가능한 프롬프트 템플릿(조직 표준 운영 절차 등)

호스트(Claude Desktop/Claude Code/Copilot SDK 등)는 MCP server에 붙고, 모델은 “필요 시 tool 호출” 형태로 외부 액션을 실행합니다. 이때 중요한 점은 **모델이 직접 네트워크/DB를 치는 게 아니라, 서버가 계약(contract)과 정책을 강제**한다는 점입니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/mcp?utm_source=openai))

### 2) Transport: stdio vs (Remote) HTTP 계열
- **stdio transport**: 호스트가 로컬에서 서버 프로세스를 spawn하고 stdin/stdout으로 통신. Claude Desktop의 전통적 방식(로컬 도구에 강함). ([thymer.com](https://thymer.com/mcp?utm_source=openai))
- **HTTP+SSE(legacy)** → **Streamable HTTP(권장)**: 원격 서버 연결을 위해 등장. Streamable HTTP는 기존 SSE 방식의 “긴 연결 유지/리줌 어려움” 문제를 줄이고, 더 단순한 HTTP 구현을 목표로 합니다. TypeScript SDK는 Streamable HTTP와 구형 SSE를 **호환 모드로 병행**하는 예시를 제공합니다. ([reddit.com](https://www.reddit.com/r/modelcontextprotocol/comments/1jhhokc?utm_source=openai))

실무 판단:
- “개발자 PC에서만” 돌아야 하는 보안 경계(예: 로컬 소스 트리 접근)면 **stdio**
- 여러 클라이언트가 공유하는 사내 서비스(예: 배포/티켓/관측)면 **Streamable HTTP** + 강한 AuthN/AuthZ + Audit

### 3) 버전(프로토콜/SDK) 호환이 실제로 발목 잡는다
클라이언트가 MCP 프로토콜 버전을 올리면(예: Claude Code 업데이트) **구형 SDK 기반 서버가 연결 실패**하는 사례가 커뮤니티에서 반복 보고됩니다. 운영 서버라면 “서버가 지원하는 protocol version을 로그로 노출”하고, 배포 파이프라인에 “연결 통합 테스트”를 넣는 게 현실적입니다. ([reddit.com](https://www.reddit.com/r/mcp/comments/1qvqh04/mcpcppserver_broken_after_claude_code_2128_update/?utm_source=openai))

### 4) 다른 접근과의 차이점(왜 MCP인가)
- 단순 “function calling”은 특정 벤더 API에 종속되기 쉽고, 각 에이전트/IDE마다 래핑이 중복됩니다.
- MCP는 **툴 디스커버리 + 표준 메시지 계약 + transport 추상화**까지 포함해, “사내 Tool Platform”을 만들 때 재사용성이 큽니다. (LSP가 IDE 플러그인을 표준화했던 것과 비슷한 포지션) ([docs.anthropic.com](https://docs.anthropic.com/en/docs/mcp?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: “배포 승인/실행”을 MCP tool로 만들되,
- 모델이 임의 환경(prod) 배포를 못 하게 **정책을 서버에서 강제**
- 실행은 비동기(Job)로 돌리고, 상태 조회 tool 제공
- **stdio(로컬)** + **Streamable HTTP(원격)** 둘 다 제공(개발/운영 분리)

아래 예시는 **TypeScript 기반 MCP 서버(Express) + Streamable HTTP** 형태로 작성합니다. (SDK 문서에 Streamable HTTP transport가 명시되어 있고, SSE 레거시와의 병행 패턴도 제공됩니다.) ([github.com](https://github.com/julibuilds/mcp-typescript-sdk?utm_source=openai))

### 0) 의존성/프로젝트 구성
```bash
mkdir mcp-deploy-server && cd mcp-deploy-server
npm init -y
npm i express zod
npm i @modelcontextprotocol/sdk
npm i -D typescript ts-node @types/node @types/express
npx tsc --init
```

### 1) 서버: “안전한 배포” 도구 구현 (Streamable HTTP)
- `deploy_request`: 배포 요청 생성(승인 워크플로우/정책 체크 포함)
- `deploy_status`: 상태 조회
- 핵심은 “모델이 보낸 문자열”을 그대로 shell로 넘기지 않고, **허용된 서비스/환경/버전만** 받도록 강제하는 것

```typescript
// src/server.ts
import express from "express";
import { z } from "zod";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

// ---- 현실적인 정책 예시 ----
const AllowedEnv = z.enum(["staging", "prod"]);
const AllowedService = z.enum(["billing-api", "web-frontend", "worker"]);
const SemverLike = z.string().regex(/^\d+\.\d+\.\d+(-[a-z0-9.]+)?$/i);

type JobState = "PENDING_APPROVAL" | "RUNNING" | "SUCCEEDED" | "FAILED" | "REJECTED";

const deployRequestSchema = z.object({
  service: AllowedService,
  env: AllowedEnv,
  version: SemverLike,
  changeTicket: z.string().min(5), // JIRA/Linear 등
  reason: z.string().min(10),
});

const jobs = new Map<string, { state: JobState; createdAt: number; detail?: string }>();

function newJobId() {
  return `dep_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

// 실제로는 사내 CD 시스템(ArgoCD/Spinnaker/GitHub Actions 등) API 호출.
// 여기서는 “비동기 job” 형태만 유지.
async function startDeployment(jobId: string) {
  jobs.set(jobId, { state: "RUNNING", createdAt: Date.now() });

  // 예: await fetch("https://cd.internal/deploy", ...)
  await new Promise((r) => setTimeout(r, 1500));

  jobs.set(jobId, { state: "SUCCEEDED", createdAt: Date.now(), detail: "Rolled out to 3/3 pods" });
}

async function main() {
  const mcp = new McpServer({ name: "deploy-control", version: "1.0.0" });

  // Tool 1) 배포 요청
  mcp.tool(
    "deploy_request",
    "Request a deployment with policy checks and approval gate. Never executes arbitrary commands.",
    deployRequestSchema.shape,
    async (args) => {
      const parsed = deployRequestSchema.parse(args);

      // ---- 정책: prod 배포는 티켓이 'PROD-'로 시작해야 한다(예시) ----
      if (parsed.env === "prod" && !parsed.changeTicket.startsWith("PROD-")) {
        return {
          content: [
            {
              type: "text",
              text:
                `REJECTED: prod deployments require changeTicket starting with 'PROD-'. ` +
                `Got: ${parsed.changeTicket}`,
            },
          ],
          isError: true,
        };
      }

      const jobId = newJobId();
      jobs.set(jobId, { state: "PENDING_APPROVAL", createdAt: Date.now() });

      // ---- 승인: 실제라면 Slack/Teams 승인, OPA/IGA 연동 등 ----
      // 여기선 데모로 staging은 자동 승인, prod는 수동 승인 필요로 둠.
      if (parsed.env === "staging") {
        // 자동 실행
        void startDeployment(jobId);
      } else {
        jobs.set(jobId, { state: "PENDING_APPROVAL", createdAt: Date.now(), detail: "Waiting for human approval" });
      }

      return {
        content: [
          {
            type: "text",
            text:
              `Deployment job created.\n` +
              `jobId=${jobId}\nservice=${parsed.service}\nenv=${parsed.env}\nversion=${parsed.version}\n` +
              `state=${jobs.get(jobId)!.state}`,
          },
        ],
      };
    }
  );

  // Tool 2) 상태 조회
  mcp.tool(
    "deploy_status",
    "Get status of a deployment job.",
    { jobId: z.string().min(1) },
    async ({ jobId }) => {
      const job = jobs.get(jobId);
      if (!job) {
        return {
          content: [{ type: "text", text: `Not found: ${jobId}` }],
          isError: true,
        };
      }
      return {
        content: [
          {
            type: "text",
            text: `jobId=${jobId}\nstate=${job.state}\ndetail=${job.detail ?? ""}`,
          },
        ],
      };
    }
  );

  // ---- Streamable HTTP endpoint ----
  const app = express();
  app.use(express.json());

  // MCP transport를 라우팅에 연결 (SDK 패턴에 맞춰 구현)
  const transport = new StreamableHTTPServerTransport({ endpoint: "/mcp" });
  await mcp.connect(transport);

  app.use("/mcp", transport.createExpressRouter());

  const port = process.env.PORT ? Number(process.env.PORT) : 8787;
  app.listen(port, () => {
    console.log(`[mcp] deploy-control listening on :${port}`);
    console.log(`[mcp] endpoint: http://127.0.0.1:${port}/mcp`);
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

실행:
```bash
npx ts-node src/server.ts
```

예상 출력:
```text
[mcp] deploy-control listening on :8787
[mcp] endpoint: http://127.0.0.1:8787/mcp
```

### 2) Claude Code에 연결(원격/HTTP)
Claude Code 문서에는 MCP 서버를 HTTP로 추가하는 CLI 예시가 있습니다. (조직 환경에서는 OAuth 설정까지 같이 붙는 패턴이 일반적) ([code.claude.com](https://code.claude.com/docs/en/mcp?utm_source=openai))

```bash
# 예시(개념): 로컬에서 돌지만 transport는 HTTP
claude mcp add-json deploy-control '{
  "type":"http",
  "url":"http://127.0.0.1:8787/mcp"
}'
claude mcp list
```

### 3) Claude Desktop(stdio 중심)과의 “현실적” 공존
Claude Desktop은 전통적으로 stdio 기반 설정(JSON에 command/args) 패턴이 많이 쓰였고, 제품/플랜에 따라 remote 지원이 “beta”로 언급됩니다. 즉, 조직 배포는 HTTP로 가더라도 데스크톱 사용자를 위해 **stdio wrapper(또는 mcp-remote류 브리지)** 를 두는 구성이 자주 나옵니다. ([thymer.com](https://thymer.com/mcp?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Tool contract를 “문자열”이 아니라 “스키마”로 잠가라**  
   위 코드처럼 zod로 `service/env/version`을 제한하면, prompt injection으로 “prod에 최신 main을 배포해” 같은 자연어가 들어와도 서버가 구조적으로 거부할 수 있습니다. (MCP 보안 이슈의 상당수는 “모델이 하라는 대로 툴이 너무 많은 권한으로 실행”에서 시작합니다.) ([arxiv.org](https://arxiv.org/abs/2603.22489?utm_source=openai))

2) **권한 경계를 ‘호스트(클라이언트)’가 아니라 ‘서버’에서 강제**  
   “클라이언트가 조심하겠지”는 깨집니다. 2026년 4월에도 MCP 관련 취약점/설계 논쟁이 계속되고 있고, tool chaining으로 RCE까지 이어질 수 있다는 보고가 반복됩니다. ([techradar.com](https://www.techradar.com/pro/security/anthropics-official-git-mcp-server-had-some-worrying-security-flaws-this-is-what-happened-next?utm_source=openai))

3) **버전/호환성: Streamable HTTP 우선 + 레거시 SSE 폴백 전략**  
   TS SDK는 Streamable HTTP 연결 실패 시 SSE로 폴백하는 예시를 공식적으로 제공합니다. 서버도 (필요하면) 구형 클라이언트를 위해 병행 제공을 고려하세요. ([github.com](https://github.com/julibuilds/mcp-typescript-sdk?utm_source=openai))

### 흔한 함정/안티패턴
- **“shell tool” 남발**: `exec("kubectl ...")` 같은 범용 실행 툴은 에이전트 확장 서버가 아니라 “RCE as a Service”가 됩니다.
- **tool description(메타데이터)에 운영 지침을 길게 써서 모델에 기대기**: tool poisoning(툴 설명/메타에 숨은 지시) 계열 리스크가 지적되어 왔습니다. 설명은 짧고, 정책은 코드로. ([vulnerablemcp.info](https://vulnerablemcp.info/vuln/tool-poisoning-attacks.html?utm_source=openai))
- **관측성 부재**: “왜 모델이 이 툴을 호출했는지/무슨 인자를 넣었는지/실패율”이 없으면 운영이 불가능합니다. (최근 연구/현업 체크리스트들도 이 부분을 반복 강조) ([arxiv.org](https://arxiv.org/abs/2603.13417?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- stdio는 로컬에서 빠르고 단순하지만, 사용자 PC 의존/배포 난이도가 올라갑니다.
- 원격(Streamable HTTP)은 공유/통제가 쉽지만, **AuthN/Z·레이트리밋·감사로그**를 갖춘 “미니 플랫폼”이 됩니다(초기 비용↑, 운영 안정성↑).
- 보안은 “추가 옵션”이 아니라 **프로토콜 사용 순간 필수 비용**으로 잡아야 합니다(최근 공개된 취약점/설계 비판 이슈들을 보면 더더욱). ([techradar.com](https://www.techradar.com/pro/security/this-is-not-a-traditional-coding-error-experts-flag-potentially-critical-security-issues-at-the-heart-of-anthropics-mcp-exposes-150-million-downloads-and-thousands-of-servers-to-complete-takeover?utm_source=openai))

---

## 🚀 마무리
핵심은 이겁니다: MCP server는 “Claude에 기능을 붙이는 플러그인”이 아니라, **에이전트의 실행 권한을 캡슐화하는 서버**입니다. 그래서 구현 포인트도 “툴을 몇 개 제공하느냐”보다 **(1) 스키마로 입력을 제한하고 (2) 서버에서 정책/권한을 강제하고 (3) transport/버전 호환과 운영(로그·감사·테스트)을 갖추는지**가 도입 성패를 가릅니다. ([code.claude.com](https://code.claude.com/docs/en/mcp?utm_source=openai))

도입 판단 기준(체크리스트):
- 이 툴이 없으면 사람이 하던 “반복 실행/조회”가 명확히 존재하는가?
- 그 작업이 **정형화된 입력 스키마**로 떨어지는가? (안 떨어지면 위험 신호)
- 서버에서 AuthZ/승인/감사를 강제할 수 있는가?
- Claude Desktop/Claude Code/IDE 등 다중 클라이언트까지 염두에 두고 transport 전략이 있는가?

다음 학습 추천:
- Streamable HTTP로의 마이그레이션/호환 전략(공식 TS SDK 패턴) ([github.com](https://github.com/julibuilds/mcp-typescript-sdk?utm_source=openai))
- MCP 보안(특히 tool poisoning / 간접 prompt injection) 관련 연구·가이드 ([arxiv.org](https://arxiv.org/abs/2603.22489?utm_source=openai))
- Claude Code의 MCP 설정/운영 문서(서버 추가, OAuth 포함) ([code.claude.com](https://code.claude.com/docs/en/mcp?utm_source=openai))