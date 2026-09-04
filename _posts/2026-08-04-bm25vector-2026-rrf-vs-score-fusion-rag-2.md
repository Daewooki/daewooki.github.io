---
title: "BM25+Vector 하이브리드 검색, 2026년형 “랭킹 병합” 실전 가이드: RRF vs Score Fusion, 그리고 RAG에 먹이는 법"
description: "RAG 품질이 흔히 무너지는 지점은 “LLM”이 아니라 retrieval입니다. 특히 운영 환경에서는 다음 두 부류의 질의가 섞입니다."
date: 2026-08-04 03:23:14 +0900
categories: [AI, RAG]
tags: [ai, rag]
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
RAG 품질이 흔히 무너지는 지점은 “LLM”이 아니라 **retrieval**입니다. 특히 운영 환경에서는 다음 두 부류의 질의가 섞입니다.

- **정확 매칭이 중요한 질의**: 에러 메시지, API 이름, 제품 SKU, 정책 문구, 버전/숫자 조건 → BM25가 강함
- **의미 기반 탐색이 중요한 질의**: 표현이 바뀌거나 동의어/요약이 많은 질문 → vector search(embeddings)가 강함

문제는 둘 중 하나만 고르면 반대 케이스에서 바로 리콜/정확도가 깨진다는 점이고, 그래서 2026년에도 “**hybrid search(BM25 + vector)**”가 사실상 RAG의 기본 옵션으로 자리 잡았습니다. 다만 “둘을 같이 돌리면 좋아진다”는 말은 절반만 맞습니다. 실제로는 **랭킹 병합(fusion) 전략**을 잘못 잡으면 하이브리드가 오히려 성능을 떨어뜨리거나(쿼리/코퍼스 특성), 디버깅이 매우 어려워집니다(스코어 스케일 불일치). 운영 사례에서도 “hybrid+rerank가 오히려 악화”된 보고가 꾸준히 나옵니다.[^1]

**언제 쓰면 좋은가**
- 질의 분포가 “정확 키워드”와 “의미 검색”을 모두 포함하고, 단일 방식으로는 coverage가 부족할 때
- 동일 문서가 여러 표현으로 언급되며, 사용자 질의가 길거나(자연어) 짧거나(키워드) 양극단이 공존할 때
- RAG에서 top-k evidence를 안정적으로 확보해야 할 때(특히 Recall@k가 중요한 파이프라인)

**언제 쓰면 안 되는가(혹은 보수적으로)**
- 코퍼스가 작고(예: 수천 문서) 질의가 정형화되어 BM25만으로 충분할 때
- 숫자/코드/정확 문구가 압도적으로 중요할 때: 이 경우 dense가 노이즈를 섞을 수 있음(최근 연구에서도 “BM25가 dense를 이기는 문서군”이 명확히 보고됨).[^2]
- eval 없이 “hybrid + reranker”를 만능 처방처럼 붙일 때(데이터에 따라 실제로 악화 가능).[^1]

---

## 🔧 핵심 개념
### 1) 왜 BM25와 vector를 “그냥 더하면” 안 되나
BM25 점수와 vector similarity 점수는 **스케일이 구조적으로 다릅니다**. vector는 대체로 0~1 근처(혹은 cosine/inner product 기반의 좁은 범위), BM25는 코퍼스/쿼리 길이에 따라 훨씬 큰 값과 heavy-tail 분포가 나옵니다. 그래서 단순 가중합은 한쪽이 쉽게 지배합니다. MongoDB 문서도 이 스케일 차이를 하이브리드의 핵심 문제로 직접 언급합니다.[^3]

결국 병합은 크게 두 계열로 나뉩니다.

### 2) Score fusion (정규화 후 가중합)
- 각 retriever의 score를 min-max, z-score, L2 등으로 **정규화**한 뒤 가중합/평균
- 장점: “BM25 0.7 : vector 0.3” 같은 **해석 가능한 튜닝**이 가능
- 단점: outlier/분포 변동에 취약. 코퍼스가 커지거나 질의 타입이 바뀌면 정규화가 흔들림

OpenSearch도 score-based와 rank-based를 모두 소개하면서, 점수 분포가 이질적이거나 outlier가 있을 때는 rank fusion이 유리하다고 정리합니다.[^4]

### 3) Rank fusion: RRF(Reciprocal Rank Fusion)
2025~2026년 사이 실무/매니지드 검색에서 “기본값”으로 굳어가는 흐름이 **RRF**입니다. 이유는 간단합니다.

- 서로 스케일이 다른 점수를 억지로 맞추지 않고,
- 각 결과의 **순위(rank)** 만으로 합산해,
- 여러 retriever에서 “꾸준히 상위권”인 문서를 끌어올립니다.

