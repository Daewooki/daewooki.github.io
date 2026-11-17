---
title: "Kubernetes Code Freeze로 배우는 릴리스 컷오프 운영법"
description: "Kubernetes v1.38 Code/Test Freeze를 운영 이벤트로 바꿔 버전 스큐, 체리픽, 테스트·릴리스 노트 컷오프를 굴리는 방법."
date: 2026-11-17 12:50:05 +0900
categories: ["DevOps", "Kubernetes"]
tags: ["kubernetes", "sig-release", "release-engineering", "code-freeze", "test-freeze", "version-skew"]
render_with_liquid: false
---

## 프리즈를 일정이 아니라 컷오프로 취급해야 하는 이유

2026-11-17 KST인 지금, Kubernetes v1.38 릴리스 캘린더 상 **Code Freeze**와 **Test Freeze**가 걸려 있습니다. 일정 표기 자체가 플랫폼팀에게 중요한 힌트를 줍니다. “Monday 16th November 2026 (AoE) / Tuesday 17th November 2026, 12:00 UTC”처럼 AoE와 UTC를 같이 씁니다. [Kubernetes v1.38 Release Information](https://www.kubernetes.dev/resources/release/)에 명시된 그대로, 2026-11-16(AoE)이라는 표현은 “지구 어디에서든 그 날짜가 끝날 때”를 의미하고, 예시로 AoE 마감은 다음날 12:00 UTC로 환산된다고 설명합니다.[^1]

한국(UTC+9)에서는 12:00 UTC가 21:00 KST입니다. 따라서 v1.38 Code/Test Freeze 컷오프는 **2026-11-17 21:00 KST**로 받아들이는 편이 운영에 유리합니다. AoE는 “개발자에게 관대한 마감”이 아니라 “운영자가 데드라인을 단일한 순간으로 바꿀 수 있는 표준화 장치”에 가깝습니다.

여기서 말하는 릴리스 컷오프는 upstream 쿠버네티스 개발자들의 이벤트를 구경하는 게 목적이 아닙니다. 플랫폼팀 입장에서는 다음 두 가지를 동시에 만족해야 합니다.

- 업그레이드(그리고 그로 인한 장애)를 **예측 가능한 창**으로 밀어 넣기
- 프리즈 주간에 발생하는 체리픽/테스트/문서(릴리스 노트 포함)의 흐름을 **운영 가능한 큐**로 바꾸기

이게 안 되면 프리즈는 “바쁜 주”로 끝나고, 되면 “업그레이드와 변경을 통제하는 운영 이벤트”가 됩니다.

## upstream Kubernetes에서 Code Freeze와 Test Freeze가 실제로 막는 것

프리즈가 걸리면 무엇이 막히는지부터 정확해야 플랫폼팀이 같은 패턴을 복제할 수 있습니다.

Kubernetes 릴리스 프로세스 문서에서는 Code Freeze를 “최종 릴리스 전 약 4주 동안, 크리티컬 버그픽스만 머지되는 기간”으로 정의합니다. 그리고 이 과정에서 최종 릴리스는 release branch에서 빌드되고, master에서 남은 변경은 release branch로 체리픽된다고 설명합니다. [Kubernetes Release Cycle](https://kubernetes.io/releases/release/)이 딱 이 구조를 공식화합니다.[^2]

중요한 부분은 “누가 막는가”입니다. 이게 사람의 선언만으로 돌아가면 규모가 커질수록 누수가 나옵니다. SIG Release의 Release Manager 핸드북은 Code Freeze를 Tide(자동 머지 엔진) 설정 변경으로 만든다고 적습니다. 구체적으로는 `kubernetes/kubernetes`의 `master`와 현재 release branch에 대해, Tide 쿼리에 `milestone: vX.Y` 같은 제약을 추가해서 “마일스톤에 들어간 PR만 머지 큐로 들어오게” 만듭니다. 이게 Kubernetes가 trunk-based 개발을 유지하면서도 릴리스를 굴리는 핵심 장치입니다. [release-manager.md](https://github.com/kubernetes/sig-release/blob/master/release-engineering/handbooks/release-manager.md) 참고.[^3]

Test Freeze는 Code Freeze와 동시에 걸리지만 성격이 다릅니다. `sig-release`의 [release_phases.md](https://github.com/kubernetes/sig-release/blob/master/releases/release_phases.md)는 Test Freeze를 “그 날짜 이후로는 release-blocking 등 예외적 사유가 아니면 테스트를 변경하거나 Conformance로 승격하지 않는다”로 정의합니다. 프리즈 이후의 목표는 테스트 추가가 아니라, 실패하는 테스트를 고치거나 revert하거나 제거하는 쪽으로 무게중심을 옮기는 겁니다.[^4]

Enhancements 팀 핸드북은 더 노골적으로 적습니다. Test Freeze는 Code Freeze와 동시에 발생하며, “새 테스트 변경/승격 금지(예외는 release-blocking 등)”라는 운영 규칙을 둡니다. 또한 트래킹되는 enhancement라면 관련 테스트 PR도 데드라인까지 `approved`/`lgtm` 상태로 merge-ready여야 한다고 적습니다. upstream은 이걸 체크리스트가 아니라 “트래킹 보드에서 Tracked for code freeze 판정 조건”으로 씁니다. [Enhancements Handbook](https://github.com/kubernetes/sig-release/blob/master/release-team/role-handbooks/enhancements/README.md) 안의 Understanding Test Freeze가 근거입니다.[^5]

예외(exception)도 운영상 핵심입니다. 예외는 “아무 때나 부탁하면 되는 것”이 아니라 데드라인이 또 있습니다. [EXCEPTIONS.md](https://github.com/kubernetes/sig-release/blob/master/releases/EXCEPTIONS.md)는 Code/Test Freeze 이후 예외 요청은 **3일 이내 제출**이라는 룰을 박아 둡니다. 프리즈를 컷오프로 운영하려면 “컷오프 이후에도 예외를 무제한 받는 조직”이 되면 안 됩니다.[^6]

정리하면 upstream의 프리즈는 대략 이런 구조입니다.

- Code Freeze: 자동 머지 정책(Tide)으로 “현재 릴리스 마일스톤이 아닌 PR”을 물리적으로 막음[^3]
- Test Freeze: 테스트는 추가보다 안정화(고치기/revert/제거)로 전환[^4]
- Exceptions: 프리즈 이후에도 요청 창은 열어두되 3일 내 제출 같은 추가 컷오프를 둠[^6]

플랫폼팀이 가져가야 할 교훈은 “프리즈는 선언이 아니라 정책/큐/데드라인의 조합”이라는 점입니다.

## 플랫폼팀 관점의 프리즈 주간: 릴리스 컷오프를 운영 이벤트로 만드는 프레임

내가 플랫폼팀 일을 하면서 느낀 건, 프리즈는 개발팀을 괴롭히는 행사도 아니고 QA 팀의 성수기도 아닙니다. **업그레이드 압력**을 다루는 조직이라면 프리즈는 “변경이 몰려드는 구간을 일부러 만들고, 그 구간 밖을 조용하게 만드는” 장치입니다.

여기서 프리즈 주간에 플랫폼팀이 해야 하는 일을 4개의 컷오프로 나눠 보면 정리가 됩니다.

1) Upgrade Window 컷오프: “이번 minor를 언제 받아들이고, 언제부터는 다음 minor로 넘길지”를 정함

2) Version Skew 컷오프: “우리 fleet이 업그레이드를 감당할 수 있는 skew 상태인지”를 수치로 판정

3) Cherry-pick 컷오프: “프리즈 주간에 들어오는 변경 요청을 어떤 큐로 받고, 어디까지 받아줄지”를 데드라인으로 고정

4) Test Freeze 대응 컷오프: “테스트를 추가하는 기간”과 “테스트를 고정하고 안정화하는 기간”을 갈라서, 실패 대응을 운영 큐로 만듦

upstream은 이 네 가지를 다른 문서/도구/역할로 쪼개 굴립니다. 우리는 조직 규모가 다르더라도 구조는 그대로 가져올 수 있습니다.

v1.38 캘린더를 보면 Code/Test Freeze가 2026-11-17 12:00 UTC(= 21:00 KST)이고, 그 다음 주요 이벤트로 2026-12-03에 release-1.38 branch 생성 및 v1.38.0-rc.0, 그리고 2026-12-16에 v1.38.0 GA가 잡혀 있습니다. 이 간격이 플랫폼팀 입장에서는 “RC로 스테이징을 태워서 위험을 드러내고, GA 이후에 프로덕션을 태울지 말지 결정하는 구간”이 됩니다. [Kubernetes v1.38 Release Information](https://www.kubernetes.dev/resources/release/)의 타임라인이 이 흐름을 그대로 보여줍니다.[^1]

## Version Skew를 숫자로 만들면 업그레이드 윈도우가 보인다

프리즈 주간에 가장 흔한 실패는 “업그레이드 일정 논의가 사람의 감으로 흐르는 것”입니다. 감으로 논의하면 결국 마지막에 남는 건 두 문장입니다.

- “될 것 같은데요.”
- “불안한데요.”

Kubernetes는 이 부분을 문서로 못 박아 둡니다. [Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/)가 운영자가 들고 다녀야 하는 표준입니다.[^7]

핵심 조항만 뽑으면 다음과 같습니다.

- `kubelet`은 `kube-apiserver`보다 **newer면 안 됨**
- `kubelet`은 `kube-apiserver`보다 **최대 3 minor older**까지 허용(단, `kubelet` < 1.25이면 2 minor)[^7]
- HA cluster에서 apiserver가 혼재(예: 1.37과 1.36 공존)하면, 이 혼재 자체가 `kubelet`의 허용 범위를 **더 좁힘**[^7]

이 정책을 그대로 “업그레이드 윈도우”로 변환할 수 있습니다.

예를 들어 fleet의 어떤 클러스터가 control plane이 1.36인데 노드가 1.33이라면, 그 클러스터는 이미 `kubelet`이 3 minor behind입니다. 여기서 control plane을 1.37로 올리면 노드는 1.33이 4 behind가 됩니다. 즉, 스큐 정책 위반이고, 업그레이드 절차상 control plane 업그레이드 전에 노드를 먼저 끌어올려야 합니다. 정책 문서에는 “persistently 3 minor behind 상태로 운영하면 control plane 업그레이드 전에 노드를 올려야 한다”는 경고까지 들어 있습니다.[^7]

이걸 프리즈 주간에 쓰는 방식은 간단합니다.

- v1.38 프리즈(2026-11-17 21:00 KST) 이전: fleet의 skew를 측정하고, **업그레이드 가능/불가를 분류**
- 프리즈 이후: 분류 결과에 따라 “이번 릴리스(1.38)를 받는 클러스터”와 “다음으로 미루는 클러스터”를 고정

여기서 중요한 태도는 “모든 클러스터를 같은 날 올리겠다”가 아니라 “같은 기준으로 분류해서, 같은 종류의 클러스터를 같은 창에 넣겠다”입니다. 프리즈를 운영 이벤트로 만들려면 이 분류 작업이 프리즈 이전에 끝나야 합니다.

## Cherry-pick 데드라인을 만들지 않으면 프리즈 주간은 무한정 길어진다

플랫폼팀에서 프리즈 주간이 길어지는 전형적인 패턴이 있습니다.

- 팀 A: “이거 이번 릴리스에 꼭 들어가야 합니다.”
- 플랫폼팀: “그러면 체리픽으로 넣죠.”
- 팀 A: “근데 아직 테스트가…”
- 플랫폼팀: “그럼 예외로…”
- 팀 A: “근데 문서가…”
- 플랫폼팀: “그럼 또 예외로…”

이 루프가 시작되면 프리즈는 컷오프가 아니라 “협상 기간”이 됩니다. upstream Kubernetes는 이걸 두 겹의 장치로 막습니다.

첫째, Code Freeze 이후 변경은 원칙적으로 release-blocking 범주로 제한합니다. [release_phases.md](https://github.com/kubernetes/sig-release/blob/master/releases/release_phases.md)는 Code Freeze 시점 이후 “남는 PR은 release-blocking 이슈 관련만 허용”이라는 운영 규칙을 명시합니다.[^4]

둘째, 예외 요청도 무한정 받지 않습니다. [EXCEPTIONS.md](https://github.com/kubernetes/sig-release/blob/master/releases/EXCEPTIONS.md)는 Code/Test Freeze 이후 예외 요청은 3일 이내 제출이라고 적습니다. 즉 “프리즈 이후에도 요청 창은 열려 있지만, 창이 작다”는 설계입니다.[^6]

플랫폼팀이 이 구조를 가져오려면, cherry-pick을 “git 기술”이 아니라 “운영 큐”로 만들어야 합니다.

### release branch에 들어가는 변경을 라벨로 통제하는 감각

upstream 쪽에서 release branch에 들어가는 PR은 `cherry-pick-approved` 같은 라벨과 함께 굴러가고, 승인되지 않은 PR은 `do-not-merge/cherry-pick-not-approved` 같은 자동 라벨로 막힙니다. 이 라벨은 Prow 플러그인으로 설명돼 있고, 실제 라벨 정의도 `kubernetes/test-infra`의 labels.yaml에 들어 있습니다. 운영 포인트는 “사람이 머지 버튼을 안 누른다”가 아니라, “도구가 머지 조건을 바꾼다”입니다.[^8]

플랫폼팀 조직에서도 똑같이 만들 수 있습니다.

- main branch 머지: 평소 정책
- release branch(또는 release candidate 브랜치) 머지: 라벨/마일스톤/승인 조건 강화
- freeze 기간에는 “release branch로 들어오는 PR 큐”만 남기고 나머지는 다음 릴리스로 넘김

이때 꼭 필요한 게 데드라인입니다.

- 프리즈 컷오프(T0): 더 이상 새 기능/새 변경을 받지 않음
- 체리픽 요청 컷오프(T0 + 2~3일): 예외/긴급은 이때까지만 접수
- 머지 컷오프(T0 + 1주 같은 내부 규칙): 들어온 체리픽을 안정화시키고 큐를 비움

upstream의 “3일 내 exception 제출” 같은 숫자는 우리 조직이 그대로 따라야 할 규칙은 아니지만, “프리즈 후에도 요청 창은 열되 좁혀야 한다”는 설계 원칙은 그대로 가져오는 게 맞습니다.[^6]

### 실제 체리픽 도구(스크립트)까지 내려오면 운영이 빨라진다

플랫폼팀이 downstream patch(예: 사내 배포판 패치, 특정 드라이버 패치, 이미지 빌드 파이프라인 패치)를 들고 있다면, 체리픽을 수동으로 하면 프리즈 주간 처리량이 급락합니다.

Kubernetes 쪽에는 `hack/cherry_pick_pull.sh`가 있고, kOps 문서가 이 스크립트를 받아서 체리픽 PR을 만드는 예시를 제공합니다. upstream 프로젝트에서 관성적으로 쓰이는 도구를 그대로 쓰는 편이, 프리즈 주간에 작업 방식이 흔들리지 않습니다. [Cherry-picking changes back to previous branches](https://kops.sigs.k8s.io/contributing/proposing-a-cherry-pick/)에 스크립트 다운로드 및 실행 예시가 나옵니다.[^9]

여기서 포인트는 “스크립트가 있으니 써라”가 아니라, 스크립트 기반으로 작업을 표준화하면 다음이 가능해진다는 점입니다.

- 체리픽 PR 제목/본문/원본 PR 링크/릴리스 노트 참조가 일관됨
- 승인 라벨/머지 조건을 기계적으로 적용 가능
- 프리즈 주간에 체리픽 누락(원본은 고쳤는데 release branch에는 안 들어간 상태)을 줄임

또 하나의 운영 포인트는 patch release 시기에도 “체리픽 freeze”가 따로 존재한다는 점입니다. SIG Release의 Release Manager 핸드북은 patch release를 자르기 전에 `cherry-pick-approved` 라벨을 정리하면서 잠깐 freeze를 걸어 “HEAD에서 테스트가 충분히 돈 상태”를 확보한다고 설명합니다. 이게 minor 프리즈뿐 아니라 patch 레벨에서도 똑같이 반복된다는 뜻입니다.[^3]

이 패턴을 플랫폼팀이 흡수하면, minor 프리즈 주간뿐 아니라 “정기 패치 릴리스”도 계약처럼 다룰 수 있습니다. 예전 글에서 패치 릴리스를 운영 계약으로 바꾸는 얘기는 따로 정리했으니, 여기서는 반복하지 않습니다. [Kubernetes 1.35.10 패치 릴리스: 정기 패치를 운영 계약으로 바꾸는 법](https://daewooki.github.io/posts/kubernetes-patch-release-ops-contract/)

## Test Freeze 대응은 테스트 추가를 멈추는 게 아니라 실패 대응 큐를 만드는 일이다

Test Freeze를 “이제 테스트 건드리지 말자”로만 이해하면 현장에서 바로 부딪힙니다. 프리즈 주간에 테스트는 계속 터집니다. flaky가 폭발하기도 하고, 릴리스 브랜치에서만 나는 실패가 나오기도 합니다.

upstream 정의를 보면 Test Freeze는 “테스트 변경 금지”가 아니라 “새 테스트/승격을 멈추고 안정화 모드로 전환”입니다. [release_phases.md](https://github.com/kubernetes/sig-release/blob/master/releases/release_phases.md)가 이 구분을 정확히 씁니다. 프리즈 이후에는 테스트를 고치거나, revert하거나, 제거해서 green을 만드는 방향으로 목표를 옮깁니다.[^4]

Enhancements 핸드북의 Understanding Test Freeze도 같은 톤입니다. Conformance 승격 같은 큰 변경은 예외 사유가 아니면 막고, tracked enhancement의 테스트 PR은 데드라인까지 merge-ready여야 한다고 압박합니다.[^5]

플랫폼팀에서 이걸 운영 이벤트로 만들려면, 내부적으로 다음 3개의 큐가 필요합니다.

1) 릴리스 블로킹 큐: 업그레이드 자체를 깨는 문제(예: API server가 뜨지 않음, kubelet이 기동 불가, CNI가 전면 장애)

2) 업그레이드 리스크 큐: 업그레이드는 되지만 기능/성능/비용 리스크가 큰 문제(예: 특정 워크로드의 eviction 폭증, HPA 반응 급변)

3) 노이즈 큐: flaky나 관측성 이슈처럼 “지금 고치면 좋지만 릴리스 컷오프를 넘길 가치가 없는 것”

Test Freeze 이후에 큐 1만 남기고 큐 2/3을 다음 창으로 미루는 결정을 해야 프리즈가 끝납니다. 이 결정을 못 하면 프리즈는 영원히 지속됩니다.

### release dashboards를 ‘내부 SLO’로 복제하기

v1.38 타임라인에는 v1.38.0-rc.0 시점에 `1.38-blocking`, `1.38-informing` 같은 Testgrid 대시보드가 명시됩니다. release branch가 만들어지고(2026-12-03) RC가 잘릴 때, 어떤 테스트가 blocking이고 어떤 테스트가 informing인지가 릴리스 팀의 운영 단위가 됩니다. [Kubernetes v1.38 Release Information](https://www.kubernetes.dev/resources/release/)에 링크가 붙어 있습니다.[^1]

내부에서도 비슷한 구조가 필요합니다.

- blocking: 이게 빨갛면 업그레이드/배포를 멈춤
- informing: 빨갛면 원인 분석은 하되, 반드시 멈추지는 않음(단, 일정 기준 넘으면 blocking으로 승격)

SIG Cluster Lifecycle의 kubeadm 저장소 문서도 “release blocking/informing 대시보드의 잡은 실패 시 릴리스를 막을 수 있다”는 현실적인 운영 관점을 설명합니다. 대시보드에 걸린 잡은 운영 우선순위가 다르고, 실패가 누적되면 알람을 보내는 설정도 있다는 식으로요. 내부 테스트 그리드가 있다면 이 수준까지는 아니더라도, 프리즈 주간만큼은 blocking/informing 구분이 있어야 합니다.[^10]

## 릴리스 브랜치/백포트/릴리스 노트: 프리즈 주간에 문서까지 운영 자산으로 다루기

프리즈 주간에 문서(특히 릴리스 노트)를 뒷전으로 밀면, GA 직전에 운영 부채가 폭발합니다. upstream이 왜 릴리스 노트를 자동화/강제하는지 보면 플랫폼팀이 무엇을 강제해야 하는지가 보입니다.

### release branch는 rc.0 시점에 만들어지고, 그게 백포트의 기준점이 된다

Kubernetes 릴리스 프로세스 문서는 release branch(`release-X.Y`)가 `vX.Y-rc.0` 시점에 생성되고, 이후 약 12개월 동안 patch 릴리스(`vX.Y.Z`)의 기반이 된다고 설명합니다. 즉, release branch는 “코드 스냅샷”이 아니라 “향후 1년간 유지보수의 기준점”입니다.[^2]

v1.38의 구체 일정도 같습니다. 2026-12-03에 `release-1.38` branch 생성과 `v1.38.0-rc.0` 릴리스가 같은 날로 잡혀 있습니다. [Kubernetes v1.38 Release Information](https://www.kubernetes.dev/resources/release/) 타임라인에 그대로 나옵니다.[^1]

플랫폼팀이 이 이벤트를 왜 신경 써야 하냐면, 내부 업그레이드 실무에서 다음이 갈리기 때문입니다.

- master(또는 main) 기준으로 패치를 계속 넣을 것인가
- RC 이후에는 release branch로 체리픽해서 “GA 후보”를 고정할 것인가

RC 이후에도 main에만 패치를 넣고 프로덕션을 올리면, 프로덕션에서 문제가 터졌을 때 “어느 커밋이 GA에 들어갔는지”가 아니라 “그때그때 최신이 뭐였는지”로 사고 조사를 하게 됩니다. 프리즈를 컷오프로 운영하는 조직은 RC 이후 변경을 release candidate 라인으로 모읍니다.

### 릴리스 노트는 PR 단계에서 강제하지 않으면 프리즈 주간에 절대 못 모은다

Kubernetes는 PR 템플릿에 릴리스 노트 블록을 두고, 사용자 영향이 있는 PR인데 릴리스 노트가 없으면 `do-not-merge/release-note-label-needed` 라벨이 자동으로 붙는다고 문서화돼 있습니다. 이건 릴리스 노트를 “출시 직전 작성하는 문서”가 아니라 “변경이 생길 때마다 쌓는 데이터”로 본다는 뜻입니다. [Adding Release Notes](https://www.kubernetes.dev/docs/guide/release-notes/)에 명시돼 있습니다.[^11]

또 하나 중요한 포인트는, patch release branch의 체리픽 PR은 원본(master) PR에서 릴리스 노트를 끌고 온다는 설명입니다. 즉, “릴리스 노트는 원본 PR에서 제대로 써야 백포트도 제대로 된다”는 설계입니다.[^11]

플랫폼팀도 똑같이 해야 합니다.

- 인프라 코드(Helm chart, Terraform, CRD, admission policy) 변경은 릴리스 노트를 남김
- 릴리스 노트 없는 변경은 프리즈 주간에 cherry-pick 승인 대상에서 제외

이 규칙을 프리즈 주간에 갑자기 도입하면 반발만 생기고 효과는 없습니다. 대신 “프리즈 전 주”에 라벨/템플릿을 적용하고, 프리즈 주간에는 예외만 처리하는 편이 현실적입니다.

## 프리즈 주간에 바로 써먹는 스큐/윈도우 점검 코드: fleet-skew-audit.sh

프리즈를 운영 이벤트로 만들려면, “지금 fleet이 어떤 상태인지”를 매일 동일한 방식으로 뽑아낼 수 있어야 합니다. 그리고 그 결과가 업그레이드 가능/불가 판정으로 이어져야 합니다.

여기서는 `kubectl`과 `jq`만으로 fleet의 Version Skew를 점검하는 스크립트를 정리합니다. 현실적인 전제는 이렇습니다.

- 여러 클러스터 컨텍스트가 한 kubeconfig에 들어 있음(플랫폼팀 점프박스나 CI 러너)
- 프리즈 주간에 매일(또는 매 커밋) 실행해서 “업그레이드 가능한 클러스터 목록”을 고정하고, 예외는 티켓으로 처리

이 스크립트가 판정하는 규칙은 Kubernetes 공식 Version Skew Policy의 kubelet 조항입니다.

- kubelet must not be newer than kube-apiserver
- kubelet may be up to three minor versions older than kube-apiserver[^7]

### 의존성

- bash 5.x
- kubectl 1.37.x 이상(서버 버전이 1.38이 되더라도 `kubectl`은 apiserver와 ±1 minor 지원 정책이므로 1.37/1.38 조합이 일반적으로 성립)[^7]
- jq 1.6+

### 설치(예: Ubuntu)

```bash
sudo apt-get update
sudo apt-get install -y jq
# kubectl 설치는 환경별로 다르니 생략합니다.
```

### 스크립트: fleet-skew-audit.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./fleet-skew-audit.sh                  # kubeconfig의 모든 context 검사
#   ./fleet-skew-audit.sh ctx-a ctx-b      # 지정한 context만 검사

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing dependency: $1" >&2
    exit 2
  }
}

require kubectl
require jq

contexts=("$@")
if [[ ${#contexts[@]} -eq 0 ]]; then
  mapfile -t contexts < <(kubectl config get-contexts -o name)
fi

semver_minor() {
  # input: v1.37.1 or 1.37.1
  local v=${1#v}
  # shellcheck disable=SC2001
  echo "$v" | sed -E 's/^([0-9]+)\.([0-9]+)\..*$/\2/'
}

semver_major() {
  local v=${1#v}
  echo "$v" | sed -E 's/^([0-9]+)\.([0-9]+)\..*$/\1/'
}

fail=0

printf "% -28s % -10s % -10s % -10s %s\n" "CONTEXT" "APISERVER" "KUBELET" "SKEW" "RESULT"
printf "%0.s-" {1..80}; echo

for ctx in "${contexts[@]}"; do
  # server version
  server_json=$(kubectl --context "$ctx" version -o json 2>/dev/null || true)
  if [[ -z "$server_json" ]]; then
    printf "% -28s % -10s % -10s % -10s %s\n" "$ctx" "-" "-" "-" "UNREACHABLE"
    fail=1
    continue
  fi

  apiserver=$(echo "$server_json" | jq -r '.serverVersion.gitVersion')
  apimaj=$(semver_major "$apiserver")
  apimin=$(semver_minor "$apiserver")

  # kubelet versions (may differ across nodes)
  node_json=$(kubectl --context "$ctx" get nodes -o json)
  mapfile -t kubelets < <(echo "$node_json" | jq -r '.items[].status.nodeInfo.kubeletVersion' | sort -u)

  if [[ ${#kubelets[@]} -eq 0 ]]; then
    printf "% -28s % -10s % -10s % -10s %s\n" "$ctx" "$apiserver" "-" "-" "NO_NODES"
    fail=1
    continue
  fi

  # evaluate worst skew (oldest kubelet minor)
  oldest_minor=999
  newest_minor=-1
  newest_kubelet=""
  oldest_kubelet=""

  for kv in "${kubelets[@]}"; do
    kmaj=$(semver_major "$kv")
    kmin=$(semver_minor "$kv")

    # major mismatch is always suspicious
    if [[ "$kmaj" != "$apimaj" ]]; then
      :
    fi

    if (( kmin < oldest_minor )); then
      oldest_minor=$kmin
      oldest_kubelet=$kv
    fi
    if (( kmin > newest_minor )); then
      newest_minor=$kmin
      newest_kubelet=$kv
    fi
  done

  # Policy checks:
  # - kubelet must not be newer than apiserver
  # - kubelet may be up to 3 minors older
  skew_old=$(( apimin - oldest_minor ))
  skew_new=$(( newest_minor - apimin ))

  result="OK"
  detail="oldest=$oldest_kubelet newest=$newest_kubelet"

  if (( skew_new > 0 )); then
    result="VIOLATION(kubelet>apiserver)"
    fail=1
  elif (( skew_old > 3 )); then
    result="VIOLATION(kubelet too old)"
    fail=1
  fi

  # Print representative kubelet versions (range)
  kubelet_repr="$oldest_kubelet"
  if [[ "$oldest_kubelet" != "$newest_kubelet" ]]; then
    kubelet_repr+="..$newest_kubelet"
  fi

  skew_repr="-${skew_old}/+${skew_new}"

  printf "% -28s % -10s % -10s % -10s %s (%s)\n" \
    "$ctx" "$apiserver" "$kubelet_repr" "$skew_repr" "$result" "$detail"
done

exit $fail
```

### 실행 예시

```bash
chmod +x ./fleet-skew-audit.sh
./fleet-skew-audit.sh
```

예상 출력(형태 예시):

```text
CONTEXT                      APISERVER   KUBELET     SKEW       RESULT
--------------------------------------------------------------------------------
prod-us-east-1                v1.37.1     v1.36.4     -1/+0      OK (oldest=v1.36.4 newest=v1.36.4)
stage-us-east-1               v1.36.9     v1.33.7..v1.34.2 -3/+0 VIOLATION(kubelet too old) (oldest=v1.33.7 newest=v1.34.2)
lab-kind                      v1.38.0-alpha.0 v1.38.0-alpha.0 -0/+0 OK (oldest=v1.38.0-alpha.0 newest=v1.38.0-alpha.0)
```

이 결과가 프리즈 주간에 의미하는 바는 단순합니다.

- OK인 클러스터는 “v1.38 RC/GA 업그레이드 윈도우 후보”에 남겨둘 수 있음
- VIOLATION인 클러스터는 “먼저 노드 업그레이드/재이미징/런타임 정리” 같은 선행작업이 필요하고, 프리즈 주간에 무리하게 v1.38로 올리는 계획은 보류하는 게 맞음

Version Skew Policy는 단지 허용 범위를 말하는 게 아니라, 업그레이드 순서와 전제(예: kubelet 업그레이드 전 drain, persistently behind 경고)까지 포함하고 있습니다. 스크립트 결과를 사람의 감으로 해석하지 말고, 정책 문서의 경고를 그대로 운영 룰로 옮기는 편이 사고가 적습니다.[^7]

## v1.38 프리즈 타임라인에 맞춰 플랫폼팀이 실제로 잠그는 것

v1.38 릴리스 캘린더의 해당 구간만 다시 보면, 프리즈를 중심으로 운영 이벤트가 어떻게 생겨야 하는지가 보입니다.

- 2026-11-17 12:00 UTC(= 21:00 KST): Code Freeze + Test Freeze[^1]
- 2026-12-03: release-1.38 branch 생성, v1.38.0-rc.0[^1]
- 2026-12-16: v1.38.0 GA[^1]

이 기간에 플랫폼팀이 잠그는 대상은 보통 코드보다 “운영 표면적”입니다.

### 1) 업그레이드 윈도우 잠금

프리즈가 들어가는 순간(= 2026-11-17 21:00 KST) 이후로는 “이번 v1.38을 언제 받을지”가 아니라 “받을 클러스터는 어디인지”가 확정돼야 합니다.

- fleet 스큐 점검 결과로 업그레이드 가능 클러스터를 확정
- 이 목록을 바탕으로 staging에서 RC를 태울 대상과, GA 이후 프로덕션 대상의 순서를 고정

이걸 못 하면 GA 이후에 모든 팀이 동시에 “우리도 올려주세요”를 외치고, 결국 안전한 순서가 깨집니다.

### 2) 체리픽 큐 잠금

프리즈 이후에 들어오는 변경 요청을 무조건 막을 수는 없습니다. 다만 큐를 잠가야 합니다.

- 어떤 종류의 변경이 체리픽 대상인지 정의(릴리스 블로킹/회귀/보안)
- 예외 요청은 “프리즈 후 3일” 같은 짧은 창만 열고, 그 이후는 다음 릴리스로 넘김(업스트림도 같은 방식으로 운영)[^6]
- 승인 라벨/머지 조건을 강화해서, “누가 승인했는지/왜 승인했는지”를 남김

### 3) 테스트 운영 모드 잠금

Test Freeze 이후에는 테스트 추가보다 안정화입니다. upstream 정의 그대로, 테스트는 고치기/revert/제거 쪽으로 무게가 이동합니다.[^4]

플랫폼팀 내부에서도 프리즈 이후에는 다음을 원칙으로 두는 편이 맞습니다.

- 프리즈 이전: 커버리지 확장, 큰 테스트 구조 변경도 허용
- 프리즈 이후: 신규 시나리오 추가 금지, 실패한 테스트를 green으로 되돌리는 작업에 집중

이렇게 하면 프리즈가 끝나는 시점이 생깁니다.

### 4) 릴리스 노트/변경 로그 잠금

프리즈 주간에 릴리스 노트를 제대로 쌓아두지 않으면, GA 직전에 운영자가 “action required”를 못 보고 맞습니다.

Kubernetes는 PR 단계에서 릴리스 노트를 강제하는 라벨과 프로세스를 문서로 제공합니다. 플랫폼팀도 PR(인프라 변경) 단계에서 같은 강제를 걸어야 프리즈 주간에 문서가 모입니다.[^11]

## 도입 판단 기준: 프리즈 운영을 해야 하는 조직과 하지 말아야 하는 조직

릴리스 컷오프 운영은 비용이 듭니다. 특히 플랫폼팀이 작고, 바뀌는 대상이 많을수록 “운영 이벤트화”가 부담이 될 수 있습니다.

다음 조건이면 프리즈를 운영 이벤트로 만드는 편이 맞습니다.

- 클러스터 수가 많아서 업그레이드를 물리적으로 한 번에 못 함
- 워크로드 스펙트럼이 넓어서 “안전한 업그레이드 순서”가 필요함
- (사내든 upstream든) 체리픽/백포트가 실제로 자주 발생함
- 릴리스 노트/변경 로그를 기반으로 장애 예방을 해야 함

반대로 다음 조건이면 과투자일 수 있습니다.

- 단일 클러스터 또는 소수 클러스터만 운영하고, 업그레이드도 일회성에 가까움
- 완전 관리형 Kubernetes만 쓰고, 조직 내부에서 체리픽/백포트를 사실상 하지 않음
- 변경의 대부분이 애플리케이션 레이어에 있고, 플랫폼 레이어 변경이 거의 없음

다만 “완전 관리형이라 프리즈가 필요 없다”는 결론은 보통 틀립니다. 관리형이어도 버전 스큐와 업그레이드 윈도우 문제는 그대로 남고, 오히려 공급자 캘린더에 종속되기 때문에 컷오프 운영이 더 중요해지는 경우가 많았습니다.

## 참고 자료

- [Kubernetes v1.38 Release Information](https://www.kubernetes.dev/resources/release/)
- [Kubernetes Release Cycle](https://kubernetes.io/releases/release/)
- [Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/)
- [Kubernetes SIG Release: release_phases.md](https://github.com/kubernetes/sig-release/blob/master/releases/release_phases.md)
- [Kubernetes SIG Release: EXCEPTIONS.md](https://github.com/kubernetes/sig-release/blob/master/releases/EXCEPTIONS.md)
- [Kubernetes SIG Release: Enhancements Handbook](https://github.com/kubernetes/sig-release/blob/master/release-team/role-handbooks/enhancements/README.md)
- [Kubernetes Contributors: Adding Release Notes](https://www.kubernetes.dev/docs/guide/release-notes/)
- [Kubernetes SIG Release: Release Manager Handbook](https://github.com/kubernetes/sig-release/blob/master/release-engineering/handbooks/release-manager.md)
- [Prow Plugin Catalog](https://prow.k8s.io/plugins)
- [kOps: Cherry-picking changes back to previous branches](https://kops.sigs.k8s.io/contributing/proposing-a-cherry-pick/)
- [Kubernetes Patch Releases](https://kubernetes.io/releases/patch-releases/)

[^1]: <https://www.kubernetes.dev/resources/release/>
[^2]: <https://kubernetes.io/releases/release/>
[^3]: <https://github.com/kubernetes/sig-release/blob/master/release-engineering/handbooks/release-manager.md>
[^4]: <https://github.com/kubernetes/sig-release/blob/master/releases/release_phases.md>
[^5]: <https://github.com/kubernetes/sig-release/blob/master/release-team/role-handbooks/enhancements/README.md>
[^6]: <https://github.com/kubernetes/sig-release/blob/master/releases/EXCEPTIONS.md>
[^7]: <https://kubernetes.io/releases/version-skew-policy/>
[^8]: <https://github.com/kubernetes/test-infra/blob/master/label_sync/labels.yaml>
[^9]: <https://kops.sigs.k8s.io/contributing/proposing-a-cherry-pick/>
[^10]: <https://github.com/kubernetes/kubeadm/blob/main/docs/managing-e2e-tests.md>
[^11]: <https://www.kubernetes.dev/docs/guide/release-notes/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
