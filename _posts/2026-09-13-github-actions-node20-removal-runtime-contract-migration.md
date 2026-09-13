---
title: "GitHub Actions Node 20 제거 전에 런타임 계약 재정리와 마이그레이션 플랜"
description: "Node 20 제거(2026-09-23) 전, 워크플로·액션·러너·ARM32까지 한 번에 정리하는 실행 계획입니다."
date: 2026-09-13 12:51:37 +0900
categories: ["DevOps", "GitHub Actions"]
tags: ["github-actions", "ci-cd", "self-hosted-runner", "nodejs", "supply-chain", "arm64"]
render_with_liquid: false
---

## removal date가 촉발한 문제: 버전업이 아니라 계약 파기입니다
GitHub는 GitHub Actions runners에서 Node 20 deprecation을 진행 중이고, **Node 20 제거(removal) 날짜가 2026-09-23으로 고정**됐습니다. 해당 날짜는 GitHub Changelog 글의 편집자 노트(2026-08-25)로 갱신됐고, 2026-06-16부터는 기본 런타임이 Node 24로 전환됐습니다. 테스트를 위해 `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`를 제공하고, 일시적 opt-out으로 `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true`를 제공하지만, 그 opt-out도 2026-09-23까지만 유효하다고 못 박았습니다[^1].

이걸 단순히 “워크플로에서 Node 버전 한 줄 올리면 되겠지”로 보면 사고가 납니다. 여기서 깨지는 것은 애플리케이션의 Node가 아니라, **CI 런타임 계약(CI runtime contract)**입니다.

- 워크플로가 호출하는 액션은 어떤 런타임을 요구하는가
- 그 런타임은 runner에 내장되어 있는가(그리고 언제 삭제되는가)
- self-hosted runner는 어떤 아키텍처/OS로 굴러가고, 그 조합이 앞으로도 지원되는가
- (특히 ARM32) “지원된다고 문서에 적힌 것”과 “현실적으로 실행 가능한 것” 사이의 간극을 누가 메우는가

이번 이슈는 워크플로 파일만 고치는 작업이 아니라, 액션/러너/이미지/아키텍처를 묶어 CI 전체의 계약을 다시 쓰는 작업입니다.

## Node 20 제거가 실제로 깨뜨리는 것: JavaScript action 런타임
GitHub Actions에서 “Node 20을 쓰는 주체”가 두 가지로 갈립니다.

1) **내 워크플로의 `run:` 스텝에서 실행되는 Node**
- 예: `actions/setup-node`로 Node를 설치/선택하고 `npm ci`를 돌리는 케이스

2) **JavaScript action 자체를 실행하는 Node**
- 예: `actions/checkout`, `actions/cache`, `actions/upload-artifact` 같은 액션은 “내가 설치한 Node”가 아니라, runner가 들고 있는 내장 Node로 실행됩니다.

두 번째가 핵심입니다. Actions runner는 내장 Node를 별도 경로로 갖고 있고, JavaScript action은 `$PATH`의 `node`가 아니라 그 내장 Node로 실행됩니다. runner 문서에도 “`<runner_root>/externals/node20/` 또는 `<runner_root>/externals/node24/`의 내장 node로 실행된다”고 명시돼 있습니다[^2].

즉, 워크플로에서 `setup-node`로 Node 24를 설치해도, 액션이 `runs.using: node20`이라면 runner는 node20 내장을 요구합니다. 2026-09-23 이후에는 그 내장이 사라지니, 액션 실행 자체가 실패할 수 있습니다.

여기서 “액션이 Node 20 기반인지”는 워크플로 YAML이 아니라, **액션 저장소의 `action.yml`의 `runs.using`**에 박혀 있습니다. GitHub 공식 문서의 메타데이터 문법은 JavaScript action에서 `runs.using`으로 `node20` 또는 `node24`를 지정한다고 적습니다[^3].

