---
title: "말 끊김 없이 “대화가 되는” 2026년형 실시간 음성 에이전트: STT/TTS 파이프라인 vs Speech-to-Speech, WebRTC로 끝내기"
date: 2026-06-05 04:28:03 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-06]
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
실시간 음성 에이전트에서 개발자가 실제로 겪는 문제는 단순히 **STT 정확도**가 아닙니다. “사용자가 말 끝나자마자 1초 안에 첫 소리가 나오는가”, “중간에 끼어들면(barge-in) 자연스럽게 멈추는가”, “네트워크가 흔들려도 세션이 살아남는가” 같은 **대화 UX/시스템 문제**가 핵심입니다. 엔터프라이즈에선 여기에 **관측(Observability), 비용, 장애 격리, 개인정보**가 덧붙습니다.

언제 쓰면 좋나?
- 콜센터/상담, 인앱 코치, 현장 작업 보조처럼 **즉시 반응(낮은 latency) + 길게 대화(안정성)**가 필요한 경우
- 도구 호출(function calling)로 **업무 시스템과 연결**해야 하는 경우(예약/검색/티켓 생성)

언제 쓰면 안 되나?
- 사용자 경험이 “대화”가 아니라 “녹음 후 처리”에 가까운 경우(회의록, 사후 분석). 이 경우 실시간 스트리밍 복잡도를 감수할 이유가 적습니다.
- 규제/보안으로 **클라우드 전송이 어려운 환경**인데 온프렘 구축 여력이 없을 때(실시간은 네트워크/인프라 의존도가 큼)

2026년 6월 시점 트렌드는 크게 두 갈래입니다.
1) 여전히 주류인 **Cascaded Streaming 파이프라인(STT → LLM → TTS)**: 각 단계는 스트리밍으로 “겹쳐” 돌려서 시간을 줄입니다. 엔터프라이즈 튜토리얼 논문에서도 “핵심은 모델 하나가 아니라 streaming/pipelining”이라고 못 박습니다. ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))  
2) **Speech-to-Speech(End-to-End) Realtime 모델**: 입력도 오디오, 출력도 오디오로 받는 방식. OpenAI는 Realtime API와 새로운 음성 모델들을 발표했고 ([openai.com](https://openai.com/index/advancing-voice-intelligence-with-new-models-in-the-api/?utm_source=openai)), AWS도 WebRTC 기반 양방향 스트리밍을 AgentCore에 넣어 “브라우저/모바일” 실시간 경험을 전면에 둡니다. ([aws.amazon.com](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-bedrock-webrtc/?utm_source=openai))  

---

## 🔧 핵심 개념
### 1) “실시간”의 정의: TTFA(Time To First Audio)
실무에서 체감 품질을 결정하는 지표는 보통 **TTFA(P50/P90)** 입니다.  
- P50이 800~1000ms면 “빠르다” 느낌이 나고  
- P90이 2초를 넘어가면 사용자(특히 상담/인터뷰)가 끊기거나 겹침이 생깁니다.  
엔터프라이즈 튜토리얼은 Cascaded 구성으로도 P50 TTFA ~947ms(best 729ms)까지 측정합니다. ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))  

### 2) 두 가지 아키텍처 비교
#### A. Cascaded Streaming (STT → LLM → TTS)
**구조/흐름**
1. 클라이언트 마이크 오디오를 짧은 프레임(예: 20ms)로 쪼개 전송
2. STT가 partial transcript(중간 결과)를 계속 푸시
3. LLM은 “문장 끝”을 기다리지 않고 **증분(incremental)**로 토큰 생성(스트리밍)
4. TTS도 텍스트를 chunk로 받아 **스트리밍 합성**
5. 사용자가 말 끊으면 VAD/ASR 이벤트로 TTS를 즉시 cancel

**장점**
- 도구 호출, 긴 컨텍스트, 고난도 추론을 LLM에 맡기기 쉬움(디버깅도 텍스트 기반)
- 벤더 교체가 상대적으로 쉬움(STT/TTS/LLM 분리)

**단점**
- 각 단계의 지연이 누적되기 쉬움(특히 네트워크 hop이 많으면 악화)
- partial transcript 기반의 “성급한 추론”이 생길 수 있음(말이 아직 안 끝났는데 결론 내림)

#### B. Speech-to-Speech Realtime (Audio In/Out)
**구조/흐름**
- 오디오 스트림을 WebRTC/WebSocket으로 모델에 넣으면 모델이 오디오로 바로 응답(중간에 텍스트를 만들지 않거나 선택적으로만 생성)

**장점**
- 파이프라인 단계가 줄어 TTFA가 낮아지기 쉬움
- turn-taking/backchannel(“음…”, “네”) 같은 대화적 리듬이 자연스럽게 나올 여지

