---
title: "2026년 8월, OCR + Document AI + LLM으로 “문서 이해/구조화 추출/표·PDF”를 끝내는 현실적인 설계도"
date: 2026-08-23 01:50:08 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-08]
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
문서 추출 프로젝트가 실패하는 전형적인 패턴은 이겁니다: **OCR로 텍스트는 뽑았는데, “구조”가 깨져서(표/다단/헤더 계층/키-값 관계/reading order) 결국 사람이 후처리**하게 되는 것. 특히 PDF는 “보이는 것”과 “텍스트 스트림”이 다를 수 있어, 단순 파싱(PDFMiner류)이나 단순 OCR(Tesseract류)만으로는 **정확한 테이블 구조/섹션 계층/필드 정합성**을 보장하기 어렵습니다.

2026년 8월 기준 흐름은 크게 두 갈래로 정리됩니다.

- **(A) Specialized Document AI(레이아웃+OCR+테이블) → LLM은 ‘정규화/검증/보강’ 역할**  
  고정된 문서 타입(청구서, 은행명세서, 폼 등)과 대량 처리에서 비용/지연/재현성이 좋습니다. Azure Document Intelligence v4.0의 품질 개선·인증/학습 기능 업데이트 같은 “운영 기능”이 강점입니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/whats-new?view=doc-intel-4.0.0&utm_source=openai))
- **(B) 멀티모달 LLM(비전) 중심으로 “문서 이해→JSON”을 한 번에**  
  복잡 레이아웃/혼합 문서에서 초기 구축이 빠르지만, **표 구조 오류/환각/비용**이 튀는 구간이 있습니다. 그래서 실무에선 (A)와 섞거나, “레이아웃 파서(LLM+OCR 결합)” 같은 관리형 서비스를 씁니다. Google Document AI의 Gemini 기반 layout parser가 그 방향을 명확히 보여줍니다. ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai))

**언제 쓰면 좋은가**
- 문서가 PDF/스캔 이미지로 들어오고, **표·키값·섹션 구조**가 핵심인 경우(재무 리포트, 계약서, 인보이스, 규정집, 공문)
- RAG 이전 단계에서 **chunking 품질을 “레이아웃 기반”으로 끌어올려야** 하는 경우(다단/각주/표 캡션 때문에 검색 품질이 무너질 때)

**언제 쓰면 안 좋은가(또는 설계를 바꿔야 하는가)**
- “어차피 원천이 이미 구조화(DB/CSV)”인데 PDF만 남아있는 경우: 복원이 아니라 **원천 파이프라인 수정이 ROI가 높음**
- 품질 측정 없이 “LLM이 알아서”로 가는 경우: **표/금액/단위**는 작은 오류가 치명적이라, 반드시 정량 평가/검증 계층이 필요(아래 ‘함정’ 참고)

---

## 🔧 핵심 개념
### 1) 2026년형 파이프라인의 표준: Layout-first → Structure → Semantics
요즘(2025~2026) 도구들이 공통적으로 택하는 흐름은 다음과 같습니다.

