---
title: "합성 데이터(Synthetic Data)로 LLM 파인튜닝을 “공급망”처럼 굴리는 법 — 2026년 6월 기준 실전 파이프라인"
date: 2026-06-23 04:09:39 +0900
categories: [AI, Data]
tags: [ai, data, trend, 2026-06]
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
LLM 파인튜닝에서 **가장 비싼 비용**은 GPU가 아니라 “좋은 데이터”입니다. 특히 (1) 로그/대화가 민감정보를 포함하거나, (2) 케이스 커버리지가 부족하거나, (3) 레이블링 인력이 없거나, (4) 평가 기준이 애매한 도메인(고객지원, 정책 준수, 보안, 의료/법률 등)에서는 **합성 데이터 생성(SDG, Synthetic Data Generation)** 이 사실상 유일한 확장 전략이 됩니다. NVIDIA는 Nemotron-4 340B의 SFT/Preference 파인튜닝 데이터 상당 부분을 합성으로 만들었다는 점을 문서에 명시했고, 이를 재현하는 파이프라인을 NeMo Curator로 제공하고 있습니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/25.02/datacuration/syntheticdata.html?utm_source=openai))

다만 “언제 쓰면 안 되나?”도 명확합니다.

- 쓰면 좋은 경우
  - **요구 행동이 명확**(정책/형식/톤/절차/툴 사용)하고, 골든 데이터가 희소한 경우
  - **긴 꼬리(long-tail) 케이스**를 의도적으로 커버해야 하는 경우(에러 핸들링, 엣지 케이스, 안전/보안)
  - **Preference/DPO용 pair 데이터**(A vs B)를 대량으로 만들어야 하는 경우(사람 라벨링 없이 RLAIF로 근사)
- 쓰면 안 되는 경우
  - 실제 분포(Real-world distribution)가 중요한데 **생성 모델이 그 분포를 모를 때**(환각/편향이 그대로 학습됨)
  - 합성 데이터가 “정답”을 결정해버리는 문제(예: 사실성/지식 업데이트). 이건 **RAG/툴 기반**으로 해결해야지 SDG로 때우면 악화됩니다.
  - 모델이 스스로 만든 데이터를 다시 먹는 **self-training 루프**를 검증 없이 돌릴 때(모드 붕괴/편향 고착)

핵심은 합성 데이터를 “컨텐츠 생성”이 아니라 **데이터 엔지니어링(생성→필터→라벨→평가→재생성)의 폐루프**로 다루는 겁니다. NeMo Curator도 SDG를 단독 기능이 아니라 “큐레이션 파이프라인 일부”로 설계합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/latest/curate-text/generate-data/index.html?utm_source=openai))

---

## 🔧 핵심 개념
### 1) LLM 합성 데이터 생성의 3가지 역할
실무에서 SDG는 보통 아래 셋 중 하나(혹은 조합)로 씁니다.

1. **Instruction/SFT 데이터 확장**  
   - (입력, 출력) 형태의 데모를 늘려서 “행동”을 학습
2. **Preference 데이터(DPO/RLAIF) 생성**  
   - 같은 입력에 대해 후보 응답을 여러 개 만들고, “무엇이 더 낫나”를 비교 데이터로 만듦  
   - Anthropic의 Constitutional AI 계열은 “원칙(Constitution) → critique/revision → AI가 선호 비교” 같은 구조로 RLAIF를 활용하는 접근을 제시했습니다. ([arxiv.org](https://arxiv.org/abs/2212.08073?utm_source=openai))
3. **Adversarial/Red-team 데이터 생성**  
   - 안전/보안/정책 위반 케이스를 의도적으로 만들어 방어학습(단, 리스크가 큼)

### 2) 내부 작동 방식: “생성 파이프라인”은 ETL + 심사 + 재생성
2026년 기준, 잘 되는 팀들의 SDG는 대체로 다음 흐름입니다.

1. **Spec 정의(요구사항을 데이터로 표현)**  
   - “좋은 답”의 규격: 포맷, 금지어, 정책 준수, 근거 제시 방식, tool-call 규약 등  
2. **Coverage Plan(케이스 설계)**  
   - 매크로 토픽 → 서브토픽 → 난이도/에러 조건 → 도메인 제약  
   - NeMo 문서에서도 토픽 중복을 제거하지 않으면 비용이 낭비된다고 경고합니다(중복 주제는 곧 중복 호출). ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/25.07/datacuration/syntheticdata.html?utm_source=openai))
