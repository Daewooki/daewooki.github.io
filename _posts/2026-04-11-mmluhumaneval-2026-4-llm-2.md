---
title: "MMLU·HumanEval을 “점수”가 아니라 “측정 도구”로 읽는 법: 2026년 4월 기준 LLM 벤치마크 심층 해석"
date: 2026-04-11 02:53:23 +0900
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
LLM 성능을 숫자 하나로 요약하고 싶은 유혹은 강하지만, 2026년에는 그 방식이 오히려 의사결정을 망칩니다. MMLU는 상식/학술 지식의 폭을 빠르게 비교하는 데 유용했지만, 상위권 모델에서 점수 포화(saturation)와 프롬프트 민감도 문제가 계속 지적되어 왔고, 이를 보완하려는 흐름으로 MMLU-Pro 같은 “더 어렵고 더 견고한” 변형이 부상했습니다. ([artificialanalysis.ai](https://artificialanalysis.ai/evaluations/mmlu-pro?utm_source=openai))  
코딩 쪽의 HumanEval 역시 “164문제 pass@1”이라는 간명함 덕분에 널리 쓰이지만, 테스트 케이스가 얕아 overfitting/contamination을 가리기 어렵다는 비판이 커졌고, EvalPlus의 HumanEval+처럼 테스트를 대폭 확장해 “진짜 정답인지”를 더 세게 검증하는 쪽으로 발전하고 있습니다. ([evalplus.github.io](https://evalplus.github.io/?utm_source=openai))  

이 글에서는 **MMLU / (확장 흐름으로서) MMLU-Pro**, **HumanEval / HumanEval+**를 “점수 랭킹”이 아니라 **평가 설계(프롬프트, 채점, 지표)와 해석의 함정** 관점에서 뜯어보고, 실무에서 재현 가능한 mini-eval 코드를 함께 정리합니다.

---

## 🔧 핵심 개념
### 1) MMLU: 다과목 MCQ 정확도, 그런데 “정확도”만 보면 안 되는 이유
MMLU는 57개 과목의 multiple-choice 질문으로 구성되어 모델의 폭넓은 지식을 평가합니다. ([huggingface.co](https://huggingface.co/datasets/lighteval/mmlu?utm_source=openai))  
여기서 핵심은 **“정답률(accuracy)”이 모델 능력의 단일 척도처럼 보이지만, 실제로는 평가 파이프라인의 영향이 크다**는 점입니다.

- **Prompt formatting / few-shot example**: 같은 데이터라도 few-shot 구성과 예시 순서가 달라지면 점수가 흔들립니다.
- **Answer extraction**: 모델이 “A”를 출력했는지, “The answer is A”인지, 혹은 설명 중간에 A가 등장했는지에 따라 파서가 다르게 채점할 수 있습니다.
- **Token-probability 기반 vs generation 기반**: Stanford HELM은 최근 API 환경(일부는 logprob 미제공)에 맞춰 **모델이 답을 생성하도록 하는 방식(Multiple Choice Joint)**을 사용하고, 과거의 token probability 기반 방식에서 벗어났다고 명시합니다. ([crfm.stanford.edu](https://crfm.stanford.edu/2024/05/01/helm-mmlu.html?utm_source=openai))  

즉, MMLU 점수는 “모델” + “평가 구현”의 합성 결과입니다. 그래서 2026년에는 “MMLU 점수 몇 점”보다 **어떤 harness/프롬프트/파서로 측정했는지**가 더 중요해졌습니다. ([evalevalai.com](https://evalevalai.com/events/shared-task-every-eval-ever/?utm_source=openai))  

### 2) MMLU-Pro 흐름: 더 어렵게, 덜 흔들리게
MMLU-Pro는 난이도와 견고성을 높이기 위해 4지선다에서 10지선다로 확장하고, reasoning 성격을 강화했습니다. 또한 여러 프롬프트 스타일을 테스트했을 때 **프롬프트 변화에 따른 점수 변동이 MMLU 대비 작아졌다는 보고**가 있습니다. ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))  
실무 관점에서 이 변화는 “문제집을 더 어렵게 만들었다” 정도가 아니라, **리더보드 상위 모델 간 ‘미세한 점수 차’가 프롬프트 요행인지 실력 차인지 구분하기 쉬워지는 방향**이라는 의미가 있습니다.

### 3) HumanEval: pass@k의 의미와, 왜 “테스트 강화”가 필수인가
HumanEval은 docstring을 보고 Python 함수를 작성하는 164문제이며, 보통 pass@1을 대표 지표로 씁니다. ([lmmarketcap.com](https://lmmarketcap.com/benchmarks/humaneval?utm_source=openai))  
문제는 **원본 HumanEval의 테스트가 충분히 강하지 않으면 “그럴듯한 코드”가 통과**할 수 있다는 점입니다. 이 약점을 보완하기 위해 EvalPlus는 HumanEval을 **80배 규모로 테스트를 확장한 HumanEval+**를 제공한다고 밝힙니다. ([evalplus.github.io](https://evalplus.github.io/?utm_source=openai))  

정리하면:
- **pass@1**: “첫 시도에 통과” → 제품에서의 기본 UX와 유사하지만, 샘플링 전략/temperature에 크게 영향.
- **pass@k**: k번 생성 중 하나라도 통과하면 성공 → “에이전트가 재시도 가능한 환경”에는 더 현실적.
- **HumanEval+**: 같은 문제라도 **숨은 버그를 더 잘 잡는 테스트로 ‘정답’의 기준을 강화**.

---

## 💻 실전 코드
아래는 “완전한 lm-eval-harness급”은 아니지만, 팀 내부에서 **MMLU 스타일 MCQ + HumanEval 스타일 실행 기반 평가를 최소 단위로 재현**할 수 있는 코드입니다.  
포인트는 (1) **프롬프트 템플릿 고정**, (2) **파서 규칙 명시**, (3) **결과 로그를 남겨 재현성 확보**입니다.

```python
# 언어: python
# 목적: (1) MCQ(MMLU-like) accuracy, (2) code-eval(HumanEval-like) pass@1을 최소 구현
# 주의: 실제 HumanEval 데이터/테스트 러너(EvalPlus 등)를 쓰면 더 엄격해집니다.

from dataclasses import dataclass
import json, re, subprocess, tempfile, textwrap
from typing import List, Dict, Callable, Optional

@dataclass
class MCQItem:
    id: str
    question: str
    choices: List[str]  # ["A) ...", "B) ...", ...]
    answer: str         # "A" / "B" / ...

def mcq_prompt(item: MCQItem) -> str:
    # 프롬프트는 "항상 동일한 형식"이 핵심 (few-shot을 넣는다면 예시도 고정)
    choices_block = "\n".join(item.choices)
    return textwrap.dedent(f"""\
    You are taking a closed-book exam.
    Choose the single best answer. Reply with only one letter: A, B, C, D (or more if provided).

    Q: {item.question}
    {choices_block}

    Answer:
    """)

def parse_mcq_answer(text: str, valid: List[str]) -> Optional[str]:
    # 파서 규칙을 명시적으로: 첫 매칭 1글자만 인정
    m = re.search(r"\b([A-Z])\b", text.strip())
    if not m:
        return None
    a = m.group(1)
    return a if a in valid else None

def eval_mcq(items: List[MCQItem], call_llm: Callable[[str], str]) -> Dict:
    correct = 0
    rows = []
    for it in items:
        prompt = mcq_prompt(it)
        out = call_llm(prompt)
        pred = parse_mcq_answer(out, valid=[c[0] for c in it.choices])  # "A" from "A) ..."
        ok = (pred == it.answer)
        correct += int(ok)
        rows.append({"id": it.id, "pred": pred, "gold": it.answer, "raw": out})
    return {"accuracy": correct / max(1, len(items)), "details": rows}

# ---------------- Code Eval (HumanEval-like) ----------------

@dataclass
class CodeItem:
    id: str
    prompt: str        # 함수 설명 + 시그니처 유도
    test_code: str     # 단위 테스트 (unittest/pytest 스타일)
    entry: str         # 함수명

def run_python_with_timeout(code: str, timeout_s: int = 3) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        # -I: isolate(가능한 경우), 단 여기선 단순 실행
        r = subprocess.run(["python", path], capture_output=True, text=True, timeout=timeout_s)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False

def eval_code_pass_at_1(items: List[CodeItem], call_llm: Callable[[str], str]) -> Dict:
    passed = 0
    rows = []
    for it in items:
        # 모델이 "코드만" 내게 강제: 실무에선 더 강한 포맷터/샌드박스 필요
        prompt = textwrap.dedent(f"""\
        Write Python code that satisfies the specification.
        Return ONLY code. No markdown fences.

        Specification:
        {it.prompt}
        """)
        gen = call_llm(prompt)

        # 생성 코드 + 테스트 결합
        full = gen + "\n\n" + it.test_code
        ok = run_python_with_timeout(full, timeout_s=3)
        passed += int(ok)
        rows.append({"id": it.id, "pass@1": ok})
    return {"pass@1": passed / max(1, len(items)), "details": rows}

# ---------------- Example usage ----------------

def fake_llm(prompt: str) -> str:
    # 데모용 더미. 실제로는 OpenAI/Anthropic/로컬 모델 호출로 교체
    if "Choose the single best answer" in prompt:
        return "A"
    return "def add(a,b):\n    return a+b\n"

if __name__ == "__main__":
    mcq = [
        MCQItem(
            id="mcq1",
            question="Which is a property of a pure function?",
            choices=["A) No side effects", "B) Uses global state", "C) Depends on time", "D) Mutates inputs"],
            answer="A",
        )
    ]
    code_items = [
        CodeItem(
            id="code1",
            prompt="Implement function add(a, b) that returns the sum of a and b.",
            entry="add",
            test_code=textwrap.dedent("""\
            def _test():
                assert add(1,2)==3
                assert add(-1,1)==0
            _test()
            """),
        )
    ]

    mcq_res = eval_mcq(mcq, fake_llm)
    code_res = eval_code_pass_at_1(code_items, fake_llm)

    print(json.dumps({"mcq": mcq_res, "code": code_res}, ensure_ascii=False, indent=2))
```

---

## ⚡ 실전 팁
### 1) “MMLU 점수”를 볼 때 체크리스트(재현성/공정성)
- **Harness를 명시**: lm-eval-harness/HELM/사내 스크립트 등 구현체가 다르면 결과가 달라집니다. “같은 MMLU”라도 로그 포맷/프롬프트/파서가 달라질 수 있다는 문제의식이 공유되고 있습니다. ([evalevalai.com](https://evalevalai.com/events/shared-task-every-eval-ever/?utm_source=openai))  
- **Prompt/answer parsing 고정**: MCQ는 “한 글자만 출력” 같은 제약을 걸고, 파서가 실패하면 “랜덤 추측 처리” 같은 규칙은 점수를 왜곡할 수 있으니 금지하는 게 안전합니다(실무에선 파서 실패율 자체도 메트릭으로 보세요).
- **Option order/positional bias**: MCQ는 보기 순서에 민감할 수 있습니다. 최소한 shuffle 실험(여러 seed)으로 분산을 확인하세요. ([arxiv.org](https://arxiv.org/abs/2308.11483?utm_source=openai))  

### 2) HumanEval을 “그대로” 쓰면 생기는 착시
- **테스트가 약하면 과대평가**: 원본 HumanEval 통과가 “문제 요구사항을 일반화해서 만족”한다는 뜻이 아닐 수 있습니다. 그래서 HumanEval+처럼 테스트를 확장해 평가를 강화하는 흐름이 중요합니다. ([evalplus.github.io](https://evalplus.github.io/?utm_source=openai))  
- **pass@1 vs pass@k를 목적에 맞게**: IDE 자동완성/단발 생성은 pass@1에 가깝고, agent가 재시도 가능한 파이프라인은 pass@k가 더 현실적입니다. 지표를 제품 시나리오와 연결하지 않으면 “좋은 점수인데 현업에서 별로”가 자주 발생합니다.

### 3) 2026년형 권장 운영 방식: “공개 벤치 + 사내 벤치” 이중화
- 공개 벤치(MMLU/HumanEval)는 **외부 커뮤니케이션과 대략적 포지셔닝**에 좋고,
- 사내 벤치는 **우리 도메인 데이터/실패 모드/비용 제약**을 반영해 “진짜 성능”을 봅니다.
- 공유 로그 표준화 시도도 나오고 있는데, 같은 MMLU라도 툴마다 프롬프트/추출 방식이 달라 비교가 어긋날 수 있다는 점을 문제로 제기합니다. ([evalevalai.com](https://evalevalai.com/events/shared-task-every-eval-ever/?utm_source=openai))  

---

## 🚀 마무리
- MMLU는 “지식/시험형 MCQ”의 대표 벤치지만, 2026년에는 **프롬프트·파서·few-shot 구성**에 따라 점수가 의미 있게 흔들릴 수 있어 **평가 설정을 함께 읽어야** 합니다. ([crfm.stanford.edu](https://crfm.stanford.edu/2024/05/01/helm-mmlu.html?utm_source=openai))  
- HumanEval은 “코드 생성”의 대표 지표지만, **테스트 강도 한계** 때문에 HumanEval+처럼 테스트를 대폭 확장하는 방향이 실무적으로 더 유효합니다. ([evalplus.github.io](https://evalplus.github.io/?utm_source=openai))  
- 결론적으로 “리더보드 점수”는 출발점일 뿐이고, 제품/도메인에 맞춘 **재현 가능한 사내 eval**이 최종 의사결정의 기준이 되어야 합니다.

다음 학습으로는 (1) lm-evaluation-harness로 MMLU를 고정 설정으로 돌려 재현성 확보 ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai)), (2) EvalPlus로 HumanEval+를 적용해 “테스트 강화가 점수를 어떻게 바꾸는지”를 직접 관측하는 것을 추천합니다. ([evalplus.github.io](https://evalplus.github.io/?utm_source=openai))