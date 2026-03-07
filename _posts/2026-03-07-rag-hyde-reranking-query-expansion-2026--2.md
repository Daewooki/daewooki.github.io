---
title: "RAG 성능이 안 오르는 진짜 이유: HyDE + Reranking + Query Expansion을 “같이” 최적화하는 법 (2026년 3월 기준)"
date: 2026-03-07 02:34:45 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-03]
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
프로덕션 RAG에서 “임베딩 모델 바꾸면 좋아지겠지”는 보통 착각입니다. 실패 패턴을 뜯어보면 대개 **(1) query–document asymmetry(질문은 짧고 문서는 길다)**, **(2) 1차 검색의 recall 부족**, **(3) 상위 k 안에서의 precision 부족** 세 가지로 귀결됩니다.  
2026년 3월 시점에도 업계/연구의 흐름은 크게 변하지 않았고, 이 문제를 가장 실전적으로 푸는 조합이 **HyDE로 recall을 끌어올리고 → Reranking으로 precision을 고정 → Query Expansion으로 커버리지를 넓히는** 3단 구조입니다. HyDE는 원래 “relevance label 없이도” zero-shot dense retrieval을 강하게 만드는 아이디어로 제안됐고, 실제 RAG 최적화 가이드들에서도 “HyDE + reranker”를 강력 추천하는 패턴이 반복됩니다. ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))

---

## 🔧 핵심 개념
### 1) HyDE (Hypothetical Document Embeddings)
**정의:** 유저 query를 그대로 embed해서 검색하지 않고, LLM으로 “이 질문에 대한 이상적인 답변/문서(가짜 문서)”를 먼저 생성한 뒤 그 텍스트를 embedding해서 검색하는 기법입니다. ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))

**왜 통하나(원리):**
- query는 짧고 정보가 덜 들어있어서 embedding 공간에서 “어떤 문서랑 가까워야 하는지” 신호가 약합니다.
- HyDE는 **답변 형태의 텍스트(=문서 스타일)** 를 만들어 embedding 입력을 문서 분포에 맞춥니다. 즉, embedding 모델이 잘하는 형태로 query를 변환해 **semantic gap**을 줄입니다. ([emergentmind.com](https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde?utm_source=openai))  
**리스크:** HyDE가 “그럴듯한 헛소리”를 생성하면 엉뚱한 방향으로 검색이 당겨질 수 있어, 후단에서 **reranker로 post-validate** 하는 게 사실상 세트입니다. ([emergentmind.com](https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde?utm_source=openai))

