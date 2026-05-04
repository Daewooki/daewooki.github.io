---
title: "HyDE × Reranking × Query Expansion: 2026년형 RAG 성능 최적화 “3단 부스터” 설계 가이드"
date: 2026-05-04 03:55:42 +0900
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
RAG 성능이 안 나오는 팀이 흔히 하는 오해는 “embedding 모델만 바꾸면 해결된다”입니다. 실제로는 **(1) 질문이 검색에 불리한 형태로 들어오고(짧고 모호함), (2) 1차 검색이 recall을 충분히 못 뽑고, (3) 최종으로 LLM에 들어가는 문서가 precision이 낮아서** 정답이 있어도 못 맞춥니다. 2026년 기준으로 현업에서 가장 재현성 있게 먹히는 처방이 **Query Transformation(확장/재작성/HyDE) → (하이브리드) 1차 검색 → Cross-Encoder Reranking**의 다단 파이프라인입니다. ([jacar.es](https://jacar.es/rag-hibrido-2026-patrones/?utm_source=openai))

**언제 쓰면 좋나**
- 사용자 질문이 짧고(예: “권한 에러 해결”), 문서 조각은 길고 구조적일 때(내부 위키/정책/기술 문서) → **HyDE/Query Expansion 효과가 큼** ([bestaiweb.ai](https://www.bestaiweb.ai/what-is-query-transformation-and-how-hyde-multi-query-and-step-back-prompting-improve-rag-recall/?utm_source=openai))  
- 1차 검색(top-k)에 “정답이 어딘가 있긴 한데” LLM이 못 보는 경우 → **Reranking이 가장 빠른 품질 상승 레버** ([scadea.com](https://scadea.com/rag-architecture-patterns-chunking-embedding-and-retrieval-strategies/?utm_source=openai))  
- 다국어/혼합 언어 검색(한국어+영어 API명) → **multilingual reranker/embedding 선택**이 중요 ([bestaiweb.ai](https://www.bestaiweb.ai/what-is-reranking-and-how-cross-encoders-rescore-retrieved-documents-for-better-precision/?utm_source=openai))  

**언제 쓰면 안 되나(또는 제한적으로)**
- **정확한 숫자/코드/키 값 매칭**이 핵심인 질의(재무 테이블, 정확한 파라미터 값 찾기): query expansion/HyDE가 오히려 의미를 퍼뜨릴 수 있고, BM25가 더 강할 때가 있음 ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))  
- 레이턴시 SLA가 빡센 실시간(수십 ms 단위): cross-encoder rerank는 보통 **추가 100ms~수백 ms**가 붙을 수 있어 단계적(cascade) 적용이 필요 ([docs.bswen.com](https://docs.bswen.com/blog/2026-02-25-best-reranker-models/?utm_source=openai))  

---

## 🔧 핵심 개념
### 1) HyDE (Hypothetical Document Embeddings)
**정의**: 사용자의 질문에서 바로 embedding을 뽑아 검색하지 않고, LLM으로 “그럴듯한 답변/문서 형태의 가상 문서(hypothetical document)”를 먼저 생성한 뒤, 그 텍스트를 embedding해서 검색하는 기법입니다. 질문(짧음)과 문서 청크(길고 설명적임) 사이의 **embedding space geometry gap**을 줄여 recall을 끌어올리는 게 목적입니다. ([bestaiweb.ai](https://www.bestaiweb.ai/what-is-query-transformation-and-how-hyde-multi-query-and-step-back-prompting-improve-rag-recall/?utm_source=openai))

**내부 흐름**
1. user query `q`
2. LLM이 `q`에 대한 “정답처럼 보이는” 설명 텍스트 `d_hypo` 생성 (여기서 중요한 건 *정답 여부가 아니라 문서 스타일/용어*를 맞추는 것)
3. embed(`d_hypo`) → 벡터 검색 → 후보 문서 집합 `C`
4. (옵션) 원래 `q`로도 검색해서 `C`와 merge

**차이점**
- 단순 query rewrite는 “질문을 더 좋은 질문으로” 바꾸는 반면, HyDE는 “질문을 **문서 형태의 프로브(probe)**로 바꿔 embedding이 잘 먹히게” 만듭니다. ([bestaiweb.ai](https://www.bestaiweb.ai/what-is-query-transformation-and-how-hyde-multi-query-and-step-back-prompting-improve-rag-recall/?utm_source=openai))  
- HyDE는 recall에 강하지만, 숫자/정확 매칭에서 확장 노이즈가 생길 수 있어 하이브리드(BM25 병행)나 후단 reranking이 사실상 세트입니다. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))  

### 2) Query Expansion / Multi-Query Retrieval
**정의**: 한 개의 질의로 top-k를 뽑지 말고, LLM(또는 규칙)으로 **3~6개 정도의 다양한 재작성/분해/동의어 확장 질의**를 만들고 각각 검색한 뒤 합칩니다. 과도한 확장은 후보를 폭증시켜 비용만 늘리므로 “적당히”가 핵심입니다. ([thegeocommunity.com](https://thegeocommunity.com/blogs/generative-engine-optimization/query-rewriting-multiquery-rag/?utm_source=openai))

**작동 방식(실전 관점)**
- `q1..qn` 생성 → 각 질의로 top-k_dense, top-k_bm25 → 합집합/중복제거 → RRF 같은 fusion → rerank
- expansion은 recall을 올리지만 precision은 떨어지기 쉬워서 **reranking이 브레이크 역할**을 합니다.

### 3) Reranking (Cross-Encoder)
**정의**: 1차 검색은 보통 bi-encoder(embedding similarity)라서 빠르지만 정밀도가 약합니다. reranker는 query-document를 **한 번에 입력으로 넣고** 점수를 매겨 상위 N개를 재정렬합니다. “LLM이 실제로 읽는 컨텍스트”를 결정하는 마지막 관문이라 효과가 큽니다. ([bestaiweb.ai](https://www.bestaiweb.ai/what-is-reranking-and-how-cross-encoders-rescore-retrieved-documents-for-better-precision/?utm_source=openai))

**2026년 실전 구도**
- 1차: cheap retriever(하이브리드 포함)로 top 50~200
- 2차: cross-encoder rerank로 top 5~10
- 이 패턴이 “진짜 운영되는 RAG”에서 가장 흔한 생존 패턴으로 수렴 중 ([jacar.es](https://jacar.es/rag-hibrido-2026-patrones/?utm_source=openai))  
- 오픈 가중치 쪽은 BGE reranker 계열이 실무 기본 선택지로 자주 언급됩니다(특히 multilingual). ([bestaiweb.ai](https://www.bestaiweb.ai/what-is-reranking-and-how-cross-encoders-rescore-retrieved-documents-for-better-precision/?utm_source=openai))  

---

## 💻 실전 코드
아래는 “사내 기술 위키(수천 문서) + Jira/Runbook” 같은 환경을 가정한 **현실적인** 파이프라인 예시입니다.

- 저장소: Elasticsearch(lexical/BM25) + Qdrant(vector)
- embedding: `sentence-transformers` (예시), reranker: `BAAI/bge-reranker-v2-m3` (multilingual)
- 질의 전략: (A) HyDE 1개 + (B) Multi-Query 3개 + (C) 원문 질의 1개
- 검색: 각 질의마다 BM25 top20 + Dense top20 → 합쳐서 RRF → 후보 60~120개
- rerank: 후보 중 상위 60개만 cross-encoder로 top8 추림 → LLM 입력

> 실제 운영에서는 embedding/LLM은 사내 표준(OpenAI/자체 서빙)로 바꾸면 됩니다. 핵심은 “단계”와 “k 설계”입니다.

### 0) 의존성/환경
```bash
pip install qdrant-client elasticsearch==8.* sentence-transformers transformers torch --upgrade
# Elasticsearch/Qdrant는 이미 떠 있다고 가정
```

### 1) HyDE + Multi-Query 생성기 (LLM 호출은 인터페이스만)
```python
# python
from dataclasses import dataclass
from typing import List, Dict
import re

@dataclass
class QueryPack:
    original: str
    hyde: str
    expansions: List[str]

class LLM:
    """운영에서는 OpenAI/사내 LLM SDK로 대체"""
    def generate(self, prompt: str) -> str:
        raise NotImplementedError

def build_hyde_prompt(q: str) -> str:
    return f"""You are writing a technical wiki paragraph that would answer the question.
Write a concise but information-dense passage (6~10 sentences) with relevant terms, commands, and error messages if applicable.
Question: {q}
Passage:"""

def build_multiquery_prompt(q: str) -> str:
    return f"""Generate 3 alternative search queries for retrieving internal engineering docs.
Rules:
- Preserve entities/product names/version numbers exactly.
- Prefer concrete keywords (error codes, components, file names).
- Output as bullet lines, no extra text.
Query: {q}"""

def parse_bullets(text: str) -> List[str]:
    lines = [re.sub(r"^[\-\*\d\.\)\s]+", "", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]

def make_query_pack(llm: LLM, q: str) -> QueryPack:
    hyde = llm.generate(build_hyde_prompt(q))
    mq_raw = llm.generate(build_multiquery_prompt(q))
    expansions = parse_bullets(mq_raw)[:3]
    return QueryPack(original=q, hyde=hyde, expansions=expansions)
```

### 2) 하이브리드 검색 + RRF fusion
```python
# python
from qdrant_client import QdrantClient
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer
import math

def rrf_fusion(rank_lists: List[List[str]], k: int = 60) -> Dict[str, float]:
    # Reciprocal Rank Fusion: score(d)=Σ 1/(k + rank)
    scores: Dict[str, float] = {}
    for lst in rank_lists:
        for i, doc_id in enumerate(lst, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + i)
    return scores

class HybridRetriever:
    def __init__(self, es: Elasticsearch, qdrant: QdrantClient, embed: SentenceTransformer,
                 es_index: str, qdrant_collection: str):
        self.es = es
        self.qdrant = qdrant
        self.embed = embed
        self.es_index = es_index
        self.qdrant_collection = qdrant_collection

    def bm25(self, query: str, topk: int = 20) -> List[str]:
        resp = self.es.search(index=self.es_index, size=topk, query={"match": {"content": query}})
        return [hit["_id"] for hit in resp["hits"]["hits"]]

    def dense(self, text: str, topk: int = 20) -> List[str]:
        vec = self.embed.encode(text, normalize_embeddings=True).tolist()
        hits = self.qdrant.search(collection_name=self.qdrant_collection, query_vector=vec, limit=topk)
        return [str(h.id) for h in hits]

    def retrieve_candidates(self, queries: List[str], topk_each: int = 20) -> List[str]:
        rank_lists = []
        for q in queries:
            rank_lists.append(self.bm25(q, topk_each))
            rank_lists.append(self.dense(q, topk_each))
        fused = rrf_fusion(rank_lists, k=60)
        # 상위 후보만 리턴
        return [doc_id for doc_id, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)[:120]]
```

### 3) Cross-Encoder Reranking → top-N 컨텍스트 구성
```python
# python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

class CrossEncoderReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", device: str = "cpu"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device)
        self.device = device

    @torch.no_grad()
    def rerank(self, query: str, docs: List[Dict], topn: int = 8) -> List[Dict]:
        # docs: [{"id":..., "content":...}, ...]
        pairs = [(query, d["content"]) for d in docs]
        inputs = self.tokenizer(
            [p[0] for p in pairs],
            [p[1] for p in pairs],
            padding=True, truncation=True, return_tensors="pt", max_length=1024
        ).to(self.device)
        scores = self.model(**inputs).logits.squeeze(-1).float().cpu().tolist()
        for d, s in zip(docs, scores):
            d["_rerank_score"] = s
        return sorted(docs, key=lambda x: x["_rerank_score"], reverse=True)[:topn]

# (예시) doc store는 ES/Qdrant/DB 어디든 가능. 여기선 인터페이스만.
class DocStore:
    def bulk_get(self, ids: List[str]) -> List[Dict]:
        raise NotImplementedError

def build_context(reranked: List[Dict]) -> str:
    # 운영에서는 metadata(제목/섹션/URL) 포함 권장
    blocks = []
    for d in reranked:
        blocks.append(f"[doc_id={d['id']} score={d['_rerank_score']:.3f}]\n{d['content']}")
    return "\n\n---\n\n".join(blocks)

def rag_retrieve(llm: LLM, retriever: HybridRetriever, store: DocStore, reranker: CrossEncoderReranker, q: str) -> str:
    pack = make_query_pack(llm, q)
    queries = [pack.original] + pack.expansions + [pack.hyde]   # original + multiquery + hyde
    cand_ids = retriever.retrieve_candidates(queries, topk_each=20)

    cand_docs = store.bulk_get(cand_ids[:60])  # reranker 비용 제어: 상위 60개만 읽기
    top_docs = reranker.rerank(pack.original, cand_docs, topn=8)
    return build_context(top_docs)
```

**예상 출력(형태)**
- 최종적으로 LLM에 들어갈 컨텍스트는 `doc_id/score`가 붙은 5~10개 블록
- 디버깅 시 “어떤 expansion/HyDE가 어떤 문서를 끌고 왔는지”까지 로깅하면 튜닝 속도가 급상승합니다(아래 팁 참고)

---

## ⚡ 실전 팁 & 함정
### Best Practice (품질/비용 대비 효율이 좋은 것)
1) **k를 키우는 순서**를 지키세요:  
   - 먼저 1차 후보를 충분히 넓히기(top50→top150) + 하이브리드 적용  
   - 그 다음 reranker로 topN 좁히기  
   이게 “비싸게 정밀하게”를 마지막에 쓰는 정석입니다. 2026년 다단 파이프라인(확장→후보→rerank)이 대회/실무에서 반복되는 이유도 이 구조가 비용 대비 안정적이라서입니다. ([arxiv.org](https://arxiv.org/abs/2602.16989?utm_source=openai))  

2) **multilingual / 도메인 적합성**을 모델 선택의 1순위로  
   reranker가 영어 MS MARCO 계열이면 한국어/도메인 문서에서 “rerank가 오히려 악화”될 수 있습니다. multilingual 지원 모델/데이터 적합성을 우선 확인하세요. ([bestaiweb.ai](https://www.bestaiweb.ai/what-is-reranking-and-how-cross-encoders-rescore-retrieved-documents-for-better-precision/?utm_source=openai))  

3) **HyDE는 “단독”이 아니라 “후보 생성기”로 취급**  
   HyDE 텍스트는 그럴듯하지만 틀릴 수 있습니다. 목적은 정답 생성이 아니라 검색 recall 증대입니다. 그래서 HyDE 결과는 **원문 질의 + 하이브리드 + rerank**로 안전장치를 걸어야 합니다. ([aussieai.com](https://www.aussieai.com/research/hyde?utm_source=openai))  

### 흔한 함정/안티패턴
- **expansion을 10개 이상 마구 생성**: 후보 폭증 → 비용/레이턴시 증가 + 노이즈로 precision 저하. 실무에서는 3~6개가 보통 “충분”하다는 경험칙이 반복 언급됩니다. ([thegeocommunity.com](https://thegeocommunity.com/blogs/generative-engine-optimization/query-rewriting-multiquery-rag/?utm_source=openai))  
- **reranker 입력 문서가 너무 길거나(토큰 초과) 너무 짧은 경우**: 긴 문서는 잘려서 핵심이 날아가고, 짧은 문서는 근거가 부족해 점수가 흔들립니다. “reranker용 chunk 길이”를 별도로 설계하거나(예: 300~800 tokens) 섹션 단위로 재청킹하세요.  
- **정확 질의(숫자/테이블)에도 HyDE/확장을 강제**: 금융/테이블 문서에서는 BM25가 이기거나, 확장이 제한적 이득만 보일 수 있습니다. 이런 쿼리는 규칙으로 분기(정규식으로 숫자/티커/키 감지)해서 lexical 비중을 올리는 게 낫습니다. ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))  

### 비용/성능/안정성 트레이드오프
- reranking은 품질 레버지만 레이턴시를 먹습니다(수십~수백 ms 추가 가능). ([docs.bswen.com](https://docs.bswen.com/blog/2026-02-25-best-reranker-models/?utm_source=openai))  
- 해결책은 **cascade reranking**(가벼운 모델로 top50→top15, 무거운 모델로 top15→top5) 또는 “rerank는 상위 후보 60개만” 같은 상한선입니다. (코드에서 `cand_ids[:60]`가 그 지점)

---

## 🚀 마무리
HyDE, Query Expansion, Reranking은 각각이 아니라 **“Recall을 넓히고(전처리+하이브리드), Precision을 마지막에 조여서( rerank ) LLM이 읽을 문서를 확정”**하는 한 세트로 봐야 성능이 안정적으로 올라갑니다. 2026년에도 하이브리드+rerank 패턴이 살아남는 이유가 여기에 있습니다. ([jacar.es](https://jacar.es/rag-hibrido-2026-patrones/?utm_source=openai))  

**도입 판단 기준(현업 체크리스트)**
- top-k(예: 20) 안에 정답이 *가끔* 보이는데 LLM이 못 맞춘다 → **reranking부터**  
- 정답이 top-k에 잘 안 보인다(“없음”이 많다) → **HyDE/expansion + 하이브리드 + k 확대**  
- 숫자/키 기반 질의가 많다 → **BM25 가중/메타필터** 먼저, HyDE는 제한적 적용 ([arxiv.org](https://arxiv.org/abs/2604.01733?utm_source=openai))  

**다음 학습 추천**
- 다단 검색 파이프라인의 ablation(어느 단계가 이득인지) 사례를 보고 싶다면, 멀티스테이지(확장→BM25→dense→rerank)로 기여도를 분석한 최신 리트리벌 파이프라인 논문/리포트를 참고하세요. ([arxiv.org](https://arxiv.org/abs/2602.16989?utm_source=openai))  
- reranker 모델 선택/비교 관점은 2026년 기준 오픈/상용 옵션 비교 글과 리더보드가 도움이 됩니다. ([agentset.ai](https://agentset.ai/rerankers?utm_source=openai))