---
title: "PHP2Shell 긴급 패치 런북: PHP 런타임 결함이 운영을 강제할 때"
description: "CVE-2026-109618/109619처럼 PHP 런타임 자체의 unauth RCE는 앱 수정이 아니라 ‘런타임 교체’로 대응해야 합니다."
date: 2026-10-28 13:45:39 +0900
categories: ["News", "Security"]
tags: ["php", "php2shell", "cve", "incident-response", "waf", "container-rebuild"]
render_with_liquid: false
---

## 무슨 일이 있었는지: “앱”이 아니라 PHP 런타임이 깨졌다
2026-10-21(UTC 기준) PHP 프로젝트가 CVE-2026-109618, CVE-2026-109619 두 건을 수정하는 긴급 보안 릴리스를 공개했습니다. 패치가 포함된 업스트림 버전은 **PHP 8.5.12 / 8.4.27 / 8.3.36 / 8.2.35** 입니다.[^1]

이 두 건은 unauth RCE로 분류되고, “PHP2Shell”이라는 이름으로 묶여 유통되었습니다. 특히 중요한 지점은, 프레임워크/애플리케이션 레벨의 인증·권한 체크로 차단할 수 있는 유형이 아니라는 점입니다. 요청이 애플리케이션 코드에 도달하기 전에 PHP 런타임 내부(요청 파싱/요청 정리/워커 재사용 경로)에서 문제가 터질 수 있다고 여러 기관과 벤더가 반복해서 강조했습니다.[^2]

ENISA는 2026-10-21 13:40 UTC에 업데이트가 나왔다고 명시하면서, 조직들이 즉시 조치(자산 식별, 인터넷 노출 우선, 필요시 격리/오프라인)를 취하라고 공동 성명을 냈습니다.[^3]

UK NCSC 역시 같은 날(2026-10-21) 경보(Alert)를 내고, 업데이트가 불가능하면 임시 완화 또는 오프라인까지 포함한 강한 결정을 요구했습니다.[^2]

캐나다 사이버 보안 센터는 2026-10-26에 CISA KEV에 두 CVE가 등재되었다는 업데이트를 포함해(=야생에서 악용되고 있다는 신호를 운영 우선순위로 반영해야 한다는 뜻), 고정 버전으로의 업그레이드를 재차 강조했습니다.[^4]

## 배경과 맥락: 런타임 취약점은 “패치 적용”의 단위가 다릅니다
애플리케이션 취약점(예: 특정 라우트의 SSRF, 특정 컨트롤러의 RCE)은 보통 아래처럼 대응 우선순위가 나뉩니다.

- 취약 라우트를 끄거나 feature flag로 우회
- 특정 파라미터 검증 강화
- WAF로 특정 패턴 차단
- 라이브러리(Composer, npm, pip) 업데이트

반면 런타임 취약점은 대응 단위가 프레임워크가 아니라 “실행 프로세스”입니다. PHP는 SAPI 형태가 다양하고(PHP-FPM, mod_php, php-cgi, LiteSpeed, FrankenPHP 등), 운영자는 애플리케이션이 아니라 이 SAPI가 실제로 요청을 어떻게 받고 어떤 워커 모델로 재사용되는지까지 포함해 봐야 합니다. PHP 측도 ‘웹 요청을 서빙하는 모든 설치가 위험’하다고 못 박았고, 특정 배포 형태(mod_php)를 더 위험하다고 콕 집었습니다.[^1]

여기서 조직이 흔히 실패하는 포인트는 두 가지입니다.

1) “우리 서비스는 Laravel/Symfony/WordPress를 쓰지 않는다” 같은 프레임워크 관점으로 범위를 좁히는 것
- PHP 런타임 취약점은 프레임워크 불문입니다. 정적 페이지를 뿌리는 단순 스크립트여도, PHP 프로세스가 웹 요청을 받는 순간 노출면이 생깁니다.

2) “패키지 업데이트”로 끝낼 수 있다고 착각하는 것
- Composer 업데이트는 PHP 바이너리를 바꾸지 않습니다.
- 컨테이너를 쓴다면 base image 재빌드와 재배포가 필요합니다.
- OS 패키지를 쓴다면 리포지토리 업데이트 + 롤링 재시작이 필요합니다.

이 차이 때문에, 런타임 결함 주간에는 운영팀/플랫폼팀/보안팀이 동일한 런북을 공유하지 않으면 속도가 안 나옵니다.

## 왜 중요한지: “패치 지연 = 인터넷 노출면 리스크”가 되는 구조
이번 케이스는 런타임 결함 중에서도 특히 운영을 강제하는 조건을 갖습니다.

