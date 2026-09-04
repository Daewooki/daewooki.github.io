---
title: "합성 데이터로 LLM을 ‘내 도메인 전문가’로 만드는 법: 2026년식 Synthetic Data 생성·정제·파인튜닝 실전 레시피"
description: "LLM 파인튜닝이 막히는 지점은 대부분 “학습시킬 데이터가 없다”가 아니라 “내 제품에서 실제로 실패하는 케이스를 커버하는 학습 데이터가 없다”입니다. 로그는 쌓이는데 정답 라벨이 없고, 사람 라벨링은 비싸고 느립니다."
date: 2026-08-19 01:44:00 +0900
categories: [AI, Data]
tags: [ai, data]
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
LLM 파인튜닝이 막히는 지점은 대부분 “학습시킬 데이터가 없다”가 아니라 **“내 제품에서 실제로 실패하는 케이스를 커버하는 학습 데이터가 없다”**입니다. 로그는 쌓이는데 정답 라벨이 없고, 사람 라벨링은 비싸고 느립니다. 이때 2026년 현재 가장 실용적인 해법이 **LLM synthetic data(합성 데이터)**로 학습용 데이터셋을 구축하고, 작은 모델/사내 모델을 도메인에 맞게 **SFT + preference 최적화(DPO 등)**로 밀어붙이는 방식입니다. (Llama 3.1 계열이 “출력으로 다른 모델을 개선하는” 사용을 허용하면서 이 흐름이 더 대중화되었습니다.[^1])

언제 쓰면 좋나:
- **라벨이 부족하지만 입력 분포는 명확**(예: 고객 문의, 티켓, 콜센터 요약, 사내 문서 Q&A, 특정 포맷 변환)
- **정답을 규칙/근거로 검증할 수 있음**(예: 데이터 추출 결과가 원문에 “존재해야 함”, JSON schema 준수, 계산 검증)
- **prompting으로는 한계**(비용/지연/안정성)라서 작은 모델로 내리고 싶을 때

언제 쓰면 안 되나:
- 합성 데이터의 정답을 **검증할 방법이 없고** “그럴듯함”으로만 통과시키는 경우(환각이 라벨로 굳습니다)
- 데이터가 모델에 **그대로 역증류(distillation)**되면 안 되는 고위험 환경(정책/보안/경쟁 리스크). 실제로 대규모 distillation 공격/방어가 2026년에도 중요한 이슈로 다뤄집니다.[^2]
- “모델이 모르는 걸 알게 만들기”가 목적일 때(합성 데이터는 결국 **교사 모델이 아는 범위**에서 강해지는 경우가 많음)

---

## 🔧 핵심 개념
### 주요 개념 정의
- **Synthetic data for SFT**: 교사 LLM이 만든 (prompt, response) 쌍으로 학생 모델을 **cross-entropy**로 학습.
- **Preference data / DPO**: (chosen, rejected) 쌍으로 “어떤 답을 선호하는지”를 학습. Llama 계열 post-training에서도 SFT 다음 DPO를 쓰는 흐름이 일반적입니다.[^3]
- **RLAIF / Constitutional AI 스타일 생성**: 규칙(“constitution”)을 주고 **critique→revision**으로 더 안전/정책준수한 답을 만들며 그 과정 자체를 데이터로 저장(예: classifier/정책 데이터). Anthropic은 constitution 기반 synthetic data로 classifier를 학습했다고 공개했습니다.[^4]
- **Distillation(실무적 의미)**: 엄밀한 “soft label/logits distillation”이 아니라, 현실에선 **큰 모델 출력으로 작은 모델을 강화**(synthetic Q/A, reasoning trace, preference pair 등)하는 운영 패턴을 통칭하는 경우가 많습니다(문서/커뮤니티에서 용어 혼재).

### 내부 작동 방식(구조/흐름)
실무 파이프라인은 보통 아래 “플라이휠”로 굴립니다.

