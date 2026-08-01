---
title: "2026년 8월 기준: Modal·Runpod·AWS Lambda로 “서버리스 LLM”을 굴릴 때 cold start를 이기는 실전 설계"
date: 2026-08-01 03:37:39 +0900
categories: [Infra, Serverless]
tags: [infra, serverless, trend, 2026-08]
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
서버리스 LLM 배포가 해결하는 문제는 명확합니다. **트래픽이 들쭉날쭉한 추론(inference)**을 위해 GPU/서버를 상시 켜두는 “idle tax”를 없애고, 요청이 올 때만 자동 확장(scale-out)하는 것입니다. 문제는 반대로 **cold start가 사용자 경험의 상한을 결정**한다는 점입니다. 컨테이너 pull → CUDA 초기화 → weights 로드(수~수십 GB) → 엔진(vLLM 등) 부팅 → 첫 토큰(TTFT)까지가 전부 cold start 경로에 얹히면, “서버리스”는 곧 “느린 서비스”가 됩니다.

언제 쓰면 좋나
- **버스트 트래픽 / 간헐적 호출**(예: 사내 툴, 특정 시간대만 몰리는 기능, 배치성 요약/분류, 이벤트 기반 파이프라인)
- **모델/버전이 자주 바뀌는** 제품(Blue/Green, A/B, 빠른 실험)

언제 쓰면 안 되나
- **항상 높은 QPS**가 유지되는 실시간 서비스: 결국 warm capacity가 필요해져 “서버리스 프리미엄”만 지불할 수 있음
- **초저지연(수백 ms 단위 TTFT) SLA**가 하드하게 필요한 채팅 UX: cold start는 설계로 줄여도 “0”이 되지 않음(플랫폼/하드웨어 레벨 최적화가 필요)

