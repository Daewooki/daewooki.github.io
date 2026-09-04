---
title: "HyDE + Reranking + Query Expansion: RAG 성능을 “한 단계” 끌어올리는 3단 조합"
description: "RAG 성능 최적화에서 가장 흔한 실패 패턴은 “검색이 약해서 LLM이 헛소리한다”가 아니라, 더 미묘하게는 (1) 후보 문서를 충분히 못 찾거나(recall 부족), (2) 찾았는데도 상위에 못 올리거나(precision 부족), (3) 올려놔도 컨텍스트 창에 쓸데없는 토큰을 쏟아붓는…"
date: 2026-02-01 03:18:59 +0900
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
RAG 성능 최적화에서 가장 흔한 실패 패턴은 **“검색이 약해서 LLM이 헛소리한다”**가 아니라, 더 미묘하게는 **(1) 후보 문서를 충분히 못 찾거나(recall 부족), (2) 찾았는데도 상위에 못 올리거나(precision 부족), (3) 올려놔도 컨텍스트 창에 쓸데없는 토큰을 쏟아붓는(token budget 낭비)** 입니다.  
2025~2026년 흐름을 보면, 이 문제를 구조적으로 해결하려고 **Two-stage retrieval(초기 검색 + reranking) + query expansion**을 결합하고, 여기에 **HyDE(Hypothetical Document Embeddings)** 같은 “의미 기반 query 강화”를 섞는 방식이 실전에서 강력한 조합으로 자리잡았습니다.[^1]

이번 글은 “RAG 고급 기법”을 표면적으로 나열하지 않고, **왜 HyDE/Query Expansion/Reranking이 서로 보완 관계인지**, 그리고 **어떤 순서와 예산(token/latency)으로 묶어야 성능이 실제로 오르는지**를 중심으로 정리합니다.

---

## 🔧 핵심 개념
### 1) HyDE: “질문을 답처럼 바꿔서” 임베딩한다
HyDE는 원 질문을 그대로 embedding하는 대신, LLM으로 **가상의 정답 문서(hypothetical document)** 를 먼저 생성하고, 그 문서를 embedding해서 검색 쿼리로 씁니다. 이렇게 하면 원 질문이 짧거나 모호해도, 가상 문서가 **도메인 용어/구체 표현**을 채워 넣어 dense retrieval에서 유리해집니다. LangChain도 HyDE Retriever를 공식 통합으로 제공하고, 구조는 “LLM 생성 → embeddings → vector search”로 단순합니다.[^2]

- 장점: 짧은 질문/은유적 표현/도메인 지식이 필요한 질문에서 recall이 잘 오름
- 함정: LLM이 “그럴듯한 허구 디테일”을 섞으면 embedding이 **잘못된 방향**으로 끌릴 수 있음 → 뒤 단계에서 제어 필요

### 2) Query Expansion: 후보 풀(recall)을 “의도적으로” 키운다
Query Expansion은 한 번의 쿼리로 끝내지 않고, **LLM 기반 확장/패러프레이즈/추상화/키워드 확장** 등을 통해 여러 쿼리를 만들거나, 쿼리를 풍부하게 만들어 더 넓은 후보를 가져오는 전략입니다.  
최근 연구/실무 방향은 “확장을 많이 해서 후보를 크게 뽑고, reranker가 token budget 내에서 최적 subset을 고르는” 2단 구조를 강조합니다. 특히 FlashRank처럼 **relevance뿐 아니라 novelty·brevity(짧음)·토큰 예산까지 고려해 재선택**하는 접근이 나옵니다.[^1]  
또한 UniRAG처럼 “쿼리 이해(확장/인코딩)를 분리하지 말고 통합해서, 상황에 맞는 augmentation 전략을 고르는” 흐름도 있습니다.[^3]

### 3) Reranking: precision과 컨텍스트 품질을 책임지는 ‘게이트’
초기 검색이 embedding 기반이면, 상위 K가 “비슷한 말”에는 강하지만 **정답성/근거성**은 약할 수 있습니다. 그래서 reranker가 필요합니다.