**단점**
- 텍스트 중간 산출물이 없으면 디버깅/감사/로깅이 어려워질 수 있음(대신 별도 transcription 채널이 필요)
- 벤더 종속이 커질 수 있음(프로토콜/세션/이벤트 모델)

OpenAI는 Realtime API에서 WebRTC 연결을 권장하고(브라우저에서 일관된 성능) 데이터채널로 이벤트를 주고받는 패턴을 공식 가이드로 제공합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  

### 3) “더 빨리 말하기” 트릭: Speculative/Hybrid
2026년 논문들에서 흥미로운 방향은 “빠른 경로”와 “느린 경로”를 병렬로 돌려 **첫 음성은 빨리**, 내용은 **나중에 더 정확하게** 이어붙이는 방식입니다(예: RelayS2S). ([arxiv.org](https://arxiv.org/abs/2603.23346?utm_source=openai))  
즉, 실시간의 본질은 “한 방에 끝내는 모델”이 아니라 **오케스트레이션**입니다.

---

## 💻 실전 코드
아래 예제는 **브라우저(WebRTC) ↔ 서버(툴/로그/권한) ↔ OpenAI Realtime** 구성을 전제로 합니다.

- 브라우저는 WebRTC로 “말하고/듣는” 실시간 세션을 유지
- 서버는 **Ephemeral token 발급**, 도구 호출 처리, 대화 로그/관측을 담당
- 음성 에이전트는 “바로 응답 + barge-in + function calling”까지 고려

> 주의: OpenAI Realtime의 이벤트 타입/모델명은 제품 업데이트가 잦습니다. 아래 코드는 “구조/패턴”을 재사용하는 용도이며, 이벤트 스키마는 공식 문서 기준으로 맞추세요. (WebRTC 연결 + data channel 이벤트 송수신 패턴은 문서에 명시) ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  

### 0) 의존성/구성
```bash
# server
npm init -y
npm i express cors dotenv
npm i openai

# client는 Vite/Next 등 아무거나 가능(여기선 개념 코드)
```

`.env`
```bash
OPENAI_API_KEY=...
```

### 1) 서버: Ephemeral token 발급 + 툴 엔드포인트
브라우저에 API Key를 두지 말고, 서버에서 짧게 사는 토큰을 발급합니다(공식 WebRTC 가이드에서도 “ephemeral key” 흐름을 소개). ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))

```typescript
// server/index.ts
import express from "express";
import cors from "cors";
import "dotenv/config";
import OpenAI from "openai";

const app = express();
app.use(cors());
app.use(express.json());

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY! });

// 1) 브라우저가 WebRTC로 붙을 때 사용할 ephemeral token 발급
app.post("/api/realtime-token", async (req, res) => {
  // 모델/권한/만료는 프로젝트 정책에 맞게
  // (정확한 파라미터는 OpenAI 최신 문서에 맞춰 조정)
  const token = await client.realtime.sessions.create({
    model: "gpt-realtime", // 예시: 실제론 gpt-realtime 또는 최신 realtime 모델
    // voice, modalities, tools 등 세션 기본값을 서버에서 강제할 수도 있음
  });

  res.json(token);
});

// 2) 함수 호출 예시: “티켓 생성”
app.post("/api/create-ticket", async (req, res) => {
  const { title, detail, priority } = req.body;
  // 실제로는 Jira/Linear/ServiceNow 등 연동 + 인증/감사로그 필요
  const ticketId = `TCK-${Math.floor(Math.random() * 100000)}`;
  res.json({ ticketId, title, priority, createdAt: new Date().toISOString() });
});

app.listen(8787, () => console.log("server on :8787"));
```

### 2) 클라이언트: WebRTC 세션 + DataChannel 이벤트 + Barge-in(핵심)
- 오디오 송수신은 `RTCPeerConnection`이 처리
- 제어 이벤트(대화 아이템 생성/툴 결과 전달/취소)는 **data channel**로 주고받습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  

