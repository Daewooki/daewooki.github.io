---
title: "**서버리스 챗봇은 끝났다: 2026년 7월, “Stateful Agent + Control/Data Plane 분리”로 가는 AI 앱 아키텍처 패턴 지도**"
date: 2026-07-05 04:07:56 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-07]
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
2026년 중반 기준 AI 애플리케이션의 실패 원인은 “모델 성능”보다 **아키텍처**에서 더 자주 터집니다. 특히 (1) 멀티스텝 작업이 길어지고, (2) tool 호출이 늘고, (3) RAG가 단순 검색에서 “agentic RAG”로 진화하면서 **상태(state)·복구(replay)·격리(sandbox)·관측(observability)·비용 통제**가 설계의 중심이 됐습니다. OpenAI도 Agents SDK를 “모델-native harness / sandbox / configurable memory” 같은 방향으로 강화하고 있습니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/?utm_source=openai))

### 언제 쓰면 좋은가
- **업무 플로우가 5단계 이상**(예: 조사→요약→근거검증→티켓 생성→승인)
- **실패 비용이 크고**, 중간 결과를 저장/재개해야 함(예: 금융/보안/배포 자동화)
- 사용자 동시성이 늘어 **세션 충돌**, **긴 작업의 재시도**, **부분 재실행**이 필요함 ([runpod.io](https://www.runpod.io/articles/guides/stateful-langgraph-agents-on-runpod?utm_source=openai))

### 언제 쓰면 안 되는가
- 단발성 Q&A, 단순 요약처럼 **stateless**로 충분한 작업
- “실시간 100ms”급 초저지연이 절대 목표(에이전트 오케스트레이션은 본질적으로 느림)
- tool 호출이 거의 없고, 규칙 기반 파이프라인이 더 명확한 경우(LLM을 오케스트레이터로 쓰면 오히려 불확실성만 증가)

---

## 🔧 핵심 개념
2026년 7월 기준 “확장 가능한 AI 앱 설계 패턴”을 한 문장으로 요약하면:

> **Stateful workflow runtime(그래프/상태머신) 위에, Control Plane과 Data Plane을 분리하고, 실행은 sandbox+관측+캐시로 감싼다.**

### 1) Stateless Agent → Stateful Agent(그래프/상태머신)로의 전환
프로토타입은 보통 “tool-calling loop”로 시작합니다. 문제는 프로덕션에서:
- 중간 실패 시 **전체가 날아가고 재현이 어려움**
- 동시 요청에서 **thread_id/세션 충돌**
- LLM 컨테이너와 상태 저장이 결합돼 **스케일링 단위가 꼬이고 비용 폭발** ([runpod.io](https://www.runpod.io/articles/guides/stateful-langgraph-agents-on-runpod?utm_source=openai))

그래서 현장에서는 LangGraph류의 **stateful graph runtime**이 “대화”가 아니라 “업무 실행”에 더 적합하다는 이야기가 반복됩니다(체크포인팅, human-in-the-loop, 분기/재시도 구조). ([ailearningguides.com](https://ailearningguides.com/production-ai-agents-langgraph-mcp-2026-build-guide/?utm_source=openai))  
핵심은 **State를 1급 시민**으로 둔다는 것:
- 매 노드 실행 후 State를 저장(checkpoint)
- 실패한 노드부터 재시도 가능(부분 replay)
- 승인/대기(Interrupt) 같은 “멈춤”이 primitive로 존재

### 2) Control Plane / Data Plane 분리(확장성의 본체)
최근 가이드/연구에서 반복되는 원칙이 **오케스트레이션(결정/흐름)** 과 **데이터/실행(검색/코드실행/외부 API)** 을 분리하라는 것입니다. ([ijrai.org](https://www.ijrai.org/index.php/ijrai/article/download/343/322/647?utm_source=openai))

- **Control Plane**: workflow graph, 정책(guardrails), 라우팅, 재시도 전략, 비용/레이트리밋
- **Data Plane**: RAG retrieval, DB/사내시스템 접근, 코드 실행, 브라우징, batch job

이렇게 나누면:
- LLM/오케스트레이터는 CPU 위주로 수평 확장
- retrieval / embedding / GPU inference / sandbox는 별도 풀로 확장
- 장애 격리(예: sandbox 죽어도 control plane은 살아서 재시도)

### 3) “Hybrid pattern”: 생성은 자유롭게, 실행은 결정적으로
현장에서 자주 쓰는 하이브리드:
- 1단계: LLM이 **open-ended 생성**(계획, 후보안, 근거 수집)
- 2단계: 그 결과를 **구조화된 JSON**으로 고정
- 3단계: JSON을 입력으로 **state machine이 결정적 실행**(API 호출/티켓 생성/권한 요청) ([reactify-solutions.com](https://www.reactify-solutions.com/articles/langgraph-production-agents-2026?utm_source=openai))

이게 중요한 이유: LLM이 “실행 그 자체”를 하면 재현/테스트가 불가능해지기 쉽고, 반대로 state machine만 쓰면 요구 변화에 취약합니다.

### 4) Sandbox 실행 + Memory/State의 “범위”를 명확히
OpenAI Agents SDK가 “native sandbox execution / configurable memory”를 강조하는 흐름은, 결국 **안전한 실행 격리**와 **기억의 통제**가 프로덕션 요구사항이 됐다는 뜻입니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/?utm_source=openai))  
여기서 실무 포인트는:
- Memory는 “장기 기억”이 아니라 **정책이 있는 저장소**(TTL/PII redaction/권한)
- Sandbox는 “코드 실행”뿐 아니라 **tool 자체를 격리**(네트워크 egress 제한, 파일시스템 제한)

---

## 💻 실전 코드
아래는 “지원 티켓 자동 분류/조치” 시나리오입니다. 포인트는 **(a) state schema 고정**, **(b) 단계별 checkpoint**, **(c) tool 실행을 data-plane worker로 분리**하는 구조입니다. (LangGraph를 직접 의존하지 않아도 패턴은 그대로 적용됩니다.)

### 0) 의존성/실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pydantic httpx redis sqlalchemy psycopg2-binary
# (선택) Celery/RQ 등 큐를 붙이면 data-plane worker 분리가 쉬워집니다.
```

### 1) State(계약) 정의 + 체크포인트 저장소(Postgres)
```python
# app/state.py
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict
from datetime import datetime

class TicketState(BaseModel):
    # workflow identity
    thread_id: str
    ticket_id: str

    # inputs
    user_text: str
    user_tier: Literal["free","pro","enterprise"]

    # derived / intermediate
    intent: Optional[str] = None
    risk: Literal["low","medium","high"] = "low"
    retrieved_docs: List[Dict] = Field(default_factory=list)

    # proposed actions (structured, deterministic execution input)
    plan: List[Dict] = Field(default_factory=list)

    # outputs
    resolution_summary: Optional[str] = None
    status: Literal["running","needs_approval","done","failed"] = "running"

    # bookkeeping
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

```python
# app/checkpoint.py
import json
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg2://app:app@localhost:5432/app")

def save_checkpoint(thread_id: str, step: str, state_dict: dict):
    with engine.begin() as conn:
        conn.execute(text("""
          insert into checkpoints(thread_id, step, state_json)
          values(:thread_id, :step, :state_json)
        """), {
            "thread_id": thread_id,
            "step": step,
            "state_json": json.dumps(state_dict, ensure_ascii=False),
        })

def load_latest(thread_id: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(text("""
          select state_json from checkpoints
          where thread_id=:thread_id
          order by id desc
          limit 1
        """), {"thread_id": thread_id}).fetchone()
        return json.loads(row[0]) if row else None
```

(테이블 예시)
```bash
psql -d app -c "
create table if not exists checkpoints(
  id bigserial primary key,
  thread_id text not null,
  step text not null,
  state_json jsonb not null,
  created_at timestamptz default now()
);
create index if not exists idx_checkpoints_thread on checkpoints(thread_id, id desc);
"
```

### 2) Control Plane: 오케스트레이터(상태머신) + Data Plane 호출(큐/HTTP)
```python
# app/orchestrator.py
import httpx
from app.state import TicketState
from app.checkpoint import save_checkpoint

DATA_PLANE_URL = "http://localhost:9001"  # 별도 worker 서비스라고 가정

async def run_ticket_workflow(state: TicketState) -> TicketState:
    # Step A: classify intent/risk (LLM 호출은 여기서 하되, 결과는 "작게" 구조화)
    # (예시는 간단화. 실제로는 Responses API/Agents SDK를 사용)
    state.intent = "refund_request" if "환불" in state.user_text else "general"
    state.risk = "high" if state.user_tier == "enterprise" else "medium"
    save_checkpoint(state.thread_id, "classified", state.model_dump())

    # Step B: retrieval은 data plane으로 (독립 확장 대상)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{DATA_PLANE_URL}/retrieve", json={
            "ticket_id": state.ticket_id,
            "query": state.user_text,
            "intent": state.intent
        })
        r.raise_for_status()
        state.retrieved_docs = r.json()["docs"]
    save_checkpoint(state.thread_id, "retrieved", state.model_dump())

    # Step C: plan 생성(구조화된 액션 목록)
    # 핵심: 이후 실행은 "결정적"이어야 하므로 JSON plan으로 고정
    state.plan = [
        {"action": "create_jira", "project": "CS", "priority": "P1" if state.risk=="high" else "P2"},
        {"action": "draft_reply", "tone": "polite", "include_policy_links": True},
    ]
    # enterprise & high risk면 human approval gate
    if state.risk == "high":
        state.status = "needs_approval"
        save_checkpoint(state.thread_id, "needs_approval", state.model_dump())
        return state

    save_checkpoint(state.thread_id, "planned", state.model_dump())

    # Step D: execute plan은 data plane에서(외부 API 권한/레이트리밋/재시도 정책)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{DATA_PLANE_URL}/execute", json={
            "thread_id": state.thread_id,
            "plan": state.plan
        })
        r.raise_for_status()
        result = r.json()

    state.resolution_summary = result["summary"]
    state.status = "done"
    save_checkpoint(state.thread_id, "done", state.model_dump())
    return state
```

```python
# data_plane/worker.py (별도 프로세스)
from fastapi import FastAPI
from typing import Dict, List

app = FastAPI()

@app.post("/retrieve")
def retrieve(payload: Dict):
    # 실제로는 vector DB + ACL + chunking 전략 + hierarchical RAG 등이 들어감
    # 여기서는 "docs contract"만 보여주기 위해 단순화
    return {"docs": [
        {"doc_id": "policy-12", "title": "Refund Policy", "snippet": "환불은 결제 후 7일 이내..."},
        {"doc_id": "runbook-3", "title": "Enterprise Escalation", "snippet": "엔터프라이즈는 P1로..."},
    ]}

@app.post("/execute")
def execute(payload: Dict):
    plan: List[Dict] = payload["plan"]
    # 실제로는 Jira/Slack/Email API 호출 + idempotency key + retry/backoff 필요
    executed = [p["action"] for p in plan]
    return {"summary": f"Executed: {executed}. Reply draft created."}
```

예상 흐름/출력:
- high risk(enterprise)면 `needs_approval`에서 멈추고 checkpoint 저장
- 승인 후 같은 `thread_id`로 재개하면 “retrieved 이후부터” 이어서 실행 가능  
이게 바로 “긴 작업/실패/재시도”에 강한 구조입니다(서버리스 단발 호출로는 어렵습니다). ([runpod.io](https://www.runpod.io/articles/guides/stateful-langgraph-agents-on-runpod?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (추천 3가지)
1) **State schema 버저닝 + 마이그레이션**
- stateful 시스템은 시간이 지나면 State 필드가 바뀝니다. 체크포인트가 쌓인 뒤 스키마 깨지면 “재개”가 불가능해집니다.
- 최소한 `state_version`을 두고, 구버전 → 신버전 변환기를 준비하세요(템플릿들이 자주 강조하는 포인트이기도 함). ([reddit.com](https://www.reddit.com/r/LangChain/comments/1ss1r93/i_built_a_productionready_template_for_ai_agents/?utm_source=openai))

2) **Idempotency가 없는 tool 실행은 지뢰**
- 재시도/부분 replay가 가능해질수록, 외부 API는 “중복 실행” 위험이 커집니다.
- `idempotency_key = thread_id + step + action_index` 같은 규칙을 강제하세요.

3) **오케스트레이터(LLM)와 실행기(data plane)의 스케일링 단위를 분리**
- retrieval/embedding/GPU inference와 workflow runner를 한 컨테이너에 넣으면, CPU-bound 트래픽 때문에 GPU가 같이 늘어 “조용히” 비용이 터집니다. ([runpod.io](https://www.runpod.io/articles/guides/stateful-langgraph-agents-on-runpod?utm_source=openai))

### 흔한 함정/안티패턴
- **“모든 걸 LLM에게 맡기는” Plan-and-Execute의 과신**  
  Plan은 LLM이 짜도 되지만, Execute는 “검증된 결정적 레이어”로 내려보내는 게 운영이 됩니다(감사/재현/테스트). ([reactify-solutions.com](https://www.reactify-solutions.com/articles/langgraph-production-agents-2026?utm_source=openai))
- **관측 없이 멀티에이전트부터 도입**  
  멀티에이전트는 디버깅 비용이 기하급수로 증가합니다. 먼저 single-agent + stateful + checkpoint + tracing을 만들고 확장하세요.
- **RAG를 “vector DB 붙이면 끝”으로 착각**  
  실제 병목은 ACL/권한, stale 문서, prompt injection 경로, chunking/재랭킹, 캐시/무효화 정책입니다.

### 비용/성능/안정성 트레이드오프(의사결정 기준)
- **Stateful(안정/복구)** ↔ **Stateless(저지연/단순)**
- **계층형/agentic RAG(정확)** ↔ **단순 RAG(저렴/빠름)**
- **Sandbox/Guardrails(안전)** ↔ **Tool 직접 실행(빠름/위험)**  
OpenAI도 sandbox와 guardrails를 “표준 인프라”로 끌어올리는 이유가 여기에 있습니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/?utm_source=openai))

---

## 🚀 마무리
2026년 7월의 “확장 가능한 AI 앱”은 더 이상 프롬프트 묶음이 아니라, **Stateful workflow runtime + Control/Data Plane 분리 + Sandbox/Observability**로 굳어지는 중입니다. ([runpod.io](https://www.runpod.io/articles/guides/stateful-langgraph-agents-on-runpod?utm_source=openai))

도입 판단 기준은 간단합니다:
- 내 앱이 **중간 실패 후 재개**가 필요하면 → stateful + checkpoint는 필수
- 외부 시스템을 건드리고 **실행 책임**이 생기면 → plan을 구조화하고 execute를 결정적으로
- 트래픽/비용이 문제면 → control/data plane 분리로 독립 스케일링

다음 학습 추천(순서):
1) OpenAI Agents SDK의 memory/sandbox 개념을 “아키텍처 관점”에서 정리 ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk/?utm_source=openai))  
2) LangGraph류의 state machine 모델(체크포인트, interrupt, replay)로 운영 시나리오 설계 ([runpod.io](https://www.runpod.io/articles/guides/stateful-langgraph-agents-on-runpod?utm_source=openai))  
3) Control/Data Plane 분리 후, idempotency/관측/평가(evals)까지 포함한 운영 체계 구축 ([ijrai.org](https://www.ijrai.org/index.php/ijrai/article/download/343/322/647?utm_source=openai))

원하시면, 위 예제를 **실제로 OpenAI Responses API/Agents SDK 호출**로 바꾸고(스트리밍/툴콜/메모리 포함), Redis 큐를 붙여 data plane worker를 완전히 분리한 “프로덕션 골격”으로 확장해드릴게요.