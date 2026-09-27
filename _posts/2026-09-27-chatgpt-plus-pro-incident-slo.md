---
title: "39분 ChatGPT 오류율 상승이 SLO를 태우는 방식"
description: "OpenAI Status의 Plus/Pro 오류율 상승(39분)을 플랜·기능·재시도·리텐션·에러버짓 관점으로 쪼개서 본다."
date: 2026-09-27 10:22:37 +0900
categories: ["News", "AI"]
tags: ["openai-status", "slo", "error-budget", "retry-storm", "circuit-breaker", "chatgpt"]
render_with_liquid: false
---

## 사건 타임라인: Plus/Pro 오류율 상승 39분, 컴포넌트는 Conversations

OpenAI Status에 2026-09-22(페이지 현지 표기 기준) **ChatGPT Plus/Pro 사용자에서 오류율 상승**이 기록되어 있습니다. 상태는 `Degraded performance`로 표시됐고, 영향받은 컴포넌트는 `ChatGPT → Conversations` 하나로 잡혀 있습니다. 업데이트는 2개(Investigating → Resolved)만 남아 있고, Investigating이 09:58, Resolved가 10:37로 찍혀 있어 총 39분 구간입니다. 이 페이지는 “All impacted services have now fully recovered.”로 마무리되어 있습니다.[^1]

여기서 중요한 디테일이 두 가지 있습니다.

첫째, 영향 범위가 “ChatGPT 전체”가 아니라 “Conversations”로 명시되어 있습니다. ChatGPT 같은 제품은 기능이 촘촘히 얽혀 있기 때문에, 특정 컴포넌트의 오류율 상승은 사용자가 체감하는 실패가 한 플로우에 집중될 가능성이 큽니다. 이런 경우 장애 시간이 짧아도 전환/결제/리텐션 같은 제품 지표가 더 크게 흔들립니다.

둘째, OpenAI Status에는 “가용성 메트릭은 전체 티어/모델/에러 타입을 합산한 aggregate로 보고되며, 개별 고객의 가용성은 티어/모델/API 기능에 따라 달라질 수 있다”는 단서가 같이 노출됩니다. 즉, “전체 평균은 멀쩡해 보이는데 특정 유료 플랜만 깨지는” 상황이 구조적으로 가능하다는 뜻입니다.[^1]

이 39분을 단기 장애로 치부하면 놓치는 게 많습니다. 특히 LLM이 핵심 플로우인 서비스(자사 제품이든, 외부 LLM 의존이든)는 “짧은 degraded”가 어떤 메커니즘으로 비용과 신뢰를 갉아먹는지 분해해두는 편이 운영 난이도를 낮춥니다.

## ‘짧은 장애’가 지표를 망치는 방식: 시간보다 분모·분자부터 깨진다

장애의 체감 비용은 “몇 분 다운됐나”로 끝나지 않습니다. SLO를 어떻게 정의했는지(시간 기반/요청 기반/기능 기반)에 따라 같은 39분도 에러버짓을 태우는 양이 달라집니다.

Google SRE 문서에서는 SLI를 오류율(실패 비율) 같은 요청 기반 지표로 잡는 게 부분 장애/부분 성공을 다루는 데 유리하다고 반복해서 이야기합니다. “서비스가 일부만 이용 불가”거나 “부하가 시간대별로 변동”하는 경우, 단순한 시간 기반 다운타임보다 “전체 연산 중 실패 비율”이 더 유용하다는 취지입니다.[^2]

문제는 많은 조직이 여전히 운영 커뮤니케이션에서는 시간(39분)으로 사고하고, 실제 제품 체감은 요청/세션/사용자 여정 단위로 발생한다는 괴리입니다.

- 시간 기반: 39분 degraded → 39분 다운과 비슷하게 취급하기 쉬움
- 요청 기반: 같은 39분이라도 트래픽 피크에 맞으면 실패 요청 수가 폭증
- 여정 기반: 특정 플로우(예: 메시지 전송)만 깨지면 “사용자는 그날 서비스를 못 쓴 것”과 거의 동일하게 인식

이 괴리를 방치하면, 장애 회고에서 “짧았으니 넘어가자”가 나오고, 다음 번에는 더 큰 지표 손실로 돌아옵니다.

## 결제 플랜별 영향: Plus/Pro만 깨졌다는 건 제품이 ‘분기’되어 있다는 증거

