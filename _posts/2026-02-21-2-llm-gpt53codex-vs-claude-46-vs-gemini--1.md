---
title: "2월 한 달, LLM 판도가 또 바뀌었다: GPT‑5.3‑Codex vs Claude 4.6 vs Gemini 3.1 Pro"
date: 2026-02-21 02:37:51 +0900
categories: [AI, News]
tags: [ai, news, trend, 2026-02]
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
2026년 2월(특히 2/5 전후) OpenAI·Anthropic·Google이 각각 개발자/에이전트 워크플로우를 겨냥한 신규 모델·플랫폼 업데이트를 연달아 발표했습니다. 단순 “성능 업”이 아니라, **agentic coding·1M context·엔터프라이즈 운영**이 경쟁의 중심축으로 확실히 이동한 것이 핵심입니다. ([openai.com](https://openai.com/index/introducing-gpt-5-3-codex/?utm_source=openai))

---

## 📰 무슨 일이 있었나
- **OpenAI — 2026-02-05, GPT‑5.3‑Codex 발표**
  - OpenAI가 **GPT‑5.3‑Codex**를 공개하며 “가장 강력한 agentic coding 모델”로 포지셔닝했습니다. 이전 세대 대비 **25% faster**를 강조했고, 공개한 벤치마크에서 **SWE‑Bench Pro (Public) 56.8%**, **Terminal‑Bench 2.0 77.3%**, **OSWorld‑Verified 64.7%** 등을 제시했습니다. ([openai.com](https://openai.com/index/introducing-gpt-5-3-codex/?utm_source=openai))
- **OpenAI — 2026-02-05, Frontier(엔터프라이즈 에이전트 플랫폼) 발표**
  - 같은 날 OpenAI는 기업이 에이전트를 **build/deploy/manage**하도록 돕는 **Frontier**를 발표했고, 초기 채택 기업으로 Intuit, Uber, State Farm, Thermo Fisher 등 사례를 함께 공개했습니다. ([openai.com](https://openai.com/index/introducing-openai-frontier/?utm_source=openai))
- **Anthropic — 2026-02-05, Claude Opus 4.6 발표**
  - Anthropic은 최상위 모델 **Claude Opus 4.6**를 발표하며, Opus급에서 처음으로 **1M token context window(beta)**를 내세웠습니다. 또한 Claude Code에 **agent teams(리서치 프리뷰)**, API에 **effort controls(저/중/고/max)**, **context compaction(beta)** 같은 “장기 작업/에이전트 운영” 기능을 추가했습니다. 가격은 **$5 / $25 per million input/output tokens**(기본 구간)로 유지된다고 명시했습니다. ([anthropic.com](https://www.anthropic.com/news/claude-opus-4-6?utm_source=openai))
- **Anthropic — 2026-02-17, Claude Sonnet 4.6 발표**
  - 2주 뒤 Anthropic은 중간 라인업인 **Claude Sonnet 4.6**를 공개했고, Free/Pro에서 **default model**로 전환했습니다. **1M context(beta)**를 포함하며, 가격은 **$3 / $15 per million input/output tokens**로 Sonnet 4.5와 동일하다고 밝혔습니다. ([anthropic.com](https://www.anthropic.com/news/claude-sonnet-4-6?utm_source=openai))
- **Google — 2026-02-19, Gemini 3.1 Pro 발표(프리뷰 롤아웃)**
  - Google은 **Gemini 3.1 Pro**를 발표하며 “복잡한 문제 해결/추론” 강화를 전면에 두었습니다. Ars Technica가 인용한 수치로 **Humanity’s Last Exam 44.4%**, **ARC‑AGI‑2 77.1%**를 강조했고, **context 1M input / 64k output**, API 가격 **$2 input / $12 output per 1M tokens**를 유지한다고 전했습니다(AI Studio/Vertex 등으로 확산). ([arstechnica.com](https://arstechnica.com/google/2026/02/google-announces-gemini-3-1-pro-says-its-better-at-complex-problem-solving/?utm_source=openai))

---

## 🔍 왜 중요한가
1. **경쟁의 축이 “chat”에서 “agentic workflow”로 고정**
   - GPT‑5.3‑Codex는 Terminal‑Bench/OSWorld처럼 “도구·터미널·컴퓨터 사용” 성격이 강한 지표를 전면에 내세웠고, Frontier는 이를 조직에 배포/운영하는 프레임까지 묶었습니다. 즉, 모델 성능만이 아니라 **에이전트를 굴리는 운영 체계**가 제품 경쟁력이 됐습니다. ([openai.com](https://openai.com/index/introducing-gpt-5-3-codex/?utm_source=openai))
2. **1M context가 ‘스펙’이 아니라 ‘제품 기능’으로 내려옴**
   - Opus 4.6과 Sonnet 4.6 모두 1M context(beta)를 명시했고, Sonnet 4.6은 더 낮은 가격대에서 “기본 모델”로 깔리기 시작했습니다. 개발자 입장에선 RAG/샤딩/요약 파이프라인을 “항상” 짜야 하는 상황이 일부 완화될 수 있지만, 동시에 **긴 컨텍스트를 안정적으로 유지하는 프롬프트/툴 설계**가 더 중요해집니다. ([anthropic.com](https://www.anthropic.com/news/claude-opus-4-6?utm_source=openai))
3. **성능 비교가 더 ‘다차원’이 됨**
   - Gemini 3.1 Pro는 ARC‑AGI‑2 같은 추론 지표에서 큰 폭의 개선을 내세운 반면, Ars Technica는 LM Arena에서 텍스트/코드 부문에서 Claude Opus 4.6, 일부 GPT 계열이 여전히 앞선다고 정리합니다. 이제 “누가 1등”이 아니라 **업무 유형(코딩 에이전트/지식작업/추론/컴퓨터 사용)**별 최적 모델 선택이 현실적인 전략입니다. ([arstechnica.com](https://arstechnica.com/google/2026/02/google-announces-gemini-3-1-pro-says-its-better-at-complex-problem-solving/?utm_source=openai))

---

## 💡 시사점과 전망
- **엔터프라이즈는 ‘멀티모델+거버넌스’로 간다**
  - Frontier가 “에이전트 운영”을 전면에 둔 것처럼, 대기업은 단일 LLM보다 **권한/감사/데이터 경계/평가**가 더 큰 구매 요인이 됩니다. 이 흐름에서 개발자는 모델 호출 코드보다 **관측 가능성(observability), 정책, 평가 자동화**를 제품의 일부로 설계해야 합니다. ([openai.com](https://openai.com/index/introducing-openai-frontier/?utm_source=openai))
- **Anthropic의 전략: 최상위(Opus) 기능을 중간 티어(Sonnet)로 빠르게 확산**
  - Sonnet 4.6을 Free/Pro 기본값으로 깔아버린 건 “프리미엄 기능의 대중화”에 가깝습니다. 결과적으로 팀 내부에서 “모두가 동일한 기본 모델”을 쓰며 생산성을 끌어올리기 쉬워지고, Opus는 더 어려운 장기/고난도 작업으로 포지셔닝이 선명해집니다. ([anthropic.com](https://www.anthropic.com/news/claude-sonnet-4-6?utm_source=openai))
- **Google은 ‘추론+가격’으로 개발자 점유율을 노림**
  - Gemini 3.1 Pro는 1M context를 유지하면서 토큰 가격(입력 $2/출력 $12 per 1M)을 강조하고 있어, 대규모 트래픽 서비스에서 “비용 대비 성능” 경쟁이 더 치열해질 가능성이 큽니다. (다만 실제 체감은 벤치마크보다, 각자 도메인 데이터/툴체인에서의 실패율이 좌우합니다.) ([arstechnica.com](https://arstechnica.com/google/2026/02/google-announces-gemini-3-1-pro-says-its-better-at-complex-problem-solving/?utm_source=openai))

---

## 🚀 마무리
2026년 2월의 핵심은 “새 모델 출시” 자체보다, **LLM이 팀의 코딩/업무를 ‘대행하는 에이전트’로 제품화**되고 있다는 점입니다(OpenAI는 GPT‑5.3‑Codex+Frontier, Anthropic은 Opus/Sonnet 4.6의 1M context와 agent teams, Google은 Gemini 3.1 Pro로 추론·가격 경쟁). ([openai.com](https://openai.com/index/introducing-gpt-5-3-codex/?utm_source=openai))

개발자 권장 액션:
- (1) 사내 대표 유스케이스 2~3개를 정해 **SWE‑Bench류 지표가 아니라 “우리 리포/우리 로그/우리 툴”에서 A/B 평가**를 먼저 돌리기  
- (2) 1M context를 전제로 **프롬프트/툴 호출 설계(요약·compaction·권한 경계)**를 재점검하기  
- (3) “모델 선택”보다 더 중요한 **운영(관측·평가·가드레일·비용 모니터링)**을 제품 요구사항으로 격상시키기 ([anthropic.com](https://www.anthropic.com/news/claude-opus-4-6?utm_source=openai))