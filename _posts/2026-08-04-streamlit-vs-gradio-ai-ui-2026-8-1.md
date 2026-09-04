---
title: "Streamlit vs Gradio로 “하루 만에” AI 데모 UI를 만드는 법: 실전 설계/성능/배포까지"
description: "AI 모델(LLM/RAG/이미지 생성/ASR 등)을 “일단 써보게” 만드는 데모 UI는, 제품 UI와 다른 요구를 가집니다. 핵심은 빠른 반복(모델/프롬프트/파라미터), 안정적인 동시성, 그리고 배포/공유 비용 최소화입니다."
date: 2026-08-04 03:22:12 +0900
categories: [AI, Prototyping]
tags: [ai, prototyping]
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

AI 모델(LLM/RAG/이미지 생성/ASR 등)을 “일단 써보게” 만드는 데모 UI는, 제품 UI와 다른 요구를 가집니다. 핵심은 **빠른 반복(모델/프롬프트/파라미터), 안정적인 동시성, 그리고 배포/공유 비용 최소화**입니다. 이때 Streamlit과 Gradio는 둘 다 “Python만으로 UI”를 만들지만, 내부 철학이 달라서 프로젝트 성격에 따라 체감 생산성이 크게 갈립니다.

- **언제 Streamlit이 좋은가**
  - 데모가 곧 **데이터 앱/운영 도구**로 확장될 가능성이 크다 (대시보드, 분석 테이블, 관리자 화면)
  - “화면 구성 + 상태 관리 + 여러 위젯 조합”이 중요하다
  - 2026년 들어 Streamlit이 **Starlette/Uvicorn 기반**으로 전환되며 ASGI 호환성이 좋아졌고, 하단 고정 UI(`st.bottom`) 같은 패턴이 쉬워졌다[^1]

- **언제 Gradio가 좋은가**
  - 목표가 명확히 “모델 데모/리서치 공유”이고, **ChatInterface/Blocks**로 빠르게 형태가 나온다[^2]
  - **동시 요청 제어(Queue/Concurrency)**가 핵심인 추론 데모(특히 GPU 자원 제한)[^3]
  - FastAPI에 **mount**해서 기존 백엔드/인증(OAuth 등)에 붙이고 싶다[^4]

- **언제 둘 다 “쓰면 안 되는가”**
  - 외부 고객 대상의 정교한 UX, 세밀한 프론트 상태 업데이트, 복잡한 디자인 시스템이 필요하면(또는 “진짜 제품 UI”) 결국 React/Next.js 등 정통 웹 스택이 더 싸게 먹힐 수 있습니다. 빠른 데모 프레임워크의 한계(전역 재실행, 컴포넌트 상태 분리 난이도 등)는 규모가 커질수록 비용으로 돌아옵니다(커뮤니티에서도 반복적으로 지적).[^5]

---

## 🔧 핵심 개념

### 1) Streamlit의 실행 모델: “스크립트 재실행 + 캐시/세션으로 제어”
Streamlit의 본질은 **사용자 인터랙션마다 스크립트를 다시 실행**하는 모델입니다. 그래서 UI 코드는 간단하지만, 성능/상태를 잡으려면 의도적으로 설계해야 합니다.[^6]

- **상태/성능의 핵심 프리미티브**
  - `st.cache_data`: 데이터 결과 캐시(serialize 가능한 결과에 적합)
  - `st.cache_resource`: 모델/클라이언트/커넥션 같은 “리소스” 캐시  
  Streamlit 문서에서도 `st.cache` 대신 이 두 가지로의 전환을 강조합니다.[^7]

- **2026년 변화 포인트(데모 UI 관점)**
  - Streamlit이 기본 서버를 **Tornado → Starlette/Uvicorn(ASGI)**로 전환: async 생태계/미들웨어/배포 호환성이 좋아지고, 고급 설정이 `st.App`로 노출됩니다.[^1]
  - `st.bottom`: 채팅 입력/툴바를 **화면 하단에 고정**하는 패턴을 공식 지원(“챗 UI”에 특히 유용)[^1]
  - `:shimmer[]`: 스트리밍/대기 상태를 “로딩 텍스트”로 자연스럽게 표현[^1]

**차이점 요약:** Streamlit은 “앱”을 만들기 좋고, 대신 **재실행 모델을 이해하고 캐시/세션을 설계**해야 합니다.

### 2) Gradio의 실행 모델: “이벤트 기반 + 내장 Queue로 동시성 제어”
Gradio는 Blocks/컴포넌트에 이벤트를 연결하고, 이벤트 실행은 **내장 Queue**가 받아서 처리합니다. “추론 함수 호출”이 중심이며, UI는 그 주변을 감싸는 구조입니다.

- **Queue/Concurrency가 설계의 중심**
  - 기본적으로 이벤트 리스너는 queue를 갖고, 동시 실행 수를 `concurrency_limit`으로 제어합니다.
  - 여러 이벤트가 GPU를 공유하면 `concurrency_id`로 **공유 큐**를 만들 수 있습니다. (GPU 1~2장짜리 데모에서 매우 현실적인 요구)[^3]
  - `Blocks.queue(default_concurrency_limit=...)`로 앱 전체 기본값을 줄 수도 있습니다.[^3]

