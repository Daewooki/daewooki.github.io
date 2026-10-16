---
title: "Gemini API 모델 문자열을 계약으로 고정하는 운영 패턴"
description: "자동 라우팅·shutdown 공지 시대에 모델 선택을 코드 계약으로 만들고, 테스트·카나리로 품질/비용 변화를 막는 방법."
date: 2026-10-16 09:42:57 +0900
categories: ["AI", "Gemini"]
tags: ["gemini-api", "model-governance", "contract-testing", "canary-release", "deprecation", "llm-ops"]
render_with_liquid: false
---

## 자동 라우팅이 만든 새로운 실패 모드

Gemini API 운영에서 가장 위험한 변화는 500 에러나 429가 아닙니다. 성공(200)으로 보이는데, 내부적으로 모델이 바뀌어서 품질·비용·지연시간이 조용히 변하는 상황입니다.

2026년 10월 릴리스 노트에는 `gemini-3.5-flash`가 deprecated 되었고, **API 요청이 `gemini-3.6-flash`로 자동 라우팅된다**는 문장이 명시되어 있습니다[^1].[^1]

이게 왜 운영 문제냐면, 많은 팀이 “모델 ID를 하드코딩했으니 재현 가능하다”는 전제를 깔고 SLA/비용 산정/프롬프트 회귀 테스트를 설계하기 때문입니다. 그런데 자동 라우팅이 들어오면 하드코딩이 더 이상 재현성을 보장하지 않습니다. `gemini-3.5-flash`를 호출하는 코드가 그대로여도 결과는 `gemini-3.6-flash`일 수 있습니다. 더 나쁜 건, 애플리케이션 로그에 `model="gemini-3.5-flash"`만 남기면 바뀐 사실조차 눈치채기 어렵습니다.

문제는 여기서 끝나지 않습니다.

* `gemini-3.5-flash`처럼 “endpoint는 안 끊고 라우팅만 바꾸는” 케이스가 있습니다.
* `deep-research-pro-preview-12-2025`처럼 “정해진 날짜에 shut down” 되는 케이스가 있습니다.

2026-10-23 shut down 예정인 Deep Research 에이전트(`deep-research-pro-preview-12-2025`)는 릴리스 노트와 deprecations 페이지에 shutdown 날짜가 명시되어 있습니다[^1][^2].[^1]

자동 라우팅과 shutdown은 성격이 다릅니다.

* 자동 라우팅: “성공하지만 바뀐다” → 품질/비용 회귀가 조용히 누적됩니다.
* shutdown: “어느 날부터 실패한다” → 장애가 즉시 폭발합니다.

이 글의 결론은 단순합니다. 모델 선택을 설정 파일의 문자열이 아니라 **테스트 가능한 Contract**로 만들어서, “라우팅/종료” 같은 공급자 정책 변화를 우리가 통제 가능한 형태로 변환해야 합니다.

## deprecation과 shutdown을 운영 규칙으로 번역하기

Gemini 문서에서 deprecation은 지원 중단 공지, shutdown은 endpoint가 완전히 꺼져 더 이상 사용할 수 없는 상태로 정의됩니다[^3].[^4]

여기서 실무적으로 중요한 포인트는 deprecations 표의 “Shutdown date”가 항상 날짜가 아니라는 점입니다.

예를 들어 `gemini-3.5-flash`는 shutdown date가 `N/A`로 표시되고, 추천 replacement에 “endpoint는 shutdown되지 않으며 자동 라우팅한다”는 문구가 붙습니다[^2].[^2]

운영 규칙으로 바꾸면 이렇게 정리됩니다.

### 1) `Shutdown date = 날짜`인 경우

이건 “마이그레이션 deadline”입니다.

* D-7~D-14: 신규 버전으로 카나리/섀도우 트래픽 시작
* D-2~D-3: 롤백 가능한 마지막 점검
* D-day: 이전 버전 호출이 남아 있으면 장애

`deep-research-pro-preview-12-2025`는 2026-10-23에 shut down으로 명시되어 있고[^2], 2026-10-16 KST 기준으로 정확히 7일 남은 상태입니다.[^2]

