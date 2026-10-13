---
title: "Next.js 16.4: Turbopack 캐시·번들 최적화로 모노레포 CI 비용 다시 보기"
description: "16.4의 캐시 압축·정리, 번들 축소, create-next-app 기본값 변화가 로컬/CI의 캐시 키와 빌드 SLO를 어떻게 바꾸는지 정리합니다."
date: 2026-10-13 12:03:42 +0900
categories: ["News", "Frontend"]
tags: ["nextjs", "turbopack", "monorepo", "ci-cd", "bundle-size", "cache-components"]
render_with_liquid: false
---

## 2026-10-06에 바뀐 것 중, 비용에 직결되는 항목만 뽑으면

2026-10-06에 공개된 [Next.js 16.4 릴리스 노트](https://nextjs.org/blog/next-16-4)는 Cache Components 쪽이 메인 테마이지만, 프런트엔드 팀이 체감하는 인프라 비용(개발자 머신 SSD/IO, CI 캐시 스토리지, 워크플로 실행 시간, 아티팩트 업로드/다운로드, 번들 전송량)을 바꾸는 포인트는 의외로 Turbopack 디스크 캐시와 번들 최적화 쪽입니다.

특히 아래 네 가지가 같이 움직입니다.

- **Turbopack disk cache 20–25% 절감**: 16.4에서 Turbopack 디스크 캐시가 별도 설정 없이 20–25% 덜 차지하도록 바뀌었고, 공간 대부분을 먹는 데이터에는 Zstandard 압축을 적용하고 메타데이터는 LZ4를 유지해 lookup 속도를 유지합니다. stale 데이터 제거(compaction) 루틴도 개선됐습니다.[^1]
- dev에서의 불필요한 백그라운드 컴파일 감소: Lazy server HMR로, 이전에 방문했던 다른 라우트까지 서버 모듈 업데이트를 밀어 넣는 일을 줄였습니다.[^1]
- 번들/전송량 감소: production에서 CSS Modules class name이 짧아지고, export mangling이 들어가 번들 연결용 내부 export 이름을 줄입니다.[^1]
- **Cache Components 기본값 전환**: 16.4부터 create-next-app로 만든 새 앱은 Cache Components가 기본 enabled가 됐고, Next.js 팀은 16.4부터 Cache Components를 “모든 앱에 대한 최선의 선택”으로 추천합니다.[^1][^2]

이 글의 관점은 기능 소개가 아니라, 위 변화들을 전제로 모노레포/CI의 캐시 계층(Next/Turbopack 캐시 vs Turborepo Remote Cache vs GitHub Actions cache)과 캐시 키 설계, 빌드 시간 SLO 자체를 다시 잡는 쪽입니다.

## Turbopack 디스크 캐시가 ‘비용’이 되는 지점

Turbopack은 dev에서 캐시를 공격적으로 남기고, 그게 성능을 만드는 방식입니다. 이건 16.x에서 더 뚜렷해졌고, Next.js 문서도 filesystem cache가 `.next` 폴더에 저장돼 다음 `next dev`/`next build`에 걸친 작업량을 줄인다고 설명합니다.[^3]

여기서 비용은 단순히 “디스크가 많이 찬다”로 끝나지 않습니다.

1) 개발자 머신: SSD 공간 + 파일 인덱싱 + 백신/EDR 스캔 + 백업 에이전트

대부분 회사 맥북/윈도우 노트북은 다음이 같이 묶여 있습니다.

- 파일이 많이 생성되면 Spotlight/Windows Search 인덱싱이 폭주합니다.
- EDR이 `.next` 아래 변경 파일을 전부 스캔하면서 CPU/IO가 튑니다.
- Time Machine/OneDrive/Dropbox 같은 동기화/백업 클라이언트가 변경분을 쫓아갑니다.

Turbopack 캐시가 커질수록 “빌드가 빨라짐”과 별개로 시스템 전체가 느려지는 구간이 생깁니다. 이 지점에서 개발자는 결국 `.next/dev`를 삭제해 리셋하고, 그럼 warm cache 이점은 사라집니다.

실제로 Turbopack dev filesystem cache가 `.next/dev/cache/turbopack` 아래에 쌓이고, 모노레포에서 수십 GB까지 커질 수 있다는 문제 제기가 있었습니다.[^4]