- unauth RCE 성격이라, 인터넷-facing이면 대개 우선순위가 최상위로 올라갑니다.[^1]
- 임시 완화가 “완전한 해결책이 아니다”라는 문구가 공식 권고에 반복됩니다.[^1]
- 공격 타임라인이 패치 공개 전(embargo 기간 포함)으로 당겨질 수 있다는 관측이 나왔습니다(AWS MadPot 텔레메트리 기준 2026-10-17 관측). 즉, “공개 후 N일 내 패치” 같은 기존 SLA 감각이 무너집니다.[^5]

운영 관점에서 더 치명적인 건, 이 유형이 “웹 전체 운영”을 강제한다는 점입니다.

- PHP는 단일 서비스의 일부가 아니라 조직 내 다수 서비스/관리 UI/사내 도구에 광범위하게 깔려 있습니다.
- PHP가 직접적으로 보이지 않는 제품(어플라이언스, 장비 웹 UI, 번들된 관리 포털)에도 숨어 들어갑니다. ENISA와 NCSC가 ‘PHP를 직접 쓰지 않는 것처럼 보이는 제품도 확인하라’고 말한 이유가 여기에 있습니다.[^3]

결국 이 주간의 본질은 보안 이슈가 아니라 운영 이슈입니다. 패치 자체는 쉬워 보여도, “어디를 고쳐야 하는지”와 “교체 단위가 뭔지”를 정리하는 비용이 대부분을 차지합니다.

## 반론과 회의론: 그래도 왜 다들 ‘재빌드’까지 가나
이번 주간에 자주 나오는 반론을 몇 가지로 정리해 보면 아래 같습니다.

### “WAF 룰이 나왔으니 WAF로 막으면 된다”
Cloudflare, AWS WAF처럼 관리형 룰이 빠르게 배포되긴 했습니다. Cloudflare는 Managed Ruleset/Free Ruleset에 관련 룰 ID를 공개하며, 패치 동안 WAF를 켜 두라고 권고합니다.[^6]

AWS도 PHP application managed rule group에 `PHP2Shell_BODY`, `PHP2Shell_BODY_Extended` 룰을 추가했다고 설명합니다.[^7]

다만 두 벤더 모두 결론은 같습니다. WAF는 defense-in-depth이고, 패치는 대체 불가입니다.[^7]

운영 현실에서도 WAF 임시 완화는 “시간을 버는 장치”로는 가치가 있지만, 다음 이유로 종료 조건이 명확해야 합니다.

- 오탐/정탐 튜닝이 필요해 차단 모드 전환에 시간이 걸립니다.
- 공격자가 페이로드를 변형해 우회하는 속도는 WAF 업데이트 속도보다 빠를 수 있습니다(Cloudflare도 공격자가 차단 피드백을 기반으로 변형한다고 언급).[^8]
- 무엇보다 런타임 메모리/워커 상태 문제는 HTTP 레이어 시그니처만으로 100% 모델링이 어렵습니다.

### “공개 PoC는 불안정하다던데, 조금 지켜봐도 되지 않나”
PoC의 완성도는 본질이 아닙니다. unauth RCE + 런타임 결함 조합은 ‘상위 레이어에서 막기 어렵다’는 이유로 늘 최우선입니다. 그리고 AWS는 “공개 전부터 시도 정황이 있다”는 메시지로, 패치/악용 간격이 더 짧아졌다고 주장합니다.[^5]

조직 입장에서는, 성공/실패 여부가 불확실한 시그니처를 기다릴수록 비용이 기하급수로 커집니다. 이럴 때는 기술적인 확률 논쟁보다, 런북을 태워서 “업데이트된 런타임으로 교체”하는 게 가장 싸게 먹힙니다.

### “우리는 컨테이너인데 base image는 안전하지 않나”
컨테이너는 격리 방식일 뿐이고, 이미지 안에 취약한 PHP가 있으면 똑같이 취약합니다. 오히려 컨테이너는 ‘재빌드하지 않으면 영원히 고쳐지지 않는다’는 점에서 더 잔인합니다.

- 태그가 `php:8.3-fpm` 같은 moving tag라면, CI가 이미지를 다시 빌드하지 않는 한 바뀐 베이스가 반영되지 않습니다.
- 태그를 digest로 고정해 두었다면, 정책상 더 안전하지만 이번 주간에는 반드시 digest를 갱신해야 합니다.

## 앞으로 지켜볼 것: 패치가 끝이 아닌 이유
이번 건은 2026-10-21 패치 버전으로 끝나지 않고, 운영팀이 계속 모니터링해야 할 갈래가 생겼습니다.

