---
title: "Tomcat 10.1 HTTP/2 mix-up 취약점 대응 런북"
description: "Tomcat HTTP/2+async 조합에서 사용자 간 응답 섞임이 남기는 운영·감사 리스크와 프록시 완화 런북."
date: 2026-10-21 10:01:24 +0900
categories: ["News", "Security"]
tags: ["apache-tomcat", "http2", "async-servlet", "response-mixup", "reverse-proxy", "runbook"]
render_with_liquid: false
---

## 2026-10-20 공개된 Tomcat 10.1.x 이슈 묶음과 버전 범위

2026-10-20에 Tomcat 보안 페이지와 oss-security를 통해 Tomcat 9/10/11 여러 이슈가 한꺼번에 공개됐습니다. 그중 운영 리스크를 가장 크게 재평가해야 하는 건 **HTTP/2 request/response mix-up** 계열입니다.

Tomcat 10.1.x 기준으로 이번에 같이 공개된 항목을 정리하면 아래처럼 묶입니다.

- **CVE-2026-101356 (Severity: important)**: HTTP/2에서 async servlet 처리 중 오류가 난 뒤, 내부 객체 재사용(object recycling) 문제로 사용자 간 request/response가 섞일 수 있음. Tomcat 10.1.55~10.1.60 영향, 10.1.61에서 수정. 공개일은 2026-10-20으로 명시돼 있습니다.[^1]
- CVE-2026-88041 (Severity: low): HTTP/2 trailer header가 이전 요청에서 다음 요청으로 새어 들어가는 cross-contamination. Tomcat 10.1.27~10.1.60 영향, 10.1.61에서 수정.[^1]
- CVE-2026-74049 (Severity: low): Jasper JSTL의 `<c:redirect>` tag plugin이 redirect 후 page abort(SKIP_PAGE)를 누락해서 redirect 후에도 페이지 나머지 처리가 계속될 수 있음. Tomcat 10.1.0-M1~10.1.60 영향, 10.1.61에서 수정(관련 커밋 메일이 남아 있음).[^1]
- (같은 날 공개됐지만 이 글의 중심은 아닌) CVE-2026-101296 (Severity: important): JNDIRealm을 non-GSSAPI SASL로 구성했을 때 인증이 fails open으로 흐를 수 있는 이슈. 10.1.0-M1~10.1.60 영향, 10.1.61에서 수정.[^1]

이 글의 초점은 CVE-2026-101356이 만드는 실패 모드가 운영/감사 관점에서 어떤 파장을 가지는지, 그리고 패치가 바로 어렵다는 전제를 놓고 프록시/WAF 계층에서 런북을 어떻게 구성하는지가 됩니다.

버전 타임라인도 같이 봐야 합니다.

- Tomcat 10.1.61은 changelog 기준으로 2026-10-06 날짜가 붙어 있습니다.[^2]
- 하지만 보안 페이지의 섹션 헤더는 “2026-10-12 Fixed in Apache Tomcat 10.1.61”로 정리되어 있고, 공개일은 2026-10-20으로 명시돼 있습니다.[^1]

운영에서는 공개일(2026-10-20) 기준으로 외부 스캐너/리포트/감사가 움직이기 시작하고, 실제 패치 가능성은 릴리스 날짜(대개 2026-10-06 전후)와 배포 파이프라인 속도가 결정합니다. 이 간극 때문에 “이미 고쳐진 버전이 있으니 천천히”가 아니라 “공개됐으니 우선순위가 바뀐다”로 판단이 역전됩니다.

## CVE-2026-101356: 사용자 간 응답 섞임이 의미하는 사고 유형

CVE-2026-101356 설명의 핵심 문장은 짧습니다.

- “Incorrect object recycling and re-use … can trigger request and/or response mix-up between users.”[^3]

여기서 운영팀이 바로 떠올려야 하는 사고 시나리오는 보통 세 가지입니다.

1) **정보 유출(Confidentiality)**: A 사용자가 받아야 할 JSON/HTML이 B 사용자에게 가는 유형입니다. 개인정보, 결제정보, 내부 승인 화면이 섞이면 그 순간 사고가 됩니다.

