---
title: "Caddy 2.11.9: reverse_proxy 기본값 변화 안전 배포"
description: "Caddy 2.11.9 업그레이드에서 reverse_proxy 기본값(Host/SNI/HTTP2·HTTP3/timeout) 변화가 장애로 번지지 않게 테스트·관측·롤백으로 굳힙니다."
date: 2026-11-06 14:49:17 +0900
categories: ["Infrastructure", "Caddy"]
tags: ["caddy", "reverse-proxy", "http2", "http3", "observability", "rollout"]
render_with_liquid: false
---

## v2.11.9 업그레이드에서 reverse_proxy를 먼저 보는 이유

Caddy v2.11.9는 GitHub 릴리스 기준으로 2026-11-05 전후(UTC 2026-11-05 01:30 표기)로 배포된 태그입니다.[^1]

이 릴리스 노트만 놓고 보면 중심은 FastCGI 보안 이슈와 Caddyfile 어댑터의 breaking change(예: TLS policy 병합 시 `client_auth` 충돌을 에러로 처리)입니다.[^2]  
그런데 운영에서 체감 장애를 만드는 지점은 릴리스 노트의 제목과 다르게 터지는 경우가 많습니다. Caddy는 Automatic HTTPS/ACME로 TLS를 “쉽게” 만들어 주는 만큼, 그 위에 얹히는 `reverse_proxy`의 기본 동작 변화가 조용히 퍼지기 좋습니다.

내가 v2.11 라인에서 특히 예민하게 보는 포인트는 세 가지입니다.

1) **HTTPS 업스트림으로 프록시할 때 Host 헤더가 자동으로 바뀌는 기본값**(v2.11.0부터)  
2) HTTP/2, HTTP/3이 기본 활성화되는 환경에서 “스트리밍/업로드/타임아웃”이 프록시 체인 전체로 전염되는 방식  
3) 기본값 의존도가 높은 설정에서, “안전한 재배포”를 기능이 아니라 절차(테스트/관측/롤백)로 고정하는 것

Host 헤더 자동 재작성은 v2.11에서 PR로 명시적으로 들어갔습니다(HTTPS 업스트림 프록시 시 `Host`를 `{upstream_hostport}`로 맞추는 방향).[^3]  
공식 문서도 동일한 방향을 적고 있습니다. “v2.11.0부터 HTTPS 업스트림으로 프록시할 때 `Host` override를 수동으로 하지 않아도 된다”가 곧 “원래 Host를 그대로 넘기던 기본값에서 벗어났다”는 의미입니다.[^4]

이게 왜 위험하냐면, 많은 업스트림 애플리케이션이 `Host`를 다음 용도로 씁니다.

- vhost 라우팅(같은 IP/포트에서 여러 사이트를 호스팅)
- absolute redirect 생성(`Location: https://$host/...`)
- multi-tenant 식별(서브도메인 기반 테넌트)
- OAuth callback URL 검증, CSRF origin 검증

Caddy는 기본적으로 `X-Forwarded-Host`를 세팅해 주지만, 업스트림이 그 헤더를 보지 않는다면 Host 자동 재작성은 곧 동작 변화입니다.[^4]

정리하면, v2.11.9 자체가 reverse_proxy breaking change를 크게 내세우진 않더라도, “지금 최신으로 올리는 작업”이 곧 “현재 운영이 어떤 기본값에 기대고 있는지 재검증하는 작업”이 됩니다.

## reverse_proxy 기본 동작: Host, SNI, 업스트림 선택이 엮이는 지점

`reverse_proxy`는 겉보기엔 단순하지만 내부적으로는 다음 순서로 묶여 돌아갑니다.

- 클라이언트 요청(요청 라우팅은 Caddy가 Host/Path matcher로 처리)
- 업스트림 선택(고정 upstream, 혹은 dynamic upstream)
- 업스트림으로의 round trip(HTTP transport, TLS 여부, HTTP 버전 협상)
- 헤더 처리(요청/응답 모두)

여기서 운영 사고로 직행하는 결합은 `Host header ↔ TLS SNI ↔ 업스트림 라우팅`입니다.

### 기본 헤더 패스스루와 예외

공식 문서 기준으로, Caddy reverse_proxy는 기본적으로 들어온 요청 헤더(Host 포함)를 그대로 업스트림으로 전달합니다. 예외는 `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`를 Caddy가 보안 목적(스푸핑 방지)으로 재작성/증강한다는 점입니다.[^4]

그런데 HTTPS 업스트림으로 프록시할 때는 문제가 하나 생깁니다.

- TLS 핸드셰이크는 “HTTP 헤더”를 보기 전에 끝납니다.
- 업스트림이 vhost 기반이면, TLS 단계에서 SNI가 맞아야 올바른 인증서/라우팅이 됩니다.
- SNI는 대개 `Host`에서 파생됩니다.

