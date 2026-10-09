---
title: "mod_pagespeed 2.2 운영: nginx에서 optimizer worker 붙이고 안전하게 업데이트하기"
description: "2.2.0의 보안·신뢰성 변경을 전제로 nginx/Apache+worker를 매칭 배포하고, 캐시·행(hang)·레이턴시를 운영 관점에서 다룹니다."
date: 2026-10-09 14:28:07 +0900
categories: ["Performance", "Modpagespeed"]
tags: ["mod-pagespeed", "nginx", "performance", "security-updates", "optimizer-worker", "lcp"]
render_with_liquid: false
---

## PageSpeed를 성능 플러그인이 아니라 서버 컴포넌트로 봐야 하는 이유

mod_pagespeed는 HTML과 정적 리소스를 서버에서 재작성합니다. 이 말은 곧, (1) 파서와 rewriter가 요청 경로에 들어오고, (2) admin endpoint와 management API 같은 운영용 표면이 생기며, (3) 외부 리소스 fetcher가 서버 권한으로 동작한다는 뜻입니다. 성능 최적화 도구이면서 동시에 공격 표면이 됩니다.

2.2.0 릴리스 노트가 이 관점을 강하게 뒷받침합니다. 2026-10-06에 module과 optimizer worker가 함께 릴리스되었고, 운영 형태와 무관하게 **매칭 페어로 설치/업그레이드** 하라고 명시합니다. 그리고 “보안 및 신뢰성 업데이트”로서 11건의 보안 이슈 수정, 번들 curl 업데이트, nginx module의 worker 사용 가능, shared cache에서의 데이터 유실 방지, 특정 상황에서의 hang 방지 등이 묶여 있습니다.[^1]

운영에서 중요한 포인트는 단순합니다.

- PageSpeed를 켰으면, 그 순간부터 이 구성요소는 reverse proxy나 WAS 런타임과 같은 급으로 패치/롤백/관측 대상이 됩니다.
- 업데이트를 “성능 개선 릴리스”로 취급하면, 보안 패치를 놓치거나, 캐시 포맷 변경 같은 운영 리스크를 성능 튜닝 작업으로 오해하게 됩니다.

이 글은 2.2.0에서 특히 운영 설계를 바꿔야 하는 지점 세 가지를 중심으로 정리합니다.

1) nginx/Apache module + optimizer worker를 매칭 배포하는 방법과 배포 순서

2) 캐시 공유 시 데이터 유실과 행(hang)을 피하기 위한 설정/운영 포인트

3) prioritize_critical_css 같은 기능이 실제 레이턴시에 주는 영향을 측정하는 방법

## 2.2.0에서 운영자가 먼저 읽어야 할 변경점

### 1) module과 optimizer worker는 한 제품으로 움직입니다

2.2.0은 “module + optimizer worker를 함께 릴리스하고 매칭 페어로 설치한다”를 제품 정책으로 박아두었습니다. apt/yum repo에서 두 패키지는 같은 패키지 버전(1.17.0)을 가지며, 컨테이너/Helm/NuGet 등 제품 버전은 2.2.0으로 맞춰집니다.[^1]

여기서 운영 관점의 해석은:

- pagespeed 관련 장애가 나면 module만 재시작/롤백해서 해결하는 접근이 점점 통하지 않습니다.
- 반대로, worker를 도입하면 요청 경로에서 heavy work를 분리할 수 있지만, 프로세스 간 캐시/소켓/권한/업그레이드 순서 같은 운영 지점이 늘어납니다.

### 2) 2.2.0은 보안 릴리스입니다(11건 수정 + curl 업데이트)

릴리스 노트에 보안 항목이 구체적으로 열거됩니다. nginx module / Apache module / HTML rewriter의 DoS 성격 이슈, nginx admin pages 접근 제한 우회, in-place optimization 관련 cache integrity 및 정보 노출, admin console request forgery(CSRF 성격) 방어, optimizer management API DoS 및 `--api-read-open` 정보 노출, Windows LPE, 그리고 curl 8.22.0 번들 업데이트가 포함됩니다.[^1]

curl 8.22.0의 보안 공지는 2026-09-02에 공개된 advisory batch와 함께 나왔고, oss-security와 curl 프로젝트 아카이브에서도 확인됩니다.[^2]

이 지점은 “우리 서비스는 리소스 최적화만 하는데?”로 넘길 수 없습니다. mod_pagespeed가 번들한 curl은 서버에서 리소스를 가져오는 경로에 들어갑니다. 외부 fetcher가 취약하면 SSRF, request smuggling, TLS 관련 취약점 등으로 이어질 여지가 생깁니다(취약점의 성격은 CVE마다 다르지만, 운영 관점에서는 업데이트 트리거로 충분합니다).

### 3) nginx module이 optimizer worker를 쓸 수 있게 됩니다

2.2.0의 굵직한 변화 중 하나가 “native nginx module이 worker를 사용 가능”입니다.[^1]

