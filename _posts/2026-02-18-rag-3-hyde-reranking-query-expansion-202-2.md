---
title: "RAG 성능을 한 단계 끌어올리는 3종 세트: HyDE + Reranking + Query Expansion (2026년 2월 기준)"
date: 2026-02-18 02:50:49 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-02]
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
RAG 성능이 “모델이 약해서” 무너지는 경우는 생각보다 드뭅니다. 실무에서 더 자주 터지는 병목은 **Retrieval 단계의 실패(낮은 recall / 낮은 precision)** 입니다. 짧고 모호한 사용자 질문은 코퍼스의 표현과 어긋나기 쉽고(용어 불일치), 벡터 검색은 “그럴듯한 근접”을 쉽게 만들어 **가짜 근거**를 컨텍스트로 끌고 들어옵니다.  
그래서 2024~2026 사이 RAG 고급 최적화에서 자주 묶여 나오는 조합이 **HyDE(semantic gap 보정) + Query Expansion(recall 확장) + Reranking(precision 회복)** 입니다. HyDE는 “질문을 문서처럼 바꿔 임베딩한다”는 발상으로 zero-shot dense retrieval을 강화했고, Query Expansion은 underspecified query를 보강하며, Reranking은 최종 컨텍스트의 질을 책임집니다. ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))

---

## 🔧 핵심 개념
### 1) HyDE: Hypothetical Document Embeddings
**정의**: 질의(query)를 바로 임베딩하지 않고, LLM이 **가상의 “이상적인 답변/문서(hypothetical document)”** 를 생성하게 한 뒤, 그 생성문을 임베딩해서 검색 벡터로 사용합니다. ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))

**왜 효과적인가(원리)**  
- dense retriever가 약한 게 아니라, 애초에 query가 너무 짧거나 표현이 달라서 **semantic gap**이 큽니다.  
- HyDE는 LLM이 “답변에 들어갈 법한 용어/구조”를 채워 넣어 **문서에 가까운 표현**으로 바꿉니다.  
- 이후 임베딩 단계의 “dense bottleneck”이 생성문 속 **허구 디테일을 완화**하고, 전체 토픽/의도 중심으로 코퍼스 근방(neighborhood)을 찾는다는 게 HyDE 논문의 핵심 설명입니다. ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))

**트레이드오프**: LLM 호출이 추가되어 **지연시간/비용**이 늘고, 프롬프트가 허술하면 오히려 오답 방향으로 “좋은 문장”을 생성해 retrieval을 망칠 수 있습니다. ([emergentmind.com](https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde?utm_source=openai))

### 2) Query Expansion: Multi-Query / Rewrite / Fusion
**정의**: 하나의 query로만 찾지 말고, LLM으로 **다양한 관점의 query 변형을 여러 개 생성**해 각각 검색한 뒤 합칩니다. LangChain의 MultiQueryRetriever가 대표적 접근입니다. ([langchain.readthedocs.io](https://langchain.readthedocs.io/en/latest/retrievers/langchain.retrievers.multi_query.MultiQueryRetriever.html?utm_source=openai))

**작동 방식(전형적 패턴)**  
1) 원 질문 → 변형 질의 3~5개 생성  
2) 각 질의로 top-k 후보 문서 수집  
3) 중복 제거/병합 후 reranking 또는 RRF(Reciprocal Rank Fusion) 같은 fusion으로 순위를 안정화  
이 흐름은 “단일 검색의 취약성”을 줄여 recall을 올리지만, 후보가 많아지므로 **reranking**이 거의 필수로 따라옵니다. ([emergentmind.com](https://www.emergentmind.com/topics/fusionrag?utm_source=openai))

### 3) Reranking: precision을 “회수”하는 마지막 관문
**정의**: 1차 검색(보통 BM25/dense)이 뽑아온 후보를, cross-encoder류 또는 rerank API로 **query-document 쌍을 정밀 채점**해 재정렬합니다. LangChain은 CohereRerank를 ContextualCompressionRetriever 형태로 쉽게 끼울 수 있습니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/retrievers/cohere-reranker?utm_source=openai))

