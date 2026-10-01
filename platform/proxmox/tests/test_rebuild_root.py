"""The rebuild-only root (ADR-0007) can only ever create guests after an
explicit, exact confirmation, and never touches a live root."""

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.repo

MONOREPO_ROOT = Path(__file__).resolve().parents[3]
ROOT_DIR = Path(__file__).resolve().parents[1] / "terraform" / "rebuild-guests"


def _text(name):
    return (ROOT_DIR / name).read_text(encoding="utf-8")


def test_default_selection_is_empty_and_confirmation_is_exact():
    variables = _text("variables.tf")
    assert re.search(r'variable "rebuild_guests".*?default\s*=\s*\[\]', variables, re.S)
    assert re.search(r'variable "rebuild_confirmation".*?default\s*=\s*""', variables, re.S)
    main = _text("main.tf")
    assert (
        'expected_confirmation = "REBUILD ${join(" ", sort(tolist(var.rebuild_guests)))} FROM ZERO"'
        in main
    )
    assert "var.rebuild_confirmation == local.expected_confirmation" in main


def test_every_created_vm_is_protected_off_and_indestructible():
    main = _text("main.tf")
    for line in (
        "protection                           = true",
        "on_boot                              = false",
        "started                              = false",
        "purge_on_destroy                     = false",
        "delete_unreferenced_disks_on_destroy = false",
        "prevent_destroy = true",
    ):
        assert line in main, line


def test_identities_come_from_lab_yml_only():
    main = _text("main.tf")
    assert "yamldecode(file(var.lab_file))" in main
    assert not re.search(r"vm_id\s*=\s*\d", main), "no literal VMIDs"
    assert not re.search(r'mac_address\s*=\s*"', main), "no literal MACs"
    assert not re.search(r"\b192\.168\.", main), "no literal addresses"


def test_rebuildable_set_matches_the_live_roots():
    """Every guest the rebuild root can create has a live root, and vice versa."""
    with (MONOREPO_ROOT / "inventory/lab.yml").open(encoding="utf-8") as fh:
        lab = yaml.safe_load(fh)
    rebuildable = {g["vmid"] for g in lab["guests"].values() if g.get("rebuild")}
    assert rebuildable == {300, 310, 320, 321, 322, 330}


def test_no_apply_destroy_or_import_target_exists():
    makefile = (ROOT_DIR.parents[1] / "Makefile").read_text(encoding="utf-8")
    for banned in ("rebuild-guests-apply", "rebuild-guests-destroy", "rebuild-guests-import"):
        assert banned not in makefile
    assert not re.search(
        r"\b(tofu|terraform)\b[^\n]*\b(apply|destroy|import)\b",
        makefile.split("rebuild-guests-fmt")[1],
    )


def test_state_is_local_encrypted_and_lock_file_is_pinned():
    state = _text("state.tofu")
    assert 'backend "local"' in state
    assert 'path          = "/homelab-state/rebuild-guests/terraform.tfstate"' in state
    assert 'key_provider "pbkdf2"' in state
    assert "enforced = true" in state
    assert 'method "aes_gcm"' in state
    assert 'path = "/homelab-state/rebuild-guests/terraform.tfstate"' in _text(
        "backend.hcl.example"
    )
    lock = _text(".terraform.lock.hcl")
    assert 'provider "registry.opentofu.org/bpg/proxmox"' in lock
    assert 'version     = "0.107.0"' in lock


def test_offline_behaviour_tests_exist():
    tests = _text("tests/rebuild.tftest.hcl")
    assert 'mock_provider "proxmox"' in tests
    for run in (
        "default_plan_creates_nothing",
        "wrong_confirmation_is_refused",
        "non_rebuildable_guest_is_refused",
        "confirmed_rebuild_plans_one_guest_from_lab_yml",
    ):
        assert f'run "{run}"' in tests
