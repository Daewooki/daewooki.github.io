---
title: "중복이 성능을 갉아먹는다: 2026년식 데이터 큐레이션 Dedup + Dataset Quality 전처리 실전 설계"
date: 2026-06-13 04:28:53 +0900
categories: [AI, Data]
tags: [ai, data, trend, 2026-06]
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
LLM/임베딩/검색 모델 학습 데이터에서 **중복(duplicate / near-duplicate)** 은 생각보다 “조용히” 비용과 품질을 동시에 망칩니다. 비용 관점에서는 같은 패턴을 반복 학습해 **유효 토큰 다양도**가 줄고, 품질 관점에서는 (1) 특정 문장/코드/템플릿이 과대표집되어 편향이 생기거나 (2) evaluation split과의 **leakage**로 지표가 부풀 수 있습니다. “Deduplicating Training Data Makes Language Models Better” 류의 결과는 이제 상식에 가까워졌고, 오픈 데이터 큐레이션 벤치마크(DataComp-LM)도 **deduplication + filtering**을 핵심 축으로 다룹니다. ([arxiv.org](https://arxiv.org/abs/2107.06499?utm_source=openai))

**언제 쓰면 좋나**
- CommonCrawl/웹 스크랩/깃 레포/문서 덤프처럼 **재게시·미러·보일러플레이트**가 많은 코퍼스
- synthetic data를 대량 생성할 때(템플릿 붕괴, 패턴 반복 감시)
- 멀티모달(이미지/비디오)에서 리사이즈·크롭·워터마크로 **겉보기만 다른 중복**이 많을 때(semantic dedup 필요)

**언제 쓰면 안 되나(혹은 매우 조심)**
- 데이터가 원래부터 “의도적으로 반복”인 경우(예: 특정 정책/규약 문구를 강하게 학습시키려는 instruction set). 이때는 “중복 제거”가 아니라 **중복 상한(cap)과 mixing** 문제입니다.
- 규모가 작고(수만~수십만) 도메인이 좁아서, 중복이 사실상 “정답 패턴”인 경우. 지나친 dedup은 오히려 recall/커버리지를 깎습니다.
- dedup을 “품질 필터”로 착각하는 경우: 중복이 없어도 쓰레기 텍스트는 그대로 남습니다(둘은 별개 축).

---

## 🔧 핵심 개념
### 1) 중복의 3종 세트: exact / lexical near-dup / semantic near-dup
실무에서는 보통 **3단계 방어선**으로 설계합니다.

1. **Exact dedup**  
   - 동일 바이트(또는 정규화 후 동일)면 cryptographic hash(MD5/SHA-256 등)로 끝.  
   - 가장 싸고, 가장 확실합니다(precision 100%).  
2. **Lexical near-duplicate (MinHash/SimHash 계열)**  
   - “복붙/보일러플레이트/거의 동일”을 잡는 구간.  
   - 대표적으로 **w-shingling(예: 5-gram)** → **MinHash signature** → **LSH**로 후보를 만든 뒤, 후보끼리만 Jaccard를 확인하는 흐름이 정석입니다. ([metricgate.com](https://metricgate.com/docs/minhash-near-duplicate-detection/?utm_source=openai))  
   - Hugging Face DataTrove도 MinHash+LSH를 문서 단위 dedup의 핵심으로 두고, `num_buckets=14`, `hashes_per_bucket=8` 같은 실무형 기본값을 제공합니다(즉, 파라미터가 “연구”가 아니라 “운영”에 가까운 레시피로 굳어가는 중). ([deepwiki.com](https://deepwiki.com/huggingface/datatrove/5-tokenization-and-data-preparation?utm_source=openai))  
3. **Semantic dedup (embedding 기반)**  
   - “의미는 같은데 문장만 바뀐 패러프레이즈”까지 잡습니다.  
   - 단점은 비용: Crawlix 같은 현업 도구도 embedding-based dedup이 잡는 추가 이득이 제한적이고 compute가 크다고 언급합니다(ROI 문제). ([crawlix.app](https://crawlix.app/blog/duplicate-content-detection/?utm_source=openai))  
   - 그래도 멀티모달/짧은 문장/번역 데이터처럼 lexical 기준이 잘 안 먹히는 곳에서는 효과가 큽니다. NeMo Curator는 exact/fuzzy(MinHash)/semantic(embedding) 워크플로를 한 도구 상에서 제공하며, semantic dedup workflow를 명시적으로 제공합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/26.02/curate-text/process-data/deduplication/index.html?utm_source=openai))  

### 2) 내부 작동 방식(“구조/흐름” 관점)
#### MinHash + LSH 파이프라인(텍스트)
- **정규화(normalization)**: HTML boilerplate 제거, 공백/유니코드 정규화, 낮은 신호 구간(네비게이션/푸터) 제거  
- **Shingling**: 토큰 5-gram 또는 char n-gram으로 집합(set) 생성  
- **MinHash**: shingle set을 여러 hash permutation으로 스케치(signature)로 압축  
- **LSH banding**: signature를 band로 나눠 같은 bucket에 들어온 것만 “후보(candidates)”로 봄  
- **후처리(검증)**: 후보 쌍에 대해 실제 Jaccard(또는 overlap) 계산 → threshold 넘으면 같은 cluster로 병합  
- **keeper policy**: cluster마다 대표 1개만 남기거나(가장 긴 문서/품질 점수 최고) 혹은 상한 K개만 남김

핵심은: **LSH는 후보 생성기**일 뿐이고, 마지막에 “정확한(또는 더 정확한) 판정”이 들어가야 운영에서 사고가 덜 납니다. NVIDIA NeMo 문서도 MinHash+LSH의 근사성 때문에 bucket 내부에서 false positive를 후처리로 제거한다고 설명합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/24.07/datacuration/gpudeduplication.html?utm_source=openai))  

#### Semantic dedup(embedding) 파이프라인
- 문서(또는 chunk)를 embedding
- ANN index(FAISS 등)로 kNN 후보 생성
- cosine/L2 threshold 또는 clustering(k-means 등) 후 대표만 유지  
NeMo Curator는 텍스트/비디오 등에서 embedding 기반 semantic dedup 튜토리얼과 워크플로를 제공합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/latest/curate-video/tutorials/split-dedup.html?utm_source=openai))  

### 3) 다른 접근과의 차이점(선택 기준)
- **MinHash**: “텍스트가 얼마나 겹치나(lexical overlap)” → 빠르고 해석 가능, 보일러플레이트에 강함 ([metricgate.com](https://metricgate.com/docs/minhash-near-duplicate-detection/?utm_source=openai))  
- **SimHash**: 64-bit 같은 초저비용 fingerprint로 근사 유사도(Hamming distance) → 아주 싸지만 임계값 튜닝이 거칠 수 있음 ([crawlix.app](https://crawlix.app/blog/duplicate-content-detection/?utm_source=openai))  
- **Embedding**: 의미 중복까지 → 비용 높고, 임계값/도메인별 편향 이슈(특히 semantic dedup이 특정 그룹을 더 많이 제거하는 문제도 연구됨) ([openaccess.thecvf.com](https://openaccess.thecvf.com/content/CVPR2024/papers/Slyman_FairDeDup_Detecting_and_Mitigating_Vision-Language_Fairness_Disparities_in_Semantic_Dataset_CVPR_2024_paper.pdf?utm_source=openai))  

---

## 💻 실전 코드
아래는 “웹 문서/스크랩” 1~수천만 건에서 흔한 운영 형태인 **2-stage dedup** 예시입니다.

- Stage A: **Exact + MinHash(lexical)로 1차 대량 제거**
- Stage B: 남은 데이터에 **Semantic dedup(embedding)로 ‘의미 중복’만 제한적으로 제거**
- 모든 단계는 **Parquet** 기반으로 “RAM보다 큰 데이터”를 상정합니다.

### 0) 의존성/입력 가정
- 입력: `data/raw_docs/*.parquet`  
  - 컬럼: `doc_id`(string), `text`(string), `source`(string), `timestamp`(optional)
- 출력: `data/curated_docs/*.parquet` + dedup 리포트

```bash
pip install "polars>=0.20" pyarrow datasketch fasttext-wheel sentence-transformers faiss-cpu tqdm
# faiss-gpu 환경이면 faiss-gpu로 교체
```

### 1) Stage A — Exact + MinHash(LSH) 문서 단위 dedup
현실적인 포인트:
- “문서 전체”만 하면 누적 boilerplate(푸터/헤더) 때문에 false positive가 늘 수 있어, 전처리에서 **본문 추출/라인 필터**가 중요합니다.
- LSH는 후보만 만들고, 후보에 대해 실제 Jaccard를 계산해 확정합니다(운영 안전장치).

```python
import re
import hashlib
from datasketch import MinHash, MinHashLSH
import polars as pl
from tqdm import tqdm

WORD_RE = re.compile(r"\w+", re.UNICODE)

def normalize_text(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    # 너무 공격적인 정규화(구두점 제거 등)는 도메인에 따라 의미를 죽일 수 있어 최소화
    return s

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def shingles(text: str, k: int = 5):
    toks = WORD_RE.findall(text)
    if len(toks) < k:
        return []
    return [" ".join(toks[i:i+k]) for i in range(len(toks)-k+1)]

def build_minhash(text: str, num_perm: int = 128, shingle_k: int = 5) -> MinHash:
    mh = MinHash(num_perm=num_perm)
    for sh in set(shingles(text, k=shingle_k)):
        mh.update(sh.encode("utf-8"))
    return mh

def jaccard_estimate(a: MinHash, b: MinHash) -> float:
    return a.jaccard(b)

# ---- load ----
df = pl.scan_parquet("data/raw_docs/*.parquet").select(["doc_id", "text", "source"]).collect()

# ---- exact dedup (after normalization) ----
df = df.with_columns(
    pl.col("text").map_elements(normalize_text, return_dtype=pl.Utf8).alias("text_norm")
).with_columns(
    pl.col("text_norm").map_elements(sha256_hex, return_dtype=pl.Utf8).alias("hash_exact")
)

df_exact = df.unique(subset=["hash_exact"], keep="first")  # exact duplicates 제거
print(f"After exact dedup: {df_exact.height:,} docs")

# ---- MinHash + LSH ----
NUM_PERM = 128
SHINGLE_K = 5
# threshold는 운영에서 가장 중요한 knob: 0.7~0.9 사이를 도메인별로 실험
LSH_THRESHOLD = 0.8

lsh = MinHashLSH(threshold=LSH_THRESHOLD, num_perm=NUM_PERM)
minhashes = {}
kept = []
seen = set()

# 미리 MinHash 만들기(큰 규모면 배치/분산 필요)
for row in tqdm(df_exact.iter_rows(named=True), total=df_exact.height):
    doc_id = row["doc_id"]
    if doc_id in seen:
        continue
    mh = build_minhash(row["text_norm"], num_perm=NUM_PERM, shingle_k=SHINGLE_K)
    minhashes[doc_id] = mh

# LSH 인덱싱 + 클러스터링(간단 버전: 먼저 들어온 것을 대표로 유지)
for row in tqdm(df_exact.iter_rows(named=True), total=df_exact.height):
    doc_id = row["doc_id"]
    if doc_id in seen:
        continue

    mh = minhashes[doc_id]
    candidates = lsh.query(mh)

    # 후보가 있으면 실제 유사도 확인(여기서는 MinHash jaccard 추정치로 2차 확인)
    dup_found = False
    for c in candidates:
        if c == doc_id:
            continue
        if jaccard_estimate(mh, minhashes[c]) >= LSH_THRESHOLD:
            dup_found = True
            break

    if not dup_found:
        kept.append(doc_id)
        lsh.insert(doc_id, mh)  # 대표만 인덱스에 넣는 정책
    seen.add(doc_id)

df_stage_a = df_exact.filter(pl.col("doc_id").is_in(kept)).drop(["text_norm", "hash_exact"])
print(f"After MinHash dedup: {df_stage_a.height:,} docs")

df_stage_a.write_parquet("data/curated_docs/stage_a_minhash.parquet")
```

**예상 출력(형태)**
- `After exact dedup: 12,345,678 docs`
- `After MinHash dedup: 9,876,543 docs`

> 운영 규모(수천만~수십억)면 위 코드는 단일 머신에선 부족합니다. 하지만 “정책/파라미터/리포팅 구조”는 동일하고, 실행 엔진만 Ray/Spark/NeMo Curator/DataTrove로 옮기는 게 보통입니다. NeMo Curator가 exact/fuzzy(MinHash+LSH) dedup을 워크플로로 제공하는 이유가 여기 있습니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/26.02/curate-text/process-data/deduplication/index.html?utm_source=openai))  

### 2) Stage B — Semantic dedup(선택 적용, 비용 통제)
여기서는 Stage A에서 줄인 데이터에만, 그리고 “짧고 패러프레이즈가 많은” 소스(예: Q/A, instruction, 요약문)만 골라 semantic dedup을 거는 식으로 비용을 통제합니다. NeMo Curator도 semantic matching을 별도 워크플로로 제공합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/26.02/curate-text/process-data/deduplication/index.html?utm_source=openai))  

```python
import numpy as np
import polars as pl
from sentence_transformers import SentenceTransformer
import faiss
from tqdm import tqdm

df = pl.read_parquet("data/curated_docs/stage_a_minhash.parquet")

# 예: source가 "synthetic" 또는 "qa"인 문서만 semantic dedup
target = df.filter(pl.col("source").is_in(["synthetic", "qa"])).select(["doc_id", "text"])
rest   = df.filter(~pl.col("source").is_in(["synthetic", "qa"]))

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")  # NeMo Curator 예시에도 자주 등장 ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/26.02/curate-text/process-data/deduplication/index.html?utm_source=openai))
batch_size = 256

texts = target["text"].to_list()
doc_ids = target["doc_id"].to_list()

embs = []
for i in tqdm(range(0, len(texts), batch_size)):
    e = model.encode(texts[i:i+batch_size], normalize_embeddings=True)
    embs.append(e.astype("float32"))
X = np.vstack(embs)

dim = X.shape[1]
index = faiss.IndexFlatIP(dim)  # cosine == inner product (normalize_embeddings=True)
index.add(X)

# threshold 튜닝이 전부: 0.92~0.98 사이를 도메인별로 검증
SIM_THRESHOLD = 0.96
k = 10

kept = []
dropped = set()
for i in tqdm(range(X.shape[0])):
    if i in dropped:
        continue
    kept.append(i)
    D, I = index.search(X[i:i+1], k)
    for j, sim in zip(I[0], D[0]):
        if j == i:
            continue
        if sim >= SIM_THRESHOLD:
            dropped.add(j)

kept_ids = [doc_ids[i] for i in kept]
target_dedup = target.filter(pl.col("doc_id").is_in(kept_ids))

out = pl.concat([rest, target_dedup], how="vertical")
out.write_parquet("data/curated_docs/final.parquet")

print(f"StageB semantic kept: {target_dedup.height:,}/{target.height:,}")
print(f"Final: {out.height:,}")
```

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **Dedup을 “순서”로 설계하라: cheap → expensive**
- Exact → MinHash/SimHash → Embedding 순으로 가야 총비용이 안정됩니다. Crawlix가 embedding 기반을 “추가 이득 대비 10× 비용”으로 보는 관점도 같은 맥락입니다. ([crawlix.app](https://crawlix.app/blog/duplicate-content-detection/?utm_source=openai))  

2) **keeper policy를 “품질 점수”와 결합**
- 중복 클러스터에서 “첫 번째”를 남기면, 운 나쁘면 저품질(짧은/깨진) 샘플이 대표가 됩니다.  
- DataComp-LM 쪽 흐름이 보여주듯, 결국 승부는 “필터링/스코어링과의 결합”입니다. ([papers.nips.cc](https://papers.nips.cc/paper_files/paper/2024/hash/19e4ea30dded58259665db375885e412-Abstract-Datasets_and_Benchmarks_Track.html?utm_source=openai))  
- 실무에선 대표 선택을 `quality_score`(길이, 언어확률, perplexity proxy, 포맷 점수, 소스 신뢰도) 최대인 것으로 둡니다.

3) **평가/학습 split leakage를 별도 트랙으로 잡아라**
- “train 내부 dedup”만으로 끝내지 말고, **train ↔ eval** 교차 dedup(또는 유사도 검색)을 별도 작업으로 돌리세요. 이거 하나로 지표 신뢰도가 달라집니다.

### 흔한 함정/안티패턴
- **LSH 결과를 맹신**: LSH는 후보 생성이고, 후검증이 없으면 false positive로 데이터가 과도하게 날아갑니다(NeMo 문서도 bucket 후처리를 언급). ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/24.07/datacuration/gpudeduplication.html?utm_source=openai))  
- **문서 단위만 dedup**: 긴 문서 내부에 반복되는 boilerplate/코드블록/라이선스가 토큰을 잡아먹습니다. 문서 dedup 후에도 “span/sentence-level dedup”이 필요한 경우가 많습니다(DataTrove는 sentence-level dedup을 별도 전략으로 둠). ([deepwiki.com](https://deepwiki.com/huggingface/datatrove/5-tokenization-and-data-preparation/?utm_source=openai))  
- **Semantic dedup을 전체에 전면 적용**: 비용도 비용이지만, 임계값 하나로 모든 도메인을 커버하려다 보면 특정 스타일/집단이 더 많이 제거되는 편향 문제가 생길 수 있습니다(semantic dedup의 fairness 이슈가 연구 주제로도 존재). ([openaccess.thecvf.com](https://openaccess.thecvf.com/content/CVPR2024/papers/Slyman_FairDeDup_Detecting_and_Mitigating_Vision-Language_Fairness_Disparities_in_Semantic_Dataset_CVPR_2024_paper.pdf?utm_source=openai))  

### 비용/성능/안정성 트레이드오프(결정 기준)
- **MinHash 파라미터(perm 수, bucket/band 구성)**: recall↑(더 잘 잡음) vs 후보쌍↑(비용↑). DataTrove/NeMo 쪽 기본값이 존재하는 건, 이게 “적당히 괜찮은 운영점”이기 때문입니다. ([deepwiki.com](https://deepwiki.com/huggingface/datatrove/5-tokenization-and-data-preparation?utm_source=openai))  
- **Embedding threshold**: 조금만 낮추면 “의미가 비슷한데 필요한 다양성”까지 날릴 수 있음. 보통은
  - (a) 특정 소스만 적용
  - (b) cluster size cap
  - (c) human spot-check로 보정
  조합으로 갑니다.

---

## 🚀 마무리
정리하면, 2026년 6월 기준 실무 데이터 큐레이션에서 “정답에 가까운” dedup 설계는 다음입니다.

- **Exact dedup**은 무조건(가성비 최고)
- **MinHash+LSH(lexical near-dup)** 로 웹/코드/문서의 대량 중복을 먼저 눌러서 토큰 낭비를 제거(NeMo Curator, DataTrove 같은 툴체인이 이미 이 흐름을 표준화) ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/26.02/curate-text/process-data/deduplication/index.html?utm_source=openai))  
- **Semantic dedup(embedding)** 은 ROI가 나오는 구간(패러프레이즈가 많은 소스/멀티모달/번역)에만 “선택적으로” 적용 ([crawlix.app](https://crawlix.app/blog/duplicate-content-detection/?utm_source=openai))  
- dedup은 품질의 일부일 뿐이므로, 최종적으로는 **quality scoring/필터링과 결합**해서 keeper policy까지 포함한 “큐레이션 레시피”로 굳혀야 합니다(DataComp-LM이 그 방향을 벤치마크로 고정). ([papers.nips.cc](https://papers.nips.cc/paper_files/paper/2024/hash/19e4ea30dded58259665db375885e412-Abstract-Datasets_and_Benchmarks_Track.html?utm_source=openai))  

**도입 판단 기준**
- 내 데이터에서 (1) exact dup 비율, (2) 5-gram 기반 near-dup 비율, (3) semantic dup 비율을 샘플링으로 먼저 추정해보세요.  
- (2)가 크면 MinHash가 1순위, (3)가 의미 있게 크고 모델이 패러프레이즈에 민감하면 semantic을 제한적으로 얹는 게 합리적입니다.

**다음 학습 추천**
- DataComp-LM 논문/레시피를 “내 도메인 코퍼스에 적용 가능한 실험 설계” 관점으로 읽기 ([papers.nips.cc](https://papers.nips.cc/paper_files/paper/2024/hash/19e4ea30dded58259665db375885e412-Abstract-Datasets_and_Benchmarks_Track.html?utm_source=openai))  
- NeMo Curator의 dedup 워크플로(Exact/Fuzzy/Semantic) 문서로 운영 파이프라인 형태 익히기 ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/26.02/curate-text/process-data/deduplication/index.html?utm_source=openai))  
- MinHash/LSH 파라미터 감 잡기(왜 threshold가 그렇게 나오는지) ([metricgate.com](https://metricgate.com/docs/minhash-near-duplicate-detection/?utm_source=openai))  

원하면, (1) 당신의 데이터 형태(문서 평균 길이, 언어, 소스, 규모)와 (2) 목표(사전학습 vs SFT vs RAG corpus)에 맞춰 **MinHash/LSH 파라미터(ngram, num_perm, band 구성)와 semantic threshold를 어떻게 실험/결정할지**를 더 구체적인 체크리스트로 내려드릴게요.