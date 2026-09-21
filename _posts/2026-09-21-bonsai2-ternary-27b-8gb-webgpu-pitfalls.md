---
title: "Bonsai 2 27B ‘ternary’ 로컬 LLM을 8GB VRAM·WebGPU에 올릴 때 마주치는 품질·속도·운영 함정"
description: "5.9GB급 27B ternary 모델은 ‘돌아간다’보다 ‘어떻게 망가지는가’가 중요합니다. 추론 실패 패턴, 메모리 예산별 서빙 토폴로지, fp16/Q4 대비 품질 저하를 팀 합의 지표로 만드는 방법을 정리합니다."
date: 2026-09-21 13:17:17 +0900
categories: ["AI", "Local LLM"]
tags: ["local-llm", "ternary-quantization", "llama-cpp", "webgpu", "evaluation", "serving"]
render_with_liquid: false
---

PrismML이 2026-09-17에 발표한 Bonsai 2 27B는 Qwen3.8 27B를 ternary {−1, 0, +1} weight로 압축해 **언어 모델 본체를 5.95GB(PTQ1_0)~7.21GB(PQ2_0)** 범위에 넣었습니다. “27B급을 로컬에서”가 데모 문구가 아니라, 8GB VRAM 단일 GPU에서도 운영 옵션이 되는 쪽으로 문이 열린 사건입니다. 다만 이 모델은 단순 Q4/Q3 대비 “더 작다” 수준이 아니라, 추론 중 수치적 성질·런타임 요구사항·실패 모드가 달라서, 운영에 올릴 때 함정이 노골적으로 나옵니다.[^1]

## 모델 스펙을 숫자로 다시 읽기: 5.9GB의 의미와 ‘필수 런타임’

Bonsai 2 27B는 “ternary weights + FP16 group-wise scaling”을 사용하며, PrismML 발표문 기준으로 1.76 effective bits/weight, 총 5.9GB footprint를 전면에 내세웁니다. 이때 중요한 포인트는 두 가지입니다.[^2]

첫째, 이 모델은 low-bit weight-only를 “지원하는” 범용 런타임(일반적인 llama.cpp, vLLM, WebLLM) 위에 그냥 얹히는 타입이 아닙니다. Hugging Face 모델 카드가 명시하듯, **PrismML-Eng/llama.cpp 포크의 ‘ternary hybrid-attention kernels’와 Hadamard activation runtime**이 없으면 파일을 제대로 실행할 수 없습니다. 더 위험한 지점은 “로딩은 되는데 결과가 깨지는” 케이스입니다. 모델 카드에 따르면 stock llama.cpp는 PQ2_0/PTQ1_0를 unknown type으로 거부하지만, Q2_0를 경고 없이 로드해 garbage를 뱉을 수 있다고 적혀 있습니다. 운영 관점에서는 이것만으로도 배포 파이프라인의 체크리스트가 바뀝니다.[^3]

둘째, 파일 크기만 보고 “8GB니까 262K context도 되겠네”로 직진하면 바로 터집니다. weight는 5.95GB까지 내려왔지만 KV cache, 런타임 버퍼, 그래프/커널 워크스페이스, (멀티모달이면) mmproj까지 합치면 8GB는 매우 타이트합니다. mmproj 자체도 Q8_0 기준 0.63GB로 작지 않습니다.[^3]

이 모델 카드가 제공하는 packing은 두 가지입니다.

- PTQ1_0: trit를 dense packing, 5.95GB, 1.75 bits/weight
- PQ2_0: trit를 2-bit slot에 저장, 7.21GB, 2.13 bits/weight

그리고 “둘 중 어느 게 더 빠른가”도 GPU 세대별로 갈립니다. 즉, footprint/속도 선택을 런타임의 unpack 비용과 GPU의 메모리 대역/연산 비율로 다시 해야 합니다.[^3]

## ternary + Hadamard rotation이 추론을 바꾸는 지점: ‘정확도 저하’가 아니라 ‘실패 형태’가 달라진다

Bonsai 2 27B의 weight 표현은 “각 weight는 {−1,0,+1}”이고, 128개 weight 그룹마다 공유 FP16 scale을 둡니다. 여기까지만 보면 BitNet b1.58 류의 ternary weight 서사와 비슷해 보이는데, Hugging Face 모델 카드가 강조하는 차별점은 “rotated basis”입니다. 각 matrix를 blockwise orthogonal Hadamard rotation으로 변환한 뒤 ternary assignment를 하고, 런타임은 activations에 매칭 transform을 적용합니다. packed 모델은 이 rotation을 metadata로 선언하고, 런타임이 이를 적용하지 못하면 로드를 거부하거나(또는 잘못된 런타임이면 garbage)로 이어질 수 있습니다.[^3]

이 설계는 전형적인 PTQ(Q4/Q3)와 다른 실패 패턴을 만듭니다.

### 1) reasoning mode에서 ‘길어지는 추론’이 오히려 취약점을 증폭한다

PrismML은 “thinking mode 벤치마크 평균”으로 FP16 대비 98.2%를 주장합니다. 같은 페이지에서 conventional low-bit(Qwen3.8-27B IQ2_XXS)의 붕괴는 reasoning이 길어지는 벤치에서 선택적으로 발생한다고 적어두었고, AIME26·LiveCodeBench 같은 sustained reasoning 계열에서 점수가 크게 깨진다고 예를 듭니다.[^3]