3. **Generation(다양성 제어)**  
   - temperature/top_p, 시스템 프롬프트, 다중 샘플링(n-best)로 다양성 확보
4. **Filtering/Scoring(품질 게이트)**  
   - 규칙 기반(정규식/스키마), 분류기, LLM judge(자기평가 포함), 중복 제거
5. **Labeling(정답/선호/메타데이터)**  
   - SFT면 정답 텍스트 + 메타(토픽, 난이도, policy tags)  
   - DPO면 (chosen, rejected) 쌍 + 비교 기준
6. **Eval & Iterate(오프라인 평가 + 재생성)**  
   - 실패 케이스를 다시 SDG의 seed로 넣어 “데이터가 모델을 고치는” 루프를 만듦

이걸 수작업으로 짜면 금방 파이프라인이 망가지는데, NeMo Curator는 SDG를 “대량 프롬프트 생성/레이트리밋 대응/파이프라인 컴포넌트화” 관점에서 묶어둔 것이 특징입니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/latest/curate-text/generate-data/index.html?utm_source=openai))

### 3) 다른 접근과의 차이점: “RAG로 지식, SDG로 행동”
- RAG: 최신 지식/근거/사실성(knowledge)을 외부에서 공급
- SDG + Fine-tuning: 형식/절차/선호/톤/정책 준수 같은 **행동(behavior)** 을 모델 파라미터에 각인

따라서 “지식이 부족해서 틀린 답을 한다”를 SDG로 해결하려 하면, **환각을 더 그럴듯하게 만드는 방향**으로 튜닝될 위험이 큽니다(특히 teacher LLM이 틀린 정보를 자신감 있게 생성할 때).

---

## 💻 실전 코드
현실적인 시나리오: “사내 고객지원 티켓을 요약하고, 다음 액션을 표준 포맷으로 제안하는 모델”을 만들고 싶습니다. 그런데 실제 티켓은 개인정보/계약정보가 많아 학습에 쓰기 어렵고, 케이스 커버리지도 부족합니다.  
해결: (1) 합성 티켓 생성 → (2) 정답 요약/액션 생성(SFT) → (3) 후보 2개 생성 후 LLM judge로 preference(DPO)까지 만들 수 있게 데이터셋을 구축합니다.

아래 예제는 **로컬 vLLM(OpenAI-compatible endpoint)** 또는 **NVIDIA/OpenAI 호환 API** 어디든 붙일 수 있게 “OpenAI compatible” 클라이언트를 전제로 작성합니다(NeMo Curator도 이 방식을 권장). ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/v26.04/curate-text/synthetic?utm_source=openai))

### 0) 의존성/환경
```bash
python -m venv .venv && source .venv/bin/activate
pip install "openai>=1.0.0" pydantic jsonlines tenacity
export OPENAI_API_KEY="..."                # 또는 로컬 서버면 더미여도 됨
export OPENAI_BASE_URL="http://localhost:8000/v1"  # vLLM/Ray Serve 등 OpenAI 호환 엔드포인트
```

### 1) 합성 티켓 + SFT 데이터 생성(JSONL)
- 출력은 **OpenAI SFT 포맷(대화 메시지 배열)** 로 바로 저장합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/supervised-fine-tuning?utm_source=openai))
- 포인트는 “그럴듯한 이야기”가 아니라 **학습시키고 싶은 행동을 강제하는 스키마**입니다.

