---
title: "합성 데이터로 LLM 파인튜닝을 “공장화”하는 법: 2026년형 Synthetic Data Pipeline 심층 분석"
date: 2026-04-24 03:37:27 +0900
categories: [AI, Data]
tags: [ai, data, trend, 2026-04]
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
현업에서 파인튜닝이 막히는 지점은 거의 항상 같습니다. **“학습시킬 만한 데이터가 없다(또는 비싸다)”** 입니다. 로그/문서/DB는 넘치는데, 막상 SFT나 preference fine-tuning(DPO류), RFT에 바로 넣을 **정제된 (instruction, response) / (chosen, rejected)** 형태의 데이터는 부족합니다. 이때 합성 데이터(LLM synthetic data)는 *라벨링 비용*과 *도메인 커버리지*를 동시에 줄이는 강력한 해법이 됩니다.

다만 “그냥 많이 생성해서 학습”은 2026년 기준으로도 여전히 실패 확률이 큽니다. 이유는 단순합니다: **합성 데이터는 생성 모델의 편향/환각/스타일을 그대로 증폭**시키기 때문입니다. 그래서 지금의 베스트 프랙티스는 “생성(prompt) 잘 쓰기”가 아니라, **생성→검증→필터링→평가(evals)→재생성**이 돌아가는 *데이터 엔지니어링 파이프라인*을 만드는 쪽으로 이동했습니다. (OpenAI도 fine-tuning을 “evals + prompt + fine-tuning”의 플라이휠로 설명합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning?utm_source=openai)))

**언제 쓰면 좋은가**
- 실제 유저 트래픽/도메인 문서가 있지만, 이를 **학습 가능한 형태로 변환**하는 비용이 큰 경우
- “정답 형식/정책/톤/툴 호출 포맷”처럼 **출력 제약이 명확**한 업무(고객센터 요약, RAG 답변 포맷팅, function calling, 리포트 생성 등)
- 소량의 seed 예제는 있으나 커버리지가 좁아 **롱테일 케이스 확장**이 필요한 경우

**언제 쓰면 안 되는가**
- ground truth가 필요한 문제(법률/의료 판단의 정답 라벨)에서 **검증 없이** 합성으로 대체하려는 경우
- 모델이 “모른다/거절”을 학습해야 하는데, 합성 데이터가 이를 과다/과소 대표하는 경우(거절 비율 불균형은 실제로 튜닝 품질을 망칩니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai)))
- 평가 체계(evals)가 없거나, 운영에서 실패를 관측해도 **데이터로 되돌리는 루프**를 만들 수 없는 조직

---

## 🔧 핵심 개념
### 1) “합성 데이터”를 3가지로 쪼개서 생각하기
2026년 실무 관점에서 합성 데이터는 목적이 다르면 설계가 완전히 달라집니다.

1. **SFT용 합성 (instruction → response)**  
   - 목표: 특정 포맷/절차/도메인 지식 적용을 “정답 시연”으로 주입
   - 위험: 환각이 들어가면 “자신감 있는 거짓말”을 학습

