---
title: "Docker Desktop 4.91.0 업그레이드에서 로컬 환경을 지키는 법"
description: "엔진/런타임 갱신으로 깨지기 쉬운 로컬 표준을, 링 배포·버전 고정·진단 번들·롤백 런북으로 운영 가능하게 만든다."
date: 2026-09-18 12:44:57 +0900
categories: ["News", "Tools"]
tags: ["docker-desktop", "upgrade-rings", "rollback", "diagnostics-bundle", "settings-management", "local-dev-env"]
render_with_liquid: false
---

Docker Desktop 4.91.0은 2026-09-14에 공개됐고, 구성요소로 Docker Engine v29.8.0과 containerd v2.3.4가 같이 올라갔습니다.[^1] 업데이트 자체보다 더 눈에 들어오는 건 “깨진 로컬환경”에서 사람들이 마지막 수단으로 쓰던 factory reset 의존도를 낮추는 운영성 버그픽스가 들어갔다는 점입니다. 특히 “abrupt shutdown 이후 Docker network database가 corrupt 되면서 Engine이 아예 못 뜨고 factory reset만 답이던” 케이스를 고쳤다고 명시합니다.[^1]

KST 2026-09-18 현재(즉 공개 4일 후) 팀 단위 업그레이드 윈도우를 잡는 상황이라면, 이번 릴리스는 “올려도 되나?”가 아니라 “올리되, 깨졌을 때 복구 가능성이 확보돼 있나?”를 체크리스트로 만들어야 합니다. Docker Desktop을 팀 로컬 개발환경의 표준으로 고정해 쓰는 순간, Docker Desktop 업데이트는 곧 팀 생산성의 계획된 리스크가 됩니다.

예전에 내가 로컬 표준화/업데이트 압력의 맥락을 정리한 글들이 있는데(예: [Kubernetes·Docker·클라우드 네이티브 판이 “업그레이드 압박” 국면으로 들어간 이유](https://daewooki.github.io/posts/2025-12-kubernetesdocker-1/)), 오늘은 그 연장선에서 4.91.0을 “운영”하는 방법만 좁혀서 적습니다. 특히 **갑작스런 부팅 실패 / 네트워크 DB 손상 / Resource Saver 계열 이슈**를 사전에 탐지하고, 필요하면 빠르게 롤백할 수 있게 만드는 쪽입니다.

## 4.91.0에서 실제로 바뀐 것: 런타임 갱신 + ‘복구 지점’ 추가

4.91.0 릴리스 노트에서 확인되는 업데이트는 다음이 핵심입니다.

- Docker Engine v29.8.0[^1]
- containerd v2.3.4[^1]
- Docker Compose v5.5.1, Buildx v0.37.0 등 번들 구성요소 갱신[^1]

Engine 쪽으로 내려가면 Docker Engine 29.8.0 자체는 2026-09-03 릴리스이며(Desktop에 들어온 건 09-14), 기능 추가로 `docker run --umask` 같은 옵션이 포함됩니다.[^2] 이런 기능이 당장 “로컬 깨짐”과 연결되진 않지만, 엔진 업데이트는 결국 storage/network/build 쪽 내부 동작이 바뀌는 이벤트입니다.

반대로 이번 글에서 중요한 버그픽스는 Engine이 아니라 Desktop 레이어(VM/설정/업데이트/상태 관리)에 더 많이 걸려 있습니다. 4.91.0의 운영성 관점 포인트를 세 가지로 묶으면 이렇습니다.

1) **네트워크 DB 손상으로 Engine이 부팅 불가 → factory reset 강제**였던 문제를 수정
- “corrupt Docker network database(대개 abrupt shutdown이 원인)가 Docker Engine start를 막고 factory reset만 복구 옵션이 되던 버그”를 고쳤다고 명시합니다.[^1]

2) “idle/Resource Saver” 주변의 예외 케이스를 다수 정리
- Resource Saver wake 때 Docker Compose가 locally-built image를 매번 rebuild 하던 문제를 수정합니다.[^1]
- idle timeout을 0으로 설정했을 때 VM이 예상치 않게 내려갈 수 있던 문제를 수정합니다.[^1]

3) 상태/디스크/업데이트에서 “망가지는 방식”을 줄이는 쪽으로 보강
- disk image location 변경 중 작업이 중단되면 기존 disk image가 삭제될 수 있던 문제를 수정합니다.[^1]
- VM이 예기치 않게 멈췄을 때 Engine stopped를 보고하는 데 5분 더 걸리던 문제를 수정합니다.[^1]
- Windows에서 WSL이 disk image location에 접근을 못 하면 “Starting…”에서 무한 대기하던 문제를 고치고, 접근 실패 원인을 액션 가능한 가이드로 보여준다고 합니다.[^1]

