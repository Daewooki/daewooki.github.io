---
title: "RAG 성능을 2배로 끌어올리는 2026년형 Chunking 전략: Overlap을 “줄이고”, Semantic을 “구조화”하라"
date: 2026-07-07 04:05:48 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-07]
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
RAG에서 **chunking(document splitting)** 은 “대충 자르면 되는 전처리”가 아니라, 검색 품질(Recall/Precision)과 비용(embedding/index size), 그리고 답변의 근거성(groundedness)을 동시에 좌우하는 **핵심 설계 변수**입니다. 2026년 들어 “semantic chunking이 만능”이라는 분위기가 있었지만, 최근 분석/가이드/연구 흐름을 보면 결론은 더 현실적입니다: **문서 타입과 질의 패턴에 맞춘 하이브리드(구조 기반 + 의미 기반 + 필요 시 최소 overlap)** 가 가장 재현성이 좋습니다. ([optyxstack.com](https://optyxstack.com/rag-reliability/rag-chunking-strategy-chunk-size-overlap-document-structure-recall?utm_source=openai))

**언제 쓰면 좋은가**
- 사내 위키/정책/가이드/기술문서처럼 **heading 구조가 있고**, 섹션 단위로 의미 경계가 비교적 명확한 코퍼스
- PDF/HTML/Markdown 혼합, 표/캡션/코드블록 등 **“붙어 있어야 의미가 사는 블록”** 이 존재하는 문서 ([thread-transfer.com](https://thread-transfer.com/blog/2026-06-17-rag-document-chunking-best-practices/?utm_source=openai))
- “정확한 문장 근거”가 중요한 QA(법무/규정/보안/운영런북)

**언제 쓰면 안 되는가(혹은 신중해야 하는가)**
- 문서가 매우 짧거나(예: 수백 토큰), 애초에 retrieval 없이도 LLM context에 **통째로 넣는 게 더 싸고 안전한** 경우
- 검색이 아니라 “브라우징/요약”이 목적이라 top-k를 넓게 뽑아도 괜찮은 경우(과도한 chunk 최적화는 비용만 증가)
- semantic chunking을 무리하게 적용해 **전처리 비용이 과해지고**, 인덱싱 파이프라인이 불안정해지는 경우(특히 대규모 배치)

---

## 🔧 핵심 개념
### 1) Chunking의 목표를 “토큰 크기”가 아니라 “검색 단위의 의미 보존”으로 재정의
chunking은 단순히 *N tokens로 자르기*가 아니라,
1) **retriever가 찾기 쉬운 단위**로 나누고  
2) **LLM이 읽었을 때 자기완결적인 단위**를 만들며  
3) **중복/비용을 최소화**하는 작업입니다.

여기서 가장 큰 함정은, overlap을 늘려 “경계 손실”을 막으려다 **top-k 결과가 서로 거의 같은 chunk로 도배**되는 현상입니다. 이러면 다양성이 떨어져 답이 한쪽으로 치우치고, 인덱스/저장/임베딩 비용만 커집니다. ([thread-transfer.com](https://thread-transfer.com/blog/2026-06-17-rag-document-chunking-best-practices/?utm_source=openai))

### 2) 2026년 기준 chunking 전략 4종과 내부 흐름
실무에서 의미 있는 옵션은 보통 아래 4개로 수렴합니다. ([appscale.blog](https://appscale.blog/en/blog/document-chunking-architecture-rag-semantic-late-contextual-2026?utm_source=openai))

#### (A) Fixed/Recursive splitting (+ overlap)
- **흐름**: separators(문단/문장/공백/문자) → 목표 chunk size에 맞게 재귀적으로 쪼갬
- 장점: 빠르고 단순, 구현/운영 안정적
- 단점: heading/표/코드 경계를 “모른다” → 의미가 깨질 수 있음

#### (B) Structure-aware splitting (문서 구조 우선)
- **흐름**: Markdown heading, HTML tag, PDF 레이아웃/섹션 → 구조 단위로 먼저 그룹핑 → 그 내부에서 size 맞추기
- “문서의 저자가 의도한 의미 경계”를 존중하는 게 핵심
- LangChain의 MarkdownHeaderTextSplitter 같은 접근이 대표적입니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/splitters/markdown_header_metadata_splitter?utm_source=openai))

#### (C) Semantic chunking (topic shift 기준)
- **흐름**: 문장/단락 단위 후보 생성 → 임베딩/유사도/코사인 거리 등으로 **주제 변화 지점** 탐지 → 그 지점에서 자름
- 장점: 경계 품질이 좋아 overlap을 줄일 여지가 큼
- 단점: 전처리 비용 상승(임베딩/추가 모델 호출), 문서 타입에 따라 과분할/과병합 가능  
- LlamaIndex에도 semantic 기반 splitter가 API로 제공됩니다. ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/semantic_splitter/?trk=public_post_comment-text&utm_source=openai))

#### (D) Late chunking / Contextual(요약 컨텍스트 prepend)
- 최근 2026 가이드들에서 자주 언급되는 방향: “chunk 자체가 짧아도, **주변 문맥 요약을 앞에 붙여** 임베딩한다” 같은 contextual retrieval류 또는 “먼저 길게 임베딩하고 나중에 풀링/분할”류 late chunking ([aiworkflowlab.dev](https://aiworkflowlab.dev/article/rag-chunking-strategies-late-contextual-semantic-2026?utm_source=openai))  
- 다만 이건 인프라/모델 제약이 커서, 대부분 팀은 **(B)+(A) 또는 (B)+(C)** 로 먼저 이득을 봅니다.

### 3) Overlap에 대한 2026년식 관점: “기본값이 아니라 최후의 안전장치”
최근(2026) 분석에선 overlap이 **효과가 없거나 비용만 올리는 경우**가 적지 않다는 결과도 나옵니다. ([arxiv.org](https://arxiv.org/abs/2601.14123?utm_source=openai))  
실무적으로는 이렇게 정리하는 게 안전합니다.

- **구조/의미 경계가 잘 잡히면** overlap은 0~작게(예: 5~10%)도 충분
- **fixed/recursive 위주면** 경계 손실 방지용으로 10~20%가 여전히 출발점 ([reddit.com](https://www.reddit.com/r/LangChain/comments/1tskru6/spent_way_too_long_debugging_rag_before_realizing/?utm_source=openai))
- “overlap으로 해결”하려는 문제(캡션 분리, 표 제목 분리, 섹션 헤더 유실)는 대부분 **splitter가 구조를 모르기 때문에 생김** → overlap이 아니라 *structure-aware*가 정답 ([thread-transfer.com](https://thread-transfer.com/blog/2026-06-17-rag-document-chunking-best-practices/?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “사내 기술문서(Markdown) + 운영런북”을 가정합니다.

- 1단계: **Markdown heading 기반으로 1차 분리(구조 보존)**
- 2단계: 섹션 내부를 **Recursive splitting으로 목표 토큰 크기에 맞추기**
- 3단계: **overlap을 최소화**하되, 섹션 말미/코드블록 등 경계 위험 구간은 약간의 overlap 허용
- 4단계: chunk에 **metadata(heading path, source, section id)** 를 붙여 retrieval 후 re-ranking/필터링에 활용

> 의존성은 LangChain splitters 쪽을 사용합니다(문서화가 잘 되어 있고 파이프라인 구성도 쉬움). ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/splitters/markdown_header_metadata_splitter?utm_source=openai))

```bash
pip install langchain-text-splitters tiktoken
```

```python
import re
from dataclasses import dataclass
from typing import List, Dict, Any

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter


@dataclass
class Chunk:
    id: str
    text: str
    metadata: Dict[str, Any]


def normalize_whitespace(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def split_markdown_for_rag(
    md_text: str,
    source: str,
    *,
    target_chunk_chars: int = 2400,   # 대략 500~800 tokens 수준(문서/언어에 따라 다름)
    chunk_overlap_chars: int = 200,   # "기본값"이 아니라 안전장치
) -> List[Chunk]:
    md_text = normalize_whitespace(md_text)

    # 1) 구조 보존: heading 단위로 먼저 분리
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "h1"),
            ("##", "h2"),
            ("###", "h3"),
            ("####", "h4"),
        ],
        strip_headers=False,
    )
    header_docs = header_splitter.split_text(md_text)

    # 2) 섹션 내부 size 맞추기: recursive splitter
    #    - 실제로는 tiktoken 기반 token splitter가 더 정확하지만,
    #      운영에서는 chars 기반도 충분히 재현성 있게 동작하는 경우가 많습니다.
    body_splitter = RecursiveCharacterTextSplitter(
        chunk_size=target_chunk_chars,
        chunk_overlap=chunk_overlap_chars,
        separators=["\n\n", "\n", ". ", " ", ""],  # 문단/줄/문장/단어 순
    )

    chunks: List[Chunk] = []
    for i, d in enumerate(header_docs):
        section_text = normalize_whitespace(d.page_content)
        section_meta = dict(d.metadata or {})

        # heading path를 retrieval 디버깅에 쓰기 좋게 정리
        heading_path = " > ".join(
            [section_meta[k] for k in ["h1", "h2", "h3", "h4"] if k in section_meta]
        )

        # 3) 섹션이 너무 길면 추가 분할
        sub_texts = body_splitter.split_text(section_text)

        for j, t in enumerate(sub_texts):
            t = normalize_whitespace(t)
            chunk_id = f"{source}::sec{i:04d}::chunk{j:03d}"
            chunks.append(
                Chunk(
                    id=chunk_id,
                    text=t,
                    metadata={
                        "source": source,
                        "heading_path": heading_path,
                        "section_index": i,
                        "chunk_index": j,
                        # 나중에 필터링/스코어 조정용
                        "has_codeblock": "```" in t,
                        "approx_chars": len(t),
                    },
                )
            )

    return chunks


if __name__ == "__main__":
    # 현실적인 시나리오: 운영런북 일부(예시)
    md = """
# Payments Runbook

## Incident: Payment timeout spikes
Symptoms:
- p95 latency > 2s
- error rate > 1%

### Mitigation
1. Check upstream: gateway health
2. Reduce concurrency in worker pool
3. Verify DB connection pool saturation

```bash
kubectl -n payments get pods
kubectl -n payments logs deploy/api --since=10m | tail -n 200
```

### Root Cause Notes
Timeouts often correlate with downstream provider throttling.
If throttling confirmed, switch routing to provider B.

## Incident: Duplicate charges
When customers report duplicates, validate idempotency keys...
"""
    out = split_markdown_for_rag(md, source="runbook/payments.md")
    print(f"chunks={len(out)}")
    print(out[0].id, out[0].metadata)
    print(out[0].text[:200], "...")
```

**예상 출력(예시)**
- `chunks=3~6` (문서 길이에 따라 변동)
- 첫 chunk metadata에 `heading_path="Payments Runbook > Incident: Payment timeout spikes"` 형태로 들어가며,
- code block이 포함된 chunk는 `has_codeblock=True`

이 파이프라인의 포인트는 **overlap으로 의미를 보존하려고 애쓰기 전에, heading 구조를 보존**한다는 점입니다. heading이 살아 있으면 retriever가 “관련 섹션 전체”를 맞출 확률이 올라가고, 경계 손실을 overlap로 땜질할 필요가 줄어듭니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/splitters/markdown_header_metadata_splitter?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2-3개)
1) **Structure-first, size-second**
- Markdown/HTML/PDF는 “보이는 구조”가 존재합니다. 이를 무시하고 token window로만 자르면 표/캡션/리스트가 찢어져 retrieval이 급격히 나빠집니다. 특히 *캡션-표 본문 분리*는 전형적인 retrieval killer로 자주 보고됩니다. ([thread-transfer.com](https://thread-transfer.com/blog/2026-06-17-rag-document-chunking-best-practices/?utm_source=openai))

2) Overlap은 “정책”이 아니라 **진단 후 조정**
- overlap을 고정값으로 두지 말고, 다음 시그널을 보고 줄이거나 늘리세요.
  - top-k 결과가 같은 섹션/문단 변형으로만 채워진다 → overlap 과다 가능성 ([thread-transfer.com](https://thread-transfer.com/blog/2026-06-17-rag-document-chunking-best-practices/?utm_source=openai))
  - 답을 포함한 문장이 경계에서 잘린다(grounding이 끊김) → 경계가 잘못 잡힌 것(semantic/structure 개선) 또는 최소 overlap 필요

3) chunk에는 **retrieval 디버깅 가능한 metadata**를 남겨라
- `heading_path`, `source`, `section_index` 같은 값은 “왜 이 chunk가 뽑혔는지”를 추적하는 데 결정적입니다.
- 운영에서 chunking은 결국 “평가-수정-재색인” 루프이므로, 디버깅이 안 되면 개선이 멈춥니다.

### 흔한 함정/안티패턴
- **과도한 overlap으로 인덱스 팽창**: 임베딩 비용/저장 비용 증가 + 검색 다양성 저하(중복 chunk 상위 랭크) ([thread-transfer.com](https://thread-transfer.com/blog/2026-06-17-rag-document-chunking-best-practices/?utm_source=openai))
- semantic chunking을 도입했는데, 실제론 문서에 topic shift가 희미해서 **오히려 경계가 불안정**해지는 경우  
- “chunk size를 키우면 더 잘 맞겠지”로 2k~5k tokens 이상을 밀어붙이는 것: 최근 분석에서는 특정 구간 이후 품질이 꺾이는(문맥 절벽) 관찰도 보고됩니다. ([arxiv.org](https://arxiv.org/abs/2601.14123?utm_source=openai))

### 비용/성능/안정성 트레이드오프(현실 결론)
- **Recursive + small overlap**: 가장 싸고 단단함(운영 안정), 하지만 구조 파괴 위험
- **Structure-aware + Recursive(추천 기본형)**: 구현 난이도 대비 성능 향상 폭이 큼
- **Semantic chunking**: 전처리 비용 증가(임베딩/추가 모델) 대신 overlap을 줄이고 경계를 개선할 여지. 단, 문서 타입별 검증 필수 ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/semantic_splitter/?trk=public_post_comment-text&utm_source=openai))
- **Late/Contextual 계열**: 성능 잠재력은 크지만 파이프라인 복잡도/비용도 큼. 먼저 구조 기반을 다듬고 나서 도입하는 게 안전 ([aiworkflowlab.dev](https://aiworkflowlab.dev/article/rag-chunking-strategies-late-contextual-semantic-2026?utm_source=openai))

---

## 🚀 마무리
2026년 7월 기준으로 “정답 chunk size/overlap” 같은 단일 레시피는 점점 설득력을 잃고 있습니다. 대신 실무적으로 재현 가능한 결론은 이겁니다.

- **1순위**: 문서 구조를 보존(heading/표/캡션/코드 블록)하고, 그 안에서 size를 맞춰라 ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/splitters/markdown_header_metadata_splitter?utm_source=openai))  
- **2순위**: overlap은 기본값이 아니라 “경계 손실”에 대한 최소 안전장치로만 써라(중복 top-k가 보이면 즉시 줄여라) ([thread-transfer.com](https://thread-transfer.com/blog/2026-06-17-rag-document-chunking-best-practices/?utm_source=openai))  
- **3순위**: semantic chunking은 만능이 아니라 “경계 품질을 돈으로 사는 옵션”이다. 문서/질의 특성에 맞을 때만 도입하라 ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/semantic_splitter/?trk=public_post_comment-text&utm_source=openai))  

**도입 판단 기준(체크리스트)**
- 문서에 heading/섹션 구조가 있는가? → 있으면 structure-aware부터
- top-k 중복이 심한가? → overlap 줄이고, 구조/의미 경계 개선
- 답이 자주 경계에서 끊기는가? → semantic 또는 section-aware로 경계 자체를 바꿔라(“더 큰 overlap”은 마지막 수단)

**다음 학습 추천**
- LlamaIndex의 semantic/sentence window 계열 splitter 흐름을 훑고(semantic 경계 vs sentence window의 차이), ([docs.llamaindex.ai](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/semantic_splitter/?trk=public_post_comment-text&utm_source=openai))  
- LangChain의 MarkdownHeaderTextSplitter + Recursive 조합을 “표/캡션/코드블록 보존” 관점에서 확장해 보세요. ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/splitters/markdown_header_metadata_splitter?utm_source=openai))

원하시면, (1) 여러분 문서 샘플 2~3개 유형(정책문서/PDF/코드/표 포함)을 기준으로 (2) chunking 평가 지표(recall@k, chunk duplication rate, answerable span hit-rate)까지 포함한 “실험 설계 템플릿”도 같이 만들어드릴게요.