1) **Seed 수집(현실 데이터)**  
   - 제품 로그/티켓/문서/대화에서 대표 입력을 뽑습니다.
   - 여기서 중요한 건 “랜덤 샘플”이 아니라 **실패/재시도/클레임 케이스를 과대표집**하는 것(나중에 성능이 체감됩니다).  

2) **Teacher로 합성 생성(다양성/난이도 제어)**  
   - 한 번에 정답만 뽑지 말고, 생성물에 **메타데이터(난이도, 근거, 추출 위치, 타입)**를 붙이면 필터링/커리큘럼이 가능해집니다. 임상 정보 추출 논문도 합성 Q/A에 섹션/근거/난이도/설명을 함께 넣어 품질을 끌어올립니다.[^5]

3) **검증(자동 채점 + 샘플 휴먼 리뷰)**  
   - 합성 데이터의 핵심은 “생성”이 아니라 **게이트(quality gate)**입니다.
   - 형식 검증(JSON schema), 근거 검증(원문 substring/스팬), consistency check(동일 질문 다중 샘플링), LLM-as-judge 등을 조합합니다. OpenAI 쪽도 eval harness/그레이더를 붙여 “평가 플라이휠”로 운영하는 접근을 지속적으로 강조합니다.[^6]

4) **학습(SFT → Preference 최적화 → 재평가)**  
   - SFT로 “형식/도메인 언어”를 먼저 잡고,
   - 그 다음 DPO(또는 ORPO 등)로 “우리 팀이 원하는 답의 스타일/정책/우선순위”를 고정합니다. (Meta 모델 카드에서도 synthetic + vendor human 데이터 혼합, DPO 사용을 언급합니다.[^3])

### 다른 접근과의 차이점
- **Prompt engineering vs 합성+FT**: 프롬프트는 빠르고 싸게 시작하지만, 트래픽이 커지면 비용/지연이 커지고 케이스별 안정성(회귀)이 어렵습니다. 합성+FT는 초기 투자(파이프라인)가 크지만 **단위 비용과 일관성**이 좋아집니다.
- **RAG vs 합성+FT**: RAG는 “지식 최신성/근거”에 강하지만, “출력 포맷/업무 절차 준수” 같은 행동 학습에는 한계가 있습니다. 합성 데이터는 바로 그 **절차/정책/형식**을 학습시키는 데 유리합니다.
- **휴먼 라벨링 vs 합성**: 휴먼 라벨은 최강이지만 비싸고 느립니다. 합성은 싸고 빠르지만 편향/환각이 섞입니다. 결론은 보통 **소량의 human gold + 대량 synthetic + 강한 eval** 조합입니다.

---

## 💻 실전 코드
시나리오: “사내 고객지원 티켓을 분류하고, 답변 초안을 만드는” 모델을 만들고 싶습니다.  
목표는 (1) **합성 티켓 생성 + 답변 초안** 데이터셋 구축, (2) **자동 검증**, (3) **SFT용 JSONL**로 내보내기입니다.  
(학습 자체는 조직마다 스택이 달라 여기서는 데이터 구축에 집중하되, 바로 FT에 넣을 수 있는 포맷으로 뽑습니다.)

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install "pydantic>=2" "jsonschema>=4" tenacity tqdm openai
export OPENAI_API_KEY="..."
```

### 1) 데이터 스키마 + 검증 규칙(현실적인 게이트)
- 출력은 반드시 JSON
- `category`는 고정된 taxonomy
- `reply_draft`는 “정책 문구/금지 문구” 체크
- `evidence`는 티켓 본문에서 substring으로 존재해야 함(환각 방지용 최소 장치)

```python
# build_synth_dataset.py
import json, re
from typing import List, Literal
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, wait_exponential, stop_after_attempt
from tqdm import tqdm

from openai import OpenAI

client = OpenAI()

Category = Literal[
    "billing_refund", "account_login", "bug_report", "feature_request",
    "security_privacy", "howto"
]

