---
title: "2025년형 GitHub Actions로 “안전하고 빠른” CI/CD 파이프라인 구축하는 법 (재사용·캐시·OIDC·배포보호까지)"
date: 2025-12-25 02:11:32 +0900
categories: [DevOps, Tutorial]
tags: [devops, tutorial, trend, 2025-12]
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
팀 규모가 커질수록 CI/CD는 “자동화” 자체보다 **일관성, 속도, 보안, 배포 통제**가 핵심이 됩니다. 2025년의 GitHub Actions는 단순히 `push` 때 테스트 돌리는 수준을 넘어, **least privilege 권한 관리**, **OIDC 기반의 무비밀(또는 최소 비밀) 배포 인증**, **environments 기반 승인/보호**, **concurrency로 배포 충돌 방지**, 그리고 **캐시 백엔드 변화(업그레이드 필수)**까지 고려해야 “운영 가능한 파이프라인”이 됩니다.  
특히 GitHub의 공식 가이드가 강조하듯 `GITHUB_TOKEN` 권한을 최소화하고, 가능한 경우 cloud credential을 long-lived secret 대신 OIDC로 대체하는 접근이 표준으로 굳어졌습니다. ([docs.github.com](https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-guides/security-hardening-for-github-actions?learn=getting_started&learnProduct=actions&utm_source=openai))

---

## 🔧 핵심 개념
### 1) CI/CD 파이프라인을 “Stage”로 쪼개는 이유
실무 파이프라인은 보통 **CI(검증)** 와 **CD(배포)** 를 분리합니다.

- **CI**: lint/test/build/scan → 빠른 피드백, PR 품질 보장
- **CD**: artifact 재사용 + 승인/보호 + 안전한 인증 → 운영 리스크 최소화

이때 중요한 건 “각 Stage가 어떤 신뢰 경계(trust boundary)를 가지는가”입니다. 예: PR에서 실행되는 CI는 외부 입력(코드)을 받기 때문에 권한이 매우 제한돼야 하고, 배포 단계는 승인·환경 보호·자격증명 범위 제한이 필요합니다.

