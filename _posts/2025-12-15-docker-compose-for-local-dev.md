---
title: "Docker Compose로 로컬 개발환경 세팅하기 🐳"
description: "이 말을 안 하려면 Docker가 필수입니다. 특히 Docker Compose는 로컬 개발환경 구성에 있어서 게임 체인저입니다."
date: 2025-12-15 10:00:00 +0900
categories: [Infrastructure, Docker]
tags: [docker, docker-compose, devops, local-development]
---

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
## 왜 Docker Compose인가?

"내 컴퓨터에서는 되는데요?"

이 말을 안 하려면 Docker가 필수입니다. 
특히 **Docker Compose**는 로컬 개발환경 구성에 있어서 게임 체인저입니다.

---

## 🎯 목표

이 글에서 만들 개발환경:
- FastAPI 백엔드
- PostgreSQL 데이터베이스
- Redis 캐시
- pgAdmin (DB 관리 도구)

---

## 📄 docker-compose.yml

```yaml
version: '3.8'

services:
  # FastAPI 애플리케이션
  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: fastapi-app
    ports:
      - "8000:8000"
    volumes:
      - ./app:/app/app  # 코드 변경 시 자동 반영
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/myapp
      - REDIS_URL=redis://redis:6379
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  # PostgreSQL
  db:
    image: postgres:16-alpine
    container_name: postgres-db
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
      POSTGRES_DB: myapp
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Redis
  redis:
    image: redis:7-alpine
    container_name: redis-cache
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  # pgAdmin
  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@admin.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - db

volumes:
  postgres_data:
  redis_data:
```

---

## 🐍 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 복사
COPY . .

# 포트 노출
EXPOSE 8000

# 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 🚀 사용법

### 시작하기
```bash
# 모든 서비스 시작 (백그라운드)
docker-compose up -d

# 로그 확인
docker-compose logs -f api

# 특정 서비스만 재시작
docker-compose restart api
```

### 데이터베이스 접속
```bash
# psql로 직접 접속
docker-compose exec db psql -U postgres -d myapp

# pgAdmin 접속
# http://localhost:5050
# Email: admin@admin.com
# Password: admin
```

### 종료하기
```bash
# 서비스 종료 (데이터 유지)
docker-compose down

# 서비스 종료 + 볼륨 삭제 (데이터 초기화)
docker-compose down -v
```

---

## 💡 꿀팁

### 1. 개발용 vs 프로덕션용 분리

```bash
# docker-compose.override.yml (개발용, 자동 적용)
# docker-compose.prod.yml (프로덕션용)

# 프로덕션 실행
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 2. .env 파일 활용

```yaml
# docker-compose.yml
services:
  db:
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
```

```bash
# .env
DB_PASSWORD=super_secret_password
```

### 3. healthcheck 활용
서비스 간 의존성이 있을 때 `depends_on`만으로는 부족합니다.
`healthcheck`를 설정하면 DB가 완전히 준비된 후 앱이 시작됩니다.

### 4. 볼륨으로 Hot Reload
```yaml
volumes:
  - ./app:/app/app  # 소스코드 마운트
```
이렇게 하면 코드 수정 시 컨테이너 재빌드 없이 바로 반영됩니다.

---

## 🎯 마무리

Docker Compose를 쓰면:
- ✅ 팀원 모두 동일한 환경
- ✅ 원커맨드로 전체 인프라 구동
- ✅ 프로덕션과 유사한 환경에서 개발

처음 세팅이 조금 번거롭지만, 한번 해두면 정말 편합니다!

다음 글에서는 **Kubernetes 로컬 개발환경 (k3d)**을 다뤄보겠습니다.

