---
title: "Drupal 코어 보안 릴리스를 정기 배포 이벤트로 운영하기"
description: "PSA로 예고된 코어 보안 릴리스를 Composer 잠금·스테이징 검증·롤백/DB 마이그레이션 관리로 반복 가능한 배포 이벤트로 만든다."
date: 2026-10-19 13:11:25 +0900
categories: ["OpenSource", "Drupal"]
tags: ["drupal", "composer-lock", "security-release", "drush", "deployment"]
render_with_liquid: false
---

## 2026-10-14 코어 보안 릴리스: 예고(PSA)와 실제 릴리스가 남긴 운영 힌트

Drupal Security Team은 2026년 10월 12일에 PSA-2026-10-12를 게시하면서, **2026년 10월 14일 16:00~21:00 UTC** 사이에 지원 중인 모든 코어 브랜치에 대한 보안 릴리스를 예고했습니다.[^1]

시간대부터 운영 관점에서 정리해 두는 편이 좋습니다.

- 예고된 릴리스 윈도우: 2026-10-14 16:00~21:00 UTC[^1]
- 한국 시간(KST, UTC+9)으로는: 2026-10-15 01:00~06:00 KST
- 사용자가 적어 준 “오늘 2026-10-19 KST” 기준으로는, 이 릴리스는 이미 끝났고(2026-10-15 KST 새벽), 실제 advisory도 공개된 상태입니다.

PSA 자체는 세부 취약점 내용은 비공개로 유지하면서(Disclosure policy), 영향을 받는 지원 브랜치(Drupal 11.4.x / 11.3.x / 10.6.x)와 위험도(19/25), 그리고 “몇 시간~며칠 내 exploit이 개발될 수 있으니 그 시간대에 업데이트 시간을 확보하라”는 요청을 명시했습니다.[^1]

릴리스 후 공개된 코어 advisory를 보면, 같은 날짜(2026-10-14)에 코어에서 최소 3개의 advisory가 함께 나왔습니다.

- SA-CORE-2026-014: Field UI 모듈 관련 Remote code execution, CVE-2026-108097. 코어만으로는 직접 exploit이 어렵지만 contrib 모듈 조합에서 심각한 exploit path가 존재하며, 최소 1개 path는 인증이 필요 없다고 설명합니다. 임시 완화책으로 `field_ui` 언인스톨을 제시하고, 수정 버전은 Drupal 11.4.10 / 11.3.19 / 10.6.19 입니다.[^2]
- SA-CORE-2026-015: Link 모듈 관련 XSS, CVE-2026-108515. 수정 버전은 동일하게 11.4.10 / 11.3.19 / 10.6.19 입니다.[^3]
- SA-CORE-2026-016: Navigation 모듈 관련 XSS, CVE-2026-108514. 공격 조건(특정 권한 필요)까지 포함해 설명하며, 수정 버전은 동일합니다.[^4]

운영 관점에서 핵심은 “무슨 취약점이었나”보다, **예고형 릴리스가 팀 프로세스를 설계할 수 있는 시간을 준다**는 점입니다. PSA는 공개 전까지 기술 정보가 비어 있으니, 준비 기간에 할 수 있는 일은 자연스럽게 “테크니컬 디테일 조사”가 아니라 “업데이트 윈도우를 안전하게 열기 위한 반복 가능한 절차 정리”로 수렴합니다.

이 글의 목표는 Drupal 보안 릴리스를 긴급 패치로만 취급하지 않고, 매달(또는 예고가 뜨는 경우) 반복 가능한 **정기 보안 배포 이벤트**로 다루기 위한 실전 운영 설계를 정리하는 것입니다.

## Drupal 코어 보안 릴리스는 원래 ‘윈도우 기반’으로 움직입니다

Drupal은 보안 릴리스를 아무 때나 내지 않습니다. Security Team 가이드에는 코어 보안 릴리스가 보통 한 달에 한 번(대개 세 번째 수요일), 그리고 보안 릴리스가 올라오는 시간대가 16:00~22:00 UTC라고 명시돼 있습니다.[^5]

또한 PSA(공개 서비스 공지)는 아무 때나 나오지 않고, “매우 치명적/치명적 이슈에서 월요일에 PSA를 내고 수요일 릴리스를 예고하는 경우가 있다”는 프로세스가 문서화돼 있습니다.[^6]

