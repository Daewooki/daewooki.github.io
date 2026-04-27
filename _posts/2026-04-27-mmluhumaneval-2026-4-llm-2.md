---
title: "MMLU·HumanEval 점수, 그대로 믿으면 망합니다: 2026년 4월 LLM 벤치마크 “해석법” 심층 가이드"
date: 2026-04-27 03:49:23 +0900
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
LLM을 도입/교체할 때 가장 흔한 실패는 “벤치마크 1~2개 점수만 보고” 모델을 고르는 것입니다. 특히 **MMLU**(지식+추론 MCQ)와 **HumanEval**(코드 생성)는 여전히 가장 많이 인용되지만, 2026년 시점에선 **점수 자체보다 ‘점수가 만들어지는 과정’**을 이해하지 못하면 의사결정이 틀어지기 쉽습니다. MMLU는 라벨/정답 오류 이슈가 공개적으로 분석되었고(오류로 인한 상한선 문제), 이를 보완하는 흐름(예: MMLU-Pro/Redux)이 강해졌습니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai)) HumanEval은 pass@k라는 통계적 정의, 실행 환경 격리/timeout, 그리고 데이터 오염(benchmark contamination) 문제가 “점수 비교”를 매우 까다롭게 만듭니다. ([gitextract.com](https://gitextract.com/openai/human-eval?utm_source=openai))

**언제 쓰면 좋나**
- 사내/프로덕션 태스크가 아직 정리되지 않았을 때, 후보 모델군을 빠르게 “대충” 걸러낼 때
- 회귀(regression) 감지를 위한 **상대 비교**(동일 세팅에서만) 신호로 쓸 때
- 모델이 **지식형/코딩형**에서 어느 쪽이 강한지 큰 방향성을 볼 때

**언제 쓰면 안 되나**
- “MMLU 2%p 더 높으니 우리 고객지원 챗봇이 더 좋아짐” 같은 **직결 판단**
- 서로 다른 리포트/리더보드 점수를 섞어 **교차 비교**
- HumanEval pass@k를 보고 “실제 PR도 잘 만들겠네”라고 **현업 SWE 능력으로 과대 해석**

---

## 🔧 핵심 개념
### 1) MMLU: ‘지식+추론’처럼 보이지만, 측정 신호가 섞여 있다
- **정의**: 다양한 과목의 4지선다(원본 MMLU)에서 정답률(accuracy/EM)을 측정.
- **문제 1 — 데이터 품질(정답/문항 오류)**: MMLU는 정답 오류가 유의미하게 존재한다는 수동 분석이 나왔고(약 6.5% 수준 추정), 이 경우 점수는 “모델 성능”이 아니라 **데이터 노이즈**에 의해 상한이 생깁니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  
  → 작은 점수 차(예: 0.5~1%p)는 “유의미한 개선”이 아닐 수 있습니다.
- **문제 2 — 포맷/프롬프트 민감도**: 동일 태스크도 프롬프트 스타일, 출력 파싱 규칙에 따라 점수가 흔들립니다. 이를 줄이려는 설계가 **MMLU-Pro** 계열입니다(보기 10개, 더 어려운 문항, 프롬프트 민감도 감소 보고). ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))

**실무 해석 포인트**
- 원본 MMLU 고득점은 (일부) **기억/패턴**과 **시험 최적화**를 포함합니다.
- “우리 도메인 지식 Q&A”에 가까우면 참고 가치가 있지만, “복잡한 업무 절차/툴 사용/정책 준수” 같은 것은 MMLU만으로는 거의 판단 불가입니다.

