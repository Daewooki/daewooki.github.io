---
title: "HyDE + Reranking + Query Expansion: 2026년 3월 기준 “검색 품질”로 RAG를 역전시키는 고급 최적화 레시피"
date: 2026-03-24 02:46:50 +0900
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
RAG 성능이 안 나오는 팀을 보면, 대개 LLM 문제가 아니라 **retrieval 품질(Recall/Precision)** 문제가 먼저 터집니다. 특히 실무 데이터(내부 위키, 티켓, 코드, 계약서)는 사용자 질의가 짧고 모호해서 **vocabulary mismatch**가 자주 발생합니다. “용어는 다른데 같은 뜻”인 경우, dense embedding만으로는 근처를 못 잡고, sparse(BM25)만으로는 의미를 못 잡습니다.

2026년 3월 시점에 “확실히 체감되는” 고급 패턴은 세 가지를 **멀티스테이지로 결합**하는 겁니다.

- **HyDE**: 질의를 “가상의 정답 문서(hypothetical document)”로 바꿔 embedding 공간에서 더 잘 붙게 만들기 (Gao et al., 2022) ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))  
- **Query Expansion/Transformation**: 질의를 여러 개로 재작성/확장해 recall을 뻥튀기 ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/optimizing/advanced_retrieval/query_transformations/?utm_source=openai))  
- **Reranking**: 많이 가져온 후보를 cross-encoder/LLM으로 다시 채점해 precision을 끌어올리기 ([docs.cohere.com](https://docs.cohere.com/docs/reranking?utm_source=openai))  

핵심은 “하나만”이 아니라 **Recall 단계(확장/HyDE/하이브리드) → Precision 단계(rerank)**로 역할을 분리하는 것입니다. Microsoft의 RAG IR 가이드도 query rewriter/executor/reranker로 단계화하는 구성을 권장합니다. ([learn.microsoft.com](https://learn.microsoft.com/fil-ph/azure/architecture/ai-ml/guide/rag/rag-information-retrieval?utm_source=openai))

---

## 🔧 핵심 개념
### 1) HyDE (Hypothetical Document Embeddings)
HyDE는 질의 `q`를 바로 embed하지 않고, LLM에게 **그럴듯한 답변/문서** `d̂`를 생성하게 한 다음, `d̂`를 embedding해서 벡터 검색에 씁니다. “정답처럼 생긴 문서”는 원문 코퍼스의 표현(용어/문장 패턴)과 더 가깝기 때문에, embedding 근접성이 좋아지는 효과가 납니다. ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))  
중요한 포인트: `d̂`는 사실과 다를 수 있지만, HyDE 논문은 **dense bottleneck(embedding)이 허위 디테일을 어느 정도 걸러주고**, 근방의 “진짜 문서”를 찾는 데 도움된다고 설명합니다. ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))

