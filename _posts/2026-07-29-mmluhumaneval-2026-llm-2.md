---
title: "MMLU·HumanEval 점수에 속지 않는 법: LLM 벤치마크 해석과 “내 서비스에 맞는 평가” 설계"
description: "LLM을 프로덕션에 붙일 때 진짜 어려운 건 “모델이 똑똑한가?”가 아니라 내 워크로드에서 실패하지 않는가입니다. 그런데 2026년 7월 기준으로도 많은 팀이 여전히 MMLU(지식/추론)와 HumanEval(코딩) 같은 전통 벤치마크 점수로 모델을 고릅니다."
date: 2026-07-29 03:21:56 +0900
categories: [AI, LLM]
tags: [ai, llm]
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
LLM을 프로덕션에 붙일 때 진짜 어려운 건 “모델이 똑똑한가?”가 아니라 **내 워크로드에서 실패하지 않는가**입니다. 그런데 2026년 7월 기준으로도 많은 팀이 여전히 MMLU(지식/추론)와 HumanEval(코딩) 같은 **전통 벤치마크 점수**로 모델을 고릅니다. 문제는 이 점수들이 (1) **포화(saturation)**, (2) **오염(contamination)/누수**, (3) **채점 방식의 편향** 때문에 “내 프로젝트에서의 성능”과 어긋나기 쉽다는 점입니다. MMLU의 정답 오류 이슈를 지적하며 “이제 MMLU로 충분한가?”를 묻는 분석도 나왔고, 이를 보완하려는 MMLU-Redux 흐름이 이어졌습니다.[^1] 또한 오염을 줄이려는 MMLU-CF 같은 변형도 등장했습니다.[^2]

**언제 쓰면 좋나**
- 모델 후보군을 1차로 빠르게 압축해야 할 때(“최저선 컷”)
- 같은 계열 모델 간 회귀(regression) 체크(버전업/파인튜닝 후 성능 하락 탐지)

**언제 쓰면 안 되나**
- 점수 1~2% 차이를 근거로 “A가 B보다 낫다” 같은 결론을 내릴 때(노이즈/프롬프트/채점 편차)
- 에이전트형/도구사용/장문추론/코드베이스 수정 같은 **실제 업무형** 사용처를 MMLU/HumanEval로 대체하려 할 때(문제 형태가 다름)
- HumanEval pass@1만 보고 “우리 코드 생성은 충분”이라 판단할 때(테스트 빈약·허술한 통과가 가능)

---

## 🔧 핵심 개념
### 1) MMLU는 “지식+시험형 MCQ”이고, 2026년엔 해석이 더 중요해졌다
MMLU는 57개 과목의 객관식 문제로 폭넓은 지식 범위를 커버하지만, **(a) 정답/문항 품질**, **(b) 객관식 포맷 자체의 취약점**, **(c) 포화** 문제가 지속적으로 언급됩니다. “Are We Done with MMLU?”는 MMLU에 **ground-truth errors(정답 오류)**가 꽤 있어 점수 해석을 흐린다고 지적합니다.[^1]

이를 보완하려는 흐름이 대표적으로:
- **MMLU-Pro**: 4지선다→10지선다로 바꾸고 더 reasoning-heavy 문항을 넣어 **변별력**을 키우려는 시도. 프롬프트 스타일 변화에 대한 민감도도 낮추려 했다는 결과가 보고됩니다.[^3]
- **MMLU-CF**: contamination-free를 목표로 “누수/오염” 문제를 줄이려는 변형.[^2]
- **채점 방식 재검토**: “객관식 선택”보다 **answer matching(자유응답 기반의 정답 매칭)**이 사람 채점과 더 잘 맞을 수 있다는 연구도 나왔습니다.[^4]

즉 2026년의 포인트는 “MMLU 점수”가 아니라 **어떤 MMLU(원본/Redux/Pro/CF), 어떤 프롬프트/채점/샷 수, 어떤 언어**로 재현했는지까지 봐야 한다는 겁니다.

### 2) HumanEval은 “코드 실행 기반”이라 단단해 보이지만, pass@1만으로는 부족하다
HumanEval은 164개 Python 함수 문제에 대해 테스트를 실행해 맞는지 보는 “functional correctness” 평가라 직관적으로 신뢰가 갑니다. 하지만 실무에서 흔히 겪는 이슈는:
- 테스트가 얕으면 **틀린 풀이도 통과**할 수 있음 → 그래서 HumanEval+ / EvalPlus류가 “테스트를 더 빡세게” 하는 방향으로 진화
- pass@1만 보면 “한 번에 잘 짜는지”만 보게 되고, 실제 개발 흐름(재시도·수정·도구사용·기존 코드베이스 반영)과 멀어짐
- 최근에는 HumanEval/MBPP에서 잘 나오던 모델이 더 현실적인 변형에서 떨어지는 현상도 보고됩니다(예: self-invoking 형태의 HumanEval Pro).[^5]