### 2) `Shutdown date = N/A` + “자동 라우팅”인 경우

이건 deadline이 아니라 “관측·검증 deadline”입니다.

endpoint가 안 끊기니까 급한 불은 없지만, 다음이 즉시 위험해집니다.

* 비용: 토큰 사용량/가격 정책이 바뀌면 월말 청구가 달라집니다.
* 품질: 출력 길이, 형식 준수율(JSON mode), 함수 호출 성향이 바뀝니다.
* latency: p95/p99가 흔들리면 타임아웃/재시도 폭풍이 터집니다.

`gemini-3.5-flash` → `gemini-3.6-flash` 자동 라우팅은 릴리스 노트와 “What’s new” 문서 양쪽에서 명시되어 있습니다[^5][^6].[^5]

운영 관점에서는 “이제부터 `gemini-3.5-flash`는 모델 ID가 아니라 alias에 가까운 것”으로 취급하는 편이 맞습니다.

### 3) Preview 모델/에이전트의 수명

Gemini 모델 페이지는 preview 모델이 더 제한적일 수 있고, 보통 최소 2주 notice로 deprecate 된다는 식의 라이프사이클 정보를 제공합니다[^7].[^7]

실제로 운영 난이도가 높은 건 preview string입니다.

* `...-preview-...`는 날짜/월이 박혀 있어서 심리적으로 “pinning 되어 있다”는 착시를 줍니다.
* 하지만 공급자 입장에서는 preview를 더 공격적으로 정리합니다.

그래서 preview를 쓰는 순간부터 모델 문자열을 “코드 계약 + 주기적 검증” 체계로 끌고 오지 않으면, 운영이 문서 구독 업무가 됩니다.

## 모델 문자열을 Contract로 만들 때 지켜야 하는 불변 조건

내가 말하는 Contract는 “이 모델을 쓰겠습니다”가 아니라, “이 호출이 만족해야 하는 운영적 불변 조건” 묶음입니다. 문자열은 그 Contract를 충족하기 위한 하나의 구현 디테일일 뿐입니다.

실무에서 유용한 불변 조건은 대략 다음 네 축으로 정리됩니다.

### 1) Identity: 실제로 어떤 모델이 응답했나

Gemini `generateContent` 응답에는 `usageMetadata.modelVersion`이 포함될 수 있고, API 레퍼런스에도 “응답을 생성한 모델 버전” 필드가 명시되어 있습니다[^8].[^9]

자동 라우팅 시대에 이 필드를 로깅하지 않으면, 비용/품질 회귀를 “원인 미상”으로만 보게 됩니다.

운영 Contract에는 최소한 다음이 들어가야 합니다.

* 요청한 모델 ID (requested model)
* 실제 응답한 모델 버전 (resolved modelVersion)
* 둘이 다를 때 허용/차단 정책

### 2) Shape: 출력 형식(구조화 출력) 보장

애플리케이션은 자연어를 소비하지 않습니다. 대부분은 JSON을 소비합니다.

Gemini는 `generationConfig.response_mime_type = "application/json"`과 `responseSchema`를 통해 구조화 출력을 유도할 수 있고, 스키마 기반 출력은 강한 힌트 없이 mime type만 주는 것보다 안전하다는 가이드가 Vertex AI 문서에도 정리돼 있습니다[^10][^11].[^10]

Contract는 “정확히 같은 문장”이 아니라 “파싱 가능한 JSON + 스키마 만족”을 검증해야 합니다.

### 3) Economics: 토큰 사용량과 latency 분포

공급자가 라우팅을 바꾸면 모델이 달라지고, 모델이 달라지면 latency 분포가 먼저 흔들립니다. 대개 p50은 비슷해도 p95/p99가 바뀝니다. 그러면 타임아웃/재시도/큐 적체로 비용이 2차 폭발합니다.

Contract에는 토큰 사용량과 latency의 “상한선/목표치”가 들어가야 합니다.

* prompt tokens, output tokens
* wall-clock latency
* timeout policy

Gemini 응답에 usage metadata(토큰 사용량 메타데이터)가 포함된다는 점은 `generateContent` 레퍼런스에 명시돼 있습니다[^8].[^8]

