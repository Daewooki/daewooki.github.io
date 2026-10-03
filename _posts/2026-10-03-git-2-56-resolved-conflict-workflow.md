---
title: "Git 2.56.0: 충돌 해결을 안전하게 만드는 팀 워크플로"
description: "git add --resolved를 팀 운영 계약으로 번역해 PR 규칙·훅·성능 실측까지 한 번에 정리합니다."
date: 2026-10-03 13:31:59 +0900
categories: ["Tools", "Git"]
tags: ["git", "conflict-resolution", "workflow", "hooks", "monorepo"]
render_with_liquid: false
---

## `git add --resolved`가 줄이는 실수의 형태

충돌 해결에서 사고가 나는 지점은 대개 편집이 아니라 staging입니다. 파일을 열어 `<<<<<<<`, `=======`, `>>>>>>>`를 지우는 건 누구나 합니다. 문제는 그 다음 단계에서 `git add -u`, `git add -A`, GUI의 “Stage all” 같은 동작이 **충돌 해결과 무관한 변경까지 같이 stage**한다는 점입니다. Git 2.56.0에 들어간 `git add --resolved`는 이 단계를 “충돌 해결 전용”으로 좁혀서, 팀 차원의 실수를 구조적으로 줄이려는 UX입니다. [Git v2.56 Release Notes](https://github.com/git/git/blob/master/Documentation/RelNotes/2.56.0.adoc).[^1]

이 기능을 “새 옵션 하나 추가”로 보면 별 의미가 없습니다. 팀 운영 계약으로 번역하면 달라집니다.

- PR 리뷰 규칙: “충돌 해결 커밋은 충돌 파일만 포함한다”를 사람의 주의력이 아니라 도구의 제약으로 만들 수 있습니다.
- 훅/CI: conflict marker가 stage되는 순간을 막는 방어선을 더 촘촘하게 만들 수 있습니다.
- 운영 비용: 충돌 해결 중에 섞여 들어간 변경은 리뷰 시간, revert 비용, hotfix 비용을 늘립니다. `--resolved`는 그 비용을 줄이는 쪽으로 유도합니다.

반대로, 언제 쓰면 안 되는지도 분명합니다.

- 충돌 해결이 끝났는데도 추가 수정(리팩토링/포맷팅/의존성 업데이트)을 한 번에 같이 커밋하려는 습관이 팀 문화라면 `--resolved`는 오히려 “귀찮은 제약”으로 보일 수 있습니다. 이 경우에도 사고율(불필요한 diff, 누락된 marker, 의도치 않은 파일 포함)이 충분히 높다면 습관을 바꾸는 쪽이 낫습니다.
- merge conflict가 아니라 단순히 “수정한 파일을 stage하는” 목적에는 맞지 않습니다. `--resolved`는 충돌로 인해 index가 unmerged 상태인 경로만 대상으로 삼습니다. [git-add 문서](https://git-scm.com/docs/git-add).[^2]

핵심은 기능 자체가 아니라, 팀이 staging을 어떤 의미로 쓰는지(운영 계약)입니다.

## unmerged index와 marker 스캔이 실제로 뭘 보장하는가

Git의 충돌 상태는 working tree 파일에 marker가 보이는 것만이 전부가 아닙니다. 충돌이 나면 index(= staging area)에 “unmerged entry”가 생기고, 이때 경로별로 stage 1/2/3(공통 조상/ours/theirs)의 슬롯을 동시에 가질 수 있습니다. 이 구조 때문에 충돌 해결 중에는 `git diff --ours/--theirs/--base` 같은 비교가 성립합니다. [git-diff 문서](https://git-scm.com/docs/git-diff).[^3]

전통적인 워크플로는 문서에도 그대로 적혀 있습니다.

- 충돌을 해결한 뒤 `git add <path>`로 index를 업데이트하고
- `git commit` 또는 `git merge --continue`로 마무리

이때 흔히 하는 실수가 두 가지입니다.

1) **충돌 marker가 남아 있는데도 stage**

사람이 marker를 놓치면 `git add <path>`는 그대로 받아들일 수 있습니다(파일 내용 자체가 “정상 텍스트”이기 때문). 팀에 따라서는 이게 그대로 PR로 올라와 코드 리뷰에서 잡히고, 더 운이 없으면 main에 들어갑니다.

2) **충돌과 무관한 로컬 변경이 같이 stage**

충돌을 해결하는 동안 다른 파일을 열어 로그를 찍거나, 린트가 고쳐준 파일이 생기거나, IDE가 import 정리를 하거나, 문서 오타를 고치거나. 이 자체는 나쁜 게 아닌데, 충돌 해결 커밋에 섞이면 리뷰/검증의 단위가 깨집니다.

`git add --resolved`가 보장하려는 것은 2가지입니다.

- 대상 경로를 “현재 unmerged인 경로”로 제한합니다.
- stage하기 전에 **충돌 marker가 남아 있는지 스캔**해서, 하나라도 남아 있으면 아무 것도 stage하지 않고 실패합니다.

문서에도 그대로 적혀 있습니다. “unmerged paths matching pathspec에서 working tree에 conflict marker가 남아있지 않을 때만 index를 업데이트”하며, marker가 남아 있으면 “어떤 파일도 stage하지 않고 거부”합니다. 또한 `-u`, `-A`와 같이 쓸 수 없습니다. [git-add 문서의 `--resolved`](https://git-scm.com/docs/git-add).[^2]

여기서 팀 운영 관점의 포인트는 “all-or-nothing”입니다.

- 일부 파일만 통과시키고 나머지 파일은 실패시키는 흐름이 아닙니다.
- 선택한 범위(pathspec) 안에서 marker가 하나라도 남아 있으면 전부 롤백됩니다.

이게 작은 UX 차이처럼 보이지만, 실제로는 충돌 해결을 “완료 기준이 명확한 체크리스트 작업”으로 바꿉니다.

## 충돌 해결 절차(SOP)를 `--resolved` 중심으로 다시 쓰기

팀 문서에 “충돌 나면 파일 고치고 `git add` 하세요” 정도로만 적혀 있으면, 결국 각자 습관(그리고 각자 GUI)이 표준이 됩니다. Git 2.56.0 이후로는 SOP를 더 구체적으로 쓸 수 있습니다.

아래는 내가 팀 가이드에 넣는 형태로 정리한 절차입니다. 중요한 건 명령어 자체가 아니라, staged/unstaged를 사람의 기억이 아니라 `git status --short`의 두 컬럼으로 확인하게 만드는 부분입니다.

### 1) merge/rebase 중 충돌이 났을 때, stage 기준을 먼저 고정

- “충돌 해결 커밋”은 충돌 경로만 포함합니다.
- 충돌과 무관한 변경(문서 오타, 리팩토링, 포맷팅)은 별도 커밋으로 분리합니다.

이 기준이 먼저 고정돼야 `--resolved`가 팀 계약으로 작동합니다.

### 2) 충돌 파일만 해결하고, 해결 완료 확인은 `--resolved`로 한다

- 충돌 marker 제거는 편집기에서 합니다.
- 해결 완료의 신호는 `git add --resolved`가 성공하는 것입니다.

이 단계에서 `git add -A`, `git add -u`, GUI의 stage-all은 금지합니다.

### 3) staged/unstaged 상태를 `git status --short`로 “항상” 확인

`git status --short`의 두 컬럼은 (왼쪽=staged, 오른쪽=unstaged)라는 규칙을 갖고 있고, 이게 충돌 해결에서 특히 중요합니다. GitHub의 2.56 하이라이트 글이 이 점을 예제로 직접 보여줍니다. [Highlights from Git 2.56](https://github.blog/open-source/git/highlights-from-git-2-56/).[^4]

이 UX를 SOP에 녹이면 팀의 커밋 품질이 올라갑니다.

- 충돌 파일은 `M `(staged modified) 형태가 되어야 합니다.
- 충돌과 무관한 로컬 수정은 ` M`(unstaged modified)로 남아 있어야 합니다.

### 4) merge/rebase 이어서 진행

- merge라면 `git merge --continue`
- rebase/cherry-pick라면 해당 명령의 continue

여기서 “충돌 해결 커밋에는 충돌 파일만”이라는 원칙을 지키면, 이후에 남겨둔 ` M` 변경은 별도의 커밋으로 정리하거나 버립니다.

## 재현 가능한 시나리오: `git add -u`가 왜 위험하고 `--resolved`가 뭘 막는가

아래는 실제 팀에서 일어나는 유형(충돌 해결 중 다른 파일도 같이 건드린 상태)을 의도적으로 만드는 재현 절차입니다. Git 2.56.0이 설치되어 있어야 하고, `git --version`이 `2.56.0`인지 확인합니다. (Git for Windows도 2026-09-28에 2.56.0을 배포한 것으로 표기되어 있습니다.) [Git for Windows 다운로드 페이지](https://git-scm.com/install/windows).[^5]

### 저장소 준비

```bash
mkdir git-256-resolved-demo
cd git-256-resolved-demo

git init

git config user.name "Demo"
git config user.email "demo@example.com"

cat > recipe.txt <<'EOF'
base: pancake
- flour
- egg
EOF

cat > notes.txt <<'EOF'
my notes
EOF

git add recipe.txt notes.txt
git commit -m "init"
```

### 충돌을 만드는 두 브랜치 생성

```bash
# branch A
git switch -c feature/a
perl -0777 -pe 's/- egg/- egg\n- milk/' -i recipe.txt

git add recipe.txt
git commit -m "add milk"

# back to main, branch B
git switch -c feature/b main
perl -0777 -pe 's/- egg/- egg\n- banana/' -i recipe.txt

git add recipe.txt
git commit -m "add banana"
```

### 충돌을 유발하고, 충돌과 무관한 로컬 변경도 함께 만든다

```bash
# main으로 가정하고 feature/a를 먼저 합친 뒤,
# feature/b를 합치며 충돌을 만든다.

git switch main

git merge --no-ff feature/a -m "merge feature/a"

# 충돌 발생
git merge --no-ff feature/b

# 충돌 해결 중에 흔히 같이 건드리는 "무관한" 변경을 만든다
echo "scratch during merge" >> notes.txt
```

이 상태에서 `git status`를 보면 unmerged path가 있고, working tree에 `notes.txt` 수정도 존재합니다.

### 기존 방식(위험): `git add -u`

```bash
# (하지 말아야 하는 예)
git add -u
```

`-u`는 “modified tracked path 전체를 update”하기 때문에, 충돌 해결 의도와 상관없이 `notes.txt`도 같이 stage할 수 있습니다. 또한 충돌 marker가 남아 있는 `recipe.txt`까지 실수로 stage할 여지도 생깁니다. 이 문제가 GitHub 글에서 직접 지적된 부분입니다. [Highlights from Git 2.56](https://github.blog/open-source/git/highlights-from-git-2-56/).[^4]

### Git 2.56 방식(권장): `git add --resolved`

1) 먼저 `recipe.txt`를 열어 marker를 일부러 남겨둔 채로 실행해 봅니다.

```bash
git add --resolved
```

충돌 marker가 남아 있으면 실패하면서, 어떤 파일도 stage하지 않습니다. “marker가 하나라도 남아 있으면 index는 그대로”라는 게 포인트입니다. [git-add 문서](https://git-scm.com/docs/git-add).[^2]

2) `recipe.txt`를 편집해 marker를 모두 제거한 뒤 다시 실행합니다.

```bash
# 편집 후

git add --resolved

git status --short
```

`git status --short`의 두 컬럼이 여기서 팀 교육 자료가 됩니다.

- 충돌 경로는 staged에만 반영되어 `M  recipe.txt` 형태
- 충돌과 무관한 로컬 변경은 그대로 ` M notes.txt`로 남음

이 예시는 GitHub 하이라이트 글에도 거의 같은 형태로 나옵니다. [Highlights from Git 2.56](https://github.blog/open-source/git/highlights-from-git-2-56/).[^4]

이 흐름을 팀이 표준화하면, “충돌 해결 커밋”이 내용적으로 더 깨끗해집니다.

## PR 리뷰 규칙: `--resolved`를 전제로 체크리스트를 바꾸기

`git add --resolved`는 로컬 동작입니다. 팀 운영 계약이 되려면 PR 리뷰 규칙으로 이어져야 합니다. 내가 보통 문서에 반영하는 방식은 “리뷰어가 사람 눈으로 찾는 항목”을 줄이고, “작성자가 명령으로 보장하는 항목”을 늘리는 쪽입니다.

### 1) 충돌 해결 커밋 분리 규칙

- merge/rebase 충돌을 해결했다면, 그 커밋에는 충돌 파일만 들어갑니다.
- 충돌 해결 중에 발견한 오타, 리팩토링, 포맷팅은 별도 커밋(또는 별도 PR)입니다.

이 규칙의 목표는 도덕이 아니라 비용입니다.

- 충돌 해결 커밋은 원래 diff가 복잡합니다(ours/theirs가 섞이기 때문).
- 여기에 “겸사겸사 수정”이 섞이면 리뷰의 인지 부하가 올라가고, 나중에 revert 단위가 나빠집니다.

`--resolved`는 이 규칙을 지키기 쉽게 만들어 줍니다.

### 2) staged/unstaged를 교육 내용으로 넣는다

대부분의 팀 사고는 “나는 고쳤다고 생각했는데 stage가 달랐다”에서 시작합니다. `git status --short`의 두 컬럼이 staged/unstaged를 분리한다는 사실을 팀 온보딩에 넣는 게 효과가 큽니다. 이 포맷은 공식 문서에도 정의돼 있고, `XY`가 staged/unstaged를 나타냅니다. [git-status 문서](https://git-scm.com/docs/git-status).[^6]

나는 보통 팀 교육에서 아래 3개만 강제합니다.

- 충돌 해결 중에는 `git diff`(unstaged)와 `git diff --staged`(staged)를 분리해서 본다.
- 충돌 해결 커밋 직전에는 `git status --short`를 본다.
- staging은 `git add --resolved`부터 시도한다.

### 3) 리뷰어의 역할을 바꾼다

리뷰어가 “이 파일 왜 같이 바뀌었죠?”를 묻는 팀은 충돌 비용이 큽니다. 대신 리뷰어는 다음을 확인합니다.

- 충돌 해결 커밋의 diff가 “의도된 최소 변경”인지
- 충돌과 무관한 변경은 별도 커밋인지

이때 `--resolved`를 팀 표준으로 깔아두면, 리뷰어는 “이 커밋이 충돌 해결 커밋인지”를 커밋 메시지 규칙과 함께 더 쉽게 판단할 수 있습니다.

## 훅과 CI: `--resolved`는 시작이고, 방어선은 겹쳐야 한다

현실적으로는 `--resolved`만으로 100% 막지 못합니다.

- 누군가는 여전히 `git add <path>`를 칠 수 있습니다.
- GUI가 내부적으로 어떤 `git add`를 실행하는지 사용자에게 보이지 않을 수 있습니다.
- conflict marker 문자열이 진짜 데이터로 들어갈 수도 있습니다(드물지만 0은 아닙니다).

그래서 나는 보통 “로컬 훅 + CI + 서버 정책” 3겹으로 가져갑니다.

### 1) 로컬 pre-commit 훅: stage된 콘텐츠에서 marker 탐지

`git add --resolved`가 막는 건 “충돌 중인 unmerged path를 stage할 때 marker가 남아 있는 경우”입니다. 그런데 marker가 남은 채로 stage되어 커밋되려면 결국 pre-commit에서 잡는 게 가장 싸게 막힙니다.

아래 훅은 stage된 변경에 대해 conflict marker 패턴을 탐지합니다. 완벽한 파서는 아니지만, “실수로 marker가 커밋되는” 대다수 케이스를 막습니다.

`.githooks/pre-commit`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# staged 파일만 대상으로, 흔한 conflict marker를 탐지합니다.
# -U0: 문맥 없이 변경 라인만
# 정규식은 팀 사정에 맞게 조정합니다.

diff_output=$(git diff --cached -U0 --no-color || true)

if printf "%s" "$diff_output" | grep -E '^(\+| ).*(<{7}|={7}|>{7})( |$)' >/dev/null; then
  echo "ERROR: conflict markers seem to be staged." >&2
  echo "Hint: during conflict resolution, use 'git add --resolved' (Git 2.56+) and re-check staged diff." >&2
  exit 1
fi
```

훅 공유는 `core.hooksPath`로 팀 표준화하는 편이 낫습니다. 저장소에 `.githooks/`를 넣고, 개발자 로컬에서 한 번 설정하는 방식이 운영이 쉽습니다. [git-config의 `core.hooksPath`](https://www.kernel.org/pub/software/scm/git/docs/git-config.html), [githooks 문서](https://git-scm.dev/docs/githooks).[^7]

```bash
git config --local core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

### 2) CI: PR에서 marker가 들어오면 즉시 실패

로컬 훅은 우회될 수 있습니다(또는 Windows에서 실행 권한 이슈로 무력화되기도 합니다). PR 레벨에서는 CI가 최종 방어선입니다.

내가 자주 쓰는 방식은 아래처럼 “diff 전체”를 grep하지 않고, 체크 범위를 stage가 아니라 PR의 변경 파일로 잡는 겁니다.

`scripts/check-conflict-markers.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

base_ref=${1:-origin/main}

# PR에서 변경된 파일만
files=$(git diff --name-only "$base_ref"...HEAD)

if [ -z "$files" ]; then
  exit 0
fi

# 바이너리/서브모듈 등은 필요하면 제외
# 여기서는 단순화를 위해 텍스트 파일만 대상으로 둡니다.

bad=0
while IFS= read -r f; do
  # 파일이 삭제된 경우 skip
  if [ ! -f "$f" ]; then
    continue
  fi
  if grep -nE '^(<{7}|={7}|>{7})( |$)' "$f" >/dev/null; then
    echo "conflict marker found in: $f" >&2
    bad=1
  fi
done <<< "$files"

exit $bad
```

GitHub Actions를 쓰는 팀이라면, 예전에 정리한 것처럼 workflow를 reusable로 만들어 재사용하는 편이 장기적으로 관리가 됩니다. [GitHub Actions로 CI/CD 파이프라인 구축하기](https://daewooki.github.io/posts/2025-github-actions-cicd-reusable-workfl-2/).

### 3) 운영 계약: 충돌 해결 중 커밋 금지/허용 기준을 명문화

충돌 해결 중간 커밋을 허용할지 여부는 팀마다 다릅니다. 중요한 건 “허용한다/안 한다”가 아니라, **무엇이 충돌 해결 커밋인지 정의**하는 겁니다.

`--resolved`는 이 정의를 코드로 만들기 좋습니다.

- 충돌 해결 커밋은 `git add --resolved`로 stage 가능한 변경만 포함
- 그 외의 변경은 다음 커밋으로 분리

이 규칙을 지키면, 리뷰 단계에서 충돌 해결 커밋이 “기능 변경 커밋”으로 위장하는 일이 줄어듭니다.

## 대규모 저장소 성능: Git 2.56의 개선을 팀 계약으로 번역하는 포인트

Git 2.56.0의 릴리스 하이라이트는 `--resolved`만이 아닙니다. 다만 팀 운영 계약 관점에서는 “누가 체감하는가”가 중요합니다. 내 경험상 성능 개선은 모두가 체감하지 않습니다. 하지만 특정 저장소에서는 개발 문화 자체(브랜치 전략, 리베이스 주기, CI 전략)에 영향을 줍니다.

### 1) `git merge-base --all` 급가속: rebase/merge의 숨은 비용이 줄어든다

GitHub 하이라이트 글에서 가장 인상적인 수치가 merge-base 쪽입니다.

- 어떤 실제 monorepo 케이스에서 traversal이 0.68s → 0.01s로 줄었다고 소개합니다.
- 또 다른 대형 monorepo들에서 70배, 평균 20배 수준의 개선 사례를 언급합니다.
- Linux kernel 케이스로 `git merge-base --all v4.8 v4.9`가 0.29s → 0.01s로 줄었다는 예시도 있습니다.

이건 “명령 하나 빨라졌다”가 아니라, 아래 같은 팀 계약에 영향을 줍니다.

- CI에서 ancestry/merge-base 기반 최적화를 더 공격적으로 해도 부담이 줄어듭니다.
- 대형 히스토리를 가진 monorepo에서 “rebase를 자주 하자” 같은 규칙이 덜 고통스러워집니다.

근거로는 GitHub의 성능 수치 공개가 가장 직접적입니다. [Highlights from Git 2.56](https://github.blog/open-source/git/highlights-from-git-2-56/).[^4]

다만, 릴리스 노트에는 early-exit 최적화 관련해서 “v1 commit-graph와 clock skew가 있는 경우 잘못된 결과를 낼 수 있어 조건을 gate했다”는 버그 수정도 들어가 있습니다. 즉, 성능 개선이 곧장 항상 적용되는 건 아니고 correctness 가드가 있습니다. [Git v2.56 Release Notes](https://github.com/git/git/blob/master/Documentation/RelNotes/2.56.0.adoc).[^1]

팀 운영 관점의 결론은 단순합니다.

- “우리 repo에서 merge-base가 병목인가?”를 먼저 재야 합니다.
- 병목이면, Git 버전 업그레이드를 정책 이슈로 올릴 가치가 있습니다.

### 2) 서버 운영: `--path-walk` repack의 채택 가능성이 커졌다

GitHub 글은 `--path-walk` repack이 pack 크기를 크게 줄일 수 있다는 벤치마크를 보여주고(Fluent UI 기준 71% 감소), 기존에는 reachability bitmap과 delta islands와 함께 쓰기 어려웠는데 Git 2.56에서 이 제한이 풀렸다고 설명합니다. [Highlights from Git 2.56](https://github.blog/open-source/git/highlights-from-git-2-56/).[^4]

이건 대형 저장소(특히 호스팅 서버/monorepo)에서 운영 계약으로 번역하면 다음이 됩니다.

- “저장소 용량(스토리지) vs fetch 성능 vs repack CPU”의 트레이드오프를 다시 평가할 수 있습니다.
- delta islands를 쓰는 조직(예: refs/pull, refs/changes가 많은 호스팅 구조)은 특히 의미가 있습니다. delta islands 자체는 문서에 운영상의 이유까지 꽤 자세히 설명돼 있습니다. [git-pack-objects의 DELTA ISLANDS](https://git-scm.com/docs/git-pack-objects/2.56.0.html).[^8]

여기서 “팀 규칙”이 되는 지점은 개발자 로컬이 아니라 플랫폼 팀(DevOps/Infra)입니다.

- gc 정책(언제 repack할지)
- bitmap 활성화 여부
- `pack.usePathWalk` 같은 기본 설정 적용 여부(테스트 환경에서만 먼저 적용)

`pack.usePathWalk`는 Git 문서의 config에서도 언급됩니다. [pack.* 설정 문서 일부](https://fossies.org/linux/misc/git-2.56.0.rc0.tar.xz/git-2.56.0.rc0/Documentation/config/pack.adoc).[^9]

### 3) 개발자 체감: untracked 파일 열거가 느린 repo에서 `git status`가 달라진다

릴리스 노트에 “git status에서 untracked/ignored 파일 열거가 string list 삽입의 quadratic을 피해서 O(n^2) → O(n log n)로 줄였다”는 항목이 들어가 있습니다. [Git v2.56 Release Notes](https://github.com/git/git/blob/master/Documentation/RelNotes/2.56.0.adoc).[^1]

이건 모든 repo에서 체감되지 않습니다. 체감이 큰 repo는 대체로 이런 특징이 있습니다.

- working tree에 파일이 많고(특히 생성물이 쌓이는 구조)
- ignore 규칙이 복잡하거나
- 개발자들이 `git status`를 자주 치는 흐름(그리고 IDE가 내부적으로 더 자주 실행)

팀 운영 계약으로 바꾸면:

- ignore 관리가 허술해서 “untracked 지옥”인 저장소는, Git 업그레이드와 별개로 working tree 청결 규칙을 세워야 합니다.
- 반대로 이미 청결한 저장소는 이 개선을 거의 못 느낄 수 있습니다.

## 실측 관점 제안: 우리 저장소에서 체감이 큰지 재는 방법

릴리스 노트/하이라이트 수치를 그대로 팀에 복사하면 설득이 약합니다. 특히 성능은 repo 형태에 따라 편차가 큽니다. 대신 “우리 저장소에서 반복 측정 가능한 벤치”를 만들면, 버전 업그레이드가 감정이 아니라 데이터가 됩니다.

### 1) merge-base 벤치(대형 히스토리일수록 유효)

```bash
# hyperfine이 없다면 설치 후
# macOS: brew install hyperfine
# Ubuntu: apt install hyperfine

# 예: 우리 조직의 통합 브랜치/릴리스 태그/장기 유지 브랜치 같은 두 지점을 잡는다.
hyperfine --warmup 3 \
  'git merge-base --all origin/main origin/release'
```

포인트:

- 같은 체크아웃 상태에서 반복 실행합니다.
- commit-graph 설정(v1/v2), fsmonitor 등 환경 요인이 크니, 결과를 공유할 때는 `.git/config`의 관련 설정을 같이 기록하는 편이 좋습니다.

### 2) status 벤치(파일이 많은 워킹 트리일수록 유효)

```bash
hyperfine --warmup 3 \
  'git status --porcelain=v1 >/dev/null'
```

`--porcelain`을 쓰는 이유는 사람이 읽는 출력 포맷의 비용을 줄여, “상태 계산” 자체를 더 잘 보기 위해서입니다.

### 3) 충돌 해결 안전 벤치(정량화는 사고율/리뷰 시간으로 잡는다)

`--resolved`의 가치는 속도가 아니라 사고율입니다. 이건 마이크로벤치로는 잘 안 잡힙니다. 대신 운영 지표로 잡는 게 맞습니다.

- PR에서 “불필요 파일 변경”으로 코멘트가 달린 횟수
- 충돌 해결 커밋에서 “리뷰어가 revert 또는 분리 커밋을 요구한” 횟수
- main에 conflict marker가 들어가 CI가 깨진 incident 수

Git 2.56 도입 전후로 1~2달만 비교해도 추세가 보입니다. 팀의 규모가 클수록 통계가 빨리 모입니다.

## 도입 판단: Git 버전 분포, 도구 호환성, 그리고 교육 비용

Git 자체는 CLI 도구지만, 팀의 실제 사용자 경험은 IDE/GUI/자동화가 결정합니다.

### 1) “충돌 해결 단계만 CLI로 고정”이 현실적으로 가장 잘 먹힌다

전원이 같은 GUI를 쓰게 만드는 건 거의 불가능합니다. 대신 충돌 해결 단계만큼은 팀 공통 절차를 강제하는 게 효과가 좋습니다.

- 충돌 해결은 어떤 도구로 편집해도 되지만
- staging은 `git add --resolved`로 한다

이 규칙은 도구 혼종 팀에서도 적용이 쉽습니다. 또, 에디터 플러그인들도 빠르게 따라 붙을 가능성이 큽니다. 예를 들어 vim-fugitive 쪽에서도 “충돌 해결 단계에서 `git add --resolved`를 쓰자”는 요청 이슈가 이미 올라와 있습니다. [vim-fugitive 이슈 #2492](https://github.com/tpope/vim-fugitive/issues/2492).[^10]

### 2) `git status` 안내 문구 변경도 교육 자료를 바꾼다

Git 2.56 릴리스 노트에는 `git status`가 behind/diverged일 때 보여주는 advice가 `git pull <remote> <branch>`를 제안하도록 바뀌었다는 항목이 있습니다. [Git v2.56 Release Notes](https://github.com/git/git/blob/master/Documentation/RelNotes/2.56.0.adoc).[^1]

이런 자잘한 문구는 팀 교육 자료/스크린샷과 금방 어긋납니다. 릴리스 직후(2026-09-28 공개 직후)에 팀 표준 문서를 업데이트하기 좋다는 판단은 여기서도 맞습니다.

### 3) 브랜치 정리까지 운영 계약에 포함시키면 효과가 커진다

Git 2.56의 다른 변화 중 팀 운영에 바로 얹기 좋은 건 `git branch --delete-merged` 계열입니다. GitLab 글은 이 기능을 꽤 “운영 관점”으로 풀어줍니다. 추적(upstream) 설정이 되어 있어야 하고, 통합 브랜치를 기준으로 fork/merge된 브랜치를 정리하는 흐름을 제시합니다. [What’s new in Git 2.56.0?](https://about.gitlab.com/blog/whats-new-in-git-2-56-0/).[^11]

공식 문서에도 `--delete-merged`의 동작과 안전장치(업스트림이 없거나 worktree에서 체크아웃된 경우 제외 등)가 나옵니다. [git-branch 문서](https://git-scm.com/docs/git-branch).[^12]

충돌 해결 안전(`--resolved`)과 브랜치 정리는 같이 묶을수록 팀 운영이 깔끔해집니다.

- 브랜치가 오래 살아 있으면 충돌 빈도와 난이도가 올라가고
- 충돌이 많아질수록 staging 실수의 표면적이 커집니다.

## 팀 규칙 템플릿: 가이드/템플릿/교육 자료에 바로 넣는 문구

아래는 내가 실제로 팀 위키나 `CONTRIBUTING.md`에 넣는 형태로 정리한 계약 문구입니다.

### 충돌 해결

- merge/rebase/cherry-pick 중 충돌이 발생하면, 충돌 해결이 끝난 파일은 `git add --resolved`로 stage합니다(Git 2.56+).
- `git add -A`, `git add -u`, GUI의 stage-all은 충돌 해결 단계에서 사용하지 않습니다.
- `git add --resolved`가 conflict marker를 보고 실패하면, 실패한 상태에서 index는 변경되지 않습니다. marker 제거 후 다시 시도합니다. [git-add 문서](https://git-scm.com/docs/git-add).[^2]

### 커밋 단위

- “충돌 해결 커밋”은 충돌 파일만 포함합니다.
- 충돌 해결 과정에서 생긴 기타 수정은 별도 커밋으로 분리합니다.

### 로컬 훅

- 저장소는 `.githooks/` 디렉터리를 통해 pre-commit 훅을 제공합니다.
- 모든 개발자는 `git config --local core.hooksPath .githooks`로 활성화합니다. [git-config의 `core.hooksPath`](https://www.kernel.org/pub/software/scm/git/docs/git-config.html).[^7]

### CI

- PR CI에서 conflict marker 패턴(`<<<<<<<`, `=======`, `>>>>>>>`)이 발견되면 실패합니다.

### 브랜치 운영(선택)

- feature 브랜치는 반드시 통합 브랜치(upstream)를 추적하도록 생성합니다.
- 통합 브랜치에 merge된 feature 브랜치는 정기적으로 정리합니다(`git branch --delete-merged`). [What’s new in Git 2.56.0?](https://about.gitlab.com/blog/whats-new-in-git-2-56-0/).[^11]

이 정도로 규칙을 문장화하면, `--resolved`는 개인 팁이 아니라 팀의 일관된 절차가 됩니다.

## 참고 자료

- [Highlights from Git 2.56](https://github.blog/open-source/git/highlights-from-git-2-56/)
- [What’s new in Git 2.56.0?](https://about.gitlab.com/blog/whats-new-in-git-2-56-0/)
- [Git v2.56 Release Notes](https://github.com/git/git/blob/master/Documentation/RelNotes/2.56.0.adoc)
- [git-add 문서](https://git-scm.com/docs/git-add)
- [git-status 문서](https://git-scm.com/docs/git-status)
- [git-branch 문서](https://git-scm.com/docs/git-branch)
- [git-pack-objects 문서](https://git-scm.com/docs/git-pack-objects/2.56.0.html)
- [Git for Windows 다운로드 페이지](https://git-scm.com/install/windows)
- [vim-fugitive 이슈 #2492](https://github.com/tpope/vim-fugitive/issues/2492)
- [GitHub Actions로 CI/CD 파이프라인 구축하기: Reusable Workflow·OIDC·Concurrency·Artifacts까지](https://daewooki.github.io/posts/2025-github-actions-cicd-reusable-workfl-2/)

[^1]: <https://github.com/git/git/blob/master/Documentation/RelNotes/2.56.0.adoc>
[^2]: <https://git-scm.com/docs/git-add>
[^3]: <https://git-scm.com/docs/git-diff>
[^4]: <https://github.blog/open-source/git/highlights-from-git-2-56/>
[^5]: <https://git-scm.com/install/windows>
[^6]: <https://git-scm.com/docs/git-status>
[^7]: <https://www.kernel.org/pub/software/scm/git/docs/git-config.html>
[^8]: <https://git-scm.com/docs/git-pack-objects/2.56.0.html>
[^9]: <https://fossies.org/linux/misc/git-2.56.0.rc0.tar.xz/git-2.56.0.rc0/Documentation/config/pack.adoc>
[^10]: <https://github.com/tpope/vim-fugitive/issues/2492>
[^11]: <https://about.gitlab.com/blog/whats-new-in-git-2-56-0/>
[^12]: <https://git-scm.com/docs/git-branch>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
