---
title: "2026년 4월 기준: vLLM·TGI·Ollama로 LLM 서빙 “진짜” 배포하기 (로컬/프로덕션/최적화까지)"
date: 2026-04-30 03:52:22 +0900
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
LLM 서빙을 직접 운영하면 곧바로 부딪히는 문제가 3가지입니다.

1) **GPU 메모리(KV cache) 때문에 동시성(concurrency)이 안 나옴**  
2) **TTFT(Time To First Token) vs Throughput(토큰/초) 트레이드오프**로 “체감 속도”가 들쭉날쭉함  
3) 개발환경(로컬)에서는 잘 되는데, **배포(관측/롤링업데이트/장애대응)** 단계에서 갑자기 복잡해짐

2026년 4월 시점에서 실무적으로 가장 많이 비교되는 축은 **vLLM / Hugging Face TGI / Ollama**인데, 포지션이 꽤 명확합니다.

- **vLLM**: “GPU를 최대한 쥐어짜서” **동시성과 처리량**을 뽑고 싶을 때. OpenAI-compatible API 서버를 공식 지원해서 기존 클라이언트 재사용이 쉽습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.11.1/serving/openai_compatible_server/))  
- **TGI**: 여전히 현장에 깔린 곳이 많지만, Hugging Face 문서 기준으로 **2025-12-11부터 maintenance mode**라서 “신규 도입”은 보수적으로 봐야 합니다(마이그레이션 가이드도 vLLM/SGLang 쪽을 권장). ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi))  
- **Ollama**: 팀 생산성과 로컬 배포(특히 단일 노드, 개발자 경험)에 강점. 다만 높은 동시성/낮은 p99가 중요한 서비스에선 병목이 빨리 옵니다(벤치마크에서도 이런 경향이 반복). ([sitepoint.com](https://www.sitepoint.com/ollama-vs-vllm-performance-benchmark-2026/?utm_source=openai))  

언제 쓰면 좋은가 / 안 좋은가를 “프로젝트 관점”으로 정리하면:

- **vLLM 추천**: 동시 사용자 수가 늘 수 있고, 비용(=GPU당 처리량)을 KPI로 보는 서비스, 혹은 내부 플랫폼팀이 표준 서빙을 만들 때  
- **vLLM 비추천**: “1대에서 가볍게” + 운영 오버헤드를 최소화해야 하고, 대규모 동시성이 요구되지 않는 경우(이 경우 Ollama가 더 빠른 길)  
- **TGI 추천**: 이미 TGI 기반 운영이 있고, 단기간에 교체가 어렵지만 **v3 zero-config** 같은 자동 튜닝에 기대는 환경(단, 신규 도입은 maintenance mode 리스크를 감안) ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi))  
- **Ollama 추천**: 로컬/PoC/사내 도구/단일 서버에서 빠르게 띄우고, quantized 모델로 비용을 낮추고 싶을 때  
- **Ollama 비추천**: 다중 GPU 스케일링, 높은 동시성, 엄격한 tail latency(p95/p99)가 핵심인 경우 ([sitepoint.com](https://www.sitepoint.com/ollama-vs-vllm-performance-benchmark-2026/?utm_source=openai))  

---

## 🔧 핵심 개념
### 1) “서빙 성능”은 모델 FLOPs보다 **KV cache 관리**에서 갈립니다
대부분의 LLM 서빙 병목은 “한 토큰 생성”보다, **여러 요청의 prefill/decoding이 겹칠 때 KV cache를 어떻게 저장/스케줄링하느냐**에서 크게 갈립니다. 여기서 vLLM이 치고 나가는 이유가 **PagedAttention**입니다.  
- 전통적인 방식은 요청별 KV cache가 연속된 메모리 덩어리로 잡히기 쉬워서 fragmentation이 커지고, 동시 요청을 늘리기 어렵습니다.
- vLLM은 OS의 페이징처럼 KV cache를 “페이지 단위”로 관리해 **메모리 효율 + 높은 동시성**을 노립니다. ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai))  

