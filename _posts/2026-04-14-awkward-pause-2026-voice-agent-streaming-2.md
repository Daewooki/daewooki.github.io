---
title: "멈칫(awkward pause) 없는 2026 실시간 Voice Agent: Streaming STT/TTS vs Speech-to-Speech Realtime의 승부처"
date: 2026-04-14 03:29:28 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-04]
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
2026년 4월 기준, 음성 AI는 “말은 잘하는데 대화가 어색한” 단계를 넘어서 **실시간(turn-taking)** 품질이 제품 경쟁력을 좌우하는 국면입니다. 콜센터/IVR, 인앱 상담, 음성 코치, 통역/번역 등에서 사용자가 제일 민감하게 느끼는 건 정확도보다도 **응답 타이밍(지연, 끊김, 끼어들기 barge-in)** 입니다.

최근 흐름은 크게 둘로 정리됩니다.

- **Cascaded(Streaming STT → LLM → Streaming TTS)**: 제어력이 높고 디버깅이 쉽지만, 레이어가 많아질수록 EOT(end-of-turn)와 tool call 왕복에서 지연이 튑니다. Deepgram 같은 벤더는 스트리밍 지연을 p95 관점으로 측정/개선하라고 강조합니다. ([developers.deepgram.com](https://developers.deepgram.com/docs/measuring-streaming-latency?utm_source=openai))  
- **Speech-to-Speech(end-to-end) Realtime**: 오디오 in/out을 단일 세션으로 처리해 구조를 단순화하고 지연을 줄이는 방향. OpenAI는 WebRTC/WebSocket/SIP로 연결되는 `gpt-realtime`과 Realtime API를 GA로 밀고 있고, 브라우저에서는 **ephemeral token + WebRTC 직결** 패턴을 공식 가이드로 제공합니다. ([openai.com](https://openai.com/index/introducing-gpt-realtime?utm_source=openai))  

이 글은 “실시간 음성 대화 구현”에 초점을 맞춰, 2026년형 아키텍처 선택 기준과 **바로 실행 가능한 코드 스켈레톤**까지 정리합니다.

---

## 🔧 핵심 개념
### 1) 핵심 지표는 ‘STT latency’가 아니라 ‘대화 루프 지연’
실무에서 체감 품질을 결정하는 건 보통 다음의 합입니다.

- **EOT latency**: 사용자가 말을 멈춘 뒤 “이제 내 차례”라고 시스템이 확정하는 시간  
- **TTFB/TTFS(Time-to-first-speech)**: 모델이 첫 음성 바이트를 내기까지의 시간  
- **Barge-in handling**: 사용자가 끼어들면 AI 음성을 즉시 중단하고 다시 듣기 모드로 전환하는 능력

Deepgram 문서도 “voice agent에서 중요한 건 transcription latency 자체보다 **end-of-turn(EOT)**”라고 못 박습니다. ([developers.deepgram.com](https://developers.deepgram.com/docs/measuring-streaming-latency?utm_source=openai))  

### 2) Realtime(Speech-to-Speech)의 구조적 이점: 레이어 제거가 곧 지연 제거
전통 파이프라인은 (대충) 이렇게 됩니다.

`Audio → STT → (텍스트) LLM → TTS → Audio`

반면 Realtime은 “한 세션에서” 오디오를 받고 오디오를 내며, WebRTC/WebSocket/SIP 같은 low-latency 전송을 전제로 합니다. OpenAI는 `gpt-realtime`이 **WebRTC/WebSocket/SIP**를 지원한다고 명시합니다. ([developers.openai.com](https://developers.openai.com/api/docs/models/gpt-realtime?utm_source=openai))  

이게 왜 중요하냐면:
- STT 결과의 오탈자/부분 결과가 LLM 입력으로 “굳어지는” 문제 감소
- TTS 시작을 텍스트 생성 끝까지 기다리지 않고, 모델이 오디오를 스트리밍으로 흘릴 수 있음
- 브라우저/모바일에서 **WebRTC**로 네트워크 적응(지터 버퍼, 패킷 손실 대응)까지 가져갈 수 있음

### 3) WebRTC 직결의 보안 패턴: Ephemeral Token
브라우저에서 Realtime로 바로 붙이면 키 유출이 치명적이라, 공식 가이드는 다음 패턴을 권장합니다.

- Backend: **master API key**로 ephemeral token 발급
- Frontend: ephemeral token으로 WebRTC 연결 수립 ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  

이 패턴이 2026년형 “클라이언트 실시간 음성”의 기본값입니다.

---

## 💻 실전 코드
아래는 **(1) Node 서버에서 ephemeral token 발급 → (2) 브라우저에서 WebRTC로 Realtime 연결**하는 최소 예제입니다. (실제 서비스에선 인증/레이트리밋/로깅을 추가하세요)

```javascript
// server.js (Node + Express)
// 1) 브라우저가 /session 호출 -> 2) 서버가 OpenAI에 ephemeral token 요청 -> 3) 브라우저에 반환
import express from "express";

const app = express();
app.use(express.json());

app.post("/session", async (req, res) => {
  // 주의: OPENAI_API_KEY는 서버에만 보관
  const apiKey = process.env.OPENAI_API_KEY;

  // OpenAI 공식 문서의 "Realtime API with WebRTC" 가이드 흐름을 따름
  // (세부 엔드포인트/필드명은 문서 업데이트에 따라 바뀔 수 있으니 반드시 확인)
  const r = await fetch("https://api.openai.com/v1/realtime/sessions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session: {
        type: "realtime",
        model: "gpt-realtime",
        audio: {
          output: { voice: "marin" }, // 예: marin/cedar 등(가용 voice는 계정/정책에 따라 다름)
        },
      },
    }),
  });

  if (!r.ok) {
    const err = await r.text();
    return res.status(500).send(err);
  }

  const data = await r.json();

  // 보통 client_secret 같은 형태로 내려오며, 이를 프론트에서 사용
  res.json({ client_secret: data.client_secret });
});

app.listen(3000, () => console.log("listening on http://localhost:3000"));
```

```html
<!-- index.html (브라우저) -->
<script>
async function startRealtime() {
  // 1) ephemeral token(client_secret) 받기
  const s = await fetch("/session", { method: "POST" }).then(r => r.json());
  const token = s.client_secret?.value;
  if (!token) throw new Error("No client_secret");

  // 2) WebRTC PeerConnection 준비
  const pc = new RTCPeerConnection();

  // 3) 마이크 입력을 RTCPeerConnection에 연결
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  for (const track of stream.getAudioTracks()) pc.addTrack(track, stream);

  // 4) 원격 오디오 재생 (AI 음성)
  const audio = document.createElement("audio");
  audio.autoplay = true;
  pc.ontrack = (e) => { audio.srcObject = e.streams[0]; };

  // 5) (선택) DataChannel로 이벤트/툴콜/자막 등을 주고받는 통로
  const dc = pc.createDataChannel("oai-events");
  dc.onmessage = (m) => {
    // 여기서 partial transcript / turn events / tool calls 등을 처리
    // 실무 포인트: barge-in을 하려면 "사용자 발화 감지" 이벤트에 맞춰
    // 현재 재생 중인 오디오를 끊고(또는 세션에 중단 이벤트 전송) 듣기 모드로 전환
    console.log("event:", m.data);
  };

  // 6) SDP Offer 생성 -> OpenAI Realtime에 전달 -> SDP Answer로 연결 완성
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  // OpenAI Realtime API는 WebRTC SDP offer/answer 플로우를 제공
  const answerRes = await fetch("https://api.openai.com/v1/realtime/calls", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`, // ephemeral token 사용
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ sdp: offer.sdp, session: { type: "realtime" } }),
  });

  const answer = await answerRes.json();
  await pc.setRemoteDescription({ type: "answer", sdp: answer.sdp });

  console.log("Realtime connected");
}

startRealtime().catch(console.error);
</script>
```

위 흐름은 OpenAI가 문서에서 제시하는 **ephemeral token + WebRTC 연결** 및 Realtime call(offer/answer) 개념과 맞닿아 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  

---

## ⚡ 실전 팁
1) **Turn detection을 “내가 직접” 하려는 순간 지연이 폭발한다**  
Streaming STT를 쓸 때 endpointing/VAD 튜닝은 필수지만, 지나치게 공격적으로 잡으면 말 끊김이 늘고 보수적으로 잡으면 EOT가 늘어 대화가 느려집니다. Deepgram은 endpointing(침묵 ms) 같은 파라미터로 “언제 최종 확정(speech_final)”할지 제어할 수 있음을 문서화합니다. ([developers.deepgram.com](https://developers.deepgram.com/docs/endpointing?utm_source=openai))  

2) **Barge-in은 “오디오 재생 중단”만으론 부족**  
사용자가 끼어들 때:
- 클라이언트 재생(audio element/AudioTrack) 중단
- 동시에 세션에도 “이전 응답을 중단/무시”시키는 제어 신호(또는 새 turn 시작)를 넣어야, 모델이 계속 말하려는 관성을 끊을 수 있습니다.  
(이 부분은 SDK/이벤트 스키마에 따라 구현이 달라, 벤더별 이벤트를 꼭 확인하세요.)

3) **Tool call 왕복이 ‘진짜 병목’이 되는 경우가 많다**  
현업 피드백으로는 STT→LLM보다 **tool call(검색/CRM/예약 등)** 왕복이 대화의 정적을 만든다는 이야기가 자주 나옵니다. 즉, 모델이 아무리 빨라도 외부 API가 600~800ms면 체감이 망가집니다. (해결: 캐시, speculative execution, 미리보기 응답, 비동기 업데이트)

4) **WebSocket vs WebRTC는 “환경”으로 결정**
- 브라우저/모바일: WebRTC 선호(네트워크 적응 + 미디어 파이프라인 자연스러움) ([platform.openai.com](https://platform.openai.com/docs/guides/realtime-webrtc?utm_source=openai))  
- 서버-서버/콜센터 백엔드: WebSocket이 디버깅/관측성이 좋을 때가 많음  
- 전화망(PSTN/VoIP): SIP 연동이 핵심이며, OpenAI도 SIP를 Realtime 전송으로 지원한다고 명시합니다. ([developers.openai.com](https://developers.openai.com/api/docs/models/gpt-realtime?utm_source=openai))  

5) **연구 트렌드: “Listen-Think-Speak”의 스트리밍 사고**
2026년 초 arXiv에서는 음성 에이전트의 딜레마(End-to-end는 reasoning 약함 vs cascaded는 지연 큼)를 지적하며, 사람처럼 “듣는 중에도 생각을 시작”하는 incremental reasoning/triggering 프레임워크가 제안됩니다. 실무적으로는 “부분 의미가 확정되는 순간부터 tool prefetch” 같은 설계로 이어집니다. ([arxiv.org](https://arxiv.org/abs/2601.19952?utm_source=openai))  

---

## 🚀 마무리
2026년 4월의 결론은 단순합니다.

- “실시간”의 본질은 **EOT + TTFS + barge-in + tool latency**를 한 덩어리로 최적화하는 것
- **Speech-to-Speech Realtime**은 아키텍처를 단순화해서 지연과 실패 포인트를 줄이는 강력한 선택지 (WebRTC/WebSocket/SIP) ([developers.openai.com](https://developers.openai.com/api/docs/models/gpt-realtime?utm_source=openai))  
- 그래도 cascaded가 유리한 경우(커스텀 STT, 특정 도메인 용어, 강한 observability, 비용 최적화)는 여전히 많고, 이때는 endpointing/VAD와 버퍼링이 승부처 ([developers.deepgram.com](https://developers.deepgram.com/docs/endpointing?utm_source=openai))  

다음 학습으로는:
1) WebRTC 미디어 파이프라인(오디오 track, jitter buffer, echo cancellation)  
2) turn-taking 설계(semantic EOT, partial hypothesis, barge-in state machine)  
3) tool call을 대화 흐름에 녹이는 패턴(캐시/프리페치/낙관적 응답)  
을 추천합니다.

원하면, 위 예제를 기반으로 **(A) 자막(Streaming transcript) UI**, **(B) function calling으로 예약/검색 붙이기**, **(C) SIP 전화 수신 플로우** 중 하나로 확장한 “완성형 튜토리얼”도 이어서 작성해드릴게요.