## ARM32는 다른 차원의 문제: 구성 변경으로 해결되지 않습니다
GitHub Changelog 글은 Node 24 관련 호환성 문제를 두 개로 명시합니다.

- Node 24는 macOS 13.4 이하와 호환되지 않는다
- Node 24는 ARM32에 대한 공식 지원이 없으므로, ARM32 self-hosted runner는 Node 20 deprecation 이후 더 이상 지원되지 않는다[^1]

여기서 두 번째가 치명적입니다. GitHub Docs의 self-hosted runner 레퍼런스는 아키텍처로 `ARM32`(Linux)를 여전히 “지원” 목록에 넣어 두고 있습니다[^4]. 하지만 Node 24가 ARM32를 공식 지원하지 않는다면, runner가 내장 Node 24를 ARM32에 제공하기 어렵고(혹은 제공하지 않는다고 보는 편이 안전하고), JavaScript action 런타임은 붕 뜹니다.

이 문제는 “워크플로에서 env 하나 더 넣자”로 해결되지 않습니다. **ARM32 runner 자체가 런타임 계약을 충족할 수 없게 되는 것**이므로, 아키텍처 전환(ARM64 또는 x64)로 답이 수렴합니다.

Node.js 쪽에서도 같은 방향이 보입니다. Node.js 22→24 마이그레이션 문서는 Node.js 24.0.0부터 “32-bit Linux on armv7”가 빠졌다고 명시합니다[^5]. Node 저장소의 BUILDING 문서에서도 GNU/Linux armv7이 Node.js 24에서 “downgraded”됐다고 적혀 있습니다[^6].

GitHub Actions의 ARM32 이슈는 GitHub만의 변덕이 아니라, upstream 런타임 생태계가 이미 ARM32를 주력 지원선 밖으로 밀어낸 결과에 가깝습니다.

## (오늘 2026-09-13 KST 기준) 10일짜리 실행 플랜: 워크플로→업스트림 액션→self-hosted/ARM32를 한 번에
여기서는 “꼭 오늘부터 굴릴 수 있는” 형태로 단계와 산출물을 정의합니다. 핵심은 3가지 인벤토리를 동시에 뽑아내는 겁니다.

- 워크플로가 참조하는 액션 목록(직접/간접)
- 각 액션이 요구하는 `runs.using`(node20인지 node24인지)
- self-hosted runner(특히 ARM32)의 실제 배치 현황

### D-10 ~ D-9 (2026-09-13~14): 액션 의존성 인벤토리 만들기
먼저 “우리 repo가 어떤 액션을 쓰는지”부터 파악해야 합니다. 경험상 실패하는 팀은 여기서 `actions/checkout` 같은 obvious한 것만 보고 끝내는데, 진짜 문제는 다음에 있습니다.

- 오래전에 핀(tag 또는 SHA) 박아둔 third-party action
- composite action 내부의 `uses:`
- reusable workflow(`uses: org/repo/.github/workflows/..@ref`) 내부의 `uses:`

아래는 내 쪽에서 실제로 써먹는 “최소 도구” 조합입니다.

- `ripgrep`(rg): 빠른 텍스트 인벤토리
- `yq`: YAML에서 `uses`만 추출
- `gh`: ref(SHA) resolve + 파일 fetch
- Python: 재귀(워크플로 → composite/reusable) 분석

#### 1) 1차로 “사용 중인 uses 문자열”만 뽑기
```bash
# repo 루트에서
rg -n "^\s*-\s*uses:" .github/workflows \
  | sed -E 's/^([^:]+):([0-9]+):\s*-\s*uses:\s*//'
```

이 결과는 대개 이런 형태가 됩니다.

- `actions/checkout@v4`
- `docker/login-action@v3`
- `org/some-action@3f1c...` (SHA pin)
- `org/repo/path/to/action@v2`
- `org/repo/.github/workflows/reusable.yml@v1`

여기까진 “표면”입니다. composite/reusable 내부로 들어가야 합니다.