여기서 중요한 건 “버그를 고쳤다” 자체가 아니라, 우리가 팀 로컬 표준을 운영할 때 어떤 failure mode를 전제로 설계를 해야 하는지(그리고 이번에 그 failure mode 중 하나가 ‘명시적으로’ 줄었다는 점)입니다.

## Docker Desktop에 로컬 표준을 걸었을 때의 구조적 취약점

Docker Desktop을 표준으로 삼으면, 팀에 공통된 장점이 생깁니다.

- OS가 달라도 “Linux VM + Docker Engine”이라는 공통 실행면을 갖게 됩니다.
- 컨테이너 기반 툴체인(Postgres/Redis/MinIO/LocalStack/Testcontainers 등)이 일관됩니다.
- Onboarding 속도가 빨라집니다.

문제는 단일 실행면이 생긴다는 건 단일 고장점이 생긴다는 뜻이기도 합니다.

- Desktop이 안 뜨면 `docker`가 안 됩니다.
- `docker`가 안 되면 로컬 DB도 안 뜹니다.
- 로컬 DB가 안 뜨면 개발/테스트가 멈춥니다.

운영 관점에서 “로컬 개발환경 표준”은 사실상 내부 플랫폼 하나를 운영하는 것과 비슷합니다. 제품은 Desktop이고, 사용자는 개발자이고, 장애는 생산성 장애입니다.

이번 4.91.0의 “corrupt network database → engine start 실패” 픽스가 의미 있는 이유가 여기 있습니다. 이 증상은 흔히 개발자가 노트북을 덮거나(절전), 강제 재부팅하거나, OS 업데이트로 갑자기 종료되는 상황에서 발생합니다. 즉, 개발자가 의도를 갖고 만든 장애가 아니라, 일상적인 사용 패턴에서 발생합니다. 릴리스 노트에서도 원인을 abrupt shutdown으로 명시합니다.[^1]

## ‘갑작스런 부팅 실패/네트워크 DB 손상/Resource Saver’가 팀을 멈추게 만드는 방식

로컬 장애를 운영 관점으로 다루려면, 장애를 “현상”이 아니라 “복구 가능한 상태 머신”으로 모델링해야 합니다. 내가 현업에서 실제로 많이 본 형태를 3갈래로 정리합니다.

### 1) Engine 부팅 실패: UI는 뜨지만 ‘Starting…’에서 멈추는 계열
이 계열은 두 가지가 섞여 나옵니다.

- Desktop UI는 뜨는데 Engine이 못 뜹니다.
- Desktop UI도 제대로 못 뜹니다(무한 재시작/그래픽 드라이버 문제 등).

4.91.0 릴리스 노트에는 “특정 그래픽 드라이버 이슈에서 UI가 무한 restart loop에 빠지던 문제를 고쳤고, UI가 표시될 수 없는 하드웨어 호환성 문제에 대해 메시지를 추가”했다고 되어 있습니다.[^1] 이건 팀 표준 관점에서 꽤 중요합니다. UI가 깨지면 개발자는 흔히 ‘재설치’로만 접근하고, 그 과정에서 데이터/설정이 같이 날아갑니다.

또한 Windows에서는 WSL이 disk image location에 접근 불가할 때 “Starting…” 무한 대기하던 문제를 고치고 가이드를 추가했습니다.[^1] 이 범주는 장애 원인이 사용자 설정/권한/디스크 정책에 걸려 있는 경우가 많아서, “진단 번들 수집 + 정책 변경”으로 풀어야지 무지성 초기화로 풀면 안 되는 타입입니다.

### 2) 네트워크 DB 손상: engine이 못 뜨거나 네트워크가 이상해지는 계열
이번 릴리스가 직접적으로 겨냥한 케이스입니다.

- abrupt shutdown 이후 Docker network database가 corrupt
- 그 결과 Docker Engine이 start 자체를 못 함
- 복구 옵션이 factory reset밖에 없었던 상황

이를 4.91.0에서 고쳤다고 명시합니다.[^1]

여기서 팀 운영 관점 포인트는 이겁니다.

- “factory reset만 답”인 장애는 팀 표준에 치명적입니다.
- 왜냐하면 factory reset은 곧 로컬의 이미지/볼륨/설정/컨텍스트를 통째로 날리는 선택지이기 때문입니다.

Docker Docs의 Troubleshoot 메뉴에서도 “Clean up data”는 Docker data를 리셋하면서 기존 설정이 손실된다고 명시하고, “Reset to factory defaults”는 최초 설치 상태로 되돌린다고 설명합니다.[^3] 즉, 이건 ‘해결책’이라기보다 ‘포맷’에 가깝습니다.

4.91.0이 이 케이스를 줄였다고 해서, 우리가 아무 대비 없이 올려도 된다는 뜻은 아닙니다. 오히려 “이런 케이스가 실제로 빈번했고, Docker도 이걸 운영성 버그로 인지했다”는 신호로 읽는 게 맞습니다.

