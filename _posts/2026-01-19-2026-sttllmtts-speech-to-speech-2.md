---
title: "실시간 음성 에이전트 2026: “STT→LLM→TTS”를 넘어 Speech-to-Speech로 가는 설계와 구현"
description: "2026년 1월 기준, 음성 AI 제품에서 사용자가 체감하는 품질은 “정답률”보다 “대화감”이 더 크게 좌우합니다. 대화감은 결국 latency(지연), turn-taking(턴 교대), barge-in(끼어들기), 그리고 streaming(연속 처리) 4가지가 결정합니다."
date: 2026-01-19 02:28:24 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal]
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
2026년 1월 기준, 음성 AI 제품에서 사용자가 체감하는 품질은 “정답률”보다 “대화감”이 더 크게 좌우합니다. 대화감은 결국 **latency(지연)**, **turn-taking(턴 교대)**, **barge-in(끼어들기)**, 그리고 **streaming(연속 처리)** 4가지가 결정합니다.  
과거의 전형적인 파이프라인(STT→LLM→TTS)은 구성은 단순하지만, (1) 텍스트 경유로 감정/억양 정보가 손실되고, (2) 각 단계가 누적 지연을 만들며, (3) 사용자가 말 끊었을 때(cancel) 처리와 오디오 동기화가 매우 까다롭습니다. OpenAI는 이를 줄이기 위해 **Realtime API**로 persistent connection(WebRTC/WebSocket) 기반 **speech-to-speech**를 제공하고, 자동 interruption 처리까지 강조합니다.[^1]  
한편 Google은 Gemini Live API로 스트리밍 기반 실시간 대화(네이티브 오디오 출력 포함)를 가이드하며, 실시간 멀티모달/툴 연계를 전면에 둡니다.[^2]  
결론적으로 “실시간 음성 대화 구현”은 이제 모델 선택보다 **시스템 설계(네트워크+오디오+대화 상태 머신)**가 경쟁력의 핵심입니다.

---

## 🔧 핵심 개념
### 1) Realtime Voice Agent의 2가지 아키텍처
**A. Realtime Model(Speech-to-Speech)**
- 오디오 입력을 그대로 스트리밍하고, 모델이 오디오로 바로 응답
- 장점: latency 최적화, 자연스러운 prosody(억양/리듬), interruption 자동화
- 단점: “실시간 자막(interim transcript)”이 늦거나 없을 수 있음(UX 요구에 따라 별도 STT 필요)[^3]

**B. Pipeline(STT → LLM → TTS)**
- 장점: 제어 용이(스크립트 출력, 안전 필터링, 감사로그), 자막/검색/분석에 유리
- 단점: 단계별 지연 누적, barge-in 처리 복잡, 감정/비언어 신호 손실

실무에서는 흔히 **Hybrid**를 씁니다: “대화는 speech-to-speech로” 하되, 화면 자막/키워드 하이라이트/검색용으로 **별도 STT를 병렬**로 붙이는 방식입니다.[^3]

### 2) Latency를 쪼개서 관리하기 (측정 포인트)
실시간 음성에서 “체감”은 평균이 아니라 **P95/P99**가 지배합니다. 최소 아래를 분리 계측해야 합니다.
- mic capture → uplink
- server receive → first token/audio frame
- TTS onset(첫 음성 출력 시작)
- barge-in 발생 → playback stop 완료까지

TTS 연구/상용 모두 “초기 발화 지연(initial delay)”을 100ms 수준까지 끌어내리는 흐름이 강합니다(스트리밍 TTS).[^4]

### 3) Turn-taking과 Barge-in의 본질
- **turn-taking**: 사용자의 “끝남”을 얼마나 빨리/정확히 감지하느냐(endpointing)
- **barge-in**: 에이전트가 말하는 도중 사용자가 끼어들면, **출력 오디오를 즉시 중단**하고 새 입력에 맞춰 상태를 재정렬하는 능력

OpenAI Realtime는 “자동 interruption 처리”를 직접 언급합니다.[^1]  
하지만 자동이라고 해서 공짜는 아닙니다. 앱 레벨에서 **(1) 재생 중단, (2) 이미 발화한 문장과 새 의도 충돌 해결, (3) tool call 취소/재시도 정책**이 필요합니다.

---

## 💻 실전 코드
아래 예제는 **브라우저(WebRTC) ↔ OpenAI Realtime** 연결의 최소 골격입니다. 포인트는 2가지입니다.
1) 오디오는 WebRTC 트랙으로 자동 스트리밍/재생  
2) 제어 이벤트(메시지/함수 호출 등)는 DataChannel로 주고받기[^5]