RRF의 직관은 다음입니다.

- 각 검색 결과에서 문서의 랭크가 r이면 기여도는 `1 / (k + r)`
- k(상수)는 상위 랭크에 과도하게 쏠리지 않게 “완충” 역할을 합니다.
- MongoDB는 `$rankFusion`에서 rank_constant가 60으로 동작한다고 명시합니다.[^3]

Azure AI Search도 hybrid에서 병합이 필요한 이유(복수 쿼리 병렬 실행 후 “단일 결과” 필요)와 RRF 개념을 공식 문서로 정리합니다.[^5]  
OpenSearch는 Neural Search 플러그인에서 RRF를 hybrid에 도입하며 “점수 정규화의 고통”을 피하는 장점을 강조합니다.[^6]

### 4) RAG 관점의 “하이브리드 = 리콜 확보 장치”
RAG에서 하이브리드의 역할은 보통 이겁니다.

1) BM25로 “정답 근처 키워드”를 놓치지 않고
2) vector로 “표현이 달라도 의미가 같은 근거”를 확보한 뒤
3) (선택) reranker로 top-n을 정렬/정제

다만 연구/실무 보고 모두 공통으로 말하는 포인트는:  
**하이브리드는 리콜을 올리기 쉽지만, 최종 품질은 reranking/컨텍스트 구성/평가 설계에 좌우**된다는 점입니다. (산업 배치에서 fusion을 평가한 논문들도 “고정된 latency/budget” 조건에서 trade-off를 다룹니다.)[^7]

---

## 💻 실전 코드
아래는 “toy”가 아니라, **실제 RAG 서비스에서 흔한 형태**(PostgreSQL + pgvector + 별도 BM25 인덱스(Elasticsearch))를 가정한 예제입니다.

- 이유: 2026년에도 많은 팀이 **vector는 DB/pgvector**, **BM25는 Elasticsearch/OpenSearch**로 분리 운영합니다(마이그레이션 비용/리스크 때문).  
- 그리고 이 구조에서 제일 중요한 게 “**랭킹 병합을 애플리케이션에서 어떻게 안정적으로 하느냐**”입니다.

### 0) 의존성 / 환경
```bash
pip install fastapi uvicorn httpx numpy pydantic python-dotenv
```

환경 변수:
```bash
# .env
ELASTIC_URL=http://localhost:9200
ELASTIC_INDEX=kb_docs
PG_DSN=postgresql://rag:rag@localhost:5432/rag
EMBEDDING_MODEL=text-embedding-3-large   # 예시: 실제론 사내/외부 모델로 교체
TOPK_BRANCH=50
TOPK_FINAL=12
RRF_K=60
```

