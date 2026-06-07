---
title: "MMLU·HumanEval 점수에 속지 않는 법: 2026년 6월 기준 LLM 평가를 “프로덕션 의사결정”으로 바꾸는 해석 프레임"
date: 2026-06-07 04:45:45 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-06]
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
LLM을 도입/교체할 때 가장 흔한 실패는 **벤치마크 점수(예: MMLU, HumanEval)를 ‘성능의 진실’로 오해**하는 겁니다. 2026년 6월 기준으로도 여전히 모델 릴리즈 노트에는 “MMLU xx%, HumanEval yy%”가 전면에 나오지만, 실무에서는 다음 문제가 반복됩니다.

- **MMLU 고득점인데** 우리 도메인 QA/정책/규정 질문에서 **헛소리(hallucination)**가 줄지 않는다
- **HumanEval 고득점인데** 실제 코드베이스에서는 **리팩토링/테스트/빌드/의존성** 때문에 실패한다
- 리더보드 점수와 사내 재현 점수가 **10~20p씩 불일치**한다(프롬프트, 샘플링, harness 차이)

언제 쓰면 좋나?
- “모델 A vs B”를 **같은 환경/같은 프로토콜**로 빠르게 비교해 **후보를 좁힐 때**
- 회귀(regression) 방지용으로 **고정된 golden set** + 자동 채점 파이프라인을 만들 때(예: OpenAI Evals 같은 프레임워크) ([evals.openai.com](https://evals.openai.com/?utm_source=openai))

언제 쓰면 안 되나?
- 리더보드 점수만으로 **프로덕션 품질을 단정**할 때
- MMLU/HumanEval 하나로 **“우리 서비스에 맞는다”**를 결론내릴 때(측정 대상이 다름)

---

## 🔧 핵심 개념
### 1) MMLU는 “지식/선다형 추론”이고, 이미 포화(saturation) 구간
MMLU(Massive Multitask Language Understanding)는 다분야 선다형 문제로 **지식 + 약한 추론**을 측정합니다. 하지만 2026년에는 상위권 모델이 높은 구간에 몰리면서 “몇 점 차”가 의사결정 신호로 약해졌다는 평가가 많고, 더 어려운 변형(예: **MMLU-Pro**)이 활용됩니다. ([benchmarkingagents.com](https://benchmarkingagents.com/mmlu/?utm_source=openai))  
또한 MMLU 자체는 **정답 오류(ground-truth error)** 이슈가 보고되어 “최대 점수” 해석에 노이즈 바닥(noise floor)이 생길 수 있습니다. ([en.wikipedia.org](https://en.wikipedia.org/wiki/MMLU?utm_source=openai))

**MMLU-Pro**는 (요지)
- 선택지 수 증가(더 촘촘한 구분)
- reasoning 중심 재설계
- 프롬프트 스타일 변화에 대한 민감도를 낮추려는 설계  
(프롬프트 변화 민감도가 MMLU 대비 줄었다는 보고) ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))

실무적 의미:
- MMLU/MMLU-Pro는 “우리 제품 지표”라기보다 **모델의 베이스라인 능력(지식/선다형 안정성)**을 확인하는 **스크리닝** 도구로 보는 게 안전합니다.
- 도메인(예: 금융/의료/법무/사내정책)에서는 “정답률”보다 **근거 제시, 인용, 불확실성 표현, 거절/에스컬레이션**이 더 중요해지므로 별도 eval이 필요합니다.

### 2) HumanEval은 “작은 함수 단위 코딩”이며, 오염(contamination)·형식 의존성이 큼
HumanEval은 Python 함수 생성 문제로 pass@k(보통 pass@1)로 평가합니다. 하지만 널리 알려진 한계가 있습니다.

- **문제셋이 오래 공개**되어 학습 데이터 오염(contamination) 가능성이 상존  
- pass@k는 **샘플링 전략/temperature/생성 개수**에 따라 의미가 바뀜  
- 실제 업무는 단일 함수가 아니라 **다파일 변경, 테스트, 의존성, 빌드, 스타일, 보안**까지 포함

이런 “벤치마크-실무 괴리”는 HumanEval에서 특히 자주 언급됩니다. ([blog.imfsoftware.com](https://blog.imfsoftware.com/llm-wiki/docs/sources/humaneval-benchmark/?utm_source=openai))

실무적 의미:
- HumanEval은 “코딩 퍼즐”에 가깝고, 실제 제품개발 성과를 예측하려면 **SWE-bench 계열/리얼 코드베이스 기반** 또는 **사내 리포지토리 기반 eval**이 더 강한 신호를 줍니다(후술).

### 3) 점수 불일치의 주범: “프로토콜(=재현성)”
같은 벤치마크라도 아래가 바뀌면 점수가 흔들립니다.

- 프롬프트 템플릿(특히 MMLU류 few-shot)
- 디코딩(temperature, top_p), 샘플 수(pass@k)
- 토크나이저/컨텍스트 길이 제한
- 정답 파싱 규칙(선택지 추출, 공백/대소문자 처리)
- 버전이 다른 harness/태스크 정의

이 때문에 실무에서는 **LM Evaluation Harness** 같은 러너로 “내 환경에서 재현 가능한 점수”를 만드는 게 핵심입니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai))  
(하네스 릴리즈 노트에도 HumanEval 정렬/일치 수정 같은 항목이 계속 등장합니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai)))

---

## 💻 실전 코드
아래 예제는 “리더보드 점수”가 아니라 **우리 조직의 배포 의사결정**에 바로 쓰기 위한 구성입니다.

- 1단계: `lm-evaluation-harness`로 MMLU/HumanEval을 **동일 프로토콜**로 재현
- 2단계: 결과를 JSON으로 남기고 **회귀 체크(merge gate)**에 연결
- 3단계: HumanEval을 그대로 믿지 않고, **사내 코드 태스크(현실 시나리오)**를 추가하는 확장 포인트를 마련

### 0) 환경 준비
```bash
# Python 3.10+ 권장
python -m venv .venv
source .venv/bin/activate

pip install -U pip

# lm-evaluation-harness 설치 (버전 고정 권장: 재현성 핵심)
pip install "lm-eval==0.4.4"  # 예시: 실제로는 팀에서 합의한 버전으로 고정하세요

# OpenAI/호환 API를 쓸 경우(예: vLLM OpenAI server / 사내 gateway)
pip install openai python-dotenv
```

`.env`:
```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1   # 사내 OpenAI-compatible endpoint면 교체
MODEL_NAME=gpt-4o-mini                      # 예시
```

### 1) MMLU + HumanEval을 “같은 조건”으로 돌리기 (CLI)
```bash
export $(cat .env | xargs)

# MMLU (시간/비용 큼: 먼저 subset로 스모크 테스트 추천)
lm_eval \
  --model openai-chat-completions \
  --model_args model=$MODEL_NAME,base_url=$OPENAI_BASE_URL,api_key=$OPENAI_API_KEY \
  --tasks mmlu \
  --num_fewshot 5 \
  --batch_size 1 \
  --output_path runs/${MODEL_NAME}_mmlu.json

# HumanEval (pass@1 기준)
lm_eval \
  --model openai-chat-completions \
  --model_args model=$MODEL_NAME,base_url=$OPENAI_BASE_URL,api_key=$OPENAI_API_KEY \
  --tasks humaneval \
  --num_fewshot 0 \
  --batch_size 1 \
  --output_path runs/${MODEL_NAME}_humaneval.json
```

예상 출력(요지):
- `runs/...json`에 태스크별 score/metadata가 기록됩니다.
- 여기서 중요한 건 “점수” 자체보다 **동일한 러너/설정으로 반복 측정 가능한가**입니다. (하네스가 사실상 표준 러너로 널리 쓰입니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness?ref=Technology&utm_source=openai)))

