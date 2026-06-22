---
title: "RAG 성능의 80%는 Chunking에서 결정된다: 2026년 6월 기준 Document Splitting/Overlap/Semantic Chunking 실전 전략"
date: 2026-06-22 05:13:05 +0900
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
RAG에서 “검색은 됐는데 답이 이상하다/근거가 약하다/헛소리를 한다”의 상당수는 embedding 모델이나 vector DB가 아니라 **document splitting(=chunking)** 설계 문제로 귀결됩니다. 고정 길이로 잘라 넣으면 다음 문제가 반복됩니다.

- **Boundary loss**: 답이 들어있는 문장이 chunk 경계에서 잘려 검색 상위에 안 뜸(또는 반쪽만 뜸)
- **Topic bleeding**: 하나의 chunk에 여러 주제가 섞여 embedding이 “중간 벡터”가 되어 recall/precision 동시 하락
- **비용 폭발**: overlap을 습관처럼 키우면 인덱싱/저장/검색 비용이 선형으로 증가

언제 쓰면 좋나:
- 문서가 길고(정책/스펙/매뉴얼), 섹션 구조가 뚜렷하며, 질문이 다양하게 들어오는 **enterprise knowledge base**
- “정확한 근거 인용/재현”이 중요한 **지원/컴플라이언스/기술 문서 QA**

언제 쓰면 안 되나(또는 최소화해야 하나):
- 데이터가 짧고 균질(FAQ 1~2문단)해서 chunking 이슈가 거의 없는 경우
- latency/비용이 극단적으로 민감한데, semantic chunking처럼 embedding 호출이 많이 늘어나는 방식을 “멋있어 보여서” 도입하는 경우
- 코드/JSON/HTML 같은 **구조 기반 데이터**를 텍스트처럼 자르는 경우(semantic이 아니라 구조 경계를 먼저 봐야 함)

---

## 🔧 핵심 개념
### 1) Chunking은 “검색 단위 설계”다
RAG의 retrieval은 보통 “chunk embedding ↔ query embedding” 유사도로 돌아갑니다. 즉 chunk는 단순 분할이 아니라 **retrieval의 원자 단위**입니다. 좋은 chunk는:
- **Intrachunk cohesion**(한 chunk 내부는 한 주제에 가깝고)
- **Interchunk separability**(chunk 간은 잘 구분되며)
- **Size compliance**(retrieval 후 LLM context에 안정적으로 들어감)
을 동시에 만족해야 합니다. 2026년에는 이런 품질을 문서별로 평가해 “고정값 튜닝” 대신 **문서-적응형(adaptive)**으로 고르자는 연구/프레임워크도 나왔습니다. ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))

### 2) Fixed-size + Overlap: 가장 싸고 예측 가능한 베이스라인
- **장점**: 구현 단순, 처리량 예측 쉬움, 인덱싱 파이프라인 안정적
- **단점**: 의미 경계 무시 → boundary loss/ topic bleeding 발생

