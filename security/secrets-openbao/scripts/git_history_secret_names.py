#!/usr/bin/env python3
"""List secret-looking filenames from Git history without reading file content."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

NAME_PATTERN = re.compile(
    r"(^|/)(\.env($|\.)|.*(credential|password|secret|token).*)", re.IGNORECASE
)


def scan(repo: Path) -> dict[str, object]:
    result = subprocess.run(
        ["git", "-C", str(repo), "log", "--all", "--format=", "--name-only"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"not a readable Git repository: {repo}")
    names = sorted(
        {
            line.strip()
            for line in result.stdout.splitlines()
            if NAME_PATTERN.search(line.strip())
        }
    )
    return {"repository": str(repo.resolve()), "secret_looking_filenames": names}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = {"repositories": [scan(repo) for repo in args.repo]}
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
