---
title: "LLM 시대(2026년 5월)의 OCR Document AI: “레이아웃 + 스키마 + 검증”으로 표·PDF를 구조화 추출하는 법"
date: 2026-05-29 04:20:09 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-05]
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
문서 OCR/이해 파이프라인에서 **진짜 어려운 문제**는 “텍스트를 읽는 것”이 아니라, *표/레이아웃을 깨뜨리지 않고* **업무 스키마(JSON)** 로 *일관되게* 뽑아내는 겁니다. 특히 PDF(스캔/디지털 혼합), 표(merged cell, multi-line header), 라인아이템(동적 행 수), 그리고 페이지를 넘나드는 합계/세금 규칙에서 터집니다.

2026년 5월 시점의 실무 결론은 대체로 이렇습니다.

- **언제 쓰면 좋은가**
  - 문서 종류가 다양하고 레이아웃 변형이 잦은 경우(거래명세서/인보이스/운송장/BOL/재무제표 PDF 등)
  - “정확한 JSON 스키마”가 필요하고, 후처리/검증까지 포함해 **ETL**로 붙여야 하는 경우
  - 표·PDF에서 *의미 단위* 추출(라인아이템, 섹션별 조항, 표의 헤더-바디 매핑)이 핵심인 경우  
  - LLM을 **검증/정규화/보정 레이어**로 쓰고, OCR은 좌표/레이아웃을 안정적으로 확보하는 용도일 때 (현업에서 이 조합이 가장 잘 굴러갑니다)

- **언제 쓰면 안 되는가**
  - 초고정형 서식(레이아웃이 99% 동일) + 초대량(일 수십만 건)이라면, LLM은 비용이 과합니다. 전통 Document AI(템플릿/모델) + 규칙 기반이 더 싸고 안정적일 수 있어요.
  - “표 전체를 그대로 DB로” 같은 요구는 LLM 단독으로는 재현성이 낮습니다. (예: Textract Queries는 “표 전체/행·열 전체를 질의로 뽑기”가 제한적이라는 점도 명시되어 있습니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/textract/latest/dg/bestqueries.html?utm_source=openai)))
  - 규제/감사 대응으로 **완전한 결정 경로 설명**이 필요한 경우: LLM은 설명 가능성 확보를 위해 추가 설계(근거 스팬, 좌표 링크, 규칙 검증)가 필요합니다.

---

## 🔧 핵심 개념
### 1) “OCR → Layout → (LLM) Schema Extraction”이 표준이 된 이유
전통적인 흐름은 보통 이랬습니다.

1. OCR(문자 인식)
2. Layout 분석(문단/표/셀)
3. 키-값/테이블 추출 모델(문서 타입별)
4. 후처리(정규화/검증/합계 체크)

2026년에는 여기에 **LLM(특히 멀티모달)** 이 들어오면서 두 가지 전략이 공존합니다.

- **A. OCR 없이 이미지/PDF를 LLM에 바로 넣기**  
  최근 연구들은 “강한 MLLM이면 OCR이 꼭 필요하지 않을 수도 있다”는 결과를 내기도 합니다. ([arxiv.org](https://arxiv.org/abs/2603.02789?utm_source=openai))  
  다만 실무에서는 *좌표/근거/셀 단위 정합성* 때문에 OCR/Layout를 완전히 빼기 어렵습니다.

- **B. OCR/Layout로 ‘구조’를 잡고, LLM은 ‘의미를 스키마로’ 정렬**  
  이 접근이 현업에서 가장 재현성이 좋습니다. Azure Document Intelligence v4.0이 문서 구조/표/그림을 Markdown 등으로 내보내 RAG/후처리에 쓰는 방향을 강조한 것도 같은 맥락입니다. ([techcommunity.microsoft.com](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/announcing-the-general-availability-of-document-intelligence-v4-0-api/4357988/?utm_source=openai))  
  Google Document AI도 Layout parser로 텍스트·표·리스트를 추출하고 “context-aware chunk”를 만들어 검색/생성형 워크플로우에 붙이는 흐름을 문서로 제공합니다. ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai))

