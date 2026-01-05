---
title: "12월 클라우드 전쟁의 포인트는 ‘AI Agent + 거대 컨텍스트 + 크로스클라우드’였다: AWS re:Invent 2025와 GCP/Azure의 맞불"
date: 2026-01-05 02:30:21 +0900
categories: [Infrastructure, News]
tags: [infrastructure, news, trend, 2026-01]
---

<div class="pageviews" style="margin: 0.25rem 0 1rem; opacity: 0.8;">
  <span style="font-weight: 600;">조회수</span>: <span id="pv-post">-</span>
</div>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
<script defer src="/assets/js/pageviews.js"></script>

## 들어가며
2025년 12월(정확히는 11/30~12/4 개최된 AWS re:Invent 2025 이후) AWS가 대규모 신규 서비스/기능을 쏟아냈고, 같은 12월에 GCP와 Azure도 “AI Agent 운영”과 “LLM 트래픽 제어”, “크로스클라우드 연결”을 전면에 내세웠습니다. 핵심 흐름은 단순 모델 제공을 넘어, **엔터프라이즈급 Agent 운영·거버넌스·비용통제**로 경쟁의 무게중심이 이동했다는 점입니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))

---

## 📰 무슨 일이 있었나
### AWS: re:Invent 2025(11/30~12/4, 라스베이거스) 발표 요약(12/5 업데이트)
AWS는 2025년 re:Invent에서 “Agentic AI”를 중심축으로 여러 서비스를 공개했습니다. 그중 개발 관점에서 파급이 큰 것만 추리면 다음이 눈에 띕니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))

- **Amazon Nova 2 Lite**: “reasoning”을 전면에 내세운 비용 효율 모델로, **1M token context window**를 언급했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))  
- **Amazon Nova Act (GA)**: 브라우저 기반 UI 작업(폼 입력, 검색·추출, 예약, QA 등)을 자동화하는 **AI agent** 서비스로, 엔터프라이즈 배포 기준 **90%+ reliability**를 강조했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))  
- **Amazon Bedrock AgentCore**: agent 배포 시 **policy control, quality evaluation, memory** 등 “운영 기능” 강화를 내놨습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))  
- **Amazon S3 Vectors (GA)**: 벡터 저장/검색을 S3 라인으로 끌어안으며, **index당 최대 20억 vectors**, **~100ms query latency**, “specialized DB 대비 비용 최대 90% 절감”을 제시했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))  
- **Amazon Bedrock: 18개 fully managed open weight models 추가**: Mistral Large 3/Ministral 3 등 다수 모델을 관리형으로 제공한다고 밝혔습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))  
- (운영/보안) **AWS DevOps Agent(Preview)**, **AWS Security Agent(Preview)** 등 “사람이 하던 운영·보안 워크플로우”를 agent로 자동화하려는 방향성이 강합니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))

### GCP: 2025년 12월 릴리즈 노트에서 드러난 ‘LLM 트래픽 관리’와 ‘크로스클라우드’
GCP는 2025년 12월 23일자 릴리즈에서 Apigee X에 **LLM Token Management용 정책 2종을 GA**로 공개했습니다.

