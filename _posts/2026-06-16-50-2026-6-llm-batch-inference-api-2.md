---
title: "배치로 50% 깎고도 폭탄 청구서가 나오는 이유: 2026년 6월 LLM Batch Inference API 비용/파이프라인 심층 분석"
date: 2026-06-16 05:15:34 +0900
categories: [AI, MLOps]
tags: [ai, mlops, trend, 2026-06]
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
LLM을 “대량 처리”로 붙이는 순간, 비용 문제는 **토큰 단가**만으로 설명이 안 됩니다. 같은 모델/같은 프롬프트라도 (1) 요청을 어떻게 묶고 (2) 어디서 큐잉하며 (3) 실패·재시도·중복을 어떻게 다루는지에 따라 **월 비용이 2~5배**까지 갈립니다. 그래서 2026년 6월 시점엔 “Batch inference API(비동기 대량 처리)”가 사실상 표준 옵션이 됐고, OpenAI Batch API처럼 **입·출력 50% 할인 + 24h completion window**를 명시적으로 제공합니다. ([openai.com](https://openai.com/ro-RO/api/pricing/))

언제 쓰면 좋은가:
- **오프라인/비실시간** 작업: 문서 분류, 평가(evals), 대규모 임베딩, 로그 요약, 카탈로그 정규화 등 ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))
- **rate limit 때문에 동기 처리로는 며칠 걸리는 작업**을 하루 내에 끝내야 할 때(배치 전용 풀/헤드룸이 더 큼) ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))
- 결과가 늦어도 되며, streaming/tool calling 같은 대화형 기능이 필요 없을 때(서비스 제약을 수용 가능)

언제 쓰면 안 되는가:
- 사용자 요청에 즉시 응답해야 하는 **online serving**
- 응답 중간 스트리밍이 필요하거나, tool calling/structured output 등 **상호작용 기능 의존**이 큰 경우  
  (예: Bedrock batch inference는 tool calling/structured output을 지원하지 않는다고 명시) ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html?utm_source=openai))
- “큰 system prompt + 작은 질문”을 매 요청마다 반복하는 구조인데 **prompt caching/컨텍스트 공유 최적화 없이** 배치만 도입하려는 경우(할인보다 중복 토큰이 더 큼)

---

## 🔧 핵심 개념
### 1) Batch inference의 정의: “요청 묶기”가 아니라 “비동기 실행 계약”
Batch API는 단순히 N개를 한 번에 보내는 endpoint가 아니라, **(A) 입력을 파일로 제출 → (B) 서버가 비동기로 실행 → (C) 결과를 모아서 돌려주는** 실행 계약입니다.

- OpenAI Batch API:  
  - JSONL 파일(라인당 1요청)을 업로드(purpose=`batch`) ([platform.openai.com](https://platform.openai.com/docs/api-reference/files?api-mode=responses&utm_source=openai))  
  - `/v1/batches`로 실행(현재 completion_window는 `24h`만 지원) ([platform.openai.com](https://platform.openai.com/docs/api-reference/batch/retrieve?api-mode=responses&lang=curl&utm_source=openai))  
  - 24시간 내 완료 + **동기 대비 50% 비용 할인** ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))
- AWS Bedrock batch inference:  
  - 입력을 S3에 올리고 Job을 만들면, 결과도 S3로 떨어지는 **S3 중심 파이프라인** ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html?utm_source=openai))  
  - “레코드 독립 처리”이며 multi-turn/상호작용 기능이 제한됨 ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html?utm_source=openai))

핵심은 **“지연(24h)과 기능 제약을 받아들이는 대신, 비용과 처리량을 산다”** 입니다.

