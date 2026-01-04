---
title: "Kubernetes v1.35 출시부터 Docker Desktop 12월 연속 업데이트까지: 2025년 12월 클라우드 네이티브 판이 바뀌는 신호들"
date: 2025-12-30 02:11:47 +0900
categories: [DevOps, News]
tags: [devops, news, trend, 2025-12]
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
2025년 12월 클라우드 네이티브 업계는 **Kubernetes v1.35 정식 릴리스(12/17)**와 **Docker Desktop 12월 릴리스(12/04, 12/16)**를 축으로 “운영 안정성·보안·런타임/개발자 경험”을 동시에 끌어올리는 흐름이 두드러졌습니다. 특히 Kubernetes 쪽은 기능 추가만큼이나 **생태계 컴포넌트 유지보수 리스크(예: Ingress NGINX)**가 전면으로 올라왔다는 점이 인상적입니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))

---

## 📰 무슨 일이 있었나
- **2025-12-17: Kubernetes v1.35.0 릴리스**  
  Kubernetes 공식 블로그에서 v1.35(코드네임 Timbernetes) 릴리스를 공개했습니다. 이번 릴리스에서 눈에 띄는 팩트는 크게 3가지입니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
  1) **Dynamic Resource Allocation(DRA)**: v1.34에서 core 기능이 stable이 된 뒤, v1.35에서는 **항상 활성화(always enabled)** 되는 방향으로 정리되었습니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
  2) **resourceVersion semantics 변경**: 기존에는 “문자열 동일성(equality)” 수준으로만 취급하던 resourceVersion이, v1.35부터는 **비교 가능한(Comparable) 형태의 decimal number**라는 더 엄격한 정의를 갖게 되었다고 설명합니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
  3) **Ingress NGINX retirement 언급**: v1.35 릴리스 글에서 커뮤니티 차원에서 Ingress NGINX가 “유지보수 불가능에 가까운 상태”가 되었고, **2026년 3월까지 best-effort maintenance**, 이후 **아카이브(추가 업데이트 없음)** 예정임을 강조했습니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  