핵심은: **Layout(좌표/구조)은 deterministic하게**, **의미 매핑/정규화는 LLM으로**.

### 2) 스키마 기반 추출: “프롬프트”가 아니라 “계약(Contract)”
LLM을 문서 추출에 붙이면 늘 터지는 문제가 “JSON이 깨짐 / 누락 / 타입 틀림”입니다. 이걸 막는 장치가 **Structured Outputs(= JSON Schema 기반 제약 디코딩)** 입니다. OpenAI는 API 레벨에서 JSON Schema 기반 Structured Outputs를 제공하고, 특정 모델 스냅샷에서 지원 범위를 명시합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))

이게 실무에서 바꾸는 게임의 룰:
- “모델이 JSON을 잘 찍어주길 바란다”가 아니라
- **스키마를 계약으로 고정**하고,
- 모델은 **채우기(fill)** 만 하게 만들 수 있습니다.
- 그리고 마지막에 **validator-guided repair**(검증기 기반 수선)까지 붙이면, 파이프라인이 견고해집니다(유사 접근이 2026년 논문/아키텍처에서도 반복됩니다). ([arxiv.org](https://arxiv.org/abs/2604.06571?utm_source=openai))

### 3) 표/페이지 처리에서 중요한 내부 흐름(구조/흐름)
표·PDF에서 안정적으로 구조화하려면, 보통 아래 순서를 권합니다.

1. **Ingestion**
   - PDF가 “텍스트 PDF”인지 “스캔 이미지”인지 판별
   - 페이지 단위 렌더링(DPI 200~300) + deskew/denoise(필요 시)
2. **Layout/OCR**
   - 페이지별: blocks/lines/words + bounding boxes
   - tables: cell grid + row/col span + header candidates
3. **Chunking(문서 분할)**
   - “페이지 n” 단위가 아니라 **섹션/표 단위**로 자르는 게 포인트  
   - Google Layout parser가 “chunk”를 강조하는 것도 같은 이유입니다. ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai))
4. **LLM Schema Extraction**
   - 입력: (a) 표의 셀 텍스트 + (b) 주변 캡션/제목 + (c) 좌표 요약
   - 출력: JSON schema(라인아이템 배열, totals, vendor, dates…)
5. **Validation & Reconciliation**
   - 합계 검증(∑ line_items == total), 통화/날짜 표준화, vendor canonicalization
   - 실패 시 재시도 전략: 다른 chunk 재구성 / 상위 모델로 escalation / OCR 재수행
6. **Human-in-the-loop(옵션)**
   - confidence 낮은 필드만 태스크로 올리기

여기서 “다른 접근과의 차이점”은:
- 전통 Document AI: 문서 타입별 학습/튜닝의 비중이 큼
- 2026 LLM-하이브리드: **스키마/검증/오케스트레이션**이 경쟁력  
  (텍스트 인식 자체는 commodity가 되고, 파이프라인 설계가 실력 차이를 만듭니다.)

---

## 💻 실전 코드
아래 예시는 **“PDF 인보이스/거래명세서에서 라인아이템 + 합계 + 세금”**을 뽑아 **DB에 넣기 좋은 JSON**을 만드는 현실형 파이프라인입니다.

- OCR/Layout: (예시로) Azure Document Intelligence Layout을 호출해 텍스트/테이블 구조 확보
- LLM: OpenAI `gpt-4o-2024-08-06` + **Structured Outputs(JSON Schema)** 로 스키마 강제 ([developers.openai.com](https://developers.openai.com/api/docs/models/gpt-4o?utm_source=openai))
- 검증: Pydantic + 합계 일치 검사

> 주의: Azure DI v4.0이 GA이며, 최신 API 버전 업데이트가 권장됩니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/applied-ai-services/form-recognizer/whats-new?utm_source=openai))

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install "openai>=1.0.0" "pydantic>=2.7.0" requests python-dotenv
```

`.env`
```bash
AZURE_DI_ENDPOINT="https://<your-resource-name>.cognitiveservices.azure.com/"
AZURE_DI_KEY="<key>"
OPENAI_API_KEY="<key>"
```

### 1) 스키마 정의 + LLM 추출(Structured Outputs)
```python
# extract_invoice.py
import os
import time
import json
import requests
from typing import List, Optional, Literal
from dotenv import load_dotenv
from pydantic import BaseModel, Field, conlist, ValidationError
from openai import OpenAI

