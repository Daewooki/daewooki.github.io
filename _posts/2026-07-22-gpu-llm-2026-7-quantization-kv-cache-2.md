---
title: "GPU를 “갈아넣지 않고” LLM 서빙 성능 뽑는 법: 2026년 7월 기준 Quantization + KV cache + 커널/런타임 최적화 실전 가이드"
date: 2026-07-22 03:27:17 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-07]
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
LLM 서빙에서 GPU 비용을 폭발시키는 주범은 대개 **(1) KV cache 메모리 압박**과 **(2) decode 단계의 메모리 대역폭 병목**입니다. 모델 weight만 줄인다고 해결되지 않는 이유는, 동시성(concurrency)과 긴 context에서 **KV cache가 VRAM을 선형으로 잠식**하고, 결국 **배치/동시 요청을 못 올려 tokens/s가 무너지는** 패턴이 흔하기 때문입니다.

**언제 쓰면 좋은가**
- “채팅형”처럼 **prefill 대비 decode 비중이 큰** 워크로드(긴 대화, streaming 출력)
- RAG/에이전트처럼 **동시 요청이 늘었다 줄었다** 하고, 평균보다 **피크 트래픽**을 버텨야 하는 서비스
- GPU가 H100/H200/B200/GB200처럼 최신일수록(특히 FP8/FP4 계열 지원) 효과가 큼. Blackwell은 **NVFP4(=FP4 계열) 기반 추론 최적화**가 강하게 밀리고 있음 ([developer.nvidia.com](https://developer.nvidia.com/blog/nvidia-blackwell-sets-stac-ai-record-for-llm-inference-in-finance/?utm_source=openai))

**언제 쓰면 안 되는가**
- 응답이 짧고 동시성이 낮은 “사내 도구” 수준(최적화 복잡도가 비용 초과)
- 정확도/안정성이 절대적인 도메인(법률/의료 등)에서 **INT4·FP4**를 “그냥” 적용하려는 경우: 회귀 테스트/가드레일 없으면 리스크가 큼
- GPU가 구형이고(예: 일부 SM80 등) 원하는 dtype 경로가 느리거나 에뮬레이션이면, 오히려 latency가 악화될 수 있음(특히 KV cache quant가 커널 경로에 따라 함정이 많음)

---

## 🔧 핵심 개념
### 1) LLM 서빙의 병목은 “GEMM”만이 아니다
서빙을 단순화하면:
1) **prefill**: prompt 전체를 한 번에 통과 → 상대적으로 GEMM 비중이 큼  
2) **decode**: 토큰을 1개씩 생성 → attention이 반복되고 **KV cache read/write**가 지배적

따라서 “weight-only INT4(W4A16)”로 weight VRAM을 줄여도, 동시성이 올라가면 KV cache가 남는 VRAM을 다 먹고, 결국 **동시 request 수를 못 올려 tokens/s가 제한**됩니다. 여기서 **KV cache quantization**이 체감 효율을 크게 바꿉니다.

### 2) Quantization을 3개 층으로 나눠라: Weights / Activations / KV cache
2026년 실전에서 가장 많이 쓰는 축은 아래 3가지입니다.

