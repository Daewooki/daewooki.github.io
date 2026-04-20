---
title: "RAG 성능을 바꾸는 건 “모델”이 아니라 “Chunk”다: 2026년 4월 기준 Document Splitting/Overlap/Semantic Chunking 실전 전략"
date: 2026-04-20 03:40:22 +0900
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
RAG에서 “답이 문서에 있는데도 못 찾는” 문제의 상당수는 retriever나 LLM이 아니라 **chunking(문서 청킹/분할)** 에서 시작합니다. 특히 다음 증상은 chunking 냄새가 진합니다.

- 정의/조건/예외가 **chunk 경계에서 잘려** top-k에 안 뜸
- chunk가 너무 커서 **topic soup**(여러 주제가 섞인 덩어리) → embedding이 흐려짐
- overlap을 크게 줬더니 **중복 chunk가 대량 검색**되어 비용/latency가 튐
- PDF/HTML에서 표/리스트/헤더가 깨져 **의미 단위가 붕괴**

언제 쓰면 좋나:
- 문서가 길고 구조가 복잡한(정책/계약/가이드/PDF) 지식베이스
- 질문이 “키워드 검색”이 아니라 **조건/절차/예외**를 묻는 Q&A
- production에서 “왜 틀렸는지”를 로그로 보고 **재현/개선**해야 하는 팀

언제 안 쓰는 게 낫나:
- 데이터가 짧고 균질(FAQ 몇 줄)해서 fixed window로도 충분
- ingest 비용(embedding/파싱/전처리)을 거의 못 쓰는 환경
- 실시간 스트리밍 데이터(로그/이벤트)처럼 “문서” 개념이 약한 경우(이때는 chunking보다 인덱싱/집계/structured retrieval이 더 큼)

