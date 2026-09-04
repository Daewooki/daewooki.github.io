---
title: "문서 청킹(Chunking)으로 RAG 성능을 2배 올리는 법: 2026년 기준 Overlap vs Semantic Chunking 실전 분해 전략"
description: "RAG에서 “검색이 약하다”는 증상은 대개 retriever나 embedding 모델 문제가 아니라 문서를 어떤 단위로 쪼개서(indexing) ‘검색 가능한 최소 증거 단위’로 만들었는지에서 시작합니다."
date: 2026-07-30 02:54:58 +0900
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
RAG에서 “검색이 약하다”는 증상은 대개 retriever나 embedding 모델 문제가 아니라 **문서를 어떤 단위로 쪼개서(indexing) ‘검색 가능한 최소 증거 단위’로 만들었는지**에서 시작합니다. 청킹이 잘못되면 (1) 답이 경계에서 찢겨 나가거나, (2) 너무 큰 덩어리 안에 답이 희석되거나, (3) overlap 과다로 중복 chunk가 상위 k를 점령해 **다양성(diversity)이 무너져** 사실상 recall이 떨어집니다.[^1]

언제 쓰면 좋나:
- 정책/가이드/계약/기술문서처럼 “정답 근거가 문장/조항/절 단위”로 존재하는 문서
- PDF/HTML/Markdown 등 구조가 있고, heading/리스트/테이블이 의미를 갖는 문서
- 운영 중 “답은 문서에 있는데 못 찾는다(저회수 low-recall)” 류 이슈가 많은 경우[^1]

언제 쓰면 안 되나(혹은 우선순위 낮나):
- 문서 품질(추출, OCR, heading 인식)이 심각하게 깨진 파이프라인: 이 경우 chunking을 고도화해도 오염된 입력이 그대로 전파됩니다(구조 기반 청킹은 특히 더). 먼저 extraction/정규화가 1순위입니다(실무 커뮤니티에서도 반복되는 결론).[^2]
- 문서/질의가 매우 짧아 chunking 자체가 큰 변수가 아닌 경우

---

## 🔧 핵심 개념
### 1) “정답 근거 단위(answer-bearing unit)”를 보존하는 게 목표
좋은 chunking의 정의는 “예쁜 길이로 자르기”가 아니라, **질의가 요구하는 근거가 한 chunk 안에서 온전히 재구성**되도록 하는 겁니다. OptyxStack이 강조하듯 chunking은 ingestion 디테일이 아니라 **recall 레버**입니다.[^1]

### 2) Overlap의 작동 원리: 경계 손상(boundary damage) 완화 vs 중복 폭발
Overlap은 “경계에서 문장/조항이 잘리는 문제”를 완화합니다. 하지만 overlap이 커질수록:
- 동일 내용이 다수 chunk에 복제 → 벡터스토어 저장/임베딩 비용 증가
- top-k가 중복 chunk로 채워져 **context precision**(LLM에게 주는 근거의 밀도) 하락
- reranker가 있더라도 후보 다양성이 줄어드는 문제가 남음[^1]

따라서 overlap은 “보험”이지 “해결책”이 아닙니다. 기본은 **경계 자체를 의미 단위로 맞추는 것**이고, overlap은 그 다음입니다.

### 3) Semantic chunking의 작동 방식(임베딩 기반 문장 그룹핑)
Semantic chunking은 “문장을 나열”한 뒤, 인접 문장 그룹 간 의미 변화 지점(breakpoint)을 찾아 덩어리를 만듭니다. 예를 들어 LlamaIndex의 `SemanticSplitterNodeParser`는:
- sentence splitter로 문장을 자르고
- 문장 buffer(여러 문장을 합친 combined_sentence)를 만들어 임베딩을 구한 뒤
- 인접 그룹 간 distance를 계산하고
- distance 분포에서 percentile threshold를 넘어서는 지점을 breakpoint로 삼아 chunk를 만듭니다(“percentile breakpoints”).[^3]

