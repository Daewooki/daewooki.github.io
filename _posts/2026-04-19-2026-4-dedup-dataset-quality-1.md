---
title: "중복이 “학습 비용”을 태운다: 2026년 4월 기준 데이터 큐레이션 Dedup + Dataset Quality 전처리 실전 설계"
date: 2026-04-19 03:38:14 +0900
categories: [AI, Data]
tags: [ai, data, trend, 2026-04]
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
LLM/검색/분류/랭킹 모델을 막론하고 **학습 데이터의 중복(duplicate/near-duplicate)** 은 생각보다 치명적입니다. 첫째, **학습 비용을 그대로 증폭**시킵니다(같은 정보를 여러 번 학습). 둘째, **memorization/overfitting**을 유발해 “그럴듯하지만 일반화가 약한” 모델이 됩니다. 셋째, 평가셋/테스트셋과의 **data leakage(오염, contamination)** 를 만들어 지표를 속입니다(특히 벤치마크/사내 회귀테스트가 웹에서 왔다면 더 위험). NeMo Curator 문서도 실무 워크플로우를 “Quality filtering → Fuzzy deduplication” 순으로 제시합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/0.25.7/about/concepts/text/data-processing-concepts.html?utm_source=openai))

언제 쓰면 좋은가:
- 여러 소스(웹 크롤/로그/문서덤프/QA 생성물)를 섞어 **대규모 코퍼스**를 만들 때
- 파인튜닝/지식 주입에서 **템플릿형 반복**(예: 동일 포맷의 FAQ/상품 설명)이나 **재배포된 콘텐츠**가 많은 도메인
- 평가 신뢰도가 중요한데, **train–eval 중복** 가능성이 있을 때(특히 instruction/eval set)

언제 “과하게” 쓰면 안 되는가:
- 데이터가 본질적으로 반복되는 문제(예: 규격 문서, 코드 스니펫, 정책 문구)에서 **무리한 near-dup 제거**는 커버리지를 깎습니다.
- 다중 덤프(Common Crawl 여러 스냅샷 등)에서는 “너무 깊은 dedup”가 오히려 성능을 해칠 수 있다는 관찰도 있습니다(작은 클러스터까지 제거하면 OOD/저품질만 남는 방향으로 왜곡될 수 있음). ([reddit.com](https://www.reddit.com/r/LocalLLaMA/comments/1d6zwgy?utm_source=openai))  
  → 즉 “얼마나” 제거할지가 핵심이며, 무조건 많이 지우는 게임이 아닙니다.

---

## 🔧 핵심 개념
### 1) Dedup의 3계층: Exact / Near / Semantic
1) **Exact dedup**  
- 문서 정규화(whitespace/Unicode/HTML 제거 등) 후 해시(MD5/SHA)로 동일 문서 제거  
- 빠르고 확실하지만 “약간 수정된 복붙”은 못 잡음  
- RedPajama 파이프라인도 Bloom filter 기반 exact dedup와 LSH 기반 fuzzy dedup를 분리해 제공합니다. ([github.com](https://github.com/togethercomputer/RedPajama-Data?utm_source=openai))

2) **Near-duplicate(문자열 유사) dedup: MinHash + LSH**
- 문서를 character n-gram(shingle)로 쪼개고 MinHash signature를 만들고, LSH로 후보쌍을 좁혀 Jaccard 유사 문서군을 찾습니다.
- NeMo Curator는 흐름을 “MinHash → LSH bucket → (그래프) connected components로 그룹”으로 명시합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/curate-text/process-data/deduplication/fuzzy?utm_source=openai))
- 장점: 대규모에서도 근사적으로 동작, 텍스트가 거의 같은 변형(서식/오탈자) 제거에 강함
- 단점: 패러프레이즈(의미는 같지만 표현이 많이 다른 경우)는 약함