```javascript
// client.js (Browser)
// 실행 전제: 서버에서 ephemeral token을 발급하는 /token 엔드포인트가 있어야 함.
// 주의: API key를 브라우저에 직접 넣지 마세요(반드시 ephemeral token 사용).

async function startRealtimeVoice() {
  // 1) Ephemeral token 발급 (서버에서 OpenAI로부터 짧은 수명 토큰 받아서 내려줌)
  const tokenResp = await fetch("/token");
  const { value: EPHEMERAL_KEY } = await tokenResp.json();

  // 2) WebRTC PeerConnection 생성
  const pc = new RTCPeerConnection();

  // 3) 원격 오디오 재생 엘리먼트
  const audioEl = document.createElement("audio");
  audioEl.autoplay = true;
  document.body.appendChild(audioEl);

  pc.ontrack = (e) => {
    // 모델이 내보내는 오디오가 track으로 들어옴
    audioEl.srcObject = e.streams[0];
  };

  // 4) 마이크 입력을 트랙으로 추가
  const ms = await navigator.mediaDevices.getUserMedia({ audio: true });
  pc.addTrack(ms.getTracks()[0], ms);

  // 5) 제어 이벤트용 DataChannel
  const dc = pc.createDataChannel("oai-events");
  dc.addEventListener("message", (e) => {
    const evt = JSON.parse(e.data);
    // 여기서 tool call 요청, partial status, session lifecycle 등을 처리
    console.log("server event:", evt);
  });

  // 6) SDP Offer/Answer 교환
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  // OpenAI Realtime create-call: SDP를 POST하고 SDP answer를 받음
  const sdpResp = await fetch("https://api.openai.com/v1/realtime/calls", {
    method: "POST",
    body: offer.sdp,
    headers: {
      Authorization: `Bearer ${EPHEMERAL_KEY}`,
      "Content-Type": "application/sdp",
    },
  });

  const answer = { type: "answer", sdp: await sdpResp.text() };
  await pc.setRemoteDescription(answer);

  // 7) 대화 시작용 이벤트(텍스트로 “시동” 걸기: 디버깅에 유용)
  // 실제 음성 대화는 이미 트랙으로 들어가지만, 시스템 프롬프트/역할 부여에 사용 가능
  dc.send(JSON.stringify({
    type: "conversation.item.create",
    item: {
      type: "message",
      role: "user",
      content: [{ type: "input_text", text: "이제부터 한국어로 짧게 답변해줘." }]
    }
  }));
}

startRealtimeVoice().catch(console.error);
```

이 코드만으로도 “말하면 바로 말로 답하는” 프로토타입은 됩니다. 이후 실전에서는 **tool calling**, **대화 메모리 절단(truncate)**, **로그/감사**, **취소 정책**을 붙이며 제품이 됩니다. (OpenAI는 production voice agent용 `gpt-realtime` 및 비용/컨텍스트 제어 개선을 발표했습니다.[^6])

---

## ⚡ 실전 팁
1) **자막 UX가 필요하면 STT를 병렬로**
- Realtime 모델은 입력 transcription이 늦게 오거나 interim이 부족할 수 있습니다. 화면에 실시간 자막/키워드 표시가 필요하면 별도 STT 스트림을 병렬로 운영하세요.[^3]  
- 이때 “자막 텍스트”는 UX용, “모델 입력 오디오”는 대화 품질용으로 분리하면 충돌이 줄어듭니다.

2) **Barge-in은 ‘오디오 stop’만이 아니다**
- 사용자가 끼어들면:
  - (a) 플레이어 즉시 stop
  - (b) 진행 중 tool call/워크플로우 취소(가능하면 idempotent)
  - (c) 이미 말한 내용과 새 요구가 상충할 때의 정책(“방금 말한 건 무시할까요?” 같은 repair 전략)
- 이 3개를 상태 머신으로 설계하세요. 즉흥 처리하면 꼭 레이스 컨디션이 납니다.

3) **비용/지연의 트레이드오프: 컨텍스트를 “요약”이 아니라 “절단”**
- 장시간 콜에서 전체 history를 계속 넣으면 지연·비용이 증가하고, 음성 모드가 텍스트로 새는 문제도 언급됩니다.[^3]  
- 요약(summarize)은 모델 품질에 의존하지만, 절단(truncate)은 결정적(deterministic)입니다. “최근 N턴만 유지 + 중요한 사실은 별도 구조화 메모리”가 운영이 쉽습니다.

4) **네트워크는 WebRTC가 정답인 경우가 많다**
- 브라우저/모바일에서 지연과 NAT traversal을 고려하면 WebSocket보다 WebRTC가 유리한 경우가 많습니다(오디오 트랙 전송/재생이 표준화). OpenAI도 WebRTC 가이드를 별도로 제공합니다.[^5]  
- 단, 엔터프라이즈 환경(방화벽)에서는 TURN 비용/품질도 함께 계산해야 합니다.

---

## 🚀 마무리
2026년의 실시간 음성 에이전트는 “STT/TTS 성능”만으로 승부가 나지 않습니다. **speech-to-speech(Realtme) 기반의 저지연 대화**, 그리고 **turn-taking·barge-in·컨텍스트 제어**를 시스템적으로 묶어내는 팀이 이깁니다. OpenAI의 Realtime API(WebRTC/WebSocket)와 Google의 Gemini Live API는 그 방향성을 분명히 보여줍니다.[^1]  

다음 학습으로는:
- (1) WebRTC audio pipeline(AGC/NS/AEC) 튜닝
- (2) 상태 머신 기반 barge-in/취소 설계
- (3) Hybrid(Realtime + 병렬 STT) 아키텍처의 observability(P95) 구축  
을 추천합니다.

[^1]: <https://openai.com/index/introducing-the-realtime-api/>
[^2]: <https://ai.google.dev/gemini-api/docs/live-guide>
[^3]: <https://docs.livekit.io/agents/integrations/realtime/>
[^4]: <https://arxiv.org/abs/2509.15969>
[^5]: <https://platform.openai.com/docs/guides/realtime-webrtc>
[^6]: <https://openai.com/index/introducing-gpt-realtime/>
