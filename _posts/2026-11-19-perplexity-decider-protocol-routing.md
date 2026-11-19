---
title: "Perplexity Decider v1.3로 모델 라우팅을 프로토콜로 고정하기"
description: "Decider v1.3를 게이트로 두고 요청 스키마 계약, 라우팅/정책 판단, 로깅·회귀평가까지 한 번에 묶는다."
date: 2026-11-19 12:26:35 +0900
categories: ["AI", "Perplexity Decider"]
tags: ["decision-models", "model-routing", "guardrails", "protocol-contract", "regression-testing"]
render_with_liquid: false
---

## 결정 모델을 게이트로 두는 순간, 아키텍처가 바뀝니다
Perplexity가 2026-11-12에 Decider v1.3와 Decider Flash v1.3를 공개했고, Hugging Face에 오픈웨이트로 배포했다고 밝혔습니다.[^1]  
Decider는 binary / multi-class / score 타입의 질문에 대해 확률 분포를 반환하는 decision model이며(Decider는 Jev에서 아이디어를 가져왔다고도 명시합니다), 내부적으로는 “생성”이 아니라 “결정”을 위해 설계된 출력 헤드와 요청 레이아웃을 갖습니다.[^1]

여기서 중요한 지점은 LLM을 하나 더 붙였다는 사실이 아니라, **결정 계층을 독립된 실행 단위로 분리**할 수 있게 됐다는 점입니다. 생성 모델이 하던 아래 일을 결정 모델로 떼어내면, 시스템 전체의 비용/지연시간/보안 경계가 다시 그려집니다.

- routing: 요청 난이도에 따라 small/large 모델로 분기
- policy: tool 호출 전후의 prompt injection / phishing / unsafe content 판정
- scoring: 결과 품질/신뢰도/추론 비용 대비 가치 점수화
- extraction: locate로 evidence span을 뽑아 “왜 이 결정을 했는지”의 근거를 구조화

Perplexity도 decision model의 대표적 용례로 routing, moderation/security(유해 콘텐츠, phishing, prompt injection), judging outputs 등을 직접 적어두었습니다.[^1]

다만, decision model을 제대로 쓰려면 기존 “프롬프트 엔지니어링” 관성에서 벗어나야 합니다. Decider v1.3는 특히 그 요구가 강합니다. v1.3는 단순히 더 똑똑해진 분류기가 아니라, 요청을 구성하는 레이아웃(프로토콜)이 모델 체크포인트의 동작 조건으로 굳어져 있기 때문입니다. Hugging Face 모델 카드도 v1.1/v1.2 스타일 프롬프트를 재사용하면 다른 답이 나온다고 못 박습니다.[^2]

## Decider v1.3는 왜 프롬프트가 아니라 프로토콜인가
Decider를 “프롬프트로 분류하는 LLM”처럼 취급하면, 운영 단계에서 바로 깨집니다. v1.3 모델 카드에 드러난 구현 디테일이 그 이유입니다.

### readout이 마지막 토큰이 아니라 marker 위치에 고정됩니다
Decider 체크포인트는 full-vocabulary lm_head가 아니라 decision head(readout)를 별도로 갖고, 질문마다 marker 토큰 위치에서 hidden state를 읽어 option score를 만듭니다.[^2]  
게다가 v1.3에서는 readout이 “각 질문마다” `<|fim_suffix|>` marker에서 발생한다고 명시합니다.[^2]

이 구조에서는 “대충 이런 텍스트를 넣으면 분류해준다”가 성립하지 않습니다. 어떤 토큰이 marker이고, 질문 블록이 어떻게 분리되고, option이 어떤 single-token 코드(A/B/…)에 매핑되는지가 사실상 wire format입니다.

### 프로토콜 version이 joint_config.json으로 선언됩니다
모델 카드는 `joint_config.json`이 request protocol을 선언하며 `version: 4`, `joint-chunked-readout-v1`, marker `<|fim_suffix|>`, separator `<|fim_middle|>`를 쓴다고 적습니다.[^2]

