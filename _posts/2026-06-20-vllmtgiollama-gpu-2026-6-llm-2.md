---
title: "vLLM·TGI·Ollama로 “내 GPU를 실제로 일하게” 만드는 2026년 6월 LLM 서빙 배포 가이드"
date: 2026-06-20 04:21:23 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-06]
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
LLM 서빙을 실제 프로젝트에 붙이면 곧바로 부딪히는 문제는 3가지입니다: **(1) 동시성에서의 처리량(throughput) 붕괴**, **(2) KV cache로 인한 VRAM 고갈/파편화**, **(3) 배포/운영 복잡도(업데이트, 모델 관리, 보안 노출)**. 2026년 6월 기준으로 현업에서 자주 비교되는 선택지가 **vLLM / Hugging Face TGI(Text Generation Inference) / Ollama**이고, 각각 “잘 맞는 상황”이 꽤 다릅니다.

- **vLLM을 쓰면 좋은 때**: 동시 요청이 늘수록 GPU가 놀지 않게 만들고 싶을 때(고동시성 API, RAG/Agent 트래픽, 배치 추론). vLLM은 OpenAI-compatible server, prefix caching 옵션 등을 공식 CLI에서 제공하며, 최근 버전 문서에서 prefix caching/serve 옵션이 계속 확장되고 있습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.8.3/serving/openai_compatible_server.html?utm_source=openai))  
- **TGI를 쓰면 좋은 때**: Hugging Face 생태계(모델/토크나이저/배포 파이프라인) 중심이고, Docker/K8s로 “제품화된” 서빙을 빠르게 굴리고 싶을 때. TGI는 gRPC/HTTP 서버 및 OpenAI Chat Completion 호환(Messages API)을 지속적으로 제공 중입니다. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  
- **Ollama를 쓰면 좋은 때**: 팀에 MLOps가 얇고 “로컬 배포/개발자 경험”을 최우선으로 할 때(사내 도구, PoC→내부 서비스). 다만 “로컬 기본”이라도 서버를 외부에 노출해 사고가 나기 쉬운 패턴이 실제로 보고됐습니다. ([en.wikipedia.org](https://en.wikipedia.org/wiki/Ollama?utm_source=openai))  

반대로,
- **vLLM을 쓰면 안 좋은 때**: 트래픽이 작고 단일 사용자/낮은 동시성에서 P99 지연이 최우선이면, 튜닝 없이는 “세팅 대비 체감”이 약할 수 있습니다(스케줄러/배치가 이득을 못 봄). vLLM vs TGI 비교 연구에서도 워크로드에 따라 선택 기준이 갈린다고 요약합니다. ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai))  
- **Ollama를 그대로 프로덕션 인터넷에 올리는 것**: “편해서” 올리기 쉽지만, 노출 사례가 반복적으로 언급됩니다. ([en.wikipedia.org](https://en.wikipedia.org/wiki/Ollama?utm_source=openai))  

---

## 🔧 핵심 개념
### 1) 왜 동시성에서 성능이 무너지는가: KV cache가 진짜 병목
LLM 디코딩은 토큰을 한 개씩 생성하므로, 요청이 많아지면 각 요청의 **KV cache**(각 레이어의 key/value)가 VRAM을 급격히 잡아먹습니다. “요청별로 연속된 큰 버퍼를 잡는 방식”은 파편화/낭비가 심해져, 결국 **배치를 키우지 못하고** throughput이 떨어집니다.

### 2) vLLM의 핵심: PagedAttention + Continuous Batching
vLLM은 KV cache를 OS의 페이징처럼 **고정 크기 페이지로 쪼개 동적으로 할당**해 낭비를 줄이는 PagedAttention을 제안했고, 그 위에 **continuous batching**(배치가 끝날 때까지 기다리지 않고 새 요청을 즉시 합류)으로 GPU idle을 줄입니다. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  
실무적으로 중요한 차이는 “동시 요청이 늘 때” 나타납니다. 여러 벤치마크/비교 글에서 vLLM이 높은 동시성에서 처리량 우위가 두드러진다고 정리합니다. ([runpod.io](https://www.runpod.io/articles/guides/vllm-pagedattention-continuous-batching?utm_source=openai))  

- **Prefix caching**: 동일 프롬프트 prefix(예: 시스템 프롬프트, 공통 지시문, RAG 템플릿 앞부분)를 재사용해 prefill 비용을 줄입니다. vLLM 서버 옵션으로 enable 가능합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.8.3/serving/openai_compatible_server.html?utm_source=openai))  
- (확장 관점) 2026년 6월에는 prefix가 아닌 “세그먼트 단위 공유” 연구도 활발합니다(멀티턴/에이전트에서 반복 구간이 prefix만은 아니기 때문). ([arxiv.org](https://arxiv.org/abs/2606.01751?utm_source=openai))  

### 3) TGI의 핵심: “제품화된” 서빙 + (역할 분리) 런타임/엔드포인트
TGI는 Hugging Face가 주도하는 추론 서버로, Docker 이미지 기반 배포가 표준화되어 있고, gRPC/HTTP 및 OpenAI 호환 응답을 제공하는 방향이 명확합니다. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  
vLLM과 달리 “KV cache 가상화”를 vLLM만큼 강하게 전면에 내세우진 않지만, 운영 관점에서 **배포 재현성/모델 생태계**가 강점입니다.

### 4) Ollama의 핵심: 로컬 모델 관리 + 단일 바이너리 경험
Ollama는 모델을 “pull/run/manage”하는 개발자 UX가 강하고, 로컬 API로 붙이기 쉽습니다. ([en.wikipedia.org](https://en.wikipedia.org/wiki/Ollama?utm_source=openai))  
다만 운영에서 자주 터지는 함정이 “서버 프로세스가 이미 떠 있는데 env만 바꿔도 적용될 거라 착각” 같은 형태입니다(서버 재시작 필요). ([modelpiper.com](https://modelpiper.com/blog/ollama-environment-variables?utm_source=openai))  

---

## 💻 실전 코드
아래는 “사내 서비스”에서 흔한 시나리오(공통 시스템 프롬프트 + RAG 템플릿 + 여러 동시 사용자)를 기준으로, **(1) vLLM 고처리량 서빙**, **(2) TGI Docker 배포**, **(3) Ollama 로컬/엣지 배포**를 단계적으로 붙이는 예제입니다.

### Step 0) 공통: 부하 테스트용 클라이언트(현실형)
- 동시 요청을 걸어 **TTFT / tokens/sec**를 보고, prefix caching 켰을 때 prefill이 줄어드는지 확인합니다.
- OpenAI-compatible endpoint를 공통으로 사용(서버만 바꿔끼우기).

```python
# load_test.py
import asyncio, time, statistics, os
from openai import AsyncOpenAI

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000/v1")
API_KEY  = os.environ.get("API_KEY", "EMPTY")  # vLLM/TGI는 보통 로컬에서 무시 가능(운영은 별도)
MODEL    = os.environ.get("MODEL", "Qwen/Qwen2.5-7B-Instruct")

SYSTEM = """You are a senior backend engineer. Answer concisely with actionable steps."""
RAG_TEMPLATE = """Context:
{context}

Question: {question}
Give a production-grade answer with caveats.
"""

QUESTIONS = [
  "Our Redis cache hit ratio dropped after deploying RAG. What to check first?",
  "Design a rate limiter for /chat/completions with user tiers.",
  "How to size GPU memory for 8k context with KV cache considerations?",
]

async def one_call(client, q):
    ctx = "Company policy: never output secrets. Use structured logs. Prefer idempotent retries."
    prompt = RAG_TEMPLATE.format(context=ctx, question=q)

    t0 = time.perf_counter()
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":SYSTEM},
            {"role":"user","content":prompt},
        ],
        temperature=0.2,
        max_tokens=256,
    )
    dt = time.perf_counter() - t0
    return dt, len(resp.choices[0].message.content)

async def main(concurrency=20, rounds=3):
    client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
    dts = []
    for _ in range(rounds):
        tasks = [one_call(client, QUESTIONS[i % len(QUESTIONS)]) for i in range(concurrency)]
        out = await asyncio.gather(*tasks)
        dts.extend([x[0] for x in out])

    print(f"BASE_URL={BASE_URL}, concurrency={concurrency}, rounds={rounds}")
    print(f"latency avg={statistics.mean(dts):.3f}s p95={statistics.quantiles(dts, n=20)[18]:.3f}s")

if __name__ == "__main__":
    asyncio.run(main())
```

예상 출력(형태):
- `latency avg=... p95=...`
- vLLM에서 동시성↑ 시 p95가 완만히 증가하고, Ollama(단일 로컬 세션 지향)는 큐잉으로 튀는 패턴이 흔히 관찰됩니다(워크로드/모델에 따라 다름). ([techplained.com](https://www.techplained.com/ollama-vs-vllm-vs-llamacpp?utm_source=openai))  

---

### Step 1) vLLM: OpenAI-compatible 서버 + prefix caching + 운영 기본값 잡기
vLLM은 CLI로 OpenAI-compatible server를 띄우는 방식이 가장 빠릅니다. 최신 문서에서 `vllm serve` 및 OpenAI-compatible server 가이드를 제공합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/latest/cli/serve/?utm_source=openai))  

```bash
# 1) 설치(예: CUDA 환경 가정, 환경별로 wheels/컨테이너 전략은 다를 수 있음)
pip install -U vllm

# 2) 서버 실행: 공통 prefix가 많은 RAG/에이전트면 prefix caching을 우선 켜서 검증
# (옵션 이름/가용성은 vLLM 버전에 따라 다를 수 있으니 docs 기준으로 확인)
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --enable-prefix-caching
```

테스트:
```bash
export BASE_URL="http://localhost:8000/v1"
export MODEL="Qwen/Qwen2.5-7B-Instruct"
python load_test.py
```

확장(실무 포인트):
- “GPU가 OOM 나면 CPU offload로 버티기” 같은 옵션이 버전별로 추가되고 있습니다(예: KV cache offloading). 이런 옵션은 **tail latency**를 크게 흔들 수 있어 “살리기” 용도로만 쓰고, 정석은 **max context / max_num_seqs / 배치 정책**부터 맞추는 겁니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.16.0/cli/serve/?utm_source=openai))  

---

### Step 2) TGI: Docker로 재현 가능한 배포(팀 운영 표준화)
TGI는 공식 GitHub에 Docker 실행 예시가 잘 정리되어 있고, 컨테이너 볼륨을 공유해 모델 재다운로드를 피하는 운영 패턴을 권장합니다. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  

```bash
# 모델 캐시 디렉터리 공유(재시작/롤링업데이트 비용 절감)
mkdir -p ./tgi-data

docker run --gpus all --rm \
  -p 8080:80 \
  -v $PWD/tgi-data:/data \
  ghcr.io/huggingface/text-generation-inference:3.3.5 \
  --model-id Qwen/Qwen2.5-7B-Instruct
```

테스트(서버가 OpenAI 호환 엔드포인트를 제공하는 구성인지 확인 후):
```bash
export BASE_URL="http://localhost:8080/v1"
python load_test.py
```

운영에서 TGI를 선택하는 이유는 “성능 1등”이 아니라 **배포/관측/권한/릴리즈 프로세스가 팀 표준에 잘 맞는가**입니다(특히 K8s에 얹을 때).

---

### Step 3) Ollama: 로컬/엣지 배포 + API 연결(단, 노출 주의)
Ollama는 로컬 개발자 경험이 좋아 빠르게 내장형 서비스를 만들기 좋습니다. 다만 env 기반 튜닝은 “서버 시작 시점에 읽는다”는 함정이 있어, 이미 서버가 실행 중이면 shell에서 env를 바꿔도 적용되지 않는다는 점이 반복적으로 언급됩니다. ([modelpiper.com](https://modelpiper.com/blog/ollama-environment-variables?utm_source=openai))  
또한 “외부 인터넷 노출” 사고가 실제로 문제 되었으니, 기본은 **localhost 바인딩 + 내부망 접근 제어**로 가야 합니다. ([en.wikipedia.org](https://en.wikipedia.org/wiki/Ollama?utm_source=openai))  

```bash
# 모델 받기/실행(예시)
ollama pull llama3.1
ollama run llama3.1
```

Ollama를 OpenAI-compatible로 프록시하는 구성은 프로젝트마다 달라(예: 게이트웨이 계층에서 표준화) 여기서는 원칙만:
- 내부 서비스는 **/v1/chat/completions** 같은 표준을 원하므로, Ollama를 직접 붙이기보다 **API Gateway(nginx/Envoy/FastAPI)에서 스키마/인증/로깅을 통일**하는 편이 운영이 쉽습니다.
- “로컬에서만 돌린다”를 지키지 못하면 보안 사고 확률이 급상승합니다. ([en.wikipedia.org](https://en.wikipedia.org/wiki/Ollama?utm_source=openai))  

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **워크로드를 먼저 분해하라: prefill vs decode**
- RAG는 긴 prompt로 **prefill 비용**이 크고, 채팅은 **decode(생성)** 비중이 커집니다. prefix caching은 prefill을, continuous batching은 decode 구간의 GPU idle을 주로 줄입니다. vLLM은 prefix caching 옵션을 제공하니 “공통 시스템 프롬프트/템플릿”이 큰 조직일수록 먼저 켜서 A/B 테스트 가치가 큽니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.8.3/serving/openai_compatible_server.html?utm_source=openai))  

2) **동시성 테스트를 “진짜 트래픽 형태”로**
- 1명 사용 기준 tokens/sec는 별 의미가 없고, 동시 요청·프롬프트 길이·출력 길이 분포가 중요합니다. 높은 동시성에서 vLLM의 강점(PagedAttention/continuous batching)이 드러난다는 비교가 반복됩니다. ([runpod.io](https://www.runpod.io/articles/guides/vllm-pagedattention-continuous-batching?utm_source=openai))  

3) **모델 캐시/가중치 다운로드를 배포 설계의 일부로**
- TGI는 볼륨 공유로 재다운로드를 피하라고 명시합니다. 같은 원칙이 vLLM/기타에도 그대로 적용됩니다(롤링업데이트 때 “모델 다운로드”가 장애가 되기 쉬움). ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  

### 흔한 함정/안티패턴
- **Ollama env 튜닝을 “실행 중인 서버”에 적용된다고 착각**: 서버가 이미 떠 있으면 env를 바꿔도 적용이 안 될 수 있습니다(재시작/서비스 매니저 반영 필요). ([modelpiper.com](https://modelpiper.com/blog/ollama-environment-variables?utm_source=openai))  
- **로컬용 서버를 인터넷에 그대로 노출**: Ollama는 기본 로컬 지향인데도 노출된 서버가 관측된 바 있습니다. “내부망”이라도 인증/ACL 없이는 위험합니다. ([en.wikipedia.org](https://en.wikipedia.org/wiki/Ollama?utm_source=openai))  
- **“처리량만” 보고 선택**: vLLM이 고동시성에서 강한 경우가 많지만, 연구/비교에서는 특정 시나리오에서 TGI가 tail latency 측면에서 유리할 수 있다고도 정리합니다. ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai))  

### 비용/성능/안정성 트레이드오프
- **vLLM**: GPU를 가장 효율적으로 쓰기 좋지만(특히 동시성), 튜닝 파라미터(컨텍스트, 배치, 캐시, 오프로딩)로 tail latency가 요동칠 수 있어 SLO 기반으로 단계적으로 조정해야 합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.16.0/cli/serve/?utm_source=openai))  
- **TGI**: 운영 표준화/재현성(컨테이너 중심) 비용을 지불하고 예측 가능한 배포를 얻는 선택.  
- **Ollama**: 개발자 생산성이 높아 “내부 도구/엣지”에서 ROI가 좋지만, 프로덕션 멀티테넌트·강한 동시성에서는 설계적으로 불리해질 수 있습니다(특히 트래픽이 큐잉되기 쉬움). ([techplained.com](https://www.techplained.com/ollama-vs-vllm-vs-llamacpp?utm_source=openai))  

---

## 🚀 마무리
정리하면, 2026년 6월 시점의 실전 판단 기준은 이렇게 잡는 게 안전합니다.

- **고동시성 API(팀/서비스 여러 개가 동시에 때림), GPU 효율이 곧 비용 절감** → vLLM 우선 검토(PagedAttention/continuous batching + prefix caching을 “내 트래픽”에 대입해 측정). ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  
- **배포 표준화(Docker/K8s), HF 중심 운영, 빠른 제품화** → TGI가 조직 적합성이 높을 가능성 큼. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  
- **로컬/엣지/개발자 경험 최우선** → Ollama. 단, 외부 노출/운영 튜닝(서버 재시작 반영 등) 함정을 통제할 수 있을 때만. ([modelpiper.com](https://modelpiper.com/blog/ollama-environment-variables?utm_source=openai))  

다음 학습 추천은 “벤치마크 숫자”보다 **KV cache/스케줄링이 성능을 왜 바꾸는지**를 이해하는 쪽이 장기적으로 이득입니다. vLLM의 PagedAttention 원 논문을 한 번 읽고, prefix caching을 실제 RAG 템플릿에 적용해 “prefill 비용이 얼마나 줄었는지”부터 계측해 보세요. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))