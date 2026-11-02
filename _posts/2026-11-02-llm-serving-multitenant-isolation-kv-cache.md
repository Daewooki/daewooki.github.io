---
title: "Cloudflare Workers AI GLM-5.3 KV cache 노출로 정리하는 LLM 서빙 멀티테넌시 격리 체크리스트"
description: "KV cache/세션/요청 경계가 무너지면 무엇이 새는지, SGLang 계열 서빙 스택에서의 방어·검증 체크리스트를 정리합니다."
date: 2026-11-02 14:03:54 +0900
categories: ["AI", "LLM Serving"]
tags: ["llm-serving", "kv-cache", "multitenancy", "sglang", "cloudflare", "security"]
render_with_liquid: false
---

2026-10-26 Cloudflare가 공개한 사건은 LLM 서빙에서 멀티테넌시 격리가 실제로 어떻게 깨지는지, 그리고 그 깨짐이 KV cache/전송/런타임 스케줄러의 어떤 지점에서 발생하는지까지 드러낸 사례입니다. 핵심은 “prefix caching 때문에 timing leak이 생길 수 있다” 수준이 아니라, 특정 조건에서 **cross-request로 타 테넌트의 컨텍스트 조각이 응답 본문에 섞여 나왔다**는 점입니다. Cloudflare는 영향 범위를 155개 응답으로 특정했고, 모두 681,280 tokens를 초과하는 매우 긴 프롬프트에서만 발생했다고 밝혔습니다.[^1][^2]

이 글은 다음 관점으로 정리합니다.

- KV cache/세션/요청 경계가 무너지면 실제로 무엇이 새는가
- cross-request 노출을 만드는 전형적인 설계 실수(특히 “거절(reject) 경로”와 “부분 성공(partial success)”)
- SGLang 계열(그리고 유사한 PD disaggregation/continuous batching 스택)에서 지금 당장 적용 가능한 방어: 키 스코핑, 메모리/캐시 파티셔닝, 재현/회귀 테스트

이미 KV cache 최적화(quantization, dtype, kernel) 자체는 예전에 여러 번 다뤘으니 반복하지 않습니다. 대신 격리 관점의 안전장치만 집중합니다.

- [GPU를 “갈아넣지 않고” LLM 서빙 성능 뽑는 법: Quantization + KV cache + 커널/런타임 최적화 실전 가이드](https://daewooki.github.io/posts/gpu-llm-2026-7-quantization-kv-cache-2/)
- [Kubernetes에서 LLM 서빙을 “GPU 오토스케일”로 굴리는 현실적인 방법: KEDA + (Queue Depth / KV Cache) + DCGM/NVML](https://daewooki.github.io/posts/2026-7-kubernetes-llm-gpu-keda-queue-dep-1/)

## 사건에서 확인된 사실: 어떤 조건에서 무엇이 새었나
Cloudflare가 밝힌 사실관계를 먼저 고정해 두는 편이 좋습니다. 여기서 조금이라도 흐릿해지면, 이후 체크리스트가 과잉 방어(비용 폭발) 또는 과소 방어(재발)로 갑니다.

- 대상: Cloudflare Workers AI의 `@cf/zai-org/glm-5.3` 모델[^1][^2]
- 노출 기간: 2026-08-27(모델 공개) ~ 2026-09-09(복구) 사이[^1][^2]
- 영향: “바로 직전에 같은 모델을 사용한 다른 고객의 요청 데이터”가 응답에 포함되는 형태의 cross-request 노출. 총 155개 응답[^1][^2]
- 트리거 조건: 681,280 tokens보다 긴 프롬프트에서만 발생[^1][^2]
- 직접 원인(겹친 두 요인):
  1) context window는 1,048,576 tokens로 설정했는데, prefill GPU의 KV cache pool은 681,280 tokens만 수용[^1][^2]
  2) SGLang disaggregated prefill/decode 모드에서 “pool을 초과하는 요청”이 reject 처리되면서도, 에러로 중단되지 않고 1-token placeholder로 prefill이 진행되고 KV가 decode로 전송되는 버그가 존재. decode는 “전송 완료”를 보고 이번 요청의 KV가 덮어써졌다고 가정했지만 실제로는 대부분이 이전 요청의 KV 상태를 유지했고, 그 stale page 위에서 decode가 진행되며 타 요청 데이터가 섞여 나옴[^1][^2]

여기서 중요한 포인트는, 노출이 “캐시 hit에 따른 timing 차이”가 아니라 “응답 본문이 타 테넌트의 내용을 포함”했다는 점입니다. 즉 confidentiality breach가 즉시 현실화된 케이스입니다.

Cloudflare는 조치로 (1) pool을 context length보다 크게 늘려 유효 요청이 reject 경로로 들어가지 않게 했고(약 2.04M tokens 수용으로 조정), (2) 엔진 패치와 설정 수정으로 reject 요청을 제대로 에러로 종료하도록 했다고 밝혔습니다.[^1][^2]

한편, SGLang 측도 같은 날(2026-10-26) “요청 격리 개선”이라는 이름으로 메커니즘과 운영자 권고를 정리해 공개했습니다.[^3][^3]

