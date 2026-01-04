---
title: "Kubernetes v1.35와 Docker Desktop 4.54~4.55가 말해주는 2025년 12월 Cloud Native의 “보안·생산성” 전환점"
date: 2026-01-04 02:30:36 +0900
categories: [DevOps, News]
tags: [devops, news, trend, 2026-01]
---

<div class="pageviews" style="margin: 0.25rem 0 1rem; opacity: 0.8;">
  <span style="font-weight: 600;">조회수</span>: <span id="pv-post">-</span>
</div>
<script defer src="/assets/js/pageviews.js"></script>


## 들어가며
2025년 12월 클라우드 네이티브 진영에서 가장 눈에 띈 소식은 **Kubernetes v1.35 정식 릴리스(12/17)**와 **Docker Desktop 12월 릴리스 라인(12/04, 12/16)**입니다. 공통 키워드는 명확합니다. “기능 추가”보다 **보안 강화(credential, token, image access)**와 **개발자 경험(로컬/데스크톱 워크플로우)** 쪽으로 무게중심이 이동했습니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))

---

## 📰 무슨 일이 있었나
- **2025년 12월 17일**, Kubernetes 프로젝트가 **Kubernetes v1.35 “Timbernetes (The World Tree Release)”**를 발표했습니다. 이번 릴리스에서 눈여겨볼 변화는 다음과 같습니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
  - **kubelet의 “cached image credential verification”**이 **beta로 승격**되며 **기본 활성화(enabled by default)**: `imagePullPolicy: IfNotPresent`로 노드에 캐시된 private image를 쓰는 경우에도, Pod가 해당 이미지를 pull할 자격(credential)을 갖고 있는지 **kubelet이 검증**하도록 강화. 필요 시 `KubeletEnsureSecretPulledImages` feature gate로 비활성화 가능. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
  - **Container 단위 restartPolicy / restartPolicyRules**가 **beta + 기본 활성화**: Pod-level restartPolicy 한계(복잡 워크로드, AI/ML 잡 등)를 줄이고, 컨테이너별로 더 세밀한 재시작 규칙을 정의할 수 있게 됨. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
  - **StatefulSet RollingUpdate에 `maxUnavailable`**이 **beta**로(기본 사용 가능): stateful workload 업데이트 속도를 끌어올릴 여지. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
  - 인증/보안 측면에서 **CSI driver가 ServiceAccount token을 secrets 필드로 받는 opt-in 방식** 등, “토큰이 로그/평문 경로로 새는 위험”을 줄이려는 개선들이 포함. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  

- **2025년 12월 4일**, Docker가 **Docker Desktop 4.54.0** 릴리스를 공개했습니다. 주요 포인트는: ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))  
  - **Docker Model Runner**에서 **Windows(WSL2) + NVIDIA GPU 환경의 vLLM 지원** 추가  
  - 구성요소 업그레이드: **Docker Engine v29.1.2**, **Buildx v0.30.1**, **runc v1.3.4** 등 ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))  
  - **CVE-2025-13743** 관련: diagnostics bundle 로그 출력에 Hub PAT가 섞여 들어갈 수 있었던 이슈에 대한 **보안 패치** 언급 ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))  

- **2025년 12월 16일**, Docker가 **Docker Desktop 4.55.0**을 릴리스했습니다. 엔진은 **Docker Engine v29.1.3**로 업데이트됐고, “startup에서 멈춤” 같은 안정성 이슈를 수정했습니다. 또한 **Wasm workloads가 향후 Docker Desktop에서 deprecated/removed 예정**이라는 공지가 함께 실렸습니다. ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))  

---