- NCSC-NL은 php2shell 관련 운영 정보를 GitHub 레포로 계속 업데이트하고, 번들/어플라이언스 제품 목록도 관리합니다(특히 “PHP가 숨어 있는 제품” 추적에 유용).[^9]
- PHP는 2026-10-23에 session upload progress 관련 추가 안내(정보성 권고)를 냈고, `session.upload_progress.enabled=0` 유지 같은 운영 결정을 요구합니다.[^1]
- KEV 등재처럼 운영 우선순위를 바꾸는 이벤트가 며칠 뒤에 추가로 들어올 수 있습니다(캐나다 센터는 2026-10-26 KEV 등재를 업데이트로 반영).[^4]

이제 본론으로 들어가서, 런북 관점에서 조직이 어떤 순서로 움직여야 하는지 정리합니다.

## 런북 전체 흐름: 자산 식별 → 버전 매트릭스 → 재빌드/교체 → 임시 완화 → 검증/롤백
런타임 취약점 대응에서 가장 중요한 건 “순서를 고정”하는 일입니다. 순서가 흔들리면, 온 조직이 동시에 달리다가 결국 아무것도 완료하지 못한 상태가 됩니다.

내가 운영에서 반복해서 본 추천 순서는 아래입니다.

1) 자산 식별(Inventory): 어디에 PHP가 있는지, 어떤 SAPI로 웹 요청을 받고 있는지
2) 버전 매트릭스(Matrix): 고쳐야 하는 목표 버전과, 각 배포 단위(패키지/이미지/어플라이언스)의 갱신 경로
3) 패키지/이미지 재빌드(Rebuild) 및 교체(Deploy): PHP 바이너리가 바뀐 아티팩트를 만들어 전파
4) WAF/임시 완화(Compensating Controls): 배포 대기 시간을 줄이고, 인터넷 노출면을 임시로 좁힘
5) 검증/롤백(Verify & Rollback): “고쳐졌다”를 증명하고, 장애 시 빠르게 되돌릴 장치 확보

이 순서를 따라가면, 누가 어떤 일을 언제까지 해야 하는지가 명확해집니다.

## 1) 자산 식별: PHP가 “실행되는 곳”을 찾아야 합니다
NCSC가 “오래된 버전만 찾지 말고 PHP 설치 자체를 찾으라”고 적은 게 핵심입니다.[^2]

자산 식별은 두 겹으로 나눠야 합니다.

- PHP 바이너리/라이브러리 존재 여부(설치된 곳)
- 그 PHP가 외부 요청을 실제로 서빙하는지(노출된 곳)

### 서버(VM/Bare metal)에서 빠르게 ‘실행 중인 SAPI’ 찾기
아래 명령은 “프로세스 기준”으로 확인합니다. 패키지 DB만 보면 컨테이너/번들/정적 빌드 같은 예외를 놓칠 수 있습니다.

```bash
# 1) 흔한 PHP 프로세스가 떠 있는지
ps auxww | egrep -i 'php-fpm|apache2|httpd|litespeed|openlitespeed|frankenphp|php-cgi' | grep -v egrep

# 2) 웹서버가 PHP를 어떻게 붙이고 있는지(대표 케이스)
# nginx + php-fpm
nginx -T 2>/dev/null | egrep -n 'fastcgi_pass|php\.conf|\.php' | head

# apache + mod_php 또는 proxy_fcgi
apachectl -M 2>/dev/null | egrep -i 'php|proxy_fcgi|mpm'

# 3) 현재 CLI php 버전(단, 이것만 믿으면 안 됨)
php -v

# 예상 출력 예시
# PHP 8.3.35 (cli) (built: ...)
# -> 이번 이슈에서는 8.3.36 이상이 목표
```

여기서 함정은, `php -v`가 보여주는 CLI 버전과 실제 php-fpm/Apache module 버전이 다를 수 있다는 점입니다. 특히 다음 케이스는 자주 발생합니다.

- 서버에 PHP가 여러 버전 공존(8.1, 8.2, 8.3 동시 설치)
- php-fpm은 8.2인데 CLI는 8.3
- Apache는 mod_php(8.1)로 올라가 있는데 운영자는 php-fpm만 보고 있다

그래서 프로세스 경로 기반으로도 확인합니다.

```bash
# php-fpm 바이너리 경로 확인
readlink -f "$(command -v php-fpm 2>/dev/null)" || true

# systemd 유닛으로 실제 실행 바이너리 확인(배포판마다 이름이 다름)
systemctl status php*-fpm 2>/dev/null | sed -n '1,25p'

# Apache가 mod_php를 쓴다면 로딩 모듈 확인
apachectl -M 2>/dev/null | grep -i php
```

