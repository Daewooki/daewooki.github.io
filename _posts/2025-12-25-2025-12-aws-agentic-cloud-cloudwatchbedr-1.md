---
title: "2025년 12월 AWS가 던진 ‘Agentic Cloud’ 신호탄: CloudWatch·Bedrock AgentCore·Nova 2가 바꿀 운영 패러다임"
date: 2025-12-25 02:10:52 +0900
categories: [Infrastructure, News]
tags: [infrastructure, news, trend, 2025-12]
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
2025년 12월(정확히는 AWS re:Invent 2025 기간인 11월 30일~12월 4일 전후) AWS는 “AI agents를 실제 운영에 올리는 방법”을 제품 레벨로 대거 발표했습니다. 핵심은 모델 자체보다 **agent 운영(Observability, Policy, Evaluation, Incident 대응 자동화)**을 AWS 관리형 서비스로 흡수하기 시작했다는 점입니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))

---

## 📰 무슨 일이 있었나
- **2025년 11월 30일 ~ 12월 4일(라스베이거스)** 진행된 **AWS re:Invent 2025**에서 주요 신규 서비스/기능이 공개됐고, AWS News Blog가 **2025년 12월 5일(업데이트 시각 12:57 p.m. PST)** 기준으로 ‘Top announcements’를 정리했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  
- AI/Agent 중심으로 눈에 띄는 발표는 다음과 같습니다. (일부는 GA, 일부는 Preview로 발표)
  - **Amazon Nova 2 라인업**: *Nova 2 Sonic(음성-음성), Nova 2 Lite(Reasoning), Nova 2 Omni(Preview, multimodal)* 등 모델 포트폴리오를 확장했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  
  - **Amazon Nova Act (GA)**: 브라우저 기반 UI 작업 자동화 에이전트를 겨냥한 서비스로, 엔터프라이즈 워크플로우 자동화를 전면에 내세웠습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  
  - **Amazon Bedrock AgentCore**: 에이전트를 “배포 가능한 시스템”으로 만들기 위한 **policy controls**, **quality evaluations**, **memory** 관련 기능을 추가했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  
  - **AWS DevOps Agent (Preview)**: CloudWatch, GitHub, ServiceNow 등과 연계해 **incident 원인 분석 및 대응 조율**을 수행하는 “자율 on-call 엔지니어” 성격을 강조했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  
- 운영/관측(Observability) 쪽에선 re:Invent 2025 “Cloud Operations” 축에서 다음 메시지가 강하게 나왔습니다.
  - **Amazon CloudWatch의 Generative AI observability**: latency, token usage, errors 등 **AI 워크로드 텔레메트리**를 기본 제공 형태로 관측하는 방향을 제시했습니다. 또한 **Bedrock AgentCore** 및 LangChain/LangGraph/CrewAI 등과의 호환을 언급했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/mt/2025-top-10-announcements-for-aws-cloud-operations/?utm_source=openai))  
  - re:Invent 세션 안내에서도 **Bedrock AgentCore**, **ADOT(AWS Distro for OpenTelemetry)** 기반 계측, 그리고 CloudWatch로 agent/model telemetry를 시각화하는 흐름을 전면에 배치했습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/mt/embracing-ai-driven-operations-and-observability-at-reinvent-2025/?utm_source=openai))  

---