2) **세션 탈취(Session fixation/steal)**: 응답에 `Set-Cookie: JSESSIONID=...` 같은 세션 쿠키가 포함될 때, 쿠키가 섞여 B가 A의 세션을 갖게 되는 상황이 이론적으로는 가능합니다. mix-up이 “body만”인지 “header까지”인지에 따라 위험도가 급격히 달라집니다. Tomcat 보안 공지는 request/response mix-up이라고만 되어 있고, 어느 레벨까지 섞이는지는 공지 단독으로는 단정하기 어렵습니다. 그래서 운영에서는 최악 가정을 기준으로 완화를 먼저 잡는 쪽이 현실적입니다.

3) **감사/증적 붕괴(Auditability loss)**: 이 유형이 특히 까다롭습니다. 로그에는 A가 `/account`를 호출한 기록이 남는데, 실제 A 브라우저는 B의 `/admin` 화면을 봤을 수 있습니다. 그러면 사후에 “누가 무엇을 조회했는지”를 로그로 증명할 수 없습니다. 여기서부터는 보안 사고이면서, 규제/감사/법무의 언어로 번역해야 하는 이슈가 됩니다.

이번 이슈는 “HTTP/2 + async servlet + 오류 이후”라는 조건이 붙습니다. 조건이 붙었다고 안심하기 쉬운데, 실서비스에서는 비동기 처리와 오류는 흔합니다.

- async servlet: SSE, long-poll, 대용량 업로드/다운로드, 외부 API fan-out, 파일 변환, 이미지 리사이징 같은 곳에서 생각보다 쉽게 등장합니다.
- 오류: 타임아웃, 클라이언트 커넥션 드롭, upstream reset, 애플리케이션 예외, `IOException`은 트래픽이 있으면 항상 섞여 있습니다.

즉, “공격자가 정교하게 트리거해야만 한다”가 아니라 “정상 트래픽의 꼬리에서 공격 난이도가 내려갈 수 있다” 쪽으로 시각을 잡아야 합니다.

## HTTP/2 + async 조합에서 mix-up이 특히 독해지는 이유

HTTP/2의 본질은 한 TCP(TLS) 커넥션 위에 stream을 여러 개 올려 multiplexing 하는 것입니다. HTTP/1.1 keep-alive에서도 한 커넥션에 여러 요청이 오지만, 일반적인 처리 모델은 직렬에 가깝고, 파이프라이닝은 대부분의 클라이언트가 적극적으로 쓰지 않습니다. 반대로 HTTP/2는 동시성이 기본값입니다.

Tomcat 쪽에서 이번 이슈를 “object recycling and re-use”로 설명했다는 건, 요청/응답 처리에 쓰는 내부 객체가 재사용 풀로 돌아가거나, stream 간 경계가 무너지는 순간이 있다는 의미로 읽힙니다.[^3]

Tomcat 문서가 설명하는 큰 흐름(Endpoint → Protocol → CoyoteAdapter → Servlet engine)을 보면, 프로토콜(HTTP/2) 계층에서 들어온 요청이 공통 어댑터로 넘어가며 servlet로 흘러갑니다.[^4] 이 과정에서 “어느 stream의 응답을 어느 stream으로 내보낼지”를 매핑하는 내부 상태가 흔들리면, 애플리케이션 로직이 아무리 안전해도 결과물이 엉뚱한 사용자에게 갈 수 있습니다.

async servlet은 여기서 한 번 더 꼬입니다.

- 요청 스레드는 반환되고
- 응답 커밋 시점이 뒤로 밀리며
- I/O는 non-blocking으로 흘러갈 수 있고
- 에러(특히 커넥션 단절/리셋)가 발생하면 cleanup 경로가 타이밍 의존적으로 변합니다.

이 조합은 관측 가능성도 나빠집니다. 동기 서블릿이면 “요청-응답이 한 함수 스코프 안에서 끝난다”는 직관이 있고, 로깅 포인트도 단순합니다. async에서는 응답을 쓰는 시점이 애플리케이션 스레드/컨테이너 스레드/네트워크 이벤트 루프에 분산되면서, 로그 타임라인이 요청 타임라인과 분리됩니다.

## 운영·감사 관점: 로그에 남는 증거와 남지 않는 증거

응답 섞임 계열에서 제일 먼저 부딪히는 벽은 “로그로 뭘 증명할 수 있나”입니다.

### 1) Tomcat access log는 대개 ‘의도된 처리’를 기록합니다