#### 2) 실제 분석 스크립트: node20 기반 액션을 찾아서 리스트업
아래 스크립트는 다음을 합니다.

- `.github/workflows/**/*.yml`에서 `uses:`를 수집
- 외부 액션에 대해 `action.yml` 또는 `action.yaml`을 fetch
- `runs.using`이 `node20`인지 확인
- composite action이면 내부 steps의 `uses:`를 추가로 수집(깊이 제한)
- reusable workflow(`.github/workflows/*.yml`을 `uses:`로 호출하는 형태)는 YAML을 fetch해서 동일하게 스캔

실행을 위해 `gh` 로그인만 되어 있으면 됩니다.

```python
#!/usr/bin/env python3
import os
import re
import json
import subprocess
from pathlib import Path

# pip install pyyaml
import yaml

USES_RE = re.compile(r"^[^/\s]+/[^\s@]+(?:/[^@\s]+)?@[^\s]+$")

def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{p.stderr}")
    return p.stdout

def gh_api_json(endpoint: str) -> dict:
    out = run(["gh", "api", endpoint])
    return json.loads(out)

def gh_api_raw(endpoint: str) -> str:
    return run(["gh", "api", "--header", "Accept: application/vnd.github.raw", endpoint])

def parse_uses(value: str):
    value = str(value).strip().strip('"').strip("'")
    if not value:
        return None
    # ignore docker:// and local ./
    if value.startswith("docker://") or value.startswith("./") or value.startswith("$/"):
        return None
    if not USES_RE.match(value):
        return None
    return value

def split_uses(uses: str):
    # owner/repo/path@ref  or owner/repo@ref
    repo_part, ref = uses.rsplit("@", 1)
    parts = repo_part.split("/")
    owner = parts[0]
    repo = parts[1]
    path = "/".join(parts[2:]) if len(parts) > 2 else ""
    return owner, repo, path, ref

def fetch_repo_file(owner: str, repo: str, path: str, ref: str) -> str | None:
    # GET /repos/{owner}/{repo}/contents/{path}?ref=...
    endpoint = f"/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    try:
        return gh_api_raw(endpoint)
    except Exception:
        return None

def load_yaml(text: str) -> dict | None:
    try:
        return yaml.safe_load(text)
    except Exception:
        return None

def scan_yaml_for_uses(doc) -> list[str]:
    found = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "uses":
                    u = parse_uses(v)
                    if u:
                        found.append(u)
                else:
                    walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(doc)
    return found

def classify_action(owner: str, repo: str, action_path: str, ref: str):
    # action metadata file is either action.yml or action.yaml
    base = action_path.strip("/")
    candidates = []
    if base:
        candidates.append(f"{base}/action.yml")
        candidates.append(f"{base}/action.yaml")
    else:
        candidates.append("action.yml")
        candidates.append("action.yaml")

    for meta_path in candidates:
        raw = fetch_repo_file(owner, repo, meta_path, ref)
        if not raw:
            continue
        meta = load_yaml(raw)
        if not isinstance(meta, dict):
            continue

        runs = meta.get("runs")
        if not isinstance(runs, dict):
            continue

        using = runs.get("using")
        if using in ("node20", "node24"):
            return {
                "kind": "js-action",
                "runs_using": using,
                "meta_path": meta_path,
                "nested_uses": [],
            }

        if using == "composite":
            nested = []
            steps = runs.get("steps")
            if isinstance(steps, list):
                for s in steps:
                    if isinstance(s, dict) and "uses" in s:
                        u = parse_uses(s["uses"])
                        if u:
                            nested.append(u)
            return {
                "kind": "composite",
                "runs_using": using,
                "meta_path": meta_path,
                "nested_uses": nested,
            }

        if using == "docker":
            return {
                "kind": "docker",
                "runs_using": using,
                "meta_path": meta_path,
                "nested_uses": [],
            }

        return {
            "kind": "unknown",
            "runs_using": str(using),
            "meta_path": meta_path,
            "nested_uses": [],
        }

    return None

def is_reusable_workflow(path: str) -> bool:
    return path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))

def main():
    # 1) entrypoint: local workflows
    entry_uses = []
    for wf in Path(".github/workflows").rglob("*.yml"):
        doc = load_yaml(wf.read_text("utf-8"))
        if doc:
            entry_uses.extend(scan_yaml_for_uses(doc))

    # 2) BFS with depth limit
    queue = [(u, 0, "workflow") for u in sorted(set(entry_uses))]
    seen = set()

    results = []

    while queue:
        uses, depth, from_where = queue.pop(0)
        if uses in seen:
            continue
        seen.add(uses)

        owner, repo, path, ref = split_uses(uses)

        # reusable workflow
        if path and is_reusable_workflow(path):
            raw = fetch_repo_file(owner, repo, path, ref)
            doc = load_yaml(raw) if raw else None
            nested = scan_yaml_for_uses(doc) if doc else []
            results.append({
                "uses": uses,
                "type": "reusable-workflow",
                "from": from_where,
                "depth": depth,
                "nested_uses": nested,
            })
            if depth < 3:
                for n in nested:
                    queue.append((n, depth + 1, uses))
            continue

        info = classify_action(owner, repo, path, ref)
        if not info:
            results.append({
                "uses": uses,
                "type": "unresolved",
                "from": from_where,
                "depth": depth,
                "nested_uses": [],
            })
            continue

        results.append({
            "uses": uses,
            "type": info["kind"],
            "runs_using": info["runs_using"],
            "meta_path": info["meta_path"],
            "from": from_where,
            "depth": depth,
            "nested_uses": info["nested_uses"],
        })

        if info["kind"] == "composite" and depth < 3:
            for n in info["nested_uses"]:
                queue.append((n, depth + 1, uses))

    # 3) report
    node20 = [r for r in results if r.get("runs_using") == "node20"]

    print("== Summary ==")
    print(f"total refs: {len(results)}")
    print(f"node20 js actions: {len(node20)}")

    print("\n== Node20-backed actions (will be at risk after 2026-09-23) ==")
    for r in node20:
        print(f"- {r['uses']} (from={r['from']}, meta={r.get('meta_path')})")

    Path(".gha-node20-report.json").write_text(json.dumps(results, indent=2), "utf-8")

if __name__ == "__main__":
    main()
```

