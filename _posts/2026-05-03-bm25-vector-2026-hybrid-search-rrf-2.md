---
title: "BM25와 Vector를 “그냥 섞지 말자”: 2026년형 Hybrid Search 랭킹 병합(RRF/정규화/가중치) 실전 가이드"
date: 2026-05-03 03:58:30 +0900
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
RAG에서 “검색이 약간만 틀려도” 생성 품질이 급격히 무너지는 케이스를 많이 봅니다. 특히 다음 같은 상황에서요.

- **정확한 키워드/코드(에러코드, SKU, 옵션명, 함수명)**가 포함된 질문: vector-only는 종종 놓칩니다.
- 반대로 **사용자가 표현을 돌려 말하는 질문**: BM25-only는 recall이 깨집니다.
- 문서가 길고(매뉴얼/PDF), chunk가 애매하면 둘 다 흔들립니다.

그래서 2026년 현재 실무 RAG 검색은 “BM25 + vector”를 병렬로 돌리고, **랭킹 병합(fusion)** 으로 결과를 합치는 **Hybrid Search**가 기본 옵션이 됐습니다. OpenSearch는 hybrid query + search pipeline(정규화/랭크 병합)을 공식 기능으로 제공하고, RRF 같은 rank-based fusion도 제품 기능으로 들어왔습니다. ([docs.opensearch.org](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/?utm_source=openai))

### 언제 쓰면 좋나
- **도메인 용어/약어/제품 코드가 자주 등장**하는 검색(전자상거래, 헬프데스크, 개발문서, 사내 위키)
- **질문 스타일이 제각각**(키워드형/자연어형 혼재)
- RAG에서 **top-k 품질이 곧 답변 품질**로 직결되는 경우

### 언제 쓰지 말아야 하나(혹은 신중히)
- 쿼리/문서가 매우 동질적이고 **semantic만으로도 충분히 잘 맞는** 폐쇄형 코퍼스
- **운영 복잡도**(인덱스 2종, 파이프라인, 튜닝 포인트 증가)를 감당 못할 때
- “병합”이 만능이라 생각하고 **chunking/파싱 품질을 방치**할 때(이 경우 hybrid가 기대만큼 개선이 안 나오는 사례가 반복 보고됨) ([reddit.com](https://www.reddit.com/r/Rag/comments/1sjpl95/hybrid_search_bm25_vectors_rrf_barely_improved/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Hybrid Search의 본질: “점수 합산”이 아니라 “서로 다른 스코어 체계의 충돌 해결”
- **BM25 점수**: 쿼리-문서 토큰 매칭 기반, 스케일이 **unbounded**(상한 없음)
- **Vector 유사도**(cosine 등): 보통 **[0,1]** 또는 좁은 범위
- 즉, 둘을 단순히 더하면 **BM25가 이기거나**, 반대로 정규화가 과하면 **vector가 과대평가**됩니다.

OpenSearch 쪽 문서/가이드도 이 지점을 명확히 짚고, hybrid는 “sub-query 결과를 받아 **정규화/결합하는 search pipeline**”로 구현된다고 설명합니다. ([docs.opensearch.org](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/?utm_source=openai))

### 2) 병합 전략의 두 계열
#### A. Score-based fusion (정규화 + 가중합)
흐름은 보통 아래입니다.

1) BM25로 topK_sparse, vector로 topK_dense를 각각 구함  
2) 문서별 점수를 모아 **정규화(normalization)**  
3) `final_score = α * norm(bm25) + (1-α) * norm(vector)` 같은 방식으로 결합  
4) 최종 topK를 반환

장점
- “BM25를 0.7로, vector를 0.3으로” 같은 **직관적 튜닝**이 가능
- 특정 도메인에서는 query-type 별로 α를 바꾸는 **adaptive weighting**도 가능(다만 운영 복잡도 증가)

단점
- 정규화가 잘못되면 **스케일 왜곡**으로 랭킹이 급격히 깨짐
- topK 밖의 후보는 애초에 섞이지 않으므로 **candidate recall**이 부족할 수 있음

