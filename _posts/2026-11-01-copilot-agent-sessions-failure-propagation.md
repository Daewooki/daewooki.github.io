---
title: "Copilot Cloud agent sessions 장애가 드러낸 에이전트 IDE/CLI의 장애 전파 경로"
description: "세션 create/list의 1~2% 부분 실패가 IDE·CLI·모바일 전체를 느리게 만드는 구조를 분해하고 프록시·레이트리밋·폴백 설계를 정리합니다."
date: 2026-11-01 14:20:56 +0900
categories: ["News", "Tools"]
tags: ["github-copilot", "resilience", "rate-limiting", "proxy", "circuit-breaker", "fallback-routing"]
render_with_liquid: false
---

## 2026-10-29(UTC) Copilot Cloud agent sessions 장애에서 확인되는 사실

GitHub Status는 2026-10-29 10:19 UTC에 “Disruption with Copilot Cloud services”를 게시했고, 10:22 UTC 업데이트에서 문제 범위를 **agent sessions service의 create/list 실패 및 지연**으로 좁혔습니다. 11:01 UTC와 11:37 UTC 업데이트에는 실패율이 1~2% 수준이며 latency가 증가했다고 명시되어 있고, 영향 범위는 web, mobile, VS Code, CLI, GitHub Copilot app의 cloud 기반 agent sessions로 적혀 있습니다. 12:33 UTC에 mitigated, 12:49 UTC에 resolved로 종료됐습니다. 이 사건에 대해 GitHub는 “상세 RCA를 추후 공유”한다고만 남겼고(작성 시점인 2026-11-01 KST 기준), 원인은 공개되지 않았습니다.[^1]

여기서 중요한 건 “완전 장애가 아닌 1~2% 실패”라는 표현입니다. 내 경험상 개발자 도구에서 1~2% 실패는 체감상 훨씬 큰 장애로 번집니다. 이유는 간단합니다. 에이전트 기반 워크플로는 단일 요청/응답이 아니라, 세션을 중심으로 UI/CLI/백그라운드가 지속적으로 동기화하며 돌아가고, 이때 create/list 같은 control-plane 호출이 여러 클라이언트 표면에서 동시에 반복되기 때문입니다.

GitHub가 Universe 시즌에 공개한 설명도 같은 방향을 가리킵니다. “폰에서 cloud agent session을 시작하고, 데스크톱 VS Code에서 steer하고, github.com에서 확인한다”는 식으로 cross-client continuity가 전면에 나왔습니다. 이 모델이 성립하려면 결국 “세션을 만들고, 세션 목록을 빠르게 보여주고, 세션 상태를 조회/갱신하는 경로”가 안정적이어야 합니다.[^2]

## agent sessions가 개발자 도구의 control-plane이 된 배경

Copilot cloud agent는 세션을 시작하는 entrypoint가 많습니다. GitHub Docs는 GitHub(issues/Agents 탭/대시보드/Chat), GitHub Mobile, IDE, REST API, GitHub CLI, MCP Server, Jira/Slack/Teams 같은 협업 툴까지 나열합니다. 즉 “에이전트”는 IDE 플러그인 기능이 아니라, 조직의 개발 활동 전체를 가로지르는 control-plane으로 설계되어 있습니다.[^3]

CLI도 예외가 아닙니다. GitHub CLI 2.80.0+에서 `gh agent-task create/list/view`로 cloud agent 세션을 만들고 추적할 수 있다고 문서/릴리스 노트에 명시돼 있습니다. create/list/view가 곧 agent sessions의 핵심 API 표면이라는 뜻입니다.[^4]

또 하나 눈여겨볼 대목은 “cloud sessions 초기화가 2-phase”라는 점입니다. Copilot SDK 문서에는 `createSession`이 “작업을 예약(reserve)하는 즉시 resolve”되지만, 실제 worker(`copilot-agent`)가 연결되어 `session.start` 이벤트를 내기까지 1~2초가 더 걸릴 수 있다고 적혀 있습니다. 즉 세션은 원천적으로 비동기이고, UI는 그 사이를 메우기 위해 list/status/event를 계속 당깁니다. 이 구조가 부분 실패에 취약합니다.[^5]