실행:
```bash
python3 ./scripts/gha_node_runtime_audit.py
```

예상 출력(형태):
```text
== Summary ==
total refs: 47
node20 js actions: 3

== Node20-backed actions (will be at risk after 2026-09-23) ==
- some-org/some-action@v1 (from=workflow, meta=action.yml)
- some-org/legacy-cache@a1b2c3... (from=org/reusable/.github/workflows/ci.yml@v2, meta=action.yml)
- my-org/internal-composite/scan@v3 (from=workflow, meta=scan/action.yml)
```

여기서 중요한 포인트는 두 가지입니다.

- `node20 js actions`가 0이 아니면, 2026-09-23 이후 “갑자기” 깨질 수 있습니다.
- `unresolved`가 남으면(특히 private repo/권한 문제), 그게 더 위험합니다. 이 경우는 직접 `action.yml`을 확인해 `runs.using`을 확정해야 합니다.

### D-9 ~ D-7 (2026-09-14~16): canary로 Node 24 강제 실행 + 실패 유형 분류
GitHub가 제공한 `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`는 “지금 당장” Node 24 런타임으로 액션을 실행해 보게 해 줍니다[^1].

이 단계의 목적은 단 하나입니다.

- 2026-09-23 이후 깨질 것을 **지금 깨뜨려서** 에러 로그를 분류한다.

가장 안전한 방식은 “전 워크플로 일괄 적용”이 아니라, runner(또는 workflow) 단위 canary입니다.

