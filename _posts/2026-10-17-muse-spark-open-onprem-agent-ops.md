---
title: "Muse Spark Open 오픈웨이트를 온프렘 에이전트로 운영하는 설계 포인트"
description: "Muse Spark Open 오픈웨이트를 로컬/온프렘에 들일 때의 라이선스·provenance·SBOM, 1M 컨텍스트 캐시, MoE 비용/토폴로지를 운영 관점에서 정리합니다."
date: 2026-10-17 12:32:26 +0900
categories: ["AI", "LLM Serving"]
tags: ["muse-spark-open", "open-weights", "model-provenance", "sbom", "long-context", "moe-serving"]
render_with_liquid: false
---

## 오픈웨이트를 “기업 배포 가능한 아티팩트”로 바꾸는 첫 관문: 라이선스와 접근 제어

Meta는 2026-10-15에 Muse Spark Open의 weights 공개를 공식 발표했습니다. 모델 스펙으로는 816B total parameters, 42B active parameters, 1M-token context window를 전면에 내세웠고, Mac Studio 2대(Apple M5 Ultra) + MLX로 데스크톱 실행도 강조했습니다[^1].

그런데 프로덕션 관점에서 더 중요한 건 “weights가 공개되었다”는 문장 하나로 끝나지 않는다는 점입니다. **오픈웨이트는 곧바로 내부 보안 정책/컴플라이언스/배포 체계와 충돌**합니다. 특히 Muse Spark Open은 Meta의 커스텀 라이선스인 Muse Model License로 배포됩니다[^2].

라이선스에서 실제 운영팀이 걸려 넘어지기 쉬운 포인트는 대략 세 가지로 정리됩니다.

1) UI/문서에 특정 문구 표기 요구
- 라이선스 조건에 “Built with Muse Spark Open”을 제품 UI/문서/웹/설정 메뉴 등에 눈에 띄게 표기하라는 조항이 들어가 있습니다[^2].
- 온프렘 에이전트가 “내부 운영 도구”인지 “고객-facing 제품”인지에 따라 이 조항이 실제로 UI 변경 작업으로 이어집니다. 특히 B2B SaaS에서 화이트라벨 요구가 있는 경우, 법무/세일즈 측면에서 이 문구가 문제로 번질 수 있습니다.

2) Model as a Service 매출 기준 통지/별도 계약 요구
- Muse Model License에는 “Model as a Service”로 제3자에게 API 형태로 제공하고, 일정 매출(aggregate gross revenue) 기준을 넘으면 Meta에 통지하고 별도 계약을 체결해야 한다는 조건이 있습니다[^2].
- 많은 팀이 “우리는 온프렘으로 쓸 거라 괜찮다”에서 끝내는데, 현실에선 다음 케이스가 애매합니다.
  - 내부 플랫폼 팀이 사내 공용 LLM API를 운영하고, 그 API를 각 사업부가 호출하는 구조
  - 고객사별로 전용 배포(Managed On-Prem) 형태로 “사실상 API 제공”을 하는 구조
- 라이선스의 문장 해석은 법무 영역이지만, 아키텍처 자체가 라이선스 트리거를 건드릴 수 있다는 사실은 기술 의사결정에서 선제적으로 반영해야 합니다.

3) weights 접근 자체가 gated이고, 다운로더의 신원/연락처가 남는다
- Hugging Face Hub의 “gated model”은 사용자가 모델 접근 시 사용자명과 이메일을 모델 저자에게 공유하는 동의 흐름을 포함할 수 있습니다[^3].
- Muse Spark Open도 모델 카드 상에서 로그인/조건 동의 흐름이 존재합니다(모델 페이지에서 “review the conditions and access this model content” 형태로 노출)(예: [Muse-Spark-Open-816B-A42B](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B), [NVFP4 variant](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B-NVFP4)).

여기서 프로덕션 체크리스트가 바로 갈립니다.
- 개인 계정으로 다운받아 S3에 올려두고 팀이 쓰는 방식은 흔하지만, 공급망 관점에서는 “누가 어떤 조건에 동의하고 어떤 리비전을 가져왔는지”가 추적 불가능해지기 쉽습니다.
- 기업에서 재현 가능한 방식으로 운영하려면, 적어도 “조직 계정 기반의 다운로더”, “리비전 핀 고정”, “해시 기록”, “내부 아티팩트 레지스트리로 승격” 같은 절차가 필요합니다.