결과적으로 “같은 GPU”에서도 **동시 요청이 늘어날수록 vLLM의 총 throughput 우위가 커지는** 패턴이 자주 관측됩니다. ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai))  

### 2) vLLM / TGI / Ollama의 내부 흐름 차이(실무 관점)
- **vLLM (OpenAI-compatible server)**  
  요청 → (tokenize) → **continuous batching 스케줄러**가 prefill/decoding을 GPU에 밀어 넣음 → PagedAttention으로 KV cache 페이지 할당/회수 → 스트리밍 응답.  
  핵심은 “배치를 사람이 고정으로 잡는” 게 아니라, **들어오는 요청을 계속 합쳐서 GPU idle time을 줄이는 것**입니다. ([morphllm.com](https://www.morphllm.com/vllm-benchmarks?utm_source=openai))  

- **TGI**  
  TGI v3에서 “zero-config”를 내세우며, 하드웨어를 보고 max input/total tokens 같은 배치 파라미터를 자동 산정합니다. 다만, 공식 문서상 maintenance mode로 들어갔기 때문에 “장기 운영 표준”으로는 리스크가 있습니다. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi))  

- **Ollama**  
  “서버”라기보다 개발자 친화적 런타임/패키저 성격이 강합니다. `ollama serve`로 HTTP API(`/api/chat`, `/api/generate`, `/api/embed`)를 노출하고, 모델 관리(pull/run)가 매우 쉽습니다. ([sitepoint.com](https://www.sitepoint.com/ollama-local-llm-production-deployment-docker/?utm_source=openai))  
  대신 대규모 동시성에서의 스케줄링/배치 최적화는 vLLM류에 비해 한계가 빨리 드러납니다(특히 p99). ([sitepoint.com](https://www.sitepoint.com/ollama-vs-vllm-performance-benchmark-2026/?utm_source=openai))  

### 3) “로컬 배포”와 “서빙 인프라”를 분리해서 보자
- 로컬에서 중요한 건: **재현성(Docker/Compose), 모델 캐시 영속화, GPU 패스스루, 개발자 UX**
- 프로덕션에서 중요한 건: **OpenAI-compatible 표준화, 관측(메트릭/로그), 롤링 업데이트, 멀티 GPU 확장, 장애 격리**

즉, 로컬은 Ollama가 편하고, 프로덕션은 vLLM이 강한 경우가 많습니다. “처음엔 Ollama → 트래픽 생기면 vLLM” 같은 단계적 전략이 실제로 합리적입니다. ([valendra.tech](https://valendra.tech/en/insights/self-hosted-llms-ollama-vllm-tgi?utm_source=openai))  

---

## 💻 실전 코드
아래는 “toy”가 아니라, **사내/서비스에서 바로 써먹는 형태**로 구성합니다.

- 목표 시나리오  
  1) 단일 GPU 서버에서 **vLLM을 OpenAI-compatible API**로 띄운다  
  2) 같은 네트워크에서 **worker(예: FastAPI 배치 작업)**가 OpenAI SDK 스타일로 호출한다  
  3) 운영 최소 요건(헬스체크/타임아웃/재시도/관측)을 넣는다  
  4) 로컬 개발자는 Ollama로 동일 인터페이스를 흉내 내며 개발한다(환경변수로 endpoint 전환)

### 1단계) vLLM 서버: Docker Compose (GPU + 모델 캐시 볼륨)
```bash
# 폴더 준비
mkdir -p llm-serve/vllm-cache
cd llm-serve
```

```yaml
# docker-compose.yml
services:
  vllm:
    image: vllm/vllm-openai:latest
    container_name: vllm
    ports:
      - "8000:8000"
    environment:
      # Hugging Face gated 모델이면 토큰 필요 (Secret로 관리 권장)
      - HF_HOME=/data/hf
    volumes:
      - ./vllm-cache:/data/hf
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    command:
      [
        "--model", "meta-llama/Llama-3.1-8B-Instruct",
        "--host", "0.0.0.0",
        "--port", "8000"
      ]
    healthcheck:
      test: ["CMD", "bash", "-lc", "curl -sf http://localhost:8000/v1/models | jq -e '.data | length > 0' >/dev/null"]
      interval: 10s
      timeout: 3s
      retries: 12
```

```bash
# 실행
docker compose up -d
docker logs -f vllm
```

확인:
```bash
curl -s http://localhost:8000/v1/models | jq
```

vLLM이 OpenAI-compatible server로 Completions/Chat API 등을 구현한다는 점이 핵심입니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.11.1/serving/openai_compatible_server/))  

