---
title: "2025년형 GitHub Actions로 “안전하고 빠른” CI/CD 파이프라인 구축하기: 재사용·동시성·OIDC까지 한 번에"
date: 2025-12-31 02:13:10 +0900
categories: [DevOps, Tutorial]
tags: [devops, tutorial, trend, 2025-12]
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
2025년의 CI/CD는 “돌아가기만 하면 된다”를 넘어 **속도(개발 리드타임)**, **안정성(배포 충돌/롤백)**, **보안(공급망/토큰 유출)**을 동시에 만족해야 합니다. GitHub Actions는 저장소 이벤트와 코드(Workflow YAML)가 결합된 형태라 진입장벽이 낮지만, 규모가 커질수록 YAML이 중복되고(팀/서비스별 파편화), 병렬 실행으로 리소스가 낭비되며, 토큰/시크릿 관리가 복잡해집니다.

그래서 2025년에 “잘 만든” Actions 파이프라인은 보통 아래 3가지를 중심으로 설계합니다.

- **재사용(reusable workflows)**로 파이프라인 표준화/중복 제거 (`workflow_call`) ([docs.github.com](https://docs.github.com/en/enterprise-cloud%40latest/actions/using-workflows/reusing-workflows?utm_source=openai))  
- **동시성 제어(concurrency)**로 중복 실행/배포 충돌 방지 (`cancel-in-progress`, group 전략) ([docs.github.com](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency?utm_source=openai))  
- **OIDC 기반의 단기 자격 증명**으로 클라우드 배포 시 장기 Secret 제거 (`id-token: write`, 클레임 기반 신뢰) ([docs.github.com](https://docs.github.com/en/actions/reference/security/oidc?utm_source=openai))  

---

## 🔧 핵심 개념
### 1) CI/CD 파이프라인을 “컴포넌트”로 쪼개는 이유: Reusable Workflow
단일 저장소에서 워크플로우가 늘어나면, 테스트/빌드/배포 단계가 서비스마다 조금씩 달라지면서 YAML 복붙이 시작됩니다. GitHub Actions의 **reusable workflows**는 이를 해결하기 위해 `on: workflow_call`로 “호출 가능한 워크플로우”를 만들고, 각 저장소는 이를 “호출”만 하는 방식으로 표준화를 유도합니다. ([docs.github.com](https://docs.github.com/en/enterprise-cloud%40latest/actions/using-workflows/reusing-workflows?utm_source=openai))

여기서 중요한 디테일:
- reusable workflow는 `.github/workflows` **하위 디렉터리를 지원하지 않습니다**(의외로 자주 막힘). ([docs.github.com](https://docs.github.com/en/enterprise-cloud%40latest/actions/using-workflows/reusing-workflows?utm_source=openai))  
- 입력/시크릿을 `inputs`, `secrets`로 명시적으로 설계할 수 있습니다. ([docs.github.com](https://docs.github.com/en/enterprise-cloud%40latest/actions/using-workflows/reusing-workflows?utm_source=openai))  
- **Environment secrets는 `workflow_call`로 전달이 안 되고**, called workflow에서 `environment:`를 쓰면 그 환경 시크릿이 우선됩니다(설계 시 의도적으로 활용하거나, 반대로 예상치 못한 우선순위에 주의). ([docs.github.com](https://docs.github.com/en/enterprise-cloud%40latest/actions/using-workflows/reusing-workflows?utm_source=openai))  

### 2) “같은 브랜치에서 여러 번 돌면 무엇이 취소되는가”: Concurrency의 진짜 의미
`concurrency`는 단순히 “동시에 못 돌게”가 아니라, **동일 그룹에서 최대 1 running + 1 pending만 허용**한다는 점이 핵심입니다. 새 실행이 들어오면 기존 pending을 취소하고, `cancel-in-progress: true`면 running도 취소합니다. ([docs.github.com](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency?utm_source=openai))  
즉, 배포 파이프라인에서는 보통:
- PR 검증: 최신 커밋만 의미 있으니 **cancel-in-progress=true**
- main 배포: 중간이 끊기면 위험하니 **cancel-in-progress=false** + 환경 단위로 직렬화

### 3) 2025년 배포 보안의 표준: OIDC로 “장기 키” 없애기
클라우드 배포에서 가장 흔한 사고는 “장기 Access Key가 Actions Secret에 들어있고, 그것이 유출/오남용”입니다. GitHub Actions는 OIDC 토큰을 발급할 수 있고, 클라우드 쪽에서 `sub` 같은 클레임 조건으로 신뢰 정책을 구성해 **워크플로우 실행 컨텍스트에만** 권한을 부여합니다. ([docs.github.com](https://docs.github.com/en/actions/reference/security/oidc?utm_source=openai))  
이때 워크플로우는 최소한 `permissions: id-token: write`가 필요합니다. ([docs.github.com](https://docs.github.com/en/actions/reference/security/oidc?utm_source=openai))  

---

## 💻 실전 코드
아래 예시는 “Node.js 앱” 기준이지만, 구조 자체는 언어와 무관합니다.

- PR: lint/test/build (빠르게, 캐시 적극 활용)
- main: build → artifact 업로드 → deploy(환경 직렬화, OIDC 사용 가정)
- 중복 제거: build/test는 reusable workflow로 분리

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
  push:
    branches: [ "main" ]

# 같은 브랜치에서 CI 중복 실행 제어
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true # PR/브랜치 최신 커밋만 남기기 ([docs.github.com](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency?utm_source=openai))

permissions:
  contents: read

jobs:
  test_build:
    uses: ./.github/workflows/_reusable_build.yml
    with:
      node-version: "20"
      run-tests: true
```

```yaml
# .github/workflows/cd.yml
name: CD

on:
  push:
    branches: [ "main" ]

# 배포는 환경 단위로 직렬화(충돌 방지)
concurrency:
  group: deploy-production
  cancel-in-progress: false # 운영 배포는 중간 취소보다 '완주'가 안전

permissions:
  contents: read
  id-token: write  # OIDC 토큰 발급에 필요 ([docs.github.com](https://docs.github.com/en/actions/reference/security/oidc?utm_source=openai))

jobs:
  build:
    uses: ./.github/workflows/_reusable_build.yml
    with:
      node-version: "20"
      run-tests: true

  upload_artifact:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v4

      # v4는 immutable artifact + 동일 이름 재업로드 불가(매트릭스면 이름에 suffix 필수) ([github.com](https://github.com/actions/upload-artifact?utm_source=openai))
      - name: Upload dist
      - uses: actions/upload-artifact@v4
        with:
          name: dist-${{ github.sha }}
          path: dist/
          retention-days: 7

  deploy:
    runs-on: ubuntu-latest
    needs: upload_artifact
    environment: production
    steps:
      - name: (Example) Request OIDC + Deploy
        run: |
          echo "Here you would run cloud login action using OIDC, then deploy."
          echo "OIDC claims (sub, ref, environment 등) 기반으로 클라우드 신뢰정책을 구성합니다."
```

```yaml
# .github/workflows/_reusable_build.yml
name: Reusable Build

on:
  workflow_call:
    inputs:
      node-version:
        required: true
        type: string
      run-tests:
        required: true
        type: boolean

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}

      # 캐시는 "의존성/빌드 산출 중 재사용 가능한 것"에만 적용
      # cache key는 lockfile 해시를 섞어 '의존성 변동'에 민감하게 ([github.com](https://github.com/actions/cache?utm_source=openai))
      - name: Cache npm
        uses: actions/cache@v4
        with:
          path: |
            ~/.npm
          key: npm-${{ runner.os }}-${{ hashFiles('**/package-lock.json') }}
          restore-keys: |
            npm-${{ runner.os }}-

      - name: Install
        run: npm ci

      - name: Test
        if: ${{ inputs.run-tests }}
        run: npm test

      - name: Build
        run: npm run build
```

---

## ⚡ 실전 팁
1) **Artifact(v4)와 Cache를 혼동하지 마세요**
- Cache: “다음 실행에서 재사용” 목적(의존성/빌드 캐시). 키 설계가 전부입니다. ([github.com](https://github.com/actions/cache?utm_source=openai))  
- Artifact(v4): “이번 워크플로우 런에서 전달/보관” 목적. v4는 **동일 artifact name으로 여러 번 업로드가 실패**하므로 매트릭스/멀티잡이면 이름에 OS/sha 등을 반드시 포함하세요. ([github.com](https://github.com/actions/upload-artifact?utm_source=openai))  

2) **Concurrency는 ‘취소 정책’보다 ‘그룹 키’가 더 중요합니다**
`group`를 대충 잡으면 서로 관계없는 워크플로우가 취소되는 사고가 납니다. 문서에서도 여러 워크플로우가 공존하면 `github.workflow`를 포함해 유니크하게 만들라고 안내합니다. ([docs.github.com](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency?utm_source=openai))  
- CI는 보통 `group: ${{ github.workflow }}-${{ github.ref }}`
- CD는 환경 기반 `group: deploy-${{ inputs.env || 'prod' }}` 같은 식

3) **Reusable workflow의 “시크릿/환경” 경계는 설계 포인트**
- `workflow_call`로 시크릿을 깔끔히 넘길 수 있지만, **Environment secrets는 전달이 아니라 ‘called workflow가 environment를 선언했을 때 그 환경 시크릿을 직접 사용’**하는 모델입니다. ([docs.github.com](https://docs.github.com/en/enterprise-cloud%40latest/actions/using-workflows/reusing-workflows?utm_source=openai))  
→ 조직 표준 파이프라인을 만들 때, “배포 job은 반드시 environment를 선언한다” 같은 규칙이 생기는 이유입니다.

4) **OIDC는 단순 기능이 아니라 ‘권한 모델’입니다**
OIDC를 쓰면 “토큰을 발급받는 워크플로우”를 클라우드가 신뢰해야 합니다. 이때 `sub`(예: repo/ref/environment 등) 클레임을 최대한 좁혀야, 동일 조직의 다른 저장소/브랜치에서 토큰을 악용하기 어렵습니다. GitHub는 OIDC 토큰에 다양한 클레임(예: `environment`, `ref`, `repository`)을 포함합니다. ([docs.github.com](https://docs.github.com/en/actions/reference/security/oidc?utm_source=openai))  

---

## 🚀 마무리
2025년 GitHub Actions 기반 CI/CD의 핵심은 “YAML을 잘 쓰는 법”이 아니라, **파이프라인을 제품처럼 설계**하는 겁니다.

- 재사용(`workflow_call`)으로 표준화/중복 제거 ([docs.github.com](https://docs.github.com/en/enterprise-cloud%40latest/actions/using-workflows/reusing-workflows?utm_source=openai))  
- 동시성(`concurrency`)으로 낭비와 배포 충돌 제거 ([docs.github.com](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency?utm_source=openai))  
- OIDC로 장기 Secret을 없애고, 클레임 기반 신뢰로 배포 권한을 최소화 ([docs.github.com](https://docs.github.com/en/actions/reference/security/oidc?utm_source=openai))  
- Artifact(v4)/Cache의 역할을 분리해 속도와 안정성을 동시에 챙기기 ([github.com](https://github.com/actions/upload-artifact?utm_source=openai))  

다음 학습으로는 (1) 조직 단위 reusable workflow 배포/버저닝 전략, (2) OIDC trust policy를 repo/ref/environment 단위로 쪼개는 방법, (3) self-hosted runner 그룹/격리 설계까지 확장하면 “엔터프라이즈급 Actions”에 도달할 수 있습니다.