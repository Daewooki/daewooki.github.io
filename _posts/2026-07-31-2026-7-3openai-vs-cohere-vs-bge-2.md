---
title: "2026년 7월, 임베딩 모델 3파전(OpenAI vs Cohere vs BGE): “우리 서비스”에 맞는 선택 기준"
date: 2026-07-31 03:38:06 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-07]
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
임베딩(embedding)은 결국 “문장을 벡터로 바꿔서, **의미 기반 검색/매칭**을 빠르게 하는” 기술입니다. 문제는 실무에서 임베딩 품질이 좋아도 **(1) 언어/도메인/문서 형태**가 바뀌면 성능이 급락하거나, **(2) 벡터 차원·인덱스·비용** 때문에 전체 시스템 비용이 폭발하거나, **(3) 재색인(reindex) 비용**이 발목을 잡는다는 점입니다.

**언제 쓰면 좋나**
- RAG에서 “관련 chunk를 잘 찾는 것”이 답변 품질의 상한을 결정할 때
- 유사 문서 추천, 중복 이슈/티켓 병합, FAQ 자동 라우팅, 로그/사고 리포트 클러스터링
- 다국어 쿼리/문서가 섞여 있고 번역 파이프라인을 넣고 싶지 않을 때(특히 Cohere/BGE 쪽 강점)

**언제 쓰면 안 되나(혹은 단독으로는 부족)**
- 정확히 “키워드/필터”가 중요한 검색(법령 조항 번호, SKU, 에러 코드): BM25/keyword + embedding 하이브리드가 대개 이김
- 긴 문서(PDF/리포트)를 “그대로” 넣고 한 방에 해결하려는 경우: chunking/metadata/rerank가 더 큰 변수

