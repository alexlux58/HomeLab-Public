#!/usr/bin/env python3
"""Build a deterministic, secret-free Home Lab OpenBao recovery bundle."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import tempfile
from pathlib import Path

INCLUDE_DIRS = (
    "ansible",
    "docs",
    "integrations",
    "openbao",
    "scripts",
    "terraform",
    "tests",
)
INCLUDE_FILES = (
    ".ansible-lint",
    ".gitignore",
    ".yamllint",
    "AGENTS.md",
    "CLAUDE.md",
    "Makefile",
    "README.md",
    "VERSION_MATRIX.md",
    "ansible.cfg",
    "requirements.txt",
    "requirements.yml",
)
EXCLUDED_PARTS = {
    ".git",
    ".terraform",
    ".venv",
    "__pycache__",
    "artifacts",
    "secrets",
    "rendered",
    "snapshots",
}
EXCLUDED_SUFFIXES = {
    ".age",
    ".agekey",
    ".key",
    ".p12",
    ".pem",
    ".secret-id",
    ".snap",
    ".tfstate",
    ".token",
    ".unseal",
}
PRIVATE_MARKERS = (
    b"-----BEGIN " + b"PRIVATE KEY-----",
    b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----",
)


def safe_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for name in INCLUDE_FILES:
        path = root / name
        if path.is_file():
            candidates.append(path)
    for dirname in INCLUDE_DIRS:
        base = root / dirname
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            if path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            data = path.read_bytes()
            if any(marker in data for marker in PRIVATE_MARKERS):
                raise ValueError(
                    f"private key marker found in {path.relative_to(root)}"
                )
            candidates.append(path)
    return sorted(set(candidates), key=lambda path: str(path.relative_to(root)))


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def build(root: Path, output: Path) -> dict[str, object]:
    files = safe_files(root)
    manifest = {
        "format": 1,
        "files": [
            {
                "path": str(path.relative_to(root)),
                "sha256": digest(path),
                "size": path.stat().st_size,
            }
            for path in files
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with tarfile.open(temporary_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            for path in files:
                info = archive.gettarinfo(
                    str(path), arcname=str(path.relative_to(root))
                )
                info.mtime = 0
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
            rendered = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
            info = tarfile.TarInfo("MANIFEST.json")
            info.size = len(rendered)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(rendered))
        temporary_path.replace(output)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    checksum = digest(output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{checksum}  {output.name}\n", encoding="utf-8"
    )
    return {"output": str(output), "sha256": checksum, "file_count": len(files)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.root.resolve(), args.output.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
