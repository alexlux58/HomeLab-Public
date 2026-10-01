#!/usr/bin/env python3
"""Create, encrypt, retain locally, and SFTP an OpenBao Raft snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

SAFE_REMOTE = re.compile(r"^/[A-Za-z0-9._/-]+$")


def require_private_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} is missing")
    if path.stat().st_mode & 0o077:
        raise ValueError(f"{label} must not be group/world accessible")


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> None:
    subprocess.run(
        command,
        env=env,
        input=input_text,
        text=input_text is not None,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--age-recipient-file", type=Path, required=True)
    parser.add_argument("--local-dir", type=Path, required=True)
    parser.add_argument("--sftp-host", required=True)
    parser.add_argument("--sftp-port", type=int, default=22)
    parser.add_argument("--sftp-user", required=True)
    parser.add_argument("--sftp-key", type=Path, required=True)
    parser.add_argument("--sftp-known-hosts", type=Path, required=True)
    parser.add_argument("--remote-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        require_private_file(args.token_file, "Agent token file")
        require_private_file(args.sftp_key, "SFTP private key")
        if not args.age_recipient_file.is_file() or not args.sftp_known_hosts.is_file():
            raise ValueError("age recipient or SFTP known_hosts file is missing")
        if not SAFE_REMOTE.fullmatch(args.remote_dir):
            raise ValueError("remote directory contains unsupported characters")
        if not 1 <= args.sftp_port <= 65535:
            raise ValueError("SFTP port is outside the valid range")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    args.local_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"openbao-raft-{stamp}"
    plaintext = args.local_dir / f".{base}.snap.unencrypted"
    encrypted = args.local_dir / f"{base}.snap.age"
    checksum_file = args.local_dir / f"{base}.snap.age.sha256"
    manifest_file = args.local_dir / f"{base}.manifest.json"

    environment = os.environ.copy()
    environment["BAO_TOKEN"] = args.token_file.read_text(encoding="utf-8").strip()
    environment.setdefault("BAO_CLIENT_TIMEOUT", "120s")
    try:
        run(
            ["bao", "operator", "raft", "snapshot", "save", str(plaintext)],
            env=environment,
        )
    except subprocess.CalledProcessError:
        print("OpenBao Raft snapshot creation failed", file=sys.stderr)
        return 3

    try:
        run(
            [
                "age",
                "--recipients-file",
                str(args.age_recipient_file),
                "--output",
                str(encrypted),
                str(plaintext),
            ]
        )
    except subprocess.CalledProcessError:
        print(
            "snapshot encryption failed; plaintext retained for operator investigation",
            file=sys.stderr,
        )
        return 4
    else:
        plaintext.unlink()

    encrypted.chmod(0o600)
    checksum = sha256(encrypted)
    checksum_file.write_text(f"{checksum}  {encrypted.name}\n", encoding="utf-8")
    checksum_file.chmod(0o600)
    manifest = {
        "format": 1,
        "created_utc": stamp,
        "encrypted_file": encrypted.name,
        "sha256": checksum,
        "size": encrypted.stat().st_size,
        "encryption": "age recipient outside OpenBao",
    }
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_file.chmod(0o600)

    batch = "".join(
        f"put {path} {args.remote_dir}/{path.name}\n"
        for path in (encrypted, checksum_file, manifest_file)
    )
    try:
        run(
            [
                "sftp",
                "-b",
                "-",
                # sftp spells the port -P, not -p. The pinned known_hosts entry
                # must be port-qualified as [host]:port to match.
                "-P",
                str(args.sftp_port),
                "-i",
                str(args.sftp_key),
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                f"UserKnownHostsFile={args.sftp_known_hosts}",
                f"{args.sftp_user}@{args.sftp_host}",
            ],
            input_text=batch,
        )
    except subprocess.CalledProcessError:
        print(
            "SFTP transfer failed; encrypted local snapshot was preserved",
            file=sys.stderr,
        )
        return 5

    print(
        json.dumps(
            {"status": "transferred", "file": encrypted.name, "sha256": checksum}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