### 컨테이너/Kubernetes에서 ‘실제 이미지 태그/다이제스트’까지 수집
컨테이너 환경에서는 “노드에 설치된 PHP”가 아니라 “이미지에 들어간 PHP”가 전부입니다. 따라서 자산 식별의 최소 단위는 아래처럼 잡는 편이 안전합니다.

- (namespace, workload, container name, image reference, rollout 방식)

예시로, K8s에서 PHP가 들어 있는 컨테이너를 대충이라도 훑는 스크립트는 이렇게 시작합니다.

```bash
# 모든 네임스페이스의 이미지 목록을 수집
kubectl get pods -A -o json \
  | jq -r '.items[]
    | .metadata.namespace as $ns
    | .metadata.name as $pod
    | .spec.containers[]
    | [$ns, $pod, .name, .image]
    | @tsv' \
  | column -t \
  | tee pods-images.tsv

# 이미지 문자열에 php가 들어간 것만 1차 필터 (완벽하진 않지만 시작점)
awk '$4 ~ /php|wordpress|drupal|joomla|laravel|symfony|nextcloud|magento/i {print}' pods-images.tsv > suspect.tsv
```

하지만 문자열 필터는 놓치는 게 많습니다. 결국은 런타임 확인이 필요합니다.

```bash
# php -v를 컨테이너에서 직접 실행(php 바이너리가 있는 경우만)
# 운영 환경에서는 canary namespace나 제한된 RBAC로만 수행하는 게 안전합니다.
while read -r ns pod cname image; do
  echo "== $ns/$pod ($cname) $image"
  kubectl exec -n "$ns" "$pod" -c "$cname" -- sh -lc 'php -v 2>/dev/null | head -n 2' || true
done < <(awk '{print $1, $2, $3, $4}' suspect.tsv)

# 예상 출력 예시
# PHP 8.4.26 (cli) ...
# -> 이번 이슈에서는 8.4.27 이상이 목표
```

여기까지가 “어디에 있는지”입니다. 다음은 “무엇으로 올릴지”를 매트릭스로 고정합니다.

## 2) 버전 매트릭스: ‘고정 버전’과 ‘배포 단위’를 같은 표로 묶습니다
PHP 공식 권고는 매우 단순합니다.

- 업스트림 소스 기준: 8.5.12 / 8.4.27 / 8.3.36 / 8.2.35로 업데이트[^1]

문제는 실전에서 “업스트림 버전 문자열과 일치하지 않는 패키징”이 흔하다는 점입니다.

- 배포판 백포트: `8.2.34-1ubuntu...`처럼 보이지만 CVE 패치가 백포트된 빌드일 수 있음
- 벤더 번들: 제품이 PHP를 내장하고 있고, 사용자는 PHP를 직접 업데이트할 수 없음
- 컨테이너: 이미지 tag는 `myapp:2026-10-01`인데 내부 PHP가 8.3.35일 수 있음

그래서 매트릭스는 “PHP 버전”이 아니라 “교체 가능한 아티팩트 단위”로 만듭니다.

추천 컬럼(최소)은 아래입니다.

- 자산 ID(서비스/클러스터/제품)
- 노출면(Internet-facing / Internal / Admin-only)
- 실행 형태(SAPI: PHP-FPM, mod_php, php-cgi, LiteSpeed, FrankenPHP 등)
- 현재 상태(현재 PHP 버전 또는 패키지 버전/이미지 digest)
- 목표 상태(8.5.12/8.4.27/8.3.36/8.2.35 중 무엇으로 갈지, 또는 벤더 핫픽스 버전)
- 교체 방법(apt/yum, 이미지 재빌드, Helm upgrade, 어플라이언스 펌웨어)
- 소유 팀(오너)
- 완료 조건(버전 확인 + 워커 재시작 + 로그 모니터링)

그리고 이번 이슈는 mod_php의 위험도가 더 높다고 공식 자료에 반복되므로, 매트릭스에서 mod_php를 별도 플래그로 표시하는 편이 좋습니다.[^1]

추가로, NCSC-NL 레포의 software list는 “어떤 상용 제품이 PHP를 번들하는지”를 찾는 데 꽤 도움이 됩니다. 매트릭스 초안을 만든 뒤, 해당 목록에 자사 사용 제품이 있는지 대조해서 빠진 자산을 메우는 방식이 효과적입니다.[^9]

## 3) 패키지/이미지 재빌드: 런타임 취약점의 실질적인 ‘패치 적용’
공식 발표에서 반복되는 문장이 있습니다. “업데이트만이 완전한 해결책”입니다.[^1]

여기서 업데이트는 서비스 코드 업데이트가 아니라, PHP 바이너리가 바뀐 상태로 프로세스가 다시 떠야 한다는 뜻입니다.

