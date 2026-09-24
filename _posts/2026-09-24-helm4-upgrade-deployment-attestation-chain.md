---
title: "Helm 4 업그레이드의 난관은 배포 증명 체인이다"
description: "Helm 4는 차트 문법보다 릴리스/서명/attestation, 레지스트리·캐시, 플러그인 신뢰경계를 다시 설계하게 만듭니다."
date: 2026-09-24 10:17:52 +0900
categories: ["Tools", "Helm"]
tags: ["helm", "kubernetes", "oci", "supply-chain", "provenance", "plugins"]
render_with_liquid: false
---

Helm 4 라인은 2025년 11월 12일 Helm v4.0.0 릴리스 이후 계속 전개 중이고, 2026년 9월 9일에는 Helm v4.3.0이 릴리스되었습니다[^1][^2]. Helm 3는 이미 End of Life 일정이 공지돼 있습니다[^3].

내가 Helm 3→4 전환에서 가장 크게 체감한 포인트는, 팀이 그동안 암묵적으로 합의해온 배포 파이프라인 계약이 사실상 “차트 템플릿 + values”만이 아니라는 점입니다. Helm 4에서 차트 호환성은 상당히 신경 써서 유지되지만[^4], 운영을 흔드는 변화는 다른 곳에서 터집니다.

- 릴리스 아티팩트가 “tag 기반”에서 “digest 기반(불변)”으로 이동할 수 있는 길이 열렸습니다[^5][^4].
- provenance(.prov)와 플러그인 서명 같은 “검증 단위”가 차트 외부(플러그인/바이너리/레지스트리)에까지 확장됩니다[^6][^7].
- 플러그인 시스템 자체가 재설계되면서(post-renderer가 플러그인으로 이동), 신뢰경계가 바뀌고 기존 자동화가 그대로는 못 갑니다[^4][^8].

이 글은 Helm 4를 실제로 굴릴 때 진짜 깨지는 지점(배포 증명 + 레지스트리/캐시 + 플러그인 신뢰경계)을 기준으로, 팀 단위 “파이프라인 계약”을 어떻게 재정의해야 하는지 정리한 기록입니다.

## 차트 API가 유지돼도 운영이 깨지는 지점

Helm 4 문서가 직접 강조하는 요약은 “차트 호환성 유지 + 내부 아키텍처 변화 + 보안/플러그인/캐시 강화”입니다[^4]. 여기서 운영이 깨지는 유형은 대체로 다음처럼 정리됩니다.

1) **CLI 입력이 파이프라인의 API인데, 그 API가 깨진다**

- `helm registry login`은 Helm 4에서 URL scheme(`https://`)나 path를 받지 않습니다. hostname(그리고 optional port)만 받습니다[^4][^5].
- Helm v4에서 `helm list` 동작/옵션 변화로 스크립트가 깨지는 사례가 실제 이슈로 올라왔습니다[^9].

2) **아티팩트 식별 방식이 바뀌면 “캐시/재현성/감사”가 바뀐다**

- OCI 차트를 digest로 설치할 수 있고, digest 불일치 차트는 설치하지 않는 방향으로 공급망 보안이 강화됐습니다[^4].
- OCI 레지스트리로 push/pull할 때 Helm이 digest를 출력하고, 설치도 `oci://...@sha256:...` 형태로 고정할 수 있습니다[^5].

3) **플러그인이 “확장 기능”이 아니라 “실행 권한”이 된다**

- Helm 4에서 post-renderer가 플러그인 타입으로 이동하면서, 기존에 `--post-renderer /path/to/exe` 하던 파이프라인이 깨집니다[^4][^8].
- 플러그인 서명 검증 관련 보안 이슈도 실제로 터졌고(4.1.4에서 패치), 결국 플러그인은 “신뢰할 수 있는 공급망”으로 관리해야 합니다[^10].