### 2단계) 앱 서버(현실적인 호출): Python worker + 재시도/타임아웃 + 스트리밍
```bash
python -m venv .venv
source .venv/bin/activate
pip install "httpx==0.27.*" "tenacity==8.*"
```

```python
# client.py
import os
import json
import httpx
from tenacity import retry, wait_exponential_jitter, stop_after_attempt

BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000")
MODEL = os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
TIMEOUT = float(os.getenv("LLM_TIMEOUT_SEC", "60"))

@retry(wait=wait_exponential_jitter(initial=0.5, max=5), stop=stop_after_attempt(4))
def chat_stream(prompt: str):
    url = f"{BASE_URL}/v1/chat/completions"
    payload = {
        "model": MODEL,
        "stream": True,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "You are a senior SRE who answers with concrete steps."},
            {"role": "user", "content": prompt},
        ],
    }

    with httpx.Client(timeout=TIMEOUT) as client:
        with client.stream("POST", url, json=payload) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[len("data: "):]
                    if data == "[DONE]":
                        break
                    evt = json.loads(data)
                    delta = evt["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta

if __name__ == "__main__":
    q = "vLLM 서버를 운영할 때 p99 latency가 튀는 원인 5가지를 우선순위로 정리해줘."
    for chunk in chat_stream(q):
        print(chunk, end="", flush=True)
    print()
```

```bash
python client.py
```

예상 출력(요약):
- KV cache 압박/동시성 과다
- 과도한 max_tokens, 긴 context
- GPU 클럭/전력 제한, thermal throttling
- 토크나이저 CPU 병목
- 네트워크/프록시 버퍼링 등

### 3단계) 로컬 개발자는 Ollama로 전환(엔드포인트 스왑)
Ollama는 `ollama serve`로 API를 열 수 있고, Compose로 단일 노드 재현성을 확보하는 패턴이 흔합니다. ([sitepoint.com](https://www.sitepoint.com/ollama-local-llm-production-deployment-docker/?utm_source=openai))  
(중요: **운영에서는 모델 pull을 사전에 해두는 게 안전**하다는 경험칙도 많습니다. ([reddit.com](https://www.reddit.com/r/ollama/comments/1s7h9e7/production_notes_after_6_months_running_ollama/?utm_source=openai)))

아래처럼 “개발환경”에서만 Ollama를 띄우고, 앱은 `LLM_BASE_URL`만 바꿔치기하는 전략이 현실적입니다.

```yaml
# docker-compose.ollama.yml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ./ollama-data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    command: ["serve"]
```

```bash
docker compose -f docker-compose.ollama.yml up -d

# 모델은 운영/개발 모두 "사전 pull" 권장
docker exec -it ollama ollama pull llama3.1:8b-instruct
```

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **동시성은 “요청 수”가 아니라 “토큰 예산”으로 잡아라**  
   TGI 문서가 말하듯, max input length / max tokens / batch total tokens는 결국 “메모리 예산” 문제입니다. 길이를 조금만 낮춰도 동시 요청 수가 2배가 되는 경우가 흔합니다. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi))  

2) **표준 인터페이스는 OpenAI-compatible로 고정하고, 엔진은 교체 가능하게**  
   vLLM이 OpenAI-compatible server를 제공하므로 클라이언트/미들웨어/게이트웨이를 표준화하기 좋습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.11.1/serving/openai_compatible_server/))  
   (TGI→vLLM 마이그레이션도 결국 이 경로를 밟습니다. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi)))