Status에 “Plus와 Pro 사용자에서 오류율 상승”이라고 적혀 있다는 건, 기술적으로는 트래픽이 최소한 한 번 이상 분기된다는 의미입니다.

- 라우팅이 다르거나(별도 pool, 별도 rate limit, 별도 모델/기능)
- 요청 패턴이 다르거나(긴 컨텍스트, 첨부/툴, 더 잦은 세션 유지)
- 보호 정책이 다르거나(유료 사용자 보호를 위해 aggressive retry/hedging을 켜뒀다가 역효과)

OpenAI가 실제로 어떤 구조를 쓰는지는 Status 한 줄로 확정할 수 없습니다. 다만 “특정 결제 플랜만 오류율이 올라간다”는 관측 자체가, 운영과 지표를 플랜 단위로 분리해서 봐야 한다는 강한 힌트입니다.

여기서 제품 지표가 무너지는 경로는 단순합니다.

1) **유료 고객**의 실패는 무료 고객 실패보다 매출/환불/차지백 리스크로 직결됩니다.
2) Plus/Pro 사용자는 보통 usage intensity가 높습니다. 같은 오류율이라도 “실패한 시도 수”가 더 커질 수 있습니다.
3) 유료 고객은 기대치가 다릅니다. 짧은 degraded에도 “돈 내고 쓰는데 안 됨”으로 기억이 각인됩니다.

SLO를 플랜별로 나누지 않으면, 내부에서 “전체 에러율은 괜찮음”이라는 평균값이 의사결정을 오염시킵니다. 특히 CS/환불/해지/재결제 같은 지표는 평균과 거의 상관이 없습니다. 플랜별, 코호트별로 갈라져 움직입니다.

내 경우 B2C 구독 모델에서 가장 크게 데인 부분이 “가용성은 평균이 아니라 상위 코호트 경험”이라는 점이었습니다. Plus/Pro가 깨졌다면, 전체 지표가 멀쩡해 보였더라도 그날의 리텐션 손실은 유료 코호트에서 더 오래 남습니다.

## Conversations 컴포넌트 단위로 다시 보기: 같은 39분이라도 어떤 기능이 깨졌는지가 다르다

Status는 영향을 `Conversations`로 잡았습니다. ChatGPT에서 Conversations는 보통 다음 하위 기능을 포함합니다.

- Conversation list 로드(사이드바/목록)
- Conversation 생성(새 채팅 시작)
- Message 전송(유저 입력 → 서버에 commit)
- Streaming 응답(서버 → 클라이언트 chunk)
- 히스토리 sync(새로고침/다중 디바이스)

여기서 “대화 내용이 안 열림”과 “메시지 전송이 실패함”은 제품 지표에 미치는 충격이 다릅니다.

- 목록 로드 실패: 사용자는 새로고침 몇 번으로 넘어갈 수 있음
- 히스토리 로드 실패: 컨텍스트가 끊겨 신뢰가 급격히 하락(업무 사용자는 특히 민감)
- 메시지 전송 실패: 사용자는 그 순간 목적을 달성하지 못함 → 세션 종료/이탈로 바로 연결
- 스트리밍 끊김: 결과물이 “불완전한 답”으로 남아 재시도 확률이 올라감 → 후속 부하 증가

이런 기능 단위의 차이가 “짧은 장애”를 위험하게 만듭니다. 장애가 39분이어도, 그 39분 동안 사용자가 가장 많이 수행하는 핵심 동작이 실패하면 전환율은 시간 대비 훨씬 크게 흔들립니다.

여기서 한 단계 더 들어가면, 기능 단위 SLI를 분리하는 이유가 나옵니다.

- `message_send_success_rate`
- `stream_start_success_rate`
- `stream_complete_rate` (사용자가 중단한 것 vs 서버가 끊은 것 분리)
- `conversation_create_success_rate`

Conversations를 하나의 컴포넌트로만 보면, “대화 목록 API는 멀쩡했는데 메시지 commit만 깨졌던” 같은 핵심 디테일이 지워집니다. 그리고 지워진 디테일만큼 다음 번에도 같은 방식으로 지표가 부서집니다.

## 재시도 폭주가 장애를 늘리는 방식: 실패가 ‘부하’로 다시 들어온다