load_dotenv()

# --------- 1) Target Schema (DB-friendly contract) ----------
class Money(BaseModel):
    currency: Literal["USD", "KRW", "EUR", "JPY", "CNY", "GBP"] = "USD"
    amount: float = Field(..., description="numeric amount, dot decimal")

class LineItem(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[Money] = None
    line_total: Money
    sku: Optional[str] = None

class InvoiceExtraction(BaseModel):
    vendor_name: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = Field(None, description="ISO-8601 date string if possible")
    purchase_order: Optional[str] = None

    subtotal: Optional[Money] = None
    tax: Optional[Money] = None
    total: Money

    line_items: conlist(LineItem, min_length=1)
    warnings: List[str] = []

# --------- 2) Azure Document Intelligence Layout call ----------
def azure_di_layout_analyze(pdf_bytes: bytes) -> dict:
    endpoint = os.environ["AZURE_DI_ENDPOINT"].rstrip("/")
    key = os.environ["AZURE_DI_KEY"]

    # Use Layout model; API version should match your resource configuration
    url = f"{endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze?api-version=2024-11-30"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/pdf",
    }
    r = requests.post(url, headers=headers, data=pdf_bytes)
    r.raise_for_status()

    op_loc = r.headers.get("operation-location")
    if not op_loc:
        raise RuntimeError("No operation-location returned from Azure DI")

    # Poll
    for _ in range(60):
        pr = requests.get(op_loc, headers={"Ocp-Apim-Subscription-Key": key})
        pr.raise_for_status()
        data = pr.json()
        if data.get("status") in ("succeeded", "failed"):
            if data["status"] == "failed":
                raise RuntimeError(f"Azure DI failed: {json.dumps(data)[:500]}")
            return data
        time.sleep(1)

    raise TimeoutError("Azure DI polling timeout")

def flatten_layout_to_llm_input(di_result: dict) -> str:
    """
    Turn DI result into a compact, LLM-friendly representation.
    Key idea: keep table cells + nearby context, not raw full JSON.
    """
    analyze = di_result["analyzeResult"]
    pages = analyze.get("pages", [])
    tables = analyze.get("tables", [])

    out = []
    out.append("DOCUMENT_PAGES:")
    for p in pages[:30]:
        out.append(f"- page {p.get('pageNumber')}: width={p.get('width')} height={p.get('height')}")

    out.append("\nTABLES:")
    for ti, t in enumerate(tables[:50]):
        rows = t.get("rowCount")
        cols = t.get("columnCount")
        out.append(f"\n[TABLE {ti}] rows={rows} cols={cols}")
        # collect cells sorted
        cells = sorted(t.get("cells", []), key=lambda c: (c.get("rowIndex", 0), c.get("columnIndex", 0)))
        for c in cells[:2000]:
            txt = (c.get("content") or "").replace("\n", " ").strip()
            ri = c.get("rowIndex")
            ci = c.get("columnIndex")
            rs = c.get("rowSpan", 1)
            cs = c.get("columnSpan", 1)
            if txt:
                out.append(f"  - r{ri}c{ci} span({rs},{cs}): {txt}")

    # include some top-level content lines if available
    # (some DI outputs include "content" at analyzeResult level)
    content = analyze.get("content", "")
    if content:
        # keep head/tail to avoid token blow-up
        out.append("\nCONTENT_HEAD:")
        out.append(content[:4000])
        out.append("\nCONTENT_TAIL:")
        out.append(content[-2000:])

    return "\n".join(out)

