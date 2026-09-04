---
title: "컨텍스트 윈도우로는 부족하다: AI Agent 장단기 메모리 & Long-term 상태 관리 구현 가이드"
description: "2026년 7월 기준, “에이전트가 똑똑해지면 된다”는 기대는 대부분 깨졌습니다. 실제 장애는 모델 성능보다 state(상태) 관리에서 터집니다. 대표 증상은 아래와 같습니다."
date: 2026-07-26 03:38:52 +0900
categories: [AI, Agent]
tags: [ai, agent]
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
2026년 7월 기준, “에이전트가 똑똑해지면 된다”는 기대는 대부분 깨졌습니다. 실제 장애는 **모델 성능보다 state(상태) 관리**에서 터집니다. 대표 증상은 아래와 같습니다.

- 며칠/몇 주 걸리는 업무에서 **중간에 프로세스가 죽으면 처음부터 재시도**(비용 폭발 + 사용자 신뢰 하락)
- 대화 로그를 다 넣으면 토큰이 터지고, 안 넣으면 **중요한 사용자 선호/결정이 유실**
- “기억”을 벡터DB 하나로 해결하려다 **오염된 기억**, 잘못된 회상, 삭제 요청 대응 불가

언제 쓰면 좋나?
- **장시간/다단계 워크플로우**(리서치, 코드 리뷰, 운영 티켓 처리, 세일즈/CS 케이스 핸들링)
- **사람 승인(HITL)**, 외부 I/O 대기, 재시도/재개(resume)가 필수인 업무
- “기억”이 제품 가치(개인화/일관성/재사용)를 만드는 경우

언제 쓰면 안 되나?
- 1~2턴 내 끝나는 단발성 Q&A(상태 저장이 오히려 복잡도/비용만 증가)
- 규정상 장기 저장이 어려운 데이터(PII/민감정보)를 **설계 없이** 다루는 경우
- “기억”이 모델 답변을 과도하게 고정시키면 위험한 도메인(의료/법률)에서 검증 체계 없이 적용

핵심 메시지: 2026년형 에이전트에서 memory는 “기능”이 아니라 **분산시스템의 state**입니다. Vercel도 agent memory를 사실상 state management 문제로 봐야 한다고 강조합니다.[^1]

---

## 🔧 핵심 개념
### 1) 메모리는 1개가 아니라 “계층”이다
최근 글/가이드들이 공통으로 정리하는 구조는 대략 4층입니다:  
- **Short-term (in-context)**: 현재 프롬프트에 들어가는 최근 대화/작업 맥락  
- **Working state (KV/structured state)**: 실행 중 필요한 구조화 상태(주문ID, 워크플로우 단계, 승인 여부 등)  
- **Long-term semantic memory (retrieval store)**: 오래 유지할 지식/경험을 임베딩/문서 형태로 저장 후 검색  
- **Procedural memory**: 규칙/정책/행동 양식(시스템 프롬프트, 도구 사용 규약, 템플릿)[^2]

여기서 실전에서 중요한 구분:
- **대화 히스토리 저장 = Session memory**
- **“교훈/요약/선호”를 추출해 저장 = Agent memory**
OpenAI Agents SDK도 Session(대화 기록)과 Memory(교훈을 파일로 증류)를 명확히 분리합니다.[^3]

### 2) “장기 상태 관리”는 결국 두 문제다: Durability + Recall
#### (A) Durability(내구성): 중단돼도 정확히 이어서 실행
LangGraph는 **durable execution / persistence**를 핵심 가치로 내세우며, 체크포인터를 통한 단기 메모리(스레드별 실행 상태)와 store를 통한 장기 메모리(스레드 너머 지속 데이터)를 개념적으로 분리합니다.[^4]  
OpenAI Agents SDK 역시 **snapshotting/rehydration**로 컨테이너가 바뀌어도 상태를 복원해 이어가는 방향을 강화했습니다.[^5]

내구성 설계의 핵심은 “대화 저장”이 아니라:
- **어떤 단계까지 커밋됐는지**
- **툴 호출이 idempotent한지**
- **재개 시 중복 실행/중복 결제/중복 티켓 생성이 안 나는지**
입니다.

#### (B) Recall(회상): 필요한 기억만 정확히 꺼내기 + 업데이트/삭제 가능
Redis는 long-term memory를 “저장소 하나”가 아니라 **raw 이벤트 → 정제/요약 → 인덱싱 → 검색** 파이프라인으로 보며, latency/cost/forgetting 트레이드오프를 강조합니다.[^6]  
또 2026년 연구들은 “무작정 텍스트를 쌓는 기억”이 **provenance-role collapse(출처/역할 붕괴)** 같은 실패 모드를 만든다고 지적하며 typed/구조화 표현의 필요성을 제기합니다.[^7]