### 1) 핵심: RRF 병합 + “브랜치별 top-k 제한” + “디버깅 가능한 로그”
```python
# app.py
import os
import math
import asyncio
from typing import Dict, List, Tuple, Any
import httpx
import numpy as np
import psycopg2
from fastapi import FastAPI
from pydantic import BaseModel

ELASTIC_URL = os.environ["ELASTIC_URL"]
ELASTIC_INDEX = os.environ["ELASTIC_INDEX"]
PG_DSN = os.environ["PG_DSN"]

TOPK_BRANCH = int(os.getenv("TOPK_BRANCH", "50"))   # BM25 top-k, vector top-k 각각
TOPK_FINAL = int(os.getenv("TOPK_FINAL", "12"))     # RAG에 넣을 최종 top-k
RRF_K = int(os.getenv("RRF_K", "60"))

app = FastAPI()

class QueryReq(BaseModel):
    query: str
    filters: Dict[str, Any] | None = None  # 예: {"tenant_id": "t1", "lang": "ko"}

def rrf_fuse(rank_lists: List[List[str]], k: int = 60) -> List[Tuple[str, float]]:
    """
    rank_lists: 각 검색기의 결과를 doc_id 리스트로 전달 (0번이 1등)
    return: (doc_id, fused_score) 내림차순
    """
    scores: Dict[str, float] = {}
    for lst in rank_lists:
        for idx, doc_id in enumerate(lst):
            r = idx + 1
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + r)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

async def bm25_search(query: str, filters: Dict[str, Any] | None) -> List[str]:
    # Elasticsearch 예시 (OpenSearch도 거의 동일)
    must = [{"match": {"content": {"query": query}}}]
    flt = []
    if filters:
        for k, v in filters.items():
            flt.append({"term": {k: v}})
    q = {
        "size": TOPK_BRANCH,
        "_source": False,
        "query": {"bool": {"must": must, "filter": flt}},
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(f"{ELASTIC_URL}/{ELASTIC_INDEX}/_search", json=q)
        r.raise_for_status()
        hits = r.json()["hits"]["hits"]
        return [h["_id"] for h in hits]

def vector_search_pg(query_embedding: List[float], filters: Dict[str, Any] | None) -> List[str]:
    # pgvector (cosine distance) 예시: embedding 컬럼이 vector 타입이라고 가정
    where = []
    params = {"emb": query_embedding, "limit": TOPK_BRANCH}

    if filters:
        for i, (k, v) in enumerate(filters.items()):
            where.append(f"{k} = %({k})s")
            params[k] = v

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
      SELECT doc_id
      FROM documents
      {where_sql}
      ORDER BY embedding <=> %(emb)s
      LIMIT %(limit)s
    """
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [r[0] for r in rows]

async def embed(query: str) -> List[float]:
    # 실제 운영에서는 사내 임베딩 서비스/배치 모델을 호출
    # 여기서는 "이미 임베딩 API가 있다"는 전제로 인터페이스만 둠
    # (예: OpenAI/Bedrock/Cohere/사내 Triton 등)
    raise NotImplementedError("Connect your embedding service here")

def fetch_docs(doc_ids: List[str]) -> List[Dict[str, Any]]:
    # 실제로는 doc store에서 chunk 텍스트/메타데이터 로드
    sql = """
      SELECT doc_id, title, chunk_text, source, updated_at
      FROM doc_chunks
      WHERE doc_id = ANY(%(ids)s)
    """
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"ids": doc_ids})
            rows = cur.fetchall()
    return [
        {"doc_id": r[0], "title": r[1], "chunk_text": r[2], "source": r[3], "updated_at": r[4].isoformat()}
        for r in rows
    ]

@app.post("/retrieve")
async def retrieve(req: QueryReq):
    q = req.query
    filters = req.filters

    # 1) BM25와 vector를 "동시에" 실행 (latency 최적화의 기본)
    bm25_task = asyncio.create_task(bm25_search(q, filters))
    # embedding + pgvector 검색은 보통 직렬이므로(임베딩 필요),
    # 운영에서는 query embedding 캐시/semantic cache를 반드시 고려
    bm25_ids = await bm25_task

    # 여기서는 embed가 NotImplemented라서 실제 실행은 불가.
    # 여러분 환경에서는 embed(q) 구현 후 아래를 활성화.
    # q_emb = await embed(q)
    # vec_ids = await asyncio.to_thread(vector_search_pg, q_emb, filters)

    vec_ids = []  # 데모: 임베딩 연결 전

    # 2) RRF fuse (스코어 정규화 없이 랭크 기반으로)
    fused = rrf_fuse([bm25_ids, vec_ids], k=RRF_K)
    final_ids = [doc_id for doc_id, _ in fused[:TOPK_FINAL]]

    # 3) 컨텍스트 로드
    docs = fetch_docs(final_ids)

    return {
        "query": q,
        "filters": filters,
        "bm25_top": bm25_ids[:5],
        "vector_top": vec_ids[:5],
        "fused_top": fused[:10],
        "contexts": docs,
        "note": "vector branch disabled until embed() is connected"
    }
```

예상 출력(일부):
- `bm25_top`: 키워드 일치가 강한 문서 ID들이 먼저 보임
- `fused_top`: 두 브랜치에 모두 등장하거나 각각 상위권인 문서가 상단으로 섞여 올라옴
- `contexts`: RAG에 바로 넣을 chunk 텍스트 목록

### 2) 확장: “가중 RRF”로 쿼리 타입별 편향 주기
RRF는 기본적으로 retriever 간 가중치가 약합니다(랭크만 쓰기 때문). 하지만 운영에서는 아래처럼 “질의 타입 감지” 후 **브랜치 가중**을 주면 안정적인 경우가 많습니다.

- 에러 코드/파일명/ID 패턴이면 BM25 쪽 리스트의 점수에 weight를 곱함
- 질문형/요약형이면 vector 쪽 weight를 곱함

(코드에서는 `scores[doc_id] += weight * 1/(k+r)` 형태로 확장)

이 접근은 OpenSearch가 hybrid에서 weight 파라미터로 영향도를 조절하는 방식과 개념적으로 유사합니다.[^8]

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **브랜치별 top-k를 넉넉히, 최종 top-k는 작게**
   - RRF는 “순위”로 합치므로, 각 브랜치가 너무 얕으면(예: 10개) 서로 보완할 여지가 줄어듭니다.
   - 보통 `topk_branch=50~200`, `topk_final=8~20`로 시작해 eval로 조정합니다.

