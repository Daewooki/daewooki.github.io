---
title: "컨텍스트 1M 시대에도 “기억”은 부족하다: 2026년 8월 LLM Long Context Compaction 설계 가이드 (Lost-in-the-Middle 대응 포함)"
date: 2026-08-06 03:21:00 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-08]
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
긴 컨텍스트(window 200K~1M)가 보편화되면서 “그냥 다 넣으면 되겠지”라는 유혹이 커졌습니다. 하지만 실제 프로덕션에서는 **(1) 토큰 비용/TTFT 폭증**, **(2) 대화·에이전트가 길어질수록 누적되는 노이즈**, **(3) 컨텍스트 안에 있어도 중간 정보가 씹히는 Lost-in-the-Middle(LITM)** 때문에 “긴 컨텍스트 = 안정적 기억”이 성립하지 않습니다. LITM은 관련 정보가 컨텍스트 **앞/뒤에 있을 때 성능이 높고, 가운데에 있을 때 크게 떨어지는 U-curve**로 관측됩니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))

그래서 2026년의 실무 해법은 **“long context를 최대한 쓰되, 그대로 쌓지 말고 compaction/summary로 SNR(signal-to-noise ratio)을 관리”**하는 쪽으로 수렴 중입니다. OpenAI는 Responses API에 **native compaction**을 넣어 “개발자가 직접 요약/상태 관리 시스템을 설계하지 않도록” 한다고 밝히고 있고, ([openai.com](https://openai.com/index/equip-responses-api-computer-environment/?utm_source=openai)) Anthropic도 Messages API에서 **compaction 전략을 베타로 제공**하며 요청 헤더/전략 설정으로 활성화하게 했습니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/compaction?e45d281a_page=1&gad_source=1&hsa_acc=4274135664&hsa_ad=546356286896&hsa_cam=14664253650&hsa_grp=126956236963&hsa_kw=data+orchestration&hsa_mt=&hsa_net=adwords&hsa_src=d&hsa_tgt=kwd-388439863644&hsa_ver=3&wtime=596s&utm_source=openai)) 또한 연구 쪽에서는 “컨텍스트 길이 자체가(심지어 perfect retrieval이어도) 성능을 떨어뜨린다”는 결과가 나오면서, ([arxiv.org](https://arxiv.org/abs/2510.05381?utm_source=openai)) 단순히 retrieval을 잘하는 것만으로는 부족하다는 경고도 명확해졌습니다.

**언제 쓰면 좋은가**
- 장시간 에이전트(코딩/운영/리서치)처럼 “대화 히스토리가 업무 상태(state)”가 되는 경우
- 긴 문서/로그/PRD/Incident timeline을 반복적으로 참조해야 하는 경우
- RAG를 쓰더라도 “회차가 누적되며 컨텍스트가 비대해지는” 워크플로우

**언제 쓰면 안 좋은가**
- 법/의료/금융처럼 **요약 손실이 곧 리스크**인 고정밀 도메인(요약은 항상 lossy)
- “요약이 곧 증거”가 되는 감사/규정 준수 기록(원문을 별도로 저장하고, 요약은 인덱스/가이드로만)
- 짧은 단발 작업(컨텍스트가 차지 않는데 compaction부터 걸면 오히려 품질 저하)

---

## 🔧 핵심 개념
### 1) Compaction의 정의: “토큰을 줄이는 것”이 아니라 “업무 상태를 재부호화하는 것”
실무에서 compaction은 보통 아래 중 하나(혹은 조합)입니다.

- **Conversation summarization compaction**: 오래된 turns를 요약으로 치환(서버/클라이언트 어디서든 가능)
- **Structured state compaction**: “요약 문장” 대신 **스키마화된 상태(결정/제약/TODO/인터페이스/키값)**로 재구성
- **External memory offload + retrieval**: 원문은 저장소로 보내고, 컨텍스트에는 “인덱스/요약+핵심 포인터”만 유지

문제는 요약이 누적될수록 정보가 증발하는 경향이 있다는 점입니다. 최근 일부 이론/분석 글들은 이걸 **rate-distortion 관점**(제한된 채널에 무엇을 보존할 것인가)으로 모델링하면서 “summarize-a-summary는 관련 정보가 기하급수적으로 줄어들 수 있다”는 논지를 강화합니다. ([tmls.nyc](https://www.tmls.nyc/research/context-compression-lower-bounds?utm_source=openai))

### 2) Lost-in-the-Middle(LITM)와 compaction의 관계
LITM은 “컨텍스트가 길면 모델이 가운데 정보를 못 본다” 수준이 아니라, **길어질수록 유효 주의(attention) 분배가 희박해지고**, 결과적으로 “중간 구간의 신호가 잡음에 묻히는 현상”으로 이해하는 게 실전에서 더 유용합니다. 고전 연구인 *Lost in the Middle*은 multi-doc QA와 key-value retrieval에서 **관련 정보 위치에 따라 성능이 크게 변동**함을 보여줍니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))

그리고 2025~2026엔 더 불편한 결과가 나왔습니다. **관련 정보를 완벽히 제공(perfect retrieval)해도 입력 길이만 증가하면 성능이 크게 하락**할 수 있다는 실험 보고가 있습니다. ([arxiv.org](https://arxiv.org/abs/2510.05381?utm_source=openai))  
즉, “RAG로 관련 chunk만 넣었으니 괜찮다”가 아니라, **컨텍스트를 짧고 밀도 있게 유지**해야 합니다.

### 3) 2026년 흐름: “모델/서빙 레벨의 compaction”과 “애플리케이션 레벨 compaction”의 분리
- **서빙/인프라 레벨**: KV-cache 병목을 줄여 긴 컨텍스트를 “돌릴 수 있게” 만드는 기술(예: paged KV 등). 다만 이건 비용/서빙 효율 문제를 푸는 것이지, LITM을 직접 해결하진 않습니다. (예: llama.cpp에서도 paged KV 논의가 활발) ([github.com](https://github.com/ggml-org/llama.cpp/discussions/21961?utm_source=openai))
- **애플리케이션 레벨**: 무엇을 남기고 무엇을 버릴지(업무 의미론) 결정하는 compaction. 여기서 LITM 방지(앞/뒤에 앵커 배치, 구조화 상태 유지)가 핵심입니다.
- **모델 내부 레벨(KV compaction)**: 2026년엔 KV cache 자체를 “압축/compaction”하는 연구도 나오고 있습니다(예: Still: single forward pass로 amortized KV cache compaction). ([arxiv.org](https://arxiv.org/abs/2606.07878?utm_source=openai))  
  이 축은 “토큰을 줄이는 요약”과는 다르게, **모델이 보는 내부 메모리 표현을 줄여 장기 지평을 늘리는** 계열입니다.

---

## 💻 실전 코드
아래는 “긴 컨텍스트 채팅/에이전트”에서 흔한 실패(히스토리 누적 → 비용 증가 + LITM + 제약 유실)를 막기 위한 **현실적인 compaction 파이프라인** 예시입니다.

핵심 아이디어:
1) 대화 로그는 원문 그대로 저장(감사/재현/디버깅용)
2) 모델에 넣는 컨텍스트는 **(a) 고정 Anchor(규칙/제약/목표)** + **(b) 작업 상태(state)** + **(c) 최근 turns**로 제한
3) 임계치에 도달하면 “free-form 요약”이 아니라 **스키마 기반 state 업데이트**로 compact (요약의 누적 손실을 줄임)

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate
pip install openai tiktoken pydantic
export OPENAI_API_KEY="..."
```

### 1) 상태 스키마 + 토큰 예산 기반 compaction
```python
from __future__ import annotations

import json
import os
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

from openai import OpenAI
import tiktoken

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ---- 1) "요약" 대신 남길 업무 상태를 구조화한다 ----
class WorkState(BaseModel):
    goal: str
    hard_constraints: List[str] = Field(default_factory=list)   # 절대 깨면 안 되는 규칙/제약
    decisions: List[str] = Field(default_factory=list)          # 이미 합의된 결정
    open_questions: List[str] = Field(default_factory=list)     # 아직 미해결
    next_actions: List[str] = Field(default_factory=list)       # 다음 할 일(짧고 명령형)
    key_artifacts: Dict[str, str] = Field(default_factory=dict) # 파일/링크/티켓/커밋 등 포인터

class Memory(BaseModel):
    anchor: WorkState
    recent_messages: List[Dict[str, str]] = Field(default_factory=list)  # role/content
    raw_log_path: str = "raw_log.jsonl"

# ---- 2) 토큰 카운팅(대략) ----
enc = tiktoken.get_encoding("o200k_base")

def approx_tokens(messages: List[Dict[str, str]]) -> int:
    # 모델별 정확 카운터가 있으면 그걸 쓰는 게 더 좋다.
    return sum(len(enc.encode(m["content"])) + 8 for m in messages)

def render_prompt(mem: Memory) -> List[Dict[str, str]]:
    anchor_block = {
        "role": "system",
        "content": (
            "You are a senior engineer assistant.\n"
            "Use the following WORK_STATE as the source of truth.\n"
            "If something is missing, ask a question instead of guessing.\n\n"
            f"WORK_STATE(JSON):\n{mem.anchor.model_dump_json(indent=2)}\n"
        )
    }
    return [anchor_block] + mem.recent_messages

def append_raw(mem: Memory, role: str, content: str) -> None:
    with open(mem.raw_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"role": role, "content": content}, ensure_ascii=False) + "\n")

def compact_if_needed(mem: Memory, max_input_tokens: int = 12000, keep_last_n: int = 10) -> None:
    """
    - recent_messages가 너무 길어지면, 오래된 메시지를 "요약"하지 말고
      anchor(WorkState)를 업데이트하는 방식으로 compaction 한다.
    - 그리고 recent_messages는 최근 N개만 남긴다.
    """
    messages = render_prompt(mem)
    if approx_tokens(messages) <= max_input_tokens:
        return

    # compaction 대상(최근 N개를 제외한 과거 turns)
    old = mem.recent_messages[:-keep_last_n]
    if not old:
        return

    # 모델에게 "스키마 업데이트"를 요구: summarize-a-summary를 피하고,
    # anchor를 누적 갱신(append/merge)하게 만든다.
    compaction_prompt = [
        {
            "role": "system",
            "content": (
                "You update WORK_STATE. Do NOT write a narrative summary.\n"
                "Return ONLY valid JSON that matches the WorkState schema.\n"
                "Rules:\n"
                "- Preserve hard constraints verbatim if present.\n"
                "- Convert long discussion into decisions/open_questions/next_actions.\n"
                "- Add pointers to key artifacts.\n"
            )
        },
        {
            "role": "user",
            "content": (
                "Current WORK_STATE:\n"
                f"{mem.anchor.model_dump_json(indent=2)}\n\n"
                "Conversation turns to compact:\n"
                f"{json.dumps(old, ensure_ascii=False, indent=2)}\n\n"
                "Return the updated WorkState JSON:"
            )
        }
    ]

    resp = client.responses.create(
        model="gpt-5-mini",  # 예시. 조직 표준 모델로 교체
        input=compaction_prompt,
        temperature=0.2,
    )

    updated_json = resp.output_text.strip()
    mem.anchor = WorkState.model_validate_json(updated_json)

    # recent는 tail만 남기고, 나머지는 "anchor에 흡수"됐다고 간주
    mem.recent_messages = mem.recent_messages[-keep_last_n:]

# ---- 3) 실제 에이전트 루프(예: 운영 이슈 대응) ----
def ask(mem: Memory, user_text: str) -> str:
    append_raw(mem, "user", user_text)
    mem.recent_messages.append({"role": "user", "content": user_text})

    compact_if_needed(mem)

    resp = client.responses.create(
        model="gpt-5-mini",
        input=render_prompt(mem),
        temperature=0.2,
    )
    answer = resp.output_text

    append_raw(mem, "assistant", answer)
    mem.recent_messages.append({"role": "assistant", "content": answer})

    return answer

if __name__ == "__main__":
    mem = Memory(
        anchor=WorkState(
            goal="서비스 장애(5xx 급증) 원인 파악 및 30분 내 완화, 24시간 내 근본 해결책 도출",
            hard_constraints=[
                "절대 프로덕션 DB에 write-heavy 쿼리/마이그레이션을 실행하지 않는다.",
                "PII 로그는 외부로 반출하지 않는다.",
            ],
            key_artifacts={
                "runbook": "internal://runbooks/api-5xx",
                "dashboard": "internal://grafana/api-latency",
            }
        )
    )

    print(ask(mem, "지난 2시간 동안 /checkout 5xx가 3배 증가했어. 우선 완화책부터 제안해줘."))
    print(ask(mem, "최근 배포는 40분 전, 결제 모듈의 timeout 설정 변경이 있었어. 다음으로 확인할 포인트?"))
```

### 예상 출력(형태)
- 초기에는 일반 답변이 나오다가, 입력 토큰이 예산을 넘으면 `compact_if_needed()`가 동작해
  - `hard_constraints`는 유지
  - “결론/결정/다음 액션”이 `WorkState`에 축적
  - `recent_messages`는 최근 N개만 유지

이 패턴의 장점은 **LITM을 줄이기 위해 중요한 상태를 항상 컨텍스트 맨 앞(system anchor)에 고정**한다는 점입니다. “긴 대화 중간에 묻힌 제약/결정”이 모델에게 다시 잘 보이게 됩니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Anchor를 ‘앞’에 고정하고, 업데이트는 append/merge로만**
- LITM U-curve 특성상 “중간에 있는 정보”는 신뢰하기 어렵습니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))  
- 따라서 “현재 상태(규칙/결정/인터페이스/중요 키값)”는 항상 system 또는 첫 블록에 두고, compaction은 그 블록을 갱신하는 방식이 안정적입니다.

2) **free-form summary 대신 ‘스키마 기반 상태’로 compact**
- summarize-a-summary 누적은 품질이 서서히 무너집니다(특히 장기 에이전트). ([tmls.nyc](https://www.tmls.nyc/research/context-compression-lower-bounds?utm_source=openai))  
- `decisions/open_questions/next_actions`처럼 “업무에 필요한 최소 충분 통계량(sufficient state)”을 정의해 두면, 요약 손실을 관리할 수 있습니다.

3) **원문은 밖에 저장하고, 컨텍스트에는 포인터만**
- “길이 자체가 성능을 해친다”는 결과를 감안하면 ([arxiv.org](https://arxiv.org/abs/2510.05381?utm_source=openai)), 원문을 계속 넣어두는 건 손해입니다.
- 원문은 object storage + 검색(RAG)로 두고, 컨텍스트에는 “무엇을 어디서 다시 꺼낼지”만 남기는 게 비용/품질 모두 유리합니다.

### 흔한 함정/안티패턴
- **(안티패턴) 임계치마다 ‘전체 대화 요약 1개’로 치환**
  - 겉보기엔 깔끔하지만, 실제로는 “중요한 제약/보안 규칙/예외 케이스”가 빠지기 쉽습니다.
- **(안티패턴) compaction 결과를 검증 없이 진실로 취급**
  - compaction은 생성(generation)입니다. 반드시 “누락/왜곡 가능성”을 전제로 하고, 중요 항목은 구조화/검증(예: key 목록, 테스트, 체크리스트)으로 방어하세요.
- **(안티패턴) 긴 컨텍스트를 ‘저장소’로 사용**
  - 컨텍스트는 DB가 아닙니다. 길어질수록 모델이 잘 못 쓰는 경향(LITM)도 있고 ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai)), 길이 자체가 성능을 떨어뜨릴 수도 있습니다. ([arxiv.org](https://arxiv.org/abs/2510.05381?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **별도 요약 호출(compaction call)**: 품질은 통제하기 쉽지만 호출 비용/지연이 추가
- **provider-native compaction(OpenAI/Anthropic 등)**: 운영은 편하지만 “어떤 포맷으로 무엇을 보존하는지”를 100% 통제하기 어려움  
  - OpenAI는 Responses API에 native compaction을 넣어 개발자 부담을 줄인다고 설명합니다. ([openai.com](https://openai.com/index/equip-responses-api-computer-environment/?utm_source=openai))  
  - Anthropic은 API에서 compaction 전략을 활성화하는 문서를 제공합니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/compaction?e45d281a_page=1&gad_source=1&hsa_acc=4274135664&hsa_ad=546356286896&hsa_cam=14664253650&hsa_grp=126956236963&hsa_kw=data+orchestration&hsa_mt=&hsa_net=adwords&hsa_src=d&hsa_tgt=kwd-388439863644&hsa_ver=3&wtime=596s&utm_source=openai))
- **KV-level compaction(Still 등)**: 장기 지평에서 매력적이지만, 앱 관점의 “업무 의미론(무엇이 중요한가)”을 자동으로 해결하진 않음. ([arxiv.org](https://arxiv.org/abs/2606.07878?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 8월의 long context 활용은 “창이 커졌으니 다 넣자”가 아니라:

- **길이 자체가 성능을 해칠 수 있고** ([arxiv.org](https://arxiv.org/abs/2510.05381?utm_source=openai))
- **중간 정보는 더 잘 잃어버리며(LITM)** ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))
- 그래서 **compaction은 선택이 아니라 운영 기법**이 되었습니다.

도입 판단 기준:
- 대화/에이전트가 30분~수시간 이상 이어지고, “이전 결정/제약”이 반복적으로 중요하다 → **스키마 기반 compaction + anchor 고정** 추천
- 문서가 길고 재참조가 잦다 → 원문은 외부 저장 + RAG, 컨텍스트에는 **상태+포인터만**
- “요약이 틀리면 큰 사고” → compaction은 최소화하고, **원문 인용/검증 루프**를 설계

다음 학습 추천(읽을 거리):
- LITM의 정석: *Lost in the Middle* ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))
- “retrieval이 완벽해도 길면 망가진다”: *Context Length Alone Hurts…* ([arxiv.org](https://arxiv.org/abs/2510.05381?utm_source=openai))
- 프로바이더 네이티브 compaction: OpenAI Responses API 소개 ([openai.com](https://openai.com/index/equip-responses-api-computer-environment/?utm_source=openai)), Anthropic compaction 문서 ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/compaction?e45d281a_page=1&gad_source=1&hsa_acc=4274135664&hsa_ad=546356286896&hsa_cam=14664253650&hsa_grp=126956236963&hsa_kw=data+orchestration&hsa_mt=&hsa_net=adwords&hsa_src=d&hsa_tgt=kwd-388439863644&hsa_ver=3&wtime=596s&utm_source=openai))
- KV-level 연구 방향: Still (amortized KV cache compaction) ([arxiv.org](https://arxiv.org/abs/2606.07878?utm_source=openai))

원하시면, 위 코드 예제를 **(1) RAG 인덱스(예: Postgres+pgvector)와 결합**, **(2) compaction 결과에 대한 자동 검증(“hard_constraints 누락 감지”, “결정/액션 중복 제거”)**, **(3) 팀 개발용 handoff 문서 자동 생성**까지 확장한 버전으로도 정리해드릴게요.