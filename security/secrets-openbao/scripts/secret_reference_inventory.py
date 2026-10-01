#!/usr/bin/env python3
"""Inventory secret *names* without reading or emitting their assigned values."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

KEY_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:PASSWORD|TOKEN|SECRET|SECRET_ID|API_KEY|PRIVATE_KEY|CREDENTIAL)[A-Z0-9_]*)\b"
)
ALLOWED_SUFFIXES = {".env", ".ini", ".json", ".md", ".tf", ".tpl", ".yaml", ".yml"}
EXCLUDED_PARTS = {
    ".git",
    ".terraform",
    ".venv",
    "artifacts",
    "secrets",
    "rendered",
    "snapshots",
}


def inventory(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES and path.name != "Makefile":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        names = sorted(set(KEY_RE.findall(text)))
        if names:
            findings.append(
                {"file": str(path.relative_to(root)), "secret_names": names}
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {
        "root": str(args.root.resolve()),
        "findings": inventory(args.root.resolve()),
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
