---
title: "컨텍스트 윈도우를 넘어서: 2026년형 AI Agent 장·단기 메모리와 Long-term 상태 관리 구현 패턴"
date: 2026-05-06 03:52:47 +0900
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
프로덕션 AI Agent를 붙이다 보면 “모델 성능”보다 더 빨리 한계가 오는 지점이 **state(상태)** 입니다. 세션이 바뀌면 사용자의 선호/업무 맥락을 잊고, 도구 실행 중간에 죽으면 재시도 전략이 없고, 멀티스텝 워크플로우가 길어질수록 “무엇을 알고/했고/해야 하는지”가 붕괴합니다. 결국 **Memory = UX**이자 **State = 안정성/비용** 문제로 수렴합니다. (최근 커뮤니티에서도 “메모리 지속성과 비용 제어는 같은 문제”라는 관찰이 반복됩니다. ([reddit.com](https://www.reddit.com/r/LangChain/comments/1rs07c6/how_are_you_handling_memory_persistence_across/)))

**언제 쓰면 좋은가**
- 사용자별 개인화(선호/규칙/금지사항)가 누적될수록 가치가 커지는 제품
- 멀티스텝 툴 실행(ETL, 티켓 처리, 코드 변경, 리서치→작성 파이프라인)처럼 “중간 상태”가 중요한 에이전트
- 장애/재시작/스케일아웃이 일상인 환경(컨테이너 재배치, 서버리스, 워커 풀)

**언제 쓰면 안 되는가**
- 단발성 Q&A, “한 번 답하고 끝”인 기능(메모리 유지가 오히려 개인정보/규정 리스크)
- 요구사항이 불명확한 초기 단계에서 “일단 다 저장”하는 접근(중복/오염/삭제 요구 대응 불가)
- 강한 정합성이 필요한 트랜잭션(결제/송금 등)을 “에이전트 내부 state”에 의존하려는 설계(외부 시스템이 source of truth여야 함)

---

## 🔧 핵심 개념
### 1) 용어를 먼저 분리: STM / LTM / State
2026년 실전에서는 메모리를 **3계층**으로 나누는 게 가장 사고가 적습니다.

- **STM (Short-term / working memory)**: “지금 실행 중인 스텝”에 필요한 최근 대화/툴 결과. 보통 context window에 직접 로드.
- **LTM (Long-term memory)**: 세션을 넘어 유지되는 사용자 선호, 사실, 에피소드, 지식. RAG/Vector/Graph/문서 저장 등으로 보관.
- **State (durable execution state)**: “이 워크플로우가 어디까지 실행됐는지”, “어떤 tool call이 완료/실패했는지”, “다음 재시도는 무엇인지” 같은 **재개(resume)** 가능한 실행 상태.

여기서 중요한 포인트: **LTM은 ‘기억(knowledge)’이고, State는 ‘진행 상황(checkpoint)’**입니다. 이 둘을 섞으면 “잘못된 기억을 영구 저장”하거나 “실행 상태를 검색으로 복구”하는 지옥이 열립니다.

### 2) 2026년 트렌드: “Checkpoint + Rehydration”이 기본값
OpenAI Agents SDK는 메모리 주입(요약 파일)과 함께, **snapshotting/rehydration(스냅샷/재수화)**로 실패 후 같은 상태에서 이어가기 패턴을 전면에 둡니다. 즉, 에이전트를 “프로세스”가 아니라 “복구 가능한 실행체”로 다룹니다. ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk))

LangGraph 쪽도 동일한 방향인데, 그래프 각 스텝마다 state를 **checkpointer**로 저장해 thread 단위로 지속화할 수 있게 합니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/persistence))

정리하면 2026년형 표준 흐름은 아래입니다.

1) 요청 들어옴 → `thread_id/run_id` 부여  
2) 그래프/에이전트가 스텝 실행  
3) **각 스텝 종료 시점에 state checkpoint 저장** (재실행/재개를 위해)  
4) 필요 시 LTM에 “추출된 사실/선호/요약”을 별도로 기록(비동기 가능)  
5) 다음 요청에서 STM은 최근 대화 + “필요한 메모리만” 로드(전체 덤프 금지)

