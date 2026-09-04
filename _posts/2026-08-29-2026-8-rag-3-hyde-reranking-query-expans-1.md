---
title: "RAG 성능을 “진짜” 끌어올리는 3종 세트: HyDE + Reranking + Query Expansion 실전 설계"
description: "RAG가 프로덕션에서 흔들리는 지점은 대체로 한 가지입니다. “검색 단계에서 엉뚱한 근거를 가져오고, LLM은 그럴듯하게 완성한다”는 것."
date: 2026-08-29 06:48:07 +0900
categories: [AI, RAG]
tags: [ai, rag]
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
RAG가 프로덕션에서 흔들리는 지점은 대체로 한 가지입니다. **“검색 단계에서 엉뚱한 근거를 가져오고, LLM은 그럴듯하게 완성한다”**는 것. 이 문제는 모델의 답변 품질이 아니라 **Retrieval의 recall/precision 균형**과 **질의-문서 스타일 갭(vocabulary/style mismatch)**에서 시작합니다.

- **언제 쓰면 좋은가**
  - 사용자 질문이 짧고 모호하거나(예: “메모리 누수 해결”), 문서가 길고 기술적이며(로그/에러/가이드), 질문과 문서 표현이 잘 안 맞는 도메인
  - Top-k를 늘려도 정답 근거가 잘 안 잡히는 “검색 실패율”이 높은 RAG
  - “찾기만 하면 LLM은 잘 요약한다”는 확신이 있는데도, 컨텍스트가 엇나가서 답이 틀리는 경우

- **언제 쓰면 안 되는가**
  - 질의가 이미 문서의 키워드/용어와 잘 맞고(lexical match 강함), baseline retrieval이 안정적인 경우 (HyDE/QE는 비용만 늘릴 가능성)
  - latency 예산이 매우 빡빡하고(예: p95 < 500ms), 추가 LLM 호출/재랭킹 비용을 감당 못하는 경우
  - 보안/정책상 “질의를 외부 LLM로 변환/확장”하는 게 어려운 환경(내부 LLM/온프레미스가 없다면 리스크)

핵심은 이 3개를 “기술 이름”으로 도입하는 게 아니라, **실패 모드별로 선택적으로 켜는 것**입니다.

---

## 🔧 핵심 개념
### 1) HyDE (Hypothetical Document Embeddings)
HyDE는 한 줄로 요약하면 **“질문을 임베딩하지 말고, LLM이 만든 ‘가상의 정답 문서’를 임베딩해서 검색하자”**입니다. 원래 아이디어는 HyDE 논문(2022)에서 “질문↔문서 표현 갭”을 줄이기 위해 제안됐고, 실제로 다양한 RAG 스택에서 query-side 변환으로 쓰입니다.[^1]

**내부 흐름**
1. user query → LLM에 넣어서 *hypothetical answer/document* 생성
2. hypothetical text를 embedding → 벡터 검색
3. 결과 문서(실제 근거)로 최종 답변

**왜 효과가 나는가**
- 질문은 종종 “원하는 것”을 말하지만, 문서는 “설명/절차/용어”로 쓰입니다. HyDE는 LLM이 생성한 가상 문서를 통해 **문서 쪽 표현으로 질의를 ‘번역’**하는 효과가 있습니다.[^2]
- 단점은 명확합니다. **쿼리마다 LLM 생성이 추가**되므로 비용/지연이 늘고, 생성 품질이 나쁘면 오히려 retrieval이 틀어집니다(“잘못된 가상 답”에 끌려감).

> 2026년 8월 관점에서 흥미로운 포인트: HyDE가 “런타임 생성 비용”을 유발한다는 점을 정면으로 문제 삼고, 이를 우회하려는 연구도 나옵니다(예: HyPE가 HyDE류의 스타일 갭 문제를 다루면서 런타임 오버헤드를 줄이려는 방향을 제시).[^3]

### 2) Reranking (Cross-Encoder / Late Interaction)
RAG에서 retrieval은 보통 2단계가 됩니다.

- **Stage 1 (Recall 우선):** BM25 / dense bi-encoder / hybrid로 후보를 넓게 뽑음
- **Stage 2 (Precision 우선):** reranker로 후보 순서를 정교화

