---
title: "에이전틱 AI가 클라우드 “신규 서비스 발표”의 주인공이 된 2025년 12월: AWS re:Invent발 변화와 Azure/GCP의 대응"
description: "2025년 12월(정확히는 2025년 11월 30일~12월 4일) AWS re:Invent 2025에서 AWS가 대규모 신규 서비스를 쏟아냈고, 메시지는 한 줄로 요약됩니다: AI 모델 자체보다 “AI agent를 안전하게, 대규모로 굴리는 플랫폼” 경쟁이 본격화됐다는 것."
date: 2026-01-08 02:13:48 +0900
categories: [News, Infrastructure]
tags: [infrastructure, news]
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
2025년 12월(정확히는 2025년 11월 30일~12월 4일) AWS re:Invent 2025에서 AWS가 대규모 신규 서비스를 쏟아냈고, 메시지는 한 줄로 요약됩니다: **AI 모델 자체보다 “AI agent를 안전하게, 대규모로 굴리는 플랫폼” 경쟁이 본격화**됐다는 것.[^1]  
동시에 Microsoft는 Ignite 흐름에서 **Security Copilot과 보안 에이전트**를 “라이선스 번들”로 확장하며, AI 운영의 중심을 보안/거버넌스로 끌어당겼습니다.[^2]

---

## 📰 무슨 일이 있었나
### 1) AWS: re:Invent 2025(라스베이거스, 2025-11-30~12-04)에서 ‘agent + 인프라’ 동시 확장
AWS는 공식 요약(업데이트 시각: 2025-12-05 PST)에서 다음을 핵심 발표로 정리했습니다.[^1]  

- **Amazon Nova 2 모델 라인업** 공개  
  - *Nova 2 Sonic*: speech-to-speech(음성-음성) 대화형 모델  
  - *Nova 2 Lite*: “fast, cost-effective reasoning model”, **1M token context window** 명시  
  - *Nova 2 Omni*: 멀티모달 모델(Preview)[^1]  
- **Amazon Nova Forge**: 기업이 내부 데이터/도메인 전문성을 “프론티어 모델 학습 단계”에 깊게 반영하도록 돕는 프로그램/플랫폼 성격의 발표[^1]  
- **Amazon Nova Act (GA)**: 브라우저 기반 작업(폼 입력, 검색&추출, 예약, QA 등) 자동화 에이전트 구축용 서비스로, **enterprise deployments에서 90%+ reliability**를 전면에 내세움[^1]  
- **Amazon Bedrock AgentCore 기능 추가**: agent 배포를 위한 **policy control(정책 통제)** 및 **quality evaluation(품질 평가)** 강화[^1]  
- **Amazon S3 Vectors (GA)**: 벡터 저장/검색을 S3 영역으로 끌어와, 인덱스당 **최대 20억 vectors**, **100ms query latency**, **특화 DB 대비 최대 90% 비용 절감**을 제시[^1]  
- **Compute 인프라 확장**  
  - *Graviton5* 공개(“most powerful and efficient CPU”로 소개)[^1]  
  - *Trainium3 UltraServers* “이용 가능(now available)”로 대형 AI 학습/추론을 더 빠르고 저렴하게[^1]  
  - *AWS Lambda Managed Instances*: “Serverless simplicity with EC2 flexibility”를 표방(서버리스의 운영경험을 유지하면서 EC2 가격/하드웨어 선택 폭을 가져가려는 시도)[^1]  

보도 관점에서도 re:Invent 2025의 키워드를 “agentic AI”로 잡고, Bedrock/AgentCore/Trainium/Nova를 한 흐름으로 묶어 조명했습니다.[^3]  

### 2) Microsoft: 2025년 12월 공지에서 Security Copilot ‘접근성’ 확대 + 12개 보안 에이전트
Microsoft Learn의 2025년 12월 파트너 공지에 따르면,
- **Security Copilot이 Microsoft 365 E5 고객에게 제공(2025-11-18부터 롤아웃 시작)**  
- 그리고 Defender/Entra/Intune/Purview 전반에 걸친 **“12 new agents”**를 Ignite에서 발표했다고 명시합니다.[^2]  

즉, Azure 진영은 “개발 생산성 에이전트”도 중요하지만 **보안 운영 워크플로우를 에이전트로 자동화**하는 쪽에 강하게 무게를 둔 업데이트로 읽힙니다.

### 3) GCP: (2025년 12월 ‘대형 신규 서비스 발표’는 상대적으로 조용) 대신 ‘AI 인프라/에이전트 생태계’ 내러티브 강화
이번 검색 범위(“2025년 12월”)에서 AWS처럼 “12월 한 방” 형태의 GCP 대형 런치 요약 문서는 확실하게 잡히지 않았습니다. 다만 2025년 Cloud Next 흐름에서는 **TPU(예: Ironwood), Gemini 라인업, 멀티 에이전트/상호운용성(Agent2Agent)** 같은 키워드로 AI 플랫폼 확장을 강하게 밀고 있다는 정리가 보입니다.[^4]  
결과적으로 12월의 업계 헤드라인은 AWS가 가져갔고, GCP는 연중 이벤트(Next) 중심의 서사로 AI 인프라/에이전트 방향성을 지속 강화하는 구도가 더 뚜렷했습니다.

---

