---
title: "mod_pagespeed 2.8.0 보안 업데이트: nginx 모듈 재배포 롤아웃 리스크"
description: "성능 모듈 업데이트가 nginx 바이너리·모듈·캐시·재시작까지 흔드는 공급망 변경이 되는 지점을 정리합니다."
date: 2026-11-09 14:46:58 +0900
categories: ["News", "Performance"]
tags: ["mod-pagespeed", "ngx-pagespeed", "nginx", "security", "supply-chain", "rollout"]
render_with_liquid: false
---

## 무슨 일이 있었는지: 2.8.0은 성능 릴리스가 아니라 보안 롤아웃 이벤트입니다

2026-11-05에 mod_pagespeed 2.8.0이 **Security update**로 게시됐습니다. 릴리스 노트의 포지션도 명확합니다. “nginx/Apache/IIS 모듈, optimizer worker, ASP.NET Core 패키지까지 광범위한 보안 수정”이며, “모든 사이트 업데이트 권고”로 시작합니다.[^1]

오늘이 2026-11-09 KST라면 게시 후 4일 지난 시점입니다. 웹서버 모듈은 애플리케이션 패치보다 적용이 늦어지기 쉬운데, 이번 건은 특히 늦어질수록 위험해지는 이유가 있습니다.

- “성능 최적화 모듈”로 받아들이면 손이 느려집니다.
- 실제로는 nginx의 dynamic module(.so) + 패키지 저장소(apt/yum) + 재시작/업그레이드 순서 + 캐시 무효화/CDN purge까지 묶인 **공급망 구성요소**입니다.
- 2.8.0은 패치만 들어간 게 아니라, 배포 타깃이 늘었습니다. Ubuntu 26.04용 native nginx module 패키지가 추가됐고, nginx.org stable용 별도 모듈 패키지(`nginx-module-pagespeed-nginxorg`)가 Debian 13 / Ubuntu 24.04 / EL9까지 확장됐습니다.[^1]

이 조합은 “보안 업데이트를 빨리 적용하려다가 nginx 모듈 체인이 끊기는” 전형적인 사고 패턴을 만들기 쉽습니다.

## 배경과 맥락: mod_pagespeed의 배포 형태가 곧 리스크 프로파일입니다

mod_pagespeed 2.8.0에서 중요한 전제는 “동일 버전으로 모듈과 optimizer worker를 같이 설치한다”는 제품 형태입니다. 릴리스 노트는 2.8.0을 모듈+worker가 함께 릴리스되고 “matching pair로 설치된다”고 못 박습니다. apt/yum 패키지, 컨테이너 이미지, NuGet, Helm chart appVersion이 모두 2.8.0으로 정렬돼 있다는 점도 여기서 나옵니다.[^1]

또 하나의 전제는 nginx 쪽 패키징 모델입니다.

- 배포판 stock nginx에 맞춰 exact-version pin을 건 `nginx-module-pagespeed` (Debian/Ubuntu/EL 계열에서 배포판이 제공하는 nginx 버전에 딱 붙는 모델)
- nginx.org stable에 맞춰 “nginx.org stable 버전 1개당 모듈 빌드 1개”로 내는 `nginx-module-pagespeed-nginxorg` (amd64 중심)[^2]

이 모델은 운영에서 장점도 있지만, 보안 패치 롤아웃 관점에서는 “nginx 업데이트와 모듈 업데이트가 한 덩어리로 움직여야 한다”는 제약을 강제합니다.

그리고 이 제약은 기술적으로 피해갈 수 없습니다. nginx dynamic module은 “같은 nginx 버전에서 빌드된 모듈만 로드 가능”이라는 성질을 갖고 있고, nginx 측 문서/블로그도 버전 체크의 필요성을 명시합니다.[^3]

mod_pagespeed 설치 문서도 직설적으로 씁니다. “nginx는 다른 버전으로 빌드된 모듈 로드를 거부하며 `--with-compat`도 그 체크를 느슨하게 만들지 않는다”는 문장을 운영자가 그대로 받아들이는 게 낫습니다.[^2]

결론은 간단합니다.

