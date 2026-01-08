---
title: "2025년형 GitHub Actions CI/CD 파이프라인: “빠르게”가 아니라 “안전하게 자동화”하는 방법"
date: 2026-01-08 02:14:44 +0900
categories: [DevOps, Tutorial]
tags: [devops, tutorial, trend, 2026-01]
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
2025년의 CI/CD는 “빌드/테스트 자동화”를 넘어서 **배포 권한 통제, 공급망 보안, 병렬 실행 제어, 캐시 전략**까지 한 덩어리로 설계해야 합니다. GitHub Actions는 YAML 몇 줄로 시작할 수 있지만, 실제 운영에서는 작은 설정 하나(예: `permissions`, `concurrency`, `cache` 버전) 때문에 **배포 충돌, 토큰 과권한, 캐시 실패로 인한 전면 장애**가 나기도 합니다.

최근 변화 중 특히 실무에 영향이 큰 건 캐시입니다. GitHub Actions 캐시 백엔드가 v2로 전환되며, `@actions/cache` 패키지는 **2025-02-01부터 구버전이 사실상 실패를 유발할 수 있으니 v4+로 업그레이드 권고**가 공지되었습니다. 즉, “예전 YAML 그대로”는 2025년에 더 위험합니다. ([github.com](https://github.com/actions/toolkit/discussions/1890?utm_source=openai))

---

## 🔧 핵심 개념
### 1) 파이프라인을 3층으로 나눠라: CI / CD / Governance
- **CI(검증)**: lint/test/build, artifact 생성. 빠르고 반복 가능해야 함.
- **CD(배포)**: environment 별로 승인/제한/비밀값 접근이 달라짐.
- **Governance(통제)**: 누가 워크플로를 바꿀 수 있는지, 어떤 Action을 허용하는지, 토큰 권한을 어디까지 주는지.

이 3층을 섞어버리면 “CI 수정”이 “프로덕션 배포 권한 변경”으로 이어지는 사고가 발생합니다. GitHub는 이를 방지하려고 `GITHUB_TOKEN` 권한 최소화, 환경 보호 규칙, OIDC 등을 강하게 권장합니다. ([docs.github.com](https://docs.github.com/actions/using-jobs/assigning-permissions-to-jobs?utm_source=openai))

### 2) `GITHUB_TOKEN`과 `permissions`: 기본값에 기대지 말 것
GitHub Actions에서 대부분의 자동화는 `GITHUB_TOKEN`으로 돌아갑니다. 중요한 포인트는:
- Action은 명시적으로 토큰을 넘기지 않아도 `github.token` 컨텍스트로 토큰에 접근 가능
- 그래서 **workflow/job 단위로 `permissions`를 최소 권한으로 고정**하는 게 안전합니다 ([docs.github.com](https://docs.github.com/actions/using-jobs/assigning-permissions-to-jobs?utm_source=openai))

### 3) OIDC로 “장기 Secret”을 제거하라
클라우드 배포에서 가장 흔한 안티패턴은 `AWS_ACCESS_KEY_ID` 같은 장기 키를 `secrets`에 넣는 것입니다. GitHub Actions는 **OIDC(OpenID Connect)** 로 워크플로 실행 시점에만 유효한 토큰을 발급받아 클라우드에 로그인하도록 설계할 수 있습니다. 이를 위해 워크플로에 `permissions: id-token: write`가 필요합니다. ([docs.github.com](https://docs.github.com/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers?utm_source=openai))

### 4) `concurrency`로 “중복 배포”를 구조적으로 차단
main 브랜치에 커밋이 연속으로 들어오면, 이전 배포가 끝나기도 전에 새 배포가 시작되며 환경이 꼬일 수 있습니다. GitHub Actions의 `concurrency`는 같은 그룹의 실행을 **대기/취소**시켜 “마지막 커밋만 배포” 같은 정책을 쉽게 구현합니다. ([docs.github.com](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency?utm_source=openai))

### 5) 캐시는 “성능”이 아니라 “신뢰성” 문제
캐시는 단순 가속 장치가 아니라, 잘못 설계하면 “오염된 결과를 빠르게 재현”하는 장치입니다.
- 키 설계: lockfile hash 기반 + restore-keys로 점진적 폴백
- 보안: 캐시에 민감 정보 저장 금지(특히 PR에서 악용 가능) ([docs.github.com](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows?utm_source=openai))
- 2025 관점: `actions/cache@v4` 사용이 사실상 필수 레벨 ([docs.github.com](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 **Node.js(예: React/Next/Nest 상관없음)** 기준으로, “CI(검증) + CD(배포)”를 한 파일에서 보여주되, 운영에서는 CD를 별 workflow로 분리하거나 reusable workflow로 쪼개는 것을 추천합니다.

```yaml
name: ci-cd

on:
  pull_request:
  push:
    branches: [ "main" ]

# 같은 브랜치/워크플로에서 여러 실행이 겹치면, 최신 실행만 남기고 취소
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

# 기본은 최소 권한. (job별로 추가 권한 부여)
permissions:
  contents: read

jobs:
  ci:
    name: CI (lint/test/build)
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          # setup-node 내장 캐시를 쓰는 방법도 있지만,
          # 여기서는 cache action을 명시해서 키/정책을 통제한다.
          # cache: "npm"

      - name: Cache npm
        uses: actions/cache@v4
        with:
          path: ~/.npm
          # lockfile이 바뀌면 새 캐시 생성 (재현성)
          key: npm-${{ runner.os }}-${{ hashFiles('**/package-lock.json') }}
          restore-keys: |
            npm-${{ runner.os }}-

      - name: Install
        run: npm ci

      - name: Test
        run: npm test --if-present

      - name: Build
        run: npm run build --if-present

  deploy:
    name: CD (deploy to prod)
    needs: [ "ci" ]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    # OIDC로 클라우드 접근하려면 id-token: write 필요
    permissions:
      contents: read
      id-token: write

    # 환경 보호 규칙(승인자/브랜치 제한/대기시간 등)을 여기에 연결
    environment: production

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      # 예시: OIDC 토큰을 직접 "요청"만 해서 존재 확인 (클라우드별 로그인 액션은 각자 다름)
      - name: Prove OIDC token can be issued
        uses: actions/github-script@v7
        with:
          script: |
            const core = require('@actions/core');
            // id-token: write 권한이 있어야 정상 동작
            const token = await core.getIDToken('my-audience');
            core.info(`OIDC token issued (length=${token.length})`);

      - name: Deploy (placeholder)
        run: |
          echo "여기서 AWS/Azure/GCP 공식 로그인 action으로 OIDC 교환 후 배포하세요."
          echo "예: kubectl apply, terraform, serverless deploy 등"
```

이 구성의 핵심은 “기능”이 아니라 **통제 지점**입니다.
- CI는 `contents: read`로 고정
- CD는 `id-token: write`만 추가(장기 secret 제거 방향) ([docs.github.com](https://docs.github.com/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers?utm_source=openai))
- `concurrency`로 main 배포 경합을 구조적으로 제거 ([docs.github.com](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency?utm_source=openai))
- 캐시는 `actions/cache@v4` 기반으로 키를 lockfile에 결박 ([docs.github.com](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows?utm_source=openai))

---

## ⚡ 실전 팁
1) **`permissions`는 “명시”가 정책이다**
- “작동하니까 OK”가 아니라, *어떤 자동화가 어떤 권한으로 움직이는지*가 CI/CD의 품질입니다.
- 특히 PR에서 실행되는 workflow는 더 보수적으로(예: `pull_request`에서 write 권한 금지) 설계하세요. ([docs.github.com](https://docs.github.com/actions/using-jobs/assigning-permissions-to-jobs?utm_source=openai))

2) **배포는 `environment`로 감싸고, 보호 규칙을 적극 활용**
- production 배포는 `environment: production`에 연결하고, GitHub UI에서 승인자(required reviewers)나 브랜치 제한 같은 보호 규칙을 두는 방식이 운영 친화적입니다.
- OIDC 정책 조건에 environment를 엮으면 “특정 환경에서만 토큰 발급” 같은 통제가 가능해집니다. ([docs.github.com](https://docs.github.com/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers?utm_source=openai))

3) **캐시 키는 “정확도 우선”, restore-keys는 “속도 우선”**
- `key`는 lockfile hash로 재현성을 확보하고
- `restore-keys`는 부분 매칭으로 속도를 챙깁니다.
- 그리고 캐시에 credential/토큰/빌드 산출물 중 민감 데이터가 섞이지 않게 경로를 엄격히 제한하세요. ([docs.github.com](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows?utm_source=openai))

4) **2025 캐시 이슈 체크리스트**
- `actions/cache@v4` 사용 여부 확인(조직 내 템플릿/내부 Action 포함)
- 오래된 `@actions/cache` 의존(커스텀 JS Action) 있으면 v4+로 업그레이드 계획 수립 ([github.com](https://github.com/actions/toolkit/discussions/1890?utm_source=openai))

5) **중복 실행 제어는 “비용”이 아니라 “사고 방지”**
- `concurrency`로 main 배포를 직렬화하고 `cancel-in-progress: true`로 “최신만 배포”를 구현하면,
  배포 충돌/리소스 낭비/롤백 난이도가 크게 줄어듭니다. ([docs.github.com](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency?utm_source=openai))

---

## 🚀 마무리
2025년 GitHub Actions로 CI/CD를 “잘” 만든다는 건 YAML을 많이 아는 게 아니라,
- `permissions`로 **최소 권한**
- OIDC로 **장기 secret 제거**
- `concurrency`로 **배포 경합 제거**
- `actions/cache@v4` + 올바른 키 설계로 **속도와 재현성 균형**
을 시스템적으로 설계하는 것입니다. ([docs.github.com](https://docs.github.com/actions/using-jobs/assigning-permissions-to-jobs?utm_source=openai))

다음 학습 추천:
- GitHub Actions OIDC를 실제 클라우드(AWS/Azure/GCP) 로그인 action과 연결해 “무비밀 배포” 완성 ([docs.github.com](https://docs.github.com/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers?utm_source=openai))
- Security hardening 가이드 기반으로 Action pinning/승인 흐름(CODEOWNERS 포함)까지 파이프라인 거버넌스로 확장 ([docs.github.com](https://docs.github.com/enterprise-server%403.15/actions/security-for-github-actions/security-guides/using-githubs-security-features-to-secure-your-use-of-github-actions?utm_source=openai))