일반적인 AccessLogValve는 request line, status, bytes, elapsed 등을 요청 단위로 기록합니다. 문제는 mix-up이 “응답 라우팅”에서 터지면, Tomcat 입장에서는 A 요청을 처리했고 A 요청의 status/bytes를 기록했는데, 네트워크로 나간 payload는 B stream으로 갔을 수 있습니다.

즉, access log는 사고의 부정확한 증거가 될 수 있습니다. 감사 조직이 “로그 상으로는 유출이 없다”고 결론 내리기 쉬운 구조인데, 이 결론이 틀릴 수 있다는 점이 위험합니다.

### 2) 애플리케이션 로그도 마찬가지로 ‘서버 관점’입니다

애플리케이션 로그는 보통

- request id
- authenticated principal/user id
- session id
- handler/URI
- DB query

를 “요청 컨텍스트”에 붙여 남깁니다. 이 역시 처리 컨텍스트는 A의 것이고, 최종 응답이 누구에게 갔는지는 보장하지 않습니다.

여기서 운영팀이 자주 하는 실수가 “서버 로그에서 userId=A로 찍혔으니 A가 봤다”로 귀결하는 겁니다. mix-up 사고에서는 그 가정이 깨집니다.

### 3) 그나마 의미가 있는 증거는 경계 장비의 커넥션/스트림 관측입니다

HTTP/2는 한 커넥션에 stream이 여러 개이기 때문에, 다음 레벨의 데이터가 필요해집니다.

- L7 프록시(Envoy/Nginx/Apache httpd)의 HTTP/2 stream 단위 로그
- WAF의 트랜잭션 로그(단, WAF가 HTTP/2를 이해하고 stream 단위로 남길 때)
- 패킷 캡처(현실적으로는 상시가 어렵고, 사고 시점에 없을 확률이 높음)

Tomcat을 프록시 뒤에 두고 HTTP/2를 프록시에서 terminate하면, 최소한 “클라이언트가 받은 응답은 프록시가 어떤 upstream 응답을 어떤 다운스트림 요청에 매핑했는지”를 프록시 로그로 추적할 수 있습니다. 반대로 Tomcat이 인터넷에 직접 HTTP/2를 서빙하면, 이 증거가 통째로 사라지는 경우가 많습니다.

내 경우 보안 감사에서 제일 빨리 파고드는 질문은 항상 이것이었습니다.

- 특정 사용자(식별자)가 특정 시각에 특정 리소스를 “열람했다”는 걸 어떤 로그 조합으로 증명하나
- 인증/인가가 제대로 동작했음을 어떤 증적으로 보장하나

mix-up 계열은 이 두 질문에 대한 답변 자체를 불안정하게 만듭니다.

## 세션/캐시 오염 가능성: ‘서버 상태’와 ‘클라이언트 상태’를 분리해서 봐야 합니다

응답 섞임을 보면 바로 “세션/캐시가 오염된다”로 연결하기 쉬운데, 운영 판단은 좀 더 분해해서 해야 합니다.

### 1) 서버 측 상태 오염은 항상 일어나는 게 아닙니다

CVE 설명이 말하는 건 “응답이 섞인다”이고, 서버가 DB에 잘못 쓰거나 캐시 키를 바꿔치기한다는 의미는 아닙니다. 많은 경우 서버 내부 처리 자체는 정상이고, 마지막에 네트워크로 나가는 응답이 잘못 연결됩니다.

그래서 서버 측 오염은 애플리케이션이 “응답을 기반으로 후속 요청을 만들거나, 클라이언트가 받은 값을 다시 서버로 제출”하는 설계일 때 2차로 발생합니다. 예를 들어:

- 응답으로 내려준 CSRF token이 다른 사용자에게 가고, 그 토큰으로 form submit이 들어옴
- redirect URL에 일회성 코드가 들어가는데 코드가 섞여 들어감

서버 입장에서는 정상 요청이 들어온 것처럼 보입니다.

### 2) 클라이언트 측 상태 오염은 훨씬 직접적입니다

브라우저/앱이 받는 것:

- 쿠키(Set-Cookie)
- 로컬 스토리지에 저장할 사용자 프로필 JSON
- 화면에 렌더되는 개인정보

여기가 섞이면, 클라이언트가 스스로 오염됩니다. 특히 cookie는 브라우저가 자동으로 붙여 보내기 때문에 위험합니다.

