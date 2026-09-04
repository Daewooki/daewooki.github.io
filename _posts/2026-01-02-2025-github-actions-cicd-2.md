---
title: "2025년형 GitHub Actions CI/CD 파이프라인: “자동화”를 넘어 “신뢰 가능한 배포”까지"
date: 2026-01-02 02:21:55 +0900
categories: [DevOps, Tutorial]
tags: [devops, tutorial, trend, 2026-01]
render_with_liquid: false
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
2025년의 CI/CD는 단순히 “빌드-테스트-배포”를 자동화하는 수준에서 끝나지 않습니다. 파이프라인이 커질수록 **권한 관리(credential leak)**, **공급망 공격(supply-chain attack)**, **배포 경쟁 상태(race condition)** 같은 문제가 실제 장애/사고로 이어지기 때문입니다.  
GitHub Actions는 여전히 가장 널리 쓰이는 선택지지만, 이제는 “YAML 몇 줄”이 아니라 **보안·재현성·운영 안정성까지 포함한 설계**가 중요해졌습니다. 특히 GitHub는 클라우드 배포 인증에서 **OIDC(OpenID Connect)**를 강하게 권장하고, 빌드 산출물에 대해 **Artifact Attestations(서명된 provenance)**까지 제공하면서 “검증 가능한 배포”를 현실적인 표준으로 만들고 있습니다. ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))

---

## 🔧 핵심 개념
### 1) 파이프라인을 “Stage”로 쪼개는 이유: 신뢰 경계(Trust Boundary)
실무형 GitHub Actions 파이프라인은 보통 다음 3단으로 설계합니다.

- **CI (build/test)**: PR마다 빠르게 검증, 여기서는 배포 권한이 없어야 함
- **Package/Release**: main/tag에서만 산출물 생성(재현성, 버전 정책)
- **CD (deploy)**: 보호된 환경(environment)에서만 배포, 승인/브랜치 제한 적용

이렇게 나누면 “테스트 job이 가진 권한”과 “배포 job이 가진 권한”을 분리할 수 있고, 사고 반경을 줄입니다.

### 2) 2025년형 인증의 핵심: OIDC로 “long-lived secret” 제거
GitHub Actions는 OIDC로 외부 클라우드(AWS/Azure 등)에 **짧은 수명의 토큰**을 교환해 접근할 수 있게 합니다. 즉, repo secret에 장기 키를 저장하는 대신,
- workflow가 **OIDC JWT**를 발급받고
- 클라우드가 그 JWT의 claim(예: repo/branch/environment)을 조건으로
- 제한된 역할(role)만 Assume 하도록 구성합니다. ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))

여기서 중요한 디테일:
- workflow/job에 `permissions: id-token: write`가 없으면 OIDC 토큰을 못 받습니다. ([docs.github.com](https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-azure?source=post_page-----1420f360a086--------------------------------&utm_source=openai))
- AWS는 trust policy에서 `token.actions.githubusercontent.com:sub` 조건으로 **어떤 repo/branch/environment만 역할을 Assume할지** 제한하라고 명시합니다. ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))

