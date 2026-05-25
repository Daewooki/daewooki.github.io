---
title: "RAG 성능의 천장을 결정하는 2026년식 Chunking/Document Splitting 전략 (Overlap vs Semantic Chunking 실전 가이드)"
date: 2026-05-25 04:40:34 +0900
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
RAG에서 “검색이 헛돌고 답이 근거 없이 흔들리는” 문제의 상당수는 embedding/LLM이 아니라 **문서가 어떻게 쪼개졌는지(chunking)** 에서 시작합니다. 특히 규정/정책/기술문서처럼 **문장 하나가 정확도를 좌우**하는 문서에서, 경계가 잘못 잘리면 “관련은 있어 보이는데 정답 문장이 없는 chunk”만 계속 뽑히는 상황이 자주 나옵니다(실무자들도 실패 케이스를 뜯어보면 대개 이 케이스). ([reddit.com](https://www.reddit.com/r/LangChain/comments/1tgcldy/why_does_everyone_skip_the_chunking_part/?utm_source=openai))

**언제 쓰면 좋나**
- 문서가 길고(수십~수백 페이지), 섹션/헤딩/표/코드블록 등 **구조가 강한 문서**
- 질문이 “정의/예외/조건/수치/ID”처럼 **정확한 구절**을 요구하는 QA
- 같은 문서라도 “챕터/섹션 단위로 의미가 뚝뚝 끊기는” 콘텐츠

**언제 chunking에 과투자하면 안 되나**
- 문서가 짧아서(예: 1~2k tokens) 그냥 통째로 넣는 게 가능한 경우
- 검색 자체가 아니라, 요약/변환처럼 “정밀 인용”이 덜 중요한 워크플로우
- 쿼리 품질/메타데이터/하이브리드 검색(BM25+vector) 부재로 인한 문제를 chunking으로만 때우려는 경우(정확한 ID/코드에는 vector만으로 한계가 큼). ([reddit.com](https://www.reddit.com/r/LangChain/comments/1tgcldy/why_does_everyone_skip_the_chunking_part/?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Chunking의 목표는 “검색 단위 최적화”다
RAG의 retrieval은 결국 **top-k chunk 선택 게임**입니다. chunk가 너무 크면 precision이 떨어지고(잡음 증가), 너무 작으면 recall은 좋아져도 **정답 생성에 필요한 주변 맥락이 사라집니다**. 그래서 2026년 트렌드는 “고정 길이 vs semantic” 이분법이 아니라,
- **구조(heading/section) 기반으로 1차 분할**
- 그 안에서 **semantic boundary 또는 문장 단위로 2차 분할**
- 필요하면 **parent-child(계층형)로 맥락 복원**
으로 가는 쪽이 강합니다. (계층형/structure-aware가 성능에 유의미하다는 실험들도 계속 나오는 중) ([arxiv.org](https://arxiv.org/abs/2603.24556?utm_source=openai))

### 2) Overlap은 “보험”이지 “치료”가 아니다
Overlap은 경계에서 문장이 잘리는 문제를 완화하지만, 문서 구조를 무시한 채 무작정 sliding window를 돌리면 **주제 전환 지점이 chunk 내부에 섞여** 검색이 애매해집니다. Reddit에서도 “overlap이 나쁘진 않지만 나쁜 전략을 고치진 못한다”는 얘기가 반복되고요. ([reddit.com](https://www.reddit.com/r/Rag/comments/1t59a9z/chunking_decision_you_make_on_day_1_determines/?utm_source=openai))  
실무 감각으로 정리하면:
- **Overlap은 10~15% 수준**(예: 800 tokens에 80~120 tokens)에서 “경계 손실”만 막는 용도로 쓰는 게 비용 대비 효율이 좋습니다. ([minneker.github.io](https://minneker.github.io/nlp-26wi/assets/lectures/20260224-rag-and-tools.pdf?utm_source=openai))

### 3) Semantic chunking은 “경계 탐지(boundary detection)” 문제다
2026년 semantic chunking의 큰 흐름은 “LLM이 알아서”라기보다, **인접 문장/문단 임베딩 유사도의 변화로 breakpoint를 잡는 방식**과, 문서 구조(heading)와 결합하는 방식입니다. LangChain의 `SemanticChunker`도 “의미적으로 뭉치는 단위”를 만들기 위해 embedding 기반으로 쪼갭니다. ([deepwiki.com](https://deepwiki.com/langchain-ai/langchain-experimental/3.2-semanticchunker?utm_source=openai))  
최근에는 더 나아가, 긴 내러티브 문서에서 **자연스러운 분할 지점**을 LLM/모델로 탐지하는 시도(LumberChunker)처럼 “chunking=segmentation 모델링”으로 보는 접근도 나왔습니다. ([blog.ml.cmu.edu](https://blog.ml.cmu.edu/2026/03/17/lumberchunker-long-form-narrative-document-segmentation/?utm_source=openai))

### 4) (중요) “내 문서에 맞는 chunker를 고르는” 쪽으로 간다
하나의 chunking이 모든 문서에 최적일 가능성은 낮습니다. 2026년 논문들에서는 문서 기반의 내재적 지표(응집도, 블록 무결성 등)로 **문서별로 chunking 전략을 선택하는 adaptive chunking**을 제안합니다. 즉, “우리는 800/120이 정답”이 아니라, **문서 타입별로 정책을 나누는 게 정답**에 가깝습니다. ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “사내 정책/기술 스펙 문서(Markdown/PDF→Markdown 전처리됨)를 RAG로 붙이는” 현실적인 시나리오입니다.

- 1단계: heading 기반으로 큰 덩어리(Parent) 유지
- 2단계: parent 내부는 semantic chunking으로 Child 생성
- 3단계: 검색은 child로 하되, 답변에는 parent 문맥을 같이 붙이는(맥락 복원) 형태

> 의존성: `pip install langchain-text-splitters langchain-experimental sentence-transformers numpy`

```python
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

# (선택) LangChain semantic chunker를 쓰고 싶으면:
# from langchain_experimental.text_splitter import SemanticChunker

@dataclass
class Chunk:
    id: str
    text: str
    meta: Dict[str, Any]

def split_by_markdown_headings(md: str) -> List[Chunk]:
    """
    구조 기반 1차 분할: heading 단위 Parent chunk 생성
    - RAG에서 'breadcrumb(제목 계층)'을 meta로 남겨두면 검색/디버깅이 쉬워짐
    """
    lines = md.splitlines()
    sections: List[Tuple[str, List[str]]] = []
    current_title = "ROOT"
    buf: List[str] = []

    heading_re = re.compile(r"^(#{1,6})\s+(.*)\s*$")

    for line in lines:
        m = heading_re.match(line)
        if m:
            if buf:
                sections.append((current_title, buf))
            level = len(m.group(1))
            title = m.group(2).strip()
            current_title = f"{'#'*level} {title}"
            buf = [line]
        else:
            buf.append(line)
    if buf:
        sections.append((current_title, buf))

    parents = []
    for i, (title, content_lines) in enumerate(sections):
        text = "\n".join(content_lines).strip()
        if not text:
            continue
        parents.append(
            Chunk(
                id=f"p{i}",
                text=text,
                meta={"title": title, "kind": "parent"}
            )
        )
    return parents

def semantic_breakpoint_chunk(
    text: str,
    model: SentenceTransformer,
    target_chars: int = 1800,
    min_chars: int = 900,
    thr_quantile: float = 0.20,
    overlap_sentences: int = 1
) -> List[str]:
    """
    embedding 기반 breakpoint semantic chunking (가볍게 구현)
    - 문장 단위로 나눈 뒤, 인접 문장 embedding similarity가 급락하는 지점을 경계 후보로 사용
    - 문서마다 밀도가 다르므로, threshold를 절대값(0.7)로 고정하기보다 분위수 기반으로 둠
      (실무에서 문서군이 섞이면 절대 threshold는 쉽게 망가짐)
    """
    # 문장 분리(단순): 실제 서비스면 spaCy/kiwi 등 사용 권장
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text) if s.strip()]
    if len(sents) <= 3:
        return [text]

    emb = model.encode(sents, normalize_embeddings=True)
    sims = (emb[:-1] * emb[1:]).sum(axis=1)  # cosine similarity since normalized
    # similarity가 낮을수록 경계일 확률↑
    thr = np.quantile(sims, thr_quantile)

    chunks = []
    start = 0
    acc_len = 0

    def flush(end_idx: int):
        nonlocal start
        chunk_sents = sents[start:end_idx]
        chunks.append(" ".join(chunk_sents).strip())
        # overlap: 마지막 n문장을 다음 chunk의 시작에 포함
        start = max(end_idx - overlap_sentences, start)

    for i in range(len(sims)):
        acc_len += len(sents[i]) + 1
        is_break = sims[i] <= thr and acc_len >= min_chars
        is_too_big = acc_len >= target_chars

        if is_break or is_too_big:
            flush(i + 1)
            acc_len = sum(len(s) + 1 for s in sents[start:i+1])

    if start < len(sents):
        chunks.append(" ".join(sents[start:]).strip())

    return [c for c in chunks if c]

def build_parent_child_chunks(md: str) -> List[Chunk]:
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    parents = split_by_markdown_headings(md)

    out: List[Chunk] = []
    for p in parents:
        children = semantic_breakpoint_chunk(
            p.text, model,
            target_chars=1800,
            min_chars=900,
            thr_quantile=0.20,
            overlap_sentences=1
        )
        for j, c in enumerate(children):
            out.append(
                Chunk(
                    id=f"{p.id}-c{j}",
                    text=c,
                    meta={
                        "kind": "child",
                        "parent_id": p.id,
                        "title": p.meta["title"],
                    }
                )
            )
        # parent도 저장해두면(별도 인덱스 또는 docstore) 검색 후 문맥 복원에 사용 가능
        out.append(p)
    return out

if __name__ == "__main__":
    # 현실적인 입력: 사내 운영 정책/개발 가이드/규정 문서 같은 Markdown
    md = open("policy.md", "r", encoding="utf-8").read()
    chunks = build_parent_child_chunks(md)

    # 예상 출력(예): parent 수십개 + child 수백개
    parents = sum(1 for c in chunks if c.meta["kind"] == "parent")
    children = sum(1 for c in chunks if c.meta["kind"] == "child")
    print(f"parents={parents}, children={children}")
    print("sample child:\n", next(c.text for c in chunks if c.meta["kind"] == "child")[:400])
```

**이 코드가 “toy가 아닌” 이유**
- heading 기반 1차 분할은 실제 문서(정책/스펙/PRD/ADR)에 바로 먹힙니다.
- child chunk는 문장 경계 + semantic breakpoint로 만들어 “필요한 문장 포함” 확률을 올립니다.
- meta에 `title`, `parent_id`를 남겨서 retrieval 실패를 디버깅할 때 “어느 섹션이었나”를 즉시 추적할 수 있습니다(이게 운영에서 시간을 크게 줄입니다).

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Structure-aware → Semantic** 순서로 쪼개라  
먼저 heading/섹션/표/코드블록 같은 “의미적 컨테이너”를 보존하고, 그 안에서만 semantic chunking을 적용하세요. 구조를 무시한 semantic은 “문서 내 계층”을 잃고, 검색 결과를 사람이 해석/검증하기도 어려워집니다. ([arxiv.org](https://arxiv.org/abs/2603.24556?utm_source=openai))

2) Overlap은 “문장 단위”로 최소화하라  
character/token overlap을 크게 주면 저장량·embedding 비용이 직선으로 늘고, top-k가 중복 문맥으로 낭비됩니다. 대신 위 예제처럼 **마지막 1~2문장 overlap**만으로 경계 손실을 크게 줄일 수 있습니다(특히 규정/정의 문장). “12% overlap” 같은 가이드도 이 맥락에서 자주 등장합니다. ([minneker.github.io](https://minneker.github.io/nlp-26wi/assets/lectures/20260224-rag-and-tools.pdf?utm_source=openai))

3) chunking은 “고정값”이 아니라 “문서군별 정책”으로 운영하라  
최근 연구는 문서별 지표로 chunker를 선택하는 adaptive 방향을 제안합니다. 실무에서도 “계약서/정책/릴리즈노트/코드”를 동일 파라미터로 처리하면 결국 특정 문서군이 망가집니다. 문서 타입별로 chunker/size/overlap을 나누는 게 장기적으로 안정적입니다. ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))

### 흔한 함정/안티패턴
- **semantic chunking이면 무조건 좋다**: 문서가 짧거나, 질문이 넓게 요약을 요구하는 경우엔 큰 chunk가 더 낫습니다. 실험/벤치마크에서도 “간단한 recursive가 충분히 강한” 케이스가 반복해서 나옵니다(결국 내 문서에서 측정해야 함). ([reddit.com](https://www.reddit.com/r/Rag/comments/1r47duk/we_benchmarked_7_chunking_strategies_most_best/?utm_source=openai))
- **Overlap으로 모든 문제를 해결하려고 함**: overlap은 missing sentence를 줄이지만, “주제 혼합 chunk” 문제를 해결하지 못합니다. ([reddit.com](https://www.reddit.com/r/Rag/comments/1t59a9z/chunking_decision_you_make_on_day_1_determines/?utm_source=openai))
- **vector-only 검색**: 제품 코드/모델명/조항 번호처럼 exact match가 중요한 도메인은 BM25/keyword를 섞지 않으면 “가까운 말”을 틀리게 가져옵니다(그리고 이걸 chunking 탓으로 오해함). ([reddit.com](https://www.reddit.com/r/LangChain/comments/1tgcldy/why_does_everyone_skip_the_chunking_part/?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- Semantic chunking(embedding 기반)은 **인덱싱 시간이 늘고** 문서가 많으면 비용이 커집니다.
- 하지만 운영에서 진짜 비용은 “헛도는 답변으로 인한 사용자 재시도/불신/지원 티켓”인 경우가 많습니다. 그래서 **핵심 문서군(정책/규정/스펙)** 에만 semantic+structure를 적용하고, 나머지는 recursive로 가는 하이브리드가 현실적입니다. ([arxiv.org](https://arxiv.org/abs/2603.24556?utm_source=openai))

---

## 🚀 마무리
정리하면 2026년 5월 기준 RAG chunking의 실전 결론은 이렇습니다.

- “chunk_size 몇이 정답?”이 아니라 **문서 구조를 살리고, 경계를 의미적으로 자르고, 필요하면 계층으로 문맥을 복원**하는 쪽이 안정적입니다. ([arxiv.org](https://arxiv.org/abs/2603.24556?utm_source=openai))  
- Overlap은 필수에 가깝지만, **10~15% 또는 1~2문장 수준의 최소 overlap**을 추천합니다. ([minneker.github.io](https://minneker.github.io/nlp-26wi/assets/lectures/20260224-rag-and-tools.pdf?utm_source=openai))  
- Semantic chunking은 강력하지만 비용이 있으니, **문서군별로 적용 범위를 나누고**(혹은 adaptive chunking처럼 문서별 선택) 실패 쿼리를 기준으로 튜닝하세요. ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))

**도입 판단 기준(체크리스트)**
- 내 실패 케이스가 “관련 chunk는 나오는데 정답 문장이 없다”인가? → semantic/structure + 최소 overlap로 개선 여지 큼 ([reddit.com](https://www.reddit.com/r/LangChain/comments/1tgcldy/why_does_everyone_skip_the_chunking_part/?utm_source=openai))  
- 문서가 heading/조항/섹션 중심인가? → structure-aware 1차 분할부터  
- 문서 타입이 섞여 있는가? → 문서군별 정책(또는 adaptive) 없으면 결국 망가짐 ([arxiv.org](https://arxiv.org/abs/2603.25333?utm_source=openai))

**다음 학습 추천**
- 구조/계층형 retrieval(H-RAG류)로 “child 검색 + parent 문맥 복원” 패턴을 정식으로 가져가기 ([arxiv.org](https://arxiv.org/abs/2605.00631?utm_source=openai))  
- “Late chunking(Embed full doc then chunk)”은 long-context embedding이 가능한 환경에서 강력한 대안이 될 수 있으니, 인프라 여건이 되면 비교 실험 권장 ([arxiv.org](https://arxiv.org/abs/2409.04701?utm_source=openai))