여기서 자주 놓치는 포인트가 하나 더 있습니다.

- “user 간 응답이 섞였다”는 건 곧 “보안 통제(authorization)가 우회됐다”는 의미와 거의 동치로 취급될 수 있습니다.

애플리케이션은 authorization을 통과한 사용자에게만 응답을 주도록 설계합니다. 응답이 다른 사용자에게 갔다는 건, 결과적으로는 authorization이 무력화된 것과 같게 보입니다. 이것이 운영/감사에서 severity가 뛰는 이유입니다.

## 프록시/WAF 계층에서의 완화 패턴: HTTP/2를 어디서 끝낼지부터 결정합니다

Tomcat 10.1에서 HTTP/2를 켜는 건 server.xml에 `UpgradeProtocol`로 `org.apache.coyote.http2.Http2Protocol`을 붙이는 방식입니다.[^5] 즉, Tomcat 자체가 HTTP/2 endpoint가 되는 토폴로지가 기본적으로 존재합니다.

운영 완화는 결국 “HTTP/2를 누가 처리할 것인가”로 귀결됩니다.

### 패턴 A: Tomcat에서 HTTP/2를 꺼서, 애초에 취약한 경로를 제거

가장 단순하고 강한 완화입니다.

- Tomcat이 인터넷(또는 내부망)에서 직접 HTTP/2를 받는 구성이라면, `UpgradeProtocol`을 제거하거나 비활성화합니다.
- 그러면 클라이언트는 HTTP/1.1로만 접속하므로 multiplexing 기반 mix-up 계열은 표면적을 잃습니다.

대신 잃는 것:

- HTTP/2의 헤더 압축(HPACK) 효율
- 모바일 환경에서의 체감 성능
- gRPC 같은 HTTP/2 의존 워크로드(서블릿 기반 gRPC 브리지 포함)

즉, 모든 서비스에서 일괄 적용할 수는 없고, “경로 분리” 전략과 같이 가는 경우가 많습니다.

### 패턴 B: Edge/Ingress에서 HTTP/2를 terminate 하고 Tomcat에는 HTTP/1.1로 전달

현실적으로 제일 많이 쓰는 방식입니다.

- 클라이언트 ↔ (Nginx/Envoy/ALB) : HTTP/2 유지
- 프록시 ↔ Tomcat : HTTP/1.1

이렇게 하면 Tomcat의 HTTP/2 코드 경로를 우회합니다. CVE-2026-101356의 조건이 “Tomcat의 HTTP/2 processing”에 묶여 있으니, 아키텍처적으로 가장 설득력 있는 완화입니다.[^3]

다만 여기서도 함정이 있습니다.

- 프록시가 upstream으로 HTTP/2(h2c 포함)를 사용하도록 설정되어 있으면 완화가 아닙니다.
- 프록시 체인이 길면 중간 hop 중 하나가 Tomcat과 HTTP/2로 통신하는 구성이 숨어 있을 수 있습니다.

프록시 체인에서 HTTP/2 패치가 어떻게 전파되는지에 대한 감각은 예전에 정리한 글이 있고, 여기서는 그 관점만 빌립니다.

- [Apache httpd 2.4.69: HTTP/2 패치가 프록시 체인에 미치는 영향](https://daewooki.github.io/posts/apache-httpd-2469-proxy-chain-security/)

### 패턴 C: 경로 분리(path split) + 커넥션 격리(connection isolation)

서비스를 단번에 업그레이드할 수 없거나, 일부 엔드포인트만 async+HTTP/2를 쓰는 경우에 현실적인 타협안입니다.

- async가 들어간 엔드포인트(예: `/stream/*`, `/events/*`)를 별도의 Tomcat 클러스터로 분리
- 그 클러스터는 HTTP/2를 끄거나, 바로 업그레이드가 가능한 작은 blast radius로 만든다
- 나머지 동기 요청 위주의 트래픽은 기존 클러스터 유지

커넥션 격리는 여기서 두 가지 레벨이 있습니다.

1) **클라이언트 커넥션 격리**: 사용자/세션별로 커넥션을 공유하지 않도록 만드는 것인데, 브라우저 동작과 TLS 세션 재사용 때문에 강제하기 어렵습니다.

