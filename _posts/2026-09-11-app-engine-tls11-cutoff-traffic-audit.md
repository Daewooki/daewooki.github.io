---
title: "App Engine(Go)의 TLS 1.1 이하 차단에 대비한 트래픽 계측과 단계적 종료"
description: "TLS 1.0/1.1 차단은 ‘서버 장애’처럼 보일 수 있습니다. 누가 구버전으로 붙는지 로그로 계측하고, 영향 범위를 산정해 단계적으로 종료합니다."
date: 2026-09-11 13:09:09 +0900
categories: ["Cloud", "App Engine"]
tags: ["gcp", "app-engine", "tls", "load-balancing", "cloud-logging", "go"]
render_with_liquid: false
---

## 바뀌는 일정: opt-in과 영구 차단의 경계

Google Cloud App Engine 표준환경(Go) 릴리스 노트에 따르면, 2026년 8월부터 App Engine이 애플리케이션을 TLS 1.2 이상으로 자동 opt-in 하고(구버전 TLS가 필요하면 2026년 8월 말까지 opt-out 가능), **2026년 9월부터는 TLS 1.1 이하의 insecure traffic을 영구 차단할 수 있다**고 명시되어 있습니다.[^1]

- 릴리스 노트(표준환경 Go): [App Engine standard environment for Go release notes](https://docs.cloud.google.com/appengine/docs/standard/go/release-notes)
- 설정 가이드: [Secure your app with minimum TLS (standard environment)](https://docs.cloud.google.com/appengine/docs/standard/secure-minimum-tls)

여기서 중요한 포인트는 “차단”이 HTTP 레벨에서 4xx/5xx를 내주는 변화가 아니라, TLS handshake 단계에서 연결 자체가 성립하지 않는 형태로 보일 수 있다는 점입니다. 운영 관점에서는 다음의 현상이 한 덩어리로 묶여 “갑자기 죽었다”로 체감됩니다.

1) 특정 클라이언트(또는 중간 프록시)가 TLS 1.0/1.1로만 접속 가능
2) 어느 날부터 handshake가 실패
3) 애플리케이션 로그에는 아무 것도 안 남음
4) 고객은 “서버가 다운됐다”라고 인지

이 글은 “TLS 올리세요”로 끝내지 않고, 실제로 누가 TLS 1.0/1.1로 붙는지 계측하고, 차단 시의 영향 범위를 산정한 뒤, 단계적 종료 공지/대응과 교체 순서를 운영 절차로 정리하는 쪽에 집중합니다.

## ‘서버 장애’처럼 보이는 이유: TLS에서 끊기면 HTTP 로그가 없다

TLS 1.0/1.1 차단이 특히 위험한 이유는, 장애 신호가 애플리케이션 관측 지점에 잘 잡히지 않기 때문입니다.

클라이언트가 TLS 1.0/1.1로 연결을 시도할 때, 서버(정확히는 edge)가 이를 거부하면 HTTP request가 애플리케이션까지 도달하지 않습니다. 결과적으로 App Engine request log, 애플리케이션 APM, 애플리케이션 custom log에는 아무런 흔적이 남지 않을 수 있습니다.

Load Balancer 쪽도 마찬가지로 함정이 하나 더 있습니다. Google Cloud의 global external Application Load Balancer 문서에는, TLS handshake가 실패한 경우(프로토콜 mismatch, cipher negotiation 실패 등)는 Cloud Logging에 기록되지 않는다고 명시되어 있습니다. 즉 “차단 이후”의 실패 트래픽은 로그가 아니라, 고객 문의/헬프데스크/CS 티켓으로 먼저 관측될 가능성이 높습니다.[^2]

따라서 전략은 단순합니다.

- 차단 이후 실패를 잡겠다는 발상은 늦습니다.
- 차단 이전에 “성공한 요청들 중 TLS 1.0/1.1로 들어오는 요청이 있었는지”를 계측해 두어야 합니다.

이 관점이 없으면, 변경 당일의 현상은 늘 비슷하게 흘러갑니다.

- 특정 고객사 네트워크(프록시)만 죽고
- 특정 오래된 SDK/런타임만 죽고
- 우리 서버 CPU/메모리/5xx는 멀쩡해서 원인 추적이 늦어지고
- 결국 임시로 opt-out 같은 ‘되돌림’에 의존하게 됩니다.