## 🔍 왜 중요한가
1) **“모델 성능”에서 “에이전트 운영”으로 전장 이동**
Nova 2(모델) 발표 자체도 크지만, 개발자 입장에서 더 큰 변화는 **Nova Act(업무 수행 에이전트) + Bedrock AgentCore(정책/평가) 조합**입니다. 에이전트는 “만들기”보다 **통제/평가/감사/안전장치**가 어렵고, AWS는 그 운영 레이어를 서비스로 제품화했습니다.[^1]  

2) **벡터 스토리지가 ‘전용 DB’에서 ‘오브젝트 스토리지(S3)’로 내려온 의미**
S3 Vectors가 “인덱스당 최대 20억 벡터”, “100ms”, “최대 90% 비용 절감”을 전면에 내세운 건, 검색/추천/RAG 워크로드에서 **비용 구조**가 바뀔 수 있다는 신호입니다.[^1]  
특히 이미 S3를 데이터 레이크의 표준 저장소로 쓰는 팀은, “RAG용 벡터DB”를 별도 운영하지 않고도 아키텍처를 단순화할 여지가 생깁니다(물론 지연시간/필터링/스키마 요구에 따라 전용 DB가 여전히 유리한 케이스도 남습니다).

3) **서버리스도 ‘하드웨어/가격 유연성’ 요구를 정면으로 받기 시작**
Lambda Managed Instances는 서버리스의 편의와 EC2의 선택지를 섞겠다는 방향입니다. 서버리스가 성숙하면서, 이제는 “완전 관리”만으로는 만족하지 못하고 **특정 하드웨어/비용 모델**을 요구하는 워크로드가 늘었다는 방증이죠.[^1]  

4) **보안 영역에서 ‘에이전트 번들링’이 시작**
Microsoft가 Security Copilot을 M365 E5로 확장하고 12개 보안 에이전트를 같이 밀어 넣는 건, 2026년 경쟁이 **“에이전트 기능” + “라이선스/번들”**로도 갈 수 있음을 보여줍니다. 개발팀은 결국 보안팀/감사팀과 같은 테이블에서 에이전트 운영 정책을 합의해야 합니다.[^2]  

---

## 💡 시사점과 전망
- **클라우드 3사의 공통분모: Agentic AI를 ‘플랫폼화’**
  - AWS는 Nova Act/AgentCore로 **에이전트 실행 + 통제/평가** 레이어를 빠르게 올렸고[^1]  
  - Microsoft는 Security Copilot과 보안 에이전트를 통해 **운영/보안 워크플로우 자동화**를 번들로 밀고[^2]  
  - Google은 Cloud Next를 중심으로 멀티 에이전트/상호운용성(Agent2Agent) 및 AI 인프라(예: TPU) 내러티브를 강화[^4]  
  결과적으로 2026년은 “모델 선택”보다 **에이전트를 어디서(어느 클라우드/스택에서) 안전하게 굴릴 것인가**가 구매/아키텍처 의사결정의 중심이 될 가능성이 큽니다.

- **시나리오 1: ‘에이전트 신뢰성’이 SLA/벤치마크로 제품화**
  AWS가 Nova Act에서 “90%+ reliability” 같은 표현을 공식 요약에 넣은 건, 향후 **업무 자동화 에이전트의 품질을 수치로 계약/평가**하려는 흐름의 출발점일 수 있습니다.[^1]  

- **시나리오 2: 데이터/벡터/로그가 더 강하게 ‘클라우드 네이티브 저장소’로 회귀**
  S3 Vectors 같은 움직임은 “전용 시스템 난립”을 줄이고, 오브젝트 스토리지를 중심으로 다시 모으려는 힘입니다.[^1]  
  이는 멀티클라우드 환경에서는 반대로 **데이터 이동/중복 저장 전략**을 더 어렵게 만들 수도 있어(각 클라우드의 네이티브 벡터/에이전트 스택에 묶임) 아키텍트의 판단이 중요해집니다.

---

## 🚀 마무리
2025년 12월 AWS 발표의 핵심은 “새 모델 추가”가 아니라 **AI agent를 실제 업무 자동화로 끌고 가기 위한 실행/통제/저장/인프라를 한꺼번에 내놓은 것**입니다(Nova Act, Bedrock AgentCore, S3 Vectors, Graviton5/Trainium3 등).[^1]  
개발자에게 권장하는 액션은 세 가지입니다.

1) **PoC 우선순위를 “에이전트 운영”에 두기**: 프롬프트보다 policy/eval/로그/권한 설계를 먼저 잡아보세요(AgentCore류 관점).[^1]  
2) **벡터 스토리지 비용 재산정**: 전용 벡터DB를 쓰고 있다면 S3 Vectors 같은 옵션과 비교해, 인덱스 규모/지연시간/운영비 관점에서 다시 계산하세요.[^1]  
3) **보안팀과 “에이전트 사용 정책” 합의**: Microsoft가 보안 에이전트를 번들로 확장하는 흐름을 보면, 2026년에는 에이전트 도입이 곧 보안/컴플라이언스 이슈가 됩니다.[^2]

[^1]: <https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/>
[^2]: <https://learn.microsoft.com/en-us/partner-center/announcements/2025-december>
[^3]: <https://www.itpro.com/cloud/live/aws-re-invent-2025-all-the-news-updates-and-announcements-live-from-las-vegas>
[^4]: <https://www.itpro.com/cloud/live/google-cloud-next-2025-all-the-news-and-updates-live>