이 문장을 운영 관점으로 번역하면 다음과 같습니다.

- “짧은 질의응답”에서는 괜찮아 보이는데
- chain-of-thought가 길어지고, tool call/코드 생성처럼 중간 상태를 유지해야 할수록
- quantization noise나 누적 오차가 **토큰 단위로 증폭**되면서
- 실패가 ‘약간 덜 똑똑함’이 아니라 ‘갑자기 이상한 모드로 들어감’으로 나타날 확률이 올라갑니다.

특히 로컬 운영에서는 reasoning mode를 켜서 품질을 뽑아야 하는 경우가 많습니다. 클라우드 API는 “모델이 틀리면 재시도/앙상블”을 돈으로 해결할 수 있지만, 로컬은 1-shot 성공률이 중요해지는 경향이 있고, 그때 reasoning이 길어지면 loop·형식 붕괴의 리스크가 커집니다.

### 2) token loop / coherence bug는 ‘샘플링 튜닝’으로만 설명되지 않는다

Hugging Face에 올라온 파생 GGUF(dealignai) 모델 카드에는, 2026-09-17 20:44 PDT(=2026-09-18 03:44 UTC)에 “reasoning mode(low/xhigh)에서 coherence bug가 있었고 token loop를 유발할 수 있으니 재다운로드” 공지가 박혀 있습니다. 이것은 단순히 temperature/top-p를 잘못 준 수준이 아니라, 빌드/체크포인트/런타임 조합에서 특정 모드가 깨질 수 있음을 보여줍니다.[^4]

또한 PrismML 공식 모델 카드에서도 “`low` reasoning effort는 지원하지 않으며, 선택해도 `xhigh`에 가깝게 동작한다”라고 못 박습니다. 운영자가 UI에서 reasoning level을 3단계로 노출해놓고 low로 내려서 latency를 줄이려는 시도를 하면, 기대와 실제 동작이 엇갈립니다. 이 엇갈림이 품질 문제로만 끝나면 다행인데, “모드 전환이 애매한 상태”가 되면 모델이 더 불안정해질 수 있습니다(경험적으로 reasoning prompt가 흔들릴수록 self-consistency가 떨어지는 계열이 많았습니다).[^3]

### 3) ternary는 logit margin을 얇게 만들고, 얇아진 margin은 ‘형식 준수’부터 먼저 무너진다

ternary weight는 표현력 여유가 적습니다. 회전/스케일링으로 최대한 정보를 보존하더라도, 모델이 원래 갖고 있던 “정답 토큰과 차선 토큰의 logit 차이(logit margin)”가 작은 구간에서는 작은 잡음이 토큰 선택을 바꿉니다. reasoning mode는 토큰을 많이 내뱉기 때문에, 한 번의 토큰 선택이 다음 상태를 바꾸고, 다음 상태가 또 취약해지는 연쇄가 생깁니다.

운영에서 이 현상은 대개 아래 순서로 드러납니다.

1) JSON/tool-call format이 처음으로 흔들림
2) 코드 생성에서 괄호/indentation 같은 구조적 제약이 먼저 깨짐
3) “이미 충분히 했습니다”류의 종료 신호를 반복하거나, 같은 문장을 변주 없이 되풀이
4) 장문에서 주어/목적어가 바뀌며 문맥 drift

단순 Q4 대비 reasoning 점수 몇 점 차이로는 이 현상을 설명하기 어렵고, “실패 패턴을 관측·완화하는 운영 장치”가 필요해집니다.

## 8GB VRAM/메모리 예산에서의 서빙 토폴로지: 로컬 앱, 온프렘, 브라우저를 구분해야 한다

8GB급 VRAM이라는 말은 실제로 서로 다른 3가지 상황을 뭉개서 부르는 경우가 많습니다.

- (A) 단일 dGPU 8GB(예: RTX 4060 8GB 등) + 시스템 RAM 32~64GB
- (B) iGPU/UMA(Apple Silicon 8~16GB unified memory)
- (C) 브라우저 WebGPU: (A)나 (B) 위에서 브라우저가 GPU를 공유하며, 추가 제약(메모리 할당/보안 샌드박스/커널 제어권 제한)을 받는 환경

Bonsai 2 27B는 (A)/(B)에서 “커스텀 커널/런타임”으로 겨우 운영권에 들어왔고, (C)는 별도의 이야기입니다. PrismML 공식 글은 CUDA와 MLX를 platform coverage로 적고 있고, WebGPU를 first-party로 언급하지 않습니다.[^2]

### 8GB VRAM에서 weight만 올리는 건 쉽고, KV cache가 진짜 적이다

모델 카드 기준 언어 모델 본체는 PTQ1_0가 5.95GB입니다. 여기에 다음이 추가됩니다.[^3]

- (옵션) mmproj Q8_0: 0.63GB
- KV cache: context 길이에 비례해서 증가
- 런타임 워크스페이스/그래프/allocator fragmentation

8GB VRAM에서 PTQ1_0(5.95GB)를 올리고 나면, 남는 VRAM은 “대략 2GB 전후”인데, 이 안에 KV cache가 들어가야 합니다. 결국 8GB급에서의 현실적인 운영은 아래 중 하나로 수렴합니다.

