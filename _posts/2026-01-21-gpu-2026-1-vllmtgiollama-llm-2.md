---
title: "로컬부터 멀티 GPU까지: vLLM·TGI·Ollama LLM 서빙 배포/최적화 실전 가이드"
description: "2026년 1월 시점의 LLM 서빙은 “모델을 띄운다”를 넘어, 동시성(throughput)·TTFT(Time To First Token)·KV cache 메모리 효율·API 호환성(OpenAI compatible)·운영 편의성(관측/롤링업데이트)이 성패를 가릅니다."
date: 2026-01-21 02:25:52 +0900
categories: [AI, MLOps]
tags: [ai, mlops]
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
2026년 1월 시점의 LLM 서빙은 “모델을 띄운다”를 넘어, **동시성(throughput)**·**TTFT(Time To First Token)**·**KV cache 메모리 효율**·**API 호환성(OpenAI compatible)**·**운영 편의성(관측/롤링업데이트)**이 성패를 가릅니다. 특히 사내망/온프렘 환경에서 “클라우드 API 없이 로컬 배포” 요구가 커지면서 vLLM, TGI(Text Generation Inference), Ollama가 자주 비교됩니다.

흥미로운 변화도 있습니다. Hugging Face 문서에 따르면 **TGI는 2025-12-11 기준 maintenance mode**로 전환되었고, Inference Endpoints에서는 대안으로 vLLM/SGLang를 권장합니다.[^1]  
즉, **신규 구축의 기본값은 vLLM**, 다만 “이미 TGI로 굳어진 운영”이나 “특정 기능/스택” 때문에 TGI를 유지하는 팀도 여전히 존재합니다.

---

## 🔧 핵심 개념
### 1) vLLM: PagedAttention + Continuous batching
vLLM이 강한 이유는 **PagedAttention 기반 KV cache 관리**와 **continuous batching**입니다. KV cache를 고정 블록 단위로 관리해 단편화를 줄이고, 실행 중인 요청들을 동적으로 묶어 GPU를 최대한 태웁니다(동시 요청이 늘수록 강해짐).[^2]  
또한 OpenAI-compatible 서버 모드를 공식 지원하며, `--tensor-parallel-size`, `--pipeline-parallel-size`, `--gpu-memory-utilization`, `--enable-prefix-caching` 같은 운영 핵심 옵션이 잘 정리돼 있습니다.[^3]

추가로, vLLM의 **Automatic Prefix Caching**는 “같은 prefix를 가진 요청”에서 프롬프트 prefill을 재사용해 비용을 줄입니다. vLLM v1 설계 문서에서 해시 기반으로 KV 블록을 캐시/재사용하는 구조를 설명합니다.[^4]

### 2) TGI: 성숙한 프로덕션 기능 vs maintenance mode
TGI는 Rust/Python 기반의 고성능 서빙 엔진으로, **streaming**, **continuous batching**, **OpenAI-compatible `/v1/chat/completions`**, 메트릭/트레이싱 등을 강점으로 내세웁니다.[^1]  
다만 지금은 maintenance mode이므로(신규 기능보다는 유지보수 위주) “장기 로드맵” 관점에서는 vLLM로 이동이 자연스러운 선택이 될 수 있습니다.[^1]

### 3) Ollama: 로컬 개발자 경험(Developer UX) 최강, 고동시성은 튜닝 필요
Ollama는 **로컬 실행/모델 관리/간단한 HTTP API**에 최적화된 UX를 제공합니다. API는 기본적으로 `http://localhost:11434/api`로 노출되며 `/api/chat`, `/api/generate`를 바로 호출할 수 있습니다.[^5]  
다만 “기본 설정”은 단일 사용자 성격이 강해 동시성에서 vLLM 대비 불리할 수 있고, 실제 벤치마크에서도 vLLM이 높은 concurrency에서 throughput/TTFT 면에서 우세한 결과가 보고됩니다.[^6]  
또한 환경변수 동작/문서화가 버전에 따라 혼선이 생길 수 있어(예: `OLLAMA_NUM_PARALLEL` 이슈) 운영 시 검증이 필요합니다.[^7]

---

## 💻 실전 코드
아래는 “한 대 서버에서 로컬 배포” 기준으로, **vLLM / TGI / Ollama**를 각각 띄우고 클라이언트에서 호출하는 실행 예제입니다.

