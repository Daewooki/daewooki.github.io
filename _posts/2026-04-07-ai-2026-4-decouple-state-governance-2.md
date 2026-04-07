---
title: "AI 앱 아키텍처, 2026년 4월의 정답은 “분리(Decouple) + 상태(State) + 거버넌스(Governance)”다"
date: 2026-04-07 03:19:29 +0900
categories: [Backend, Architecture]
tags: [backend, architecture, trend, 2026-04]
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
2024~2025년의 AI 앱은 “LLM API 호출 + RAG”만 붙여도 제품이 됐습니다. 하지만 2026년 4월 기준, 현업에서 부딪히는 병목은 달라졌습니다.

- 기능이 늘수록 프롬프트가 비대해져 **monolithic agent**가 되고, 변경/테스트/롤백이 어려워짐
- 도구(tool)·데이터 소스가 늘면서 통합이 파편화되고, 권한/감사/보안이 **아키텍처 레벨 문제**로 튀어나옴
- 멀티스텝(계획→실행→검증) 워크플로우가 기본이 되며, “LLM 한 번 호출” 모델로는 **확장성(throughput)과 신뢰성**을 맞추기 어려워짐

특히 도구 연결은 MCP(Model Context Protocol) 같은 표준을 중심으로 재편되는 흐름이 뚜렷하고, 동시에 agentic 보안 위협(Goal Hijack, Tool Misuse, Inter-agent comms 등)을 전제로 설계해야 합니다. ([modelcontextprotocol.io](https://modelcontextprotocol.io/docs/learn/architecture?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Orchestrator-Worker 패턴: “계획은 얇게, 실행은 분산으로”
요즘 확장 가능한 AI 앱은 **Orchestrator(오케스트레이터)** 가 작업을 쪼개고, **Worker(워커)** 들이 도메인 단위로 수행합니다. 장점은 명확합니다.

- Orchestrator는 “무엇을/어떤 순서로”만 결정 → 프롬프트/정책/가드레일이 한 곳에 모여 **통제 가능**
- Worker는 “한 가지 도구/책임”에 집중 → 병렬 실행, 재시도, 캐시가 쉬워 **스케일링 유리**
- 워커 간 계약(contract)을 **schema(JSON Schema/Pydantic/Zod)** 로 고정하면, agent-to-agent 통신 품질이 급상승 ([sitepoint.com](https://www.sitepoint.com/the-definitive-guide-to-agentic-design-patterns-in-2026/?utm_source=openai))

핵심은 “LLM을 똑똑하게 만들기”보다, **LLM이 지휘하는 실행 시스템**을 클라우드 네이티브처럼 분해하는 겁니다.

### 2) Stateful Graph 패턴: “대화가 아니라 워크플로우를 모델링”
실무에서 “한 번 답변”보다 중요한 건 **진행 상태**입니다.

- 입력 정규화 → 계획 수립 → 검색/도구 실행 → 검증/리라이트 → 감사 로그
- 여기서 상태(state)는 단순 채팅 히스토리가 아니라, **typed state(구조화된 실행 컨텍스트)** 여야 합니다.
- 이 상태가 있어야 idempotency(중복 실행 방지), 재시도, 부분 실패 격리, 관측성(트레이싱)이 됩니다.

Agentic RAG도 같은 방향으로 진화합니다. 단순 “retrieval 1회”가 아니라, 계획 기반으로 **iterative retrieval / memory 관리 / tool-invocation** 을 반복하는 구조가 정리되고 있습니다. ([arxiv.org](https://arxiv.org/abs/2603.07379?utm_source=openai))

### 3) Tool Interface 표준화(MCP): “연결을 코드가 아니라 프로토콜로”
도구 통합을 SDK/어댑터로만 쌓으면 팀/서비스마다 연결 방식이 달라져 운영이 지옥이 됩니다. MCP는 이를 **클라이언트-호스트-서버 구조**로 표준화하고(JSON-RPC 기반), 한 앱(Host)이 여러 MCP Server(툴 제공자)에 연결하는 형태를 제시합니다. ([modelcontextprotocol.io](https://modelcontextprotocol.io/specification/2025-06-18/architecture?utm_source=openai))

중요 포인트는 “도구를 붙인다”가 아니라:
- 도구 목록/스키마/알림(notification) 등 컨텍스트 교환을 표준으로 다루고
- 향후 transport scalability, agent communication, governance까지 로드맵에 포함되어 있다는 점입니다 ([blog.modelcontextprotocol.io](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/?utm_source=openai))

### 4) 거버넌스-퍼스트: OWASP가 말하는 “AI가 무엇을 하게 둘 것인가”
2025 LLM 앱 보안은 Prompt Injection 등 “출력/프롬프트 중심”이 강했고, 2026 Agentic은 “AI가 실행하는 행위” 자체가 위협면입니다. ([owasp.org](https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf?utm_source=openai))

그래서 아키텍처 패턴도 바뀝니다:
- 최소 권한 도구권한(least privilege) + 동적 승인(consent)
- 실행 전/후 정책 검사(policy check)
- 툴 호출/외부 요청/데이터 접근에 대한 감사 추적(audit trail)

---

## 💻 실전 코드
아래 예시는 “Orchestrator-Worker + Structured Output + 정책 게이트”의 최소 구현입니다.  
실제 LLM 호출은 공급자별로 다르니, 여기서는 **LLM이 반환한다고 가정한 JSON**을 검증/실행하는 쪽에 집중합니다(=아키텍처 뼈대).

```python
# python 3.11+
# pip install pydantic

from __future__ import annotations
from pydantic import BaseModel, Field, ValidationError
from typing import Literal, List, Optional, Dict, Any
import time

# 1) Worker 계약(Contract): 에이전트/워커 사이 메시지를 스키마로 고정
class PlanStep(BaseModel):
    kind: Literal["tool", "retrieval", "final"]
    name: str = Field(..., description="tool name or step name")
    args: Dict[str, Any] = Field(default_factory=dict)
    risk: Literal["low", "medium", "high"] = "low"

class ExecutionPlan(BaseModel):
    goal: str
    steps: List[PlanStep]

# 2) Tool registry: MCP 같은 표준을 쓰더라도 결국 "서버/툴 카탈로그" 개념이 필요
def tool_send_email(to: str, subject: str, body: str) -> str:
    # 실제로는 SMTP/Provider API 호출
    return f"EMAIL_SENT(to={to}, subject={subject})"

def tool_sql_query(query: str) -> list[dict]:
    # 실제로는 read-only replica / sandbox에서 실행해야 함
    if "delete" in query.lower():
        raise PermissionError("Destructive query is blocked")
    return [{"id": 1, "name": "alice"}]

TOOLS = {
    "send_email": tool_send_email,
    "sql_query": tool_sql_query,
}

# 3) Policy gate: OWASP Agentic 관점에서 "도구 오용"을 아키텍처에서 차단
def policy_check(step: PlanStep) -> None:
    # 간단 예: high risk는 사람 승인 필요(여기선 예외로 차단)
    if step.risk == "high":
        raise PermissionError(f"Step '{step.name}' requires human approval")

    # 도구 allowlist
    if step.kind == "tool" and step.name not in TOOLS:
        raise PermissionError(f"Tool '{step.name}' is not allowed")

# 4) Orchestrator: 계획을 해석하고 워커를 실행(분산 실행은 큐/워크플로 엔진으로 확장)
def execute_plan(plan: ExecutionPlan) -> dict:
    trace = {"goal": plan.goal, "events": []}
    for i, step in enumerate(plan.steps, start=1):
        t0 = time.time()
        policy_check(step)

        if step.kind == "tool":
            fn = TOOLS[step.name]
            result = fn(**step.args)  # 스키마 기반 args라면 여기서 타입 안정성↑
        elif step.kind == "retrieval":
            # 예: vector search / keyword search 등을 붙이는 자리
            result = {"docs": ["doc1...", "doc2..."], "query": step.args.get("q", "")}
        else:  # final
            result = step.args.get("answer", "")

        trace["events"].append({
            "seq": i,
            "step": step.model_dump(),
            "result": result,
            "latency_ms": int((time.time() - t0) * 1000),
        })
    return trace

# ---- demo ----
if __name__ == "__main__":
    # LLM이 반환했다고 가정한 JSON(Structured Output)
    llm_json = {
        "goal": "고객 목록을 조회하고 요약 메일 발송",
        "steps": [
            {"kind": "tool", "name": "sql_query", "args": {"query": "select id, name from customers limit 10"}, "risk": "low"},
            {"kind": "tool", "name": "send_email", "args": {"to": "ops@company.com", "subject": "요약", "body": "고객 10명 조회 완료"}, "risk": "medium"},
            {"kind": "final", "name": "respond", "args": {"answer": "완료했습니다."}, "risk": "low"},
        ]
    }

    try:
        plan = ExecutionPlan.model_validate(llm_json)  # 스키마 검증(실패하면 재프롬프트/수정 루프)
        trace = execute_plan(plan)
        print(trace)
    except ValidationError as e:
        print("PLAN_SCHEMA_INVALID:", e)
    except Exception as e:
        print("EXECUTION_FAILED:", e)
```

이 코드의 요지는 “LLM이 곧 코드”가 아니라, **LLM은 계획(데이터)을 내고 시스템이 실행**한다는 점입니다. 이 구조가 되어야 스케일링(큐/병렬/재시도/관측성)과 보안(정책 게이트)이 들어갑니다.

---

## ⚡ 실전 팁
1) **Compute / State / Governance를 물리적으로 분리**
- Compute: 모델 호출, 워커 실행
- State: 대화/작업 상태(typed state), 장기 메모리, 벡터 인덱스
- Governance: 정책/권한/감사/키관리  
이 분리가 되어야 “모델 바꾸기”, “툴 추가”, “권한 강화”가 서로 발목을 안 잡습니다. (멀티에이전트 스케일링 글들이 반복해서 강조하는 지점도 결국 이 분리입니다.) ([nexaitech.com](https://nexaitech.com/multi-ai-agent-architecutre-patterns-for-scale/?utm_source=openai))

2) **Structured Output을 ‘옵션’이 아니라 ‘기본 계약’으로**
- agent-to-agent / agent-to-tool 모두 스키마로 고정
- 실패 시: (a) 자동 재요청 (b) 부분 수정 (c) fallback 모델  
멀티에이전트에서 “한 에이전트 출력이 다른 에이전트 입력”이 되면, 포맷 흔들림이 곧 장애입니다. ([androidcentral.com](https://www.androidcentral.com/apps-software/ai/google-is-making-it-easier-to-use-the-gemini-api-in-multi-agent-workflows?utm_source=openai))

3) **RAG는 ‘검색’이 아니라 ‘제어 루프’로 설계**
Agentic RAG 흐름에서는
- 불확실하면 더 찾고
- 충돌하면 재질의하고
- 메모리를 갱신/폐기하는
루프가 핵심입니다. 단발 retrieval로는 비용만 늘고 품질이 불안정해집니다. ([arxiv.org](https://arxiv.org/abs/2603.07379?utm_source=openai))

4) **MCP 도입 시, “연결”보다 “신뢰 경계(trust boundary)”를 먼저 그리기**
MCP는 통합을 가속하지만, 도구/서버가 늘수록 공격면도 커집니다. MCP 자체 공격면을 체계화한 위협 분류(MCP-38)처럼, 프로토콜/툴 계층의 위협을 별도로 모델링하세요. ([arxiv.org](https://arxiv.org/abs/2603.18063?utm_source=openai))

5) **OWASP Top 10을 아키텍처 체크리스트로 “매핑”**
LLM 앱(2025)과 Agentic 앱(2026)은 포커스가 다릅니다. “무슨 말을 하게 할 것인가”에서 “무슨 행동을 하게 둘 것인가”로 중심이 이동했습니다.  
- 도구 오용/권한 남용/에이전트 목표 하이재킹을 전제로
- 실행 전 정책 게이트, 인간 승인, 감사 로그를 설계에 포함하세요 ([owasp.org](https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf?utm_source=openai))

---

## 🚀 마무리
2026년 4월의 AI 애플리케이션 아키텍처 설계 패턴을 한 줄로 요약하면:

- **오케스트레이션은 중앙에서 얇게(Orchestrator), 실행은 도메인 단위로 두껍게(Worker)**
- **상태는 typed state로, 워크플로우는 graph/plan으로**
- **툴 통합은 표준(MCP)로, 보안은 OWASP Agentic 관점으로 거버넌스-퍼스트**

다음 학습으로는 (1) MCP 기반 툴 카탈로그/권한 모델 설계, (2) agentic RAG의 planning+retrieval 루프 구현, (3) OWASP LLM(2025)·Agentic(2026) Top 10을 자사 아키텍처에 매핑한 보안 설계 문서화를 추천합니다. ([blog.modelcontextprotocol.io](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/?utm_source=openai))