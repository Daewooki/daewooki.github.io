---
title: "LLM 서빙 3대장(vLLM·TGI·Ollama) 2026년 3월 배포 레시피: 로컬 인프라 최적화까지 한 번에"
date: 2026-03-30 03:27:14 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-03]
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
2026년 현재 LLM을 “써보는” 단계는 끝났고, **어떻게 안정적으로 서빙할지**가 실력 차이를 만듭니다. 특히 사내/온프렘/개인 워크스테이션 환경에서는 (1) GPU VRAM이 넉넉하지 않고, (2) 동시 요청이 조금만 늘어도 latency가 흔들리며, (3) 모델/버전이 자주 바뀌기 때문에 **서빙 엔진 선택과 배포 방식**이 곧 운영 난이도를 결정합니다.

이 글은 2026년 3월 기준으로 많이 쓰는 3가지 옵션을 한 축으로 묶어 비교/배포합니다.

- **vLLM**: PagedAttention 기반의 KV cache 메모리 효율로 “고동시성/고처리량”에 강함. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  
- **TGI (Text Generation Inference)**: Hugging Face 생태계/운영 기능이 강하고, continuous batching 등 실서비스 기능이 탄탄함. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  
- **Ollama**: 로컬 배포/개발자 경험이 매우 좋고, 환경변수로 동시성/상주 정책을 쉽게 조절 가능. ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))  

---

## 🔧 핵심 개념
### 1) LLM 서빙 성능의 본질: **KV cache + batching**
LLM 추론에서 GPU 메모리를 가장 크게 잡아먹는 축은 대개 **weights**보다 **KV cache**(특히 긴 context, 동시 요청 증가)입니다. 요청이 많아지면 “prefill(프롬프트 처리)”과 “decode(토큰 생성)”가 섞이며, 이를 잘 묶어 처리하는 **continuous batching**이 처리량을 좌우합니다. TGI는 continuous batching을 핵심 기능으로 내세웁니다. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  

### 2) vLLM의 PagedAttention: “KV cache를 페이지 단위로” 다루기
전통적인 방식은 KV cache를 연속 메모리로 크게 잡으면서 **fragmentation**과 낭비가 커지는데, PagedAttention은 이를 OS의 paging처럼 다뤄 **낭비를 줄이고 더 큰 batch/동시성을** 허용합니다. 이게 vLLM이 고동시성에서 강한 이유입니다. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  

### 3) TGI의 강점: 운영 친화성과 구성 파라미터의 “자동 최대화”
TGI는 max input/total tokens, batch 관련 파라미터를 하드웨어에 맞춰 자동으로 크게 잡는 전략을 제공하고(또는 env로 명시), `/docs`로 OpenAPI 문서까지 바로 노출됩니다. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/en/engines/tgi?utm_source=openai))  

### 4) Ollama의 포지션: 로컬 “멀티 모델/멀티 유저”를 환경변수로 제어
Ollama는 개발/로컬 배포에서 압도적으로 단순합니다. 대신 “대규모 GPU 효율”보다는 **단일/소수 GPU에서 여러 모델을 로드/스케줄링**하는 운영이 핵심이고, 이때 자주 만지는 것이:
- `OLLAMA_HOST`(바인딩 주소)
- `OLLAMA_KEEP_ALIVE`(모델 상주 시간)
- `OLLAMA_MAX_LOADED_MODELS`(동시 로드 모델 수)
- `OLLAMA_NUM_PARALLEL`(모델당 병렬 요청 수) ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))  

---

## 💻 실전 코드
아래 예제는 “로컬/온프렘에서 바로 실행”을 목표로 했습니다. (NVIDIA GPU 기준)

### 1) vLLM: OpenAI-Compatible Server로 띄우기
vLLM은 OpenAI 호환 API 서버 모드가 있어, 클라이언트 코드를 거의 그대로 재사용할 수 있습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.8.0/serving/openai_compatible_server.html?utm_source=openai))  

```bash
# vLLM 설치 (예: 파이썬 venv 안에서)
pip install -U vllm

# OpenAI-compatible server 실행
# - model: Hugging Face 모델 ID 또는 로컬 경로
# - tensor-parallel-size: 멀티 GPU면 >1 (단일 GPU면 1)
vllm serve "meta-llama/Meta-Llama-3.1-8B-Instruct" \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 1
```

테스트(스트리밍은 클라이언트에서 구현 가능):
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "messages": [{"role":"user","content":"vLLM의 PagedAttention을 한 문단으로 설명해줘"}],
    "temperature": 0.2,
    "max_tokens": 200
  }'
```

### 2) TGI: Docker로 가장 표준적인 배포
TGI는 공식 repo 기준으로 `docker run --gpus all ... ghcr.io/...` 패턴이 가장 흔합니다. 또한 `/docs`로 API 문서가 바로 뜹니다. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  

```bash
# (사전) NVIDIA Container Toolkit 설치 필요
# 모델 캐시 볼륨을 공유해 재시작 시 다운로드를 피한다.
export HF_TOKEN="YOUR_HF_TOKEN"
export MODEL="meta-llama/Meta-Llama-3.1-8B-Instruct"
export VOL="$PWD/tgi-data"

