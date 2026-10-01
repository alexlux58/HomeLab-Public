#!/usr/bin/env python3
"""Create a consistent, append-only application backup set for the NetBox guest.

A file-level copy of a running PostgreSQL data directory is not a backup. This
program takes a transactional `pg_dump` through the container, hashes every
artifact, and writes a detached manifest. It never deletes or prunes anything.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

DOCKER = "/usr/bin/docker"
POSTGRES_CONTAINER = "netbox-postgres"
NETBOX_CONTAINER = "netbox"

# Media, reports, and scripts are user-supplied and are not reproducible from
# Git. The Compose definition is included so a restore does not depend on the
# controller being reachable.
CONFIG_PATHS = (
    Path("/opt/netbox/compose"),
    Path("/srv/netbox/media"),
    Path("/srv/netbox/reports"),
    Path("/srv/netbox/scripts"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/srv/netbox-backups/staging"),
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


def dump_postgres(destination: Path) -> None:
    """Stream a single-transaction pg_dump straight into a gzip file."""
    command = [
        DOCKER,
        "exec",
        POSTGRES_CONTAINER,
        "pg_dump",
        "--username=netbox",
        "--dbname=netbox",
        "--format=plain",
        "--no-owner",
        "--no-privileges",
        "--serializable-deferrable",
    ]
    with (
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process,
        gzip.open(destination, "wb", compresslevel=6) as output,
    ):
        if process.stdout is None:
            raise RuntimeError("pg_dump did not open stdout")
        shutil.copyfileobj(process.stdout, output, length=1024 * 1024)
        process.stdout.close()
        returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(f"NetBox pg_dump failed with exit code {returncode}")
    if destination.stat().st_size == 0:
        raise RuntimeError("NetBox pg_dump produced an empty archive")
    destination.chmod(0o600)


def archive_configuration(destination: Path) -> None:
    with tarfile.open(destination, "w:gz", compresslevel=6) as archive:
        for source in CONFIG_PATHS:
            if not source.exists():
                raise RuntimeError(f"required configuration path is missing: {source}")
            archive.add(source, arcname=str(source.relative_to("/")), recursive=True)
    destination.chmod(0o600)


def write_version_metadata(destination: Path) -> None:
    """Record the exact image references a restore has to match.

    A NetBox dump can only be loaded by the same or a newer schema, so the
    image reference is part of the backup, not incidental metadata.
    """
    result = subprocess.run(
        [DOCKER, "inspect", NETBOX_CONTAINER, POSTGRES_CONTAINER],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"container inspection failed with exit code {result.returncode}")

    sanitized = [
        {
            "name": container.get("Name", "").lstrip("/"),
            "image_reference": container.get("Config", {}).get("Image"),
            "image_id": container.get("Image"),
            "status": container.get("State", {}).get("Status"),
        }
        for container in json.loads(result.stdout)
    ]
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

    database_dump = database_root / "netbox.sql.gz"
    dump_postgres(database_dump)
    artifacts.append(artifact(database_dump, "postgres-transactional-dump", backup_root))

    config_archive = backup_root / "configuration-and-media.tar.gz"
    archive_configuration(config_archive)
    artifacts.append(artifact(config_archive, "configuration-archive", backup_root))

    version_metadata = backup_root / "image-versions.json"
    write_version_metadata(version_metadata)
    artifacts.append(artifact(version_metadata, "sanitized-metadata", backup_root))

    manifest = {
        "schema": 1,
        "created_utc": datetime.now(UTC).isoformat(),
        "hostname": socket.gethostname(),
        "retention": "append-only; no automatic pruning",
        "excluded_ephemeral": [
            {
                "path": "/srv/netbox/redis-tasks",
                "reason": "RQ queue state; jobs are re-runnable and are not source of truth",
            },
            {
                "path": "/srv/netbox/postgres",
                "reason": "live data directory; the transactional dump is the backup",
            },
        ],
        "restore_requires": "a NetBox image at or newer than image-versions.json",
        "artifacts": artifacts,
    }
    manifest_path = backup_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest_path.chmod(0o600)
    print(backup_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
