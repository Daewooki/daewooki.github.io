---
title: "LLM Batch Inference API “대량 처리 비용” 실전 가이드: 50% 할인만 믿었다가 망하는 지점들"
description: "대량 LLM 작업(문서 요약/분류/정규화, 로그·CS 티켓 라벨링, 카탈로그 정제, 대규모 RAG 인덱싱 전처리)을 synchronous API로 밀어 넣으면 보통 두 가지가 먼저 터집니다."
date: 2026-07-25 03:25:00 +0900
categories: [AI, MLOps]
tags: [ai, mlops]
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
대량 LLM 작업(문서 요약/분류/정규화, 로그·CS 티켓 라벨링, 카탈로그 정제, 대규모 RAG 인덱싱 전처리)을 **synchronous API로 밀어 넣으면** 보통 두 가지가 먼저 터집니다.

- **비용**: “토큰 단가 × 요청 수”가 직선으로 증가
- **처리량**: RPM/TPM 제한 + 워커 수를 늘릴수록 재시도 폭탄

여기서 Batch inference API(비동기 배치 추론)는 “실시간 응답”을 포기하는 대신, **단가(대체로 ~50% 할인) + 더 큰 throughput**을 얻는 선택지입니다. OpenAI Batch API는 *synchronous 대비 50% 할인*을 명시하고 있고, AWS Bedrock도 *batch inference가 on-demand 대비 50% 저렴*하다고 안내합니다.[^1]

언제 쓰면 좋은가
- 결과를 **몇 분~몇 시간 뒤** 받아도 되는 오프라인/비동기성 파이프라인
- 같은 템플릿/시스템 프롬프트를 공유하는 **대량 동일 작업**(prompt caching, 공통 prefix)
- “요청당 latency”보다 “전체 처리량/총비용”이 KPI인 배치 잡

언제 쓰면 안 되는가
- 유저가 기다리는 **온라인 경로**(p95/p99 latency가 중요한 API)
- “부분 실패가 곧 장애”인 트랜잭션(결제, 권한 부여 같은 강결합 로직)
- 배치 결과가 늦게 오면 **재처리/중복 처리가 더 큰 비용**이 되는 워크로드(멱등성 설계가 어렵다면)

---

## 🔧 핵심 개념
### 1) Batch inference의 본질: “요청을 모아서 스케줄러에 맡긴다”
Batch API는 보통 다음 흐름입니다.

1. **입력 파일(JSONL)** 업로드 또는 job 생성 시 payload로 전달  
2. 서버가 내부 큐에 적재(스케줄링/리밸런싱)
3. 개별 요청을 실행(실패는 개별 단위로 기록)
4. **결과 파일(JSONL)** 을 나중에 다운로드/조회

이 구조의 핵심은:
- 클라이언트가 “즉시 응답” 대신 “**작업 ID + 나중에 수거**”로 모델 호출을 바꾼다는 점
- 공급자는 실시간 트래픽 피크를 맞추기보다, 데이터센터 관점에서 **효율적인 배치 스케줄링**을 할 수 있어 단가를 깎아줄 수 있다는 점

### 2) 비용 모델: “단가 할인”보다 “토큰 구조”가 더 크다
2026년 7월 기준, 실제 비용은 보통 아래 요소들의 곱/합으로 결정됩니다.

- **Input tokens** + **Output tokens**
- (가능하면) **Cached input tokens** 또는 prompt caching read
- Batch tier 할인(예: 50%)
- 데이터 레지던시/geo 옵션(일부는 가산)
- 실패/재시도/중복 처리(파이프라인 설계 비용)

예를 들어 OpenAI 쪽 문서에는 특정 모델의 **Batch API token 가격(예: GPT-5.5: input $5 / cached input $0.5 / output $30 per 1M tokens)** 이 표기되어 있어, “캐시를 얼마나 먹이느냐”가 배치 비용의 체감에 직결됩니다.[^2]  
그리고 OpenAI Batch API FAQ는 **synchronous 대비 50% 할인**을 명시합니다.[^1]

Anthropic 쪽도 “Batch processing tier” 단가를 별도로 두고(예: Claude 3.7 Sonnet 기준 input/output가 standard의 절반 수준으로 표기) 토큰·캐시 항목을 분리해 가격표에 제공합니다.[^3]

AWS Bedrock도 batch inference는 on-demand 대비 **50% 낮은 가격**이라고 안내하며, 특정 기간 프로모션 가격(예: 2026-08-31 종료)처럼 **날짜에 따른 가격 변화**도 있으니 “이번 달 견적”은 항상 고정값이 아닙니다.[^4]

### 3) “Batch vs Streaming/Sync”의 구조적 차이
- Sync: 클라이언트가 latency를 직접 부담, 공급자는 피크 대비 용량을 확보해야 함 → 단가↑
- Batch: 공급자가 내부적으로 **유휴 자원/스케줄링 최적화** 가능 → 단가↓, 대신 완료 시간은 SLA 성격

