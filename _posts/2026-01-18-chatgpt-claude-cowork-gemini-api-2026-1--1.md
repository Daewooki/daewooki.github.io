---
title: "ChatGPT에 광고, Claude는 “Cowork”, Gemini API는 대규모 파일·모델 정리 모드: 2026년 1월 빅테크 AI 업데이트 총정리"
date: 2026-01-18 02:29:01 +0900
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
2026년 1월 중순, OpenAI·Anthropic·Google이 각각 **수익화(ads), 에이전트/데스크톱 자동화, API 입력·모델 정책(폐기/과금)**을 중심으로 굵직한 업데이트를 연달아 내놓았습니다. 공통점은 “모델 성능 경쟁”을 넘어 **프로덕션 운영(비용/정책/마이그레이션)**이 개발자 의사결정의 핵심으로 이동하고 있다는 점입니다. ([openai.com](https://openai.com/index/our-approach-to-advertising-and-expanding-access//?utm_source=openai))

---

## 📰 무슨 일이 있었나
- **OpenAI (2026-01-16)**: OpenAI는 “ChatGPT 접근성 확대”와 함께 **미국에서 Free 및 ChatGPT Go 티어에 ads 테스트를 “향후 몇 주 내” 시작**한다고 밝혔습니다. 또한 **ChatGPT Go를 $8/월로 미국 및 ChatGPT 제공 지역에 확장**하고, **Plus/Pro/Business/Enterprise는 ad-free**로 유지한다고 명시했습니다. ([openai.com](https://openai.com/index/our-approach-to-advertising-and-expanding-access//?utm_source=openai))  
- **OpenAI API (2026-01-14, 01-13 등)**: OpenAI API Changelog 기준으로 **Responses API에 `gpt-5.2-codex`가 출시(2026-01-14)**됐고, `gpt-realtime-mini`, `gpt-audio-mini`, `sora-2`, `gpt-4o-mini-tts`, `gpt-4o-mini-transcribe` 등은 **slug가 특정 snapshot(예: 2025-12-15)으로 재지정**되는 업데이트가 있었습니다. 운영 환경에서 “같은 이름인데 동작이 바뀌는” 상황이 발생할 수 있음을 시사합니다. ([platform.openai.com](https://platform.openai.com/docs/changelog?utm_source=openai))

- **Anthropic (2026-01-13 전후)**: Anthropic은 macOS 앱에서 동작하는 연구 프리뷰 형태의 **“Claude Cowork”**를 공개했습니다. 로컬 폴더 접근 및 Asana/Notion 등 커넥터를 통해, 단순 채팅을 넘어 **데스크톱 업무를 병렬로 수행하는 에이전트형 워크플로우**를 지향합니다(단, 안전 이슈도 함께 경고). ([theverge.com](https://www.theverge.com/ai-artificial-intelligence/860730/anthropic-cowork-feature-ai-agents-claude-code?utm_source=openai))  
- **Anthropic API/정책 (2026-01-05, 01-12)**: Anthropic API 릴리즈 노트에는 **Claude Opus 3 (`claude-3-opus-20240229`)가 2026-01-05에 retire되어 요청이 error 처리**된다고 명시되어 있고, **대체로 Opus 4.5 업그레이드 권고**가 포함됩니다. ([releasebot.io](https://releasebot.io/updates/anthropic/anthropic-api?utm_source=openai))  
  또한 Privacy Policy 변경(효력 2026-01-12)에서 **Consumer Health Data Privacy Policy 링크 추가(미국 일부 주의 consumer health data 법을 전제로, Claude와 3rd-party health app 연동 시 적용)**가 언급됩니다. ([privacy.claude.com](https://privacy.claude.com/en/articles/10301952-updates-to-our-privacy-policy))  
  Usage Policy 업데이트에서는 **healthcare·legal guidance 등 high-risk use case에 추가 안전 조치 요구**, 그리고 **조직이 특정 조건을 충족하면 미성년자 대상 제품에 API를 포함할 수 있도록 허용 범위 확장**이 언급됩니다. ([anthropic.com](https://www.anthropic.com/news/updating-our-usage-policy))

- **Google Gemini API (2025-12~2026-01)**: Gemini API 공식 changelog에 따르면 **Grounding with Google Search “Gemini 3 billing”이 2026-01-05부터 시작**됩니다(즉, 1월부터 비용 구조가 달라짐). 또한 2025-12 공지로 **일부 모델 shutdown 일정(예: `text-embedding-004` 2026-01-14, `gemini-2.5-flash-image-preview` 2026-01-15)**이 명시되어 있어 1월이 “정리/마이그레이션”의 시점이었습니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/changelog))  
  별도로 Gemini API deprecations 문서에는 `gemini-2.0-flash` 계열이 **“Earliest February 2026”**에 shutdown될 수 있고, `gemini-2.5-pro`는 **`gemini-3-pro`로의 교체 권고**가 정리돼 있습니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/deprecations?utm_source=openai))

---

## 🔍 왜 중요한가
1) **“모델”보다 “플랜(티어/ads/과금/폐기)”이 더 자주 앱을 깨뜨린다**  
   OpenAI는 ChatGPT 레벨에서 ads를 테스트하며 수익화 축을 강화하고, Google은 Grounding 과금을 시작하며, Anthropic은 모델 retire를 실제로 실행했습니다. 이제 개발자는 “성능 비교”만이 아니라 **비용/정책/폐기 일정**을 릴리즈 노트 수준으로 상시 추적해야 합니다. ([openai.com](https://openai.com/index/our-approach-to-advertising-and-expanding-access//?utm_source=openai))

2) **API 운영 관점에서 ‘slug → snapshot’ 변경이 리스크가 된다**  
   OpenAI API에서 `gpt-4o-mini-transcribe` 등 slug가 특정 snapshot으로 업데이트된 것처럼, “같은 모델명”이더라도 서버 측에서 가리키는 버전이 바뀔 수 있습니다. 프로덕션에서는 **회귀 테스트, 모델 핀ning(스냅샷 고정), 관측지표(quality/cost/latency) 대시보드**가 필수가 됩니다. ([platform.openai.com](https://platform.openai.com/docs/changelog?utm_source=openai))

3) **에이전트는 이제 ‘채팅’이 아니라 ‘OS/앱 커넥터’가 본체**  
   Claude Cowork는 폴더 접근, 외부 서비스 연결, 동시 작업 등 “업무 자동화”를 전면에 두었습니다. 개발자 입장에선 LLM 호출 API만 붙이는 단계를 넘어, **권한 모델(파일/계정), 감사 로그, prompt injection 방어, 안전한 실행 샌드박스**를 제품 설계에 포함해야 합니다. ([theverge.com](https://www.theverge.com/ai-artificial-intelligence/860730/anthropic-cowork-feature-ai-agents-claude-code?utm_source=openai))

4) **정책 변화가 곧 제품 요구사항이 된다(health data, high-risk)**  
   Anthropic의 privacy/usage 정책 업데이트는 health data 연동과 high-risk use case에 대한 요구를 명시합니다. 헬스케어·리걸·금융 유사 영역은 “모델 성능”보다 **컴플라이언스 구현(고지/동의/보관/보안/제한)**이 출시 속도를 좌우할 가능성이 커졌습니다. ([privacy.claude.com](https://privacy.claude.com/en/articles/10301952-updates-to-our-privacy-policy))

---

## 💡 시사점과 전망
- **수익화(ads) + 저가 티어 확장**은 “대중화”의 신호이지만, 동시에 생태계에선 **개발자/기업 고객을 위한 ad-free·SLA·데이터 통제**가 더 중요해질 겁니다. OpenAI가 Pro/Business/Enterprise를 명확히 ad-free로 둔 것도 이 맥락입니다. ([openai.com](https://openai.com/index/our-approach-to-advertising-and-expanding-access//?utm_source=openai))  
- **모델 폐기/교체 주기**는 더 짧아질 가능성이 큽니다. Google의 deprecation 테이블처럼 “Earliest shutdown” 형태로 예고하고, Anthropic처럼 retire를 실행하는 흐름이 굳어지면, 개발 조직은 **모델 교체를 분기 단위 ‘상시 업무’로 내재화**해야 합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/deprecations?utm_source=openai))  
- 에이전트 경쟁은 “누가 더 똑똑한가”에서 “누가 더 안전하고 운영 가능한 자동화를 제공하는가”로 이동합니다. Cowork 같은 데스크톱/커넥터 기반 기능이 확산되면, 업계 표준은 **권한 분리·행동 제한·사용자 확인(confirmation) UX·보안 평가**로 수렴할 확률이 높습니다. ([theverge.com](https://www.theverge.com/ai-artificial-intelligence/860730/anthropic-cowork-feature-ai-agents-claude-code?utm_source=openai))

---

## 🚀 마무리
2026년 1월 업데이트의 본질은 “새 모델” 자체보다 **운영 현실(ads/요금/폐기/정책/에이전트 안전)**이 제품 설계의 중심으로 들어왔다는 점입니다.  
개발자 권장 액션은 세 가지입니다: (1) OpenAI/Anthropic/Google의 **changelog·deprecations를 CI 알림으로 구독**하고, (2) 모델을 **snapshot pinning + 회귀 테스트**로 관리하며, (3) 에이전트형 기능을 붙일 땐 **권한/로그/보안 가드레일**을 “기능”으로 같이 출시하세요. ([platform.openai.com](https://platform.openai.com/docs/changelog?utm_source=openai))