- **Chat UI를 빨리 만드는 방법**
  - `gr.ChatInterface`는 챗봇 UI를 몇 줄로 올리는 고수준 추상화입니다.[^2]
  - 더 복잡한 이벤트/버튼/툴 호출을 붙이려면 `Blocks` 안에서 `gr.Chatbot` + `gr.ChatInterface`를 같이 감싸는 패턴을 권장합니다.[^2]

- **기존 백엔드와의 결합(실무에서 중요)**
  - `mount_gradio_app`로 FastAPI에 Gradio를 **서브패스**로 붙이고, `auth_dependency`로 외부 OAuth/인증을 연동할 수 있습니다.[^4]

**차이점 요약:** Gradio는 “모델 데모”에 최적화되어 있고, 특히 **동시성/공유/배포**가 강점입니다.

---

## 💻 실전 코드

현실적인 시나리오로 “RAG 기반 사내 문서 Q&A 데모”를 만듭니다.

- 요구사항:
  - 사용자 입력 → (벡터 검색) → 컨텍스트 구성 → LLM 호출
  - GPU/LLM API rate limit 때문에 **동시 요청 제한**
  - 사내 SSO/게이트웨이가 있어서 **FastAPI에 합쳐서 배포**
  - “빠른 데모”지만, 나중에 운영 도구로도 확장 가능

아래는 **Gradio를 FastAPI에 마운트**하고, Queue로 동시성을 제한하는 형태입니다.

### 0) 설치/실행

```bash
uv venv
source .venv/bin/activate
uv pip install fastapi uvicorn gradio openai python-dotenv
# (예시) OPENAI_API_KEY 환경변수 설정
uvicorn app:api --host 0.0.0.0 --port 8000
```

### 1) FastAPI + Gradio mount + 인증 훅(스텁) + Queue 동시성 제어

```python
# app.py
from __future__ import annotations

import os
from typing import Optional, List, Tuple

from fastapi import FastAPI, Request
import gradio as gr

from openai import OpenAI

api = FastAPI(title="RAG Demo Host")
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ---- (현실 포인트) 사내 인증은 게이트웨이/프록시가 헤더에 유저를 넣는 경우가 흔함 ----
def auth_dependency(req: Request) -> Optional[str]:
    # 예: X-Auth-User 헤더를 게이트웨이가 주입한다고 가정
    user = req.headers.get("x-auth-user")
    return user  # None이면 401

# ---- (현실 포인트) 벡터 검색은 보통 별도 서비스/DB로. 여기선 "서비스 호출" 형태로 스텁 ----
def retrieve_context(query: str) -> str:
    # TODO: 실제로는 pgvector/qdrant/weaviate/elastic 등에 질의
    return (
        "Context:\n"
        "- (DocA) API rate limit은 분당 60 요청\n"
        "- (DocB) 내부 정책상 PII는 마스킹 후 전송\n"
    )

def answer_with_rag(message: str, history: List[Tuple[str, str]]):
    # Gradio ChatInterface fn 시그니처: (message, history)
    context = retrieve_context(message)

    # (현실 포인트) 스트리밍/토큰 단위 출력은 UI 체감에 큰 영향.
    # 여기선 간단히 chunk yield로 흉내. 실제로는 OpenAI streaming API를 연결.
    prompt = f"""You are a helpful assistant for internal docs QA.
Use the provided context. If missing, say you don't know.

{context}

User: {message}
"""

    # (간단 구현) non-streaming 호출 후, UI에는 토큰처럼 나눠서 흘려보냄
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )
    text = resp.output_text

    buf = ""
    for token in text.split(" "):
        buf += (token + " ")
        yield buf

with gr.Blocks(title="Internal RAG Demo") as demo:
    gr.Markdown("## Internal RAG Q&A (FastAPI-mounted)\n- 동시성 제한 + 인증 연동 예시")
    chat = gr.ChatInterface(
        fn=answer_with_rag,
        examples=["정책상 PII 처리는 어떻게 해?", "rate limit은?", "이 문서 범위 밖 질문은?"],
    )

# (실무 포인트) GPU/외부 LLM API 보호: 전역 default 동시성 제한
demo = demo.queue(default_concurrency_limit=4)

# FastAPI에 /demo로 mount, 외부 인증 의존성으로 보호
from gradio.routes import mount_gradio_app
api = mount_gradio_app(
    api,
    demo,
    path="/demo",
    auth_dependency=auth_dependency,
    auth_message="Company SSO required",
)
```

**예상 동작**
- `http://localhost:8000/demo` 접속
- `x-auth-user` 헤더가 없으면 401(실제 운영에선 게이트웨이가 넣어줌)
- 동시 접속이 몰려도 Queue가 이벤트 실행을 제어(기본 4 동시 실행)

