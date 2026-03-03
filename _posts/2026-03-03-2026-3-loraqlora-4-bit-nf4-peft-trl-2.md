---
title: "2026년 3월 기준 LoRA/QLoRA 파인튜닝 실전 튜토리얼: 4-bit NF4 + PEFT + TRL로 “효율”을 끝까지 뽑아내기"
date: 2026-03-03 02:49:03 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-03]
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
LLM fine-tuning은 “내 도메인/내 톤/내 포맷”에 모델을 맞추는 가장 강력한 방법이지만, 비용이 항상 문제입니다. Full fine-tuning은 가중치·그라디언트·optimizer state가 함께 메모리를 잡아먹어(특히 AdamW의 FP32 상태가 큼) 현실적인 GPU 한 장에서 바로 터집니다. 그래서 2026년에도 여전히 현업의 표준은 **PEFT(Parameter-Efficient Fine-Tuning)** 계열, 그중에서도 **LoRA**와 **QLoRA(4-bit quant + LoRA)** 조합입니다.  

최근 Hugging Face 생태계에서는 **Transformers의 BitsAndBytesConfig(4-bit NF4, nested/double quant)** + **PEFT의 LoRA(예: target_modules="all-linear", rsLoRA, LoftQ 등 옵션)** + **TRL의 SFTTrainer**로 “거의 공식 레시피”가 굳어졌습니다. 특히 NF4와 nested quant(= double quant)는 QLoRA의 핵심 구성으로 문서에 명확히 정리되어 있습니다. ([huggingface.co](https://huggingface.co/docs/transformers/v4.49.0/quantization/bitsandbytes?utm_source=openai))

---

## 🔧 핵심 개념
### 1) LoRA란?
LoRA는 큰 weight 업데이트(ΔW)를 직접 학습하지 않고, **저랭크 행렬 분해(BA)** 형태로만 학습합니다. 즉,
- 원래 가중치 W는 **frozen**
- 학습 가능한 것은 작은 rank `r`의 어댑터(LoRA A,B)
- 결과적으로 **학습 파라미터 수와 optimizer state가 급감**

PEFT에서는 `LoraConfig` + `get_peft_model()`로 주입하며, 초기화/대상 모듈/스케일링 전략(rsLoRA 등)까지 옵션화되어 있습니다. ([huggingface.co](https://huggingface.co/docs/peft/v0.9.0/developer_guides/lora?utm_source=openai))

### 2) QLoRA란? (LoRA + 4-bit quant)
QLoRA의 아이디어는 간단합니다:
- **base model weight를 4-bit(NF4)로 quantize**해서 VRAM을 크게 절약하고,
- quantized base weight는 그대로 두고(동결),
- 그 위에 **LoRA adapter만 학습**합니다.

여기서 중요한 디테일이 3개입니다.

**(a) NF4 (NormalFloat4)**  
LLM weight 분포가 대체로 “정규분포 주변”에 몰린 특성을 반영한 4-bit 포맷이라, 학습용 4-bit로 권장됩니다. Transformers 문서에서도 “훈련용 4-bit면 NF4를 쓰라”가 사실상 정답입니다. ([huggingface.co](https://huggingface.co/docs/transformers/v4.49.0/quantization/bitsandbytes?utm_source=openai))

**(b) Nested quantization = `bnb_4bit_use_double_quant=True`**  
첫 양자화에서 생기는 “스케일 상수”까지 다시 한 번 양자화해 **약 0.4 bits/param 정도를 추가로 절약**합니다. 메모리가 빡빡할 때 체감이 크고, 공식 문서에서도 nested quant로 별도 항목을 둡니다. ([huggingface.co](https://huggingface.co/docs/transformers/v4.49.0/quantization/bitsandbytes?utm_source=openai))

**(c) “QLoRA 스타일”의 target_modules**
원 논문/레시피에서 흔히 강조되는 포인트는 “attention의 q,v만”이 아니라 **가능하면 모든 linear에 LoRA를 붙이는 것**입니다. PEFT에서는 이를 `target_modules="all-linear"`로 간단히 처리할 수 있게 가이드합니다. ([huggingface.co](https://huggingface.co/docs/peft/v0.9.0/developer_guides/lora?utm_source=openai))

---

## 💻 실전 코드
아래 코드는 **Transformers + bitsandbytes(4-bit) + PEFT(LoRA) + TRL(SFTTrainer)** 조합으로 “실행 가능한” QLoRA SFT 예시입니다.  
(실무에선 dataset만 갈아끼우면 그대로 파이프라인이 됩니다.)

```python
import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

# 1) 모델/토크나이저 선택
model_id = "meta-llama/Llama-3.1-8B-Instruct"  # 예시. 접근 권한/라이선스에 맞게 변경
tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)

# 일부 모델은 pad_token이 없을 수 있어 안전장치
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# 2) 4-bit QLoRA용 quantization 설정 (NF4 + nested/double quant)
# - NF4: 학습용 4-bit 권장
# - bnb_4bit_use_double_quant: nested quant로 추가 메모리 절약
# - compute dtype: bf16 권장(가능한 GPU면). 속도/안정성 타협점
quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
)

# Transformers 문서의 4-bit 가이드가 이 형태를 권장 ([huggingface.co](https://huggingface.co/docs/transformers/v4.49.0/quantization/bitsandbytes?utm_source=openai))
base_model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=quant_config,
    device_map="auto",
)

# 3) LoRA 설정
# - QLoRA 스타일: 모든 linear 레이어에 적용(target_modules="all-linear")
# - r/alpha는 품질-자원 트레이드오프의 핵심 노브
lora_config = LoraConfig(
    r=32,
    lora_alpha=64,
    lora_dropout=0.05,
    target_modules="all-linear",
    bias="none",
    task_type="CAUSAL_LM",
    use_rslora=True,  # rsLoRA: 스케일링을 안정화하는 옵션(PEFT 가이드) ([huggingface.co](https://huggingface.co/docs/peft/v0.9.0/developer_guides/lora?utm_source=openai))
)

model = get_peft_model(base_model, lora_config)

# 4) 데이터셋 준비 (예시: instruction -> response 형태로 텍스트 합치기)
ds = load_dataset("tatsu-lab/alpaca", split="train[:2000]")

def format_example(ex):
    # 실무 팁: 학습 포맷을 “일관된 템플릿”으로 고정하면 수렴이 좋아짐
    return {
        "text": f"### Instruction:\n{ex['instruction']}\n\n### Response:\n{ex['output']}"
    }

ds = ds.map(format_example, remove_columns=ds.column_names)

# 5) TRL SFTTrainer 구성
# TRL은 PEFT 통합/예제를 공식 문서로 제공 ([huggingface.co](https://huggingface.co/docs/trl/peft_integration?utm_source=openai))
cfg = SFTConfig(
    output_dir="./qlora_adapter",
    max_seq_length=1024,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=2e-4,
    num_train_epochs=1,
    logging_steps=10,
    save_steps=200,
    bf16=True,  # GPU 지원 시
    optim="paged_adamw_32bit",  # QLoRA 레시피에서 메모리 스파이크 완화에 유용한 선택지로 알려짐 ([deepwiki.com](https://deepwiki.com/artidoro/qlora/3.1-memory-optimization-techniques?utm_source=openai))
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=ds,
    args=cfg,
    dataset_text_field="text",
)

trainer.train()

# 6) 어댑터만 저장(=배포/공유 비용 최소화)
trainer.model.save_pretrained("./qlora_adapter")
tokenizer.save_pretrained("./qlora_adapter")
```

---

## ⚡ 실전 팁
1) **NF4 + bf16 compute dtype가 “기본값에 가까운 정답”**  
훈련용 4-bit면 NF4를 추천하고, compute dtype를 bf16로 두면 속도/안정성 밸런스가 좋습니다. ([huggingface.co](https://huggingface.co/docs/transformers/v4.49.0/quantization/bitsandbytes?utm_source=openai))

2) **nested/double quant는 “메모리가 문제면 켜라”**  
`bnb_4bit_use_double_quant=True`는 추가 메모리 절약을 주고, 커뮤니티에서도 “메모리 부족이면 double quant, 정밀도는 NF4, 학습 속도는 16-bit dtype” 같은 룰오브썸이 공유됩니다. ([discuss.huggingface.co](https://discuss.huggingface.co/t/is-this-needed-bnb-4bit-use-double-quant-true/50616?utm_source=openai))

3) **`target_modules="all-linear"`로 QLoRA 스타일을 간단히 재현**  
모델 아키텍처마다 레이어 이름이 미묘하게 달라 “q_proj/v_proj만 찍기”는 깨지기 쉽습니다. PEFT가 `all-linear` 옵션을 제공하는 이유가 실전 호환성입니다. ([huggingface.co](https://huggingface.co/docs/peft/v0.9.0/developer_guides/lora?utm_source=openai))

4) **bitsandbytes는 환경 제약이 있다 (특히 CUDA)**  
TPU 환경에서 bitsandbytes가 동작하지 않는다는 식의 제약이 반복적으로 언급됩니다. 즉, “QLoRA=bitsandbytes”로 가면 **CUDA GPU 전제**가 됩니다. ([discuss.huggingface.co](https://discuss.huggingface.co/t/bitsandbytesconfig-is-not-compitable-in-tpu-env/95817?utm_source=openai))

5) **어댑터 배포 전략을 분리하라**
QLoRA의 진짜 운영 이점은 “base model은 그대로 + adapter만 교체”입니다. Hugging Face에 올라오는 많은 repo가 실제로 **LoRA adapter만** 공개/배포합니다. ([huggingface.co](https://huggingface.co/tomhr/llm2025-lora-repo?utm_source=openai))

---

## 🚀 마무리
LoRA는 “학습 파라미터를 줄여서” 파인튜닝을 현실화했고, QLoRA는 “base weight를 4-bit(NF4)로 눌러서” 단일 GPU에서도 꽤 큰 모델을 튜닝 가능하게 만들었습니다. 2026년 3월 기준 실전 레시피는 다음 조합이 가장 재현성이 높습니다.

- Transformers `BitsAndBytesConfig`로 **4-bit NF4 + nested/double quant**
- PEFT `LoraConfig(target_modules="all-linear", rsLoRA 등)`로 **QLoRA 스타일 LoRA 주입**
- TRL `SFTTrainer`로 **SFT 파이프라인 단순화**

다음 단계로는 (1) completion-only 학습(불필요한 instruction loss 제거), (2) sequence packing으로 padding 낭비 줄이기, (3) LoftQ 같은 초기화/양자화 오차 대응, (4) 모델/프레임워크별 성능 최적화(예: Unsloth류, 커널 퓨전 기반 프레임워크 비교)까지 확장해보면 “효율적 학습”의 체감이 더 커집니다. ([huggingface.co](https://huggingface.co/docs/peft/v0.9.0/developer_guides/lora?utm_source=openai))