39분 degraded에서 운영팀이 제일 경계해야 하는 것은 원인 자체보다 **재시도 증폭(retry amplification)** 입니다. 서비스가 느리거나 오류가 나기 시작하면 클라이언트/중간 계층/백엔드가 동시에 재시도를 걸 수 있고, 그 재시도가 복구 구간의 부하를 더 키워 장애를 연장합니다.

AWS Well-Architected Framework는 재시도에서 흔히 하는 실수로 “exponential backoff/jitter 없이 재시도”, “최대 재시도 제한 없음”을 명시적으로 경고합니다. 서버가 과부하로 실패하는 상황에서 고정 간격 재시도는 회복 시간을 늘리고, jitter를 넣지 않으면 클라이언트가 동기화되어 thundering herd가 됩니다.[^3]

AWS SDK 문서도 같은 맥락에서, jitter가 없으면 동시에 에러를 맞은 클라이언트가 동시에 재시도해 burst를 만들고(thundering herd), full jitter가 이를 분산시킨다고 설명합니다.[^4]

이걸 ChatGPT 같은 앱에 대입하면 더 위험합니다.

- 웹/모바일 클라이언트는 UX 개선을 위해 자동 재시도를 넣기 쉽습니다.
- 스트리밍이 끊기면 사용자는 다시 보내거나, 새로고침하거나, 앱이 자동 재연결합니다.
- 유료 사용자일수록 “될 때까지” 시도할 가능성이 높습니다.

재시도 폭주가 무서운 이유는, 장애 시간이 짧을수록 더 잘 터지기 때문입니다. 2시간짜리 완전 장애는 사람도 시스템도 “일단 멈추자”로 수렴하는데, 39분 degraded는 애매해서 모두가 계속 두드립니다. 두드리는 동안 장애가 더 길어집니다.

여기서 circuit breaker가 같이 필요해집니다. Martin Fowler가 정리한 Circuit Breaker 패턴의 핵심은 “실패 임계치를 넘으면 더 이상 원격 호출을 시도하지 않고, 빠르게 실패(fail fast)해서 호출자 자원을 보호한다”입니다. 많은 호출자가 느린/불능 공급자를 계속 호출하면 호출자 쪽 자원이 고갈되어 연쇄 장애(cascading failure)로 번진다는 문제를 직접 언급합니다.[^5]

AWS Prescriptive Guidance도 circuit breaker가 “반복된 timeout/failure가 있는 호출을 재시도하지 않도록 막아” 동기 호출에서의 cascade를 예방한다고 설명합니다.[^6]

정리하면, 39분 degraded는 “짧아서 괜찮다”가 아니라 “짧아서 재시도 증폭이 더 잘 난다”에 가깝습니다.

## 에러버짓 관점에서 39분을 다시 계산하기: ‘다운타임’이 아니라 ‘소진 속도’

많은 팀이 99.9% 같은 가용성 목표를 말로만 들고 있는데, 숫자로 환산하면 감각이 달라집니다.

Google Cloud 블로그는 30일(43,200분) 기준 99.9%는 월 다운타임 예산이 43.2분이라고 계산 예시를 듭니다.[^7]

즉, 시간 기반으로만 보더라도 “39분”은 99.9% 월 예산(43.2분)의 약 90%입니다.

- 월 총 시간: 43,200분
- 99.9% error budget: 0.1% = 43.2분
- 39분 / 43.2분 ≈ 90.3%

여기서 흔한 반론은 “그건 완전 다운타임일 때 얘기고, elevated errors면 덜 태운다”입니다. 맞는 말인데, 그래서 요청 기반으로 봐야 합니다.

요청 기반 SLI로 바꾸면 계산은 이렇게 됩니다.

- 목표: `success_rate >= 99.9%`
- error budget(요청): `total_requests * 0.1%`

39분 동안 트래픽이 피크였고(유료 사용자 활동 시간대), 오류율이 5%만 나도 그 구간의 실패 요청 수는 상당합니다. 반대로 트래픽이 적을 때 오류율이 높아도 “요청 수” 기준으로는 덜 태울 수 있습니다.

중요한 건 “장애가 몇 분이었나”보다 “그 시간에 얼마만큼의 유효 사용자 행동이 실패했나”입니다. 이게 제품 지표와 더 잘 맞습니다.