장점: 문서가 “주제 전환”을 자주 가지는 경우, 고정 길이보다 응집도가 좋아질 수 있음  
단점: 임베딩 호출이 늘고(문장 그룹 단위), threshold/버퍼 크기 튜닝이 필요하며, **항상 더 낫지 않습니다**(문서 구조/질의 유형에 따라 고정 청킹이 더 안정적인 케이스도 흔함).[^4]

### 4) 2026년에 중요한 변화: “한 가지 전략”이 아니라 “문서별 적응”
2026년 연구인 *Adaptive Chunking*은 “one-size-fits-all chunking”의 한계를 정면으로 다루며, 문서별로 최적 chunking을 선택하는 프레임워크를 제안합니다. 핵심은 downstream 정답률만 보지 말고, chunk 자체 품질을 재는 **intrinsic metric**(예: Intrachunk Cohesion, Block Integrity 등)을 도입해 전략을 고른다는 것.[^5]  
이 방향성은 실무적으로도 납득이 갑니다. PDF 매뉴얼/법률/FAQ/로그/위키는 “정답 단위”가 서로 달라서, 동일 chunk_size/overlap로는 최적화가 안 됩니다.

### 5) (보너스) Late chunking: “chunk를 먼저 자르지 말고, 문서 전체 컨텍스트로 임베딩한 뒤 나중에 자르자”
Late chunking은 긴 컨텍스트 임베딩 모델을 활용해 문서 전체 토큰을 먼저 인코딩하고, mean pooling 직전에 chunk를 적용해 **chunk 임베딩이 문서 전체 문맥을 반영**하도록 합니다. 전통적 “먼저 자르고 각각 임베딩” 방식의 컨텍스트 손실을 줄이는 접근입니다.[^6]  
다만 이 글의 초점은 splitting 전략이므로, “가능하면 고려할 옵션” 정도로만 두겠습니다(인프라/모델 제약이 큼).

---

## 💻 실전 코드
아래 예제는 “회사 내부 기술문서(Markdown/HTML 섞임) + 제품 정책/에러 트러블슈팅”을 가정합니다. 목표는:
1) **구조 기반 분할(heading 우선)**
2) heading 블록이 너무 길면 **Recursive split + 소량 overlap**
3) 구조 추출이 불안정하거나 heading이 없는 텍스트는 **Semantic chunking으로 fallback**
4) 운영에서 전략 비교가 가능하도록 chunk 메타데이터에 `strategy`, `section_path`를 남김

### 0) 설치
```bash
pip install llama-index-core llama-index-embeddings-openai langchain-text-splitters tiktoken
```

### 1) 문서 로드 + 구조 기반(Heading) 1차 분할 + Recursive 2차 분할
```python
import re
from dataclasses import dataclass
from typing import List, Dict, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.embeddings.openai import OpenAIEmbedding  # 예: OpenAI 임베딩 사용

@dataclass
class Chunk:
    text: str
    metadata: Dict

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

def split_by_markdown_headings(md: str) -> List[Chunk]:
    """Markdown heading 기준으로 섹션 블록을 만들고, section_path를 메타데이터로 남긴다."""
    matches = list(HEADING_RE.finditer(md))
    if not matches:
        return [Chunk(md, {"strategy": "no_heading"})]

    sections = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i + 1 < len(matches) else len(md)
        level = len(m.group(1))
        title = m.group(2).strip()
        block = md[start:end].strip()
        sections.append(Chunk(block, {"strategy": "heading", "heading_level": level, "heading_title": title}))
    return sections

def recursive_refine(chunks: List[Chunk], chunk_size: int, overlap: int) -> List[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", " ", ""],  # 문단/줄/공백 우선
    )
    out = []
    for c in chunks:
        # heading 블록이 너무 길 때만 refine
        if len(c.text) <= chunk_size:
            out.append(c)
            continue
        parts = splitter.split_text(c.text)
        for j, p in enumerate(parts):
            md = dict(c.metadata)
            md.update({"strategy": md["strategy"] + "+recursive", "part": j})
            out.append(Chunk(p, md))
    return out

def build_chunks(md_text: str) -> List[Chunk]:
    # 1차: heading
    base = split_by_markdown_headings(md_text)

    # 현실적인 기본값: 700~1200 tokens 범위를 많이 쓰지만,
    # 여기서는 "문서 문자 길이" 기반 예시로 chunk_size를 잡고(운영에선 tokenizer 기준 권장)
    refined = recursive_refine(base, chunk_size=3500, overlap=350)  # overlap은 과도하게 키우지 않기
    return refined
```