이 패턴의 장점은 “데모 UI”가 단독 서버가 아니라 **기존 API 서버의 일부**로 들어가서, 라우팅/로깅/인증/배포 파이프라인을 공통화할 수 있다는 점입니다. `auth_dependency`, `root_path` 같은 옵션이 그 목적에 맞게 설계돼 있습니다.[^4]

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) 동시성은 “기능”이 아니라 “자원 모델링”이다 (Gradio Queue 적극 사용)
GPU/LLM API는 보통 “무한 확장”이 아니라 **정해진 처리량**이 있습니다.  
Gradio에서는 이벤트마다 `concurrency_limit`, 여러 이벤트가 GPU를 공유하면 `concurrency_id`로 묶는 방식이 공식 가이드로 제시됩니다.[^3]  
- 데모가 “잘 되는 것처럼 보이는데 가끔 죽는” 가장 흔한 원인은 동시성 제어 부재입니다.
- 무조건 `None`(무제한)으로 풀면, 피크에서 프로세스/메모리/레이트리밋이 먼저 터집니다.

### Best Practice 2) Streamlit은 “캐시 설계”가 곧 아키텍처다
Streamlit의 재실행 모델에서는 모델 로딩/DB 커넥션/벡터 인덱스 초기화 같은 무거운 작업을 매번 하면 즉시 망합니다. `st.cache_data`/`st.cache_resource`로 역할을 분리해야 합니다.[^7]  
- **resource 캐시**: LLM client, embedding model, DB pool
- **data 캐시**: 검색 결과, 전처리된 데이터(단 TTL/무효화 정책 필요)

### Best Practice 3) “빠른 데모”를 “운영 서비스”로 착각하지 말기
커뮤니티에서도 공통적으로 나오는 얘기지만, 빠른 데모 레이어는 규모가 커지면 UI/상태 복잡도에서 벽을 맞습니다.[^5]  
- 데모 단계에서 다음 질문을 명확히 하세요:
  - 이 UI가 3개월 뒤에도 “데모”인가, 아니면 “내부 툴/제품”이 되는가?
  - 사용자 수가 늘면 **동시성/비용/관측성(로그/트레이싱)**은 어떻게 할 건가?

### 흔한 함정/안티패턴
- (Gradio) Queue를 켜지 않고 “왜 피크에서 timeout 나지?” 고민
- (Streamlit) 모델/인덱스를 캐시하지 않고 버튼 클릭마다 재로딩
- (둘 다) 프록시 뒤 서빙하면서 base path 설정을 대충 처리 → 정적 파일/라우팅 깨짐  
  Gradio는 `root_path`가 이 문제를 다루는 옵션으로 명시돼 있습니다.[^4]

### 비용/성능/안정성 트레이드오프
- **Streamlit**: 앱 확장성/구성 자유도가 높지만, 재실행 모델 때문에 “성능은 설계로 해결”해야 함.
- **Gradio**: 추론 데모는 빠르고 안전(Queue), 하지만 복잡한 앱/페이지/권한별 UI 분기까지 커지면 FastAPI/프론트 분리 요구가 빨리 올 수 있음.
- 둘 다 공통: “가벼운 데모”일수록 관측성/리소스 제한을 미루는데, 실제로는 그게 장애의 시작점입니다.

---

## 🚀 마무리

- **Streamlit**은 2026년 기준으로 Starlette/Uvicorn 기반 전환과 `st.bottom`, `:shimmer[]` 같은 UX 도구가 더해지면서 “챗/데이터 앱” 형태의 데모를 **앱답게** 만들기 좋아졌습니다.[^1]  
- **Gradio**는 ChatInterface/Blocks + Queue가 만들어내는 “추론 데모 최적화”가 여전히 강하고, FastAPI에 마운트 + 외부 인증 연동이 깔끔합니다.[^4]

**도입 판단 기준(실무 체크리스트)**
1) 동시 사용자/추론 비용이 중요하다 → Gradio Queue 중심으로 설계  
2) 데모가 운영 도구/데이터 앱으로 커질 가능성이 크다 → Streamlit(캐시/상태 설계 전제)  
3) 기존 백엔드(인증/로깅/배포)에 합치고 싶다 → Gradio mount 또는 Streamlit의 ASGI 친화 변화 고려(단, 실제 운영 결합 방식은 검증 필요)[^1]

**다음 학습 추천**
- Gradio: Queue/Concurrency 튜닝을 실제 GPU 수에 맞게 모델링(공유 큐, limit)[^3]  
- Streamlit: `st.cache_data` vs `st.cache_resource`를 기준으로 “무엇을 어디에 캐시할지”부터 앱 구조를 설계[^7]

[^1]: <https://docs.streamlit.io/develop/quick-reference/release-notes/2026>
[^2]: <https://www.gradio.app/docs/gradio/chatinterface>
[^3]: <https://gradio.app/guides/queuing>
[^4]: <https://www.gradio.app/docs/gradio/mount_gradio_app>
[^5]: <https://www.reddit.com/r/Chatbots/comments/1u5kq4r/migrating_an_ai_desktop_interface_from_streamlit/>
[^6]: <https://docs.streamlit.io/develop/api-reference/caching-and-state>
[^7]: <https://docs.streamlit.io/develop/concepts/architecture/caching>
