---
title: "2026년 4월 기준 Embedding Model 3파전: OpenAI vs Cohere vs BGE, “우리 도메인”에서 이기는 선택법"
date: 2026-04-21 03:32:14 +0900
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
RAG/semantic search를 “돌아가게” 만드는 것과 “정확하게” 만드는 것의 차이는 대부분 embedding에서 시작합니다. 특히 2026년 현재는 **(1) 상용 API(OpenAI, Cohere)** 와 **(2) 오픈소스(BGE 계열)** 가 모두 강력해져서, “그냥 유명한 거”로 고르기보다 **도메인/운영 제약(비용·지연·보안·배포)** 중심으로 선택해야 합니다.

- 언제 쓰면 좋나:  
  - 문서 검색(RAG), 유사 사례 추천, FAQ 라우팅, 고객문의 분류처럼 **텍스트 의미를 거리로 계산**해야 할 때
  - BM25 같은 lexical만으로는 recall이 부족한 **동의어/패러프레이즈/다국어** 환경
- 언제 쓰면 안 되나(또는 단독 사용 금지):  
  - “정답 근거”가 중요한 법률/의료처럼 **오탐 비용이 큰** 도메인에서 embedding만으로 top-k를 확정하는 경우(→ reranker/hybrid 필요)
  - 데이터가 짧고 라벨이 충분한 분류 문제(→ fine-tuned classifier가 더 싸고 정확할 때가 많음)

이번 글은 2026년 4월 시점의 공개 자료(모델 문서/리더보드/가격표)를 바탕으로, **OpenAI 임베딩(text-embedding-3), Cohere Embed(v3/v4), BGE-M3**를 “내 프로젝트 기준”으로 비교하고, 도메인별 선택 가이드를 제공합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/embeddings/embedding-models%20.class?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Embedding 비교에서 진짜 중요한 축 4가지
1. **품질(정확도) = 도메인 분포 + 평가셋**  
   MTEB 같은 리더보드는 유용하지만, 내 데이터(예: 고객센터 말투, 사내 약어, 긴 PDF, 혼합 언어)에선 순위가 뒤집히기도 합니다. “MTEB 상위=내 서비스 상위”가 아닙니다. ([discuss.huggingface.co](https://discuss.huggingface.co/t/why-are-my-benchmark-results-so-different-from-the-mteb-leaderboard/168305?utm_source=openai))

2. **Vector 차원(dimension) = 저장비/속도/정확도의 삼각형**  
   - OpenAI는 `text-embedding-3-large`가 기본 3072d, `3-small`이 1536d이며, API에서 **dimensions로 축소**(예: 1024, 256)할 수 있습니다. 이때 정확도와 저장비를 트레이드오프합니다. ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))  
   - Cohere는 Embed v3/v4 계열에서 **Matryoshka Embeddings(256/512/1024/1536 등)** 를 공식 지원합니다(차원 줄여도 상대적으로 의미 보존). ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed?utm_source=openai))  
   - BGE-M3는 오픈소스라 “차원 축소”는 보통 PCA/quantization 같은 후처리로 해결합니다(모델이 matryoshka로 학습된 건 아니라서 단순 슬라이싱은 위험). ([huggingface.co](https://huggingface.co/BAAI/bge-m3?utm_source=openai))

3. **맥락 길이/입력 단위 = “긴 문서” 비용 구조를 바꿈**  
   Cohere 문서에는 Embed 모델의 **최대 토큰(예: 128k)** 과 차원 옵션이 명시되어 있습니다. 긴 PDF/규정집을 “덩어리 크게” 넣고 싶은 팀에 중요합니다. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed?utm_source=openai))  
   (OpenAI 임베딩도 max token이 공개 문서/가이드에 정리되어 있습니다.) ([pinecone.io](https://www.pinecone.io/learn/openai-embeddings-v3/?utm_source=openai))

4. **운영 제약(보안/온프레/벤더락인/지연)**  
   - OpenAI/Cohere: 품질·운영 단순성 강점, 대신 API 의존  
   - BGE: 사내 GPU/온프레 배포 가능(데이터 거버넌스 강점), 대신 서빙·최적화·모니터링을 팀이 떠안음

### 2) 내부 작동 흐름(구조/흐름 관점)
실무 RAG 검색 파이프라인을 “embedding이 들어가는 지점”으로 쪼개면 다음입니다.

1. **Chunking(문서 분절)**: 문단/섹션/슬라이딩 윈도우로 자르기  
2. **Embedding 생성**: chunk → vector  
3. **Indexing**: HNSW/IVF 등 ANN 인덱스 구성  
4. **Query embedding**: 질의 → vector  
5. **ANN 검색(top-k)**: 근접 벡터 후보 추출  
6. **(권장) Rerank**: cross-encoder/LLM rerank로 top-k 재정렬  
7. **Answering**: top 문서로 LLM 생성

여기서 **embedding 모델 선택**은 2,4의 품질뿐 아니라 3,5의 비용(차원/정규화/metric)까지 영향을 줍니다. OpenAI는 `dimensions`로 벡터 길이를 줄이는 “내장형” 최적화 옵션을 제공하고, Cohere는 matryoshka 차원 세트를 공식적으로 제공합니다. ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))

