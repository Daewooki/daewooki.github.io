---
title: "2026년 7월, “OCR → Document AI → LLM 구조화 추출” 스택이 재정의됐다: 표·PDF를 프로덕션에 넣는 현실적인 기준"
date: 2026-07-24 03:27:38 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-07]
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
현업에서 문서 자동화가 막히는 지점은 “텍스트를 읽느냐”가 아니라, **(1) 레이아웃(heading/paragraph/reading order) 유지**, **(2) 표 구조(Table Structure Recognition) 재구성**, **(3) 최종 스키마에 맞춘 안정적인 structured extraction(JSON)**, 그리고 **(4) 추출 결과를 원문 좌표로 trace/backlink** 하는 “검증 가능성”입니다. 특히 스캔 PDF + 복잡한 표(merged cell, multi-line header, footnote) 조합은 여전히 실패율이 높고, LLM을 얹으면 “그럴듯한 JSON”이 나오지만 **근거(좌표/셀 출처)가 없는 hallucination**이 운영을 망칩니다(커뮤니티에서도 반복적으로 언급). ([reddit.com](https://www.reddit.com/r/computervision/comments/1t9nnba/why_is_pdf_table_extraction_still_hard_even_with/?utm_source=openai))

**언제 쓰면 좋은가**
- 대량 문서(수천~수만 페이지/일)에서 **표/폼/계약서/청구서**를 스키마로 적재해야 하고, 사람이 최종 검수하더라도 **검수 비용을 10x 줄이고 싶을 때**
- OCR 품질이 흔들리는 환경(스캔본, 워터마크, 도장/서명)에서 **layout + 표 + 키값**을 같이 뽑아야 할 때
- RAG 이전 단계로 **PDF → Markdown/구조화**가 필요하고, downstream QA 성능을 올리고 싶을 때(문서 변환 품질이 RAG 품질을 좌우한다는 평가 연구가 등장). ([arxiv.org](https://arxiv.org/abs/2604.04948?utm_source=openai))

**언제 쓰면 안 되는가**
- “정확히 정해진 템플릿”만 다루고 volume이 크지 않다면: 규칙 기반/템플릿 기반이 더 싸고 안정적
- 규제/감사 때문에 **좌표 기반 증빙**이 필수인데, 사용하는 LLM/툴이 provenance(값→셀/박스 연결)를 제공하지 않는다면: 먼저 **layout/table 모델** 쪽을 강화해야 함
- 비용 민감한 경우(특히 multi-page PDF를 VLM로 통째로 보내는 방식): OCR/레이아웃 단계에서 **chunking + 후보 영역 좁히기**가 선행돼야 함

---

## 🔧 핵심 개념
### 1) 2026년식 파이프라인: “Layout-first + LLM schema mapping”
최근 제품/문서에서 공통적으로 보이는 방향은 다음 3단 분해입니다.

1. **Layout Parse (문서 구조 복원)**  
   - 페이지를 block 단위(heading, paragraph, header/footer, table, figure 등)로 분해하고 reading order를 잡음  
   - Google Document AI의 **Gemini 기반 layout parser**는 OCR 모델 + Gemini를 결합해 “정밀한 구조화”를 강조합니다. ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai))  
   - Microsoft Document Intelligence는 layout 모델 출력에 대해 **Markdown 형태 출력** 및 좌표 정보를 제공하는 샘플들이 존재합니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?country=us&culture=en-us&view=doc-intel-3.1.0&utm_source=openai))  
   - Mistral OCR 4는 bounding box, block label, confidence 등을 전면에 내세웁니다. ([docs.mistral.ai](https://docs.mistral.ai/models/model-cards/ocr-4-0?utm_source=openai))

2. **Table Structure Recognition (TSR) / 표 재구성**
   - 표는 “텍스트”가 아니라 **격자 구조 + header 계층 + merged cell + footnote**의 조합
   - 흥미로운 포인트: 최신 연구 중에는 딥러닝 대신 **OpenCV 기반 휴리스틱 + OCR**로 고정밀 TSR을 만드는 접근(SPARTAN)이 소개됩니다. GPU 없이도 실무 품질을 얻고, 마지막에 LLM을 “스키마 매핑”에만 제한적으로 사용합니다. 이게 비용/설명가능성 측면에서 꽤 실전적입니다. ([nature.com](https://www.nature.com/articles/s41598-026-44325-7?utm_source=openai))  
   - AWS Textract도 표에서 merged cell, column header, summary cell 같은 메타를 직접 다루는 쪽으로 문서가 정리되어 있습니다(즉, “표는 별도 객체”로 취급). ([docs.aws.amazon.com](https://docs.aws.amazon.com/textract/latest/dg/how-it-works-tables.html?utm_source=openai))

3. **LLM Structured Extraction (스키마로의 안정적 매핑)**
   - LLM은 “문서 이해”에 강점이 있지만, 프로덕션에서 필요한 건 **엄격한 JSON schema + 재시도/검증 루프**입니다.
   - 2026년 문서 이해 서베이에서도 MLLM 기반 접근이 OCR-free/OCR-based로 갈리며, robustness와 hallucination, fine-grained perception이 핵심 과제로 정리됩니다. ([aclanthology.org](https://aclanthology.org/2026.findings-acl.652/?utm_source=openai))  
   - 결론적으로, 실무에서는 “LLM이 문서를 처음부터 끝까지 읽고 JSON 생성”보다는 **Layout/Tables에서 근거를 뽑고, LLM은 mapping/normalization에 집중**시키는 쪽이 안전합니다.

### 2) OCR-free vs OCR-based: 무엇이 다른가
- **OCR-based**: 먼저 텍스트/박스를 얻고, 그 위에서 entity extraction.  
  - 장점: 좌표/근거 연결이 쉽고, 오류 원인 분석이 가능
  - 단점: OCR 오류가 downstream으로 전파
- **OCR-free(혹은 VLM end-to-end)**: 이미지→바로 구조/텍스트 생성  
  - 장점: 복잡한 시각 단서(폰트, 선, 레이아웃)를 한 번에 반영 가능
  - 단점: “그럴듯한 생성”이 나오기 쉬워 검증/감사가 어렵고, 표의 provenance가 약해지기 쉬움(현업이 싫어하는 지점)

---

## 💻 실전 코드
아래 예제는 “스캔/비정형 PDF(표 포함)”를 **1) Layout/Table 파싱 → 2) LLM 스키마 매핑 → 3) 검증/재시도**로 구성합니다. 핵심은 **LLM에게 원문 전체를 주지 않고, layout parser가 뽑은 table/paragraph chunk만 주는 것**입니다.

시나리오: 공급업체가 보내는 월간 정산 PDF에서 `invoice_id`, `vendor_name`, `period`, `line_items(표)`를 추출해 DB 적재.

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate
pip install pydantic httpx tenacity python-dotenv
# (각 클라우드/벤더 SDK는 사용하는 서비스에 맞게 추가)
```

`.env`:
```bash
GOOGLE_PROJECT_ID=...
GOOGLE_LOCATION=...
GOOGLE_PROCESSOR_ID=...     # Document AI layout parser processor
OPENAI_API_KEY=...          # 스키마 매핑용 LLM (예시)
```

### 1) Layout/Table 파싱 (Google Document AI Layout Parser 예시)
Google은 복잡한 PDF에는 OCR parser 대신 **layout parser**를 권장하고, table annotation을 켤 수 있습니다. ([docs.cloud.google.com](https://docs.cloud.google.com/generative-ai-app-builder/docs/parse-chunk-documents?authuser=19&hl=en&utm_source=openai))  
(아래 코드는 “실행 가능한 형태”의 뼈대이며, 실제 호출 파라미터/SDK는 환경에 맞게 조정하세요.)

```python
# file: pipeline_extract.py
import os, json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel, Field, ValidationError

GOOGLE_PROJECT_ID = os.environ["GOOGLE_PROJECT_ID"]
GOOGLE_LOCATION = os.environ["GOOGLE_LOCATION"]
GOOGLE_PROCESSOR_ID = os.environ["GOOGLE_PROCESSOR_ID"]

PDF_PATH = "sample_settlement.pdf"

@dataclass
class Block:
    kind: str                # "paragraph" | "table" | ...
    text: str
    page: int
    bbox: Optional[Dict[str, Any]] = None
    table_html: Optional[str] = None   # 표는 가능한 한 구조(셀/행/열)를 유지한 형태로 보관

def call_layout_parser(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    실제로는 Google Document AI SDK를 권장.
    여기서는 'layout parser 결과 JSON을 얻는다'는 형태로 추상화.
    """
    raise NotImplementedError("Use Document AI SDK / REST for your environment")

def blocks_from_layout(doc: Dict[str, Any]) -> List[Block]:
    blocks: List[Block] = []

    # 포인트: LLM에게 원문 PDF를 통째로 주지 말고,
    # layout 단계에서 paragraph/table 단위로 '증거 조각'을 만든다.
    for page_idx, page in enumerate(doc.get("pages", []), start=1):
        # paragraphs
        for p in page.get("paragraphs", []):
            blocks.append(Block(
                kind="paragraph",
                text=p.get("text", "").strip(),
                page=page_idx,
                bbox=p.get("bbox"),
            ))

        # tables (가능하면 table을 HTML/CSV/Markdown 등으로 직렬화)
        for t in page.get("tables", []):
            blocks.append(Block(
                kind="table",
                text=t.get("text", "").strip(),
                page=page_idx,
                bbox=t.get("bbox"),
                table_html=t.get("html"),  # 예: 셀 구조 포함
            ))
    return blocks
```

### 2) LLM로 “스키마 매핑”만 수행 (JSON schema 강제 + 재시도)
핵심은 LLM 입력을 **(a) 표/문단 블록 + (b) 목표 스키마 + (c) 추출 규칙**으로 제한하는 겁니다.  
또한 결과는 `pydantic`으로 검증하고 실패 시 재시도합니다.

```python
class LineItem(BaseModel):
    item_name: str
    quantity: float
    unit_price: float
    amount: float

class Settlement(BaseModel):
    invoice_id: str
    vendor_name: str
    period: str  # "2026-06" 같은 정규화된 값
    currency: str = Field(default="USD")
    line_items: List[LineItem]
    evidence: Dict[str, Any]  # 각 필드의 page/bbox 등 provenance

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def llm_schema_map(blocks: List[Block]) -> Settlement:
    # 입력은 "관련성이 높은 table/paragraph"만 추리면 더 좋다.
    tables = [b for b in blocks if b.kind == "table" and (b.table_html or b.text)]
    paras  = [b for b in blocks if b.kind == "paragraph" and b.text]

    prompt = {
        "task": "Extract settlement fields into strict JSON.",
        "rules": [
            "Do NOT guess. If a value is missing, return empty string and add a warning in evidence.",
            "All numeric fields must be parseable as floats.",
            "period must be normalized to YYYY-MM if possible.",
            "For each top-level field, include evidence: page and bbox if available, and whether it came from a table cell or paragraph."
        ],
        "schema": Settlement.model_json_schema(),
        "inputs": {
            "tables": [
                {"page": t.page, "bbox": t.bbox, "table_html": t.table_html, "fallback_text": t.text[:2000]}
                for t in tables
            ],
            "paragraphs": [
                {"page": p.page, "bbox": p.bbox, "text": p.text[:1000]}
                for p in paras
            ],
        },
    }

    # 예시: OpenAI Responses API 호출로 가정(프로젝트에 맞게 교체)
    # 실제로는 "structured output" / "json_schema" 강제 기능을 쓰는 편이 운영에 유리.
    import openai
    client = openai.OpenAI()

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
        # 실제 구현에서는 json_schema 강제 옵션 사용 권장
    )

    text = resp.output_text
    data = json.loads(text)  # 모델이 JSON만 출력하도록 강제해야 안전
    try:
        return Settlement.model_validate(data)
    except ValidationError as e:
        # 검증 실패는 재시도 트리거(tenacity)
        raise RuntimeError(f"Schema validation failed: {e}") from e
```

### 3) 실행 및 예상 출력
```python
def main():
    pdf_bytes = open(PDF_PATH, "rb").read()
    doc = call_layout_parser(pdf_bytes)
    blocks = blocks_from_layout(doc)

    settlement = llm_schema_map(blocks)
    print(settlement.model_dump_json(indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
```

예상 출력(요지):
```json
{
  "invoice_id": "INV-2026-06-1138",
  "vendor_name": "ACME Logistics LLC",
  "period": "2026-06",
  "currency": "USD",
  "line_items": [
    {"item_name": "Linehaul", "quantity": 12, "unit_price": 85.5, "amount": 1026.0}
  ],
  "evidence": {
    "invoice_id": {"page": 1, "bbox": {"x1":0.12,"y1":0.08,"x2":0.32,"y2":0.10}, "source":"paragraph"},
    "line_items": {"page": 2, "bbox": {"x1":0.05,"y1":0.22,"x2":0.95,"y2":0.78}, "source":"table"}
  }
}
```

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **LLM을 “최종 생성자”가 아니라 “정규화/매핑기”로 제한**
- Layout/Table 단계에서 구조를 최대한 복원하고(표는 셀 단위), LLM은 `schema mapping + normalization`만 담당시키면 hallucination을 크게 줄입니다.
- 휴리스틱 기반 TSR(SPARTAN) 같은 접근이 다시 주목받는 이유가 “비용/설명가능성/튜닝 용이성”입니다. ([nature.com](https://www.nature.com/articles/s41598-026-44325-7?utm_source=openai))

2) **provenance(근거) 설계를 1순위로**
- 값마다 `page + bbox + source(table cell/paragraph)`를 붙이세요.
- 커뮤니티에서 지적하듯 “JSON은 예쁜데 출처 추적이 안 되면” 운영에서 바로 막힙니다. ([reddit.com](https://www.reddit.com/r/computervision/comments/1t9nnba/why_is_pdf_table_extraction_still_hard_even_with/?utm_source=openai))

3) **PDF → Markdown 변환을 RAG 품질 관점에서 측정**
- “텍스트 잘 뽑힘”이 아니라 “downstream QA 정확도”로 평가하는 연구가 나왔고, 변환/청킹/메타데이터 전략의 영향이 큽니다. ([arxiv.org](https://arxiv.org/abs/2604.04948?utm_source=openai))  
- 즉, 추출 파이프라인은 단독 지표(WER)보다 **업무 KPI(정산 검수 시간, QA 정답률)**로 평가하세요.

### 흔한 함정/안티패턴
- **스캔 PDF 전체를 VLM에 그대로 넣고 “표를 JSON으로” 한 방에 끝내기**  
  → 데모는 되지만, (a) 비용 폭발, (b) 페이지 수 늘면 컨텍스트/일관성 붕괴, (c) provenance 부재로 장애 대응 불가.
- **OCR 품질이 낮은데 LLM으로 “상식 보정”**  
  → LLM이 빈 칸을 채워 넣는 순간, 회계/정산/법무 문서에서 사고가 납니다. “Do NOT guess” 규칙 + 검증 루프 필수.
- **표를 Markdown으로만 저장하고 셀 좌표를 버림**  
  → 나중에 “이 금액이 표의 어느 셀에서 왔냐” 질문에 답을 못 합니다.

### 비용/성능/안정성 트레이드오프 (2026년 7월 기준)
- Google의 Gemini 기반 layout parser처럼 “OCR + LLM 결합”은 구조화 품질을 끌어올리지만, **대량 처리 시 단가/지연**을 반드시 측정해야 합니다. ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai))  
- Mistral OCR 4는 bounding box/레이블/신뢰도와 멀티언어를 강점으로 내세우고, self-hosted 단일 컨테이너도 언급됩니다(배포/데이터 경계가 중요한 조직에 매력). ([mistral.ai](https://mistral.ai/fr/news/ocr-4/?utm_source=openai))  
- 반대로, AWS Textract나 Azure Document Intelligence처럼 “문서 전용” 제품은 표/레이아웃 객체가 비교적 명시적이라 **감사/운영 친화적**인 면이 있습니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/textract/latest/dg/how-it-works-tables.html?utm_source=openai))

---

## 🚀 마무리
2026년 7월의 결론은 단순합니다. **문서 AI는 ‘LLM으로 읽는다’가 아니라 ‘Layout/Table을 먼저 복원하고, LLM은 스키마 매핑에 제한한다’**가 프로덕션 승률이 높습니다. Google의 Gemini 기반 layout parser 같은 흐름, Mistral OCR 4의 bbox/블록/신뢰도 강조, 그리고 휴리스틱 TSR(SPARTAN) 재부상은 모두 같은 방향을 가리킵니다. ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai))

도입 판단 기준(실무 체크리스트):
- 표가 핵심이면: **TSR 품질 + merged cell 처리 + 좌표/셀 근거 제공 여부**
- 운영이면: **provenance 설계(값→원문 근거) + 검증/재시도 + 관측가능성(로그/샘플링)**
- 비용이면: **페이지당 비용 + chunking 전략 + “LLM 투입 범위 최소화”**

다음 학습 추천:
- MLLM 기반 문서 이해의 방법/과제 정리(서베이)로 큰 그림 잡기 ([aclanthology.org](https://aclanthology.org/2026.findings-acl.652/?utm_source=openai))  
- PDF 변환 품질이 RAG에 미치는 영향 평가 프레임워크 참고 ([arxiv.org](https://arxiv.org/abs/2604.04948?utm_source=openai))  
- “프로덕션 아키텍처” 관점(마이크로서비스/스케일링/재처리) 사례 연구로 운영 설계 보강 ([arxiv.org](https://arxiv.org/abs/2605.18818?utm_source=openai))