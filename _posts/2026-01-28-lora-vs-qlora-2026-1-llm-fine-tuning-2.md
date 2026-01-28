---
title: "LoRA vs QLoRA, 2026년 1월 기준 “진짜 효율”로 LLM Fine-tuning 하는 법 (원리+실전코드)"
date: 2026-01-28 02:25:10 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-01]
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
2026년에도 LLM fine-tuning의 본질은 변하지 않습니다. **성능(도메인 적합도)**을 올리고 싶지만, **GPU VRAM/학습 시간/운영 비용**이 발목을 잡습니다. Full fine-tuning은 7B만 가도 메모리 부담이 급격히 커지고(가중치+gradient+optimizer state), 실무에서는 “일단 돌아가는” 효율적 방법이 필요합니다. ([arxiv.org](https://arxiv.org/abs/2601.02609?utm_source=openai))

이때 가장 현실적인 해법이 **LoRA / QLoRA**입니다. LoRA는 업데이트 파라미터를 “저랭크(low-rank)”로 제한해 학습 비용을 줄이고, QLoRA는 여기에 **4-bit quantization**을 더해 **더 큰 모델을 더 작은 VRAM에서** fine-tuning 가능하게 만듭니다. ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide?utm_source=openai))

---

## 🔧 핵심 개념
### 1) LoRA: “가중치 전체” 대신 “저랭크 어댑터”만 학습
LoRA의 핵심은 선형층의 가중치 업데이트를 직접 학습하지 않고, 아래처럼 **저랭크 행렬 A,B로 분해된 델타(ΔW)**만 학습하는 겁니다.

- 원래: `W` 전체를 업데이트 (비싸고 메모리 많이 듦)
- LoRA: `W' = W + ΔW`, 그리고 `ΔW = B @ A` (rank r, r≪d)

이렇게 하면 학습해야 할 파라미터 수가 크게 줄고, checkpoint도 “어댑터만” 저장할 수 있어 배포/롤백도 쉬워집니다.

