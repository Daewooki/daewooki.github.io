---
title: "2026년 3월, 확장 가능한 AI 앱 아키텍처 설계 패턴: “단발성 Prompt”에서 “Durable Agent Runtime”으로"
date: 2026-03-21 02:38:19 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-03]
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
2024~2025년의 LLM 앱은 “요청 1번 → 응답 1번” 구조가 많았습니다. 하지만 2026년 3월 기준 현업에서 문제는 명확합니다: **멀티스텝(workflow) + 외부 Tool 호출 + 장시간 실행 + 재시도/복구 + 감사(audit)** 가 기본 요구가 되면서, 단순한 챗봇 아키텍처로는 **비용 폭증, 장애 시 재실행, 부작용(side effect) 중복 실행**을 막기 어렵습니다. 그래서 최근 흐름은 “LLM을 똑똑하게 만드는 법”보다, **LLM을 ‘안전하게 운영 가능한 컴포넌트’로 만드는 설계 패턴** 쪽으로 이동했습니다. 특히 **stateful graph workflows + durable execution + typed tool interface**가 핵심 축으로 굳어지는 중입니다. ([blog.langchain.com](https://www.blog.langchain.com/building-langgraph/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Pattern A — Stateful Graph Workflows (Graph-based Orchestration)
**개념**: 에이전트를 “while 루프”로 돌리는 대신, 노드(node)와 엣지(edge)로 표현되는 **StateGraph**로 모델링합니다. 각 노드는 *Retriever*, *Planner*, *Tool Executor*, *Verifier* 같은 역할을 가지며, 상태(state)를 입력/출력으로 주고받습니다.  
**왜 중요한가**:  
- 실행 경로가 명시적이라 **관측/디버깅/리플레이**가 쉬움  
- 멀티 에이전트/툴 호출을 **구조적으로 제한**할 수 있음(무한 루프 방지, 단계별 예산 부여)  
- checkpoint와 결합하면 “중간부터 재개”가 가능 ([agentic-design.ai](https://agentic-design.ai/patterns/workflow-orchestration/stateful-graph-workflows?utm_source=openai))

### 2) Pattern B — Durable Execution (Checkpoint / Replay / Resume)
**개념**: 장시간 워크플로우는 “실행 중 프로세스가 죽는 것”이 정상입니다. Durable execution은 **각 단계의 결과를 저장**해두고, 실패 시 **마지막 안전 지점부터 재개**하게 합니다. LangGraph는 checkpointer를 붙이면 이 레이어가 사실상 기본 제공됩니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/durable-execution?utm_source=openai))  
**핵심 포인트(원리)**:
- LLM 호출은 비결정적(nondeterministic)이므로, 내구성 시스템에서는 보통 “activity step”처럼 **결과를 기록하고 재실행하지 않게** 설계합니다(재시작 시 동일 호출로 비용/결과가 바뀌는 문제 방지). ([zylos.ai](https://zylos.ai/research/2026-02-17-durable-execution-ai-agents?utm_source=openai))

### 3) Pattern C — Manager→Specialist (Agents-as-Tools / Handoff)
**개념**: “모든 걸 하는 단일 Agent” 대신, **Manager Agent**가 전체 컨텍스트를 관리하고, Specialist들을 **tool처럼 호출**(handoff)합니다. OpenAI Agents SDK 문서에서도 대표 패턴으로 정리됩니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/?utm_source=openai))  
**확장성 포인트**:
- Specialist는 독립 배포/스케일링 가능(예: Retrieval 전용, Code 실행 전용)
- 팀 개발 시 책임 경계가 선명해져 변경 영향이 줄어듦
- 병렬 실행(예: Promise.all)로 latency 최적화 가능 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/?utm_source=openai))