- 패키지 기반이면: 패키지 업데이트 + php-fpm/Apache 재시작
- 컨테이너면: 이미지 재빌드 + 롤아웃
- 서버리스(예: Bref 같은 런타임 레이어)이면: 런타임 레이어/이미지 업데이트 + 재배포

### Dockerfile 레벨에서 “업데이트가 반영되게” 만드는 패턴
아래는 Debian 계열에서 `php:8.3-fpm` 베이스를 쓰는 전형적인 예시입니다. 핵심은 “베이스 이미지를 바꾼 뒤, 애플리케이션 레이어만 얹는 방식”으로 재빌드가 가능하도록 하는 것입니다.

```Dockerfile
# 예시: PHP 8.3 FPM 기반
# 목표: 베이스가 8.3.36으로 올라간 이미지를 다시 빌드해 배포
FROM php:8.3-fpm-bookworm

# 운영에서 흔히 쓰는 확장 설치 예시
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git unzip; \
    docker-php-ext-install opcache; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY composer.json composer.lock /app/
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer \
 && composer install --no-dev --prefer-dist --no-interaction --no-progress

COPY . /app

# healthcheck를 걸어두면 롤아웃 검증이 쉬워집니다.
HEALTHCHECK --interval=30s --timeout=3s CMD php -v | head -n 1
```

재빌드와 검증은 아래처럼 “버전 문자열을 CI에서 강제”하는 게 좋습니다.

```bash
# 빌드
docker build -t registry.example.com/myapp:php2shell-fix .

# 로컬에서 버전 확인
docker run --rm registry.example.com/myapp:php2shell-fix php -v | head -n 1

# 예상 출력
# PHP 8.3.36 (cli) ...
```

이걸 하지 않으면, 재배포가 완료됐는데도 내부 PHP가 그대로인 “헛바퀴 배포”가 나옵니다. 런타임 이슈 주간에는 이런 실수가 가장 비쌉니다.

### Kubernetes 롤아웃에서 중요한 건 ‘완료’가 아니라 ‘교체’입니다
K8s에서 `Deployment`가 Available 상태라고 해서 안전하진 않습니다.

- 오래된 파드가 termination grace 기간 동안 남아 있을 수 있음
- php-fpm 워커가 살아 있는 동안 요청을 계속 받을 수 있음
- HPA가 붙어 있으면, 스케일 인/아웃 타이밍에 취약 파드가 다시 늘어날 수 있음

그래서 런북 완료 조건에 아래를 넣습니다.

- `kubectl rollout status` 성공
- 모든 파드의 이미지 digest가 기대값과 일치
- 파드 내부 `php -v`가 기대값과 일치(샘플링이든 전수든 정책화)

## 4) WAF/임시 완화: 패치를 “대체”하지 않고 “버퍼”를 만듭니다
PHP는 “업데이트만이 완전한 해결책”이라고 쓰면서도, 현실적으로 즉시 업데이트가 불가능한 조직을 위해 임시 완화 가이드를 같이 제공합니다.[^1]

임시 완화는 두 층으로 나눠 보는 게 안전합니다.

- PHP 런타임 설정(메모리/세션/백트레이스/워커 재시작)
- 경계 장비/프록시/WAF에서 요청 형태를 제한

### (A) PHP 런타임 설정 기반 임시 완화(공식 권고)
공식 권고의 성격을 요약하면 아래처럼 분리됩니다.

- CVE-2026-109618(OOM corruption): 메모리 고갈 조건을 공격자가 만들기 어렵게
- CVE-2026-109619(stale state): 특정 트리거 경로(session upload progress 등)를 닫고, 워커 재사용에서 남는 상태를 줄이게

PHP 보안 권고에 명시된 임시 완화 항목 중 운영에서 실제로 만지는 것만 뽑으면 아래입니다.[^1]

- `memory_limit=-1`를 “앱이 override 못하는 위치”에 강제(FPM pool의 `php_admin_value` 등)
- `post_max_size`를 낮추고, `upload_max_filesize`는 그보다 더 낮게
- (CVE-109619 경로) `session.upload_progress.enabled=0` 설정 후 **모든 워커 재시작**
- (PHP 8.5) `fatal_error_backtraces=0` 설정 후 **모든 워커 재시작**
- 요청마다 적용되는 잘못된/폐기된 ini 설정을 제거(.htaccess, per-dir ini, 잘못된 PHP_VALUE 등)

FPM pool 설정 예시는 아래처럼 갑니다.

```ini
; /etc/php/8.3/fpm/pool.d/www.conf 같은 위치
php_admin_value[memory_limit] = -1
php_admin_value[session.upload_progress.enabled] = 0

; 업로드를 쓴다면 운영 요구에 맞게 조정
php_admin_value[post_max_size] = 32M
php_admin_value[upload_max_filesize] = 16M
```