이 특성 때문에 Drupal 운영에서 가장 비용이 큰 실수는 보통 두 가지로 나뉩니다.

1) 보안 릴리스를 “갑자기 떨어지는 긴급 작업”으로만 취급해서, 업데이트 준비(검증/승인/롤백 계획)가 매번 즉흥적으로 만들어지는 경우

2) 반대로 “정기 배포는 분기별/월별로 충분하다”는 관성 때문에, 코어 보안 릴리스 윈도우에 맞춘 업데이트 시간을 확보하지 못하는 경우(PSA가 그걸 방지하려고 나온 겁니다)[^1]

코어 보안 릴리스는 구조적으로 릴리스 윈도우가 존재하고(16:00~22:00 UTC), 예고형 PSA는 그 윈도우에 맞춰 팀이 캘린더/체인지 프로세스를 미리 열라는 신호입니다.[^5]

따라서 운영 목표는 다음처럼 바뀌어야 합니다.

- “사고가 나면 밤새 패치”가 아니라,
- “수요일 윈도우에 배포할 준비가 된 상태를 만들고, 수요일에 배포하고, 배포 후 검증까지 한 번의 리허설처럼 끝낸다”

이 방향으로 가면, PSA는 공포 마케팅이 아니라 **배포 시스템을 테스트할 수 있는 리허설 일정 공지**가 됩니다.

## Composer 잠금: 업데이트를 ‘결정’하는 곳과 ‘재현’하는 곳을 분리합니다

Drupal을 production에서 운영한다면, 보안 릴리스 당일에 production 서버에서 `composer update`를 돌리는 순간부터 변수가 폭증합니다.

- 패키지 해석(resolution)은 네트워크/레포 상태/플러그인/캐시 영향을 받습니다.
- 같은 커밋이라도 `composer update`는 그 시점에 허용되는 최신 의존성으로 움직입니다.
- 보안 릴리스는 코어만 바뀌지 않고, 코어 메타패키지/스캐폴드/메시지 패키지가 같이 움직이며, 기여 모듈이 얽히면 해석 결과가 예상과 다르게 퍼집니다.

Drupal 공식 문서도 production에서는 `composer update`가 아니라 `composer install --no-dev`를 권장합니다. 즉, 업데이트 결정은 dev/staging에서 하고, production은 lockfile을 기반으로 재현만 하라는 뜻입니다.[^7]

Drupal의 “Deploying a Drupal update” 문서는 더 노골적입니다. 로컬에서 업데이트 후 테스트하고, 서버에서는 업데이트된 `composer.lock`가 정의하는 상태를 `composer install`로 재현하라고 씁니다.[^8]

여기서 핵심 산출물은 **composer.lock**입니다.

- 변경을 만들 때: `composer update` 또는 `composer require ... --update-with-all-dependencies`로 lockfile을 갱신
- production에 반영할 때: lockfile을 커밋/배포하고, 서버에서는 `composer install`로 동일 상태를 재현[^8]

### drupal/core-recommended를 유지하는 이유

Drupal 문서는 `drupal/core-recommended`를 기준으로 업데이트 절차를 설명합니다. 이 패키지는 “의존성 대부분을 patch-level로 제한해서 안정성을 극대화”하는 목적이라고 명시돼 있습니다. 반대로 `drupal/core`는 의존성까지 더 넓게 움직일 수 있어, 더 많은 테스트 책임을 팀이 떠안게 됩니다.[^7]

보안 릴리스 운영을 이벤트화하려면, 릴리스 당일의 불확실성을 줄이는 쪽이 유리합니다. 그래서 내 기준은 단순합니다.

- 특별한 이유(특정 dependency minor를 땡겨야 하는 상황)가 없다면 `drupal/core-recommended`를 유지한다.
- 예외적으로 `drupal/core`로 잠깐 이동했다면, 목적을 달성한 뒤 다시 `drupal/core-recommended`로 돌아온다(문서도 “일시적” 사용을 권장합니다).[^9]

### PSA가 뜬 시점(T-2일)에 해야 할 Composer 작업

PSA는 “10월 14일 전에 각자의 브랜치에서 최신 patch(bugfix) 릴리스까지 미리 올려 두라”고 권합니다. 보안 릴리스 자체를 최소 변경으로 만들기 위해서입니다.[^1]