# --------- 3) LLM extraction with Structured Outputs ----------
def llm_extract(schema_input: str) -> InvoiceExtraction:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Use Structured Outputs (JSON Schema) to harden output
    # If your SDK supports Pydantic helpers, you can generate JSON schema from the model.
    json_schema = InvoiceExtraction.model_json_schema()

    resp = client.responses.create(
        model="gpt-4o-2024-08-06",
        input=[
            {
                "role": "system",
                "content": (
                    "You are a senior document extraction engine. "
                    "Extract invoice fields into the given JSON schema. "
                    "Prefer values grounded in TABLES. "
                    "If uncertain, fill warnings and leave nullable fields null."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract structured invoice data.\n\n"
                    "=== LAYOUT/TABLE DUMP ===\n"
                    f"{schema_input}\n"
                ),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "InvoiceExtraction",
                "schema": json_schema,
                "strict": True
            },
        },
    )

    data = json.loads(resp.output_text)
    return InvoiceExtraction.model_validate(data)

# --------- 4) Validation / reconciliation ----------
def reconcile(ex: InvoiceExtraction) -> InvoiceExtraction:
    warnings = list(ex.warnings)

    # Sum line items sanity check (tolerate small OCR rounding)
    sum_lines = sum(li.line_total.amount for li in ex.line_items)
    if abs(sum_lines - ex.total.amount) > max(0.02 * ex.total.amount, 1.0):
        warnings.append(f"Total mismatch: sum(line_items)={sum_lines} vs total={ex.total.amount}")

    return ex.model_copy(update={"warnings": warnings})

def run(pdf_path: str):
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    di = azure_di_layout_analyze(pdf_bytes)
    llm_in = flatten_layout_to_llm_input(di)

    try:
        ex = llm_extract(llm_in)
    except ValidationError as ve:
        # In production: store raw output, fallback to repair prompt, or escalate model
        raise RuntimeError(f"Schema validation failed: {ve}")

    ex = reconcile(ex)
    print(ex.model_dump_json(indent=2, exclude_none=True))

if __name__ == "__main__":
    run("sample_invoice.pdf")
```

### 예상 출력(예시)
```json
{
  "vendor_name": "ACME SUPPLY CO.",
  "invoice_number": "INV-104892",
  "invoice_date": "2026-05-12",
  "subtotal": { "currency": "USD", "amount": 1840.0 },
  "tax": { "currency": "USD", "amount": 147.2 },
  "total": { "currency": "USD", "amount": 1987.2 },
  "line_items": [
    {
      "description": "Nitrile Gloves, Large (Case)",
      "quantity": 10,
      "unit_price": { "currency": "USD", "amount": 120.0 },
      "line_total": { "currency": "USD", "amount": 1200.0 }
    },
    {
      "description": "Safety Goggles",
      "quantity": 16,
      "unit_price": { "currency": "USD", "amount": 40.0 },
      "line_total": { "currency": "USD", "amount": 640.0 }
    }
  ],
  "warnings": []
}
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “표 전체를 LLM에 맡기지 말고, 표를 ‘덤프’해서 스키마만 채우게”
표 추출에서 LLM이 강한 건 “이 셀들이 어떤 의미인지”를 매핑하는 능력이지, 픽셀에서 그리드를 재구성하는 능력이 아닙니다. 그래서 **Layout/OCR 엔진으로 셀을 확보**하고, LLM은 **스키마 필드 채우기**에 집중시키는 게 비용/성능/재현성 균형이 좋습니다. (Google Layout parser가 테이블/리스트를 뽑아 chunk를 만드는 방향도 이 철학과 맞습니다. ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai)))

### Best Practice 2) “스키마 강제 + validator-guided repair”를 기본값으로
- Structured Outputs로 1차 방어(스키마 일탈 차단) ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))
- 그 다음 **비즈니스 검증(합계/세금/통화)** 를 2차 방어로 둡니다.
- 실패 시 재시도는 “같은 프롬프트 반복”이 아니라:
  - chunk를 다르게 구성(표 + 캡션만)
  - OCR 재시도(DPI 조정, deskew)
  - 상위 모델로 escalation
  - *필드별 재질의* (invoice_number만 다시 뽑기)
이런 식으로 “실패 원인”을 바꾸는 재시도가 효율적입니다.

