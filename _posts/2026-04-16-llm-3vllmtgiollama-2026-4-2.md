---
title: "LLM 서빙 3대장(vLLM·TGI·Ollama) 2026년 4월 배포 가이드: 로컬/서버/쿠버네티스 최적화까지"
date: 2026-04-16 03:35:29 +0900
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
2026년 기준 LLM은 “학습”보다 “서빙(inference)”이 비용과 안정성을 좌우합니다. 같은 모델이라도 **KV cache 메모리 관리**, **continuous batching**, **prefill/decode 스케줄링**에 따라 GPU 한 장에서 처리 가능한 동시 요청 수와 p95 latency가 크게 갈립니다.  
실무에서 자주 부딪히는 요구는 보통 세 가지입니다.

- **고동시성 API 서빙**(사내 서비스/에이전트 백엔드): OpenAI-compatible API가 필요 → vLLM/TGI
- **로컬 배포(개발자/보안 환경)**: 설치 간단, 모델 관리 쉬움 → Ollama
- **운영 최적화**: OOM 회피, TTFT(Time To First Token) 줄이기, 토큰 예산/배치 튜닝

이번 글은 2026년 4월 기준 최신 문서/동향을 바탕으로, vLLM·TGI·Ollama를 **같은 관점(인프라/배포/최적화)**에서 비교하고 바로 배포 가능한 예제를 제공합니다. (참고: Hugging Face 문서에서는 **TGI가 2025-12-11 기준 maintenance mode**임을 명시합니다. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi?utm_source=openai)))

---

## 🔧 핵심 개념
### 1) KV cache가 병목의 80%를 만든다
Causal LLM 생성은 매 토큰마다 attention을 수행하는데, 이미 계산한 과거 토큰의 K/V를 재활용하기 위해 **KV cache**를 GPU 메모리에 쌓습니다. 문제는 “동시 요청 × 컨텍스트 길이 × 생성 길이”가 커질수록 KV cache가 폭증하고, 여기서 **메모리 단편화/할당 비용**이 성능을 망칩니다.

### 2) vLLM: PagedAttention + continuous batching의 조합
vLLM의 핵심은 **PagedAttention**으로 KV cache를 “페이지(block)” 단위로 관리해 단편화를 줄이고, **continuous batching(= iteration-level scheduling)**로 decode 단계에서 GPU를 쉬지 않게 만드는 것입니다. 이 조합이 고동시성에서 throughput을 크게 끌어올리는 이유로 반복적으로 언급됩니다. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  
또한 vLLM은 **OpenAI-Compatible Server**를 공식 지원해, 기존 OpenAI SDK/클라이언트를 거의 그대로 붙일 수 있습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/?utm_source=openai))

> 실무적 결론: “동시 요청이 많고 배치 효과가 큰” 워크로드(사내 챗봇 다수 사용자, 배치 생성, 에이전트 병렬 실행)는 vLLM이 강합니다. (vLLM vs TGI 성능 비교 연구에서도 고동시성에서 vLLM의 우위와, 특정 조건에서 TGI의 tail latency 장점을 함께 언급합니다. ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai)))

### 3) TGI: production 기능은 강하지만(다만 maintenance)
TGI는 Docker 기반 배포가 쉽고, 문서에 **/docs(OpenAPI)**, 다양한 파라미터(토큰/배치 예산), 관측성(메트릭/트레이싱) 등 운영 기능을 강조합니다. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  
다만 2026년 4월 관점에서 중요한 포인트는, Hugging Face 문서 자체가 **TGI maintenance mode**를 명시하고 “동일 모델이면 vLLM 엔진 선택”을 안내한다는 점입니다. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi?utm_source=openai))  
즉 “지금 새로 깐다”면 vLLM 쪽으로 무게가 실리지만, 이미 TGI 운영 중이면 안정적으로 굴리는 전략도 가능합니다.