**예상 출력(메타데이터 예시)**  
- `strategy`: `heading+recursive`  
- `heading_title`: “Rate Limits”  
- `part`: 0,1,2…

> 포인트: overlap을 “기본값”으로 크게 두기보다, **heading/문단 경계를 최대한 살리고 부족한 부분만 overlap**으로 메웁니다. (중복으로 top-k가 오염되는 걸 방지)[^1]

### 2) Semantic chunking fallback (구조가 없는 텍스트/깨진 PDF 추출물)
```python
from llama_index.core.schema import Document

def semantic_fallback(raw_text: str) -> List[Chunk]:
    embed_model = OpenAIEmbedding(model="text-embedding-3-large")  # 예시
    parser = SemanticSplitterNodeParser(
        embed_model=embed_model,
        buffer_size=3,  # 인접 문장 몇 개를 묶어 의미 변화 탐지 (문서 성격에 따라 튜닝)
        breakpoint_percentile_threshold=95,  # 높일수록 덩어리가 커지고, 낮추면 더 잘게 쪼개짐
    )
    docs = [Document(text=raw_text, metadata={"source": "fallback"})]
    nodes = parser.get_nodes_from_documents(docs)
    return [Chunk(n.text, {"strategy": "semantic", **(n.metadata or {})}) for n in nodes]
```

> LlamaIndex 구현은 “문장 그룹 임베딩 → 인접 거리(distance) 계산 → percentile 기반 breakpoint”로 chunk를 구성합니다. 즉, semantic chunking은 **경계가 데이터 분포(거리) 기반**이라서 문서 종류가 바뀌면 threshold가 같이 흔들릴 수 있습니다.[^3]