나는 예전에 에이전트 툴링 경쟁 구도를 정리하면서(예: [에이전트가 IDE를 집어삼키는 2026년 5월](https://daewooki.github.io/posts/ide-2026-5-kirocopilotcodexcursor-1/), [Cursor·Copilot·Windsurf로 에이전트를 프로젝트에 안전하게 붙이는 튜토리얼](https://daewooki.github.io/posts/cursorcopilotwindsurf-ai-2026-6-rulesmcp-2/)) “세션”이 UI의 단위이자 과금/감사/공유의 단위가 되는 걸 위험 신호로 봤습니다. 이번 2026-10-29 장애는 그 위험이 운영 관점에서 현실화된 케이스입니다.

## 1~2% 부분 실패가 워크플로 전체로 증폭되는 전파 경로

이번 사건은 “agent sessions의 creating/listing에서 failure + latency 증가”가 핵심입니다. create/list는 겉으로는 단순한 API인데, 에이전트 워크플로에서는 이 둘이 병목이 되기 쉽습니다.[^1]

아래는 내가 현장에서 자주 보는 장애 전파 경로를 이번 사건에 맞게 분해한 것입니다. (GitHub 내부 구현이 이렇다고 단정하는 게 아니라, 이런 형태의 구조를 쓰면 왜 부분 실패가 커지는지를 설명하는 모델입니다.)

### 1) 세션 목록(list)이 “메뉴 렌더링”이 아니라 “상태 동기화 루프”가 됨

VS Code는 sessions list로 ongoing work를 모니터링하고 completed work를 정리하는 흐름을 강조합니다. 즉 목록은 단순히 과거 기록이 아니라 현재 진행 중인 작업의 상태판입니다.[^6]

CLI에서도 `/sessions`로 세션을 보고 이어서 붙는 흐름(특히 cloud continuity)이 튜토리얼로 제공됩니다. 다시 말해 list는 유저 액션 한 번이 아니라, 사용자가 VS Code/터미널을 켜 놓는 동안 지속적으로 호출될 가능성이 큽니다.[^7]

이때 list가 느려지면 사용자는 “에이전트 자체가 멈췄다”고 인식합니다. 실제 worker는 돌고 있는데 UI가 새 로그/상태를 못 가져오면 체감은 완전 장애에 가깝습니다. GitHub의 availability report에서도 “task는 완료되는데 status/results 업데이트가 늦는다”는 유형이 이미 언급된 바 있습니다. control-plane 지연이 데이터-plane(작업 실행) 정상 동작을 가려버리는 패턴입니다.[^8]

### 2) latency 증가는 동시성(concurrency)을 기하급수적으로 키움

간단한 등식 하나로 설명이 됩니다.

- 특정 클라이언트가 세션 목록을 평균적으로 초당 λ번 호출
- 목록 API의 평균 응답 시간이 L초

그러면 그 클라이언트가 동시에 붙잡고 있는 in-flight 요청 수의 기대값은 대략 `λ * L`입니다(대충 Little’s Law 형태로 보면 됩니다). 

문제는 L이 평소 200ms였다가 2초로 늘어나는 순간, 같은 호출 빈도에서도 동시성이 10배가 됩니다. 여기서 끝나지 않습니다.

- 타임아웃이 걸리면 retry가 붙고(클라이언트/SDK/프록시 어디선가)
- UI는 사용자에게 “새로고침” 버튼을 제공하거나, 백그라운드에서 다시 시도하고
- 여러 표면(IDE + CLI + web + mobile)이 동시에 같은 계정으로 붙습니다

이렇게 되면 1~2% 실패가 “실패율 1~2%”로 끝나지 않고 “동시성 폭증 + tail latency 악화 + 추가 실패 증가”로 이어집니다. 이게 내가 말하는 **부분 실패**의 증폭입니다.

### 3) retry가 여러 계층에서 중복되면 retry storm이 됨

AWS Well-Architected와 Builders’ Library는 retry를 할 때 exponential backoff + jitter를 쓰고, 최대 retry 횟수를 제한하라고 반복해서 강조합니다. 특히 중요한 문장은 “대부분의 경우 retry는 스택의 한 지점에서만 수행하라”는 종류의 권고입니다. 여러 계층에서 동시에 retry하면 회복 중인 서비스에 다시 부하를 얹어서 장애를 길게 끕니다.[^9]

에이전트 세션 create/list는 딱 이 함정에 들어가기 쉽습니다.

- 앱(IDE/CLI)이 retry
- 내부 corporate proxy가 retry
- 외부 edge proxy가 retry

이 중 2개만 겹쳐도, “실패율 1~2%”가 “요청량 +5~+20%” 같은 형태로 곧장 증폭될 수 있습니다. 그리고 증가한 요청량은 다시 latency를 밀어 올립니다.

### 4) create는 2-phase라서, 작은 지연도 사용자 행동을 바꿈

Copilot SDK 문서가 말하는 2-phase 초기화를 다시 보면:

- `createSession`이 먼저 끝남(예약)
- worker가 붙고 `session.start`가 나중에 옴

이 사이가 느려지면 사용자는 세션이 안 만들어진 것으로 보고 다시 create를 누릅니다. 혹은 UI가 알아서 “생성 중”을 갱신하려고 list/status 호출을 더 자주 합니다. 결국 create 지연은 list 트래픽을, list 지연은 create 중복을 유발할 수 있습니다.[^5]

## 사내 프록시를 둬야 하는 이유: 안정성은 클라이언트 문제로 남지 않음

Copilot/에이전트 도구를 “회사 표준 도구”로 쓰기 시작하면, 장애는 개인의 불편을 넘어 조직 생산성 비용이 됩니다. 이때 문제는 한 가지로 모입니다.

- 사내에서 Copilot을 쓰는 표면이 너무 많아서
- 각 표면에 “최적의 재시도/레이트리밋/폴백”을 강제하기가 거의 불가능

그래서 내 결론은 보통 이렇습니다.

1) 네트워크 egress에 agent 전용 gateway(프록시)를 둔다
2) 거기에서 관찰/제어/폴백을 중앙집중화한다

