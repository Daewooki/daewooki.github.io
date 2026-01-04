#!/usr/bin/env python3
"""
기존 _posts/*.md에 조회수 위젯을 일괄 삽입합니다.

- front matter(--- ... ---) 바로 뒤에 삽입
- 이미 삽입된 파일(id="pv-post")은 건너뜀
"""

from __future__ import annotations

from pathlib import Path


WIDGET = """<div class="pageviews" style="margin: 0.25rem 0 1rem; opacity: 0.8;">
  <span style="font-weight: 600;">조회수</span>: <span id="pv-post">-</span>
</div>
<script defer src="/assets/js/pageviews.js"></script>

"""


def insert_widget(md: str) -> str:
    if 'id="pv-post"' in md:
        return md

    # Find front matter end: first two occurrences of "---" at line start
    lines = md.splitlines(keepends=True)
    if not lines:
        return md

    if not lines[0].lstrip().startswith("---"):
        # Not a standard Jekyll post; skip.
        return md

    dash_count = 0
    end_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            dash_count += 1
            if dash_count == 2:
                end_idx = i
                break

    if end_idx is None:
        return md

    # Insert after front matter block (end_idx line) and a newline if needed.
    out = "".join(lines[: end_idx + 1])
    if not out.endswith("\n"):
        out += "\n"
    out += "\n" + WIDGET
    out += "".join(lines[end_idx + 1 :])
    return out


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    posts_dir = repo_root / "_posts"
    if not posts_dir.exists():
        raise SystemExit(f"Not found: {posts_dir}")

    changed = 0
    for path in sorted(posts_dir.glob("*.md")):
        original = path.read_text(encoding="utf-8")
        updated = insert_widget(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1

    print(f"Done. Updated {changed} file(s).")


if __name__ == "__main__":
    main()