적용 후에는 반드시 워커를 갈아엎습니다.

```bash
sudo systemctl restart php8.3-fpm
# 또는 컨테이너면 롤아웃으로 교체
```

여기서 중요한 운영 포인트는, 임시 완화는 “설정 적용 + 재시작”까지가 한 묶음이라는 점입니다. stale state 유형은 특히 재시작이 빠지면 효과가 반감됩니다.

### (B) Cloudflare/AWS WAF 같은 관리형 룰은 ‘즉시성’이 장점입니다
Cloudflare는 php2shell 관련 룰을 Managed Ruleset/Free Ruleset로 배포하면서, 룰 ID까지 공개했습니다. 이런 투명성은 운영자가 변경 여부를 감사하기 좋습니다.[^6]

AWS는 PHP application managed rule group에 php2shell 룰이 포함됐고(버전 고정 시 업데이트 필요), multipart 차단/바디 사이즈 제한/세션 업로드 필드 기반 차단을 조합하라고 가이드합니다.[^7]

다만 운영자가 기억해야 하는 결론은 하나입니다.

- WAF는 “패치 창(patch window)”을 줄이는 도구이고, 패치가 끝나면 방어선을 보조하는 장치로 격하되어야 합니다.[^7]

### (C) reverse proxy 레벨에서 multipart를 줄이는 건 효과가 큽니다
AWS도 두 취약점이 `multipart/form-data` 처리 루트와 연관되어 있어서, 업로드가 없는 앱이면 아예 multipart를 막는 게 강한 완화라고 설명합니다.[^7]

Nginx에서 “업로드가 필요 없는 경로에 대해” 강제하는 예시는 아래처럼 갑니다.

```nginx
# 업로드가 없는 서비스라면 전역 차단도 가능하지만,
# 대개는 특정 location에만 적용하는 편이 안전합니다.

location / {
  # 기본적인 바디 크기 제한
  client_max_body_size 1m;

  # multipart 차단(업로드 안 쓰는 경우)
  if ($content_type ~* "multipart/form-data") {
    return 415;
  }

  include fastcgi_params;
  fastcgi_pass unix:/run/php/php8.3-fpm.sock;
  fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
}
```

이런 완화는 장애를 부르기 쉽습니다. 결제/회원가입/프로필 사진/CS 첨부 같은 기능이 multipart를 쓰는 경우가 많아서, “모든 경로 차단”은 운영 사고로 이어질 수 있습니다. 그래서 런북에서는 반드시 매트릭스에 “업로드 필요 여부”를 컬럼으로 넣고, 업로드가 없는 서비스부터 경계 차단을 강하게 넣는 식으로 우선순위를 나눕니다.

## 5) 검증: 패치 적용의 증거를 남기고, 침해 여부를 같은 창에서 확인합니다
NCSC는 업데이트/완화가 늦어졌다면 침해 증거 점검도 함께 하라고 명시합니다.[^2]

내 경험상 이 단계에서 실수가 많이 나옵니다. 이유는 간단합니다.

- 배포 완료를 “조치 완료”로 착각
- 버전 확인을 “일부 서버만” 하고 종료
- 오래된 워커가 남아 있는 걸 놓침

검증을 런북으로 만들 때는 아래를 분리합니다.

### (A) 런타임 교체 검증(필수)
- php-fpm이면: 모든 fpm 워커가 재시작 되었는지(재시작 시각, PID 교체)
- Apache mod_php면: Apache가 재시작 되었는지 + 로드된 모듈이 기대 버전인지
- 컨테이너면: 모든 파드가 새 이미지 digest인지

버전 확인은 “HTTP로 노출되는 PHP” 기준으로 하는 편이 안전합니다. 운영에서 흔히 쓰는 방법은 `/__health/php-version` 같은 엔드포인트를 만들어 `phpversion()`만 반환하고, 내부에서만 접근되게 막아두는 것입니다. 다만 이 글에서는 실제 서비스 코드 변경을 요구하지 않는 방향으로, 컨테이너 내부 `php -v` 샘플링을 기본으로 둡니다.

### (B) 임시 완화 검증(패치 지연 시 필수)
- `session.upload_progress.enabled=0`이 적용됐는지
- `post_max_size`, `upload_max_filesize`가 기대값인지
- 웹서버/프록시에서 multipart 차단이 의도대로 동작하는지

### (C) 침해 점검(패치 완료와 별개로 필요)
이번 케이스는 “공개 전 시도” 가능성까지 언급되었기 때문에, 조직의 관측 시작점을 disclosure date로 잡으면 늦습니다. AWS는 MadPot 기준 관측 시작일을 최소 2026-10-17로 잡으라고 말합니다.[^5]

