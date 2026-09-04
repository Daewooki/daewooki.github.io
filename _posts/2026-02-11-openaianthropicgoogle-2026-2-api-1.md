---
title: "OpenAI·Anthropic·Google, ‘API/정책’이 동시에 흔들린다: 코딩 에이전트 강화와 디프리케이션 러시"
description: "2026년 2월 들어 OpenAI는 코딩 특화 신모델을 내놓는 동시에(2/5) 레거시 모델 정리 일정을 못 박았고(2/13~2/16), Google은 Gemini API에서 모델 디프리케이션 타임라인을 명확히 하며(“Earliest February 2026”) 교체를 유도하고 있습니다.…"
date: 2026-02-11 03:14:33 +0900
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
2026년 2월 들어 OpenAI는 코딩 특화 신모델을 내놓는 동시에(2/5) 레거시 모델 정리 일정을 못 박았고(2/13~2/16), Google은 Gemini API에서 모델 디프리케이션 타임라인을 명확히 하며(“Earliest February 2026”) 교체를 유도하고 있습니다. Anthropic은 초장문 컨텍스트(1M tokens)와 에이전트 협업 기능을 전면에 내세우는 한편, 1월부터 적용되는 개인정보정책 변경을 공지했습니다.

---

## 📰 무슨 일이 있었나
- **OpenAI (2026-02-05)**: OpenAI Help Center ‘모델 릴리스 노트’에 따르면 **GPT-5.3-Codex**가 공개됐습니다. “에이전트형 코딩 모델”을 전면에 내세우며, Codex + GPT-5 학습 스택 결합과 속도/성능 개선을 강조합니다.[^1]  
- **OpenAI (2026-02-13 예정 / 2026-01-29 공지)**: OpenAI는 **2026-02-13**에 ChatGPT에서 **GPT‑4o, GPT‑4.1, GPT‑4.1 mini, o4-mini** 등을 retire 한다고 공지했습니다(단, “API에는 현재 변경 없음”이라고 명시).[^2]  
- **OpenAI (2026-02-04)**: **GPT-5.2 Thinking**의 “Extended thinking” 레벨을 복원하는 등, 추론 모델의 기본 “thinking time”을 계속 실험/조정 중임을 공개했습니다.[^3]  
- **OpenAI API 디프리케이션(2026-02-16 예정, 보도 기반)**: VentureBeat 보도에 따르면 OpenAI가 API 고객에게 **`chatgpt-4o-latest`를 2026-02-16에 종료**한다는 이메일을 보냈다고 합니다(이 일정은 API에만 해당).[^4]  

- **Google (Gemini API 디프리케이션)**: Google AI for Developers 문서에 따르면 **`gemini-2.0-flash` / `gemini-2.0-flash-001` / `gemini-2.0-flash-lite` 계열**의 shutdown date가 **“Earliest February 2026”**로 기재되어 있고, 대체 모델로 **`gemini-2.5-flash` / `gemini-2.5-flash-lite`**를 권장합니다.[^5]  
- **Google (Gemini API 변경/과금)**: Gemini API Release notes에는 **Gemini 3에서 Grounding with Google Search 과금이 2026-01-05부터 시작**된다고 기록돼 있어, “검색 기반 grounding”이 더 이상 공짜 옵션이 아님을 분명히 했습니다.[^6]  

- **Anthropic (2026년 2월 초, 제품/모델 보도)**: ITPro 보도에 따르면 Anthropic은 **Claude Opus 4.6**를 공개했고, **1 million token context window(베타)**를 핵심으로 내세웠습니다. 또한 여러 Claude agent가 병렬로 협업하는 **‘Agent Teams’**, API 상의 ‘adaptive thinking/effort’ 류 제어를 언급합니다.[^7]  
- **Anthropic (정책, 2026-01-12 효력)**: Anthropic Privacy Center는 **2026-01-12**부터 효력인 개인정보정책 변경 요약을 게시했습니다. 핵심은 (1) **Consumer Health Data Privacy Policy** 링크 추가(특정 미국 주의 health data 법 적용 사용자 + third-party health app 연동 시), (2) 지역별 supplemental disclosure를 섹션 11로 통합입니다.[^8]  

---

## 🔍 왜 중요한가
- **“코딩 에이전트”가 모델 릴리스의 1순위가 됨**  
  OpenAI가 GPT-5.3-Codex를 “에이전트형 코딩 모델”로 포지셔닝한 건, 단순 code completion이 아니라 **작업을 ‘수행’하는 코딩 에이전트**로 개발 플로우가 이동하고 있음을 뜻합니다.[^1] 개발자 입장에선 IDE/CI에 붙이는 방식이 “챗봇 호출”을 넘어, **작업 단위(이슈/PR/리팩토링) 자동화**로 재설계될 가능성이 큽니다.

