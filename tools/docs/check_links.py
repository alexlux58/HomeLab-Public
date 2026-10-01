#!/usr/bin/env python3
"""Offline link check for the monorepo's Markdown (make docs-check).

For every Markdown file in scope, each relative link must point at an existing
file or directory, and a `#fragment` into a Markdown file must match one of its
headings (GitHub slug rules, or Pandoc's for the walkthrough). A `repo:PATH`
link (the walkthrough's scheme, see tools/docs-build/build.py) must name a
tracked path from the repository root, and `#LA-LB` must be lines that exist.
External URLs are not fetched: CI is offline. Exit 1 and one line per broken
link.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_PREFIXES = (
    "public/",
    "docs/reference/legacy/",
    "docs/walkthrough/legacy/",
    "services/media/docs/legacy/",
    "services/music-library/",
    # Public-tree files: their links resolve in public/, and publish_snapshot.py
    # checks them against the staged public tree instead.
    "tools/publish/overlay/",
)
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.M)
FENCE = re.compile(r"^```.*?^```", re.M | re.S)


def markdown_files() -> list[str]:
    if (ROOT / ".git").exists():
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "*.md"], check=True, capture_output=True, text=True
        )
        files = out.stdout.splitlines()
    else:
        files = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.md") if ".venv" not in p.parts]
    return sorted(f for f in files if not f.startswith(SKIP_PREFIXES) and "/collections/" not in f)


def slug(heading: str) -> str:
    text = re.sub(r"[`*_]|<[^>]+>", "", heading).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    seen: dict[str, int] = {}
    result = set()
    for heading in HEADING.findall(text):
        base = slug(heading)
        count = seen.get(base, 0)
        result.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
        result.add(re.sub(r"-+", "-", base))  # Pandoc collapses the hyphens
    return result


REPO_LINK = re.compile(r"^repo:([^#]+)(?:#L(\d+)(?:-L(\d+))?)?$")


def check_repo_link(rel: str, target: str) -> list[str]:
    match = REPO_LINK.match(target)
    if not match:
        return [f"{rel}: malformed repo: link {target}"]
    destination = ROOT / match.group(1)
    if not is_published(destination):
        return [f"{rel}: missing or untracked target {target}"]
    if match.group(2):
        start, end = int(match.group(2)), int(match.group(3) or match.group(2))
        count = len(destination.read_text(encoding="utf-8").splitlines())
        if not 1 <= start <= end <= count:
            return [f"{rel}: {target} is outside 1-{count}"]
    return []


def tracked_paths() -> set[str] | None:
    """Tracked files, or None outside a git checkout (then every file counts)."""
    if not (ROOT / ".git").exists():
        return None
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], check=True, capture_output=True, text=True)
    return set(out.stdout.splitlines())


TRACKED = tracked_paths()


def is_published(destination: Path) -> bool:
    """A link must resolve in a fresh clone: git-ignored local files do not count."""
    if not destination.exists():
        return False
    if TRACKED is None:
        return True
    rel = destination.resolve().relative_to(ROOT.resolve()).as_posix()
    return rel in TRACKED or any(path.startswith(rel + "/") for path in TRACKED)


def check(rel: str) -> list[str]:
    source = ROOT / rel
    text = FENCE.sub("", source.read_text(encoding="utf-8"))
    problems = []
    for target in LINK.findall(text):
        if target.startswith("repo:"):
            problems += check_repo_link(rel, target)
            continue
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("//"):
            continue  # external or mailto: not checked offline
        path_part, _, fragment = target.partition("#")
        destination = source if not path_part else (source.parent / path_part.split("?")[0])
        if path_part and not is_published(destination):
            problems.append(f"{rel}: missing or untracked target {target}")
            continue
        if fragment and destination.suffix == ".md" and fragment.lower() not in anchors(destination):
            problems.append(f"{rel}: no heading for #{fragment} in {path_part or rel}")
    return problems


def main() -> int:
    problems = [p for rel in markdown_files() for p in check(rel)]
    for problem in problems:
        print(problem)
    print(f"checked {len(markdown_files())} Markdown files: {len(problems)} broken link(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
