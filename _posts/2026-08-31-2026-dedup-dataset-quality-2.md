---
title: "중복이 성능을 훔친다: 2026년식 학습 데이터 큐레이션 Dedup + Dataset Quality 전처리 실전 설계"
date: 2026-08-31 05:08:46 +0900
categories: [AI, Data]
tags: [ai, data, trend, 2026-08]
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

2026년 8월 기준으로 “학습 데이터 큐레이션”에서 가장 흔하게 성능을 갉아먹는 요인은 모델/하이퍼파라미터가 아니라 **데이터 중복(duplicate/near-duplicate)과 품질 편차**입니다. 중복이 많으면 (1) 학습 신호가 과대표집되어 과적합·편향이 커지고, (2) 토큰/스토리지 비용이 그대로 낭비되며, (3) 평가 데이터 contamination 리스크가 올라가 성능이 “좋아 보이기만” 하는 문제가 생깁니다. 최근 contamination을 **정량화**하려는 프레임워크(DCR 등)와 “contamination-resistant benchmark” 논의가 커진 것도 같은 맥락입니다. ([arxiv.org](https://arxiv.org/abs/2507.11405?utm_source=openai))

**언제 쓰면 좋나**
- 웹 크롤/문서 수집/로그 기반으로 **대규모 텍스트 코퍼스**를 만들고 pretraining / continued pretraining / instruction tuning을 하려는 경우
- RAG 지식베이스에서 chunk 레벨 중복 때문에 검색 품질이 흔들리는 경우(“조용한 성능 킬러”) ([reddit.com](https://www.reddit.com/r/Rag/comments/1px0hpp/open_source_i_built_a_localfirst_semantic/?utm_source=openai))
- 데이터 소스가 여러 개라서 동일 문서/미러/리포스트가 섞일 가능성이 큰 경우

**언제 쓰면 안 되나 (또는 보수적으로)**
- 데이터가 작고(예: 수십만 문서 이하) 사람이 직접 검수 가능한 경우: 과한 fuzzy dedup는 **false positive**로 다양성을 잃을 수 있음
- “중복 자체가 신호”인 도메인(예: 특정 템플릿 이메일/정형 로그를 그대로 배우게 하려는 경우)
- semantic dedup를 무턱대고 먼저 적용하는 경우: 임베딩 모델/threshold가 바뀌면 재현성이 무너지고, 운영비가 급증합니다(아래 함정 참고)

---

## 🔧 핵심 개념

### 1) Dedup의 레이어: exact → near → semantic
실무에서 dedup는 보통 3단으로 나눕니다.

1. **Exact dedup**: 완전히 동일한 텍스트(정규화 후)가 반복되는지 체크  
   - `xxhash/sha1` 같은 fingerprint로 O(N)  
   - 단점: 약간만 바뀌면(공백/헤더/날짜) 못 잡음

2. **Near-duplicate (surface-level) dedup**: “거의 같은 문서” 탐지  
   - 대표: **MinHash + LSH**, **SimHash + Hamming distance**  
   - 텍스트를 token shingle로 만들고(예: 5-gram), 이를 스케치로 압축해 유사도를 근사합니다. SimHash는 유사한 문서가 **Hamming distance가 작게** 나오도록 설계됩니다. ([github.com](https://github.com/seomoz/simhash-py?utm_source=openai))  
   - MinHash/LSH는 “후보군 blocking → 후보끼리만 정밀 비교” 구조라서 대규모에 유리합니다. DataTrove 같은 큐레이션 라이브러리도 “blocks for deduplication” 식으로 이 패턴을 제공합니다. ([github.com](https://github.com/huggingface/datatrove/blob/main/README.md?utm_source=openai))  
   - 흥미로운 포인트: 최신 계열 연구에서도 **robust near-duplicate**에서는 여전히 MinHash가 강력하다는 주장들이 반복됩니다(embedding이 항상 우월하지 않음). ([openreview.net](https://openreview.net/pdf?id=23b9KSNQTX&utm_source=openai))

3. **Semantic dedup**: 패러프레이즈/의미 중복까지 제거  
   - embedding → ANN/FAISS → threshold  
   - 장점: “말만 바꾼 중복” 제거  
   - 단점: 비용(embedding), 재현성(모델/버전 변화), false positive 리스크가 큼  
   - 그래서 실무는 **(exact/near)로 먼저 크게 줄이고, 남은 것에 semantic을 제한적으로** 적용하는 쪽이 안정적입니다(비용-효율).

### 2) Dataset quality는 “점수”가 아니라 “게이트 + 관측지표”
품질 평가는 단일 지표로 끝내기 어렵습니다. 대신 운영 가능한 형태는 보통:
- **하드 필터(게이트)**: 길이/문자 비율/중복도/언어/금칙어/boilerplate 비율 등
- **소프트 스코어(관측지표)**: 샘플링 기반 휴먼 검수, 도메인 분포, perplexity 기반 이상치(과도하게 쉬운/어려운 문서), contamination risk 체크 등

특히 2024~2026년 흐름에서 “evaluation contamination”은 데이터 품질의 일부로 같이 묶어서 봅니다. contamination이 있으면 모델이 “일반화”가 아니라 “기억”으로 점수를 올릴 수 있고, 이를 정량화하려는 DCR/ConTAM 같은 접근이 등장했습니다. ([arxiv.org](https://arxiv.org/abs/2507.11405?utm_source=openai))

### 3) 내부 작동 흐름(추천 아키텍처)
**대규모 텍스트 큐레이션에서 가장 안전한 흐름**은 아래입니다.

1) Ingest (Parquet/JSONL)  
2) Normalize(정규화: unicode/whitespace/boilerplate 최소 제거)  
3) Exact dedup (fingerprint)  
4) Near-dup 후보군 생성(MinHash/SimHash) → 후보끼리만 검증  
5) Quality gate (규칙 기반 + lightweight score)  
6) (선택) Semantic dedup / contamination scan  
7) Export (Parquet/WebDataset 등)

분산 처리 프레임워크로는 Ray Data처럼 block 단위 병렬/스트리밍 파이프라인이 실전에서 다루기 편합니다(Parquet read/write, map_batches, streaming execution). ([docs.ray.io](https://docs.ray.io/en/latest/data/api/dataset.html?utm_source=openai))  
또는 “dedup + filter + executor”까지 패키징된 Data-Juicer/DataTrove 류를 쓰면 시행착오를 줄일 수 있습니다. ([docs.ray.io](https://docs.ray.io/en/master/ray-more-libs/data_juicer_distributed_data_processing.html?utm_source=openai))

---

## 💻 실전 코드

아래 예제는 “웹 크롤 문서 Parquet(수백 GB~TB) → exact+near dedup → 품질 게이트 → 결과 Parquet 저장”을 목표로 합니다. **toy가 아니라**, 실제로 현업에서 자주 쓰는 형태(Parquet + 분산 배치 + 중간 메타데이터 저장)로 구성합니다.

### 0) 의존성/실행 준비

```bash
# Python 3.10+ 권장
pip install "ray[data]" pyarrow pandas datatrove
# (선택) 빠른 로컬 실행을 위해:
# export RAY_DISABLE_DOCKER_CPU_WARNING=1
```

### 1) 초기 셋업: Parquet 로드 + 정규화 + exact dedup

```python
import re
import unicodedata
import ray
import ray.data as rd

def normalize_text(t: str) -> str:
    # (중요) 너무 과한 정규화는 의미를 망가뜨려 false positive를 키움
    t = unicodedata.normalize("NFKC", t or "")
    t = t.replace("\u00a0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t

def quality_gate(t: str) -> dict:
    # 현실적인 게이트 예시(프로젝트에 맞게 조정)
    # - 너무 짧거나 너무 긴 문서 제거
    # - 링크/보일러플레이트 과다 제거(간단 휴리스틱)
    n = len(t)
    url_cnt = len(re.findall(r"https?://", t))
    alpha_ratio = (sum(c.isalpha() for c in t) / max(n, 1))

    ok = True
    reasons = []
    if n < 300:
        ok = False; reasons.append("too_short")
    if n > 200_000:
        ok = False; reasons.append("too_long")
    if url_cnt > 50:
        ok = False; reasons.append("too_many_urls")
    if alpha_ratio < 0.3:
        ok = False; reasons.append("low_alpha_ratio")

    return {"quality_ok": ok, "quality_reasons": reasons, "len": n, "url_cnt": url_cnt, "alpha_ratio": alpha_ratio}

ray.init()

# 예: S3/HDFS/로컬 모두 가능. Ray Data는 Parquet 병렬 로드를 지원.
ds = rd.read_parquet("s3://my-bucket/raw_crawl/2026-08/*.parquet")  # 경로는 환경에 맞게

# 1) 정규화
ds = ds.map(lambda r: {**r, "text_norm": normalize_text(r["text"])})

# 2) exact fingerprint로 1차 dedup (텍스트 자체를 키로 distinct는 비싸니 fingerprint 권장)
import xxhash
def add_fp(r):
    fp = xxhash.xxh64(r["text_norm"]).hexdigest()
    return {**r, "fp64": fp}

ds = ds.map(add_fp)

# fingerprint 기준으로 대표 1개만 남김(가장 간단한 형태)
# 프로젝트에 따라 "가장 긴 텍스트 우선" 같은 정책을 넣는 게 더 좋음
ds_exact = ds.groupby("fp64").map_groups(lambda batch: batch.head(1))
```

예상 출력(개념):
- `ds` 대비 `ds_exact`는 exact 중복이 제거되어 row 수가 줄어듭니다.
- `quality_gate`는 아직 적용 전이므로 “중복 제거율”을 먼저 관측하기 좋습니다.

### 2) Near-duplicate: DataTrove의 dedup blocks 패턴을 “파이프라인에 끼워 넣는” 방식
DataTrove는 대규모 텍스트 처리/필터링/중복 제거를 목적으로 만들어졌고, dedup를 위한 “block” 구조를 제공합니다. ([github.com](https://github.com/huggingface/datatrove/blob/main/README.md?utm_source=openai))  
여기서는 **운영에서 중요한 포인트**만 잡겠습니다: “near-dup는 반드시 (a) 후보군 생성 (b) 비교 (c) 클러스터 대표 선택”의 3단계로 설계해야 합니다.

> 아래 코드는 DataTrove의 구성 요소를 활용해 **MinHash 기반 near-dup**를 붙이는 예시 스켈레톤입니다. (세부 파라미터는 데이터 언어/도메인/길이에 따라 튜닝이 필요)

```python
# NOTE: DataTrove는 대규모 처리를 위한 파이프라인 구성요소를 제공한다.
# 아래는 "Ray로 분산 실행 + MinHash 계열 near-dedup"을 연결하는 전형적 구조 예시.

from datatrove.pipeline.readers import ParquetReader
from datatrove.pipeline.writers import ParquetWriter
from datatrove.pipeline.executors import RayPipelineExecutor

# (개념) dedup 관련 블록/스텝을 구성
from datatrove.pipeline.dedup import (
    MinhashDedupSignature,   # 시그니처 생성
    MinhashDedupBuckets,     # LSH 버킷팅(후보군)
    MinhashDedupCluster,     # 후보 비교/클러스터
    DedupKeepBest            # 대표 선택 정책
)

logging_dir = "s3://my-bucket/curation_logs/2026-08"
input_path  = "s3://my-bucket/raw_crawl/2026-08/"
output_path = "s3://my-bucket/curated/2026-08/"

pipeline = [
    ParquetReader(input_path, text_key="text"),

    # 정규화/필터를 넣고 싶다면 여기 map/filter 스텝을 추가(프로젝트 커스텀)
    # DataTrove에도 각종 filter가 존재하지만, 핵심은 "너무 무거운 NLP는 피하라"는 점.

    # 1) MinHash signature 생성
    MinhashDedupSignature(
        text_key="text",
        output_signature_key="minhash_sig",
        ngram=5,              # char/token n-gram은 데이터에 맞게
        num_perm=128
    ),

    # 2) LSH buckets로 후보군 생성
    MinhashDedupBuckets(
        signature_key="minhash_sig",
        num_bands=32          # band 수가 커지면 recall↑, candidate↑(비용↑)
    ),

    # 3) 후보군 내에서 비교/클러스터
    MinhashDedupCluster(
        signature_key="minhash_sig",
        threshold=0.85        # near-dup 기준 (Jaccard 근사)
    ),

    # 4) 클러스터에서 대표 1개만 유지(정책 중요)
    DedupKeepBest(
        # 예: 길이가 긴 것, 메타데이터가 좋은 것, 최신 것 등
        strategy="keep_longest"
    ),

    ParquetWriter(output_path)
]

executor = RayPipelineExecutor(
    pipeline=pipeline,
    logging_dir=logging_dir
)
executor.run()
```

핵심 튜닝 포인트:
- `ngram`, `num_perm`, `num_bands`, `threshold`는 **recall/precision/비용**을 좌우합니다.
- “대표 선택 정책”이 품질을 좌우합니다. 예: 같은 기사 복제본이라면 `keep_longest`가 유리하지만, 크롤러가 붙인 boilerplate가 길이를 늘린 경우엔 오히려 역효과입니다. 이런 경우엔 “본문 비율이 높은 것”을 점수화해서 keep하는 편이 낫습니다.

### 3) 확장: Ray Data 스트리밍 파이프라인으로 “품질 게이트 + 출력 포맷”까지 고정
Ray Data는 연산자를 파이프라인처럼 연결해 스트리밍 실행이 가능하고, Parquet/WebDataset 저장까지 지원합니다. ([docs.ray.io](https://docs.ray.io/en/latest/data/api/dataset.html?utm_source=openai))

```python
# ds_exact에서 quality gate를 적용해 최종 curated set을 만들고 Parquet로 저장

def apply_quality(r):
    q = quality_gate(r["text_norm"])
    return {**r, **q}

ds_q = ds_exact.map(apply_quality).filter(lambda r: r["quality_ok"])

# 컬럼 pruning: 최종 학습에 필요한 컬럼만 남기기
ds_out = ds_q.select_columns(["doc_id", "source", "text_norm", "len", "alpha_ratio"])

ds_out.write_parquet("s3://my-bucket/curated_parquet/2026-08/")  # Ray Data write_parquet 지원 ([docs.ray.io](https://docs.ray.io/en/master/data/api/doc/ray.data.Dataset.write_parquet.html?utm_source=openai))
```

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) “Dedup의 단위”를 먼저 고정하라: document vs chunk vs line
- pretraining 코퍼스는 보통 **document-level + near-duplicate**가 1차 목표
- RAG는 chunk-level dedup가 실익이 큰데, 여기서 semantic dedup를 넣으면 “벡터DB에 중복 chunk가 쌓여 성능이 죽는” 현상을 줄일 수 있습니다. ([reddit.com](https://www.reddit.com/r/Rag/comments/1px0hpp/open_source_i_built_a_localfirst_semantic/?utm_source=openai))  
- 단, chunk-level은 false positive가 더 치명적입니다(하나의 문서 내부에서 반복되는 정의/코드 블록 등).

### Best Practice 2) MinHash/SimHash는 “후보군 생성기”로 쓰고, 마지막 판정은 정책으로
MinHash/SimHash는 확률적 스케치라서 “완벽한 판정기”가 아니라 **candidate generator**에 가깝습니다. ([github.com](https://github.com/seomoz/simhash-py?utm_source=openai))  
실전에서는:
- 후보군을 만들고
- 후보군에서 **추가 검증(예: 길이 비율, n-gram overlap 재계산, source 신뢰도)**를 한 번 더 하고
- 클러스터 대표 선택 정책을 명시합니다

이걸 안 하면 “중복 제거율”은 올라가는데 “데이터 다양성”이 무너집니다.

### Best Practice 3) contamination은 “평가셋 보호” 관점으로 분리 운영
최근 연구들이 보여주듯 contamination은 측정도 어렵고, 영향도 일관적이지 않습니다. (탐지 가정이 잘 안 맞으면 랜덤 수준 성능이라는 보고도 있음) ([aclanthology.org](https://aclanthology.org/2025.findings-naacl.291/?utm_source=openai))  
따라서 운영 팁:
- 학습 코퍼스 dedup과 별개로 **평가 데이터(benchmark) 보호 파이프라인**을 둡니다(DCR/ConTAM류 아이디어). ([arxiv.org](https://arxiv.org/abs/2507.11405?utm_source=openai))
- “모델 점수 올리기”보다 “점수 신뢰성 확보”가 목적임을 분리해야 합니다.

### 흔한 함정 1) semantic dedup를 먼저 돌린다
- 비용 폭발(embedding)
- 임베딩 모델/버전 변경 시 재현성 붕괴
- cosine threshold 하나로 케이스/버전/서식 차이를 중복 처리하는 등 오탐 증가(최근 RAG 운영 툴에서도 이 문제를 경고). ([reddit.com](https://www.reddit.com/r/Rag/comments/1w297tf/i_built_an_opensource_tool_that_finds_the/?utm_source=openai))  
권장: **exact/near로 먼저 줄이고, semantic은 “고가치 subset”에만**

### 흔한 함정 2) “보일러플레이트 제거”를 과격하게 해서 dedup을 망친다
정규화/boilerplate 제거는 dedup recall을 올리지만, 과하면 서로 다른 문서가 같은 fingerprint/스케치로 뭉개집니다.  
실무적으로는:
- 정규화는 최소(whitespace/unicode 정도)
- boilerplate 제거는 “검증된 extractor”를 쓰거나, 제거 여부를 feature로 남겨 모니터링

### 트레이드오프: 비용/성능/안정성
- MinHash(LSH) 기반: **CPU 중심, 비용 예측 가능**, 운영 안정적. 단, “의미 중복”에는 약함.
- Semantic dedup: **품질 잠재력은 크지만 비용/재현성 리스크**가 큼.
- 분산 실행(Ray/Data-Juicer 등): 처리량은 늘지만, **중간 산출물/로그/재시도 전략**이 없으면 장애 복구가 더 어려워집니다. DataTrove가 completion marker 같은 “완료 추적”을 강조하는 이유가 이 부분입니다. ([github.com](https://github.com/huggingface/datatrove/blob/main/README.md?utm_source=openai))  
또한 Data-Juicer는 Ray 기반 대규모 dedup(테스트 규모 TB 단위) 사례를 공유합니다. ([docs.ray.io](https://docs.ray.io/en/master/ray-more-libs/data_juicer_distributed_data_processing.html?utm_source=openai))

---

## 🚀 마무리

정리하면, 2026년 8월 시점의 “학습 데이터 큐레이션”은 **(1) exact → (2) MinHash/SimHash 기반 near-dup → (3) quality gate → (4) 필요 시 semantic/contamination 스캔** 순서로 설계하는 게 비용 대비 성공 확률이 높습니다. embedding 기반 semantic dedup는 강력하지만, 먼저 도입할수록 운영 리스크가 커지므로 “후반, 제한적”으로 두는 편이 좋습니다. 또한 benchmark contamination은 단순 중복 제거가 아니라 **평가 신뢰성 엔지니어링** 문제로 분리해 다루는 게 최근 흐름과 맞습니다. ([arxiv.org](https://arxiv.org/abs/2605.19999?utm_source=openai))

**도입 판단 기준(현업 체크리스트)**
- 내 코퍼스에서 exact 중복이 1% 이상인가? near-dup 후보가 많은 소스(미러/리포스트)가 있는가?
- 토큰 비용/학습 시간이 병목인가? 그렇다면 dedup ROI가 바로 나온다
- 평가 점수가 “갑자기” 좋아졌는가? 그렇다면 contamination risk 측정을 병행하라

**다음 학습 추천**
- MinHash/SimHash/LSH의 파라미터(ngram, num_perm, band, threshold)가 precision/recall/비용에 주는 영향
- DataTrove / Ray Data로 “재시도 가능한 파이프라인(로그/체크포인트/산출물 버전닝)” 만들기 ([github.com](https://github.com/huggingface/datatrove/blob/main/README.md?utm_source=openai))
- contamination 정량화 프레임워크(DCR/ConTAM류)를 평가 파이프라인에 붙이는 방법 ([arxiv.org](https://arxiv.org/abs/2507.11405?utm_source=openai))