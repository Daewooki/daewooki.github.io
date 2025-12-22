---
title: "2025년형 GitHub Actions로 “진짜” CI/CD 파이프라인 구축하기: Reusable Workflow·OIDC·Concurrency·Artifacts까지"
date: 2025-12-22 02:24:01 +0900
categories: [DevOps, Tutorial]
tags: [devops, tutorial, trend, 2025-12]
---

## 들어가며

2025년의 CI/CD는 “돌아가면 됐다” 수준을 이미 넘어섰습니다. PR마다 자동으로 test/build가 안정적으로 반복되고, main 병합 시에는 **검증된 산출물**이 **안전한 인증 방식(OIDC)** 으로 **배포 환경 보호(approvals)** 를 거쳐 **경합 없이(concurrency)** 릴리즈되는 흐름이 기본 기대치가 됐죠.  
GitHub Actions는 이런 요구를 충족하기 위한 기능들이 성숙해졌지만, 막상 파이프라인을 구축하면 흔히 다음 문제를 만납니다.

- workflow가 커져서 재사용/표준화가 안 됨 → 팀별로 제각각 파편화
- secrets를 오래 저장(Access Key 등) → 보안 리스크
- 동일 브랜치에 push가 연속으로 들어오면 배포가 꼬임 → 레이스 컨디션
- 산출물(artifacts) 업로드/다운로드가 느리거나 동작이 바뀌어 깨짐 → action 버전 이슈

이 글에서는 **“CI(검증) → Build(산출물 생성) → CD(배포)”** 를 GitHub Actions로 설계할 때, 2025년 기준으로 실무에서 가장 효과적인 구성과 원리(왜 이렇게 해야 하는지)를 심층적으로 정리합니다.

---

## 🔧 핵심 개념

### 1) CI/CD를 “Job 나열”이 아니라 “신뢰 경계(Trust Boundary)”로 설계
파이프라인의 본질은 단계가 아니라 **권한과 신뢰를 어디까지 허용할지**입니다.

- CI(Test/Lint): 코드 읽기 권한 + 최소 권한으로 충분
- Build: 의존성 다운로드/빌드 + 산출물 생성(artifact)
- Deploy: 클라우드 리소스 접근 권한 필요 → **OIDC로 단기 토큰 발급**이 정석