## request boundary, session boundary, tenant boundary가 실제 스택에서 갈라지는 지점
LLM 서빙에서 경계가 무너지는 이유는 단순합니다. 스택이 성능 때문에 경계를 일부러 흐립니다. 문제는 흐리게 만든 경계가 “명시적 설계”가 아니라 “부수효과”로 생길 때입니다.

정리해 보면 경계는 최소 3개입니다.

- request boundary: 단일 completion/chat 호출의 시작~끝
- session boundary: 같은 사용자/대화의 multi-turn 상태 공유(예: session KV reuse, conversation memory)
- tenant boundary: 조직/고객/워크스페이스 단위로 절대 섞이면 안 되는 보안 경계

성능 최적화는 대부분 request boundary를 넘습니다.

- continuous batching: 서로 다른 요청을 한 GPU step에서 함께 decode
- KV cache pool: GPU 메모리에서 “페이지” 단위로 할당/해제/재사용
- prefix cache(prompt caching): 요청 간 prefix가 같으면 prefill 결과(KV)를 재사용
- PD disaggregation: prefill GPU와 decode GPU를 분리하고 KV cache를 RDMA로 전송

Cloudflare가 설명한 Workers AI 구조는 disaggregated prefill/decode이고, KV cache를 RDMA로 넘기는 전송 계층으로 Mooncake를 사용합니다.[^1][^2]

PD disaggregation 자체는 흔해지고 있습니다. Mooncake도 “prefill과 decode를 분리하고 KV cache를 이동시키는” 것을 전제로 Transfer Engine을 제공합니다.[^4][^4]

이 구조에서 멀티테넌시 격리 문제는 보통 두 층으로 나뉩니다.

1) 의도된 공유(합법적 공유)가 만드는 side-channel
- prefix cache hit/miss에 따른 TTFT 차이
- cache key 설계가 허술하면 collision/poisoning

2) 의도치 않은 공유(버그/경계 붕괴)가 만드는 직접 노출
- use-after-free 성격의 stale page read
- abort/disconnect/timeout 경로의 리소스 회수 타이밍 오류
- reject 처리에서 partial success가 발생

이번 Cloudflare 사건은 2)에 속합니다.

## KV cache/세션/요청 경계가 무너지면 새는 데이터의 실체
cross-request 노출이 위험한 이유는 “토큰이 섞였다”가 아니라 “토큰이 곧 비밀”이기 때문입니다. 실제 서비스 프롬프트에는 보통 다음이 포함됩니다.

- system prompt: 정책, 내부 규칙, 비공개 instruction, 모델에게 주는 guardrail
- tool 호출 결과: 내부 API 응답, DB 조회 결과, 사내 문서
- RAG retrieval: 벡터 검색 결과(대부분 원문 chunk)
- user content: 고객 데이터, PII, 소스코드, 계약서, 의료/금융 텍스트
- 운영 메타데이터: trace id, internal routing info, 실수로 섞인 credential

KV cache는 이 모든 텍스트의 “중간 표현(키/값 텐서)”이지만, 서빙 버그가 나면 중간 표현이 다시 텍스트로 역투영됩니다. SGLang 측도 “오염된 한 slot이 전체 generation을 망친다”는 점을 설명하면서, 실제 재현에서 victim 요청의 출력이 정상 카운팅을 하다가 donor 요청의 프롬프트 텍스트로 변했다고 적었습니다.[^3][^3]

이 현상은 직관적으로 이상하지만, attention이 모든 과거 position을 읽는다는 점을 생각하면 자연스럽습니다. decode가 읽는 KV 중 일부가 “이 요청이 쓴 적 없는 페이지”로 바뀌는 순간, 모델은 그 foreign context를 자기 컨텍스트로 믿고 다음 토큰을 냅니다. 그 결과는 흔히 다음 둘 중 하나로 나타납니다.

- incoherent output(문맥 붕괴)
- foreign text fragment가 “그럴듯한 형태”로 출력에 섞임(이번 사건이 여기)

운영자 관점에서는 이 두 번째가 진짜 문제입니다. incoherent output은 장애로 끝나지만, foreign fragment는 보안 사고로 끝납니다.

## 이번 케이스의 실패 모드: over-length 요청 + disaggregated handoff + stale page
Cloudflare가 공개한 설명을 “서빙 엔진 설계 실수” 관점으로 다시 쓰면 다음과 같습니다.

- 설정 불일치: 모델 context length(논리 한도)와 KV pool capacity(물리 한도)가 불일치
  - context length: 1,048,576 tokens
  - prefill KV pool: 681,280 tokens까지만 수용
  - 결과: “논리적으로는 허용되는 요청”이 “물리적으로는 처리 불가능”한 상태[^1][^2]