## weights provenance를 소프트웨어처럼 취급하기: 리비전 핀, 해시, 서명, 내부 레지스트리

온프렘/로컬 운영에서 오픈웨이트는 종종 “코드보다 더 위험한 바이너리”가 됩니다. 이유는 단순합니다.
- 코드 리포지토리는 보통 PR 리뷰/CI/정적 분석/서명이 있는데
- 모델 weights는 “큰 파일”이라는 이유로 이런 절차 밖에 방치되기 쉽습니다.

Muse Spark Open은 Hugging Face에 safetensors로 배포됩니다[^4][^5]. 이건 좋은 출발입니다. safetensors는 pickle 기반 포맷 대비 임의 코드 실행 위험을 줄이기 위해 설계된 포맷이고, upstream 변경에 대비해 특정 revision을 핀 고정하라는 권고도 명시합니다[^6].

하지만 포맷만으로 provenance 문제가 끝나진 않습니다. 최소한 아래 네 가지를 기록해야 합니다.

- Source of truth: 어디에서 가져왔는가
  - 예: Hugging Face repo, 특정 commit hash(revision)
- License snapshot: 다운 시점의 LICENSE 텍스트(또는 링크 + 해시)
- Model card snapshot: README/모델 카드(운영 주의사항 포함)
- File-level hashes: safetensors/토크나이저/설정 파일 각각 SHA256

여기까지가 “감사 가능한 다운로드”의 최소치입니다.

그 다음 단계가 조직별로 갈리는데, 나는 내부 운영에 올리는 weights는 결국 OCI artifact로 승격시키는 편을 선호합니다. 이유는 배포/스캔/서명/레지스트리 권한 제어가 컨테이너 생태계 쪽이 훨씬 성숙해 있기 때문입니다. Docker Model Runner는 Hugging Face에서 모델을 pull하거나, GGUF/safetensors를 OCI artifact로 패키징해 레지스트리에 배포하는 흐름을 명시적으로 지원합니다[^7].

여기에 “서명”이 붙으면 모델 공급망이 소프트웨어 공급망과 비슷한 형태가 됩니다.
- Sigstore는 OIDC 기반 키리스 서명과 투명성 로그를 통해 신원/무결성을 다루는 모델을 제공합니다[^8].
- OpenSSF Model Signing(OMS)은 AI 모델 아티팩트 서명을 위한 표준/툴링 방향을 제시하고, Sigstore bundle format + in-toto statement 기반을 전제로 합니다[^9][^10][^11].

중요한 건 “Meta가 이미 서명했는가”가 아니라, **내 조직이 배포한 모델이 무엇인지 내부적으로 증명할 수 있는가**입니다. 오픈웨이트는 외부 공격보다 내부 실수로 사고가 더 많이 납니다. 특히 아래 두 유형이 자주 나옵니다.
- 같은 모델 이름인데 리비전이 바뀌었고, 평가/검증 없이 운영에 들어간 경우
- 누군가가 변형(quantization/merge/adapter 포함)한 weights를 “원본과 동일”로 취급한 경우

라이선스 관점에서도 provenance는 필요합니다. “어떤 라이선스에 동의한 weights를 어떤 제품에 사용했는가”는 결국 증빙이 있어야 합니다.

## SBOM을 모델 배포물에 붙이는 방식: SPDX AI Profile을 최소 단위로 쓴다

SBOM을 모델에도 붙이자는 얘기는 이제 구호가 아니라 현실적 요구사항으로 들어오고 있습니다. SPDX 3.x는 AI Profile을 통해 AI 시스템/컴포넌트에 대한 표준화된 문서화를 목표로 합니다[^12][^13].

다만 모델 SBOM은 소프트웨어 SBOM보다 훨씬 복잡해지기 쉽습니다.
- weights는 수백 GB~TB 단위
- tokenizer/config/런타임 코드/커스텀 커널/서빙 이미지까지 포함
- 파생 모델(quantized, distilled, fine-tuned)의 계보 추적이 필요

내 경우 “완벽한 SBOM”을 목표로 하면 시작을 못 하게 되어서, 프로덕션에 바로 쓰는 최소 단위를 이렇게 잡습니다.