#### 1) workflow 단위로 강제 적용
```yaml
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: 'true'
```

#### 2) self-hosted runner 머신 단위로 강제 적용
- systemd service 환경변수로 넣고 canary runner group만 대상으로 운영합니다.

이 시점에 확인해야 할 실패 유형은 대략 아래로 갈립니다.

1) **순수 런타임 문제**
- node20을 가정하고 구현된 코드가 node24에서 터지는 케이스
- 예: deprecated API/패키지 번들링 실수

2) **네이티브 모듈/바이너리 종속**
- JavaScript action이 “순수 JS”가 아니라, 배포물에 네이티브 바이너리를 끼고 있고 node ABI에 묶여 있는 케이스
- 이런 액션은 업스트림 교체가 답이 됩니다.

3) **container job 특이점**
- container job에서 JS action은 여전히 runner 내장 node로 실행되는 구조라, 이미지/마운트/런타임 제약이 겹쳐서 터질 수 있습니다.

이 단계는 속도가 생명이라, 고쳐야 할 것과 버려야 할 것을 빨리 결정하는 게 낫습니다.

### D-7 ~ D-5 (2026-09-16~18): 업스트림 액션 교체/업그레이드/핀 고정 재정리
Node 20 제거 이슈를 해결하는 직접적인 방법은 “node20 기반 액션을 node24 기반으로 바꾸는 것”입니다. 여기서 선택지가 셋 있습니다.

1) **업스트림 액션을 최신 버전으로 올리기**
- 가장 일반적인 해법입니다.
- 단, `@v1`, `@v2` 같은 tag pin은 “자동 업데이트”라는 장점이 있지만, 반대로 공급망 관점에서는 mutable ref라는 리스크가 있습니다.

2) **핀을 SHA로 고정하고, SHA를 node24 기반 커밋으로 업데이트**
- GitHub는 보안 하드닝 관점에서 액션을 full-length commit SHA로 pinning 하는 것을 권장합니다[^7].
- GitHub Changelog에서도 SHA pinning enforcement 정책을 강조해 왔습니다[^8].

3) **액션 자체를 교체하기**
- maintainer가 node24로 올릴 의지가 없거나, repo가 사실상 방치된 경우
- 이 경우는 같은 기능을 가진 다른 액션으로 갈아타거나, composite로 흡수하거나, `run:`으로 대체합니다.

내 경우 판단 기준은 단순합니다.

- “checkout/cache/upload-artifact” 같이 CI 인프라 핵심 경로면, GitHub-owned 액션을 우선합니다.
- third-party 액션은 SHA pin + Renovate/Dependabot으로 업데이트 자동화를 걸고, 내부에서 필요한 기능은 점점 걷어냅니다.

여기서 한 가지 함정이 있습니다.

- Node 20 제거 대응을 하다가, 보안 때문에 SHA pinning을 강화하면, 오히려 “오래된 SHA”에 묶여 node20을 계속 밟는 형태가 될 수 있습니다.

그래서 이 단계는 **“node24로 올라간 커밋을 SHA로 pin”**하는 방식이 가장 일관됩니다.

### D-5 ~ D-3 (2026-09-18~20): self-hosted runner 인벤토리 + 최소 버전 강제 정책까지 같이 반영
Node 런타임만 맞춰도 runner가 낡으면 다른 이유로 멈춥니다. GitHub는 self-hosted runner에 대해 최소 버전 enforcement를 다시 시작했고, 업데이트가 30일 이상 지연되면 job이 queueing되지 않을 수 있다고 공지했습니다[^9].

이 공지는 “Node 20 제거(2026-09-23)” 직후인 “enforcement date(2026-09-25)” 같은 일정이 현실적으로 겹칠 수 있다는 점에서, 이번 마이그레이션의 범위를 넓혀야 하는 이유가 됩니다.

#### 1) GitHub API로 self-hosted runner 버전/OS/상태 수집
GitHub REST API는 self-hosted runner 조회를 제공합니다[^10].