class TicketSynth(BaseModel):
    ticket_id: str = Field(..., description="uuid-like id")
    language: Literal["ko"] = "ko"
    product: str
    user_tier: Literal["free", "pro", "enterprise"]
    subject: str
    body: str
    category: Category
    evidence: List[str] = Field(..., description="body에 존재하는 근거 문장/구절 리스트")
    reply_draft: str
    severity: Literal["low", "medium", "high"]
    tags: List[str]

BANNED_PATTERNS = [
    r"내부 정책상.*알 수 없습니다",     # 과도한 회피
    r"법적 조언",                     # 법률 자문 오해 소지
    r"비밀번호를 알려",               # 보안 위험
]

def evidence_is_grounded(body: str, evidence: List[str]) -> bool:
    body_norm = re.sub(r"\s+", " ", body)
    for ev in evidence:
        ev_norm = re.sub(r"\s+", " ", ev).strip()
        if len(ev_norm) < 10:
            return False
        if ev_norm not in body_norm:
            return False
    return True

def reply_is_safe(reply: str) -> bool:
    for pat in BANNED_PATTERNS:
        if re.search(pat, reply):
            return False
    return True

SCHEMA_HINT = {
  "type": "object",
  "required": ["ticket_id","product","user_tier","subject","body","category","evidence","reply_draft","severity","tags"],
  "additionalProperties": True
}

SYSTEM = """You are a senior support engineer.
Generate realistic Korean customer support tickets and high-quality reply drafts.
Output MUST be valid JSON only. No markdown.
Rules:
- evidence: list of exact substrings copied from body (grounding).
- reply_draft: actionable steps, ask for missing info, no policy-evasion.
- Use categories from the provided taxonomy only.
"""

TAXONOMY = """taxonomy:
- billing_refund: 결제/환불/영수증
- account_login: 로그인/2FA/계정 잠금
- bug_report: 재현 가능한 오류/크래시/로그
- feature_request: 기능 제안
- security_privacy: 데이터 삭제/권한/보안 이슈
- howto: 사용 방법"""

@retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(4))
def generate_one(seed_context: str) -> TicketSynth:
    resp = client.responses.create(
        model="gpt-5-mini",  # 조직에서 쓰는 최신/가성비 모델로 교체
        input=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"{TAXONOMY}\n\nGenerate 1 ticket JSON.\nContext:{seed_context}\nSchemaHint:{json.dumps(SCHEMA_HINT)}"}
        ],
        temperature=0.8,
    )

    text = resp.output_text
    obj = json.loads(text)
    item = TicketSynth.model_validate(obj)

    if not evidence_is_grounded(item.body, item.evidence):
        raise ValueError("Ungrounded evidence")
    if not reply_is_safe(item.reply_draft):
        raise ValueError("Unsafe/low-quality reply draft")

    return item

def to_sft_jsonl(items: List[TicketSynth], out_path: str):
    """
    OpenAI/일반 SFT에서 흔히 쓰는 chat format JSONL.
    (플랫폼마다 키는 다를 수 있으니, 아래 messages 구조만 유지하면 이식이 쉽습니다.)
    """
    with open(out_path, "w", encoding="utf-8") as f:
        for it in items:
            prompt = (
                "You are a helpful customer support assistant.\n"
                f"Product: {it.product}\n"
                f"UserTier: {it.user_tier}\n"
                f"Subject: {it.subject}\n"
                f"Body:\n{it.body}\n\n"
                "Task: classify category and write a reply draft.\n"
                "Return JSON with keys: category, reply_draft."
            )
            completion = json.dumps(
                {"category": it.category, "reply_draft": it.reply_draft},
                ensure_ascii=False
            )
            row = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": completion}
                ],
                "metadata": {
                    "severity": it.severity,
                    "tags": it.tags,
                    "evidence": it.evidence,
                    "ticket_id": it.ticket_id
                }
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    # seed_context는 “현실 분포”를 잡는 핵심. 실제로는 운영 로그에서 샘플링한 요약/클러스터를 넣는 걸 권장.
    seeds = [
        "최근 배포 이후 Windows 앱에서 로그인 후 무한 로딩, 콘솔 로그에 401 반복",
        "프로 요금제 결제는 됐는데 인보이스가 안 내려받아짐, 회계팀 제출 필요",
        "GDPR 관련 계정 삭제 요청, 데이터 보관 기간 문의",
        "새 기능: CSV 업로드 시 컬럼 매핑 자동 추천 요청"
    ]

    items: List[TicketSynth] = []
    for i in tqdm(range(60)):
        seed = seeds[i % len(seeds)]
        try:
            items.append(generate_one(seed))
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            # 실패 샘플은 버리지 말고 별도 로그로 쌓아 “생성 프롬프트/게이트”를 개선하는 재료로 씁니다.
            continue

    to_sft_jsonl(items, "support_synth_sft.jsonl")
    print(f"saved: {len(items)} rows -> support_synth_sft.jsonl")