3) **Semantic dedup(임베딩 기반)**
- 문서를 임베딩해 ANN으로 가까운 이웃을 찾고, cosine/inner-product로 유사 클러스터를 제거
- SemHash는 SentenceTransformer류 임베딩 + ANN 백엔드를 이용한 “semantic dedup & filtering”를 전면으로 내세웁니다. ([github.com](https://github.com/MinishLab/semhash?utm_source=openai))
- 장점: 패러프레이즈/요약/번역체 중복까지 잡을 수 있음
- 단점: 비용(임베딩 계산) + 오탐 리스크(“주제는 비슷하지만 서로 다른 문서”를 지워버림)

### 2) 내부 작동 흐름(실무형)
제가 2026년 4월 시점에 권장하는 전처리/큐레이션 순서는 다음입니다.

1. **정규화/청소 (Normalize)**
   - Unicode 정규화, HTML→text, boilerplate 제거, 줄 반복/스팸 패턴 완화  
2. **Quality filtering**
   - 길이/비알파비율/반복라인/boilerplate 등 heuristic + (가능하면) 경량 모델 분류  
   - NeMo Curator는 “대부분의 사용자가 먼저 quality filtering”을 한다고 명시합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/0.25.7/about/concepts/text/data-processing-concepts.html?utm_source=openai))  
3. **Near-duplicate dedup (MinHash+LSH)**
   - 후보쌍을 LSH로 좁히고, 연결요소로 클러스터링한 뒤 “클러스터당 1개”를 선택  
   - (옵션) 버킷 내 pairwise Jaccard로 **false positive check**를 더해 오탐을 줄입니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/24.09/datacuration/gpudeduplication.html?utm_source=openai))  
4. **Semantic dedup (선택)**
   - 남은 데이터에만 적용(비용 절감), 또는 “평가셋/민감셋 decontamination”에 한정