이 때문에 과거에는 `reverse_proxy https://...`를 쓰면서 `header_up Host {upstream_hostport}`를 명시하라는 가이드가 많이 돌았습니다. v2.11.0부터는 이 동작을 기본으로 가져갔고, 문서에도 “자동으로 처리되니 수동으로 Host를 override할 필요가 없다”가 적혀 있습니다.[^4]

즉, v2.11부터는 “HTTPS 업스트림일 때는 Host가 그대로 전달되지 않을 수 있다”가 기본 전제가 됩니다.

### 자동 Host 재작성의 실전 함정

자동 Host 재작성은 순기능이 큽니다.

- 업스트림이 HTTPS이고 서버명이 필요한 경우, 설정 실수로 TLS handshake가 실패하는 경우를 줄입니다.
- TLS와 Host 라우팅을 동일 기준으로 맞춰 “애매한 상태”를 줄입니다.

하지만 반대급부가 있습니다.

- 업스트림 앱이 Host 기반으로 redirect를 만들면, redirect 대상이 “업스트림 주소”로 바뀝니다.
- 업스트림이 또 다른 reverse proxy(예: 내부 Nginx/Envoy/Ingress)라면, vhost 라우팅이 바뀝니다.
- 보안 장치(allowed host, callback allowlist)가 Host 값을 기준으로 판단하면, 정상 요청이 차단되거나 반대로 잘못 허용될 여지가 생깁니다.

실제 사례로, v2.11.2에서 `reverse_proxy https://10.x.x.x:443` 형태(IP로 HTTPS 업스트림 지정)일 때 브라우저가 업스트림 IP로 리다이렉트되는 문제를 겪고, `header_up Host "도메인"`을 수동으로 넣어서 해결했다는 이슈가 있습니다.[^5]

또, v2.11에서 Host 관련 기본값이 바뀐 뒤 “pre-v2.11 동작으로 되돌리기 위해 `header_up Host {hostport}`를 넣었더니 경고가 뜬다” 같은 혼선(경고 메시지가 과거 전제에 묶여 있음)도 보고된 바 있습니다.[^6]

이 두 가지는 결론이 같습니다.

- 기본값은 선의로 바뀌어도 운영에서는 “의미 변화”로 읽혀야 합니다.
- 의미 변화는 문서로 이해하는 데서 끝나면 안 되고, **테스트 케이스로 고정**해야 합니다.

## HTTP/2·HTTP/3 기본 활성화가 프록시에 주는 파장

Caddyfile 글로벌 옵션의 `servers` 블록에서 `protocols` 기본값은 `h1 h2 h3`입니다.[^7]  
즉, 특별히 끄지 않으면 클라이언트-엣지 구간에서 HTTP/3(QUIC/UDP)까지 열리는 방향이 기본입니다.

여기서 흔한 오해는 “HTTP/3는 켜져도 그냥 더 빠르겠지”입니다. 운영에서는 다음 이유로 장애 확률이 올라갑니다.

- 방화벽/보안그룹이 TCP 443만 열려 있고 UDP 443이 막혀 있으면, 클라이언트가 h3 시도 후 fallback하면서 추가 지연이 생깁니다.
- L4/L7 장비가 QUIC를 중간에서 건드리면, 특정 단말/망에서만 간헐 오류가 발생합니다.
- HTTP/3는 “서버만 켠다고” 끝이 아니라, 관측(클라이언트 프로토콜 분포/에러율)까지 묶어야 의미가 있습니다.

반대로 HTTP/2도 안전지대가 아닙니다. v2.11.6에서 기본 idle read/write timeout이 들어가면서 스트리밍 계열에서 문제가 보고되었고, v2.11.7과 v2.11.8에서 HTTP/2 스트림 reset, 업로드 중 502 같은 회귀가 수정되었습니다.[^8]

이 얘기는 “2.11.9면 다 해결”로 끝나지 않습니다.

- 현재 운영이 어떤 스트리밍 특성을 가지는지(SSE, WebSocket, gRPC, chunked upload)
- 타임아웃/버퍼링 기본값이 그 특성과 충돌하지 않는지
- 프로토콜이 달라졌을 때(HTTP/1.1 ↔ HTTP/2 ↔ HTTP/3) 장애 증상이 로그에 어떻게 찍히는지

이걸 릴리스마다 회귀 테스트로 굳히는 편이 싸게 먹힙니다.