이 말은 프로세스적으로는 다음을 뜻합니다.

- 월요일(PSA 게시)~수요일(릴리스 윈도우) 사이에는 “보안 릴리스 적용”만 남기고 싶다.
- 그러려면 수요일 이전에 이미 최신 patch까지 따라온 상태여야 한다.

현실에서는 항상 그렇게 못 합니다. 그래도 원칙은 유지하되, 운영 runbook을 “최악의 날에도 처리 가능한 단위”로 쪼개야 합니다.

- 월요일~화요일: (가능하다면) 현재 minor에서 최신 patch까지 사전 업그레이드
- 수요일 윈도우: 보안 릴리스 patch 적용 + DB update + smoke test + 모니터링

## 스테이징 검증: production 복제 + lockfile 재현 + DB 업데이트까지 ‘한 번에’ 끝냅니다

보안 릴리스가 진짜로 위험한 이유는, 취약점 자체도 있지만 “패치가 공개된 뒤 exploit이 빠르게 따라온다”는 운영 현실 때문입니다(PSA도 그 점을 적시합니다).[^1]

그래서 스테이징 검증은 길게 하지 못합니다. 대신 목표를 바꿔야 합니다.

- 기능 테스트 전체를 다 하겠다는 욕심을 버리고
- 배포 실패/업데이트 실패/롤백 실패를 막는 데 집중합니다

내가 Drupal 코어 보안 릴리스에서 스테이징을 쓰는 방식은 거의 고정돼 있습니다.

1) production DB snapshot을 스테이징에 복원
2) production과 동일한 lockfile 기반으로 `composer install`을 강제
3) Drupal 업데이트(특히 DB 업데이트)를 production과 같은 명령으로 실행
4) 최소 smoke test + 로그 확인

Drupal 문서에서 production 배포 단계는 서버에서 `composer install`로 lockfile을 재현하고, 그 다음 Drupal 업데이트를 수행하라고 설명합니다.[^8]

그리고 Drush의 `deploy` 커맨드는 이 과정을 표준화합니다. 문서에 따르면 `drush deploy`는 대략 아래 흐름을 수행합니다.

- `drush updatedb`
- `drush cache:rebuild`
- `drush config:import`
- `drush cache:rebuild`
- `drush deploy:hook`

이 순서가 문서에 그대로 박혀 있다는 점이 중요합니다. 팀 합의 없이도, runbook에 박아 넣기 쉬운 기준점이 됩니다.[^10]

### 스테이징에서 확인해야 하는 것은 “취약점 재현”이 아니라 “업데이트 경로 안정성”

이번 SA-CORE-2026-014는 Field UI 모듈의 RCE이고, 코어만으로는 직접 exploit이 어렵지만 contrib 조합에서 심각한 경로가 있을 수 있다고 씁니다.[^2]

이 타입의 이슈는 보통 두 가지 위험이 같이 옵니다.

- 패치 공개 후 공격자들이 diff를 보고 자동화
- 사이트별로 설치된 contrib/커스텀 코드 조합에 따라 실제 공격 가능성이 달라짐

따라서 스테이징의 핵심은 “우리 사이트 조합에서 exploit이 가능한가”를 규명하는 게 아니라, **patch를 가장 빨리 안전하게 적용할 수 있는 배포 경로를 확보**하는 데 있습니다.

- lockfile 변경이 production에서 그대로 재현되는지
- `drush updatedb`가 무사히 끝나는지
- config가 바뀌는지(바뀐다면 export/import 경로가 정상인지)
- 캐시 rebuild 이후에 치명적인 error가 없는지

Drupal 문서도 코어 업데이트 후 `drush updatedb`와 `drush cache:rebuild`를 수행하라고 안내하고, config management를 쓰는 경우 DB 업데이트 후 config export가 필요할 수 있다고 말합니다.[^7]

## DB 마이그레이션과 롤백: Drupal에서는 ‘DB를 되돌리는 능력’이 곧 배포 속도입니다

Drupal 보안 릴리스 운영에서 팀이 가장 자주 착각하는 지점이 “코드만 되돌리면 된다”입니다. Drupal은 업데이트 과정에서 DB schema/config 상태가 바뀔 수 있고, 그 변화는 일반적으로 자동 롤백이 제공되지 않습니다.