2) **프록시 업스트림 커넥션 풀 격리**: 예를 들어 Envoy/Nginx에서 upstream connection pooling을 조절해 특정 route는 별도 upstream cluster로 보내고, 해당 cluster에 대해서는 HTTP/1.1만 쓰게 강제하는 방식은 실무에서 효과가 좋습니다. “한 Tomcat 인스턴스가 HTTP/2를 받지 않도록”을 보장할 수 있기 때문입니다.

## 런북: 공개일(2026-10-20) 기준으로 우선순위 재산정하는 순서

아래 런북은 “바로 업그레이드가 이상적이지만, 현실적으로 24~72시간은 걸린다”를 전제로 짰습니다.

### 1) 자산 인벤토리: Tomcat이 HTTP/2를 직접 받는지부터 확인

우선순위는 여기서 갈립니다.

- (높음) Tomcat이 인터넷/사내 사용자망에서 직접 TLS terminate + HTTP/2 수신
- (중간) L7 프록시가 HTTP/2 terminate, Tomcat은 HTTP/1.1
- (낮음) Tomcat이 외부에서 직접 접근 불가 + HTTP/2 미사용

Tomcat에서 HTTP/2가 켜져 있는지 확인하는 가장 빠른 방법은 server.xml의 `UpgradeProtocol` 존재 여부입니다. Tomcat 공식 문서도 HTTP/2 활성화 방법을 이 형태로 제시합니다.[^5]

조직에 따라 “Tomcat은 HTTP/2 안 쓴다”라고 믿고 있는데, 실제로는 특정 서비스만 켜져 있는 경우가 많습니다(성능 실험, A/B, 특정 팀의 요구).

### 2) 버전 스코핑: 영향 범위를 숫자로 잘라 말할 수 있어야 함

이번 CVE-2026-101356은 Tomcat 10.1.55~10.1.60이 영향이고 10.1.61이 수정 버전입니다.[^1]

여기서 실무적으로 중요한 건 “10.1.54는 안전” 같은 단정이 아니라, “우리가 실제로 가진 버전 분포가 어디에 걸리는지”입니다.

- 10.1.55~10.1.60이 한 대라도 있으면, 그 서비스는 CVE 기준으로는 영향 자산입니다.
- 이때 ‘영향’은 exploit 여부가 아니라, 사고 유형이 사용자 간 데이터 섞임이라는 점 때문에 곧바로 대응 우선순위가 올라갑니다.

같은 날 공개된 trailer header cross-contamination(CVE-2026-88041)도 10.1.27~10.1.60이 영향입니다.[^1] 즉, 10.1.55~10.1.60은 둘 다 겹칩니다.

### 3) 우선순위 결정 규칙: “async+HTTP/2를 실제로 쓰는가”를 서비스 단위로 판별

CVE가 컨테이너 레벨이라도, 실제 노출은 워크로드가 만듭니다.

- async servlet을 쓰는지 확인
  - Servlet 3.0+의 async(`AsyncContext`)를 쓰는 엔드포인트
  - SSE/streaming
  - WebSocket은 별도지만, 같은 릴리스에서 WebSocket 이슈가 계속 나오는 걸 보면 경계면이 겹칠 수 있음
- HTTP/2를 실제로 타는지 확인
  - 클라이언트 ↔ Tomcat이 직접 HTTP/2인지
  - 프록시 ↔ Tomcat이 혹시 h2c로 붙는 구간이 있는지

이 조합이 참이면 “패치 전까지 완화 적용”을 기본값으로 둡니다.

## 런북: WAF/프록시 계층 완화(HTTP/2 비활성화, 경로 분리, 커넥션 격리)

### 시나리오 1) Tomcat이 직접 HTTP/2를 받는 구성: HTTP/2 즉시 비활성화

Tomcat 문서가 말하듯 HTTP/2는 `UpgradeProtocol`로 enable 합니다.[^5] 즉, 가장 확실한 완화는 disable 입니다.

- 즉시 조치: server.xml에서 HTTP/2 protocol을 제거(또는 주석 처리)
- 부작용: 일부 클라이언트에서 성능 저하

운영적으로는 “언제 다시 켤 수 있나”가 관건인데, 답은 단순합니다.

- 10.1.61로 업그레이드 완료 후 재활성화

이게 런북의 1순위입니다.

### 시나리오 2) HTTP/2는 유지해야 함: 프록시에서 terminate하고 Tomcat은 HTTP/1.1로 고정

