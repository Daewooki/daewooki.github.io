---
title: "RAG 성능을 좌우하는 Chunking 전략: 2026년 8월 기준 “Overlap vs Semantic Chunking” 실전 선택 가이드"
date: 2026-08-21 01:46:57 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-08]
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
RAG에서 “검색이 잘 안 된다”는 문제의 상당수는 Retriever나 Embedding이 아니라 **document splitting(=chunking)에서 이미 결정**됩니다. 질문에 필요한 근거가 (1) 잘려 나가거나, (2) 너무 많은 문맥에 묻히거나, (3) 표/섹션 구조가 깨지면, 이후에 rerank/prompt를 아무리 튜닝해도 비용만 늘고 정답률은 잘 안 오릅니다.

언제 쓰면 좋나?
- 사내 위키/매뉴얼/정책/기술 문서처럼 **heading/section 구조가 있는 코퍼스**
- “특정 조건/예외/표의 수치” 같은 **정밀 QA**가 필요할 때
- PDF → text/markdown 변환을 거치며 **레이아웃/표 구조가 흔들리는** 파이프라인

언제 쓰면 안 되나?
- 코퍼스가 매우 짧고(예: 각 문서가 1~2문단) 질문도 단순한 경우: 과한 chunking은 오히려 중복 인덱싱만 만듭니다.
- 다이어그램/도면(P&ID 등)처럼 정보가 시각적/공간적으로 인코딩된 문서: 텍스트 chunking만으로 한계가 크며 multimodal 접근이 필요합니다. ([arxiv.org](https://arxiv.org/abs/2603.24556))

---

## 🔧 핵심 개념
### 1) Chunking을 “split”과 “chunk assembly”로 분리해서 생각하기
2026년 실무 관점에서 가장 유용한 프레임은 다음 3단계입니다(특히 overlap/semantic을 섞어 쓸 때 중요).

1. **Document splitting**: 어디를 “끊을지” 결정  
   - content-independent: token/char/sentence/paragraph 기반  
   - content-dependent: speaker turn(콜 transcript), 섹션 경계, 코드 블록/표 경계 등  
   Cohere의 가이드도 이 분리를 명시하고, transcript처럼 구조를 보존해야 하는 경우 content-dependent split이 유리하다고 설명합니다. ([docs.cohere.com](https://docs.cohere.com/page/chunking-strategies))

2. **Chunk assembly**: split 조각들을 “얼마나 묶어서” 최종 chunk로 만들지(=chunk size 정책)
   - 작은 chunk: retrieval precision↑, 문맥↓
   - 큰 chunk: 문맥↑, retrieval dilution↑  
   Hugging Face cookbook도 “너무 작으면 아이디어가 잘리고, 너무 크면 의미가 희석된다”고 정리합니다. ([huggingface.co](https://huggingface.co/learn/cookbook/advanced_rag))

3. **Overlap**: 끊긴 경계의 손실을 “중복”으로 복구  
   - 장점: 경계에서 핵심 문장/근거가 반으로 잘리는 리스크 완화
   - 단점: 인덱스 중복(비용/저장/latency) + 상위 K 결과가 유사 chunk로 도배될 위험 ([docs.cohere.com](https://docs.cohere.com/page/chunking-strategies))

### 2) Overlap vs Semantic chunking의 구조적 차이
#### Overlap(슬라이딩/윈도우) 기반
- **원리**: “문서 의미를 이해하지 않고도” 경계 손실을 낮추는 확률적 안전장치
- **흐름**: (문장/문단/토큰) 단위로 자른 뒤, 인접 chunk에 N 토큰(또는 문자)을 겹치게 함
- **강점**: 구현 단순, 일관된 latency, 파라미터 튜닝이 비교적 직관적
- **약점**: 중복이 곧 비용. 그리고 동일 문맥이 여러 chunk에 들어가 rerank를 어렵게 할 수 있음

#### Semantic chunking(브레이크포인트/embedding 기반)
- **원리**: “의미가 바뀌는 지점”을 경계로 잡아 chunk cohesion을 높임
- **흐름(대표적 패턴)**  
  1) 문서 → 문장(또는 문단) 리스트  
  2) 각 단위 임베딩 계산  
  3) 인접 유사도가 임계치 아래로 떨어지는 지점을 breakpoint로 설정  
  4) breakpoint 사이를 chunk로 묶고, 최대 길이 초과 시 추가 분할  
- **강점**: chunk 내부 응집도가 좋아져 retrieval 시 “필요한 근거가 한 덩어리로” 들어올 확률↑
- **약점**: 임베딩 비용/시간 + 임계치 튜닝이 도메인 의존적. 표/코드/레이아웃 문서는 오히려 구조 기반이 더 낫기도 함(아래 참고).

### 3) 2026년 트렌드: “한 가지 chunker”가 아니라 “문서별 선택(Adaptive)”
2026년 논문 흐름에서 눈에 띄는 건 **Adaptive Chunking**입니다. 핵심은 “어떤 chunker가 최고냐”가 아니라, 문서의 특징(구조/참조/블록 무결성 등)에 따라 **문서별로 chunking 전략을 고르는 것**. intrinsic metric(RC, ICC, DCC, BI, SC)을 정의해 chunk 품질을 직접 평가하고, 모델/프롬프트를 바꾸지 않고도 정답률을 올렸다고 보고합니다. ([arxiv.org](https://arxiv.org/abs/2603.25333))

또한 2026년 산업 문서(오일&가스) 평가에서는 **structure-aware chunking이 semantic이나 baseline 대비 top-K retrieval에서 유리하고 비용도 낮았다**고 보고합니다. 특히 표/도면류는 텍스트-only RAG의 한계를 분명히 지적합니다. ([arxiv.org](https://arxiv.org/abs/2603.24556))  
PDF 파싱/변환 쪽에서도 “hierarchical splitting + metadata enrichment”가 정확도에 크게 기여한다는 결과가 반복됩니다. ([arxiv.org](https://arxiv.org/abs/2604.04948?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “실무에서 흔한” **Markdown/정책 문서(heading 구조 + 표/코드 블록 혼재)**를 대상으로,
1) 구조 기반(heading/코드블록 보호) 1차 split  
2) 섹션 내부에서 semantic chunking(문장 임베딩) 2차 split  
3) 마지막에 소량 overlap을 옵션으로 주는 **하이브리드 ingestion** 파이프라인입니다.

- Vector DB: FAISS (로컬에서 재현 쉬움)
- Embedding: sentence-transformers (로컬/온프레 가정)
- Retriever는 BM25+Vector 하이브리드까지 가면 더 좋지만, 여기서는 chunking에 집중합니다.

### 0) 의존성/실행
```bash
python -m venv .venv
source .venv/bin/activate

pip install -U faiss-cpu sentence-transformers numpy regex rank-bm25
```

### 1) 구조 보존 + semantic chunking + (선택) overlap
```python
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple, Iterable, Optional

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer


# --------- 데이터 모델 ---------
@dataclass
class Chunk:
    chunk_id: str
    text: str
    meta: Dict


# --------- 유틸: 코드블록 보호 + heading 기반 섹션 분해 ---------
CODE_FENCE_RE = re.compile(r"```.*?\n.*?\n```", re.DOTALL)

def split_markdown_by_headings(md: str) -> List[Tuple[str, str]]:
    """
    returns list of (section_path, section_text)
    - code fences는 통째로 보존(중간 분해 방지)
    - heading(#..######) 기준으로 섹션을 쪼갬
    """
    # 1) code fence를 placeholder로 치환
    fences = []
    def _stash(m):
        fences.append(m.group(0))
        return f"__CODE_FENCE_{len(fences)-1}__"
    protected = CODE_FENCE_RE.sub(_stash, md)

    # 2) heading split
    lines = protected.splitlines()
    sections = []
    cur_title = "ROOT"
    buf = []

    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
    for line in lines:
        m = heading_re.match(line)
        if m:
            # flush
            if buf:
                sections.append((cur_title, "\n".join(buf).strip()))
                buf = []
            level = len(m.group(1))
            title = m.group(2).strip()
            cur_title = f"{'#'*level} {title}"
        buf.append(line)

    if buf:
        sections.append((cur_title, "\n".join(buf).strip()))

    # 3) placeholder 복원
    def _restore(text: str) -> str:
        for i, fence in enumerate(fences):
            text = text.replace(f"__CODE_FENCE_{i}__", fence)
        return text

    return [(title, _restore(text)) for title, text in sections if text]


# --------- 유틸: 문장 단위 분해(간단 버전) ---------
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

def to_sentences(text: str) -> List[str]:
    sents = [s.strip() for s in SENT_SPLIT_RE.split(text) if s.strip()]
    # 너무 짧은 조각은 앞에 붙이는 등 후처리 가능(실무에서는 권장)
    return sents


# --------- Semantic chunking (breakpoint based) ---------
def semantic_chunk_sentences(
    sentences: List[str],
    embed: SentenceTransformer,
    max_chars: int = 1800,
    breakpoint_sim: float = 0.75,   # 낮을수록 더 잘게 쪼개짐(도메인 튜닝 필요)
) -> List[str]:
    if not sentences:
        return []

    embs = embed.encode(sentences, normalize_embeddings=True, batch_size=64)
    # 인접 cosine similarity
    sims = (embs[:-1] * embs[1:]).sum(axis=1)

    chunks = []
    cur = [sentences[0]]

    def cur_len():
        return sum(len(x) for x in cur) + max(0, len(cur)-1)

    for i in range(1, len(sentences)):
        # 규칙 1: 의미가 크게 바뀌는 지점이면 끊기
        if sims[i-1] < breakpoint_sim:
            chunks.append(" ".join(cur).strip())
            cur = [sentences[i]]
            continue

        # 규칙 2: 길이 제한
        if cur_len() + 1 + len(sentences[i]) > max_chars:
            chunks.append(" ".join(cur).strip())
            cur = [sentences[i]]
            continue

        cur.append(sentences[i])

    if cur:
        chunks.append(" ".join(cur).strip())

    return [c for c in chunks if c]


# --------- Overlap (선택): chunk 경계 완충 ---------
def apply_overlap(chunks: List[str], overlap_chars: int = 200) -> List[str]:
    if overlap_chars <= 0 or len(chunks) <= 1:
        return chunks

    out = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i-1]
        cur = chunks[i]
        prefix = prev[-overlap_chars:] if len(prev) > overlap_chars else prev
        out.append((prefix + "\n" + cur).strip())
    return out


# --------- 인덱싱: FAISS ---------
class FaissIndex:
    def __init__(self, embed: SentenceTransformer):
        self.embed = embed
        self.index = None
        self.chunks: List[Chunk] = []

    def add(self, chunks: List[Chunk]):
        vecs = self.embed.encode([c.text for c in chunks], normalize_embeddings=True)
        vecs = np.asarray(vecs, dtype="float32")

        if self.index is None:
            dim = vecs.shape[1]
            self.index = faiss.IndexFlatIP(dim)  # cosine ~ inner product (normalized)
        self.index.add(vecs)
        self.chunks.extend(chunks)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Chunk, float]]:
        qv = self.embed.encode([query], normalize_embeddings=True).astype("float32")
        scores, ids = self.index.search(qv, top_k)
        results = []
        for idx, score in zip(ids[0], scores[0]):
            if idx == -1:
                continue
            results.append((self.chunks[idx], float(score)))
        return results


# --------- 현실적 시나리오: 정책/런북 문서 ingest ---------
def ingest_markdown_docs(docs: List[Tuple[str, str]]) -> List[Chunk]:
    """
    docs: list of (doc_id, markdown_text)
    """
    embed = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    all_chunks: List[Chunk] = []
    for doc_id, md in docs:
        sections = split_markdown_by_headings(md)

        for sec_i, (sec_title, sec_text) in enumerate(sections):
            sents = to_sentences(sec_text)

            sem_chunks = semantic_chunk_sentences(
                sents,
                embed=embed,
                max_chars=1800,
                breakpoint_sim=0.75,
            )

            # overlap은 "조금만" (semantic chunking에서도 경계 손실은 생김)
            final_chunks = apply_overlap(sem_chunks, overlap_chars=180)

            for j, ch in enumerate(final_chunks):
                all_chunks.append(
                    Chunk(
                        chunk_id=f"{doc_id}::sec{sec_i}::ch{j}",
                        text=ch,
                        meta={
                            "doc_id": doc_id,
                            "section": sec_title,
                            "sec_index": sec_i,
                            "chunk_index": j,
                        },
                    )
                )
    return all_chunks


if __name__ == "__main__":
    # 예시: SRE 런북 + 보안 정책 같은 “현실 문서”를 가정(텍스트는 짧게 축약)
    runbook = """
# Incident Runbook

## Mitigation steps
If error rate increases above 5% for 10 minutes, do:
1. Check deploy history
2. Rollback if needed
3. Verify DB connections

## Rollback procedure
```bash
kubectl rollout undo deploy/api -n prod
kubectl rollout status deploy/api -n prod
```

## Postmortem template
Write: timeline, impact, root cause, actions.
"""

    policy = """
# Security Policy

## Password requirements
Minimum length is 14 characters. Disallow common passwords.
Rotate privileged credentials every 90 days.

## Exception process
Exceptions require approval from Security and are time-boxed.
"""

    chunks = ingest_markdown_docs([
        ("runbook.md", runbook),
        ("security_policy.md", policy),
    ])

    embed = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    ix = FaissIndex(embed)
    ix.add(chunks)

    query = "kubectl로 롤백하는 방법이 뭐야?"
    results = ix.search(query, top_k=3)

    print("=== Top hits ===")
    for c, s in results:
        print(f"\nscore={s:.3f} id={c.chunk_id} section={c.meta['section']}")
        print(c.text[:400])
```

### 예상 출력(예)
- “Rollback procedure” 섹션(코드블록 포함) chunk가 1~2순위로 뜨고,
- overlap 덕분에 바로 앞 문장(맥락)까지 일부 같이 들어오는 형태가 됩니다.

이 파이프라인이 실무적으로 중요한 이유:
- Hugging Face가 말한 것처럼 recursive/구조 보존이 문서 전체 구조를 유지하는 데 유리하고 ([huggingface.co](https://huggingface.co/learn/cookbook/advanced_rag))
- Cohere가 강조한 overlap의 “경계 완충”을 과도한 중복 없이 최소로만 적용하며 ([docs.cohere.com](https://docs.cohere.com/page/chunking-strategies))
- 최근 연구들이 반복해서 보여주는 “structure-aware가 종종 semantic보다 싸고 잘 먹힌다”는 결과를 반영하기 때문입니다. ([arxiv.org](https://arxiv.org/abs/2603.24556))

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 적용 가능)
1) **heading path / metadata를 chunk에 넣어라**
- “섹션 제목 + 문서 경로”는 retrieval precision을 올리는 가장 싼 방법입니다.
- PDF→Markdown 파이프라인 평가에서도 hierarchical splitting과 metadata enrichment가 정확도에 크게 기여한다고 보고됩니다. ([arxiv.org](https://arxiv.org/abs/2604.04948?utm_source=openai))

2) **semantic chunking은 ‘전체 문서’가 아니라 ‘구조로 잘라낸 섹션 내부’에서만**
- 전체 문서에 semantic을 돌리면 비용이 크고, 표/코드/목차 등 잡음이 breakpoint를 오염시킵니다.
- 먼저 structure-aware split → 그 내부에서 semantic은 “미세 조정” 역할이 가장 안정적입니다(실무 체감 + 최근 구조 기반 우세 결과와도 부합). ([arxiv.org](https://arxiv.org/abs/2603.24556))

3) **Overlap은 기본값이 아니라 “보험료”로 취급**
- overlap은 중복 인덱싱 비용을 영구히 발생시키므로 “필요 최소”로.
- 특히 semantic chunking까지 쓰면 overlap을 크게 줄이거나(예: 10% 미만) 아예 꺼도 되는 케이스가 많습니다. ([docs.cohere.com](https://docs.cohere.com/page/chunking-strategies))

### 흔한 함정 / 안티패턴
- **고정 token chunk + 큰 overlap만으로 모든 문서를 해결하려는 접근**: 빠르게 만들 수는 있지만, 섹션/표/코드 경계를 무시하면 top-K가 “비슷한 중복 chunk”로 채워져 실제 근거가 묻힙니다.
- **semantic chunking 임계치(breakpoint_sim)를 한 번 정하고 영원히 고정**: 도메인/문체가 바뀌면 바로 성능이 흔들립니다. 2026년에는 문서별 전략 선택(Adaptive)이 유효하다는 근거가 쌓이는 중입니다. ([arxiv.org](https://arxiv.org/abs/2603.25333))
- **시각적 문서(P&ID/복잡한 표)를 텍스트로만 해결하려 함**: 연구에서도 순수 텍스트 chunking은 한계가 명확합니다. ([arxiv.org](https://arxiv.org/abs/2603.24556))

### 비용/성능/안정성 트레이드오프(의사결정 기준)
- 비용이 가장 큰 축: **semantic chunking(임베딩 비용) + overlap(저장/검색 중복)**
- 안정성이 높은 축: **structure-aware split(heading/문단/코드블록 보호)**
- 권장 우선순위(대부분의 팀에 맞음):
  1) 구조 기반 split + metadata
  2) chunk size 재조정(Reader context window 고려)
  3) overlap 최소 적용
  4) 그래도 부족하면 섹션 내부 semantic chunking
  5) 코퍼스가 다양한 대규모면 Adaptive(문서별 선택)로 확장 ([arxiv.org](https://arxiv.org/abs/2603.25333))

---

## 🚀 마무리
2026년 8월 기준 chunking의 결론은 “semantic이냐 overlap이냐”의 이분법이 아니라, **구조 보존(structure-aware) → 필요 시 semantic → overlap은 최소 보험**의 레이어드 전략입니다. 최근 연구/가이드에서도 구조 보존과 문서별 전략 선택(Adaptive), 그리고 overlap의 장단점(완충 vs 중복)이 반복해서 강조됩니다. ([arxiv.org](https://arxiv.org/abs/2603.24556))

도입 판단 기준(빠른 체크리스트):
- 문서에 heading/섹션이 있다 → structure-aware 먼저
- 질문이 “정의/조건/예외/표 수치” 중심이다 → semantic(섹션 내부) 고려
- “근거가 반쯤 잘린다” 이슈가 있다 → overlap을 최소로만 추가
- 문서 타입이 다양하고 한 전략이 자주 깨진다 → Adaptive chunking(문서별 선택) 실험 ([arxiv.org](https://arxiv.org/abs/2603.25333))

다음 학습 추천:
- chunk 품질을 intrinsic metric으로 평가하고 문서별로 chunker를 고르는 Adaptive Chunking 흐름 ([arxiv.org](https://arxiv.org/abs/2603.25333))
- PDF → Markdown 변환과 hierarchical splitting/metadata enrichment가 QA 정확도에 미치는 영향(“chunking 이전 단계”까지 포함) ([arxiv.org](https://arxiv.org/abs/2604.04948?utm_source=openai))