- mod_pagespeed 업데이트 = nginx 모듈 체인 업데이트
- nginx 모듈 체인 업데이트 = 재시작/업그레이드 절차 + 검증이 필요

## 왜 중요한지: 2.8.0은 보안 범위가 넓고, 캐시 레이어까지 흔듭니다

### 1) “Restricted content” 계열 이슈는 성능 모듈에서 가장 위험한 부류입니다

2.8.0 릴리스 노트의 보안 섹션 첫 항목은 “Restricted content no longer reaches other clients”입니다. 로그인 사용자/로컬 주소/allow-deny 룰로 제한한 콘텐츠가 최적화 결과물(optimized resources/pages, agent-ready copies)이나 캐시된 응답 형태로 다른 클라이언트에게 섞여 나갈 수 있는 종류의 문제를 직접적으로 언급합니다. 그리고 영향 범위를 “2.7.0 및 이전”으로 잡습니다.[^1]

이건 CVE 번호가 붙었느냐와 별개로, 운영 리스크 기준에서는 최상위입니다.

- 취약점이 “원격 코드 실행”이 아니더라도,
- 데이터 노출은 사고 대응 비용이 더 커질 때가 많고,
- “캐시된 상태로 남아있는 시간”이 곧 노출 창구가 됩니다.

### 2) downstream cache(CDN 포함) purge가 ‘선택’이 아니라 ‘보안 절차’가 됩니다

릴리스 노트는 “Security 섹션에 해당되는 이슈가 있었다면 CDN 같은 downstream cache는 purge하라”는 가이드를 포함합니다. 업그레이드 후에도 CDN이 이전 응답을 들고 있으면 만료될 때까지 그대로 남는다는 현실을 명시합니다.[^1]

즉 2.8.0을 설치만 하고 끝내면, 가장 중요한 종류의 보안 이슈(캐시/최적화 산출물로 인한 교차 노출)가 “이전 캐시 TTL”만큼 계속됩니다.

### 3) 업데이트 1회성 cold start가 성능/비용/오리진 부하로 튑니다

2.8.0은 캐시 키 체계를 바꿔서 “업데이트 시점에 한 번 caches start cold”를 공식적으로 예고합니다. 페이지/stylesheet/script/image가 “첫 요청에서 다시 오리진에서 fetch되고 최적화된다”, 그 동안 CPU와 오리진 fetch 증가, 그리고 일부 응답은 최적화 없이 나갈 수 있다고 적습니다.[^1]

이건 성능 모듈의 보안 업데이트가 비용 이벤트로 변하는 지점입니다.

- 캐시가 cold면 TTFB가 튀고
- 오리진이 동시 fetch를 감당 못하면 오류율이 튀고
- worker/모듈이 리소스를 더 써서 인프라 상한선을 건드릴 수 있습니다

따라서 롤아웃은 “패키지 적용”이 아니라 “캐시 재생성 이벤트”로 계획하는 게 안전합니다.

## 패키지 소스와 nginx 모듈 체인: 어디에서 nginx를 가져오느냐가 설치 전략을 갈라놓습니다

여기부터는 운영자가 먼저 “내 nginx는 어디서 온 것인가”를 확정해야 합니다. 모듈 체인 사고는 대부분 이 지점에서 시작합니다.

### A) 배포판 stock nginx + `nginx-module-pagespeed`

mod_pagespeed 문서가 제공하는 매트릭스는 운영 판단의 기준선으로 쓰기 좋습니다. 예를 들어 Ubuntu 26.04는 stock nginx 1.28.3에 exact-version pin으로 맞춘다고 명시돼 있습니다.[^2]

이 모델에서의 장점은 단순함입니다.

- nginx 업데이트(보안 패치 포함)와 모듈 업데이트가 배포판 리포지토리/서드파티 리포지토리 정책에 따라 함께 움직입니다.
- 다만 함께 움직이지 않을 때(보안 긴급패치 vs 모듈 지연) 충돌이 커집니다.

### B) nginx.org stable + `nginx-module-pagespeed-nginxorg`