## 🔍 왜 중요한가
1) **Kubernetes의 이미지 접근 모델이 더 “엄격한 기본값”으로 이동**
- v1.35의 핵심 중 하나는 “노드에 캐시돼 있으면 자격 없이도 쓸 수 있는” 구멍을 줄이는 방향입니다. 멀티테넌트 클러스터나 shared node 환경에서는 이게 실제 보안 사고로 이어질 수 있는데, 이번엔 **beta이면서 기본 활성화**라서 업그레이드 시 체감 변화가 큽니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
- 개발자 관점에서 영향: “어제까지는 잘 뜨던 Pod가 오늘은 ImagePull/권한 문제로 막힘” 같은 업그레이드 이슈가 발생할 수 있으니, **imagePullSecrets / registry auth 체계**를 점검해야 합니다.

2) **운영/플랫폼 팀에 유리한: 정책·보안·업데이트 속도 개선이 한 번에 들어옴**
- StatefulSet의 `maxUnavailable` (beta)는 단순 편의가 아니라, **업데이트 윈도우/장애 허용치(SLO)**와 직결됩니다. “Stateful은 무조건 1개씩”이라는 운영 상수에서 벗어날 여지가 생깁니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
- CSI driver의 token 전달 경로 개선은 “로그로 토큰이 새는” 류의 사고 가능성을 구조적으로 낮추려는 흐름으로 읽힙니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  

3) **Docker Desktop은 ‘컨테이너 개발 환경 + 로컬 AI 런타임’ 축을 강화**
- 12월 릴리스에서 vLLM, Model Runner 같은 키워드가 전면에 있고, 동시에 diagnostics/토큰 관련 CVE 패치를 명시하는 걸 보면 “개발자 생산성 기능 확대”와 “토큰/자격증명 취급 강화”를 같이 밀고 있습니다. ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))  
- Wasm workloads deprecate 예고는, 로컬 개발 환경에서 “실험 기능”이 정리되는 신호일 수 있습니다(최소한 Docker Desktop 라인에서는). ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))  

---

## 💡 시사점과 전망
- **클라우드 네이티브의 기본값(Default)이 보안 쪽으로 더 이동**하고 있습니다. Kubernetes는 캐시 이미지 자격 검증을 “기본 ON”으로 올렸고, Docker Desktop도 diagnostics/토큰 누출을 명시적으로 다룹니다. 즉, 2026년으로 갈수록 “편하면 됨”이 아니라 **credential 경로, 로그, 캐시, 토큰 전달 방식**이 제품 경쟁력의 핵심이 될 가능성이 큽니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
- 워크로드 관점에서는 AI/ML·배치성 워크로드가 계속 압박을 주고 있고, Kubernetes는 restartPolicyRules 같은 “세밀한 제어”를 기본 기능으로 끌어올리는 중입니다. 이는 향후 플랫폼 계층(스케줄링/자원할당/잡 오케스트레이션)에서도 비슷한 방향의 개선이 이어질 신호로 봅니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
- Docker Desktop의 로컬 AI 기능 확장은, 개발자가 “클러스터 없이도” 어느 정도 실험을 끝내고 클라우드로 올리는 워크플로우를 가속할 수 있습니다. 다만 조직 표준 도구로 채택할 경우, Desktop의 보안 패치/업데이트 주기와 정책(예: deprecations)을 **운영 관점에서 따라갈 준비**가 필요합니다. ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))  

---

## 🚀 마무리
2025년 12월 흐름을 한 줄로 정리하면 **“Kubernetes는 보안·운영 기본값을 강화하고, Docker Desktop은 개발 환경과 로컬 AI 생산성을 확장한다”**입니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  

개발자/플랫폼 팀 권장 액션:
- Kubernetes 업그레이드 계획이 있다면 **v1.35의 cached image credential verification(기본 ON)**로 인해 영향받는 서비스가 없는지, **registry 인증(imagePullSecrets, SA 권한)**을 사전 점검하세요. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
- StatefulSet을 운영 중이면 `maxUnavailable` beta 도입 가능성을 검토해 **배포 시간 단축 vs 장애 허용치**를 수치로 비교해보세요. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
- Docker Desktop을 조직 표준으로 쓰는 팀은 **12월 릴리스의 CVE/토큰 관련 보안 패치**와 **Wasm deprecate 예고**를 릴리스 관리 항목에 포함시키는 걸 권합니다. ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))