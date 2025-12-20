---
title: "AI로 빠르게 프로토타이핑하는 나만의 방법 🤖"
date: 2025-12-20 11:00:00 +0900
categories: [AI, Prototyping]
tags: [ai, llm, prototyping, productivity, cursor]
---

## 들어가며

요즘 저는 새로운 아이디어가 떠오르면 **하루 안에 동작하는 프로토타입**을 만들어봅니다.

예전 같으면 "나중에 시간 날 때..."라며 미뤘을 텐데, 
AI 도구들 덕분에 아이디어 검증 속도가 비약적으로 빨라졌습니다.

오늘은 제가 실제로 사용하는 AI 프로토타이핑 워크플로우를 공유해봅니다.

---

## 🛠️ 내가 사용하는 도구들

### 1. Cursor IDE
코드 작성의 80%는 AI와 함께합니다.

```python
# 이런 식으로 주석만 달아도
# FastAPI로 유저 CRUD API 만들어줘

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class User(BaseModel):
    id: int
    name: str
    email: str

# AI가 나머지를 완성해줍니다
```

### 2. Claude / ChatGPT
복잡한 로직 설계나 아키텍처 고민은 대화로 풀어갑니다.

- "이런 요구사항에 맞는 DB 스키마 설계해줘"
- "이 코드 더 효율적으로 리팩토링 해줘"
- "이 에러 왜 발생하는지 분석해줘"

### 3. v0 by Vercel
프론트엔드 UI가 필요할 때, 말로 설명하면 React 컴포넌트를 생성해줍니다.

---

## 📋 나의 프로토타이핑 프로세스

### Step 1: 아이디어 정리 (15분)
- 핵심 기능 3가지만 정의
- 사용자 시나리오 1개 작성
- 최소한의 데이터 모델 스케치

### Step 2: 백엔드 스캐폴딩 (30분)
```bash
# 프로젝트 생성
mkdir my-prototype && cd my-prototype
python -m venv venv && source venv/bin/activate
pip install fastapi uvicorn sqlalchemy
```

AI에게 API 엔드포인트 코드 요청 → 복붙 → 수정

### Step 3: 프론트엔드 (1시간)
- v0로 UI 컴포넌트 생성
- Next.js로 간단한 페이지 구성
- API 연동

### Step 4: 배포 (30분)
```bash
# 백엔드: Railway 또는 Render
# 프론트엔드: Vercel
# 데이터베이스: Supabase 또는 PlanetScale
```

---

## 💡 핵심 팁

### 1. 완벽함을 버려라
프로토타입의 목적은 **아이디어 검증**입니다.
코드 퀄리티는 나중 문제!

### 2. 범위를 좁혀라
"이것도 되면 좋겠는데..."는 금물.
**MVP(Minimum Viable Product)** 원칙을 지키세요.

### 3. AI에게 맥락을 줘라
```
❌ "로그인 기능 만들어줘"
⭕ "FastAPI + SQLAlchemy로 JWT 기반 로그인 API 만들어줘. 
   이메일/비밀번호로 로그인하고, access_token 반환해줘."
```

### 4. 실패해도 괜찮아
하루 투자로 "이건 아니다"를 알 수 있다면 성공입니다.

---

## 🎯 마무리

AI는 도구일 뿐입니다.

하지만 이 도구를 **어떻게 활용하느냐**에 따라 
생산성이 5배, 10배 차이 날 수 있습니다.

여러분도 한번 시도해보세요.
오늘 떠오른 아이디어, 내일까지 만들어보는 건 어떨까요? 🚀

---

다음 글에서는 실제 프로젝트 예시와 함께 더 구체적인 팁을 공유하겠습니다!

