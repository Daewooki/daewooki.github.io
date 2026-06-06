---
title: "2026년 6월 기준: vLLM·TGI·Ollama로 “진짜 운영 가능한” LLM 서빙 스택 짜는 법 (로컬/온프렘 최적화까지)"
date: 2026-06-06 04:08:57 +0900
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
LLM을 “돌아가게” 만드는 건 쉽습니다. 문제는 **여러 사용자가 동시에 쓰는 순간**부터 시작합니다: KV cache 폭증으로 OOM, 요청별 지연시간 요동, 배치가 안 잡혀 GPU utilization이 들쭉날쭉, 모델 로딩이 느려서 재시작이 곧 장애가 되는 식이죠. 이런 문제를 해결하려고 2026년에도 현장에서 많이 쓰는 선택지가 **vLLM / Hugging Face TGI / Ollama**입니다.

- **언제 쓰면 좋나**
  - **vLLM**: 동시성/처리량(throughput)이 핵심인 사내 API, 에이전트 백엔드, 사내 Copilot 등 “서버” 워크로드. OpenAI-compatible로 앱 전환 비용도 낮음. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.0/serving/openai_compatible_server.html?utm_source=openai))  
  - **TGI**: 관측/운영 기능(메트릭, tracing 등)과 “서빙 제품”으로서의 완성도를 원할 때. 다만 2026년 기준 **문서에서 maintenance mode를 명시**하고 있어 신규 도입은 신중해야 함. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/index?utm_source=openai))  
  - **Ollama**: 개발자 경험(DX), 로컬 개발/PoC, 개인/팀 단위 내재화에 최적. “Docker for LLMs”처럼 빠르게 띄우고 API로 붙이기 좋음(대신 고성능 멀티유저 운영은 한계가 빨리 옴). ([gigagpu.com](https://gigagpu.com/vllm-vs-ollama/?utm_source=openai))  

- **언제 쓰면 안 되나**
  - 트래픽이 낮고 단일 사용자 위주인데도 “괜히” vLLM/TGI로 복잡도만 올리는 경우(옵션 튜닝/장애 포인트 증가)
  - 규제/보안/감사 요구가 있는데 로컬 서빙의 **로그/프롬프트 저장 정책**을 정하지 않고 시작하는 경우(엔진 문제가 아니라 운영 설계 문제)

---

## 🔧 핵심 개념
### 1) LLM 서빙 병목은 “연산”보다 “메모리(KV cache)와 스케줄링”
Autoregressive decoding은 토큰을 한 개씩 생성합니다. 각 요청은 생성 과정에서 **KV cache**(attention key/value)를 계속 누적하고, 동시 요청이 늘면 KV cache가 VRAM을 잠식합니다. 그래서 서버는 단순히 “배치 크게”가 아니라, **요청 스케줄링 + KV cache 관리 + 연산 커널 최적화**가 핵심입니다.

- **Continuous batching**: 들어오는 요청을 “고정 배치”가 아니라 토큰 단위로 합쳐서 GPU를 계속 바쁘게 만듭니다(vLLM/TGI 모두 이 계열). ([huggingface.co](https://huggingface.co/docs/text-generation-inference/index?utm_source=openai))  
- **Paged KV cache / PagedAttention**: KV cache를 OS의 paging처럼 블록 단위로 관리해 단편화/낭비를 줄이고 더 많은 동시 요청을 수용합니다. vLLM의 정체성에 가깝고, TGI도 유사 최적화를 언급합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.0/serving/openai_compatible_server.html?utm_source=openai))  

### 2) vLLM vs TGI vs Ollama: 구조적 차이
- **vLLM**: “서버 워크로드”에서 처리량을 끌어올리는 데 집중. OpenAI-compatible server가 표준 인터페이스처럼 쓰이고, KV cache/배치/로드 최적화 옵션이 촘촘합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.0/serving/openai_compatible_server.html?utm_source=openai))  
- **TGI**: “제품형 서빙”의 전통(메트릭, tracing, 다양한 하드웨어 백엔드) + Hugging Face 생태계. 다만 공식 문서에서 **maintenance mode**를 박았기 때문에, 장기 로드맵이 중요한 팀은 vLLM/SGLang 등 대안을 함께 검토하는 게 안전합니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/index?utm_source=openai))  
- **Ollama**: 내부적으로 llama.cpp 계열을 활용하는 로컬 중심 경험. 팀 내 로컬 배포/개발 편의성이 강점이고, “한 대에서 여러 명이 쓰는 API 서버”로 키우려면 결국 **인스턴스 분리/로드밸런싱** 같은 운영 설계가 필요해집니다. ([gigagpu.com](https://gigagpu.com/vllm-vs-ollama/?utm_source=openai))  

---

## 💻 실전 코드
목표 시나리오: **사내 서비스가 OpenAI SDK 그대로**(chat.completions) 붙을 수 있게 하고, 로컬/온프렘에서 **vLLM(고성능) + Ollama(개발/백업) + TGI(레거시/운영기능)**를 같은 인터페이스로 교체 가능하게 구성.

### 1단계) vLLM: OpenAI-compatible API로 운영형 서빙 띄우기 (Docker)
- 요구: NVIDIA GPU + Docker
- 포인트: `--gpu-memory-utilization`, `--tensor-parallel-size`, KV cache dtype 같은 **운영 튜닝 레버**가 핵심입니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.0/serving/openai_compatible_server.html?utm_source=openai))  