Tomcat을 업그레이드하기 전까지는 Tomcat으로 HTTP/2가 들어가지 않게 만드는 게 핵심입니다.

대표 패턴(개념 수준)은 아래처럼 잡습니다.

- Client ↔ Nginx/Envoy: HTTP/2 (유지)
- Nginx/Envoy ↔ Tomcat: HTTP/1.1 (강제)

여기서 중요한 운영 체크는 두 가지입니다.

- 프록시가 upstream에 대해 HTTP/2를 사용하지 않는지
- Tomcat이 뒤에서라도 HTTP/2 connector를 열어두지 않는지(내부 다른 ingress가 바로 붙을 수 있음)

HTTP/3/QUIC까지 섞여 있으면 계층이 더 복잡해지는데, 완화 런북은 결국 “HTTP/2를 Tomcat에서 걷어낸다”로 단순화해야 합니다. 이 감각은 예전에 NGINX QUIC/HTTP/3 관련 체크리스트를 만들면서도 똑같이 느꼈습니다.

- [NGINX HTTP/3 구성 의존 CVE 대응 체크리스트](https://daewooki.github.io/posts/nginx-http3-quic-cve-mitigation-checklist/)

### 시나리오 3) 경로 분리: async 엔드포인트만 격리해서 ‘HTTP/2를 끄는 범위’를 최소화

현장에서는 “메인 서비스는 HTTP/2를 끄면 KPI가 흔들린다” 같은 제약이 자주 나옵니다. 이때는 경로 분리로 접근합니다.

- `/api/*`는 기존대로 유지
- `/stream/*` 같은 async 구간은 별도 upstream으로 보내고, 그 upstream은 HTTP/2를 끄거나 우선 업그레이드

장점:

- blast radius가 작아짐
- 긴급 대응(완화 적용)이 빨라짐

단점:

- 배포/라우팅 규칙이 복잡해지고, 관측 지점도 늘어남

그래도 mix-up 계열은 운영/감사 충격이 크기 때문에, 단기적으로 복잡도를 받아들이는 편이 낫습니다.

### 시나리오 4) 커넥션 격리: upstream 풀을 분리해서 교차 오염의 확률을 줄임

이건 “완전한 차단”이 아니라 “사고 확률과 폭을 낮추는” 쪽입니다.

- route별로 별도 upstream pool
- keep-alive 커넥션 수를 제한
- 문제가 되는 트래픽(비동기/대용량/불안정한 클라이언트)을 별도 pool로 분리

단, CVE-2026-101356은 Tomcat 내부 object recycling 문제라서, 커넥션 격리는 원인 제거가 아닙니다. 패치 전 임시 처방으로만 취급해야 합니다.

## 재현/탐지 목적의 테스트 하네스: 운영 환경에서 ‘섞임이 보이면 즉시 중단’

취약점 공지에는 재현 스크립트가 없습니다. 그렇다고 손 놓고 있을 수는 없어서, 나는 보통 “취약점을 100% 재현”이 아니라 “우리 서비스에서 mix-up 징후가 있는지 빠르게 탐지”하는 하네스를 만듭니다.

아래 코드는 CVE를 재현한다기보다, HTTP/2 multiplex 환경에서 async 응답이 섞이는 현상을 관측하기 위한 최소 단위입니다.

### 구성 개요

- Tomcat 10.1.x 위에 간단한 Jakarta Servlet(Async) 앱 배포
- HTTP/2로 동시 요청을 한 커넥션에서 쏘고
- 요청마다 고유한 `X-Req-Id`를 보내며
- 응답 body와 header에 그 값을 echo
- 클라이언트가 받은 값이 요청과 다르면 “섞임”으로 카운트

이 방식의 장점은 명확합니다.

- 서버 로그가 아니라 **클라이언트 관점에서** 섞임을 검출
- 장애/보안 사고의 본질(사용자가 뭘 받았나)에 가깝게 측정

### (1) Async servlet 예시 코드

`src/main/java/com/example/MixupProbeServlet.java`

```java
package com.example;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import jakarta.servlet.AsyncContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet(urlPatterns = "/probe", asyncSupported = true)
public class MixupProbeServlet extends HttpServlet {

  // 데모이므로 단순화. 운영에서는 앱의 executor/virtual thread 정책과 맞춰야 함.
  private final ExecutorService pool = Executors.newFixedThreadPool(32);

  @Override
  protected void doGet(HttpServletRequest req, HttpServletResponse resp)
      throws ServletException, IOException {

    final String reqId = req.getHeader("X-Req-Id");
    final String who = req.getHeader("X-User");

    final AsyncContext ac = req.startAsync();
    ac.setTimeout(3_000);

    pool.submit(() -> {
      HttpServletResponse r = (HttpServletResponse) ac.getResponse();
      try {
        // async 타이밍을 일부러 흔들어서 경계 조건을 많이 밟게 함
        Thread.sleep((long) (Math.random() * 30));

        r.setStatus(200);
        r.setContentType("application/json; charset=utf-8");

        // 응답에 echo: 섞이면 클라이언트에서 바로 검출 가능
        r.setHeader("X-Req-Id-Echo", reqId == null ? "(null)" : reqId);
        r.setHeader("X-User-Echo", who == null ? "(null)" : who);

        // cookie까지 섞이면 더 치명적일 수 있으니 함께 관측
        r.addCookie(new Cookie("probe", reqId == null ? "(null)" : reqId));

        String body = "{"
            + "\"ts\":\"" + Instant.now().toString() + "\","
            + "\"reqId\":\"" + (reqId == null ? "(null)" : reqId) + "\","
            + "\"user\":\"" + (who == null ? "(null)" : who) + "\""
            + "}";

        r.getOutputStream().write(body.getBytes(StandardCharsets.UTF_8));
        r.getOutputStream().flush();

      } catch (Exception e) {
        // 오류 경로를 밟는 게 핵심이라 일부러 500을 내보내지 않고 종료
      } finally {
        ac.complete();
      }
    });
  }
}
```

### (2) Maven 설정(예시)

```xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>tomcat-mixup-probe</artifactId>
  <version>1.0.0</version>
  <packaging>war</packaging>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
  </properties>

  <dependencies>
    <dependency>
      <groupId>jakarta.servlet</groupId>
      <artifactId>jakarta.servlet-api</artifactId>
      <version>6.0.0</version>
      <scope>provided</scope>
    </dependency>
  </dependencies>
</project>
```

### (3) HTTP/2 동시 요청 클라이언트(Python)

`probe.py`

```python
import asyncio
import uuid
import httpx

URL = "https://YOUR_TOMCAT_OR_PROXY/probe"
CONCURRENCY = 200
TOTAL = 5000

async def worker(client, idx, results):
    req_id = str(uuid.uuid4())
    user = f"user-{idx % 50}"

    r = await client.get(
        URL,
        headers={
            "X-Req-Id": req_id,
            "X-User": user,
        },
    )

    echo = r.headers.get("x-req-id-echo")
    uecho = r.headers.get("x-user-echo")

    ok = (echo == req_id) and (uecho == user)
    if not ok:
        results.append((req_id, user, echo, uecho, r.status_code, r.text[:200]))

async def main():
    mismatches = []

    limits = httpx.Limits(max_keepalive_connections=1, max_connections=1)
    async with httpx.AsyncClient(http2=True, verify=False, limits=limits, timeout=5.0) as client:
        sem = asyncio.Semaphore(CONCURRENCY)

        async def run_one(i):
            async with sem:
                await worker(client, i, mismatches)

        await asyncio.gather(*[run_one(i) for i in range(TOTAL)])

    print(f"TOTAL={TOTAL}")
    print(f"MISMATCHES={len(mismatches)}")
    if mismatches:
        print("sample:")
        print(mismatches[0])

if __name__ == "__main__":
    asyncio.run(main())
```

실행:

```bash
python -m pip install 'httpx[http2]'
python probe.py
```

예상 출력(정상):

```text
TOTAL=5000
MISMATCHES=0
```

이 테스트는 “취약하면 반드시 섞인다”를 보장하지 않습니다. 대신 운영에서 필요한 건 보통 이겁니다.

- 완화 전/후에 섞임 징후가 있는지
- 특정 엔드포인트/특정 트래픽 패턴에서만 터지는지
- 프록시 terminate 구성이 제대로 되었는지(HTTP/2가 Tomcat까지 내려가는지)

## 회의론과 반론: 조건이 붙은 취약점인데 과잉 대응 아닌가

이 질문은 반드시 나옵니다. 답은 조직의 리스크 모델에 따라 달라지지만, 나는 아래 근거로 “과잉 대응이 아니다” 쪽에 둡니다.

1) 영향이 “DoS”가 아니라 “cross-user mix-up”입니다. 이건 많은 조직에서 곧바로 개인정보/기밀 유출로 분류됩니다.

