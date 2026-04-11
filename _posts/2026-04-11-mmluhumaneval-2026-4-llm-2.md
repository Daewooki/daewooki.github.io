---
title: "MMLU·HumanEval 점수, 이제 그대로 믿으면 위험한 이유 — 2026년 4월 기준 LLM 벤치마크 해석법"
date: 2026-04-11 06:36:22 +0900
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
LLM을 도입할 때 가장 흔한 질문은 “그래서 **성능이 얼마나 좋아요?**”입니다. 이때 가장 먼저 등장하는 지표가 MMLU(지식/추론)와 HumanEval(코딩) 같은 표준 benchmark 점수죠. 문제는 2026년 현재, 이 점수들이 **(1) 포화(saturation)**, **(2) 데이터 오염(contamination)**, **(3) 벤치마크 자체 오류(ground-truth errors)**, **(4) 측정 방식의 허점(pass@k의 해석, 테스트 커버리지)** 때문에 “현업 성능”과 점점 멀어지고 있다는 점입니다.  
특히 MMLU는 “상위 모델 간 점수 차가 너무 작아” 변별력이 떨어진다는 지적이 많고, MMLU의 정답 라벨 오류를 교정한 MMLU-Redux 같은 작업도 등장했습니다. ([lmmarketcap.com](https://lmmarketcap.com/trackers/benchmark-saturation?utm_source=openai))  
HumanEval 역시 pass@k라는 지표가 “샘플을 여러 번 뽑으면 올라가는” 구조라, **단일 응답 품질**과는 다른 의미를 가질 수 있고, 기존 테스트가 얕아 오답이 통과하는 문제를 보완한 HumanEval+ / EvalPlus 계열도 널리 인용됩니다. ([github.com](https://github.com/openai/human-eval?utm_source=openai))

---

## 🔧 핵심 개념
### 1) MMLU를 해석할 때의 3가지 함정
- **Saturation(포화)**: 상위권 모델이 90%대에 몰리면, +0.5%p 차이는 “실제 능력 차”라기보다 *프롬프트/샷 수/서빙 세팅 차*일 가능성이 커집니다. 2026-04-11 기준으로 MMLU가 “saturated”로 표시되는 트래커도 있습니다. ([lmmarketcap.com](https://lmmarketcap.com/trackers/benchmark-saturation?utm_source=openai))  
- **Ground-truth errors(정답 오류)**: “정답 데이터가 틀린 문제”가 있으면, 모델 점수는 능력이 아니라 **라벨 노이즈에 대한 운**을 반영하게 됩니다. MMLU를 수작업 재주석해 오류를 분석하고, 교정 세트를 만든 MMLU-Redux 연구가 대표적입니다(일부 서브셋에서 오류 비율이 매우 높다고 보고). ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  
- **Contamination(오염)**: 모델이 학습 중에 벤치마크(또는 매우 유사한 문항)를 “봤다면” 점수는 일반화가 아니라 **기억력**이 됩니다. 2026년에도 benchmark contamination을 실무 리스크로 강하게 경고하는 글/연구가 계속 나옵니다. ([mbrenndoerfer.com](https://mbrenndoerfer.com/writing/benchmark-contamination-llm-detection-mitigation?utm_source=openai))  

### 2) MMLU-Pro가 나온 이유: “더 어렵게” + “더 견고하게”
MMLU-Pro는 MMLU의 한계를 보완하려는 시도로, 더 어려운 문항/구성으로 robustness를 높이려는 방향을 제시합니다. 다만 Pro 계열 역시 평가 harness/출력 파싱 방식 등 “운영 디테일”에 성능이 흔들릴 수 있어, 점수만 떼어보면 오해하기 쉽습니다. ([proceedings.neurips.cc](https://proceedings.neurips.cc/paper_files/paper/2024/file/ad236edc564f3e3156e1b2feafb99a24-Paper-Datasets_and_Benchmarks_Track.pdf?utm_source=openai))  

### 3) HumanEval과 pass@k: “코딩 실력”이 아니라 “샘플링 전략”을 재는 경우가 많다
HumanEval은 unit test로 기능적 정답 여부를 확인하고, 보통 **pass@k**로 “k번 뽑아 하나라도 맞으면 성공”을 봅니다. 이때 k가 커질수록 점수는 구조적으로 올라갑니다. OpenAI의 HumanEval harness도 pass@k 계산/제약(샘플 수가 k보다 작으면 평가 불가)을 명시합니다. ([github.com](https://github.com/openai/human-eval?utm_source=openai))  
또한 테스트가 충분히 촘촘하지 않으면 “틀린 코드가 통과”할 수 있는데, 이를 보완하려고 테스트를 대폭 늘려 pass rate가 실제로 내려가는 현상을 보인 EvalPlus/HumanEval+ 계열이 유명합니다. ([app.argminai.com](https://app.argminai.com/arxiv-dashboard/papers/2305.01210v3?utm_source=openai))  
그리고 2024~현재에는 HumanEval/MBPP의 한계를 지적하며 **LiveCodeBench**처럼 “오염에 강하고, 더 현실적인 코딩 평가”를 지향하는 benchmark도 확산되었습니다. ([arxiv.org](https://arxiv.org/abs/2403.07974?utm_source=openai))  

---

## 💻 실전 코드
아래 코드는 **(A) HumanEval 스타일 pass@k를 직접 계산**하고, **(B) MMLU/MMLU-Pro/MMLU-Redux처럼 MCQ(객관식) 평가에서 “정답률 + 불확실성(bootstrap CI)”**를 같이 보는 최소 골격입니다.  
실무에서는 이 뼈대에 “프롬프트/샷 수/temperature/seed/서빙 파라미터/데이터 버전”을 모두 기록해 재현성을 확보해야 합니다.

```python
# python 3.10+
# pip install numpy

import math
import random
import numpy as np

def humaneval_pass_at_k(n: int, c: int, k: int) -> float:
    """
    HumanEval에서 널리 쓰이는 unbiased pass@k estimator 형태.
    n: 생성 샘플 수
    c: 그 중 unit test 통과 샘플 수
    k: k개를 뽑았을 때(하나라도 맞으면 성공) 확률 추정
    """
    if k > n:
        raise ValueError("k must be <= n (HumanEval harness도 이 케이스는 평가하지 않음).")
    if c == 0:
        return 0.0
    if n - c < k:
        return 1.0
    # 1 - C(n-c, k) / C(n, k)
    # 조합이 커질 수 있으니 log/누적곱으로 안정화
    num = 1.0
    den = 1.0
    # product_{i=0..k-1} (n-c-i)/(n-i)
    for i in range(k):
        num *= (n - c - i)
        den *= (n - i)
    return 1.0 - (num / den)

def mcq_accuracy(preds, labels) -> float:
    """MMLU류 객관식: top-1 정답률(EM)만 계산하는 단순 버전"""
    correct = sum(int(p == y) for p, y in zip(preds, labels))
    return correct / len(labels)

def bootstrap_ci(acc_fn, preds, labels, iters=2000, seed=42, alpha=0.05):
    """
    점수 차이가 작은(MMLU 포화) 상황에서 필수:
    bootstrap으로 신뢰구간을 뽑아 '유의미한 차이인지' 판단 보조
    """
    rng = random.Random(seed)
    n = len(labels)
    stats = []
    for _ in range(iters):
        idx = [rng.randrange(n) for _ in range(n)]
        sp = [preds[i] for i in idx]
        sl = [labels[i] for i in idx]
        stats.append(acc_fn(sp, sl))
    stats.sort()
    lo = stats[int((alpha/2) * iters)]
    hi = stats[int((1 - alpha/2) * iters)]
    return float(np.mean(stats)), (lo, hi)

if __name__ == "__main__":
    # (A) HumanEval pass@k 예시
    n, c = 200, 120  # 200개 생성 중 120개 통과했다고 가정
    for k in [1, 5, 10, 50]:
        print("pass@{} = {:.3f}".format(k, humaneval_pass_at_k(n, c, k)))

    # (B) MMLU류 MCQ 예시 + bootstrap CI
    labels = ["A","C","B","D","A","B","C","D","A","B"]
    preds  = ["A","C","D","D","A","B","C","A","A","B"]
    acc = mcq_accuracy(preds, labels)
    mean_acc, (lo, hi) = bootstrap_ci(mcq_accuracy, preds, labels)
    print(f"MCQ EM acc={acc:.3f}, bootstrap mean={mean_acc:.3f}, 95% CI=({lo:.3f},{hi:.3f})")
```

---

## ⚡ 실전 팁
1) **MMLU 점수는 “점수”가 아니라 “실험 설정의 함수”로 보세요**  
   - few-shot(0/5-shot), system prompt, 출력 형식 강제, temperature=0 여부만 바뀌어도 랭킹이 바뀝니다. 포화된 벤치마크일수록 더 심합니다. ([lmmarketcap.com](https://lmmarketcap.com/trackers/benchmark-saturation?utm_source=openai))  

2) **MMLU-Redux 같은 “클린 데이터”로 재평가하는 습관**  
   - 모델 간 차이가 0.x%p라면, 라벨 오류가 그보다 클 수 있습니다. “원본 MMLU 점수”만 보고 결론 내리지 말고, 오류 교정 세트/대체 세트(MMLU-Redux, MMLU-Pro, GPQA 등)를 같이 보세요. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  

3) **HumanEval은 pass@1과 pass@k를 분리해서 읽기**
   - pass@k가 높다고 “한 번에 잘 코딩한다”는 뜻이 아닙니다. 샘플링을 많이 할수록 유리하고, rerank/selection 전략이 개입하면 점수가 더 올라갑니다. 구매/도입 관점이면 **pass@1 + 실패 패턴**이 더 중요합니다. ([github.com](https://github.com/openai/human-eval?utm_source=openai))  

4) **HumanEval 단독 사용 금지: 테스트 강화/오염 저항 벤치마크를 병행**
   - HumanEval은 공개된 지 오래되어 contamination 리스크가 있고, 테스트 커버리지가 얕을 수 있습니다. EvalPlus(HumanEval+)처럼 테스트를 늘린 평가나, LiveCodeBench처럼 오염에 강한 벤치마크를 같이 보세요. ([app.argminai.com](https://app.argminai.com/arxiv-dashboard/papers/2305.01210v3?utm_source=openai))  

5) **점수 차이 해석에 통계(신뢰구간) 넣기**
   - “92.1 vs 92.6”은 대부분 의미 없는 차이일 수 있습니다. bootstrap CI를 같이 제시하면, 조직 내 의사결정(모델 선정/비용 대비 성능)에 훨씬 정직해집니다.

---

## 🚀 마무리
2026년 4월 기준으로 MMLU와 HumanEval은 여전히 “공통 언어”이긴 하지만, 그대로 믿기엔 **포화·오염·라벨 오류·측정 허점**이 누적된 상태입니다. ([lmmarketcap.com](https://lmmarketcap.com/trackers/benchmark-saturation?utm_source=openai))  
실무에서의 결론은 단순합니다.

- MMLU: **MMLU-Pro / MMLU-Redux 같은 대체·정제 세트 + 통계적 해석(CI)**를 함께 가져가라. ([proceedings.neurips.cc](https://proceedings.neurips.cc/paper_files/paper/2024/file/ad236edc564f3e3156e1b2feafb99a24-Paper-Datasets_and_Benchmarks_Track.pdf?utm_source=openai))  
- HumanEval: **pass@1 중심 + 강화된 테스트(EvalPlus/HumanEval+) + 오염 저항 벤치(LiveCodeBench)**를 묶어서 보라. ([app.argminai.com](https://app.argminai.com/arxiv-dashboard/papers/2305.01210v3?utm_source=openai))  

다음 학습으로는 (1) LiveCodeBench, SWE-bench류 “agent/레포 단위” 평가가 왜 필요한지, (2) contamination 탐지/완화(데이터 중복, near-dup, paraphrase) 방법론, (3) 내부 제품 로그 기반 “in-the-loop eval” 설계를 추천합니다.