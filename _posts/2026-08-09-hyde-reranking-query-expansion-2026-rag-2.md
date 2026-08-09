---
title: "HyDE + Reranking + Query Expansion: 2026년형 RAG 성능을 “끝까지” 끌어올리는 검색 스택 설계 가이드"
date: 2026-08-09 02:15:22 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-08]
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
RAG를 운영해보면 결국 같은 벽에 부딪힙니다.

- **Recall 부족**: “정답이 인덱스에 있는데” 못 찾는다.
- **Precision 부족**: 찾긴 찾는데 “그럴듯한” 문서가 섞여 LLM이 헛소리를 만든다.
- **Query-Document style gap**: 유저 질문은 짧고 추상적인데, 문서는 길고 구체적이라 **dense embedding만으로는 매칭이 자주 빗나간다**(HyDE가 겨냥하는 핵심 문제). ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))

2026년 8월 기준, 실무에서 성능을 확 올리는 조합은 보통 **(1) Query Expansion(다중 쿼리/rewriting)로 recall을 올리고 → (2) Fusion(RRF)로 결과를 안정적으로 합치고 → (3) Cross-Encoder Reranking으로 precision을 끌어올리는** 3단 스택입니다. SemEval-2026 RAG 계열 시스템들이 비슷한 파이프라인(쿼리 재작성 → 하이브리드+fusion → cross-encoder rerank)을 반복해서 채택한 것도 같은 이유입니다. ([arxiv.org](https://arxiv.org/abs/2605.12028?utm_source=openai))

### 언제 쓰면 좋은가
- 질문이 짧거나 모호하고(“권한 에러 해결”), 문서가 길고 구조화된 경우(사내 위키/런북/PRD/로그 가이드)
- “정답 문서가 있는데 못 찾는” 케이스가 자주 발생하고, LLM 프롬프트만 만져서는 개선이 안 되는 경우
- 비용/지연을 일부 감수하더라도 **정답률**이 KPI인 경우(고객지원/내부 DevOps Assistant)

### 언제 쓰면 안 되는가
- **초저지연**(예: p95 < 200ms)이 절대조건인데, reranker(특히 cross-encoder)까지 넣기 어려운 경우
- 코퍼스가 작고(수천 문서 이하), 단순 BM25나 기본 dense로도 충분히 맞는 경우
- 장문 생성(HyDE)이 규정상/보안상 어렵거나, 질문이 민감해서 LLM 호출 자체가 제한적인 경우(이때는 HyDE 대신 rule-based query rewrite나 domain thesaurus가 더 현실적)

---

## 🔧 핵심 개념
### 1) HyDE (Hypothetical Document Embeddings)
**정의**: 유저 query를 그대로 임베딩하지 않고, LLM에게 “이 질문에 답하는 그럴듯한 문서(가짜 문서)”를 생성하게 한 뒤, 그 가짜 문서를 임베딩해서 retrieval query로 쓰는 기법입니다. ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))

**왜 먹히나(구조/흐름)**  
일반 dense retrieval은 `embed(query)`와 `embed(chunk)`를 비교합니다. 문제는 query가 짧을수록 embedding이 “의도”만 담고, chunk embedding은 “내용”을 담아서 **벡터 공간에서 직접 맞붙으면 스타일/길이 차이로 손해**를 봅니다. HyDE는 LLM이 query를 **문서 스타일로 확장**해 줌으로써 `query → pseudo-doc → embedding`으로 매칭 분포를 문서쪽에 더 가깝게 끌어옵니다(질문-문서 갭을 줄임). ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))