여기까지가 Helm 4 업그레이드의 본질입니다. 차트 문법은 대부분 그대로인데, 배포 시스템이 기대하던 불변성/검증/캐싱/권한 경계가 바뀌니 운영이 깨집니다.

## Helm 바이너리 신뢰: get.helm.sh 서명과 GitHub attestation

Helm을 업그레이드할 때 “Helm 바이너리 자체를 어떻게 믿을 것인가”부터 계약으로 박아야 합니다. 이유는 단순합니다. Helm은 클러스터에 적용하는 최종 조립기이고, 여기가 뚫리면 그 다음 단계(차트 서명, digest pinning)는 의미가 약해집니다.

### 1) 바이너리 검증은 선택이 아니라 배포 체인의 첫 관문

Helm 공식 설치 문서는 각 릴리스에 대해 다음을 요구합니다.

- tar.gz 아카이브
- sha256 checksum
- `.asc` signature
- Helm maintainers의 PGP public keys

그리고 검증 예시까지 들어서 `sha256sum -c ...`와 `gpg --verify ...`를 안내합니다[^11]. 특히 중요한 경고가 하나 있습니다.

- KEYS를 매번 upstream에서 가져오지 말고, 한 번 import한 뒤 팀이 통제하는 안전한 장소에 보관하라는 내용입니다. repo가 침해되면 KEYS가 바뀔 수 있고, 그때 로컬에 고정된 키가 있어야 탐지가 가능하다는 취지입니다[^11].

내 경우 이 문장이 Helm 4 전환에서 가장 현실적인 체크포인트였습니다. Helm 3 시절에는 “대충 업그레이드해도” 큰 사고가 잘 안 났는데, Helm 4는 플러그인/레지스트리/캐시까지 연쇄적으로 바뀌어서, 바이너리 검증이 한 단계라도 느슨하면 나중에 원인 규명이 안 됩니다.

### 2) GitHub 릴리스 attestation은 무엇이고, 무엇이 아닌가

`helm/helm` GitHub 릴리스 자산에는 “Release attestation (json)”이 포함됩니다[^2]. Helm v4.3.0 릴리스 페이지에도 이 자산이 올라와 있습니다.

이건 차트 attestation이 아니라 “릴리스 산출물에 대한 GitHub의 attestation” 쪽에 가깝습니다. 즉, 우리 팀이 차트/플러그인/values를 어떻게 믿을지와는 별개로, Helm 바이너리를 검증하는 축 하나가 더 생겼다는 의미입니다.

여기서 중요한 운영 포인트는, attestation이 존재한다는 사실보다 “우리 파이프라인이 그걸 소비(consumption)하는가”입니다. 많은 팀은 여전히 다음 수준에서 멈춥니다.

- 특정 버전의 Helm을 그냥 다운로드해 PATH에 넣는다.

Helm 4로 넘어오면서, 최소한 아래까지는 문서화해야 합니다.

- CI에서 Helm 바이너리 검증(`sha256sum`, `gpg --verify`)을 강제할 것인가
- PGP 키(Helm maintainers, 사내 chart signer, 사내 plugin signer)를 어디에 고정(pin)하고 누가 교체 권한을 가지는가
- GitHub release attestation을 “참조 자료”로만 둘지, 아니면 정책으로 끌어올릴지

이 지점은 내가 예전에 AI API 업데이트 글에서 강조했던 “발표보다 더 무서운 건 조용한 변경”과 성질이 같습니다. 겉보기엔 버전업인데, 사실은 검증 체인의 계약이 바뀌는 쪽이 더 위험합니다[^12].

## Chart provenance(.prov)와 OCI digest: 둘 중 하나만 하면 반쪽이다

Helm 생태계에는 오래된 서명 메커니즘(provenance)이 있습니다. `.tgz.prov` 파일을 만들고, `helm verify` 또는 `helm install --verify`로 검증하는 흐름입니다[^6].