Drupal 공식 업데이트 가이드도 업데이트 전에 백업을 권장하고, Drush로 `drush archive:dump` 또는 `drush sql:dump` 같은 백업 방식을 언급합니다.[^7]

내 경험상 코어 보안 릴리스에서 롤백 설계를 할 때는, 롤백을 3계층으로 나눠야 사고가 줄어듭니다.

1) Code rollback: 직전 배포 artifact(또는 git tag)로 되돌리기
2) Dependency rollback: `composer.lock` 기준으로 vendor까지 동일하게 되돌리기
3) DB rollback: snapshot restore

여기서 1)과 2)는 생각보다 쉽습니다. 진짜 어려운 건 3)입니다.

- RDS snapshot, LVM snapshot, ZFS snapshot 같은 인프라 레벨 snapshot이 있으면 롤백 시간이 짧아집니다.
- 인프라 snapshot이 없다면 `drush sql:dump` 기반 restore를 해야 하는데, 사이트 DB 크기가 크면 배포 윈도우 안에 못 끝나는 경우가 많습니다.

결론적으로 Drupal 보안 배포를 이벤트화하려면, DB 복구 시간을 예측 가능한 수준으로 만들지 못하는 순간부터 운영이 무너집니다. 배포 실패에 대비해 rollback을 빠르게 할 수 있어야, 패치 적용을 주저하지 않게 됩니다.

### 이번 이슈의 “임시 완화책”은 운영 결정의 힌트입니다

SA-CORE-2026-014는 임시 완화책으로 Field UI 모듈(`field_ui`) 언인스톨을 제시합니다.[^2]

이런 완화책이 문서에 등장한다는 건, 실제 운영에서는 다음 상황이 자주 발생한다는 의미입니다.

- 보안 릴리스가 떴는데, 지금 당장 업데이트를 못 한다(의존성 충돌, 배포 승인, DB 작업 시간 부족)
- 그렇다고 방치할 수는 없다

이럴 때 임시 완화책은 “기술적인 회피”라기보다 “업데이트를 끝내기 위한 시간을 버는 운영 옵션”입니다. 다만 언인스톨은 사이트마다 영향이 다르니, 평소에 다음 질문에 답을 준비해 두는 게 맞습니다.

- 우리 production에서 `field_ui`가 켜져 있는가?
- 켜져 있다면, 지금 끄면 누구에게 어떤 영향이 생기는가(편집자/관리자 워크플로우)?
- 언인스톨이 가능한가, disable만 가능한가, 혹은 권한으로 대체 가능한가?

이 질문은 이번 이슈에만 유효한 게 아니라, “보안 릴리스 때 임시 완화책이 주어졌을 때 우리 팀이 어떤 속도로 결정을 내릴 수 있나”를 측정하는 지표가 됩니다.

## 프로덕션 업데이트 윈도우를 안전하게 여는 배포 절차(런북)

여기서는 Drupal 공식 가이드가 말하는 큰 흐름(로컬에서 업데이트 → lockfile 배포 → 서버에서 `composer install` → Drupal 업데이트)을 그대로 가져가되, 실제 운영에서 필요한 gate를 추가합니다.[^8]

### 0) 전제: production에서 바뀌면 안 되는 것

- production에서 dependency resolution을 하지 않는다. 즉 `composer update`를 금지한다.
- production에서 수정 커밋을 만들지 않는다. 즉 `composer.lock`는 배포 artifact에 포함된다.
- 업데이트 실행 명령은 사람이 기억하지 않고 스크립트로 고정한다.

이 전제가 깨지는 순간, 보안 릴리스는 이벤트가 아니라 복구 작업이 됩니다.

### 1) 릴리스 윈도우 전에 만들어 두는 브랜치/태그

- `release/security-YYYYMMDD` 브랜치 생성
- production 직전 커밋을 `prod-pre-YYYYMMDD-HHMM` 같은 태그로 남김
- 배포 artifact를 남길 수 있다면(이미지/패키지), 배포 전 artifact도 함께 보관

태그는 기술적으로는 단순하지만, DB 롤백이 필요한 상황에서 “어느 코드로 되돌릴지” 결정 시간을 줄입니다.

### 2) dev(또는 스테이징)에서 보안 릴리스 버전으로 lockfile을 만든다

이번 릴리스는 advisory에 수정 버전이 명시돼 있습니다.

