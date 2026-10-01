#!/usr/bin/env python3
"""Export only public backup-node identity from canonical inventory for Windows."""

import argparse
import json
from pathlib import Path

import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", required=True, choices=["pve1", "pve2", "pve"])
    args = parser.parse_args()
    lab = yaml.safe_load((Path(__file__).resolve().parents[3] / "inventory/lab.yml").read_text())
    node = next(value for value in lab["nodes"].values() if value["inventory_name"] == args.node)
    print(
        json.dumps(
            {"node": args.node, "address": node["address"], "fingerprint": node["host_fingerprint"]}
        )
    )


if __name__ == "__main__":
    main()