- reject 처리의 원칙이 fail-closed가 아니었다
  - 정상적인 fail-closed라면: pool 초과 시 prefill 단계에서 즉시 에러 반환, decode까지 도달 금지
  - 실제 동작: pool 초과 요청이 내부적으로 reject 표시되고 1-token placeholder로 치환됨. 그런데 그 상태로 prefill이 placeholder의 KV를 만들고, decode로 “전송 완료”를 알림. decode는 기존 페이지가 덮어써졌다고 가정했지만 실제로는 대부분 stale page가 남아 있었고, 그 위에서 decode가 진행[^1][^2]

- 이 버그가 disaggregated PD에서만 위험해진 이유
  - 단일 노드라면 prefill=decode라서 reject 경로가 비교적 단순하고 “에러로 끝내는” 경로가 하나로 합쳐집니다.
  - PD disaggregation은 “prefill이 성공했다/실패했다” “전송이 끝났다/부분만 끝났다” “decode가 이제 읽어도 된다/아직 쓰는 중이다” 같은 상태를 여러 컴포넌트가 공유합니다. 이때 상태 합의가 깨지면 분산 use-after-free와 비슷한 형태가 됩니다.

SGLang 쪽 글은 이 계열 문제를 더 일반화해 “KV cache slot이 언제 진짜로 free인가”라는 질문으로 설명합니다. abort로 요청 A가 죽었을 때 decode가 destination slot을 allocator에 반환해 재사용시키면, 아직 NIC/전송 계층에 남아 있는 A의 RDMA write가 나중에 그 slot에 도착해 요청 B를 오염시킬 수 있습니다.[^3][^3]

Cloudflare 사건은 trigger가 “over-length reject 경로”였지만, 같은 종류의 사고는 abort/disconnect/timeout에서도 충분히 납니다. 그래서 체크리스트는 “길이 체크만 제대로 하면 끝”이 아닙니다.

## 전형적인 설계 실수: cross-request 노출을 만드는 패턴
내가 운영/리뷰하면서 반복적으로 보는 실수는 대부분 아래 범주 중 하나로 들어갑니다.

### 1) 논리 한도(context length)와 물리 한도(pool capacity)를 분리해 두고, 둘의 합의가 없다
Cloudflare가 이번에 딱 여기서 시작했습니다. 엔진이 “에러를 줄 것이다”라고 기대했지만, 실제 경로는 placeholder로 진행됐습니다.[^1][^2]

이 실수의 위험한 점은 테스트로 잘 안 잡힌다는 것입니다.

- long-context 테스트는 보통 “성공 케이스”를 본다
- 거절 경로(reject)가 “에러로 끝나는지” “부분 성공이 되는지”는 따로 테스트해야 한다
- 특히 disaggregated 모드에서는 거절 경로가 prefill/decode 각각에 존재할 수 있다

### 2) reject/abort 경로가 fail-closed가 아니라 best-effort로 흘러간다
LLM 서빙 엔진은 성능 때문에 “일단 forward를 돌려서 뭐라도 만들고” 나중에 취소하는 경로가 많습니다.

- 스케줄러가 admission에서 reject했는데도 bootstrap/metadata buffer 예약/전송 핸드셰이크가 진행
- “이번 요청이 쓴 범위”를 표시하지 않고 “전송 완료”만 보고 decode가 진행

SGLang은 이 문제를 admission 단계에서 더 일찍 요청을 retire시키는 패치로 막았고(#36988, #38935), Cloudflare도 “engine-side fix이자 backstop”이라고 적었습니다.[^1][^2]

### 3) allocator는 free라고 믿지만, 실제로는 NIC/전송 큐에 ‘되돌릴 수 없는 write’가 남아 있다
PD disaggregation + RDMA(one-sided WRITE/READ)에서는 “이미 NIC에 올라간 work request를 취소하기 어렵다”는 점이 핵심 제약입니다.[^3][^3]

이건 단순히 “전송을 동기화하면 되지 않나”로 풀기 어렵습니다.

- 동기화는 성능을 크게 깎습니다.
- 그래도 abort 경로는 반드시 존재합니다.
- 그러면 abort에서 동기화가 안 되는 구간을 어떻게 다룰지(hold, drain ack, timeout)가 설계의 핵심이 됩니다.

### 4) prefix cache/세션 cache의 키 스코핑이 테넌트 경계를 표현하지 못한다
이건 “직접 노출”이 아니라 side-channel 쪽이지만, 멀티테넌시에서는 같이 묶어서 봐야 합니다.

vLLM은 보안 문서에서 “같은 서버 프로세스 내에서는 tenant isolation을 제공하지 않는다”고 명시하고, `cache_salt`는 특정 위험을 줄이지만 isolation boundary가 아니라고 못박습니다.[^5][^6]

그리고 prefix caching이 timing side-channel이 될 수 있다는 점은 CVE로도 연결되어 있습니다.[^7][^7]

SGLang 쪽도 RadixKey에 `extra_key`, `cache_salt` 같은 네임스페이스 필드를 넣어 “서로 공유하면 안 되는 요청을 분리”할 수 있게 설계해 둔 흔적이 있습니다.[^8][^8]

하지만 이건 “요청이 올바른 값을 넣는다”가 전제입니다. 즉 gateway가 강제해야 합니다.

### 5) 관측/검증이 ‘로그 기반 사후 분석’에만 의존한다
Cloudflare는 “155개 응답”이라는 숫자까지 추적했지만, 그건 사건 이후 포렌식으로 가능한 영역입니다. 운영 중에는 “지금 이 순간 decode가 foreign KV를 읽고 있는지”를 빨리 감지해야 합니다.

Cloudflare는 SGLang에 다음 관측/무결성 기능이 들어갔다고 적었습니다.

- `--disaggregation-enable-kv-checksum`: prefill→decode 전송 KV에 체크섬을 붙이고 decode가 검증[^1][^2]
- `--kv-canary`: KV 오염 가능성을 탐지/로그(단 모델 아키텍처 커버리지 제한 언급)[^1][^2]

SGLang도 PD checksum을 “두 엔진에 모두 플래그를 주고 KV layout이 일치해야 한다”고 구체적으로 설명합니다.[^3][^3]

## 멀티테넌시 격리 체크리스트: 서빙 스택 관점
여기부터는 사건을 교훈으로 “내 서비스라면 어떤 체크를 코드/설정/테스트로 박을지”를 정리합니다. 항목은 크게 6묶음입니다.

### A. admission(입장)에서 fail-closed를 강제한다
1) context length와 KV pool capacity를 같은 소스에서 계산/검증한다
- Cloudflare는 “pool이 context보다 작으면 context를 낮춰서 맞춰라. 프록시에 맡기지 마라. 엔진이 알아서 reject할 거라 가정하지 마라”고 권고했습니다.[^1][^2]