**Cross-Encoder reranking**
- query와 chunk를 **하나의 모델 입력으로 결합**해 “관련성 점수”를 직접 예측합니다.
- bi-encoder가 포기한 토큰 수준 상호작용을 되살려 정확도가 높지만, 후보 수만큼 모델을 돌려야 해서 느립니다. (monoBERT/monoT5 계열의 전통적 강점)[^4]

**Late interaction (ColBERT 계열)**
- 쿼리/문서를 token vector로 들고 있다가 MaxSim류로 빠르게 매칭합니다.
- cross-encoder보단 싸고, bi-encoder보단 정확한 “중간 단계”로, 2026년 실무 스택에서 **bi-encoder/hybrid → ColBERT → cross-encoder**로 계단식 프루닝하는 패턴이 자주 언급됩니다.[^5]

### 3) Query Expansion (Multi-query / Rewrite / Decompose)
Query Expansion(QE)은 “사용자 질의가 너무 짧거나 애매해서 못 찾는다”를 해결하는 고전적 방법이고, LLM 시대에는 **LLM이 expansion query를 생성**하는 방식이 널리 쓰입니다. 최근에는 QE를 체계적으로 정리한 서베이도 나왔고, RAG에서의 적용 포인트(1차 검색, multi-query fusion, rerank 결합 등)가 정리됩니다.[^6]

**HyDE vs QE 차이**
- QE: “질문을 여러 질문으로 확장” (여러 번 검색 후 fusion)
- HyDE: “질문을 문서 스타일 텍스트로 변환 후 1번(또는 소수) 검색”
- 둘 다 vocabulary mismatch를 줄이지만,
  - QE는 **검색 호출 수가 늘어나는 비용**
  - HyDE는 **LLM 생성 품질/편향 리스크**
  - 그리고 둘 다 **reranking과 결합할 때 효과가 극대화**됩니다(후보는 넓게, 최종은 정교하게).

---

## 💻 실전 코드
아래는 “문서가 길고 기술적인 내부 위키/Runbook”을 대상으로 하는 현실적 파이프라인 예시입니다.

- Vector DB: Qdrant (로컬/도커)
- Embedding: sentence-transformers 계열(로컬)
- HyDE: OpenAI(예시)로 hypothetical doc 생성
- Reranker: sentence-transformers CrossEncoder (로컬)
- Query Expansion: LLM이 3개 확장 질의 생성 → RRF 스타일로 합치고 rerank

> 실행 전제: 사내 문서가 이미 chunking + 메타데이터(서비스명/버전/날짜 등)로 인덱싱되어 있고, Qdrant 컬렉션에 upsert 되어 있다고 가정합니다. (toy 예제처럼 “문장 5개”로 끝내면 reranking/HyDE의 비용-효과 판단이 안 됩니다.)

### 1) 초기 셋업 (의존성 + Qdrant 준비)
```bash
# 1) Qdrant 실행
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest

# 2) 파이썬 의존성
pip install qdrant-client sentence-transformers openai numpy
```