2. **Preference 데이터 (chosen vs rejected)**  
   - 목표: 같은 instruction에 대해 *좋은 답/나쁜 답* 쌍을 만들어 선호 최적화(DPO류) 또는 preference fine-tuning에 사용  
   - OpenAI도 preference 학습 데이터 소스로 **synthetic generation**을 명시합니다. ([openai.com](https://openai.com/index/o1-and-new-tools-for-developers/?utm_source=openai))  
   - 위험: rejected가 너무 쉬운(허술한) 답이면 학습 신호가 약해짐

3. **Adversarial/negative 합성 (공격/오류 유도)**  
   - 목표: 안전/정책/견고성 향상. 예: jailbreak 방어를 위해 “공격 프롬프트”를 합성하고 이를 분류기나 방어 계층 학습에 사용  
   - Anthropic은 **synthetic 데이터로 입력/출력 classifier를 학습**해 jailbreak에 대응하는 접근을 공개했습니다. ([anthropic.com](https://www.anthropic.com/news/constitutional-classifiers?id=18683&utm_source=openai))  
   - 최근에는 RLAIF 기반으로 *독성/위험 데이터*를 통제적으로 생성하는 연구도 나옵니다(적대적 데이터 생성의 자동화). ([arxiv.org](https://arxiv.org/abs/2604.17769?utm_source=openai))  

핵심은: **“합성”은 값싼 데이터가 아니라, ‘생성 규칙을 코드화한 데이터 생산 공정’**이라는 점입니다.

### 2) 내부 작동 방식: 생성→검증→필터링→평가→재생성 루프
실무적으로 가장 안정적인 파이프라인은 아래 흐름입니다.

1. **Seed 수집(현실 데이터)**  
   - 운영 로그(대화/툴 호출), 도메인 문서, FAQ, 티켓, SQL 쿼리, 정책 문서 등  
2. **Task spec 고정(스키마/정책/포맷)**  
   - “정답의 형태”를 JSON schema, function calling spec, 스타일 가이드로 고정  
3. **합성 생성(Teacher LLM)**  
   - 다양화 전략: paraphrase, edge case 확대, counter-example 생성, role-play(사용자 vs 시스템)  
4. **자동 검증/필터링(Programmatic + LLM-as-judge 혼합)**  
   - 규칙 검증: JSON parse, 스키마 체크, 금칙어/PII 탐지  
   - 의미 검증: 근거 문서 대비 consistency, retrieval 기반 fact-check  
   - 중복 제거/다양성 확보  
   - 최근 연구/실무 모두 “필터링”을 핵심으로 봅니다(합성 데이터 필터링 기법 연구도 활발). ([aclanthology.org](https://aclanthology.org/2025.findings-naacl.299.pdf?utm_source=openai))  
5. **Evals로 품질 측정 → 부족한 slice만 재생성**  
   - OpenAI가 강조하는 것처럼, 튜닝은 evals와 함께 “플라이휠”로 돌아가야 합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning?utm_source=openai))  

이 구조가 중요한 이유는, 합성 데이터의 최대 리스크인 **“환각의 체계적 증폭”**을 *검증/필터링/평가*가 제동 걸어주기 때문입니다.

### 3) 다른 접근과의 차이점: “prompt engineering” vs “data engineering”
- Prompt engineering은 **단발성 품질**을 올리지만, 데이터 생산을 “반복 가능한 공정”으로 만들지 못합니다.
- 반면 합성 파이프라인은:
  - 생성 정책을 코드/설정으로 고정하고
  - 실패 케이스를 slice로 분류해
  - 필요한 부분만 재생성/재학습하는 구조라서  
**장기적으로 비용과 안정성이 더 좋습니다.**

---

## 💻 실전 코드
아래 예제는 “현실적인 시나리오”로 **고객지원 티켓 로그(원문) → 합성 QA + 툴 호출 스타일 응답 → 자동 검증/필터링 → OpenAI fine-tuning jsonl 생성**까지 한 번에 연결합니다.  
(실제 운영에선 여기에 eval 세트/대시보드가 추가됩니다.)

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install "openai>=1.0.0" pydantic jsonschema tqdm python-dotenv
export OPENAI_API_KEY="YOUR_KEY"
```

### 1) 입력(현실 데이터) 예시
`tickets.jsonl` (운영에서 추출한 티켓/대화 요약본이라고 가정)
```json
{"ticket_id":"T-10492","product":"payments","lang":"ko","issue":"결제 승인 후 즉시 취소했는데 카드사에 승인 내역이 남아있어요","metadata":{"plan":"pro","channel":"email"}}
{"ticket_id":"T-10501","product":"auth","lang":"ko","issue":"SAML 로그인 시 간헐적으로 무한 리다이렉트가 발생합니다","metadata":{"plan":"enterprise","channel":"slack"}}
```

### 2) 합성 데이터 생성 + 검증/필터링 + FT 파일 생성
- 생성 산출물 스키마를 강제(JSON)
- 규칙 기반 검증(필수 필드/길이/PII 간단 탐지)
- “쉬운 rejected”를 막기 위해 chosen/rejected를 모두 일정 품질 이상으로 만들고, 차이를 “미묘하지만 결정적”으로 설계

```python
import os, json, re
from typing import List, Dict, Any
from tqdm import tqdm
from pydantic import BaseModel, Field
from jsonschema import validate, ValidationError
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ---- (A) 합성 데이터 스키마 정의 ----
SAMPLE_SCHEMA = {
  "type": "object",
  "required": ["instruction", "context", "chosen", "rejected", "tags"],
  "properties": {
    "instruction": {"type": "string", "minLength": 30},
    "context": {"type": "object"},
    "chosen": {"type": "string", "minLength": 80},
    "rejected": {"type": "string", "minLength": 80},
    "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1}
  }
}

PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),        # SSN 형태(예시)
    re.compile(r"\b\d{2,4}-\d{3,4}-\d{4}\b"),    # 전화번호 형태(예시)
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")  # 이메일
]

def has_pii(text: str) -> bool:
    return any(p.search(text) for p in PII_PATTERNS)

def to_ft_jsonl_preference(sample: Dict[str, Any]) -> Dict[str, Any]:
    """
    Preference fine-tuning용 (chosen, rejected) 레코드로 변환.
    OpenAI가 preference 학습을 별도로 안내/제공하는 흐름을 전제로 한 포맷 예시.
    """
    return {
        "input": [
            {"role": "system", "content": "You are a senior support engineer. Follow policy and be precise."},
            {"role": "user", "content": sample["instruction"]},
            {"role": "user", "content": f"Context(JSON): {json.dumps(sample['context'], ensure_ascii=False)}"},
        ],
        "preferred_output": sample["chosen"],
        "non_preferred_output": sample["rejected"]
    }

# ---- (B) Teacher LLM으로 합성 생성 ----
GEN_PROMPT = """
너는 SaaS 고객지원/개발지원 데이터 엔지니어다.
주어진 티켓 이슈를 바탕으로 파인튜닝용 preference 데이터 1개를 생성한다.

요구사항:
- 반드시 JSON 하나로만 출력
- instruction: 실제 고객이 보낼 법한 요청(한국어), 재현 가능한 정보 포함
- context: 제품/플랜/채널/가정한 로그 단서 등 구조화
- chosen: "좋은 답변" (진단 절차, 재현 방법, 원인 후보, 다음 액션, 필요 로그 요청, 안전한 가정 명시)
- rejected: "그럴듯하지만 나쁜 답변" (핵심 확인 없이 단정/누락/비현실적 조치/정책 위반/모호함 중 2개 이상 포함)
- chosen/rejected 둘 다 동일한 톤(정중/전문적)이되, chosen이 더 신뢰 가능해야 함
- 개인정보/민감정보는 만들지 말 것
- tags: ["product:...", "task:troubleshooting", "lang:ko"] 같은 형태

티켓:
{ticket_json}
"""

def generate_one(ticket: Dict[str, Any]) -> Dict[str, Any]:
    prompt = GEN_PROMPT.format(ticket_json=json.dumps(ticket, ensure_ascii=False))
    resp = client.responses.create(
        model="gpt-4.1-mini-2025-04-14",
        input=prompt,
        temperature=0.6,
    )
    text = resp.output_text.strip()
    return json.loads(text)

# ---- (C) 검증/필터링 ----
def validate_sample(sample: Dict[str, Any]) -> List[str]:
    problems = []
    try:
        validate(instance=sample, schema=SAMPLE_SCHEMA)
    except ValidationError as e:
        problems.append(f"schema_error:{e.message}")

    joined = " ".join([sample.get("instruction",""), sample.get("chosen",""), sample.get("rejected","")])
    if has_pii(joined):
        problems.append("pii_detected")

    # rejected가 너무 짧거나 너무 노골적으로 나쁘면 학습 신호가 약해짐(실무에서 흔한 함정)
    if "모르겠습니다" in sample.get("rejected","") or "그냥" in sample.get("rejected",""):
        problems.append("rejected_too_obvious")

    # chosen이 과도한 확신(단정)으로 환각을 유발할 수 있는 표현 탐지(간단 규칙)
    if any(phrase in sample.get("chosen","") for phrase in ["100% 확실", "무조건", "절대"]):
        problems.append("overconfident_chosen")

    return problems

def build_dataset(tickets_path: str, out_ft_path: str, n_per_ticket: int = 3):
    tickets = [json.loads(line) for line in open(tickets_path, "r", encoding="utf-8")]
    kept = 0
    total = 0

    with open(out_ft_path, "w", encoding="utf-8") as f_out:
        for t in tqdm(tickets, desc="tickets"):
            for _ in range(n_per_ticket):
                total += 1
                try:
                    sample = generate_one(t)
                    problems = validate_sample(sample)
                    if problems:
                        continue

                    ft_record = to_ft_jsonl_preference(sample)
                    f_out.write(json.dumps(ft_record, ensure_ascii=False) + "\n")
                    kept += 1
                except Exception:
                    continue

    print(f"generated={total}, kept={kept}, keep_rate={kept/total:.2%}")

if __name__ == "__main__":
    build_dataset("tickets.jsonl", "ft_preference.jsonl", n_per_ticket=5)
```

**예상 출력**
```bash
tickets: 100%|██████████| 2/2 [00:12<00:00,  6.10s/it]
generated=10, kept=6, keep_rate=60.00%
```

여기서 `keep_rate`가 너무 낮으면 “프롬프트 개선”보다 먼저:
- 스키마/규칙이 과도하게 빡센지
- rejected 품질 규칙이 현실적인지
- seed 티켓이 너무 짧아 instruction 생성이 불안정한지  
부터 점검하는 게 보통 더 효과적입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (현업에서 효과 큰 것 3가지)
1) **운영 분포를 강제로 맞춰라 (refusal/난이도/길이/툴 호출 비율)**
- OpenAI가 예로 드는 것처럼, 학습 데이터에서 거절 비율이 과도하면 운영에서도 과도 거절로 튀는 문제가 생깁니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))  
- 해결: slice별로 목표 비율을 정하고(예: “추가정보 요청 20%”) 생성 단계에서 컨트롤

2) **“생성”보다 “필터링/검증”에 예산을 써라**
- 합성 데이터는 양이 아니라 **정확도/다양성/정합성**이 승부처입니다.
- 최근에는 합성 데이터 필터링을 별도 기법으로 연구할 정도로 중요해졌습니다. ([aclanthology.org](https://aclanthology.org/2025.findings-naacl.299.pdf?utm_source=openai))  
- 팁: 규칙 검증(스키마) + LLM judge(루브릭) + retrieval fact-check를 조합

3) **Evals를 먼저 만들고, 부족한 slice만 재생성하는 “데이터 플라이휠”**
- OpenAI 문서가 강조하듯, 튜닝은 evals와 함께 반복해야 합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning?utm_source=openai))  
- 실무 팁: “모델이 틀리는 케이스 유형 taxonomy”를 만들고, 그 taxonomy를 tags로 데이터에 박아두면 재생성이 쉬워집니다.

### 흔한 함정/안티패턴
- **교사 모델(teacher)의 말투/서술 습관을 학생 모델(student)이 그대로 복제**  
  → 해결: style randomization(말투/구조 템플릿 여러 개), 다중 teacher(서로 다른 모델/프롬프트), 그리고 “너무 문학적인 답” 같은 패턴을 필터링
- **rejected를 너무 쓰레기로 만들기**  
  → DPO류에서는 “미묘한 차이”가 학습 신호가 됩니다. rejected가 너무 쉽게 구분되면 실제 품질 향상 폭이 작습니다.
- **도메인 사실 검증 없이 SFT로 밀어붙이기**  
  → 특히 법/정책/가격/한도 등은 환각이 곧 장애입니다. retrieval 기반 검증(근거 문서 링크/스니펫)을 파이프라인에 넣어야 합니다.

### 비용/성능/안정성 트레이드오프
- **큰 모델로 생성(비용↑) + 강한 필터링(비용↑) + 작은 모델 튜닝(추론비용↓)** 조합이 총소유비용(TCO) 관점에서 유리한 경우가 많습니다.
- 반대로, 생성 비용을 아끼려고 작은 모델로 대량 생성하면 **노이즈가 늘어 필터링/재학습 비용이 폭증**할 수 있습니다.

---

## 🚀 마무리
2026년 4월 기준 “LLM 합성 데이터”는 더 이상 트릭이 아니라, **파인튜닝용 데이터 구축의 표준 공정**에 가깝습니다. 핵심은:
- 합성 데이터는 **생성**이 아니라 **파이프라인(검증/필터링/evals)** 이다
- SFT / preference / adversarial을 목적별로 분리 설계해야 한다
- 운영 분포를 맞추지 않으면(거절/길이/난이도/툴 호출) 튜닝이 오히려 망가질 수 있다 ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))

**도입 판단 기준**
- (도입 OK) 운영 로그/도메인 문서가 있고, 이를 “학습 포맷”으로 바꾸는 게 병목인 팀
- (도입 보류) eval이 없고, 데이터 품질을 자동으로 걸러낼 장치가 없는 팀

**다음 학습 추천**
- OpenAI fine-tuning best practices와 “evals+fine-tuning 플라이휠” 가이드를 먼저 정독하고, 데이터 분포/품질 체크리스트를 팀 표준으로 만드는 것을 추천합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))  
- 안전/적대적 합성 데이터까지 고려한다면, synthetic data로 방어 계층을 학습하는 접근(예: classifier 학습) 사례도 함께 보는 게 좋습니다. ([anthropic.com](https://www.anthropic.com/news/constitutional-classifiers?id=18683&utm_source=openai))

원하시면 위 파이프라인을 당신의 도메인에 맞춰 **(1) RAG 근거 기반 fact-check 포함 버전**, **(2) DPO용 “난이도 스케줄링”**, **(3) 운영 트레이스 → 학습 데이터 자동 변환(MLOps)** 형태로 확장한 설계안을 추가로 작성해드릴게요.