nginx.org stable을 쓰는 팀은 보통 “nginx를 최신/일관된 upstream 패키지로 유지하겠다”는 목표가 있습니다. 이 환경에서 배포판 stock nginx용 모듈을 설치하면 모듈 로드 단계에서 바로 깨질 확률이 높습니다(버전 체크에 걸리거나, 운 좋게 로드돼도 런타임에서 터집니다).

mod_pagespeed는 이 케이스를 위해 별도 모듈 패키지(`nginx-module-pagespeed-nginxorg`)를 제공하고, 이 패키지가 “nginx.org stable의 특정 버전에 pinned”된다는 점을 분명히 합니다. 또한 이 패키지는 `nginx-module-pagespeed`와 함께 설치할 수 없다고도 못 박습니다.[^2]

릴리스 노트도 운영 절차를 직접 제시합니다.

- nginx.org가 nginx를 먼저 내면, 업그레이드가 nginx를 hold back해서 모듈이 계속 동작하게 한다.
- nginx 보안 패치를 먼저 당겨야 하면: 모듈을 제거 → nginx 업그레이드 → 모듈이 새 nginx 버전용으로 올라오면 재설치.
- Docker라면 이미지 태그를 “모듈 패키지가 그 버전을 따라왔을 때만” 이동한다.[^1]

이 문장은 사실상 “nginx+모듈 공급망의 동기화 규칙”입니다.

### C) EL9에서 dnf 플러그인으로 nginx hold를 거는 이유

EL9에서는 모듈 패키지가 작은 dnf 플러그인을 설치해서 nginx(및 nginx.org 모듈 패키지들)를 “모듈이 빌드된 버전”에 고정한다고 릴리스 노트에 나옵니다. 평범한 `dnf update`는 다른 업데이트만 적용되고, `dnf check-update`는 nginx 업데이트가 대기 중으로 계속 보이게 됩니다. nginx 보안 패치를 먼저 적용하려면 `dnf upgrade nginx --allowerasing`로 모듈 패키지를 제거하면서 nginx를 올리라고까지 구체적으로 적습니다.[^1]

이건 불편하지만, 사고를 줄이는 방향의 불편입니다.

- nginx를 올렸는데 모듈이 아직 이전 버전이면 nginx가 뜨지 않습니다.
- nginx가 뜨지 않으면 보안 패치 롤아웃이 아니라 장애 롤아웃이 됩니다.

## 롤아웃 리스크를 분해하면 3가지입니다: (1) 바이너리 적합성 (2) 재시작 (3) 캐시 무효화

### 1) 바이너리 적합성: “모듈이 로드되냐”보다 “같은 체인으로 로드되냐”가 중요합니다

nginx dynamic module은 버전 불일치에서 보통 2가지 형태로 실패합니다.

- 시작/리로드 시점에 “모듈이 binary compatible하지 않다” 류로 실패
- 운 좋게 로드돼도, 요청 경로에서 crash/segfault로 실패

nginx 공식 블로그는 버전 체크가 들어간 이유를 “다른 버전으로 컴파일된 모듈을 로드하면 구조체 불일치로 segfault가 난다”는 관점에서 설명합니다.[^3]

또, `--with-compat`는 무슨 만능 스위치가 아닙니다. nginx.org 문서에서 `--with-compat`는 “dynamic modules compatibility를 enable”한다고만 말하지만, 이건 configure 옵션/빌드 옵션 간의 호환성을 조금 넓히는 쪽에 가깝고, 버전 자체가 달라도 된다는 의미로 읽으면 운영에서 바로 사고가 납니다.[^4]

mod_pagespeed 쪽은 더 단호합니다. “nginx는 다른 버전으로 빌드된 모듈 로드를 거부하고 `--with-compat`도 그 체크를 느슨하게 만들지 않는다”가 운영자가 가져가야 하는 결론입니다.[^2]

따라서 “패키지를 설치했다”보다 먼저 해야 하는 검증은 이겁니다.

- nginx가 stock 패키지인지 nginx.org 패키지인지
- 설치하려는 mod_pagespeed 모듈 패키지가 그 nginx 계열에 맞는지
- nginx 버전이 모듈이 기대하는 버전과 동일한지