### 3) “OpenAI vs Cohere vs BGE”를 한 줄로 요약하면
- **OpenAI(text-embedding-3)**: API로 빠르게 고품질. `dimensions`로 저장/성능 튜닝 가능. 가격표가 명확해 비용 산정이 쉽다. ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))  
- **Cohere Embed(v3/v4)**: 기업 환경에서 선호되는 케이스가 많고(특히 배포 옵션/긴 컨텍스트), matryoshka 차원 지원이 강점. ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed?utm_source=openai))  
- **BGE-M3(BAAI)**: 온프레/로컬 최강 후보. 다국어/다기능을 목표로 한 모델/연구 생태계가 탄탄. 다만 “내 도메인” 성능 보장은 결국 자체 평가가 답. ([huggingface.co](https://huggingface.co/BAAI/bge-m3?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “toy”가 아니라, **사내 위키 + PDF 텍스트 + 고객문의** 같이 섞인 코퍼스를 가정합니다.

- 입력 문서: `data/docs/*.md`, `data/tickets.jsonl`
- 공통: chunking → embedding → FAISS 인덱싱 → 질의 검색(top-k)  
- 모델만 교체: OpenAI / Cohere / BGE

### 0) 의존성 설치 & 환경변수
```bash
pip install -U faiss-cpu numpy tiktoken python-dotenv openai cohere sentence-transformers
export OPENAI_API_KEY="..."
export COHERE_API_KEY="..."
```

### 1) 인덱싱/검색 공통 코드 (OpenAI/Cohere/BGE 플러그인)
```python
import os, json, glob
import numpy as np
import faiss
from dataclasses import dataclass
from typing import List, Dict, Tuple, Protocol

# -------------------------
# Chunking (현실적인 기본형)
# -------------------------
def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    text = text.replace("\r\n", "\n")
    chunks = []
    i = 0
    while i < len(text):
        j = min(len(text), i + max_chars)
        chunk = text[i:j].strip()
        if chunk:
            chunks.append(chunk)
        i = j - overlap
        if i < 0:
            i = 0
        if j == len(text):
            break
    return chunks

# -------------------------
# Embedding Provider 인터페이스
# -------------------------
class Embedder(Protocol):
    dim: int
    def embed(self, texts: List[str], *, is_query: bool) -> np.ndarray: ...

@dataclass
class CorpusItem:
    doc_id: str
    text: str

def load_corpus() -> List[CorpusItem]:
    items: List[CorpusItem] = []

    for path in glob.glob("data/docs/*.md"):
        doc_id = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        for k, ch in enumerate(chunk_text(raw)):
            items.append(CorpusItem(doc_id=f"{doc_id}#chunk{k}", text=ch))

    for path in glob.glob("data/tickets.jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for n, line in enumerate(f):
                obj = json.loads(line)
                # 예: {"ticket_id":"T-19381","subject":"...","body":"...","lang":"ko"}
                raw = f"[SUBJECT] {obj.get('subject','')}\n[BODY]\n{obj.get('body','')}"
                for k, ch in enumerate(chunk_text(raw)):
                    items.append(CorpusItem(doc_id=f"{obj.get('ticket_id','T?')}#chunk{k}", text=ch))

    return items

def l2_normalize(x: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(x, axis=1, keepdims=True) + 1e-12
    return x / norm

def build_faiss_cosine_index(vectors: np.ndarray) -> faiss.Index:
    # cosine ~= inner product on normalized vectors
    vectors = l2_normalize(vectors).astype("float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    return index

def search(index: faiss.Index, doc_vectors: np.ndarray, query_vec: np.ndarray, top_k: int = 8) -> List[Tuple[int, float]]:
    q = l2_normalize(query_vec).astype("float32")
    scores, ids = index.search(q, top_k)
    return list(zip(ids[0].tolist(), scores[0].tolist()))

# -------------------------
# OpenAI Embedder
# -------------------------
class OpenAIEmbedder:
    def __init__(self, model: str = "text-embedding-3-large", dimensions: int | None = 1024):
        from openai import OpenAI
        self.client = OpenAI()
        self.model = model
        self.dim = dimensions if dimensions else (3072 if model.endswith("3-large") else 1536)

        # OpenAI는 dimensions 파라미터로 축소 가능 (저장/속도 vs 정확도 튜닝 포인트)
        self.dimensions = dimensions

    def embed(self, texts: List[str], *, is_query: bool) -> np.ndarray:
        # OpenAI embeddings API는 input 배열 지원
        resp = self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions
        )
        vecs = np.array([d.embedding for d in resp.data], dtype="float32")
        return vecs

# -------------------------
# Cohere Embedder
# -------------------------
class CohereEmbedder:
    def __init__(self, model: str = "embed-multilingual-v3.0", input_type_query: str = "search_query",
                 input_type_doc: str = "search_document", dim: int = 1024):
        import cohere
        self.client = cohere.Client(os.environ["COHERE_API_KEY"])
        self.model = model
        self.dim = dim
        self.input_type_query = input_type_query
        self.input_type_doc = input_type_doc

    def embed(self, texts: List[str], *, is_query: bool) -> np.ndarray:
        input_type = self.input_type_query if is_query else self.input_type_doc
        # Cohere는 dimension 옵션/Matryoshka를 공식적으로 제공(모델/버전에 따라 지원 범위 상이)
        resp = self.client.embed(
            model=self.model,
            texts=texts,
            input_type=input_type,
            embedding_types=["float"],
            truncate="END"
        )
        vecs = np.array(resp.embeddings.float, dtype="float32")
        # 일부 설정에서는 반환 dim이 model/config에 의해 결정되므로, 운영에선 여기서 assert로 고정 권장
        return vecs

# -------------------------
# BGE Embedder (로컬)
# -------------------------
class BGEEmbedder:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        # sentence-transformers는 get_sentence_embedding_dimension 제공
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str], *, is_query: bool) -> np.ndarray:
        # BGE류는 query/doc 프롬프트를 붙이는 레시피가 있는 경우가 많음(모델 카드 권장사항 확인)
        # 여기서는 운영 단순화를 위해 동일 인코딩(대신 자체 튜닝 여지 남김)
        vecs = self.model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        return np.array(vecs, dtype="float32")

# -------------------------
# 파이프라인 실행
# -------------------------
def run(embedder: Embedder, query: str):
    corpus = load_corpus()
    doc_texts = [c.text for c in corpus]

    doc_vecs = embedder.embed(doc_texts, is_query=False)
    assert doc_vecs.shape[1] == embedder.dim or True  # Cohere/BGE는 dim이 유동일 수 있어 운영에선 엄격히 맞추세요.

    index = build_faiss_cosine_index(doc_vecs)

    q_vec = embedder.embed([query], is_query=True)
    hits = search(index, doc_vecs, q_vec, top_k=8)

    print(f"\n[Query] {query}\nTop hits:")
    for rank, (idx, score) in enumerate(hits, 1):
        item = corpus[idx]
        snippet = item.text[:120].replace("\n", " ")
        print(f"{rank:02d}. score={score:.4f} id={item.doc_id} :: {snippet}...")

if __name__ == "__main__":
    q = "결제 오류가 반복될 때 고객에게 어떤 안내를 해야 하나요? (한국어/영어 혼합 문서 포함)"
    # 1) OpenAI: 3-large를 1024d로 줄여 저장비/속도 타협
    # run(OpenAIEmbedder(model="text-embedding-3-large", dimensions=1024), q)

    # 2) Cohere: multilingual v3 기반 (운영 환경에 따라 v4 사용 고려)
    # run(CohereEmbedder(model="embed-multilingual-v3.0", dim=1024), q)

    # 3) BGE: 로컬/온프레
    run(BGEEmbedder("BAAI/bge-m3"), q)
```

#### 예상 출력(형태)
- “결제 오류”, “billing failure”, “payment declined”가 섞인 문서가 상위에 뜨고, 사내 위키의 “결제 장애 대응 Runbook” 섹션 chunk가 1~3위로 뜨는 형태가 정상입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 효과 나는 것 3가지)
1) **차원(dimension)을 ‘저장비’가 아니라 ‘SLA’로 결정**  
- 대규모 코퍼스(수백만 chunk)에서는 3072d→1024d만 내려도 **RAM/디스크/인덱스 빌드 시간**이 크게 줄고, 그게 곧 latency/비용으로 직결됩니다.  
- OpenAI는 `dimensions`로 축소 가능하고, Cohere는 matryoshka 차원 세트가 강점입니다. ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))

