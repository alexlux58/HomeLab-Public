#!/usr/bin/env python3
"""Run yamllint on the given files, each with its component's own .yamllint.

yamllint reads one config per invocation, but components keep different rules,
so files are grouped by the nearest ancestor directory holding a .yamllint.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def nearest_config(path: Path) -> Path | None:
    for parent in [path.parent, *path.parent.parents]:
        candidate = parent / ".yamllint"
        if candidate.is_file():
            return candidate
        if parent == ROOT:
            break
    return None


def main(argv: list[str]) -> int:
    if not argv:
        return 0
    if shutil.which("yamllint") is None:
        print("yamllint is not installed; use the devcontainer or `make setup`.", file=sys.stderr)
        return 1
    groups: dict[Path | None, list[str]] = defaultdict(list)
    for name in argv:
        groups[nearest_config((ROOT / name).resolve())].append(name)
    status = 0
    for config, files in groups.items():
        cmd = ["yamllint", "-s"] + (["-c", str(config)] if config else []) + files
        status |= subprocess.run(cmd, check=False).returncode
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