2) mix-up 계열은 이미 Tomcat에서 반복적으로 등장했습니다. Tomcat 10 보안 페이지에는 과거에도 “Request and/or response mix-up” 계열 항목이 따로 기록되어 있습니다.[^1]

3) 로그/감사 관점에서 피해 산정이 어렵습니다. 기술적으로는 1건이라도 사고인데, 사후 증거가 약하면 대응 비용이 기하급수로 늘어납니다.

4) 완화 비용이 “HTTP/2를 끄거나 terminate 지점을 바꾸는 것”이라면, 단기 비용 대비 얻는 안정성이 큽니다.

반대로 다음 조건이면 우선순위를 낮출 수 있습니다.

- Tomcat이 HTTP/2를 직접 처리하지 않음(프록시에서 terminate)
- async servlet을 사용하지 않음(또는 해당 서비스에서 HTTP/2 경로로는 사용하지 않음)
- 외부 노출이 전혀 없고, 내부 사용자도 제한적이며, 서비스 데이터가 비민감

다만 “내부망이니까 괜찮다”는 요즘 거의 성립하지 않습니다. 내부 사용자도 개인정보 주체이고, 내부 침해도 감사 대상이 되기 때문입니다.

## 지금 할 수 있는 일: 패치/완화 우선순위 결론