docker run --gpus all --shm-size 1g \
  -e HF_TOKEN=$HF_TOKEN \
  -p 8080:80 \
  -v $VOL:/data \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id $MODEL
```

요청 예시(기본 completions 스타일):
```bash
curl http://localhost:8080/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "inputs":"continuous batching이 왜 throughput에 유리해?",
    "parameters":{"max_new_tokens":128, "temperature":0.2}
  }'
```

### 3) Ollama: Docker Compose로 “로컬 멀티유저/멀티모델” 세팅
Ollama는 `OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_KEEP_ALIVE` 같은 knobs로 “내 GPU에서 어디까지 동시성을 줄지”를 빠르게 튜닝합니다. ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))  

```yaml
# compose.yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama:/root/.ollama
    environment:
      # 외부 접근 필요 시 0.0.0.0 바인딩
      - OLLAMA_HOST=0.0.0.0:11434
      # 모델 상주 시간(예: 10분 동안 미사용이면 언로드)
      - OLLAMA_KEEP_ALIVE=10m
      # 동시에 메모리에 올려둘 모델 수
      - OLLAMA_MAX_LOADED_MODELS=2
      # 모델당 동시 처리 요청 수(늘리면 VRAM/latency 압박 증가)
      - OLLAMA_NUM_PARALLEL=2
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
volumes:
  ollama:
```

실행/모델 pull/테스트:
```bash
docker compose up -d
curl -s http://localhost:11434/api/tags | jq .

# 예: 모델 다운로드
docker exec -it ollama ollama pull llama3.1:8b

# 간단 호출
curl http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.1:8b","prompt":"로컬 LLM 서빙에서 KV cache가 중요한 이유는?","stream":false}'
```

---

## ⚡ 실전 팁
1) **서빙 엔진 선택 기준을 ‘추상’이 아니라 ‘워크로드’로 잡기**
- 동시 요청이 많고 batch가 잘 모이는 서비스(예: 챗봇/에이전트 다중 사용자) → vLLM의 KV cache 효율이 큰 이득이 되는 경우가 많습니다(PagedAttention). ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  
- “운영 기능/문서화/허깅페이스 연동/배포 표준화”가 중요 → TGI가 편합니다(`/docs`, continuous batching, 다양한 런처 옵션). ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  
- 개발자 PC/작은 서버에서 여러 모델을 빠르게 바꿔가며 로컬 제공 → Ollama가 압도적으로 생산적입니다(환경변수로 동시성/상주 제어). ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))  

2) **토큰 한도(max input/total tokens)는 “성능 슬라이더”다 (특히 TGI)**
TGI는 하드웨어 기반 자동 최대 설정을 하기도 하지만, 컨텍스트를 크게 열어두면 **요청당 메모리 사용량이 커져 batching 효율이 떨어질 수** 있습니다. “우리 서비스의 평균 prompt 길이/응답 길이”를 측정한 뒤 상한을 재설정하세요. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/en/engines/tgi?utm_source=openai))  

3) **Ollama 동시성 튜닝의 함정: NUM_PARALLEL을 올리면 무조건 좋은가?**
`OLLAMA_NUM_PARALLEL`을 올리면 처리량이 늘 수 있지만, VRAM 여유가 적으면 오히려 **swap/언로드/로드가 잦아져 tail latency**가 튈 수 있습니다. 보통은:
- `OLLAMA_MAX_LOADED_MODELS`는 1~2로 보수적으로
- `OLLAMA_NUM_PARALLEL`을 2부터 올리며 관찰
- `OLLAMA_KEEP_ALIVE`로 “재로딩 비용”과 “VRAM 상주” 사이 균형  
을 추천합니다. ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))  

4) **벤치마크는 TTFT vs TPOT vs Throughput을 분리해서 보라**
서빙은 “첫 토큰까지 시간(TTFT)”과 “토큰 생성 속도(TPOT)”, 그리고 “동시성 하 throughput”이 서로 다른 병목을 가집니다. 단일 수치로 비교하면 판단을 그르치기 쉽습니다. (벤치 템플릿/지표 분리의 중요성은 BentoML 가이드도 강조합니다.) ([bentoml.com](https://bentoml.com/llm/inference-optimization/llm-performance-benchmarks?utm_source=openai))  

---

## 🚀 마무리
- **vLLM**은 PagedAttention으로 KV cache 메모리 효율을 끌어올려 **고동시성에서 강한 선택지**가 되기 쉽습니다. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  
- **TGI**는 continuous batching, 풍부한 런처 옵션, `/docs` 기반 문서화로 **운영 표준화**에 강합니다. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  
- **Ollama**는 로컬 배포에서 환경변수 기반 튜닝(동시 처리/동시 로드/상주 정책)으로 **개발·팀 내부 배포의 속도**를 극대화합니다. ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))  

다음 학습으로는 (1) 실제 트래픽 로그 기반으로 prompt 길이/응답 길이 분포를 만들고, (2) TTFT/TPOT/throughput을 분리 측정하며, (3) KV cache가 VRAM을 얼마나 먹는지 관측(특히 긴 context)하는 과정을 추천합니다. 그러면 “엔진 선택”이 취향이 아니라 데이터 기반 결정이 됩니다. ([bentoml.com](https://bentoml.com/llm/inference-optimization/llm-performance-benchmarks?utm_source=openai))