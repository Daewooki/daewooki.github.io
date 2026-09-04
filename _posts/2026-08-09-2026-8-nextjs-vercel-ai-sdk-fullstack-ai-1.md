---
title: "Next.js + Vercel AI SDK로 “운영 가능한” Fullstack AI 앱을 만드는 법 (스트리밍·Tool Calling·모델 라우팅·비용 통제)"
description: "Next.js로 AI 앱을 만들 때 대부분의 팀이 초반에 겪는 문제는 비슷합니다."
date: 2026-08-09 02:13:51 +0900
categories: [AI, Prototyping]
tags: [ai, prototyping]
render_with_liquid: false
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
Next.js로 AI 앱을 만들 때 대부분의 팀이 초반에 겪는 문제는 비슷합니다.

- **스트리밍 UX**(TTFT/체감 성능)와 **서버 부하/타임아웃**을 동시에 만족시키기 어렵다  
- LLM 호출이 늘수록 **비용 통제**(모든 요청을 frontier model로 보내는 실수)가 곧바로 과금 폭탄으로 이어진다
- Tool calling을 붙이는 순간, “함수 몇 개”가 아니라 **권한/검증/관측(Observability)/재시도/폴백**까지 포함한 **백엔드 설계 문제**로 커진다
- 결과적으로 “챗봇 데모”는 금방 만들지만, **프로덕션 fullstack**(DB 저장, 정책, 라우팅, 오류 처리)로 확장할 때 갈아엎는다

2026년 8월 기준, Next.js App Router 위에서 Vercel AI SDK를 쓰면 “데모를 넘어 운영 가능한” 구조를 비교적 짧은 코드로 만들 수 있습니다. 특히 AI SDK는 기본적으로 **Vercel AI Gateway를 통한 모델 접근/라우팅**을 전제로 설계되어, 모델 교체/폴백/관측을 “문자열 바꾸기” 수준으로 단순화할 수 있는 게 강점입니다.[^1]

### 언제 쓰면 좋나
- **스트리밍 응답**이 곧 제품 경험인 경우(챗, 분석 리포트 생성, 코드 리뷰, 고객지원 등)
- **Tool calling**(DB 조회, 티켓 생성, 결제 상태 확인 등)을 붙여 “행동하는 AI”로 가야 하는 경우
- 트래픽이 늘면서 **비용/가용성/폴백**을 체계적으로 관리해야 하는 경우(AI Gateway 기반 라우팅이 유리)[^2]

### 언제 쓰면 안 되나
- 응답이 즉시 필요 없고 **배치/큐 기반**(워크플로우, 백그라운드 잡)이 더 적합한 문제를 억지로 실시간 스트리밍으로 만들 때
- 규제가 강해 **데이터 경로를 엄격히 고정**해야 하는데, 게이트웨이/다중 프로바이더 폴백 자체가 조직 정책과 충돌하는 경우(가능은 하지만 설계/검증 비용이 커짐)
- “RSC 기반 Generative UI(streamUI)”를 핵심 아키텍처로 박으려는 경우: 템플릿/문서에 **AI SDK RSC 개발이 pause**되었다는 명시가 있어(즉, 방향성이 바뀔 수 있음) 프로덕션 코어로는 보수적으로 봐야 합니다.[^3]

---

## 🔧 핵심 개념
### 1) AI SDK의 역할 분리: Core(서버) vs UI(클라이언트)
- 서버에서 하는 일: `streamText` 같은 **생성 호출 + 스트림 제어 + tool 실행**[^4]
- 클라이언트에서 하는 일: `useChat` 같은 **스트림 소비/메시지 상태 관리**(템플릿들이 이 패턴을 강하게 밀고 있음)[^5]

이 분리가 중요한 이유는, “LLM 호출”은 결국 외부 네트워크 + 과금 + 정책이 걸린 서버 관심사이고, UI는 스트리밍을 **끊김 없이 보여주는 상태 머신**이기 때문입니다. 둘을 섞으면(예: 클라이언트에서 직접 provider 호출) 키 관리/감사/비용 통제가 무너집니다.

### 2) Route Handler 스트리밍의 내부 흐름(실무 관점)
Next.js App Router에서 스트리밍 AI 엔드포인트의 전형적인 흐름은:

