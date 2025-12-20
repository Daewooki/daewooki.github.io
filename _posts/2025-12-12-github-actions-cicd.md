---
title: "GitHub Actions로 CI/CD 파이프라인 구축하기"
date: 2025-12-12 14:00:00 +0900
categories: [DevOps, CI/CD]
tags: [github-actions, cicd, devops, automation]
---

## CI/CD가 왜 필요한가?

수동 배포의 문제점:
- 🐛 "배포할 때마다 뭔가 빠뜨려요"
- ⏰ "배포하는 데 30분씩 걸려요"
- 😰 "금요일 오후에는 배포 못 해요"

CI/CD를 도입하면 이런 고민이 사라집니다.

---

## 🎯 구축할 파이프라인

```
Push → Test → Build → Deploy
```

1. **CI (Continuous Integration)**
   - 코드 린트 검사
   - 유닛 테스트 실행
   - Docker 이미지 빌드

2. **CD (Continuous Deployment)**
   - 스테이징 자동 배포
   - 프로덕션 승인 후 배포

---

## 📄 워크플로우 파일

### .github/workflows/ci.yml

{% raw %}
```yaml
name: CI Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: '3.12'
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - name: Install dependencies
        run: |
          pip install ruff mypy
          pip install -r requirements.txt
      
      - name: Run Ruff (linter)
        run: ruff check .
      
      - name: Run MyPy (type check)
        run: mypy app/

  test:
    runs-on: ubuntu-latest
    needs: lint
    
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'
      
      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-dev.txt
      
      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/test_db
        run: |
          pytest --cov=app --cov-report=xml
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml

  build:
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push'
    
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=sha,prefix=
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```
{% endraw %}

### .github/workflows/deploy.yml

{% raw %}
```yaml
name: Deploy

on:
  workflow_run:
    workflows: ["CI Pipeline"]
    types: [completed]
    branches: [main]

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    environment: staging
    
    steps:
      - name: Deploy to Staging
        run: |
          echo "Deploying to staging..."
          # SSH로 서버 접속 후 docker pull & restart
          # 또는 kubectl apply
      
      - name: Run smoke tests
        run: |
          curl -f https://staging.example.com/health || exit 1

  deploy-production:
    runs-on: ubuntu-latest
    needs: deploy-staging
    environment: production  # 승인 필요
    
    steps:
      - name: Deploy to Production
        run: |
          echo "Deploying to production..."
```
{% endraw %}

---

## 💡 핵심 포인트

### 1. 캐시 활용하기

{% raw %}
```yaml
- uses: actions/setup-python@v5
  with:
    python-version: '3.12'
    cache: 'pip'  # pip 캐시 자동 관리
```
{% endraw %}

### 2. Matrix 빌드
여러 Python 버전에서 테스트하고 싶다면:

{% raw %}
```yaml
strategy:
  matrix:
    python-version: ['3.10', '3.11', '3.12']
steps:
  - uses: actions/setup-python@v5
    with:
      python-version: ${{ matrix.python-version }}
```
{% endraw %}

### 3. Secrets 관리

{% raw %}
```yaml
env:
  API_KEY: ${{ secrets.API_KEY }}
```
{% endraw %}

Settings > Secrets에서 안전하게 관리하세요.

### 4. Environment Protection Rules
- 프로덕션 배포 전 승인 필수
- 특정 브랜치만 배포 허용
- 배포 시간 제한

---

## 🎯 결과

이렇게 구성하면:
- ✅ PR마다 자동 테스트
- ✅ main 브랜치 푸시 시 자동 빌드
- ✅ 스테이징 자동 배포
- ✅ 프로덕션 승인 후 배포

**"금요일 오후 배포"도 이제 두렵지 않습니다!** 🚀

다음 글에서는 ArgoCD를 이용한 GitOps 배포를 다뤄보겠습니다.