알림 정책도 “시간”이 아니라 “버짓 소진 속도(burn rate)”로 설계해야 합니다. Google SRE Workbook은 multi-window, multi-burn-rate 알림을 권장하면서, 예를 들어 14.4x burn rate를 1h/5m 윈도우로 같이 확인해 paging하는 패턴을 제시합니다.[^8]

이걸 이번 사건에 대입하면 해석이 명확해집니다.

- 39분 degraded가 “그냥 지나가는” 게 아니라
- “에러버짓을 빠르게 소진하는 이벤트”면 바로 대응해야 합니다.

특히 외부 LLM 의존 서비스라면, 장애 자체를 막을 수 없을 때가 많습니다. 그때 운영의 목표는 원인을 제거하는 것보다 “우리 서비스의 버짓 소진 속도를 통제”하는 쪽으로 이동합니다.

## ‘외부 LLM 의존’ 서비스에서 SLO를 쪼개는 방법: 플랜 × 기능 × 의존성

OpenAI Status 한 줄이 던지는 메시지는, SLO가 단일 숫자로는 운영에 도움이 안 된다는 점입니다. 나는 아래 3축으로 쪼개는 편을 선호합니다.

### 1) 플랜별 SLO

- Free
- Paid(Plus/Pro에 준하는 유료)
- Enterprise

유료 플랜은 SLO 목표치를 더 높게 잡기보다, **별도 에러버짓을 따로 운영**하는 게 효과적입니다. 유료 장애가 무료 장애에 평균으로 섞이면, 내부 의사결정이 계속 늦어집니다.

### 2) 기능별 SLO(사용자 여정 단위)

Conversations 같은 덩어리가 아니라 실제 여정을 기준으로 분해합니다.

- `Send message` 성공률
- `Start stream` 성공률
- `Complete stream` 성공률
- `Open conversation history` 성공률

이 방식은 “degraded지만 쓸 수는 있음” 같은 애매한 상태를 정량화하기 좋습니다.

### 3) 의존성별 SLO(우리 SLO를 ‘재무제표’처럼 합산)

외부 LLM이든, 벡터 DB든, 결제든, 의존성은 각자 실패합니다. 중요한 건 우리 사용자 여정 SLO가 의존성 실패를 포함한 end-to-end로 정의되어야 한다는 점입니다.

여기서 운영 난이도가 올라가는 포인트가 하나 있습니다. OpenAI Status는 aggregate를 기본값으로 제공합니다.[^1] 그래서 “우리 사용자의 실제 실패”와 “벤더의 공개 status”가 1:1로 매칭되지 않을 수 있습니다.

결국 필요한 건 벤더 status가 아니라, **우리 사용자 여정에서 관측한 실패율**입니다. 벤더 status는 원인 추정과 커뮤니케이션에 도움이 되지만, SLO/에러버짓의 회계 장부는 우리 관측으로 써야 합니다.

이 관점은 예전에 비용 최적화 얘기할 때 썼던 “캐시 히트율이 비용을 좌우한다”와 구조가 닮아 있습니다. 프롬프트 캐싱을 다룬 글에서 비용을 숫자로 분해했듯이, 가용성도 숫자로 분해해야 팀이 같은 언어로 얘기합니다: [프롬프트 캐싱으로 LLM 비용 50~90% 줄이기: OpenAI·Anthropic 실전 설계와 히트율 최적화](https://daewooki.github.io/posts/llm-5090-2026-6-openaianthropic-2/)

## 실행 가능한 예시: retry budget + jitter + circuit breaker를 LLM gateway에 넣기

ChatGPT 제품 장애와 똑같은 환경을 재현할 수는 없지만, “외부 LLM이 39분 동안 elevated errors를 뿜을 때 우리 서비스가 어떻게 망가지는지”는 로컬에서 충분히 실험할 수 있습니다.

아래 코드는 두 가지 HTTP 엔드포인트를 한 프로세스에 둡니다.

- `/mock/llm`: 외부 LLM을 흉내 내는 mock. 확률적으로 500을 반환하거나 지연을 넣습니다.
- `/chat`: 우리 서비스의 LLM gateway. mock을 외부 의존성처럼 호출합니다.

핵심은 세 가지입니다.

1) **exponential backoff + full jitter**로 재시도를 분산
2) 전체 트래픽 관점에서 재시도를 제한하는 retry budget(토큰 버킷)
3) 연속 실패가 나면 circuit breaker로 fail fast