- **Cross-encoder reranker**: query+doc을 함께 넣고 relevance score → 정확도는 높지만 느림(문서 수에 선형 비용)[^4]  
- **Late-interaction(ColBERT 계열)**: 토큰 단위 상호작용(MaxSim)으로 효율/품질 절충[^4]  
- **LLM reranker**: reasoning이 강하지만 비용/지연이 큼(“마지막 10개만” 같은 제한적 사용이 실전적)[^4]

### 4) 세 기법의 ‘정답 조합’은 순서가 핵심
실전에서 가장 재현성 좋은 패턴은:

1) **Query Expansion/HyDE로 recall 확보** (후보 pool 확대)  
2) **Reranking으로 precision 회복** (정답 근거를 상위로)  
3) **Token budget 내 컨텍스트 선택/압축** (FlashRank류의 “subset selection”이 여기 해당)[^1]

즉, HyDE/Expansion은 “가져오는 단계”, Reranking은 “걸러내는 단계”로 역할이 다릅니다.

---

## 💻 실전 코드
아래는 “HyDE + Multi-query expansion + Cross-encoder rerank”의 최소 구현 예시입니다.  
(전제: 문서들은 이미 chunking되어 있고, vector DB/FAISS 등으로 검색 가능하다고 가정)

```python
# Python 3.10+
# pip install -U openai sentence-transformers faiss-cpu numpy

from openai import OpenAI
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer, CrossEncoder

client = OpenAI()

# 1) Embedding model (dense retrieval)
embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

# 2) Reranker (cross-encoder)
# 품질을 더 원하면 bge-reranker-large류를 쓰되, latency/메모리 고려 필요
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# ----- 준비: 예시 문서 코퍼스 -----
docs = [
    "HyDE는 질문에서 가상의 답변 문서를 생성한 뒤 그 문서를 embedding하여 검색 쿼리를 강화한다.",
    "Reranking은 초기 검색 결과를 query-document 쌍으로 다시 점수화하여 상위 문서의 precision을 끌어올린다.",
    "Query expansion은 패러프레이즈, 키워드 확장 등을 통해 후보 문서 recall을 증가시킨다.",
    "FlashRank는 토큰 예산 하에서 relevance/novelty/brevity 등을 고려해 evidence subset을 선택하는 접근을 제안한다."
]

doc_vecs = embed_model.encode(docs, normalize_embeddings=True).astype("float32")
index = faiss.IndexFlatIP(doc_vecs.shape[1])
index.add(doc_vecs)

def llm_generate(prompt: str) -> str:
    # HyDE/expansion에선 긴 출력이 오히려 노이즈일 수 있어 길이 제한을 두는 편이 안전
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )
    return resp.output_text.strip()

def hyde_document(question: str) -> str:
    prompt = f"""
너는 검색용 가상 문서를 작성한다.
요구사항:
- 사실 주장보다는 "이 질문에 답하려면 어떤 내용이 나와야 하는지"를 중심으로 기술
- 핵심 용어/동의어/관련 개념을 자연스럽게 포함
질문: {question}

가상 문서:
""".strip()
    return llm_generate(prompt)

def expand_queries(question: str, n: int = 3) -> list[str]:
    prompt = f"""
다음 질문을 검색 친화적으로 확장/패러프레이즈한 쿼리를 {n}개 만들어라.
- 서로 다른 관점(키워드 중심/정의 중심/비교 중심 등)으로 다양화
- 각 줄에 하나씩만 출력

원문: {question}
""".strip()
    text = llm_generate(prompt)
    return [line.strip("- ").strip() for line in text.splitlines() if line.strip()]

def dense_search(query: str, k: int = 10):
    qvec = embed_model.encode([query], normalize_embeddings=True).astype("float32")
    scores, idx = index.search(qvec, k)
    return [(docs[i], float(scores[0][j])) for j, i in enumerate(idx[0])]

def rerank(question: str, candidates: list[str], top_k: int = 3):
    pairs = [(question, c) for c in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]

def rag_retrieve(question: str):
    # (A) HyDE로 query 강화
    hyde = hyde_document(question)

    # (B) Multi-query expansion으로 후보 폭 확장
    expanded = expand_queries(question, n=3)

    # (C) 초기 후보 풀: 원문 + HyDE + 확장쿼리 검색 결과 합치기
    pool = []
    for q in [question, hyde] + expanded:
        pool.extend([d for d, _ in dense_search(q, k=5)])

    # 중복 제거
    pool = list(dict.fromkeys(pool))

    # (D) Reranking으로 상위 컨텍스트 선별
    top = rerank(question, pool, top_k=3)
    return {
        "hyde_doc": hyde,
        "expanded_queries": expanded,
        "top_context": top
    }

if __name__ == "__main__":
    q = "RAG에서 HyDE와 reranking을 같이 쓰면 왜 성능이 오르지?"
    result = rag_retrieve(q)
    print("=== HyDE ===")
    print(result["hyde_doc"])
    print("\n=== Expanded Queries ===")
    for x in result["expanded_queries"]:
        print("-", x)
    print("\n=== Top Context (reranked) ===")
    for ctx, sc in result["top_context"]:
        print(f"[{sc:.4f}] {ctx}")
```

