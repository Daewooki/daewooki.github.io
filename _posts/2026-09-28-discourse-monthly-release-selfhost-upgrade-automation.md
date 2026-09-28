---
title: "Discourse 월간 릴리스에 맞춘 셀프호스팅 업그레이드 운영"
description: "Discourse 월간 릴리스 체계에서 업그레이드·롤백, 플러그인/테마 호환성 검증을 파이프라인으로 고정하는 운영 접근을 정리합니다."
date: 2026-09-28 13:14:22 +0900
categories: ["News", "OpenSource"]
tags: ["discourse", "self-hosting", "release-management", "rollback", "plugin-compatibility", "theme-build"]
render_with_liquid: false
---

## 2026-09-22 월간 릴리스 공지: 운영 관점에서 바뀐 전제

Discourse가 2026-09-22에 9월 월간 릴리스(v2026.9.0)와 함께, 지원되는 다른 버전들의 패치 릴리스도 같이 공지했습니다. 월간 릴리스 공지 글 자체는 짧지만, 운영자의 전제는 크게 바뀝니다. 

- 기능이 지속적으로 누적되는 흐름을 “수시 업데이트”로 취급하기 어렵습니다.
- 월간 릴리스마다 변경량이 꽤 쌓이는 구조라서, 커뮤니티 서비스도 릴리스 관리(검증/점진 롤아웃/복구 리허설)가 필요해집니다.

공식 공지/변경 내역은 아래에서 확인됩니다.

- [September 2026 monthly release](https://meta.discourse.org/t/september-2026-monthly-release/413037?tl=en)
- [v2026.9.0 Changelog](https://releases.discourse.org/changelog/v2026.9.0/)

이 릴리스의 제품 기능(Ask AI 대시보드, MCP server 내장 등)은 눈에 띄지만, 셀프호스팅 운영 입장에서는 그 자체보다 릴리스 cadence가 만드는 운영 비용이 핵심입니다. 월 1회 큰 변경이 전제가 되면, “업그레이드 한번 누르고 끝”이 아니라 **업그레이드 윈도우/롤백**, **플러그인 호환성 매트릭스**, **테마/프론트 번들 빌드 변경**을 월간 이벤트로 정례화해야 합니다.

## 월간 릴리스가 ‘작은 업데이트’가 아닌 이유: 지원 타임라인이 운영을 압박한다

Discourse는 releases.discourse.org에서 릴리스 날짜와 지원 타임라인을 제공합니다. 여기서 중요한 문장은 두 가지입니다.

- 월간 릴리스는 보안 업데이트를 대략 2개월 정도 받습니다.
- 6개월마다 ESR이 지정되고, ESR은 대략 8개월 정도 업데이트를 받습니다.

이 구조는 단순한 “버전 선택” 문제가 아니라 운영 스케줄링 문제입니다.

- 월간 릴리스를 따라가는 경우: 월 1회가 아니라, 지원 종료 전에 다음 월간 릴리스로 넘어가야 하므로 실제로는 4~8주 단위로 upgrade window를 확보해야 합니다.
- ESR을 따라가는 경우: 기능 변경은 덜하지만, 그만큼 ESR 전환 시점의 변경량이 커집니다. 즉, “자주 조금” vs “가끔 많이”의 선택일 뿐, 검증/복구 체계가 없으면 결국 터집니다.

타임라인은 여기에서 확인됩니다.

- [Discourse Releases](https://releases.discourse.org/)

또 한 가지 운영 포인트가 있습니다. latest 채널은 연속 업데이트 성격이 강해서, 월간 릴리스로 운영 리듬을 잡고 싶다면 release/ESR 기반으로 정책을 분명히 하는 편이 낫습니다. 이 구분은 2026-01의 릴리스 공지에서도 설명됩니다.

- [January 2026 Releases](https://meta.discourse.org/t/january-2026-releases/393903?tl=en)

내 블로그에서 systemd, Terraform, etcd 업그레이드를 다룰 때도 같은 결론으로 수렴했습니다. “업그레이드가 쉬운 소프트웨어”는 존재할 수 있지만, “업그레이드 관리가 필요 없는 서비스”는 거의 없습니다.

- [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)
- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)
- [etcd v3.7.2 운영 리허설: 업그레이드·백업·복구·이미지 전략까지](https://daewooki.github.io/posts/etcd-372-kubernetes-ops-rehearsal/)

## 월간 릴리스 시대의 업그레이드 윈도우: ‘작업 시간’이 아니라 ‘검증 가능한 절차’로 고정한다

월간 릴리스에서 업그레이드 윈도우를 잡는 목적은 단순합니다.

- 다운타임(또는 degrade)을 예측 가능하게 만들기
- 실패했을 때 다음 행동(복구/재시도)을 자동으로 실행 가능하게 만들기

여기서 중요한 건 “언제 올릴까”가 아니라, “올릴 때 어떤 입력이 필요하고 어떤 산출물이 남아야 하는가”입니다. 내가 운영에서 고정하는 산출물은 아래 4개입니다.

1) 업그레이드 대상 버전(예: v2026.9.0 / release/2026.9)
2) Discourse core 기준점(브랜치/커밋)
3) 플러그인 목록 + 각 플러그인 기준점(브랜치/커밋)
4) 테마/테마 컴포넌트 기준점(리포지토리 + 커밋)

