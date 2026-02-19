---
title: "LLM 성능평가의 함정: 2026년 2월 기준 MMLU·HumanEval 벤치마크를 “숫자”가 아니라 “방법”으로 읽는 법"
date: 2026-02-19 02:50:15 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-02]
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
LLM을 배포/운영하는 입장에서 “우리 모델이 더 똑똑해졌다”를 증명하는 가장 쉬운 방법은 MMLU, HumanEval 같은 벤치마크 점수를 가져오는 겁니다. 문제는 **점수는 쉬운데, 해석은 어렵다**는 것. 같은 모델이라도 프롬프트 템플릿, few-shot 개수, 출력 형식 강제, sampling 파라미터, 심지어 평가 도구 버전이 달라지면 점수가 흔들립니다. 실제로 현업에서 “리그테이블 1등”이 제품 품질을 보장하지 않는 이유의 대부분은 **평가 프로토콜의 차이**에서 나옵니다.

2026년 2월 시점엔 EleutherAI의 `lm-evaluation-harness`가 사실상 표준 실행기 역할을 하고 있고(최근 릴리스가 계속 갱신), MMLU는 변형 태스크(예: logits 기반, instruct 강제)가 늘어나면서 **‘MMLU 점수’라는 말 자체가 모호**해졌습니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases))

---

