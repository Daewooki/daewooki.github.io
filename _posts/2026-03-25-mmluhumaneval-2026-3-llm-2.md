---
title: "MMLU·HumanEval 점수, 이제 그대로 믿으면 안 되는 이유: 2026년 3월 LLM 평가 벤치마크 심층 해부"
date: 2026-03-25 02:51:28 +0900
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
2026년 3월에도 여전히 많은 모델 릴리스 노트가 **MMLU(지식/이해)**, **HumanEval(코드 생성)** 점수를 “성능”의 대표 지표처럼 내세웁니다. 하지만 현업에서 모델을 붙여보면, 리더보드 상위권인데도 **도메인 QA에서 헛소리**를 하거나, HumanEval은 잘하는데 **SWE-bench류 실제 수정 작업**에서는 무너지는 경우가 흔합니다.  
문제는 벤치마크 자체가 나쁘다기보다, (1) **측정 방식이 너무 단일 점수로 소비**되고, (2) **오염(contamination)/누수(leakage)** 가능성이 커졌고, (3) 프롬프트/온도/샘플링/채점기(judge) 등 **실험 조건이 점수만큼 중요**해졌기 때문입니다. 특히 OpenAI의 `simple-evals`처럼 MMLU/HumanEval을 포함해 “간단히 재현” 가능한 프레임워크가 널리 쓰였지만, 해당 레포는 **2025년 7월 이후 신규 모델/결과 업데이트를 중단**한다고 명시되어 있어, “최신 점수”를 말할 때는 더더욱 출처와 조건을 확인해야 합니다. ([github.com](https://github.com/openai/simple-evals?utm_source=openai))

---

## 🔧 핵심 개념
### 1) MMLU: “지식+추론”처럼 보이지만, 사실은 “객관식 선택”의 합
- MMLU는 57개 과목에 걸친 객관식 문제로 **폭넓은 언어 이해/지식**을 측정하는 대표 지표입니다. ([deepwiki.com](https://deepwiki.com/openai/simple-evals/4-command-line-interface?utm_source=openai))  
- 핵심 함정은 **점수의 분산 요인**이 많다는 겁니다.
  - 0-shot vs 5-shot
  - 선택지/질문 포맷(프롬프트 템플릿)
  - temperature(무작위성)
  - “정답만 출력” 같은 출력 제약
- 최근에는 오염 이슈를 줄이려는 시도로 **MMLU-CF(Contamination-free)** 같은 변형 벤치마크가 제안되기도 했습니다. “기존 MMLU 점수”와 “오염을 줄인 MMLU-CF 점수” 사이의 괴리는, 우리가 리더보드의 단일 점수에 과적합되어 있음을 보여줍니다. ([arxiv.org](https://arxiv.org/abs/2412.15194?utm_source=openai))

### 2) HumanEval: 실행 기반이라 “정직”하지만, 164문항의 한계가 너무 크다
- HumanEval은 164개 파이썬 문제를 **테스트 실행(pass@1 등)** 으로 채점하는 구조라 “LLM-judge”보다 객관적입니다. ([deepwiki.com](https://deepwiki.com/openai/simple-evals/4-command-line-interface?utm_source=openai))  
- 하지만 164문항은 너무 작고, 시간이 지나며 널리 학습/복제/유통되면서 **누수 가능성**이 커집니다. 또한 “짧은 함수 생성” 중심이라, 실제 업무의 **리팩터링/버그 수정/테스트 추가/의존성 이해**와는 다른 능력을 재기 쉽습니다. (그래서 업계는 HumanEval 외에 SWE-bench 등도 같이 보려는 흐름이 강합니다. 이는 여러 리더보드가 함께 제공하는 항목 구성에서도 드러납니다.) ([codesota.com](https://www.codesota.com/llm/?utm_source=openai))  
- 한편, HumanEval의 언어적 범위를 확장한 **mHumanEval(다국어 코드 생성 평가)** 같은 연구도 나와 “영어 설명 + 파이썬 코드” 형태에 편향된 기존 측정을 보완하려는 움직임이 있습니다. ([aclanthology.org](https://aclanthology.org/2025.naacl-long.570/?utm_source=openai))

### 3) “점수”가 아니라 “평가 설계”가 실력이다
2026년의 실무 LLM 평가는 “벤치마크를 돌렸다”가 끝이 아니라 아래를 함께 설계해야 합니다.
- **재현성**: 프롬프트/seed/temperature/샘플 수 고정
- **통계적 안정성**: 표본이 작은 벤치마크는 ±1~2%가 의미 없을 수 있음
- **오염 방어**: 변형 벤치마크(MMLU-CF 등)나 새 문항이 공급되는 평가를 병행
- **사용 사례 적합성**: 코드 생성은 HumanEval만으로 부족 → 실제 변경 작업/레포 맥락 기반 평가 추가

---

## 💻 실전 코드
아래 코드는 `openai/simple-evals` 스타일로 **MMLU/HumanEval 결과를 “숫자”로만 보지 않고**, 실험 조건을 고정한 뒤 결과를 JSON으로 저장해 **비교 가능하게 만드는 최소 루프**입니다.  
(실제 벤치마크 데이터/러너는 프레임워크마다 다르므로, 여기서는 현업에서 바로 적용 가능한 “평가 러너 골격”에 집중합니다. `simple-evals`가 MMLU/HumanEval을 포함하고, CLI로 실행되는 구조라는 점은 공개 문서에 나와 있습니다.) ([deepwiki.com](https://deepwiki.com/openai/simple-evals/4-command-line-interface?utm_source=openai))

```python
# python
# 실행: python eval_runner.py
# 목적: (1) 평가 조건을 고정하고 (2) 결과를 누적 저장하여 (3) 점수 해석이 가능하게 만들기

import json
import os
import random
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, List

@dataclass
class EvalConfig:
    model: str
    temperature: float = 0.0
    max_tokens: int = 512
    seed: int = 42
    prompt_template_version: str = "v1"  # 프롬프트 바뀌면 점수도 바뀜: 버전으로 잠금
    shots: int = 0                       # 0-shot / 5-shot 등
    run_id: str = ""

def set_determinism(seed: int):
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

def run_mmlu_stub(cfg: EvalConfig) -> Dict[str, Any]:
    """
    실제 MMLU는 57개 과목 객관식 평가.
    여기서는 예시로 '과목별 정확도' 구조를 흉내만 냄.
    포인트: 결과를 단일 평균만 저장하지 말고 breakdown을 저장.
    """
    # TODO: simple-evals / lm-eval-harness / helm 등 실제 러너 호출로 교체
    subjects = ["math", "law", "medicine", "philosophy"]
    # 난수는 예시(재현성 보여주기 위해 seed 고정)
    rng = random.Random(cfg.seed + cfg.shots)
    per_subject = {s: round(rng.uniform(0.55, 0.85), 4) for s in subjects}
    avg = round(sum(per_subject.values()) / len(subjects), 4)
    return {"metric": "accuracy", "avg": avg, "per_subject": per_subject}

def run_humaneval_stub(cfg: EvalConfig) -> Dict[str, Any]:
    """
    실제 HumanEval은 코드 실행 기반 pass@k 측정.
    포인트: pass@1만 보지 말고 실패 유형/재시도 정책 등을 같이 저장.
    """
    rng = random.Random(cfg.seed)
    pass_at_1 = round(rng.uniform(0.60, 0.90), 4)
    # 실무에서는 "timeout", "wrong-answer", "syntax-error" 같은 분류를 수집하는 게 도움 됨
    failure_profile = {
        "timeout": rng.randint(0, 5),
        "wrong_answer": rng.randint(5, 20),
        "runtime_error": rng.randint(0, 8),
    }
    return {"metric": "pass@1", "value": pass_at_1, "failure_profile": failure_profile}

def main():
    cfg = EvalConfig(
        model="your-llm-name",
        temperature=0.0,
        max_tokens=512,
        seed=42,
        prompt_template_version="v1",
        shots=0,
        run_id=time.strftime("%Y%m%d-%H%M%S"),
    )
    set_determinism(cfg.seed)

    # (중요) 같은 모델이라도 조건(temperature/shots/prompt)이 다르면 점수 비교가 무의미해짐
    result = {
        "config": asdict(cfg),
        "mmlu": run_mmlu_stub(cfg),
        "humaneval": run_humaneval_stub(cfg),
    }

    os.makedirs("eval_results", exist_ok=True)
    out_path = f"eval_results/{cfg.model}_{cfg.run_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Saved: {out_path}")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

---

## ⚡ 실전 팁
1) **MMLU는 “평균”보다 “과목별 분포”를 보세요**  
MMLU 평균 1~2% 올랐다고 좋아하기 전에, 법/의학/수학 등 **특정 과목이 떨어졌는지** 확인해야 합니다. 실제 제품은 “평균 사용자”가 아니라 “당신의 사용자”가 쓰기 때문입니다. 또한 최근 연구들은 MMLU 점수가 **작은 교란(프롬프트/표현 변화)** 에도 유의미하게 흔들릴 수 있음을 지적하며, 단일 점수에 대한 과신을 경계합니다. ([arxiv.org](https://arxiv.org/abs/2502.07445?utm_source=openai))

2) **오염(contamination) 방어: “동일 벤치마크 반복” 대신 “대체/변형”을 병행**  
MMLU-CF 같은 contamination-free 계열을 같이 보거나, 최소한 “내 모델이 학습 데이터에 해당 벤치마크가 섞였는지” 리스크를 문서화하세요. 벤치마크 오염은 2024~2026 사이 계속 커진 주제이고, 평가 생태계 자체를 바꿔야 한다는 문제 제기도 나옵니다. ([arxiv.org](https://arxiv.org/abs/2412.15194?utm_source=openai))

3) **HumanEval은 ‘코드 실행 통과’까지만 말해준다: 실제 개발 과업으로 확장하라**  
HumanEval은 실행 기반이라 깔끔하지만, 작은 세트(164문항)와 과업 편향이 큽니다. 실무에서는
- 레포 컨텍스트 포함(여러 파일)
- 테스트 추가/수정
- 버그 재현 후 패치  
같은 형태의 평가를 추가해야 “코딩 잘함”이 “일 잘함”으로 연결됩니다. 리더보드 사이트들도 HumanEval 외에 SWE-bench 같은 항목을 함께 보여주는 이유가 여기에 있습니다. ([codesota.com](https://www.codesota.com/llm/?utm_source=openai))

4) **점수 비교의 전제조건: 프롬프트/샘플링/채점기까지 ‘버전 고정’**  
특히 MMLU/HumanEval조차도, 러너에 따라 프롬프트 템플릿과 후처리가 달라집니다. `simple-evals` 문서에서도 MMLU/HumanEval이 “frozen”으로 묶여 있고, CLI 러너 구조가 명시되어 있듯, **도구/버전 자체가 실험 조건**입니다. ([deepwiki.com](https://deepwiki.com/openai/simple-evals/4-command-line-interface?utm_source=openai))

---

## 🚀 마무리
- MMLU는 범용 지식/이해의 좋은 출발점이지만, **객관식 평균 점수** 하나로 모델을 판단하면 실패합니다. 과목별 분포와 조건 고정이 필수입니다.  
- HumanEval은 실행 기반이라 강점이 있지만, **문항 수·과업 형태**가 제한적이어서 “실제 개발 능력”을 대변하지 못합니다.  
- 2026년의 핵심은 “벤치마크를 돌렸는가”가 아니라 **평가 설계를 했는가**입니다: 재현성, 오염 방어, 사용 사례 적합성, 결과 저장/비교 가능성.

다음 학습으로는 (1) MMLU-CF 같은 contamination-free 벤치마크의 생성/검증 방식, (2) 코드 평가에서 HumanEval을 넘어 레포 기반 과업(SWE-bench류)으로 확장하는 평가 파이프라인 설계를 추천합니다. ([arxiv.org](https://arxiv.org/abs/2412.15194?utm_source=openai))