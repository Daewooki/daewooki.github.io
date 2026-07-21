---
title: "0.9초 안에 말이 돌아오는 실시간 Voice Agent: 2026년 7월 기준 STT·TTS·Realtime 모델 선택과 구현 포인트"
date: 2026-07-21 03:28:31 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-07]
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
실시간 음성 대화(“전화/웹에서 끊김 없이 대화”)가 어려운 이유는 모델 성능보다 **지연(latency)과 턴테이킹(turn-taking)** 때문입니다. STT가 “문장 끝”을 너무 늦게 확정하거나, LLM이 첫 토큰을 늦게 뱉거나, TTS가 “첫 오디오(time-to-first-audio)”가 늦으면 사용자는 바로 “로봇 같다/답답하다”로 체감합니다. LiveKit은 이 문제를 **WebRTC 기반 실시간 미디어 전송 + 에이전트 런타임(Agents)** 로 묶어 “음성 파이프라인을 제품 수준으로 운영”하는 쪽에 초점이 있습니다. ([docs.livekit.io](https://docs.livekit.io/agents/?utm_source=openai))

언제 쓰면 좋나:
- **콜센터/예약/상담/내부 헬프데스크**처럼 “대화 중 도구 실행(조회/예약/티켓 생성)”이 필수인 경우(함수 호출/툴콜 기반). 파이프라인(STT→LLM→TTS)이 디버깅/제어가 쉽습니다. ([livekit.com](https://livekit.com/voice-agents?utm_source=openai))
- 웹/앱에서 **WebRTC로 양방향 음성**을 붙이고, 관찰(트랜스크립트/트레이스)과 배포/스케일링까지 염두에 둔 경우(LiveKit Agents). ([docs.livekit.io](https://docs.livekit.io/agents/?utm_source=openai))

언제 쓰면 안 되나:
- “사람처럼 자연스러운 말투/감정/억양”이 최우선이고, 복잡한 툴콜 제어가 덜 중요한 경우는 **speech-to-speech(Realtime) 모델**이 더 간단할 수 있습니다(대신 단계별 제어가 줄어듦). ([livekit.com](https://livekit.com/voice-agents?utm_source=openai))
- 완전 오프라인/엣지에서 **엄격한 지연 보장**이 필요하면(예: 임베디드), 클라우드 API 의존이 큰 스택은 설계부터 다시 봐야 합니다(온디바이스 streaming ASR 연구/모델 검토 필요). ([arxiv.org](https://arxiv.org/abs/2604.14493?utm_source=openai))

---

## 🔧 핵심 개념
### 1) “실시간”의 정의는 모델이 아니라 **스트리밍+파이프라이닝**
2026년에도 업계 표준은 대체로 **cascaded streaming pipeline: STT → LLM → TTS** 입니다. 중요한 건 세 단계를 “순차 실행”이 아니라 **서로 겹치게(overlap)** 만들어 전체 TTFA(Time To First Audio)를 줄이는 겁니다. 실측에서도 end-to-end(speech-to-speech) 모델이 느리거나(예: 특정 모델은 TTFA가 수초~10초대) 제어가 어려워, 파이프라인이 여전히 실무 주류라는 결과가 보고됩니다. ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))

핵심 지연 구성요소(대화 체감에 직결):
- **Endpointing/VAD**: 사용자가 말 끝났는지 판단(침묵 임계치)  
- **STT first partial / final**: 첫 부분 자막이 뜨는 시점, 최종 확정 시점  
- **LLM TTFT**(time-to-first-token): 첫 토큰이 나오기까지  
- **TTS TTFA**(time-to-first-audio): 첫 오디오 바이트가 나오기까지 ([livekit.com](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained?utm_source=openai))

### 2) Turn-taking: “대화가 자연스럽다”의 절반
LiveKit Agents는 음성 에이전트에서 자주 망가지는 부분(중간 끼어들기, 말 겹침, 응답 타이밍)을 다루기 위해 **turn detection/interruptions/speech handle** 같은 음성 제어 개념을 노출합니다. 즉 “STT 결과가 나왔으니 말한다”가 아니라, **언제 말 시작/중단/재개할지**를 프레임워크 레벨에서 잡습니다. ([docs.livekit.io](https://docs.livekit.io/agents/multimodality/audio/?utm_source=openai))

### 3) Realtime 모델 vs 파이프라인: 선택 기준
- **Realtime(speech-to-speech)**: STT/TTS를 생략해 지연을 줄이고 음성 뉘앙스를 보존할 수 있지만, 단계별 관측/수정/정책 적용(예: PII 마스킹 후 TTS)이 어렵고, 제공자/모델에 따라 기능(툴콜 등)이 제약될 수 있습니다. ([livekit.com](https://livekit.com/voice-agents?utm_source=openai))
- **STT→LLM→TTS**: 각 단계 최적화(특정 STT, 특정 TTS 교체), 규정 준수, 캐싱/폴백, 장애 격리가 쉽습니다. “0.9초 TTFA” 같은 목표는 **단일 모델이 아니라 파이프라이닝 설계**로 달성하는 쪽이 현실적이라는 튜토리얼/실험 결과가 많습니다. ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))

---

## 💻 실전 코드
아래 예제는 “웹(또는 콜)에서 들어오는 오디오 스트림”을 **WebRTC(LiveKit Room)** 로 받고, 서버에서 **STT→LLM→TTS를 스트리밍으로 엮어** 사용자가 말하는 도중에도 부분 인식/응답 준비를 진행하는 구조를 목표로 합니다.

전제:
- 런타임은 Node.js
- 미디어 전송/세션은 LiveKit
- STT/TTS는 LiveKit Agents 플러그인(또는 LiveKit Inference)로 교체 가능(코드 구조 유지) ([docs.livekit.io](https://docs.livekit.io/agents/?utm_source=openai))

### 1) 셋업
```bash
# Node 20+ 권장
mkdir realtime-voice-agent && cd realtime-voice-agent
npm init -y

# LiveKit Agents JS + (예: VAD 플러그인) 설치
npm i @livekit/agents @livekit/agents-plugin-silero dotenv zod
```

`.env`
```bash
LIVEKIT_URL=wss://YOUR_LIVEKIT_HOST
LIVEKIT_API_KEY=YOUR_KEY
LIVEKIT_API_SECRET=YOUR_SECRET

# (선택) STT/TTS/LLM 제공자 키들
OPENAI_API_KEY=...
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...
```

### 2) “현실적인” 음성 상담 시나리오: 주문 조회 + 바지인(barge-in)
- 사용자는 “주문번호 1234 상태 알려줘… 아, 배송지 변경도…”처럼 중간에 말을 바꿈
- 에이전트는 **말 끊기면(Turn detection)** 즉시 TTS를 중단하고 다시 듣기
- 툴콜로 내부 API를 호출하고, 결과를 짧게 요약해 말하기

`agent.ts`
```typescript
import 'dotenv/config';
import { z } from 'zod';
import {
  Agent,
  defineTool,
  type ToolContext,
} from '@livekit/agents';

// (예시) 실제로는 DB/CRM/OMS 호출
async function fetchOrder(orderId: string) {
  // latency가 큰 외부 API라고 가정(현실적인 케이스)
  await new Promise(r => setTimeout(r, 250));
  return {
    orderId,
    status: 'IN_TRANSIT',
    eta: '2026-07-23',
    carrier: 'UPS',
  };
}

const getOrderStatus = defineTool({
  name: 'getOrderStatus',
  description: '주문번호로 배송 상태를 조회한다.',
  schema: z.object({
    orderId: z.string().min(1),
  }),
  handler: async ({ orderId }: { orderId: string }, ctx: ToolContext) => {
    // 관찰 포인트: 툴 실행 시간/실패율이 음성 UX에 그대로 드러남
    const data = await fetchOrder(orderId);
    return data;
  },
});

async function main() {
  // LiveKit Agents는 STT-LLM-TTS 파이프라인과 realtime 모델을 모두 다룰 수 있는 구조를 제공
  // (여기서는 파이프라인 접근을 가정)
  const agent = new Agent({
    // 아래는 “어떤 STT/TTS/LLM을 쓰든” 구조가 유지되게 하는 게 핵심
    // 실제 SDK에서는 provider 플러그인/설정 객체로 바인딩
    instructions: `
너는 물류 고객센터 상담원이다.
1) 답변은 짧고, 먼저 핵심(상태/예상일)부터 말한다.
2) 고객이 말을 끊으면 즉시 멈추고 다시 듣는다.
3) 주문조회는 getOrderStatus 도구를 사용한다.
`,
    tools: [getOrderStatus],
  });

  // (중요) 스트리밍/턴테이킹/인터럽트는 “모델”보다 프레임워크/설정이 지배
  // LiveKit Agents는 speech handle 기반으로 말하기/중단 제어를 제공한다. ([docs.livekit.io](https://docs.livekit.io/agents/multimodality/audio/?utm_source=openai))

  await agent.start({
    livekit: {
      url: process.env.LIVEKIT_URL!,
      apiKey: process.env.LIVEKIT_API_KEY!,
      apiSecret: process.env.LIVEKIT_API_SECRET!,
      room: 'support-queue',
    },

    // (개념적으로) VAD는 endpointing을 빠르게 만들어 체감 latency를 크게 줄임
    // STT가 native streaming을 지원하지 않으면 VAD로 감싸 streaming처럼 동작시키는 패턴도 문서에 언급됨. ([docs.livekit.io](https://docs.livekit.io/agents/logic/nodes/?utm_source=openai))
    vad: {
      provider: 'silero',
      // 실제 튜닝 포인트: silence threshold / min speech duration 등
    },

    stt: {
      provider: 'deepgram', // 또는 'openai'의 streaming STT 등 (2026년: streaming STT 모델 등장) ([openai.com](https://openai.com/index/advancing-voice-intelligence-with-new-models-in-the-api/?utm_source=openai))
      model: 'nova',        // 예시
      interimResults: true,
    },

    llm: {
      provider: 'openai',
      model: 'gpt-realtime', // speech-to-speech가 아니라도, 저지연 응답/도구호출 조합을 고려
    },

    tts: {
      provider: 'cartesia', // 예: streaming TTS
      voice: 'your-voice-id',
      stream: true,
    },
  });

  console.log('voice agent started');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

예상 동작(개념):
- 사용자가 말하기 시작 → VAD/STT가 partial transcript를 빠르게 올림
- LLM은 **final transcript 전**에도(정책에 따라) 준비를 시작하거나, 최소한 “툴 파라미터 후보”를 준비
- 사용자가 끼어들면(barge-in) → 현재 TTS 스트림 중단 → 다시 STT 우선
- “주문번호 1234”가 확정되면 tool call → 결과 요약 → TTS가 **문장 전체 생성 전**에 먼저 말 시작(스트리밍 TTS)

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **Endpointing을 ‘보수적으로’ 잡지 말고, 도메인별로 튜닝**
- 침묵 임계치를 조금만 길게 잡아도 “LLM이 시작을 못하는 시간”이 누적됩니다.
- 콜센터처럼 짧은 문장이 많은 도메인은 aggressive endpointing + 바지인 안정화가 유리합니다. ([livekit.com](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained?utm_source=openai))

2) “전 단계 스트리밍”을 강제하라: STT partial → LLM streaming → TTS streaming
- 어느 한 단계라도 배치로 굳으면 전체가 배치처럼 느껴집니다.
- 실측으로도 “키는 빠른 모델”이 아니라 **스트리밍을 연결하는 아키텍처**라는 결론이 반복됩니다. ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))

3) 관찰 가능성(Observability)을 먼저 설계
- 대화 UX 이슈의 80%는 “VAD가 늦게 끝남 / STT가 final을 늦게 줌 / TTS가 TTFA가 김”처럼 계측으로만 잡힙니다.
- LiveKit은 에이전트 운영/배포/관측을 강조합니다. ([docs.livekit.io](https://docs.livekit.io/agents/?utm_source=openai))

### 흔한 함정/안티패턴
- **“Realtime(speech-to-speech)면 끝”**이라고 생각: 자연스러울 수는 있어도, 콜센터 업무처럼 툴콜/정책/감사로그가 중요하면 단계별 제어가 필요합니다. ([livekit.com](https://livekit.com/voice-agents?utm_source=openai))
- STT로 Whisper 계열을 “실시간”에 그대로 투입: Whisper는 기본적으로 배치/청크 설계라 **native streaming 제약**이 자주 언급되고, 실시간은 별도 아키텍처/대안이 필요합니다. ([openai.com](https://openai.com/index/advancing-voice-intelligence-with-new-models-in-the-api/?utm_source=openai))
- “조용한 구간”에서의 STT hallucination/잡음 트리거를 무시: VAD/노이즈 억제, 최소 발화 길이 등을 도메인 데이터로 검증해야 합니다(연구에서도 VAD 결합/버퍼링 전략이 핵심으로 다뤄짐). ([arxiv.org](https://arxiv.org/abs/2604.25611?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **가장 비싼 건 보통 LLM 토큰**입니다. 하지만 음성 UX는 STT/TTS/endpointing이 결정하는 경우가 많아, “LLM을 더 큰 모델로”보다 “턴테이킹/스트리밍을 더 잘”이 비용 대비 효과가 큽니다.
- STT/TTS를 교체 가능한 파이프라인으로 두면, 지역/언어/도메인별로 “지연 최적”과 “정확도 최적”을 분리 운영할 수 있습니다. ([livekit.com](https://livekit.com/voice-agents?utm_source=openai))

---

## 🚀 마무리
2026년 7월 기준 실시간 Voice Agent의 승부처는 “최신 모델 이름”이 아니라:
- **스트리밍(전 단계) + 파이프라이닝(단계 겹치기)**
- **턴테이킹(바지인/중단/재개)**
- **관측/운영(계측 기반 튜닝)**
입니다. ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))

도입 판단 기준(현실 체크):
- 툴콜/정책/감사/디버깅이 중요하면 **STT→LLM→TTS 파이프라인**으로 시작
- “자연스러움 최우선 + 기능 제어는 덜 중요”면 **Realtime(speech-to-speech)** 를 POC로 빠르게 검증
- 어떤 경우든, 첫 주 목표는 “정확도”가 아니라 **P50 TTFA < 1.2s** 같은 지연 SLO를 잡고 계측부터 하는 게 성공 확률이 높습니다. ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))

다음 학습 추천:
- LiveKit Agents의 **audio/interruptions/speech handle** 개념을 먼저 정독하고(턴테이킹이 UX를 좌우), ([docs.livekit.io](https://docs.livekit.io/agents/multimodality/audio/?utm_source=openai))
- “Voice Agent Architecture” 글의 지연 분해(TTFT/TTFA/endpointing)를 기준으로, 여러분의 도메인 통화/대화 로그에 맞춰 VAD·STT·TTS를 튜닝해보세요. ([livekit.com](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained?utm_source=openai))