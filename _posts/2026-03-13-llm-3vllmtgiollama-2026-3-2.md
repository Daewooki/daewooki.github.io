---
title: "LLM 서빙 3대장(vLLM·TGI·Ollama) 2026년 3월판 배포 가이드: 로컬부터 프로덕션까지 “성능 곡선”으로 결정하기"
date: 2026-03-13 02:43:56 +0900
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
2026년 현재 LLM 서빙은 “모델을 띄우는 것”보다 **동시성(concurrency)에서의 성능 곡선**과 **운영 난이도**가 승패를 가릅니다. 같은 GPU 1장이라도, 요청이 1개일 때 빠른 서버와 50명이 동시에 붙었을 때 SLA를 지키는 서버는 다릅니다. 최근 벤치마크/분석에서 공통적으로 드러나는 결론은 명확합니다:  
- **vLLM**은 continuous batching + PagedAttention 기반으로 고동시성에서 처리량이 크게 튑니다. ([developers.redhat.com](https://developers.redhat.com/articles/2025/08/08/ollama-vs-vllm-deep-dive-performance-benchmarking?utm_source=openai))  
- **TGI(Text Generation Inference)**는 “프로덕션 패키징(라우터/샤딩/통합)”이 강하고, OpenAI 호환(Messages API 포함) 흐름이 안정적입니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))  
- **Ollama**는 로컬 배포/모델 관리 UX가 압도적으로 쉽지만, 기본 구조상 다중 사용자에서 큐잉으로 tail latency가 커지기 쉽습니다(튜닝은 가능). ([developers.redhat.com](https://developers.redhat.com/articles/2025/08/08/ollama-vs-vllm-deep-dive-performance-benchmarking?utm_source=openai))  

이 글은 “셋 다 띄워보기”가 아니라, **인프라 관점(서빙 구조/메모리/KV cache/배포 단위)**에서 왜 그런 차이가 나는지, 그리고 2026년 3월 기준으로 로컬~서버 배포를 어떤 방식으로 가져가면 좋은지 심층적으로 정리합니다.

---

## 🔧 핵심 개념
### 1) throughput vs TTFT/ITL: 무엇을 최적화할 건가
- **TTFT(Time To First Token)**: 첫 토큰이 나오기까지의 시간(대화 UX 핵심)
- **ITL(Inter-Token Latency)**: 토큰 사이 간격(생성 “속도감”)
- **aggregate throughput**: 동시 요청 전체 토큰 처리량(비용/스케일 핵심)

vLLM은 **continuous batching**으로 “요청이 계속 들어오는 환경”에서 배치를 끊지 않고 GPU 파이프라인에 끼워 넣어 aggregate throughput을 크게 끌어올립니다. 이때 배치가 커질수록 개별 요청 ITL이 늘 수 있지만(토큰 간격 증가), 전체 처리량은 좋아집니다. ([developers.redhat.com](https://developers.redhat.com/articles/2025/08/08/ollama-vs-vllm-deep-dive-performance-benchmarking?utm_source=openai))  
Ollama는 단일 사용자/개발 환경에 최적화된 단순한 흐름이 강점이지만, 기본적으로 요청이 쌓이면 큐잉이 생겨 TTFT가 급격히 증가하는 형태가 나오기 쉽습니다. ([developers.redhat.com](https://developers.redhat.com/articles/2025/08/08/ollama-vs-vllm-deep-dive-performance-benchmarking?utm_source=openai))  

### 2) PagedAttention과 KV cache가 “서빙 인프라”가 된 이유
LLM 서빙에서 병목은 종종 연산이 아니라 **메모리(KV cache)**입니다. vLLM은 PagedAttention으로 KV cache를 페이지 단위로 관리해, 다양한 길이의 요청이 섞여도 메모리 파편화/낭비를 줄이고 더 많은 동시 시퀀스를 안정적으로 올립니다(결과적으로 고동시성 처리량이 상승). ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai))  

### 3) TGI 아키텍처: “Router + Model server” 분리의 의미
TGI는 구성 요소가 비교적 명확합니다.
- **launcher**가 모델 서버(샤딩 포함)를 올리고
- **router( Rust 웹서버 )**가 HTTP 요청을 받아 모델 서버로 라우팅합니다.
- OpenAI 호환(Messages API)도 router 레벨에서 제공합니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))  

이 분리는 운영에서 꽤 유리합니다. 예를 들어, 라우터에 인증/레이트리밋/관측을 붙이고, 모델 서버는 “GPU를 최대한 태우는 역할”로 격리하기 쉽습니다.

### 4) 로컬 배포의 현실: “모델 관리 UX”가 생산성이다
로컬/팀 내 실험에서는 **실행 단순성**이 성능보다 중요할 때가 많습니다. Ollama는 단일 바이너리 + 모델 풀/업데이트 경험이 좋아 “돌려보는 비용”이 낮습니다. 반면 동시 사용자 서빙을 목표로 하면 vLLM/TGI 쪽 구조가 맞는 경우가 많습니다. ([sitepoint.com](https://www.sitepoint.com/ollama-vs-vllm-performance-benchmark-2026/?utm_source=openai))  

---

## 💻 실전 코드
아래는 1대 서버(단일 GPU) 기준으로 **vLLM / TGI / Ollama**를 각각 “OpenAI-style로 호출 가능한 형태”까지 올리는 최소 실행 예제입니다. (실전에서는 reverse proxy, auth, metrics는 별도 권장)

```bash
# 0) 공통: NVIDIA Docker 환경(요약)
# - nvidia-container-toolkit 설치되어 있어야 GPU가 컨테이너로 패스스루됩니다.
# - 모델이 gated(Hugging Face)라면 HF_TOKEN 필요합니다(환경변수/secret 사용 권장).

export HF_TOKEN="***"   # 절대 git에 커밋 금지

############################################################
# 1) vLLM: OpenAI-compatible API 서버
############################################################
# vLLM은 continuous batching + PagedAttention 기반으로 고동시성에 강점이 있습니다.
# 예시는 AWQ/FP16 등 모델에 따라 VRAM 요구량이 크게 달라집니다.

docker run --gpus all --rm -it \
  -p 8000:8000 \
  -e HF_TOKEN="$HF_TOKEN" \
  vllm/vllm-openai:latest \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192

# 호출 예시 (OpenAI-style)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"meta-llama/Llama-3.1-8B-Instruct",
    "messages":[{"role":"user","content":"vLLM continuous batching이 뭐야?"}],
    "temperature":0.2
  }'

############################################################
# 2) TGI: Router + Model server, OpenAI Messages API 지원
############################################################
# TGI는 router가 OpenAI 호환(Messages API 포함)을 제공할 수 있습니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))
# (이미지 태그/옵션은 환경에 따라 달라질 수 있으니 공식 docs 기준으로 조정하세요.)

docker run --gpus all --rm -it \
  -p 8080:80 \
  -e HF_TOKEN="$HF_TOKEN" \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id meta-llama/Llama-3.1-8B-Instruct \
  --port 80

# OpenAI-style 호출(엔드포인트가 /v1/... 형태로 제공되는 구성이 많습니다. ([huggingface.co](https://huggingface.co/blog/tgi-messages-api?utm_source=openai)))
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"tgi",
    "messages":[{"role":"user","content":"TGI router 구조를 한 문단으로 설명해줘"}],
    "temperature":0.2
  }'

############################################################
# 3) Ollama: 로컬/팀 개발용으로 가장 빠른 부팅 경험
############################################################
# Ollama는 기본 포트 11434에 API를 제공합니다.
# 동시성은 OLLAMA_NUM_PARALLEL 등으로 조정 가능하지만, 아키텍처 특성상
# 높은 동시 사용자에서는 tail latency가 커질 수 있다는 보고가 많습니다. ([developers.redhat.com](https://developers.redhat.com/articles/2025/08/08/ollama-vs-vllm-deep-dive-performance-benchmarking?utm_source=openai))

docker run --gpus all --rm -it \
  -p 11434:11434 \
  -e OLLAMA_HOST="0.0.0.0:11434" \
  -e OLLAMA_NUM_PARALLEL=4 \
  -v ollama:/root/.ollama \
  ollama/ollama:latest

# 모델 pull 후 실행(컨테이너 내부에서)
# ollama pull llama3.1:8b-instruct
# ollama run llama3.1:8b-instruct

# HTTP 호출 예시(대표적으로 generate API 사용)
curl http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model":"llama3.1:8b-instruct",
    "prompt":"Ollama를 팀 서버에 올릴 때 주의점 3가지",
    "stream":false
  }'
```

---

## ⚡ 실전 팁
1) **“로컬=Ollama, 팀/프로덕션=vLLM 또는 TGI”로 역할 분리**
- 개발자는 Ollama로 빠르게 모델/프롬프트를 반복하고,
- 서비스 트래픽은 vLLM/TGI로 받는 구성이 비용 대비 효율이 좋습니다.  
특히 고동시성에서 vLLM이 처리량/TTFT 측면에서 유리하다는 벤치마크가 반복적으로 관찰됩니다. ([sitepoint.com](https://www.sitepoint.com/ollama-vs-vllm-performance-benchmark-2026/?utm_source=openai))  

2) **vLLM 운영 튜닝의 핵심은 “동시 시퀀스 상한”과 “GPU 메모리 상한”**
- `--gpu-memory-utilization`을 너무 공격적으로 잡으면(예: 0.95+) 다른 프로세스/드라이버 오버헤드로 OOM이 나기 쉽습니다.
- 요청이 길어질수록 KV cache가 커지니 `--max-model-len`을 “필요한 만큼만” 설정하세요. (서빙에서 컨텍스트 길이는 비용 그 자체)

3) **TGI는 “Router 레이어”를 적극 활용**
TGI 아키텍처 문서가 강조하듯 router는 OpenAI Messages API 및 HTTP 수용 지점입니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))  
여기에:
- 인증(mTLS, JWT), rate limiting
- request logging/PII 마스킹
- 모델 서버와 독립적인 롤링 업데이트  
를 붙이면 운영이 정리됩니다.

4) **Ollama를 외부에 열 때는 보안/네트워크를 먼저**
Ollama는 기본적으로 API 서버입니다. 포트(11434)를 내부망에만 두거나 reverse proxy로 감싸고, 방화벽/ACL/인증을 분리하세요. 로컬 UX가 좋다고 “그대로 인터넷 오픈”하면 사고 납니다. (특히 사내 데이터 프롬프트 유출 위험)

