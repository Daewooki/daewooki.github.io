---
title: "LLM API 비용을 “반으로” 줄이는 2026년식 Routing: Prompt Caching + Semantic Cache + Cascade로 토큰을 아껴라"
description: "프로덕션에서 LLM 비용이 폭증하는 패턴은 대체로 하나입니다. 매 요청마다 “거의 같은” 컨텍스트(시스템 프롬프트, tool schema, 정책/가드레일, 공통 문서, 대화 히스토리)를 통째로 다시 보내고, 비싼 모델이 그걸 매번 다시 prefill합니다."
date: 2026-08-07 03:10:14 +0900
categories: [AI, LLM]
tags: [ai, llm]
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
프로덕션에서 LLM 비용이 폭증하는 패턴은 대체로 하나입니다. **매 요청마다 “거의 같은” 컨텍스트(시스템 프롬프트, tool schema, 정책/가드레일, 공통 문서, 대화 히스토리)를 통째로 다시 보내고, 비싼 모델이 그걸 매번 다시 prefill**합니다. Agent/멀티에이전트로 갈수록 이 “중복 prefill”이 전체 비용의 대부분이 됩니다.

이 글에서 다룰 해결책은 **(1) Prompt Caching으로 “동일 prefix”를 싸게 재사용하고, (2) Semantic Cache로 “의미적으로 같은 질문”을 재사용하며, (3) Model Routing/Cascade로 “비싼 모델은 정말 필요할 때만” 호출**하는 조합입니다. 2026년 7~8월 기준으로 Google Gemini는 **Batch API로 50% 비용 절감** 같은 옵션도 공식 문서에 포함되어 있고, OpenAI/Anthropic 모두 **프롬프트 캐싱**을 비용 최적화의 1순위 레버로 밀고 있습니다.[^1]

언제 쓰면 좋나?
- **반복되는 prefix가 큰 서비스**: RAG/에이전트/코딩 어시스턴트/툴콜 기반 챗봇(도구 정의가 길다)
- **질문 분포가 반복적**(FAQ, 고객센터, 운영 자동화, 사내 검색)
- **SLA(지연/에러)와 비용을 동시에** 잡아야 함 (cache hit는 대체로 TTFT도 줄어듦)

언제 쓰면 안 되나?
- 요청마다 시스템 프롬프트/툴이 자주 바뀌는 구조(캐시가 계속 깨짐)
- 사용자별로 컨텍스트가 매번 크게 달라 prefix 동일성이 낮은 경우(캐시 이득이 작음)
- “정확히 최신”이 중요한 질의인데 semantic cache로 재사용 위험을 통제할 수 없는 경우(드리프트/환각 리스크)

---

## 🔧 핵심 개념
### 1) Prompt Caching: “동일 prefix”를 싸게 재사용
**Prompt Caching**은 요청 프롬프트의 **앞부분(prefix)** 이 이전 요청과 **완전히 동일**하면, 모델이 그 부분을 다시 계산하지 않고 캐시를 재사용하는 방식입니다.

- OpenAI는 API에서 “가장 긴 prefix”를 캐시하며, **최소 1,024 tokens부터 128 tokens 단위로 증가**하는 식으로 prefix 캐싱이 동작한다고 설명합니다. 캐시는 보통 **5~10분 비활성 시 정리**, 최대 1시간 내 제거 같은 TTL 성격을 가집니다.[^2]  
- Anthropic은 prompt caching을 공식적으로 제공하며, 캐시 read가 **base input 대비 매우 저렴(예: 10%)**, 대신 캐시 “write(creation)”에 **할증**이 붙는 구조를 명시합니다(공식 블로그/문서).[^3]

**구조/흐름(중요):**
1. 요청을 **[고정 prefix] + [변동 suffix]** 로 나눈다.
2. 고정 prefix 끝에 **cache breakpoint**(Anthropic의 cache_control 같은 개념)를 둔다.[^4]
3. 다음 요청에서 prefix가 **바이트/토큰 수준으로 완전 동일**하면 cache hit:
   - hit된 토큰은 **cache read price**
   - 새로 추가된 suffix만 정상 input price

**다른 접근과 차이**
- “프롬프트를 짧게 쓰자”는 최적화는 한계가 있음(기능/품질을 깎기 쉬움).
- Prompt caching은 **품질을 유지한 채** 중복 prefill을 줄이는 방식.
- 단, **prefix 100% 동일성**이 핵심이라 “timestamp/req id/정렬 변경/툴 정의 순서 변경” 같은 사소한 변화가 비용을 폭발시킬 수 있음(실무에서 가장 흔한 함정). 이 포인트는 최근 prompt caching break-even 분석에서도 강조됩니다.[^5]

