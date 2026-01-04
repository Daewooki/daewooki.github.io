---
title: "2025년 FastAPI 백엔드 베스트 프랙티스: “DI + Lifespan + Contract-First”로 아키텍처를 고정하라"
date: 2025-12-24 02:09:34 +0900
categories: [Backend, Tutorial]
tags: [backend, tutorial, trend, 2025-12]
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
2025년의 Python 백엔드에서 FastAPI는 “빠르게 만들기”보다 “오래 운영하기”에서 실력이 갈립니다. 특히 (1) settings/DB/http client 같은 리소스의 생명주기, (2) 테스트에서의 override 가능성, (3) API 계약(OpenAPI) 일관성이 무너지면 서비스가 커질수록 변경 비용이 폭증합니다.  
핵심은 **FastAPI의 Dependency Injection(DI)을 요청 단위 경계로**, **Starlette Lifespan을 프로세스 단위 경계로** 명확히 나누고, 그 위에 **API 설계 규칙(에러/페이지네이션/버저닝)**을 “고정된 계약”으로 세우는 것입니다. FastAPI의 DI는 OpenAPI 스키마와도 강하게 결합되어 있어, 설계를 잘하면 문서/검증/보안이 함께 따라옵니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/he/tutorial/dependencies/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) DI(요청 단위) vs Lifespan(앱 단위)
- **DI(Depends)**: 요청 처리 전에 실행되고 결과를 엔드포인트에 주입합니다. 같은 요청 내에서 같은 dependency가 여러 번 필요해도 **요청 단위 캐시**가 동작합니다(기본 `use_cache=True`). ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/reference/dependencies/?utm_source=openai))  
- **Lifespan**: 앱 시작/종료 시점에 리소스를 만들고 정리합니다. Starlette는 Lifespan이 끝나기 전엔 요청을 받지 않으며, teardown은 연결/백그라운드 작업 종료 후 실행됩니다. 또한 Lifespan에서 만든 객체를 `app.state`/`request.state`로 공유할 수 있습니다. ([starlette.io](https://www.starlette.io/lifespan/?utm_source=openai))

결론:  
- **DB pool, AsyncClient, 모델 로딩**처럼 “프로세스 전체에서 공유”할 것은 Lifespan.  
- “요청마다 달라지는 컨텍스트(인증 사용자, 트랜잭션 세션)”는 DI.

### 2) Settings: `pydantic-settings` + `@lru_cache`로 “가볍고 테스트 가능한 싱글턴”
FastAPI 문서도 settings를 dependency로 제공하고 `@lru_cache`로 재로딩 비용을 없애는 패턴을 권장합니다. 이 방식은 테스트에서 override/환경변수 주입이 상대적으로 깔끔합니다. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/az/advanced/settings/?utm_source=openai))

