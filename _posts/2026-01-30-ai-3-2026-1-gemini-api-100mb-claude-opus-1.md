---
title: "AI 빅3의 업데이트 총정리: Gemini API “100MB 파일 입력”, Claude Opus 3 은퇴, OpenAI 정책/안전 변화"
description: "2026년 1월은 “모델 성능 경쟁”보다 제품화·운영·정책(Compliance) 레이어가 빠르게 바뀐 달이었습니다."
date: 2026-01-30 02:41:18 +0900
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
2026년 1월은 “모델 성능 경쟁”보다 **제품화·운영·정책(Compliance) 레이어**가 빠르게 바뀐 달이었습니다. Google은 Gemini API의 데이터 인입(ingestion) 한계를 크게 넓혔고, Anthropic은 콘솔/모델 라인업을 정리했으며, OpenAI는 안전·정책 측면의 공지를 강화했습니다.[^1]

---

## 📰 무슨 일이 있었나
- **Google (Gemini API)**
  - (공식 changelog 기준) 2025년 12월 공지로, **Grounding with Google Search의 Gemini 3 billing이 2026년 1월 5일부터 시작**된다고 명시됐습니다. 즉 “검색 Grounding”이 기능뿐 아니라 **과금 항목으로 본격 운영** 단계에 들어갔다는 신호입니다.[^2]
  - (2026년 1월 12일 업데이트로 유통된 릴리즈 요약) Gemini API가 **입력 파일을 GCS/외부 URL(HTTPS, signed URL 포함)에서 직접 받는 흐름**을 지원하고, **inline payload 한도를 20MB → 100MB로 상향**했다는 업데이트가 공유됐습니다. 데이터 업로드/재업로드 비용을 줄이는 방향입니다.[^1]
  - 한편 EU는 2026년 1월 27일, Google이 DMA(디지털시장법) 하에서 **경쟁사에게 AI 서비스/데이터 접근을 공정하게 제공**하도록 하는 절차를 개시했다고 보도됐습니다(규제 리스크가 제품/사업 정책에 직접 영향).[^3]

- **Anthropic (Claude Developer Platform / 정책)**
  - 2026년 1월 5일, **Claude Opus 3 (`claude-3-opus-20240229`)가 retired**되어 해당 모델 호출은 에러를 반환하며, **Opus 4.5로 업그레이드 권고**가 공식 릴리즈 노트에 게시됐습니다.[^4]
  - 2026년 1월 12일, `console.anthropic.com`이 **`platform.claude.com`으로 redirect**되도록 바뀌었습니다(브랜드/개발자 콘솔 통합).[^4]
  - 또한 Anthropic은 **개인정보처리방침(Privacy Policy) 변경을 2026년 1월 12일부로 적용**하며, 미국 일부 주(consumer health data laws) 맥락의 **Consumer Health Data Privacy Policy 링크를 추가**했다고 밝혔습니다.[^5]

- **OpenAI (정책/안전 공지)**
  - 2026년 1월 12일, OpenAI는 **직원들이 안전/법/회사 정책 관련 이슈를 제기할 권리를 보호하는 ‘Raising Concerns Policy’ 공개**를 게시했습니다(거버넌스/컴플라이언스 메시지 강화).[^6]
  - 동시에 OpenAI는 Help Center를 통해 **Usage Policies를 통합·정리하고(Consolidated), 미성년자 보호 강화 등 방향성**을 안내했습니다(정책이 제품/빌더 운영에 더 직접적으로 연결되는 흐름).[^7]

---

## 🔍 왜 중요한가
- **“API 기능 업데이트”의 핵심이 모델이 아니라 ‘데이터 경로’로 이동**
  - Gemini API의 파일 입력 상향(20MB→100MB)과 GCS/URL 직접 입력은, 개발자 입장에서 **RAG/문서 기반 워크로드의 전처리·업로드 파이프라인을 단순화**합니다. 특히 signed URL/GCS object registration 패턴은 사내 스토리지와 LLM을 “느슨하게” 연결해 **데이터 이동 비용·운영 부담**을 줄이는 쪽으로 읽힙니다.[^1]
  - 동시에 Google은 Grounding with Google Search에 대해 **2026년 1월 5일부터 과금 시작**을 명시했기 때문에, “검색 Grounding을 켜면 품질이 좋아진다” 수준을 넘어 **비용 모델(단가/트래픽)까지 설계에 포함**해야 합니다.[^2]

