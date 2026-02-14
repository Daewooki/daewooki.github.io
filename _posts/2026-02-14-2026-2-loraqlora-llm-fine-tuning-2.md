---
title: "2026년 2월 기준: LoRA/QLoRA로 LLM Fine-tuning을 “현실적으로” 끝내는 방법 (원리+실전)"
date: 2026-02-14 02:42:51 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-02]
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
LLM fine-tuning은 “성능은 좋은데 비용이 너무 비싸다”가 늘 문제였습니다. Full fine-tuning은 GPU 메모리/시간/비용이 기하급수로 커지고, 실무에서는 데이터도 충분히 크지 않은 경우가 많습니다. 그래서 2026년 2월에도 여전히 표준 해법은 **PEFT(Parameter-Efficient Fine-Tuning)**, 그중에서도 **LoRA/QLoRA**입니다.

- **LoRA**: base model weight는 고정(freeze)하고, 일부 Linear layer에 **저랭크(rank) adapter**만 학습해 파라미터/메모리를 크게 줄입니다.
- **QLoRA**: base model을 **4-bit quantization**으로 로드해 VRAM을 더 아끼고, 그 위에 LoRA adapter를 학습합니다. QLoRA는 NF4, double quantization, paged optimizer 등으로 메모리 효율을 극대화했습니다. ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))

결론적으로, “내 GPU 한 장(심지어 8~16GB)으로도” 최신 오픈웨이트 LLM을 업무용으로 커스터마이징하는 가장 현실적인 루트가 LoRA/QLoRA입니다.

---

## 🔧 핵심 개념
### 1) LoRA의 핵심 아이디어: ΔW를 저랭크로 근사
Transformer의 Linear weight를 \(W\)라 하면, LoRA는 학습 시 \(W\)를 직접 업데이트하지 않고 다음처럼 업데이트를 “우회”합니다.

- 원래: \(W \leftarrow W + \Delta W\)
- LoRA: \(\Delta W \approx \frac{\alpha}{r} AB\)  (A: in→r, B: r→out)  
즉, 큰 행렬 업데이트 대신 **작은 두 행렬(A, B)**만 학습합니다. 이때 **rank r**가 작을수록 학습 파라미터가 줄고, 표현력도 함께 줄어듭니다. 실무에서는 \( \alpha \)와 \( r \)의 비율(스케일링)이 중요하고, 경험적으로 `lora_alpha = r` 또는 `2*r` 같은 규칙이 널리 쓰입니다. ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide?utm_source=openai))