결론: 배치는 “싼 API”가 아니라 “**시스템을 비동기로 재설계할 때만** 싼 API”입니다.

---

## 💻 실전 코드
아래 예시는 “대규모 문서 요약 + 메타데이터 추출”을 **비동기 배치 파이프라인**으로 돌리는 현실적인 패턴입니다.

- 입력: S3/DB에 있는 문서 10만 건
- 처리: LLM으로 (a) 5줄 요약 (b) 카테고리 (c) PII 여부
- 출력: JSONL 결과를 다시 DW(BigQuery/Snowflake/Postgres)에 upsert
- 요구사항: 재시도/부분 실패/중복 방지(멱등성)

### 0) 의존성/환경
```bash
python -m venv .venv
source .venv/bin/activate
pip install httpx tenacity pydantic python-dotenv
export OPENAI_API_KEY="..."
```

### 1) 입력 JSONL 생성(멱등 키 포함)
요점: 배치에서는 “나중에 결과를 join”해야 하므로 **custom_id**(또는 유사 필드)로 원본 레코드 키를 박아둡니다.

```python
# build_batch_jsonl.py
import json
from pathlib import Path

def iter_docs():
    # 현실에선 DB cursor/파일 인덱스/S3 list로 대체
    for i in range(1, 10001):
        yield {
            "doc_id": f"doc_{i:06d}",
            "text": f"Long document body ... (#{i})"
        }

out = Path("requests.jsonl")
with out.open("w", encoding="utf-8") as f:
    for d in iter_docs():
        payload = {
            # OpenAI Batch는 개별 요청이 결국 "API 호출 1회"가 되므로
            # custom_id로 결과를 원본 doc_id에 매핑한다.
            "custom_id": d["doc_id"],
            "method": "POST",
            "url": "/v1/responses",
            "body": {
                "model": "gpt-5.5-2026-04-23",
                "input": [
                    {
                        "role": "system",
                        "content": "You are an information extraction engine."
                    },
                    {
                        "role": "user",
                        "content": (
                            "Return JSON with keys: summary_5_lines, category, contains_pii.\n\n"
                            f"DOCUMENT:\n{d['text']}"
                        )
                    }
                ],
                # 출력 토큰 폭주 방지(배치에서 가장 흔한 비용 사고)
                "max_output_tokens": 250,
            }
        }
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

print(f"Wrote {out}")
```

예상 출력
```bash
Wrote requests.jsonl
```

### 2) Batch job 제출 → 상태 폴링 → 결과 수거
핵심: (1) 완료까지 polling (2) 결과 JSONL을 다운로드 (3) 실패 항목만 재배치

```python
# run_batch_pipeline.py
import os, json, time
import httpx
from tenacity import retry, wait_exponential_jitter, stop_after_attempt

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
BASE_URL = "https://api.openai.com"

headers = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
}

@retry(wait=wait_exponential_jitter(1, 10), stop=stop_after_attempt(5))
def upload_file(path: str) -> str:
    with httpx.Client(timeout=60) as client:
        files = {"file": (os.path.basename(path), open(path, "rb"), "application/jsonl")}
        data = {"purpose": "batch"}
        r = client.post(f"{BASE_URL}/v1/files", headers=headers, data=data, files=files)
        r.raise_for_status()
        return r.json()["id"]

def create_batch(file_id: str) -> str:
    # endpoint는 정책/버전에 따라 다를 수 있으니 실제 사용 시 최신 문서 확인 필요
    body = {
        "input_file_id": file_id,
        "endpoint": "/v1/responses",
        "completion_window": "24h",
    }
    with httpx.Client(timeout=60) as client:
        r = client.post(f"{BASE_URL}/v1/batches", headers={**headers, "Content-Type": "application/json"}, json=body)
        r.raise_for_status()
        return r.json()["id"]

def get_batch(batch_id: str) -> dict:
    with httpx.Client(timeout=60) as client:
        r = client.get(f"{BASE_URL}/v1/batches/{batch_id}", headers=headers)
        r.raise_for_status()
        return r.json()

def download_file(file_id: str, out_path: str) -> None:
    with httpx.Client(timeout=120) as client:
        r = client.get(f"{BASE_URL}/v1/files/{file_id}/content", headers=headers)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)

def main():
    file_id = upload_file("requests.jsonl")
    batch_id = create_batch(file_id)
    print("batch_id =", batch_id)

    # 폴링(실전에서는 큐/워크플로 엔진로 넘기는 게 정석)
    while True:
        b = get_batch(batch_id)
        status = b["status"]
        print("status =", status)
        if status in ("completed", "failed", "cancelled", "expired"):
            break
        time.sleep(20)

    if b["status"] != "completed":
        raise RuntimeError(f"Batch ended with status={b['status']}")

    output_file_id = b["output_file_id"]
    download_file(output_file_id, "results.jsonl")
    print("downloaded results.jsonl")

    # 결과 처리(성공/실패 분기)
    ok, failed = 0, 0
    with open("results.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            doc_id = row.get("custom_id")
            if row.get("error"):
                failed += 1
                # 실패는 doc_id 기반으로 재배치 목록 구성
                continue
            # row["response"]에 모델 응답이 들어온다고 가정
            ok += 1

    print({"ok": ok, "failed": failed})

if __name__ == "__main__":
    main()
```

