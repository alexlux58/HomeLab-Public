"""The media component follows the same safety contract as the rest of the lab."""

import re

import pytest
import yaml

ROLE_GATES = {
    "media_host": ("media_host_allow", "media_host_confirmation", "MEDIA HOST "),
    "arr_stack": ("arr_stack_allow", "arr_stack_confirmation", "MEDIA DEPLOY "),
    "media_backup": ("media_backup_allow", "media_backup_confirmation", "MEDIA BACKUP "),
}


@pytest.fixture(scope="module")
def compose(component):
    return yaml.safe_load((component / "config/compose.yaml").read_text(encoding="utf-8"))


def test_every_image_is_pinned_by_digest(compose):
    for name, service in compose["services"].items():
        assert re.search(r"@sha256:[0-9a-f]{64}$", service["image"]), name


def test_every_service_is_bounded_and_drops_capabilities(compose):
    for name, service in compose["services"].items():
        assert service.get("mem_limit"), f"{name} has no memory limit"
        assert service.get("cap_drop") == ["ALL"], f"{name} keeps capabilities"
        assert service.get("network_mode") != "host", name
        assert not service.get("privileged"), name


def test_only_the_live_apps_publish_ports(compose):
    published = {name for name, s in compose["services"].items() if s.get("ports")}
    assert published == {"radarr", "prowlarr"}


def test_secrets_come_only_from_operator_env_files(compose):
    for name, service in compose["services"].items():
        for env_file in service.get("env_file", []):
            assert env_file.startswith("/etc/media/secrets/"), name
        for key in service.get("environment") or {}:
            assert not re.search(r"(?i)api_?key|password|token", key), f"{name} inlines {key}"


def test_recyclarr_is_on_demand_only(compose):
    assert compose["services"]["recyclarr"]["profiles"] == ["recyclarr"]


def test_arr_root_never_owns_what_recyclarr_owns(component):
    text = (component / "terraform/arr/main.tf").read_text(encoding="utf-8")
    for resource in ("quality_profile", "custom_format", "quality_definition", "indexer"):
        assert not re.search(rf'resource "(radarr|prowlarr)_[a-z_]*{resource}', text), resource


def test_arr_root_providers_and_lock_are_pinned(component):
    versions = (component / "terraform/arr/versions.tf").read_text(encoding="utf-8")
    assert 'version = "2.5.0"' in versions and 'version = "3.2.1"' in versions
    lock = (component / "terraform/arr/.terraform.lock.hcl").read_text(encoding="utf-8")
    assert "devopsarr/radarr" in lock and "devopsarr/prowlarr" in lock


@pytest.mark.parametrize("role", sorted(ROLE_GATES))
def test_role_gates_default_closed_and_are_asserted_first(component, role):
    flag, confirmation, prefix = ROLE_GATES[role]
    defaults = yaml.safe_load((component / f"ansible/roles/{role}/defaults/main.yml").read_text())
    assert defaults[flag] is False
    assert defaults[confirmation] == ""
    first = yaml.safe_load((component / f"ansible/roles/{role}/tasks/main.yml").read_text())[0]
    that = first["ansible.builtin.assert"]["that"]
    assert f"{flag} | bool" in that
    assert f"{confirmation} == ('{prefix}' ~ inventory_hostname)" in that


def test_recyclarr_and_plex_backup_have_their_own_gates(component):
    defaults = yaml.safe_load((component / "ansible/roles/arr_stack/defaults/main.yml").read_text())
    assert defaults["arr_stack_allow_recyclarr_sync"] is False
    recyclarr = (component / "ansible/roles/arr_stack/tasks/recyclarr.yml").read_text()
    assert "'--preview'" in recyclarr
    plex = yaml.safe_load((component / "ansible/roles/plex/defaults/main.yml").read_text())
    assert plex["plex_allow_backup_task"] is False and plex["plex_backup_confirmation"] == ""


def test_plex_role_never_touches_the_windows_firewall_or_sleep(component):
    text = (component / "ansible/roles/plex/tasks/main.yml").read_text(encoding="utf-8")
    for banned in ("NetFirewall", "netsh", "powercfg", "Set-ItemProperty"):
        assert banned not in text


def test_backups_never_delete(component):
    for path in (
        "scripts/arr_backup.py",
        "scripts/plex-backup.ps1",
        "ansible/roles/media_backup/tasks/main.yml",
    ):
        lines = (component / path).read_text(encoding="utf-8").splitlines()
        text = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
        for banned in ("unlink(", "rmtree", "os.remove", "Remove-Item", "/MIR", "/PURGE", "state: absent"):
            assert banned not in text, f"{path}: {banned}"


def test_every_playbook_is_serial_and_fatal(component):
    for path in sorted((component / "ansible/playbooks").glob("*.yml")):
        for play in yaml.safe_load(path.read_text(encoding="utf-8")):
            assert play["serial"] == 1 and play["any_errors_fatal"] is True, path.name


def test_no_aggregate_target(component):
    makefile = (component / "Makefile").read_text(encoding="utf-8")
    assert not re.search(r"^[\w-]*(-all|everything)\s*:", makefile, re.M)
    assert "apply:" not in makefile and "destroy:" not in makefile