### 3) “빌드가 진짜 우리 CI에서 나온 게 맞나?”: Artifact Attestations
Artifact Attestations는 빌드 산출물에 대해 **위조 불가능한 provenance(출처 증명)**을 서명해 남깁니다. 이 provenance에는 workflow 링크, repo/org, commit SHA, trigger event 등 검증에 필요한 정보가 포함됩니다. ([docs.github.com](https://docs.github.com/en/actions/concepts/security/artifact-attestations?utm_source=openai))  
GitHub는 이를 Sigstore 기반으로 제공하며, 결국 CD 단계에서 “검증된 산출물만 배포” 같은 정책이 가능해집니다. ([docs.github.com](https://docs.github.com/en/actions/concepts/security/artifact-attestations?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 **Node.js 컨테이너 이미지를 빌드 → provenance attestation 생성 → OIDC로 AWS 배포**까지 한 번에 연결한 “현실형” 파이프라인 예시입니다.

```yaml
name: ci-cd

on:
  pull_request:
  push:
    branches: [ "main" ]
  workflow_dispatch:

# 최소 권한 원칙: 기본은 read, 필요한 job에서만 승격
permissions:
  contents: read

concurrency:
  # 같은 브랜치에서 여러 번 push되면 최신 것만 남기고 이전 실행 취소
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    name: CI (test)
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install
        run: npm ci

      - name: Test
        run: npm test

  build_and_attest:
    name: Build + Attest (main only)
    runs-on: ubuntu-latest
    needs: [ci]
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: read
      id-token: write         # attestation 서명/클라우드 OIDC에 필요 ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))
      attestations: write     # attestation 저장 권한 ([github.com](https://github.com/actions/attest?utm_source=openai))

    outputs:
      image_digest: ${{ steps.build.outputs.digest }}

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        id: build
        run: |
          docker build -t myapp:main .
          # 실제 운영에서는 registry push 후 digest를 쓰는 편이 안전합니다.
          DIGEST="$(docker inspect --format='{{index .RepoDigests 0}}' myapp:main || true)"
          echo "digest=$DIGEST" >> "$GITHUB_OUTPUT"

      # 핵심: 산출물(provenance)을 GitHub Artifact Attestations로 서명
      - name: Attest build provenance
        uses: actions/attest-build-provenance@v1
        with:
          # 여기서는 예시로 로컬 경로를 넣지만,
          # 실무에선 빌드 산출물(zip, 바이너리, 이미지 등)을 대상으로 잡습니다.
          subject-path: "${{ github.workspace }}/Dockerfile"

  deploy:
    name: Deploy (OIDC to AWS)
    runs-on: ubuntu-latest
    needs: [build_and_attest]
    if: github.ref == 'refs/heads/main'
    environment: prod  # environment protection rule(승인/브랜치 제한)과 결합 권장 ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))
    permissions:
      contents: read
      id-token: write   # AWS OIDC 토큰 교환에 필요 ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))

    steps:
      - name: Configure AWS Credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ap-northeast-2

      - name: Deploy (example)
        run: |
          # 예: ECS 서비스 업데이트 / S3 배포 / EKS rollout 등
          aws sts get-caller-identity
          echo "Deploying..."
```

포인트 요약:
- **CI job에는 배포 권한이 없음**(권한 분리)
- **main에서만 build+attest+deploy**
- deploy는 `environment: prod`로 보호 규칙을 얹어 “마지막 안전장치”를 둠 ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))
- OIDC는 `id-token: write`가 핵심 트리거 ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))

---

## ⚡ 실전 팁
1) **OIDC Trust Policy를 “repo:*”로 열어두지 말기**  
AWS 문서에서도 `token.actions.githubusercontent.com:sub` 조건을 평가해 **특정 repo/branch/environment만 Assume**하도록 제한하라고 권장합니다.  
가능하면 `environment: prod` 기반(`repo:ORG/REPO:environment:prod`)으로 제한하면 운영 안전성이 크게 올라갑니다. ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))

2) **permissions는 “workflow 전역 최소 + job에서만 승격” 패턴으로**  
Actions의 사고는 대부분 “불필요하게 넓은 권한”에서 시작합니다. `contents: read`를 기본으로 두고, `id-token: write`, `attestations: write` 같은 권한은 필요한 job에만 부여하세요. ([github.com](https://github.com/actions/attest?utm_source=openai))

3) **Attestation은 ‘자주 도는 CI’에 붙이지 말고, ‘릴리즈 산출물’에만**  
GitHub Docs도 “보안 이점은 검증까지 해야 생긴다” + “테스트용 잦은 빌드에 굳이 서명하지 말라”는 가이드를 줍니다.  
즉, main/tag에서 생성되는 **배포 가능한 artifact**에만 붙이고, CD에서 `gh attestation verify` 같은 검증 단계를 넣는 게 정석입니다. ([docs.github.com](https://docs.github.com/en/actions/concepts/security/artifact-attestations?utm_source=openai))

4) **concurrency로 배포 경쟁 상태 방지**  
같은 브랜치에서 연속 push 시 이전 deploy가 살아있으면 “구버전이 나중에 배포되는” 사고가 납니다. `concurrency + cancel-in-progress`는 CD 품질에 직결되는 장치입니다.

---

## 🚀 마무리
2025년 GitHub Actions 기반 CI/CD의 핵심은 세 가지입니다.

- **OIDC로 장기 credential 제거**(보안) ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))  
- **Artifact Attestations로 provenance를 남겨 ‘검증 가능한 배포’로 확장**(공급망) ([docs.github.com](https://docs.github.com/en/actions/concepts/security/artifact-attestations?utm_source=openai))  
- **permissions / environment / concurrency로 운영 사고를 구조적으로 예방**(안정성) ([docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=openai))  

다음 학습 추천은 두 갈래입니다.
1) 조직 단위로 **Reusable workflows**를 만들어 “검증된 빌드 정의를 중앙화”하기(표준화/감사 대응에 강함)  
2) CD 단계에서 실제로 **attestation verify를 강제**해 “서명된 산출물만 배포” 정책을 완성하기 ([docs.github.com](https://docs.github.com/en/actions/concepts/security/artifact-attestations?utm_source=openai))