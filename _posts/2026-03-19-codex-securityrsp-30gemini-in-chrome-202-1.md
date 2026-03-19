---
title: "Codex Security·RSP 3.0·Gemini in Chrome: 2026년 3월, “모델 성능”보다 “운영·정책·보안”이 승부를 가른다"
date: 2026-03-19 02:53:29 +0900
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
2026년 3월(그리고 직전 2월 말) OpenAI·Anthropic·Google은 공통적으로 “더 똑똑한 모델” 자체보다, 개발자가 실제로 쓰게 만드는 **보안/정책/배포 단위의 업데이트**를 전면에 내세웠습니다. Codex가 AppSec 에이전트로 확장되고, Anthropic은 안전 거버넌스를 재작성했으며, Google은 브라우저/워크스페이스 레이어에서 Gemini를 더 깊게 끌어안는 흐름이 뚜렷합니다. ([openai.com](https://openai.com/index/codex-security-now-in-research-preview/?utm_source=openai))

---

## 📰 무슨 일이 있었나
- **2026년 3월 6일, OpenAI — “Codex Security” 연구 프리뷰 공개**
  - OpenAI가 애플리케이션 보안 에이전트 **Codex Security**를 “research preview”로 발표했습니다.
  - 제공 채널은 **Codex web**이며, 대상은 **ChatGPT Pro, Enterprise, Business, Edu** 고객입니다.
  - “다음 한 달 무료 사용”이 명시되어 있어, 초기 도입 장벽을 낮춘 형태로 보입니다. ([openai.com](https://openai.com/index/codex-security-now-in-research-preview/?utm_source=openai))
  - OpenAI Help Center에도 Codex Security가 “취약점 식별/검증/수정(remediate)”을 돕는 연구 프리뷰로 정리되어 있습니다. ([help.openai.com](https://help.openai.com/en/articles/20001107-codex-security?utm_source=openai))

- **2026년 3월 10일, OpenAI — ChatGPT 수학/과학 학습 기능 업데이트**
  - OpenAI는 ChatGPT에 **dynamic visual explanations**를 도입해, 수학·과학 개념을 더 “인터랙티브”하게 학습하도록 돕는다고 발표했습니다.
  - “70개 이상의 core math/science concepts부터 시작”이라는 범위가 구체적으로 언급됩니다. ([openai.com](https://openai.com/index/new-ways-to-learn-math-and-science-in-chatgpt/?utm_source=openai))

- **2026년 2월 24일(효력일), Anthropic — Responsible Scaling Policy(RSP) v3.0**
  - Anthropic은 RSP를 **v3.0으로 전면 개정(“comprehensive rewrite”)**했고, **2026년 2월 24일 effective**로 명시했습니다.
  - 핵심 변화로 **Frontier Safety Roadmaps(안전 목표 로드맵)**와, 배포된 모델 전반의 위험을 수치화한다는 **Risk Reports** 발행을 포함한다고 밝혔습니다. ([anthropic.com](https://www.anthropic.com/rsp-updates?utm_source=openai))
  - 같은 맥락에서 Claude Opus 4.6 관련 **Sabotage Risk Report(외부 공개 버전)** 발행도 RSP 업데이트 페이지에서 연결됩니다. ([anthropic.com](https://www.anthropic.com/rsp-updates?utm_source=openai))
  - 외부 보도에서는 Anthropic이 과거 RSP의 “핵심 안전 공약(사전 안전 보장 없이는 학습/확장 중단)”을 사실상 폐기하고, 대신 “투명성·리스크 리포팅·로드맵” 중심으로 재정렬했다는 점이 강조됐습니다. ([time.com](https://time.com/7380854/exclusive-anthropic-drops-flagship-safety-pledge/?utm_source=openai))

- **2026년 3월, Google — Gemini를 ‘브라우저/업무 도구’로 확장 + 일부 모델 deprecation 신호**
  - Google Workspace/Chrome 흐름에서 **Gemini in Chrome** 관련 롤아웃/가용성 안내가 2026년 3월에도 이어지고(Releasebot 집계에 따르면 롤아웃 시작일이 **2026년 3월 10일**로 표기), 관리자 제어(ON/OFF, 도메인·OU 단위 등)와 함께 배포되는 형태입니다. ([releasebot.io](https://releasebot.io/updates/google))
  - 같은 “2026년 3월 업데이트” 묶음에서, Google이 **gemini-embedding-2-preview(멀티모달 embedding)** 릴리스 및 특정 preview 모델의 **2026년 3월 31일 shutdown** 같은 “운영 공지”가 함께 언급됩니다. ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))

---

## 🔍 왜 중요한가
1) **보안이 ‘옵션’이 아니라, 에이전트 개발 파이프라인의 기본 기능으로 편입**
- Codex Security는 단순 SAST 보조가 아니라 “에이전트 + 검증(automated validation)”을 내세우며, “false positive triage 비용”을 줄이는 방향을 전면에 둡니다. 즉, 개발팀 입장에선 코드 생성/리팩토링과 동일한 레벨로 **보안 리뷰 자동화**를 설계할 근거가 생깁니다. ([openai.com](https://openai.com/index/codex-security-now-in-research-preview/?utm_source=openai))  
- 특히 “Pro/Enterprise/Business/Edu + 1개월 무료”는, 기술적으로는 API보다도 **조직 단위 PoC**가 빠르게 늘어날 수 있는 전형적인 프로덕트 GTM 신호입니다. ([openai.com](https://openai.com/index/codex-security-now-in-research-preview/?utm_source=openai))

2) **안전 ‘정책’이 기술 스펙처럼 개발 의사결정에 직접 영향을 주기 시작**
- Anthropic RSP v3.0은 “모델이 어느 수준이면 무엇을 공개/보고할 것인가”를 **Risk Reports, Frontier Safety Roadmaps** 같은 산출물로 고정합니다. 개발자/보안 담당자 관점에선, 벤더 선택 시 모델 성능뿐 아니라 **리스크 보고 주기, 공개 범위, 거버넌스 구조**가 비교 가능해집니다. ([anthropic.com](https://www.anthropic.com/rsp-updates?utm_source=openai))

3) **Google은 ‘모델 API’보다 ‘업무/브라우징 표면적(surface)’을 넓혀 락인을 강화**
- Gemini in Chrome은 단순 챗봇이 아니라 “열려 있는 탭 컨텍스트를 활용”하고, Workspace 관리자가 통제하는 방식으로 굳어지고 있습니다(조직 보안/거버넌스 요구에 맞춰 제품화). 개발자는 이제 “모델 호출”뿐 아니라 **브라우저/업무 도구 내 AI 사용 흐름**까지 포함해 제품 경험을 재설계해야 합니다. ([releasebot.io](https://releasebot.io/updates/google))  
- 동시에 embedding preview 릴리스, preview 모델 shutdown 공지처럼 “수명주기 관리”가 더 촘촘해져, 운영팀은 **모델 deprecation 대응**을 릴리즈 프로세스에 포함해야 합니다. ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))

---

## 💡 시사점과 전망
- **경쟁 축이 “모델 점수” → “운영 가능성(보안·정책·배포)”으로 이동**
  - OpenAI는 Codex를 “코딩 에이전트”에서 **AppSec 에이전트**로 확장해, 기업 도입의 마지막 병목(보안 리뷰)을 정면으로 겨냥했습니다. ([openai.com](https://openai.com/index/codex-security-now-in-research-preview/?utm_source=openai))  
  - Anthropic은 안전 프레임워크를 “멈출 수 있다”는 선언형 공약보다, **정기 리포팅/로드맵** 같은 지속 가능한 거버넌스로 재정의했습니다. ([anthropic.com](https://www.anthropic.com/rsp-updates?utm_source=openai))  
  - Google은 사용자가 매일 쓰는 Chrome/Workspace에 Gemini를 끼워 넣어, AI를 “별도 도구”가 아니라 **업무 흐름의 기본 레이어**로 만들고 있습니다. ([releasebot.io](https://releasebot.io/updates/google))

- **예상 시나리오(팩트 기반 추론)**
  1) 2026년 상반기에는 “agent + security + governance” 패키지가 엔터프라이즈 구매 체크리스트의 표준이 될 가능성이 큽니다(각 사 발표가 이미 그 방향). ([openai.com](https://openai.com/index/codex-security-now-in-research-preview/?utm_source=openai))  
  2) 모델/기능이 preview로 빠르게 나오고 빠르게 종료되는 흐름이 강화되며, 개발 조직은 “모델 버전업/종료”를 **SRE 수준의 변경관리**로 다뤄야 합니다. ([releasebot.io](https://releasebot.io/updates/google?utm_source=openai))

---

## 🚀 마무리
2026년 3월의 핵심은 “누가 더 똑똑한 모델을 냈나”보다, **보안 에이전트(Codex Security)**, **안전 거버넌스(RSP 3.0)**, **배포 표면적(Gemini in Chrome/Workspace)**처럼 개발 현장의 실제 비용을 줄이는 업데이트였습니다. ([openai.com](https://openai.com/index/codex-security-now-in-research-preview/?utm_source=openai))

개발자에게 권장 액션:
- (OpenAI) Codex Security가 들어갈 수 있는 지점(예: PR 단계, 릴리즈 후보 브랜치, 취약점 triage)을 정해 **AppSec 파이프라인 PoC**를 설계하세요. ([openai.com](https://openai.com/index/codex-security-now-in-research-preview/?utm_source=openai))  
- (Anthropic) 벤더 평가 기준에 “Risk Reports/로드맵/정책 업데이트 주기”를 포함해, 모델 성능 외의 **거버넌스 지표**를 문서화하세요. ([anthropic.com](https://www.anthropic.com/rsp-updates?utm_source=openai))  
- (Google) Gemini in Chrome/Workspace 롤아웃과 admin control을 전제로, 조직 내 AI 사용 정책(데이터 경계, 허용 범위)을 **브라우저 레벨**까지 확장해 점검하세요. ([releasebot.io](https://releasebot.io/updates/google))