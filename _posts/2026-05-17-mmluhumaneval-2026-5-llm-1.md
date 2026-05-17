---
title: "MMLU·HumanEval 점수에 속지 마라: 2026년 5월 기준 LLM 벤치마크를 “내 프로젝트 관점”으로 해석하는 법"
date: 2026-05-17 04:06:25 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-05]
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

LLM을 도입할 때 제일 흔한 실패 패턴은 “리더보드에서 MMLU/HumanEval 점수 높은 모델 = 우리 서비스에서도 좋겠지”라고 가정하는 겁니다. 그런데 2025~2026년으로 오면서 **벤치마크 오염(contamination)**, **평가 프로토콜 차이(프롬프트/샘플링/채점기)**, **현실 과업과의 괴리**가 더 크게 문제로 떠올랐습니다. HumanEval은 특히 *pass@k*라는 지표 자체가 의사결정자를 자주 속입니다(“k번 뽑아보면 하나는 맞겠지”의 확률). ([ibm.com](https://www.ibm.com/es-es/think/topics/humaneval?utm_source=openai))

**언제 쓰면 좋나**
- 여러 후보 모델을 **같은 조건에서** 빠르게 비교(회귀 테스트 포함)할 때
- “지식형 QA” vs “코딩 함수 생성”처럼 **능력 축을 분리**해 보고 싶을 때(MMLU ↔ HumanEval)

**언제 쓰면 안 되나**
- 점수 하나로 “우리 제품에 적합”을 결론내릴 때(특히 RAG/에이전트/툴콜 기반 시스템)
- 벤치마크 점수가 **자사 KPI(정확도/안전/비용/지연)**로 직결된다고 믿을 때(벤치마크는 ‘대리 지표’일 뿐)

---

## 🔧 핵심 개념

### 1) MMLU와 HumanEval이 측정하는 “축”이 다르다
- **MMLU**: 다분야 객관식(주로 4지선다) 지식/추론 능력을 측정하는 대표 벤치마크.
- **HumanEval**: 자연어 문제 설명 → **Python 함수 구현** → 테스트 통과 여부로 **functional correctness**를 평가. 핵심 지표는 *pass@k*. ([llmreference.com](https://www.llmreference.com/benchmark/humaneval?utm_source=openai))

즉, MMLU가 높다고 해서 코드 생성이 강한 것도 아니고, HumanEval이 높다고 해서 제품 코드(리팩토링/보안/성능/레포 규모 맥락)를 잘하는 것도 아닙니다.

### 2) 프로토콜이 결과를 바꾼다: “점수”가 아니라 “실험”을 봐야 한다
벤치마크는 데이터셋만이 아니라 **평가 프로토콜 전체**(프롬프트 템플릿, few-shot 수, 샘플링 온도, 채점 방식, 런타임)입니다.

- MMLU는 “few-shot 몇 개냐”, “선지 포맷을 어떻게 주냐”에 따라 흔들립니다. 그래서 최근엔 더 어렵고(10지선다) 프롬프트 민감도를 낮추려는 **MMLU-Pro**가 많이 언급됩니다. ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))
- HumanEval은 “샘플을 몇 개 뽑아 pass@k로 보느냐”가 본질적으로 **탐색 예산(budget)**을 의미합니다. pass@1과 pass@10은 “모델 실력”이 아니라 “우리 서비스가 몇 번 재시도/다중샘플을 허용하나”와 직결됩니다. ([arxiv.org](https://arxiv.org/abs/2510.04265?utm_source=openai))

### 3) HumanEval의 ‘테스트 빈약’ 문제와 HumanEval+ (EvalPlus)
HumanEval은 원래 테스트가 제한적이라 “겉보기로 맞는 코드”가 통과하는 일이 생깁니다. 이를 보강하려고 **EvalPlus(HumanEval+)**가 각 문제당 테스트 케이스를 대폭(평균적으로 훨씬 많이) 늘려 더 엄격하게 검증합니다. 실제로 기존 HumanEval 대비 점수가 꽤 떨어질 수 있고, 심지어 일부 기준 구현/테스트 자체의 문제도 지적됩니다. ([arxiv.org](https://arxiv.org/abs/2305.01210?utm_source=openai))

### 4) 2026년에 벤치마크를 보는 실무적 관점: “리더보드 점수” → “내 환경에서 재현 가능한 하네스”
요즘은 벤치마크 자체보다, **재현 가능한 evaluation harness**(예: EleutherAI lm-evaluation-harness)로 내 모델/내 서빙 스택에서 동일 조건으로 돌려보는 게 더 중요합니다. lm-eval-harness는 MMLU 같은 태스크를 자동화해 주지만, 버전/태스크 정의/프롬프트/토크나이저 차이로 결과가 달라질 수 있어 “실험 구성”을 코드로 고정해야 합니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness?ref=Technology&utm_source=openai))

또한 제품 관점에서는 “오프라인 벤치마크”만으로 부족해서, **조직 목표→측정→개선** 루프(프로덕션 eval)로 가져가는 흐름이 강조됩니다. ([openai.com](https://openai.com/index/evals-drive-next-chapter-of-ai/?utm_source=openai))

---

## 💻 실전 코드

아래는 “우리 팀이 모델 후보 A/B를 고르는 상황”을 가정한 **현실적인 파이프라인**입니다.

- (1) `lm-evaluation-harness`로 **MMLU(지식/추론)** 측정  
- (2) `evalplus`로 **HumanEval+(코드 정답성)** 측정  
- (3) 결과를 JSON으로 수집해 CI에서 **회귀 게이트**로 사용

> 전제: 모델은 HuggingFace 로컬 모델이거나 vLLM로 서빙 가능하다고 가정(내부망/온프레에서도 흔한 구성).

### 0) 의존성/환경

```bash
python -m venv .venv
source .venv/bin/activate

pip install -U pip

# lm-eval-harness (MMLU 등)
pip install -U lm-eval

# EvalPlus (HumanEval+)
pip install -U evalplus

# 결과 정리
pip install -U pandas
```

### 1) MMLU를 “같은 조건”으로 고정해서 실행 (lm-eval-harness)

```bash
# 예시: vLLM 백엔드로 로컬 모델 평가
# 포인트: num_fewshot, batch_size, seed(가능하면), prompt/template를 버전 고정
lm_eval \
  --model vllm \
  --model_args pretrained="meta-llama/Meta-Llama-3-8B-Instruct",dtype=float16,tensor_parallel_size=1 \
  --tasks mmlu \
  --num_fewshot 5 \
  --batch_size auto \
  --output_path ./eval_out/mmlu_llama3_8b.json
```

**예상 출력(요지)**: `./eval_out/mmlu_llama3_8b.json`에 accuracy 및 서브태스크 점수 기록  
(팀 운영에서는 이 JSON을 “모델 카드”처럼 PR에 붙입니다)

> 주의: lm-eval-harness는 릴리스별로 태스크 구현/프롬프트가 미세 변경되기도 합니다. “점수 비교”는 반드시 **같은 커밋/버전**에서만 하세요. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai))

### 2) HumanEval+로 “통과율 뻥”을 줄이기 (EvalPlus)

EvalPlus는 생성(codegen)과 실행(evaluate)을 분리할 수도 있고, 바로 평가도 가능합니다. CI에서는 보통 “샘플 생성 artifact”를 남겨 재현성을 확보합니다.

```bash
# (A) 생성: greedy로 고정(샘플링 변수를 줄여 회귀에 유리)
evalplus.codegen \
  --model "meta-llama/Meta-Llama-3-8B-Instruct" \
  --dataset humaneval \
  --backend hf \
  --greedy \
  --output_path ./eval_out/humaneval_samples.jsonl

# (B) 평가: HumanEval+ 테스트로 검증
evalplus.evaluate \
  --dataset humaneval \
  --samples ./eval_out/humaneval_samples.jsonl \
  --base-only false \
  --output_path ./eval_out/humanevalplus_report.json
```

EvalPlus가 HumanEval 테스트를 대폭 확장해 더 엄격히 잡아내는 것이 핵심입니다. ([github.com](https://github.com/evalplus/evalplus?utm_source=openai))

### 3) (확장) “의미 있는 게이트”로 바꾸기: pass@1 + 비용/지연 + 실패 유형
벤치마크 점수 하나로 merge를 막지 말고, 운영 지표를 함께 보세요. 예를 들어:

- MMLU: accuracy 하락이 1.0pt 이상이면 fail
- HumanEval+: pass@1 하락이 2.0pt 이상이면 fail
- 그리고 **평균 latency / 토큰 비용**도 함께 fail 조건에 포함

```python
import json
from pathlib import Path

def load_score(path: str, key_candidates):
    data = json.loads(Path(path).read_text())
    for k in key_candidates:
        if k in data:
            return float(data[k])
    raise KeyError(f"score key not found in {path}")

# 예시 스키마는 실행 환경/버전에 따라 달라질 수 있으니
# 팀에서는 output JSON 스키마를 먼저 고정(또는 jq로 추출)하는 것을 권장
mmlu = json.loads(Path("./eval_out/mmlu_llama3_8b.json").read_text())
hum = json.loads(Path("./eval_out/humanevalplus_report.json").read_text())

# (예시) 실제로는 mmlu/hum JSON 구조에 맞게 추출 로직을 조정하세요.
print("Artifacts generated. Wire these into CI with schema-locked extractors.")
```

---

## ⚡ 실전 팁 & 함정

### Best Practice (2~3개)
1) **항상 pass@1을 기본으로 보고, pass@k는 “예산 지표”로 분리**
- pass@10이 높은 모델은 “10번 뽑으면 하나 맞는다”일 수 있습니다. 제품이 재시도/다중샘플을 허용하는지(비용/지연)와 함께 해석하세요. ([arxiv.org](https://arxiv.org/abs/2510.04265?utm_source=openai))

2) **HumanEval 대신 최소 HumanEval+ (EvalPlus)까지는 같이 돌려라**
- 원본 HumanEval은 테스트 커버리지가 얕아 과대평가될 수 있습니다. +버전에서 떨어지는 모델은 “취약한 정답”을 내는 경우가 많습니다. ([arxiv.org](https://arxiv.org/abs/2305.01210?utm_source=openai))

3) **벤치마크를 ‘제품 eval’로 연결하는 루프를 설계**
- 오프라인 점수는 후보 필터링까지만. 실제 도입 판단은 “우리 입력/우리 출력/우리 실패정의”로 만든 eval이 필요합니다(LLM-as-judge를 쓰더라도 human-in-the-loop 권장). ([openai.com](https://openai.com/index/evals-drive-next-chapter-of-ai/?utm_source=openai))

### 흔한 함정/안티패턴
- **리더보드 점수만 보고 모델 선택**: 동일 모델이라도 프롬프트/런타임/버전에 따라 재현이 안 됩니다.
- **평가 하네스 버전 미고정**: lm-eval-harness 릴리스/태스크 수정으로 스코어가 바뀌면, A/B 비교가 무의미해집니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai))
- **코드 실행 평가를 샌드박스 없이 돌림**: 모델 출력 코드를 로컬에서 바로 실행하면 보안 사고로 이어집니다(EvalPlus도 Docker 기반 안전 실행을 강조). ([github.com](https://github.com/evalplus/evalplus?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- pass@k를 올리려면 샘플 수(k)를 늘려야 하고, 이는 **토큰 비용/지연**을 직격합니다.
- few-shot을 늘리면 MMLU가 오를 수 있지만, 프롬프트 길이 증가로 **latency/컨텍스트 비용**이 증가합니다.
- 더 엄격한 벤치(HumanEval+)는 “마케팅 점수”는 떨어뜨리지만, **운영 리스크(버그/엣지케이스)**를 줄이는 방향입니다.

---

## 🚀 마무리

정리하면, 2026년 5월 시점에서 MMLU/HumanEval은 여전히 유용하지만 **“점수”가 아니라 “실험 설계”**가 핵심입니다.

- MMLU: 지식/추론 축의 빠른 비교용(가능하면 MMLU-Pro 등 더 강한 변형도 검토) ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))  
- HumanEval: 코드 생성의 최소 기준이지만, **HumanEval+ (EvalPlus)**로 테스트를 강화해야 실무 신뢰도가 올라감 ([evalplus.github.io](https://evalplus.github.io/?utm_source=openai))  
- 최종 도입 판단: 오프라인 벤치마크는 필터, **제품 맞춤 eval + CI 게이트**가 결정타 ([openai.com](https://openai.com/index/evals-drive-next-chapter-of-ai/?utm_source=openai))

**다음 학습 추천**
- lm-evaluation-harness로 태스크/프롬프트/버전 고정하여 “재현 가능한 모델 비교” 체계를 만들기 ([github.com](https://github.com/EleutherAI/lm-evaluation-harness?ref=Technology&utm_source=openai))  
- EvalPlus로 HumanEval+ 파이프라인을 CI에 붙이고, 내부 코드베이스 기반의 추가 테스트(레포 단위/성능/보안)를 설계하기 ([github.com](https://github.com/evalplus/evalplus?utm_source=openai))

원하면, 당신 팀의 실제 시나리오(예: RAG, 코드 어시스턴트, 티켓 분류, 정책 QA)에 맞춰 **“MMLU/HumanEval 점수를 어떻게 가중치로 쓰고, 어떤 커스텀 eval을 추가해야 하는지”**까지 의사결정 템플릿 형태로 같이 설계해 드릴 수 있어요.