다만 Helm 공식 provenance 문서에는 경고가 붙어 있습니다. “이 페이지는 Helm 4에 맞게 아직 업데이트되지 않았다”는 경고입니다[^6]. 이 경고는 오히려 현실을 잘 보여줍니다.

- Helm 4에서 새로 생긴 공급망 기능(OCI digest install, content cache, 플러그인 타입/서명)은 문서가 분산돼 있고, 팀이 조합해 운영 모델을 만들어야 합니다.

### provenance가 보장하는 것

Helm provenance 문서는 `.prov`가 제공하는 보장을 이렇게 설명합니다.

- chart package(`.tgz`)의 SHA256 digest가 포함된다.
- chart의 `Chart.yaml`이 포함된다.
- 본문 전체가 OpenPGP로 서명된다.

결국 provenance는 “이 `.tgz`는 이 서명자가 이 digest로 패키징했다”를 말해줍니다[^6].

하지만 운영에서 문제가 되는 부분은 그 다음입니다.

- `.tgz`를 어디서 받았는가(레지스트리/리포지토리/캐시)
- 같은 버전 tag가 나중에 바뀌었을 가능성(특히 OCI tag는 mutable)

### Helm 4가 열어준 digest pinning의 의미

Helm 4 Overview는 OCI digest로 설치하는 예시를 명시하고, digest 불일치 chart는 설치되지 않는다고 설명합니다[^4]. OCI 레지스트리 문서에서도 `helm install oci://...@sha256:...` 형태를 별도 섹션으로 설명합니다[^5].

여기서 내가 정리한 결론은 단순합니다.

- provenance는 “누가 만들었나(서명자)”를 강화하고,
- digest pinning은 “무엇을 설치했나(불변 식별자)”를 강화합니다.

둘 중 하나만 하면, 공격/사고 시나리오가 남습니다.

- provenance만 쓰면: 동일 버전의 `.tgz`가 다른 저장소에서 바뀌어도, 파이프라인이 `.prov`를 제대로 따라오지 않으면 검증이 비활성화될 수 있습니다(사람이 `--verify`를 빼는 순간 끝입니다).
- digest만 쓰면: “digest가 맞는 것”은 보장해도 그 digest가 ‘누가 서명한 릴리스인지’를 별도로 추적해야 합니다. 이때 digest 목록을 어디에 보관하는지가 또 계약이 됩니다.

그래서 Helm 4 운영 모델에서는 **배포 증명**을 다음처럼 층으로 나누는 게 안전합니다.

- Helm 바이너리(도구) 검증
- 차트 아카이브(.tgz) provenance 검증
- OCI digest pinning(불변 설치)

그리고 실제 설치 경로(레지스트리/캐시)가 이 층들을 연결합니다.

## 레지스트리/캐시: Helm 4에서 파이프라인 비용이 갈리는 곳

Helm 4는 “OCI digest support”와 “content-based caching”을 요약에 넣을 정도로 캐시/레지스트리를 중요하게 다룹니다[^4]. Full Changelog에도 content cache 추가가 breaking change로 기록돼 있습니다[^13].

### 1) `helm registry login`은 이제 hostname만 받는다

Helm 4 Overview에 breaking change로 들어가 있고, OCI 레지스트리 문서에 표로 명시돼 있습니다.

- `ghcr.io`는 OK
- `https://ghcr.io`는 NO
- `ghcr.io/myrepo`는 NO

[^5][^4]

이게 왜 운영을 흔드냐면, 많은 조직 문서/런북/스크립트가 “레지스트리 URL”을 그대로 넣기 때문입니다. Helm v4.1.0 이후로는 그 습관이 바로 장애로 이어집니다. 실제로 이 변화 때문에 Google Artifact Registry 같은 문서 예시(`https://...`)를 그대로 썼다가 로그인 실패를 보고한 이슈도 있습니다[^14].

팀 계약 관점에서는 변수를 분리해야 합니다.