이전에는 Apache 쪽이 worker 모델에 더 자연스럽게 얹혔다면, 이제 nginx에서도 같은 방식으로 in-place optimization을 worker에게 넘길 수 있습니다. nginx는 `pagespeed DaemonSocketPath`와 `pagespeed DaemonVolumePath` 두 지시어를 `server` 블록에 설정해 worker의 notify socket과 cache volume을 연결합니다.[^3]

### 4) 캐시 포맷 변경과 start-order가 운영 리스크로 등장합니다

2.2.0에서 디스크 캐시 라이브러리의 on-disk format이 바뀌면서 “업그레이드 직후 캐시가 한 번 비어 시작한다”가 명시됩니다. 기본 cache dir도 v1에서 v2로 바뀝니다.[^1]

그리고 start-order가 중요합니다.

- optimizer를 먼저 시작
- 그 다음 web server 시작/재시작

이 순서를 지키지 않으면 nginx가 worker 캐시를 못 붙는 동안 in-place optimization을 끄거나, 어떤 조건에서는 nginx 시작 자체가 실패할 수 있다고 릴리스 노트가 경고합니다.[^1]

## 배포 토폴로지 선택: native module 결합 vs reverse-proxy shape

mod_pagespeed 2.x 계열은 현실적으로 두 가지 shape로 운영됩니다.

### 1) native module(nginx 또는 Apache) + optimizer worker

- nginx는 배포판 stock nginx 버전에 맞춘 dynamic module 패키지를 제공합니다.
- nginx module은 기본적으로 단독 동작하지만, 2.2.0부터 worker를 붙이는 경로가 공식화됩니다.
- Apache는 패키지 설치 시 worker를 바라보는 구성도 함께 설치되는 쪽으로 문서가 정리되어 있습니다.[^3]

이 shape는 장점이 뚜렷합니다.

- 요청 경로 최적화와 백그라운드 최적화를 분리할 수 있습니다.
- 서버 내 파일 시스템 캐시(optimizer cache volume)를 중심으로 성능을 만들기 때문에, 외부 캐시 계층을 단순화할 수 있습니다.

대신 운영 포인트가 늘어납니다.

- unix socket/권한/pagespeed 그룹
- cache volume 경로 설계(v1→v2 같은 세대 교체 포함)
- worker 장애 시 동작(in-place fallback)과 관측

### 2) Docker/Helm에서의 reverse-proxy shape(thin nginx + worker)

문서에서 “thin nginx module + worker”는 별도 설정 레퍼런스로 분리되어 있습니다. 여기서는 nginx 설정 surface가 작고, 핵심은 `pagespeed_cache_path`로 worker와 같은 cache volume file을 mmap 공유하는 방식입니다.[^4]

이 shape는 멀티 오리진이나 k8s 운영에서 다루기 쉽지만, 캐시 파일을 공유하는 형태가 강제되면서 캐시 일관성과 IO 특성이 더 민감해집니다. 또한 upgrade 시 캐시 generation mismatch를 모듈이 감지해서 캐시를 꺼버리는 동작이 기본 안전장치로 들어옵니다.[^4]

이 글은 사용자가 제시한 관점에 맞춰, native nginx/Apache에서 worker를 붙이는 운영을 중심으로 설명하되, reverse-proxy shape에서만 의미가 있는 “cache generation mismatch 관측”과 “read leases” 같은 포인트도 같이 끌어옵니다.

## (1) nginx/Apache module + optimizer worker: 매칭 배포와 업그레이드 절차

### 버전 정책: 같은 릴리스의 module/worker를 한 세트로 고정합니다

2.2.0에서는 “module과 worker를 함께, 같은 릴리스로”가 제품 규칙입니다.[^1]

내 경우 이 규칙을 좀 더 강하게 적용합니다.

- OS 패키지 배포를 쓰더라도, repo 최신을 무작정 따라가지 않고 “우리가 승인한 mod_pagespeed 릴리스”를 고정합니다.
- 배포 파이프라인에서 pagespeed 관련 패키지는 nginx 메이저/마이너 업데이트와 묶지 않습니다. 교차 변경을 피하려고 분리합니다.

### nginx: 패키지 설치(예시)와 group 권한

공식 문서는 `packages.modpagespeed.com`의 설치 스크립트로 repo를 추가하고 nginx module 패키지를 설치하는 흐름을 안내합니다.[^3]

```bash
# repo 등록
curl -fsSL https://packages.modpagespeed.com/install.sh | sudo sh

# nginx module (Debian/Ubuntu)
sudo apt-get update
sudo apt-get install -y nginx-module-pagespeed

# optimizer worker
sudo apt-get install -y pagespeed-optimizer

# worker 먼저 기동
sudo systemctl enable --now pagespeed-optimizer
sudo systemctl status pagespeed-optimizer --no-pager
```

worker는 pagespeed 사용자/그룹으로 동작하고, nginx 프로세스가 worker의 소켓/캐시 파일을 읽을 수 있어야 합니다. 문서는 module 설치 시 pagespeed group에 nginx user를 추가한다고 설명하지만, 순서가 꼬였거나 nginx user가 다른 경우에는 직접 추가가 필요합니다.[^3]