```bash
# vLLM OpenAI-compatible server (예: 1 GPU, 단일 노드)
# MODEL은 HF repo 또는 로컬 경로. 운영에서는 /models에 prefetch해두는 게 안정적입니다.
export MODEL="mistralai/Mistral-7B-Instruct-v0.3"

docker run --gpus all --rm -p 8000:8000 \
  -e HF_TOKEN="$HF_TOKEN" \
  -v $PWD/models:/models \
  vllm/vllm-openai:latest \
  --model "$MODEL" \
  --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --kv-cache-dtype auto
```

예상 동작
- 헬스체크: `GET /health`
- OpenAI 호환: `POST /v1/chat/completions` (스트리밍 포함) ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.0/serving/openai_compatible_server.html?utm_source=openai))  

### 2단계) 애플리케이션 코드: “서버 교체”가 가능한 클라이언트 (Python)
같은 코드를 **vLLM/TGI/llama.cpp/Ollama(OpenAI 호환 프록시 사용 시)**로 바꿔 끼우려면, 핵심은 `base_url`과 `api_key`를 환경변수로 분리하는 겁니다.

```python
# requirements:
#   pip install openai==1.* tenacity

import os
from tenacity import retry, wait_exponential_jitter, stop_after_attempt
from openai import OpenAI

BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
API_KEY  = os.environ.get("LLM_API_KEY", "local")  # 로컬은 보통 의미 없음
MODEL    = os.environ.get("LLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

@retry(wait=wait_exponential_jitter(initial=0.5, max=8), stop=stop_after_attempt(3))
def ask_ticket_triage(ticket_text: str) -> str:
    # “toy”를 피하기 위해: 현실적인 헬프데스크 분류/요약 + JSON 강제(실전에서 바로 씀)
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": (
                "You are an internal support triage bot. "
                "Return STRICT JSON with keys: category, priority, summary, next_action."
            )},
            {"role": "user", "content": ticket_text},
        ],
    )
    return resp.choices[0].message.content

if __name__ == "__main__":
    sample = """VPN 접속이 아침부터 자주 끊깁니다. Windows 11이고, 회사 와이파이에서는 더 심해요.
로그인 재시도하면 잠깐 되다가 다시 끊깁니다. 오늘 회의가 많아서 급합니다."""
    print(ask_ticket_triage(sample))
```

예상 출력(예)
- `{"category":"network/vpn","priority":"P1",...}` 형태의 JSON 문자열

### 3단계) TGI: (가능하면) “기존 환경 유지” 목적의 배포
TGI는 문서상 maintenance mode이므로 “신규 표준”이라기보단, 이미 쓰고 있던 팀이 **안전하게 유지/이관**하는 관점이 더 현실적입니다. 그래도 OpenAI 호환/메트릭 등 기능은 강점으로 언급됩니다. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/index?utm_source=openai))  

```bash
# 예시: TGI 컨테이너로 모델 서빙 (구체 옵션은 모델/하드웨어에 따라 조정)
# 공식 문서의 CLI/옵션을 기준으로 운영 파라미터를 잡는 것을 권장합니다.
docker run --gpus all --rm -p 8080:80 \
  -e HF_TOKEN="$HF_TOKEN" \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id mistralai/Mistral-7B-Instruct-v0.3 \
  --port 80
```

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 체감되는 3가지)
1) **“동시성 목표”를 먼저 수치로 고정**하세요  
   예: “동시 사용자 30, 평균 1k prompt, 256 output, p95 < 2.5s”. 이걸 정해야 `max-model-len`, KV cache 정책, admission control(큐잉/거절)을 설계할 수 있습니다. vLLM은 이런 튜닝 레버가 많습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/latest/cli/serve.html?utm_source=openai))  

2) **모델 로딩 시간을 장애로 보라 (prefetch/가중치 staging)**  
   운영에서는 “서버 재시작 = 수 분간 응답 불가”가 흔합니다. 가중치 파일을 디스크/캐시에 미리 올리고, 롤링 배포 전략(이중화)을 기본값으로 두세요. vLLM CLI에는 로딩 최적화(예: prefetch 등) 관련 옵션/설명이 있습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/latest/cli/serve.html?utm_source=openai))  