1. `app/api/chat/route.ts` 같은 **Route Handler**가 요청을 받음[^6]  
2. 입력을 검증/정규화(사용자 메시지, 세션, 권한)
3. AI SDK `streamText()`로 호출 → 토큰이 생성되는 대로 **ReadableStream 형태로 흘러나옴**
4. 이를 그대로 Response로 반환 → 클라이언트는 `useChat`이 그 스트림을 읽어 UI를 업데이트

여기서 포인트는 “API가 끝난 뒤 한번에 JSON 반환”이 아니라, **응답 바디가 시간에 따라 자라나는 스트림**이라는 점입니다. 그래서:
- 서버 타임아웃/런타임(edge/node) 선택
- 중간에 tool 실행이 끼어들 때의 지연(툴 호출 → DB/외부 API)  
을 고려한 설계가 필요합니다.

### 3) 2026년의 차별점: 모델 호출이 아니라 “라우팅”이 1급 시민
2026년 Vercel 스택에서 큰 변화는, AI SDK를 쓰면 기본적으로 **AI Gateway를 통해 수백 모델을 한 엔드포인트로 호출**하고, **폴백/라우팅/예산/모니터링**을 게이트웨이 계층에서 다룰 수 있다는 점입니다.[^2]

- 모델을 `"creator/model"` 문자열로 지정하면, 그 자체가 라우팅 지시가 됩니다(“base URL/프로바이더 SDK 바꿔끼우기” 부담 감소).[^7]
- providerOptions로 **우선순위/허용 목록/폴백**을 제어할 수 있습니다.[^8]

즉, 앱 코드는 “무슨 모델을 쓸지”가 아니라 **“이 요청을 어떤 티어로 보낼지”**(cheap vs frontier, latency vs quality)를 결정하는 쪽으로 진화합니다.

---

## 💻 실전 코드
현실적인 시나리오: **“고객지원 티켓 분류 + 요약 + 우선순위 산정”**  
- 입력: 사용자가 붙여넣은 문의 내용
- 출력(스트리밍): 먼저 요약 텍스트를 스트리밍으로 보여주고,
- tool calling: 내부 DB(여기서는 간단 mock)에서 **고객 플랜/최근 이슈**를 조회해 우선순위를 보정
- 비용: 쉬운 문의는 mini 모델, 어려우면 frontier로 승격(라우팅)

### 0) 설치/환경변수
```bash
# Next.js App Router 프로젝트 기준
pnpm add ai zod
# (직접 provider SDK를 고정해서 쓸 경우 @ai-sdk/openai 등도 사용하지만,
# 2026년 흐름은 AI Gateway 기본 경로를 많이 탑니다)
```

`.env.local`
```bash
AI_GATEWAY_API_KEY=your_key
```

### 1) Route Handler: 스트리밍 + tool calling + 티어 라우팅
`app/api/support/route.ts`
```typescript
import { streamText, tool, StreamingTextResponse } from 'ai';
import { z } from 'zod';

export const runtime = 'nodejs'; // edge는 타임아웃/제약 이슈가 생길 수 있어 우선 node 권장(케이스별 조정)

const TicketInput = z.object({
  message: z.string().min(20),
  userId: z.string().uuid(),
});

async function classifyDifficulty(text: string) {
  // 실무에선 휴리스틱 + 간단 모델 호출 조합을 권장
  const len = text.length;
  const hasLogs = /stack trace|exception|500|timeout|SQLSTATE/i.test(text);
  if (hasLogs || len > 1200) return 'hard' as const;
  return 'easy' as const;
}

// mock: 내부 고객 정보 조회(실무에선 DB/CRM)
async function getCustomerContext(userId: string) {
  // 예: Neon/Postgres에서 최근 티켓/플랜 조회 (템플릿은 Neon 사용 사례가 많음)[^5]
  return {
    plan: 'business', // free | pro | business
    openIncidents: 1,
    lastPaymentFailed: false,
  };
}

export async function POST(req: Request) {
  const json = await req.json();
  const { message, userId } = TicketInput.parse(json);

  const difficulty = await classifyDifficulty(message);

  // 쉬운 건 저렴/빠른 모델, 어려운 건 상위 모델
  // (모델명은 예시. 핵심은 creator/model 문자열로 라우팅한다는 점)[^7]
  const model =
    difficulty === 'easy'
      ? 'openai/gpt-5.4-mini'
      : 'openai/gpt-5.4';

  const result = streamText({
    model,
    system: [
      'You are a senior support engineer.',
      'Return actionable triage: summary, category, priority, and next steps.',
      'Be concise; no marketing tone.',
    ].join('\n'),
    prompt: `User message:\n${message}`,

    tools: {
      getCustomerContext: tool({
        description: 'Fetch plan and recent incident context for this user.',
        parameters: z.object({ userId: z.string().uuid() }),
        execute: async ({ userId }) => getCustomerContext(userId),
      }),
    },

    // 모델이 필요하다고 판단하면 tool을 호출해 근거를 보강하게 유도
    // (구체 프롬프트 전략은 팀 상황에 맞게 조정)
    // toolChoice 같은 세부 옵션은 모델/게이트웨이 설정에 따라 달라질 수 있음.
  });

  // Next.js Route Handler에서 스트리밍 텍스트 반환
  return new StreamingTextResponse(result.toAIStream());
}
```

