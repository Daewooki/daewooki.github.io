---
title: "2026년 5월, “확장 가능한 AI 앱”을 만드는 6가지 아키텍처 설계 패턴: MCP·Durable Execution·Observability까지"
date: 2026-05-13 04:03:48 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-05]
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
2026년 5월 기준 AI 애플리케이션(LLM/agent/RAG)은 “모델을 잘 고르는 문제”를 넘어 **아키텍처가 곧 품질/비용/신뢰성**을 결정하는 국면으로 넘어왔습니다. 특히 팀이 겪는 고통은 비슷합니다.

- PoC는 되는데 **프로덕션에서 실패 원인을 못 찾는다**(retrieval이 틀렸는지, tool이 죽었는지, 모델이 헛소리했는지).
- 기능이 늘수록 **LLM 호출이 직렬로 늘어나 p95 latency·비용이 폭발**한다.
- “툴 연동”이 늘수록 **권한/감사(audit)/정책 적용이 복잡**해진다.
- 장시간 작업(리포트 생성, 배치 분석, 워크플로우)이 **타임아웃/중단/재시도 지옥**으로 간다.

이 글은 “2026년 5월에 실제로 확장 가능한 구조”를 만들기 위한 패턴을 정리합니다. 핵심은 한 문장입니다:

> **Deterministic backbone(결정론적 오케스트레이션) + LLM은 ‘필요한 지점’에만 배치 + Durable Execution + Observability/평가가 기본값** ([zylos.ai](https://zylos.ai/research/2026-04-14-graph-based-agent-workflow-orchestration-production?utm_source=openai))

### 언제 쓰면 좋나
- 고객-facing AI 기능(헬프데스크, 리서치 요약, 내부 지식 Q&A)처럼 **오류 비용이 크고 트래픽이 있는 서비스**
- tool/API/DB 연동이 많은 “agentic workflow”
- SLA(p95 latency, 오류율, 비용/요청)가 있는 팀

### 언제 쓰면 안 되나
- 단발성 내부 스크립트(운영/감사 필요 없음)
- “대화만 잘하면 되는” 단순 챗봇(툴/데이터 연동 적음)  
  → 이 경우 오버엔지니어링이 됩니다.

---

## 🔧 핵심 개념
여기서는 “패턴”을 6개로 묶어, 내부 흐름(왜 이렇게 작동하는지)을 중심으로 설명합니다.

### 패턴 1) Deterministic Orchestrator + LLM Step(“LLM을 함수처럼”)
2026년 agent 시스템 설계에서 가장 중요한 변화는 **LLM이 워크플로우를 ‘전부’ 지배하게 두지 말고**, 상태 머신/그래프/DAG 같은 **결정론적 실행 뼈대**가 흐름을 통제하는 접근입니다. 연구/현업 가이드 모두 이 방향을 “승자 접근”으로 강조합니다. ([zylos.ai](https://zylos.ai/research/2026-04-14-graph-based-agent-workflow-orchestration-production?utm_source=openai))

- Orchestrator(그래프/워크플로우 엔진): 분기, 재시도, 타임아웃, 승인(HITL), 상태 저장
- LLM Step: 분류, 계획 생성, 요약, 스키마 변환, 후보 생성 등 “지능이 필요한 좁은 구간”

**차이점(LLM-first vs backbone-first)**  
- LLM-first(“ReAct로 계속 툴 호출”): 빠른 PoC, 그러나 호출이 늘면 비용/지연/디버깅이 망가짐
- backbone-first: 설계 비용이 들지만, **운영/확장/컴플라이언스**가 쉬워짐

### 패턴 2) Durable Execution(장시간·실패·재시도에 강한 실행 계층)
Agent/RAG는 외부 시스템(I/O)에 의존하므로 실패가 “정상 상태”입니다. 그래서 2026년에는 **durable execution + checkpointing**이 “있으면 좋은 것”이 아니라 기본 전제가 됐습니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/durable-execution?utm_source=openai))

- 각 step 실행 후 상태를 durable store에 저장
- 워커가 죽거나 타임아웃이 나도 **중간부터 재개**
- 재시도 정책(백오프/서킷브레이커/보상 트랜잭션)을 워크플로우 레벨에서 통일

### 패턴 3) MCP Gateway(툴 연동 표준화 + 권한/정책의 중앙집중)
툴 연동이 늘수록 “각 agent가 각 API에 직접 붙는” 구조는 곧 무너집니다. 2026년에는 MCP(Model Context Protocol)가 사실상 **툴/리소스/프롬프트를 표준 인터페이스로 노출**하는 축으로 자리잡고 있습니다. ([semantic.io](https://semantic.io/insights/model-context-protocol-deep-dive?utm_source=openai))

핵심은 **MCP Server(도구 제공) / MCP Client(앱) / Host**로 역할을 분리하고, JSON-RPC 기반으로 capabilities(tools/resources/prompts)를 노출한다는 점입니다. ([raftlabs.com](https://www.raftlabs.com/blog/model-context-protocol-explained?utm_source=openai))

프로덕션에서는 보통 “그냥 MCP”가 아니라:
- **MCP Gateway**: allowlist, 정책(OPA 등), 감사로그, rate-limit, tool sandboxing, PII 마스킹
- “tool을 보여주는 것”과 “자동 실행해도 되는 것”을 분리(중요)  
  (실무에서 이 2단 allowlist가 사고를 줄입니다—커뮤니티에서도 반복 언급) ([reddit.com](https://www.reddit.com/r/LLM_Gateways/comments/1s3hhol/best_mcp_gateway_in_2026_for_enterprise_ai/?utm_source=openai))

### 패턴 4) Async/Background + Streaming(긴 작업을 기본으로 다루기)
리서치/분석/코드 수정 같은 agent 작업은 수십 초~수 분이 자연스럽습니다. OpenAI Responses API는 **background mode**로 장시간 작업을 안정적으로 처리하는 패턴을 공식화했고, WebSocket 기반으로 agentic workflow의 상호작용 성능도 개선하고 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))

구조적으로는:
- request/response 동기 처리 → (대기/타임아웃/재시도 어려움)
- **job 기반 비동기**(enqueue → status poll/webhook → 결과 저장)로 전환

### 패턴 5) Guardrails를 “워크플로우 경계”가 아니라 “툴 호출마다” 건다
2025~2026의 중요한 교훈: 최종 답변만 검사하면 늦습니다. 실제 사고는 “툴 호출”에서 터집니다(권한 과다, 잘못된 파라미터, 데이터 유출 등). 그래서 Agents SDK는 **tool guardrails**(툴 실행 전/후 검증)를 별도 개념으로 강조합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/guardrails/?utm_source=openai))

### 패턴 6) Observability + Evaluation을 CI/CD에 연결(“LLM readiness”)
2026년의 “관찰 가능성”은 로그 몇 줄이 아니라,
- retrieval hit rate
- groundedness / policy compliance
- cost / p95 latency
- workflow success rate  
같은 지표를 **트레이스로 연결하고**, 배포 파이프라인에서 **quality gate**로 쓰는 방향으로 진화 중입니다. ([arxiv.org](https://arxiv.org/abs/2603.27355?utm_source=openai))

---

## 💻 실전 코드
시나리오: **“사내 Incident 요약/원인 추정”** 기능을 만든다고 가정합니다.

- 입력: incident id
- 흐름:
  1) DB/로그 시스템에서 데이터 가져오기(MCP tool)
  2) LLM로 “요약 + 원인 후보 + 다음 액션” 생성
  3) 결과 저장(다시 MCP tool)
- 요구: 확장성(비동기), 툴 호출마다 guardrail, 추적(Trace ID), 실패 재시도 기반

아래는 **OpenAI Responses API의 background mode**를 이용해 “job 형태”로 실행하는 최소 실전 골격입니다. (MCP Gateway는 HTTP endpoint로 가정해 붙입니다.)

### 1) 초기 셋업
```bash
python -m venv .venv
source .venv/bin/activate
pip install openai fastapi uvicorn httpx pydantic
export OPENAI_API_KEY="..."
export MCP_GATEWAY_URL="http://localhost:9000"   # 사내 MCP Gateway
```

### 2) FastAPI: 비동기 Job 실행 + MCP Gateway 연동
```python
# app.py
import os, json
from typing import Any, Dict, Optional
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from openai import OpenAI

app = FastAPI()
client = OpenAI()

MCP_GATEWAY_URL = os.environ["MCP_GATEWAY_URL"]

# ---- Models ----
class StartRequest(BaseModel):
    incident_id: str
    actor: str  # 요청자(권한/감사에 필요)

class StartResponse(BaseModel):
    response_id: str  # OpenAI background 작업 핸들

class StatusResponse(BaseModel):
    status: str
    result: Optional[Dict[str, Any]] = None

# ---- MCP Gateway helper ----
async def mcp_call(tool: str, args: Dict[str, Any], actor: str, trace_id: str) -> Dict[str, Any]:
    """
    MCP Gateway에 tool 실행을 요청.
    - 실무에서는 여기서 OPA 정책검사, allowlist, PII 마스킹, audit log가 같이 걸림.
    """
    payload = {
        "tool": tool,
        "args": args,
        "actor": actor,
        "trace_id": trace_id,
    }
    async with httpx.AsyncClient(timeout=30) as hx:
        r = await hx.post(f"{MCP_GATEWAY_URL}/call", json=payload)
        r.raise_for_status()
        return r.json()

# ---- API ----
@app.post("/incidents/start", response_model=StartResponse)
async def start(req: StartRequest):
    # 1) incident 데이터는 MCP tool로 가져온다 (LLM이 DB 직접 접근 X)
    trace_id = f"inc-{req.incident_id}"  # 실무: UUID + 상관관계 키
    incident = await mcp_call(
        tool="incidents.get_context",
        args={"incident_id": req.incident_id},
        actor=req.actor,
        trace_id=trace_id,
    )

    # 2) LLM은 “결정론적 뼈대”가 만든 컨텍스트를 받아서 생성만 한다
    prompt = {
        "incident": incident,
        "instructions": [
            "너는 SRE assistant다.",
            "출력은 반드시 JSON 하나로만 반환한다.",
            "키: summary, likely_root_causes (array), next_actions (array), confidence (0..1).",
            "근거는 incident 데이터에서 인용 가능한 범위에서만 작성한다."
        ],
    }

    # 3) background mode: 긴 작업을 job으로 실행 (타임아웃/재시도에 유리)
    resp = client.responses.create(
        model="gpt-4.1",  # 예시. 팀 표준 모델로 교체
        input=[
            {"role": "system", "content": "Return ONLY valid JSON. No prose."},
            {"role": "user", "content": json.dumps(prompt)}
        ],
        background=True,
        # 실무: metadata에 trace_id/actor/incident_id 넣어 observability 연결
        metadata={"trace_id": trace_id, "actor": req.actor, "incident_id": req.incident_id},
    )
    return StartResponse(response_id=resp.id)

@app.get("/incidents/status/{response_id}", response_model=StatusResponse)
async def status(response_id: str):
    r = client.responses.retrieve(response_id)

    # status: "in_progress" / "completed" 등
    if r.status != "completed":
        return StatusResponse(status=r.status)

    # output_text는 모델별/SDK별 다를 수 있어, 실제론 structured output 사용 권장.
    # 여기선 "JSON only"를 강제했으니 파싱 시도.
    text = r.output_text
    try:
        data = json.loads(text)
    except Exception:
        raise HTTPException(500, "Model did not return valid JSON")

    # 완료 후: MCP tool로 결과 저장(감사로그/권한/정책 적용 지점)
    trace_id = (r.metadata or {}).get("trace_id", "unknown")
    actor = (r.metadata or {}).get("actor", "unknown")
    await mcp_call(
        tool="incidents.store_analysis",
        args={"analysis": data},
        actor=actor,
        trace_id=trace_id,
    )

    return StatusResponse(status="completed", result=data)
```

### 예상 동작(현실적인 출력)
- `/incidents/start` → `{"response_id":"resp_..."}`
- `/incidents/status/resp_...`  
  - 진행 중: `{"status":"in_progress"}`
  - 완료:  
    ```json
    {
      "status": "completed",
      "result": {
        "summary": "2026-05-12 03:14 UTC부터 checkout API에서 5xx 급증...",
        "likely_root_causes": ["DB connection pool exhaustion", "Recent deploy regression in payment-service"],
        "next_actions": ["Rollback payment-service v2.3.7", "Increase pool size with cap", "Add alert on queue depth"],
        "confidence": 0.63
      }
    }
    ```

이 구조의 핵심은 **LLM이 DB/툴을 직접 “알아서” 만지는 게 아니라**,  
- tool 호출은 MCP Gateway로 표준화(정책/감사/권한의 중심)
- LLM은 생성/추론 스텝에만 집중
- 긴 작업은 background job으로 운영 가능  
이라는 점입니다. ([semantic.io](https://semantic.io/insights/model-context-protocol-deep-dive?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **툴 노출(visibility)과 자동 실행(auto-exec)을 분리**
- “모델이 볼 수 있는 툴” ≠ “승인 없이 실행해도 되는 툴”
- 실제로 많은 팀이 2단 allowlist로 사고를 줄입니다. ([reddit.com](https://www.reddit.com/r/LLM_Gateways/comments/1s3hhol/best_mcp_gateway_in_2026_for_enterprise_ai/?utm_source=openai))

2) **tool guardrail을 ‘모든 호출’에 걸기**
- agent-level output 검증만으로는 데이터 변경/유출을 막기 어렵습니다.
- Agents SDK도 tool guardrails를 별도 권장합니다. ([openai.github.io](https://openai.github.io/openai-agents-python/guardrails/?utm_source=openai))

3) **RAG/툴/모델 호출을 하나의 Trace로 엮기(OpenTelemetry 계열)**
- “모델 호출만 추적”하면 문제의 절반만 보입니다(대부분 upstream retrieval/tool에서 깨짐).
- 2026년에는 RAG 파이프라인을 span 단위로 쪼개 추적하는 접근이 확산 중입니다. ([uptrace.dev](https://uptrace.dev/guides/opentelemetry-rag-observability?utm_source=openai))

### 흔한 함정/안티패턴
- **직렬 tool-call 사슬**(LLM 왕복이 5~10번): 성능/비용이 선형이 아니라 체감상 폭발합니다. “결정론적 backbone + batch/병렬화”로 줄이세요. ([reddit.com](https://www.reddit.com/r/ClaudeCode/comments/1rs15x9/mcp_isnt_dead_tool_calling_is_whats_dying/?utm_source=openai))
- **MCP 도입 = 보안 해결**이라고 착각: MCP는 표준 인터페이스일 뿐, 정책·권한·감사·샌드박싱은 별도 레이어가 필요합니다. ([techradar.com](https://www.techradar.com/pro/how-to-reliably-connect-llms-to-real-world-data-and-systems?utm_source=openai))
- **평가 없는 배포**: offline benchmark만으로는 운영 품질이 유지되지 않습니다. CI gate(시나리오 기반 readiness score)로 막아야 합니다. ([arxiv.org](https://arxiv.org/abs/2603.27355?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- Durable execution/observability를 붙이면 초기 개발 속도는 느려지지만, **장기적으로 incident 대응/디버깅 비용이 크게 감소**합니다.
- background job은 UX가 즉답형보다 복잡(상태 조회 필요)하지만, **타임아웃/재시도/부하제어** 측면에서 안정적입니다. ([platform.openai.com](https://platform.openai.com/docs/guides/background?utm_source=openai))
- MCP Gateway는 중앙집중형이므로 병목이 될 수 있어, rate-limit/캐시/큐잉을 같이 설계해야 합니다(특히 tool latency가 긴 경우).

---

## 🚀 마무리
2026년 5월의 “확장 가능한 AI 앱 아키텍처”는 유행하는 프레임워크 이름보다, 다음 3가지를 갖췄는지로 판단하는 게 정확합니다.

1) **Deterministic backbone**이 실행을 통제하는가? (LLM은 특정 step에만) ([zylos.ai](https://zylos.ai/research/2026-04-14-graph-based-agent-workflow-orchestration-production?utm_source=openai))  
2) **Durable execution + async**로 실패/장시간 작업이 기본 처리되는가? ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/durable-execution?utm_source=openai))  
3) **MCP/툴 정책/guardrails/observability/evaluation**이 운영 기본값인가? ([semantic.io](https://semantic.io/insights/model-context-protocol-deep-dive?utm_source=openai))  

### 다음 학습 추천(순서)
- MCP: capabilities 설계(툴 스키마, 권한 모델, gateway 패턴) ([semantic.io](https://semantic.io/insights/model-context-protocol-deep-dive?utm_source=openai))  
- Durable execution: LangGraph durable execution 개념/상태 모델링 ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/durable-execution?utm_source=openai))  
- Observability: RAG 파이프라인을 span으로 쪼개는 OTel 접근 ([uptrace.dev](https://uptrace.dev/guides/opentelemetry-rag-observability?utm_source=openai))  

원하면, 위 예제를 **(1) LangGraph 기반 그래프 오케스트레이션 버전** 또는 **(2) MCP Gateway에 OPA(Rego) 정책을 붙인 버전**으로 확장해 드릴게요.