2) reject 경로가 “에러 반환”으로 끝나는지 통합 테스트를 만든다
- 특히 PD disaggregation에서는 prefill reject, decode reject, router reject가 따로 있을 수 있습니다.
- “400/413 같은 client error로 끝났는지” “decode가 토큰을 생성했는지”를 테스트로 고정합니다.

3) over-length를 “placeholder + best-effort”로 처리하지 않는다
- placeholder는 내부적으로는 편할 수 있지만, disaggregated 구조에서 “전송 완료/부분 완료”의 상태 합의를 망가뜨리기 쉽습니다.
- 이번 사건은 그 최악의 형태였습니다.[^1][^2]

### B. allocator/메모리 풀에서 ‘소유권’을 1급 데이터로 취급한다
1) KV 페이지(또는 slot)에 owner tag를 붙이는 방향이 장기적으로는 제일 강합니다
Cloudflare가 “Integrity by construction”으로 언급한 방식이 이 계열입니다.

- 물리 KV page마다 reallocation 때 바뀌는 tag를 붙인다
- 각 request는 “내가 읽어야 하는 tag 집합”을 기록한다
- decode가 KV를 읽기 직전에 tag를 검사해서, mismatch면 그 request만 실패로 끝낸다
- Cloudflare는 자체 프로토타입에서 throughput/tail latency 비용이 1% 미만이었다고 적었습니다.[^1][^2]

이건 구현 난도가 높지만, 구조적으로 “다음 버그의 형태를 예측하지 않아도” 되는 쪽이라 투자 가치가 있습니다.

2) 단기적으로는 checksum/canary 같은 검출 장치가 필요합니다
- checksum은 “전송 구간에서 무엇이 도착했는지”를 잡는 데 강합니다.
- canary는 “내부 corruption을 발견”하는 쪽인데, 모델 아키텍처 지원 범위가 제한될 수 있습니다.[^1][^2]

### C. PD disaggregation에서는 abort/disconnect가 곧 공격면이다
SGLang은 abort 경로를 분산 use-after-free로 설명합니다.[^3][^3]

여기서 체크리스트는 명확합니다.

1) deferred KV release(해제 지연)를 켠다
- abort 시 즉시 free하지 말고 hold한다
- drain ack(“이제 더 이상 in-flight write 없다”)를 받을 때까지 기다린다

2) hold timeout을 운영 데이터로 sizing한다
SGLang은 `SGLANG_DISAGGREGATION_DEFERRED_DECODE_KV_RELEASE_TIMEOUT`을 언급하며 60~120s 같은 넉넉한 값을 예로 들고, “abort rate × T_hold × pages per request”가 held capacity가 된다고 설명합니다.[^3][^3]

3) transfer batch size를 제한해 “한 번 실패할 때 남는 in-flight write”를 제한한다
SGLang은 `SGLANG_MOONCAKE_MAX_TRANSFER_BATCH_INDICES`로 Mooncake 전송을 더 작은 batch로 쪼개는 방식을 언급합니다. 작은 batch는 성능 비용이 있으니 극단적 long-context에서만 추가 안전장치로 쓰라고 적습니다.[^3][^3]

4) router/proxy가 abort를 불필요하게 만들지 않게 한다
Cloudflare는 로드밸런서가 “첫 토큰까지는 요청을 진행시키도록” 해서 불필요한 abort를 줄이라고 권고했습니다.[^1][^2]

### D. prefix cache/세션 cache는 ‘누가 공유 가능한가’를 키에 박는다
여기서 목표는 두 가지로 나뉩니다.

