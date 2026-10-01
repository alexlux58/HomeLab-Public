"""Inventory schema validation. Runs offline; contacts nothing."""

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.repo

MONOREPO_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_ROOT = MONOREPO_ROOT / "inventory"

REQUIRED_HOST_KEYS = {
    "ansible_host",
    "expected_hostname",
    "preserve_guests",
    "cluster_seed",
    "ssh_alias",
    "expected_host_fingerprint",
}
IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
FINGERPRINT = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


@pytest.fixture
def inventory(repo_root):
    with (INVENTORY_ROOT / "hosts.yml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture
def proxmox_hosts(inventory):
    return inventory["all"]["children"]["proxmox"]["hosts"]


def test_exactly_three_proxmox_hosts(proxmox_hosts):
    assert set(proxmox_hosts) == {"pve1", "pve2", "pve"}


def test_every_host_has_the_required_keys(proxmox_hosts):
    for name, host in proxmox_hosts.items():
        missing = REQUIRED_HOST_KEYS - set(host)
        assert not missing, f"{name} is missing {sorted(missing)}"


def test_addresses_match_the_documented_environment(proxmox_hosts):
    assert proxmox_hosts["pve1"]["ansible_host"] == "192.168.0.11"
    assert proxmox_hosts["pve2"]["ansible_host"] == "192.168.0.12"
    assert proxmox_hosts["pve"]["ansible_host"] == "192.168.0.13"
    for host in proxmox_hosts.values():
        assert IPV4.match(host["ansible_host"])


def test_exactly_one_cluster_seed(proxmox_hosts):
    seeds = [n for n, h in proxmox_hosts.items() if h["cluster_seed"]]
    assert seeds == ["pve1"]


def test_cluster_seed_hostname_does_not_collide_with_host_boolean(repo_root):
    with (INVENTORY_ROOT / "group_vars/all.yml").open(encoding="utf-8") as fh:
        group_vars = yaml.safe_load(fh)
    assert group_vars["cluster_seed_host"] == "pve1"
    assert "cluster_seed" not in group_vars


def test_preserve_flags_match_the_plan(proxmox_hosts):
    assert proxmox_hosts["pve1"]["preserve_guests"] is True
    assert proxmox_hosts["pve2"]["preserve_guests"] is False
    assert proxmox_hosts["pve"]["preserve_guests"] is False


def test_fingerprints_are_well_formed(proxmox_hosts):
    for name, host in proxmox_hosts.items():
        assert FINGERPRINT.match(host["expected_host_fingerprint"]), name


def test_fingerprints_are_unique(proxmox_hosts):
    values = [h["expected_host_fingerprint"] for h in proxmox_hosts.values()]
    assert len(values) == len(set(values))


def test_no_credentials_anywhere_in_the_inventory(repo_root):
    text = (INVENTORY_ROOT / "hosts.yml").read_text()
    for banned in ("password", "passwd", "ansible_pass", "token", "secret", "PRIVATE KEY"):
        assert banned.lower() not in text.lower(), f"'{banned}' must not appear in the inventory"


def test_connection_vars_are_key_based(inventory):
    group_vars = inventory["all"]["children"]["proxmox"]["vars"]
    assert group_vars["ansible_user"] == "root"
    assert group_vars["ansible_python_interpreter"] == "/usr/bin/python3"
    assert group_vars["ansible_ssh_private_key_file"] == "{{ ssh_private_key_file }}"


def test_key_filename_is_defined_exactly_once(repo_root):
    """The key name must be one documented variable, not scattered literals."""
    hits = []
    # The inventory moved to the monorepo root in Phase 1, so the scan covers
    # both the shared inventory and this component.
    candidates = list(INVENTORY_ROOT.rglob("*")) + list(repo_root.rglob("*"))
    for path in candidates:
        if not path.is_file():
            continue
        rel = path.relative_to(MONOREPO_ROOT).as_posix()
        component_rel = (
            path.relative_to(repo_root).as_posix() if path.is_relative_to(repo_root) else ""
        )
        # Generated output legitimately contains the resolved key path many
        # times. The rule is that the filename is *defined* once in source.
        if component_rel.startswith(
            (".venv/", ".ansible/", ".git/", "docs/", "artifacts/", "host-configs/", "site/")
        ):
            continue
        if component_rel in ("README.md", "tests/test_inventory_schema.py"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "proxmox_cluster_ed25519" not in line:
                continue
            if line.strip().startswith("#"):
                continue  # explanatory comments may name the file
            hits.append(f"{rel}:{i} -> {line.strip()}")
    assert len(hits) == 1, (
        "the key filename must be defined exactly once, as ssh_key_name in "
        "group_vars; found: " + str(hits)
    )
    assert hits[0].startswith("inventory/group_vars/all.yml")
    assert "ssh_key_name:" in hits[0]


def test_convenience_groups_are_consistent(inventory):
    children = inventory["all"]["children"]
    assert set(children["preserve"]["hosts"]) == {"pve1"}
    assert set(children["disposable"]["hosts"]) == {"pve2", "pve"}
    assert set(children["seed"]["hosts"]) == {"pve1"}


def test_guest_retention_scope_matches_the_operator_decision(repo_root):
    with (INVENTORY_ROOT / "group_vars/all.yml").open(encoding="utf-8") as fh:
        group_vars = yaml.safe_load(fh)

    assert set(group_vars["protected_guests"]) == {"pve1"}
    # 2026-09-19: the operator confirmed VM 297 ubuntu-vm obsolete and destroyed
    # it. This list drives vzdump_backup_targets, so an entry for a guest that no
    # longer exists would fail every backup stage. VM 290 EVENG is now the only
    # protected migration guest.
    assert {guest["vmid"] for guest in group_vars["protected_guests"]["pve1"]} == {290}
    assert {guest["vmid"] for guest in group_vars["disposable_guests"]["pve2"]} == {
        100,
        101,
        102,
        9000,
        9100,
    }
    assert {guest["vmid"] for guest in group_vars["disposable_guests"]["pve"]} == {
        100,
        101,
        102,
    }
