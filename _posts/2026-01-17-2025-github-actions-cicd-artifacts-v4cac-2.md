---
title: "GitHub Actions로 “안전하고 빠른” CI/CD 파이프라인 만들기: Artifacts v4·Cache v5·OIDC까지 한 번에"
description: "2025년의 GitHub Actions CI/CD는 “YAML 좀 잘 쓰면 된다” 수준을 넘었습니다. 실제 운영에서는 속도(캐시/병렬화), 재현성(artifact/lockfile), 보안(최소 권한·OIDC·Environment gate) 이 셋이 동시에 맞아야 파이프라인이 오래 갑니다…"
date: 2026-01-17 00:11:10 +0900
categories: [DevOps, Tutorial]
tags: [devops, tutorial]
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
2025년의 GitHub Actions CI/CD는 “YAML 좀 잘 쓰면 된다” 수준을 넘었습니다. 실제 운영에서는 **속도(캐시/병렬화)**, **재현성(artifact/lockfile)**, **보안(최소 권한·OIDC·Environment gate)** 이 셋이 동시에 맞아야 파이프라인이 오래 갑니다. 특히 2025년 초 기준으로는 **artifact 액션 v3가 2025-01-30부터 GitHub.com에서 사용 불가**가 되어, 예전 워크플로를 그대로 두면 배포 파이프라인이 갑자기 깨질 수 있습니다.[^1]  
그래서 이 글은 “2025년에 깨지지 않고, 운영 친화적으로 확장 가능한” GitHub Actions CI/CD를 **원리부터 구현까지** 묶어서 정리합니다.

---

## 🔧 핵심 개념
### 1) CI/CD를 ‘Job 그래프’로 설계한다
GitHub Actions는 결국 **Job DAG(의존 그래프)** 입니다. 빌드→테스트→패키징→배포를 직렬로만 두면 단순하지만 느리고, 반대로 무작정 병렬화하면 artifact 충돌/캐시 오염/승인 게이트 누락이 생깁니다.  
2025년형 설계 포인트는:
- **CI(Job)**: 빠른 피드백(테스트/정적분석) + 재현성(고정된 런타임/lockfile)
- **CD(Job)**: “승인/권한/비밀”이 붙는 구간은 **Environment**로 분리

### 2) Artifacts v4: 즉시 사용 가능하지만 “불변(immutable) + 이름 중복 불가”
Artifacts v4는 업로드 성능이 크게 개선되고, 업로드 후 **즉시 UI/API에서 사용 가능**해졌습니다.[^2]  
대신 운영에서 중요한 제약이 생깁니다:
- v4는 **불변(immutable)** 이라 같은 이름으로 여러 번 업로드가 불가(특히 matrix에서 충돌)[^3]  
- 업로드/다운로드는 **v4끼리만 호환**(v3 artifact를 v4로 다운로드 불가)[^4]  
- 숨김파일은 기본 제외(민감정보 유출 방지). 필요 시 옵션으로 포함 가능[^5]  

즉, “빌드 산출물 공유”는 여전히 artifact가 정답이지만, **matrix면 이름을 유니크하게** 만들고, 필요하면 download-artifact의 패턴/merge 개념으로 모으는 방식이 안전합니다.[^4]  

### 3) Cache: 의존성은 캐시하되, 러너/버전 변화에 주의
`actions/cache`는 2025-02-01 전후로 **새 캐시 서비스(v2 API)로 전환**되며, 권장 버전(v3/v4) 업그레이드를 강하게 요구했습니다.[^6]  
또한 최근 액션들은 Node.js 24 런타임을 쓰며 **self-hosted runner 최소 버전 요구**가 생기므로(예: upload-artifact v6, cache v5), 사내 러너면 업그레이드 정책이 파이프라인 안정성에 직결됩니다.[^6]  

### 4) 보안의 핵심: 최소 권한 + OIDC + Environment gate
- **OIDC**를 쓰면 클라우드 액세스 키(장기 secret)를 저장하지 않고, 실행 시점에 짧은 토큰으로 교환합니다. 이를 위해 워크플로에 `permissions: id-token: write`가 필요합니다.[^7]  
- 배포 Job은 `environment:`를 걸고, GitHub UI에서 **Required reviewers / wait timer** 같은 보호 규칙을 설정해 “사람 승인” 또는 “지연 배포”를 강제할 수 있습니다.[^8]  

---

## 💻 실전 코드
아래 예시는 **Node.js(예: Next.js/Express/TS)** 기준이지만, 구조는 어떤 스택에도 그대로 적용됩니다.

