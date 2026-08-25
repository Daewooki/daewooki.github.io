---
title: "컨텍스트 폭발을 이기는 2026 Supervisor/Worker 멀티‑에이전트 오케스트레이션 실전 설계"
date: 2026-08-25 01:42:22 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-08]
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
2026년 현재 “multi-agent orchestration”이 다시 뜨는 이유는 단순합니다. 단일 Agent에 **너무 많은 tool schema / 역할 / 장기 히스토리**를 몰아넣으면 (1) 컨텍스트가 비대해져 비용이 튀고, (2) 의사결정이 흔들리며, (3) 실패 시 복구가 어려워집니다. 그래서 **Supervisor가 흐름을 통제하고, Worker가 좁은 범위의 일을 수행**하는 supervisor/worker 패턴(= orchestrator/subagent, Russian-doll 패턴)이 실무에서 가장 “수습 가능한” 형태로 자리 잡았습니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/architecture/multi-agent-orchestrator-sub-agent?utm_source=openai))

**언제 쓰면 좋나**
- 작업이 “도메인/기능”으로 자연스럽게 분해되고(예: 웹리서치, DB조회, 코드생성, 정책검토), 각 단계에 **서로 다른 가드레일/툴/모델**이 필요한 경우 ([learn.microsoft.com](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/architecture/multi-agent-orchestrator-sub-agent?utm_source=openai))
- “장기 실행 + 중간 실패 + 재시도/중단/승인(HITL)”이 필요한 업무 플로우(비즈니스 프로세스, 문서처리, 컴플라이언스) ([arxiv.org](https://arxiv.org/abs/2607.19297?utm_source=openai))
- 비용을 통제하며 품질을 올리기 위해 **fan-out → merge**, **validator/critic** 같은 “단일 목적 호출”을 넣고 싶은 경우 ([preprints.org](https://www.preprints.org/frontend/manuscript/32c81f12531e9db99f8c719e6591d5e1/download_pub?utm_source=openai))

**언제 쓰면 안 되나**
- 단일 Tool-call agent로도 충분한 짧은 작업(오케스트레이션 오버헤드가 더 큼)
- Supervisor가 계속 “생각/플래닝”을 하느라 매 턴 전체 히스토리를 먹는 구조(토큰 비용이 선형/누적 증가) ([preprints.org](https://www.preprints.org/frontend/manuscript/32c81f12531e9db99f8c719e6591d5e1/download_pub?utm_source=openai))
- Worker 간 자유로운 P2P 대화를 허용하는 “무정부형 스웜”(디버깅/재현성/비용 통제가 매우 어려움). 대신 중앙집중/계층형을 권장 ([preprints.org](https://www.preprints.org/frontend/manuscript/32c81f12531e9db99f8c719e6591d5e1/download_pub?utm_source=openai))

---

## 🔧 핵심 개념
### 주요 개념 정의
- **Supervisor(Orchestrator)**: “다음에 누가 일할지/끝낼지”를 결정하는 라우터 + 품질/비용 책임자. 대개 *routing 전용 프롬프트*와 *상태(state) 기반 정책*을 가진다.
- **Worker(Subagent)**: 좁은 역할(예: `ResearchWorker`, `SQLWorker`, `PolicyWorker`)만 수행. 입력/출력 스키마가 명확하고, 가진 tool도 최소화.
- **Handoff**: Supervisor가 Worker에게 작업을 “넘기는” 메커니즘. OpenAI Agents SDK에서는 handoff/agent-as-tool 같은 방식으로 매니저형 구성이 가능하고, LangGraph 계열에서는 노드 간 전이로 구현합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

### 내부 작동 방식(구조/흐름)
실무에서 안정적인 supervisor/worker 흐름은 보통 아래 3층으로 정리됩니다.

1) **Plan/Route(결정 층)**  
Supervisor는 (a) 사용자 의도, (b) 현재 state(진행도/실패/예산), (c) 필요한 증거 수준을 보고 다음 액션을 고릅니다.  
중요 포인트는 *Worker 출력이 채팅 텍스트로 “그냥 붙는” 게 아니라*, Supervisor가 이해하기 쉬운 **구조화 결과(JSON)** 로 들어와야 한다는 점입니다. (그래야 라우팅이 규칙/정책화 가능)

2) **Act(실행 층)**  
Worker는 “한 번의 실행”을 최대한 단순하게 끝냅니다.
- web search / RAG / DB / 코드 실행 등
- 실패하면 **명시적 실패 상태**(retryable, non-retryable)를 반환

3) **Judge/Merge(검증/통합 층)**  
Supervisor는 Worker 결과를 합치되,
- 증거가 부족하면 추가 Worker 호출
- 정책 위반/불확실성이면 `PolicyWorker` 또는 HITL interrupt
- 결과가 충분하면 종료

이 설계가 중요한 이유: 2026년 멀티 에이전트 논의의 핵심은 “똑똑한 대화”가 아니라 **컨텍스트/비용/실패를 관리하는 오케스트레이션 엔지니어링**으로 이동했기 때문입니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

### 다른 접근과의 차이점
- **단일 Agent + 많은 tools**: 간단하지만 tool schema가 커질수록 선택이 흔들리고, 로그/재현성이 약해집니다.
- **Auto speaker-selection류 그룹챗**: 매 턴 전체 대화가 들어가며 토큰 비용이 누적되기 쉬움(특히 대화 길어질수록). ([preprints.org](https://www.preprints.org/frontend/manuscript/32c81f12531e9db99f8c719e6591d5e1/download_pub?utm_source=openai))
- **Supervisor/Worker**: 라우팅을 중앙에서 강제하여 *컨텍스트를 “필요한 만큼만”* 흘려보낼 수 있고, Worker별로 가드레일/모델/툴을 분리하기 쉽습니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/architecture/multi-agent-orchestrator-sub-agent?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “운영팀이 매일 보는 장애 리포트(로그) + KPI 테이블”을 입력으로 받아,
1) **LogWorker**가 로그를 요약/원인 후보 추출  
2) **SQLWorker**가 KPI를 조회(여기선 예시로 SQLite)  
3) **ReviewerWorker**가 결과를 검증(근거/불확실성/후속 액션)  
4) Supervisor가 최종 보고서를 작성  
…하는 “현실적인” supervisor/worker 파이프라인입니다.

> 구현은 **OpenAI Agents SDK의 ‘orchestration via code’ 스타일**을 기준으로, Worker를 `as_tool()`로 노출하고 Supervisor가 호출하는 구조로 잡았습니다. (2026년 기준 공식 문서가 이 접근을 명시적으로 안내합니다.) ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

### 1) 설치/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install openai-agents aiosqlite pydantic python-dotenv
export OPENAI_API_KEY="..."
```

### 2) 실행 코드 (Python)
```python
# file: supervisor_worker_incident_report.py
import os
import json
import asyncio
from typing import Literal, Optional
from pydantic import BaseModel, Field
import aiosqlite

from agents import Agent, Runner  # openai-agents-python

# ---------- Domain schemas ----------
class LogFinding(BaseModel):
    incident_id: str
    suspected_causes: list[str]
    key_errors: list[str]
    confidence: float = Field(ge=0, le=1)

class KpiSnapshot(BaseModel):
    incident_id: str
    window: str
    error_rate: float
    p95_latency_ms: float
    notes: Optional[str] = None

class ReviewResult(BaseModel):
    verdict: Literal["ok", "needs_more_data", "unsafe_or_uncertain"]
    missing: list[str] = []
    risk_notes: list[str] = []
    next_actions: list[str] = []

# ---------- Workers as tools ----------
log_worker = Agent(
    name="LogWorker",
    instructions=(
        "You analyze raw incident logs.\n"
        "Return STRICT JSON matching LogFinding schema.\n"
        "Do not propose fixes; only extract evidence, errors, and plausible causes."
    ),
    output_type=LogFinding,
)

sql_worker = Agent(
    name="SQLWorker",
    instructions=(
        "You query a SQLite database for KPI context.\n"
        "You will be given incident_id and time window.\n"
        "Return STRICT JSON matching KpiSnapshot schema.\n"
        "If data is missing, set notes and keep numeric fields as -1 if unavailable."
    ),
    output_type=KpiSnapshot,
)

review_worker = Agent(
    name="ReviewerWorker",
    instructions=(
        "You are a production reviewer.\n"
        "Check whether the evidence supports conclusions.\n"
        "Flag uncertainty, missing data, and risky claims.\n"
        "Return STRICT JSON matching ReviewResult."
    ),
    output_type=ReviewResult,
)

# ---------- Supervisor ----------
class RouteDecision(BaseModel):
    step: Literal["call_log_worker", "call_sql_worker", "call_reviewer", "final"]
    reason: str
    incident_id: str
    window: str = "last_60m"

supervisor = Agent(
    name="Supervisor",
    instructions=(
        "You orchestrate workers to produce an incident report.\n"
        "Rules:\n"
        "1) Always start with LogWorker.\n"
        "2) Then call SQLWorker for KPIs.\n"
        "3) Then call ReviewerWorker.\n"
        "4) If Reviewer says needs_more_data, ask for specific missing data and stop.\n"
        "Produce final report with: Summary, Evidence, KPIs, Suspected causes, Next actions.\n"
        "Be concise; avoid speculation."
    ),
    output_type=RouteDecision,
    tools=[
        log_worker.as_tool(tool_name="run_log_worker"),
        sql_worker.as_tool(tool_name="run_sql_worker"),
        review_worker.as_tool(tool_name="run_review_worker"),
    ],
)

# ---------- Example "realistic" data sources ----------
RAW_LOGS = """
2026-08-24T09:12:01Z api-gw ERROR upstream timeout service=checkout latency_ms=8123 trace_id=abc...
2026-08-24T09:12:02Z checkout ERROR db pool exhausted pool=primary active=200 waiting=340
2026-08-24T09:12:05Z api-gw WARN retrying request service=checkout attempt=2
2026-08-24T09:12:08Z checkout ERROR deadlock detected on orders table txn=...
"""

async def setup_db(db_path="kpi.db"):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS kpis(incident_id TEXT, window TEXT, error_rate REAL, p95_latency_ms REAL)"
        )
        await db.execute("DELETE FROM kpis")
        await db.execute(
            "INSERT INTO kpis VALUES(?,?,?,?)",
            ("INC-2026-0824-001", "last_60m", 0.073, 1820.0),
        )
        await db.commit()

async def query_kpi(db_path, incident_id, window):
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT error_rate, p95_latency_ms FROM kpis WHERE incident_id=? AND window=?",
            (incident_id, window),
        ) as cur:
            row = await cur.fetchone()
            return row

async def main():
    await setup_db()

    incident_id = "INC-2026-0824-001"
    window = "last_60m"

    # Step 1: LogWorker
    finding = await Runner.run(
        log_worker,
        input=f"incident_id={incident_id}\nlogs:\n{RAW_LOGS}"
    )
    finding_obj: LogFinding = finding.final_output

    # Step 2: SQLWorker (we actually query DB here, then pass to agent to format/interpret)
    row = await query_kpi("kpi.db", incident_id, window)
    if row:
        error_rate, p95 = row
        kpi_payload = {"incident_id": incident_id, "window": window, "error_rate": error_rate, "p95_latency_ms": p95}
    else:
        kpi_payload = {"incident_id": incident_id, "window": window, "error_rate": -1, "p95_latency_ms": -1, "notes": "missing"}

    kpis = await Runner.run(
        sql_worker,
        input=json.dumps(kpi_payload)
    )
    kpi_obj: KpiSnapshot = kpis.final_output

    # Step 3: ReviewerWorker
    review = await Runner.run(
        review_worker,
        input=json.dumps({
            "finding": finding_obj.model_dump(),
            "kpis": kpi_obj.model_dump(),
        })
    )
    review_obj: ReviewResult = review.final_output

    if review_obj.verdict != "ok":
        print("REVIEW BLOCKED:", review_obj.model_dump_json(indent=2))
        return

    # Final: Supervisor synthesizes (here we keep it deterministic via a final supervisor call)
    final_text = await Runner.run(
        Agent(
            name="ReportWriter",
            instructions=(
                "Write a production incident report.\n"
                "Use provided JSON only.\n"
                "Sections: Summary, Evidence, KPIs, Suspected causes, Next actions."
            )
        ),
        input=json.dumps({
            "finding": finding_obj.model_dump(),
            "kpis": kpi_obj.model_dump(),
            "review": review_obj.model_dump(),
        })
    )

    print(final_text.final_output)

if __name__ == "__main__":
    asyncio.run(main())
```

### 예상 출력(요약)
- Summary: checkout 경로에서 timeout 급증
- Evidence: db pool exhausted, deadlock 등
- KPIs: error_rate 7.3%, p95 1820ms
- Suspected causes: DB connection pool saturation, transactional contention
- Next actions: pool/쿼리 플랜 점검, deadlock 원인 테이블/인덱스 확인, rate limit/큐잉 등

이 예제의 포인트는 “Supervisor가 만능으로 다 한다”가 아니라,
- Worker를 **좁은 책임 + 구조화 출력**으로 만들고
- 마지막 합성만 최소화된 컨텍스트로 수행해서
토큰/실패/검증을 통제한다는 점입니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Worker 출력은 반드시 schema로 고정(JSON)**
   - Supervisor 라우팅을 “프롬프트 감”이 아니라 **정책 코드/조건 분기**로 옮길 수 있습니다.
   - 추후 리플레이/회귀테스트도 쉬워집니다(같은 입력 → 같은 구조 결과). ([arxiv.org](https://arxiv.org/abs/2607.19297?utm_source=openai))

2) **컨텍스트를 “공유 히스토리”가 아니라 “공유 state 요약”으로 전달**
   - 에이전트 수/대화 길이가 늘수록 전체 히스토리 기반 오케스트레이션은 비용이 선형으로 악화됩니다. ([preprints.org](https://www.preprints.org/frontend/manuscript/32c81f12531e9db99f8c719e6591d5e1/download_pub?utm_source=openai))  
   - Supervisor는 “필요한 state만” Worker에게 주고, Worker가 본문 로그/문서는 외부 저장소에서 가져오게 하세요.

3) **Reviewer/Policy Worker를 ‘마지막에 한 번’이 아니라 ‘게이트’로 배치**
   - 특히 web-search/RAG 기반이면 근거 누락이 빈번합니다.
   - “불확실하면 멈추고 무엇이 부족한지 출력”이 운영 안정성에 크게 기여합니다. ([arxiv.org](https://arxiv.org/abs/2607.19297?utm_source=openai))

### 흔한 함정/안티패턴
- **Worker가 서로에게 handoff 하는 자유대화**: 책임 소재가 흐려지고, 루프/핑퐁으로 비용 폭발이 납니다(실무 커뮤니티에서도 “API bill 2~3배” 패턴이 반복 보고). ([reddit.com](https://www.reddit.com/r/LangChain/comments/1sxmbgk/anyone_running_multiagent_setups_in_prod_curious/?utm_source=openai))
- **Supervisor가 decomposition까지 과도하게 수행**: 플래닝 토큰이 커져서 “결정 비용”이 본 작업보다 비싸지는 구간이 옵니다. 가능하면 분해는 규칙화(템플릿/분류)하고 LLM은 애매한 라우팅에만 쓰세요.
- **도구 스키마를 한 Agent에 과적재**: 툴 선택 오류 + 컨텍스트 혼탁. 2026년 LangGraph 쪽에서도 “tool-calling 기반 supervisor(수동 패턴)가 컨텍스트 엔지니어링 제어에 유리”하다고 강조합니다. ([reference.langchain.com](https://reference.langchain.com/python/langgraph-supervisor?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- Supervisor/worker는 호출 수가 늘어 **비용 상한**이 올라갑니다. 대신
  - 각 호출 목적이 좁아 품질이 안정되고
  - 재시도/부분 실패 복구가 쉬우며
  - 병렬 fan-out(리서치/추출) + merge로 지연을 줄일 여지가 있습니다. ([thesis.unipd.it](https://thesis.unipd.it/retrieve/ecc36f73-ac30-440c-8e89-6df0408d050c/Russo_Christian_Francesco.pdf?utm_source=openai))  
실무에선 “멀티 에이전트”라기보다 **오케스트레이션된 단일 목적 LLM 호출들의 그래프**로 보는 게 더 정확합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))

---

## 🚀 마무리
정리하면 2026년 8월 시점의 supervisor/worker 패턴은 “똑똑한 에이전트 팀”이라기보다, **컨텍스트와 실패를 통제하는 실행 아키텍처**입니다. 도입 판단 기준은 아래처럼 잡으면 실패 확률이 줄어듭니다.

- **단일 Agent로 품질/비용이 버티는가?** 버틴다면 멀티로 갈 이유가 약함
- **작업이 역할로 분해되고, 각 역할의 I/O를 스키마로 고정할 수 있는가?** 가능하면 supervisor/worker가 강력
- **재시도/중단/승인/감사 로그가 중요한가?** 중요할수록 중앙 오케스트레이션(그래프/상태머신)이 유리 ([arxiv.org](https://arxiv.org/abs/2607.19297?utm_source=openai))

다음 학습으로는 (1) OpenAI Agents SDK의 orchestration/manager-style 패턴(도구화/hand off), (2) LangGraph의 supervisor 패턴과 typed state/interrupt/checkpoint 설계를 같이 보길 추천합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/multi_agent/?utm_source=openai))