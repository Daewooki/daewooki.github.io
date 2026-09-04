---
title: "AI 에이전트가 클라우드의 ‘새 기본값’이 된 2025년 12월: AWS re:Invent 발표로 본 AWS·GCP·Azure 경쟁 구도"
description: "2025년 12월, AWS는 re:Invent 2025를 통해 AI agent 중심의 대규모 신규 서비스/기능을 공개하며 “개발 생산성 + 인프라(칩/서버) + 모델 플랫폼”을 한 번에 밀어붙였습니다."
date: 2025-12-28 02:28:46 +0900
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
2025년 12월, AWS는 re:Invent 2025를 통해 AI agent 중심의 대규모 신규 서비스/기능을 공개하며 “개발 생산성 + 인프라(칩/서버) + 모델 플랫폼”을 한 번에 밀어붙였습니다. 같은 시기 Azure는 Azure Copilot과 신규 PostgreSQL 계열 DB 프리뷰를 전면에 내세웠고, GCP는 Next ’25 발표 묶음에서 인프라/쿠버네티스/추론 게이트웨이 등 AI 실행 계층을 강화했습니다.[^1]

---

## 📰 무슨 일이 있었나
- **2025년 12월 4일(최신 업데이트 기준)**, AWS는 **re:Invent 2025** 핵심 발표를 정리하며 다음을 전면에 배치했습니다.[^1]  
  - **Amazon Bedrock AgentCore**: agent를 운영(거버넌스/실행/신뢰성)하는 플랫폼 축을 강화.[^1]  
  - **Frontier Agents 3종**: **Kiro autonomous agent**, **AWS Security Agent**, **AWS DevOps Agent** 공개(“자율적으로 hours~days 단위로 동작”이라는 메시지).[^1]  
  - **Amazon Nova 2 모델 패밀리** 확장 및 **Amazon Nova Forge**(“open training” 및 체크포인트/데이터 결합 등 메시지) 발표.[^1]  
  - 인프라 측면에서 **Graviton5**, **Trainium3 UltraServers**, 그리고 **NVIDIA GB300 NVL72** 기반 **P6e-GB300 UltraServers** 등 “AI 학습/추론”용 하드웨어 라인업을 확장.[^1]

- **2025년 12월 15일**, AWS News Blog의 Weekly Roundup에서도 연말까지 출시가 이어졌습니다. 예를 들어  
  - **Amazon ECS on AWS Fargate**: 이미지의 **STOPSIGNAL**을 존중하는 “custom container stop signals” 지원  
  - **Amazon Cognito identity pools + AWS PrivateLink**: public internet 없이 private connectivity 지원  
  - **Amazon Aurora DSQL**: “cluster creation in seconds” 메시지로 프로비저닝 속도 개선  
  같은 식으로 “agent/AI만이 아니라 운영 디테일까지 계속 개선” 흐름이 확인됩니다.[^2]

- **Azure(2025년 12월 16일)**: Microsoft는 파트너 업데이트에서  
  - **Azure Copilot (private preview)**: Azure portal/PowerShell/CLI에 **specialized agents**를 붙여 migration/modernization을 가속한다는 포지션  
  - **Azure HorizonDB for PostgreSQL (private preview)**: autoscaling storage, rapid compute scale-out, vector indexing 등 “AI 워크로드 지향 DB” 메시지  
  등을 강조했습니다.[^3]

- **Google Cloud(Next ’25 wrap-up 문서)**: 단일 “12월 발표”라기보다 Next ’25 발표 묶음 형태이지만,  
  - **GKE Inference Gateway**, **GKE Inference Quickstart**, **Cluster Director for GKE(GA)** 등 “추론 운영/스케일링”에 초점을 둔 컴포넌트가 눈에 띕니다.[^4]

---

## 🔍 왜 중요한가
1) **클라우드 경쟁의 초점이 ‘모델’에서 ‘Agent 운영체계’로 이동**
- AWS는 Bedrock/AgentCore와 Frontier Agents로 “agent를 만들고(개발) 굴리고(운영) 통제(정책/검증)한다”는 풀스택을 전면에 세웠습니다. 이건 단순 LLM API 경쟁이 아니라, **DevEx + Ops + Governance**를 통째로 잠그려는 시도입니다.[^1]  
- Azure도 Copilot을 portal/CLI까지 확장해 “운영 자동화의 기본 인터페이스 = agent”를 만들려는 흐름이 뚜렷합니다.[^3]

