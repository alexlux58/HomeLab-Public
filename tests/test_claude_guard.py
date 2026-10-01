"""The Claude Code PreToolUse guard blocks every command and read that
AGENTS.md forbids, and does not block ordinary offline work."""

import json
import shutil
import subprocess

import pytest

BLOCKED_COMMANDS = [
    "terraform apply",
    "terraform -chdir=platform/proxmox/terraform/homelab-guests apply -auto-approve",
    "terraform destroy",
    "terraform import proxmox_virtual_environment_vm.x pve1/300",
    "tofu apply",
    "tofu destroy",
    "tofu import a b",
    "terraform state rm module.x",
    "bao operator init",
    "bao operator unseal",
    "bao operator rekey",
    "pvecm add 192.168.0.11",
    "pvecm expected 1",
    "qm destroy 300",
    "pct destroy 101",
    "rm -rf build",
    "rm -fr build",
    "rm -r -f build",
    "rm --recursive --force build",
    "Remove-Item -Recurse -Force build",
    "git push --force origin main",
    "git push origin main --force-with-lease",
    "git push origin --delete old",
    "git push --mirror origin",
    "git push origin +main:main",
    "git push origin :old",
    "git push upstream main",
    "git push https://github.com/other/repo.git main",
    "git -C public push --force origin main",
    "git -c remote.origin.pushurl=https://example.com push origin main",
    "git push origin main --no-verify",
    'ssh pve1 "pvecm add 192.168.0.11"',
    "ssh -p 22 pve1 qm destroy 300",
    "sudo pvecm status",
    "bash -lc 'qm destroy 300'",
    "echo hi && rm -rf /tmp/x",
    "find . -name x -exec rm -rf {} +",
    "xargs rm -rf",
    "cat .env",
    "cat services/media/.env",
    "cat platform/proxmox/terraform/homelab-guests/terraform.tfstate",
    "cp prod.tfvars /tmp/",
    "cat ~/.ssh/proxmox_cluster_ed25519",
    "cat ~/.ssh/config",
    "cat ~/.ssh/proxmox_cluster_ed25519.pub",
    "ssh -i key -o BatchMode=yes pve1 'pvecm status'",
    "xargs -n 1 rm -rf",
    "head platform/proxmox/artifacts/discovery.json",
    "grep -r token platform/proxmox/host-configs/",
    "Get-Content C:/ProgramData/Plex/Preferences.xml",
    "cat radarr/config.xml",
    "cat .runtime/radarr/config/radarr.db",
    "cat /etc/homelab/secret-store/speedtest-tracker.env",
    "python3 read.py < .env",
    'echo "unbalanced',
    "bash <<'EOF'\npvecm add 192.168.0.11\nEOF",
    "ssh pve1 <<EOF\nqm destroy 300\nEOF",
    "cat <<'EOF' | bash\nrm -rf /srv\nEOF",
    "git commit -F - <<'EOF'\nmessage\nEOF\nterraform apply",
]

ALLOWED_COMMANDS = [
    "git push origin main",
    "git push -u origin main snapshot/pre-restructure-20260929",
    "git -C public push origin main",
    "git grep pvecm",
    "git grep 'pvecm expected'",
    "git status",
    "git log --oneline -5",
    "terraform fmt -check -recursive",
    "terraform -chdir=x validate",
    "make -C platform/proxmox check",
    "make COMPONENT=tests check",
    "ls artifacts/",
    "find platform -name '*.tfstate'",
    "rm build/output.txt",
    "rm -r build",
    "cat README.md",
    "cat .env.example",
    "ansible-playbook --syntax-check ansible/playbooks/00-preflight.yml",
    "grep -rn secret-hierarchy docs/",
    "git ls-files | grep -E '(artifacts|host-configs)/'",
    "rg -n 'artifacts/' docs",
    "git commit -q -F - <<'EOF'\nfix: repair NetBox's roles\n\nNever run pvecm expected or rm -rf.\nEOF",
    "cat > notes.md <<EOF\nit's data, not a command\nEOF",
    "cat security/secrets-openbao/AGENTS.md",
]


