---
title: "NGINX 1.31.5: Control API와 njs 리스크가 만나는 지점"
description: "NGINX 1.31.5의 Control API/JSON 기반 라우팅은 운영 모델을 바꾸고, njs의 js_access 우회(CVE-2026-18329)는 스크립팅 프록시의 실패 모드를 드러냅니다."
date: 2026-09-08 12:48:14 +0900
categories: ["News", "Web"]
tags: ["nginx", "njs", "control-api", "security", "api-gateway", "cve"]
render_with_liquid: false
---

## 2026-09-02에 동시에 벌어진 일: 기능 투하와 CVE 묶음 공개

2026년 9월 2일, NGINX 메인라인 1.31.5와 njs 1.0.1이 같은 날짜에 릴리스되면서, 기능 추가와 보안 수정이 한 묶음으로 들어왔습니다. NGINX 쪽은 **Control API**, predicate locations, `client_body_early_read`, `ngx_http_json_module`이 한 번에 들어왔고[^1][^2][^3], njs 쪽은 `js_access` 관련 access control bypass(CVE-2026-18329)를 포함해 여러 이슈를 한 번에 닫았습니다[^4][^5].

오늘이 2026-09-08(KST)인 시점에서, “njs를 인증/접근제어에 쓰는 구성”은 이번 주에 영향도 평가가 필요한 게 맞습니다. 이유는 단순합니다. `js_access`는 access phase에서 allow/deny를 결정하기 때문에, 여기에서 fail-open이 나면 보안 경계가 통째로 무너집니다. njs 1.0.1 릴리스 노트는 이번 이슈가 “예외/Unhandled rejection 상황에서 nginx가 `js_access`가 성공한 것처럼 계속 처리할 수 있었다”라고 못 박습니다[^4].

반대로 NGINX 1.31.5의 기능 묶음은 프록시/게이트웨이의 운영 면에서도 꽤 큰 방향 전환입니다. 예전에는 “NGINX 인스턴스 제어는 signal 기반 + 로그 확인 + 외부 오케스트레이터”가 사실상 정답이었는데, Control API가 들어오면 “프로세스가 API를 제공하고, CI/CD가 동기적으로 결과를 받는” 모델로 기울 수밖에 없습니다[^6].

이 글의 관점은 두 가지를 묶습니다.

1) Control API/JSON 모듈이 운영 모델을 바꾸는 지점

2) `js_access` 우회 같은 이슈가 “스크립팅을 붙인 프록시”의 위험면을 어떻게 키우는지

## Control API: NGINX가 ‘API로 제어되는 프로세스’가 되는 순간

NGINX의 전통적인 제어 플로우는 대체로 이렇습니다.

- 배포 파이프라인이 `nginx -t`로 문법 검사
- `nginx -s reload`(SIGHUP)로 reload
- 성공/실패의 디테일은 error log를 tail 해서 확인
- 운영 자동화는 결국 “명령 실행 + 로그 파싱 + 재시도”로 귀착

Control API는 이 루프를 끊어내려는 시도입니다. NGINX 문서에서 Control API는 master process에 구현된 REST API라고 명시하고, worker/process/config 정보를 조회하거나 config reload를 트리거하고 reload 로그까지 구조화된 형태로 확인할 수 있다고 설명합니다[^6].

특히 눈에 띄는 부분은 다음입니다.

- 엔드포인트: `/1/control/processes`, `/1/control/config`, `/1/nginx`[^6]
- `/1/control/config`는 in-memory config을 반환하고 `PATCH`로 reload를 트리거할 수 있다고 설명합니다[^6]
- API는 기본적으로 disabled이며, `nginx -l` 옵션으로 UNIX domain socket 또는 TCP 포트에 바인딩해 활성화합니다[^6]
- Open Source 1.31.5부터 가능하다고 명시합니다[^6]

여기서 운영 모델이 바뀌는 지점은 “성공/실패를 로그에서 사후적으로 찾는 것”과 “API 응답으로 동기적으로 받는 것”의 차이입니다. reload는 언제나 위험합니다. 설정 파일은 컴파일이 아니라 런타임 파싱이고, 모듈 조합에 따라 경계 조건이 많습니다. 그런데 signal 기반은 결과를 ‘프로세스 외부’에서 추론해야 합니다. Control API는 결과를 프로세스가 직접 말해줍니다.

