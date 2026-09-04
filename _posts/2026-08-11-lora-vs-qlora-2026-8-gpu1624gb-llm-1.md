---
title: "LoRA vs QLoRA: “내 GPU(16~24GB)로 LLM 파인튜닝을 끝내는” 실전 튜토리얼"
description: "LLM fine-tuning의 현실 문제는 간단합니다. 성능을 올리고 싶지만, 풀 파인튜닝(Full FT)은 VRAM/비용/운영 복잡도가 너무 크다는 것. LoRA/QLoRA는 이 지점에서 “가성비 좋은 커스터마이징”을 제공합니다."
date: 2026-08-11 02:11:45 +0900
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
LLM fine-tuning의 현실 문제는 간단합니다. **성능을 올리고 싶지만, 풀 파인튜닝(Full FT)은 VRAM/비용/운영 복잡도가 너무 크다**는 것. LoRA/QLoRA는 이 지점에서 “가성비 좋은 커스터마이징”을 제공합니다. 핵심은 **기존 LLM 가중치는 거의 그대로 두고(동결) 작은 adapter만 학습**한다는 점입니다(PEFT).[^1]

언제 쓰면 좋나:
- **도메인/스타일/포맷 적응**(예: 고객센터 톤, 사내 문서 기반 답변 포맷, text-to-SQL, 리포트 템플릿)처럼 “베이스 능력은 충분한데 출력 습관을 바꾸고 싶은” 경우
- 1~2장의 GPU(특히 16~24GB)로 **반복 실험**해야 하는 경우(QLoRA가 특히 유리)
- 배포 시 “베이스 모델은 공용 + adapter만 교체” 같은 운영 패턴이 필요한 경우(모델 버전 관리가 쉬움)

언제 쓰면 안 되나:
- 데이터가 매우 많고(수백만~수천만 샘플) 목표가 **모델 능력 자체를 재학습**하는 수준이면(사실상 continued pretraining) LoRA만으로는 한계가 빠르게 옵니다.
- “모델이 특정 사실을 절대적으로 외우길” 기대하는 경우: SFT/LoRA는 **기억 저장 장치가 아니라 분포 이동**에 가깝고, RAG/툴/평가 파이프라인이 함께 설계돼야 합니다.

---

## 🔧 핵심 개념
### 주요 개념 정의
- **LoRA (Low-Rank Adaptation)**: 선형층의 가중치 업데이트(ΔW)를 직접 학습하지 않고, **저랭크 분해(BA)** 형태의 작은 행렬만 학습합니다. 즉, W는 동결하고 ΔW=BA만 학습 → 학습 파라미터/메모리/저장 크기 급감.
- **QLoRA**: LoRA는 그대로 두되, **베이스 모델 가중치를 4-bit로 quantize해서 로딩**하고(동결), 역전파는 LoRA adapter로만 흘립니다. 그래서 “LoRA + 4-bit base”라고 생각하면 됩니다.[^1]

### 내부 작동 방식(흐름)
1) **Base model 로딩**
- LoRA: 보통 base를 FP16/BF16로 로딩
- QLoRA: base를 bitsandbytes로 **4-bit NF4**(권장)로 로딩  
  - NF4는 가중치 분포(대체로 0 근처에 몰림)에 맞춘 4-bit 포맷이라는 설명이 널리 쓰입니다.[^2]
  - **Double Quantization**: quantization에 필요한 상수(스케일 등)도 한 번 더 압축해 메모리를 줄입니다.[^2]

2) **학습 시 forward**
- base weight는 4-bit로 저장되어 있다가 연산 시 내부적으로 디퀀타이즈/커널을 거쳐 사용
- 해당 linear 모듈에 LoRA가 붙어 있으면 `Linear(x) + LoRA(x)` 형태로 결과가 합쳐짐

3) **학습 시 backward**
- base weight는 동결이므로 gradient/optimizer state를 거의 만들지 않음
- **LoRA 파라미터만 optimizer가 관리** → 메모리/속도 이점이 큼

4) **메모리 스파이크 관리**
- QLoRA 쪽에서 자주 언급되는 “paged optimizers”는 **피크 메모리** 문제를 줄이기 위한 아이디어로 알려져 있고, Hugging Face 쪽에서도 QLoRA 혁신 요소로 반복 소개됩니다.[^2]