- 모델 배포 단위를 1개의 “Model Release”로 정의
- 그 릴리스에 포함되는 파일을 전부 나열(경로/크기/해시)
- 출처(repo URL + revision)
- 라이선스 텍스트의 해시
- 서빙 런타임(vLLM/SGLang/TensorRT-LLM 등)과 컨테이너 이미지 digest

여기서 SPDX 문서 포맷 자체를 100% 엄밀하게 따르지 못해도, 최소한 “감사 가능한 inventory”로서의 역할은 충분히 합니다. 중요한 건 **사람이 읽을 수 있고, CI에서 자동 생성/검증 가능하며, 변경이 감지되는 것**입니다.

아래는 Muse Spark Open 같은 대형 모델을 “내부 레지스트리로 승격”할 때의 현실적인 산출물 예시입니다.
- `model-manifest.json`: 파일 해시/크기/리비전 등 기계 친화
- `MODEL_PROVENANCE.md`: 사람이 읽는 provenance 요약
- `sbom.spdx.json`: SPDX AI Profile을 참고해 최소 필드부터 채우는 형태

SLSA 쪽에서는 provenance가 in-toto statement의 subject/materials/invocation 등을 담는 attestation으로 정의됩니다[^14]. 이걸 모델 배포에 그대로 들이대면 너무 무겁지만, “subject=weights 파일들” + “materials=원본 리포지토리 리비전” 정도만 잡아도 공급망 사고를 크게 줄일 수 있습니다.

## 1M 컨텍스트 운영에서 제일 먼저 부딪히는 벽: KV cache 용량과 대역폭

Muse Spark Open은 “1M-token context window”를 내세웁니다[^1][^4].

프로덕션에서 1M 컨텍스트가 의미를 가지려면, 두 가지가 성립해야 합니다.
- 단일 요청이 1M까지 들어간다
- 동시에 여러 요청을 받아도 성능/비용이 납득 가능하다

그리고 이 둘은 대개 동시에 성립하지 않습니다. 이유는 KV cache입니다.

vLLM 쪽에서는 long-context 서빙이 점점 더 memory-bound가 되고, 128k+에서 KV cache가 GPU 메모리를 지배하는 상황을 명시적으로 다룹니다[^15]. vLLM의 핵심 아이디어(PagedAttention)는 KV cache를 블록 단위로 관리해 메모리 낭비를 줄이는 구조입니다[^16][^17].

Muse Spark Open의 모델 카드에는 언어 모델 파트의 레이어/헤드 구조가 공개되어 있습니다(예: 62 layers, 16 KV heads, head dim 64)[^4]. 이 값만으로도 “KV cache가 왜 터지는지”를 대략 계산할 수 있습니다.

- KV heads: 16
- head dim: 64
- 한 토큰당 한 레이어에서 저장해야 하는 KV element 수(대략):
  - K: 16 * 64 = 1024
  - V: 16 * 64 = 1024
  - 합: 2048 elements
- BF16(2 bytes)라고 가정하면 한 레이어 한 토큰당 KV bytes ≈ 2048 * 2 = 4096 bytes
- 레이어 62개면 한 토큰당 KV bytes ≈ 4096 * 62 ≈ 253,952 bytes (약 248 KiB)
- 컨텍스트 1,048,576(=2^20) 토큰이면, 배치 1에서 KV cache만 대략 248 GiB 규모가 됩니다.

이 계산은 단일 GPU에 다 들어간다는 뜻이 아니라, “샤딩/텐서 병렬/파이프라인 병렬을 해도 1M 컨텍스트는 결국 KV cache가 시스템을 지배한다”는 직감치를 줍니다. 그래서 Muse Spark Open 모델 카드도 실행 요구사항을 매우 공격적으로 적어놨습니다.
- NVFP4로도 최소 700GB VRAM
- BF16은 2TB VRAM
- 지원 프레임워크로 SGLang, vLLM, TensorRT-LLM, Unsloth, Llama.cpp 등을 언급
- Mac Studio 2대(M5 Ultra) + MLX 최적화 언급
[^5]

또 Hugging Face의 배포 가이드에서는 NVFP4 variant를 Inference Endpoints에서 SGLang recipe로 돌릴 때,
- 8 × NVIDIA RTX Pro 6000 98GB: 컨텍스트 131,072
- 8 × NVIDIA H200 141GB: 컨텍스트 1,048,576
라는 식으로 하드웨어-컨텍스트 길이를 직접 연결해 제시합니다[^18].