예상 출력(예시)
```bash
batch_id = batch_abc123
status = validating
status = in_progress
status = completed
downloaded results.jsonl
{'ok': 9992, 'failed': 8}
```

이제 `failed` 8건만 별도 JSONL로 모아 **재배치**하면, “대량 처리 중 일부 실패”를 전체 재실행 없이 복구할 수 있습니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **output 상한을 먼저 설계**하라  
배치 비용 사고의 80%는 “요약인데 모델이 장문을 써버린 케이스”입니다. `max_output_tokens`를 박고, JSON schema(또는 엄격한 포맷)로 출력 폭을 제한하세요.

2) **공통 prefix는 prompt caching/cached input을 강제 활용**  
OpenAI는 cached input이 일반 input 대비 훨씬 저렴한 가격 항목으로 분리돼 있고(모델별 표 참조), 캐시를 먹이면 배치 할인보다 체감이 더 커질 수 있습니다.[^2]  
Anthropic도 cache write/read가 별도 항목이며 batch tier와 함께 고려하게 되어 있습니다.[^3]

3) **멱등성 키 + “재배치 전용 파이프”**를 분리  
배치는 “언젠가 완료” 모델이라 운영 중 타임아웃/부분 실패는 정상입니다. `custom_id`를 DB primary key로 매핑하고, (a) 최초 대량 배치 (b) 실패 재배치 (c) 포맷 검증 실패 재처리 를 워크플로 레벨에서 분리하면 운영 난이도가 급감합니다.

### 흔한 함정/안티패턴
- “50% 할인”만 보고 **동일 workload를 그대로** sync→batch로 바꾸기  
  배치에선 결과가 늦게 오니, 다운스트림이 재요청/중복 처리하면 비용이 다시 상승합니다. 결국 **파이프라인까지 비동기화**해야 이득이 납니다.
- 배치 파일을 너무 크게 만들고 **관측/리트라이 단위를 잃는 것**  
  10만 건 1잡보다, 1만 건 × 10잡이 장애 격리와 재처리에 유리한 경우가 많습니다(특히 출력 포맷 검증이 빡센 작업).
- US-only/geo 제약, 프로모션 종료일을 무시한 비용 산정  
  Bedrock은 2026-08-31 같은 **프로모션 종료일**이 명시된 항목이 있습니다. 견적서에 “언제 가격이 바뀌는지” 날짜를 같이 박아두세요.[^4]

### 비용/성능/안정성 트레이드오프 한 줄 요약
- **비용↓**: batch + caching + 출력 상한
- **안정성↑**: 작은 배치 단위 + 멱등성 + 실패 재배치
- **처리량↑**: 공급자 배치 tier(보통 rate limit 측면에서 유리) 활용(단, 완료 지연 허용)

---

## 🚀 마무리
2026년 7월 시점의 LLM batch inference는 “대량 처리 비용을 절반으로” 같은 슬로건보다, 실제로는 다음 3가지를 동시에 만족할 때 가장 강력합니다.

1) 워크로드가 **비동기 완료**를 허용한다  
2) `custom_id` 기반으로 **부분 실패를 재처리**할 수 있다  
3) prompt caching/cached input + output cap으로 **토큰 구조를 통제**한다[^2]

다음 학습 추천(바로 실무 적용 관점)
- 워크플로 엔진(Temporal/Airflow)로 “배치 제출→폴링→수거→재배치”를 상태 머신으로 만들기
- 결과 JSON schema 검증(예: jsonschema) + validation fail 전용 재처리 큐 설계
- 비용 모델링: 문서 길이 분포 기반으로 input/output 토큰 p50/p95를 추정하고, batch 단위(1k/5k/10k)별 실패 격리 비용까지 포함한 TCO 산정

[^1]: <https://help.openai.com/en/articles/9197833-batch-api-faq%3F.gz>
[^2]: <https://developers.openai.com/api/docs/models/gpt-5.5>
[^3]: <https://www-cdn.anthropic.com/files/4zrzovbb/website/3684c2faafb97418665782cea0001f439f74b1d2.pdf>
[^4]: <https://aws.amazon.com/bedrock/pricing/?linkId=766764308&sc_campaign=Support&sc_channel=sm&sc_content=Support&sc_country=global&sc_geo=GLOBAL&sc_outcome=AWS+Support&sc_publisher=REDDIT&trk=Support>
