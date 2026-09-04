---
title: "긴 컨텍스트(200k~1M+)가 ‘쓸 수 있게’ 되는 법: 2026년식 LLM compaction/summary 설계와 lost-in-the-middle 대응"
description: "LLM의 context window가 200k~1M 토큰까지 커졌는데도, “그 안에 넣기만 하면 알아서 잘 쓰겠지”는 여전히 잘 안 됩니다. 실제 현업에서 터지는 문제는 보통 3가지로 요약됩니다."
date: 2026-08-22 01:39:35 +0900
categories: [AI, LLM]
tags: [ai, llm]
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
LLM의 context window가 200k~1M 토큰까지 커졌는데도, **“그 안에 넣기만 하면 알아서 잘 쓰겠지”**는 여전히 잘 안 됩니다. 실제 현업에서 터지는 문제는 보통 3가지로 요약됩니다.

1) **비용/지연**: 긴 컨텍스트는 입력 토큰 비용과 latency를 선형(혹은 시스템적으로 더)로 밀어 올립니다.  
2) **성능 저하(특히 중간)**: 문서/대화가 길어질수록, 중요한 정보가 **중간에 묻히면** 정확도가 떨어지는 *lost in the middle*이 반복 관측됩니다. Google의 *Found in the middle*은 이를 **U-shaped attention bias(앞/뒤 과대, 중간 과소)**로 설명합니다.[^1]  
3) **장기 세션의 ‘기억 부패’**: agent가 수백 step을 돌면, compaction(요약/압축)이 요약을 다시 요약하면서 중요한 사실을 잃거나(irreversible loss), 잘못된 사실이 요약에 들어가 “독”처럼 남습니다.[^2]

**언제 쓰면 좋나**
- 장기 대화/agent(코딩 에이전트, 운영 자동화, 리서치 에이전트)
- RAG에서 검색 결과/툴 출력이 길고 반복 참조되는 경우(티켓/런북/로그/PR diff)
- “문서 전체를 한 번에”가 아니라, **반복적으로 일부만 참조**하면서 작업이 진행되는 워크플로우

**언제 쓰면 안 되나**
- 단발성 Q&A(입력 짧음): compaction 호출 자체가 “Summary tax(요약 비용)”만 추가할 수 있음[^2]  
- 정확히 보존해야 할 원문(법무/규정/정산 등)을 요약에만 의존: 요약은 항상 손실 가능  
- 디버깅이 안 된 상태로 “자동 compaction”만 켜기: 무엇이 언제 사라지는지 관측 불가

---

## 🔧 핵심 개념
### 1) “long context 활용”의 적: position bias + middle loss
*Lost-in-the-middle*은 단순히 “컨텍스트가 길어서”가 아니라, 모델 내부적으로 **앞/뒤 토큰에 더 주의를 주는 편향**과 연결됩니다. *Found in the middle*은 이 편향을 보정해 긴 컨텍스트에서 관련 정보를 찾는 성능을 올리는 접근을 제안합니다.[^1]  
즉, **길이를 늘리는 것(LongRoPE 같은 확장)**만으로는 해결이 안 되고, *배치(placement)*, *압축(compaction)*, *검색(RAG)*, *평가*가 같이 가야 합니다. (LongRoPE류는 “더 많이 넣을 수 있음”의 영역)[^3]

### 2) compaction의 본질: “요약”이 아니라 “상태(state) 재인코딩”
실무 compaction은 보통 다음 중 하나(또는 혼합)입니다.

- **Hard compression(텍스트 요약/프루닝)**: 오래된 대화를 요약문으로 치환, 중요하지 않은 메시지는 drop  
- **Query-aware compression(RAG 압축)**: 질문/의도(Q)에 따라 문서에서 쓸 부분만 남김(문서 재정렬/랭킹 포함). 잃기 쉬운 중간 정보를 “앞쪽으로 끌어올리는” 효과도 있음.[^4]  
- **Soft compression(잠재 표현/KV cache 압축)**: 텍스트 자체가 아니라 latent/KV에 정보를 넣어 효율적으로 유지(연구가 활발, 배포 난이도 높음).[^5]  

2026년 현업 관점에서 당장 쓸 수 있는 건 대개 **Hard + Query-aware 혼합**이고, 여기에 “middle loss를 줄이기 위한 배치 규칙”이 핵심입니다.

### 3) 자동 compaction(플랫폼 기능) vs 앱 레벨 compaction
예를 들어 AWS Bedrock의 Claude Messages는 **server-side compaction**을 제공하며, 특정 beta header로 활성화하고 “compaction block” 이전 메시지를 자동으로 요약/드롭해 이어갑니다.[^6]  
이 방식은 통합은 쉽지만, 실무에선 아래가 중요합니다.

