#!/usr/bin/env python3
"""Create a replacement AppRole SecretID in a protected operator file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from configure_openbao import BaoClient, BaoError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", required=True)
    parser.add_argument("--ca-cert", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    expected = f"ROTATE APPROLE {args.role}"
    if args.confirm != expected:
        print(f"exact confirmation required: {expected}", file=sys.stderr)
        return 2
    if args.output.exists():
        print("output exists; refusing to overwrite SecretID material", file=sys.stderr)
        return 2
    if not args.token_file.is_file() or not args.ca_cert.is_file():
        print("operator token or CA file is missing", file=sys.stderr)
        return 2
    token = args.token_file.read_text(encoding="utf-8").strip()
    try:
        response = BaoClient(args.address, args.ca_cert, token).request(
            "POST", f"auth/approle/role/{args.role}/secret-id", {}
        )
        data = response.get("data", {})
        if not data.get("secret_id") or not data.get("secret_id_accessor"):
            raise BaoError("OpenBao returned incomplete SecretID material")
    except BaoError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    args.output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "role": args.role,
                "secret_id": data["secret_id"],
                "secret_id_accessor": data["secret_id_accessor"],
            },
            handle,
            indent=2,
        )
        handle.write("\n")
    print(f"replacement AppRole material written to protected file {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