예시(조직 runner 조회):
```bash
ORG=my-org
TOKEN="$(gh auth token)"

curl -sS -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${TOKEN}" \
  "https://api.github.com/orgs/${ORG}/actions/runners?per_page=100" \
  | jq -r '.runners[] | [.name, .os, .status, .busy, .version, (.labels|map(.name)|join(","))] | @tsv'
```

이 결과로 최소한 아래를 확정합니다.

- runner version(예: 2.32x.x, 2.33x.x)
- labels에 `ARM`, `ARM64`, `X64` 등이 들어가는지
- offline/busy 상태와 capacity

이 인벤토리는 Node 20 제거 대응의 “진짜 스코프”를 결정합니다.

- GitHub-hosted만 쓰는 repo는 액션 업데이트가 대부분이고,
- self-hosted가 섞이면 runner 업데이트/교체 계획이 포함되고,
- ARM32가 섞이면 아키텍처 전환이 포함됩니다.

### D-3 ~ D-1 (2026-09-20~22): ARM32 전환(ARM64/x64)과 `runs-on` 계약 재작성
ARM32는 “지원 종료”로 보는 편이 안전합니다. GitHub는 Node 24가 ARM32 공식 지원이 없다는 이유로 ARM32 self-hosted runner 지원이 끝난다고 적어놨습니다[^1].

반면 GitHub-hosted에는 ARM64 runner 라벨들이 이미 존재하고, 공식 문서에서도 지원 범위를 표로 제공합니다[^11]. runner-images 저장소도 ARM64 이미지 라벨/스키마를 공개합니다[^12].

여기서 내가 잡는 원칙은 “워크플로의 `runs-on`을 OS가 아니라 capability로 쓴다”입니다.

- 기존: `runs-on: self-hosted` (실제로는 ARM32든 x64든 섞여서 돌아감)
- 변경: `runs-on: [self-hosted, linux, arm64]` 같은 식으로 계약을 명확히 함

GitHub Docs에서도 self-hosted runner 타깃팅을 위해 `self-hosted`를 배열의 첫 번째로 두고, 추가 라벨을 붙이라고 설명합니다[^13].

#### ARM32→ARM64 전환에서 자주 터지는 지점
- “ARM64 머신”만 바꾸고 OS가 32-bit인 경우(예: Raspberry Pi OS 32-bit)
- Docker 기반 작업은 arm64에서 문제 없는데, 특정 액션이 바이너리 제공을 x64만 해두는 경우
- cache/artifact 같은 기본 액션은 대체로 잘 돌아가지만, third-party action이 arm64 릴리스가 없는 경우

이건 결국 “CI의 실행 환경을 몇 개의 표준 아키텍처로 수렴”시키는 작업이 됩니다.

- 비용/성능/호환성 기준으로 x64 또는 arm64로 표준화
- arm64가 필요하면 GitHub-hosted arm64(가능한 플랜/레포 조건 확인) 또는 self-hosted arm64 fleet로 정리
- ARM32는 퇴역

### D-day (2026-09-23): opt-out 제거 + 실패를 ‘예상된 실패’로 만든 상태로 들어가기
2026-09-23 이후에는 `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true`로도 Node 20을 붙잡을 수 없다고 공지돼 있습니다[^1].

D-day에 해야 할 건 기술적으로는 단순합니다.

- 임시로 켜 둔 opt-out 플래그 제거
- canary에서 이미 Node 24로 검증한 워크플로를 전체 반영
- self-hosted runner fleet에서 ARM32 제거/격리

하지만 운영적으로는 이게 “사후 대응”이 아니라 “계약 변경 반영”이어야 합니다.

- 어떤 액션이 어떤 런타임을 요구하는지(=node20/node24)
- 어떤 runner 라벨 조합에서 어떤 워크플로가 실행되는지
- 어떤 방식으로 액션 버전이 업데이트되는지(tag, SHA, lockfile)

