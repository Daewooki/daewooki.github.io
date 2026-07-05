---
title: "배치 추론으로 LLM 비용을 “반값”으로 만드는 법: 2026년 7월 Batch Inference API 비용·파이프라인 심층 가이드"
date: 2026-07-05 04:08:59 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-07]
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
LLM을 프로덕션에 붙여 “대량 요청(수십만~수천만 건)”을 처리하려는 순간, 비용과 처리량 문제가 동시에 터집니다. 동기(synchronous) 호출로는 **QPS 한계, 스로틀링, 재시도 폭주, 피크 시간 비용**이 겹치고, 무엇보다 “지금 당장”이 아닌 작업(리포트 생성, 로그 요약, 제품 카탈로그 정규화, 오프라인 평가/라벨링, 백필(backfill) 작업)에 동기 호출을 쓰는 건 거의 낭비가 됩니다.

**Batch inference(비동기 배치 추론)**가 해결하는 문제는 명확합니다.

- **비용**: 대표적으로 OpenAI Batch API는 표준 API 대비 **입·출력 토큰 모두 50% 할인**이 공식 정책입니다. ([help.openai.com](https://help.openai.com/en/articles/9197833-batch-api-faq%3F.midi?utm_source=openai))  
- **처리 안정성**: 요청을 파일 단위로 모아 제출하고, 결과도 파일로 받는 구조라 **재시도/부분 실패/정산**을 파이프라인으로 다루기 좋습니다.
- **대량 처리 UX**: “온라인 트래픽”이 아니라 “잡(job)”으로 다루므로, 큐/워크플로 엔진과 궁합이 좋습니다.

반대로, 아래 케이스에는 Batch가 **부적합**합니다.

- **저지연 인터랙션**(채팅/에이전트 루프): Batch는 본질적으로 비동기이며(예: OpenAI는 24시간 내 처리 목표), 스트리밍 응답이 필요하면 맞지 않습니다. ([help.openai.com](https://help.openai.com/en/articles/9197833-batch-api-faq%3F.midi?utm_source=openai))
- **툴 호출(function calling) 의존 파이프라인**: 제공자/제품에 따라 Batch에서 tool calling, structured output 등이 제한될 수 있습니다(예: Bedrock 문서에 Batch는 tool calling 미지원 명시). ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html?linkId=665046301&sc_campaign=Support&sc_channel=sm&sc_content=Support&sc_country=global&sc_geo=GLOBAL&sc_outcome=AWS+Support&sc_publisher=REDDIT&trk=Support&utm_source=openai))
- **즉시성 SLA가 중요한 운영 자동화**: “언제 끝날지”가 변수인 작업을 핵심 경로에 넣으면 장애가 됩니다.

---

## 🔧 핵심 개념
### 1) 주요 개념 정의
- **Batch inference**: 다수의 요청을 모아 “배치 작업”으로 제출하고, 제공자가 내부 스케줄링으로 처리한 뒤 결과를 비동기로 반환.
- **비용 단가(Per-token pricing)**: 대부분 제공자는 입력/출력 토큰 단가가 분리되어 있고, 출력이 더 비싼 편입니다. OpenAI는 Batch 모드에서 “표준 대비 50% 절감”을 명시합니다. ([openai.com](https://openai.com/pl-PL/api/pricing/?utm_source=openai))
- **캐시(prompt caching)**: 동일/유사 프롬프트를 반복 호출할 때 할인되는 별도 메커니즘(벤더별 명칭/조건 상이). 비용 최적화는 보통 **Batch + caching** 조합에서 폭발합니다(단, 캐시 적중률이 낮으면 의미 없음).

### 2) 내부 작동 방식(구조/흐름)
Batch는 “API 호출”이라기보다 “ETL 잡”에 가깝습니다.

1. **입력 레코드 준비**  
   보통 JSONL(한 줄당 한 요청) 형태로 `custom_id`(추적 키)와 모델/프롬프트/파라미터를 넣습니다.
2. **배치 제출**  
   벤더는 입력 파일을 받아 내부 큐에 올립니다(동기 API처럼 즉시 토큰을 소비하는 느낌이 아니라, 제출/상태조회/완료 이벤트로 관리).
3. **비동기 처리(스케줄링)**  
   제공자는 오프피크/여유 용량을 활용해 처리합니다. 이게 “할인”의 경제적 근거입니다(시간은 양보, 비용은 절감).
4. **출력 파일 생성 & 회수**  
   결과는 다시 JSONL로 떨어지는 경우가 많고, 성공/실패가 레코드 단위로 섞일 수 있습니다. 따라서 “전체 실패”가 아니라 **부분 실패를 전제로 한 설계**가 필수입니다.

### 3) 다른 접근과의 차이점
- **동기 API + 내부 큐**: 직접 SQS/Kafka로 큐잉하고 워커에서 동기 호출을 해도 “비동기 파이프라인”은 만들 수 있습니다. 하지만 **토큰 단가 할인**은 못 받습니다(벤더 Batch 할인은 Batch 엔드포인트를 써야 적용).
- **클라우드 Batch (Bedrock/Vertex 등)**: AWS Bedrock도 Batch inference를 제공하고 “on-demand 대비 50% 낮은 가격”을 안내합니다. ([aws.amazon.com](https://aws.amazon.com/bedrock/pricing/?refid=5eef8ffa-5155-4b81-9303-69672b9516c1&utm_source=openai))  
  다만 Bedrock은 S3 입출력, 쿼터, 모델/리전 제약 같은 “클라우드 운영 요소”가 비용/복잡도를 추가할 수 있어, 순수 토큰 단가만 비교하면 사고 납니다.
- **Anthropic Message Batches**: Anthropic도 배치당 최대 10,000 쿼리, 24시간 내 처리, 50% 할인 구조를 공식 발표로 설명했습니다. ([anthropic.com](https://www.anthropic.com/news/message-batches-api?_bhlid=d7a971ecc142113bfa1d17304a438e3b79a60500&utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “**대량 고객 상담 로그를 요약+태깅해서 BigQuery/DB에 적재**” 같은 현실적인 오프라인 잡을 가정합니다.

- 입력: 하루치 상담 로그 300,000건(예: S3/GCS가 아니라 로컬→오브젝트 스토리지 업로드도 가능)
- 출력: `{ticket_id, summary, sentiment, categories}` 형태
- 요구: **비용 최적화(배치)** + **부분 실패 재처리** + **아이템 단위 추적**

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate
pip install openai==1.* tenacity python-dotenv
export OPENAI_API_KEY="..."
```

### 1) JSONL 입력 파일 생성 (현실적인 레코드 + idempotency 키)
```python
# build_batch_input.py
import json
from pathlib import Path

INPUT_PATH = Path("batch_input.jsonl")

def iter_tickets():
    # 현실에서는 DB/Parquet/S3에서 스트리밍으로 읽음
    for i in range(1, 10001):
        yield {
            "ticket_id": f"TCK-{i:07d}",
            "messages": [
                {"role": "system", "content": "You are a support analyst. Output JSON only."},
                {"role": "user", "content": f"""
다음 상담 로그를 1) 3문장 요약 2) sentiment(positive/neutral/negative)
3) 카테고리(최대 3개)로 구조화해줘.

[상담 로그]
고객: 배송이 아직 안 왔어요. 3일 지났는데요.
상담원: 송장 조회해드릴게요...
(중략) #{i}
"""}
            ],
        }

with INPUT_PATH.open("w", encoding="utf-8") as f:
    for t in iter_tickets():
        # custom_id는 나중에 결과를 원본과 join할 핵심 키
        record = {
            "custom_id": t["ticket_id"],
            "method": "POST",
            "url": "/v1/responses",
            "body": {
                "model": "gpt-5.4-mini",
                "input": t["messages"],
                # structured output이 Batch에서 제한될 수 있는 벤더도 있어
                # 여기서는 "JSON only"를 강제하는 방식으로 설계
                "temperature": 0.2,
                "max_output_tokens": 300,
            },
        }
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"Wrote: {INPUT_PATH} (jsonl)")
```

예상 결과:
- `batch_input.jsonl` 생성(10,000라인)
- 각 라인은 `custom_id`로 추적 가능

### 2) Batch 업로드/생성 → 상태 폴링 → 결과 다운로드
```python
# run_batch.py
import json
import time
from pathlib import Path
from openai import OpenAI

client = OpenAI()

INPUT_PATH = Path("batch_input.jsonl")
OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)

def create_batch():
    # 1) 입력 파일 업로드
    uploaded = client.files.create(
        file=INPUT_PATH.open("rb"),
        purpose="batch",
    )

    # 2) Batch 생성 (responses 엔드포인트를 배치로 실행)
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={"job": "support_ticket_summarize_v1", "date": "2026-07-05"},
    )
    return batch.id

def wait_batch(batch_id: str, poll_sec=10):
    while True:
        b = client.batches.retrieve(batch_id)
        print(f"[{b.status}] completed={b.completed_requests} failed={b.failed_requests}")
        if b.status in ("completed", "failed", "cancelled", "expired"):
            return b
        time.sleep(poll_sec)

def download_file(file_id: str, path: Path):
    content = client.files.content(file_id)
    path.write_bytes(content.read())

if __name__ == "__main__":
    batch_id = create_batch()
    print("batch_id =", batch_id)

    final = wait_batch(batch_id)

    # 결과는 output_file_id / error_file_id 등으로 분리되는 경우가 많음
    if final.output_file_id:
        download_file(final.output_file_id, OUT_DIR / "output.jsonl")
        print("downloaded output.jsonl")

    if final.error_file_id:
        download_file(final.error_file_id, OUT_DIR / "error.jsonl")
        print("downloaded error.jsonl")
```

예상 출력(예시):
- `[in_progress] completed=1200 failed=3`
- `[completed] completed=10000 failed=12`
- `out/output.jsonl`, `out/error.jsonl` 생성

### 3) 결과 머지 + 실패 레코드만 재배치(핵심 운영 패턴)
```python
# merge_and_retry.py
import json
from pathlib import Path

OUT_DIR = Path("out")
OUTPUT = OUT_DIR / "output.jsonl"
ERRORS = OUT_DIR / "error.jsonl"

def load_jsonl(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

ok = load_jsonl(OUTPUT)
err = load_jsonl(ERRORS)

# 1) 성공 결과를 ticket_id 기준으로 머지할 dict 만들기
by_id = {}
for r in ok:
    ticket_id = r.get("custom_id")
    # OpenAI Responses API 결과 포맷에 맞게 필요한 필드만 뽑아 저장
    # (벤더/버전마다 다를 수 있어, 실제로는 r 구조를 로그로 확인 후 고정)
    by_id[ticket_id] = r

print("ok =", len(ok), "err =", len(err))

# 2) 실패만 재시도 입력 파일로 재생성
# (중요) 재시도는 “원본 입력 그대로”가 아니라,
# - 원인(토큰 초과, 안전필터, 일시 오류)에 맞춘 파라미터 조정이 필요
retry_path = Path("batch_retry.jsonl")
with retry_path.open("w", encoding="utf-8") as f:
    for e in err:
        # 에러 레코드에도 보통 custom_id가 들어있음
        custom_id = e.get("custom_id")
        req = e.get("request")  # 벤더에 따라 다를 수 있음
        if not custom_id or not req:
            continue

        body = req["body"]
        body["max_output_tokens"] = min(body.get("max_output_tokens", 300), 200)
        body["temperature"] = 0.0  # 재현성/안정성 우선

        f.write(json.dumps({
            "custom_id": custom_id,
            "method": "POST",
            "url": req["url"],
            "body": body
        }, ensure_ascii=False) + "\n")

print("wrote retry file:", retry_path)
```

이 “실패만 재배치” 패턴이 중요한 이유:
- 대량 처리에서 실패는 0이 되기 어렵고,
- 전체를 다시 돌리면 비용이 2배가 됩니다.
- 결국 **레코드 단위 idempotency + 부분 재처리**가 배치 파이프라인의 핵심입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **배치 크기 = “운영 단위”로 잡기 (10k~100k 단위)**
- 너무 작으면 업로드/관리 오버헤드가 커지고, 너무 크면 “실패 재처리”가 무거워집니다.
- 운영적으로는 “하루치/시간대별/테넌트별”로 쪼개면 정산/롤백이 쉬워집니다.

2) **custom_id를 업무 PK로 고정하고, 결과 스키마를 join-friendly하게**
- 결과 파일은 결국 데이터 파이프라인에 들어갑니다.
- `ticket_id`, `doc_id`, `row_hash` 같은 키가 없으면 **재처리/중복 제거**가 지옥이 됩니다.

3) **비용 모델을 “입력:출력 비율”로 먼저 산정**
- 대부분 출력 토큰이 훨씬 비싸고(예: OpenAI 가격표는 입력/출력 분리), 장문 생성은 비용이 폭증합니다. ([openai.com](https://openai.com/pl-PL/api/pricing/?utm_source=openai))  
- 따라서 배치 할인(50%)만 믿지 말고,
  - `max_output_tokens` 캡
  - “요약→태깅”처럼 출력 짧은 태스크로 재설계
  - 필요하면 2-pass(저가 모델로 1차 정제 후 고가 모델로 일부만 재처리)
  를 같이 해야 “대량 처리 비용”이 예측 가능합니다.

### 흔한 함정/안티패턴
- **Batch로 에이전트 작업을 돌리려는 시도**: tool calling/structured output 제약이 걸릴 수 있고(특히 Bedrock 문서처럼 명시된 경우), 스트리밍이 없어서 디버깅도 힘듭니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html?linkId=665046301&sc_campaign=Support&sc_channel=sm&sc_content=Support&sc_country=global&sc_geo=GLOBAL&sc_outcome=AWS+Support&sc_publisher=REDDIT&trk=Support&utm_source=openai))
- **결과 파일을 “그냥 저장”하고 끝내기**: 반드시
  - 성공/실패 분리 적재
  - 실패 원인별 재시도 정책
  - 중복 방지(idempotency)
  을 데이터 엔지니어링 레이어로 고정해야 합니다.
- **토큰 추정 없이 덤프**: 1M 요청에서 프롬프트가 200토큰 늘면(입력만) 바로 “수억 토큰”이 추가됩니다. 배치로 반값이어도 절대액은 큽니다.

### 비용/성능/안정성 트레이드오프(핵심)
- **비용↓**: OpenAI Batch는 표준 대비 50% 할인(입·출력 모두)이라는 “확정된 레버”가 있습니다. ([help.openai.com](https://help.openai.com/en/articles/9197833-batch-api-faq%3F.midi?utm_source=openai))
- **지연↑**: 24h completion window 같은 비동기 특성 때문에 “언제 끝날지”가 변수입니다. ([help.openai.com](https://help.openai.com/en/articles/9197833-batch-api-faq%3F.midi?utm_source=openai))
- **운영 복잡도↑**: 파일 기반 입출력, 부분 실패, 재처리 파이프라인이 필수입니다.
- **처리량/쿼터**: 동기 API에서 겪던 레이트리밋 문제를 완화하지만, 대신 “배치 큐/쿼터/모델 지원 범위” 제약이 생깁니다(모델별 지원 여부 확인 필요). ([help.openai.com](https://help.openai.com/en/articles/9197833-batch-api-faq%3F.midi?utm_source=openai))

---

## 🚀 마무리
2026년 7월 기준으로 “LLM 대량 처리 비용”을 줄이는 가장 현실적인 1순위는 **Batch inference로 오프라인 워크로드를 분리**하는 겁니다. OpenAI는 Batch API가 **표준 대비 50% 할인**이며 비동기 처리(24시간 창)를 전제로 한다는 점을 공식 FAQ/가격 페이지에서 명확히 합니다. ([help.openai.com](https://help.openai.com/en/articles/9197833-batch-api-faq%3F.midi?utm_source=openai))  
Anthropic과 AWS Bedrock도 “배치/비동기 + 할인”을 전면에 두고 있어, 업계 표준 패턴으로 굳어진 상황입니다. ([anthropic.com](https://www.anthropic.com/news/message-batches-api?_bhlid=d7a971ecc142113bfa1d17304a438e3b79a60500&utm_source=openai))

**도입 판단 기준**은 간단합니다.
- 내 작업이 “지금 당장 응답”이 필요한가? → 그렇다면 Batch 말고 동기/스트리밍.
- 내 작업이 “대량·반복·오프라인”인가? → Batch가 기본값.
- 실패/중복/재처리를 데이터 파이프라인으로 감쌀 준비가 되었나? → 준비가 안 됐으면 비용 절감보다 운영 사고가 먼저 옵니다.

다음 학습 추천:
- (1) 배치 결과를 데이터 웨어하우스에 적재하는 **idempotent upsert 패턴**
- (2) 비용을 결정하는 **token accounting(입력/출력/캐시) 모델링**
- (3) 워크플로 오케스트레이션(Airflow/Temporal)로 **재처리/백필/부분 실패 자동화**

원하시면, 위 예제를 “S3/GCS에 입력/출력 파일 자동 적재 + Airflow DAG(또는 Temporal workflow) + 비용 리포트(토큰/달러) 생성”까지 확장한 버전으로 이어서 작성해드릴게요.