### 3) Resource Saver/Idle 주변: 성능 최적화가 기능 장애로 튀는 계열
Resource Saver는 로컬에서 컨테이너를 상시 켜두지 않는 개발자에게 꽤 유용하지만, “절전/복귀/idle timeout”이 섞이면 상태 머신이 복잡해집니다.

4.91.0에서 눈여겨볼 문구는 두 가지입니다.

- Resource Saver wake 때 Compose가 locally-built 이미지를 매번 rebuild 하던 문제를 수정[^1]
- idle timeout을 0으로 설정했을 때 VM이 예상치 않게 shut down될 수 있던 문제를 수정[^1]

이런 문제는 겉으로는 “느리다/안 된다”로 보이지만, 실제로는 팀 생산성을 잡아먹는 지속성 이슈가 됩니다. 특히 Compose rebuild는 개발자마다 원인이 다르게 보이고(캐시가 날아간 것처럼 보이기도 해서), 원인 분석 시간부터 비용이 큽니다.

## 링 배포로 ‘일단 일부만 깨지게’ 만드는 게 출발점

Docker Desktop 릴리스 노트에는 업데이트가 점진적으로 롤아웃되며 보통 릴리스 후 1주 내에 업데이트가 제공된다고 적혀 있습니다.[^1] 이 점진 롤아웃은 Docker 쪽 품질 관리 목적이지만, 팀 운영 관점에서는 “링 배포”의 자연스러운 기반이 됩니다.

다만 현실적으로 팀에서 통제 가능한 링 배포를 하려면, Docker가 랜덤하게 뿌리는 롤아웃에 기대면 부족합니다. 내가 권하는 설계는 다음과 같습니다.

- Ring 0 (Canary): 플랫폼/인프라 담당 + 로컬이 자주 깨져도 즉시 복구 가능한 사람
- Ring 1 (Pilot): 팀별 대표자/파워유저 10~20%
- Ring 2 (Broad): 나머지

그리고 링 간 승급 조건을 “감”이 아니라 smoke test로 고정해야 합니다.

- Engine start 시간, `docker info` 정상
- 네트워크 생성/삭제, 포트 publish 정상
- 볼륨 I/O, bind mount 정상
- Compose up/down, rebuild 캐시 유지
- Resource Saver wake 이후 compose 동작

이걸 자동화하지 않으면, 결국 업그레이드는 “각자 업데이트하고, 깨진 사람이 슬랙에 올리고, 옆 사람이 해결해주고, wiki에 적는” 흐름으로 회귀합니다.

## 버전 고정: 업데이트를 ‘금지’하는 게 아니라 ‘통제’하는 방법

업데이트를 통제하는 방법은 크게 2층입니다.

- Docker Desktop 자체 업데이트(앱 버전)
- Desktop 내부 구성요소 업데이트(Compose/CLI/Scout 등 일부는 재시작 없이 올라갈 수 있음)

### Business 환경: Settings Management로 업데이트 플래그를 잠그기
Docker Business를 쓰고 있다면 Settings Management가 제일 정석입니다. `admin-settings.json`으로 중앙에서 설정을 강제할 수 있고, MDM(Jamf 등)로 배포하는 것을 공식 문서가 권장합니다.[^4]

이 문서에서 업데이트와 직접 연결되는 설정은 두 가지가 특히 중요합니다.

- `disableUpdate`: 업데이트 확인/알림을 비활성화[^4]
- `silentModulesUpdate`: 재시작이 필요 없는 구성요소 자동 업데이트 제어[^4]

또한 Settings Management는 sign-in enforcement 등 전제가 있고, `admin-settings.json` 파일의 존재 자체가 sign-in을 강제하는 용도로도 쓰인다고 명시합니다.[^4] 이 전제가 조직 상황과 맞는지 먼저 확인해야 합니다.

아래는 “업데이트를 팀이 통제한다”는 관점에서 최소한의 예시입니다.

```json
{
  "configurationFileVersion": 2,
  "disableUpdate": {
    "locked": true,
    "value": true
  },
  "silentModulesUpdate": {
    "locked": true,
    "value": false
  }
}
```

이 설정이 의미하는 건 “업데이트를 영원히 하지 말자”가 아니라, “업데이트를 하더라도 사전에 패키지/체크리스트/링 배포로 하자”입니다.

### Windows에서 MSI를 쓰는 조직: 기본값이 이미 ‘버전 일관성’에 유리함
Windows에서 MSI로 배포하는 경우, 문서에 따르면 in-app update가 기본으로 비활성화됩니다. 조직이 버전 일관성을 유지하고 승인되지 않은 업데이트를 막기 위한 설계라고 설명합니다.[^5]