- **2025-12-15: CNCF 블로그에서 2025년 Kubernetes 보안 변화 요약 및 2026 프리뷰 게시**  
  CNCF 블로그는 2025년에 stable로 자리 잡은 보안 관련 기능들과, v1.35 기준 alpha/beta로 2026년에 영향이 커질 항목들을 정리했습니다. 예로 **Robust image pull authorization(KEP-2535, v1.35 beta)**, **Pod certificates for mTLS(KEP-4317, v1.35 beta)**, **User namespaces for pods(v1.35에서 beta/on-by-default)** 등이 언급됩니다. ([cncf.io](https://www.cncf.io/blog/2025/12/15/kubernetes-security-2025-stable-features-and-2026-preview/?utm_source=openai))  

- **2025-12-04 / 2025-12-16: Docker Desktop 4.54.0 / 4.55.0 릴리스**  
  Docker Desktop 릴리스 노트 기준으로 12월에 **4.54.0(12/04)**, **4.55.0(12/16)**이 연속 공개됐습니다. ([docs.docker.com](https://docs.docker.com/desktop/release-notes/?utm_source=openai))  
  - 4.54.0은 Windows에서 **Docker Model Runner의 vLLM 지원(WSL2 + NVIDIA GPU)** 추가가 “New”로 명시됐고, 업그레이드 항목에 **Buildx v0.30.1**, **Engine v29.1.2**, **runc v1.3.4**가 포함됩니다. 또한 **진단 번들에 Hub PAT가 노출될 수 있던 보안 이슈(CVE-2025-13743)** 패치도 적시되어 있습니다. ([docs.docker.com](https://docs.docker.com/desktop/release-notes/?utm_source=openai))  
  - 4.55.0은 **Engine v29.1.3**로 업데이트되었고, “Wasm workloads will be deprecated and removed in a future Docker Desktop release.”라는 **Wasm 워크로드 디프리케이션 예고**가 “Important”로 들어갔습니다. ([docs.docker.com](https://docs.docker.com/desktop/release-notes/?utm_source=openai))  

---

## 🔍 왜 중요한가
1) **Kubernetes는 ‘기능 + 운영 모델’이 같이 바뀌고 있다**  
   DRA가 “항상 활성화”로 굳어지는 건, GPU/가속기 같은 디바이스 자원 관리가 더 이상 실험적 영역이 아니라 **기본 운영 가정(default assumption)**이 되고 있다는 신호입니다. 즉, 스케줄링/자원 할당/디바이스 관리가 점점 표준화되는 방향이고, 플랫폼 팀은 디바이스 플러그인 기반 설계만 고집하기보다 DRA 로드맵을 함께 봐야 합니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  

2) **클라이언트/컨트롤러 신뢰성에 직결되는 resourceVersion 변화**  
   resourceVersion을 “비교 가능”하게 정의한 건 겉보기엔 API 디테일이지만, Kubernetes가 직접 언급하듯 informer 성능/신뢰성, 스토리지 버전 마이그레이션 같은 **컨트롤 플레인·클라이언트 일관성 문제**와 연결됩니다. 운영 환경에서 watch 재연결/이벤트 유실 감지 등과 맞물리면, 장기적으로는 컨트롤러의 장애 복구 패턴에도 영향이 갈 수 있습니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  

3) **Ingress NGINX retirement는 ‘기술’이 아니라 ‘리스크 관리’ 이슈**  
   Ingress NGINX는 사실상 표준처럼 쓰인 곳이 많습니다. 그런데 Kubernetes 공식 채널에서 “best-effort until 2026-03, then archived”를 명확히 못 박았다는 건, 이제 이건 선택의 문제가 아니라 **마이그레이션 계획을 세워야 하는 일정 이슈**가 되었습니다. 특히 규제/보안 요구가 있는 조직일수록 “best-effort”는 내부 감사 관점에서 리스크로 해석될 수 있습니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  

4) **Docker Desktop은 ‘컨테이너 개발 도구’에서 ‘AI 개발 런타임’ 성격이 강해짐**  
   12/04 릴리스에서 vLLM 지원이 “New”로 들어간 것은, 로컬 개발 환경에서 컨테이너가 단지 앱 실행 단위를 넘어 **모델 실행(추론) 개발 워크플로우**까지 끌어안고 있다는 흐름입니다. 동시에 진단 번들(PAT 노출) 같은 이슈를 보면, 개발자 도구도 이제는 **보안 경계의 일부(credential handling)**로 관리해야 합니다. ([docs.docker.com](https://docs.docker.com/desktop/release-notes/?utm_source=openai))  

---

## 💡 시사점과 전망
- **클라우드 네이티브의 무게중심이 “스펙/기능”에서 “운영 가능성(maintainability)·보안·표준 런타임”으로 이동**  
  Kubernetes v1.35 릴리스 글에서조차 Ingress NGINX의 유지보수 현실을 크게 다룬 것은, 커뮤니티가 “많이 쓰이는 컴포넌트”를 더 이상 자동으로 떠안기 어렵다는 메시지로 읽힙니다. 2026년 3월(maintenance 종료)이라는 명확한 시한이 생긴 만큼, 2026 상반기에는 **Ingress 대체(또는 Gateway API 기반 재설계) 논의가 급격히 늘어날 가능성**이 큽니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  

- **Kubernetes 보안 기능은 ‘점진적 상향 평준화’ 패턴**  
  CNCF 보안 정리 글이 보여주듯, 2025년에 stable로 올라온 항목(토큰/사이드카/마운트/권한 부여 디테일 등)은 운영팀이 “선택”으로 두기 어려운 기본기 영역입니다. 그리고 v1.35의 beta/alpha 항목(robust image pull authorization, Pod certificates 등)은 2026년에 정책/표준(예: registry auth, workload identity) 쪽 논쟁을 더 키울 수 있습니다. ([cncf.io](https://www.cncf.io/blog/2025/12/15/kubernetes-security-2025-stable-features-and-2026-preview/?utm_source=openai))  

- **Docker Desktop의 Wasm 디프리케이션 예고는 ‘로컬 런타임 전략 재정렬’ 신호**  
  Docker Desktop이 Wasm 워크로드 제거를 예고했다는 건(시점은 “future release”로만 표기), 적어도 Desktop 제품 안에서 Wasm을 중심축으로 밀어붙이기보다는 다른 방향(예: AI/Model Runner 강화)에 리소스를 더 싣는 선택일 수 있습니다. Wasm 기반 로컬 실행/테스트에 기대를 걸었던 팀이라면 영향도를 점검해야 합니다. ([docs.docker.com](https://docs.docker.com/desktop/release-notes/?utm_source=openai))  

---

## 🚀 마무리
2025년 12월의 핵심은 **Kubernetes v1.35(2025-12-17)**로 대표되는 “플랫폼 기본 동작의 재정의(DRA 상시화, resourceVersion semantics 강화)”와, **Docker Desktop 12월 릴리스(2025-12-04, 2025-12-16)**에서 보이는 “AI 개발 경험 강화 + 보안 이슈 즉시 대응 + Wasm 디프리케이션 예고”로 요약됩니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  

개발자/플랫폼 팀 권장 액션:
- (Kubernetes) v1.35 릴리스 노트를 기준으로 **클라이언트/컨트롤러가 resourceVersion 비교 가능성 변화에 영향받는지** 점검하고, 디바이스 자원 사용 워크로드는 **DRA 기반 설계/테스트**를 서둘러 보세요. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
- (Ingress) **Ingress NGINX는 2026년 3월 이후 ‘업데이트 없음’**이 전제이므로, 지금부터 대체 옵션 검증과 마이그레이션 타임라인을 문서화하는 게 안전합니다. ([kubernetes.io](https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/?utm_source=openai))  
- (Docker) Docker Desktop을 조직 표준으로 쓰는 경우, 12월 릴리스의 **보안 패치/진단 번들 이슈**를 근거로 업데이트 정책(자동 업데이트/최소 버전)을 재정비하고, Wasm 워크로드 사용 여부도 미리 파악해 두는 편이 좋습니다. ([docs.docker.com](https://docs.docker.com/desktop/release-notes/?utm_source=openai))