### 4) Lifecycle: 종료일 기반의 자동 경고/차단

`deep-research-pro-preview-12-2025`는 deprecated 되었고 2026-10-23 shutdown이 문서에 명시돼 있습니다[^12][^2].[^12]

이건 사람이 캘린더에 적어두는 방식으로는 못 막습니다. 코드 계약에 shutdown date를 박아 두고, 배포 파이프라인에서 강제해야 합니다.

## 실행 가능한 구현: Python으로 만드는 Model/Agent Contract + 계약 테스트

아래 예시는 “설정 파일의 문자열”이 아니라, 코드로 정의된 Contract가 단일 진실 공급원(Source of Truth)이 되는 패턴입니다.

요구사항은 세 가지입니다.

1. `gemini-3.5-flash`를 호출하더라도 실제 `modelVersion`이 `gemini-3.6-flash`로 라우팅될 수 있음을 탐지한다.
2. `deep-research-pro-preview-12-2025`는 2026-10-23 이후에는 호출 자체를 막는다(테스트/빌드 실패).
3. 마이그레이션을 위해 신규 대상(`gemini-3.6-flash`, `deep-research-preview-04-2026` 등)을 동시에 호출하는 카나리 러너를 제공한다.

### 프로젝트 구조

```text
contracts_demo/
  requirements.txt
  gemini_rest.py
  model_contracts.py
  canary_runner.py
  tests/
    test_model_contracts.py
```

### requirements.txt

```txt
requests==2.32.3
pydantic==2.9.2
python-dateutil==2.9.0.post0
pytest==8.3.3
```

버전은 글 작성일(2026-10-16 KST) 기준으로 예시이며, 핵심은 “REST 호출 + 계약 검증” 구조입니다.

### gemini_rest.py (REST 클라이언트)

```python
import os
import time
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BASE = "https://generativelanguage.googleapis.com/v1beta"

def _headers():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY env var is required")
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

def generate_content(model: str, *, text: str, response_schema: dict | None = None, timeout_s: int = 30):
    """Calls models/*:generateContent.

    Returns: (elapsed_ms, response_json)
    """
    url = f"{BASE}/models/{model}:generateContent"

    generation_config = {
        "temperature": 0,
        "response_mime_type": "application/json",
    }
    if response_schema is not None:
        generation_config["responseSchema"] = response_schema

    body = {
        "contents": [
            {"role": "user", "parts": [{"text": text}]}
        ],
        "generationConfig": generation_config,
    }

    t0 = time.time()
    r = requests.post(url, headers=_headers(), json=body, timeout=timeout_s)
    elapsed_ms = int((time.time() - t0) * 1000)

    # Raise with payload for easier debugging
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini API error {r.status_code}: {r.text}")

    return elapsed_ms, r.json()

def interactions_create(*, agent: str, input_text: str, timeout_s: int = 300):
    """Calls POST /v1beta/interactions with agent.

    This follows the public Interactions API shape shown in the managed/custom agents docs.
    """
    url = f"{BASE}/interactions"
    body = {
        "agent": agent,
        "input": input_text,
    }

    t0 = time.time()
    r = requests.post(url, headers=_headers(), json=body, timeout=timeout_s)
    elapsed_ms = int((time.time() - t0) * 1000)

    if r.status_code >= 400:
        raise RuntimeError(f"Gemini Interactions API error {r.status_code}: {r.text}")

    return elapsed_ms, r.json()
```

* `generateContent` endpoint, `usageMetadata.modelVersion` 같은 응답 구조는 공식 API 레퍼런스에 기반합니다[^8].[^8]
* Interactions API에서 `agent`를 지정하는 형태는 공식 가이드의 예시와 일치합니다[^13].[^13]

### model_contracts.py (Contract 정의 + 검증)

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from dateutil import parser

@dataclass(frozen=True)
class ModelContract:
    name: str
    requested_model: str

    # 실제 응답 modelVersion이 이 prefix 중 하나로 시작하면 "허용"
    allowed_model_version_prefixes: tuple[str, ...]

    # 자동 라우팅이 있다는 사실을 명시하고, 감지되면 로그/메트릭에 올리기 위한 라벨
    routing_expected: bool