여기서 말하는 프록시는 단순 HTTP forward proxy가 아니라, 다음을 하는 control-plane gateway에 가깝습니다.

- per-user / per-org rate limiting
- in-flight request dedupe(singleflight)
- cache(stale-while-revalidate 포함)
- bounded retry(딱 한 계층에서)
- circuit breaker
- fallback routing(모델/런타임/기능 단위)

특히 GitHub Status가 이번 장애의 영향 표면을 web/mobile/VS Code/CLI/Copilot app까지 명시했다는 건, “한 서비스(agent sessions) 품질이 모든 표면을 같이 끌어내린다”는 현실을 인정한 표현으로 읽힙니다.[^1]

## 프록시 설계의 첫 단추: 실패를 분류할 수 있어야 한다

부분 실패가 무서운 이유는 “실패인지, 느린 성공인지, 영구 실패인지”가 섞여 보이기 때문입니다. 프록시는 최소한 다음을 구분해야 합니다.

- timeout(클라이언트/프록시/업스트림 어디에서 끊겼는지)
- upstream 5xx
- upstream 429(rate limit)
- auth/token 문제(401/403)
- policy block(조직 정책)

내가 실무에서 선호하는 방식은, 내부 클라이언트(IDE/CLI wrapper)와 사내 gateway 사이의 에러 포맷을 RFC 9457 Problem Details로 통일하는 것입니다. 그래야 UI가 “다시 시도”와 “잠시 후”와 “모델 폴백”을 구분해서 행동할 수 있습니다.[^10]

rate limit을 줄 때도 마찬가지입니다. HTTP 429에 `Retry-After`를 주면, 최소한 클라이언트가 무의미한 tight loop를 만들 가능성이 줄어듭니다.[^11]

## 레이트리밋과 retry를 어디에 둘지: 핵심은 한 군데에서만, 그리고 상한을 둔다

여기서부터는 트레이드오프가 명확합니다.

- “클라이언트가 알아서 retry하게 두자”는 접근은 표면이 많아질수록 실패합니다.
- “프록시가 다 해주자”는 접근은 프록시가 SPOF가 되고 구현이 복잡해집니다.

나는 후자를 선택하되, 프록시 자체는 최대한 단순하게 유지하는 쪽으로 설계합니다. 기준은 다음 세 가지입니다.

### 1) retry budget을 프록시에서 강제한다

Envoy는 circuit breaking에서 retry 폭주를 막는 의도를 문서에 분명히 적어두고 있습니다. “sporadic failure를 위한 retry는 허용하되, 전체 retry volume이 폭발해서 cascading failure를 만들지 않게 한다”는 문장 그대로입니다.[^12]

즉 프록시 레벨에서 “active retries 동시성 상한”, “최대 재시도 횟수”, “백오프”를 강제하고, IDE/CLI는 retry를 끄거나 최소화하는 게 더 안전합니다.

### 2) backoff는 exponential + jitter를 기본값으로 둔다

AWS는 retry에 exponential backoff + jitter를 쓰고 최대 횟수를 제한하라고 Well-Architected 항목으로 박아놓았습니다. 에이전트 세션처럼 control-plane 호출이 많은 시스템에서는 사실상 필수입니다.[^9]

여기서 중요한 실무 포인트는 “jitter가 없으면 장애 복구 순간에 동기화된 재시도가 한 번 더 폭발한다”는 점입니다. thundering herd는 개념 설명만 봐도 직관적입니다.[^13]

### 3) circuit breaker는 latency 기반으로도 열린다

대부분 팀이 circuit breaker를 “5xx가 연속으로 나오면 연다”로만 생각하는데, 이번 케이스처럼 latency가 늘어나는 장애에서는 그 접근이 늦습니다.

