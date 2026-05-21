---
title: "FP8 KV Cache부터 INT4 Weight-Only까지: 2026년 5월 기준 GPU LLM 서빙 최적화(Quantization·추론 가속) 실전 가이드"
date: 2026-05-21 04:24:20 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-05]
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
2026년의 LLM 서빙 병목은 “모델 weights를 GPU에 올리느냐”를 넘어, **KV cache가 VRAM을 집어삼키면서 batch/throughput을 무너뜨리는 문제**로 더 자주 나타납니다. vLLM/TensorRT-LLM/SGLang 같은 서빙 엔진들이 paged KV, continuous batching을 기본값으로 가져가면서, 이제 최적화의 승부처는 크게 두 가지로 정리됩니다:

- **(1) KV cache/attention 경로 최적화**: paged attention + KV cache quantization(FP8 중심) + 더 빠른 attention kernel(FlashAttention/FlashInfer/FlashMLA 등)
- **(2) Weight quantization + GEMM 최적화**: INT4/INT8 weight-only, FP8(W8A8) 같은 경로로 **prefill/decode GEMM을 더 싸게**

언제 쓰면 좋나?
- **긴 context(8K~256K) + 동시 요청 많음**: KV cache가 메모리 지배적이라 FP8 KV cache가 체감효과가 큼. vLLM은 `--kv-cache-dtype fp8`로 “저장만 FP8”이 아니라 **attention 연산 자체를 FP8 도메인에서 수행**하는 경로까지 지원합니다(backend 조건). ([docs.vllm.ai](https://docs.vllm.ai/en/v0.17.1/features/quantization/quantized_kvcache/?utm_source=openai))
- **H100/H200 같은 Hopper 계열**: FP8 지원이 성숙했고, attention/kernel 생태계가 FP8을 전제로 설계되는 흐름. ([docs.pytorch.org](https://docs.pytorch.org/TensorRT/user_guide/shapes_precision/quantization.html?utm_source=openai))
- **GPU가 부족한데 모델은 커야 함**: INT4 weight-only(AWQ/GPTQ/ModelOpt 등) + FP8 KV cache 조합이 “올릴 수 있는 모델/동시성”을 크게 바꿈. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.3/features/quantization/?utm_source=openai))

언제 쓰면 안 되나?
- **정밀도가 아주 중요한 출력(예: strict JSON, tool-call 토큰, 코드 생성에서 1글자 오류가 치명적)**: 특히 “스케일링/캘리브레이션이 빈약한” KV quant는 attention score의 작은 오차가 softmax에서 증폭되어 실패 패턴이 생길 수 있습니다(커뮤니티에서도 이 케이스가 반복적으로 보고됨). ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1t1t4nw/kv_cache_quantization_ignorance_or_malice/?utm_source=openai))
- **GPU가 FP8에 강하지 않은 세대(A100 이전/일부 RTX 환경) + kernel 경로가 불안정**: FP8을 켰는데 실제로는 dequant overhead나 fallback으로 이득이 사라질 수 있어 “측정 기반”으로만 결정해야 합니다. (특히 엔진/버전/attention backend 조합에 따라 달라짐) ([docs.vllm.ai](https://docs.vllm.ai/en/v0.17.1/features/quantization/quantized_kvcache/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) LLM 서빙에서 “진짜로” GPU가 바빠지는 구간
LLM 추론은 크게 두 단계입니다.

- **Prefill(프롬프트 처리)**: 시퀀스 길이 L에 대해 큰 GEMM이 돌고, attention도 L×L 성격이 강해 GPU 연산이 많이 듭니다.
- **Decode(토큰 1개씩 생성)**: 매 step마다 attention에서 **현재 토큰의 Q(1) × 과거 KV(L)**를 보므로, 연산 자체는 줄지만 **KV cache 읽기/쓰기(메모리 대역) + 작은 커널 수많은 호출(런타임 오버헤드)**이 병목이 되기 쉽습니다.

그래서 2026년 최적화는 “GEMM만 빠르게”가 아니라,
- **KV cache를 얼마나 효율적으로 저장/접근(paging)하고**
- **attention kernel을 얼마나 잘 고르며**
- **KV 자체를 quantize해서 VRAM과 대역폭을 줄이는지**
가 throughput을 결정합니다. vLLM의 PagedAttention/continuous batching이 여기서 기본 토대입니다. ([runpod.io](https://www.runpod.io/articles/guides/vllm-pagedattention-continuous-batching?utm_source=openai))

### 2) PagedAttention: KV cache를 OS 페이지처럼 다루는 이유
기존 구현은 요청마다 “연속된 큰 KV 텐서”를 잡아 VRAM 낭비(외부 단편화, over-allocation)를 만들었습니다. PagedAttention은 KV를 **fixed-size block(page)**로 쪼개 pool에 넣고, 요청별로 필요한 block만 매핑합니다. 덕분에
- 동시 요청이 늘어도 메모리 단편화가 줄고
- continuous batching에서 batch 구성이 매 step 바뀌어도 KV 관리가 견딥니다. ([runpod.io](https://www.runpod.io/articles/guides/vllm-pagedattention-continuous-batching?utm_source=openai))

### 3) KV cache quantization: “저장만”이 아니라 “attention 연산 경로”를 바꾸는 최적화
KV cache quantization은 보통 다음 중 하나로 나뉩니다.

- **Storage-only quant**: KV를 FP8/INT8/INT4로 저장하고, attention 직전에 FP16/BF16로 복원(dequant)해서 계산.
- **Quantized attention path**: KV를 FP8로 저장하고, **QK 및 ScoreV matmul을 FP8 도메인에서 수행**해 bandwidth뿐 아니라 연산 경로도 최적화.

vLLM 문서/블로그에서는 FP8 KV cache 사용 시(특정 backend에서) **attention 연산이 quantized domain에서 수행**된다고 명시합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.17.1/features/quantization/quantized_kvcache/?utm_source=openai))  
이게 중요한 이유는 decode에서 병목인 “L 길이 방향 contraction”이 FP16보다 FP8이 더 유리해져, **메모리 절감 + latency/throughput 개선**이 함께 나오기 때문입니다(단, GPU/커널 지원 전제). ([github.com](https://github.com/vllm-project/vllm-project.github.io/blob/main/_posts/2026-04-22-fp8-kvcache.md?utm_source=openai))

### 4) Weight quantization(특히 INT4 weight-only)와의 역할 분담
- **Weight-only INT4(AWQ/GPTQ 등)**: VRAM에서 weights가 차지하는 비중을 줄여 “모델을 올리는” 문제를 해결하고, GEMM을 더 싸게 돌릴 여지를 줍니다.
- **KV cache FP8**: 요청이 길어지고 동시성이 커질수록 weights보다 KV가 지배적이므로 “서빙 capacity”를 키웁니다.

즉, 2026년 실전 조합은 대체로:
- **(중대형 모델) INT4 weight-only + FP8 KV cache + paged attention**
이 기본 빌딩블록이 됩니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.3/features/quantization/?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “toy”가 아니라, **실제 서비스에서 자주 하는 구성**(OpenAI-compatible endpoint + concurrency + 측정)을 vLLM 기준으로 잡습니다. 핵심은 “옵션을 켜는 법”이 아니라 **측정/검증 루프**까지 포함하는 것입니다.

### 1) 초기 셋업: vLLM 서버 실행 (FP8 KV cache + FlashAttention/FlashInfer 경로)
```bash
# (권장) CUDA 환경에서 vLLM 설치
python -m venv .venv && source .venv/bin/activate
pip install -U "vllm>=0.17.1" "openai>=1.0.0" "httpx" "pydantic"

# 모델 예시: INT4(AWQ) 체크포인트 + FP8 KV cache
# 주의: 모델/GPU/드라이버에 따라 지원 조합이 달라서 반드시 A/B 테스트 필요
export MODEL="cyankiwi/Qwen3.6-27B-AWQ-INT4"

# vLLM OpenAI-compatible API 서버
# - kv-cache-dtype fp8: KV cache를 FP8로 저장(및 일부 backend에서 FP8 attention 경로)
# - max-model-len / max-num-seqs: 동시성-컨텍스트 트레이드오프 핵심 파라미터
# - attention-backend: 환경에 따라 FLASHINFER/FLASH_ATTN 등의 선택지가 성능에 큰 영향
vllm serve "$MODEL" \
  --host 0.0.0.0 --port 8000 \
  --dtype auto \
  --kv-cache-dtype fp8 \
  --max-model-len 32768 \
  --max-num-seqs 8 \
  --gpu-memory-utilization 0.90 \
  --attention-backend FLASHINFER
```

예상 출력(요지):
- 서버가 모델 로드 후 `Uvicorn running on ...`
- 로그에 KV cache dtype, attention backend 관련 설정이 노출됨  
(환경에 따라 FP8 관련 경고가 뜰 수 있는데, 예를 들어 “checkpoint scaling factor” 이슈처럼 **FP8 attention backend에서만 의미 있는 스케일 메타데이터**가 없을 때 성능/정확도 리스크가 생깁니다. 이런 경고는 무시하면 안 됩니다.) ([docs.vllm.ai](https://docs.vllm.ai/en/v0.17.1/features/quantization/quantized_kvcache/?utm_source=openai))

### 2) 현실적인 시나리오: 동시 요청 부하 + TTFT/throughput 측정
아래 파이썬은
- 긴 프롬프트(수천 토큰) + 생성
- 동시 요청 N개
- TTFT(time-to-first-token)와 overall latency를 수집
을 합니다. (실제론 토큰 카운팅/트레이싱/Prometheus까지 붙이지만, 최소 실행 단위로 구성)

```python
# benchmark_vllm_openai.py
import asyncio, time, statistics
from openai import AsyncOpenAI

BASE_URL = "http://localhost:8000/v1"
MODEL = "cyankiwi/Qwen3.6-27B-AWQ-INT4"

client = AsyncOpenAI(base_url=BASE_URL, api_key="EMPTY")

LONG_PROMPT = """
You are a senior backend engineer.
We are designing a GPU LLM serving stack.
Given the constraints below, propose a concrete configuration and justify tradeoffs.

Constraints:
- 1x H100 80GB
- traffic: 20 rps burst, long prompts 6k-12k tokens, outputs 200-800 tokens
- must support JSON tool-calls
- budget cap: keep GPU under 90% memory utilization
Return a structured answer with sections:
1) Serving engine
2) Quantization strategy for weights
3) KV cache strategy
4) Attention backend and why
5) Failure modes and mitigations
""" * 6  # 현실적인 "긴 프롬프트"를 의도적으로 구성(실전에서 흔히 보는 중복/규격 텍스트)

async def one_request(i: int):
    t0 = time.perf_counter()
    first_token_t = None
    out = []

    stream = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": LONG_PROMPT},
        ],
        temperature=0.2,
        max_tokens=400,
        stream=True,
    )

    async for ev in stream:
        if ev.choices and ev.choices[0].delta and ev.choices[0].delta.content:
            if first_token_t is None:
                first_token_t = time.perf_counter()
            out.append(ev.choices[0].delta.content)

    t1 = time.perf_counter()
    return {
        "id": i,
        "ttft_ms": (first_token_t - t0) * 1000 if first_token_t else None,
        "latency_ms": (t1 - t0) * 1000,
        "chars": sum(len(x) for x in out),
    }

async def main(concurrency: int = 8):
    tasks = [one_request(i) for i in range(concurrency)]
    res = await asyncio.gather(*tasks)

    ttfts = [r["ttft_ms"] for r in res if r["ttft_ms"] is not None]
    lats = [r["latency_ms"] for r in res]

    print(f"concurrency={concurrency}")
    print(f"TTFT ms:  p50={statistics.median(ttfts):.1f}, p95={sorted(ttfts)[int(len(ttfts)*0.95)-1]:.1f}")
    print(f"LAT  ms:  p50={statistics.median(lats):.1f}, p95={sorted(lats)[int(len(lats)*0.95)-1]:.1f}")
    print("samples:", res[:2])

if __name__ == "__main__":
    asyncio.run(main(8))
```

실무 포인트:
- **FP8 KV cache의 목적은** “더 많은 동시성(max-num-seqs)”을 같은 VRAM에서 먹이기 위함입니다. 그러니 벤치마크는 반드시 `max-num-seqs`/concurrency를 올리면서 **throughput이 어디서 꺾이는지**를 봐야 합니다.
- 긴 context에서는 KV가 지배적이라 FP8을 켠 차이가 훨씬 크게 나타납니다. vLLM은 이 기능을 명시적으로 제공하고, 장문 컨텍스트에서의 attention 경로까지 논의합니다. ([github.com](https://github.com/vllm-project/vllm-project.github.io/blob/main/_posts/2026-04-22-fp8-kvcache.md?utm_source=openai))

### 3) 확장: TensorRT-LLM/Torch-TensorRT로 “빌드 기반” 최적화(PTQ/FP8/FP4)
vLLM이 “운영 편의 + 배치/메모리 관리” 강점이라면, TensorRT-LLM/Torch-TensorRT는 **엔진 빌드(compile) 기반으로 커널/그래프를 더 공격적으로 최적화**하는 축입니다. Torch-TensorRT는 ModelOpt 기반으로 INT8/FP8/FP4 PTQ를 문서화하고 있습니다. ([docs.pytorch.org](https://docs.pytorch.org/TensorRT/user_guide/shapes_precision/quantization.html?utm_source=openai))

(여기서 중요한 판단 기준은 “엔진 빌드/배포 복잡도”를 감당할 만큼 latency/throughput 이득이 있는가입니다.)

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “KV cache FP8”은 batch/컨텍스트 정책과 세트로 튜닝하라
FP8 KV cache는 VRAM을 절약하지만, 그 절약분을 어떻게 쓸지(동시성↑ vs 컨텍스트↑ vs 안전마진↑)를 결정하지 않으면 체감이 작습니다.
- 운영적으로는 `--gpu-memory-utilization`을 보수적으로 잡고(예: 0.90),  
- `--max-model-len`과 `--max-num-seqs`를 **트래픽 분포(p50/p95 prompt length)**에 맞춰 두 개의 프로파일(예: short/long)로 나누는 게 안정적입니다.  
PagedAttention/continuous batching이 이런 “혼합 워크로드”에서 강점을 갖습니다. ([runpod.io](https://www.runpod.io/articles/guides/vllm-pagedattention-continuous-batching?utm_source=openai))

### Best Practice 2) Attention backend를 “기능”이 아니라 “커널 경로”로 봐라
vLLM은 FlashAttention/FlashInfer/기타 백엔드를 지원하고, FP8 KV cache는 특히 backend에 따라 **연산이 quantized domain에서 돌아가느냐/저장만 quantize냐**가 달라질 수 있습니다. 문서에서도 Flash Attention 3와 FP8 KV cache 조합에서 quantized domain attention을 언급합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.17.1/features/quantization/quantized_kvcache/?utm_source=openai))  
즉, “옵션 하나 켜기”가 아니라 **backend 조합별로 TTFT/throughput/정확도**를 재는 게 정답입니다.

### Best Practice 3) JSON/tool-call workload는 반드시 “정확도 리그레션 테스트”를 붙여라
KV quant/INT4 weight-only는 일반 대화에서는 티가 덜 나도,
- tool-call 토큰
- strict JSON
- 코드/스키마가 빡빡한 출력
에서는 작은 오차가 큰 장애로 이어질 수 있습니다. FP8 관련 스케일 메타데이터 경고나, KV quant 실패 모드는 실제 사용자 경험으로도 보고됩니다. ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1t1t4nw/kv_cache_quantization_ignorance_or_malice/?utm_source=openai))  
최소한 “샘플 200개 고정 프롬프트 + temperature=0 + exact match(또는 JSON parse 성공률)” 같은 게이트를 두세요.

### 흔한 함정) “INT4 weights면 KV도 더 길어질 것”이라고 착각
weights가 줄어도 **긴 context에서 VRAM을 잡아먹는 건 KV cache**입니다. 그래서 INT4로 모델을 올렸는데도 컨텍스트/동시성이 기대만큼 안 늘어나는 케이스가 흔합니다(커뮤니티에서도 KV가 VRAM을 빠르게 소모한다는 체감이 반복됨). ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1stc3pe/with_48gb_vram_on_vllm_qwen3627bawqint4_has_only/?utm_source=openai))  
해결은 결국 KV 전략(paged + FP8/INT8/더 공격적 압축) 쪽입니다.

### 비용/성능/안정성 트레이드오프
- **FP8 KV cache**: 보통 “메모리 절감 대비 품질 저하가 작다”는 방향으로 최적화가 집중되어 있고, vLLM도 이를 전면 기능으로 밀고 있습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.17.1/features/quantization/quantized_kvcache/?utm_source=openai))  
  다만 모델/백엔드/스케일링 메타에 따라 예외가 있으니, 운영 전 회귀 테스트는 필수.
- **INT8/INT4 KV cache**: 메모리 절감은 더 크지만 품질/안정성 리스크가 커질 수 있고, 연구/실험이 활발한 상태입니다(가속화된 INT8 KV quant 연구 등). ([arxiv.org](https://arxiv.org/abs/2601.04719?utm_source=openai))
- **TensorRT-LLM/Torch-TensorRT(엔진 빌드)**: 최고 성능 잠재력 vs 배포/업그레이드 복잡도. 릴리즈 노트/지원 매트릭스 따라가기 자체가 운영비용입니다. ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/release-notes.html?utm_source=openai))

---

## 🚀 마무리
2026년 5월 기준으로 “GPU LLM 서빙 최적화”를 프로젝트에 적용할 때의 결론은 단순합니다.

1) **긴 context + 동시성**이 문제라면:  
- PagedAttention(또는 동등 개념) + continuous batching이 기본이고,  
- 그 위에 **FP8 KV cache**가 가장 비용 대비 효과가 큰 레버입니다(vLLM은 `--kv-cache-dtype fp8`로 실전 적용이 쉽고, 일부 경로에선 attention 연산 자체도 FP8 도메인으로 최적화합니다). ([runpod.io](https://www.runpod.io/articles/guides/vllm-pagedattention-continuous-batching?utm_source=openai))

2) **모델을 “올리는 것”이 문제라면**:  
- INT4 weight-only(AWQ/GPTQ/ModelOpt 등)로 weights부터 줄이고,  
- 그 다음 KV가 병목으로 바뀌는 순간 FP8 KV cache로 넘어가세요. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.3/features/quantization/?utm_source=openai))

3) 도입 판단 기준(실무 체크리스트):
- (성능) TTFT/p95 latency/throughput을 **concurrency와 prompt length 분포**로 나눠 측정했는가?
- (정확도) JSON/tool-call 성공률 회귀테스트가 있는가? FP8 관련 경고를 “성능 로그”가 아니라 “정확도 리스크”로 처리하고 있는가? ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1t1t4nw/kv_cache_quantization_ignorance_or_malice/?utm_source=openai))
- (운영) 엔진 빌드 기반(TensorRT-LLM) 최적화의 배포 복잡도를 감당 가능한가? ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/release-notes.html?utm_source=openai))

