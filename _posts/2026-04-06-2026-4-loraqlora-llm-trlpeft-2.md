---
title: "2026년 4월 기준 LoRA·QLoRA로 LLM 파인튜닝을 “가볍게” 끝내는 법 (원리부터 TRL/PEFT 코드까지)"
date: 2026-04-06 03:29:23 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-04]
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
LLM fine-tuning은 여전히 “성능 vs 비용” 싸움입니다. Full fine-tuning은 가장 직관적이지만, VRAM·시간·운영 복잡도가 급격히 커집니다. 그래서 실무에서는 **PEFT(Parameter-Efficient Fine-Tuning)** 계열, 특히 **LoRA**가 사실상 표준이 되었고, 여기에 4-bit quantization을 결합한 **QLoRA**가 “단일 GPU에서도 7B~급을 현실적으로” 다루게 만들었습니다. QLoRA의 핵심은 **모델 본체는 4-bit로 얼려서 메모리를 줄이고**, 학습은 **LoRA adapter만** 업데이트한다는 점입니다. (NF4, double quantization, paged optimizer 같은 구성요소가 여기서 등장합니다.) ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))

2026년 4월 관점에서 보면, 생태계는 **Transformers + PEFT + bitsandbytes + TRL(SFTTrainer)** 조합이 가장 범용적이고, Unsloth 같은 가속 레이어/도구도 실무 채택이 늘고 있습니다. ([huggingface.co](https://huggingface.co/docs/transformers/v4.56.0/quantization/bitsandbytes/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) LoRA란?
LoRA는 원래 weight 업데이트(ΔW)를 직접 학습하지 않고, 이를 **저랭크 분해**로 근사합니다.

- 원래: `W <- W + ΔW`
- LoRA: `ΔW ≈ B @ A` (rank=r, r이 작음)

즉, 큰 행렬 W는 고정하고, 작은 A/B만 학습합니다. 그래서 **학습 파라미터 수/optimizer state가 급감**하고, 저장/배포도 “adapter만” 하면 됩니다. PEFT 문서도 이런 초기화/adapter 관리 방식을 명확히 제공합니다. ([huggingface.co](https://huggingface.co/docs/peft/main/en/developer_guides/lora?utm_source=openai))

### 2) QLoRA란? (LoRA + 4-bit quantization)
QLoRA는 “LoRA만 학습”하는 건 그대로 두고, **base model weight를 4-bit로 로드**합니다. 여기서 중요한 포인트는 다음 3개입니다.

- **NF4 (NormalFloat4)**: LLM weight 분포(대체로 정규분포에 가까움)에 맞춘 4-bit 타입  
- **Double quantization**: quantization 상수(스케일 등) 자체도 한 번 더 quantize해서 메모리 절약  
- **Paged optimizers**: 학습 중 순간적으로 튀는 메모리 스파이크를 완화

이 3개 덕분에 “4-bit인데도 성능을 크게 잃지 않고” fine-tuning이 가능해졌습니다. ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))

### 3) bitsandbytes에서 QLoRA가 돌아가는 방식(실무 관점)
Transformers는 `BitsAndBytesConfig`로 4-bit 로딩을 지원하고, QLoRA에서 흔히 아래 조합을 씁니다.

- `load_in_4bit=True`
- `bnb_4bit_quant_type="nf4"`
- `bnb_4bit_use_double_quant=True/False` (VRAM 압박 있으면 True 고려)
- `bnb_4bit_compute_dtype=torch.bfloat16` (가능하면 bf16 선호)

이때 **quantized weight는 고정**이고, forward/backward에서 필요한 연산 정밀도는 `compute_dtype`에 의해 좌우됩니다. ([huggingface.co](https://huggingface.co/docs/transformers/v4.56.0/quantization/bitsandbytes/?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 **Transformers + PEFT + TRL(SFTTrainer)**로 QLoRA SFT를 수행하는 “최소 실전형” 뼈대입니다. (단일 GPU 기준, dataset은 예시로 초소형을 사용)

```python
import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

# ---------------------------
# 1) (예시) SFT 데이터 준비
# ---------------------------
# 실무에서는 instruction/chat 템플릿을 명확히 정하고,
# "prompt/response"를 하나의 text로 합쳐 학습시키는 패턴이 흔합니다.
train_samples = [
    {"text": "### Instruction:\n요약해줘\n### Input:\nQLoRA는 무엇인가?\n### Response:\nQLoRA는 4-bit로 양자화된 base model에 LoRA adapter만 학습하는 방법입니다."},
    {"text": "### Instruction:\n설명해줘\n### Input:\nLoRA rank는 무엇을 의미해?\n### Response:\nrank는 LoRA의 저랭크 차원으로, 클수록 표현력은 늘지만 VRAM/연산이 증가합니다."},
]
train_ds = Dataset.from_list(train_samples)

# ---------------------------
# 2) Tokenizer / Model 로드
# ---------------------------
model_name = "meta-llama/Llama-2-7b-hf"  # 예시. 사용 모델에 맞게 변경

tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token  # causal LM에서 흔한 처리

# QLoRA용 4-bit 로딩 설정 (NF4 + (옵션) double quant)
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16,  # GPU가 bf16 지원하면 권장
)

# base model은 4-bit로 로드되고, 여기 파라미터들은 "학습 대상이 아님(고정)"이 핵심
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    quantization_config=bnb_config,
    device_map="auto",
)
model.config.use_cache = False  # gradient checkpointing 등과 충돌 방지용으로 자주 끔

# ---------------------------
# 3) LoRA adapter 붙이기
# ---------------------------
# target_modules는 모델 아키텍처에 따라 달라집니다.
# LLaMA 계열은 q_proj/k_proj/v_proj/o_proj가 대표적.
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()  # 학습되는 파라미터만 확인 (중요!)

# ---------------------------
# 4) TRL SFTTrainer로 학습
# ---------------------------
# TRL은 PEFT와 결합된 SFT 파이프라인을 자주 사용합니다.
sft_args = SFTConfig(
    output_dir="./qlora_adapter_out",
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,  # effective batch 확보
    learning_rate=2e-4,
    num_train_epochs=1,
    logging_steps=1,
    save_steps=20,
    bf16=True,                      # 가능하면 bf16
    max_seq_length=512,
    report_to=[],
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    args=sft_args,
    train_dataset=train_ds,
    dataset_text_field="text",
)

trainer.train()

# ---------------------------
# 5) 결과 저장 (adapter만 저장)
# ---------------------------
trainer.model.save_pretrained("./qlora_adapter_out")
tokenizer.save_pretrained("./qlora_adapter_out")
```

위 코드는 QLoRA에서 “정말 중요한 사실”을 그대로 반영합니다.

- **base model weight는 4-bit로 로드**(bitsandbytes) ([huggingface.co](https://huggingface.co/docs/transformers/v4.56.0/quantization/bitsandbytes/?utm_source=openai))  
- **학습은 LoRA adapter만**(PEFT) ([huggingface.co](https://huggingface.co/docs/peft/main/en/developer_guides/lora?utm_source=openai))  
- **SFT는 TRL의 trainer로 깔끔하게**(PEFT integration 흐름) ([huggingface.tw](https://huggingface.tw/docs/trl/peft_integration?utm_source=openai))  

---

## ⚡ 실전 팁
1) **target_modules를 “아키텍처별로” 잡아라**  
LLaMA류는 attention projection(q/k/v/o)에 LoRA를 걸면 효율/성능 밸런스가 좋습니다. 반대로 MLP까지 다 걸면 성능은 오를 수 있지만 VRAM/시간이 늘고, 데이터가 작을수록 과적합 위험도 커집니다.

2) **NF4는 기본값으로 두고, double quant는 VRAM이 빡빡할 때만 켜라**  
Hugging Face 커뮤니티에서도 경험칙으로 “NF4 + 16-bit compute”를 기본으로 두고, 메모리 압박이 있으면 double quant를 켜는 식의 접근이 자주 언급됩니다. ([discuss.huggingface.co](https://discuss.huggingface.co/t/is-this-needed-bnb-4bit-use-double-quant-true/50616?utm_source=openai))

3) **merge(어댑터 병합)는 ‘언제/어디에’ 할지 전략을 정해라**  
실무 배포에서는
- 학습/실험: adapter로 관리(가볍고 실험 빠름)
- 배포: 필요 시 merge해서 단일 체크포인트로  
패턴이 흔합니다. 다만 4-bit/로드 상태에 따라 merge 과정에서 충돌/오류가 나는 케이스들이 있어, **merge는 FP16/BF16 base에서 하는 편이 안전**한 경우가 많습니다(환경/버전 영향 큼). ([github.com](https://github.com/huggingface/peft/issues/1599?utm_source=openai))

4) **PEFT/Transformers 버전 차이로 성능·옵션이 바뀐다**  
PEFT 릴리즈에서 QLoRA 효율을 더 끌어올리는 옵티마이저/기능이 추가되기도 합니다. 재현성 필요한 팀이라면 “실험별 의존성 고정(lock)”은 필수입니다. ([github.com](https://github.com/huggingface/peft/releases?utm_source=openai))

5) **‘빠르게’가 목표면 Unsloth/Training Hub 같은 백엔드도 검토**  
2026년 4월 기준으로 Training Hub가 Unsloth 백엔드를 이용해 LoRA/QLoRA를 지원한다는 흐름이 보입니다. “표준 스택(Transformers/PEFT/TRL)”로 원리를 이해한 뒤, 운영 단계에서 가속 도구를 붙이는 접근이 가장 안전합니다. ([developers.redhat.com](https://developers.redhat.com/articles/2026/04/01/unsloth-and-training-hub-lightning-fast-lora-and-qlora-fine-tuning?utm_source=openai))

---

## 🚀 마무리
LoRA는 **학습 파라미터를 저랭크로 제한**해 비용을 줄이고, QLoRA는 여기에 **4-bit(NF4) quantization + (선택) double quant + 메모리 관리 기법**을 더해 “로컬 GPU에서도 실전 fine-tuning”을 가능하게 만듭니다. ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))  
추천 다음 학습 흐름은 아래 순서가 효율적입니다.

1) PEFT LoRA 문서로 adapter 메커니즘/멀티 어댑터 운용 이해 ([huggingface.co](https://huggingface.co/docs/peft/main/en/developer_guides/lora?utm_source=openai))  
2) Transformers bitsandbytes quantization 가이드로 4-bit 로딩 파라미터 체계 정리 ([huggingface.co](https://huggingface.co/docs/transformers/v4.56.0/quantization/bitsandbytes/?utm_source=openai))  
3) QLoRA 원 논문으로 NF4/double quant/paged optimizer의 “왜”를 재확인 ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))  

원하시면 다음 단계로, (1) 특정 모델(Llama/Qwen/Mistral 등)별 권장 `target_modules` 템플릿, (2) 데이터 포맷을 ChatML/Alpaca 스타일로 바꾸는 방법, (3) merge & export(vLLM/llama.cpp/Ollama)까지 포함한 배포 파이프라인을 같은 구조로 이어서 작성해드릴게요.