```bash
# Debian/Ubuntu의 nginx user가 www-data인 경우
sudo usermod -a -G pagespeed www-data

# 그룹 적용은 프로세스 재시작이 필요
sudo systemctl restart nginx
```

이 작업이 빠지면 nginx는 worker notify socket(`/run/pagespeed-optimizer/notify.sock` 같은)과 cache volume을 열지 못하고, 결과적으로 in-place optimization을 worker로 넘기는 구성이 무력화됩니다. 더 나쁜 경우는, nginx가 부팅 시점에 worker 연결을 시도하다가 장애 증상이 “pagespeed가 갑자기 비활성화됨” 같은 식으로만 보이는 겁니다.

### nginx: server 블록에 worker 연결 지시어를 같이 설정합니다

nginx native module이 worker를 사용하려면 `pagespeed DaemonSocketPath`와 `pagespeed DaemonVolumePath`를 같은 `server` 블록에 함께 설정해야 합니다. 하나만 설정하면 동작하지 않고 에러 로그에 둘 다 필요하다고 남긴다고 문서가 적어둡니다.[^3]

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    pagespeed on;

    # module 자신의 파일 캐시
    pagespeed FileCachePath /var/cache/ngx_pagespeed;

    # worker notify socket + worker cache volume
    pagespeed DaemonSocketPath /run/pagespeed-optimizer/notify.sock;
    pagespeed DaemonVolumePath /var/cache/pagespeed-optimizer/v2/cache;

    # (예시) admin endpoint는 운영망에서만 허용
    location ^~ /pagespeed_admin {
        allow 127.0.0.1;
        allow 10.0.0.0/8;
        deny all;
    }
    location ^~ /pagespeed_global_admin {
        allow 127.0.0.1;
        deny all;
    }
}
```

여기서 중요한 운영 규칙이 하나 더 있습니다.

- `FileCachePath`(module cache)와 `DaemonVolumePath`(optimizer cache)는 다른 경로여야 합니다. 문서가 분리하라고 못 박습니다.[^3]

경로를 섞어 쓰면 “캐시 정리 스크립트가 두 캐시를 같이 날린다” 같은 간접 사고가 생깁니다. 특히 purge를 자동화해둔 환경에서는, purge-all을 어디에 걸었는지에 따라 module/worker 양쪽 동작이 동시에 흔들립니다.

### Apache: 원리는 같습니다(연결면이 config로 감춰질 뿐)

Apache는 패키지 설치 시 module과 worker를 연결하는 설정이 함께 설치된다고 문서가 안내합니다.[^3]

그렇다고 “Apache는 알아서 되겠지”로 두면 안 됩니다. 운영자가 확인해야 하는 건 두 가지입니다.

- 실제로 worker가 떠 있는지(systemd, container, supervisor 무엇이든)
- module이 worker 캐시 볼륨과 같은 세대를 보고 있는지(업그레이드 직후 cache format mismatch 같은 케이스)

확인 자체는 간단하게 시작할 수 있습니다.

- 응답 헤더에 Apache는 `X-Mod-Pagespeed`가 붙고, nginx는 `X-Page-Speed`가 붙는다고 Getting started 문서가 안내합니다.[^5]

```bash
curl -I https://example.com/ | egrep -i 'x-(mod-)?page-speed'
```

헤더가 없으면 “동작 안 함”, 헤더가 있고 `HIT/MISS`가 찍히면 “최소한 파이프라인은 붙어 있음”까지는 확인됩니다.

### 업그레이드 순서: optimizer 먼저, 그 다음 web server

2.2.0에서 이 순서가 중요한 이유는 캐시 포맷/세대가 바뀌는 타이밍에 web server가 worker 캐시를 붙이다가 실패하거나, worker socket이 존재하지만 accept하지 못하는 상태에서 hang에 가까운 지연이 생길 수 있기 때문입니다. 릴리스 노트는 이 경로를 직접 언급하면서, optimizer 먼저 시작하고 web server를 재시작하면 해소된다고 설명합니다.[^1]

운영 절차로는 이렇게 가져갑니다.

1) 패키지 다운로드/검증 단계(서명 repo를 쓰는 형태면 repo 메타 검증)

2) canary 노드에서 optimizer 패키지 업그레이드 → optimizer 기동 확인

3) 같은 노드에서 nginx/Apache 모듈 업그레이드 → web server 재시작

4) 페이지 샘플링 점검(헤더, 에러 로그, cache hit/miss)

5) 전체 롤아웃

여기서 canary의 정의는 “트래픽이 적은 노드”가 아니라 “실제 대표 트래픽을 받는 노드”에 가깝게 잡는 편이 맞습니다. prioritize_critical_css처럼 RUM beacon 기반 최적화가 섞이면, 트래픽 특성이 다르면 결과가 다르게 나옵니다.

## (2) 캐시 공유 환경에서 데이터 유실/행(hang) 방지 포인트

2.2.0 릴리스 노트에는 운영자가 흔히 겪는 두 종류의 문제를 직접 겨냥한 항목이 들어 있습니다.

- 프로세스가 죽거나 잘못된 타이밍에 시작될 때 다른 프로세스가 hang 또는 교착에 가까운 상태로 들어가는 문제
- shared cache에서 optimized copy가 사라져 원본만 계속 서빙되는 문제

이 두 문제는 “성능이 조금 나빠짐”이 아니라, 트래픽 급증과 결합하면 장애 양상으로 보입니다.

### 1) socket 존재하지만 accept 못 하는 상태를 장애로 취급합니다

2.2.0은 “서버 start 또는 config test가 optimizer socket에서 더 이상 hang 하지 않는다”는 수정이 들어갔고, 2초 후 포기하고 in-place optimization through optimizer를 끄고 시작하도록 바뀌었다고 설명합니다.[^1]

이 변경은 안전장치입니다. 하지만 운영 관점에서 바람직한 상태는 아닙니다.

- web server는 떠 있는데 PageSpeed가 worker 경로를 못 타고 있다
- 성능/캐시 hit rate가 갑자기 떨어진다
- 운영자는 “요청은 성공하는데 왜 느려졌지?”로 접근하게 된다

나는 이 상태를 “부분 장애”로 분류합니다. 그래서 systemd를 쓴다면 의존성을 노골적으로 걸어둡니다.

```ini
# /etc/systemd/system/nginx.service.d/pagespeed-optimizer.conf
[Unit]
After=pagespeed-optimizer.service
Requires=pagespeed-optimizer.service

