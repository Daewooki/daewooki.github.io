---
title: "2026년 6월 기준: Next.js + Vercel AI SDK로 “진짜” Fullstack AI 앱을 만드는 법 (스트리밍/툴콜/운영 함정까지)"
date: 2026-06-01 05:02:43 +0900
categories: [AI, Prototyping]
tags: [ai, prototyping, trend, 2026-06]
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
Next.js로 AI 기능을 붙이는 건 이제 “챗 UI + API 한 개”로 끝나는 문제가 아닙니다. 실서비스에 들어가면 곧바로 아래가 터집니다.

- **스트리밍 응답**(UX)과 **서버 실행 제한**(timeout, runtime) 사이의 충돌  
- Tool calling이 들어가는 순간 생기는 **멀티스텝 오케스트레이션**, 그리고 “툴 출력이 그대로 프론트에 노출되는” 문제
- 대화/작업 로그, 피드백(👍/👎), 관측(telemetry)까지 포함한 **운영 가능성**

2026년 6월 시점에서 Next.js + Vercel AI SDK 기반 fullstack AI 앱을 추천하는 경우는:
- **LLM 응답이 사용자 경험의 핵심**이고, **토큰 단위 스트리밍**이 필요하다
- Provider(OpenAI/Anthropic/Google 등)를 바꿀 가능성이 높아 **추상화 계층**이 필요하다
- Next.js App Router에서 **Route Handler 중심**으로 “프론트+백”을 빠르게 합치고 싶다