프록시가 해야 하는 일은 보통 두 가지입니다.

- upstream latency가 일정 수준을 넘으면 create/list를 강하게 제한(또는 폴백)
- list는 캐시를 우선 반환하고 비동기로 갱신(stale-while-revalidate)

이렇게 해야 UI가 “계속 기다리다 타임아웃 → 다시 시도”로 들어가며 시스템을 더 망가뜨리는 경로를 차단할 수 있습니다.

## 폴백 라우팅을 기능 단위로 쪼개야 한다: create와 list는 같은 서비스가 아니다

GitHub Status가 이번에 콕 집어 말한 것도 create/list였습니다.[^1]

나는 이 유형의 장애에서 폴백을 “모델 폴백” 하나로 퉁치면 실패한다고 봅니다. 이유는 agent sessions 장애는 흔히 모델 추론이 아니라 세션 control-plane에서 터지기 때문입니다. 2026-10-28(UTC) Copilot 장애는 Status 업데이트에서 “upstream model provider 문제”라고 명확히 언급하며 “다른 모델을 선택하라”는 가이드를 줬습니다. 이건 모델 폴백이 유효한 사건입니다.[^1]

반대로 2026-10-29 사건은 “agent sessions service(create/list)”입니다. 이런 경우 모델을 바꿔도 세션이 안 만들어지고 목록이 안 뜨면 소용이 없습니다.

그래서 폴백을 최소 3층으로 나눕니다.

1) **list 폴백**: 캐시/스냅샷을 반환한다(정확도보다 UX 유지)
2) **create 폴백**: (a) fallback upstream으로 라우팅하거나 (b) 큐잉 후 나중에 생성하거나 (c) local session으로 강등한다
3) **execution 폴백**: cloud agent가 막히면 local harness로 전환하거나, 정책상 허용된 다른 provider로 라우팅한다

이때 “local로 강등”은 무조건 좋은 선택이 아닙니다. 보안/데이터 유출/라이선스/정책 때문에 cloud agent만 허용하는 조직도 있습니다. GitHub Docs도 cloud agent가 조직 정책에 의해 막힐 수 있음을(예: policy_blocked 같은 유형) 언급하고 있습니다.[^5]

그래서 결국 사내 gateway가 가져야 하는 건 **폴백 라우팅** 자체가 아니라 “조직 정책에 맞는 폴백 그래프”입니다.

- 특정 repo는 local 허용
- 특정 repo는 cloud only
- 특정 네트워크(모바일 LTE)에서는 list 캐시만
- 특정 상황(429 급증)에서는 create를 큐잉

이걸 클라이언트 표면마다 따로 구현하면 6개월 뒤 유지보수가 무너집니다.

## 동작하는 예제: 부분 실패를 흡수하는 agent-session-gateway

Copilot의 실제 세션 API를 그대로 재현하긴 어렵고, 그럴 필요도 없습니다. 핵심은 “create/list가 느려지거나 일부 실패할 때, 조직 내부에서 트래픽과 UX를 어떻게 안정화할지”입니다.

아래 예제는 다음을 보여줍니다.

- upstream(가짜 agent sessions 서비스)이 1~2% 실패 + 높은 latency를 가진 상황
- gateway가
  - list는 캐시를 먼저 주고(singleflight로 중복 호출도 제거)
  - create는 timeout 후 fallback upstream으로 라우팅
  - 과도한 호출은 429 + Retry-After로 제한
  - 에러는 RFC 9457 스타일 JSON으로 통일

### 구성

- `upstream-primary`: 일부 실패/지연이 있는 upstream
- `upstream-fallback`: 상대적으로 안정적인 fallback upstream
- `gateway`: 사내 egress gateway 역할

### 1) docker-compose.yml

```yaml
services:
  upstream-primary:
    image: python:3.12-slim
    working_dir: /app
    volumes:
      - ./upstream:/app
    environment:
      - PORT=8000
      - FAIL_RATE=0.02
      - DELAY_MS=1200
    command: bash -lc "pip install -r requirements.txt && uvicorn app:app --host 0.0.0.0 --port 8000"
    ports:
      - "8001:8000"

  upstream-fallback:
    image: python:3.12-slim
    working_dir: /app
    volumes:
      - ./upstream:/app
    environment:
      - PORT=8000
      - FAIL_RATE=0.0
      - DELAY_MS=150
    command: bash -lc "pip install -r requirements.txt && uvicorn app:app --host 0.0.0.0 --port 8000"
    ports:
      - "8002:8000"

  gateway:
    image: golang:1.22
    working_dir: /src
    volumes:
      - ./gateway:/src
    environment:
      - PRIMARY_URL=http://upstream-primary:8000
      - FALLBACK_URL=http://upstream-fallback:8000
      - LIST_CACHE_TTL=15s
      - UPSTREAM_TIMEOUT=800ms
      - RATE_QPS=5
      - RATE_BURST=10
    command: bash -lc "go mod download && go run ."
    ports:
      - "8080:8080"
    depends_on:
      - upstream-primary
      - upstream-fallback
```