[Service]
# nginx 시작 전에 worker health check를 넣고 싶으면 ExecStartPre를 추가
# (환경에 맞게 /run 소켓 존재, perms, API health 등을 확인)
```

worker가 죽으면 nginx도 같이 내려가게 하는 게 맞냐는 논쟁이 생기는데, 여기서는 정책을 분리합니다.

- 캐시/최적화가 “있으면 좋은 것”이면, nginx는 살아야 합니다(최적화 비활성화로 degrade).
- 캐시/최적화가 “SLO를 맞추기 위한 필수 구성요소”이면, nginx도 같이 fail fast가 맞습니다.

2.2.0이 “hang 대신 in-place optimization off”를 선택한 건 전자 쪽에 더 가깝습니다. 하지만 SLO가 빡빡한 서비스는 후자를 택하는 경우가 많습니다.

### 2) 캐시 포맷 세대 교체(v1 → v2)를 배포 계획에 포함합니다

2.2.0은 cache library가 새 on-disk format으로 이동하며, 기본 cache dir이 `/var/cache/pagespeed-optimizer/v2`로 바뀐다고 명시합니다. 직접 경로를 지정해 쓰고 있었다면 `v1`을 `v2`로 바꾸라고도 적어 둡니다.[^1]

여기서 실전 포인트는 세 가지입니다.

- 업그레이드 직후 cache hit rate가 떨어지는 걸 정상으로 받아들인다.
- 롤백 계획이 있다면 old file을 즉시 삭제하지 않는다(릴리스 노트도 old 파일을 남긴다고 말합니다).[^1]
- 캐시 디렉터리를 버전 경로로 두고, 운영에서는 심볼릭 링크로 가리키는 방식이 정리하기 쉽다.

예를 들어:

- `/var/cache/pagespeed-optimizer/v2/cache`는 실체
- `/var/cache/pagespeed-optimizer/current/cache` 같은 링크를 하나 만들고, config에서는 current를 가리키게 하면, 롤백/실험이 단순해집니다.

다만 이 방식은 “worker와 module이 같은 경로를 참조한다”를 강하게 지켜야 합니다. 경로가 어긋나면 worker는 A 캐시를 만들고, module은 B 캐시를 보게 되는 식의 비가시 오류가 생깁니다.

### 3) shared cache에서 optimized copy가 사라지는 케이스를 관측합니다

2.2.0은 “stylesheet 또는 script에서 optimized copy가 optimizer cache에서 사라졌는데 compressed copy는 남아 있는 경우, 원본이 계속 서빙되던 문제”를 수정했다고 설명합니다. 다음 notification에서 다시 처리하도록 바꿨고, module도 감지하면 다시 요청한다고 합니다.[^1]

이 문제는 보통 이렇게 보입니다.

- 특정 리소스만 최적화가 풀린다
- purge 전까지 계속 원본이 나간다
- 트래픽이 몰릴 때만 재현된다

이걸 운영 지표로 잡으려면, worker API의 notification/error 카운터가 유용합니다. HTTP API 문서에는 `notifications.missing_copy_healed` 같은 항목이 정의되어 있습니다.[^6]

즉, 2.2.0 이후에는 다음을 운영 알림으로 만들 수 있습니다.

- missing_copy_healed가 급증하면 cache volume IO/디스크 오류/외부 purge 자동화 등을 의심한다.
- purge-all 직후 missing_copy_healed가 급증하면 purge 정책이 너무 공격적인지 본다.

### 4) purge-all은 이제 안전해졌지만, 비용 모델은 이해하고 써야 합니다

2.2.0은 purge-all이 다른 읽기/쓰기가 진행 중일 때 optimizer가 crash할 수 있던 문제를 수정했고, purge가 in-flight read/write를 안전하게 피해가며 수행되도록 바뀌었다고 설명합니다. 대신 “너무 늦게 들어온 write는 drop되고, 나중 요청에서 다시 최적화된다”고도 적어둡니다.[^1]

운영 해석은:

- purge-all을 “안전하게 쓸 수 있게 됐다”이지 “마구 쓸 수 있게 됐다”로 받아들이면 안 됩니다.
- purge-all은 캐시 hit rate를 0으로 만들고 worker CPU/IO를 몰아넣습니다.
- 대규모 purge를 배치 잡으로 돌리면, purge 직후 traffic spike와 합쳐져 worker가 병목이 되기 쉽습니다.

내가 보수적으로 가져가는 방식은 이렇습니다.

- purge-all은 사건 대응(취약 리소스 강제 제거, 잘못된 최적화 전파 차단)에서만 사용
- 평상시에는 URL 단위 purge 또는 TTL 기반 자연 소멸을 선호
- purge를 실행하는 자동화는 worker health 및 queue 상태를 보고 동작

### 5) reverse-proxy shape를 쓰면 generation mismatch를 로그로 고정합니다

reverse-proxy shape(thin module)는 worker가 쓴 `pagespeed-shared.conf`를 1초 폴링으로 읽고, cache format generation이 mismatch면 캐시를 꺼버리고 에러 로그를 한 번 남깁니다.[^4]

문서는 mismatch 상태를 `$pagespeed_cache_generation` 같은 변수로 노출합니다.[^4]

```nginx
log_format pagespeed_gen '$remote_addr "$request" $status '
                         'cache_generation=$pagespeed_cache_generation '
                         'm=$pagespeed_cache_generation_module '
                         'o=$pagespeed_cache_generation_optimizer';