### 프로젝트 구조

```text
llm-gateway/
  go.mod
  main.go
```

### go.mod

```go
module example.com/llm-gateway

go 1.22
```

### main.go

```go
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"sync"
	"sync/atomic"
	"time"
)

// -------------------------------
// Retry budget (token bucket)
// -------------------------------

type RetryBudget struct {
	capacity int64
	tokens   atomic.Int64
	refillEvery time.Duration
	refillAmount int64
}

func NewRetryBudget(capacity int64, refillEvery time.Duration, refillAmount int64) *RetryBudget {
	rb := &RetryBudget{capacity: capacity, refillEvery: refillEvery, refillAmount: refillAmount}
	rb.tokens.Store(capacity)
	go func() {
		t := time.NewTicker(refillEvery)
		defer t.Stop()
		for range t.C {
			for {
				cur := rb.tokens.Load()
				next := cur + refillAmount
				if next > rb.capacity {
					next = rb.capacity
				}
				if rb.tokens.CompareAndSwap(cur, next) {
					break
				}
			}
		}
	}()
	return rb
}

func (rb *RetryBudget) TrySpend(n int64) bool {
	for {
		cur := rb.tokens.Load()
		if cur < n {
			return false
		}
		if rb.tokens.CompareAndSwap(cur, cur-n) {
			return true
		}
	}
}

// -------------------------------
// Simple circuit breaker
// - consecutive failures threshold
// - open for openTimeout
// - half-open allows probe calls
// -------------------------------

type BreakerState int

const (
	Closed BreakerState = iota
	Open
	HalfOpen
)

type CircuitBreaker struct {
	mu sync.Mutex
	state BreakerState
	consecutiveFailures int
	failThreshold int
	openUntil time.Time
	openTimeout time.Duration
	halfOpenMaxProbes int
	halfOpenProbes int
}

var (
	ErrCircuitOpen = errors.New("circuit breaker is open")
)

func NewCircuitBreaker(failThreshold int, openTimeout time.Duration, halfOpenMaxProbes int) *CircuitBreaker {
	return &CircuitBreaker{
		state: Closed,
		failThreshold: failThreshold,
		openTimeout: openTimeout,
		halfOpenMaxProbes: halfOpenMaxProbes,
	}
}

func (cb *CircuitBreaker) allowLocked(now time.Time) bool {
	switch cb.state {
	case Closed:
		return true
	case Open:
		if now.After(cb.openUntil) {
			cb.state = HalfOpen
			cb.halfOpenProbes = 0
			return true
		}
		return false
	case HalfOpen:
		if cb.halfOpenProbes >= cb.halfOpenMaxProbes {
			return false
		}
		cb.halfOpenProbes++
		return true
	default:
		return false
	}
}

func (cb *CircuitBreaker) onSuccessLocked() {
	cb.consecutiveFailures = 0
	cb.state = Closed
}

func (cb *CircuitBreaker) onFailureLocked(now time.Time) {
	cb.consecutiveFailures++
	if cb.state == HalfOpen {
		cb.state = Open
		cb.openUntil = now.Add(cb.openTimeout)
		return
	}
	if cb.consecutiveFailures >= cb.failThreshold {
		cb.state = Open
		cb.openUntil = now.Add(cb.openTimeout)
	}
}

func (cb *CircuitBreaker) Execute(ctx context.Context, fn func(context.Context) ([]byte, int, error)) ([]byte, int, error) {
	now := time.Now()
	cb.mu.Lock()
	allowed := cb.allowLocked(now)
	cb.mu.Unlock()
	if !allowed {
		return nil, 0, ErrCircuitOpen
	}

	body, status, err := fn(ctx)
	now = time.Now()
	cb.mu.Lock()
	defer cb.mu.Unlock()
	if err == nil && status < 500 && status != 429 {
		cb.onSuccessLocked()
		return body, status, nil
	}
	cb.onFailureLocked(now)
	return body, status, err
}

// -------------------------------
// Backoff with full jitter
// delay = rand(0, min(cap, base*2^attempt))
// -------------------------------

func fullJitterDelay(base, cap time.Duration, attempt int) time.Duration {
	exp := base * time.Duration(1<<attempt)
	if exp > cap {
		exp = cap
	}
	if exp <= 0 {
		return 0
	}
	return time.Duration(rand.Int63n(int64(exp)))
}

// -------------------------------
// Mock upstream: /mock/llm
// -------------------------------

type MockConfig struct {
	FailRate float64       `json:"failRate"`
	MinDelayMillis int     `json:"minDelayMillis"`
	MaxDelayMillis int     `json:"maxDelayMillis"`
}

var mockCfg atomic.Value // holds MockConfig

func handleMockLLM(w http.ResponseWriter, r *http.Request) {
	cfg := mockCfg.Load().(MockConfig)
	// random delay
	if cfg.MaxDelayMillis > 0 {
		minD := cfg.MinDelayMillis
		maxD := cfg.MaxDelayMillis
		if maxD < minD {
			maxD = minD
		}
		d := minD
		if maxD > minD {
			d = minD + rand.Intn(maxD-minD)
		}
		time.Sleep(time.Duration(d) * time.Millisecond)
	}

	if rand.Float64() < cfg.FailRate {
		w.WriteHeader(http.StatusInternalServerError)
		fmt.Fprintf(w, "mock upstream error")
		return
	}

	b, _ := io.ReadAll(r.Body)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, `{"answer":"ok","echo":%q}`, string(b))
}

func handleMockConfig(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	var cfg MockConfig
	if err := json.NewDecoder(r.Body).Decode(&cfg); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		fmt.Fprintf(w, "bad json: %v", err)
		return
	}
	mockCfg.Store(cfg)
	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, "ok")
}

// -------------------------------
// Gateway: /chat
// -------------------------------

type ChatReq struct {
	ConversationID string `json:"conversationId"`
	MessageID      string `json:"messageId"`
	Prompt         string `json:"prompt"`
}

type ChatResp struct {
	Answer string `json:"answer"`
	UpstreamStatus int `json:"upstreamStatus"`
	Attempts int `json:"attempts"`
	Degraded bool `json:"degraded"`
	Err string `json:"err,omitempty"`
}

// naive in-memory idempotency (demo purpose)
var idem sync.Map // key -> []byte

func main() {
	rand.Seed(time.Now().UnixNano())
	mockCfg.Store(MockConfig{FailRate: 0.0, MinDelayMillis: 50, MaxDelayMillis: 120})

	budget := NewRetryBudget(200, 1*time.Second, 50) // capacity 200 tokens, refill 50/sec
	breaker := NewCircuitBreaker(8, 15*time.Second, 3)

	client := &http.Client{Timeout: 8 * time.Second}

	http.HandleFunc("/mock/llm", handleMockLLM)
	http.HandleFunc("/mock/config", handleMockConfig)

	http.HandleFunc("/chat", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}

		var req ChatReq
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			fmt.Fprintf(w, "bad json: %v", err)
			return
		}
		key := req.ConversationID + ":" + req.MessageID
		if v, ok := idem.Load(key); ok {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write(v.([]byte))
			return
		}

		ctx := r.Context()
		attempts := 0
		degraded := false
		var lastStatus int
		var lastErr error

		call := func(ctx context.Context) ([]byte, int, error) {
			attempts++
			payload, _ := json.Marshal(req)
			hreq, _ := http.NewRequestWithContext(ctx, http.MethodPost, "http://127.0.0.1:8080/mock/llm", io.NopCloser(bytesReader(payload)))
			hreq.Header.Set("Content-Type", "application/json")
			resp, err := client.Do(hreq)
			if err != nil {
				return nil, 0, err
			}
			defer resp.Body.Close()
			b, _ := io.ReadAll(resp.Body)
			return b, resp.StatusCode, nil
		}

		// breaker outside: protects caller resources and limits herd behavior
		var body []byte
		body, lastStatus, lastErr = breaker.Execute(ctx, func(ctx context.Context) ([]byte, int, error) {
			// inner retries with budget + jitter
			maxAttempts := 3
			base := 150 * time.Millisecond
			capDelay := 2 * time.Second

			var b []byte
			var st int
			var err error
			for i := 0; i < maxAttempts; i++ {
				b, st, err = call(ctx)
				if err == nil && st < 500 && st != 429 {
					return b, st, nil
				}

				// retry gate
				if i == maxAttempts-1 {
					break
				}
				// spend from global retry budget (each retry costs 1 token)
				if !budget.TrySpend(1) {
					degraded = true
					break
				}
				d := fullJitterDelay(base, capDelay, i)
				select {
				case <-time.After(d):
				case <-ctx.Done():
					return nil, 0, ctx.Err()
				}
			}
			return b, st, err
		})

		resp := ChatResp{Attempts: attempts, UpstreamStatus: lastStatus, Degraded: degraded}
		if lastErr != nil {
			resp.Err = lastErr.Error()
		}

		if lastErr == nil && lastStatus == 200 {
			resp.Answer = string(body)
			out, _ := json.Marshal(resp)
			idem.Store(key, out)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write(out)
			return
		}

		// fail fast surface; do not hide it as 200
		w.Header().Set("Content-Type", "application/json")
		if errors.Is(lastErr, ErrCircuitOpen) {
			w.WriteHeader(http.StatusServiceUnavailable)
		} else {
			w.WriteHeader(http.StatusBadGateway)
		}
		out, _ := json.Marshal(resp)
		w.Write(out)
		log.Printf("chat failed conv=%s msg=%s attempts=%d upstream=%d err=%v degraded=%v", req.ConversationID, req.MessageID, attempts, lastStatus, lastErr, degraded)
	})

	log.Printf("listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}

// bytesReader avoids importing bytes for a tiny helper (keeps demo self-contained)
type br struct { b []byte; i int }
func bytesReader(b []byte) *br { return &br{b: b} }
func (r *br) Read(p []byte) (int, error) {
	if r.i >= len(r.b) { return 0, io.EOF }
	n := copy(p, r.b[r.i:])
	r.i += n
	return n, nil
}
```