```

예상 출력:
```text
saved: 47 rows -> support_synth_sft.jsonl
```

### 2) 확장: preference(DPO)용 pair 만들기(critique→revision)
Constitutional AI/RLAIF 계열의 핵심은 “규칙 기반 critique→revision”로 **chosen(수정 후)**, **rejected(수정 전)** 쌍을 만들 수 있다는 점입니다. (Anthropic의 Constitutional AI는 RLAIF 개념을 정리했고[^7], synthetic data로 classifier를 학습하는 사례도 공개했습니다.[^4])

아래는 같은 티켓에 대해 “초안 → 규칙으로 비평 → 개선안”을 생성해 pair를 저장하는 뼈대입니다(학습은 TRL 등으로 진행).

```python
# make_preference_pairs.py
import json
from openai import OpenAI
client = OpenAI()

CONSTITUTION = """
You must:
- Ask for reproduction steps/logs when bug_report.
- Never request passwords or secrets.
- Provide clear next actions and what you need from user.
- If uncertain, say what you can do and what info is missing.
"""

def make_pair(ticket_prompt: str):
    # 1) draft
    draft = client.responses.create(
        model="gpt-5-mini",
        input=[{"role":"user","content": ticket_prompt + "\nWrite reply draft."}],
        temperature=0.7,
    ).output_text

    # 2) critique + revision
    revised = client.responses.create(
        model="gpt-5-mini",
        input=[
            {"role":"system","content": f"Apply these rules:\n{CONSTITUTION}"},
            {"role":"user","content": f"Original reply:\n{draft}\n\nCritique then provide improved reply."}
        ],
        temperature=0.4,
    ).output_text

    return draft, revised

if __name__ == "__main__":
    prompt = "User ticket: 로그인 후 무한 로딩, 401 반복. 환경: Windows 11, 앱 v2.3.1"
    rejected, chosen = make_pair(prompt)

    row = {"prompt": prompt, "chosen": chosen, "rejected": rejected}
    with open("support_pref.jsonl","a",encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **합성 데이터는 “생성”이 아니라 “평가/게이트”가 성패를 가릅니다**  
   - LLM-as-judge를 쓰더라도 *judge가 속는 패턴*이 있습니다. OpenAI가 “elicitation(끌어내는 방식) 없이는 capability claim이 약하다”, “reward hacking” 같은 문제를 지적한 이유가 여기 있습니다.[^8]  
   - 최소한 **형식 검증 + 근거 검증 + 샘플 휴먼 리뷰** 3종은 넣으세요.

2) **커리큘럼(난이도/타입)과 “실패 케이스 과대표집”을 같이 굴리기**  
   - 쉬운 케이스만 잔뜩 만들면 모델이 “그럴듯한 템플릿”만 배웁니다.
   - 생성 단계에서 난이도/타입 태깅(앞서 임상 합성 데이터처럼)하면, 학습 배치를 의도적으로 섞을 수 있습니다.[^5]