### 2) 재시작: nginx reload로 끝내려는 습관이 가장 위험합니다

운영에서 자주 나오는 착각은 이렇습니다.

- “모듈 업데이트도 reload면 되지 않나?”

nginx는 dynamic module을 `load_module`로 로드하고, 이 로드 과정은 nginx 프로세스가 모듈 파일을 실제로 메모리에 매핑하는 동작입니다. 그래서 안전한 운영 절차는 “패키지 설치 후 재시작을 전제로 한다”가 됩니다. (무중단이 필요하면 `USR2` 기반 binary upgrade까지 포함한 절차를 별도로 잡아야 합니다.)

여기서 중요한 건 “재시작 자체”가 아니라 “재시작을 컨트롤할 수 있느냐”입니다.

- 롤링 재시작(서버 풀에서 1대씩)
- 커넥션 드레이닝(로드밸런서에서 트래픽 제외 후 재시작)
- 재시작 직후 warm-up(캐시 cold start로 인한 순간 부하를 제어)

### 3) 캐시 무효화: 2.8.0은 캐시 키 변경이 명시된 업데이트입니다

2.8.0은 “새 cache keys 아래로 저장한다”고 공식 문서에 적혀 있습니다. 결과적으로 업데이트 순간에 캐시는 한 번 cold가 되고, 첫 요청마다 오리진 fetch + 재최적화가 발생합니다.[^1]

이건 ‘운영 계획’에서 2개의 체크리스트를 강제합니다.

- (내부) mod_pagespeed/worker 캐시 cold에 대비한 부하 예측
- (외부) CDN purge 또는 TTL 단축 같은 downstream cache 전략

릴리스 노트가 CDN purge를 언급하는 이유도 여기와 이어집니다. 보안 fix가 “캐시된 콘텐츠가 잘못 섞여 나갈 수 있다” 계열이면, 외부 캐시에 남아있는 바이트를 지우는 순간까지가 패치 적용 범위입니다.[^1]

## 실제 적용 전략: “패키지 설치 → 재시작”이 아니라 “공급망 동기화 + 캐시 이벤트 관리”로 본다

여기서는 nginx native module을 설치해 운영하는 전형적인 케이스를 기준으로, 내가 납득하는 안전한 순서를 적습니다.

### 0) 사전 정리: 내 nginx가 어디서 왔는지, 모듈이 어떤 패키지인지부터 확정

다음은 Ubuntu/Debian 계열에서 가장 빨리 현실을 드러내는 커맨드들입니다.

```bash
# nginx가 어떤 configure 옵션으로 빌드됐는지
nginx -V 2>&1 | sed -n '1,3p'

# 동적 모듈 로드 경로/플래그 확인
nginx -V 2>&1 | tr -- - '\n' | grep -E 'with-compat|modules-path|dynamic' || true

# 설치된 pagespeed 관련 패키지 확인
dpkg -l | grep -E 'nginx.*pagespeed|pagespeed-optimizer|mod-pagespeed' || true

# 어떤 repo에서 들어오는지 확인
apt-cache policy nginx nginx-module-pagespeed nginx-module-pagespeed-nginxorg pagespeed-optimizer | sed -n '1,120p'
```

nginx.org 패키지를 쓰면서 `nginx-module-pagespeed`(배포판 stock nginx용)를 설치하려고 하는 순간부터 게임이 꼬입니다. 반대로 배포판 stock nginx를 쓰면서 `nginx-module-pagespeed-nginxorg`를 설치하려고 해도 동일하게 꼬입니다. 설치 문서가 “둘은 같이 설치될 수 없다”고 명시하는 이유가 바로 이 충돌입니다.[^2]

### 1) 2.8.0의 ‘보안 범위’를 이해하고, 패치 적용 후 해야 할 일을 같이 결정

2.8.0은 “여러 클래스의 보안 이슈”를 한 번에 고치는 업데이트이고, 그 중 핵심은 캐시/최적화 산출물의 경계 조건입니다.