16.4의 20–25% 절감은 이 맥락에서 의미가 있습니다. “캐시를 남기는 전략”은 유지하면서도, 디스크 풋프린트를 줄여 OS/보안 도구/백업 도구가 발작하는 임계점을 뒤로 미룹니다.

2) CI: 캐시 업/다운로드, 캐시 miss 폭발, 저장소 과금

CI에서 돈이 드는 항목을 쪼개면 대략 아래입니다.

- 빌드/테스트 wall time (runner 비용)
- 캐시 upload/download 시간 (wall time의 일부)
- 캐시 저장소 사용량 (캐시 백엔드 과금)

캐시는 히트하면 돈을 아끼는데, 캐시 자체가 너무 커지면 “캐시를 받느라” 돈이 듭니다. Next/Turbopack 계열 캐시는 파일 수가 많고 변경이 잦아 전송 오버헤드가 커지기 쉽습니다.

16.4의 캐시 압축/compaction 개선은 단순히 dev 경험이 아니라, CI에서 “캐시를 내려받는 시간”과 “캐시 저장소가 쓰레기 파일로 부풀어오르는 속도”에 직결됩니다.

## 캐시 계층을 3개로 나누고, 각 계층의 역할을 다시 정의합니다

모노레포에서 Next.js를 쓰면 캐시가 세 겹으로 생깁니다.

- Next/Turbopack 캐시: `.next` 하위에 쌓이는 컴파일 산출물/캐시
- 작업 러너 캐시: Turborepo/ Nx의 task cache(원격 캐시 포함)
- CI 플랫폼 캐시: GitHub Actions `actions/cache`, CircleCI cache, Buildkite cache 등

여기서 흔한 실수는 “전부 캐시하면 빨라진다”라고 생각하고 `.next` 전체를 상위 캐시에 얹는 겁니다. 특히 dev 캐시(`.next/dev`)는 CI의 빌드 산출물과 성격이 다르고, dev 세션 히스토리에 따라 내용이 바뀌기 쉬워서 캐시 효율이 낮습니다.

내 기준에서 16.4 이후의 권장 전략은 아래처럼 역할을 갈라 잡는 쪽입니다.

- Next/Turbopack 캐시: 로컬 dev warm start와 반복 빌드에 집중. 디스크 풋프린트는 budget을 두고 관리.
- Turborepo Remote Cache: 빌드 산출물(배포에 필요한 결과물) 중심. dev 캐시는 넣지 않음.
- CI 플랫폼 캐시: 의존성 설치(pnpm store) + “가치가 큰 빌드 캐시”만 선별. 키 설계를 잘못하면 오히려 비용 상승.

16.4는 Turbopack 디스크 캐시 풋프린트를 줄여서 첫 번째 층(로컬 dev) 부담을 낮추고, 동시에 번들 크기 최적화로 세 번째 층(아티팩트 전송량, 결과물 저장량) 부담도 낮추는 방향으로 움직였습니다.[^1]

## 모노레포에서 캐시 키를 다시 설계할 때 핵심: ‘환경 변화’와 ‘코드 변화’를 분리

캐시 키 설계에서 가장 큰 비용은 불필요한 miss입니다. 키가 조금만 달라져도 전체 캐시가 날아가면, 캐시가 커질수록 miss 비용이 폭발합니다.

모노레포 Next.js CI에서 키를 최소 2단으로 나누는 편이 안정적입니다.

- 1단(의존성): lockfile 기반. pnpm이면 `pnpm-lock.yaml` hash.
- 2단(빌드 캐시): “의존성 + 빌드 도구 버전 + Next config” 기반.

여기서 “앱 소스 코드 변경”은 캐시 키에 넣지 않는 쪽이 낫습니다. 소스가 바뀌는 건 캐시가 존재하는 이유이기도 해서, 소스 변경마다 캐시를 무효화하면 cache hit ratio가 구조적으로 낮아집니다.

대신 다음을 키에 넣어야 합니다.

- Node 버전(Next 16은 Node 20.9+를 요구합니다)[^5]
- Next.js 버전(16.3 → 16.4 업그레이드 자체가 캐시 포맷/최적화에 영향을 줍니다)
- `next.config.*`에 있는 Turbopack/Cache Components 관련 플래그
- package manager 종류(npm/yarn/pnpm/bun)

이렇게 잡으면 16.4에서 캐시 포맷이 바뀌거나 디스크 캐시 구조가 바뀌어도 “정상적으로 miss”가 나고, 앱 코드가 바뀌는 정도에서는 계속 hit를 기대할 수 있습니다.