3) **SFT 다음에 preference 최적화(DPO 등)로 ‘조직의 기준’을 고정**  
   - SFT는 스타일/형식을 빠르게 맞추지만, “우리가 싫어하는 답”을 밀어내는 데는 preference가 강합니다.
   - Meta Llama 계열도 SFT 후 DPO 같은 preference 단계와 synthetic 혼합을 언급합니다.[^3]

### 흔한 함정/안티패턴
- **Teacher의 말투/구조를 그대로 복제**: 모델이 “지원팀 특유의 말투”는 잘 따라하지만, 정작 제품 KPI(해결률/재문의율)는 안 오릅니다. → 반드시 운영 지표와 연결된 eval을 설계하세요.
- **합성 데이터 누수(정답이 프롬프트에 암시)**: “정답을 만들기 쉬운 템플릿”을 teacher에게 주면 데이터가 과하게 깨끗해지고, 실제 입력에서 무너집니다.
- **검증 없는 chain-of-thought 강제**: reasoning 텍스트를 정답처럼 학습시키면, 환각 reasoning이 “정답 패턴”이 되기도 합니다. 필요하면 reasoning은 숨기고(훈련에는 사용, 출력에는 금지) 혹은 근거 기반 형태로 제한하세요.

### 비용/성능/안정성 트레이드오프
- **Teacher 비용 vs 데이터 품질**: 고성능 teacher가 “한 방”에 더 좋은 라벨을 만들지만, 결국 통과율은 게이트가 결정합니다. 처음엔 teacher를 높이고, 파이프라인이 안정되면 teacher를 낮추는 전략이 현실적입니다.
- **FT vs 프롬프트 비용**: 트래픽이 커질수록 FT가 유리하지만, 제품이 자주 바뀌면(정책/기능/UX) 재학습 비용이 커집니다. 그래서 “평가 플라이휠” 자동화가 필수입니다.[^6]
- **보안/정책 리스크**: 합성 데이터 생성 자체가 “증류”로 간주되어 민감해질 수 있고, 공격/방어 관점에서도 반복 구조/대량 요청이 신호가 될 수 있습니다.[^2]

---

## 🚀 마무리
합성 데이터 기반 파인튜닝은 2026년에도 여전히 “가장 빨리 ROI가 나는” LLM 엔지니어링 패턴 중 하나지만, 성공 조건은 명확합니다.

- 도입하면 좋은 조건: **(a) 실패 케이스가 명확**, **(b) 자동 검증이 가능**, **(c) 평가 플라이휠을 돌릴 역량**이 있다.
- 도입을 보류할 조건: **정답 검증이 불가능**하거나, **데이터/정책 리스크가 큰데 통제가 없다**.

다음 학습/실행 추천(바로 프로젝트에 적용 순서):
1) “우리 제품의 30개 골든 케이스”를 만들고(휴먼)  
2) 그 케이스를 통과시키는 **합성 생성 프롬프트 + 게이트**를 만든 뒤  
3) SFT JSONL을 뽑아 작은 모델에 적용,  
4) 마지막으로 DPO용 preference pair를 추가해 “싫은 답”을 제거하세요.

[^1]: <https://github.com/huggingface/blog/blob/main/llama31.md>
[^2]: <https://www.anthropic.com/news/detecting-and-preventing-distillation-attacks?via=free>
[^3]: <https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/MODEL_CARD.md>
[^4]: <https://www.anthropic.com/research/next-generation-constitutional-classifiers?agency_tier=platinum>
[^5]: <https://pmc.ncbi.nlm.nih.gov/articles/PMC12065832/>
[^6]: <https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/Building_resilient_prompts_using_an_evaluation_flywheel.md>
[^7]: <https://arxiv.org/abs/2212.08073>
[^8]: <https://openai.com/index/trustworthy-third-party-evaluations-foundations/>