- `REGISTRY_HOST`: `europe-west1-docker.pkg.dev` 같은 hostname
- `REPOSITORY_PATH`: `org/project/charts` 같은 path

그리고 `helm registry login`에는 HOST만 들어가야 합니다.

### 2) 캐시 디렉터리의 “성격”이 바뀌면 CI 최적화 방식이 바뀐다

Helm은 XDG 구조를 따르고, `HELM_CACHE_HOME`, `HELM_CONFIG_HOME`, `HELM_DATA_HOME` 같은 환경변수를 노출합니다[^11]. Helm 4 코드 레벨에서도 env vars 목록에 `HELM_CONTENT_CACHE`가 포함돼 있습니다[^15].

여기서 Helm 4의 변화는 단순히 “캐시 디렉터리 위치”가 아니라, content-based cache라는 개념이 들어왔다는 점입니다[^13][^4].

운영에서 이게 의미하는 바는 다음과 같습니다.

- Helm chart를 어디서 받든(HTTP repo든 OCI든), 동일 content면 재사용 가능한 캐시 구조로 가려는 방향입니다.
- CI에서 “repo index 캐시만” 저장해도 효과가 있는 팀이 있고, “content cache를 같이 저장해야” 병목이 풀리는 팀이 생깁니다.

내 경우 Helm 3 시절에는 대충 `~/.cache/helm/repository`만 저장해도 충분한 경우가 많았습니다. Helm 4로 오면 OCI pull이 늘고 digest pinning을 시작하면서, 차트 내용 자체를 content cache로 재사용하는 쪽이 체감이 큽니다. 이건 개발자가 체감하는 기능이 아니라 CI 비용으로 체감하는 기능입니다.

### 3) 레지스트리 자체가 신뢰 경계가 된다

OCI digest install을 도입하면, 레지스트리는 “tag 제공자”가 아니라 “digest 콘텐츠 주소 공간”이 됩니다. 이때 레지스트리 정책이 바뀝니다.

- tag overwrite를 허용할 것인가
- retention policy로 오래된 blob을 지울 것인가
- pull-through cache(ECR 등)를 붙일 것인가

Helm은 이걸 대신 결정해주지 않습니다. Helm 4가 제공하는 건 `oci://...@sha256:...` 형태의 소비 방식이고[^5], 운영이 해야 하는 건 “digest가 가리키는 blob이 일정 기간 보존되도록 레지스트리를 운영”하는 일입니다.

## 플러그인: 기능 확장이 아니라 신뢰경계 재설정

Helm 4 Released 글은 Helm 4의 새 기능 중 하나로 “Redesigned plugin system”과 “Post-renderers are now plugins”를 언급합니다[^1]. Helm 4 Overview에도 post-renderer 변경이 breaking change로 올라와 있습니다[^4].

### 1) post-renderer가 플러그인이 되면 무엇이 달라지나

핵심은 이겁니다.

- Helm 3: `--post-renderer`에 실행 파일 경로를 줄 수 있었다.
- Helm 4: `--post-renderer`에 “plugin name”을 줘야 한다.

[^8]

이게 단순히 입력 형식 변화가 아닙니다. 팀 단위 파이프라인에서 post-renderer는 보통 다음 용도로 쓰입니다.

- OPA 정책용 label/annotation 강제
- 사내 platform 요구사항(internal sidecar, PodSecurityContext 등) 주입
- GitOps 도구와 충돌 회피를 위한 metadata 정규화

Helm 4에서는 이게 “클러스터에 적용 직전 단계에서 실행되는 코드”로서 plugin supply chain에 들어갑니다. 즉, Helm 4에서 post-renderer는 이제 도구 바깥의 임의 바이너리가 아니라, Helm이 관리하는 플러그인 디렉터리(`HELM_PLUGINS`) 아래로 들어오고 서명/검증 대상이 될 수 있습니다[^11][^7].

### 2) 플러그인 타입과 runtime이 명시되면서 생기는 장단

Helm 4 플러그인은 타입이 명시됩니다.

