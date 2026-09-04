---
title: "12월 클라우드 3사 신제품 전쟁: AWS는 ‘Agent + Multicloud’, GCP는 ‘Agent Engine GA’, Azure는 ‘Foundry + 새 DB’로 판이 커졌다"
description: "2025년 12월(특히 AWS re:Invent 2025 전후) 클라우드 업계의 신규 서비스 발표 흐름은 한마디로 “AI agent의 생산 배치(Production) + Multicloud 연결성”으로 수렴했습니다."
date: 2025-12-22 02:22:30 +0900
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
2025년 12월(특히 AWS re:Invent 2025 전후) 클라우드 업계의 신규 서비스 발표 흐름은 한마디로 **“AI agent의 생산 배치(Production) + Multicloud 연결성”**으로 수렴했습니다. AWS는 re:Invent에서 대규모 런치를 쏟아냈고, GCP와 Azure도 12월 업데이트에서 **agent 운영 기능과 데이터/거버넌스 축**을 강화했습니다.[^1]

---

## 📰 무슨 일이 있었나
### AWS: re:Invent 2025(2025년 12월 1~5일, 라스베이거스) 중심으로 “AI agent + 인프라” 런치 폭발
AWS는 re:Invent 2025 이후 공식 요약 포스트에서 다음과 같은 **신규 서비스/기능/제품**을 ‘Top announcements’로 정리했습니다.[^1]

- **AWS Lambda Managed Instances**: “Serverless simplicity with EC2 flexibility”를 표방하며, Lambda를 **EC2 컴퓨트 위에서** 운영하면서도 관리 부담을 AWS가 가져가는 형태를 제시[^1]  
- **AWS Lambda Durable Functions**: 멀티스텝 워크플로우를 **최대 1년까지** 신뢰성 있게 코디네이션(오케스트레이션)[^1]  
- **AWS Interconnect – Multicloud (Preview)**: Amazon VPC와 **다른 클라우드 환경 간 private, secure, high-speed 연결**을 내세운 멀티클라우드 네트워킹. **Google Cloud가 첫 런치 파트너**로 ‘preview’ 시작, **Azure 지원은 2026년 예정**[^2]  
- **AWS DevOps Agent (Preview)**: CloudWatch, GitHub, ServiceNow 등과 연계해 **incident response를 자동화/가속**한다는 ‘자율형 on-call 엔지니어’ 콘셉트[^1]  
- **AWS Security Agent (Preview)**: 설계~배포까지 AppSec를 확장(디자인 리뷰/코드 분석 등)하는 에이전트형 보안 기능[^1]  
- **AWS Transform custom / Windows modernization / mainframe(Reimagine + automated testing)**: 레거시 현대화를 AI로 자동화(“execution time up to 80% 단축” 등)[^1]  
- **Database Savings Plans**: DB 워크로드 비용 최적화를 위한 신규 pricing 모델[^1]  
- **Graviton5**, **Trainium3 UltraServers(Trn3, 3nm)** 등 커스텀 실리콘 라인업 확대[^1]  

또한 AWS News Blog(Weekly Roundup, 2025년 12월 8일)는 re:Invent 이후 추가 런치로:
- **Kiro Autonomous Agent**(Kiro GA는 11월, 12월에는 autonomous agent 소개)[^2]  
- **Multimodal Retrieval for Bedrock Knowledge Bases (GA)**: 텍스트/이미지/오디오/비디오를 함께 인덱싱·검색하는 멀티모달 RAG 계열 기능[^2]  
를 언급했습니다.

### GCP: 2025년 12월 중순 릴리스 노트에서 “Agent Engine GA + 백업/거버넌스” 강화
12월 16일자 GCP 릴리스 노트(정리본) 기준으로 눈에 띄는 변화는 다음입니다.
- **Vertex AI Agent Engine의 Sessions 및 Memory Bank가 GA**[^3]  
- Vertex AI Agent Engine의 **pricing 변경(런타임 가격 인하)** 및 **2026년 1월 28일부터 Sessions/Memory Bank/Code Execution 과금 시작** 예고[^3]  
- **Cloud SQL enhanced backups GA**: Backup and DR 기반 중앙 관리, 보존 정책/스케줄링 강화, 그리고 **인스턴스 삭제 후 PITR 지원**[^3]  
- **Cloud Hub GA**, BigQuery Data Transfer Service의 **Oracle → BigQuery 전송 GA** 등 운영/데이터 측면 확장[^3]  

### Azure: 2025년 12월 업데이트에서 “Foundry 모델 선택지 + 새 PostgreSQL DB(Private Preview) + Agent 거버넌스”
Microsoft의 12월 파트너 업데이트 포스트 기준 하이라이트는:
- **Microsoft Foundry에 Anthropic Claude 모델 제공**(모델 선택지 확대)[^4]  
- **Azure HorizonDB for PostgreSQL (Private Preview)**: 미션 크리티컬/AI 워크로드를 겨냥한 신규 PostgreSQL 클라우드 DB로 소개[^4]  
- **Microsoft Agent 365**: Microsoft 365, Azure, Foundry 전반의 **AI agent 거버넌스/관리(control plane)** 성격을 강조[^4]  