- 요약 포맷을 **내가 통제**할 수 있는가?
- 무엇을 **절대 보존(pinned state)**할지 정의할 수 있는가?
- compaction 시점/빈도/토큰 예산을 관측하고 튜닝할 수 있는가?

(플랫폼 compaction을 쓰더라도, 앱 레벨에서 “핀/체크포인트/검증”을 얹는 게 안전합니다.)

---

## 💻 실전 코드
아래는 “장기 세션 agent”에서 **lost-in-the-middle + 요약 드리프트**를 동시에 잡는 패턴입니다.

- 핵심 아이디어: 컨텍스트를
  1) **PINNED(절대 상태)**: 프로젝트/환경/식별자/규칙  
  2) **COMPACTED MEMORY(요약 상태)**: 결정/진행/시도/결과/오픈이슈  
  3) **RECENT WINDOW(최근 N step)**: 최신 대화 원문  
  4) **EPISODIC BLOBS(큰 툴 출력)**: 원문은 외부 저장 + 필요 시 query-aware로 얇게 가져오기  
  로 분리하고, 매 turn마다 “중요 상태”는 **앞/뒤에 배치**합니다(중간에 묻히지 않게).

### 0) 의존성/실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install pydantic rich
python agent_compaction_demo.py
```

### 1) 코드 (실전 스켈레톤)
```python
# agent_compaction_demo.py
from __future__ import annotations

import json
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from rich import print

# --- 1) 데이터 모델: "요약"이 아니라 "상태"로 보관 ---
class PinnedState(BaseModel):
    # 절대 잃으면 안 되는 값들(식별자/환경/목표/안전규칙/버전 등)
    project: str
    env: str
    customer_id: str
    repo: str
    hard_constraints: List[str]

class MemoryState(BaseModel):
    # 장기적으로 유지할 "결정/시도/결과" (요약의 핵심 단위)
    goal: str
    decisions: List[str] = Field(default_factory=list)
    attempts: List[str] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    last_updated_ts: float = Field(default_factory=lambda: time.time())

class Turn(BaseModel):
    role: str  # "user" | "assistant" | "tool"
    content: str
    ts: float = Field(default_factory=lambda: time.time())

# --- 2) LLM 호출은 실제 프로젝트의 SDK로 교체 ---
def call_llm(messages: List[Dict[str, str]]) -> str:
    """
    실제로는 OpenAI/Bedrock/Anthropic 등으로 교체.
    여기서는 '형태'만 보여주기 위해 더미 응답.
    """
    # 현실 코드에서는 messages를 그대로 API에 전달하고 텍스트를 반환
    return "DUMMY: (여기서 LLM이 답변/다음 행동을 생성한다고 가정)"

# --- 3) Compaction: "요약문"이 아니라 구조화된 MemoryState로 갱신 ---
def compact_memory(pinned: PinnedState, memory: MemoryState, old_turns: List[Turn]) -> MemoryState:
    """
    핵심: (a) 구조화 포맷, (b) 덮어쓰기/드리프트 방지, (c) 회복불가 손실 최소화.
    """
    # 실무에서는 이 프롬프트를 LLM에 보내 JSON으로 업데이트를 받는다.
    # 여기서는 old_turns에서 키워드 기반으로 "시도/결과"를 누적하는 예시.
    updated = memory.model_copy(deep=True)
    updated.last_updated_ts = time.time()

    for t in old_turns:
        c = t.content.lower()
        if "tried:" in c:
            updated.attempts.append(t.content.strip())
        if "decision:" in c:
            updated.decisions.append(t.content.strip())
        if "found:" in c or "result:" in c:
            updated.findings.append(t.content.strip())
        if "open:" in c or "todo:" in c:
            updated.open_questions.append(t.content.strip())

    # 드리프트 방지: constraints는 pinned로만 유지(요약이 수정하지 못하게 분리)
    return updated

# --- 4) Query-aware context compression (RAG/툴 출력 압축) 자리 ---
def compress_blob_for_query(blob_text: str, query: str, token_budget_chars: int = 1800) -> str:
    """
    실제로는 AttnComp/ACC-RAG 류처럼 '질문 적응형 압축'을 적용하거나[^7]
    LLM/규칙 기반으로 코드/JSON은 byte-preserving, 설명 텍스트만 축약하는 혼합 전략을 쓴다.
    """
    # 매우 단순한 placeholder: query 관련 줄만 우선 + 길이 제한
    lines = blob_text.splitlines()
    picked = [ln for ln in lines if any(k in ln.lower() for k in query.lower().split())]
    out = "\n".join(picked)[:token_budget_chars]
    return out if out.strip() else blob_text[:token_budget_chars]