- restricted content가 다른 클라이언트로 섞이지 않도록 변경[^1]
- cached content가 site/URL 경계를 넘어가지 않도록 변경(릴리스 노트에 같은 섹션으로 존재)[^1]
- downstream cache purge 권고[^1]

이건 운영 관점에서 “업그레이드 + purge + 모니터링”을 세트로 묶어야 한다는 뜻입니다.

- purge 없이 업그레이드만 하면: 외부 캐시에 남아있는 취약 응답이 계속 서빙될 수 있습니다.
- 업그레이드 없이 purge만 하면: 당연히 의미 없습니다.

### 2) 패키지 신뢰 체인 검증: 서드파티 모듈은 여기서부터 공급망입니다

mod_pagespeed는 packages.modpagespeed.com의 apt/yum 리포지토리가 GPG-signed임을 밝히고, 공개 키 fingerprint까지 제공합니다. fingerprint는 `DF00 E296 BE91 41CE A541 1346 F50D 6054 F107 12A0`로 안내돼 있습니다.[^5]

현장에서 이걸 반드시 매번 하지는 않더라도, 최소한 “처음 도입할 때 / CI 이미지 베이스를 바꿀 때 / 보안 사고 이후”에는 확인하는 게 낫습니다.

```bash
curl -fsSL https://packages.modpagespeed.com/pubkey.gpg -o modpagespeed.asc

gpg --show-keys --with-fingerprint modpagespeed.asc
# expect: DF00 E296 BE91 41CE A541  1346 F50D 6054 F107 12A0

gpg --dearmor < modpagespeed.asc | sudo tee /usr/share/keyrings/modpagespeed.gpg > /dev/null
```

컨테이너 기반이면 cosign 서명/attestation까지 이어갈 수 있는데, 최소한 “서명 있는 채널을 선택한다”는 판단 자체가 팀의 기본값이 돼야 합니다(이건 성능 도구가 아니라 공급망이기 때문입니다). 해당 내용은 mod_pagespeed 지원 문서에서 “GHCR 이미지가 keyless cosign으로 서명되고 SBOM/provenance를 제공한다”고 언급합니다.[^5]

### 3) 업그레이드 순서: nginx와 모듈을 ‘같이’ 올리는 것부터 자동화한다

릴리스 노트가 말하는 운영 규칙은 다음과 같습니다.

- nginx.org stable을 쓰면 nginx와 모듈을 함께 업그레이드하라.
- nginx만 먼저 올라가야 한다면, 모듈을 제거하고 올린 뒤 모듈 빌드가 따라오면 재설치하라.
- Docker는 이미지 태그를 모듈 패키지가 따라왔을 때만 옮겨라.[^1]

이 규칙을 사람 기억에 맡기면 언젠가 깨집니다. 그래서 나는 “업그레이드 가능 조합인지”를 자동 검증하는 스크립트를 둡니다.

아래는 Debian/Ubuntu 기준으로 쓸 수 있는 현실적인 체크입니다.

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1) 어떤 pagespeed nginx 모듈 패키지가 깔려있는지
installed_pagespeed_pkgs=$(dpkg -l | awk '/nginx-module-pagespeed/ {print $2}' | tr '\n' ' ' || true)

# 2) nginx 버전
nginx_ver=$(nginx -v 2>&1 | awk -F/ '{print $2}')

echo "nginx version: ${nginx_ver}"
echo "installed pagespeed pkgs: ${installed_pagespeed_pkgs:-<none>}"

# 3) nginx.org 패키지 감지(완벽하진 않지만 운영에서 유용)
#    - apt-cache policy 출력에 nginx.org 표기가 직접 나오지 않을 수 있어,
#      여기서는 설치된 패키지 버전 문자열/epoch 등을 함께 보고 판단합니다.
apt-cache policy nginx | sed -n '1,40p'

# 4) 동시에 깔린 경우 차단
if echo "$installed_pagespeed_pkgs" | grep -q "nginx-module-pagespeed-nginxorg" && \
   echo "$installed_pagespeed_pkgs" | grep -q "nginx-module-pagespeed"; then
  echo "ERROR: both nginx-module-pagespeed and nginx-module-pagespeed-nginxorg are installed"
  exit 2
