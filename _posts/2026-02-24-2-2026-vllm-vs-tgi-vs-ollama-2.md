---
title: "2월 2026 기준: vLLM vs TGI vs Ollama, “어떻게” 배포하고 “왜” 그렇게 튜닝하는가"
description: "LLM 서빙을 운영해보면 곧 두 가지 벽에 부딪힙니다. (1) GPU 메모리(KV cache) 한계와 (2) 동시성/지연시간(SLO) 한계입니다. 모델 가중치보다 KV cache가 더 빨리 메모리를 잡아먹고, 요청이 조금만 몰려도 prefill 구간에서 지연이 급증합니다."
date: 2026-02-24 02:48:34 +0900
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
LLM 서빙을 운영해보면 곧 두 가지 벽에 부딪힙니다. **(1) GPU 메모리(KV cache) 한계**와 **(2) 동시성/지연시간(SLO) 한계**입니다. 모델 가중치보다 KV cache가 더 빨리 메모리를 잡아먹고, 요청이 조금만 몰려도 prefill 구간에서 지연이 급증합니다. 그래서 2026년 2월 기준 실무에서는 “서빙 엔진 선택”이 곧 “인프라 비용과 성능의 운명”이 됩니다.

요약하면:
- **vLLM**: 고성능/고처리량(continuous batching, PagedAttention) + OpenAI-compatible API로 “프로덕션 서빙 기본값”에 가까움[^1]  
- **TGI (Text Generation Inference)**: 기능은 강하지만, Hugging Face 문서 기준 **2025-12-11부터 maintenance mode**라 장기 전략은 재검토 필요[^2]  
- **Ollama**: 로컬/엣지/개발자 경험(DX) 최강. 대신 고부하 GPU 서빙보단 “내 PC/사내 워크스테이션 배포”에 최적[^3]  

---

## 🔧 핵심 개념
### 1) Continuous batching: “배치를 고정하지 말고, 흐르는 요청을 계속 묶어라”
전통적인 배치는 “N개 모이면 실행”이라 tail latency가 망가지기 쉽습니다. vLLM/TGI류는 **in-flight request를 스케줄링**해 GPU를 계속 채우는 방식(continuous batching)을 씁니다. 특히 streaming과 궁합이 좋습니다.[^2]  

### 2) KV cache가 진짜 병목이다 (그리고 PagedAttention의 의미)
LLM inference는 토큰을 한 개씩 생성할수록 과거 토큰의 K/V를 재사용(KV cache)합니다. 문제는 컨텍스트가 길어질수록 KV cache가 기하급수로 커져 **동시성(concurrency)**을 갉아먹는다는 점입니다.  
vLLM은 **PagedAttention**으로 KV cache를 “OS의 paging처럼” 쪼개서 관리해 낭비를 줄이고, 결과적으로 처리량을 끌어올립니다(공식 홈페이지에서도 핵심 가치로 강조).[^1]  

### 3) OpenAI-compatible API는 “프록시/표준화 레이어”
2026년 현재 서빙 엔진은 바뀌어도 앱 코드는 유지하려면 **/v1/chat/completions** 같은 OpenAI 스펙 호환이 중요합니다. vLLM은 OpenAI-compatible server를 공식 문서로 제공하고, chat template 이슈(모델 tokenizer의 chat_template 유무)가 실무 함정 포인트로 문서에 명시돼 있습니다.[^4]  

### 4) TGI의 현재 포지션(중요)
Hugging Face 문서에서 **TGI는 2025-12-11부터 maintenance mode**라고 명시합니다. 즉, 지금 당장 굴릴 수는 있어도 “2~3년 운영할 서빙 표준”으로는 vLLM/SGLang 같은 대안을 검토하는 게 자연스럽습니다.[^2]  

---

## 💻 실전 코드
아래는 “한 대 서버에 로컬 배포”를 기준으로, **vLLM / TGI / Ollama**를 각각 띄우고(OpenAI 호환 또는 HTTP 호출) 동일한 클라이언트 코드로 테스트하는 예제입니다.

```bash
# 1) vLLM: OpenAI-compatible server (권장: 프로덕션 지향)
# - 모델이 chat_template을 안 갖고 있으면 --chat-template로 지정해야 함(함정 포인트)
# - 멀티 GPU면 --tensor-parallel-size 조정
pip install -U vllm

vllm serve NousResearch/Meta-Llama-3-8B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --max-model-len 8192 \
  --enable-offline-docs
```

```bash
# (옵션) vLLM 멀티 GPU 스케일링
# 단일 노드에서 모델이 1장에 안 들어가면 tensor parallel이 1순위
vllm serve <MODEL_ID> \
  --tensor-parallel-size 4 \
  --host 0.0.0.0 --port 8000
```