여기서 중요한 함정이 하나 있습니다.

- MSI 배포를 해놓고, 개발자는 앱 안에서 업데이트가 되길 기대하는 경우

문서에는 Docker Desktop 4.60+에서 Settings Management로 `disableUpdate=false`로 바꾸면 MSI 설치에서도 in-app update를 활성화할 수 있다고 합니다.[^5] 즉, “업데이트를 중앙 통제할지, 사용자에게 맡길지”를 명확히 결정해야 합니다.

내 경우엔 팀 로컬 표준을 Docker Desktop에 강하게 의존할수록, MSI/MDM로 버전을 통제하는 편이 낫다고 봅니다. 사용자가 업데이트를 각자 해버리면, 링 배포가 무력화됩니다.

### 개인/소규모 팀: GUI 설정과 settings-store.json의 존재를 전제로 운영하기
Docker Desktop은 각 OS에서 `settings-store.json` 파일 위치를 문서로 제공합니다.[^6]

- Mac: `~/Library/Group Containers/group.com.docker/settings-store.json`[^6]
- Windows: `%APPDATA%\Docker\settings-store.json`[^6]

또한 GUI에는 “Always download updates”, “Automatically update components” 같은 설정이 있습니다.[^6]

이 레벨에서 중요한 운영 포인트는 두 가지입니다.

- 업그레이드 전 `settings-store.json`를 백업해 두면, 롤백/재설치 시 재현성이 올라갑니다.
- “Automatically update components”가 켜져 있으면, Desktop 앱 버전은 고정해도 내부 컴포넌트가 서서히 달라질 수 있습니다. 이건 재현성을 해칩니다.[^6]

## 사전 탐지: ‘깨지기 전’이 아니라 ‘깨진 직후’를 자동으로 잡는 게 현실적

로컬 환경에서 “깨지기 전”을 완벽히 예측하기는 어렵습니다. 대신 실무에서는 다음이 더 효율적입니다.

- 업그레이드 직후 5분 안에 깨짐을 탐지
- 자동으로 증거(로그/진단 번들)를 남김
- 실패하면 자동으로 롤백 가이드로 전환

이 전략이 먹히려면, smoke test가 “장난감”이 아니라 실제 팀 워크로드를 대표해야 합니다.

아래는 내가 팀에서 써먹기 좋은 형태로 정리한 smoke test 예시입니다.

- Postgres + Redis + bind mount + 네트워크 생성 + 포트 publish
- 데이터 영속성(볼륨) 확인
- Compose up/down
- 최소 빌드(빌드 캐시/BuildKit 경로)

### 예시: repo에 같이 넣어두는 dd-smoke 프로젝트
폴더 구조는 이렇게 단순하게 둡니다.

```text
local-sentinel/
  compose.yaml
  scripts/
    dd-smoke.sh
    dd-smoke.ps1
  artifacts/
```

#### compose.yaml
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_USER: postgres
      POSTGRES_DB: app
    ports:
      - "15432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d app"]
      interval: 2s
      timeout: 2s
      retries: 30

  redis:
    image: redis:7
    ports:
      - "16379:6379"

  probe:
    image: postgres:16
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./:/work
    working_dir: /work
    entrypoint: ["bash", "-lc"]
    command:
      - |
        set -euo pipefail
        echo "[probe] create table";
        psql "postgresql://postgres:postgres@postgres:5432/app" -v ON_ERROR_STOP=1 <<'SQL'
        create table if not exists sentinel(
          id bigserial primary key,
          ts timestamptz not null default now(),
          note text not null
        );
        insert into sentinel(note) values('ok');
        select count(*) as rows from sentinel;
        SQL
        echo "[probe] bind mount write";
        echo "ok $(date -u +%FT%TZ)" > /work/artifacts/bind-mount.txt
        echo "[probe] done";

volumes:
  pgdata:
```

이 구성은 실제 팀에서 흔한 로컬 스택(DB + cache + bind mount)를 대충이라도 대표합니다. `probe`는 Postgres 이미지의 `psql`을 그대로 써서, 별도 클라이언트 설치 없이 DB I/O를 확인합니다.

#### scripts/dd-smoke.sh (macOS/Linux)
```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p artifacts

echo "== Docker Desktop smoke test =="

# 1) Desktop/Engine 버전 확인
if command -v docker >/dev/null 2>&1; then
  echo "-- docker version --"
  docker version || true
else
  echo "docker CLI not found" >&2
  exit 2
fi

# 2) Engine 응답성 확인
echo "-- docker info (wait up to 60s) --"
for i in $(seq 1 60); do
  if docker info >/dev/null 2>&1; then
    echo "engine is responding"
    break
  fi
  sleep 1
  if [ "$i" = "60" ]; then
    echo "engine is not responding" >&2
    exit 3
  fi