```typescript
// client/realtime.ts (개념 코드)
async function startVoiceAgent() {
  // 1) ephemeral token 받기
  const tokRes = await fetch("http://localhost:8787/api/realtime-token", { method: "POST" });
  const tok = await tokRes.json();

  // 2) WebRTC PeerConnection 구성
  const pc = new RTCPeerConnection();

  // 2-1) 마이크 입력을 peer에 붙임
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  for (const track of stream.getAudioTracks()) pc.addTrack(track, stream);

  // 2-2) 에이전트 음성 출력 재생
  pc.ontrack = (e) => {
    const audio = document.querySelector<HTMLAudioElement>("#agentAudio")!;
    audio.srcObject = e.streams[0];
    audio.play();
  };

  // 3) DataChannel로 이벤트 송수신
  const dc = pc.createDataChannel("oai-events");
  dc.onmessage = async (e) => {
    const evt = JSON.parse(e.data);

    // (A) 툴 호출 요청이 오면 서버에 위임 후 결과를 다시 모델에 전달
    if (evt.type === "response.output_item.tool_call") {
      const { name, arguments: args, call_id } = evt;
      if (name === "create_ticket") {
        const r = await fetch("http://localhost:8787/api/create-ticket", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(JSON.parse(args)),
        });
        const result = await r.json();

        dc.send(JSON.stringify({
          type: "conversation.item.create",
          item: {
            type: "tool_result",
            tool_call_id: call_id,
            content: [{ type: "output_text", text: JSON.stringify(result) }],
          },
        }));

        // 툴 결과 반영해서 후속 응답 생성 트리거(이벤트명은 최신 스펙에 맞춰 조정)
        dc.send(JSON.stringify({ type: "response.create" }));
      }
    }

    // (B) 디버깅/관측: partial transcript나 상태 이벤트를 로그로 남김
    if (evt.type?.includes("transcription") || evt.type?.includes("session")) {
      console.log("[realtime]", evt.type, evt);
    }
  };

  // 4) SDP offer/answer 교환 (여기서는 개념적으로만 표시)
  // 실제 구현은 OpenAI Realtime WebRTC 가이드의 절차를 따르세요. ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))
  // - createOffer -> setLocalDescription
  // - OpenAI endpoint에 SDP 전송 -> SDP answer 수신
  // - setRemoteDescription

  // 5) “barge-in” 처리: 사용자가 말 시작하면 에이전트 TTS를 취소
  // 포인트: 클라이언트 VAD(간단) + 서버/모델 이벤트(정교) 조합이 안정적
  const vad = createSimpleVAD(stream, () => {
    // 말 시작 감지 시 현재 응답 취소 이벤트 전송(이벤트명은 최신 스펙 확인)
    dc.send(JSON.stringify({ type: "response.cancel" }));
  });

  // 6) 첫 시스템 지시 + 툴 정의(세션 시작 시 한 번)
  dc.onopen = () => {
    dc.send(JSON.stringify({
      type: "session.update",
      session: {
        instructions:
          "너는 사내 헬프데스크 음성 에이전트다. 사용자의 이슈를 요약하고 필요하면 티켓을 생성한다.",
        tools: [{
          type: "function",
          name: "create_ticket",
          description: "헬프데스크 티켓 생성",
          parameters: {
            type: "object",
            properties: {
              title: { type: "string" },
              detail: { type: "string" },
              priority: { type: "string", enum: ["low","medium","high"] }
            },
            required: ["title","detail","priority"]
          }
        }]
      }
    }));

    // 대화 시작 트리거(사용자 음성 기반이라면 자동으로 시작되도록 구성 가능)
    dc.send(JSON.stringify({
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text: "지금부터 음성으로 문의할게." }]
      }
    }));
    dc.send(JSON.stringify({ type: "response.create" }));
  };
}

// 매우 단순한 VAD 예시(실무는 WebAudio + energy + hangover + 노이즈 적응 필요)
function createSimpleVAD(stream: MediaStream, onSpeechStart: () => void) {
  const ctx = new AudioContext();
  const src = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  src.connect(analyser);

  const data = new Uint8Array(analyser.frequencyBinCount);
  let speaking = false;

  const tick = () => {
    analyser.getByteFrequencyData(data);
    const energy = data.reduce((a, b) => a + b, 0) / data.length;

    if (!speaking && energy > 18) { // 임계값은 환경별 튜닝 필요
      speaking = true;
      onSpeechStart();
    } else if (speaking && energy < 10) {
      speaking = false;
    }
    requestAnimationFrame(tick);
  };
  tick();
  return { stop: () => ctx.close() };
}
```

예상 동작(현실 시나리오)
- 사용자가 “VPN이 자꾸 끊겨요…”라고 말하는 중에도 partial events가 로깅되고
- 에이전트가 해결 절차를 말하다가 사용자가 끼어들면 즉시 `response.cancel`로 **TTS가 멈추고**
- “티켓 만들까요?” 흐름에서 모델이 `create_ticket` 툴을 호출하면 서버가 실제 티켓 생성 후 결과를 다시 전달
- 이후 에이전트가 “TCK-12345 생성했어요”처럼 음성으로 마무리

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **WebSocket보다 WebRTC 우선(브라우저)**  
브라우저/모바일의 실시간 오디오는 WebRTC가 지연/지터 대응에 유리합니다. OpenAI도 브라우저 연결은 WebRTC를 권장합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  