```yaml
# .github/workflows/ci-cd.yml
name: ci-cd

on:
  pull_request:
  push:
    branches: [ "main" ]

# 기본은 최소 권한. 필요한 Job만 권한을 올린다.
permissions:
  contents: read

concurrency:
  # 같은 브랜치에 대해 중복 실행은 최신만 남기고 취소(배포 경쟁/캐시오염 방지)
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      # Node 런타임 고정 + 의존성 캐시
      - name: Setup Node
        uses: actions/setup-node@v6
        with:
          node-version: 24
          cache: npm

      - name: Install
        run: npm ci

      - name: Unit Test
        run: npm test

  build:
    needs: [test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Setup Node
        uses: actions/setup-node@v6
        with:
          node-version: 24
          cache: npm

      - name: Install
        run: npm ci

      - name: Build
        run: npm run build

      # 2025년 기준: artifact는 v4 이상 권장/사실상 필수(구 v3는 GitHub.com에서 2025-01-30부터 사용 불가)
      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: web-dist-${{ github.sha }}   # v4는 같은 이름 중복 업로드 불가 → SHA로 유니크하게
          path: |
            dist/
            .next/standalone/
          if-no-files-found: error
          retention-days: 7

  deploy-prod:
    # main 브랜치 푸시에만 배포
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    needs: [build]
    runs-on: ubuntu-latest

    # Environment를 걸면, 이 Job은 해당 Environment 보호 규칙(Required reviewers 등)을 통과해야 실행됨
    environment:
      name: production
      url: https://example.com

    # OIDC를 쓰는 Job만 id-token 권한을 올린다(최소 권한 원칙)
    permissions:
      contents: read
      id-token: write

    steps:
      - name: Download build artifact
        uses: actions/download-artifact@v4
        with:
          name: web-dist-${{ github.sha }}
          path: ./artifact

      # 예: AWS에 OIDC로 로그인(장기 Secret 없이)
      # - name: Configure AWS credentials (OIDC)
      #   uses: aws-actions/configure-aws-credentials@v4
      #   with:
      #     role-to-assume: arn:aws:iam::<account-id>:role/<role-name>
      #     aws-region: ap-northeast-2

      - name: Deploy
        run: |
          ls -al ./artifact
          # 여기에 실제 배포 스크립트(SSH, S3 sync, k8s apply, Helm 등)를 배치
```

---

## ⚡ 실전 팁
1) **Artifact v4 마이그레이션 체크리스트**
- 같은 이름으로 여러 번 업로드하던 패턴(matrix 빌드 등)은 반드시 깨집니다 → `name: artifact-${{ matrix.os }}-${{ github.sha }}`처럼 유니크하게.[^3]  
- 숨김파일이 기본 제외이므로(예: `.env`, `.npmrc`) “왜 빠졌지?”가 자주 발생합니다. 민감정보는 원칙적으로 artifact에 넣지 말고, 정말 필요하면 `include-hidden-files`를 의도적으로 켜세요.[^5]  

2) **캐시는 ‘성능 기능’이지 ‘정답 데이터 저장소’가 아니다**
- 캐시 키는 lockfile 해시 기반으로 설계하고, 빌드 산출물은 artifact로 분리하세요(캐시는 언제든 무효화/미스 가능).  
- self-hosted runner를 쓴다면 cache/artifact 액션의 런타임(Node24) 요구와 runner 최소 버전을 먼저 맞추는 게 장애 예방의 핵심입니다.[^6]  

3) **OIDC + Environment를 같이 써야 “배포 보안”이 완성된다**
- OIDC는 `id-token: write`가 필요하며, 이 권한은 “OIDC 토큰 요청”만 가능하게 해주는 것이지 repo write 권한이 아닙니다.[^7]  
- production 배포는 `environment: production`으로 분리하고 Required reviewers/Prevent self-review를 켜서 “혼자 트리거하고 혼자 승인”을 막는 게 운영에서 효과가 큽니다.[^9]  

4) **재사용 가능한 표준 파이프라인은 reusable workflows로 굳혀라**
여러 서비스/모노레포에서 동일한 CI/CD 규칙을 강제하려면 `workflow_call` 기반 reusable workflows가 가장 유지보수 비용이 낮습니다(입력/secret 전달 포함).[^10]  

---

## 🚀 마무리
2025년 GitHub Actions CI/CD의 핵심은 “YAML을 잘 짠다”가 아니라,  
- **Artifacts v4의 불변성과 제약을 이해하고**,[^4]  
- **Cache/Runner 업그레이드 이슈를 운영 관점에서 흡수**하며,[^6]  
- **OIDC + Environment gate로 배포 권한을 설계**하는 것입니다.[^7]  

다음 학습으로는 (1) reusable workflows로 조직 표준 CI/CD 템플릿 만들기, (2) Environment 보호 규칙(승인/대기/브랜치 제한) 운영 정책화, (3) OIDC claim 설계(issuer/audience/subject 제한)까지 확장해보면 “보안과 자동화의 균형”이 한 단계 올라갑니다.[^11]

[^1]: <https://github.blog/changelog/2024-04-16-deprecation-notice-v3-of-the-artifact-actions>
[^2]: <https://github.blog/news-insights/product-news/get-started-with-v4-of-github-actions-artifacts/>
[^3]: <https://github.com/actions/upload-artifact>
[^4]: <https://github.blog/changelog/2023-12-14-github-actions-artifacts-v4-is-now-generally-available>
[^5]: <https://github.blog/changelog/2024-08-19-notice-of-upcoming-deprecations-and-breaking-changes-in-github-actions-runners>
[^6]: <https://github.com/actions/cache>
[^7]: <https://docs.github.com/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers>
[^8]: <https://docs.github.com/en/actions/reference/environments>
[^9]: <https://docs.github.com/en/enterprise-cloud%40latest/actions/reference/workflows-and-actions/deployments-and-environments>
[^10]: <https://docs.github.com/en/enterprise-cloud%40latest/actions/using-workflows/reusing-workflows>
[^11]: <https://docs.github.com/en/enterprise-cloud%40latest/actions/reference/openid-connect-reference>
