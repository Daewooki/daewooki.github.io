---
title: "RAG가 “거의 맞는데” 마지막 10%가 안 오를 때: HyDE × Reranking × Query Expansion 실전 최적화 가이드 (2026년 6월)"
date: 2026-06-10 04:24:54 +0900
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
프로덕션 RAG에서 가장 흔한 실패 패턴은 단순합니다. **정답 문서가 인덱스에 존재하는데도 LLM이 못 봅니다.** 이유는 대개 (1) query가 코퍼스 표현과 어긋나거나, (2) 1차 retrieval이 후보를 충분히 못 모으거나(Recall 문제), (3) 후보는 모였는데 top-k에 못 올라오는(Precision 문제) 케이스입니다. 이때 2026년 기준으로 “질을 올리는” 대표 레버가 **HyDE(가상 문서 기반 retrieval), Reranking(2단계 정밀 정렬), Query Expansion/Rewrite(질의 재작성/다중 질의)** 조합입니다. TREC RAG 2025 1위 시스템도 HyDE와 hybrid retrieval, reranking을 묶어서 성과를 냈고, HyDE embedding과 원 query embedding을 섞는 **HyDE Vector Mix** 같은 실용적 변형까지 제시합니다. ([trec.nist.gov](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf))

언제 쓰면 좋나:
- **질문이 애매하거나 짧고**, 문서 표현이 다양해 “표현 불일치”가 큰 도메인(내부 위키/설계문서/정책/FAQ)
- **멀티턴 대화**에서 대명사/생략이 많아 query 자체가 retrieval에 부적합한 경우(standalone rewrite 필요) ([docs.nvidia.com](https://docs.nvidia.com/rag/latest/multiturn.html))
- top-k 컨텍스트가 “거의 맞는데” **정답 chunk가 20~200위에 숨어있는** 경우(= reranking이 가장 잘 먹힘)

언제 쓰면 안 되나(혹은 제한적으로):
- **정밀 숫자/표 기반 질의(재무/지표/정책 조항 번호)**: 2026년 벤치마크에서 HyDE·multi-query 같은 expansion이 “정확한 수치 질의”에는 이득이 제한적이라는 보고가 있습니다. 이런 경우 BM25/hybrid + reranking이 더 일관되게 유리합니다. ([arxiv.org](https://arxiv.org/abs/2604.01733))
- latency/budget가 빡센 서비스에서 multi-query를 무제한으로 쓰는 것(LLM 호출/검색 호출 폭증)

---

## 🔧 핵심 개념
### 1) HyDE (Hypothetical Document Embeddings)
**HyDE**는 “query를 그대로 embed”하지 않고, LLM으로 query에 대한 **가상의 답변/문서(= hypothetical document)** 를 생성한 뒤 그 텍스트를 embedding해서 retrieval에 쓰는 기법입니다. 요지는 *query → (LLM) 가상 문서 → embedding → vector search* 로, query가 너무 짧거나 키워드가 빈약할 때 “문서처럼 생긴” 텍스트로 의미 신호를 증폭합니다. ([emergentmind.com](https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde?utm_source=openai))

실무적으로 중요한 포인트는 HyDE가 “사실”을 만들려고 하는 게 아니라, **retrieval space에서 가까워질 표현을 만들어내는 것**입니다. 그래서 TREC RAG 2025에서는 원 query embedding과 HyDE embedding을 섞는 **mixing ratio α**를 두고, query 타입에 따라 최적 α가 다를 수 있다고 분석합니다. ([trec.nist.gov](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf))  
→ 즉, HyDE는 “항상 on”이 아니라 **게이팅/믹싱**이 핵심입니다.

### 2) Reranking (2-stage retrieval의 정석)
대부분의 프로덕션 RAG는 이제 “1차(cheap)로 많이 뽑고, 2차(expensive)로 정확히 줄이는” 구조가 기본입니다. 1차는 dense/sparse/hybrid로 50~200개 후보를 모으고, 2차에서 **cross-encoder reranker**가 query-문서 쌍을 직접 읽고 점수화해 top-k를 재정렬합니다. 이 패턴은 SemEval-2026 MTRAGEval 제출 시스템에서도 **query rewriting → hybrid(BM25+dense, RRF) → cross-encoder reranking(BGE reranker)** 로 명확히 나타납니다. ([arxiv.org](https://arxiv.org/abs/2605.12028))

왜 cross-encoder가 강한가?
- bi-encoder(embedding)는 query와 문서를 **독립적으로** 벡터화해 근사 유사도를 봅니다.
- cross-encoder는 query와 문서를 **동시에** 넣고 attention으로 상호작용을 보며 “이 문서가 이 질문에 답이 되는가”를 직접 학습해 점수화합니다.  
대신 비용은 큽니다(후보 개수 × 모델 추론).

### 3) Query Expansion / Query Rewriting / Multi-Query
여기서 용어가 섞이기 쉬운데, 실무 관점에서 이렇게 나누면 판단이 쉽습니다.

- **Query Rewriting(standalone rewrite)**: 멀티턴에서 “그거/저거/거기” 같은 지시어를 풀어 **독립 질의**로 바꿈. NVIDIA RAG blueprint도 “정확도는 올라가지만 LLM 호출로 latency가 추가된다”는 점을 명시합니다. ([docs.nvidia.com](https://docs.nvidia.com/rag/latest/multiturn.html))
- **Multi-Query(다중 질의 확장)**: 같은 의도를 다양한 표현으로 N개 질의로 만들어 각각 retrieval한 뒤 합치고(rerank/fusion) 최종 top-k를 뽑음. recall에 강하지만 비용이 폭증합니다.
- **Keyword Expansion(BM25 보강)**: sparse retrieval의 약점을 보완하기 위해 동의어/연관어를 생성해 BM25 query를 확장. TREC RAG 2025에서도 “BM25 query expansion용 키워드 생성 프롬프트”를 별도로 둡니다. ([trec.nist.gov](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf))

핵심 차이:
- **HyDE는 ‘문서형 텍스트’를 만들어 dense 신호를 강화**
- **Query expansion은 ‘질의 표현’을 늘려 recall을 넓힘**
- **Reranking은 후보를 “정답 우선”으로 정렬해 precision을 올림**

---

## 💻 실전 코드
아래는 “내부 기술문서(Confluence/Notion export/Markdown) + Qdrant + hybrid + HyDE mix + cross-encoder rerank”를 한 번에 엮는 현실적인 파이프라인 예시입니다. 포인트는 **(1) hybrid로 후보 풀을 넓히고, (2) HyDE는 mix로 과신을 막고, (3) rerank는 top-N 후보에만 적용**하는 것입니다.

### 0) 의존성/환경
```bash
python -m venv .venv && source .venv/bin/activate
pip install qdrant-client "fastembed>=0.3.0" sentence-transformers rank-bm25 openai python-dotenv
```

- Qdrant: vector store
- fastembed: 빠른 embedding(로컬)
- sentence-transformers: cross-encoder reranker
- rank-bm25: 로컬 BM25(예시는 간단화를 위해 인메모리; 실무에선 Elasticsearch/OpenSearch 권장)
- openai: HyDE/rewriting용 LLM(다른 LLM으로 대체 가능)

### 1) 인덱싱(현실 시나리오: “제품 장애 대응 런북 + 설계 문서”)
```python
# rag_advanced.py
import os
from dataclasses import dataclass
from typing import List, Dict, Tuple

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from fastembed import TextEmbedding

from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from openai import OpenAI


@dataclass
class Chunk:
    id: str
    text: str
    meta: Dict


class AdvancedRAG:
    def __init__(
        self,
        qdrant_url: str,
        collection: str = "runbooks",
        embed_model: str = "BAAI/bge-small-en-v1.5",
        reranker_model: str = "BAAI/bge-reranker-v2-m3",
    ):
        self.collection = collection
        self.qdrant = QdrantClient(url=qdrant_url)
        self.embedder = TextEmbedding(model_name=embed_model)
        self.reranker = CrossEncoder(reranker_model)  # cross-encoder
        self.llm = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        self._bm25 = None
        self._bm25_chunks: List[Chunk] = []

    def create_collection(self, dim: int):
        self.qdrant.recreate_collection(
            collection_name=self.collection,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )

    def index(self, chunks: List[Chunk]):
        # 1) dense index
        texts = [c.text for c in chunks]
        vecs = list(self.embedder.embed(texts))
        dim = len(vecs[0])
        self.create_collection(dim)

        points = []
        for c, v in zip(chunks, vecs):
            points.append(
                qm.PointStruct(
                    id=c.id,
                    vector=v,
                    payload={"text": c.text, **c.meta},
                )
            )
        self.qdrant.upsert(collection_name=self.collection, points=points)

        # 2) bm25 index (toy 아님: 실무에선 문서량 커지면 ES로 대체)
        tokenized = [t.lower().split() for t in texts]
        self._bm25 = BM25Okapi(tokenized)
        self._bm25_chunks = chunks

    def _hyde(self, query: str) -> str:
        prompt = (
            "Generate a hypothetical answer (~150 words) to improve dense retrieval. "
            "It does NOT need to be factually correct. Avoid specific numbers/dates.\n\n"
            f"Query: {query}"
        )
        r = self.llm.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        return r.output_text

    def _rewrite_standalone(self, query: str, history: List[Tuple[str, str]]) -> str:
        # 멀티턴이면 rewrite, 아니면 원문 유지
        if not history:
            return query
        hist = "\n".join([f"User: {u}\nAssistant: {a}" for u, a in history[-2:]])
        prompt = (
            "Rewrite the user's last question into a standalone search query. "
            "Preserve constraints and identifiers. Output ONLY the rewritten query.\n\n"
            f"{hist}\n\nUser: {query}"
        )
        r = self.llm.responses.create(model="gpt-4.1-mini", input=prompt)
        return r.output_text.strip()

    def _dense_search(self, query_vec, top_n: int) -> List[Tuple[str, float, Dict]]:
        res = self.qdrant.search(
            collection_name=self.collection,
            query_vector=query_vec,
            limit=top_n,
            with_payload=True,
        )
        return [(str(p.id), float(p.score), p.payload) for p in res]

    def _bm25_search(self, query: str, top_n: int) -> List[Tuple[str, float, Dict]]:
        scores = self._bm25.get_scores(query.lower().split())
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_n]
        out = []
        for idx, s in ranked:
            c = self._bm25_chunks[idx]
            out.append((c.id, float(s), {"text": c.text, **c.meta}))
        return out

    def _rrf_fuse(self, runs: List[List[Tuple[str, float, Dict]]], k: int = 60) -> List[Tuple[str, float, Dict]]:
        # Reciprocal Rank Fusion: score = sum 1/(k + rank)
        # TREC 계열에서 널리 쓰는 간단/강력한 fusion ([trec.nist.gov](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf))
        agg: Dict[str, Tuple[float, Dict]] = {}
        for run in runs:
            for rank, (doc_id, _score, payload) in enumerate(run, start=1):
                rrf = 1.0 / (k + rank)
                if doc_id not in agg:
                    agg[doc_id] = (0.0, payload)
                agg[doc_id] = (agg[doc_id][0] + rrf, payload)

        fused = [(doc_id, sc, payload) for doc_id, (sc, payload) in agg.items()]
        fused.sort(key=lambda x: x[1], reverse=True)
        return fused

    def answer(
        self,
        query: str,
        history: List[Tuple[str, str]] = None,
        dense_top: int = 80,
        bm25_top: int = 80,
        rerank_top: int = 40,
        final_k: int = 6,
        hyde_alpha: float = 0.35,  # HyDE mix ratio (0~1)
    ):
        history = history or []

        q = self._rewrite_standalone(query, history)  # multiturn 대응 ([docs.nvidia.com](https://docs.nvidia.com/rag/latest/multiturn.html))

        # HyDE vector mix: v = (1-a)*v(q) + a*v(hyde(q)) ([trec.nist.gov](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf))
        q_vec = list(self.embedder.embed([q]))[0]
        hyde_txt = self._hyde(q)
        h_vec = list(self.embedder.embed([hyde_txt]))[0]
        mix_vec = [(1 - hyde_alpha) * a + hyde_alpha * b for a, b in zip(q_vec, h_vec)]

        dense_run = self._dense_search(mix_vec, top_n=dense_top)
        bm25_run = self._bm25_search(q, top_n=bm25_top)

        # hybrid + fusion
        fused = self._rrf_fuse([dense_run, bm25_run])

        # rerank: fused 상위 rerank_top만 cross-encoder로 점수화
        candidates = fused[:rerank_top]
        pairs = [(q, c[2]["text"]) for c in candidates]
        rerank_scores = self.reranker.predict(pairs)

        rescored = []
        for (doc_id, _sc, payload), s in zip(candidates, rerank_scores):
            rescored.append((doc_id, float(s), payload))
        rescored.sort(key=lambda x: x[1], reverse=True)
        top_ctx = rescored[:final_k]

        # 예상 출력(컨텍스트)
        print("=== Retrieved Context (top) ===")
        for i, (doc_id, s, p) in enumerate(top_ctx, 1):
            print(f"{i}. score={s:.4f} id={doc_id} title={p.get('title')}")
        return top_ctx


if __name__ == "__main__":
    # 현실적인 chunk 예시(짧게만)
    chunks = [
        Chunk("1", "Runbook: Kafka consumer lag spikes after deploy... mitigation: scale consumers, check rebalance, ...", {"title": "Kafka Lag Runbook"}),
        Chunk("2", "Design: Request routing uses consistent hashing. Edge cache TTL policy ...", {"title": "Routing Design"}),
        Chunk("3", "Postmortem 2026-02: elevated 5xx due to connection pool exhaustion; fix: tune maxPoolSize ...", {"title": "5xx Postmortem"}),
        # ... 실제로는 수천~수만 chunk
    ]

    rag = AdvancedRAG(qdrant_url="http://localhost:6333")
    rag.index(chunks)

    rag.answer(
        "배포 후 특정 서비스에서 5xx가 늘고 latency도 튀는데, connection pool 관련 점검 포인트가 뭐였지?",
        history=[("어제 배포한 결제 서비스가 불안정해.", "어떤 증상이야?")],
    )
```

### 2) 왜 이 구성이 “실무형”인가
- **rewrite(멀티턴) → hybrid 후보 풀 확대 → rerank로 top-k 정제**는 2026년 대회/블루프린트류에서 반복되는 패턴입니다. ([docs.nvidia.com](https://docs.nvidia.com/rag/latest/multiturn.html))  
- HyDE는 “올인”이 아니라 **mix(α)** 로 제어해야 하며, query 타입별 최적이 다를 수 있다는 관찰이 있습니다. ([trec.nist.gov](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf))
- 숫자 정밀 질의에서는 HyDE/multi-query가 제한적일 수 있으니, 이 코드처럼 **BM25 채널을 반드시 남겨두는 hybrid**가 안전합니다. ([arxiv.org](https://arxiv.org/abs/2604.01733))

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **Reranker는 “정답이 후보에 들어오는가”가 전제**
- rerank는 recall을 만들지 못합니다. 먼저 hybrid(RRF)나 multi-query로 후보 풀(50~200)을 안정적으로 만들고, rerank는 그 위에 얹으세요. SemEval-2026 파이프라인도 이 순서를 따릅니다. ([arxiv.org](https://arxiv.org/abs/2605.12028))

2) **HyDE는 숫자/고유명사에 약해질 수 있으니 ‘제약 프롬프트’가 필수**
- HyDE 텍스트에 구체 수치/날짜를 마구 생성하면 embedding이 “그럴듯한데 틀린 디테일” 쪽으로 끌려가 drift가 납니다.
- 그래서 예시 코드처럼 “Avoid specific numbers/dates” 같은 제약을 걸고, α를 낮게(예: 0.2~0.4) 시작한 뒤 오프라인 평가로 올리세요. (TREC 시스템도 α를 튜닝 대상으로 둡니다.) ([trec.nist.gov](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf))

3) **멀티턴은 history를 retrieval에 넣지 말고, rewrite로 ‘독립 질의’를 만들기**
- NVIDIA RAG blueprint는 query rewriting이 “best retrieval accuracy”를 주지만 LLM 호출로 latency가 늘어난다고 명시합니다. 즉, 정확도/지연의 교환을 의도적으로 선택해야 합니다. ([docs.nvidia.com](https://docs.nvidia.com/rag/latest/multiturn.html))

### 흔한 함정/안티패턴
- **multi-query를 top-k마다 다 돌려버리기**: N개의 질의 × (dense+BM25) × rerank까지 겹치면 비용이 기하급수로 증가합니다. expansion은 “애매한 query에서만” 게이팅하세요.
- **rerank에 너무 큰 chunk를 그대로 넣기**: cross-encoder는 입력 길이에 민감합니다. “문단 단위 chunk + title/section header prepend” 정도가 대체로 안정적입니다.
- **도메인/언어 미스매치**: reranker가 영어 위주 데이터로 학습된 경우 한국어/사내 약어에서 역효과가 날 수 있습니다. (모델/도메인 적합성 검증 없이 rerank on은 금물)

### 비용/성능/안정성 트레이드오프
- 성능(정확도) 순 대체로: **hybrid + rerank > 단일 dense > 단일 BM25** (단, 금융/표처럼 sparse가 강한 코퍼스는 예외) ([arxiv.org](https://arxiv.org/abs/2604.01733))
- 비용(지연) 순: **multi-query/HyDE(LLM 추가 호출)** 가 가장 비싸고, 그 다음이 rerank(후보 수에 비례), 그 다음이 1차 retrieval입니다.
- 안정성은 “게이팅”으로 확보합니다: (a) HyDE는 query 타입별 on/off, (b) rerank는 후보 수 제한, (c) multi-query는 실패 시 원 query fallback.

---

## 🚀 마무리
정리하면, 2026년 6월 시점의 RAG 성능 최적화는 “새 임베딩 하나 갈아끼우기”보다 **파이프라인을 2~3단으로 구조화**하는 쪽이 더 큰 이득을 줍니다.

- **Recall 문제**면: query rewriting / keyword expansion / HyDE / multi-query로 후보 풀을 넓히고  
- **Precision 문제**면: cross-encoder **reranking**으로 top-k를 정제하세요  
- 단, **정밀 숫자 질의**는 HyDE·multi-query가 제한적일 수 있으니 BM25/hybrid 채널을 유지하는 게 안전합니다. ([arxiv.org](https://arxiv.org/abs/2604.01733))  
- HyDE는 “항상 on”이 아니라, TREC RAG 2025의 HyDE Vector Mix처럼 **α 믹싱/게이팅**이 실무적으로 핵심입니다. ([trec.nist.gov](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf))

다음 학습 추천(바로 실무로 이어지는 순서):
1) 내 서비스 쿼리를 “대화형/서술형/정밀수치형”으로 분류하고, 타입별로 **rewrite/HyDE/multi-query 게이팅 규칙** 만들기  
2) hybrid(RRF) + rerank의 후보 수(dense_top, bm25_top, rerank_top)를 바꿔가며 **Recall@k / MRR / latency**를 같이 튜닝하기 ([trec.nist.gov](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf))  
3) 최종적으로는 “좋은 retrieval이면 generation은 따라온다”가 아니라, **retrieval-then-rerank-then-cite**까지 포함한 E2E 평가 루프를 붙이기

원하시면, 당신의 코퍼스 특성(문서 길이/언어/표 포함 여부/평균 query 길이/실시간성)과 현재 지연 예산을 기준으로 **HyDE α 범위, rerank 후보 수, multi-query 개수**를 구체적인 튜닝 플랜으로 내려드릴게요.