5. **Cluster 대표 샘플 선택 정책**
   - 중요한 포인트: “중복군에서 무엇을 남길지”는 quality 점수에 의해 결정해야 합니다. RedPajama/NeMo류 파이프라인이 결국 이 방향입니다. ([mbrenndoerfer.com](https://mbrenndoerfer.com/writing/deduplication-exact-near-duplicate-jaccard-similarity-suffix-arrays?utm_source=openai))

### 3) 2026년 관점에서의 스케일 이슈: 메모리/디스크 병목
- 전통적인 MinHashLSH는 “인덱스가 커져서 메모리/디스크가 병목”이 되기 쉽습니다.
- 이를 정면으로 다룬 연구로 **LSHBloom**(MinHashLSH의 인덱스를 Bloom filter로 치환)이 있고, 극단적 규모에서 디스크 사용을 크게 줄이는 방향을 제안합니다. ([arxiv.org](https://arxiv.org/abs/2411.04257?utm_source=openai))  
- GPU로 MinHash/LSH를 가속하는 실무 프레임워크는 NeMo Curator가 대표적이며, 문서 단위 fuzzy dedup(near-dup 제거)를 구체적인 파라미터와 함께 제공합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/curate-text/process-data/deduplication/fuzzy?utm_source=openai))  
- 2025년 arXiv의 **FED**는 GPU 클러스터에서 MinHash LSH 파이프라인을 최적화해 대규모 토큰을 빠르게 처리하는 방향을 제시합니다. ([arxiv.org](https://arxiv.org/abs/2501.01046?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “toy”가 아니라, **사내 문서/로그/크롤 결과를 parquet(JSONL도 유사)** 로 모아 **(1) 품질 필터링 → (2) MinHash LSH near-dup 제거 → (3) 클러스터에서 quality가 가장 좋은 문서만 남기기**까지 한 번에 가는 형태입니다.

> 전제: 대규모에서는 Spark/Dask/Ray/NeMo Curator 같은 분산이 유리하지만, 여기서는 “단일 머신에서 수백만 문서까지”를 목표로 **현실적인 로컬 파이프라인**을 구성하고, 확장 포인트를 같이 적습니다.

### 0) 설치/입력 데이터 가정
- 입력: `data/raw/*.parquet`
- 스키마: `doc_id: str`, `url: str`, `text: str`, `ts: timestamp`
- 출력: `data/curated/train.parquet`

```bash
pip install "polars>=1.0.0" datasketch xxhash beautifulsoup4 regex tqdm
```

### 1) 품질 시그널 계산 + 1차 필터(heuristic)
- NeMo Curator가 제시하는 대표 heuristic(문서 길이, non-alphanumeric 비율, 반복 라인 등)을 로컬 버전으로 흉내냅니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/0.25.7/about/concepts/text/data-processing-concepts.html?utm_source=openai))

```python
import polars as pl
import re
import math
from bs4 import BeautifulSoup

_non_alnum = re.compile(r"[^0-9A-Za-z가-힣\s]")
_space = re.compile(r"\s+")
_line = re.compile(r"\r?\n")

def html_to_text(s: str) -> str:
    # 이미 text면 비용만 듦: "html일 때만" 태그가 충분히 있을 경우 적용하는 게 좋음
    if s is None:
        return ""
    if "<" in s and ">" in s:
        return BeautifulSoup(s, "html.parser").get_text(" ")
    return s

def normalize(s: str) -> str:
    s = html_to_text(s)
    s = s.replace("\u00a0", " ")
    s = _space.sub(" ", s).strip()
    return s

def non_alnum_ratio(s: str) -> float:
    if not s:
        return 1.0
    return len(_non_alnum.findall(s)) / max(len(s), 1)

def repeated_line_fraction(s: str) -> float:
    lines = [ln.strip() for ln in _line.split(s) if ln.strip()]
    if len(lines) < 5:
        return 0.0
    from collections import Counter
    c = Counter(lines)
    repeated = sum(v for v in c.values() if v >= 2)
    return repeated / len(lines)

def quality_score(s: str) -> float:
    # 단순하지만 실무에서 "클러스터 대표 선택"에 유용: (길이, 기호비율, 반복라인)로 점수화
    n = len(s)
    if n == 0:
        return -1e9
    # 너무 짧거나 너무 긴 문서는 감점(도메인에 맞게 튜닝)
    length_term = -abs(math.log(max(n, 1)) - math.log(2000))  # 2KB 근처 선호 예시
    sym_penalty = -3.0 * non_alnum_ratio(s)
    rep_penalty = -2.0 * repeated_line_fraction(s)
    return length_term + sym_penalty + rep_penalty

raw = (
    pl.scan_parquet("data/raw/*.parquet")
    .with_columns([
        pl.col("text").fill_null("").map_elements(normalize, return_dtype=pl.Utf8).alias("text_norm"),
    ])
    .with_columns([
        pl.col("text_norm").str.len_chars().alias("char_len"),
        pl.col("text_norm").map_elements(non_alnum_ratio, return_dtype=pl.Float64).alias("non_alnum_ratio"),
        pl.col("text_norm").map_elements(repeated_line_fraction, return_dtype=pl.Float64).alias("repeated_line_frac"),
        pl.col("text_norm").map_elements(quality_score, return_dtype=pl.Float64).alias("qscore"),
    ])
    .filter(
        (pl.col("char_len") >= 500) &
        (pl.col("char_len") <= 200_000) &
        (pl.col("non_alnum_ratio") <= 0.30) &
        (pl.col("repeated_line_frac") <= 0.60)
    )
)

df = raw.collect(streaming=True)
print(df.select(pl.len()).item(), "docs after quality filter")
print(df.select(["char_len","non_alnum_ratio","repeated_line_frac","qscore"]).describe())
```

예상 출력(예시):
- `N docs after quality filter` (원본 대비 30~70% 남는 경우가 흔함; 도메인마다 다름)
- `describe()`로 분포 확인 후 threshold 튜닝

### 2) MinHash LSH로 near-duplicate 클러스터 만들기
- NeMo Curator가 설명하는 방식과 동일하게 “character n-gram 기반 MinHash + LSH”를 로컬에서 구현합니다(분산/GPUs는 확장 섹션 참고). ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/curate-text/process-data/deduplication/fuzzy?utm_source=openai))