- Drupal 11.4.x라면 11.4.10
- Drupal 11.3.x라면 11.3.19
- Drupal 10.6.x라면 10.6.19[^2]

Drupal 문서에는 특정 버전으로 pin 하는 `composer require ... --update-with-all-dependencies` 예시가 있습니다. 이 패턴을 그대로 사용하면 “릴리스 당일에 무엇으로 올릴지”를 사람이 해석하지 않아도 됩니다.[^7]

아래는 drupal/recommended-project 계열(`drupal/core-recommended`, `drupal/core-composer-scaffold`, `drupal/core-project-message`)을 쓰는 프로젝트에서 바로 실행 가능한 형태입니다.

```bash
# (예) 현재 프로젝트가 Drupal 11.4.x 라인이라면
composer require \
  drupal/core-recommended:11.4.10 \
  drupal/core-composer-scaffold:11.4.10 \
  drupal/core-project-message:11.4.10 \
  --update-with-all-dependencies

# vendor/bin/drush가 프로젝트 로컬에 설치돼 있다는 가정
vendor/bin/drush status
vendor/bin/drush updatedb -y
vendor/bin/drush cache:rebuild
```

예상 출력(환경마다 값은 달라집니다):

```text
$ vendor/bin/drush status
Drupal version   : 11.4.10
Site URI         : http://localhost
DB driver        : mysql
...

$ vendor/bin/drush updatedb -y
 [notice] Update started...
 [notice] Update completed.

$ vendor/bin/drush cache:rebuild
 [success] Cache rebuild complete.
```

핵심은 출력의 exact text가 아니라, 이 단계에서 아래 산출물이 생겨야 한다는 점입니다.

- `composer.lock` 변경
- (필요시) scaffold 파일 변경
- (DB 업데이트 후) config export가 필요한 변화 감지

스캐폴드 변경은 drupal-composer/drupal-project 쪽에서도 업데이트 절차에서 “scaffolding 파일 변경을 리뷰하고, 코어 업데이트와 함께 한 커밋으로 묶어 동기화를 유지하라”고 강조합니다.[^11]

### 3) 스테이징에서 production과 동일한 방식으로 검증한다

여기서 중요한 건 “스테이징에서 composer update를 돌려서 성공했다”가 아닙니다.

- 스테이징 서버는 production과 같은 방식으로 배포돼야 합니다.
- 즉, lockfile 기반 `composer install`로 재현돼야 합니다.[^8]

스테이징에서의 실행은 다음처럼 고정합니다.

- 코드 배포(artifact 또는 git checkout)
- `composer install --no-dev` (서버 정책에 따라 옵션은 조정)
- `drush deploy -y` 또는 최소한 `drush updatedb -y && drush cache:rebuild`

Drush `deploy` 커맨드를 채택하면, DB 업데이트/캐시/설정 반영 순서를 runbook에서 논쟁할 필요가 줄어듭니다.[^10]

## 실제로 굴러가는 형태의 배포 스크립트(Composer 잠금 + Drush deploy)

아래 스크립트는 “production에서 lockfile을 재현하고, DB 업데이트와 config import까지 한 번에 수행”하는 형태입니다. Drupal 문서가 말하는 배포 구조(서버에서 `composer install`, 이후 Drupal 업데이트 수행)를 정면으로 반영합니다.[^8]

가정:

- Drupal 프로젝트 루트에 `composer.json`, `composer.lock`, `vendor/`가 위치
- Drush는 프로젝트 로컬 의존성(`vendor/bin/drush`)으로 설치
- 웹 루트는 `web/`
- PHP/Composer는 서버에 설치돼 있으며, production에서는 `composer install`만 수행

### scripts/prod-deploy-security-release.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/drupal-app}"
PHP_BIN="${PHP_BIN:-php}"
COMPOSER_BIN="${COMPOSER_BIN:-composer}"
DRUSH_BIN="${DRUSH_BIN:-${APP_DIR}/vendor/bin/drush}"

cd "$APP_DIR"

# 1) (선택) 현재 버전 기록
"$DRUSH_BIN" status || true

# 2) maintenance mode (업데이트 동안 편집/쓰기 방지)
"$DRUSH_BIN" state:set system.maintenance_mode 1 -y
"$DRUSH_BIN" cache:rebuild