#### 예상 동작(출력)
- 클라이언트는 요청 직후 200 응답을 받고,
- 본문은 토큰 단위로 점진적으로 도착하며,
- 내용 중간에 tool 호출이 발생하면(고객 플랜 조회) 잠깐 지연 후 이어서 스트리밍됩니다.

### 2) Client: `useChat`로 스트리밍 소비
`app/support/page.tsx`
```typescript
'use client';

import { useChat } from 'ai/react';
import { useMemo } from 'react';

export default function SupportTriagePage() {
  const { messages, input, handleInputChange, handleSubmit, isLoading } =
    useChat({
      api: '/api/support',
      body: useMemo(
        () => ({ userId: '3fa85f64-5717-4562-b3fc-2c963f66afa6' }),
        []
      ),
    });

  return (
    <div style={{ maxWidth: 820, margin: '40px auto', fontFamily: 'system-ui' }}>
      <h2>Support Triage</h2>

      <form onSubmit={handleSubmit}>
        <textarea
          value={input}
          onChange={handleInputChange}
          placeholder="Paste customer issue (logs, steps, expected/actual)..."
          rows={8}
          style={{ width: '100%', padding: 12 }}
        />
        <button disabled={isLoading} style={{ marginTop: 12 }}>
          {isLoading ? 'Streaming...' : 'Triage'}
        </button>
      </form>

      <div style={{ marginTop: 24 }}>
        {messages.map((m) => (
          <div key={m.id} style={{ marginBottom: 16 }}>
            <div style={{ opacity: 0.6 }}>{m.role}</div>
            <pre style={{ whiteSpace: 'pre-wrap' }}>{m.content}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 3) (확장) Provider 폴백/허용 목록을 코드로 고정하기
운영에서 흔한 요구: “우리 서비스는 특정 provider만 허용” 또는 “A가 장애면 B로 폴백”.

AI Gateway는 providerOptions로 **순서/허용 목록**을 줄 수 있습니다.[^8]  
아래는 개념 예시(실제 적용은 팀의 게이트웨이 설정/모델 정책에 맞춰 조정):

```typescript
const result = streamText({
  model: 'anthropic/claude-opus-4.5', // 예시
  providerOptions: {
    gateway: {
      order: ['bedrock', 'anthropic'],
      only: ['bedrock', 'anthropic'],
    },
  },
  prompt: '...',
});
```

---

## ⚡ 실전 팁 & 함정
### Best Practice 1) “스트리밍 엔드포인트는 Route Handler”를 기본값으로 두기
Server Actions로도 흉내는 낼 수 있지만, 스트리밍/에러/캐시/런타임 제어가 섞이면 디버깅 난이도가 급상승합니다. Next.js 문서도 Route Handler를 명확히 분리된 서버 엔드포인트로 안내합니다.[^6]  
(팀 내 규칙: “AI 스트리밍은 `/app/api/**`에서만” 같은 가드레일이 효과적)

### Best Practice 2) 비용 통제는 “모델 선택”이 아니라 “라우팅 정책”으로
모든 요청을 frontier로 보내는 팀이 매우 많습니다. 2026년 Vercel KB가 제시하는 방식은:
- 먼저 요청 난이도를 분류하고
- cheap tier로 시도 후
- 검증 실패/불확실할 때만 상위로 승격  
같은 패턴입니다.[^7]  
이걸 코드 레벨에서 강제하지 않으면, 기능 추가할 때마다 “일단 좋은 모델”로 회귀합니다.

### Best Practice 3) Tool calling은 “함수 호출”이 아니라 “권한 경계”다
- tool은 곧 내부 시스템 접근 권한입니다.
- `zod`로 파라미터를 제한하는 것만으로 부족하고, **userId/tenantId 기반 권한 체크**를 tool 내부에서 반드시 해야 합니다.
- 특히 “검색/조회 tool”은 프롬프트 인젝션에 의해 민감 데이터가 새어 나갈 수 있으므로, 반환 스키마를 최소화하고 로깅/감사를 남기세요.

### 흔한 함정/안티패턴
- **RSC Generative UI를 코어로 채택**: 템플릿에 “AI SDK RSC 개발 pause”가 명시되어 있어, 장기 유지보수 리스크가 있습니다. UI는 `useChat` 기반의 안정적인 경로를 먼저 잡고, RSC는 실험적으로만 권장합니다.[^3]
- **Edge 런타임 만능론**: 스트리밍+툴 호출+DB 접근을 한 번에 넣으면, 실행 제한/네트워크 제약/장애 재현성 때문에 오히려 운영이 어려워집니다. 먼저 nodejs에서 안정화 후 edge는 “정말 필요한 엔드포인트만” 분리하는 편이 낫습니다.
- **관측(Observability) 부재**: “왜 느린지”가 LLM 때문인지 tool 때문인지 게이트웨이 라우팅 때문인지 모르면 최적화가 불가능합니다. AI Gateway는 라우팅/폴백/사용량을 한곳에서 보려는 목적이 강합니다.[^2]

### 비용/성능/안정성 트레이드오프(의사결정 기준)
- **성능(TTFT)**: cheap/fast 모델 + 스트리밍이 체감 품질을 올림
- **품질**: frontier 모델로 승격하는 조건(검증 실패/불확실성)이 핵심
- **안정성**: provider 폴백은 가용성을 올리지만, 모델별 미세한 응답 차이로 테스트/회귀 비용이 늘 수 있음 → “중요 플로우만 고정 모델” 같은 절충이 필요
- **비용**: 난이도 분류/승격 정책이 없으면 트래픽 증가와 비용 증가가 거의 선형으로 따라옴[^7]

---

## 🚀 마무리
정리하면, 2026년 8월의 “Next.js + Vercel AI SDK fullstack”에서 중요한 건 **LLM 호출 자체가 아니라 운영 가능한 경계 설계**입니다.

- Route Handler에서 `streamText`로 **스트리밍 UX**를 만들고[^4]  
- tool calling은 “기능”이 아니라 “권한/검증/감사” 관점으로 설계하고
- 모델 선택은 개별 개발자 취향이 아니라 **라우팅 정책(cheap→frontier, 폴백, 예산)**으로 통제하며[^7]  
- RSC Generative UI는 멋지지만, 문서/템플릿에서 pause 신호가 있으니(장기 리스크) 코어에는 보수적으로 접근하는 게 안전합니다.[^3]

### 도입 판단 체크리스트
- “스트리밍이 제품 가치인가?” → Yes면 AI SDK + Route Handler가 강력한 기본값
- “tool이 2개 이상 필요한가?” → Yes면 권한 경계/관측/폴백까지 포함한 설계가 필수
- “비용이 중요한가?” → Yes면 난이도 분류 + 티어 라우팅을 초기에 넣을 것[^7]

### 다음 학습 추천
- AI SDK Core의 `streamText`/tool calling 레퍼런스(옵션과 이벤트 훅을 숙지)[^4]  
- Vercel AI Gateway의 모델/프로바이더/폴백 및 providerOptions 전략[^2]  
- Vercel의 Next.js AI Chatbot 템플릿을 “기능”이 아니라 **아키텍처(데이터 저장, 파일, auth) 관점**으로 뜯어보기[^5]

[^1]: <https://github.com/vercel/ai>
[^2]: <https://vercel.com/docs/ai-gateway>
[^3]: <https://vercel.com/templates/next.js/rsc-genui>
[^4]: <https://ai-sdk.dev/docs/reference/ai-sdk-core/stream-text>
[^5]: <https://vercel.com/new/folds-graphics-projects/templates/next.js/nextjs-ai-chatbot>
[^6]: <https://nextjs.org/docs/15/app/getting-started/route-handlers-and-middleware>
[^7]: <https://vercel.com/kb/guide/cost-aware-model-routing-with-ai-gateway>
[^8]: <https://vercel.com/docs/ai-gateway/models-and-providers/provider-options>
