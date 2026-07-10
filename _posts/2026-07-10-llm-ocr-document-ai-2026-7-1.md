---
title: "LLM 시대의 OCR Document AI: 2026년 7월 기준 “문서 이해→구조화 추출”을 프로덕션에 넣는 설계 가이드"
date: 2026-07-10 03:59:13 +0900
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
문서 OCR/이해 파이프라인이 해결하는 문제는 단순히 “PDF에서 text 뽑기”가 아닙니다. 실무에서 진짜 골칫거리는:

- **레이아웃이 시각적으로 풍부(Visually Rich)** 해서 텍스트만 뽑으면 의미가 깨짐(헤더/푸터, 컬럼, footnote, 표, 페이지 번호, 섹션 구조)
- **표(Table) 구조**가 핵심인데 cell 병합/다중 헤더/페이지 넘김(table spanning pages) 때문에 결과가 흔들림
- 최종 목표는 대개 **DB에 넣을 수 있는 schema(JSON/SQL)** 로 “정규화된 구조화 추출”인데, OCR 결과가 제각각이라 후처리가 폭발

2026년 흐름은 “OCR → Layout/Structure → (필요 시) LLM로 schema 매핑/검증/수정”의 **하이브리드**가 가장 현실적인 선택지로 굳어지고 있습니다. Google은 Gemini 기반 layout parsing을 Document AI에 붙여 레이아웃/구조 추출을 강화했고([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai)), Microsoft는 Document Intelligence에서 layout 모델을 중심으로 **문서 구조/표/reading order**를 안정적으로 뽑아 RAG/semantic chunking에 연결하는 방향을 강조합니다([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?country=us&culture=en-us&view=doc-intel-3.1.0&utm_source=openai)). AWS Textract는 여전히 “텍스트/표/폼 구조 추출”을 강점으로 유지하며 API가 꾸준히 업데이트되고 있습니다(문서 업데이트가 2026-06-26로 표기)([docs.aws.amazon.com](https://docs.aws.amazon.com/textract/latest/APIReference/?utm_source=openai)).

### 언제 쓰면 좋나
- 문서 유형이 다양하고(공급사/기관별 양식 상이) **규칙 기반 파서가 유지보수 지옥**인 경우
- **표가 핵심**이고, 표를 “그대로 복원”보다 “업무 스키마로 정규화”해야 하는 경우(예: 거래내역/청구서 라인아이템)
- Human-in-the-loop(검수 UI)까지 고려한 **확률적 파이프라인**을 설계할 수 있을 때

### 언제 쓰면 안 되나
- 문서가 1~2종으로 고정이고 레이아웃도 안정적이라면: LLM을 넣기보다 **deterministic 규칙+검증**이 더 싸고 안전함
- 보안/규제상 원문을 외부로 못 보내거나, latency/비용이 극단적으로 민감한데 온프렘 대안이 없는 경우
- “정확도 99.9%”를 **무검수로** 요구하는 고위험 업무(세무/법무 자동 제출 등): LLM은 “그럴듯한 오답” 리스크가 있어 설계 난도가 급상승

---

## 🔧 핵심 개념
### 1) Document Understanding의 레이어 분리: OCR vs Layout vs Schema
실무적으로는 아래 3단을 분리해 생각하는 게 안정적입니다.

1. **OCR (Text recognition)**  
   이미지/PDF에서 글자를 인식. 하지만 OCR만으로는 “이 텍스트가 어디에 속하는지”가 약합니다.

2. **Layout/Structure (Document layout analysis)**  
   페이지 내 **블록(단락/제목/헤더/푸터/표/그림)**, **reading order**, **table grid**를 추출합니다. Microsoft가 말하는 “hierarchical document structure analysis”가 여기고, RAG에서도 chunk를 잘 자르려면 이 계층 구조가 중요합니다([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?country=us&culture=en-us&view=doc-intel-3.1.0&utm_source=openai)).

3. **Schema mapping (Structured extraction)**  
   “InvoiceNumber”, “LineItems[]”, “Tax”, “Total” 같은 **업무 스키마**로 매핑.  
   2026년 트렌드는 여기서 LLM을 “추출기”로 쓰기보다 **(a) 후보 생성 + (b) validator로 강제 + (c) repair 루프**로 쓰는 패턴이 강합니다(스키마 우선/검증 우선)([arxiv.org](https://arxiv.org/abs/2604.06571?utm_source=openai)).

### 2) 왜 LLM을 OCR 자리에 두면 실패하는가 (그리고 어디에 두면 이득인가)
Visually Rich Document에서 MLLM/VLM이 유망하다는 조사도 있지만([aclanthology.org](https://aclanthology.org/2026.findings-acl.652/?utm_source=openai)), 프로덕션에서는 “OCR-free로 한 방에 끝”이 생각보다 어렵습니다.

- **문서가 길어질수록**(수십 페이지 PDF) 컨텍스트/비용/지연이 커지고, 중간 누락/왜곡이 검증하기 어려움
- 표는 특히 “grid”가 중요해서, LLM이 자연어로 요약해버리면 **셀 단위 정합성**이 깨지기 쉽습니다
- 반대로 LLM을 **schema mapping + validation/repair**에 두면:
  - 레이아웃 엔진이 뽑은 근거(텍스트/좌표/셀)를 기반으로 **정규화**를 잘함
  - “규칙으로 커버하기 어려운 예외(약어/단위/표 헤더 변형)”를 흡수 가능

Google의 “Gemini layout parser”는 이 간극을 줄이려고, OCR/레이아웃 파싱 자체에 generative LLM을 결합한 형태로 보입니다(레이아웃 요소/테이블 구조 등 파싱)([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai)). 즉, LLM을 완전 대체재가 아니라 **구조 추출의 품질 부스터**로 쓰는 접근입니다.

### 3) Table/PDF 처리에서 핵심 난제 3가지
1. **Merged cells / multi-row headers**: 헤더가 2~3줄로 쌓이거나 병합되면 “컬럼 의미”가 흔들림  
2. **Cross-page tables**: 페이지 넘어가면서 헤더 반복/생략, subtotal/continued 등장  
3. **PDF 텍스트 레이어 함정**: “스캔 PDF + hidden text layer”처럼 혼종이면 extractor가 잘못된 레이어를 우선해 오염될 수 있음

최근 연구에서도 “전통적(heuristic) 파이프라인이 비용/설명가능성 측면에서 다시 경쟁력”이 있다는 주장까지 나옵니다(예: SPARTAN은 GPU/학습 없이도 고정밀 table extraction을 목표)([nature.com](https://www.nature.com/articles/s41598-026-44325-7?utm_source=openai)). 결론은: **LLM만이 답이 아니라, 파이프라인 전체를 비용/성능/검증성으로 최적화**해야 합니다.

---

## 💻 실전 코드
아래 예제는 “대량 PDF(은행명세서/청구서)에서 표 포함 내용을 추출 → LLM으로 스키마(JSON)로 정규화 → Pydantic으로 검증 → 실패 시 재시도”까지를 현실적으로 엮은 형태입니다.

- OCR/Layout: **AWS Textract AnalyzeDocument** (TABLES + FORMS)
- Schema mapping: **LLM(Chat Completions 계열 가정)**  
  - 실제로는 OpenAI/Azure OpenAI/Bedrock 등 어떤 LLM이든 대체 가능
- 검증: **pydantic**
- 포인트: LLM 입력에는 “원문 전체”가 아니라 **Textract가 준 table cell + key-value**를 압축해 넣습니다(비용/안정성).

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate

pip install boto3 pydantic==2.* tenacity python-dotenv
# LLM SDK는 예시로 openai를 가정(대체 가능)
pip install openai
```

`.env`
```bash
AWS_REGION=us-east-1
OPENAI_API_KEY=YOUR_KEY
LLM_MODEL=gpt-4.1-mini
```

### 1) Textract로 표/폼 구조 추출 → “근거 기반” 중간 표현 만들기
```python
import os, json
import boto3
from dotenv import load_dotenv

load_dotenv()
REGION = os.environ["AWS_REGION"]

textract = boto3.client("textract", region_name=REGION)

def analyze_pdf_bytes(pdf_bytes: bytes) -> dict:
    # TABLES + FORMS를 함께 켜야 key-value(폼)와 표를 같이 얻기 좋습니다.
    resp = textract.analyze_document(
        Document={"Bytes": pdf_bytes},
        FeatureTypes=["TABLES", "FORMS"],
    )
    return resp

def build_intermediate(textract_json: dict) -> dict:
    """
    LLM에 바로 던질 '압축된 근거'를 구성합니다.
    - full raw blocks를 던지지 말고, 테이블은 (row,col,text)로 평탄화
    - key-value는 (key,text,value,text)로 정리
    """
    blocks = {b["Id"]: b for b in textract_json["Blocks"]}
    tables = []
    kvs = []

    # 1) Key-Value 추출(간단화: KEY_VALUE_SET만)
    for b in textract_json["Blocks"]:
        if b["BlockType"] == "KEY_VALUE_SET" and "KEY" in b.get("EntityTypes", []):
            key_text = _collect_text_from_relationships(blocks, b.get("Relationships", []))
            value_text = ""
            for rel in b.get("Relationships", []):
                if rel["Type"] == "VALUE":
                    for vid in rel["Ids"]:
                        vb = blocks[vid]
                        value_text = _collect_text_from_relationships(blocks, vb.get("Relationships", []))
            if key_text.strip():
                kvs.append({"key": key_text.strip(), "value": value_text.strip()})

    # 2) Table 추출: TABLE -> CELL -> WORD
    for b in textract_json["Blocks"]:
        if b["BlockType"] == "TABLE":
            cell_rows = []
            for rel in b.get("Relationships", []):
                if rel["Type"] == "CHILD":
                    for cid in rel["Ids"]:
                        cb = blocks[cid]
                        if cb["BlockType"] != "CELL":
                            continue
                        text = _collect_text_from_relationships(blocks, cb.get("Relationships", []))
                        cell_rows.append({
                            "row": cb.get("RowIndex"),
                            "col": cb.get("ColumnIndex"),
                            "rowSpan": cb.get("RowSpan", 1),
                            "colSpan": cb.get("ColumnSpan", 1),
                            "text": text.strip(),
                        })
            # row/col로 정렬
            cell_rows.sort(key=lambda x: (x["row"], x["col"]))
            tables.append({"cells": cell_rows})

    return {"key_values": kvs, "tables": tables}

def _collect_text_from_relationships(blocks: dict, rels: list) -> str:
    out = []
    for rel in rels or []:
        if rel["Type"] == "CHILD":
            for cid in rel["Ids"]:
                cb = blocks[cid]
                if cb["BlockType"] == "WORD":
                    out.append(cb["Text"])
                elif cb["BlockType"] == "SELECTION_ELEMENT":
                    if cb.get("SelectionStatus") == "SELECTED":
                        out.append("[X]")
    return " ".join(out)
```

예상 중간 출력(요약):
```json
{
  "key_values": [{"key":"Account Number","value":"123-45-6789"}, ...],
  "tables": [
    {"cells":[{"row":1,"col":1,"text":"Date"}, {"row":1,"col":2,"text":"Description"}, ...]}
  ]
}
```

### 2) LLM으로 “업무 스키마” JSON 추출 + Pydantic 검증 + repair 루프
```python
from typing import List, Optional
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = os.environ.get("LLM_MODEL", "gpt-4.1-mini")

class LineItem(BaseModel):
    date: str
    description: str
    amount: float
    currency: str = "USD"

class Statement(BaseModel):
    account_number: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    line_items: List[LineItem] = Field(default_factory=list)
    total_amount: Optional[float] = None

SYSTEM = """You are a senior document extraction engine.
You MUST output valid JSON only, matching the provided schema.
Do not hallucinate: if a field is not present, use null/empty.
Numbers: parse as float. Currency: infer from symbols if present else USD.
Table: prefer table cells for line_items. Preserve sign for debits/credits.
"""

def llm_extract_statement(intermediate: dict, last_error: str | None = None) -> dict:
    schema_hint = Statement.model_json_schema()
    user = {
        "schema": schema_hint,
        "intermediate": intermediate,
        "notes": "If table header is multi-row, treat the last header row as column names.",
        "last_error": last_error,
    }

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        temperature=0,
    )
    content = resp.choices[0].message.content
    return json.loads(content)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def extract_with_validation(intermediate: dict) -> Statement:
    last_error = None
    for _ in range(2):  # 한 번 더 repair 기회
        raw = llm_extract_statement(intermediate, last_error=last_error)
        try:
            return Statement.model_validate(raw)
        except ValidationError as e:
            last_error = str(e)
    # 마지막 시도에서 실패하면 예외로 올려서 retry(tenacity)로 재시도
    raise ValueError(f"Extraction failed: {last_error}")
```

### 3) 엔드투엔드 실행(파일 입력 → 결과 저장)
```python
def run(pdf_path: str, out_path: str):
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    tex = analyze_pdf_bytes(pdf_bytes)
    intermediate = build_intermediate(tex)

    statement = extract_with_validation(intermediate)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(statement.model_dump_json(indent=2, ensure_ascii=False))

if __name__ == "__main__":
    run("samples/bank_statement.pdf", "out/statement.json")
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “구조 추출”과 “의미 추출”을 분리하고, LLM에는 근거를 압축해서 넣기
- 원문 PDF를 통째로 LLM에 넣는 방식은 비용/지연/누락 리스크가 큽니다.
- 대신 Textract/Document Intelligence/Document AI 같은 엔진에서 **reading order + tables + key-values**를 얻고, LLM은 **schema mapping + 정규화 + 예외 처리**에 집중시키세요. (Microsoft도 문서 구조 분석의 중요성을 RAG 맥락에서 반복 강조)([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?country=us&culture=en-us&view=doc-intel-3.1.0&utm_source=openai))

### Best Practice 2) Schema-first + validator-guided repair
- “LLM 출력은 항상 틀릴 수 있다”를 전제로, **Pydantic/JSON Schema/비즈니스 룰**로 강제하세요.
- 위 예제처럼 ValidationError를 LLM에 다시 주면, 단순 추출보다 **안정적으로 수렴**합니다(최근 파이프라인 연구도 유사한 패턴을 언급)([arxiv.org](https://arxiv.org/abs/2604.06571?utm_source=openai)).

### Best Practice 3) Table은 “복원”이 아니라 “정규화” 기준으로 설계
- 표를 DataFrame으로 예쁘게 재구성하는 것과, 업무에 필요한 컬럼만 정확히 뽑는 것은 다릅니다.
- 헤더가 흔들리는 문서라면, LLM에게 “헤더 후보 목록을 만들고 컬럼 매핑”을 시키는 편이 유지보수에 유리합니다(표 추출 파이프라인에서 LLM을 보조로 쓰는 아이디어가 실제로 등장)([nature.com](https://www.nature.com/articles/s41598-026-44325-7?utm_source=openai)).

### 흔한 함정/안티패턴
- **confidence score 맹신**: OCR/추출 confidence가 높아도 “문맥상 틀린 값”이 나옵니다. 특히 손글씨 수정/취소선 같은 케이스에서 silent failure가 발생하기 쉽습니다(현업 경험담에서도 반복)([reddit.com](https://www.reddit.com/r/documentAutomation/comments/1tt0ujj/one_thing_i_learned_while_building_a_document/?utm_source=openai)).
- **multi-page 문서에서 page boundary 무시**: “표가 페이지를 넘는 순간” 품질이 급락합니다. 페이지별로 처리 후 이어 붙이려면, “header 반복/continued” 규칙과 합치기 전략이 필요합니다.
- **비용 폭주**: LLM을 “원문+이미지”로 호출하면 토큰/이미지 비용이 폭발합니다. 먼저 레이아웃 엔진으로 압축하고, LLM 호출을 “문서당 1~2회”로 제한하는 설계가 현실적입니다.

### 비용/성능/안정성 트레이드오프(현실적인 판단 기준)
- **최저 비용/최고 처리량**이 목표면: 전통 OCR+heuristic/table pipeline도 다시 검토 가치가 있습니다(학습/GPU 없이도 경쟁력을 주장하는 연구가 나옴)([nature.com](https://www.nature.com/articles/s41598-026-44325-7?utm_source=openai)).
- **문서 다양성/예외 처리**가 핵심이면: Layout 엔진 + LLM 정규화가 총비용(TCO) 관점에서 유리해지는 경우가 많습니다.
- **감사/설명가능성**이 필요하면: “LLM이 읽고 요약”이 아니라, “레이아웃 근거 기반으로 schema 매핑” + “검증 로그/근거 좌표 저장”을 남기세요.

---

## 🚀 마무리
정리하면, 2026년 7월 기준 “OCR Document AI + LLM”의 정답은 **LLM 올인**이 아니라:

- (1) Textract/Document Intelligence/Document AI 같은 엔진으로 **텍스트+레이아웃+표 구조를 안정적으로 추출**하고([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?country=us&culture=en-us&view=doc-intel-3.1.0&utm_source=openai))  
- (2) LLM은 **schema-first 정규화 + validation/repair**에 배치해서  
- (3) 표/멀티페이지/예외 케이스를 “검증 가능한 형태”로 수렴시키는 설계입니다.

도입 판단 기준은 간단합니다.
- 문서 유형/레이아웃이 계속 늘고, 규칙 기반 유지보수가 한계를 보이면: **하이브리드(Structure → LLM schema)** 로 가는 게 맞습니다.
- 문서가 고정이고 정확도가 절대적으로 중요하면: LLM은 최소화하고, deterministic + 검수/감사를 강화하세요.

다음 학습 추천:
- “Visually Rich Document + MLLM” 동향을 잡고 싶다면 관련 survey를 먼저 훑고([aclanthology.org](https://aclanthology.org/2026.findings-acl.652/?utm_source=openai)),
- 실제 프로덕션 운영 관점(마이크로서비스/스케일링/재처리/관측성)은 운영 아키텍처 논문류를 참고해 파이프라인을 설계하는 게 도움이 됩니다([arxiv.org](https://arxiv.org/abs/2605.18818?utm_source=openai)).

원하시면, (A) Google Document AI(Gemini layout parser) 기반으로 동일한 파이프라인을 재작성하거나([docs.cloud.google.com](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk?utm_source=openai)), (B) “표가 페이지를 넘는 bank statement”를 기준으로 cross-page table stitching 전략(헤더 정렬/continued 감지/라인아이템 정규화)을 더 깊게 확장해 드릴 수 있습니다.