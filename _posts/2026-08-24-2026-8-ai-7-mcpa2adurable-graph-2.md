---
title: "2026년 8월, “에이전트가 운영되는” AI 앱 아키텍처 패턴 7가지: MCP·A2A·Durable Graph로 확장성과 안정성을 동시에 잡는 법"
date: 2026-08-24 01:47:37 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-08]
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
2026년 8월 기준 AI 애플리케이션의 병목은 “모델 성능”보다 **운영 가능한 아키텍처**에서 더 자주 터집니다. 특히 (1) tool 호출이 늘어나고, (2) 장기 실행(long-running) 작업이 생기고, (3) 멀티 에이전트가 도입되면서, 단순한 request/response 서버 구조는 금방 한계가 옵니다. MCP의 로드맵에서도 “agentic workload는 표준 request-and-response 패턴에 더 이상 맞지 않는다”는 문제의식이 명시되어 있고, 이를 위해 stateless core/Tasks/Extensions 같은 방향으로 진화 중입니다. ([blog.modelcontextprotocol.io](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/?utm_source=openai))

**언제 쓰면 좋나**
- AI 기능이 “부가 기능”이 아니라 제품의 핵심 플로우이며, tool/data 연동이 많은 경우
- 사용자 수/조직 수(멀티테넌시)가 늘어날 예정이고, 장애 격리가 중요한 경우
- HITL(Human-in-the-loop), 승인/감사(audit), 재시도, 관측성(Observability)이 요구되는 경우 ([langchain.com](https://www.langchain.com/blog/runtime-behind-production-deep-agents?utm_source=openai))

**언제 쓰면 안 되나**
- 단일 모델 호출 + 간단한 DB 조회 정도의 “짧고 결정론적인” 작업만 있는 서비스
- 운영팀/플랫폼 성숙도가 낮아 분산 컴포넌트가 오히려 장애 원인이 되는 단계(초기 MVP)
- 규정/보안 요구가 낮은데도 멀티 에이전트로 과설계하는 경우(비용·복잡도 폭증)

---

## 🔧 핵심 개념
아래는 2026년 8월 관점에서 “확장 가능한 AI 앱”에서 반복적으로 등장하는 설계 패턴을 **프로토콜(MCP/A2A) + 런타임(Durable Execution) + 시스템 디자인(격리/확장)**으로 묶어 설명한 것입니다.

### 1) **Stateless Tool/Context Gateway (MCP 기반)**
MCP는 기본적으로 **client-host-server** 구조를 따르며, host가 여러 client 인스턴스를 실행할 수 있는 형태로 정의됩니다. ([modelcontextprotocol.io](https://modelcontextprotocol.io/specification/2025-06-18/architecture?utm_source=openai))  
2026-07-28 RC에서 강조되는 핵심은 “**stateless core**”와 “Tasks/Extensions”로, 원격 MCP 서버를 “일반 HTTP workload처럼” 운영 가능하게 만드는 방향입니다. ([blog.modelcontextprotocol.io](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/?utm_source=openai))

- **정의**: LLM/Agent가 접근해야 하는 tool/data를 *세션 상태에 의존하지 않고* 호출하도록, Gateway를 둔다.
- **내부 흐름**
  1) Agent가 tool 호출 의도를 생성
  2) MCP Gateway가 authz/quotas/validation 수행
  3) 실제 백엔드(검색, 결제, 티켓, CRM 등) 호출 후 결과를 표준 형태로 반환
- **차이점**: “프롬프트에서 직접 API 호출” vs “MCP로 tool 인터페이스를 표준화/격리”
- **트레이드오프**: Stateless는 운영·스케일에는 유리하지만, 대화/작업 문맥은 **외부 저장소(threads/runs/state store)**로 명시적으로 빼야 합니다(구현 난이도 상승).

### 2) **Proxy Aggregator / Domain Adapter (MCP 서버 패턴)**
MCP 서버는 도메인별로 늘어나기 쉽고, 그 결과 “tool sprawl(도구 난립)”이 생깁니다. 이를 해결하는 반복 패턴이 **Aggregator/Adapter**입니다. (실무/산업 경험 기반으로 MCP 서버 패턴들을 분류한 자료도 등장했습니다.) ([arxiv.org](https://arxiv.org/abs/2606.30317?utm_source=openai))

- **Proxy Aggregator**: 여러 MCP 서버를 하나로 묶어 라우팅/권한/관측을 중앙화
- **Domain Adapter**: 사내 레거시(예: SOAP/메인프레임/사내 RPC)를 MCP tool로 “번역”하는 얇은 계층
- **핵심 포인트**: “LLM이 이해하는 계약(스키마)”과 “내부 시스템 계약”을 분리해 변경 비용을 낮춤

### 3) **Durable Execution Graph (LangGraph 계열)**
프로덕션 에이전트는 중간에 멈추고(resume), 재시도하고, 사람 승인을 기다리고, 관측돼야 합니다. LangChain 쪽에서도 장기 실행 에이전트를 배포하려면 durable execution/체크포인트/멀티테넌시/HITL/observability가 필요하다고 정리합니다. ([langchain.com](https://www.langchain.com/blog/runtime-behind-production-deep-agents?utm_source=openai))  
LangGraph는 breakpoints/HITL를 `interrupt`로 단순화하는 패턴을 권장합니다. ([github.com](https://github.com/langchain-ai/langgraphjs/blob/main/docs/docs/concepts/human_in_the_loop.md?utm_source=openai))

- **정의**: 에이전트 플로우를 “함수 체인”이 아니라 **상태 머신/그래프**로 모델링하고, 각 스텝을 저장해 재개 가능하게 만든다.
- **왜 중요한가**: LLM 호출은 비결정적이고 비용이 크며, 외부 tool은 실패한다. “재현 가능한 실행”이 곧 비용·신뢰성을 좌우.

### 4) **HITL as a First-class Node (승인을 ‘끝’이 아니라 ‘중간’에 배치)**
실무에서 흔한 실패는 “마지막에 approve 버튼”을 붙여놓고, 그 전에 이미 위험한 tool 호출/데이터 변형을 해버리는 겁니다. LangGraph는 tool call을 실행 전에 사람이 검토/수정/승인하는 흐름을 공식 개념으로 설명합니다. ([github.com](https://github.com/langchain-ai/langgraphjs/blob/main/docs/docs/concepts/human_in_the_loop.md?utm_source=openai))

- **패턴**: (a) 계획/도구 선택 → (b) 사람 검토 → (c) 실행 → (d) 결과 검증
- **효과**: 감사 가능성, 사고 방지, 규정 준수(특히 티켓 생성/권한 변경/비용 집행)

### 5) **Agent-to-Agent Interop (A2A)**
멀티 에이전트가 늘면서 “에이전트 간 통신 표준”이 필요해졌고, Google이 만든 A2A는 독립적인(opaque) 에이전트들 간 상호운용을 목표로 한 오픈 프로토콜로 소개됩니다. ([developers.googleblog.com](https://developers.googleblog.com/a2a-a-new-era-of-agent-interoperability/?utm_source=openai))  
Google Cloud 문서에서도 서로 다른 프레임워크/벤더/서버에서 돌아가는 에이전트 간 통신을 목표로 한다고 명시합니다. ([docs.cloud.google.com](https://docs.cloud.google.com/run/docs/ai/a2a-agents?authuser=19&hl=en&utm_source=openai))  
또한 2026년 8월 기사에서는 A2A가 새로운 재단으로 옮겨가며 표준화가 진전되는 흐름이 언급됩니다. ([axios.com](https://www.axios.com/2026/08/17/a2a-agentic-ai-foundation-open-ai-standards?utm_source=openai))

- **정의**: “내 서비스 내부 모듈”이 아니라 **외부/타팀/타벤더 에이전트**를 안전하게 호출하는 표준 레이어
- **내부 흐름(개념)**: client agent가 remote agent(A2A server)에 task를 보내고 결과를 받는 형태
- **차이점**: 내부 마이크로서비스 RPC vs “에이전트 호출”은 입력/출력이 훨씬 비정형이고, 중간 상태/진행률/재시도 모델이 중요

### 6) **Async Task Boundary (Tasks/send + Queue + Idempotency)**
A2A 예시/문서에서는 `message/send` 같은 동기 패턴 외에도 `tasks/send`, `tasks/get` 같은 task 기반 메서드가 언급됩니다. ([developers.googleblog.com](https://developers.googleblog.com/build-cross-language-multi-agent-team-with-google-agent-development-kit-and-a2a/?utm_source=openai))  
이건 아키텍처적으로 “LLM 요청을 동기 API로 끝내지 말고, **작업 경계**를 분리하라”는 신호입니다.

- **패턴**: API 요청 → task 생성 → 워커 실행 → 결과 저장 → 폴링/웹훅/스트림으로 전달
- **핵심**: Idempotency key(중복 실행 방지), 비용 상한(guardrail), 부분 실패 재시도 전략

### 7) **Observability & Policy Gate (LLM 호출을 ‘비용 청구되는 외부 의존성’으로 취급)**
Durable runtime이 강조하는 요소 중 하나가 observability이고 ([langchain.com](https://www.langchain.com/blog/runtime-behind-production-deep-agents?utm_source=openai)), MCP/A2A 모두 “엔터프라이즈 운영”을 전제로 보안/인증/운영성을 강화하는 방향입니다. ([developers.googleblog.com](https://developers.googleblog.com/a2a-a-new-era-of-agent-interoperability/?utm_source=openai))  
따라서 LLM 호출/툴 호출을 **APM/로그/트레이싱/정책 엔진**으로 감싸는 게 확장성의 전제조건이 됩니다.

---

## 💻 실전 코드
현실적인 시나리오: **B2B SaaS의 “인시던트 대응 에이전트”**  
- 사용자는 Slack/웹에서 “장애 의심”을 입력
- 에이전트는 (1) 로그 검색, (2) 변경 이력 조회, (3) 롤백/티켓 생성 같은 tool을 호출하려고 함
- 위험한 작업(롤백/권한 변경)은 **HITL 승인 후** 실행
- 장기 실행이므로 **Durable Execution + Async Task**로 처리
- tool 인터페이스는 **MCP Server**로 표준화(내부 시스템 변경에도 에이전트 계약 유지)

아래 예시는 “MCP Tool Gateway + Durable workflow + HITL”를 한 서비스 안에서 최소 구성으로 보여줍니다.

### 1) 초기 셋업 (의존성/환경)
```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn httpx pydantic sqlalchemy aiosqlite
```

### 2) MCP 스타일 Tool Gateway (FastAPI) + 정책/승인 게이트
```python
# app.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import asyncio
import time
import uuid

app = FastAPI()

# --- In-memory stores (데모용). 실무에선 Redis/Postgres로 교체 ---
TASKS: dict[str, dict] = {}
APPROVALS: dict[str, dict] = {}

RISKY_TOOLS = {"rollback_deploy", "rotate_api_key", "close_incident"}

class ToolCall(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    actor: str  # tenant/user/service id
    idempotency_key: str | None = None

class TaskHandle(BaseModel):
    task_id: str

class TaskStatus(BaseModel):
    task_id: str
    status: str  # PENDING/RUNNING/WAITING_APPROVAL/SUCCEEDED/FAILED
    result: dict | None = None
    error: str | None = None

class ApprovalRequest(BaseModel):
    task_id: str
    summary: str
    proposed_tool: ToolCall

class ApprovalDecision(BaseModel):
    approve: bool
    editor_notes: str | None = None

def policy_check(call: ToolCall) -> None:
    # 예: 테넌트별 비용 상한, 허용 tool, 시간대 제한, RBAC 등
    if call.tool == "rotate_api_key" and call.actor != "oncall-admin":
        raise HTTPException(status_code=403, detail="Not allowed by policy")

async def execute_tool(call: ToolCall) -> dict:
    # 현실 코드라면 여기서 실제 로그 플랫폼/배포 시스템/티켓 시스템 호출
    await asyncio.sleep(0.3)

    if call.tool == "search_logs":
        q = call.args.get("query", "")
        return {"hits": 42, "top": f"error: timeout while calling payments (query={q})"}
    if call.tool == "get_recent_deploys":
        return {"deploys": [{"sha": "a1b2c3", "time": int(time.time()) - 1800}]}
    if call.tool == "rollback_deploy":
        env = call.args.get("env", "prod")
        return {"rollback": "started", "env": env, "ticket": f"CHG-{uuid.uuid4().hex[:8]}"}

    raise HTTPException(status_code=404, detail="Unknown tool")

@app.post("/tasks/send", response_model=TaskHandle)
async def tasks_send(call: ToolCall):
    policy_check(call)

    task_id = uuid.uuid4().hex
    TASKS[task_id] = {"status": "PENDING", "result": None, "error": None, "call": call.model_dump()}

    # 위험 tool은 바로 실행하지 않고 승인 대기 상태로 전환
    if call.tool in RISKY_TOOLS:
        TASKS[task_id]["status"] = "WAITING_APPROVAL"
        APPROVALS[task_id] = {
            "summary": f"Risky tool '{call.tool}' requested with args={call.args}",
            "approved": None,
            "notes": None,
        }
        return TaskHandle(task_id=task_id)

    # 안전 tool은 비동기 실행
    asyncio.create_task(_run_task(task_id))
    return TaskHandle(task_id=task_id)

async def _run_task(task_id: str):
    TASKS[task_id]["status"] = "RUNNING"
    call = ToolCall(**TASKS[task_id]["call"])
    try:
        result = await execute_tool(call)
        TASKS[task_id]["status"] = "SUCCEEDED"
        TASKS[task_id]["result"] = result
    except Exception as e:
        TASKS[task_id]["status"] = "FAILED"
        TASKS[task_id]["error"] = str(e)

@app.get("/tasks/get", response_model=TaskStatus)
async def tasks_get(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="task not found")
    t = TASKS[task_id]
    return TaskStatus(task_id=task_id, status=t["status"], result=t["result"], error=t["error"])

@app.get("/approvals/get", response_model=ApprovalRequest)
async def approvals_get(task_id: str):
    if task_id not in APPROVALS:
        raise HTTPException(status_code=404, detail="approval not found")
    t = TASKS[task_id]
    a = APPROVALS[task_id]
    return ApprovalRequest(
        task_id=task_id,
        summary=a["summary"],
        proposed_tool=ToolCall(**t["call"])
    )

@app.post("/approvals/decide")
async def approvals_decide(task_id: str, decision: ApprovalDecision):
    if task_id not in APPROVALS:
        raise HTTPException(status_code=404, detail="approval not found")
    APPROVALS[task_id]["approved"] = decision.approve
    APPROVALS[task_id]["notes"] = decision.editor_notes

    if not decision.approve:
        TASKS[task_id]["status"] = "FAILED"
        TASKS[task_id]["error"] = "Rejected by human"
        return {"ok": True, "status": "REJECTED"}

    # 승인되면 실행
    asyncio.create_task(_run_task(task_id))
    return {"ok": True, "status": "APPROVED"}
```

실행:
```bash
uvicorn app:app --reload --port 8000
```

### 3) 에이전트(또는 오케스트레이터) 측: “계획 → tool 호출 → 승인 대기 → 재개”
아래는 LLM이 만든 tool call을 받았다고 가정하고, **tasks/send → tasks/get**으로 상태를 추적합니다. (A2A 문서/예시에서 언급되는 task 기반 상호작용 감각과 동일합니다.) ([developers.googleblog.com](https://developers.googleblog.com/build-cross-language-multi-agent-team-with-google-agent-development-kit-and-a2a/?utm_source=openai))

```python
# orchestrator.py
import time
import httpx

BASE = "http://localhost:8000"

def send_tool(tool: str, args: dict, actor: str):
    payload = {"tool": tool, "args": args, "actor": actor, "idempotency_key": f"{actor}:{tool}:{hash(str(args))}"}
    r = httpx.post(f"{BASE}/tasks/send", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()["task_id"]

def wait_task(task_id: str):
    while True:
        s = httpx.get(f"{BASE}/tasks/get", params={"task_id": task_id}, timeout=10).json()
        if s["status"] in ("SUCCEEDED", "FAILED"):
            return s
        if s["status"] == "WAITING_APPROVAL":
            a = httpx.get(f"{BASE}/approvals/get", params={"task_id": task_id}, timeout=10).json()
            print("\n--- HUMAN APPROVAL REQUIRED ---")
            print(a["summary"])
            print("proposed:", a["proposed_tool"])
            # 데모: 자동 승인(실무에선 Slack/Console에서 승인 버튼)
            httpx.post(f"{BASE}/approvals/decide",
                       params={"task_id": task_id},
                       json={"approve": True, "editor_notes": "OK. proceed with rollback."},
                       timeout=10)
        time.sleep(0.2)

if __name__ == "__main__":
    # 1) 안전한 관측성 tool
    t1 = send_tool("search_logs", {"query": "5xx AND payments"}, actor="oncall")
    print("search_logs:", wait_task(t1))

    # 2) 위험한 변경 tool -> 승인 후 실행
    t2 = send_tool("rollback_deploy", {"env": "prod", "to_sha": "a1b2c3"}, actor="oncall-admin")
    print("rollback_deploy:", wait_task(t2))
```

예상 출력(요지):
- `search_logs`는 바로 SUCCEEDED
- `rollback_deploy`는 WAITING_APPROVAL → 승인 후 RUNNING → SUCCEEDED

이 구조가 “toy가 아닌” 이유:
- 장애 대응은 실제로 장기 실행/부분 실패/승인이 필수고,
- tool 호출의 위험도가 다르며,
- 상태 추적(Tasks)과 승인(HITL)이 분리되어야 운영이 됩니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **“Stateless core + 외부 상태 저장소”를 일찍 확정**
   - MCP가 stateless 방향으로 가는 이유는 운영/확장/캐싱/격리를 위해서입니다. ([blog.modelcontextprotocol.io](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/?utm_source=openai))  
   - 대신 thread/run/task 상태를 Redis/Postgres 같은 “명시적 state store”로 빼세요. 그래야 재시도/재개/감사가 됩니다.

2) **Risk-based Tool Tiering**
   - tool을 “read-only(검색/조회)” vs “write(변경/집행)”로 나누고,
   - write는 기본적으로 HITL 또는 2단계 승인(특히 비용/권한 관련)로 설계하세요.
   - 이게 비용 폭주(모델이 무한 루프)와 사고를 동시에 줄입니다.

3) **장기 실행은 무조건 Task boundary**
   - A2A 예시에서 task 메서드가 등장하는 건 우연이 아닙니다. ([developers.googleblog.com](https://developers.googleblog.com/build-cross-language-multi-agent-team-with-google-agent-development-kit-and-a2a/?utm_source=openai))  
   - “사용자 요청 한 번에 에이전트가 모든 걸 끝내는” 구조는 타임아웃/재시도 지옥으로 갑니다.

### 흔한 함정/안티패턴
- **Approve 버튼을 맨 끝에만 두기**: 이미 앞에서 위험한 tool을 실행해버리면 승인 UX는 장식입니다. (LangGraph가 ‘tool call 사전 검토’ 개념을 강조하는 이유) ([github.com](https://github.com/langchain-ai/langgraphjs/blob/main/docs/docs/concepts/human_in_the_loop.md?utm_source=openai))
- **멀티 에이전트 = 마이크로서비스처럼 생각하기**: 에이전트는 비정형 IO + 비용/환각/정책 문제가 있으니, “RPC 호출”보다 더 강한 guardrail/관측이 필요합니다.
- **프롬프트에 운영 책임을 떠넘기기**: “이런 경우엔 호출하지 마”를 프롬프트로만 막으면, 언젠가 터집니다. 반드시 policy gate를 코드로 두세요.

### 비용/성능/안정성 트레이드오프
- Durable execution/HITL을 넣으면 **레이턴시**는 늘지만, **실패 비용**(재작업·장애·보안 사고·잘못된 변경)은 급격히 줄어듭니다.
- Aggregator/Gateway는 중앙화로 편해지지만, 잘못 설계하면 **병목/단일 장애점(SPOF)** 이 됩니다. 수평 확장 + rate limit + 캐시 + 회로차단(circuit breaker)을 기본 옵션으로 두세요.
- A2A/MCP 같은 표준을 쓰면 락인은 줄지만, 초기에는 **스키마 설계 비용**이 듭니다(장기적으로는 이 비용이 “팀 간 통합 비용”을 대체).

---

## 🚀 마무리
2026년 8월의 AI 앱 아키텍처 설계 패턴은 한 문장으로 요약하면 이겁니다:  
**“LLM을 함수처럼 호출하지 말고, 운영되는 분산 시스템의 한 컴포넌트로 취급하라.”**

도입 판단 기준(체크리스트):
- tool 호출이 5개 이상으로 늘어날 가능성이 있는가?
- 장기 실행/재시도/재개가 필요한가?
- 변경(write) 작업이 있는가(권한/비용/데이터 변형)?
- 멀티테넌시/감사/승인이 요구되는가?
→ 2개 이상 “예”라면 **MCP 기반 Tool Gateway + Task boundary + Durable/HITL** 조합이 투자 대비 효과가 큽니다. ([blog.modelcontextprotocol.io](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/?utm_source=openai))  
멀티 에이전트로 외부 에이전트를 호출해야 한다면, 상호운용 표준으로 **A2A**까지 검토하세요. ([developers.googleblog.com](https://developers.googleblog.com/a2a-a-new-era-of-agent-interoperability/?utm_source=openai))

다음 학습 추천(순서):
1) MCP architecture/stateless 방향과 운영 모델 이해 ([modelcontextprotocol.io](https://modelcontextprotocol.io/specification/2025-06-18/architecture?utm_source=openai))  
2) Durable execution + HITL를 “그래프/체크포인트”로 구현 ([langchain.com](https://www.langchain.com/blog/runtime-behind-production-deep-agents?utm_source=openai))  
3) 조직/벤더 경계를 넘는 경우 A2A 프로토콜 모델 학습 ([github.com](https://github.com/a2aproject/A2A/blob/main/docs/specification.md?utm_source=openai))