```python
from datasketch import MinHash, MinHashLSH
import xxhash
from tqdm import tqdm

def shingles_char(s: str, n: int = 24):
    # NeMo Curator도 char_ngrams를 기본 24로 제시 (권장 >=20). ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/curate-text/process-data/deduplication/fuzzy?utm_source=openai))
    s = s.lower()
    if len(s) <= n:
        yield s
        return
    for i in range(0, len(s) - n + 1):
        yield s[i:i+n]

def build_minhash(s: str, num_perm: int = 128, ngram: int = 24) -> MinHash:
    m = MinHash(num_perm=num_perm)
    # 해시 안정성과 속도를 위해 xxhash 사용
    for sh in shingles_char(s, n=ngram):
        m.update(xxhash.xxh64(sh).digest())
    return m

# LSH threshold: "거의 복붙" 제거면 0.85~0.95에서 시작해 샘플링으로 튜닝
THRESH = 0.90
NUM_PERM = 128
NGRAM = 24

lsh = MinHashLSH(threshold=THRESH, num_perm=NUM_PERM)
minhashes = {}

for row in tqdm(df.select(["doc_id", "text_norm"]).iter_rows(named=True), total=df.height):
    doc_id = row["doc_id"]
    mh = build_minhash(row["text_norm"], num_perm=NUM_PERM, ngram=NGRAM)
    minhashes[doc_id] = mh
    lsh.insert(doc_id, mh)

# Union-Find로 connected components(중복군) 만들기
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x

def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra

# 후보 매칭
doc_ids = df["doc_id"].to_list()
for doc_id in tqdm(doc_ids):
    mh = minhashes[doc_id]
    # 같은 군 내 후보들
    candidates = lsh.query(mh)
    for other in candidates:
        if other != doc_id:
            union(doc_id, other)

# cluster_id 부여
cluster_id = {doc_id: find(doc_id) for doc_id in doc_ids}
clusters = pl.DataFrame({"doc_id": doc_ids, "cluster_id": [cluster_id[d] for d in doc_ids]})

dedup_ready = df.join(clusters, on="doc_id", how="inner")
print(dedup_ready.select(pl.n_unique("cluster_id")).item(), "clusters")
```

### 3) “클러스터에서 무엇을 남길지”: quality 기반 대표 선택
- 여기서 많은 팀이 실수합니다: **중복 제거는 ‘삭제’가 아니라 ‘선택(selection)’ 문제**입니다.  
- 같은 중복군에서 `qscore`가 가장 좋은 문서를 남깁니다(필요하면 url 도메인, 최신 ts, 언어 등 추가).

```python
# cluster_id 별로 최고 qscore 1개만 선택
curated = (
    dedup_ready
    .sort(["cluster_id", "qscore"], descending=[False, True])
    .group_by("cluster_id")
    .head(1)
    .drop("cluster_id")
)

print("final docs:", curated.height)
curated.write_parquet("data/curated/train.parquet")
```

예상 출력/효과(경험칙):
- 웹/문서 혼합 데이터는 **near-dup 제거만으로도 10~40% 이상 감소**가 흔하고,
- “학습 토큰” 기준 비용 절감이 직접적으로 나옵니다(단, 과도하면 커버리지 손실).

