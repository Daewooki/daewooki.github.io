---
title: "Next.js + Vercel AI SDK로 “진짜” Fullstack AI 앱 만들기 (2026년 6월 기준): 스트리밍·툴콜·런타임 선택까지"
date: 2026-06-15 05:11:54 +0900
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
Next.js로 AI 앱을 만들 때 팀이 가장 많이 막히는 지점은 “모델 호출 자체”가 아니라 **제품 형태로 만들기 위한 풀스택 접점**입니다. 예를 들면:

- UI는 빠르게 반응해야 하는데, LLM 응답은 느리다 → **Streaming**이 필수
- 단순 Q&A가 아니라 검색/DB/외부 API를 연결해야 한다 → **Tool calling**이 필요
- 배포 환경(Vercel)에서 Edge/Node 런타임, 타임아웃, 스트림 포맷이 꼬인다 → **런타임/프로토콜 이해**가 필요

2026년 6월 기준, Next.js App Router + Route Handlers 조합이 “AI 스트리밍 백엔드”로 가장 예측 가능하고, Vercel AI SDK는 그 위에서 **provider 교체 가능 + streamText 기반 메시지 스트림 + 툴 호출 파트**를 표준화해줍니다. (실제 템플릿/예제도 App Router 중심으로 제공) ([vercel.com](https://vercel.com/templates/next.js/vercel-x-xai-chatbot?utm_source=openai))

### 언제 쓰면 좋나
- **채팅/코파일럿/에이전트형 UX**(중간 진행상황을 보여줘야 함)
- 모델이 **외부 지식(사내 문서/DB/브라우저/사내 API)**에 의존
- provider(예: OpenAI/Anthropic/xAI 등)를 바꿀 가능성이 있어 **벤더 락인을 줄이고 싶을 때** ([vercel.com](https://vercel.com/templates/next.js/vercel-x-xai-chatbot?utm_source=openai))

### 언제 쓰면 안 되나
- 결과가 항상 짧고 즉시 끝나는 작업(예: 짧은 분류)만 한다면 굳이 복잡한 스트리밍 파이프라인은 과함
- Edge Runtime 제약(지원되지 않는 Node API/패키지)과 타임아웃이 치명적인 워크로드라면, “Edge에 다 올리기”는 오히려 리스크 ([nextjs.org](https://nextjs.org/docs/pages/api-reference/edge?utm_source=openai))
- Generative UI(RSC로 UI를 모델이 스트리밍)까지 욕심내면, 현재는 **AI SDK RSC 라인이 ‘paused’** 공지가 있어(예제 페이지에 명시) 장기 유지보수 관점에서 신중해야 함 ([vercel.com](https://vercel.com/new/mke/templates/next.js/rsc-genui?utm_source=openai))

---

## 🔧 핵심 개념
### 1) “풀스택 AI 앱”에서의 데이터 흐름(권장 아키텍처)
Next.js(App Router) 기준으로 가장 실무적인 흐름은 이렇습니다:

1. **Client(UI)**: `useChat` 같은 UI 훅이 `/api/chat`로 메시지를 POST
2. **Route Handler(서버)**: `streamText`로 모델 호출 + tool 실행
3. **Stream Protocol**: 텍스트 토큰 + tool-call/tool-result 같은 “파트(part)”가 섞여서 스트림으로 내려옴  
4. **Client(UI)**: 스트림을 읽어 “지금 모델이 말하는 중인지 / 툴을 실행 중인지 / 툴 결과가 뭔지”를 상태로 렌더링

Steel 예제처럼 “에이전트가 브라우저를 조작하고(tool) 그 과정이 UI로 스트리밍”되는 패턴이 2026년형의 전형적인 형태입니다. ([docs.steel.dev](https://docs.steel.dev/cookbook/vercel-ai-sdk-nextjs?utm_source=openai))

### 2) Route Handlers + 런타임(Edge vs Node) 선택이 중요한 이유
Next.js Route Handlers는 Web API 기반이라 Edge/Node 모두에서 동작하도록 설계되어 있고, 스트리밍도 지원합니다. ([nextjs.org](https://nextjs.org/docs/13/app/building-your-application/routing/route-handlers?utm_source=openai))  
하지만 실무에서는 **런타임에 따라 실패 양상이 달라**집니다.

- **Edge Runtime**
  - 장점: 지연시간(Latency) 유리, 전 세계 POP 근접
  - 단점: Node API/패키지 제약, 일부 기능 제한(ISR 미지원 등), 운영 제약이 까다로움 ([nextjs.org](https://nextjs.org/docs/pages/api-reference/edge?utm_source=openai))
- **Node.js Runtime**
  - 장점: 대부분의 SDK/드라이버/암호화/DB 라이브러리 호환성 좋음, 긴 작업에 유리
  - 단점: Edge 대비 지연시간 불리(대신 많은 AI 앱은 모델 지연이 지배적이라 체감이 작기도)

**판단 기준:** 툴이 DB/브라우저 자동화/사내망 호출/무거운 패키지(Chromium, native deps)를 쓰면 Node로 가는 게 안전합니다. Steel 예제도 Node runtime을 명시합니다. ([docs.steel.dev](https://docs.steel.dev/cookbook/vercel-ai-sdk-nextjs?utm_source=openai))

### 3) Generative UI(RSC streaming)는 “매력적이지만” 현재 판단이 필요
Vercel은 `streamUI`로 RSC를 스트리밍하는 Generative UI를 강하게 밀었고, 내부적으로는 “텍스트 토큰 스트림”이 아니라 “UI 조각을 점진적으로 보내는” 방식입니다. ([vercel.com](https://vercel.com/blog/ai-sdk-3-generative-ui?utm_source=openai))  
다만 2026년 시점에는 공식 템플릿 페이지에서 **AI SDK RSC 개발이 paused**라고 명시되어 있어, 신규 프로덕션에 바로 박기보다는 **텍스트 스트리밍 + tool 파트 렌더링**을 기본으로 두고, UI 스트리밍은 실험/특정 화면에 제한하는 전략이 현실적입니다. ([vercel.com](https://vercel.com/new/mke/templates/next.js/rsc-genui?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “toy”가 아니라, 실제 서비스에서 흔한 **사내 지식 검색 + DB 기록 + 스트리밍 답변** 시나리오입니다.

- UI: `useChat`로 스트림 수신
- 서버: `/api/chat` Route Handler에서
  - `streamText`로 답변 스트리밍
  - tool 2개 제공:
    - `searchDocs`: 사내 문서 검색(여기서는 외부 API로 가정)
    - `saveNote`: DB에 요약 저장(PostgreSQL/Prisma 가정)
- 런타임: Node.js (DB 드라이버 호환성/긴 작업 대비)

### 0) 설치/환경변수
```bash
pnpm add ai @ai-sdk/openai zod
pnpm add prisma @prisma/client
# 또는 사용하는 DB/ORM으로 대체
```

```bash
# .env
OPENAI_API_KEY=...
DOCS_API_URL=https://internal.example.com/search
DATABASE_URL=postgresql://...
```

### 1) 서버: Route Handler (스트리밍 + tool calling)
```typescript
// app/api/chat/route.ts
import { z } from 'zod';
import { streamText } from 'ai';
import { openai } from '@ai-sdk/openai';
import { PrismaClient } from '@prisma/client';

export const runtime = 'nodejs';

const prisma = new PrismaClient();

const SearchDocsInput = z.object({
  query: z.string().min(2),
  topK: z.number().int().min(1).max(8).default(5),
});

const SaveNoteInput = z.object({
  title: z.string().min(1),
  content: z.string().min(1),
  sourceMessageId: z.string().optional(),
});

export async function POST(req: Request) {
  const { messages } = await req.json();

  // 실무 포인트: system에 “툴을 언제/어떻게 쓰는지”를 강하게 적어야
  // 에이전트가 실제로 tool을 활용함.
  const system = `
너는 사내 개발자 지원 어시스턴트다.
- 사용자가 질문하면 먼저 searchDocs 도구로 근거를 찾고,
- 근거를 인용 형태(문서 제목/URL)로 요약한 뒤 답변하라.
- 답변 마지막에는 "요약을 저장할까요?"를 물어보고,
  사용자가 원하면 saveNote 도구를 호출해 저장하라.
`;

  const result = await streamText({
    model: openai('gpt-4.1-mini'), // 예시: 모델은 조직 정책/비용에 맞게
    system,
    messages,
    maxSteps: 8, // tool 실행 + 후속 답변까지 충분히
    tools: {
      searchDocs: {
        description: '사내 문서 검색 API를 호출해 관련 문서를 찾는다.',
        inputSchema: SearchDocsInput,
        execute: async ({ query, topK }) => {
          const url = new URL(process.env.DOCS_API_URL!);
          url.searchParams.set('q', query);
          url.searchParams.set('k', String(topK));

          const res = await fetch(url.toString(), {
            headers: { 'Accept': 'application/json' },
          });
          if (!res.ok) throw new Error(`DOCS_API error: ${res.status}`);
          const data = await res.json();

          // 반환 형태는 모델이 쓰기 쉬운 “작은 덩어리”가 좋음
          return (data.items ?? []).map((it: any) => ({
            title: it.title,
            url: it.url,
            snippet: it.snippet,
          }));
        },
      },

      saveNote: {
        description: '답변 요약을 DB에 저장한다.',
        inputSchema: SaveNoteInput,
        execute: async ({ title, content, sourceMessageId }) => {
          const row = await prisma.note.create({
            data: { title, content, sourceMessageId },
            select: { id: true, createdAt: true },
          });
          return row;
        },
      },
    },
  });

  // AI SDK의 표준 스트림 응답(클라이언트 useChat과 호환)
  return result.toTextStreamResponse();
}
```

**예상 동작(스트림):**
- 클라이언트는 텍스트 토큰이 점진적으로 보이고,
- 중간에 `searchDocs` tool-call 파트가 발생하면 “검색 중…” 같은 UI를 띄울 수 있음
- 사용자가 저장 요청을 하면 `saveNote` 호출 → 결과(id/createdAt)가 스트림 파트로 내려옴

### 2) 클라이언트: tool 파트까지 렌더링하는 채팅 UI
```typescript
// app/page.tsx
'use client';

import { useChat } from 'ai/react';

export default function Page() {
  const { messages, input, handleInputChange, handleSubmit, isLoading } =
    useChat({ api: '/api/chat' });

  return (
    <main style={{ maxWidth: 860, margin: '40px auto', fontFamily: 'system-ui' }}>
      <h1>Dev Assistant</h1>

      <div style={{ border: '1px solid #ddd', padding: 16, borderRadius: 12 }}>
        {messages.map((m) => (
          <div key={m.id} style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700 }}>{m.role}</div>

            {/* 텍스트 */}
            {m.content && <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>}

            {/* 실무 포인트: tool-call/tool-result 파트를 UI로 노출 */}
            {Array.isArray(m.parts) &&
              m.parts.map((p: any, idx: number) => {
                if (p.type === 'tool-call') {
                  return (
                    <div key={idx} style={{ marginTop: 8, color: '#555' }}>
                      [tool-call] {p.toolName} {JSON.stringify(p.args)}
                    </div>
                  );
                }
                if (p.type === 'tool-result') {
                  return (
                    <div key={idx} style={{ marginTop: 8, background: '#fafafa', padding: 8 }}>
                      <div style={{ color: '#555' }}>[tool-result] {p.toolName}</div>
                      <pre style={{ margin: 0, overflowX: 'auto' }}>
                        {JSON.stringify(p.result, null, 2)}
                      </pre>
                    </div>
                  );
                }
                return null;
              })}
          </div>
        ))}

        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8 }}>
          <input
            value={input}
            onChange={handleInputChange}
            placeholder="질문을 입력하세요 (예: 배포 파이프라인에서 캐시가 꼬여요)"
            style={{ flex: 1, padding: 10, borderRadius: 10, border: '1px solid #ddd' }}
          />
          <button disabled={isLoading} style={{ padding: '10px 14px' }}>
            전송
          </button>
        </form>
      </div>
    </main>
  );
}
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “툴 결과”는 모델이 읽기 쉬운 구조로, 그리고 작게
툴 출력이 너무 크면:
- 토큰 비용 증가
- 모델이 핵심을 놓치고 헛소리(환각) 확률 증가
- 스트림이 느려짐

`searchDocs` 결과는 **title/url/snippet** 정도로 제한하고, 원문이 필요하면 “추가로 문서 본문 fetch tool”을 분리하는 게 안정적입니다.

### Best Practice 2) 런타임은 “Edge 우선”이 아니라 “의존성/타임아웃 우선”
Next.js Edge Runtime은 Node API가 제한되고(공식 문서에 caveats 명시), 패키지 호환성 문제로 디버깅 비용이 커집니다. ([nextjs.org](https://nextjs.org/docs/pages/api-reference/edge?utm_source=openai))  
DB/브라우저 자동화/사내 SDK 같은 **무거운 툴**이 들어가면 Node로 두고, 정말 latency가 중요한 경로만 Edge로 분리하세요(예: 인증 프록시, 얇은 라우팅).

### 함정 1) “Generative UI(streamUI)”는 프로덕션 기본값으로 두기엔 리스크
Generative UI는 강력하지만, Vercel 템플릿 자체에 **AI SDK RSC 개발 paused**가 명시되어 있습니다. ([vercel.com](https://vercel.com/new/mke/templates/next.js/rsc-genui?utm_source=openai))  
즉, 2026년 6월 현재 판단은:
- 기본은 **streamText + tool parts 렌더링**
- UI 스트리밍은 “실험 기능/특정 플로우”로 격리

### 함정 2) 스트리밍은 인프라/프록시에서 “버퍼링”되면 망가진다
로컬에서는 잘 되는데 프로덕션에서 한 번에 몰아서 뜨는 문제는, 중간 프록시가 응답을 버퍼링하는 경우가 흔합니다(특히 self-host + nginx 등). 커스텀 인프라를 쓴다면 `Cache-Control: no-store`, 압축/버퍼 설정을 점검해야 합니다(관련 이슈 사례가 커뮤니티에 반복적으로 등장). ([reddit.com](https://www.reddit.com/r/nextjs/comments/1d3x76h?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **maxSteps**를 크게 하면 tool 연쇄 실행이 가능하지만 비용/지연이 증가
- Node 런타임은 안정적이지만, Edge 대비 지역별 latency가 늘 수 있음(다만 LLM 호출이 병목이면 큰 차이가 안 날 때도 많음)
- tool이 외부 API를 많이 때리면 “모델 비용”보다 “툴 비용/레이트리밋”이 먼저 터집니다 → tool 캐싱/디바운싱 설계가 더 중요

---

## 🚀 마무리
핵심은 “Next.js는 UI, AI SDK는 모델 호출” 정도의 얕은 결합이 아니라, **Route Handler에서 스트리밍 + tool calling을 표준 프로토콜로 만들고, 클라이언트는 그 파트를 제품 UX로 해석**하는 구조가 2026년형 풀스택 AI 앱의 정답에 가깝다는 점입니다. (템플릿/예제도 이 흐름에 맞춰 제공) ([vercel.com](https://vercel.com/templates/next.js/vercel-x-xai-chatbot?utm_source=openai))

### 도입 판단 기준(체크리스트)
- 채팅/코파일럿 UX에서 **중간 진행상황**이 가치인가? → YES면 스트리밍
- 외부 지식/DB/자동화가 필요한가? → YES면 tool calling
- Edge 제약을 감당할 수 있는가? (패키지/타임아웃/운영) → NO면 Node 우선 ([nextjs.org](https://nextjs.org/docs/pages/api-reference/edge?utm_source=openai))
- Generative UI가 “핵심 가치”인가, “부가 실험”인가? → paused 공지 고려해 격리 ([vercel.com](https://vercel.com/new/mke/templates/next.js/rsc-genui?utm_source=openai))

### 다음 학습 추천
- Next.js Route Handlers의 스트리밍/런타임 설정을 정확히 이해하기 ([nextjs.org](https://nextjs.org/docs/13/app/building-your-application/routing/route-handlers?utm_source=openai))
- Vercel AI SDK의 tool-part 스트림을 UI에서 어떻게 “상태 머신”으로 표현할지(로딩/툴 실행/결과/재시도)
- Generative UI(`streamUI`)는 “기술 데모”가 아니라 **유지보수 가능한 범위**로 제한적으로 실험 ([vercel-ai.mintlify.app](https://vercel-ai.mintlify.app/reference/ai-sdk-rsc/stream-ui?utm_source=openai))