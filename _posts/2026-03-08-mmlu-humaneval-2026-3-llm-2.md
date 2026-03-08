---
title: "MMLU와 HumanEval, 점수 하나로 모델을 뽑으면 망하는 이유: 2026년 3월 기준 LLM 벤치마크 해석법"
date: 2026-03-08 02:48:17 +0900
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
LLM을 “평가”한다는 건 결국 **의사결정(모델 선택, 배포, 튜닝, 비용 최적화)** 을 위한 숫자를 만드는 일입니다. 그런데 2026년 3월 시점에서 MMLU, HumanEval 같은 고전 벤치마크는 여전히 널리 쓰이면서도, **점수 자체가 비교 불가능하게 만들어지는 케이스**가 너무 많습니다. 특히
- MMLU는 **prompting/shot 수/CoT 유무**에 따라 점수가 크게 달라지고,
- HumanEval은 **pass@k(샘플링 기반)** 이라서 “모델 능력”과 “추론 전략/샘플 수/온도”가 섞여버립니다.

게다가 Stanford CRFM은 “같은 MMLU 점수”라도 평가 방식이 제각각이라 **리더보드 간 비교가 위험**하다고 지적하며, HELM에서 표준화된 방식으로 다시 측정하는 접근을 제안했습니다. ([crfm.stanford.edu](https://crfm.stanford.edu/2024/05/01/helm-mmlu.html))  
OpenAI도 과거에 `simple-evals`로 MMLU/HumanEval 등을 **간단한 레퍼런스 구현** 형태로 공개했지만(그리고 2025년 7월 이후 신규 모델/결과 업데이트는 중단), 중요한 건 “점수”가 아니라 **재현 가능한 평가 파이프라인**이라는 메시지에 가깝습니다. ([github.com](https://github.com/openai/simple-evals))

이 글은 2026년 3월 기준으로, MMLU/HumanEval을 “모델 성능”으로 번역해 읽는 법(=해석 프레임)을 기술 심층 관점에서 정리합니다.

---

## 🔧 핵심 개념
### 1) MMLU: “지식+추론” 테스트가 아니라 “프로토콜” 테스트가 되어버린 이유
MMLU는 57개 과목의 객관식 QA로 구성되고, 점수는 보통 accuracy(정답률)로 표현됩니다. 문제는 **평가 프로토콜이 조금만 달라도** 점수가 달라져서, 서로 다른 문서/리더보드의 MMLU를 “모델 비교”로 쓰기 어렵다는 점입니다. Stanford CRFM은 다음을 대표적인 비교 불가능 원인으로 꼽습니다: 동일 모델이라도 **non-standard prompting(예: 특정 CoT 라우팅), 템플릿 비공개, 프레임워크 미공개, 내부 스냅샷 사용** 등으로 점수가 부풀거나 재현이 안 된다는 것. ([crfm.stanford.edu](https://crfm.stanford.edu/2024/05/01/helm-mmlu.html))

**해석 팁(중요):**  
MMLU 점수는 “모델의 절대 지능”이 아니라, 최소한 아래가 고정된 경우에만 비교 가능합니다.
- 동일 prompt 템플릿
- 동일 shot 수(예: 5-shot)
- 동일 decoding(temperature 등)
- 동일 정답 선택 규칙(예: logprob 기반 vs 텍스트 파싱)

또 하나의 흐름은 **MMLU의 품질 문제(정답 오류/애매한 문항)** 입니다. 이 이슈를 반영해 “MMLU-Redux(정제/수정)” 같은 파생 벤치마크가 등장했고, MMLU 자체를 대체/보완하려는 움직임이 커졌습니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))

### 2) HumanEval: pass@k는 “능력”이 아니라 “확률+샘플링”이다
HumanEval은 코드 생성 벤치마크로, 모델이 생성한 코드가 유닛 테스트를 통과하는지로 **functional correctness**를 측정합니다. 공식 구현은 샘플(jsonl)을 받아 테스트를 실행하고 `pass@1`, `pass@10`, `pass@100` 등을 계산합니다. ([github.com](https://github.com/openai/human-eval?utm_source=openai))  

여기서 핵심은:
- **pass@1**: 한 번 뽑아서 맞을 확률
- **pass@k**: k번 뽑으면 “적어도 하나는 맞을” 확률(샘플링을 많이 할수록 올라감)

즉 HumanEval 점수는 “모델이 코딩을 잘한다” + “추론 시 샘플링 전략이 공격적이다”가 섞입니다. 그래서 실무에서는 “우리 서비스는 1번만 생성하는가? rerank/repair loop가 있는가?” 같은 **제품 추론 전략**과 함께 읽어야 합니다.

추가로, HumanEval은 테스트 수가 상대적으로 적고(문항당 평균 7~8개 테스트라는 요약도 흔합니다), 과최적화/오염(benchmark contamination) 논쟁이 반복되어 왔고, 더 빡센 테스트를 추가한 HumanEval+ 같은 강화형도 널리 쓰입니다. ([ibm.com](https://www.ibm.com/think/topics/humaneval?utm_source=openai))

### 3) “벤치마크 포화(saturation)”와 대표성 문제
2025~2026으로 갈수록 커뮤니티는 “MMLU-Pro 같은 것도 결국 포화된다”는 이야기를 계속합니다(새롭고 어려운 벤치마크가 계속 등장). 이때 중요한 메타 관점은:  
- **벤치마크 점수 행렬 자체를 분석**해 “서로 강하게 상관된 데이터셋/모델 묶음”을 찾고, 적은 subset으로도 랭킹을 유지할 수 있다는 연구(예: SimBA)가 등장했다는 점입니다. 이는 “벤치마크 여러 개 돌릴수록 더 정확”이 항상 성립하지 않음을 시사합니다. ([arxiv.org](https://arxiv.org/abs/2510.17998))

---

## 💻 실전 코드
아래는 **MMLU/HumanEval을 ‘점수’가 아니라 ‘재현 가능한 실험’으로 다루는 최소 파이프라인** 예시입니다.

- HumanEval: OpenAI `human-eval` 레포 포맷(jsonl)로 샘플을 만들고, 공식 스크립트로 pass@k를 계산 ([github.com](https://github.com/openai/human-eval?utm_source=openai))  
- MMLU: 여기서는 “평가 스크립트”보다 더 중요한 **실험 메타데이터(shot/prompt/decoding)를 고정하고 기록**하는 코드를 보여줍니다(실무에서 이게 없으면 점수는 의미가 없어집니다). 또한 OpenAI `simple-evals`가 MMLU/HumanEval 레퍼런스 구현을 제공했다는 점을 참고로 링크드 프로젝트를 선택하면 좋습니다. ([github.com](https://github.com/openai/simple-evals))

```python
"""
Reproducible eval skeleton for MMLU + HumanEval.

- Stores evaluation protocol (prompting/decoding) as structured metadata.
- Produces HumanEval jsonl compatible with openai/human-eval.
- Intentionally minimal: replace `call_model()` with your actual LLM client.

Prereqs (conceptual):
  - human-eval: https://github.com/openai/human-eval  (for running pass@k)  # see citations
"""

from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

# -----------------------------
# 1) Protocol is the "real benchmark"
# -----------------------------
@dataclass(frozen=True)
class EvalProtocol:
    # MMLU-related
    mmlu_n_shot: int
    mmlu_prompt_template_id: str  # version your template explicitly
    mmlu_answer_extraction: str   # e.g., "first_token_logprob", "regex_letter", ...

    # Decoding / sampling (affects both MMLU & HumanEval!)
    temperature: float
    top_p: float
    max_tokens: int
    seed: int

    # Bookkeeping
    evaluator: str
    created_at_utc: str


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# -----------------------------
# 2) Replace with real LLM call
# -----------------------------
def call_model(prompt: str, protocol: EvalProtocol) -> str:
    """
    Stub. In practice:
      - pin model version (exact checkpoint / API snapshot)
      - log request+response
      - keep decoding params identical across runs
    """
    raise NotImplementedError("Connect your LLM client here.")


# -----------------------------
# 3) HumanEval sample writer (jsonl)
# -----------------------------
def write_humaneval_samples(
    out_jsonl_path: str,
    task_to_prompt: Dict[str, str],
    protocol: EvalProtocol,
    samples_per_task: int = 1,
) -> None:
    """
    human-eval expects jsonl rows like:
      {"task_id": "...", "completion": "code only"}
    (prompt is NOT included in completion)
    """
    os.makedirs(os.path.dirname(out_jsonl_path), exist_ok=True)
    with open(out_jsonl_path, "w", encoding="utf-8") as f:
        for task_id, prompt in task_to_prompt.items():
            for _ in range(samples_per_task):
                completion = call_model(prompt, protocol)
                row = {"task_id": task_id, "completion": completion}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Store protocol next to outputs for reproducibility
    meta_path = out_jsonl_path + ".protocol.json"
    with open(meta_path, "w", encoding="utf-8") as mf:
        json.dump(asdict(protocol), mf, ensure_ascii=False, indent=2)


# -----------------------------
# 4) MMLU run record (protocol + raw outputs)
# -----------------------------
def save_mmlu_predictions(
    out_path: str,
    examples: List[Dict[str, Any]],
    protocol: EvalProtocol,
) -> None:
    """
    examples: [{"id": "...", "prompt": "...", "gold": "C"}, ...]
    Save raw model outputs; scoring is separate to avoid "silent" changes.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    outputs = []
    for ex in examples:
        raw = call_model(ex["prompt"], protocol)
        outputs.append(
            {
                "id": ex["id"],
                "gold": ex["gold"],
                "raw_output": raw,
            }
        )

    artifact = {
        "protocol": asdict(protocol),
        "predictions": outputs,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    protocol = EvalProtocol(
        mmlu_n_shot=5,
        mmlu_prompt_template_id="mmlu_v3_simple_standardized",  # version your prompt
        mmlu_answer_extraction="regex_letter_A-D",
        temperature=0.2,
        top_p=1.0,
        max_tokens=1024,
        seed=42,
        evaluator="yourname@company",
        created_at_utc=utc_now_iso(),
    )

    # Example placeholders
    humaneval_tasks = {
        "HumanEval/0": "### Problem...\n# (put real HumanEval prompt here)\n",
    }
    mmlu_examples = [
        {"id": "mmlu_demo_0", "prompt": "Question... A) ... B) ...", "gold": "B"},
    ]

    # Outputs
    # write_humaneval_samples("artifacts/humaneval_samples.jsonl", humaneval_tasks, protocol, samples_per_task=10)
    # save_mmlu_predictions("artifacts/mmlu_raw_predictions.json", mmlu_examples, protocol)
    pass
```

---

## ⚡ 실전 팁
1) **MMLU는 “점수”보다 “프로토콜 diff”를 먼저 보세요**  
서로 다른 MMLU 수치를 비교해야 한다면, (1) shot, (2) CoT 사용 여부, (3) 정답 추출 방식, (4) 프레임워크 공개 여부부터 확인하세요. Stanford CRFM이 지적했듯, 비표준 prompting은 비교를 깨뜨리는 대표 원인입니다. ([crfm.stanford.edu](https://crfm.stanford.edu/2024/05/01/helm-mmlu.html))

2) **HumanEval은 pass@1과 pass@k를 분리 해석**  
- 제품이 단발 생성이면 pass@1에 가까움  
- “generate N개 → 테스트/선별 → repair” 루프가 있으면 pass@k가 의미 있음  
따라서 모델 카드에 HumanEval pass@10만 있으면, 그 모델이 “한 번에” 잘 짠다는 뜻이 아닙니다.

3) **오염(contamination)과 포화를 전제로, ‘강화형/정제형’을 같이 보세요**  
MMLU는 오류/애매 문항 문제로 Redux 계열이 나왔고, HumanEval도 HumanEval+처럼 테스트를 대폭 강화한 평가가 등장했습니다. “원본 점수”만 보면 과대평가할 수 있습니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))

4) **리더보드 숫자보다 “raw output + 재채점 가능성”을 남기세요**  
점수는 나중에 스코어링 로직이 바뀌면 의미가 흔들립니다. 반면 raw output을 남기면
- extraction rule을 바꿔 재채점(MMLU)
- 새로운 테스트 추가(HumanEval+ 스타일)
가 가능합니다.

5) **벤치마크를 늘리는 게 항상 더 좋은 평가가 아니다**
SimBA 같은 연구가 보여주듯, 벤치마크 내부에는 강한 상관 구조가 있고 일부 subset만으로도 랭킹이 거의 유지될 수 있습니다. 즉 “많이 돌리기”가 아니라 “다양한 실패 모드 커버”가 목표여야 합니다. ([arxiv.org](https://arxiv.org/abs/2510.17998))

---

## 🚀 마무리
2026년 3월 기준 MMLU와 HumanEval은 여전히 유용하지만, **그 자체가 성능의 진실**이라기보다 **프로토콜/샘플링/오염/포화까지 포함한 ‘측정 시스템’**입니다.  
- MMLU는 표준화된 프롬프트/shot/추출 규칙이 없으면 비교가 깨지고 ([crfm.stanford.edu](https://crfm.stanford.edu/2024/05/01/helm-mmlu.html))  
- HumanEval은 pass@k가 “샘플링 전략”을 포함한 값이며, 강화형(HumanEval+)도 함께 봐야 합니다. ([github.com](https://github.com/openai/human-eval?utm_source=openai))

다음 학습으로는:
- HELM MMLU의 표준화 철학(“평가 재현성” 관점) ([crfm.stanford.edu](https://crfm.stanford.edu/2024/05/01/helm-mmlu.html))
- MMLU-Redux 같은 정제형 벤치마크의 설계 의도 ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))
- HumanEval 공식 레포의 pass@k 산출 방식/제약 ([github.com](https://github.com/openai/human-eval?utm_source=openai))  
을 추천합니다.

원하시면, **(1) MMLU/HumanEval을 사내 CI에 붙이는 구성(artifact/seed/logging), (2) 모델 A/B 비교를 통계적으로 처리(신뢰구간/부트스트랩), (3) 오염 점검 체크리스트**까지 포함한 “실무 평가 템플릿” 버전으로 확장해드릴게요.