access_log /var/log/nginx/access.log pagespeed_gen;
```

native nginx module + worker 모델에서도, 이 관측 철학은 그대로 가져갈 가치가 있습니다.

- “성능이 느려짐”을 보기 전에 “캐시가 붙어 있나?”를 먼저 본다
- 배포 직후에 캐시가 꺼진 상태로 오래 유지되면 즉시 롤백 또는 재배포 판단을 한다

## (3) prioritize_critical_css가 레이턴시에 주는 영향: 측정 방법을 먼저 설계합니다

prioritize_critical_css는 2.2.0에서 “content가 styles 없이 보이지 않게 stylesheets를 로드한다”는 변경으로 강조됩니다.[^1]

이 기능은 단순 minify/concat 계열과 달리, 레이턴시에 대한 영향이 양면적입니다.

- 장점: render-blocking CSS를 비차단 형태로 바꿔서 FCP/LCP를 당길 수 있습니다.
- 단점: critical CSS 추출을 위한 RUM beacon 수집이 필요하고, 잘못 수집되면 스타일 깨짐, CLS 증가, 또는 오히려 늦은 스타일 적용으로 LCP가 악화될 수 있습니다.

문서는 이 필터를 CSS 카테고리로 두고 Risk를 Test first로 표시합니다. 그리고 동작 방식으로 “실사용 방문에서 JavaScript beacon으로 critical CSS 데이터를 수집한다”고 못 박습니다.[^7]

즉, 측정은 lab 한 번으로 끝내면 안 되고, 최소한 아래 세 층을 분리해야 합니다.

- 서버 측: TTFB, 응답 크기, 캐시 HIT/MISS, worker queue/CPU
- 브라우저 측 lab: LCP/FCP/CLS, waterfall, preload 동작
- 브라우저 측 RUM: 실제 사용자 네트워크/디바이스에서 LCP 분포가 어떻게 변하는지

### 1) enable 조건과 검증 포인트

필터는 CoreFilters에 포함되지 않아서 명시적으로 켜야 합니다. nginx에서는 아래처럼 켭니다.[^7]

```nginx
pagespeed EnableFilters prioritize_critical_css;
```

켜자마자 확인할 체크 포인트는 기능 동작 여부가 아니라 안정성입니다.

- `/pagespeed_beacon`류 endpoint가 막혀 있지 않은가(수집이 막히면 학습이 진행되지 않습니다)
- CSP가 너무 빡빡해서 loader script가 막히지 않는가
- HTML 캐시 계층에서 beacon이 잘못 캐시되지 않는가

reverse-proxy shape 문서에는 async CSS loader가 `/pagespeed_static/async_css.<hash>.js` 같은 content-hash 경로로 제공되고, inline onload가 아니라 external loader라서 `script-src 'self'` CSP에서도 동작하도록 설계했다고 설명합니다.[^4]

운영에서는 이 설명이 곧 체크리스트가 됩니다.

- `/pagespeed_static/`를 CDN이나 WAF에서 차단하지 않았는가
- CSP에 self 외에 별도 host를 강제했는데 pagespeed_static이 다른 도메인으로 가는 구조는 아닌가

### 2) 서버 레이턴시(TTFB)와 사용자 체감(LCP)을 분리해서 봅니다

prioritize_critical_css는 “렌더 차단 CSS를 비차단으로 바꾸는 대신, critical rule을 inline으로 넣는다”에 가깝습니다. 따라서 TTFB 자체가 좋아지지 않을 수 있습니다. 오히려 HTML 바이트가 늘면 첫 바이트/전송 완료가 약간 악화될 여지도 있습니다.

내가 측정할 때는 이렇게 자릅니다.

- TTFB는 서버/캐시/worker 병목을 보기 위한 지표
- LCP는 prioritize_critical_css의 실효성을 보기 위한 지표

TTFB만 보면 이 필터는 손해로 보일 수 있고, LCP만 보면 서버가 이미 병목인 상황에서 효과를 과대평가할 수 있습니다.

### 3) 실전 측정 시나리오: cold cache / warm cache를 분리합니다

PageSpeed 계열은 “첫 요청은 원본 서빙 + 백그라운드 최적화 시작, 이후 요청이 캐시에서 HIT”인 progressive 모델을 가집니다. Is it working? 문서도 첫 요청/두 번째 MISS 등을 정상적인 워밍업 현상으로 설명합니다.[^8]

따라서 prioritize_critical_css 평가에서 최소 두 번의 측정이 필요합니다.

- cold: 최적화 캐시가 비거나 flush 직후
- warm: 트래픽이 충분히 지나 최적화가 안정화된 상태

2.2.0 업그레이드 직후에는 캐시 포맷 변경으로 “한 번 비어 시작”이 들어가므로, 배포 직후 지표만 보고 기능을 잘못 판정하기 쉽습니다.[^1]

### 4) 간단하지만 재현 가능한 측정 도구 조합

여기서는 로컬에서 최소 재현 가능한 형태를 제시합니다.

- 부하/TTFB: k6
- lab LCP: Lighthouse CLI
- RUM LCP: PerformanceObserver + beacon(서비스가 이미 쓰는 수집 파이프라인에 붙이는 게 현실적)

#### (a) k6로 TTFB와 캐시 워밍업을 함께 봅니다

k6는 `res.timings.waiting`으로 서버가 첫 바이트를 내기까지 시간을 볼 수 있어, 워커 연결 문제나 캐시 miss 폭증을 빠르게 감지할 수 있습니다.

```javascript
// k6-pagespeed-ttfb.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    warmup: { executor: 'constant-vus', vus: 5, duration: '30s' },
    measure: { executor: 'constant-vus', vus: 20, duration: '2m', startTime: '30s' },
  },
  thresholds: {
    http_req_failed: ['rate<0.001'],
    http_req_waiting: ['p(95)<400'],
  },
};