### 2) Semantic Cache: “의미적으로 같은 질문”은 답을 재사용
Prompt caching이 “동일 prefix”라면, semantic cache는 “**유사 질의**”를 묶어 **응답 자체**를 재사용합니다. 2026년에는 semantic caching을 “이론/보장/온라인 적응” 관점에서 다루는 연구도 많이 나왔습니다(연속 의미공간에서의 캐시 최적화, 온라인 학습 기반 eviction 등).[^6]

실무 관점에서 semantic cache는 보통:
- key: embedding(query) + (정규화된 컨텍스트 fingerprint)
- value: final answer + (근거/출처/버전) + (안전성 메타데이터)
- gate: 유사도 임계값 + “드리프트 검사”(문서 버전, 최신성 요구 여부)

RAG에서는 특히 “문서가 바뀌었는데 캐시된 답을 재사용”하면 사고가 납니다. 그래서 **RAG용 캐시 재사용 안전성**을 다루는 연구(grounded cache routing)처럼 “재사용해도 되는지”를 판단하는 레이어가 필요합니다.[^7]

### 3) Model Routing/Cascade: “싼 모델로 먼저, 어려울 때만 비싼 모델”
Routing은 간단히 말해:
- **cheap model**로 먼저 시도
- 실패(불확실/규칙 위반/근거 부족/품질 낮음)일 때만 **expensive model**로 escalation

핵심은 “실패 판정”을 **토큰을 많이 쓰지 않고** 해야 합니다. 그래서 실무에서는 아래 2단이 흔합니다.
- 1차: 규칙 기반(입력 길이, 금칙어, required citations 여부, tool 필요 여부)
- 2차: 저렴한 judge model / logit 기반 uncertainty / self-check(짧게)

이때 prompt caching이 붙으면, expensive model로 escalte 하더라도 **공통 prefix는 캐시로 싸게** 들어가므로 “2번 불러서 손해”가 줄어듭니다.

---

## 💻 실전 코드
아래는 **(A) Prompt caching을 깨지 않게 프롬프트를 구성**하고, **(B) Semantic cache로 응답 재사용**, **(C) Cascade routing(cheap → expensive)** 을 한 서비스에서 같이 운영하는 예제입니다. (FastAPI 기준, Redis 사용)

### 0) 의존성/환경
```bash
pip install fastapi uvicorn redis pydantic numpy
# (실제 OpenAI/Anthropic/Gemini SDK는 조직 표준에 맞게 추가)
```