3) **OpenAI-compatible를 ‘표준 ABI’로 삼아 엔진을 느슨하게 결합**  
   앱 코드는 OpenAI SDK 고정, 서버만 교체(vLLM ↔ TGI ↔ llama.cpp 계열)되게 만들면, 성능/비용 이슈가 터졌을 때 “이주”가 훨씬 싸집니다. vLLM과 llama.cpp 모두 OpenAI-compatible endpoint를 강조합니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.0/serving/openai_compatible_server.html?utm_source=openai))  

### 흔한 함정 / 안티패턴
- **Ollama를 멀티유저 운영 서버로 바로 쓰기**: DX는 좋지만, 동시성/멀티GPU/스케줄링에서 “서버형 엔진”만큼 예측 가능하게 뽑기 어렵습니다. 결국 GPU별 인스턴스 분리 같은 우회 운영이 필요해집니다(커뮤니티에서도 비슷한 조언이 반복). ([reddit.com](https://www.reddit.com/r/ollama/comments/1t33nh0/is_it_possible_to_use_2_gpus_with_ollama_amd/?utm_source=openai))  
- **컨텍스트 길이를 무작정 크게**: `max-model-len`을 올리면 품질보다 먼저 **KV cache 비용**이 폭증합니다. 장문 입력은 RAG로 쪼개거나, 요약 파이프라인을 앞단에 두는 게 더 싸고 안정적입니다.
- **“벤치마크 수치”만 보고 결정**: 벤치마크는 트래픽 패턴(프롬프트 길이, 출력 길이, 스트리밍 여부)에 따라 결론이 바뀝니다. 외부 비교 글은 참고만 하고, 반드시 **자기 트레이스로 리플레이**하세요. ([gigagpu.com](https://gigagpu.com/vllm-vs-tgi-vs-ollama-benchmark-comparison/?utm_source=openai))  

### 비용/성능/안정성 트레이드오프 한 줄 요약
- **성능(throughput)**: 대체로 vLLM이 유리하다는 벤치/현장 증언이 많음 ([gigagpu.com](https://gigagpu.com/vllm-vs-tgi-vs-ollama-benchmark-comparison/?utm_source=openai))  
- **운영 성숙도/관측성**: TGI는 “서빙 제품” 철학이 강점이지만, maintenance mode 리스크를 감안 ([huggingface.co](https://huggingface.co/docs/text-generation-inference/index?utm_source=openai))  
- **로컬 내재화/DX**: Ollama가 압도적으로 빠르지만, 멀티유저 운영은 별도 설계 필요 ([gigagpu.com](https://gigagpu.com/vllm-vs-ollama/?utm_source=openai))  

---

## 🚀 마무리
2026년 6월 기준으로 “내 프로젝트에 적용” 관점에서 정리하면:

- **운영형(동시성/처리량) 기본값은 vLLM**: OpenAI-compatible + KV cache/배치 최적화가 핵심 무기입니다. 특히 로컬/온프렘에서도 서버답게 굴리기 좋습니다. ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.0/serving/openai_compatible_server.html?utm_source=openai))  
- **TGI는 신규 표준이라기보다 ‘기존 사용자의 유지/이관’ 도구로 재해석**: 공식 문서의 maintenance mode 선언을 리스크로 보고, 장기 운영이면 vLLM/SGLang 계열을 같이 검토하세요. ([huggingface.co](https://huggingface.co/docs/text-generation-inference/index?utm_source=openai))  
- **Ollama는 팀 생산성을 올리는 로컬 엔진**: PoC/개발/개인 비서/내부 실험에 좋고, 멀티유저 운영으로 갈수록 인스턴스 분리/프록시/로드밸런싱 같은 “서버 엔지니어링”이 필요해집니다. ([gigagpu.com](https://gigagpu.com/vllm-vs-ollama/?utm_source=openai))  

다음 학습 추천(실무 우선순위)
1) vLLM OpenAI server의 주요 튜닝 플래그(메모리, 모델 로딩, 텐서 병렬) 문서 정독 ([docs.vllm.ai](https://docs.vllm.ai/en/v0.7.0/serving/openai_compatible_server.html?utm_source=openai))  
2) TGI의 exported metrics / tracing 설정을 보고 “우리 SLO에 필요한 관측 포인트” 체크 ([huggingface.co](https://huggingface.co/docs/text-generation-inference/index?utm_source=openai))  
3) 로컬 배포에서 llama.cpp(OpenAI-compatible)까지 포함해 “엔진 교체 가능한 ABI”로 아키텍처 굳히기 ([huggingface.co](https://huggingface.co/docs/inference-endpoints/engines/llama_cpp?utm_source=openai))  

원하면, 당신의 환경(단일 GPU/멀티 GPU, 예상 동시 사용자, 평균 prompt/output 토큰, 모델 후보, 쿠버네티스 사용 여부)을 기준으로 **vLLM/TGI/Ollama 중 무엇을 메인으로 두고 어떤 폴백/롤링 전략을 가져갈지**를 의사결정 표로 더 구체화해드릴게요.