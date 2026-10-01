#!/usr/bin/env python3
"""Create a consistent, append-only application backup set for VM 300."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

SQLITE_DATABASES = {
    "npm.sqlite": Path("/srv/homelab/npm/data/database.sqlite"),
    "linkding.sqlite3": Path("/srv/homelab/linkding/data/db.sqlite3"),
    "speedtest-tracker.sqlite": Path("/srv/homelab/speedtest-tracker/config/database.sqlite"),
}

DOCKER = "/usr/bin/docker"

CONFIG_PATHS = (
    Path("/opt/homelab/compose"),
    Path("/srv/homelab/homepage/config"),
    Path("/srv/homelab/npm/data/nginx"),
    Path("/srv/homelab/npm/letsencrypt"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/srv/homelab-backups/staging"),
        help="Append-only parent directory for timestamped backup sets",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path, kind: str, root: Path) -> dict[str, object]:
    return {
        "kind": kind,
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def backup_sqlite(source: Path, destination: Path) -> str:
    if not source.is_file():
        raise RuntimeError(f"required SQLite database is missing: {source}")

    source_uri = f"file:{source}?mode=ro"
    with (
        sqlite3.connect(source_uri, uri=True) as source_db,
        sqlite3.connect(destination) as destination_db,
    ):
        source_db.backup(destination_db)
        result = destination_db.execute("PRAGMA integrity_check").fetchone()

    if result != ("ok",):
        raise RuntimeError(f"SQLite integrity check failed for {source}")
    destination.chmod(0o600)
    return "ok"


def backup_uptime_kuma(destination: Path) -> None:
    command = [
        DOCKER,
        "exec",
        "uptime-kuma",
        "mariadb-dump",
        "--socket=/app/data/run/mariadb.sock",
        "--all-databases",
        "--single-transaction",
        "--quick",
        "--skip-lock-tables",
        "--routines",
        "--events",
        "--triggers",
    ]
    with (
        subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as process,
        gzip.open(destination, "wb", compresslevel=6) as output,
    ):
        if process.stdout is None:
            raise RuntimeError("Uptime Kuma MariaDB dump did not open stdout")
        shutil.copyfileobj(process.stdout, output, length=1024 * 1024)
        process.stdout.close()
        returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(f"Uptime Kuma MariaDB dump failed with exit code {returncode}")
    destination.chmod(0o600)


def archive_configuration(destination: Path) -> None:
    with tarfile.open(destination, "w:gz", compresslevel=6) as archive:
        for source in CONFIG_PATHS:
            if not source.exists():
                raise RuntimeError(f"required configuration path is missing: {source}")
            archive.add(source, arcname=str(source.relative_to("/")), recursive=True)
    destination.chmod(0o600)


def write_netknife_metadata(destination: Path) -> None:
    result = subprocess.run(
        [DOCKER, "inspect", "netknife-api", "netknife-web"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"NetKnife metadata inspection failed with exit code {result.returncode}"
        )

    inspected = json.loads(result.stdout)
    sanitized = []
    for container in inspected:
        labels = container.get("Config", {}).get("Labels", {}) or {}
        sanitized.append(
            {
                "name": container.get("Name", "").lstrip("/"),
                "image_reference": container.get("Config", {}).get("Image"),
                "image_id": container.get("Image"),
                "labels": {
                    key: value
                    for key, value in labels.items()
                    if key.startswith("com.examplelab.homelab.")
                },
                "status": container.get("State", {}).get("Status"),
            }
        )
    destination.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n")
    destination.chmod(0o600)


def main() -> int:
    args = parse_args()
    os.umask(0o077)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_root = args.output / timestamp
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    database_root = backup_root / "databases"
    database_root.mkdir(mode=0o700)

    artifacts: list[dict[str, object]] = []
    sqlite_checks: dict[str, str] = {}

    for filename, source in SQLITE_DATABASES.items():
        destination = database_root / filename
        sqlite_checks[filename] = backup_sqlite(source, destination)
        artifacts.append(artifact(destination, "sqlite-online-backup", backup_root))

    uptime_dump = database_root / "uptime-kuma-all-databases.sql.gz"
    backup_uptime_kuma(uptime_dump)
    artifacts.append(artifact(uptime_dump, "mariadb-transactional-dump", backup_root))

    config_archive = backup_root / "configuration-and-certificates.tar.gz"
    archive_configuration(config_archive)
    artifacts.append(artifact(config_archive, "configuration-archive", backup_root))

    netknife_metadata = backup_root / "netknife-metadata.json"
    write_netknife_metadata(netknife_metadata)
    artifacts.append(artifact(netknife_metadata, "sanitized-metadata", backup_root))

    manifest = {
        "schema": 1,
        "created_utc": datetime.now(UTC).isoformat(),
        "hostname": socket.gethostname(),
        "retention": "append-only; no automatic pruning",
        "excluded_ephemeral": [
            {
                "path": "/srv/homelab/linkding/data/tasks.sqlite3",
                "reason": "disposable background-task queue; recreated by Linkding",
            }
        ],
        "sqlite_integrity_checks": sqlite_checks,
        "artifacts": artifacts,
    }
    manifest_path = backup_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest_path.chmod(0o600)
    print(backup_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