- `cli/v1`
- `getter/v1`
- `postrenderer/v1`

[^16]

그리고 Helm 3 플러그인을 Helm 4로 마이그레이션하는 문서에서, `plugin.yaml`에 `apiVersion`, `type`, `runtime`이 필수로 들어간다고 못 박습니다[^8].

이 구조의 장점은 “플러그인이 뭘 하려는지”를 Helm이 알고, 더 강한 격리(예: optional Wasm runtime)로 가는 발판이 된다는 겁니다[^4].

단점은 명확합니다.

- 기존에 “그냥 실행 파일 하나”로 유지되던 post-renderer/도우미 스크립트가 플러그인 패키징 대상이 됩니다.
- 패키징이 되면 버전/배포/서명/키 회전까지 고려해야 합니다.

운영 입장에서는 단점 같지만, 공급망 관점에서는 이게 맞는 방향입니다. post-renderer는 원래부터 “배포 파이프라인에서 권한이 가장 센 코드”였고, 다만 관리가 안 됐을 뿐입니다.

### 3) 플러그인 검증을 느슨하게 두면 실제로 터진다

Helm 4.0.0~4.1.3 구간에는 “서명 검증이 required인 상황에서도 `.prov`가 없는 플러그인이 설치되는” 보안 문제가 있었고, 4.1.4에서 패치되었습니다[^10]. Advisory는 impact를 분명히 적습니다.

- malicious plugin이 arbitrary code execution을 할 수 있다.

그리고 Helm에는 플러그인 서명 검증을 위한 `helm plugin verify` 커맨드가 있습니다[^7].

이 조합을 보면, Helm 4에서 플러그인 신뢰경계는 더 이상 “개발자 로컬의 편의 기능”이 아닙니다. 팀 단위로 키/서명/검증을 설계하지 않으면, 도구 업그레이드가 곧 공격면 확장입니다.

## 실전: OCI 차트 + .prov + digest 고정 배포 흐름

여기서는 로컬에서 재현 가능한 형태로 “차트를 OCI 레지스트리에 push하고, digest로 설치하는” 흐름을 구성합니다. 핵심은 두 가지를 동시에 만족시키는 겁니다.

- provenance(.prov)로 서명자/무결성 검증 축을 확보
- digest pinning으로 불변 설치 축을 확보

Helm 공식 OCI 레지스트리 문서가 제공하는 출력 예시(푸시/풀/설치 결과)를 그대로 기준으로 삼아 흐름을 정리합니다[^5].

### 0) 준비물

- Docker(로컬 레지스트리 실행용)
- Helm 4.x
- (선택) GPG 키: chart signing 및 plugin signing에 사용

### 1) 로컬 OCI 레지스트리 실행

```bash
docker run -d --rm --name oci-registry -p 5000:5000 registry:2
```

### 2) 차트 생성 및 패키징

```bash
helm create mychart
# 필요하면 Chart.yaml, values.yaml, templates 수정
helm package mychart
ls -1 mychart-*.tgz
```

서명을 붙이려면 `.prov`를 생성해야 합니다. Helm provenance 문서는 `helm package --sign --key ... --keyring ...` 흐름을 설명합니다[^6].

```bash
# 예시: keyring/secring은 팀 상황에 맞게 준비
helm package --sign --key "YOUR SIGNING KEY" --keyring ~/.gnupg/secring.gpg mychart
ls -1 mychart-*.tgz mychart-*.tgz.prov
```

### 3) 레지스트리 로그인: hostname만

```bash
helm registry login -u myuser localhost:5000
```

OCI 문서는 성공 시 “Login succeeded”를 출력하는 예시를 제공합니다[^5].

주의할 점은 `http://localhost:5000`처럼 scheme를 넣지 않는 것입니다. Helm 4 breaking change입니다[^5][^4].

### 4) OCI로 push (그리고 digest를 확보)

