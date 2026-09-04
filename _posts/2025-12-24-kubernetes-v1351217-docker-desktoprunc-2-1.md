---
title: "Kubernetes v1.35(12/17) 릴리스와 Docker Desktop·runC 취약점 이슈가 만든 클라우드 네이티브 판도 변화"
description: "2025년 12월 클라우드 네이티브 업계는 “기능 진화”와 “런타임 보안”이 동시에 전면에 부상한 달이었습니다."
date: 2025-12-24 02:08:40 +0900
categories: [News, DevOps]
tags: [devops, news]
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
2025년 12월 클라우드 네이티브 업계는 “기능 진화”와 “런타임 보안”이 동시에 전면에 부상한 달이었습니다. Kubernetes는 v1.35를 12월 17일 공개하며 대규모 개선(총 60개 enhancement)을 발표했고, 한편 Docker Desktop 및 runC 계열 취약점 이슈가 운영·개발 환경의 보안 기본선을 다시 끌어올렸습니다.[^1]

---

## 📰 무슨 일이 있었나
- **2025년 12월 17일**, Kubernetes 프로젝트가 **Kubernetes v1.35 “Timbernetes (The World Tree Release)”**를 공개했습니다. 이번 릴리스는 **총 60개 enhancement(Stable 17 / Beta 19 / Alpha 22)**를 포함하며, 일부 **deprecation/removal**도 함께 안내됐습니다. 즉, “새 기능 추가”뿐 아니라 “정리/정돈”이 동반되는 릴리스 사이클이 이어졌다는 신호입니다.[^1]  
- **2025년 11월~12월 흐름에서** 컨테이너 런타임 보안 이슈가 크게 주목받았습니다. 보안 리서치 결과로 **runC 취약점 3종(CVE-2025-31133, CVE-2025-52565, CVE-2025-52881)**이 공개되었고, 특정 버전에서 **호스트 권한(루트) 수준 영향** 가능성이 언급되며 패치 버전이 제시됐습니다(예: 1.2.8 / 1.3.3 / 1.4.0-rc.3 등).[^2]  
- Docker Desktop 측면에서도 **CVE-2025-9074**가 중요한 이슈로 다뤄졌습니다. 분석 글들에 따르면(특히 Windows/WSL2 결합 환경 맥락에서) “Docker Engine API 접근”과 같은 공격 경로가 논의되었고, Docker Desktop 업데이트(예: 4.44.3 언급) 권고가 나왔습니다.[^3]  

---

## 🔍 왜 중요한가
1) **Kubernetes 업그레이드가 ‘기능 선택’이 아니라 ‘운영 전략’이 됨**  
v1.35처럼 enhancement 규모가 큰 릴리스는, 단순히 “새 기능을 쓰자”보다 **클러스터 정책·애드미션·스케줄링·노드 운영 표준을 재점검**하는 계기가 됩니다. 특히 릴리스 공지에서 **deprecation/removal**을 강조하는 패턴은, 업그레이드 지연이 곧 기술부채로 직결될 수 있음을 의미합니다.[^1]  

2) **개발 PC/CI 환경의 Docker Desktop도 ‘보안 경계’로 재분류**  
많은 조직에서 Docker Desktop은 “개발자 로컬 도구”로 취급되지만, CVE-2025-9074 같이 **Engine API 접근/권한 상승 시나리오**가 제기되면, 개발자 단말이 곧 공급망 공격의 진입점이 될 수 있습니다. 즉 **로컬 표준 이미지 빌드·테스트 환경**까지도 패치·정책(권한, 설정) 관리 대상이 됩니다.[^3]  

3) **Kubernetes vs Docker 이슈가 아니라 ‘runC/런타임 계층’이 핵심**  
Kubernetes는 기본적으로 Docker를 직접 런타임으로 쓰지 않는 방향(containerd/CRI 등)으로 오래전부터 이동했지만, 이번 이슈는 “Docker냐 Kubernetes냐”가 아니라 **공통 기반(runC 같은 저수준 런타임)**의 중요성을 다시 보여줍니다. 운영자가 봐야 할 포인트는 배포 툴이 아니라 **노드 런타임 버전, 패치 레벨, 하드닝 옵션(rootless, user namespace 등)**입니다.[^2]  

---

## 💡 시사점과 전망
- **“릴리스 속도”와 “보안 패치 속도”가 동일한 KPI로 묶이는 추세**  
Kubernetes는 정기 릴리스로 기능/정리를 지속하고, 런타임 계층은 취약점 공개 주기와 패치 압력이 커집니다. 결과적으로 2026년에는 더 많은 팀이 **플랫폼 엔지니어링(Platform Engineering)** 관점에서 “업그레이드 자동화 + 취약점 대응 자동화”를 같이 설계하게 될 가능성이 큽니다(예: 노드 이미지 빌드 파이프라인, 취약점 스캐닝/정책 게이트).[^1]  
- **Windows/WSL2 조합, Dev 환경이 ‘예외 구간’이 아니라 ‘취약 구간’이 될 수 있음**  
Docker Desktop 취약점 논의가 Windows 환경에서 더 크게 다뤄진 것처럼, 조직 내 이질적인 개발 환경이 많을수록(Windows/macOS 혼재) “보안 기준선 통일”이 어려워집니다. 앞으로는 **Dev Container 정책, 로컬 런타임 구성 표준화, 업데이트 강제(관리형 배포)**가 강화될 가능성이 높습니다.[^3]  

---

## 🚀 마무리
2025년 12월의 핵심은 두 가지였습니다. **Kubernetes v1.35(2025-12-17)로 대표되는 플랫폼 기능·정리의 지속**과, **runC/Docker Desktop 취약점 이슈로 대표되는 런타임 보안의 재부상**입니다.[^1]  

개발자/플랫폼 팀 권장 액션은 간단히 정리하면 다음입니다.
- Kubernetes: **v1.35 릴리스 노트 기반으로 deprecation/removal 영향부터 점검**하고, 업그레이드 계획을 “기능 검토”가 아니라 “운영 리스크 관리”로 다루기[^1]  
- 런타임: 노드/빌드 환경에서 **runC 패치 버전 적용 여부를 우선 확인**하고(벤더 이미지/AMI 포함), rootless·user namespace 등 하드닝 옵션 검토[^2]  
- Dev 환경: Docker Desktop 사용 조직이라면 **CVE-2025-9074 관련 업데이트 권고 버전 적용** 및 로컬 정책(권한/설정/업데이트 강제) 정비[^3]

[^1]: <https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/>
[^2]: <https://www.techradar.com/pro/security/some-docker-containers-may-not-be-as-secure-as-they-like-experts-warn>
[^3]: <https://www.techradar.com/pro/security/a-critical-docker-desktop-security-flaw-puts-windows-hosts-at-risk-of-attack-so-patch-now>
