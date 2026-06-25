---
title: "BM25+Vector+RRF로 “안정적으로” 이기는 법: 2026년형 Hybrid Search 랭킹 병합 실전 가이드"
date: 2026-06-25 04:13:52 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-06]
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
RAG 시스템을 운영해보면 “semantic search만으로는” 자꾸 빈틈이 드러납니다. 대표적으로:

- 사용자 쿼리가 **정확한 토큰(제품명/에러코드/약어/버전/정책 코드)** 중심일 때 → vector가 놓치거나 엉뚱한 유사문서를 끌어옴
- 반대로 쿼리가 **의도/의미 중심(자연어)** 일 때 → BM25가 동의어/패러프레이즈를 못 따라감
- 그리고 가장 골치 아픈 건, 배포 후에 **랭킹이 미세하게 흔들리며 “일관성”이 깨지는 문제**(LLM 응답 품질이 체감상 급락)

그래서 2026년 현재, 프로덕션 RAG에서 “기본값”에 가까워진 형태가 **Hybrid Retrieval(BM25 + dense vector) + (필요 시) reranking**입니다. 특히 서로 다른 스코어 스케일을 섞을 때 **score normalization보다 rank-based fusion인 RRF(Reciprocal Rank Fusion)**가 안정적으로 쓰이는 흐름이 강합니다. ([infoq.com](https://www.infoq.com/articles/vector-search-hybrid-retrieval-rag/?utm_source=openai))

언제 쓰면 좋나?
- 질의가 **키워드형/의미형이 섞여** 들어오고, “누락(Recall)”이 치명적인 RAG
- 사내 문서/티켓/런북처럼 **정확한 문자열 매칭이 의미를 갖는** 코퍼스
- 검색 품질을 실험으로 계속 올릴 계획이 있는 팀(평가 셋/로그 기반 튜닝)

언제 쓰면 안 되나?
- 데이터가 너무 작고(수백~수천 문서), 질의도 단순해서 **BM25 단독**으로도 충분할 때
- latency 예산이 빡빡하고(예: p95 50ms), 인프라 여유가 없는데 **두 검색을 병렬**로 돌려야 할 때
- “검색”이 아니라 “정확한 필터링/룩업”이 본질인 서비스(이 경우 DB/SQL이 우선)

---

## 🔧 핵심 개념
### 1) Hybrid Search의 본질: “두 개의 리콜 엔진” + “한 개의 병합 정책”
- **BM25(lexical/sparse)**: inverted index 기반. 토큰 단위로 강력한 precision/설명가능성.
- **Dense vector(semantic)**: embedding 공간에서 ANN(k-NN, HNSW 등)으로 의미 기반 recall.
- 문제: **BM25 score와 vector score는 스케일이 다르다** → 단순 가중합이 생각보다 깨지기 쉽다. 그래서 병합이 핵심. ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))

### 2) RRF(Reciprocal Rank Fusion): “점수”가 아니라 “순위”를 합친다
RRF는 각 검색 결과 리스트에서 문서의 rank를 기반으로 점수를 줍니다.

- 각 리스트 i에서 문서 d의 rank가 `rank_i(d)`라면  
  `RRF(d) = Σ_i 1 / (k + rank_i(d))`
- k는 보통 50~60 근처로 잡아 상위 랭크에만 과도하게 쏠리지 않게 합니다.

왜 RRF가 하이브리드에 강하나?
- BM25와 vector가 만들어내는 score 분포가 달라도 **rank만 믿고 합치니 안정적**
- 한 쪽에서만 “압도적으로 큰 스코어”가 나와 전체를 집어삼키는 현상이 감소
- OpenSearch도 “스코어 정규화(min-max, L2) 대신 RRF가 더 안정적”이라는 맥락으로 하이브리드에 RRF를 밀고 있습니다. ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))

### 3) 2026년형 실전 파이프라인(권장)
많은 팀이 아래 구조로 수렴합니다:

1) **BM25 topN** (키워드 recall)
2) **Vector topN** (의미 recall)
3) **RRF로 후보 합치기** (topK 후보군 생성)
4) (옵션) **Cross-encoder rerank** (질의-문서 pairwise로 “정밀도” 올리기)
5) (옵션) **MMR/다양성** (중복 chunk 억제)