참고로 HTTP/2 프록시 체인에서 취약점/패치가 운영 영향으로 번진 사례는 이미 여러 번 있었습니다. 내 블로그에서는 [Apache httpd 2.4.69: HTTP/2 패치가 프록시 체인에 미치는 영향](https://daewooki.github.io/posts/apache-httpd-2469-proxy-chain-security/), [Tomcat 10.1 HTTP/2 mix-up 취약점 대응 런북](https://daewooki.github.io/posts/tomcat-http2-response-mixup-runbook/) 같은 형태로 “프로토콜 레벨 변화는 프록시 레벨에서 먼저 잡아야 한다”를 다뤘는데, Caddy도 같은 결입니다.

## 재현 가능한 회귀 테스트 랩

운영에 적용하기 전에, Host/SNI/프로토콜 변화가 실제로 무엇을 바꾸는지 손으로 확인할 수 있어야 합니다. 아래 랩은 다음을 재현합니다.

- HTTPS 업스트림으로 프록시할 때 Host가 업스트림 주소로 바뀌는 현상
- 그로 인해 업스트림 라우팅/리다이렉트가 깨지는 형태
- 관측(접근 로그/에러 로그/metrics/업스트림 상태)을 같이 남기는 형태

구성 요소:

- edge: Caddy v2.11.9 (클라이언트가 붙는 엔드포인트)
- upstream: 간단한 Go HTTPS 서버(요청을 JSON으로 에코 + Host 기반 라우팅 + redirect)
- CA/인증서: OpenSSL로 로컬 CA를 만들고 upstream 서버 인증서를 서명

### 디렉터리 구조

```text
caddy-lab/
  docker-compose.yml
  certs/
    make-certs.sh
    ca.pem
    ca.key
    upstream.crt
    upstream.key
  edge/
    Caddyfile
  upstream/
    Dockerfile
    main.go
```

### 인증서 생성 스크립트(certs/make-certs.sh)

이 랩은 업스트림을 IP로 붙되(`https://172.28.0.10:9443`), TLS SNI는 도메인(`upstream.local`)로 고정하는 운영 패턴을 재현합니다. IP로 붙는 이유는 내부망/VPN/고정 IP 환경에서 흔하고, 그때 Host 기본값 변화가 redirect/vhost를 망가뜨리기 쉽기 때문입니다(앞서 언급한 이슈 형태).[^5]

```bash
#!/usr/bin/env bash
set -euo pipefail

mkdir -p certs
cd certs

# 1) 로컬 CA 생성
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -subj "/C=KR/ST=Seoul/L=Seoul/O=Lab CA/OU=Infra/CN=lab-ca" \
  -out ca.pem

# 2) upstream.local 서버 인증서 생성(서버 인증서에 SAN 포함)
openssl genrsa -out upstream.key 2048

cat > upstream.cnf <<'EOF'
[ req ]
distinguished_name = dn
req_extensions = req_ext
prompt = no

[ dn ]
C = KR
ST = Seoul
L = Seoul
O = Lab Upstream
OU = Infra
CN = upstream.local

[ req_ext ]
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = upstream.local
EOF

openssl req -new -key upstream.key -out upstream.csr -config upstream.cnf

cat > upstream-ext.cnf <<'EOF'
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = upstream.local
EOF

openssl x509 -req -in upstream.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
  -out upstream.crt -days 365 -sha256 -extfile upstream-ext.cnf

rm -f upstream.csr upstream.cnf upstream-ext.cnf ca.srl

echo "Generated: ca.pem, upstream.crt/upstream.key"
```

### upstream 서버(upstream/main.go)

이 서버는 다음 엔드포인트를 제공합니다.

- `GET /echo`: Host, X-Forwarded-Host, Proto(업스트림이 받은 HTTP 버전) 등을 JSON으로 반환
- `GET /vhost`: Host가 기대값과 다르면 404
- `GET /redirect`: `Location: https://{Host}/after-login`을 반환(Host 변화가 사용자에게 바로 보이는 형태)

```go
package main

import (
	"crypto/tls"
	"encoding/json"
	"log"
	"net/http"
	"os"
)

type Echo struct {
	Method          string            `json:"method"`
	URI             string            `json:"uri"`
	Proto           string            `json:"proto"`
	Host            string            `json:"host"`
	XFwdHost        string            `json:"x_forwarded_host"`
	XFwdProto       string            `json:"x_forwarded_proto"`
	XFwdFor         string            `json:"x_forwarded_for"`
	Headers         map[string]string `json:"headers"`
	ExpectedHost    string            `json:"expected_host"`
	VhostMatched    bool              `json:"vhost_matched"`
	RedirectExample string            `json:"redirect_example"`
}

func main() {
	addr := env("ADDR", ":9443")
	cert := env("TLS_CERT", "/certs/upstream.crt")
	key := env("TLS_KEY", "/certs/upstream.key")
	expected := env("EXPECTED_HOST", "edge.local:8443")

	mux := http.NewServeMux()

	mux.HandleFunc("/echo", func(w http.ResponseWriter, r *http.Request) {
		hdr := map[string]string{}
		for _, k := range []string{"Host", "X-Forwarded-Host", "X-Forwarded-Proto", "X-Forwarded-For", "User-Agent"} {
			hdr[k] = r.Header.Get(k)
		}

		e := Echo{
			Method:          r.Method,
			URI:             r.RequestURI,
			Proto:           r.Proto,
			Host:            r.Host,
			XFwdHost:        r.Header.Get("X-Forwarded-Host"),
			XFwdProto:       r.Header.Get("X-Forwarded-Proto"),
			XFwdFor:         r.Header.Get("X-Forwarded-For"),
			Headers:         hdr,
			ExpectedHost:    expected,
			VhostMatched:    r.Host == expected,
			RedirectExample: "https://" + r.Host + "/after-login",
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(e)
	})

	mux.HandleFunc("/vhost", func(w http.ResponseWriter, r *http.Request) {
		if r.Host != expected {
			http.NotFound(w, r)
			return
		}
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("vhost ok\n"))
	})

	mux.HandleFunc("/redirect", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Location", "https://"+r.Host+"/after-login")
		w.WriteHeader(http.StatusPermanentRedirect) // 308
	})

	srv := &http.Server{
		Addr:    addr,
		Handler: mux,
		TLSConfig: &tls.Config{
			MinVersion: tls.VersionTLS12,
		},
	}

	log.Printf("listening on %s, expected host=%s", addr, expected)
	log.Fatal(srv.ListenAndServeTLS(cert, key))
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
```

### upstream Dockerfile(upstream/Dockerfile)

```dockerfile
FROM golang:1.23 AS build
WORKDIR /src
COPY main.go ./
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/upstream ./main.go

FROM gcr.io/distroless/static:nonroot
COPY --from=build /out/upstream /upstream
USER nonroot:nonroot
ENTRYPOINT ["/upstream"]
```

### docker-compose.yml

HTTP/3 테스트를 하려면 UDP 포트 매핑이 필요합니다. 여기서는 `8443/tcp`와 `8443/udp`를 같이 매핑합니다.

```yaml
services:
  upstream:
    build: ./upstream
    container_name: upstream
    environment:
      ADDR: ":9443"
      TLS_CERT: "/certs/upstream.crt"
      TLS_KEY: "/certs/upstream.key"
      EXPECTED_HOST: "edge.local:8443"
    volumes:
      - ./certs:/certs:ro
    networks:
      labnet:
        ipv4_address: 172.28.0.10

  edge:
    image: caddy:2.11.9
    container_name: edge
    ports:
      - "8080:8080/tcp"
      - "8443:8443/tcp"
      - "8443:8443/udp"
      # 랩에서만 admin 노출(운영에서는 금지)
      - "2019:2019/tcp"
    volumes:
      - ./edge/Caddyfile:/etc/caddy/Caddyfile:ro
      - ./certs:/certs:ro
      - ./edge-data:/data
      - ./edge-config:/config
    networks:
      - labnet

networks:
  labnet:
    ipam:
      config:
        - subnet: 172.28.0.0/24
```

### edge Caddyfile(edge/Caddyfile) — 1차(문제 재현용)

핵심은 업스트림을 `https://172.28.0.10:9443`로 잡고, TLS는 `upstream.local`로 검증한다는 점입니다.

- 업스트림 주소는 IP라서 “기본값대로라면” Host는 `{upstream_hostport}` → `172.28.0.10:9443`가 됩니다.[^4]
- 하지만 TLS SNI/검증은 `tls_server_name upstream.local`로 맞추기 때문에 handshake는 성공합니다. (이 패턴이 운영에서 많이 나옵니다.)[^4]

```caddyfile
{
	admin :2019
	debug

	http_port 8080
	https_port 8443

	# metrics 수집 활성화(그리고 admin API에는 기본 /metrics가 붙음)
	metrics

	servers {
		# 기본값은 h1 h2 h3지만, 실험에서 명시적으로 고정
		protocols h1 h2 h3
	}
}

edge.local:8443 {
	tls internal

	# access log(JSON)
	log {
		output stdout
		format json
	}

	reverse_proxy https://172.28.0.10:9443 {
		transport http {
			# upstream 인증서는 로컬 CA로 서명했으니 trust pool 지정
			tls_trust_pool file /certs/ca.pem
			# SNI/검증용 이름을 upstream.local로 고정
			tls_server_name upstream.local
		}
	}
}
```

공식 문서에서 `transport http`의 `versions` 기본값은 `1.1 2`입니다.[^4]  
즉 업스트림(Go 서버)이 HTTP/2를 받아주면, edge→upstream 구간이 HTTP/2가 될 수 있습니다. 이 또한 “업스트림 앱이 특정 HTTP 버전에서만 미묘하게 다르게 동작하는가”를 확인해야 하는 포인트입니다.

## 테스트 케이스 1: HTTPS 업스트림에서 Host 자동 재작성

### 실행

```bash
# 0) 인증서 생성
bash certs/make-certs.sh

# 1) 컨테이너 빌드/실행
docker compose up --build
```

다른 터미널에서 요청을 보냅니다.

```bash
# edge.local을 로컬(127.0.0.1)로 강제 라우팅
curl -sk --resolve edge.local:8443:127.0.0.1 https://edge.local:8443/echo | jq
```

### 기대 결과(핵심 필드)

- `host`가 `172.28.0.10:9443`로 찍히면: Host가 업스트림 주소로 바뀌어 들어간 것입니다.
- `x_forwarded_host`는 `edge.local:8443`로 남아있을 가능성이 큽니다.

이 조합이 제일 위험합니다.

- 업스트림은 `Host`를 보고 redirect/vhost를 판단
- 원래 사용자가 접근한 Host는 `X-Forwarded-Host`에만 남음

즉, 업스트림이 `X-Forwarded-Host`를 보도록 이미 설계되어 있으면 괜찮고, 그렇지 않으면 동작이 바뀝니다. 이 동작이 v2.11.0부터 기본값으로 들어갔다는 것이 공식 문서의 의미입니다.[^4]

## 테스트 케이스 2: 업스트림 라우팅/리다이렉트 깨짐을 잡아내는 방법

Host 기본값 변화가 장애로 번지는 형태를 두 가지로 쪼개면 빠르게 잡힙니다.

1) vhost 라우팅 실패(404/401/잘못된 앱으로 라우팅)  
2) redirect 대상 오염(사용자가 내부 IP/내부 호스트로 날아감)

