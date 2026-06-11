---
title: "컨텍스트가 길어질수록 성능이 나빠진다: 2026년 LLM Long Context에서 “Compaction”으로 이기는 법"
date: 2026-06-11 04:46:59 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-06]
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
2026년의 LLM은 128k~수백 k, 심지어 “백만 토큰”급 컨텍스트를 내세우지만, **긴 컨텍스트를 “그대로 다 넣는 것”이 곧 문제 해결**로 이어지진 않습니다. 대표 증상이 두 가지입니다.

- **Lost in the middle**: 중요한 근거가 프롬프트 “중간”에 있으면 정답률이 떨어지는 현상(긴 컨텍스트 모델에서도 관찰). ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))  
- **Context bloat → 비용/지연/불안정**: 에이전트나 RAG에서 툴 출력·로그·중복 문서가 누적되며, 토큰 비용과 latency가 급증하고 “제약 조건 상실/환각”이 늘어남.

그래서 2025~2026년 실무 흐름은 “컨텍스트를 늘리는 경쟁”에서 **컨텍스트를 관리(압축/정리/재배치)하는 compaction**으로 무게중심이 이동했습니다. OpenAI는 Responses API에 **native compaction**을 넣어 “요약/상태 유지 시스템을 직접 설계하는 부담을 줄이겠다”고 명시했고, 초과 직전 요청을 compaction으로 흡수하는 동작도 언급합니다. ([openai.com](https://openai.com/index/equip-responses-api-computer-environment?utm_source=openai)) LangChain은 Deep Agents에서 **임계치 기반 요약 + 에이전트가 스스로 압축을 트리거하는 autonomous context compression**까지 제공하기 시작했죠. ([langchain.com](https://www.langchain.com/blog/context-management-for-deepagents?utm_source=openai))

### 언제 쓰면 좋은가
- **Long-running agent**(코드 리팩터링, 멀티파일 편집, 인시던트 대응, 리서치/툴 반복 호출)처럼 “대화가 길어지는 게 정상”인 워크플로우 ([langchain.com](https://www.langchain.com/blog/autonomous-context-compression?utm_source=openai))
- RAG에서 top-k chunk를 그대로 넣으면 **노이즈가 더 커져** 품질이 떨어지는 경우(특히 multi-doc QA)
- 팀/프로덕트에서 **토큰 비용 상한**이 확실한 경우(운영 예산/레이트리밋)

### 언제 쓰면 안 되는가 (혹은 조심해야 하는가)
- 법률/의료/감사 등 **원문 근거의 정확한 보존**이 중요한 경우: 요약은 본질적으로 lossy
- “이전에 말한 값/조건”이 **정확히 재현**되어야 하는 자동화(예: 배포 파라미터, 보안 설정)에서 무분별한 대화 요약
- **Compaction 결과를 검증/추적(audit trail)**하지 못하는 시스템: 한 번 잘못 압축되면 이후 모든 추론이 오염됨(복구 비용이 큼)

---

## 🔧 핵심 개념
긴 컨텍스트 활용을 “많이 넣기”로 생각하면 실패합니다. 2026년의 정답은 **Window(버퍼)와 Memory(내구 저장)를 분리**하고, Window 안에서는 **compaction으로 ‘좋은 형태’의 입력을 유지**하는 것입니다(“compaction is not memory”라는 경고가 반복됨). ([memnode.dev](https://memnode.dev/articles/compaction-is-not-memory-context-window?utm_source=openai))

### 1) Compaction의 정의: “요약”이 아니라 “상태(state) 재구성”
실무 compaction은 보통 3개 레이어로 나뉩니다.

- **Conversation state**: 합의된 결정, 변수 값, 제약 조건, TODO, 미해결 질문
- **Evidence index**: 원문 근거의 위치/출처(파일, URL, chunk id, line range)
- **Working set**: 지금 단계에서 바로 쓰는 근거(“이번 호출에 필요한 것만”)

여기서 핵심은 **요약문만 남기면 lost-in-the-middle + 근거 소실**로 망합니다. 대신 요약 결과에 **앵커(anchor)** 를 박습니다:
- “결론/결정/제약”은 짧게
- “근거”는 *짧은 인용 + 포인터* (id/경로/오프셋)로 남겨 재확장 가능하게

LangChain Deep Agents는 대화 전체를 “가상 파일시스템”에 보관하고, 임계치에서 요약(compaction)을 수행한다고 설명합니다. 즉, **Window를 줄이되 원문은 밖에 보관**하는 구조가 기본 전제입니다. ([langchain.com](https://www.langchain.com/blog/context-management-for-deepagents?utm_source=openai))

### 2) Lost in the middle과 Compaction의 연결
“Lost in the Middle” 연구는 **관련 정보가 문맥의 시작/끝에 있을 때 성능이 높고, 중간에 있을 때 떨어진다**는 실험 결과를 제시합니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))  
이걸 시스템 설계로 번역하면:

- 컨텍스트가 길어질수록, “중간에 묻힌 핵심 제약/질문/정답 근거”가 무시될 확률이 커진다
- 따라서 compaction의 목적은 단순 토큰 절감이 아니라  
  **(a) 핵심을 ‘끝부분’으로 재배치하고 (b) 노이즈를 제거해 신호 대 잡음비를 올리는 것**

Anthropic도 long-context 프롬프트에서 “질문/관련 구간의 거리”에 따른 성능 저하를 다루며, 실무적으로는 **질문을 끝에 두거나 재진술**하는 패턴이 자주 쓰입니다. ([anthropic.com](https://www.anthropic.com/news/prompting-long-context?utm_source=openai))

### 3) 접근 방식 비교: “긴 컨텍스트 vs RAG vs Compression”
- **Long context packing**: 코드베이스/대규모 문서를 통째로 넣고 cross-section reasoning이 필요할 때 유리. 하지만 비용·중간 망각·노이즈에 취약.
- **RAG**: 필요한 chunk만 넣어 비용/노이즈를 줄이지만, retrieval 오류나 chunk 단절로 논리 일관성이 깨질 수 있음.
- **Contextual compression / compaction**: RAG와 결합이 특히 강력. “찾은 문서”를 **질문 기준으로 압축해 관련 부분만** 남김. LangChain은 `ContextualCompressionRetriever`로 이를 명시적으로 제공. ([langchain.com](https://www.langchain.com/blog/improving-document-retrieval-with-contextual-compression?utm_source=openai))
- **Recursive/Tree 요약(MapReduce)**: 문서를 계층적으로 요약/통합해 coherence를 유지하려는 흐름(예: Tree MapReduce reasoning). ([arxiv.org](https://arxiv.org/abs/2511.00489?utm_source=openai))
- **Multi-scale RAG**(예: MacRAG): “압축 + 슬라이싱 + 스케일”로 다단계 컨텍스트 구성을 최적화해 LongBench 계열에서 개선을 보고. ([arxiv.org](https://arxiv.org/abs/2505.06569?utm_source=openai))

평가 측면에선 LongBench v2처럼 8k~2M words까지 포함하는 벤치마크가 등장하면서, “길게 넣기만 하면 된다”는 환상이 더 빨리 깨지고 있습니다. ([arxiv.org](https://arxiv.org/abs/2412.15204?utm_source=openai))

---

## 💻 실전 코드
아래는 “사내 장애 대응(incident) 에이전트”를 가정한 **현실적인 파이프라인**입니다.

- Slack/티켓/로그 요약이 계속 누적되어 컨텍스트가 터짐
- 매 단계마다 “현재 가설/결정/미해결/근거”를 **구조화 compaction**으로 유지
- lost-in-the-middle 완화를 위해 **핵심 state를 항상 프롬프트 끝에 붙임**
- 근거는 포인터로 남겨 필요 시 재확장(원문은 외부 저장: S3/DB/Vector store)

### 1) 의존성/실행
```bash
pip install openai pydantic tiktoken
export OPENAI_API_KEY="..."
```

### 2) Compaction 스키마 + 토큰 예산 기반 트리거
```python
from __future__ import annotations
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import time
import tiktoken
from openai import OpenAI

client = OpenAI()

MODEL = "gpt-5-thinking"  # 예시: 실제 사용 모델로 교체

enc = tiktoken.get_encoding("o200k_base")

def count_tokens(text: str) -> int:
    return len(enc.encode(text))

class Evidence(BaseModel):
    source: str  # e.g., "slack://channel/ts", "s3://bucket/key", "log://service#offset"
    snippet: str # 1~2문장(짧게). 원문 전체 금지
    relevance: str

class CompactState(BaseModel):
    goal: str
    current_hypothesis: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)  # SLA, policy, forbidden actions, etc.
    next_actions: List[str] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    audit_trail: List[str] = Field(default_factory=list)  # "why we compacted / what dropped"

def compact_messages(messages: List[Dict[str, str]], prev_state: Optional[CompactState]) -> CompactState:
    """
    대화 전체를 단순 요약하지 말고:
    - 상태(state) + 근거 포인터(evidence) + 추적(audit)을 생성
    - prev_state가 있으면 덮어쓰기/중복 제거/충돌 해결
    """
    system = (
        "You are a senior SRE agent. Compact the conversation into a durable state.\n"
        "Rules:\n"
        "- Keep constraints, decisions, parameters exact.\n"
        "- Evidence must include a short snippet + a pointer-like source.\n"
        "- If uncertain, add to open_questions.\n"
        "- Add an audit_trail note about what was dropped/merged.\n"
        "Return valid JSON matching the CompactState schema."
    )

    # prev_state를 함께 넣어 '증분 compaction' 유도
    prev = prev_state.model_dump() if prev_state else None

    resp = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"prev_state={prev}"},
            {"role": "user", "content": f"messages={messages}"},
        ],
        # 응답을 JSON으로 강제(실제 지원 옵션은 모델/SDK 버전에 맞춰 조정)
        response_format={"type": "json_object"},
    )

    data = resp.output_text
    return CompactState.model_validate_json(data)

def build_prompt(task: str, state: CompactState, working_context: str) -> List[Dict[str, str]]:
    """
    lost-in-the-middle 완화:
    - 긴 working_context(로그/문서)는 위에 두되,
    - 'state 요약'과 '질문/지시'는 맨 끝에 반복 배치
    """
    return [
        {"role": "system", "content": "You are an incident response assistant. Be precise and cite evidence sources."},
        {"role": "user", "content": f"Working context (may be long):\n{working_context}"},
        {"role": "user", "content": "----\nCOMPACT STATE (authoritative):\n" + state.model_dump_json(indent=2)},
        {"role": "user", "content": f"Task:\n{task}\n\nInstructions:\n- Use COMPACT STATE as truth.\n- If evidence is insufficient, request specific sources.\n- Produce: diagnosis, mitigation steps, and what to check next."},
    ]

class ContextManager:
    def __init__(self, soft_limit_tokens: int = 120_000):
        self.soft_limit = soft_limit_tokens
        self.messages: List[Dict[str, str]] = []
        self.state: Optional[CompactState] = None

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def maybe_compact(self):
        # 단순하지만 실무에서 자주 쓰는: soft limit 넘기기 직전 compaction
        total = sum(count_tokens(m["content"]) for m in self.messages)
        if total > self.soft_limit:
            before = total
            self.state = compact_messages(self.messages, self.state)
            # 메시지는 “최근 몇 개 + state”만 남김(원문은 외부 저장이 이상적)
            self.messages = self.messages[-6:]
            after = sum(count_tokens(m["content"]) for m in self.messages) + count_tokens(self.state.model_dump_json())
            self.state.audit_trail.append(f"compacted_at={time.time()} tokens_before={before} tokens_after~={after}")

# ---- 사용 예: 장애 대응 루프 ----
if __name__ == "__main__":
    cm = ContextManager(soft_limit_tokens=20_000)  # 데모: 작은 값

    # (현실 시나리오) 툴/로그 출력이 누적된다고 가정
    cm.add("user", "DB latency가 20:10부터 급증. p95 2s -> 12s. 서비스 A 타임아웃 증가.")
    cm.add("assistant", "확인할 것: slow query log, connection pool, deploy event, downstream dependency.")
    cm.add("user", "slow query log: SELECT ... FROM orders WHERE user_id=? AND status IN (...) ORDER BY created_at DESC LIMIT 50; 평균 800ms")
    cm.add("user", "배포: 20:05에 orders-service에 인덱스 변경 없는 릴리즈")
    cm.maybe_compact()

    # working_context는 매 요청마다 다르게(최근 로그/메트릭)
    working_context = "Grafana: DB CPU 90%, connections 95%...\n(중략: 긴 로그/메트릭 덤프)"
    if cm.state is None:
        # 첫 호출에서 state가 없으면 최소 state 구성
        cm.state = CompactState(goal="Stabilize production latency for service A")

    prompt = build_prompt(
        task="가장 가능성 높은 원인 2개와 즉시 적용 가능한 완화(mitigation) 플랜을 제시해줘.",
        state=cm.state,
        working_context=working_context,
    )

    answer = client.responses.create(model=MODEL, input=prompt)
    print(answer.output_text)
```

### 예상 출력(형태)
- 원인 가설(예: 인덱스 부재/통계 갱신 문제, connection pool 고갈, 핫 파티션)
- 즉시 완화(쿼리 힌트/인덱스 추가 전 임시 우회, pool limit 조정, read replica 라우팅)
- “어떤 evidence source로 확인할지”를 명시(슬랙 타임스탬프/로그 포인터)

이 구조의 포인트는 **“긴 working_context를 매번 바꿔 끼우고, state는 작고 단단하게 유지”**하는 것입니다. 즉, window를 “메모리”로 쓰지 않습니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3)
1) **State를 ‘데이터 모델’로 강제하라**  
자연어 요약 한 덩어리는 결국 drift가 납니다. `constraints/decisions/open_questions/evidence`처럼 필드를 쪼개고, compaction 결과를 JSON schema로 검증하세요. (LangChain/에이전트 프레임워크를 쓰더라도 이 계층은 별도로 두는 게 안전)

2) **Evidence는 “짧은 snippet + 포인터”로 남겨라**  
요약이 틀릴 수 있다는 걸 전제로, 원문 재조회가 가능한 형태로 남기는 게 운영 복구에 결정적입니다. Deep Agents가 “대화 기록을 파일시스템에 보관”하는 것도 같은 이유입니다. ([langchain.com](https://www.langchain.com/blog/context-management-for-deepagents?utm_source=openai))

3) **lost-in-the-middle 완화는 ‘재배치’가 1순위**  
핵심 지시/질문/제약을 프롬프트 끝에 반복 배치하고, “이번 호출의 목표/성공 조건”을 마지막에 다시 말하게 하세요. 논문이 말하는 현상 자체가 “중간이 약하다”이므로, UX 레벨에서 위치를 바꾸는 게 가장 싸고 강력합니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))

### 흔한 함정/안티패턴
- **Rolling summary만 계속 이어붙이기**: 요약 위에 요약을 얹으면 작은 오류가 누적되어 “context rot”가 됩니다. “compaction is not memory” 경고가 여기서 나옵니다. ([memnode.dev](https://memnode.dev/articles/compaction-is-not-memory-context-window?utm_source=openai))  
- **툴 출력(로그/HTML/JSON)을 무조건 대화에 붙이기**: 가장 빨리 컨텍스트를 망치는 패턴. 원문은 외부 저장 + 필요한 부분만 working set으로 올리세요.
- **Compaction 타이밍을 토큰 임계치로만 결정**: LangChain이 “에이전트가 적절한 순간에 스스로 압축 트리거”를 넣은 이유가 있습니다. 작업 경계(task boundary)나 결론 도출 직후가 더 안전한 경우가 많습니다. ([langchain.com](https://www.langchain.com/blog/autonomous-context-compression?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **Compaction 호출 자체가 비용**이며, 큰 모델로 하면 더 비쌉니다. 다만 “컨텍스트 폭발로 매 호출이 비싸지는 것”을 막아 총비용을 줄이는 경우가 많습니다.
- **Blocking latency**: compaction이 동기적으로 들어가면 에이전트가 멈춥니다. 2026년에는 “parallel context compaction”처럼 serving 관점에서 병렬화/비동기화를 연구하는 흐름도 나왔습니다. ([arxiv.org](https://arxiv.org/abs/2605.23296?utm_source=openai))
- **정확도 vs 압축률**: 압축률을 올릴수록 evidence 손실 위험이 커집니다. 운영 시스템이라면 “state는 보수적으로, working set은 공격적으로”가 보통 더 안전합니다.

---

## 🚀 마무리
정리하면, 2026년 long context의 실전 해법은 “컨텍스트를 늘려서 해결”이 아니라:

- **Window는 버퍼**로 보고,
- **Compaction은 상태(state) + 근거 포인터(evidence) + 추적(audit)**을 남기는 “구조화 작업”으로 만들고,
- **lost-in-the-middle을 전제로 핵심을 프롬프트 끝에 고정**하는 것입니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))

### 도입 판단 기준(내 프로젝트 체크리스트)
- 대화/에이전트 세션이 **30분~수시간 이상** 지속되나?
- 툴 출력/문서가 누적되어 **토큰 비용이 선형 이상으로 증가**하나?
- 실패 원인이 “추론력 부족”보다 **제약/결정의 망각**에 가깝나?
- compaction 결과를 **스키마 검증 + 원문 재조회**로 통제할 수 있나?

### 다음 학습 추천
- Lost in the Middle 원 논문(평가 프로토콜/현상 이해) ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))  
- LongBench v2로 “내 파이프라인이 긴 컨텍스트에서 어디서 깨지는지” 측정 ([arxiv.org](https://arxiv.org/abs/2412.15204?utm_source=openai))  
- LangChain Contextual Compression(검색-후-압축의 구현 패턴) ([langchain.com](https://www.langchain.com/blog/improving-document-retrieval-with-contextual-compression?utm_source=openai))  
- OpenAI Responses API의 native compaction 개념(상용 환경에서의 설계 방향) ([openai.com](https://openai.com/index/equip-responses-api-computer-environment?utm_source=openai))  

원하시면, 위 코드 예제를 **(1) LangChain Deep Agents 기반**, **(2) RAG + ContextualCompressionRetriever 결합**, **(3) “실패 시 역추적(what did we drop?)” 자동 평가 루프**까지 확장한 버전으로 재작성해 드릴게요.