나는 이게 단순히 편의 기능이라고 보지 않습니다. 이제 NGINX도 정책/구성/운영을 API로 다루는 흐름이 더 강해진다는 신호에 가깝습니다. 예전에 썼던 글에서 “발표”보다 무서운 게 API/정책의 조용한 변경이라고 정리했는데[^7], NGINX 같은 인프라 컴포넌트도 비슷하게 움직입니다. 사람이 수동으로 만지는 시절이 길어질수록 drift와 수동 예외가 늘고, 결국 신뢰할 수 있는 건 API/자동화 경로가 됩니다.

## Control API는 ‘원격 제어’가 아니라 ‘제어면(control plane) 노출’이다

Control API는 강력하지만, 보안 모델이 매우 날것입니다. NGINX 커뮤니티 블로그는 Control API를 네트워크 포트로 노출하지 말고 UNIX domain socket에 바인딩하라고 강하게 경고합니다. 이유는 간단합니다. 인증이 없는 인터페이스로 내부를 노출하는 형태이기 때문입니다[^2].

문서도 같은 방향으로 “인터넷에 절대 노출하지 말 것”, “가능하면 UNIX domain socket을 사용할 것”, “방화벽/ACL로 제한할 것”을 적습니다[^6].

여기서 운영자가 새로 가지게 되는 책임은 두 가지입니다.

1) NGINX 프로세스의 제어면을 네트워크 경계 밖으로 새지 않게 만들기

2) CI/CD, SRE 도구가 해당 소켓에 접근할 수 있는 최소 권한 설계

나는 Control API를 “운영 효율 개선”으로만 보면 사고가 난다고 봅니다. 이건 NGINX Unit의 Control API를 프록시 레이어까지 끌고 오는 느낌에 가깝습니다. Unit은 애초에 JSON 기반 구성을 REST로 관리하는 컨셉이고, 예제도 UNIX socket 중심으로 설계되어 있습니다[^8]. NGINX도 같은 철학을 일부 채택하는 순간, 기존에 없던 attack surface가 생깁니다.

정리하면 Control API는 “원격에서 reload를 편하게”가 아니라, **프로세스 자체가 관리 인터페이스를 가진다**로 봐야 합니다.

## JSON parsing + predicate locations + early body read: ‘API 게이트웨이’ 쪽으로 한 발 더

NGINX 1.31.5에서 같이 들어온 기능들은 사실 Control API만큼이나 운영/아키텍처에 영향이 큽니다.

- predicate locations: `location $variable { ... }` 형태로 변수를 기반으로 location 선택이 가능해졌습니다[^9]. 문서에는 “prefix/regex/predicate(1.31.5)”라는 표현이 들어갑니다[^9].
- `client_body_early_read`: request header를 받은 직후에 request body를 location 매칭 이전에 미리 읽는 옵션입니다[^9]. 또한 특정 모듈과 호환되지 않는다고 명시합니다(예: unbuffered body를 쓰는 `ngx_http_grpc_module`, body를 파일로 쓰는 `ngx_http_dav_module` 등)[^9].
- `ngx_http_json_module`: JSON 문서를 변수에 담아두고, `json_set`으로 path 기반 값을 뽑아 NGINX 변수로 만드는 기능입니다. 문서는 “문서는 request당 1회만 파싱되며”, “기본 빌드에 포함되지 않고 `--with-http_json_module`이 필요”하다고 밝힙니다[^10].

이 조합이 왜 중요하냐면, 기존에는 다음 둘 중 하나였습니다.

- URI/host/header 위주의 라우팅으로 만족
- body 기반 라우팅/검증이 필요하면 Lua(OpenResty)나 njs 같은 스크립팅 레이어를 올림

그런데 지금은 “body(JSON)를 읽고 → 값을 변수로 뽑고 → 그 변수를 predicate로 location을 선택한다”가 core에서 됩니다. 커뮤니티 블로그는 이걸 “스크립팅 없이 JSON payload를 파싱하고 라우팅하는 능력”으로 강조합니다[^2].

이게 결국 의미하는 바는 “NGINX를 API gateway처럼 쓰는 패턴이 더 메인스트림이 된다”입니다. 단순 reverse proxy가 아니라, payload-aware routing과 edge validation을 core로 가져왔기 때문입니다.

여기서 중요한 트레이드오프도 같이 커집니다.