### 4) Pattern D — “Tool Interface as Code” + Registry-driven Tooling
**개념**: 엔터프라이즈 데이터/텔레메트리는 스키마와 의미가 계속 변합니다. REGAL 같은 최근 연구는 **도구(tool) 정의를 registry(선언적 정의)로 버전 관리**하고, 그 정의로부터 tool을 합성/컴파일해 “tool drift”를 줄이는 아키텍처를 강조합니다. ([arxiv.org](https://arxiv.org/abs/2603.03018?utm_source=openai))  
**효과**:
- LLM이 임의 SQL/임의 API를 때리지 않고, “정해진 action space”에서만 움직이게 됨
- 거버넌스/권한/정책을 인터페이스 경계에 삽입 가능

---

## 💻 실전 코드
아래 예제는 “Graph + Durable execution + Tool interface + Budget/Idempotency” 감각을 보여주는 **실행 가능한 최소 구조**입니다. (외부 의존성을 최소화하기 위해 LLM 호출은 mock으로 두고, 아키텍처 골격에 집중합니다.)

```python
# python 3.11+
# pip install fastapi uvicorn pydantic

from __future__ import annotations
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal
import sqlite3
import json
import time
import uuid

app = FastAPI()

# --- Durable checkpoint store (SQLite) ---
conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS checkpoints (
  run_id TEXT,
  step TEXT,
  state_json TEXT,
  created_at REAL,
  PRIMARY KEY(run_id, step)
)
""")
conn.commit()

def save_checkpoint(run_id: str, step: str, state: Dict[str, Any]) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO checkpoints(run_id, step, state_json, created_at) VALUES (?, ?, ?, ?)",
        (run_id, step, json.dumps(state, ensure_ascii=False), time.time())
    )
    conn.commit()

def load_checkpoint(run_id: str, step: str) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        "SELECT state_json FROM checkpoints WHERE run_id=? AND step=?",
        (run_id, step)
    )
    row = cur.fetchone()
    return json.loads(row[0]) if row else None

# --- Typed Tool Interface (tool = deterministic execution boundary) ---
class ToolResult(BaseModel):
    ok: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

def tool_search_docs(query: str) -> ToolResult:
    # 실제로는 Vector DB / Search service 호출.
    # 중요한 설계 포인트: tool은 "입력->출력"이 명확하고 로깅/재현이 쉬워야 함.
    docs = [
        {"id": "doc-1", "text": "Durable execution uses checkpoints to resume workflows."},
        {"id": "doc-2", "text": "Manager agent delegates to specialist tools/agents."},
    ]
    hits = [d for d in docs if query.lower() in d["text"].lower()]
    return ToolResult(ok=True, data={"hits": hits, "count": len(hits)})

# --- Simple budget + idempotency guard ---
class Budget(BaseModel):
    max_steps: int = 8
    used_steps: int = 0

    def consume(self) -> None:
        self.used_steps += 1
        if self.used_steps > self.max_steps:
            raise RuntimeError("Step budget exceeded (possible loop / runaway agent).")

class RunState(BaseModel):
    run_id: str
    input: str
    budget: Budget = Field(default_factory=Budget)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    # idempotency_key: 외부 부작용 작업(메일 발송, 티켓 생성 등)에 붙여 중복 실행 방지
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))

# --- Mock "LLM reasoning" (replace with real model call) ---
def llm_summarize(hits: list[dict]) -> str:
    # 실제에선 structured output + eval/guardrail을 붙이는 것을 권장
    return " | ".join([h["text"] for h in hits]) if hits else "No relevant docs."

# --- Graph-like workflow runner (step-by-step checkpointing) ---
def run_workflow(state: RunState, resume_from: Optional[Literal["retrieval","synthesis","final"]] = None) -> RunState:
    # 1) retrieval
    if resume_from in (None, "retrieval"):
        state.budget.consume()
        save_checkpoint(state.run_id, "start", state.model_dump())
        tr = tool_search_docs(state.input)
        if not tr.ok:
            raise RuntimeError(tr.error or "tool error")
        state.artifacts["search"] = tr.data
        save_checkpoint(state.run_id, "retrieval", state.model_dump())

    # 2) synthesis
    if resume_from in (None, "retrieval", "synthesis"):
        state.budget.consume()
        hits = state.artifacts.get("search", {}).get("hits", [])
        state.artifacts["summary"] = llm_summarize(hits)
        save_checkpoint(state.run_id, "synthesis", state.model_dump())

    # 3) final (side-effect free in this demo)
    state.budget.consume()
    state.artifacts["output"] = {
        "answer": state.artifacts["summary"],
        "run_id": state.run_id,
        "idempotency_key": state.idempotency_key
    }
    save_checkpoint(state.run_id, "final", state.model_dump())
    return state

class StartRequest(BaseModel):
    text: str

@app.post("/runs")
def start_run(req: StartRequest):
    run_id = str(uuid.uuid4())
    state = RunState(run_id=run_id, input=req.text)
    final_state = run_workflow(state)
    return final_state.artifacts["output"]

@app.post("/runs/{run_id}/resume")
def resume_run(run_id: str, step: Literal["start","retrieval","synthesis","final"] = "retrieval"):
    # 장애 후 재개: 마지막 저장된 상태를 로드하고 다음 단계부터 진행
    saved = load_checkpoint(run_id, step)
    if not saved:
        return {"error": f"No checkpoint for run_id={run_id}, step={step}"}

    state = RunState(**saved)
    # 여기서는 step 기준으로 "그 다음"을 실행한다고 가정
    resume_from = "retrieval" if step == "start" else ("synthesis" if step == "retrieval" else "final")
    final_state = run_workflow(state, resume_from=resume_from)
    return final_state.artifacts["output"]
```

---

## ⚡ 실전 팁
1) **“LLM = 순수 함수가 아니다”를 전제로 설계**  
재시작/재시도 때 LLM이 다른 답을 내는 건 자연스러운 현상입니다. 그래서 production에서는 LLM 호출을 “deterministic workflow”에 직접 섞기보다, **step 경계로 격리하고 결과를 저장**(journal/checkpoint)하는 접근이 내구성 면에서 유리합니다. ([zylos.ai](https://zylos.ai/research/2026-02-17-durable-execution-ai-agents?utm_source=openai))

2) **Idempotency Key + Compensator(보상 트랜잭션) 없이는 멀티스텝이 곧 장애**  
에이전트가 이메일/결제/배포 같은 side effect를 만지는 순간, “한 번 더 실행”은 곧 사고입니다. 단계별로 **idempotency key**를 강제하고, 실패 시 되돌릴 수 있는 **compensator**(취소/롤백 작업)를 설계 패턴으로 고정하세요. (특히 멀티 에이전트는 연쇄 실패가 쉽게 납니다.) ([reddit.com](https://www.reddit.com/r/aiagents/comments/1rt1kjh/after_3_months_of_running_multiagent/?utm_source=openai))

3) **Manager→Specialist로 분리하되, Specialist는 ‘tool 계약’을 지켜라**  
OpenAI Agents SDK가 강조하는 Agents-as-tools/handoff는 조직 확장에 좋지만, Specialist가 “대화형 지능”을 과도하게 가지면 예측 불가능해집니다. Specialist는 가급적 **입력/출력 스키마가 명확한 tool 성격**(typed interface)을 유지하고, Manager가 정책/예산/승인(HITL)을 통제하는 구조가 운영에 강합니다. ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/?utm_source=openai))

4) **Tool Interface as Code(Registry)로 tool drift를 막아라**  
엔터프라이즈 데이터는 변합니다. “프롬프트에 API 설명을 적는 방식”은 금방 깨집니다. REGAL이 제안하듯, metric/tool을 **선언적으로 정의하고 버전 관리**해, 실행계(tool runtime)와 모델계(model prompting)가 같은 소스를 보게 만드는 접근이 유지보수 비용을 크게 줄입니다. ([arxiv.org](https://arxiv.org/abs/2603.03018?utm_source=openai))

---

## 🚀 마무리
2026년 3월의 “AI 애플리케이션 아키텍처 설계 패턴”을 한 줄로 요약하면 **Agent를 코드로 ‘돌리는’ 게 아니라, 시스템으로 ‘운영’하는 방법**으로 수렴하고 있습니다.  
핵심 패턴은 (1) **Stateful Graph Workflows**, (2) **Durable Execution**, (3) **Manager→Specialist(Agents-as-Tools)**, (4) **Registry-driven Tooling** 네 가지를 축으로, 확장성(Scale)과 신뢰성(Reliability)을 함께 잡는 것입니다. ([blog.langchain.com](https://www.blog.langchain.com/building-langgraph/?utm_source=openai))

다음 학습 추천:
- LangGraph의 checkpoint/durable execution 개념을 실제 프로덕션 장애 시나리오(타임아웃, 재시작, 부분 성공)로 재현해보기 ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/durable-execution?utm_source=openai))  
- OpenAI Agents SDK의 handoff/agent-as-tool 패턴으로 “팀 구조(Manager/Specialist)”를 설계해보고, tool 스키마와 관측(tracing)을 붙여 운영 관점에서 점검하기 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/multi-agent/?utm_source=openai))