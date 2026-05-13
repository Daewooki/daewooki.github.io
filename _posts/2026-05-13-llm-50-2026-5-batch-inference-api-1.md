---
title: "배치 추론으로 LLM 비용 50% 줄이기: 2026년 5월 “Batch Inference API” 대량 처리 비용 설계 가이드"
date: 2026-05-13 04:02:35 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-05]
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
LLM을 “대량 처리”로 쓰는 순간 비용과 운영 난이도가 동시에 폭발합니다. 예를 들어 **수십만~수천만 건의 문서 요약/분류**, **로그/CS 티켓 자동 태깅**, **상품 카탈로그 정규화**, **오프라인 평가(Eval) 파이프라인**처럼 *지금 당장 사용자에게 응답할 필요는 없지만* 처리량이 큰 작업은, 실시간 API(online inference)로 돌리면 **단가가 비싸고**, **rate limit에 걸리고**, **재시도/중복 처리로 낭비**가 생깁니다.

2026년 5월 기준으로 주요 사업자들이 공통적으로 제공하는 해법이 **batch inference (비동기 배치 추론)** 입니다. 핵심은 간단합니다.

- **“최대 24시간 내 처리” 같은 SLA를 받아들이는 대신**
- **토큰 단가를 할인(대표적으로 50%)** 받고
- **대량 요청을 큐/잡 형태로 비동기 처리**한다