3) **성능 튜닝은 “평균 TPS”가 아니라 p95/p99 + TTFT + 실패율로 본다**  
   벤치마크에서도 vLLM은 동시성이 커질수록 throughput 이점이 커지지만, 사용자 경험은 tail latency가 좌우합니다. synthetic TPS만 보고 결정하면 운영에서 후회합니다. ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai))  

### 흔한 함정/안티패턴
- **“컨텍스트 128k를 기본값으로 열어두기”**  
  긴 context는 KV cache를 폭발시키고 동시성을 갉아먹습니다. “최대 context”는 기능이 아니라 비용 폭탄일 수 있습니다. (TGI도 예시로 128k→64k로 낮추면 동시 요청이 늘 수 있음을 명시) ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi))  

- **Ollama를 멀티팀/멀티테넌트 프로덕션 코어로 바로 쓰기**  
  가능은 하지만, 결국 “동시성·격리·관측·롤링업데이트” 요구가 생기면 vLLM류 아키텍처가 그리워집니다. Ollama는 개발자 UX가 강점인 대신, 높은 동시성 경쟁에서는 불리하다는 관측이 반복됩니다. ([sitepoint.com](https://www.sitepoint.com/ollama-vs-vllm-performance-benchmark-2026/?utm_source=openai))  

- **모델 pull/다운로드를 런타임 요청 경로에 넣기**  
  첫 요청이 타임아웃 나거나, 배포 시점마다 변동이 생깁니다. (Ollama 운영 경험담에서도 사전 pull을 강조) ([reddit.com](https://www.reddit.com/r/ollama/comments/1s7h9e7/production_notes_after_6_months_running_ollama/?utm_source=openai))  

### 비용/성능/안정성 트레이드오프(의사결정 포인트)
- **비용(=GPU당 토큰)**: 동시성이 늘고 배칭이 먹을수록 vLLM이 유리해지는 경우가 많음(PagedAttention/continuous batching). ([arxiv.org](https://arxiv.org/abs/2511.17593?utm_source=openai))  
- **안정성(장기 유지보수)**: TGI는 공식적으로 maintenance mode라 “지금 신규 표준”으로 채택하기엔 리스크. ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi))  
- **개발 속도**: 로컬/단일 노드/개발자 경험은 Ollama가 압도적으로 빠른 경우가 많음. ([sitepoint.com](https://www.sitepoint.com/ollama-local-llm-production-deployment-docker/?utm_source=openai))  

---

## 🚀 마무리
정리하면, 2026년 4월 기준으로 “배포 방법”을 기술 스택 의사결정까지 포함해 해석하면 다음이 실무적으로 깔끔합니다.

- **로컬/PoC/사내 도구**: Ollama로 빠르게 반복 → 모델/프롬프트/제품 요구를 확정  
- **프로덕션 표준 서빙**: vLLM(OpenAI-compatible)로 고정 → 관측/게이트웨이/클라이언트 표준화  
- **TGI**: 기존 운영이 있으면 당장 유지 가능하되, 공식 maintenance mode를 감안해 **vLLM/SGLang로의 전환 계획**을 미리 세우는 게 안전 ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/tgi))  

다음 학습 추천(순서):
1) vLLM OpenAI-compatible server의 server/engine arguments와 운영 옵션 정리(헬스체크, 로깅, 병렬화/스케일링) ([docs.vllm.ai](https://docs.vllm.ai/en/v0.11.1/serving/openai_compatible_server/))  
2) “내 트래픽” 기준의 벤치마크 설계: TTFT/ITL/p99/실패율 + 컨텍스트 분포  
3) (조직이 커지면) 모델 서빙을 단일 엔진에 묶지 말고, OpenAI-compatible 게이트웨이(LiteLLM류)로 엔진 교체 가능성 확보

원하면, **(1) 단일 GPU 기준 vLLM 튜닝 체크리스트**, **(2) k8s에서 롤링 업데이트 시 warmup/모델 캐시 전략**, **(3) Ollama→vLLM 마이그레이션(프롬프트/템플릿/모델 포맷) 실전 플랜**까지 후속 글 형태로 더 구체화해드릴 수 있습니다.