### 2) upstream (FastAPI) - upstream/requirements.txt

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
```

### 3) upstream (FastAPI) - upstream/app.py

```python
import os
import random
import time
from fastapi import FastAPI, HTTPException

app = FastAPI()

FAIL_RATE = float(os.getenv("FAIL_RATE", "0.0"))
DELAY_MS = int(os.getenv("DELAY_MS", "0"))

# 매우 단순한 in-memory 세션 저장소
SESSIONS = []

@app.get("/sessions")
def list_sessions():
    _inject_faults()
    return {"sessions": list(reversed(SESSIONS))[:50]}

@app.post("/sessions")
def create_session(payload: dict):
    _inject_faults()
    session_id = f"s_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    item = {
        "id": session_id,
        "title": payload.get("title", "untitled"),
        "repo": payload.get("repo", "unknown"),
        "created_at_ms": int(time.time() * 1000),
    }
    SESSIONS.append(item)
    return item

def _inject_faults():
    if DELAY_MS > 0:
        time.sleep(DELAY_MS / 1000)

    if FAIL_RATE > 0 and random.random() < FAIL_RATE:
        raise HTTPException(status_code=500, detail="upstream_error")
```

### 4) gateway (Go) - gateway/go.mod

```go
module agent-session-gateway

go 1.22

require golang.org/x/sync v0.8.0

require golang.org/x/time v0.6.0
```

### 5) gateway (Go) - gateway/main.go

```go
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"golang.org/x/sync/singleflight"
	"golang.org/x/time/rate"
)

type Problem struct {
	Type   string `json:"type"`
	Title  string `json:"title"`
	Status int    `json:"status"`
	Detail string `json:"detail,omitempty"`
	Trace  string `json:"trace_id,omitempty"`
}

type CacheItem struct {
	Body      []byte
	ExpiresAt time.Time
}

type Server struct {
	PrimaryURL   string
	FallbackURL  string
	HTTPClient   *http.Client
	ListTTL      time.Duration
	Limiter      *rate.Limiter
	SF           singleflight.Group
	Mu           sync.Mutex
	ListCache    CacheItem
}