5) **“단일 사용자 tok/s”로 비교하지 말고, 반드시 동시성 곡선으로 비교**
최근 비교 글들은 1-user 성능 차이는 크지 않아도, 동시 10~50에서 vLLM의 aggregate throughput이 크게 벌어지는 패턴을 반복 보고합니다. ([sitepoint.com](https://www.sitepoint.com/ollama-vs-vllm-performance-benchmark-2026/?utm_source=openai))  
즉, 선택 기준은 “내 서비스 동시 사용자”입니다.

---

## 🚀 마무리
2026년 3월 기준으로 실무적인 결론은 이렇습니다.

- **Ollama**: 로컬 배포/프로토타이핑 최강. 팀 온보딩 비용을 최소화.  
- **vLLM**: 고동시성·비용 효율·처리량이 핵심인 서빙 인프라에 강력(continuous batching + PagedAttention). ([sitepoint.com](https://www.sitepoint.com/ollama-vs-vllm-performance-benchmark-2026/?utm_source=openai))  
- **TGI**: router/model server 분리와 Hugging Face 생태계, OpenAI 호환(Messages API) 흐름이 안정적인 “프로덕션 패키지”. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/main/en/architecture?utm_source=openai))  

다음 학습으로는 (1) vLLM의 scheduling/continuous batching이 tail latency를 어떻게 바꾸는지, (2) TGI router에 auth/observability를 붙이는 패턴, (3) 동일 모델을 FP16 vs AWQ/4bit로 내렸을 때 KV cache/throughput이 어떻게 변하는지 벤치로 검증해보면, “감”이 아니라 “수치”로 설계를 할 수 있습니다.