- request body를 early read하면 buffering과 메모리/디스크 I/O 특성이 바뀝니다. `client_body_early_read`는 body read 설정을 server block에서 가져온다고 설명합니다[^9].
- 호환성 제약이 생깁니다. 문서가 호환되지 않는 모듈을 명시한 건, “켜면 안 되는 곳”이 분명히 있다는 뜻입니다[^9].

NGINX가 ‘이제 API로 제어되는 시대’라는 말은, Control API 하나만으로 성립하지 않습니다. 라우팅 판단 자체가 점점 더 “API 요청의 의미(semantic)”로 올라오고 있기 때문에, 운영 측면에서도 정책과 관측 지점이 바뀝니다.

## 실전 구성 예제: JSON으로 라우팅하고, Control API로 reload를 검증한다

아래 예제는 장난감처럼 보일 수 있지만, 의도는 꽤 현실적입니다.

- API endpoint는 다 `/api`로 들어오고
- body(JSON)에 `route` 필드가 들어있고
- 그 값에 따라 upstream을 분기
- 분기 자체는 njs 없이 core 기능으로만 구현
- 운영 측면에서 reload는 Control API를 통해 동기적으로 성공/실패를 확인

### 실행 전 확인: 이미지/빌드 옵션

- NGINX Docker Official Image는 `1.31.5` 태그를 제공합니다[^11].
- `ngx_http_json_module`은 “기본 빌드에 포함되지 않는다”고 문서에 적혀 있습니다. 즉, 사용 중인 NGINX가 `--with-http_json_module`로 빌드되지 않았다면 설정이 로드되지 않습니다[^10].
- Control API도 Open Source에서는 `--with-control-api`로 빌드되어 있어야 한다고 문서에 적혀 있습니다[^6].

NGINX 1.31.5 소스 릴리스 자체는 nginx.org 다운로드 페이지에 올라와 있습니다[^12].

### 파일 1) docker-compose.yml

```yaml
services:
  nginx:
    image: nginx:1.31.5
    container_name: nginx-1315
    ports:
      - "8080:8080"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./run:/run
    # Control API를 UNIX domain socket으로 열기
    command: ["nginx", "-g", "daemon off;", "-l", "unix:/run/nginx-control.sock"]
    depends_on:
      - backend_a
      - backend_b

  backend_a:
    image: hashicorp/http-echo:1.0
    container_name: backend-a
    command: ["-listen=:9001", "-text=backend=a\n"]

  backend_b:
    image: hashicorp/http-echo:1.0
    container_name: backend-b
    command: ["-listen=:9002", "-text=backend=b\n"]
```

### 파일 2) nginx.conf

```nginx
worker_processes auto;

events {
  worker_connections  1024;
}

http {
  # JSON 파싱/early read를 쓰는 순간, body size/버퍼 정책이 사실상 라우팅 정책이 됩니다.
  client_max_body_size    64k;
  client_body_buffer_size 64k;

  # Content-Type이 JSON일 때만 early read
  map $http_content_type $early_read {
    default           "";
    application/json  1;
  }

  server {
    listen 8080;

    # location 매칭 전에 request body를 미리 읽어 $request_body를 채우는 전제
    client_body_early_read $early_read;

    # $request_body(JSON)에서 route 값을 뽑아 $route에 저장
    # ngx_http_json_module 필요
    json_set $route $request_body route;

    # predicate location을 안전하게 쓰려면, URI까지 같이 묶어서 predicate를 만들어야 합니다.
    # 그렇지 않으면 route=a가 들어온 모든 요청이 location $is_route_a로 빨려 들어갈 수 있습니다.
    map "$uri|$route" $is_route_a {
      default   "";
      "/api|a"  1;
    }

    map "$uri|$route" $is_route_b {
      default   "";
      "/api|b"  1;
    }

    # predicate locations (1.31.5)
    location $is_route_a {
      proxy_pass http://backend_a:9001;
    }

    location $is_route_b {
      proxy_pass http://backend_b:9002;
    }

    # 기본 /api 핸들러
    location = /api {
      default_type text/plain;
      return 400 "unknown route=$route\n";
    }

    location / {
      return 404;
    }
  }
}
```

### 실행 명령

```bash
mkdir -p run

docker compose up -d
```

### 동작 확인: JSON payload 기반 라우팅

