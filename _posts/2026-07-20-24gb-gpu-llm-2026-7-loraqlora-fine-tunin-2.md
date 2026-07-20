---
title: "24GB GPU 한 장으로 “내 도메인 전용 LLM” 만들기: 2026년 7월 기준 LoRA/QLoRA Fine-tuning 실전 튜토리얼"
date: 2026-07-20 03:48:38 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-07]
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
프로덕션에서 LLM을 “그럴듯하게” 쓰는 것과 “우리 조직의 톤/정책/지식 구조를 일관되게” 반영하는 것은 다릅니다. RAG만으로 해결하려 하면 (1) 문서가 길어질수록 프롬프트가 비대해지고 (2) 답변 스타일/형식이 흔들리고 (3) 도메인 특화 판단(예: 운영 규칙, 대응 우선순위)이 매번 재설명되어 비용이 커집니다. 이때 Fine-tuning(특히 LoRA/QLoRA)은 **모델의 행동 양식(스타일, 포맷, 의사결정 규칙)** 을 “가볍게” 고정하는 데 강합니다. QLoRA는 4-bit 기반으로 VRAM 요구량을 크게 낮춰, 7B~8B급은 6GB 수준에서도 학습 가능하다는 가이드가 명시돼 있고(실사용은 seq_len/배치에 따라 달라짐) 소비자 GPU에서 현실화되었습니다. ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements?utm_source=openai))

**언제 쓰면 좋나**
- “정답 지식”보다 **답변 형식/톤/정책 준수**가 중요한 경우(사내 헬프데스크, DevOps Runbook Q&A, CS 매크로, 코드리뷰 코치 등)
- RAG로 문서를 붙여도 **출력 포맷이 안정적으로 안 지켜지는** 경우(JSON 스키마, 체크리스트, 티켓 템플릿)
- 온프렘/로컬 배포(Ollama/llama.cpp/vLLM)까지 염두에 두고, **adapter만 관리**하고 싶을 때(내부 배포/버전관리) ([gptfrontier.com](https://www.gptfrontier.com/unsloth-qlora-llama-3-tutorial/?utm_source=openai))

**언제 쓰면 안 되나**
- 데이터가 부족한데 “지식”을 주입하려는 경우(환각/오염 위험): 이건 RAG + 평가/가드레일이 우선
- 모델이 이미 충분히 잘하는 일반 태스크에서, 작은 개선을 위해 무리하게 돌리는 경우(ROI 낮음)
- 법/의료 등 고위험 도메인에서 “정답성”을 튜닝으로 해결하려는 경우(평가/감사 체계 없으면 위험)

---

## 🔧 핵심 개념
### 주요 개념 정의
- **LoRA (Low-Rank Adaptation)**: base model weight는 **freeze**하고, 특정 Linear layer에 저랭크 행렬(대개 A,B)을 추가해 **학습 파라미터 수를 극단적으로 줄이는** PEFT 방식.
- **QLoRA**: LoRA는 그대로 쓰되, base model weight를 **4-bit(NF4 등)** 로 로드하여 **메모리 사용을 크게 낮춘** 학습 방식. ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))
- **NF4 / Double Quantization / Paged Optimizers**: QLoRA를 현실화한 핵심 구성요소. NF4는 “정규분포에 가까운 weight”에 맞춘 4-bit 타입이고, double quantization은 “양자화에 쓰이는 상수”까지 다시 양자화해 메모리를 더 줄이며, paged optimizer는 순간 메모리 스파이크(OOM)를 완화합니다. ([github.com](https://github.com/huggingface/blog/blob/main/4bit-transformers-bitsandbytes.md?utm_source=openai))

### 내부 작동 방식(흐름)
1) **Base model(4-bit) 로드**  
   - QLoRA에서는 forward 시점에 4-bit weight를 연산에 맞게 dequantize/사용합니다. 이때 성능 병목이 될 수 있어, 커널 최적화가 중요한 주제입니다(최근 NF4 dequantization 커널 최적화 연구도 등장). ([arxiv.org](https://arxiv.org/abs/2604.02556?utm_source=openai))  
2) **LoRA adapter 삽입(학습 대상)**  
   - attention의 q_proj/k_proj/v_proj/o_proj, MLP의 up/down/gate 등 “어디에 꽂느냐”가 품질/비용을 좌우합니다.
3) **Optimizer는 adapter 파라미터만 업데이트**  
   - base는 고정, adapter만 업데이트하므로 checkpoint가 작고 배포가 쉽습니다.
4) **(선택) merge/export**  
   - adapter만 배포하거나, merge해서 단일 weight로 만들거나, GGUF로 내보내 로컬 추론(Ollama/llama.cpp)로 이어갑니다. ([gptfrontier.com](https://www.gptfrontier.com/unsloth-qlora-llama-3-tutorial/?utm_source=openai))

### 다른 접근과의 차이점(실무 관점)
- **Full Fine-tuning(FFT)**: 성능 상한은 높을 수 있지만 비용/리스크가 큼(과적합, catastrohpic forgetting, VRAM 폭증). Unsloth 쪽 문서도 대체로 “대부분 FFT는 불필요”에 가깝게 가이드합니다. ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide?utm_source=openai))
- **RAG**: 지식 최신성/정답성에 강함. 대신 “행동/형식” 고정에는 한계. 보통은 **RAG + LoRA(스타일/정책)** 조합이 ROI가 좋습니다.
- **Prompt engineering**: 가장 싸고 빠르지만, 길어질수록 비용/불안정성 증가. 운영에선 “규칙을 모델 내부로 옮기는” 편이 더 싸질 때가 많습니다.

