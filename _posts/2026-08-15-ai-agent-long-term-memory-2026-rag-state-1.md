---
title: "AI Agent “Long-term Memory + 상태 관리”를 2026년에 제대로 구현하는 법: RAG를 넘어 실행 상태(State)로 다루기"
date: 2026-08-15 01:40:18 +0900
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

AI Agent를 프로덕션에 올리면, 제일 먼저 터지는 건 대개 “추론 능력”이 아니라 **메모리와 상태(state) 일관성**입니다. 데모에서는 잘 되던 에이전트가 실서비스에서 갑자기:

- 재시작 후 **이전 승인/결정**을 잊고 같은 질문을 반복하거나
- 과거에 잘못 수행했던 tool call을 **다시 실행**해서 비용을 태우거나
- “사용자 선호/정책” 같은 **stable fact**가 대화 요약 과정에서 drift(변질)되거나
- 세션/스레드가 길어지면 **컨텍스트가 비대해져 latency/비용이 폭발**합니다.

2026년 관점에서 중요한 포인트는 “long-term memory = 벡터DB”가 아니라, **메모리를 ‘실행 상태 관리(execution state management)’의 문제로 재정의**해야 한다는 흐름입니다. 최근 연구는 단순 semantic retrieval이 long-horizon 작업에서 상태 의존성을 깨뜨리고(올바른 트레이스와 오류 트레이스가 섞임) 실패를 유발한다고 지적하며, 상태 트리 기반으로 “현재 실행 경로”를 보존하는 접근을 제안합니다. ([arxiv.org](https://arxiv.org/abs/2606.06090?utm_source=openai)) 또한 장기 메모리를 “DB workload”로 보고 ingestion/revision/forgetting 같은 **state-level operator**가 필요하다는 주장도 나왔습니다. ([arxiv.org](https://arxiv.org/abs/2605.26252?utm_source=openai))

### 언제 쓰면 좋은가
- 사용자와 상호작용이 “한 번에 끝나는” 게 아니라 **반복/누적되는 제품**(B2B 운영, 고객지원, 코딩/리서치 어시스턴트)
- 작업이 길고 중단/재개가 잦은 **long-running workflow**
- “기억”이 곧 **정책/승인/결정 로그**가 되어 감사(audit)가 필요한 도메인

### 언제 쓰면 안 되는가
- 단발성 Q&A, stateless batch 처리처럼 **상태가 가치가 없는 작업**
- 개인정보/규제 부담이 크고, “기억”이 제품 가치에 핵심이 아니라면(저장 자체가 리스크)
- 메모리를 붙여도 결국 source of truth는 기존 시스템인데, 그 경계를 설계하지 않고 “에이전트가 알아서 기억”하게 만들 때(거의 항상 사고 납니다)

---

## 🔧 핵심 개념

### 1) “메모리”를 3층으로 쪼개지 않으면 상태가 붕괴한다
2026년 실무 글/가이드들의 공통 결론은 **hybrid layered memory**입니다: sliding window + summary + vector retrieval + structured memory를 섞고, 이를 조정하는 memory manager가 필요합니다. ([blogs.oracle.com](https://blogs.oracle.com/developers/which-agent-memory-approach-is-best-for-long-conversations?utm_source=openai))  
핵심은 “장단기”가 아니라 **역할(role)** 분리입니다.

- **Working/Short-term (STM)**: 지금 턴의 계획/최근 tool 결과/현재 subgoal
- **Episodic LTM**: “언제/어떤 맥락에서 무슨 일이 있었나” (시간축이 중요)
- **Semantic/Structured LTM**: 변하지 않는 사실(정책, 사용자 선호, 엔티티, 결정사항)
- (옵션) **Procedural memory**: 반복되는 운영 절차/플레이북(코드/워크플로)

Oracle 쪽 글이 특히 명확하게 “Similarity ≠ Relevance”를 강조합니다. 즉, 벡터 유사도가 높다고 현재 상태에 필요한 정보라는 보장은 없고, 그래서 structured memory가 필요합니다. ([blogs.oracle.com](https://blogs.oracle.com/developers/which-agent-memory-approach-is-best-for-long-conversations?utm_source=openai))

### 2) RAG-only가 실패하는 이유: 실행 상태 의존성(trajectory)을 끊어먹는다
일반적인 “대화 로그 → 임베딩 → top-k 검색”은 long-horizon에서 다음 문제가 큽니다.

- **올바른 분기와 잘못된 분기의 조각이 섞여** 현재 상태 재구성이 깨짐
- “이 결정은 A를 전제로 한다” 같은 **의존성**이 semantic chunking에서 유실
- 요약/압축이 누적되면 drift가 생겨, “그럴듯한데 틀린 상태”가 됨

이를 정면으로 다룬 연구가 “메모리는 semantic organization이 아니라 execution state”라는 주장이고, 상태 트리에서 **현재 활성 경로(root→current)**를 기반으로 상태를 구성하는 디자인을 제안합니다. ([arxiv.org](https://arxiv.org/abs/2606.06090?utm_source=openai))

### 3) 상태 관리의 기본기: Checkpointing은 ‘복구’이고 LTM은 ‘학습/회상’이다
LangGraph 쪽 지식베이스가 정확히 짚는 부분이 있습니다:

- checkpoint는 **그래프 실행 상태 전체를 저장**하며, resume을 위한 “단기 복구 메커니즘”에 가깝다
- 큰 payload를 state에 넣지 말고, state에는 reference만 두고 외부 스토리지(S3 등)에 둬야 한다
- subgraph마다 checkpointer를 두면 namespace가 갈라지고 문서가 비대해져 resume 문제가 생긴다 ([kb.langchain.com](https://kb.langchain.com/articles/1242226068-how-do-i-configure-checkpointing-in-langgraph))

즉, **checkpoint = 장애/중단 대비**, **LTM = cross-session 기억**입니다. 같은 DB에 넣어도 모델링/TTL/조회 패턴이 다릅니다.

### 4) “Revision/Forget”이 없는 메모리는 결국 부정확해진다
최근 DB 관점 연구는 장기 메모리를 단순 저장이 아니라, ingestion/revision/forgetting/retrieval 같은 **state-level 연산**이 필요한 workload로 봅니다. ([arxiv.org](https://arxiv.org/abs/2605.26252?utm_source=openai))  
또, Anthropic의 Managed Agents memory는 변경 시 **immutable version(감사/point-in-time 복구)** 같은 운영 기능을 강조합니다. ([platform.claude.com](https://platform.claude.com/docs/en/managed-agents/memory?35444d06_page=2&50c59e3f_page=2))  
이 두 흐름이 합쳐지면 실무 결론은: “저장”보다 **정정(revision)과 추적(audit)**이 더 중요해집니다.

---

## 💻 실전 코드

현실적인 시나리오: **B2B 운영 에이전트**(티켓/장애 대응 보조)가 “스레드가 며칠씩 이어지고”, 중간에 서버가 재시작되며, 다음을 지켜야 한다고 합시다.

- 최근 대화/툴 결과는 STM으로 즉시 반영
- 결정/승인은 structured state로 확정 저장(소스 오브 트루스)
- 긴 로그는 episodic로 축적(감사 + 회고)
- semantic recall은 vector search로 보조하되, “현재 활성 상태”를 우선

아래 예시는 **FastAPI + Postgres** 기반으로:
- `agent_state`(structured) + `event_log`(episodic) + `vector_memory`(semantic) 3종을 분리하고
- “memory manager”가 요청 시 필요한 메모리만 조립해 프롬프트를 구성하는 형태입니다.
- 임베딩/LLM은 벤더 중립 인터페이스로 두고(실서비스에선 OpenAI/Claude/Azure 등 교체 가능), 코드 구조에 집중합니다.

### 0) 의존성/실행

```bash
pip install fastapi uvicorn sqlalchemy psycopg[binary] pydantic
# (옵션) 임베딩/벡터 검색은 실제로는 pgvector/외부 벡터DB를 쓰세요.
# 여기서는 구조를 보여주기 위해 "vector_memory"를 테이블로 단순화합니다.
```

### 1) 스키마(Structured / Episodic / Semantic)

```python
# app/db.py
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, DateTime, Text, Integer, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/agent"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class AgentState(Base):
    """
    Structured, source-of-truth state.
    - user/tenant scoped
    - approvals/decisions/preferences/entities 등 drift 나면 안 되는 것
    """
    __tablename__ = "agent_state"
    key = Column(String, primary_key=True)  # e.g., f"{tenant}:{user_id}"
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data = Column(JSON, nullable=False)     # canonical structured state

class EventLog(Base):
    """
    Episodic memory: append-only가 기본(감사/회고/디버깅).
    """
    __tablename__ = "event_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String, index=True, nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    type = Column(String, nullable=False)  # "user_msg" | "tool_call" | "decision" ...
    payload = Column(JSON, nullable=False)

class VectorMemory(Base):
    """
    Semantic memory: 실제로는 pgvector/HNSW/외부 벡터DB 권장.
    여기서는 검색/랭킹 부분을 대체할 placeholder.
    """
    __tablename__ = "vector_memory"
    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String, index=True, nullable=False)  # tenant/user/thread
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    text = Column(Text, nullable=False)
    meta = Column(JSON, nullable=False)  # {"kind":"summary","thread_id":...}

def init_db():
    Base.metadata.create_all(bind=engine)
```

### 2) Memory Manager: “상태 조립”을 한 곳에 모으기

```python
# app/memory_manager.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.db import AgentState, EventLog, VectorMemory

@dataclass
class MemoryBundle:
    structured_state: Dict[str, Any]
    recent_events: List[Dict[str, Any]]
    semantic_hits: List[Dict[str, Any]]

class MemoryManager:
    """
    핵심: LLM에 넣을 '컨텍스트'를 무작정 누적하지 말고,
    - Structured state(정답) 먼저
    - Recent episodic(working continuity) 다음
    - Semantic retrieval(보조) 마지막
    순서로 조립한다.
    """
    def __init__(self, db: Session):
        self.db = db

    def load_structured_state(self, state_key: str) -> Dict[str, Any]:
        row = self.db.get(AgentState, state_key)
        if not row:
            row = AgentState(key=state_key, data={
                "preferences": {},
                "open_incidents": [],
                "approvals": {},
                "facts": {}
            })
            self.db.add(row)
            self.db.commit()
        return row.data

    def append_event(self, thread_id: str, type_: str, payload: Dict[str, Any]) -> None:
        self.db.add(EventLog(thread_id=thread_id, type=type_, payload=payload))
        self.db.commit()

    def get_recent_events(self, thread_id: str, limit: int = 25) -> List[Dict[str, Any]]:
        rows = (self.db.query(EventLog)
                .filter(EventLog.thread_id == thread_id)
                .order_by(EventLog.id.desc())
                .limit(limit)
                .all())
        # 최근 -> 과거 순서를 뒤집어 대화 흐름 유지
        return [{"ts": r.ts.isoformat(), "type": r.type, "payload": r.payload} for r in reversed(rows)]

    def semantic_search(self, scope: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        실제 구현:
        - 임베딩 생성
        - vector index top-k
        - (가능하면) keyword + embedding hybrid
        OpenAI의 file_search도 hybrid ranker를 언급합니다. ([github.com](https://github.com/openai/openai-node/blob/main/src/resources/responses/responses.ts?utm_source=openai))
        """
        # placeholder: 최신 k개를 'hit'로 간주
        rows = (self.db.query(VectorMemory)
                .filter(VectorMemory.scope == scope)
                .order_by(VectorMemory.id.desc())
                .limit(k)
                .all())
        return [{"text": r.text, "meta": r.meta, "ts": r.ts.isoformat()} for r in rows]

    def build_bundle(self, state_key: str, thread_id: str, scope: str, query: str) -> MemoryBundle:
        structured = self.load_structured_state(state_key)
        recent = self.get_recent_events(thread_id, limit=30)
        semantic = self.semantic_search(scope, query=query, k=5)
        return MemoryBundle(structured_state=structured, recent_events=recent, semantic_hits=semantic)
```

### 3) API: 이벤트 기록 + 상태 업데이트(“결정”만 structured로 승격)

```python
# app/main.py
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import SessionLocal, init_db, AgentState
from app.memory_manager import MemoryManager

app = FastAPI()
init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ChatIn(BaseModel):
    tenant: str
    user_id: str
    thread_id: str
    message: str

@app.post("/agent/chat")
def chat(inp: ChatIn, db: Session = Depends(get_db)):
    mm = MemoryManager(db)
    state_key = f"{inp.tenant}:{inp.user_id}"
    scope = state_key  # tenant/user 단위 semantic memory

    # 1) episodic에 유저 메시지 기록
    mm.append_event(inp.thread_id, "user_msg", {"text": inp.message})

    # 2) 필요한 메모리 번들 조립
    bundle = mm.build_bundle(state_key, inp.thread_id, scope, query=inp.message)

    # 3) (여기서 LLM 호출) - 예시는 "결정 승격" 흐름만 보여줌
    # 현실적으로는:
    # - structured_state를 시스템 프롬프트의 '정답 레이어'로 제공
    # - recent_events는 대화 연속성
    # - semantic_hits는 참고자료(신뢰도 낮음)로 라벨링
    #
    # 데모: 특정 키워드가 나오면 approval을 structured로 승격
    if "승인" in inp.message:
        st = mm.load_structured_state(state_key)
        st["approvals"]["last_approval"] = {"thread_id": inp.thread_id, "note": inp.message}
        row = db.get(AgentState, state_key)
        row.data = st
        db.commit()
        mm.append_event(inp.thread_id, "decision", {"kind": "approval", "text": inp.message})

    return {
        "structured_state": bundle.structured_state,
        "recent_events_count": len(bundle.recent_events),
        "semantic_hits_count": len(bundle.semantic_hits),
        "note": "LLM 호출은 생략. 프로덕션에선 bundle을 기반으로 prompt를 구성하세요."
    }
```

**예상 출력(개념)**  
- structured_state에는 approvals/preferences 같은 “정답”이 유지되고  
- recent_events는 최근 30개로 bounded  
- semantic_hits는 보조 레이어(검색 기반)로만 사용

이 구조가 중요한 이유는, long-term memory를 “그냥 과거 로그”로 취급하지 않고:
- **결정/승인/정책**은 structured state로 고정(요약 drift 방지)
- 대화 로그는 append-only로 남겨 감사 가능
- semantic recall은 “참고”로만 주입해 상태를 오염시키지 않게 합니다

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) “상태 승격(Promotion) 규칙”을 코드로 박아라
요약/벡터 검색에서 뽑힌 텍스트를 그대로 structured state에 쓰면 drift가 누적됩니다.  
권장: **(a) 후보 추출 → (b) 검증(출처/최신성/테넌트) → (c) 승격** 단계를 분리하세요. “revision/forgetting”이 필요하다는 최근 DB 관점도 결국 이 이야기입니다. ([arxiv.org](https://arxiv.org/abs/2605.26252?utm_source=openai))

### Best Practice 2) Checkpoint/State/LTM을 한 저장소에 우겨넣지 말고 “접근 패턴”으로 분리
LangGraph 체크포인트 문서 자체가 “complete graph state + metadata”라서 비대해지기 쉽고, 큰 payload를 state에 넣으면 관측/성능에도 영향이 납니다. ([kb.langchain.com](https://kb.langchain.com/articles/1242226068-how-do-i-configure-checkpointing-in-langgraph))  
- checkpoint: TTL 짧게, 복구용
- event log: append-only, 파티션/보관 정책
- structured state: 강한 일관성/업데이트 규칙
- semantic store: 재색인/압축/TTL 전략

### Best Practice 3) Audit(버전/불변성) 없이 “기억” 기능을 넣지 마라
Anthropic Managed Agents memory가 “변경 시 immutable version으로 감사/복구”를 강조하는 이유가 여기에 있습니다. ([platform.claude.com](https://platform.claude.com/docs/en/managed-agents/memory?35444d06_page=2&50c59e3f_page=2))  
실무에서는 “왜 그 결정을 했는지”가 나중에 더 중요해집니다.

---

### 흔한 함정/안티패턴

- **안티패턴: 벡터 top-k를 ‘정답’처럼 취급**  
  Similarity ≠ relevance. 특히 정책/승인/권한은 반드시 structured source-of-truth에서만 읽게 하세요. ([blogs.oracle.com](https://blogs.oracle.com/developers/which-agent-memory-approach-is-best-for-long-conversations?utm_source=openai))

- **안티패턴: 요약을 계속 덮어쓰는 단일 summary 문서**  
  drift + 정보 손실이 누적됩니다. 요약은 “압축본”이지 원본이 아닙니다. event log는 남기고, 요약은 버전/스냅샷으로 관리하세요.

- **안티패턴: 테넌트 경계 없는 shared memory**  
  memory는 곧 데이터입니다. scope(tenant/user/thread)를 키 설계의 1순위로 두세요. Azure Cosmos DB 가이드도 파티션 키/인덱스/모델링을 먼저 다룹니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/cosmos-db/gen-ai/agentic-memories))

---

### 비용/성능/안정성 트레이드오프

- **저장량 vs 품질**: 다 저장하면 retrieval 노이즈가 늘고, 안 저장하면 개인화/연속성이 깨짐  
- **요약 비용 vs 재생성 비용**: 배치 요약은 비용 예측이 쉽지만 최신성이 떨어질 수 있음. 반대로 on-demand 요약은 latency가 튈 수 있음
- **구조화 비용 vs 안정성**: structured state를 유지하려면 스키마/승격 규칙/검증이 필요하지만, 그게 결국 운영 안정성을 만듭니다
- **semantic 검색 품질 vs 운영 복잡도**: hybrid search(embedding+keyword)나 ranker 옵션을 쓰면 품질이 오르지만(도구들도 hybrid를 강조하는 추세) 설정/관측 포인트가 늘어납니다. ([github.com](https://github.com/openai/openai-node/blob/main/src/resources/responses/responses.ts?utm_source=openai))

---

## 🚀 마무리

2026년의 결론은 간단합니다.

1) long-term memory는 “기억 저장”이 아니라 **상태(state) 관리** 문제다. ([arxiv.org](https://arxiv.org/abs/2606.06090?utm_source=openai))  
2) RAG-only로는 long-horizon에서 **의존성과 분기(trajectory)**를 복원하기 어렵다.  
3) 프로덕션에서는 **Structured state(정답) / Episodic log(감사) / Semantic recall(참고)** 를 분리하고, 승격/정정/망각을 운영 규칙으로 둬야 한다. ([blogs.oracle.com](https://blogs.oracle.com/developers/which-agent-memory-approach-is-best-for-long-conversations?utm_source=openai))  
4) 버전/Audit이 없는 메모리는 나중에 반드시 부채가 된다. ([platform.claude.com](https://platform.claude.com/docs/en/managed-agents/memory?35444d06_page=2&50c59e3f_page=2))

### 도입 판단 기준(내 프로젝트에 적용할지)
- “사용자/업무가 며칠에 걸쳐 이어지나?” → Yes면 structured+episodic 분리부터
- “승인/권한/정책이 중요한가?” → Yes면 semantic memory는 참고 레이어로 격리
- “재시작/분산 실행/중단-재개가 있나?” → Yes면 checkpoint(복구)와 LTM(학습)을 분리 설계

### 다음 학습 추천
- 실행 상태 관점의 메모리 설계: MAGE(상태 트리) 아이디어 ([arxiv.org](https://arxiv.org/abs/2606.06090?utm_source=openai))  
- 장기 메모리의 데이터 관리 관점(GEM, revision/forgetting) ([arxiv.org](https://arxiv.org/abs/2605.26252?utm_source=openai))  
- 체크포인트/상태 비대화 운영 이슈: LangGraph checkpointing 가이드 ([kb.langchain.com](https://kb.langchain.com/articles/1242226068-how-do-i-configure-checkpointing-in-langgraph))  

원하면, 위 예제를 **pgvector 기반 진짜 semantic search(하이브리드 랭킹 포함)**로 확장하고, “승격 규칙(validator + audit versioning)”까지 포함한 프로덕션 템플릿으로 다듬어드릴 수 있습니다.