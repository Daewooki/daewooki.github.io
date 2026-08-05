---
title: "8월 2026 기준: vLLM vs TGI vs Ollama — “로컬/사내 LLM 서빙” 배포 전략과 성능 튜닝의 현실적인 선택 기준"
date: 2026-08-05 03:18:54 +0900
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
사내/로컬에 LLM을 서빙하려고 하면 거의 항상 같은 문제를 만납니다.

- **GPU 메모리(KV cache) 때문에 동시성(concurrency)을 못 올림**
- **prefill(긴 입력)과 decode(토큰 생성) 성격이 달라 tail latency가 튐**
- **OpenAI API 호환(클라이언트/게이트웨이) 유지 vs 운영 복잡도**
- **“한 대에서 돌리는 로컬 배포”와 “쿠버네티스/멀티 GPU”의 요구사항이 다름**

2026년 8월 시점에서 실무적으로 가장 많이 거론되는 조합이 **vLLM / Hugging Face TGI / Ollama**입니다. 각각 “잘하는 문제”가 달라서, 단순 벤치마크보다 **내 트래픽 패턴과 운영 형태**로 고르는 게 맞습니다.

- **vLLM을 쓰면 좋은 경우**: 동시 요청이 많고(연속 batching 이득), GPU 메모리가 빡빡하며(KV cache 효율 중요), OpenAI 호환 API로 빠르게 제품에 붙이고 싶을 때. vLLM의 핵심은 PagedAttention 기반의 메모리 효율 + continuous batching입니다. ([vllm-project.github.io](https://vllm-project.github.io/2023/06/20/vllm.html?utm_source=openai))  
- **TGI를 쓰면 좋은 경우**: Hugging Face 생태계/운영도구에 붙이기 쉽고, 멀티 GPU 샤딩/라우팅 등 “배포 관점”의 제품화가 잘 되어 있는 구성이 필요할 때. TGI는 Rust router + model server 구조를 갖고, OpenAI Messages API 호환도 문서화되어 있습니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))  
- **Ollama를 쓰면 좋은 경우**: “일단 팀 내부에서 로컬/단일 노드로 굴려서” 빠르게 제품/에이전트 프로토타입을 만들고, 운영 복잡도를 최소화하고 싶을 때. API도 단순하고 Docker로 로컬 배포가 쉽습니다. ([docs.ollama.com](https://docs.ollama.com/api/chat?utm_source=openai))  

반대로,
- **초저지연(특히 단일 사용자 인터랙션)만 극단적으로 중요**하고 동시성이 낮다면, vLLM의 “처리량 최적화”가 체감이 약할 수 있고(설정 잘못하면 오히려 불안정), TGI가 더 깔끔할 때가 있습니다(연구/벤치에서도 워크로드별 차이를 언급). ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai))  
- **규모가 커져서 multi-node, autoscaling, 관측/롤링업데이트가 핵심**이면 “엔진”보다 **배포 아키텍처(라우팅, 캐시, 모델 저장소, 토큰 제한, rate limit)**가 더 중요해집니다. 이 단계에서는 vLLM/TGI 자체 성능보다 “운영 가능한 형태”가 승부입니다.

---

## 🔧 핵심 개념
### 1) KV cache와 “왜 서빙이 메모리 싸움인가”
LLM inference는 매 토큰마다 attention을 계산하는데, 과거 토큰의 key/value를 **KV cache**에 저장해 재사용합니다. 동시 요청 수가 늘면 KV cache가 선형으로 커지고, 이게 GPU 메모리를 가장 빨리 잠식합니다. 결국 **“얼마나 KV cache를 효율적으로 쪼개서/재활용해서/조각화 없이 쌓느냐”**가 동시성 한계치를 좌우합니다.

### 2) vLLM: PagedAttention + continuous batching의 구조적 이점
vLLM의 PagedAttention은 OS의 paging처럼 KV cache를 **고정 크기 block/page**로 나눠 비연속 메모리에 저장하고, block table로 추적합니다. 그래서 요청 길이가 제각각일 때도 “큰 덩어리 연속 할당”을 덜 요구하고 **fragmentation을 줄여 더 큰 effective batch**를 만들 수 있습니다. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  