### 다른 접근과의 차이점(프로젝트 관점)
- Full FT: 성능 잠재력은 크지만 비용/운영 난이도가 큼
- LoRA: 품질-비용 균형이 좋고 안정적. 다만 base를 FP16로 들고 가면 VRAM이 더 듦
- **QLoRA**: LoRA 품질을 크게 잃지 않으면서 **VRAM을 더 공격적으로 줄임**(특히 7B~13B에서 체감). Hugging Face/PEFT 문서도 “큰 모델을 단일 GPU에서”라는 포인트로 설명합니다.[^3]

---

## 💻 실전 코드
현실적인 시나리오: **사내 로그/이벤트를 받아 운영자가 바로 실행 가능한 “Incident Summary + Action Items”를 생성**하는 LLM을 만든다고 가정합니다.  
데이터는 내부 포맷(JSONL)로 이미 쌓여 있고, “답변 스타일/구조”를 맞추는 게 목적이므로 SFT + QLoRA가 잘 맞습니다.

아래 코드는 Hugging Face TRL의 `SFTTrainer` + PEFT(LoRA) + bitsandbytes(4-bit)를 사용합니다. TRL은 PEFT/QLoRA 통합 가이드를 공식 문서로 제공합니다.[^4]

### 1) 초기 셋업
```bash
# CUDA 환경 가정
python -m venv .venv
source .venv/bin/activate

pip install -U "transformers>=4.44" "trl>=0.11" "datasets>=2.20" "accelerate>=0.33" \
  "peft>=0.14" "bitsandbytes>=0.43" "torch" "sentencepiece"

# (권장) 실험 추적이 필요하면 MLflow 같은 도구도 고려
pip install -U mlflow
```

### 2) 데이터 준비(현업형 포맷)
`train.jsonl` 예시(한 줄에 하나):
- `prompt`: 내부 시스템 이벤트(알람/로그) + 운영 컨텍스트
- `response`: 우리가 원하는 포맷(요약/원인/조치/재발방지)

```json
{"prompt":"[service]=payments-api\n[severity]=P1\n[signal]=latency p95 4.2s\n[context]=deploy v2.31 12:03 UTC, spike after deploy\n[logs]=...","response":"## Incident Summary\n...\n## Root Cause Hypothesis\n...\n## Immediate Actions\n...\n## Follow-ups\n..."}
```

### 3) QLoRA로 SFT 실행
```python
import os
import torch
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig

BASE_MODEL = os.environ.get("BASE_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")  # 예시
DATA_PATH = os.environ.get("DATA_PATH", "train.jsonl")
OUT_DIR = os.environ.get("OUT_DIR", "./out-qlora-incident")

# 4-bit QLoRA 로딩 설정 (NF4 + Double Quant)
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16,  # GPU 지원 시 BF16 권장
)

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
)

# k-bit training 준비: layernorm 캐스팅/gradient checkpointing 친화 설정 등
model = prepare_model_for_kbit_training(model)

# LoRA 타겟 레이어는 모델 계열마다 다름.
# (Mistral/Llama 계열은 보통 q_proj/k_proj/v_proj/o_proj에 많이 적용)
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
)

ds = load_dataset("json", data_files=DATA_PATH, split="train")

def format_example(e):
    # “toy”를 피하려면 실제 운영 프롬프트 구조(헤더/구분자/규칙)를 고정하는 게 중요
    return f"""<incident_prompt>
{e['prompt']}
</incident_prompt>

<expected_response>
{e['response']}
</expected_response>"""

training_args = SFTConfig(
    output_dir=OUT_DIR,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,  # 24GB 이하에서 자주 필요
    learning_rate=2e-4,
    num_train_epochs=2,
    logging_steps=10,
    save_steps=200,
    bf16=True,
    max_seq_length=2048,
    optim="paged_adamw_8bit",  # QLoRA에서 흔히 쓰는 선택지
    warmup_ratio=0.03,
    lr_scheduler_type="cosine",
    report_to="none",
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=ds,
    peft_config=lora_config,
    args=training_args,
    formatting_func=format_example,
)

trainer.train()
trainer.save_model(OUT_DIR)

print("Saved to:", OUT_DIR)
print("Tip: base model + adapter를 분리 배포할지, merge할지 결정하세요.")
```

예상 출력(요지):
- step 로그(loss)
- `./out-qlora-incident/`에 adapter 체크포인트 저장

참고: TRL의 `SFTTrainer`는 QLoRA/LoRA 워크플로를 문서화했고, PEFT 통합도 공식 지원합니다.[^5]

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **“무엇을 학습시킬지”를 좁히고, 포맷을 고정하라**
- QLoRA는 특히 “스타일/포맷/도메인 용어”에 강합니다.  
  Incident 요약처럼 출력 구조가 중요하면, 프롬프트에 `<incident_prompt> ... </incident_prompt>` 같은 **구분자/템플릿을 강제**하면 재현성이 크게 올라갑니다.