fi

# 5) nginx 설정 테스트 (모듈 로드 실패는 여기서 터짐)
nginx -t

echo "OK: nginx -t passed"
```

이 스크립트는 “버전이 정확히 일치하는지”까지는 보장하지 못합니다. 대신 “가장 흔한 사고(모듈 패키지 계열을 잘못 깔아놓는 것)”를 초기에 잘라줍니다.

정밀하게 하려면 `nginx-module-pagespeed-nginxorg` 패키지 버전 문자열이 특정 nginx 버전에 pinned된다는 문서의 힌트를 활용할 수 있습니다(버전 이름에 `+ngx...`가 들어가거나, EL에서는 `nginx = 2:...` 같은 dependency가 걸리는 형태).[^2]

### 4) 재시작 전략: 롤링 + warm-up을 기본값으로 둔다

2.8.0의 cold start 특성 때문에, 재시작 직후 첫 트래픽이 몰리면 오리진 fetch와 최적화 비용이 한 번에 쏠립니다.[^1]

나는 다음 순서를 기본으로 둡니다.

1. (LB) 한 대를 트래픽에서 제외
2. (Host) 패키지 업그레이드
3. (Host) `nginx -t`로 설정/모듈 로드 검증
4. (Host) `systemctl restart nginx` (reload로 끝내지 않습니다)
5. (Host) health check + 핵심 URL warm-up
6. (LB) 트래픽 복귀
7. 다음 노드로 반복

warm-up은 “페이지 몇 개 curl로 두드리는 장난감”이 아니라, 실제 상위 트래픽 URL/critical CSS/이미지 경로까지 포함해야 의미가 있습니다.

예시는 이렇게 둡니다.

```bash
# warmup.txt에는 캐시를 채워야 하는 URL 목록(절대경로)을 넣습니다.
# 예) /, /pricing, /assets/app.css, /assets/app.js, /images/hero.jpg

base="https://example.com"
while read -r path; do
  [ -z "$path" ] && continue
  curl -fsS -o /dev/null -D - "${base}${path}" \
    -H 'Cache-Control: no-cache' \
  | sed -n '1,12p'