## 🔍 왜 중요한가
1) **“Agent 운영”이 제품화됐다 (코드가 아니라 런타임의 문제)**  
지금까지 agent 개발의 고통은 프롬프트보다 **운영**이었습니다. 관측(토큰/지연/에러), 정책(무엇을 해도 되는가), 평가(좋은 답이었나), 사고 대응(장애 시 누가 무엇을 판단하나)이 분리돼 있었는데, AWS는 이를 **CloudWatch + Bedrock AgentCore + DevOps Agent** 축으로 관리형 영역에 넣고 있습니다. ([aws.amazon.com](https://aws.amazon.com/blogs/mt/2025-top-10-announcements-for-aws-cloud-operations/?utm_source=openai))  

2) **Observability의 중심이 “서비스”에서 “AI workflow/agent”로 이동**  
CloudWatch가 GenAI 지표(토큰, 지연, 오류)를 대놓고 1st-class로 취급하기 시작했다는 건, 앞으로 SRE/DevOps의 대시보드에 **CPU/Latency뿐 아니라 Token/Model Invocation/Agent Trace**가 자연스럽게 들어온다는 뜻입니다. 개발자는 “agent가 왜 그런 결정을 했는지”를 추적할 수 있어야 하고, 이는 분산 트레이싱의 확장판(의사결정 트레이스)으로 흘러갑니다. ([aws.amazon.com](https://aws.amazon.com/blogs/mt/2025-top-10-announcements-for-aws-cloud-operations/?utm_source=openai))  

3) **UI Automation(Nova Act) + Incident 대응(DevOps Agent) 조합의 파급력**  
Nova Act가 “브라우저 기반 작업 자동화”를 GA로 내놓고, DevOps Agent가 “on-call 자동화”를 Preview로 제시한 흐름은 공통적으로 **사람이 하던 클릭/조사/조율 업무를 agent가 가져가려는 시도**입니다. 즉, 단순 챗봇이 아니라 실제 운영 절차(runbook)·업무 프로세스까지 클라우드 벤더가 흡수합니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  

4) (멀티클라우드 관점) **MCP(Model Context Protocol)처럼 ‘에이전트-도구 연결 표준’이 경쟁 지점으로 부상**  
AWS 쪽에서도 MCP 서버(예: IAM Policy Autopilot MCP server 같은 오픈소스 형태)를 발표했고, Azure는 **Azure MCP Server**를 공개/업데이트하며 여러 Azure 서비스(Azure AI Search, PostgreSQL, Key Vault, Kusto 등)와의 연결을 확장하고 있습니다. 이제 “누가 모델이 더 똑똑한가”보다 “누가 도구 연결을 더 안전하고 표준적으로 제공하는가”가 더 중요해질 가능성이 큽니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  

---

## 💡 시사점과 전망
- **클라우드 3사(AWS/GCP/Azure)의 경쟁 축이 ‘모델 성능’에서 ‘Agent Platform’으로 이동**  
AWS는 Bedrock AgentCore(정책/평가/메모리) + CloudWatch(GenAI observability) + DevOps Agent(incident 자동화)로 “운영 가능한 agent” 스택을 쌓고 있습니다. Azure는 MCP Server를 통해 개발 도구/서비스 연결을 넓히는 방향을 보여줍니다. 이 흐름이 이어지면 2026년엔 “agent 운영 콘솔/거버넌스”가 DB 콘솔만큼 중요해질 겁니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  
- **표준화(MCP)와 계측(OpenTelemetry 계열)의 결합이 가속**  
re:Invent 세션에서 ADOT 기반 계측을 전면에 두는 것처럼, 벤더 종속을 줄이려면 “계측 표준 + 도구 연결 표준”이 필수입니다. 멀티클라우드를 쓰는 팀일수록 agent observability와 tool integration을 특정 벤더 콘솔에만 묶으면 회수 비용이 커질 수 있어, 초기에 설계를 잘 해야 합니다. ([aws.amazon.com](https://aws.amazon.com/blogs/mt/embracing-ai-driven-operations-and-observability-at-reinvent-2025/?utm_source=openai))  
- **가까운 시나리오(6~12개월): 운영팀에 ‘Agent SRE’ 역할이 생긴다**  
서비스 장애 때 “로그/메트릭”만 보는 것이 아니라, “agent의 행동 이력, policy 위반 여부, 평가 점수 변화”까지 함께 보게 됩니다. 이는 운영 조직의 역량 요구사항을 바꾸고, DevOps 파이프라인에도 agent 평가/정책 검증 단계가 들어갈 가능성이 큽니다. ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  

---

## 🚀 마무리
2025년 12월 AWS 발표의 요지는 “AI agent를 만들었다”가 아니라, **AI agent를 운영할 수 있게 만들었다**입니다(관측/정책/평가/사고대응의 제품화). ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  

개발자 권장 액션은 3가지입니다.
1) CloudWatch 중심으로 **GenAI 지표(토큰/지연/오류) 관측 설계**를 기존 APM 설계에 포함시키기 ([aws.amazon.com](https://aws.amazon.com/blogs/mt/2025-top-10-announcements-for-aws-cloud-operations/?utm_source=openai))  
2) Bedrock AgentCore/유사 플랫폼을 쓸 경우, **policy controls + quality evaluations**를 “나중에”가 아니라 MVP 단계부터 파이프라인에 넣기 ([aws.amazon.com](https://aws.amazon.com/blogs/aws/top-announcements-of-aws-reinvent-2025/))  
3) 멀티클라우드 팀이라면 MCP 같은 흐름을 주시하면서, **도구 연결과 권한 모델을 표준/분리 구조로 설계**해 벤더 락인 리스크를 관리하기 ([devblogs.microsoft.com](https://devblogs.microsoft.com/azure-sdk/azure-mcp-server-may-2025-release/?utm_source=openai))