## Turbopack dev 캐시 retention 문제: 16.4의 ‘compaction 개선’만으로는 부족할 수 있습니다

16.4는 stale 데이터를 더 효율적으로 drop하도록 compaction을 개선했다고 밝힙니다.[^1]

하지만 이건 어디까지나 “더 잘 정리한다”이지, 강제적인 상한선이 생겼다는 얘기는 아닙니다. 실제로 16.2.x 시점에 dev filesystem cache retention이 문서화되어 있지 않다는 문제 제기가 있었고, `.next/dev/cache/turbopack`가 66GB까지 커진 사례가 공유됐습니다.[^4]

그래서 모노레포에서는 다음을 별도 정책으로 가져가는 편이 낫습니다.

- 개발자 머신 디스크 budget: 예를 들어 “앱 1개당 `.next/dev` 10GB 상한” 같은 규칙
- 정리 메커니즘: 자동(16.4 실험 기능) + 수동(주기적 purge) 조합

16.4에는 디스크 캐시 정리를 위한 실험 옵션 `experimental.turbopackGc`가 추가됐습니다. 오래된 세션의 stale 데이터(삭제한 라우트의 캐시 등)도 회수할 수 있다고 설명합니다.[^1][^6]

프로덕션 코드 품질과 별개로, “로컬에서 디스크가 터져서 개발자가 캐시를 수동 삭제하는 일”이 반복된다면 이 플래그는 꽤 실용적입니다.

## 번들 축소가 CI 비용에 연결되는 방식

Next.js 16.4가 말하는 번들 축소는 사용자 다운로드만 줄이는 게 아닙니다.

- CI에서 `next build` 결과물 크기가 줄어들면, 아티팩트 업로드/다운로드 시간이 줄어듭니다.
- 모노레포에서 여러 앱을 한 번에 빌드할 때, 저장/전송 병목이 줄어듭니다.
- 캐시 저장소에서 “저장할 파일 총량”이 줄어듭니다.

16.4의 번들 관련 하이라이트는 세 가지입니다.

- Turbopack shared runtime: 런타임을 라우트마다 중복해서 내보내는 대신, 하나의 공유 chunk로 제공해 다운로드 크기와 cache hit rate를 개선합니다.[^1][^7]
- production CSS Modules class name 단축: production에서 더 짧은 class name을 생성합니다. HTML/JS에서 참조하는 문자열 자체가 줄어드는 효과가 있습니다.[^1]
- **export mangling**: 모듈을 연결하는 내부 export 이름을 줄여 번들 크기를 감소시킵니다.[^1]

여기서 CSS Modules class name은 그동안 Turbopack 기반(특히 Lightning CSS) 파이프라인에서 길어진다는 불만이 있었고, “prod에서는 짧게 만들고 dev에서는 디버깅을 위해 길게 유지”라는 방향이 16.4에서 명시적으로 들어온 셈입니다.[^8]

## create-next-app 기본값 변화가 CI/모노레포에 주는 영향

16.4에서 새로 생성되는 앱은 Cache Components가 기본 enabled입니다. 또한 agent feedback도 recommended 설정으로 만든 경우 기본 enabled라고 설명합니다.[^1]

여기서 비용 관점에서 중요한 건 “기능이 좋아졌다”가 아니라, 기본 렌더링/캐싱 모델이 바뀌면 다음이 같이 바뀐다는 점입니다.

- build-time에서 어떤 라우트가 static으로 남는지, request-time으로 떨어지는지
- prefetch/ppr로 생성되는 산출물의 성격
- 특정 코드 패턴이 build를 실패시키는지(정책적으로 막는지)

16.4는 Cache Components 갭을 메우는 기능으로 `ensureStatic`을 소개합니다. 의도치 않게 dynamic 컴포넌트가 섞여 서버 비용 특성이 깨지는 걸 build 단계에서 막는 장치입니다.[^1]

이건 프런트엔드 팀이 “성능 최적화”의 일부로 하던 일을 “정책/컴파일 타임 계약”으로 끌어올리는 변화입니다. 결과적으로 CI에서는 다음이 바뀝니다.

- 빌드 실패가 늘어날 수 있습니다(좋은 실패이기도 함). 대신 배포 후 비용 폭탄을 줄입니다.
- 라우트별로 SLO를 잡을 때, 단순히 build time뿐 아니라 “static 보장률” 같은 지표를 넣을 여지가 생깁니다.

