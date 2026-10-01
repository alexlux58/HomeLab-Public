"""Ladder rung L1 (pve_host_config) is gated, derives everything from lab.yml,
only ever adds backup jobs, and never prunes."""

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.repo

ROLE = Path(__file__).resolve().parents[1] / "ansible" / "roles" / "pve_host_config"


def _tasks():
    """Task text without YAML comments, which may name what they forbid."""
    lines = []
    for path in sorted((ROLE / "tasks").glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("#"):
                lines.append(line)
    return "\n".join(lines)


def test_gate_defaults_are_closed():
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text(encoding="utf-8"))
    assert defaults["pve_host_config_allow"] is False
    assert defaults["pve_host_config_confirmation"] == ""
    assert defaults["pve_host_config_backup_prune"] == "keep-all=1"


def test_gate_is_the_first_real_task_and_names_every_node():
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
    assert "set_fact" in str(tasks[0])
    gate = tasks[1]
    assert gate["ansible.builtin.assert"]["that"] == [
        "pve_host_config_allow | bool",
        "pve_host_config_confirmation == pve_host_config_expected_confirmation",
    ]
    assert "L1 CONFIGURE {{ ansible_play_hosts_all | sort | join(' ') }}" in str(tasks[0])


def test_backup_jobs_are_only_created_never_changed_or_deleted():
    text = _tasks()
    assert "pvesh\n      - create\n      - /cluster/backup" in text
    banned = ("delete", "set\n      - /cluster/backup", "--remove", "keep-last", "keep-daily")
    for word in banned:
        assert word not in text, word
    create = (ROLE / "tasks/backup_jobs.yml").read_text(encoding="utf-8")
    assert "when: (item.vmid | string) not in pve_host_config_jobs_by_vmid" in create


def test_quorum_is_required_and_never_forced():
    text = _tasks()
    assert "Quorate:\\\\s+Yes" in text
    assert not re.search(r"^\s*-\s*expected\s*$", text, re.M)


def test_no_cloud_init_option_is_touched():
    """qm set on cloud-init options regenerates host keys on a stopped guest."""
    text = _tasks()
    options = ("--nameserver", "--searchdomain", "--ipconfig", "--ciuser", "--sshkeys")
    for option in (*options, "--cipassword"):
        assert option not in text


def test_no_backreference_in_the_role():
    assert "'\\1'" not in _tasks()


def test_playbook_is_serial_and_only_runs_the_role(repo_root):
    path = repo_root / "ansible/playbooks/host/10-configure-hosts.yml"
    (play,) = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert play["serial"] == 1
    assert play["any_errors_fatal"] is True
    assert play["roles"] == [{"role": "pve_host_config"}]
