---
title: "합성 데이터로 LLM 파인튜닝 “진짜 성능” 뽑는 법: 2026년 5월 기준 Synthetic Data 파이프라인 설계 가이드"
date: 2026-05-30 04:06:40 +0900
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
프로덕션에서 LLM을 쓰다 보면, 결국 두 가지 벽을 만납니다.

1) **도메인/포맷 특화가 필요한데 라벨 데이터가 없다** (또는 만들기 너무 비싸다)  
2) RAG로는 해결이 안 되는 **출력 스타일·정책·함수호출·분류 기준** 같은 “행동”을 모델에 주입해야 한다

이때 2026년에도 가장 비용 효율적인 선택지 중 하나가 **LLM synthetic data(합성 데이터)로 SFT 데이터셋을 구축**하는 접근입니다. Self-Instruct 류 워크플로우(소량 seed → teacher LLM 확장 → 품질 필터링 → JSONL로 SFT)가 사실상 표준 레시피로 굳어졌고, 대규모 합성 코퍼스(Cosmopedia)처럼 “합성으로 스케일을 만든” 사례도 공개되어 있습니다. ([futureagi.com](https://futureagi.com/blog/synthetic-data-fine-tuning-llms/?utm_source=openai))

### 언제 쓰면 좋은가
- **출력 포맷 고정(JSON/SQL/함수 호출 스키마)**, 사내 규칙 기반 분류, 템플릿화된 리포트 생성처럼 “정답 형식”이 명확한 작업
- **엣지 케이스가 중요한 작업**(장애 대응 runbook Q&A, 정책 위반 탐지 설명 등)에서 커버리지를 빠르게 늘리고 싶을 때
- 고가 frontier 모델을 직접 호출하는 대신, **작은 모델을 파인튜닝해서 inference cost를 낮추고** 싶은 경우

### 언제 쓰면 안 되는가 (또는 매우 조심)
- **정답의 사실성/법률/의료 정확성**이 핵심인 생성 태스크에서 “그럴듯함”이 성능으로 오인될 때(합성 데이터는 특히 그럴듯한 오류를 양산)
- seed가 빈약한데 대량 합성으로 “대충 채우기”: 분포가 틀어지는 **distribution drift**가 누적되면, 나중에 고치기 더 어렵습니다. ([digitalapplied.com](https://www.digitalapplied.com/blog/synthetic-data-generation-llm-training-decision-guide-2026?utm_source=openai))
- 검증(quality gate) 없이 단일 패스 생성: 현업에서 가장 흔한 실패 원인이 “모델이 정답을 학습한 게 아니라 teacher의 말투/버릇을 학습”하는 경우입니다(커뮤니티에서도 반복적으로 보고). ([reddit.com](https://www.reddit.com/r/deeplearning/comments/1t0rdri/i_have_been_finetuning_llama_31_8b_with_qlora_for/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) LLM 합성 데이터의 3요소: **Generator / Verifier / Curator**
2026년 실무 합성 데이터 파이프라인을 단순화하면 아래 3개 역할로 분해됩니다.

- **Generator(teacher)**: seed를 보고 새로운 instruction/input을 만들고 답을 생성
- **Verifier(judge)**: 샘플이 “요구 조건을 만족하는지” 자동 채점(규칙+LLM judge 혼합)
- **Curator**: 중복 제거, 난이도/토픽 밸런싱, train/eval 분리, JSONL 변환

핵심은 “한 번에 좋은 데이터를 뽑는다”가 아니라 **데이터 엔지니어링처럼 파이프라인으로 반복 개선**하는 것입니다(단일 패스 생성의 환각/드리프트 문제가 자주 언급됨). ([reddit.com](https://www.reddit.com/r/LangChain/comments/1sm29wx/title_moving_beyond_prompt_engineering_why_i/?utm_source=openai))

### 2) Self-Instruct 계열 흐름(구조/흐름)
Self-Instruct 원 논문은 “거의 무라벨”로 instruction-tuning 데이터를 늘리는 접근을 제시합니다. 구조는 대략 이렇습니다. ([arxiv.org](https://arxiv.org/abs/2212.10560?utm_source=openai))

1. **Seed tasks**(예: 200개)를 사람이 작성(작게, 하지만 매우 정확히)
2. Teacher LLM에 seed를 few-shot으로 주고, **새로운 instruction을 생성**
3. 각 instruction에 대해 **response 생성**
4. 휴리스틱/모델 기반 필터로 노이즈 제거 → **SFT 학습 데이터(JSONL)**

여기서 2026년 실무적으로 중요한 차이는:
- **“생성”보다 “검증/필터링”이 성능을 좌우**한다는 점  
- 데이터가 커질수록 **중복/패턴 반복이 급격히 성능을 갉아먹는다**는 점(대규모 합성 데이터에서도 dedup을 강조). ([huggingface.co](https://huggingface.co/datasets/HuggingFaceTB/cosmopedia?utm_source=openai))

### 3) 합성 데이터의 대표 실패 모드
- **Style overfitting**: 모델이 과제 해결 로직이 아니라 teacher의 문장 패턴/포맷 버릇을 학습 ([reddit.com](https://www.reddit.com/r/deeplearning/comments/1t0rdri/i_have_been_finetuning_llama_31_8b_with_qlora_for/?utm_source=openai))  
- **Distribution drift**: 실제 운영 트래픽과 합성 데이터 분포가 달라져서, offline 성능은 좋아 보이는데 online에서 무너짐 ([digitalapplied.com](https://www.digitalapplied.com/blog/synthetic-data-generation-llm-training-decision-guide-2026?utm_source=openai))  
- **Leakage/contamination**: train에 들어간 패턴이 eval에도 들어가서 과대평가(특히 합성은 “생성 템플릿”이 반복되기 쉬움)

---

## 💻 실전 코드
현실적인 시나리오로: **사내 장애 대응(runbook) Q&A 봇**을 만든다고 가정하겠습니다.

- 입력: 엔지니어가 장애 상황을 서술(로그 일부 + 증상)
- 출력: **반드시 JSON**(원인 후보, 확인 커맨드, 롤백/완화 단계, 위험도)
- 목표: 작은 모델(예: Llama/Qwen 계열)을 SFT로 “항상 JSON으로, 사내 규칙대로” 답하게 만들기  
- 데이터 문제: 실제 장애 티켓은 민감하고 수가 적음 → seed 120개만 정제 가능

아래 코드는
1) seed로부터 synthetic instruction 생성  
2) teacher로 답 생성  
3) **Verifier(규칙 + LLM judge)**로 필터링  
4) OpenAI SFT 포맷(JSONL messages)로 저장  
까지 한 번에 갑니다.

> 의존성: `pip install openai pydantic jsonschema tenacity tqdm`  
> 사전 준비: `OPENAI_API_KEY` 설정  
> (OpenAI SFT는 “투자 전에 eval 구축”과 데이터 포맷을 강조합니다. 포맷/베스트프랙티스는 공식 가이드를 따르세요.) ([platform.openai.com](https://platform.openai.com/docs/guides/supervised-fine-tuning?utm_source=openai))

```python
import os, json, re, hashlib
from typing import List, Dict, Any, Optional
from tqdm import tqdm
from tenacity import retry, wait_exponential, stop_after_attempt
from jsonschema import validate, ValidationError
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ---- 1) 우리가 원하는 출력(JSON) 스키마를 먼저 고정한다 ----
RUNBOOK_SCHEMA = {
    "type": "object",
    "required": ["summary", "hypotheses", "checks", "mitigations", "risk"],
    "properties": {
        "summary": {"type": "string", "minLength": 10},
        "hypotheses": {
            "type": "array",
            "minItems": 2,
            "items": {"type": "object", "required": ["cause", "confidence"], "properties": {
                "cause": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
            }}
        },
        "checks": {"type": "array", "minItems": 2, "items": {"type": "string"}},
        "mitigations": {"type": "array", "minItems": 2, "items": {"type": "string"}},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]}
    }
}

def stable_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

def extract_json(text: str) -> Optional[dict]:
    # 모델이 앞/뒤로 말을 붙이는 경우가 많아서, 가장 그럴듯한 JSON 덩어리를 추출
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

# ---- 2) seed 예시(현실에서는 사내 120개 정도를 준비) ----
SEED_CASES = [
    {
        "service": "payments-api",
        "symptoms": "결제 승인 요청이 30% 확률로 504. p95 latency 12s로 급등. 신규 배포 없음.",
        "log_snippet": "upstream connect error or disconnect/reset before headers. reset reason: connection termination",
        "constraints": ["AWS EKS", "Envoy", "Postgres"],
    },
    {
        "service": "auth-service",
        "symptoms": "로그인 성공률 급락. 401 증가. 일부 리전에만 발생.",
        "log_snippet": "jwt signature validation failed: kid not found",
        "constraints": ["multi-region", "JWKS cache", "CloudFront"],
    },
]

# ---- 3) Generator: seed를 변형해서 더 많은 케이스(instruction/input)를 만든다 ----
@retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(4))
def gen_new_case(seed: dict) -> dict:
    prompt = f"""
You are generating realistic on-call incident tickets for SRE training data.
Create ONE new incident scenario derived from the seed, but not a trivial paraphrase.
Keep it plausible and operationally detailed.

Seed:
{json.dumps(seed, ensure_ascii=False)}

Return JSON with keys:
service, symptoms, log_snippet, constraints (array), hidden_true_cause (string), difficulty (1-5)
"""
    r = client.responses.create(
        model="gpt-5.5-2026-04-23",
        input=prompt,
        temperature=0.8,
    )
    obj = extract_json(r.output_text)
    if not obj:
        raise ValueError("generator did not return JSON")
    return obj

# ---- 4) Teacher: 케이스 -> 우리가 원하는 "정답(JSON)"을 생성 ----
@retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(4))
def teacher_answer(case: dict) -> str:
    sys = "You are a senior SRE. Output MUST be valid JSON only. No extra text."
    user = f"""
Incident:
{json.dumps({k: case[k] for k in ["service","symptoms","log_snippet","constraints"]}, ensure_ascii=False)}

Output JSON matching this schema (conceptually):
- summary: brief
- hypotheses: 2-4 items with confidence 0..1
- checks: shell/kubectl/sql commands or verification steps (strings)
- mitigations: safe mitigations/rollbacks (strings)
- risk: low/medium/high
"""
    r = client.responses.create(
        model="gpt-5.5-2026-04-23",
        input=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        temperature=0.3,
    )
    return r.output_text

# ---- 5) Verifier: (a) JSON schema (b) LLM judge로 "실무적으로 유용한가" 채점 ----
@retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(4))
def judge_score(case: dict, answer_text: str) -> dict:
    # judge는 "정답성"보단 "형식 준수/실행가능성/환각 가능성"을 본다
    prompt = f"""
You are a strict dataset judge for SFT training.
Given an incident and an assistant answer, score it.

Incident:
{json.dumps({k: case[k] for k in ["service","symptoms","log_snippet","constraints"]}, ensure_ascii=False)}

Assistant answer (must be JSON):
{answer_text}

Return JSON:
{{
  "format_ok": true/false,
  "actionable": 1-5,
  "hallucination_risk": 1-5,
  "constraint_alignment": 1-5,
  "notes": "short"
}}
Rules:
- format_ok false if not valid JSON or missing required fields.
- actionable: are checks/mitigations concrete and safe?
- hallucination_risk: higher means more likely wrong/unsafe steps.
"""
    r = client.responses.create(
        model="gpt-5.5-2026-04-23",
        input=prompt,
        temperature=0.0,
    )
    obj = extract_json(r.output_text)
    if not obj:
        raise ValueError("judge did not return JSON")
    return obj

def passes_rules(answer_text: str) -> bool:
    obj = extract_json(answer_text)
    if not obj:
        return False
    try:
        validate(instance=obj, schema=RUNBOOK_SCHEMA)
    except ValidationError:
        return False
    # 추가 룰: confidence 합이 0이거나 전부 1이면(대충 찍기) 탈락
    confs = [h.get("confidence", 0) for h in obj.get("hypotheses", [])]
    if len(confs) < 2:
        return False
    if all(c in (0, 1) for c in confs):
        return False
    return True

def to_openai_sft_record(case: dict, answer_text: str) -> dict:
    # OpenAI SFT는 messages 기반 JSONL을 사용 ([platform.openai.com](https://platform.openai.com/docs/guides/supervised-fine-tuning?utm_source=openai))
    user = f"""
Incident:
service={case["service"]}
symptoms={case["symptoms"]}
log_snippet={case["log_snippet"]}
constraints={case["constraints"]}

Return JSON only.
"""
    return {
        "messages": [
            {"role": "system", "content": "You are a senior SRE assistant. Output MUST be valid JSON only."},
            {"role": "user", "content": user.strip()},
            {"role": "assistant", "content": extract_json(answer_text) and json.dumps(extract_json(answer_text), ensure_ascii=False)}
        ],
        "metadata": {
            "case_id": stable_hash(user),
            "difficulty": case.get("difficulty"),
            "hidden_true_cause": case.get("hidden_true_cause")
        }
    }

def build_dataset(target_n: int = 200, out_path: str = "sre_synth_sft.jsonl"):
    seen = set()
    kept = 0
    with open(out_path, "w", encoding="utf-8") as f:
        pbar = tqdm(total=target_n)
        while kept < target_n:
            seed = SEED_CASES[kept % len(SEED_CASES)]
            case = gen_new_case(seed)

            # 중복 방지(케이스 텍스트 기준)
            sig = stable_hash(case["service"] + case["symptoms"] + case["log_snippet"])
            if sig in seen:
                continue
            seen.add(sig)

            ans = teacher_answer(case)
            if not passes_rules(ans):
                continue

            j = judge_score(case, ans)
            if (not j.get("format_ok")):
                continue
            if j.get("actionable", 0) < 4:
                continue
            if j.get("hallucination_risk", 5) > 2:
                continue
            if j.get("constraint_alignment", 0) < 4:
                continue

            rec = to_openai_sft_record(case, ans)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            kept += 1
            pbar.update(1)
        pbar.close()

if __name__ == "__main__":
    build_dataset(target_n=200)
    print("Wrote sre_synth_sft.jsonl")
```

### 예상 출력/산출물
- `sre_synth_sft.jsonl` (200 lines)
- 각 라인은 `messages`(system/user/assistant) + `metadata` 포함
- 이후 OpenAI SFT에 바로 투입 가능한 형태(단, 실제로는 **eval 세트 분리**가 먼저입니다). ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “생성”보다 “필터링”에 토큰을 써라
합성 데이터는 양을 늘리기 쉽지만, 성능을 만드는 건 **quality gate**입니다. OpenAI도 파인튜닝은 eval 기반으로 접근하라고 강하게 권장하고, RFT 문서에서도 “점수에 학습 신호가 있어야 한다(변별력)”는 류의 메시지가 반복됩니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))  
실무 팁:
- 규칙 검증(JSON schema, 금칙어, 길이, 필수 필드) + LLM judge 조합
- judge는 “정답성”보다 **실행 가능성/형식 준수/위험도**를 보게 설계

### Best Practice 2) train/eval contamination을 구조적으로 막아라
합성은 템플릿이 반복되기 쉬워서, 랜덤 split만 하면 leakage가 생깁니다.
- 케이스 `case_id`를 만들고, **seed 계열/서비스/원인군 단위로 그룹 split**
- MinHash/SimHash로 **near-duplicate 제거**(Cosmopedia도 중복을 매우 강하게 관리). ([huggingface.co](https://huggingface.co/datasets/HuggingFaceTB/cosmopedia?utm_source=openai))

### Best Practice 3) “accumulate, don’t replace”를 하드 제약으로
합성 데이터로 실제 데이터를 대체하는 순간, 분포가 무너질 때 감지 자체가 늦습니다. “합성은 커버리지 확장/빈틈 메우기”로 쓰고, **소량이라도 real trace/real ticket을 계속 섞는** 전략이 안전합니다. ([digitalapplied.com](https://www.digitalapplied.com/blog/synthetic-data-generation-llm-training-decision-guide-2026?utm_source=openai))

### 흔한 함정/안티패턴
- **단일 teacher + 단일 프롬프트로 5만 건 뽑기**: 말투/구조가 고정되어 style overfitting 유발 ([reddit.com](https://www.reddit.com/r/deeplearning/comments/1t0rdri/i_have_been_finetuning_llama_31_8b_with_qlora_for/?utm_source=openai))  
  → generator 프롬프트에 “audience/format/verbosity/role” 축을 랜덤화하고, 가능하면 teacher를 2종 이상 섞기(Ensemble류 아이디어도 연구로 제안). ([arxiv.org](https://arxiv.org/abs/2310.13961?utm_source=openai))
- **합성으로 안전장치가 느슨해질 수 있음**: 2025년 연구는 synthetic fine-tuning 데이터가 모델 행동에 미치는 영향(예: 가드레일 약화 가능성)을 경고합니다. ([arxiv.org](https://arxiv.org/abs/2511.01490?utm_source=openai))  
  → policy 관련 태스크는 별도 트랙으로 분리하고, red-teaming eval을 같이 운용

### 비용/성능/안정성 트레이드오프(현실 버전)
- Teacher를 frontier로 쓰면 품질은 오르지만 비용↑. 대신 **Verifier를 강하게** 해서 “버리는 비율”을 감수하는 편이, 저품질을 학습시키는 것보다 낫습니다.
- SFT 자체도 “데이터가 곧 모델”이라서, 파인튜닝 비용보다 **데이터 생성/검증 비용**이 커지는 구간이 옵니다.
- OpenAI 쪽은 2026년 5월 8일 업데이트로 fine-tuning 플랫폼/프로그램 변화 공지가 있었으니, 도입 시점에는 제품 정책을 반드시 재확인하세요. ([openai.com](https://openai.com/index/introducing-improvements-to-the-fine-tuning-api-and-expanding-our-custom-models-program/?utm_source=openai))

---

## 🚀 마무리
핵심만 정리하면:

- 2026년 합성 데이터 기반 파인튜닝은 **Self-Instruct(확장) + Verifier(필터) + Curator(중복/분포 관리)**의 “파이프라인 싸움”입니다. ([arxiv.org](https://arxiv.org/abs/2212.10560?utm_source=openai))
- 성공하는 팀은 “많이 생성”이 아니라 **엄격히 버리고, eval로 확인하고, 실제 데이터와 섞어** 갑니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))
- 도입 판단 기준:
  1) 출력 형식/정책이 명확한가? (명확할수록 synthetic이 강함)  
  2) 검증 가능한가? (schema/테스트/시뮬레이터/정답 룰)  
  3) 운영 트래픽과 분포를 맞출 장치가 있는가? (trace 기반 샘플링, 그룹 split)

다음 학습/확장 추천:
- 대규모 합성 데이터 제작/중복 제거 사례: Cosmopedia 제작 방식(프롬프트 스케일링, dedup) ([huggingface.co](https://huggingface.co/blog/cosmopedia?utm_source=openai))
- synthetic 데이터가 모델 행동/안전성에 미치는 영향(가드레일 포함) ([arxiv.org](https://arxiv.org/abs/2511.01490?utm_source=openai))
- OpenAI SFT/RFT 문서로 “eval 먼저”와 포맷/운용 기준 정리 ([platform.openai.com](https://platform.openai.com/docs/guides/supervised-fine-tuning?utm_source=openai))

원하면, 당신의 프로젝트 도메인(예: 고객센터 분류, SQL 생성, 내부 정책 Q&A, 코드 리뷰 봇)에 맞춰 **(1) seed 설계 템플릿 (2) judge rubric (3) contamination 방지 split 전략 (4) LoRA/QLoRA까지 포함한 학습 커맨드** 형태로 바로 적용 가능한 청사진으로 바꿔드릴게요.