### 3) 운영용 라우팅: “구조 신뢰도”로 전략 선택
```python
def choose_strategy(text: str) -> str:
    # 아주 단순한 휴리스틱 예시(운영에선 더 정교하게):
    # - heading이 충분히 있고, heading 간 평균 블록 길이가 안정적이면 구조 기반
    # - 아니면 semantic fallback
    heading_count = len(list(HEADING_RE.finditer(text)))
    if heading_count >= 3:
        return "heading"
    return "semantic"

def chunk_document(text: str) -> List[Chunk]:
    strategy = choose_strategy(text)
    if strategy == "heading":
        return build_chunks(text)
    else:
        return semantic_fallback(text)
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “Overlap은 2차 수단” + 중복으로 top-k를 망치지 말기
Overlap은 경계 문제를 줄이지만, 과하면 중복 chunk가 상위 결과를 잠식해 precision/다양성을 떨어뜨립니다. 운영에서는 **retrieved chunk의 중복률(near-duplicate ratio)** 을 꼭 모니터링하세요.[^1]

### Best Practice 2) “문서 구조”가 있는 도메인은 구조를 먼저 먹여라
정책/가이드/API 문서/테이블/절차형 문서는 구조를 살리면 recall이 크게 오르는 경우가 많습니다. 고정 토큰 윈도우로 자르면 “규칙/조건/예외”가 서로 다른 chunk로 흩어져 근거가 약해집니다.[^1]

### Best Practice 3) 문서별로 전략을 다르게(Adaptive mindset)
2026년 *Adaptive Chunking*이 주장하듯, chunking은 평가 프레임워크 없이 “감”으로 고르면 끝이 없습니다. 최소한 문서군(cohort)별로:
- 구조 기반 vs recursive+overlap vs semantic
- chunk_size 후보 2~3개
를 놓고 오프라인 eval(정답 span 포함 gold set)로 비교하세요.[^5]

### 흔한 함정 1) “Semantic chunking이면 overlap 필요 없다”는 착각
Semantic chunking도 완벽하지 않습니다. 의미 변화 탐지가 실패하면 중요한 한 문장이 경계에 걸릴 수 있고, 질의는 “의미 덩어리”가 아니라 “조항/수치/파라미터” 같은 딱딱한 단위를 요구할 수 있습니다. 커뮤니티에서도 semantic이 항상 우월하지 않다는 경험담이 반복됩니다.[^4]

### 흔한 함정 2) Chunking 고도화 전에 extraction 품질을 무시
깨진 PDF에서 heading 인식이 틀리면 “heading 기반 청킹”은 그 오류를 증폭합니다. 먼저 텍스트 정규화(줄바꿈/하이픈 제거), 표/각주 처리, heading 신뢰도 점검을 하세요.[^2]

### 비용/성능 트레이드오프 요약
- Overlap 증가: 임베딩/저장/검색 비용 ↑, 중복으로 top-k 품질 ↓ 가능[^1]  
- Semantic chunking: 임베딩 호출(문장 그룹) ↑, 튜닝 비용 ↑, 하지만 문서가 “주제 전환형”이면 응집도 개선 여지[^3]  
- Late chunking: 품질 잠재력 ↑(컨텍스트 보존) 하지만 long-context embedding/파이프라인 복잡도 ↑[^6]

---

## 🚀 마무리
핵심은 세 가지입니다.

1) Chunking은 “텍스트를 잘게 자르기”가 아니라 **검색 가능한 증거 단위를 설계**하는 일입니다.[^1]  
2) Overlap은 보험이지만, 과하면 중복이 검색 결과를 오염시킵니다.  
3) 2026년 기준 베스트 프랙티스는 “정답 하나”가 아니라 **문서군별로 전략을 달리하고, eval로 고르는 Adaptive 접근**입니다.[^5]

도입 판단 기준(실무 체크리스트):
- 내 도메인의 정답은 “문장/조항/절차 단계/테이블 row” 중 어디에 걸려 있나?
- 현재 실패 케이스는 “경계에서 찢김(→ overlap/경계 개선)”인가, “큰 덩어리에 희석(→ 더 작은 구조 단위/parent-child)”인가?
- 문서 구조 추출이 신뢰 가능한가? 아니면 semantic/fixed로 fallback해야 하나?[^2]

다음 학습 추천:
- LlamaIndex `SemanticSplitterNodeParser` 구현을 직접 읽고(buffer/percentile이 결과에 미치는 영향 체감)[^3]  
- *Late Chunking* 논문으로 “임베딩 단계에서의 컨텍스트 손실” 문제를 이해하고, 장문 문서에서의 대안을 검토[^6]  
- *Adaptive Chunking*처럼 “chunk 품질을 수치화해 선택”하는 관점으로, 팀 내 chunking 실험을 프로세스화[^5]

[^1]: <https://optyxstack.com/rag-reliability/rag-chunking-strategy-chunk-size-overlap-document-structure-recall>
[^2]: <https://www.reddit.com/r/Rag/comments/1uxwqsh/best_chunking_strategy_for_different_pdf/>
[^3]: <https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/node_parser/text/semantic_splitter.py>
[^4]: <https://www.reddit.com/r/Rag/comments/1tvrym3/semantic_chunking_isnt_always_better_than/>
[^5]: <https://arxiv.org/abs/2603.25333>
[^6]: <https://arxiv.org/abs/2409.04701>
