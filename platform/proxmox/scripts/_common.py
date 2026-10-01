"""Shared helpers for the migration tooling.

Standard library only, on purpose: these scripts must run on a bare macOS
controller and inside an offline CI runner without installing anything.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGTPE]?)i?B?\s*$", re.IGNORECASE)
_SIZE_MULT = {
    "": 1,
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
    "P": 1024**5,
    "E": 1024**6,
}


def eprint(*args: Any) -> None:
    """Print to stderr so stdout stays machine-readable."""
    print(*args, file=sys.stderr)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: str | Path) -> Any:
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"ERROR: input file not found: {p}")
    try:
        with p.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: {p} is not valid JSON: {exc}") from exc


def dump_json(obj: Any, path: str | Path | None) -> str:
    text = json.dumps(obj, indent=2, sort_keys=False, default=str) + "\n"
    if path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return text


def write_text(text: str, path: str | Path | None) -> str:
    if path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return text


def parse_size(value: Any) -> int:
    """Parse '32G', '512M', '1.5T', 1234 or '1234' into bytes.

    Proxmox writes disk sizes as ``size=32G`` in guest configs and as raw byte
    counts in API output, so both forms have to work. Unparseable values return
    0 rather than raising: a missing size must never crash a capacity report,
    it must show up as an explicit zero the operator can see.
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    match = _SIZE_RE.match(str(value))
    if not match:
        return 0
    number, unit = match.groups()
    return int(float(number) * _SIZE_MULT[unit.upper()])


def human_bytes(num: float) -> str:
    """Render a byte count with binary units, e.g. 1.5 TiB."""
    step = 1024.0
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(value) < step or unit == "PiB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} PiB"


def normalize_mac(mac: str | None) -> str:
    """Uppercase, colon-separated MAC. Empty string for anything unusable."""
    if not mac:
        return ""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", str(mac))
    if len(cleaned) != 12:
        return ""
    cleaned = cleaned.upper()
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


def hosts_of(discovery: dict) -> dict[str, dict]:
    hosts = discovery.get("hosts")
    if not isinstance(hosts, dict):
        raise SystemExit("ERROR: discovery document has no 'hosts' object")
    return hosts


def iter_guests(discovery: dict) -> Iterator[tuple[str, dict]]:
    """Yield (inventory_hostname, guest) for every guest on every host."""
    for host_name, host in sorted(hosts_of(discovery).items()):
        for guest in host.get("guests", []) or []:
            yield host_name, guest


def guest_label(guest: dict) -> str:
    return f"{guest.get('vmid', '?')}/{guest.get('name', 'unnamed')}"


def guest_disk_bytes(guest: dict, include_unused: bool = True) -> int:
    """Total provisioned bytes for a guest, used for backup size estimates."""
    total = 0
    for disk in guest.get("disks", []) or []:
        if disk.get("media") == "cdrom":
            continue
        total += parse_size(disk.get("size_bytes") or disk.get("size"))
    if include_unused:
        for disk in guest.get("unused_disks", []) or []:
            total += parse_size(disk.get("size_bytes") or disk.get("size"))
    for extra_key in ("efidisk", "tpmstate"):
        extra = guest.get(extra_key)
        if isinstance(extra, dict):
            total += parse_size(extra.get("size_bytes") or extra.get("size"))
    return total


def backed_up_disk_bytes(guest: dict) -> int:
    """Bytes that vzdump will actually write (disks with backup enabled)."""
    total = 0
    for disk in guest.get("disks", []) or []:
        if disk.get("media") == "cdrom":
            continue
        if disk.get("backup") is False:
            continue
        total += parse_size(disk.get("size_bytes") or disk.get("size"))
    return total


def excluded_disks(guest: dict) -> list[dict]:
    """Disks that vzdump will silently skip because backup=0."""
    return [
        d
        for d in guest.get("disks", []) or []
        if d.get("backup") is False and d.get("media") != "cdrom"
    ]


def pct(part: float, whole: float) -> float:
    return 0.0 if not whole else round(100.0 * part / whole, 1)


def fail(message: str, code: int = 1) -> None:
    eprint(f"FAIL: {message}")
    raise SystemExit(code)