다음 학습 추천(깊이 순):
- vLLM의 Quantized KV Cache 문서/FP8 KV cache 블로그(“attention이 왜 FP8에서 유리해지는지”까지 들어감) ([docs.vllm.ai](https://docs.vllm.ai/en/v0.17.1/features/quantization/quantized_kvcache/?utm_source=openai))
- FlashInfer 논문/서플(서빙 관점 attention kernel 설계와 FP8 KV 전제) ([proceedings.mlsys.org](https://proceedings.mlsys.org/paper_files/paper/2025/file/dbf02b21d77409a2db30e56866a8ab3a-Supplemental-Conference.pdf?utm_source=openai))
- TensorRT-LLM 릴리즈 노트 + Torch-TensorRT quantization 문서(ModelOpt 기반 FP8/FP4/INT8 PTQ) ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/release-notes.html?utm_source=openai))

원하면, 사용 중인 GPU(H100/H200/L40S/5090 등), 목표 모델(예: Llama 3.1 70B, Qwen 3.x 32B), 트래픽(평균 prompt 길이/동시성/응답 토큰)을 알려주면 위 코드/설정을 **“당신의 조건에서 가장 먼저 성능이 터질 지점”** 기준으로 튜닝 플랜(2~3개 프로파일 + 회귀테스트 항목)으로 재구성해드릴 수 있습니다.