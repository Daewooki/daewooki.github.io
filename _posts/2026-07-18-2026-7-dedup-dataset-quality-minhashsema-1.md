---
title: "2026년 7월 기준: Dedup + Dataset Quality 전처리 “현업형” 설계도 (MinHash→Semantic→Contamination Gate)"
date: 2026-07-18 03:13:54 +0900
categories: [AI, Data]
tags: [ai, data, trend, 2026-07]
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
LLM/멀티모달 학습 데이터에서 **중복(duplicate/near-duplicate/semantic duplicate)** 은 단순히 “데이터를 더 크게 보이게” 만드는 문제가 아니라, **(1) 학습 효율 저하**, **(2) 특정 패턴 과적합/기억(memorization) 강화**, **(3) 벤치마크 오염(contamination)로 성능 착시**를 유발합니다. Nature Communications의 분석에서도 **fuzzy duplicate(표면이 조금 다른 중복)** 가 모델 memorization에 크게 기여하고, 문서 단위 dedup만으로는 **시퀀스 레벨 중복이 남는다**는 점을 강조합니다. ([doi.org](https://doi.org/10.1038/s41467-026-68603-0?utm_source=openai))

언제 쓰면 좋은가:
- 웹/크롤링/로그/UGC 기반으로 **데이터 소스가 혼합**되고, repost/미러/템플릿 페이지가 많은 경우
- **대규모 토큰 예산**에서 “양”이 아니라 “유효 신호 밀도(signal density)”가 병목인 경우
- 평가 신뢰성이 중요한 경우(벤치마크/고객 데이터 포함 가능성)

언제 쓰면 안 되는가(또는 보수적으로):
- 데이터가 작고 도메인이 매우 좁아 **중복 자체가 ‘중요한 반복 학습’ 신호**일 수 있는 경우(예: 특정 포맷/약관/스펙 문서)
- 법/라이선스/추적(provenance) 요구가 강한데, aggressive dedup로 **근거 추적이 깨질** 수 있는 경우(이때는 “삭제” 대신 “그룹핑 + reweight” 고려)
- 이미 online reweighting 같은 방식으로 학습 중 **샘플 중요도를 동적으로 조절**할 계획이라면(전처리 hard filter는 다양성을 깎을 수 있음) ([arxiv.org](https://arxiv.org/abs/2605.05227?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Dedup의 3계층: Exact → Fuzzy(near) → Semantic
실무에서 가장 안전한 패턴은 “한 방에 semantic”이 아니라 **progressive(단계적) dedup** 입니다. ICLR 2026 계열 파이프라인에서도 **n-gram/MinHash LSH → semantic embedding 기반**으로 단계가 분리된 구성을 제시합니다. ([openreview.net](https://openreview.net/pdf?id=e2s7YHeVZW&utm_source=openai))

- **Exact dedup**: 완전 동일 텍스트 제거(해시 MD5/SHA 등). 비용이 매우 낮고, 부작용도 적음.
- **Fuzzy/near-duplicate**: 표면이 거의 같은 문서(광고 문구만 다름, 날짜만 다름, 일부 문단 reorder 등).
  - 대표: **MinHash + LSH**(Jaccard 근사), SimHash 등
  - 문서가 “부분적으로” 겹치는 경우도 잡아내지만, boilerplate(템플릿)가 많으면 오탐이 늘 수 있음.
- **Semantic duplicate**: 문장이 다르게 쓰였지만 의미가 같은 데이터(의역/요약/재서술).
  - 임베딩 기반 kNN/threshold로 유사 문서 제거
  - SemDeDup 같은 방식이 “표면 중복 제거 이후에도 남는 의미 중복”을 겨냥합니다. ([github.com](https://github.com/facebookresearch/SemDeDup/?utm_source=openai))
  - 2026년 7월 arXiv의 SemHash-LLM은 **distilled LLM embedding 공간에서 binary code(semantic hashing)** 와 **attention-weighted MinHash**로 boilerplate 영향을 줄이는 방향을 제안합니다. ([arxiv.org](https://arxiv.org/abs/2607.01601?utm_source=openai))  
  - 같은 달 H3D는 MinHash/SimHash 같은 전통 해싱부터 **BGE 임베딩 + quantization** 류까지 “문서 dedup 해싱”을 벤치마킹합니다. ([arxiv.org](https://arxiv.org/abs/2607.08382?utm_source=openai))

핵심 차이점(왜 3계층인가):
- MinHash는 빠르고 싸지만 **“의미”** 에 둔감합니다(의역에 취약).
- Semantic은 강력하지만 비용이 큽니다(embedding, 인덱스, threshold 튜닝).
- 그래서 **Exact로 물량을 먼저 줄이고 → MinHash로 ‘거의 같은 것’을 정리 → Semantic으로 ‘의미 중복’을 정리**하는 게 전체 비용/품질의 최적점이 되는 경우가 많습니다. ([openreview.net](https://openreview.net/pdf?id=e2s7YHeVZW&utm_source=openai))

### 2) Dataset Quality는 “점수 하나”가 아니라 “게이트들의 합”
최근 데이터 큐레이션은 dedup만이 아니라 **quality filtering + contamination gate + provenance**까지 묶어 “학습 입력으로 들어가기 전 관문”을 만듭니다. 실무 글/가이드에서도 MinHash/semantic dedup뿐 아니라 **벤치마크 격리, threshold 롤백**을 함께 다룹니다. ([oh-bug.com](https://oh-bug.com/posts/llm-pretraining-data-deduplication-production-guide/?utm_source=openai))  
RedPajama-v2는 대규모 풀에서 **Bloom filter 기반 exact dedup** 같은 강한 전처리를 하고, 품질 분류기/블랙리스트 등을 파이프라인에 포함합니다. ([together.ai](https://www.together.ai/blog/redpajama-v2-faq?utm_source=openai))  
NeMo Curator는 exact/fuzzy/semantic dedup을 **GPU 가속 워크플로우**로 제공하며, 결과를 “삭제”가 아니라 **dedup id 컬럼으로 남겨 원본 복원/추적 가능**하게 설계합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/v26.04/curate-text/process-data/deduplication?utm_source=openai))

즉, 실전에서의 목표는:
- “중복 제거율” 극대화가 아니라
- **(A) 유효 신호 밀도**, **(B) 다양성(diversity)**, **(C) 오염 리스크**, **(D) 추적 가능성**의 균형입니다.

---

## 💻 실전 코드
아래는 “웹 문서/크롤링 결과(parquet)”를 가정한 **현실적인 3단계 파이프라인** 예시입니다.

- 입력: `s3://.../raw/*.parquet` (컬럼: `doc_id`, `url`, `text`, `timestamp` 등)
- 출력:
  - `clean/*.parquet` (정제본)
  - `dupes/*.parquet` (중복 그룹 메타: keep/drop, score, reason)
  - `contamination_report.json` (벤치마크/금칙패턴 격리 결과)

### 0) 의존성/실행
```bash
pip install pandas pyarrow fastparquet datasketch xxhash sentence-transformers faiss-cpu regex tqdm
```

### 1단계: Exact + Boilerplate 정규화(“해시가 의미있어지게”)
```python
import re
import xxhash
import pandas as pd

BOILERPLATE_PATTERNS = [
    r"cookie(s)?\s+policy.*",          # 쿠키 배너류
    r"subscribe\s+to\s+our\s+newsletter.*",
    r"all\s+rights\s+reserved.*",
]

def normalize_text(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    # 템플릿/배너 제거(도메인에 맞게 강화 필요)
    for p in BOILERPLATE_PATTERNS:
        text = re.sub(p, " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def exact_fingerprint(text: str) -> str:
    # xxhash64: 빠른 exact dedup용
    return xxhash.xxh64(text).hexdigest()

df = pd.read_parquet("raw_shard.parquet")
df["norm_text"] = df["text"].map(normalize_text)
df["exact_fp"]  = df["norm_text"].map(exact_fingerprint)

# exact 중복: 같은 exact_fp 중 첫 번째만 keep
df = df.sort_values(["exact_fp", "timestamp"])
df["is_exact_dup"] = df.duplicated(subset=["exact_fp"], keep="first")

exact_kept = df[~df["is_exact_dup"]].copy()
exact_dupes = df[df["is_exact_dup"]][["doc_id","url","exact_fp"]]
print("exact kept:", len(exact_kept), " exact dup:", len(exact_dupes))
```

예상 출력(예):
- `exact kept: 8,420,113  exact dup: 1,901,774`

핵심은 “정규화 없이 해시”하면 광고/날짜/추적 파라미터로 인해 exact가 거의 안 잡힙니다. 반대로 과한 정규화는 서로 다른 문서를 같은 것으로 만들 수 있으니, **boilerplate 제거 규칙은 샘플링 검증**이 필수입니다.

### 2단계: MinHash LSH로 near-duplicate(비용 대비 효율 구간)
```python
from datasketch import MinHash, MinHashLSH
from tqdm import tqdm

def shingles(text: str, k=5):
    # 단어 단위 shingle(언어/도메인 따라 char shingle도 고려)
    toks = text.split()
    for i in range(0, max(0, len(toks)-k+1)):
        yield " ".join(toks[i:i+k])

def build_minhash(text: str, num_perm=128):
    m = MinHash(num_perm=num_perm)
    for s in set(shingles(text, k=5)):
        m.update(s.encode("utf-8"))
    return m

# LSH threshold는 “제거율”이 아니라 “오탐 허용” 기준으로 튜닝
lsh = MinHashLSH(threshold=0.85, num_perm=128)

minhashes = {}
for row in tqdm(exact_kept.itertuples(index=False), total=len(exact_kept)):
    mh = build_minhash(row.norm_text, num_perm=128)
    minhashes[row.doc_id] = mh
    lsh.insert(str(row.doc_id), mh)

# near-dup 그룹핑: 같은 버킷 후보들 중 대표 1개 keep
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
def union(a,b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra

doc_ids = list(minhashes.keys())
for doc_id in tqdm(doc_ids):
    cand = lsh.query(minhashes[doc_id])
    for other in cand:
        if other != str(doc_id):
            union(doc_id, int(other))

exact_kept["near_group"] = exact_kept["doc_id"].map(find)
# 그룹별 대표 선택(예: 가장 이른 timestamp 또는 가장 긴 본문 등)
exact_kept = exact_kept.sort_values(["near_group","timestamp"])
exact_kept["is_near_dup"] = exact_kept.duplicated(subset=["near_group"], keep="first")

near_kept = exact_kept[~exact_kept["is_near_dup"]].copy()
near_dupes = exact_kept[exact_kept["is_near_dup"]][["doc_id","url","near_group"]]
print("near kept:", len(near_kept), " near dup:", len(near_dupes))
```

튜닝 포인트:
- `threshold=0.85`는 꽤 공격적입니다. 템플릿이 많은 도메인은 오탐이 늘 수 있어 **0.9~0.95**로 시작하는 게 안전할 때가 많습니다.
- 문서 길이가 짧으면 MinHash 분산이 커져 “우연히 비슷”이 생깁니다. **길이 필터**(너무 짧은 문서 제외)와 함께 가야 합니다.

### 3단계: Semantic dedup(“비싼 대신 마지막 칼”)
MinHash 이후에도 “의역/재작성”은 남습니다. 여기서 embedding 기반으로 **semantic duplicate** 를 잡습니다. SemDeDup류 아이디어처럼 임베딩 유사도로 제거하되, 비용이 크므로 **MinHash로 줄인 후** 수행하는 게 보통 합리적입니다. ([github.com](https://github.com/facebookresearch/SemDeDup/?utm_source=openai))

```python
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")  # 예시(실무는 도메인 모델 권장)

# 길이/품질 기본 게이트(너무 짧거나 깨진 텍스트 제외)
near_kept["len"] = near_kept["norm_text"].str.len()
cand = near_kept[near_kept["len"] >= 400].copy()

texts = cand["norm_text"].tolist()
emb = model.encode(texts, batch_size=256, show_progress_bar=True, normalize_embeddings=True)
emb = np.asarray(emb, dtype="float32")

# cosine similarity == inner product (normalize_embeddings=True)
d = emb.shape[1]
index = faiss.IndexFlatIP(d)
index.add(emb)

# kNN로 근접 후보 찾고, threshold 이상이면 같은 semantic 그룹으로 묶기
k = 10
D, I = index.search(emb, k)

SEM_TH = 0.92  # 도메인/모델마다 calibration 필요(샘플링으로 결정)

parent2 = {}
def find2(x):
    parent2.setdefault(x, x)
    while parent2[x] != x:
        parent2[x] = parent2[parent2[x]]
        x = parent2[x]
    return x
def union2(a,b):
    ra, rb = find2(a), find2(b)
    if ra != rb:
        parent2[rb] = ra

ids = cand["doc_id"].tolist()
for i, doc_id in enumerate(ids):
    for j in range(1, k):  # j=0은 자기 자신
        sim = float(D[i, j])
        if sim >= SEM_TH:
            other_id = ids[int(I[i, j])]
            union2(doc_id, other_id)

cand["sem_group"] = cand["doc_id"].map(find2)
cand = cand.sort_values(["sem_group","timestamp"])
cand["is_sem_dup"] = cand.duplicated(subset=["sem_group"], keep="first")

sem_kept = cand[~cand["is_sem_dup"]].copy()
sem_dupes = cand[cand["is_sem_dup"]][["doc_id","url","sem_group"]]
print("semantic kept:", len(sem_kept), " semantic dup:", len(sem_dupes))
```

운영 관점 출력물(권장):
- `sem_dupes`에 **(drop_doc_id → keep_doc_id, sim_score, stage, reason)** 를 남겨 “왜 삭제됐는지” 감사(audit) 가능하게 만드세요.
- NeMo Curator처럼 dedup id 컬럼으로 원본과 연결되는 구조는, 나중에 threshold를 바꿔 재생성할 때 강력합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/v26.04/curate-text/process-data/deduplication?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Threshold는 ‘정답’이 아니라 ‘정책’이다**
- MinHash/semantic 모두 “몇 % 지웠다”가 목표가 아닙니다.  
  추천: (a) 도메인별 샘플 200~500건 뽑아 **오탐/미탐을 사람이 라벨링** → (b) 임계값을 “오탐률 제한”으로 결정 → (c) 토큰/성능 지표로 2차 검증.
- 특히 semantic threshold는 모델/도메인에 따라 크게 흔들립니다.

2) **Dedup은 품질과 충돌한다: ‘삭제’ 대신 ‘그룹+대표+reweight’도 고려**
- aggressive dedup은 다양성을 깎습니다. 최근 흐름에서 “offline hard filtering”의 일반화 한계를 지적하고, **online reweighting** 관점(학습 중 가중치 조절)을 제안하는 연구도 나옵니다. ([arxiv.org](https://arxiv.org/abs/2605.05227?utm_source=openai))  
- 현실적 타협: semantic group을 만들고 **대표 1개 + 나머지는 낮은 weight**(또는 curriculum)로 운영.

3) **Contamination gate를 dedup과 분리된 ‘별도 단계’로 둬라**
- 벤치마크/평가셋 문자열(또는 파생)을 “dedup 과정에서 우연히 살아남는” 일이 있습니다.  
- 실무 가이드들처럼 **benchmark isolation + threshold rollback**을 별도 프로세스로 두는 것이 안전합니다. ([oh-bug.com](https://oh-bug.com/posts/llm-pretraining-data-deduplication-production-guide/?utm_source=openai))

### 흔한 함정/안티패턴
- **문서 단위 dedup만 하고 끝내기**: 문서가 다르면 남지만, 내부에 동일 Q/A·코드 스니펫이 반복될 수 있습니다(시퀀스 레벨 중복). ([doi.org](https://doi.org/10.1038/s41467-026-68603-0?utm_source=openai))  
- **boilerplate가 강한 도메인에서 MinHash 오탐 폭발**: 템플릿이 유사도를 지배합니다. attention-weighted나 boilerplate 억제가 필요하다는 문제의식이 2026년 7월 SemHash-LLM 같은 방향으로 이어집니다. ([arxiv.org](https://arxiv.org/abs/2607.01601?utm_source=openai))  
- **semantic dedup을 처음부터 전량에 적용**: 비용/시간/인덱싱이 터집니다. 반드시 앞단에서 물량을 줄이세요.

### 비용/성능/안정성 트레이드오프
- MinHash는 **저비용·대용량 친화**지만, 의역에 약함.
- Semantic은 **고비용·고정밀(의미 중복 제거)** 가능하지만, threshold에 민감하고 “다양성 손실” 위험이 큼.
- GPU 워크플로우(예: NeMo Curator)는 처리량을 끌어올리지만, 운영 환경/메모리/파티셔닝 설계가 필요합니다. ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/v26.04/curate-text/process-data/deduplication?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 7월 시점의 “실전형 데이터 큐레이션”은 **Dedup을 단일 기법이 아니라 게이트들의 파이프라인**으로 봅니다:

- **Exact → MinHash LSH → Semantic(embedding)** 의 progressive dedup ([openreview.net](https://openreview.net/pdf?id=e2s7YHeVZW&utm_source=openai))  
- dedup의 목적은 “삭제율”이 아니라 **유효 신호 밀도/다양성/오염 리스크/추적성** 최적화 ([doi.org](https://doi.org/10.1038/s41467-026-68603-0?utm_source=openai))  
- 필요하면 hard filter 대신 **grouping + reweight** 같은 전략도 검토(일반화/다양성 관점) ([arxiv.org](https://arxiv.org/abs/2605.05227?utm_source=openai))

도입 판단 기준(현업 체크리스트):
- 데이터 소스가 2개 이상이고 repost/미러가 많다 → **MinHash까지는 거의 필수**
- 평가 신뢰성이 최우선이다 → **contamination gate + dedup audit log** 필수
- 비용이 빡빡하다 → **Exact/MinHash에서 최대한 줄이고 semantic은 “핵심 도메인”만**

다음 학습 추천:
- NeMo Curator의 dedup 워크플로우(실제 운영형 파이프라인 설계에 도움) ([docs.nvidia.com](https://docs.nvidia.com/nemo/curator/v26.04/curate-text/process-data/deduplication?utm_source=openai))  
- SemDeDup/semantic dedup 구현과 실험 철학 ([github.com](https://github.com/facebookresearch/SemDeDup/?utm_source=openai))  
- 2026년 7월 SemHash-LLM / H3D로 최신 semantic hashing·벤치마킹 트렌드 파악 ([arxiv.org](https://arxiv.org/abs/2607.01601?utm_source=openai))