이 랩에서는 `/vhost`, `/redirect`로 각각 확인합니다.

### 2-1) vhost 라우팅 실패 재현

```bash
curl -sk --resolve edge.local:8443:127.0.0.1 https://edge.local:8443/vhost -i
```

현재 upstream은 `EXPECTED_HOST=edge.local:8443`로 설정돼 있습니다. 그런데 앞 단계에서 본 것처럼 Host가 `172.28.0.10:9443`로 바뀌어 들어가면 `/vhost`는 404가 납니다.

운영에서는 이런 형태로 보입니다.

- IdP/SSO 앞단: “unknown host”
- 앱 서버: “Invalid Host header”
- 내부 reverse proxy: “no app for hostname”, “no vhost match”

### 2-2) redirect 대상 오염 재현

```bash
curl -sk --resolve edge.local:8443:127.0.0.1 https://edge.local:8443/redirect -I
```

`Location`이 `https://172.28.0.10:9443/after-login` 같이 나오면, 사용자에게 내부 IP가 노출되는 것은 물론이고 브라우저가 그쪽으로 리다이렉트되면서 장애가 됩니다. 이 증상은 실제로 비슷한 구성에서 보고된 바 있습니다.[^5]

### 수정안 A: v2.10까지의 감각(원래 Host 유지)을 명시적으로 고정