### 4) Ollama: 로컬/온프렘의 ‘운영 단순성’ 최강
Ollama는 로컬에서 모델 pull/run 경험이 좋아서 개발 환경에 많이 씁니다. 원격 접근을 위해서는 bind 주소를 바꿔야 하는데, 공식 FAQ에 **`OLLAMA_HOST=0.0.0.0:11434`**로 바인딩 변경하는 방법이 명시되어 있습니다. ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))  
즉, “내 PC/사내 서버에 올리고 팀이 같은 네트워크에서 접근” 같은 시나리오에 매우 현실적인 선택입니다.

---

## 💻 실전 코드
아래는 **단일 서버(리눅스) 기준**으로 “vLLM(OpenAI 호환) + TGI + Ollama”를 각각 띄우고, 같은 방식으로 health check 및 호출을 해보는 예제입니다.

### 1) vLLM: OpenAI-Compatible Server (Docker)
```bash
# 1) GPU 서버에서 vLLM OpenAI API 서버 실행
# - /v1/chat/completions 형태로 호출 가능(=OpenAI SDK 호환)
# - 모델은 HF 모델 ID 또는 로컬 경로를 사용
docker run --gpus all --rm -p 8000:8000 \
  -v $HOME/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  --model meta-llama/Meta-Llama-3-8B-Instruct

# 2) curl로 간단 호출(OpenAI Chat Completions)
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Meta-Llama-3-8B-Instruct",
    "messages": [{"role":"user","content":"paged KV cache가 뭐야? 3줄로 설명해줘"}],
    "temperature": 0.2,
    "max_tokens": 128
  }' | jq .
```
- vLLM의 OpenAI-compatible 서빙은 공식 문서로 관리되고 있고, chat template 관련 주의(템플릿 없으면 chat 요청이 실패)도 명시되어 있습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/stable/serving/openai_compatible_server.html?utm_source=openai))

### 2) TGI: text-generation-inference (Docker)
```bash
# TGI는 공식 GitHub에 Docker 실행 예시와 /docs(OpenAPI) 노출을 안내
# 기본 포트는 컨테이너 80, 호스트는 8080으로 매핑 예시
MODEL=meta-llama/Meta-Llama-3-8B-Instruct

docker run --gpus all --rm -p 8080:80 \
  -v $HOME/.cache/huggingface:/data \
  -e HF_TOKEN="$HF_TOKEN" \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id $MODEL

# 생성 호출(비-OpenAI 스타일의 /generate 예시; TGI는 /docs로 스펙 확인 가능)
curl -s http://localhost:8080/generate \
  -H "Content-Type: application/json" \
  -d '{
    "inputs":"Explain continuous batching in 2 sentences.",
    "parameters":{"max_new_tokens":64,"temperature":0.2}
  }' | jq .

# OpenAPI 문서
curl -I http://localhost:8080/docs
```
- TGI는 `/docs`로 OpenAPI 문서 확인이 가능하다고 공식 저장소에서 안내합니다. ([github.com](https://github.com/huggingface/text-generation-inference?utm_source=openai))  
- 다만 현재는 maintenance mode라는 점을 감안해 “신규 도입” 시에는 vLLM 우선 검토가 안전합니다. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi?utm_source=openai))

### 3) Ollama: 원격 접근 + API 호출
```bash
# (A) systemd 환경에서 외부 바인딩: 공식 FAQ에 나온 핵심 한 줄
# /etc/systemd/system/ollama.service.d/override.conf 등에 아래를 추가하는 형태로 사용
# Environment="OLLAMA_HOST=0.0.0.0:11434"

# (B) 실행 후 모델 pull
ollama pull llama3.2

# (C) REST API 호출 예시(/api/generate)
curl -s http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model":"llama3.2",
    "prompt":"KV cache가 왜 필요한지 한 문단으로 설명해줘.",
    "stream": false
  }' | jq .
```
- `OLLAMA_HOST`로 bind 주소를 바꿔 원격 접근을 열 수 있다는 점은 공식 FAQ에 명확히 나옵니다. ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))