### 2) HumanEval: pass@k는 “단일 정답률”이 아니라 ‘샘플링 전략’의 함수
- **정의**: 164개 Python 문제에 대해 모델이 코드를 생성하고, 제공된 테스트를 모두 통과하면 성공. 점수는 보통 **pass@k**로 보고합니다. ([llmreference.com](https://www.llmreference.com/benchmark/humaneval?utm_source=openai))
- **pass@k의 핵심 의미**: “k번 뽑아보면(샘플 k개 생성) 그중 하나라도 맞을 확률”입니다.  
  즉, **temperature**, **샘플 개수 n**, **선택 k**, **샘플링/리랭킹 여부**에 따라 점수가 달라지고, 서로 다른 리포트 간 비교가 위험합니다. ([mbrenndoerfer.com](https://mbrenndoerfer.com/writing/humaneval-code-generation-benchmark-pass-at-k?utm_source=openai))
- **실행 안전/재현성**: HumanEval 구현은 보통 별도 프로세스로 코드를 실행하고 timeout 등을 둬 위험을 제한합니다(격리/timeout 없으면 평가 자체가 위험해짐). ([gitextract.com](https://gitextract.com/openai/human-eval?utm_source=openai))
- **오염(contamination) 이슈**: HumanEval은 오래된 벤치마크라 학습 데이터에 포함되었을 가능성(또는 유사 변형 포함)이 지속적으로 지적되고, 이를 완화하려는 연구도 있습니다. ([arxiv.org](https://arxiv.org/abs/2412.01526?utm_source=openai))

**실무 해석 포인트**
- pass@1이 높아도 “리팩토링/테스트 추가/라이브러리 사용/레거시 대응” 같은 실제 업무 능력은 별개입니다.
- 반대로 pass@10이 높으면 “샘플 여러 개 뽑아 검증/선택하는 파이프라인”을 구성했을 때 성과가 날 가능성이 있습니다(= **모델 단독**이 아니라 **시스템 설계**로 성능을 끌어올릴 여지).

### 3) 결론적으로: 벤치마크는 ‘모델’이 아니라 ‘평가 파이프라인’을 평가한다
2026년 시점의 핵심은 이겁니다.

- **MMLU류는** “문항/정답 품질 + 프롬프트/파싱 + 추론 예산”의 결과
- **HumanEval은** “샘플링/실행환경/timeout + pass@k 산식 + 오염 가능성”의 결과

그래서 “점수”가 아니라, **내 프로젝트에서 재현 가능한 평가 세팅**을 먼저 정의해야 합니다.

---

## 💻 실전 코드
목표: “우리 팀이 모델 후보를 바꿀 때마다” **동일 세팅**으로 MMLU(또는 MMLU-Pro 계열) + HumanEval을 돌리고, 결과를 **프로젝트 관점으로 해석 가능한 형태(비용/지연 포함)**로 남기는 미니 파이프라인을 만듭니다.

아래 예시는 **EleutherAI lm-evaluation-harness로 MMLU 계열**, 그리고 **HumanEval은 실행 기반 pass@k**를 별도 러너로 분리하는 방식입니다. lm-eval도 HumanEval을 지원하지만(환경 변수 등 실행 이슈 존재), 코드 벤치마크는 실행/격리 세팅이 민감해서 파이프라인에서 분리하는 쪽을 권장합니다. ([deepwiki.com](https://deepwiki.com/EleutherAI/lm-evaluation-harness/3.4-code-generation-tasks?utm_source=openai))

### 0) 셋업
```bash
# (권장) 격리된 venv/conda에서 수행
python -m venv .venv
source .venv/bin/activate

pip install -U lm-eval
pip install -U datasets evaluate transformers accelerate

# HumanEval 실행은 안전장치가 필요합니다.
# lm-eval HumanEval 경로를 쓸 경우 코드 실행을 허용하는 플래그가 필요할 수 있습니다.
export HF_ALLOW_CODE_EVAL=1
```

### 1) MMLU(또는 MMLU-Pro)를 “같은 프롬프트/같은 파싱/같은 few-shot”으로 고정 실행
아래는 **허깅페이스 로컬/서빙 모델**을 lm-eval로 평가하는 예시입니다. 핵심은 “한 번 정한 설정을 CI에서 고정”하는 것입니다.

```bash
# 예: MMLU 5-shot 고정 (모델/토크나이저 버전도 고정 권장)
lm_eval \
  --model hf \
  --model_args pretrained=meta-llama/Meta-Llama-3.1-8B-Instruct,trust_remote_code=True \
  --tasks mmlu \
  --num_fewshot 5 \
  --batch_size 4 \
  --output_path ./eval_out/mmlu_llama31_8b.json
```

예상 출력(요지):
- `acc` 또는 `acc_norm`류
- subject별 breakdown(설정에 따라)

**현실적 시나리오 포인트**
- 사내 모델 게이트에서 “모델 교체” PR이 올라오면, 이 커맨드를 그대로 CI에서 돌려서 **회귀를 감지**합니다.
- 단, MMLU 점수 1%p 미만 차이는 데이터/프롬프트 노이즈 범위일 수 있으니, 최소한 **subject별 변화**와 함께 봅니다(예: 법/의학/CS만 하락했는지).

### 2) HumanEval: pass@k를 “샘플링 예산”과 묶어서 설계하기
여기서는 HumanEval 자체 구현 대신, **원칙을 코드로 고정**합니다:
- temperature, n(총 샘플 수), k(pass@k), max_tokens를 고정
- 실행 timeout 고정(문제별)
- 결과를 `pass@1`, `pass@5`, `pass@10`으로 동시에 기록
- (중요) 비용/지연을 같이 저장 → “pass@10은 좋아졌는데 비용이 10배” 같은 의사결정이 가능

```python
# humaneval_runner.py
import json, time, subprocess, tempfile, os
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class RunConfig:
    samples_per_task: int = 20   # n
    k_list: List[int] = None     # pass@k
    timeout_sec: int = 3
    temperature: float = 0.8
    max_new_tokens: int = 512

def pass_at_k(n: int, c: int, k: int) -> float:
    # 표준 unbiased estimator를 쓰는 구현들이 많습니다.
    # 여기서는 개념 데모가 아니라 "파이프라인 고정" 목적이므로,
    # 실제 운영에선 검증된 구현(evaluate/code_eval 등)을 그대로 가져오세요.
    if c == 0:
        return 0.0
    if n - c < k:
        return 1.0
    # 간단 근사 (운영용 X): 정확한 식은 라이브러리 사용 권장
    return 1.0 - ((n - c) / n) ** k

def run_python_tests(code: str, tests: str, timeout_sec: int) -> bool:
    # 매우 단순화된 실행기: 실제론 프로세스 격리/리소스 제한이 더 필요합니다.
    # (openai/human-eval도 별도 프로세스+timeout으로 감쌉니다.) ([gitextract.com](https://gitextract.com/openai/human-eval?utm_source=openai))
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "main.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
            f.write("\n\n")
            f.write(tests)
        try:
            subprocess.run(
                ["python", path],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=True,
            )
            return True
        except Exception:
            return False

def main():
    # 실무에선 humaneval dataset 로더를 쓰세요.
    # 여기서는 "파이프라인 형태"를 보여주기 위해
    # 이미 전처리된 tasks.jsonl(각 라인: {task_id, prompt, tests})가 있다고 가정합니다.
    cfg = RunConfig(samples_per_task=20, k_list=[1,5,10], timeout_sec=3)
    t0 = time.time()

    results = {"tasks": [], "summary": {}}
    with open("./data/humaneval_tasks.jsonl", "r", encoding="utf-8") as f:
        tasks = [json.loads(line) for line in f]

    # TODO: 실제로는 여기서 모델 호출(OpenAI/자체서빙/HF generate)을 붙입니다.
    # 핵심은 "n개 샘플 생성 → 각 샘플 실행 → 성공 개수 c 집계 → pass@k 산출" 흐름입니다.
    for task in tasks:
        n = cfg.samples_per_task
        # (예시) 이미 생성된 completions를 로드한다고 가정
        completions = task["completions"][:n]

        passed = 0
        for code in completions:
            ok = run_python_tests(code=code, tests=task["tests"], timeout_sec=cfg.timeout_sec)
            passed += 1 if ok else 0

        task_row = {"task_id": task["task_id"], "n": n, "c": passed, "pass@k": {}}
        for k in cfg.k_list:
            task_row["pass@k"][f"pass@{k}"] = pass_at_k(n=n, c=passed, k=k)
        results["tasks"].append(task_row)

    # aggregate
    for k in cfg.k_list:
        key = f"pass@{k}"
        results["summary"][key] = sum(t["pass@k"][key] for t in results["tasks"]) / len(results["tasks"])

    results["summary"]["wall_time_sec"] = time.time() - t0

    os.makedirs("./eval_out", exist_ok=True)
    with open("./eval_out/humaneval_passk.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
```

예상 출력(요지):
- `summary.pass@1`, `summary.pass@5`, `summary.pass@10`
- `wall_time_sec`
- 태스크별 성공 개수 분포

**확장(실전)**
- 샘플 생성 단계에 “컴파일/테스트 빠른 실패 필터링”, “LLM-as-judge 리랭킹” 등을 넣으면 pass@k 대비 비용이 어떻게 변하는지 측정 가능합니다.
- pass@10만 올리는 전략은 곧바로 **추론 비용**과 연결되므로, 반드시 비용/latency와 같이 기록하세요.

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **벤치마크 점수를 ‘게이트’가 아니라 ‘알람’으로 쓰기**
- CI에서 MMLU/HumanEval을 매번 돌리되, merge 차단은 **프로덕션 샘플 기반 eval**(사내 골든셋)로 하세요.
- MMLU는 데이터 오류/노이즈 바닥이 존재하므로 작은 변동은 경보만 울리는 게 합리적입니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))

2) **HumanEval은 pass@1과 pass@10을 같이 보고, “시스템 전략”을 결정**
- pass@1이 중요하면: deterministic(낮은 temperature), 툴/타입체크/테스트 생성 등 “한 방 성공”을 설계
- pass@10이 중요하면: 샘플링+검증(테스트 실행/정적 분석) 파이프라인이 ROI가 나올 수 있음  
- 이때 pass@k는 샘플링 파라미터에 민감하니, 리포트 비교 시 설정을 반드시 같이 남기세요. ([mbrenndoerfer.com](https://mbrenndoerfer.com/writing/humaneval-code-generation-benchmark-pass-at-k?utm_source=openai))

3) **MMLU는 가능하면 MMLU-Pro/Redux 계열과 병행해서 ‘해석 안전성’을 올리기**
- MMLU-Pro는 보기 수 확대/난이도/프롬프트 민감도 완화 등을 통해 변별력을 높이려는 방향이고, MMLU의 한계를 보완하려는 흐름이 명확합니다. ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))

### 흔한 함정/안티패턴
- **서로 다른 리더보드 점수 합치기**: 프롬프트, few-shot, 파싱, temperature가 다르면 “같은 MMLU/HumanEval”이 아닙니다.
- **파싱 실패를 무시**: MCQ는 출력 포맷 파싱이 점수에 직접 영향(특히 답안 추출 로직).
- **HumanEval을 ‘실제 업무’로 과대평가**: 실제 업무는 repo context, 빌드 시스템, 의존성, 부분 수정, 테스트 추가 등 정적 벤치마크 밖의 요소가 대부분입니다.

### 비용/성능/안정성 트레이드오프
- **pass@10 상승**은 거의 항상 **토큰 비용+지연 증가**와 동행합니다.
- MMLU few-shot을 늘리면 점수가 오르기도 하지만, 그건 “모델 능력”이라기보다 “컨텍스트 제공량 증가”의 효과일 수 있습니다.
- 그래서 “정확도 1%p”가 아니라 “정확도/비용/지연의 파레토”로 의사결정을 문서화해야 합니다.

---

## 🚀 마무리
- **MMLU**와 **HumanEval**은 2026년에도 “초기 후보 필터링/회귀 감지”에는 유용하지만, 그대로 제품 성능으로 번역하면 위험합니다. MMLU는 정답 오류/노이즈 이슈가 공론화되었고 이를 보완하려는 작업(MMLU-Redux 등)이 있습니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))
- HumanEval은 pass@k가 “모델”이 아니라 “샘플링+검증 시스템”의 성능을 반영하기 쉬우며, 오염과 실행 환경이 점수 해석에 큰 영향을 줍니다. ([arxiv.org](https://arxiv.org/abs/2412.01526?utm_source=openai))

**도입 판단 기준(현업 체크리스트)**
1) 우리 유스케이스가 **MCQ 지식형**인가, **코드 생성(테스트로 검증 가능)**인가, 아니면 **툴/워크플로우형**인가?
2) 벤치마크를 “외부 점수”로 볼 건가, “내 CI에서 재현 가능한 설정”으로 고정할 건가?
3) HumanEval에서 pass@k 개선을 노린다면, 그에 필요한 **추론 예산(샘플 수)**과 **검증 비용**을 감당할 수 있나?

**다음 학습 추천**
- 벤치마크 점수 대신, 조직 맞춤 평가를 어떻게 설계/운영할지: OpenAI의 evals best practices(continuous evaluation, 블라인드 평가, 회귀 감지 운영 패턴) ([platform.openai.com](https://platform.openai.com/docs/guides/evaluation-best-practices?utm_source=openai))
- 내부적으로는 “MMLU/HumanEval + 사내 골든셋 + 프로덕션 트래픽 샘플링”의 3계층을 만들고, 모델 변경 시 파레토(품질/비용/지연) 리포트를 자동 생성하는 쪽이 가장 ROI가 좋습니다.

원하면, 당신의 제품(예: 고객지원, 코드리뷰 봇, RAG QA, 에이전트 자동화)의 **입력/출력 스키마**를 기준으로 “사내 골든셋 + grader 설계(정답 기반/LLM-as-judge/휴먼 블라인드)”까지 포함한 평가 설계안을 같이 만들어 드릴게요.