### 3) 접근 방식 차이: RAG만으로는 “상태”를 못 푼다
Make(자동화 플랫폼)에서도 지적하듯 RAG를 “메모리”로 쓰는 건 정적 지식에는 유효하지만, “빠르게 변하는 고객 상태”에는 freshness/인덱싱 문제가 생깁니다. ([make.com](https://www.make.com/en/blog/agent-workflow-memory))  
즉,
- “회사 휴가 정책” → RAG ok  
- “이 고객은 오늘 오전에 환불 요청했고, 내가 2단계까지 처리했음” → **State/ledger**가 필요

또한 Zep은 “최근 몇 메시지는 raw short-term, 장기 컨텍스트는 별도 파이프라인으로 생성되며 ingestion 지연이 있을 수 있다”고 명시합니다. 이 말은 곧, **LTM은 즉시 일관성을 보장하기 어렵고**, 그래서 실행 안전성은 checkpoint/state로 해결해야 한다는 뜻입니다. ([help.getzep.com](https://help.getzep.com/v2/memory))

---

## 💻 실전 코드
아래 예제는 “지원 티켓 처리 에이전트” 시나리오입니다.

- 사용자는 여러 날에 걸쳐 티켓을 업데이트
- 에이전트는 (1) 티켓 요약 (2) 정책 조회 (3) 답변 초안 생성 (4) CRM 업데이트 를 수행
- 중간에 장애가 나도 **마지막 스텝부터 재개**
- 사용자 선호(말투, 민감정보 처리 규칙 등)는 **LTM(Notes)로 축적**하고, 매 런에 “요약” 형태로 주입

> 구현 선택: OpenAI Agents SDK의 메모리 세션 개념(메모리 요약/주입) ([openai.github.io](https://openai.github.io/openai-agents-js/guides/sandbox-agents/memory)) + 별도 DB에 “durable state(ledger)”를 저장하는 패턴  
> (왜 별도 DB냐? LTM은 비동기/압축/중복제거를 하기 때문에 “정확한 진행 상태” 저장소로 부적합)

### 1) 초기 셋업 (의존성/DB)
```bash
npm init -y
npm i @openai/agents better-sqlite3 zod
```

```ts
// db.ts
import Database from "better-sqlite3";

export const db = new Database("agent_state.sqlite");

db.exec(`
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  status TEXT NOT NULL,           -- running|done|failed
  step TEXT NOT NULL,             -- classify|policy|draft|crm
  state_json TEXT NOT NULL,       -- durable state snapshot
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_facts (
  user_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, key)
);
`);
```

### 2) 기본 동작: “체크포인트 기반 재개 + 메모리 요약 주입”
```ts
// agent.ts
import { z } from "zod";
import { db } from "./db";
import { MemorySession, run } from "@openai/agents";

const TicketInput = z.object({
  userId: z.string(),
  threadId: z.string(),
  runId: z.string(),
  ticketId: z.string(),
  message: z.string(),
});

type DurableState = {
  ticketId: string;
  lastUserMessage: string;
  classification?: { priority: "low" | "med" | "high"; topic: string };
  policySnippets?: string[];
  draftReply?: string;
  crmUpdated?: boolean;
};

function loadRun(runId: string): { step: string; state: DurableState } | null {
  const row = db.prepare("SELECT step, state_json FROM runs WHERE run_id=?").get(runId) as any;
  if (!row) return null;
  return { step: row.step, state: JSON.parse(row.state_json) };
}

function saveRun(params: {
  runId: string; userId: string; threadId: string;
  status: string; step: string; state: DurableState;
}) {
  db.prepare(`
    INSERT INTO runs(run_id,user_id,thread_id,status,step,state_json,updated_at)
    VALUES (@runId,@userId,@threadId,@status,@step,@stateJson,@updatedAt)
    ON CONFLICT(run_id) DO UPDATE SET
      status=excluded.status,
      step=excluded.step,
      state_json=excluded.state_json,
      updated_at=excluded.updated_at
  `).run({
    ...params,
    stateJson: JSON.stringify(params.state),
    updatedAt: Date.now(),
  });
}

// LTM(선호/규칙)을 "사실" 형태로 최소 스키마로 저장
function upsertMemoryFact(userId: string, key: string, value: string) {
  db.prepare(`
    INSERT INTO memory_facts(user_id,key,value,updated_at)
    VALUES (?,?,?,?)
    ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
  `).run(userId, key, value, Date.now());
}

function loadMemorySummary(userId: string): string {
  const rows = db.prepare("SELECT key,value FROM memory_facts WHERE user_id=?").all(userId) as any[];
  if (!rows.length) return "No persisted user preferences yet.";
  // “전부 로드”가 아니라 요약 형태로만 주입 (토큰 비용/오염 방지)
  return rows.map(r => `- ${r.key}: ${r.value}`).join("\n");
}

async function stepClassify(state: DurableState): Promise<DurableState> {
  // 실제로는 모델 호출 + 스키마 검증을 권장
  const priority = state.lastUserMessage.includes("긴급") ? "high" : "med";
  return { ...state, classification: { priority, topic: "refund" } };
}

async function stepPolicy(state: DurableState): Promise<DurableState> {
  // 정책은 RAG로 가져오되, state에는 "근거 스니펫"만 저장 (원문 전체 저장 금지)
  const snippets = [
    "Refunds allowed within 14 days if unused.",
    "Escalate to human if chargeback mentioned."
  ];
  return { ...state, policySnippets: snippets };
}

async function stepDraft(state: DurableState, memorySummary: string): Promise<DurableState> {
  // 여기서 OpenAI Agents SDK를 사용해 초안을 생성한다고 가정
  const session = new MemorySession({
    // SDK가 런 시작 시 memory_summary.md 형태로 주입하는 패턴을 제공 ([openai.github.io](https://openai.github.io/openai-agents-js/guides/sandbox-agents/memory))
    // 실제 옵션/필드는 SDK 버전에 맞춰 조정
  } as any);

  const prompt = `
You are a support agent.
User memory summary:
${memorySummary}

Ticket: ${state.ticketId}
User message: ${state.lastUserMessage}
Policy snippets:
${(state.policySnippets ?? []).map(s => `- ${s}`).join("\n")}

Write a concise reply draft in Korean, polite but direct.
`;
  const result = await run({
    agent: {
      name: "support-drafter",
      instructions: prompt,
    } as any,
    session,
  });

  const draft = (result as any).output_text ?? "초안 생성 실패";
  return { ...state, draftReply: draft };
}

async function stepCrm(state: DurableState): Promise<DurableState> {
  // 외부 CRM 업데이트는 idempotency key가 필수(여기서는 생략)
  return { ...state, crmUpdated: true };
}

export async function handleTicket(raw: unknown) {
  const input = TicketInput.parse(raw);

  // 0) 재개 지점 로드
  const loaded = loadRun(input.runId);
  let step = loaded?.step ?? "classify";
  let state: DurableState = loaded?.state ?? {
    ticketId: input.ticketId,
    lastUserMessage: input.message,
  };

  // 1) LTM 요약 로드(“필요한 만큼만”)
  const memorySummary = loadMemorySummary(input.userId);

  // 2) 실행 + 각 스텝마다 durable checkpoint 저장
  saveRun({ runId: input.runId, userId: input.userId, threadId: input.threadId, status: "running", step, state });

  try {
    if (step === "classify") {
      state = await stepClassify(state);
      step = "policy";
      saveRun({ runId: input.runId, userId: input.userId, threadId: input.threadId, status: "running", step, state });
    }

    if (step === "policy") {
      state = await stepPolicy(state);
      step = "draft";
      saveRun({ runId: input.runId, userId: input.userId, threadId: input.threadId, status: "running", step, state });
    }

    if (step === "draft") {
      state = await stepDraft(state, memorySummary);
      step = "crm";
      saveRun({ runId: input.runId, userId: input.userId, threadId: input.threadId, status: "running", step, state });
    }

    if (step === "crm") {
      state = await stepCrm(state);
      step = "done";
      saveRun({ runId: input.runId, userId: input.userId, threadId: input.threadId, status: "done", step, state });
    }

    // 3) LTM 업데이트(동기/비동기 선택)
    // 예: 말투 선호를 감지했다면 key-value로 덮어쓰기(“facts overwrite on change” 패턴)
    if (input.message.includes("존댓말로")) {
      upsertMemoryFact(input.userId, "tone", "use polite Korean (존댓말)");
    }

    return { ok: true, step, state };
  } catch (e: any) {
    saveRun({ runId: input.runId, userId: input.userId, threadId: input.threadId, status: "failed", step, state });
    throw e;
  }
}
```

**예상 출력(예시)**  
- 첫 실행: `classify → policy → draft → crm → done`으로 진행, 중간마다 DB에 checkpoint 저장  
- 프로세스가 `draft` 직후 죽어도 다음 실행에서 `step=crm`부터 재개(“이미 만든 draft를 다시 만들지 않음”)

### 3) 확장: “장기 메모리”를 저장할 때의 최소 규칙
여기서 LTM을 무작정 conversation log로 저장하지 않고, **추출된 사실/선호/규칙만 구조화**해서 넣었습니다. 이게 2026년 실전에서 중요한 이유는:
- 중복/충돌이 줄고(“같은 사실을 30번 다른 문장으로 저장” 문제) ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1sva2ww/which_platforms_offer_the_easiest_way_to_manage/))
- 삭제/정정이 가능하고(키 단위 overwrite)
- 토큰 비용이 예측 가능해집니다

더 고급으로 가면 Zep처럼 “장기 컨텍스트 문자열 + 최근 raw 메시지”를 분리하는 구조를 쓰거나 ([help.getzep.com](https://help.getzep.com/v2/memory)), Mem0처럼 “압축 엔진으로 토큰을 줄이는” 서비스를 붙이는 선택지도 있습니다. ([mem0docs.xyz](https://mem0docs.xyz/))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **State(재개)와 LTM(지식)을 물리적으로 분리**
- State는 트랜잭션/정합성/재시도에 최적화(SQLite/Postgres/Redis).
- LTM은 압축/검색/정책(보존/삭제)에 최적화(Vector/Graph/문서/전용 메모리 레이어).
- LangGraph의 checkpointer가 “그래프 실행 상태”를 저장하는 이유도 이 분리에 있습니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/persistence))

2) **메모리 로딩은 ‘전부 주입’이 아니라 ‘요약 + 선택적 retrieval’**
- 커뮤니티 사례처럼 “관련 없는 메모리를 매번 로드하면 토큰 비용 폭발”합니다. ([reddit.com](https://www.reddit.com/r/LangChain/comments/1rs07c6/how_are_you_handling_memory_persistence_across/))
- 기본은 `memory_summary`(짧고 안정적인 규칙/선호) + 필요 시 tool로 검색(semantic/graph).

3) **LTM 쓰기는 비동기(또는 배치)로, 대신 State는 동기**
- Zep도 ingestion 지연이 있을 수 있음을 문서화합니다. ([help.getzep.com](https://help.getzep.com/v2/memory))  
- 즉시 반영이 필요한 건 State에 기록하고, LTM은 “나중에 반영돼도 되는 지식”만.

### 흔한 함정/안티패턴
- **Anti-pattern: RAG를 “고객 상태 DB”처럼 사용**
  - RAG 인덱스는 업데이트/삭제/정정이 까다롭고, freshness 관리가 어렵습니다. ([make.com](https://www.make.com/en/blog/agent-workflow-memory))
- **Anti-pattern: conversation 전체를 영구 저장하고 매번 다 넣기**
  - 비용 증가 + 개인정보 리스크 + 모델이 과거의 잘못된 추론을 “사실”로 굳히는 오염.
- **Anti-pattern: 멀티 에이전트가 같은 LTM을 경쟁적으로 업데이트**
  - “누가 최종 진실을 결정하나?”가 없으면 메모리 충돌이 누적됩니다(특히 팀/멀티-agent). ([reddit.com](https://www.reddit.com/r/AIMemory/comments/1r1tw1v/semantic_memory_was_built_for_users_but_what/))

### 비용/성능/안정성 트레이드오프
- **DB 1개로 끝내고 싶다**: 작은 규모면 SQLite로도 충분(상태/핵심 facts) + 필요해질 때만 vector/graph 추가.
- **낮은 지연**: hot state는 Redis/SQLite, LTM retrieval은 캐시/배치/비동기.
- **높은 안정성**: checkpoint 주기를 촘촘히 할수록 안전하지만 쓰기 비용 증가 → “스텝 종료 시점” 또는 “외부 side-effect 직전/직후”만 저장하는 전략이 현실적.

---

## 🚀 마무리
2026년 5월 기준으로, “기억하는 에이전트”를 만드는 핵심은 멋진 벡터DB가 아니라:

- **Durable State(체크포인트)로 실행을 복구 가능하게 만들고**
- **LTM은 압축/요약/검색 가능한 지식 레이어로 분리하며**
- **매 런에 주입되는 컨텍스트는 ‘요약 + 선택적 retrieval’로 비용을 통제**하는 것입니다.

도입 판단 기준은 간단합니다.
- “중간에 죽어도 이어가야 한다” → 먼저 **checkpoint/state**부터
- “사용자별 선호가 반복해서 등장한다” → **key-value facts + 요약 주입**
- “대화/지식이 길어져 검색이 필요하다” → 그때 **vector/graph/Zep/Mem0류**를 붙이기 ([help.getzep.com](https://help.getzep.com/v2/memory))

다음 학습 추천:
- LangGraph의 persistence/checkpointer 개념을 먼저 익히고(워크플로우 재개) ([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/persistence))  
- 그 다음 OpenAI Agents SDK의 memory 주입/rehydration 흐름을 보고(런타임 복구) ([openai.com](https://openai.com/index/the-next-evolution-of-the-agents-sdk))  
- 마지막으로 Mem0/Zep/Letta 같은 “LTM 제품/런타임”을 비교하며, 내 제품에 필요한 메모리 타입(선호/사실/에피소드/스킬)을 어디에 둘지 결정하는 순서가 가장 실패 확률이 낮습니다. ([help.getzep.com](https://help.getzep.com/v2/memory))