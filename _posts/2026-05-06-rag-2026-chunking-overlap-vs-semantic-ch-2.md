---
title: "RAG 성능을 갈라버리는 2026년형 Chunking 설계: overlap vs semantic chunking, 그리고 “문서 구조”를 이기는 방법"
date: 2026-05-06 03:53:57 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-05]
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

RAG에서 “모델이 똑똑한데도 답을 못 한다/헛소리를 한다”의 상당수는 **retrieval 실패**고, 그 retrieval 실패의 뿌리에는 의외로 **document splitting(청킹) 설계**가 있습니다. 질문에 필요한 문장이 두 덩어리로 찢겨 서로 다른 chunk에 들어가면, retriever는 둘 중 하나만 가져오고 LLM은 **근거 부족을 hallucination으로 메우거나** “없다”고 말합니다. ([viqus.ai](https://viqus.ai/blog/rag-chunking-strategies-2026?utm_source=openai))

언제 쓰면 좋나:
- **규정/가이드/매뉴얼/정책/기술문서**처럼 섹션 구조가 명확하고, 답이 특정 단락/표/절에 “박혀 있는” 문서
- 문서가 길고(수십~수백 페이지), 질문이 디테일(예: 예외조항, 조건, 파라미터 설명)에 걸리는 경우
- “찾아오기만 하면” LLM은 잘 요약/추론할 수 있는 도메인

언제 쓰면 안 되나(혹은 chunking만으로 해결 불가):
- 데이터 자체가 최신성이 핵심인데 인덱스 업데이트가 느린 경우(청킹보다 ingestion/refresh가 병목)
- 질문이 여러 문서를 가로질러 **합성/비교**해야 하고, 메타데이터/랭킹/퓨전/리랭커가 더 중요한 경우
- 표/수식/코드가 많은데, 텍스트만 뽑아 “문장 단위 의미”로 쪼개려는 경우(구조 보존이 우선)

핵심 결론부터 말하면, 2026년 흐름은 “512 tokens + 50 overlap” 같은 고정 레시피가 아니라:
1) **문서 구조를 먼저 살리고**(heading/table/page/element)  
2) 그 안에서 **semantic boundary**를 쓰되 비용을 통제하고  
3) edge context는 overlap만이 아니라 **window/parent-child**로 해결하는 쪽으로 진화 중입니다. ([unstructured-53.mintlify.app](https://unstructured-53.mintlify.app/api-reference/partition/chunking?utm_source=openai))

---

## 🔧 핵심 개념

### 1) Chunking이 실제로 최적화하는 것
Chunking은 단순히 “나누기”가 아니라 아래 3가지를 동시에 맞추는 최적화 문제입니다.

- **Retrieval Recall**: 필요한 근거가 chunk 안에 존재해야 함
- **Precision/Noise**: chunk가 너무 크면 관련 없는 문장이 같이 딸려와 top-k가 더러워짐
- **Generation Groundedness**: LLM이 읽는 컨텍스트가 “답을 만들기 좋은 형태”여야 함

최근 연구/정리들은 chunking을 fixed/sentence/structure/semantic/LLM-guided/hierarchical/adaptive 같은 축으로 분류하고, “문서별로 다른 전략이 이긴다”는 쪽으로 무게가 실립니다. ([arxiv.org](https://arxiv.org/abs/2602.16974?utm_source=openai))

### 2) Overlap: 가장 싸고 효과적인 보험이지만, 과하면 독
**overlap**은 경계에서 문맥이 끊기는 문제를 완화합니다. 하지만 overlap을 늘리면:
- 인덱싱 토큰/임베딩 비용 증가
- 벡터 DB 저장량 증가
- 유사 chunk가 많아져 검색 결과가 중복되고 다양성이 떨어질 수 있음

Unstructured는 “element 기반으로 묶되, 너무 큰 element만 text-splitting하고 그때 overlap을 적용” 같은 모델을 제공합니다. 즉 “무조건 sliding window”가 아니라 **문서 파싱 결과(element)**를 우선으로 합니다. ([docs.unstructured.io](https://docs.unstructured.io/open-source/core-functionality/chunking?utm_source=openai))

또한 `overlap_all`처럼 “oversized element뿐 아니라 일반 chunk에도 overlap을 걸지” 선택지가 있는데, 이건 **비용과 중복률**에 직접적인 영향을 줍니다. ([docs.unstructured.io](https://docs.unstructured.io/open-source/ingestion/ingest-configuration/chunking-configuration?utm_source=openai))

### 3) Semantic chunking: “의미 경계”를 잡되 ingestion 비용이 숨어있다
LangChain의 `SemanticChunker`는 embedding 기반으로 문장 사이 의미 변화 지점을 찾아 chunk를 만듭니다(임계값 방식: percentile/standard deviation 등). ([api.python.langchain.com](https://api.python.langchain.com/en/latest/experimental/text_splitter/langchain_experimental.text_splitter.SemanticChunker.html?utm_source=openai))

장점:
- 문장/단락을 억지로 자르지 않아서 chunk가 “주제 단위”가 되기 쉬움
- 고정 길이 대비 검색 정확도가 올라갈 가능성

단점(실무에서 크게 체감):
- ingestion 단계에서 문장 단위 embedding/유사도 계산이 추가되어 **지연/비용**이 증가
- 문서 타입에 따라 개선 폭이 3~5% 수준으로 “미미한데 복잡도만 늘었다”는 피드백도 흔함 ([reddit.com](https://www.reddit.com/r/Rag/comments/1rab7rs/what_chunking_strategies_are_you_using_in_your/?utm_source=openai))
- 표/코드/목차-본문 관계 같은 “레이아웃/구조 의미”는 embedding만으로 잘 보존되지 않음(semantic chunking 단독 적용의 함정)

그래서 2026년 튜토리얼/가이드들에서 자주 나오는 패턴이 **hybrid**입니다:
- 1차로 `RecursiveCharacterTextSplitter` 같은 coarse split로 섹션 단위로 자른 후
- 2차로 semantic chunking을 적용해 미세 조정 ([langchain-tutorials.github.io](https://langchain-tutorials.github.io/langchain-semantic-text-splitter-chunk-by-meaning/?utm_source=openai))

### 4) Overlap의 대안: Sentence window / Parent-child / Context prefix
Overlap은 “앞/뒤 일부를 복사”하는 방식이라 중복이 필연입니다. 대신:
- LlamaIndex `SentenceWindowNodeParser`: 노드는 1문장 단위로 저장하되, 주변 문장 window를 metadata로 들고 있다가 **retrieval 후 LLM에 줄 때만 window로 확장**할 수 있습니다. 즉, “검색은 정밀하게, 생성은 넓게”가 가능합니다. ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/sentence_window/?utm_source=openai))
- 문서 구조 기반 chunking(heading/table/page/element) + 필요 시 window/parent로 확장: “저장/검색 단위”와 “LLM에 먹이는 단위”를 분리하는 발상입니다. (최근 논문/프레임워크들도 이 방향을 taxonomy로 다룹니다.) ([arxiv.org](https://arxiv.org/abs/2602.16974?utm_source=openai))

---

## 💻 실전 코드

현실적인 시나리오:  
사내 운영팀이 쓰는 “장애 대응 Runbook + 정책 문서(PDF→text)”를 RAG로 붙이는데, 질문은 보통 “조건+예외+절차”를 함께 요구합니다.  
문제는 **예외 조항이 다음 단락으로 넘어가거나**, “정의 섹션”을 같이 읽어야 답이 완성된다는 점입니다.

여기서는 **Hybrid(Structure/Coarse → Semantic) + 최소 overlap** 전략을 구현합니다.

### 0) 설치/의존성

```bash
pip install -U langchain-text-splitters langchain-experimental langchain-community sentence-transformers tiktoken
```

### 1) 1차: coarse split(섹션/문단 경계 우선) + 2차: semantic chunking

```python
import re
from typing import List, Dict, Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker

from langchain_community.embeddings import HuggingFaceEmbeddings


def normalize(text: str) -> str:
    # PDF 추출 텍스트에 흔한 공백/개행 노이즈 완화(너무 aggressive하면 표/코드 망가짐)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_hybrid_semantic(
    raw_text: str,
    source: str,
    coarse_chars: int = 6000,
    coarse_overlap: int = 200,
    semantic_breakpoint_percentile: float = 85.0,
) -> List[Document]:
    """
    - 1차(coarse): RecursiveCharacterTextSplitter로 큰 덩어리(섹션 후보) 생성
    - 2차(semantic): SemanticChunker로 의미 경계를 기준으로 세분화
    - 메타데이터에 source, 단계별 인덱스, 시작 오프셋 저장(디버깅/평가 필수)
    """
    text = normalize(raw_text)

    # 1) Coarse splitting: 문단/헤딩/문장 경계를 최대한 우선
    coarse = RecursiveCharacterTextSplitter(
        chunk_size=coarse_chars,
        chunk_overlap=coarse_overlap,
        separators=["\n\n## ", "\n\n# ", "\n\n", "\n", ". ", " "],
        add_start_index=True,
    )

    coarse_docs = coarse.create_documents([text], metadatas=[{"source": source, "stage": "coarse"}])

    # 2) Semantic splitting: embedding 기반 의미 경계
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
    sem = SemanticChunker(
        embeddings=embeddings,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=semantic_breakpoint_percentile,
    )

    out: List[Document] = []
    for i, d in enumerate(coarse_docs):
        # coarse chunk 안에서 semantic split
        sd = sem.create_documents([d.page_content], metadatas=[{**d.metadata, "coarse_i": i, "stage": "semantic"}])
        # semantic chunk에 coarse 시작 오프셋을 보존(추적/하이라이트에 중요)
        base = d.metadata.get("start_index", 0)
        for j, s in enumerate(sd):
            s.metadata["semantic_i"] = j
            s.metadata["coarse_start_index"] = base
            out.append(s)

    return out


if __name__ == "__main__":
    # 예: PDF에서 추출한 텍스트라고 가정(실무에서는 OCR/레이아웃 파서 단계가 앞에 옴)
    with open("runbook.txt", "r", encoding="utf-8") as f:
        raw = f.read()

    docs = chunk_hybrid_semantic(
        raw_text=raw,
        source="runbook_v2026_04",
        coarse_chars=6000,
        coarse_overlap=200,
        semantic_breakpoint_percentile=85.0,
    )

    print(f"chunks: {len(docs)}")
    print("sample metadata:", docs[0].metadata)
    print("sample content (first 400 chars):")
    print(docs[0].page_content[:400])
```

예상 출력(형태):
- `chunks: 180` 처럼 문서 길이에 비례
- metadata에 `source`, `coarse_i`, `semantic_i`, `start_index/coarse_start_index`가 들어가서 “어떤 split 단계에서 어디서 왔는지”를 역추적 가능

### 2) 이 전략을 “프로젝트에 적용 가능한” 형태로 평가하는 법(간단한 프레임)

Chunking은 감으로 하면 끝이 없습니다. 2026년 논문/가이드들이 반복해서 말하는 건 **평가 기반 선택**입니다. ([arxiv.org](https://arxiv.org/abs/2601.14123?utm_source=openai))  
최소한 아래를 로그로 남기세요.

- 질문별 top-k chunk에서 **정답 근거가 포함되는지**(human label 또는 LLM judge)
- chunk 길이 분포(p50/p95), 중복률(near-duplicate 비율)
- ingestion 시간/비용(semantic은 여기서 차이 큼)
- 동일 질문군에서 overlap 증가가 recall을 올리는지 vs 중복만 늘리는지

---

## ⚡ 실전 팁 & 함정

### Best Practice 1) “문서 구조 파싱 → chunking” 순서를 바꾸지 마라
PDF/HTML/Word는 단순 텍스트가 아니라 **레이아웃 의미**가 있습니다. Unstructured가 element 단위로 먼저 partition하고, 그 다음 chunking에서 element를 묶거나 oversized element만 split하는 철학은 꽤 실무적입니다. ([docs.unstructured.io](https://docs.unstructured.io/open-source/core-functionality/chunking?utm_source=openai))  
테이블/헤딩/리스트가 많은 문서에서 “그냥 텍스트로 뽑고 semantic chunking”부터 들어가면, 의미 경계가 아니라 **추출 노이즈 경계**를 학습하게 됩니다.

### Best Practice 2) overlap을 늘리기 전에 “검색 단위 vs 생성 단위 분리”를 먼저 검토
Overlap은 쉽지만 중복 비용이 계속 쌓입니다. 대신 sentence-window처럼:
- 저장/검색은 작은 단위(문장/짧은 단락)
- LLM에 주는 컨텍스트는 window/확장으로 크게  
로 설계하면, overlap 없이도 경계 손실을 줄일 수 있습니다. ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/sentence_window/?utm_source=openai))

### Best Practice 3) SemanticChunker는 “임계값 튜닝”이 전부다
LangChain `SemanticChunker`는 `breakpoint_threshold_type/amount`로 경계를 자릅니다. “percentile 85부터 시작해서 문서 타입별로 튜닝” 같은 실전 조언이 커뮤니티에서 반복됩니다. ([api.python.langchain.com](https://api.python.langchain.com/en/latest/experimental/text_splitter/langchain_experimental.text_splitter.SemanticChunker.html?utm_source=openai))  
문서가 매뉴얼/법무/릴리즈노트처럼 일정한 구조면 threshold를 올려 chunk를 덜 쪼개고, FAQ/위키처럼 주제가 빨리 바뀌면 threshold를 낮추는 식으로 접근하세요.

### 흔한 함정/안티패턴
- **무한 오버랩**: overlap을 올리면 recall은 잠깐 오르지만, top-k가 중복 chunk로 채워져 “다양한 근거”가 사라지고 결국 답이 약해질 수 있음(특히 reranker 없을 때)
- **semantic chunking = 무조건 정답**: ingestion 비용이 커지고 개선 폭이 문서에 따라 작을 수 있음(“3~5%인데 복잡도만 증가” 케이스) ([reddit.com](https://www.reddit.com/r/Rag/comments/1rab7rs/what_chunking_strategies_are_you_using_in_your/?utm_source=openai))
- **chunk 품질을 길이로만 관리**: 길이 제한(토큰/문자)만 맞추면 된다고 생각하면, 표/코드/절차서에서 “핵심 단위(블록)”가 깨져 retrieval이 흔들림

### 비용/성능/안정성 트레이드오프(의사결정 가이드)
- **고정 split + overlap**: 가장 단순/저렴/안정적. 대신 문서 구조를 자주 망가뜨림.
- **structure-aware(heading/element/page) + 최소 overlap**: 문서가 정형일수록 강력. 파서 품질이 관건. ([unstructured-53.mintlify.app](https://unstructured-53.mintlify.app/api-reference/partition/chunking?utm_source=openai))
- **semantic chunking**: 품질 잠재력은 있지만 ingestion 비용/튜닝 비용이 큼. “coarse→semantic” 하이브리드로 폭발을 막는 게 실무적. ([langchain-tutorials.github.io](https://langchain-tutorials.github.io/langchain-semantic-text-splitter-chunk-by-meaning/?utm_source=openai))
- **adaptive chunking(문서별 전략 선택)**: 연구는 강하게 밀고 있으나, 구현/운영 난이도가 올라감(메트릭/후처리/평가 파이프라인 필요). ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))

---

## 🚀 마무리

정리하면, 2026년 5월 시점의 “RAG chunking strategy document splitting”에서 실무적으로 가장 수익률 좋은 선택지는 다음 우선순위입니다.

1) **문서 구조를 먼저 살려라**(element/heading/table/page)  
2) 경계 손실은 overlap로만 때우지 말고, 가능하면 **window/parent-child/metadata context**로 “검색 단위 vs 생성 단위”를 분리하라 ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/sentence_window/?utm_source=openai))  
3) semantic chunking은 만능이 아니니, **coarse split 후 semantic**으로 비용을 통제하고 threshold를 문서 타입별로 튜닝하라 ([langchain-tutorials.github.io](https://langchain-tutorials.github.io/langchain-semantic-text-splitter-chunk-by-meaning/?utm_source=openai))  
4) 무엇보다 “우리 문서/질문”으로 **평가 루프**를 돌려라(연구도 결국 그 결론으로 수렴). ([arxiv.org](https://arxiv.org/abs/2601.14123?utm_source=openai))

다음 학습 추천(바로 실무에 도움 되는 순서):
- Unstructured의 chunking/element 기반 chunking 옵션과 `by_similarity`, `overlap_all`의 의미(문서 타입별로) ([unstructured-53.mintlify.app](https://unstructured-53.mintlify.app/api-reference/partition/chunking?utm_source=openai))  
- LangChain `SemanticChunker`의 threshold 전략(문서군별 튜닝 가이드 작성) ([api.python.langchain.com](https://api.python.langchain.com/en/latest/experimental/text_splitter/langchain_experimental.text_splitter.SemanticChunker.html?utm_source=openai))  
- LlamaIndex `SentenceWindowNodeParser` + metadata replacement로 “정밀 검색 + 넓은 생성 컨텍스트” 패턴 적용 ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/sentence_window/?utm_source=openai))  
- 마지막으로 adaptive/hierarchical chunking 관련 최신 연구 흐름(문서별 전략 선택) ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))

원하시면, (1) 문서 타입(PDF? Markdown? Confluence?) (2) 평균 문서 길이 (3) 질문 유형(정의/절차/비교/예외) (4) 현재 top-k/리랭커 유무를 알려주시면, 위 코드/파라미터를 기준으로 **당신 프로젝트용 chunking 실험 설계(평가지표+샘플링+튜닝 범위)**까지 구체적으로 잡아드릴게요.