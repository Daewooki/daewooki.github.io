---
title: "2025년 12월, Kubernetes·Docker·클라우드 네이티브 판이 “업그레이드 압박” 국면으로 들어간 이유"
date: 2026-01-01 02:29:34 +0900
categories: [DevOps, News]
tags: [devops, news, trend, 2026-01]
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
2025년 12월은 겉으로는 “큰 사건”보다, 운영자·플랫폼 팀에게 장기적으로 치명적인 **기술 부채 청산 신호**가 또렷해진 달이었습니다. Docker Desktop은 12월 릴리스에서 보안/운영 이슈를 정리하며 개발 환경의 기본값을 다듬었고, Kubernetes는 v1.35(업스트림 2025년 12월 릴리스 예정)에서 **cgroup v1·containerd 1.x 정리** 같은 하부 스택 변화를 예고했습니다. ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))

---

## 📰 무슨 일이 있었나
- **2025-12-16, Docker Desktop 4.55.0 릴리스**
  - Docker Engine **v29.1.3** 업데이트
  - Desktop 시작 시 멈춤(stuck) 문제 등 안정성 개선
  - “Wasm workloads will be deprecated and removed in a future Docker Desktop release”라는 **Wasm 워크로드 향후 제거 예고**가 명시됨 ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))

- **2025-12-04, Docker Desktop 4.54.0 릴리스**
  - Docker Model Runner 관련 기능 업데이트(Windows vLLM 지원 등)
  - 보안 패치: **CVE-2025-13743**(진단 번들에 expired Hub PAT가 로그로 포함될 수 있었던 이슈) 대응 ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))

- **2025-11-26, Kubernetes v1.35 Sneak Peek 공개(12월 릴리스 전 사전 공지)**
  - v1.35에서 **cgroup v1 support 제거**: 오래된 Linux 배포판/구성에서 `kubelet`이 시작 실패할 수 있어 **cgroup v2로 마이그레이션 필요** ([kubernetes.io](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/?utm_source=openai))
  - v1.35에서 **kube-proxy ipvs mode deprecate** 예고(리눅스 권장 모드는 nftables 방향) ([kubernetes.io](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/?utm_source=openai))
  - v1.35이 **containerd 1.x 지원의 “마지막 릴리스”**라는 경고: 다음 버전으로 넘어가려면 containerd **2.0+** 전환 필요, `kubelet_cri_losing_support` 메트릭으로 사전 점검 권장 ([kubernetes.io](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/?utm_source=openai))

- **(클라우드 운영 관점) AKS 문서에서 드러난 2025년 말~2026년 초 업그레이드 압박**
  - AKS: **2025-11-30부터 Azure Linux 2.0 지원/보안 업데이트 중단**, **2026-03-31 노드 이미지 제거 및 스케일 불가** 예고(문서에 명시) ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions?utm_source=openai))
  - AKS 표 기준으로 **Kubernetes 1.35 업스트림 릴리스가 2025년 12월**로 잡혀 있고, AKS는 2026년 프리뷰/GA 타임라인을 제시 ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions?utm_source=openai))

---

## 🔍 왜 중요한가
1) **“Kubernetes 버전 업”이 곧 “노드 OS·cgroup·runtime 업”으로 바뀜**  
v1.35에서 cgroup v1이 제거되면, 단순히 control plane만 올리는 문제가 아니라 **노드 이미지/커널/런타임 호환성**까지 한 번에 정리해야 합니다. 특히 오래된 배포판이나 레거시 노드 풀을 끌고 가던 팀은 “업그레이드 = 프로젝트”가 됩니다. ([kubernetes.io](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/?utm_source=openai))

2) **containerd 1.x 종료 카운트다운은 “클러스터 전반”에 영향**  
Kubernetes가 v1.35를 containerd 1.x 지원의 마지막으로 못 박으면서, 다음 버전(차기 minor)에서 runtime 미전환 노드는 업그레이드 자체가 막히거나 운영 리스크가 커질 수 있습니다. 즉, 2025년 12월은 “언젠가 하자”가 아니라 **전환 계획을 지금 세워야 하는 분기점**입니다. ([kubernetes.io](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/?utm_source=openai))

3) **개발 환경(Docker Desktop)도 “보안/기능 정리”가 가속**  
12월 릴리스에서 CVE 대응이 명시되고, Wasm 워크로드 제거 예고까지 들어왔습니다. 로컬 개발/테스트 파이프라인에서 Docker Desktop을 표준으로 쓰는 조직은 **버전 고정, 보안 점검, 기능 의존성(Wasm 등) 재검토**가 필요합니다. ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))

---

## 💡 시사점과 전망
- **클라우드 네이티브의 다음 경쟁 포인트는 “기능 추가”보다 “기반 스택 정합성”**  
cgroup v2 전환, nftables 방향성, containerd 메이저 전환 같은 변화는 화려하진 않지만, 플랫폼의 안정성과 보안 posture를 좌우합니다. 2026년에는 “Kubernetes 최신 기능”보다 **업그레이드 가능한 플랫폼 설계(immutable node, 표준 런타임, 이미지 수명주기)**가 팀 생산성을 가를 가능성이 큽니다. ([kubernetes.io](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/?utm_source=openai))

- **관리형 Kubernetes(예: AKS)에서도 OS 이미지 수명주기(EOL)가 더 직접적인 제약으로**  
AKS의 Azure Linux 2.0 EOL/제거 일정처럼, “Kubernetes 버전 지원 정책”과 별개로 **노드 OS SKU/이미지 정책**이 업그레이드 트리거가 됩니다. 앞으로는 클러스터 업그레이드 계획을 세울 때, K8s minor뿐 아니라 **노드 이미지/OS 지원 종료 캘린더**를 같이 운영해야 합니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions?utm_source=openai))

- **Docker Desktop은 “개발자 도구”에서 “조직 보안 경계의 일부”로**  
진단 번들/토큰 로그 같은 이슈가 반복적으로 패치되는 흐름은, Desktop이 개인 도구가 아니라 기업 환경에서 **민감정보 취급 경로**가 될 수 있음을 보여줍니다. 보안팀과 개발팀이 함께 Desktop 업데이트/설정 표준을 만드는 쪽으로 갈 확률이 높습니다. ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))

---

## 🚀 마무리
2025년 12월의 핵심은 “새 기능”보다 **하부 스택 정리 신호**였습니다: Kubernetes v1.35에서 cgroup v1 제거와 containerd 1.x 종료 경고가 나왔고, Docker Desktop은 12월 릴리스에서 보안 이슈를 구체적으로 패치하며 Wasm 워크로드 제거까지 예고했습니다. ([kubernetes.io](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/?utm_source=openai))

개발자/플랫폼 팀 권장 액션은 3가지입니다.
1) 클러스터별로 **cgroup v2 사용 여부**와 노드 OS/커널 조건을 점검하고, 레거시 노드 풀 정리 계획을 세우기 ([kubernetes.io](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/?utm_source=openai))  
2) 노드 런타임에서 **containerd 2.0+ 전환 로드맵**을 확정(테스트 클러스터부터)하고, 관련 메트릭(`kubelet_cri_losing_support`) 기반 가시화 추가 ([kubernetes.io](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/?utm_source=openai))  
3) 조직 표준 개발 환경에서 Docker Desktop을 쓰고 있다면 **12월 릴리스의 보안 패치/CVE 항목**과 “향후 Wasm 제거” 문구를 기준으로 의존 기능을 점검하고 업데이트 정책을 문서화 ([docs.docker.com](https://docs.docker.com/docker-for-windows/release-notes/?utm_source=openai))