```bash
curl -s -X POST http://localhost:8080/api \
  -H 'Content-Type: application/json' \
  -d '{"route":"a","request":{"id":"req-1"}}'

curl -s -X POST http://localhost:8080/api \
  -H 'Content-Type: application/json' \
  -d '{"route":"b","request":{"id":"req-2"}}'

curl -s -X POST http://localhost:8080/api \
  -H 'Content-Type: application/json' \
  -d '{"route":"c"}'
```

예상 출력은 대략 아래 형태입니다.

```text
backend=a
backend=b
unknown route=c
```

여기서 핵심은 “njs 없이도 body(JSON) 기반 분기를 core로 넣을 수 있다”는 점입니다. 그 자체가 스크립팅 프록시의 필요성을 낮춥니다.

### Control API 확인: 프로세스 상태 조회와 reload 결과의 구조화

Control API 소켓을 host에 `./run`로 노출했기 때문에, host에서 바로 호출할 수 있습니다.

```bash
curl --unix-socket ./run/nginx-control.sock http://localhost/1/nginx
curl --unix-socket ./run/nginx-control.sock http://localhost/1/control/processes
```

그리고 reload는 아래처럼 호출합니다.

```bash
curl --unix-socket ./run/nginx-control.sock \
  -X PATCH http://localhost/1/control/config
```

Control API의 엔드포인트 구성을 문서가 정리해두었습니다[^6]. 기존 `nginx -s reload`는 “명령 성공”과 “reload 성공”이 같은 의미가 아니었는데, Control API는 이 둘을 한 응답으로 묶어낼 수 있는 여지를 만듭니다.

## 반론: “이 정도면 NGINX가 점점 무거워지는 것 아닌가”

이 방향에 대한 회의론도 충분히 성립합니다.

1) early body read는 비용이 듭니다. NGINX의 강점은 streaming인데, 라우팅 전에 body를 읽으면 buffering이 기본값이 됩니다. `client_body_early_read`는 모듈 호환성 제약을 문서에 명시할 정도로 처리 순서를 바꿉니다[^9].

2) JSON 파싱은 결국 CPU를 씁니다. `ngx_http_json_module`은 “request당 1회만 파싱”으로 비용을 제어한다고 설명하지만[^10], 초고성능 엣지 레이어에서 이 비용은 무시할 수 없습니다.

3) Control API는 운영 편의와 함께 control plane 노출을 가져옵니다. 그리고 인증/권한 제어가 기본 제공되는 형태가 아니라면, 결국 “소켓 권한/네임스페이스/네트워크 격리”로 해결해야 합니다[^6].

나는 이 반론을 “맞다” 쪽에 둡니다. 다만 시장의 트래픽 패턴이 이미 바뀌고 있습니다. URI가 의미를 잃고 `/api`, `/graphql` 같은 endpoint로 모든 게 들어오는 구조에서는, 엣지에서 body를 조금 읽고 의미 기반 라우팅을 하는 요구가 계속 올라옵니다. 커뮤니티 블로그도 이 변화(동일한 URI로 서로 다른 operational request가 들어오는 패턴)를 전제로 기능들을 설명합니다[^2].

## njs `js_access` 우회(CVE-2026-18329): 실패 모드가 ‘deny’가 아니라 ‘allow’였던 문제

njs 1.0.1 릴리스 노트의 첫 항목이 이 이슈입니다.

- 비동기 request body continuation이 exception을 던지거나 unhandled rejection을 만들었을 때
- nginx가 `js_access` 체크가 성공한 것처럼 요청을 계속 처리할 수 있었다
- CVE-2026-18329
- 0.9.9에서 도입된 이슈로 기술

[^4]

njs Security 문서는 영향 버전을 더 직접적으로 정리합니다.

- Vulnerable: 0.9.9–1.0.0
- Not vulnerable: 1.0.1+

[^5]

이 이슈가 운영에 치명적인 이유는 `js_access`의 의미 때문입니다. `js_access`는 access phase handler이고, “아무 것도 하지 않고 return하면 access를 grant한다”는 규칙을 문서가 명시합니다. deny는 `r.return()`을 호출해야 합니다[^13].

즉, 정상 설계에서 `js_access`는 보통 아래 패턴을 갖습니다.

- 성공(allow): 함수가 그냥 return
- 실패(deny): `r.return(401/403)` 호출

그런데 예외/Unhandled rejection 경로가 ‘함수의 정상적인 종료’로 취급되어 버리면, 설계 의도와 반대로 allow로 빠질 수 있습니다. 이게 CVE-2026-18329가 만들어내는 공포입니다. “실패했는데 통과한다”는 건 보안에서 가장 나쁜 형태입니다.

