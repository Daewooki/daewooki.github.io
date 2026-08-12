---
title: "MMLU·HumanEval 점수, 이제 그대로 믿으면 안 된다: 2026년 8월 기준 LLM 벤치마크 해석과 실무 적용 가이드"
date: 2026-08-12 02:31:17 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-08]
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

LLM을 프로젝트에 붙일 때 “어떤 모델이 더 좋나?”를 빠르게 결정하려면 결국 **평가(evaluation)** 가 필요합니다. 문제는 2026년 현재, MMLU/HumanEval 같은 고전 벤치마크 점수는 **그 자체로 제품 성능을 대표하지 못하는 경우가 점점 늘었다**는 점입니다. 이유는 크게 세 가지입니다.

- **데이터셋 결함/정답 오류**: MMLU는 정답 오류가 유의미하게 존재한다는 대규모 수작업 분석이 있었고, 그 결과물이 MMLU-Redux로 이어졌습니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  
- **벤치마크 “오염(contamination)”과 과적합**: 모델이 학습 과정에서 문제/해설을 “봤을” 가능성이 커질수록 점수는 더 이상 일반화 성능을 의미하지 않습니다. 코드 벤치마크는 특히 취약해서, HumanEval을 **더 빡센 테스트로 확장한 HumanEval+**(EvalPlus)가 널리 인용됩니다. ([arxiv.org](https://arxiv.org/abs/2305.01210?utm_source=openai))  
- **평가 구현체/프롬프트/런타임 차이로 점수가 흔들림**: MMLU-Pro처럼 프롬프트 민감도를 낮추려는 시도도 있지만, 여전히 “어떤 구현으로 돌렸는지”가 점수를 좌우합니다. ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))  

언제 쓰면 좋나?
- **모델 후보군을 1차로 좁힐 때**(cheap filter): “완전 탈락” 모델 걸러내기
- **동일 조건으로 반복 측정 가능한 사내 리그(내 파이프라인) 구축**할 때

언제 쓰면 안 되나?
- MMLU/HumanEval **리더보드 숫자만 보고** “우리 서비스에 적합” 판단
- 프롬프트/샘플링/코드 실행 환경이 다른데 **점수를 직접 비교**하는 것
- 제품 요구(툴 사용, 장기 컨텍스트, 에이전트 워크플로우)가 있는데 **단일 샷 QA/코딩 문제로 대표**시키는 것

---

## 🔧 핵심 개념

### 1) MMLU: “지식+추론”처럼 보이지만, 사실은 “MCQ 채점 파이프라인”이다
MMLU는 57개 과목의 **multiple-choice** 문제에서 **Exact Match(정답 선택)** 로 채점합니다. 구현체 관점에서 핵심은 다음 흐름입니다.

1. (입력) `question + options(A/B/C/D...)`
2. (프롬프트) zero-shot 또는 few-shot 컨텍스트 구성
3. (모델 출력) 선택지 토큰(예: “C”) 또는 해설+선택
4. (정규화) 출력에서 최종 선택지 추출
5. (스코어) 정답 레이블과 비교

이 구조의 함정:
- 모델이 “정답을 아는데” 출력 파싱이 실패하면 0점
- 반대로, **운 좋게** 찍어 맞추면 1점
- 정답 레이블 자체가 틀리면, 모델이 맞는 답을 해도 0점  
→ 실제로 MMLU는 정답/문항 품질 이슈가 지적되었고, 이를 정제/재주석한 MMLU-Redux가 제안되었습니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  

### 2) MMLU-Pro / Redux: “난이도/신뢰도”를 올리려는 갈래
- **MMLU-Redux**: 원본 MMLU의 오류를 체계적으로 분류/주석해 “점수의 신뢰도”를 올리려는 접근 ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  
- **MMLU-Pro**: 더 어려운 문제·더 많은 보기(10-way) 등으로 “찍기 운”을 줄이고, 프롬프트 민감도를 낮추려는 접근 ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))  

실무적으로는 “원본 MMLU 점수 vs Pro/Redux 점수”가 다르면,
- 모델이 **암기/오염**에 강했는지
- **추론/문항 이해**가 실제로 좋은지
- 평가 파이프라인이 **파싱/프롬프트에 의존**하는지  
를 의심할 근거가 됩니다.

### 3) HumanEval: 코드 생성 평가는 “pass@k + 실행 환경”이 전부다
HumanEval은 164개 Python 문제에서 **테스트 통과(pass@k)** 로 봅니다. 실행 기반이라 좋아 보이지만, 여기서도 구조를 뜯어보면:

