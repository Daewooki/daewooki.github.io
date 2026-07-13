---
title: "2026년 7월 기준 RAG 고급 최적화: HyDE + Reranking + Query Expansion “3단 부스터”를 프로덕션에 제대로 꽂는 법"
date: 2026-07-13 03:40:36 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-07]
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
RAG 성능이 흔들릴 때 원인은 대부분 “LLM이 못해서”가 아니라 **retrieval 단계에서 답이 될 근거가 prompt에 들어오지 못해서**입니다. 특히 아래 같은 증상은 1-stage vector search만으로는 한계가 빨리 옵니다.

- 질문이 짧거나 모호해서 embedding이 빈약함(semantic gap)
- 도메인 용어/제품 코드/조항 번호처럼 **lexical match**가 중요한 데이터
- top-k를 늘리면 잡음이 늘어 hallucination/오답이 증가
- 같은 질문이라도 표현만 바뀌면 hit가 들쭉날쭉(robustness 문제)

이때 2026년 기준 실무에서 가장 “즉시” 성능을 올리기 쉬운 레버가 **HyDE(가상 문서 생성) / Reranking(2단계 정렬) / Query Expansion(다중 쿼리·재작성 + fusion)** 조합입니다. 다만 무조건 넣는다고 좋아지지 않습니다. 예를 들어 텍스트+표(수치) 문서에서 **정밀 수치 질의**는 HyDE나 multi-query가 이득이 제한적이라는 보고도 있습니다. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))

**언제 쓰면 좋나**
- 사용자 질문이 짧고, 문서가 길거나 서술형이며 “정답 근거가 문장 어딘가에 존재”하는 형태
- recall을 올려야 하는데 top-k 확대가 품질을 망칠 때(잡음 제어가 필요)
- hybrid(BM25+dense)까지 했는데도 최종 컨텍스트가 엇나갈 때

**언제 쓰면 안 되나(또는 제한적으로)**
- “정확한 숫자/표 계산/스펙 비교”처럼 **정밀 numeric QA** 중심(오히려 가상 문서가 편향을 만들 수 있음) ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))
- latency/비용 budget이 빡센 실시간 트래픽(특히 LLM reranker, 다중 쿼리 확장)
- 데이터가 너무 짧고 정규화되어 있어 BM25만으로도 충분한 경우

---

## 🔧 핵심 개념
여기서 다루는 3가지는 서로 역할이 다릅니다. “뭐가 더 좋냐”가 아니라 **어떤 실패 모드를 어떤 단계에서 잡느냐**로 봐야 합니다.

### 1) HyDE (Hypothetical Document Embeddings)
**정의**: 사용자의 짧은 query를 그대로 embedding하지 않고, LLM으로 “정답처럼 보이는 긴 가상 문서(hypothetical document)”를 생성한 뒤 그 문서를 embedding해 retrieval에 사용합니다. 핵심은 query embedding의 정보량 부족(semantic gap)을 “가상 문서로 부풀려” 문서 embedding 공간에 더 잘 매칭시키는 것입니다. ([arxiv.org](https://arxiv.org/abs/2507.16754?utm_source=openai))

**내부 흐름(중요)**
1. User query → LLM prompt로 “답변형 문서” 생성 (너무 창작하면 위험)
2. hypothetical doc → embed
3. vector search (또는 hybrid의 dense 쪽) 후보군 확장
4. 이후 reranking/필터링로 잡음 제거

**차이점**
- Query Expansion은 “다른 쿼리들”을 늘리는 방식이고,
- HyDE는 “쿼리는 1개지만 embedding 입력을 문서 수준으로 풍부화”합니다.

**주의**: HyDE는 “가상 답”을 만들기 때문에, 도메인에서 강한 편향/환각이 섞이면 retrieval이 그 편향 방향으로 끌릴 수 있습니다(그래서 보통 **reranking과 같이** 씁니다).

### 2) Reranking (Cross-Encoder / ColBERT / LLM Reranker)
**정의**: 1차 검색(cheap, high-recall) 결과 top-N을 받아서, query-document pair를 더 비싼 모델로 재채점해 top-k를 정밀하게 뽑는 2-stage 구조입니다. 2026년에도 “hybrid + neural reranking”이 단일 단계보다 강하다는 결과가 반복됩니다. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))