**트레이드오프**: 쿼리마다 LLM 호출이 추가되어 **query-time 비용/지연 증가**가 가장 큰 단점입니다(후속 연구들도 HyDE의 오버헤드를 계속 지적). ([arxiv.org](https://arxiv.org/abs/2607.29402?utm_source=openai))  
그래서 2026년엔 “HyDE를 무조건”이 아니라, **difficulty-based gating**(어려운 질문일 때만 HyDE/다중쿼리 활성화) 같은 운영 패턴이 자주 언급됩니다. ([reddit.com](https://www.reddit.com/r/Rag/comments/1uowqpz/the_production_querytime_rag_flow_we_landed_on_in/?utm_source=openai))

> 참고: 2026년 7월 말에는 HyDE의 query-time 오버헤드를 줄이려는 방향으로, 런타임 생성 대신 미리 프리컴퓨트해 retrieval을 question-question 형태로 바꾸는 접근(HyPE)이 제안되었습니다. 즉, HyDE 계열은 “갭을 줄이되 비용을 줄이는” 방향으로 진화 중입니다. ([arxiv.org](https://arxiv.org/abs/2607.29402?utm_source=openai))

### 2) Query Expansion (Multi-query / Query Rewriting)
**정의**: 동일 의도의 질문을 여러 표현으로 생성해 각각 retrieval하고 합치는 방식입니다. 예: “timeout 해결” → “read timeout”, “connection timeout”, “nginx upstream timeout”…  

**내부 작동**:
- LLM 또는 규칙 기반으로 **N개의 쿼리 변형** 생성
- 각 쿼리로 topK 검색
- 결과를 **fusion**으로 합친 뒤 rerank

이 패턴은 RAG-Fusion(다중 쿼리 + RRF) 계열에서 “recall을 올리되 안정적으로 합치는” 방법으로 반복적으로 다뤄집니다. ([arxiv.org](https://arxiv.org/abs/2603.02153?utm_source=openai))

### 3) Fusion (RRF: Reciprocal Rank Fusion)
**정의**: 서로 다른 검색기/쿼리에서 나온 **랭킹 리스트**를 스코어 스케일 정규화 없이 합치는 랭크 기반 방법입니다. ([colab.ws](https://colab.ws/articles/10.1145/1571941.1572114?utm_source=openai))  
대표 공식은 다음 형태입니다:

- `RRF(d) = Σ_i w_i / (k + rank_i(d))` ([arc-labs.ai](https://arc-labs.ai/learn/reciprocal-rank-fusion?utm_source=openai))

**왜 중요한가**: BM25 점수, cosine 유사도 점수, 다른 모델 점수는 스케일이 달라 단순 합이 위험합니다. RRF는 “순위”만 쓰므로 **스케일 문제를 회피**하고, 다중 쿼리/하이브리드(희소+밀집) 조합에서 특히 안정적입니다. ([arc-labs.ai](https://arc-labs.ai/learn/reciprocal-rank-fusion?utm_source=openai))

### 4) Reranking (Cross-Encoder / ColBERT 류)
**정의**: 1차 검색(topK) 결과에 대해, query와 passage를 함께 넣고 **정밀한 relevance score**로 재정렬합니다. SemEval-2026에서도 cross-encoder reranking(BGE reranker 계열)을 파이프라인 후단에 붙이는 구성이 반복됩니다. ([arxiv.org](https://arxiv.org/abs/2605.12028?utm_source=openai))

- Cross-Encoder 장점: precision 상승, “lost in the middle” 완화(상위 문서의 진짜 관련도 정렬)
- 단점: **비용/지연**(topK에 비례)

2026년 실무/가이드 문서에서도 bge-reranker-v2-m3 같은 경량 cross-encoder reranker가 “쉽게 배치 가능한 기본 선택지”로 자주 언급됩니다. ([huggingface.co](https://huggingface.co/BAAI/bge-reranker-v2-m3/blob/refs%2Fpr%2F40/README.md?utm_source=openai))

---

## 💻 실전 코드
아래는 **현실적인 시나리오(사내 런북/장애 대응 문서 RAG)** 기준입니다.

- 코퍼스: Markdown/PDF에서 추출된 “장애 코드/증상/원인/조치” 문서
- 목표: 짧고 애매한 질문에도 **조치(runbook) 문서**를 안정적으로 상위로 올리기
- 구성: **Hybrid(BM25 + Dense) → (선택) HyDE/Query Expansion → RRF Fusion → Cross-Encoder Rerank → 상위 문서 컨텍스트로 생성**

> 주의: 아래 코드는 “toy 데이터 5줄”이 아니라, 실제 서비스에서 흔한 구성요소(벡터DB, BM25, reranker, fusion, gating)를 한 파일에서 재현 가능하게 구성했습니다. 모델/DB는 환경에 맞게 바꿔 끼우면 됩니다.

### 0) 설치/환경
```bash
pip install -U qdrant-client sentence-transformers transformers torch rank-bm25 numpy
# 선택: OpenAI/사내 LLM을 HyDE에 쓰려면 해당 SDK 추가
```

### 1) 인덱싱(오프라인) + 하이브리드 검색기 준비
```python
# rag_advanced.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple
import os, re
import numpy as np

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

# -----------------------------
# 데이터 구조
# -----------------------------
@dataclass
class Chunk:
    id: str
    title: str
    text: str
    source: str  # url/path
    tags: List[str]

def simple_tokenize(s: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9_./:-]+|[가-힣]+", s.lower())

# -----------------------------
# 벡터 인덱스(Qdrant) + BM25
# -----------------------------
class HybridIndex:
    def __init__(self, qdrant_url: str = "http://localhost:6333", collection: str = "runbooks"):
        self.client = QdrantClient(url=qdrant_url)
        self.collection = collection
        self.embedder = SentenceTransformer("BAAI/bge-m3")  # 다국어/범용 dense 임베딩 계열로 자주 사용
        self.chunks: List[Chunk] = []
        self.bm25 = None
        self.bm25_corpus_tokens = []

    def build(self, chunks: List[Chunk]):
        self.chunks = chunks
        # BM25 준비
        self.bm25_corpus_tokens = [simple_tokenize(c.title + "\n" + c.text) for c in chunks]
        self.bm25 = BM25Okapi(self.bm25_corpus_tokens)

        # Qdrant 컬렉션 생성
        dim = self.embedder.get_sentence_embedding_dimension()
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )

        # Dense 임베딩 업로드
        texts = [c.title + "\n" + c.text for c in chunks]
        vecs = self.embedder.encode(texts, normalize_embeddings=True, batch_size=64)
        points = [
            qm.PointStruct(
                id=i,
                vector=vecs[i].tolist(),
                payload={
                    "chunk_id": chunks[i].id,
                    "title": chunks[i].title,
                    "text": chunks[i].text,
                    "source": chunks[i].source,
                    "tags": chunks[i].tags,
                },
            )
            for i in range(len(chunks))
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    def dense_search(self, query: str, top_k: int = 30) -> List[Tuple[int, float]]:
        qv = self.embedder.encode([query], normalize_embeddings=True)[0].tolist()
        hits = self.client.search(collection_name=self.collection, query_vector=qv, limit=top_k)
        return [(h.id, float(h.score)) for h in hits]

    def bm25_search(self, query: str, top_k: int = 30) -> List[Tuple[int, float]]:
        q_tokens = simple_tokenize(query)
        scores = self.bm25.get_scores(q_tokens)
        idx = np.argsort(scores)[::-1][:top_k]
        return [(int(i), float(scores[i])) for i in idx]

    def get_payload(self, internal_id: int) -> Dict:
        # Qdrant에서 payload 조회 (간단히 search로 대체하지 않고, 여기선 local chunks로)
        c = self.chunks[internal_id]
        return {"chunk_id": c.id, "title": c.title, "text": c.text, "source": c.source, "tags": c.tags}


# -----------------------------
# RRF Fusion
# -----------------------------
def rrf_fuse(rank_lists: List[List[int]], k: int = 60, weights: List[float] | None = None) -> Dict[int, float]:
    # RRF(d) = Σ_i w_i / (k + rank_i(d))
    if weights is None:
        weights = [1.0] * len(rank_lists)
    scores: Dict[int, float] = {}
    for w, lst in zip(weights, rank_lists):
        for r, doc_id in enumerate(lst, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + w / (k + r)
    return scores

# -----------------------------
# Cross-Encoder Reranker (실행 가능)
# -----------------------------
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

class CrossEncoderReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", device: str | None = None):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()

    @torch.inference_mode()
    def rerank(self, query: str, docs: List[Dict], top_k: int = 8) -> List[Tuple[Dict, float]]:
        pairs = [(query, d["title"] + "\n" + d["text"]) for d in docs]
        inputs = self.tokenizer(
            pairs, padding=True, truncation=True, max_length=512, return_tensors="pt"
        ).to(self.device)
        logits = self.model(**inputs).logits.squeeze(-1)
        scores = logits.detach().cpu().numpy().tolist()

        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)[:top_k]
        return ranked

# -----------------------------
# (선택) HyDE / Query Expansion (여기선 "자리"를 명확히)
# -----------------------------
def should_expand(query: str) -> bool:
    # 운영에서 흔한 게이트: 짧거나(<=6 토큰), 에러코드/모호 키워드가 있으면 확장
    toks = simple_tokenize(query)
    if len(toks) <= 6:
        return True
    if re.search(r"\b(5\d\d|4\d\d)\b", query) or "timeout" in query.lower() or "permission" in query.lower():
        return True
    return False

def expand_queries_stub(query: str) -> List[str]:
    """
    실제로는 여기서:
    - LLM으로 multi-query 생성(RAG-Fusion 스타일)
    - 또는 HyDE: hypothetical doc 생성 후 그것을 '확장 쿼리'처럼 사용
    을 합니다.

    이 예제는 실행 가능성을 위해 rule-based 확장을 넣었습니다.
    (프로덕션에서는 사내 LLM / OpenAI / Vertex 등으로 교체)
    """
    base = query.strip()
    variants = [base]

    q = base.lower()
    if "timeout" in q:
        variants += [base + " read timeout", base + " connect timeout", base + " upstream timeout nginx"]
    if "permission" in q or "권한" in base:
        variants += [base + " 403", base + " RBAC", base + " IAM policy"]
    # 중복 제거
    seen, out = set(), []
    for v in variants:
        if v not in seen:
            seen.add(v); out.append(v)
    return out[:5]

# -----------------------------
# End-to-end 검색
# -----------------------------
def retrieve(index: HybridIndex, reranker: CrossEncoderReranker, query: str) -> List[Tuple[Dict, float]]:
    queries = expand_queries_stub(query) if should_expand(query) else [query]

    # 각 쿼리마다 hybrid(BM25 + Dense) 수행
    fused_rank_lists = []
    for q in queries:
        dense_ids = [doc_id for doc_id, _ in index.dense_search(q, top_k=30)]
        bm25_ids  = [doc_id for doc_id, _ in index.bm25_search(q, top_k=30)]
        # 쿼리 내부에서도 fusion (dense + bm25)
        scores = rrf_fuse([dense_ids, bm25_ids], k=60, weights=[1.0, 1.0])
        ranked = [doc_id for doc_id, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:30]]
        fused_rank_lists.append(ranked)

    # 쿼리 간 fusion (multi-query)
    multi_scores = rrf_fuse(fused_rank_lists, k=60)
    pre_candidates = [doc_id for doc_id, _ in sorted(multi_scores.items(), key=lambda x: x[1], reverse=True)[:30]]

    # payload 구성 후 rerank
    docs = [index.get_payload(i) for i in pre_candidates]
    reranked = reranker.rerank(query=query, docs=docs, top_k=8)
    return reranked

# -----------------------------
# 실행 예시
# -----------------------------
if __name__ == "__main__":
    # 현실적인 runbook chunk 예시(실제에선 사내 위키/Confluence/PDF에서 추출)
    chunks = [
        Chunk(
            id="rbk-101",
            title="Nginx upstream timeout(504) 대응 런북",
            text="증상: 504 Gateway Timeout...\n원인: upstream 서비스 read timeout...\n조치: proxy_read_timeout 조정, upstream 헬스체크...",
            source="wiki://runbooks/nginx-504",
            tags=["nginx","timeout","http-504"],
        ),
        Chunk(
            id="rbk-203",
            title="Kubernetes RBAC 권한 오류(403) 트러블슈팅",
            text="증상: Forbidden...\n원인: RoleBinding 누락...\n조치: kubectl auth can-i, 필요한 Role/ClusterRole 바인딩...",
            source="wiki://runbooks/k8s-rbac-403",
            tags=["k8s","rbac","permission"],
        ),
        # ... 수천개 chunk가 있다고 가정
    ]

    index = HybridIndex()
    index.build(chunks)

    reranker = CrossEncoderReranker()

    q = "nginx 504 timeout 해결"
    results = retrieve(index, reranker, q)

    print(f"QUERY: {q}\n")
    for i, (doc, score) in enumerate(results, 1):
        print(f"{i}. rerank_score={score:.4f}  title={doc['title']}  source={doc['source']}")
```

### 예상 출력(예)
```text
QUERY: nginx 504 timeout 해결

1. rerank_score=7.8123  title=Nginx upstream timeout(504) 대응 런북  source=wiki://runbooks/nginx-504
2. rerank_score=1.0345  title=Kubernetes RBAC 권한 오류(403) 트러블슈팅  source=wiki://runbooks/k8s-rbac-403
```

이 예제의 포인트는 “BM25 + Dense로 후보를 넓게 만들고(RRF로 스케일 이슈 회피) → Cross-Encoder가 최종 정렬”입니다. 이런 retrieve-then-rerank 구조는 실제 평가/대회/가이드에서도 반복 등장합니다. ([arxiv.org](https://arxiv.org/abs/2605.12028?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) HyDE/Query Expansion은 “항상”이 아니라 “게이트”로 운영
HyDE/다중쿼리는 recall을 올려주지만 query-time 비용이 큽니다(연산/지연/토큰비). HyDE의 오버헤드 문제는 2026년 연구에서도 계속 지적되며, 이를 줄이려는 HyPE 같은 변형도 등장했습니다. ([arxiv.org](https://arxiv.org/abs/2607.29402?utm_source=openai))  
따라서 실무에선:
- 짧은 질문, 에러코드, 낮은 1차 retrieval confidence 때만 확장
- 나머지는 기본 hybrid + rerank만

### Best Practice 2) Fusion은 점수 합이 아니라 RRF로(특히 hybrid/멀티쿼리)
BM25 점수와 dense cosine 점수는 분포가 다릅니다. RRF는 랭크 기반이라 스케일 이슈 없이 합치기 좋고, 다중 시스템/쿼리 결합에서 검증된 고전적 기법입니다. ([colab.ws](https://colab.ws/articles/10.1145/1571941.1572114?utm_source=openai))  
파라미터 `k`는 상위 랭크에 더 가중을 주는 정도를 조절합니다(일반적으로 60 근처가 자주 언급/사용).

### Best Practice 3) Reranker 예산(topK)은 “정답률 곡선” 보고 결정
Cross-encoder rerank는 topK에 비례해 비용이 증가합니다. 많은 팀이 `retrieve top 50~200 → rerank top 20~50 → context top 5~10` 같이 예산을 쪼갭니다. SemEval-2026 계열에서도 reranking stage를 별도로 두고(즉, 후보군을 먼저 좁힌 다음 정밀 모델을 태움) 리소스를 아낍니다. ([arxiv.org](https://arxiv.org/abs/2605.12028?utm_source=openai))

### 흔한 함정/안티패턴
- **HyDE 텍스트를 “근거 문서”처럼 프롬프트에 넣기**: HyDE는 검색을 위한 중간물일 뿐, 사실 근거가 아닙니다. (넣는 순간 환각이 “근거처럼” 강화될 수 있음)
- **reranker를 너무 앞단에 쓰기**: 후보군이 넓은 상태에서 cross-encoder를 돌리면 비용 폭발. 반드시 1차 retrieval로 좁힌 뒤 rerank.
- **다중쿼리 N을 무작정 늘리기**: recall은 오르지만 중복/노이즈도 같이 늘고, RRF 상위권이 흔들릴 수 있습니다. N=3~5에서 먼저 수렴을 확인하세요(운영 벤치로 결정).

### 비용/성능/안정성 트레이드오프(현실 체크)
- Query Expansion/HyDE: **recall↑**, 비용/지연↑, 노이즈↑(제어 필요)
- RRF Fusion: **안정성↑**, 구현 쉬움, 다만 “진짜 점수” 최적화는 아니라서 rerank가 사실상 마무리 역할
- Cross-Encoder Rerank: **precision↑** 가장 확실, 하지만 GPU/지연 예산이 핵심 제약
- 최신 흐름: HyDE류의 장점을 유지하면서 query-time 생성비용을 줄이려는 방향(HyPE 등) ([arxiv.org](https://arxiv.org/abs/2607.29402?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년형 “성능 지향 RAG”는 보통 다음 순서로 설계하면 실패 확률이 확 줄어듭니다.

1) **Hybrid retrieval**(BM25 + dense)로 후보군을 넓히고  
2) (필요할 때만) **Query Expansion / HyDE**로 recall을 추가로 끌어올린 뒤 ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))  
3) **RRF Fusion**으로 결과를 스케일 문제 없이 합치고 ([arc-labs.ai](https://arc-labs.ai/learn/reciprocal-rank-fusion?utm_source=openai))  
4) **Cross-Encoder reranker**로 최종 precision을 “확정”한다(특히 bge-reranker-v2-m3 같은 경량 모델이 배치 난이도를 낮춤). ([huggingface.co](https://huggingface.co/BAAI/bge-reranker-v2-m3/blob/refs%2Fpr%2F40/README.md?utm_source=openai))  

### 도입 판단 기준(프로젝트 적용 체크리스트)
- “정답 문서가 있는데 못 찾는” 비율이 높다 → Query Expansion/HyDE 우선
- “찾긴 찾는데 상위에 이상한 문서가 섞인다” → Reranking 우선
- hybrid/멀티쿼리를 섞을 계획이다 → Fusion은 RRF 기본값
- p95 지연/비용이 빡빡하다 → HyDE는 게이트로, reranker topK 예산부터 튜닝

### 다음 학습 추천
- HyDE 원 논문(질문-문서 갭을 어떻게 다루는지) ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))  
- RAG-Fusion/산업 적용에서의 fusion 교훈(멀티쿼리+RRF 운영 관점) ([arxiv.org](https://arxiv.org/abs/2603.02153?utm_source=openai))  
- HyDE의 오버헤드를 줄이려는 최신 변형(HyPE) ([arxiv.org](https://arxiv.org/abs/2607.29402?utm_source=openai))  

원하시면, 위 코드에 **(A) 실제 HyDE LLM 호출(OpenAI/Vertex/사내 vLLM)**을 붙이고, **(B) 평가셋으로 “HyDE on/off, rerank on/off, topK sweep” 자동 벤치 스크립트**까지 확장해 드릴게요.