- context를 짧게(예: 4K~16K) 유지하고, 대신 retrieval을 aggressively 하거나
- KV cache를 더 낮은 precision으로 저장(런타임 옵션)해서 context를 늘리거나
- KV는 host RAM으로 밀어내고(성능 하락) “돌아가기만” 하는 구성을 택하거나
- 아예 이 모델은 “인터랙티브 단발”로만 쓰고, 긴 문서는 더 큰 서버로 보냄

내 경우, “27B를 8GB에 넣는다”는 목표를 잡는 순간, 실제 목표는 “KV cache 예산을 설계한다”로 바뀌었습니다. weight가 5.9GB가 됐다고 262K context가 공짜로 생기지 않습니다. (이 주제는 내가 이전에 쓴 [Quantization + KV cache + 커널/런타임 최적화 실전 가이드](https://daewooki.github.io/posts/gpu-llm-2026-7-quantization-kv-cache-2/)에서 더 길게 다뤘고, 여기서는 Bonsai 2 27B의 특수성을 중심으로만 정리합니다.)

### PTQ1_0 vs PQ2_0: 8GB에서는 ‘대부분 PTQ1_0’인데, 속도는 GPU 세대별로 다르다

모델 카드의 권장에 따르면 PQ2_0는 H100/A100/Blackwell 계열에서 decode가 빠르고, PTQ1_0는 Ada(L4 포함)에서 decode가 빠르며, 메모리가 가장 타이트할 때 PTQ1_0가 우선 선택입니다. 8GB 소비자 GPU는 대부분 Ada 계열로 묶이는 경우가 많아서, 결과적으로 “PTQ1_0로 가는 게 맞는” 케이스가 많습니다.[^3]

다만 운영에서 중요한 건 ‘내 GPU에서의 tg(decode)와 pp(prefill)’입니다. Bonsai 2 27B 모델 카드는 tg128/pp512를 분리해 테이블로 제공합니다. tg128이 interactive decode throughput이고, pp512가 긴 프롬프트 처리(prefill) 처리량입니다.[^3]

예를 들어 RTX 4090에서는 PTQ1_0가 tg128이 더 높고(91.1 vs 81.2), pp512는 PQ2_0가 훨씬 높습니다(3124 vs 1645). 즉 “대화형 응답 속도만” 보면 PTQ1_0가 유리하고, “긴 문서 넣고 요약”은 PQ2_0가 유리한 구도가 나옵니다.[^3]

이 구조가 8GB급에서 더 까다로운 이유는, 긴 문서/긴 컨텍스트를 하려면 KV cache까지 커지고, 그러면 PQ2_0의 7.21GB는 weight만으로도 벽에 가깝습니다. 즉 8GB급에서 실전은 보통 다음으로 정리됩니다.

- **대화형(짧은 컨텍스트) + 빠른 decode**: PTQ1_0
- 프롬프트가 긴 워크플로(코드베이스/문서 투입): “8GB에서는 애초에 어렵다” 쪽으로 결론

### 온프렘 서빙: ‘작아진 덕분에’ 멀티테넌시가 쉬워질 거라는 기대가 가장 위험하다

Bonsai 2 27B가 5.9GB가 되면, 사람들은 바로 “그럼 한 GPU에 여러 모델을 같이 띄우자”로 갑니다. 이건 절반만 맞습니다.

- weight만 보면 co-resident가 가능해 보이지만
- 실제로는 KV cache가 request별로 늘어나고
- reasoning mode는 출력 토큰이 길어지며 KV가 더 빨리 찹니다.

결국 멀티테넌시의 병목은 VRAM 총량이 아니라, “최악 케이스의 KV 폭주를 어떻게 막느냐”가 됩니다. 나는 이런 경우, 처음부터 ‘모델을 많이 띄우는 구조’보다 ‘요청을 얇게 자르는 구조’를 먼저 설계합니다.

- per-request max_new_tokens 상한
- reasoning budget 상한(가능한 런타임에서)
- tool call은 JSON schema validator로 early reject
- loop detector로 mid-stream abort

이건 성능 최적화가 아니라, 운영 안정성입니다.

### 브라우저(WebGPU): 지금 시점에서 Bonsai 2 27B는 “가능할 수도”가 아니라 “제품화하기 어렵다”에 가깝다

WebGPU 쪽은 기대가 과열되기 쉬운데, Bonsai 2 27B의 핵심은 “ternary + Hadamard rotation + custom kernels”입니다. WebLLM은 WebGPU 기반 브라우저 추론 엔진으로 잘 정리돼 있고(MLC/TVM 기반), 모델을 브라우저에서 돌리는 표준 경로 중 하나입니다. 다만 WebLLM이 전제하는 모델 포맷/커널과 Bonsai 2 27B의 포크 llama.cpp 커널은 완전히 다른 세계입니다.[^5]

운영적으로 WebGPU에서 정말 해야 하는 질문은 “이 모델이 WebGPU에서 돌아가나”가 아니라 아래입니다.

- 브라우저 샌드박스에서 이 ternary kernel을 안전하게 배포할 수 있나
- 모델 다운로드(6~8GB)를 사용자 네트워크/캐시 정책에서 감당할 수 있나
- GPU 메모리 할당 실패/탭 크래시를 어떻게 복구할 건가
- 사용자 장치의 VRAM/드라이버/브라우저 버전을 어떻게 매트릭스로 테스트할 건가

WebLLM도 문서에서 ‘브라우저에서 로컬 추론’을 강하게 밀지만, 모델 크기/기기 등급을 나눠 라우팅하는 전략을 같이 가져갑니다. 27B를 브라우저로 “기본값”으로 두는 설계는, 데모는 돼도 제품 운영이 매우 어렵습니다.[^6]

## 속도와 전력: ‘작아서 빠르다’가 아니라 ‘병목이 메모리 대역으로 이동한다’가 포인트

PrismML 발표문과 모델 카드에서 반복되는 메시지는 “decode는 메모리 대역 지배”라는 점입니다. 모델 카드는 M5 Pro에서 decode가 weight streaming ~204 GB/s에 가깝다고 적습니다. 이 말은, 모델이 작아지면서 compute보다 메모리 트래픽이 상대적으로 더 큰 비중을 차지하고, 최적화 포인트가 바뀐다는 뜻입니다.[^3]

또한 PrismML 공식 발표는 RTX 5090에서 최대 143 tok/s, M5 Max에서 46.8 tok/s를 언급하고, RTX 4090에서 0.714 mWh/token 같은 에너지 지표도 제시합니다. 이런 수치들은 “내 환경에서 그대로 나온다”가 아니라, 어떤 형태의 최적화(커스텀 커널 포함)를 전제하는지 확인해야 합니다.[^2]

### PTQ1_0가 항상 빠르지 않은 이유: unpack arithmetic vs 메모리 트래픽

PTQ1_0는 trit를 촘촘히 packed해서 footprint를 줄였지만, 그만큼 unpack에 연산이 들어갑니다. 모델 카드의 Limitations는 이를 명시적으로 적어두고, Ampere/Hopper/Blackwell에선 batch-1 decode가 bandwidth-starved가 아닐 수 있어서 PTQ1_0가 느릴 수 있다고 말합니다. 즉, “작은 packing = 항상 빠름”이 아닙니다.[^3]

8GB급 소비자 GPU에서는 보통 메모리 대역이 넉넉하지 않아 decode가 bandwidth 병목으로 붙을 가능성이 높고, 그 경우 PTQ1_0가 유리해질 수 있습니다. 반대로 서버급 GPU나 상위 세대에서는 PQ2_0가 더 나을 수 있습니다. 이 판단을 감으로 하면 망하고, tg128/pp512를 둘 다 찍어봐야 합니다.

## DFlash2 같은 speculative decoding이 8GB급에서 의미가 생기는 지점

“모델이 작아졌다”가 의미를 갖는 순간은, 그 덕분에 speculative decoding(draft model)을 붙이는 토폴로지가 쉬워질 때입니다.

ProCreations가 공개한 Bonsai 2 27B DFlash2 draft 모델은, 원본 Qwen3.8 27B DFlash2 head를 Bonsai 2 PQ2_0 target에 맞춰 적응시킨 것으로, BF16 checkpoint/Q8_0 GGUF draft/패치된 native CUDA runtime/레시피/측정값을 포함한다고 설명합니다. 핵심은 speedup이 ‘엄청나게’가 아니라, 측정 조건이 명확히 박혀 있다는 점입니다.[^7]

- RTX PRO 6000 Blackwell 96GB에서
- no draft 138.4 tok/s → adapted DFlash2 179.2 tok/s (1.295x)
- max 5 draft tokens, context 32768, temperature 1/top-p 0.95/top-k 20 등 조건 명시

그리고 “짧은 컨텍스트의 finite-prefix speed 측정이지 correctness 보장이 아니다”라고 스스로 한계를 적어둡니다. 이 타입의 문서화가 실제 운영에서는 더 중요합니다. speedup을 믿는 게 아니라, “내 워크로드에서 acceptance가 나오는지”를 예측할 수 있는 정보를 주기 때문입니다.[^7]

8GB급에서 speculative decoding을 붙이는 건, VRAM 때문에 draft/target을 둘 다 GPU에 올리기 어렵다는 문제가 있습니다. 그래서 실제로는 다음 중 하나가 됩니다.

- (온프렘) target은 GPU, draft는 CPU(혹은 더 작은 GPU)
- (로컬) draft를 아주 작은 모델로 바꾸고 acceptance를 포기하거나
- (브라우저) speculative 자체는 더 어렵고, 오히려 서버로 뺍니다.

즉 “로컬 27B”가 열어준 건, 단일 모델을 띄우는 게 끝이 아니라, speculative/guardrail 같은 운영 장치를 붙일 수 있는 설계 공간이 넓어진 쪽입니다.

## ternary/저비트가 reasoning에서 만드는 실패 패턴: 실전에서 자주 밟는 것들

여기서부터는 “벤치 점수”가 아니라 운영 중 실제로 문제가 되는 패턴을 기준으로 정리합니다. (특정 케이스는 커뮤니티에서 공유된 빌드 이슈도 섞여 있고, 내 경험상 저비트 계열에서 반복되는 형태라서, 모델/런타임 버전에 따라 정도가 달라질 수 있습니다.)

### 1) 무한 반복(loop): 종료 조건이 아니라 ‘상태 붕괴’다

dealignai의 모델 카드에 token loop를 유발하는 coherence bug 공지가 있었던 것처럼, loop는 단순 샘플링 과열이 아니라 런타임/빌드/모드 조합에서 촉발될 수 있습니다.[^4]

운영에서 loop는 다음의 “탐지 가능 시그널”이 있습니다.

- 동일 n-gram 반복률 급증
- 문장 길이가 줄지 않고 같은 문장 패턴이 재생산
- tool call이 같은 payload로 계속 재시도
- “I have everything I need”류의 메타 문장 반복

loop를 “temperature를 낮추면 된다”로 퉁치면, 실제로는 더 나빠질 때가 있습니다. logit margin이 얇아진 모델에서 temperature를 0에 가깝게 만들면, 잘못된 국소 최적(같은 토큰 패턴)에 더 강하게 고정되는 경우가 있습니다. 결국 해결책은 샘플링 하나가 아니라, 아래를 같이 가져가야 합니다.

- mid-stream loop detector로 early abort
- abort 시, 동일 prompt로 retry하지 않고 prompt를 바꾸거나(예: 출력 형식 재지정) 상위 모델로 escalation
- tool call에는 idempotency key와 retry budget을 둠

### 2) reasoning 길이가 길어질수록 ‘정답률’이 아니라 ‘형식 준수율’이 먼저 깎인다

Bonsai 2 27B 모델 카드가 제시하는 수치에서 흥미로운 점은, math/coding 평균은 크게 안 떨어지는데(예: Math 97.06→96.57, Coding 89.07→89.42), Knowledge & reasoning/ Vision 쪽에서 차이가 더 납니다. 이건 “틀린다/맞는다”로만 보면 애매하고, 실제 제품에서는 “요구한 형식을 끝까지 유지하냐”가 더 먼저 문제가 됩니다.[^3]

나는 저비트 모델을 운영에 올릴 때, 품질 지표를 ‘정답률’보다 먼저 아래로 잡습니다.

- JSON schema 준수율
- 코드 컴파일/테스트 통과율
- tool call 계획 → 실행 → 반영의 멀티턴 성공률
- 정해둔 길이/예산 안에서 결론까지 도달하는 비율

이게 reasoning 모델에서는 특히 중요합니다. reasoning을 길게 쓰는 모델은 정답이라도 길게 가는 경향이 있고, 그 자체가 KV/시간/비용을 폭발시킵니다.

### 3) 긴 컨텍스트에서의 drift: “262K 지원”과 “262K를 운영”은 다르다

PrismML은 262K-token context를 지원한다고 적습니다.[^2]

하지만 8GB급 VRAM에서 262K를 실제로 운영할 수 있는지는 전혀 다른 문제입니다. 긴 컨텍스트는 (1) KV cache 예산, (2) prefill 시간, (3) long-horizon coherence를 동시에 요구합니다. weight가 작아져도 KV는 길이에 비례하고, prefill은 토큰 수에 비례합니다. 실제로 모델 카드도 Apple M4 Pro에서는 decode보다 prefill이 실질적 한계라고 적습니다.[^3]

운영에서 긴 컨텍스트가 필요한 워크플로(문서 분석, 리포지토리 전체 질의, 장시간 agent loop)는 8GB 단일 GPU에서 “그냥 된다”가 아니라, 아래 중 하나로 설계가 갈립니다.

- retrieval + 요약으로 working set을 줄여서 짧은 컨텍스트를 반복
- long context는 큰 GPU(혹은 클라우드)로 보내고, 8GB 로컬은 인터랙션/보조 역할
- long context 자체를 포기하고 “로컬에서 가능한 일”의 스코프를 명확히 제한

## 8GB급에서의 현실적인 배포 구성: 내가 잡는 기준선

### 1) 로컬 앱(개발자용/개인용): 단일 사용자, 짧은 컨텍스트, 빠른 응답

- 모델: PTQ1_0 우선
- 멀티모달: 8GB에서는 mmproj를 올리는 순간 매우 불안정해질 수 있으니(메모리) 스코프를 분리
- 모드: `medium` reasoning을 기본으로 두고, `xhigh`는 “정말 필요할 때만”

여기서 가장 중요한 운영 포인트는 “가끔 멈추는/루프 도는” 상황을 UX로 받아낼 수 있느냐입니다. 로컬 앱은 장애를 사람이 직접 보고 재시도할 수 있어서 그나마 낫습니다.

### 2) 온프렘(팀 공용): 동시성 제어가 곧 안정성

- 모델을 작게 만든 만큼, 단일 GPU에 동시 요청을 많이 넣고 싶어집니다.
- 그러나 reasoning 모델은 요청마다 토큰 예산이 들쭉날쭉하고, KV가 request-local로 터집니다.

그래서 나는 아래를 기본값으로 둡니다.

- concurrency를 올리기 전에 “요청당 토큰 상한”을 먼저 고정
- server에서 stream 출력 중 loop/형식 붕괴 탐지 시 즉시 종료
- 종료된 요청은 동일 프롬프트 자동 재시도 금지(폭주 방지)

그리고 “로컬 27B”를 쓰는 이유가 비용이라면, 실패했을 때의 fallback이 더 중요해집니다.

- fallback은 같은 모델 다른 quant(Q4)로 가는 게 아니라, “다른 모델/다른 백엔드”로 가야 안정적으로 개선됩니다.

### 3) 브라우저(WebGPU): 모델을 브라우저로 넣는 게 아니라, 브라우저를 ‘클라이언트’로 보는 쪽이 더 현실적

WebLLM은 브라우저에서 로컬 추론을 가능하게 하는 정석 경로 중 하나고, WebGPU 기반으로 동작합니다.[^6]

하지만 Bonsai 2 27B는 llama.cpp 포크의 커스텀 ternary 커널을 요구합니다.[^3]

그래서 2026-09-21 KST 시점에서 “제품 운영” 관점의 WebGPU 토폴로지는 대부분 아래로 수렴합니다.

- 브라우저는 UI/에이전트 프런트만 담당
- 추론은 로컬/온프렘 서버(동일 LAN)로 보내서 GPU에서 처리
- 민감 데이터가 브라우저에 남아야 한다면, “브라우저 안에서 27B”가 아니라 “브라우저 안에서 작은 모델 + 서버에서 큰 모델”로 역할을 분리

브라우저에서 6~8GB 모델을 내려받아 실행하는 건, 네트워크/캐시/메모리/크래시 복구까지 포함한 제품 역량이 필요합니다. 이건 연구/데모와 운영의 경계가 확실히 갈리는 지점입니다.

## 동일 프롬프트에서 fp16/Q4 대비 품질 저하를 ‘팀이 합의 가능한 지표’로 만드는 방법

벤치마크 점수는 참고값입니다. 실제 도입 결정은 “우리 팀의 업무에서, 실패했을 때 비용이 큰가”로 갈립니다. 그래서 지표를 팀 합의로 만들려면, 모델 평가를 아래 세 층으로 분해하는 게 효과가 좋았습니다.

### Layer 1: 형식 준수/안정성(운영 지표)

- JSON schema 준수율
- tool call 재시도 횟수(또는 재시도 없이 성공률)
- loop 발생률(탐지 규칙 기반)
- time-to-first-token, tokens/sec(가능하면)

이 레이어는 품질이라기보다 운영 안정성입니다. ternary/저비트의 손해는 여기서 먼저 터집니다.

### Layer 2: 태스크 성공률(팀 업무 기반)

팀이 실제로 하는 일을 그대로 태스크로 만듭니다.

- “레거시 코드에 기능 추가 + 테스트 추가 + CI 통과”
- “SQL 쿼리 작성 + 결과 검증(샘플 데이터 포함)”
- “문서 요약 + 규정 체크리스트 채우기(정답 키 있음)”

중요한 포인트는 “정답 키”가 있는 태스크를 절반 이상 섞는 것입니다. 그렇지 않으면 평가가 감상평으로 흐릅니다.

### Layer 3: pairwise preference(사람 평가)

사람 평가는 필요합니다. 다만 방식을 고정해야 팀 합의로 변합니다.

- 동일 프롬프트
- 동일 시스템 프롬프트(또는 최소화)
- 동일 샘플링 파라미터
- 모델 이름을 가린 blind 리뷰
- 1~5점이 아니라 “A/B 중 누가 더 낫나 + 이유 한 줄” 정도로만

이렇게 하면 “벤치마크는 높다는데 왜 현업에서 별로지?” 같은 논쟁이 줄어듭니다.

### 실행 가능한 최소 평가 하네스: llama.cpp 서버(OpenAI 호환) + Python 스크립트

아래는 (1) Bonsai 2 27B를 실행하고, (2) OpenAI 호환 endpoint로 평가 스크립트를 돌리는 최소 구성입니다. 핵심은 ‘정확도’를 측정하기 전에, loop/형식 붕괴/시간 폭주 같은 운영 실패를 먼저 잡는 것입니다.

#### 1) PrismML-Eng/llama.cpp 포크 빌드 + 모델 다운로드

모델 카드가 “stock llama.cpp는 안 된다”고 못 박으므로 포크를 씁니다.[^3]

```bash
# Ubuntu 22.04 기준 예시
# CUDA는 설치돼 있다고 가정합니다.

sudo apt-get update
sudo apt-get install -y git cmake build-essential

git clone https://github.com/PrismML-Eng/llama.cpp
cd llama.cpp

cmake -B build -DGGML_CUDA=ON
cmake --build build -j

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install huggingface_hub==0.25.1

mkdir -p ../models/bonsai2

# 8GB VRAM이면 PTQ1_0부터 시작하는 쪽이 안전합니다.
# (파일명은 모델 카드의 Shipped Components에 맞춰 선택)
# PTQ1_0: 5.95 GB, PQ2_0: 7.21 GB
hf download prism-ml/Ternary-Bonsai-2-27B-gguf \
  Ternary-Bonsai-2-27B-PTQ1_0.gguf \
  --local-dir ../models/bonsai2

ls -lh ../models/bonsai2
```

예상 출력(환경에 따라 달라질 수 있습니다):

```text
-rw-r--r-- 1 user user 6.0G ... Ternary-Bonsai-2-27B-PTQ1_0.gguf
```

#### 2) 단발 실행으로 “정상 출력” 먼저 확인

모델 카드 Quickstart에 준하는 형태로, 먼저 `llama-cli`로 확인합니다.[^3]

```bash
./build/bin/llama-cli \
  -m ../models/bonsai2/Ternary-Bonsai-2-27B-PTQ1_0.gguf \
  -ngl 99 -fa on -c 8192 \
  --temp 1.0 --top-p 0.95 --top-k 20 \
  -p "You are a helpful assistant.\n\nExplain the trade-offs of ternary quantization for reasoning models." \
  -n 256
```

여기서 보는 체크포인트는 단순합니다.

- 출력이 ‘말이 되는 문장’인가(garbage 여부)
- 첫 토큰이 지나치게 늦지 않은가(TTFT)
- 반복/루프 조짐이 있는가

8GB에서 `-c 32768` 같은 큰 값을 바로 넣는 건 추천하지 않습니다. 성공/실패가 “품질”이 아니라 “메모리 초과/스왑/드라이버 리셋”으로 갈 수 있습니다.

#### 3) 서버로 띄우고 평가 스크립트에서 호출

llama.cpp 서버 실행 예시(옵션은 버전에 따라 다를 수 있습니다):

```bash
./build/bin/llama-server \
  -m ../models/bonsai2/Ternary-Bonsai-2-27B-PTQ1_0.gguf \
  -ngl 99 -c 8192 \
  --host 127.0.0.1 --port 8080
```

Python 평가 스크립트는 OpenAI SDK를 사용하면 간단합니다.

```bash
python -m pip install openai==1.40.0 pydantic==2.8.2
```

```python
# eval_bonsai2.py
import json
import re
import time
from typing import List, Dict

from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="local")

PROMPTS: List[Dict] = [
    {
        "id": "json_tool_call",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": (
                    "Return ONLY valid JSON. No markdown.\n"
                    "Schema: {\"action\": string, \"items\": [string], \"risk\": 0|1|2}.\n"
                    "Task: action=\"triage\", items must contain 3 concise failure modes of low-bit reasoning models."
                ),
            },
        ],
        "expect_json": True,
    },
    {
        "id": "loop_prone",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": (
                    "Write a 12-step debugging plan for a CUDA kernel that produces NaNs only on batch=1. "
                    "Each step must start with 'Step N:' and be non-redundant."
                ),
            },
        ],
        "expect_json": False,
    },
]

def looks_like_loop(text: str) -> bool:
    # 매우 단순한 loop detector (운영에서는 토큰 단위/스트림 단위로 더 촘촘히 잡는 편이 좋습니다)
    # 1) 같은 문장(마침표 기준)이 3번 이상 반복
    sents = [s.strip() for s in re.split(r"[\n\.]+", text) if s.strip()]
    if len(sents) >= 6:
        tail = sents[-6:]
        if len(set(tail)) <= 2:
            return True

    # 2) 5-gram 반복률
    words = re.findall(r"\w+", text.lower())
    if len(words) < 80:
        return False
    n = 5
    grams = [" ".join(words[i:i+n]) for i in range(len(words)-n+1)]
    uniq = len(set(grams))
    rep_ratio = 1.0 - (uniq / max(1, len(grams)))
    return rep_ratio > 0.35

def try_parse_json(text: str):
    # 모델이 여분 텍스트를 붙이는 경우가 있어, 앞뒤 공백 제거 후 1차 파싱
    t = text.strip()
    return json.loads(t)

def run_case(case: Dict) -> Dict:
    t0 = time.time()
    resp = client.chat.completions.create(
        model="local",  # llama.cpp 서버의 기본 모델 이름을 사용(환경에 따라 다를 수 있습니다)
        messages=case["messages"],
        temperature=1.0,
        top_p=0.95,
    )
    dt = time.time() - t0

    text = resp.choices[0].message.content or ""

    result = {
        "id": case["id"],
        "latency_sec": round(dt, 3),
        "chars": len(text),
        "loop": looks_like_loop(text),
        "raw": text,
    }

    if case.get("expect_json"):
        try:
            obj = try_parse_json(text)
            result["json_ok"] = True
            result["json_keys"] = sorted(list(obj.keys())) if isinstance(obj, dict) else None
        except Exception as e:
            result["json_ok"] = False
            result["json_error"] = str(e)

    return result

def main():
    out = []
    for case in PROMPTS:
        out.append(run_case(case))

    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

실행:

```bash
python eval_bonsai2.py | tee report.json
```

이 결과로 팀 합의를 만들 때는, 단순히 “Bonsai가 JSON을 잘 맞추네/못 맞추네”가 아니라 아래처럼 문장을 바꿔야 합니다.

- “우리 운영에서 허용 가능한 JSON 실패율은 1% 미만이다.”
- “loop detector로 잘리는 비율이 0.5%를 넘으면, 자동화 워크플로에는 넣지 않는다.”

이런 합의가 있어야 fp16/Q4 대비 저하를 ‘감정’이 아니라 ‘정책’으로 바꿀 수 있습니다.

## 운영 함정 체크리스트: 모델 파일보다 런타임이 더 중요해지는 구간

### 1) 잘못된 런타임에서 ‘조용히 망가지는’ 위험

PrismML 모델 카드는 “stock llama.cpp가 Q2_0를 경고 없이 로드하고 garbage를 만든다”고 명시합니다. 이건 배포 파이프라인에서 반드시 막아야 합니다.[^3]

내가 권하는 방어선은 아래입니다.

- 모델 파일/런타임 바이너리를 같이 묶어서 배포(버전 매트릭스 고정)
- “정상 출력 스모크 테스트”를 CI에 넣기(위의 `llama-cli` 단발 실행 같은 것)
- 로딩 시점에 모델 metadata(회전 여부, quant type)를 읽고 런타임이 거부하도록 만들기

### 2) reasoning effort UI/옵션이 제품에서 오히려 사고 지점이 된다

모델 카드가 `low` reasoning effort 미지원/실질적으로 `xhigh`에 가깝다고 말하는 순간, 제품 UI에서 low/medium/high 토글을 그대로 노출하면 “사용자는 속도 낮추려고 했는데 비용만 늘어난다” 같은 장애가 생깁니다.[^3]

이런 모델은 차라리 제품에서 reasoning 레벨을 2단계로만 노출하고(예: medium/xhigh), low는 숨기는 쪽이 안정적입니다.

### 3) 8GB에서 멀티모달(mmproj)은 별도 제품으로 분리하는 게 낫다

mmproj가 0.63GB(Q8_0)라서 “그 정도면 같이 올리지”라고 생각하기 쉽지만, 8GB에서는 그 0.63GB가 사실상 KV cache 예산을 먹는 것과 같습니다. 멀티모달은 요청당 prefill도 늘어나고, long context 경향도 강합니다. 결국 8GB 단일 GPU에서 텍스트+비전까지 한 서버로 우겨 넣으면, 성능 문제가 아니라 안정성 문제가 됩니다.[^3]

## 도입 판단 기준: ‘8GB에서 27B’가 정답이 되는 경우와 아닌 경우

여기까지의 내용을 결론으로 압축하면 단순합니다.

- Bonsai 2 27B는 “작고 빠른” 모델이라기보다, **커스텀 커널/런타임을 전제로 ‘저비트에서 reasoning 붕괴를 덜 일으키도록’ 설계된 모델**입니다.[^3]
- 8GB에서의 성공은 weight가 아니라 KV cache 예산 설계에 달려 있습니다.
- 품질 평가는 벤치마크보다 “운영 실패(형식 붕괴/loop/폭주)”를 먼저 숫자로 만들어야 팀 합의가 됩니다.

내 기준으로는 아래 케이스에서 도입 가치가 큽니다.

- 로컬/온프렘에서 데이터가 나가면 안 되고, 8GB급 하드웨어라도 “돌아가야” 하는 경우
- tool-call/코드 생성이 있지만, 요청당 컨텍스트를 적극적으로 줄일 수 있는 워크플로
- 실패했을 때 fallback(상위 모델/클라우드)이 있고, 로컬은 캐시/초안/고빈도 질의 처리로 포지셔닝할 수 있는 경우

반대로 아래라면, 27B를 8GB에 억지로 올리는 순간 운영 비용이 더 커집니다.

- 긴 컨텍스트(수만 토큰)를 상시 요구
- 비전까지 포함한 멀티모달을 같은 서버에서 동시성 있게 운영
- loop/형식 붕괴가 곧바로 장애/비용으로 이어지는 완전 자동화 파이프라인(guardrail 없이는 위험)

8GB급에서 “27B가 돌아간다”는 사실은 이제 출발점이고, 실제 승부는 실패 패턴을 관찰하고 토폴로지를 설계하는 쪽에서 납니다.

## 참고 자료

- [PrismML 발표: PrismML Launches Bonsai 2 27B](https://prismml.com/news/prismml-launches-bonsai-2-27b)
- [PrismML 기술 글: Introducing Bonsai 2 27B](https://prismml.com/news/bonsai-2-27b)
- [Hugging Face 모델 카드: prism-ml/Ternary-Bonsai-2-27B-gguf](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf)
- [Hugging Face 모델 카드: ProCreations/Ternary-Bonsai-2-27B-DFlash2](https://huggingface.co/ProCreations/Ternary-Bonsai-2-27B-DFlash2)
- [Hugging Face 모델 카드: dealignai/Bonsai-2-27B-Ternary-CRACK-GGUF](https://huggingface.co/dealignai/Bonsai-2-27B-Ternary-CRACK-GGUF)
- [WebLLM 문서: Local Inference](https://webllm.io/docs/guides/local-inference/)
- [WebLLM GitHub: mlc-ai/web-llm](https://github.com/mlc-ai/web-llm)
- [논문: WebLLM: A High-Performance In-Browser LLM Inference Engine](https://arxiv.org/abs/2412.15803)
- [논문: The Era of 1-bit LLMs: All Large Language Models are in 1.58 Bits](https://arxiv.org/abs/2402.17764)
- [내 글: Quantization + KV cache + 커널/런타임 최적화 실전 가이드](https://daewooki.github.io/posts/gpu-llm-2026-7-quantization-kv-cache-2/)
- [내 글: Quantization & Inference Acceleration 실전 가이드](https://daewooki.github.io/posts/2026-8-gpu-llm-2-quantization-inference--1/)

[^1]: <https://prismml.com/news/prismml-launches-bonsai-2-27b>
[^2]: <https://prismml.com/news/bonsai-2-27b>
[^3]: <https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf>
[^4]: <https://huggingface.co/dealignai/Bonsai-2-27B-Ternary-CRACK-GGUF/blob/main/README.md>
[^5]: <https://github.com/mlc-ai/web-llm>
[^6]: <https://webllm.io/docs/guides/local-inference/>
[^7]: <https://huggingface.co/ProCreations/Ternary-Bonsai-2-27B-DFlash2?hardware=p100>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