정리하면 HumanEval은 “코드가 실행되느냐”라는 강점이 있지만, **테스트 커버리지·데이터 누수·문제 분포·pass@k 설정**에 따라 해석이 크게 달라집니다.

### 3) 2026년 평가 트렌드: “벤치마크 점수” → “내 작업에 맞춘 eval + 벤치마크는 보조”
OpenAI도 고전 벤치마크에서 점차 SWE-Bench/MLE-Bench/PaperBench 같은 **업무형 평가**로 이동하는 맥락을 설명했고, 경제적 가치 기반 평가(GDPval)도 제안했습니다.[^6]
실무팀 입장에서는 결론이 간단합니다:  
**MMLU/HumanEval은 ‘건강검진’이고, 최종 결정은 ‘내 서비스 시나리오 리허설’로 해야** 합니다.

---

## 💻 실전 코드
아래는 “벤치마크 숫자 뽑기”가 아니라, **내 조직의 모델 선택/회귀 감지 파이프라인**으로 바로 붙일 수 있는 형태로 구성합니다.

- 1단계: `openai/simple-evals`로 MMLU/HumanEval을 **재현 가능한 방식**으로 실행[^7]  
- 2단계: 결과를 JSON으로 저장하고, **게이팅 규칙**(예: MMLU는 보조, HumanEval은 최소선, 그리고 사내 태스크 eval이 최종)을 적용
- 3단계: PR/릴리즈마다 회귀 체크(“점수 1%↑”가 아니라 **통계적/실무적 유의미성** 중심)

### 0) 환경 준비
```bash
python -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install simple-evals pandas
export OPENAI_API_KEY="YOUR_KEY"
```

### 1) MMLU + HumanEval 실행(재현 가능한 “스냅샷” 만들기)
`simple-evals`는 커맨드로 여러 벤치마크를 돌릴 수 있는 형태를 제공합니다. (모델/샘플 수/실행 로그를 남기는 게 핵심)[^7]

```bash
# 예: 전체가 아니라 빠른 스모크(예: 200문항)로 PR 단계에서 먼저 돌리고
# 나이트리/릴리즈에서 full로 돌리는 식으로 운영
python -m simple-evals.simple_evals \
  --model "gpt-4.1-2025-04-14" \
  --examples 200 \
  --benchmarks "mmlu,humaneval" \
  --output "eval_runs/2026-07-29_gpt-4.1_smoke.json"
```

예상 출력(예시):
- `mmlu_accuracy`: 0.87
- `humaneval_pass@1`: 0.92
- 각 벤치별 latency/token usage(구현에 따라 포함)

### 2) “벤치마크 점수”를 제품 의사결정으로 번역하는 게이팅 코드
핵심은 **(a) 최소선, (b) 회귀 감지, (c) 우리 태스크 우선**입니다. MMLU는 포화/오염 논쟁이 있으니 “합격/불합격”보다 **이상징후 감지(급락)** 용도로 쓰는 편이 안전합니다.[^1]

```python
import json
from pathlib import Path
import pandas as pd

RUN_PATH = Path("eval_runs/2026-07-29_gpt-4.1_smoke.json")

def load_run(p: Path) -> dict:
    return json.loads(p.read_text())

def gate(run: dict) -> dict:
    # 팀/도메인에 맞게 조정
    humaneval_min = 0.85          # 코드 생성 최소선
    mmlu_drop_alert = -0.03       # 이전 대비 -3%p 이상이면 경고(노이즈 감안)
    
    mmlu = run["results"]["mmlu"]["accuracy"]
    he = run["results"]["humaneval"]["pass_at_1"]

    decision = {
        "approve_for_next_stage": (he >= humaneval_min),
        "alerts": [],
        "metrics": {"mmlu_accuracy": mmlu, "humaneval_pass@1": he},
    }

    if he < humaneval_min:
        decision["alerts"].append("HumanEval pass@1 below minimum: block release candidate")

    # MMLU는 절대 점수보다 '급락'을 감지하는 보조 지표로 사용
    # (예: baseline을 별도 저장해두고 비교)
    baseline_mmlu = run.get("baseline", {}).get("mmlu_accuracy")
    if baseline_mmlu is not None:
        if (mmlu - baseline_mmlu) <= mmlu_drop_alert:
            decision["alerts"].append("MMLU accuracy dropped sharply: investigate prompt/model/regression")

    return decision

if __name__ == "__main__":
    run = load_run(RUN_PATH)
    d = gate(run)
    print(json.dumps(d, indent=2, ensure_ascii=False))
```

### 3) 확장: “우리 회사형 HumanEval”로 연결(가장 중요한 단계)
여기서부터가 실무 승부처입니다. HumanEval처럼 **실행 기반**으로, 하지만 우리 환경에 맞게:
- 사내 SDK/라이브러리 사용
- 실제 데이터 스키마/에러 처리/타임아웃
- 단위테스트+프로퍼티테스트(가능하면)
- 수정 루프(에이전트/툴콜) 포함한 평가까지