여기까지 들어가면 CI가 갑자기 깨지는 문제가 아니라, 깨질 가능성이 있는 지점을 지속적으로 점검하는 구조로 바뀝니다.

## CI 런타임 계약을 문서화하는 방식: 워크플로를 “스펙”으로 다루기
나는 GitHub Actions를 “자동화 도구”가 아니라 “배포의 신뢰성 레이어”로 다루는 쪽이라, 워크플로도 스펙처럼 관리합니다. 기존에 쓴 글에서는 재사용/보안/속도와 OIDC, 최소 권한 같은 축을 다뤘는데, 이번 이슈는 그 연장선에서 런타임 계약까지 포함하는 게 맞습니다.

- [GitHub Actions CI/CD 파이프라인: “자동화”를 넘어 “신뢰 가능한 배포”까지](https://daewooki.github.io/posts/2025-github-actions-cicd-2/)
- [GitHub Actions로 “안전하고 빠른” CI/CD 파이프라인 구축하는 법 (캐시 v2·OIDC·권한 최소화까지)](https://daewooki.github.io/posts/2025-github-actions-cicd-v2oidc-2/)

이번 글에서 추가로 강조하는 런타임 계약의 항목은 아래입니다.

1) 액션 런타임(node20/node24)
- 워크플로에서는 보이지 않으니 별도 스캐너로 inventory

2) runner 내장 런타임의 위치/의존
- JavaScript action은 `$PATH` node가 아니라 runner 내장 node를 사용[^2]

3) self-hosted runner의 아키텍처/OS
- GitHub Docs는 ARM32를 언급하지만[^4], Node 24 전환으로 실사용이 붕괴할 수 있음

4) 업스트림 액션 버전 정책
- tag pin을 유지할지, SHA pin을 표준으로 할지
- GitHub는 SHA pin을 보안 하드닝의 핵심으로 권장[^7]

이걸 문서화할 때 중요한 건 “정책”보다 “검증 루프”입니다.

- PR마다 액션 inventory 스캔
- node20 기반 액션이 들어오면 CI에서 fail
- self-hosted runner 버전/라벨 drift 감지

## 함정과 트레이드오프: FORCE/ACTIONS_ALLOW 플래그를 어떻게 봐야 하나
GitHub가 제공한 두 환경변수는 성격이 완전히 다릅니다.

### `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`
- 목적: **미리 깨뜨려보기**
- 성격: canary/검증용
- 리스크: 액션이 node24에서 동작은 하더라도, upstream이 공식적으로 node24를 지원하는 상태가 아닐 수 있음(테스트 공백)

이 변수는 "이제부터 node24로 갈 거니까 한 번 돌려봐"라는 제공자 관점의 프리뷰 도구에 가깝습니다.

### `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true`
- 목적: **임시 유예**
- 성격: 리스크 수용(EOL 런타임 사용)
- 리스크: 보안/컴플라이언스 리스크 + 결국 2026-09-23에 종료[^1]

이 변수는 이름부터 “unsecure”입니다. 나는 이걸 “시간을 버는 용도”로만 쓰고, 계획에서 제거 날짜를 고정으로 박습니다.

- 2026-09-23 이후에는 통하지 않는다
- 그 전에도 최대한 빨리 제거한다

## 도입 판단 기준: 무엇을 이번 기회에 같이 끝내는 게 합리적인가
Node 20 제거 대응은 단기간에 끝낼 수 있지만, 보통 여기서 부채가 같이 드러납니다. 그래서 나는 아래 체크리스트로 스코프를 결정합니다.

### 1) 우리 조직이 ARM32 self-hosted runner를 실제로 쓰는가
- yes면: 이건 Node 20 제거 대응이 아니라, 하드웨어/OS 전환 프로젝트입니다.
- no면: 액션 업데이트 + runner 버전 업데이트가 주력입니다.