def _event(tool, **tool_input):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}


@pytest.mark.parametrize("command", BLOCKED_COMMANDS)
def test_forbidden_commands_are_blocked(guard, command):
    with pytest.raises(guard.Blocked):
        guard.decide(_event("Bash", command=command))


@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
def test_offline_work_is_allowed(guard, command):
    guard.decide(_event("Bash", command=command))


@pytest.mark.parametrize(
    ("tool", "path"),
    [
        ("Read", "/work/platform/proxmox/terraform/homelab-guests/terraform.tfstate"),
        ("Read", "C:\\Users\\labuser\\Documents\\Home-Lab\\.env"),
        ("Read", "/home/me/.ssh/id_ed25519"),
        ("Read", "/work/platform/proxmox/artifacts/discovery.json"),
        ("Read", "/work/platform/proxmox/host-configs/pve1/297.conf"),
        ("Read", "/work/.runtime/radarr/config/config.xml"),
        ("Edit", "/work/prod.tfvars"),
        ("Write", "/work/services/media/.env"),
        ("Grep", "/work/platform/proxmox/artifacts"),
    ],
)
def test_protected_paths_are_blocked_for_file_tools(guard, tool, path):
    key = "path" if tool == "Grep" else "file_path"
    with pytest.raises(guard.Blocked):
        guard.decide(_event(tool, **{key: path}))


@pytest.mark.parametrize(
    ("tool", "path"),
    [
        ("Read", "/work/AGENTS.md"),
        ("Read", "/work/inventory/hosts.yml"),
        ("Read", "/work/.env.example"),
        ("Glob", "/work/platform/proxmox/artifacts"),
        ("Edit", "/work/MEMORY.md"),
    ],
)
def test_ordinary_paths_are_allowed(guard, tool, path):
    key = "path" if tool == "Glob" else "file_path"
    guard.decide(_event(tool, **{key: path}))


def _run_hook(root, event):
    return subprocess.run(
        ["bash", str(root / ".claude/hooks/guard.sh")],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to run the hook")
def test_hook_wrapper_exit_codes(root):
    blocked = _run_hook(root, _event("Bash", command="pvecm add 192.168.0.11"))
    assert blocked.returncode == 2
    assert "Blocked by the Home Lab guard" in blocked.stderr
    allowed = _run_hook(root, _event("Bash", command="git status"))
    assert allowed.returncode == 0, allowed.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to run the hook")
def test_hook_fails_closed_on_garbage_input(root):
    result = subprocess.run(
        ["bash", str(root / ".claude/hooks/guard.sh")],
        input="not json",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


def test_settings_register_the_hook_and_deny_rules(root):
    settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
    (entry,) = settings["hooks"]["PreToolUse"]
    matched = set(entry["matcher"].split("|"))
    assert {"Bash", "PowerShell", "Read", "Grep", "Edit", "Write"} <= matched
    assert entry["hooks"][0]["command"].endswith('.claude/hooks/guard.sh"')
    deny = set(settings["permissions"]["deny"])
    for rule in (
        "Bash(terraform apply:*)",
        "Bash(terraform destroy:*)",
        "Bash(terraform import:*)",
        "Bash(tofu apply:*)",
        "Bash(bao operator:*)",
        "Bash(pvecm:*)",
        "Bash(qm destroy:*)",
        "Bash(rm -rf:*)",
        "Read(./**/*.tfstate)",
        "Read(./**/.env)",
        "Read(~/.ssh/**)",
        "Read(./**/artifacts/**)",
        "Read(./**/host-configs/**)",
    ):
        assert rule in deny, rule
    assert "allow" not in settings.get("permissions", {}), "no blanket allow rules"