### 3) “에러 포맷”을 계약으로 고정: RFC 7807 (Problem Details)
대규모 서비스에서 에러 응답이 제각각이면 프론트/모바일/외부 파트너가 모두 고통받습니다. RFC 7807의 `application/problem+json`은 **기계가 읽기 좋은 에러 표준 포맷**을 제시합니다. ([datatracker.ietf.org](https://datatracker.ietf.org/doc/rfc7807?utm_source=openai))  
FastAPI는 예외 핸들러를 통해 이 포맷을 전역으로 강제하기 좋습니다.

### 4) Django와의 역할 분리(현실적인 하이브리드)
- **Django**: Admin/ORM 중심의 “도메인 백오피스”, 강력한 auth/관리 UI.
- **FastAPI**: 외부 공개 API, BFF, 고성능 IO 중심 엔드포인트.  
운영 관점에선 “한 프레임워크로 통일”보다, **경계(도메인/배포 단위/DB 스키마 소유권)**를 명확히 하는 게 더 중요합니다.

---

## 💻 실전 코드
- FastAPI + Lifespan으로 `httpx.AsyncClient`를 앱 단위로 생성
- `pydantic-settings` + `@lru_cache`로 Settings 단일화
- DI로 settings/client를 주입
- 예외를 RFC7807 스타일로 통일

```python
from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated, Any, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


# 1) Settings: dependency + @lru_cache로 싱글턴화 (요청마다 파일/환경 재로딩 방지)
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "my-api"
    UPSTREAM_BASE_URL: str = "https://api.example.com"
    TIMEOUT_SECONDS: float = 3.0


@lru_cache
def get_settings() -> Settings:
    # 테스트에서 환경변수/캐시를 재설정하거나, app factory로 주입하는 전략을 쓸 수 있음
    return Settings()


# 2) RFC7807(Problem Details) 스타일 응답 모델
class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: Optional[str] = None
    instance: Optional[str] = None
    # 필요하면 extension 필드(trace_id 등)도 추가 가능


def problem(status: int, title: str, detail: str | None = None, instance: str | None = None):
    payload = ProblemDetails(status=status, title=title, detail=detail, instance=instance).model_dump()
    return JSONResponse(payload, status_code=status, media_type="application/problem+json")


# 3) Lifespan: 프로세스 단위 리소스(http client 등) 생성/정리
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # 앱 전체에서 공유할 AsyncClient: connection pool 재사용으로 레이턴시/자원 효율 개선
    async with httpx.AsyncClient(
        base_url=settings.UPSTREAM_BASE_URL,
        timeout=settings.TIMEOUT_SECONDS,
    ) as client:
        app.state.http_client = client
        yield
        # async with 블록이 종료되며 client가 안전하게 close됨


app = FastAPI(lifespan=lifespan)


# 4) DI: request에서 app.state를 꺼내 주입 (요청 단위 경계로 정리)
def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # 모든 HTTPException을 RFC7807로 통일
    return problem(
        status=exc.status_code,
        title="HTTP Error",
        detail=str(exc.detail),
        instance=str(request.url),
    )


@app.get("/v1/upstream-health")
async def upstream_health(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    # settings/client 모두 DI로 주입되어 테스트/대체가 쉬워짐
    r = await client.get("/health")

    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Upstream error: {r.status_code}")

    return {"app": settings.APP_NAME, "upstream": "ok", "status_code": r.status_code}
```

---

## ⚡ 실전 팁
1) **Lifespan에 “너무 많은 정책”을 넣지 말기**  
Lifespan은 “리소스 생성/정리”까지만. 비즈니스 규칙/라우팅/DI graph를 Lifespan에 섞으면 테스트에서 override가 어려워집니다(특히 settings를 Lifespan에서 직접 고정해버리면). Lifespan은 Starlette 레벨 개념이며 `state` 공유가 핵심입니다. ([starlette.io](https://www.starlette.io/lifespan/?utm_source=openai))

2) **DI 캐시를 이해하고 `use_cache=False`를 의도적으로만 사용**  
FastAPI는 같은 요청 내 dependency 결과를 재사용합니다. “같은 요청에서 매번 새 값”이 필요한 특수 케이스에서만 `use_cache=False`를 쓰세요. ([fastapi.tiangolo.com](https://fastapi.tiangolo.com/reference/dependencies/?utm_source=openai))

3) **에러 응답은 ‘표준 포맷 + trace_id’까지가 기본**  
RFC7807을 쓰면 클라이언트가 공통 파서를 가질 수 있습니다. 운영에선 `instance`(요청 URL) + `trace_id`(로그 상관관계)를 extension으로 추가하는 게 효과가 큽니다. ([datatracker.ietf.org](https://datatracker.ietf.org/doc/rfc7807?utm_source=openai))

4) **FastAPI vs Django는 “기능 비교”보다 “경계 설정”이 우선**  
Django(관리/도메인)와 FastAPI(외부 API/BFF)를 섞을 때는
- API 스키마(OpenAPI) 소유권
- DB 스키마 마이그레이션 소유권
- 인증 주체(SSO/JWT/Session)  
을 문서로 먼저 고정하세요. 프레임워크 선택보다 이 경계가 장애를 줄입니다.

---

## 🚀 마무리
2025년 FastAPI 백엔드 베스트 프랙티스의 요지는 “기술 스택”이 아니라 **경계 설계**입니다.

- 요청 단위는 **Depends(DI)**, 프로세스 단위는 **Lifespan**
- Settings는 `pydantic-settings` + `@lru_cache`로 **가볍고 테스트 가능하게**
- API 품질은 RFC7807 같은 **에러 계약**으로 고정
- Django와 병행한다면 “무엇을 어디서 소유할지”를 먼저 합의

다음 학습으로는 (1) OpenAPI 기반 Contract-First 개발(스키마 버저닝/호환성), (2) 테스트 전략(TestClient로 Lifespan 포함, DI override 설계), (3) 비동기 리소스(Async DB, httpx) 생명주기 패턴을 깊게 파보는 것을 추천합니다. ([starlette.io](https://www.starlette.io/lifespan/?utm_source=openai))