## 계측의 현실: App Engine 단독으로는 TLS 버전이 안 보일 수 있다

App Engine 표준환경에서 TLS termination은 애플리케이션 프로세스(Go http.Server) 앞단에서 이뤄집니다. 그래서 애플리케이션 코드에서 `r.TLS` 같은 식으로 TLS version을 꺼내는 방식은 원천적으로 성립하지 않습니다(애플리케이션이 직접 TLS socket을 받지 않기 때문입니다).

그렇다고 “계측이 불가능하다”로 결론내리면 곤란합니다. 계측은 보통 edge에서 합니다.

여기서 선택지는 두 갈래입니다.

### 1) App Engine 설정으로 TLS 1.2+를 강제하고 끝낸다

Google 문서에는, App Engine이 2026년 8월부터 기본으로 TLS 1.2+를 사용하도록 opt-in 한다고 되어 있고, 구버전이 필요하면 2026년 8월 말까지 opt-out 가능하다고 안내합니다.[^3]

이 선택은 운영이 간단하지만, “누가 TLS 1.0/1.1로 붙는지” 같은 가시성을 확보하기는 어렵습니다. 차단 전에 계측을 못 하면, 9월 이후 차단이 실제로 일어났을 때 고객 영향을 사후 대응하게 됩니다.

### 2) Load Balancer를 앞단에 두고 TLS metadata를 로그로 남긴다

App Engine으로 들어오는 트래픽을 global/regional external Application Load Balancer로 받아서 라우팅하면, Load Balancer 로그에 TLS metadata를 남길 수 있습니다.

Google Cloud Load Balancing 문서에는 `tls` 필드가 `TlsInfo` 포맷이며, `tls.protocol`과 `tls.cipher`를 optional logging field로 남길 수 있다고 나옵니다.[^4]

App Engine 문서도 “serverless NEG + Cloud Load Balancing” 조합을 언급하며, Load Balancer에서 SSL policy로 TLS 버전/암호군을 더 제한할 수 있다고 적어 둡니다.[^3]

이 글의 핵심은 이 2번을 전제로 합니다. 계측은 edge에서 하고, 차단은 (가능하면) edge에서 점진적으로 맞춰 들어가는 편이 운영이 덜 위험합니다.

## Load Balancer 로그로 TLS 1.0/1.1 트래픽을 계측하는 방법

여기부터는 “실제로 누가 TLS 1.0/1.1로 붙는지”를 숫자로 뽑아내는 방법입니다. 목표는 단순한 전체 카운트가 아닙니다.

- TLS 1.0/1.1 트래픽의 비율
- 어떤 endpoint에 붙는지
- 어떤 고객/네트워크 대역/국가/ASN(가능하면)에서 오는지
- 어떤 User-Agent/SDK 조합인지
- 그 트래픽이 매출/업무에 얼마나 중요한지

### 로깅에서 확보해야 하는 데이터

Load Balancer access log에서 최소한 다음이 필요합니다.

- `jsonPayload.tls.protocol` (TLSv1, TLSv1.1, TLSv1.2, TLSv1.3, QUIC 등)[^2]
- `jsonPayload.tls.cipher` (가능하면)
- `httpRequest.requestUrl` 또는 path/host 정보
- `httpRequest.userAgent`
- `httpRequest.remoteIp`

TLS protocol만 있어도 1차 필터링은 됩니다. 다만 cipher까지 같이 뽑으면 “TLS 1.2인데 사실상 구식 cipher만 쓰는 클라이언트” 같은 숨은 레거시도 같이 잡힙니다.

### logging optional fields 활성화(gcloud)

global external Application Load Balancer 문서에는 backend service에 대해 logging optional fields를 `tls.protocol,tls.cipher`로 켤 수 있다고 되어 있습니다.[^2]

이미 backend service가 있는 경우(대부분 이 케이스)에 해당하는 업데이트 형태는 다음 패턴으로 이해하면 됩니다.

- logging을 켜고(`--enable-logging`)
- sample rate를 1.0으로 시작하고(`--logging-sample-rate=1.0`)
- optional mode를 CUSTOM으로 두고
- optional field로 `tls.protocol,tls.cipher`를 지정

