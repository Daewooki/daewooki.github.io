---
title: "2026년 6월 기준: LangGraph·AutoGen·CrewAI로 “멀티 에이전트”를 프로덕션에 올리는 법 (비교 + 구현 패턴)"
date: 2026-06-26 04:19:39 +0900
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
2026년의 AI Agent 개발에서 진짜 문제는 “LLM 호출을 잘 묶는 것”이 아니라, **(1) 멀티 에이전트의 제어 흐름(control flow)을 어떻게 명시적으로 관리할지**, **(2) 상태(state)·메모리(memory)·툴(tool) 사용을 어떻게 재현 가능하게 만들지**, **(3) 보안 경계(특히 localhost/툴 실행)와 관측성(observability)을 어떻게 확보할지**입니다. 최근 Microsoft는 브라우징 에이전트가 로컬 제어면(local control plane)을 건드리며 RCE로 이어질 수 있는 “AutoJack”류 위험을 공개적으로 경고했죠. ([microsoft.com](https://www.microsoft.com/en-us/security/blog/2026/06/18/autojack-single-page-rce-host-running-ai-agent/?utm_source=openai))

이 글은 LangGraph / AutoGen / CrewAI를 “소개”하지 않습니다. 대신 아래 질문에 답합니다.

- **언제 LangGraph가 맞나?**: 분기/재시도/중단-재개, 장기 실행, human-in-the-loop, 감사/재현성(규제 산업 포함)까지 **워크플로우를 코드로 ‘구조화’**해야 할 때. LangGraph는 그래프 + 체크포인터 기반으로 이 문제를 정면으로 다룹니다. ([reference.langchain.com](https://reference.langchain.com/python/langgraph/overview?utm_source=openai))  
- **언제 AutoGen이 맞나?**: 에이전트 간 대화/협상/역할 분담을 **대화 중심으로 빠르게 실험**하고, “누가 다음 발화자(speaker)인가” 같은 동적 라우팅을 자연스럽게 다루고 싶을 때(예: SelectorGroupChat). ([microsoft.github.io](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/selector-group-chat.html?utm_source=openai))  
- **언제 CrewAI가 맞나?**: 팀/역할/업무(Task) 단위로 **업무 위임과 운영 모델(Manager-Worker)을 빠르게 제품화**하고 싶을 때. 순차/계층형 프로세스가 명확합니다. ([docs.crewai.com](https://docs.crewai.com/?utm_source=openai))  

반대로,
- **쓰면 안 되는 경우**: “정확히 어떤 단계가 실행돼야 하는지”가 명확한 단순 배치 작업(에이전트 필요 없음), 보안 격리가 안 된 환경에서 브라우징+로컬툴을 섞는 설계(취약), 실패 비용이 큰데 테스트/재현 전략이 없는 경우입니다. 특히 localhost 제어면을 두고 브라우저/에이전트를 신뢰하면 위험해집니다. ([microsoft.com](https://www.microsoft.com/en-us/security/blog/2026/06/18/autojack-single-page-rce-host-running-ai-agent/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) 세 프레임워크의 “정신모델” 차이
- **LangGraph = Graph(노드/엣지) + State + Checkpointer**
  - 핵심은 “에이전트 앱도 결국 **상태 기계(state machine)**”라는 관점입니다.
  - 각 노드는 (a) LLM 호출, (b) tool node, (c) 라우터, (d) 검증/가드레일 등으로 구성되고, 엣지가 다음 실행 경로를 결정합니다.
  - 실행은 super-step(한 번의 노드 실행/전이) 단위로 진행되고, **체크포인트가 매 step마다 상태를 저장**해 중단/재개·time travel 디버깅이 가능합니다. (TS 가이드에서 Memory/SQLite/Postgres/Redis/Mongo 등 백엔드 언급) ([langgraphjs.guide](https://langgraphjs.guide/persistence/?utm_source=openai))  

- **AutoGen = Conversation Runtime + GroupChat(발화자 선택) + Termination**
  - 멀티 에이전트를 “대화 프로토콜”로 봅니다.
  - `SelectorGroupChat`는 에이전트 설명과 컨텍스트를 바탕으로 **다음 화자(=다음 실행 에이전트)를 동적으로 선택**합니다. 무한 루프 방지를 위해 `MaxMessageTermination` 같은 종료 조건을 함께 둡니다. ([microsoft.github.io](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/selector-group-chat.html?utm_source=openai))  
  - 장점: 동적 협업/협상/상호 검증에 강함. 단점: 워크플로우를 “형식적으로” 재현/감사하기엔 추가 설계가 필요합니다(로그/스냅샷/상태 관리가 코드 바깥으로 새기 쉬움).

- **CrewAI = Crew(팀) + Task(업무) + Process(순차/계층)**
  - 멀티 에이전트를 “조직 구조”로 봅니다.
  - sequential은 파이프라인형, hierarchical은 manager가 계획/위임/검수/재할당을 수행합니다(문서/커뮤니티에서도 이 구분을 반복 강조). ([learn.engineering.vips.edu](https://learn.engineering.vips.edu/agent-protocols/crewai-hierarchical-process?utm_source=openai))  
  - 장점: “프로덕트 관점”에서 역할/책임이 읽히고 운영이 쉬움. 단점: 복잡한 분기/재시도/부분 재개 같은 제어흐름은 설계에 따라 LangGraph만큼 투명하지 않을 수 있습니다(그래서 Flows를 함께 보게 됨). ([docs.crewai.com](https://docs.crewai.com/core-concepts/Agents?utm_source=openai))  

### 2) 멀티 에이전트 구현에서 진짜 중요한 3가지 흐름
1. **Routing(다음 단계/다음 에이전트 선택)**  
   - LangGraph: 라우터 노드(조건 분기)로 명시
   - AutoGen: speaker selection(SelectorGroupChat)로 암묵적/동적
   - CrewAI: process(순차/계층)로 큰 틀을 고정하고 manager가 미세 조정

2. **State & Persistence(중단/재개, 재현성)**  
   - LangGraph: checkpointer가 설계의 중심(메모리/DB 저장) ([reference.langchain.com](https://reference.langchain.com/python/langgraph/overview?utm_source=openai))  
   - AutoGen/CrewAI: 기본 제공만으로는 “스텝 단위 재개”를 시스템적으로 강제하기 어렵고, 외부 저장/이벤트 로그/작업 큐 설계가 더 중요해집니다.

3. **Security Boundary(브라우징·툴·로컬 제어면)**  
   - “브라우저로 외부 컨텐츠를 읽는 에이전트”와 “로컬에서 코드를 실행/제어하는 서비스”를 같은 trust zone에 두면 사고가 납니다. AutoJack 케이스는 loopback(localhost)을 신뢰 경계로 착각했을 때 어떤 일이 생기는지 보여줍니다. ([microsoft.com](https://www.microsoft.com/en-us/security/blog/2026/06/18/autojack-single-page-rce-host-running-ai-agent/?utm_source=openai))  

---

## 💻 실전 코드
현실적인 시나리오: **“보안 패치 리서치 → 영향 분석 → PR 초안 생성”**을 멀티 에이전트로 돌립니다.  
요구사항은 다음과 같습니다.

- 리서치 결과가 불완전하면 **재시도**
- 분석 단계에서 “영향 없음”이면 **조기 종료**
- 실패해도 **중단 지점부터 재개**
- 실행 기록이 남아야 함(디버깅/감사)

여기서는 이 요구사항에 가장 직결되는 **LangGraph + Checkpointer**로 구현하고, 마지막에 AutoGen/CrewAI로 같은 문제를 풀 때의 구조 차이를 정리합니다.

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install -U langgraph langchain-core langgraph-checkpoint-sqlite openai
export OPENAI_API_KEY="..."
```

### 1) LangGraph: 상태/분기/재개 가능한 멀티 에이전트 그래프
- Agent를 “여러 개” 만들되, 핵심은 **State에 누적**하고 **노드 간 계약(입출력)을 고정**하는 것입니다.
- 체크포인터(SQLite)로 thread 단위 재개를 켭니다. (공식 문서에서 SQLite/Postgres 체크포인터가 언급됩니다.) ([reference.langchain.com](https://reference.langchain.com/python/langgraph/overview?utm_source=openai))  

```python
from __future__ import annotations

from typing import TypedDict, Literal, Optional, List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from openai import OpenAI

client = OpenAI()

# --- 1) Graph State: "재개 가능한 계약" ---
class PatchState(TypedDict, total=False):
    issue_id: str
    target_repo: str

    # 누적 산출물
    sources: List[Dict[str, str]]          # [{"title":..., "url":..., "notes":...}]
    research_summary: str
    impact_assessment: str
    pr_plan: str
    pr_diff: str

    # 제어용 상태
    attempts: int
    decision: Literal["need_more_research", "no_impact", "create_pr"]

def llm_json(system: str, user: str) -> Dict[str, Any]:
    # 운영에서는 response_format(JSON schema) / tool calling으로 강제하는 편이 안전
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    # 간단화를 위해 텍스트를 JSON으로 "가정"하지 말고, 실제론 tool calling을 쓰세요.
    # 여기서는 데모로만 문자열 반환.
    return {"text": resp.output_text}

# --- 2) Nodes (멀티 에이전트 역할을 노드로 분리) ---
def researcher(state: PatchState) -> PatchState:
    issue = state["issue_id"]
    attempts = state.get("attempts", 0) + 1

    # 현실: 여기서 GitHub Advisory/NVD/벤더 릴리즈노트/커밋 등을 수집
    # 데모: LLM에게 "필요한 소스 목록/요약"을 생성하게 하되,
    # 실제 구현에선 search tool + fetch + parser가 들어가야 합니다.
    out = llm_json(
        system="You are a security patch researcher. Produce a concise research summary and 3-5 sources.",
        user=f"Research issue {issue}. Include affected components, versions, and mitigation hints."
    )["text"]

    sources = state.get("sources", [])
    sources.append({"title": f"Research attempt {attempts}", "url": "about:blank", "notes": out})

    return {
        **state,
        "attempts": attempts,
        "sources": sources,
        "research_summary": out,
    }

def assessor(state: PatchState) -> PatchState:
    repo = state["target_repo"]
    summary = state.get("research_summary", "")

    out = llm_json(
        system=(
            "You are a senior engineer doing impact assessment. "
            "Decide if the target repo is likely impacted. "
            "Return one of: no_impact, need_more_research, create_pr and an explanation."
        ),
        user=f"Target repo: {repo}\nResearch summary:\n{summary}\n"
    )["text"]

    # 운영에서는 LLM output을 파싱/검증해서 decision을 강제해야 합니다.
    # 여기선 단순 휴리스틱(설명 텍스트에 키워드)로 분기.
    t = out.lower()
    if "need_more_research" in t:
        decision = "need_more_research"
    elif "no_impact" in t:
        decision = "no_impact"
    else:
        decision = "create_pr"

    return {**state, "impact_assessment": out, "decision": decision}

def planner(state: PatchState) -> PatchState:
    out = llm_json(
        system="You are a tech lead. Write a PR plan with steps, files to touch, and rollback strategy.",
        user=f"Repo: {state['target_repo']}\nAssessment:\n{state.get('impact_assessment','')}\n"
    )["text"]
    return {**state, "pr_plan": out}

def patch_writer(state: PatchState) -> PatchState:
    # 현실: repo checkout + dependency bump + tests + formatter + git diff 생성
    # 여기선 PR diff 초안을 텍스트로 생성(실제로는 위험; 반드시 sandbox에서 생성/검증)
    out = llm_json(
        system="Generate a minimal unified diff patch proposal. Keep it small and safe.",
        user=f"Repo: {state['target_repo']}\nPlan:\n{state.get('pr_plan','')}\n"
    )["text"]
    return {**state, "pr_diff": out}

# --- 3) Routing: 분기 로직을 코드로 고정 ---
def route_after_assess(state: PatchState) -> str:
    if state["decision"] == "need_more_research":
        # 2회까지만 재시도 후 강제 종료(운영에서는 human-in-the-loop로 넘기는 게 낫습니다)
        if state.get("attempts", 0) >= 2:
            return END
        return "researcher"
    if state["decision"] == "no_impact":
        return END
    return "planner"

# --- 4) Build Graph + Checkpointer (중단/재개 핵심) ---
builder = StateGraph(PatchState)
builder.add_node("researcher", researcher)
builder.add_node("assessor", assessor)
builder.add_node("planner", planner)
builder.add_node("patch_writer", patch_writer)

builder.set_entry_point("researcher")
builder.add_edge("researcher", "assessor")
builder.add_conditional_edges("assessor", route_after_assess, {
    "researcher": "researcher",
    "planner": "planner",
    END: END,
})
builder.add_edge("planner", "patch_writer")
builder.add_edge("patch_writer", END)

checkpointer = SqliteSaver.from_conn_string("checkpoints.sqlite")
graph = builder.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    # thread_id가 "실행 단위". 장애나 재시작 후에도 이어가기 가능.
    config = {"configurable": {"thread_id": "secfix-2026-06-issue-123"}}

    initial: PatchState = {
        "issue_id": "CVE-2026-XXXX (example)",
        "target_repo": "github.com/acme/payments-service",
        "attempts": 0,
        "sources": [],
    }

    final = graph.invoke(initial, config=config)
    print("=== decision:", final.get("decision"))
    print("=== attempts:", final.get("attempts"))
    print("=== pr_diff (preview):\n", (final.get("pr_diff") or "")[:800])
```

#### 예상 출력(형태)
- `decision: create_pr` 또는 `no_impact`
- `attempts: 1~2`
- `pr_diff` 초안 일부 출력

### 2) 같은 요구사항을 AutoGen/CrewAI로 풀면 “어디가 달라지나”
- **AutoGen**: `SelectorGroupChat`로 “다음 담당 에이전트”를 대화 기반으로 선택하는 건 편합니다. 대신 위 코드에서 checkpointer가 책임졌던 **스텝 단위 재개/감사**는 별도 저장소(이벤트 로그, DB, queue)로 직접 설계해야 운영이 편해집니다. ([microsoft.github.io](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/selector-group-chat.html?utm_source=openai))  
- **CrewAI**: sequential/hierarchical 프로세스로 “일의 흐름”은 빠르게 잡히고, manager 패턴이 조직적으로 읽힙니다. 다만 “부분 실패 후 정확히 어디부터 재개할지”를 일관되게 만들려면 Task 결과 저장, idempotency, 외부 상태 저장 규약을 강하게 둬야 합니다. ([docs.crewai.com](https://docs.crewai.com/?utm_source=openai))  

---

## ⚡ 실전 팁 & 함정
### Best Practice (제가 2026년에 프로덕션에서 반드시 넣는 것들)
1) **State를 ‘로그 겸 계약’으로 설계하라**  
   - 멀티 에이전트가 커질수록 “메시지 히스토리”가 아니라 **명시적 State**가 디버깅 단위가 됩니다. LangGraph의 checkpointer/time travel이 강력한 이유가 여기 있습니다. ([langgraphjs.guide](https://langgraphjs.guide/persistence/?utm_source=openai))  

2) **Termination / Loop budget을 코드로 강제하라**  
   - AutoGen은 종료 조건을 함께 두는 예시가 문서에 나옵니다(무한 루프 방지). LangGraph도 라우팅에서 retry budget을 강제하세요. ([microsoft.github.io](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/selector-group-chat.html?utm_source=openai))  

3) **브라우징 에이전트와 로컬 제어면/툴 실행을 분리하라(필수)**  
   - AutoJack 이슈는 “localhost면 안전”이라는 가정이 깨졌을 때의 전형적인 사고 경로를 보여줍니다.  
   - 실무 체크리스트: (a) MCP/제어 API 인증/인가, (b) loopback도 untrusted로 취급, (c) 브라우저/에이전트 샌드박스(컨테이너) 분리, (d) 툴 allowlist + parameter validation. ([microsoft.com](https://www.microsoft.com/en-us/security/blog/2026/06/18/autojack-single-page-rce-host-running-ai-agent/?utm_source=openai))  

### 흔한 함정/안티패턴
- **“메모리 = 만능” 착각**: 장기 메모리는 편하지만, 잘못 주입된 정보가 다음 실행의 제어 흐름을 오염시키는 문제가 꾸준히 연구됩니다(메모리 기반 공격/오염 이슈가 논의됨). 따라서 중요한 분기 조건은 메모리에서 읽지 말고 **검증 가능한 구조화 데이터**로 두세요. ([arxiv.org](https://arxiv.org/abs/2603.15125?utm_source=openai))  
- **Diff/코드 생성 결과를 곧바로 실행**: patch_writer 같은 노드는 반드시 sandbox + 테스트 + 정책 검증을 붙여야 합니다. “에이전트가 만든 코드”는 실행 가능한 공격 페이로드가 될 수 있습니다(위 보안 이슈와 결이 같습니다). ([microsoft.com](https://www.microsoft.com/en-us/security/blog/2026/06/18/autojack-single-page-rce-host-running-ai-agent/?utm_source=openai))  

### 비용/성능/안정성 트레이드오프
- **LangGraph**: 체크포인트/저장소 round-trip이 step마다 붙습니다. 대신 재시도/재개/감사 비용을 크게 줄입니다(장기 운영일수록 이득). ([docs.persql.com](https://docs.persql.com/recipes/langgraph-checkpointer/?utm_source=openai))  
- **AutoGen/CrewAI**: 초기 구현은 빠르지만, 운영 단계에서 “관측성/재현성/재개”를 외부로 설계하다가 총비용이 커질 수 있습니다.

---

## 🚀 마무리
정리하면, 2026년 6월 기준 멀티 에이전트 프레임워크 선택은 “기능표”가 아니라 **내 시스템의 실패 형태**로 결정하는 게 맞습니다.

- **LangGraph를 선택할 기준**: 분기·재시도·중단/재개·감사 로그가 핵심인 워크플로우(보안 패치, 고객 티켓 자동화, 장기 리서치, 승인 플로우). checkpointer 기반 persistence가 강력한 근거입니다. ([reference.langchain.com](https://reference.langchain.com/python/langgraph/overview?utm_source=openai))  
- **AutoGen을 선택할 기준**: 에이전트 협업이 “대화” 그 자체이고, 동적 speaker selection/협상/자기검증 패턴을 빠르게 실험하고 싶을 때. ([microsoft.github.io](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/selector-group-chat.html?utm_source=openai))  
- **CrewAI를 선택할 기준**: 역할 기반의 팀 운영, manager-worker 위임, task 중심 파이프라인을 빠르게 제품화할 때. ([docs.crewai.com](https://docs.crewai.com/?utm_source=openai))  

다음 학습 추천(순서):
1) LangGraph의 persistence/time travel을 실제 DB(Postgres/Redis)로 붙여 “재개 가능한 운영”을 경험해보기 ([langgraphjs.guide](https://langgraphjs.guide/persistence/?utm_source=openai))  
2) AutoGen의 SelectorGroupChat + Termination 패턴을 그대로 가져와, LangGraph 라우터로 “대화 기반 라우팅을 그래프에 고정”해보기 ([microsoft.github.io](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/selector-group-chat.html?utm_source=openai))  
3) 마지막으로, 브라우징/로컬툴/제어면을 분리한 보안 아키텍처를 기본값으로 두기(AutoJack류를 설계에서 차단) ([microsoft.com](https://www.microsoft.com/en-us/security/blog/2026/06/18/autojack-single-page-rce-host-running-ai-agent/?utm_source=openai))