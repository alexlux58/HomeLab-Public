"""inventory/lab.yml is the single source of truth (ADR-0005): every Ansible
inventory and live OpenTofu root agrees with it, and the check can fail."""

import copy

import inventory_contract as ic
import pytest


@pytest.fixture(scope="module")
def lab():
    return ic.lab()


def test_no_unexpected_drift(lab):
    assert ic.unexpected(ic.evaluate(lab)) == []


def test_known_drift_entries_are_still_real(lab):
    assert ic.stale_known_drift(ic.evaluate(lab)) == []


@pytest.mark.parametrize(
    ("mutate", "expected_key"),
    [
        (lambda d: d["guests"]["netbox"].update(mac="52:54:00:00:00:00"), "netbox_mac_address"),
        (lambda d: d["guests"]["homelab-services"].update(memory_mib=8192), "homelab-services.memory"),
        (lambda d: d["guests"]["observability"].update(onboot=True), "observability.on_boot"),
        (lambda d: d["guests"]["bao-2"].update(address="198.51.100.99/22"), "bao-2.address"),
        (
            lambda d: d["nodes"]["pve1"].update(host_fingerprint="SHA256:x"),
            "pve1.expected_host_fingerprint",
        ),
        (lambda d: d["nodes"]["pve3"].update(address="192.168.0.1"), "pve.ansible_host"),
        (lambda d: d["guests"]["netbox"].update(admin_user="root"), "netbox.ansible_user"),
        (lambda d: d["guests"]["bao-3"].update(vmid=320), "duplicate vmid"),
        (lambda d: d["guests"]["bao-3"].update(vmid=297), "retired vmid reused"),
        (lambda d: d["network"].update(gateway="198.51.100.254"), "gateway"),
    ],
)
def test_drift_is_detected(lab, mutate, expected_key):
    data = copy.deepcopy(lab)
    mutate(data)
    keys = {key for _, key, _ in ic.evaluate(data)}
    assert expected_key in keys


def test_every_rebuildable_guest_has_full_identity(lab):
    required = {
        "vmid",
        "node",
        "address",
        "mac",
        "cores",
        "cpu_type",
        "memory_mib",
        "disk_gib",
        "datastore",
        "disk_format",
        "admin_user",
        "onboot",
        "startup",
    }
    for name, guest in lab["guests"].items():
        if guest.get("rebuild"):
            missing = {k for k in required if guest.get(k) is None}
            assert not missing, f"{name} lacks {missing}"


def test_every_guest_has_a_backup_job_or_a_reason(lab):
    covered = {job["vmid"] for job in lab["backup_jobs"]}
    for name, guest in lab["guests"].items():
        if guest.get("restore_from") == "none":
            continue
        assert guest["vmid"] in covered, f"{name} ({guest['vmid']}) has no vzdump job"


def test_no_backup_job_prunes(lab):
    for job in lab["backup_jobs"]:
        assert "prune" not in job and "remove" not in job
    assert lab["cluster"]["backup_storage"] == "synology-backup"