문서에 나온 예시는 다음과 같은 형태입니다.[^2]

```bash
gcloud compute backend-services update BACKEND_SERVICE \
  --global \
  --enable-logging \
  --logging-sample-rate=1.0 \
  --logging-optional=CUSTOM \
  --logging-optional-fields=tls.protocol,tls.cipher
```

sample rate는 처음엔 100%로 두는 편이 안전합니다. TLS 1.0/1.1 트래픽은 흔히 “희귀하지만 중요”한 형태로 남아 있어서, 1% 샘플링을 걸어버리면 존재 자체를 놓치기 쉽습니다.

로그 비용이 걱정되면 다음 순서가 현실적입니다.

1) 3~7일만 100%로 뽑아서 분포를 본다
2) TLS 1.0/1.1이 0에 수렴하면 10~20% 샘플링으로 낮춘다
3) TLS 1.0/1.1이 의미 있게 나오면, 그 구간 동안은 100% 유지한다

### Cloud Logging에서 바로 집계하는 쿼리 감각

Load Balancer 로그는 보통 `resource.type="http_load_balancer"`로 필터링해서 보기 시작합니다. 문서에서도 resource type과 로그 엔트리 타입을 기준으로 필터링하는 예시가 반복됩니다.[^2]

가장 먼저 확인할 것은 “TLSv1 / TLSv1.1이 실제로 찍히는가”입니다.

- `jsonPayload.tls.protocol="TLSv1"`
- `jsonPayload.tls.protocol="TLSv1.1"`

여기서 한 번 더 중요한 운영 포인트가 있습니다.

- global external LB는 handshake 실패를 로그로 남기지 않습니다.[^2]
- 따라서 “차단 이후의 실패량”을 로그로 재구성하기 어렵습니다.
- 즉, **차단 이전에 성공 요청을 기준으로 레거시를 찾아야 합니다.**

성공 요청 기반 계측의 함정은 “레거시 클라이언트가 이미 retry/backoff를 심하게 하면서 성공률이 낮은 상태”일 수 있다는 점입니다. 그 경우, 성공 로그에서의 비중은 낮지만, 실제 고객 불편은 훨씬 크게 나타납니다. 그래서 다음 단계가 필요합니다.

- 같은 IP/UA가 4xx/5xx/timeout을 얼마나 내는지도 같이 보거나
- 해당 고객군을 식별해서 직접 커뮤니케이션으로 확인하는 방식

## Go로 TLS protocol 분포 리포트를 자동 생성하기

콘솔에서 눈으로 보는 것만으로는 조직적으로 종료 계획을 밀어붙이기 어렵습니다. 내가 운영에서 유용했던 형태는 “매일 아침 자동으로 TLS 분포 리포트가 슬랙/메일로 떨어지는 상태”를 먼저 만들어 두는 것입니다.

여기서는 Cloud Logging API를 사용해 최근 N일의 Load Balancer 로그를 읽고, `jsonPayload.tls.protocol`을 집계하는 작은 CLI를 만듭니다.

전제는 두 가지입니다.

- backend service logging에서 `tls.protocol`을 optional field로 기록 중이어야 합니다.[^2]
- 조회 대상은 “handshake가 끝난 성공 연결”만 포함합니다(실패 handshake는 로그가 안 남습니다).[^2]

### 디렉터리 구조

```text
tls-audit/
  go.mod
  cmd/
    tls-audit/
      main.go
```

### go.mod

```go
module example.com/tls-audit

go 1.23

require (
  cloud.google.com/go/logging v1.13.0
  google.golang.org/api v0.223.0
)
```

버전은 예시입니다. 실제로는 조직의 표준 Go 버전을 맞추는 편이 낫습니다. 이 도구는 “최신 기능”이 아니라 “매일 굴러가는 안정성”이 우선입니다.

### main.go

