---
title: "BM25+Vector 하이브리드 검색, 2026년 RAG의 “마지막 20%”를 채우는 랭킹 병합 전략 (RRF vs Weighted)"
date: 2026-05-26 04:15:44 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-05]
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
RAG에서 “답이 틀린” 이유의 상당수는 LLM이 아니라 **retrieval이 후보 문서를 잘못 뽑았기 때문**입니다. 특히 실무 문서(사내 위키/티켓/로그/정책/기술 문서)는 다음 두 종류의 질의가 섞입니다.

- **lexical 강한 질의**: 에러 코드, API/클래스명, 설정 키, 정확한 약어(예: `ERR_CONNECTION_RESET`, `x-amz-request-id`)
- **semantic 강한 질의**: 사용자가 자연어로 의도를 말하지만 문서 표현은 다를 때(동의어/우회 표현/설명형 문장)

BM25(또는 BM25F)는 전자에 강하고, vector search는 후자에 강합니다. 그래서 2026년의 “production RAG” 담론은 대부분 **하이브리드 검색(= BM25 + vector) + 랭킹 병합(fusion) + (가능하면) rerank**로 수렴했습니다. OpenSearch는 hybrid search 및 RRF 기반 rank fusion을 기능으로 강화했고(2.19에서 score ranker processor/RRF 소개), Elasticsearch도 RRF retriever를 공식 REST API로 문서화했습니다. ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))

**언제 쓰면 좋은가**
- 문서가 “자연어 + 키워드(코드/식별자)”가 혼재된 기술 문서/지원 티켓/런북/인시던트 포스트모템
- RAG에서 “정확 키워드 미포함” 때문에 근거 문서를 놓치는 문제가 있을 때
- 질의 타입이 다양해 **dense 단독** 또는 **BM25 단독**이 계속 흔들릴 때

**언제 안 쓰는 게 나은가**
- 데이터가 매우 구조화되어 있고(테이블/필드가 명확), 질의도 필터/정렬이 핵심인 경우: hybrid+RRF가 “마법탄”처럼 개선되지 않을 수 있습니다(실제 커뮤니티에서도 “거의 개선 없음” 사례가 자주 보고됨). ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1sjpilr/hybrid_search_bm25_vectors_rrf_barely_improved/?utm_source=openai))
- latency/비용이 매우 빡빡해서 “2회 검색 + 병합 + rerank” 파이프라인을 감당하기 어려운 경우(이때는 query 라우팅/룰 기반으로 단일 경로를 먼저 고려)

---

## 🔧 핵심 개념
### 1) BM25 vs Vector: 스코어의 “단위”가 다르다
- BM25 점수는 **용어 빈도/역문서빈도/문서 길이 정규화** 기반의 sparse scoring
- vector 점수는 cosine/dot/L2 등 **임베딩 공간 유사도** 기반

문제는 두 스코어가 **스케일과 분포가 완전히 다르다**는 점입니다. 그래서 단순히 `final = bm25_score + vector_score`는 대부분 실패합니다. 2026년 실무 가이드는 “스코어를 합치기보다, 랭크를 합쳐라” 쪽(= RRF) 또는 “정규화+가중합”을 신중하게 쓰는 쪽으로 정리되는 분위기입니다. ([elastic.co](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion?utm_source=openai))

### 2) Fusion의 두 축: Rank fusion(RRF) vs Score fusion(Weighted)
#### (A) RRF(Reciprocal Rank Fusion): **랭크 기반 병합**
Elasticsearch 문서 기준 RRF는 여러 result set을 합칠 때 다음 형태의 점수(개념적으로)를 사용합니다. ([elastic.co](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion?utm_source=openai))

- 각 리스트에서의 rank `r`에 대해 `1 / (k + r)`를 누적(여기서 `k`는 랭크 완만화 상수)
- 장점: 스코어 스케일 이슈에 둔감, 튜닝 부담이 낮음, “둘 중 하나에서만 강하게 뜨는 문서”를 살려줌
- 단점: **top-K 후보군 품질**에 매우 민감(각 검색이 얼마나 좋은 후보를 가져오느냐), 그리고 “정확히 얼마나 BM25를 더 믿을지” 같은 미세 조정이 어려움

