---
title: "컨텍스트 윈도우가 길어질수록 더 위험해진다: 2026년형 LLM Long Context Compaction/Summary 설계 가이드"
date: 2026-07-15 03:14:35 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-07]
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
LLM long context window(200K~1M+ tokens)가 “문서를 통째로 넣고 끝”을 가능하게 만든 건 맞습니다. 하지만 2026년 현재 실무에서 더 자주 겪는 문제는 따로 있습니다.

- **비용 폭증**: 대화/에이전트가 길어질수록 매 턴마다 “지금까지 전부”를 다시 보내고 다시 추론하며 과금됩니다. 그래서 **prompt caching**과 **compaction**이 사실상 필수가 됐습니다. ([redis.io](https://redis.io/blog/context-compaction/?utm_source=openai))  
- **성능 붕괴(quality rot)**: 컨텍스트가 길어질수록 모델이 “가운데(mid)” 증거를 못 쓰는 **lost-in-the-middle** U-shape가 실전에서도 계속 터집니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))  
- **정보 보존 실패**: 요약은 토큰을 줄이지만, “원문이 갖고 있던 약속/제약(semantic commitments)”이 깨지면 다음 턴부터는 조용히 잘못된 방향으로 갑니다. 2026년엔 이를 **검증 가능한 압축** 문제로 다루려는 연구가 나오기 시작했습니다. ([arxiv.org](https://arxiv.org/abs/2605.17304?utm_source=openai))  

### 언제 쓰면 좋나
- 멀티턴 에이전트/코딩 어시스턴트/툴 호출이 반복되는 **long-running session**
- 컨텍스트에 “로그/툴 출력/스크린샷”이 쌓여 **입력 토큰이 기하급수적으로 커지는** 워크로드 ([claude.com](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude?utm_source=openai))  
- 동일한 prefix(시스템 프롬프트+정적 컨텍스트)를 반복 사용하는 구조로 **캐시 이득**을 볼 수 있을 때 ([code.claude.com](https://code.claude.com/docs/en/prompt-caching?utm_source=openai))  

### 언제 쓰면 안 되나(또는 제한적으로)
- **디버깅/포렌식**: stack trace, exact error string, diff 등 “정확히 그 문자열”이 중요한 작업은 요약이 치명적일 수 있습니다(요약은 필연적으로 손실). ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1u11qkx/how_i_stopped_context_window_bloat_in_continuous/?utm_source=openai))  
- 법/의료/금융처럼 “요약의 오해석”이 리스크인 도메인(요약은 보조로만, 원문 링크/근거 유지 필수)
- 단발성 Q&A처럼 컨텍스트가 짧고 캐시 재사용이 적은 경우(복잡한 compaction 파이프라인이 오히려 비용)

---

## 🔧 핵심 개념
이 글에서 말하는 “long context compaction”은 단순 요약이 아닙니다. 핵심은 **(1) 토큰을 줄이되 (2) 다음 추론에 필요한 약속을 보존하고 (3) lost-in-the-middle을 구조적으로 피하는 것**입니다.

### 1) 개념 정의
- **Context window**: 모델이 한 번의 추론에서 볼 수 있는 토큰 한도.
- **Compaction**: 오래된 히스토리를 “요약/압축된 representation”으로 바꿔 새 컨텍스트를 재구성하는 작업. Claude API/도구 생태계에서도 “컨텍스트 한도 근처에서 이전 내용을 요약 블록으로 치환”하는 방식으로 정의됩니다. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/compaction?e45d281a_page=1&gad_source=1&hsa_acc=4274135664&hsa_ad=546356286896&hsa_cam=14664253650&hsa_grp=126956236963&hsa_kw=data+orchestration&hsa_mt=&hsa_net=adwords&hsa_src=d&hsa_tgt=kwd-388439863644&hsa_ver=3&wtime=596s&utm_source=openai))  
- **Prompt caching**: 자주 재사용되는 prefix(시스템 프롬프트, 큰 문서 컨텍스트 등)를 캐시에 올려 **반복 비용/지연을 줄이는** 메커니즘. Bedrock는 1시간 TTL 캐시도 지원하면서 장시간 세션의 경제성을 키웠습니다. ([aws.amazon.com](https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-bedrock-one-hour-duration-prompt-caching/?utm_source=openai))  
- **Lost in the middle**: 중요한 정보가 긴 입력의 중간에 있을 때 성능이 떨어지는 현상(U-shape). ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))  