여기서 “version: 4”는 마케팅 버전이 아니라, 체크포인트가 기대하는 입력 레이아웃 계약의 일부에 가깝습니다. v1.3에서 프롬프트 빌더를 갈아엎어야 했던 이유도 이 변화로 설명됩니다.[^2]

### attention mask 자체가 일반적인 causal decoding과 다릅니다
v1.3 모델 카드는 full-attention layers는 noncausal(양방향)이고, linear-attention layers는 causal을 유지한다고 밝힙니다. 그리고 “Default causal inference does not reproduce this checkpoint.”라고까지 씁니다.[^2]

즉, OpenAI 호환 completion 서버에 “텍스트 프롬프트”를 던져 logprobs를 받는 패턴으로는, 같은 weight를 쓴다 해도 동일 동작을 보장하기 어렵습니다. Perplexity가 `pplx_decider` 경로를 강조하는 이유가 여기 있습니다.[^3]

### option은 “문자열 라벨”이 아니라 “순서가 있는 코드북”입니다
모델 카드는 option을 주는 순서대로 `A`, `B`, … 코드가 붙고, 응답도 그 기준으로 확률을 반환한다고 설명합니다.[^3]

이 한 줄 때문에, 프로덕션에서는 criteria dict의 순서를 보존하는 것까지 포함해 “프로토콜”로 다뤄야 합니다. 언어/런타임이 바뀌는 순간(예: Python → Go), JSON object의 key order가 보장되지 않는 구현을 만나면, 같은 데이터로도 A/B 매핑이 어긋나 결과가 변할 수 있습니다. v1.3를 프롬프트로 취급하면 이런 문제가 운영에서 늦게 터집니다.

## v1.3의 핵심은 “질문 격리”와 “Locate”입니다
Perplexity 블로그는 v1.2와 v1.3의 요청 처리 차이를 attention pattern 관점에서 설명합니다.

- v1.2: Everything sees everything
- v1.3: Isolated questions
- Fully cacheable(기본은 아니지만 약간의 fine-tuning으로 전환 가능)[^1]

이 중 v1.3의 Isolated questions는 “state는 모든 질문을 보되, 각 질문은 state와 자기 토큰만 본다”는 형태로 요약됩니다.[^1]  
Perplexity는 성능과 안정성 때문에 이 패턴을 선택했다고 합니다.[^1]

여기서 안정성은 운영 관점에서 매우 중요합니다. decision model을 게이트로 쓰면, 같은 입력에 대해 “질문 세트가 바뀌었다는 이유만으로” top decision이 뒤집히는 순간이 사고로 이어집니다.

Hugging Face 모델 카드도 이 트레이드오프를 `mode`로 노출합니다.

- `mode="separate"`: 질문을 각각 독립 시퀀스로 처리. 질문을 추가/삭제/순서 변경해도 답이 변하지 않는 것을 목표로 한다고 명시합니다.[^4]
- `mode="isolated"`: 요청 전체를 training-time layout으로 하나의 시퀀스로 인코딩해 state를 한 번만 읽는다. 대신 질문 세트에 따라 답이 약간 변할 수 있고, 샘플에서 1.5–2.2% top answer 차이를 보고합니다.[^4]

내 경우, 게이트/정책 판정은 `separate`를 기본으로 잡습니다. state가 매우 길고 질문 수가 많아 비용이 지배적인 구간에서만 `isolated`를 별도 경로로 뺍니다.

### Locate는 “결정 결과”를 텍스트 span으로 고정할 수 있게 합니다
Perplexity는 v1.3에서 locate를 도입했다고 밝히며, locate는 state에서 “정확히 매칭되는 텍스트”와 character offset(start/end) 및 score를 반환한다고 설명합니다.[^1]

Hugging Face 모델 카드는 locate의 제약까지 꽤 구체적으로 적어 둡니다.