---

## ⚡ 실전 팁
### 1) “OOM 회피”는 max_tokens가 아니라 “총 토큰 예산”으로 잡아라
서빙에서 진짜 위험한 건 요청 하나의 max_tokens보다, **동시 요청들이 만들어내는 (prefill + decode) 총 토큰**입니다. TGI 문서도 “입력+출력 합산 토큰 예산” 관점으로 설명합니다. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi?utm_source=openai))  
vLLM도 마찬가지로, 동시성/컨텍스트 길이가 길어질수록 KV cache가 폭발합니다. 운영에서는:
- 사용자별 max context 제한
- 서버 레벨의 max batch token 예산(동시성 제한)
- 긴 요청은 별도 큐/엔드포인트로 분리
를 권장합니다.

### 2) vLLM에서 chat template 미스매치는 “조용히” 장애를 만든다
OpenAI 호환으로 붙였는데 특정 모델만 chat 요청이 에러 나는 경우가 있습니다. vLLM 문서에 **chat template이 없으면 chat 요청이 실패**한다고 명시되어 있으니, 모델 교체 시 가장 먼저 확인해야 합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/stable/serving/openai_compatible_server.html?utm_source=openai))

### 3) TGI는 “유지보수 모드”를 전제로: 마이그레이션 플랜을 같이 세워라
이미 TGI를 돌리고 있고 안정적이라면 당장 바꿀 필요는 없지만, 신규 프로젝트면 vLLM 쪽이 더 미래지향적입니다(문서에서조차 vLLM 엔진 선택을 안내). ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi?utm_source=openai))  
현실적인 접근:
- 단기: TGI 그대로 + 관측/리밋/캐시 튜닝
- 중기: 동일 모델로 vLLM PoC → 트래픽 일부 canary 전환
- 장기: OpenAI-compatible layer 표준화(클라이언트는 고정, 백엔드는 교체 가능)

### 4) 로컬/팀 공유 Ollama는 네트워크 바인딩과 방화벽이 전부다
Ollama는 기본이 localhost 바인딩이라 팀 공유가 막힙니다. `OLLAMA_HOST=0.0.0.0:11434`로 열고, 보안상 내부망/VPN/리버스프록시로 보호하세요. ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))  
(특히 사내에서 “그냥 0.0.0.0로 열기”는 인증 없는 모델 API가 되기 쉽습니다.)

---

## 🚀 마무리
- **vLLM**: PagedAttention + continuous batching으로 **고동시성 throughput**에 강하고, 공식 **OpenAI-compatible server**로 서비스 붙이기 쉽습니다. ([arxiv.org](https://arxiv.org/abs/2309.06180?utm_source=openai))  
- **TGI**: 운영 기능은 성숙했지만, 2026년 4월 기준 문서에서 **maintenance mode**를 명시하므로 신규 도입은 신중히(또는 vLLM 우선) 접근하는 게 합리적입니다. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi?utm_source=openai))  
- **Ollama**: 로컬/온프렘에서 “설치와 모델 운영”이 단순하고, `OLLAMA_HOST`로 팀 접근도 열 수 있습니다. ([docs.ollama.com](https://docs.ollama.com/faq?utm_source=openai))  

다음 학습으로는 (1) KV cache 메모리 모델링(동시성/ctx/토큰 예산 산정), (2) Prometheus 기반 p95/TTFT 관측, (3) vLLM의 스케줄링/캐시 정책 튜닝을 추천합니다.  
원하시면 **단일 GPU(예: L4/4090) 기준으로 vLLM 파라미터를 어떻게 잡으면 OOM 없이 동시성/TTFT 균형이 나오는지**까지, 워크로드(평균 입력 길이/동시 요청/목표 p95) 받아서 구체적인 튜닝 레시피로 이어서 정리해드릴게요.