### 1) 서버 코드: 캐시 친화 prompt + semantic cache + routing
```python
# app.py
import os, json, time, hashlib
from typing import Optional, Dict, Any, Tuple
import numpy as np
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

# ---- (1) Prompt prefix를 "완전히 고정"시키기 위한 설계 ----
# 절대 매 요청마다 바뀌는 값(시간, request_id, 실시간 카운터)을 prefix에 넣지 말 것.
SYSTEM_PREFIX = """You are a production assistant.
Follow policy:
- Output must be JSON with keys: answer, citations, confidence
- If unsure, set confidence <= 0.6 and include "needs_review": true
Tool schema:
- search_docs(query: string) -> {docs:[{id,title,body,version}]}
- fetch_doc(id: string) -> {id,title,body,version}
"""
# Anthropic를 쓴다면 cache_control breakpoint를 SYSTEM_PREFIX 마지막에 두는 식으로 설계.
# OpenAI는 "가장 긴 prefix 캐시"라서 동일 prefix 유지가 핵심.[^2]

def stable_fingerprint(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

PREFIX_FP = stable_fingerprint(SYSTEM_PREFIX)

# ---- (2) Semantic cache: embedding은 예제에서 더미(실무에선 provider embedding 모델 사용) ----
def cheap_embedding(text: str, dim: int = 256) -> np.ndarray:
    # toy가 아니라 "구조"를 보여주기 위한 더미. 실무에서는 임베딩 API/로컬 모델로 교체.
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec = np.frombuffer(h * (dim // len(h) + 1), dtype=np.uint8)[:dim].astype(np.float32)
    vec = (vec - vec.mean()) / (vec.std() + 1e-6)
    return vec

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

def semantic_cache_get(keyspace: str, query: str, threshold: float = 0.92) -> Optional[Dict[str, Any]]:
    qv = cheap_embedding(query)
    # 최근 N개만 스캔(운영에선 ANN 인덱스/벡터DB 권장)
    ids = r.lrange(f"sc:{keyspace}:ids", 0, 200)
    best: Tuple[float, Optional[str]] = (0.0, None)
    for cid in ids:
        item = r.get(f"sc:{keyspace}:item:{cid}")
        if not item:
            continue
        obj = json.loads(item)
        sv = np.array(obj["emb"], dtype=np.float32)
        sim = cosine(qv, sv)
        if sim > best[0]:
            best = (sim, cid)
    if best[1] and best[0] >= threshold:
        hit = json.loads(r.get(f"sc:{keyspace}:item:{best[1]}"))
        hit["semantic_similarity"] = best[0]
        return hit
    return None

def semantic_cache_put(keyspace: str, query: str, answer_obj: Dict[str, Any], ttl_sec: int = 3600):
    cid = hashlib.md5(f"{keyspace}:{query}".encode("utf-8")).hexdigest()
    obj = {
        "query": query,
        "emb": cheap_embedding(query).astype(float).tolist(),
        "answer": answer_obj,
        "created_at": int(time.time()),
        "prefix_fp": PREFIX_FP,
        "doc_version": answer_obj.get("doc_version"),
    }
    r.setex(f"sc:{keyspace}:item:{cid}", ttl_sec, json.dumps(obj))
    r.lpush(f"sc:{keyspace}:ids", cid)
    r.ltrim(f"sc:{keyspace}:ids", 0, 500)

# ---- (3) Routing/Cascade ----
class AskReq(BaseModel):
    user_id: str
    query: str
    require_fresh: bool = False     # 최신성 중요하면 semantic cache를 제한
    max_cost_tier: str = "standard" # "low" | "standard" | "high"
    doc_version: Optional[str] = None

def choose_route(req: AskReq) -> str:
    # 규칙 기반 1차 라우팅
    q = req.query.lower()
    if req.require_fresh or "today" in q or "latest" in q:
        return "expensive"  # 최신성 필요: 캐시 재사용 보수적
    if len(req.query) < 120 and req.max_cost_tier == "low":
        return "cheap"
    if "refactor" in q or "security" in q or "migration" in q:
        return "expensive"
    return "cheap"

# ---- (4) Provider 호출부(여기서는 형태만; 실무에선 SDK 붙이기) ----
def call_llm(provider_model: str, system_prefix: str, user_query: str) -> Dict[str, Any]:
    # 실제로는 OpenAI/Anthropic/Gemini Responses API 호출 + usage에서 cached_tokens 관측.
    # OpenAI는 usage에 cached_tokens가 포함됨.[^2]
    # Anthropic도 cache read/write token이 과금에 직접 반영됨.[^4]
    # 예제 응답:
    return {
        "answer": f"[{provider_model}] {user_query} 에 대한 응답(예시)",
        "citations": [],
        "confidence": 0.72 if provider_model == "cheap-model" else 0.86,
        "needs_review": False,
        "doc_version": "v2026-08-01"
    }

@app.post("/ask")
def ask(req: AskReq):
    keyspace = f"{req.user_id}:{req.doc_version or 'default'}"

    # (A) semantic cache 우선 (최신성 요구/버전 불일치면 패스)
    if not req.require_fresh:
        hit = semantic_cache_get(keyspace, req.query)
        if hit and (not req.doc_version or hit.get("doc_version") == req.doc_version):
            return {
                "route": "semantic_cache",
                "prefix_fp": PREFIX_FP,
                "semantic_similarity": hit["semantic_similarity"],
                "result": hit["answer"]
            }

    # (B) 모델 라우팅
    route = choose_route(req)
    if route == "cheap":
        result = call_llm("cheap-model", SYSTEM_PREFIX, req.query)
        # cheap 결과가 애매하면 escalation (짧은 judge 로직; 여기선 confidence로 대체)
        if result.get("confidence", 0) < 0.75:
            result = call_llm("expensive-model", SYSTEM_PREFIX, req.query)
            route = "cascade_escalated"
    else:
        result = call_llm("expensive-model", SYSTEM_PREFIX, req.query)

    # (C) semantic cache 저장 (confidence 낮거나 최신성 요구면 저장하지 않는 정책도 가능)
    if not req.require_fresh and result.get("confidence", 0) >= 0.75:
        semantic_cache_put(keyspace, req.query, result, ttl_sec=3600)

    return {
        "route": route,
        "prefix_fp": PREFIX_FP,
        "result": result
    }
```

### 2) 실행/예상 출력
```bash
uvicorn app:app --reload --port 8000
curl -s localhost:8000/ask -H "Content-Type: application/json" -d '{
  "user_id":"team-a",
  "query":"우리 서비스에서 tool schema가 길어서 토큰이 많이 듭니다. prompt caching을 깨지 않게 구성하는 규칙을 정리해줘",
  "require_fresh": false,
  "max_cost_tier":"standard",
  "doc_version":"v2026-08-01"
}' | jq
```