### 2) HyDE + Multi-query Retrieval + Cross-Encoder Rerank
```python
import os
import numpy as np
from typing import List, Dict, Any, Tuple
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from sentence_transformers import SentenceTransformer
from sentence_transformers.cross_encoder import CrossEncoder

from openai import OpenAI

QDRANT_URL = "http://localhost:6333"
COLLECTION = "runbooks_chunks"

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # 예시
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"    # 예시 (reranker)[^7]

client = QdrantClient(url=QDRANT_URL)
embedder = SentenceTransformer(EMBED_MODEL)
reranker = CrossEncoder(RERANK_MODEL)

oai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def llm_hyde(query: str) -> str:
    """
    HyDE: 질문에 대한 '가상의 정답 문서'를 생성해서 임베딩에 사용.
    핵심: "답을 맞히려 하지 말고, 검색에 유리한 문서 스타일"로 쓰게 프롬프트 설계.
    """
    prompt = f"""
너는 SRE runbook 작성자다.
아래 질문에 대해, 실제 사실을 단정하지 말고 "검색에 유리한" 형태로
가능한 원인/증상/관련 로그 키워드/조치 절차를 포함한 기술 문서(500~800자)를 작성하라.

질문: {query}

형식:
- Symptoms:
- Likely causes:
- Key logs / metrics:
- Remediation steps:
- Related components / keywords:
"""
    resp = oai.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
        temperature=0.2,
    )
    return resp.output_text

def llm_expand_queries(query: str, n: int = 3) -> List[str]:
    """
    Query Expansion: 서로 다른 관점(원인/현상/컴포넌트)으로 확장 질의 생성.
    """
    prompt = f"""
아래 원 질문을 검색 효율이 높도록 {n}개의 확장 검색 질의로 바꿔라.
- 각 질의는 12~20단어 내, 키워드를 많이 포함
- 서로 다른 관점(증상/에러코드/컴포넌트/버전)을 반영
- 중복 최소화
원 질문: {query}
출력은 한 줄에 하나씩.
"""
    resp = oai.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
        temperature=0.3,
    )
    lines = [l.strip("- ").strip() for l in resp.output_text.splitlines() if l.strip()]
    return lines[:n]

def vector_search(text: str, top_k: int = 50, filter_: qm.Filter | None = None) -> List[Dict[str, Any]]:
    vec = embedder.encode([text], normalize_embeddings=True)[0].tolist()
    hits = client.search(
        collection_name=COLLECTION,
        query_vector=vec,
        limit=top_k,
        query_filter=filter_,
        with_payload=True,
    )
    results = []
    for h in hits:
        payload = h.payload or {}
        results.append({
            "id": h.id,
            "score": float(h.score),
            "text": payload.get("text", ""),
            "source": payload.get("source", ""),
            "meta": payload,
        })
    return results

def rrf_fuse(result_lists: List[List[Dict[str, Any]]], k: int = 60) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion 유사 구현: 여러 retrieval 결과를 안정적으로 합침.
    """
    scores = {}
    docs = {}
    for lst in result_lists:
        for rank, item in enumerate(lst):
            doc_id = item["id"]
            docs[doc_id] = item
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    fused = []
    for doc_id, s in scores.items():
        it = docs[doc_id]
        fused.append({**it, "rrf_score": s})
    fused.sort(key=lambda x: x["rrf_score"], reverse=True)
    return fused

def cross_encoder_rerank(query: str, candidates: List[Dict[str, Any]], top_n: int = 8) -> List[Dict[str, Any]]:
    pairs = [[query, c["text"]] for c in candidates]
    scores = reranker.predict(pairs, batch_size=32)
    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)
    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
    return candidates[:top_n]

def retrieve(query: str) -> List[Dict[str, Any]]:
    # (A) HyDE 문서 생성 → 검색
    hyde_doc = llm_hyde(query)
    hyde_hits = vector_search(hyde_doc, top_k=50)

    # (B) Query Expansion → 다중 검색
    expansions = llm_expand_queries(query, n=3)
    expanded_hits = [vector_search(q, top_k=30) for q in expansions]

    # (C) 원문 query도 같이 넣어(회귀 방지)
    base_hits = vector_search(query, top_k=30)

    # (D) fuse 후 rerank
    fused = rrf_fuse([base_hits, hyde_hits, *expanded_hits], k=60)[:80]
    final = cross_encoder_rerank(query, fused, top_n=8)
    return final

if __name__ == "__main__":
    q = "kubernetes에서 OOMKilled가 간헐적으로 발생하고, HPA 스케일링 이후 더 자주 터집니다. 원인과 점검 순서?"
    top = retrieve(q)

    print("=== Top contexts (reranked) ===")
    for i, t in enumerate(top, 1):
        print(f"\n[{i}] rerank={t['rerank_score']:.4f} source={t.get('source')}")
        print(t["text"][:500])
```

### 예상 출력(형태)
- rerank_score 기준으로 상위 8개 chunk가 나오고,
- source/메타(서비스명, 버전, 날짜)가 함께 보이면 “정말로 근거가 맞는지” 사람도 빠르게 검증 가능합니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (효과가 큰 순)
1) **Reranking을 “마지막 30~80개 후보”에만 걸어라**
- cross-encoder는 후보 수에 거의 비례해 느려집니다.
- 실무에서는 **1차로 top-200 정도 뽑고, 중간 단계(예: late interaction)로 50으로 줄인 뒤 cross-encoder로 10 내외**를 만드는 패턴이 널리 언급됩니다.[^5]

2) **HyDE 프롬프트는 ‘정답’이 아니라 ‘검색 키워드가 풍부한 문서’가 목표**
- HyDE가 실패하는 전형: LLM이 그럴듯한 원인을 단정 → 그 단정이 embedding space를 끌고 가서 **관련 없는 문서로 수렴**.
- 해결: “사실 단정 금지”, “Symptoms/Logs/Keywords 포함”, “관련 컴포넌트 나열”처럼 **retrieval-friendly 구조화**가 좋습니다. HyDE 자체가 “가상 문서 생성→임베딩” 흐름임을 잊지 마세요.[^1]

