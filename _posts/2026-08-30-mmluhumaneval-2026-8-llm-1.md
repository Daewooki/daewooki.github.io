---
title: "MMLU·HumanEval 점수, 이제 그대로 믿으면 안 된다: 2026년 8월 기준 LLM 벤치마크 해석 실전 가이드"
date: 2026-08-30 05:00:59 +0900
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
LLM 성능을 “수치로” 비교해야 하는 순간이 있습니다. 모델 교체(비용/지연), fine-tuning 효과 검증, 릴리즈 회귀(regression) 탐지, 고객사 PoC 등. 이때 가장 흔히 보는 게 **MMLU(일반 지식/추론)**, **HumanEval(코드 생성)** 점수인데, 2026년 시점에 이 둘은 “모델의 진짜 실력”이라기보다 **평가 프로토콜을 얼마나 잘 맞췄는지**를 반영하는 경우가 많습니다.

- **언제 쓰면 좋나**:  
  1) 내부 모델/프롬프트/디코딩 변경의 **회귀 테스트**, 2) 같은 조건에서의 **상대 비교**, 3) “이 모델은 지식형/코드형 중 어디가 강한가” 같은 **대략적 성격 파악**.
- **언제 쓰면 안 되나**:  
  1) 프로덕션 품질(신뢰성, 일관성, 보안)을 **단일 점수로 보증**하려는 경우, 2) 서로 다른 공개 리더보드 점수들을 **그대로 섞어서 의사결정**하는 경우(프롬프트/샷 수/추출 규칙/디코딩이 다름), 3) “HumanEval 90%면 우리 레포 이슈도 90% 해결” 같은 **과잉 일반화**(실제로는 상관이 낮다는 리뷰/분석들이 계속 나옵니다). ([link.springer.com](https://link.springer.com/article/10.1007/s10462-026-11571-0?utm_source=openai))

---

## 🔧 핵심 개념
### 1) MMLU의 본질: “지식 + 선택지 게임”
MMLU는 다분야 객관식(MCQA)으로, 모델이 **정답 선택지(A/B/C/D…)를 맞히는지**를 봅니다. 문제는 (a) 정답 자체 오류, (b) 프롬프트 스타일 민감도, (c) 학습 데이터 contamination 가능성 때문에 점수 해석이 점점 어려워졌다는 것.

- **MMLU의 신뢰성 이슈(ground truth errors)**: MMLU-Redux 계열 작업은 MMLU에 오류가 적지 않음을 지적하며, 일부 서브셋은 오류 비율이 매우 높다고 보고합니다. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))  
  → 즉, “MMLU 1~2점 차이”는 모델 차이보다 **데이터/프로토콜 잡음**일 수 있습니다.

- **MMLU-Pro로의 이동**: MMLU가 포화/오류/쉬운 문제 문제를 드러내면서, TIGER-Lab의 **MMLU-Pro**가 대안으로 자리잡았습니다. 4지선다를 10지선다로 늘리고, 더 reasoning 중심으로 재구성하며, 프롬프트 변형에 대한 민감도를 낮추려는 설계를 합니다. ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))  
  핵심은 “더 어려워서 모델 간 분리가 잘 된다”이지만, 여전히 **프롬프트/추출/샷 수**가 통제되지 않으면 리더보드 비교가 깨집니다(로컬 커뮤니티에서도 regex/추출로 점수 출렁임을 많이 겪습니다). ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1e04c6e?utm_source=openai))

### 2) HumanEval의 본질: “함수 단위 + 테스트 통과 + pass@k”
HumanEval은 164개 정도의 파이썬 함수 생성 문제에서, 생성한 코드가 제공 테스트를 통과하면 성공으로 봅니다. 여기서 대부분 리더보드는 **pass@1, pass@10** 같은 형태를 사용합니다.