- (보안) 테넌트 간 공유 금지
- (성능) 테넌트 내부에서는 공유 허용(조직 내 사용자끼리 같은 system prompt를 쓰는 경우가 많습니다)

vLLM은 `cache_salt`를 요청 파라미터로 받아 prefix cache hash에 섞는다고 문서화했습니다.[^5][^6]

SGLang의 Radix cache 구현은 `RadixKey`에 `extra_key`와 `cache_salt`를 포함시켜 “서로 다른 extra_key는 prefix를 공유하지 않는다”고 주석으로도 명확히 적어 두었습니다.[^8][^8]

운영 체크리스트는 다음입니다.

1) client가 `cache_salt`/`extra_key`를 마음대로 넣지 못하게 한다
- gateway가 tenant_id/org_id 기준으로 강제 스코핑
- client 제공 값은 무시하거나, server-side secret과 HMAC해서 재작성

2) “격리 수준”을 명시적으로 선택한다
- per-tenant salt: 테넌트 간 공유 금지
- per-user salt: 같은 테넌트 내 사용자 간에도 공유 금지(보안 강하지만 hit rate 급락)
- per-org salt: 조직 내부 공유 허용(현실적 타협)

3) 측정 항목을 TTFT 평균이 아니라 분포로 본다
- prefix hit은 tail을 줄이는 쪽이라 평균만 보면 효과를 놓치기 쉽습니다.

### E. 프로세스/노드 파티셔닝은 최후의 격리수단으로 남겨 둔다
vLLM 문서가 명확히 말하듯, 같은 프로세스 내 다중 테넌시는 엔진이 isolation boundary를 제공하지 않는 한 근본적으로 위험합니다.[^5][^6]

그래서 고보안 환경에서는 결국 다음 중 하나로 갑니다.

- per-tenant dedicated serving instance
- GPU 파티셔닝(MIG 같은 하드 파티셔닝)
- node pool 자체를 테넌트별로 분리

다만 이건 비용이 바로 튀는 영역이라, 위의 A~D를 먼저 정교하게 하고 “여기까지 해도 위험 허용 불가”일 때 마지막 카드로 쓰는 편이 낫습니다.

### F. 운영 중 검증: “우연히 섞인 1번”을 잡아내는 장치를 둔다
사고는 155번만 터졌습니다. 비율로는 낮았을 가능성이 큽니다. 그런데 보안 사고는 1번이면 충분합니다.

그래서 운영 중에는 “발생 확률”보다 “발생 즉시 탐지”가 중요합니다.

- disaggregation checksum(`--disaggregation-enable-kv-checksum`)을 지원하는 모델/구성이라면 켠다[^3][^3]
- `--kv-canary`를 쓸 수 있으면 켠다(단 모델 아키텍처 커버리지 확인 필요)[^1][^2]
- deferred release 관련 metric을 대시보드에 올린다(Cloudflare는 v0.5.22에서 metric이 들어갔다고 표로 남김)[^1][^2]

## SGLang에서 바로 적용 가능한 방어 설정(단일 노드/PD disaggregation)
SGLang 버전 업이 전제입니다. Cloudflare는 “v0.5.22 또는 그 이후 빌드로 업그레이드”를 권했고, 사건 관련 fix가 여러 PR로 들어갔다고 적었습니다.[^1][^2]

SGLang 릴리스는 GitHub releases에서 확인할 수 있고, v0.5.22가 2026-10-19에 릴리스됐습니다.[^9][^9]

### 1) PD checksum을 켤 수 있으면 켠다
SGLang은 PD checksum에 대해 다음을 명시합니다.

- prefill과 decode 엔진 모두에 `--disaggregation-enable-kv-checksum`를 줘야 함
- 두 엔진의 KV cache layout이 일치해야 함
- 성능 비용 때문에 기본은 off지만, 측정에서는 유의미한 throughput 저하가 없었다고 보고[^3][^3]

### 2) deferred KV release/transfer batch bound를 운영 기본값으로 본다
SGLang은 구버전(v0.5.19, v0.5.20)에서 임시로 켜야 하는 env를 구체적으로 씁니다.

- `SGLANG_DISAGGREGATION_DEFERRED_DECODE_KV_RELEASE=1`
- `SGLANG_MOONCAKE_MAX_TRANSFER_BATCH_INDICES`
- `SGLANG_DISAGGREGATION_DEFERRED_DECODE_KV_RELEASE_TIMEOUT=60~120s`

그리고 “이건 업그레이드를 대체하지 못한다”고도 못박습니다.[^3][^3]

### 3) prefix cache는 tenant boundary를 강제하는 키 전략 없이는 멀티테넌시에서 켜지 않는다
SGLang의 Radix cache는 `extra_key`/`cache_salt`로 네임스페이스를 분리할 수 있게 되어 있습니다.[^8][^8]

이게 실제로 요청 경계/테넌트 경계에서 강제되는지는 gateway 설계에 달려 있습니다.