실제 3rd-party 요약도 이 이슈를 “authentication/authorization bypass”로 설명합니다[^14].

## `js_access`를 접근제어에 쓰는 구성에서 위험이 커지는 이유

njs 통합 문서는 JavaScript가 독립적으로 실행되는 런타임이 아니라, nginx가 정해진 integration point에서 호출한다고 설명합니다. 특히 `js_access` 같은 handler는 한 번 호출되고, 비동기 이벤트는 내부 콜백으로 이어진다고 적습니다[^15].

이 모델의 특징은 다음입니다.

- access phase라는 “짧고 결정적인 구간”에서
- 외부 서비스 호출(예: `ngx.fetch()`), body 파싱(예: `r.readRequestJSON()`), 타이머 등 비동기를 엮어
- allow/deny를 결정하는 코드가 자연스럽게 만들어진다는 점입니다[^13][^15].

즉, 스크립팅 프록시를 붙이면 편해지는 이유와, 위험이 커지는 이유가 같습니다.

- 편해짐: “요청을 보고 즉석에서 정책을 실행”
- 위험 커짐: “정책이 실행되는 경로가 비동기/예외/외부 의존성에 걸려 복잡해짐”

CVE-2026-18329는 이 복잡성의 취약한 지점이 “fail-open”으로 터진 사례입니다. 그리고 이런 류의 이슈는 한 번으로 끝나지 않는 편입니다. 이번 njs 1.0.1에는 worker crash(CVE-2026-78222)와 XML 관련 heap overflow(CVE-2026-78689)도 같이 들어왔습니다[^4][^5].

인증/접근제어에 스크립팅을 붙인 순간, “프록시 취약점”이 아니라 “인증 시스템 취약점”이 됩니다.

## 회피/완화의 현실적인 우선순위: 코드 수정이 아니라 버전 업그레이드

CVE-2026-18329는 코드 패턴을 잘 짜면 피할 수 있는 종류가 아닙니다. 예외/Unhandled rejection에서 nginx가 요청을 계속 처리할 수 있었다는 것은, 애플리케이션 로직 레벨의 실수가 아니라 런타임/연동부의 실패 모드 문제입니다[^4].

따라서 1순위는 업그레이드입니다.

- njs 1.0.1 이상으로 올려서 취약 버전을 벗어나는 게 기본 대응입니다[^5].

그다음이 “코드 레벨의 방어적 구현”입니다. 패치 후에도 운영에서는 항상 네트워크/외부 의존성/타임아웃/메모리 부족 같은 실패가 터집니다. 접근제어 로직은 실패했을 때 반드시 deny로 가야 합니다.

### `js_access` 핸들러의 방어적 기본형

`js_access` 문서는 “return만 하면 allow”라고 적기 때문에[^13], 나는 다음을 팀 규칙으로 둡니다.

- allow는 “아무 것도 하지 않고 return”이 아니라, 코드 상에서 “여기부터 allow”라는 경계를 명확히 드러낸다
- 예외는 반드시 catch해서 `r.return(403)` 또는 `r.return(401)`로 끝낸다
- 외부 호출은 timeout을 강제하고, timeout도 deny로 본다

예시 코드는 아래처럼 쓰는 쪽에 가깝습니다.

```js
// access.js

async function authorize(r) {
  try {
    // request body를 쓰는 순간부터, body 읽기 실패/JSON 파싱 실패는 항상 발생 가능한 경로입니다.
    const body = await r.readRequestJSON();

    const token = r.headersIn.Authorization;
    if (!token) {
      r.return(401);
      return;
    }

    // 여기서 외부 인증 서버 호출(ngx.fetch)을 한다면, timeout/실패는 deny로 귀결시키는 게 맞습니다.
    // (구체 구현은 환경마다 다르니 생략)

    // allow: 아무 것도 하지 않고 return
    return;

  } catch (e) {
    // 실패는 항상 deny
    r.error(`authorize failed: ${e}`);
    r.return(403);
    return;
  }
}

export default { authorize };
```

이 방어 패턴은 취약점 자체를 없애는 해결책이 아니라, 패치 이후에도 남는 “운영 실패 모드”를 정리하는 습관에 가깝습니다.

## ‘스크립팅 붙인 프록시’의 위험을 줄이는 방향: core 기능으로 이동시키기