### 실행 방법

```bash
cd llm-gateway
go run .
```

다른 터미널에서 mock을 30% 실패로 바꿉니다.

```bash
curl -X POST http://127.0.0.1:8080/mock/config \
  -H 'content-type: application/json' \
  -d '{"failRate":0.30,"minDelayMillis":200,"maxDelayMillis":700}'
```

이제 `/chat`을 여러 번 호출합니다.

```bash
curl -s http://127.0.0.1:8080/chat \
  -H 'content-type: application/json' \
  -d '{"conversationId":"c-1","messageId":"m-1","prompt":"hello"}' | jq
```

예상되는 관찰 포인트는 이렇습니다.

- 실패율이 올라가면 attempts가 2~3까지 증가
- retry budget이 바닥나면 degraded=true가 뜨면서 재시도 자체를 중단
- 연속 실패가 쌓이면 breaker가 열리고(ErrCircuitOpen), 그 순간부터는 upstream 호출 없이 빠르게 503이 떨어짐
- messageId를 동일하게 반복 호출하면 idempotency 캐시로 같은 결과를 즉시 반환(중복 과금/중복 결과를 막는 첫 단계)

이 예시는 간단하지만, 39분 degraded에서 현실적으로 터지는 실패 모드(재시도 증폭, 호출자 자원 고갈, 중복 요청, 복구 구간 과부하)를 한 번에 보여줍니다.