OpenAI는 Batch API에 대해 “입력/출력 토큰 모두 50% 절감, 24시간 비동기 처리”를 명시하고 있고, ([openai.com](https://openai.com/api/pricing/))  
AWS Bedrock도 “batch inference는 on-demand 대비 50% 낮은 가격”을 공식 가격 페이지에 명시합니다. ([aws.amazon.com](https://aws.amazon.com/bedrock/pricing/?nc1=h_ls))

언제 쓰면 좋나?
- **오프라인/비실시간**: 하루 1~2회 돌리는 ETL/리포트/정제 작업
- **재처리 가능**: 실패해도 재시도해도 되는 파이프라인
- **단가 민감**: 토큰이 곧 돈인 워크로드(요약/추출/분류/스코어링)

언제 쓰면 안 되나?
- **사용자 대기 시간이 곧 UX**인 기능(채팅, 에이전트 상호작용)
- **즉시성+낮은 지연**이 필수인 트래픽(서버 사이드 동기 요청)
- **작업 단위가 너무 작고(토큰 적음) 오버헤드가 더 큰 경우**: 배치 잡 생성/폴링/결과 수집 비용이 상대적으로 커질 수 있음

---

## 🔧 핵심 개념
### 1) Batch inference의 정의(“비동기 잡 + 할인 토큰”)
Batch inference는 실시간 endpoint에 1요청=1응답으로 붙는 대신,
1) 요청들을 **파일/리스트로 모아 제출(submit)**  
2) 서버가 내부적으로 **스케줄링/큐잉** 해서 처리  
3) 일정 시간 내에 **결과 파일(또는 결과 리스트)** 를 제공하는 모델입니다.

OpenAI는 Batch API를 “24시간 비동기 처리 + 입력/출력 50% 할인”으로 포지셔닝합니다. ([openai.com](https://openai.com/api/pricing/))  
또한 Batch API의 rate limit이 기존(동기) API와 **완전히 분리**된다고 명시되어, 대량 처리 파이프라인을 별도 레인으로 빼기 좋습니다. ([help.openai.com](https://help.openai.com/en/articles/9197833-batch-api-faq%23.gz))

AWS Bedrock도 동일한 경제 논리로 “select FMs batch inference 50% lower price”를 명시하며, 실제 가격 테이블에서 on-demand와 batch의 입력/출력 토큰 단가가 반으로 내려간 예(예: Claude 3.5 Sonnet input/output $6/$30 → batch $3/$15)가 보입니다. ([aws.amazon.com](https://aws.amazon.com/bedrock/pricing/?nc1=h_ls))

### 2) 내부 작동 방식(구조/흐름)
실무적으로는 아래 흐름으로 이해하면 설계가 쉬워집니다.

- **(A) Ingestion**: 처리할 레코드(문서, 티켓, 상품 등)를 읽고 “LLM 요청 1건” 단위로 쪼갬  
- **(B) Batching**: N건을 모아 batch job 생성(대개 JSONL)  
- **(C) Submit**: provider에 batch job 제출 → job_id 반환  
- **(D) Async execution**: provider 내부 큐에서 실행(혼잡도에 따라 지연)  
- **(E) Collection**: 완료 이벤트/폴링으로 결과 다운로드  
- **(F) Post-processing**: 결과 파싱, 검증, 재시도 대상 분리, 저장(예: S3/GCS/DB)

중요 포인트는 “할인”이 단순 마케팅이 아니라, **사업자가 백그라운드 큐에서 더 효율적으로 GPU/TPU를 채울 수 있기 때문에** 가능하다는 점입니다. 즉, 여러분은 *지연을 비용으로 바꾸는* 트레이드오프를 선택하는 겁니다.

### 3) 다른 접근과의 차이
- **동기 API + 클라이언트 측 병렬화**
  - 장점: 즉시 응답, 구현 단순
  - 단점: rate limit/429, 폭주 제어 어려움, 단가 비쌈, 실패 재처리 설계가 난해
- **자체 호스팅(vLLM/TGI)**
  - 장점: 일정 규모 이상이면 단가 통제 가능, 커스텀 가능
  - 단점: 운영(스케일링/모니터링/장애) 비용, 피크 대비 프로비저닝, 모델 업데이트 부담
- **Batch inference API**
  - 장점: (대부분) **토큰 단가 할인(대표 50%)**, 대량 처리에 최적화, rate limit 분리 ([openai.com](https://openai.com/api/pricing/))
  - 단점: 결과 지연(최대 24h), 잡 단위 오케스트레이션 필요, 부분 실패 처리 설계 필요

---

## 💻 실전 코드
아래 예시는 “CS 티켓 50만 건을 하루 1회 요약+라벨링”하는 현실적인 배치 파이프라인입니다. 포인트는 **(1) JSONL로 요청을 만들고 (2) Batch Job을 제출한 뒤 (3) 완료되면 결과를 내려받아 DB에 upsert** 하는 구조입니다.

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate
pip install openai sqlalchemy psycopg[binary] tenacity tqdm
export OPENAI_API_KEY="..."
export DATABASE_URL="postgresql+psycopg://user:pass@host:5432/app"
```

### 1) 배치 입력(JSONL) 만들기 + Batch 제출
```python
# batch_submit.py
import os, json
from openai import OpenAI
from sqlalchemy import create_engine, text
from tqdm import tqdm

MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")  # 예시: 실제 사용 모델로 교체
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20000"))

client = OpenAI()
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

PROMPT_TMPL = """You are a senior support analyst.
Summarize the ticket in Korean (<= 3 lines) and assign:
- category: one of [billing, bug, feature, account, abuse, other]
- severity: one of [low, medium, high, critical]
Return strict JSON with keys: summary, category, severity.
Ticket:
{body}
"""

def fetch_tickets(limit: int):
    q = text("""
      select id, body
      from support_tickets
      where llm_processed_at is null
      order by created_at asc
      limit :limit
    """)
    with engine.begin() as conn:
        return conn.execute(q, {"limit": limit}).mappings().all()

def build_jsonl(rows, path: str):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            # custom_id로 결과를 원본 레코드와 안정적으로 조인
            req = {
                "custom_id": f"ticket:{r['id']}",
                "method": "POST",
                "url": "/v1/responses",
                "body": {
                    "model": MODEL,
                    "input": PROMPT_TMPL.format(body=r["body"]),
                    # 출력 폭주 방지: 상한은 비용/품질 트레이드오프의 핵심 레버
                    "max_output_tokens": 200,
                }
            }
            f.write(json.dumps(req, ensure_ascii=False) + "\n")

def main():
    rows = fetch_tickets(BATCH_SIZE)
    if not rows:
        print("No pending tickets.")
        return

    jsonl_path = "tickets_batch.jsonl"
    build_jsonl(rows, jsonl_path)
    print(f"Wrote {len(rows)} requests to {jsonl_path}")

    # 1) 파일 업로드
    with open(jsonl_path, "rb") as f:
        input_file = client.files.create(file=f, purpose="batch")

    # 2) batch 생성(비동기)
    batch = client.batches.create(
        input_file_id=input_file.id,
        endpoint="/v1/responses",
        completion_window="24h",  # 배치 특성: 시간 여유 ↔ 비용 절감
        metadata={"job": "daily_ticket_labeling"}
    )

    # 운영 관점: job_id를 DB에 저장해 추적/재처리 가능하게
    with engine.begin() as conn:
        conn.execute(
            text("insert into llm_batches(id, provider, status) values (:id,'openai',:st)"),
            {"id": batch.id, "st": batch.status}
        )

    print("Submitted batch:", batch.id, "status:", batch.status)

if __name__ == "__main__":
    main()
```

예상 출력(예):
- `Wrote 20000 requests to tickets_batch.jsonl`
- `Submitted batch: batch_... status: in_progress`

### 2) 완료 폴링 + 결과 수집 + DB upsert
```python
# batch_collect.py
import os, json, time
from openai import OpenAI
from sqlalchemy import create_engine, text
from tenacity import retry, wait_exponential, stop_after_attempt

client = OpenAI()
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

POLL_SEC = int(os.getenv("POLL_SEC", "30"))

@retry(wait=wait_exponential(min=2, max=30), stop=stop_after_attempt(10))
def download_file(file_id: str) -> bytes:
    return client.files.content(file_id).read()

def upsert_result(ticket_id: int, payload: dict):
    with engine.begin() as conn:
        conn.execute(text("""
          update support_tickets
          set llm_summary = :summary,
              llm_category = :category,
              llm_severity = :severity,
              llm_processed_at = now()
          where id = :id
        """), {
            "id": ticket_id,
            "summary": payload.get("summary"),
            "category": payload.get("category"),
            "severity": payload.get("severity"),
        })

def parse_custom_id(custom_id: str) -> int:
    # "ticket:123" -> 123
    return int(custom_id.split(":")[1])

def main(batch_id: str):
    while True:
        b = client.batches.retrieve(batch_id)
        with engine.begin() as conn:
            conn.execute(text("update llm_batches set status=:st where id=:id"),
                         {"id": batch_id, "st": b.status})

        print("status:", b.status)
        if b.status in ("completed", "failed", "cancelled", "expired"):
            break
        time.sleep(POLL_SEC)

    if b.status != "completed":
        print("Batch not completed:", b.status)
        return

    # 결과 파일 다운로드(JSONL)
    content = download_file(b.output_file_id).decode("utf-8")
    for line in content.splitlines():
        obj = json.loads(line)
        custom_id = obj["custom_id"]

        # Responses API 응답 구조는 provider별로 다를 수 있으니,
        # 실서비스에서는 스키마 버전/파서 계층을 두는 걸 추천
        raw_text = obj["response"]["output_text"]
        payload = json.loads(raw_text)

        ticket_id = parse_custom_id(custom_id)
        upsert_result(ticket_id, payload)

    print("Done collecting:", batch_id)

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “비용”은 토큰 단가보다 **출력 상한(max_output_tokens)** 이 지배한다
Batch로 50% 할인받아도, 모델이 장황하게 출력하면 비용은 다시 올라갑니다.  
실무에서는 **출력 길이를 스펙으로 고정**(예: “<= 3 lines”, “strict JSON”, `max_output_tokens`)하고, 품질이 부족하면 *모델을 키우기 전에 프롬프트/스키마/후처리를 먼저 다듬는* 게 더 싸게 먹힙니다.

### Best Practice 2) custom_id를 “도메인 키”로 설계하라 (idempotency의 시작)
배치 처리에서 가장 무서운 건 **부분 실패 + 재시도**로 인한 중복 업데이트입니다.  
`custom_id = ticket:{id}` 같은 형태로 **원본 레코드와 1:1 매핑**을 강제하면,
- 결과 수집이 순서와 무관해지고
- 재시도 시에도 upsert로 흡수 가능해집니다.

### Best Practice 3) “부분 실패 라우팅”을 기본값으로
배치 잡은 2만 건 중 200건만 실패할 수도 있습니다. 이때 전체를 재돌리면 낭비가 큽니다.  
실전에서는 결과 수집 단계에서:
- JSON 파싱 실패
- 정책/필터링으로 빈 응답
- 타임아웃/에러
를 **별도 DLQ 테이블**로 보내고, 다음 배치에서 *실패분만 재처리*하세요.

### 흔한 함정) Vertex/하이퍼스케일러는 “토큰 단가” 외 비용 요인이 섞인다
특히 GCP Vertex AI 쪽은 토큰 단가만 보고 들어갔다가, 파이프라인/잡 런/기타 서비스 비용이 섞여 “생각보다 비쌈”을 겪는 케이스가 자주 보고됩니다(공식 가격 페이지에도 배치/파이프라인 런 등 다양한 과금 축이 존재). ([cloud.google.com](https://cloud.google.com/vertex-ai/pricing))  
결론: **가격표 비교는 ‘내 파이프라인 구성 그대로’로 시뮬레이션**해야 합니다.

### 비용/성능/안정성 트레이드오프(결정 프레임)
- **최저비용**: batch inference(+50% 할인) + 실패분만 재처리
- **최저지연**: on-demand 동기 + 공격적 병렬화(단, rate limit/429 대응 필요)
- **운영 안정성**: batch + 명시적 상태 머신(Submitted → Running → Completed/Failed) + DLQ

참고로 OpenAI Batch는 “입력/출력 50% 절감”을, AWS Bedrock batch도 “on-demand 대비 50% 낮은 가격”을 공식적으로 내걸고 있으므로, 대량·비실시간이라면 **우선 batch를 기본값**으로 검토하는 게 합리적입니다. ([openai.com](https://openai.com/api/pricing/))

---

## 🚀 마무리
2026년 5월 기준 LLM 대량 처리 비용을 줄이는 가장 실전적인 방법은, **동기 호출을 버리고 batch inference로 “지연을 비용으로 환전”**하는 겁니다. OpenAI와 AWS Bedrock 모두 batch에 대해 **50% 수준의 명시적 할인**을 제공하며, 대신 비동기(최대 24h) 처리 모델을 요구합니다. ([openai.com](https://openai.com/api/pricing/))

도입 판단 기준(실무용 체크리스트):
- 요청이 **비실시간**인가? (Yes면 batch 유리)
- 월 토큰이 **수억~수십억** 단위인가? (Yes면 50% 할인 체감 큼)
- 실패/재시도/중복 처리에 대한 **idempotent 설계**가 가능한가?
- 결과 수집/후처리를 담을 **비동기 파이프라인(큐, 잡, DLQ)** 을 운영할 준비가 됐는가?

다음 학습 추천:
- “상태 머신 기반 배치 오케스트레이션”(DB 기반 job table + 리트라이 정책)
- “스키마 강제(JSON schema) + 파서/검증 계층”으로 후처리 안정성 올리기
- 비용 모델링: **(입력 토큰 + 출력 토큰 상한) × 단가 × 성공률/재시도율**로 월 예산 시뮬레이션하기

원하시면, 여러분의 실제 워크로드(레코드 수/평균 토큰/허용 지연/성공률 목표)를 기준으로 **월 비용 추정식**과 “batch 크기(BATCH_SIZE)·폴링·DLQ 정책”까지 포함한 아키텍처를 더 구체화해드릴게요.