3) **Query Expansion은 ‘다양성’이 핵심이고, fusion은 RRF 같은 보수적 방식이 안전**
- expansion을 많이 만들수록 recall은 오르지만, 노이즈도 늘어 rerank 비용이 커집니다.
- 보통 3~5개로 제한하고, RRF로 합쳐 “한 쿼리의 폭주”를 막는 게 운영 친화적입니다(특정 expansion이 이상하면 전체가 망가지는 문제 완화).[^6]

### 흔한 함정/안티패턴
- **HyDE + QE를 항상 켜놓기**
  - 쿼리 타입별로 효과가 크게 다릅니다. “정확한 에러코드/함수명” 질의는 오히려 lexical/hybrid가 더 강하고, HyDE/QE가 의미를 흐릴 수 있습니다.
- **reranker 점수를 ‘절대값’으로 신뢰**
  - cross-encoder 점수는 모델/도메인에 따라 스케일이 달라 **threshold 기반 gating**을 할 때 특히 위험합니다. A/B로 calibrated threshold를 잡거나, “상대 순위만 사용”하는 설계가 안전합니다.[^8]
- **chunk 품질(구조/메타/길이) 방치**
  - retrieval이 약한 문제의 상당수는 chunking/메타데이터/하이브리드 인덱싱에서 해결됩니다. 고급 기법은 그 다음입니다.[^2]

### 비용/성능/안정성 트레이드오프 (의사결정 포인트)
- **Latency**
  - HyDE: LLM 1회 생성 비용(수백 ms~수 초)
  - QE: LLM 1회 + 검색 N회
  - Rerank: 후보 수 × 모델 추론
- **정확도**
  - 보통 “Recall(확장) → Precision(재랭킹)” 순으로 안정적으로 오릅니다.
- **운영 안정성**
  - LLM 기반 query transform(HyDE/QE)은 모델/프롬프트 변화에 민감합니다. 반드시 **offline eval + 샘플링 모니터링**(검색 결과 drift)을 걸어야 합니다.

---

## 🚀 마무리
정리하면, 2026년 8월의 “고급 RAG 성능 최적화”는 멋있는 아키텍처가 아니라 **실패 모드별 스위치**입니다.

- **HyDE**: 질문↔문서 스타일 갭이 큰 도메인에서 강력하지만, 쿼리당 LLM 비용과 편향 리스크가 있다.[^1]  
- **Reranking(cross-encoder/late interaction)**: 최종 precision을 끌어올리는 가장 확실한 카드지만, 후보 수 관리(프루닝)가 핵심이다.[^4]  
- **Query Expansion**: recall을 넓히되, 다양성/퓨전 전략을 잘못 잡으면 비용과 노이즈가 폭발한다.[^6]  

**도입 판단 기준(현실적 체크리스트)**
1) “정답 근거가 top-50에 아예 없나?” → QE/HyDE로 recall부터  
2) “근거는 있는데 순위가 낮나?” → reranking 우선  
3) “도메인 용어 불일치가 심한가?” → HyDE(또는 rewrite)  
4) “p95 latency 예산이 빡빡한가?” → late interaction로 중간 프루닝, HyDE/QE는 조건부

다음 학습으로는 (1) late interaction(ColBERT/PLAID) 기반의 단계적 프루닝, (2) HyDE류 런타임 오버헤드를 줄이려는 접근(HyPE 같은 최신 흐름), (3) query transform을 켜고 끄는 adaptive routing(Self-RAG/Corrective RAG 계열)을 함께 보길 추천합니다.[^3]

[^1]: <https://arxiv.org/abs/2212.10496>
[^2]: <https://www.tmls.nyc/research/production-rag-beyond-chunking>
[^3]: <https://arxiv.org/abs/2607.29402>
[^4]: <https://rag-repo.org/research/reranking-and-two-stage-retrieval/>
[^5]: <https://reranker.uk/guides/late-interaction-rerank>
[^6]: <https://arxiv.org/abs/2509.07794>
[^7]: <https://www.sbert.net/examples/cross_encoder/applications/README.html>
[^8]: <https://github.com/huggingface/sentence-transformers/blob/main/docs/cross_encoder/usage/usage.rst>