- **pass@k가 의미하는 것**: “k번 뽑아봤을 때 최소 1개가 맞을 확률”입니다. 따라서 k를 늘리면 점수가 올라가며, 이는 **‘최선의 샘플을 고를 수 있는 능력(=검증기/리랭커가 있는 상황)’**을 측정합니다. ([dreaming.press](https://dreaming.press/posts/2026-06-27-pass-at-k-vs-pass-hat-k-agent-reliability-evals.html?utm_source=openai))  
  프로덕션에서 중요한 “항상 잘 맞는가(신뢰성)”와는 다릅니다.

- **최근(2026년) 쟁점: pass@k의 오용**  
  2026년 8월 공개된 연구는, 에이전트/코드 생성 평가에서 pass@k 구현이 잘못 적용되는 사례(독립 시도 n과 테스트 개수 혼동 등)를 지적합니다. ([arxiv.org](https://arxiv.org/abs/2608.14711?utm_source=openai))  
  → 팀 내 벤치마크 코드가 “유명 레포니까 맞겠지”가 아니라, **내가 쓰는 harness가 n/k를 어떻게 정의하는지**를 반드시 확인해야 합니다.

### 3) “점수”를 “의사결정”으로 바꾸는 내부 흐름(추천)
실무에서는 벤치마크를 다음 파이프로 다루는 게 안전합니다.

1) **고정된 평가 프로토콜 정의**(프롬프트 템플릿, few-shot, temperature, max_tokens, stop, answer extraction)  
2) **모델 후보들을 동일 조건으로 실행**  
3) 단일 점수 대신 **서브스킬별 breakdown + 분산/신뢰구간**(seed/샘플링)  
4) 마지막에 **내 도메인 회귀 세트**(내 로그/티켓/레포 기반)로 교차검증