const URL = __ENV.URL || 'https://example.com/';

export default function () {
  const res = http.get(URL, {
    headers: {
      // 캐시 계층이 있다면 목적에 맞게 제어
      'Cache-Control': 'no-cache',
    },
  });

  check(res, {
    'status is 200': (r) => r.status === 200,
    'has pagespeed header': (r) => r.headers['X-Page-Speed'] || r.headers['X-Mod-Pagespeed'],
  });

  // 필요하면 res.headers의 HIT/MISS 비율도 로그로 남긴다.
  sleep(0.2);
}
```

실행:

```bash
k6 run -e URL=https://example.com/ k6-pagespeed-ttfb.js
```

예상되는 해석:

- 배포 직후 warmup 구간에서 `http_req_waiting`이 높고, 시간이 지나며 낮아지면: 워밍업으로 해석 가능
- 특정 시점부터 waiting이 튀고 `X-Page-Speed`가 사라지면: module/worker 연결, 권한, socket 문제를 의심

#### (b) Lighthouse CLI로 LCP 변화를 반복 측정합니다

Lighthouse는 lab 환경이긴 하지만 “prioritize_critical_css가 렌더 경로를 바꿔서 LCP를 당겼는지”를 보기에는 충분합니다.

중요한 건 같은 조건을 유지하는 겁니다.

- 같은 디바이스 에뮬레이션
- 같은 네트워크 throttling
- 같은 URL(파라미터 포함)
- 같은 캐시 상태(가능하면 측정 전에 워밍업 시퀀스 고정)

```bash
# 예시: 크롬 설치 경로/옵션은 환경에 맞게 조정
npx lighthouse https://example.com/ \
  --only-categories=performance \
  --output=json \
  --output-path=./lh-baseline.json

# prioritize_critical_css enable 후
npx lighthouse https://example.com/ \
  --only-categories=performance \
  --output=json \
  --output-path=./lh-critical-css.json