```bash
# 2) TGI: Docker로 빠르게 띄우기 (단, HF 문서상 maintenance mode 유의)
docker run --gpus all --shm-size 1g \
  -p 8080:80 \
  -v ~/.cache/huggingface:/data \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id HuggingFaceTB/SmolLM2-360M-Instruct
```

```bash
# 3) Ollama: 로컬/사내 개발 환경에서 “가장 간단”
# 네트워크에 노출하려면 OLLAMA_HOST를 0.0.0.0:11434로
# (Linux systemd 서비스라면 systemctl edit로 Environment 추가)
# 예: Environment="OLLAMA_HOST=0.0.0.0:11434"
```

```python
# 공통 테스트 클라이언트:
# vLLM은 OpenAI python client로 바로 호출(서버가 /v1 제공)
# TGI도 OpenAI 호환 엔드포인트를 제공할 수 있으나(환경/버전/설정에 따라),
# 여기서는 "vLLM OpenAI 호환"을 기준 예제로 둠.

from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",  # vLLM
    api_key="local-token"                 # 로컬이면 의미만 채움
)

resp = client.chat.completions.create(
    model="NousResearch/Meta-Llama-3-8B-Instruct",
    messages=[
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": "LLM serving에서 KV cache가 병목인 이유를 3줄로 설명해줘."},
    ],
    temperature=0.2,
)

print(resp.choices[0].message.content)
```

---

## ⚡ 실전 팁
1) **chat_template 없는 모델은 “서버가 죽는 게 아니라, 요청이 에러”로 터진다**  
vLLM 문서에서 chat template을 tokenizer가 제공해야 하고, 없으면 `--chat-template`로 지정하라고 못 박습니다. 운영 중 “특정 모델만 400/500” 나는 전형적인 원인입니다.[^4]  

2) **컨텍스트 길이는 ‘품질’이 아니라 ‘동시성’과 트레이드오프**  
TGI 문서도 긴 context를 그대로 열면 동시 요청 수가 급감할 수 있고, max input length를 낮춰 동시성을 확보하라는 식의 가이드를 제공합니다. 운영에서는 “128k 가능”보다 “SLO 만족”이 우선입니다.[^2]  

3) **멀티 GPU 확장은 vLLM에서 tensor parallel → (필요시) pipeline parallel 순서로**  
단일 노드 멀티 GPU는 tensor parallel이 기본 선택이고, 노드를 넘어가면 tensor+pipeline 조합을 권장합니다. 이 기준을 모르면 괜히 분산 구성을 먼저 하다 디버깅 지옥이 열립니다.[^5]  

4) **Ollama를 외부에 열 때는 OLLAMA_HOST + 리버스 프록시를 세트로**
Ollama는 기본 바인딩이 `127.0.0.1:11434`라 원격 접속이 안 됩니다. 문서에 나온 대로 `OLLAMA_HOST=0.0.0.0:11434`로 바꾸고, 필요하면 Nginx로 프록시를 둬서 접근 제어/로그/인증을 붙이는 게 안전합니다.[^3]  

5) **TGI는 “지금 돌릴 수 있음”과 “장기 표준”을 분리해서 판단**
HF 공식 문서에 maintenance mode가 명시된 이상, 신규 구축은 vLLM 쪽으로 기울고(특히 Inference Endpoints도 vLLM 대안을 권장), TGI는 기존 운영분 유지/마이그레이션 관점으로 보는 게 합리적입니다.[^2]  

---

## 🚀 마무리
- **프로덕션 GPU 서빙 인프라**: vLLM이 사실상 1순위(continuous batching + PagedAttention + OpenAI-compatible).[^1]  
- **기존 TGI 운영**: 2025-12-11 이후 maintenance mode이므로, 신규는 신중/마이그레이션 플랜 필수.[^2]  
- **로컬 배포/사내 개발 표준**: Ollama는 설정이 단순하고(특히 OLLAMA_HOST로 노출), 팀 생산성을 올리기 좋습니다.[^3]  

다음 학습 추천:
1) vLLM의 OpenAI-compatible server 옵션(템플릿, extra params, 멀티모달 입력) 문서 정독[^4]  
2) “컨텍스트 길이/동시성/메모리” 트레이드오프를 SLO 기준으로 수치화(부하테스트 스크립트 + Prometheus 지표)  
3) (조직 규모가 크면) Ray Serve LLM 같은 상위 오케스트레이션도 검토[^4]

[^1]: <https://vllm.ai/>
[^2]: <https://huggingface.co/docs/inference-endpoints/engines/tgi>
[^3]: <https://docs.ollama.com/faq>
[^4]: <https://docs.vllm.ai/en/stable/serving/openai_compatible_server.html>
[^5]: <https://docs.vllm.ai/en/v0.14.0/serving/parallelism_scaling/>