OpenSearch 하이브리드 예시에서도 BM25와 k-NN 점수 스케일 차이를 언급하며 normalization processor를 사용하라고 가이드합니다. ([docs.digitalocean.com](https://docs.digitalocean.com/products/vector-databases/opensearch/how-to/hybrid-search/?utm_source=openai))

#### B. Rank-based fusion (RRF: Reciprocal Rank Fusion)
RRF는 “점수” 대신 “순위”만 사용합니다.

- 각 검색기에서 나온 랭크를 `rank`라 할 때,
- 문서의 RRF 점수는 대략 `sum( 1 / (k + rank) )`
- 여러 검색기에서 **상위에 반복 등장하는 문서**가 위로 올라옵니다.

장점
- 스코어 정규화 지옥에서 벗어남: **서로 다른 스코어 스케일을 신경 쓸 필요가 거의 없음** ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))
- 구현이 단순하고 안정적(“BM25가 너무 세다/약하다” 같은 스케일 문제를 완화)

단점
- “BM25 신호를 2배 더 강하게” 같은 **미세한 가중 튜닝**은 상대적으로 제한적(가능은 하지만 제품/구현마다 방식이 다름)
- 각 랭커의 topK 설정이 중요: topK가 작으면 candidate 다양성이 줄어듦

OpenSearch는 Neural Search 플러그인에서 RRF를 hybrid search 병합 기능으로 소개했고, Azure AI Search 역시 hybrid scoring에서 RRF 기반의 랭킹 병합을 공식 문서로 제공합니다. ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))

### 3) “랭킹 병합”만으로 RAG가 끝나지 않는 이유: 2-stage의 필요
2026년 4월 arXiv 논문에서도, **hybrid retrieval + neural reranking(2-stage)** 조합이 단일 단계보다 크게 성능이 좋다고 보고합니다. 특히 특정 도메인(예: 금융 문서)에서는 BM25가 dense를 이기기도 해서, “semantic이 항상 우월”이라는 전제를 깨고요. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))

실무적으로는:
- Stage1: hybrid(BM25+vector)로 **recall을 최대화**
- Stage2: cross-encoder/LLM reranker로 **precision을 올림**
이 구성이 “안정적으로 잘 나오는” 패턴입니다.

---

## 💻 실전 코드
아래는 “toy”가 아니라, **실제 RAG 인덱스/검색 파이프라인**을 가정한 예제입니다.

- 검색엔진: **OpenSearch**
- 인덱스: 문서 chunk(예: 매뉴얼/가이드)를 저장
- 쿼리: `BM25(match)` + `k-NN(vector)`를 병렬 수행
- 병합: (1) 정규화+가중합 또는 (2) RRF 중 하나 선택
- 후처리: topN을 RAG 컨텍스트로 전달(여기서는 검색까지)

> OpenSearch hybrid는 “hybrid query + search pipeline(정규화/랭크 병합)” 패턴을 사용합니다. ([docs.opensearch.org](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/?utm_source=openai))

### 0) 의존성/환경
```bash
# OpenSearch 2.11+ 권장 (hybrid 기능 문서 기준)
# Python client
pip install opensearch-py==2.*
```

### 1) 인덱스 예시(문서 chunk + dense vector)
```bash
curl -X PUT "$OPENSEARCH_URL/rag_chunks" -H 'Content-Type: application/json' -d '{
  "settings": {
    "index": { "knn": true }
  },
  "mappings": {
    "properties": {
      "doc_id":    { "type": "keyword" },
      "chunk_id":  { "type": "integer" },
      "title":     { "type": "text" },
      "content":   { "type": "text" },
      "content_vector": {
        "type": "knn_vector",
        "dimension": 1536,
        "method": { "name": "hnsw", "space_type": "cosinesimil", "engine": "nmslib" }
      },
      "updated_at": { "type": "date" },
      "source":     { "type": "keyword" }
    }
  }
}'
```