**왜 먹히나**
- bi-encoder(vector search)는 query/doc을 독립적으로 embedding해서 cosine 유사도를 보므로, 미세한 조건(예: “A는 포함하되 B는 제외”)을 잘 못 잡습니다.
- cross-encoder는 query와 passage를 **joint attention**으로 보며 relevance를 직접 학습/추론합니다. ([link.springer.com](https://link.springer.com/article/10.1007/s10791-026-10156-3?utm_source=openai))

**현실적 선택지**
- **Open-source cross-encoder(BGE 계열, MiniLM 등)**: 비용↓, 품질/도메인 적합성은 튜닝 여지
- **Hosted rerank API(Cohere 등)**: 운영 편의↑, 비용/데이터 거버넌스 이슈
- **LLM-based reranker**: 규칙 기반(“최신, 공식, 정책 우선”) 같은 정렬 정책을 넣기 쉬우나 비용/지연↑
- 최근에는 reranker를 “답 품질”에 직접 align하려는 RL 접근도 나옵니다(RRPO). ([arxiv.org](https://arxiv.org/abs/2604.02091?utm_source=openai))

### 3) Query Expansion / Multi-Query + Fusion(RRF)
**정의**: 한 번의 query로 못 찾는다면, LLM으로 **서로 다른 관점의 쿼리 여러 개**를 만들고 각각 검색한 뒤 결과를 합칩니다. RAG-Fusion은 대표적으로 multi-query + Reciprocal Rank Fusion(RRF)을 씁니다. ([arxiv.org](https://arxiv.org/abs/2402.03367?utm_source=openai))

**RRF가 실무에서 강한 이유**
- 검색 점수 스케일이 서로 다르거나(BM25 vs dense), 쿼리별 분포가 달라도 robust하게 합쳐줍니다.
- “여러 쿼리에서 반복적으로 상위에 뜨는 문서”를 올려주므로 안정성이 좋아집니다. ([arxiv.org](https://arxiv.org/abs/2402.03367?utm_source=openai))

**핵심 트레이드오프**
- recall은 대개 올라가지만, 후보가 커져서 reranking 비용이 증가 → 그래서 보통 **(multi-query → fusion → topN → rerank)** 순으로 설계합니다.

---

## 💻 실전 코드
아래는 “사내 기술 문서/운영 Runbook/장애 보고서” 같은 KB를 가정한, **HyDE + Multi-query(RRF) + Cross-Encoder Rerank** 파이프라인 예제입니다.  
(실제 운영에서는 Vector DB(Qdrant/Weaviate/Elastic)로 바꾸면 되고, 구조는 동일합니다.)

### 0) 의존성/환경
```bash
pip install -U qdrant-client sentence-transformers transformers torch openai
# OPENAI_API_KEY 환경변수 필요 (HyDE/쿼리 확장에 사용)
```

### 1) 인덱싱(현실적인 chunk + metadata)
```python
# rag_advanced.py
import os, re
from typing import List, Dict, Tuple
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from sentence_transformers import SentenceTransformer, CrossEncoder
from openai import OpenAI

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"   # 예시(교체 가능)
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"    # 가벼운 reranker 예시

client = QdrantClient(":memory:")  # 데모: 메모리. 운영: Qdrant 서버로 변경
embedder = SentenceTransformer(EMBED_MODEL)
reranker = CrossEncoder(RERANK_MODEL)
llm = OpenAI()

COLL = "kb"

def chunk_text(text: str, chunk_size=900, overlap=150) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i+chunk_size])
        i += chunk_size - overlap
    return out

def index_docs(docs: List[Dict]):
    # docs: [{"id": "...", "title":"...", "body":"...", "source":"confluence", "updated":"2026-06-01"}]
    vectors = 384  # all-MiniLM-L6-v2
    client.recreate_collection(
        collection_name=COLL,
        vectors_config=qm.VectorParams(size=vectors, distance=qm.Distance.COSINE),
    )

    points = []
    pid = 0
    for d in docs:
        chunks = chunk_text(d["body"])
        embs = embedder.encode(chunks, normalize_embeddings=True)
        for c, v in zip(chunks, embs):
            points.append(
                qm.PointStruct(
                    id=pid,
                    vector=v.tolist(),
                    payload={
                        "doc_id": d["id"],
                        "title": d["title"],
                        "chunk": c,
                        "source": d["source"],
                        "updated": d["updated"],
                    },
                )
            )
            pid += 1
    client.upsert(collection_name=COLL, points=points)
```

### 2) HyDE + Multi-query + RRF + Rerank 검색
```python
def chat(prompt: str, model: str = "gpt-4.1-mini") -> str:
    resp = llm.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

def hyde_generate(query: str) -> str:
    # "정답처럼 보이는 문서"를 만들되, 단정/창작을 줄이기 위해 조건을 건다
    prompt = f"""
너는 사내 기술 문서 검색용 assistant다.
아래 질문에 대해, 실제 문서에 있을 법한 '근거 중심' 설명을 8~12문장으로 작성하라.
- 모르는 내용은 단정하지 말고 '가능성'으로 표현
- 제품명/에러코드/설정키 등 키워드를 포함해 retrieval에 도움 되게 작성
질문: {query}
"""
    return chat(prompt)

def expand_queries(query: str) -> List[str]:
    prompt = f"""
아래 사용자 질문을 검색 성능을 위해 4개로 재작성하라.
각 재작성은 서로 다른 관점이어야 한다:
1) 키워드 중심
2) 증상/로그 중심
3) 원인/진단 중심
4) 설정/구성 중심
출력은 JSON 배열의 문자열만.
질문: {query}
"""
    txt = chat(prompt)
    # 매우 단순 파서(운영에선 JSON strict parsing + retry 권장)
    qs = re.findall(r'"(.*?)"', txt)
    return [query] + qs[:4]

def qdrant_search(text: str, top_n: int = 40) -> List[Tuple[int, float, Dict]]:
    v = embedder.encode([text], normalize_embeddings=True)[0].tolist()
    hits = client.search(collection_name=COLL, query_vector=v, limit=top_n)
    return [(h.id, h.score, h.payload) for h in hits]

def rrf_fuse(result_lists: List[List[Tuple[int, float, Dict]]], k: int = 60) -> List[Tuple[int, float, Dict]]:
    # RRF: score(doc)=sum(1/(k+rank))
    scores, payloads = {}, {}
    for lst in result_lists:
        for rank, (pid, _score, payload) in enumerate(lst, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
            payloads[pid] = payload
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(pid, s, payloads[pid]) for pid, s in fused]

def rerank(query: str, candidates: List[Tuple[int, float, Dict]], top_k: int = 8):
    pairs = [(query, c[2]["chunk"]) for c in candidates]
    rr_scores = reranker.predict(pairs)  # higher=better
    merged = []
    for (pid, _s, payload), rrs in zip(candidates, rr_scores):
        merged.append((pid, float(rrs), payload))
    merged.sort(key=lambda x: x[1], reverse=True)
    return merged[:top_k]

def retrieve(query: str):
    # 1) query expansion
    qs = expand_queries(query)

    # 2) HyDE 문서 생성(옵션): "원 질문"에만 적용해 비용 폭발 방지
    hyde_doc = hyde_generate(query)
    qs_for_retrieval = qs + [hyde_doc]

    # 3) 각 쿼리별 1차 검색 후 RRF로 fuse
    per = [qdrant_search(q, top_n=40) for q in qs_for_retrieval]
    fused = rrf_fuse(per, k=60)[:80]  # fused 후보를 너무 키우지 말 것

    # 4) rerank로 최종 컨텍스트 결정
    top = rerank(query, fused, top_k=8)
    return {"expanded_queries": qs, "hyde": hyde_doc, "top": top}

if __name__ == "__main__":
    docs = [
        {
            "id": "runbook-redis-timeout",
            "title": "Redis timeout 장애 대응",
            "body": "증상: latency spike... 원인: connection pool 고갈... 설정: maxclients...",
            "source": "confluence",
            "updated": "2026-06-01",
        },
        {
            "id": "guide-qdrant-scaling",
            "title": "Qdrant 운영 스케일링 가이드",
            "body": "HNSW 파라미터... ef_search 튜닝... 메모리 사용량...",
            "source": "notion",
            "updated": "2026-05-10",
        },
    ]
    index_docs(docs)

    q = "장애 때 Redis timeout이 나는데 원인 진단을 어떻게 해?"
    out = retrieve(q)

    print("Expanded queries:", out["expanded_queries"])
    print("\nHyDE doc (excerpt):", out["hyde"][:200], "...")
    print("\nTop contexts:")
    for i, (_, score, p) in enumerate(out["top"], 1):
        print(f"{i}. rerank={score:.3f} | {p['title']} | updated={p['updated']}")
```

**예상 출력(형태)**
- Expanded queries 5개(원본 + 4개)
- HyDE 문서 일부
- top contexts 8개: title/updated와 함께 rerank score가 높은 순으로 정렬

> 포인트: 여기서 성능 최적화의 핵심은 “후보군을 넓히는 단계(HyDE/Expansion)”와 “잡음을 줄이는 단계(Rerank)”를 분리하고, 비용 폭발을 막기 위해 **fuse 이후 rerank 대상 N을 강하게 캡**하는 것입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 적용)
1) **HyDE는 ‘전부’에 쓰지 말고, “빈약한 쿼리”에만 조건부로**
- query 길이/엔티티 수/과거 hit-rate로 gating 하세요. HyDE는 유효하지만 비용과 편향 리스크가 있습니다. ([arxiv.org](https://arxiv.org/abs/2507.16754?utm_source=openai))

2) **Multi-query는 3~5개가 sweet spot, 그리고 RRF로 합쳐라**
- 무작정 10개 만들면 recall은 오르지만 rerank 비용이 선형 증가합니다.
- RRF는 점수 스케일 문제를 덜어주고 안정성이 좋습니다. ([arxiv.org](https://arxiv.org/abs/2402.03367?utm_source=openai))

3) **Reranking은 “top-5면 의미 없음, top-50~200에서 효과”**
- 1차에서 너무 적게 뽑으면 reranker가 개선할 여지가 없습니다(실무 글들도 반복해서 강조). ([teachmeidea.com](https://teachmeidea.com/reranking-in-rag-cohere-cross-encoders/?utm_source=openai))

### 흔한 함정/안티패턴
- **HyDE 결과를 그대로 컨텍스트로 넣기**: HyDE는 검색용입니다. “가상 문서”를 LLM에 근거로 주면 환각이 정당화됩니다.
- **reranker를 맹신**: reranker는 “후보군 안에서”만 고릅니다. 후보군이 틀리면 아무것도 못 합니다.
- **정밀 수치 질의에 query expansion 남발**: 숫자/표 기반 질문은 확장이 오히려 산만해질 수 있고, 실제로 이득이 제한적이라는 결과가 있습니다. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))

### 비용/성능/안정성 트레이드오프(현실적 기준)
- latency budget이 2~3초라면:
  - Expansion: 3~4개 제한
  - HyDE: “cold query / 실패한 query”에만
  - Rerank: cross-encoder로 top-80 정도만
- 품질이 최우선(법무/리서치)이라면:
  - hybrid + (multi-query + RRF) + (강한 reranker 또는 LLM listwise) 조합이 자주 쓰입니다(최근 실무/정리 글에서도 이런 스택을 다룹니다). ([thread-transfer.com](https://thread-transfer.com/blog/2026-06-17-rag-reranking-llm-colbert/?utm_source=openai))
- 장기적으로는 “reranker를 답 품질에 맞게 align”하려는 연구도 나오고 있어, 단순 relevance를 넘어 end-to-end 최적화 방향을 염두에 둘 만합니다. ([arxiv.org](https://arxiv.org/abs/2604.02091?utm_source=openai))

---

## 🚀 마무리
HyDE / Reranking / Query Expansion은 각각 다른 실패 모드를 겨냥합니다.

- **HyDE**: 짧고 빈약한 query를 “문서 수준 의미”로 증폭해 recall을 끌어올림
- **Query Expansion + RRF**: 표현 다양성/관점 다양성으로 recall과 robustness 개선
- **Reranking**: 늘어난 후보군의 잡음을 정밀하게 제거해 최종 precision 확보

도입 판단 기준은 간단합니다.
1) 지금 오답의 원인이 “컨텍스트 미포함”이라면 → Expansion/HyDE부터  
2) “컨텍스트는 들어오는데 모델이 헛소리”가 아니라 “정답 chunk가 top-k에서 밀림”이라면 → Reranking 우선  
3) numeric/표 질의가 많다면 → HyDE/다중 확장은 gating하고 hybrid/BM25 비중 + rerank에 투자 ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))

다음 학습으로는 (1) hybrid retrieval 설계, (2) reranker 선택/튜닝 및 운영(평가·변경 감시), (3) query routing/observability를 추천합니다. 특히 2026년 연구/사례들은 “retriever–reranker 조합 선택”과 “reranker를 생성 품질에 align”하는 방향이 빠르게 늘고 있습니다. ([link.springer.com](https://link.springer.com/article/10.1007/s10791-026-10156-3?utm_source=openai))