2) **오디오 경로와 제어 경로를 분리**  
오디오는 WebRTC 미디어 트랙으로, 제어는 data channel(이벤트)로. 이 분리가 되어야  
- barge-in 취소  
- 도구 호출/결과 전달  
- 세션 업데이트(정책/툴/프롬프트)  
를 “끊김 없이” 처리합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  

3) **관측(Observability)을 처음부터**  
“대화가 이상하다”는 버그 리포트는 대부분 재현이 어렵습니다. 최소한 아래는 남기세요.
- TTFA(P50/P90), turn latency, cancel 횟수
- VAD 트리거 시점 vs 실제 사용자 발화 시점(오탐/미탐)
- tool call request/response payload(PII 마스킹 포함)

### 흔한 함정/안티패턴
- **(안티패턴) STT 최종 결과만 기다렸다가 LLM 호출**: 실시간이 아닙니다. 엔터프라이즈 튜토리얼도 스트리밍/파이프라이닝이 핵심이라고 지적합니다. ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))  
- **(안티패턴) barge-in을 “클라이언트에서 오디오 mute”로만 처리**: 상대(모델)는 계속 말하고 있어 상태가 꼬입니다. 반드시 “취소 이벤트”로 세션 상태를 동기화하세요.
- **(함정) NAT/방화벽 환경에서 WebRTC 실패**: TURN이 필요합니다. AWS AgentCore도 WebRTC를 쓰려면 TURN(관리형/서드파티/자가)을 언급합니다. ([aws.amazon.com](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-bedrock-webrtc/?utm_source=openai))  

### 비용/성능/안정성 트레이드오프
- **Speech-to-Speech 모델**은 단계가 줄어 UX는 좋아지기 쉬우나, 감사/재처리/품질 관리(텍스트 로그)가 약해질 수 있어 **별도 transcription 채널**(또는 Realtime transcription 모델)을 함께 고려하는 편이 안전합니다. OpenAI도 Realtime transcription을 별도 가이드로 분리해 제공합니다. ([openai.com](https://openai.com/index/advancing-voice-intelligence-with-new-models-in-the-api/?utm_source=openai))  
- **Cascaded**는 구성 요소별 최적화가 가능하지만, hop이 늘어날수록 P90이 튀기 쉽습니다. 이때 RelayS2S 같은 speculative/hybrid(빠른 프리픽스 + 느린 고품질 이어쓰기)가 설계 대안이 됩니다. ([arxiv.org](https://arxiv.org/abs/2603.23346?utm_source=openai))  

---

## 🚀 마무리
정리하면, 2026년 6월의 “실시간 음성 에이전트”는 **모델 선택**보다 **스트리밍 아키텍처와 오케스트레이션**이 승부처입니다.
- 브라우저/모바일: WebRTC + data channel 이벤트 기반으로 “오디오/제어”를 분리하고 ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  
- barge-in, tool calling, 재연결/관측을 필수 기능으로 보고
- Speech-to-Speech(Realtime)로 단순화할지, Cascaded로 통제/교체 가능성을 가져갈지 결정하세요. 엔터프라이즈 튜토리얼이 말하듯, 복잡한 업무엔 아직 Cascaded가 강력한 현실 해법입니다. ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))  

도입 판단 기준(실무용 체크)
- P90 TTFA 목표가 1.5초 이내인가? → WebRTC + 스트리밍 필수
- 감사/요약/검색을 위해 텍스트 로그가 필수인가? → transcription/텍스트 경로를 반드시 설계
- 네트워크가 거친 환경(기업망/모바일)인가? → TURN/재연결/세션 복구를 예산에 포함 ([aws.amazon.com](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-bedrock-webrtc/?utm_source=openai))  

다음 학습 추천
- OpenAI Realtime API WebRTC 가이드(이벤트/세션 모델 이해) ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  
- “Enterprise Realtime Voice Agents from Scratch” 논문(지연 측정/파이프라인 구성) ([arxiv.org](https://arxiv.org/abs/2603.05413?utm_source=openai))  
- RelayS2S 같은 speculative/hybrid 패턴(낮은 TTFA + 높은 품질의 공존) ([arxiv.org](https://arxiv.org/abs/2603.23346?utm_source=openai))  

원하면, 위 코드 예제를 **(1) Next.js + Vite 프론트**, **(2) 실제 SDP 교환/시그널링**, **(3) 음성 UI(푸시투톡/자동감지) + 재연결 + 로그 수집**까지 포함한 “프로덕션 스켈레톤” 형태로 확장해 드릴 수 있어요.