이 4개가 “증거로 남는” 순간부터 업그레이드 윈도우는 반복 가능한 작업이 됩니다. 반대로, 이게 없으면 롤백도 결국 감으로 하게 됩니다.

운영 정책으로는 다음 형태가 현실적이었습니다.

- 월간 릴리스 공지(Release day) + 1~2일: staging에 후보 적용
- staging에서 24~72시간 관찰(에러 로그, asset 빌드, 플러그인 기능 확인)
- 프로덕션은 트래픽 낮은 시간대에 1회 적용

여기서 staging은 “같은 스펙의 동일한 설치”여야 합니다. Discourse는 플러그인/테마/설정 조합에 민감해서, staging이 프로덕션과 다르면 검증이 거의 무의미해집니다.

## 롤백은 ‘버전 되돌리기’가 아니라 ‘복구’다: Discourse에서 특히 그렇다

Discourse 셀프호스팅에서 롤백을 “이전 버전 컨테이너 재기동” 정도로 생각하면 실제 상황에서 막힙니다. 가장 큰 이유는 DB migration입니다.

Discourse Meta의 지원 답변에서도 요지는 명확합니다.

- DB가 업그레이드된 뒤에는 단순한 버전 롤백은 지원되지 않습니다.

- [Rollback upgrades](https://meta.discourse.org/t/rollback-upgrades/116074?tl=en)

즉, 운영자가 원하는 건 rollback이 아니라 “복구 루트”입니다. 내가 잡는 복구 루트는 두 단계입니다.

- (A) 업그레이드 직전 백업을 가지고, 동일 버전으로 restore 가능한지
- (B) 업그레이드 실패 시점이 migration 전인지 후인지 구분하고, 후라면 즉시 restore 루트로 전환 가능한지

Discourse는 CLI로 백업/복구가 가능합니다.

- [Backup discourse from the command line](https://meta.discourse.org/t/backup-discourse-from-the-command-line/64364?tl=en)
- [Create, download, and restore a backup of your Discourse database](https://meta.discourse.org/t/create-download-and-restore-a-backup-of-your-discourse-database/122710?tl=en)

이 문서들을 읽으면 공통적으로 강조되는 제약이 있습니다.

- restore는 덮어쓰기이며, 실수하면 기존 데이터가 날아갑니다.
- restore 대상은 “버전이 맞아야” 합니다. 

이 제약 때문에, 월간 릴리스 운영에서 현실적인 결론은 하나입니다.

- 실패했을 때는 “이전 버전으로 돌아간다”가 아니라, “업그레이드 전 상태로 복구한다”를 자동화해야 합니다.

복구 자동화에서 꼭 포함해야 하는 데이터는 DB/업로드 파일만이 아닙니다.

- /var/discourse/containers/app.yml
- 플러그인/테마의 기준점(커밋 SHA)

app.yml과 플러그인 커밋이 없으면, 복구 후 rebuild에서 다시 다른 코드가 들어오면서 재현이 깨집니다.

## /var/discourse를 GitOps처럼 다루는 방식: app.yml + lockfile

Discourse 셀프호스팅을 운영하면서 가장 자주 겪는 실패는 “같은 업그레이드를 다시 재현할 수 없다”입니다. 버튼 한번 누르고 끝내는 방식은 그 순간엔 빠르지만, 장애 시점에는 아무것도 남지 않습니다.

나는 /var/discourse를 그대로 Git에 올리지는 않더라도, 운영에 필요한 선언형 파일은 별도 리포지토리로 관리하는 쪽으로 정리했습니다.

예시 구조는 아래처럼 잡았습니다.

```text
discourse-ops/
  containers/
    app.yml
  lock/
    discourse.lock.yml
  scripts/
    fetch_release.py
    build_candidate.sh
    backup_before_upgrade.sh
    restore_full.sh
  docs/
    runbook.md
```

### lockfile의 역할

lockfile은 “이번 윈도우에 들어갈 모든 코드의 기준점”입니다.

- core: release/2026.9 (또는 특정 커밋)
- plugins: 각 플러그인 repo + commit
- themes: 각 테마 repo + commit

예시는 아래처럼 단순하게 시작했습니다.

```yaml
# lock/discourse.lock.yml
release:
  channel: release
  version: v2026.9.0
  branch: release/2026.9

core:
  repo: https://github.com/discourse/discourse.git
  ref: release/2026.9

plugins:
  - name: docker_manager
    repo: https://github.com/discourse/docker_manager.git
    ref: 4c2d0e1b6f...
  - name: discourse-prometheus
    repo: https://github.com/discourse/discourse-prometheus.git
    ref: 9f8a77c4d4...

themes:
  - name: my-brand-theme
    repo: https://github.com/our-org/discourse-theme-brand.git
    ref: 2f0b1c0a71...
```

이 파일이 있으면, staging과 prod 모두 같은 입력으로 rebuild가 가능합니다.

### core 버전은 어디서 가져오나

Discourse는 릴리스/지원 타임라인을 releases.discourse.org에서 제공하고, Discourse repo에는 versions.json이 있습니다.

- [Discourse Releases](https://releases.discourse.org/)
- [discourse/versions.json](https://github.com/discourse/discourse/blob/main/versions.json)

운영 자동화에서는 “릴리스를 읽고 사람이 판단”이 아니라, “릴리스를 읽고 후보를 만들고 사람이 승인” 형태로 가야 부담이 줄어듭니다.

## 업그레이드 윈도우 자동화: 후보 생성 → staging 적용 → prod 승격

여기부터는 실제로 굴러가는 형태로 적습니다. 전제는 흔한 단일 VM/단일 컨테이너(standalone) 구성입니다.

- 호스트: Ubuntu Linux
- 설치 경로: /var/discourse
- 업그레이드: discourse_docker의 launcher rebuild

### 1) 월간 릴리스 후보 버전 감지 스크립트

releases.discourse.org는 사람이 보기 좋게 되어 있고, 자동화엔 versions.json 쪽이 다루기 편했습니다. 아래 스크립트는 versions.json을 가져와서 가장 최신 monthly release를 찾아 lockfile의 release 섹션을 채우는 형태입니다.

필요 도구:

- python3 (3.11+ 권장)

```python
#!/usr/bin/env python3
# scripts/fetch_release.py

import json
import re
import sys
import urllib.request

VERSIONS_JSON = "https://raw.githubusercontent.com/discourse/discourse/main/versions.json"

def load_versions():
    with urllib.request.urlopen(VERSIONS_JSON, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def parse_year_month(s: str):
    # keys like "2026.9" or "2026.10"
    m = re.fullmatch(r"(\d{4})\.(\d{1,2})", s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))

def latest_monthly_release(versions):
    # versions.json structure can evolve; defensively handle.
    releases = versions.get("discourse", {})
    candidates = []
    for k, v in releases.items():
        ym = parse_year_month(k)
        if not ym:
            continue
        # heuristic: ESR flag exists
        if isinstance(v, dict) and v.get("esr") is False:
            candidates.append((ym, k, v))

    if not candidates:
        raise RuntimeError("No monthly release candidates found")

    candidates.sort(key=lambda x: x[0])
    return candidates[-1]

def main():
    versions = load_versions()
    (year, month), key, meta = latest_monthly_release(versions)

    # Discourse가 월간 릴리스 브랜치를 release/YYYY.M 형태로 쓰는 흐름을 전제로 둠
    branch = f"release/{year}.{month}"

    print(json.dumps({
        "year": year,
        "month": month,
        "key": key,
        "branch": branch,
        "supportEndDate": meta.get("supportEndDate"),
    }, indent=2))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

실행 예시(출력은 예시이며 실제 값은 시점에 따라 달라집니다).

```bash
python3 scripts/fetch_release.py
```

예상 출력 예시:

```json
{
  "year": 2026,
  "month": 9,
  "key": "2026.9",
  "branch": "release/2026.9",
  "supportEndDate": "2026-11-24"
}
```

이 출력이 있어야 “이번 달 업그레이드 대상”이 사람 머리에서 빠지고, 파이프라인의 입력으로 고정됩니다.

### 2) 업그레이드 직전 백업: 실패 가능성을 전제로 둔다

Discourse는 컨테이너 안에서 discourse 커맨드로 백업을 만들 수 있습니다.

- [Backup discourse from the command line](https://meta.discourse.org/t/backup-discourse-from-the-command-line/64364?tl=en)

standalone 기준으로, 나는 rebuild 전에 반드시 백업 파일명까지 로그로 남기게 했습니다.

```bash
#!/usr/bin/env bash
# scripts/backup_before_upgrade.sh

set -euo pipefail

cd /var/discourse

# 백업은 시간이 걸릴 수 있으니, 타임아웃/모니터링은 운영 환경에 맞춰 추가
./launcher run app discourse backup

# 백업 파일은 보통 아래 경로에 생성됨(standalone 기준)
# /var/discourse/shared/standalone/backups/default/
ls -al /var/discourse/shared/standalone/backups/default/ | tail -n 20
```

백업 파일은 원격으로 빼두지 않으면 결국 같은 디스크에 남습니다. 월간 릴리스에서는 디스크 풀(특히 uploads) 때문에 실패하는 경우도 많아서, 백업이 같은 디스크에만 있으면 복구 루트가 같이 죽습니다.

여기서 내 판단은 단순했습니다.

- 월간 릴리스 운영에서 진짜 비용은 “백업 생성”이 아니라 “복구 성공률”입니다.
- 따라서 백업은 만들고 끝이 아니라, restore 리허설이 포함되어야 합니다.

이 부분은 예전에 Linux stable 커널 롤아웃 체크리스트를 정리할 때와 결이 같습니다. 배포보다 어려운 건 되돌릴 수 있는 배포입니다.

- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)

### 3) staging rebuild를 ‘후보 적용’으로 고정한다

업그레이드는 결국 ./launcher rebuild app로 끝납니다. 문제는 rebuild 결과가 환경(plugins/themes/node toolchain)에 민감하다는 점입니다.

- 플러그인이 빌드 시스템 전환을 따라오지 못하면 asset compile에서 터집니다.
- 테마가 전역 변수/구 번들 전제를 가지고 있으면 브라우저에서 런타임 에러가 납니다.

그래서 staging에서는 rebuild 자체를 “검증 스위치”로 삼는 편이 낫습니다.

여기서 중요한 건, staging이 prod와 같아야 한다는 점과, staging rebuild가 실패했을 때 로그가 남아야 한다는 점입니다.

## 플러그인 호환성 매트릭스: ‘지금 compatible한가’를 매달 다시 증명해야 한다

월간 릴리스에서 가장 자주 터지는 건 core 자체가 아니라 플러그인입니다. Discourse는 공식 플러그인도 많지만, 셀프호스팅 커뮤니티는 커스텀/서드파티 플러그인을 얹는 순간부터 운명이 갈립니다.

여기서 2026년에 중요한 변화가 하나 더 들어왔습니다. 플러그인의 JavaScript 빌드 시스템이 바뀌고, native ES module 기반으로 전환되는 흐름이 명시됐습니다.

- [Introducing a new build system for plugins](https://meta.discourse.org/t/introducing-a-new-build-system-for-plugins/398713?tl=en)

이 변화는 운영 관점에서 두 가지 의미가 있습니다.

1) 플러그인의 JS가 “대충 돌아가는” 구간이 줄어듭니다. 빌드/로딩 과정에서 더 엄격하게 깨집니다.
2) 빌드가 서버 rebuild 시간에 영향을 주고, 리소스가 작은 머신에서 더 체감됩니다(Discourse 쪽도 인기 플러그인 precompile/번들링을 언급합니다).

### 호환성 매트릭스의 최소 단위

내가 월간 릴리스에 맞춰 관리하는 호환성 매트릭스의 최소 단위는 아래입니다.

- core ref(월간 릴리스 브랜치)
- plugin repo + ref
- 결과: build 성공/실패, 런타임 에러 유무, 관리자가 확인해야 할 기능 리스트

이걸 표로 만들면 대충 이런 형태입니다.

```text
core: release/2026.9

| plugin | ref | build | runtime | note |
|-------|-----|-------|---------|------|
| docker_manager | 4c2d... | pass | pass | admin/upgrade 확인 |
| discourse-prometheus | 9f8a... | pass | pass | /metrics 스크랩 확인 |
| custom-sso | a81b... | fail | - | duplicate export 에러 |
```

핵심은 표 자체가 아니라, 표가 자동으로 생성되도록 만드는 것입니다.

### 플러그인 ref를 고정하는 방법: 브랜치로 고정 vs 커밋으로 고정

Discourse Meta에는 “특정 플러그인 버전을 checkout하고 싶다”는 질문이 오래전부터 있습니다.

- [Checkout specific version of plugin?](https://meta.discourse.org/t/checkout-specific-version-of-plugin/167919)

여기서 운영 현실은 이렇습니다.

- 많은 플러그인은 “릴리스 태그/호환 브랜치”를 잘 제공하지 않습니다.
- app.yml에서 git clone을 해도 결국 기본 브랜치 최신을 따라가 버리기 쉽습니다.

그래서 월간 릴리스 운영에서는 커밋 SHA 고정이 필요해집니다. 이때 discourse_docker의 hooks가 유용합니다. discourse_docker는 템플릿에서 hook을 제공하고, templates에서 hook 위치를 검색하라고 안내합니다.

- [discourse/discourse_docker](https://github.com/discourse/discourse_docker)

내 경우는 app.yml에 플러그인을 clone한 다음, after_code hook에서 커밋을 checkout하는 방식으로 맞췄습니다.

예시(app.yml 일부):

```yaml
hooks:
  after_code:
    - exec:
        cd: $home/plugins
        cmd:
          - cd docker_manager && git fetch --all && git checkout 4c2d0e1b6f
          - cd discourse-prometheus && git fetch --all && git checkout 9f8a77c4d4
```

이 방식의 단점도 명확합니다.

- 커밋이 삭제되거나 force push로 사라지면 재현이 깨집니다.
- 플러그인별로 fetch 시간이 늘어납니다.

그래도 월간 릴리스에서는 “재현 가능성”이 “편의성”보다 앞선다고 봤습니다. 장애 시점에 필요한 건 최신이 아니라 동일 조건입니다.

### 호환성 매트릭스 자동 생성: rebuild 로그에서 ‘실패 지점’을 구조화한다

가장 단순한 자동화는 이겁니다.

- staging rebuild의 stdout/stderr를 파일로 보관
- 특정 키워드(PLUGIN compile error, RollupError 등)를 grep
- 실패한 플러그인을 lockfile에 표시하고, 그 상태로는 prod 승격을 막음

Discourse 플러그인 빌드 오류 사례는 위 플러그인 빌드 시스템 공지 글의 댓글에도 직접 나옵니다(duplicate export 류). 이런 에러는 “운 좋으면 지나가고 운 나쁘면 터지는” 게 아니라, 특정 조합에서 매번 재현됩니다.

즉, 매달 재현 가능한 매트릭스를 쌓는 방식이 운영 효율이 더 좋았습니다.

## 테마/프론트 번들 빌드 변경: 월간 릴리스에서 가장 조용하게 서비스 품질을 깎는 칼

플러그인은 실패하면 대개 rebuild 단계에서 터져서 빨리 알아차립니다. 테마는 다릅니다.

- 빌드는 통과했는데, 특정 페이지에서만 UI가 깨집니다.
- 특정 브라우저/특정 사용자 그룹에서만 composer가 이상해집니다.

2026년에는 Discourse core의 JS 빌드 시스템도 큰 변화가 있었습니다.

- [Introducing a new JS build system for Discourse core](https://meta.discourse.org/t/introducing-a-new-js-build-system-for-discourse-core/403908?tl=en)

요점은 다음입니다.

- ember-cli/webpack에서 rolldown 기반으로 이동
- JS를 native ES module로 빌드
- 개발 경험(로컬)도 bin/dev 기반으로 바뀜

운영 서버는 pre-compiled assets를 쓰기 때문에 “프로덕션은 변화가 없을 것”이라는 설명이 있지만, 셀프호스팅에서 테마/플러그인을 얹는 순간부터 서버 rebuild 과정은 결국 영향을 받습니다.

그리고 v2026.9.0 changelog를 보면, core 내부에서도 번들 엔트리포인트 정리 같은 변화가 들어갑니다. 예를 들어 vendor 엔트리포인트 제거 같은 항목은, 전역 스코프를 전제한 커스텀 코드가 있을 때 조용히 부러질 수 있는 신호입니다.

- [v2026.9.0 Changelog](https://releases.discourse.org/changelog/v2026.9.0/)

### 테마를 ‘DB 설정’이 아니라 ‘빌드 대상’으로 간주한다

운영에서 테마가 위험한 이유는 “관리자 화면에서 설정하는 것”처럼 보여서입니다. 실제로는 프론트엔드 코드입니다.

그래서 월간 릴리스 운영에서는 테마/테마 컴포넌트를 다음처럼 다뤄야 합니다.

- 리포지토리로 관리
- 커밋 SHA로 고정
- lint/build 워크플로우를 월간 릴리스와 같이 돌림

이 흐름을 현실적으로 가능하게 해주는 도구가 skeleton 기반 워크플로우입니다. 2026-09에는 skeleton을 최신 권장 설정으로 업데이트하는 도구가 공개됐습니다.

- [Introducing @discourse/update-skeleton](https://meta.discourse.org/t/introducing-discourse-update-skeleton/412460)

이 도구는 pnpx로 실행해서 theme/plugin에 권장 config(워크플로우, lint, tsconfig, Gemfile 등)를 끌어오는 식입니다. 월간 릴리스에서는 “한 번 세팅”보다 “권장 세팅을 계속 따라가는 비용”이 더 크기 때문에, 이런 도구를 CI 파이프라인에 묶는 쪽이 유리합니다.

### (실행 가능한) 테마/플러그인 리포지토리 정비 자동화 예시

전제:

- Node.js 22.x
- pnpm 10.x
- Ruby/Bundler

테마(또는 플러그인) 리포지토리에서 아래를 실행하는 작업을 월간 릴리스마다 자동으로 수행할 수 있습니다.

```bash
# repo root에서
pnpx @discourse/update-skeleton@latest
pnpm install
pnpm lint
```

여기서 중요한 건 결과물입니다.

- 월간 릴리스 적용 전에, 테마/플러그인의 “권장 빌드 규칙”을 먼저 최신으로 맞춰둠
- 빌드 규칙이 바뀌어 깨질 거면 staging rebuild가 아니라 CI에서 먼저 깨짐

내 경험상, 이 방향으로 가면 운영 장애가 “서비스 장애”가 아니라 “PR 실패”로 이동합니다. 월간 릴리스 시대에 이게 가장 값싼 형태입니다.

## 월간 릴리스에 맞춘 ‘점진 롤아웃’은 Discourse에서 어떤 형태가 현실적인가

대규모 서비스처럼 트래픽 1% 카나리를 하기는 어렵습니다. Discourse를 셀프호스팅하는 환경에서 점진 롤아웃의 현실적인 형태는 대개 두 가지 중 하나입니다.

1) 별도 staging 호스트에서 동일 데이터 restore → 업그레이드 검증
2) 프로덕션에서 maintenance window를 짧게 잡고, 실패 시 즉시 restore 루트로 전환

여기서 1)번이 훨씬 좋지만, 비용이 듭니다. 그렇다고 2)번만 하면 복구 경험이 축적되지 않습니다.

내 결론은 중간 형태였습니다.

- 월간 릴리스마다 staging restore 리허설을 매번 하지는 않더라도, 최소 월 1회는 “복구 루트를 실제로 실행”해 봅니다.
- Android Security Bulletin을 운영에 반영할 때도 같은 원칙을 썼습니다. 패치 자체보다, 패치 체인을 운영 조직이 소화할 수 있는지가 더 중요합니다.

- [Android Security Bulletin 2026-09로 다시 짜는 모바일 보안 업데이트 운영](https://daewooki.github.io/posts/android-security-bulletin-patch-level-ops/)

## 반론과 회의론: 월간 릴리스가 운영을 더 어렵게 만드는 지점

월간 릴리스가 좋은 점만 있는 건 아닙니다. 운영에서 부정적인 효과도 분명합니다.

- 매달 검증/승격/관찰이 생기면서 운영 리듬을 잡지 못하면 피로도가 급증합니다.
- 플러그인 생태계는 릴리스 리듬이 다양한데, core는 월간으로 달립니다. 셀프호스팅에서 플러그인 1개가 곧 단일 장애점이 됩니다.
- 테마/커스텀 JS가 많은 커뮤니티는 결국 프론트엔드 유지보수 비용을 떠안게 됩니다.

그래서 월간 릴리스 시대에 중요한 건 “업그레이드 자동화”가 아니라 “자동화의 범위 설정”입니다.

- 모든 걸 자동화하려고 하면 유지보수 대상만 늘어납니다.
- 대신, 자동화는 업그레이드/복구/검증의 골격만 담당하고, 나머지는 사람이 확인할 항목을 최소화하는 방향이 낫습니다.

이 판단은 내가 Terraform 업그레이드 체크리스트를 만들면서 느낀 것과 같습니다. 버전 고정은 안전을 보장하지 않고, 절차 고정이 안전을 만듭니다.

## 앞으로 지켜볼 것: 월간 릴리스가 ‘운영 가능한 속도’로 정착하는 조건

내가 Discourse 월간 릴리스 체계에서 특히 보고 있는 건 세 가지입니다.

- releases.discourse.org의 타임라인이 운영 자동화에 더 친화적인 형태(API/머신리더블)로 강화되는지
- 플러그인 precompile/캐싱이 실제로 셀프호스팅 rebuild 시간을 유의미하게 줄이는지(리소스 작은 호스트에서 특히)
- theme/plugin skeleton과 update-skeleton 같은 도구 체인이 “한 번 세팅”이 아니라 “계속 따라가기”를 얼마나 저렴하게 만드는지

이 중 3번째는 이미 방향이 나왔습니다. update-skeleton은 운영 관점에서 단순 편의 도구가 아니라, 월간 릴리스를 버틸 수 있게 만드는 전제 조건에 가깝습니다.

## 운영 결론: 월간 릴리스는 자동화가 없으면 운영 비용으로 전환된다

2026-09-22 월간 릴리스 공지는 Discourse가 기능을 많이 추가했다는 뉴스가 아니라, 커뮤니티 플랫폼도 월 단위 릴리스 관리가 필요해졌다는 신호로 읽는 편이 맞습니다.

내 운영 기준에서 월간 릴리스 대응의 핵심은 화려한 배포 전략이 아니라, 세 가지를 매달 증명 가능한 형태로 반복하는 것입니다.

- 업그레이드 윈도우는 시간표가 아니라 산출물(lockfile/로그/백업 파일명)로 고정한다.
- 롤백은 “버전 되돌리기”가 아니라 “복구 리허설 성공률”로 정의한다.
- 플러그인/테마는 설정이 아니라 코드이며, 월간 릴리스에 맞춰 호환성 매트릭스를 자동으로 갱신한다.

이 정도까지 고정하면, Discourse 월간 릴리스는 부담스러운 이벤트가 아니라 통제 가능한 월간 작업으로 떨어집니다.

## 참고 자료

- [September 2026 monthly release](https://meta.discourse.org/t/september-2026-monthly-release/413037?tl=en)
- [Discourse Releases](https://releases.discourse.org/)
- [v2026.9.0 Changelog](https://releases.discourse.org/changelog/v2026.9.0/)
- [January 2026 Releases](https://meta.discourse.org/t/january-2026-releases/393903?tl=en)
- [Introducing a new build system for plugins](https://meta.discourse.org/t/introducing-a-new-build-system-for-plugins/398713?tl=en)
- [Introducing a new JS build system for Discourse core](https://meta.discourse.org/t/introducing-a-new-js-build-system-for-discourse-core/403908?tl=en)
- [Introducing @discourse/update-skeleton](https://meta.discourse.org/t/introducing-discourse-update-skeleton/412460)
- [Backup discourse from the command line](https://meta.discourse.org/t/backup-discourse-from-the-command-line/64364?tl=en)
- [Create, download, and restore a backup of your Discourse database](https://meta.discourse.org/t/create-download-and-restore-a-backup-of-your-discourse-database/122710?tl=en)
- [Rollback upgrades](https://meta.discourse.org/t/rollback-upgrades/116074?tl=en)
- [Checkout specific version of plugin?](https://meta.discourse.org/t/checkout-specific-version-of-plugin/167919)
- [discourse/versions.json](https://github.com/discourse/discourse/blob/main/versions.json)
- [discourse/discourse_docker](https://github.com/discourse/discourse_docker)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