NGINX 1.31.5의 JSON/predicate/early-read 조합은, 역설적으로 njs 사용 범위를 줄일 수 있게 해줍니다.

- body(JSON)에서 특정 key를 뽑아
- map으로 정책을 만들고
- predicate location으로 분기

이 정도는 이제 njs 없이도 됩니다[^10][^9].

njs가 계속 필요한 영역은 남습니다.

- 외부 API 호출 기반의 복잡한 authorization
- 동적 rate limit, shared dict 기반 카운터
- 특수한 request/response 변환

다만 “인증/접근제어의 최종 결정”을 njs에 두는 건 이번 이슈 같은 형태로 리스크가 증폭됩니다. 가능한 설계는 아래 쪽입니다.

- allow/deny 최종 결정은 내장 기능(예: `auth_request`, mTLS, JWT, allow/deny)으로 두고
- njs는 부가 정보 추출/헤더 구성/라우팅 힌트 정도로 제한

이 글의 앞부분에서 예제로 보여준 것처럼, routing decision을 core로 옮기면 스크립팅 레이어는 줄어듭니다.

나는 이런 변화를 AI API 운영 변화와 비슷하게 봅니다. 기능이 늘어나는 방향은 대부분 “오퍼레이터가 임의로 스크립팅해서 풀던 문제를 제품 core가 가져가는” 쪽입니다. 지난 몇 달 동안 AI API 쪽도 에이전트 표준화, 운영/보안 강제가 커졌다는 정리를 했는데[^16][^17], NGINX도 “이제 core에서 처리할 수 있는 영역을 늘려서 스크립팅에 기대지 않게 만든다”는 방향으로 읽힙니다.

## 앞으로 지켜볼 것: Control API가 ‘운영의 표준 인터페이스’가 되려면

Control API는 시작점입니다. 다만 실제 운영 표준으로 자리잡으려면, 나는 다음이 관건이라고 봅니다.

1) 인증/권한 모델

문서/블로그의 뉘앙스는 “애초에 네트워크로 열지 말고 UDS로만 열어라”에 가깝습니다[^2][^6]. 이 전략은 단순하지만, 클러스터/원격 운영에서 불편해집니다. 결국 외부 시스템(NGINX Agent, Instance Manager, sidecar)을 통해 간접 제어로 흐를 가능성이 큽니다.

2) API 스키마 안정성

Control API는 OpenAPI 스펙을 다운로드할 수 있도록 안내합니다[^6]. 이게 안정적으로 유지되고, 버전 정책이 명확해져야 CI/CD에서 “API 의존”이 됩니다.

3) ‘reload 기반 모델’ 자체의 한계

Control API가 들어와도, NGINX의 config 적용 단위가 reload인 건 그대로입니다. Unit처럼 “부분 적용/동적 변경”과는 다른 길입니다[^8]. 다만 reload 결과를 API 응답으로 받는 것만으로도 운영 난이도는 크게 내려갑니다.

## 지금 당장 해야 할 영향도 평가 체크리스트

여기부터는 이번 주에 실제로 점검할 항목들입니다.

### 1) njs `js_access` 사용 여부부터 찾기

- `nginx.conf` 및 include되는 파일에서 `js_access`를 grep
- 사용 중이면, 그 location이 어디를 보호하는지(인증이 필요한 API인지) 분류

`js_access`의 의미(아무 것도 하지 않으면 allow)는 문서에 명시되어 있으니, 검색 결과가 나오면 우선순위를 높게 잡는 게 맞습니다[^13].

### 2) njs 버전 확인: 0.9.9–1.0.0이면 즉시 대응

njs Security 문서가 vulnerable range를 명확히 적고 있습니다[^5].

- Vulnerable: 0.9.9–1.0.0
- Not vulnerable: 1.0.1+

패키지 배포 형태에 따라 확인 방법은 다르지만, 핵심은 “실제 로드된 njs 모듈의 버전”입니다.

### 3) 업그레이드가 당장 어렵다면, `js_access` 경로를 임시로 우회 차단

나는 “코드에 try/catch 넣어서 완화”는 2차 대응으로 둡니다. 이번 이슈는 런타임의 fail-open이기 때문에, 근본 해결은 패치입니다[^4].

그럼에도 업그레이드가 지연되면, 임시 대응으로는 아래 같은 선택지가 남습니다.

- `js_access`를 제거하고, 더 보수적인 내장 접근제어(예: `auth_request`)로 임시 전환
- 취약 location 자체를 maintenance로 내려서 서비스 범위를 줄이기