### 2) 내부 작동 방식(현실적인 파이프라인)
실무에서 compaction을 “한 번 요약”으로 끝내면 거의 망합니다. 안정적인 구조는 보통 아래 형태입니다.

1) **계측(telemetry)**  
   - 현재 컨텍스트 토큰 수, “툴 출력 토큰 비중”, 캐시 hit 여부(또는 TTL 만료), compaction 발생 횟수/간격을 기록  
   - 목표는 “요약을 잘 쓰는 것”이 아니라 **요약이 필요 없는 구간을 먼저 줄이는 것**(툴 출력, 중복 로그 제거)

2) **분류 & 우선순위화**  
   - (A) **Commitments**: 변하면 안 되는 계약/결정/요구사항/제약/버전/환경  
   - (B) **State**: 현재 진행 상황(어디까지 구현했고 무엇이 실패했는지)  
   - (C) **Evidence**: 근거(로그/링크/코드 diff) — 단, 전부를 유지할 수 없으니 “참조 포인터”로 남기기  
   - (D) **Chatter**: 품질에 영향 없는 대화/중복 설명

3) **다층 압축(rolling buffer + anchored summary)**  
   - 요약을 “한 덩어리”로 만들면 lost-in-the-middle 위험이 커집니다.  
   - 최신 상호작용은 raw로 유지하고, 오래된 건 구조화된 메모리로 바꾸는 **cache-aware rolling buffer + compaction** 조합이 권장됩니다. ([claude.com](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude?utm_source=openai))  