InfoQ도 “vector만으론 부족해서 hybrid+fusion이 필요”라는 방향으로 정리하고, OpenSearch는 hybrid query 및 RRF를 제품 기능으로 강화하는 흐름입니다. ([infoq.com](https://www.infoq.com/articles/vector-search-hybrid-retrieval-rag/?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “현실적인 RAG 운영”을 가정합니다.

- 코퍼스: 사내 런북/장애 티켓/설계 문서 chunk
- 요구: (1) 정확한 에러코드 매칭 (2) 자연어 질의 의미 매칭 (3) 결과 병합의 안정성
- 구현: **PostgreSQL + pgvector + BM25(tsvector)** 로 BM25와 vector를 각각 뽑고, 애플리케이션에서 **RRF fusion**  
  (Postgres는 운영에 강하고, 이미 많은 팀이 “vector + BM25 + RRF” 조합을 실제로 사용한다고 공유됩니다. ([reddit.com](https://www.reddit.com/r/Rag/comments/1rf7xf6/whats_your_experience_with_hybrid_retrieval/?utm_source=openai)))

### 0) 의존성/전제
- PostgreSQL 15+ 권장
- `pgvector` 확장 설치
- Python 3.11+

```bash
pip install psycopg[binary]==3.2.9 numpy==2.0.1
```

### 1) 스키마(문서 chunk + BM25 인덱스 + 벡터)
```sql
-- 확장
CREATE EXTENSION IF NOT EXISTS vector;

-- 문서 chunk 테이블
CREATE TABLE IF NOT EXISTS kb_chunks (
  id           bigserial PRIMARY KEY,
  doc_id       text NOT NULL,
  chunk_id     int  NOT NULL,
  title        text,
  body         text NOT NULL,
  -- 한국어면 별도 설정이 필요할 수 있으나, 여기서는 영어/혼합 코퍼스 가정
  body_tsv     tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(body,''))) STORED,
  embedding    vector(1024), -- 예: bge 계열/사내 임베딩 차원에 맞추기
  updated_at   timestamptz NOT NULL DEFAULT now()
);

-- BM25(FTS) 인덱스
CREATE INDEX IF NOT EXISTS kb_chunks_tsv_idx ON kb_chunks USING GIN (body_tsv);

-- Vector 인덱스(HNSW)
CREATE INDEX IF NOT EXISTS kb_chunks_hnsw_idx
ON kb_chunks USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 128);
```

### 2) 하이브리드 검색 + RRF 병합(프로덕션형)
포인트는 세 가지입니다.
- BM25와 vector를 **각각 topN으로 넉넉히** 뽑는다(예: 100)
- RRF로 합친 뒤 topK(예: 20)를 만들고
- 그 topK를 RAG context로 넘기거나, 필요 시 rerank한다

```python
import os
import numpy as np
import psycopg

DSN = os.environ["PG_DSN"]

def rrf_fuse(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """
    rankings: 여러 검색 결과에서 doc_id(여기서는 kb_chunks.id)의 순서 리스트
    return: id -> rrf_score
    """
    scores: dict[int, float] = {}
    for r in rankings:
        for idx, doc_id in enumerate(r, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + idx)
    return scores

def search_bm25(cur, query: str, topn: int = 100) -> list[int]:
    cur.execute(
        """
        SELECT id
        FROM kb_chunks
        WHERE body_tsv @@ websearch_to_tsquery('english', %s)
        ORDER BY ts_rank_cd(body_tsv, websearch_to_tsquery('english', %s)) DESC
        LIMIT %s
        """,
        (query, query, topn),
    )
    return [row[0] for row in cur.fetchall()]

def search_vector(cur, embedding: np.ndarray, topn: int = 100) -> list[int]:
    # pgvector는 python list로 넘겨도 동작
    cur.execute(
        """
        SELECT id
        FROM kb_chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (embedding.tolist(), topn),
    )
    return [row[0] for row in cur.fetchall()]

def fetch_chunks(cur, ids: list[int]) -> list[dict]:
    cur.execute(
        """
        SELECT id, doc_id, chunk_id, title, body
        FROM kb_chunks
        WHERE id = ANY(%s)
        """,
        (ids,),
    )
    rows = cur.fetchall()
    by_id = {r[0]: r for r in rows}
    out = []
    for i in ids:
        r = by_id.get(i)
        if not r:
            continue
        out.append({"id": r[0], "doc_id": r[1], "chunk_id": r[2], "title": r[3], "body": r[4]})
    return out

def hybrid_search(query: str, query_embedding: np.ndarray, topn_each: int = 100, topk: int = 20):
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            bm25_ids = search_bm25(cur, query, topn=topn_each)
            vec_ids = search_vector(cur, query_embedding, topn=topn_each)

            fused = rrf_fuse([bm25_ids, vec_ids], k=60)
            # RRF 점수 내림차순으로 topk
            top_ids = [doc_id for doc_id, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)[:topk]]

            chunks = fetch_chunks(cur, top_ids)
            return chunks

if __name__ == "__main__":
    # 예시: "EKS node disk pressure evicted pods" 같은 운영 질의
    q = "EKS DiskPressure evicted pods kubelet log location"
    # 실제로는 embedding 모델 호출 결과를 넣어야 함(예: OpenAI/사내 모델)
    fake_emb = np.random.randn(1024).astype(np.float32)
    fake_emb = fake_emb / np.linalg.norm(fake_emb)

    results = hybrid_search(q, fake_emb)
    print(f"top{len(results)} chunks:")
    for r in results[:5]:
        print("-", r["doc_id"], r["chunk_id"], (r["title"] or "")[:60])
```

예상 출력(형태)
- top20 chunks가 나오고, 상위에는
  - BM25가 강한 “DiskPressure”, “evicted”, “kubelet” 같은 토큰 정확 매칭 문서
  - vector가 강한 “노드 디스크 부족 → eviction” 의미권 문서
  가 섞여 들어오는 게 정상입니다.

확장(2단계 빌드업)
- topK 결과에 대해 cross-encoder reranker(예: bge-reranker 계열)를 붙이면, 하이브리드의 recall을 유지하면서 precision을 크게 올리는 패턴이 논문/실전 보고에서 반복됩니다. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “Fusion 전에 topN을 넉넉히” 잡아라
RRF는 순위 기반이라, 애초에 각 후보 리스트에 문서가 **등장하지 않으면** 절대 올라오지 않습니다.  
보통 `topN_each=50~200`을 두고 latency/비용을 보며 조정합니다. (코퍼스가 크고 ANN이 빠르면 200도 가능)

### Best Practice 2) RRF의 k는 “안정성 레버”
- k가 너무 작으면 1~3위에 과도하게 쏠려, 한 쪽 엔진의 편향이 다시 커질 수 있습니다.
- k를 50~60 근처로 두는 레시피가 널리 쓰이고(OpenSearch도 RRF를 하이브리드 안정화로 소개), 운영에서 튜닝 포인트가 됩니다. ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))

### Best Practice 3) “언제 rerank할지”를 정해 비용을 통제
cross-encoder rerank는 효과가 좋지만 비쌉니다. 2026년 실전 가이드는 “항상 rerank”보다:
- (a) fused topK의 점수/엔트로피가 애매할 때만 rerank
- (b) 특정 카테고리 질의(정책/결제/보안)만 rerank
처럼 **조건부 rerank**로 가는 사례가 많습니다. ([aitechconnect.in](https://aitechconnect.in/tips/production-rag-hybrid-retrieval-guide-2026?utm_source=openai))

### 흔한 함정/안티패턴
- **스코어를 억지로 min-max로 맞춘 뒤 weighted sum**: 데이터 분포가 바뀌면(신규 문서/배포/인덱스 튜닝) 랭킹이 미세하게 출렁일 수 있음. RRF가 선호되는 이유가 여기 있습니다. ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))
- **chunk 품질 무시**: 하이브리드/병합은 “retrieval”을 개선할 뿐, 잘못 쪼갠 chunk(너무 길거나, 헤더/코드/표가 섞여 의미가 흐림)는 그대로 망가진 context로 들어갑니다.
- **Hybrid와 sort/rescore 조합 제약 미확인**: 엔진(OpenSearch 등)별로 hybrid query에서 rescore/sort 조합 제약이 있습니다. 운영 전 반드시 확인해야 합니다. ([docs.opensearch.org](https://docs.opensearch.org/latest/query-dsl/compound/hybrid/?utm_source=openai))

### 비용/성능/안정성 트레이드오프(결정 기준)
- BM25는 CPU/디스크 친화적, vector ANN은 메모리/CPU(또는 GPU) 부담이 큼
- 반대로 vector는 의미 recall을 크게 올리지만, exact token precision이 약해 “환각 방지”에 불리해질 수 있음  
→ 그래서 BM25를 버리기보다 **BM25를 안전장치로 유지**하는 구성이 2026년에도 유효합니다. ([infoq.com](https://www.infoq.com/articles/vector-search-hybrid-retrieval-rag/?utm_source=openai))
- OpenSearch는 dense뿐 아니라 **neural sparse(역색인 기반 sparse embedding)** 같은 대안도 밀고 있고, dense+neural sparse를 hybrid로 섞는 방향도 현실적인 선택지입니다(특히 비용/지연이 민감하면). ([docs.opensearch.org](https://docs.opensearch.org/latest/vector-search/ai-search/neural-sparse-search/?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 6월 기준으로 “프로덕션 RAG의 하이브리드 검색”은 다음 결론에 수렴합니다.

- BM25와 dense vector는 **서로의 실패 모드를 상쇄**한다.
- 병합은 score-based보다 **RRF 같은 rank-based fusion이 안정적**인 경우가 많다. ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))
- 최종 품질은 (Hybrid + Fusion)만으로 끝나지 않고, 필요 시 **cross-encoder rerank**로 마무리하는 2-stage/3-stage가 강력하다. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))

도입 판단 기준(현실적인 체크리스트)
1) 우리 쿼리에 **에러코드/약어/정확 문자열**이 자주 등장하는가? → Yes면 BM25 필수
2) 동의어/표현 다양성이 큰가? → Yes면 vector 필수
3) “스코어 튜닝”에 자신이 없는가/랭킹 흔들림이 싫은가? → RRF 우선
4) p95 latency/비용 예산이 낮은가? → topN을 줄이고, rerank는 조건부로

다음 학습 추천
- OpenSearch의 hybrid query와 RRF 동작/제약(운영 시 중요) ([docs.opensearch.org](https://docs.opensearch.org/latest/query-dsl/compound/hybrid/?utm_source=openai))
- neural sparse(희소 임베딩) + dense의 조합(비용 대비 효율 관점) ([docs.opensearch.org](https://docs.opensearch.org/latest/vector-search/ai-search/neural-sparse-search/?utm_source=openai))
- 하이브리드+rerank가 실제로 single-stage를 이긴다는 최근 벤치마크 흐름 ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))