---
title: "“GPU 다음”을 노리는 한국 NPU와 공급망 병목: NVIDIA vs Rebellions vs FuriosaAI 트렌드 체크"
description: "2026년 7~8월로 넘어오며 AI 가속기 시장의 키워드는 “더 많은 GPU”가 아니라 “추론(inference) 효율 + 공급망 제약 회피”로 선명해지고 있습니다."
date: 2026-08-03 03:37:56 +0900
categories: [News, AI]
tags: [ai, news]
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
2026년 7~8월로 넘어오며 AI 가속기 시장의 키워드는 **“더 많은 GPU”**가 아니라 **“추론(inference) 효율 + 공급망 제약 회피”**로 선명해지고 있습니다. NVIDIA 중심의 데이터센터 GPU 증산 흐름 위에, 한국의 Rebellions·FuriosaAI가 **NPU + 소프트웨어 스택 + 서비스 형태(NPUaaS)**로 실사용 사례를 만들며 존재감을 키우는 구도가 보입니다.[^1]

---

## 📰 무슨 일이 있었나
- **NVIDIA 데이터센터 GPU 공급량 전망(2026)**: 시장 분석 관측치로, 2026년 NVIDIA 데이터센터 AI GPU 공급이 **약 820만 대** 수준으로 언급됩니다(장기적으로 2028년 1,240만 대 전망 포함). 즉, “GPU가 부족하다”가 여전하지만 동시에 **어떻게든 물량은 늘고 있는** 상황입니다.[^1]  
- **Rebellions: 2026년 6월 30일 SqueezeBits 인수 발표**  
  - Rebellions가 **AI inference 최적화** 기업 SqueezeBits를 인수했다고 공식 발표했습니다.  
  - 발표문에서 **vLLM 중심 워크숍/오픈소스 생태계**를 함께 키워왔고, NPU용 모델 압축 및 전용 소프트웨어를 공동 개발해왔다고 명시합니다. 하드웨어만이 아니라 **서빙 최적화(압축/런타임/툴체인)**까지 수직 통합하려는 행보입니다.[^2]  
- **Rebellions: 2026년 3월 30일 4억 달러 Pre-IPO + 시스템 제품군 공개**  
  - Pre-IPO 라운드에서 **4억 달러** 조달 및 **RebelRack / RebelPOD** 같은 시스템 단 제품군을 발표했습니다. 칩(“Rebel100” NPU, chiplet 기반)에서 끝나는 게 아니라 **“인프라로 납품”**하려는 패턴이 강화됩니다.[^3]  
- **FuriosaAI: 2026년 5월 27일 Broadcom과 차세대 inference 플랫폼 협력, RNGD 양산 언급**  
  - FuriosaAI는 Broadcom과 함께 **Ethernet scale-up / fabric**을 포함한 차세대 inference 플랫폼 협력을 공개했고, 자사 데이터센터 inference 칩 **RNGD가 mass production(양산)** 단계라고 밝혔습니다.[^4]  
- **FuriosaAI 실사용 사례(2026년 7월 15일 보도)**  
  - Upstage(및 Daum 운영 측)와 FuriosaAI가 협력해, Daum의 AI Summary 검색 기능에 **Upstage Solar LLM + FuriosaAI RNGD NPU**를 결합한 “상용 full-stack” 사례를 제시했다는 보도가 나왔습니다. “국산 소버린 AI 스택 상용”이라는 메시지 자체가 시장 공략 포인트입니다.[^5]  
- **공급망 이슈: CoWoS/HBM/패키징 병목이 계속 화두**  
  - 업계에서는 AI 수요가 웨이퍼뿐 아니라 **패키징(CoWoS)·HBM·툴/서브스트레이트** 등 후공정/부품까지 압박한다는 논의가 이어집니다. 이 맥락에서 “병목 자원을 덜 쓰는 추론 칩” 접근이 경제적으로 유리할 수 있다는 연구(2026년 7월 arXiv)도 공개됐습니다.[^6]

---

## 🔍 왜 중요한가
실무 개발자 관점에서 핵심은 “어떤 칩이 더 빠르냐”보다 **내 서비스의 배포 옵션과 비용/납기 리스크가 어떻게 바뀌냐**입니다.

1) **‘GPU = 정답’에서 ‘Inference 전용 가속기’로 선택지가 현실화**
- Rebellions가 SqueezeBits를 인수하며 강조한 건 단순 NPU 성능이 아니라 **inference 최적화(압축/서빙 프레임워크 접점)**입니다. 이 방향은 개발자에게 “CUDA 종속”만이 아니라 **vLLM 같은 서빙 레이어에서의 최적화 전쟁**이 커진다는 신호입니다.[^2]  
- FuriosaAI도 RNGD 양산과 함께 네트워크/패브릭까지 묶는 플랫폼을 이야기합니다. 즉, 앞으로는 **칩 + 컴파일러/런타임 + 네트워킹 + 운영 형태(NPUaaS)**가 패키지로 들어오고, 개발자는 “모델을 어떻게 서빙 가능한 형태로 규격화할지”가 더 중요해집니다.[^4]  

