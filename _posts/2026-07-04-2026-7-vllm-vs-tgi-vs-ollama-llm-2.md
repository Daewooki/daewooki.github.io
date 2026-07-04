---
title: "2026년 7월 기준 vLLM vs TGI vs Ollama: “내 서비스”에 맞는 LLM 서빙 인프라/로컬 배포/최적화 결정 가이드"
date: 2026-07-04 03:50:35 +0900
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
LLM 서빙에서 진짜 골치 아픈 문제는 “모델을 띄우는 것”이 아니라 **(1) GPU 메모리(KV cache) 한계, (2) 동시성/지연시간(TTFT) 균형, (3) 운영 난이도(배포·관측·롤백)** 입니다. 2026년 7월 기준으로 현업에서 가장 자주 거론되는 선택지가 vLLM, Hugging Face TGI(Text Generation Inference), Ollama인데, 셋 다 “OpenAI-compatible API”를 표방하면서도 **목표 사용처가 다릅니다**. vLLM은 고성능 온라인 서빙(continuous batching + PagedAttention), TGI는 Hugging Face 생태계 중심의 프로덕션 서빙(멀티백엔드/배포 레시피 풍부), Ollama는 로컬/단일 노드 운영 경험 최적화(모델 풀/Modelfile/간단한 API) 쪽에 강점이 있습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/?utm_source=openai))

