---
title: "FastAPI 백엔드 “진짜” 베스트 프랙티스: DI·Lifespan·API 설계로 Django급 안정성 만들기"
description: "FastAPI는 “빠르게 만든 API”에서 끝나면 곤란합니다. 2025년의 FastAPI는 Pydantic v2, ASGI 생태계(uvicorn/starlette), async DB 드라이버/ORM(SQLAlchemy 2.x async)와 결합되며 타입 기반 계약(Contract) 과…"
date: 2026-01-04 02:31:26 +0900
categories: [Backend, Tutorial]
tags: [backend, tutorial]
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
FastAPI는 “빠르게 만든 API”에서 끝나면 곤란합니다. 2025년의 FastAPI는 Pydantic v2, ASGI 생태계(uvicorn/starlette), async DB 드라이버/ORM(SQLAlchemy 2.x async)와 결합되며 **타입 기반 계약(Contract)** 과 **명시적 의존성(Dependency Injection)** 을 중심으로 아키텍처를 잡는 쪽으로 성숙했습니다. 실무에서 문제는 늘 비슷합니다: “라우트가 비대해짐”, “DB 세션/커넥션 누수”, “startup/shutdown이 환경마다 다르게 동작”, “에러 포맷 제각각”, “Django처럼 표준 레일이 없어서 팀마다 스타일이 분열”.  
따라서 2025년 베스트 프랙티스는 *FastAPI를 Django처럼 ‘일관된 규칙’ 위에서 운용*하는 것입니다: **Lifespan으로 리소스 수명 관리**, **DI로 계층 분리**, **표준 에러 포맷(RFC 9457)로 API 설계 품질 고정**.[^1]

---

## 🔧 핵심 개념
### 1) DI(Dependency Injection)는 “주입”이 아니라 “요청 스코프 설계”
FastAPI의 Depends는 단순한 IoC가 아니라,
- 요청 단위로 객체를 만들고(예: DB session)
- 필요하면 재사용하며(요청 내 캐시)
- 종료 시 정리(cleanup)까지 수행하는 **요청 스코프 컨테이너**에 가깝습니다.  
이걸 제대로 쓰면 라우트는 얇아지고(HTTP 레이어), 검증/권한/리소스 조회 같은 반복 로직은 **Dependency로 재사용**됩니다.[^2]

### 2) Lifespan: “startup 이벤트”가 아니라 “프로세스 수명”의 진입점
실무에서 가장 큰 함정은 개발 서버 `--reload`/멀티워커/쿠버네티스 환경마다 startup 코드가 다르게(혹은 여러 번) 실행되는 겁니다. 최근 권장 흐름은 `lifespan` context에서 “무거운 리소스 초기화/정리”를 **idempotent** 하게 두고, 워커 수(N)만큼 실행됨을 전제로 설계하는 것입니다.[^1]

### 3) FastAPI vs Django: “프레임워크 선택”보다 “경계(Boundary) 설계”가 핵심
Django(특히 DRF)는 ORM/미들웨어/인증/권한/관리자 등 “레일”이 강하고, FastAPI는 레고에 가깝습니다. 즉 FastAPI에서는 팀이 **프로젝트 구조(routers/services/repos), 에러 규약, 설정 로딩, 테스트 전략**을 먼저 고정해야 장기 유지보수가 됩니다. “Keep the app shape boring(지루하게 유지)”가 생산 환경에서 강력한 규칙으로 반복 등장합니다.[^3]

### 4) API 설계: 에러는 표준으로 고정(RFC 9457 Problem Details)
클라이언트 입장에서 가장 비용이 큰 것은 “에러 응답이 서비스마다 다름”입니다. RFC 9457은 `application/problem+json`으로 **일관된 에러 바디**(type/title/status/detail/instance)를 정의해, API 간 상호운용성과 디버깅 효율을 올립니다(구 RFC 7807을 대체).[^4]

---

## 💻 실전 코드
- FastAPI + Lifespan으로 리소스(예: DB engine) 수명 관리
- SQLAlchemy 2.x async session을 Dependency로 주입
- Service/Repo 계층으로 라우트 얇게 유지
- RFC 9457 Problem Details 형태로 에러 응답 통일

