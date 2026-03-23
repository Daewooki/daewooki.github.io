---
title: "OpenAI·Anthropic·Google, 2026년 3월 “API/정책/제품”이 동시에 흔들린 한 달"
date: 2026-03-23 02:54:00 +0900
categories: [AI, News]
tags: [ai, news, trend, 2026-03]
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
2026년 3월 AI 빅테크 3사는 “모델 성능 경쟁”만이 아니라, **API 라인업 재편·제품 노출 확대·안전/정책 포지셔닝 변경**을 한꺼번에 밀어붙였습니다. 특히 OpenAI의 정부 계약 문구 수정, Anthropic의 Responsible Scaling Policy(RSP) 기조 변화, Google의 Gemini Embedding 2 공개는 개발자 운영과 제품 로드맵에 직접적인 영향을 줍니다. ([openai.com](https://openai.com/index/our-agreement-with-the-department-of-war/?utm_source=openai))

---

## 📰 무슨 일이 있었나
- **OpenAI (2026-02-28, 2026-03-02 업데이트)**  
  OpenAI는 “Department of War”와의 계약 내용을 공개하며, **미국인(US persons)에 대한 domestic surveillance(국내 감시) 목적 사용 금지**가 계약 문구에 **명시되도록 추가 언어를 넣었다**고 밝혔습니다(2026년 3월 2일 업데이트). 또한 NSA 등 “Department of War intelligence agencies” 사용은 **새로운 별도 합의가 필요**하다고 적시했습니다. ([openai.com](https://openai.com/index/our-agreement-with-the-department-of-war/?utm_source=openai))

- **OpenAI (모델/API 업데이트: 2026-02-05, 2026-02-10, 2026-03 초까지 반영되는 흐름)**  
  - 2026년 2월 5일: **GPT-5.3-Codex** 공개(“agentic coding”에 초점, 속도 ~25% 개선 등). ([openai.com](https://openai.com/index/introducing-gpt-5-3-codex/?utm_source=openai))  
  - 2026년 2월 10일: **GPT-5.2 Instant**가 ChatGPT와 **API에서 품질/톤 업데이트**를 받았다고 공지. ([help.openai.com](https://help.openai.com/en/articles/9624314-model-release-notes%3Futm_source%3Dsyndication%26pubDate%3D20260309?utm_source=openai))  
  - (참고로) Codex 계열은 **Responses API 중심 제공** 흐름을 계속 강화하고 있고, GPT-5-Codex는 Responses API only로 안내됩니다. ([platform.openai.com](https://platform.openai.com/docs/models/gpt-5-codex/?utm_source=openai))  
  - 2026년 3월(2주 전 공개): **GPT-5.4**를 “ChatGPT, API, Codex로 롤아웃”한다고 소개하며, 2026년 6월 5일 retire 관련 일정도 함께 언급했습니다. ([openai.com](https://openai.com/fil-PH/index/introducing-gpt-5-4/?utm_source=openai))

- **Anthropic (2026-02-24 보도, 안전정책 기조 변경)**  
  TIME 보도에 따르면 Anthropic는 2023년에 내세웠던 RSP의 핵심 약속(“안전 보장을 확신하기 전엔 frontier 시스템을 훈련/릴리스하지 않겠다” 취지)을 **더 이상 그대로 유지하지 않는 방향으로 RSP를 대폭 개편**했다고 설명했습니다. 경쟁 심화/지정학적 환경을 이유로 “일방적 제약”이 현실적이지 않다는 논리를 폈고, 대신 경쟁사 대비 안전 노력의 “matching/surpassing”, 위험 공개 강화, 특정 조건에서의 “delay” 등으로 프레이밍을 바꿨습니다. ([time.com](https://time.com/7380854/exclusive-anthropic-drops-flagship-safety-pledge/?utm_source=openai))

- **Google (2026-03-04 ~ 2026-03-10, 제품/개발자 동시 드라이브)**  
  - 2026년 3월 4일: Google Search에서 **Gemini의 “Canvas in AI Mode”를 미국(영어) 사용자 전체로 확대**(TechCrunch). ([techcrunch.com](https://techcrunch.com/2026/03/04/https-techcrunch-com-2026-03-04-google-search-rolls-out-geminis-canvas-in-ai-mode-to-all-us-users/?utm_source=openai))  
  - 2026년 3월 10일: Google이 **Gemini Embedding 2**를 공개하며, **Gemini API 및 Vertex AI에서 Public Preview 제공**을 발표. “natively multimodal embedding model”임을 전면에 내세웠고, 모델명은 API에서 `gemini-embedding-2-preview`로 안내됩니다. ([blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-embedding-2/?utm_source=openai))  
  - (같은 흐름에서) `gemini-2.5-flash-lite-preview-09-2025`는 **2026년 3월 31일 shutdown** 예정으로 공지 형태로 확산되었습니다. ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))

---

## 🔍 왜 중요한가
- **“정책 문구”가 곧 제품 요구사항이 되는 국면**  
  OpenAI 사례처럼, 정부/규제 환경에서 **사용 제한이 계약/정책 텍스트로 명시**되면(예: domestic surveillance 금지), 이후 엔터프라이즈/공공 섹터 납품 시 **로그, 데이터 경로, 접근통제, 감사(audit) 설계**가 구현 요구로 되돌아옵니다. 개발자는 “기능 구현”뿐 아니라 **컴플라이언스 가능한 아키텍처(특히 cloud-only, data boundary)**를 기본값으로 깔아야 합니다. ([openai.com](https://openai.com/index/our-agreement-with-the-department-of-war/?utm_source=openai))

- **API는 ‘스펙’보다 ‘라인업 변동성’이 리스크가 됨**  
  Google의 `gemini-2.5-flash-lite-preview-09-2025` shutdown(2026-03-31) 같은 이벤트는, 모델 선택이 단순 성능 비교가 아니라 **서비스 연속성(SLA), 마이그레이션 비용, 회귀 테스트 체계**의 문제임을 보여줍니다. “preview” 모델을 프로덕션에 넣는 순간, **모델 교체 자동화/추상화 레이어**가 없으면 장애가 곧바로 매출 리스크로 전이됩니다. ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))

- **Embedding의 멀티모달화는 RAG 설계를 바꾼다**  
  Gemini Embedding 2처럼 “natively multimodal”을 전면에 둔 embedding이 API로 들어오면, RAG는 텍스트 chunking만의 문제가 아니라 **이미지/문서/동영상까지 동일한 retrieval 공간에 올리는 파이프라인**으로 진화합니다. 즉, “생성 모델 선택”보다 먼저 **인덱싱 단위, 저장 비용, 개인정보 포함 가능성(이미지/문서)**까지 재설계 이슈가 커집니다. ([blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-embedding-2/?utm_source=openai))

- **Coding agent는 ‘도구 호출(툴링)’이 핵심 경쟁축**  
  OpenAI가 GPT-5.3-Codex, GPT-5.4에서 “coding + reasoning + agentic”을 강조하는 흐름은, 개발자 입장에서 모델 자체보다 **Responses API 기반 tool calling, 작업 단위 실행, 평가/관측(telemetry)**이 제품 차별점이 되는 방향을 강화합니다. 코드 생성 품질이 비슷해질수록, 결국 **에이전트 운영(작업 큐/권한/샌드박스/비용통제)**이 승부처가 됩니다. ([openai.com](https://openai.com/index/introducing-gpt-5-3-codex/?utm_source=openai))

---

## 💡 시사점과 전망
- **“안전”은 약속의 형태가 바뀌고, 구현 책임은 더 아래(개발팀)로 내려온다**  
  Anthropic의 RSP 기조 변경 보도는, 업계가 “선(先)중단 약속” 같은 강한 형태에서 **경쟁 환경을 전제로 한 ‘상대 비교/지연’ 프레임**으로 이동하고 있음을 시사합니다. 결과적으로 제품팀은 “모델 제공사가 알아서 안전하게 해준다”가 아니라, **자사 서비스 레벨에서의 안전장치(권한, 레이트리밋, abuse 탐지, red-teaming 루프)**를 기본 요구로 삼게 됩니다. ([time.com](https://time.com/7380854/exclusive-anthropic-drops-flagship-safety-pledge/?utm_source=openai))

- **Google은 Search 배포(대중 노출) + API(개발자) 투트랙을 동시에 밀고 있다**  
  3월 초 “Canvas in AI Mode”의 미국 전면 확대는 사용자의 습관을 바꾸는 배포이고, 3월 10일 Embedding 2는 개발자 생태계에 직접 꽂는 업데이트입니다. 이 조합은 “모델”보다 **유통 채널(검색)과 개발 채널(API/Vertex)**을 묶어 생태계를 잠그려는 전략으로 읽힙니다. ([techcrunch.com](https://techcrunch.com/2026/03/04/https-techcrunch-com-2026-03-04-google-search-rolls-out-geminis-canvas-in-ai-mode-to-all-us-users/?utm_source=openai))

- **OpenAI는 공공/국방 협업에서 ‘계약 언어’로 신뢰를 쌓는 방식에 집중**  
  3월 2일 업데이트로 계약에 domestic surveillance 금지 등을 명시한 것은, 기술적 안전장치뿐 아니라 **법/정책/계약 텍스트를 제품 신뢰의 일부로 취급**하겠다는 신호입니다. 앞으로는 “모델 성능”과 별개로, **어떤 문구를 공개하고 어떤 제한을 명시하느냐**가 엔터프라이즈 수주 경쟁력으로 작동할 가능성이 큽니다. ([openai.com](https://openai.com/index/our-agreement-with-the-department-of-war/?utm_source=openai))

---

## 🚀 마무리
2026년 3월의 핵심은 “새 모델이 나왔다”가 아니라, **(1) 정책·계약이 제품 요구사항이 되고, (2) API 모델 라인업이 빠르게 교체되며, (3) 멀티모달 embedding이 RAG 설계를 바꾸는** 흐름이 동시에 진행됐다는 점입니다. ([openai.com](https://openai.com/index/our-agreement-with-the-department-of-war/?utm_source=openai))

개발자 권장 액션:
- 프로덕션에서 모델/벤더 교체를 전제로 **Model Abstraction Layer + 회귀테스트(프롬프트/출력 포맷/비용) 자동화**를 구축하세요(특히 preview 모델). ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))  
- RAG를 운영 중이면 `gemini-embedding-2-preview` 같은 멀티모달 embedding을 염두에 두고 **인덱싱/권한/PII 필터링**을 텍스트 중심에서 확장 설계하세요. ([blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-embedding-2/?utm_source=openai))  
- 공공/규제 산업이라면, OpenAI의 사례처럼 **계약/정책 텍스트가 요구하는 금지/제한사항을 시스템 요건으로 번역**(로그, 접근통제, 감사)하는 프로세스를 먼저 정립하세요. ([openai.com](https://openai.com/index/our-agreement-with-the-department-of-war/?utm_source=openai))