예상 출력(요지):
- 첫 요청: `route`가 `cheap` 또는 `cascade_escalated`
- 같은 query 재요청: `route`가 `semantic_cache`
- 실제 운영에서는 provider usage에서 `cached_tokens`(OpenAI) 또는 cache read/write 토큰(Anthropic)을 **메트릭으로 수집**해 캐시 효율을 관측해야 합니다.[^2]

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “캐시 가능한 prefix”를 설계 문서로 고정하라
Prompt caching은 **동일 prefix**가 생명입니다.
- system prompt / policy / tool schema는 **정렬·공백·키 순서까지** 고정(코드로 생성하지 말고, 생성한다면 canonicalization 강제)
- prefix에 timestamp, request id, 실시간 feature flag를 넣지 말 것  
실측에서도 “prefix 상단에 동적 문자열 1줄”이 캐시 적중률을 거의 0으로 떨어뜨릴 수 있다고 보고됩니다.[^5]

### Best Practice 2) 캐시는 “비용”도 만든다: write surcharge / TTL을 감안한 break-even
Anthropic은 cache write에 할증, read에 큰 할인 같은 **비대칭 가격 구조**를 문서/가격표로 명확히 둡니다.[^3]  
즉, “캐시를 만들었는데 TTL 안에 재사용을 못하면” 손해가 납니다.
- **긴 세션/반복 호출**(agent loop)에는 극도로 유리
- **원샷 요청**이 대부분이면 오히려 불리할 수 있음

### Best Practice 3) Routing은 “판정 비용”이 전체 최적화를 망친다
routing/판정에 비싼 모델을 쓰면 본말전도입니다.
- 1차 규칙 기반 + 2차 저렴 judge(또는 간단 self-check)로 끝내기
- escalation 기준은 “정확도”뿐 아니라 **출력 토큰 폭발 방지**(요약/형식 강제)도 포함

### 흔한 함정/안티패턴
- **대화 중간에 tool schema를 바꾸는 UX**: prefix가 바뀌어 캐시가 깨지고, 다음 턴부터 갑자기 비용이 폭증
- semantic cache에 “근거/버전” 없이 텍스트만 저장: RAG 드리프트에서 사고
- 캐시 hit/miss를 “비용”이 아니라 “에러”만으로 모니터링: 캐싱이 깨져도 서비스는 정상이라 탐지가 늦음  
(OpenAI/Anthropic 모두 usage에 캐시 관련 토큰이 나오므로, **cached_tokens 비율 알람**을 반드시 두는 게 좋습니다.)[^2]

비용/성능/안정성 트레이드오프(현실 결론)
- Prompt caching: **품질 유지 + 비용/지연 감소**(대신 prefix 안정성 강제)
- Semantic cache: **가장 큰 비용 절감 잠재력**(대신 안전장치/드리프트 대응 필요)
- Routing/Cascade: **비싼 모델 호출 횟수 자체를 줄임**(대신 판정 로직이 복잡, 실패 모드 설계 필요)

---

## 🚀 마무리
2026년 8월 시점의 LLM 비용 최적화는 “프롬프트를 조금 줄이는” 정도로는 체감이 약합니다. 실무에서 효과가 큰 순서는 보통:
1) **Prompt Caching이 잘 먹는 구조로 시스템을 재설계**(고정 prefix/캐시 브레이크포인트/동적 요소 격리)[^2]  
2) **Semantic Cache + (RAG라면) 재사용 안전성 게이트**[^7]  
3) **Routing/Cascade로 expensive model 호출을 최소화**

도입 판단 기준(체크리스트)
- “반복 prefix”가 평균 입력의 30% 이상인가?
- 동일한 업무 유형이 반복되는가(FAQ/운영/에이전트 루프)?
- 캐시 hit/miss를 **토큰 단위로 관측**할 준비(usage 수집/대시보드/알람)가 되어 있는가?

다음 학습 추천
- 각 provider의 prompt caching 동작/가격(특히 TTL, write/read 단가, usage 필드)을 먼저 정확히 읽고(OpenAI/Anthropic 공식)[^2]  
- RAG를 운영한다면 “cache reuse safety” 계열(grounded cache routing)로 드리프트/환각 리스크를 통제하는 쪽을 같이 보세요.[^7]

[^1]: <https://ai.google.dev/gemini-api/docs/pricing?hl=en>
[^2]: <https://openai.com/index/api-prompt-caching/>
[^3]: <https://claude.com/blog/prompt-caching?trk=public_post_comment-text>
[^4]: <https://platform.claude.com/docs/en/build-with-claude/prompt-caching?38d7aa68_page=1&70039c34_page=2&fcdaa149_sort_date=desc>
[^5]: <https://www.digitalocean.com/community/tutorials/prompt-caching-cost-break-even>
[^6]: <https://arxiv.org/abs/2604.20021>
[^7]: <https://arxiv.org/abs/2605.27494>