핵심 포인트는 **HyDE/확장으로 pool을 키우되**, 최종 컨텍스트는 **reranker가 책임지게** 만든다는 점입니다. (그래야 HyDE/확장의 노이즈를 흡수할 수 있습니다.)

---

## ⚡ 실전 팁
- **HyDE 프롬프트는 ‘사실 생성’이 아니라 ‘검색용 용어 확장’에 최적화**하세요. HyDE가 특정 회사명/버전/수치 같은 “허구 디테일”을 만들어내면 embedding이 오염됩니다. LangChain 예시처럼 HyDE는 구현이 간단하지만, 성능은 프롬프트 품질에 크게 좌우됩니다.[^2]
- **확장 쿼리는 2~5개 정도가 sweet spot**인 경우가 많습니다. 많이 만들수록 recall은 오르지만 rerank 비용이 커지고, 오히려 “비슷비슷한 문서만 잔뜩” 가져올 수 있습니다. Two-stage retrieval 논문도 “확장으로 recall 확보 + 예산 기반 rerank/선택” 구조를 전면에 둡니다.[^1]
- **Reranker 선택 가이드**
  - latency 여유가 있으면 cross-encoder(정확도 최상)[^4]  
  - 트래픽이 많으면 late-interaction(ColBERT 계열)로 절충[^4]  
  - LLM rerank는 “마지막 10개” 같은 제한적 구간에서만 (비용 폭발 방지)[^4]
- **Token budget을 ‘검색 단계’에서부터 모델링**하세요. “top_k=20 넣고 LLM이 알아서”는 2026년에 비싸고 느립니다. FlashRank처럼 novelty·brevity를 포함해 evidence subset을 고르는 접근은, 컨텍스트 창이 제한적인 RAG에서 실무적으로 설득력이 큽니다.[^1]
- **평가 지표를 retrieval 관점으로 분해**하세요: (1) recall@K(정답 문서가 후보에 들어왔는가), (2) MRR/nDCG(상위에 올렸는가), (3) answer faithfulness(근거 기반으로 답했는가). Query expansion은 (1), reranking은 (2), subset selection은 (3)+비용을 주로 개선합니다.

---

## 🚀 마무리
HyDE, Reranking, Query Expansion은 각각 “좋아 보이는 옵션”이 아니라, **recall → precision → token budget**이라는 RAG 병목을 단계별로 푸는 조합입니다. 최신 흐름은 **확장으로 후보를 넓히고**, **reranker/예산 기반 선택으로 컨텍스트 품질을 보장**하는 Two-stage(또는 multi-stage) 파이프라인으로 수렴하고 있습니다.[^1]

다음 학습으로는:
- (1) **Hybrid retrieval(BM25 + dense) + expansion 조합**  
- (2) **ColBERT류 late-interaction 도입 시 저장공간/인덱싱 설계**[^4]  
- (3) **evidence subset selection(FlashRank류)와 컨텍스트 압축/요약의 결합**[^1]  

을 추천합니다.

[^1]: <https://arxiv.org/abs/2601.03258>
[^2]: <https://docs.langchain.com/oss/javascript/integrations/retrievers/hyde/>
[^3]: <https://aclanthology.org/2025.acl-long.693/>
[^4]: <https://thread-transfer.com/blog/2025-07-28-reranking-strategies/>