done < warmup.txt
```

여기서 `Cache-Control: no-cache`를 붙이는 이유는 “중간 캐시를 경유해 버려서 내 서버 캐시가 안 차는” 상황을 줄이기 위해서입니다. 환경에 따라 CDN이 이 헤더를 무시할 수도 있으니, 그 경우는 오리진 직접 호출 경로를 따로 둡니다.

### 5) CDN purge를 ‘변경 후 옵션’이 아니라 ‘보안 패치 절차’로 포함

릴리스 노트는 downstream cache purge를 분명히 권고합니다. 특히 Security 섹션의 이슈에 해당될 수 있는 사이트는 purge하지 않으면 “업데이트 이전에 저장된 응답이 TTL 동안 계속 제공”됩니다.[^1]

내 기준은 단순합니다.

- 로그인/권한/지역/IP allowlist로 컨텐츠가 달라질 수 있는 사이트라면 purge를 기본값으로 둡니다.
- purge 범위는 HTML만이 아니라, 최적화 산출물(리라이트된 CSS/JS/이미지)까지 고려합니다.
- 다만 purge 폭이 너무 크면 오리진이 터지니, 롤링 재시작과 함께 “도메인/경로별 분할 purge”로 부담을 분산합니다.

릴리스 노트는 또한 “클라이언트 사이드 프레임워크 hydration이 있는 사이트는 CDN에 캐시된 HTML을 purge하라”는 형태로도 언급합니다.[^1]

이건 보안과는 별개로, 업데이트 이후 HTML rewrite 동작이 바뀌면서 hydration 관련 수정이 들어갔기 때문인데(React/Next.js/Vue/Nuxt/Svelte 언급), 운영 관점에서는 “업데이트 이후 특정 페이지가 깨져 보이는” 유형의 장애와 바로 연결됩니다.[^1]

## 반론과 회의론: “pagespeed 같은 건 이제 안 쓰지 않나?”에 대한 현실적인 답

이 주제는 항상 양쪽 극단이 있습니다.

- “mod_pagespeed는 낡았고, 빌드 타임 최적화나 CDN으로 대체 가능하다”
- “여전히 레거시/멀티테넌트/마이그레이션 중인 서비스에선 즉효성 있는 도구다”

둘 다 사실일 때가 많습니다.

다만 2.8.0 같은 업데이트를 다룰 때 중요한 결론은 다른 데 있습니다.

- mod_pagespeed를 쓰는지 여부와 관계없이,
- nginx의 third-party module을 운영에 넣는 순간,
- 그 모듈은 성능 기능이 아니라 **배포/보안/공급망 책임의 일부**가 됩니다.

그래서 “안 쓰는 게 답”이 될 수도 있고 “계속 쓰되 운영 난이도를 감수”가 될 수도 있는데, 어떤 결정을 하든 롤아웃 리스크를 과소평가한 상태로 두면 가장 안 좋은 형태(업데이트 지연 + 급하게 올리다 장애)로 굳습니다.

## 앞으로 지켜볼 것: 2.8.0 이후에는 ‘패키지 동기화 속도’가 보안 대응 속도입니다

릴리스 노트 자체가 “nginx가 먼저 나오면 모듈이 따라올 때까지 hold”라는 운영을 전제로 합니다.[^1]

이 모델에서 앞으로 계속 확인해야 하는 포인트는 세 가지입니다.

1) nginx.org stable 보안 릴리스가 나왔을 때 mod_pagespeed 모듈 패키지가 따라오는 시간

- 따라오는 시간이 길어지면, 운영자는 “nginx 보안 패치를 당겨야 하는데 모듈 때문에 못 올리는” 압박을 받습니다.
- 그 압박이 커질수록, 누군가는 언젠가 “그냥 올려”를 선택합니다.

2) 2.8.0이 예고한 캐시 키 변경/경계 조건 변경이 다음 릴리스에서 또 발생하는지

- 캐시 키 변경은 기능적으로는 깔끔해질 수 있지만, 운영 비용을 동반합니다.
- 특히 멀티 노드에서 warm-up이 어려운 서비스는 비용이 큽니다.

3) 스캐너 기반 이슈(Anthropic OSS Scanner 등)가 계속 다량으로 보고되는지

릴리스 노트는 이번 이슈들이 Anthropic OSS Scanner에 의해 발견되었다고 명시합니다.[^1]

스캐너 기반 보고가 많아지는 건 대체로 좋은 신호지만, 운영자 입장에서는 “패치 주기/캐시 purge 이벤트가 잦아질 수 있다”는 뜻도 됩니다.

## 지금 할 수 있는 일: 2.8.0 적용 체크리스트(nginx native module 기준)

여기서는 “이미 mod_pagespeed를 운영 중”이라는 가정으로 적습니다. 새 도입은 다른 결의 판단이 필요합니다.

### 1) 인벤토리

- nginx가 배포판 stock인지 nginx.org stable인지 확정
- 설치된 패키지가 `nginx-module-pagespeed`인지 `nginx-module-pagespeed-nginxorg`인지 확정[^2]
- optimizer worker(`pagespeed-optimizer`)를 같이 쓰는지 확인(2.8.0은 matching pair 전제)[^1]

### 2) 배포 전 검증 환경에서 “업그레이드 → 재시작 → cold start 부하”를 재현

2.8.0은 cold start가 한 번 발생하는 게 문서에 박혀 있습니다.[^1]

- staging에서 오리진 fetch 증가량
- nginx worker CPU 상승
- 5xx 비율
- 첫 요청에서 최적화가 빠지는 페이지가 있는지

이 네 가지를 최소한 확인하고 롤아웃을 잡는 게 안전합니다.

### 3) 패키지 설치 및 재시작

Ubuntu/Debian 계열 예시입니다.

```bash
sudo apt-get update
sudo apt-get install --only-upgrade nginx-module-pagespeed pagespeed-optimizer

