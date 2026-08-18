---
title: "2026년 8월 기준: “GPU를 더 사기 전에” LLM 서빙을 2배 뽑아내는 Quantization & Inference Acceleration 실전 가이드"
date: 2026-08-18 01:39:55 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-08]
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
LLM 서빙 최적화의 본질은 **GPU FLOPS**가 아니라, 대부분의 경우 **메모리 대역폭 + KV cache 메모리 + 커널 런치/스케줄링 오버헤드**를 얼마나 줄이느냐입니다. 2026년 8월 시점에는 이 문제를 “가장 값싸게” 푸는 축이 명확해졌습니다:

- **Weights quantization (FP8/INT8/INT4)**: 모델 파라미터 적재/대역폭 감소 → 더 큰 모델/더 높은 batch/concurrency
- **KV cache quantization (FP8/INT8/FP4 계열)**: 디코드가 메모리-바운드인 상황에서 토큰당 비용을 직접 절감
- **Attention/GEMM kernel 가속(FlashAttention-3, FlashInfer, TRT-LLM 커널)**: mixed prefill/decode, ragged batch, paged KV cache에서 병목 제거

**언제 쓰면 좋나**
- 트래픽이 늘어 **concurrency**를 올려야 하는데 GPU 메모리가 부족할 때
- long context(예: 32k~256k)에서 디코드가 느리고 KV cache가 터질 때
- vLLM/TensorRT-LLM 같은 서빙 엔진을 쓰고 있고, “모델 자체”보다 “서빙 스택”에서 성능을 뽑아야 할 때

