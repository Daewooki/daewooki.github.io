---
title: "Kubernetes 1.35 ‘Timbernetes’가 던진 신호: cgroup v1 종료, containerd 1.x 최종 경고, 그리고 “Pod 리소스 무중단 변경”의 현실화"
description: "2025년 12월 클라우드 네이티브 업계의 핵심 뉴스는 Kubernetes v1.35 정식 릴리스(12월 17일)로 요약됩니다."
date: 2025-12-21 02:22:33 +0900
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
2025년 12월 클라우드 네이티브 업계의 핵심 뉴스는 **Kubernetes v1.35 정식 릴리스(12월 17일)**로 요약됩니다. 이번 릴리스는 기능 추가만큼이나 **런타임/노드 운영의 ‘전환’(cgroup v1 제거, containerd 1.x 지원 종료 예고)**을 강하게 밀어붙였고, 개발자/플랫폼팀 모두가 체감할 변화가 큽니다.[^1]

---

## 📰 무슨 일이 있었나
- **2025년 12월 17일**, Kubernetes 프로젝트가 **Kubernetes v1.35 “Timbernetes (The World Tree Release)”**를 공식 발표했습니다. 이번 릴리스는 **총 60개 enhancements(Stable 17, Beta 19, Alpha 22)**를 포함합니다.[^1]  
- 릴리스 하이라이트 중 개발자 관점에서 가장 즉시 체감되는 변화는 다음입니다.
  - **In-place update of Pod resources가 GA(Stable)**로 승격: Pod/Container 재시작 없이 CPU/Memory 리소스를 조정하는 방향을 공식 지원합니다.[^1]  
  - **Pod certificates(Workload identity 관련) 기능이 Beta**: kubelet이 키를 만들고 PodCertificateRequest를 통해 인증서를 요청/회전하며, Secret 기반·사이드카 기반 구성 복잡도를 줄이는 흐름을 제시합니다.[^1]  
- “기능”보다 더 큰 파장을 만드는 운영/호환성 변화도 같이 명시됐습니다.
  - **cgroup v1 지원 제거(Removal)**: cgroup v2 미지원/미활성화 노드에서는 kubelet이 시작 실패할 수 있으니 노드 OS/커널/설정을 선제 점검하라고 못 박았습니다.[^1]  
  - **containerd v1.x에 대한 ‘Final call’**: v1.35가 **containerd v1.x를 지원하는 마지막 Kubernetes 버전**이며, 다음 버전 업그레이드 전에 containerd 2.0+로 전환하라고 경고합니다. 또한 점검용으로 `kubelet_cri_losing_support` 메트릭을 언급합니다.[^1]  
  - **kube-proxy ipvs mode Deprecation**: 당장 제거는 아니지만, 유지보수 부담 때문에 경고를 출력하며 장기적으로는 다른 방향(문서에선 nftables 전환 언급)으로 유도합니다.[^1]  
- 같은 시기(주간 개발 동향 요약)에서도 릴리스가 확인됩니다. **LWKD(Last Week in Kubernetes Development)**는 “**Kubernetes v1.35.0이 live**”라고 정리하며, 생태계 도구 업데이트도 함께 언급했습니다.[^2]

---

## 🔍 왜 중요한가
1) **“Pod 리소스 무중단 변경”이 GA가 됐다는 의미**
- 지금까지는 requests/limits 조정이 곧 재배포/재시작(또는 최소한 Pod 재생성)과 연결되는 경우가 많았고, stateful/batch 워크로드에서 운영 리스크가 컸습니다. v1.35에서 이를 GA로 만들면서, **Vertical scaling의 운영 패턴 자체가 바뀔 여지**가 생겼습니다.[^1]  
- 개발자 관점 포인트: “오토스케일링=수평(HPA)만”이 아니라, 워크로드 특성에 따라 **리소스 튜닝 루프(성능/비용 최적화)가 더 짧아질 수** 있습니다.