- **Anthropic: “모델 은퇴”가 실서비스 장애로 직결**
  - Claude Opus 3가 2026년 1월 5일 retired되며 “호출 시 에러”로 바뀐 건, 운영 중인 서비스라면 **즉시 장애/성능 변화**로 이어질 수 있다는 뜻입니다. 릴리즈 노트에서 Opus 4.5 업그레이드를 명확히 권고하므로, 모델 버전 pinning을 해두었다면 **마이그레이션 플랜이 필수**입니다.[^4]
  - 콘솔 도메인 이동(redirect)은 사소해 보여도, SSO/허용 목록(allowlist)/내부 문서/온보딩 링크 등 **조직 단위 운영 자산**에 영향을 줍니다.[^4]

- **OpenAI: 정책/거버넌스가 제품만큼 ‘개발자 경험’이 됨**
  - OpenAI가 2026년 1월 12일 Raising Concerns Policy를 공개한 것은, 외부 개발자 API 스펙 변경이라기보다 **조직/안전 거버넌스 신뢰를 문서로 고정**하는 움직임입니다. 엔터프라이즈 도입에서 “기술”만큼 “리스크 관리”가 중요해진 현실을 반영합니다.[^6]
  - Usage Policies 통합/강화 흐름은, 결국 **프롬프트/콘텐츠 정책 준수, 모니터링, 차단/완화 로직**을 제품 설계에 내장해야 한다는 의미입니다. “나중에 약관 맞추지 뭐”가 점점 어려워집니다.[^7]

---

## 💡 시사점과 전망
- **경쟁 축이 “모델 성능” → “플랫폼 운영성(ingestion, grounding, policy)”로 이동**
  - Google은 입력·검색 결합을 강화하면서도 과금 체계를 명확히 하고, EU DMA 같은 규제 환경에서는 **접근/데이터 공유 요구**까지 맞닥뜨립니다. 결과적으로 2026년엔 “Gemini가 똑똑해졌다”보다 **어떤 데이터가 어떤 조건으로 들어가고, 얼마를 내는지**가 승부처가 될 가능성이 큽니다.[^3]
- **Anthropic은 제품/조직 재정렬 + 라인업 정리로 ‘상용 안정성’에 방점**
  - 콘솔 통합과 구형 모델 은퇴는, API 사업이 커질수록 불가피한 “정리 단계”입니다. 앞으로도 deprecated/retired 속도는 빨라질 수 있어, 개발팀은 **모델 교체를 전제로 한 아키텍처**(fallback, A/B, eval 자동화)를 갖추는 쪽이 안전합니다.[^4]
- **OpenAI는 ‘정책 문서’가 사실상 제품 스펙의 일부가 되는 흐름**
  - 특히 미성년자 보호 등 안전 영역은 기능/UX뿐 아니라 약관·정책·감사(audit)로 연결됩니다. 2026년에는 API 문서 못지않게 **policy 문서 업데이트 추적**이 중요해질 겁니다.[^7]

---

## 🚀 마무리
2026년 1월의 핵심은 세 가지입니다. (1) Google은 Gemini API의 **대용량 파일/외부 스토리지 입력**으로 “데이터 인입 DX”를 넓히는 동시에, **Search Grounding 과금(2026-01-05)**으로 비용 설계를 강제했습니다.[^1] (2) Anthropic은 **Claude Opus 3 은퇴(2026-01-05)**와 콘솔 통합(2026-01-12)으로 운영 표준화를 진행 중입니다.[^4] (3) OpenAI는 2026-01-12 **Raising Concerns Policy 공개** 및 Usage Policies 정비 흐름으로 거버넌스/정책 레이어를 강화했습니다.[^6]

개발자 권장 액션:
- 배포 중인 모든 LLM 호출에서 **모델 버전/엔드포인트 의존성 목록화** 후, retired/deprecation 모니터링을 CI 체크리스트로 넣기.[^4]  
- Gemini를 쓴다면 **Grounding 비용(2026-01-05 시작)**과 **대용량 파일 인입(100MB)**을 기준으로, RAG 파이프라인을 “업로드 중심”에서 “URL/GCS 참조 중심”으로 재설계 검토.[^2]  
- OpenAI/Anthropic 모두 정책 업데이트가 잦으니, 출시 노트뿐 아니라 **Usage/Privacy/Compliance 문서 변경 로그**를 정기적으로 추적(분기 1회면 늦을 수 있음).[^7]

[^1]: <https://releasebot.io/updates/google/gemini>
[^2]: <https://ai.google.dev/gemini-api/docs/changelog>
[^3]: <https://apnews.com/article/c39de40513a0f00dc8e71244e115e30a>
[^4]: <https://platform.claude.com/docs/en/release-notes/overview>
[^5]: <https://privacy.claude.com/en/articles/10301952-updates-to-our-privacy-policy>
[^6]: <https://openai.com/index/openai-raising-concerns-policy/>
[^7]: <https://help.openai.com/en/articles/12092907>