이번 글은 2026년 7월 기준으로 **OpenAI / Cohere / BAAI(BGE)** 축을 놓고, “내 도메인에서는 뭘 고를지” 판단할 수 있도록 **구조적 차이 + 실전 적용 코드 + 함정**까지 정리합니다. (최신 스펙/특징은 각 공식 문서·모델카드 기반) ([developers.openai.com](https://developers.openai.com/api/docs/models/text-embedding-3-large?utm_source=openai))

---

## 🔧 핵심 개념
### 1) “좋은 embedding”의 정의는 1개가 아니다
실무에서 자주 섞이는 목표가 3가지입니다.

1. **Semantic Search (query→doc)**: 사용자 질문과 문서 chunk를 같은 공간에 놓고 가까운 것을 찾기  
2. **Clustering/Classification**: 유사 이슈 묶기, 티켓 라우팅, 주제 군집  
3. **Cross-lingual Retrieval**: 한국어 질문으로 영어/일본어 문서를 찾기

여기서 중요한 포인트:
- 모델마다 **최적화된 input_type(쿼리/문서/분류)**가 다르거나(대표적으로 Cohere는 `input_type`로 용도를 명시) ([docs.cohere.com](https://docs.cohere.com/v1/docs/embeddings?utm_source=openai))
- **차원 축소(shortening)**를 전제로 학습해 “비용-성능” 커브를 원하는 곳에서 자를 수 있거나(OpenAI는 `dimensions`로 3072→1024/256 등 축소 가능) ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))
- 아예 “dense만”이 아니라 **sparse + multi-vector + long context**까지 한 모델로 커버하는 쪽(BGE-M3)도 있음 ([arxiv.org](https://arxiv.org/abs/2402.03216?utm_source=openai))

### 2) OpenAI / Cohere / BGE의 구조적 차이(실무 관점)
#### OpenAI: “Matryoshka(shortening) + 생태계/운영 난이도 낮음”
- `text-embedding-3-large`는 최대 **3072 dims**이며 `dimensions` 파라미터로 줄여 저장비/속도를 조절할 수 있습니다. ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))  
- OpenAI embedding 출력은 기본적으로 **L2-normalized**라는 점(코사인/내적으로 운영 설계가 단순해짐). ([help.openai.com](https://help.openai.com/en/articles/6824809-embeddings-faq-2?utm_source=openai))  
- 장점: API 운영 편의, 모델 품질/안정성, “차원 줄여도 꽤 쓸만”한 선택지  
- 리스크: 멀티모달(이미지/PDF) 임베딩까지 한 방에 처리하려면 별도 설계가 필요(embedding 자체는 텍스트 중심)

#### Cohere: “업무 문서/다국어/멀티모달 입력을 retrieval에 맞게”
- `embed-v4.0`는 **128k context**를 표방하고, **텍스트+이미지/혼합(예: PDF)** 입력을 단일 임베딩으로 만들 수 있는 방향을 강조합니다. 또한 출력 차원을 `[256, 512, 1024, 1536]`에서 선택(“Matryoshka” 계열 아이디어를 문서에서 명시)합니다. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed?utm_source=openai))  
- 그리고 실무적으로 매우 중요한 포인트: `input_type="search_query"` vs `"search_document"`로 **쿼리/문서 공간을 구분 최적화**합니다. 이걸 안 지키면 “모델이 별로”가 아니라 “내가 모델을 망가뜨린” 결과가 나옵니다. ([docs.cohere.com](https://docs.cohere.com/v1/docs/embeddings?utm_source=openai))  
- 장점: 다국어·문서형 데이터(특히 PDF/이미지 섞인 기업 문서)에서 파이프라인 단순화 여지  
- 리스크: 컨텍스트 길이/입력 제약, 벤더 종속(온프레미스/프라이빗 배포는 옵션이 있으나 조직마다 조건 다름)

#### BGE(특히 BGE-M3): “오픈웨이트 + long context + hybrid retrieval 성향”
- `BAAI/bge-m3`는 **1024 dims**, **8192 tokens** 입력을 지원하고, dense/sparse/colbert(멀티벡터) 기능을 한 모델 패밀리로 묶어 “현실 IR에 필요한 모드”를 넓게 커버하는 컨셉입니다. ([arxiv.org](https://arxiv.org/abs/2402.03216?utm_source=openai))  
- 장점: 비용(자체 호스팅), 데이터 거버넌스(민감문서), 커스터마이징(도메인 파인튜닝/지시문(instruction) 최적화)  
- 리스크: 운영 난이도(GPU/배포/성능 튜닝), 그리고 실제 서비스 성능은 “모델”보다 **chunking + hybrid + rerank**가 더 크게 좌우(오픈쪽은 특히 당신이 다 책임져야 함)

---

## 💻 실전 코드
아래 예제는 “사내 위키 + Jira 티켓 + RFC 문서”를 모아 RAG용 인덱스를 만들고, **OpenAI / Cohere / BGE를 같은 스키마로 비교**할 수 있게 만든 형태입니다.  
핵심은 **(1) 동일 chunk/전처리**, **(2) 동일 벡터DB/검색 로직**, **(3) 모델별 ‘권장 파라미터’ 반영**입니다.

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install -U openai cohere sentence-transformers numpy pgvector psycopg[binary]
```

Postgres(+pgvector)가 이미 있다고 가정합니다.

```bash
# 예: 로컬 도커 (이미 있다면 스킵)
docker run --name pgvec -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d pgvector/pgvector:pg16
```

### 1) 공통 스키마 + chunking(“toy”가 아닌 운영형 최소안)
- 문서 소스/권한/갱신시각을 같이 넣어야 “검색은 되는데 권한 위반/구버전 인용” 사고가 줄어듭니다.
- chunk는 “문단 단위 + 최대 토큰 제한”이 기본. 여기선 간단히 길이 기반으로 나눕니다(실전에서는 문서 구조 기반이 더 좋음).

```python
# index_rag.py
import os
import re
import json
import time
import numpy as np
from dataclasses import dataclass
from typing import List, Literal, Optional, Dict, Any, Tuple

import psycopg
from pgvector.psycopg import register_vector

# --------- domain doc ----------
@dataclass
class DocChunk:
    doc_id: str
    source: Literal["wiki", "jira", "rfc"]
    path: str
    updated_at: int  # epoch sec
    acl: List[str]   # e.g. ["team:search", "user:alice"]
    text: str

def simple_chunk(text: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return [text]
    out = []
    i = 0
    while i < len(text):
        out.append(text[i:i+max_chars])
        i += max_chars - overlap
    return out

# --------- embeddings backends ----------
def embed_openai(texts: List[str], *, model="text-embedding-3-large", dimensions: int = 1024) -> np.ndarray:
    # NOTE: requires OPENAI_API_KEY
    from openai import OpenAI
    client = OpenAI()
    resp = client.embeddings.create(model=model, input=texts, dimensions=dimensions)
    vectors = np.array([d.embedding for d in resp.data], dtype=np.float32)
    return vectors

def embed_cohere(texts: List[str], *, model="embed-v4.0", input_type="search_document", output_dimension=1024) -> np.ndarray:
    # NOTE: requires COHERE_API_KEY
    import cohere
    co = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    resp = co.embed(
        model=model,
        texts=texts,
        input_type=input_type,            # 중요: query/doc를 분리해야 함
        output_dimension=output_dimension,
        embedding_types=["float"],
    )
    vectors = np.array(resp.embeddings.float, dtype=np.float32)
    return vectors

def embed_bge(texts: List[str], *, model_name="BAAI/bge-m3") -> np.ndarray:
    # local inference (GPU 있으면 빠름)
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(model_name)
    vecs = m.encode(texts, normalize_embeddings=True)  # 코사인 운영 단순화
    return np.array(vecs, dtype=np.float32)

# --------- storage ----------
DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunks (
  chunk_id BIGSERIAL PRIMARY KEY,
  doc_id TEXT NOT NULL,
  source TEXT NOT NULL,
  path TEXT NOT NULL,
  updated_at BIGINT NOT NULL,
  acl JSONB NOT NULL,
  text TEXT NOT NULL,
  embedding vector(1024) NOT NULL
);

CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
ON rag_chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS rag_chunks_acl_idx ON rag_chunks USING gin (acl);
"""

def upsert_chunks(conn, chunks: List[DocChunk], embeddings: np.ndarray):
    with conn.cursor() as cur:
        for c, e in zip(chunks, embeddings):
            cur.execute(
                """
                INSERT INTO rag_chunks (doc_id, source, path, updated_at, acl, text, embedding)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (c.doc_id, c.source, c.path, c.updated_at, json.dumps(c.acl), c.text, e.tolist()),
            )

def search(conn, query_vec: np.ndarray, *, top_k: int = 8, allowed_principals: List[str]) -> List[Tuple[float, Dict[str, Any]]]:
    # ACL은 예시로 “principal 중 하나라도 포함되면 허용” 형태
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 - (embedding <=> %s::vector) AS score, doc_id, source, path, updated_at, text
            FROM rag_chunks
            WHERE acl ?| %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vec.tolist(), allowed_principals, query_vec.tolist(), top_k),
        )
        rows = cur.fetchall()
    return [(float(r[0]), {"doc_id": r[1], "source": r[2], "path": r[3], "updated_at": r[4], "text": r[5]}) for r in rows]

def main():
    # ---- sample corpus (현실 시나리오: 여러 소스 혼합) ----
    raw_docs = [
        {
            "doc_id": "WIKI-123",
            "source": "wiki",
            "path": "/wiki/search/rag/chunking",
            "updated_at": int(time.time()) - 86400 * 2,
            "acl": ["team:search"],
            "text": """RAG chunking 가이드: 위키 문서는 섹션 헤더 기준으로 자르고,
                     표/코드블록은 별도 chunk로 분리한다. 너무 작은 chunk는 recall을 해치고,
                     너무 큰 chunk는 precision을 해친다...""",
        },
        {
            "doc_id": "JIRA-991",
            "source": "jira",
            "path": "/jira/JIRA-991",
            "updated_at": int(time.time()) - 86400 * 10,
            "acl": ["team:search", "team:platform"],
            "text": """사고 요약: embedding 재색인 중 dimension 불일치(768 vs 1024)로
                     검색이 전부 0점 처리. 롤백 후 차원 통일 및 마이그레이션 플랜 수립...""",
        },
        {
            "doc_id": "RFC-42",
            "source": "rfc",
            "path": "/rfc/42-vector-store",
            "updated_at": int(time.time()) - 86400 * 30,
            "acl": ["team:platform"],
            "text": """Vector store 선택: pgvector(HNSW)로 시작하고,
                     recall 부족 시 reranker 추가. 멀티테넌트 ACL은 row-level security 대신
                     prefilter + postfilter 조합을 권장...""",
        },
    ]

    chunks: List[DocChunk] = []
    for d in raw_docs:
        for part in simple_chunk(d["text"]):
            chunks.append(DocChunk(
                doc_id=d["doc_id"], source=d["source"], path=d["path"],
                updated_at=d["updated_at"], acl=d["acl"], text=part
            ))

    backend = os.environ.get("EMBED_BACKEND", "openai")  # openai|cohere|bge
    if backend == "openai":
        X = embed_openai([c.text for c in chunks], dimensions=1024)
    elif backend == "cohere":
        # 문서 인덱싱은 search_document로
        X = embed_cohere([c.text for c in chunks], input_type="search_document", output_dimension=1024)
    elif backend == "bge":
        X = embed_bge([c.text for c in chunks])
    else:
        raise ValueError("unknown EMBED_BACKEND")

    conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/postgres")
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute(DDL)
    upsert_chunks(conn, chunks, X)
    conn.commit()

    # ---- query ----
    query = "임베딩 차원 불일치 때문에 검색이 깨진 사건 원인과 재발 방지책"
    if backend == "openai":
        qv = embed_openai([query], dimensions=1024)[0]
    elif backend == "cohere":
        # 쿼리는 search_query로 (이거 안 하면 성능 흔들림)
        qv = embed_cohere([query], input_type="search_query", output_dimension=1024)[0]
    else:
        qv = embed_bge([query])[0]

    results = search(conn, qv, top_k=5, allowed_principals=["team:search"])
    for score, doc in results:
        print(f"{score:.3f}  {doc['doc_id']}  {doc['path']}\n  {doc['text'][:120]}...\n")

if __name__ == "__main__":
    main()
```

**예상 출력(형태)**
- `team:search` 권한이 있는 사용자면 JIRA 사고 문서가 상위로 뜨고, wiki chunking 가이드가 그 다음.
- `team:platform`이 없으니 RFC는 내려가거나 제외.

실행:
```bash
export OPENAI_API_KEY="..."
export COHERE_API_KEY="..."

# OpenAI
EMBED_BACKEND=openai python index_rag.py

# Cohere
EMBED_BACKEND=cohere python index_rag.py

# BGE local
EMBED_BACKEND=bge python index_rag.py
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “쿼리 임베딩”과 “문서 임베딩”을 분리 최적화하라
- Cohere는 `input_type`에 **search_query / search_document**를 명확히 제공하고, 이걸 지키는 게 성능의 1차 관문입니다. ([docs.cohere.com](https://docs.cohere.com/v1/docs/embeddings?utm_source=openai))  
- OpenAI/BGE도 개념적으로 동일합니다. 실무에서는 “쿼리는 짧고 의도가 압축”, “문서는 길고 정보가 분산”이라 **학습된 분포가 다릅니다**. API가 분리를 제공하지 않으면, 최소한 전처리(쿼리 확장, 문서 타이틀 prepend 등)로 보정하세요.

### Best Practice 2) 차원(dimension)은 “품질”이 아니라 “시스템 비용 곡선”이다
- OpenAI는 `text-embedding-3-large`를 3072에서 `dimensions`로 줄여 저장/속도/비용을 튜닝할 수 있습니다. 벡터DB 제약(예: 1024 제한) 때문에 모델 자체를 포기하지 않아도 됩니다. ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))  
- Cohere `embed-v4.0`도 출력 차원을 선택할 수 있습니다(256~1536). ([docs.cohere.com](https://docs.cohere.com/v1/docs/embeddings?utm_source=openai))  
- 함정: **차원을 바꾸는 순간 재색인**이 거의 필수입니다. “일단 384로 시작” 같은 결정을 쉽게 내리면, 나중에 정확도 때문에 1024로 올릴 때 마이그레이션 비용이 큽니다.

### Best Practice 3) 도메인별로 “모델 1개”가 아니라 “파이프라인”을 고른다
- 긴 문서/복잡한 질의에서는 embedding만으로는 한계가 있고, rerank(교차 인코더)나 hybrid(BM25+vector)가 품질을 끌어올립니다.
- BGE-M3는 긴 입력(8192 tokens)과 hybrid 성격(논문/모델카드에서 multi-functionality)을 강점으로 내세웁니다. “텍스트 길다/다국어다/온프레미스다”면 파이프라인 설계 자유도가 큽니다. ([arxiv.org](https://arxiv.org/abs/2402.03216?utm_source=openai))  

### 흔한 함정/안티패턴
- **(안티패턴) chunk를 너무 잘게 쪼개기**: “high costs” 같은 파편은 의미가 약해져 오히려 클러스터링/검색이 흔들립니다(특히 분류/클러스터링).  
- **(안티패턴) 벡터 유사도만 믿고 ACL/최신성 무시**: 권한 필터를 “검색 후 필터링”만 하면 topK가 빈약해져 품질이 흔들립니다. 최소한 prefilter(메타데이터)와 결합하세요.
- **(안티패턴) 다국어인데 영어 모델 사용**: 영어 중심 embedding은 비영어에서 “조용히 망가지는” 케이스가 많습니다. 다국어 요구가 있으면 처음부터 multilingual 모델로 가는 게 싸게 먹히는 경우가 많습니다(Cohere `embed-v4.0`, BGE-M3 등). ([docs.cohere.com](https://docs.cohere.com/v1/docs/embeddings?utm_source=openai))  

### 비용/성능/안정성 트레이드오프(요약)
- **OpenAI**: 운영 편의 + 예측 가능. 차원 축소로 비용 튜닝 가능. ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))  
- **Cohere**: 엔터프라이즈 문서/멀티모달/다국어 retrieval을 전면에 둔 설계. input_type을 지키면 강력. ([docs.cohere.com](https://docs.cohere.com/v1/docs/embeddings?utm_source=openai))  
- **BGE**: 오픈웨이트/온프레미스/커스터마이징, 긴 입력/하이브리드 성향(BGE-M3). 대신 운영은 당신의 몫. ([huggingface.co](https://huggingface.co/BAAI/bge-m3?utm_source=openai))  

---

## 🚀 마무리
핵심만 정리하면, 2026년 7월의 “OpenAI vs Cohere vs BGE” 선택은 성능 1등 맞추기보다 **내 데이터 형태와 운영 제약**을 먼저 확정하는 게임입니다.

- **영어/일반 도메인 + 빠른 출시 + 차원 튜닝으로 비용 최적화**가 중요하면: OpenAI `text-embedding-3-large`(필요 시 `dimensions`로 1024/256 등 절충) ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))  
- **다국어 + 업무 문서(PDF/이미지 혼합 포함) + retrieval 파이프라인 단순화**를 원하면: Cohere `embed-v4.0` + `input_type` 엄수 ([docs.cohere.com](https://docs.cohere.com/v1/docs/embeddings?utm_source=openai))  
- **온프레미스/거버넌스 + 긴 문서/다국어 + hybrid/커스터마이징**을 원하면: BGE-M3(1024 dims, 8192 tokens) ([huggingface.co](https://huggingface.co/BAAI/bge-m3?utm_source=openai))  

다음 학습/실험 추천(“바로 프로젝트 적용” 관점):
1) 동일 데이터로 **A/B**: (모델만 교체) + (차원 256/512/1024 스윕)  
2) embedding만 비교하지 말고 **topK, chunk 크기, hybrid(BM25+vector), rerank 유무**까지 같이 그리드로 측정  
3) 다국어/전문용어(제품명, 에러코드, 약어) 포함한 **실제 쿼리 로그**로 평가(벤치마크 점수보다 이게 진짜)

원하시면, 당신의 도메인(언어 비율, 문서 길이, 업데이트 빈도, 보안/온프레미스 요구, 벡터DB 종류, 월 쿼리량/예산)을 기준으로 **의사결정 매트릭스(가중치 포함)** 형태로 “한 장짜리 선택 가이드”도 만들어 드릴게요.