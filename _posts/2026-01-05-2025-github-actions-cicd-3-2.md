---
title: "GitHub Actions CI/CD 파이프라인: “재사용·보안·속도” 3가지만 제대로 잡으면 끝납니다"
description: "2025년의 CI/CD는 “YAML을 어떻게 쓰느냐”보다 어떻게 구조화하고(재사용), 어떻게 안전하게(권한/비밀), 어떻게 빠르게(캐시/아티팩트) 굴리느냐가 성패를 가릅니다."
date: 2026-01-05 02:31:19 +0900
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
2025년의 CI/CD는 “YAML을 어떻게 쓰느냐”보다 **어떻게 구조화하고(재사용), 어떻게 안전하게(권한/비밀), 어떻게 빠르게(캐시/아티팩트)** 굴리느냐가 성패를 가릅니다. GitHub Actions는 이미 충분히 강력하지만, 팀/서비스가 늘어날수록 워크플로가 비대해지고(중복), Secret 관리가 위험해지고(장기 키), 빌드 시간이 급격히 늘어납니다(캐시 미흡).  
따라서 2025년형 파이프라인은 다음 전략이 핵심입니다.

- **Reusable workflows**로 파이프라인을 “플랫폼 레벨 표준”으로 모듈화[^1]  
- 배포 인증은 **OIDC 기반 단기 자격증명**으로 전환해 Secret 의존을 줄이기[^2]  
- **Cache + Artifact v4+**로 속도/재현성을 동시에 잡기(단, v4의 동작 변화에 적응)[^3]  

---

## 🔧 핵심 개념
### 1) 파이프라인을 “조립식”으로 만드는 Reusable Workflows
Reusable workflow는 한 줄(`uses:`)로 다른 워크플로를 호출해 **중복을 제거**하고, 조직 표준(테스트/보안 스캔/빌드 규칙)을 중앙에서 관리하게 해줍니다. 호출된 워크플로는 호출자(caller) 컨텍스트에서 실행되며, 기본적으로 `GITHUB_TOKEN`을 전달받습니다.[^1]  
주의할 점은 **호출 깊이/호출 수 제한**이 존재한다는 것입니다(과도한 계층화는 실패 요인).[^1]

### 2) “배포 자격증명”의 정답: OIDC + 최소 권한
클라우드 배포에서 가장 큰 사고 지점은 장기 Access Key를 Secret에 넣고 돌리는 방식입니다. GitHub Actions는 OIDC 토큰을 발급하고, 이를 통해 AWS 같은 외부 시스템에서 **단기 토큰으로 Role Assume**이 가능합니다. 워크플로에는 `permissions: id-token: write`가 필요하며, AWS Trust Policy는 `sub` 조건으로 repo/branch/environment를 제한해 최소권한을 구현합니다.[^2]

### 3) 캐시(Cache)와 아티팩트(Artifact)는 목적이 다르다
- **Cache**: 의존성/빌드 결과를 재사용해 “속도”를 얻음. 키 매칭 규칙(정확 일치 → 부분 일치 → restore-keys)을 이해해야 캐시 히트율이 올라갑니다.[^3]  
- **Artifact**: 빌드 산출물을 “전달/보관”해 배포 단계와 분리함. 특히 `upload-artifact@v4`는 백엔드가 바뀌며 **immutable archive**(업로드 후 변경 불가)로 동작하고, **동일 이름 아티팩트 중복 업로드가 기본적으로 불가**해 파이프라인 설계에 영향을 줍니다.[^4]

---

## 💻 실전 코드
아래 예시는 “CI(테스트/빌드) → Artifact 전달 → CD(승인된 환경에 배포, OIDC)”의 전형적인 2025년형 구조입니다.