- **Weight-only quant (INT8/INT4; W8A16, W4A16)**  
  weight 메모리·대역폭 감소. 다만 decode에서는 KV cache가 더 큰 병목이 될 수 있음. TensorRT-LLM은 INT4/INT8 weight-only를 주요 옵션으로 제공 ([github.com](https://github.com/nyunAI/TensorRT-LLM/blob/main/README.md?utm_source=openai))
- **FP8 (weights+activations 또는 kernel 경로)**  
  Hopper에서는 FP8이 “실전 디폴트”가 되었고, Blackwell은 FP8을 넘어 **NVFP4**를 강하게 전면에 둠 ([developer.nvidia.com](https://developer.nvidia.com/blog/nvidia-blackwell-sets-stac-ai-record-for-llm-inference-in-finance/?utm_source=openai))
- **KV cache quant (FP8/INT8/INT4 등)**  
  동시성(=캐시 용량)과 decode throughput의 핵심 레버. TensorRT-LLM은 FP8 KV cache 옵션을 명시적으로 다루며 ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/performance/performance-tuning-guide/fp8-quantization.html?utm_source=openai)), KV cache를 INT8로 압축해 **4× 메모리 절감**을 보고한 연구도 있음 ([arxiv.org](https://arxiv.org/abs/2601.04719?utm_source=openai))  
  또한 “시스템-양자화 공동 설계”로 KV를 INT4로 내리는 계열(QServe 등)도 성능 이점을 보임 ([proceedings.mlsys.org](https://proceedings.mlsys.org/paper_files/paper/2025/file/fbe2b2f74a2ece8070d8fb073717bda6-Paper-Conference.pdf?utm_source=openai))

핵심은 “더 낮은 bit가 무조건 빠르다”가 아니라:
- **메모리 대역폭이 병목이면** KV cache 압축이 throughput을 올릴 수 있고
- **연산/커널 오버헤드가 병목이면** 너무 공격적인 KV quant가 오히려 느려질 수 있다는 점입니다.

### 3) 2026년 흐름: Blackwell + NVFP4 + (런타임) + (attention 커널)
Blackwell(B200/GB200) 쪽은 “FP4까지”를 전제로 한 Transformer Engine·TensorRT-LLM 최적화가 계속 누적되고 있습니다. 특히 micro-tensor scaling 같은 동적 범위 관리가 FP4 계열을 성립시키는 기반으로 언급됩니다 ([docs.nvidia.com](https://docs.nvidia.com/multi-node-nvlink-systems/multi-node-tuning-guide/overview.html?utm_source=openai)).  
또한 “가장 빠른 커널을 자동으로 타게 만드는” 것이 중요해져서, vLLM처럼 다양한 quant/dtype과 attention 커널을 폭넓게 지원하는 런타임이 실무 선택지로 자리잡았습니다 ([docs.vllm.ai](https://docs.vllm.ai/en/latest/index.html?utm_source=openai))

---

## 💻 실전 코드
아래는 “**현실적인 서빙 시나리오**”를 가정한 예제입니다.

- 모델: (예시) 30B급 FP8 체크포인트 또는 BF16 + 런타임 quant
- 목표: **TTFT(Time-to-first-token)와 steady-state tokens/s**를 함께 본다
- 전략:
  1) vLLM로 baseline 서빙
  2) KV cache dtype을 FP8로 내려 동시성/throughput을 확보
  3) (가능하면) weight quant(AWQ/GPTQ/INT4 등)까지 조합해 VRAM을 추가로 확보

### 1) 초기 셋업
```bash
# (권장) 격리 환경
python -m venv .venv && source .venv/bin/activate

# CUDA 환경은 시스템에 맞게 준비되어 있다고 가정
pip install -U vllm==0.* fastapi uvicorn

# 성능 측정용
pip install -U aiohttp numpy
```

### 2) OpenAI-compatible API로 서빙 (baseline → KV cache FP8)
```bash
# baseline: BF16 (또는 모델 기본 dtype)
vllm serve /models/Qwen3-32B \
  --host 0.0.0.0 --port 8000 \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --tensor-parallel-size 2

# 개선: KV cache를 FP8로 (동시성/긴 context에 특히 영향)
# vLLM은 FP8 등 다양한 quantization/dtype을 지원한다고 문서에 명시 ([docs.vllm.ai](https://docs.vllm.ai/en/latest/index.html?utm_source=openai))
vllm serve /models/Qwen3-32B \
  --host 0.0.0.0 --port 8000 \
  --dtype bfloat16 \
  --kv-cache-dtype fp8 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --tensor-parallel-size 2
```

**예상되는 변화(경험적 판단 기준)**
- VRAM이 빡빡한 상황에서 `--kv-cache-dtype fp8`는 “동시 request 수를 1.5~2배” 수준으로 올릴 여지가 생깁니다(정확한 수치는 모델/컨텍스트/배치에 따라 다름).
- decode가 메모리 병목인 경우 steady-state tokens/s가 개선되거나, 최소한 **OOM 때문에 throughput이 무너지는 상황**을 피합니다.

### 3) 부하 테스트(현실적인 스트리밍 채팅 + 동시성)
```python
# bench_chat.py
import asyncio, time, json
import aiohttp

URL = "http://127.0.0.1:8000/v1/chat/completions"
HEADERS = {"Content-Type": "application/json"}

PROMPT = """You are an assistant helping an on-call engineer.
Given the following incident context, propose a step-by-step mitigation plan and a rollback plan.
Context:
- k8s cluster: prod-us-east
- service: gateway
- symptoms: p99 latency spiked 4x after deploy, error rate 2%
- constraints: cannot restart whole cluster, must keep 99.9% availability
"""

async def one_request(session, req_id: int):
    payload = {
        "model": "default",
        "stream": False,
        "messages": [
            {"role": "system", "content": "Be concise but operationally precise."},
            {"role": "user", "content": PROMPT},
        ],
        "max_tokens": 512,
        "temperature": 0.2,
    }
    t0 = time.time()
    async with session.post(URL, headers=HEADERS, data=json.dumps(payload)) as r:
        out = await r.json()
    t1 = time.time()
    text = out["choices"][0]["message"]["content"]
    toks = out["usage"]["completion_tokens"]
    return (t1 - t0), toks, len(text)

async def main(concurrency=16, rounds=4):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
        for rd in range(rounds):
            t0 = time.time()
            tasks = [one_request(session, i) for i in range(concurrency)]
            results = await asyncio.gather(*tasks)
            t1 = time.time()

            lat = [x[0] for x in results]
            toks = sum(x[1] for x in results)
            wall = t1 - t0
            print(f"[round {rd}] concurrency={concurrency} wall={wall:.2f}s "
                  f"avg_lat={sum(lat)/len(lat):.2f}s p95_lat={sorted(lat)[int(0.95*len(lat))-1]:.2f}s "
                  f"tok/s={toks/wall:.1f}")

if __name__ == "__main__":
    asyncio.run(main())
```

```bash
python bench_chat.py
```

**해석 방법**
- `tok/s`가 오르는지보다 먼저, **concurrency를 올렸을 때 OOM/급격한 p95 붕괴가 줄었는지**를 봅니다. KV cache quant의 1차 목적은 “같은 GPU로 더 많은 동시성을 안정적으로” 처리하는 것입니다.
- prefill이 지배적이면(짧은 답 + 긴 prompt) 개선이 제한적일 수 있으니, 워크로드를 “긴 대화/긴 출력”과 “RAG(긴 prompt)”로 나눠 각각 측정하세요.

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **prefill / decode를 분리해 병목을 진단하라**
- “prefill 빠른데 decode가 느리다”면 KV cache/attention 경로가 핵심이고, KV cache quant(FP8/INT8)가 가장 ROI가 좋습니다.
- “둘 다 느리다”면 weight/activation FP8 경로, tensor parallel, 커널 선택(FlashAttention 계열)까지 봐야 합니다. vLLM은 다양한 분산/quant 옵션을 제공 ([docs.vllm.ai](https://docs.vllm.ai/en/latest/index.html?utm_source=openai))

2) **KV cache quant는 FP8을 1차 디폴트로 두고, INT8/INT4는 ‘조건부’로**
- TensorRT-LLM은 KV cache quant를 성능 튜닝 축으로 공식 가이드에서 다루며 ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/performance/performance-tuning-guide/fp8-quantization.html?utm_source=openai)), KV를 INT8로 압축해 메모리 절감을 얻는 연구도 있지만 ([arxiv.org](https://arxiv.org/abs/2601.04719?utm_source=openai)), 실제 서비스에선 모델 민감도/커널 경로 차이로 품질/성능이 흔들릴 수 있습니다.
- 특히 INT4 KV는 시스템 공동 설계(QServe 류)처럼 “그걸 전제로 커널을 만든 경우”에 이점이 커서 ([proceedings.mlsys.org](https://proceedings.mlsys.org/paper_files/paper/2025/file/fbe2b2f74a2ece8070d8fb073717bda6-Paper-Conference.pdf?utm_source=openai)), 단순 스위치 온으로 같은 결과를 기대하면 안 됩니다.

3) **Blackwell이라면 ‘낮은 precision’ 자체보다 ‘해당 하드웨어에서 최적 커널을 타는지’를 먼저 확인**
- Blackwell은 NVFP4를 강하게 밀고 있고, FP8→NVFP4로의 진화가 공식 블로그/가이드에서 반복됩니다 ([developer.nvidia.com](https://developer.nvidia.com/blog/nvidia-blackwell-sets-stac-ai-record-for-llm-inference-in-finance/?utm_source=openai))  
- 하지만 스택(드라이버/CUDA/런타임/커널) 불일치면 “이론상 빠른” dtype이 실제로는 fallback 경로를 타서 손해를 볼 수 있습니다.

### 흔한 함정/안티패턴
- **(안티패턴) weight INT4만 하고 KV cache는 FP16/BF16 그대로**  
  → 동시성 올리면 KV cache가 터져서 “서빙이 불가능”해지거나, batch를 못 올려 tokens/s가 정체됩니다.
- **(함정) max-model-len을 크게 잡고 gpu-memory-utilization도 높게 잡기**  
  → KV cache가 worst-case로 잡히면서 실제 트래픽 변동에 취약해집니다. 운영에서는 headroom을 남기고, 필요하면 라우팅/큐잉으로 제어하세요.
- **(함정) 벤치마크 프롬프트가 너무 짧아 최적화 효과가 안 보임**  
  → KV cache 최적화는 긴 컨텍스트/동시성에서 빛납니다. “짧은 질답”만 재면 결론을 잘못 내립니다.

### 비용/성능/안정성 트레이드오프
- **FP8 KV cache**: 대체로 “안정적인 1순위” (품질 손실이 상대적으로 작고, 캐시 용량 2× 효과가 큼)
- **INT8 KV cache**: 메모리 절감은 크지만(연구에선 4×까지 보고) ([arxiv.org](https://arxiv.org/abs/2601.04719?utm_source=openai)), 모델별 민감도·커널 경로·스케일 관리에 따라 튜닝 비용이 증가
- **NVFP4/FP4 계열**: Blackwell에서 비용 대비 성능 잠재력이 크지만 ([developer.nvidia.com](https://developer.nvidia.com/blog/nvidia-blackwell-sets-stac-ai-record-for-llm-inference-in-finance/?utm_source=openai)), “정확도/회귀 테스트/스택 정합성”까지 포함한 도입 비용이 큼(프로덕션은 단계적 롤아웃 권장)

---

## 🚀 마무리
정리하면, 2026년 7월 기준 GPU LLM 서빙 최적화의 실전 우선순위는 보통 이렇게 갑니다.

1) **KV cache부터 줄여 동시성을 안정화**: `KV cache FP8`를 첫 카드로  
2) 그 다음 **weight quant(W4A16/W8A16, AWQ/GPTQ)**로 VRAM을 더 확보  
3) Blackwell 환경이면 **NVFP4/FP4 계열**까지 검토하되, “fallback 없는 커널 경로”와 회귀 테스트 체계를 먼저 갖춘다 ([developer.nvidia.com](https://developer.nvidia.com/blog/scaling-nvfp4-inference-for-flux-2-on-nvidia-blackwell-data-center-gpus/?utm_source=openai))

**도입 판단 기준(실무 체크리스트)**
- 현재 장애/병목이 **OOM/동시성 부족**인가? → KV cache quant 우선
- 병목이 **decode tokens/s**인가? → KV cache + attention 커널/런타임 튜닝 우선
- 병목이 **prefill TTFT**인가? → FP8 경로/엔진 빌드(TensorRT-LLM) + 배치/스케줄링(continuous batching) 우선 ([docs.vllm.ai](https://docs.vllm.ai/en/latest/index.html?utm_source=openai))

**다음 학습 추천**
- vLLM의 quantization/parallelism 옵션과 스케줄링(continuous batching, chunked prefill) 문서 정독 ([docs.vllm.ai](https://docs.vllm.ai/en/latest/index.html?utm_source=openai))
- TensorRT-LLM의 FP8/KV cache quant 튜닝 가이드(특히 KV cache quant와 precision 제약) ([nvidia.github.io](https://nvidia.github.io/TensorRT-LLM/performance/performance-tuning-guide/fp8-quantization.html?utm_source=openai))
- KV cache 압축 연구(서비스 워크로드에서 “품질-성능-안정성”을 어떻게 측정할지) ([arxiv.org](https://arxiv.org/abs/2601.04719?utm_source=openai))

원하면, (1) 사용 중인 GPU(예: H100 vs B200), (2) 모델 크기/컨텍스트, (3) 목표 지표(TTFT/p95/tokens/s/$/MTok)를 알려주시면 그 조건에 맞춰 **권장 quant 조합 + vLLM/TensorRT-LLM 선택 + 벤치마크 설계**까지 더 구체적으로 구성해드릴게요.