Overlap은 경계 손실을 줄이는 전통적 해결책이지만, 2026년 연구 중에는 “overlap이 측정 가능한 이득이 없고 비용만 늘린다”는 결과도 있어(문서/과제 조건에 따라) 무조건 정답은 아닙니다. ([arxiv.org](https://arxiv.org/abs/2601.14123?utm_source=openai))  
결론: **overlap은 ‘보험’이지 ‘기본값’이 아니다.** 측정으로 결정해야 합니다.

### 3) Semantic chunking: “의미 경계”를 embedding으로 찾는다
대표 흐름(실무에서 가장 흔한 Kamradt 계열 변형)은 대략 이렇습니다.

1. 문서를 sentence 단위(또는 짧은 단위)로 쪼갠다
2. 인접 sentence(또는 window) 간 embedding similarity를 계산한다
3. similarity가 급락하는 지점을 “topic shift”로 보고 boundary를 둔다
4. 최소/최대 길이 제약을 걸어 chunk size를 통제한다

Chroma가 정리한 평가 글에서도 Greg Kamradt의 semantic chunking이 소개되고, LangChain에 반영되었다고 언급합니다. ([trychroma.com](https://www.trychroma.com/research/evaluating-chunking?utm_source=openai))  
LangChain에는 `SemanticChunker`가 experimental로 존재합니다. ([reference.langchain.com](https://reference.langchain.com/v0.3/python/experimental/text_splitter/langchain_experimental.text_splitter.SemanticChunker.html?utm_source=openai))  
LlamaIndex도 semantic splitter류를 제공합니다. ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/semantic_splitter/?trk=public_post_comment-text&utm_source=openai))

**차이점(Fixed-size vs Semantic)**  
- Fixed-size는 “길이”로 자르고 overlap으로 완화
- Semantic은 “경계”를 찾아 자르되, 길이 제약/후처리가 핵심(안 그러면 chunk size가 들쭉날쭉해 운영 난이도 증가)

### 4) 2026년에 같이 고려되는 상위 전략: Late chunking & Contextual retrieval
- **Late chunking**: “먼저 문서 전체를 long-context embedding으로 token-level까지 인코딩한 뒤, pooling 직전에 chunk를 나눠 chunk vector를 만든다”는 접근입니다. 긴 문서에서 chunk embedding이 문서 전역 문맥을 더 반영하도록 한다는 아이디어로 Jina AI가 2024년에 정리했고, 논문도 공개돼 있습니다. ([jina.ai](https://jina.ai/news/late-chunking-in-long-context-embedding-models/?nocache=1&utm_source=openai))  
- **Contextual retrieval(=context prefix)**: chunk가 문서에서 분리되며 잃는 문맥을 보완하기 위해, chunk 앞에 “상위 섹션 요약/헤더 경로” 같은 prefix를 붙여 embedding을 만들기도 합니다(Anthropic 계열로 알려진 패턴). ([forge.onyxlab.ai](https://forge.onyxlab.ai/techniques/contextual-retrieval/?utm_source=openai))

실무적으로는 “semantic chunking만”이 아니라  
**(구조 기반 split) → (semantic/recursive 보정) → (context prefix) → (budget 최적화)** 같은 파이프라인이 더 강합니다.

---

## 💻 실전 코드
아래는 **현실적인 시나리오(사내 기술 문서/정책 PDF를 텍스트로 추출했다고 가정)**에서,  
1) 구조/문단 기반 Recursive split 베이스라인을 만들고  
2) semantic chunking으로 경계 품질을 올린 뒤  
3) “섹션 경로(prefix)”를 붙여 embedding 안정성을 올리는  
3단계 빌드업 예제입니다.

> 전제: Python 3.11+, OpenAI/다른 embedding provider로 교체 가능. Vector DB는 예제로 FAISS(로컬) 사용.

### 0) 설치/환경
```bash
pip install -U langchain langchain-community langchain-text-splitters langchain-experimental faiss-cpu tiktoken python-dotenv
export OPENAI_API_KEY="..."
```

### 1) 베이스라인: RecursiveCharacterTextSplitter(토큰 기준) + 최소 overlap
LangChain에서 token 기반 split 가이드는 `from_tiktoken_encoder` 패턴을 제공합니다. ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/integrations/splitters/split_by_token?utm_source=openai))  
`chunk_size`의 의미(문자/토큰 혼동)는 실무에서 자주 터지는 함정이라, **반드시 token 기반 splitter로 고정**하는 편이 안전합니다. ([github.com](https://github.com/langchain-ai/langchain/issues/2026?utm_source=openai))

```python
# python
import os
from dataclasses import dataclass
from typing import List, Dict

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

@dataclass
class RawDoc:
    doc_id: str
    title: str
    text: str

def build_baseline_chunks(raw: RawDoc) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=700,        # "retrieval unit" 크기 (토큰)
        chunk_overlap=70,      # 10% overlap: 일단 작은 보험만
        separators=["\n\n", "\n", ". ", " ", ""],  # 문단 → 줄 → 문장 → 단어 → fallback
    )

    chunks = splitter.create_documents(
        texts=[raw.text],
        metadatas=[{"doc_id": raw.doc_id, "title": raw.title}],
    )

    # chunk_id/순번 메타데이터 부여
    out = []
    for i, d in enumerate(chunks):
        md = dict(d.metadata)
        md["chunk_index"] = i
        md["chunk_kind"] = "baseline_recursive"
        out.append(Document(page_content=d.page_content, metadata=md))
    return out

if __name__ == "__main__":
    raw = RawDoc(
        doc_id="policy-2026-06",
        title="Data Retention Policy",
        text=open("data_retention_policy.txt", "r", encoding="utf-8").read(),
    )
    chunks = build_baseline_chunks(raw)
    print("num_chunks:", len(chunks))
    print("sample_chunk_tokens_approx:", len(chunks[0].page_content) // 4)  # 거친 근사
    print("sample_metadata:", chunks[0].metadata)
```

예상 출력(형태):
- `num_chunks: 12`
- `sample_metadata: {'doc_id': ..., 'title': ..., 'chunk_index': 0, 'chunk_kind': 'baseline_recursive'}`

### 2) Semantic chunking: 의미 경계 기반으로 split(비용 증가, 품질 개선)
LangChain `SemanticChunker`는 embedding을 이용해 semantic boundary를 찾는 splitter입니다. ([reference.langchain.com](https://reference.langchain.com/v0.3/python/experimental/text_splitter/langchain_experimental.text_splitter.SemanticChunker.html?utm_source=openai))  
주의: 문서가 길면 sentence 단위 embedding 호출이 늘어 **인덱싱 비용/시간이 확 증가**합니다. 그래서 “모든 문서에 일괄 적용”이 아니라, **문서 유형/길이/질문 패턴**으로 타겟팅하는 게 일반적입니다.

```python
# python
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings  # 다른 provider로 교체 가능

def build_semantic_chunks(raw: RawDoc) -> List[Document]:
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    # threshold는 문서/도메인마다 달라서 "고정 정답"이 없다.
    # 운영에서는 LangSmith/자체 eval로 튜닝하거나,
    # 최소/최대 길이 제약 + 후처리(merge/split)로 안정화한다.
    splitter = SemanticChunker(embeddings=embeddings)

    docs = [Document(page_content=raw.text, metadata={"doc_id": raw.doc_id, "title": raw.title})]
    chunks = splitter.split_documents(docs)

    out = []
    for i, d in enumerate(chunks):
        md = dict(d.metadata)
        md["chunk_index"] = i
        md["chunk_kind"] = "semantic"
        out.append(Document(page_content=d.page_content, metadata=md))
    return out
```

### 3) “Context prefix”로 chunk 단독 의미를 강화(Overlap 대체/보완)
Chunk가 문서에서 떨어져 나오면 “이 문단이 어디 섹션인지” 같은 문맥이 사라집니다. 그래서 **섹션 경로/상위 헤더/요약**을 prefix로 붙여 embedding을 만들면 retrieval 실패를 줄이는 패턴이 알려져 있습니다. ([forge.onyxlab.ai](https://forge.onyxlab.ai/techniques/contextual-retrieval/?utm_source=openai))  

아래는 “문서 내 헤더 경로”를 정규식으로 추적해 prefix를 붙이는 간단 버전입니다(실무에서는 Markdown/HTML 파서로 더 견고하게).

```python
# python
import re

HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

def infer_section_path(full_text: str, chunk_text: str) -> str:
    """
    매우 단순한 휴리스틱:
    - chunk의 첫 문장이 full_text에서 등장하는 위치를 찾아
    - 그 이전에 등장한 markdown header들을 추출해 path로 만든다
    """
    anchor = chunk_text.strip().splitlines()[0][:80]
    pos = full_text.find(anchor)
    if pos == -1:
        return ""

    headers = []
    for m in HEADER_RE.finditer(full_text[:pos]):
        level = len(m.group(1))
        title = m.group(2).strip()
        # 레벨별 스택 처리(단순화)
        headers = headers[: level - 1]
        headers.append(title)

    return " > ".join(headers)

def add_context_prefix(raw: RawDoc, chunks: List[Document]) -> List[Document]:
    out = []
    for d in chunks:
        path = infer_section_path(raw.text, d.page_content)
        prefix = f"[doc={raw.title}]"
        if path:
            prefix += f" [section={path}]"
        enriched = prefix + "\n" + d.page_content
        md = dict(d.metadata)
        md["context_prefix"] = prefix
        out.append(Document(page_content=enriched, metadata=md))
    return out
```

운영 팁:
- prefix는 **짧게(수십 토큰)**. 길어지면 embedding이 prefix에 끌려가고 비용만 증가
- overlap을 줄이거나(혹은 0으로) prefix로 경계 손실을 완화하는 실험을 해볼 가치가 큼

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 적용 가능한 것 3가지)
1) **“문서 타입별로 다른 splitter”를 기본으로 깔기**  
정책/매뉴얼(헤더 구조) vs Q&A(짧은 항목) vs 코드/JSON(구조 경계) 는 최적이 다릅니다. 2026년 연구도 “문서별로 최적 chunking이 다르다”는 방향(Adaptive Chunking)을 제시합니다. ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))

2) **Overlap은 측정으로 정하되, 먼저 0~10%부터**  
많은 글이 10~20%를 권하지만(현업 경험 기반) ([langcopilot.com](https://langcopilot.com/posts/2025-10-11-document-chunking-for-rag-practical-guide?utm_source=openai)), 최근 분석에서는 overlap이 비용 대비 이득이 없을 수 있다는 결과도 있습니다. ([arxiv.org](https://arxiv.org/abs/2601.14123?utm_source=openai))  
따라서 “기본 15%” 같은 규칙보다, **질문 로그로 재현 가능한 eval**을 먼저 만드세요.

3) **Chunk 품질을 ‘검색 결과’로만 보지 말고 ‘최종 답 품질’로 보라**  
semantic chunking은 retrieval precision을 올릴 수 있지만, chunk size가 불안정하면 오히려 LLM context에서 **핵심 근거가 잘리는** 문제가 생깁니다(=retrieval은 좋아 보이는데 generation이 흔들림). semantic boundary + size 제약(merge/split 후처리)이 필수입니다. ([trychroma.com](https://www.trychroma.com/research/evaluating-chunking?utm_source=openai))

### 흔한 함정/안티패턴
- **문자 기반 chunk_size로 운영**: 모델/언어에 따라 tokenization이 달라 “700 chars”가 어떤 날은 150 tokens, 어떤 날은 400 tokens가 됩니다. token 기반 splitter로 고정하세요. ([langchain-5e9cc07a.mintlify.app](https://langchain-5e9cc07a.mintlify.app/oss/python/integrations/splitters/split_by_token?utm_source=openai))
- **semantic chunking을 전 문서에 일괄 적용**: 인덱싱 비용이 터집니다(특히 sentence embedding 호출 수). “긴 문서/변동 큰 문서/문의 많은 문서” 등 타겟을 정하세요.
- **코드/구조 문서를 텍스트처럼 자르기**: 함수/클래스가 반으로 잘리면 RAG는 거의 망합니다. 이런 경우는 AST/구조 경계 splitter가 우선입니다(커뮤니티에서도 지속적으로 문제 제기). ([reddit.com](https://www.reddit.com/r/LangChain/comments/1rzab5x/omnichunk_a_dropin_alternative_to/?utm_source=openai))

### 비용/성능/안정성 트레이드오프(의사결정 가이드)
- **가장 싸고 안정적**: token-based recursive + 작은 overlap(또는 prefix)
- **품질(경계) 개선**: semantic chunking(단, 비용↑/운영 복잡도↑)
- **긴 문서에서 embedding 품질 극대화**: late chunking(가능한 embedding 모델/인프라 제약 큼) ([arxiv.org](https://arxiv.org/abs/2409.04701?utm_source=openai))
- **문맥 손실 보정**: contextual retrieval(prefix)로 overlap 의존도를 낮추기 ([forge.onyxlab.ai](https://forge.onyxlab.ai/techniques/contextual-retrieval/?utm_source=openai))

---

## 🚀 마무리
2026년 6월 기준으로 RAG chunking은 “chunk_size/overlap 숫자 튜닝” 단계를 넘어, **문서 구조 + 의미 경계 + 문맥 보정(prefix) + (가능하면) 문서별 적응형 선택**으로 가는 흐름이 뚜렷합니다. ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))  

도입 판단 기준을 간단히 정리하면:
- 지금 RAG가 **boundary loss**(근거가 반쪽)로 흔들린다 → overlap을 무작정 늘리기 전에 **semantic chunking 또는 prefix**를 테스트
- 문서가 길고 섹션이 뚜렷하다 → semantic chunking/structure-aware split의 ROI가 큼
- 비용/속도가 최우선이고 문서가 비교적 짧다 → token-based recursive를 잘 다듬고, prefix로 보정하는 쪽이 현실적
- “문서마다 답이 들쭉날쭉”하다 → 문서별로 chunker를 선택/스위칭하는 방향(Adaptive Chunking 사고방식)으로 설계 ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))

다음 학습 추천(바로 실무에 도움 되는 순서):
1) Chroma의 chunking 평가 글로 semantic chunking의 평가 관점을 잡기 ([trychroma.com](https://www.trychroma.com/research/evaluating-chunking?utm_source=openai))  
2) LangChain `SemanticChunker`/LlamaIndex splitter를 실제 문서에 대입해 boundary 품질과 비용을 측정 ([reference.langchain.com](https://reference.langchain.com/v0.3/python/experimental/text_splitter/langchain_experimental.text_splitter.SemanticChunker.html?utm_source=openai))  
3) Late chunking/Contextual retrieval로 “overlap 없이도 문맥을 유지”하는 설계를 실험 ([arxiv.org](https://arxiv.org/abs/2409.04701?utm_source=openai))  

원하시면, (1) 당신의 문서 유형(PDF/Markdown/Confluence/코드), (2) 평균 문서 길이, (3) 질문 유형(정의/절차/예외/표 찾기) 3가지만 알려주시면, 위 전략을 **당신 케이스에 맞춘 chunk_size/overlap 후보 + 평가 지표(offline eval 템플릿)**로 구체화해 드릴게요.