여기서 결론은 간단합니다.

1) 1M 컨텍스트를 “기능”으로 보지 말고 “시스템 모드”로 봐야 합니다.
- 같은 모델이라도 128k 모드와 1M 모드는 필요한 GPU/네트워크/호스트 메모리/요금이 완전히 달라집니다.

2) 1M 컨텍스트가 필요하다고 해서 “매 요청마다 1M을 채우는 프롬프트”가 정답이 아닙니다.
- 대개는 prefix reuse + 외부 메모리 + 선택적 재주입이 더 싸고 더 빠릅니다.

## 1M 컨텍스트에서 프롬프트/메모리/캐시를 분리 설계한다

온프렘 에이전트에서 1M 컨텍스트가 매력적인 이유는 단순합니다. “이전 대화/로그/코드/문서”를 다 넣어도 되니까 RAG를 덜 해도 될 것 같기 때문입니다.

실제로는 반대로 가는 편이 운영이 안정적입니다.

### 시스템 프롬프트/툴 스키마는 길어질수록 캐시가 자산이 된다
에이전트를 운영하다 보면 다음 덩어리들이 생각보다 큽니다.
- system prompt(행동 규칙/보안 정책/출력 포맷)
- tool schema(OpenAPI JSON, DB schema, internal RPC schema)
- 조직 공통 가드레일(PII 처리 규칙, change management 규칙)

이 덩어리들은 “모든 요청에서 반복”되는 경향이 큽니다. 따라서 long-context 모델로 갈수록, 이 prefix를 어떻게 재사용하느냐가 비용과 지연을 좌우합니다.

vLLM 내부 문서에서도 KV cache allocation과 prefix caching 같은 개념을 설계 레벨에서 다룹니다[^19]. long-context 에이전트는 결국 “프롬프트 엔지니어링”이 아니라 “캐시 엔지니어링”에 가까워집니다.

내가 잡는 원칙은 하나입니다.
- 조직 공통 prefix는 최대한 안정적으로 고정한다
- 고정된 prefix가 바뀌면, 캐시 무효화 비용을 제품 변경 비용으로 취급한다

### 대화 메모리는 1M을 다 쓰지 말고 계층화한다
1M 컨텍스트는 대화가 길어져도 한 요청 안에서 유지할 수 있다는 뜻이지만, 그렇다고 모든 것을 원문 그대로 유지하는 게 좋은 건 아닙니다.

운영에서 내가 겪는 실패 패턴은 보통 이렇습니다.
- 컨텍스트가 길어질수록 모델이 “모든 것을 고려한 답”을 주지 않는다
- 오히려 잡음이 늘어, 중요한 제약 조건을 놓치는 빈도가 올라간다
- 비용과 TTFT(Time To First Token)가 폭발한다

그래서 대화/작업 메모리는 보통 3계층이 현실적입니다.
- Working set: 지금 필요한 것만(수천~수만 토큰)
- Episodic memory: 요약/결정 사항만(수백~수천 토큰)
- Archive: 원문은 외부 저장소에 두고 필요할 때만 재주입

1M 컨텍스트는 이 중 Archive를 “한 번에 다 넣을 수 있다”는 옵션을 주지만, 프로덕션에선 “필요할 때만 넣는 파이프라인”이 더 안정적입니다.

### KV cache를 GPU 밖으로 확장하는 전략: host memory와 분산 스토리지
컨텍스트를 길게 유지하려면 결국 KV cache가 커집니다. 이때 선택지는 대략 세 갈래입니다.

- KV cache quantization
  - vLLM은 KV-cache를 FP8로 두는 옵션을 제공하며 long-context에서 메모리 병목을 줄이려는 배경을 설명합니다[^15].
- KV cache paging/eviction
  - PagedAttention은 KV cache를 블록으로 쪼개 물리 메모리 할당을 효율화하는 접근입니다[^17].
- GPU 밖으로 KV cache를 확장
  - SGLang은 prefix KV reuse를 위한 RadixAttention, 그리고 host memory/분산 스토리지로 KV cache를 확장하는 HiCache를 문서화합니다[^20].

