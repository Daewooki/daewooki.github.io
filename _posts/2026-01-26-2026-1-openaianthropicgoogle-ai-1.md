---
title: "애플·미성년자·모델 폐기까지: 2026년 1월 OpenAI·Anthropic·Google AI 업데이트가 말해주는 것"
date: 2026-01-26 02:31:51 +0900
categories: [AI, News]
tags: [ai, news, trend, 2026-01]
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
2026년 1월은 “모델 성능 경쟁”만큼이나 **정책(Policy)·플랫폼 정리·API 수명주기 관리**가 전면에 나온 달이었습니다. OpenAI는 약관/미성년자 보호 강화 흐름을, Anthropic은 Claude 브랜드/모델 세대교체를, Google은 Gemini API의 **deprecation(폐기)와 과금 전환**을 확실히 드러냈습니다. ([openai.com](https://openai.com/policies/terms-of-use/?utm_source=openai))

---

## 📰 무슨 일이 있었나
- **OpenAI**
  - **(2026-01-01)** OpenAI **Terms of Use**가 “Published: January 1, 2026 / Effective: January 1, 2026”로 게시되었습니다. 개인용 서비스(예: ChatGPT, DALL·E) 기준 Terms이며, 비즈니스/API는 별도 **Business Terms(Services Agreement)**로 안내됩니다. ([openai.com](https://openai.com/policies/terms-of-use/?utm_source=openai))
  - **(2026-01-22 보도)** ChatGPT에 **age prediction(나이 추정)** 기반 보호 기능을 도입해, 미성년자로 추정되면 민감 콘텐츠 노출을 제한하고, 오탐인 경우 **selfie로 age verification**해 복구하는 흐름이 보도됐습니다(글로벌 적용, EU는 몇 주 내 롤아웃 언급). ([theverge.com](https://www.theverge.com/news/864784/openai-chatgpt-age-prediction-restrictions-rollout?utm_source=openai))
  - **(2026-01-19 보도)** OpenAI가 **2026년 하반기 첫 디바이스** 공개를 목표로 한다는 내용이 나왔습니다(구체 스펙은 미공개). ([axios.com](https://www.axios.com/2026/01/19/openai-device-2026-lehane-jony-ive?utm_source=openai))

- **Anthropic**
  - **(2026-01-05)** Anthropic API에서 **Claude Opus 3 (claude-3-opus-20240229) retired**: 해당 모델 요청은 오류로 반환되며, **Claude Opus 4.5로 업그레이드 권고**가 명시됐습니다. ([releasebot.io](https://releasebot.io/updates/anthropic/anthropic-api?utm_source=openai))
  - **(2026-01-12, 2026-01-13 감지)** Claude Console이 **console.anthropic.com → platform.claude.com**으로 이동(리다이렉트 제공)했습니다. ([releasebot.io](https://releasebot.io/updates/anthropic/anthropic-api?utm_source=openai))
  - **(2026-01-12 효력)** Anthropic **Privacy Policy 업데이트**: (1) 미국 일부 주의 consumer health data 관련 법을 반영한 **Consumer Health Data Privacy Policy 링크 추가**, (2) 지역별 추가 고지를 Section 11로 통합. ([privacy.claude.com](https://privacy.claude.com/en/articles/10301952-updates-to-our-privacy-policy?utm_source=openai))
  - **(최근 공지, 1월 중 크롤)** Anthropic은 **Usage Policy 업데이트**에서 “high-risk use cases(예: healthcare 결정, legal guidance)”에 추가 안전 조치를 요구하고, 조건부로 **미성년자 대상 제품에 API 통합 허용** 범위를 확장한다고 밝혔습니다. ([anthropic.com](https://www.anthropic.com/news/updating-our-usage-policy?utm_source=openai))

- **Google (Gemini API)**
  - **(2026-01-05 시작)** Gemini 3에서 **Grounding with Google Search 과금**이 **2026-01-05**부터 시작된다고 changelog에 명시돼 있습니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/changelog?utm_source=openai))
  - **(2026-01-14)** `text-embedding-004` **shutdown(완전 종료)**. ([releasebot.io](https://releasebot.io/updates/google/gemini-api?utm_source=openai))
  - **(2026-01-15 예정/기재)** `gemini-2.5-flash-image-preview`는 **2026-01-15 shut down 예정**으로 공지됐습니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/changelog?utm_source=openai))
  - **(2025-12-18 업데이트된 deprecations 표)** `gemini-2.0-flash` 계열은 **Earliest February 2026** shutdown(최소 2026년 2월 이후 종료 가능)로 표기되며 대체 모델을 `gemini-2.5-flash` 계열로 안내합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/deprecations?utm_source=openai))
  - **(2026-01-12)** Gemini API에 **model lifecycle feature**(모델 lifecycle stage와 deprecation timeline 표기)가 추가됐다고 릴리즈 노트가 전합니다. ([releasebot.io](https://releasebot.io/updates/google/gemini-api?utm_source=openai))

---

## 🔍 왜 중요한가
1. **“정책/약관”이 곧 제품 기능이 됨**
   - OpenAI의 **age prediction + verification**은 단순한 안전 장치가 아니라, 서비스 경험(콘텐츠 필터), 인증 흐름, 그리고 규제(EU 등) 대응까지 포함한 **제품 설계 요소**가 됐습니다. 개발자 관점에선 “모델 호출”만큼이나 **사용자 연령/지역/리스크 레벨에 따른 UX 분기**가 필수가 됩니다. ([theverge.com](https://www.theverge.com/news/864784/openai-chatgpt-age-prediction-restrictions-rollout?utm_source=openai))

2. **모델 운영의 본질은 ‘수명주기 관리’**
   - Anthropic의 **Claude Opus 3 retired(2026-01-05)**처럼 “오래된 모델도 당분간 동작”하리라는 가정이 깨졌습니다. Google도 `text-embedding-004`를 **2026-01-14에 종료**했고, deprecations 표로 “언제든(earliest) shutdown 가능”을 명확히 합니다. 이제는 **버전 고정(pinning) + 대체 모델 테스트 + 마이그레이션 런북**이 운영의 기본입니다. ([releasebot.io](https://releasebot.io/updates/anthropic/anthropic-api?utm_source=openai))

3. **API 비용 구조가 ‘옵션 기능’에서 ‘필수 과금’으로 이동**
   - Gemini 3의 **Grounding with Google Search 과금(2026-01-05)**은, RAG/grounding이 “부가 기능”이 아니라 “핵심 품질 요소”가 되면서 비용이 제품 단가에 직접 반영되는 신호입니다. LLM 품질을 올리는 정석(검색 기반 근거/최신성 확보)이 곧바로 비용 상승으로 연결됩니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/changelog?utm_source=openai))

4. **플랫폼/브랜드 통합은 개발자 진입점까지 바꾼다**
   - Anthropic의 콘솔 도메인 이동(console → platform.claude.com)은 “문서 링크/온보딩/SSO/조직 관리” 같은 실무 동선을 흔듭니다. 작은 변화처럼 보여도, 내부 위키·Runbook·IaC·온보딩 문서가 한꺼번에 깨질 수 있습니다. ([releasebot.io](https://releasebot.io/updates/anthropic/anthropic-api?utm_source=openai))

---

## 💡 시사점과 전망
- **안전(특히 minors, high-risk) 요구사항은 2026년에 더 ‘제품화’될 가능성**
  - OpenAI는 미성년자 보호를 실제 기능(추정/검증/제한)으로 밀어붙였고, Anthropic은 high-risk use case에 추가 조치를 요구하며 정책을 촘촘히 했습니다. 결과적으로 “규제 대응”이 아니라 **B2C/B2B 모두의 기본 체크리스트**가 될 겁니다. ([theverge.com](https://www.theverge.com/news/864784/openai-chatgpt-age-prediction-restrictions-rollout?utm_source=openai))

- **‘모델 스위칭’이 잦아지며 멀티벤더 전략이 현실화**
  - Anthropic의 구형 Opus retire, Google의 embedding shutdown처럼, 특정 모델에 강결합하면 장애가 곧바로 서비스 장애로 이어집니다. 2026년에는 **fallback 모델/벤더**, **추상화 레이어**, **평가 자동화(Evals)**가 경쟁력의 일부가 됩니다. ([releasebot.io](https://releasebot.io/updates/anthropic/anthropic-api?utm_source=openai))

- **OpenAI는 “소프트웨어+서비스”에서 “디바이스”까지 확장 시도**
  - 2026년 하반기 디바이스 언급은, API 기업도 결국 **distribution(유통/채널)**을 원한다는 신호입니다. 개발자 생태계도 “앱/웹”뿐 아니라 **디바이스 기반 인터랙션(항상 켜진 마이크/센서/컨텍스트)**을 전제로 진화할 여지가 큽니다. ([axios.com](https://www.axios.com/2026/01/19/openai-device-2026-lehane-jony-ive?utm_source=openai))

---

## 🚀 마무리
2026년 1월 업데이트를 한 문장으로 요약하면, **“성능 경쟁의 다음 라운드는 정책·수명주기·과금·플랫폼 정리”**입니다. OpenAI는 Terms/미성년자 보호 흐름을 강화했고, Anthropic은 모델 세대교체와 Claude 플랫폼 통합을 진행했으며, Google은 Gemini API에서 shutdown/과금 전환과 lifecycle 표기를 통해 운영 규칙을 명확히 했습니다. ([openai.com](https://openai.com/policies/terms-of-use/?utm_source=openai))

개발자 권장 액션(바로 적용 가능한 것만):
- 프로덕션에서 **모델/임베딩 endpoint pinning** 여부 점검 + “shutdown 시나리오” 대응 런북 작성(대체 모델, 롤백, 품질 회귀 테스트). ([releasebot.io](https://releasebot.io/updates/google/gemini-api?utm_source=openai))  
- **정책(Usage/Privacy/Terms) 변경 모니터링**을 릴리즈 노트만큼 중요하게 운영(특히 minors, high-risk). ([theverge.com](https://www.theverge.com/news/864784/openai-chatgpt-age-prediction-restrictions-rollout?utm_source=openai))  
- Grounding/RAG 사용 중이면 **과금 전환(예: Google Search grounding)**을 제품 단가/요금제에 반영하고, 캐싱/쿼리 최적화로 비용을 통제. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/changelog?utm_source=openai))