## 재현/회귀 테스트: 내가 쓰는 ‘격리 테스트’ 두 가지
여기서는 “Cloudflare 사고를 그대로 재현”하는 PoC를 쓰지 않습니다. 대신 운영 관점에서 중요한 것은 (1) 격리가 깨졌을 때 탐지할 수 있는가, (2) 업그레이드/설정 변경 후 격리가 유지되는가 입니다.

그래서 테스트를 두 층으로 나눕니다.

- (T1) prefix cache 격리 회귀 테스트: 테넌트가 다르면 cache hit이 나면 안 된다(= timing 차이가 나면 안 된다)
- (T2) cross-request content leak 스모크 테스트: abort/재시도/장문 요청을 섞어 때렸을 때, canary가 타 테넌트 응답에 나타나면 즉시 실패

### 실습 환경: SGLang 단일 노드(OpenAI-compatible endpoint)
아래는 “테스트 harness가 실제로 돌아가는” 수준으로 적습니다. GPU가 있는 개발 서버 기준입니다.

- SGLang: v0.5.22
- 실행 방식: Docker
- 모델: 작은 instruct 모델(예: 0.5B~3B급)

SGLang v0.5.22는 Docker 이미지로도 배포됩니다.[^9][^9]

#### 1) SGLang 서버 실행
```bash
# (예) NVIDIA GPU 머신
# - 30000 포트를 OpenAI 호환 API로 노출한다고 가정
# - HF 모델 다운로드를 위해 캐시 볼륨을 잡는 것을 권장

docker run --rm -it \
  --gpus all \
  -p 30000:30000 \
  -v $HOME/.cache/huggingface:/root/.cache/huggingface \
  lmsysorg/sglang:v0.5.22 \
  python3 -m sglang.launch_server \
    --host 0.0.0.0 \
    --port 30000 \
    --model-path Qwen/Qwen2.5-0.5B-Instruct
```

모델 이름은 환경에 맞게 바꿔도 됩니다. 핵심은 “같은 서버 프로세스에서 멀티테넌시 상황을 흉내” 낼 수 있다는 점입니다.

#### 2) 테스트 클라이언트 준비
`requirements.txt`
```txt
httpx==0.27.2
anyio==4.6.2
```

설치:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### (T1) prefix cache 격리 회귀 테스트: cache_salt/extra_key 강제의 효과를 시간으로 확인
이 테스트는 “절대적 시간”이 아니라 “상대적 변화”를 봅니다.

- 같은 tenant(A)에서 같은 긴 프롬프트를 두 번 호출하면, 두 번째가 더 빨라질 가능성이 큽니다(prefix cache hit)
- 다른 tenant(B)에서 같은 프롬프트를 호출했을 때도 빨라진다면, 테넌트 격리가 깨진 것입니다

SGLang Radix cache 키는 token ids뿐 아니라 `extra_key`, `cache_salt`를 포함할 수 있게 되어 있습니다.[^8][^8]

`tenant_prefix_cache_isolation.py`
```python
import asyncio
import hashlib
import hmac
import os
import time

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:30000/v1")
MODEL = os.getenv("MODEL", "Qwen/Qwen2.5-0.5B-Instruct")

# 운영에서는 KMS/Secret Manager에 넣을 값입니다.
MASTER_KEY = os.getenv("MASTER_KEY", "dev-only-master-key").encode()

def derive_salt(tenant_id: str) -> str:
    # tenant_id가 노출되어도 salt가 예측 가능하면 의미가 약해집니다.
    # vLLM도 salt는 secret으로 취급하라고 권고합니다.[^5]
    digest = hmac.new(MASTER_KEY, tenant_id.encode(), hashlib.sha256).digest()
    return digest.hex()

async def chat(client: httpx.AsyncClient, tenant_id: str, prompt: str):
    # SGLang 내부에서는 req.cache_salt/req.extra_key가 RadixKey로 들어갑니다.
    # API 계층에서 이 필드를 직접 받는지 여부는 배포 방식에 따라 다를 수 있어
    # 여기서는 extra_body로 넘긴다고 가정합니다.
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 64,
        "extra_body": {
            "cache_salt": derive_salt(tenant_id),
            "extra_key": tenant_id,
        },
    }

    t0 = time.perf_counter()
    r = await client.post(f"{BASE_URL}/chat/completions", json=payload, timeout=120)
    r.raise_for_status()
    dt = time.perf_counter() - t0
    return dt, r.json()["choices"][0]["message"]["content"]

async def main():
    prompt = "\n".join([
        "You are a coding assistant.",
        "".join(["#" * 120 for _ in range(200)]),  # 프리필 시간을 늘리기 위한 더미
        "Summarize the purpose of the text above in 1 sentence.",
    ])

    async with httpx.AsyncClient() as client:
        # tenant A warm-up
        t1, _ = await chat(client, "tenant-A", prompt)
        t2, _ = await chat(client, "tenant-A", prompt)

        # tenant B (same prompt)
        t3, _ = await chat(client, "tenant-B", prompt)
        t4, _ = await chat(client, "tenant-B", prompt)

    print(f"tenant-A first : {t1:.3f}s")
    print(f"tenant-A second: {t2:.3f}s")
    print(f"tenant-B first : {t3:.3f}s")
    print(f"tenant-B second: {t4:.3f}s")

    # 단순 판정(노이즈가 있으니 CI에서는 반복 샘플링 + 통계로 강화하는 편이 낫습니다)
    if t3 < t1 * 0.7:
        raise SystemExit("FAIL: tenant-B first call is suspiciously fast; cross-tenant prefix cache sharing may exist")

if __name__ == "__main__":
    asyncio.run(main())
```