특히 에이전트 워크로드는 “비슷한 prefix를 반복하고, 긴 컨텍스트를 여러 번 재사용하는” 형태가 많아서 HiCache 류의 전략이 잘 맞습니다. 반대로 “매 요청마다 완전히 새로운 1M 입력”이라면, long-context 모델의 장점보다 비용이 먼저 튀어나옵니다.

## MoE에서 비용을 보는 법: total parameters가 아니라 active parameters와 통신을 본다

Muse Spark Open은 sparse Mixture-of-Experts 모델로 소개됩니다. Meta와 Hugging Face 자료에서 공통적으로 다음을 명시합니다.
- 816B total parameters
- 약 42B active per token
- MoE layer마다 256 experts, 토큰당 8 experts 선택(top-k routing)
[^1][^21]

MoE를 “비용 절감 모델”로 오해하면 프로덕션에서 바로 깨집니다. MoE가 바꿔주는 건 “연산량의 스케일링 방식”이지, 운영 비용을 자동으로 낮추는 버튼이 아닙니다.

### 1) 토큰당 연산량의 1차 근사는 active parameters로 잡는다
dense 모델의 거친 근사처럼, MoE도 “토큰당 MLP 연산은 active FFN 파라미터에 비례”한다고 잡을 수 있습니다. Muse Spark Open은 active가 42B라고 공개되어 있으니, 이 모델을 dense 42B급으로 착각하기 쉬운데 실제론 다음이 추가됩니다.
- attention 연산(특히 long-context에서 KV read bandwidth)
- router/dispatch 비용
- expert 간 all-to-all 통신 비용(토폴로지에 따라 크게 달라짐)

결국 active parameters는 “GPU compute 비용”의 대략적인 축이고, long-context에서는 “memory bandwidth + 네트워크 통신”이 더 큰 축이 됩니다.

### 2) weight 메모리 비용은 total parameters와 관련이 깊다
MoE는 한 토큰에서 일부 expert만 활성화되더라도, 서빙 인스턴스는 결국 그 expert weights를 메모리에 올려야 합니다(물론 offload/streaming 같은 예외 설계를 할 수 있지만, 그건 지연/복잡도 비용이 큽니다).

Muse Spark Open 모델 카드가 NVFP4에도 700GB VRAM, BF16에 2TB VRAM을 적어둔 이유는 결국 여기로 돌아옵니다[^5].

### 3) MoE는 “서빙 토폴로지 설계 문제”를 운영팀에 넘긴다
dense 모델을 tensor parallel로 쪼개면 대개는 “선형 대수 + NCCL 최적화”의 영역이지만, MoE는 expert placement가 개입합니다.

- 모든 GPU에 모든 expert를 복제하면: 메모리로 죽는다
- expert를 GPU들에 분산 배치하면: 토큰마다 expert 호출을 위해 all-to-all 통신이 생긴다

따라서 MoE 서빙은 “어떤 네트워크 도메인 안에서 expert를 묶을 것인가”가 핵심입니다.
- 단일 노드 8-GPU(NVLink) 안에서 끝낼 수 있으면 제일 단순합니다.
- 멀티 노드로 넘어가면, all-to-all이 InfiniBand로 튀면서 tail latency가 늘기 쉽습니다.

Hugging Face가 1M 컨텍스트를 8×H200 같은 형태로 제시한 건, 기능 요건뿐 아니라 “토폴로지 단순화”까지 포함한 메시지로 해석하는 편이 현실적입니다[^18].

## 서빙 아키텍처를 단순화하는 패턴: 1M 컨텍스트는 전용 풀로 격리한다

온프렘 에이전트에서 1M 컨텍스트를 제대로 쓰려면, 나는 서빙을 최소 두 개의 풀로 나누는 쪽이 낫다고 봅니다.

- Long-context pool
  - 1M 컨텍스트, 낮은 동시성, 높은 VRAM, 높은 비용
  - “대규모 코드베이스/로그/문서”를 한 번에 ingest해야 하는 작업
- Short-context pool
  - 32k~128k 정도(조직 상황에 따라)
  - 대부분의 interactive turn, tool call loop

이렇게 나누면 좋은 점이 명확합니다.
- 1M 풀은 소수의 “비싼 작업”만 받게 되어 비용 폭주를 막습니다.
- interactive 워크로드는 더 싼 풀에서 지연이 안정화됩니다.