**언제 잘 먹히나**
- 사용자가 짧게 묻고(“권한 오류 해결”), 코퍼스는 전문 용어로 길게 서술된 경우
- 도메인 용어/약어가 많아서 query가 코퍼스 표현과 어긋나는 경우 ([colehoffer.ai](https://www.colehoffer.ai/articles/advanced-rag-hyde?utm_source=openai))

**비용/리스크**
- 쿼리마다 LLM 생성이 추가되어 지연이 증가(현업에선 캐시/샘플링 필수) ([colehoffer.ai](https://www.colehoffer.ai/articles/advanced-rag-hyde?utm_source=openai))  
- HyDE 문서가 너무 “창작”되면 오히려 drift가 생길 수 있어 프롬프트 제약이 중요

### 2) Query Expansion / Query Transformation
Query Expansion은 단순히 키워드를 늘리는 게 아니라, 최근엔 LLM을 이용해 **다중 관점 질의 세트**를 만들고(예: 원인/증상/해결책/관련 컴포넌트), 각각 검색한 뒤 합치는 방식이 흔합니다. LlamaIndex도 “query transformations”로 이런 흐름을 정식 기능으로 안내합니다. ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/optimizing/advanced_retrieval/query_transformations/?utm_source=openai))  
또한 2026년 3월 arXiv의 HCQR(Hypothesis-Conditioned Query Rewriting)는 “가설(가능한 답)”을 조건으로 질의를 다시 쓰는 접근으로, 단일 질의 RAG 대비 정확도 향상을 보고합니다. ([arxiv.org](https://arxiv.org/abs/2603.19008?utm_source=openai))  
(실무적으로는 “질의 재작성”이 결국 HyDE와 같은 축에 있으며, **HyDE=문서 형태의 확장**, rewriting=질의 형태의 확장이라고 보면 이해가 쉽습니다.)

### 3) Reranking (Cross-Encoder / LLM rerank)
Reranking은 1차 검색(topK=50~200)의 후보를 대상으로, (query, doc)를 함께 넣어 **정밀 스코어링**하는 2차 모델입니다. Cohere Rerank 계열은 “엔터프라이즈 검색/RAG용”으로 포지셔닝되어 있고, Azure Model Catalog에도 2026년 1월 업데이트로 등재되어 있습니다. ([ai.azure.com](https://ai.azure.com/catalog/models/Cohere-rerank-v3.5?utm_source=openai))  
또 연구 관점에서 cross-encoder가 BM25의 TF/IDF 유사 구조를 “semantic하게” 재발견한다는 분석도 있어, reranker가 왜 강한지 직관을 줍니다. ([arxiv.org](https://arxiv.org/abs/2502.04645?utm_source=openai))

### 4) 결합 전략: “Recall을 먼저, Precision은 나중에”
실전 파이프라인을 추천 형태로 쓰면:

1) Query Expansion (여러 질의)  
2) (옵션) HyDE로 “문서형 확장 질의” 추가  
3) Hybrid retrieval(BM25 + vector) 후 RRF 같은 fusion으로 합치기 ([colehoffer.ai](https://www.colehoffer.ai/guides/reciprocal-rank-fusion-for-hybrid-search?utm_source=openai))  
4) Reranker로 topN만 남기기  
5) (옵션) context compression/중복 제거 후 LLM 생성

이렇게 하면 “reranker는 후보 집합 밖은 못 구한다”는 한계를 **확장/하이브리드**로 보완할 수 있습니다. ([colehoffer.ai](https://www.colehoffer.ai/guides/reciprocal-rank-fusion-for-hybrid-search?utm_source=openai))

---

## 💻 실전 코드
아래 코드는 **HyDE + Multi-query expansion + Hybrid 검색(RRF) + Cross-encoder rerank**를 한 번에 보여주는 “실행 가능한” 예제입니다. (데이터는 로컬 텍스트 파일 폴더를 가정)

```python
# Python 3.11+
# pip install openai qdrant-client rank-bm25 sentence-transformers numpy

import os
import glob
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from openai import OpenAI

# -----------------------------
# 0) 준비: 문서 로딩/청킹(단순 예제)
# -----------------------------
def load_docs(path="./docs/*.txt") -> List[Dict]:
    docs = []
    for fp in glob.glob(path):
        with open(fp, "r", encoding="utf-8") as f:
            text = f.read()
        docs.append({"id": os.path.basename(fp), "text": text})
    return docs

def simple_chunk(text: str, chunk_size=800, overlap=120) -> List[str]:
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i+chunk_size])
        i += chunk_size - overlap
    return chunks

# -----------------------------
# 1) Query Expansion + HyDE 생성
# -----------------------------
client = OpenAI()  # OPENAI_API_KEY 환경변수 필요

def llm_expand_queries(query: str, n: int = 4) -> List[str]:
    """
    질의를 서로 다른 관점으로 n개 확장.
    - 실무에선 사용자 로그/도메인 사전/약어사전도 함께 사용 권장
    """
    prompt = f"""
You are an expert search query rewriter for RAG.
Generate {n} alternative search queries for the user question.
Rules:
- Keep each query <= 20 Korean words.
- Use domain synonyms and likely internal terminology.
- Return as a JSON array of strings only.

User question: {query}
"""
    r = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    # 응답이 JSON array라고 가정(프로덕션에서는 robust parsing 필요)
    import json
    return json.loads(r.output_text)

def llm_hyde_doc(query: str) -> str:
    """
    HyDE: '가상의 정답 문서' 생성
    - 사실 단정 금지/불확실성 표기/키워드 풍부화가 포인트
    """
    prompt = f"""
Write a hypothetical internal engineering knowledge-base article that would answer the question.
Constraints:
- Do NOT cite external sources.
- Include likely component names, error messages, configuration keys, and troubleshooting steps.
- 8-12 bullet points, concise.
Question: {query}
"""
    r = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return r.output_text

# -----------------------------
# 2) 인덱싱: Dense(Qdrant) + Sparse(BM25)
# -----------------------------
EMB_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")  # 예시
RERANKER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")           # 예시(가벼움)

@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str

def build_chunks(docs: List[Dict]) -> List[Chunk]:
    chunks = []
    for d in docs:
        for j, c in enumerate(simple_chunk(d["text"])):
            chunks.append(Chunk(chunk_id=f"{d['id']}#{j}", doc_id=d["id"], text=c))
    return chunks

def setup_qdrant(chunks: List[Chunk], collection="rag_chunks"):
    qd = QdrantClient(":memory:")  # 데모. 실무는 서버/클라우드.
    dim = EMB_MODEL.get_sentence_embedding_dimension()
    qd.recreate_collection(
        collection_name=collection,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )
    vectors = EMB_MODEL.encode([c.text for c in chunks], normalize_embeddings=True)
    qd.upsert(
        collection_name=collection,
        points=[
            qmodels.PointStruct(
                id=i,
                vector=vectors[i].tolist(),
                payload={"chunk_id": chunks[i].chunk_id, "doc_id": chunks[i].doc_id, "text": chunks[i].text},
            )
            for i in range(len(chunks))
        ],
    )
    return qd

def setup_bm25(chunks: List[Chunk]):
    tokenized = [c.text.lower().split() for c in chunks]
    return BM25Okapi(tokenized)

# -----------------------------
# 3) Retrieval + RRF Fusion
# -----------------------------
def rrf_fuse(rank_lists: List[List[int]], k: int = 60, topn: int = 80) -> List[Tuple[int, float]]:
    """
    Reciprocal Rank Fusion:
    score(d) = sum_i 1 / (k + rank_i(d))
    """
    scores = {}
    for lst in rank_lists:
        for r, idx in enumerate(lst, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + r)
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused[:topn]

def retrieve_dense(qdrant: QdrantClient, query: str, topk=50, collection="rag_chunks") -> List[int]:
    qv = EMB_MODEL.encode([query], normalize_embeddings=True)[0]
    hits = qdrant.search(collection_name=collection, query_vector=qv.tolist(), limit=topk)
    # :memory: 컬렉션 id가 0..N-1로 들어가 있으므로 point.id를 그대로 인덱스로 사용
    return [h.id for h in hits]

def retrieve_sparse(bm25: BM25Okapi, chunks: List[Chunk], query: str, topk=50) -> List[int]:
    scores = bm25.get_scores(query.lower().split())
    idxs = np.argsort(scores)[::-1][:topk]
    return idxs.tolist()

# -----------------------------
# 4) Reranking
# -----------------------------
def rerank(query: str, chunks: List[Chunk], cand_idxs: List[int], topn=8) -> List[Chunk]:
    pairs = [(query, chunks[i].text) for i in cand_idxs]
    scores = RERANKER.predict(pairs)  # cross-encoder 점수
    ranked = sorted(zip(cand_idxs, scores), key=lambda x: x[1], reverse=True)[:topn]
    return [chunks[i] for i, _ in ranked]

# -----------------------------
# 5) End-to-end 검색 함수
# -----------------------------
def advanced_retrieve(query: str, qdrant, bm25, chunks: List[Chunk]) -> List[Chunk]:
    # (A) Query expansion
    q_variants = llm_expand_queries(query, n=4)

    # (B) HyDE: 문서형 확장 질의 1개 추가
    hyde = llm_hyde_doc(query)

    # (C) 각 질의로 dense/sparse 후보를 뽑아 RRF로 합침
    rank_lists = []
    for q in [query] + q_variants + [hyde]:
        rank_lists.append(retrieve_dense(qdrant, q, topk=50))
        rank_lists.append(retrieve_sparse(bm25, chunks, q, topk=50))

    fused = rrf_fuse(rank_lists, k=60, topn=120)
    cand_idxs = [idx for idx, _ in fused]

    # (D) Rerank로 topN 정밀 선택
    return rerank(query, chunks, cand_idxs, topn=8)

if __name__ == "__main__":
    docs = load_docs("./docs/*.txt")
    chunks = build_chunks(docs)
    qdrant = setup_qdrant(chunks)
    bm25 = setup_bm25(chunks)

    q = "S3 업로드가 간헐적으로 403 AccessDenied가 나는데 IAM은 문제 없어 보여. 원인과 점검 포인트?"
    top_chunks = advanced_retrieve(q, qdrant, bm25, chunks)

    print("Top retrieved chunks:")
    for c in top_chunks:
        print("-", c.chunk_id, c.text[:120].replace("\n", " "), "...")
```

---

## ⚡ 실전 팁
1) **HyDE는 “생성 품질”보다 “검색용 형태”가 중요**
- 답을 잘 쓰는 게 목적이 아니라, 코퍼스 어휘에 가까운 키워드/구문을 많이 포함시키는 게 목적입니다.  
- 프롬프트에 “구성요소 이름, 에러 메시지, 설정 키”를 요구하면 임베딩 근접도가 체감 개선됩니다. (HyDE가 vocab mismatch에 강하다는 실무 관찰과도 일치) ([colehoffer.ai](https://www.colehoffer.ai/articles/advanced-rag-hyde?utm_source=openai))

2) **Reranker는 topK를 무작정 키우지 말고, stage를 나눠라**
- 1차 retrieval에서 너무 큰 topK(예: 1000)를 rerank하면 비용이 폭발합니다.
- 대신 **(확장 + 하이브리드 + fusion)**으로 “좋은 후보군”을 만든 뒤 rerank 하세요. fusion으로 BM25/dense의 상보성을 얻는 접근이 RRF 가이드에서 반복적으로 강조됩니다. ([colehoffer.ai](https://www.colehoffer.ai/guides/reciprocal-rank-fusion-for-hybrid-search?utm_source=openai))

3) **멀티쿼리 확장 시 “중복/동의어 과다”가 독이 된다**
- 확장 쿼리가 비슷비슷하면 후보군이 넓어지지 않습니다.
- 제약을 걸어 “서로 다른 관점”으로 만들고(증상/원인/해결/관련 로그), RRF로 합치면 안정적입니다.

4) **Reranking 모델 선택: cross-encoder vs API형**
- API형(예: Cohere Rerank 계열)은 멀티언어/엔터프라이즈 포맷(긴 문서, JSON 등) 최적화를 내세웁니다. ([docs.cohere.com](https://docs.cohere.com/docs/reranking?utm_source=openai))  
- 온프레미스/로컬은 bge 계열 cross-encoder를 많이 씁니다(대규모 운영에서의 실전 언급도 다수). 다만 이 글 코드는 경량 예시 모델을 사용했습니다.

5) **평가 없이는 최적화도 없다**
- HyDE/확장/rerank는 “좋아 보임”이 아니라 **Recall@K, nDCG, answer accuracy**로 측정해야 합니다.
- 최소한 (a) retrieval hit 여부 (b) rerank 이후 hit 여부 (c) 최종 답 정확도를 분리 로깅하세요. IR 단계가 병목인지 생성 단계가 병목인지 바로 드러납니다. (Microsoft도 retrieval 단계를 별도 설계 요소로 다룸) ([learn.microsoft.com](https://learn.microsoft.com/fil-ph/azure/architecture/ai-ml/guide/rag/rag-information-retrieval?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 3월 기준 RAG 성능 최적화의 “승부처”는 **질의 쪽에서 recall을 늘리고(HyDE/Query Expansion/Hybrid+RRF), reranking으로 precision을 고정하는 멀티스테이지 설계**입니다. HyDE는 특히 “짧고 모호한 질문 vs 길고 전문적인 코퍼스”의 간극을 메우는 데 강력하고, reranker는 그 후보군을 정밀하게 깎는 마지막 칼날입니다. ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))  

다음 학습 추천:
- HyDE 원 논문(2022)로 의도/한계 정확히 잡기 ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))  
- LlamaIndex의 query transformations로 실전 체인 구성 익히기 ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/optimizing/advanced_retrieval/query_transformations/?utm_source=openai))  
- RRF 기반 hybrid retrieval + rerank 튜닝(TopK, k 값, latency budget) ([colehoffer.ai](https://www.colehoffer.ai/guides/reciprocal-rank-fusion-for-hybrid-search?utm_source=openai))  

원하시면, 위 파이프라인을 **(1) LangChain/LlamaIndex 버전으로 포팅**하거나, **(2) latency 예산(예: p95 800ms)** 안에서 HyDE/확장의 개수와 rerank topK를 자동 튜닝하는 실전 설정도 같이 정리해드릴게요.