- **LLMTokenQuota (GA)**: 응답 토큰 사용량을 모니터링/쿼터로 제한, 초과 시 **HTTP 429** 반환 ([docs.cloud.google.com](https://docs.cloud.google.com/release-notes?utm_source=openai))  
- **PromptTokenLimit (GA)**: 프롬프트 토큰 기반 rate limit(SpikeArrest 유사), 초과 시 **HTTP 429** 반환 ([docs.cloud.google.com](https://docs.cloud.google.com/release-notes?utm_source=openai))  

또한 같은 릴리즈 노트에 **Partner Cross-Cloud Interconnect for AWS (Preview)**가 포함되어, “온디맨드로 크로스클라우드 트랜스포트”를 강조합니다. ([docs.cloud.google.com](https://docs.cloud.google.com/release-notes?utm_source=openai))

### Azure/Microsoft: Ignite 2025 이후 ‘Foundry + Agent Service’ 구체화
Microsoft는 Ignite 2025 “Book of News”에서 **Microsoft Foundry**를 중심으로 agent 개발/운영을 플랫폼화하는 업데이트를 전면에 배치했습니다.

- **Foundry: unified MCP tools(Preview)**: MCP(Model Context Protocol) 도구 카탈로그, Logic Apps 커넥터(1,400+ 시스템) 등으로 agent의 “툴 접근”을 표준화하려는 접근 ([news.microsoft.com](https://news.microsoft.com/ignite-2025-book-of-news/?msockid=1aacee83415262a538e1f82f403363c0&utm_source=openai))  
- **Model router (GA)**: 단일 엔드포인트로 작업별 최적 모델을 자동 선택(성능/비용 최적화) ([news.microsoft.com](https://news.microsoft.com/ignite-2025-book-of-news/?msockid=1aacee83415262a538e1f82f403363c0&utm_source=openai))  
- **Foundry Agent Service: hosted agents, memory, multi-agent workflows (Preview)**: 멀티 agent·메모리·호스팅을 매니지드로 제공하려는 방향 ([news.microsoft.com](https://news.microsoft.com/ignite-2025-book-of-news/?msockid=1aacee83415262a538e1f82f403363c0&utm_source=openai))  

(참고로 Azure 생태계 내에서도 2025년 12월에 Azure Databricks가 **Databricks Assistant Agent Mode (Public Preview, 12/23)** 등을 릴리즈하며 “agent 모드”를 키워드로 잡았습니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/databricks/release-notes/product/2025/december?utm_source=openai)))

---

## 🔍 왜 중요한가
1) **“LLM 선택”에서 “Agent 운영”으로 무게중심이 이동**
2024~2025 초반까지는 “어떤 모델/엔드포인트를 쓰나”가 주제였다면, 2025년 12월 시점엔 **Agent를 안전하게 운영하고(정책/평가/메모리), 실제 업무를 자동화(UI·Ops·Sec)하는 기능**이 전면으로 나왔습니다. AWS의 Nova Act(GA)·Bedrock AgentCore, Microsoft의 Foundry Agent Service(Preview), Databricks Assistant Agent Mode(Preview)가 같은 흐름으로 읽힙니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))

2) **비용/성능 병목의 ‘현실 문제’가 제품 기능으로 흡수**
- AWS는 벡터 워크로드를 **S3 Vectors (GA)**로 끌어안으며 “대규모 벡터(최대 20억) + 낮은 지연(~100ms) + 비용 절감”을 정면으로 제시했습니다. RAG/검색 기반 시스템에서 “벡터DB 선택/운영”의 부담을 스토리지 레이어로 내리려는 시도로 해석됩니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))  
- GCP는 Apigee에 LLM 트래픽 정책을 GA로 올리며, 토큰 기반 비용 폭증/남용을 **API Gateway 레벨에서 제어**할 수 있게 했습니다. 이제 “RAG 잘 만들기”만큼 “토큰 예산/쿼터”가 아키텍처 요구사항이 됐다는 뜻이죠. ([docs.cloud.google.com](https://docs.cloud.google.com/release-notes?utm_source=openai))  
- Microsoft의 **Model router (GA)** 역시 “모델 선택”을 런타임 최적화로 흡수해, 팀이 매번 모델을 갈아끼우는 운영비를 줄이려는 방향입니다. ([news.microsoft.com](https://news.microsoft.com/ignite-2025-book-of-news/?msockid=1aacee83415262a538e1f82f403363c0&utm_source=openai))  

3) **크로스클라우드가 ‘이론’이 아니라 ‘네트워크 상품’이 됨**
GCP가 **Cross-Cloud Interconnect for AWS(Preview)**를 릴리즈 노트에 포함시킨 건 상징적입니다. 멀티클라우드를 선택한 조직이 늘면서, 이제 연결성은 VPN/직접 구성의 영역을 넘어 **SLA 기반의 상용 상품**으로 전환 중입니다. ([docs.cloud.google.com](https://docs.cloud.google.com/release-notes?utm_source=openai))

---

## 💡 시사점과 전망
- **2026년은 “AgentOps”가 “MLOps”를 대체/포함하는 해가 될 가능성**
AWS가 Bedrock AgentCore로 policy/quality/memory를 묶고, Microsoft가 Foundry에서 MCP 도구 카탈로그·hosted agents·멀티 agent 워크플로우를 예고한 흐름을 보면, 다음 경쟁 포인트는 “모델 성능”보다 **조직에서 agent를 통제 가능한 방식으로 확산시키는 플랫폼**이 될 공산이 큽니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))

- **RAG/벡터 스택의 ‘표준화’가 더 빨라질 수 있음**
S3 Vectors 같은 접근은 “전용 벡터DB를 언제까지 쓸 것인가?”라는 질문을 던집니다. 물론 모든 워크로드가 S3 Vectors로 대체되진 않겠지만, **범용 벡터 저장/검색은 클라우드 네이티브로 흡수**되고, 전용 DB는 초저지연·특수 검색/필터링·고급 인덱싱으로 더 차별화 압박을 받을 겁니다. (이 문단의 ‘전망’은 위 발표 사실을 바탕으로 한 해석입니다.) ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))

- **API Gateway는 ‘인증/라우팅’에서 ‘AI 비용 방화벽’으로 확장**
Apigee의 LLM 토큰 정책 GA는, 향후 Azure API Management/AWS API Gateway 계열도 유사한 “token-aware policy”를 강화할 여지가 큽니다. 개발팀은 2026년부터 **API 설계 단계에서 토큰 한도/429 처리/사용자별 과금 모델**을 함께 설계해야 할 가능성이 커졌습니다. ([docs.cloud.google.com](https://docs.cloud.google.com/release-notes?utm_source=openai))

---

## 🚀 마무리
2025년 12월 클라우드 신규 발표를 한 줄로 요약하면, **“AI는 모델이 아니라 운영 가능한 Agent 제품”**으로 바뀌는 변곡점이었습니다. AWS는 Nova Act·Bedrock AgentCore·S3 Vectors로 agent 실행/거버넌스/데이터 계층을 밀었고, GCP는 Apigee에서 토큰 정책을 GA로 올리며 비용 통제를 전면에, Microsoft는 Foundry에서 MCP·Agent Service·Model router로 플랫폼화를 가속했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))

개발자 권장 액션(실행 순서):
1) RAG/Agent 서비스에 **토큰 예산(쿼터)과 429 재시도/차단 정책**을 설계에 포함하기(Apigee의 흐름 참고) ([docs.cloud.google.com](https://docs.cloud.google.com/release-notes?utm_source=openai))  
2) 벡터 워크로드는 “전용 DB vs 클라우드 네이티브(예: S3 Vectors)”를 **비용/운영 복잡도 기준으로 재평가**하기 ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))  
3) Agent 도입은 POC보다 **policy/eval/memory/observability**를 먼저 체크리스트로 만들기(Bedrock AgentCore, Foundry Agent Service가 던지는 질문) ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?utm_source=openai))