---

## 🔍 왜 중요한가
1) **“AI agent”가 더 이상 데모가 아니라 운영 대상이 됐다**
- AWS는 DevOps Agent, Security Agent처럼 **운영/보안 책임 영역**을 agent로 끌고 들어왔고(프리뷰), GCP는 Agent Engine의 Sessions/Memory Bank를 GA로 올리면서 **agent의 상태/기억/세션**이 ‘제품 기능’으로 굳어졌습니다.[^1]  
- 개발자 관점에서 포인트는 “agent를 붙인다”가 아니라, **agent를 프로덕션에서 통제·감사·관찰(Observability) 가능한 형태로 운영**해야 한다는 겁니다. (세션/메모리/정책/로그/비용)

2) **멀티클라우드의 무게중심이 “네트워크 + 프라이빗 연결”로 이동**
- AWS Interconnect – Multicloud는 “첫 파트너가 Google Cloud”이고, Azure는 2026년 지원을 예고했습니다. 즉, 멀티클라우드는 문서/거버넌스만의 문제가 아니라 **저지연·고대역 private path를 표준 상품으로** 밀어붙이는 단계로 들어갑니다.[^2]  
- 팀 입장에선 향후 아키텍처 설계 시, VPN/터널링을 ‘직접 구성’하기보다 **클라우드 사업자가 제공하는 멀티클라우드 인터커넥트 상품을 기본 옵션으로 검토**하게 될 가능성이 큽니다.

3) **DB/백업이 ‘AI 시대 운영 리스크’의 핵심으로 재부상**
- GCP의 Cloud SQL enhanced backups GA와 “삭제 후 PITR”은 실무적으로 강합니다. AI/데이터 파이프라인이 커질수록 사람 실수(삭제/변경) 복구가 비용/신뢰를 좌우하니까요.[^3]  
- AWS는 Database Savings Plans로 비용 모델을 손봤고, Azure는 HorizonDB(Private Preview)로 Postgres 계열을 다시 전면에 내세웠습니다.[^1]  

---

## 💡 시사점과 전망
- **2026년은 ‘agent 플랫폼 간 표준 경쟁’**이 본격화될 가능성이 큽니다. GCP가 Sessions/Memory Bank를 GA로 두고 2026년 1월 28일부터 과금을 시작한다는 건, 결국 “agent 런타임의 단가/과금 모델”이 주요 비교 지표가 된다는 뜻입니다.[^3]  
- AWS의 Multicloud Interconnect가 “GCP부터 시작”했다는 점은 상징적입니다. 협업이든 견제든, 고객은 결국 **AWS↔GCP 간 워크로드/데이터 이동과 연계**를 더 쉽게 요구할 테고, Azure까지 포함한 삼각 구도에서 **네트워크 상품/가격/연동 범위**가 중요한 선택 기준이 될 겁니다.[^2]  
- Azure는 Foundry로 **모델 허브 + 거버넌스**를 강화하고, Agent 365로 “agent를 엔터프라이즈 자산으로 관리”하는 메시지를 밀고 있습니다. AWS/GCP가 기술 스택을 밀어 올릴수록, Azure는 M365까지 포함한 운영/관리 접점을 무기로 가져갈 가능성이 있습니다.[^4]  

---

## 🚀 마무리
12월 2025 신규 발표를 한 줄로 정리하면, **“클라우드는 이제 Infra 경쟁을 넘어 ‘Agent를 어떻게 안전하게 굴릴 것인가’와 ‘멀티클라우드를 어떻게 물리적으로 잇는가’의 경쟁”**으로 넘어왔습니다.[^1]  

개발자에게 권장하는 액션은 3가지입니다.
1) agent 도입 시 기능보다 먼저 **세션/메모리/로그/권한/비용** 운영 설계를 체크리스트화(특히 GCP는 2026-01-28 과금 전 전환 계획)[^3]  
2) 멀티클라우드를 쓰고 있다면, 2026년을 대비해 **private interconnect 계열(예: AWS Interconnect – Multicloud preview)**을 PoC 항목에 올리기[^2]  
3) 데이터 사고는 결국 복구력 싸움이므로, Cloud SQL enhanced backups 같은 **백업/복구 기능의 ‘GA 성숙도’**를 서비스 선택 기준에 명시[^3]

[^1]: <https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/?hp=rei-annc>
[^2]: <https://aws.amazon.com/blogs/aws/aws-weekly-roundup-aws-reinvent-keynote-recap-on-demand-videos-and-more-december-8-2025/>
[^3]: <https://mwpro.co.uk/blog/2025/12/17/gcp-release-notes-december-16-2025/>
[^4]: <https://partner.microsoft.com/th-th/blog/article/azure-updates-december-2025>
