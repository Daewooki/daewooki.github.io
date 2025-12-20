---
title: "FastAPI 프로젝트 구조 - 실무에서 쓰는 Best Practices"
date: 2025-12-18 09:00:00 +0900
categories: [Backend, FastAPI]
tags: [fastapi, python, backend, api, best-practices]
---

## 들어가며

FastAPI로 여러 프로젝트를 진행하면서 정립한 프로젝트 구조와 패턴을 공유합니다.

작은 프로젝트부터 대규모 서비스까지 확장 가능한 구조입니다.

---

## 📁 프로젝트 구조

```
my-fastapi-project/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 앱 엔트리포인트
│   ├── config.py            # 설정 관리
│   ├── database.py          # DB 연결 설정
│   │
│   ├── api/                  # API 라우터
│   │   ├── __init__.py
│   │   ├── deps.py          # 의존성 주입
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py    # v1 라우터 통합
│   │       ├── users.py
│   │       └── items.py
│   │
│   ├── core/                 # 핵심 로직
│   │   ├── __init__.py
│   │   ├── security.py      # 인증/보안
│   │   └── exceptions.py    # 커스텀 예외
│   │
│   ├── models/               # SQLAlchemy 모델
│   │   ├── __init__.py
│   │   └── user.py
│   │
│   ├── schemas/              # Pydantic 스키마
│   │   ├── __init__.py
│   │   └── user.py
│   │
│   └── services/             # 비즈니스 로직
│       ├── __init__.py
│       └── user_service.py
│
├── tests/
├── alembic/                  # DB 마이그레이션
├── .env
├── requirements.txt
└── docker-compose.yml
```

---

## 🔑 핵심 파일들

### 1. config.py - 환경변수 관리

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "My FastAPI App"
    debug: bool = False
    
    # Database
    database_url: str
    
    # JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
```

### 2. deps.py - 의존성 주입

```python
from typing import Generator, Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from app.database import SessionLocal
from app.config import get_settings
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Depends(oauth2_scheme)]
) -> User:
    settings = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

# Type alias for cleaner code
DBSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
```

### 3. 라우터 구성

```python
# app/api/v1/users.py
from fastapi import APIRouter, HTTPException
from app.api.deps import DBSession, CurrentUser
from app.schemas.user import UserCreate, UserResponse
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=UserResponse)
async def create_user(user_in: UserCreate, db: DBSession):
    user = user_service.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return user_service.create(db, user_in)

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser):
    return current_user
```

---

## 💡 Best Practices

### 1. 서비스 레이어 분리
라우터에 비즈니스 로직을 넣지 마세요. 서비스 레이어로 분리하면 테스트가 쉬워집니다.

### 2. Pydantic v2 활용
```python
from pydantic import BaseModel, ConfigDict

class UserBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    email: str
    name: str
```

### 3. 비동기 활용
I/O 바운드 작업은 `async/await`로 처리하세요.

```python
# DB 작업은 동기로 (SQLAlchemy)
# HTTP 요청은 비동기로 (httpx)
import httpx

async def fetch_external_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        return response.json()
```

### 4. 예외 처리 통일
```python
# app/core/exceptions.py
from fastapi import HTTPException

class NotFoundError(HTTPException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=404, detail=detail)

class UnauthorizedError(HTTPException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(status_code=401, detail=detail)
```

---

## 🚀 마무리

이 구조를 기반으로 프로젝트를 시작하면 확장성과 유지보수성을 모두 잡을 수 있습니다.

다음 글에서는 Alembic을 이용한 DB 마이그레이션 전략을 다뤄보겠습니다!