## 반론과 회의론: “39분이면 사용자는 금방 잊는다”가 틀리는 조건

짧은 장애가 항상 치명적인 건 아닙니다. 다만 아래 조건이 겹치면 39분이 길게 남습니다.

1) 유료 플랜에서만 발생
- 실패 경험이 “돈 냈는데 안 됨”으로 각인
- 해지/환불/대체재 탐색 행동으로 이어질 확률 상승

2) 핵심 플로우에서 발생
- Conversations처럼 제품의 중심 기능에서 발생하면, “서비스 품질” 자체를 다시 평가하게 만듦

3) 클라이언트 재시도가 aggressive함
- 순간 장애가 복구 구간까지 부하를 끌고 가며 체감 시간을 늘림

4) 장애가 ‘응답 지연 + 일부 실패’ 형태임
- 사용자는 완전 장애보다 부분 실패를 더 여러 번 경험(전송→실패→재시도→부분 응답→다시 실패)
- 반복 경험은 신뢰를 깎는 속도가 빠름

“짧으니 괜찮다”는 말은, 사실 “우리 제품이 신뢰 자산을 충분히 축적했고, 그날 실패가 핵심 플로우가 아니었고, 재시도가 폭주하지 않았고, 유료 코호트가 아니었다”는 전제가 숨어 있을 때만 성립합니다.

## 앞으로 지켜볼 것: Status 한 줄이 남기는 기술적 질문들