AWS 글에는 관측된 IOC IP도 포함되어 있지만, 공유 인프라일 수 있으니 무작정 차단보다 “관측 여부 확인”에 쓰는 편이 안전하다고 적습니다.[^5]

운영자가 즉시 할 수 있는 로깅 기반 점검 예시는 아래 정도가 현실적입니다.

```bash
# (1) multipart 업로드에서 자주 관측되는 키워드(세션 업로드 진행 필드)를 로그/보안 로그에서 찾기
# 환경마다 로그 형식이 다르니 문자열 기준으로만 시작합니다.

grep -R --line-number --ignore-case 'PHP_SESSION_UPLOAD_PROGRESS' /var/log/nginx /var/log/apache2 /var/log/httpd 2>/dev/null | head

# (2) 웹 루트/업로드 디렉토리에 최근 생성된 의심 파일(운영 환경에 맞게 경로 조정)
find /var/www -type f -mtime -14 \( -name '*.php' -o -name '*.phtml' -o -name '*.phar' \) -printf '%TY-%Tm-%Td %TT %p\n' 2>/dev/null | tail

# (3) 프로세스 실행 흔적(php-fpm이 shell을 띄우는 건 대부분 비정상)
ps auxww | egrep -i 'php-fpm|apache2|httpd' | head
# 여기에 /bin/sh, curl, wget 같은 게 붙는다면 따로 조사로 분리합니다.
```

이 단계에서 욕심내면 안 됩니다. “이번 CVE의 완벽한 탐지”는 대부분 불가능합니다. 대신 런북에서는 아래를 목표로 둡니다.

- (필수) 런타임이 패치 버전으로 교체되었음을 증명
- (선택) 공개된 관측 포인트(의심 필드/비정상 프로세스/최근 파일 변경)로 1차 triage
- (필수) 의심이 나오면 IR 절차로 분기(증거 보존, 포렌식, 계정 회수 등)

## 6) 롤백: 런타임 패치 롤백은 ‘버전’이 아니라 ‘아티팩트’로 합니다
런타임 보안 패치는 급하게 들어가서, 예상치 못한 호환성 문제가 터질 수 있습니다.

- 특정 extension ABI 문제
- 이미지 재빌드 과정에서 OS 라이브러리까지 올라가며 부수 변화 발생
- php.ini 기본값 차이로 인한 성능/세션 동작 변화

그래서 롤백은 “이전 PHP 버전으로 내린다”가 아니라, “이전 아티팩트로 되돌린다”가 되어야 합니다.

- 패키지 기반: 패키지 버전 downgrade는 종속성 지옥이 될 수 있으니, 가능하면 snapshot/이미지 기반 롤백(AMI, 이미지 레지스트리 태그)로 가는 게 낫습니다.
- 컨테이너: 이전 이미지 digest로 롤백(태그가 아니라 digest 권장)

그리고 이번 케이스는 공식 문서에서 “완전한 완화는 업데이트뿐”이라고 못 박았기 때문에, 보안 관점의 롤백은 조직이 감당 가능한 리스크를 문서로 승인받지 않으면 실행하면 안 됩니다. 운영 장애가 있더라도 보안적으로 원복이 어려운 패턴입니다.[^1]

현실적인 절충안은 다음입니다.

- 배포 장애 시: PHP 자체를 내리기보다, 트래픽 우회(maintenance), 기능 플래그(업로드 차단), WAF 강화로 서비스 연속성을 확보
- 정말로 롤백해야 한다면: 인터넷 노출을 줄이거나(차단/화이트리스트/VPN), 내부망으로만 내린 뒤 원인 분석

## 지금 할 수 있는 일: 24~72시간을 ‘교체 작업’으로 쓰는 체크리스트
여기부터는 계획 문서가 아니라 실행 체크리스트에 가깝게 정리합니다.

### T+0~2시간: 범위 확정과 우선순위 고정
- 인터넷-facing에서 PHP를 “실제로 웹 요청에 사용”하는 자산을 1차 식별(프로세스/Ingress 기준)
- mod_php 사용 여부 플래그 처리(위험도 상향)
- 목표 고정 버전(8.5.12/8.4.27/8.3.36/8.2.35)을 기준점으로 매트릭스 생성[^1]

### T+2~8시간: 아티팩트 재생산(재빌드)과 임시 완화 병행
- 컨테이너: 베이스 이미지 업데이트 반영 재빌드, `php -v` CI 게이트 추가
- 패키지: 업데이트 리포지토리 반영 확인 후 롤링 업데이트 계획 수립
- WAF: Cloudflare/AWS WAF 같은 관리형 룰은 가능한 한 빨리 Count/Log → Block로 전환(오탐 확인 후)[^6]
- 업로드가 없는 앱은 reverse proxy에서 multipart 차단으로 노출면 축소[^7]