```python
# synth_sft_dataset.py
import os, json, uuid
from typing import Literal
from pydantic import BaseModel, Field
from tenacity import retry, wait_exponential, stop_after_attempt
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL"),  # 로컬 vLLM이면 지정
)

class Ticket(BaseModel):
    ticket_id: str
    product: Literal["payments", "analytics", "auth", "shipping"]
    severity: Literal["sev1", "sev2", "sev3"]
    customer_tier: Literal["free", "pro", "enterprise"]
    locale: Literal["ko-KR", "en-US"]
    user_message: str = Field(..., description="원문 티켓. 개인정보/비밀번호/카드번호는 포함 금지.")
    context: str = Field(..., description="상황/시스템 로그 요약. 민감정보 제거된 형태.")
    expected_resolution: str = Field(..., description="이 티켓의 '정답 방향'(원인/해결).")

class SupportAnswer(BaseModel):
    summary: str = Field(..., description="한 문단 요약(최대 4문장)")
    root_cause: str = Field(..., description="가능한 원인(단정 금지, 근거 포함)")
    next_actions: list[str] = Field(..., description="실행 가능한 다음 액션 3~6개")
    customer_reply: str = Field(..., description="고객에게 보낼 답장. 공손/간결/불필요한 사과 남발 금지.")
    tags: list[str] = Field(..., description="예: billing, timeout, oauth, webhook, rate_limit 등")

SYSTEM_GEN_TICKET = """
You generate realistic customer support tickets for a SaaS API product.
Hard rules:
- Do NOT include any personal data, secrets, passwords, tokens, or real company names.
- The ticket must be plausible and specific (error codes, timestamps allowed but fake).
- Provide diverse edge cases (timeouts, partial failures, retries, idempotency, webhook signatures, OAuth).
Return JSON that matches the schema exactly.
"""

SYSTEM_GEN_ANSWER = """
You are a senior support engineer.
Write an answer that follows the schema and is operationally useful.
Rules:
- If uncertain, state assumptions and propose verification steps.
- Prefer concrete next actions (commands, logs to check, config fields).
- Keep customer_reply concise, avoid blaming the customer.
Return JSON that matches the schema exactly.
"""

@retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(5))
def llm_json(system: str, user: str) -> dict:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",  # 로컬이면 로컬 모델명
        messages=[
            {"role": "system", "content": system.strip()},
            {"role": "user", "content": user.strip()},
        ],
        temperature=0.8,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)

def make_one_example(i: int) -> dict:
    t = llm_json(SYSTEM_GEN_TICKET, f"Generate 1 ticket. ticket_id should be random-like. Seed={i}")
    ticket = Ticket(**t)

    a = llm_json(
        SYSTEM_GEN_ANSWER,
        f"""Ticket JSON:
{ticket.model_dump_json(indent=2)}

Produce the best possible SupportAnswer for this ticket."""
    )
    answer = SupportAnswer(**a)

    # SFT format: messages
    messages = [
        {"role": "system", "content": "You are an enterprise customer support assistant. Follow the required output format strictly."},
        {"role": "user", "content": f"""다음 티켓을 처리하세요. JSON으로만 답하세요.
Ticket:
{ticket.model_dump_json(indent=2)}

출력 스키마:
{SupportAnswer.model_json_schema()}""" },
        {"role": "assistant", "content": answer.model_dump_json()}
    ]
    return {"messages": messages, "meta": {"ticket_id": ticket.ticket_id}}

def main(n: int = 200, out_path: str = "sft_support.jsonl"):
    with open(out_path, "w", encoding="utf-8") as f:
        for i in range(n):
            ex = make_one_example(i)
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"wrote {n} examples -> {out_path}")

if __name__ == "__main__":
    main()
```

예상 출력(일부):
- `sft_support.jsonl`에 한 줄당 `{"messages":[...], "meta":...}` 형태로 저장
- 이후 바로 fine-tuning job에 넣을 수 있는 구조

### 2) (확장) Preference(DPO) 데이터까지 만들기: 후보 2개 + LLM Judge
SFT만으로 “형식”은 잡히지만, 미묘한 품질(간결함, 고객 커뮤니케이션, 과도한 확신 금지)은 **선호 학습**이 더 잘 먹힙니다. 여기서 사람 라벨이 없으면 RLAIF처럼 “AI가 비교”를 합니다(Constitutional AI가 제시한 패턴). ([arxiv.org](https://arxiv.org/abs/2212.08073?utm_source=openai))

구현 아이디어:
- 같은 티켓에 대해 답변 후보 A/B를 생성(temperature 다르게, 혹은 서로 다른 system prompt)
- Judge 모델이 “스펙 준수/유용성/안전” 기준으로 winner를 고르고 이유를 기록
- 최종적으로 (prompt, chosen, rejected) 형태로 저장

(지면 관계상 코드 생략이 아니라, 위 코드에 `candidate_generation()`과 `judge()`를 추가해 JSONL에 `chosen/rejected`를 쓰면 됩니다. 운영에서는 judge를 더 강한 모델로 두고, 생성 모델은 비용 최적화 모델로 둡니다.)

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **스키마 강제 + 메타데이터 태깅을 “처음부터”**
- 나중에 필터링/샘플링/디버깅하려면 `topic/severity/policy_tags`가 없으면 답이 없습니다.
- NeMo Curator도 SDG를 “다른 큐레이션 모듈과 결합”하는 전제를 깔고 설계합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/25.07/datacuration/syntheticdata.html?utm_source=openai))