```bash
helm push mychart-0.1.0.tgz oci://localhost:5000/helm-charts
```

Helm 문서 예시 출력은 아래 형태입니다.

```text
Pushed: localhost:5000/helm-charts/mychart:0.1.0
Digest: sha256:ec5f08ee7be8b557cd1fc5ae1a0ac985e8538da7c93f51a51eff4b277509a723
```

[^5]

여기서 digest는 “배포 파이프라인 계약”에서 가장 중요한 값이 됩니다. tag(`0.1.0`)는 사람이 보기 쉬운 이름이고, digest는 배포가 실제로 설치해야 하는 불변 식별자입니다.

또 하나 중요한 점: OCI 문서는 `.prov` 파일이 `.tgz` 옆에 있으면 push 시 자동으로 레지스트리에 업로드된다고 명시합니다[^5]. 즉, provenance를 “HTTP chart repo의 부속 파일”로만 보던 모델에서, “OCI artifact의 일부 레이어”로 결합할 수 있습니다.

### 5) digest로 설치(불변)

```bash
helm install myrelease oci://localhost:5000/helm-charts/mychart@sha256:52ccaee6d4dd272e54bfccda77738b42e1edf0e4a20c27e23f0b6c15d01aef79
```

이 설치 방식이 공급망 관점에서 강한 이유는, 레지스트리 tag가 바뀌어도 digest는 바뀌지 않기 때문입니다[^5].

내가 팀에 계약으로 박는 문장은 보통 이런 형태가 됩니다.

- production 배포는 `oci://...@sha256:...`만 허용한다.
- tag 기반 설치는 dev에서만 허용한다.

이걸 하면, 배포 실패 시에도 원인 후보가 확 줄어듭니다.

- 레지스트리 장애
- digest blob 삭제(retention)
- credentials/permission
- Helm/플러그인 버전 차이

반대로 “tag 기반 + cache 없음 + 플러그인 버전 제각각”이면, 실패해도 무엇이 달라졌는지 추적이 안 됩니다.

## 실전: Helm 3 post-renderer 실행 파일을 Helm 4 플러그인으로 포장

Helm 4에서 post-renderer는 플러그인이기 때문에, 기존에 파이프라인에서 실행 파일 경로로 넘기던 방식은 깨집니다[^8].

Helm 문서에는 “모든 리소스에 label을 주입하는 postrenderer 플러그인” 튜토리얼이 있고, `plugin.yaml` 예시까지 제공합니다[^17]. 이걸 기준으로 “기존 실행 파일 감싸기” 형태를 구성할 수 있습니다.

### 1) 플러그인 디렉터리 구성

```bash
mkdir -p $HOME/code/helm/plugins/label-injector
cd $HOME/code/helm/plugins/label-injector
```

### 2) `plugin.yaml` 작성

문서 예시의 핵심 필드는 다음입니다.

- `apiVersion: v1`
- `type: postrenderer/v1`
- `runtime: subprocess`
- `runtimeConfig.platformCommand`

[^17][^8]

```yaml
# plugin.yaml
apiVersion: v1
type: postrenderer/v1
name: label-injector
version: 0.1.0
runtime: subprocess
runtimeConfig:
  platformCommand:
    - command: ${HELM_PLUGIN_DIR}/inject-labels.sh
```

여기서 중요한 계약 포인트는 `${HELM_PLUGIN_DIR}`입니다. Helm이 플러그인 실행 경로를 통제하는 구조로 가져가면서, 기존처럼 임의 위치의 바이너리를 직접 호출하는 습관을 줄일 수 있습니다.

### 3) 실제 post-renderer 스크립트 작성

Helm 튜토리얼은 `yq`를 사용합니다[^17]. 여기서는 개념을 단순화해서, stdin으로 받은 multi-doc YAML에 label을 주입하는 형태로 둡니다(운영에서는 조직 표준 라벨, traceability 라벨, 정책 엔진이 필요한 라벨 등을 넣는 경우가 많습니다).

