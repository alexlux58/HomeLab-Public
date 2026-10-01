#!/usr/bin/env python3
"""Generate NetBox bulk-import CSV files from inventory/lab.yml (L5).

Automation never writes to NetBox: the operator imports these files through
NetBox's bulk import (Devices, Virtual Machines, IP Addresses) in that order,
after creating the site, the "homelab" cluster and the roles by hand.

Usage: netbox_seed_csv.py [--out DIR]   (default: print all three to stdout)
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

import yaml

LAB = Path(__file__).resolve().parents[3] / "inventory" / "lab.yml"
SITE = "home-lab"
CLUSTER = "homelab"


def load(path: Path = LAB) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def devices(lab: dict) -> list[dict]:
    rows = [
        {
            "name": name,
            "role": "hypervisor",
            "site": SITE,
            "status": "active",
            "description": node["hardware"],
        }
        for name, node in sorted(lab["nodes"].items())
    ]
    rows.append(
        {
            "name": lab["nas"]["name"],
            "role": "storage",
            "site": SITE,
            "status": "active",
            "description": lab["nas"]["model"],
        }
    )
    return rows


def virtual_machines(lab: dict) -> list[dict]:
    rows = []
    for name, guest in sorted(lab["guests"].items(), key=lambda item: item[1]["vmid"]):
        if not guest.get("node"):
            continue
        rows.append(
            {
                "name": name,
                "cluster": CLUSTER,
                "device": guest["node"],
                "status": "active",
                "vcpus": guest.get("cores", ""),
                "memory": guest.get("memory_mib", ""),
                "disk": (guest["disk_gib"] * 1024) if guest.get("disk_gib") else "",
                "description": f"VMID {guest['vmid']}",
            }
        )
    return rows


def ip_addresses(lab: dict) -> list[dict]:
    zone = lab["network"]["dns_zone"]
    prefix = lab["network"]["cidr"].split("/")[1]
    rows = [
        {
            "address": f"{node['address']}/{prefix}",
            "status": "active",
            "dns_name": "",
            "description": f"{name} management",
        }
        for name, node in sorted(lab["nodes"].items())
    ]
    for name, guest in sorted(lab["guests"].items()):
        if guest.get("address"):
            rows.append(
                {
                    "address": guest["address"],
                    "status": "active",
                    "dns_name": f"{name}.{zone}",
                    "description": f"VMID {guest['vmid']} {name}",
                }
            )
    rows.append(
        {
            "address": f"{lab['nas']['address']}/{prefix}",
            "status": "active",
            "dns_name": "",
            "description": "NAS",
        }
    )
    return rows


def to_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, help="directory to write the CSV files into")
    args = parser.parse_args(argv)
    lab = load()
    files = {
        "1-devices.csv": devices(lab),
        "2-virtual-machines.csv": virtual_machines(lab),
        "3-ip-addresses.csv": ip_addresses(lab),
    }
    for filename, rows in files.items():
        text = to_csv(rows)
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / filename).write_text(text, encoding="utf-8")
            print(f"wrote {args.out / filename}")
        else:
            print(f"# {filename}\n{text}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