- **모델 디프리케이션이 ‘예정 공지 → 강제 전환’ 속도로 빨라짐**  
  Google은 Gemini API 문서에 shutdown을 “Earliest February 2026”처럼 명시해, 레거시 endpoint가 갑자기 끊길 수 있음을 계약/운영 관점에서 드러냈습니다.[^5] OpenAI도 ChatGPT 레거시 retire(2/13)와 별개로 API 쪽 특정 모델(`chatgpt-4o-latest`) 종료(2/16, 보도)를 예고한 상황이라, **제품/채널별로 retire 타임라인이 다르게 흘러갈 수 있음**을 전제로 설계해야 합니다.[^2]

- **비용 구조가 “토큰 + 툴(grounding/search)” 조합으로 더 복잡해짐**  
  Gemini 3에서 Grounding with Google Search가 2026-01-05부터 과금이라는 건, “정확도/근거”를 위해 붙이던 기능이 **직접 비용 항목**이 되었단 의미입니다.[^6] 개발자는 retrieval/grounding 전략을 **항상-on**으로 둘지, **쿼리 라우팅(필요할 때만 호출)**으로 최적화할지 선택해야 합니다.

- **개인정보/규제 이슈가 ‘연동’ 기능에서 터짐**  
  Anthropic이 Consumer Health Data Privacy Policy를 별도 링크로 다룬 건, Claude가 외부 앱(특히 health domain)과 결합될 때 **데이터 분류/고지/동의**가 더 까다로워진다는 신호입니다.[^8] “AI 모델 선택”보다 “연동 설계”가 더 큰 리스크가 될 수 있습니다.

---

## 💡 시사점과 전망
- **빅테크 3사 공통 키워드: ‘에이전트화 + 운영 표준화(디프리케이션/정책)’**  
  OpenAI는 모델 릴리스 노트에서 thinking time을 조정하며 사용자/품질/지연시간을 계속 튜닝하고 있고,[^3] Google은 디프리케이션 표를 통해 교체 경로를 고정합니다.[^5] Anthropic은 초장문 컨텍스트(1M) + agent 협업을 내세워 “대형 업무 단위”를 먹겠다는 방향이 보입니다.[^7]  
  결과적으로 2026년 상반기는 “더 똑똑한 모델”보다 **더 잘 운영되는 플랫폼**(버전/교체/정책/비용)의 경쟁이 될 가능성이 큽니다.

- **예상 시나리오 1: 모델 교체가 ‘기능’이 아니라 ‘기본 운영 작업’이 됨**  
  “Earliest February 2026” 같은 표기는, 특정 분기에 교체가 아니라 **상시적 교체 파이프라인**(A/B, canary, fallback, regression suite)이 없으면 운영이 불가능하다는 뜻입니다.[^5]

- **예상 시나리오 2: 에이전트 기능은 길어지고(1M context), 가격/정책은 더 촘촘해짐**  
  Opus 4.6의 1M context가 베타로 열리고[^7], grounding이 과금되는 환경[^6] 에서는 “무조건 많이 넣기”가 아니라 **컨텍스트 압축/선별 + 툴 호출 최적화**가 성능만큼 중요해질 겁니다.

---

## 🚀 마무리
2월 업데이트의 핵심은 “새 모델” 그 자체보다 **교체 압력(디프리케이션)과 에이전트 지향 설계**가 동시에 강화됐다는 점입니다. OpenAI는 GPT-5.3-Codex로 코딩 에이전트를 밀고,[^1] Google은 Gemini API에서 2.0 Flash 계열을 “Earliest February 2026”로 정리하며 교체를 요구합니다.[^5] Anthropic은 1M context 및 agent 협업을 통해 더 큰 업무 단위를 겨냥하는 모습입니다.[^7]  

개발자 권장 액션(실행 순서):
1) 프로덕션에서 사용하는 모델/엔드포인트를 전수조사하고, “shutdown/retire date”가 명시된 항목부터 교체 백로그로 올리기(특히 Gemini 2.0 Flash 계열).[^5]  
2) 모델 교체를 코드 변경이 아닌 **운영 기능**으로 취급: fallback 모델, 회귀 테스트 프롬프트, 비용/지연시간 SLO를 함께 정의하기.  
3) grounding/search/tool 사용은 “품질 옵션”이 아니라 “비용 옵션”이므로, 라우팅(필요할 때만 호출)과 캐싱 전략을 먼저 설계하기.[^6]  
4) health 등 민감 도메인 연동이 있다면, 모델 정책보다 먼저 **개인정보정책/고지/동의 흐름**을 점검하기.[^8]

[^1]: <https://help.openai.com/ko-kr/articles/9624314-model-release-notes>
[^2]: <https://help.openai.com/en/articles/9624314>
[^3]: <https://help.openai.com/en/articles/9624314-model-release-notes>
[^4]: <https://venturebeat.com/ai/openai-is-ending-api-access-to-fan-favorite-gpt-4o-model-in-february-2026>
[^5]: <https://ai.google.dev/gemini-api/docs/deprecations>
[^6]: <https://ai.google.dev/gemini-api/docs/changelog>
[^7]: <https://www.itpro.com/technology/artificial-intelligence/anthropic-reveals-claude-opus-4-6-enterprise-focused-model-1-million-token-context-window>
[^8]: <https://privacy.claude.com/en/articles/10301952-updates-to-our-privacy-policy>
