---
title: "합성 데이터로 LLM을 “가르칠” 것인가: 2026년식 Synthetic Data 파이프라인(생성→검증→선별→파인튜닝) 심층 가이드"
date: 2026-05-08 03:42:24 +0900
categories: [AI, Data]
tags: [ai, data, trend, 2026-05]
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
LLM 파인튜닝에서 제일 비싼 건 GPU가 아니라 **“좋은 데이터”**입니다. 그런데 실제 프로젝트에서는 (1) 도메인 라벨링 인력이 없거나 (2) 개인정보/저작권 이슈로 원문 데이터를 학습에 쓰기 어렵거나 (3) 운영 로그는 많은데 품질이 들쭉날쭉이라 학습셋으로 바로 못 쓰는 일이 흔합니다. 이때 **LLM synthetic data(합성 데이터)**는 “데이터 엔지니어링을 자동화”하는 현실적인 해법이 됩니다.

다만 합성 데이터는 **아무렇게나 생성하면 성능이 오히려 떨어지는** 경우가 많습니다. 생성 모델(teacher)의 버릇/환각이 그대로 데이터에 박히고, 필터링이 약하면 분포가 망가지며, 결과적으로 student가 “그럴듯한데 틀린” 스타일을 학습합니다. 그래서 2026년 기준 베스트 프랙티스는 단순 생성이 아니라 **생성 → 자동 검증/스코어링 → 데이터 선택(data selection) → SFT/Preference 최적화**로 이어지는 파이프라인입니다. (OpenAI도 distillation 관점에서 “큰 모델 결과를 작은 모델 학습 데이터로 쓰는” 흐름을 공식 가이드로 제시합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/distillation?utm_source=openai)))