이번 글은 2026년 8월 시점에서 많이 쓰는 3축(Modal, Runpod Serverless, AWS Lambda)을 기준으로, **cold start를 줄이기 위한 구조적 레버**와 “내 프로젝트에 어떤 선택이 맞는지” 판단 기준을 정리합니다. (Runpod의 FlashBoot/Active worker, Modal의 GPU Memory Snapshot, Lambda의 response streaming 등을 중심으로 다룹니다.) ([runpod.io](https://www.runpod.io/blog/whats-new-in-runpod-serverless-faster-cold-starts-batch-inference-and-no-docker-deploys?utm_source=openai))

---

## 🔧 핵심 개념
### 1) serverless LLM cold start를 쪼개서 봐야 하는 이유
LLM 서버리스에서 cold start는 단일 시간이 아니라 **단계의 합**입니다.

1. **Provisioning**: 워커/컨테이너가 잡히는 시간(스케줄링, GPU 할당)
2. **Image 준비**: 컨테이너 이미지 pull/마운트(레이어 캐시 유무 영향)
3. **Runtime init**: CUDA context/라이브러리 초기화
4. **Weights 로드**: HF/오브젝트 스토리지에서 로드 + 디스크/VRAM 적재
5. **엔진 준비**: vLLM/SGLang 초기화, KV cache/compile artifacts, CUDA graph 등
6. **첫 요청 워밍업**: 실제 request를 넣어 커널/캐시가 안정화

대부분 팀이 (4)와 (5)에서 무너집니다. 최근 연구들도 “모델 전달/검증/캐싱”과 “초기화 단계의 오버랩/사전 준비”가 비용과 지연을 좌우한다고 지적합니다. ([arxiv.org](https://arxiv.org/abs/2607.16596?utm_source=openai))

### 2) Modal: “프로세스를 스냅샷으로 굳혀서 깨운다”
Modal은 **Memory Snapshot(특히 GPU Memory Snapshot)**을 핵심 무기로 가져갑니다. 아이디어는 간단합니다.

- cold start 경로에서 가장 비싼 “vLLM 부팅 + 모델 로드 + 워밍업”을
- `@modal.enter(snap=True)` 같은 훅에서 **미리 수행**
- 그 상태를 스냅샷으로 저장했다가, 요청 시 “wake”로 복원

공식 예제는 vLLM을 띄우고 준비될 때까지 기다린 뒤 warmup을 수행하고 sleep한 다음, 그 상태를 스냅샷으로 남겨 cold start를 줄이는 흐름을 보여줍니다. ([modal.com](https://modal.com/docs/examples/lfm_snapshot?utm_source=openai))  
즉 Modal 쪽 최적화는 “컨테이너를 빨리 띄운다”가 아니라 **LLM 서버 프로세스의 ‘이미 준비된 메모리 상태’로 점프**하는 접근입니다.

### 3) Runpod Serverless: “FlashBoot + 워커 타입(Active/Flex)로 cold start를 돈으로 제어”
Runpod은 2026년 7월 기준으로 **FlashBoot**를 cold-start 최적화 레이어로 강조하고, “pre-warmed workers”로 **sub-200ms 응답**을 내세웁니다. ([runpod.io](https://www.runpod.io/product/serverless?utm_source=openai))  
또한 2026년 6월 pricing 업데이트에서 **Active worker / Flex** 같은 개념으로 “항상 켜둘 최소 워커” vs “완전 scale-to-zero”를 분리해 비용/지연을 트레이드오프 하도록 유도합니다. ([runpod.io](https://www.runpod.io/blog/serverless-pricing-update?utm_source=openai))

정리하면 Runpod의 레버는:
- 완전 서버리스(0→N)로 비용 최소화(대신 cold start)
- Active workers로 “항상 따뜻한” 워커를 일정 수 유지(대신 비용)
- FlashBoot로 cold start 자체를 압축(플랫폼 레벨)

### 4) AWS Lambda: GPU 추론 “직접”보다는 제어 plane / streaming에 강점
AWS Lambda는 **GPU 서버리스 추론** 자체가 강점인 포지션이 아닙니다(실제 GPU 추론은 보통 SageMaker/EC2/ECS류로 가는 편). 다만 Lambda는:
- **response streaming**(Function URL 또는 InvokeWithResponseStream)으로 최대 200MB까지 스트리밍 응답 지원 ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))
- 이벤트 기반 glue(큐/스케줄러/라우팅)로 “cold start를 사용자에게 숨기는” 아키텍처를 만들기 쉬움
- 컨테이너 이미지 cold start 최적화 연구/기능(예: SnapStart 계열, 이미지 로딩 최적화)들이 축적 ([assets.amazon.science](https://assets.amazon.science/25/06/d2e5ea9c411c9e4d366aa2fbbca5/on-demand-container-loading-in-aws-lambda.pdf?utm_source=openai))

그래서 “LLM을 Lambda에서 돌린다”가 아니라, 실전에서는 **Lambda를 프론트/오케스트레이터로 두고 GPU inference는 Modal/Runpod(또는 SageMaker 등)로 분리**하는 패턴이 더 현실적입니다.

---

## 💻 실전 코드
아래 코드는 “실시간 채팅”이 아니라, 실제 서비스에서 자주 있는 **서버리스 LLM 추론 엔드포인트를 운영하면서 cold start를 비용으로 제어**하는 시나리오입니다.

- **GPU inference**: Runpod Serverless endpoint (scale-to-zero + 필요 시 Active worker)
- **API**: AWS Lambda(Function URL)에서 요청 정규화/인증/레이트리밋/스트리밍 프록시
- **핵심**: Lambda는 “빠르게 응답을 시작”하고, GPU 쪽이 느릴 때는 **fallback 메시지/재시도 전략**으로 UX를 지킨다.

### 1) 인프라 전제
- Runpod에서 Serverless endpoint 생성(예: vLLM 템플릿 기반)
  - cold start를 줄이고 싶으면 FlashBoot/Active worker 옵션을 검토 ([runpod.io](https://www.runpod.io/blog/whats-new-in-runpod-serverless-faster-cold-starts-batch-inference-and-no-docker-deploys?utm_source=openai))
- AWS Lambda Function URL 활성화 + response streaming 사용 ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))
- 환경변수
  - `RUNPOD_ENDPOINT`: Runpod endpoint URL
  - `RUNPOD_API_KEY`: 인증 토큰

### 2) Lambda (TypeScript) — 스트리밍 프록시 + cold start 완충
```typescript
// runtime: nodejs20.x
// package: "undici" 사용 (Node 18+ 내장 fetch도 가능하지만 스트리밍 제어를 명시적으로 하기 위해 undici 예시)
// npm i undici

import { request } from "undici";
import type { APIGatewayProxyHandlerV2 } from "aws-lambda";

// Runpod serverless는 일반적으로 "요청 -> 작업 실행 -> 결과" 형태가 많아
// 완전 토큰 단위 streaming이 아니라도, Lambda에서 "진행상황/타임아웃"을 스트리밍으로 처리하면 UX가 좋아짐.
export const handler: APIGatewayProxyHandlerV2 = async (event) => {
  const endpoint = process.env.RUNPOD_ENDPOINT!;
  const apiKey = process.env.RUNPOD_API_KEY!;

  const body = event.body ? JSON.parse(event.body) : {};
  const prompt: string = body.prompt;
  const maxTokens: number = body.max_tokens ?? 512;

  if (!prompt || typeof prompt !== "string") {
    return { statusCode: 400, body: "prompt is required" };
  }

  // Lambda response streaming을 쓰면 더 좋지만,
  // 여기서는 Function URL + "chunked" 전송을 흉내내기 위해
  // 단순화된 형태로 예시를 제시한다.
  // (실제 production에서는 AWS 공식 streaming API를 사용) ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))

  const payload = {
    input: {
      prompt,
      max_tokens: maxTokens,
      temperature: body.temperature ?? 0.2,
    },
  };

  // cold start 방어 전략:
  // 1) 짧은 타임아웃으로 "서버가 바로 준비됐는지" 확인
  // 2) 실패/지연이면 202 Accepted + job id 패턴으로 전환(폴링/웹훅)
  // 여기서는 1)만 간단히 구현
  const t0 = Date.now();
  try {
    const res = await request(endpoint, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(payload),
      // undici는 별도의 timeout 옵션을 두거나 AbortController를 쓰는 게 일반적
    });

    const text = await res.body.text();
    const latencyMs = Date.now() - t0;

    // 예상 출력(예):
    // { "output": "...", "usage": {...}, ... }
    return {
      statusCode: 200,
      headers: {
        "content-type": "application/json",
        "x-upstream-latency-ms": String(latencyMs),
      },
      body: text,
    };
  } catch (e: any) {
    // cold start / 용량 부족 / 워커 준비 실패 등을 한 번에 UX로 흡수
    return {
      statusCode: 503,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        error: "Upstream GPU endpoint not ready (cold start or capacity).",
        retry_after_seconds: 3,
        hint:
          "If this happens frequently, consider Active workers (Runpod) or Memory Snapshots (Modal).",
      }),
    };
  }
};
```

### 3) 확장: “동기 응답”을 고집하지 말고 202 + 폴링/웹훅으로 바꾸기
실무적으로 cold start를 “없애는” 것보다, **사용자 요청 path에서 분리**하는 게 더 강력합니다.

- `/generate`는 202로 job id를 즉시 반환
- 백엔드에서 GPU 워커가 완료하면 Redis/S3에 결과 저장
- `/result/{jobId}` 폴링 또는 WebSocket/SSE로 푸시

이 패턴은 Runpod/Modal 어디든 적용되고, 특히 트래픽이 스파이크 칠 때 “사용자가 기다리는 시간”을 제어할 수 있습니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (바로 효과 나는 것)
1) **cold start 예산을 “비용으로 수치화”**
- Runpod은 Active worker로 “따뜻한 최소 용량”을 두는 순간, cold start가 줄어드는 대신 비용이 고정비로 바뀝니다. 2026년 pricing에서도 워커 타입을 분리해 이 트레이드오프를 노출합니다. ([runpod.io](https://www.runpod.io/blog/serverless-pricing-update?utm_source=openai))  
- 결론: “한 달에 몇 번 느린 첫 요청을 허용할 것인가”를 SLA로 정의하고, 그 SLA를 만족하는 최소 warm capacity를 찾으세요.

2) **모델/엔진 초기화를 스냅샷/프리웜으로 빼기**
- Modal은 vLLM 서버를 띄워 warmup 후 스냅샷으로 저장하는 패턴을 문서/예제로 밀고 있습니다. ([modal.com](https://modal.com/docs/examples/lfm_snapshot?utm_source=openai))  
- 스냅샷이 가능한 구조(서버 프로세스가 long-lived, 초기화 훅 분리)가 되면 “weights 로드 + 엔진 준비”가 hot path에서 사라집니다.

3) **모델 전달(artifact) 전략을 별도 설계**
- 최근 연구는 “수십~수백 GB 모델 전달”이 scale-to-zero의 경제성을 지배한다고 지적합니다. 단순히 S3/HF에서 매번 받는 구조는 결국 cold start를 키웁니다. ([arxiv.org](https://arxiv.org/abs/2607.16596?utm_source=openai))  
- 실전 체크리스트: 이미지 레이어 캐시, 로컬 볼륨/스토리지, 모델 digest pinning, 검증 비용(해시)까지 포함.

### 흔한 함정 / 안티패턴
- **“Lambda에서 LLM inference를 직접”**: GPU가 필요하면 결국 다른 서비스가 필요하고, Lambda는 오케스트레이션/스트리밍에 집중하는 편이 낫습니다. (Lambda streaming은 강점) ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))
- **동기 API만 고집**: cold start는 “가끔 반드시 발생”합니다. 동기 API만 있으면 그 순간이 곧 장애가 됩니다.
- **scale-to-zero + 대형 모델 + 엄격한 p95**를 동시에 요구: 셋 중 하나는 포기해야 합니다(대부분 “scale-to-zero”를 부분 포기하고 warm pool을 둠).

### 비용/성능/안정성 트레이드오프 한 줄 요약
- Modal: 스냅샷으로 **지연을 기술적으로 줄이는** 쪽(대신 플랫폼 SDK 패턴에 맞춰야 함) ([modal.com](https://modal.com/docs/guide/memory-snapshots?utm_source=openai))
- Runpod: 워커 타입/FlashBoot로 **지연을 돈과 설정으로 제어**하는 쪽(대신 capacity/운영 관점 고려) ([runpod.io](https://www.runpod.io/blog/whats-new-in-runpod-serverless-faster-cold-starts-batch-inference-and-no-docker-deploys?utm_source=openai))
- AWS Lambda: GPU 추론 엔진이라기보다 **제어 plane + streaming + 이벤트 구동**으로 cold start를 “사용자 경로에서 분리”하는 쪽 ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))

---

## 🚀 마무리
핵심은 “서버리스 LLM = 자동확장”이 아니라, **cold start를 어떤 레이어에서 해결할지**입니다.

- **앱 레벨**: 202 + 폴링/웹훅, 큐 기반 비동기화로 사용자의 기다림을 설계로 흡수
- **플랫폼 레벨**: Runpod의 FlashBoot/Active worker처럼 warm capacity를 옵션으로 두고 비용으로 제어 ([runpod.io](https://www.runpod.io/blog/whats-new-in-runpod-serverless-faster-cold-starts-batch-inference-and-no-docker-deploys?utm_source=openai))
- **런타임 레벨**: Modal의 GPU Memory Snapshot처럼 “준비된 프로세스 상태”를 복원해 초기화를 hot path에서 제거 ([modal.com](https://modal.com/docs/guide/memory-snapshots?utm_source=openai))

도입 판단 기준(실무용)
1) 트래픽 패턴이 버스트인가, 상시 고QPS인가?
2) p95 TTFT 요구가 “절대”인가, “대부분 빠르면” 되는가?
3) 모델 크기/엔진(vLLM 등) 초기화가 병목인가?
4) 팀이 플랫폼 SDK/제약(Modal 스타일)을 받아들일 수 있는가, 아니면 컨테이너 중심(Runpod)이 편한가?

다음 학습 추천
- Modal의 Memory Snapshots + vLLM snapshot 예제 흐름을 그대로 따라가며 “내 모델”로 바꿔보기 ([modal.com](https://modal.com/docs/examples/lfm_snapshot?utm_source=openai))
- Runpod Serverless의 FlashBoot/Active worker 옵션을 켠 경우와 끈 경우를 A/B로 측정해 “warm capacity 1대의 가치”를 수치화 ([runpod.io](https://www.runpod.io/blog/whats-new-in-runpod-serverless-faster-cold-starts-batch-inference-and-no-docker-deploys?utm_source=openai))
- AWS Lambda response streaming을 실제로 붙여, GPU cold start 시에도 사용자에게 즉시 진행 상태를 보여주는 UX를 설계 ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))