```bash
# inject-labels.sh
#!/usr/bin/env bash
set -euo pipefail

# Helm post-renderer는 렌더된 YAML을 stdin으로 주고,
# post-renderer는 수정된 YAML을 stdout으로 내보내야 합니다.

if ! command -v yq >/dev/null 2>&1; then
  echo "yq is required" >&2
  exit 1
fi

# 모든 문서의 metadata.labels에 주입
# (실전에서는 kind/namespace별 조건을 더 넣는 게 보통입니다.)
yq '(.metadata.labels.helm_postrendered //= "true")' -
```

```bash
chmod +x inject-labels.sh
```

### 4) 플러그인 설치 및 적용

```bash
helm plugin install $HOME/code/helm/plugins/label-injector
helm plugin list
```

이제 Helm 4에서는 다음처럼 plugin name을 `--post-renderer`에 넘깁니다.

```bash
helm install myrelease ./mychart --post-renderer label-injector
```

이게 바로 Helm 4에서 post-renderer가 플러그인으로 이동한 의미입니다. 이 순간부터 post-renderer는 “로컬 실행 파일”이 아니라 “배포 파이프라인 구성요소”가 됩니다.

그리고 여기서 더 중요한 운영 포인트가 있습니다.

- 이 플러그인을 어떻게 배포할 것인가(내장? 외부 artifact?)
- 플러그인을 서명하고 검증할 것인가

Helm에는 플러그인 서명 검증 커맨드가 있고, `.prov` 기반으로 검증한다고 명시합니다[^7]. Helm 4.1.4 이전에는 이 검증 체인이 느슨해지는 취약점이 있었고 패치되었습니다[^10].

이 조합 때문에 Helm 4 운영에서 플러그인은 “아무나 설치하는 도구”가 아니라 **신뢰경계**로 다뤄야 합니다.

## 업그레이드 체크리스트: 팀 계약으로 못 박아야 하는 항목

Helm 4를 도입할 때, 나는 아래를 “업그레이드 작업”이 아니라 “배포 계약 재정의”로 문서화했습니다.

### 1) 아티팩트 식별자 계약

- chart는 가능하면 OCI로 유통한다[^5].
- production 설치는 digest pinning을 원칙으로 한다[^5][^4].
- provenance(.prov)는 생성/보관/배포 정책을 정한다[^6].

### 2) 레지스트리 로그인/자격증명 계약

- `helm registry login`에는 hostname만 들어간다[^4][^5].
- 기존 문서/스크립트에서 `https://REGISTRY/...` 형태를 전수 조사한다[^14].

### 3) 캐시/성능 계약

- CI에서 무엇을 캐시할지(Repository cache vs Content cache) 정의한다.
- Helm env vars(`HELM_CACHE_HOME`, `HELM_REPOSITORY_CACHE`, `HELM_CONTENT_CACHE`)를 컨테이너 런타임/CI 워커에서 어떻게 매핑할지 표준화한다[^15][^13].

### 4) 플러그인 공급망 계약

- post-renderer는 “플러그인으로 패키징된 artifact”만 허용한다[^8].
- 플러그인은 서명/검증 흐름을 강제하고, Helm 버전 하한을 보안 패치 버전 이상으로 둔다(최소 4.1.4 이상)[^10].
- 플러그인 타입(cli/getter/postrenderer)별로 허용 목록(allowlist)을 둔다[^16].

### 5) 깨지는 자동화(이미 보고된 사례)를 사전 제거

- `helm list` 옵션/기본 동작 변화로 스크립트가 깨질 수 있다[^9].
- post-renderer 인자 방식이 깨진다[^4][^8].
- 레지스트리 로그인 인자 방식이 깨진다[^5].

이 체크리스트는 기능 나열이 아니라 사고 대응을 위한 우선순위입니다. Helm 4 업그레이드를 “차트 lint 통과”로 끝내면, 운영에서 터지는 건 대개 인증/캐시/플러그인/검증 체인입니다.