추가로 2025~2026 흐름에서 중요한 포인트가 두 가지:
- **rsLoRA**: scaling을 `lora_alpha/r` 대신 `lora_alpha/sqrt(r)`로 안정화해 고랭크에서 성능 잠재력을 더 끌어올리는 접근 ([huggingface.co](https://huggingface.co/docs/peft/main/developer_guides/lora?utm_source=openai))  
- **LoRA-FA optimizer**: LoRA 학습에서 activation memory를 줄여 VRAM 효율을 더 개선(랭크 올려도 메모리 증가 둔감) ([huggingface.co](https://huggingface.co/docs/peft/main/en/developer_guides/lora?utm_source=openai))  

### 2) QLoRA: 4-bit로 “베이스 모델”을 들고 오고, LoRA만 학습
QLoRA는 베이스 모델 가중치를 **4-bit로 quantize**해서 GPU에 올리고, 학습은 LoRA adapter(대개 16-bit/bf16)만 합니다. 핵심 옵션들이 실전 품질을 좌우합니다.

- **NF4**: QLoRA 논문 계열에서 권장되는 4-bit 타입. 학습용 4-bit base에는 NF4 권장 ([huggingface.co](https://huggingface.co/docs/transformers/main/quantization/bitsandbytes?utm_source=openai))  
- **compute dtype**: 4-bit 저장 + bf16 계산(예: `bnb_4bit_compute_dtype=torch.bfloat16`)로 속도/안정성 타협 ([huggingface.co](https://huggingface.co/docs/transformers/main/quantization/bitsandbytes?utm_source=openai))  
- **(Nested) double quantization**: 4-bit 양자화에 추가 최적화를 얹는 계열(설정에 따라 VRAM 절감) ([huggingface.co](https://huggingface.co/docs/transformers/main/quantization/bitsandbytes?utm_source=openai))  

또, PEFT 쪽에서는 QLoRA 성능을 끌어올리는 “초기화”도 강조됩니다.
- **LoftQ**: quantization error를 줄이도록 LoRA를 초기화. 특히 `target_modules="all-linear"` + `nf4` 조합이 권장되는 흐름 ([huggingface.co](https://huggingface.co/docs/peft/main/en/developer_guides/lora?utm_source=openai))  

---

## 💻 실전 코드
아래 예제는 **Transformers + PEFT + bitsandbytes** 조합으로, “4-bit(Q)LoRA SFT”를 최소 구성으로 돌리는 형태입니다. (대화형 데이터라면 chat template 적용을 권장)

```python
import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# 1) 4-bit quantization config (QLoRA 핵심)
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",              # 학습용 base는 NF4 권장
    bnb_4bit_compute_dtype=torch.bfloat16,  # bf16 compute로 속도/안정성
    bnb_4bit_use_double_quant=True,         # nested/double quant 계열
)

base_model_id = "meta-llama/Meta-Llama-3-8B-Instruct"  # 예시: 라이선스/접근 권한 확인 필요
tokenizer = AutoTokenizer.from_pretrained(base_model_id, use_fast=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    base_model_id,
    quantization_config=bnb_config,
    device_map="auto",
)

# 2) k-bit training 준비: LayerNorm 캐스팅/gradient checkpoint 등 안정화 설정에 관여
model = prepare_model_for_kbit_training(model)

# 3) LoRA 설정
# - target_modules는 모델 아키텍처에 따라 다름(q_proj/v_proj 등). "all-linear"는 폭 넓게 먹이는 옵션.
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules="all-linear",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# 4) 데이터: 예시는 HF dataset의 text 컬럼이 있다고 가정
#    실무에서는 ChatML/ShareGPT를 "prompt + response"로 명확히 포맷하고,
#    response 부분만 loss를 주는 방식이 품질/안전성에 유리한 경우가 많음.
ds = load_dataset("Abirate/english_quotes")  # 예시 데이터
def tokenize_fn(ex):
    return tokenizer(
        ex["quote"],
        truncation=True,
        max_length=256,
        padding="max_length",
    )

train_ds = ds["train"].select(range(2000)).map(tokenize_fn, remove_columns=ds["train"].column_names)

data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

# 5) 학습 설정
args = TrainingArguments(
    output_dir="./qlora-adapter-out",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,  # VRAM 부족하면 늘려서 effective batch 확보
    learning_rate=2e-4,
    num_train_epochs=1,
    logging_steps=20,
    save_steps=200,
    bf16=True,                      # 가능하면 bf16 권장(환경 따라 fp16)
    optim="paged_adamw_8bit",        # bitsandbytes 계열 optimizer (환경에 따라 가용성 확인)
    report_to="none",
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=train_ds,
    data_collator=data_collator,
)

trainer.train()

# 6) 결과 저장: base는 그대로, LoRA adapter만 저장하는 게 일반적
model.save_pretrained("./qlora-adapter-out/adapter")
tokenizer.save_pretrained("./qlora-adapter-out/adapter")
```

참고로 실무 관점에선 “학습이 정말 진행 중인지”를 **gradient norm / loss curve**로 반드시 확인해야 합니다. 최근에는 특정 프레임워크 벤치마크가 “실제로는 학습이 안 도는 상태”였다는 지적도 나왔습니다. ([arxiv.org](https://arxiv.org/abs/2601.02609?utm_source=openai))

---

## ⚡ 실전 팁
- **NF4 + bf16 compute는 사실상 기본값**처럼 굳어졌습니다. 학습용 4-bit base에서는 NF4가 권장됩니다. ([huggingface.co](https://huggingface.co/docs/transformers/main/quantization/bitsandbytes?utm_source=openai))  
- **target_modules를 보수적으로 시작하지 마세요**: QLoRA에서 “몇 개 레이어만” LoRA를 걸면 용량은 줄지만 성능이 급격히 꺾이는 케이스가 있습니다. LoftQ도 “많이 타겟팅할수록” 유리한 방향을 제시합니다. ([huggingface.co](https://huggingface.co/docs/peft/main/en/developer_guides/lora?utm_source=openai))  
- **LoRA rank(r)는 ‘품질 vs 비용’의 레버**: r=8/16/32를 빠르게 스윕하고, rsLoRA/LoRA-FA 같은 최신 옵션으로 “랭크를 올렸을 때의 이득”을 회수하는 전략이 좋습니다. ([huggingface.co](https://huggingface.co/docs/peft/main/developer_guides/lora?utm_source=openai))  
- **“토큰 패딩 낭비”가 학습비를 잡아먹습니다**: sequence packing(길이 비슷한 샘플을 묶어 패딩 최소화)을 도입하면 체감 속도가 크게 오릅니다. 최신 프레임워크들은 이걸 핵심 최적화로 내세웁니다. ([arxiv.org](https://arxiv.org/abs/2601.02609?utm_source=openai))  
- **로그/재현성은 선택이 아니라 필수**: MLflow 같은 툴로 파라미터·메트릭·아티팩트를 남겨야 “왜 좋아졌는지/나빠졌는지”를 추적할 수 있습니다. 특히 PEFT 모델 로깅 요구 버전 조건도 있으니 문서를 확인하세요. ([mlflow.org](https://mlflow.org/docs/latest/ml/deep-learning/transformers/tutorials/fine-tuning/transformers-peft/?utm_source=openai))  

---

## 🚀 마무리
정리하면,
- **LoRA**는 “학습 파라미터 자체를 줄여” fine-tuning 비용을 낮추고,
- **QLoRA**는 “베이스 모델을 4-bit로 들고 와서” 더 큰 모델을 작은 VRAM에서 다루게 해줍니다. ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide?utm_source=openai))  

다음 학습으로는 (1) PEFT의 **LoftQ/rsLoRA/LoRA-FA** 같은 “품질·효율 개선 옵션”을 실제 데이터셋에서 ablation으로 비교하고 ([huggingface.co](https://huggingface.co/docs/peft/main/en/developer_guides/lora?utm_source=openai)), (2) padding 낭비를 줄이는 **packing**과 학습이 “진짜로” 되고 있는지 검증하는 **gradient/loss sanity check**를 파이프라인에 고정으로 넣는 걸 추천합니다. ([arxiv.org](https://arxiv.org/abs/2601.02609?utm_source=openai))