---
title: "Go 1.27 HTTP/1 connection reuse 최적화와 순차 요청 지연시간"
description: "순차 GET·keep-alive에서 Go 1.27이 빨라진 이유를 net/http 내부 동작과 Transport 튜닝, 재현 가능한 벤치마크로 풀어봅니다."
date: 2026-10-15 12:53:05 +0900
categories: ["Performance", "Go"]
tags: ["go", "net-http", "http1", "performance", "latency", "connection-reuse"]
render_with_liquid: false
---

## 순차 요청 워크로드에서 왜 체감이 큰가

Go 팀이 2026-10-14에 공개한 [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse) 글에서 핵심 수치가 하나 나옵니다. HTTP/1만 강제로 쓰는 조건(`GODEBUG=http2client=0`)에서, `http.Get`로 100번 순차 호출하며 상태 코드만 확인하고 `resp.Body`는 읽지 않은 채 `Close`만 하는 코드가 Go 1.26에서는 약 710ms, Go 1.27에서는 약 150ms였다는 결과입니다. 같은 코드, 같은 워크로드에서 거의 5배 차이가 납니다.

이 차이가 크게 보이는 패턴은 딱 세 가지 조건이 겹칠 때입니다.

- **순차 요청**: 동시성(concurrency)이 낮고, “요청 A가 끝나야 요청 B를 보낸다” 형태(폴링, 배치, 크론 잡, 컨트롤 플레인 호출, 리트라이 루프 등)
- **HTTP/1.1 keep-alive**: 원래라면 연결을 재사용할 수 있어야 비용이 줄어드는 상황
- **응답 body를 끝까지 읽지 않음**: 상태 코드만 보고 끝내거나, JSON을 파싱하되 마지막 `\n` 같은 잔여 바이트가 남는 형태

순차 요청에서 connection reuse가 실패하면, 성능 모델이 “한 번만 내면 되는 연결 수립 비용”에서 “요청마다 반복되는 연결 수립 비용”으로 바뀝니다. TLS가 얹힌 환경이면 TCP + TLS 핸드셰이크가 지배적이 되는 구간이 많고, cross-region이면 더 노골적으로 티가 납니다. 위 Go 블로그 글도 새 연결의 RTT 비용(TCP 1 RTT + TLS 1.2 2 RTT 같은 그림)을 이 얘기의 배경으로 둡니다. [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)

내 경험으로는 이런 패턴이 내부 서비스에도 흔합니다.

- “작업 상태 확인(status polling)”을 100ms~1s 간격으로 순차 호출
- 배치 잡이 외부 API를 1개씩 순차 호출하면서 성공/실패만 확인
- 장애 시에 circuit breaker가 half-open 상태에서 소량의 probe 요청을 순차 수행

이때 body를 다 읽지 않는 코드가 들어가면, keep-alive를 켜놨는데도 keep-alive가 사실상 꺼진 것처럼 동작합니다. Go 1.27의 변화는 이 함정을 표준 라이브러리 수준에서 상당 부분 메워줍니다.

## Go 1.27에서 바뀐 점: Close가 곧바로 “폐기”가 아니게 됨

HTTP/1에서 response는 같은 TCP 스트림 위로 **직렬**로 흘러옵니다. `net/http`가 헤더까지만 파싱하고 `Response`를 돌려줄 수는 있지만, 다음 응답의 시작점을 찾으려면 결국 현재 응답 body를 EOF까지 소비해야 합니다. 이 설명은 Go 블로그 글의 문제 정의 그대로입니다. [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)

Go 1.26까지는 `resp.Body.Close()`가 호출됐을 때 body가 남아 있으면 “이 연결은 재사용 불가”로 보고 연결을 버리는 쪽으로 기울어 있었습니다(정확히는 재사용 경로로 돌려보내기 어렵게 만들어지는 케이스가 많았습니다). 그래서 상태 코드만 확인하는 순차 GET 같은 워크로드에서 재사용이 깨지고, 매번 새 연결을 만들게 됩니다. [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)

Go 1.27부터는 기본 전략이 바뀝니다.

- HTTP/1 response body가 **EOF까지 읽히지 않은 상태에서 Close**되면
- Transport가 **백그라운드에서 남은 body를 일정 한도까지 drain**해서
- 재사용 가능한 상태(다음 응답의 시작을 읽을 수 있는 상태)로 만들 수 있으면 idle pool로 돌려보냅니다.

