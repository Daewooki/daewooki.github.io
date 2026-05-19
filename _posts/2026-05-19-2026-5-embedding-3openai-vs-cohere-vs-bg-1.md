---
title: "2026년 5월, Embedding 모델 3파전(OpenAI vs Cohere vs BGE-M3): “우리 도메인”에서 이기는 선택법"
date: 2026-05-19 04:14:27 +0900
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
Embedding 모델을 고르는 일은 결국 **검색 품질(Recall/Precision)**, **운영 비용(토큰/스토리지/인덱싱)**, **데이터 거버넌스(외부 API vs 온프레)**를 동시에 최적화하는 문제입니다. 특히 RAG/semantic search에서 “LLM이 똑똑해도 답이 엉뚱한” 원인의 상당수는 **retrieval이 틀린 것**(=embedding/인덱스/쿼리 설계 실패)에서 시작합니다.

**언제 쓰면 좋은가**
- 문서 검색/FAQ/티켓/코드 검색처럼 “의미 기반으로 비슷한 것을 찾는” 문제가 있고,
- BM25 같은 lexical 검색만으로는 동의어/표현 차이를 못 잡아 Recall이 떨어질 때
- 사용자 질의가 짧고 다양(챗봇 질문, 고객 문의)하며, 운영 중 지속적으로 평가/튜닝할 때

