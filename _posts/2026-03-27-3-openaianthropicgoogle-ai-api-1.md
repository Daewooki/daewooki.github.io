---
title: "3월 한 달, OpenAI·Anthropic·Google AI가 동시에 ‘제품+정책+API’ 판을 흔들었다"
date: 2026-03-27 03:18:58 +0900
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
2026년 3월, OpenAI는 제품/엔터프라이즈 통합과 함께 API에 새 모델을 올렸고, Anthropic은 안전 정책 프레임워크(Responsible Scaling Policy, RSP)를 재정비했으며, Google은 Gemini API에 **멀티모달 embedding**을 공개 프리뷰로 내놓고 일부 프리뷰 모델 **shutdown 일정을 명시**했습니다. 각각의 발표는 방향이 다르지만, 공통적으로 “모델 성능”보다 “운영(rollout, deprecation, 정책, 계약 언어)”이 개발자 경험을 좌우하는 국면으로 들어왔다는 신호입니다. ([openai.com](https://openai.com/index/chatgpt-for-excel/?utm_source=openai))

---

## 📰 무슨 일이 있었나
### OpenAI (2026년 3월)
- **2026년 3월 5일**: OpenAI가 *ChatGPT for Excel* (beta) 및 금융 데이터 통합을 발표했고, 같은 공지에서 **GPT‑5.4(“GPT‑5.4 Thinking”)가 ChatGPT, Codex, API에서 사용 가능**하다고 밝혔습니다. 즉, “새 모델 제공(5.4)”과 “스프레드시트 워크플로 내장”이 한 번에 묶여 나왔습니다. ([openai.com](https://openai.com/index/chatgpt-for-excel/?utm_source=openai))
- **2026년 3월 2일 업데이트 포함 공지**: OpenAI는 “Department of War” 계약 관련 입장을 정리하며, **cloud-only deployment**, 계약 문구, 법/정책, 그리고 “layered safety stack”을 강조했습니다(단순 Usage policy만으로 막지 않겠다는 뉘앙스). 이 문서는 제품 업데이트라기보다 **정책/거버넌스 커뮤니케이션** 성격이 강합니다. ([openai.com](https://openai.com/index/our-agreement-with-the-department-of-war/?utm_source=openai))
- (운영 이슈) **2026년 3월 2일**: OpenAI Status에서 파일 업로드/처리 장애(에러 증가)를 공지했습니다. 모델 자체보다 “파일/툴 체인”이 업무 영향도를 키우는 전형적 사례입니다. ([status.openai.com](https://status.openai.com/incidents/01KJQJRF7J0CKT82SHDZ85YG4Y?utm_source=openai))
- (엔터프라이즈 배포) OpenAI Help Center 기준으로 **2026년 3월 11일부로 ChatGPT에서 GPT‑5.1 모델 제공 중단**이 명시되어, 조직 단위 운영에서는 “모델 수명주기 관리”가 더 중요해졌음을 보여줍니다. ([help.openai.com](https://help.openai.com/zh-hant/articles/10128477-chatgpt-enterprise-%E8%88%87-edu%E7%89%88%E6%9C%AC%E7%99%BC%E8%A1%8C%E8%AA%AA%E6%98%8E?utm_source=openai))

### Anthropic (2026년 2~3월 흐름, 3월에 영향 확산)
- Anthropic은 **Responsible Scaling Policy Updates** 페이지에서 RSP 변경 이력을 관리하고 있으며, “업데이트된 평가(evaluations)와 안전장치(safeguards)”를 계속 언급합니다. 정책 문서가 단발 공지가 아니라 **버전업/개정 이력 관리 대상**이 됐다는 점이 포인트입니다. ([anthropic.com](https://www.anthropic.com/rsp-updates?utm_source=openai))
- 외부 보도(2026년 2월 26일자)에서는 Anthropic이 과거의 “특정 조건에서 scaling/pause” 성격의 핵심 약속을 더 유연한 프레임으로 바꿨다는 해석이 나왔습니다(경쟁 환경, 반복 출시 속도 등을 배경으로 듦). ([techradar.com](https://www.techradar.com/ai-platforms-assistants/anthropic-drops-its-signature-safety-promise-and-rewrites-ai-guardrails?utm_source=openai))

### Google (2026년 3월)
- **2026년 3월 10일**: Google이 **Gemini Embedding 2**를 발표하며, Gemini 아키텍처 기반의 **“natively multimodal embedding model”**을 **Gemini API와 Vertex AI에서 Public Preview로 제공**한다고 밝혔습니다. RAG/검색/추천 시스템에서 “text-only embeddings”가 병목이던 팀들에게 직접적인 업데이트입니다. ([blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-embedding-2/?utm_source=openai))
- 또한 Google 관련 릴리즈 트래킹(3월 업데이트 요약)에서는 **`gemini-2.5-flash-lite-preview-09-2025`가 2026년 3월 31일 shutdown** 된다는 “deprecation/shutdown 일정”이 명시되어 있습니다. 프리뷰 모델이라도 운영 중이면, 이 한 줄이 곧 장애/마이그레이션 티켓으로 바뀝니다. ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))

---

## 🔍 왜 중요한가
1) **“모델 발표”가 아니라 “업무 흐름에 끼워 넣기”가 핵심 전장이 됨 (OpenAI)**
- GPT‑5.4 제공 자체도 크지만, OpenAI가 2026년 3월 5일 공지에서 보여준 건 “API/모델”을 “Excel 같은 현업 도구 안으로 밀어 넣는 전략”입니다. 개발자 입장에선 단순 API 호출이 아니라, **스프레드시트 기반의 데이터/권한/감사(audit) 체계**까지 함께 설계해야 합니다. ([openai.com](https://openai.com/index/chatgpt-for-excel/?utm_source=openai))

2) **정책은 ‘문서’가 아니라 ‘릴리즈 노트’처럼 관리되는 대상이 됨 (Anthropic)**
- Anthropic이 RSP 업데이트 이력을 지속 관리하고, 외부에서 그 의미(더 유연해짐)를 크게 해석하는 상황은 “정책 변화”가 곧 **제품의 허용 사용 범위/안전장치/고객 커뮤니케이션**에 직결됨을 보여줍니다. 특히 B2B 고객은 모델 성능보다 “어제 가능하던 것이 오늘 불가”가 더 큰 리스크입니다. ([anthropic.com](https://www.anthropic.com/rsp-updates?utm_source=openai))

3) **RAG/검색 스택에서 ‘멀티모달 embedding’이 API 레벨 표준 옵션으로 올라오기 시작 (Google)**
- Gemini Embedding 2의 Public Preview는, 문서+이미지(도면/스크린샷)+오디오/비디오까지 한 시스템에서 다루려는 팀에게 “별도 모델 조합” 대신 **단일 embedding 계층**을 검토할 근거를 제공합니다. 반대로 말하면, 임베딩 인덱스/스키마/평가 지표를 **멀티모달 기준으로 재설계**해야 하는 팀이 늘어납니다. ([blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-embedding-2/?utm_source=openai))

4) **Deprecation/Shutdown이 더 노골적으로 ‘날짜로’ 들어온다 (Google)**
- `gemini-2.5-flash-lite-preview-09-2025`의 **2026년 3월 31일 shutdown**처럼, 프리뷰 모델도 “언젠가”가 아니라 “정확한 날짜”로 닫힙니다. 개발자는 이제 모델 선택 기준에 **성능/가격 + 수명주기(availability window)**를 강제로 포함해야 합니다. ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))

---

## 💡 시사점과 전망
- **빅테크 3사의 공통 흐름**은 “더 강한 모델”보다 “배포/정책/운영”을 전면에 올리는 것입니다. OpenAI는 워크플로 내장(Excel)과 계약/안전 스택 커뮤니케이션을, Anthropic은 RSP처럼 **정책을 제품의 일부**로, Google은 API 라인업을 늘리면서도 **shutdown 타임라인**을 같이 가져갑니다. ([openai.com](https://openai.com/index/chatgpt-for-excel/?utm_source=openai))
- **경쟁 구도**는 “누가 제일 똑똑하냐”에서 “누가 운영하기 쉽고(툴/통합), 예측 가능하며(deprecation), 규정 준수 설명이 명확하냐(정책/계약)”로 이동합니다. 특히 엔터프라이즈/공공 영역은 모델 벤치마크보다 **정책·감사·계약 언어**가 실제 도입을 좌우할 가능성이 큽니다. ([openai.com](https://openai.com/index/our-agreement-with-the-department-of-war/?utm_source=openai))
- 단기적으로(2026년 2분기) 개발 조직에서 늘어날 일은 두 가지입니다:  
  1) **멀티모달 RAG 평가 체계 정비**(embedding 교체/병행, 재인덱싱 비용 산정) ([blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-embedding-2/?utm_source=openai))  
  2) **모델 deprecation 대응 프로세스**(모델별 종료일 캘린더링, fallback 라우팅, 회귀 테스트 자동화) ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))  

---

## 🚀 마무리
2026년 3월 업데이트를 한 줄로 요약하면, **AI는 이제 “모델”이 아니라 “운영되는 제품”**이라는 겁니다. OpenAI는 GPT‑5.4를 API에 올리면서 Excel 워크플로까지 밀어 넣었고, Anthropic은 RSP처럼 정책을 계속 개정·관리하는 방식으로 신뢰/경쟁을 동시에 다루려 하며, Google은 멀티모달 embedding을 공개 프리뷰로 내놓는 동시에 프리뷰 모델 shutdown 날짜를 못 박았습니다. ([openai.com](https://openai.com/index/chatgpt-for-excel/?utm_source=openai))

개발자 권장 액션(바로 실행 가능한 것만):
- **모델/임베딩 “종료일”을 아키텍처 요구사항에 포함**(SLA, 대체 모델, 회귀 테스트 항목화). ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))  
- RAG를 운영 중이라면 **Gemini Embedding 2 같은 멀티모달 embedding 도입 시 재인덱싱/평가 비용**을 먼저 산정(POC는 빠르게, 운영 전환은 천천히). ([blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-embedding-2/?utm_source=openai))  
- 도구 내장형(AI in Excel 등) 도입 시 **권한/감사 로그/데이터 경계(tenant, workspace)**를 “기능”만큼 먼저 설계. ([openai.com](https://openai.com/index/chatgpt-for-excel/?utm_source=openai))