### 2) (핵심) Hybrid Query + 랭킹 병합
#### 옵션 A: 정규화 + 가중 결합(Score-based)
DigitalOcean의 OpenSearch hybrid 가이드는 BM25 점수(무한대 가능)와 k-NN 점수([0,1])를 섞기 위해 **normalization-processor**를 사용하라고 명시합니다. ([docs.digitalocean.com](https://docs.digitalocean.com/products/vector-databases/opensearch/how-to/hybrid-search/?utm_source=openai))

아래는 Python에서 hybrid 검색을 호출하는 현실적인 코드(필터, topK 설정 포함)입니다.

```python
from opensearchpy import OpenSearch

client = OpenSearch(
    hosts=[{"host": "localhost", "port": 9200}],
    http_compress=True,
)

def hybrid_search(query_text: str, query_vector: list[float], tenant: str, k_dense=50, k_sparse=50, size=10):
    body = {
        "size": size,
        "query": {
            "hybrid": {
                "queries": [
                    {
                        "match": {
                            "content": {
                                "query": query_text,
                                "operator": "and"
                            }
                        }
                    },
                    {
                        "knn": {
                            "content_vector": {
                                "vector": query_vector,
                                "k": k_dense
                            }
                        }
                    }
                ]
            }
        },
        # 운영에서 필터는 거의 필수(테넌트/권한/문서종류/기간 등)
        "post_filter": {
            "bool": {
                "filter": [
                    {"term": {"source": tenant}}
                ]
            }
        },
        # search_pipeline은 클러스터에 미리 구성돼있다고 가정
        # (normalization-processor가 subquery 점수를 정규화/결합)
        "ext": {
            "search_pipeline": "hybrid_norm_pipeline_v1"
        }
    }
    return client.search(index="rag_chunks", body=body)

# 예상 출력(요약)
# hits.hits[i]._source: {doc_id, chunk_id, title, content...}
# hits.hits[i]._score: 병합된 최종 스코어
```

**파이프라인에서 할 일(개념적으로)**  
- BM25, k-NN의 점수를 normalization 후, `α`로 섞습니다.
- α는 “키워드 쿼리 비율이 높은 서비스”면 BM25 쪽을 더 주고, “자연어 질문이 대부분”이면 vector 쪽을 더 주는 식으로 시작합니다(하지만 아래 ‘함정’ 참고).

#### 옵션 B: RRF(Rank-based)
OpenSearch는 RRF를 hybrid search의 병합 전략으로 소개하며, 스코어 정규화 대신 **rank 기반 결합**이 안정적이라고 설명합니다. ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))  
Azure AI Search도 hybrid scoring에서 RRF를 공식적으로 설명합니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking?utm_source=openai))

RRF를 쓰는 경우, 운영 감각은 이렇습니다.
- BM25 topK_sparse, vector topK_dense를 **충분히 크게** 뽑는다(예: 50~200)
- RRF 상수 k(문헌/제품에서 k=60 같은 값이 자주 보임)를 고정하고
- “둘 다에서 상위에 드는” 문서가 올라오게 만든다

(OpenSearch에서 RRF를 어떻게 파이프라인에 설정하는지는 버전/플러그인 구성에 따라 달라서, 운영 환경 문서에 맞춰 적용해야 합니다. 중요한 건 “정규화 대신 rank fusion을 한다”는 구조입니다.)

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) topK를 “최종 size”보다 훨씬 크게 뽑아라
하이브리드는 병합이 핵심이라서,
- BM25에서 top10
- vector에서 top10
- 병합해서 top10
처럼 하면 **후보군이 너무 작아** “둘 중 하나만 강한 문서”를 놓치기 쉽습니다.

권장 출발점:
- 1차 후보: 각 50~200
- 최종 반환: 10~20
- 이후 reranker: 20~50 정도

2-stage가 단일 단계보다 성능이 크게 나온다는 보고도 같은 맥락입니다. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))

### Best Practice 2) Query-type에 따라 병합 전략을 나눠라(최소한의 규칙 기반이라도)
- 쿼리에 **코드/버전/에러번호/고유명사**가 많다 → BM25 가중↑ 또는 RRF에서 sparse topK↑
- “~하는 방법”, “차이”, “개념 설명” 같은 자연어 → vector 신호↑