### Best Practice 3) Chunking은 “페이지”가 아니라 “의미 단위(표/섹션)”로
200페이지 PDF를 통으로 넣고 JSON 한 번에 뽑으려다 깨지는 사례는 커뮤니티에서도 반복됩니다(대개 invalid schema / truncation). ([reddit.com](https://www.reddit.com/r/GeminiAI/comments/1p59pkq/vertex_ai_gemini_fails_on_large_200_page_pdfs/?utm_source=openai))  
**문서→섹션→표**로 분할하고, 마지막에 머지(merge)하세요.

### 흔한 함정/안티패턴
- **“Queries로 표 전체를 뽑자”**: Textract Queries는 표 전체/행·열 전체 추출이 지원되지 않는 제한이 문서에 명시돼 있습니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/textract/latest/dg/bestqueries.html?utm_source=openai))  
  → Queries는 *특정 키-값*이나 제한된 질의에 쓰고, 표는 TABLES 기능/레이아웃 기반으로 처리하는 식으로 역할 분담이 필요합니다.
- **모델/엔진 업그레이드를 단순 버전업으로 취급**: Document AI 계열은 버전업 시 레이아웃 가정이 바뀌어 추출 결과가 달라질 수 있습니다(실무 체감 이슈로 자주 나옵니다). ([reddit.com](https://www.reddit.com/r/AZURE/comments/1s2i5gr/experiencing_decreased_accuracy_with_doc/?utm_source=openai))  
  → “리그레션 테스트 세트(실제 문서 100~500개)”를 고정해 CI에서 비교하세요.
- **LLM 단독 OCR로 비용 폭발**: “LLM OCR이 표에서 전통 OCR보다 낫다”는 주장도 있으나, 벤더/문서 특성/비용 구조에 따라 다릅니다. ([parsli.co](https://parsli.co/blog/llm-ocr-vs-traditional-ocr?utm_source=openai))  
  → 고정형 대량은 전통 OCR이 유리, 변형 많은 표-heavy는 하이브리드/LLM이 유리인 경우가 많습니다.

### 비용/성능/안정성 트레이드오프(현실적 가이드)
- **가장 싸고 빠름**: 전통 OCR + 규칙/템플릿  
  단, 문서 변형에 취약
- **가장 균형 좋음(추천)**: Layout/OCR(좌표 안정) + LLM(스키마 매핑/정규화) + 검증  
  운영 난이도는 있지만 “프로덕션”에 맞음
- **가장 강하지만 비쌈**: 멀티모달 LLM에 PDF를 직접 넣어 end-to-end  
  PoC에는 좋지만, 대량·재현성·감사 대응에서 추가 설계가 필수

---

## 🚀 마무리
2026년 5월의 문서 이해/구조화 추출은 “OCR vs LLM” 싸움이 아니라, **파이프라인 설계(레이아웃 확보 → 스키마 강제 → 검증/재시도)** 가 승패를 가릅니다.  
도입 판단 기준은 아래 3가지로 정리할 수 있어요.

1) 문서 레이아웃 변형이 큰가? → 크면 LLM 기반 스키마 매핑 가치가 큼  
2) 표/라인아이템이 핵심인가? → Layout 기반 셀 확보 + LLM 매핑이 가장 안전  
3) 운영 요구(비용, SLA, 감사/재현성)가 빡센가? → Structured Outputs + validator + 리그레션 테스트가 필수

다음 학습 추천:
- Google Document AI Layout parser 기반 chunking/테이블 추출 흐름(“layout → chunk”) ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai))
- OpenAI Structured Outputs(JSON Schema)로 “추출 결과를 계약화”하는 패턴 ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))
- Azure Document Intelligence v4.0의 구조/표 중심 출력과 RAG 결합 방향 ([techcommunity.microsoft.com](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/announcing-the-general-availability-of-document-intelligence-v4-0-api/4357988/?utm_source=openai))

원하면, (1) “인보이스/거래명세서/재무제표” 중 어떤 문서인지, (2) 월 처리량과 허용 비용, (3) 반드시 맞아야 하는 필드(예: line_items vs total) 3가지만 알려주시면 위 코드/아키텍처를 그 조건에 맞춰 더 구체적으로 튜닝해드릴게요.