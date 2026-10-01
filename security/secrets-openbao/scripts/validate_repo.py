#!/usr/bin/env python3
"""Offline safety validation for the Home Lab OpenBao repository."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED = (
    "README.md",
    "CLAUDE.md",
    "docs/architecture.md",
    "docs/restore-runbook.md",
    "terraform/main.tf",
    # Phase 1 moved inventories to one root boundary outside this component.
    "../../inventory/secrets-openbao/hosts.yml",
    "openbao/secrets-engines/engines.json",
    "scripts/raft_snapshot.py",
)
BANNED_EXECUTABLE_TEXT = (
    "StrictHostKeyChecking" + "=no",
    "ignore_errors" + ": true",
    "pvecm" + " expected",
    "rm" + " -rf",
    "bao operator" + " init",
    "bao operator raft snapshot" + " restore",
    "bao operator raft" + " remove-peer",
)
PRIVATE_MARKERS = (
    "-----BEGIN " + "PRIVATE KEY-----",
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
    "-----BEGIN AGE " + "ENCRYPTED FILE-----",
)
TOKEN_PATTERNS = (
    re.compile(r"\bhvs\.[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bs\.[A-Za-z0-9_-]{20,}"),
)
EXECUTABLE_DIRS = ("ansible", "scripts", "terraform")


def validate(root: Path) -> list[str]:
    issues: list[str] = []
    for relative in REQUIRED:
        if not (root / relative).is_file():
            issues.append(f"missing required file: {relative}")

    for playbook in sorted((root / "ansible/playbooks").glob("*.yml")):
        text = playbook.read_text(encoding="utf-8")
        if "serial: 1" not in text:
            issues.append(f"playbook lacks serial: 1: {playbook.name}")
        if "any_errors_fatal: true" not in text:
            issues.append(f"playbook lacks any_errors_fatal: true: {playbook.name}")

    for dirname in EXECUTABLE_DIRS:
        for path in (root / dirname).rglob("*"):
            if not path.is_file() or ".terraform" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for banned in BANNED_EXECUTABLE_TEXT:
                if banned in text:
                    issues.append(
                        f"banned executable text {banned!r}: {path.relative_to(root)}"
                    )

    for path in root.rglob("*"):
        if not path.is_file() or any(
            part in {".git", ".terraform", ".venv"} for part in path.parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in PRIVATE_MARKERS:
            if marker in text:
                issues.append(f"private material marker in {path.relative_to(root)}")
        for pattern in TOKEN_PATTERNS:
            if pattern.search(text):
                issues.append(f"possible OpenBao token in {path.relative_to(root)}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    issues = validate(args.root.resolve())
    print(
        json.dumps(
            {"status": "pass" if not issues else "fail", "issues": issues}, indent=2
        )
    )
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