언제 쓰면 좋나(추천):
- **vLLM**: 트래픽이 있고(동시 요청), **throughput 최적화**가 중요하며, 프록시 뒤에서 OpenAI API로 앱을 붙이고 싶을 때(특히 chat/completions). ([docs.vllm.ai](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/?utm_source=openai))  
- **TGI**: Hugging Face 모델을 “그대로” 서빙하고, Docker/K8s 레시피 기반으로 **운영 표준화**하고 싶을 때(모델 게이팅 토큰, 배포 이미지, 백엔드 다양성). ([huggingface.co](https://huggingface.co/docs/google-cloud/en/examples/gke-tgi-deployment?utm_source=openai))  
- **Ollama**: 팀/개인이 **로컬/온프렘 단일 서버**에 빠르게 올리고, 내부 도구(에이전트/챗 UI)에서 가볍게 쓰고 싶을 때. ([markaicode.com](https://markaicode.com/integrate/deploy-ollama-production-server-guide/?utm_source=openai))  

언제 쓰면 안 되나(비추천/주의):
- vLLM: “그냥 간단히 한 대에 띄우고 끝” 같은 경우엔 초기 튜닝 포인트가 오히려 부담일 수 있습니다(스케줄링/메모리/병렬 설정). 반대로 멀티 GPU 병렬에서 환경에 따라 hang 이슈 같은 운영 리스크 사례도 있습니다. ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1rvtg8g/vllm_hangs_on_multigpu_parallelism/?utm_source=openai))  
- TGI: 이미지 태그를 `latest`로 두면 깨질 확률이 높아 **버전 pinning이 사실상 필수**입니다. 게이티드 모델은 HF_TOKEN 미설정 시 “배포는 된 것 같은데 로딩 실패” 형태로 터지기 쉽습니다. ([theneuralbase.com](https://theneuralbase.com/tgi/learn/beginner/text-generation-inference-hf/?utm_source=openai))  
- Ollama: 기본은 단일 노드/단순 운영에 최적화라, **대규모 멀티 GPU/멀티 노드 서빙**을 주력으로 할 때는 vLLM/TGI 계열이 더 자연스럽습니다(또는 Ollama를 내부 개발/프로토타이핑 레인으로 분리).

---

## 🔧 핵심 개념
### 1) 공통: LLM 서빙의 병목은 “KV cache”와 “스케줄링”
Transformer 디코딩은 토큰이 늘어날수록 KV cache가 커집니다. 결국 **동시 요청 수 × 컨텍스트 길이 × 레이어 수**가 GPU 메모리를 집어삼킵니다. 그래서 서빙 엔진의 본질은
- KV cache를 얼마나 효율적으로 관리하는지(메모리 단편화/낭비 최소화)
- 프리필(prefill)과 디코드(decode)를 어떻게 섞어 스케줄링하는지
- 스트리밍/배치(continuous batching)를 어떻게 해서 GPU를 놀리지 않는지
로 갈립니다.

### 2) vLLM: PagedAttention + continuous batching으로 “메모리/동시성”을 밀어붙임
vLLM의 유명한 포인트는 PagedAttention: KV cache를 고정 큰 텐서로 “미리 다 잡아두는” 대신, **페이지/블록 단위로 쪼개 관리**해 메모리 낭비와 단편화 문제를 줄입니다. 이 구조 덕분에 동시 요청이 많고 시퀀스 길이가 들쭉날쭉한 워크로드에서 효율이 잘 나옵니다. ([www2.eecs.berkeley.edu](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2025/Archive/EECS-2025-192.pdf?utm_source=openai))  
그리고 OpenAI-compatible server를 공식 문서로 제공하면서, 앱 레이어에서 “OpenAI SDK 그대로” 붙이는 패턴이 현실적인 기본값이 됐습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/?utm_source=openai))  
또한 2026년 흐름에서 vLLM은 attention backend 최적화(예: Triton 기반 unified attention 등) 같은 커널 레벨 튜닝도 빠르게 진화 중입니다. ([vllm.ai](https://vllm.ai/blog/2026-03-04-vllm-triton-backend-deep-dive?utm_source=openai))

**다른 접근과 차이점**: llama.cpp 계열이 “단일 프로세스/경량/CPU까지”를 넓게 포괄한다면, vLLM은 “GPU 온라인 서빙 엔진”에 집중해 **서빙 스케줄러+메모리 관리+분산 병렬**을 제품처럼 다듬는 방향입니다(특히 TP/PP). ([github.com](https://github.com/vllm-project/vllm/blob/main/docs/serving/parallelism_scaling.md?utm_source=openai))

### 3) TGI: “프로덕션 서빙 키트” + 멀티 백엔드/배포 레시피
TGI는 Hugging Face가 “서빙 제품” 관점으로 만든 툴킷입니다. Docker로 로컬 실행부터, GKE 같은 관리형 K8s 배포 예제까지 문서가 두껍고, 다양한 가속기 백엔드(예: Gaudi 이미지 태그 별도 제공)처럼 운영 옵션이 넓습니다. ([huggingface.co](https://huggingface.co/docs/google-cloud/en/examples/gke-tgi-deployment?utm_source=openai))  
또 하나 중요한 포인트: **OpenAI Messages API(/v1/chat/completions)** 같은 호환 레이어가 문서화되어 있어, 애플리케이션 교체 비용을 줄일 수 있습니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/en/reference/api_reference?utm_source=openai))

**다른 접근과 차이점**: vLLM이 “엔진 최적화 중심”이라면, TGI는 “배포/운영 패키지화”가 강합니다. 대신 운영 안정성은 **버전 pinning** 같은 기본 수칙을 지키는지에 크게 좌우됩니다. ([theneuralbase.com](https://theneuralbase.com/tgi/learn/beginner/text-generation-inference-hf/?utm_source=openai))

### 4) Ollama: 로컬/단일 서버에 최적화된 “개발자 UX”
Ollama의 장점은 팀이 **GPU 한 대**로 내부 도구를 만들 때 “설치/실행/모델 풀” 경험이 압도적으로 단순하다는 점입니다. 프로덕션 배포도 systemd + Nginx reverse proxy로 굴리는 실전 가이드가 많이 공유되고, 동시성은 `OLLAMA_NUM_PARALLEL` 같은 변수로 제어하는 식의 운영 패턴이 알려져 있습니다. ([markaicode.com](https://markaicode.com/integrate/deploy-ollama-production-server-guide/?utm_source=openai))  
또한 OpenAI-compatible `/v1` 서브셋을 제공하는 Docker 이미지(보안/키 관리 포함) 같은 “운영 보조재”도 생태계에 존재합니다. ([hub.docker.com](https://hub.docker.com/r/hwdsl2/ollama-server?utm_source=openai))

---

## 💻 실전 코드
아래는 “내 서비스에 바로 붙이는” 기준으로, **단일 GPU 서버(예: Ubuntu 24.04 + NVIDIA)**에 vLLM/TGI/Ollama를 각각 띄우고, 동일한 Python 클라이언트로 호출하는 실전 구성을 보여줍니다. 포인트는:
- **API 표면을 OpenAI로 통일**해 앱 변경을 최소화
- reverse proxy/관측은 다음 단계로 넘기되, 최소한의 운영 안전장치(버전 pinning, 환경변수, 볼륨) 포함

### 1단계) vLLM: OpenAI-compatible 서버(로컬/단일 노드)
```bash
# (권장) 컨테이너로 고정 실행: 이미지 태그는 팀 표준에 맞춰 pinning
# 예시는 vLLM 공식 문서의 OpenAI-compatible 서버 흐름에 맞춤 ([docs.vllm.ai](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/?utm_source=openai))

export MODEL="meta-llama/Meta-Llama-3.1-8B-Instruct"
export HF_TOKEN="hf_xxx"   # 게이티드 모델이면 필요

docker run --gpus all --rm -it \
  -e HF_TOKEN=$HF_TOKEN \
  -p 8000:8000 \
  -v vllm-cache:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  vllm serve $MODEL \
    --host 0.0.0.0 --port 8000 \
    --gpu-memory-utilization 0.90
```

예상 동작:
- `http://localhost:8000/v1/chat/completions`로 요청 가능
- 동시 요청이 늘수록 continuous batching 효과로 throughput이 좋아지지만, **TTFT가 늘 수도** 있으니 워크로드에 따라 튜닝(다음 섹션에서 팁)

### 2단계) TGI: Docker로 로컬 서빙(+버전 pinning)
```bash
# TGI는 "latest" 대신 버전을 고정하는 게 운영 상 안전하다는 가이드가 널리 공유됨 ([theneuralbase.com](https://theneuralbase.com/tgi/learn/beginner/text-generation-inference-hf/?utm_source=openai))
# 또한 게이티드 모델은 HF_TOKEN 미설정 시 런타임 로딩에서 터질 수 있음 ([theneuralbase.com](https://theneuralbase.com/tgi/learn/beginner/text-generation-inference-hf/?utm_source=openai))

export MODEL="meta-llama/Meta-Llama-3.1-8B-Instruct"
export HF_TOKEN="hf_xxx"

docker run --gpus all --rm -it \
  -e HF_TOKEN=$HF_TOKEN \
  -p 3000:3000 \
  -v tgi-data:/data \
  ghcr.io/huggingface/text-generation-inference:2.0.5 \
  --model-id $MODEL \
  --port 3000
```

예상 동작:
- 문서에 따라 `/v1/chat/completions` 호출이 가능(“OpenAI Messages API”). ([huggingface.co](https://huggingface.co/docs/text-generation-inference/en/reference/api_reference?utm_source=openai))  
- 운영 시에는 K8s 배포 예제도 공식 문서로 제공(예: GKE). ([huggingface.co](https://huggingface.co/docs/google-cloud/en/examples/gke-tgi-deployment?utm_source=openai))

### 3단계) Ollama: 단일 서버 배포(Compose 예시) + 동시성 제어
```bash
# 운영에서 자주 쓰는 패턴: Docker/Compose + reverse proxy(TLS) + healthcheck
# 여기서는 Ollama 자체만 띄우고, 프록시는 생략(실전에서는 Nginx 권장) ([sitepoint.com](https://www.sitepoint.com/ollama-local-llm-production-deployment-docker/?utm_source=openai))

cat > compose.ollama.yml <<'YAML'
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama:/root/.ollama
    environment:
      # 동시 요청(모델당) 제어 포인트로 자주 언급 ([modelpiper.com](https://modelpiper.com/blog/ollama-environment-variables?utm_source=openai))
      - OLLAMA_NUM_PARALLEL=1
volumes:
  ollama: {}
YAML

docker compose -f compose.ollama.yml up -d

# 모델 pull(미리 안 하면, 외부 UI/클라이언트에서 "모델이 없다"로 보일 수 있음) ([reddit.com](https://www.reddit.com/r/ollama/comments/1s6hb0w/open_webui_not_connecting_to_ollama_on/?utm_source=openai))
docker exec -it ollama ollama pull llama3.2
```

### 4단계) “앱 코드는 하나로” 통일: OpenAI SDK로 vLLM/TGI에 붙이기
vLLM은 공식적으로 “OpenAI Python client로 호출” 예시를 제공합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.21.0/serving/openai_compatible_server/?utm_source=openai))  
아래 코드는 **프로덕션에서 흔한 패턴(환경별 base_url만 교체)** 입니다.

```python
# python 3.11+
# pip install openai

import os
from openai import OpenAI

BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
API_KEY = os.environ.get("LLM_API_KEY", "dummy")  # 로컬이면 의미 없을 수 있으나 인터페이스 통일용

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

resp = client.chat.completions.create(
    model=os.environ.get("LLM_MODEL", "any"),  # vLLM/TGI는 서버 런치 시 로드된 모델을 사용
    messages=[
        {"role": "system", "content": "You are a senior backend engineer."},
        {"role": "user", "content": "우리 서비스에서 LLM 서빙을 vLLM로 갈 때 체크리스트 5개만."},
    ],
    temperature=0.2,
    stream=False,
)

print(resp.choices[0].message.content)
```

실행 예:
```bash
# vLLM
LLM_BASE_URL="http://localhost:8000/v1" python client.py

# TGI
LLM_BASE_URL="http://localhost:3000/v1" python client.py
```

Ollama는 OpenAI 호환을 “부분 제공”하거나 별도 이미지로 우회하는 경우가 많아서(서브셋/프록시), 팀 표준을 **(1) Ollama native API**, **(2) OpenAI 호환 프록시 레이어** 중 하나로 먼저 고르는 게 안전합니다. (OpenAI 호환 서브셋을 제공하는 Ollama 서버 이미지 예시가 존재) ([hub.docker.com](https://hub.docker.com/r/hwdsl2/ollama-server?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “OpenAI 호환”은 인터페이스 통일용이지, 운영 요구사항의 끝이 아니다
vLLM/TGI 모두 OpenAI-compatible 서버를 전면에 내세우지만, 실제 운영에서는
- 요청 큐잉(레이트리밋/우선순위)
- 배치 작업(대량 JSONL)을 온라인 서빙에 직접 때리지 않기
같은 **트래픽 형태 분리**가 중요합니다. (온라인 서빙에 배치 트래픽을 직접 꽂아 서버를 망가뜨리는 사례가 커뮤니티에서 반복) ([reddit.com](https://www.reddit.com/r/Vllm/comments/1u24zxn/openai_batch_api_for_existing_vllm_servers_jsonl/?utm_source=openai))  
즉, OpenAI 호환은 “앱 변경 최소화”이고, **SLO는 별도 설계**해야 합니다.

### Best Practice 2) TGI는 반드시 “버전 pinning + 토큰/모델 로딩 사전검증”
- `:latest`는 피하고(깨지면 원인 추적이 어렵습니다), 검증된 태그로 고정하는 게 실무적으로 유리합니다. ([theneuralbase.com](https://theneuralbase.com/tgi/learn/beginner/text-generation-inference-hf/?utm_source=openai))  
- 게이티드 모델은 `HF_TOKEN` 누락 시 “컨테이너는 뜨는데 첫 inference에서 로딩 실패” 류의 장애가 나기 쉬우니, **헬스체크를 ‘프로세스 살아있음’이 아니라 ‘모델 로딩 완료’ 기준**으로 잡는 게 좋습니다. ([theneuralbase.com](https://theneuralbase.com/tgi/learn/beginner/text-generation-inference-hf/?utm_source=openai))

### Best Practice 3) Ollama는 “동시성/노출”을 기본값으로 믿지 말고, 역프록시 + 제한을 먼저
Ollama는 편하지만, 운영 서버로 노출할 때는
- `OLLAMA_NUM_PARALLEL`로 무작정 병렬을 올리기보다 GPU 메모리와 컨텍스트 길이를 기준으로 보수적으로 시작
- Nginx 같은 reverse proxy로 TLS/인증/레이트리밋을 앞단에서 처리
가 안전한 출발입니다. 실전 가이드들도 이 스택을 권합니다. ([markaicode.com](https://markaicode.com/integrate/deploy-ollama-production-server-guide/?utm_source=openai))  

### 흔한 함정 1) 멀티 GPU 병렬(TP/PP)은 “옵션만 올리면 끝”이 아니다
vLLM은 TP/PP를 지원하고, 문서/레시피에서도 `--tensor-parallel-size`, `--pipeline-parallel-size` 같은 스케일링 방법이 이야기됩니다. ([kubernetes.recipes](https://kubernetes.recipes/recipes/ai/distributed-inference-kubernetes/?utm_source=openai))  
하지만 실제론 NCCL/드라이버/토폴로지(NVLink 유무)/컨테이너 런타임에 따라 첫 요청이 hang 하는 등 운영 리스크가 존재합니다. ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1rvtg8g/vllm_hangs_on_multigpu_parallelism/?utm_source=openai))  
따라서 “단일 노드 단일 GPU로 성능/안정성 베이스라인 → 단일 노드 멀티 GPU → 멀티 노드” 순으로 단계적으로 올리는 게 좋습니다.

### 흔한 함정 2) ‘throughput 최적화’가 ‘TTFT 최적화’와 충돌
continuous batching은 GPU utilization을 끌어올려 TPS를 올리지만, **초기 토큰이 늦게 나오는(TTFT 증가)** 형태로 사용자 체감이 나빠질 수 있습니다.  
- 사용자 인터랙션(챗봇)은 TTFT 민감
- 백그라운드 요약/분류는 throughput 민감  
워크로드를 섞지 말고, 가능하면 **서버 풀을 분리**하거나 라우팅 계층을 두세요.

### 비용/성능/안정성 트레이드오프(요약)
- vLLM: 성능 잠재력↑ / 튜닝·운영 난이도↑ / 대규모 트래픽에 강함
- TGI: 운영 패키지화↑ / HF 생태계 친화↑ / 버전·토큰·백엔드 조합 관리가 핵심
- Ollama: 개발자 UX↑ / 단일 서버 운영 단순↑ / 대규모/복잡한 SLO엔 한계가 빨리 옴

---

## 🚀 마무리
핵심은 “셋 중 무엇이 더 좋나”가 아니라, **내 트래픽 형태와 운영 역량에 무엇이 맞나**입니다.

도입 판단 기준(현업용 체크리스트):
1) **동시성/트래픽이 본격적**이고 GPU를 끝까지 뽑아야 한다 → vLLM 우선 검토(특히 OpenAI-compatible로 앱 변경 최소화). ([docs.vllm.ai](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/?utm_source=openai))  
2) Hugging Face 모델/배포 레시피 중심으로 **표준화된 프로덕션 서빙**이 필요 → TGI(단, 버전 pinning/토큰/헬스체크를 운영 규칙으로). ([theneuralbase.com](https://theneuralbase.com/tgi/learn/beginner/text-generation-inference-hf/?utm_source=openai))  
3) 내부 도구/온프렘 단일 서버에 **빠르고 단순한 로컬 배포**가 목적 → Ollama(대신 노출/동시성/프록시를 먼저 설계). ([markaicode.com](https://markaicode.com/integrate/deploy-ollama-production-server-guide/?utm_source=openai))  

다음 학습 추천(바로 실무로 이어지는 순서):
- vLLM: OpenAI-compatible server + 병렬 스케일링 문서(클러스터 토폴로지/TP·PP 감각 잡기). ([docs.vllm.ai](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/?utm_source=openai))  
- TGI: 공식 API reference(/v1/chat/completions)와 배포 예제(GKE 등)로 운영 형태를 먼저 확정. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/en/reference/api_reference?utm_source=openai))  
- Ollama: 환경변수/동시성(OLLAMA_NUM_PARALLEL)과 systemd/프록시 기반 하드닝 패턴을 팀 표준으로 문서화. ([modelpiper.com](https://modelpiper.com/blog/ollama-environment-variables?utm_source=openai))