**언제 쓰면 좋은가**
- 운영 트래픽/티켓/대화 로그가 많고, 이를 **정제·라벨링**하기가 어려울 때(“trace → synthetic data → fine-tuned specialist” 루프가 커뮤니티에서 반복적으로 공유됩니다. ([reddit.com](https://www.reddit.com/r/mlops/comments/1rp47s1/closing_the_production_loop_llm_traces_synthetic/?utm_source=openai)))
- 목표가 “새 지식 주입”이라기보다 **형식, 절차, 도구 호출, 스타일, 정책 준수**처럼 행동/포맷을 안정화하는 것일 때 (SFT가 특히 강함. ([platform.openai.com](https://platform.openai.com/docs/guides/distillation?utm_source=openai)))
- 작은 모델(SLM)을 **업무 특화**로 만들어 inference 비용을 낮추고 싶을 때(teacher→student distillation/합성 데이터가 핵심)

**언제 쓰면 안 되는가**
- 문제의 핵심이 “사내 문서/DB의 최신 지식”이라면: 파인튜닝보다 **RAG**가 더 안전하고 유지보수 비용이 낮습니다(합성 데이터로 지식을 주입하면 누락/망각 위험이 큼).
- 자동 검증이 불가능한(정답 판정이 어려운) 태스크인데도 평가·필터링 체계 없이 “그냥 많이 생성”하려는 경우: 품질이 랜덤워크처럼 무너집니다(“검증 파이프라인 없으면 drift/환각 패턴이 누적된다”는 실무 경험담이 많습니다. ([reddit.com](https://www.reddit.com/r/LangChain/comments/1sm29uv/title_moving_beyond_prompt_engineering_why_i/?utm_source=openai)))

---

## 🔧 핵심 개념
### 1) 주요 개념 정의
- **Teacher model / Student model**: teacher(큰 LLM)가 고품질 답안을 생성하고, 이를 student(작은 LLM) 학습 데이터로 사용해 비용 효율을 얻는 패턴. OpenAI 가이드도 distillation을 SFT 데이터 구축 방법으로 명시합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/distillation?utm_source=openai))
- **Self-Instruct**: LLM이 스스로 instruction(문제)과 demonstration(모범 답)을 생성해 instruction tuning 데이터를 만드는 방법. 인간 라벨링을 거의 안 쓰는 접근의 시초격. ([arxiv.org](https://arxiv.org/abs/2212.10560?utm_source=openai))
- **Evol-Instruct / Auto Evol-Instruct**: seed instruction을 점진적으로 “진화”시켜 난이도/다양성을 키우는 계열. Auto Evol-Instruct는 “진화 프롬프트 설계 자체를 자동화/최적화”한다는 방향. ([arxiv.org](https://arxiv.org/abs/2406.00770?utm_source=openai))
- **Data selection / Filtering**: 합성 데이터는 “생성”보다 “선별”이 성능을 좌우합니다. 최근에는 **reverse selection**처럼 “좋은 것 고르기”보다 “나쁜 것 제거”가 더 견고하다는 연구/사례도 나옵니다. ([ai-paper-delta.vercel.app](https://ai-paper-delta.vercel.app/en/papers/2603.12165?utm_source=openai))

### 2) 내부 작동 방식(구조/흐름)
2026년 실무형 파이프라인을 “왜 이 순서가 안정적인지”까지 포함해 정리하면 아래 흐름이 가장 재현성이 좋습니다.

1) **Seed 수집(현실 분포 고정)**
- 운영 로그, 티켓, API 요청, 기존 프롬프트 템플릿 등에서 “현실 입력 분포”를 뽑습니다.
- 이유: 합성 데이터는 쉽게 **style drift**가 생깁니다. seed가 없으면 teacher의 말투/편향이 분포를 지배합니다.

2) **Instruction 확장(coverage 확보)**
- Self-Instruct 방식으로 seed를 변형/확장하거나 ([arxiv.org](https://arxiv.org/abs/2212.10560?utm_source=openai))  
- Evol/Auto-Evol 계열로 난이도/제약을 추가해 “빈 구간”을 채웁니다. ([arxiv.org](https://arxiv.org/abs/2406.00770?utm_source=openai))  
- 실무 팁: 여기서 “무작정 복잡하게”가 아니라, **실패 케이스 중심**으로 확장해야 합니다(예: JSON 깨짐, tool args 누락, 정책 위반 등).

3) **Answer 생성(teacher)**
- teacher는 가능하면 “정답 근거가 명확한 형식”으로 답하게 설계합니다(예: function call JSON, SQL, 코드 diff, 체크리스트).
- 이유: 다음 단계(자동 검증/스코어링)가 가능해집니다.

4) **자동 검증/스코어링(quality gate)**
- **형식 검증**: JSON schema, function signature, lint/test.
- **정합성 검증**: 입력에 없는 사실을 만들지 않는지(grounding), 금칙 정책 위반 여부 등.
- **Judge scoring**: 별도의 judge LLM로 일관성/명료성 점수화 후 컷. (운영 trace→스코어링→학습 루프 사례가 공유됨. ([reddit.com](https://www.reddit.com/r/mlops/comments/1rp47s1/closing_the_production_loop_llm_traces_synthetic/?utm_source=openai)))

5) **Data selection(중복 제거 + 난이도/다양성 균형)**
- 중복/유사 샘플이 많으면 “학습은 잘 되는데 일반화가 안 되는” 현상이 생깁니다.
- 최신 연구는 “적은 양만 남겨도 성능 유지” 같은 결과를 보여주며, 결국 핵심은 **선별 규칙**입니다. ([ai-paper-delta.vercel.app](https://ai-paper-delta.vercel.app/en/papers/2603.12165?utm_source=openai))

6) **Fine-tuning(SFT → 필요 시 DPO/RFT)**
- 먼저 SFT로 포맷/행동을 고정하고, “선호”가 중요한 영역(말투, 안전, 거절, 우선순위)은 preference 최적화(DPO 등)를 고려합니다(관련 가이드 존재). ([cookbook.openai.com](https://cookbook.openai.com/examples/fine_tuning_direct_preference_optimization_guide?utm_source=openai))  
- OpenAI는 데이터 밸런스(예: refusal 비율)가 추론 시 행동을 왜곡할 수 있다고 명시합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))

### 3) 다른 접근과의 차이점
- **RAG vs 합성 데이터 파인튜닝**: RAG는 “지식 최신성/근거”에 강하고, 파인튜닝은 “형식/스타일/절차의 일관성”에 강합니다. 합성 데이터는 특히 후자에 효율적입니다.
- **수동 라벨링 vs 합성 데이터**: 수동은 품질이 좋지만 확장성이 낮고, 합성은 확장되지만 필터링이 없으면 품질이 급락합니다. 그래서 2026년에는 “생성보다 검증/선별”이 경쟁력입니다. ([blog.premai.io](https://blog.premai.io/how-to-generate-synthetic-training-data-for-llm-fine-tuning-2026-guide/?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “운영에서 많이 나오는” **Customer Support 티켓 → 표준화된 triage 결과(JSON) 생성**을 목표로 합니다.  
합성 데이터로 **파인튜닝용 SFT 데이터(JSONL)**를 만들고, 최소한의 품질 게이트(스키마/중복/LLM judge)까지 넣습니다.

### 0) 의존성/준비
```bash
python -m venv .venv
source .venv/bin/activate
pip install openai pydantic jsonlines rapidfuzz tqdm python-dotenv
export OPENAI_API_KEY="YOUR_KEY"
```

### 1) 스키마(학습 타깃을 “검증 가능”하게 만들기)
```python
# schema.py
from pydantic import BaseModel, Field
from typing import Literal, List

class TriageResult(BaseModel):
    category: Literal["billing", "bug", "account", "howto", "feature_request", "other"]
    severity: Literal["sev1", "sev2", "sev3", "sev4"]
    needs_human: bool
    actions: List[str] = Field(min_length=1, max_length=6)
    reply_draft: str = Field(min_length=50, max_length=800)
```

### 2) Seed(현실적인 입력 분포) + Teacher로 합성 레코드 생성
- 포인트: “질문 생성”까지 합성으로 하면 drift가 커지니, **seed는 운영 데이터/템플릿에서 시작**하는 걸 권합니다.
- teacher 프롬프트는 **JSON only** + “근거 없는 내용 금지”를 강하게.

```python
# generate_sft_data.py
import os, json, hashlib
from openai import OpenAI
from tqdm import tqdm
from schema import TriageResult
from rapidfuzz import fuzz

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SEEDS = [
  {
    "ticket_id": "T-18422",
    "subject": "결제가 두 번 되었어요",
    "body": "어제 19.99달러 결제했는데 오늘 또 결제 알림이 왔습니다. 환불 가능한가요?",
    "plan": "pro",
    "locale": "ko-KR"
  },
  {
    "ticket_id": "T-18423",
    "subject": "로그인 시 2FA 코드가 안 와요",
    "body": "SMS 인증 코드가 오지 않습니다. 이메일로는 받을 수 있나요?",
    "plan": "team",
    "locale": "ko-KR"
  },
  # 실제로는 운영 티켓에서 수천 개 샘플링
]

SYSTEM = """You are a senior support triage assistant.
Return ONLY valid JSON that matches the given schema. No markdown, no commentary.
Do not invent facts not present in the ticket. If unknown, choose conservative actions and set needs_human=true.
Write reply_draft in Korean."""

SCHEMA_HINT = {
  "category": "billing|bug|account|howto|feature_request|other",
  "severity": "sev1|sev2|sev3|sev4",
  "needs_human": True,
  "actions": ["..."],
  "reply_draft": "..."
}

def call_teacher(ticket: dict) -> dict:
    prompt = {
      "ticket": ticket,
      "output_schema": SCHEMA_HINT
    }
    r = client.responses.create(
        model="gpt-4.1-2025-04-14",
        input=[
          {"role":"system","content": SYSTEM},
          {"role":"user","content": json.dumps(prompt, ensure_ascii=False)}
        ],
        temperature=0.2
    )
    text = r.output_text
    return json.loads(text)

def is_near_duplicate(a: str, b: str) -> bool:
    return fuzz.token_set_ratio(a, b) >= 92

def stable_id(ticket: dict, triage: dict) -> str:
    s = json.dumps({"t":ticket, "y":triage}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

def to_openai_sft_example(ticket: dict, triage: dict) -> dict:
    # OpenAI SFT는 대화형 messages 형태가 일반적(모델/가이드 참고). ([platform.openai.com](https://platform.openai.com/docs/guides/distillation?utm_source=openai))
    return {
      "messages": [
        {"role":"system","content": SYSTEM},
        {"role":"user","content": f"[SUBJECT]\n{ticket['subject']}\n\n[BODY]\n{ticket['body']}\n\n[PLAN]\n{ticket['plan']}\n[LOCALE]\n{ticket['locale']}"},
        {"role":"assistant","content": json.dumps(triage, ensure_ascii=False)}
      ],
      "metadata": {
        "ticket_id": ticket["ticket_id"],
        "example_id": stable_id(ticket, triage)
      }
    }

def llm_judge_score(ticket: dict, triage: dict) -> float:
    # 간단 judge: 명료성/정합성/액션 구체성 1~5 평균
    judge_system = "You are a strict QA judge. Output only JSON: {clarity, consistency, actionability} each 1-5."
    judge_user = {
      "ticket": ticket,
      "triage_json": triage,
      "rubric": {
        "clarity": "Is reply_draft clear and polite?",
        "consistency": "No invented facts; actions match ticket.",
        "actionability": "Actions are concrete and feasible."
      }
    }
    r = client.responses.create(
      model="gpt-4.1-mini-2025-04-14",
      input=[
        {"role":"system","content": judge_system},
        {"role":"user","content": json.dumps(judge_user, ensure_ascii=False)}
      ],
      temperature=0.0
    )
    s = json.loads(r.output_text)
    return (s["clarity"] + s["consistency"] + s["actionability"]) / 3.0

def main():
    out_path = "triage_sft.jsonl"
    seen_subjects = []

    with open(out_path, "w", encoding="utf-8") as f:
      for ticket in tqdm(SEEDS, desc="generating"):
        # 중복 방지(초간단): subject 유사도 기반
        if any(is_near_duplicate(ticket["subject"], s) for s in seen_subjects):
            continue

        triage = call_teacher(ticket)

        # 스키마 검증(여기서 깨지면 바로 폐기)
        TriageResult(**triage)

        # judge 컷(보수적으로)
        score = llm_judge_score(ticket, triage)
        if score < 4.0:
            continue

        ex = to_openai_sft_example(ticket, triage)
        f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        seen_subjects.append(ticket["subject"])

    print(f"wrote: {out_path}")

if __name__ == "__main__":
    main()
```

**예상 출력**
```bash
$ python generate_sft_data.py
generating: 100%|██████████| 2/2 [00:05<00:00,  2.62s/it]
wrote: triage_sft.jsonl
```

생성된 `triage_sft.jsonl`은 곧바로 SFT에 올릴 수 있는 형태이며, “JSON이 깨진 샘플”은 스키마 단계에서, “그럴듯하지만 부정확한 샘플”은 judge 단계에서 상당 부분 제거됩니다. 이 “검증/선별 중심”이 합성 데이터 성공의 핵심입니다. ([blog.premai.io](https://blog.premai.io/how-to-generate-synthetic-training-data-for-llm-fine-tuning-2026-guide/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **정답을 ‘검증 가능’한 형태로 설계하라**
- 자유서술 답안만 모으면 필터링이 어려워서 데이터가 쉽게 오염됩니다.
- 가능하면 JSON schema, function call, 테스트 가능한 코드/SQL 등으로 만들고 “자동 검증”을 붙이세요(위 예시처럼).

2) **Reverse filtering(나쁜 것 제거) + 다양성 제약**
- “좋아 보이는 것만 고르기”는 judge 편향에 취약합니다.
- 최근 reverse selection 계열은 noisy synthetic에서 강건하다는 아이디어를 제시합니다. ([ai-paper-delta.vercel.app](https://ai-paper-delta.vercel.app/en/papers/2603.12165?utm_source=openai))  
- 실무에서는 (a) 형식 오류 제거 (b) 사실 불일치/환각 제거 (c) 중복 제거 (d) 분포 버킷별 최소 수량 보장(카테고리/난이도)을 조합하는 게 안정적입니다.

3) **데이터 밸런스가 곧 모델 성격**
- OpenAI도 “학습 데이터에서 refusal이 과하면 추론에서도 과도하게 거절한다”는 식으로 분포-행동 연결을 경고합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))  
- 합성 데이터는 특히 “안전/거절/정책” 비율이 쉽게 과대해지니, 목표 inference 분포를 정하고 맞추세요.

### 흔한 함정/안티패턴
- **“Seed 없이” 합성 질문까지 전부 생성**: 초기엔 잘 되다가 금방 drift가 생깁니다. 운영 입력 분포를 anchor로 잡으세요.
- **한 번 생성한 데이터로 끝**: 합성 데이터는 생성기/프롬프트/필터가 바뀌면 성격이 크게 변합니다. 데이터셋 버저닝/체인지로그가 필요합니다(데이터 파이프라인 버전 관리 강조 사례가 많음). ([meta-intelligence.tech](https://www.meta-intelligence.tech/en/insight-finetuning-data?utm_source=openai))
- **Judge 1개에 올인**: judge도 편향이 있습니다. 최소한 “형식 검증 + rule-based + judge” 3중으로 나누는 게 안정적입니다.

### 비용/성능/안정성 트레이드오프
- **비용**: teacher 생성 + judge 채점이 이중 비용입니다. 대신 그 비용으로 “고품질 소량”을 만들면, 파인튜닝/운영 비용을 크게 줄일 수 있습니다(특화 SLM로 내려가는 게 목적).
- **성능**: 대량 생성보다 “필터링 강도”가 성능에 더 큰 영향을 주는 경우가 많습니다. ([blog.premai.io](https://blog.premai.io/how-to-generate-synthetic-training-data-for-llm-fine-tuning-2026-guide/?utm_source=openai))
- **안정성**: 검증 가능성(테스트/스키마) 확보가 곧 안정성입니다. 검증 불가능한 태스크라면, 합성 데이터는 “증강” 정도로만 쓰고 핵심은 인간 검수로 남기는 게 안전합니다.

---

## 🚀 마무리
2026년 5월 시점의 합성 데이터 활용은 “LLM이 데이터를 만들어준다”가 아니라, **데이터 엔지니어링을 제품화**하는 쪽으로 정리되고 있습니다. Self-Instruct/Evol 계열로 coverage를 확장하되 ([arxiv.org](https://arxiv.org/abs/2212.10560?utm_source=openai)), 승부는 **검증/선별(data selection)**에서 나고 ([ai-paper-delta.vercel.app](https://ai-paper-delta.vercel.app/en/papers/2603.12165?utm_source=openai)), 최종적으로는 distillation 관점에서 “큰 모델 성능을 작은 모델에 이식”해 비용을 줄이는 흐름이 실무적으로 가장 달콤합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/distillation?utm_source=openai))

**도입 판단 기준**
- 출력이 **구조화/검증 가능**한가? (Yes면 강추, No면 위험)
- 운영 입력 분포(seed)를 확보할 수 있는가?
- 자동 필터링(스키마/테스트/룰/judge) 중 2개 이상을 붙일 수 있는가?
- 목표가 “지식 주입”인가 “행동/형식 고정”인가? 후자일수록 합성+SFT가 잘 먹힙니다.

**다음 학습 추천**
- SFT 이후 “선호/정렬”이 필요하면 DPO 같은 preference 최적화 가이드를 함께 보세요. ([cookbook.openai.com](https://cookbook.openai.com/examples/fine_tuning_direct_preference_optimization_guide?utm_source=openai))  
- 데이터 품질 개선은 결국 반복 실험이므로, OpenAI의 fine-tuning best practices(데이터 밸런스/오류 패턴 점검)도 체크리스트로 두는 걸 권합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))