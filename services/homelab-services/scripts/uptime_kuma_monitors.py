#!/usr/bin/env python3
"""Report drift between config/uptime-kuma/monitors.yml and a backup dump.

Uptime Kuma 2 on VM 300 stores monitors in MariaDB. The nightly application
backup writes `uptime-kuma-all-databases.sql.gz` (mariadb-dump). This script
reads the `monitor` table straight from that dump: no database connection, no
write path, nothing on VM 300 is touched.

Usage: uptime_kuma_monitors.py --dump /path/uptime-kuma-all-databases.sql.gz
Exit 1 on drift.
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config" / "uptime-kuma" / "monitors.yml"
CREATE = re.compile(r"CREATE TABLE `monitor` \((.*?)\n\)", re.S)
COLUMN = re.compile(r"^\s*`([^`]+)`", re.M)
INSERT = re.compile(r"INSERT INTO `monitor` VALUES (.*?);\n", re.S)


def declared(path: Path = CONFIG) -> dict[str, str]:
    with path.open(encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    return {m["name"]: m["url"] for m in config["monitors"]}


def _tuples(values: str) -> list[list[str | None]]:
    """Split mariadb-dump extended-insert VALUES into rows of Python values."""
    rows, row, field, quoted, i = [], [], [], False, 0
    in_row = False
    while i < len(values):
        char = values[i]
        if quoted:
            if char == "\\" and i + 1 < len(values):
                field.append({"n": "\n", "t": "\t", "0": "\0"}.get(values[i + 1], values[i + 1]))
                i += 2
                continue
            if char == "'":
                quoted = False
            else:
                field.append(char)
        elif char == "'":
            quoted = True
        elif char == "(" and not in_row:
            in_row, row, field = True, [], []
        elif char in ",)" and in_row:
            text = "".join(field).strip()
            row.append(None if text == "NULL" else text)
            field = []
            if char == ")":
                rows.append(row)
                in_row = False
        elif in_row:
            field.append(char)
        i += 1
    return rows


def from_dump(dump: Path) -> dict[str, str]:
    opener = gzip.open if dump.suffix == ".gz" else open
    with opener(dump, "rt", encoding="utf-8") as fh:
        text = fh.read()
    create = CREATE.search(text)
    if not create:
        raise SystemExit("no `monitor` table in this dump")
    columns = COLUMN.findall(create.group(1))
    name_at, url_at = columns.index("name"), columns.index("url")
    monitors = {}
    for statement in INSERT.findall(text):
        for row in _tuples(statement):
            monitors[row[name_at]] = row[url_at] or ""
    return monitors


def drift(want: dict[str, str], have: dict[str, str]) -> list[str]:
    lines = [f"missing: {name} ({url})" for name, url in sorted(want.items()) if name not in have]
    lines += [f"undeclared: {name}" for name in sorted(have) if name not in want]
    lines += [
        f"url differs: {name}: {have[name]} != {url}"
        for name, url in sorted(want.items())
        if name in have and have[name].rstrip("/") != url.rstrip("/")
    ]
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump", required=True, type=Path)
    args = parser.parse_args(argv)
    lines = drift(declared(), from_dump(args.dump))
    for line in lines:
        print(line)
    if not lines:
        print("Uptime Kuma matches monitors.yml")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