### 3) 다른 접근과의 차이점(현실적 판단 기준)
- **Context stuffing(긴 컨텍스트 창)**: 구현은 쉬우나 비용/지연이 선형 증가. “삭제/감사/재현”이 어려움.
- **Vector DB only**: semantic recall은 되지만 “현재 단계/승인/결제 상태” 같은 **정확성이 필요한 상태**에는 부적합.
- **Durable workflow + memory distillation(추천)**:  
  - 실행 상태는 **DB/체크포인트**로 정확히 관리  
  - 장기 기억은 **요약/typed fact**로 제한 저장  
  - 검색은 “필요할 때만” 컨텍스트에 주입

---

## 💻 실전 코드
아래는 “고객사 장애 티켓을 처리하는 에이전트”를 가정합니다.

요구사항:
- 티켓 처리 중 사람 승인 대기 가능(수 시간~수일)
- 중간에 서버가 재시작돼도 이어서 처리
- 장기 기억: 고객별 선호(연락 방식, 금지된 조치), 과거 해결책 요약
- 단기 상태: 현재 워크플로우 단계, 티켓ID, 이미 수행한 액션들(중복 방지)

구현 전략:
- **Durable execution/state**: LangGraph persistence(checkpointer + store)
- **Long-term memory**: 별도 “memory writer”가 이벤트를 요약/정규화해 store에 저장
- **Short-term**: 실행 시점에만 최근 메시지/필요 기억을 주입

> 주의: LangGraph 버전/스토리지 어댑터는 환경에 따라 다릅니다. 아래 코드는 “구조/패턴”에 초점을 둔 실행 가능한 골격입니다(로컬 SQLite + 파일 기반 벡터 인덱스 등으로 쉽게 치환 가능). LangGraph는 durable execution/persistence를 공식 컨셉으로 제공합니다.[^8]

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install langgraph==1.2.9 langchain openai pydantic sqlite-utils
export OPENAI_API_KEY="..."
```

### 1) 상태 스키마 + 체크포인트 + 장기 store
```python
from __future__ import annotations
from typing import TypedDict, Literal, Optional, List, Dict
from pydantic import BaseModel
import hashlib
import time

# (A) 워크플로우 실행 상태 (정확성이 중요: KV/structured)
class TicketState(TypedDict, total=False):
    thread_id: str
    ticket_id: str
    stage: Literal["triage", "propose_fix", "await_approval", "execute_fix", "done"]
    last_error: Optional[str]
    actions_done: List[str]            # idempotency 키 기록
    customer_id: str

# (B) 장기 기억(typed facts) 모델
class CustomerMemory(BaseModel):
    customer_id: str
    preferences: Dict[str, str] = {}   # e.g. {"contact_channel": "email"}
    banned_actions: List[str] = []     # e.g. ["restart-db"]
    resolutions: List[str] = []        # 짧은 요약들(감사/삭제 가능하게)