### 2) 왜 50% 할인인데도 ‘대량 처리 비용’이 폭발할까?
2026년 6월 기준, OpenAI는 Batch에 대해 “입력+출력 50% 절감”을 명확히 안내하지만 ([openai.com](https://openai.com/ro-RO/api/pricing/)), 실제 비용은 아래 항목들의 합으로 결정됩니다.

1) **중복 토큰(프롬프트/컨텍스트)**
- 배치는 “요청을 늦게 처리”할 뿐, **중복된 프롬프트를 자동 dedupe**하지 않습니다.
- 특히 “긴 system prompt(정책/스키마/예시) + 짧은 데이터 한 줄” 구조면, 단가 50%를 받아도 총토큰이 과하게 커져서 비용이 그대로 큽니다.
- 이 경우는 배치보다 먼저 **prompt caching(가능한 플랫폼에 한함) / 템플릿 축소 / RAG 컨텍스트 압축**을 고민해야 합니다.

2) **실패/재시도에 따른 ‘중복 결제’**
- 배치는 보통 streaming이 없고, job이 길게 돌기 때문에 네트워크/파서/다운스트림 저장에서 실패가 나면 **idempotency 설계 없이는 같은 레코드를 다시 태워** 비용이 늘어납니다.
- 따라서 배치에선 “성공률”보다 “재처리 비율”이 비용을 좌우합니다.