```

결과 비교는 점수보다 LCP(ms), Total Blocking Time 같은 raw metric을 보는 게 낫습니다. 점수는 가중치가 바뀌면 해석이 흔들립니다.

#### (c) RUM: LCP 분포(p75)를 봅니다

prioritize_critical_css는 문서 그대로 “실사용 방문에서 beacon으로 수집”을 전제로 합니다.[^7]

따라서 운영 판단은 RUM이 최종입니다.

- 배포 전 7일 p75 LCP
- 배포 후 7일 p75 LCP
- 같은 기간의 CLS p75도 같이 봅니다(스타일 적용 타이밍이 바뀌면 CLS가 흔들릴 수 있습니다)

이때 중요한 건 “TTFB와 분리해서” 보는 겁니다. TTFB가 동일하거나 나빠졌는데 LCP가 좋아졌다면 기능이 목표를 달성한 겁니다. 반대로 TTFB만 좋아지고 LCP가 나빠지면, 렌더 경로가 꼬였거나 critical CSS 품질이 낮아진 겁니다.

### 5) prioritize_critical_css가 LCP를 악화시키는 대표적인 패턴

이건 제품 결함이라기보다 “서버 최적화가 애플리케이션과 충돌하는 방식”에 가깝습니다.

- above-the-fold가 사용자 상태에 따라 달라지는 페이지(로그인 여부, AB 테스트, 지역별 배너)
- CSS가 런타임에서 크게 변하는 SPA(초기 HTML은 얇고, JS가 스타일/클래스를 바꾸는 구조)
- CSS가 integrity attribute로 핀 되어 있어 PageSpeed가 건드리지 못하는 리소스가 많은 경우(부분 최적화로 섞임)

이런 페이지에서 prioritize_critical_css는 beacon 기반 학습과 실제 렌더가 어긋나면서 “critical rule이 부족하거나 과도”해지기 쉽습니다. 문서가 Risk를 Test first로 둔 이유가 여기와 맞닿아 있습니다.[^7]

## 보안/신뢰성 업데이트를 운영에 녹이는 체크포인트

2.2.0의 보안 이슈를 보면, 운영자가 실수하기 쉬운 지점이 그대로 드러납니다. “기능 켜고 성능만 보자”로 접근하면 놓칩니다.

### 1) admin endpoint는 path 기반 매칭으로 막지 않습니다

보안 가이드는 `/pagespeed_admin/` 같은 endpoint를 WAF에서 단순 문자열 매칭으로 막는 방식이 우회될 수 있다고 경고합니다. `//`, `/./`, `%2e`, mixed case, trailing slash, `;param` 같은 path normalization 트릭을 언급하면서, nginx라면 `location =` 또는 `^~` 같은 정규화된 location 레벨에서 막으라고 설명합니다.[^9]

그리고 2.2.0 릴리스 노트에는 nginx admin pages에서 access-restriction bypass를 수정했고, 패키징된 snippet과 Admin Console 가이드의 예시도 업데이트되었다고 적혀 있습니다. 업데이트 후 각 `server` 블록에서 규칙을 교체하라고까지 말합니다.[^1]

운영 결론은 간단합니다.

- 2.2.0으로 올릴 때는 “바이너리만 교체”로 끝내지 말고, admin endpoint 접근제어 룰도 같이 교체합니다.

### 2) admin console을 외부에 열었다면 CSRF 성격의 위험을 전제로 봅니다

2.2.0은 admin console의 request forgery 방어를 명시합니다. “다른 사이트에서 admin action trigger가 가능했다”는 종류는 운영에서 흔히 “내부망이니까 괜찮다”로 방치되는 류입니다.[^1]

하지만 실제로는:

- 운영자 브라우저가 내부망에 붙어 있고
- 운영자가 외부 사이트를 열어볼 수 있다면

내부 서비스도 영향을 받을 수 있습니다. 그러니 가장 안전한 선택은 “admin console은 loopback 또는 bastion에서만 접속”입니다.

### 3) optimizer management API는 unix socket + token을 기본으로 둡니다

2.2.0 보안 항목 중 optimizer management API 관련 이슈가 두 가지(DoS, `--api-read-open` 정보 노출) 들어갑니다.[^1]

HTTP API 문서는 token을 환경변수로 넣는 방식을 선호한다고 설명합니다. 커맨드라인 플래그로 토큰을 주면 `/proc/<pid>/cmdline`로 노출될 수 있다는 이유를 명시합니다.[^6]

운영 원칙은 이렇습니다.

- 가능하면 TCP로 열지 말고 unix socket로만 연다
- token은 환경변수로 주고, 프로세스 리스트/로그에 토큰이 남지 않게 한다
- `--api-read-open` 같은 편의 플래그는 기본값이 아니면 더 의심한다

### 4) curl 번들 업데이트는 SBOM/스캔 체계에 넣습니다

2.2.0은 curl 8.22.0으로 번들 HTTPS fetch library를 업데이트했다고 명시하고, 2026-09-02에 공개된 9건의 curl 취약점이 해당 버전에서 수정되었다고 적습니다.[^1]

