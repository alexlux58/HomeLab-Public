#!/usr/bin/env python3
"""Verify, decrypt, and structurally inspect an encrypted Raft snapshot offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--age-identity", type=Path, required=True)
    parser.add_argument("--checksum", type=Path)
    args = parser.parse_args()

    if not args.input.is_file() or not args.age_identity.is_file():
        print("snapshot or age identity is missing", file=sys.stderr)
        return 2
    if args.age_identity.stat().st_mode & 0o077:
        print("age identity must be mode 0600", file=sys.stderr)
        return 2

    checksum_path = args.checksum or Path(f"{args.input}.sha256")
    actual = sha256(args.input)
    if checksum_path.is_file():
        expected = checksum_path.read_text(encoding="utf-8").split()[0]
        if actual != expected:
            print("encrypted snapshot checksum mismatch", file=sys.stderr)
            return 3

    with tempfile.TemporaryDirectory(prefix="openbao-restore-inspect-") as directory:
        plaintext = Path(directory) / "snapshot.snap"
        decrypt = subprocess.run(
            [
                "age",
                "--decrypt",
                "--identity",
                str(args.age_identity),
                "--output",
                str(plaintext),
                str(args.input),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if decrypt.returncode != 0:
            print("snapshot decryption failed", file=sys.stderr)
            return 4
        inspect = subprocess.run(
            ["bao", "operator", "raft", "snapshot", "inspect", str(plaintext)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if inspect.returncode != 0:
            print("OpenBao snapshot structure inspection failed", file=sys.stderr)
            return 5
    print(
        json.dumps({"status": "verified", "sha256": actual, "restore_performed": False})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