```go
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"

	"cloud.google.com/go/logging/logadmin"
	"google.golang.org/api/iterator"
)

type counter map[string]int64

func (c counter) inc(key string) {
	if key == "" {
		key = "UNKNOWN"
	}
	c[key]++
}

func main() {
	var (
		projectID  = flag.String("project", os.Getenv("GOOGLE_CLOUD_PROJECT"), "GCP project id (or GOOGLE_CLOUD_PROJECT)")
		days       = flag.Int("days", 7, "lookback days")
		limit      = flag.Int("limit", 200000, "max log entries to scan")
		urlPrefix  = flag.String("url-prefix", "", "optional: only include requestUrl starting with this prefix")
		uaContains = flag.String("ua-contains", "", "optional: only include userAgent containing this substring")
	)
	flag.Parse()

	if *projectID == "" {
		fmt.Fprintln(os.Stderr, "missing -project or GOOGLE_CLOUD_PROJECT")
		os.Exit(2)
	}

	ctx := context.Background()
	client, err := logadmin.NewClient(ctx, *projectID)
	if err != nil {
		fmt.Fprintln(os.Stderr, "logadmin.NewClient:", err)
		os.Exit(1)
	}
	defer client.Close()

	start := time.Now().Add(-time.Duration(*days) * 24 * time.Hour).UTC().Format(time.RFC3339)

	// Load balancer request logs.
	// tls.protocol is optional; if optional logging wasn't enabled, the field might be missing.
	filterParts := []string{
		`resource.type="http_load_balancer"`,
		`jsonPayload.@type="type.googleapis.com/google.cloud.loadbalancing.type.LoadBalancerLogEntry"`,
		fmt.Sprintf(`timestamp>="%s"`, start),
	}
	filter := strings.Join(filterParts, "\n")

	it := client.Entries(ctx,
		logadmin.Filter(filter),
		logadmin.NewestFirst(),
	)

	byProto := counter{}
	byProtoAndUA := map[string]counter{}

	scanned := 0
	for {
		if scanned >= *limit {
			break
		}
		e, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			fmt.Fprintln(os.Stderr, "iterator:", err)
			os.Exit(1)
		}
		scanned++

		// The payload is a Struct; easiest portable way is to JSON roundtrip.
		b, _ := json.Marshal(e.Payload)
		var m map[string]any
		_ = json.Unmarshal(b, &m)

		// httpRequest
		httpReq, _ := m["httpRequest"].(map[string]any)
		var requestURL, userAgent string
		if httpReq != nil {
			requestURL, _ = httpReq["requestUrl"].(string)
			userAgent, _ = httpReq["userAgent"].(string)
		}

		if *urlPrefix != "" && !strings.HasPrefix(requestURL, *urlPrefix) {
			continue
		}
		if *uaContains != "" && !strings.Contains(userAgent, *uaContains) {
			continue
		}

		// jsonPayload.tls.protocol
		jsonPayload, _ := m["jsonPayload"].(map[string]any)
		var proto string
		if jsonPayload != nil {
			tls, _ := jsonPayload["tls"].(map[string]any)
			if tls != nil {
				proto, _ = tls["protocol"].(string)
			}
		}

		byProto.inc(proto)

		normalizedUA := normalizeUA(userAgent)
		if _, ok := byProtoAndUA[proto]; !ok {
			byProtoAndUA[proto] = counter{}
		}
		byProtoAndUA[proto].inc(normalizedUA)
	}

	fmt.Printf("scanned=%d (limit=%d) lookbackDays=%d start=%s\n", scanned, *limit, *days, start)
	fmt.Println("\nTLS protocol distribution:")
	printCounter(byProto)

	fmt.Println("\nTop user agents per TLS protocol (normalized):")
	for _, proto := range sortedKeys(byProto) {
		fmt.Printf("\n- %s\n", proto)
		printTop(byProtoAndUA[proto], 10)
	}
}

func normalizeUA(ua string) string {
	ua = strings.TrimSpace(ua)
	if ua == "" {
		return "(empty)"
	}
	// Very rough normalization. Real world에서는 UA 정규화 룰을 조직에 맞게 키워야 합니다.
	switch {
	case strings.Contains(ua, "okhttp"):
		return "okhttp"
	case strings.Contains(strings.ToLower(ua), "java"):
		return "java"
	case strings.Contains(strings.ToLower(ua), "python"):
		return "python"
	case strings.Contains(strings.ToLower(ua), "go-http-client"):
		return "go-http-client"
	case strings.Contains(strings.ToLower(ua), "curl"):
		return "curl"
	default:
		return ua
	}
}

func sortedKeys(c counter) []string {
	keys := make([]string, 0, len(c))
	for k := range c {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func printCounter(c counter) {
	keys := sortedKeys(c)
	var total int64
	for _, k := range keys {
		total += c[k]
	}
	for _, k := range keys {
		v := c[k]
		pct := 0.0
		if total > 0 {
			pct = float64(v) * 100.0 / float64(total)
		}
		fmt.Printf("  %-10s %12d  %6.2f%%\n", k, v, pct)
	}
	fmt.Printf("  %-10s %12d\n", "TOTAL", total)
}

func printTop(c counter, n int) {
	type kv struct {
		k string
		v int64
	}
	arr := make([]kv, 0, len(c))
	for k, v := range c {
		arr = append(arr, kv{k: k, v: v})
	}
	sort.Slice(arr, func(i, j int) bool { return arr[i].v > arr[j].v })
	if len(arr) > n {
		arr = arr[:n]
	}
	for _, it := range arr {
		fmt.Printf("    %-30s %d\n", it.k, it.v)
	}
}
```