def idempotency_key(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
```

### 2) “기억 쓰기”는 별도 단계로(요약/정규화/스코프)
핵심은 **무조건 저장하지 말고, 저장 기준을 코드로 박아두는 것**입니다.

```python
def distill_memory_from_event(state: TicketState, event: dict) -> Optional[CustomerMemory]:
    """
    event 예: {"type":"user_feedback","text":"전화 말고 이메일로 주세요"}
    """
    cid = state["customer_id"]
    mem = CustomerMemory(customer_id=cid)

    if event["type"] == "user_feedback":
        text = event.get("text", "")
        if "이메일" in text:
            mem.preferences["contact_channel"] = "email"
            mem.resolutions.append("고객 연락은 email 선호(피드백 기반).")
            return mem

    if event["type"] == "postmortem":
        # 과도한 원문 저장 대신, 1~2문장 요약만 남김(추후 삭제/정정 가능)
        summary = event.get("summary")
        if summary:
            mem.resolutions.append(summary[:200])
            return mem

    return None
```

### 3) 그래프 노드: (1) 트리아지 → (2) 해결책 제안 → (3) 승인 대기 → (4) 실행
실행 단계에서 중요한 건:
- 실행(state)과 기억(memory)을 섞지 말고
- 실행은 체크포인트로, 기억은 store로
- “실행”은 idempotent하게

```python
from langgraph.graph import StateGraph, END

# (가정) store API는 프로젝트별로 래핑하세요.
# LangGraph는 checkpointer/store를 통한 persistence 개념을 제공합니다.[^4]
MEM_DB: Dict[str, CustomerMemory] = {}  # 데모용(실무는 DB)

def load_customer_memory(customer_id: str) -> CustomerMemory:
    return MEM_DB.get(customer_id, CustomerMemory(customer_id=customer_id))

def merge_customer_memory(new_mem: CustomerMemory):
    cur = load_customer_memory(new_mem.customer_id)
    cur.preferences.update(new_mem.preferences)
    cur.banned_actions = sorted(set(cur.banned_actions + new_mem.banned_actions))
    cur.resolutions = (cur.resolutions + new_mem.resolutions)[-50:]  # 상한선
    MEM_DB[new_mem.customer_id] = cur

def triage(state: TicketState) -> TicketState:
    state["stage"] = "triage"
    return state

def propose_fix(state: TicketState) -> TicketState:
    state["stage"] = "propose_fix"
    mem = load_customer_memory(state["customer_id"])

    # 예: 고객이 이메일 선호면 커뮤니케이션 플랜도 바꿈
    channel = mem.preferences.get("contact_channel", "chat")
    # (여기서 LLM 호출해도 되지만 예시는 상태 흐름에 집중)
    state["last_error"] = None
    state["actions_done"] = state.get("actions_done", [])
    state["proposed_plan"] = f"1) 로그 수집 2) 설정 점검 3) 고객에게 {channel}로 진행상황 공유"
    return state

def await_approval(state: TicketState) -> TicketState:
    state["stage"] = "await_approval"
    # 현실: human approval tool / ticketing webhook 대기
    # durable workflow에서는 이 지점이 '재개 가능'해야 함
    return state

def execute_fix(state: TicketState) -> TicketState:
    state["stage"] = "execute_fix"
    mem = load_customer_memory(state["customer_id"])

    action = "restart-db"
    if action in mem.banned_actions:
        state["last_error"] = f"Action '{action}' is banned for this customer."
        return state

    key = idempotency_key(state["ticket_id"], "execute", action)
    done = set(state.get("actions_done", []))
    if key in done:
        # 재시도/재개 시 중복 실행 방지
        return state

    # (실제 실행) 외부 시스템 호출은 반드시 idempotency 키를 함께 전달하는 구조로
    time.sleep(0.2)  # 데모

    done.add(key)
    state["actions_done"] = list(done)
    return state

def done(state: TicketState) -> TicketState:
    state["stage"] = "done"
    # 사후 요약을 memory로 증류 저장(원문 전체 저장 X)
    mem = distill_memory_from_event(state, {
        "type": "postmortem",
        "summary": f"Ticket {state['ticket_id']} 해결: 설정 누락 수정 후 정상화."
    })
    if mem:
        merge_customer_memory(mem)
    return state

def route(state: TicketState) -> str:
    if state.get("stage") in (None, "triage"):
        return "propose_fix"
    if state["stage"] == "propose_fix":
        return "await_approval"
    if state["stage"] == "await_approval":
        # 데모: 승인 받았다고 가정
        return "execute_fix"
    if state["stage"] == "execute_fix":
        if state.get("last_error"):
            return "done"  # 실패 처리/에스컬레이션으로 분기 가능
        return "done"
    return "done"

graph = StateGraph(TicketState)
graph.add_node("triage", triage)
graph.add_node("propose_fix", propose_fix)
graph.add_node("await_approval", await_approval)
graph.add_node("execute_fix", execute_fix)
graph.add_node("done", done)

graph.set_entry_point("triage")
graph.add_conditional_edges("triage", route, {
    "propose_fix": "propose_fix",
})
graph.add_conditional_edges("propose_fix", route, {
    "await_approval": "await_approval",
})
graph.add_conditional_edges("await_approval", route, {
    "execute_fix": "execute_fix",
})
graph.add_conditional_edges("execute_fix", route, {
    "done": "done",
})
graph.add_edge("done", END)

app = graph.compile()
```

### 예상 실행(핵심 출력)
```python
initial: TicketState = {
    "thread_id": "thread-001",
    "ticket_id": "INC-20260726-1234",
    "customer_id": "cust-42",
    "actions_done": [],
}

final = app.invoke(initial)
print(final["stage"])
print(final.get("proposed_plan"))
print(MEM_DB["cust-42"].resolutions[-1])
```

예상:
- `stage == "done"`
- `proposed_plan`에 고객 선호 채널 반영
- `resolutions`에 티켓 요약 1줄 저장

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3)
1) **메모리를 “쓰기/읽기” 분리하고, 쓰기는 엄격한 기준으로**
- OpenAI도 Session(히스토리)과 Memory(교훈 증류)를 분리합니다.[^3]  
- 실무에선 “무엇을 기억할 가치가 있는가”를 룰로 고정(선호/제약/결정/검증된 해결책 등).

2) **Durable execution을 먼저, RAG는 나중에**
- 장기 작업에서 가장 치명적인 건 “좋은 답”이 아니라 “재개 실패/중복 실행”입니다. LangGraph는 durable execution/persistence를 전면에 둡니다.[^8]  
- 외부 시스템 호출은 idempotent 키를 전파하세요(결제/티켓/배포).

3) **Typed memory(구조화)로 provenance를 보존**
- 2026년 연구는 unstructured flat text 메모리가 출처/역할 붕괴 같은 실패 모드를 유발할 수 있다고 경고합니다.[^7]  
- “누가 말했는지/언제 확정됐는지/근거 링크”를 스키마로 들고 가면 디버깅이 급격히 쉬워집니다.

### 흔한 함정/안티패턴
- **대화 로그 전체를 long-term에 누적**: 검색 품질 악화 + 삭제/정정/감사 불가능 + 토큰/스토리지 증가
- **Vector DB를 state DB처럼 사용**: “정확히 한 번 실행”이 필요한 상태를 유사검색으로 처리하면 언젠가 터집니다.
- **Persistence를 신뢰하면서 보안은 무시**: 메모리/직렬화/체크포인트는 공격 표면이 됩니다. 실제로 state persistence 관련 취약점 이슈가 보고되었고, 패치/설계가 보안 컴포넌트 취급을 받아야 합니다.[^9]

### 비용/성능/안정성 트레이드오프
- **Recall 품질 vs Latency**: 검색을 자주/많이 하면 정확도는 오를 수 있으나 p95가 무너집니다. Redis도 latency/cost/forgetting 균형을 강조합니다.[^6]  
- **기억의 양 vs 유지보수성**: 많이 저장할수록 “정정/삭제/충돌 해결” 비용이 커집니다.
- **Durability vs 구현 복잡도**: 체크포인트/재개/멱등성은 초기 설계 비용이 크지만, 운영 단계에서 장애 비용을 압도적으로 줄입니다.

---

## 🚀 마무리
정리하면, 2026년 7월의 “AI Agent memory long-term 상태 관리”는 다음 3가지를 동시에 만족해야 합니다.

1) **Durable execution**: 중단/재시작/대기(HITL)에도 정확히 이어서 실행  
2) **Memory distillation**: 대화 저장이 아니라 “교훈/선호/제약”을 구조화해 저장  
3) **Selective recall**: 필요한 순간에만, 검증 가능한 형태로 컨텍스트에 주입

도입 판단 기준(체크리스트):
- 내 에이전트가 **30분 이상 실행되거나**, 승인/대기가 들어가나?
- 외부 시스템 호출이 있고, 중복 실행이 곧 장애인가?
- 사용자/고객별로 “선호/금지/결정”이 반복되어 비용을 만들고 있나?
- 저장/삭제/감사(“왜 이런 결정을 했나?”) 요구가 있는가?

다음 학습 추천:
- OpenAI Agents SDK의 **Session vs Memory 분리**, snapshot/rehydration 개념 정리[^3]  
- LangGraph의 **persistence(durable execution, checkpointer/store)** 아키텍처 패턴[^4]  
- “무구조 텍스트 기억의 실패 모드”와 typed memory 접근(연구)[^7]

[^1]: <https://vercel.com/i/agent-memory>
[^2]: <https://zalt.me/blog/2026/07/ai-agent-memory-and-state>
[^3]: <https://openai.github.io/openai-agents-js/guides/sessions/>
[^4]: <https://langchain-ai.github.io/langgraph/concepts/time-travel/?h=time+travel>
[^5]: <https://openai.com/index/the-next-evolution-of-the-agents-sdk/>
[^6]: <https://redis.io/blog/long-term-memory-architectures-ai-agents/>
[^7]: <https://arxiv.org/abs/2605.25869>
[^8]: <https://github.com/langchain-ai/langgraph>
[^9]: <https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/06/CSA_research_note_langgraph_rce_chain_CVE_20260612-csa-styled.pdf>