done

# 3) 네트워크 생성/삭제가 정상인지(네트워크 DB 계열의 간접 신호)
NET_NAME="dd_smoke_net"
if docker network inspect "$NET_NAME" >/dev/null 2>&1; then
  docker network rm "$NET_NAME" >/dev/null || true
fi

docker network create "$NET_NAME" >/dev/null

docker network rm "$NET_NAME" >/dev/null

# 4) Compose로 실제 워크로드 스모크
echo "-- docker compose up --"
docker compose up -d --remove-orphans

echo "-- docker compose run probe --"
docker compose run --rm probe

echo "-- restart postgres and re-check persistence --"
docker compose restart postgres

# probe 재실행: 볼륨이 유지되면 row count가 증가
ROW_COUNT=$(docker compose run --rm probe bash -lc \
  "psql 'postgresql://postgres:postgres@postgres:5432/app' -tAc 'select count(*) from sentinel;'" \
  | tr -d '[:space:]')

echo "rows in sentinel: ${ROW_COUNT}"

echo "-- docker compose down --"
docker compose down

echo "PASS"
```

실행:

```bash
chmod +x scripts/dd-smoke.sh
./scripts/dd-smoke.sh
```

예상 출력(환경에 따라 상세는 달라지지만, 형태는 이래야 합니다):

- `docker version`에서 Server가 출력됨
- `engine is responding`
- `rows in sentinel: 2` 같은 숫자가 찍힘(최소 1 이상)
- 마지막에 `PASS`

#### scripts/dd-smoke.ps1 (Windows PowerShell)
```powershell
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot ".."))
Set-Location $Root

New-Item -ItemType Directory -Force -Path "artifacts" | Out-Null

Write-Host "== Docker Desktop smoke test =="

Write-Host "-- docker version --"
& docker version | Out-Host

Write-Host "-- wait for docker info (60s) --"
$ok = $false
1..60 | ForEach-Object {
  try {
    & docker info *> $null
    $ok = $true
    return
  } catch {
    Start-Sleep -Seconds 1
  }
}
if (-not $ok) {
  throw "engine is not responding"
}

Write-Host "-- network create/remove --"
$net = "dd_smoke_net"
try { & docker network rm $net *> $null } catch {}
& docker network create $net *> $null
& docker network rm $net *> $null

Write-Host "-- docker compose up --"
& docker compose up -d --remove-orphans | Out-Host

Write-Host "-- docker compose run probe --"
& docker compose run --rm probe | Out-Host

Write-Host "-- restart postgres and re-check persistence --"
& docker compose restart postgres | Out-Host

$row = (& docker compose run --rm probe bash -lc "psql 'postgresql://postgres:postgres@postgres:5432/app' -tAc 'select count(*) from sentinel;'" ).Trim()
Write-Host "rows in sentinel: $row"

Write-Host "-- docker compose down --"
& docker compose down | Out-Host

