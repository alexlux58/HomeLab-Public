#!/usr/bin/env python3
"""Read-only validation of an initialized OpenBao cluster."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from configure_openbao import BaoClient, BaoError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", required=True)
    parser.add_argument("--ca-cert", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--expected-peers", type=int, default=3)
    args = parser.parse_args()
    if not args.token_file.is_file() or not args.ca_cert.is_file():
        print("operator token or CA file is missing", file=sys.stderr)
        return 2
    token = args.token_file.read_text(encoding="utf-8").strip()
    client = BaoClient(args.address, args.ca_cert, token)
    issues: list[str] = []
    report: dict[str, object] = {"address": args.address}
    try:
        health = client.request("GET", "sys/health", expected=(200, 429))
        if not health.get("initialized"):
            issues.append("cluster is not initialized")
        if health.get("sealed"):
            issues.append("responding node is sealed")
        report["initialized"] = bool(health.get("initialized"))
        report["sealed"] = bool(health.get("sealed"))

        raft = client.request("GET", "sys/storage/raft/configuration")
        servers = raft.get("data", {}).get("config", {}).get("servers", [])
        voters = [server for server in servers if server.get("voter")]
        leaders = [server for server in servers if server.get("leader")]
        if len(voters) != args.expected_peers:
            issues.append(f"expected {args.expected_peers} voters, found {len(voters)}")
        if len(leaders) != 1:
            issues.append(f"expected one leader, found {len(leaders)}")
        report["voters"] = len(voters)
        report["leaders"] = len(leaders)

        mounts = client.request("GET", "sys/mounts").get("data", {})
        expected_mounts = {"kv/", "transit/", "pki_int/"}
        missing_mounts = sorted(expected_mounts - set(mounts))
        if missing_mounts:
            issues.append(f"missing mounts: {', '.join(missing_mounts)}")

        auth = client.request("GET", "sys/auth").get("data", {})
        if "approle/" not in auth:
            issues.append("AppRole auth is not enabled")

        audit = client.request("GET", "sys/audit").get("data", {})
        if "local-file/" not in audit:
            issues.append("declarative local audit device is not active")
    except (BaoError, AttributeError, TypeError) as exc:
        print(f"cluster validation failed: {exc}", file=sys.stderr)
        return 3
    report["status"] = "pass" if not issues else "fail"
    report["issues"] = issues
    print(json.dumps(report, indent=2))
    return 0 if not issues else 4


if __name__ == "__main__":
    raise SystemExit(main())
