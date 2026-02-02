---
title: "MMLU 점수 90점의 함정: 2026년 2월 기준 LLM 벤치마크(MMLU·HumanEval) 해석 가이드"
date: 2026-02-02 02:51:55 +0900
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
LLM을 “잘한다”고 말할 때, 우리는 대개 리더보드 숫자 한 줄(MMLU 90, HumanEval 95 등)로 결론을 냅니다. 하지만 2026년 2월 시점에는 이 방식이 점점 위험해졌습니다. 이유는 간단합니다. (1) MMLU 자체가 오래된 지식/문항 구조를 갖고 있고, (2) 코드 벤치마크(HumanEval)는 테스트가 얕으면 “그럴듯한 정답”이 과대평가되며, (3) 무엇보다 **contamination(학습 데이터에 평가셋이 섞임)** 이 점수를 무력화할 수 있기 때문입니다. 최근에는 contamination을 탐지/완화하려는 연구와 “강화판 벤치마크”들이 빠르게 확산되고 있습니다. ([arxiv.org](https://arxiv.org/abs/2510.27055?utm_source=openai))

이번 글에서는 2026년 2월 기준으로 **MMLU / HumanEval을 ‘평가 방법’ 관점에서 어떻게 해석해야 실무 의사결정에 도움이 되는지**를 기술 심층 분석으로 정리합니다.

---

## 🔧 핵심 개념
### 1) MMLU: “지식+추론”처럼 보이지만, 사실은 ‘형식’이 성능을 좌우한다
- **MMLU**는 57개 과목의 객관식(대개 4지선다) 문제로 general knowledge를 측정합니다. ([llmdb.com](https://llmdb.com/benchmarks/mmlu?utm_source=openai))  
- 문제는 LLM이 강해질수록 **(a) 보기의 분포를 학습**하거나 **(b) 프롬프트/출력 포맷 최적화**만으로도 점수가 오릅니다.  
- 그래서 최근에는 더 어려운 형태로 확장한 **MMLU-Pro(10지선다, 더 긴 reasoning 중심)** 같은 변형이 주목받습니다. “같은 MMLU 계열 점수”라도 난이도/선지 수가 바뀌면 의미가 달라집니다. ([llmdb.com](https://llmdb.com/benchmarks/mmlu-pro?utm_source=openai))

또한 영어 편향 문제를 줄이기 위해 **Global-MMLU(42개 언어, 문화 민감도 주석 포함)** 같은 멀티링구얼 벤치마크도 등장했습니다. ([llmdb.com](https://llmdb.com/benchmarks/global-mmlu?utm_source=openai))  
한 단계 더 나아가 “동일 문항을 29개 언어로 병렬 제공”해 언어 간 비교를 가능하게 한 **MMLU-ProX**도 제안되었습니다. ([mmluprox.github.io](https://mmluprox.github.io/?utm_source=openai))  
즉 2026년에는 “MMLU 점수”라고 퉁치면 안 되고, **어떤 MMLU인지**가 먼저입니다.

### 2) HumanEval: pass@k는 ‘모델의 코딩 능력’이 아니라 ‘평가 설계+테스트 강도’의 함수다
- **HumanEval**은 docstring 기반으로 함수를 작성하게 하고, 숨겨진 테스트로 functional correctness를 측정합니다. 기본 지표는 보통 **pass@1 / pass@k**입니다. ([github.com](https://github.com/openai/human-eval?utm_source=openai))  
- 하지만 원본 HumanEval은 테스트가 얕아 “운 좋게 통과”하거나 “특정 패턴을 외워서” 통과할 여지가 있습니다.
- 이를 보완하려고 **EvalPlus(HumanEval+)**가 제안되었고, 원본 대비 훨씬 많은 테스트로 통과 기준을 강화합니다. 실무 관점에서 HumanEval+가 더 “안전한” 이유가 여기 있습니다. ([openlm.ai](https://openlm.ai/coder-evalplus/?utm_source=openai))

추가로, 코드 생성 평가도 멀티링구얼/멀티모달로 확장되고 있습니다. 예를 들어 **HumanEval-X(여러 언어의 코드 생성/번역)**, 다이어그램을 읽고 코딩하는 **HumanEval-V** 같은 흐름은 “단순 Python 함수 문제”가 더 이상 충분한 대표성이 없다는 신호입니다. ([emergentmind.com](https://www.emergentmind.com/topics/humaneval-x-benchmark?utm_source=openai))

### 3) Contamination: “점수 상승”의 가장 큰 숨은 변수
벤치마크 해석에서 2025~2026년 가장 중요한 키워드는 contamination입니다. 최근 연구들은 다음을 말합니다.

- 단순한 텍스트 중복 탐지로는 부족하고, **모델 내부 거동(activation trajectory)** 를 보면 “외운 문제”가 조기 확신(shortcut) 패턴을 보인다는 접근(MemLens)이 나왔습니다. ([arxiv.org](https://arxiv.org/abs/2509.20909?utm_source=openai))  
- **in-context example이 오히려 성능을 떨어뜨리는 패턴**으로 “이미 학습된 데이터(외운 데이터)”를 구분하려는 방법(CoDeC)도 제안되었습니다. ([arxiv.org](https://arxiv.org/abs/2510.27055?utm_source=openai))  
- 더 적극적으로는 “현실 세계의 최신 지식으로 문항을 업데이트해 contamination-resilient 데이터셋을 만들자”(CoreEval) 같은 방향도 등장했습니다. ([arxiv.org](https://arxiv.org/abs/2511.18889?utm_source=openai))  

결론: 2026년에는 “MMLU/HumanEval 점수”를 볼 때 **그 점수가 ‘일반화’인지 ‘회상’인지**를 분리해서 생각해야 합니다.

---

## 💻 실전 코드
아래는 실무에서 자주 쓰는 **lm-evaluation-harness**로 MMLU 계열(예: mmlu)과 HumanEval 계열을 “같은 파이프라인”으로 돌리는 예시입니다. 최근 릴리즈에서 HumanEval/HumanEval+/MBPP+ 같은 코드 벤치마크 태스크가 추가/정리되고, chat template 적용 옵션도 제공됩니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai))  

```bash
# 1) 설치 (Python 3.9+ 권장: lm-eval이 3.8 지원을 드롭함)
pip install -U lm-eval

# 2) (예시) 로컬 HF 모델로 MMLU 평가
# - apply_chat_template: instruct/chat 모델에서 프롬프트 포맷 불일치를 줄임
# - num_fewshot: MMLU는 few-shot 설정에 민감하므로 반드시 명시
lm_eval \
  --model hf \
  --model_args pretrained=meta-llama/Llama-3.1-8B-Instruct,dtype=float16,trust_remote_code=True \
  --tasks mmlu \
  --num_fewshot 5 \
  --batch_size 8 \
  --apply_chat_template \
  --output_path ./eval_results/mmlu_llama31_8b.json

# 3) HumanEval(또는 humaneval 계열) 평가
# 주의: HumanEval은 "untrusted code execution" 이슈가 있어 sandbox가 필요함.
lm_eval \
  --model hf \
  --model_args pretrained=meta-llama/Llama-3.1-8B-Instruct,dtype=float16,trust_remote_code=True \
  --tasks humaneval \
  --batch_size 1 \
  --apply_chat_template \
  --output_path ./eval_results/humaneval_llama31_8b.json
```

핵심 포인트(주석으로 다시 강조):
- **MMLU는 few-shot 수/프롬프트 템플릿**에 따라 점수가 쉽게 흔들립니다. “리더보드 점수 재현”이 목표라면 설정을 고정해야 합니다.
- **HumanEval은 코드 실행**이 포함되므로 컨테이너/샌드박스(권한 제한, 타임아웃, 네트워크 차단)가 사실상 필수입니다. OpenAI의 human-eval 레포도 이 위험을 강하게 경고합니다. ([github.com](https://github.com/openai/human-eval?utm_source=openai))  

---

## ⚡ 실전 팁
1) **MMLU 점수는 ‘절대값’보다 ‘조건’을 먼저 기록**
- (모델, 버전, decoding 설정, chat template, few-shot 수, subject별 macro/micro 평균)를 함께 남기세요.  
- 특히 instruct 모델은 **chat template 미적용** 시 “문제 이해가 아니라 포맷 미스”로 점수가 빠질 수 있습니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai))  

2) **MMLU → MMLU-Pro/Global-MMLU로 “해석 가능성”을 보강**
- 일반 지식/추론을 보려면 MMLU만으로는 부족하고, 더 challenging한 MMLU-Pro 같은 변형을 같이 보는 게 안전합니다. ([llmdb.com](https://llmdb.com/benchmarks/mmlu-pro?utm_source=openai))  
- 글로벌 서비스라면 Global-MMLU나 MMLU-ProX처럼 멀티링구얼에서의 성능 하락폭을 봐야 “영어에서만 똑똑한 모델”을 걸러낼 수 있습니다. ([llmdb.com](https://llmdb.com/benchmarks/global-mmlu?utm_source=openai))  

3) **HumanEval은 반드시 HumanEval+와 함께 보라**
- 원본 HumanEval pass@1이 높아도, 테스트가 강화된 HumanEval+에서 급락하면 “정답같이 보이는 코드”일 가능성이 큽니다. ([openlm.ai](https://openlm.ai/coder-evalplus/?utm_source=openai))  
- 실무에서는 “통과율”보다 **실패 케이스 분류(경계값, 시간복잡도, 예외처리, I/O 변형)**가 더 큰 가치가 있습니다.

4) **Contamination을 ‘없다’고 가정하지 말고, ‘측정’의 영역으로 가져오기**
- 공개 가중치 모델/불명확한 학습 코퍼스 모델은 contamination 리스크가 큽니다.
- 최신 연구들은 activation/in-context 반응으로 contamination을 탐지하려는 방법(CoDeC, MemLens)을 제안하고 있고, 평가 보고서에 contamination 점검 절차를 포함하는 것이 점점 표준이 되는 흐름입니다. ([arxiv.org](https://arxiv.org/abs/2510.27055?utm_source=openai))  

---

## 🚀 마무리
2026년 2월 기준으로 MMLU와 HumanEval은 여전히 “기본 체력 테스트”로 유효하지만, 해석 방법은 예전과 달라야 합니다.

- MMLU는 **벤치마크 버전(MMLU vs MMLU-Pro vs Global-MMLU/MMLU-ProX)** 과 **평가 조건(few-shot, 템플릿)** 없이는 숫자 자체가 의미가 약합니다. ([llmdb.com](https://llmdb.com/benchmarks/mmlu-pro?utm_source=openai))  
- HumanEval은 반드시 **테스트 강화판(HumanEval+)** 과 함께 보고, pass@k를 “코딩 실력의 전부”로 오해하지 않아야 합니다. ([openlm.ai](https://openlm.ai/coder-evalplus/?utm_source=openai))  
- 무엇보다 contamination은 회피가 아니라 **측정/완화 전략**의 문제로 다뤄야 합니다. ([arxiv.org](https://arxiv.org/abs/2511.18889?utm_source=openai))  

다음 학습으로는 (1) lm-evaluation-harness에서 태스크 설정/프롬프트 템플릿이 점수에 미치는 영향 실험, (2) HumanEval+로 모델별 실패 유형 분석 리포트 자동화, (3) contamination 탐지 아이디어(CoDeC류)를 내부 평가 파이프라인에 체크리스트로 도입을 추천합니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/releases?utm_source=openai))