@dataclass(frozen=True)
class AgentContract:
    name: str
    requested_agent: str
    shutdown_at: datetime  # timezone-aware
    replacement_agent: str

def parse_dt(value: str) -> datetime:
    # ISO8601 or RFC3339
    dt = parser.isoparse(value)
    if dt.tzinfo is None:
        raise ValueError("shutdown_at must be timezone-aware")
    return dt

# ---- Contracts (single source of truth) ----

GEMINI_FLASH_35_TO_36 = ModelContract(
    name="flash_3_5_deprecated_routes_to_3_6",
    requested_model="gemini-3.5-flash",
    allowed_model_version_prefixes=(
        # 자동 라우팅 문서화에 맞춰 3.6 계열 허용
        "gemini-3.6-flash",
        # 일부 응답은 'models/...' prefix로 오기도 해서 방어적으로 허용
        "models/gemini-3.6-flash",
    ),
    routing_expected=True,
)

GEMINI_FLASH_36_PINNED = ModelContract(
    name="flash_3_6_pinned",
    requested_model="gemini-3.6-flash",
    allowed_model_version_prefixes=(
        "gemini-3.6-flash",
        "models/gemini-3.6-flash",
    ),
    routing_expected=False,
)

DEEP_RESEARCH_PRO_12_2025 = AgentContract(
    name="deep_research_pro_preview_12_2025_shutdown",
    requested_agent="deep-research-pro-preview-12-2025",
    # 문서에 명시된 shutdown: October 23, 2026
    # 팀 표준 타임존이 KST라면 +09:00 기준으로 박아두는 편이 실무에서 덜 헷갈립니다.
    shutdown_at=parse_dt("2026-10-23T00:00:00+09:00"),
    replacement_agent="deep-research-preview-04-2026",
)

def assert_model_version_allowed(contract: ModelContract, *, model_version: str):
    if not any(model_version.startswith(p) for p in contract.allowed_model_version_prefixes):
        raise AssertionError(
            f"Contract '{contract.name}' violated: modelVersion='{model_version}' "
            f"not in allowed prefixes={contract.allowed_model_version_prefixes}"
        )

def assert_not_past_shutdown(contract: AgentContract, *, now: datetime):
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if now >= contract.shutdown_at:
        raise AssertionError(
            f"Agent '{contract.requested_agent}' is past shutdown_at={contract.shutdown_at.isoformat()} "
            f"replacement='{contract.replacement_agent}'"
        )

def contract_now() -> datetime:
    # 재현 가능한 테스트를 위해 CONTRACT_NOW를 주입할 수 있게 합니다.
    # (CI에서는 보통 비워두고 실제 현재 시간을 사용)
    import os

    v = os.environ.get("CONTRACT_NOW")
    if v:
        return parse_dt(v)
    return datetime.now(timezone.utc)
```

여기서 핵심은 “문서의 내용”을 사람이 기억하는 게 아니라, 코드에 “허용되는 실제 modelVersion prefix”와 “shutdown deadline”을 못 박는다는 점입니다.

`gemini-3.5-flash` 자동 라우팅은 릴리스 노트 및 deprecations 페이지에 명시돼 있으니, Contract가 그 사실을 반영해야 합니다[^5][^2].[^5]

### tests/test_model_contracts.py (계약 테스트)

```python
import json

from gemini_rest import generate_content
from model_contracts import (
    GEMINI_FLASH_35_TO_36,
    GEMINI_FLASH_36_PINNED,
    DEEP_RESEARCH_PRO_12_2025,
    assert_model_version_allowed,
    assert_not_past_shutdown,
    contract_now,
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "source_of_truth": {"type": "string", "enum": ["contract-test"]},
    },
    "required": ["answer", "source_of_truth"],
    "additionalProperties": False,
}

def _extract_model_version(resp: dict) -> str:
    usage = resp.get("usageMetadata") or {}
    mv = usage.get("modelVersion")
    if not mv:
        raise AssertionError(f"No usageMetadata.modelVersion in response: keys={list(resp.keys())}")
    return mv