Muse Spark Open이 “agentic work”를 강조하지만[^22], 에이전트는 보통 긴 작업을 “여러 번의 짧은 턴”으로 수행합니다. 그러면 1M 컨텍스트가 항상 필요한 게 아니라 “초기 이해 단계에서만” 필요한 경우가 많습니다.

여기서 운영 설계 포인트는 하나입니다.
- 1M을 기본값으로 만들지 말고, 라우팅 규칙을 만들고, 라우팅 자체를 관측 가능하게 만든다.

## 배포와 보안의 접점: trust_remote_code, 파일 포맷, 리비전 고정

오픈웨이트를 안전하게 배포할 때 자주 놓치는 체크가 두 가지입니다.

1) 파일 포맷
- Muse Spark Open은 safetensors를 사용합니다[^4].
- safetensors는 pickle 기반 포맷 대비 임의 코드 실행 위험을 줄이려는 의도를 명확히 밝히고 있습니다[^6].

2) 리비전 고정
- safetensors 프로젝트도 “특정 revision을 핀 고정하라”는 권고를 합니다[^6].
- 운영에서 weights는 “최신이 항상 좋은” 유형의 의존성이 아닙니다. 평가/가드레일/캐시가 엮이기 때문에, 리비전이 움직이면 장애로 이어집니다.

내 기준에서 “오픈웨이트를 프로덕션에 들였다”는 건, 서빙이 성공했다가 아니라 다음이 갖춰졌다는 뜻입니다.
- 리비전이 고정되어 있고
- 해시가 기록되어 있고
- 내부 레지스트리에 있고
- 재현 가능한 방식으로 다시 가져올 수 있다

## 실행 가능한 형태로 굳히기: 다운로드/해시 매니페스트/서빙

아래 예시는 “Muse Spark Open을 사내 격리망에 반입”하는 현실적인 흐름을 가정합니다.
- 다운로드는 인터넷 가능한 빌드 존에서 수행
- weights는 내부 오브젝트 스토리지/레지스트리로 승격
- 서빙 존은 egress 제한(필요 시 완전 차단)

### 1) 다운로드 + 파일 해시 매니페스트 생성

의존성(검증된 버전으로 고정하는 편이 안전합니다)

```bash
python -V
# Python 3.11.x 권장

pip install "huggingface_hub==0.28.1" "tqdm==4.67.1"
```

`download_and_manifest.py`

```python
import os
import json
import hashlib
from pathlib import Path
from huggingface_hub import snapshot_download
from tqdm import tqdm

REPO_ID = os.environ.get("REPO_ID", "meta-models/Muse-Spark-Open-816B-A42B-NVFP4")
REVISION = os.environ.get("REVISION")  # 예: "<commit hash>" 를 권장
HF_TOKEN = os.environ.get("HF_TOKEN")
OUT_DIR = Path(os.environ.get("OUT_DIR", "./muse_spark_open_snapshot"))

if not HF_TOKEN:
    raise SystemExit("HF_TOKEN env is required for gated model download")

# revision을 명시하지 않으면 재현성이 깨집니다.
# 파일이 너무 큰 모델일수록 '반드시 커밋 해시'로 고정하는 쪽이 안전합니다.
local_dir = snapshot_download(
    repo_id=REPO_ID,
    revision=REVISION,
    token=HF_TOKEN,
    local_dir=OUT_DIR,
    local_dir_use_symlinks=False,
)

local_dir = Path(local_dir)

files = [p for p in local_dir.rglob("*") if p.is_file()]
manifest = {
    "repo_id": REPO_ID,
    "revision": REVISION,
    "local_dir": str(local_dir),
    "files": [],
}

for p in tqdm(files, desc="hashing"):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    manifest["files"].append(
        {
            "path": str(p.relative_to(local_dir)),
            "size_bytes": p.stat().st_size,
            "sha256": h.hexdigest(),
        }
    )

manifest_path = local_dir / "model-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

print("wrote:", manifest_path)
print("file_count:", len(manifest["files"]))
```

실행

```bash
export HF_TOKEN="<huggingface token>"
export REPO_ID="meta-models/Muse-Spark-Open-816B-A42B-NVFP4"
# export REVISION="<commit hash>"  # 강력 권장
python download_and_manifest.py
```

예상 출력(형태)