Cache Components 플래그 자체는 `next.config`에서 `cacheComponents: true`로 켭니다.[^2][^9][^10]

## 모노레포 gotcha: `.next/dev`를 빌드 산출물로 취급하면 비용이 폭발합니다

모노레포에서 Turborepo를 쓰는 경우가 많고, 여기서 “outputs”를 넓게 잡으면 `.next/dev`까지 캐시 산출물로 딸려 들어가면서 원격 캐시가 비정상적으로 커집니다.

문제는 `.next/dev`의 성격이 빌드 산출물과 다르다는 데 있습니다.

- dev server 세션에서 방문한 라우트/모듈 히스토리의 영향을 받습니다.
- 협업자 간에 재현성이 낮습니다.
- CI에서는 dev server를 안 띄우는 경우가 대부분이라 재사용 가치가 낮습니다.

반대로 `.next/dev/cache/turbopack`가 수십 GB로 커질 수 있다는 점은 이미 공유된 경험입니다.[^4]

따라서 모노레포에서는 최소한 다음을 분리하는 편이 안전합니다.

- 배포용 빌드 산출물: `next build` 결과 중 실제로 배포에 필요한 것
- 개발용 캐시: `.next/dev` 계열
- 빌드 캐시: `.next/cache` 계열(여기 역시 “CI 플랫폼 캐시”로 빼는 게 낫지, 빌드 산출물로 원격 캐시에 넣는 건 신중해야 합니다)

이 구분이 16.4에서 더 중요해지는 이유는, 캐시가 더 커지는 방향(더 aggressive한 caching, 더 많은 최적화)으로 프레임워크가 진화하고 있기 때문입니다. 16.4는 그 비용을 낮추기 위해 압축/정리를 손봤지만, 분리 전략이 없으면 결국 캐시 폭발을 다시 경험합니다.

## CI 빌드 시간 SLO를 다시 잡는 방법: “빌드 1회”가 아니라 “캐시 포함 E2E”로 잡습니다

Next/Turbopack이 기본이 된 이상, 빌드 시간 SLO는 cold build만으로는 팀을 못 움직입니다. 오히려 목표는 아래 조합이 됩니다.

- cold build: 캐시가 없을 때 최악의 시간
- warm build: 동일 브랜치/유사 변경에서 캐시가 있을 때 기대 시간
- cache restore 비용: 캐시 다운로드/압축 해제/파일 restore에 걸리는 시간

여기서 16.4의 변화는 warm build 쪽 “캐시 크기”를 줄여 cache restore 비용 자체를 낮추는 방향입니다.[^1]

내가 SLO를 다시 잡을 때 권장하는 지표는 다음입니다.

1) CI Build Wall Time (P50/P95)

- P50은 개발자가 기대하는 평균 체감
- P95는 장애/배포 지연의 원인이 됩니다

2) Cache Hit Ratio (빌드 캐시, 태스크 캐시 각각)

- hit가 낮으면 캐시에 돈을 쓰는 의미가 없어집니다

3) Cache Size Budget

- 캐시 단건 크기(예: `.next/cache`가 1GB를 넘으면 경고)
- 캐시 누적 크기(저장소 총량)

4) Artifact Upload/Download Time

- 배포 파이프라인이 느린 팀은 여기서 발목 잡힙니다

이렇게 보면, 16.4의 “번들 축소”는 런타임만이 아니라 아티팩트/캐시 전송 시간에도 영향을 주는 변화로 해석하는 게 맞습니다.

## 업그레이드 실측을 위한 플레이북: 숫자를 만들 때까지의 최소 루프

여기부터는 “16.4가 좋아요”가 아니라, 7일 안에 팀에 공유 가능한 숫자를 만드는 방법입니다. 수치는 환경마다 달라서, 이 글에서는 측정 방법을 고정하고 결과를 비교하는 흐름만 정리합니다.

### 1) 버전 고정과 비교축 만들기

- 기준 버전: 16.3.x(또는 현재 프로덕션)
- 실험 버전: 16.4.x
- Node 버전은 고정(Next 16의 요구사항이 Node 20.9+임을 감안)[^5]

예시(프로젝트에 맞게 패키지 매니저만 맞추면 됩니다):