func main() {
	primary := mustEnv("PRIMARY_URL")
	fallback := mustEnv("FALLBACK_URL")
	listTTL := mustDuration(getEnv("LIST_CACHE_TTL", "15s"))
	timeout := mustDuration(getEnv("UPSTREAM_TIMEOUT", "800ms"))
	qps := mustInt(getEnv("RATE_QPS", "5"))
	burst := mustInt(getEnv("RATE_BURST", "10"))

	s := &Server{
		PrimaryURL:  primary,
		FallbackURL: fallback,
		HTTPClient: &http.Client{
			Timeout: timeout,
		},
		ListTTL: listTTL,
		Limiter: rate.NewLimiter(rate.Limit(qps), burst),
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/v1/sessions", s.handleSessions)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) })

	addr := ":8080"
	log.Printf("gateway listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, withTrace(withLogging(mux))))
}

func (s *Server) handleSessions(w http.ResponseWriter, r *http.Request) {
	if !s.Limiter.Allow() {
		w.Header().Set("Retry-After", "2")
		writeProblem(w, Problem{
			Type:   "https://example.internal/problems/rate-limited",
			Title:  "rate limited",
			Status: 429,
			Detail: "too many requests to agent sessions gateway",
			Trace:  traceIDFromCtx(r.Context()),
		})
		return
	}

	switch r.Method {
	case http.MethodGet:
		s.handleList(w, r)
	case http.MethodPost:
		s.handleCreate(w, r)
	default:
		w.WriteHeader(405)
	}
}

func (s *Server) handleList(w http.ResponseWriter, r *http.Request) {
	// 캐시가 살아있으면 즉시 반환
	if body, ok := s.getListCache(); ok {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Cache", "HIT")
		w.WriteHeader(200)
		w.Write(body)
		return
	}

	// 중복 호출은 singleflight로 묶어서 upstream 압력을 줄인다
	v, err, _ := s.SF.Do("list", func() (any, error) {
		body, err := s.getUpstream(r.Context(), s.PrimaryURL+"/sessions")
		if err != nil {
			// list는 fallback도 가능하지만, 여기서는 cache-first 전략을 강조하기 위해
			// fallback보다 "stale"을 우선한다.
			if stale, ok := s.getListCacheStale(); ok {
				return map[string]any{"body": stale, "stale": true}, nil
			}
			return nil, err
		}
		s.setListCache(body)
		return map[string]any{"body": body, "stale": false}, nil
	})

	if err != nil {
		writeProblem(w, Problem{
			Type:   "https://example.internal/problems/upstream-unavailable",
			Title:  "agent sessions upstream unavailable",
			Status: 503,
			Detail: err.Error(),
			Trace:  traceIDFromCtx(r.Context()),
		})
		return
	}

	m := v.(map[string]any)
	body := m["body"].([]byte)
	stale := m["stale"].(bool)

	w.Header().Set("Content-Type", "application/json")
	if stale {
		w.Header().Set("X-Cache", "STALE")
	} else {
		w.Header().Set("X-Cache", "MISS")
	}
	w.WriteHeader(200)
	w.Write(body)
}

func (s *Server) handleCreate(w http.ResponseWriter, r *http.Request) {
	payload, err := io.ReadAll(r.Body)
	if err != nil {
		writeProblem(w, Problem{Type: "about:blank", Title: "bad request", Status: 400, Detail: err.Error(), Trace: traceIDFromCtx(r.Context())})
		return
	}

	// 1) primary에 시도
	body, err := s.postUpstream(r.Context(), s.PrimaryURL+"/sessions", payload)
	if err == nil {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Upstream", "primary")
		w.WriteHeader(201)
		w.Write(body)
		return
	}

	// 2) 실패하면 fallback으로 1회만 시도 (bounded retry)
	body, err2 := s.postUpstream(r.Context(), s.FallbackURL+"/sessions", payload)
	if err2 == nil {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Upstream", "fallback")
		w.WriteHeader(201)
		w.Write(body)
		return
	}

	writeProblem(w, Problem{
		Type:   "https://example.internal/problems/create-failed",
		Title:  "failed to create session",
		Status: 503,
		Detail: fmt.Sprintf("primary=%v; fallback=%v", err, err2),
		Trace:  traceIDFromCtx(r.Context()),
	})
}

func (s *Server) getUpstream(ctx context.Context, url string) ([]byte, error) {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	resp, err := s.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 500 {
		return nil, errors.New("upstream 5xx")
	}
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("unexpected upstream status=%d", resp.StatusCode)
	}
	return b, nil
}

func (s *Server) postUpstream(ctx context.Context, url string, payload []byte) ([]byte, error) {
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, url, io.NopCloser(bytesReader(payload)))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 500 {
		return nil, errors.New("upstream 5xx")
	}
	if resp.StatusCode != 200 {
		// upstream은 200을 반환하지만 gateway는 201로 바꿔준다
		// (예제를 단순화하기 위해 upstream 구현을 그대로 둠)
	}
	return b, nil
}

func (s *Server) setListCache(body []byte) {
	s.Mu.Lock()
	defer s.Mu.Unlock()
	s.ListCache = CacheItem{Body: body, ExpiresAt: time.Now().Add(s.ListTTL)}
}

func (s *Server) getListCache() ([]byte, bool) {
	s.Mu.Lock()
	defer s.Mu.Unlock()
	if s.ListCache.Body == nil {
		return nil, false
	}
	if time.Now().After(s.ListCache.ExpiresAt) {
		return nil, false
	}
	return s.ListCache.Body, true
}

func (s *Server) getListCacheStale() ([]byte, bool) {
	s.Mu.Lock()
	defer s.Mu.Unlock()
	if s.ListCache.Body == nil {
		return nil, false
	}
	return s.ListCache.Body, true
}

func writeProblem(w http.ResponseWriter, p Problem) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(p.Status)
	json.NewEncoder(w).Encode(p)
}

func withLogging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Printf("method=%s path=%s dur=%s trace=%s", r.Method, r.URL.Path, time.Since(start), traceIDFromCtx(r.Context()))
	})
}

type ctxKey string

const traceKey ctxKey = "trace_id"