```text
wrote: muse_spark_open_snapshot/model-manifest.json
file_count: 123
```

이 단계 산출물(`model-manifest.json`)은 SBOM이 아니어도 됩니다. 중요한 건 “나중에 동일 파일인지 검증할 수 있는 근거”가 생겼다는 점입니다.

### 2) vLLM로 OpenAI-compatible 서빙(거대한 하드웨어가 전제)

Muse Spark Open 모델 페이지는 vLLM 예시를 직접 제공합니다[^4].

```bash
pip install vllm
vllm serve "meta-models/Muse-Spark-Open-816B-A42B-NVFP4"
```

호출 예시(OpenAI-compatible)

```bash
curl -X POST "http://localhost:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  --data '{
    "model": "meta-models/Muse-Spark-Open-816B-A42B-NVFP4",
    "messages": [{"role": "user", "content": "say hi"}]
  }'
```

이 커맨드는 “돌아간다”는 수준의 예시지, 1M 컨텍스트 운영 설정을 담고 있진 않습니다. 1M은 하드웨어와 런타임 기능 조합으로 성립하는 별도 모드에 가깝고, Hugging Face도 Endpoints 레시피에서 하드웨어별 컨텍스트 상한을 분리해 안내합니다[^18].

### 3) SGLang + HiCache로 long-context 재사용 최적화(개념을 운영에 반영)

Muse Spark Open 모델 페이지는 SGLang 예시도 제공합니다[^4].

```bash
pip install sglang
python3 -m sglang.launch_server \
  --model-path "meta-models/Muse-Spark-Open-816B-A42B-NVFP4" \
  --host 0.0.0.0 \
  --port 30000
```

여기에 long-context에서 체감이 큰 최적화 축이 KV cache reuse인데, SGLang은 RadixAttention/HiCache 설계를 공개하고 host memory pool 크기 플래그 예시도 제공합니다[^20].

```bash
python3 -m sglang.launch_server \
  --model-path "meta-models/Muse-Spark-Open-816B-A42B-NVFP4" \
  --host 0.0.0.0 \
  --port 30000 \
  --hicache-size 30
```

여기서 `--hicache-size 30`은 “rank당 host memory 30GB 풀 할당” 같은 식의 의미로 문서에 예시가 있습니다[^20]. 실제 최적 값은 워크로드(동일 prefix 재사용률, 세션 길이, 동시성)에 따라 달라집니다.

### 4) Hugging Face Inference Endpoints로 1M 컨텍스트를 빨리 검증

온프렘 구축 전에 “1M 컨텍스트 모드가 우리 워크로드에서 의미가 있나”를 검증하려면, 단기간에는 관리형 엔드포인트가 유리할 때가 많습니다.

Hugging Face는 Muse Spark Open NVFP4 variant에 대해 SGLang pre-validated recipe를 제공하고, 1M 컨텍스트(1,048,576)는 8×H200 141GB 구성을 연결해 안내합니다[^18].

```bash
hf endpoints catalog deploy \
  --repo meta-models/Muse-Spark-Open-816B-A42B-NVFP4 \
  --name muse-spark
```

이 접근의 장점은 “성능이 좋다”가 아니라, **하드웨어/런타임 매트릭스가 정리된 상태에서 기능 검증을 빨리 끝낼 수 있다**는 점입니다.

## 도입 판단 기준: 언제 Muse Spark Open이 맞고, 언제 아닌가

Muse Spark Open은 “오픈웨이트로 에이전트 구축”의 재료가 된 건 맞습니다. 다만 프로덕션 도입의 핵심 판단 기준은 성능 요약이 아니라 운영 가능성입니다.

- 라이선스/표기/매출 조건이 제품 구조와 충돌하면, 기술적으로 가능해도 도입 비용이 올라갑니다[^2].
- weights 접근이 gated이고, 조직 정책상 외부로 계정 정보가 나가는 것이 문제라면, 반입 절차가 먼저 정의되어야 합니다[^3].
- 1M 컨텍스트는 KV cache 때문에 “서빙 모드” 자체가 달라지고, 하드웨어 비용이 폭발합니다. Hugging Face가 1M을 8×H200으로 제시하는 건 상징이 아니라 요건에 가깝습니다[^18].
- MoE는 active parameters 덕분에 compute만 보면 착시가 생기지만, 메모리(총 weights)와 통신(토폴로지)이 운영 난이도를 결정합니다[^21].

