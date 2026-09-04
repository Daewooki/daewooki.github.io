---
title: "2025년형 GitHub Actions로 “안전하고 빠른” CI/CD 파이프라인 구축하는 법 (캐시 v2·OIDC·권한 최소화까지)"
date: 2025-12-28 02:29:54 +0900
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
2025년의 CI/CD는 “돌아가기만 하면 된다”를 넘어, **속도(캐시/병렬화)·안정성(동시성 제어)·보안(권한 최소화/비밀 제거)**가 기본 요구사항이 됐습니다. 특히 GitHub Actions는 팀이 가장 손쉽게 선택하는 플랫폼이지만, 아무 설정 없이 워크플로를 늘리다 보면 다음 문제가 금방 터집니다.

- PR이 몰릴 때 불필요한 중복 실행으로 runner 시간/비용 폭증
- long-lived cloud secret 유출 리스크(특히 deploy 키/토큰)
- `GITHUB_TOKEN` 권한 과다로 인한 공급망 공격면 확대
- 캐시/아티팩트 버전 이슈로 파이프라인이 특정 시점부터 갑자기 깨짐

이 글은 **2025년 기준 GitHub Actions의 “최신 권장 방식”**(캐시 서비스 전환, OIDC, 동시성, 권한 설계)을 엮어 **실전형 CI/CD 파이프라인**을 설계/구현하는 방법을 심층적으로 다룹니다. (단순 YAML 나열이 아니라 “왜 이렇게 해야 하는지”까지 설명합니다.)

---

## 🔧 핵심 개념
### 1) CI/CD 파이프라인을 “단계”가 아니라 “권한 경계”로 나누기
전통적으로는 `build -> test -> deploy` 순서만 생각하지만, GitHub Actions에서는 **job 단위가 곧 보안 경계**입니다.  
즉, “배포 job”만 cloud 권한이 필요하고, “CI job”은 코드 읽기 정도만 필요합니다. GitHub Docs는 `permissions`로 `GITHUB_TOKEN` 스코프를 세밀히 제한할 수 있고, 지정하지 않은 권한은 `none`이 된다고 명시합니다. ([docs.github.com](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions?s=09&utm_source=openai))

**정리:** CI job은 최소 권한, CD job은 OIDC + 환경 보호로 강하게 잠그는 구조가 2025년형 정석입니다.

### 2) OIDC(OpenID Connect): “시크릿 없는 배포”의 핵심
GitHub Actions는 OIDC로 클라우드(AWS/Azure/GCP 등)에서 **짧은 수명(short-lived) 토큰**을 발급받아 사용합니다. 이 방식의 본질은:
- GitHub가 workflow/job의 신원을 담은 JWT를 발급
- 클라우드는 사전 구성한 trust policy로 “어떤 repo/branch/environment만 허용”을 검증
- 통과하면 해당 job 동안만 유효한 토큰을 내려줌

즉, **GitHub Secrets에 장기 키를 저장하지 않아도 배포 가능**해지고, 토큰이 자동 만료되어 사고 반경이 줄어듭니다. ([docs.github.com](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect?utm_source=openai))

### 3) concurrency: “배포 충돌”과 “중복 실행”을 시스템적으로 차단
GitHub Actions는 `concurrency`로 동일 그룹의 workflow/job 실행을 1개로 제한할 수 있고, 필요하면 새 실행이 들어올 때 기존 실행을 취소(`cancel-in-progress`)할 수 있습니다. 이 기능은 특히:
- PR에서 push가 연속으로 들어올 때: 이전 CI를 취소하고 최신 커밋만 검증
- staging/prod 배포: 동시에 두 배포가 겹치지 않게 직렬화

