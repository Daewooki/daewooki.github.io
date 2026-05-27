---
title: "컨텍스트가 1M 토큰이어도 망한다: 2026년식 LLM Long Context Compaction으로 “Lost in the Middle” 잡는 법"
date: 2026-05-27 04:28:37 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-05]
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
LLM long context window가 커질수록 “이제 RAG 없이 문서/대화/에이전트 히스토리를 통째로 넣어도 되겠지?”라는 유혹이 생깁니다. 그런데 2026년 5월 기준 실무 결론은 정반대입니다. **긴 컨텍스트는 ‘저장 용량’이 아니라 ‘주의력(attention) 예산’ 문제**라서, 윈도우가 커져도 **signal dilution + lost in the middle**로 성능이 떨어집니다. Morph의 정리처럼 입력 길이가 늘면(윈도우를 다 채우지 않아도) 신뢰도가 감소하고, 관련 정보가 중간에 있으면 정확도가 크게 빠집니다. ([morphllm.com](https://www.morphllm.com/context-compression))

**언제 쓰면 좋나**
- 장시간 실행되는 coding agent / ops agent처럼 **툴 출력, 로그, diff, 에러 트레이스가 누적**되는 워크로드
- “이전 결정을 보존하면서 다음 스텝을 계속”해야 하는 multi-turn(요구사항, 제약, 결정사항 유지)
- RAG를 쓰더라도, “검색 결과 + 최근 히스토리”가 계속 쌓이는 구조(결국 compaction 필요)

**언제 쓰면 안 되나**
- 법/의료/금융 등 **원문 근거의 완전성**이 핵심인 경우: aggressive summary는 감사(audit) 불가능한 손실을 만듭니다. 이때는 “원문 span 유지 + 최소 요약 + 근거 링크” 전략이 필요합니다.
- 태스크가 단발성이고 컨텍스트가 짧은데도 compaction을 걸어 **불필요한 정보 변형**을 만드는 경우(요약은 곧 변형)

---

## 🔧 핵심 개념
### 1) Compaction vs Summary: “토큰 줄이기”가 목적이 아니다
실무에서 compaction은 크게 두 계열입니다.

- **LLM summarization (semantic compression)**: 텍스트를 재서술해 짧게 만듦. 장점은 고압축, 단점은 **손실/왜곡/비결정성**.
- **Verbatim/structural compaction (lossless-ish)**: 형식 노이즈 제거, 중복 제거, 구조화(예: JSON 정규화, 로그 축약)로 토큰을 줄임. Morph가 “verbatim compaction은 hallucination risk가 낮고 빠르다”고 구분한 이유가 여기 있습니다. ([morphllm.com](https://www.morphllm.com/context-compression))

2026년 5월에 흥미로운 흐름은 “요약을 잘하자”를 넘어서 **‘무엇을 잃으면 안 되는가’를 명시하고 검증**하려는 시도입니다. *Compress the Context, Keep the Commitments*는 컨텍스트를 단순 텍스트가 아니라 **commitment(목표/제약/결정/선호/근거/안전 경계)**의 집합으로 보고, 이를 **typed atoms**로 추출→정규화→렌더링→검증하는 프레임워크(Context Codec, CCL)를 제안합니다. 즉 “요약이 맞는지”가 아니라 **Critical Atom Recall 같은 지표로 ‘보존해야 할 의미’가 살아남았는지**를 보자는 접근입니다. ([arxiv.org](https://arxiv.org/abs/2605.17304))

### 2) Lost in the Middle은 “검색 문제”가 아니라 “배치/주의력 문제”
Lost in the middle은 단순히 “모델이 멍청해서”가 아니라, 긴 입력에서 **중간 구간의 정보 활용이 구조적으로 불리**해지는 현상입니다. 그래서 긴 컨텍스트를 그냥 늘리는 전략은 비용만 늘리고(더 많은 토큰) 정확도는 안정적으로 보장하지 못합니다. Morph도 “bigger windows don’t solve the problem” 맥락에서 이걸 강조합니다. ([morphllm.com](https://www.morphllm.com/context-compression))

결론: compaction 설계의 핵심은
- **중요 정보를 ‘앞/뒤 앵커(anchor)’로 끌어올리고**
- 중간은 “원문 보관소”로 두되, 모델이 재참조할 수 있는 **키/포인터/근거 span**을 남기는 것

### 3) 2026년 5월의 최신 포인트 3가지
1) **Parallel Context Compaction**: 요약(LLM call)이 에이전트 inference를 블로킹하고, 요약량이 매번 흔들리는 문제를 지적하면서, compaction을 **병렬화해 wall time을 줄이고 블록별로 더 예측 가능한 볼륨 제어**를 하자는 연구가 2026-05-22 arXiv로 나왔습니다. 운영 관점에서 “요약이 느려서 못 써”를 직접 겨냥합니다. ([arxiv.org](https://arxiv.org/abs/2605.23296))  
2) **Write-time 진단과 EPC(예측 보존)**: WhenLoss는 long-context memory 실패를 “retrieval이 못 찾는 문제”와 “write(압축/저장) 단계에서 버린 문제”로 분해해 진단하고, write-time에 미래 질문을 예측해 최소 근거를 남기는 EPC를 제안합니다. 즉 compaction은 “나중에 질문 오면 요약하자”가 아니라 **저장 시점에 무엇을 남길지**가 더 중요할 수 있다는 결론입니다. ([arxiv.org](https://arxiv.org/abs/2605.24579))  
3) **모델 내부 관점의 context 관리**: Microsoft Research의 Memento는 모델이 생성 중 자기 CoT를 블록으로 나눠 “memento”로 압축해 **KV cache를 줄이고 throughput을 높이는** 방향(서빙 최적화)을 보여줍니다. 앱 레벨 compaction과는 층위가 다르지만, “컨텍스트 관리는 이제 시스템의 1급 primitive”라는 신호입니다. ([microsoft.com](https://www.microsoft.com/en-us/research/articles/memento-teaching-llms-to-manage-their-own-context/))  

---

## 💻 실전 코드
아래는 “장시간 돌아가는 coding agent”를 전제로, **툴 출력/로그는 lossless에 가깝게 구조 compaction**, **대화/결정사항은 commitment atom으로 요약**, 그리고 **lost-in-the-middle 완화용 앵커 배치**까지 포함한 예시입니다.

- 스택: Python + OpenAI API(예시) + tiktoken(토큰 추정)  
- 포인트: “요약 한 방”이 아니라, (1) 이벤트를 타입화하고 (2) 보존해야 할 commitments를 구조화하고 (3) 최근 N턴 + commitments + 선택된 원문 증거만 컨텍스트로 재구성

```bash
pip install openai tiktoken pydantic
export OPENAI_API_KEY="..."
```

```python
from __future__ import annotations
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel
import json, re, time

import tiktoken
from openai import OpenAI

client = OpenAI()

# --------- 1) 데이터 모델: "텍스트"가 아니라 이벤트/커밋먼트로 저장 ----------
class ToolObs(BaseModel):
    tool: str
    ts: float
    # 원문은 저장하되, 컨텍스트에는 compact 버전만 넣는다
    raw: str
    compact: str
    # 나중에 근거로 다시 가져올 수 있도록 해시/키를 둔다
    key: str

class CommitmentAtom(BaseModel):
    type: Literal["goal","constraint","decision","fact","risk","next_step"]
    text: str
    evidence_keys: List[str] = []
    confidence: float = 0.7  # 운영에서는 eval로 보정

class MemoryState(BaseModel):
    atoms: List[CommitmentAtom] = []
    tool_obs: List[ToolObs] = []
    recent_dialogue: List[Dict[str,str]] = []  # [{"role":"user","content":"..."}, ...]

# --------- 2) Lossless-ish compaction: 로그/JSON/diff 노이즈를 줄인다 ----------
def compact_json_like(s: str) -> str:
    # JSON이 섞인 로그에서 공백/정렬 노이즈 제거(완전한 파서는 아니고 실무형 휴리스틱)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def compact_terminal_output(s: str, max_lines: int = 120) -> str:
    lines = s.splitlines()
    # 너무 긴 출력은 "중요 헤더/에러 라인"을 우선 남긴다(여기서 완전 손실 없는 건 불가)
    keep = []
    for ln in lines:
        if ("error" in ln.lower()) or ("failed" in ln.lower()) or ln.startswith(("Traceback", "Exception")):
            keep.append(ln)
    head = lines[:40]
    tail = lines[-40:] if len(lines) > 80 else []
    merged = head + (["…(snip)…"] if len(lines) > max_lines else []) + keep[:40] + tail
    merged = merged[:max_lines]
    return "\n".join(dict.fromkeys(merged))  # 중복 라인 제거(순서 보존)

def make_tool_obs(tool: str, raw: str) -> ToolObs:
    compact = compact_json_like(raw)
    compact = compact_terminal_output(compact)
    key = f"{tool}:{hash(raw) & 0xffffffff:x}"
    return ToolObs(tool=tool, ts=time.time(), raw=raw, compact=compact, key=key)

# --------- 3) Commitment atom 추출(요약이 아니라 "보존해야 할 것"을 구조화) ----------
ATOM_SCHEMA = {
  "type":"object",
  "properties":{
    "atoms":{
      "type":"array",
      "items":{
        "type":"object",
        "properties":{
          "type":{"type":"string","enum":["goal","constraint","decision","fact","risk","next_step"]},
          "text":{"type":"string"},
          "evidence_keys":{"type":"array","items":{"type":"string"}},
          "confidence":{"type":"number"}
        },
        "required":["type","text","evidence_keys","confidence"]
      }
    }
  },
  "required":["atoms"]
}

def extract_atoms_with_llm(dialogue: List[Dict[str,str]], recent_tool_obs: List[ToolObs]) -> List[CommitmentAtom]:
    # lost-in-the-middle 완화를 위해: 모델이 반드시 봐야 하는 규칙/출력형식을 "맨 위"에 둔다
    tool_index = "\n".join([f"- {o.key}: {o.tool} @ {time.strftime('%H:%M:%S', time.localtime(o.ts))}" for o in recent_tool_obs][-20:])
    prompt = f"""
You are a senior SWE agent memory compressor.
Task: extract commitments that MUST survive compaction.

Rules:
- Do NOT rewrite tool outputs; only cite them by evidence_keys.
- Prefer atomic, testable statements.
- If a constraint or decision exists, include it.
- Output JSON only, matching the schema.

Available evidence keys (tool outputs stored externally):
{tool_index}
""".strip()

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role":"system","content":prompt},
            {"role":"user","content":json.dumps({"recent_dialogue": dialogue[-12:]}, ensure_ascii=False)}
        ],
        response_format={"type":"json_schema","json_schema":{"name":"atoms", "schema": ATOM_SCHEMA}}
    )
    data = json.loads(resp.output_text)
    return [CommitmentAtom(**a) for a in data["atoms"]]

# --------- 4) 컨텍스트 빌더: 앵커(앞/뒤) + 중간은 포인터 중심 ----------
def build_model_context(state: MemoryState, user_request: str) -> List[Dict[str,str]]:
    # 앞 앵커: 운영 규칙/현재 목표/제약
    atoms_txt = "\n".join([f"- [{a.type}] {a.text} (evidence={a.evidence_keys}, conf={a.confidence:.2f})"
                           for a in state.atoms][-40:])

    # 중간: 툴 출력은 "compact + key"만 (원문은 key로 재조회)
    tool_txt = "\n\n".join([f"[{o.key}] {o.tool}\n{o.compact}" for o in state.tool_obs][-8:])

    # 뒤 앵커: 가장 최근 대화(모델이 잘 보는 tail에 최신 요구를 둠)
    context = [
        {"role":"system","content": "You are a coding agent. Use commitments as source of truth. If missing evidence, ask to fetch by key."},
        {"role":"system","content": f"Commitments (must-follow):\n{atoms_txt}"},
        {"role":"system","content": f"Recent tool observations (compacted, cite by key):\n{tool_txt}"},
    ]
    context += state.recent_dialogue[-8:]
    context += [{"role":"user","content": user_request}]
    return context

# --------- 5) 데모: 실제 시나리오(리포지토리 빌드 실패 → 원인 추적) ----------
def run():
    state = MemoryState()

    # (A) 최근 대화 누적
    state.recent_dialogue += [
        {"role":"user","content":"우리 monorepo에서 api-server 빌드가 CI에서만 실패해. 원인 추적 도와줘."},
        {"role":"assistant","content":"좋아요. CI 로그와 로컬 환경 차이를 확인해야 해요. 먼저 CI 빌드 로그를 붙여주세요."},
    ]

    # (B) 툴 출력(긴 로그) 유입 → 구조 compaction
    raw_ci_log = """
    ... 3000 lines ...
    ERROR: ModuleNotFoundError: No module named 'orjson'
    pip freeze:
      fastapi==0.110.0
      ...
    """
    obs = make_tool_obs("ci_log", raw_ci_log)
    state.tool_obs.append(obs)

    # (C) 커밋먼트 추출(결정/제약/다음 행동)
    state.atoms = extract_atoms_with_llm(state.recent_dialogue, state.tool_obs)

    # (D) 다음 요청에 대해 컨텍스트 구성 후 모델 호출
    ctx = build_model_context(state, "이제 무엇부터 확인하면 돼? 재현 가능한 디버깅 플랜을 단계별로 제시해줘.")
    resp = client.responses.create(
        model="gpt-4.1",
        input=ctx
    )
    print(resp.output_text)

if __name__ == "__main__":
    run()
```

**예상 출력(요지)**  
- commitments에 “CI에서만 실패”, “ModuleNotFoundError: orjson” 같은 **핵심 fact/next_step**이 잡히고  
- 모델은 “pyproject/requirements lock 불일치, extras 미설치, 플랫폼 wheel 이슈” 등 **재현 플랜**을 내며  
- 추가 로그가 필요하면 “evidence key(ci_log:xxxx)” 기반으로 **원문 재조회 요청**을 하게 됩니다(요약이 아니라 포인터 전략).

이 구조의 장점은 “대화가 길어져도” 모델이 봐야 할 것은 앞/뒤 앵커에 고정되고, 중간은 포인터화되어 **lost-in-the-middle을 구조적으로 완화**한다는 점입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Compaction은 ‘비율’이 아니라 ‘보존 대상’부터 정의**
   - “몇 % 줄였나”보다 “무엇(결정/제약/근거)을 절대 잃으면 안 되나”가 먼저입니다. Context Codec류가 말하는 commitment/atom 단위 접근이 이 문제를 정면으로 다룹니다. ([arxiv.org](https://arxiv.org/abs/2605.17304))
2) **Write-time에 남길 것을 결정하라**
   - WhenLoss의 메시지처럼, 실패 원인이 retrieval 이전에 “써놓을 때 버린 것”일 수 있습니다. 툴 출력/문서가 들어오는 순간에 (a) key 생성 (b) compact 버전 생성 (c) atom이 참조할 evidence span/key를 남기는 파이프라인을 만드세요. ([arxiv.org](https://arxiv.org/abs/2605.24579))
3) **요약 LLM call은 병목이 된다 → 병렬화/비동기화 고려**
   - long-horizon agent에서 요약이 blocking call이 되면 체감 latency가 폭증합니다. Parallel Context Compaction은 이 병목 자체를 연구 주제로 삼습니다. 실무에서도 “요약은 백그라운드 작업 + 다음 턴은 최근 히스토리로 먼저 진행” 같은 설계를 추천합니다. ([arxiv.org](https://arxiv.org/abs/2605.23296))

### 흔한 함정/안티패턴
- **한 방 요약으로 모든 걸 덮기**: 요약 프롬프트가 “중요한 거 다 넣어”라고 말해도, 실제로는 누락/왜곡이 생기고 다음 턴에서 hallucination이 터집니다(특히 코드/버전/숫자).
- **툴 출력까지 semantic 요약**: 로그/diff/JSON을 LLM이 자연어로 바꾸는 순간, “정확히 무엇이었나”가 사라집니다. 툴 출력은 가능한 한 구조 compaction + key 참조로 두세요.
- **앵커가 없다**: commitments를 만들었는데도, 최종 프롬프트 중간에 박아두면 lost-in-the-middle로 다시 약해집니다. **앞(system)과 뒤(user 직전)**에 배치하는 “sandwich”가 실무 체감이 큽니다.

### 비용/성능/안정성 트레이드오프
- **LLM summarization**: 비용/지연 ↑, 압축률 ↑, 안정성은 설계에 따라 ↓  
- **Structural compaction**: 비용/지연 ↓, 압축률 중간, 안정성 ↑  
- **Hybrid(추천)**: “결정/제약/다음 행동”은 atom 요약(짧고 구조화), “근거”는 key로 원문 보관

---

## 🚀 마무리
2026년 5월의 long context compaction 트렌드를 한 줄로 요약하면: **“더 큰 window”가 아니라 “더 나은 memory layout + verifiable compaction”**입니다. Lost in the middle은 프롬프트 요령으로 잘 안 고쳐지고, 결국 (1) commitments를 추출해 앵커로 고정하고 (2) 툴/근거는 key 기반으로 분리 저장하고 (3) write-time에 무엇을 남길지 설계하며 (4) 요약 호출은 병렬화/비동기화로 운영 병목을 없애는 쪽이 승률이 높습니다. ([morphllm.com](https://www.morphllm.com/context-compression))

**도입 판단 기준**
- “대화/에이전트가 30분~수시간 지속” + “툴 출력이 폭증” + “이전 결정사항을 자주 재사용”이면: compaction은 옵션이 아니라 기본 기능
- “정확한 원문 근거가 곧 제품 신뢰”이면: semantic summary 단독은 금지, atom+evidence key 방식으로 감사 가능하게

**다음 학습 추천(실무 로드맵)**
1) 여러분 도메인에 맞는 atom 타입 정의(goal/constraint/decision/fact/risk/next_step부터) ([arxiv.org](https://arxiv.org/abs/2605.17304))  
2) WhenLoss류 진단처럼 write vs retrieval 실패를 분리해 측정(간단한 A/B라도) ([arxiv.org](https://arxiv.org/abs/2605.24579))  
3) 요약이 병목이면 Parallel/async compaction으로 파이프라인화 ([arxiv.org](https://arxiv.org/abs/2605.23296))  

원하시면, (a) 여러분 서비스의 실제 이벤트 스키마(툴 종류, 로그 형태, 사용자 요청 패턴)와 (b) 목표 토큰 예산(예: 64K/128K/256K)을 알려주시면, 위 코드를 “프로덕션용 compaction policy + eval 체크리스트(NIAH 위치별, atom recall)”까지 확장해서 구체화해드릴게요.