1. (입력) 함수 시그니처 + docstring 스펙
2. (모델 출력) 함수 구현 코드
3. (샌드박스 실행) unit test 실행
4. (집계) pass@1, pass@10 등 계산

핵심 차이:
- MMLU는 “문자 선택” 파싱이 중요
- HumanEval은 “실행/테스트”가 중요(의존성, 타임아웃, 샌드박스, 난수 고정 등)

그리고 HumanEval의 약점(현업 관점)은 명확합니다:
- “테스트가 약하면” 허술한 코드도 통과 가능  
→ 그래서 HumanEval의 테스트를 대폭 확장한 **HumanEval+ (EvalPlus)** 같은 변형이 널리 쓰입니다. ([arxiv.org](https://arxiv.org/abs/2305.01210?utm_source=openai))  
- 오염 방지 측면에서 “최신 문제”를 쓰려면 LiveCodeBench 같은 접근이 등장했습니다. ([arxiv.org](https://arxiv.org/abs/2403.07974?utm_source=openai))  

### 4) 2026년식 결론: 벤치마크는 “점수”가 아니라 “측정 시스템”이다
요즘 커뮤니티/프레임워크는 “canonical implementation”을 강조합니다. 예를 들어 OpenAI는 simple-evals에서 MMLU/HumanEval 등을 정리해 제공합니다. ([github.com](https://github.com/openai/simple-evals?utm_source=openai))  
또한 EleutherAI lm-evaluation-harness 쪽도 태스크/설정이 계속 업데이트되어, 동일 벤치라도 설정 차이로 결과가 달라질 수 있음을 시사합니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai))  

---

## 💻 실전 코드

목표: “리더보드 점수”가 아니라 **내 제품 시나리오에 가까운 사내 평가 리그**를 만드는 예제를 제공합니다.

- MMLU 스타일: **우리 도메인 MCQ(정답 1개)** 를 동일 파이프라인으로 측정
- HumanEval 스타일: **우리 코드베이스 패턴에 가까운 ‘패치/함수 구현’** 을 테스트로 검증
- 공통: 결과를 JSONL로 남기고, 재현 가능한 설정(temperature=0, seed, timeout)을 고정

아래 예제는 Python 기반 “미니 eval runner”입니다. (벤치마크 원본을 그대로 긁어오는 게 아니라, **우리 문제를 MMLU/HumanEval 방식으로 측정**하는 게 핵심입니다.)

### 1) 초기 셋업

```bash
python -m venv .venv
source .venv/bin/activate
pip install openai pytest jsonlines pydantic
export OPENAI_API_KEY="..."
```

### 2) 평가 러너 (MCQ + 코드 실행)

```python
# eval_runner.py
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Literal, Optional, List, Dict, Any

import jsonlines
from openai import OpenAI


# ---------- MMLU-style MCQ ----------

@dataclass
class MCQItem:
    id: str
    subject: str
    question: str
    choices: Dict[str, str]  # {"A": "...", "B": "...", ...}
    answer: str             # e.g., "C"

def format_mcq_prompt(item: MCQItem) -> str:
    # 파싱 흔들림을 줄이기 위해 출력 포맷을 강제
    choices = "\n".join([f"{k}. {v}" for k, v in item.choices.items()])
    return f"""You are taking a closed-book multiple-choice test.

Subject: {item.subject}

Question:
{item.question}

Choices:
{choices}

Return ONLY a JSON object like: {{"final": "A"}}.
"""

def extract_final_letter(text: str) -> Optional[str]:
    # 모델이 지시를 어겨도 최대한 회수
    try:
        obj = json.loads(text)
        val = obj.get("final")
        if isinstance(val, str) and val.strip() in ["A","B","C","D","E","F","G","H","I","J"]:
            return val.strip()
    except Exception:
        pass
    for ch in ["A","B","C","D","E","F","G","H","I","J"]:
        if f'"{ch}"' in text or f" {ch}" == text.strip():
            return ch
    return None


# ---------- HumanEval-style code execution ----------

@dataclass
class CodeItem:
    id: str
    prompt: str          # function stub + docstring spec
    tests_py: str        # pytest test file content

def run_pytest(code: str, tests_py: str, timeout_s: int = 20) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as d:
        code_path = os.path.join(d, "solution.py")
        test_path = os.path.join(d, "test_solution.py")

        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)

        with open(test_path, "w", encoding="utf-8") as f:
            f.write(tests_py)

        try:
            p = subprocess.run(
                ["pytest", "-q", test_path],
                cwd=d,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            return {
                "ok": p.returncode == 0,
                "returncode": p.returncode,
                "stdout": p.stdout[-2000:],
                "stderr": p.stderr[-2000:],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "returncode": None, "stdout": "", "stderr": "TIMEOUT"}


# ---------- Model call ----------

def call_model_json(client: OpenAI, model: str, prompt: str) -> str:
    # 재현성을 위해 temperature=0 고정(가능한 범위 내)
    resp = client.responses.create(
        model=model,
        input=prompt,
        temperature=0,
    )
    return resp.output_text


def main():
    client = OpenAI()

    model = os.environ.get("EVAL_MODEL", "gpt-4.1-mini")

    mcq_items: List[MCQItem] = [
        MCQItem(
            id="ops-001",
            subject="Backend/Operations",
            question="In Kubernetes, what is the most appropriate primitive to ensure a pod is automatically restarted on failure?",
            choices={"A": "Service", "B": "Deployment", "C": "ConfigMap", "D": "Ingress"},
            answer="B",
        ),
        MCQItem(
            id="sec-002",
            subject="AppSec",
            question="Which HTTP response header is most directly related to mitigating XSS via restricting script sources?",
            choices={"A": "CSP", "B": "ETag", "C": "Accept-Ranges", "D": "Server"},
            answer="A",
        ),
    ]

    code_items: List[CodeItem] = [
        CodeItem(
            id="code-redis-ttl-001",
            prompt="""# solution.py
def normalize_cache_ttl(seconds: int) -> int:
    \"\"\"Normalize TTL for cache writes.

    - For negative input: raise ValueError
    - For 0..30: return 30  (avoid stampede)
    - For 31..3600: return as-is
    - For >3600: cap to 3600 (avoid stale data)
    \"\"\"
    # TODO: implement
""",
            tests_py="""# test_solution.py
import pytest
from solution import normalize_cache_ttl

def test_negative():
    with pytest.raises(ValueError):
        normalize_cache_ttl(-1)

def test_floor():
    assert normalize_cache_ttl(0) == 30
    assert normalize_cache_ttl(15) == 30
    assert normalize_cache_ttl(30) == 30

def test_mid():
    assert normalize_cache_ttl(31) == 31
    assert normalize_cache_ttl(600) == 600

def test_cap():
    assert normalize_cache_ttl(3601) == 3600
    assert normalize_cache_ttl(999999) == 3600
""",
        )
    ]

    out_path = "eval_results.jsonl"
    with jsonlines.open(out_path, mode="w") as w:
        # MCQ eval
        mcq_ok = 0
        for it in mcq_items:
            prompt = format_mcq_prompt(it)
            raw = call_model_json(client, model, prompt)
            pred = extract_final_letter(raw)
            ok = (pred == it.answer)
            mcq_ok += 1 if ok else 0
            w.write({
                "type": "mcq",
                "id": it.id,
                "subject": it.subject,
                "answer": it.answer,
                "pred": pred,
                "ok": ok,
                "raw": raw,
            })

        # Code eval
        code_ok = 0
        for it in code_items:
            raw = call_model_json(client, model, it.prompt)
            # 모델이 prompt 전체를 그대로 출력할 수 있으니, 최소한 solution.py로 저장 가능한 형태로 정리
            code = raw if "def normalize_cache_ttl" in raw else (it.prompt + "\n" + raw)
            r = run_pytest(code=code, tests_py=it.tests_py, timeout_s=20)
            ok = bool(r["ok"])
            code_ok += 1 if ok else 0
            w.write({
                "type": "code",
                "id": it.id,
                "ok": ok,
                "runner": r,
                "raw": raw,
            })

    print(f"[MCQ] {mcq_ok}/{len(mcq_items)}")
    print(f"[CODE] {code_ok}/{len(code_items)}")
    print(f"wrote: {out_path}")


if __name__ == "__main__":
    main()
```

예상 출력(예시):

```bash
[MCQ] 2/2
[CODE] 1/1
wrote: eval_results.jsonl
```

이게 왜 “MMLU/HumanEval 실전 적용”이냐?
- MMLU/HumanEval을 그대로 돌리기보다, **같은 채점 원리(정답 선택 / 테스트 통과)** 를 내 문제로 이식해야 점수가 의미를 갖습니다.
- OpenAI simple-evals도 “구현체(benchmark runner)”가 중요하다는 방향으로 정리되어 있습니다. ([github.com](https://github.com/openai/simple-evals?utm_source=openai))  

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) “리더보드 점수” 대신 “내 파이프라인의 canonical run”을 만들기
- 프롬프트 템플릿, temperature, max tokens, 파서, 타임아웃, 샌드박스 옵션을 **고정**하고 버전 관리하세요.
- lm-evaluation-harness처럼 설정 업데이트로 결과가 바뀔 수 있다는 점을 전제로, **eval 스냅샷(코드+데이터+설정)** 을 남기는 게 필수입니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai))  

### Best Practice 2) MMLU는 “정답률”만 보지 말고, “무효 문항/불확실 문항”을 분리
MMLU류는 정답 오류/문항 품질 문제가 실제로 보고되었습니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  
실무 대응:
- 사내 MCQ 세트에도 “애매한 문항”이 섞이기 쉽습니다(특히 트렌드/버전 이슈).
- **문항별 disagreement(모델들/사람들 간 불일치)** 가 큰 문제는 “평가에서 제외”하거나 “근거 제출형(LLM judge + human audit)”으로 전환하세요.

### Best Practice 3) HumanEval은 반드시 HumanEval+ 또는 사내 강화 테스트로 보강
HumanEval은 테스트가 상대적으로 약해 “그럴듯한 코드”가 통과할 수 있습니다. 이를 보완하는 대표 흐름이 HumanEval+ (EvalPlus)입니다. ([arxiv.org](https://arxiv.org/abs/2305.01210?utm_source=openai))  
실무 대응:
- “단위 테스트 추가(엣지/랜덤/프로퍼티 기반)”가 가장 비용 대비 효과가 큽니다.
- 가능하면 LiveCodeBench 같은 “오염에 강한 최신 문제” 계열을 참고해, **신규 문제를 주기적으로 추가**하세요. ([arxiv.org](https://arxiv.org/abs/2403.07974?utm_source=openai))  

### 흔한 함정/안티패턴
- **pass@k를 pass@1처럼 해석**: 제품은 대부분 첫 출력이 중요합니다. k를 올리면 “샘플링 비용”을 성능으로 착각하기 쉽습니다.
- MMLU에서 **CoT(Chain-of-Thought) 강제** 후 최종 선택 파싱이 불안정해져 오히려 점수/안정성이 떨어짐
- 코드 실행 평가에서 **의존성/네트워크/시간 제한**을 느슨하게 둬서 “현실에서 불가능한 풀이”가 통과

### 비용/성능/안정성 트레이드오프
- MMLU류: cheap(토큰만)하지만 “측정 신뢰도”를 확보하려면 문항 정제가 필요
- HumanEval류: 실행 비용+샌드박스 비용이 들지만 “실제 동작”에 더 가까움
- 둘 다 공통으로, **평가 세트가 작으면 분산이 커지고**(우연), **크면 비용이 증가**합니다.  
→ 그래서 “소형 smoke eval + 주간 풀 eval” 같은 계층화가 현실적입니다.

---

## 🚀 마무리

정리하면, 2026년 8월 기준 MMLU/HumanEval은 여전히 유용하지만 **‘점수’가 아니라 ‘측정 시스템’** 으로 다뤄야 합니다.

도입 판단 기준:
- 우리 요구가 “지식형 QA”에 가깝다면: MMLU 스타일 MCQ를 쓰되, **Redux/Pro 계열의 문제의식(오류/난이도/프롬프트 민감도)** 을 내 평가에도 반영 ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  
- 우리 요구가 “코드 생성/수정”이라면: HumanEval pass@1을 기본으로, **HumanEval+ 수준으로 테스트를 강화**하고 실행 환경을 제품과 가깝게 ([arxiv.org](https://arxiv.org/abs/2305.01210?utm_source=openai))  
- 그리고 무엇보다: simple-evals/lm-eval-harness처럼 **구현체를 고정하고 재현 가능한 리그를 운영**하는 것이 “진짜 성능 비교”의 출발점입니다. ([github.com](https://github.com/openai/simple-evals?utm_source=openai))  

다음 학습 추천:
- MMLU-Redux 논문/데이터셋로 “정답 오류가 점수를 어떻게 왜곡하는지” 체감하기 ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  
- HumanEval+ (EvalPlus) 논문로 “테스트 강화가 모델 순위를 어떻게 바꾸는지” 확인 ([arxiv.org](https://arxiv.org/abs/2305.01210?utm_source=openai))  
- LiveCodeBench로 “오염에 강한 코드 평가” 설계를 참고 ([arxiv.org](https://arxiv.org/abs/2403.07974?utm_source=openai))  

원하면, 당신의 서비스(예: RAG QA / 코드리뷰 봇 / 데이터 파이프라인 생성기)에 맞춰 **평가 항목 설계(문항 타입, 채점 방식, 비용 상한, 실패 분석 리포트 포맷)** 까지 이어서 템플릿으로 잡아드릴 수 있습니다.