---

## 💻 실전 코드
아래는 “사내 DevOps Runbook Q&A” 같은 현실 시나리오를 가정합니다. 목표는 **답변을 ‘시니어 엔지니어 톤 + 체크리스트 + 위험도 분류 + 롤백 플랜’** 템플릿으로 강제하는 것. (지식 자체는 RAG로 보강하고, 여기서는 행동 양식을 튜닝)

### 0) 셋업 (Ubuntu 기준)
```bash
python -m venv .venv
source .venv/bin/activate

pip install -U "unsloth" "datasets" "transformers" "accelerate" "trl" "peft"
```
Unsloth는 설치 시 호환 버전을 맞춰주는 편이라, CUDA/torch 조합 충돌을 줄이는 장점이 있습니다(환경은 여전히 검증 필요). ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements?utm_source=openai))

### 1) 데이터 준비(실무형)
형식은 “대화형 instruct”가 유리합니다. (Base 모델보다 Instruct 모델 추천) ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide?utm_source=openai))  
예: `data/devops_sft.jsonl` (현실적으로는 티켓/포스트모템/런북에서 추출 후 비식별 처리)
```jsonl
{"messages":[
  {"role":"system","content":"You are a senior DevOps engineer. Follow the required response template."},
  {"role":"user","content":"Kubernetes에서 특정 노드만 Pod가 Pending입니다. 이벤트에는 'Insufficient cpu'가 보이고, HPA도 동작 중이에요. 지금 당장 어떤 순서로 진단/조치할까요?"},
  {"role":"assistant","content":"[SEVERITY] ...\n[DIAGNOSIS CHECKLIST] ...\n[IMMEDIATE ACTIONS] ...\n[ROLLBACK PLAN] ...\n[POST-INCIDENT] ..."}
]}
```