## 🔧 핵심 개념
### 1) MMLU는 “지식+추론”을 묻지만, 무엇을 강제하느냐가 점수를 만든다
`lm-evaluation-harness` 쪽 카탈로그를 보면 MMLU 계열이 여러 변종으로 나뉩니다. 대표적으로:
- `mmlu`: 기본 MMLU(57 subjects) ([docs.nvidia.com](https://docs.nvidia.com/nemo/evaluator/latest/evaluation/benchmarks/catalog/all/harnesses/lm-evaluation-harness.html))  
- `mmlu_instruct`: **출력을 단일 알파벳(letter)**로 강제하는 변형(채점 안정성 ↑, 대신 실제 챗모델 행태와 괴리 가능) ([docs.nvidia.com](https://docs.nvidia.com/nemo/evaluator/latest/evaluation/benchmarks/catalog/all/harnesses/lm-evaluation-harness.html))  
- `mmlu_logits`: **생성 텍스트가 아니라 logits로 정답 선택**(모델이 “설명 잘하다가 마지막에 헛소리” 하는 문제를 제거하지만, API 모델은 logprobs 미지원이면 평가 불가) ([docs.nvidia.com](https://docs.nvidia.com/nemo/evaluator/latest/evaluation/benchmarks/catalog/all/harnesses/lm-evaluation-harness.html))  
- `mmlu_pro`: MMLU-Pro(“더 어렵게” 만들기 위해 선택지 수를 늘린 버전으로 알려짐) ([docs.nvidia.com](https://docs.nvidia.com/nemo/evaluator/latest/evaluation/benchmarks/catalog/all/harnesses/lm-evaluation-harness.html))  

여기서 중요한 해석 포인트는:
- **생성 기반(letter 출력)**은 “모델이 지식이 있나?” + “지시를 잘 따르나?”가 섞입니다.
- **logits 기반**은 “모델 내부 분포가 정답을 더 선호하나?”에 가깝습니다.
- 따라서 MMLU 점수를 비교할 때는 “MMLU”가 아니라 **(태스크 변형, few-shot, chat template 적용 여부)**까지 같이 적어야 재현됩니다.

추가로 MMLU-Pro도 깔끔하지 않습니다. 데이터 카드/논의에서 “항상 10 choices”라고 생각했는데 실제 split에선 선택지 개수가 가변(3~10)인 항목이 존재하며, 이는 필터링/품질관리 과정 때문이라고 설명됩니다. 즉, “10지선다라서 guess 확률이 낮다” 같은 단순한 서술만 믿고 난이도를 단정하면 위험합니다. ([huggingface.co](https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro/discussions/22))

### 2) HumanEval은 “코드 형태”가 아니라 “실행 결과(Functional Correctness)”를 본다
HumanEval은 164개 문제에서 **docstring(요구사항) → Python 함수 코드 생성 → 숨겨진 unit test 통과 여부**로 측정합니다. ([deepwiki.com](https://deepwiki.com/EleutherAI/lm-evaluation-harness/3.4-code-generation-tasks?utm_source=openai))  
핵심은 “그럴듯한 코드”가 아니라 **테스트 통과**입니다. 그리고 실행 기반 평가라서 다음이 성패를 가릅니다:
- 프롬프트를 얼마나 원문 그대로 유지하느냐(공백/트렁케이션/템플릿 삽입)
- 모델 출력에서 “설명 텍스트”를 허용하느냐(코드만 파싱하느냐)
- 샌드박스/타임아웃/의존성 차이

실제로 HumanEval 실행기 구현에서 `unsafe_code: true`처럼 **코드 실행 자체가 필수이며 보안 리스크**가 동반된다는 점이 명시됩니다. ([deepwiki.com](https://deepwiki.com/EleutherAI/lm-evaluation-harness/3.4-code-generation-tasks?utm_source=openai))

### 3) pass@k는 편하지만, “샘플링 정책”이 곧 점수다
HumanEval은 종종 `pass@1`, `pass@k`를 씁니다. pass@k는 “k번 뽑아 하나라도 맞으면 성공” 확률이라서, temperature/탐색 정책이 바뀌면 점수가 크게 달라질 수 있습니다. ([emergentmind.com](https://www.emergentmind.com/topics/humaneval-dataset?utm_source=openai))  
게다가 2025년엔 pass@k가 랭킹을 불안정하게 만들 수 있다는 비판과 함께 Bayesian 관점의 대안 프레임워크도 제안됩니다(샘플 수가 제한될수록 더 문제). ([arxiv.org](https://arxiv.org/abs/2510.04265?utm_source=openai))

정리하면:
- **MMLU는 “채점 방식”이 점수를 만든다**
- **HumanEval은 “실행 환경/파서/샘플링”이 점수를 만든다**
- 따라서 벤치마크는 단일 숫자가 아니라 **프로토콜의 묶음**으로 읽어야 합니다.

---

## 💻 실전 코드
아래는 `lm-evaluation-harness(lm_eval)`로 MMLU/HumanEval을 **재현 가능하게** 돌리는 최소 예제입니다. 핵심은 “실행 커맨드”보다 **결과를 JSON으로 저장하고, 실행 조건을 같이 버전관리**하는 것입니다. (최근 릴리스에서 백엔드가 선택 설치로 바뀌는 등 환경 차이가 커졌습니다.) ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases))

```bash
# 1) 설치 (core + HF backend 예시)
python -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install "lm_eval" "transformers" "torch"

# 2) MMLU 평가 (instruct variant: letter 출력 강제)
# - apply_chat_template 여부가 instruct 모델 점수에 큰 영향
# - num_fewshot(0/5/10 등)도 반드시 명시
lm_eval \
  --model hf \
  --model_args pretrained=meta-llama/Llama-2-7b-hf \
  --tasks mmlu_instruct \
  --apply_chat_template \
  --num_fewshot 5 \
  --batch_size 4 \
  --output_path ./runs/mmlu_instruct_f5.json

# 3) HumanEval 평가
# - HumanEval은 코드 실행이 필요(실행환경/샌드박스 주의)
# - pass@1을 우선 고정(샘플링 영향 최소화) 후 pass@k 확장 권장
lm_eval \
  --model hf \
  --model_args pretrained=meta-llama/Llama-2-7b-hf \
  --tasks humaneval \
  --batch_size 1 \
  --output_path ./runs/humaneval_pass1.json
```

실무에서는 JSON 결과 파일에 더해 아래를 같이 남기세요.
- `lm_eval --version`(또는 패키지 lock)
- 모델 해시/리비전
- 프롬프트 템플릿(system prompt 포함)
- decoding 파라미터(temperature, top_p, max_new_tokens)
- HumanEval 실행 컨테이너/파이썬 버전/타임아웃

---

## ⚡ 실전 팁
1) **“MMLU 점수”라고 말하지 말고, 변형/설정을 같이 말하라**
- 예: `mmlu_instruct, 5-shot, chat template on` 같이 기록.
- logits 기반(`mmlu_logits`)은 해석이 더 “모델 자체 능력”에 가깝지만, 플랫폼 제약(예: logprobs 미지원)으로 재현이 어려울 수 있습니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/microservices/latest/evaluate/evaluation-types.html?utm_source=openai))

2) **HumanEval은 파서/포맷 규칙이 은근히 점수를 좌우한다**
- “설명 + 코드”를 허용하냐, fenced code만 받냐에 따라 통과율이 달라집니다.
- 프롬프트를 “원문 그대로” 유지하는 러너(출력/실패 사유 저장)처럼 **감사(audit)** 가능한 형태가 신뢰도를 올립니다. ([pypi.org](https://pypi.org/project/gguf-humaneval-benchmark/?utm_source=openai))

3) **pass@k는 ‘모델’ 성능이라기보다 ‘샘플링+예산’ 성능이다**
- pass@1을 기본 KPI로 두고,
- pass@k는 “동일한 샘플 수(n), 동일한 decoding”으로만 비교하세요.
- 샘플 수가 작다면 pass@k 랭킹이 출렁일 수 있다는 문제 제기도 있으니, 최소한 신뢰구간/반복 측정을 같이 제시하는 게 좋습니다. ([arxiv.org](https://arxiv.org/abs/2510.04265?utm_source=openai))

4) **HumanEval 고득점이 곧 ‘코드 이해’는 아니다**
- HumanEval은 “함수 작성”에 강하지만, 짧은 코드의 실행 추론/입출력 예측 같은 다른 축에선 상관이 약할 수 있습니다(예: CRUXEval이 보여주는 괴리). ([arxiv.org](https://arxiv.org/abs/2401.03065?utm_source=openai))  
즉, 제품이 요구하는 능력이 “코드 생성”인지 “코드 리뷰/추론”인지에 따라 벤치마크를 섞어야 합니다.

---

## 🚀 마무리
MMLU와 HumanEval은 여전히 유용하지만, 2026년 2월 기준으로는 더더욱 **“점수”보다 “평가 프로토콜”이 본체**입니다.  
- MMLU는 `instruct/logits/pro` 등 변형과 템플릿/샷 수가 점수 해석을 바꾸고 ([docs.nvidia.com](https://docs.nvidia.com/nemo/evaluator/latest/evaluation/benchmarks/catalog/all/harnesses/lm-evaluation-harness.html))  
- HumanEval은 실행 환경과 출력 파싱 규칙, 그리고 pass@k 샘플링 정책이 성능을 만든다 ([deepwiki.com](https://deepwiki.com/EleutherAI/lm-evaluation-harness/3.4-code-generation-tasks?utm_source=openai))  

다음 학습/확장으로는:
- `lm-evaluation-harness`에서 태스크 정의(yaml)와 채점 코드를 직접 읽고, 팀 표준 “평가 프로필”(템플릿/샷/디코딩/버전)을 고정해 내부 리더보드를 운영해보세요. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases))