---
title: "GCP europe-west2 power event 장애에서 본 존 이슈의 리전 확산 경로와 페일오버 설계"
description: "존 단 전원 장애가 제어플레인 의존성과 용량 포화, 리트라이 증폭을 타고 리전 장애처럼 보이는 과정을 복기하고, 멀티존·멀티리전 전환을 실제로 동작시키는 체크리스트를 정리합니다."
date: 2026-10-26 12:52:29 +0900
categories: ["News", "Cloud"]
tags: ["google-cloud", "outage-analysis", "multi-region", "cloud-run", "load-balancing", "retries"]
render_with_liquid: false
---

## 타임라인에서 먼저 보이는 것: 전원 이벤트는 존에서 끝났지만, 영향은 리전으로 퍼졌다

2026-10-26 KST 시점에서 Google Cloud는 europe-west2(런던) 장애에 대해 상태 페이지에 Preliminary Incident Report를 올렸습니다. 게시 시각은 2026-10-22 01:42 PDT로 보이며, KST로는 2026-10-22 17:42입니다[^1].

상태 페이지가 제공하는 타임라인을 KST까지 포함해 다시 정리하면, 이번 사건은 “단일 존(europe-west2-b)에서 시작한 물리 장애가 리전 단 대규모 장애처럼 관측”되는 전형적인 형태입니다.

- **2026-10-20 14:53 KST (2026-10-19 22:53 PDT / 2026-10-20 06:53 BST)**: europe-west2-b가 위치한 데이터센터에서 전력망 장애 발생. UPS로 전환 후 디젤 발전기 자동 전환 시퀀스가 동작해야 하는데, PLC(Programmable Logic Controller) 자동화 시스템(주/예비 모두)이 발전기 시작/전환 로직을 시작하지 못했다고 보고됩니다[^1].
- **2026-10-20 15:00 KST (23:00 PDT / 07:00 BST)**: UPS 배터리 고갈 시점부터 물리 호스트 서버, 네트워크 스위칭 패브릭, 로컬 스토리지 어레이가 전원을 잃고 오프라인. 이 시각이 incident start로 잡혀 있습니다[^1].
- **2026-10-20 15:08 KST (23:08 PDT / 07:08 BST)**: 모니터링과 프로버가 API 에러 비율 상승, job submission timeout, europe-west2-b 인프라 도달 불가를 감지해 알림[^1].
- **두 개의 “연속된 phase”**: 고객 영향은 23:00–05:10 PDT(총 6시간 10분) 동안 두 단계로 이어졌고, 초기 phase(23:00–04:29 PDT) 동안 “elevated error rate / API timeout / processing delay”가 광범위하게 관측됐다고 적혀 있습니다[^1].
- **2026-10-20 21:10 KST (05:10 PDT / 13:10 BST)**: “vast majority” 서비스 가용성 회복 및 대부분 고객 영향 해소 시점[^1].
- **2026-10-20 23:03 KST (07:03 PDT / 15:03 BST)**: incident closure notification 게시 시각. 회복 tail을 처리한 뒤 공지를 닫았다고 설명합니다[^1].

언론 보도는 영향을 받은 사용자 입장에서 “런던 지역의 Google Cloud outage가 은행 앱을 흔들었다”는 식으로 관측을 정리했습니다. AP는 6:08 GMT(= 06:08 UTC 근처) 직후 시작, 약 6시간 뒤 대부분 해결로 서술하고, Lloyds/HSBC/Halifax/Revolut 등을 사례로 듭니다[^2].

이 타임라인에서 중요한 포인트는 두 가지입니다.

1) 물리 장애는 “europe-west2-b의 시설 전원”으로 제한되어 있다고 분명히 적혀 있습니다. 그런데도 2) 영향은 단일 존의 VM/DB replica unreachable 수준을 넘어, “regional service control plane의 cross-zone RPC timeout”, “unimpacted zone의 compute slot 포화”, “500/503 증가”로 확장됩니다[^1].

## ‘단일 존 이슈’가 리전 장애로 보이게 되는 3개의 경로

### 1) 데이터플레인의 자동 failover가 만드는 순간적인 수요 쇼크

상태 페이지는 “regional traffic-routing mechanisms와 client applications가 인접 존으로 자동 failover를 시작했다”고 씁니다[^1]. 여기서 관측이 리전 장애처럼 변형되기 시작합니다.

- 한 존이 꺼지면, 정상 존이 처리해야 할 트래픽이 늘어납니다.
- 평상시에는 존별로 headroom이 있어서 흡수할 수 있지만, 장애 상황에서는 다음이 동시에 발생합니다.
  - 기존 워크로드의 재스케줄링/재시작
  - 데이터베이스 HA failover
  - 큐/스트리밍 처리의 backlog 재처리
  - 타임아웃을 맞은 클라이언트의 재시도

상태 페이지가 직접 “redirected query executions, high-availability database failovers, compute workloads”가 다른 존의 capacity를 포화시켜 admission queue 상승, DB failover completion 지연, region 전반의 500/503을 유발했다고 적고 있다는 점이 중요합니다[^1].

즉, 존 하나가 꺼진 것이 1차 충격이라면, 자동 failover로 인해 정상 존에 부하가 몰리며 2차 충격이 만들어집니다. 고객 입장에서는 “나의 리소스는 b가 아니라 a/c에 있는데도 느리다/안 된다”가 됩니다.

멀티존을 했는데도 리전 장애처럼 보이는 가장 흔한 패턴은 “정상 존이 충분히 남아있지만, 남은 용량이 failover 부하를 감당하지 못하는” 상황입니다. 이건 설계가 틀렸다기보다, 멀티존을 **capacity planning**까지 포함한 체계로 보지 않았을 때 생깁니다.

### 2) 제어플레인의 cross-zone 의존성이 ‘존 장애 → 리전 API 장애’를 만든다

이번 사건에서 제일 날카로운 문장은 이것입니다.

- “Cross-zone remote procedure calls from regional service control planes directed to metadata and catalog components in the offline zone encountered timeouts, causing initial job submission stalls and API latency spikes.”[^1]

여기서 리전 장애처럼 보이는 이유가 설명됩니다.

- 데이터플레인(내 워커/내 DB replica)은 살아 있어도,
- 컨트롤러(스케줄러/프로비저너/오케스트레이터)가 ‘어딘가의 metadata/catalog’를 조회하거나 검증해야 해서 API를 처리합니다.
- 그 metadata/catalog가 오프라인 존에 있고, 컨트롤러가 거기에 cross-zone RPC를 날리다 timeout을 맞으면,
- 결과적으로 “새 job이 안 올라간다”, “scale out이 안 된다”, “API가 느리거나 timeout”이 됩니다.

이런 현상은 고객이 멀티존으로 VM을 분산해뒀는지와 무관하게 나타날 수 있습니다. 컨트롤플레인이 ‘논리적으로는 regional’이지만 ‘물리적으로는 특정 존의 컴포넌트에 의존’하는 순간, 단일 존 outage가 제어플레인 장애로 확대됩니다.

상태 페이지의 “Affected products included … unexpected degradation and failover issues … control-plane API timeouts waiting on validations from the offline zone”라는 문장도 같은 결을 강화합니다[^1].

### 3) 리트라이 증폭(retry amplification)이 복구 시간을 늘리고, 정상 존을 더 느리게 만든다

장애가 나면 개발자는 “재시도하면 되겠지”를 떠올립니다. Google도 SRE 관점에서 “모든 RPC 클라이언트는 jitter가 포함된 exponential backoff를 구현해야 한다”고 못 박습니다[^3].

문제는, 많은 시스템이 다음의 형태로 재시도를 ‘겹겹이’ 가지고 있다는 점입니다.

- 사용자 앱(모바일/웹)이 재시도
- API Gateway/Service Mesh가 재시도
- SDK(Cloud Client Libraries 등)가 재시도
- 내부 fan-out 호출(마이크로서비스)이 재시도

이때 500/503/timeouts가 발생하면, 총 요청 수가 원래 트래픽보다 더 커질 수 있습니다. Google SRE 책은 이를 cascading failure의 전형적 패턴으로 설명하고 randomized exponential backoff를 강조합니다[^4].

Google Cloud 문서에서도 API 재시도 시 “truncated exponential backoff with introduced jitter”를 권고하면서, 동기화된 재시도(thundering herd)와 quota 초과 위험을 직접 언급합니다[^5].

이번 europe-west2 사건에 그대로 대응시키면 다음의 루프가 만들어집니다.

1) europe-west2-b 오프라인 → 일부 요청 timeout/실패
2) 트래픽 라우팅/클라이언트 failover → a/c로 몰림
3) a/c에서 admission queue 상승 → 500/503 증가
4) 클라이언트/게이트웨이/SDK 재시도 → 더 몰림
5) 정상 존도 느려지고 에러가 늘어남 → 리전 장애처럼 보임

이 루프를 끊는 설계가 “페일오버가 실제로 동작한다”의 핵심입니다.

## 멀티존이 약해지는 지점: 공유 의존성(shared dependency)을 못 본다

멀티존 설계는 흔히 “워크로드를 3개 zone에 나눠 깐다”로 끝납니다. 그런데 이번 사건은 그 다음 레이어가 더 중요하다는 것을 보여줍니다.

상태 페이지에 명시된 확산 경로를 다시 보면, 공유 의존성은 크게 두 부류였습니다.

- 제어플레인/메타 계층: regional service control plane이 metadata/catalog 컴포넌트를 조회하는 경로가 오프라인 존으로 향했고 timeout을 유발[^1]
- 용량/스케줄링 계층: redirected workload가 정상 존의 compute slot/processing capacity를 포화시켜 admission queue 및 API 500/503을 만들었음[^1]

이 모델을 내 시스템에 적용해보면 체크해야 할 질문이 바뀝니다.

- “내 서비스는 multi-zone인가?”가 아니라
- “내가 기대하는 failover 시나리오에서 control plane이 어떤 검증/메타데이터를 어디서 읽는가?”
- “failover 순간에 남은 zone이 감당해야 하는 peak load는 얼마인가? failover storm까지 포함하면 얼마인가?”

이번 장애의 영향 서비스 목록에 Cloud Load Balancing, Cloud NAT, VPC 같은 네트워킹 계층까지 들어가 있다는 점도 눈여겨볼 만합니다[^1]. 애플리케이션이 멀티존이라도, 네트워크 제어/데이터 경로가 같은 실패 도메인을 공유하면 관측상 “다 죽은 것처럼” 보일 수 있습니다.

## 멀티리전 전환을 실제로 동작시키는 구성: Cloud Run + Global external Application Load Balancer

멀티존을 넘어서 멀티리전으로 가면 “한 리전의 제어플레인/용량 문제”에서 빠져나올 가능성이 커집니다. Cloud Run은 서비스가 리전 단위로 배포되기 때문에, 문서도 “여러 리전에 배포하고 global load balancing을 구성해야 한다”고 정리합니다[^6].

여기서 중요한 건, 멀티리전이 ‘설정값’이 아니라 ‘동작하는 시스템’이 되려면 다음 두 가지를 만족해야 한다는 점입니다.

- 트래픽 전환이 자동으로 일어나고(또는 수동 전환이 충분히 빠르고),
- 전환 순간에 재시도/백로그/콜드스타트가 정상 리전을 압살하지 않는다.

Cloud Run에는 이를 위해 “service health”라는 메커니즘을 제공합니다. readiness probe를 바탕으로 리전별 서비스 건강도를 집계하고, global external Application Load Balancer(또는 cross-region internal Application Load Balancer)가 unhealthy 리전을 자동으로 빼도록 설계합니다[^7].

아래는 내가 실제로 운영에 가져갈 때 최소한으로 확인하는 형태의 예시입니다. 장난감 수준을 피하기 위해 “의존 서비스(catalog)가 죽으면 API를 즉시 unready로 내려서 트래픽을 다른 리전으로 보내는” 형태로 구성합니다.

### 예시 시나리오

- `catalog` 서비스: 단순 조회 API(다운스트림 역할)
- `checkout` 서비스: 요청마다 `catalog`를 호출해야만 정상 응답 가능
- 멀티리전: europe-west2(런던), europe-west1(벨기에)
- 라우팅: Global external Application Load Balancer + Cloud Run service health
- 장애 가정: 런던 리전의 `catalog` 또는 네트워크가 불안정해지면 `checkout` readiness가 즉시 실패 → 런던 리전 `checkout`을 unhealthy로 판단 → 로드밸런서가 벨기에로 우회

Cloud Run service health는 “컨테이너 readiness probe 결과를 Cloud Run이 집계해 리전 단위 health로 노출한다”고 설명합니다[^7].

### 애플리케이션 코드 (Go 1.23 기준)

`MODE=catalog` 또는 `MODE=checkout`으로 같은 이미지가 두 역할을 수행하도록 만들면 배포가 단순해집니다.

```go
// go.mod
module example.com/multiregion-run

go 1.23
```

```go
// main.go
package main

import (
	context "context"
	cryptoRand "crypto/rand"
	encodingBinary "encoding/binary"
	fmt "fmt"
	io "io"
	log "log"
	net "net"
	nethttp "net/http"
	os "os"
	time "time"
)

type Config struct {
	Mode              string
	Port              string
	CatalogURL        string
	ReadyTimeout      time.Duration
	CallTimeout       time.Duration
	MaxAttempts       int
	BackoffBase       time.Duration
	BackoffCap        time.Duration
	OverallDeadline   time.Duration
	MaxConnsPerHost   int
	IdleConnTimeout   time.Duration
	DisableKeepAlives bool
}

func env(key, def string) string {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	return v
}

func envDuration(key string, def time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return def
	}
	return d
}

func envInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	var n int
	_, err := fmt.Sscanf(v, "%d", &n)
	if err != nil {
		return def
	}
	return n
}

func loadConfig() Config {
	return Config{
		Mode:              env("MODE", "checkout"),
		Port:              env("PORT", "8080"),
		CatalogURL:        env("CATALOG_URL", ""),
		ReadyTimeout:      envDuration("READY_TIMEOUT", 250*time.Millisecond),
		CallTimeout:       envDuration("CALL_TIMEOUT", 400*time.Millisecond),
		MaxAttempts:       envInt("MAX_ATTEMPTS", 3),
		BackoffBase:       envDuration("BACKOFF_BASE", 50*time.Millisecond),
		BackoffCap:        envDuration("BACKOFF_CAP", 500*time.Millisecond),
		OverallDeadline:   envDuration("OVERALL_DEADLINE", 900*time.Millisecond),
		MaxConnsPerHost:   envInt("MAX_CONNS_PER_HOST", 64),
		IdleConnTimeout:   envDuration("IDLE_CONN_TIMEOUT", 30*time.Second),
		DisableKeepAlives: env("DISABLE_KEEPALIVES", "false") == "true",
	}
}

func newHTTPClient(cfg Config) *nethttp.Client {
	tr := &nethttp.Transport{
		DialContext: (&net.Dialer{Timeout: 300 * time.Millisecond}).DialContext,
		MaxConnsPerHost:     cfg.MaxConnsPerHost,
		MaxIdleConns:        256,
		MaxIdleConnsPerHost: cfg.MaxConnsPerHost,
		IdleConnTimeout:     cfg.IdleConnTimeout,
		DisableKeepAlives:   cfg.DisableKeepAlives,
	}
	return &nethttp.Client{Transport: tr}
}

func randFloat01() float64 {
	var b [8]byte
	_, err := cryptoRand.Read(b[:])
	if err != nil {
		// 최악의 경우 동기화 위험이 커지므로, 실패하면 시간을 섞어서라도 분산
		return float64(time.Now().UnixNano()%1_000_000) / 1_000_000
	}
	u := binary.BigEndian.Uint64(b[:])
	return float64(u) / (1<<64 - 1)
}

// full jitter: sleep = random_between(0, min(cap, base*2^attempt))
func sleepWithJitter(ctx context.Context, base, cap time.Duration, attempt int) error {
	exp := base * (1 << attempt)
	if exp > cap {
		exp = cap
	}
	d := time.Duration(randFloat01() * float64(exp))
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-t.C:
		return nil
	}
}

func getWithRetry(ctx context.Context, client *nethttp.Client, url string, cfg Config) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, cfg.OverallDeadline)
	defer cancel()

	var lastErr error
	for attempt := 0; attempt < cfg.MaxAttempts; attempt++ {
		reqCtx, reqCancel := context.WithTimeout(ctx, cfg.CallTimeout)
		req, _ := nethttp.NewRequestWithContext(reqCtx, nethttp.MethodGet, url, nil)

		resp, err := client.Do(req)
		if err == nil {
			body, readErr := io.ReadAll(resp.Body)
			_ = resp.Body.Close()
			if readErr != nil {
				err = readErr
			} else if resp.StatusCode >= 200 && resp.StatusCode < 300 {
				return body, nil
			} else {
				err = fmt.Errorf("upstream status=%d body=%s", resp.StatusCode, string(body))
			}
		}
		reqCancel()
		lastErr = err

		// 마지막 시도면 더 자지 않음
		if attempt == cfg.MaxAttempts-1 {
			break
		}
		_ = sleepWithJitter(ctx, cfg.BackoffBase, cfg.BackoffCap, attempt)
	}
	return nil, lastErr
}

func main() {
	cfg := loadConfig()
	client := newHTTPClient(cfg)

	mux := nethttp.NewServeMux()

	mux.HandleFunc("/healthz", func(w nethttp.ResponseWriter, r *nethttp.Request) {
		// liveness: 프로세스가 살아있는지
		w.WriteHeader(200)
		_, _ = w.Write([]byte("ok"))
	})

	mux.HandleFunc("/readyz", func(w nethttp.ResponseWriter, r *nethttp.Request) {
		if cfg.Mode == "catalog" {
			w.WriteHeader(200)
			_, _ = w.Write([]byte("ready"))
			return
		}

		// checkout은 catalog에 의존. catalog 호출이 불안정하면 ready를 내림.
		if cfg.CatalogURL == "" {
			w.WriteHeader(500)
			_, _ = w.Write([]byte("CATALOG_URL required"))
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), cfg.ReadyTimeout)
		defer cancel()

		url := cfg.CatalogURL + "/catalog/ping"
		_, err := getWithRetry(ctx, client, url, Config{
			CallTimeout:     150 * time.Millisecond,
			OverallDeadline: cfg.ReadyTimeout,
			MaxAttempts:     1, // readiness에 재시도를 넣으면 전환이 늦어짐
			BackoffBase:     10 * time.Millisecond,
			BackoffCap:      10 * time.Millisecond,
		})
		if err != nil {
			w.WriteHeader(503)
			_, _ = w.Write([]byte("not ready: " + err.Error()))
			return
		}
		w.WriteHeader(200)
		_, _ = w.Write([]byte("ready"))
	})

	mux.HandleFunc("/catalog/ping", func(w nethttp.ResponseWriter, r *nethttp.Request) {
		if cfg.Mode != "catalog" {
			w.WriteHeader(404)
			return
		}
		w.WriteHeader(200)
		_, _ = w.Write([]byte("pong"))
	})

	mux.HandleFunc("/checkout", func(w nethttp.ResponseWriter, r *nethttp.Request) {
		if cfg.Mode != "checkout" {
			w.WriteHeader(404)
			return
		}
		if cfg.CatalogURL == "" {
			w.WriteHeader(500)
			_, _ = w.Write([]byte("CATALOG_URL required"))
			return
		}

		start := time.Now()
		body, err := getWithRetry(r.Context(), client, cfg.CatalogURL+"/catalog/ping", cfg)
		dur := time.Since(start)
		if err != nil {
			// 중요한 점: 여기서 무한 재시도, 장시간 timeout은 금물
			log.Printf("catalog error: %v dur=%s", err, dur)
			w.WriteHeader(503)
			_, _ = w.Write([]byte("upstream unavailable"))
			return
		}

		w.WriteHeader(200)
		_, _ = w.Write([]byte(fmt.Sprintf("checkout ok, catalog=%s dur=%s", string(body), dur)))
	})

	srv := &nethttp.Server{
		Addr:              ":" + cfg.Port,
		Handler:           mux,
		ReadHeaderTimeout: 2 * time.Second,
	}

	log.Printf("starting mode=%s port=%s", cfg.Mode, cfg.Port)
	if err := srv.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}
```

이 코드에서 운영적으로 중요한 의도가 몇 가지 있습니다.

- readiness(`/readyz`)에는 재시도를 거의 넣지 않았습니다. readiness가 늦게 실패하면 로드밸런서가 늦게 우회합니다.
- 실제 호출(`/checkout`)에는 “짧은 deadline + 작은 횟수의 재시도 + jitter”를 넣었습니다. Google SRE가 강조하는 retry amplification 완화 원칙과 같은 방향입니다[^3].
- `MaxConnsPerHost`로 연결 수를 어느 정도 제한했습니다. 장애 상황에서 unbounded concurrency는 스스로를 DDoS하는 형태가 되기 쉽습니다.

### Dockerfile

```dockerfile
# syntax=docker/dockerfile:1
FROM golang:1.23 as build
WORKDIR /src
COPY go.mod ./
COPY main.go ./
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/app ./

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/app /app
USER nonroot:nonroot
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/app"]
```

### 배포 (gcloud CLI)

Cloud Run은 리전 단위 배포이므로 두 리전에 각각 배포합니다. 멀티리전 서비스 구성 자체는 문서가 안내하는 형태를 따라갑니다[^6].

```bash
PROJECT_ID="YOUR_PROJECT"
IMAGE="europe-docker.pkg.dev/${PROJECT_ID}/demo/multiregion-run:1"

# Artifact Registry
gcloud artifacts repositories create demo \
  --repository-format=docker \
  --location=europe \
  --project "$PROJECT_ID"

gcloud auth configure-docker europe-docker.pkg.dev

docker build -t "$IMAGE" .
docker push "$IMAGE"

# catalog in europe-west2
gcloud run deploy catalog \
  --image "$IMAGE" \
  --region europe-west2 \
  --set-env-vars MODE=catalog \
  --no-allow-unauthenticated

# catalog in europe-west1
gcloud run deploy catalog \
  --image "$IMAGE" \
  --region europe-west1 \
  --set-env-vars MODE=catalog \
  --no-allow-unauthenticated
```

이어서 `checkout`을 배포합니다. 여기서 `CATALOG_URL`은 같은 리전의 catalog를 보도록 설정합니다(리전 내부 의존성을 분리해야, 한 리전이 죽을 때 다른 리전을 끌고 들어가지 않습니다).

```bash
CATALOG_W2_URL="https://catalog-<hash>-ew2.a.run.app"
CATALOG_W1_URL="https://catalog-<hash>-ew1.a.run.app"

# checkout in europe-west2
gcloud run deploy checkout \
  --image "$IMAGE" \
  --region europe-west2 \
  --set-env-vars MODE=checkout,CATALOG_URL="$CATALOG_W2_URL" \
  --no-allow-unauthenticated \
  --set-secrets="" \
  --update-env-vars READY_TIMEOUT=250ms,CALL_TIMEOUT=400ms,OVERALL_DEADLINE=900ms,MAX_ATTEMPTS=3

# checkout in europe-west1
gcloud run deploy checkout \
  --image "$IMAGE" \
  --region europe-west1 \
  --set-env-vars MODE=checkout,CATALOG_URL="$CATALOG_W1_URL" \
  --no-allow-unauthenticated \
  --update-env-vars READY_TIMEOUT=250ms,CALL_TIMEOUT=400ms,OVERALL_DEADLINE=900ms,MAX_ATTEMPTS=3
```

예상 출력(요지)은 다음과 비슷합니다.

```text
Deploying container to Cloud Run service [checkout] in project [YOUR_PROJECT] region [europe-west2]
...done
Service [checkout] revision [checkout-00001-...] has been deployed
```

### 트래픽 라우팅: Global external Application Load Balancer + service health

Cloud Run 멀티리전 라우팅은 “리전별 serverless NEG를 만들고 global load balancing을 설정”하는 형태입니다[^6]. 그리고 자동 failover/failback을 원하면 service health 가이드를 보라고 안내합니다[^6].

로드밸런서 동작 자체는 “Premium tier에서 가장 가까운 healthy backend로 라우팅하고 edge에서 최대한 가까이 termination한다”가 핵심입니다[^8].

여기서 운영자가 반드시 확인할 체크포인트는 다음입니다.

- 로드밸런서가 “헬스”를 무엇으로 판단하는가: 단순 200이 아니라, 내 서비스의 dependency까지 포함한 readiness가 반영되는가.
- unhealthy 판단이 늦으면, 장애 리전에 트래픽이 계속 들어가서 리트라이가 폭발한다.
- healthy로 복귀할 때 “failback”이 너무 공격적이면, 복구 직후 리전에 트래픽이 몰려 2차 장애를 만든다(이번 incident에서도 controlled traffic re-admission을 강조합니다[^1]).

Cloud Run 쪽 문서는 “readiness probe를 집계해 리전별 서비스 건강도를 노출한다”고 설명합니다[^7]. 이건 곧, readiness 설계를 대충하면 멀티리전 자체가 종이 위 설계가 되기 쉽다는 뜻입니다.

## 장애가 ‘연쇄’로 보일 때의 방어선: 멀티존/멀티리전 체크리스트

이번 europe-west2 사건에서 드러난 확산 경로(제어플레인 cross-zone timeout, 정상 존 용량 포화, 500/503 증가)를 기준으로 체크리스트를 만들면, 질문이 인프라/앱/클라이언트까지 내려옵니다.

### 트래픽 전환 계층: 전환 장치가 여러 개면, 우선순위를 정해야 한다

- Global external Application Load Balancer 같은 멀티리전 장치가 있으면, DNS 기반 전환(예: TTL 짧게)과 역할이 겹칠 수 있습니다.
- Cloud DNS는 routing policy(WRR, GEO, failover)와 health check를 제공하지만, DNS는 캐시/TTL 특성상 “정확히 즉시” 바뀌지 않는 것을 문서가 직접 경고합니다[^9].

내 경험상, “전환 장치가 많을수록 안전”이 아니라 “전환 장치가 많을수록 실제 장애 시 어떤 게 동작했는지 모른다”가 됩니다. 멀티리전은 가능하면 L7 전환(로드밸런서)을 1차로 두고, DNS는 최후의 백업(또는 온프레/타 클라우드 연동)처럼 성격을 나누는 편이 운영이 단단해집니다.

### 제어플레인/오케스트레이션 계층: 새로 만들기(Create)가 막히면 이미 떠 있는 것만으로 버텨야 한다

상태 페이지 업데이트에서도 “기존 워크로드 복구는 진행되지만 새 워크로드 생성은 아직 어려울 수 있다”는 뉘앙스가 반복됩니다[^1]. control plane이 불안정할 때는 이런 현상이 흔합니다.

따라서 멀티존/멀티리전 전환 설계에서 ‘필수’ 질문은 이것입니다.

- 장애 시점에 autoscaler가 scale out을 못 한다면, 현재 떠 있는 capacity만으로 얼마나 버틸 수 있는가?
- “존 하나가 날아간 상태의 steady state”를 기준으로 HPA/스케줄링/리밋을 잡았는가?

이번 사건에서 Google이 “scheduler allocations and capacity limits”를 조정해 customer reservation을 우선시하고 queue backlog를 줄였다고 밝힌 것도 같은 맥락입니다[^1].

### 용량 계층: failover 순간의 최대 부하를 평시의 2배 이상으로 잡아야 한다

europe-west2-b가 꺼지자 남은 존이 다음을 한꺼번에 떠안았습니다.

- redirected query execution
- database HA failover
- compute workload failover

그리고 그 결과가 “compute slots/processing capacity 포화 → admission queue 상승 → 500/503”입니다[^1].

멀티존 전환이 “그냥 다른 존으로 간다”라고 생각되기 쉬운데, 실제로는 “한동안 훨씬 더 비싼 방식으로 돌아간다”에 가깝습니다.

- 캐시가 cold
- DB failover 중
- 큐 backlog
- 관측/알림/대시보드도 장애

정리하면, 멀티존/멀티리전은 비용을 추가로 내고 용량을 비워두는 설계가 아니라, 장애 시점에 처리해야 하는 “추가 작업”을 위한 공간을 확보하는 설계입니다.

### 데이터 계층: ‘존 장애’와 ‘리전 장애’가 요구하는 복제 형태가 다르다

Spanner 문서는 regional configuration이 “3개의 read-write replica를 서로 다른 zone에 둔다”고 설명하며, single-zone failure에 대한 가용성을 기본으로 포함한다고 말합니다[^10].

하지만 리전 단 장애까지 상정하면 multi-region/dual-region이 필요해지고, 가용성/비용/지연시간 trade-off가 급격히 커집니다. Spanner는 multi-region에서 “regional failure에도 availability를 유지할 수 있고 더 높은 SLA를 제공”한다고 문서에 직접 적습니다[^10].

결국 애플리케이션 설계는 다음 중 하나를 선택해야 합니다.

- 데이터베이스 자체가 멀티리전 quorum을 형성(강한 일관성 유지, 비용/지연 증가)
- 데이터는 단일 리전에 두되 애플리케이션 레벨에서 degrade(읽기 전용, 제한 모드)
- 국가/규제 요구가 있으면 dual-region처럼 “국내 2리전” 패턴을 선택(제품/에디션 제약 가능)

멀티리전이 필요하다는 결론은 쉬운데, 어떤 형태의 멀티리전이 ‘비즈니스가 감당 가능한 비용’인지가 더 어렵습니다.

### 클라이언트/SDK 계층: 재시도는 ‘성공률을 올리는 장치’가 아니라 ‘장애를 키우는 장치’가 될 수 있다

Google SRE는 재시도가 cascading failure를 유발할 수 있고, randomized exponential backoff를 쓰라고 강조합니다[^4]. Google Cloud 문서도 thundering herd를 직접 언급하며 jitter가 필요하다고 말합니다[^5].

운영에서 체크할 항목은 구현 디테일입니다.

- timeout은 hop마다 어떻게 배분되는가(엔드투엔드 deadline을 먼저 정했는가)
- retry는 몇 번인가(무한 재시도가 있는가)
- retry는 어떤 에러에 적용되는가(503만? timeout도?)
- write 요청에는 idempotency key가 있는가
- circuit breaker/load shedding이 있는가

이 항목들이 빠지면, 멀티리전 전환이 있어도 장애 리전에 계속 두드리다가 정상 리전까지 무너뜨리는 그림이 나옵니다.

### 관측 계층: 장애 시점에 “같은 리전에서 도는 모니터링”은 같이 죽는다

Google Cloud는 Service Health 대시보드 외에도 Personalized Service Health를 언급합니다[^11]. 또한 문서로 “Personalized Service Health를 연동”하는 방법을 제공합니다[^12].

하지만 공급자 내부 대시보드만으로는 초기 탐지가 늦어질 수 있습니다. 장애를 빨리 감지하고 전환을 실행하려면, 최소한 다음은 필요합니다.

- 서로 다른 리전/외부 네트워크에서의 synthetic probe
- 고객 트래픽과 동일한 critical path(로그인/결제/조회 등) 기반 SLI
- 장애 시 자동으로 전환을 수행하는 runbook(혹은 자동화)

이번 사건에서도 Google은 “automated monitoring systems and probers”로 23:08 PDT에 감지했다고 명시합니다[^1]. 고객도 같은 형태의 “외부에서 보는 프로버”가 있어야 전환이 빨라집니다.

## 반론과 회의론: 멀티존/멀티리전이 만능이 아닌 이유

1) 멀티리전은 비용이 아니라 운영 복잡도를 삽니다. 트래픽 전환, 데이터 복제, 배포 파이프라인, 권한 모델, 사고 대응까지 전부가 두 배로 느껴질 수 있습니다.

2) Global external Application Load Balancer 같은 글로벌 구성도 결국은 제어플레인/데이터플레인 복합체입니다. 문서는 global external Application Load Balancer가 Premium tier에서 “가장 가까운 healthy backend로 라우팅”한다고 설명하지만[^8], “healthy”의 정의가 애플리케이션 readiness와 맞지 않으면 전환은 늦거나 잘못됩니다.

3) 데이터는 애플리케이션보다 옮기기 어렵습니다. 특히 강한 일관성을 유지하는 write 경로는 멀티리전으로 갈수록 latency/비용이 커집니다. Spanner가 multi-region에서 더 높은 SLA(예: 99.999%)를 제공한다고 설명하는 대신[^13], 그만큼 구조적 비용이 들어갑니다.

4) “우리 서비스는 멀티리전이니까 괜찮다”는 안도감이 오히려 리트라이/백프레셔/큐잉 설계의 허점을 방치하게 만들기도 합니다. 이번 incident의 확산 경로는, 전환 장치가 있어도 리트라이 증폭과 용량 포화를 제어하지 못하면 리전 전반이 느려질 수 있음을 보여줍니다[^1].

## 최종 RCA에서 확인하고 싶은 질문들

Preliminary Incident Report만으로도 큰 그림은 잡히지만, 설계 관점에서 더 알고 싶은 질문이 남습니다.

- regional service control plane이 의존하던 metadata/catalog 컴포넌트는 왜 오프라인 존에 있었는가. 복제/쿼럼 구조였는데도 timeout이 전파된 것인지, 혹은 특정 강결합 경로가 있었는가[^1].
- “traffic isolation”이 구체적으로 어떤 레벨에서 이뤄졌는가. 고객 트래픽만 차단한 것인지, 제어플레인의 cross-zone 호출까지 잘라냈는가[^1].
- compute slot 포화가 발생했을 때 admission control 정책은 어떤 식으로 동작했고, 어떤 워크로드가 우선순위를 가져갔는가. 특히 regional service와 zonal 서비스의 공존에서 starvation이 있었는가.
- controlled traffic re-admission은 어느 정도 속도로 이뤄졌고, 그 속도를 결정하는 신호는 무엇이었는가[^1].

이 답이 나오면, 고객 설계에서 “어떤 종류의 멀티존/멀티리전이 실제로 리스크를 줄이는지”가 더 명확해집니다.

## 지금 당장 점검할 수 있는 항목: 전환이 ‘가능’이 아니라 ‘즉시’인가

이번 사건을 보면서, 멀티존/멀티리전 설계를 실제로 동작하게 만드는 최소 점검 항목을 다시 정리했습니다.

- 전환 목표 시간: 장애 감지부터 1분/5분/15분 중 어디를 목표로 하는가. 목표가 없으면 timeout/retry만 길어집니다.
- readiness 설계: dependency 불능을 readiness에 반영하는가. 500을 뿜는 상태로 “healthy”가 유지되면 전환은 실패합니다.
- retry budget: 엔드투엔드 deadline과 최대 재시도 횟수가 정해져 있는가. hop마다 따로 재시도하면 폭발합니다.
- failover 순간의 capacity: “한 존/한 리전이 사라졌을 때 남은 곳이 failover 작업까지 포함해 감당 가능한가”를 수치로 확인했는가. 이번 incident는 정상 존이 failover 트래픽으로 포화될 수 있음을 명시합니다[^1].
- 관측의 분리: 모니터링/알림이 같은 리전/같은 VPC에 갇혀 있지 않은가.
- 전환 후 복귀(failback): 복구 직후에 트래픽을 공격적으로 다시 원래 리전에 몰아넣지 않는가. 공급자도 controlled re-admission을 강조합니다[^1].

이번 europe-west2 사건은 전원 장애 자체보다, “단일 존 장애가 제어플레인과 용량, 재시도 증폭을 타고 리전 장애처럼 관측되는 과정”이 더 많은 힌트를 줍니다. 페일오버는 아키텍처 다이어그램이 아니라, 타임아웃/헬스/용량/재시도를 동시에 설계했을 때만 동작합니다.

## 참고 자료

- [Incident details | Google Cloud Service Health](https://status.cloud.google.com/incidents/Xs2XTHzAVC9YnafnPyzj)
- [Google Cloud outage hits UK banks | AP News](https://apnews.com/article/google-outage-europe-bank-apps-e8d708a22cb1a1b225e2b1b70e963a31)
- [Serve traffic from multiple regions | Cloud Run](https://docs.cloud.google.com/run/docs/multiple-regions?hl=en)
- [Automate cross-region failover with Cloud Run service health](https://docs.cloud.google.com/run/docs/configuring/configure-service-health?hl=en)
- [External Application Load Balancer overview](https://docs.cloud.google.com/load-balancing/docs/https)
- [DNS routing policies and health checks](https://docs.cloud.google.com/dns/docs/routing-policies-overview)
- [Retry failed requests | IAM](https://docs.cloud.google.com/iam/docs/retry-strategy?hl=en)
- [Production Services Best Practices](https://sre.google/sre-book/service-best-practices/)
- [Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/)
- [Regional, dual-region, and multi-region configurations | Spanner](https://docs.cloud.google.com/spanner/docs/instance-configurations?hl=en)
- [Cloud Spanner Service Level Agreement (SLA)](https://cloud.google.com/spanner/sla)
- [Integrate with Personalized Service Health](https://docs.cloud.google.com/service-health/docs/how-to-integrate)

[^1]: <https://status.cloud.google.com/incidents/Xs2XTHzAVC9YnafnPyzj>
[^2]: <https://apnews.com/article/google-outage-europe-bank-apps-e8d708a22cb1a1b225e2b1b70e963a31>
[^3]: <https://sre.google/sre-book/service-best-practices/>
[^4]: <https://sre.google/sre-book/addressing-cascading-failures/>
[^5]: <https://docs.cloud.google.com/iam/docs/retry-strategy?hl=en>
[^6]: <https://docs.cloud.google.com/run/docs/multiple-regions?hl=en>
[^7]: <https://docs.cloud.google.com/run/docs/configuring/configure-service-health?hl=en>
[^8]: <https://docs.cloud.google.com/load-balancing/docs/https>
[^9]: <https://docs.cloud.google.com/dns/docs/routing-policies-overview>
[^10]: <https://docs.cloud.google.com/spanner/docs/instance-configurations?hl=en>
[^11]: <https://status.cloud.google.com/index.html>
[^12]: <https://docs.cloud.google.com/service-health/docs/how-to-integrate>
[^13]: <https://cloud.google.com/spanner/sla>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
