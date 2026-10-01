#!/usr/bin/env python3
"""Offline structural checks for the observability repository."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker" / "compose.yaml"
REQUIRED_DASHBOARDS = {
    "fleet-overview.json",
    "proxmox.json",
    "synology.json",
    "linux-hosts.json",
    "docker.json",
    "logs.json",
    "availability.json",
    "storage-trends.json",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    compose_text = COMPOSE.read_text(encoding="utf-8")
    if re.search(r"image:\s*\S+:(?:latest|main|master)\s*$", compose_text, re.MULTILINE):
        fail("Compose contains a floating image tag")

    dashboards_dir = ROOT / "config" / "grafana" / "dashboards"
    present = {path.name for path in dashboards_dir.glob("*.json")}
    missing = REQUIRED_DASHBOARDS - present
    if missing:
        fail(f"missing dashboards: {sorted(missing)}")

    for path in dashboards_dir.glob("*.json"):
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not payload.get("uid") or not payload.get("title"):
            fail(f"dashboard lacks uid/title: {path}")

    forbidden_names = {
        "snmp.yml",
        "pve.yml",
        "grafana_admin_password",
        "smtp_password",
    }
    committed_forbidden = [
        path for path in ROOT.rglob("*") if path.is_file() and path.name in forbidden_names
    ]
    if committed_forbidden:
        fail(f"runtime secret file present in repository: {committed_forbidden}")

    print("PASS: offline structure, image pinning, dashboards, and secret boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