1. **Ingress(입력 정규화)**: PDF(네이티브/스캔 혼합), TIFF, JPG 등
2. **Layout analysis(문서 구조 분해)**: 페이지를 블록(제목/본문/표/그림/각주)으로 나누고 reading order 추정  
   - 오픈소스 계열은 DocLayNet 기반 레이아웃 모델을 많이 씁니다(Docling). ([arxiv.org](https://arxiv.org/abs/2501.17887?utm_source=openai))
3. **OCR(텍스트 복원)**: 블록별로 OCR/텍스트 추출
4. **Table structure recognition(표 구조 인식)**: “셀 경계/헤더 계층/병합 셀”을 복원  
   - Docling은 TableFormer 계열을 언급하며 테이블 구조 복원에 초점을 둡니다. ([arxiv.org](https://arxiv.org/abs/2501.17887?utm_source=openai))
5. **LLM extraction(의미 기반 구조화)**: 최종 목표 스키마(예: invoice schema, financial metrics schema)로 변환  
   - 여기서 LLM이 잘하는 건 “필드 매핑/정규화/누락 보강/설명 생성”이고, **좌표 기반 구조(표 셀 정렬)**는 전용 모델이 더 안전한 경우가 많습니다. 테이블을 그냥 텍스트로 직렬화하면 열이 밀리는 문제가 흔하다는 지적이 반복됩니다. ([logic.inc](https://logic.inc/resources/own-vs-offload-llm-table-extraction?utm_source=openai))

### 2) “Gemini layout parser” 류가 의미하는 것: OCR + LLM을 한 서비스로 결합
Google Document AI의 layout parser는 **전용 OCR + Gemini 기반 생성 모델**을 결합해 “복잡 문서를 구조화된 요소로 파싱”하는 방향을 명시합니다(프리트레인 버전 명시 및 LLM 결합 설명). ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai))  
이건 실무적으로 **(i) 레이아웃 이해를 LLM로 끌어올리되 (ii) 문서 처리에 필요한 출력 형태를 고정**하려는 접근입니다. 즉 “자유로운 대화형 LLM”이 아니라 “문서 파싱 제품”으로 패키징하는 쪽.

### 3) 오픈소스 스택이 강해진 이유: 변환 품질이 RAG 성능에 직결
RAG를 하려면 PDF를 Markdown/텍스트로 바꾸는데, 2026년에는 “어떤 변환 프레임워크를 쓰느냐가 다운스트림 QA 정확도에 미치는 영향”을 비교한 연구도 나옵니다(여러 오픈소스 변환 도구 비교). ([arxiv.org](https://arxiv.org/abs/2604.04948?utm_source=openai))  
결국 문서 이해/추출은 “OCR 정확도”만이 아니라 **레이아웃 보존, 메타데이터(페이지/블록/테이블) 보존, chunking 전략**의 문제로 확장됩니다.

---

## 💻 실전 코드
아래 예제는 “현실적인 운영”을 전제로 합니다.

- 입력: **스캔/네이티브가 섞인 PDF**
- 1차 변환: **Docling으로 레이아웃+테이블 포함한 구조화(Markdown/JSON 계열)**  
- 2차 추출: LLM에 바로 PDF를 넣지 않고, **(a) 테이블은 구조를 유지한 채 (b) 본문은 섹션 단위로** 스키마 추출  
- 3차 검증: 금액/합계/컬럼 정합성 룰로 **후처리 validation**

> 주의: Docling/LLM 연동은 팀마다 선택지가 많아, “패턴” 중심으로 작성합니다. Docling은 레이아웃/테이블 중심의 오픈소스 변환 툴킷으로 널리 언급됩니다. ([arxiv.org](https://arxiv.org/abs/2501.17887?utm_source=openai))

### 1) 셋업
```bash
# (예시) python 3.11+
python -m venv .venv
source .venv/bin/activate

pip install -U docling pydantic tenacity rapidfuzz

# LLM 호출은 팀 표준에 맞추세요:
# - OpenAI / Azure OpenAI / Vertex AI / Anthropic 등
# 여기서는 "LLM_API_URL + API_KEY"로 호출하는 형태의 의사 구현을 둡니다.
```

### 2) PDF → 레이아웃/테이블 보존 변환 (Docling) + 섹션/테이블 분리
```python
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

# ---- 스키마(예: 재무/거래 테이블 추출) ----
class LineItem(BaseModel):
    date: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None

class StatementExtract(BaseModel):
    account_holder: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    transactions: List[LineItem] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

# ---- (의사) Docling 변환 결과를 받아온다고 가정 ----
def docling_convert(pdf_path: str) -> Dict[str, Any]:
    """
    실제로는 Docling의 converter를 호출해
    - 문서 요소(heading/paragraph/table)
    - table 구조(행/열/셀)
    - 페이지/좌표 메타데이터
    를 얻어야 합니다.
    """
    # NOTE: 프로젝트에서는 여기서 Docling API를 직접 호출하세요.
    # 아래는 "구조"를 보여주기 위한 예시 포맷입니다.
    return {
        "doc_id": Path(pdf_path).name,
        "sections": [
            {"type": "heading", "text": "Account Statement"},
            {"type": "kv", "key": "Account Holder", "value": "Jane Doe"},
            {"type": "kv", "key": "Period", "value": "2026-07-01 ~ 2026-07-31"},
            {"type": "table", "name": "transactions",
             "header": ["Date", "Description", "Amount", "Currency"],
             "rows": [
                 ["2026-07-02", "Coffee Shop", "-4.50", "USD"],
                 ["2026-07-05", "Salary", "3500.00", "USD"],
             ]}
        ]
    }

def split_for_extraction(doc: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    - 본문 텍스트는 LLM에 넣기 쉬운 형태로 직렬화
    - 테이블은 구조 보존(행/열)으로 별도 전달
    """
    narrative_parts = []
    tables = []
    for el in doc["sections"]:
        if el["type"] == "table":
            tables.append(el)
        else:
            if el["type"] == "kv":
                narrative_parts.append(f'{el["key"]}: {el["value"]}')
            else:
                narrative_parts.append(el["text"])
    return "\n".join(narrative_parts), tables

if __name__ == "__main__":
    pdf_path = "samples/statement.pdf"
    doc = docling_convert(pdf_path)
    narrative, tables = split_for_extraction(doc)

    print("=== NARRATIVE ===")
    print(narrative)
    print("\n=== TABLES ===")
    print(json.dumps(tables, indent=2))
```

**예상 출력(요지)**
- narrative에는 `Account Holder`, `Period` 같은 문장/키값이 모이고
- tables에는 `rows`가 **열 정렬을 유지한 채** 들어갑니다  
이게 중요한 이유는 “표를 텍스트로 풀어버리면 열이 밀린다”는 테이블 추출의 대표 실패 모드를 피하기 위해서입니다. ([logic.inc](https://logic.inc/resources/own-vs-offload-llm-table-extraction?utm_source=openai))

### 3) LLM 추출(스키마 강제) + 검증(룰 기반)
```python
import os
import re
import math
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

LLM_API_URL = os.getenv("LLM_API_URL")  # 예: 사내 게이트웨이
LLM_API_KEY = os.getenv("LLM_API_KEY")

def parse_money(x: str) -> Optional[float]:
    if x is None:
        return None
    x = x.strip()
    x = re.sub(r"[,$]", "", x)
    try:
        return float(x)
    except:
        return None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def call_llm_json(prompt: str) -> Dict[str, Any]:
    """
    팀 표준 LLM 호출부로 교체하세요.
    핵심은: 결과를 '반드시 JSON'으로 받도록 강제하고, 실패 시 재시도/로깅.
    """
    resp = requests.post(
        LLM_API_URL,
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
        json={
            "response_format": "json",
            "prompt": prompt,
            "temperature": 0
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()

def build_prompt(narrative: str, tables: List[Dict[str, Any]]) -> str:
    # 테이블을 "구조화된 JSON" 그대로 전달 (텍스트 평탄화 금지)
    return f"""
You are an information extraction engine.
Return ONLY valid JSON that matches this schema:
{StatementExtract.model_json_schema()}

Rules:
- Do not invent values. If missing, use null and add a warning.
- Parse amounts as numbers (negative for debits).
- Prefer table 'transactions' as the source of line items.

Document narrative:
{narrative}

Tables (structured):
{json.dumps(tables, ensure_ascii=False)}
""".strip()

def validate(extract: StatementExtract) -> StatementExtract:
    # 예: 거래 합계/잔액 정합성 같은 도메인 룰을 추가 가능
    for t in extract.transactions:
        if t.amount is None and t.description:
            extract.warnings.append(f"amount_missing_for: {t.description}")
    return extract

if __name__ == "__main__":
    pdf_path = "samples/statement.pdf"
    doc = docling_convert(pdf_path)
    narrative, tables = split_for_extraction(doc)

    prompt = build_prompt(narrative, tables)
    llm_out = call_llm_json(prompt)

    extract = StatementExtract.model_validate(llm_out)

    # 테이블 기반 보정(LLM이 실수하면 안전장치)
    # 예: LLM이 amount를 문자열로 내면 강제 파싱
    fixed = extract.model_copy(deep=True)
    for i, t in enumerate(fixed.transactions):
        if isinstance(t.amount, str):
            fixed.transactions[i].amount = parse_money(t.amount)

    fixed = validate(fixed)
    print(fixed.model_dump_json(indent=2, exclude_none=False))
```

이 패턴의 포인트:
- **LLM은 “결정/매핑”에 쓰고**, 표의 열 정렬/계층은 **전용 구조(테이블 JSON)**로 보호
- 실패해도 재시도/검증으로 “운영 가능한” 파이프라인이 됨
- 관리형 서비스를 쓰는 경우(예: Azure/Google)는 여기서 `docling_convert()`를 각 벤더 SDK 호출로 대체하면 됩니다. Azure는 v4.0에서 품질 개선/학습 기능 업데이트를 지속 반영하고 있습니다. ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/whats-new?view=doc-intel-4.0.0&utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **문서 타입별로 “구조 보존 포맷”을 먼저 고정**  
   Markdown만으로 충분한지, table은 별도 JSON이어야 하는지, bbox가 필요한지부터 결정하세요. 테이블은 평탄화하면 열 밀림이 빈번합니다. ([logic.inc](https://logic.inc/resources/own-vs-offload-llm-table-extraction?utm_source=openai))

2) **평가셋을 “최악 문서” 중심으로 만들기**  
   평균 문서는 다 맞습니다. 문제는 다단+각주+복잡 표+스캔 품질입니다. OmniDocBench 같은 벤치가 업데이트되며 다양한 모델 평가를 지속 반영하는 것도 이런 배경입니다. ([github.com](https://github.com/opendatalab/OmniDocBench?utm_source=openai))

3) **RAG 목적이면 ‘변환 품질 → QA 성능’으로 역평가**  
   “문서 변환이 좋아 보인다”가 아니라, 실제 QA 정확도에 영향이 있는지 봐야 합니다. PDF 변환 도구가 다운스트림 QA에 미치는 영향을 비교한 연구가 나오는 이유가 여기입니다. ([arxiv.org](https://arxiv.org/abs/2604.04948?utm_source=openai))

### 흔한 함정/안티패턴
- **표를 텍스트로만 직렬화해서 LLM에 던지기**: 멀티헤더/병합셀에서 열이 미끄러져 “그럴듯한 오답”이 나옵니다. ([logic.inc](https://logic.inc/resources/own-vs-offload-llm-table-extraction?utm_source=openai))
- **LLM 출력 JSON을 그대로 DB에 넣기**: schema validation, type coercion, 도메인 룰 검증(합계=부분합, 날짜 범위, 통화 단위)을 반드시 두세요.
- **비용 모델을 페이지 기준으로만 추정**: 스캔 PDF는 OCR 비용+LLM 토큰 비용이 같이 늘고, 재시도까지 포함하면 예산이 흔들립니다.

### 비용/성능/안정성 트레이드오프(2026년 현실)
- **대량/정형 문서**: 전통 Document AI(전용 OCR+모델) + 최소 LLM이 대체로 유리(지연/단가/재현성).
- **혼합/복잡 레이아웃**: LLM 결합형 레이아웃 파서(예: Gemini 결합 layout parser) 같은 제품형 접근이 “구축 속도 vs 통제”의 균형점이 됩니다. ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai))
- **온프렘/데이터 통제**: Docling 같은 오픈소스 변환 + 사내 LLM(또는 게이트웨이) 조합이 매력적입니다. ([arxiv.org](https://arxiv.org/abs/2501.17887?utm_source=openai))

---

## 🚀 마무리
2026년 8월 기준으로 문서 OCR/이해/구조화 추출은 “OCR만 잘하면 끝”이 아니라, **Layout-first(문서 구조) + Table structure(표 구조) + LLM semantics(의미 추출) + Validation(검증)**의 조합 문제로 정리됩니다. Google Document AI의 Gemini 결합 layout parser 같은 흐름은 “LLM을 문서 파싱 제품에 내장”하는 방향을 분명히 보여주고, ([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai)) 오픈소스 진영은 Docling처럼 레이아웃/테이블에 강한 변환 스택으로 빠르게 따라오고 있습니다. ([arxiv.org](https://arxiv.org/abs/2501.17887?utm_source=openai))

**도입 판단 기준(실무 체크리스트)**
- 내 문서의 80%가 “정형+대량”인가, “혼합+복잡”인가?
- 표 정확도가 KPI인가? 그렇다면 **표 구조 인식 계층**을 분리했는가?
- LLM을 쓰더라도 **스키마 강제 + 검증 + 재처리 전략**이 있는가?
- RAG가 목적이라면 변환 품질을 **QA 정확도**로 역평가했는가? ([arxiv.org](https://arxiv.org/abs/2604.04948?utm_source=openai))

**다음 학습 추천**
- (1) 레이아웃/테이블 중심 변환(Docling 계열) → (2) 스키마 기반 추출(Pydantic/JSON schema) → (3) 테이블 정합성 검증(도메인 룰) 순으로 PoC를 쪼개면, “데모는 되는데 운영이 안 되는” 함정을 가장 빨리 피할 수 있습니다.