즉, HumanEval은 “측정 방식(실행 기반)”만 가져오고, **문제는 우리 도메인으로 재구성**하는 게 ROI가 큽니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **MMLU는 “능력의 상한”이 아니라 “형태가 특정된 시험 성능”으로만 취급**
- 특히 MMLU 계열은 정답 오류/포화/오염 이슈가 반복적으로 지적됩니다.[^1]  
- 따라서 “MMLU 1%p 높음”은 구매/전환 근거로 약합니다. 대신 “이번 릴리즈에서 갑자기 5%p 떨어졌다” 같은 **이상징후**에 집중하세요.

2) **HumanEval은 pass@1만 보지 말고 pass@k·테스트 강화 버전을 함께**
- k를 늘리면 “한 번에 맞추는 능력”이 아니라 “샘플링/재시도 포함한 해결 확률”을 보게 됩니다.
- 그리고 HumanEval Pro처럼 더 현실적인 변형에서 성능이 떨어질 수 있다는 관찰이 있습니다.[^5]  
- 즉, pass@1이 높아도 “실무에서 덜 망가지는 코드”를 의미하진 않습니다.

3) **채점 방식이 성능을 만든다: MCQ vs 자유응답**
- 객관식은 보기 중 하나를 고르는 게임이 되기 쉽고, 자유응답 기반의 answer matching이 더 사람 채점과 잘 맞을 수 있다는 연구가 나왔습니다.[^4]  
- 가능하면 중요한 영역(예: 의료/법률/정책)은 MCQ 점수보다 **서술형+채점자(휴먼/LLM-judge)+근거 평가**로 옮기세요.

### 흔한 함정/안티패턴
- **리더보드 점수를 그대로 비교**: 프롬프트, 샷 수, temperature, 채점 모델이 다르면 “다른 실험”입니다.
- **모델을 벤치마크에 맞춰 튜닝**: 단기 점수는 오르지만 실제 제품 품질(안정성/보안/일관성)이 떨어질 수 있습니다.
- **MMLU/HumanEval만으로 에이전트 품질을 판단**: 도구 사용, 상태 관리, 장기 계획은 다른 축입니다. OpenAI도 고전 벤치마크에서 업무형 평가로 확장하는 흐름을 명시합니다.[^6]

### 비용/성능/안정성 트레이드오프
- **평가 비용**: pass@k를 올리거나, 더 강한 테스트(프로퍼티 테스트/샌드박스)로 가면 비용이 선형~초선형으로 증가합니다.
- **안정성**: 실행 기반 평가는 “환경 재현(의존성/런타임/타임아웃)”이 품질을 좌우합니다. CI에서 컨테이너로 고정하세요.
- **성능 지표의 의미**: 작은 점수 차이보다, **실패 모드 분해(예: 타입/경계값/예외/보안)**가 제품 개선에 훨씬 직접적입니다.

---

## 🚀 마무리
2026년 7월의 결론은 이겁니다.

- **MMLU**: “시험형 지식/추론”의 스냅샷. 정답 오류·오염·포화 이슈가 있어 **절대 점수/미세한 차이로 의사결정하지 말고**, 급락 감지/최저선 체크에 쓰세요.[^1]  
- **MMLU-Pro / MMLU-CF**: 변별력/오염 문제를 개선하려는 시도이므로, 원본 MMLU만 볼 때보다 낫지만 “내 워크로드 대표성”은 여전히 별개입니다.[^3]  
- **HumanEval**: 실행 기반이라 강력하지만, pass@1만으로는 실무 품질을 대변하지 못합니다. 테스트 강화/변형 벤치마크/사내형 실행 평가로 확장하세요.[^5]  
- 최종 도입 판단 기준: **(1) 사내 시나리오 eval 1등, (2) 회귀에 강한 재현성, (3) 실패 모드가 우리 리스크(보안/정확성/비용)와 맞는가**.

다음 학습 추천(바로 실무에 도움되는 순서):
1) `simple-evals` 같은 도구로 **재현 가능한 벤치마크 실행 파이프라인** 구축[^7]  
2) HumanEval 방식(실행 기반)을 복제해 **사내 도메인 문제+테스트**로 “CompanyEval” 만들기  
3) 가능하면 SWE-Bench류 “업무형” 평가까지 연결(벤치마크는 보조, 제품 시나리오는 본선)

[^1]: <https://arxiv.org/abs/2406.04127>
[^2]: <https://arxiv.org/abs/2412.15194>
[^3]: <https://arxiv.org/abs/2406.01574>
[^4]: <https://arxiv.org/abs/2507.02856>
[^5]: <https://arxiv.org/abs/2412.21199>
[^6]: <https://openai.com/index/gdpval/>
[^7]: <https://github.com/openai/simple-evals>