3) **결과물 크기(출력 토큰)**
- 대량 처리에서 흔한 실수: “요약/라벨링”인데 결과를 verbose하게 받아서 **output tokens**가 input 못지않게 커짐.
- 배치 할인은 output에도 적용되지만 ([openai.com](https://openai.com/ro-RO/api/pricing/)), “출력 제한(max_output_tokens) + 포맷 강제(JSON)”가 없으면 비용 예측이 안 됩니다.

### 3) Batch vs 동기 병렬 처리 vs 큐 기반 워커의 차이
- **동기 + 병렬(예: 500 동시 요청)**  
  장점: 즉시 결과, 관측/취소/재시도 쉬움  
  단점: rate limit에 막히기 쉽고, 대량이면 비용/스로틀링 튜닝이 어렵다
- **자체 큐(SQS/Kafka) + 워커 + 동기 API 호출**  
  장점: 제어권(우선순위, 백오프, 재시도, 부분 완료)  
  단점: 동기 단가 그대로 + 운영 복잡도 증가
- **공급자 Batch API**  
  장점: 할인(예: OpenAI 50%) ([openai.com](https://openai.com/ro-RO/api/pricing/)), 대량 처리 rate headroom ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai)), 운영 단순화(파일 제출)  
  단점: 24h SLA/지연, 기능 제약(예: tool calling 불가) ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html?utm_source=openai)), job 단위 실패/취소 모델에 맞춰 설계 필요 ([platform.openai.com](https://platform.openai.com/docs/api-reference/batch/retrieve?api-mode=responses&lang=curl&utm_source=openai))

---

## 💻 실전 코드
아래는 “프로덕션에서 흔한” 시나리오: **수십만 개 고객 문의(티켓) 텍스트를 분류/라벨링**해서 데이터 웨어하우스에 적재하는 파이프라인입니다.

- 요구: 하루 1회 배치, 24h 내면 OK
- 핵심: (1) JSONL 생성 (2) OpenAI Batch 제출 (3) 완료 시 결과 파일을 내려받아 (4) **custom_id로 원본과 join**해서 적재
- 주의: 배치 파일은 purpose=`batch`, JSONL, 크기 제한(문서에 “Batch API only supports .jsonl up to 200MB”가 명시) ([platform.openai.com](https://platform.openai.com/docs/api-reference/files?api-mode=responses&utm_source=openai))

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate
pip install openai==1.* pydantic==2.* tenacity==8.*
export OPENAI_API_KEY="..."
```

### 1) 배치 입력(JSONL) 만들기 + 파일 업로드 + 배치 생성
```python
# batch_submit.py
import json
import time
from pathlib import Path
from pydantic import BaseModel, Field
from openai import OpenAI

client = OpenAI()

# 현실적인 스키마: downstream에서 바로 쓰기 위해 좁고 결정적으로
class TicketLabel(BaseModel):
    category: str = Field(description="billing|bug|feature|account|other")
    priority: str = Field(description="p0|p1|p2|p3")
    language: str = Field(description="ko|en|ja|zh|other")
    needs_human: bool

def build_request(custom_id: str, text: str) -> dict:
    # /v1/responses로 배치 가능 ([platform.openai.com](https://platform.openai.com/docs/api-reference/batch/retrieve?api-mode=responses&lang=curl&utm_source=openai))
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/responses",
        "body": {
            "model": "gpt-4.1-mini",  # 예시: 실제 사용 모델로 교체
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict classifier. "
                        "Return ONLY JSON that matches the schema."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Classify the following support ticket.\n\n"
                        f"TICKET:\n{text}\n\n"
                        "JSON schema:\n"
                        f"{TicketLabel.model_json_schema()}"
                    ),
                },
            ],
            "max_output_tokens": 120,  # output 폭주 방지
            "temperature": 0,
        },
    }

def main():
    # 예: 데이터 레이크/DB에서 뽑아온 티켓 샘플(실전에서는 수만~수십만)
    tickets = [
        ("t_10001", "결제가 이중으로 청구됐어요. 환불 부탁드립니다."),
        ("t_10002", "iOS 앱에서 로그인 누르면 바로 튕깁니다. 로그 첨부 가능해요."),
        ("t_10003", "Can you add SSO for our enterprise account?"),
    ]

    out = Path("tickets_batch.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for tid, text in tickets:
            f.write(json.dumps(build_request(tid, text), ensure_ascii=False) + "\n")

    # 1) Files 업로드 (purpose=batch) ([platform.openai.com](https://platform.openai.com/docs/api-reference/files?api-mode=responses&utm_source=openai))
    file_obj = client.files.create(
        file=out.open("rb"),
        purpose="batch",
    )

    # 2) Batch 생성: completion_window=24h, endpoint 지정 ([platform.openai.com](https://platform.openai.com/docs/api-reference/batch/retrieve?api-mode=responses&lang=curl&utm_source=openai))
    batch = client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/responses",
        completion_window="24h",
    )

    print("file_id:", file_obj.id)
    print("batch_id:", batch.id)

if __name__ == "__main__":
    main()
```

예상 출력:
- `file_id: file_...`
- `batch_id: batch_...`

### 2) 배치 상태 추적 + 결과 다운로드 + 원본과 join
Batch는 “완료까지 24h” 계약이라 ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai)), 운영 관점에서는 **폴링 + 타임아웃 + 재시도**를 표준으로 둡니다(가능하면 이벤트 기반으로 감싸기).

```python
# batch_collect.py
import json
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI

client = OpenAI()

@retry(stop=stop_after_attempt(8), wait=wait_exponential(min=5, max=300))
def get_batch(batch_id: str):
    return client.batches.retrieve(batch_id)

def main(batch_id: str):
    # 완료될 때까지 폴링 (실전에서는 cron/worker가 주기적으로 실행)
    while True:
        b = get_batch(batch_id)
        print("status:", b.status)

        if b.status in ("completed", "failed", "cancelled", "expired"):
            break

        # 서버가 비동기로 처리하므로 너무 촘촘한 폴링은 의미가 적음
        import time; time.sleep(30)

    if b.status != "completed":
        raise RuntimeError(f"Batch not completed: {b.status}")

    # 결과 파일 내려받기: output_file_id가 생김 (API 모델에 따라 필드명 차이 가능)
    output_file_id = b.output_file_id
    raw = client.files.content(output_file_id).read()

    out = Path("batch_output.jsonl")
    out.write_bytes(raw)

    # custom_id로 원본과 join해서 DB에 적재한다는 가정
    # 결과 JSONL의 각 라인은 custom_id + response body를 포함 ([platform.openai.com](https://platform.openai.com/docs/api-reference/batch/retrieve?api-mode=responses&lang=curl&utm_source=openai))
    records = []
    for line in out.read_text("utf-8").splitlines():
        obj = json.loads(line)
        custom_id = obj["custom_id"]
        body = obj["response"]["body"]  # /v1/responses 결과 구조에 맞게 파싱
        # body에서 모델 출력(JSON)을 꺼내는 로직은 실제 응답 형태에 맞춰 조정
        records.append((custom_id, body))

    print("rows:", len(records))
    print("sample:", records[0][0])

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
```

이 파이프라인을 “현실적”으로 만드는 포인트는 다음입니다.
- 결과를 단순 파일로 두지 말고, **custom_id를 DB primary key와 1:1로 설계**(idempotency)
- “티켓 원본 → 배치 요청” 변환은 재실행해도 동일한 custom_id가 나오게(중복 결제 방지)
- output 토큰 폭주 방지: `max_output_tokens`, JSON-only 강제(파싱 실패율↓)

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) 비용을 좌우하는 건 “배치 할인율”이 아니라 “중복 토큰 제거율”
OpenAI Batch는 50% 절감을 내세우지만 ([openai.com](https://openai.com/ro-RO/api/pricing/)), 대량 처리에서 진짜 큰 레버는:
- system prompt/예시를 줄이기
- 템플릿화(필요 최소 규칙만)
- 가능한 플랫폼이면 caching 전략까지 같이 설계(배치만으로 해결하려 하지 말기)

체크리스트:
- “레코드당 input tokens” 분포를 먼저 측정하고(P50/P95), 긴 꼬리를 줄여라.
- output은 **스키마 최소화** + max cap을 걸어라.

### Best Practice 2) 비동기 파이프라인의 관건은 “정확히 한 번(exactly-once)”이 아니라 “중복에 안전(at-least-once + idempotent)”
Batch/Job 시스템은 실패/재시도/부분 완료가 자연스러운 세계입니다.
- custom_id를 **결정적(deterministic)** 으로 만들기: `sha256(normalized_text)+version`
- 결과 적재는 `UPSERT`로 만들기
- “실패 레코드만 재처리” 가능한 구조로 분리(전체 배치 재처리 금지)

### Best Practice 3) 관측(Observability): 배치에선 “latency”보다 “단위 비용”과 “실패율”이 SLO
동기 API는 p95 latency가 중요하지만, 배치에서는:
- 성공률(파싱/스키마 불일치 포함)
- 재처리 비율
- 레코드당 평균 input/output tokens
- 배치 완료시간 분포(24h window 내) ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))  
가 SLO입니다.

### 흔한 함정/안티패턴
- (함정) 배치에 streaming/tool calling을 기대함 → 지원 제약에 걸려 설계를 다시 해야 함  
  (예: Bedrock batch inference는 tool calling/structured output 미지원 명시) ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html?utm_source=openai))
- (안티패턴) “배치가 싸다”는 이유로 output을 장문 리포트로 받기 → output 토큰이 비용의 절반 이상이 됨
- (안티패턴) 결과 파일을 “그냥 S3/디스크에 저장”하고 끝 → 재처리/중복/감사 추적이 지옥이 됨  
  (Batch는 JSONL 기반이므로 **레코드 단위 추적성**을 설계로 확보해야 함) ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))

### 비용/성능/안정성 트레이드오프 정리
- 비용: Batch(50% 할인) ([openai.com](https://openai.com/ro-RO/api/pricing/))  vs 동기(정가)
- 성능: 처리량은 Batch가 유리(대량 전용 헤드룸) ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai)) vs 동기는 순간 burst에 제한
- 안정성: Batch는 “지연 + 재처리”를 전제로 설계해야 안정적(운영모델 전환 필요)

---

## 🚀 마무리
2026년 6월의 LLM 대량 처리 비용 최적화는 “싼 모델 고르기”보다 **비동기 배치 파이프라인을 제대로 설계하기**에 가깝습니다. OpenAI Batch API는 24h 비동기 처리와 50% 비용 절감을 명시하며 ([openai.com](https://openai.com/ro-RO/api/pricing/)), JSONL 기반 제출/결과 수집이라는 전형적인 batch 운영 모델을 제공합니다. ([platform.openai.com](https://platform.openai.com/docs/api-reference/batch/retrieve?api-mode=responses&lang=curl&utm_source=openai))

도입 판단 기준(실무용):
- 결과가 **수 분~수 시간 늦어도 괜찮다** → Batch 우선 검토
- 요청당 프롬프트 중복이 크다 → Batch 이전에 템플릿/컨텍스트 최적화부터
- 재처리/중복이 잦은 데이터 파이프라인이다 → Batch는 “idempotency + UPSERT + 관측”이 갖춰질 때만

다음 학습 추천:
- OpenAI Batch API 가이드/레퍼런스(파일 포맷, endpoint, 24h window, 결과 구조) ([platform.openai.com](https://platform.openai.com/docs/guides/batch/?utm_source=openai))
- Bedrock batch inference의 제약(레코드 독립 처리, 기능 제한, S3 중심 설계) ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html?utm_source=openai))

원하시면, **(1) “월 1억 토큰” 같은 목표량을 주고** batch vs 동기 vs 자체 워커의 TCO를 숫자로 비교하는 템플릿(스프레드시트/파이썬)과, **(2) 실패 레코드만 재처리하는 설계(Dead-letter + re-batch)**까지 확장 버전으로 이어서 작성해드릴게요.