```bash
# (예) pnpm
pnpm add -D next@16.3.0
pnpm add -D react@latest react-dom@latest

# 브랜치 분기 후 16.4로 업그레이드
pnpm add -D next@16.4.0
```

Next.js 16은 `next dev`/`next build` 기본 bundler가 Turbopack입니다. Webpack과 비교하려면 명시적으로 `--webpack`을 붙여야 합니다.[^11][^12]

### 2) 로컬 dev 캐시 크기 측정

dev 캐시 크기는 적어도 아래 세 가지를 같이 봐야 합니다.

- `.next/dev` 전체 크기
- `.next/dev/cache/turbopack` 크기(존재하면)
- “일주일 개발 후” 증가량(시간축)

macOS/Linux 기준 예시:

```bash
# 앱 디렉터리에서
DU_BASELINE=$(du -sk .next/dev 2>/dev/null | awk '{print $1}')
echo "dev-cache-kb=$DU_BASELINE"

# 개발 중 체크
du -sh .next/dev .next/dev/cache/turbopack 2>/dev/null || true
```

Windows라면 PowerShell로 대체합니다.

```powershell
# 앱 디렉터리에서
Get-ChildItem -Recurse .next\dev -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum
```

16.4는 같은 워크로드에서 디스크 캐시가 20–25% 줄어든다고 밝혔기 때문에, dev 캐시가 커지는 팀은 여기서 바로 숫자가 나옵니다.[^1]

### 3) 장시간 dev 세션에서의 누수/정리 확인(turbopackGc)

16.4 실험 옵션인 `experimental.turbopackGc`는 dev 중에 디스크/메모리에서 불필요한 캐시를 회수하는 garbage collector입니다.[^6]

측정은 단순합니다.

- `turbopackGc: false` (기본)로 하루 개발
- `turbopackGc: true`로 하루 개발
- `.next/dev` 증가량 비교

설정 예시:

```ts
// next.config.ts
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  experimental: {
    turbopackGc: true,
  },
}

export default nextConfig
```

여기서 중요한 건 “캐시가 줄었다”만이 아니라, 팀이 실제로 체감하는 현상(노트북이 느려짐, 디스크 부족 경고, CI 캐시 폭증)이 줄었는지를 같이 보는 겁니다.

### 4) CI 캐시 키 설계 실험(최소 2안 비교)

캐시 키는 설계에 따라 결과가 갈립니다. 아래는 ‘틀’이고, 각 팀 레포 구조에 맞춰 바꿔야 합니다.

- 안 A: lockfile + Node + Next 버전
- 안 B: A + next.config hash

next.config가 바뀌는 건 빌드 결과와 캐시 재사용성에 영향을 주는데, 그 영향을 키에 반영하지 않으면 “깨진 캐시를 히트하는” 상황이 늘어납니다.

GitHub Actions라면 대략 이런 구성이 됩니다(개념 예시).

```yaml
- name: Compute cache keys
  id: keys
  shell: bash
  run: |
    echo "node=$(node -v)" >> $GITHUB_OUTPUT
    echo "next=$(node -p \"require('next/package.json').version\")" >> $GITHUB_OUTPUT
    echo "lock=${{ hashFiles('pnpm-lock.yaml') }}" >> $GITHUB_OUTPUT
    echo "nextcfg=${{ hashFiles('apps/web/next.config.ts','apps/web/next.config.js') }}" >> $GITHUB_OUTPUT

- name: Cache Next build cache
  uses: actions/cache@v4
  with:
    path: |
      apps/web/.next/cache
    key: nextcache-${{ runner.os }}-${{ steps.keys.outputs.node }}-${{ steps.keys.outputs.next }}-${{ steps.keys.outputs.lock }}-${{ steps.keys.outputs.nextcfg }}
    restore-keys: |
      nextcache-${{ runner.os }}-${{ steps.keys.outputs.node }}-${{ steps.keys.outputs.next }}-${{ steps.keys.outputs.lock }}-
      nextcache-${{ runner.os }}-${{ steps.keys.outputs.node }}-${{ steps.keys.outputs.next }}-
```

주의할 점은 두 가지입니다.

- `.next/dev`를 CI 캐시에 넣을 이유가 거의 없습니다.
- `.next` 전체를 캐시하면 키 miss 시 다운로드/업로드 비용이 너무 커져서 오히려 느려질 수 있습니다.

### 5) 번들 크기 변화는 ‘전송량’과 ‘캐시 히트’로 다시 측정합니다