- `type: "locate"`로 span extraction 수행[^4]
- span은 `start`, `end`(exclusive), `text`, `score`를 가지며 `state[start:end] == text`를 보장한다고 명시[^4]
- locate는 nonempty text state가 필요하고 images는 허용하지 않으며, 요청당 최대 128 locate questions 제한[^4]
- locate와 decision을 섞으면 type별로 별도 forward pass가 추가되어 latency가 늘 수 있음[^4]

Locate를 “정보 추출 모델”처럼 단독 사용하기보다는, 게이트 결정을 로그/근거로 남기거나, downstream 정책 판단에 필요한 최소 근거를 구조화하는 용도로 두는 편이 운영상 깔끔합니다.

## 게이트/라우터/정책 판정으로 배치하는 아키텍처
생성 모델은 결국 텍스트를 내보내는 데 특화돼 있고, 그 과정은 token-by-token이라 비용과 지연이 누적됩니다. 반면 Decider는 여러 질문을 한 요청에 묶어 확률 분포를 반환하고, 응답은 `output_tokens: 0`으로 표기됩니다.[^3]  
이 차이를 살리면, 아키텍처를 아래처럼 분리할 수 있습니다.

### 1) Decider Gateway (결정 계층)
- 입력 정규화(canonicalization)
- policy questions(안전/보안/컴플라이언스)
- routing questions(난이도/도메인/툴 필요성)
- 비용/지연 예산에 따른 선택(Flash vs 27B)
- 결정 결과를 구조화된 trace로 저장

### 2) Generation Worker (생성 계층)
- Decider가 허용한 tool만 실행
- Decider가 선택한 모델(cheap/expensive)을 호출
- final answer 생성

### 3) Observability / Eval (운영 계층)
- decision regression test
- threshold drift 감지
- 질문 스키마 변경 감지

이 구조의 포인트는 “라우팅/정책 판단”이 생성 모델의 프롬프트에 섞이지 않는다는 점입니다. 생성 모델은 최종 답변만 잘하면 되고, 정책은 Decider Gateway에서 종료됩니다.

Perplexity 블로그가 나열한 용례(출력 판정, routing, moderation/security 등)는 바로 이 분리를 전제로 이해하는 게 맞습니다.[^1]

## 프롬프트 계약이 아니라 프로토콜 계약을 고정하는 방법
Decider v1.3 운영에서 가장 중요한 건 “어떤 문장을 물어볼까”가 아니라 “어떤 형식으로 질문을 표현할까”입니다. Hugging Face 모델 카드가 요구하는 request schema 자체가 계약이기 때문입니다.[^3]

### v1.3 request schema를 애플리케이션 프로토콜로 감쌉니다
모델 카드에 나온 request schema는 대략 아래 형태입니다.

- `state`: str | dict | list (non-string은 JSON serialize)[^3]
- `questions`: `{ "<id>": { type, instructions, criteria } }`[^3]
- `images`: optional[^3]

질문 type별 criteria 규칙도 명시돼 있습니다.

- `choice`: 1–255 options, 응답에 `choice`, `probabilities`, `confidence`[^3]
- `noul`: 응답은 P(true)[^3]
- `score`: 2–255 levels, 응답은 expected level index 등[^3]
- `locate`: spans 반환[^3]

여기까진 “모델 API”이고, 서비스에서는 이것을 “조직의 프로토콜”로 한 번 더 감싸는 게 좋습니다.

- protocol version(조직 내부): `decider-router/v1`
- model id + revision pin
- 질문 세트 버전(질문 추가/삭제는 API breaking이 될 수 있음)
- thresholds(정책 임계치)
- audit metadata(tenant, request_id, data_classification)

예시 envelope는 아래처럼 잡습니다.