```yaml
# .github/workflows/ci-cd.yml
name: ci-cd

on:
  pull_request:
  push:
    branches: [ "main" ]

# 기본은 최소 권한. 배포 Job에서만 id-token을 추가로 엽니다.
permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    name: Build & Test (CI)
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      # Cache: "속도"를 위한 계층 키 설계 (lockfile 변경에 반응)
      - name: Restore npm cache
        uses: actions/cache@v4
        with:
          path: |
            ~/.npm
            node_modules
          key: npm-${{ runner.os }}-${{ hashFiles('package-lock.json') }}
          restore-keys: |
            npm-${{ runner.os }}-

      - name: Install
        run: npm ci

      - name: Test
        run: npm test

      - name: Build
        run: npm run build

      # Artifact v4+: immutable + 기본적으로 동일 name 중복 업로드 불가
      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: web-dist-${{ github.sha }}   # 이름을 SHA로 유니크하게
          path: dist/
          retention-days: 14

  deploy_prod:
    name: Deploy (CD, prod)
    needs: [ci]
    runs-on: ubuntu-latest

    # Environment를 쓰면 승인/보호 규칙(수동 승인, 배포 보호 등)과 연결 가능
    environment: prod

    # OIDC를 쓰기 위해 id-token 권한을 명시적으로 열기
    permissions:
      contents: read
      id-token: write

    steps:
      - name: Download artifact
        uses: actions/download-artifact@v4
        with:
          name: web-dist-${{ github.sha }}
          path: dist/

      # AWS 예시: 장기키 없이 OIDC로 Role Assume
      - name: Configure AWS Credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v5
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }} # repo/env vars로 관리
          aws-region: ap-northeast-2

      - name: Deploy to S3 (example)
        run: aws s3 sync dist/ s3://${{ vars.S3_BUCKET }}/ --delete
```

---

## ⚡ 실전 팁
1) **권한은 “기본 차단 후 필요한 Job만 오픈”**  
`permissions`를 워크플로 최상단에서 최소로 두고, 배포 Job에서만 `id-token: write`를 열어 OIDC를 사용하세요. OIDC 자체는 외부 리소스에 쓰기 권한을 주는 게 아니라 “토큰 요청 권한”이므로, 실제 권한은 클라우드 Role 정책에서 통제합니다.[^2]

2) **OIDC Trust Policy는 sub 조건으로 좁혀라**  
AWS 기준으로 `token.actions.githubusercontent.com:sub`를 repo/branch 또는 environment 단위로 제한하지 않으면, 의도치 않은 주체가 Role을 Assume할 여지가 생깁니다.[^2]

3) **Cache는 ‘맞추는 게임’이 아니라 ‘키 설계’다**  
캐시는 정확히 일치하는 key가 최우선이며, 없으면 부분/restore-keys로 내려갑니다. 키를 너무 세분화하면 항상 miss, 너무 뭉치면 오염된 캐시를 먹습니다. lockfile 해시 + OS 정도가 대체로 균형점입니다.[^3]  
또한 캐시 경로에는 토큰/인증정보를 넣지 마세요(PR로 캐시 접근 리스크).[^3]

4) **Artifact v4는 “한 번 올리면 끝”이라는 전제로 설계**  
`upload-artifact@v4`는 immutable이고, 같은 name을 여러 번 업로드하면 실패할 수 있습니다(기본 동작). 빌드 산출물은 **Job당 1회 업로드**로 정리하거나, 이름을 SHA/매트릭스 축으로 유니크하게 구성하세요.[^4]

5) **Reusable workflow는 과도한 계층화보다 ‘얇게, 여러 개’가 유지보수에 유리**  
공통 단계를 재사용으로 빼되, 깊이 제한/호출 수 제한을 의식해 “표준 게이트(보안/테스트) + 언어별 셀 + 배포 셀” 정도의 모듈 경계를 추천합니다.[^1]

---

## 🚀 마무리
2025년 GitHub Actions 파이프라인의 핵심은 “YAML 트릭”이 아니라 **아키텍처**입니다.

- CI는 **Cache로 빠르게**, 결과는 **Artifact로 고정(immutable)**[^3]  
- CD는 **Environment 보호 + OIDC 단기 자격증명 + 최소 권한**[^2]  
- 팀/서비스 확장에는 **Reusable workflows로 표준화**[^1]  

다음 단계로는 (1) org 단위 reusable workflow 라이브러리 설계, (2) 환경(prod/stg) 보호 규칙과 배포 게이트 정교화, (3) self-hosted runner 운영(보안/업데이트/스케일)을 학습하면 “진짜 CI/CD 플랫폼”까지 자연스럽게 확장할 수 있습니다.

[^1]: <https://docs.github.com/actions/using-workflows/reusing-workflows>
[^2]: <https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services>
[^3]: <https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows>
[^4]: <https://github.com/actions/upload-artifact>