16.4는 shared runtime, CSS Modules class name 단축, export mangling을 통해 production 번들을 줄인다고 밝혔습니다.[^1]

여기서 팀에 공유할 숫자는 보통 두 가지가 설득력이 있습니다.

- 빌드 결과물 총량 변화: `.next/static` 또는 배포 아티팩트 전체 크기
- 상위 N개 라우트의 JS/CSS 전송량 변화

Turbopack Bundle Analyzer는 16.1+에서 통합되어 있고, 16.4에서 기능이 강화됐습니다. 라우트 요약, 스냅샷/디프 등이 들어갑니다.[^1][^13]

분석 도구를 붙이면 “번들 3% 감소” 같은 모호한 수치보다, 특정 라우트에서 어떤 의존성이 줄었는지까지 내려갈 수 있어서 CI SLO 재설계에도 연결됩니다.

## 회의론: 캐시가 줄어도 병목이 다른 데 있으면 효과가 제한됩니다

16.4의 캐시 최적화는 기본적으로 I/O와 저장소 비용에 유리한 변화입니다. 그렇다고 항상 체감이 나오지는 않습니다.

- dev 병목이 CPU라면: 압축(Zstandard) 도입이 CPU를 더 쓰는 방향일 수 있습니다. 16.4는 lookup 성능을 위해 메타데이터는 LZ4를 유지한다고 설명하지만, 워크로드에 따라 CPU-IO 트레이드오프가 달라질 수 있습니다.[^1]
- CI가 네트워크 제한이면: 캐시 전송량이 줄어도, 캐시 백엔드의 RTT/스루풋이 병목이면 체감이 적을 수 있습니다.
- 모노레포가 너무 크면: 캐시 압축보다 “캐시가 생성되는 양” 자체가 문제일 수 있습니다. 이때는 캐시 정책(어떤 앱에서 무엇을 캐시할지)과 레포 경계가 먼저입니다.

또 하나는 CSS Modules class name과 관련된 현실적인 이슈입니다.

- class name이 짧아지면 HTML/JS 문자열이 줄어드는 효과는 있지만, E2E 테스트가 class selector에 의존하는 팀이라면 번들러 변경(Turbopack 전환) 자체가 이미 깨짐을 만들 수 있습니다. 이 문제는 이미 16 시점부터 논의됐고, Turbopack에서 CSS Modules naming을 커스터마이즈하기 어렵다는 맥락이 있었습니다.[^8]

16.4의 “짧은 class name”은 이 방향의 문제를 완화하는 쪽이지만, 테스트/모니터링이 class name에 결합된 팀은 여전히 selectors를 정리하는 게 본질적인 해결입니다.

## 앞으로 지켜볼 것: 16.4는 ‘비용 재정의’의 중간 단계입니다

16.4의 메시지는 명확합니다.

- Next/Turbopack은 캐시를 더 적극적으로 쓰는 방향으로 간다.
- 그 캐시가 비용이 되는 지점을 줄이기 위해 압축/정리/GC 같은 시스템 레벨 기능을 계속 넣는다.

16.4에서 내가 특히 “모노레포/CI 운영” 관점으로 관심 있게 보는 옵션은 아래입니다.

- `experimental.turbopackGc`: 캐시가 커지는 걸 자동으로 되돌리는 첫 단추입니다.[^6]
- `experimental.turbopackLazyDynamicImports`: dev에서 client-side dynamic import를 브라우저가 요청할 때까지 미루는 옵션입니다. 대형 앱에서 초기 컴파일량을 줄이는 방향이라, dev 머신 비용(초기 CPU/IO)을 줄일 수 있습니다.[^1][^14]
- `experimental.turbopackAdditionalRoots`: 모노레포에서 symlinked 패키지나 pnpm global store 같은 구조를 다룰 때, 감시/해시/캐시 경계가 어떻게 바뀌는지에 영향을 줍니다. 16.4에서 추가 roots 지원이 들어왔습니다.[^1][^15]

그리고 Cache Components 기본값 전환은, 프런트엔드의 “캐시 설계”가 이제 애플리케이션 레벨의 운영 비용과 더 직접적으로 연결될 거라는 신호이기도 합니다. 특히 `use cache`와 `cacheLife` 같은 API는 성능뿐 아니라 서버 부하와 비용을 조정하는 레버로 점점 더 쓰이게 됩니다.[^10][^16]