실행:
```bash
BASE_URL=http://localhost:30000/v1 \
MODEL=Qwen/Qwen2.5-0.5B-Instruct \
MASTER_KEY='replace-with-real-secret' \
python tenant_prefix_cache_isolation.py
```

예상 출력(형태):
```txt
tenant-A first : 1.842s
tenant-A second: 0.611s
tenant-B first : 1.801s
tenant-B second: 0.605s
```

판정 포인트는 tenant-B의 첫 호출이 tenant-A의 두 번째처럼 빨라지지 않는지입니다. 만약 tenant-B의 첫 호출이 지나치게 빠르면, 테넌트 경계가 prefix cache에 반영되지 않았거나 gateway가 필드를 제대로 강제하지 않는 것입니다.

이 테스트를 CI에 넣으면 좋은 지점은 “서빙 엔진 업그레이드”가 아니라 “gateway/라우팅 계층 변경”입니다. 실무에서 격리 문제는 엔진 자체보다 앞단에서 터지는 경우가 더 많았습니다.

### (T2) cross-request content leak 스모크 테스트: canary 기반
Cloudflare 사건처럼 “다른 테넌트 요청의 일부가 내 응답에 섞여 나오는지”는 시간으로는 못 잡습니다. 본문에 특정 문자열이 나오면 바로 실패시키는 방식이 가장 단단합니다.

여기서 핵심은 canary 문자열을 운영 데이터와 절대 섞지 않는 것입니다.

- 테넌트 A의 프롬프트에만 canary를 넣는다
- 테넌트 B의 응답에서 canary가 발견되면 즉시 실패

`cross_request_canary_smoke.py`
```python
import asyncio
import os
import re
import time

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:30000/v1")
MODEL = os.getenv("MODEL", "Qwen/Qwen2.5-0.5B-Instruct")

CANARY = f"CANARY_{int(time.time())}_DO_NOT_LEAK"

def contains_canary(text: str) -> bool:
    return re.search(re.escape(CANARY), text) is not None

async def chat(client: httpx.AsyncClient, prompt: str, extra_body=None):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 128,
    }
    if extra_body:
        payload["extra_body"] = extra_body

    r = await client.post(f"{BASE_URL}/chat/completions", json=payload, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

async def main():
    # 테넌트 A: canary를 포함한 장문 컨텍스트(실서비스에서는 RAG chunk, tool output이 이런 역할을 합니다)
    prompt_a = "\n".join([
        "You are a helpful assistant.",
        f"Here is a secret marker: {CANARY}",
        "".join(["lorem ipsum " * 200 for _ in range(200)]),
        "Explain the above in bullet points.",
    ])

    # 테넌트 B: 전혀 관계 없는 요청
    prompt_b = "Write a short poem about network packets."

    async with httpx.AsyncClient() as client:
        _ = await chat(client, prompt_a, extra_body={"extra_key": "tenant-A"})

        # B를 여러 번 쏴서 확률 사건을 조금이라도 끌어올립니다.
        for i in range(20):
            out_b = await chat(client, prompt_b, extra_body={"extra_key": "tenant-B"})
            if contains_canary(out_b):
                raise SystemExit(f"FAIL: canary leaked into tenant-B output at iter={i}\n{out_b}")

    print("PASS: no canary observed")

if __name__ == "__main__":
    asyncio.run(main())
```

실행:
```bash
BASE_URL=http://localhost:30000/v1 \
MODEL=Qwen/Qwen2.5-0.5B-Instruct \
python cross_request_canary_smoke.py
```

이건 “이번 Cloudflare 버그를 그대로 재현”하는 테스트가 아닙니다. 대신 다음을 보장합니다.

- 어떤 이유로든 cross-request 텍스트 혼입이 발생하면, CI에서 즉시 잡힌다
- 특히 엔진 업그레이드, disaggregation 설정 변경, router 교체 같은 큰 변경 후에 최소한의 안전망이 된다

PD disaggregation 환경에서는 이 스모크 테스트를 “abort를 유발하는 트래픽 패턴”과 같이 돌리는 편이 좋습니다. SGLang이 설명한 것처럼 abort/disconnect는 오염 경로를 열어주기 때문입니다.[^3][^3]

## 트레이드오프: 격리 강도 vs 성능(throughput/TTFT) vs 운영 복잡도
격리 강도를 올리는 방법은 많지만, 비용이 어디에서 나가는지 감을 잡고 선택해야 합니다.

### 1) per-tenant salt는 보안에 유리하지만 prefix cache hit rate를 깎는다
테넌트 내부 공유가 허용되는 SaaS라면 per-org salt가 제일 현실적입니다.