### 2) 액션 버전 정책이 tag pin인가, SHA pin인가
- tag pin이면: node24 대응은 쉬울 수 있지만, 공급망 리스크와 “갑작스런 변경” 리스크는 남습니다.
- SHA pin이면: 보안은 강해지지만, 이번처럼 런타임 전환 때 “내가 직접 SHA를 올려야” 합니다.

GitHub는 SHA pin을 권장하고, 정책으로 강제하는 기능도 확장해 왔습니다[^8]. 그래서 장기적으로는 SHA pin 쪽으로 조직이 이동하는 게 자연스럽습니다.

### 3) self-hosted runner 업데이트가 자동/표준화돼 있는가
GitHub는 self-hosted runner에 대해 최소 버전 enforcement를 재개했고, 업데이트 지연이 job queueing 중단으로 이어질 수 있다고 밝혔습니다[^9].

이 정책이 들어오면 self-hosted runner는 “내부 서버”가 아니라, **외부 서비스 계약을 만족시켜야 하는 에이전트**가 됩니다.

- runner 업데이트 자동화(systemd + auto-update 정책)
- ephemeral runner(1 job 1 VM/컨테이너)로 드리프트 제거
- runner group/label로 capability 기반 라우팅

여기까지 묶어서 정리하면, Node 20 제거 같은 이벤트가 와도 “깨지고 고치는” 패턴이 아니라 “변경이 들어올 때 통과시키는” 패턴으로 바뀝니다.

## 참고 자료
- [Deprecation of Node 20 on GitHub Actions runners](https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/)
- [Metadata syntax reference](https://docs.github.com/en/actions/reference/workflows-and-actions/metadata-syntax?learn=create_actions&learnProduct=actions)
- [Node.js Connection Check](https://github.com/actions/runner/blob/main/docs/checks/nodejs.md)
- [Self-hosted runners reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)
- [GitHub-hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Choosing the runner for a job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)
- [GitHub Actions: Minimum version enforcement timeline for self-hosted runners](https://github.blog/changelog/2026-06-12-github-actions-minimum-version-enforcement-timeline-for-self-hosted-runners/)
- [REST API endpoints for self-hosted runners](https://docs.github.com/en/rest/actions/self-hosted-runners)
- [actions/runner-images](https://github.com/actions/runner-images)
- [Node.js v22 to v24](https://nodejs.org/en/blog/migrations/v22-to-v24)
- [nodejs/node BUILDING.md](https://github.com/nodejs/node/blob/main/BUILDING.md?plain=1)
- [Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use?ref=devaisemanal.com)
- [GitHub Actions policy now supports blocking and SHA pinning actions](https://github.blog/changelog/2025-08-15-github-actions-policy-now-supports-blocking-and-sha-pinning-actions/)

[^1]: <https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/>
[^2]: <https://github.com/actions/runner/blob/main/docs/checks/nodejs.md>
[^3]: <https://docs.github.com/en/actions/reference/workflows-and-actions/metadata-syntax?learn=create_actions&learnProduct=actions>
[^4]: <https://docs.github.com/en/actions/reference/runners/self-hosted-runners>
[^5]: <https://nodejs.org/en/blog/migrations/v22-to-v24>
[^6]: <https://github.com/nodejs/node/blob/main/BUILDING.md?plain=1>
[^7]: <https://docs.github.com/en/actions/reference/security/secure-use?ref=devaisemanal.com>
[^8]: <https://github.blog/changelog/2025-08-15-github-actions-policy-now-supports-blocking-and-sha-pinning-actions/>
[^9]: <https://github.blog/changelog/2026-06-12-github-actions-minimum-version-enforcement-timeline-for-self-hosted-runners/>
[^10]: <https://docs.github.com/en/rest/actions/self-hosted-runners>
[^11]: <https://docs.github.com/en/actions/reference/runners/github-hosted-runners>
[^12]: <https://github.com/actions/runner-images>
[^13]: <https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