def test_flash_35_is_routed_to_allowed_model_version():
    elapsed_ms, resp = generate_content(
        GEMINI_FLASH_35_TO_36.requested_model,
        text="Return JSON with fields {answer, source_of_truth}. answer must be 'ok'.",
        response_schema=RESPONSE_SCHEMA,
        timeout_s=30,
    )

    model_version = _extract_model_version(resp)
    assert_model_version_allowed(GEMINI_FLASH_35_TO_36, model_version=model_version)

    # JSON shape check (do not assert exact text beyond schema)
    text = resp["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(text)
    assert data["source_of_truth"] == "contract-test"

def test_flash_36_is_stable_under_contract():
    elapsed_ms, resp = generate_content(
        GEMINI_FLASH_36_PINNED.requested_model,
        text="Return JSON with fields {answer, source_of_truth}. answer must be 'ok'.",
        response_schema=RESPONSE_SCHEMA,
        timeout_s=30,
    )

    model_version = _extract_model_version(resp)
    assert_model_version_allowed(GEMINI_FLASH_36_PINNED, model_version=model_version)

def test_deep_research_shutdown_deadline_guard():
    now = contract_now()
    assert_not_past_shutdown(DEEP_RESEARCH_PRO_12_2025, now=now)
```

이 테스트는 “모델 출력이 예전과 똑같다”를 보장하지 않습니다. 대신 운영에 필요한 최소 조건을 고정합니다.

* 응답이 스키마를 만족하는 JSON이다.
* `usageMetadata.modelVersion`이 허용된 계열이다.
* shutdown deadline이 지나면 빌드/배포 파이프라인에서 즉시 터진다.

이 정도만 해도, 자동 라우팅으로 인한 조용한 변화가 “모니터링 가능한 이벤트”로 바뀝니다.

### 실행 방법

```bash
cd contracts_demo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export GEMINI_API_KEY="YOUR_KEY"

# 글 작성일(2026-10-16 KST) 기준으로 재현 가능한 실행
export CONTRACT_NOW="2026-10-16T00:00:00+09:00"

pytest -q
```

예상 출력 예시는 아래처럼 단순합니다.

```text
3 passed in 2.31s
```

(실제 시간, 네트워크 상태, 계정 quota에 따라 실행 시간은 달라집니다.)

## 카나리 설계: “자동 라우팅”과 “종료일”을 분리해서 다루기

자동 라우팅과 shutdown을 같은 체크리스트로 묶으면 항상 실패합니다. 둘은 마이그레이션 전략이 다릅니다.

### 1) 자동 라우팅 대응: “Detect → Decide → Enforce”

`gemini-3.5-flash`가 `gemini-3.6-flash`로 라우팅된다는 사실이 문서에 박혔다면[^5], 운영의 목표는 “하루빨리 3.6으로 문자열을 바꾼다”가 아닙니다. 목표는 아래 세 단계입니다.[^5]

1. Detect: 실제 응답의 `usageMetadata.modelVersion`을 수집한다.
2. Decide: 이 라우팅을 허용할지(3.6을 표준으로 승격), 아니면 트래픽을 제한할지 결정한다.
3. Enforce: 결정 결과를 Contract에 반영하고, 테스트/게이트로 강제한다.

자동 라우팅은 “공급자가 이미 결정을 내린 것”처럼 보이지만, 우리에게는 최소 두 가지 선택지가 남아 있습니다.

* fail-open: 라우팅을 허용하되, 관측과 회귀 탐지를 강화한다.
* **fail-closed**: 허용된 modelVersion prefix가 아니면 호출을 실패 처리하여, 문제가 더 큰 확산으로 번지는 걸 막는다.

내 경우 production에서는 fail-closed를 기본으로 잡고, 다만 카나리/실험 트래픽만 fail-open으로 둡니다. 그래야 “모델이 바뀌어서 좋았는지 나빴는지”를 비교할 시간이 생깁니다.

### 2) shutdown 대응: “역산 일정 + 단계적 교체 + 롤백 가능성 확보”

`deep-research-pro-preview-12-2025`는 2026-10-23 shutdown이 명시돼 있습니다[^2]. 이건 fail-open을 선택할 여지가 없습니다. 날짜 이후에는 죽습니다.[^2]

2026-10-16 KST 기준으로 현실적인 롤아웃을 역산해 보면 이렇게 됩니다.

* 2026-10-16 ~ 2026-10-18: 신규 에이전트(`deep-research-preview-04-2026`, 필요시 `deep-research-max-preview-04-2026`)로 섀도우 실행 시작
* 2026-10-19 ~ 2026-10-21: 카나리 1~5% 트래픽 전환 + 품질/비용/latency 비교
* 2026-10-22: 50% 전환(롤백 가능) + 장애 대응 runbook 확정
* 2026-10-23 00:00 KST 이전: 100% 전환 완료 + old agent 호출 차단(코드 레벨)

릴리스 노트는 신규 Deep Research 에이전트 버전으로의 마이그레이션을 `agent` 파라미터 변경으로 안내합니다[^1].[^1]

다만 에이전트는 모델보다 변동이 더 큽니다.

* 내부적으로 어떤 base model을 쓰는지 바뀔 수 있습니다.
* tool use 정책이나 결과 포맷이 바뀔 수 있습니다.

그래서 에이전트 마이그레이션은 “문자열 바꾸기”가 아니라 “업무 시나리오 기반의 회귀 테스트”가 필요합니다.

## 카나리 러너: 동일 입력을 두 대상에 쏘고 운영 지표로 비교하기

아래 `canary_runner.py`는 동일한 입력을 구(old) / 신(new) 대상에 동시에 실행하고, 최소 지표를 뽑아 비교합니다.

* generateContent 모델: 3.5(라우팅 대상) vs 3.6(pinned)
* agent: deep-research-pro-preview-12-2025 vs deep-research-preview-04-2026

```python
import json
from model_contracts import (
    GEMINI_FLASH_35_TO_36,
    GEMINI_FLASH_36_PINNED,
    DEEP_RESEARCH_PRO_12_2025,
    assert_model_version_allowed,
)
from gemini_rest import generate_content, interactions_create

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["summary", "risk"],
    "additionalProperties": False,
}