### 실행 방법

1) 로컬에서 Application Default Credentials 설정

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="YOUR_PROJECT_ID"
```

2) 빌드/실행

```bash
go run ./cmd/tls-audit -days 7 -limit 200000
```

### 예상 출력 예시

```text
scanned=38210 (limit=200000) lookbackDays=7 start=2026-09-04T00:12:11Z

TLS protocol distribution:
  QUIC              12000   31.40%
  TLSv1.2           25000   65.43%
  TLSv1.3            1200    3.14%
  TLSv1.1              10    0.03%
  TOTAL             38210

Top user agents per TLS protocol (normalized):

- TLSv1.1
    java                           6
    okhttp                         4
```

이 정도 리포트만 나와도 바로 다음 결정을 할 수 있습니다.

- TLSv1.1이 10건이지만 특정 고객/특정 SDK로 묶이는가
- 그 고객이 매출/업무적으로 중요한가
- 교체 가능한가(우리 SDK 교체인지, 고객 네트워크 프록시 교체인지)

내 경우는 여기서 “트래픽 비중”이 아니라 “고객 식별 가능성”이 가장 중요했습니다. 0.03%라도 특정 파트너 결제/정산이면 100%입니다.

## 영향 범위 산정: ‘몇 건’이 아니라 ‘누가’의 문제

TLS 1.0/1.1 트래픽을 집계해서 숫자를 얻으면, 다음에 해야 할 일은 blast radius를 운영 언어로 번역하는 것입니다.

- (기술) TLSv1.1 요청이 하루 200건
- (운영) 특정 파트너사의 배치 잡이 매일 새벽 2시에 호출하며, 실패 시 정산이 늦어짐
- (비즈) SLA 위반 가능

숫자를 운영 언어로 바꾸는 방법은 “차단되면 곧장 장애로 이어질 흐름”을 찾아내는 것입니다.

### 1) endpoint 기준으로 나누기

TLSv1/TLSv1.1 트래픽을 endpoint(path) 기준으로 나눕니다.

- 로그인/토큰 발급 같은 인증 endpoint
- 결제/정산 같은 핵심 endpoint
- 웹 정적 리소스(가능하면 CDN으로 분리)
- 내부 운영 도구 endpoint

인증 endpoint에 TLSv1.1이 얹혀 있으면 위험도가 급상승합니다. 인증 실패는 모든 기능 장애로 전파되기 때문입니다.

### 2) remoteIp / 네트워크 대역 기준으로 나누기

레거시 TLS는 “클라이언트”가 아니라 “중간 프록시”에서 발생하는 경우가 흔합니다.

- 기업망 outbound proxy
- 오래된 WAF
- 관제/보안 솔루션의 TLS inspection
- 데이터센터의 NAT/프록시

이 경우 앱을 고쳐도 해결되지 않습니다. 고객 네트워크 팀이 움직여야 합니다. 그래서 remoteIp(또는 그 상위 집계 단위)가 중요해집니다.

### 3) User-Agent는 힌트지만 정답은 아니다

UA가 정직한 경우도 있고, 그냥 빈 문자열인 경우도 많습니다. 그럼에도 UA는 다음을 빠르게 잡는 데 도움이 됩니다.

- 오래된 SDK(자체 배포한 라이브러리)
- IoT/임베디드 계열 클라이언트
- 배치/스크립트(curl, Python requests, Java)

UA 기반으로 “우리 팀이 고칠 수 있는 것”과 “고객이 고쳐야 하는 것”을 나누는 것만으로도 대응 속도가 달라집니다.

## 단계적 종료 공지와 기술적 가드레일

TLS 1.0/1.1 종료는 기술 변경이면서 커뮤니케이션 이벤트입니다. 특히 “차단 시점이 장애처럼 보일 수 있다”는 점 때문에, 커뮤니케이션이 기술 대응의 일부가 됩니다.

여기서 흔한 실패는 둘 중 하나입니다.

- (과소) 공지를 안 하고 차단 → 고객은 장애로 인지
- (과대) ‘전체 고객’에게 광역 공지 → 불필요한 혼란 + 문의 폭주

계측을 하는 이유는 공지 대상을 좁히기 위해서입니다.

### 공지 타임라인(내가 선호하는 형태)

- T-6주: 레거시 트래픽 식별(고객/파트너/네트워크 단위), 1차 개별 연락
- T-4주: 공지 문서 배포(종료일/영향/테스트 방법/지원 범위)
- T-3주: “사전 차단 리허설”을 위한 테스트 도메인 제공(가능하다면)
- T-2주: 레거시 트래픽이 남아 있는 대상에만 2차 리마인드
- T-1주: 마지막 리마인드 + 장애 접수 경로 명시
- T day: 차단/모니터링 강화

여기서 “테스트 방법”에 들어가야 할 것은 단순합니다.

- `openssl s_client -tls1_1 -connect your.domain:443` 같은 구버전 강제 시도가 실패해야 정상
- 반대로 TLS 1.2+로는 성공해야 정상

다만 이 글은 OpenSSL 커맨드 모음집이 아니라 운영 절차가 주제라서, 테스트 커맨드는 내부 runbook로 넣는 편이 낫습니다.

### opt-out을 쓰는 시나리오와 금지선

App Engine 문서에 따르면 2026년 8월 말까지는 opt-out이 가능하다고 되어 있습니다.[^3]

opt-out은 “고객 영향이 명확하고, 교체가 물리적으로 불가능하며, 기간이 짧게 확정된 경우”에만 써야 합니다.

- 고객 네트워크 장비 교체 납기(예: 3주)가 이미 계약으로 확정
- 우리 SDK 배포 사이클(예: 모바일 앱 스토어 심사)이 물리적으로 필요한 상황

금지선은 다음입니다.

- opt-out을 디폴트로 열어두고 “언젠가 닫자”로 두는 것
- 레거시 허용을 장기 운영으로 받아들이는 것

보안 팀과의 합의가 깨지는 문제도 있지만, 더 큰 문제는 “opt-out을 닫는 순간 똑같은 장애가 다시 발생”한다는 점입니다. 빚을 미루는 형태가 됩니다.

### 임시 레거시 엔드포인트를 만들고 싶다면

가끔 정말로 “구버전 TLS밖에 못 하는” 시스템(특히 오래된 장비/펌웨어)이 존재합니다. 그때 흔히 나오는 아이디어가 “레거시 전용 도메인”입니다.

이건 가능은 하지만, 조건이 까다롭습니다.

- 허용 대상 IP allowlist가 가능해야 합니다(불특정 다수 공개는 위험)
- 기간이 짧아야 합니다(예: 4주)
- 기능도 최소화해야 합니다(예: read-only 또는 특정 batch endpoint만)
- 트래픽 양이 제한적이어야 합니다

그리고 이 경우에도 “우회 경로”가 전부 Cloud provider의 정책 변화로 함께 막힐 수 있다는 점을 인정해야 합니다. TLS 1.0/1.1은 이미 광범위하게 퇴출되는 흐름이고, 구글만의 문제가 아닙니다.

## 교체 순서: client → proxy → SDK → edge policy

TLS 종료 작업은 순서를 잘못 잡으면 계속 되돌아오게 됩니다. 내가 추천하는 순서는 다음입니다.

### 1) 중간 프록시/게이트웨이부터 정리

레거시 TLS의 ‘진짜 주범’은 종종 중간 프록시입니다.

- 고객사 outbound proxy가 TLS 1.1까지만 지원
- 사내 보안 솔루션이 TLS inspection을 하면서 TLS 1.1로 downgrade

이 경우 앱/SDK를 아무리 바꿔도 소용이 없습니다. 먼저 네트워크 경로를 바꿔야 합니다.

계측이 remoteIp 단위로 나오는 이유가 여기 있습니다.

### 2) 조직이 통제하는 SDK/클라이언트 라이브러리

조직이 배포한 SDK(Go/Java/Python/Node)가 있다면, 그 SDK에서 TLS 설정을 명시적으로 올려 두는 편이 안전합니다.

특히 Go 클라이언트는 런타임 버전이 힌트가 됩니다. Go 1.18 릴리스 노트에는 클라이언트 사이드에서 TLS 1.0/1.1이 기본 비활성화(기본 최소 버전이 TLS 1.2)로 바뀐다고 명시되어 있습니다.[^5]

즉 TLS 1.0/1.1로 붙는 Go 클라이언트가 있다면, 대개는 다음 중 하나입니다.

- Go 1.17 이하(또는 매우 오래된 Go)
- 커스텀 `tls.Config.MinVersion`으로 낮춰 둔 코드
- 특이한 프록시/미들박스가 TLS를 재협상

SDK를 고칠 때는 “자동”을 믿지 말고, 최소 버전을 명시하는 편이 운영에서 유리합니다.

```go
tr := &http.Transport{
  TLSClientConfig: &tls.Config{
    MinVersion: tls.VersionTLS12,
  },
}
client := &http.Client{Transport: tr}
```

Go의 `crypto/tls` 구현에서 기본 최소 버전이 TLS 1.2로 잡힌다는 설명은 소스 주석에서도 확인할 수 있습니다.[^6]

### 3) 최종적으로 edge policy를 고정

계측 → 공지 → 교체가 진행되면, 마지막에 edge(App Engine 설정 또는 Load Balancer SSL policy)에서 TLS 1.2+를 고정합니다.

이때 운영적으로 중요한 것은 “언제 고정했는지”를 로그/런북/변경 기록에 남기는 것입니다. TLS 종료는 3개월 뒤에 또 감사가 들어오거나, 또 다른 시스템 이관 때 동일한 질문이 반복됩니다.

## App Engine(Go)에서 할 수 있는 일과 할 수 없는 일

여기서 App Engine 표준환경(Go) 기준으로, 내가 실무에서 헷갈렸던 지점을 정리합니다.

### App Engine 앱 코드로 TLS version을 직접 찍을 수 없다

앞서 말했듯 TLS termination이 앱 밖에서 일어나면, 앱은 TLS handshake 정보를 알 수 없습니다. “서버에서 TLS 1.2 이상만 허용”을 앱 코드로 해결하려는 시도는 보통 실패합니다.

### 대신 App Engine 설정과 edge에서 제어한다

App Engine은 최소 TLS 설정을 문서로 제공하고, 2026년 8월부터 TLS 1.2+를 기본 opt-in 한다고 밝히고 있습니다.[^3]

추가로, serverless NEG + Load Balancer를 붙이면 SSL policy와 로깅을 edge에서 더 세밀하게 다룰 수 있습니다.[^3]

이 구조의 장점은 두 가지입니다.

- 계측이 가능해집니다(`tls.protocol`, `tls.cipher`)
- 차단 정책도 edge에서 통제할 수 있습니다

단점은 구조 복잡도가 올라가고, Load Balancer 비용과 운영 포인트가 늘어난다는 점입니다.

내 기준에서는 “레거시 TLS가 있을 가능성이 있는 B2B API”라면 복잡도를 감수하고서라도 edge 계측을 붙이는 편이 낫습니다. 반대로 “불특정 다수 웹 트래픽 + 레거시 가능성이 거의 0”이라면 App Engine 기본 opt-in으로도 충분할 수 있습니다.

## 도입 판단 기준: 이 작업을 프로젝트로 만들 것인가, 체크리스트로 끝낼 것인가

TLS 1.0/1.1 차단 대비를 ‘프로젝트’로 승격해야 하는지, 단순 체크리스트로 끝낼 수 있는지 판단하는 기준을 적어 둡니다.

### 프로젝트로 만드는 게 맞는 경우

- 트래픽이 B2B/API 중심이고, 고객 네트워크(프록시) 변수가 크다
- 고객사가 소수이며, 고객별 매출/업무 영향이 크다
- 과거에도 “특정 고객만 갑자기 안 된다” 류의 이슈가 반복됐다
- 레거시 SDK/장비(IoT/임베디드/산업 장비)를 실제로 운영한다

이 경우 “계측 자동화 + 고객별 종료 계획”이 없으면, 9월 이후 차단이 장애처럼 터질 가능성이 높습니다.

### 체크리스트로 끝내도 되는 경우

- 트래픽이 최신 브라우저/최신 모바일 앱 중심
- 고객이 불특정 다수이며, 레거시를 특정해 커뮤니케이션하기 어렵다
- 이미 Cloud Load Balancer에서 Modern/Restricted SSL policy로 운영 중이고, TLS 1.0/1.1 트래픽이 장기간 0이었다

다만 이 경우에도 최소한 “7일간의 TLS 분포 스냅샷” 정도는 남기는 편이 좋습니다. 나중에 장애가 나면 가장 먼저 받는 질문이 “정말 레거시가 없었냐”이기 때문입니다.

이 작업은 결국 비용과 리스크를 맞바꾸는 선택입니다. 내 결론은 간단합니다. App Engine의 TLS 1.1 이하 차단 같은 변화는 기술적으로는 작은 설정이지만, 운영적으로는 사전 계측이 없으면 장애로 보일 확률이 높아서, 계측부터 깔고 들어가는 편이 이깁니다.

## 참고 자료

- [App Engine standard environment for Go release notes](https://docs.cloud.google.com/appengine/docs/standard/go/release-notes)
- [Secure your app with minimum TLS (standard environment)](https://docs.cloud.google.com/appengine/docs/standard/secure-minimum-tls)
- [Global external Application Load Balancer logging and monitoring](https://docs.cloud.google.com/load-balancing/docs/https/https-logging-monitoring)
- [Regional external Application Load Balancer logging and monitoring](https://docs.cloud.google.com/load-balancing/docs/https/https-reg-logging-monitoring)
- [SSL policies overview](https://docs.cloud.google.com/load-balancing/docs/ssl-policies-concepts)
- [Use SSL policies](https://docs.cloud.google.com/load-balancing/docs/use-ssl-policies)
- [Go 1.18 Release Notes (TLS 1.0 and 1.1 disabled by default client-side)](https://go.dev/doc/go1.18)
- [Go 1.17 Release Notes (pre-announcement of TLS default change)](https://go.dev/doc/go1.17)
- [crypto/tls source (comment about default minimum TLS version)](https://go.googlesource.com/go/+/refs/tags/go1.20.14/src/crypto/tls/common.go)
- [12월 클라우드 3사 신제품 전쟁: AWS는 ‘Agent + Multicloud’, GCP는 ‘Agent Engine GA’, Azure는 ‘Foundry + 새 DB’로 판이 커졌다](https://daewooki.github.io/posts/12-3-aws-agent-multicloud-gcp-agent-engi-1/)
- [LLM 전쟁의 ‘다음 라운드’가 열렸다: GPT‑5.2·Codex와 Gemini 3 Flash, 그리고 ChatGPT App Directory](https://daewooki.github.io/posts/2025-12-llm-gpt52codex-gemini-3-flash-ch-1/)

[^1]: <https://docs.cloud.google.com/appengine/docs/standard/go/release-notes>
[^2]: <https://docs.cloud.google.com/load-balancing/docs/https/https-logging-monitoring?authuser=110>
[^3]: <https://docs.cloud.google.com/appengine/docs/standard/secure-minimum-tls?authuser=0>
[^4]: <https://docs.cloud.google.com/load-balancing/docs/https/https-reg-logging-monitoring?hl=en>
[^5]: <https://go.dev/doc/go1.18>
[^6]: <https://go.googlesource.com/go/%2B/refs/tags/go1.20.14/src/crypto/tls/common.go>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