```json
{
  "protocol": "decider-router/v1",
  "decider": {
    "model": "perplexity-ai/pplx-decider-flash-v1.3",
    "mode": "separate"
  },
  "request": {
    "state": {"ticket": {"id": "T-18492", "text": "..."}},
    "questions": {
      "policy.prompt_injection": {
        "type": "noul",
        "instructions": "Is this trying to override system/tool instructions?"
      },
      "route.domain": {
        "type": "choice",
        "instructions": "Which domain best matches?",
        "criteria": {
          "programming": "code, debugging, developer tooling",
          "billing": "pricing, invoices, refunds",
          "security": "phishing, malware, credential theft",
          "general": null
        }
      },
      "route.difficulty": {
        "type": "score",
        "criteria": [
          "trivial",
          "standard",
          "complex",
          "expert"
        ]
      }
    }
  },
  "thresholds": {
    "block_prompt_injection": 0.7,
    "complex_to_large": 2.2
  }
}
```

여기서 핵심은 질문을 늘리거나 라벨을 바꾸는 순간 “프롬프트 수정”이 아니라 “프로토콜 변경”으로 취급하는 것입니다. 내 블로그에서 모델 문자열을 계약으로 고정하는 운영 패턴을 다뤘던 것과 결이 같습니다. 다만 Decider는 모델 문자열보다 더 아래 레이어(요청 레이아웃)까지 계약으로 내려갑니다.