2) **중복 제거(Dedup)와 다양성 제어가 비용을 결정**
- 토픽/프롬프트가 중복되면 그대로 LLM 호출 비용으로 새어 나갑니다(레이트리밋도 악화). ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/25.07/datacuration/syntheticdata.html?utm_source=openai))
- 실전에서는 MinHash/SimHash로 입력(티켓)과 출력(답변) 모두 near-dup 제거를 권장합니다.

3) **합성 데이터는 “평가셋”이 아니라 “훈련셋”**
- 평가셋까지 합성으로 만들면, 모델이 teacher의 취향을 따라가며 “좋아 보이기”만 합니다.
- 최소한의 인간 검토 샘플(예: 토픽별 50개)과, 실제 로그 기반의 privacy-safe eval set을 분리하세요.

### 흔한 함정/안티패턴
- **Teacher leakage**: 생성에 쓴 모델과 같은 계열/체크포인트를 파인튜닝 타깃으로 쓰면, “복습”이 돼서 겉보기 성능이 과대평가됩니다.
- **과도한 정답 단정**: LLM이 만든 root_cause는 대개 “그럴듯한 소설”입니다. 반드시 “검증 단계”를 next_actions에 포함시키게 스키마로 강제하세요.
- **Self-training 무한루프**: 실패 케이스를 분석하지 않고 “더 많이 생성→더 학습”만 하면 편향이 고착됩니다.

### 비용/성능/안정성 트레이드오프
- 비용: (생성 모델)×(샘플 수)×(후처리/평가 호출)  
  - 대량 SDG는 API 호출 레이트리밋/단가가 병목이라, NeMo 쪽은 **로컬/자사 엔드포인트(OpenAI 호환)** 와 파이프라인 동시 실행을 강조합니다. ([nvidia.com](https://www.nvidia.com/en-us/gpu-cloud/nemo-llm-service/?utm_source=openai))
- 성능: SFT는 “형식/절차”, Preference는 “품질 감각”을 올리지만, 둘 다 **지식 최신성**은 해결 못 합니다.
- 안정성: 합성 데이터가 정책/안전 영역을 다루면, 공격적 데이터(예: 독성/우회) 생성 연구도 존재합니다. 이런 데이터는 방어 목적으로만 제한적으로 다뤄야 하며, 접근 통제와 리뷰가 필요합니다. ([arxiv.org](https://arxiv.org/abs/2604.17769?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년의 SDG는 “프롬프트 몇 개로 5만 건 만들기”가 아니라 **데이터 공급망(생성→필터→라벨→평가→재생성)** 입니다. NeMo Curator가 SDG를 큐레이션 파이프라인 일부로 다루고, Nemotron 계열에서 합성 데이터 비중을 크게 가져간 이유도 여기에 있습니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/25.02/datacuration/syntheticdata.html?utm_source=openai))

도입 판단 기준(체크리스트):
- 우리 문제는 **지식 부족**인가, **행동/형식/정책 준수** 문제인가? → 후자면 SDG+FT 적합
- “좋은 답”을 스키마/규칙으로 **검증 가능**하게 정의할 수 있는가?
- 합성 데이터가 만들어낼 편향을 막을 **실제 eval set**과 **인간 샘플 리뷰**가 있는가?
- 중복 제거/품질 게이트/메타 태깅을 포함한 파이프라인을 운영할 준비가 되었는가?

다음 학습 추천:
- NeMo Curator의 SDG 튜토리얼을 따라가며 “대량 생성 + 레이트리밋 대응” 감각을 잡고, ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/latest/curate-text/generate-data/index.html?utm_source=openai))
- Constitutional AI/RLAIF 패턴을 참고해 “선호 데이터 생성 + judge 설계”를 붙여보세요. ([arxiv.org](https://arxiv.org/abs/2212.08073?utm_source=openai))

원하시면, 위 예제를 기반으로 **(1) dedup+품질 점수(LLM judge)까지 포함한 완전 파이프라인**, **(2) DPO 학습용 데이터 포맷 변환**, **(3) 실제 OpenAI fine-tuning job 생성 스크립트**까지 한 글로 이어서 구성해 드릴게요. ([platform.openai.com](https://platform.openai.com/docs/guides/supervised-fine-tuning?utm_source=openai))