이번 기록만으로 원인을 단정할 수는 없지만, 운영 관점에서는 질문을 만들 수 있습니다.

- 왜 Plus/Pro만 영향이 있었나(라우팅/기능 flag/모델 선택/쿼터 정책)
- Conversations로 묶인 하위 기능 중 어디가 깨졌나(전송/스트리밍/히스토리)
- “elevated errors”의 성격은 무엇이었나(5xx, 429, timeout, websocket/stream 끊김)
- 복구 구간에서 트래픽이 튀었나(재시도 증폭이 있었나)

그리고 자사 서비스 관점으로 번역하면 더 실용적인 질문이 됩니다.

- 외부 LLM 장애가 발생했을 때 우리 쪽 retry amplification factor는 얼마인가
- 유료 코호트(혹은 high-value tenant)에서 별도 SLO/에러버짓이 정의되어 있는가
- 기능 단위로 “이 실패는 사용자 여정 실패다/아니다”를 분류할 수 있는가

## 지금 할 수 있는 일: ‘짧은 degraded’를 전제로 설계하기

정리하면, 39분짜리 degraded를 무시하지 않으려면 기술적으로는 아래 6가지를 갖춰야 합니다.

1) 플랜/테넌트별 SLI 분리
- 평균값으로 장애를 숨기지 않게 만드는 최소 장치

2) 사용자 여정 단위 SLI 정의
- Conversations 같은 큰 컴포넌트가 아니라, 메시지 전송/스트리밍 완료 같은 실제 행동을 분모로 삼기

3) retry budget 도입
- “한 요청의 재시도 횟수 제한”이 아니라 “시스템 전체가 재시도로 추가로 허용하는 부하”를 제한

4) exponential backoff + jitter 표준화
- 고정 간격 재시도 금지, full jitter 기본값화(AWS가 반복해서 강조하는 부분)[^3]

5) circuit breaker로 fail fast
- 호출자 자원(스레드/커넥션/큐)을 보호하고 cascade를 차단(Fowler가 지적한 핵심)[^5]

6) 버짓 소진 속도 기반 알림
- multi-window, multi-burn-rate 같은 패턴으로 “39분짜리”를 조기에 감지하고, 버짓이 태워지는 속도에 비례해 대응 강도를 조정[^8]

이 사건의 요지는 “OpenAI가 39분 장애를 냈다”가 아니라, LLM이 핵심 플로우인 제품에서 짧은 degraded가 플랜별 신뢰와 에러버짓을 빠르게 소진시키는 구조가 이미 보편화됐다는 점입니다.

## 참고 자료

- [OpenAI Status: Increased error rate for Plus and Pro users (ChatGPT Conversations)](https://status.openai.com/incidents/01M348TX2DX7KPM9X857N4APNV)
- [Google SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Google SRE Book: Availability Table](https://sre.google/sre-book/availability-table/)
- [Google Cloud Blog: What is availability and what does it mean](https://cloud.google.com/blog/products/gcp/available-or-not-that-is-the-question-cre-life-lessons)
- [Google SRE Workbook: Error Budget Policy](https://sre.google/workbook/error-budget-policy/)
- [Google SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [AWS Well-Architected Framework: Control and limit retry calls](https://docs.aws.amazon.com/wellarchitected/2023-04-10/framework/rel_mitigate_interaction_failure_limit_retries.html)
- [AWS SDKs and Tools: Retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)
- [Martin Fowler: Circuit Breaker](https://martinfowler.com/bliki/CircuitBreaker.html)
- [AWS Prescriptive Guidance: Circuit breaker pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/circuit-breaker.html)
- [Microsoft Learn: Circuit Breaker pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)

[^1]: <https://status.openai.com/incidents/01M348TX2DX7KPM9X857N4APNV>
[^2]: <https://sre.google/sre-book/service-level-objectives/>
[^3]: <https://docs.aws.amazon.com/wellarchitected/2023-04-10/framework/rel_mitigate_interaction_failure_limit_retries.html>
[^4]: <https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html>
[^5]: <https://martinfowler.com/bliki/CircuitBreaker.html>
[^6]: <https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/circuit-breaker.html>
[^7]: <https://cloud.google.com/blog/products/gcp/available-or-not-that-is-the-question-cre-life-lessons>
[^8]: <https://sre.google/workbook/alerting-on-slos/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