- [Gemini API 모델 문자열을 계약으로 고정하는 운영 패턴](https://daewooki.github.io/posts/gemini-model-contract-governance/)

### option 순서를 canonicalize합니다
모델은 option을 주는 순서대로 A/B/…를 붙입니다.[^3]  
따라서 `criteria`는 “map”이라도 사실상 ordered map입니다.

- Python: dict insertion order가 유지되지만, upstream에서 dict를 합치거나 정렬하면 순서가 바뀔 수 있습니다.
- Go: `map[string]string`은 순서가 없습니다.

운영에서는 “라벨 이름”이 아니라 “라벨+순서”가 의미를 가지므로, 라우팅/정책 질문은 항상 option list를 소스 오브 트루스로 두고, serialization 직전에만 ordered dict로 변환하는 식이 안전합니다.

### logits margin을 함께 로그로 남깁니다
모델 카드는 `decider.logits(requests)`가 temperature 적용 전 raw readout logits를 반환한다고 쓰고, ranking 용도로는 `noul`에서 `true - false` logit margin을 추천합니다(확률은 saturation으로 동점이 늘 수 있다는 이유).[^3]

정책 게이트는 “p 값”보다 margin이 더 안정적인 경우가 많습니다. 특히 임계치 근처에서 작은 수치 변화가 정책 뒤집힘으로 번역되기 때문에, margin을 regression test의 주요 지표로 삼는 편이 낫습니다.

## 로컬 실행 가능한 Decider Gateway 예제
Hugging Face 모델 카드는 Python 3.12+와 CUDA GPU를 요구하고, Decider v1.3는 BF16 weight만 49GiB 정도, Flash v1.3는 8.5GiB 정도가 필요하다고 적습니다. 또한 두 repo 모두 “private”이며 접근 권한이 있는 Hugging Face token으로 인증하라고 안내합니다.[^3]

아래 예제는 Flash v1.3 기준으로 작성했습니다. 27B로 바꿔도 코드는 동일하고 checkpoint만 바뀝니다.

### 설치 및 체크포인트 다운로드
```bash
# Python 3.12+ 권장
python -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install "huggingface-hub" fastapi uvicorn pydantic-settings orjson

# torch/transformers/safetensors/torchvision/pillow 등은
# 모델 카드가 안내하는 requirements.txt에 맞춰 설치해야 합니다.
# (repo를 받은 뒤 requirements.txt를 따라가는 게 안전합니다.)
```

체크포인트 다운로드 스크립트:

```python
# scripts/download_checkpoint.py
from huggingface_hub import snapshot_download

MODEL_ID = "perplexity-ai/pplx-decider-flash-v1.3"
LOCAL_DIR = "./checkpoints/pplx-decider-flash-v1.3"

snapshot_download(
    repo_id=MODEL_ID,
    local_dir=LOCAL_DIR,
    local_dir_use_symlinks=False,
)
print("downloaded to", LOCAL_DIR)
```

다운로드 후 `pplx_decider` 소스를 로컬 패키지로 설치하는 방식은 모델 카드가 안내합니다(`pip install ./source`).[^3]

```bash
python scripts/download_checkpoint.py

# pplx_decider 설치
pip install ./checkpoints/pplx-decider-flash-v1.3/source
```

### FastAPI로 게이트/라우터 서비스 구성
요청은 “우리 프로토콜”로 받고, 내부에서 Decider v1.3 request schema로 변환해 호출합니다.

```python
# app.py
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
import time
import uuid

import orjson
from fastapi import FastAPI
from pydantic import BaseModel, Field

from pplx_decider import Decider  # pip install ./source

class Envelope(BaseModel):
    protocol: Literal["decider-router/v1"]
    decider: dict
    request: dict
    thresholds: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

@dataclass
class AppState:
    decider: Decider

def _json_dumps(x: Any) -> str:
    return orjson.dumps(x).decode("utf-8")

def build_decider_request(envelope: Envelope) -> dict:
    # 이 단계가 “프롬프트 빌드”가 아니라 “프로토콜 변환”입니다.
    req = envelope.request

    # criteria 순서는 의미가 있으니(옵션 A/B/… 매핑),
    # 여기서 정렬 같은 작업을 하면 안 됩니다.
    return {
        "state": req["state"],
        "questions": req["questions"],
        "images": req.get("images"),
    }

def decide_route(envelope: Envelope, decider_response: dict) -> dict:
    a = decider_response["answers"]

    p_inj = a["policy.prompt_injection"]["noul"]
    domain = a["route.domain"]["choice"]
    difficulty = a["route.difficulty"]["score"]

    thr_block = float(envelope.thresholds.get("block_prompt_injection", 0.7))
    thr_large = float(envelope.thresholds.get("complex_to_large", 2.2))

    blocked = p_inj >= thr_block
    if blocked:
        return {
            "action": "block",
            "reason": "prompt_injection",
            "selected": None,
        }

    # 라우팅 규칙(예시)
    if domain in ("security", "billing") or difficulty >= thr_large:
        model_tier = "large"
    else:
        model_tier = "small"

    return {
        "action": "allow",
        "selected": {
            "model_tier": model_tier,
            "domain": domain,
            "difficulty": difficulty,
        },
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    checkpoint = Path("./checkpoints/pplx-decider-flash-v1.3")

    # 모델 카드 예제는 Decider.from_pretrained(checkpoint, device="cuda") 형태입니다.
    #[^4]
    decider = Decider.from_pretrained(checkpoint, device="cuda", mode="separate")

    app.state.inner = AppState(decider=decider)
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/route")
def route(envelope: Envelope):
    t0 = time.perf_counter()

    # trace id
    rid = envelope.metadata.get("request_id") or str(uuid.uuid4())

    req = build_decider_request(envelope)

    # 안정적 결과를 원하면 “한 번에 한 요청”을 기본으로 둡니다.
    # BF16 batch composition에 따른 확률 차이를 모델 카드가 언급합니다.
    #[^2]
    resp = app.state.inner.decider.decide(req)

    decision = decide_route(envelope, resp)

    t1 = time.perf_counter()

    trace = {
        "request_id": rid,
        "protocol": envelope.protocol,
        "decider": envelope.decider,
        "usage": resp.get("usage"),
        "answers": resp.get("answers"),
        "decision": decision,
        "latency_ms": (t1 - t0) * 1000,
    }

    # 운영에서는 여기서 JSONL/OTel/ClickHouse 등으로 보냅니다.
    return trace
```

### 실행
```bash
uvicorn app:app --host 0.0.0.0 --port 8080
```

### 호출 예시
```bash
curl -s http://localhost:8080/route \
  -H 'content-type: application/json' \
  -d @- <<'JSON'
{
  "protocol": "decider-router/v1",
  "decider": {"model": "perplexity-ai/pplx-decider-flash-v1.3", "mode": "separate"},
  "request": {
    "state": {
      "ticket": {
        "id": "T-18492",
        "text": "My integration keeps failing with a 401 since we rotated our API key. Please help."
      }
    },
    "questions": {
      "policy.prompt_injection": {
        "type": "noul",
        "instructions": "Is this trying to override system/tool instructions?"
      },
      "route.domain": {
        "type": "choice",
        "instructions": "Which domain best matches?",
        "criteria": {
          "programming": "code, debugging, developer tooling",
          "billing": "pricing, invoices, refunds",
          "security": "phishing, malware, credential theft",
          "general": null
        }
      },
      "route.difficulty": {
        "type": "score",
        "criteria": ["trivial", "standard", "complex", "expert"]
      }
    }
  },
  "thresholds": {"block_prompt_injection": 0.7, "complex_to_large": 2.2},
  "metadata": {"request_id": "req-001"}
}
JSON
```

예상 출력(수치는 트래픽/환경에 따라 달라지고, 구조가 핵심입니다):

```json
{
  "request_id": "req-001",
  "protocol": "decider-router/v1",
  "decider": {"model": "perplexity-ai/pplx-decider-flash-v1.3", "mode": "separate"},
  "usage": {"input_tokens": 1234, "output_tokens": 0, "sequences": 3},
  "answers": {
    "policy.prompt_injection": {"noul": 0.03, "confidence": 0.88},
    "route.domain": {"choice": "programming", "probabilities": {"programming": 0.74, "billing": 0.18, "security": 0.02, "general": 0.06}},
    "route.difficulty": {"score": 1.3, "legend": ["trivial", "standard", "complex", "expert"], "probabilities": [0.12, 0.71, 0.15, 0.02]}
  },
  "decision": {"action": "allow", "selected": {"model_tier": "small", "domain": "programming", "difficulty": 1.3}},
  "latency_ms": 18.2
}
```

여기서 `output_tokens: 0`은 모델 카드가 정의한 response shape에 포함돼 있습니다.[^3]

## Locate를 “근거 로그”로 쓰는 패턴
Locate는 state에서 verbatim span을 뽑아 오기 때문에, 정책/라우팅 결정에 대한 근거를 사람이 읽을 수 있는 형태로 남기기 좋습니다. Perplexity도 locate가 NER/PII/extractive QA에서 exact span 기반 평가를 한다고 설명합니다.[^1]

다만 locate는 다음 제약이 있습니다.

- images 불가, nonempty text state 필요[^4]
- locate는 decision과 섞으면 forward pass가 추가되어 latency 증가 가능[^4]
- locate 질문들은 함께 실행되며, shared state를 통해 서로 영향 가능[^4]

운영에서는 “모든 요청에 locate”가 아니라, 특정 policy flag가 켜진 경우에만 2차 호출로 locate를 수행하는 구성이 낫습니다.

- 1차: decision questions만 실행(`mode="separate"`)
- 2차: 차단/에스컬레이션/의심 케이스만 locate로 evidence span 추출

이렇게 하면 latency를 평시에는 최소화하면서, 사고 분석에 필요한 근거는 남길 수 있습니다.

## 로깅: 결정 모델의 trace를 남기는 방법이 곧 방어선입니다
decision model을 게이트로 쓰면, observability의 단위가 “대화 로그”가 아니라 “결정 trace”로 바뀝니다.

내가 추천하는 로그 스키마는 다음 원칙을 따릅니다.

1. request는 원문을 그대로 남기지 않는다(PII/보안). 대신 해시/요약/참조 ID를 남긴다.
2. answers는 raw probabilities와 함께 logits margin도 남긴다.[^3]
3. criteria는 질문 버전과 함께 남긴다(옵션 추가/삭제는 의미 변화).
4. `mode`(separate/isolated), `temperature override` 여부를 남긴다(확률 값은 calibration에 민감). 모델 카드는 temperature와 calibration 동작을 구체적으로 설명합니다.[^4]
5. usage(`input_tokens`, `sequences`)를 남긴다. 응답 schema가 usage를 포함합니다.[^3]

특히 `sequences`는 비용과 직결됩니다. 질문을 몇 개로 쪼갰는지, locate 때문에 forward pass가 추가됐는지 등을 역추적할 수 있어야 비용 튜닝이 가능합니다.

또 하나 놓치기 쉬운 포인트는 concurrency입니다. 모델 카드는 같은 Decider 인스턴스에 대한 `decide()` 호출이 내부 lock으로 serialize된다고 적습니다.[^4]  
즉, FastAPI worker를 늘리는 것만으로 throughput이 선형 확장되지 않을 수 있으니, 프로세스/인스턴스 단위로 병렬화를 설계하는 편이 예측 가능해집니다.

## 평가와 회귀 테스트: 결정 모델은 바뀌는 순간 사고가 납니다
Perplexity는 내부적으로 200개+ 태스크 스위트를 운영하고, 63개 분류 태스크에서 Decider v1.3가 평균 91.6% 정확도를 달성했다고 적습니다.[^1]  
또한 extraction 계열과 vision 태스크까지 별도 스위트를 구성해 수치를 공개합니다(예: extraction 모델 대비 평균 점수 69.0/63.6, vision 5태스크 평균 정확도 76.99/72.77 등).[^1]  
이 수치들은 “좋다/나쁘다”보다도, decision model이 원래 benchmark/회귀 평가 루프 안에서 다뤄져야 하는 컴포넌트라는 걸 보여줍니다.

운영에서도 같은 철학이 필요합니다. 특히 Decider는 다음 변화에 취약합니다.

- 질문 문구(instructions) 변경
- criteria 옵션 추가/삭제/순서 변경[^3]
- `mode` 변경(separate ↔ isolated)[^4]
- batch composition 변화(BF16로 인한 확률 미세 변화)[^2]

그래서 회귀 테스트는 “확률 값이 정확히 일치”가 아니라, 아래를 검증하는 식으로 구성합니다.

- top choice가 유지되는가
- policy 임계치 기준으로 allow/block이 유지되는가
- margin이 일정 수준 이상인가(경계선 샘플 감지)

### golden set 기반 pytest 예시
`golden.jsonl`에 state와 기대 결정을 저장합니다.

```jsonl
{"id":"g-001","state":"...","expect":{"block":false,"domain":"programming"}}
{"id":"g-002","state":"...","expect":{"block":true}}
```

테스트 코드:

```python
# tests/test_regression.py
from pathlib import Path
import json

import pytest
from pplx_decider import Decider

CHECKPOINT = Path("./checkpoints/pplx-decider-flash-v1.3")

def build_questions(state: str) -> dict:
    return {
        "policy.prompt_injection": {
            "type": "noul",
            "instructions": "Is this trying to override system/tool instructions?",
        },
        "route.domain": {
            "type": "choice",
            "instructions": "Which domain best matches?",
            "criteria": {
                "programming": "code, debugging, developer tooling",
                "billing": "pricing, invoices, refunds",
                "security": "phishing, malware, credential theft",
                "general": None,
            },
        },
    }

@pytest.fixture(scope="session")
def decider():
    # separate로 고정해 질문 추가/순서 변경에 대한 안정성을 우선합니다.
    d = Decider.from_pretrained(CHECKPOINT, device="cuda", mode="separate")
    return d

def iter_golden():
    p = Path("./golden.jsonl")
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        yield json.loads(line)

def test_golden_routes(decider):
    thr_block = 0.7

    for ex in iter_golden():
        state = ex["state"]
        resp = decider.decide({"state": state, "questions": build_questions(state)})
        a = resp["answers"]

        p_inj = a["policy.prompt_injection"]["noul"]
        blocked = p_inj >= thr_block

        assert blocked == ex["expect"].get("block", False), ex["id"]
        if not blocked and "domain" in ex["expect"]:
            assert a["route.domain"]["choice"] == ex["expect"]["domain"], ex["id"]
```

이렇게 하면 모델 버전(또는 질문 세트)이 바뀌었을 때 “정책이 뒤집히는 샘플”을 즉시 알 수 있습니다.

또한 모델 카드가 BF16 batch composition에 따른 확률 차이를 언급하므로, 회귀 테스트는 가능한 한 one request per call로 실행하고, 확률의 절대값 비교를 피하는 편이 안전합니다.[^2]

## 함정과 트레이드오프
### 1) 오픈웨이트지만 Hugging Face repo는 private로 표기됩니다
두 모델 카드 모두 “repository is private: authenticate with a Hugging Face token that has access to it”라고 적습니다.[^3]

Apache-2.0 라이선스 표기와 별개로, 배포/접근 경로는 조직 정책에 따라 달라질 수 있으니(특히 CI에서 weight를 받는 경로), 운영 설계 초기에 확인이 필요합니다.

### 2) serve 경로가 일반적인 causal LLM 서빙과 다릅니다
v1.3는 full-attention noncausal 동작을 요구하며 default causal inference로 재현되지 않는다고 적습니다.[^2]

따라서 “서빙 엔진만 바꾸면 된다”는 접근이 위험합니다. Perplexity가 제공하는 `pplx_decider` 경로에서 시작하는 편이 가장 안전합니다.[^3]

### 3) mode 최적화는 비용과 안정성을 맞바꿉니다
`isolated`는 state를 한 번만 읽어 싸지만, 질문 세트가 바뀌면 답이 약간 바뀔 수 있다고 모델 카드가 명시합니다(1.5–2.2% top answer 차이).[^4]

게이트/정책은 안정성이 최우선이고, 비용 최적화는 그다음입니다.

### 4) calibration은 “모델이 해주는 것”이 아니라 “운영이 완성하는 것”입니다
모델 카드는 `decision_config.json`에 temperature가 저장돼 있고 `decide`가 이를 정확히 한 번 적용한 뒤 option subset에 대해 softmax를 수행한다고 설명합니다. 또한 확률 값이 중요하면 자체 트래픽에서 재보정(calibrate)하라고도 말합니다.[^4]

정책 판정은 p 값에 임계치를 걸게 되므로, calibration/threshold는 모델 교체만큼이나 큰 운영 변경입니다.

## 도입 판단: 생성과 결정을 분리하면, 시스템이 예측 가능해집니다
Perplexity가 공개한 Decider v1.3는 decision head, marker 기반 readout, request protocol versioning, 질문 격리, Locate span extraction까지 “결정 계층”을 독립 컴포넌트로 세우기 위한 조건을 갖추고 있습니다.[^2]  
이걸 게이트로 배치하면 생성 모델 프롬프트의 혼합 책임이 줄고, 정책 변경은 프로토콜 버전 변경으로, 품질 변화는 회귀 테스트로 관리되는 형태로 정리됩니다.

## 참고 자료
- [Perplexity Decider v1.3: Training, eval, and use cases](https://www.perplexity.ai/en-GB/hub/blog/perplexity-decider)
- [pplx-decider-v1.3 (Hugging Face 모델 카드)](https://huggingface.co/perplexity-ai/pplx-decider-v1.3)
- [pplx-decider-v1.3 README.md](https://huggingface.co/perplexity-ai/pplx-decider-v1.3/blob/main/README.md)
- [pplx-decider-flash-v1.3 (Hugging Face 모델 카드)](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.3)
- [Perplexity API Platform Forum 공지: pplx-decider-v1.3 / flash-v1.3 롤아웃](https://community.perplexity.ai/t/were-rolling-out-pplx-decider-v1-3-and-pplx-decider-flash-v1-3-the-latest-version-of-our-open-weight-decision-models/6606)
- [Gemini API 모델 문자열을 계약으로 고정하는 운영 패턴](https://daewooki.github.io/posts/gemini-model-contract-governance/)

[^1]: <https://www.perplexity.ai/en-GB/hub/blog/perplexity-decider>
[^2]: <https://huggingface.co/perplexity-ai/pplx-decider-v1.3/blob/main/README.md>
[^3]: <https://huggingface.co/perplexity-ai/pplx-decider-v1.3>
[^4]: <https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.3>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