이건 단순히 “PageSpeed가 업데이트했다”로 끝나면 안 됩니다.

- 보안 스캔 체계에서 “OS 패키지 curl”만 보는 경우, mod_pagespeed 번들 curl은 사각지대가 됩니다.
- reverse proxy나 CDN 계층에서 outbound를 막아도, 내부 fetcher는 origin fetch/재작성에 개입할 수 있습니다.

따라서 mod_pagespeed는 SBOM 관점에서 애플리케이션 종속성이 아니라 서버 종속성으로 등록하는 편이 맞습니다.

### 5) 관측: 문제를 성능 그래프로 보기 전에 상태를 헤더/카운터로 봅니다

운영에서 흔한 실수는 “LCP가 나빠졌네 → 필터를 꺼야 하나?”로 바로 들어가는 겁니다. 먼저 상태를 봐야 합니다.

- 응답 헤더에 `X-Page-Speed` 또는 `X-Mod-Pagespeed`가 붙는지[^5]
- HIT/MISS 비율이 배포 직후 급락했는지(캐시 포맷 변경이면 정상일 수도)
- worker API에서 missing_copy_healed 같은 카운터가 튀는지[^6]

원인이 “필터가 나빠서”가 아니라 “worker 연결이 끊겨서”일 때는, 최적화 기능 토글은 문제를 숨길 뿐 해결이 아닙니다.

## 도입/업데이트 판단 기준

mod_pagespeed 2.2.0을 운영에 넣을지 결정할 때는, 성능 기대치보다 먼저 “운영 비용”을 계산하는 편이 맞습니다.

- 이 컴포넌트는 보안 업데이트 대상입니다(2.2.0 자체가 그 증거입니다).[^1]
- worker를 붙이는 순간, cache volume/notify socket/권한/배포 순서가 서비스 SLO에 영향을 주는 운영 포인트가 됩니다.[^3]
- prioritize_critical_css 같은 기능은 lab 점수가 아니라 RUM 분포(p75 LCP/CLS)로 판정해야 합니다. 문서가 beacon 기반 수집을 동작 원리로 명시하고, Risk를 Test first로 둔 이유가 거기에 있습니다.[^7]

나는 2.2.0을 “성능 플러그인 업그레이드”가 아니라 “서버 컴포넌트 보안/신뢰성 패치”로 취급하고, module과 worker를 같은 릴리스로 묶어 canary→롤아웃을 밟는 쪽이 운영적으로 가장 싸다고 봅니다.

## 참고 자료

- [mod_pagespeed 2.2 릴리스 노트](https://modpagespeed.com/docs/release-notes-2-2/)
- [mod_pagespeed 릴리스 노트 인덱스 및 보안 업데이트 섹션](https://modpagespeed.com/docs/release-notes/)
- [Apache/nginx module 설치 가이드 및 nginx에서 worker 사용 설정](https://modpagespeed.com/docs/installation-module/)
- [Worker 및 reverse-proxy shape 설정 레퍼런스](https://modpagespeed.com/docs/worker-configuration/)
- [prioritize_critical_css 필터 문서](https://modpagespeed.com/docs/filters/prioritize_critical_css/)
- [mod_pagespeed 보안 가이드](https://modpagespeed.com/docs/security/)
- [mod_pagespeed Admin Console 가이드](https://modpagespeed.com/docs/admin-console/)
- [Optimizer worker HTTP API 문서](https://modpagespeed.com/docs/http-api/)
- [oss-security의 curl 8.22.0 advisory 공지](https://openwall.com/lists/oss-security/2026/09/02/2)
- [curl 프로젝트 메일링리스트의 curl 8.22.0 advisory 공지](https://curl.se/mail/lib-2026-09/0001.html)
- [NGINX HTTP/3 구성 의존 CVE 대응 체크리스트](https://daewooki.github.io/posts/nginx-http3-quic-cve-mitigation-checklist/)
- [NGINX 1.31.5: Control API와 njs 리스크가 만나는 지점](https://daewooki.github.io/posts/nginx-control-api-njs-security/)
- [Go 1.27 size-specialized allocations 이후 GC·지연시간 튜닝 관점](https://daewooki.github.io/posts/go-size-specialized-allocations-gc-latency/)

[^1]: <https://modpagespeed.com/docs/release-notes-2-2/>
[^2]: <https://openwall.com/lists/oss-security/2026/09/02/2>
[^3]: <https://modpagespeed.com/docs/installation-module/>
[^4]: <https://modpagespeed.com/docs/worker-configuration/>
[^5]: <https://modpagespeed.com/docs/getting-started/>
[^6]: <https://modpagespeed.com/docs/http-api/>
[^7]: <https://modpagespeed.com/docs/filters/prioritize_critical_css/>
[^8]: <https://modpagespeed.com/docs/is-it-working/>
[^9]: <https://modpagespeed.com/docs/security/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