```bash
# 1) vLLM (OpenAI-compatible) - 단일 노드/단일 GPU 예시
# 핵심: gpu 메모리 상한, prefix caching, tensor parallel(멀티 GPU면 -tp 조정)
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Meta-Llama-3.1-8B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching \
  --tensor-parallel-size 1
#  -gpu-memory-utilization: KV cache까지 포함한 메모리 플랜에 큰 영향
#  -enable-prefix-caching: 동일 prefix 반복 호출(툴/에이전트/템플릿)에서 비용 절감
#  -tensor-parallel-size: 멀티 GPU면 보통 GPU 개수에 맞춰 2/4/8 등으로 설정[^3]

# 2) TGI - Docker로 빠르게 띄우기
# (maintenance mode이지만, 기존 운영/호환성 때문에 여전히 쓰는 경우가 많음)
model=HuggingFaceH4/zephyr-7b-beta
volume=$PWD/data

docker run --gpus all --shm-size 1g -p 8080:80 -v $volume:/data \
  ghcr.io/huggingface/text-generation-inference:3.3.5 \
  --model-id $model
# 이후 OpenAI-compatible endpoint도 제공(/v1/chat/completions)[^8]

# 3) Ollama - 서버 바인딩을 외부로 열고(필요 시) API 호출
# Linux(systemd) 환경이면 서비스에 환경변수로 OLLAMA_HOST 설정 가능[^9]
export OLLAMA_HOST=0.0.0.0:11434
ollama serve

# Ollama Chat API 호출 (streaming 기본)
curl http://localhost:11434/api/chat -d '{
  "model": "gemma3",
  "messages": [{"role":"user","content":"KV cache가 왜 중요한가?"}]
}'
# /api/chat 스펙은 공식 문서에 정리[^10]
```

---

## ⚡ 실전 팁
1) **“동시성” 목표가 있으면 vLLM을 기본값으로**
- 높은 concurrency에서 vLLM은 dynamic scheduling/continuous batching으로 throughput이 잘 스케일합니다. 반면 Ollama는 기본 설정이 병렬 처리에 보수적이라 튜닝 없이는 금방 plateau가 옵니다.[^6]  
- 사내 서비스(여러 팀/봇/에이전트)가 한 엔드포인트를 공유한다면, vLLM이 운영 안정성/성능 예측이 쉬운 편입니다.

2) **Prefix caching은 “에이전트/템플릿 기반” 워크로드에서 체감이 큼**
- 동일한 system prompt, 동일한 tool 설명, 동일한 정책 문구가 반복되는 서비스는 prefix caching이 “거의 공짜 점수”가 됩니다. vLLM은 해시 기반 KV 블록 재사용 설계를 문서로 공개하고 있습니다.[^4]  
- 단, 캐싱이 켜졌는데도 GPU 메모리 사용률이 기대보다 낮게 보이는 케이스도 보고되므로(버전/모델/양자화 조합) 관측과 검증이 필요합니다.[^11]

3) **TGI는 신규 도입보다 “기존 운영의 안정적 유지” 쪽으로**
- HF 문서 기준으로 TGI는 maintenance mode입니다. 신규 기능/성능 경쟁은 vLLM 쪽이 더 활발할 가능성이 큽니다.[^1]  
- 이미 TGI로 `/v1/chat/completions` 호환을 쓰고 있다면, 마이그레이션 플랜을 미리 준비(새 endpoint 병행 운영 → 트래픽 전환)하는 것이 리스크를 줄입니다.[^1]

4) **Ollama 운영 시: 바인딩/환경변수/버전 차이를 반드시 테스트**
- 공식 FAQ는 `OLLAMA_HOST`로 외부 노출을 안내합니다.[^9]  
- 반면 병렬성 관련 환경변수(`OLLAMA_NUM_PARALLEL` 등)는 버전별 이슈가 보고된 적이 있어, “문서/릴리스노트/실측” 3종 검증이 안전합니다.[^7]

---

## 🚀 마무리
- **vLLM**: 2026년 1월 기준 “프로덕션 LLM 서빙”의 사실상 표준에 가깝습니다(continuous batching, PagedAttention, OpenAI-compatible, prefix caching, 멀티 GPU 옵션).[^2]  
- **TGI**: 기능/성숙도는 높지만 maintenance mode 전환으로 신규 도입은 신중하게.[^1]  
- **Ollama**: 로컬 개발/실험/개인용 서버에 최고. 다중 사용자 고부하 서비스는 튜닝/한계 인지가 필요.[^5]  

다음 학습으로는 (1) vLLM에서 `-tp` 기반 멀티 GPU(단일 노드) 구성, (2) prefix caching 효과를 재현하는 벤치마크(동일 prefix 반복), (3) 관측( Prometheus/OpenTelemetry )을 붙여 TTFT/ITL을 상시 모니터링하는 구성을 추천합니다.

[^1]: <https://huggingface.co/docs/inference-endpoints/engines/tgi>
[^2]: <https://www.marktechpost.com/2025/11/07/comparing-the-top-6-inference-runtimes-for-llm-serving-in-2025/>
[^3]: <https://docs.vllm.ai/en/v0.8.3/serving/openai_compatible_server.html>
[^4]: <https://docs.vllm.ai/en/v0.10.1.1/design/prefix_caching.html>
[^5]: <https://docs.ollama.com/api/introduction>
[^6]: <https://developers.redhat.com/articles/2025/08/08/ollama-vs-vllm-deep-dive-performance-benchmarking>
[^7]: <https://github.com/ollama/ollama/issues/5722>
[^8]: <https://github.com/huggingface/text-generation-inference>
[^9]: <https://docs.ollama.com/faq>
[^10]: <https://docs.ollama.com/api/chat>
[^11]: <https://github.com/vllm-project/vllm/issues/8242>