## 지금 당장 바꿔야 하는 것: 캐시 키/outputs/SLO를 16.4에 맞춰 재정렬

정리하면 16.4는 “업그레이드하면 빌드가 조금 빨라진다” 수준이 아니라, 로컬과 CI 비용 모델을 다시 쓰게 만드는 릴리스입니다.

- dev 머신에서는 `.next/dev`를 더 이상 방치하면 안 됩니다. 디스크 budget과 정리 정책이 필요하고, 16.4의 압축/compaction 개선과 `turbopackGc`는 그 정책을 가능하게 합니다.[^1][^6]
- CI에서는 캐시 키를 “코드 변경에 따라 매번 무효화”하는 방식에서 벗어나야 합니다. 환경/도구 변화와 코드 변화를 분리하고, 캐시 크기 자체를 SLO에 포함시키는 게 맞습니다.
- 번들 축소는 런타임만의 문제가 아닙니다. 아티팩트/캐시 전송량과 저장량을 줄여 파이프라인의 총 비용을 낮춥니다. shared runtime, CSS Modules class name 단축, export mangling은 그 방향의 신호입니다.[^1][^7]
- create-next-app 기본값이 Cache Components로 바뀐 건, 신규 앱은 캐싱/프리렌더링 정책을 “명시적으로 설계해야” 하는 방향으로 강제된다는 뜻입니다. 모노레포에 새 앱이 계속 추가되는 조직이라면, 이 기본값 변화는 곧바로 CI 정책과 SLO에 반영돼야 합니다.[^1][^2]

결국 16.4에서 비용을 줄이는 가장 현실적인 방법은, 업그레이드 자체보다도 캐시를 한 덩어리로 취급하던 습관을 버리고(로컬 dev 캐시, 빌드 캐시, 태스크 캐시를 분리), 각 캐시가 “어떤 비용을 줄이기 위해 존재하는지”를 SLO로 못 박는 쪽입니다.

## 참고 자료

- [Next.js 16.4 릴리스](https://nextjs.org/blog/next-16-4)
- [Turbopack FileSystem Caching](https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopackFileSystemCache)
- [turbopackGc 설정](https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopackGc)
- [turbopackLazyDynamicImports 설정](https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopackLazyDynamicImports)
- [cacheComponents 설정](https://nextjs.org/docs/app/api-reference/config/next-config-js/cacheComponents)
- [Cache Components 가이드](https://nextjs.org/docs/app/getting-started/partial-prerendering)
- [use cache directive](https://nextjs.org/docs/app/api-reference/directives/use-cache)
- [cacheLife 함수](https://nextjs.org/docs/app/api-reference/functions/cacheLife)
- [How Turbopack chunks your JavaScript](https://nextjs.org/blog/turbopack-chunking)
- [Package Bundling 가이드](https://nextjs.org/docs/pages/guides/package-bundling)
- [Version 16 업그레이드 가이드](https://nextjs.org/docs/app/guides/upgrading/version-16)
- [GitHub Discussion: Add retention controls for the Turbopack dev filesystem cache](https://github.com/vercel/next.js/discussions/94190)
- [GitHub Discussion: CSS Modules class name format in Next.js 16](https://github.com/vercel/next.js/discussions/85869)

[^1]: <https://nextjs.org/blog/next-16-4>
[^2]: <https://nextjs.org/docs/app/api-reference/config/next-config-js/cacheComponents>
[^3]: <https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopackFileSystemCache>
[^4]: <https://github.com/vercel/next.js/discussions/94190>
[^5]: <https://nextjs.org/docs/app/guides/upgrading/version-16>
[^6]: <https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopackGc>
[^7]: <https://nextjs.org/blog/turbopack-chunking>
[^8]: <https://github.com/vercel/next.js/discussions/85869>
[^9]: <https://nextjs.org/docs/app/getting-started/partial-prerendering>
[^10]: <https://nextjs.org/docs/app/api-reference/directives/use-cache>
[^11]: <https://nextjs.org/docs/app/getting-started/installation>
[^12]: <https://nextjs.org/docs/pages/api-reference/turbopack>
[^13]: <https://nextjs.org/docs/pages/guides/package-bundling>
[^14]: <https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopackLazyDynamicImports>
[^15]: <https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopack>
[^16]: <https://nextjs.org/docs/app/api-reference/functions/cacheLife>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
