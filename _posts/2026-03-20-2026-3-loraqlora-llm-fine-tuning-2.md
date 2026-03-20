---
title: "2026년 3월 기준: LoRA/QLoRA로 LLM Fine-tuning을 “싸고 빠르게” 끝내는 실전 튜토리얼 (원리까지)"
date: 2026-03-20 02:44:49 +0900
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
2026년에도 LLM 파인튜닝의 현실은 크게 변하지 않았습니다. “데이터는 있는데 GPU/예산이 없다”가 기본 전제고, 그래서 **Full Fine-Tuning(FFT)** 대신 **PEFT(Parameter-Efficient Fine-Tuning)**가 표준이 됐습니다. 특히 **LoRA**는 base weight는 얼리고 저랭크 adapter만 학습해 비용을 확 줄이고, **QLoRA**는 여기에 **4-bit quantization**을 결합해 “큰 모델을 작은 자원으로” 다루게 해줍니다. Unsloth 쪽은 2026년 3월에도 Colab/로컬 환경에서 **안정적으로 QLoRA 파이프라인을 굴리는 방법**(환경 고정, 크래시 회피, 설정 조합)을 강조하고 있고, Hugging Face 생태계는 **PEFT + TRL(SFTTrainer)** 조합이 사실상 기본 빌딩블록이 됐습니다. ([marktechpost.com](https://www.marktechpost.com/2026/03/03/how-to-build-a-stable-and-efficient-qlora-fine-tuning-pipeline-using-unsloth-for-large-language-models/))

---

## 🔧 핵심 개념
### 1) LoRA란?
Transformer의 Linear 레이어에 대해, 원래 가중치 업데이트(ΔW)를 직접 학습하지 않고 **저랭크 분해된 행렬 A,B만 학습**합니다.

- 원래 업데이트: `W <- W + ΔW`
- LoRA: `ΔW = B @ A` (rank r, 보통 r=8~64)
- 장점: 학습 파라미터/옵티마 상태가 크게 줄어듦(=VRAM 절약), adapter만 저장/배포 가능

또한 2026년 Hugging Face PEFT 문서 기준으로 “기본 LoRA는 attention의 일부 모듈(q,v 등)만” 타깃하는 패턴이 흔하지만, **QLoRA 스타일**(논문 방식에 가깝게)은 **모든 linear 레이어**에 adapter를 붙이는 접근이 많이 쓰이고, PEFT에서는 이를 `target_modules="all-linear"`로 단순화했습니다. ([huggingface.co](https://huggingface.co/docs/peft/main/developer_guides/lora))

### 2) QLoRA란?
QLoRA는 “LoRA + 4-bit quantization” 조합입니다.

- **Base model weight**를 4-bit(예: bitsandbytes NF4 계열)로 로드해 VRAM을 크게 줄임
- 학습은 LoRA adapter만 업데이트 (adapter는 fp16/bf16로 유지)
- 결과적으로 “큰 모델도 단일 GPU/저사양에서 SFT 가능”이 목표

Unsloth 가이드에서도 “처음엔 LoRA/QLoRA로 시작하고, FFT는 마지막 수단”이라는 운영 원칙을 강하게 권장합니다(실무에서도 동일). ([docs.unsloth.ai](https://docs.unsloth.ai/get-started/fine-tuning-llms-guide))

### 3) 왜 2026년엔 “파이프라인 안정성”이 더 중요해졌나?
LoRA/QLoRA 자체는 기술적으로 성숙했지만, 실제로는
- CUDA/torch/transformers/bitsandbytes 호환성
- Colab 런타임 리셋/라이브러리 충돌
- GPU 감지 실패, VRAM OOM
같은 “비기술적” 문제로 시간이 더 날아갑니다. 2026-03-03 튜토리얼이 아예 **안정적인 QLoRA 파이프라인**을 전면에 내세운 이유가 여기입니다. ([marktechpost.com](https://www.marktechpost.com/2026/03/03/how-to-build-a-stable-and-efficient-qlora-fine-tuning-pipeline-using-unsloth-for-large-language-models/))

---

## 💻 실전 코드
아래는 “Hugging Face Transformers + bitsandbytes(4-bit) + PEFT(LoRA) + TRL(SFTTrainer)”로 QLoRA SFT를 돌리는 **최소 실전형** 예제입니다. (데이터는 예시로 아주 작은 synthetic 형태)

```python
import os
import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

# 1) 모델 선택: Instruct 계열 권장 (chat template 적용 쉬움)
model_id = "meta-llama/Meta-Llama-3.1-8B-Instruct"  # 예시: 접근 권한/대체 모델 필요할 수 있음

# 2) QLoRA용 4-bit 로드 설정 (bitsandbytes)
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",           # QLoRA에서 널리 쓰이는 타입
    bnb_4bit_use_double_quant=True,      # 메모리/정확도 트레이드오프에 유리한 경우가 많음
    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float16
)

tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)
# 많은 causal LM은 pad_token이 없어서 학습 시 필요
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=False
)

# 3) PEFT LoRA 설정
#    - QLoRA 스타일로 "all-linear"을 쓰면 아키텍처별 모듈명 차이를 크게 줄일 수 있음
lora = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules="all-linear"
)
model = get_peft_model(model, lora)

# 4) 데이터 (실전에서는 instruction-following 포맷 + chat template 권장)
train_data = Dataset.from_list([
    {"text": "### Instruction: 우리 서비스 장애 대응 런북을 요약해줘.\n### Response: ..."},
    {"text": "### Instruction: LoRA와 QLoRA 차이를 5줄로 설명해줘.\n### Response: ..."},
])

# 5) TRL SFTTrainer 설정
#    - TRL의 SFTTrainer는 transformers Trainer를 확장한 SFT 전용 도구
#    - gradient_checkpointing=True, use_cache=False 조합이 VRAM/안정성에 중요
sft_config = SFTConfig(
    output_dir="./qlora_out",
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=2e-4,
    max_steps=100,                 # 예시: 빠른 smoke test
    logging_steps=10,
    save_steps=50,
    bf16=torch.cuda.is_available(), # 가능하면 bf16 권장
    fp16=not torch.cuda.is_available(),
    gradient_checkpointing=True,
    max_length=1024,
    packing=False,                  # 데이터 짧으면 False가 디버깅 쉬움
    report_to="none",
)

# 모델 캐시 사용은 학습에서 메모리 폭발/버그의 원인이 되곤 함
model.config.use_cache = False

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_data,
    args=sft_config,
    dataset_text_field="text",
)

trainer.train()

# 6) LoRA adapter만 저장 (배포/머지 전략에 따라 달라짐)
trainer.model.save_pretrained("./qlora_adapter")
tokenizer.save_pretrained("./qlora_adapter")
```

- `SFTConfig`에 들어가는 옵션들이 매우 많고(optimizer, checkpoint, packing 등), TRL 문서에서 확인 가능합니다. ([huggingface.co](https://huggingface.co/docs/trl/main/en/sft_trainer))
- `target_modules="all-linear"`은 QLoRA 스타일을 “모듈명 나열 없이” 적용하는 핵심 트릭입니다. ([huggingface.co](https://huggingface.co/docs/peft/main/developer_guides/lora))

---

## ⚡ 실전 팁
1) **먼저 “smoke test”로 파이프라인을 검증**
- `max_steps=20~100`, 작은 데이터로 **OOM/형상 오류/속도**를 먼저 확인하세요.
- QLoRA는 설정이 많아서 “본 학습 전에 죽는” 케이스가 흔합니다(특히 Colab). 안정성 자체가 생산성입니다. ([marktechpost.com](https://www.marktechpost.com/2026/03/03/how-to-build-a-stable-and-efficient-qlora-fine-tuning-pipeline-using-unsloth-for-large-language-models/))

2) **Instruct 모델 + 올바른 chat template이 성능을 좌우**
- 같은 데이터라도 formatting이 엉키면 “학습은 되는데 모델이 이상해지는” 전형적인 실패가 납니다.
- 가능하면 ShareGPT/ChatML 등 표준 포맷으로 정규화하고, tokenizer의 chat template 경로/적용 방식을 점검하세요(TRL에도 관련 옵션들이 존재). ([huggingface.co](https://huggingface.co/docs/trl/main/en/sft_trainer))

3) **LoRA가 FFT를 ‘대체’하려면 타깃/하이퍼파라미터를 공격적으로 튜닝**
- 기본 LoRA(q,v만)로 부족하면, QLoRA 스타일처럼 **all-linear**로 확장하는 것이 성능/표현력에 유리한 경우가 많습니다. ([huggingface.co](https://huggingface.co/docs/peft/main/developer_guides/lora))  
- 실무 감각으로는 `r`(rank)와 `lora_alpha`는 “용량”이고, `dropout`은 “과적합 보험”입니다. 데이터가 작을수록 dropout을 켜고, 데이터가 크고 명확할수록 dropout을 줄이는 편이 낫습니다.

4) **“FFT로 가면 해결”은 대부분 착각**
- Unsloth 가이드가 지적하듯, LoRA/QLoRA에서 망가지면 데이터/포맷/목표 정의가 문제인 경우가 많고 FFT가 마법처럼 고쳐주지 않습니다. ([docs.unsloth.ai](https://docs.unsloth.ai/get-started/fine-tuning-llms-guide))

---

## 🚀 마무리
정리하면, 2026년 3월 기준 LLM Fine-tuning의 가장 실전적인 루트는 **QLoRA(4-bit) + PEFT(LoRA) + TRL(SFTTrainer)** 조합입니다. 핵심은 “더 큰 모델을 더 싸게”가 아니라, **(1) QLoRA 스타일로 adapter 범위를 넓히고(all-linear), (2) 학습 파이프라인을 안정화하고, (3) 데이터 포맷/템플릿을 제대로 잡는 것**입니다. ([huggingface.co](https://huggingface.co/docs/peft/main/developer_guides/lora))

다음 학습으로는:
- TRL의 `SFTTrainer` 옵션들(특히 packing/length 전략, optimizer/compile 관련)을 깊게 파고들고 ([huggingface.co](https://huggingface.co/docs/trl/main/en/sft_trainer))
- Unsloth의 Fine-tuning 가이드에서 QLoRA/LoRA 선택과 운영상의 함정(FFT 오해, VRAM 전략)을 체계적으로 정리해보는 것을 추천합니다. ([docs.unsloth.ai](https://docs.unsloth.ai/get-started/fine-tuning-llms-guide))