def extract_model_version(resp: dict) -> str:
    return (resp.get("usageMetadata") or {}).get("modelVersion") or ""

def extract_text(resp: dict) -> str:
    return resp["candidates"][0]["content"]["parts"][0]["text"]

def run_generatecontent_canary():
    prompt = (
        "You are running in a contract canary. "
        "Return JSON that matches the schema exactly. "
        "Summarize in one sentence why model identity governance matters. "
        "Risk must be one of low/medium/high."
    )

    results = []
    for c in [GEMINI_FLASH_35_TO_36, GEMINI_FLASH_36_PINNED]:
        elapsed_ms, resp = generate_content(
            c.requested_model,
            text=prompt,
            response_schema=RESPONSE_SCHEMA,
            timeout_s=30,
        )
        mv = extract_model_version(resp)
        assert_model_version_allowed(c, model_version=mv)

        text = extract_text(resp)
        data = json.loads(text)

        usage = resp.get("usageMetadata") or {}
        results.append(
            {
                "contract": c.name,
                "requested_model": c.requested_model,
                "resolved_model_version": mv,
                "elapsed_ms": elapsed_ms,
                "prompt_tokens": usage.get("promptTokenCount"),
                "output_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
                "json_ok": True,
                "payload": data,
            }
        )

    return results

def run_agent_canary():
    # deep research는 응답이 길고 비결정적이라서 여기서는 단순히 호출 가능성과 latency만 봅니다.
    # 실무에서는 "citation 수", "중복률", "특정 도메인 커버리지" 같은 스코어링을 추가하는 편이 낫습니다.

    input_text = "Find 3 authoritative sources about Gemini API model deprecations and summarize key operational risks."

    agents = [
        (DEEP_RESEARCH_PRO_12_2025.requested_agent, "old"),
        (DEEP_RESEARCH_PRO_12_2025.replacement_agent, "new"),
    ]

    results = []
    for agent, label in agents:
        elapsed_ms, resp = interactions_create(agent=agent, input_text=input_text, timeout_s=300)
        results.append(
            {
                "label": label,
                "agent": agent,
                "elapsed_ms": elapsed_ms,
                "interaction_id": (resp.get("interaction") or {}).get("id"),
                "output_text_preview": ((resp.get("interaction") or {}).get("output_text") or "")[:200],
            }
        )

    return results