이걸 ML로 하든(분류기), 룰로 하든(정규식/토큰 특징), “항상 0.5/0.5”는 생각보다 잘 안 맞습니다. 커뮤니티에서도 “일부 쿼리는 BM25에 더 기대야 한다”는 피드백이 반복됩니다. ([reddit.com](https://www.reddit.com/r/Rag/comments/1sjpl95/hybrid_search_bm25_vectors_rrf_barely_improved/?utm_source=openai))

### Best Practice 3) 필터를 hybrid 전체에 ‘한 번’만 적용되게 구성하라
하이브리드 쿼리에서 테넌트/권한 필터를 각 subquery에 중복 적용하면 유지보수 지옥입니다. OpenSearch는 hybrid 쿼리에서 공통 필터를 쉽게 적용하는 방향으로 기능을 확장해 왔습니다. ([opensearch.org](https://opensearch.org/blog/introducing-common-filter-support-for-hybrid-search-queries/?utm_source=openai))

### 흔한 함정 1) “hybrid 썼는데 개선이 거의 없음” → chunking/파싱이 원인인 경우가 많다
특히 표/스키마/도면이 많은 기술문서(PDF)에서:
- 텍스트 추출이 깨짐
- chunk가 표를 반으로 자름
- BM25는 매칭할 토큰이 없어지고, vector도 의미가 흐려짐

이 경우 hybrid를 더 튜닝해도 한계가 있고, **파싱(레이아웃 보존) + chunking 전략**부터 고쳐야 합니다. 실제로 hybrid+RRF가 “마법탄이 아니다”라는 현장 피드백이 이 지점에서 많이 나옵니다. ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1sjpilr/hybrid_search_bm25_vectors_rrf_barely_improved/?utm_source=openai))

### 흔한 함정 2) 가중합을 쓰면서 정규화를 가볍게 봄
BM25와 vector의 스케일은 본질적으로 달라서,
- min-max/표준화/L2 같은 정규화 선택에 따라 결과가 확 달라집니다.
OpenSearch도 이 문제 때문에 normalization processor 같은 전용 메커니즘을 제공하는 흐름입니다. ([docs.opensearch.org](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **비용**: 검색을 2번(또는 2개의 subquery) 하니 CPU/메모리/IO가 증가
- **지연시간**: ANN(k-NN) + BM25 둘 다 돌리면 p95가 튈 수 있어 topK, shard, 캐시, 필터 전략이 중요
- **안정성**: reranker까지 넣으면 더 좋아지지만, 모델 호출 비용/지연과 장애 포인트가 추가됨  
  → 고가치 쿼리(유료 고객, CS, 규정/법무)만 rerank하는 식으로 단계적 적용이 현실적

---

## 🚀 마무리
정리하면, 2026년의 hybrid search는 “BM25 + vector를 같이 돌린다”가 끝이 아니라, **랭킹 병합 전략을 어떻게 설계/운영하느냐**가 승부처입니다.

- **스코어 정규화에 자신 없고 안정성을 원하면**: RRF 같은 rank-based fusion을 먼저 고려 ([opensearch.org](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/?utm_source=openai))  
- **도메인 특성상 신호의 비중을 적극적으로 조절해야 하면**: normalization + weighted sum(단, 정규화 설계가 핵심) ([docs.digitalocean.com](https://docs.digitalocean.com/products/vector-databases/opensearch/how-to/hybrid-search/?utm_source=openai))  
- 그리고 대부분의 “프로덕션급 RAG”는 결국 **hybrid(Recall) + rerank(Precision)** 2-stage로 수렴하는 경향이 강합니다. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))

### 도입 판단 기준(빠른 체크리스트)
- 내 쿼리에 **희귀 토큰/코드/고유명사**가 자주 등장한다 → hybrid 가치 큼
- 검색 실패 원인의 50% 이상이 “의미는 비슷한데 정확한 항목이 안 나옴/그 반대” → hybrid + fusion 튜닝 대상
- chunking/파싱 품질이 낮다 → hybrid 전에 ingestion부터 개선

### 다음 학습 추천
- OpenSearch hybrid query + pipeline(정규화/랭크 병합) 문서 흐름을 그대로 따라가며, **내 코퍼스에서 topK/병합 파라미터를 로그 기반으로 튜닝**하는 루프를 먼저 만드세요. ([docs.opensearch.org](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/?utm_source=openai))

원하시면, 사용 중인 스택(OpenSearch/Elasticsearch/pgvector/Weaviate 등)과 문서 타입(PDF/HTML/Notion/Confluence), 쿼리 예시 20개 정도를 기준으로 **(1) RRF vs 가중합 선택**, **(2) topK/α/k 튜닝 초기값**, **(3) reranker 도입 임계점**까지 “실제로 굴러가는” 구성안을 더 구체적으로 잡아드릴게요.