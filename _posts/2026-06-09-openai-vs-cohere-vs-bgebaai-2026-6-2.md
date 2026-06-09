---
title: "OpenAI vs Cohere vs BGE(BAAI) 임베딩, 2026년 6월 “진짜” 선택 가이드: 성능·비용·도메인 적합성까지"
date: 2026-06-09 04:13:48 +0900
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
RAG/검색/추천 시스템에서 **임베딩 모델 선택**은 “정확도”만의 문제가 아닙니다. 한 번 모델을 고르면 **(1) 전체 코퍼스 re-embedding 비용**, **(2) 벡터 차원에 따른 DB 스토리지/쿼리 비용**, **(3) 언어/도메인 적합성**, **(4) 운영 제약(지연, 배치 처리, 온프렘)**까지 연쇄적으로 고정됩니다. 특히 OpenAI는 `text-embedding-3-small/large` 중심으로 양분되어 있고, Cohere는 `embed-v4.0`에서 **멀티모달(텍스트+이미지/PDF)** 및 **긴 컨텍스트(128k)**를 전면에 내세우며, BGE 계열은 **오픈소스/자가호스팅**을 통한 비용 최적화가 강점입니다. ([developers.openai.com](https://developers.openai.com/api/docs/models/text-embedding-3-large))

언제 쓰면 좋나:
- **검색 정확도가 곧 매출/리스크로 직결**(법률/의료/금융, 고객지원 자동화의 오답 비용이 큼)
- **다국어 코퍼스**(한국어 포함) + 질의/문서가 섞여 들어오는 환경
- **대규모 코퍼스**(수천만 문서)로, 비용/운영이 성패를 가르는 경우

언제 쓰면 안 되나(또는 재검토):
- “그냥 RAG니까 최고 점수 모델”처럼 **벤치마크(MTEB)만 보고 고르는 경우**(현업 데이터와 분포가 다르면 역전이 흔함)
- **인덱스 재생성(re-embedding)**을 감당할 수 없는 서비스(모델 업그레이드 주기가 잦다면 더욱) ([embeddingcost.com](https://embeddingcost.com/openai))
- 개인정보/규제 때문에 외부 API 사용이 어려운데도, 아무 대비 없이 SaaS 임베딩부터 붙이는 경우(온프렘/BGE 검토 필요)

---

## 🔧 핵심 개념
### 1) 임베딩이 “검색 품질”을 결정하는 실제 메커니즘
임베딩은 텍스트를 고정 길이 벡터로 바꾸고, 검색 시에는 보통 다음 흐름으로 동작합니다.

1. **Chunking**: 문서를 의미 단위로 쪼갬(길이/구조가 품질에 직접 영향)
2. **Embedding**: 각 chunk → 벡터
3. **Indexing(ANN)**: HNSW/IVF 등 근사 최근접 탐색 인덱스 구성
4. **Query embedding**: 질의도 벡터로 변환
5. **Vector search**: cosine/dot 등으로 top-k 후보를 찾음
6. **Rerank/LLM**: 후보를 재정렬하거나 답변 생성

여기서 임베딩 모델은 “의미 공간”을 정의합니다. **같은 ANN/DB라도 임베딩이 바뀌면 이웃 관계 자체가 바뀌어** 검색 결과가 확 달라집니다. 결국 모델 선택은 *벡터 공간의 성질(언어, 도메인, 길이, 노이즈耐성)*을 고르는 일입니다.

### 2) 차원(dimension)과 비용/성능의 연결
- OpenAI `text-embedding-3-large`는 **3,072 dims**, `3-small`은 **1,536 dims**이며 가격도 큰 차이가 납니다(대략 6.5배). ([developers.openai.com](https://developers.openai.com/api/docs/models/text-embedding-3-large))  
- Cohere `embed-v4.0`는 **256/512/1024/1536** 중 선택 가능(기본 1536)이고, **128k context**를 명시합니다. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed))

차원이 커지면:
- 장점: 표현력이 늘어 “구분해야 할 의미”를 더 잘 분리할 수 있음(특히 희귀 도메인/다국어)
- 단점: **벡터 DB 저장 비용(대략 dims에 비례)**, 네트워크 전송, 검색 시간(인덱스 구조에 따라 체감)

그래서 실무에서는 “최대 성능”보다 **필요 충분한 차원**을 찾는 게 핵심입니다.

### 3) MTEB는 참고 지표지만, ‘도메인 평가’가 본게임
MTEB는 다양한 태스크/데이터셋을 묶은 대표 벤치마크지만, 결국 “내 문서/내 질의”와 분포가 다르면 결과가 역전될 수 있습니다. 그래서 모델 후보를 2~3개로 좁힌 뒤에는:
- **우리 서비스 질의 로그 + 실제 문서**로
- top-k recall, nDCG, answer accuracy(LLM 포함)까지
- A/B(또는 오프라인 replay)로 검증하는 게 안전합니다. ([arxiv.org](https://arxiv.org/abs/2210.07316?utm_source=openai))

### 4) 2026년 6월 기준, 후보군의 “성격” 요약
- **OpenAI**: `text-embedding-3-small`(가성비) vs `text-embedding-3-large`(고정밀)로 단순. 가격은 공개 문서/비교표에서 널리 확인 가능. ([developers.openai.com](https://developers.openai.com/api/docs/models/text-embedding-3-large))
- **Cohere**: `embed-v4.0`가 **긴 컨텍스트(128k)** + **텍스트/이미지 혼합(PDF 등)** + **가변 차원**을 전면에 둠. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed))
- **BGE(BAAI)**: BGE-M3/large-en-v1.5 등 오픈소스 계열이 널리 사용되며, 모델 허브/리더보드에서 MTEB 점수들이 공유됨(온프렘/비용 최적화에 강점). ([mixpeek.com](https://mixpeek.com/model/BAAI/bge-large-en-v1.5?utm_source=openai))

---

## 💻 실전 코드
아래는 **“기술 문서 검색(한국어+영어 혼합) + 벡터DB(pgvector) + 모델 교체 가능한 평가 루프”** 예제입니다.  
목표는 *toy*가 아니라, 실제 서비스에서 바로 쓰는 **(1) 오프라인 인덱싱**, **(2) 온라인 질의**, **(3) 모델별 품질/비용 비교**까지 한 번에 돌아가게 만드는 것입니다.

### 0) 셋업 (PostgreSQL + pgvector)
```bash
# 로컬 개발용 (실서비스는 RDS/Cloud SQL 등으로 대체)
docker run --name pgvector -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d pgvector/pgvector:pg16

# 테이블/확장
docker exec -it pgvector psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker exec -it pgvector psql -U postgres -c "
CREATE TABLE IF NOT EXISTS docs (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  chunk TEXT NOT NULL,
  lang TEXT NOT NULL,
  embedding vector(1536) -- 기본은 1536으로 시작(모델에 따라 바꿀 수 있음)
);
"
```

### 1) 인덱싱 파이프라인 (모델별로 교체 가능)
- OpenAI `text-embedding-3-small`은 **$0.02 / 1M tokens**, `3-large`는 **$0.13 / 1M tokens**로 문서화된 비교 자료가 많고, 대량 인덱싱은 Batch로 비용 절감(최대 50%)이 자주 언급됩니다. ([developers.openai.com](https://developers.openai.com/api/docs/models/text-embedding-3-large))  
- Cohere `embed-v4.0`는 차원 선택(256~1536)과 긴 컨텍스트(128k)가 명시되어 있어 “PDF/긴 문서 파이프라인”에서 설계가 달라집니다. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed))

```python
# index_docs.py
import os
import re
import time
from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

import psycopg
from psycopg.rows import dict_row

# OpenAI (공식 SDK)
from openai import OpenAI

# Cohere (공식 SDK)
import cohere


Provider = Literal["openai", "cohere"]

@dataclass
class EmbedConfig:
    provider: Provider
    model: str
    dims: int  # pgvector 컬럼 차원과 일치해야 함
    batch_size: int = 64

def detect_lang(text: str) -> str:
    # 간단 휴리스틱(실무에선 fastText/CLD3 권장)
    return "ko" if re.search(r"[가-힣]", text) else "en"

def chunk_markdown(md: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    # “현실적인” 청킹: 섹션/문단 기반 + 길이 제한 + 오버랩
    paras = [p.strip() for p in md.split("\n\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= max_chars:
            cur = (cur + "\n\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            # 다음 청크는 overlap만큼 꼬리 재사용
            tail = cur[-overlap:] if cur else ""
            cur = (tail + "\n\n" + p).strip()
    if cur:
        chunks.append(cur)
    return chunks

def embed_texts_openai(texts: List[str], model: str, dims: Optional[int] = None) -> List[List[float]]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    kwargs = {"model": model, "input": texts}
    if dims is not None:
        # OpenAI 일부 임베딩 모델은 dimensions 파라미터를 지원(저장/성능 트레이드오프)
        kwargs["dimensions"] = dims
    resp = client.embeddings.create(**kwargs)
    return [d.embedding for d in resp.data]

def embed_texts_cohere(texts: List[str], model: str, dims: int) -> List[List[float]]:
    ch = cohere.Client(os.environ["COHERE_API_KEY"])
    # Cohere는 문서에서 256/512/1024/1536 차원 선택을 명시
    resp = ch.embed(texts=texts, model=model, embedding_types=["float"], input_type="search_document", truncate="END", dimensions=dims)
    return resp.embeddings.float  # List[List[float]]

def index_sources(conn_str: str, sources: List[Tuple[str, str]], cfg: EmbedConfig):
    """
    sources: List[(source_name, markdown_text)]
    """
    all_rows = []
    for source, md in sources:
        chunks = chunk_markdown(md)
        for c in chunks:
            all_rows.append((source, c, detect_lang(c)))

    # 임베딩 생성
    embeddings = []
    for i in range(0, len(all_rows), cfg.batch_size):
        batch = all_rows[i:i+cfg.batch_size]
        texts = [r[1] for r in batch]
        if cfg.provider == "openai":
            vecs = embed_texts_openai(texts, model=cfg.model, dims=cfg.dims)
        else:
            vecs = embed_texts_cohere(texts, model=cfg.model, dims=cfg.dims)
        embeddings.extend(vecs)
        time.sleep(0.05)

    # DB 저장
    with psycopg.connect(conn_str) as con:
        with con.cursor() as cur:
            cur.execute("BEGIN;")
            for (source, chunk, lang), emb in zip(all_rows, embeddings):
                cur.execute(
                    "INSERT INTO docs(source, chunk, lang, embedding) VALUES (%s, %s, %s, %s)",
                    (source, chunk, lang, emb),
                )
            cur.execute("COMMIT;")

if __name__ == "__main__":
    # 예: OpenAI 가성비 기본안
    cfg = EmbedConfig(provider="openai", model="text-embedding-3-small", dims=1536)

    # 예: Cohere 멀티모달/긴문서 파이프라인을 의식한다면(차원 1024로 저장비 절감)
    # cfg = EmbedConfig(provider="cohere", model="embed-v4.0", dims=1024)

    conn_str = "postgresql://postgres:postgres@localhost:5432/postgres"
    sources = [
        ("internal-wiki", open("data/internal_wiki.md", "r", encoding="utf-8").read()),
        ("api-guide", open("data/api_guide.md", "r", encoding="utf-8").read()),
        ("runbooks", open("data/runbooks.md", "r", encoding="utf-8").read()),
    ]
    index_sources(conn_str, sources, cfg)
    print(f"Indexed {len(sources)} sources with {cfg.provider}:{cfg.model} dims={cfg.dims}")
```

예상 출력(예시):
- `Indexed 3 sources with openai:text-embedding-3-small dims=1536`
- 이후 `docs` 테이블에 chunk 단위로 적재

### 2) 온라인 검색 + 간단 평가(도메인별 선택의 핵심)
“모델 뭐 쓰지?”의 답을 빨리 얻으려면, **질의 세트(20~100개)**를 만들고 top-k hit rate를 비교하세요.

```python
# search_eval.py
import os
from typing import List, Tuple, Optional, Literal
import psycopg
from openai import OpenAI
import cohere

Provider = Literal["openai", "cohere"]

def embed_query(provider: Provider, model: str, q: str, dims: int) -> List[float]:
    if provider == "openai":
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.embeddings.create(model=model, input=[q], dimensions=dims)
        return resp.data[0].embedding
    else:
        ch = cohere.Client(os.environ["COHERE_API_KEY"])
        resp = ch.embed(texts=[q], model=model, embedding_types=["float"], input_type="search_query", truncate="END", dimensions=dims)
        return resp.embeddings.float[0]

def search(conn_str: str, qvec: List[float], top_k: int = 8, lang: Optional[str] = None) -> List[Tuple[int, str, str]]:
    where = "WHERE lang = %s" if lang else ""
    params = [lang] if lang else []
    sql = f"""
      SELECT id, source, chunk
      FROM docs
      {where}
      ORDER BY embedding <=> %s
      LIMIT {top_k};
    """
    with psycopg.connect(conn_str) as con:
        with con.cursor() as cur:
            cur.execute(sql, params + [qvec])
            return cur.fetchall()

def hit_rate_at_k(results, must_contain: str) -> float:
    # 현실적이면서도 빠른 근사 평가: “정답 문서/키워드가 top-k에 들어오는가”
    return 1.0 if any(must_contain in r[2] for r in results) else 0.0

if __name__ == "__main__":
    conn_str = "postgresql://postgres:postgres@localhost:5432/postgres"

    # 같은 질의로 모델 A/B를 돌려본다
    candidates = [
        ("openai", "text-embedding-3-small", 1536),
        ("openai", "text-embedding-3-large", 3072),
        ("cohere", "embed-v4.0", 1024),
    ]

    eval_set = [
        ("배치 인덱싱에서 비용 줄이는 방법", "Batch"),  # 문서에 "Batch" 언급이 있어야 hit
        ("How do we rotate API keys safely in production?", "rotation"),
        ("장애 대응 runbook에서 oncall 핸드오프 절차", "handoff"),
    ]

    for provider, model, dims in candidates:
        score = 0.0
        for q, gold_hint in eval_set:
            qvec = embed_query(provider, model, q, dims)
            results = search(conn_str, qvec, top_k=8)
            score += hit_rate_at_k(results, gold_hint)
        print(provider, model, "avg_hit@8 =", score / len(eval_set))
```

이 스크립트의 포인트:
- **MTEB 점수(전역 평균)**보다, 내 도메인의 “필요한 구분”이 되는지를 빠르게 확인합니다.
- 같은 top-k라도 모델마다 “비슷한 문서”의 정의가 달라져 hit@k가 바뀝니다.
- **다국어**라면 `lang` 필터를 켠/끈 두 경우를 모두 보세요(혼합 코퍼스에서 교차언어 매칭이 오히려 독이 되는 경우가 있습니다).

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 효과 나는 것 3가지)
1) **모델 선택 전에 ‘재임베딩 비용’을 먼저 계산**
- OpenAI는 모델 변경 시 코퍼스를 다시 임베딩해야 하고(일회성), 큰 코퍼스일수록 이 비용이 의사결정을 지배합니다. ([embeddingcost.com](https://embeddingcost.com/openai))  
- “일단 3-large로 가자”는 결정은, **미래의 인덱스 마이그레이션 비용**까지 포함해 정당화돼야 합니다.

2) **차원(dims)은 “DB 비용”과 “검색 품질”의 레버**
- Cohere `embed-v4.0`처럼 차원을 선택할 수 있으면(256~1536), 처음부터 1536 고정이 아니라 **1024 또는 512로 내려서 POC → 필요 시 상향** 전략이 먹힙니다. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed))  
- OpenAI는 `3-large`가 3072로 크기 부담이 있으니, “정확도”가 확실히 필요한 도메인인지 먼저 검증하세요. ([developers.openai.com](https://developers.openai.com/api/docs/models/text-embedding-3-large))

3) **RAG 품질 문제의 60%는 임베딩이 아니라 ‘청킹/메타데이터/평가’에서 터짐**
- 임베딩 모델 바꾸기 전에:
  - 섹션/표/코드블록 보존 청킹
  - 문서 버전/권한/제품 라인 같은 메타데이터 필터
  - 질의 로그 기반 eval set(최소 50개)
  를 먼저 갖추면, 모델 교체 효과도 명확해집니다.

### 흔한 함정/안티패턴
- **MTEB 1~2점 차이에 과몰입**: 실데이터에서는 chunk 길이/용어 사전/혼합 언어 비율이 더 큰 변수입니다. MTEB 자체는 “폭넓은 비교용”이지 “내 서비스 결론”이 아닙니다. ([arxiv.org](https://arxiv.org/abs/2210.07316?utm_source=openai))
- **코퍼스에 중복/보일러플레이트가 많은데 그대로 임베딩**: 유사한 템플릿 문장이 벡터 공간을 오염시켜, 검색이 “문서 레이아웃”을 찾게 됩니다.
- **OpenAI 3-large를 3072로 저장해놓고 나중에 비용이 터짐**: pgvector/HNSW에서 RAM/디스크가 실제로 병목이 됩니다(특히 인덱스 빌드/리빌드 시간).

### 비용/성능/안정성 트레이드오프(도메인별 추천)
- **SaaS, 빠른 구축, 일반적인 RAG(영/한 혼합)**  
  → OpenAI `text-embedding-3-small`로 시작이 합리적(저비용, 운영 단순). 가격/비교는 공개 자료에서 명확. ([developers.openai.com](https://developers.openai.com/api/docs/models/text-embedding-3-large))
- **정확도 민감(규제/리스크), 다국어가 난이도 높음**  
  → OpenAI `3-large` 또는 Cohere `embed-v4.0`를 후보에 올리고, 반드시 도메인 eval로 결론. OpenAI는 비용 프리미엄이 크니(6.5x) 품질 이득이 “측정 가능”해야 함. ([embeddingcost.com](https://embeddingcost.com/openai))
- **온프렘/자가호스팅/비용 최적화가 최우선**  
  → BGE 계열(BGE-M3, bge-large-en-v1.5 등)로 자체 서빙 + 벡터DB 최적화가 강력한 옵션(다만 운영/튜닝 비용을 팀이 감당해야 함). ([arxiv.org](https://arxiv.org/abs/2402.03216?utm_source=openai))
- **PDF/이미지+텍스트 같이 다뤄야 함(문서 이해 파이프라인)**  
  → Cohere `embed-v4.0`는 문서에서 혼합 입력/긴 컨텍스트를 명시하므로, 이 니즈가 확실하면 설계가 깔끔해집니다. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed))

---

## 🚀 마무리
2026년 6월 기준으로 임베딩 모델 선택을 “한 줄”로 정리하면:

- **기본값**: OpenAI `text-embedding-3-small`(가성비/운영 단순) ([developers.openai.com](https://developers.openai.com/api/docs/models/text-embedding-3-large))  
- **정확도/다국어/하이리스크**: `text-embedding-3-large` 또는 Cohere `embed-v4.0`를 **도메인 eval로 채택** ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed))  
- **온프렘/비용 최적화**: BGE 계열을 중심으로 “서빙+인덱스+평가 루프”까지 소유 ([arxiv.org](https://arxiv.org/abs/2402.03216?utm_source=openai))

도입 판단 기준(실무 체크리스트):
1) 코퍼스 토큰량 기준으로 **re-embedding 1회 비용**을 계산했는가? ([embeddingcost.com](https://embeddingcost.com/openai))  
2) 벡터 차원(dims)이 **DB 비용**에 미치는 영향을 추정했는가?  
3) 우리 질의 로그로 만든 eval set에서 **hit@k / nDCG / 답변 정확도**가 실제로 개선되는가? ([arxiv.org](https://arxiv.org/abs/2210.07316?utm_source=openai))  
4) 다국어/형태소(한국어)에서 “용어 매칭”이 아니라 “의미 매칭”이 되는가(도메인 평가로 검증)?

다음 학습 추천:
- MTEB의 구성/한계를 이해하고, “내 도메인 벤치마크”를 만드는 방법부터 정리하세요. ([arxiv.org](https://arxiv.org/abs/2210.07316?utm_source=openai))  
- 이후에는 **Embedding + Rerank**(특히 Cohere는 rerank 라인업도 강하게 밀고 있음) 조합으로, “임베딩 하나로 해결” 접근에서 벗어나는 게 다음 단계입니다. ([pecollective.com](https://pecollective.com/tools/cohere-pricing/?utm_source=openai))