OpenSearch도 Neural Search 플러그인에 RRF를 도입해 hybrid 성능을 끌어올리는 방향을 공식 블로그로 강조했습니다. ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))

#### (B) Weighted sum / alpha: **스코어 기반 병합**
Weaviate는 hybrid에서 `alpha`(0=BM25, 1=vector) 같은 형태로 가중치를 주는 접근을 제공합니다. ([weaviate.io](https://weaviate.io/developers/weaviate/search/hybrid?utm_source=openai))  
장점은 “우리 도메인에서 lexical이 훨씬 중요” 같은 정책을 스코어에 직접 반영 가능하다는 점.

하지만 여기서 핵심은:
- 두 스코어를 **정규화**하지 않으면 alpha는 거의 의미가 없어질 수 있고,
- alpha를 “고정 값”으로 박아두면 질의 타입 변화에 취약합니다.

그래서 2025~2026 연구/실무에서는 **per-query로 alpha를 동적으로 튜닝**하는 시도(DAT 같은 접근)도 등장합니다. ([arxiv.org](https://arxiv.org/abs/2503.23013?utm_source=openai))

### 3) Production에서의 “정석” 흐름(3단)
2026년 시점의 레퍼런스 파이프라인은 대체로 이 형태입니다.

1) **Candidate generation (parallel)**  
   - BM25 top N + Vector top M (보통 50~200씩)  
2) **Fusion (RRF 또는 정규화+가중합)**  
3) **Rerank (cross-encoder)**: fused top K(예: 50)만 재정렬

SemEval-2026 시스템 보고에서도 “query rewriting → BM25+dense를 RRF로 결합 → cross-encoder rerank” 같은 3단 구성이 반복됩니다. ([arxiv.org](https://arxiv.org/abs/2605.12028?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 “기술 지원/런북 문서” 5만~50만 건 정도를 가정한 **현실적인 RAG retrieval 서비스** 형태입니다.

- BM25: PostgreSQL full-text search(실무에서 운영/백업/권한/조인이 쉬움)
- Vector: pgvector
- Fusion: **RRF**(애플리케이션 레벨에서 병합—엔진 교체/AB 테스트가 쉬움)
- Rerank: 선택(여기서는 인터페이스만 열어둠)

### 0) 의존성/셋업
```bash
# Python 3.11+
pip install fastapi uvicorn psycopg[binary] pgvector pydantic python-dotenv

# Postgres에 확장 설치(1회)
# CREATE EXTENSION IF NOT EXISTS vector;
```

예시 테이블(요지):
- `docs(id, title, body, meta jsonb, tsv tsvector, embedding vector(768))`
- `tsv`는 `to_tsvector('english', title || ' ' || body)`로 미리 생성(트리거/배치)

### 1) BM25 / Vector 후보를 “각각” 뽑기
```python
# app.py
from fastapi import FastAPI
from pydantic import BaseModel
import os
import psycopg
from typing import Dict, List, Tuple

app = FastAPI()
DB_DSN = os.environ["DB_DSN"]

class SearchReq(BaseModel):
    query: str
    topk: int = 10
    bm25_k: int = 80
    vec_k: int = 80
    rrf_k: int = 60  # RRF 완만화 상수(작을수록 상위 랭크 편향이 강함)

def rrf_fuse(
    bm25_ids: List[int],
    vec_ids: List[int],
    k: int,
    out_size: int
) -> List[Tuple[int, float]]:
    # RRF score = Σ 1 / (k + rank)
    scores: Dict[int, float] = {}

    for rank, doc_id in enumerate(bm25_ids, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    for rank, doc_id in enumerate(vec_ids, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused[:out_size]

def embed_query(text: str) -> List[float]:
    """
    현실에서는 embedding service(예: 내부 모델 서버, Bedrock, OpenAI 등)를 호출.
    여기서는 '이미 query embedding을 만들었다'고 가정하는 형태로 인터페이스만 둔다.
    """
    raise NotImplementedError("Provide query embedding via your embedding service.")

@app.post("/search")
def search(req: SearchReq):
    q = req.query
    q_emb = embed_query(q)

    with psycopg.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            # 1) BM25 후보
            cur.execute(
                """
                SELECT id
                FROM docs
                WHERE tsv @@ websearch_to_tsquery('english', %s)
                ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', %s)) DESC
                LIMIT %s
                """,
                (q, q, req.bm25_k),
            )
            bm25_ids = [r[0] for r in cur.fetchall()]

            # 2) Vector 후보 (cosine distance -> similarity로 쓰려면 정렬 주의)
            # pgvector: <=> 는 cosine distance(설정/버전에 따라 연산자 다를 수 있음)
            cur.execute(
                """
                SELECT id
                FROM docs
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (q_emb, req.vec_k),
            )
            vec_ids = [r[0] for r in cur.fetchall()]

            # 3) Fusion (RRF)
            fused = rrf_fuse(bm25_ids, vec_ids, k=req.rrf_k, out_size=max(req.topk, 50))
            fused_ids = [doc_id for doc_id, _ in fused]

            # 4) (선택) rerank: 여기서는 fused_ids 상위 50개를 reranker에 넣는 구조로 확장
            # reranked_ids = cross_encoder_rerank(q, fused_ids[:50])

            # 5) 최종 문서 로드
            cur.execute(
                """
                SELECT id, title, left(body, 400) AS snippet
                FROM docs
                WHERE id = ANY(%s)
                """,
                (fused_ids[:req.topk],),
            )
            rows = cur.fetchall()

    return {
        "query": q,
        "bm25_candidates": len(bm25_ids),
        "vec_candidates": len(vec_ids),
        "topk": req.topk,
        "results": [{"id": r[0], "title": r[1], "snippet": r[2]} for r in rows],
        "debug": {
            "bm25_top10": bm25_ids[:10],
            "vec_top10": vec_ids[:10],
            "fused_top10": fused[:10],
        },
    }
```

**예상 출력(요지)**  
- `bm25_top10`에는 에러코드/키워드 정확 매치 문서가,
- `vec_top10`에는 유사 개념 문서가,
- `fused_top10`에는 “둘 중 하나라도 강한” 문서가 섞여 들어오는 패턴이 나와야 정상입니다.

### 2) 확장: “후보군 크기”를 튜닝하는 이유
RRF는 “랭크”만 보므로, **각 retriever가 가져오는 후보군이 빈약하면** fusion도 빈약해집니다. OpenSearch 기반 하이브리드 튜토리얼/가이드에서도 vector 쪽 `k`를 충분히 크게 잡아야 정상적으로 섞인다고 조언합니다. ([docs.digitalocean.com](https://docs.digitalocean.com/products/vector-databases/opensearch/how-to/hybrid-search/?utm_source=openai))  
실무에서는 보통:
- `bm25_k = 50~200`
- `vec_k = 50~200`
- `fusion_out = 50~200`
- `rerank = 20~100`
으로 시작해서, 오프라인 평가로 줄입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 효과 나는 3개)
1) **Fusion 전에 “필터링”을 먼저 하라 (metadata narrowing)**
- 테넌트/권한/제품/버전/언어/기간 같은 강한 조건은 BM25/Vector 둘 다에 동일하게 적용해야 합니다.
- 안 하면 topK가 잡음으로 오염되고 RRF가 그 잡음을 “공정하게” 섞어버립니다.

2) **RRF의 k(완만화 상수)는 “품질-다양성” 노브**
- k가 작으면 상위 랭크의 힘이 커져서 “한쪽이 확실히 맞는” 케이스에 유리
- k가 크면 더 많은 후보를 완만하게 섞어 “다양성/커버리지”가 늘 수 있음  
Elasticsearch도 RRF를 독립 retriever로 다루며 파라미터로 제어합니다. ([elastic.co](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion?utm_source=openai))

3) **Reranker는 ‘정답률’보다 ‘안정성’을 산다**
- hybrid+RRF만으로도 좋아지지만, production에서 체감 차이를 만드는 건 종종 cross-encoder rerank입니다(특히 “비슷한 문서가 많은” 위키/정책 문서).
- 단, 비용/지연이 크니 fused top 50 정도만 넣고, 캐시/배치 전략을 꼭 같이 설계하세요(여러 2026 실무 가이드가 이 3단 구성을 반복). ([appscale.blog](https://appscale.blog/en/blog/hybrid-search-and-reranking-production-rag-bm25-dense-cross-encoder-2026?utm_source=openai))

### 흔한 함정/안티패턴
- **“hybrid를 켰는데 개선이 없다”**  
  실제로 구조화/짧은 문서/테이블 깨짐/필터 누락 같은 이유로 BM25 신호가 죽으면 RRF가 섞을 게 없습니다(커뮤니티에서도 이런 케이스가 반복). ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1sjpilr/hybrid_search_bm25_vectors_rrf_barely_improved/?utm_source=openai))
- **후보군 topK가 너무 작음**  
  BM25 top 10 + vector top 10을 섞어봤자, 이미 놓친 정답은 영원히 못 올라옵니다.
- **가중합(alpha) 고정으로 만능 해결 시도**  
  도메인에 따라 “식별자 질의”는 BM25가 압승이고, “설명형 질의”는 dense가 압승입니다. 고정 alpha는 평균만 맞추고 극단을 망칩니다. 그래서 per-query 동적 튜닝(DAT 등) 연구가 나옵니다. ([arxiv.org](https://arxiv.org/abs/2503.23013?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **2회 검색(lexical+dense)**: p95 latency가 1.7~2.5배로 늘 수 있음 → 병렬화/타임아웃/캐시 필수
- **RRF**: 스코어 정규화 부담이 적고 운영 안정성이 좋음(“튜닝 지옥”이 덜함). 대신 “정교한 정책 반영”은 어려움
- **Weighted fusion**: 정책 반영이 쉬우나, 스코어 정규화/캘리브레이션/질의별 편차 대응이 필요(운영 난이도↑)

---

## 🚀 마무리
정리하면, 2026년 5월 기준 hybrid search의 실전 결론은 간단합니다.

- **BM25 + vector를 ‘둘 다’ 돌려 후보를 넓히고**
- **fusion은 먼저 RRF로 시작해(튜닝 비용↓)**
- **품질/안정성이 더 필요하면 cross-encoder rerank를 얹는다**
- 이후에야 alpha(가중합)나 per-query 동적 가중 같은 “고급 튜닝”을 고민하는 게 ROI가 좋습니다. ([elastic.co](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion?utm_source=openai))

**도입 판단 기준(현업용)**
- “정확 키워드 질의”에서 근거를 자주 놓친다 → hybrid는 거의 필수
- 질의가 전부 자연어이고 문서도 서술형이며, 정확 매치가 거의 필요 없다 → dense + rerank가 더 단순/효율적일 수 있음
- latency/비용이 제한적 → hybrid는 하되, 후보군/ rerank K를 공격적으로 줄이고 캐시/필터를 먼저 최적화

**다음 학습 추천**
- Elasticsearch/OpenSearch의 RRF 구현 파라미터/실행 모델(코디네이팅 노드에서의 결합 등) 문서를 먼저 읽고, ([elastic.co](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion?utm_source=openai))
- “왜 어떤 코퍼스에서 hybrid가 별로인가”를 사례 기반으로 점검(테이블/구조화 데이터/필터 누락), ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1sjpilr/hybrid_search_bm25_vectors_rrf_barely_improved/?utm_source=openai))
- per-query 가중(동적 alpha) 같은 적응형 hybrid(DAT류)를 실험해 “질의 라우팅”까지 확장. ([arxiv.org](https://arxiv.org/abs/2503.23013?utm_source=openai))