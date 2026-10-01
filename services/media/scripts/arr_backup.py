#!/usr/bin/env python3
"""Append-only copy of Radarr/Prowlarr scheduled backups to the NAS.

Each app writes its own zip backups; this copies the newest one per app to
<dest>/<app>/, verifies it is a readable zip, and writes a .sha256 sidecar.
It never deletes or overwrites anything at the destination.

Usage: arr-backup --dest /mnt/media-backups/arr --source radarr=/srv/.../scheduled [...]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path


class BackupError(Exception):
    pass


def newest_backup(source: Path) -> Path:
    candidates = sorted(source.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise BackupError(f"no backup zip in {source}")
    return candidates[-1]


def verify_zip(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
    except zipfile.BadZipFile as exc:
        raise BackupError(f"{path} is not a valid zip") from exc
    if bad is not None:
        raise BackupError(f"{path}: corrupt member {bad}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_one(app: str, source: Path, dest_root: Path) -> str:
    latest = newest_backup(source)
    verify_zip(latest)
    target_dir = dest_root / app
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / latest.name
    if target.exists():
        return f"{app}: {latest.name} already copied"
    tmp = target.with_suffix(target.suffix + ".partial")
    shutil.copy2(latest, tmp)
    verify_zip(tmp)
    tmp.rename(target)
    (target_dir / f"{latest.name}.sha256").write_text(f"{sha256(target)}  {latest.name}\n", encoding="utf-8")
    return f"{app}: copied {latest.name}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", required=True, type=Path)
    parser.add_argument("--source", action="append", required=True, help="app=/path/to/scheduled")
    args = parser.parse_args(argv)
    status = 0
    for spec in args.source:
        app, _, path = spec.partition("=")
        try:
            print(copy_one(app, Path(path), args.dest))
        except (BackupError, OSError) as exc:
            print(f"{app}: FAILED: {exc}", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