**언제 쓰면 안 되나**
- 출력 품질(특히 long-context, reasoning)이 매우 민감하고, 아직 **정량 평가/가드레일**이 없는 서비스
- latency tail(P99/P999)이 비즈니스적으로 치명적인데, 커널/그래프/스케줄링 변화로 **non-determinism** 리스크를 감당 못할 때(특히 mixed batching) ([docs.flashinfer.ai](https://docs.flashinfer.ai/api/attention.html?utm_source=openai))
- “일단 4bit 박으면 빨라지겠지” 같은 접근: 실제로는 **kernel 경로/스케일링/캘리브레이션**에 따라 느려질 수도 있습니다(특히 FP4/NVFP4는 하드웨어/커널 성숙도 영향을 크게 받음) ([docs.flashinfer.ai](https://docs.flashinfer.ai/api/quantization.html?utm_source=openai))

---

## 🔧 핵심 개념
### 1) 병목을 두 개로 쪼개서 보자: Prefill vs Decode
- **Prefill(프롬프트 처리)**: GEMM/attention compute 비중이 커지고, batch가 커질수록 Tensor Core를 잘 태우는지가 중요
- **Decode(토큰 생성)**: 한 토큰씩 진행 + KV cache를 매 토큰 읽음 → 대개 **메모리-바운드**. 그래서 “weights를 줄이는 것”보다 **KV cache를 줄이는 것**이 체감이 큽니다.

### 2) KV cache quantization이 “서빙 최적화의 중심”이 된 이유
vLLM은 FP8 KV cache를 켜면 KV cache 저장을 절반 수준으로 줄이고, attention의 QK/ScoreV matmul까지 FP8 경로로 태워 **decode cost 자체를 낮추는** 흐름을 강화했습니다. 특히 긴 컨텍스트/높은 동시성에서 KV cache가 병목이면, 이게 곧바로 동시성/컨텍스트 상한으로 이어집니다. ([vllm.ai](https://vllm.ai/blog/2026-04-22-fp8-kvcache?utm_source=openai))

또한 TensorRT-LLM도 KV cache를 **INT8/FP8 quant mode**로 관리하는 옵션을 공식 기능으로 제공하고 있어, “KV cache 저정밀화”는 사실상 업계 표준 레버가 됐습니다. ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/features/attention.html?utm_source=openai))

### 3) FP8/FP4/INT4… 정밀도 전쟁의 실제 결론(2026.8 현실)
- **FP8 (E4M3)**: (Hopper/Blackwell에서) 하드웨어 지원 + 커널 최적화가 가장 탄탄. weights/activation/KV cache에서 “일단 FP8부터”가 안전한 출발점. ([github.com](https://github.com/vllm-project/vllm/blob/main/docs/features/quantization/llm_compressor/fp8.md?utm_source=openai))  
- **FP4(NVFP4/MXFP4 등)**: 더 공격적이지만, 커널/툴체인(예: FlashInfer의 NVFP4/MXFP4 계열, CuTe-DSL 의존)과 워크로드 적합성이 중요. “이론상 이득”이 “실서빙 이득”으로 바로 안 나오는 케이스가 많습니다. ([docs.flashinfer.ai](https://docs.flashinfer.ai/api/quantization.html?utm_source=openai))  
- **INT4 weights (AWQ/GPTQ/Marlin 등)**: 메모리 절감은 강력하지만, 결국 성패는 **dequant+GEMM fused 커널 경로**를 제대로 타느냐(=fallback이면 손해)입니다. vLLM에서도 다양한 구현(예: Marlin)이 있고, 하드웨어/모델에 따라 결과가 갈립니다. ([docs.vllm.ai](https://docs.vllm.ai/_/downloads/en/v0.6.2/pdf/?utm_source=openai))  

### 4) “커널이 곧 제품”인 시대: FlashAttention-3 / FlashInfer / TRT-LLM
- FlashAttention-3는 Hopper에서 **asynchrony + FP8 저정밀**을 이용해 attention을 빠르고 안정적으로 만드는 설계를 제시했고, 실제로 vLLM에서도 FP8 attention 경로 개선/회귀 수정이 성능과 정확도에 직결되는 사례가 보고되었습니다. ([arxiv.org](https://arxiv.org/abs/2407.08608?utm_source=openai))  
- FlashInfer는 서빙 관점(continuous batching, mixed prefill/decode, paged KV cache 등)에서 커널 라이브러리로 자리잡았고, vLLM/SGLang 등에서 실제 백엔드로 통합되는 흐름이 강합니다. ([arxiv.org](https://arxiv.org/abs/2501.01005?utm_source=openai))  

---

## 💻 실전 코드
아래는 “현실적인” 상황(여러 사용자가 동시에 긴 컨텍스트 + 스트리밍 생성)을 가정해 **vLLM에서 KV cache FP8 + FlashInfer attention backend**를 켜고, 동시에 **서빙 품질 리스크를 줄이기 위해 sliding-window 계열 레이어를 스킵**하는 형태까지 포함합니다(하이브리드 attention 모델에서 유용). ([vllm.ai](https://vllm.ai/blog/2026-04-22-fp8-kvcache?utm_source=openai))

### 1단계) 환경/의존성 (CUDA 서버)
```bash
# (예) Python 3.10+
python -m venv .venv && source .venv/bin/activate

# vLLM 설치(환경에 맞는 CUDA wheel 사용 권장)
pip install -U vllm

# FlashInfer 설치 (vLLM이 FlashInfer backend를 사용할 때 필요)
pip install -U flashinfer

# (권장) 성능/디버깅 도구
pip install -U prometheus-client aiohttp
```

### 2단계) vLLM 서버 실행: FP8 KV cache + FlashInfer + 동시성 타겟팅
```bash
# 모델은 예시. 실제로는 FP8 weights checkpoint(또는 BF16+KV FP8) 조합을 선택.
# 핵심은 KV cache dtype과 attention backend를 명시적으로 “성능 좋은 경로”로 고정하는 것.

export CUDA_VISIBLE_DEVICES=0

vllm serve meta-llama/Llama-3.1-8B \
  --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 131072 \
  --kv-cache-dtype fp8 \
  --attention-backend flashinfer \
  --enable-chunked-prefill \
  --max-num-batched-tokens 8192
```

**예상되는 관찰 포인트(출력/로그가 아니라 “측정 지표”)**
- 같은 GPU에서 **동시 요청 수(concurrency)**가 상승하거나, 같은 concurrency에서 **ITL(inter-token latency)**가 감소
- long context에서 OOM이 나던 것이 **KV cache 절감**으로 버티기 시작
- 반대로, 특정 모델(head_dim=256 등)이나 하이브리드 attention 구조에서는 prefill이 미세하게 손해를 볼 수 있으니 A/B 측정이 필요(2026년 vLLM 검증 결과에서도 이런 caveat가 언급됨). ([vllm.ai](https://vllm.ai/blog/2026-04-22-fp8-kvcache?utm_source=openai))  

### 3단계) “품질 리스크 줄이기”: sliding-window 계열 레이어 스킵(가능할 때만)
하이브리드 attention 모델에서 FP8 KV cache가 항상 이득이 아니고, sliding-window 레이어를 스킵하는 게 더 낫다는 권고가 있습니다. ([vllm.ai](https://vllm.ai/blog/2026-04-22-fp8-kvcache?utm_source=openai))

```bash
vllm serve gpt-oss-20b \
  --host 0.0.0.0 --port 8000 \
  --max-model-len 131072 \
  --kv-cache-dtype fp8 \
  --kv-cache-dtype-skip-layers sliding_window \
  --attention-backend flashinfer
```

### (선택) FlashInfer에서 “paged KV cache를 더 공격적으로” 다루고 싶을 때의 힌트
FlashInfer는 quantization 유틸/커널(API)에서 **paged KV cache를 NVFP4로 quantize**하는 기능까지 노출합니다. 다만 이건 “바로 서빙에 꽂는 옵션”이라기보다, 엔진 통합(또는 커스텀 런타임)에서 의미가 큽니다. ([docs.flashinfer.ai](https://docs.flashinfer.ai/api/quantization.html?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “정밀도”보다 먼저 “병목”을 계측해라
- decode가 느리면: **KV cache quantization(FP8)** + paged KV cache + attention kernel이 먼저
- prefill이 느리면: weights FP8, fused GEMM 경로, chunked prefill, max-num-batched-tokens 튜닝이 먼저  
특히 vLLM의 FP8 KV cache는 **메모리 절감(=concurrency)**과 **decode 비용**에 직결되도록 설계/검증이 진행된 케이스라 우선순위가 높습니다. ([vllm.ai](https://vllm.ai/blog/2026-04-22-fp8-kvcache?utm_source=openai))

### Best Practice 2) “fallback 커널”을 피하는 게 4bit 성공의 80%
INT4/AWQ/GPTQ를 쓰더라도, 실제로는 특정 shape/하드웨어에서 optimized kernel을 못 타고 fallback이 되면 **dequant 비용 때문에 느려질** 수 있습니다. vLLM도 quantization 구현이 여러 갈래로 존재하니(예: Marlin 등) “내 GPU에서 어떤 경로를 타는지”를 로그/프로파일로 확인하세요. ([docs.vllm.ai](https://docs.vllm.ai/_/downloads/en/v0.6.2/pdf/?utm_source=openai))

### Best Practice 3) Blackwell 계열에서는 FlashInfer/FP8/FP4의 “지원 매트릭스”를 먼저 확인
FlashInfer의 일부 quantization 커널은 SM100+와 추가 의존성(cuda.tile 등)을 요구하는 등, 하드웨어 세대/패키지 조건이 빡빡합니다. “설치되면 되는 줄” 알았다가 운영 환경에서 재현이 안 되는 경우가 흔합니다. ([docs.flashinfer.ai](https://docs.flashinfer.ai/api/quantization.html?utm_source=openai))

### 흔한 함정) CUDA Graph 만능론
mixed prefill/decode, ragged batch, kv seq len 변동이 크면 CUDA Graph 호환성이 깨지거나 이득이 제한될 수 있습니다(FlashInfer 문서에서도 호환 보장이 없다고 명시). 즉, “고정 shape”가 안 나오는 서빙에서는 Graph보다 **스케줄링/continuous batching**이 더 중요해지는 경우가 많습니다. ([docs.flashinfer.ai](https://docs.flashinfer.ai/api/attention.html?utm_source=openai))

### 비용/성능/안정성 트레이드오프(현실적인 결론)
- **가장 안전한 성능 레버**: FP8 KV cache + 검증된 attention backend(FlashAttention/FlashInfer)  
- **가장 큰 비용 절감 레버**: INT4 weights(단, 커널 경로가 맞아야 함)  
- **가장 리스크 큰 최적화**: FP4 계열(성능 잠재력은 크지만, 커널 성숙도/모델 적합성/툴체인 의존이 큼) ([docs.flashinfer.ai](https://docs.flashinfer.ai/api/quantization.html?utm_source=openai))

---

## 🚀 마무리
2026년 8월 기준으로 “GPU LLM 서빙 최적화”는 더 이상 추상적인 튜닝이 아니라, **(1) KV cache를 FP8 등으로 줄이고 (2) attention/GEMM 커널이 최적 경로를 타게 하며 (3) mixed batching에서의 스케줄링/메모리 압력을 관리**하는 엔지니어링 문제로 수렴했습니다. 특히 vLLM의 FP8 KV cache는 단순 메모리 절감이 아니라 **attention 계산 경로까지 저정밀 최적화**로 엮여 있어, long context + 높은 concurrency에서 투자 대비 효과가 큽니다. ([vllm.ai](https://vllm.ai/blog/2026-04-22-fp8-kvcache?utm_source=openai))

**도입 판단 기준(체크리스트)**
- 내 서비스가 decode-bound인가? (ITL, KV cache 메모리, GPU mem bandwidth)
- long context / 높은 concurrency가 핵심 KPI인가?
- 내 GPU(Hopper/Blackwell/Ampere)에 맞는 **커널 경로**를 확실히 탈 수 있는가?
- 품질 저하를 막을 평가셋(특히 long-context/needle 테스트)이 있는가? (없으면 FP8 KV cache부터 작게 시작)

**다음 학습 추천(우선순위)**
1) vLLM의 FP8 KV cache/attention quantization 검증 포인트(언제 피해야 하는지 포함) ([vllm.ai](https://vllm.ai/blog/2026-04-22-fp8-kvcache?utm_source=openai))  
2) TensorRT-LLM의 KV cache quant mode 및 transformer fusions(서빙 스택 설계 관점) ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/features/attention.html?utm_source=openai))  
3) FlashInfer의 attention/quantization API와 mixed batching 제약(특히 CUDA Graph/shape 변동) ([docs.flashinfer.ai](https://docs.flashinfer.ai/api/attention.html?utm_source=openai))  

원하면, **당신의 GPU 모델/목표(SLO), 모델(예: Qwen/Llama/MoE), 평균 프롬프트 길이/동시성**을 기준으로 “FP8 KV cache vs INT4 weights vs FP4 시도” 우선순위를 표 형태로 정리해 줄 수 있어요.