2) **개발자는 이제 ‘서비스 선택’보다 ‘Agent 아키텍처 표준화’가 더 중요**
- 예전에는 “EKS vs GKE vs AKS” 같은 선택이 중심이었다면, 2025년 12월 발표들은 “agent가 어떤 tool을 호출하고, 어떤 권한 경계에서 실행되고, 어떻게 평가/감사되는가”가 핵심 설계 포인트가 됐습니다(특히 보안/운영 agent).[^1]

3) **인프라(칩/서버) 발표가 다시 ‘개발자 체감’ 영역으로 들어옴**
- Graviton5, Trainium3 UltraServers, NVIDIA GB300 기반 UltraServers처럼 “AI 성능/비용”을 좌우하는 하드웨어 계층이 발표의 중심축으로 재등장했습니다. AI 서비스의 비용 구조가 팀의 아키텍처(캐싱/배치/추론 전략)를 강하게 규정하기 때문에, 이제 인프라 발표는 곧 애플리케이션 설계 변경으로 이어집니다.[^1]

---

## 💡 시사점과 전망
- **단기(2026 상반기)**: 각 클라우드는 “agent 개발 도구”보다 **운영/거버넌스 통합**에서 승부를 볼 가능성이 큽니다. Azure Copilot이 portal/CLI로 들어오고, AWS는 Frontier Agents로 Dev/Sec/Ops 역할을 패키징하며, GCP는 GKE Inference 계층을 강화해 “실행 안정성”을 잡는 방향입니다.[^3]  
- **중기**: DB 계층은 “vector indexing + autoscale + AI workload”가 기본 스펙이 될 공산이 큽니다(Azure HorizonDB의 포지션이 상징적). 이때 개발자에게 중요한 건 특정 DB 브랜드가 아니라, **agent가 데이터 계층을 안전하게 호출**하도록 하는 권한/감사 설계입니다.[^3]  
- **리스크**: agent 기반 자동화가 늘수록, “누가 어떤 변경을 왜 했는지”가 모호해질 수 있습니다. 따라서 2026년에는 agent의 실행 기록, 정책, 승인(HITL) 같은 **auditability**가 차별점이 될 가능성이 높습니다(각사가 ‘신뢰/통제’ 메시지를 강하게 내는 이유).[^5]

---

## 🚀 마무리
2025년 12월 AWS 발표의 핵심은 “AI agent를 클라우드의 기본 인터페이스로 만들겠다”는 선언에 가깝고, Azure/GCP도 각자의 방식으로 같은 방향으로 수렴하고 있습니다.[^1]  

개발자 권장 액션:
- 팀 내부에 **Agent 실행 권한 경계(IAM/Policy) + 감사 로그**를 우선 설계(기능 도입보다 먼저).  
- PoC는 “모델 성능”이 아니라 **운영 시나리오(배포/롤백/보안 수정/DB 스키마 변경 등)**에서 agent가 실제로 시간을 줄이는지로 평가.  
- 2026년 대비로, 사용하는 클라우드의 **agent 운영 플랫폼(예: AgentCore/Copilot)과 데이터 계층(vector/DB)의 결합 방식**을 기술 부채 관점에서 점검.

[^1]: <https://www.aboutamazon.com/news/aws/aws-re-invent-2025-ai-news-updates//>
[^2]: <https://aws.amazon.com/blogs/aws/aws-weekly-roundup-amazon-ecs-amazon-cloudwatch-amazon-cognito-and-more-december-15-2025/>
[^3]: <https://partner.microsoft.com/fi-fi/blog/article/azure-updates-december-2025>
[^4]: <https://cloud.google.com/blog/topics/google-cloud-next/google-cloud-next-2025-wrap-up>
[^5]: <https://www.techradar.com/pro/live/aws-re-invent-2025-all-the-news-and-updates-as-it-happens>