### 4) Control API를 켰다면, 노출 경로 점검이 먼저다

- TCP 포트로 열지 않았는지 확인
- UDS 권한/경로가 안전한지 확인

문서가 “UDS가 가장 효과적”이라고 말하는 이유는 파일 권한으로 통제 가능하기 때문입니다[^6].

### 5) JSON/early-read 기능 도입은 성능/호환성 실측 후 점진 적용

`client_body_early_read`는 호환되지 않는 모듈이 존재한다고 문서가 명시합니다[^9]. “도입하면 편할 것 같다”로 켜는 기능이 아닙니다.

- 적용 대상 location을 좁혀서 시작
- body 크기 제한을 강하게 걸고
- memory/temp file 동작을 확인

이 정도는 전제입니다.

## 참고 자료

- [NGINX 2026 뉴스](https://nginx.org/2026.html)
- [NGINX 1.31.5 커뮤니티 블로그](https://blog.nginx.org/blog/nginx-1-31-5-control-api-predicate-locations-early-body-inspection-and-more)
- [nginx-1.31.5 CHANGES](https://fossies.org/linux/www/nginx-1.31.5.tar.gz/nginx-1.31.5/CHANGES)
- [nginx 다운로드](https://nginx.org/en/download.html)
- [ngx_http_json_module](https://nginx.org/en/docs/http/ngx_http_json_module.html)
- [ngx_http_core_module: location](https://nginx.org/en/docs/http/ngx_http_core_module.html)
- [ngx_http_core_module: client_body_early_read](https://nginx.org/en/docs/http/ngx_http_core_module.html)
- [Control NGINX Processes at Runtime](https://docs.nginx.com/nginx/admin-guide/basic-functionality/runtime-control/)
- [njs 1.0.1 변경 사항](https://nginx.org/en/docs/njs/changes.html)
- [njs Security](https://nginx.org/en/docs/njs/security.html)
- [ngx_http_js_module: js_access](https://nginx.org/en/docs/http/ngx_http_js_module.html)
- [Execution model and integration points](https://nginx.org/en/docs/njs/integration.html)
- [Amazon Linux ALAS: CVE-2026-18329](https://explore.alas.aws.amazon.com/CVE-2026-18329.html)
- [nginx Official Image](https://hub.docker.com/_/nginx/?_pxhc=1481865177513)
- [NGINX Unit Control API](https://unit.nginx.org/controlapi/)
- [빅테크 AI “발표”보다 더 무서운 건 API/정책의 조용한 변경이다](https://daewooki.github.io/posts/2026-3-ai-api-1/)
- [8월 업데이트 총정리: 에이전트 표준화 + 운영/보안 강제](https://daewooki.github.io/posts/8-67-ai-api-1/)
- [5월 업데이트 총정리: Ops와 한도, 비동기](https://daewooki.github.io/posts/52026-ai-api-ops-1/)

[^1]: <https://nginx.org/2026.html>
[^2]: <https://blog.nginx.org/blog/nginx-1-31-5-control-api-predicate-locations-early-body-inspection-and-more>
[^3]: <https://fossies.org/linux/www/nginx-1.31.5.tar.gz/nginx-1.31.5/CHANGES>
[^4]: <https://nginx.org/en/docs/njs/changes.html>
[^5]: <https://nginx.org/en/docs/njs/security.html>
[^6]: <https://docs.nginx.com/nginx/admin-guide/basic-functionality/runtime-control/>
[^7]: <https://daewooki.github.io/posts/2026-3-ai-api-1/>
[^8]: <https://unit.nginx.org/controlapi/>
[^9]: <https://nginx.org/en/docs/http/ngx_http_core_module.html>
[^10]: <https://nginx.org/en/docs/http/ngx_http_json_module.html>
[^11]: <https://hub.docker.com/_/nginx/?_pxhc=1481865177513>
[^12]: <https://nginx.org/en/download.html>
[^13]: <https://nginx.org/en/docs/http/ngx_http_js_module.html>
[^14]: <https://explore.alas.aws.amazon.com/CVE-2026-18329.html>
[^15]: <https://nginx.org/en/docs/njs/integration.html>
[^16]: <https://daewooki.github.io/posts/8-67-ai-api-1/>
[^17]: <https://daewooki.github.io/posts/52026-ai-api-ops-1/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
