---
title: "Next.js + Vercel AI SDK로 “프로덕션급 Fullstack AI 앱”을 만드는 2026년 7월식 설계도"
date: 2026-07-01 04:42:51 +0900
categories: [AI, Prototyping]
tags: [ai, prototyping, trend, 2026-07]
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
2026년의 “AI 앱”은 더 이상 **프롬프트 → 응답 문자열**로 끝나지 않습니다. 사용자는 *즉시 반응(Streaming)*, *도구 호출(Tool calling)*, *구조화된 결과(Structured output)*, *장시간 작업(브라우저 자동화/크롤링/문서 처리)*, *비용/관측(Observability)*까지 요구합니다. Next.js(App Router) + Vercel AI SDK 조합이 강한 이유는, 이 요구사항이 **Route Handler(서버) + React 클라이언트 훅(useChat) + Data Stream 프로토콜**로 자연스럽게 맞물리기 때문입니다. 특히 `streamText()`가 토큰을 즉시 흘려보내 UX를 크게 개선하는 패턴은 2026년 기준 사실상 표준이 됐습니다. ([sitepoint.com](https://www.sitepoint.com/nextjs-ai-streaming-building-realtime-apps-with-vercel-ai-sdk/?utm_source=openai))

**언제 쓰면 좋은가**
- 대화형/작업형 UI에서 **응답 지연이 곧 이탈로 이어지는** 제품(고객지원, IDE 보조, 리서치 도구)
- LLM이 **툴을 호출**하며 여러 step을 수행해야 하는 앱(검색, DB 조회, 브라우저 자동화, 워크플로우)
- 모델/벤더를 바꿀 가능성이 높아 **provider-agnostic**이 필요한 팀(AI Gateway 포함)

**언제 쓰면 안 되는가**
- LLM 호출이 거의 없고 “가끔 요약/생성” 정도라면: 굳이 스트리밍/툴 루프까지 도입하면 복잡도만 늘어납니다.
- 강한 규정/감사(온프레/폐쇄망) 환경에서 Vercel 런타임/게이트웨이를 못 쓰는 경우: AI SDK는 쓰되, 운영/키관리/관측을 자체 스택으로 대체할 설계가 필요합니다.
- **RSC 기반 Generative UI**를 최우선으로 보고 있다면: Vercel 쪽에서도 RSC 기반 AI SDK 라인이 “일시 중단(paused)”된 상태라, 안정적인 프로덕션 기준에선 Route Handler + Client UI 스트리밍이 현실적입니다. ([vercel.com](https://vercel.com/templates/next.js/rsc-genui?utm_source=openai))

---

## 🔧 핵심 개념
### 1) “Fullstack AI”에서의 데이터 흐름(중요)
핵심은 **클라이언트가 `/api/chat`에 메시지 배열을 POST**하고, 서버는 `streamText()` 결과를 **Data Stream 포맷**으로 흘려보내며, 클라이언트는 `useChat()`이 그 스트림을 파싱해 **메시지/툴 이벤트를 UI로 증분 반영**하는 구조입니다. ([sitepoint.com](https://www.sitepoint.com/nextjs-ai-streaming-building-realtime-apps-with-vercel-ai-sdk/?utm_source=openai))

- **Client (useChat)**  
  - 입력/메시지 상태 관리
  - 스트리밍 도중 토큰을 append
  - 툴 호출 파트(예: `tool-*` part)를 별도 렌더링 가능(진짜 “에이전트 UI”의 시작점)

- **Server (Route Handler)**  
  - 요청 검증(Zod 등)
  - 모델 호출(`streamText`)
  - 툴 정의 및 실행(서버에서만, 비밀키/DB/사내 API 접근)
  - 응답을 `toDataStreamResponse()` 같은 헬퍼로 **스트리밍 가능한 Response**로 변환

이때 `generateText()`는 “한 번에 받아서 반환”이라 TTFB/UX가 나빠지고, `streamText()`는 토큰이 생성되는 즉시 내려보내는 차이가 있습니다. ([sitepoint.com](https://www.sitepoint.com/nextjs-ai-streaming-building-realtime-apps-with-vercel-ai-sdk/?utm_source=openai))

### 2) Tool calling이 “서버 풀스택”을 강제하는 이유
툴은 본질적으로 **서버 리소스(DB, 파일, 네트워크, 브라우저, 사내망)**를 만집니다. 즉, 프론트만으로는 완성되지 않고 서버 런타임/권한/타임아웃/비용이 설계의 중심이 됩니다. Steel 예제처럼 Playwright/브라우저 자동화는 Edge에서 못 돌리고 Node runtime + 외부 패키지 번들링 전략까지 동반됩니다. ([docs.steel.dev](https://docs.steel.dev/cookbook/vercel-ai-sdk-nextjs?utm_source=openai))

### 3) Edge vs Node.js Runtime: 2026년의 “현실적인” 선택
예전엔 “Edge가 빠르다”가 정답처럼 들렸지만, Vercel 문서에서 **신규 Functions는 Node.js runtime 권장** 흐름이 명확해졌습니다(신뢰성/성능 이유). ([vercel.com](https://vercel.com/docs/functions/runtimes/edge?utm_source=openai))  
그리고 2026년 6월 기준, Node.js/Python Vercel Functions가 **최대 30분**까지 늘어나 장시간 AI 작업(긴 reasoning, 여러 툴 호출, 브라우저 자동화)에 훨씬 유리해졌습니다. ([vercel.com](https://vercel.com/changelog/vercel-functions-can-now-run-up-to-30-minutes?utm_source=openai))  
=> 결론: **짧은 저지연 스트리밍만** 필요하면 Edge, “진짜 에이전트/워크플로우”면 Node + `maxDuration`이 기본값이 됩니다.

### 4) AI Gateway: 모델 라우팅/비용/관측의 ‘운영 레이어’
Vercel AI Gateway는 “키 하나로 여러 모델 + 통합 관측/과금/폴백”을 제공하는 운영 레이어로 포지셔닝됩니다. ([vercel.com](https://vercel.com/ai-gateway?utm_source=openai))  
템플릿들도 **AI_GATEWAY_API_KEY**를 기본 전제로 가는 경우가 많습니다(특히 Vercel 외부 배포 시). ([examples.vercel.com](https://examples.vercel.com/templates/ai/chatbot?utm_source=openai))

---

## 💻 실전 코드
시나리오: **“지원 티켓 요약 + 계정 상태 조회 + (옵션) 내부 지식 검색”을 한 번의 대화로 처리**하는 풀스택 AI 채팅.  
요구사항:
- 스트리밍 응답(사용자 체감 속도)
- 툴 호출로 DB/사내 API 호출
- Node runtime(장시간/외부 SDK 대비), 타임아웃 명시
- 요청 검증(Zod)
- 운영 시 AI Gateway 사용 가능

### 0) 설치/환경 변수
```bash
pnpm add ai zod @ai-sdk/openai
# (선택) Vercel AI Gateway 쓸 거면 Vercel 대시보드에서 키 발급 후 env에 추가
# AI_GATEWAY_API_KEY=gw_xxx
# 또는 OpenAI 직접 호출이면 OPENAI_API_KEY=...
```

### 1) Route Handler: `app/api/chat/route.ts`
- Node runtime + 장시간 허용(`maxDuration`)
- 툴 2개 예시: `getAccountStatus`, `summarizeTicket`
- 스트리밍으로 텍스트/툴 이벤트를 함께 내려보냄

```typescript
import { z } from 'zod';
import { streamText } from 'ai';
import { openai } from '@ai-sdk/openai';

// 운영 관점: 장시간 tool loop/브라우저 자동화/사내 API가 붙을 수 있으니 Node로 고정
export const runtime = 'nodejs';
export const maxDuration = 300; // 필요 시 1800까지(플랜/설정에 따라) ([vercel.com](https://vercel.com/changelog/vercel-functions-can-now-run-up-to-30-minutes?utm_source=openai))

const MessageSchema = z.object({
  role: z.enum(['user', 'assistant']),
  content: z.string().min(1).max(8000),
});

const RequestSchema = z.object({
  messages: z.array(MessageSchema).min(1).max(60),
  // 멀티테넌시/권한 체크용 메타데이터(실무에서 중요)
  workspaceId: z.string().min(1),
  userId: z.string().min(1),
});

async function getAccountStatus(workspaceId: string, userId: string) {
  // TODO: 실제로는 DB/내부 API 호출
  // 예: await db.accounts.findFirst({ where: { workspaceId, userId } })
  return {
    plan: 'pro',
    seatsUsed: 7,
    seatsLimit: 10,
    delinquent: false,
  };
}

async function summarizeTicket(ticketId: string) {
  // TODO: 실제로는 티켓 본문/댓글/로그를 읽어 요약
  return {
    ticketId,
    summary: '결제 실패는 3DS 인증 단계에서 리다이렉트가 누락되어 발생. 콜백 URL 설정 확인 필요.',
    severity: 'high' as const,
    suggestedNext: ['콜백 URL 화이트리스트 확인', '3DS 테스트 카드로 재현', '로그에 request_id 추가'],
  };
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const parsed = RequestSchema.safeParse(body);
  if (!parsed.success) return new Response('Invalid request', { status: 400 });

  const { messages, workspaceId, userId } = parsed.data;

  const result = streamText({
    model: openai('gpt-5.5-mini'), // 예시. 조직 표준 모델로 교체
    system: [
      'You are a senior support engineer assistant.',
      'Always call tools when you need authoritative workspace/account/ticket data.',
      'When you return an action plan, format it as bullet points.',
    ].join('\n'),
    messages,
    tools: {
      getAccountStatus: {
        description: 'Get current account plan and seat usage for the user.',
        parameters: z.object({}),
        execute: async () => getAccountStatus(workspaceId, userId),
      },
      summarizeTicket: {
        description: 'Summarize a support ticket by ticketId.',
        parameters: z.object({
          ticketId: z.string().min(3),
        }),
        execute: async ({ ticketId }) => summarizeTicket(ticketId),
      },
    },
    // 실무 팁: 무한 tool loop 방지(에이전트 안정성)
    // stopWhen: stepCountIs(10) 같은 패턴을 많이 씀 ([docs.steel.dev](https://docs.steel.dev/cookbook/vercel-ai-sdk-nextjs?utm_source=openai))
  });

  // AI SDK 권장 패턴: Data Stream Response로 반환 (useChat과 호환)
  return result.toDataStreamResponse();
}
```

**예상 동작**
- 사용자가 “티켓 TCK-193 요약하고, 우리 계정 상태 기반으로 대응 플랜 줘”라고 입력
- 모델이 `summarizeTicket` → `getAccountStatus`를 호출
- 클라이언트는 스트림 중간중간:
  - 텍스트 토큰(요약 문장)
  - tool 결과(요약 JSON / 계정 상태 JSON)
  - 최종 액션 플랜
을 순차 렌더링

### 2) Client UI: `app/page.tsx` (핵심만)
- `useChat()`로 스트리밍 수신
- tool 호출 파트를 “UI 카드”로 분리 렌더링(실무에서 체감 품질이 크게 상승)

```typescript
'use client';

import { useChat } from 'ai/react';

export default function Page() {
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: '/api/chat',
    body: {
      workspaceId: 'ws_123',
      userId: 'user_456',
    },
  });

  return (
    <div style={{ maxWidth: 900, margin: '24px auto', fontFamily: 'system-ui' }}>
      <h1 style={{ fontSize: 18, marginBottom: 12 }}>Support Copilot</h1>

      <div style={{ border: '1px solid #ddd', borderRadius: 12, padding: 16, minHeight: 420 }}>
        {messages.map(m => (
          <div key={m.id} style={{ marginBottom: 12 }}>
            <div style={{ opacity: 0.7, fontSize: 12 }}>{m.role}</div>

            {/* 기본 텍스트 */}
            <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>

            {/* 고급: tool 결과를 별도 렌더링하고 싶다면,
               UIMessage의 parts(데이터 파트) 렌더링 패턴을 적용.
               (SDK 버전에 따라 메시지 구조가 다를 수 있으니 템플릿/문서 기반으로 맞추는 게 안전) */}
          </div>
        ))}

        {isLoading && <div style={{ opacity: 0.6 }}>streaming…</div>}
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <input
          value={input}
          onChange={handleInputChange}
          placeholder="예) 티켓 TCK-193 요약하고 대응 플랜 만들어줘"
          style={{ flex: 1, padding: 12, borderRadius: 10, border: '1px solid #ddd' }}
        />
        <button type="submit" style={{ padding: '12px 14px' }}>Send</button>
      </form>
    </div>
  );
}
```

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 적용 가능)
1) **Route Handler를 “AI Boundary”로 두고, 요청 검증/권한을 강제**
- 실무에서는 `workspaceId`, `userId`, `conversationId` 같은 컨텍스트가 없으면 툴이 오염됩니다.
- Zod로 입력을 조여서 “프롬프트 인젝션 → 툴 오남용”을 1차로 줄이세요. ([sitepoint.com](https://www.sitepoint.com/nextjs-ai-streaming-building-realtime-apps-with-vercel-ai-sdk/?utm_source=openai))

2) **Edge 우선이 아니라 “툴/의존성/시간” 기준으로 런타임 결정**
- Edge는 제약이 많고(동적 코드 실행 등) Vercel도 신규는 Node 권장 흐름입니다. ([vercel.com](https://vercel.com/docs/functions/runtimes/edge?utm_source=openai))  
- 브라우저 자동화/무거운 SDK는 Node + `serverExternalPackages` 같은 번들링 전략이 필요합니다. ([docs.steel.dev](https://docs.steel.dev/cookbook/vercel-ai-sdk-nextjs?utm_source=openai))

3) **장시간 AI 작업은 `maxDuration`을 명시하고, “단계 제한”을 둔다**
- Vercel Functions가 30분까지 가능해졌다고 해서 무제한 루프를 허용하면 비용/장애가 납니다. ([vercel.com](https://vercel.com/changelog/vercel-functions-can-now-run-up-to-30-minutes?utm_source=openai))  
- step 제한(`stepCountIs`)은 에이전트 안정성의 보험입니다. ([docs.steel.dev](https://docs.steel.dev/cookbook/vercel-ai-sdk-nextjs?utm_source=openai))

### 흔한 함정/안티패턴
- **“그냥 Server Actions로 AI 호출하면 되겠지?”**
  - 단순 mutation이면 가능하지만, 스트리밍/외부 클라이언트(모바일/파트너)까지 고려하면 Route Handler가 더 예측 가능합니다(공개 API 형태). 스트리밍은 특히 Route Handler가 구현/디버깅이 수월합니다. ([reddit.com](https://www.reddit.com/r/nextjs/comments/1sc94a9/best_practice_for_streaming_ai_responses_in/?utm_source=openai))
- **RSC 기반 Generative UI에 올인**
  - 데모는 매력적이지만, 현재는 “개발 일시 중단” 공지가 있어 제품 핵심 플로우로 두기엔 리스크가 큽니다. ([vercel.com](https://vercel.com/templates/next.js/rsc-genui?utm_source=openai))
- **스트리밍이 로컬에서는 되는데 프로덕션에서 한 번에 몰아서 도착**
  - 프록시/로드밸런서/런타임 설정에 따라 버퍼링이 생깁니다. (특히 셀프호스팅 + nginx 조합에서 자주 발생)

### 비용/성능/안정성 트레이드오프(결정 기준)
- **Streaming은 UX를 올리지만**: 토큰이 길어질수록 비용이 선형 증가. “요약 먼저 → 추가 요청 시 확장” 같은 UX가 비용을 줄입니다.
- **AI Gateway는 운영 편의/관측을 올리지만**: 게이트웨이 의존이 생깁니다. 다만 “모델 라우팅/폴백/예산 제한”을 직접 구현하는 비용이 더 큰 경우가 많습니다. ([vercel.com](https://vercel.com/ai-gateway?utm_source=openai))
- **Node runtime은 유연하지만**: cold start/번들 사이즈/의존성 관리가 숙제가 됩니다(특히 Playwright류). Edge는 가볍지만 제약이 강합니다. ([vercel.com](https://vercel.com/kb/guide/library-sdk-compatible-with-vercel-edge-runtime-and-functions?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 7월의 Next.js + Vercel AI SDK 풀스택 AI 앱은 다음 3가지를 “기본값”으로 가져가면 실패 확률이 크게 줄어듭니다.

1) **Route Handler + `streamText()` + `useChat()`**로 스트리밍 아키텍처를 고정 ([sitepoint.com](https://www.sitepoint.com/nextjs-ai-streaming-building-realtime-apps-with-vercel-ai-sdk/?utm_source=openai))  
2) 툴 호출은 “서버 권한/검증/단계 제한”을 포함한 **운영 가능한 에이전트 루프**로 설계 ([docs.steel.dev](https://docs.steel.dev/cookbook/vercel-ai-sdk-nextjs?utm_source=openai))  
3) 런타임은 Edge 집착 대신 **Node + `maxDuration`**로 장시간/복잡 툴을 수용(특히 2026-06-15 이후 30분 옵션이 생기며 실전성이 커짐) ([vercel.com](https://vercel.com/changelog/vercel-functions-can-now-run-up-to-30-minutes?utm_source=openai))  

**도입 판단 기준**
- “우리 앱이 *대화 UI*가 아니라 *작업 실행 UI*로 진화할 가능성이 있는가?” → Yes면 AI SDK 툴/스트리밍은 투자 가치가 큼
- “모델/벤더 교체, 비용 통제, 장애 폴백이 중요해질 것 같은가?” → Yes면 AI Gateway까지 포함한 설계 고려 ([vercel.com](https://vercel.com/ai-gateway?utm_source=openai))
- “브라우저 자동화/문서 처리 등 장시간 작업이 있는가?” → Yes면 Node runtime + `maxDuration` 전제 ([vercel.com](https://vercel.com/changelog/vercel-functions-can-now-run-up-to-30-minutes?utm_source=openai))

다음 학습 추천은 두 갈래입니다:  
(1) **AI SDK v6 기준의 structured output(Output.object)/툴 파트 렌더링 패턴**을 팀 코드 컨벤션으로 굳히기 ([vercel-docs.vercel.sh](https://vercel-docs.vercel.sh/academy/ai-sdk?utm_source=openai))  
(2) “우리 서비스의 툴 카탈로그(권한/감사/레이트리밋 포함)”를 설계 문서로 먼저 만들고, 그 다음에 UI를 붙이기—이 순서가 풀스택 AI 앱을 가장 빨리 ‘제품’으로 만듭니다.