내 결론은 단순합니다. Muse Spark Open을 온프렘 에이전트로 운영한다는 건 “모델 하나 추가”가 아니라, 모델을 아티팩트로 관리하는 공급망 체계(SBOM/provenance/서명)와 1M 컨텍스트를 위한 캐시/토폴로지 체계를 같이 도입하는 일입니다. 그 두 축을 동시에 할 각오가 있는 팀에만 이 모델이 실전 카드가 됩니다.

## 참고 자료

- [Meta AI Research 발표](https://research.meta.ai/blog/muse-spark-open)
- [Meta 개발자 블로그: Build with Muse Spark Open](https://dev.meta.ai/resources/blog/build-with-muse-spark-open)
- [Hugging Face 블로그: Welcome Muse Spark Open](https://huggingface.co/blog/meta-muse-spark-open)
- [Hugging Face 배포 가이드(원문 Markdown)](https://github.com/huggingface/blog/blob/main/meta-muse-spark-open.md)
- [Muse Spark Open BF16 모델 카드](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B)
- [Muse Spark Open NVFP4 모델 카드](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B-NVFP4)
- [Muse Model License 원문](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B/blob/main/LICENSE.md)
- [Hugging Face gated models 문서](https://huggingface.co/docs/hub/models-gated)
- [Docker Model Runner 문서](https://docs.docker.com/ai/model-runner)
- [safetensors SECURITY.md](https://github.com/safetensors/safetensors/blob/main/SECURITY.md)
- [vLLM FP8 KV-cache 글](https://vllm.ai/blog/2026-04-22-fp8-kvcache)
- [vLLM Paged Attention 문서](https://docs.vllm.ai/en/stable/design/paged_attention/)
- [PagedAttention 논문](https://arxiv.org/abs/2309.06180)
- [SGLang HiCache design](https://github.com/Schilings/sglang/blob/main/docs/advanced_features/hicache_design.md)
- [Sigstore Security Model](https://docs.sigstore.dev/about/security/)
- [OpenSSF Model Signing 프로젝트](https://openssf.org/projects/model-signing/)
- [OMS spec GitHub](https://github.com/ossf/model-signing-spec)
- [sigstore/model-transparency](https://github.com/sigstore/model-transparency/blob/main/README.md)
- [SLSA provenance spec](https://slsa.dev/spec/v0.2/provenance)
- [SPDX AI Profile 설명](https://spdx.github.io/spdx-spec/latest/model/AI/AI/)
- [SPDX specs 안내](https://spdx.dev/use/specifications/)

[^1]: <https://research.meta.ai/blog/muse-spark-open>
[^2]: <https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B/blob/main/LICENSE.md>
[^3]: <https://huggingface.co/docs/hub/models-gated>
[^4]: <https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B>
[^5]: <https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B-NVFP4>
[^6]: <https://github.com/safetensors/safetensors/blob/main/SECURITY.md>
[^7]: <https://docs.docker.com/ai/model-runner>
[^8]: <https://docs.sigstore.dev/about/security/>
[^9]: <https://openssf.org/projects/model-signing/>
[^10]: <https://github.com/ossf/model-signing-spec>
[^11]: <https://github.com/sigstore/model-transparency/blob/main/README.md>
[^12]: <https://spdx.github.io/spdx-spec/latest/model/AI/AI/>
[^13]: <https://spdx.dev/use/specifications/>
[^14]: <https://slsa.dev/spec/v0.2/provenance>
[^15]: <https://vllm.ai/blog/2026-04-22-fp8-kvcache>
[^16]: <https://docs.vllm.ai/en/stable/design/paged_attention/>
[^17]: <https://arxiv.org/abs/2309.06180>
[^18]: <https://github.com/huggingface/blog/blob/main/meta-muse-spark-open.md>
[^19]: <https://github.com/vllm-project/vllm/blob/main/docs/design/hybrid_kv_cache_manager.md>
[^20]: <https://github.com/Schilings/sglang/blob/main/docs/advanced_features/hicache_design.md>
[^21]: <https://huggingface.co/blog/meta-muse-spark-open>
[^22]: <https://dev.meta.ai/resources/blog/build-with-muse-spark-open>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
