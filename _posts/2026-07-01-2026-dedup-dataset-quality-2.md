---
title: "중복을 “지우는” 순간, 데이터 품질이 “결정”된다: 2026년식 Dedup + Dataset Quality 전처리 실전 설계"
date: 2026-07-01 04:44:08 +0900
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
LLM/검색·추천/분류 모델이든, 결국 성능은 **학습 데이터 분포**와 **오염(contamination)**에 끌려갑니다. 특히 2026년 현재는 크롤링·RAG·멀티모달 수집이 일상화되면서, 데이터 파이프라인에서 가장 흔한 실패가 이 3가지로 수렴합니다.

1) **중복(duplicate / near-duplicate)** 때문에 “학습이 쉬워져” 지표는 좋아 보이는데 일반화가 깨짐  
2) **데이터 누수(train-test leakage / benchmark contamination)**로 평가가 의미 없어짐  
3) **저품질 샘플**(짧은 텍스트, 광고/스팸, 깨진 인코딩, 비정상 분포)이 모델을 오염

흥미로운 포인트는, 대규모 데이터에서 dedup은 단순 정제 작업이 아니라 **학습 효율·일반화·평가 신뢰성**을 동시에 건드리는 “모델링 레버”라는 점입니다. Hugging Face가 BigCode/The Stack dedup 사례에서 문서 클러스터링(Union-Find) 기반 근사 dedup을 소개하며, 중복을 공격적으로 제거할수록 다운스트림 성능이 좋아지는 경우가 있음을 보여준 것도 같은 맥락입니다. ([huggingface.co](https://huggingface.co/blog/dedup?utm_source=openai))

### 언제 쓰면 좋은가
- 웹/문서/로그 기반 대규모 코퍼스(중복률이 구조적으로 높음)
- RAG 인덱싱 전(중복 chunk는 검색 품질과 비용을 동시에 망침)
- 파인튜닝(SFT/RLHF) 데이터(같은 답변 패턴이 반복되면 편향·과적합 유발)
- 평가셋을 “신뢰 가능한 기준”으로 만들고 싶을 때(오염 제거)

### 언제는 조심해야 하는가(혹은 안 하는 게 나은가)
- “반복 자체가 신호”인 도메인(예: 동일 문구가 규정/정책으로 의미가 있는 경우)
- 데이터량이 매우 작고, 중복 제거로 **커버리지**가 급격히 줄어드는 경우
- dedup 기준이 불명확한데 임계값만 올려서 “좋은 데이터까지 삭제”하는 경우  
  (특히 semantic dedup은 false positive 비용이 큼)

---

## 🔧 핵심 개념
### 1) Dedup의 3계층: exact → near → semantic
현업에서는 보통 아래 순서로 갑니다(비용이 싼 것부터 비싼 것).

1. **Exact dedup (hash-based)**  
   - 정규화(normalization) 후 `sha1/xxhash` 같은 해시로 동일 레코드 제거  
   - 장점: 빠름, 결정적(deterministic), 재현성 좋음  
   - 단점: 공백/문장부호/순서 바뀌면 못 잡음

2. **Near-duplicate (MinHash/LSH, shingling)**  
   - 문서를 n-gram(shingles) 집합으로 바꾸고 **Jaccard 유사도**를 근사  
   - MinHash + LSH는 웹 스케일에서 “근접 중복”을 싸게 잡는 표준 루트로 널리 쓰임 ([huggingface.co](https://huggingface.co/blog/dedup?utm_source=openai))  
   - 단점: 패러프레이즈(의미는 같은데 단어가 바뀐 경우)에는 약함

3. **Semantic dedup (embedding + ANN/FAISS)**  
   - 문장/문서 embedding을 만들고 cosine 유사도 기반으로 중복 후보 제거  
   - SemDeDup 류 연구는 “의미 중복” 제거로 데이터 효율을 끌어올리는 방향을 제시 ([arxiv.org](https://arxiv.org/abs/2303.09540?utm_source=openai))  
   - 최근에는 실전 도구로 **SemHash** 같은 빠른 semantic dedup 툴이 주목받는 흐름 ([github.com](https://github.com/MinishLab/semhash?utm_source=openai))  
   - 단점: 비용(embedding), 임계값 민감, 도메인에 따라 오탐/과탐 리스크

핵심 차이점은 간단합니다.  
- **MinHash는 ‘표면 형태’**의 근접 중복을 싸게 제거  
- **Embedding은 ‘의미’**의 중복을 더 넓게 제거(대신 비싸고 위험)

### 2) “Dedup = delete”가 아니라 “cluster → policy”다
대규모에서는 “어떤 하나를 남기고 지운다”보다 **중복 클러스터를 만든 다음**, 정책으로 처리하는 게 안전합니다. BigCode/The Stack dedup에서도 문서 군집을 만들기 위해 Union-Find를 언급합니다. ([huggingface.co](https://huggingface.co/blog/dedup?utm_source=openai))

예시 정책:
- 클러스터당 1개만 남기기(aggressive)
- 길이/품질 점수 최댓값만 남기기(quality-aware)
- 소스 신뢰도(도메인/라이선스/작성자) 우선
- 시간 최신본 우선(문서 버전이 중요한 경우)

### 3) Dataset quality는 “규칙 기반 + 분포 기반 + 모델 기반” 혼합이 현실적
2026년 데이터 품질 도구들은 rule-based validation(예: Great Expectations), observability/anomaly detection(예: Monte Carlo류), catalog/governance(예: OpenMetadata)로 역할이 갈립니다. ([basedash.com](https://www.basedash.com/blog/best-data-quality-tools-compared-2026?utm_source=openai))  
다만 “학습 데이터” 관점에서는 아래 3축을 같이 봐야 합니다.

- **규칙 기반**: 스키마, null 비율, 길이, 금칙어, 언어 감지, PII  
- **분포 기반**: 토큰 길이 분포, 언어/도메인 비중, 라벨 불균형, 시계열 drift  
- **모델 기반**: perplexity/품질 스코어, toxicity, instruction-following 적합도, “eval에 가까운 샘플” 탐지(오염 방지)

OpenAI도 파인튜닝 품질을 올리기 위해 데이터의 균형/다양성, 예제 자체의 결함 점검을 강조합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))

---

## 💻 실전 코드
아래는 “크롤링된 한국어/영어 혼합 텍스트 + 메타데이터(JSONL)”를 가정하고, **대용량에서도 돌아가게** 설계한 3단계 파이프라인입니다.

- Step 0: 환경 구성
- Step 1: Exact dedup + 간단 품질 필터(스트리밍)
- Step 2: Near-duplicate(MinHash LSH)로 후보 클러스터링
- Step 3: (옵션) Semantic dedup으로 마지막 정리 + 품질 점수 기반 대표 선택
- 마지막: Great Expectations로 “전처리 결과”에 대한 회귀 테스트(데이터가 다시 더러워지는 걸 방지)

### Step 0) 의존성/입력 포맷
```bash
python -m venv .venv
source .venv/bin/activate

pip install polars pyarrow datasketch xxhash tqdm \
            sentence-transformers faiss-cpu \
            great-expectations
```

입력 `raw.jsonl` 예시(현실적으로 자주 보는 형태):
```json
{"id":"a1","source":"crawl_siteA","url":"...","text":"..."}
{"id":"a2","source":"crawl_siteB","url":"...","text":"..."}
...
```

### Step 1) Exact dedup + 품질 필터(스트리밍)
- 정규화 후 `xxhash`로 fingerprint 생성
- 너무 짧거나(예: <200 chars), 깨진 텍스트, “링크 모음/광고” 패턴 제거
- 여기서 **데이터를 많이 죽여도** 괜찮습니다. 뒤 단계 비용을 줄이는 게 목적입니다.

```python
# step1_exact_and_quality.py
import json, re, sys
import xxhash
from tqdm import tqdm

WS_RE = re.compile(r"\s+")
BAD_PATTERNS = [
    re.compile(r"cookie|privacy policy|all rights reserved", re.I),
    re.compile(r"http[s]?://"),
]

def normalize(text: str) -> str:
    text = text.strip()
    text = WS_RE.sub(" ", text)
    return text

def quality_ok(text: str) -> bool:
    if len(text) < 200:
        return False
    # 링크만 잔뜩 있는 페이지 방지(간단 휴리스틱)
    if text.count("http") > 3:
        return False
    for p in BAD_PATTERNS:
        if p.search(text):
            return False
    return True

def fp(text: str) -> int:
    # seed 고정으로 재현성 확보
    return xxhash.xxh3_64_intdigest(text)

def main(inp, outp):
    seen = set()
    kept = 0
    dropped_dup = 0
    dropped_q = 0

    with open(inp, "r", encoding="utf-8") as fin, open(outp, "w", encoding="utf-8") as fout:
        for line in tqdm(fin, desc="step1"):
            obj = json.loads(line)
            text = normalize(obj.get("text", ""))
            if not quality_ok(text):
                dropped_q += 1
                continue
            h = fp(text)
            if h in seen:
                dropped_dup += 1
                continue
            seen.add(h)
            obj["text"] = text
            obj["fp64"] = h
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            kept += 1

    print({"kept": kept, "dropped_dup": dropped_dup, "dropped_q": dropped_q})

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

예상 출력(예):
```bash
python step1_exact_and_quality.py raw.jsonl step1.jsonl
# {'kept': 812345, 'dropped_dup': 132210, 'dropped_q': 945001}
```

### Step 2) MinHash LSH로 near-duplicate 클러스터링(문서 단위)
여기서는 “완전 동일”이 아니라 **부분 편집/템플릿 반복**을 잡습니다. MinHash는 대규모에서 여전히 비용 대비 효과가 좋아서 표준처럼 쓰입니다. ([arxiv.org](https://arxiv.org/abs/2501.01046?utm_source=openai))

```python
# step2_minhash_cluster.py
import json, sys
from datasketch import MinHash, MinHashLSH
from collections import defaultdict

def shingles(text: str, n=5):
    # 단어 단위 shingle (한국어는 형태소까지 가면 좋지만 비용↑. 일단 whitespace 토큰.)
    toks = text.split()
    for i in range(max(0, len(toks) - n + 1)):
        yield " ".join(toks[i:i+n]).encode("utf-8")

def mh(text: str, num_perm=128):
    m = MinHash(num_perm=num_perm)
    for s in shingles(text):
        m.update(s)
    return m

def main(inp, out_clusters, jaccard_threshold=0.85):
    lsh = MinHashLSH(threshold=jaccard_threshold, num_perm=128)
    docs = {}          # id -> text
    minhashes = {}     # id -> MinHash

    with open(inp, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            did = obj["id"]
            text = obj["text"]
            docs[did] = text
            m = mh(text)
            minhashes[did] = m
            lsh.insert(did, m)

    # 후보군 조회 후 간단 클러스터링(대규모면 union-find/분산 처리 권장)
    cluster_of = {}
    clusters = []
    for did, m in minhashes.items():
        if did in cluster_of:
            continue
        cand = lsh.query(m)
        cluster = sorted(set(cand))
        for x in cluster:
            cluster_of[x] = len(clusters)
        clusters.append(cluster)

    with open(out_clusters, "w", encoding="utf-8") as fout:
        for idx, c in enumerate(clusters):
            fout.write(json.dumps({"cluster_id": idx, "doc_ids": c}, ensure_ascii=False) + "\n")

    print({"clusters": len(clusters), "docs": len(docs)})

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

### Step 3) (옵션) Semantic dedup + “대표 샘플 선택” 정책
MinHash로 “표면 중복”을 쳐낸 뒤, 남은 문서에서 **의미 중복**까지 줄이고 싶을 때 embedding 기반으로 한 번 더 갑니다. SemDeDup 계열 접근이 이 방향성을 뒷받침합니다. ([arxiv.org](https://arxiv.org/abs/2303.09540?utm_source=openai))  
실전에서는 SemHash 같은 구현을 참고하거나, 직접 FAISS 파이프라인을 꾸립니다. ([github.com](https://github.com/MinishLab/semhash?utm_source=openai))

아래 코드는 “클러스터 내 대표 1개만 남기기”를 **품질 점수(길이/문장 다양성 간단 지표)**로 선택합니다.

```python
# step3_semantic_dedup_and_select.py
import json, sys, math
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

def quality_score(text: str) -> float:
    # 너무 복잡하게 가지 말고, "대표 선택"에 필요한 정도만.
    # 길이(log) + 문장 수 + 중복 토큰 비율 패널티 같은 식으로 확장 가능.
    length = len(text)
    sents = text.count(".") + text.count("다.") + text.count("?") + text.count("!")
    return math.log(1 + length) + 0.2 * math.log(1 + sents)

def main(step1_jsonl, out_jsonl, sim_threshold=0.92, batch=256):
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    docs = []
    with open(step1_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            docs.append(obj)

    texts = [d["text"] for d in docs]
    embs = []
    for i in range(0, len(texts), batch):
        e = model.encode(texts[i:i+batch], normalize_embeddings=True)
        embs.append(e.astype("float32"))
    X = np.vstack(embs)

    # cosine similarity == inner product (normalize_embeddings=True)
    dim = X.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(X)

    kept = []
    removed = set()

    # greedy: 품질 높은 순으로 남기고, 유사한 것 제거
    order = sorted(range(len(docs)), key=lambda i: quality_score(docs[i]["text"]), reverse=True)

    for i in order:
        if i in removed:
            continue
        kept.append(i)
        # topK는 데이터 규모에 맞게 조절(너무 크면 느림)
        D, I = index.search(X[i:i+1], 50)
        for sim, j in zip(D[0], I[0]):
            if j == -1 or j == i:
                continue
            if sim >= sim_threshold:
                removed.add(j)

    with open(out_jsonl, "w", encoding="utf-8") as fout:
        for i in kept:
            fout.write(json.dumps(docs[i], ensure_ascii=False) + "\n")

    print({"input": len(docs), "kept": len(kept), "removed": len(removed)})

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

### 마지막) Great Expectations로 “전처리 회귀 테스트” 걸기
전처리를 한 번 잘해도, 크롤러/파트너 피드/포맷 변경으로 다음 달에 다시 더러워집니다. 그래서 **품질 기준을 테스트로 고정**하는 게 중요합니다(도구로는 Great Expectations 같은 “파이프라인 내 검증”이 여전히 실용적입니다). ([forage.ai](https://forage.ai/blog/best-data-observability-tools-for-external-data-pipelines/?utm_source=openai))

(지면상 전체 프로젝트 구성은 생략하고, 핵심 체크만 예시로 듭니다.)
- `text` null 금지
- 길이 p50/p95 범위(급격한 분포 붕괴 탐지)
- source별 비중 상한(한 사이트가 갑자기 80% 되면 경고)

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “두 번 dedup”이 안전하다: cheap pass → expensive pass
- 1차: exact + MinHash로 비용을 최소화하며 중복률을 크게 낮춤  
- 2차: embedding은 “정말 필요한 구간”에만(예: 클러스터 내, 특정 소스만)  
이 구조가 SemHash 같은 빠른 semantic dedup 도구가 사랑받는 이유이기도 합니다. ([github.com](https://github.com/MinishLab/semhash?utm_source=openai))

### Best Practice 2) 삭제가 아니라 “클러스터”를 저장해라
나중에 꼭 이런 질문이 옵니다.
- “이 샘플 왜 빠졌죠?”
- “임계값 0.92가 맞아요?”
- “특정 고객 데이터는 보존해야 해요”
클러스터와 대표 선택 근거(점수/룰/버전)를 저장하면, **재현성과 거버넌스**가 생깁니다. BigCode가 클러스터링 관점(Union-Find)을 강조한 것도 같은 이유입니다. ([huggingface.co](https://huggingface.co/blog/dedup?utm_source=openai))

### Best Practice 3) 품질은 ‘룰’보다 ‘분포’를 먼저 잡아라
룰은 쉽게 속습니다(예: 스팸도 길이는 길 수 있음).  
최소한 아래는 매 배치마다 리포팅하세요.
- 토큰/문자 길이 분포(p50/p95)
- 언어/도메인 비중
- 중복률(Exact, MinHash, Semantic 각 단계에서 얼마나 줄었는지)

### 흔한 함정/안티패턴
- **semantic threshold를 올리면 품질이 좋아질 거라는 착각**  
  → 오탐 비용이 커서 “다양성”이 죽고, 모델이 특정 표현만 학습할 수 있음
- **dedup을 eval/benchmark와 분리하지 않음**  
  → train에서 benchmark 문장이 남아 있으면 평가가 무의미(오염)
- **전처리 파이프라인 버전 관리 부재**  
  → 같은 데이터셋 이름인데 결과가 달라져 재현 불가(모델 비교 불가)

### 비용/성능/안정성 트레이드오프(현실적인 판단 기준)
- MinHash/LSH: CPU로도 큰 볼륨 처리 가능, 안정적. 다만 의미 중복은 못 잡음. ([arxiv.org](https://arxiv.org/abs/2501.01046?utm_source=openai))  
- Embedding dedup: 품질 레버가 크지만, 비용/임계값/도메인 편향 리스크가 큼. SemDeDup류가 제안하는 이득이 “항상” 나오진 않음. ([arxiv.org](https://arxiv.org/abs/2303.09540?utm_source=openai))  
- 도구 선택: “학습 데이터 품질”은 전통적 DQ(테이블) 도구만으로 부족하고, 검증/관측/거버넌스가 섞인 스택이 필요(2026년 도구들이 통합 플랫폼으로 가는 이유). ([forrester.com](https://www.forrester.com/blogs/the-forrester-wave-data-quality-solutions-q1-2026/?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 7월 기준 “데이터 큐레이션에서 dedup과 quality는 별개가 아니라 하나의 설계 문제”입니다.

- **가장 실전적인 기본형**:  
  `Exact (hash) → Near (MinHash/LSH) → (필요 시) Semantic (embedding+FAISS) → Quality regression tests(Great Expectations 등)`
- **도입 판단 기준**:
  - 중복률이 높다/소스가 많다/템플릿 문서가 많다 → MinHash까지는 거의 필수
  - 패러프레이즈가 많고, 데이터 효율이 병목이다 → semantic dedup을 “부분 적용”으로 시작
  - 다음 달에도 같은 품질을 유지해야 한다 → 품질 체크를 테스트로 고정(관측 포함)

다음 학습 추천:
- MinHash/LSH 기반 대규모 dedup 운영 패턴(클러스터링/Union-Find) ([huggingface.co](https://huggingface.co/blog/dedup?utm_source=openai))  
- Semantic dedup의 이론과 이득/리스크(SemDeDup 계열) ([arxiv.org](https://arxiv.org/abs/2303.09540?utm_source=openai))  
- 파인튜닝/평가 관점에서 “데이터 품질을 어떻게 반복 개선할지”(OpenAI best practices) ([platform.openai.com](https://platform.openai.com/docs/guides/fine-tuning-best-practices?utm_source=openai))