### T+8~24시간: 배포 완료의 ‘증거’ 만들기
- 버전/이미지 digest/재시작 여부를 서비스별로 증빙(스크린샷이 아니라 커맨드 출력/로그로 남김)
- 패치 지연 자산은 임시 완화 적용 + 워커 재시작까지 완료 조건으로 묶기[^1]

### T+24~72시간: 남는 구멍 메우기
- 번들/어플라이언스 계열은 NCSC-NL 소프트웨어 목록을 참고해 벤더 공지 추적, 펌웨어/핫픽스 적용 계획 확정[^9]
- 로그 기반 triage로 침해 의심 시 IR로 분기(특히 2026-10-17~2026-10-21 구간 포함)[^5]

## 정리: 런타임 취약점 대응의 목표는 “패치”가 아니라 “교체 완료를 증명”하는 것입니다
CVE-2026-109618/109619 대응은 PHP 코드를 고치는 작업이 아니라, 취약한 PHP 런타임이 더 이상 요청을 받지 못하게 만드는 교체 작업입니다. 자산 식별과 버전 매트릭스를 먼저 고정하지 않으면, 재빌드/배포/WAF/검증이 전부 제각각 진행되어 속도도 품질도 나오지 않습니다. 이번 주간에 조직이 얻어야 하는 결과물은 “패치했다”는 선언이 아니라, 어떤 아티팩트가 어떤 경로로 어떤 시각에 교체되었는지까지 남긴 운영 기록입니다.

## 참고 자료
- [PHP 2026 뉴스 아카이브: 보안 권고 및 고정 버전 안내](https://www.php.net/archive/2026.php)
- [ENISA 공동 성명: Critical PHP vulnerabilities 즉시 조치 권고](https://www.enisa.europa.eu/news/joint-statement-on-critical-php-vulnerabilities)
- [UK NCSC 경보: Critical security issue affecting PHP](https://www.ncsc.gov.uk/news/critical-security-issue-affecting-php)
- [캐나다 사이버 보안 센터 경보(AL26-026): 고정 버전 및 KEV 등재 업데이트](https://www.cyber.gc.ca/en/alerts-advisories/al26-026-critical-vulnerabilities-impacting-php-cve-2026-109618-cve-2026-109619)
- [NCSC-NL php2shell 운영 정보 레포(제품 번들 목록 포함)](https://github.com/NCSC-NL/php2shell)
- [Cloudflare 블로그: php2shell WAF 보호 배포 및 룰 ID](https://blog.cloudflare.com/php-vulnerabilities-waf-protection)
- [AWS Security Blog: AWS WAF로 php2shell 완화 적용](https://aws.amazon.com/blogs/security/using-aws-waf-to-apply-mitigations-for-php2shell-rce-vulnerabilities-cve-2026-109618-and-cve-2026-109619/)
- [AWS Security Blog: MadPot에서 본 공개 전 시도 타임라인](https://aws.amazon.com/blogs/security/amazon-threat-intelligence-identifies-php2shell-exploitation-prior-to-public-disclosure-in-madpot/)
- [Datadog Security Labs 분석: 앱 인증으로 막을 수 없다는 재현 및 완화 한계](https://securitylabs.datadoghq.com/articles/php2shell-critical-vulnerabilities-in-php/)

[^1]: <https://www.php.net/archive/2026.php>
[^2]: <https://www.ncsc.gov.uk/news/critical-security-issue-affecting-php>
[^3]: <https://www.enisa.europa.eu/news/joint-statement-on-critical-php-vulnerabilities>
[^4]: <https://www.cyber.gc.ca/en/alerts-advisories/al26-026-critical-vulnerabilities-impacting-php-cve-2026-109618-cve-2026-109619>
[^5]: <https://aws.amazon.com.cdn.amazon.com/blogs/security/amazon-threat-intelligence-identifies-php2shell-exploitation-prior-to-public-disclosure-in-madpot/>
[^6]: <https://blog.cloudflare.com/php-vulnerabilities-waf-protection/?ref=securinglaravel.com>
[^7]: <https://aws.amazon.com/blogs/security/using-aws-waf-to-apply-mitigations-for-php2shell-rce-vulnerabilities-cve-2026-109618-and-cve-2026-109619/>
[^8]: <https://www.techradar.com/pro/security/aws-says-hackers-tried-to-exploit-php-security-issues-days-before-fix-as-cloudflare-ceo-says-it-saw-a-huge-rise-in-targeted-attack-attempts>
[^9]: <https://github.com/NCSC-NL/php2shell>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