**중요 포인트**  
- Query Expansion/HyDE로 recall을 공격적으로 올리면 “쓰레기 후보”도 같이 늘기 때문에, 최종 컨텍스트 품질은 reranker가 좌우합니다.  
- reranking은 정확도는 올리지만 비용이 크므로, 실무에선 **후보 수(top_k)를 제한**하고 캐시/배치/병렬화가 중요합니다. (최근엔 reranker 효율 최적화 연구도 활발합니다.) ([arxiv.org](https://arxiv.org/abs/2504.02921?utm_source=openai))

---

## 💻 실전 코드
아래 예시는 **(1) Multi-Query로 recall 확장 → (2) HyDE로 semantic gap 보정 → (3) Reranking으로 precision 회복**을 한 파이프라인에 묶는 실전형 스켈레톤입니다.  
주의: LangChain 버전/패키지 분리가 빠르게 변하므로, 예시는 “구조”를 이해하는 데 초점을 둡니다(키는 환경변수로 설정).

```python
# Python 3.10+
# pip install langchain langchain-openai langchain-community langchain-cohere faiss-cpu

import os
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# Query Expansion
from langchain.retrievers.multi_query import MultiQueryRetriever

# Reranking (Contextual Compression)
from langchain.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_cohere import CohereRerank

# (옵션) HyDE: LangChain에는 언어/버전별로 구현 위치가 달라질 수 있어
# 여기서는 "HyDE를 직접 구현"하는 안전한 방식으로 예시를 듭니다.
# 핵심은: (질문 -> hypothetical doc 생성 -> hypothetical doc 임베딩 -> 검색)
from langchain_core.prompts import ChatPromptTemplate

def build_vectorstore():
    # 데모용 문서(실무에선 chunking + metadata + hybrid 인덱싱 권장)
    docs = [
        Document(page_content="HyDE는 query로 가상의 문서를 생성한 뒤 그 문서를 임베딩해 검색한다."),
        Document(page_content="Reranking은 후보 문서 집합을 정밀 채점해 순서를 재정렬한다."),
        Document(page_content="Multi-query expansion은 질문을 여러 관점의 질의로 변형해 recall을 올린다."),
        Document(page_content="RRF(Reciprocal Rank Fusion)는 여러 랭킹 결과를 융합하는 대표 기법이다."),
    ]
    embeddings = OpenAIEmbeddings()
    return FAISS.from_documents(docs, embeddings)

# 1) HyDE용 hypothetical document 생성 프롬프트
HYDE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You write a factual, information-dense passage that would appear in a technical document."),
    ("human", "Question: {q}\n\nWrite a short technical passage (6-10 sentences) that answers the question.")
])

def hyde_retrieve(llm, vectorstore, q: str, k: int = 20):
    # (a) hypothetical doc 생성
    hypo = llm.invoke(HYDE_PROMPT.format_messages(q=q)).content

    # (b) hypothetical doc을 query로 삼아 1차 후보 검색 (dense)
    #     -> 여기서 vectorstore는 내부적으로 hypo를 임베딩해 nearest search 수행
    candidates = vectorstore.similarity_search(hypo, k=k)

    return candidates, hypo

def main():
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    vectorstore = build_vectorstore()

    user_query = "RAG에서 HyDE와 Query Expansion, Reranking을 같이 쓰면 뭐가 좋아져?"

    # 2) Query Expansion: MultiQueryRetriever로 후보 폭을 넓힘
    base_retriever = vectorstore.as_retriever(search_kwargs={"k": 10})
    mq = MultiQueryRetriever.from_llm(retriever=base_retriever, llm=llm)
    mq_docs = mq.invoke(user_query)  # 여러 질의로 검색한 결과 union

    # 3) HyDE: semantic gap 보정으로 또 다른 후보군 확보
    hyde_docs, hypo_text = hyde_retrieve(llm, vectorstore, user_query, k=20)

    # 4) 후보 병합(중복 제거)
    merged = {d.page_content: d for d in (mq_docs + hyde_docs)}
    merged_docs = list(merged.values())

    # 5) Reranking: merged 후보를 query 기준으로 재정렬 + 상위만 남김
    #    - CohereRerank는 ContextualCompressionRetriever 형태로 흔히 연결
    #    - 실무에선 merged_docs를 "임시 retriever"로 만들거나,
    #      처음부터 base_retriever의 k를 키우고 reranker를 바로 붙이는 구성이 더 깔끔할 때가 많음
    reranker = CohereRerank(model="rerank-english-v3.0")  # 모델명은 사용 환경에 맞게
    compression = ContextualCompressionRetriever(
        base_retriever=vectorstore.as_retriever(search_kwargs={"k": 30}),
        base_compressor=reranker,
    )
    top_docs = compression.invoke(user_query)

    print("=== User Query ===")
    print(user_query)
    print("\n=== HyDE Hypothetical Passage (debug) ===")
    print(hypo_text)
    print("\n=== Top Docs After Rerank ===")
    for i, d in enumerate(top_docs, 1):
        print(f"{i}. {d.page_content}")

if __name__ == "__main__":
    main()
```

---

## ⚡ 실전 팁
1) **HyDE는 ‘항상 ON’이 아니라 ‘조건부 ON’이 좋다**  
질문이 짧거나 모호하고, 1차 검색 점수/엔트로피가 불안할 때만 HyDE를 켜면 비용 대비 효율이 좋아집니다. HyDE는 프롬프트 품질에 민감하고, 생성이 빗나가면 retrieval 자체가 다른 동네로 가버릴 수 있습니다. ([emergentmind.com](https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde?utm_source=openai))

2) **Query Expansion은 recall을 올리되, 후보 폭발을 제어하라**  
- 변형 질의 개수(n)와 각 질의의 top_k를 곱하면 후보가 기하급수로 늘어납니다.  
- 그래서 보통 “확장 → fusion(RRF) 또는 dedupe → rerank” 순서가 안정적입니다. FusionRAG/RRF 계열이 이 문제를 정면으로 다룹니다. ([emergentmind.com](https://www.emergentmind.com/topics/fusionrag?utm_source=openai))

3) **Reranking은 성능 상한을 올리지만, 시스템 병목이 되기 쉽다**  
- reranker에 들어가는 후보 수를 20~100 사이로 관리하고, batch inference/캐시를 붙이세요.  
- reranker가 비싸서 못 쓰는 상황이면, “확장 질의 수를 줄이고(precision 쪽으로) HyDE만 제한적으로” 같은 타협이 필요합니다. ([arxiv.org](https://arxiv.org/abs/2504.02921?utm_source=openai))

4) **평가(Eval)를 retrieval 단위로 쪼개라**  
생성 답변 정확도만 보면 원인분리가 안 됩니다. 최소한 아래를 분리 측정하세요.  
- recall@k: 정답 근거 chunk가 top-k 안에 들어왔나?  
- rerank hit rate: rerank 후 상위 n개에 정답이 올라왔나?  
이렇게 봐야 “Query Expansion이 필요한 문제인지, reranker가 약한지, chunking이 문제인지”가 갈립니다.

---

## 🚀 마무리
HyDE, Query Expansion, Reranking은 역할이 명확합니다.

- **HyDE**: query를 “문서처럼” 바꿔 **semantic gap을 메우는** 장치 ([arxiv.org](https://arxiv.org/abs/2212.10496?utm_source=openai))  
- **Query Expansion**: 다양한 표현/관점을 추가해 **recall을 끌어올리는** 장치 ([langchain.readthedocs.io](https://langchain.readthedocs.io/en/latest/retrievers/langchain.retrievers.multi_query.MultiQueryRetriever.html?utm_source=openai))  
- **Reranking**: 늘어난 후보에서 **precision을 회수**해 최종 컨텍스트를 정제 ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/retrievers/cohere-reranker?utm_source=openai))  

다음 학습으로는 (1) RRF 기반 fusion, (2) chunking/metadata 필터링/recency 전략, (3) reranker 효율 최적화(KV-cache reuse 등) 쪽을 같이 보면 “성능-비용-지연” 트레이드오프 설계를 훨씬 잘 하게 됩니다. ([emergentmind.com](https://www.emergentmind.com/topics/fusionrag?utm_source=openai))