공식 문서는 “자동으로 바뀌는 동작을 원치 않으면 원래 Host로 되돌릴 수 있다”고 적고 있고, 예시로 `header_up Host {hostport}`를 들고 있습니다.[^4]

edge Caddyfile의 reverse_proxy 블록을 아래처럼 바꿉니다.

```caddyfile
	reverse_proxy https://172.28.0.10:9443 {
		header_up Host {hostport}
		transport http {
			tls_trust_pool file /certs/ca.pem
			tls_server_name upstream.local
		}
	}
```

리로드:

```bash
docker exec -it edge caddy reload --config /etc/caddy/Caddyfile
```

다시 테스트:

```bash
curl -sk --resolve edge.local:8443:127.0.0.1 https://edge.local:8443/echo | jq
curl -sk --resolve edge.local:8443:127.0.0.1 https://edge.local:8443/vhost -i
curl -sk --resolve edge.local:8443:127.0.0.1 https://edge.local:8443/redirect -I
```

기대 결과는 다음입니다.

- upstream `/echo`에서 `host`가 `edge.local:8443`로 돌아옴
- `/vhost`가 200
- `/redirect`의 Location이 `https://edge.local:8443/after-login`

수정안 A는 “업스트림이 Host 기반으로 동작한다”는 전제를 그대로 살립니다.

### 수정안 B: Host는 업스트림용으로 쓰고, 원래 Host는 X-Forwarded-Host로만 신뢰