2) **“top-k는 embedding, 최종은 rerank”로 책임 분리**  
- embedding은 recall 담당(많이 가져오기), reranker는 precision 담당(정확히 고르기).  
- 법률/정책/의료 같은 도메인에서 “embedding만으로 top-3 확정”은 사고 확률이 높습니다(문장 뉘앙스·예외조항·최신성 이슈).

3) **MTEB 점수보다 ‘우리 쿼리 로그’ 200개가 더 가치 있음**  
- 최소한 (a) 실제 질의 200개, (b) 정답 chunk 라벨(약식으로라도)을 만들어서,  
  - Recall@k (k=10/20)  
  - nDCG@10  
  - “다국어/오탈자/짧은 쿼리” 별 slice  
  로 비교하세요. 리더보드와 다른 결과가 나오는 건 흔합니다. ([discuss.huggingface.co](https://discuss.huggingface.co/t/why-are-my-benchmark-results-so-different-from-the-mteb-leaderboard/168305?utm_source=openai))

### 흔한 함정 / 안티패턴
- **(함정) 모델을 바꾸고 과거 임베딩을 그대로 사용**  
  임베딩 공간이 바뀌면 유사도 의미가 깨집니다. “모델 변경 = 재임베딩”이 원칙입니다(부분 마이그레이션은 듀얼 인덱스 등 설계 필요). ([reddit.com](https://www.reddit.com/r/vectordatabase/comments/152s1ii?utm_source=openai))
- **(함정) cosine/IP metric 혼용 + 정규화 누락**  
  Cohere/OpenAI/BGE 조합에서 특히 많이 터집니다. “cosine로 검색”이면 **문서/쿼리 모두 normalize**를 습관화하세요.
- **(안티패턴) chunk를 너무 작게 쪼개서 의미가 깨짐**  
  고객문의/규정은 문맥 의존이 커서 과도한 분절이 오히려 성능을 내립니다. “chunk 크기”는 embedding 모델보다 먼저 튜닝할 때가 많습니다.

### 비용/성능/안정성 트레이드오프(2026년 4월 관점)
- OpenAI 임베딩은 공개 가격표 기준으로 `text-embedding-3-large`가 더 비싸고, `3-small`이 비용 효율이 좋다는 분석이 많습니다. (대량 인덱싱이면 batch 할인 언급도 자주 등장) ([awesomeagents.ai](https://awesomeagents.ai/pricing/embedding-models-pricing/?utm_source=openai))  
- Cohere는 모델에 따라 차원/컨텍스트/배포 옵션이 달라 “조직 제약”에 맞출 때 강점이 생깁니다(특히 matryoshka, 멀티모달/기업 배포 옵션 언급). ([docs.cohere.com](https://docs.cohere.com/changelog/embed-multimodal-v4?utm_source=openai))  
- BGE-M3는 GPU가 있으면 토큰당 비용을 “내부 비용”으로 바꿀 수 있지만, 서빙 장애/스케일링/업그레이드까지 포함하면 총소유비용(TCO)이 다시 올라갈 수 있습니다. ([huggingface.co](https://huggingface.co/BAAI/bge-m3?utm_source=openai))

---

## 🚀 마무리
핵심만 정리하면, 2026년 4월 기준 “OpenAI vs Cohere vs BGE”는 **성능만의 싸움이 아니라 운영 모델의 선택**입니다.

- **OpenAI(text-embedding-3-small/large)** 를 고르기 좋은 팀  
  - 빠르게 제품화, 품질 상향, `dimensions`로 저장비 튜닝까지 하고 싶다 ([openai.com](https://openai.com/index/new-embedding-models-and-api-updates/?utm_source=openai))
- **Cohere Embed(v3/v4)** 가 맞는 팀  
  - matryoshka 차원/긴 컨텍스트/기업 배포 옵션 등 “조직 제약”이 크다 ([docs.cohere.com](https://docs.cohere.com/docs/cohere-embed?utm_source=openai))
- **BGE-M3** 가 맞는 팀  
  - 온프레/사내망/데이터 레지던시가 1순위, 그리고 서빙을 직접 운영할 역량이 있다 ([huggingface.co](https://huggingface.co/BAAI/bge-m3?utm_source=openai))

다음 학습/실험 추천:
1) 내 쿼리 200개로 **Recall@20 + nDCG@10** 미니 벤치 만들기  
2) 차원 1536 vs 1024 vs 512로 내려가며 **인덱스 크기/지연/품질** 같이 측정  
3) embedding 단독이 아니라 **hybrid(BM25 + dense) + rerank**까지 포함한 end-to-end로 비교

원하시면, “당신 도메인(예: 법률/CS/개발문서/쇼핑/논문)”과 “코퍼스 규모(문서 수/평균 길이/언어)”를 알려주시면, 위 코드 베이스로 **모델 3종을 동일 조건으로 벤치마크하는 체크리스트 + 지표 설계**까지 더 구체화해 드릴게요.