#### 확장: GPU/분산으로 올리려면
- 규모가 커지면 NeMo Curator의 hash-based dedup(Exact/Fuzzy) 모듈로 옮기는 게 현실적입니다. Fuzzy dedup는 MinHash+LSH 파이프라인과 파라미터(ngram, bands 등)를 문서화해 제공하고, false positive check도 옵션으로 둡니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/24.09/datacuration/gpudeduplication.html?utm_source=openai))  
- MinHashLSH의 메모리/디스크 병목 자체를 줄이는 방향으로는 LSHBloom 같은 접근이 “극단적 스케일”에서 의미가 있습니다. ([arxiv.org](https://arxiv.org/abs/2411.04257?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “Dedup ratio”를 목표로 두지 말고 “오염/성능 지표”로 피드백 루프 만들기
- 목표: “중복을 X% 제거”가 아니라  
  - (a) **eval contamination 감소**(train-eval 근접/중복 탐지)  
  - (b) **학습 FLOPs/토큰 대비 성능** 개선  
- DCLM(DataComp-LM)처럼 “큐레이션 전략(필터/디덥/믹싱)을 표준 레시피로 비교”하려는 시도도 등장했습니다. ([github.com](https://github.com/mlfoundations/dclm?utm_source=openai))  
  → 사내에서도 작은 샘플로 “전/후 성능”을 비교하는 실험 harness를 먼저 만드세요.

### Best Practice 2) Near-dup 클러스터에서는 “최고 품질 1개”만 남겨라(그리고 그 기준을 로그로 남겨라)
- RedPajama 관련 정리 글에서도 “quality filtering과 함께, near-dup 클러스터에서 무엇을 남길지”가 실무의 핵심이라고 강조합니다. ([mbrenndoerfer.com](https://mbrenndoerfer.com/writing/deduplication-exact-near-duplicate-jaccard-similarity-suffix-arrays?utm_source=openai))  
- 추천 로그:
  - cluster size 분포(거대 클러스터 상위 100개 샘플)
  - 제거된 문서의 qscore 분포
  - 남긴 문서의 도메인/언어 분포 변화

### Best Practice 3) 2-stage dedup이 비용-정확도 밸런스가 좋다
- (1) MinHash/LSH로 “거의 같은 복붙” 대량 제거  
- (2) 남은 데이터에서만 semantic dedup(임베딩) 적용  
- SemHash는 semantic dedup을 “대규모에서도 ANN으로 빠르게” 가져가려는 도구이고, 임계값 탐색(least similar duplicates로 threshold 찾기)을 지원합니다. ([github.com](https://github.com/MinishLab/semhash?utm_source=openai))

### 흔한 함정/안티패턴
- **함정 A: 정규화 없이 해시 dedup**  
  - 공백/유니코드/HTML 차이로 exact dup이 빠져나가고, 결국 fuzzy 단계가 과부하
- **함정 B: LSH threshold를 한 번에 고정**  
  - 데이터 도메인(뉴스/블로그/코드/정책)에 따라 “0.9”가 과하거나 약할 수 있음  
  - 샘플링으로 “오탐(서로 다른 문서 삭제)”을 반드시 확인
- **함정 C: false positive check 생략 + 공격적 threshold**  
  - NeMo 문서도 LSH bucketing은 근사이므로 필요 시 bucket 내부에서 Jaccard로 검증하라고 안내합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/24.09/datacuration/gpudeduplication.html?utm_source=openai))

### 비용/성능/안정성 트레이드오프(의사결정 포인트)
- **CPU 단일 머신**: 단순/저렴하지만 수천만+ 문서에서 벽(시간/메모리)
- **GPU/분산(NeMo Curator 등)**: 초기 셋업 비용이 있지만, MinHash/LSH가 병목인 구간에서 효과적 ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/latest/datacuration/gpudeduplication.html?utm_source=openai))
- **인덱스 구조 혁신(LSHBloom)**: “수십억 문서” 같은 극단 스케일에서 디스크/메모리 비용을 뒤집는 접근 ([arxiv.org](https://arxiv.org/abs/2411.04257?utm_source=openai))
- **Semantic dedup**: 품질은 좋아지지만 임베딩 비용 + 오탐 리스크(특히 도메인 지식 문서) 증가 ([github.com](https://github.com/MinishLab/semhash?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 4월 기준의 학습 데이터 큐레이션에서 “dedup + dataset quality”는 더 이상 옵션이 아니라 **학습 비용/성능/평가 신뢰도를 좌우하는 엔지니어링 영역**입니다. 추천 도입 기준은 다음 3가지입니다.

1) 데이터가 여러 소스/여러 덤프에서 오고, **반복/재배포**가 많다 → 최소 MinHash 기반 near-dup는 필수  
2) 평가셋이 웹/공개 코퍼스 기반이거나, 사내 테스트셋이 재사용된다 → **train–eval decontamination**까지 고려  
3) 규모가 커서 dedup이 병목이다 → NeMo Curator 같은 GPU/분산 파이프라인, 또는 LSHBloom/FED류 접근을 검토 ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/latest/datacuration/gpudeduplication.html?utm_source=openai))

다음 학습 추천(실무 관점):
- NeMo Curator의 fuzzy dedup 파라미터(ngram/bands/hashes)와 false positive check 흐름을 먼저 이해하고, ([docs.nvidia.com](https://docs.nvidia.com/nemo-framework/user-guide/24.09/datacuration/gpudeduplication.html?utm_source=openai))  
- 사내 데이터 1~5% 샘플로 “threshold sweep + 오탐 리뷰 + 성능 회귀테스트” 자동화를 만드세요.
- 마지막으로 semantic dedup(예: SemHash)은 “전체 적용”보다 “남은 데이터/평가 오염 제거”에 제한적으로 써서 비용 대비 효과를 최적화하는 쪽이 안전합니다. ([github.com](https://github.com/MinishLab/semhash?utm_source=openai))