2) **공급망 제약이 ‘기술 선택’에 직접 영향을 주는 국면**
- HBM/고급 패키징이 병목이면, 개발팀은 “성능 최상”만 보고 하드웨어를 결정했다가 **납기/가격/증설 실패**를 맞을 수 있습니다.  
- 2026년 7월 공개된 연구처럼, decode(특히 inference)의 경제성 관점에서 **HBM·CoWoS 같은 ‘rationed input’을 피하는 설계**가 전략적 우위가 될 수 있다는 주장도 나옵니다. 이건 실무적으로 “GPU가 없어서 못 한다”를 줄이는 또 하나의 길이 됩니다.[^6]  

3) **개발 워크플로우 변화: ‘커널 최적화’뿐 아니라 ‘서빙/압축/프로파일링’이 주 전장**
- GPU에서는 여전히 CUDA 커널 최적화가 중요하지만, 동시에 시장은 “서빙 스택(런타임/스케줄러/텐서 병렬화/압축)”을 더 큰 레버로 보고 있습니다(vLLM 중심 생태계 언급). 앞으로는 모델 아키텍처/프롬프트 설계만이 아니라 **quantization·KV cache 전략·batching 정책** 같은 운영 최적화가 경쟁력이 됩니다.[^2]  

---

## 💡 시사점과 전망
### 경쟁 구도 해석: “NVIDIA는 물량”, “NPU는 공급망 회피 + 수직통합”
- NVIDIA는 2026년에도 데이터센터 GPU 물량을 늘려가며 시장의 표준 지위를 유지하는 흐름으로 보입니다(공급 수치 전망).[^1]  
- 반면 Rebellions/FuriosaAI는 공통적으로 **“Inference 중심 + 시스템/플랫폼 + 소프트웨어 통합”**을 전면에 둡니다. 특히 Rebellions의 SqueezeBits 인수는 “칩이 아니라 **서빙 성능을 제품화**하겠다”는 선언에 가깝습니다.[^2]  

### 3~6개월 시나리오(2026년 8~2027년 1월 관점)
1) **‘상용 레퍼런스’ 경쟁이 더 격화**  
   - Daum AI Summary처럼 “실제 서비스에 들어갔다”는 케이스는 영업에서 강합니다. 비슷한 국내/아시아권 상용 사례가 추가로 나올 가능성이 큽니다.[^5]  
2) **NPUaaS/하이브리드(GPU+NPU) 운영이 확산**  
   - GPU는 학습/최대 성능, NPU는 대량 추론/비용 최적화로 역할 분담하는 형태가 늘 수 있습니다. (Rebellions가 하이브리드/멀티모달 추론 등 활용을 언급하는 맥락과 맞물립니다.)[^7]  
3) **회의론/리스크도 분명**  
   - NPU는 결국 “지원 모델/오퍼레이터 커버리지, 디버깅, 관측성(observability), 장애 대응” 같은 운영 성숙도가 관건입니다. 또 특정 NPU에 맞춘 최적화는 **벤더 락인**이 될 수 있고, GPU 생태계(CUDA) 대비 인력/툴링 풀이 얇을 가능성이 큽니다(이 부분은 각 사 SDK/커뮤니티 성숙도로 검증 필요).[^8]  

---

## 🚀 마무리
2026년 8월의 AI 가속기 트렌드는 “더 빠른 GPU”만이 아니라 **추론 최적화(소프트웨어) + 공급망 현실(패키징/HBM) + 시스템 단 제품화**로 이동하고 있습니다. Rebellions는 SqueezeBits 인수로 inference 소프트웨어 수직 통합을 강화했고, FuriosaAI는 RNGD 양산 및 상용 full-stack 사례로 “GPU 대안”을 실증하는 흐름을 만들고 있습니다.[^2]  

개발자가 지금 할 수 있는 액션 2가지:
1) **서빙 스택을 표준화**하세요: vLLM 등 “하드웨어가 바뀌어도 이식 가능한” 레이어를 중심으로, quantization/배치/캐시 정책을 코드와 실험으로 자산화합니다.[^2]  
2) **PoC를 ‘성능’이 아니라 ‘TCO+납기+운영’으로 평가**하세요: GPU/NPU 각각에 대해 latency, throughput뿐 아니라 전력, 장애 대응, 관측성, 모델 교체 주기까지 포함해 체크리스트로 비교해야 2026년형 리스크(공급망/비용 변동)에 덜 흔들립니다.[^6]

[^1]: <https://www.tomshardware.com/tech-industry/artificial-intelligence/google-could-build-more-ai-accelerators-than-nvidia-sells-in-2028-analyst-claims-could-push-the-company-to-use-intel-foundry-to-meet-its-goals>
[^2]: <https://rebellions.ai/newsroom/rebellions_squeezebits_acquisition_260630/>
[^3]: <https://rebellions.ai/newsroom/rebellions-closes-400-million-pre-ipo-and-launches-rebelrack-and-rebelpod-to-accelerate-global-expansion/>
[^4]: <https://furiosa.ai/blog/furiosaai-partners-with-broadcom-to-build-next-generation-inference-platform-for-the-agentic-era>
[^5]: <https://www.koreatimes.co.kr/amp/business/tech-science/20260715/upstage-furiosaai-team-up-to-power-daums-ai-search-with-homegrown-stack>
[^6]: <https://arxiv.org/abs/2607.13068>
[^7]: <https://kr.rebellions.ai/>
[^8]: <https://forums.furiosa.ai/>