2) **공통 필터를 ‘양쪽’에 동일하게 적용**
   - tenant, ACL, language, time-range 같은 필터가 BM25와 vector에서 다르게 적용되면 “그럴듯하지만 권한 밖 문서”가 섞이거나, 병합 단계에서 문서 풀이 달라져 디버깅이 어려워집니다.
   - OpenSearch도 hybrid에서 common filter 지원을 강화하는 이유가 바로 이 운영 이슈입니다.[^9]

3) **eval을 “질의 타입별”로 쪼개서 보라**
   - 평균 점수 하나로 보면 hybrid가 좋아 보이는데, 실제로는 “정확 질의군”에서 악화되고 “의미 질의군”에서 개선되는 식의 상쇄가 흔합니다.
   - 최근 벤치마킹에서도 문서 도메인에 따라 BM25 우위가 뚜렷한 케이스가 보고됩니다.[^2]

### 흔한 함정 / 안티패턴
- **스코어 가중합을 하면서 정규화를 대충 처리**: 데이터가 바뀌면 튜닝이 무너짐(특히 outlier)
- **hybrid 뒤에 reranker를 무조건 붙이기**: reranker budget(문서 수)과 latency 제약 때문에, 오히려 “좋은 후보를 더 많이” 넣지 못해 성능이 떨어질 수 있습니다. 커뮤니티에서도 실제 악화 사례가 반복 보고됩니다.[^1]
- **vector search recall(ANN 파라미터) 미튜닝**: HNSW/IVF 설정이 낮으면 “애초에” 좋은 후보가 벡터 브랜치에서 안 올라옵니다. 이 상태에서 hybrid는 개선이 제한적입니다(ef_search, nprobe 같은 파라미터를 반드시 관찰).

### 비용/성능/안정성 트레이드오프
- RRF는 개념적으로 단순하지만, **두 검색을 병렬로 돌리면 비용은 2배**가 됩니다(인프라/쿼리 비용).
- 반대로 단일 엔진(예: OpenSearch/Azure/MongoDB 등)에서 native hybrid+RRF를 제공하면 “한 번의 요청”으로 줄어 latency/운영 복잡도가 낮아집니다. (Azure는 hybrid에서 RRF를 기본 랭킹 병합으로 설명)[^5]
- 최종적으로는 “품질 이득 vs 운영 단순성 vs 비용”의 삼각형에서 결정해야 합니다.

---

## 🚀 마무리
정리하면, 2026년 기준 hybrid search의 핵심은 “BM25와 vector를 같이 쓰자”가 아니라 **어떻게 병합하고, 어떤 질의에서 어느 쪽을 더 믿을지 결정하는 체계**입니다.

- 스코어 스케일 차이/분포 변동이 걱정되면 **RRF( rank fusion )**로 시작하는 게 안전합니다.[^6]
- 다만 hybrid는 만능이 아니고, 데이터에 따라 악화될 수 있으니 **질의군 분리 eval + reranker budget/latency 설계**가 필수입니다.[^1]
- 도입 판단 기준(실무 체크리스트):
  1) “정확 키워드 질의” 비중이 있는가? (있으면 BM25 유지/강화)
  2) “표현 다양성/요약 질의”가 많은가? (있으면 vector 필요)
  3) 두 질의군을 하나의 retriever로 커버하기 어렵다면 hybrid
  4) 병합은 RRF로 시작 → 필요 시 가중/쿼리 타입 기반으로 확장
  5) reranker는 “항상”이 아니라, 비용 대비 이득이 검증될 때만

다음 학습 추천:
- RRF 기반 hybrid의 공식 동작/파라미터 문서(Azure, OpenSearch, MongoDB)를 각각 읽고, **자기 서비스의 필터/ACL/latency 제약에 맞춰** 병합 설계를 고정시키는 것을 권합니다.[^5]

[^1]: <https://www.reddit.com/r/Rag/comments/1v7g3oe/hybrid_search_and_reranking_made_my_rag_worse/>
[^2]: <https://arxiv.org/abs/2604.01733>
[^3]: <https://www.mongodb.com/docs/vector-search/hybrid-search/hybrid-search-overview/>
[^4]: <https://opensearch.org/blog/building-effective-hybrid-search-in-opensearch-techniques-and-best-practices/>
[^5]: <https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking>
[^6]: <https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/>
[^7]: <https://arxiv.org/abs/2603.02153>
[^8]: <https://docs.opensearch.org/latest/ml-commons-plugin/api/agentic-memory-apis/hybrid-search-memory/>
[^9]: <https://opensearch.org/blog/introducing-common-filter-support-for-hybrid-search-queries/>