### 2) QLoRA로 SFT 학습(Unsloth)
```python
# train_qlora_devops.py
import os
import torch
from datasets import load_dataset
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments

MODEL_ID = "unsloth/llama-3.1-8b-unsloth-bnb-4bit"  # 4-bit quant ready (예시)
MAX_SEQ_LEN = 2048

def format_chat(example):
    # messages 그대로 쓰는 데이터셋을 가정
    return {"text": example["messages"]}

def main():
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name = MODEL_ID,
        max_seq_length = MAX_SEQ_LEN,
        dtype = None,          # BF16 가능하면 torch.bfloat16 고려
        load_in_4bit = True,   # QLoRA
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r = 16,
        lora_alpha = 32,
        lora_dropout = 0.05,
        target_modules = ["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
        bias = "none",
        use_gradient_checkpointing = "unsloth",  # 긴 컨텍스트/VRAM 절약에 유리
    )

    ds = load_dataset("json", data_files="data/devops_sft.jsonl")["train"]
    ds = ds.map(format_chat, remove_columns=ds.column_names)

    args = TrainingArguments(
        output_dir = "out/devops-qlora",
        per_device_train_batch_size = 1,
        gradient_accumulation_steps = 8,   # 실효 배치 = 8
        learning_rate = 2e-4,
        num_train_epochs = 2,
        warmup_ratio = 0.03,
        logging_steps = 10,
        save_steps = 200,
        bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8,
        fp16 = not (torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8),
        optim = "adamw_torch",
        lr_scheduler_type = "cosine",
        report_to = "none",
    )

    trainer = SFTTrainer(
        model = model,
        tokenizer = tokenizer,
        train_dataset = ds,
        dataset_text_field = "text",
        max_seq_length = MAX_SEQ_LEN,
        args = args,
        packing = True,  # 짧은 샘플 많을 때 토큰 효율 개선(평가로 부작용 확인)
    )

    trainer.train()

    # adapter 저장 (작게 관리)
    model.save_pretrained("out/devops-qlora/adapter")
    tokenizer.save_pretrained("out/devops-qlora/adapter")

if __name__ == "__main__":
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    main()
```

**예상 로그/출력(예시)**
- `train_runtime`, `train_loss`가 출력되고, `out/devops-qlora/adapter`에 LoRA adapter가 생성됩니다.
- VRAM은 모델/seq_len/r에 따라 다르지만, QLoRA가 “단일 GPU에서도 가능”하도록 만든다는 것이 핵심입니다. Unsloth 문서에는 8B QLoRA 최소 6GB 수준의 표가 있고, 실제 4090에서 6~7GB대 사례가 보고됩니다(조건에 따라 변동). ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements?utm_source=openai))

### 3) 로컬 추론 테스트(학습된 adapter 적용)
```python
# infer.py
import torch
from unsloth import FastLanguageModel

BASE = "unsloth/llama-3.1-8b-unsloth-bnb-4bit"
ADAPTER = "out/devops-qlora/adapter"

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = BASE,
    max_seq_length = 2048,
    dtype = None,
    load_in_4bit = True,
)
model = FastLanguageModel.get_peft_model(model)  # PEFT wrapper
model.load_adapter(ADAPTER)

FastLanguageModel.for_inference(model)

prompt = [
  {"role":"system","content":"You are a senior DevOps engineer. Follow the required response template."},
  {"role":"user","content":"배포 직후 5xx가 급증했고, ALB target은 healthy로 보이는데 앱 로그에는 DB timeout이 늘었습니다. 15분 내 완화가 목표입니다."}
]

inputs = tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True, return_tensors="pt").to("cuda")
out = model.generate(
    input_ids=inputs,
    max_new_tokens=500,
    temperature=0.2,
    top_p=0.9,
)
print(tokenizer.decode(out[0], skip_special_tokens=True))
```

(선택) GGUF로 export해서 Ollama/llama.cpp로 가져가는 흐름은 Unsloth 튜토리얼들에서 “학습→export→로컬서빙”까지 자주 다루는 패턴입니다. ([gptfrontier.com](https://www.gptfrontier.com/unsloth-qlora-llama-3-tutorial/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **“지식”이 아니라 “행동”을 튜닝하라**  
   - QLoRA/LoRA는 작은 데이터로도 스타일/포맷/정책 준수는 빠르게 좋아집니다. 반면 사실 지식 주입은 위험합니다. 지식은 RAG/툴콜로 해결하고, 튜닝은 “응답 품질의 일관성”에 집중하세요.
2) **target_modules는 비용-품질 레버**  
   - 모든 projection에 다 꽂으면 품질은 오르기 쉽지만 VRAM/학습시간/오버피팅 리스크도 증가. 먼저 attention 쪽(q/v/o)부터 시작→필요 시 MLP까지 확장 식으로 단계적으로.
3) **서빙 precision과 학습 precision의 일관성**  
   - “4-bit로 서빙할 건데 학습은 16-bit로 했다” 같은 혼종은 품질/재현성 이슈가 납니다. Unsloth 문서도 “serve precision과 train precision을 맞추라”는 방향을 명시합니다. ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide?utm_source=openai))