### 2) QLoRA: 4-bit로 base model을 “고정한 채” 역전파는 adapter로
QLoRA는 base model을 **4-bit로 quantize**해 VRAM을 줄이되, 학습 불안정성을 피하기 위해 **학습은 LoRA adapter에만** 일어납니다. 이때 자주 쓰는 설정이:
- `bnb_4bit_quant_type="nf4"`: 정규분포 가정의 weight에 최적화된 4-bit 타입 ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))
- `bnb_4bit_use_double_quant=True`: “양자화 상수”도 다시 양자화해 메모리 절감 ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))
- `prepare_model_for_kbit_training(model)`: k-bit 학습을 위한 전처리(예: layernorm 처리 등) ([huggingface.co](https://huggingface.co/docs/peft/en/developer_guides/quantization?utm_source=openai))

### 3) 어디에 LoRA를 꽂을까: `target_modules`
아키텍처마다 layer명이 달라 골치 아픈데, 2026년 실무 팁은 **가능하면 “all-linear”**입니다. PEFT는 `target_modules="all-linear"`로 Transformer 내부의 Linear/Conv1D에 광범위하게 적용하는 옵션을 제공합니다. ([huggingface.co](https://huggingface.co/docs/peft/en/developer_guides/quantization?utm_source=openai))

또 하나의 함정: **chat template에 특수 토큰이 들어가면 embedding / lm_head 처리**가 중요합니다. TRL의 SFTTrainer 문서에서도 `<|im_start|>`, `<|eot_id|>` 같은 special token이 있는 경우 `modules_to_save`에 `embed_tokens`, `lm_head`를 포함하지 않으면 출력이 망가질 수 있다고 명시합니다. ([huggingface.co](https://huggingface.co/docs/trl/v0.16.1/sft_trainer?utm_source=openai))

---

## 💻 실전 코드
아래 코드는 “2026년 2월 기준 가장 흔한 스택”인 **Transformers + BitsAndBytes(4-bit) + PEFT(LoRA) + TRL(SFTTrainer)** 조합으로, 로컬 GPU 1장 기준 QLoRA SFT를 재현하는 예제입니다.

```python
# 실행 전 설치 예시:
# pip install -U "transformers>=4.45" "accelerate>=0.34" "datasets>=2.20" "trl>=0.16" "peft>=0.12" bitsandbytes

import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
)
from peft import LoraConfig, prepare_model_for_kbit_training, get_peft_model
from trl import SFTTrainer, SFTConfig

# 1) Base model 선택: 가능하면 Instruct 계열 추천(대화 템플릿/토크나이저 정합성이 좋음)
model_id = "Qwen/Qwen2.5-0.5B"  # 데모용(작아서 누구나 재현 쉬움)
# 실무에서는 7B~14B Instruct를 QLoRA로 많이 감

# 2) QLoRA용 4-bit quantization 설정 (NF4 + double quant)
#    - NF4/double quant는 QLoRA 논문/PEFT 가이드에서 핵심 옵션으로 언급됨
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16,  # Ampere+에서 bf16 권장
)

tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)
# 일부 모델은 pad_token 미정의. 학습/배치에서 필요할 수 있음.
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# 3) 4-bit로 base model 로드
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    device_map="auto",
    quantization_config=bnb_config,
)

# 4) k-bit 학습 전처리: quantized model 위에서 adapter 학습을 안정화
model = prepare_model_for_kbit_training(model)

# 5) LoRA 설정
#    - QLoRA 스타일로 최대한 넓게: target_modules="all-linear"
#    - chat template에 special token이 있는 모델이면 modules_to_save 고려(특히 embed/lm_head)
peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules="all-linear",
    modules_to_save=["lm_head", "embed_tokens"],  # 필요 시(모델/템플릿에 따라 조정)
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, peft_config)

# 6) 데이터셋: 예시는 TRL에서 자주 쓰는 공개 instruct 데이터
#    - 실무에서는 "내 업무 포맷"으로 정제된 고품질 소량 데이터가 더 중요
dataset = load_dataset("trl-lib/Capybara", split="train")

# 7) SFTTrainer 설정
#    - max_length/truncation은 성능과 비용을 좌우
#    - 작은 GPU면 batch_size를 낮추고 gradient_accumulation으로 보정
sft_args = SFTConfig(
    output_dir="./qlora_sft_out",
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=2e-4,
    max_steps=200,
    logging_steps=10,
    save_steps=100,
    bf16=True,  # 가능하면 bf16 권장
    max_length=2048,  # 문서에서도 truncation 기본 동작 주의 강조
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=sft_args,
)

trainer.train()

# 8) adapter 저장 (base model은 그대로, LoRA만 저장)
trainer.model.save_pretrained("./adapter_lora")

# (선택) 추론 시:
# base model + adapter를 로드해서 사용하거나, merge 후 단일 모델로 저장할 수 있음.
```

위 코드 흐름에서 “QLoRA의 본질”은 딱 두 줄입니다.
- 4-bit로 로드: `quantization_config=bnb_config` ([huggingface.co](https://huggingface.co/docs/peft/en/developer_guides/quantization?utm_source=openai))  
- adapter만 학습: `get_peft_model(...)`로 LoRA를 얹고, base는 freeze

---

## ⚡ 실전 팁
1) **`modules_to_save`는 생각보다 중요**
ChatML/Llama 계열처럼 special token을 쓰는 템플릿에서, embedding/lm_head가 학습/저장 경로에서 빠지면 “말이 붕괴”하거나 무한 반복 같은 문제가 나기도 합니다. TRL 문서가 이를 명시적으로 경고합니다. ([huggingface.co](https://huggingface.co/docs/trl/v0.16.1/sft_trainer?utm_source=openai))  
- 해결: `modules_to_save=["lm_head","embed_tokens"]`를 우선 넣고, 모델별로 검증 후 최소화하세요.

2) **QLoRA target_modules는 “넓게”가 기본값**
PEFT 가이드는 QLoRA-style로 `target_modules="all-linear"`를 권장합니다(레이어 명이 다양한 모델에서 특히). ([huggingface.co](https://huggingface.co/docs/peft/en/developer_guides/quantization?utm_source=openai))  
정밀 튜닝이 필요하면 q/k/v/o + MLP(gate/up/down)로 좁혀가며 비용-성능 트레이드오프를 잡습니다.

3) **컨텍스트 길이(max_length)는 곧 비용**
SFTTrainer는 기본적으로 truncation을 수행하고, tokenizer 설정에 따라 예상보다 짧게 잘릴 수 있습니다. 학습 전에 반드시 `max_length`가 의도대로인지 확인하세요. ([huggingface.co](https://huggingface.co/docs/trl/v0.16.1/sft_trainer?utm_source=openai))  
실무적으로는 “최대 길이”보다 “데이터의 길이 분포”를 먼저 보고, 패딩/잘림을 줄이도록 샘플을 재구성하는 편이 효과가 큽니다.

4) **“훈련은 completions만”이 의외로 잘 먹힌다**
지시문까지 모두 loss에 넣으면, 모델이 프롬프트를 “정답처럼” 외우는 방향으로 학습될 수 있습니다. completions-only(assistant 구간만 loss)로 가면 지시 따르기 품질이 좋아지는 경우가 많습니다(특히 multi-turn). 이 전략은 QLoRA 계열 레시피에서 자주 언급됩니다. ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide?utm_source=openai))

5) **검증은 “정량+정성” 둘 다**
QLoRA 논문도 벤치마크의 신뢰성 문제를 지적하고, 평가가 생각보다 어렵다는 점을 강조합니다. ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))  
실무에서는:
- 고정된 50~200개 “업무 대표 질문 세트”를 만들고
- 학습 전/후를 동일 프롬프트로 비교
- 실패 케이스를 데이터에 되먹임(데이터 큐레이션)이 가장 빠른 개선 루프입니다.

---

## 🚀 마무리
LoRA는 “적은 파라미터로 원하는 성격만 덧입히는” 방법이고, QLoRA는 거기에 **4-bit quantization**을 더해 “내 GPU 한 장에서도” fine-tuning을 가능하게 만든 방식입니다. 2026년 2월 기준 실무 베이스라인은:

- QLoRA: `BitsAndBytesConfig(load_in_4bit=True, nf4, double_quant)` + `prepare_model_for_kbit_training` ([huggingface.co](https://huggingface.co/docs/peft/en/developer_guides/quantization?utm_source=openai))  
- LoRA: `target_modules="all-linear"`로 시작, 필요하면 좁혀가기 ([huggingface.co](https://huggingface.co/docs/peft/en/developer_guides/quantization?utm_source=openai))  
- TRL SFTTrainer: truncation/max_length와 `modules_to_save` 함정을 먼저 잡기 ([huggingface.co](https://huggingface.co/docs/trl/v0.16.1/sft_trainer?utm_source=openai))  

다음 학습 추천은 두 갈래입니다.
1) **데이터 레시피 고도화**: completions-only, 멀티턴 구성, 실패 케이스 중심 증강  
2) **후속 정렬(Alignment)**: SFT 이후 DPO/ORPO 같은 선호 최적화로 “말투/정책/안전”을 더 정교하게 만들기

원하면, (1) 특정 모델(Llama 계열/Qwen 계열/Gemma 계열) 중 어떤 걸 목표로 하는지, (2) GPU VRAM, (3) 데이터 포맷(예: ShareGPT/ChatML/자체 JSON)을 알려주면 위 코드를 그 환경에 맞춰 “바로 돌릴 수 있는 형태”로 더 좁혀서 구성해드릴게요.