# --- 5) 메시지 구성: lost-in-the-middle 대응(앞/뒤로 중요 상태 배치) ---
def build_messages(
    pinned: PinnedState,
    memory: MemoryState,
    recent: List[Turn],
    user_query: str,
    blob_snippets: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    blob_snippets = blob_snippets or []

    pinned_block = (
        "PINNED_STATE (do not modify):\n"
        + json.dumps(pinned.model_dump(), ensure_ascii=False, indent=2)
    )
    memory_block = (
        "COMPACTED_MEMORY (authoritative state):\n"
        + json.dumps(memory.model_dump(), ensure_ascii=False, indent=2)
    )

    # 중요 포인트:
    # 1) PINNED + MEMORY를 컨텍스트 "앞쪽"에 둔다
    # 2) user_query를 "뒤쪽"에도 한 번 더 둬서 end-bias를 활용한다(중요 질문이 중간에 묻히지 않게)
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": "You are a senior engineer agent. Prefer precise, verifiable steps."},
        {"role": "system", "content": pinned_block},
        {"role": "system", "content": memory_block},
    ]

    for snip in blob_snippets:
        messages.append({"role": "system", "content": f"COMPRESSED_BLOB:\n{snip}"})

    for t in recent:
        messages.append({"role": t.role, "content": t.content})

    messages.append({"role": "user", "content": user_query})
    messages.append({"role": "user", "content": f"(REPEAT_QUERY_FOR_END_BIAS) {user_query}"})
    return messages

def main():
    pinned = PinnedState(
        project="Payments Incident Agent",
        env="prod",
        customer_id="CUST-18421",
        repo="git@github.com:acme/payments.git",
        hard_constraints=[
            "Never rotate production keys without change ticket approval",
            "All changes must include rollback plan",
            "Do not expose PII in logs",
        ],
    )

    memory = MemoryState(goal="Reduce checkout latency regression introduced in v2.18.0")
    history: List[Turn] = []

    # 현실적인 장기 세션 흐름(툴 출력이 길다고 가정)
    history.append(Turn(role="user", content="최근 배포(v2.18.0) 이후 결제 latency가 2배 증가했어. 원인 분석해줘."))
    history.append(Turn(role="assistant", content="Decision: 먼저 p95 latency가 상승한 endpoint/region을 분리해서 본다."))
    history.append(Turn(role="tool", content="FOUND: ap-northeast-2 /checkout p95 900ms -> 1800ms (after v2.18.0)"))
    history.append(Turn(role="assistant", content="Tried: DB 커넥션 풀 설정 확인"))
    history.append(Turn(role="tool", content="RESULT: pool_max=20, wait 증가. 하지만 v2.18.0 변경점과 직접 연결은 약함."))
    history.append(Turn(role="assistant", content="Open: v2.18.0에서 추가된 fraud-check 호출이 병목인지 확인"))

    # ---- Compaction 트리거(예: turn 수/토큰 수 기반). 여기선 4개를 'old'로 간주 ----
    old_turns = history[:-2]
    recent = history[-2:]

    memory = compact_memory(pinned, memory, old_turns)

    # 큰 툴 출력(로그/트레이스)을 외부에 저장했다고 치고, query-aware로 얇게 가져오는 단계
    huge_trace = "\n".join([f"span={i} service=fraud_check dur_ms={5+i%20}" for i in range(5000)])
    query = "fraud_check dur_ms"
    blob = compress_blob_for_query(huge_trace, query=query, token_budget_chars=1200)

    messages = build_messages(
        pinned=pinned,
        memory=memory,
        recent=recent,
        user_query="fraud-check 호출이 latency 병목인지 확인하고, 롤백/완화 플랜을 제안해줘.",
        blob_snippets=[blob],
    )

    print("[bold]--- COMPOSED MESSAGES (truncated view) ---[/bold]")
    print(messages[1]["content"][:400] + "...\n")
    print(messages[2]["content"][:400] + "...\n")
    print("[bold]--- LLM OUTPUT ---[/bold]")
    out = call_llm(messages)
    print(out)

if __name__ == "__main__":
    main()