이건 애플리케이션/업스트림 프록시를 손댈 수 있을 때 더 깔끔한 방향입니다.

- Caddy 기본값(HTTPS 업스트림이면 Host를 업스트림으로 맞춤)을 유지
- 업스트림 앱/프록시가 원래 호스트가 필요하면 `X-Forwarded-Host`를 보게 수정

Caddy는 기본적으로 `X-Forwarded-Host`를 세팅합니다.[^4]  
프록시 체인에 여러 hop이 있으면 `trusted_proxies`까지 같이 묶어야 하고(스푸핑 방지), 여기부터는 앱별 런북이 됩니다.

내 경우, “업스트림이 또 다른 reverse proxy”인 구성(예: 내부 Nginx에서 여러 서비스 vhost 라우팅)은 수정안 A가 더 현실적인 경우가 많았습니다. 반대로 “업스트림이 단일 앱이고 프레임워크 레벨에서 proxy trust 설정이 잘 돼 있다”면 수정안 B가 더 낫습니다.

## 테스트 케이스 3: 스트리밍(SSE/업로드)과 idle timeout 회귀

v2.11.6에서 기본 idle read/write timeout이 추가되면서 스트리밍/업로드 계열에서 문제를 만들 수 있다는 점이 릴리스 노트에 적혀 있습니다.[^8]

이후 v2.11.7에서는 HTTP/2에서 reverse_proxy가 request body를 읽는 도중 panic이 나거나, SSE 같은 스트리밍이 “1분 후에 끊기는” 문제가 수정되었다고 되어 있습니다.[^9]  
v2.11.8에서도 HTTP/2 업로드 중 reverse_proxy가 request body를 잃어버리고 502가 나는 회귀를 추가로 수정했습니다.[^10]

이 흐름을 v2.11.9 관점에서 읽으면 다음입니다.

- 2.11.6에서 기본값이 바뀌었다
- 2.11.7/8에서 그 기본값이 만들었던 예상 밖 상호작용을 계속 패치했다
- 2.11.9는 2.11.8 위에 추가 보안 수정이 들어간 빠른 후속이다[^2]

따라서 안전 배포 체크리스트는 “내 트래픽 패턴이 이 영역을 밟는가”를 확인하는 테스트로 구성하는 게 맞습니다.

### 최소 스트리밍 점검 항목(운영에서 많이 밟는 것)

- SSE: 1분 이상 조용한 구간이 있는지(예: 이벤트가 뜸한 대시보드)
- WebSocket: 재배포(reload) 때 연결이 급격히 끊기는지(재접속 폭탄)
- 업로드: 대용량 업로드에서 업스트림 읽기 지연이 있는지

Caddy reverse_proxy에는 config reload 시 스트림을 바로 끊지 않게 하는 `stream_close_delay` 같은 옵션도 있습니다.[^4]  
이런 건 문서만 읽고 켜기보다, 실제 운영 트래픽(웹소켓 커넥션 수, reconnect 폭)을 보고 결정하는 쪽이 안전합니다.

## 관측: 로그/메트릭/업스트림 상태로 확신 쌓기

테스트 케이스는 “깨지는지”만 보면 반쪽입니다. 운영 배포에서는 “깨질 때 어떤 신호로 먼저 보이는지”가 더 중요합니다.

### 1) access log를 구조화해서, Host/Proto/Upstream을 바로 잡아내기

Caddy 로그는 구조화 로그(zap 기반)로 설계돼 있고, reverse proxy 로깅도 필드 기반으로 떨어지도록 만들어져 있습니다.[^11]

내가 최소로 남기는 건 다음입니다.

- request.host
- request.proto (HTTP/1.1, HTTP/2.0, HTTP/3.0)
- status
- duration
- 에러가 날 때 err_id/err_trace

그리고 reverse_proxy가 붙은 라우트는 “업스트림 주소”가 같이 찍히는지 확인합니다. 이게 있어야 Host 변화/라우팅 변화가 생겼을 때 분석이 빨라집니다.

v2.11.8에는 매칭되는 요청에만 access log 레벨을 바꾸는 `log_level`도 들어갔습니다(헬스체크만 DEBUG로 올리는 식).[^10]  
이건 디버깅 때 유용하지만, 운영에서는 “지속적인 고레벨 로그”가 비용이 되므로 상황별로만 씁니다.

### 2) metrics: admin /metrics + 필요하면 별도 metrics 엔드포인트

Caddy는 Prometheus 형식의 metrics를 노출할 수 있고, 기본적으로 admin API에 `/metrics`가 붙습니다.[^12]  
또 Caddyfile에는 `metrics` 핸들러 디렉티브가 있어서 별도 경로로 노출할 수도 있습니다(운영에서 admin API를 끄는 경우를 고려).[^13]

