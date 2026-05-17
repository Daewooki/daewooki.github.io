---
title: "Next.js + Vercel AI SDK로 “진짜” Fullstack AI 앱 만드는 법 (2026년 5월 기준): streaming, tool calling, agent loop까지 한 번에"
date: 2026-05-17 04:07:23 +0900
categories: [AI, Prototyping]
tags: [ai, prototyping, trend, 2026-05]
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
2026년 5월 기준으로 Next.js에서 AI 기능을 붙일 때 가장 흔한 실패는 “데모는 되는데, 제품은 안 되는” 지점에서 터집니다. 구체적으로는:

- **streaming**을 붙였는데 운영에서 버퍼링처럼 한 번에 몰아서 나오거나,
- **tool calling**을 넣었더니 호출이 느려지고(연쇄 호출), 비용이 튀거나,
- “agent”를 만들려다 **오케스트레이션/관측/중단 조건**이 부실해서 장애가 나는 경우입니다.

이때 **Next.js App Router + Route Handler**를 중심으로, 서버에서 **Vercel AI SDK의 `streamText`/tools/ToolLoopAgent**를 사용하면 “UI-스트림-툴-모델 호출”을 한 프로토콜로 묶을 수 있어 glue code가 크게 줄어듭니다. (공식 Next.js Route Handlers가 streaming을 1급으로 다루는 것도 핵심입니다. ([nextjs.org](https://nextjs.org/docs/13/app/building-your-application/routing/route-handlers?utm_source=openai)))

### 언제 쓰면 좋나
- **Next.js 기반 제품**에서: 채팅 UI, streaming 응답, tool calling, structured output을 빠르게 “제품급”으로 끌어올리고 싶을 때
- 서버에서 API key 보호 + 멀티스텝(tool loop)까지 한 프레임으로 묶고 싶을 때 (`streamText`, `ToolLoopAgent`) ([deepwiki.com](https://deepwiki.com/vercel/ai/2.1-text-generation?utm_source=openai))

### 언제 쓰면 안 되나
- **장시간 작업(수분~수십분)**, 워커/큐/내구 실행(durable execution)이 필수인 “백엔드 중심 에이전트”라면: AI SDK만으로는 부족할 수 있고(특히 런타임 제약/timeout), 별도 작업 큐/워크플로 레이어가 필요합니다. 커뮤니티에서도 “AI SDK는 UX/streaming 래퍼에 가깝다”는 의견이 반복됩니다. ([reddit.com](https://www.reddit.com/r/vercel/comments/1t0ntas/is_vercel_ai_sdk_actually_good_for_building_real/?utm_source=openai))
- Edge runtime에서 **Node 전용 패키지(Playwright 등)** 를 써야 한다면: 애초에 Edge에서 불가능/제약이 많아 `runtime='nodejs'` 설계로 가야 합니다. ([docs.steel.dev](https://docs.steel.dev/cookbook/vercel-ai-sdk-nextjs?utm_source=openai))

---

## 🔧 핵심 개념
### 1) AI SDK의 “메시지 계층”을 이해해야 풀스택이 단단해진다
Vercel AI SDK는 대충 “useChat ↔ API route ↔ LLM” 연결 도구가 아니라, **메시지 타입을 두 층**으로 나눕니다.

- **`UIMessage`**: 프론트(React)에서 다루는 메시지. `useChat`이 주고받는 형태
- **`ModelMessage`**: 실제 모델 호출에 들어가는 표준화된 메시지 형태

서버에서는 `UIMessage[]`를 모델 호출용으로 **`convertToModelMessages`** 같은 변환 과정을 거치는 패턴이 예제/문서에 반복됩니다. 이걸 이해하면 “클라에서 메타데이터를 마음껏 붙이되, 모델에는 필요한 것만 보낸다”가 가능해집니다. ([deepwiki.com](https://deepwiki.com/vercel/ai/5.1-next.js-integration?utm_source=openai))

### 2) `streamText`의 내부 흐름: “단일 스트림” 안에 text/tool 이벤트가 섞여 흐른다
`streamText`는 단순히 토큰을 흘려보내는 함수가 아니라, **멀티스텝 실행 모델**을 내장합니다.

1. 모델이 텍스트를 조금 생성(text-delta)
2. 모델이 tool call 이벤트를 생성(tool-call)
3. 서버가 tool을 실행(execute)하고 결과를 반환(tool-result)
4. 모델이 tool 결과를 컨텍스트로 다시 텍스트 생성…
5. stop 조건에서 종료

즉, “LLM 호출 1번”이 아니라 **(모델 ↔ 툴) 왕복이 여러 번** 일어날 수 있고, 이걸 **한 스트림 프로토콜**로 UI에 전달합니다. 그래서 stop 조건(`isStepCount`류) 없이 열어두면 비용/시간이 튈 수 있다는 경고가 문서/예제에 등장합니다. ([deepwiki.com](https://deepwiki.com/vercel/ai/2.1-text-generation?utm_source=openai))

### 3) `ToolLoopAgent`: tool calling을 “제품 로직”으로 승격시키는 루프
챗봇 수준을 넘어 “에이전트”로 가면 핵심은 **loop(관찰→결정→행동→반영)** 입니다. AI SDK의 `ToolLoopAgent`는 이 루프를 프레임으로 제공합니다. ([ai-sdk.dev](https://ai-sdk.dev/docs/reference/ai-sdk-core/tool-loop-agent?utm_source=openai))

- 장점: 툴 호출/스텝 관리/중단 조건을 표준화해서 직접 while-loop를 짜는 실수를 줄임
- 단점: 그래도 “내구 실행/큐/재시도/장기 작업”까지 자동으로 해결해주진 않음(앱 아키텍처로 보완 필요)

### 4) Next.js에서 Route Handler를 선호하는 이유
Next.js App Router의 **Route Handler는 Web Streams 기반 streaming**을 자연스럽게 처리하고, Edge/Node 런타임 선택도 코드 레벨에서 가능합니다. AI 응답 streaming은 “Server Actions vs Route Handler” 논쟁이 있지만, 현업 패턴은 여전히 Route Handler가 예측 가능하다는 경험담이 많습니다. ([nextjs.org](https://nextjs.org/docs/13/app/building-your-application/routing/route-handlers?utm_source=openai))

---

## 💻 실전 코드
현실적인 시나리오: **“리포지토리 릴리즈 노트를 기반으로 배포 요약 + 변경점 위험도 평가 + PR 링크 정리”**를 해주는 내부용 AI 도우미.
- 입력: 사용자가 릴리즈 노트 텍스트 + (선택) PR 목록 URL을 넣음
- 서버 tool:
  1) 텍스트에서 Jira 이슈 키 추출 → DB/사내 API로 소유팀/우선순위 조회
  2) PR URL이 있으면 메타데이터(제목/라벨) fetch
- 출력: streaming으로 요약이 생성되며, 중간에 tool 결과를 반영

### 0) 설치/환경 변수
```bash
npm i ai @ai-sdk/react zod
# provider 패키지는 사용하는 모델에 따라 추가
# 예: npm i @ai-sdk/openai  (환경에 맞게)
```

`.env.local`
```bash
# 예시 (사용 provider에 맞게)
OPENAI_API_KEY=...
```

### 1) Tool 정의 (server 전용)
```typescript
// lib/tools/release-tools.ts
import { z } from 'zod';

export const lookupIssueOwners = {
  description: 'Extract issue keys and return owner team + priority from internal system',
  inputSchema: z.object({
    keys: z.array(z.string()).min(1),
  }),
  execute: async ({ keys }: { keys: string[] }) => {
    // 실제로는 사내 API/DB를 호출
    // 여기서는 예시로 더미 응답
    return keys.map((k) => ({
      key: k,
      ownerTeam: k.startsWith('PAY') ? 'Payments' : 'Core',
      priority: k.endsWith('1') ? 'P0' : 'P2',
    }));
  },
};

export const fetchPullRequestMeta = {
  description: 'Fetch PR metadata (title, labels) from a URL list',
  inputSchema: z.object({
    urls: z.array(z.string().url()).min(1),
  }),
  execute: async ({ urls }: { urls: string[] }) => {
    // GitHub API 등을 붙이되, 토큰/레이트리밋/캐싱 고려 필요
    // 여기서는 더미
    return urls.map((u) => ({
      url: u,
      title: `Mock title for ${u.split('/').pop()}`,
      labels: ['risk:medium', 'area:frontend'],
    }));
  },
};
```

### 2) Route Handler: `streamText` + tools + stop 조건
```typescript
// app/api/release-assistant/route.ts
import { streamText, convertToModelMessages } from 'ai';
import { lookupIssueOwners, fetchPullRequestMeta } from '@/lib/tools/release-tools';

// Node API 필요한 경우 대비 (Playwright, node crypto, 특정 SDK 등)
// export const runtime = 'nodejs'; // 기본이 nodejs인 경우가 많지만 명시해두면 운영에서 덜 흔들림

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const messages = body?.messages ?? [];

  // UIMessage[] -> ModelMessage[] 로 변환(클라 메타데이터를 모델로 흘리지 않기)
  const modelMessages = convertToModelMessages(messages);

  const result = await streamText({
    // model: 사용 provider의 모델 객체를 넣으세요.
    // 예: model: openai('gpt-4.1-mini')
    model: body.model, // (예시) 데모용. 실제 제품에서는 화이트리스트로 제한하세요.
    messages: [
      {
        role: 'system',
        content:
          [
            'You are a release assistant for production deployments.',
            'Given release notes and PR links, generate:',
            '1) Executive summary',
            '2) Risk assessment with rationale',
            '3) Action items and owners',
            'When you need issue ownership, call lookupIssueOwners.',
            'When PR URLs are provided, call fetchPullRequestMeta.',
          ].join('\n'),
      },
      ...modelMessages,
    ],
    tools: {
      lookupIssueOwners,
      fetchPullRequestMeta,
    },
    // 멀티스텝 폭주 방지: tool-call 루프가 길어지면 비용/지연 급증
    stopWhen: (ctx) => ctx.steps.length >= 8,
  });

  // AI SDK는 스트리밍 응답 헬퍼를 제공(프로토콜은 useChat과 호환)
  return result.toDataStreamResponse();
}
```

### 3) Client: `useChat`로 streaming UI 구성
```typescript
// app/release/page.tsx
'use client';

import { useChat } from '@ai-sdk/react';

export default function ReleaseAssistantPage() {
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: '/api/release-assistant',
    // body에 모델 선택 등을 넘기고 싶다면 여기서 확장
    body: { model: undefined },
  });

  return (
    <div style={{ maxWidth: 900, margin: '24px auto', fontFamily: 'system-ui' }}>
      <h2>Release Assistant</h2>

      <form onSubmit={handleSubmit}>
        <textarea
          value={input}
          onChange={handleInputChange}
          placeholder={`Paste release notes + optional PR URLs.\nExample:\n- PAY-1201 Fix refund rounding\n- https://github.com/org/repo/pull/123`}
          rows={6}
          style={{ width: '100%', padding: 12 }}
        />
        <button disabled={isLoading} style={{ marginTop: 12 }}>
          {isLoading ? 'Generating…' : 'Generate'}
        </button>
      </form>

      <div style={{ marginTop: 24 }}>
        {messages.map((m) => (
          <div key={m.id} style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700 }}>{m.role}</div>
            <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

**예상 동작**
- Submit 직후 assistant 메시지가 streaming으로 점진적으로 채워짐
- 중간에 모델이 “이슈 소유팀 필요”를 판단하면 `lookupIssueOwners`가 호출되고, 그 결과를 반영해 최종 action items가 구체화됨
- `stopWhen`으로 최대 8 step에서 강제 종료 → 무한 루프/비용 폭발 방지 ([deepwiki.com](https://deepwiki.com/vercel/ai/2.1-text-generation?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “런타임 선택”을 기능 요구사항으로 격상하라
- Edge는 빠르고 지역 분산에 강점이 있지만 **Node API 제약**이 큽니다. Next.js도 Edge runtime이 Node.js API를 전부 지원하지 않는다고 명시합니다. ([nextjs.org](https://nextjs.org/docs/pages/api-reference/edge?utm_source=openai))  
- Playwright/브라우저 에이전트류는 Node 런타임으로 고정하는 예제가 많고, `maxDuration` 같은 실행 한도도 같이 다룹니다(장시간 도구 실행 대비). ([docs.steel.dev](https://docs.steel.dev/cookbook/vercel-ai-sdk-nextjs?utm_source=openai))  
결론: “AI API는 Edge로” 같은 구호 대신, **툴이 뭘 필요로 하는지**(Node 전용 SDK/바이너리/네트워크/timeout)로 결정하세요.

### Best Practice 2) tool calling은 “배치 설계”를 안 하면 느려진다
툴이 여러 번 호출되는 멀티스텝은 생각보다 쉽게 느려집니다.
- 예: 사람 이름 2개를 물었더니 tool이 1회가 아니라 2회 호출되는 케이스(모델이 분해해서 호출) ([community.vercel.com](https://community.vercel.com/t/vercel-ai-sdk-rsc-using-tools-in-streamtext/995?utm_source=openai))  
대응:
- tool inputSchema를 **배치-friendly** 하게 설계(배열 입력)
- tool 내부에서 **N+1을 합치고 캐싱**
- `stopWhen`/step 제한을 기본값으로 두기 ([deepwiki.com](https://deepwiki.com/vercel/ai/5.1-next.js-integration?utm_source=openai))

### Best Practice 3) “관측(Tracing)”을 초반에 박아라
AI 앱은 “느림/비용/품질”이 서로 엮여 있어서, 나중에 로그로 복구가 거의 안 됩니다. Vercel AI SDK의 `generateText`/`streamText`/ToolLoopAgent 트레이싱을 붙이는 가이드가 생태계에 빠르게 늘고 있습니다. ([docs.inference.net](https://docs.inference.net/integrations/traces/ai-sdk?utm_source=openai))  
최소한:
- requestId/사용자/모델/토큰/스텝 수/tool latency를 span으로 남기기
- “어떤 tool이 병목인지”가 보여야 최적화가 가능

### 흔한 함정) Server Actions로 다 때려 넣기
스트리밍/프로토콜/에러 처리/재시도까지 고려하면, 여전히 Route Handler가 **디버깅/운영 가시성**이 좋다는 현업 경험이 많습니다. ([reddit.com](https://www.reddit.com/r/nextjs/comments/1sc94a9/best_practice_for_streaming_ai_responses_in/?utm_source=openai))

### 비용/성능/안정성 트레이드오프 체크리스트
- step 한도(안정성↑, 품질↓ 가능) vs 무제한(품질↑, 비용/장애↑)
- Edge(지연↓) vs Node(호환성/툴 폭↑)
- tool granularity: 세분화(재사용↑) vs 배치(지연/비용↓)

---

## 🚀 마무리
Next.js + Vercel AI SDK로 fullstack AI 앱을 “제품급”으로 만들려면, 핵심은 **UI 훅(useChat)** 이 아니라 서버의 **streamText + tools + stop 조건 + 런타임 전략**입니다. `UIMessage → ModelMessage` 변환 계층을 명확히 두고, tool calling을 배치/캐싱 중심으로 설계하면 “프로토타입의 늪”을 크게 줄일 수 있습니다. ([deepwiki.com](https://deepwiki.com/vercel/ai/5.1-next.js-integration?utm_source=openai))

### 도입 판단 기준(내 프로젝트에 적용할지)
- Next.js App Router 기반이고 streaming UX가 핵심인가? → **Yes면 강추**
- 툴이 Node 전용/장시간 실행인가? → **Node runtime + 실행 한도/큐 전략**을 같이 설계
- “에이전트”가 필요하지만 장기 작업/내구 실행이 필수인가? → AI SDK는 기반으로 쓰되, **워크플로/큐**를 별도로 붙일 준비가 되어 있어야 함

### 다음 학습 추천(우선순위)
1) ToolLoopAgent로 “loop/stop/툴 설계” 감 잡기 ([ai-sdk.dev](https://ai-sdk.dev/docs/reference/ai-sdk-core/tool-loop-agent?utm_source=openai))  
2) Next.js Route Handler streaming 특성/제약(중간 notFound 불가 등) 이해 ([nextjs.org](https://nextjs.org/docs/13/app/building-your-application/routing/route-handlers?utm_source=openai))  
3) Tracing/observability를 붙여 “비용-지연-품질”을 수치로 운영 ([docs.inference.net](https://docs.inference.net/integrations/traces/ai-sdk?utm_source=openai))