### 2) Reranking (Cross-Encoder / Late Interaction)
**정의:** 1차 retrieval(topN)은 빠르게 “후보를 많이” 뽑고, reranker가 query–doc을 **jointly encode**해서 더 정확히 점수화한 뒤 topK를 재정렬합니다. BGE 문서도 reranker를 embedding 모델과 구분해 “직접 relevance를 출력”한다고 정리합니다. ([bge-model.com](https://bge-model.com/Introduction/reranker.html?utm_source=openai))

**어떤 계열이 있나:**
- **Cross-Encoder**: 정확하지만 비용이 큼(후보 N이 늘수록 선형으로 느려짐).
- **Late interaction(예: ColBERT)**: 후보를 많이 다루면서도 효율/정확 타협점. ([arxiv.org](https://arxiv.org/abs/2004.12832?utm_source=openai))

### 3) Query Expansion / Multi-Query
**정의:** 원 query를 여러 변형으로 확장(동의어, 하위 질문, 관점 분해)해 검색 커버리지를 넓히는 전략. 최근 RAG 계열 논문들도 “query rewriting/augmentation”을 별도 레이어로 다루고, **다양성 있는 multi-query**가 retrieval과 최종 품질을 올린다고 보고합니다. ([aclanthology.org](https://aclanthology.org/2025.acl-long.693/?utm_source=openai))

**핵심 포인트:** expansion은 recall을 올리지만 **노이즈도 같이 올립니다**. 그래서 실전에서는
- expansion으로 후보 pool을 키우고
- reranker로 precision을 다시 잠그는
구조가 안정적입니다.

---

## 💻 실전 코드
아래 코드는 “**Multi-Query + HyDE + (Vector Search) + Cross-Encoder Rerank**”의 뼈대입니다.  
외부 벡터DB 대신 로컬에서 `faiss`를 쓰고, reranker는 HuggingFace cross-encoder 계열(예: BGE reranker)을 붙이는 형태로 작성했습니다.

```python
# pip install -U sentence-transformers faiss-cpu numpy

from sentence_transformers import SentenceTransformer, CrossEncoder
import faiss
import numpy as np

# ---------------------------
# 1) 준비: 코퍼스(문서 chunk)와 인덱스 구축
# ---------------------------
docs = [
    "HyDE는 LLM이 생성한 hypothetical document를 embed해서 dense retrieval 성능을 개선한다.",
    "Cross-encoder reranker는 query와 document를 함께 넣고 직접 relevance score를 출력한다.",
    "Multi-query rewriting은 서로 다른 관점의 query를 만들어 recall을 높이지만 노이즈도 늘린다.",
    "ColBERT는 late interaction을 사용해 효율적인 passage search를 제공한다.",
    "RAG 최적화는 retrieve-many-then-rerank가 기본 패턴이다."
]

embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
doc_emb = embed_model.encode(docs, normalize_embeddings=True).astype("float32")

dim = doc_emb.shape[1]
index = faiss.IndexFlatIP(dim)  # cosine 유사도는 normalize + inner product로 처리
index.add(doc_emb)

# ---------------------------
# 2) Query Expansion (간단 버전)
#    - 실전에서는 LLM으로 N개 생성 + 다양성 제약(중복 제거) 권장
# ---------------------------
def expand_queries(q: str) -> list[str]:
    # 데모용: 규칙 기반. 실제로는 LLM prompt로 "서로 다른 관점 3~8개" 생성 추천
    return [
        q,
        f"{q} 성능 병목 원인",
        f"{q} reranking 적용 방법",
        f"{q} HyDE query rewriting 비교"
    ]

# ---------------------------
# 3) HyDE (데모용)
#    - 실전에서는 LLM 호출로 "가짜 문서" 생성
# ---------------------------
def hyde_generate(q: str) -> str:
    # NOTE: 여기서는 LLM 대신 템플릿. 실제로는:
    #  - "답변을 단정하지 말고 키워드/정의/절차 위주로 기술"
    #  - 길이 제한(예: 120~200 tokens)
    return (
        f"이 문서는 '{q}'에 대한 기술적 설명이다. "
        "핵심은 retrieval recall을 늘리고, reranker로 precision을 고정하며, "
        "query expansion으로 검색 커버리지를 넓히는 것이다."
    )

# ---------------------------
# 4) 1차 Retrieval: Multi-query + HyDE 임베딩으로 후보 풀 수집
# ---------------------------
def retrieve_candidates(user_query: str, top_n: int = 5) -> list[tuple[int, float]]:
    candidates = {}
    for q in expand_queries(user_query):
        hyde_doc = hyde_generate(q)
        q_emb = embed_model.encode([hyde_doc], normalize_embeddings=True).astype("float32")
        scores, ids = index.search(q_emb, top_n)

        for doc_id, score in zip(ids[0], scores[0]):
            # Rank-fusion의 아주 단순 버전: 최대 score로 통합
            candidates[doc_id] = max(candidates.get(doc_id, -1e9), float(score))

    # 후보를 score로 정렬
    return sorted(candidates.items(), key=lambda x: x[1], reverse=True)

# ---------------------------
# 5) Reranking: Cross-Encoder로 최종 정렬
#    - BGE reranker 등으로 교체 가능
# ---------------------------
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def rerank(user_query: str, cand_ids: list[int], top_k: int = 3):
    pairs = [(user_query, docs[i]) for i in cand_ids]
    ce_scores = reranker.predict(pairs)

    ranked = sorted(zip(cand_ids, ce_scores), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]

# ---------------------------
# 6) 실행
# ---------------------------
q = "RAG에서 HyDE와 reranking을 같이 쓰는 최적 패턴"
cands = retrieve_candidates(q, top_n=4)
cand_ids = [doc_id for doc_id, _ in cands][:8]  # 후보 풀 크기 조절
final_top = rerank(q, cand_ids, top_k=3)

print("== Candidates ==")
for doc_id, s in cands:
    print(doc_id, round(s, 3), docs[doc_id])

print("\n== Reranked TopK ==")
for doc_id, s in final_top:
    print(doc_id, round(float(s), 3), docs[doc_id])
```

---

## ⚡ 실전 팁
- **HyDE는 “항상 on”이 아니라 “조건부 on”이 효율적**입니다. 예: 1차 retrieval score 분포가 평평하거나, top1~topk가 특정 임계치 아래면 HyDE를 켜는 식(비용/지연 최적화). ([emergentmind.com](https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde?utm_source=openai))
- **Retrieve-many-then-rerank의 N/K를 분리**하세요. 경험적으로 `topN=30~200`(cheap) → `rerank topK=5~10`(expensive) 구조가 튜닝하기 좋습니다. ([maxpool.dev](https://maxpool.dev/rag/?utm_source=openai))
- **Query Expansion은 “다양성”이 핵심**입니다. 동의어만 늘리면 중복만 증가합니다. 관점(정의/비교/절차/제약/실패 사례)을 강제로 분해해 multi-query를 만들고, 결과는 RRF 같은 rank fusion으로 합치는 패턴이 안정적입니다(논문/실무 모두 이 방향). ([arxiv.org](https://arxiv.org/abs/2411.13154?utm_source=openai))
- **Reranker 선택**: 다국어/한글이 섞이면 multilingual cross-encoder 계열(BGE reranker 등)을 후보로 두고, latency 예산이 작으면 작은 cross-encoder부터 시작하세요. BGE는 reranker를 “embedding이 아닌 direct scoring”으로 명확히 구분해 문서화합니다. ([bge-model.com](https://bge-model.com/bge/bge_reranker.html?utm_source=openai))
- **HyDE 환각 방지 프롬프트**: “사실 단정 금지, 키워드/정의/체크리스트 위주, 길이 제한”을 걸면 drift가 줄고 reranker의 부담도 감소합니다(특히 사내 문서/정책 검색).

---

## 🚀 마무리
HyDE, Reranking, Query Expansion은 각각 “좋은 트릭”이 아니라 **서로의 부작용을 상쇄하는 역할 분담**입니다.

- HyDE: query–document asymmetry를 줄여 **recall을 끌어올림**
- Query Expansion: 검색 관점을 넓혀 **coverage를 확장**
- Reranking: 늘어난 후보/노이즈를 정리해 **precision을 고정**

다음 단계로는 (1) 조건부 HyDE 라우팅, (2) fusion(RRF) 정교화, (3) 도메인별 hard negative로 reranker 미세조정, (4) multi-hop query rewriting(계획 기반) 같은 방향을 추천합니다. ([arxiv.org](https://arxiv.org/abs/2502.18139?utm_source=openai))