if __name__ == "__main__":
    print("=== generateContent canary ===")
    for row in run_generatecontent_canary():
        print(json.dumps(row, ensure_ascii=False))

    print("\n=== deep research agent canary ===")
    for row in run_agent_canary():
        print(json.dumps(row, ensure_ascii=False))
```

실행:

```bash
python canary_runner.py
```

예상 출력은 대략 이런 형태입니다(토큰 수/latency/interaction_id는 환경에 따라 달라집니다).

```text
=== generateContent canary ===
{"contract": "flash_3_5_deprecated_routes_to_3_6", "requested_model": "gemini-3.5-flash", "resolved_model_version": "gemini-3.6-flash...", "elapsed_ms": 420, "prompt_tokens": 120, "output_tokens": 45, "total_tokens": 165, "json_ok": true, "payload": {"summary": "...", "risk": "medium"}}
{"contract": "flash_3_6_pinned", "requested_model": "gemini-3.6-flash", "resolved_model_version": "gemini-3.6-flash...", "elapsed_ms": 380, "prompt_tokens": 120, "output_tokens": 41, "total_tokens": 161, "json_ok": true, "payload": {"summary": "...", "risk": "medium"}}

=== deep research agent canary ===
{"label": "old", "agent": "deep-research-pro-preview-12-2025", "elapsed_ms": 81234, "interaction_id": "...", "output_text_preview": "..."}
{"label": "new", "agent": "deep-research-preview-04-2026", "elapsed_ms": 65432, "interaction_id": "...", "output_text_preview": "..."}
```

여기까지 구현하면, 자동 라우팅은 더 이상 “나중에 알게 되는 사건”이 아니라 “빌드/테스트에서 즉시 보이는 신호”가 됩니다.

## 함정과 트레이드오프: Contract를 너무 강하게 잡으면 생기는 일

Contract를 코드로 고정하면 당연히 부작용도 생깁니다.

### 1) modelVersion prefix를 어디까지 허용할 것인가

`usageMetadata.modelVersion`이 항상 `gemini-3.6-flash`로만 오리라는 보장은 없습니다. 문서상 “모델 버전” 필드가 존재한다는 것까지는 명확하지만[^8], 실제 값의 포맷이 `models/...` prefix를 붙이거나, patch 수준을 붙일 수 있습니다.[^9]

그래서 prefix 매칭이 실무적으로는 제일 덜 아프고, 다음 단계는 정규식입니다.

* 허용 폭이 너무 넓으면 회귀를 놓칩니다.
* 허용 폭이 너무 좁으면 정상적인 provider 롤링 업데이트에도 배포가 계속 깨집니다.

내 기준은 이렇습니다.

* major/minor는 좁게 (예: `gemini-3.6-flash`만)
* patch/build는 넓게 (예: `gemini-3.6-flash-xxx`는 허용)

### 2) fail-closed는 장애를 “앞당겨서” 만든다

fail-closed는 운영 리스크를 줄이지만, 장애 시점을 앞당깁니다. 라우팅이 바뀌면 사용자 트래픽이 아니라 배포 파이프라인에서 먼저 터집니다.

이건 나쁜 일이 아닙니다. 다만 조직의 대응 체계가 “빌드 깨짐 = 즉시 조사/승인/롤백”으로 성숙해 있어야 합니다.

### 3) 에이전트는 모델보다 “출력 계약”이 더 어렵다

Deep Research 같은 에이전트는 본질적으로 비결정적이고 결과가 길어서, JSON 스키마 한 장으로는 회귀를 잡기 어렵습니다.

이때는 Contract를 두 층으로 나누는 편이 낫습니다.

* 하위층: API 호출 가능성, latency, 에러율, tool call 수
* 상위층: 도메인별 커버리지, citation 품질(도메인 신뢰도), 중복률

그리고 shutdown이 다가오면 하위층 기준을 먼저 만족시키고, 상위층을 점진적으로 강화하는 방식이 일정상 현실적입니다.

### 4) 문서 업데이트 지연/표기 불일치

deprecations 페이지에는 “Last updated 2026-10-12 UTC” 같이 갱신 시점이 표시됩니다[^2].[^2]

이런 시스템은 문서/공지/콘솔 UI의 업데이트 타이밍이 엇갈릴 때가 있습니다. 그래서 Contract는 “문서를 그대로 복사”가 아니라, 문서의 핵심만 운영 정책으로 번역한 결과여야 합니다.

## 도입 판단 기준: 문자열 하드코딩이 안전한가라는 질문의 답

모델 ID를 하드코딩해도 안전하냐는 질문은 이제 이렇게 바뀌어야 합니다.

* “문자열을 고정하면 안전한가?”가 아니라
* “내 호출이 실제로 어떤 모델로 처리되었는지 관측하고, 그 변화를 테스트로 막고, shutdown을 날짜 기반으로 강제하는가?”입니다.

이 패턴이 특히 필요한 경우는 다음과 같습니다.

* 비용이 큰 워크로드(대량 batch, 멀티턴 agent, 긴 컨텍스트)
* JSON mode, function calling 같은 “형식 계약”이 중요한 워크로드
* 장애 허용도가 낮은 B2B/내부 핵심 업무

반대로, 아래 케이스에서는 Contract를 약하게 잡거나(경고만), 아예 적용하지 않는 쪽이 맞습니다.

* 개인 프로토타입
* 사용자가 결과를 직접 읽고 판단하는 UI
* 모델 업그레이드가 곧 가치인 실험 서비스

다만 2026년 10월 기준, Gemini API는 deprecated 모델을 “끊어버리기”만 하는 게 아니라 “자동 라우팅”도 적극적으로 사용하고 있고[^5], 특정 에이전트는 shutdown 날짜가 명시된 형태로 운영됩니다[^2].[^1]

결국 안전장치는 하드코딩 여부가 아니라, 문자열을 운영 계약으로 승격시키고, 테스트·관측·카나리로 묶어 “조용한 변경”을 사건화하는 능력입니다.

## 참고 자료

- [Gemini API Release notes](https://ai.google.dev/gemini-api/docs/changelog)
- [Gemini API Release notes (release=09-18-2026)](https://ai.google.dev/gemini-api/docs/changelog?release=09-18-2026)
- [Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations.md)
- [What’s new in Gemini 3.5 Flash](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5)
- [Models](https://ai.google.dev/gemini-api/docs/models?hl=en)
- [Deep Research Pro preview model page](https://ai.google.dev/gemini-api/docs/models/deep-research-pro-preview-12-2025)
- [Generate content API reference](https://ai.google.dev/api/generate-content)
- [Building managed agents](https://ai.google.dev/gemini-api/docs/custom-agents)
- [GenerationConfig in Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/GenerationConfig)
- [Structured output (Vertex)](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output?hl=en)
- [빅테크 AI “발표”보다 더 무서운 건 API/정책의 조용한 변경이다](https://daewooki.github.io/posts/2026-3-ai-api-1/)

[^1]: <https://ai.google.dev/gemini-api/docs/changelog?release=09-18-2026>
[^2]: <https://ai.google.dev/gemini-api/docs/deprecations.md>
[^3]: <https://ai.google.dev/gemini-api/docs/deprecations?hl=en>
[^4]: <https://ai.google.dev/gemini-api/docs/deprecations?authuser=8&hl=en>
[^5]: <https://ai.google.dev/gemini-api/docs/changelog>
[^6]: <https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5>
[^7]: <https://ai.google.dev/gemini-api/docs/models?hl=en>
[^8]: <https://ai.google.dev/api/generate-content>
[^9]: <https://ai.google.dev/api/generate-content?authuser=01&hl=es-419>
[^10]: <https://cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/GenerationConfig>
[^11]: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output?hl=en>
[^12]: <https://ai.google.dev/gemini-api/docs/models/deep-research-pro-preview-12-2025>
[^13]: <https://ai.google.dev/gemini-api/docs/custom-agents>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