**언제 쓰면 안 되는가(혹은 단독으로 쓰면 안 되는가)**
- SKU, 모델명, 날짜, 고유명사, 약어가 중요한 도메인(커머스/부품/의료 코드/사내 약어 등)에서 **embedding-only**로 1차 후보를 만들면 “조용히” 망가집니다. 이 경우 **BM25(또는 sparse) + dense** 하이브리드가 안전합니다. (BGE-M3는 이 지점을 모델 레벨에서 한 번에 풀 수 있게 설계됨) ([llmreference.com](https://www.llmreference.com/model/bge-m3?utm_source=openai))
- 이미 프로덕션에 수백만 벡터가 쌓여 있는데 모델을 바꾸려는 경우: **모델이 바뀌면 벡터 공간이 바뀌어 재임베딩이 필수**라 마이그레이션 비용/다운타임 설계를 먼저 해야 합니다. ([reddit.com](https://www.reddit.com/r/n8n/comments/1stcjlu/error_supabase_pgvector/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) “Embedding 비교”에서 진짜 봐야 할 축
많은 팀이 “벤치마크 1등”만 보고 고르는데, 실무에서는 아래 축이 더 결정적입니다.

- **Vector 공간의 압축 전략**
  - OpenAI `text-embedding-3-large`/`3-small`은 기본 차원이 크지만, `dimensions` 파라미터로 **차원 축소(=Matryoshka-style truncation)**를 지원해서 벡터DB 제약(예: 1024 dim 제한)이나 비용(스토리지/인덱스)을 맞추기 쉽습니다. ([openai.com](https://openai.com/blog/new-embedding-models-and-api-updates?hss_channel=lis-l2XDk_NCpt&utm_source=openai))
  - Cohere Embed는 **int8/binary 같은 “압축된 embedding 타입”을 네이티브로 지원**해 대규모 코퍼스에서 스토리지/캐시 비용이 강점이 됩니다. ([docs.cohere.com](https://docs.cohere.com/docs/embeddings?utm_source=openai))

- **다국어/코드스위칭 내구성**
  - OpenAI `text-embedding-3-large`는 영어/비영어 모두에 강한 범용 모델로 안내됩니다. ([developers.openai.com](https://developers.openai.com/api/docs/models/text-embedding-3-large?utm_source=openai))
  - Cohere는 영어/멀티링구얼을 모델 라인업으로 명확히 분리하고(v3 계열), 멀티링구얼에서 실무 사례가 많이 언급됩니다. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed?utm_source=openai))
  - BGE-M3는 “멀티링구얼 + 멀티 기능(dense/sparse/multi-vector)”을 한 모델이 동시에 제공하는 설계가 핵심입니다. ([arxiv.org](https://arxiv.org/abs/2402.03216?utm_source=openai))

- **하이브리드(lexical + semantic) 구성이 쉬운가**
  - OpenAI/Cohere는 기본적으로 dense 벡터 중심이라, BM25를 별도 파이프라인으로 붙여야 합니다.
  - BGE-M3는 논문/모델 카드 기준으로 dense뿐 아니라 **sparse(lexical weights) + ColBERT-style multi-vector**까지 한 번에 낼 수 있어, “브랜드명/ID/숫자” 같은 lexical 신호를 같이 가져가기 유리합니다. ([llmreference.com](https://www.llmreference.com/model/bge-m3?utm_source=openai))

### 2) 내부 작동 흐름(실무 관점)
Embedding 기반 검색의 흐름은 단순합니다. 다만 “어디서 정보가 소실되는지”를 알아야 튜닝이 됩니다.

1. **문서 전처리/Chunking**
   - 문서를 chunk로 나누는 순간, 모델은 chunk 단위 의미만 담습니다.
   - 즉 “정답이 들어있는 chunk가 후보로 안 올라오면” LLM은 절대 맞출 수 없습니다.

2. **임베딩 생성**
   - OpenAI: 기본 `text-embedding-3-small`=1536, `3-large`=3072 차원, 필요 시 `dimensions`로 줄임. ([platform.openai.com](https://platform.openai.com/docs/guides/embeddings/embedding-models%20.class?utm_source=openai))
   - Cohere: 모델별로 차원 선택(256/512/1024/1536) 및 int8/binary 같은 embedding 타입 선택 가능. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed?utm_source=openai))
   - BGE-M3: dense/sparse/multi-vector를 함께 산출하는 멀티-헤드 성격(구현체에 따라 반환 형태 상이). ([llmreference.com](https://www.llmreference.com/model/bge-m3?utm_source=openai))

3. **Vector DB 인덱싱 & 검색**
   - cosine/dot 같은 근접도 기반 ANN 검색.
   - 압축(int8/binary) 또는 차원 축소를 하면 비용이 줄지만, **도메인별로 손실이 다르게** 나타납니다(짧은 쿼리/고유명사 위주면 손실이 커질 수 있음).

4. **Rerank(선택)**
   - embedding은 1차 후보 생성용, 최종 정확도는 reranker가 책임지는 구조가 일반적.
   - 이 글의 범위는 embedding 비교지만, 실무에서는 “embedding 바꾸기 전에” chunk/top_k/rerank 유무를 먼저 고정하고 비교해야 합니다(평가 드리프트 방지).

---

## 💻 실전 코드
아래 예제는 “사내 기술문서/티켓” 코퍼스에서 **OpenAI vs Cohere vs BGE-M3를 같은 조건으로 비교**하고, **도메인별 선택을 위한 오프라인 평가 세트**까지 굴리는 현실적인 형태를 목표로 합니다.

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install -U openai cohere \
  sentence-transformers torch \
  numpy pandas tqdm scikit-learn

# (선택) 벡터DB 대신 로컬 FAISS를 쓰려면
pip install faiss-cpu
```

### 1) 공통 데이터 형태(문서/질문-정답 쌍)
```python
# file: eval_embeddings.py
import os, json
from dataclasses import dataclass
from typing import List, Dict, Tuple
import numpy as np
from tqdm import tqdm

@dataclass
class Doc:
    doc_id: str
    text: str
    meta: Dict

@dataclass
class QA:
    qid: str
    query: str
    relevant_doc_ids: List[str]  # 최소 1개 이상

def load_corpus(path: str) -> List[Doc]:
    # 예: 사내 위키/티켓을 chunking해서 만든 JSONL
    docs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            docs.append(Doc(obj["doc_id"], obj["text"], obj.get("meta", {})))
    return docs

def load_qas(path: str) -> List[QA]:
    qas = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            qas.append(QA(obj["qid"], obj["query"], obj["relevant_doc_ids"]))
    return qas

def l2_normalize(x: np.ndarray) -> np.ndarray:
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-12)

def recall_at_k(ranked_doc_ids: List[str], relevant: set, k: int) -> float:
    return 1.0 if len(relevant.intersection(ranked_doc_ids[:k])) > 0 else 0.0

def mrr_at_k(ranked_doc_ids: List[str], relevant: set, k: int) -> float:
    for i, did in enumerate(ranked_doc_ids[:k], start=1):
        if did in relevant:
            return 1.0 / i
    return 0.0

def brute_force_search(query_vecs: np.ndarray, doc_vecs: np.ndarray, doc_ids: List[str], top_k=20):
    # cosine 유사도: normalize 후 dot
    q = l2_normalize(query_vecs)
    d = l2_normalize(doc_vecs)
    sims = q @ d.T
    idx = np.argsort(-sims, axis=1)[:, :top_k]
    return [[doc_ids[j] for j in row] for row in idx]
```

### 2) OpenAI / Cohere / BGE-M3 임베더 구현
핵심은 “동일한 chunk, 동일한 평가셋”에 대해 임베딩만 갈아끼우는 구조입니다.

```python
# file: embedders.py
import os
import numpy as np

# OpenAI
from openai import OpenAI

# Cohere
import cohere

# BGE-M3 (local)
from sentence_transformers import SentenceTransformer

class OpenAIEmbedder:
    def __init__(self, model="text-embedding-3-large", dimensions=None):
        self.client = OpenAI()
        self.model = model
        self.dimensions = dimensions

    def embed(self, texts):
        kwargs = {"model": self.model, "input": texts}
        # OpenAI는 dimensions로 벡터 길이 축소 가능 ([platform.openai.com](https://platform.openai.com/docs/guides/embeddings/embedding-models%20.class?utm_source=openai))
        if self.dimensions is not None:
            kwargs["dimensions"] = self.dimensions
        res = self.client.embeddings.create(**kwargs)
        return np.array([e.embedding for e in res.data], dtype=np.float32)

class CohereEmbedder:
    def __init__(self, model="embed-multilingual-v3.0", input_type="search_document",
                 embedding_types=("float",), truncate="END"):
        self.co = cohere.ClientV2(os.environ["COHERE_API_KEY"])
        self.model = model
        self.input_type = input_type
        self.embedding_types = list(embedding_types)
        self.truncate = truncate

    def embed(self, texts):
        # Cohere는 float/int8/binary 등을 선택 가능 ([docs.cohere.com](https://docs.cohere.com/v2/docs/semantic-search-with-cohere?utm_source=openai))
        res = self.co.embed(
            model=self.model,
            input_type=self.input_type,
            embedding_types=self.embedding_types,
            texts=texts,
            truncate=self.truncate,
        )
        # float를 기본 경로로 사용
        return np.array(res.embeddings.float, dtype=np.float32)

class BGEM3Embedder:
    def __init__(self, model_name="BAAI/bge-m3", device="cpu"):
        # bge-m3는 1024 dim, 8k 컨텍스트로 알려진 멀티링구얼 모델 ([huggingface.co](https://huggingface.co/BAAI/bge-m3?utm_source=openai))
        self.model = SentenceTransformer(model_name, device=device)

    def embed(self, texts):
        vecs = self.model.encode(texts, batch_size=32, normalize_embeddings=False)
        return np.array(vecs, dtype=np.float32)
```

### 3) 실제 평가 실행: Recall@20, MRR@20로 “도메인 적합도” 판단
```python
# file: run_eval.py
import numpy as np
from tqdm import tqdm
from eval_embeddings import load_corpus, load_qas, brute_force_search, recall_at_k, mrr_at_k
from embedders import OpenAIEmbedder, CohereEmbedder, BGEM3Embedder

def eval_embedder(name, embedder, docs, qas, top_k=20):
    doc_ids = [d.doc_id for d in docs]
    doc_texts = [d.text for d in docs]

    # 1) 문서 임베딩
    doc_vecs = []
    for i in tqdm(range(0, len(doc_texts), 64), desc=f"[{name}] embed docs"):
        doc_vecs.append(embedder.embed(doc_texts[i:i+64]))
    doc_vecs = np.vstack(doc_vecs)

    # 2) 질의 임베딩
    q_vecs = []
    queries = [q.query for q in qas]
    for i in tqdm(range(0, len(queries), 64), desc=f"[{name}] embed queries"):
        q_vecs.append(embedder.embed(queries[i:i+64]))
    q_vecs = np.vstack(q_vecs)

    # 3) 검색 & 지표
    ranked = brute_force_search(q_vecs, doc_vecs, doc_ids, top_k=top_k)

    r20, mrr20 = 0.0, 0.0
    for q, cand in zip(qas, ranked):
        rel = set(q.relevant_doc_ids)
        r20 += recall_at_k(cand, rel, 20)
        mrr20 += mrr_at_k(cand, rel, 20)

    n = len(qas)
    return {"name": name, "recall@20": r20/n, "mrr@20": mrr20/n}

if __name__ == "__main__":
    docs = load_corpus("corpus.jsonl")
    qas = load_qas("qas.jsonl")

    results = []
    results.append(eval_embedder(
        "openai_3_large_1024d",
        OpenAIEmbedder(model="text-embedding-3-large", dimensions=1024),
        docs, qas
    ))
    results.append(eval_embedder(
        "cohere_multilingual_v3_float",
        CohereEmbedder(model="embed-multilingual-v3.0", input_type="search_document", embedding_types=("float",)),
        docs, qas
    ))
    results.append(eval_embedder(
        "bge_m3_local",
        BGEM3Embedder(model_name="BAAI/bge-m3", device="cpu"),
        docs, qas
    ))

    for r in results:
        print(r)
```

**예상 출력(형태)**
```text
{'name': 'openai_3_large_1024d', 'recall@20': 0.91, 'mrr@20': 0.62}
{'name': 'cohere_multilingual_v3_float', 'recall@20': 0.89, 'mrr@20': 0.59}
{'name': 'bge_m3_local', 'recall@20': 0.93, 'mrr@20': 0.65}
```
숫자는 코퍼스/언어/질의 분포에 따라 완전히 달라집니다. 중요한 건 **“우리 도메인 QA셋”으로 측정**하는 것입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “도메인별 선택”은 언어/질의 형태로 먼저 갈린다
- **영어 중심 + 품질 최우선 + 운영 단순성**: OpenAI `text-embedding-3-large`가 기본 선택이 되기 쉽고, `dimensions`로 스토리지/DB 제약을 맞추며 단계적으로 튜닝할 수 있습니다. ([openai.com](https://openai.com/blog/new-embedding-models-and-api-updates?hss_channel=lis-l2XDk_NCpt&utm_source=openai))
- **다국어/코드스위칭이 실제 트래픽의 핵심**: Cohere의 multilingual 라인이 실무에서 빠르게 성능 격차를 메웠다는 보고가 있고, 문서/쿼리 타입을 분리해 운영하기가 편합니다. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed?utm_source=openai))
- **ID/상품명/약어가 중요한 검색 + 하이브리드가 필수**: BGE-M3처럼 dense+sparse(+multi-vector) 성격을 활용하면 “embedding이 놓치는 lexical 단서”를 구조적으로 보완할 수 있습니다. ([llmreference.com](https://www.llmreference.com/model/bge-m3?utm_source=openai))

### Best Practice 2) 저장비용은 “차원”만이 아니라 “dtype/압축”이 좌우한다
- Cohere는 int8/binary embedding을 모델/플랫폼 차원에서 지원해, 대규모 코퍼스에서 벡터 저장 비용과 캐시 비용을 크게 줄이는 방향이 명확합니다. ([cohere.com](https://cohere.com/blog/int8-binary-embeddings?utm_source=openai))
- OpenAI는 차원 축소(`dimensions`)가 핵심 레버입니다(예: 3072 → 1024/256). ([openai.com](https://openai.com/blog/new-embedding-models-and-api-updates?hss_channel=lis-l2XDk_NCpt&utm_source=openai))  
- **팁**: “압축을 하면 품질이 얼마나 떨어지나?”는 일반론이 아니라 **당신의 쿼리 분포**에 종속됩니다. (고유명사/짧은 쿼리가 많을수록 손실이 눈에 띄는 경우가 흔함)

### 함정 1) 모델 스왑은 ‘한 줄 변경’이지만, 재임베딩은 절대 한 줄이 아니다
- 임베딩 모델을 바꾸면 기존 벡터와 **공간이 호환되지 않아** 재임베딩이 필요합니다. 이때
  - 새 인덱스를 병렬 구축하고,
  - dual-read(구 인덱스 + 신 인덱스)로 점진 전환하며,
  - 온라인 지표(검색 클릭/다운스트림 해결률)로 검증
  같은 운영 설계가 필요합니다. ([reddit.com](https://www.reddit.com/r/n8n/comments/1stcjlu/error_supabase_pgvector/?utm_source=openai))

### 함정 2) “embedding만 바꿔서 좋아졌다”는 착각
- chunking, top_k, 필터링, 언어 감지, 쿼리 정규화(특수문자/코드/스페이스) 같은 **무료 개선 포인트**를 고정하지 않으면, 모델 비교 실험이 노이즈 게임이 됩니다.
- 특히 다국어는 “질의 언어 감지 실패”가 retrieval 실패로 바로 이어질 수 있습니다(세션 단위 고정/발화 단위 감지 등). ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1sztoyx/most_embedding_models_silently_fail_on_nonenglish/?utm_source=openai))

---

## 🚀 마무리
핵심은 “2026년 5월 기준 어떤 모델이 제일 좋나?”가 아니라, **내 도메인에서 어떤 실패 모드를 가장 싸게/안전하게 막을 수 있나**입니다.

- **OpenAI**: `text-embedding-3-large/small` + `dimensions`로 품질↔비용을 미세 조정하기 좋고, 운영 단순성이 강점. ([platform.openai.com](https://platform.openai.com/docs/guides/embeddings/embedding-models%20.class?utm_source=openai))  
- **Cohere**: multilingual + 압축(int8/binary) 같은 **대규모 운영 친화성**이 매력. ([docs.cohere.com](https://docs.cohere.com/docs/embeddings?utm_source=openai))  
- **BGE-M3**: 온프레/오픈웨이트 선호, 그리고 **dense+sparse(+multi-vector) 하이브리드 요구**가 강한 도메인에서 설계 상 유리. ([huggingface.co](https://huggingface.co/BAAI/bge-m3?utm_source=openai))  

**도입 판단 기준(실무 체크리스트)**
1) 우리 트래픽에서 상위 50~200개의 “실패 질의”를 모아 QA셋을 만든다  
2) chunking/top_k/필터를 고정한 뒤 embedding만 바꿔 Recall@20, MRR@20로 비교한다  
3) 비용은 “토큰 + 저장(차원×dtype) + 재임베딩 마이그레이션”까지 포함해 계산한다  
4) 다국어/ID 중심이면 하이브리드를 기본 전제로 설계한다

다음 단계로는, 위 평가 코드에 **(a) BM25 결합**, **(b) Cohere int8/binary 경로**, **(c) reranker 추가**까지 넣어 “embedding 선택이 아니라 retrieval 스택 선택”으로 확장하면, 모델 교체 빈도를 크게 줄이면서 품질을 더 안정적으로 끌어올릴 수 있습니다.