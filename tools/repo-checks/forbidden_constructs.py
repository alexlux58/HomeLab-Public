#!/usr/bin/env python3
"""Scan executable and configuration files for constructs the safety contract
forbids. Used by pre-commit (on staged files) and by tests/ (on every tracked
file), so an agent of any kind hits the same wall.

Usage: forbidden_constructs.py [FILE ...]   (no files: every tracked file)
Exit 1 and one line per finding when anything is found.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Only the surface that executes or configures something. Prose (Markdown) may
# name a forbidden construct in order to forbid it.
SCANNED_SUFFIXES = {".yml", ".yaml", ".sh", ".py", ".tf", ".j2", ".cfg", ".ps1", ".toml", ".json"}
SCANNED_NAMES = {"Makefile", "Dockerfile"}

# Files whose job is to name the constructs they forbid.
EXEMPT = {
    "tools/repo-checks/forbidden_constructs.py",
    ".claude/hooks/guard.py",
    ".claude/settings.json",
    "platform/proxmox/tests/test_repo_safety.py",
    "security/secrets-openbao/scripts/validate_repo.py",
}
EXEMPT_PREFIXES = ("tests/", "public/")

PATTERNS = {
    "ignore_errors on a task": re.compile(r"^\s*ignore_errors:\s*(true|yes)\b", re.MULTILINE | re.I),
    "rm -rf": re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\b|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r\b"),
    "StrictHostKeyChecking disabled": re.compile(r"StrictHostKeyChecking\s*[= ]\s*no\b", re.I),
    "host_key_checking disabled": re.compile(r"host_key_checking\s*=\s*(false|no)\b", re.I),
    "pvecm expected": re.compile(r"\bpvecm\s+expected\b"),
    "backup pruning": re.compile(r"--prune-backups[ \t]+(?!keep-all=1|\"?\{\{)"),
    "vzdump --remove": re.compile(r"vzdump[^\n]*--remove\s+1"),
    "private key material": re.compile(
        r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |PGP |AGE ENCRYPTED )?PRIVATE KEY"
    ),
    "automated OpenBao ceremony": re.compile(r"\bbao\s+operator\s+(init|unseal|rekey|generate-root)\b"),
    "aggregate target": re.compile(
        r"^[ \t]*[\w.-]*(deploy-all|rebuild-all|migrate-all|media-all|run-all|apply-all|everything)[\w.-]*\s*:(?!=)",
        re.MULTILINE,
    ),
    "unsafe auto-approve": re.compile(r"\b(terraform|tofu)\b[^\n]*\b(apply|destroy)\b[^\n]*-auto-approve"),
}


# Pre-existing findings, recorded in MEMORY.md "Known gaps" and scheduled for
# removal. This is a ratchet: tests fail on any finding not listed here AND on
# any listed entry that no longer occurs, so the list can only shrink.
BASELINE: dict[tuple[str, str], int] = {
    # Empty since the Phase 6 publisher rewrite (2026-09-30) removed the last
    # two `rm -rf` lines in tools/publish/publish-snapshot.sh.
}


def is_prose(rel: str, line: str) -> bool:
    """A comment, or guidance telling the operator NOT to do something, names
    the construct in order to forbid it (same rule as test_repo_safety.py)."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    return bool(re.search(r"\b(do not|never|must not)\b", line, re.IGNORECASE))


UNTRACKED_DIRS = {
    ".git",
    ".venv",
    ".ansible",
    "collections",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "public",
}


def tracked_files() -> list[str]:
    """Tracked files; a `git archive` export (no .git) is tracked by definition."""
    if (ROOT / ".git").exists():
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True
        ).stdout.decode("utf-8")
        return [p for p in out.split("\0") if p]
    return sorted(
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob("*")
        if p.is_file() and not UNTRACKED_DIRS & set(p.relative_to(ROOT).parts)
    )


def in_scope(rel: str) -> bool:
    if rel in EXEMPT or rel.startswith(EXEMPT_PREFIXES):
        return False
    path = Path(rel)
    return path.suffix in SCANNED_SUFFIXES or path.name in SCANNED_NAMES


def scan(rel: str) -> list[str]:
    try:
        text = (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_text(rel, text)


def scan_text(rel: str, text: str) -> list[tuple[str, str, int]]:
    lines = text.splitlines()
    findings = []
    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            index = text.count("\n", 0, match.start())
            if is_prose(rel, lines[index] if index < len(lines) else ""):
                continue
            findings.append((rel, name, index + 1))
    return findings


def evaluate(files: list[str]) -> list[str]:
    """Return problems: findings beyond the baseline, and stale baseline entries
    (only when scanning every tracked file)."""
    found: dict[tuple[str, str], list[int]] = {}
    for name in files:
        path = Path(name)
        rel = path.resolve().relative_to(ROOT).as_posix() if path.is_absolute() else path.as_posix()
        if in_scope(rel):
            for rel_path, construct, line in scan(rel):
                found.setdefault((rel_path, construct), []).append(line)
    problems = []
    for key, lines in sorted(found.items()):
        allowed = BASELINE.get(key, 0)
        if len(lines) > allowed:
            problems.append(f"{key[0]}:{lines[0]}: {key[1]} ({len(lines)} found, baseline {allowed})")
    return problems


def stale_baseline(files: list[str]) -> list[str]:
    counts: dict[tuple[str, str], int] = {}
    for rel in files:
        if in_scope(rel):
            for rel_path, construct, _ in scan(rel):
                counts[(rel_path, construct)] = counts.get((rel_path, construct), 0) + 1
    return [
        f"{rel}: baseline for {construct} is {n} but {counts.get((rel, construct), 0)} remain; shrink it"
        for (rel, construct), n in BASELINE.items()
        if counts.get((rel, construct), 0) < n
    ]


def main(argv: list[str]) -> int:
    files = argv or tracked_files()
    problems = evaluate(files)
    if not argv:
        problems += stale_baseline(files)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
