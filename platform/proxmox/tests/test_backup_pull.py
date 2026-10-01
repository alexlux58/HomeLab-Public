"""Read-only archive protocol and the one-node approval contract."""

import hashlib
import importlib.util
import io
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "vzdump-qemu-320-2026_09_30-05_05_00.vma.zst"


@pytest.fixture
def server():
    spec = importlib.util.spec_from_file_location(
        "backup_server", ROOT / "scripts/backup_pull_server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_list_and_get_leave_archives_unchanged(server, tmp_path):
    data = bytes(range(256)) * 4096
    path = tmp_path / ARCHIVE
    path.write_bytes(data)
    before = path.stat()
    listing, payload = io.StringIO(), io.BytesIO()
    server.serve("list", tmp_path, listing)
    server.serve(f"get {ARCHIVE}", tmp_path, binary_output=payload)
    assert listing.getvalue() == f"{ARCHIVE}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}\n"
    assert payload.getvalue() == data
    assert server.signature(before) == server.signature(path.stat())
    assert path.read_bytes() == data


@pytest.mark.parametrize(
    "command",
    [
        "",
        "sh",
        "list extra",
        "get ../archive",
        "get /etc/passwd",
        "get file;touch marker",
        f"get {ARCHIVE}\n",
        f"get {ARCHIVE} extra",
        "delete anything",
        "list; rm data",
    ],
)
def test_rejects_every_other_command(server, tmp_path, command):
    with pytest.raises(ValueError):
        server.serve(command, tmp_path)
    assert not list(tmp_path.iterdir())


def test_symlinks_cannot_escape_dump(server, tmp_path):
    outside = tmp_path / "outside"
    outside.write_bytes(b"not an archive")
    (tmp_path / ARCHIVE).symlink_to(outside)
    with pytest.raises(OSError):
        server.serve(f"get {ARCHIVE}", tmp_path, binary_output=io.BytesIO())
    with pytest.raises(OSError):
        server.serve("list", tmp_path, io.StringIO())


def test_non_regular_file_is_rejected(server, tmp_path):
    (tmp_path / ARCHIVE).mkdir()
    with pytest.raises(ValueError):
        server.serve(f"get {ARCHIVE}", tmp_path, binary_output=io.BytesIO())


def test_only_finalized_archives_are_listed(server, tmp_path):
    for name in ("config.xml", ARCHIVE + ".tmp", "vzdump-qemu-320-../../passwd", "notes.txt"):
        if "/" not in name:
            (tmp_path / name).write_bytes(b"ignored")
    out = io.StringIO()
    server.serve("list", tmp_path, out)
    assert out.getvalue() == ""


def test_gate_and_key_restrictions():
    role = ROOT / "ansible/roles/backup_pull"
    defaults = yaml.safe_load((role / "defaults/main.yml").read_text())
    assert defaults["allow_backup_pull"] is False
    assert defaults["backup_pull_confirmation"] == ""
    assert defaults["backup_pull_public_key"] == ""
    tasks = yaml.safe_load((role / "tasks/main.yml").read_text())
    gate = tasks[0]["ansible.builtin.assert"]["that"]
    assert "allow_backup_pull | bool" in gate
    assert (
        "backup_pull_confirmation == 'INSTALL BACKUP PULL ON ' "
        "~ inventory_hostname ~ ' ' ~ ansible_host" in gate
    )
    assert "ansible_play_hosts_all | length == 1" in gate
    key = tasks[-1]["ansible.posix.authorized_key"]
    assert key["exclusive"] is False and key["state"] == "present"
    for option in (
        'from="',
        'command="',
        "no-port-forwarding",
        "no-agent-forwarding",
        "no-pty",
        "no-X11-forwarding",
    ):
        assert option in key["key_options"]
    assert "least loaded" in tasks[2]["name"]


def test_stage_is_serial_and_one_target():
    (play,) = yaml.safe_load(
        (ROOT / "ansible/playbooks/host/20-configure-backup-pull.yml").read_text()
    )
    assert play["serial"] == 1 and play["any_errors_fatal"] is True
    assert play["gather_facts"] is False
    makefile = (ROOT / "Makefile").read_text()
    assert "configure-backup-pull:" in makefile
    assert "ansible/playbooks/host/20-configure-backup-pull.yml" in makefile


def test_server_detects_archive_changed_during_get(server, tmp_path):
    path = tmp_path / ARCHIVE
    path.write_bytes(b"archive")

    class ChangingOutput(io.BytesIO):
        def write(self, data):
            path.write_bytes(b"changed archive")
            return super().write(data)

    with pytest.raises(ValueError, match="changed while reading"):
        server.serve(f"get {ARCHIVE}", tmp_path, binary_output=ChangingOutput())


def test_task_schedule_and_windows_boundaries():
    xml = ET.parse(ROOT / "scripts/backup-pull-task.xml")
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    for name, value in {
        "StartWhenAvailable": "true",
        "WakeToRun": "false",
        "MultipleInstancesPolicy": "IgnoreNew",
    }.items():
        assert xml.find(f".//t:{name}", ns).text == value
    assert xml.find(".//t:DaysInterval", ns).text == "1"
    assert xml.find(".//t:LogonType", ns).text == "InteractiveToken"
    assert xml.find(".//t:RunLevel", ns).text == "LeastPrivilege"
    source = (ROOT / "scripts/backup-pull.ps1").read_text()
    installer = (ROOT / "scripts/install-backup-pull-task.ps1").read_text()
    for banned in ("Remove-Item", "powercfg", "Set-NetFirewall", "Enable-WindowsOptionalFeature"):
        assert banned not in source + installer
    assert "StrictHostKeyChecking=yes" in source
    assert "100GB" in source and "[IO.File]::Move($copy.Partial, $copy.Target)" in source
    assert installer.index("Host fingerprint does not match") < installer.index("WriteAllText")


def test_node_export_matches_inventory():
    import json
    import sys

    lab = yaml.safe_load((ROOT.parents[1] / "inventory/lab.yml").read_text())
    installer = (ROOT / "scripts/install-backup-pull-task.ps1").read_text()
    assert "$config.fingerprint -cne $nodeFingerprints[$config.node]" in installer
    for node in lab["nodes"].values():
        assert f"{node['inventory_name']}='{node['address']}'" in installer
        assert f"{node['inventory_name']}='{node['host_fingerprint']}'" in installer
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/backup_pull_config.py"),
                "--node",
                node["inventory_name"],
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert json.loads(result.stdout) == {
            "node": node["inventory_name"],
            "address": node["address"],
            "fingerprint": node["host_fingerprint"],
        }


def test_powershell_client_offline(tmp_path):
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("Optional native PowerShell harness; run on Windows or the review container")
    subprocess.run(
        [
            executable,
            "-NoProfile",
            "-File",
            str(ROOT / "tests/backup_pull_client.ps1"),
            "-Scratch",
            str(tmp_path / "client"),
        ],
        check=True,
    )


def test_native_process_transfer_preserves_binary_bytes(tmp_path):
    import sys

    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("Native PowerShell transfer check requires pwsh")
    fake = tmp_path / "fake-ssh"
    fake.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "assert 'StrictHostKeyChecking=yes' in sys.argv\n"
        f"assert sys.argv[-1] == 'get {ARCHIVE}'\n"
        "sys.stdout.buffer.write(bytes(range(256)) * 4096)\n"
    )
    fake.chmod(0o755)
    pin, output = tmp_path / "test-public-pin", tmp_path / "archive"
    pin.write_text("public test placeholder only")

    # Test fixture paths, escaped as literal PowerShell strings; no network access.
    def literal(path):
        return "'" + str(path).replace("'", "''") + "'"

    harness = tmp_path / "transfer.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f". {literal(ROOT / 'scripts/backup-pull.ps1')} -KnownHosts {literal(pin)} "
        f"-SshExecutable {literal(fake)} -Identity 'test-unused'\n"
        f"Invoke-BackupSsh 'get {ARCHIVE}' {literal(output)}\n"
    )
    subprocess.run([executable, "-NoProfile", "-File", str(harness)], check=True)
    assert output.read_bytes() == bytes(range(256)) * 4096