Write-Host "PASS"
```

이 smoke test는 “네트워크 DB가 깨졌다/Engine이 부팅 불가” 같은 케이스에서 아예 초반에 실패합니다(대개 `docker info`에서 막힘). 그게 목적입니다.

## 진단 번들 수집을 ‘버튼’이 아니라 ‘런북의 첫 줄’로 만들기

링 배포 + smoke test가 있어도, 실패는 0이 아닙니다. 실패했을 때 팀 전체가 헤매지 않게 하려면 “진단 번들 수집”이 자동으로 따라와야 합니다.

Docker Docs는 진단 수집을 앱(UI)에서도 할 수 있고, 터미널에서도 할 수 있다고 안내합니다. 특히 UI가 안 뜨는 상황을 위해 CLI 경로를 같이 제공합니다.[^3]

### 1) docker desktop diagnose
Docker Desktop CLI에는 `diagnose` 명령이 있고, 옵션으로 `--upload`를 지원합니다.[^7]

```bash
docker desktop diagnose --upload
```

이 명령은 진단을 수집하고 업로드한 뒤 diagnostics ID를 출력합니다.[^3]

### 2) com.docker.diagnose gather -upload
Docker는 OS별로 `com.docker.diagnose` 실행 파일 위치와 사용 예시를 문서에 제공합니다.[^3]

- macOS:
```bash
/Applications/Docker.app/Contents/MacOS/com.docker.diagnose gather -upload
```

- Linux:
```bash
/opt/docker-desktop/bin/com.docker.diagnose gather -upload
```

- Windows(예: all-user install):
```powershell
& "C:\Program Files\Docker\Docker\resources\com.docker.diagnose.exe" gather -upload
```

이걸 “엔진이 안 뜨면 실행” 정도로 문서화해두는 게 아니라, smoke test 실패 시 자동 실행하도록 런북을 고정하는 편이 팀 비용을 훨씬 줄입니다.

### 3) 로그를 남기는 습관: docker desktop logs / init.log
진단 번들 업로드가 보안/정책상 막히는 환경도 있습니다. 그 경우를 대비해 로그 접근 경로를 최소한으로 알아야 합니다.

- Docker Desktop CLI에는 `docker desktop logs`가 있고, unit 필터를 지원합니다.[^8]

또한 daemon 로그는 Docker Docs에서 OS별 위치를 제공합니다.

- macOS: `~/Library/Containers/com.docker.docker/Data/log/vm/init.log`
- Windows(WSL2): `%LOCALAPPDATA%\Docker\log\vm\init.log`

그리고 이 `init.log`는 dockerd/containerd 등 VM 서비스 로그를 JSON 라인으로 합쳐놓은 형태라고 설명합니다.[^9]

여기까지가 “증거를 남긴다”의 최소 단위입니다. 엔진이 안 뜨는 문제를 팀 채팅에 텍스트로만 공유하면, 해결이 아니라 추측이 됩니다.

### 4) 진단 데이터의 보존/프라이버시
조직에 따라 “진단 번들 업로드”는 개인정보/보안 이슈가 됩니다. Docker 지원 문서에는 진단 번들에 username/IP 같은 개인 데이터가 포함될 수 있고, 기본적으로 30일 후 삭제된다고 명시합니다.[^10] 이 내용은 보안팀과의 합의에 쓸 수 있는 근거 문장입니다.

## 롤백을 가능하게 만드는 핵심: ‘다운그레이드 파일’이 아니라 ‘다운그레이드 프로세스’

롤백에서 팀이 실제로 자주 망하는 지점은 파일이 아닙니다.

- “어느 버전으로 돌아갈지”가 정해져 있지 않음
- “돌아가면 무엇이 유지되고 무엇이 날아가는지”가 불명확
- “데이터/볼륨을 살리고 싶다”는 욕심 때문에 복구 시간이 폭증

### 1) 롤백 기준 버전(Anchor)을 미리 지정하기
나는 보통 다음 중 하나로 Anchor를 둡니다.

- 직전 릴리스(예: 4.90.0)
- 지난 2~3주간 문제 없던 버전

4.91.0의 직전은 4.90.0(2026-09-07)입니다.[^1] 링 배포를 한다면 보통 “4.91.0에서 smoke test가 깨지면 4.90.0으로 복귀”처럼 기계적인 기준이 필요합니다.

### 2) ‘다운로드 가능성’을 롤백 전략에 포함시키기
Docker Desktop 릴리스 노트에는 “최신 버전 기준 6개월보다 오래된 Desktop 버전은 다운로드 제공되지 않는다”고 적혀 있습니다.[^1] 즉, 롤백을 하려면 “내부 아티팩트 저장소에 설치 파일을 보관하는 체계”가 필요합니다.

이건 기술보다 프로세스 문제라서, 실제로는 다음을 강제하는 게 효과적입니다.

- 링 배포를 시작하는 날, 해당 링에 배포한 설치 파일을 artifacts에 저장
- artifacts에는 체크섬/서명 검증 정보를 같이 저장

### 3) 지원 정책도 롤백 창을 제한한다
Docker 지원 문서에는 지원되는 버전 정책이 구독 플랜별로 다르다고 적혀 있습니다.

- Docker Business: 최신 대비 6개월까지 지원(픽스는 최신에만 적용)
- Pro/Team: 최신 버전만 지원

[^10]

이 말은 “롱텀으로 특정 버전에 머무르겠다”는 전략이 조직 구독/지원정책과 충돌할 수 있다는 뜻입니다. 그래서 실무적으로는 “빠르게 올리되, 깨지면 빠르게 내리고, 다음 핫픽스를 기다렸다가 다시 올리는” 리듬이 필요해집니다.

## ‘깨진 로컬환경’ 복구 런북: Reset 버튼을 누르기 전에 해야 하는 순서

아래 순서는 “개발자 개인의 문제 해결”이 아니라 “팀 표준의 운영”을 위한 흐름입니다.

### 1) 증상 분류
- A: `docker info`가 아예 안 됨 (Engine 부팅 실패)
- B: Engine은 뜨는데 네트워크/포트/DNS가 이상함
- C: Resource Saver wake 이후만 이상함(Compose rebuild, hang 등)

### 2) 공통 1단계: 증거 수집
- `docker version` 출력 캡처(클라이언트/서버 포함)[^11]
- `docker desktop diagnose --upload` 또는 `com.docker.diagnose gather -upload`로 diagnostics ID 확보[^3]
- 가능하면 `docker desktop logs --priority 2`로 error 이상 로그 확보[^8]

이 단계가 빠지면 같은 문제가 재발할 때 또 같은 시간을 씁니다.

### 3) A(부팅 실패)에서의 처리
4.91.0에서 “corrupt network database 때문에 엔진이 못 뜨고 factory reset만 답”이던 버그를 고쳤다고 하니[^1], 동일 증상이 재발하면 이제는 다음이 의심 대상입니다.

- 디스크 접근/권한(특히 Windows WSL이 disk image location 접근 불가)[^1]
- 업데이트/설치 설정 충돌(install-settings 계열)
- 보안 소프트웨어의 파일 lock

보안 소프트웨어 관련해서는 Docker 문서가 “Docker 데이터 디렉터리 스캔이 파일을 lock 해서 Docker command가 hang 할 수 있다”는 점과, 제외 설정의 트레이드오프를 설명합니다.[^12] 4.91.0의 “plugin binary가 다른 프로세스에 의해 lock 되어 업데이트가 반복 실패하던 문제”[^1] 도 이런 현실과 결이 맞습니다.

이 단계에서 바로 reset으로 가면, 원인 제거가 아니라 데이터 삭제로 문제를 가립니다.

### 4) B(네트워크 이상)에서의 처리
이번 4.91.0의 핵심 픽스가 네트워크 DB이므로, 4.91.0으로 올린 뒤에도 네트워크 계열 문제가 나오면 “이전과 같은 원인”이 아닐 수 있습니다.

- 기업 네트워크/프록시 정책 변화
- VPN/EDR이 `com.docker.backend` 트래픽을 차단

Docker Desktop 네트워킹 문서는 “VM/컨테이너 네트워킹이 com.docker.backend(Windows는 com.docker.backend.exe) 같은 프로세스를 통해 나간다”는 점을 언급합니다.[^13] 즉, 보안 제품이 이 프로세스를 막으면 Docker 전체가 통째로 통신 장애가 됩니다.

이 경우는 reset을 해도 계속 재발합니다. 원인은 정책이기 때문입니다.

### 5) C(Resource Saver)에서의 처리
4.91.0에서 Resource Saver wake 시 compose rebuild 문제를 고쳤다고 하지만[^1], 팀 표준에서 Resource Saver는 “개발자별 편차가 크고, 증상이 헷갈리는” 기능입니다.

내가 권하는 운영 방식은 다음입니다.

- 링 배포 smoke test에 “sleep/idle → wake → compose run”을 포함
- 문제가 자주 나는 조직이라면 Resource Saver 관련 설정을 중앙에서 통제(켜거나 끄거나 둘 중 하나)

로컬 표준은 “각자 최적화”보다 “모두 같은 동작”이 비용이 덜 듭니다.

## 지금 업그레이드 윈도우에서 체크할 리스트

여기부터는 4.91.0을 올리기 위한 최소 체크리스트입니다. 단순 나열이 아니라, 실패 시 어디로 롤백할지까지 포함합니다.

### 1) 배포 계획
- Ring 0/1/2 대상자 명단 고정
- Anchor 버전(예: 4.90.0) 설치 파일을 내부 저장소에 보관
- 4.91.0 설치 파일과 체크섬을 내부 저장소에 보관

Docker Desktop은 6개월 이상 지난 버전은 다운로드 제공이 안 된다고 명시하므로[^1], 파일 보관이 곧 롤백 능력입니다.

### 2) 업데이트 통제
- Business면 `admin-settings.json`로 `disableUpdate`, `silentModulesUpdate` 정책을 결정[^4]
- Windows MSI면 “in-app update 기본 비활성화” 상태를 유지할지 결정[^5]

### 3) smoke test 실행/기록
- dd-smoke 실행 결과를 artifacts로 남김
- 실패하면 즉시 diagnostics ID 수집

### 4) 실패 시 자동 조치
- smoke test 실패 + 부팅 실패(A)면: diagnostics 수집 → 롤백(4.90.0)
- 네트워크 이상(B)이면: com.docker.backend 차단 여부/프록시 정책 우선 확인[^13]
- Resource Saver(C)이면: wake 시나리오 재현 후 정책으로 통제

## 반론과 회의론: Docker Desktop에 로컬 표준을 걸지 말자는 주장

이 글은 Docker Desktop을 팀 표준으로 쓰는 상황을 전제로 했지만, 반대 방향의 주장은 여전히 유효합니다.

- Windows는 WSL2 내부에 Docker Engine을 직접 깔아서 Desktop 의존도를 줄일 수 있습니다.
- 개발 환경을 로컬이 아니라 remote dev environment(예: devcontainer + remote VM)로 옮기면, 개인 노트북의 상태 머신을 운영하지 않아도 됩니다.

다만 팀이 이미 Docker Desktop 표준 위에서 도구/문서/테스트를 다 쌓아놨다면, 갑자기 표준을 바꾸는 비용이 더 큽니다. 현실적인 선택은 “버리자/유지하자”가 아니라 “유지하되 운영 가능하게 만들자” 쪽입니다.

## 앞으로 지켜볼 것: Engine 29.8.1과 다음 Desktop의 묶음

Docker Engine은 29.8.0 이후 2026-09-15에 29.8.1이 바로 나왔습니다.[^2] 29.8.1에는 containerd static binary 업데이트(v2.3.5) 같은 패키징 변화도 포함됩니다.[^2] Desktop 4.91.0은 Engine 29.8.0 + containerd 2.3.4 조합이므로[^1], 가까운 시점에 Desktop이 29.8.1 계열로 따라올 가능성이 있습니다.

여기서 팀 운영 관점의 결론은 단순합니다.

- Desktop 버전 하나 올리는 게 끝이 아니라, 짧은 간격으로 연속 이벤트가 발생할 수 있습니다.
- 링 배포/버전 고정/진단 번들/롤백 런북이 한 번 만들어지면, 이후 이벤트는 반복 처리로 바뀝니다.

## 정리: 4.91.0은 ‘업데이트해야 하는 버전’이 아니라 ‘업데이트를 운영으로 바꾸는 계기’

4.91.0은 Engine/런타임이 갱신된 릴리스이면서, 네트워크 DB 손상으로 Engine이 아예 못 뜨던 문제를 “factory reset만 답”에서 벗어나게 만든 픽스를 포함합니다.[^1] 또한 Resource Saver/idle 주변의 실사용 버그를 줄이는 수정들이 같이 들어갔습니다.[^1]

팀 로컬 표준을 Docker Desktop에 걸었다면, 다음을 갖추는 순간부터 업그레이드는 공포가 아니라 반복 가능한 작업이 됩니다.

- 링 배포(일부만 먼저)
- 버전 고정(승인된 버전만)
- smoke test(업그레이드 직후 5분 내 탐지)
- 진단 번들 수집(실패 시 증거 자동 수집)
- 롤백(Anchor 버전으로 즉시 복귀)

이 다섯 가지가 없는 상태에서의 업그레이드는, 결국 언젠가 팀 전체의 로컬을 동시에 깨뜨리는 이벤트로 돌아옵니다.

## 참고 자료
- [Docker Desktop release notes](https://docs.docker.com/desktop/release-notes/)
- [Docker Engine version 29 release notes](https://docs.docker.com/engine/release-notes/29/)
- [Troubleshoot Docker Desktop (diagnose, com.docker.diagnose)](https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/)
- [Settings Management: Configure with admin-settings.json](https://docs.docker.com/enterprise/security/hardened-desktop/settings-management/configure-json-file/)
- [Settings Management overview](https://docs.docker.com/enterprise/security/hardened-desktop/settings-management/)
- [MSI installer (enterprise deployment)](https://docs.docker.com/enterprise/enterprise-deployment/msi-install-and-configure/)
- [Change your Docker Desktop settings (settings-store.json location)](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
- [Use the Docker Desktop CLI](https://docs.docker.com/desktop/features/desktop-cli/)
- [docker desktop diagnose (CLI reference)](https://docs.docker.com/reference/cli/docker/desktop/diagnose/)
- [docker desktop logs (CLI reference)](https://docs.docker.com/reference/cli/docker/desktop/logs/)
- [Read the daemon logs (Desktop init.log paths)](https://docs.docker.com/engine/daemon/logs/)
- [Antivirus software and Docker](https://docs.docker.com/engine/security/antivirus/)
- [Get support for Docker products (diagnostics privacy, supported versions)](https://docs.docker.com/support/)
- [Docker Desktop silent component updates (background updates control)](https://www.docker.com/blog/docker-desktop-silent-component-updates/)
- [containerd releases (v2.3.4)](https://github.com/containerd/containerd/releases)

[^1]: <https://docs.docker.com/desktop/release-notes/>
[^2]: <https://docs.docker.com/engine/release-notes/29/>
[^3]: <https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/>
[^4]: <https://docs.docker.com/enterprise/security/hardened-desktop/settings-management/configure-json-file/>
[^5]: <https://docs.docker.com/enterprise/enterprise-deployment/msi-install-and-configure/>
[^6]: <https://docs.docker.com/desktop/settings-and-maintenance/settings/>
[^7]: <https://docs.docker.com/reference/cli/docker/desktop/diagnose/>
[^8]: <https://docs.docker.com/reference/cli/docker/desktop/logs/>
[^9]: <https://docs.docker.com/engine/daemon/logs/>
[^10]: <https://docs.docker.com/support/>
[^11]: <https://docs.docker.com/reference/cli/docker/version/>
[^12]: <https://docs.docker.com/engine/security/antivirus/>
[^13]: <https://docs.docker.com/desktop/features/networking/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