## 지금 Helm 4로 전환하면서 내가 내린 결론

Helm 4에서 차트 API 호환성은 중요한 요소지만, 실제 업그레이드 난이도를 결정하는 건 그게 아닙니다. Helm 4는 OCI digest 설치, content-based caching, 플러그인 타입/런타임/서명 같은 요소를 통해 “배포 시스템이 어떤 증거를 남기고 무엇을 신뢰할지”를 다시 정의하게 만듭니다[^4][^5][^8].

Helm 3→4 전환을 도구 버전업으로 취급하면, 결국 가장 약한 고리(레지스트리 로그인 입력, 캐시 누락으로 인한 재현성 붕괴, 서명 없는 플러그인 실행)에서 운영이 깨집니다. 반대로 이 전환을 팀 단위 파이프라인 계약 재정의로 접근하면, Helm 4는 공급망 사고 가능성을 줄이고 장애 원인 추적성을 높이는 쪽으로 작동합니다.

## 참고 자료

- [helm/helm 릴리스 목록](https://github.com/helm/helm/releases)
- [Helm 4 Overview](https://docs.helm.sh/docs/overview/)
- [Helm 4 Full Changelog](https://docs.helm.sh/docs/changelog/)
- [Helm 4 Released](https://blog.helm.sh/uk/blog/helm-4-released/)
- [Helm 3 End of Life](https://helm.sh/blog/helm-v3-end-of-life)
- [Installing Helm](https://helm.sh/docs/intro/install/)
- [Use OCI-based registries](https://helm.sh/docs/topics/registries/)
- [Helm Provenance and Integrity](https://helm.sh/docs/topics/provenance/)
- [Plugins Overview](https://docs.helm.sh/docs/plugins/overview/)
- [Migrate v3 Plugins to Helm 4](https://helm.sh/docs/plugins/migrate/)
- [Tutorial: Build a Postrenderer Plugin](https://helm.sh/docs/plugins/developer/tutorial-postrenderer-plugin)
- [helm plugin verify](https://helm.sh/docs/helm/helm_plugin_verify/)
- [GHSA-q5jf-9vfq-h4h7: Plugin verification fails open when .prov is missing](https://github.com/helm/helm/security/advisories/GHSA-q5jf-9vfq-h4h7)
- [Registry Login with HTTPS URL #31962](https://github.com/helm/helm/issues/31962)
- [Breaking change to helm list cli command in v4 #31784](https://github.com/helm/helm/issues/31784)
- [Helm env vars 예시가 포함된 환경 설정 코드](https://fossies.org/linux/helm/pkg/cli/environment.go)

[^1]: <https://blog.helm.sh/uk/blog/helm-4-released/>
[^2]: <https://github.com/helm/helm/releases>
[^3]: <https://helm.sh/blog/helm-v3-end-of-life>
[^4]: <https://docs.helm.sh/docs/overview/>
[^5]: <https://helm.sh/docs/topics/registries/>
[^6]: <https://helm.sh/docs/topics/provenance/>
[^7]: <https://helm.sh/docs/helm/helm_plugin_verify/>
[^8]: <https://helm.sh/docs/plugins/migrate/>
[^9]: <https://github.com/helm/helm/issues/31784>
[^10]: <https://github.com/helm/helm/security/advisories/GHSA-q5jf-9vfq-h4h7>
[^11]: <https://helm.sh/docs/intro/install/>
[^12]: <https://daewooki.github.io/posts/2026-3-ai-api-1/>
[^13]: <https://docs.helm.sh/docs/changelog/>
[^14]: <https://github.com/helm/helm/issues/31962>
[^15]: <https://fossies.org/linux/helm/pkg/cli/environment.go>
[^16]: <https://docs.helm.sh/docs/plugins/overview/>
[^17]: <https://helm.sh/docs/plugins/developer/tutorial-postrenderer-plugin>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