이 흐름을 자동화하는 실전 도구로는 LM Evaluation Harness가 널리 쓰이고, CLI/설정 기반으로 재현성을 확보하기 좋습니다. ([lm-evaluation-harness.readthedocs.io](https://lm-evaluation-harness.readthedocs.io/?utm_source=openai))

---

## 💻 실전 코드
아래는 “우리 팀이 모델 후보 2개를 **MMLU(또는 mmlu 변형)** + **HumanEval**로 돌리고, 결과를 저장하고, HumanEval은 pass@1뿐 아니라 **반복 실행으로 ‘신뢰성 지표’를 근사**”하는 현실적인 파이프라인 예시입니다.  
(전제: 사내/온프레 모델은 vLLM, 외부는 OpenAI-compatible endpoint로 붙는 경우가 많아 vLLM 백엔드 예시로 작성)

### 0) 환경/의존성
```bash
# 1) eval harness 설치
pip install "lm-eval[vllm]"  # vLLM 백엔드 사용
# 필요시: pip install "lm-eval[hf]"  # HF Transformers로도 가능

# 2) 결과 폴더
mkdir -p ./eval_out
```

### 1) 단일 실행: MMLU + HumanEval (고정 프로토콜)
```bash
# 모델 A를 동일 조건으로 평가
lm-eval run \
  --model vllm \
  --model_args "pretrained=/models/modelA,max_model_len=8192,tensor_parallel_size=2" \
  --tasks mmlu,humaneval \
  --num_fewshot 5 \
  --batch_size auto \
  --gen_kwargs "temperature=0.0,top_p=1.0,max_gen_toks=512" \
  --output_path ./eval_out/modelA_mmlu_humaneval.json \
  --log_samples

# 모델 B
lm-eval run \
  --model vllm \
  --model_args "pretrained=/models/modelB,max_model_len=8192,tensor_parallel_size=2" \
  --tasks mmlu,humaneval \
  --num_fewshot 5 \
  --batch_size auto \
  --gen_kwargs "temperature=0.0,top_p=1.0,max_gen_toks=512" \
  --output_path ./eval_out/modelB_mmlu_humaneval.json \
  --log_samples
```

예상 출력(요지):
- `./eval_out/*.json`에 태스크별 metric(예: MMLU accuracy, HumanEval pass@1 등)과 샘플 로그가 저장됩니다. harness는 CLI/설정으로 재현 가능한 실행을 지원합니다. ([github.com](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/interface.md?utm_source=openai))

### 2) 확장: HumanEval “신뢰성” 근사(반복 실행 → pass^k 스타일로 보기)
pass@k는 “k개 중 1개라도 성공”이라 프로덕션 신뢰성과 다릅니다. 그래서 간단히라도 **동일 프롬프트를 여러 번(seed/샘플링) 반복 실행**해서 “항상 통과하는 비율”을 보고 싶습니다(개념적으로 pass^k에 가까운 관점). 이 관점이 왜 중요한지는 pass@k vs pass^k 논의에서 잘 정리되어 있습니다. ([dreaming.press](https://dreaming.press/posts/2026-06-27-pass-at-k-vs-pass-hat-k-agent-reliability-evals.html?utm_source=openai))

아래는 “temperature를 약간 주고(0.2) N회 반복 → HumanEval pass@1의 평균/최소값을 기록”하는 스크립트입니다(회귀 테스트에 유용).

```python
import json, subprocess, time, statistics, pathlib

OUT = pathlib.Path("./eval_out")
OUT.mkdir(exist_ok=True)

def run_eval(model_path: str, tag: str, run_id: int):
    out_file = OUT / f"{tag}_humaneval_run{run_id}.json"
    cmd = [
        "lm-eval", "run",
        "--model", "vllm",
        "--model_args", f"pretrained={model_path},max_model_len=8192,tensor_parallel_size=2",
        "--tasks", "humaneval",
        "--num_fewshot", "0",
        "--batch_size", "auto",
        "--gen_kwargs", "temperature=0.2,top_p=0.95,max_gen_toks=512",
        "--output_path", str(out_file),
    ]
    subprocess.check_call(cmd)
    return out_file

def extract_humaneval_pass1(path: pathlib.Path) -> float:
    data = json.loads(path.read_text())
    # lm-eval 출력 스키마는 버전에 따라 다를 수 있어 방어적으로 접근
    # 보통 results 아래 태스크 키에 metric이 들어감
    results = data.get("results", {})
    humaneval = results.get("humaneval", {})
    # metric 이름도 버전에 따라 pass@1 / pass_at_1 등 변형 가능
    for k in ["pass@1", "pass_at_1", "pass_rate"]:
        if k in humaneval:
            return float(humaneval[k])
    raise KeyError(f"Can't find pass@1 metric keys in {humaneval.keys()}")

def summarize(model_path: str, tag: str, n_runs: int = 5):
    scores = []
    for i in range(n_runs):
        p = run_eval(model_path, tag, i)
        s = extract_humaneval_pass1(p)
        scores.append(s)
        time.sleep(0.5)

    summary = {
        "tag": tag,
        "n_runs": n_runs,
        "mean_pass1": statistics.mean(scores),
        "min_pass1": min(scores),
        "max_pass1": max(scores),
        "stdev_pass1": statistics.pstdev(scores),
        "all": scores,
    }
    (OUT / f"{tag}_humaneval_stability_summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    print(summary)

if __name__ == "__main__":
    summarize("/models/modelA", "modelA", n_runs=7)
```

이 방식의 장점:
- “우리 서비스는 rerank/검증기가 없으니 pass@10은 의미가 약하다” 같은 상황에서, **출렁임(variance)**을 숫자로 볼 수 있음
- 동일 모델이라도 서빙 설정/프롬프트/토크나이저/샘플링에 따라 점수가 흔들리는지 조기 감지

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **리더보드 점수는 ‘프로토콜 해시’가 없으면 비교하지 마세요**  
   MMLU-Pro는 “프롬프트 민감도를 낮추려는” 시도가 있지만, 완전히 사라지진 않습니다. 공식/비공식 구현에서 answer extraction(regex), system prompt, few-shot, CoT 유무가 다르면 점수는 쉽게 변합니다. ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))

2) **MMLU는 가능하면 Redux/Pro 계열로 교차 확인**  
   원본 MMLU는 오류 이슈가 널리 지적되었고, MMLU-Redux는 오류 라벨링/수정 방향을 제시합니다. 작은 점수 차이로 모델을 갈아타기 전에, 최소한 “오류 가능성이 큰 구간에서 이득을 본 건 아닌지”를 확인하세요. ([arxiv.org](https://arxiv.org/abs/2406.04127?utm_source=openai))

3) **HumanEval은 pass@1과 함께 ‘신뢰성 관점’ 지표를 같이 보세요**  
   pass@k는 best-of-n 성격이라 “에이전트/검증기”가 있을 때 유리합니다. 배포 형태가 단발 응답이면, 반복 실행 분산/최소값이 더 의사결정에 가깝습니다. ([dreaming.press](https://dreaming.press/posts/2026-06-27-pass-at-k-vs-pass-hat-k-agent-reliability-evals.html?utm_source=openai))

### 흔한 함정/안티패턴
- **디코딩 budget(샘플 수) 올려놓고 성능 향상이라 착각**: pass@k는 k에 민감합니다. k를 바꾸거나 temperature를 주고 샘플을 늘리면 점수가 오르는 건 자연스러운데, 이를 모델 개선으로 오해하는 경우가 많습니다. ([aresalab.com](https://aresalab.com/books/applied-ml-2026/ch-1?utm_source=openai))
- **HumanEval 고득점 → 레포 기반(SWE-bench류)도 잘할 것이라는 착각**: 함수 단위 테스트 통과와 실제 레포 이슈 해결은 다릅니다(상관이 낮다는 리뷰도 존재). ([link.springer.com](https://link.springer.com/article/10.1007/s10462-026-11571-0?utm_source=openai))
- **pass@k 구현/정의 확인 없이 숫자만 수집**: 2026년에도 pass@k가 잘못 적용되는 사례가 지적됩니다. 평가 코드에서 n/k의 정의(독립 시도 수 vs 다른 무엇)를 명확히 하세요. ([arxiv.org](https://arxiv.org/abs/2608.14711?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- MMLU류(MCQA)는 비교적 싸게 돌릴 수 있지만, **“정답 선택지 추출”**이 평가 품질을 좌우합니다. parsing이 불안정하면 비용을 들여도 쓰레기 데이터가 됩니다.
- HumanEval은 테스트 실행이 포함되므로, 대량 샘플(pass@10 등)로 갈수록 비용이 급증합니다. 실제 배포가 single-shot이면, pass@10 대신 **반복 실행 분산** 같은 더 직접적인 지표가 비용 대비 효율적일 때가 많습니다.

---

## 🚀 마무리
- **MMLU/HumanEval은 여전히 유용**하지만, 2026년 8월 기준으로는 “모델 능력의 절대값”이라기보다 **프로토콜 포함 상대 비교 지표**로 쓰는 게 안전합니다.  
- 도입 판단 기준(실무용):
  1) 우리 서비스가 **single-shot**인가, **best-of-n + verifier/reranker**가 있는가? → HumanEval은 pass@k 해석이 달라짐  
  2) MMLU는 **오류/포화/프롬프트 변형** 리스크를 감안해 Pro/Redux로 교차 확인할 것 ([arxiv.org](https://arxiv.org/abs/2406.01574?utm_source=openai))  
  3) 최종 결정은 “공개 벤치마크 + 우리 도메인 회귀 세트”의 **2트랙**으로

다음 학습/확장 추천:
- LM Evaluation Harness로 **내 태스크(도메인 Q&A / 코드베이스 규칙 / RAG 정답성)**를 태스크로 추가해, MMLU/HumanEval을 “외부 기준점”으로만 두고 내부 회귀를 주 평가로 올리는 구성을 권합니다. harness 자체가 재현 가능한 실행/설정 중심이라는 점이 이런 운영에 적합합니다. ([lm-evaluation-harness.readthedocs.io](https://lm-evaluation-harness.readthedocs.io/?utm_source=openai))