여기서 `GITHUB_TOKEN` 권한을 workflow/job 단위로 제어해 **least privilege** 를 적용할 수 있습니다. GitHub는 `permissions` 키로 스코프를 줄일 수 있고, 명시하지 않은 권한은 `none` 처리됩니다. ([github.blog](https://github.blog/changelog/2021-04-20-github-actions-control-permissions-for-github_token/?utm_source=openai))

### 2) OIDC(OpenID Connect)로 “long-lived secret” 제거
배포 단계에서 가장 위험한 건 클라우드 Access Key 같은 **장기 비밀값**입니다. GitHub Actions는 OIDC를 통해 클라우드 제공자와 연동해 **런타임에만 유효한 토큰**으로 인증할 수 있습니다. 즉, 저장된 secret 없이도 배포가 가능해집니다. ([docs.github.com](https://docs.github.com/en/enterprise-server%403.16/actions/reference/security/secure-use?learn=adopting_github_actions_for_your_enterprise_ghes&learnProduct=actions&utm_source=openai))  
구성의 핵심은:

- workflow에 `permissions: id-token: write` 부여
- 클라우드 쪽에 GitHub OIDC trust 설정(issuer/audience/subject 조건 등)
- action에서 OIDC로 credentials 교환

### 3) Concurrency로 “배포 레이스 컨디션” 제거
동일 브랜치/동일 환경으로 배포가 동시에 실행되면 장애가 납니다(서로 덮어쓰기, DB 마이그레이션 충돌 등).  
GitHub Actions의 `concurrency`는 **같은 group에 대해 “동시에 1개만”** 실행되게 하며, `cancel-in-progress`로 새 실행이 들어오면 기존 실행을 취소할 수도 있습니다. ([docs.github.com](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/control-the-concurrency-of-workflows-and-jobs?apiVersion=2022-11-28&utm_source=openai))  
특히 배포는 보통 “마지막 커밋만 의미 있음”이므로 `cancel-in-progress: true`가 실무적으로 유용합니다.

### 4) Artifacts는 v4+로: 속도/불변성/제약 변화 이해
빌드 산출물을 다음 job(배포 job)로 넘길 때 artifacts가 핵심인데, `actions/upload-artifact@v4+`는 아키텍처가 바뀌며 속도와 동작이 크게 개선됐습니다(업로드 성능 개선, artifact-id 즉시 제공, 불변(immutable) 아카이브 등). ([github.com](https://github.com/actions/upload-artifact?utm_source=openai))  
대신 중요한 제약도 생겼습니다.

- **같은 이름으로 여러 번 업로드 불가**(기존처럼 append 개념 없음)
- hidden files 기본 제외(v4.4+)
- self-hosted runner는 방화벽 규칙 등 추가 고려 가능 ([github.com](https://github.com/actions/upload-artifact?utm_source=openai))

이 변화는 “job 간 전달물은 한 번에 만들어, 한 번에 올려라”라는 설계로 유도합니다.

---

## 💻 실전 코드

아래 예시는 **Node.js 웹앱**을 가정해,  
PR에는 CI만 수행하고, `main` push에는 **빌드 산출물 업로드 → OIDC 기반 배포**까지 수행합니다.  
(배포는 예시로 스크립트 호출만 넣었고, 실제 클라우드 커맨드로 교체하면 됩니다.)

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD

on:
  pull_request:
  push:
    branches: [ "main" ]

# 같은 브랜치에 연속 push 시, 최신 실행만 남기고 이전 실행은 취소
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true  # 레이스 컨디션 방지(특히 배포에서 중요) ([docs.github.com](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/control-the-concurrency-of-workflows-and-jobs?apiVersion=2022-11-28&utm_source=openai))

# 기본은 최소 권한. job별로 필요한 권한만 추가하는 방식 권장 ([github.blog](https://github.blog/changelog/2021-04-20-github-actions-control-permissions-for-github_token/?utm_source=openai))
permissions:
  contents: read

jobs:
  ci:
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

  build:
    # PR에서는 build 생략하고, main push에서만 빌드/산출물 생성
    if: github.event_name == 'push'
    needs: [ci]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci
      - run: npm run build

      # 산출물은 "한 번에" 올린다 (v4+는 같은 이름으로 재업로드 불가) ([github.com](https://github.com/actions/upload-artifact?utm_source=openai))
      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: web-dist
          path: dist/
          retention-days: 7

  deploy:
    if: github.event_name == 'push'
    needs: [build]
    runs-on: ubuntu-latest

    # 배포는 환경 보호 규칙(승인 등)을 붙이기 쉬우므로 environment 사용을 권장(실무 표준)
    environment: production

    # OIDC를 쓰려면 id-token: write 필요 ([docs.github.com](https://docs.github.com/en/enterprise-server%403.16/actions/reference/security/secure-use?learn=adopting_github_actions_for_your_enterprise_ghes&learnProduct=actions&utm_source=openai))
    permissions:
      contents: read
      id-token: write

    steps:
      - name: Download build artifact
        uses: actions/download-artifact@v4
        with:
          name: web-dist
          path: dist

      # 여기서부터는 클라우드별 OIDC 구성에 맞게 교체
      - name: Deploy (example)
        run: |
          echo "Deploying dist/ ..."
          ls -al dist
          # 예: aws s3 sync dist s3://...
          # 예: az storage blob upload-batch ...
          # 예: gcloud storage rsync ...
```

---

## ⚡ 실전 팁

1) **권한 최소화는 “기본 none + 필요한 것만”이 가장 안전**
- workflow 상단에 `permissions: contents: read` 정도만 주고,
- 배포 job에만 `id-token: write` 같은 민감 권한을 부여하세요.  
이 방식이 least privilege 구현에 가장 실용적입니다. ([github.blog](https://github.blog/changelog/2021-04-20-github-actions-control-permissions-for-github_token/?utm_source=openai))

2) **Artifacts(v4+)는 ‘불변(immutable)’이라는 점을 전제로 설계**
- “job A에서 올리고 job B가 받는 전달물”로 딱 맞습니다.
- 반대로 “여러 job이 같은 이름에 누적 업로드” 같은 패턴은 v4에서 깨집니다. ([github.com](https://github.com/actions/upload-artifact?utm_source=openai))  
대안은:
- job별로 artifact 이름을 다르게 하거나
- 마지막에 merge 전략을 쓰거나(액션 제공 여부는 리포지토리 문서 기준 확인)

3) **배포에는 concurrency를 환경 단위로도 걸어라**
- 브랜치 기준(`github.ref`)만으로는 “hotfix 브랜치 → prod 배포” 같은 시나리오에서 경합이 날 수 있습니다.
- 실무에서는 `concurrency.group: deploy-production`처럼 **환경을 키로 고정**하는 패턴이 강력합니다. ([docs.github.com](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/control-the-concurrency-of-workflows-and-jobs?apiVersion=2022-11-28&utm_source=openai))

4) **OIDC는 ‘설정만 하면 끝’이 아니라 ‘조건(Claims) 설계’가 핵심**
- 클라우드 쪽 trust policy에서 `repo`, `ref`, `environment`(가능한 경우) 같은 조건을 걸어
  “특정 repo의 main에서만 prod 배포 토큰 발급”이 되게 만드세요.
- 이렇게 해야 “다른 브랜치/포크에서 토큰 발급” 같은 사고를 구조적으로 차단합니다. (OIDC 사용 자체의 보안 이점은 GitHub 문서에서도 강조됩니다.) ([docs.github.com](https://docs.github.com/en/enterprise-server%403.16/actions/reference/security/secure-use?learn=adopting_github_actions_for_your_enterprise_ghes&learnProduct=actions&utm_source=openai))

5) **workflow 파일 변경은 CODEOWNERS로 보호**
- `.github/workflows/**` 변경은 사실상 “배포 권한 변경”입니다.
- CODEOWNERS로 승인자를 강제하는 습관이 파이프라인 보안의 가성비가 좋습니다. ([docs.github.com](https://docs.github.com/en/enterprise-server%403.16/actions/reference/security/secure-use?learn=adopting_github_actions_for_your_enterprise_ghes&learnProduct=actions&utm_source=openai))

---

## 🚀 마무리

2025년형 GitHub Actions CI/CD의 핵심은 “yaml을 예쁘게 짜는 것”이 아니라:

- **권한(permissions) 최소화**로 신뢰 경계를 분리하고 ([github.blog](https://github.blog/changelog/2021-04-20-github-actions-control-permissions-for-github_token/?utm_source=openai))  
- **OIDC**로 장기 secret을 제거하며 ([docs.github.com](https://docs.github.com/en/enterprise-server%403.16/actions/reference/security/secure-use?learn=adopting_github_actions_for_your_enterprise_ghes&learnProduct=actions&utm_source=openai))  
- **concurrency**로 배포 경합을 구조적으로 차단하고 ([docs.github.com](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/control-the-concurrency-of-workflows-and-jobs?apiVersion=2022-11-28&utm_source=openai))  
- **artifacts(v4+)의 불변/제약**을 이해한 전달물 중심 파이프라인을 만드는 것 ([github.com](https://github.com/actions/upload-artifact?utm_source=openai))  

다음 학습으로는:
- Reusable workflow(`workflow_call`)로 CI/CD 표준화를 조직 단위로 확장
- Environment protection rules(승인/대기/정책)와 함께 배포 거버넌스 강화
- self-hosted runner를 쓸 경우 runner 업데이트/네트워크 요건(artifact v4 관련) 점검 ([github.com](https://github.com/actions/upload-artifact?utm_source=openai))  

원하시면, 사용 중인 스택(Node/Spring/Docker/Kubernetes/Terraform 등)과 배포 대상(AWS/GCP/Azure/Vercel 등)을 알려주시면 위 템플릿을 기반으로 **실제 클라우드 OIDC 설정까지 포함한 “바로 붙여넣어 동작하는” 파이프라인**으로 구체화해드릴게요.