### 흔한 함정/안티패턴
- **packing을 켜고 데이터 경계를 무시**: 토큰 효율은 좋아지지만, 샘플 간 경계가 섞이면서 형식 학습이 깨지는 경우가 있습니다. “포맷 강제”가 목표면 packing on/off를 둘 다 평가하세요.
- **학습 데이터에 ‘나쁜 예시(규칙 위반)’를 섞고 라벨링이 부정확**: 모델은 의외로 그 패턴을 학습합니다. 특히 정책/보안 관련은 데이터 정제가 성능보다 중요.
- **loss만 보고 성공 판단**: 실무는 “템플릿 준수율, 금지행동 감소, 특정 케이스에서의 안정성”이 KPI입니다. 최소한 자체 eval set과 체크리스트를 만드세요.

### 비용/성능/안정성 트레이드오프
- **QLoRA**: 메모리/비용 효율 최고. 다만 4-bit 연산/디퀀타이즈 경로가 성능 병목이 될 수 있고 커널/라이브러리 영향이 큽니다(최근 NF4 디퀀타이즈 최적화 연구도 이 지점을 짚음). ([arxiv.org](https://arxiv.org/abs/2604.02556?utm_source=openai))  
- **LoRA(16-bit)**: VRAM 여유가 있으면 안정적이고 디버깅이 쉬운 편. 하지만 7B~8B부터는 요구 VRAM이 급상승할 수 있습니다. ([unsloth.ai](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements?utm_source=openai))  
- **Unsloth 같은 고속 구현체**: 동일한 방법론(LoRA/QLoRA)이라도 커널/트레이닝 루프 최적화로 체감 비용이 크게 달라질 수 있어, “vanilla HF vs 최적화 스택” 비교는 해볼 가치가 큽니다. ([computingforgeeks.com](https://computingforgeeks.com/fine-tune-llm-unsloth-qlora/?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 7월 기준 LoRA/QLoRA는 “대형 GPU 인프라 없이도” 도메인 전용 LLM을 만들 수 있는 가장 실용적인 경로입니다. 특히 QLoRA는 NF4/double quant/paged optimizer 같은 구성으로 4-bit 기반 학습을 가능하게 했고, Unsloth 계열 튜토리얼들은 단일 GPU에서 end-to-end(학습→테스트→GGUF export)까지를 현실적으로 보여줍니다. ([github.com](https://github.com/huggingface/blog/blob/main/4bit-transformers-bitsandbytes.md?utm_source=openai))

**도입 판단 기준**
- 출력 형식/정책 준수/톤을 “매번 프롬프트로 강제”하느라 비용이 크다 → **LoRA/QLoRA 강추**
- 지식 최신성/근거 제시가 핵심이다 → **RAG 우선**, 튜닝은 보조
- GPU가 1장(예: 12~24GB)이고 빠르게 반복해야 한다 → **QLoRA + 작은 r부터**, seq_len과 packing을 평가로 조절

**다음 학습 추천**
- QLoRA 원 논문에서 NF4/double quant/paged optimizer의 의도를 다시 읽고(왜 이 조합이 필요한지), ([arxiv.org](https://arxiv.org/abs/2305.14314?utm_source=openai))
- bitsandbytes/Transformers quantization 문서에서 NF4/설정 옵션을 정확히 확인한 뒤, ([huggingface.co](https://huggingface.co/docs/transformers/quantization/bitsandbytes?utm_source=openai))
- “내 태스크 KPI(템플릿 준수율/금지행동/응답 안정성)” 중심의 eval harness를 먼저 만들어, 학습 설정을 데이터 기반으로 튜닝하세요.

원하시면, (1) 사용 중인 모델/VRAM/목표 출력 포맷(JSON 스키마 등) (2) 데이터 형태(티켓/대화/문서) (3) 서빙 환경(Ollama/vLLM) 을 알려주시면 위 코드를 **당신 프로젝트에 맞춘 파이프라인(전처리→학습→평가→배포)** 형태로 더 구체화해 드리겠습니다.