```

### 2) 예상 출력(요지)
- `PINNED_STATE` / `COMPACTED_MEMORY`가 상단에 있고  
- 큰 툴 출력은 `COMPRESSED_BLOB`로 예산 내 제공  
- 질문을 끝에 한 번 더 반복해 end-bias를 이용(중요 질의가 middle로 밀리지 않게)

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **“요약문” 대신 “상태 머신”으로 압축하라**  
   결정(Decisions), 시도(Attempts), 근거(Findings), 오픈이슈(Open questions)를 **구조화**하면 요약 드리프트가 줄고, 재사용/검증이 쉬워집니다. 장기 compaction의 실패 패턴(요약이 요약을 먹으며 의미가 흐려짐)은 반복적으로 지적됩니다.[^2]  

2) **middle loss는 ‘더 넣기’가 아니라 ‘배치/재배치’로 먼저 해결**  
   중요한 식별자/제약/현재 상태는 앞쪽(system/pinned)으로 고정하고, 현재 질문/목표는 뒤쪽에도 반복 배치해 position bias를 역이용하세요. (Found-in-the-middle이 말하는 attention bias 관점과도 정합적)[^1]  

3) **RAG는 “그대로 붙이기”보다 “질문 적응형 압축 + 재정렬”이 기본값**  
   EMNLP 2025의 AttnComp처럼 attention-guided로 컨텍스트를 압축/선별하는 흐름이 나오고, 2025년에도 Adaptive Context Compression류가 RAG 비용을 줄이면서 성능을 유지하려는 시도가 많습니다.[^7]  

### 흔한 함정/안티패턴
- **요약을 매번 덮어쓰기(Overwrite)만 하고 검증을 안 함**: 한 번 잃은 사실은 복구가 어렵고, 잘못된 사실이 요약에 남으면 계속 전파됩니다.[^2]  
- **툴 출력/검색 결과를 “원문 그대로” 대화에 넣고 계속 참조**: 같은 비용을 매 step 재지불 + middle loss 악화  
- **플랫폼 자동 compaction을 “만능”으로 취급**: 통제/관측/회귀테스트 없으면 디버깅이 매우 어려움(예: 어떤 시점에 무엇이 사라졌는지)

### 비용/성능/안정성 트레이드오프
- Compaction은 공짜가 아니고, 추가 LLM call과 운영 복잡도를 가져옵니다(“Summary tax”).[^2]  
- 그러나 “긴 컨텍스트를 그대로 유지”하는 접근은 토큰 경제 측면에서 빠르게 비싸지고, 성능도 일정 길이 이후 떨어질 수 있다는 논의/리뷰가 이어집니다.[^8]  
- 따라서 실무 최적점은 보통: **(1) pinned state 최소화 + (2) 구조화 메모리 + (3) 최근 원문 window + (4) 필요 시 query-aware로 blob 복원**입니다.

---

## 🚀 마무리
2026년 8월 기준, long context window는 충분히 커졌지만 “제대로 쓰게 만드는 기술”은 별개 문제입니다. 핵심은:

- *lost in the middle*은 실재하는 실패 모드이며, attention bias/position bias 관점에서 **배치와 재배치**가 즉효입니다.[^1]  
- compaction은 요약이 아니라 **상태 관리(state management)**로 접근해야 드리프트/독성 요약을 줄입니다.[^9]  
- RAG는 “더 가져오기”가 아니라 “질문 적응형 압축/선별”이 기본 설계가 되어가고 있습니다.[^7]  

**도입 판단 기준**
- 대화/agent가 50~200 turn 이상, 혹은 툴 출력이 크고 반복 참조된다 → compaction 설계 가치 큼  
- 중요한 사실(식별자/제약/결정)이 중간에 묻혀 자주 누락된다 → pinned + end-bias 배치부터 적용  
- 요약 품질이 불안정하다 → 구조화 메모리 + 회귀 테스트(“핵심 상태를 N step 후에도 복원 가능한가”)를 먼저

**다음 학습 추천**
- *Found in the middle* (position bias 교정)[^1]  
- AttnComp / Adaptive Context Compression 계열(질문 적응형 RAG 압축)[^7]  
- Bedrock server-side compaction 문서(플랫폼 기능을 쓸 경우 동작/제약 파악)[^6]

[^1]: <https://research.google/pubs/found-in-the-middle-calibrating-positional-attention-bias-improves-long-context-utilization/>
[^2]: <https://tianpan.co/blog/2026-05-09-summary-tax-compaction-eats-more-tokens-than-it-saves>
[^3]: <https://github.com/microsoft/longrope>
[^4]: <https://academ.us/article/2607.08032/>
[^5]: <https://openreview.net/pdf?id=6AWWE08NnN>
[^6]: <https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-compaction.html>
[^7]: <https://aclanthology.org/2025.findings-emnlp.449/>
[^8]: <https://openreview.net/pdf?id=e8ycTWGTIR>
[^9]: <https://tianpan.co/blog/2026-04-19-compaction-traps-long-running-agents>