여기에 continuous batching(요청이 끝날 때까지 batch를 고정하지 않고, iteration 단위로 새 요청을 끼워 넣는 스케줄링)을 결합해 **GPU를 놀리지 않고** 처리량을 올립니다. ([vllm-project.github.io](https://vllm-project.github.io/2023/06/20/vllm.html?utm_source=openai))  

추가로 실무에서 중요한 옵션이 **prefix caching**입니다. 시스템 프롬프트/툴 스펙/긴 정책 문구처럼 “항상 붙는 앞부분”이 크면, prefix caching이 prefill 비용을 크게 줄일 수 있습니다(단, 메모리/보안 트레이드오프가 생깁니다). ([mintlify.com](https://www.mintlify.com/vllm-project/vllm/features/prefix-caching?utm_source=openai))  

### 3) TGI: router + model server 분리, 배포 친화적인 샤딩
TGI는 문서에 아키텍처가 비교적 명확히 정리되어 있고, Rust 기반 web server/router가 요청을 받고 모델 서버와 상호작용하는 구조를 설명합니다. 또한 **OpenAI Messages API 호환**을 공식 레퍼런스로 제공합니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))  

즉, “성능 엔진” 관점에서도 중요하지만, 실무에선 TGI가 **멀티 GPU 샤딩/라우팅을 포함한 배포 경험**에서 장점이 나오는 경우가 많습니다(특히 HF 생태계에 붙일 때).

### 4) Ollama: 로컬 배포의 단순함과 운영 경계
Ollama는 “로컬/단일 노드에서 빠르게 모델을 띄우고 API로 쓴다”에 최적화된 제품 경험입니다. Docker 문서가 있고, `/api/chat` 같은 단순 API로 서비스 통합이 쉽습니다. ([ollama.readthedocs.io](https://ollama.readthedocs.io/en/docker/?utm_source=openai))  
다만 대규모 동시성/세밀한 스케줄링/멀티 GPU 병렬화 전략은 vLLM/TGI와 결이 다릅니다. (Ollama는 “로컬 운영 단순성”을 얻는 대신 “서빙 엔진 튜닝 자유도”가 제한되는 편입니다.)

---

## 💻 실전 코드
아래는 **“한 대의 GPU 서버에서 로컬로 vLLM(고성능) + Ollama(팀 로컬 툴링) + Nginx(단일 엔드포인트)로 묶고, 필요하면 TGI로 스왑”**이 가능한 형태로 구성한 예시입니다. toy가 아니라, 실제 서비스 통합에서 흔한 요구(토큰 제한, timeouts, streaming, health check, 모델 캐시 볼륨)를 포함합니다.

### 0) 사전 준비 (공통)
- NVIDIA Docker runtime이 잡혀 있어야 합니다. Compose의 GPU 사용 방식은 Docker 공식 가이드를 따릅니다. ([docs.docker.com](https://docs.docker.com/compose/how-tos/gpu-support/?utm_source=openai))  

---

### 1) vLLM: OpenAI-compatible server를 Docker로 띄우기
vLLM은 공식 Docker 이미지가 제공됩니다(2026년 초 이후 upstream docker hub에 공식 이미지가 제공된다고 문서에 언급). ([docs.vllm.ai](https://docs.vllm.ai/en/latest/deployment/docker/?utm_source=openai))  

#### docker-compose.yml (vLLM)
```yaml
services:
  vllm:
    image: vllm/vllm-openai:latest
    container_name: vllm
    ports:
      - "8000:8000"
    volumes:
      - hf-cache:/root/.cache/huggingface
    environment:
      - HF_HOME=/root/.cache/huggingface
      # 필요 시 Hugging Face 토큰
      # - HUGGINGFACE_HUB_TOKEN=...
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    command:
      [
        "--model", "mistralai/Mistral-7B-Instruct-v0.3",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--gpu-memory-utilization", "0.90",
        "--max-model-len", "8192",
        "--enable-prefix-caching"
      ]
volumes:
  hf-cache:
```

- `--gpu-memory-utilization`과 `--max-model-len`은 **KV cache 용량**과 직결됩니다. vLLM CLI 문서에서 해당 플래그들을 안내합니다. ([mintlify.com](https://www.mintlify.com/vllm-project/vllm/api/cli/serve?utm_source=openai))  
- prefix caching은 “항상 붙는 시스템 프롬프트가 큰 서비스”에서 비용 절감이 크지만, 캐시 메모리를 더 먹고(그리고 vLLM 문서상 일부 플래그는 “trusted users only” 경고가 있습니다) 운영 정책이 필요합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/latest/cli/serve/?utm_source=openai))  

#### 호출 예시 (streaming)
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistralai/Mistral-7B-Instruct-v0.3",
    "stream": true,
    "messages": [
      {"role":"system","content":"You are a senior backend engineer. Answer with numbered steps."},
      {"role":"user","content":"PostgreSQL connection pool에서 p99 latency가 튀는 원인과 점검 순서를 알려줘."}
    ],
    "temperature": 0.2,
    "max_tokens": 400
  }'
```

**예상 출력(요지)**: SSE 형태로 delta 토큰이 연속적으로 내려옵니다(서비스에서는 이걸 그대로 프록시하거나, 게이트웨이에서 버퍼링 정책을 정합니다).

---

### 2) TGI: Docker로 OpenAI Messages API 호환 서버 띄우기
TGI는 공식 문서/레퍼런스에서 OpenAI Chat Completion(Messages API) 호환을 명시합니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/reference/api_reference?utm_source=openai))  

#### docker-compose.yml (TGI)
```yaml
services:
  tgi:
    image: ghcr.io/huggingface/text-generation-inference:3.3.5
    container_name: tgi
    ports:
      - "8080:80"
    volumes:
      - hf-models:/data
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    command:
      [
        "--model-id", "mistralai/Mistral-7B-Instruct-v0.3",
        "--port", "80"
      ]
volumes:
  hf-models:
```

- 멀티 GPU면 `--num-shard` 같은 샤딩 옵션을 쓰는 패턴이 문서/가이드에 반복적으로 등장합니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/conceptual/chunking?utm_source=openai))  

---

### 3) Ollama: 로컬 팀 배포(Compose) + API 사용
Ollama는 Docker 문서가 있고, `/api/chat` 형태로 호출합니다. ([ollama.readthedocs.io](https://ollama.readthedocs.io/en/docker/?utm_source=openai))  

#### docker-compose.yml (Ollama)
```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
volumes:
  ollama:
```

#### 모델 준비 & 호출
```bash
# 모델 다운로드(예: llama 계열)
curl http://localhost:11434/api/pull -d '{"name":"llama3.1:8b"}'

# 채팅 호출
curl http://localhost:11434/api/chat -d '{
  "model":"llama3.1:8b",
  "messages":[
    {"role":"system","content":"You are a site reliability engineer."},
    {"role":"user","content":"vLLM을 쿠버네티스에 올릴 때 가장 흔한 장애 5가지를 우선순위로 정리해줘."}
  ],
  "stream": false
}'
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “동시성 목표 → KV cache 예산”부터 역산하라
대부분의 장애/성능 문제는 모델 자체가 아니라 **KV cache 메모리 부족**에서 시작합니다.
- vLLM에서는 `--gpu-memory-utilization`, `--max-model-len`이 사실상 “동시성/컨텍스트 길이”의 상한을 결정합니다. ([mintlify.com](https://www.mintlify.com/vllm-project/vllm/api/cli/serve?utm_source=openai))  
- 컨텍스트를 무작정 크게 열어두면(예: 128k) 동시성이 급격히 떨어지고, tail latency가 폭발합니다. “긴 컨텍스트 일부 사용자”가 전체 서비스를 망가뜨리기 쉬우니 **요금제/tenant별 max context**를 게이트웨이에서 강제하는 게 현실적입니다.

### Best Practice 2) prefix caching은 “반드시 이득”이 아니라 “워크로드 의존”
prefix caching은 긴 시스템 프롬프트/정적 컨텍스트가 있는 서비스(에이전트 툴 스펙, 규정/정책 프롬프트, RAG의 공통 서문)에선 강력합니다. ([mintlify.com](https://www.mintlify.com/vllm-project/vllm/features/prefix-caching?utm_source=openai))  
하지만,
- 캐시가 커지면 GPU 메모리를 더 먹고,
- 사용자별로 프롬프트가 매번 달라지는 서비스에선 cache hit이 낮아 체감이 약할 수 있습니다.
따라서 “활성 사용자 수, 시스템 프롬프트 크기, hit ratio”를 **메트릭으로 확인 후** 켜는 게 맞습니다.

### Best Practice 3) 엔진 선택은 “성능”보다 “운영 모델”이 더 중요할 때가 많다
- vLLM은 처리량/메모리 효율에 강점(PagedAttention)으로 자주 선택됩니다. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  
- TGI는 아키텍처/배포(라우터, 샤딩, OpenAI Messages API) 문서화가 좋아 팀 단위 운영에서 장점이 큽니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))  
- Ollama는 로컬 배포 단순성이 압도적이라, “내부 도구/개발 환경 표준”으로 두기 좋습니다. ([ollama.readthedocs.io](https://ollama.readthedocs.io/en/docker/?utm_source=openai))  

### 흔한 함정) “GPU는 보이는데 느리다/CPU로 떨어진다”
Ollama 쪽에서 특히 자주 보는 이슈가 **컨테이너 런타임/GPU 초기화 문제**입니다. 공식 트러블슈팅에서도 `docker run --gpus all ... nvidia-smi`로 런타임 자체를 먼저 검증하라고 가이드합니다. ([docs.ollama.com](https://docs.ollama.com/troubleshooting?utm_source=openai))  

### 비용/성능/안정성 트레이드오프
- **Throughput 최적화(vLLM)**: 높은 동시성에서 비용 효율이 좋아지지만, 설정(메모리/컨텍스트/캐시)이 잘못되면 불안정하게 보일 수 있음.
- **배포 안정성(TGI)**: 엔터프라이즈 배포 경험이 좋은 대신, 워크로드에 따라 vLLM 대비 처리량 이점이 덜할 수 있음(연구에서도 워크로드별 우열을 언급). ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai))  
- **로컬 단순성(Ollama)**: “운영 난이도↓” 대신 “세밀한 튜닝/대규모 동시성”은 한계가 빨리 옴.

---

## 🚀 마무리
정리하면, 2026년 8월 기준으로 “내 프로젝트에 적용” 관점의 추천은 이렇게 정리됩니다.

- **프로덕션 트래픽 + 동시성 + 비용 효율**이 핵심이면: **vLLM**(PagedAttention/continuous batching 기반)으로 시작하고, `gpu-memory-utilization / max-model-len / prefix caching`을 워크로드 기반으로 튜닝하세요. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  
- **배포 표준화(샤딩/라우팅/문서화) + HF 생태계**가 핵심이면: **TGI**가 운영 팀에 더 잘 맞을 수 있습니다. OpenAI Messages API 호환도 공식 지원 범주입니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))  
- **개발팀 로컬 표준/내부 도구/PoC**면: **Ollama**를 “가장 작은 운영 단위”로 두고, 성공한 워크로드만 vLLM/TGI로 승격시키는 전략이 비용/속도 모두에서 유리합니다. ([ollama.readthedocs.io](https://ollama.readthedocs.io/en/docker/?utm_source=openai))  

다음 학습/검증 추천:
1) vLLM의 OpenAI-compatible server 옵션과 메모리 관련 플래그(`--max-model-len`, `--gpu-memory-utilization`, prefix caching)를 실제 트래픽 리플레이로 튜닝 ([docs.vllm.ai](https://docs.vllm.ai/en/latest/cli/serve/?utm_source=openai))  
2) TGI 아키텍처 문서(라우터/서버 분리) 읽고, 멀티 GPU 샤딩 전략을 “내 배포 구조”에 대입 ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))  
3) 로컬 표준은 Ollama로 빠르게 만들되, GPU 런타임 검증/트러블슈팅 체크리스트를 팀 위키로 고정 ([docs.ollama.com](https://docs.ollama.com/troubleshooting?utm_source=openai))  

원하시면, **(1) 단일 GPU/단일 노드**인지 **(2) 멀티 GPU/쿠버네티스**인지, 그리고 **동시 요청 수/평균 입력 토큰/평균 출력 토큰**을 알려주시면 그 전제에서 “vLLM vs TGI의 파라미터 세트”를 더 구체적으로(예: max_num_seqs, batching 토큰, context 정책, 게이트웨이 제한) 잡아드릴게요.