```python
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import String, Integer, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# -----------------------------
# 1) DB / Models (SQLAlchemy 2.x async)
# -----------------------------
DATABASE_URL = "sqlite+aiosqlite:///./app.db"

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

async def get_session() -> AsyncIterator[AsyncSession]:
    # 요청 단위로 세션을 열고, 끝나면 자동으로 정리
    async with SessionLocal() as session:
        yield session

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# -----------------------------
# 2) Schema (Pydantic v2 style로 써도 무방하나, 예제는 단순화)
# -----------------------------
class UserIn(BaseModel):
    email: EmailStr
    name: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str

# -----------------------------
# 3) Repo / Service (라우트 slim 유지)
# -----------------------------
class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        return await self.session.scalar(stmt)

    async def create(self, email: str, name: str) -> User:
        user = User(email=email, name=name)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

class UserService:
    def __init__(self, repo: UserRepo):
        self.repo = repo

    async def register(self, email: str, name: str) -> User:
        # “비즈니스 규칙”은 라우트가 아니라 서비스에 둔다
        existing = await self.repo.by_email(email)
        if existing:
            raise ValueError("Email already registered")
        return await self.repo.create(email=email, name=name)

def get_user_repo(session: SessionDep) -> UserRepo:
    return UserRepo(session)

def get_user_service(repo: Annotated[UserRepo, Depends(get_user_repo)]) -> UserService:
    return UserService(repo)

UserServiceDep = Annotated[UserService, Depends(get_user_service)]

# -----------------------------
# 4) RFC 9457 Problem Details 형태의 에러 응답
# -----------------------------
def problem_details(
    *,
    type_: str,
    title: str,
    status_code: int,
    detail: str,
    instance: str,
    extra: dict | None = None,
) -> JSONResponse:
    body = {
        "type": type_,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
    }
    if extra:
        body.update(extra)  # RFC는 확장 필드를 허용(클라이언트와 합의 필요)
    return JSONResponse(body, status_code=status_code, media_type="application/problem+json")

# -----------------------------
# 5) Lifespan: 프로세스 수명에서 리소스 준비/정리
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 개발/테스트 편의: 테이블 자동 생성 (운영은 Alembic 권장)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title="Accounts API", lifespan=lifespan)

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    # 도메인 예외 -> 표준 에러 포맷으로 변환
    return problem_details(
        type_="https://example.com/problems/conflict",
        title="Conflict",
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
        instance=str(request.url.path),
        extra={"request_id": str(uuid4())},  # 관측성/추적을 위한 확장 필드 예시
    )

@app.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserIn, svc: UserServiceDep):
    try:
        user = await svc.register(email=payload.email, name=payload.name)
        return UserOut(id=user.id, email=user.email, name=user.name)
    except IntegrityError:
        # 유니크 제약 위반 같은 DB 예외는 여기서 도메인 예외로 치환
        raise HTTPException(status_code=409, detail="Email already registered")
```

---

## ⚡ 실전 팁
1) **Async는 “필요한 곳만”**  
라우트가 async라고 해서 모든 것이 빨라지지 않습니다. sync ORM/무거운 CPU 작업을 async route에서 돌리면 이벤트 루프가 막힙니다. blocking이 섞이면 threadpool/worker로 분리하거나(또는 `run_in_threadpool`류) 경계를 명확히 하세요.[^3]

2) **DB 세션은 “요청 단위 yield dependency”로 고정**  
핵심은 “매 요청마다 새 커넥션 생성”이 아니라, 엔진 풀 + 세션 스코프를 올바르게 잡는 겁니다. `yield`로 반환하고 종료 시 정리되는 패턴을 표준으로 팀 규칙화하세요.[^5]

3) **Lifespan 코드는 idempotent하게**  
`--reload`나 멀티워커에서 startup이 여러 번 실행될 수 있습니다. “한 번만 실행돼야 하는 작업(마이그레이션/스케줄러 등록 등)”을 앱 프로세스에 넣는 순간 운영에서 꼬입니다. 워커/레플리카 모델을 전제로 분리하세요.[^1]

4) **DI를 “검증/권한/리소스 로딩”에 적극 재사용**  
예: `valid_post_id`, `parse_jwt_data` 같은 dependency를 조합(chain)하면, 라우트마다 같은 검증을 복붙하지 않게 됩니다. FastAPI는 요청 내 dependency 결과를 캐시하는 특성이 있으므로(남발만 안 하면) 효율도 좋습니다.[^2]

5) **에러 응답은 RFC 9457로 통일하고, 확장은 최소화**
`application/problem+json`을 기본으로 고정하면, 프론트/모바일/외부 파트너가 에러 처리 코드를 표준화할 수 있습니다. 다만 `errors` 같은 확장 필드는 팀/클라이언트와 합의된 스키마로 제한하세요(무제한 확장은 다시 혼돈을 만듦).[^4]

---

## 🚀 마무리
2025년 FastAPI 베스트 프랙티스의 중심은 “기능”이 아니라 **운영 가능한 구조**입니다.  
- Lifespan으로 리소스 수명을 통제하고[^1]  
- DI로 요청 스코프를 표준화하며[^2]  
- 서비스/레포 계층으로 라우트를 얇게 만들고[^3]  
- RFC 9457로 에러 계약을 고정하면[^4]  
FastAPI도 Django 못지않게 “예측 가능한 백엔드”가 됩니다.

다음 학습 추천:
- FastAPI dependency 설계(체이닝/캐싱/테스트에서 override) 심화[^2]  
- Lifespan + 멀티워커/쿠버네티스 환경에서의 startup 전략[^1]  
- OpenAPI 스키마 품질(버저닝, 에러 스키마, 호환성 테스트)과 RFC 9457 기반 API 계약 관리[^6]

[^1]: <https://medium.com/%40dynamicy/fastapi-starlette-lifecycle-guide-startup-order-pitfalls-best-practices-and-a-production-ready-53e29dcb9249>
[^2]: <https://github.com/zhanymkanov/fastapi-best-practices>
[^3]: <https://medium.com/%40wyliewang.work/fastapi-in-production-patterns-that-dont-bite-you-six-months-later-fa8e2fd5ab6d>
[^4]: <https://www.ietf.org/ietf-ftp/rfc/rfc9457.html>
[^5]: <https://medium.com/%40abipoongodi1211/fastapi-best-practices-a-complete-guide-for-building-production-ready-apis-bb27062d7617>
[^6]: <https://swagger.io/blog/problem-details-rfc9457-doing-api-errors-well/>
