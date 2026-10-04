---
title: "Apache httpd 2.4.69: HTTP/2 패치가 프록시 체인에 미치는 영향"
description: "2.4.69의 HTTP/2·proxy 관련 CVE를 프록시 체인 관점에서 해석하고, 롤아웃 전후 검증 체크리스트를 정리합니다."
date: 2026-10-04 13:51:42 +0900
categories: ["News", "Security"]
tags: ["apache-httpd", "http2", "reverse-proxy", "forward-proxy", "cve", "patch-management"]
render_with_liquid: false
---

## 2026-10-01에 바뀐 것은 httpd가 아니라 프록시 체인의 보안 계약입니다

Apache HTTP Server 2.4.69는 2026-10-01에 릴리스되었습니다. 릴리스 공지에서도 이 릴리스를 **security, feature and bug fix release**로 못 박고 있습니다. 단순히 서버 바이너리 하나를 교체하는 이벤트로 볼 수도 있지만, reverse proxy/forward proxy/게이트웨이 역할로 httpd를 쓰는 조직에서는 해석이 달라집니다. [Apache HTTP Server 2.4.69 발표](https://downloads.apache.org/httpd/Announcement2.4.html) 문구 그대로, 이제 2.4.x에서 “권장되는 최신 GA”가 2.4.69로 바뀌었고, 동시에 2.4.69에서 고쳐진 취약점들이 프록시의 양방향(클라이언트→프록시, 프록시→백엔드) 경계에 걸쳐 있습니다.

프록시는 요청을 전달하는 것처럼 보이지만, 실제로는 다음을 동시에 수행합니다.

- 프로토콜 변환(HTTP/2 ↔ HTTP/1.1, 혹은 HTTP/2 ↔ HTTP/2)
- 헤더 정규화 및 hop-by-hop 헤더 처리
- 인증 상태/세션 쿠키의 수명 관리(명시적으로든, 우연히든)
- 백엔드 응답을 파싱/변환(HTML rewrite, charset conversion 같은 필터 체인)

따라서 취약점 패치가 들어오면 “서버가 안전해졌다”로 끝나지 않고, 프록시 체인 전체에서 통신/헤더/상태 관리에 대한 암묵적 계약이 바뀝니다. 이번 2.4.69는 그 성격이 강합니다. 이유는 http/2(mod_http2) 관련 이슈가 2026년 내내 이어지고 있고, 2.4.69 자체에도 HTTP/2 메모리 안전 계열 취약점(CVE-2026-57941)이 포함돼 있기 때문입니다. [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69)과 [Apache httpd 2.4 취약점 목록](https://httpd.apache.org/security/vulnerabilities_24)만 놓고 봐도, 프록시·게이트웨이 운영자가 신경 써야 하는 표면이 명확합니다.

내 경우도 httpd를 “origin 웹서버”로 쓰는 구간보다, 사내 서비스 앞단에서 reverse proxy로 쓰는 구간에서 장애/보안 사고 비용이 더 큽니다. 프록시 한 대가 죽으면 여러 서비스가 같이 죽고, 프록시가 잘못 전달한 헤더 하나가 인증 우회를 만들기도 합니다.

## 2.4.69에 포함된 취약점 중 프록시 운영과 직접 부딪히는 것들

2.4.69에 고쳐진 보안 이슈는 폭이 넓지만, 프록시 체인 관점에서 특히 하중을 크게 받는 부류가 몇 가지 있습니다. 아래 항목들은 “외부 클라이언트가 악의적일 때”뿐 아니라 “백엔드가 신뢰할 수 없을 때(또는 버그/오염된 데이터가 있을 때)”도 문제가 됩니다.

### 1) mod_http2 메모리 안전 이슈: CVE-2026-57941

2.4.69에는 `mod_http2`의 use-after-free / wild write 성격의 취약점(CVE-2026-57941)이 포함돼 있습니다. 영향 버전은 2.4.0~2.4.68로 표기되어 있고, 2.4.69에서 수정된 것으로 정리돼 있습니다. [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69)에도 그대로 올라와 있고, [oss-sec 공지](https://seclists.org/oss-sec/2026/q4/18)에는 2026-10-01에 2.4.x 브랜치에서 수정(r1938665)되고 같은 날 2.4.69가 릴리스되었다는 타임라인이 같이 붙어 있습니다. 또한 [Apache httpd 2.4 취약점 목록](https://httpd.apache.org/security/vulnerabilities_24)에서도 2.4.69에 포함된 항목으로 확인됩니다.

이게 프록시 체인에서 왜 더 위험하냐면, reverse proxy는 일반적으로 다음 특성을 갖기 때문입니다.

- 하나의 클라이언트 커넥션(특히 HTTP/2) 위에 동시 스트림을 다수 얹습니다.
- 스트림 cancel/reset이 정상 동작으로도 자주 발생합니다(브라우저의 speculative fetch, 모바일 네트워크 변동, gRPC client cancel 등).
- 프록시가 upstream으로 재사용 커넥션을 유지하면서 내부 상태를 공유하기 쉽습니다.

즉, “드문 에러 경로”가 아니라, 정상 트래픽에서도 자주 밟히는 경로에서 상태 정합성이 흔들리면, 공격 난이도가 내려갑니다.

### 2) 백엔드 응답을 공격 입력으로 취급해야 하는 이슈들

프록시는 외부 입력만 받는 게 아니라, 백엔드 응답을 파싱해서 다시 클라이언트에 내보내는 중간자입니다. 2.4.69에는 그 성격의 취약점들이 여럿 들어 있습니다.

- `mod_xml2enc` NULL pointer dereference (CVE-2026-63686): “프록시된 응답의 charset 변환이 부분 성공 후 실패”하는 케이스로 DoS가 가능하다고 설명돼 있습니다. 즉 백엔드가 악성/오류 응답을 주면 프록시가 죽을 수 있습니다. [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69), [취약점 목록](https://httpd.apache.org/security/vulnerabilities_24)에서 확인됩니다.
- `mod_proxy_html` crash in dump_content (CVE-2026-56449): crafted HTTP response bodies가 입력입니다. reverse proxy에서 HTML rewrite를 켜는 조직은 대상이 됩니다. [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69), [취약점 목록](https://httpd.apache.org/security/vulnerabilities_24)
- `mod_proxy_uwsgi` Transfer-Encoding response smuggling (CVE-2026-63718): uwsgi 응답의 `Transfer-Encoding` 해석 불일치로 response smuggling을 언급합니다. 프록시 체인에서 “어느 홉이 어떤 메시지 경계를 믿는가”를 흔드는 계열이라, 보안/관측/캐시까지 같이 흔들립니다. [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69)

여기서 중요한 포인트는 “백엔드는 내부망이라 안전” 같은 전제가 무너지는 순간입니다. 백엔드가 제3자 컨트롤을 받는 SaaS거나, 멀티테넌트 환경에서 테넌트가 업로드한 콘텐츠를 다시 프록시가 변환해주는 구조면 더 빠르게 현실화됩니다.

### 3) forward proxy에 직접 걸리는 이슈: mod_proxy_ftp PASV

CVE-2026-63045는 `mod_proxy_ftp`에서 PASV 응답의 주소 처리 검증이 부적절해서, forward proxy 구성에서 “신뢰할 수 없는 FTP 서버”가 프록시로 하여금 임의의 3rd-party 호스트로 데이터 커넥션을 열게 만들 수 있다고 되어 있습니다. 프록시가 내부망에서 outbound를 허용하는 위치에 있으면, 이건 SSRF의 한 형태로 악용될 여지가 큽니다. [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69), [취약점 목록](https://httpd.apache.org/security/vulnerabilities_24)

FTP 자체를 안 쓰면 영향이 없지만, 문제는 “모듈이 로드되어 있고 ProxyRequests on인 환경”이 생각보다 남아 있다는 점입니다. 운영 중인 forward proxy는 기능을 빼기 어렵고, 일단 남아 있으면 공격면이 됩니다.

### 4) 내부 redirect에서 세션 쿠키가 흘러갈 수 있는 이슈: mod_session_cookie

CVE-2026-47360은 `mod_session_cookie`와 내부 redirect 조합에서 `SessionCookieRemove` 정책이 redirect 사이에서 바뀌는 경우, session cookie가 여전히 백엔드로 전달될 수 있다고 설명합니다. 프록시 체인 입장에서 이건 “쿠키 제거 정책이 프록시 내부에서 원자적이지 않다”는 의미입니다. 클라이언트로부터 받은 쿠키가 백엔드로 넘어가면, 백엔드의 로그/에러 리포트/추적 시스템까지 같이 노출 표면이 넓어집니다. [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69)

세션/쿠키는 내가 예전에 MCP를 Streamable HTTP로 붙이면서 보안 경계를 다시 잡았던 이유와도 결이 같습니다. 프록시가 중간에서 헤더/세션을 다루는 순간, 그 계층이 사실상 security boundary가 됩니다. 이 맥락은 예전 글인 [Claude용 MCP 서버를 에이전트 확장 서버로 구현할 때의 보안 포인트](https://daewooki.github.io/posts/2026-4-claude-mcp-streamable-http-1/)에서 다룬 “중계 계층이 인증/세션의 실질적 경계가 되는 순간”과 닿아 있습니다.

## http/2 취약점(CVE-2026-23918 포함)은 왜 계속 프록시 이슈로 돌아오는가

이번 주에 2.4.69를 당장 굴려야 한다는 압박은 “2.4.69에서 새로 발견된” 이슈 때문만은 아닙니다. 2026년 한 해 동안 httpd의 HTTP/2 계층(mod_http2)이 계속 흔들렸고, 그 연장선에서 2.4.69도 “HTTP/2를 켠 프록시” 관점에서는 한 덩어리로 봐야 합니다.

### 2026-05-04: CVE-2026-23918 (early reset에서 double free, possible RCE)

CVE-2026-23918은 Apache가 영향 버전을 2.4.66으로 특정했고, “early reset에서 double free 및 possible RCE”로 명시했습니다. 그리고 2.4.67(2026-05-04)에서 수정됐다고 정리되어 있습니다. [Apache httpd 2.4 취약점 목록](https://httpd.apache.org/security/vulnerabilities_24) 기준으로 Reported 2025-12-10, fixed r1930444 2025-12-11, Update 2.4.67 released 2026-05-04 흐름입니다.

여기서 early reset은 프록시에서 흔한 시나리오입니다. 예를 들면 클라이언트가 요청을 보냈지만 페이지 전환/탭 종료/네트워크 끊김으로 스트림을 CANCEL(RST_STREAM)하는 것은 정상 동작입니다. 취약점이 바로 그 정상 경로에서 cleanup이 두 번 일어나는 형태라면, reverse proxy는 공격자가 가장 쉽게 도달하는 표면이 됩니다.

### 2026-06-08: 2.4.68에서도 mod_http2 DoS/메모리 이슈가 이어짐

2.4.68(2026-06-08)에서도 `mod_http2` 관련 DoS/메모리 이슈가 CVE로 올라옵니다. 예를 들어 “file handles exhausted일 때 memory corruption” (CVE-2026-48913), “excessive size allocation DoS” (CVE-2026-49975)가 2.4.68에서 수정된 것으로 나옵니다. [취약점 목록](https://httpd.apache.org/security/vulnerabilities_24)에서 2.4.68 릴리스 날짜와 함께 확인됩니다.

이건 운영 관점에서는 단서가 하나 있습니다. HTTP/2는 워커/버퍼/헤더 압축(HPACK) 등으로 인해, 전통적인 HTTP/1.1보다 자원 모델이 복잡합니다. Apache도 `mod_http2` 문서에서 HTTP/2 활성화 시 워커 스레드가 추가로 생기고 리소스 소비를 고려해야 한다고 명시합니다. [mod_http2 문서](https://httpd.apache.org/docs/2.4/mod/mod_http2.html)

### 2026-10-01: 2.4.69의 CVE-2026-57941은 “그 다음 파도”

CVE-2026-57941이 “shared session->bbtmp re-entrancy” 같은 내부 상태 공유/재진입성(re-entrancy)을 언급하는 형태로 나온 건, 프록시에서 흔한 연결 재사용/세션 공유와 결이 맞습니다. [oss-sec 공지](https://seclists.org/oss-sec/2026/q4/18)에도 2.4.0~2.4.68 전체를 영향 범위로 잡았고 2026-10-01에 수정/릴리스가 같이 표기되어 있습니다.

결론적으로 2026년의 HTTP/2 이슈들을 보면, 특정 CVE 하나만 처리하고 끝낼 분위기가 아니었습니다. HTTP/2가 “새 기능”이 아니라, 프록시의 기본 전송 계층이 된 이후에는 reset/cancel/재사용/동시성 같은 정상 흐름의 조합이 곧 공격면이 됩니다. [HTTP/2 guide](https://httpd.apache.org/docs/2.4/howto/http2.html)가 정리하는 것처럼 HTTP/2는 binary 프로토콜이고 스트림 개념 위에서 다중화를 하며, h2/h2c 같은 협상 방식도 다릅니다. 이 복잡도가 구현 취약점으로 연결되기 쉽습니다.

## 프록시 체인에서 패치의 의미: “누가 누구를 신뢰하는가”가 바뀝니다

2.4.69의 보안 이슈들은 방향이 제각각입니다. 그럼에도 프록시 관점에서 공통점은 하나입니다.

- 외부 클라이언트는 프록시의 HTTP/2 상태 머신을 흔들 수 있습니다(`mod_http2` 계열)
- 내부 백엔드는 프록시의 파서/필터를 흔들 수 있습니다(`mod_xml2enc`, `mod_proxy_html`, `mod_proxy_uwsgi` 계열)

프록시는 “중간자”이기 때문에, 양쪽을 동시에 방어해야 합니다. 이게 보안 계약의 핵심입니다.

또 하나 현실적인 포인트는, 많은 조직이 httpd를 단독으로 두지 않고 체인으로 둡니다.

- CDN/Edge LB(HTTP/2) → L7 gateway(HTTP/1.1) → 내부 서비스
- 모바일 앱 → forward proxy → 인터넷
- 브라우저 → reverse proxy(httpd) → upstream(rewrite/SSO) → 앱

이때 어떤 CVE는 프록시가 “서버로서 처리하는” 입력을 타격하고, 어떤 CVE는 프록시가 “클라이언트로서 받아들이는” 입력을 타격합니다. 2.4.69는 후자(백엔드 응답 입력) 비중이 눈에 띄기 때문에, 패치 후 검증에서도 반드시 “백엔드를 악성으로 가정한 테스트”를 포함해야 합니다.

그리고 httpd만 보는 것도 부족합니다. `mod_http2`와 `mod_proxy_http2`는 libnghttp2를 사용한다고 문서에 명시돼 있습니다. [mod_http2 문서](https://httpd.apache.org/docs/2.4/mod/mod_http2.html), [mod_proxy_http2 문서](https://httpd.apache.org/docs/current/mod/mod_proxy_http2.html) 패치 후에 라이브러리 버전까지 같이 바뀌는 배포판(특히 distro 패키지 업데이트)이라면, 체인 전체의 동작이 미묘하게 변할 수 있습니다.

## 패치 적용 전후에 검증해야 할 체크리스트: 트래픽, 헤더, HTTP/2 reset

아래 체크리스트는 “CVE가 재현되는지”를 직접 증명하려는 목적보다, 프록시 체인의 계약이 바뀔 때 깨지기 쉬운 지점을 빠짐없이 밟아보는 목적입니다. 실제 롤아웃에서 필요한 건 취약점 PoC보다, 안전하게 트래픽을 흘릴 수 있다는 확신입니다.

### 1) HTTP/2 커넥션/스트림 생명주기: reset이 정상인 환경을 가정

검증 포인트는 간단합니다. RST_STREAM, GOAWAY, 커넥션 조기 종료가 섞여도 프록시가 죽지 않고, 백엔드 연결 풀도 깨지지 않아야 합니다.

- 단일 TCP 커넥션에 다중 스트림 동시 발사 후, 일부 스트림을 클라이언트가 즉시 CANCEL(RST_STREAM)
- 요청 헤더만 보낸 뒤 reset
- 요청 바디를 일부 보내다 reset(업로드 중 취소)
- 응답 헤더 수신 직후 reset(브라우저가 리소스를 더 이상 원치 않는 상황)
- 응답 바디 스트리밍 중 reset(동영상 플레이어/모바일 네트워크)
- keepalive 커넥션에서 N번째 요청만 reset(상태 누수 탐지)

관측해야 하는 지표는 다음입니다.

- httpd child/worker의 비정상 종료(core dump, SIGSEGV)
- 에러 로그에 반복되는 http2 session/stream 오류
- 같은 클라이언트 IP/JA3/ALPN에서 비정상적으로 많은 reset 비율

HTTP/2 튜닝/제한 값도 같이 확인합니다. `mod_http2`는 `H2MaxSessionStreams`, `H2MaxWorkerIdleSeconds`, `H2StreamTimeout` 같은 다수의 directive를 제공하고, HTTP/2가 워커 스레드를 추가로 사용한다고 명시합니다. [mod_http2 문서](https://httpd.apache.org/docs/2.4/mod/mod_http2.html)

### 2) 프런트엔드(h2) ↔ 백엔드(http/1.1 or h2) 변환 구간: 헤더/경계의 불일치 제거

프록시는 다음을 동시에 만족해야 합니다.

- 클라이언트가 보낸 “애매한 헤더 조합”이 백엔드에 유리한 해석으로 전달되지 않는다.
- 백엔드가 보낸 “애매한 응답 경계”가 클라이언트에 유리한(=스머글링 가능한) 형태로 전달되지 않는다.

점검 항목은 트래픽 캡처/로그 비교까지 포함해서 체크합니다.

- `Transfer-Encoding` / `Content-Length` 동시 존재 시 처리(요청/응답 각각)
- hop-by-hop 헤더 정리: `Connection`, `Upgrade`, `TE`, `Proxy-Connection`, `Keep-Alive` 등
- `Host`와 HTTP/2 `:authority` 매핑 일관성(리라이트/리다이렉트 포함)
- `X-Forwarded-For`, `X-Forwarded-Proto`, `Forwarded`의 중복/체인 규칙
- `Cookie`/`Set-Cookie`가 internal redirect/rewrite로 인해 의도치 않게 백엔드로 전달되는지(CVE-2026-47360 유형)

특히 httpd에서 백엔드까지 HTTP/2를 유지하려고 `mod_proxy_http2`를 쓰는 경우, 문서가 “backend needs to support HTTP/2이고 HTTP/1.1로 downgrade하지 않는다”고 못 박습니다. 또한 이 모듈은 experimental로 경고합니다. [mod_proxy_http2 문서](https://httpd.apache.org/docs/current/mod/mod_proxy_http2.html) 패치가 들어올 때 동작이 바뀌어도 이상하지 않은 구간이라는 뜻이고, 그래서 롤아웃 전에 체계적으로 회귀 테스트를 해야 합니다.

### 3) 백엔드를 악성 입력으로 보는 테스트: charset/HTML rewrite/uWSGI

2.4.69에 포함된 프록시 관련 CVE들의 상당수는 “신뢰할 수 없는 백엔드”를 전제로 합니다.

- `mod_xml2enc`는 “프록시된 응답의 charset 변환 실패”로 크래시가 가능하다고 서술돼 있습니다. (CVE-2026-63686) [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69)
- `mod_proxy_html`은 crafted response body로 크래시가 가능하다고 서술돼 있습니다. (CVE-2026-56449) [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69)
- `mod_proxy_uwsgi`는 `Transfer-Encoding`를 매개로 response smuggling을 언급합니다. (CVE-2026-63718) [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69)

따라서 스테이징에서는 최소한 아래를 흉내 냅니다.

- 백엔드가 잘못된 `Content-Type; charset=...`를 주고 바디는 깨진 바이트를 포함
- 백엔드가 예상보다 큰/이상한 HTML을 주고 rewrite 필터가 동작
- uWSGI가 프록시를 통과하는 구성이라면, 비정상 `Transfer-Encoding` 조합을 포함한 응답을 흉내내서 프록시가 어떤 경계를 선택하는지 확인

여기서 “백엔드는 우리 서비스니까 괜찮다”는 주장은, 현실에서 잘 안 맞습니다. 프록시는 서비스 수가 늘어날수록 비정상 응답을 하나쯤은 반드시 만나게 됩니다. 공격은 그 비정상 케이스를 인위적으로 만들 뿐입니다.

### 4) forward proxy 운영자 체크: FTP PASV와 오픈 프록시 방지

forward proxy는 늘 두 겹을 확인합니다.

- ProxyRequests/ACL이 오픈 프록시가 아니게 막혀 있는지
- 프로토콜별 모듈(`mod_proxy_ftp` 등)이 진짜로 필요한지

CVE-2026-63045는 forward proxy 구성에서 “신뢰할 수 없는 FTP 서버”가 3rd-party로 데이터 커넥션을 열게 만들 수 있다고 명시합니다. (2.4.69에서 수정) [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69)

forward proxy는 보통 내부망에서 outbound가 열려 있습니다. 그래서 이 부류의 취약점은 외부 노출 여부와 별개로 내부망 pivot의 발판이 됩니다.

### 5) 롤아웃/관측 체크: 로그에 무엇을 남길지 사전에 결정

패치 전후에 비교하려면 관측 포인트가 있어야 합니다.

- HTTP/2 관련 로그 레벨을 임시로 올려 문제 구간을 잡는 전략
- 프록시 백엔드 연결에 대한 로그(request notes) 활용

`mod_proxy_http2` 문서에는 `proxy-status`(백엔드에서 받은 HTTP/2 status), `proxy-source-port` 같은 request note를 로깅에 쓸 수 있다고 적혀 있습니다. [mod_proxy_http2 문서의 Request notes](https://httpd.apache.org/docs/current/mod/mod_proxy_http2.html)

패치 후 문제가 생겼을 때, “클라이언트-프록시 구간 문제인지, 프록시-백엔드 구간 문제인지”를 빠르게 분리하지 못하면 롤백 외에 선택지가 사라집니다.

## 2.4.68 ↔ 2.4.69 비교 검증을 위한 재현 환경(Docker)

패치를 무조건 빨리 하는 것과, 안전하게 롤아웃하는 것은 충돌합니다. 충돌을 줄이는 방법은 “같은 트래픽을 2.4.68과 2.4.69에 동일하게 때려보는” 것입니다.

여기서는 TLS를 생략하고 h2c(prior knowledge)로 단순화합니다. 실제 운영은 h2(=TLS+ALPN)가 대부분이지만, reset/동시성/상태 관리의 본질은 h2c에서도 충분히 흔들 수 있습니다. httpd가 h2c를 여전히 지원한다고 문서에서 명시합니다. [HTTP/2 guide](https://httpd.apache.org/docs/2.4/howto/http2.html)

또한 공식 Docker 이미지에 `httpd:2.4.69` 태그가 올라와 있는 것도 확인할 수 있습니다. [Docker Hub의 httpd Official Image 설명](https://hub.docker.com/_/httpd?tab=description)

### 디렉터리 구조

```text
httpd-2469-proxy-lab/
  docker-compose.yml
  apache/
    httpd.conf
  backend/
    app.py
    Dockerfile
  client/
    requirements.txt
    h2_reset_stress.py
```

### docker-compose.yml

```yaml
services:
  apache_2468:
    image: httpd:2.4.68
    ports:
      - "18080:8080"
    volumes:
      - ./apache/httpd.conf:/usr/local/apache2/conf/httpd.conf:ro
    depends_on:
      - backend

  apache_2469:
    image: httpd:2.4.69
    ports:
      - "28080:8080"
    volumes:
      - ./apache/httpd.conf:/usr/local/apache2/conf/httpd.conf:ro
    depends_on:
      - backend

  backend:
    build: ./backend
    ports:
      - "19000:9000"
```

### apache/httpd.conf (reverse proxy + h2c)

```apacheconf
ServerRoot "/usr/local/apache2"
Listen 8080
ServerName localhost
PidFile /tmp/httpd.pid

LoadModule mpm_event_module modules/mod_mpm_event.so
LoadModule unixd_module modules/mod_unixd.so
LoadModule authn_core_module modules/mod_authn_core.so
LoadModule authz_core_module modules/mod_authz_core.so
LoadModule headers_module modules/mod_headers.so
LoadModule log_config_module modules/mod_log_config.so
LoadModule proxy_module modules/mod_proxy.so
LoadModule proxy_http_module modules/mod_proxy_http.so
LoadModule http2_module modules/mod_http2.so

# h2c 실험을 위한 설정 (TLS 생략)
Protocols h2c http/1.1
H2Direct On
H2MaxSessionStreams 100
H2StreamTimeout 10

# reverse proxy
ProxyRequests Off
ProxyPreserveHost On

# hop-by-hop 헤더 정리(최소한의 안전장치)
RequestHeader unset Connection
RequestHeader unset Upgrade

ProxyPass        "/"  "http://backend:9000/"
ProxyPassReverse "/"  "http://backend:9000/"

LogFormat "%h %l %u %t \"%r\" %>s %b" common
CustomLog /proc/self/fd/1 common
ErrorLog /proc/self/fd/2
LogLevel warn http2:info proxy:info
```

### backend/Dockerfile + app.py

backend는 “정상 응답 + 일부러 깨진 charset 응답 + 느린 응답”을 섞어줍니다.

backend/Dockerfile:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY app.py /app/app.py
EXPOSE 9000
CMD ["python", "/app/app.py"]
```

backend/app.py:

```python
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return

        if self.path.startswith("/slow"):
            time.sleep(2)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"slow-ok")
            return

        if self.path.startswith("/bad-charset"):
            # 일부러 charset은 선언하지만, 바디는 그 charset으로는 깨지는 바이트를 포함
            self.send_response(200)
            self.send_header("Content-Type", "text/xml; charset=EUC-KR")
            self.end_headers()
            self.wfile.write(b"<x>\xff\xfe\xff\xfe</x>")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"hello")

    def log_message(self, fmt, *args):
        return

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
```

### 구동 및 기본 확인

```bash
docker compose up -d --build

# 2.4.68/2.4.69가 각각 떠 있는지 확인
curl -sS http://localhost:18080/healthz
curl -sS http://localhost:28080/healthz
```

예상 출력:

```text
ok
ok
```

### HTTP/2(h2c) 스트림 reset 스트레스 클라이언트

Python `h2` 라이브러리로 h2c 커넥션을 열고, 여러 스트림을 동시에 만들었다가 일부를 RST_STREAM(CANCEL)로 조기 종료합니다.

client/requirements.txt:

```text
h2==4.1.0
hyperframe==6.0.1
hpack==4.0.0
```

client/h2_reset_stress.py:

```python
import socket
import time
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import ResponseReceived, DataReceived, StreamEnded

HOST = "localhost"
PORT = 18080  # 28080으로 바꿔 2.4.69 테스트

def main():
    s = socket.create_connection((HOST, PORT))
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    config = H2Configuration(client_side=True, header_encoding="utf-8")
    conn = H2Connection(config=config)

    conn.initiate_connection()
    s.sendall(conn.data_to_send())

    stream_ids = []

    # 1) 여러 스트림을 연다 (일부는 /slow로 보내서 서버가 처리 중인 상태를 만든다)
    for i in range(1, 101):
        path = "/slow" if i % 3 == 0 else "/healthz"
        sid = conn.get_next_available_stream_id()
        stream_ids.append((sid, path))
        conn.send_headers(
            sid,
            [
                (":method", "GET"),
                (":scheme", "http"),
                (":authority", f"{HOST}:{PORT}"),
                (":path", path),
            ],
            end_stream=True,
        )

        # 매 10개마다 flush
        if i % 10 == 0:
            s.sendall(conn.data_to_send())

    s.sendall(conn.data_to_send())

    # 2) 일부 스트림은 응답을 기다리지 않고 조기 cancel
    #    (end_stream=True로 요청은 끝났지만, 클라이언트 관점에서 더는 필요 없다고 가정)
    for sid, path in stream_ids:
        if path == "/slow":
            conn.reset_stream(sid, error_code=0x8)  # CANCEL

    s.sendall(conn.data_to_send())

    # 3) 남은 이벤트를 조금 읽고 종료
    start = time.time()
    ended = set()

    while time.time() - start < 5:
        data = s.recv(65535)
        if not data:
            break
        events = conn.receive_data(data)
        for ev in events:
            if isinstance(ev, ResponseReceived):
                pass
            elif isinstance(ev, DataReceived):
                conn.acknowledge_received_data(ev.flow_controlled_length, ev.stream_id)
            elif isinstance(ev, StreamEnded):
                ended.add(ev.stream_id)
        s.sendall(conn.data_to_send())

    s.close()
    print(f"done; streams_ended={len(ended)}")

if __name__ == "__main__":
    main()
```

실행:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r client/requirements.txt

# 2.4.68 대상으로
python client/h2_reset_stress.py

# 2.4.69 대상으로는 PORT를 28080으로 바꾸거나 환경변수로 분기해 반복 실행
```

예상 출력(정확한 숫자는 환경에 따라 달라질 수 있음):

```text
done; streams_ended=...
```

이 테스트의 목적은 CVE 재현이 아니라, reset/cancel이 많은 환경에서도 프로세스가 죽지 않는지, 로그가 폭주하지 않는지, 다음 요청이 정상 처리되는지를 보는 것입니다.

### 패치 전후 비교에서 꼭 같이 볼 것

- 테스트 수행 중 `docker compose ps`에서 컨테이너가 재시작되지 않는지
- 에러 로그에 segfault, child exit, APR allocator 오류 같은 치명 로그가 남지 않는지
- 테스트 직후에도 `/healthz`가 즉시 정상 응답하는지

```bash
curl -sS http://localhost:18080/healthz && echo
curl -sS http://localhost:28080/healthz && echo

docker logs --tail 200 apache_2468
docker logs --tail 200 apache_2469
```

## 반론과 회의론: “HTTP/2를 안 쓰면 상관없다”는 말이 자주 틀리는 이유

회의론의 핵심은 보통 세 가지입니다.

1) 우리는 HTTP/2를 edge(CDN/ALB)에서만 쓴다. 내부 httpd는 HTTP/1.1만 받는다.
2) distro 패키지는 backport로 이미 패치돼 있다.
3) 보안 패치가 기능 회귀(regression)를 만든다.

첫 번째는 절반만 맞습니다. 외부에서 HTTP/2를 끊어도, reverse proxy는 여전히 백엔드 응답(=내부 입력)을 파싱합니다. 2.4.69의 CVE 중에는 `mod_xml2enc`, `mod_proxy_html`, `mod_proxy_uwsgi`처럼 “백엔드가 주는 데이터”를 입력으로 하는 것들이 포함돼 있습니다. [2.4.69 변경 요약](https://downloads.apache.org/httpd/CHANGES_2.4.69)

두 번째는 맞을 수도 있고, 틀릴 수도 있습니다. 버전 문자열만으로 판단하면 안 됩니다. 예를 들어 Ubuntu는 보안 공지에서 특정 CVE에 대한 패치 적용을 배포판 패키지 업데이트로 제공합니다. [Ubuntu security notice(USN-8239-1)](https://ubuntu.com/security/notices/USN-8239-1) 같은 자료를 기준으로 “내가 설치한 패키지 빌드가 CVE를 포함하는지”를 확인해야 합니다.

세 번째는 현실입니다. 특히 `mod_proxy_http2`는 문서에서 experimental로 경고하고, release-to-release 변경 가능성을 노골적으로 말합니다. [mod_proxy_http2 문서](https://httpd.apache.org/docs/current/mod/mod_proxy_http2.html) 그래서 더더욱 “패치 적용 전후 검증 체크리스트”가 필요합니다.

## 앞으로 지켜볼 것: 2.4.70보다 먼저 봐야 하는 건 트래픽 패턴입니다

2.4.69 이후에도 관찰해야 하는 것은 다음입니다.

- HTTP/2 reset/cancel 비율이 특정 구간에서 갑자기 튀는지(공격 징후일 수도, 클라이언트/네트워크 변화일 수도 있음)
- 특정 백엔드에서만 프록시 레이어가 불안정해지는지(응답 파싱/변환 취약점 계열의 신호)
- “HTTP/2는 켰지만 제한값은 기본”인 서비스가 과연 안전한지(`H2MaxSessionStreams` 같은 기본값이 현재 트래픽에 맞는지)

httpd 문서가 말하는 것처럼 HTTP/2는 서버 자원 모델을 바꿉니다. [mod_http2 문서](https://httpd.apache.org/docs/2.4/mod/mod_http2.html) 취약점 패치를 해도, 잘못된 제한값/관측 부재가 있으면 DoS는 다른 방식으로 다시 들어옵니다.

## 지금 해야 하는 일: 패치 주간에는 “업데이트”가 아니라 “계약 갱신”으로 롤아웃합니다

2026-10-01에 2.4.69가 릴리스됐고, 같은 날짜에 2.4.x 취약점 목록도 2.4.69 fixed 항목들로 갱신되어 있습니다. [2.4.69 발표](https://downloads.apache.org/httpd/Announcement2.4.html), [2.4 취약점 목록](https://httpd.apache.org/security/vulnerabilities_24)

그래서 이번 주(2026-10-04 KST가 포함된 주간)의 작업은 패치 적용 자체보다, 패치가 바꾼 프록시 체인의 계약을 검증하는 데 시간이 더 들어가야 맞습니다.

- HTTP/2 reset/cancel이 섞인 정상 트래픽에서 안정성 유지
- 백엔드 응답을 악성 입력으로 두고도 프록시가 버티는지 확인
- 헤더/쿠키 정책이 내부 redirect/rewrite를 거쳐도 일관되는지 확인
- forward proxy 운영자는 FTP 같은 “남아 있는 기능”이 실제로 공격면인지 재점검

업데이트를 했다는 사실보다, 업데이트 이후에도 “프록시가 무엇을 신뢰하고 무엇을 버리는지”를 증명하는 쪽이 보안 운영의 본질입니다.

## 참고 자료

- [Apache HTTP Server 2.4.69 발표](https://downloads.apache.org/httpd/Announcement2.4.html)
- [Apache httpd 2.4 취약점 목록](https://httpd.apache.org/security/vulnerabilities_24)
- [2.4.69 변경 요약(CHANGES_2.4.69)](https://downloads.apache.org/httpd/CHANGES_2.4.69)
- [oss-sec: CVE-2026-57941 공지](https://seclists.org/oss-sec/2026/q4/18)
- [mod_http2 문서](https://httpd.apache.org/docs/2.4/mod/mod_http2.html)
- [HTTP/2 guide(Apache httpd)](https://httpd.apache.org/docs/2.4/howto/http2.html)
- [mod_proxy_http2 문서](https://httpd.apache.org/docs/current/mod/mod_proxy_http2.html)
- [Docker Hub의 httpd Official Image 설명(2.4.69 태그 포함)](https://hub.docker.com/_/httpd?tab=description)
- [Ubuntu security notice(USN-8239-1)](https://ubuntu.com/security/notices/USN-8239-1)
- [Claude용 MCP 서버를 “에이전트 확장 서버”로 제대로 구현하는 법: Streamable HTTP, 버전 호환, 그리고 보안까지](https://daewooki.github.io/posts/2026-4-claude-mcp-streamable-http-1/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