공식 문서에 따르면 그룹당 **동시에 1 running + 1 pending**만 유지되며, 새 pending이 생기면 기존 pending은 취소되는 동작도 설명돼 있습니다. ([docs.github.com](https://docs.github.com/en/actions/using-jobs/using-concurrency?utm_source=openai))

### 4) 캐시(actions/cache): 2025년에 더 중요해진 “러너/액션 버전 호환성”
`actions/cache`는 2025년을 기점으로 **캐시 백엔드 서비스가 v2 API로 전환**되고, 특정 버전 미업그레이드 시 워크플로가 실패할 수 있음을 명시하고 있습니다. 또한 self-hosted runner는 최소 runner 버전 요구사항이 붙습니다. ([github.com](https://github.com/actions/cache?utm_source=openai))

**의미:** “캐시를 쓰느냐 마느냐”가 아니라, **캐시 액션 버전과 runner 버전 관리가 파이프라인 안정성의 일부**가 됐습니다.

---

## 💻 실전 코드
아래 예시는 “Node.js 프로젝트”를 가정하지만, 구조 자체는 어떤 스택에도 동일하게 적용됩니다.

- PR/Push: 테스트 + 빌드(CI)
- main에 merge되면: 배포(CD)
- PR은 중복 실행 취소, deploy는 환경 단위로 직렬화
- 최소 권한 + deploy job에서만 `id-token: write`로 OIDC 사용

```yaml
# .github/workflows/ci-cd.yml
name: ci-cd

on:
  pull_request:
  push:
    branches: [ "main" ]

# 워크플로 레벨 동시성: PR/브랜치 단위로 최신 실행만 유지
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true  # PR에서 특히 효과적 (중복 CI 절감)

jobs:
  ci:
    name: CI (test/build)
    runs-on: ubuntu-latest

    # 최소 권한 원칙: CI는 읽기만
    permissions:
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm" # setup-node 캐시(가능하면 기본 제공 캐시 활용)

      # 추가로 캐시를 직접 제어해야 하는 경우 actions/cache 사용
      - name: Cache build outputs
        uses: actions/cache@v4
        with:
          path: |
            .next/cache
            dist
          key: ${{ runner.os }}-build-${{ hashFiles('**/package-lock.json') }}-${{ github.sha }}
          restore-keys: |
            ${{ runner.os }}-build-${{ hashFiles('**/package-lock.json') }}-

      - name: Install
        run: npm ci

      - name: Test
        run: npm test

      - name: Build
        run: npm run build

      # CD로 넘길 산출물(예: dist)을 아티팩트로 저장(배포 job에서 다운로드)
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: build-dist
          path: dist

  deploy:
    name: Deploy (OIDC)
    needs: [ ci ]
    runs-on: ubuntu-latest

    # main 브랜치 push일 때만 배포
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'

    # 배포는 환경 단위로 직렬화(예: prod는 항상 한 번에 하나만)
    concurrency:
      group: deploy-prod
      cancel-in-progress: false  # 배포 중 강제 취소는 위험할 수 있어 보통 false

    # 배포 job만 OIDC 필요 + 읽기 권한만 추가
    permissions:
      contents: read
      id-token: write  # OIDC 토큰 발급을 위해 필요 (핵심)
      # 필요 시 packages: read 등 최소로만 추가

    environment:
      name: prod
      # 환경 보호(승인/브랜치 제한 등)는 GitHub UI에서 설정하는 걸 권장

    steps:
      - name: Download artifact
        uses: actions/download-artifact@v4
        with:
          name: build-dist
          path: dist

      # 예시: AWS로 배포한다면(개념만)
      # - name: Configure AWS credentials (OIDC)
      #   uses: aws-actions/configure-aws-credentials@v4
      #   with:
      #     role-to-assume: arn:aws:iam::123456789012:role/gh-actions-deploy
      #     aws-region: ap-northeast-2

      - name: Deploy
        run: |
          echo "Deploying dist/ ..."
          ls -al dist
          # 여기에 실제 배포 명령(예: S3 sync, kubectl apply, terraform apply 등)
```

핵심 포인트 주석만 보면 “그럴듯한 YAML”로 보이지만, 실제로 중요한 건 다음 두 줄입니다.

- `permissions`를 job별로 쪼개서 **권한 경계**를 만든다. ([docs.github.com](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions?s=09&utm_source=openai))  
- `id-token: write`는 deploy job에만 주고, OIDC로 **장기 secret 없는 배포**로 전환한다. ([docs.github.com](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect?utm_source=openai))

---

## ⚡ 실전 팁
1) **캐시 액션/러너 버전은 “운영 요소”로 관리**
- `actions/cache`는 2025년 캐시 서비스 전환 이슈(백엔드 재작성, 롤아웃/선셋 등)와 runner 최소 버전 요구사항이 명시되어 있습니다. self-hosted를 쓴다면 runner 업그레이드가 늦는 순간 캐시 단계가 파이프라인의 단일 장애점이 됩니다. ([github.com](https://github.com/actions/cache?utm_source=openai))  
- 대응: 캐시 액션 버전 업그레이드를 분기별 체크리스트에 포함하고, self-hosted runner 버전도 함께 관리하세요.

2) **concurrency는 CI 비용 절감 + 배포 안전장치**
- PR에서 `cancel-in-progress: true`는 “어차피 최신 커밋만 의미 있다”는 현실을 반영합니다.
- prod 배포는 반대로 “중간 취소가 더 위험”할 수 있으니 `cancel-in-progress: false`로 직렬화만 하고, 배포 안정성을 택하는 경우가 많습니다. (공식 동작 방식은 문서에 상세히 설명되어 있습니다.) ([docs.github.com](https://docs.github.com/en/actions/using-jobs/using-concurrency?utm_source=openai))

3) **`GITHUB_TOKEN`은 기본적으로 ‘과하게 강력’하다고 가정**
- 문서에서도 액션이 `github.token` 컨텍스트로 토큰에 접근할 수 있음을 강조합니다. 즉, “내가 명시적으로 넘기지 않았으니 안전”이 아닙니다. ([docs.github.com](https://docs.github.com/en/actions/tutorials/use-github_token-in-workflows?utm_source=openai))  
- 대응: workflow/job에 `permissions`를 명시해서 최소 권한을 강제하세요.

4) **조직 차원의 “SHA pinning required”도 고려**
- GitHub REST API에는 repo 수준에서 `sha_pinning_required` 같은 정책을 설정하는 항목이 있습니다. 공급망 공격 방어 관점에서 “조직 정책으로 강제”할 여지가 있다는 뜻입니다. ([docs.github.com](https://docs.github.com/en/rest/actions/permissions?utm_source=openai))  
- 현실 팁: 모든 액션을 곧바로 SHA 고정하면 운영 부담이 커질 수 있으니, 우선 배포/보안 민감 워크플로부터 단계적으로 적용하는 전략이 좋습니다.

---

## 🚀 마무리
2025년형 GitHub Actions CI/CD의 핵심은 “YAML을 잘 짜는 것”이 아니라:

- CI/CD를 **job 권한 경계**로 분리하고(`permissions`)
- 배포는 **OIDC 기반의 short-lived credential**로 바꾸고(`id-token: write`) ([docs.github.com](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect?utm_source=openai))
- `concurrency`로 중복 실행/배포 충돌을 시스템적으로 차단하며 ([docs.github.com](https://docs.github.com/en/actions/using-jobs/using-concurrency?utm_source=openai))
- 캐시/러너 버전 호환성을 “운영”으로 끌어올리는 것 ([github.com](https://github.com/actions/cache?utm_source=openai))

다음 단계로는 (1) reusable workflows로 파이프라인을 표준화하고, (2) environment protection rules로 prod 승인/브랜치 제한을 강화하고, (3) 조직 정책으로 allowed actions/sha pinning을 도입하는 순서로 확장해보면 좋습니다.

원하시면 위 예제를 기준으로 **(A) Docker 이미지 빌드/푸시 + SBOM/attestation**, **(B) Kubernetes/Helm 배포**, **(C) monorepo(matrix) 최적화** 버전으로도 같은 구조를 확장해 드릴게요.