# 3) lockfile 기반으로만 재현
# Drupal 문서에서 production에서는 composer update가 아니라 install을 권장합니다.
"$COMPOSER_BIN" install --no-dev --prefer-dist --no-interaction --no-progress

# 4) DB update + cache + config import를 표준 순서로
# Drush deploy는 updatedb/cache/config import/cache/deploy hook 순서를 표준화합니다.
"$DRUSH_BIN" deploy -y

# 5) maintenance mode 해제
"$DRUSH_BIN" state:set system.maintenance_mode 0 -y
"$DRUSH_BIN" cache:rebuild

# 6) 배포 후 상태 확인
"$DRUSH_BIN" status
"$DRUSH_BIN" watchdog:show --count=20 || true

echo "OK: security release deployed"
```

예상 출력(요약):

```text
$ ./scripts/prod-deploy-security-release.sh
 Drupal version : 11.4.10
 ...
 [success] Cache rebuild complete.
 Loading composer repositories with package information
 Installing dependencies from lock file
 ...
 [notice] Starting Drupal deployment.
 [notice] Done: updatedb
 [notice] Done: config:import
 [notice] Done: deploy hooks
 OK: security release deployed
```

이 스크립트의 장점은 단순합니다.

- 사람이 릴리스 당일에 해야 하는 행동이 “스크립트 실행”으로 수렴합니다.
- 실패하면 실패 지점이 로그로 남습니다.
- 성공하면 maintenance mode on/off까지 포함한 작업이 일관됩니다.

단점도 분명합니다.

- DB 업데이트가 느리면 maintenance window가 길어집니다.
- `config:import`가 예상치 못한 충돌을 일으키면(특히 사람 손으로 production에서 설정을 바꾼 팀) 배포가 터집니다.

그래서 이 구조는 “평소에 config drift를 막는 팀”일수록 잘 맞습니다.

## 자주 터지는 함정: partial update, scaffold 충돌, EOL 브랜치

### 1) partial update로 lockfile이 꼬이면 보안 릴리스 당일에 시간이 증발합니다

Composer에서 일부 패키지만 업데이트하다가 core 관련 패키지(`drupal/core-*`)의 버전이 엇갈리면, 보안 릴리스 때 해석 문제가 터집니다.

Drupal 문서가 코어 업데이트를 `composer update "drupal/core-*" --with-all-dependencies`로 안내하는 이유가 여기 있습니다. 코어 패키지군을 한 번에 움직여야, lockfile이 일관된 상태로 갱신됩니다.[^7]

실무에서는 다음 규칙을 강제하는 편이 낫습니다.

- 코어 보안 릴리스가 떴다: `drupal/core-*`는 한 덩어리로 업데이트
- contrib 업데이트는 별도 커밋으로 분리(가능하다면)

### 2) scaffold 파일 충돌은 “한 번 겪고 나면” 매번 나옵니다

drupal-composer/drupal-project는 코어 업데이트 시 scaffold 파일이 바뀔 수 있고, `.htaccess` 같은 파일을 커스터마이즈했다면 merge conflict를 해결해야 한다고 강조합니다. 그리고 코어 업데이트와 scaffold 변경을 한 커밋으로 묶어 동기화를 유지하라고 권합니다.[^11]

보안 릴리스 운영에서는 이 문제를 두 단계로 분리하는 편이 안전합니다.

- 첫째, scaffold 커스터마이즈를 최대한 줄입니다.
- 둘째, 꼭 커스터마이즈가 필요하면 변경 지점을 파일 상단/하단으로 몰아서 diff/merge 비용을 줄입니다.

이건 기술 이슈라기보다 “릴리스 윈도우에 맞춰 움직이기 위한 부채 관리”입니다.

### 3) EOL 브랜치는 보안 릴리스 이벤트 자체가 성립하지 않습니다

PSA는 지원 브랜치(11.4/11.3/10.6)만 언급하고, 그 이전은 EOL이라 지원되지 않는다고 명시합니다.[^1]

SA-CORE-2026-014 역시 Drupal 11.2.x 이하, Drupal 10.5.x 이하가 EOL이라 보안 커버리지가 없다고 적습니다.[^2]

이 상태에서는 runbook을 아무리 잘 만들어도 결론은 하나입니다.

- 보안 릴리스 때마다 “지원 브랜치로의 upgrade”가 함께 들어오고,
- 그 순간 보안 릴리스는 정기 이벤트가 아니라 큰 프로젝트가 됩니다.

운영에서 lifecycle을 끌어올리지 못하면, 보안 배포 이벤트화는 불가능합니다. 이 감각은 Python EOL을 맞으면서 멀티 런타임 운영이 강제되는 경험과도 닮아 있습니다[^12].

## 도입 판단 기준: 보안 릴리스를 이벤트로 만들면 무엇이 바뀌나

보안 릴리스를 이벤트로 만드는 작업은, “문서 하나 써서 공유”로 끝나지 않습니다. 실제로는 다음 체질 개선이 뒤따릅니다.

- production 변경은 lockfile 중심으로만 이루어진다(`composer install` 중심 배포)[^8]
- DB 롤백 시간(RTO)을 줄이기 위해 snapshot 체계를 갖춘다
- 스테이징이 production과 배포 방식까지 동일해야 의미가 생긴다
- Drush deploy 같은 표준 커맨드를 채택해, 사람이 실수할 여지를 줄인다[^10]

이 비용을 감당할 가치가 있는지 판단하려면, “이번 취약점이 얼마나 위험했나”보다 “우리 조직이 업데이트 속도를 확보하지 못했을 때 비용이 얼마나 커지나”를 봐야 합니다.

Drupal의 PSA는 exploit이 릴리스 후 수 시간~수일 내 등장할 수 있으니 그 시간대에 업데이트 시간을 확보하라고 말합니다.[^1] 즉, 업데이트 속도 자체가 보안의 일부라는 선언입니다.

이번 2026-10-14 릴리스는 결과적으로 Field UI RCE(CVE-2026-108097)와 XSS 두 건을 포함했고, 수정 버전이 11.4.10/11.3.19/10.6.19로 명확히 떨어졌습니다.[^2] 이런 날에 조직이 우왕좌왕하지 않으려면, 보안 릴리스를 기술 이슈가 아니라 배포 시스템의 반복 훈련 대상으로 취급하는 편이 맞습니다.

## 참고 자료

- [PSA-2026-10-12: Upcoming critical Drupal core release on October 14, 2026](https://www.drupal.org/psa-2026-10-12)
- [SA-CORE-2026-014: Drupal core - Critical - Remote code execution](https://www.drupal.org/sa-core-2026-014)
- [SA-CORE-2026-015: Drupal core - Moderately critical - Cross-site scripting](https://www.drupal.org/sa-core-2026-015)
- [SA-CORE-2026-016: Drupal core - Moderately critical - Cross-site scripting](https://www.drupal.org/sa-core-2026-016)
- [Drupal Security Advisories 목록](https://www.drupal.org/security/p)
- [Security release numbers and release timing](https://www.drupal.org/drupal-security-team/security-release-numbers-and-release-timing)
- [Security advisory process and permissions policy](https://www.drupal.org/node/475848)
- [Updating Drupal core via Composer](https://www.drupal.org/docs/updating-drupal/updating-drupal-core-via-composer)
- [Deploying a Drupal update](https://www.drupal.org/docs/updating-drupal/deploying-a-drupal-update)
- [Drush deploy command](https://www.drush.org/12.1.2/deploycommand/)
- [drupal-composer/drupal-project: Updating Drupal Core](https://github.com/drupal-composer/drupal-project)

[^1]: <https://www.drupal.org/psa-2026-10-12>
[^2]: <https://www.drupal.org/sa-core-2026-014>
[^3]: <https://www.drupal.org/sa-core-2026-015>
[^4]: <https://www.drupal.org/sa-core-2026-016>
[^5]: <https://www.drupal.org/drupal-security-team/security-release-numbers-and-release-timing>
[^6]: <https://www.drupal.org/node/475848>
[^7]: <https://www.drupal.org/docs/updating-drupal/updating-drupal-core-via-composer>
[^8]: <https://www.drupal.org/docs/updating-drupal/deploying-a-drupal-update>
[^9]: <https://www.drupal.org/docs/develop/using-composer/manage-dependencies>
[^10]: <https://www.drush.org/12.1.2/deploycommand/>
[^11]: <https://github.com/drupal-composer/drupal-project>
[^12]: <https://daewooki.github.io/posts/python-multi-runtime-lifecycle-upgrade/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
