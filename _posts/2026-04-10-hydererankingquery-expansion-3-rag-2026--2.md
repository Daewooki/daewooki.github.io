---
title: "HyDE·Reranking·Query Expansion 3종 세트로 RAG 정확도 끌어올리기: 2026년 4월 기준 고급 최적화 설계"
date: 2026-04-10 03:29:58 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-04]
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
RAG 성능을 “모델을 더 크게”로만 해결하려고 하면 비용과 latency가 폭발합니다. 실무에서 더 흔한 병목은 **retrieval 품질(Recall/Precision)과 evidence 선택 실패**입니다. 특히 (1) 사용자의 질문이 짧거나 모호하고, (2) 문서가 길고 비정형(표/수치 포함)이며, (3) 용어가 다양한 도메인에서는 단순 dense top-k로는 정답 근거를 안정적으로 못 가져옵니다.

2026년 들어 흐름은 명확합니다. “한 방 retrieval”이 아니라 **2-stage(또는 3-stage) 파이프라인**으로 가고 있고, 그 중심에 **HyDE(가상 문서 기반 검색), Reranking(cross-encoder 재정렬), Query Expansion(다중 쿼리/리라이트)**이 있습니다. 다만 모든 데이터셋에서 만능은 아닙니다. 예를 들어 텍스트+테이블 혼합 금융 QA 벤치마크에서는 **hybrid retrieval + neural reranking** 조합이 강력한 반면, **HyDE·multi-query 같은 query expansion은 “정밀 수치 질의”에서 이득이 제한적**이라는 결과도 나왔습니다. ([arxiv.org](https://arxiv.org/abs/2604.01733))

---

## 🔧 핵심 개념
### 1) HyDE (Hypothetical Document Embeddings)
**정의:** LLM이 질의에 대해 “정답처럼 보이는 가상의 문서(또는 단락)”를 먼저 생성하고, 그 텍스트를 embedding 해서 벡터 검색하는 기법입니다. “질의 임베딩” 대신 “정답 근처의 문서 임베딩”을 만들어 **semantic gap**을 줄이는 아이디어죠. ([emergentmind.com](https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde?utm_source=openai))

**작동 원리(요지):**
1. user query → LLM → hypothetical doc(가설 답변/근거 형태)
2. hypothetical doc → embedding → vector search
3. top-k 후보를 이후 reranker로 정밀 정렬

**장점:** 짧은 질의/용어 mismatch에서 recall이 올라가기 쉽습니다.  
**단점:** LLM이 만들어낸 가설이 도메인에서 틀리면, 그 “틀린 방향”으로 검색이 끌려가고 latency도 늘어납니다(LLM 호출 1회 추가). ([emergentmind.com](https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde?utm_source=openai))

### 2) Reranking (Cross-Encoder)
**정의:** 1차 retrieval(top-k)로 뽑은 후보 문서들을, **query+document를 함께 인코딩**해 점수를 매겨 재정렬하는 단계입니다. embedding 기반 bi-encoder보다 느리지만 정확도가 높습니다. BGE 문서도 “top 100을 뽑고 rerank로 top-3를 고른다”는 전형적인 2-stage 패턴을 권장합니다. ([bge-model.com](https://bge-model.com/bge/bge_reranker.html))

**왜 중요한가:** 실무에서는 “top-50 안에는 답이 있는데 LLM이 못 맞추는” 일이 흔합니다. reranking은 이걸 “top-5 안으로 당겨” generation 성공확률을 올립니다. 그리고 2026년 연구에서는 reranker를 단순 relevance가 아니라 **generator에 ‘딱 좋은’ evidence(너무 쉽지도, 너무 불가능하지도 않은 근거)를 고르는 selector로 재해석**하기도 합니다(BAR-RAG). ([arxiv.org](https://arxiv.org/abs/2602.03689))

### 3) Query Expansion (Multi-query / Rewrite / RRF)
**정의:** 원래 질의를 LLM 또는 룰로 여러 개로 확장한 뒤, 각 질의로 검색하고 결과를 fusion 합니다(대표적으로 **Reciprocal Rank Fusion, RRF**). 구현 난이도 대비 recall을 끌어올리기 좋습니다. ([gist.github.com](https://gist.github.com/codewarnab/f7f10dbc382812bcd298abd7f35f71e2?utm_source=openai))

**주의:** 확장이 “도메인에서 그럴듯하지만 틀린” 방향으로 퍼지면 precision이 무너집니다. 특히 사용자의 의도를 rewrite 모델이 “대신 결정”하는 순간 독이 됩니다. ([medium.com](https://medium.com/%40ThinkingLoop/when-query-expansion-hurts-rag-23139f06d8d4?utm_source=openai))  
또한 2026년 4월 벤치마크에서는 **정밀 수치 질의**에서 query expansion의 이득이 제한적일 수 있음을 지적합니다. ([arxiv.org](https://arxiv.org/abs/2604.01733))

---

## 💻 실전 코드
아래는 **Hybrid retrieval(BM25 + Dense) → (옵션) HyDE & Multi-query → RRF fusion → Cross-encoder reranking(BGE) → top-n 컨텍스트 구성**까지 한 번에 돌아가는 “뼈대 코드”입니다.  
(실행 전: `pip install faiss-cpu rank-bm25 sentence-transformers transformers torch`)

```python
# Python 3.11+
# End-to-end Advanced RAG Retrieval Skeleton:
# - (Optional) HyDE for query -> hypothetical doc
# - (Optional) Multi-query expansion
# - Hybrid retrieval: BM25 + Dense
# - RRF fusion
# - Cross-encoder rerank (BGE-style reranker)
#
# Notes:
# - This is a minimal runnable example with in-memory docs.
# - Replace `docs` with your chunked corpus + metadata pipeline.

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict
import numpy as np

from rank_bm25 import BM25Okapi
import faiss

from sentence_transformers import SentenceTransformer, CrossEncoder
from transformers import pipeline

@dataclass
class Doc:
    doc_id: str
    text: str

def tokenize_for_bm25(text: str) -> List[str]:
    # 실무에서는 형태소/토크나이저를 더 신경 쓰세요(특히 한국어).
    return text.lower().split()

def rrf_fusion(rankings: List[List[str]], k: int = 60) -> List[Tuple[str, float]]:
    """
    Reciprocal Rank Fusion:
    score(d) = sum_i 1 / (k + rank_i(d))
    """
    scores: Dict[str, float] = {}
    for run in rankings:
        for r, doc_id in enumerate(run, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + r)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

def build_dense_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    # cosine 유사도를 위해 L2 normalize 후 Inner Product 사용
    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index

def dense_search(index, query_vec: np.ndarray, topk: int) -> List[int]:
    q = query_vec.astype(np.float32)
    faiss.normalize_L2(q)
    scores, ids = index.search(q, topk)
    return ids[0].tolist()

def main():
    # 1) Corpus
    docs = [
        Doc("d1", "HyDE generates a hypothetical document to improve dense retrieval when queries are underspecified."),
        Doc("d2", "A cross-encoder reranker scores query-document pairs jointly, improving precision at top-k."),
        Doc("d3", "RRF combines multiple ranked lists from different retrievers or query rewrites robustly."),
        Doc("d4", "Query expansion can hurt when the rewrite drifts from the user's intent or domain constraints."),
        Doc("d5", "Hybrid retrieval (BM25 + dense) followed by neural reranking is a strong baseline for RAG."),
    ]

    # 2) Models
    embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")  # 예시
    reranker = CrossEncoder("BAAI/bge-reranker-base")         # cross-encoder reranker
    # HyDE / Query expansion용 LLM (로컬 파이프라인 예시; 실무에선 API/사내모델로 교체)
    llm = pipeline("text-generation", model="gpt2", max_new_tokens=120)

    # 3) Build BM25
    tokenized = [tokenize_for_bm25(d.text) for d in docs]
    bm25 = BM25Okapi(tokenized)

    # 4) Build Dense index
    doc_texts = [d.text for d in docs]
    doc_emb = embedder.encode(doc_texts, convert_to_numpy=True, show_progress_bar=False).astype(np.float32)
    dense_index = build_dense_index(doc_emb)

    def hyde_generate(query: str) -> str:
        # HyDE는 "답변 형태의 가상 문서"를 만들수록 잘 동작하는 편입니다.
        prompt = (
            "Write a concise, factual paragraph that would appear in a technical document answering the question:\n"
            f"Q: {query}\n"
            "Paragraph:\n"
        )
        out = llm(prompt)[0]["generated_text"]
        return out[len(prompt):].strip()

    def expand_queries(query: str) -> List[str]:
        # 실무에서는 3~5개 정도로 제한하고, 도메인 용어/약어를 보존하는 규칙을 섞는 걸 추천.
        prompt = (
            "Rewrite the query into 3 diverse search queries, keeping technical terms unchanged.\n"
            f"Original: {query}\n"
            "Queries:\n-"
        )
        out = llm(prompt)[0]["generated_text"]
        # 매우 단순 파싱(데모). 프로덕션에선 구조화 출력(JSON) 강제하세요.
        lines = [x.strip("- ").strip() for x in out.splitlines() if x.strip().startswith("-")]
        return [query] + [q for q in lines[:3] if q]

    def retrieve_once(q: str, bm25_topk=5, dense_topk=5) -> Tuple[List[str], List[str]]:
        # BM25
        bm25_scores = bm25.get_scores(tokenize_for_bm25(q))
        bm25_rank = np.argsort(bm25_scores)[::-1][:bm25_topk]
        bm25_ids = [docs[i].doc_id for i in bm25_rank]

        # Dense
        q_emb = embedder.encode([q], convert_to_numpy=True, show_progress_bar=False).astype(np.float32)
        dense_rank = dense_search(dense_index, q_emb, dense_topk)
        dense_ids = [docs[i].doc_id for i in dense_rank]

        return bm25_ids, dense_ids

    query = "How do HyDE and reranking improve RAG retrieval?"
    # 5) (Optional) HyDE + Multi-query
    hyde_doc = hyde_generate(query)
    hyde_query = hyde_doc  # HyDE에서는 hypothetical doc 자체를 검색 질의로 사용

    expanded = expand_queries(query)

    # 6) Collect rankings and fuse with RRF
    rankings = []
    for q in expanded:
        bm25_ids, dense_ids = retrieve_once(q)
        rankings.append(bm25_ids)
        rankings.append(dense_ids)

    # HyDE run도 추가(의미적으로 다른 "search intent"를 넣는 효과)
    hyde_bm25, hyde_dense = retrieve_once(hyde_query)
    rankings.append(hyde_bm25)
    rankings.append(hyde_dense)

    fused = rrf_fusion(rankings, k=60)
    candidate_ids = [doc_id for doc_id, _ in fused[:10]]  # reranker 후보 풀

    id_to_doc = {d.doc_id: d for d in docs}
    candidates = [id_to_doc[i].text for i in candidate_ids]

    # 7) Cross-encoder rerank: (query, doc) 쌍 스코어링
    pairs = [[query, c] for c in candidates]
    scores = reranker.predict(pairs)

    reranked = sorted(zip(candidate_ids, candidates, scores), key=lambda x: x[2], reverse=True)

    print("Top reranked contexts:")
    for doc_id, text, s in reranked[:3]:
        print(f"- {doc_id} score={float(s):.4f} :: {text[:90]}...")

if __name__ == "__main__":
    main()
```

---

## ⚡ 실전 팁
- **기본 승리 공식은 “Hybrid + Reranking”부터**입니다. 2026년 4월 벤치마크에서도 혼합 문서(텍스트+표) 환경에서 **2-stage(하이브리드 검색 + neural reranking)**가 강력한 상한선을 보여줍니다. ([arxiv.org](https://arxiv.org/abs/2604.01733))
- **HyDE는 “질의가 짧고 용어가 흔들릴 때”만 켜는 게 안전**합니다. 전 질의에 HyDE를 강제하면 (1) latency 증가, (2) 잘못된 가설로 인한 drift가 누적됩니다. HyDE가 비용을 25~60% 늘릴 수 있다는 보고도 있습니다. ([emergentmind.com](https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde?utm_source=openai))
- **Query Expansion은 ‘다양성’보다 ‘의도 보존’이 우선**입니다. rewrite가 사용자의 의도를 바꾸면 recall이 아니라 noise를 늘립니다. “짧은 질의만 확장”, “도메인 키워드/약어는 절대 변경 금지”, “구조화 출력(JSON) 강제” 같은 가드레일을 두세요. ([medium.com](https://medium.com/%40ThinkingLoop/when-query-expansion-hurts-rag-23139f06d8d4?utm_source=openai))
- **Reranker 후보 풀(top-k)을 줄이면 정확도가 떨어지고, 늘리면 비용이 폭발**합니다. 보통 `retrieve top 50~200 → rerank top 10~30` 정도에서 비용/품질 균형이 나옵니다(코퍼스/도메인에 따라 튜닝). cross-encoder는 정확하지만 느리다는 점이 핵심 trade-off입니다. ([bge-model.com](https://bge-model.com/bge/bge_reranker.html))
- **“Relevance”만 최적화하지 말고 “Generator-friendly evidence”를 보라**: 최근에는 reranker를 generator 관점에서 재정의해 robustness를 올리는 연구도 나왔습니다. 지금 당장 RL까지 못 하더라도, 실무적으로는 “너무 짧은 정의문만 잔뜩 뽑히는” 경우를 패널티 주는 등 heuristic으로 흉내낼 수 있습니다. ([arxiv.org](https://arxiv.org/abs/2602.03689))
- **수치/정밀 질의에서는 BM25가 dense를 이길 수 있음**: “semantic이 무조건 우월”이라는 가정이 깨지는 케이스가 있습니다. 표/수치/티커/계정과목처럼 exact match가 중요한 도메인은 BM25 비중을 과감히 올리세요. ([arxiv.org](https://arxiv.org/abs/2604.01733))

---

## 🚀 마무리
HyDE, Reranking, Query Expansion은 각각 “recall”, “precision@top”, “표현 다양성”을 올리는 도구지만, 2026년 4월 기준 실전에서 가장 재현성 높은 조합은 **Hybrid retrieval → Cross-encoder reranking**이고, HyDE/Expansion은 **조건부로 얹는 옵션**이 더 안정적입니다. ([arxiv.org](https://arxiv.org/abs/2604.01733))  
다음 학습으로는 (1) RRF/가중치 fusion의 정량 튜닝, (2) 도메인별 query rewrite 가드레일 설계, (3) “generator 관점 evidence selection” 같은 reranker 고도화(BAR-RAG 계열)까지 확장하면, 같은 모델/같은 토큰 예산으로도 RAG 품질을 한 단계 더 올릴 수 있습니다. ([arxiv.org](https://arxiv.org/abs/2602.03689))