최근 가이드들은 공통적으로 “범용 정답은 없고, 문서 구조/질문 패턴/평가로 결정”을 강조합니다. ([stackai.com](https://www.stackai.com/insights/chunking-strategies-for-rag-how-to-optimize-document-retrieval))

---

## 🔧 핵심 개념
### 1) Chunk는 “retrieval의 최소 단위”다
Chunking은 단순히 길이를 자르는 작업이 아니라, **embedding에 들어가는 의미 단위**를 설계하는 일입니다. StackAI가 지적하듯 chunk가 비일관/과대/과소면 retriever는 인접한 문장만 끌어오거나, 정의를 놓치거나, 중복을 양산합니다. ([stackai.com](https://www.stackai.com/insights/chunking-strategies-for-rag-how-to-optimize-document-retrieval))

### 2) Overlap은 “경계 손실”을 줄이지만 “중복 검색”을 만든다
Overlap의 본질은 **경계(boundary)에서 정보가 찢기는 확률을 낮추는 보험**입니다. 하지만 보험료는 명확합니다.

- 저장/embedding 비용 증가
- 검색 결과 상위에 **거의 같은 chunk**가 여러 개 올라옴 → reranker/LLM context 낭비
- 특히 top-k가 작은 시스템에서는 다양성이 떨어져 답이 더 나빠질 수도

그래서 2026년 실무 트렌드는 “무조건 overlap”이 아니라 **경계가 위험한 구간에만 overlap/윈도우를 적용**하거나, 아예 의미 기반 경계(semantic breakpoint)로 overlap 의존도를 낮추려는 방향입니다(아래 semantic chunking과 연결).

### 3) Semantic chunking = “topic shift”를 경계로 삼는다
LangChain의 `SemanticChunker`는 문장을 기본 단위로 쪼갠 뒤, 문장 임베딩 간 **semantic distance(유사도 하락)** 가 큰 지점을 breakpoint로 삼아 chunk를 만듭니다. 설정으로 breakpoint 임계값 방식(예: percentile), buffer(앞뒤 문장 포함), 최소 chunk 크기 등을 제어합니다. ([deepwiki.com](https://deepwiki.com/langchain-ai/langchain-experimental/3.2-semanticchunker))

핵심 흐름(개념적으로):
1) sentence split
2) 각 sentence embedding
3) 인접 문장 간 거리 계산 → 거리 급증 지점 = breakpoint 후보
4) breakpoint를 기준으로 묶되, min chunk size 미만은 병합

이 방식의 장점은 “의미 단위”를 더 잘 보존한다는 것이고, 단점은 **ingest 비용 + threshold 튜닝 난이도**입니다. ([stackai.com](https://www.stackai.com/insights/chunking-strategies-for-rag-how-to-optimize-document-retrieval))

### 4) Structure-aware / Hierarchical chunking이 다시 뜬다
Unstructured는 애초에 partition 단계에서 문서를 Title/List/Table 같은 **구조 요소(element)** 로 나눈 후, 그 element를 기반으로 chunk를 구성합니다. 그리고 `by_similarity`처럼 “연속 element 간 유사도”로 묶는 방식도 제공합니다. 즉 “먼저 구조를 복원하고, 그 위에서 의미/길이 제약을 적용”하는 접근입니다. ([docs.unstructured.io](https://docs.unstructured.io/platform-api/partition-api/chunking))

2026년 연구들도 chunking을 단순 고정 길이보다 **content-aware(문단 그룹, 구조 기반, 계층적)** 로 가져갈수록 retrieval 성능이 좋아진다는 결과를 보고합니다. 특히 2026년 3월 arXiv 대규모 비교에서 “Paragraph Group Chunking”이 평균 nDCG@5에서 상위였고, 도메인별로 최적이 달랐다고 밝힙니다. ([arxiv.org](https://arxiv.org/abs/2603.06976))

정리하면 2026년 4월 기준 현실적인 결론은:
- **Baseline**: recursive/structure-aware (문단/헤더 우선)
- **Hard cases**: semantic breakpoint + (필요 시) 최소 overlap
- **PDF/스캔/산업문서**: 구조 복원(레이아웃/섹션 트리) → 계층 chunking 쪽이 유리 ([arxiv.org](https://arxiv.org/abs/2604.12352?utm_source=openai))

---

## 💻 실전 코드
아래는 “사내 정책/가이드 문서(마크다운/텍스트) + Q&A RAG”를 가정한 **현실적인 ingestion 파이프라인** 예시입니다.

- 1단계: 헤더 기반 분할(문서 구조 보존)
- 2단계: 섹션 내부는 semantic chunking으로 topic shift를 반영
- 3단계: chunk metadata에 `doc_id/section_path/start_index`를 넣어 디버깅 가능하게
- 벡터DB는 예시로 Chroma(로컬) 사용

### 0) 의존성 설치
```bash
pip install -U langchain langchain-community langchain-experimental langchain-text-splitters chromadb tiktoken
```

### 1) Ingestion: “Header → Semantic” 하이브리드 chunking
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any
import os

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma


@dataclass
class ChunkedDoc:
    text: str
    metadata: Dict[str, Any]


def load_markdown(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def hybrid_chunk_markdown(md_text: str, doc_id: str) -> List[ChunkedDoc]:
    # (A) 구조 보존: 헤더 기준으로 섹션화
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")]
    )
    sections = header_splitter.split_text(md_text)

    # (B) 섹션 내부: semantic breakpoint로 chunk 생성
    # sentence embedding 기반이라 ingest 비용이 늘어납니다.
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    semantic_splitter = SemanticChunker(
        embeddings=embeddings,
        # buffer_size는 breakpoint 주변 문장을 앞/뒤로 포함해
        # 경계 손실을 줄이는 "의미 기반 overlap" 역할을 합니다.
        buffer_size=1,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=90,  # 보수적으로 topic shift가 큰 곳만 자르기
        add_start_index=True,
        min_chunk_size=400,  # 너무 작은 파편 chunk 방지(문서에 맞게 조정)
    )

    # (C) safety net: semantic 결과가 너무 길면 최종 길이 제한(토큰/문자)
    # 실제 운영에서는 "embedding 모델 입력 한계"로 필수입니다.
    hard_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200, chunk_overlap=120, separators=["\n\n", "\n", ". ", " "]
    )

    out: List[ChunkedDoc] = []
    for s in sections:
        section_text = s.page_content
        section_meta = dict(s.metadata or {})
        section_path = " > ".join([f"{k}:{v}" for k, v in section_meta.items()])

        semantic_docs = semantic_splitter.create_documents([section_text], metadatas=[{
            "doc_id": doc_id,
            "section_path": section_path,
        }])

        for d in semantic_docs:
            # hard limit 적용
            hard_docs = hard_splitter.create_documents([d.page_content], metadatas=[d.metadata])
            for hd in hard_docs:
                out.append(ChunkedDoc(text=hd.page_content, metadata=hd.metadata))

    return out


def build_chroma_index(chunks: List[ChunkedDoc], persist_dir: str) -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    texts = [c.text for c in chunks]
    metas = [c.metadata for c in chunks]

    vs = Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metas,
        persist_directory=persist_dir,
        collection_name="policy_rag",
    )
    vs.persist()
    return vs


if __name__ == "__main__":
    md_path = os.environ.get("MD_PATH", "./docs/security_policy.md")
    persist_dir = os.environ.get("CHROMA_DIR", "./chroma_policy")

    md = load_markdown(md_path)
    chunks = hybrid_chunk_markdown(md, doc_id=os.path.basename(md_path))

    print(f"chunks: {len(chunks)}")
    print("sample chunk metadata:", chunks[0].metadata)
    print("sample chunk text preview:", chunks[0].text[:200].replace("\n", " "))

    vs = build_chroma_index(chunks, persist_dir=persist_dir)

    # 간단 검색 확인
    q = "퇴사자 계정은 언제 비활성화해야 하나?"
    docs = vs.similarity_search(q, k=4)
    print("\nTop results:")
    for i, d in enumerate(docs, 1):
        print(f"[{i}] section_path={d.metadata.get('section_path')}, start_index={d.metadata.get('start_index')}")
        print(d.page_content[:220].replace("\n", " "), "\n")
```

#### 예상 출력(형태)
- `chunks: 120` 같은 개수
- `section_path=h1:... > h2:...` 로 “어디서 잘렸는지” 추적 가능
- 검색 결과에 동일 섹션이 과도하게 반복된다면 overlap/hard_split 파라미터를 조정할 신호

이 파이프라인이 실무적인 이유:
- “문서 구조(헤더)”를 먼저 고정해 **chunk가 섹션을 넘나드는 사고**를 줄임
- semantic breakpoint로 섹션 내부의 **topic shift**를 잡아 “너무 큰 섹션”을 자연스럽게 분해
- 최종 hard limit로 **모델 입력 한계**를 보장

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “chunk_size”보다 먼저 “질문 타입”을 분류하라
- Fact lookup(정의/값): 작은 chunk(짧은 문단 중심)
- Procedure/Policy(절차/예외): 조금 큰 chunk(조건+예외가 같이 있도록)
- Troubleshooting(원인/해결): 섹션 단위 + semantic 분해

대규모 실험에서도 도메인별로 강한 전략이 달랐습니다(법률/수학 vs 생물/물리/헬스). “우리 질문이 어떤 형태인지”가 파라미터보다 먼저입니다. ([arxiv.org](https://arxiv.org/abs/2603.06976))

### Best Practice 2) Overlap을 “상수”로 두지 말고 “위험 경계”에만 주기
무조건 20% overlap 같은 규칙은 중복 retrieval을 유발합니다. 오히려:
- 표/리스트/정의 구문처럼 경계 손실이 치명적인 포맷
- semantic breakpoint 주변 buffer(window)
- 헤더 직후/직전

이런 구간에만 overlap/window를 주는 편이 비용 대비 효율이 좋습니다. (LangChain `SemanticChunker`의 `buffer_size`는 사실상 “의미 기반 overlap”으로 활용 가능합니다.) ([deepwiki.com](https://deepwiki.com/langchain-ai/langchain-experimental/3.2-semanticchunker))

### Best Practice 3) PDF/레이아웃 문서는 “텍스트 splitter”로 해결하려 하지 말 것
PDF에서 표가 깨지고 헤더/푸터가 반복되면, recursive/semantic 이전에 **partition(레이아웃 파싱)** 이 우선입니다. Unstructured는 partition 결과(element) 기반 chunking과 similarity 기반 결합을 제공하고, 페이지 경계 유지(by_page) 같은 제약도 지원합니다. ([docs.unstructured.io](https://docs.unstructured.io/platform-api/partition-api/chunking))  
산업 문서(스캔/멀티모달)에서는 레이아웃/섹션 트리 복원 후 계층 chunking이 유리하다는 연구 흐름도 있습니다. ([arxiv.org](https://arxiv.org/abs/2604.12352?utm_source=openai))

### 흔한 함정) Semantic chunking을 “만능”으로 믿는 것
- ingest 비용이 큼(문장 단위 embedding + 거리 계산)
- threshold가 corpus마다 다름 → 이식성 낮음
- semantic이 잘게 쪼개지면 오히려 retrieval recall이 떨어질 수 있음(파편화)

따라서 semantic은 **baseline(구조/recursive)** 위에 얹는 “필요할 때만” 카드로 쓰는 게 안전합니다. ([stackai.com](https://www.stackai.com/insights/chunking-strategies-for-rag-how-to-optimize-document-retrieval))

### 비용/성능/안정성 트레이드오프 체크리스트
- 비용: (문장 수 × embedding 비용) + (chunk 수 × 저장/인덱스) 증가
- 성능: recall이냐 precision이냐(질문 타입에 따라 목표가 다름)
- 안정성: OCR/문장부호 깨짐 → sentence splitter/semantic이 흔들림(이때는 구조 기반이 더 안정적) ([stackai.com](https://www.stackai.com/insights/chunking-strategies-for-rag-how-to-optimize-document-retrieval))

---

## 🚀 마무리
핵심 정리:
- 2026년 4월 기준 chunking은 “길이 자르기”가 아니라 **retrieval 단위 설계**다.
- 고정 overlap은 쉽게 중복을 만들고, semantic은 쉽게 비용과 파편화를 만든다.
- 실무에서 가장 재현성 높은 출발점은 **Structure-aware/Recursive를 baseline**으로 두고, 실패 케이스(긴 섹션, 다주제 페이지, 정의/예외 분리)에만 **Semantic breakpoint(+ 최소 window)** 를 얹는 하이브리드다. ([stackai.com](https://www.stackai.com/insights/chunking-strategies-for-rag-how-to-optimize-document-retrieval))
- 연구 결과도 “content-aware(문단/구조/계층)” 쪽이 고정 길이 대비 유의미하게 좋고, 도메인별 최적이 다름을 보여줍니다. ([arxiv.org](https://arxiv.org/abs/2603.06976))

도입 판단 기준(빠르게):
- 문서가 Markdown/위키 중심 + 질문이 단문 Q&A → recursive + 작은 overlap부터
- 정책/계약/가이드처럼 예외/조건이 많다 → 헤더 기반 + 섹션 내부 semantic 고려
- PDF/스캔/표가 핵심 → 먼저 partition/레이아웃 복원(Unstructured류) 없이는 chunking 튜닝이 헛수고 ([docs.unstructured.io](https://docs.unstructured.io/platform-api/partition-api/chunking))

다음 학습 추천:
- LangChain `SemanticChunker` 파라미터(특히 `breakpoint_threshold_*`, `buffer_size`, `min_chunk_size`)를 실제 문서 20~50개에 대해 grid로 돌리고, “중복률/Top-k 다양성/정답 포함률”을 지표로 잡아 자동 평가 루프를 만드세요. (chunking은 설정이 아니라 **실험 시스템**입니다.) ([deepwiki.com](https://deepwiki.com/langchain-ai/langchain-experimental/3.2-semanticchunker))