4) **검증(최소한의 self-check)**  
   - 2026년 연구 흐름은 “압축 후에도 어떤 의미적 약속이 보존돼야 하는가”를 명시하고 측정하려는 방향입니다. ([arxiv.org](https://arxiv.org/abs/2605.17304?utm_source=openai))  
   - 실무적 타협안: “요약본에서 commitments가 빠졌는지”를 룰 기반으로 검사하거나, 작은 모델로 diff-check를 돌립니다.

### 3) 다른 접근과의 차이점
- **Retrieval(RAG)**: “필요할 때만 가져오기”. 장점은 손실이 적고 확장성이 좋지만, 대화/에이전트의 “진행 상태(state)”를 매번 재구성해야 하고, 검색 실패가 곧 실패입니다.
- **Summarization/Compaction**: “항상 들고 다닐 최소 상태”를 만든다. 장점은 에이전트가 지속적으로 이어가기 쉽지만, 손실/드리프트가 누적됩니다. ([redis.io](https://redis.io/blog/context-compaction/?utm_source=openai))  
- **Prompt compression(LLMLingua 계열)**: 요약이 아니라 **토큰 제거/선택 기반 압축**으로 “그대로의 문장 조각”을 남기는 쪽에 가깝습니다. 지연/비용 측면에서 실측 연구도 나왔고(조건 맞으면 E2E 속도 이득), RAG 컨텍스트 압축에 특히 유용합니다. ([arxiv.org](https://arxiv.org/abs/2604.02985?utm_source=openai))  

---

## 💻 실전 코드
요구사항: “장시간 코딩 에이전트 세션”에서 (1) 툴 출력이 길어지고 (2) lost-in-the-middle로 중요한 결정이 중간에 묻히며 (3) 비용이 폭증하는 상황을 가정합니다.

아래 예제는 **서버 사이드 메모리 레이어**를 만들어:
- 최근 N턴은 raw로 유지
- 오래된 히스토리는 **Commitments/State/Artifacts**로 구조화 요약(compaction)
- 툴 출력은 **LLMLingua-2**로 토큰 단위 압축(요약보다 “원문 조각”을 남김)
- 다음 요청 프롬프트는 “앵커(요약) + 최신 raw + 필요한 아티팩트 포인터”로 구성

### 1) 초기 셋업
```bash
python -m venv .venv
source .venv/bin/activate

pip install anthropic llmlingua transformers torch tiktoken
# llmlingua-2는 HF 모델을 받아오므로 최초 실행 시 다운로드 시간이 듭니다.
```

### 2) 메모리/컴팩션 파이프라인 (Python)
```python
# file: context_compaction_pipeline.py
from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

import tiktoken
from anthropic import Anthropic

from llmlingua import PromptCompressor

ENC = tiktoken.get_encoding("cl100k_base")


@dataclass
class Turn:
    role: str  # "user" | "assistant" | "tool"
    content: str
    ts: float


@dataclass
class CompactedMemory:
    commitments: List[str]       # 반드시 보존되어야 하는 결정/제약
    state: List[str]             # 현재 진행 상태/다음 액션
    artifacts: List[Dict[str, str]]  # {name, pointer, note}
    open_questions: List[str]
    last_updated_ts: float


def count_tokens(text: str) -> int:
    return len(ENC.encode(text))


class ContextManager:
    """
    - recent_raw_turns: 최신 대화는 그대로 유지(디버깅/정확성)
    - compacted: 오래된 히스토리에서 추출한 구조화 메모리(앵커)
    - tool_output_compression: tool 출력은 요약이 아니라 token-selection 압축(LLMLingua-2)
    """
    def __init__(
        self,
        model: str,
        max_context_tokens: int = 200_000,
        compact_trigger_ratio: float = 0.80,
        recent_raw_turns: int = 10,
    ):
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model

        self.max_context_tokens = max_context_tokens
        self.compact_trigger_tokens = int(max_context_tokens * compact_trigger_ratio)
        self.recent_raw_turns = recent_raw_turns

        self.turns: List[Turn] = []
        self.compacted: Optional[CompactedMemory] = None

        # LLMLingua-2 (token classification 기반)
        self.compressor = PromptCompressor(
            model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
            use_llmlingua2=True,
        )

    def add_turn(self, role: str, content: str):
        self.turns.append(Turn(role=role, content=content, ts=time.time()))

    def _compress_tool_output(self, text: str, ratio: float = 0.25) -> str:
        """
        긴 tool output을 요약해버리면 디버깅 근거가 사라집니다.
        그래서 '중요 토큰/구문을 남기는 압축'을 먼저 시도합니다.
        """
        if count_tokens(text) < 2500:
            return text

        compressed = self.compressor.compress_prompt(
            context=[text],
            instruction="Keep exact identifiers, file paths, error strings, and line numbers.",
            question="We will use this output later to debug and decide next steps.",
            ratio=ratio,
        )
        return compressed["compressed_prompt"]

    def build_prompt(self) -> str:
        """
        lost-in-the-middle 완화를 위해:
        - 앵커 메모리(Commitments/State)를 프롬프트 '앞'에 둠 (primacy)
        - 최신 raw turns를 '끝'에 둠 (recency)
        """
        parts: List[str] = []

        if self.compacted:
            parts.append("=== COMPACTED MEMORY (ANCHOR) ===")
            parts.append("## Commitments (must not change)")
            parts.extend([f"- {c}" for c in self.compacted.commitments])

            parts.append("\n## Current State")
            parts.extend([f"- {s}" for s in self.compacted.state])

            parts.append("\n## Artifacts (pointers)")
            for a in self.compacted.artifacts:
                parts.append(f"- {a['name']}: {a['pointer']} ({a.get('note','')})")

            if self.compacted.open_questions:
                parts.append("\n## Open Questions")
                parts.extend([f"- {q}" for q in self.compacted.open_questions])

            parts.append("=== END MEMORY ===\n")

        # 최근 N턴은 raw로 유지
        recent = self.turns[-self.recent_raw_turns :]
        parts.append("=== RECENT RAW TURNS ===")
        for t in recent:
            content = t.content
            if t.role == "tool":
                content = self._compress_tool_output(content)
                parts.append(f"[tool]\n{content}\n")
            else:
                parts.append(f"[{t.role}]\n{content}\n")
        parts.append("=== END RAW ===")

        prompt = "\n".join(parts)
        return prompt

    def maybe_compact(self):
        """
        컨텍스트가 임계치에 다가가면 오래된 turns를 구조화 요약으로 치환.
        Claude의 compaction 기능도 이런 목적(효과적 컨텍스트 연장)으로 제공됨. ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/compaction?e45d281a_page=1&gad_source=1&hsa_acc=4274135664&hsa_ad=546356286896&hsa_cam=14664253650&hsa_grp=126956236963&hsa_kw=data+orchestration&hsa_mt=&hsa_net=adwords&hsa_src=d&hsa_tgt=kwd-388439863644&hsa_ver=3&wtime=596s&utm_source=openai))
        """
        prompt = self.build_prompt()
        tokens = count_tokens(prompt)

        if tokens < self.compact_trigger_tokens:
            return

        # 오래된 turns를 대상으로(최근 N턴 제외) compaction 수행
        old = self.turns[:-self.recent_raw_turns]
        if not old:
            return

        old_text = "\n".join([f"[{t.role}] {t.content}" for t in old])[:200_000]

        system = (
            "You are a senior software engineer. "
            "Create a STRUCTURED memory that preserves commitments and debugging-critical facts. "
            "Do not invent. If unsure, mark as unknown."
        )

        user = f"""
We need to compact a long-running agent session.

Return JSON with fields:
- commitments: string[]
- state: string[]
- artifacts: array of {{name, pointer, note}}
- open_questions: string[]

Rules:
- commitments must include: versions, API contracts, decisions, non-negotiable constraints
- state must include: what is implemented, what failed, next concrete steps
- artifacts must store pointers instead of copying huge blobs (e.g., "logs/step42.txt", "diff:commit:abcd")
- Preserve exact error strings if present
- Avoid general prose

Conversation to compact:
{old_text}
"""

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1200,
            system=system,
            messages=[{"role": "user", "content": user}],
            # Claude compaction은 beta header로 노출되기도 함(제품/SDK에 따라 다름). ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/compaction?e45d281a_page=1&gad_source=1&hsa_acc=4274135664&hsa_ad=546356286896&hsa_cam=14664253650&hsa_grp=126956236963&hsa_kw=data+orchestration&hsa_mt=&hsa_net=adwords&hsa_src=d&hsa_tgt=kwd-388439863644&hsa_ver=3&wtime=596s&utm_source=openai))
            extra_headers={"anthropic-beta": "compact-2026-01-12"},
        )

        raw = resp.content[0].text
        data = json.loads(raw)

        self.compacted = CompactedMemory(
            commitments=data.get("commitments", []),
            state=data.get("state", []),
            artifacts=data.get("artifacts", []),
            open_questions=data.get("open_questions", []),
            last_updated_ts=time.time(),
        )

        # old turns 제거(요약으로 대체)
        self.turns = self.turns[-self.recent_raw_turns :]

    def call_agent(self, task: str) -> str:
        self.add_turn("user", task)
        self.maybe_compact()

        prompt = self.build_prompt()
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            system="You are an engineering agent. Use the memory anchor and recent turns.",
            messages=[{"role": "user", "content": prompt}],
        )
        out = resp.content[0].text
        self.add_turn("assistant", out)
        return out


if __name__ == "__main__":
    cm = ContextManager(model="claude-sonnet-4.5")  # 예시
    cm.add_turn("tool", "git diff ... (very long output) ...")
    cm.add_turn("assistant", "We should refactor the caching layer...")
    answer = cm.call_agent("Now implement the cache TTL config and add tests.")
    print(answer)
```

### 예상 출력(형태)
- compaction 트리거 전: 최근 raw turns + (없으면) memory anchor 없음
- 트리거 후: 프롬프트 상단에 `COMPACTED MEMORY(ANCHOR)` JSON에서 추출된 commitments/state가 고정되고, 최신 raw turns만 뒤에 붙습니다. 이 배치는 **중간에 묻히는 정보**를 줄이려는 의도입니다(primacy/recency).

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **요약을 “문장”이 아니라 “데이터 구조”로 만들기**  
   Commitments/State/Artifacts처럼 스키마를 강제하면, 나중에 “무엇이 보존돼야 하는지”가 명확해집니다. 2026년엔 이를 더 엄밀히 다루려는 프레임워크도 나옵니다. ([arxiv.org](https://arxiv.org/abs/2605.17304?utm_source=openai))  

2) **Compaction + Prompt caching을 같이 설계하기**  
   캐시는 prefix를 재사용할 때 비용/지연이 줄어듭니다. 하지만 세션이 길어지면 “재전송 토큰” 자체가 커져 캐시 이득이 흔들릴 수 있어 compaction이 보완재가 됩니다. ([claude.com](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude?utm_source=openai))  

3) **툴 출력은 ‘요약’보다 ‘압축(선택)’을 우선**  
   요약은 디버깅 근거를 지우기 쉽습니다. LLMLingua류처럼 토큰 선택 기반 압축은 “정확 문자열”을 남길 여지가 큽니다. 또한 2026년 실측 연구에서도 조건이 맞으면 지연/비용 이득이 보고됩니다. ([arxiv.org](https://arxiv.org/abs/2604.02985?utm_source=openai))  

### 흔한 함정/안티패턴
- **“한 번의 거대 요약”으로 모든 걸 해결하려는 시도**  
  요약이 누적되면 드리프트가 생깁니다. 특히 긴 컨텍스트에서 성능이 광고만큼 안 나온다는 지적(“context rot”)도 나와서, “윈도우가 크니 괜찮다”는 믿음이 위험합니다. ([tmls.nyc](https://www.tmls.nyc/research/context-rot-mechanistic?utm_source=openai))  

- **lost-in-the-middle을 무시한 프롬프트 배치**  
  중요한 제약/결정을 길고 복잡한 로그 중간에 섞어두면, 모델은 끝/처음에 있는 정보보다 덜 쓰는 경향이 있습니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))  
  실무 처방은 단순합니다: **(1) commitments는 앞에 고정(앵커), (2) 최근 turn은 뒤에 유지**.

- **Compaction을 너무 자주 트리거**  
  요약 자체도 비용/시간이 듭니다(Claude Code 문서도 compaction 시간의 상당 부분이 요약 생성이라고 언급). ([code.claude.com](https://code.claude.com/docs/en/prompt-caching?utm_source=openai))  
  “85%에서 compact” 같은 고정 룰도 있지만, 워크로드별로 다릅니다. ([langchain.com](https://www.langchain.com/blog/autonomous-context-compression?utm_source=openai))  

### 비용/성능/안정성 트레이드오프(의사결정 기준)
- 비용이 최우선이면: **툴 출력/문서 컨텍스트 압축(LLMLingua류) + 캐시 TTL 최적화**부터  
- 안정성이 최우선이면: compaction을 최소화하고 **Artifacts 포인터 + 원문 저장소**(로그 파일, diff, 링크)를 강제
- 에이전트 지속성이 최우선이면: **구조화 compaction(Commitments/State)**을 도입하되, “검증 체크(누락/충돌 검사)”를 반드시 넣기

---

## 🚀 마무리
2026년 7월 기준 long context는 “많이 넣을 수 있다”가 아니라, **어떻게 줄일지(Compaction/Compression)까지 포함한 context engineering**이 성패를 가릅니다.  
프로젝트 도입 판단 기준은 간단히 세 가지로 보세요.

1) 세션이 길어지며 **토큰/비용이 선형이 아니라 가속**되는가? → compaction/caching 우선순위 높음 ([redis.io](https://redis.io/blog/context-compaction/?utm_source=openai))  
2) 중간에 있는 결정/근거를 자주 놓치는가? → lost-in-the-middle 대응(앵커/배치/구조화)이 필요 ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))  
3) “정확 문자열”이 중요한 디버깅 비중이 큰가? → 요약보다 압축(선택) + 아티팩트 포인터 전략 ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1u11qkx/how_i_stopped_context_window_bloat_in_continuous/?utm_source=openai))  

다음 학습으로는:
- lost-in-the-middle 원 논문(실험 세팅/한계 이해) ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))  
- Claude의 compaction/prompt caching 운영 관점 문서(실제 제품 제약/경제성) ([platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/compaction?e45d281a_page=1&gad_source=1&hsa_acc=4274135664&hsa_ad=546356286896&hsa_cam=14664253650&hsa_grp=126956236963&hsa_kw=data+orchestration&hsa_mt=&hsa_net=adwords&hsa_src=d&hsa_tgt=kwd-388439863644&hsa_ver=3&wtime=596s&utm_source=openai))  
- “압축이 약속을 깨지 않는지”를 다루는 최신 형식화 연구(검증 관점) ([arxiv.org](https://arxiv.org/abs/2605.17304?utm_source=openai))  

원하시면, 위 코드에 **(a) 토큰 계측/대시보드 로그**, **(b) commitments 누락 검출용 unit test**, **(c) RAG 결합(Artifacts 포인터를 실제 검색으로 resolve)**까지 붙여서 “프로덕션형 템플릿”으로 확장해드릴게요.