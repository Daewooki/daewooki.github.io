---
title: "FP8 KV-Cache부터 NVFP4까지: 2026년 4월 GPU LLM 서빙 최적화(quantization + 추론 가속) 실전 가이드"
date: 2026-04-26 03:44:00 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-04]
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
LLM 서빙에서 비용을 폭발시키는 진짜 원인은 “weights 연산량”만이 아니라, **긴 context + 높은 동시성**에서 터지는 **KV cache 메모리/대역폭**과, 부하 변동을 못 따라가는 **스케줄링/배칭 병목**입니다. 2026년 4월 기준, 이 문제를 가장 현실적으로 푸는 조합은 다음 두 축으로 정리됩니다.

- **Quantization(정밀도 낮추기)**: weights(예: INT4/NVFP4) + **KV cache(예: FP8)** 를 분리해서 낮춘다.
- **Inference acceleration(런타임 최적화)**: FlashInfer 같은 attention backend, CUDA Graphs, continuous batching, (가능하면) disaggregated serving로 파이프라인을 재배치한다. ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))

언제 쓰면 좋은가(추천):
- **긴 context(8K~32K) + 동시성 높음**: KV cache가 지배적인 비용이라 FP8 KV cache 효과가 크다. ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))
- **Blackwell(B200/GB200/GB300) 같은 최신 GPU**: FP8/NVFP4 같은 저정밀 텐서코어 경로가 성숙했고, TensorRT-LLM/NVIDIA 스택이 공격적으로 최적화 중. ([developer.nvidia.com](https://developer.nvidia.com/blog/delivering-massive-performance-leaps-for-mixture-of-experts-inference-on-nvidia-blackwell/?utm_source=openai))

언제 쓰면 안 되는가(주의/비추천):
- **정확도 민감(법률/의료/정산) + 회귀 테스트 체계 없음**: 특히 KV cache/attention quantization은 모델·GPU·커널 조합에 따라 “품질/출력 안정성” 이슈가 보고됩니다(일부 환경에서 FP8 KV cache가 출력 corruption을 유발했다는 사례 등). ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1rhmepa/qwen35122b_on_blackwell_sm120_fp8_kv_cache/?utm_source=openai))
- **팀이 운영 복잡도를 감당 못 하는 단계**: disaggregated serving(Dynamo/llm-d)은 성능 여지가 큰 대신, 모니터링/오토스케일/토폴로지 제약까지 같이 설계해야 합니다. ([developer.nvidia.com](https://developer.nvidia.com/blog/deploying-disaggregated-llm-inference-workloads-on-kubernetes/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) “weights quantization”과 “KV cache quantization”은 성격이 다르다
- **Weights quantization**(W8A8, INT4 weight-only, NVFP4 등): 주로 **모델 파라미터 메모리 + GEMM 효율**을 건드립니다.
  - 예: TensorRT-LLM은 SmoothQuant, INT4/INT8 weight-only, FP8 등을 문서화하고 있고, Blackwell에서는 FP4 계열(NVFP4 등)도 스택 차원에서 강조합니다. ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/reference/precision.html?utm_source=openai))
- **KV cache quantization**(FP8 KV cache): 주로 **동시성(capacity)과 decode bandwidth**를 건드립니다.
  - KV cache는 “요청 수 × 레이어 수 × 헤드 × seq_len”로 커져서, 긴 context/동시성에서 가장 먼저 HBM을 잡아먹습니다.
  - vLLM은 `--kv-cache-dtype fp8`로 KV cache를 FP8로 저장/연산하고, FlashInfer backend와 함께 Blackwell(B200)에서의 성능/정확도를 정리하며 “많은 long-context 배포의 기본 출발점”으로 보기에 충분하다고 결론 냈습니다. ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))

핵심 판단 기준:
- **OOM/동시성 부족**이면 → weights보다 **KV cache부터** 낮추는 게 “서빙 시스템 관점”에서 ROI가 큰 경우가 많습니다(특히 긴 context).

### 2) FP8 attention/KV cache가 빨라지는 구조적 이유
FP8을 “그냥 비트 줄여서 빠름”으로 이해하면 적용이 흔들립니다. 실제로는:
- **KV cache가 작아짐 → HBM traffic 감소 → decode가 빨라짐**
- **QK, ScoreV matmul이 FP8 텐서코어 경로로 가속**(구현/커널에 따라) ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))  
이때 중요한 건, FP8이 “연산”만이 아니라 “**메모리 병목**”을 직접 건드린다는 점입니다. decode는 토큰당 연산량이 작고 메모리 의존이 커서, KV cache 최적화가 체감 성능을 좌우합니다.