func withTrace(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		trace := r.Header.Get("X-Request-Id")
		if trace == "" {
			trace = newTraceID()
		}
		ctx := context.WithValue(r.Context(), traceKey, trace)
		w.Header().Set("X-Request-Id", trace)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func traceIDFromCtx(ctx context.Context) string {
	v := ctx.Value(traceKey)
	if v == nil {
		return ""
	}
	return v.(string)
}

func newTraceID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func mustEnv(k string) string {
	v := os.Getenv(k)
	if v == "" {
		panic("missing env " + k)
	}
	return v
}

func getEnv(k, def string) string {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	return v
}

func mustDuration(v string) time.Duration {
	d, err := time.ParseDuration(v)
	if err != nil {
		panic(err)
	}
	return d
}

func mustInt(v string) int {
	i, err := strconv.Atoi(v)
	if err != nil {
		panic(err)
	}
	return i
}

type bytesReader []byte

func (b bytesReader) Read(p []byte) (int, error) {
	if len(b) == 0 {
		return 0, io.EOF
	}
	n := copy(p, b)
	return n, nil
}

func (b bytesReader) Close() error { return nil }
```

위 코드에서 의도한 포인트는 네 가지입니다.

- list는 cache-first로 UX를 살린다
- list는 singleflight로 upstream 중복 호출을 없앤다
- create는 primary 실패 시 fallback 1회만 시도한다(무한 retry 금지)
- rate limit은 gateway에서 중앙 통제한다

실제 Copilot에 붙이려면 인증 토큰 처리, 테넌트/사용자 식별, 로그 마스킹, TLS, allowlist 등이 더 필요하지만, 장애 전파를 끊는 골격은 이 정도로도 실험이 가능합니다.

### 6) 실행 방법과 예상 출력

```bash
docker compose up --build
```

list 호출:

```bash
curl -i http://localhost:8080/v1/sessions
```

예상되는 헤더 패턴:

- 첫 호출: `X-Cache: MISS` (upstream을 한 번 호출)
- TTL 내 반복 호출: `X-Cache: HIT` (gateway가 즉시 반환)
- TTL이 지난 시점에 upstream이 느리거나 실패: `X-Cache: STALE` (stale 캐시로 UX 유지)

create 호출:

```bash
curl -i -X POST http://localhost:8080/v1/sessions \
  -H 'Content-Type: application/json' \
  -d '{"title":"refactor auth flow","repo":"acme/payments"}'
```

예상되는 헤더 패턴:

- 정상: `X-Upstream: primary`
- primary가 timeout/5xx: `X-Upstream: fallback`

rate limit 초과 시:

- HTTP 429
- `Retry-After: 2`
- `application/problem+json` body

이 실험에서 중요한 관찰 지표는 “upstream-primary의 latency/실패가 있어도 gateway가 list 경로를 빠르게 응답해주는지”, 그리고 “create가 무한정 쌓이지 않게 상한이 걸리는지”입니다.

## 반론과 회의론: 사내 프록시는 만능이 아니다

프록시를 두면 좋아 보이지만, 실제로는 다음 반론이 성립합니다.

### 1) 프록시가 또 하나의 장애 지점이 된다

특히 IDE/CLI가 프록시에 강하게 결합되면, 프록시 장애가 곧 전사 장애입니다. 이건 사실입니다.

그래서 프록시는 기능을 욕심내기 시작하는 순간 망가집니다. cache, rate limit, 단일 fallback 정도까지만 하고, “세션 상태를 재구성한다” 같은 고난도 기능(예: session log를 재조립)은 하지 않는 편이 낫습니다.

### 2) 폴백이 라이선스/보안/감사 요구사항을 깨뜨릴 수 있다

cloud agent의 장점 중 하나는 “실행 환경이 GitHub 호스팅 compute로 고정”된다는 점입니다. VS Code 문서도 cloud session을 “managed execution environment”로 설명합니다.[^14]

이때 로컬 폴백(예: local model, local harness)이 켜지면 데이터가 개발자 노트북으로 내려옵니다. 어떤 조직에선 이게 곧 정책 위반입니다.

그래서 폴백은 기술 문제가 아니라 정책 그래프 문제고, gateway는 그 그래프를 강제하는 위치에 있어야 합니다.

### 3) “모델 폴백”과 “세션 폴백”을 혼동하기 쉽다

2026-10-28 사건처럼 model provider 이슈는 모델을 바꾸는 게 직접적인 해결책일 수 있습니다. GitHub Status도 그 방향으로 안내했습니다.[^1]

하지만 2026-10-29 사건처럼 세션 create/list가 망가지면 모델을 바꿔도 체감이 안 바뀝니다. 이 둘을 같은 장애로 다루면 폴백 설계가 실패합니다.

## 앞으로 지켜볼 것: GitHub가 공개할 RCA에서 봐야 하는 포인트

GitHub는 이번 사건의 RCA를 “가능한 한 빨리 공유하겠다”고만 썼습니다.[^1]

RCA가 나오면 내 관점에서 확인하고 싶은 건 다음입니다.

1) create/list 중 어떤 경로가 먼저 무너졌는지
2) 1~2% 실패가 특정 region/특정 tier/특정 클라이언트에서 치우쳤는지
3) mitigation이 무엇이었는지(캐시 플러시, 롤백, rate limit, DB failover, queue drain 등)
4) cross-client continuity가 붙으면서 list 트래픽 프로파일이 바뀌었는지

특히 Copilot SDK 문서가 말하는 2-phase 초기화(`createSession` vs `session.start`) 특성상, `session.start` 지연이 list 트래픽과 결합되면 제일 먼저 tail latency가 폭발할 가능성이 큽니다.[^5]

## 지금 할 수 있는 일: 사내 프록시/레이트리밋/폴백 모델 라우팅의 최소 단위

뉴스 분석을 실무 설계로 가져가면 결국 체크리스트로 떨어집니다. 여기서의 요점은 “거대한 플랫폼을 만드는 것”이 아니라, 장애 전파를 끊는 최소 단위를 확보하는 것입니다.

1) egress 단에서 create/list 트래픽을 한 군데로 모은다(관찰 가능성 확보)
2) list는 cache-first로 만들고 stale 응답을 허용한다(UX 방어)
3) retry는 한 계층에서만 하고, exponential backoff + jitter + 상한을 둔다[^9]
4) rate limit은 429 + Retry-After로 클라이언트를 느리게 만든다[^11]
5) create 폴백은 “다른 모델”이 아니라 “다른 실행 경로/다른 세션 서비스/큐잉/강등”으로 나눈다

이번 2026-10-29 사건이 흥미로운 이유는, 장애 원인이 무엇이든 간에 “agent sessions create/list가 느려지는 순간, IDE/CLI/모바일이 같이 느려지는 구조”가 이미 제품 설계로 굳어졌다는 점입니다. 그래서 대응도 개별 클라이언트 최적화가 아니라, 조직 경계에서의 트래픽/폴백 제어로 가는 편이 비용 대비 효과가 더 큽니다.

## 참고 자료

- [GitHub Status: Disruption with Copilot Cloud services (Oct 29, 2026)](https://www.githubstatus.com/?when=aug2026)
- [GitHub Changelog: GitHub Copilot in VS Code, Universe releases (2026-10-28)](https://github.blog/changelog/2026-10-28-github-copilot-in-vs-code-universe-releases/)
- [GitHub Docs: Starting GitHub Copilot sessions](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/start-copilot-sessions)
- [GitHub Docs: Cloud sessions (Copilot SDK)](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/cloud-sessions)
- [GitHub Docs (Enterprise Cloud): Using Copilot cloud agent from the GitHub CLI](https://docs.github.com/en/enterprise-cloud%40latest/copilot/how-tos/use-copilot-agents/cloud-agent/use-cloud-agent-from-cli)
- [GitHub CLI Manual: gh agent-task](https://cli.github.com/manual/gh_agent-task)
- [VS Code Docs: Run agent sessions in the cloud](https://code.visualstudio.com/docs/agents/run/cloud-sandbox-sessions)
- [VS Code Docs: Manage agent sessions in VS Code](https://code.visualstudio.com/docs/agents/run/sessions/manage-sessions)
- [AWS Well-Architected: Control and limit retry calls (REL05-BP03)](https://docs.aws.amazon.com/wellarchitected/2023-04-10/framework/rel_mitigate_interaction_failure_limit_retries.html)
- [AWS Builders’ Library: Timeouts, retries, and backoff with jitter (PDF)](https://d1.awsstatic.com/builderslibrary/pdfs/timeouts-retries-and-backoff-with-jitter.pdf)
- [Envoy Docs: Circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking)
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [MDN: 429 Too Many Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429)

[^1]: <https://www.githubstatus.com/?when=aug2026>
[^2]: <https://github.blog/changelog/2026-10-28-github-copilot-in-vs-code-universe-releases/>
[^3]: <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/start-copilot-sessions>
[^4]: <https://docs.github.com/en/enterprise-cloud%40latest/copilot/how-tos/use-copilot-agents/cloud-agent/use-cloud-agent-from-cli>
[^5]: <https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/cloud-sessions>
[^6]: <https://code.visualstudio.com/docs/agents/run/sessions/manage-sessions>
[^7]: <https://code.visualstudio.com/docs/agents/cloud-continuity-tutorial>
[^8]: <https://github.blog/news-insights/company-news/github-availability-report-august-2026/?trk=article-ssr-frontend-pulse_little-text-block>
[^9]: <https://docs.aws.amazon.com/wellarchitected/2023-04-10/framework/rel_mitigate_interaction_failure_limit_retries.html>
[^10]: <https://www.rfc-editor.org/rfc/rfc9457.html>
[^11]: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429>
[^12]: <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking>
[^13]: <https://en.wikipedia.org/wiki/Thundering_herd_problem>
[^14]: <https://code.visualstudio.com/docs/agents/run/cloud-sandbox-sessions>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
