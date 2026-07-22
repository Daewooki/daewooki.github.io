---
title: "합성 데이터로 파인튜닝 성능을 “올리는” 게 아니라 “망치지 않는” 2026년식 LLM Synthetic Data 파이프라인"
date: 2026-07-22 03:26:20 +0900
categories: [AI, Data]
tags: [ai, data, trend, 2026-07]
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
LLM 파인튜닝용 데이터가 부족할 때, 요즘(2026년 7월 기준) 가장 현실적인 해법은 **LLM으로 합성 데이터(synthetic data)를 만들고, 다시 LLM/룰로 검증·정제해 SFT/DPO 학습셋으로 굳히는 방식**입니다. Meta의 `synthetic-data-kit`처럼 “생성 → 큐레이션 → 포맷 저장”을 파이프라인으로 고정하는 도구가 등장한 것도 같은 흐름입니다. ([github.com](https://github.com/meta-llama/synthetic-data-kit?utm_source=openai))

다만 합성 데이터는 “공짜 라벨”이 아니라 **교사(teacher) 모델의 편향/환각/스타일을 증폭**시키기 쉬워서, 잘못 쓰면 모델을 더 멍청하게 만들거나(특히 tool calling), 특정 실패 모드를 학습시키는 지름길이 됩니다. 실제로 OpenAI는 “오답을 내는 합성 데이터로 파인튜닝하면 좁은 도메인에서도 예상치 못한 misalignment가 emergent하게 나타날 수 있다”는 실험을 공개했습니다. ([openai.com](https://openai.com/index/emergent-misalignment/?utm_source=openai))

### 언제 쓰면 좋나
- **라벨링 비용이 큰 도메인**(법률/의료/사내 티켓)에서 “정답 형식”이 명확하고, 사람이 만든 seed + 규칙/스키마로 품질을 강하게 통제할 수 있을 때
- **tool calling / agent trajectory**처럼 “행동 로그”를 많이 모아야 하는데, 실제 환경에서 수집이 느리거나 위험할 때(최근엔 “환경 없이(environment-free) API-calling agent 데이터 생성” 연구도 나옴) ([arxiv.org](https://arxiv.org/abs/2607.16900?utm_source=openai))
- **개인정보/민감정보** 때문에 원본을 그대로 학습에 못 쓰고, 구조를 보존한 합성 데이터로 distillation해야 할 때(의료 노트 합성 파이프라인 연구가 계속 나옴) ([arxiv.org](https://arxiv.org/abs/2606.26879?utm_source=openai))

### 언제 쓰면 안 되나
- “그럴듯한 답”이 아니라 **사실성(ground truth)**이 핵심인 태스크인데, 검증 소스/룰/테스트가 없을 때  
- **eval contamination**을 통제하지 못할 때(합성 데이터 생성 과정에서 평가 문제/정답이 섞이면 성능이 과대평가될 수 있음) ([openai.com](https://openai.com/index/trustworthy-third-party-evaluations-foundations/?utm_source=openai))
- 합성 데이터만으로 “전부 해결”하려는 경우: 보통은 **작은 고품질 human set + 합성 확장 + 엄격한 필터링**이 더 안정적입니다(실무/연구 공통 결론).

---

## 🔧 핵심 개념
### 1) LLM 합성 데이터 생성의 3가지 역할
1. **Generator(교사)**: seed/스키마/도메인지식을 바탕으로 instruction-response(혹은 multi-turn, tool calls)를 생성  
2. **Critic/Judge(검증자)**: 생성 결과를 기준(정확성/형식/정책/근거성/금칙 등)으로 판정·스코어링  
3. **Curator(편집자)**: 통과 샘플만 남기고 중복/오염/난이도 분포를 재조정해 학습셋으로 패키징

Anthropic의 Constitutional AI 계열은 “원칙(Constitution) → 합성 프롬프트/응답 대량 생성 → 학습”의 형태로, **규칙 문서가 데이터 공장(factory)의 기준**이 됩니다. ([anthropic.com](https://www.anthropic.com/research/constitutional-classifiers?utm_source=openai))

### 2) “단발 생성”이 아니라 “루프”가 중요한 이유
합성 데이터의 실패는 대부분 **(a) 분포 미스매치, (b) 환각, (c) 스타일 단일화, (d) 평가 오염**으로 발생합니다. 그래서 2026년의 실전 파이프라인은 대체로:

- Seed(현업 로그/케이스/스키마)
- Expand(다양화: 난이도/변형/언어/오류 케이스)
- Validate(LLM-as-a-Judge + 규칙 기반)
- Decontaminate(중복/유사도/평가셋 누수 체크)
- Save(학습 프레임워크 포맷으로 고정)

Meta `synthetic-data-kit`이 **ingest → create → curate → save-as** 4단계를 CLI로 고정한 것도 “생성 스크립트”가 아니라 “데이터 엔지니어링 파이프라인”으로 보려는 방향입니다. ([github.com](https://github.com/meta-llama/synthetic-data-kit?utm_source=openai))

### 3) 다른 접근과의 차이
- **RAG**: 지식 주입이 아니라 “런타임 참조”. 합성 데이터는 **행동/형식/정책 준수/도메인 작업 절차**를 모델 파라미터에 새길 때 유리
- **Pure human labeling**: 품질은 높지만 비싸고 느림. 합성은 빠르지만 “품질 통제 비용(검증/필터링/평가)”이 숨은 비용
- **Dataset Distillation(학술 DD)**: 목표는 “작은 합성셋으로 큰 데이터의 학습효과 재현”. LLM 합성 instruction data는 보통 “업무 시나리오 커버리지”에 더 초점(둘을 혼동하면 설계가 꼬입니다). (DD 평가지표/일관성 이슈도 계속 지적됨) ([openreview.net](https://openreview.net/forum?id=WbVTxfv1Mp&utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: **사내 “장애 티켓 → Runbook 기반 조치 제안”** 에이전트를 만들고, tool calling 형태로 파인튜닝할 데이터를 합성으로 구축합니다.

- 입력: 티켓 요약 + 로그 일부
- 출력: (1) 필요한 조회 tool call, (2) 결과를 근거로 최종 조치안
- 핵심: **형식 엄수 + 근거성 + 과잉 확신 금지 + 중복 제거 + Judge 통과만 학습**

### 0) 준비: vLLM로 로컬 OpenAI-compatible 엔드포인트 띄우기
```bash
# (예) vLLM OpenAI-compatible server
pip install vllm

# Hugging Face 모델로 서빙 (환경에 맞게 모델 교체)
vllm serve meta-llama/Llama-3.3-70B-Instruct --port 8000
```
vLLM은 OpenAI-compatible API 서버를 제공해 “생성 파이프라인/도구”가 붙이기 쉬운 게 장점입니다. ([docs.vllm.ai](https://docs.vllm.ai/en/latest/index.html?utm_source=openai))

### 1) 합성 데이터 생성 + tool call 스키마 강제 + 1차 규칙 검증
```python
import json, re, uuid, time
from typing import Dict, Any, List
from openai import OpenAI

# vLLM OpenAI-compatible endpoint
client = OpenAI(base_url="http://localhost:8000/v1", api_key="EMPTY")

TOOLS = [{
  "type": "function",
  "function": {
    "name": "query_metrics",
    "description": "Fetch time-series metrics for a service",
    "parameters": {
      "type": "object",
      "properties": {
        "service": {"type": "string"},
        "metric": {"type": "string", "enum": ["p95_latency_ms","error_rate","cpu_pct","mem_pct"]},
        "window_minutes": {"type": "integer", "minimum": 5, "maximum": 180}
      },
      "required": ["service","metric","window_minutes"]
    }
  }
}]

SYSTEM = """You are an SRE assistant.
You MUST:
- call query_metrics at least once before proposing actions
- never claim certainty; use calibrated language
- produce an incident_action_plan with: hypothesis, evidence, actions, rollback, risks
Return valid JSON ONLY with keys:
tool_calls (array) and incident_action_plan (object).
"""

SEED_TICKETS = [
  {
    "ticket_id": "INC-18421",
    "service": "checkout",
    "symptoms": "결제 API 5xx 급증, p95 latency 상승. 최근 배포 있음.",
    "log_snippet": "POST /pay 502 upstream reset; region=us-east-1; build=2026.07.18-rc3"
  },
  {
    "ticket_id": "INC-18466",
    "service": "search",
    "symptoms": "검색 결과 지연, CPU 90% 지속. 캐시 hit-rate 감소 의심.",
    "log_snippet": "redis timeout; cache_miss spike; node=search-12"
  },
]

def rule_validate(sample: Dict[str, Any]) -> List[str]:
    errs = []
    if "tool_calls" not in sample or not isinstance(sample["tool_calls"], list) or len(sample["tool_calls"]) == 0:
        errs.append("missing_tool_calls")
    plan = sample.get("incident_action_plan", {})
    for k in ["hypothesis","evidence","actions","rollback","risks"]:
        if k not in plan:
            errs.append(f"missing_plan_{k}")
    # 과잉 확신 표현 간단 차단(실전에서는 더 정교하게)
    blob = json.dumps(sample, ensure_ascii=False).lower()
    if any(x in blob for x in ["확실", "100%", "무조건", "guarantee"]):
        errs.append("overconfident_language")
    return errs

def generate_one(ticket: Dict[str, str]) -> Dict[str, Any]:
    user = f"""Ticket:
id={ticket['ticket_id']}
service={ticket['service']}
symptoms={ticket['symptoms']}
logs={ticket['log_snippet']}
Create a realistic plan for oncall SRE."""
    resp = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":user}],
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.6,
    )
    content = resp.choices[0].message.content
    # 모델이 JSON 외 텍스트를 섞을 수 있어 방어적으로 파싱
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise ValueError("No JSON object found")
    sample = json.loads(m.group(0))
    sample["_meta"] = {"ticket_id": ticket["ticket_id"], "gen_id": str(uuid.uuid4()), "ts": int(time.time())}
    return sample

rows = []
for t in SEED_TICKETS:
    s = generate_one(t)
    errs = rule_validate(s)
    if errs:
        continue
    rows.append(s)

print("kept:", len(rows))
print(json.dumps(rows[0], ensure_ascii=False, indent=2)[:800])
```

예상 출력(요약):
- `kept: 2`
- `tool_calls`에 `query_metrics(service="checkout", metric="error_rate", window_minutes=30)` 같은 호출이 들어가고,
- `incident_action_plan`에 hypothesis/evidence/actions/rollback/risks가 채워짐

### 2) LLM-as-a-Judge로 2차 검증(근거성/형식/현실성) 후 OpenAI fine-tuning JSONL로 저장
여기서 Judge는 **“Generator와 다른 모델/프롬프트”**를 쓰는 게 일반적으로 유리합니다(자기복제 편향 감소). 그리고 OpenAI가 언급한 것처럼 평가/데이터 오염(contamination)은 결과를 거짓으로 만들 수 있으니, Judge 프롬프트에도 “seed/eval 문항 재사용 금지” 같은 가드를 두는 편이 좋습니다. ([openai.com](https://openai.com/index/trustworthy-third-party-evaluations-foundations/?utm_source=openai))

```python
import json
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="EMPTY")

JUDGE_SYSTEM = """You are a strict dataset judge for SFT.
Score 0-5 on:
- format_validity
- tool_call_correctness
- evidence_grounding
- action_safety
Return JSON only:
{ "score": <0..5>, "reasons": [..], "fix_suggestions": [..] }
"""

def judge(sample):
    resp = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages=[
            {"role":"system","content":JUDGE_SYSTEM},
            {"role":"user","content":json.dumps(sample, ensure_ascii=False)}
        ],
        temperature=0.0,
    )
    j = json.loads(resp.choices[0].message.content)
    return j

def to_openai_chat_jsonl(sample):
    # SFT용: user에 ticket, assistant에 최종 JSON(혹은 plan만) 고정
    ticket_id = sample["_meta"]["ticket_id"]
    assistant = json.dumps({
        "tool_calls": sample["tool_calls"],
        "incident_action_plan": sample["incident_action_plan"]
    }, ensure_ascii=False)
    return {
        "messages": [
            {"role":"system","content":SYSTEM},
            {"role":"user","content":f"Ticket id={ticket_id}. Generate response."},
            {"role":"assistant","content":assistant}
        ]
    }

final = []
for s in rows:
    j = judge(s)
    if j["score"] >= 4:
        final.append(to_openai_chat_jsonl(s))

with open("sre_toolcalling_sft.jsonl", "w", encoding="utf-8") as f:
    for r in final:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print("final_sft_rows:", len(final))
```

이렇게 만들어진 JSONL은 “파인튜닝 입력 포맷”으로 바로 쓰거나, `synthetic-data-kit` 같은 파이프라인 도구에 넣어 **curate/save-as 단계**를 자동화하는 식으로 확장할 수 있습니다. ([github.com](https://github.com/meta-llama/synthetic-data-kit?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (진짜로 성능을 올리는 쪽)
1) **합성 데이터는 ‘확장’이고, 기준은 ‘작은 고품질 real set’**
- 최소 50~200개라도 현업 전문가가 만든 **골든 셋(평가+필터 기준)**을 먼저 확보하세요.
- 그 골든 셋으로 Judge를 튜닝하거나(프롬프트/룰), 합성 샘플을 필터링하는 게 ROI가 큽니다.

2) **Decontamination을 “절차”로 박아넣기**
- 중복 제거(문자열/semantic), seed 재노출, eval 문제 유입을 파이프라인 단계로 고정하세요.
- OpenAI가 신뢰 가능한 평가에서 contamination을 명시적으로 경고하는 이유가, 여기서 한 번 새면 “좋아 보이는 지표”가 전부 허상이 되기 때문입니다. ([openai.com](https://openai.com/index/trustworthy-third-party-evaluations-foundations/?utm_source=openai))

3) **행동 데이터(특히 tool calling)는 ‘형식 안정성’이 절반**
- tool schema, JSON-only, refusal/uncertainty 표현, multi-turn state… 이건 모델이 “알아서” 맞추지 않습니다.
- 생성 단계에서 스키마 강제 + 규칙 검증 + Judge 검증의 3중 잠금이 필요합니다.

### 흔한 함정/안티패턴
- **Generator=Judge 동일 모델/동일 프롬프트**: “그럴듯한 자기합리화”만 늘고 품질이 안 올라갑니다.
- **합성 데이터만 잔뜩**: 스타일이 단일화되고, 환각 패턴이 고정됩니다.
- **‘오답/취약코드’ 류의 합성셋을 검증 없이 섞기**: OpenAI가 보여준 것처럼 좁은 오답 학습도 예기치 못한 misalignment를 유발할 수 있습니다. ([openai.com](https://openai.com/index/emergent-misalignment/?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **비용**: 생성 자체보다 “검증(다중 샘플, Judge, 재생성 루프)”이 비용을 먹습니다. 그래도 이 비용을 안 쓰면 파인튜닝 비용이 더 크게 낭비됩니다.
- **성능**: 합성 데이터로 얻는 이득은 보통 “도메인 절차/형식/일관성” 쪽이 크고, “사실 지식”은 RAG/툴로 해결하는 편이 안전합니다.
- **안정성**: 합성 데이터는 작은 버그(포맷, tool args, role 누락)가 전체 모델 행동을 망칠 수 있어, 데이터 린팅/CI가 중요합니다.

---

## 🚀 마무리
2026년의 LLM synthetic data는 “LLM이 데이터도 만든다”가 아니라, **데이터를 소프트웨어처럼 설계·검증·배포하는 파이프라인**으로 보는 게 핵심입니다. `synthetic-data-kit` 같은 4단계(ingest/create/curate/save-as) 파이프라인화 흐름이 이를 잘 보여줍니다. ([github.com](https://github.com/meta-llama/synthetic-data-kit?utm_source=openai))

도입 판단 기준은 간단합니다.
- **골든(real) eval 셋이 있는가?** (없으면 먼저 만든다)
- **합성 샘플을 떨어뜨릴 Judge/룰이 있는가?**
- **contamination/중복/포맷 붕괴를 막는 자동화 단계가 있는가?** ([openai.com](https://openai.com/index/trustworthy-third-party-evaluations-foundations/?utm_source=openai))
- 합성으로 학습시키려는 것이 “지식”인가 “행동/형식/절차”인가? (후자일수록 성공 확률이 큼)

다음 학습으로는 (1) Constitutional AI/RLAIF 계열의 “원칙 기반 합성 데이터 생성 루프” 개념을 참고해 **내 도메인의 constitution(규칙 문서)**를 만들어보고 ([anthropic.com](https://www.anthropic.com/research/constitutional-classifiers?utm_source=openai)), (2) agent/tool-calling 합성 데이터는 최신 연구처럼 “환경 없이도 궤적을 만들고 Judge로 필터링”하는 접근을 살펴보는 것을 추천합니다. ([arxiv.org](https://arxiv.org/abs/2607.16900?utm_source=openai))