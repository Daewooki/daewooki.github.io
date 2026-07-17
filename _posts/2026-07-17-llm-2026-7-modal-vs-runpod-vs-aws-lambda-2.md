---
title: "서버리스 LLM 배포 2026년 7월판: Modal vs Runpod vs AWS Lambda, 그리고 “cold start를 설계로 이기는” 방법"
date: 2026-07-17 03:25:00 +0900
categories: [Infra, Serverless]
tags: [infra, serverless, trend, 2026-07]
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
서버리스 LLM 배포가 해결하는 문제는 명확합니다: **GPU/서빙 인프라를 상시 운영하지 않고도**(=scale-to-zero), 트래픽에 맞춰 자동 확장하면서 **LLM inference endpoint를 운영**하는 것. 하지만 2026년에도 여전히 가장 큰 적은 **cold start**입니다. 특히 오픈소스 LLM은 “컨테이너 부팅 + CUDA init + 수~수십 GB weights 로딩 + 런타임 컴파일/그래프 캡처”가 겹치며 p95가 폭발합니다.

- **언제 쓰면 좋은가**
  - 트래픽이 들쑥날쑥하고(스파이크/저트래픽), **항상 켜진 GPU 비용이 낭비**인 서비스
  - PoC→프로덕션 초입에서 **인프라 운영 복잡도**를 낮추고 싶은 팀
  - 모델/버전이 자주 바뀌며 **배포 속도**가 중요한 경우
- **언제 쓰면 안 되는가**
  - p95 TTFT(Time To First Token) 목표가 빡빡한 실시간 서비스(예: 음성 대화, 초저지연 에이전트)인데 트래픽이 꾸준해 “warm 유지”가 더 싸게 먹히는 경우
  - 커스텀 CUDA ext, 드라이버/커널 튜닝, 멀티노드 텐서/파이프라인 병렬 등 **플랫폼 추상화가 방해**가 되는 경우
  - “규모가 이미 커서” 어차피 SRE/플랫폼을 운영하고 있고, **K8s+고정 GPU 풀**이 더 예측 가능한 경우

---

## 🔧 핵심 개념
### 1) cold start는 “한 덩어리”가 아니다: 단계별 병목을 분리하라
LLM 서버리스 cold start는 보통 다음이 합쳐진 값입니다.

1. **Scheduling/Provisioning**: 빈 GPU 노드 할당, 워커 생성  
2. **Image pull / env 준비**: 컨테이너 이미지/의존성  
3. **Runtime init**: Python/uvicorn, CUDA context, NCCL 등  
4. **Weights 로딩**: HF 다운로드/디스크→CPU→GPU 전송  
5. **Warm-up**: KV cache/커널 컴파일, 그래프 캡처, 첫 요청 프롬프트 처리  
6. **Streaming 시작 지연(TTFT)**