### 3) Disaggregated serving: prefill과 decode를 분리해 병목을 다른 방식으로 푼다
단일 프로세스(aggregated)로는 한 GPU에서 prefill(대규모 matmul)과 decode(메모리/대역폭 지배)를 같이 처리해야 해서, 워크로드 믹스가 나쁘면 양쪽이 서로 발목을 잡습니다.

- **Disaggregated**: prefill worker와 decode worker를 분리하고 KV cache를 전달/공유하는 방식
- NVIDIA Dynamo는 이 아키텍처를 “자동으로 튜닝”하는 AIConfigurator를 제공하고, 최적의 worker 수/TP 설정을 SLA(TTFT/TPOT) 기준으로 탐색한다고 안내합니다. ([docs.nvidia.com](https://docs.nvidia.com/dynamo/latest/user-guides/disaggregated-serving?utm_source=openai))
- llm-d 쪽은 KV cache 이동을 위해 NIXL 같은 데이터 무브먼트 레이어를 활용한다고 소개합니다. ([developer.nvidia.com](https://developer.nvidia.com/blog/nvidia-dynamo-accelerates-llm-d-community-initiatives-for-advancing-large-scale-distributed-inference/?utm_source=openai))

차이점 요약:
- quantization이 “한 노드/한 프로세스 내부 효율”을 주로 올린다면,
- disaggregation은 “클러스터 단위 리소스 배치/파이프라이닝”을 바꿔서 **TTFT-Throughput Pareto**를 넓히는 접근입니다.

---

## 💻 실전 코드
아래는 “긴 context + 동시성”을 가정한 **vLLM 기반 OpenAI-compatible 엔드포인트**를 띄우고, **FP8 KV cache + FlashInfer**를 켠 뒤, 간단한 부하 테스트로 TTFT/TPOT 변화를 확인하는 흐름입니다. (toy가 아니라, 바로 서비스에 붙이기 전 POC에서 흔히 하는 형태)

### 0) 전제(현실 체크)
- GPU: Hopper(H100/H200) 이상 또는 Blackwell(B200/GB200 계열)에서 효과가 잘 납니다.
- 드라이버/CUDA/컨테이너 조합에 따라 FlashInfer 커널 컴파일 이슈가 있을 수 있어, **컨테이너를 고정**하고 재현성부터 잡는 걸 권합니다(특히 Blackwell 초기 스택). ([docs.vultr.com](https://docs.vultr.com/inference-cookbook/cuda/optimization/kernel-backends?utm_source=openai))

### 1) 서버 실행 (Docker + vLLM)
```bash
# 1) 이미지(예시): vLLM OpenAI 서버
# 환경에 따라 태그/버전은 바꾸세요.
docker run --gpus all --rm -it \
  -p 8000:8000 \
  -e HF_TOKEN=$HF_TOKEN \
  -v $HOME/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen3-32B-FP8 \
    --dtype auto \
    --max-model-len 8192 \
    --max-num-seqs 256 \
    --gpu-memory-utilization 0.90 \
    --enable-prefix-caching \
    --attention-backend flashinfer \
    --kv-cache-dtype fp8
```

- `--kv-cache-dtype fp8`: KV cache를 FP8로 저장(동시성/메모리 개선의 핵심). ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))  
- `--attention-backend flashinfer`: Blackwell에서 주력 attention backend로 언급됩니다(다만 커널 튜닝/호환성은 계속 변동). ([docs.vultr.com](https://docs.vultr.com/inference-cookbook/cuda/optimization/kernel-backends?utm_source=openai))

예상 로그/현상(정상 범주):
- 첫 실행 시 FlashInfer/Triton 커널 컴파일로 cold start가 길 수 있음.
- 같은 설정이라도 GPU 아키텍처(sm 버전)에서 커널 선택이 달라 성능이 요동칠 수 있음.

### 2) 현실적인 부하 테스트(동시 요청 + 긴 프롬프트)
```python
import asyncio, time, statistics, os
from openai import AsyncOpenAI

# OpenAI-compatible vLLM endpoint
client = AsyncOpenAI(
    api_key="EMPTY",
    base_url=os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
)

PROMPT = "You are a senior backend engineer. " + ("Explain tradeoffs. " * 2000)  # 긴 context 유도

async def one_request(i: int):
    t0 = time.time()
    first_token_time = None
    out_tokens = 0

    stream = await client.chat.completions.create(
        model="Qwen/Qwen3-32B-FP8",
        messages=[{"role":"user","content":PROMPT}],
        temperature=0.2,
        max_tokens=256,
        stream=True
    )

    async for chunk in stream:
        dt = time.time() - t0
        if first_token_time is None and chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            first_token_time = dt
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            out_tokens += 1

    total = time.time() - t0
    ttft = first_token_time if first_token_time is not None else total
    tpot = (total - ttft) / max(out_tokens, 1)  # token 당 시간(대략)
    return ttft, tpot, total, out_tokens

async def main(concurrency=32):
    tasks = [asyncio.create_task(one_request(i)) for i in range(concurrency)]
    results = await asyncio.gather(*tasks)

    ttft = [r[0] for r in results]
    tpot = [r[1] for r in results]
    print(f"concurrency={concurrency}")
    print(f"TTFT p50={statistics.median(ttft):.3f}s  p95={sorted(ttft)[int(0.95*len(ttft))-1]:.3f}s")
    print(f"TPOT p50={statistics.median(tpot):.4f}s/token  p95={sorted(tpot)[int(0.95*len(tpot))-1]:.4f}s/token")

if __name__ == "__main__":
    asyncio.run(main(concurrency=32))
```

이 테스트를 **(A) BF16 KV cache** vs **(B) FP8 KV cache**로 비교하면 보통:
- FP8 KV cache에서 **OOM이 줄어들고**(= 더 높은 `max-num-seqs` 가능)
- 동시성 증가 시 **TPOT 악화가 덜한** 방향의 변화가 관측됩니다(워크로드에 따라 다름). ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))

### 3) (선택) Dynamo AIConfigurator로 “구성 탐색”을 자동화
K8s/클러스터에서 aggregated/disaggregated, prefill/decode worker 비율, TP 등을 직접 손으로 튜닝하면 시간이 끝도 없이 들어갑니다. Dynamo 문서의 예시처럼 AIConfigurator로 탐색한 뒤 매니페스트를 생성하는 흐름이 있습니다. ([docs.nvidia.com](https://docs.nvidia.com/dynamo/latest/user-guides/disaggregated-serving?utm_source=openai))
```bash
pip3 install aiconfigurator

aiconfigurator cli default \
  --model_path Qwen/Qwen3-32B-FP8 \
  --total_gpus 8 \
  --system h200_sxm \
  --backend vllm \
  --backend_version 0.12.0 \
  --isl 4000 \
  --osl 500 \
  --ttft 600 \
  --tpot 16.67 \
  --save_dir ./results_vllm

kubectl apply -f ./results_vllm/agg/top1/agg/k8s_deploy.yaml
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “KV cache부터” 최적화하는 게 더 싸게 먹히는 경우가 많다
weights INT4/NVFP4는 분명 강력하지만, 서빙 장애는 보통 **메모리(동시성)와 tail latency**에서 먼저 터집니다. 긴 context가 많다면:
- 1차: `--kv-cache-dtype fp8` + attention backend 최적화
- 2차: weights quantization(INT4/NVFP4/W8A8)로 내려가며 정확도/운영 이슈를 검증  
이 순서가 시행착오 비용이 낮습니다. ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))

### Best Practice 2) “커널/컴파일 캐시”까지 운영 요소로 본다
FlashInfer/Triton/torch.compile 조합은 cold start에서 커널 컴파일이 길고, 컨테이너 재시작/스케일아웃 시 TTFT가 튈 수 있습니다. Blackwell에서 FlashInfer가 주력으로 언급되지만, 일부 커널 튜닝이 아직 진행 중이라는 가이드도 있습니다. ([docs.vultr.com](https://docs.vultr.com/inference-cookbook/cuda/optimization/kernel-backends?utm_source=openai))  
- 운영 팁: 노드 부팅 시 워밍업 트래픽(헬스체크가 아니라 실제 prefill/decode)을 흘려 “커널 캐시를 만든 뒤” 트래픽을 붙이세요.

### Best Practice 3) Disaggregated serving은 “성능”이 아니라 “SLA 형태”를 바꾸는 도구
Disaggregation은 만능이 아니라, 목표가 명확할 때만 값어치를 합니다.
- **TTFT를 낮추고 싶다**(대화형): prefill 자원을 두껍게
- **Throughput을 뽑고 싶다**(배치/에이전트 병렬): decode 자원을 두껍게  
Dynamo는 이 결정을 자동화하는 포지션을 잡고 있고, 관련 문서/도구를 제공합니다. ([docs.nvidia.com](https://docs.nvidia.com/dynamo/latest/user-guides/disaggregated-serving?utm_source=openai))

### 흔한 함정 1) FP8 KV cache = 무조건 안전? (아님)
vLLM 쪽은 FP8 KV cache가 “기본 출발점으로 충분히 준비됐다”는 톤이지만, 실제 현장에서는 **특정 GPU(sm 버전)/모델/레이어 조합에서 이상 출력** 사례가 보고됩니다. ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))  
- 대응: “정확도 평가”를 거창하게 하지 말고, 최소한
  - 고정 시드 + golden 응답(샘플 수십~수백)
  - regression diff(문장 임베딩/정규식/스코어링)
  - 장애 시 자동 fallback(BF16 KV cache, 더 높은 정밀도)  
이 3개만 있어도 도입 성공률이 올라갑니다.

### 흔한 함정 2) NVFP4는 ‘형식’이지 ‘해결책’이 아니다
NVFP4는 Blackwell에 최적화된 4-bit 포맷으로 TensorRT-LLM/Model Optimizer 스택에서 강하게 밀고 있지만, **모델별 민감 레이어는 승격(promote)** 같은 mixed-precision 전략이 필요하다고 NVIDIA 리포트에서도 언급합니다. ([developer.nvidia.com](https://developer.nvidia.com/blog/delivering-massive-performance-leaps-for-mixture-of-experts-inference-on-nvidia-blackwell/?utm_source=openai))  
- 즉, “전 레이어 일괄 4bit”는 성능은 나와도 품질/안정성에서 발목 잡힐 확률이 큽니다.

### 비용/성능/안정성 트레이드오프(실무 결론)
- FP8 KV cache: **동시성/메모리 이득 큼**, 정확도 리스크는 비교적 관리 가능(그래도 검증 필수)
- INT4/NVFP4 weights: **비용 절감 잠재력 최대**, 대신 퀄리티/호환성/툴링 의존도가 커서 “운영 난이도”가 증가
- Disaggregation: **SLA를 원하는 형태로 조각낼 수 있음**, 대신 배포/관측/스케일링 설계가 프로젝트가 됨 ([developer.nvidia.com](https://developer.nvidia.com/blog/deploying-disaggregated-llm-inference-workloads-on-kubernetes/?utm_source=openai))

---

## 🚀 마무리
2026년 4월의 “GPU LLM 서빙 최적화”는 더 이상 단일 기법 싸움이 아니라, **(1) KV cache를 줄여 동시성을 확보하고(FP8 KV cache)**, **(2) attention/GEMM 커널을 최신 backend로 태우고(FlashInfer/TensorRT-LLM)**, **(3) 필요하면 서빙 아키텍처 자체를 분리(disaggregated)** 하는 3단 조합으로 굳어지고 있습니다. ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))

도입 판단 기준(빠른 체크리스트):
- 우리 트래픽은 긴 context/동시성이 높은가? → **Yes면 FP8 KV cache부터**
- 모델 정확도 회귀를 자동화할 수 있는가? → **No면 NVFP4/INT4는 보수적으로**
- TTFT/TPOT 목표가 명확한가(수치로)? → **Yes면 Dynamo/llm-d 같은 disaggregation 검토**

다음 학습 추천(우선순위):
1) vLLM의 FP8 KV cache/attention quantization 글을 기준으로, 내 모델에서 품질-성능 그래프를 직접 그려보기 ([vllm.ai](https://vllm.ai/blog/fp8-kvcache?utm_source=openai))  
2) TensorRT-LLM의 quantization(특히 KV cache/FP8/INT4 weight-only) 문서로 “어떤 정밀도가 어디에 적용되는지” 확인 ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/1.2.0rc5/features/quantization.html?utm_source=openai))  
3) 클러스터 운영이면 Dynamo AIConfigurator로 aggregated vs disaggregated를 “감”이 아니라 탐색 결과로 결정 ([docs.nvidia.com](https://docs.nvidia.com/dynamo/latest/user-guides/disaggregated-serving?utm_source=openai))

원하시면, (1) 사용 GPU(H100/H200/B200/RTX Blackwell), (2) 목표 SLA(TTFT/TPOT), (3) 평균 ISL/OSL, (4) 모델(예: Llama/Qwen/DeepSeek 계열) 정보를 기준으로 **권장 정밀도 조합(FP8 KV + W8A8? NVFP4? INT4 weight-only?)**과 **vLLM/SGLang/TensorRT-LLM 중 선택 가이드**까지 “적용 관점”으로 더 좁혀서 설계안을 써드릴게요.