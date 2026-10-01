#!/usr/bin/env python3
"""Validate every inventory and live OpenTofu root against inventory/lab.yml.

ADR-0005: lab.yml is the single source of truth; the Ansible inventories and
live roots keep their literal values, and this check fails on any drift.

Usage: inventory_contract.py     (exit 1 and one line per drift)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "inventory"

# Drift that exists on purpose, with the reason and the plan to remove it.
# A ratchet: an entry that no longer drifts must be deleted (stale_known_drift).
KNOWN_DRIFT = {
    (
        "services/netbox/terraform/proxmox-guest/main.tf",
        "dns_server",
    ): "Live root still names the NAS's retired .20 address; changing it would make "
    "a plan against VM 330 propose a cloud-init change. Fix with the state migration "
    "(ADR-0003), then delete this entry.",
}


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def lab() -> dict:
    return load_yaml(INVENTORY / "lab.yml")


def _host(cidr: str | None) -> str | None:
    return cidr.split("/")[0] if cidr else None


def _hosts(inventory: dict) -> dict[str, dict]:
    """Flatten every host in an Ansible YAML inventory, merging group vars."""
    found: dict[str, dict] = {}

    def walk(group: dict, inherited: dict) -> None:
        merged = {**inherited, **(group.get("vars") or {})}
        for name, values in (group.get("hosts") or {}).items():
            found.setdefault(name, {}).update({**merged, **(values or {})})
        for child in (group.get("children") or {}).values():
            walk(child or {}, merged)

    walk(inventory.get("all", {}), {})
    return found


def check_ansible(data: dict) -> list[tuple[str, str, str]]:
    drift = []
    nodes = data["nodes"]
    proxmox = _hosts(load_yaml(INVENTORY / "hosts.yml"))
    for node_name, node in nodes.items():
        host = proxmox.get(node["inventory_name"])
        where = "inventory/hosts.yml"
        if host is None:
            drift.append((where, node["inventory_name"], "missing node"))
            continue
        for key, want in (
            ("ansible_host", node["address"]),
            ("expected_hostname", node_name),
            ("ssh_alias", node["alias"]),
            ("cluster_seed", node["cluster_seed"]),
            ("expected_host_fingerprint", node["host_fingerprint"]),
        ):
            if host.get(key) != want:
                drift.append((where, f"{node['inventory_name']}.{key}", f"{host.get(key)!r} != {want!r}"))

    for guest_name, guest in data["guests"].items():
        inventory_file = guest.get("inventory")
        if not inventory_file:
            continue
        where = f"inventory/{inventory_file}"
        hosts = _hosts(load_yaml(INVENTORY / inventory_file))
        host = hosts.get(guest_name)
        if host is None:
            drift.append((where, guest_name, "guest missing from its inventory"))
            continue
        checks = [("ansible_host", _host(guest["address"]))]
        if guest.get("admin_user"):
            checks.append(("ansible_user", guest["admin_user"]))
        if guest.get("ssh_key") and "ansible_ssh_private_key_file" in host:
            checks.append(("ansible_ssh_private_key_file", guest["ssh_key"]))
        for key, want in checks:
            if host.get(key) != want:
                drift.append((where, f"{guest_name}.{key}", f"{host.get(key)!r} != {want!r}"))

    # workstation itself, for the Plex role.
    media = _hosts(load_yaml(INVENTORY / "media.yml"))
    tower = data["workstation"]
    for key, want in (("ansible_host", tower["address"]), ("ansible_user", tower["ssh_user"])):
        if media.get("workstation", {}).get(key) != want:
            drift.append(("inventory/media.yml", f"workstation.{key}", "differs from lab.yml workstation"))
    if "media-vm" not in media:
        drift.append(("inventory/media.yml", "media-vm", "media guest missing"))

    # VM 300 also appears as a Docker host in the observability inventory.
    obs = _hosts(load_yaml(INVENTORY / "observability/hosts.yml"))
    vm300 = data["guests"]["homelab-services"]
    if obs.get("homelab-services", {}).get("ansible_host") != _host(vm300["address"]):
        drift.append(("inventory/observability/hosts.yml", "homelab-services.ansible_host", "differs"))
    return drift


def _tf_value(text: str, resource_marker: str, pattern: str) -> str | None:
    start = text.find(resource_marker)
    if start < 0:
        return None
    end = text.find('\nresource "', start + 1)
    block = text[start : end if end > 0 else len(text)]
    match = re.search(pattern, block)
    return match.group(1) if match else None


def check_tofu(data: dict) -> list[tuple[str, str, str]]:
    drift = []
    guests = data["guests"]

    # Import-first root: literal values per resource.
    rel = "platform/proxmox/terraform/homelab-guests/main.tf"
    text = (ROOT / rel).read_text(encoding="utf-8")
    for resource, name in (("homelab_services", "homelab-services"), ("observability", "observability")):
        marker = f'resource "proxmox_virtual_environment_vm" "{resource}"'
        guest = guests[name]
        for label, pattern, want in (
            ("vm_id", r"vm_id\s*=\s*(\d+)", str(guest["vmid"])),
            ("mac_address", r'mac_address\s*=\s*"([^"]+)"', guest["mac"]),
            ("cores", r"cores\s*=\s*(\d+)", str(guest["cores"])),
            ("cpu_type", r'type\s*=\s*"(host|x86-64[^"]*)"', guest["cpu_type"]),
            ("memory", r"dedicated\s*=\s*(\d+)", str(guest["memory_mib"])),
            ("on_boot", r"on_boot\s*=\s*(true|false)", str(guest["onboot"]).lower()),
        ):
            got = _tf_value(text, marker, pattern)
            if got != want:
                drift.append((rel, f"{name}.{label}", f"{got!r} != {want!r}"))

    # OpenBao root: the node map in variables.tf.
    rel = "security/secrets-openbao/terraform/variables.tf"
    text = (ROOT / rel).read_text(encoding="utf-8")
    for name in ("bao-1", "bao-2", "bao-3"):
        guest = guests[name]
        block = re.search(rf"{name}\s*=\s*\{{(.*?)\}}", text, re.S)
        if not block:
            drift.append((rel, name, "node missing"))
            continue
        body = block.group(1)
        for key, want in (
            ("vm_id", str(guest["vmid"])),
            ("node_name", guest["node"]),
            ("address", guest["address"]),
            ("mac_address", guest["mac"]),
            ("disk_datastore", guest["datastore"]),
            ("disk_format", guest["disk_format"]),
        ):
            match = re.search(rf'{key}\s*=\s*"?([^"\n]+?)"?\s*$', body, re.M)
            got = match.group(1) if match else None
            if got != want:
                drift.append((rel, f"{name}.{key}", f"{got!r} != {want!r}"))

    # NetBox root: variable defaults plus its DNS local.
    rel = "services/netbox/terraform/proxmox-guest/variables.tf"
    text = (ROOT / rel).read_text(encoding="utf-8")
    netbox = guests["netbox"]
    for var, want in (
        ("netbox_vm_id", str(netbox["vmid"])),
        ("netbox_node", netbox["node"]),
        ("netbox_address", netbox["address"]),
        ("netbox_mac_address", netbox["mac"]),
        ("netbox_memory_mib", str(netbox["memory_mib"])),
        ("netbox_disk_size_gib", str(netbox["disk_gib"])),
    ):
        match = re.search(rf'variable "{var}".*?default\s*=\s*"?([^"\n]+?)"?\s*$', text, re.S | re.M)
        got = match.group(1) if match else None
        if got != want:
            drift.append((rel, var, f"{got!r} != {want!r}"))
    for rel in (
        "services/netbox/terraform/proxmox-guest/main.tf",
        "security/secrets-openbao/terraform/locals.tf",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        match = re.search(r'dns_server\s*=\s*"([^"]+)"', text)
        if not match or match.group(1) != data["network"]["lab_resolver"]:
            drift.append((rel, "dns_server", f"{match.group(1) if match else None!r}"))
        match = re.search(r'gateway\s*=\s*"([^"]+)"', text)
        if not match or match.group(1) != data["network"]["gateway"]:
            drift.append((rel, "gateway", f"{match.group(1) if match else None!r}"))
    return drift


def check_identities(data: dict) -> list[tuple[str, str, str]]:
    drift = []
    guests = data["guests"].values()
    vmids = [g["vmid"] for g in guests]
    macs = [g["mac"] for g in guests if g.get("mac")]
    addresses = [_host(g["address"]) for g in guests if g.get("address")]
    for label, values in (("vmid", vmids), ("mac", macs), ("address", addresses)):
        dupes = {v for v in values if values.count(v) > 1}
        if dupes:
            drift.append(("inventory/lab.yml", f"duplicate {label}", str(sorted(dupes))))
    for retired in data.get("retired_vmids", []):
        if retired in vmids:
            drift.append(("inventory/lab.yml", "retired vmid reused", str(retired)))
    for guest in guests:
        if guest.get("node") and guest["node"] not in data["nodes"]:
            drift.append(("inventory/lab.yml", f"{guest['vmid']}.node", guest["node"]))
    for job in data["backup_jobs"]:
        if job["vmid"] not in vmids:
            drift.append(("inventory/lab.yml", "backup job for unknown vmid", str(job["vmid"])))
    return drift


def evaluate(data: dict | None = None) -> list[tuple[str, str, str]]:
    data = data or lab()
    return check_identities(data) + check_ansible(data) + check_tofu(data)


def unexpected(drift) -> list[str]:
    return [f"{w}: {k}: {d}" for w, k, d in drift if (w, k) not in KNOWN_DRIFT]


def stale_known_drift(drift) -> list[str]:
    present = {(w, k) for w, k, _ in drift}
    return [
        f"{w}: {k}: no longer drifts; remove it from KNOWN_DRIFT"
        for (w, k) in KNOWN_DRIFT
        if (w, k) not in present
    ]


def main() -> int:
    drift = evaluate()
    problems = unexpected(drift) + stale_known_drift(drift)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
