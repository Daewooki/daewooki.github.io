---
title: "2026년 5월, “AI Agent의 Tool Use/Function Calling”을 프로덕션에 넣는 법: Responses API + Agents SDK 패턴 정리"
date: 2026-05-02 03:36:58 +0900
categories: [AI, Agent]
tags: [ai, agent, trend, 2026-05]
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
AI Agent에서 **tool use(function calling)** 는 “모델이 말로만 아는 척” 하는 구간을 줄이고, **외부 시스템(DB/HTTP/Queue/사내 API)과 실제로 일하게 만드는 연결부**입니다. 2026년 5월 기준 흐름은 “프롬프트로 JSON 뽑아 파싱”이 아니라, **모델이 `tool_call`을 생성 → 앱이 실행/검증 → 결과를 `tool_result`로 다시 주입**하는 루프가 표준으로 굳어졌습니다. (OpenAI는 Responses API 중심으로 통합을 밀고 있고, Agents SDK/Tracing까지 한 덩어리로 제공합니다.) ([platform.openai.com](https://platform.openai.com/docs/guides/function-calling?api-mode=chat&utm_source=openai))

**언제 쓰면 좋은가**
- “답변”이 아니라 **업무 실행**이 핵심일 때: 티켓 분류/요약+Jira 업데이트, 주문 상태 조회+환불 프로세스, 리서치+사내 위키 기록 등
- **결정 근거가 외부 데이터**에 있을 때: 최신 가격/재고/정책/로그/권한
- 다단계 작업을 자동화하되, **실행 레이어(guardrails/승인/감사)** 를 코드로 잡을 수 있을 때

**언제 쓰면 안 되는가**
- tool이 “항상” 필요 없는 단순 Q&A: tool 스키마 토큰/호출 비용이 과함
- **정확성보다 지연이 더 치명적**인 초저지연 UX(실시간 음성 등): tool 호출이 latency를 늘리고, 상태 관리가 복잡해짐(특히 멀티모달)  
- 보안/감사 체계 없이 “사내 전체 API를 전부 툴로 노출”하려는 경우: 공격면(tool abuse/prompt injection)이 크게 늘어남 (OWASP LLM Top 10에서도 에이전트/툴 악용이 핵심 이슈로 거론됨) ([zylos.ai](https://zylos.ai/research/2026-04-07-tool-use-function-calling-standards-benchmarks?utm_source=openai))

---

## 🔧 핵심 개념
### 1) 주요 개념 정의
- **Tool definition**: 모델에게 “이런 함수가 있고, 입력은 이 JSON 스키마”라고 알려주는 계약. (OpenAI는 `tools: [{type:"function", function:{name, description, parameters}}]`) ([platform.openai.com](https://platform.openai.com/docs/guides/function-calling?api-mode=chat&utm_source=openai))
- **Tool call**: 모델이 “이 함수를 이 인자로 호출해줘”라고 **요청**하는 구조화 이벤트(실행은 모델이 아니라 애플리케이션이 함). ([platform.openai.com](https://platform.openai.com/docs/guides/function-calling?api-mode=chat&utm_source=openai))
- **Tool result**: 앱이 실제 실행 후 결과를 다시 모델 컨텍스트에 넣는 메시지/이벤트.
- **Agent loop**: (모델 추론 → tool call 생성 → 실행/검증 → 결과 주입 → 다음 추론) 반복. Responses API는 이 멀티턴/툴 흐름을 단일 인터페이스로 수렴시키는 방향입니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))

### 2) 내부 작동 방식(구조/흐름)
프로덕션에서 가장 안정적인 패턴은 아래 5단계입니다.

1. **모델 호출(Responses API)**: 시스템 지시 + 유저 요청 + *현재 단계에서 허용할 tool subset* 을 함께 보냄  
2. **모델이 tool_call을 생성**: 어떤 함수를 어떤 args로 호출할지 구조화해서 반환  
3. **애플리케이션 실행 레이어가 검증**:
   - JSON Schema validation (타입/필수 필드)
   - 정책 체크(권한/레이트리밋/허용된 범위)
   - idempotency/중복 호출 차단
4. **툴 실행 후 결과를 tool_result로 주입**
5. **다음 모델 호출**: 결과를 근거로 후속 액션/요약/추가 호출 결정

여기서 **핵심은 “툴 실행 정책은 프롬프트가 아니라 코드”** 로 잡는 겁니다. “한 번만 호출해” 같은 프롬프트 지시는 종종 깨집니다. 중복 호출/재시도는 실행 레이어에서 막고, 툴은 idempotent하게 설계하는 게 2026년에도 정석으로 반복해서 언급됩니다. ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1q9vzsi/agent_calling_tools_multiple_times/?utm_source=openai))

### 3) 다른 접근과의 차이점
- **(구) JSON 출력 파싱 방식** vs **(현) native tool calling**
  - 전자: 모델이 텍스트로 JSON을 “써주면” 파서가 실행 → 포맷 일탈/인젝션/예외처리가 지옥
  - 후자: 모델이 `tool_call` 구조를 만들고, 앱이 안전하게 실행/회수 → 운영/감사가 쉬움 ([platform.openai.com](https://platform.openai.com/docs/guides/function-calling?api-mode=chat&utm_source=openai))
- **모든 tool을 한 번에 노출** vs **단계별 tool gating**
  - 전자: tool 정의가 곧 컨텍스트 비용(수만 토큰) + 잘못된 선택 증가
  - 후자: “지금 단계에서 필요한 최소 tool만” 제공 → 비용/정확도/안정성 개선 (실무에서 체감이 큼) ([reddit.com](https://www.reddit.com/r/SideProject/comments/1sijlgf/the_hidden_problem_with_giving_ai_agents_200_api/?utm_source=openai))
- **단일 호출 순차 실행** vs **병렬/배치 실행**
  - 연구/현장 모두 “여러 툴 호출을 병렬로” 하는 방향이 성능 상 이점이 큼(폭(width) 확장) ([zylos.ai](https://zylos.ai/research/2026-04-07-tool-use-function-calling-standards-benchmarks?utm_source=openai))
- **스트리밍/소켓 기반 루프**
  - 툴 호출이 많아질수록 “모델 추론보다 API/클라이언트 오버헤드”가 커지며, 이를 줄이기 위한 WebSocket/비동기 루프 최적화가 실제로 다뤄지고 있습니다. ([openai.com](https://openai.com/index/speeding-up-agentic-workflows-with-websockets/?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: **온콜 SRE 티켓 triage 에이전트**
- 티켓 내용(증상/서비스/에러)을 입력받아
- (1) 최근 30분 로그 요약 조회 (2) 런북 검색 (3) 필요 시 Jira에 코멘트/라벨링
- 단, **권한/중복 실행/비용**을 코드로 통제

아래 예제는 “toy”가 아니라, 실제로 많이 쓰는 **HTTP 기반 내부 도구 2개 + 티켓 업데이트 1개**를 tool로 엮고, **tool gating + idempotency + 검증**까지 포함합니다.

### 0) 설정/의존성
```bash
python -m venv .venv
source .venv/bin/activate
pip install openai pydantic httpx
export OPENAI_API_KEY="..."
```

### 1) Tool 스키마 + 실행 레이어(검증/중복 방지)
```python
from __future__ import annotations
import json, hashlib, time
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pydantic import BaseModel, Field, ValidationError

from openai import OpenAI

client = OpenAI()

# ---- 1) Tool input schemas (Pydantic로 런타임 검증) ----
class LogQuery(BaseModel):
    service: str = Field(min_length=2, max_length=50)
    since_minutes: int = Field(ge=1, le=120)
    contains: Optional[str] = Field(default=None, max_length=200)

class RunbookSearch(BaseModel):
    query: str = Field(min_length=3, max_length=200)
    service: Optional[str] = Field(default=None, max_length=50)

class JiraComment(BaseModel):
    ticket_id: str = Field(pattern=r"^[A-Z]+-\d+$")
    comment_md: str = Field(min_length=10, max_length=4000)
    labels: List[str] = Field(default_factory=list, max_length=10)

# ---- 2) 실제 tool 구현(여기서는 내부 HTTP API 호출로 가정) ----
async def fetch_logs(args: LogQuery) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get(
            "https://internal-observability.example/logs",
            params={"service": args.service, "since": args.since_minutes, "q": args.contains or ""},
        )
        r.raise_for_status()
        return r.json()

async def search_runbook(args: RunbookSearch) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get(
            "https://internal-knowledge.example/runbooks/search",
            params={"q": args.query, "service": args.service or ""},
        )
        r.raise_for_status()
        return r.json()

async def post_jira_comment(args: JiraComment) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.post(
            "https://internal-jira-proxy.example/tickets/comment",
            json=args.model_dump(),
        )
        r.raise_for_status()
        return r.json()

TOOL_REGISTRY = {
    "fetch_logs": (LogQuery, fetch_logs),
    "search_runbook": (RunbookSearch, search_runbook),
    "post_jira_comment": (JiraComment, post_jira_comment),
}

# ---- 3) idempotency / 중복 호출 방지(프롬프트 말고 코드로) ----
class ToolDeduper:
    def __init__(self):
        self.seen = set()

    def key(self, name: str, args: Dict[str, Any]) -> str:
        blob = json.dumps({"name": name, "args": args}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def check_and_mark(self, name: str, args: Dict[str, Any]) -> bool:
        k = self.key(name, args)
        if k in self.seen:
            return False
        self.seen.add(k)
        return True
```

### 2) Responses API 호출 + “단계별 tool gating” 루프
포인트:
- **1턴에 모든 툴을 다 주지 않고**, “진단 단계”에는 read-only 툴만, “조치 단계”에만 write 툴(post_jira_comment)을 허용
- tool args는 **Pydantic로 강검증**하고, 실패 시 모델에 “왜 실패했는지”를 tool_result로 돌려 재시도 유도

```python
import asyncio

def tools_for_phase(phase: str) -> List[Dict[str, Any]]:
    # OpenAI function calling 스키마 형태(요지만)
    # 실제론 parameters에 JSON Schema를 넣습니다.
    base = []
    if phase == "diagnose":
        base += [
            {
                "type": "function",
                "function": {
                    "name": "fetch_logs",
                    "description": "최근 로그를 조회한다(읽기 전용).",
                    "parameters": LogQuery.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_runbook",
                    "description": "런북/운영 문서를 검색한다(읽기 전용).",
                    "parameters": RunbookSearch.model_json_schema(),
                },
            },
        ]
    if phase == "act":
        base += [
            {
                "type": "function",
                "function": {
                    "name": "post_jira_comment",
                    "description": "티켓에 코멘트/라벨을 남긴다(쓰기 작업, 신중히).",
                    "parameters": JiraComment.model_json_schema(),
                },
            }
        ]
    return base

async def run_ticket_agent(ticket_id: str, ticket_text: str) -> str:
    deduper = ToolDeduper()
    phase = "diagnose"

    # Responses API는 tool call/streaming/멀티턴을 한 흐름으로 다루는 방향(공식 가이드 참고) ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))
    input_messages = [
        {
            "role": "system",
            "content": (
                "너는 온콜 SRE 티켓 triage 에이전트다.\n"
                "- 사실은 tool 결과로만 주장한다.\n"
                "- diagnose 단계에서는 읽기 도구만 사용한다.\n"
                "- act 단계에서만 Jira 업데이트를 한다.\n"
                "- 같은 tool call을 반복하지 않는다(중복이면 다른 접근).\n"
                "- 최종 출력은: (1) 원인 가설 (2) 근거 (3) 다음 액션 (4) Jira 반영 내용"
            ),
        },
        {"role": "user", "content": f"[{ticket_id}] {ticket_text}"},
    ]

    for step in range(1, 6):  # 최대 5번 루프
        resp = client.responses.create(
            model="gpt-4.1",  # 예시. 프로젝트 정책에 맞는 모델 사용
            input=input_messages,
            tools=tools_for_phase(phase),
        )

        # 1) 모델이 tool call 없이 답하면 종료
        tool_calls = []
        for item in resp.output:
            if item.type == "tool_call":
                tool_calls.append(item)

        if not tool_calls:
            # 마지막 assistant 텍스트를 반환(단순화)
            return "".join([o.content[0].text for o in resp.output if o.type == "message"])

        # 2) tool calls 실행
        for tc in tool_calls:
            name = tc.name
            args = tc.arguments  # dict로 온다고 가정(실제 SDK 형태에 맞게 변환)
            if name not in TOOL_REGISTRY:
                input_messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps({"error": "unknown_tool"}, ensure_ascii=False),
                })
                continue

            if not deduper.check_and_mark(name, args):
                input_messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps({"error": "duplicate_call_blocked"}, ensure_ascii=False),
                })
                continue

            schema_cls, fn = TOOL_REGISTRY[name]
            try:
                validated = schema_cls.model_validate(args)
                result = await fn(validated)
                input_messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps({"ok": True, "data": result}, ensure_ascii=False),
                })
            except ValidationError as e:
                input_messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps({"ok": False, "validation_error": e.errors()}, ensure_ascii=False),
                })
            except Exception as e:
                input_messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps({"ok": False, "runtime_error": str(e)}, ensure_ascii=False),
                })

        # 3) diagnose 결과가 충분하면 act 단계로 전환(룰은 단순 예시)
        if phase == "diagnose":
            phase = "act"

    return "에이전트가 제한된 step 내에 수렴하지 못했습니다. 로그/런북 결과를 검토해 수동 triage가 필요합니다."

if __name__ == "__main__":
    print(asyncio.run(run_ticket_agent(
        "SRE-1842",
        "checkout 서비스에서 500 증가. 최근 배포 직후부터. 오류 메시지에 'DB timeout'이 보임."
    )))
```

#### 예상 출력(예시)
- 원인 가설: checkout → payments DB 커넥션 풀 고갈/timeout
- 근거: 최근 30분 로그에서 timeout spike, 런북에서 동일 패턴(커넥션 풀/slow query)
- 다음 액션: (1) read replica 상태 확인 (2) 풀 설정 롤백/확대 (3) 배포 롤백 여부 판단
- Jira 반영: 티켓에 런북 링크/라벨(`db-timeout`, `needs-rollback-review`) 코멘트 작성

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **Tool gating(단계별 최소 툴 노출)**  
   툴을 많이 줄수록 “선택 비용(토큰) + 오선택 확률”이 커집니다. 특히 MCP/툴 표준화 흐름이 오더라도, “모든 것을 항상 컨텍스트에 올리는 방식”은 비용이 터집니다. “진단(read) → 조치(write)”로 툴을 쪼개면 실패율이 눈에 띄게 줄어듭니다. ([reddit.com](https://www.reddit.com/r/SideProject/comments/1sijlgf/the_hidden_problem_with_giving_ai_agents_200_api/?utm_source=openai))

2) **Idempotency + 중복 호출 차단은 필수**  
   모델은 같은 호출을 반복할 수 있고(프롬프트로 100% 막기 어려움), 네트워크 재시도까지 겹치면 실제 시스템에 중복 쓰기가 발생합니다. **request_id(또는 args hash) 기반 dedupe**를 넣고, 쓰기 툴은 서버도 idempotent하게 설계하세요. ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1q9vzsi/agent_calling_tools_multiple_times/?utm_source=openai))

3) **Observability/Tracing을 먼저 깔고 시작**  
   “왜 그 tool을 골랐는지 / 어떤 args로 몇 번 호출했는지 / 어떤 결과가 들어왔는지”가 안 보이면 운영이 불가능합니다. OpenAI는 Agents SDK에 Tracing을 같이 엮는 방향을 문서/가이드에서 강조합니다. ([help.openai.com](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api%29%5B?utm_source=openai))

### 흔한 함정/안티패턴
- **툴 스키마를 ‘문서’처럼 길게 쓰기**: description이 길면 토큰만 잡아먹고, 모델이 중요한 제약을 놓칩니다. 제약은 “짧고 강하게” + “코드 검증”으로.
- **tool output에 원문 로그를 그대로 넣기**: 컨텍스트 폭발. 로그는 서버에서 요약/집계해서 주고, 원문은 링크/핵심 라인만.
- **모델에게 라우팅을 100% 맡기기**: “어떤 단계에서 어떤 툴이 가능한지”는 제품 정책입니다. 모델은 정책 집행자가 아니라 *의사결정 보조자*로 두는 게 안전합니다.

### 비용/성능/안정성 트레이드오프
- **성능**: 툴 호출이 많아질수록 모델 추론보다 “API/클라이언트 오버헤드”가 병목이 됩니다. WebSocket/비동기 루프 최적화가 실제로 큰 차이를 만듭니다. ([openai.com](https://openai.com/index/speeding-up-agentic-workflows-with-websockets/?utm_source=openai))  
- **비용**: 툴 정의/결과가 컨텍스트를 잠식합니다. tool gating, 결과 압축, 병렬 호출(필요 시)이 비용과 시간을 같이 줄입니다. ([zylos.ai](https://zylos.ai/research/2026-04-07-tool-use-function-calling-standards-benchmarks?utm_source=openai))  
- **안정성**: write tool은 특히 위험합니다. “승인 단계(human-in-the-loop)”를 넣거나, act 단계 툴을 별도 모델/별도 정책으로 분리하는 게 실무적으로 안전합니다.

---

## 🚀 마무리
2026년 5월 기준 “AI Agent의 function calling”은 기술적으로는 성숙 단계로 가고 있지만, 프로덕션 성공/실패를 가르는 건 여전히 **(1) tool gating (2) 검증/정책의 코드화 (3) 관측 가능성 (4) idempotency** 입니다. OpenAI는 Responses API를 중심으로 툴/에이전트/스트리밍을 통합하고 있고, Agents SDK 문서도 그 방향으로 정리되는 중입니다. ([openai.com](https://openai.com/index/new-tools-for-building-agents/?utm_source=openai))

**도입 판단 기준**
- “에이전트가 호출할 외부 작업”이 명확하고, 실패했을 때의 영향(특히 write)이 통제 가능한가?
- 툴 수가 50개를 넘어가기 시작한다면, tool gating/검색 기반 tool selection(또는 MCP 서버 분리)을 설계했는가?
- 트레이싱/감사 로그 없이도 운영할 수 있다고 생각한다면, 아직은 시기상조다.

**다음 학습 추천**
- OpenAI 공식: Function Calling/Responses API 가이드 + Agents SDK Tools/Tracing 문서 ([platform.openai.com](https://platform.openai.com/docs/guides/function-calling?api-mode=chat&utm_source=openai))
- “툴 호출 성능 최적화(비동기/소켓)” 관련 엔지니어링 글 ([openai.com](https://openai.com/index/speeding-up-agentic-workflows-with-websockets/?utm_source=openai))
- 보안 관점(프롬프트 인젝션/툴 악용)과 표준화(MCP) 동향 정리 ([zylos.ai](https://zylos.ai/research/2026-04-07-tool-use-function-calling-standards-benchmarks?utm_source=openai))

원하면, 위 예제를 **TypeScript(Node) 기반**으로 바꾸거나(실서비스에 더 흔함), “툴이 100개 이상인 조직”에서 쓰는 **Tool Search/Registry 설계(스키마 압축/동적 로딩/권한 스코핑)** 패턴까지 확장해서 이어서 정리해드릴게요.