### 2) 회귀 게이트: 이전 실행 대비 “의미 있는 하락”만 막기
실무에서는 0.2p 하락에 과민반응하면 비용만 늘고 개발이 멈춥니다. “노이즈 바닥”을 고려해 **허용 오차(guard band)**를 둡니다.

```python
# file: scripts/regression_gate.py
import json
import sys
from pathlib import Path

def load_score(path: Path, key: str) -> float:
    data = json.loads(path.read_text())
    # lm-eval 출력은 버전에 따라 구조가 조금씩 다를 수 있음
    # 아래는 대표적으로 results 아래 task명 아래 metric이 있는 형태를 가정
    # 필요 시 팀 출력 포맷에 맞춰 고정하세요.
    for task, res in data.get("results", {}).items():
        if key in res:
            return float(res[key])
    raise KeyError(f"Metric {key} not found in {path}")

def main():
    if len(sys.argv) != 5:
        print("Usage: regression_gate.py <baseline.json> <candidate.json> <metric_key> <max_drop>")
        sys.exit(2)

    baseline, candidate, metric_key, max_drop = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
    b = load_score(Path(baseline), metric_key)
    c = load_score(Path(candidate), metric_key)
    drop = b - c

    print(f"baseline={b:.4f} candidate={c:.4f} drop={drop:.4f} (allowed_drop={max_drop:.4f})")
    if drop > max_drop:
        print("FAIL: regression beyond threshold")
        sys.exit(1)
    print("PASS")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

CI 예시:
```bash
python scripts/regression_gate.py runs/model_prev_mmlu.json runs/model_new_mmlu.json acc 0.01
python scripts/regression_gate.py runs/model_prev_humaneval.json runs/model_new_humaneval.json pass@1 0.02
```

### 3) (중요) “사내 코드 태스크”를 추가해 HumanEval을 보정하는 방식
HumanEval이 단일 함수 생성에 치우치므로, 실제 배포 판단에는 아래 형태가 더 잘 맞습니다.

- 우리 repo의 대표 실패 유형 20~50개를 뽑아
- **Docker로 고정된 테스트 실행**(pytest/jest/go test)
- 모델 출력은 “패치(diff)”로 받고
- 채점은 “테스트 통과 여부 + lint + 보안 스캐너(선택)”로

이건 OpenAI Evals처럼 “루브릭/채점기” 기반으로도 운영할 수 있고(평가 자동화 프레임워크 관점) ([evals.openai.com](https://evals.openai.com/?utm_source=openai)), 또는 하네스에 커스텀 태스크(YAML/스크립트)를 붙이는 방식도 가능합니다. (하네스를 범용 러너로 쓰는 접근이 널리 공유됩니다. ([morphllm.com](https://www.morphllm.com/llm-eval-harness?utm_source=openai)))

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 효과 나는 3가지)
1) **“리더보드 점수” 대신 “내 프로토콜 점수”를 기준으로 삼기**  
   하네스 버전, 프롬프트 템플릿, 디코딩 파라미터를 고정하고(코드/락파일로) 재현성을 확보하세요. 하네스 릴리즈에서도 태스크 정렬/일치 수정이 지속적으로 이뤄집니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai))

2) **점수 하나가 아니라 “실패 모드별 슬라이스”로 본다**  
   예: MMLU에서도 subject별, HumanEval에서도 카테고리별(문자열/자료구조/재귀/예외처리)로 나눠서 “우리 서비스와 상관있는 구간”만 보세요. 총점은 PR에 쓰기 좋지만, 디버깅에는 거의 도움 안 됩니다.

3) **회귀 게이트는 ‘작은 하락 허용 + 큰 하락 차단’이 현실적**  
   MMLU류는 정답 오류/프롬프트 민감도 등으로 미세 차이가 과대해석되기 쉽습니다. “운영 의사결정을 바꾸는 하락”만 차단하는 쪽이 팀 생산성을 지킵니다. (MMLU 정답 오류 이슈가 보고됨) ([en.wikipedia.org](https://en.wikipedia.org/wiki/MMLU?utm_source=openai))

### 흔한 함정/안티패턴
- **MMLU 고득점 = 우리 도메인 지식 강함**으로 등치  
  실제로는 RAG/툴/정책 프롬프트가 더 큰 변수가 될 때가 많습니다.
- **HumanEval pass@1 하나로 코딩모델 결론**  
  오염 가능성 + 단일 함수 문제라는 구조적 한계 때문에, 실제 repo 기반 태스크로 반드시 보정하세요. ([blog.imfsoftware.com](https://blog.imfsoftware.com/llm-wiki/docs/sources/humaneval-benchmark/?utm_source=openai))
- **평가 러너를 자주 바꾸기**  
  모델이 바뀐 건지, 하네스가 바뀐 건지 구분이 안 됩니다. 분기별/반기별로만 러너 업그레이드를 허용하고, 업그레이드 PR에는 “동일 모델 재측정”을 강제하세요.

### 비용/성능/안정성 트레이드오프
- **비용**: MMLU 계열은 문항 수가 많아 API 비용이 큽니다. → 스모크(subset) → 정식(full) 2단계가 현실적.
- **성능**: temperature를 올려 pass@k를 키우면 “모델 능력”이 아니라 “샘플링 파워”를 측정할 수 있습니다. → 의사결정에 쓰려면 pass@1, temp=0 근처를 기본으로 두고, 별도로 “탐색형 설정”을 기록하세요.
- **안정성**: 모델/서빙이 바뀌면 같은 모델명이라도 결과가 달라질 수 있습니다. → 베이스 이미지, 런타임, 모델 리비전(가능하면 commit hash/weight hash)을 메타데이터로 남기세요.

---

## 🚀 마무리
정리하면, 2026년 6월 시점에 MMLU/HumanEval은 “쓸모없다”가 아니라 **그 자체로는 프로덕션 의사결정에 불충분**합니다.

- **MMLU/MMLU-Pro**: 지식/선다형 안정성의 스크리닝 도구(포화 + 오류/노이즈 고려) ([benchmarkingagents.com](https://benchmarkingagents.com/mmlu/?utm_source=openai))  
- **HumanEval**: 단일 함수 코딩 능력의 빠른 체크(오염/실무 괴리 보정 필수) ([blog.imfsoftware.com](https://blog.imfsoftware.com/llm-wiki/docs/sources/humaneval-benchmark/?utm_source=openai))  
- 진짜 핵심은 **동일 프로토콜로 반복 가능한 측정(하네스/프레임워크) + 사내 실패 모드에 맞춘 커스텀 eval**입니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness?ref=Technology&utm_source=openai))

도입 판단 기준(현실적인 체크리스트):
1) “우리 환경에서” MMLU/HumanEval을 재현할 수 있는가? (버전/파라미터 고정)  
2) 점수보다 **실패 모드 슬라이스**가 있는가?  
3) 최소 20~50개라도 **사내 repo/도메인 기반 golden eval**이 있는가?  
4) CI에서 회귀를 자동 차단할 수 있는가?

다음 학습 추천:
- `lm-evaluation-harness`로 커스텀 태스크(YAML/코드) 만드는 흐름 정리 ([github.com](https://github.com/EleutherAI/lm-evaluation-harness?ref=Technology&utm_source=openai))  
- OpenAI Evals 스타일로 “루브릭 기반 채점(LLM-as-a-judge)”을 넣되, judge 자체의 신뢰도 검증을 함께 설계 ([evals.openai.com](https://evals.openai.com/?utm_source=openai))  

원하면, 당신의 제품 유형(예: RAG QA / 코드 에이전트 / CS 자동응대)과 실패 사례 5~10개만 알려주시면, MMLU/HumanEval을 어떤 가중치로 보고 어떤 커스텀 eval을 추가해야 “점수 → 의사결정”으로 바뀌는지, 평가 설계안을 더 구체적으로 써드릴게요.