랩에서는 admin을 노출했으니 다음으로 확인합니다.

```bash
curl -s http://127.0.0.1:2019/metrics | head
```

운영에서는 admin API 자체를 외부에 노출하지 않는 게 기본이고, metrics도 별도 listener/route로 떼거나 내부 스크래핑만 허용하는 쪽이 안전합니다.

### 3) reverse proxy upstream 상태: /reverse_proxy/upstreams

Caddy admin API에는 reverse proxy upstream 상태를 보여주는 엔드포인트가 있습니다. 공식 API 문서에 `GET /reverse_proxy/upstreams`가 명시돼 있습니다.[^14]

랩에서는:

```bash
curl -s http://127.0.0.1:2019/reverse_proxy/upstreams | jq
```

이 엔드포인트는 배포 중 다음 질문에 답하는 데 도움이 됩니다.

- “장애가 난 게 업스트림 unhealthy 때문인가, Host/라우팅 변경 때문인가?”
- “카나리에서만 특정 upstream이 실패하는가?”

로그만으로도 되긴 하지만, 운영에서는 로그 파싱 비용이 커서 이런 상태 API가 더 빠른 경우가 많았습니다.

## 배포 전략: 바이너리 업그레이드와 설정 변경을 분리

v2.11.9로 “올린다”는 말을 실제로 쪼개면 두 가지입니다.

1) Caddy 바이너리/이미지 버전 변경  
2) Caddyfile/JSON config 변경

Host 기본값 변화처럼 “버전만 올려도 의미가 바뀌는 영역”이 있을 때는 두 변경을 같은 배포로 묶으면 원인 규명이 느려집니다.

내가 선호하는 절차는 다음입니다.

- (A) config는 그대로 둔 채로 바이너리만 올리고, 회귀 테스트/관측을 통과시키기
- (B) 그 다음 config를 리팩터링(불필요한 header_up 제거, protocols 조정 등)

Caddy는 reload가 내부적으로 admin API `/load`를 사용하고, 로딩 실패 시 기존 config로 롤백된다고 문서에 명시돼 있습니다.[^14]  
이 특성은 “설정 변경을 안전하게” 만드는 기반이지만, 반대로 말하면 “바이너리 업그레이드로 의미가 바뀌는 건 reload 롤백과 다른 문제”이기도 합니다.

그래서 다음 체크를 같이 묶습니다.

- `caddy version`으로 실제 실행 중인 버전 고정(이미지 태그 `latest` 금지)
- reverse_proxy가 포함된 핵심 엔드포인트에 대해, 위 랩에서 만든 형태의 Host/redirect/vhost 테스트를 CI처럼 자동화
- HTTP/2/HTTP/3는 “켜져 있는지”가 아니라 “실제 사용 비율과 에러율”을 모니터링

## 롤백: 실패를 전제로 한 복구 시나리오

Caddy는 config reload 실패 시 롤백을 보장하지만, 버전 업그레이드에서 필요한 롤백은 그것만이 아닙니다.

### 1) 설정 롤백(가장 먼저)

- Host/라우팅이 깨지는 유형은 설정 한 줄(`header_up Host ...`)로 되돌릴 수 있는 경우가 많습니다.
- 이때 중요한 건 “되돌릴 설정이 이미 준비돼 있어야 한다”는 점입니다.

즉, 배포 전에 다음 두 config를 같이 준비합니다.

- 기본값을 신뢰하는 config(최소 설정)
- 의미가 바뀌는 부분만 고정하는 config(Host 고정, protocols 고정, upstream HTTP 버전 고정)

그리고 `caddy reload`는 실패 시 자동 롤백이 된다는 점을 알고 있어야 합니다.[^15]

### 2) 바이너리/이미지 롤백(그 다음)

Host 기본값 변화 같은 것은 “버전 자체의 의미 변화”라서 config를 손대기 싫은 조직에서는 버전 롤백이 더 현실적일 수 있습니다.

- Docker라면 `caddy:2.11.9` 같은 고정 태그로 올리고, 문제 발생 시 이전 태그로 되돌립니다.
- 패키지 배포라면 이전 패키지를 캐시해 두고 바로 downgrading 할 수 있어야 합니다.

여기서 주의할 점은 데이터 디렉터리(`/data`)와 config autosave(`/config`)를 유지할지 여부입니다. Caddy는 config API 기반으로 동작할 때 마지막 config를 디스크에 저장하고, `--resume`로 복구할 수 있다고 문서에 적고 있습니다.[^14]  
운영에서는 이 기능이 편하지만, 롤백 시나리오에서는 “이전 버전이 현재 autosave를 그대로 읽어도 안전한가”를 별도로 확인하는 게 좋습니다.