정리하면, 2026-10-20 공개된 CVE-2026-101356은 Tomcat 10.1.55~10.1.60에서 HTTP/2 + async 조합으로 사용자 간 응답 섞임을 유발할 수 있는 important 이슈입니다.[^3]

운영 우선순위는 아래처럼 잡는 게 실용적입니다.

- 1순위: Tomcat을 10.1.61로 업그레이드(영향 버전 범위를 한 번에 벗어남)[^1]
- 2순위(업그레이드 전): Tomcat이 HTTP/2를 직접 받는다면 HTTP/2 비활성화(취약한 코드 경로 제거)[^5]
- 3순위(HTTP/2 유지 필요): 프록시에서 terminate하고 Tomcat에는 HTTP/1.1만 전달하도록 강제(토폴로지로 우회)
- 4순위: 경로 분리로 async 엔드포인트만 격리, 커넥션 풀 격리로 blast radius 축소

이 순서대로 진행하면 “당장 오늘(2026-10-21 KST) 해야 할 일”과 “이번 주 안에 끝낼 일”이 분리되고, 감사/보안팀에게도 설명 가능한 스토리가 됩니다.

## 참고 자료

- [Apache Tomcat 10 vulnerabilities](https://tomcat.apache.org/security-10)
- [oss-security: CVE-2026-101356 공지](https://www.openwall.com/lists/oss-security/2026/10/20/27)
- [oss-security: CVE-2026-88041 공지](https://www.openwall.com/lists/oss-security/2026/10/20/24)
- [oss-security: CVE-2026-101296 공지](https://www.openwall.com/lists/oss-security/2026/10/20/26)
- [Tomcat 10.1.61 Changelog](https://tomcat.apache.org/tomcat-10.1-doc/changelog.html)
- [Tomcat HTTP Connector / HTTP/2 설정 문서](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html)
- [Tomcat 아키텍처: Request Process Flow](https://tomcat.apache.org/tomcat-10.1-doc/architecture/requestProcess.html)
- [JSTL redirect tag plugin 수정 커밋 메일(아카이브)](https://www.mail-archive.com/dev%40tomcat.apache.org/msg197827.html)
- [CVE-2026-101356 요약(버전 범위/고정 버전 정리)](https://basefortify.eu/cve-reports/2026/10/cve-2026-101356.html)

[^1]: <https://tomcat.apache.org/security-10>
[^2]: <https://tomcat.apache.org/tomcat-10.1-doc/changelog.html>
[^3]: <https://www.openwall.com/lists/oss-security/2026/10/20/27>
[^4]: <https://svn.apache.org/repos/asf/tomcat/site/trunk/docs/tomcat-10.1-doc/architecture/requestProcess.html>
[^5]: <https://tomcat.apache.org/tomcat-10.1-doc/config/http.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