2) **cgroup v1 제거는 ‘업그레이드 체크리스트’가 아니라 ‘장애 트리거’가 될 수 있음**
- Kubernetes가 v1.35에서 **cgroup v1을 제거**했기 때문에, 아직 레거시 노드(구형 배포판/설정)를 끌고 가는 클러스터는 “나중에 하자”가 통하지 않습니다. kubelet이 아예 시작하지 못하는 시나리오를 공식적으로 경고합니다.[^1]  
- 개발자 관점 포인트: 애플리케이션 코드 이슈가 아니라 **플랫폼 레이어에서 갑자기 배포/스케일이 멈추는** 형태로 나타날 수 있으니, 플랫폼팀과의 사전 합의(노드 교체·OS 업그레이드·런타임 업그레이드)가 필수입니다.

3) **containerd 1.x ‘마지막 지원’은 Docker/컨테이너 생태계 전반의 압력**
- Kubernetes는 이미 “Docker runtime”을 직접 사용하던 시대를 지나 CRI 기반 런타임(containerd 등) 중심으로 굳어졌습니다. v1.35에서 **containerd v1.x 지원을 이번이 마지막**이라고 못 박은 건, 2026년을 앞두고 런타임 업그레이드 압박이 본격화됐다는 뜻입니다.[^1]  
- 이 흐름은 단순 버전업이 아니라, 노드 이미지/보안 정책/운영 자동화(프로비저닝)까지 영향을 주는 “플랫폼 업그레이드 프로젝트”로 번질 가능성이 큽니다.

---

## 💡 시사점과 전망
- **클라우드 네이티브의 ‘다음 표준’이 더 빨리 굳는다**: cgroup v2, containerd 2.x 같은 하부 표준이 “권장”에서 “전제”로 바뀌고 있습니다. v1.35는 그 전환을 공지 수준이 아니라 릴리스 차원에서 실행했습니다.[^1]  
- **Ingress NGINX의 유지보수 한계와 Gateway API 전환 압력**도 함께 언급되면서, 트래픽 관리 영역에서도 “사실상 표준 교체”가 진행 중입니다(베스트 에포트 유지보수는 2026년 3월까지).[^1]  
- 2026년 상반기 시나리오(보수적으로 예상):
  1) Kubernetes 업그레이드가 곧 **노드 OS/커널 + cgroup v2 + containerd 2.x 전환**을 포함하는 “묶음 업그레이드”로 정착  
  2) 운영팀은 `kubelet_cri_losing_support` 같은 신호를 기반으로 **런타임 호환성 관측(Observability)을 업그레이드 게이트**로 삼을 가능성 확대[^1]  
  3) 개발팀은 “스케일 전략”을 HPA 중심에서 **in-place 리소스 조정(Vertical)까지 포함**해 재설계하는 팀이 늘어남[^1]  

---

## 🚀 마무리
2025년 12월의 핵심은 “Kubernetes 1.35 기능 업데이트”가 아니라, **클러스터 운영의 전제조건이 바뀌었다**는 점입니다. 정리하면: **(1) Pod 리소스 in-place update GA**, **(2) cgroup v1 제거**, **(3) containerd 1.x 지원 종료 예고**가 한 번에 몰려왔습니다.[^1]  

개발자/플랫폼팀 권장 액션:
- Kubernetes v1.35 업그레이드 계획이 있다면, 먼저 **노드의 cgroup v2 활성화 여부**와 **containerd 버전(1.x인지)**을 인벤토리로 뽑아 “업그레이드 가능 클러스터”를 판별하세요.[^1]  
- 애플리케이션 운영 측면에서는, v1.35의 **in-place 리소스 조정 GA**를 전제로 “장애 없는 튜닝/비용 최적화” 운영 시나리오(배치, stateful, latency 민감 서비스)를 다시 설계해볼 타이밍입니다.[^1]

[^1]: <https://kubernetes.io/blog/2025/12/17/kubernetes-v1-35-release/>
[^2]: <https://lwkd.info/2025/20251218>