2) target_modules는 “많이”가 아니라 “맞게”
- 무작정 모든 linear에 LoRA를 붙이면 VRAM/학습 불안정/과적합 위험이 늘어납니다.
- Llama/Mistral 계열은 attention의 `q_proj/k_proj/v_proj/o_proj`가 출발점으로 자주 쓰입니다(문서/사례에서도 반복).[^6]

3) VRAM이 빡빡하면 **sequence length와 accumulation**부터 조절
- batch를 올리려다 OOM 나는 경우가 대부분입니다.
- `per_device_train_batch_size=1` + `gradient_accumulation_steps`로 “유효 배치”만 확보하는 패턴이 실무에선 더 안전합니다.

### 흔한 함정/안티패턴
- **평가 없이 “loss만 보고 성공” 선언**
  - 실제로는 포맷 붕괴, 환각 증가, 특정 케이스에서만 잘 되는 문제가 흔합니다.
  - 최소한: held-out 로그로 **정형 평가(템플릿 준수율, 금지어, 길이, action item 개수 등)** + 운영자 블라인드 리뷰를 같이 하세요.
- **4-bit 로딩/커널/버전 이슈를 무시**
  - bitsandbytes/ROCm/드라이버 조합에 따라 동작이 갈릴 수 있고, 릴리즈 노트에도 QLoRA 관련 수정이 꾸준히 올라옵니다.[^7]

### 비용/성능/안정성 트레이드오프
- QLoRA는 “학습 가능하게 만든다”는 점에서 압도적이지만, 결국 4-bit 경로(디퀀타이즈/커널)가 병목이 될 수 있고 이에 대한 연구도 계속 나옵니다.[^8]  
- 안정성이 최우선이면:
  - (A) LoRA + BF16(베이스 FP16/BF16)로 가고 GPU를 더 쓰거나
  - (B) QLoRA로 가되 실험/검증/버전 고정을 엄격히 하세요.

---

## 🚀 마무리
정리하면:
- **LoRA**는 “학습 파라미터만 줄여서” 비용을 낮추는 선택
- **QLoRA**는 거기에 더해 “베이스를 4-bit로 내려” **단일 GPU 실험 가능성**을 크게 올리는 선택입니다.[^1]

도입 판단 기준(실무 체크리스트):
- 내 목적이 “지식 추가”보다 **출력 포맷/도메인 톤/업무 스타일 적응**인가?
- GPU가 16~24GB급이고 반복 실험이 중요한가? → 그렇다면 QLoRA 우선
- 배포에서 adapter 교체 전략이 유용한가? (팀/고객별 커스텀) → LoRA/QLoRA 강력 추천
- 검증 체계를 갖출 수 있는가? (템플릿 준수율, 실패 케이스 카탈로그, 릴리즈 게이트)

다음 학습 추천:
- TRL의 SFTTrainer + PEFT 통합 문서를 먼저 읽고, 실 데이터 포맷에 맞춰 collator/템플릿을 다듬으세요.[^5]
- PEFT의 k-bit/quantization 가이드를 통해 `prepare_model_for_kbit_training`이 무엇을 바꾸는지(왜 필요한지) 확인하면 디버깅 속도가 빨라집니다.[^3]

원하시면, (1) 사용 GPU(VRAM), (2) 대상 모델(예: Llama 3.x / Qwen / Gemma), (3) 데이터 형태(대화/문서→요약/SQL/분류) 를 알려주시면, 위 코드를 **당신 프로젝트에 맞는 설정값(r/alpha/target_modules/seq_len/optimizer)**으로 구체적으로 튜닝해서 제안하겠습니다.

[^1]: <https://arxiv.org/abs/2305.14314>
[^2]: <https://huggingface.co/blog/4bit-transformers-bitsandbytes>
[^3]: <https://huggingface.co/docs/peft/v0.14.0/developer_guides/quantization>
[^4]: <https://huggingface.co/docs/trl/en/peft_integration>
[^5]: <https://huggingface.co/docs/trl/v0.11.4/en/sft_trainer>
[^6]: <https://www.rsc.org/suppdata/d6/cc/d6cc00581k/d6cc00581k1.pdf>
[^7]: <https://github.com/bitsandbytes-foundation/bitsandbytes/releases>
[^8]: <https://arxiv.org/abs/2604.02556>