# nginx.org stable을 쓰는 경우는 nginx-module-pagespeed-nginxorg로 바꿉니다.
# sudo apt-get install --only-upgrade nginx-module-pagespeed-nginxorg pagespeed-optimizer

sudo nginx -t
sudo systemctl restart nginx
```

EL9는 릴리스 노트가 말한 “nginx 보안 패치를 먼저 당겨야 할 때의 절차”가 존재합니다. 운영 환경이 해당되면 그 문장을 그대로 런북에 넣는 편이 낫습니다.[^1]

### 4) 업데이트 직후 모니터링 포인트

- `X-Page-Speed` 헤더로 “동작 여부”를 확인하는 습관은 유효합니다. 문서도 nginx 모듈은 `X-Page-Speed`를 사용한다고 정리합니다.[^2]
- 다만 2.7.0부터는 기본값이 `on`이고, 버전 노출은 설정(`ExposeVersionInHeaders`)에 따라 달라집니다. 버전을 헤더로 확인하는 방식에 의존하면 업데이트 이후 관측이 흔들릴 수 있습니다.[^6]
- 캐시 cold start로 인한 오리진 fetch spike는 필수적으로 관측합니다. 이건 성능이 아니라 비용/안정성 문제로 바로 이어집니다.[^1]

### 5) purge/정리

- Security 섹션에 해당 가능성이 있는 사이트는 CDN purge를 패치 절차에 포함합니다.[^1]
- 로컬 캐시는 2.8.0에서 키가 바뀌어 사실상 새로 채워지므로, 디스크 사용량을 본 뒤에 “오래된 캐시 경로 정리”를 별도의 작업으로 잡습니다. 업데이트 당일에 캐시 디렉터리를 수동 삭제하는 건 보통 득이 적고, 오히려 부하를 한 번 더 올릴 때가 많습니다.

기술적으로는 성능 모듈 업데이트지만, 운영에서의 실체는 “nginx 모듈 체인의 보안 패치 + 캐시 경계 조건 수정 + cold start 이벤트”입니다. 이 관점으로 롤아웃을 설계해야 2.8.0 같은 업데이트를 안전하게 흡수할 수 있습니다.

## 참고 자료

- [mod_pagespeed 2.8 릴리스 노트](https://modpagespeed.com/docs/release-notes-2-8/)
- [mod_pagespeed 전체 릴리스 노트와 2.8.0 버전 매핑](https://modpagespeed.com/docs/release-notes/)
- [mod_pagespeed: Apache/nginx 모듈 설치 가이드(nginx.org stable 패키지 포함)](https://modpagespeed.com/docs/installation-module/)
- [mod_pagespeed 지원 문서: 패키지 서명 키 fingerprint와 검증 절차](https://modpagespeed.com/support/)
- [NGINX 블로그: dynamic module 동작과 버전 체크 배경](https://blog.nginx.org/blog/nginx-dynamic-modules-how-they-work)
- [NGINX 블로그: dynamic module 패키징과 버전 매칭 필요성](https://blog.nginx.org/blog/creating-installable-packages-dynamic-modules)
- [NGINX 공식 문서: 빌드 옵션 `--with-compat`](https://nginx.org/en/docs/configure.html)
- [이 블로그: mod_pagespeed 2.2 운영 시 업데이트 안전장치](https://daewooki.github.io/posts/mod-pagespeed-22-nginx-worker-ops/)
- [이 블로그: NGINX HTTP/3 구성 의존 CVE 대응 체크리스트](https://daewooki.github.io/posts/nginx-http3-quic-cve-mitigation-checklist/)
- [이 블로그: NGINX 업그레이드에서 패키지 기준 진실 맞추기](https://daewooki.github.io/posts/nginx-mainline-package-version-source-of-truth/)

[^1]: <https://modpagespeed.com/docs/release-notes-2-8/>
[^2]: <https://modpagespeed.com/docs/installation-module/>
[^3]: <https://blog.nginx.org/blog/nginx-dynamic-modules-how-they-work>
[^4]: <https://nginx.org/en/docs/configure.html>
[^5]: <https://modpagespeed.com/support/>
[^6]: <https://modpagespeed.com/docs/is-it-working/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