- per-user: 가장 안전하지만 히트율이 낮고 GPU 비용이 증가
- per-tenant/per-org: 공유 가능한 집단 단위로 타협

여기서 중요한 현실은 “prefix caching은 성능을 올리기 위한 기능인데, 멀티테넌시에서는 그게 곧 공격면”이라는 점입니다. 이걸 인정하고 설계를 시작해야 합니다.

### 2) checksum/canary/tag 검증은 ‘이상 시 실패’라는 운영 결정을 동반한다
checksum mismatch가 났을 때 어떤 선택을 할지 정해야 합니다.

- 그냥 재시도할 것인가
- 해당 요청만 실패로 반환할 것인가(대부분 이게 맞음)
- 해당 worker를 drain하고 재시작할 것인가

Cloudflare가 강조한 방향은 “읽기 시점에 내 소유가 아닌 페이지를 감지하면 그 요청만 실패로 끝내라”입니다.[^1][^2]

### 3) deferred release는 abort storm에서 capacity를 먹는다
SGLang이 제시한 sizing 식이 정확히 이 부분을 찌릅니다.

- held capacity ≈ abort rate × T_hold × pages per request

abort storm은 “사용자가 많아서”가 아니라 “프록시/모바일 네트워크/타임아웃 정책” 때문에 생기는 경우도 많습니다. 그래서 L7/LB 설정까지 같이 봐야 합니다.

### 4) 프로세스/노드 분리는 가장 확실하지만 비용이 바로 튄다
per-tenant instance는 확실하지만, 대부분의 팀은 그 비용을 지불할 준비가 되어 있지 않습니다. 그래서 실제로는 다음 순서로 갑니다.

- (1) 키 스코핑 + gateway 강제 + 테스트
- (2) checksum/canary 같은 무결성 검출
- (3) disaggregation 경로의 lifecycle hardening(deferred release, batch bound)
- (4) 그래도 안 되면 물리 파티셔닝

## 내가 내리는 운영 판단
Cloudflare의 GLM-5.3 사건에서 제일 무거운 교훈은 “길이 제한을 잘못 잡았다”가 아닙니다. reject/abort 같은 비정상 경로에서 시스템이 fail-closed로 멈추지 않고, 분산된 컴포넌트가 서로 다른 상태를 믿는 순간 KV cache가 곧바로 보안 경계가 된다는 점입니다.[^1][^2]

그래서 멀티테넌시 LLM 서빙에서는 다음 원칙을 기본값으로 둡니다.

- admission에서 논리/물리 한도를 합의시키고, reject는 무조건 에러로 끝낸다
- KV cache는 성능 자산이면서 동시에 보안 경계이므로, 소유권/무결성 검증을 런타임에 심는다
- prefix/session cache는 tenant boundary를 키에 박고, 그 키는 gateway가 강제한다
- 격리 검증은 “재현 PoC”가 아니라 “회귀 테스트”로 매일 돌린다

이 정도까지 올라가면, 이후의 고도화(페이지 태깅, formal modeling 같은)는 투자 판단의 문제로 바뀌고, 기본적인 cross-request 노출은 운영 체계로 막을 수 있는 상태가 됩니다.

## 참고 자료
- [Cross-request KV cache exposure in the GLM-5.3 Workers AI model, and our remediation with SGLang](https://blog.cloudflare.com/kv-cache-exposure-remediation/)[^2]
- [SGLang security update: improving request isolation](https://www.lmsys.org/blog/2026-10-26-cf-security/)[^3]
- [SGLang Releases (v0.5.22 포함)](https://github.com/sgl-project/sglang/releases)[^9]
- [vLLM Security: Multi-Tenant Deployments / Cache Salting](https://docs.vllm.ai/en/latest/usage/security/)[^6]
- [GitHub Advisory: CVE-2025-46570 (vLLM prefix cache timing side-channel)](https://github.com/advisories/GHSA-4qjh-9fv9-r85r)[^7]
- [SGLang radix_cache.py: RadixKey(extra_key, cache_salt)](https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/mem_cache/radix_cache.py)[^8]
- [Mooncake Transfer Engine documentation](https://kvcache-ai.github.io/Mooncake/design/transfer-engine/index.html)[^4]

[^1]: <https://blog.cloudflare.com/kv-cache-exposure-remediation/>
[^2]: <https://blog.cloudflare.com/kv-cache-exposure-remediation>
[^3]: <https://www.lmsys.org/blog/2026-10-26-cf-security/>
[^4]: <https://kvcache-ai.github.io/Mooncake/design/transfer-engine/index.html>
[^5]: <https://docs.vllm.ai/en/latest/usage/security/>
[^6]: <https://docs.vllm.ai/en/latest/usage/security/?trk=article-ssr-frontend-pulse_little-text-block>
[^7]: <https://github.com/advisories/GHSA-4qjh-9fv9-r85r>
[^8]: <https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/mem_cache/radix_cache.py>
[^9]: <https://github.com/sgl-project/sglang/releases>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