## 도입 판단 기준

v2.11.9로 올릴 때 reverse_proxy 관점에서 내가 최종적으로 확인하는 질문은 아래입니다.

### Host/SNI/라우팅

- 업스트림이 HTTPS인가?
  - 그렇다면 v2.11 기본값은 Host를 업스트림에 맞추는 방향이다.[^4]
- 업스트림이 Host 기반으로 redirect/vhost/multi-tenant를 하는가?
  - 그렇다면 `header_up Host {hostport}`(또는 명시 호스트)로 고정하거나, 업스트림이 `X-Forwarded-Host`를 보게 강제해야 한다.[^4]
- 업스트림 주소가 IP이고, TLS 검증/SNI는 도메인으로 맞추는가?
  - 이 패턴은 Host 자동 재작성과 합쳐져 redirect 오염이 잘 나온다(랩처럼 재현 가능).[^5]

### HTTP/2, HTTP/3

- 클라이언트에서 HTTP/3를 실제로 쓸 것인가?
  - UDP 443(또는 운영 포트)가 열려 있고, 관측으로 에러율을 관리할 자신이 없다면 `protocols h1 h2`로 고정하는 게 더 싸게 먹힌다.[^7]
- 스트리밍/업로드 트래픽이 있는가?
  - 2.11.6~2.11.8에서 idle timeout 관련 수정이 이어졌고, 내 트래픽이 그 케이스를 밟는지 테스트로 확인해야 한다.[^8]

### 관측과 롤백

- access log에서 Host/Proto/Upstream을 바로 볼 수 있는가?
  - Caddy 로그는 구조화되어 있고, reverse_proxy 내부도 필드 로그 중심으로 설계돼 있다.[^11]
- metrics와 upstream 상태를 배포 중에 확인할 수 있는가?
  - admin `/metrics`와 `/reverse_proxy/upstreams`를 내부에서만이라도 확인 가능해야 한다.[^12]
- config 롤백과 바이너리 롤백 플랜이 각각 준비돼 있는가?
  - `/load`는 실패 시 롤백을 보장하지만(설정 오류), 의미 변화는 별개다.[^14]

결국 Caddy 업그레이드의 핵심은 “기본값을 신뢰하되, 기본값에 기대는 부분은 테스트로 못 박는다”입니다. reverse_proxy는 그 대상 1순위이고, v2.11 이후에는 특히 Host/SNI 결합부가 그렇습니다.

## 참고 자료

- [Caddy v2.11.9 릴리스 노트](https://github.com/caddyserver/caddy/releases/tag/v2.11.9)
- [Caddy v2.11.8 릴리스 노트](https://github.com/caddyserver/caddy/releases/tag/v2.11.8)
- [Caddy v2.11.7 릴리스 노트](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)
- [Caddy v2.11.6 릴리스 노트](https://github.com/caddyserver/caddy/releases/tag/v2.11.6)
- [reverse_proxy 문서](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
- [Global options: servers/protocols 문서](https://caddyserver.com/docs/caddyfile/options)
- [Caddy Admin API 문서](https://caddyserver.com/docs/api)
- [How Logging Works](https://caddyserver.com/docs/logging)
- [Monitoring Caddy with metrics](https://caddyserver.com/docs/metrics)
- [metrics 디렉티브 문서](https://caddyserver.com/docs/caddyfile/directives/metrics)
- [PR #7454: reverseproxy Host 기본값 변경](https://github.com/caddyserver/caddy/pull/7454)
- [이슈 #7565: v2.11.2에서 Host 변화로 redirect가 IP로 가는 사례](https://github.com/caddyserver/caddy/issues/7565)

[^1]: <https://github.com/caddyserver/caddy/releases?after=v1.0.3>
[^2]: <https://github.com/caddyserver/caddy/releases/tag/v2.11.9>
[^3]: <https://github.com/caddyserver/caddy/pull/7454>
[^4]: <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy>
[^5]: <https://github.com/caddyserver/caddy/issues/7565>
[^6]: <https://github.com/caddyserver/caddy/issues/7584>
[^7]: <https://caddyserver.com/docs/caddyfile/options>
[^8]: <https://github.com/caddyserver/caddy/releases/tag/v2.11.6>
[^9]: <https://github.com/caddyserver/caddy/releases/tag/v2.11.7>
[^10]: <https://github.com/caddyserver/caddy/releases/tag/v2.11.8>
[^11]: <https://caddyserver.com/docs/logging>
[^12]: <https://caddyserver.com/docs/metrics>
[^13]: <https://caddyserver.com/docs/caddyfile/directives/metrics>
[^14]: <https://caddyserver.com/docs/api>
[^15]: <https://caddyserver.com/docs/getting-started>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
