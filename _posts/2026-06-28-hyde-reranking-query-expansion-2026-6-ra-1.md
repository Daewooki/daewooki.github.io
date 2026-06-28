---
title: "HyDE + Reranking + Query Expansion: 2026년 6월 기준 “진짜” RAG 성능을 끌어올리는 고급 검색 스택"
date: 2026-06-28 04:38:52 +0900
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
프로덕션 RAG에서 성능이 “거의 맞는데 결정적으로 틀리는” 케이스는 보통 **retrieval 단계에서 top-k 안에 정답 근거가 못 들어오거나**, 들어와도 **상위에 못 올라와** LLM 프롬프트에 실리지 않아서 발생합니다. 2026년 기준 현업에서 가장 재현성 있게 먹히는 처방은 크게 3가지 축입니다:

- **Query Expansion**: 사용자의 짧고 모호한 query를 여러 개로 “펼쳐” recall을 올림
- **HyDE (Hypothetical Document Embeddings)**: LLM이 “그럴듯한 답변 문서”를 먼저 써주고, 그 문서를 임베딩해 retrieval의 semantic gap을 줄임 ([ocadefusion.fr](https://www.ocadefusion.fr/rag/hyde?utm_source=openai))
- **Reranking (Cross-Encoder / ColBERT)**: 1차 후보(대개 50~200개)를 “질문-문서 쌍”으로 정밀 채점해 top-n을 재정렬 ([presenc.ai](https://presenc.ai/research/best-open-weight-reranker-models-2026?utm_source=openai))

### 언제 쓰면 좋나
- 문서가 길고 다양하며(내부 위키/정책/기술문서), query가 짧고 모호한 편
- “정답 문서가 아예 안 잡히는” recall 문제가 있거나
- 하이브리드(BM25+dense)만으로는 domain mismatch가 자주 나는 경우

### 언제 쓰면 안 되나
- 이미 1차 retrieval top-10에 정답이 안정적으로 들어오는데 “생성/프롬프트”가 문제인 경우(이때는 rerank/HyDE는 비용만 늘고 효과가 작을 수 있음) ([callsphere.ai](https://callsphere.ai/blog/vw6g-hyde-hypothetical-document-embeddings-2026?utm_source=openai))
- 초저지연(수십 ms) 요구가 강한 실시간 서비스에서 cross-encoder rerank를 무턱대고 넣는 경우(캐싱/게이팅 없으면 곧바로 비용 폭발)

---

## 🔧 핵심 개념
### 1) Query Expansion: “recall을 돈으로 사는” 전략
**정의**: 하나의 query를 여러 variant로 확장(재작성/분해/동의어/약어 풀기 등)하고, 각 query로 검색한 결과를 **RRF(Reciprocal Rank Fusion)** 같은 방식으로 합치는 접근입니다. SemEval/TREC 계열 시스템도 multi-stage에서 query rewriting + hybrid + rerank 조합을 반복적으로 사용합니다. ([arxiv.org](https://arxiv.org/abs/2605.12028?utm_source=openai))

**흐름**
1. LLM(또는 rule)로 query variant N개 생성
2. 각 variant로 BM25 + dense(또는 둘 중 하나) 검색
3. 결과를 RRF로 fuse → 후보 풀을 크게 확보
4. (선택) reranker로 최종 상위만 정밀 선별

**차이점**
- HyDE가 “문서 형태로 변환”이라면, Query Expansion은 “질문 자체를 여러 개로” 늘립니다.
- Expansion은 **coverage(포괄성)**, HyDE는 **semantic gap 완화**에 강점.

### 2) HyDE: “질문을 문서로 바꿔서” 임베딩 공간의 위치를 이동
**정의**: LLM이 query에 대해 답변에 가까운 **hypothetical document**를 생성하고, 그 문서를 임베딩해 검색합니다(원 query 임베딩 대신/또는 함께). 원 아이디어는 retrieval에서 query가 너무 짧아 임베딩이 불안정한 문제를 줄이는 것. ([ocadefusion.fr](https://www.ocadefusion.fr/rag/hyde?utm_source=openai))

**내부 작동(실무 관점)**
- query → (LLM) hypothetical doc 생성
- hypothetical doc → embedding
- embedding으로 vector search 수행
- (보통) 원 query vector search도 같이 수행하고 fuse(RRF)하는 편이 안전

**2026년식 관찰 포인트**
- 임베딩/하이브리드가 강해진 환경에서는 HyDE의 평균 이득이 작아져서, **“어려운 query에만 켠다(gating)”**가 수익성이 좋다는 경험칙이 보고됩니다. ([callsphere.ai](https://callsphere.ai/blog/vw6g-hyde-hypothetical-document-embeddings-2026?utm_source=openai))

### 3) Reranking: 2-stage RAG의 “결정타”
**정의**: 1차 retriever가 뽑은 top-K(보통 50~200)를 cross-encoder가 query-document를 직접 입력으로 받아 점수를 내고 재정렬합니다. embedding 기반 유사도(=bi-encoder)와 달리, cross-encoder는 **질문과 문서를 함께 보며** 미세한 관련성을 잡습니다. ([bge-model.com](https://bge-model.com/bge/bge_reranker.html?utm_source=openai))

**대표 모델/트렌드(2026년 상반기)**
- 오픈 웨이트 쪽은 **Qwen3-Reranker, BGE-Reranker-v2 계열**이 자주 언급됩니다. ([presenc.ai](https://presenc.ai/research/best-open-weight-reranker-models-2026?utm_source=openai))
- BGE 쪽 문서도 reranker가 “embedding이 아니라 query+doc → score”라는 점을 명확히 합니다. ([bge-model.com](https://bge-model.com/bge/bge_reranker.html?utm_source=openai))
- 연구/실험에서는 retriever(HyDE/HyPE/Fusion) + reranker(BGE/MiniLM 등) 조합 평가가 계속 나오고 있습니다. ([link.springer.com](https://link.springer.com/article/10.1007/s10791-026-10156-3?utm_source=openai))

---

## 💻 실전 코드
아래는 **현실적인 내부 문서 RAG**를 가정한 파이프라인 예시입니다.

- Vector DB: Qdrant
- 1차 검색: Dense(top=80) + BM25(top=80) + RRF fuse
- Query Expansion: LLM으로 3개 variant 생성
- HyDE: LLM으로 hypothetical doc 1개 생성(어려운 query일 때만)
- Rerank: BGE cross-encoder로 최종 top-12 선별
- 출력: 상위 문서의 score/메타데이터

### 0) 의존성/실행 준비
```bash
pip install qdrant-client sentence-transformers transformers torch --upgrade
# OpenAI 사용 시:
pip install openai
```

### 1) 파이프라인 코드 (Python)
```python
import os
from dataclasses import dataclass
from typing import List, Dict, Tuple
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

# ---- 설정 ----
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "internal_docs")

# Dense embedder (예: BGE-M3 같은 계열을 가정)
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")

# Reranker: cross-encoder (2026년 현업에서 자주 쓰는 BGE reranker 계열)
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

# ---- 데이터 구조 ----
@dataclass
class Hit:
    doc_id: str
    text: str
    source: str
    score: float  # retrieval or rerank score
    meta: Dict

# ---- 유틸: RRF ----
def rrf_fuse(rank_lists: List[List[Hit]], k: int = 60) -> List[Hit]:
    # RRF score = sum(1 / (k + rank))
    # doc_id 기준으로 합산
    acc: Dict[str, Tuple[Hit, float]] = {}
    for hits in rank_lists:
        for rank, h in enumerate(hits, start=1):
            add = 1.0 / (k + rank)
            if h.doc_id not in acc:
                acc[h.doc_id] = (h, add)
            else:
                acc[h.doc_id] = (acc[h.doc_id][0], acc[h.doc_id][1] + add)

    fused = []
    for doc_id, (h, s) in acc.items():
        fused.append(Hit(doc_id=doc_id, text=h.text, source=h.source, score=s, meta=h.meta))
    fused.sort(key=lambda x: x.score, reverse=True)
    return fused

# ---- (선택) LLM 기반 Query Expansion / HyDE ----
# 여기서는 OpenAI를 예로 들되, 사내 LLM/로컬 LLM로 대체 가능하도록 함수로 분리
def llm_generate_variants(query: str) -> List[str]:
    """
    현실 팁: variant는 3~5개가 보통 sweet spot.
    - 약어 풀기
    - 동의어/제품명 변형
    - 한글/영문 혼용
    """
    try:
        from openai import OpenAI
        client = OpenAI()
        prompt = f"""
너는 검색 최적화 전문가다.
원문 질의: {query}
목표: 내부 기술문서 검색 recall을 올리기 위한 query variants 3개를 만들어라.
조건:
- 원문의 의도를 유지
- 약어/영문/한글 변형 포함
- 출력은 JSON 배열 문자열로만
"""
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            temperature=0.2,
        )
        import json
        return json.loads(r.output_text)
    except Exception:
        # LLM 미구성 시 fallback
        return [query, query + " 가이드", query + " troubleshooting"]

def llm_generate_hyde_doc(query: str) -> str:
    """
    HyDE: '답변이 실린 것 같은 문서'를 생성하되,
    사실성보다 '검색용 표현 다양성'이 핵심.
    """
    try:
        from openai import OpenAI
        client = OpenAI()
        prompt = f"""
다음 질문에 답하는 내부 기술 문서의 한 섹션을 작성해라.
질문: {query}

조건:
- bullet/절차/키워드를 풍부하게 포함
- 특정 회사 비밀/가정 데이터는 만들지 말고 일반화
- 길이: 200~350자
"""
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            temperature=0.3,
        )
        return r.output_text
    except Exception:
        return f"{query}\n\n키워드: 설정, 오류, 원인, 해결, 체크리스트"

def is_hard_query(query: str) -> bool:
    # 실무에서는 (1) 길이, (2) OOV 비율, (3) 과거 실패율, (4) 초기 top-k score gap 등으로 게이팅
    return len(query) < 12 or ("?" in query)

# ---- 검색기 ----
class RagRetriever:
    def __init__(self):
        self.qdrant = QdrantClient(url=QDRANT_URL)
        self.embedder = SentenceTransformer(EMBED_MODEL)
        self.reranker = CrossEncoder(RERANK_MODEL)

    def dense_search(self, query: str, limit: int = 80) -> List[Hit]:
        qv = self.embedder.encode(query, normalize_embeddings=True).tolist()
        res = self.qdrant.search(
            collection_name=COLLECTION,
            query_vector=qv,
            limit=limit,
            with_payload=True,
        )
        hits = []
        for p in res:
            payload = p.payload or {}
            hits.append(Hit(
                doc_id=str(p.id),
                text=payload.get("text", ""),
                source=payload.get("source", "unknown"),
                score=float(p.score),
                meta=payload
            ))
        return hits

    def bm25_search(self, query: str, limit: int = 80) -> List[Hit]:
        # Qdrant의 full-text 인덱싱/필터를 사용한다고 가정 (구현은 스키마에 따라 달라짐)
        # 여기서는 예시로 "text" 필드 full-text match를 사용했다고 가정한 pseudo.
        res = self.qdrant.search(
            collection_name=COLLECTION,
            query_filter={
                "must": [
                    {"key": "text", "match": {"text": query}}
                ]
            },
            limit=limit,
            with_payload=True
        )
        hits = []
        for p in res:
            payload = p.payload or {}
            hits.append(Hit(
                doc_id=str(p.id),
                text=payload.get("text", ""),
                source=payload.get("source", "unknown"),
                score=float(p.score),
                meta=payload
            ))
        return hits

    def rerank(self, query: str, candidates: List[Hit], top_n: int = 12) -> List[Hit]:
        pairs = [(query, h.text[:2000]) for h in candidates]  # 너무 길면 잘라서 비용/지연 관리
        scores = self.reranker.predict(pairs)
        reranked = []
        for h, s in zip(candidates, scores):
            reranked.append(Hit(doc_id=h.doc_id, text=h.text, source=h.source, score=float(s), meta=h.meta))
        reranked.sort(key=lambda x: x.score, reverse=True)
        return reranked[:top_n]

    def retrieve(self, query: str) -> List[Hit]:
        variants = llm_generate_variants(query)

        rank_lists = []
        for q in variants:
            rank_lists.append(self.dense_search(q, limit=80))
            rank_lists.append(self.bm25_search(q, limit=80))

        if is_hard_query(query):
            hyde_doc = llm_generate_hyde_doc(query)
            rank_lists.append(self.dense_search(hyde_doc, limit=80))  # HyDE는 doc를 query로 넣는 셈

        fused = rrf_fuse(rank_lists, k=60)[:200]   # rerank 입력 풀은 100~200 사이가 흔함
        reranked = self.rerank(query, fused, top_n=12)
        return reranked

if __name__ == "__main__":
    rr = RagRetriever()
    q = "HyDE를 RAG에 넣었는데 reranking까지 해야 하나?"
    top = rr.retrieve(q)
    for i, h in enumerate(top, 1):
        print(f"{i:02d}. score={h.score:.4f} source={h.source} id={h.doc_id}")
        print(h.text[:180].replace("\n", " "))
        print("-" * 80)
```

### 예상 출력(형태)
- rerank score 기반으로 상위 문서가 재정렬되며, 동일 문서가 여러 query variant에서 걸려도 RRF로 합쳐진 뒤 1회만 rerank 됩니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (효과 큰 순)
1) **Rerank는 “후보 풀 품질”이 전제**  
reranker는 top-200 안에 정답이 있어야 이깁니다. 그래서 보통 “hybrid + expansion + (필요 시 HyDE)”로 **후보 풀 recall**을 먼저 올리고, 그 다음 rerank로 precision을 올립니다. ([arxiv.org](https://arxiv.org/abs/2605.12028?utm_source=openai))

2) **HyDE는 상시 ON보다 ‘게이팅’이 현실적**  
HyDE는 LLM 호출 + 추가 검색이므로 비용이 누적됩니다. 최근 글/경험 공유에서는 강한 baseline(좋은 embedding + hybrid) 위에서는 평균 이득이 작아 **어려운 query에만 켜는 전략**이 수익성이 좋다고 봅니다. ([callsphere.ai](https://callsphere.ai/blog/vw6g-hyde-hypothetical-document-embeddings-2026?utm_source=openai))

3) **오픈 웨이트 reranker는 BGE 계열이 디폴트 옵션이 됨**  
cross-encoder 기반 reranker가 “프로덕션 RAG의 2nd stage”라는 점, 그리고 BGE reranker가 대표 오픈 모델로 널리 쓰인다는 점이 여러 자료에서 반복됩니다. ([presenc.ai](https://presenc.ai/research/best-open-weight-reranker-models-2026?utm_source=openai))

### 흔한 함정/안티패턴
- **“reranker 넣었더니 오히려 나빠짐”**:  
  - (a) reranker가 cross-encoder가 아니라 bi-encoder(임베딩 모델)를 잘못 쓴 경우  
  - (b) 언어/도메인 mismatch(특히 비영어, 사내 용어)  
  - (c) 후보 풀이 너무 작아 rerank가 의미 없음  
  현업에서도 이런 케이스가 꽤 보고됩니다. ([reddit.com](https://www.reddit.com/r/Rag/comments/1s8j0im/reranker_worsening_rag_retrieval_results/?utm_source=openai))

- **rerank 입력 텍스트를 무제한으로 넣기**: 토큰/지연/VRAM이 바로 터집니다. 상위 chunk의 **앞부분만**, 혹은 “query 주변 window”만 잘라 넣는 게 비용 대비 효율이 좋습니다.

### 비용/성능/안정성 트레이드오프
- Query Expansion/HyDE는 **LLM 호출 비용 + 지연**이 추가되지만, retriever가 약한 구간에서 recall을 올리는 데 강합니다.
- Cross-encoder rerank는 후보 K에 선형으로 비용이 늘어납니다(대개 K=100~200에서 타협). “항상 최고 모델”이 아니라, 트래픽 구간별로 **MiniLM급(저가) vs BGE급(고품질)** 이원화도 흔합니다. ([presenc.ai](https://presenc.ai/research/best-open-weight-reranker-models-2026?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 6월 시점의 실전형 RAG 성능 최적화는 “한 방”이 아니라 **스택 설계**입니다.

- **Recall**이 문제면: Query Expansion + (필요 시) HyDE로 후보 풀을 키우고 ([ocadefusion.fr](https://www.ocadefusion.fr/rag/hyde?utm_source=openai))  
- **Precision**이 문제면: cross-encoder **reranking을 2nd stage로 고정**하고, K/top-n/텍스트 길이로 비용을 제어 ([presenc.ai](https://presenc.ai/research/best-open-weight-reranker-models-2026?utm_source=openai))  
- HyDE는 강력하지만, 강한 baseline 위에서는 **게이팅**이 도입 판단의 핵심 ([callsphere.ai](https://callsphere.ai/blog/vw6g-hyde-hypothetical-document-embeddings-2026?utm_source=openai))  

다음 학습/실험 추천:
- 내 데이터셋에서 **“정답 문서가 top-200 안에 있나?”(oracle recall@200)** 먼저 재고, 그 다음 rerank/HyDE/expansion을 단계적으로 추가하세요.
- retriever–reranker 조합을 통제 실험으로 비교한 2026년 평가 연구(예: retriever/ reranker 페어링 비교)를 읽고, 본인 도메인에 맞게 K, fusion, reranker 모델 크기를 튜닝하는 게 가장 빠릅니다. ([link.springer.com](https://link.springer.com/article/10.1007/s10791-026-10156-3?utm_source=openai))