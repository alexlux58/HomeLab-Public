#!/usr/bin/env python3
"""Render Proxmox VE automated-install answer files (ladder rung L0).

One answer.toml per node, from inventory/lab.yml, in the PVE 9 kebab-case
format. Secrets are injected at build time from the environment and never
written anywhere but the git-ignored output directory:

  PVE_ROOT_PASSWORD_HASH   crypt(3) hash, e.g. from `mkpasswd -m sha-512`
  PVE_ROOT_SSH_KEYS_FILE   path to a file of root SSH *public* keys
  PVE_MAILTO               notification address

Default is a dry run that validates and prints each file with secrets
redacted. `--write` writes artifacts/autoinstall/<node>.toml with mode 0600.
Building the ISO (`proxmox-auto-install-assistant prepare-iso ...
--fetch-from iso --answer-file <node>.toml`) and booting it are operator steps.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import tomllib
import yaml

COMPONENT = Path(__file__).resolve().parents[1]
MONOREPO = COMPONENT.parents[1]
LAB = MONOREPO / "inventory" / "lab.yml"
OUT_DIR = COMPONENT / "artifacts" / "autoinstall"
REDACTED = "<redacted>"
FILESYSTEMS = {"ext4", "xfs", "zfs", "btrfs"}


class NotReady(Exception):
    """A required, operator-supplied input is missing."""


def _q(value: str) -> str:
    return json.dumps(value)  # a valid TOML basic string for these inputs


def _filter_lines(prefix: str, mapping: dict) -> list[str]:
    return [f"{prefix}.{key} = {_q(str(value))}" for key, value in sorted(mapping.items())]


def secrets_from_env(env=os.environ, redact: bool = False) -> dict:
    missing = [
        k
        for k in ("PVE_ROOT_PASSWORD_HASH", "PVE_ROOT_SSH_KEYS_FILE", "PVE_MAILTO")
        if not env.get(k)
    ]
    if missing and not redact:
        raise NotReady(f"set {', '.join(missing)} in the environment")
    keys: list[str] = []
    if env.get("PVE_ROOT_SSH_KEYS_FILE"):
        text = Path(env["PVE_ROOT_SSH_KEYS_FILE"]).read_text(encoding="utf-8")
        keys = [
            line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")
        ]
        if any(not k.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")) for k in keys):
            raise NotReady("PVE_ROOT_SSH_KEYS_FILE must contain public keys only")
    if not redact and not keys:
        raise NotReady("PVE_ROOT_SSH_KEYS_FILE holds no public key")
    password = env.get("PVE_ROOT_PASSWORD_HASH", "")
    if password and not password.startswith("$"):
        raise NotReady("PVE_ROOT_PASSWORD_HASH must be a crypt(3) hash, never a plain password")
    return {
        "password_hash": REDACTED if redact else password,
        "ssh_keys": [REDACTED] * max(len(keys), 1) if redact else keys,
        "mailto": REDACTED if redact else env["PVE_MAILTO"],
    }


def render(node_name: str, node: dict, lab: dict, secrets: dict) -> str:
    install = node.get("install") or {}
    for key in ("fqdn", "disk_filter", "interface_filter"):
        if not install.get(key):
            raise NotReady(
                f"{node_name}: inventory/lab.yml nodes.{node_name}.install.{key} is not set"
            )
    if install.get("filesystem") not in FILESYSTEMS:
        raise NotReady(f"{node_name}: filesystem must be one of {sorted(FILESYSTEMS)}")
    network = lab["network"]
    prefix = network["cidr"].split("/")[1]
    lines = [
        f"# Proxmox VE answer file for {node_name} ({node['alias']}), from inventory/lab.yml.",
        "[global]",
        'keyboard = "en-us"',
        'country = "us"',
        f"fqdn = {_q(install['fqdn'])}",
        f"mailto = {_q(secrets['mailto'])}",
        f"timezone = {_q(network['timezone'])}",
        f"root-password-hashed = {_q(secrets['password_hash'])}",
        "root-ssh-keys = [" + ", ".join(_q(k) for k in secrets["ssh_keys"]) + "]",
        "reboot-on-error = false",
        "",
        "[network]",
        'source = "from-answer"',
        f"cidr = {_q(node['address'] + '/' + prefix)}",
        # Hosts resolve through the the router; only guests need the lab zone.
        f"dns = {_q(network['gateway'])}",
        f"gateway = {_q(network['gateway'])}",
        *_filter_lines("filter", install["interface_filter"]),
        "",
        "[disk-setup]",
        f"filesystem = {_q(install['filesystem'])}",
        *_filter_lines("filter", install["disk_filter"]),
        'filter-match = "all"',
        "",
    ]
    text = "\n".join(lines)
    tomllib.loads(text)  # must parse
    return text


def build(lab: dict, nodes: list[str], env=os.environ, write: bool = False) -> dict[str, str]:
    secrets = secrets_from_env(env, redact=not write)
    rendered = {}
    for name in nodes:
        if name not in lab["nodes"]:
            raise NotReady(f"unknown node {name}")
        rendered[name] = render(name, lab["nodes"][name], lab, secrets)
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for name, text in rendered.items():
            path = OUT_DIR / f"{name}.toml"
            path.write_text(text, encoding="utf-8")
            path.chmod(0o600)
    return rendered


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--node", action="append", help="node name from lab.yml (default: all)")
    parser.add_argument(
        "--write", action="store_true", help="write real files to artifacts/autoinstall"
    )
    args = parser.parse_args(argv)
    with LAB.open(encoding="utf-8") as fh:
        lab = yaml.safe_load(fh)
    nodes = args.node or sorted(lab["nodes"])
    try:
        rendered = build(lab, nodes, write=args.write)
    except NotReady as reason:
        print(f"NOT READY: {reason}", file=sys.stderr)
        return 2
    for name, text in rendered.items():
        if args.write:
            print(f"wrote {OUT_DIR / (name + '.toml')} (mode 0600)")
        else:
            print(f"--- {name} (dry run, secrets redacted) ---\n{text}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