플랫폼별로 “어느 단계까지를 플랫폼이 흡수해 주는지”가 다릅니다. 예를 들어 Modal은 **memory snapshot / GPU memory snapshot**으로 (3~5)의 일부를 통째로 스킵하는 방향을 강하게 밀고 있습니다. ([modal.com](https://modal.com/docs/guide/cold-start?utm_source=openai))  
Runpod은 **FlashBoot**라는 레이어로 “대기 풀(pre-warmed workers)”을 운영해 (1~2)를 거의 없애는 쪽을 강조합니다. ([runpod.io](https://www.runpod.io/product/serverless?utm_source=openai))  
AWS Lambda는 GPU inference 자체보다는(기본 Lambda는 GPU가 없음) **SnapStart로 런타임 초기화 비용을 줄이고**, **response streaming**으로 체감 TTFT를 낮추는 쪽이 포인트입니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html?utm_source=openai))  

### 2) Modal: “스냅샷으로 부팅을 점프한다”
Modal의 핵심은 **함수 단위 서버리스**에 가깝지만, LLM은 결국 “서버 프로세스(vLLM 등)”를 띄워야 합니다. Modal은:
- `@modal.enter(snap=True)` 구간에서 **모델 로딩 + 서버 준비 + 워밍업**까지 해놓고
- 그 상태를 **memory snapshot**(필요시 GPU snapshot)으로 저장해
- 다음 부팅에서 그 지점으로 **restore**합니다. ([modal.com](https://modal.com/docs/examples/lfm_snapshot?utm_source=openai))  

결과적으로 “첫 요청 전에 했어야 할 일”을 **스냅샷 생성 시점으로 당겨** cold start를 줄입니다. (단, 스냅샷 만들 때의 비용/시간과 스냅샷 유효성, 스케줄링 제약은 트레이드오프)

### 3) Runpod Serverless: “풀링 + FlashBoot + 워커 설계가 전부다”
Runpod은 2026년 6~7월 기준으로 FlashBoot를 전면에 내세우며 **sub-200ms cold starts(활성 엔드포인트/사전 준비 조건 하)**를 주장합니다. ([runpod.io](https://www.runpod.io/product/serverless?utm_source=openai))  
하지만 실무적으로 중요한 포인트는: **FlashBoot가 ‘당신 워커의 warm 상태’를 유지해 주려면, 모델 로딩을 “올바른 시점”에 해둬야** 한다는 겁니다. 모델을 핸들러 내부(요청 경로)에서 매번 lazy-load하면, 부팅이 빨라도 “첫 요청이 느린” 문제가 그대로 남습니다(커뮤니티/분석 글에서도 반복). ([sergeyshmakov.github.io](https://sergeyshmakov.github.io/mineru-runpod/blog/2026-05-26-runpod-flashboot-mechanism-investigation/?utm_source=openai))  

또 2026-06-25 업데이트로 **batch inference** 및 배포 경험 개선(Flash SDK/노-도커 플로우 등)을 강조하고 있습니다. ([runpod.io](https://www.runpod.io/blog/whats-new-in-runpod-serverless-faster-cold-starts-batch-inference-and-no-docker-deploys?utm_source=openai))  

### 4) AWS Lambda: LLM “호스팅”이 아니라 LLM “오케스트레이션”에 강하다
AWS Lambda는:
- Java 계열의 cold start를 SnapStart로 줄이는 공식 메커니즘이 있고 ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html?utm_source=openai))  
- 채팅 UX에서는 **response streaming**으로 “완료까지 시간”이 아니라 **TTFT 체감**을 줄일 수 있습니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))  

다만 오픈소스 LLM을 GPU로 직접 띄우는 “서버리스 GPU” 영역은 Modal/Runpod 같은 전문 플랫폼이 주 무대입니다. 그래서 Lambda는 보통:
- (A) **프롬프트 라우팅/세이프티/캐시/툴콜 오케스트레이션**
- (B) Modal/Runpod/기타 inference endpoint 호출
을 담당시키는 쪽이 설계상 깔끔합니다.

---

## 💻 실전 코드
현실적인 시나리오: **프로덕션 API는 AWS(CloudFront/API Gateway + Lambda)로 받되**, 모델 서빙은 **Runpod Serverless(vLLM worker)** 또는 **Modal(vLLM + snapshot)** 로 빼고, 공통으로 **cold start를 “요청 경로 밖”으로 밀어내는** 구조를 만듭니다.

### 단계 1) (공통) Lambda에서 “스트리밍 프록시 + 캐시 키”로 UX 방어
- Lambda는 **SSE/스트리밍**으로 클라이언트에 토큰을 흘려보내고
- 백엔드는 Runpod/Modal endpoint를 호출
- 같은 프롬프트/컨텍스트는 캐시(예: DynamoDB/Redis)로 우회

```typescript
// runtime: nodejs20.x
// package.json: undici ^6
import { request } from "undici";
import crypto from "crypto";

type ChatReq = { model: string; messages: { role: string; content: string }[] };

const BACKEND_URL = process.env.INFERENCE_URL!; // Runpod/Modal endpoint
const BACKEND_KEY = process.env.INFERENCE_KEY!;

function cacheKey(body: ChatReq) {
  return crypto.createHash("sha256").update(JSON.stringify(body)).digest("hex");
}

// (예시) 매우 단순화: 실제로는 DynamoDB/ElastiCache 등을 붙이세요.
const inMemoryCache = new Map<string, string>();

export const handler = awslambda.streamifyResponse(
  async (event: any, responseStream: any) => {
    const body: ChatReq = JSON.parse(event.body ?? "{}");
    const key = cacheKey(body);

    responseStream.setContentType("text/event-stream; charset=utf-8");
    responseStream.write(`event: meta\ndata: ${JSON.stringify({ cache: false })}\n\n`);

    if (inMemoryCache.has(key)) {
      responseStream.write(`event: token\ndata: ${JSON.stringify({ t: inMemoryCache.get(key) })}\n\n`);
      responseStream.write(`event: done\ndata: {}\n\n`);
      responseStream.end();
      return;
    }

    // 백엔드(Modal/Runpod)로 스트리밍 요청 (백엔드가 SSE를 지원한다고 가정)
    const upstream = await request(`${BACKEND_URL}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "authorization": `Bearer ${BACKEND_KEY}`,
        "content-type": "application/json",
        "accept": "text/event-stream",
      },
      body: JSON.stringify({ ...body, stream: true }),
    });

    let full = "";
    for await (const chunk of upstream.body) {
      const s = chunk.toString("utf8");
      // 프로덕션에서는 SSE 프레이밍 파싱을 제대로 하세요.
      full += s;
      responseStream.write(s);
    }

    inMemoryCache.set(key, full);
    responseStream.write(`event: done\ndata: {}\n\n`);
    responseStream.end();
  }
);
```

예상 출력(클라이언트 관점):
- 첫 바이트가 빨리 오고(스트리밍), 백엔드 cold start가 있어도 “멈춘 화면”이 아니라 진행 상황을 제공
- 동일 요청 재시도는 캐시로 즉시 응답

> Lambda response streaming은 공식 기능이며, 스트리밍 구간/언어별 제약이 있습니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))  

### 단계 2A) Runpod Serverless 워커: “모델 로딩을 핸들러 밖으로”
핵심: **FlashBoot가 의미 있으려면** 모델 init을 “프로세스 부팅 시점”으로 당겨야 합니다(요청 핸들러에서 lazy-load 금지). ([sergeyshmakov.github.io](https://sergeyshmakov.github.io/mineru-runpod/blog/2026-05-26-runpod-flashboot-mechanism-investigation/?utm_source=openai))  

```python
# runpod_worker.py
# requirements.txt: runpod, vllm, transformers, torch (worker 이미지에 따라 다름)

import os
import runpod
from vllm import LLM, SamplingParams

MODEL_ID = os.environ.get("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")

# ✅ 중요: 부팅 시점에 weights 로딩/초기화
llm = LLM(
    model=MODEL_ID,
    trust_remote_code=True,
    # vLLM 튜닝은 엔드포인트 환경변수/플래그로 관리하는 편이 안전
)

def handler(job):
    inp = job["input"]
    prompt = inp["prompt"]
    max_tokens = int(inp.get("max_tokens", 256))

    params = SamplingParams(temperature=0.2, max_tokens=max_tokens)
    out = llm.generate([prompt], params)[0].outputs[0].text
    return {"text": out}

runpod.serverless.start({"handler": handler})
```

이렇게 하면 “첫 요청 = 모델 로딩”이 아니라, **플랫폼이 재사용 가능한 warm 상태**를 만들 여지가 생깁니다(FlashBoot/워커 재활용의 효과가 커짐). ([runpod.io](https://www.runpod.io/blog/serverless-gpu-cold-starts-flashboot?utm_source=openai))  

### 단계 2B) Modal: snapshot 지점에 vLLM을 ‘준비 완료’ 상태로 만들기
Modal은 문서 예제에서 `@modal.enter(snap=True)`로 vLLM을 띄우고 준비된 순간에 스냅샷을 찍는 패턴을 제시합니다. ([modal.com](https://modal.com/docs/examples/lfm_snapshot?utm_source=openai))  

(지면상 전체 예제는 생략하지만) 여러분이 가져가야 할 구현 포인트는:
- **스냅샷 전**: 모델 다운로드/로딩, tokenizer/engine 준비, “짧은 더미 요청”으로 워밍업
- **스냅샷 후**: HTTP 요청을 받아 바로 generate 경로로 진입

---

## ⚡ 실전 팁 & 함정
### Best Practice (프로젝트 적용 기준으로)
1) **cold start를 TTFT와 분리해 측정하라**  
   “요청부터 첫 토큰”과 “요청부터 완료”를 나누고, p50/p95/p99를 봐야 합니다. Lambda 스트리밍은 완료시간을 줄이지 않아도 **TTFT 체감**을 개선합니다. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html?utm_source=openai))  

2) **모델 로딩 위치는 플랫폼 종속 최적화 포인트다**
- Runpod: 모델 로딩을 요청 경로에 두면 FlashBoot 이점이 약해질 수 있습니다. ([sergeyshmakov.github.io](https://sergeyshmakov.github.io/mineru-runpod/blog/2026-05-26-runpod-flashboot-mechanism-investigation/?utm_source=openai))  
- Modal: 스냅샷에 포함될 수 있도록 “스냅샷 전 훅”에서 준비를 끝내야 합니다. ([modal.com](https://modal.com/docs/guide/memory-snapshots?utm_source=openai))  

3) **scale-to-zero의 비용 절감 vs warm 유지 비용을 수치로 결정**
- Modal은 `scaledown_window` 같은 라이프사이클 설정으로 cold start 확률을 줄이되, idle 비용이 늘어납니다. ([modal.com](https://modal.com/docs/guide/cold-start?utm_source=openai))  
- Runpod도 “항상 0으로 떨어뜨릴지” vs “일정 시간 warm”의 과금/지연 트레이드오프가 생깁니다(플랫폼 정책/엔드포인트 설정에 따라 다름).

### 흔한 함정/안티패턴
- **“서버리스니까” 매 요청마다 모델/어댑터를 동적으로 로딩**  
  LoRA/adapter를 요청마다 바꾸면 GPU 메모리 단편화/로딩 폭탄이 옵니다(연구/경험적으로도 반복되는 패턴). ([arxiv.org](https://arxiv.org/abs/2512.20210?utm_source=openai))  
- **cold start 회피를 위해 무작정 ping/cron keep-alive**  
  비용 예측이 깨지고, 장애 시 재시작 폭풍(thundering herd)을 부릅니다. 대신 “warm pool/스냅샷/오토 프로비전”처럼 플랫폼 기능 또는 명시적 min capacity로 관리하는 편이 낫습니다. ([runpod.io](https://www.runpod.io/blog/serverless-gpu-cold-starts-flashboot?utm_source=openai))  
- **“sub-200ms” 같은 마케팅 수치만 보고 모델 크기/초기화 비용을 무시**  
  cold start 최적화가 있어도 **모델 사이즈가 커질수록** 현실은 달라집니다(결국 weights 로딩/초기화가 지배). ([runpod.io](https://www.runpod.io/articles/guides/llm-inference-first-principles?utm_source=openai))  

### 비용/성능/안정성 트레이드오프(의사결정 체크리스트)
- 트래픽이 **지속적**이면: scale-to-zero보다 **고정 풀 + 오토스케일**이 p95/비용 모두 유리할 수 있음
- 트래픽이 **버스트**면: Runpod(FlashBoot/warm pool) 또는 Modal(snapshot)이 운영 부담 대비 효과가 큼
- 운영 안정성: 멀티 프로바이더 “헤징”으로 p95를 낮추는 접근도 커뮤니티에서 논의됩니다(복잡도는 증가). ([reddit.com](https://www.reddit.com/r/MachineLearning/comments/1uvlb6h/gpuhedge_hedging_serverless_gpu_providers/?utm_source=openai))  

---

## 🚀 마무리
2026년 7월 기준, 서버리스 LLM 배포에서 cold start 대응은 “요령”이 아니라 **아키텍처 선택**입니다.

- **Modal**: 스냅샷(특히 GPU memory snapshot)을 중심으로 “초기화 단계를 점프”하는 전략. 워밍업을 스냅샷 생성 시점으로 당길 수 있는 워크로드에 강함. ([modal.com](https://modal.com/docs/examples/lfm_snapshot?utm_source=openai))  
- **Runpod**: FlashBoot/warm worker 풀로 “프로비저닝 지연을 제거”하는 전략. 대신 워커 코드에서 모델 로딩을 부팅 시점으로 당기는 등 **워커 설계가 성패를 좌우**. ([runpod.io](https://www.runpod.io/blog/serverless-gpu-cold-starts-flashboot?utm_source=openai))  
- **AWS Lambda**: GPU LLM 호스팅이라기보다 **스트리밍/오케스트레이션 계층**. SnapStart/response streaming으로 체감 지연을 줄이고, 실제 inference는 전문 플랫폼으로 위임하는 구성이 실무적으로 깔끔. ([docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html?utm_source=openai))  

다음 학습 추천:
- Modal cold start/memory snapshot 문서와 vLLM snapshot 예제를 그대로 따라 하며 “스냅샷 경계(무엇이 포함/제외되는지)”를 체득하기 ([modal.com](https://modal.com/docs/guide/cold-start?utm_source=openai))  
- Runpod FlashBoot의 전제조건(워커 부팅/로딩 위치, 사전 프로비전)을 체크리스트로 만들어 배포 파이프라인에 넣기 ([runpod.io](https://www.runpod.io/blog/serverless-gpu-cold-starts-flashboot?utm_source=openai))  
- cold start를 단계별로 쪼개서 측정/최적화하는 연구(서버리스 LLM cold start breakdown) 훑어보기 ([usenix.org](https://www.usenix.org/system/files/conference/nsdi26/nsdi26spring_lou_prepub.pdf?utm_source=openai))  

원하면, 당신의 전제(모델 크기, 동시성 목표, TTFT/p95 목표, 월 트래픽 패턴, 스트리밍 필요 여부)를 기준으로 **Modal/Runpod 중 어떤 구성이 더 싸고 빠를지**를 숫자 기반으로 비교하는 템플릿(측정 항목 + 대략 비용 모델)도 만들어 드릴게요.