반대로 “지금은” 피하는 게 좋은 경우:
- **수십 초~수분** 걸리는 이미지/비디오 생성/대규모 배치/에이전트 워크플로가 핵심인 제품  
  → Vercel Function timeout, 재시도/큐/워크플로 관리까지 요구되면 **별도 백엔드(큐/워커)** 로 분리하는 편이 낫습니다(커뮤니티에서도 같은 이유로 분리 사례가 많음). ([reddit.com](https://www.reddit.com/r/micro_saas/comments/1t77nel/spent_today_migrating_our_backend_away_from/?utm_source=openai))
- Tool calling 결과에 **민감정보**가 포함될 가능성이 높은데, 이를 안전하게 마스킹/저장/감사까지 해야 한다  
  → SDK를 쓰되 “기본 스트림”을 그대로 노출하지 말고 **서버에서 메시지 파이프라인을 강하게 통제**해야 합니다. ([community.vercel.com](https://community.vercel.com/t/hiding-tool-call-results-from-streamtext-in-ai-sdk/35687?utm_source=openai))

---

## 🔧 핵심 개념
### 1) Vercel AI SDK의 ‘Core’와 ‘UI’가 분리돼 있다
2026년 초 문서 기준 AI SDK는 “provider-agnostic TypeScript toolkit”이고, **모델 호출(Core)** 과 **UI 스트리밍 프로토콜(UI)** 을 분리해서 봐야 합니다. ([vercel.com](https://vercel.com/docs/ai-sdk?utm_source=openai))

- **Core**: `generateText`, `streamText`, `generateObject`, `streamObject`, tools/tool calling 등  
- **UI**: `useChat` 같은 hook이 이해하는 **스트림 포맷(protocol)**, 메시지 구조(UIMessage) 등

여기서 실무적으로 중요한 결론:
- 서버에서 단순히 `ReadableStream`을 흘려보내는 것과, `useChat`이 기대하는 **Data Stream**을 흘려보내는 것은 다릅니다.  
- 그래서 2026년 기준 “안전한 기본값”은 Route Handler에서 **`result.toDataStreamResponse()`** 같은 헬퍼를 쓰는 패턴입니다(가이드/예제에서도 이 흐름을 사용). ([vercel.com](https://vercel.com/guides/fine-tuning-openai-nextjs?utm_source=openai))

### 2) Next.js App Router에서의 정석 배치는 “Route Handler”
Server Actions는 데이터 mutation에 좋지만, **긴 스트리밍/장시간 처리**와 결합할 때 운영 제약이 많아집니다. 커뮤니티에서도 “스트리밍이면 Route Handler가 예측 가능하다”는 의견이 반복됩니다. ([reddit.com](https://www.reddit.com/r/nextjs/comments/1sc94a9/best_practice_for_streaming_ai_responses_in/?utm_source=openai))  
Next.js 공식 문서도 Route Handler의 **Streaming** 섹션에서 AI 스트리밍을 대표 사례로 언급합니다. ([nextjs.org](https://nextjs.org/docs/14/app/building-your-application/routing/route-handlers?utm_source=openai))

구조적으로는 이렇게 흘러갑니다.

1) Client: `useChat()` → `/api/chat`로 POST  
2) Server(Route Handler): `streamText({ model, messages, tools, stopWhen ... })`  
3) Server: SDK가 만든 스트림을 **Data Stream 프로토콜**로 변환해 Response로 반환  
4) Client: SDK hook이 stream chunk를 파싱해 UI state(messages)에 반영

### 3) Tool calling의 “멀티스텝”은 `stopWhen`이 관건
tools를 주면 모델이 “툴 호출”을 출력할 수 있는데, 기본 동작은 **툴 호출로 한 번 끝**입니다. “툴 실행 결과를 반영해서 최종 답변까지” 가려면 멀티스텝이 필요하고, AI SDK는 `stopWhen`으로 이를 제어합니다. ([ai-sdk.dev](https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling?utm_source=openai))

핵심 포인트:
- `stopWhen`을 켜면: 모델이 tool call → 서버가 tool execute → 결과를 포함해 다음 generation …  
- 멀티스텝은 편하지만, **round-trip이 늘어** 지연/비용이 증가합니다(툴 3개면 3번 모델 호출이 될 수 있음). 이 문제의식도 커뮤니티에서 자주 언급됩니다. ([reddit.com](https://www.reddit.com/r/vercel/comments/1rsd3yd/built_a_dropin_ai_sdk_integration_that_makes_tool/?utm_source=openai))

### 4) “툴 출력 노출”은 기본값을 믿지 말고 서버에서 필터링
툴 결과를 프론트에 보여주면 안 되는 경우(내부 API 응답, PII 등)가 흔합니다. Vercel Community에서는 `onFinish`에서 `responseMessage.parts`를 수정해 tool output을 마스킹하는 식의 접근을 제안합니다. ([community.vercel.com](https://community.vercel.com/t/hiding-tool-call-results-from-streamtext-in-ai-sdk/35687?utm_source=openai))  
즉, **스트림은 UI 편의**고, **보안/거버넌스는 서버 책임**입니다.

---

## 💻 실전 코드
현실적인 시나리오: “리포지토리/문서 검색(사내) + 변경 제안 생성” 보조 봇  
- 사용자 입력: “이 기능을 추가하려면 어디를 수정해야 해?”  
- 서버는 tool로 내부 문서(또는 DB)에서 관련 스니펫을 가져오고, 모델이 이를 요약/제안  
- **스트리밍 + tool calling + 멀티스텝 + 툴 출력 마스킹 + 로그 저장**까지 한 번에 구성

### 0) 설치/환경
```bash
pnpm create next-app@latest ai-fullstack --ts --app
cd ai-fullstack

pnpm add ai @ai-sdk/openai zod
# DB는 예시로 생략(Prisma/Drizzle 아무거나). 여기서는 "저장 훅"만 함수로 둠.

# .env.local
# OPENAI_API_KEY=...
```

### 1) 서버: Route Handler (App Router) — 스트리밍 + tools + stopWhen + 툴 출력 마스킹
```typescript
// app/api/chat/route.ts
import { streamText, tool, stepCountIs, type UIMessage } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';

export const dynamic = 'force-dynamic'; // Next.js Route Handler 캐싱 회피 ([nextjs.org](https://nextjs.org/docs/14/app/building-your-application/routing/route-handlers?utm_source=openai))
// export const runtime = 'edge' | 'nodejs' 는 워크로드에 맞게.
// (긴 작업/라이브러리 호환성 필요하면 nodejs 고려)

async function saveChatTurn(input: {
  userId: string;
  messages: UIMessage[];
}) {
  // TODO: Prisma/Drizzle로 저장
}

const fetchInternalDocs = tool({
  description: 'Search internal docs by keyword and return top relevant snippets.',
  inputSchema: z.object({
    query: z.string().min(2),
    limit: z.number().int().min(1).max(5).default(3),
  }),
  execute: async ({ query, limit }) => {
    // 실무에서는: vector DB / full-text search / GitHub code search 등을 연결
    // 여기서는 예시 데이터
    const corpus = [
      {
        path: 'docs/architecture.md',
        snippet:
          'Our Next.js app uses Route Handlers for streaming responses and stores chat logs in Postgres.',
      },
      {
        path: 'packages/api/src/rate-limit.ts',
        snippet:
          'Rate limiting is enforced per userId using a sliding window stored in Redis.',
      },
      {
        path: 'apps/web/app/api/chat/route.ts',
        snippet:
          'Use streamText + tools + stopWhen to implement multi-step tool calling.',
      },
    ];

    const hits = corpus
      .filter((x) => (x.path + ' ' + x.snippet).toLowerCase().includes(query.toLowerCase()))
      .slice(0, limit);

    return { hits };
  },
});

export async function POST(req: Request) {
  const { userId, messages }: { userId: string; messages: UIMessage[] } = await req.json();

  const result = await streamText({
    model: openai('gpt-4o-mini'), // 예시. 실제는 워크로드에 맞게
    system:
      'You are a senior software engineer. Provide actionable change suggestions with file-level pointers.',
    messages,
    tools: { fetchInternalDocs },
    // 멀티스텝: tool call 후 요약/최종 답변까지 생성 ([ai-sdk.dev](https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling?utm_source=openai))
    stopWhen: stepCountIs(3),
    // (선택) temperature 등 튜닝
  });

  // 툴 출력이 그대로 프론트로 흘러가면 위험할 수 있음 → onFinish에서 마스킹 ([community.vercel.com](https://community.vercel.com/t/hiding-tool-call-results-from-streamtext-in-ai-sdk/35687?utm_source=openai))
  return result.toDataStreamResponse({
    onFinish: async ({ responseMessage, messages: finalMessages }) => {
      // 1) tool output 마스킹(필요 시)
      responseMessage.parts = responseMessage.parts.map((part: any) => {
        if (typeof part?.type === 'string' && part.type.startsWith('tool-') && part.state === 'output-available') {
          return { ...part, output: '[REDACTED]' };
        }
        return part;
      });

      // 2) 로그 저장(프론트 상태만 믿지 말고 서버에서 확정본 저장)
      await saveChatTurn({
        userId,
        messages: finalMessages as UIMessage[],
      });
    },
  });
}
```

예상 동작:
- 사용자가 “rate limit 구현 어디야?” 같은 질문 → 모델이 `fetchInternalDocs` tool call  
- 서버가 snippets 반환 → 모델이 이를 근거로 “수정 파일/포인트”를 스트리밍으로 출력  
- 프론트에는 **최종 답변 중심**이 보이고, tool raw output은 마스킹됨

### 2) 클라이언트: `useChat`로 실서비스형 UI(메타데이터 포함)
```typescript
// app/page.tsx
'use client';

import { useChat } from '@ai-sdk/react';

export default function Page() {
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: '/api/chat',
    body: { userId: 'user_123' }, // 실제는 auth/session에서
  });

  return (
    <main style={{ maxWidth: 900, margin: '40px auto', fontFamily: 'system-ui' }}>
      <h1>Repo Helper</h1>

      <div style={{ border: '1px solid #ddd', padding: 16, borderRadius: 8, minHeight: 420 }}>
        {messages.map((m) => (
          <div key={m.id} style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, opacity: 0.6 }}>{m.role}</div>
            <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
          </div>
        ))}
        {isLoading && <div style={{ opacity: 0.7 }}>streaming…</div>}
      </div>

      <form onSubmit={handleSubmit} style={{ marginTop: 12, display: 'flex', gap: 8 }}>
        <input
          value={input}
          onChange={handleInputChange}
          placeholder="예: rate limit 구현 어디 파일 수정해야 해?"
          style={{ flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' }}
        />
        <button type="submit" style={{ padding: '12px 16px' }}>
          Send
        </button>
      </form>
    </main>
  );
}
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “Route Handler + Data Stream”을 기본값으로 두기
Next.js Route Handler는 App Router 표준이고, AI 스트리밍과 자연스럽게 붙습니다. ([nextjs.org](https://nextjs.org/docs/app/building-your-application/routing/route-handlers?utm_source=openai))  
그리고 `useChat`을 쓸 거면 서버는 웬만하면 **`toDataStreamResponse()` 계열**을 써서 프로토콜 호환을 확보하세요(단순 text stream과 다름).

### Best Practice 2) Tool calling은 “멀티스텝 비용”을 예산에 넣어라
`stopWhen`으로 멀티스텝을 켜면 편하지만, tool 개수/반복 횟수만큼 모델 호출이 늘어 **latency/비용이 선형으로 증가**합니다. ([ai-sdk.dev](https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling?utm_source=openai))  
권장 판단:
- “툴 1회 + 요약” 정도면 멀티스텝 OK
- 툴이 3개 이상 연쇄되면:  
  - 툴을 합치거나(서버에서 fan-out 후 통합 결과 1개로 제공)  
  - 아예 “계획/실행”을 분리(비동기 잡)하는 쪽이 낫습니다

### Best Practice 3) 운영(Observability/Feedback)을 초기에 스키마로 박아라
Vercel 템플릿에는 OpenTelemetry 예제가 별도로 존재합니다. ([vercel.com](https://vercel.com/templates/Next.js/ai-chatbot-telemetry?utm_source=openai))  
그리고 커뮤니티에서도 “메시지 단위 피드백(👍/👎)은 기본 제공이 아니라 직접 해야 한다”는 문제 제기가 있습니다. ([reddit.com](https://www.reddit.com/r/vercel/comments/1ph31iz/is_anyone_collecting_comment_feedback_in_vercel/?utm_source=openai))  
실무에서는 최소:
- `chatId`, `messageId`, `model`, `provider`, `token usage`, `latency`, `user feedback`를 **테이블/이벤트 스키마로** 먼저 고정하세요.

### 흔한 함정 1) Vercel Function timeout을 “스트리밍이면 괜찮겠지”로 착각
스트리밍은 UX를 개선하지만, 서버 실행 시간 제한을 무효화하지 않습니다. 실제로 AI 워크플로가 길어지면 Next.js 백엔드를 분리하는 사례가 나옵니다. ([reddit.com](https://www.reddit.com/r/micro_saas/comments/1t77nel/spent_today_migrating_our_backend_away_from/?utm_source=openai))  
대응:
- 긴 작업은 **비동기 큐/워커**로 보내고, 채팅 API는 “작업 생성 + 진행상태 스트림” 형태로 바꾸기

### 흔한 함정 2) Tool output이 그대로 UI/로그로 새는 문제
툴 출력에는 내부 경로/토큰/개인정보가 섞입니다. 기본값에 맡기지 말고 서버에서 `onFinish` 등으로 **마스킹/필터링**하세요. ([community.vercel.com](https://community.vercel.com/t/hiding-tool-call-results-from-streamtext-in-ai-sdk/35687?utm_source=openai))

### 비용/성능/안정성 트레이드오프 요약
- Edge runtime: 빠른 콜드스타트/지리적 이점 vs 라이브러리 제약/실행 제한(워크로드 따라)  
- Node.js runtime: 호환성/장시간 처리에 유리 vs 스트림/프로토콜 호환 이슈를 더 엄격히 테스트 필요(환경별 차이 사례 존재). ([reddit.com](https://www.reddit.com/r/nextjs/comments/1kfy1yy?utm_source=openai))
- 멀티스텝(tool calling): 제품 품질↑ vs 지연/비용↑

---

## 🚀 마무리
Next.js + Vercel AI SDK 조합의 본질은 “LLM 호출”이 아니라 **스트리밍 UX + provider 추상화 + tool orchestration**을 fullstack 한 곳에서 빠르게 굴릴 수 있다는 점입니다. ([vercel.com](https://vercel.com/docs/ai-sdk?utm_source=openai))  
도입 판단 기준은 단순합니다.

- 채팅/코파일럿/요약/리포트처럼 **응답 생성이 핵심 기능**이고, 스트리밍이 경쟁력이면: 적극 추천  
- 워크플로가 길어지고(>30~60s), 재시도/큐/대규모 병렬이 필요하면: Next.js는 **프론트+경량 API**로 두고, “잡 시스템”을 분리하는 게 장기적으로 안전

다음 학습 추천(실무 우선순위):
1) AI SDK tool calling + `stopWhen`으로 멀티스텝 제어(비용/지연 설계 포함) ([ai-sdk.dev](https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling?utm_source=openai))  
2) Next.js Route Handler에서 스트리밍/캐싱/동적 라우팅 이해 ([nextjs.org](https://nextjs.org/docs/14/app/building-your-application/routing/route-handlers?utm_source=openai))  
3) 텔레메트리/피드백 수집(품질 개선 루프) 템플릿 참고 ([vercel.com](https://vercel.com/templates/Next.js/ai-chatbot-telemetry?utm_source=openai))

원하시면, 위 예제를 **(1) 실제 DB(Prisma/Drizzle) 저장**, **(2) Redis rate limit**, **(3) 비동기 잡(Trigger.dev/큐)** 까지 확장한 “서비스 운영형” 아키텍처로 2편 형태로 이어서 작성해드릴게요.