Go 1.27 릴리스 노트는 이를 “HTTP/1 `Response.Body`가 Close될 때 unread content를 보수적인 한도까지 자동으로 drain해서 connection reuse를 돕는다”라고 정리합니다. [Go 1.27 Release Notes](https://go.dev/doc/go1.27)

패키지 문서도 더 직접적으로 바뀌었습니다. 과거에는 “EOF까지 읽고 Close하지 않으면 재사용이 안 될 수 있다”가 사실상 교과서 문구였는데, 이제는 “대부분의 경우 manual drain이 필요 없고, Close가 보수적 한도 내에서 EOF까지 비동기로 읽어준다”라는 문장이 들어가 있습니다. [net/http package documentation](https://pkg.go.dev/net/http@go1.27.2)

핵심은 “Close는 했지만, 재사용을 위해 **조금 더 읽는 작업을 Transport가 대신**한다”입니다.

## 자동 drain의 실제 조건: 256KiB, 50ms, 그리고 ContentLength

Go 블로그 글에서 요약한 수치가 2개입니다.

- 최대 256KB
- 최대 50ms

이게 실제 구현에도 그대로 박혀 있습니다.

`net/http` 소스에는 다음 상수가 들어갑니다.

- `maxPostCloseReadBytes = 256 << 10`
- `maxPostCloseReadTime = 50 * time.Millisecond`

그리고 `maybeDrainBody`가 `io.CopyN(io.Discard, r, maxPostCloseReadBytes+1)` 형태로 drain을 시도하고, 50ms 내에 EOF를 보면 성공으로 간주합니다. [net/http transport.go](https://go.dev/src/net/http/transport.go)

여기서 중요한 디테일이 하나 더 있습니다. drain 시도 여부를 결정하는 조건이 `resp.ContentLength <= maxPostCloseReadBytes`라는 점입니다. [net/http transport.go](https://go.dev/src/net/http/transport.go)

이 조건은 두 가지 함의를 가집니다.

1) Content-Length가 명시되어 있고 256KiB를 넘으면 아예 drain을 시도하지 않을 가능성이 큽니다. 즉, “큰 body는 굳이 다운로드해서 버리느니 새 연결이 낫다”는 쪽을 기본값으로 택한 셈입니다(Go 블로그 글이 설명한 트레이드오프와 일치합니다). [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)

2) ContentLength가 -1(unknown)인 경우가 관건입니다. HTTP/1 chunked 응답, streaming 응답, 혹은 서버가 길이를 명시하지 않은 경우에 `ContentLength`는 -1이 될 수 있는데, -1은 256KiB보다 작습니다. 그러면 “시도는 한다”가 기본이 됩니다. 대신 성공 조건이 “256KiB+1을 읽기 전에 EOF가 오느냐”이므로, 길이를 모르는 응답이라도 실제로 256KiB 이내에서 EOF가 오면 성공하고, 그 이상이면 실패합니다. 게다가 50ms 타임아웃이 있어서, 느리게 흘러오는 응답은 256KiB 이내여도 실패할 수 있습니다. [net/http transport.go](https://go.dev/src/net/http/transport.go)

마지막으로 Trailer 처리도 중요합니다. `maybeDrainBody`는 underlying reader가 `*body`이면 `discardTrailer()`를 호출해서 trailer를 버립니다. trailer를 남기면 다음 응답의 시작점 정렬이 깨질 수 있으니, 재사용 가능성을 높이기 위한 조치입니다. [net/http transport.go](https://go.dev/src/net/http/transport.go)

Go 블로그 글에는 추가 최적화로 “응답에 `Connection: close`가 있으면 drain 자체가 낭비라서 스킵한다”는 얘기도 있습니다. 이건 운영에서 꽤 중요합니다. 장애/에러 경로에서 upstream이 `Connection: close`를 붙이는 경우가 있는데, 이 경로에서는 어차피 재사용이 안 되니 drain 최적화도 의미가 없습니다. [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)

## Transport 설정과의 상호작용: 좋아지는 경우, 이상해지는 경우

Go 1.27 변경은 “연결 재사용 자체가 가능해지는 비율”을 올립니다. 그런데 실제 지연시간 체감은 Transport 설정과 함께 결정됩니다.

### IdleConnTimeout: 순차 호출 간격이 길면 결국 새 연결

`IdleConnTimeout`은 idle 상태로 남아 있는 keep-alive 커넥션을 언제 닫을지 정합니다. `http.DefaultTransport`는 `IdleConnTimeout: 90s` 같은 기본값을 갖고 있고, `MaxIdleConns: 100`도 기본으로 잡혀 있습니다. [net/http transport.go (DefaultTransport)](https://github.com/golang/go/blob/master/src/net/http/transport.go)

순차 호출이 2분 간격이고 `IdleConnTimeout`이 90초면, 매번 새 연결입니다. Go 1.27이 body를 잘 drain해도 “idle로 돌아간 커넥션이 살아있지 않으면” 재사용은 불가능합니다.

체감 포인트는 단순합니다.

- 순차 요청 간격이 `IdleConnTimeout`보다 짧으면: 재사용 가능성 상승 → 지연 감소
- 순차 요청 간격이 `IdleConnTimeout`보다 길면: 어차피 새 연결 → 변화 체감이 약함

### MaxIdleConns / MaxIdleConnsPerHost: 재사용할 “자리”가 있어야 함

`MaxIdleConns`는 전체 호스트 합산 idle 커넥션 상한이고, `MaxIdleConnsPerHost`는 호스트당 상한입니다. 문서상 기본 `DefaultMaxIdleConnsPerHost`는 2입니다. [net/http transport.go](https://github.com/golang/go/blob/master/src/net/http/transport.go)

순차 워크로드가 단일 호스트만 두드린다면 기본값(2)도 충분한 경우가 많습니다. 그런데 Go 1.27의 drain이 비동기이고, “Close 직후 즉시 다음 요청”이 들어오는 경우에는 이 기본값이 체감에 영향을 줄 수 있습니다.

- drain이 아직 안 끝났는데 다음 요청이 나가면, 그 요청은 기존 커넥션을 못 쓰고 **새 커넥션을 dial**할 수 있습니다.
- 이때 새 커넥션이 생기고 나면, drain이 끝난 기존 커넥션도 idle pool로 돌아오려고 합니다.
- `MaxIdleConnsPerHost`가 너무 낮으면, 돌아온 커넥션이 곧바로 버려지거나(LRU) 불필요한 churn이 생길 수 있습니다.

Go 1.27 릴리스 노트에는 특이한 경고도 있습니다. 연결 재사용의 이득이 없는 프로그램에서, `MaxIdleConns = 0`(무제한) 같은 설정이나 “요청마다 다른 Client/Transport를 만들어서 사실상 상한을 우회하는 코드”가 있으면 오히려 성능이 나빠질 수 있다고 말합니다. 필요하면 `DisableKeepAlives=true`로 재사용을 끄라는 얘기까지 합니다. [Go 1.27 Release Notes](https://go.dev/doc/go1.27)

이 경고는 꽤 현실적입니다.

- Go 1.26까지는 “body를 안 읽으면 어차피 재사용이 깨진다”는 이유로 idle 커넥션이 덜 남았을 수 있는데
- Go 1.27부터는 drain 덕분에 재사용이 늘고, idle 커넥션이 더 오래/더 많이 남을 수 있습니다.
- 상한이 없으면 FD/메모리/커널 리소스를 불필요하게 잡아먹는 방향으로 기울 수 있습니다.

### MaxConnsPerHost: 1로 묶어두면 오히려 50ms가 ‘상한 지연’이 될 수 있음

`MaxConnsPerHost`는 “dialing/active/idle 포함 총 커넥션 수”를 제한합니다. 0이면 무제한입니다. [net/http package documentation](https://pkg.go.dev/net/http)

여기서 Go 1.27 drain과 충돌할 수 있는 설정이 `MaxConnsPerHost=1`입니다.

- Go 1.27은 Close 이후 drain을 **백그라운드**에서 하되, 실제로 커넥션이 “완전히 재사용 가능한 상태로 idle pool에 돌아가는 시점”은 drain 성공 이후입니다.
- 그런데 `MaxConnsPerHost=1`이면, drain 중인 커넥션이 아직 active로 잡혀 있다고 판단되는 동안 다음 요청이 **새 커넥션을 만들 수도 없고**, 기존 커넥션도 재사용할 수 없습니다.
- 그 결과 다음 요청이 최대 50ms까지 블록될 여지가 생깁니다(드레인이 타임아웃까지 간다면).

순차 요청 워크로드에서 “항상 1커넥션만 쓰겠다”라는 의도로 `MaxConnsPerHost=1`을 박아둔 시스템이 있는데, 이런 구성은 Go 1.27에서 오히려 tail latency를 악화시킬 수 있습니다. 이건 Go 1.27이 느려서가 아니라, 설정이 “새 연결로 도망갈 자유”를 없애는 쪽으로 설계돼 있기 때문입니다.

### DisableKeepAlives / Request.Close: 이 최적화는 의미가 없어짐

`DisableKeepAlives=true`면 요청당 한 번만 커넥션을 쓰고 버립니다. 이 설정은 TCP keepalive와 무관하고 HTTP keep-alive를 끄는 것입니다. [net/http transport.go](https://github.com/golang/go/blob/master/src/net/http/transport.go)

또한 `req.Close = true`를 세팅하면 해당 요청은 재사용을 포기하는 방향으로 동작합니다. 이런 경우 Go 1.27 drain이 성공하든 말든, 성능 이득이 제한적입니다.

## 재현 가능한 벤치마크 설계: 서비스에서 ‘그대로’ 가져올 조건

이 최적화는 마이크로벤치마크로도 잘 보이지만, 운영에서 납득하려면 “내 서비스에서 실제로 이 패턴이 있나”를 확인할 수 있어야 합니다.

내가 권하는 벤치마크 설계는 세 축으로 쪼개는 것입니다.

1) **워크로드 축**: 순차 GET + body 미소비(또는 부분 소비)
   - status polling
   - HEAD가 아닌 GET (HEAD는 body가 사실상 없어서 이 이슈가 덜함)
   - JSON decode 후 남는 바이트(개행/공백) 존재

2) **응답 축**: drain이 성공할 수 있는/없는 조건을 의도적으로 만들기
   - Content-Length가 작은 고정 body (예: 1KB, 16KB)
   - Content-Length가 큰 body (예: 1MB) → drain을 아예 안 하거나 실패해야 정상
   - chunked + 느린 전송(slow drip) → 50ms 타임아웃에 걸리기 쉬움

3) **Transport 축**: idle pool과 상한이 결과를 어떻게 바꾸는지 확인
   - `MaxIdleConnsPerHost` (1, 2, 10)
   - `IdleConnTimeout` (1s, 30s, 90s)
   - `MaxConnsPerHost` (0, 1)
   - `DisableKeepAlives` (false/true)

여기에 측정 지표를 두 가지로 고정합니다.

- 서버 관점: **accept된 TCP 커넥션 수** (재사용 여부를 가장 믿을 수 있게 확인)
- 클라이언트 관점: `httptrace`로 **GotConn.Reused**, **WasIdle**, **IdleTime** 수집

`httptrace`는 Go 표준 기능이고, “이 요청이 재사용 커넥션을 잡았는지”를 직접 제공합니다. [Introducing HTTP Tracing](https://go.dev/blog/http-tracing)

## 벤치마크 코드: 재현용 도구(서버/클라이언트) 구현

아래 코드는 “순차 요청 + body 미소비” 패턴을 재현하고, Transport 튜닝을 바꿔가며 연결 재사용과 지연시간 변화를 관찰하는 목적입니다.

- 외부 의존성 없이 표준 라이브러리만 사용합니다.
- 실서비스의 cross-region/TLS 비용을 로컬에서 재현하기 위해, **Dial 단계에 인위적인 지연을 추가하는 옵션**을 넣었습니다. (새 연결일 때만 비용이 붙게 만들어야 변화가 또렷하게 보입니다.)

### go.mod

```text
module example.com/reusebench

go 1.27
```

### cmd/benchserver/main.go

```go
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"strconv"
	"sync/atomic"
	"time"
)

type countingListener struct {
	net.Listener
	accepts atomic.Int64
}

func (l *countingListener) Accept() (net.Conn, error) {
	c, err := l.Listener.Accept()
	if err == nil {
		l.accepts.Add(1)
	}
	return c, err
}

func (l *countingListener) Accepts() int64 { return l.accepts.Load() }

type serverConfig struct {
	addr          string
	bodyBytes     int
	slowChunkMs   int
	chunked       bool
	connClose     bool
	includeNewline bool
}

func main() {
	var cfg serverConfig
	flag.StringVar(&cfg.addr, "addr", "127.0.0.1:8080", "listen addr")
	flag.IntVar(&cfg.bodyBytes, "body-bytes", 1024, "response body bytes")
	flag.IntVar(&cfg.slowChunkMs, "slow-chunk-ms", 0, "sleep between chunks in ms (chunked only)")
	flag.BoolVar(&cfg.chunked, "chunked", false, "use chunked response (no Content-Length)")
	flag.BoolVar(&cfg.connClose, "conn-close", false, "set Connection: close")
	flag.BoolVar(&cfg.includeNewline, "newline", true, "append newline to JSON body")
	flag.Parse()

	ln, err := net.Listen("tcp", cfg.addr)
	if err != nil {
		log.Fatal(err)
	}
	cl := &countingListener{Listener: ln}

	mux := http.NewServeMux()
	mux.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
		if cfg.connClose {
			w.Header().Set("Connection", "close")
		}

		payload := map[string]any{
			"ok": true,
			"ts": time.Now().UnixNano(),
		}
		b, _ := json.Marshal(payload)
		if cfg.includeNewline {
			b = append(b, '\n')
		}

		// bodyBytes에 맞추기 위해 padding.
		if cfg.bodyBytes > len(b) {
			pad := make([]byte, cfg.bodyBytes-len(b))
			for i := range pad {
				pad[i] = 'x'
			}
			b = append(b, pad...)
		}

		w.Header().Set("Content-Type", "application/json")
		if !cfg.chunked {
			w.Header().Set("Content-Length", strconv.Itoa(len(b)))
			_, _ = w.Write(b)
			return
		}

		// chunked 모드: Content-Length를 설정하지 않으면 net/http가 chunked로 보냅니다.
		fl, _ := w.(http.Flusher)
		chunk := 256
		for off := 0; off < len(b); off += chunk {
			end := off + chunk
			if end > len(b) {
				end = len(b)
			}
			_, _ = w.Write(b[off:end])
			if fl != nil {
				fl.Flush()
			}
			if cfg.slowChunkMs > 0 {
				time.Sleep(time.Duration(cfg.slowChunkMs) * time.Millisecond)
			}
		}
	})

	mux.HandleFunc("/stats", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, "accepts=%d\n", cl.Accepts())
	})

	srv := &http.Server{
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       2 * time.Minute,
	}

	log.Printf("listening on %s", cfg.addr)
	log.Fatal(srv.Serve(cl))
}
```

### cmd/benchclient/main.go

```go
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httptrace"
	"sort"
	"sync/atomic"
	"time"
)

type clientConfig struct {
	url             string
	n               int
	mode            string
	dialDelay       time.Duration
	maxIdle         int
	maxIdlePerHost  int
	idleTimeout     time.Duration
	maxConnsPerHost int
	disableKeepAlive bool
}

func main() {
	var cfg clientConfig
	flag.StringVar(&cfg.url, "url", "http://127.0.0.1:8080/status", "target URL")
	flag.IntVar(&cfg.n, "n", 200, "number of sequential requests")
	flag.StringVar(&cfg.mode, "mode", "close-only", "close-only | json-decode | drain-full")
	flag.DurationVar(&cfg.dialDelay, "dial-delay", 0, "artificial delay added only when dialing a new connection")
	flag.IntVar(&cfg.maxIdle, "max-idle", 100, "Transport.MaxIdleConns")
	flag.IntVar(&cfg.maxIdlePerHost, "max-idle-per-host", 2, "Transport.MaxIdleConnsPerHost")
	flag.DurationVar(&cfg.idleTimeout, "idle-timeout", 90*time.Second, "Transport.IdleConnTimeout")
	flag.IntVar(&cfg.maxConnsPerHost, "max-conns-per-host", 0, "Transport.MaxConnsPerHost (0 = unlimited)")
	flag.BoolVar(&cfg.disableKeepAlive, "disable-keepalive", false, "Transport.DisableKeepAlives")
	flag.Parse()

	var d net.Dialer
	dial := func(ctx context.Context, network, addr string) (net.Conn, error) {
		if cfg.dialDelay > 0 {
			select {
			case <-time.After(cfg.dialDelay):
			case <-ctx.Done():
				return nil, ctx.Err()
			}
		}
		return d.DialContext(ctx, network, addr)
	}

	tr := &http.Transport{
		Proxy:               http.ProxyFromEnvironment,
		DialContext:         dial,
		ForceAttemptHTTP2:   false, // 벤치마크는 HTTP/1.1 전제
		MaxIdleConns:        cfg.maxIdle,
		MaxIdleConnsPerHost: cfg.maxIdlePerHost,
		IdleConnTimeout:     cfg.idleTimeout,
		MaxConnsPerHost:     cfg.maxConnsPerHost,
		DisableKeepAlives:   cfg.disableKeepAlive,
	}

	client := &http.Client{Transport: tr, Timeout: 10 * time.Second}

	var reused atomic.Int64
	var newConn atomic.Int64
	lat := make([]time.Duration, 0, cfg.n)

	for i := 0; i < cfg.n; i++ {
		start := time.Now()

		req, err := http.NewRequest("GET", cfg.url, nil)
		if err != nil {
			log.Fatal(err)
		}

		trace := &httptrace.ClientTrace{
			GotConn: func(info httptrace.GotConnInfo) {
				if info.Reused {
					reused.Add(1)
				} else {
					newConn.Add(1)
				}
			},
		}
		ctx := httptrace.WithClientTrace(req.Context(), trace)
		req = req.WithContext(ctx)

		resp, err := client.Do(req)
		if err != nil {
			log.Fatalf("request %d: %v", i, err)
		}

		switch cfg.mode {
		case "close-only":
			// body를 읽지 않고 Close만
			_ = resp.Body.Close()
		case "json-decode":
			// JSON object까지만 decode하고 Close.
			// 서버가 개행을 붙이면 잔여 바이트가 남을 수 있습니다.
			var v map[string]any
			_ = json.NewDecoder(resp.Body).Decode(&v)
			_ = resp.Body.Close()
		case "drain-full":
			_, _ = io.Copy(io.Discard, resp.Body)
			_ = resp.Body.Close()
		default:
			log.Fatalf("unknown mode: %s", cfg.mode)
		}

		lat = append(lat, time.Since(start))
	}

	sort.Slice(lat, func(i, j int) bool { return lat[i] < lat[j] })
	p := func(q float64) time.Duration {
		if len(lat) == 0 {
			return 0
		}
		idx := int(float64(len(lat)-1) * q)
		return lat[idx]
	}

	total := time.Duration(0)
	for _, d := range lat {
		total += d
	}

	fmt.Printf("mode=%s n=%d dial-delay=%s\n", cfg.mode, cfg.n, cfg.dialDelay)
	fmt.Printf("transport: maxIdle=%d maxIdlePerHost=%d idleTimeout=%s maxConnsPerHost=%d disableKeepAlive=%v\n",
		cfg.maxIdle, cfg.maxIdlePerHost, cfg.idleTimeout, cfg.maxConnsPerHost, cfg.disableKeepAlive)
	fmt.Printf("connections: reused=%d new=%d\n", reused.Load(), newConn.Load())
	fmt.Printf("latency: avg=%s p50=%s p95=%s p99=%s\n", total/time.Duration(len(lat)), p(0.50), p(0.95), p(0.99))
}
```

### 실행 방법과 예상 출력 형태

서버를 먼저 띄웁니다.

```bash
go run ./cmd/benchserver -addr 127.0.0.1:8080 -body-bytes 1024 -chunked=false -conn-close=false -newline=true
```

그 다음 클라이언트를 실행합니다.

```bash
# 새 연결이 생길 때만 30ms 비용을 붙여서(로컬에서도) 차이를 또렷하게 만듭니다.
go run ./cmd/benchclient \
  -url http://127.0.0.1:8080/status \
  -n 200 \
  -mode close-only \
  -dial-delay 30ms \
  -max-idle 100 \
  -max-idle-per-host 2 \
  -idle-timeout 90s
```

예상 출력은 환경에 따라 숫자가 달라지지만, 형태는 대략 다음 패턴으로 수렴해야 정상입니다.

- Go 1.26 계열 + `close-only` + 작은 body: `new`가 n에 가깝고, 평균 지연이 dial-delay 근처로 올라갑니다.
- Go 1.27 계열 + `close-only` + 작은 body: 첫 요청만 `new`, 나머지는 `reused`가 크게 늘고 평균 지연이 떨어집니다.

서버의 accept 수도 같이 확인하면 더 확실합니다.

```bash
curl -s http://127.0.0.1:8080/stats
# accepts=... (Go 1.27에서는 1~소수, Go 1.26에서는 n에 가까운 값이 나오는 쪽이 자연스럽습니다)
```

이 벤치마크는 “Go 1.27이 무조건 빠르다”를 증명하려는 게 아니라, **내 서비스가 이 최적화의 수혜 조건에 들어가는지**를 확인하려는 목적입니다.

## 결과 해석 프레임: 지연시간이 줄어드는 ‘이유’를 분해하기

측정값을 해석할 때, 나는 다음 순서로 봅니다.

### 1) accept 수가 줄었는가: 진짜로 재사용이 생겼는가

지연시간이 줄었다고 해서 반드시 connection reuse 때문은 아닙니다. 응답 캐시, CPU 스케줄링, GC 타이밍 등도 개입합니다.

그래서 가장 먼저 “서버 accept 수”를 봅니다.

- n번 요청에 accept가 n이면: 매번 새 연결
- accept가 1~2면: 대부분 재사용

Go 1.27 최적화가 정확히 맞아떨어진 경우는 여기서 바로 드러납니다.

### 2) httptrace의 Reused가 늘었는가: 클라이언트 관점에서 일치하는가

`httptrace`는 요청 단위로 “이 요청이 어떤 커넥션을 잡았는지”를 알려줍니다. 이건 Go가 제공하는 1차 도구라서 운영에서도 활용 가치가 큽니다. [Introducing HTTP Tracing](https://go.dev/blog/http-tracing)

- `Reused=true`가 대부분이면 재사용
- `Reused=false`가 대부분이면 새 연결

서버 accept와 불일치하면, 중간 프록시/로드밸런서가 다른 동작을 하고 있거나, keep-alive가 어딘가에서 끊기는 것입니다.

### 3) p99가 줄었는가: 순차 워크로드의 tail은 ‘연결 수립’이 자주 잡아먹는다

순차 워크로드는 특히 p99가 연결 수립 비용과 강하게 결합합니다.

- 새 연결이 드물게만 생기면 p99는 낮아질 가능성이 큼
- 매 요청이 새 연결이면 p50/p95/p99 모두 비슷하게 비싸짐

Go 블로그 글의 수치(710ms → 150ms)도 사실상 “100번 중 대부분이 새 연결이었냐/아니었냐”의 차이로 설명됩니다. [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)

## 운영 튜닝 포인트: 이득을 키우는 쪽, 부작용을 막는 쪽

Go 1.27은 기본 동작을 개선했지만, 운영 튜닝 포인트는 여전히 남습니다.

### MaxIdleConnsPerHost: 기본값 2는 ‘순차 + drain 레이스’에 애매할 수 있음

Go 1.27의 drain은 비동기라서 “다음 요청이 너무 빨리 오면” 새 연결이 하나 더 생길 수 있습니다. 이때 `MaxIdleConnsPerHost=1`이면 churn이 생길 수 있고, 기본값 2는 이런 상황을 어느 정도 흡수합니다. [net/http transport.go](https://github.com/golang/go/blob/master/src/net/http/transport.go)

순차 요청만 있고 트래픽이 아주 낮다면 2로도 충분합니다. 하지만 다음 조건이 있으면 10~수십으로 올리는 판단을 합니다.

- 같은 호스트로 가는 요청이 burst 형태로 몰림
- drain이 50ms 내에 끝나지 않는 응답이 간헐적으로 존재(네트워크 흔들림)
- 동시에 여러 goroutine이 같은 upstream을 두드림

다만 idle 커넥션은 곧 리소스입니다. 무턱대고 올리기 전에 accept 수/FD 수/메모리를 같이 봐야 합니다.

### MaxIdleConns: ‘호스트가 많은 클라이언트’는 100이 병목이 될 수 있음

DefaultTransport가 `MaxIdleConns=100`인 건 “대부분의 프로그램에 무난한 값”이지, 호스트가 수백/수천인 서비스 메시/크롤러/프록시에는 작은 값일 수 있습니다. [net/http transport.go (DefaultTransport)](https://github.com/golang/go/blob/master/src/net/http/transport.go)

Go 1.27로 재사용 가능성이 올라가면, 오히려 “idle pool이 더 적극적으로 차게” 되고 `MaxIdleConns`에 빨리 닿을 수 있습니다. 이때 LRU로 밀려난 커넥션이 많아지면 성능이 다시 흔들립니다.

반대로 릴리스 노트가 경고한 것처럼 `MaxIdleConns=0`을 사실상 “무제한”으로 쓰는 습관은 Go 1.27에서 더 위험해질 수 있습니다. Go 1.27은 이전보다 재사용에 성공하는 비율이 올라가서, 무제한 idle이 더 쉽게 누적될 수 있기 때문입니다. [Go 1.27 Release Notes](https://go.dev/doc/go1.27)

### IdleConnTimeout: 짧게 잡아둔 환경은 최적화 체감이 약해진다

순차 호출 간격이 초 단위인데 `IdleConnTimeout=500ms` 같은 값이면, Go 1.27 변경을 제대로 못 먹습니다. 이건 흔히 “리소스를 줄이겠다”는 의도로 박아두는데, 실은 “요청마다 새 연결”을 강제하는 효과가 나옵니다.

내 경우는 idle timeout을 바꿀 때 항상 upstream의 keep-alive 정책(로드밸런서 idle timeout, 프록시 timeout)도 같이 봅니다. 여기서 mismatch가 있으면 “가끔씩만 터지는 새 연결 비용”이 p99에 박힙니다.

### MaxConnsPerHost=1은 재검토 대상

앞에서 말했듯이, Go 1.27의 drain과 `MaxConnsPerHost=1`은 결이 안 맞는 경우가 있습니다.

- 목표가 “upstream 보호를 위해 동시 연결 수를 제한”이라면, 1이 아니라 적당한 숫자(예: CPU 코어 수, 혹은 upstream의 rate limit에 맞춘 값)로 잡는 편이 안전합니다.
- 목표가 “항상 같은 커넥션 하나만 써서 handshake를 없애겠다”라면, Go 1.27 drain이 50ms까지 레이스를 한다는 점 때문에 오히려 다음 요청이 그 50ms에 끌려갈 수 있습니다.

이 구간은 실제로 벤치마크로 확인하는 게 낫습니다.

### 수동 drain 유틸리티는 ‘삭제’가 기본이지만, 큰 body 경로는 다시 봐야 함

Go 블로그 글의 결론은 “이제는 그냥 Close만 하라”입니다. 실제로 Go 1.27 Transport가 50ms/256KiB 한도 내에서 그 일을 대신합니다. [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)

그래서 과거에 붙여놨던 `drainAndClose` 류 헬퍼는 대부분 삭제하는 게 맞습니다.

다만 과거 수동 drain 코드가 “무한 스트림을 끝까지 읽다가 멈추는 사고”를 예방하기 위해 제한을 걸어둔 구현이었다면, 그 제한이 Go 1.27의 제한(256KiB/50ms)보다 더 엄격했을 수도 있습니다. 특히 큰 body를 자주 받는 경로에서 “이전에는 Close로 즉시 끊고 다운로드를 아예 안 했다”가 “이제는 최대 256KiB는 다운로드한다”로 바뀌는 건 맞습니다. 이 변화는 기능 버그가 아니라 의도된 트레이드오프입니다.

streaming 성격의 응답(예: SSE, chunked로 길게 흘리는 응답)을 많이 다루는 서비스라면, 내 블로그에서 예전에 다뤘던 streamable HTTP 구현 글들과 연결해서도 한 번 더 점검하는 게 좋습니다.

- [Claude용 MCP 서버를 “에이전트 확장 서버”로 제대로 구현하는 법: Streamable HTTP, 버전 호환, 그리고 보안까지](https://daewooki.github.io/posts/2026-4-claude-mcp-streamable-http-1/)
- [MCP 서버로 Claude 에이전트를 “프로젝트에 안전하게 붙이는” 방법 (2026년 6월 기준: Streamable HTTP, 보안 함정, 확장 패턴)](https://daewooki.github.io/posts/mcp-claude-2026-6-streamable-http-1/)

(위 글들의 내용을 반복할 필요는 없고, 여기서는 “streaming 응답을 중도 종료하는 패턴이 많으면 drain이 의미가 없거나 비용이 될 수 있다” 정도만 연결하면 충분합니다.)

## 반론과 한계: 모든 워크로드가 빨라지는 건 아니다

### HTTP/2에서는 애초에 이 문제가 다르게 생긴다

Go 블로그 글이 명확히 말하듯, HTTP/2는 단일 TCP 커넥션 위에서 stream을 multiplexing하므로 “한 응답 body를 안 읽었다고 해서 다음 요청이 같은 커넥션을 못 쓰는” 문제가 구조적으로 약합니다. 그래서 글에서 굳이 `GODEBUG=http2client=0`로 HTTP/1을 강제해서 차이를 보여줍니다. [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)

내가 이 변화를 “HTTP/2를 쓰면 해결되니 무시해도 된다”고 보지 않는 이유는 두 가지입니다.

- 내부 통신이 아직 HTTP/1.1인 곳이 많습니다(프록시 체인, 레거시, 단순함 선호, h2 운영 난이도 등).
- HTTP/2를 쓰더라도, 모든 경로가 HTTP/2로 끝까지 유지되는 건 아닙니다. 중간에서 HTTP/1로 다운그레이드되는 구간이 있으면 다시 이 문제가 튀어나옵니다.

### chunked + 느린 응답은 50ms 타임아웃에 걸려서 재사용이 깨질 수 있다

Go 1.27은 drain을 “무한정” 하지 않습니다. 50ms 제한이 있기 때문에, 응답이 느리게 흘러오면 재사용이 실패합니다. 이건 설계상 안전장치입니다. [net/http transport.go](https://go.dev/src/net/http/transport.go)

따라서 효과가 큰 곳은 대체로 “body가 작고 빨리 끝나는 응답인데, 코드가 굳이 끝까지 안 읽는 곳”입니다.

### point release에서의 안정성: 가능하면 1.27.2 이상을 권한다

Go 1.27에서 이런 동작이 추가되면서, 동시 Read/Close 상황에서 deadlock을 유발할 수 있는 버그가 논의됐고, 1.27 브랜치로 backport된 이슈가 있습니다. 관련 이슈는 [net/http: concurrent response body Read and Close can deadlock with automatic draining in Go 1.27 [1.27 backport] #81411](https://github.com/golang/go/issues/81411)이고, 커밋 메시지도 “automatic draining in Go 1.27”을 전제로 합니다. [Issue #81411](https://github.com/golang/go/issues/81411)

Go 릴리스 히스토리를 보면 go1.27.2는 2026-10-08에 릴리스되었습니다. 이 글을 쓰는 시점(2026-10-15 KST)에서는 업그레이드를 한다면 1.27.2 이상으로 가는 쪽이 합리적입니다. [Release History](https://go.dev/doc/devel/release)

여기서 말하는 “동시 Read/Close”는 보통의 `defer resp.Body.Close()`와는 조금 다른 패턴입니다. 하지만 운영 코드에는 다음이 실제로 존재합니다.

- 타임아웃/컨텍스트 취소 경로에서 한 goroutine이 Close
- 다른 goroutine이 body를 읽다가 동시에 Close

이런 패턴이 있다면, point release 포함해서 가져가는 편이 낫습니다.

## 도입 판단: 언제 업그레이드의 ROI가 큰가

Go 1.27의 HTTP/1 connection reuse 개선은 “적용하면 조금 빨라짐”이 아니라, 조건이 맞으면 성능 프로파일 자체가 달라집니다.

- 순차 요청이 많고
- HTTP/1.1 keep-alive를 쓰며
- 응답 body를 완주하지 않는 코드가 섞여 있고
- upstream이 cross-AZ/cross-region 또는 TLS 비용이 큰 편이라면

업그레이드만으로도 “요청당 새 연결 수립”이 “대부분 재사용”으로 바뀌면서 지연시간과 연결 수가 동시에 내려갈 여지가 큽니다. Go 블로그 글의 710ms → 150ms 같은 수치가 바로 그 전형입니다. [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)

반대로 다음이면 체감이 제한적일 수 있습니다.

- 이미 HTTP/2 위주로 통신한다
- 순차 호출 간격이 길어서 `IdleConnTimeout`에 의해 커넥션이 매번 닫힌다
- 응답이 대체로 chunked streaming이고 50ms 내 drain이 어렵다
- `DisableKeepAlives=true` 또는 `Request.Close=true` 같은 정책으로 재사용을 의도적으로 꺼놨다

내 결론은 단순합니다. Go 1.27의 이 변화는 “코드 스타일을 고치지 않아도 되는 성능 개선”에 가깝고, 그만큼 숨겨진 비용을 줄여줍니다. 다만 Transport 설정과 워크로드가 엇갈리면 기대만큼 못 먹을 수 있으니, 위 벤치마크처럼 **accept 수와 Reused 비율을 함께** 확인하고 들어가는 게 맞습니다.

## 참고 자료

- [Better HTTP/1 connection reuse](https://go.dev/blog/http-connection-reuse)
- [Blog Index](https://go.dev/blog/all)
- [Go 1.27 Release Notes](https://go.dev/doc/go1.27)
- [net/http package documentation (go1.27.2)](https://pkg.go.dev/net/http@go1.27.2)
- [Introducing HTTP Tracing](https://go.dev/blog/http-tracing)
- [net/http Transport defaults and fields (source)](https://github.com/golang/go/blob/master/src/net/http/transport.go)
- [net/http: drain response body after close #77370](https://github.com/golang/go/issues/77370)
- [net/http: concurrent response body Read and Close can deadlock with automatic draining in Go 1.27 #81411](https://github.com/golang/go/issues/81411)
- [Release History](https://go.dev/doc/devel/release)
- [Go 1.27 size-specialized allocations 이후 GC·지연시간 튜닝 관점](https://daewooki.github.io/posts/go-size-specialized-allocations-gc-latency/)
- [Claude용 MCP 서버를 “에이전트 확장 서버”로 제대로 구현하는 법: Streamable HTTP, 버전 호환, 그리고 보안까지](https://daewooki.github.io/posts/2026-4-claude-mcp-streamable-http-1/)
- [MCP 서버로 Claude 에이전트를 “프로젝트에 안전하게 붙이는” 방법 (2026년 6월 기준: Streamable HTTP, 보안 함정, 확장 패턴)](https://daewooki.github.io/posts/mcp-claude-2026-6-streamable-http-1/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