### 2) permissions: {} 와 least privilege
GitHub Actions 보안 하드닝 문서의 큰 줄기는 간단합니다:  
**기본 권한을 최소화하고, 필요한 Job에서만 권한을 올려라.** ([docs.github.com](https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-guides/security-hardening-for-github-actions?learn=getting_started&learnProduct=actions&utm_source=openai))  
특히 `permissions: {}`를 workflow 레벨에 두면 “아무 권한도 없는 상태”에서 시작해 Job별로 필요한 권한만 부여하는 습관을 만들 수 있습니다(서드파티 분석 글에서도 이 패턴을 강하게 권장). ([wiz.io](https://www.wiz.io/blog/github-actions-security-guide?utm_source=openai))

### 3) OIDC로 배포 자격증명(Secret) 줄이기
GitHub Actions는 OIDC 토큰(JWT)을 발급할 수 있고, cloud provider는 이 토큰의 `sub`, `aud` 같은 claim 조건을 기반으로 “어떤 repo/branch/environment에서 왔는지”를 검증해 role을 부여합니다. ([docs.github.com](https://docs.github.com/en/actions/reference/openid-connect-reference?utm_source=openai))  
핵심은 다음 두 가지입니다.

- 워크플로/잡에 `id-token: write` 권한이 있어야 OIDC 토큰 요청 가능 ([docs.github.com](https://docs.github.com/en/actions/reference/openid-connect-reference?utm_source=openai))
- cloud role의 trust policy는 `sub`를 **branch 또는 environment 단위**로 제한하는 것이 안전 ([docs.github.com](https://docs.github.com/en/actions/reference/openid-connect-reference?utm_source=openai))

### 4) concurrency로 “배포 충돌”을 시스템적으로 차단
배포는 병렬로 돌면 사고가 납니다(롤백 레이스, 마이그레이션 충돌 등).  
`concurrency`는 동일 그룹에 대해 **동시에 1개만 실행**되도록 제어하고, 필요 시 `cancel-in-progress`로 이전 실행을 취소할 수 있습니다. ([docs.github.com](https://docs.github.com/en/actions/using-jobs/using-concurrency?utm_source=openai))  
중요한 함정: 같은 그룹에서는 “running 1개 + pending 1개”만 유지되며, 새 pending이 오면 기존 pending이 취소되는 동작이 기본입니다(큐처럼 무한 적재가 아님). ([docs.github.com](https://docs.github.com/en/actions/using-jobs/using-concurrency?utm_source=openai))

### 5) 캐시: 2025년에는 “업그레이드”가 안정성 이슈
GitHub Actions 캐시 백엔드가 재작성되며, `@actions/cache`는 4.0.0 이상으로 업그레이드 권고(미업그레이드 시 실패 가능) 공지가 있었습니다. ([github.com](https://github.com/actions/toolkit/discussions/1890?utm_source=openai))  
직접 `actions/cache`를 쓰든, `setup-*` 계열 액션이 내부적으로 캐시를 쓰든 “버전 최신화”는 파이프라인 유지보수의 일부가 됐습니다.

---

## 💻 실전 코드
아래 예시는 **Node.js(예: pnpm) 기준**으로 “CI + CD(환경 보호 + OIDC + concurrency)”를 한 파일에 담은 형태입니다.  
포인트: *최소 권한*, *artifact로 CI 결과 재사용*, *environment로 승인/보호*, *OIDC로 배포 인증*, *concurrency로 배포 충돌 방지*.

```yaml
# .github/workflows/cicd.yml
name: CI-CD

on:
  pull_request:
  push:
    branches: [ "main" ]
  workflow_dispatch:

# 1) 기본은 무권한(least privilege). Job에서 필요한 것만 올립니다.
permissions: {}

# 2) main 배포는 동시에 1개만(배포 충돌 방지). 새 배포가 오면 이전 배포를 취소.
concurrency:
  group: deploy-prod-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    name: CI (test/build)
    runs-on: ubuntu-latest

    # CI는 코드 읽기만 필요
    permissions:
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Install
        run: |
          corepack enable
          pnpm install --frozen-lockfile

      - name: Test
        run: pnpm test

      - name: Build
        run: pnpm build

      # CI 결과물을 artifact로 넘겨 CD에서 재사용(재빌드/재테스트 비용 절감)
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  deploy:
    name: CD (deploy to Production)
    runs-on: ubuntu-latest
    needs: [ ci ]

    # GitHub Environments에서 Production을 만들고,
    # required reviewers / deployment protection rules 등을 걸어 “승인 후 배포”로 운영
    environment: Production

    # OIDC 토큰 요청 + repo 읽기 정도만
    permissions:
      contents: read
      id-token: write

    # main에서만 배포
    if: github.ref == 'refs/heads/main'

    steps:
      - name: Download artifact
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/

      # 여기서 cloud provider login action(AWS/Azure/GCP 등)을 OIDC로 구성
      # 핵심은 secrets 대신 OIDC + trust policy(sub/aud 제한)로 교체하는 것
      - name: Deploy (example)
        env:
          DEPLOY_ENV: prod
        run: |
          echo "Deploying ./dist to $DEPLOY_ENV"
          # 예: aws s3 sync dist/ s3://my-bucket/ --delete
          # 예: az storage blob upload-batch ...
          # 예: gcloud storage rsync ...
```

---

## ⚡ 실전 팁
1) **배포 Job은 environment로 감싸고, 승인/보호를 GitHub UI에서 강제**
- 문서에서도 environment secrets에 대해 “required reviewers로 접근 승인”을 권장합니다. ([docs.github.com](https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-guides/security-hardening-for-github-actions?learn=getting_started&learnProduct=actions&utm_source=openai))  
- 코드로 해결하려 하지 말고(조건문 난립), *조직 정책*으로 고정하는 게 운영에 강합니다.

2) **OIDC trust policy는 “branch”보다 “environment” 기반이 더 안전한 경우가 많다**
- OIDC `sub`는 job이 참조하는 environment 이름을 포함해 제한할 수 있습니다. 즉 “Production environment에서 실행된 deploy job만” 토큰 발급을 허용하는 형태가 가능합니다. ([docs.github.com](https://docs.github.com/en/actions/reference/openid-connect-reference?utm_source=openai))  
- 실무에서는 `main` 브랜치 보호 + environment 승인 + OIDC 조건을 조합하면 공격면이 크게 줄어듭니다.

3) **concurrency는 ‘큐’가 아니라 ‘1 running + 1 pending’ 모델이라는 점을 전제로 설계**
- “배포를 순서대로 다 실행”을 기대하면 설계가 어긋납니다. 같은 그룹에서는 새 실행이 오면 기존 pending이 취소될 수 있습니다. ([docs.github.com](https://docs.github.com/en/actions/using-jobs/using-concurrency?utm_source=openai))  
- 보통 배포는 “최신 커밋만 배포”가 목적이므로, 이 동작이 오히려 원하는 정책인 경우가 많습니다.

4) **캐시/액션 버전은 ‘기능’이 아니라 ‘가동률’ 이슈**
- 캐시 백엔드 변경으로 `@actions/cache` 4.x 업그레이드 권고가 나왔고, 미업그레이드 시 실패 가능성이 언급됐습니다. ([github.com](https://github.com/actions/toolkit/discussions/1890?utm_source=openai))  
- 워크플로에서 `uses: ...@v4`처럼 **메이저 버전 고정 + 주기적 점검**을 표준 운영 항목으로 두세요.

---

## 🚀 마무리
2025년 GitHub Actions 기반 CI/CD의 핵심은 “YAML 잘 짜기”가 아니라, **권한(permissions)·인증(OIDC)·통제(environment)·충돌방지(concurrency)·유지보수(캐시/액션 버전)**를 한 덩어리로 설계하는 것입니다.  
다음 단계로는 (1) reusable workflows로 배포 로직을 표준화하고, (2) OIDC claim 커스터마이징/조건 강화를 통해 “승인된 workflow만 배포 가능” 수준으로 올리는 것을 추천합니다. ([docs.github.com](https://docs.github.com/en/actions/reference/openid-connect-reference?utm_source=openai))