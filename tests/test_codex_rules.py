"""The Codex execpolicy rules forbid what AGENTS.md forbids.

The .rules file is Starlark, but it is restricted to plain prefix_rule() calls,
which are also valid Python. This test evaluates it with a collector and
reimplements Codex's prefix matching (exact tokens, nested lists as
alternatives, strictest decision wins). When the codex CLI is installed, the
same commands are also checked with `codex execpolicy check`.
"""

import json
import shlex
import shutil
import subprocess
import tomllib

import pytest

STRICTNESS = {"allow": 0, "prompt": 1, "forbidden": 2}


@pytest.fixture(scope="module")
def rules(root):
    collected = []

    def prefix_rule(pattern, decision="allow", justification="", match=(), not_match=()):
        collected.append(
            {
                "pattern": pattern,
                "decision": decision,
                "justification": justification,
                "match": list(match),
                "not_match": list(not_match),
            }
        )

    source = (root / ".codex/rules/homelab.rules").read_text(encoding="utf-8")
    exec(compile(source, "homelab.rules", "exec"), {"__builtins__": {}, "prefix_rule": prefix_rule})
    assert collected
    return collected


def _matches(pattern, tokens):
    if len(tokens) < len(pattern):
        return False
    for want, got in zip(pattern, tokens, strict=False):
        options = want if isinstance(want, list) else [want]
        if got not in options:
            return False
    return True


def _decision(rules, command):
    tokens = shlex.split(command)
    hits = [r["decision"] for r in rules if _matches(r["pattern"], tokens)]
    return max(hits, key=STRICTNESS.__getitem__) if hits else "allow"


def test_every_rule_is_well_formed_and_self_consistent(rules):
    for rule in rules:
        assert rule["decision"] in STRICTNESS
        assert rule["justification"], rule["pattern"]
        for example in rule["match"]:
            assert _matches(rule["pattern"], shlex.split(example)), (rule["pattern"], example)
        for example in rule["not_match"]:
            assert not _matches(rule["pattern"], shlex.split(example)), (rule["pattern"], example)


@pytest.mark.parametrize(
    "command",
    [
        "terraform apply",
        "terraform destroy",
        "terraform import a b",
        "tofu apply",
        "tofu destroy",
        "tofu import a b",
        "bao operator init",
        "bao operator unseal",
        "pvecm add 192.168.0.11",
        "qm destroy 300",
        "pct destroy 101",
        "rm -rf build",
        "rm -fr build",
        "git push --force origin main",
        "git push origin --force-with-lease main",
        "git push origin --delete old",
        "git push --mirror origin",
        "git push origin +main",
        "git push origin :main",
        "git push upstream main",
        "git push https://github.com/other/repo.git main",
    ],
)
def test_forbidden_commands(rules, command):
    assert _decision(rules, command) == "forbidden"


@pytest.mark.parametrize(
    "command",
    [
        "terraform -chdir=platform/proxmox/terraform/homelab-guests apply",
        "tofu plan",
        "ssh pve1 uptime",
        "ansible-playbook -i inventory/hosts.yml ansible/playbooks/40-deploy.yml",
    ],
)
def test_commands_that_need_the_operator_prompt(rules, command):
    assert STRICTNESS[_decision(rules, command)] >= STRICTNESS["prompt"]


@pytest.mark.parametrize(
    "command", ["make check", "git status", "pytest -q", "rm file.txt", "git push origin main"]
)
def test_offline_work_is_not_restricted(rules, command):
    assert _decision(rules, command) == "allow"


def test_project_config_keeps_the_sandbox(root):
    config = tomllib.loads((root / ".codex/config.toml").read_text(encoding="utf-8"))
    assert config["approval_policy"] == "on-request"
    assert config["sandbox_mode"] == "workspace-write"
    assert config["sandbox_workspace_write"]["network_access"] is False


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
@pytest.mark.parametrize("command", ["terraform apply", "pvecm add x", "rm -rf build"])
def test_codex_cli_agrees(root, command):
    result = subprocess.run(
        [
            "codex",
            "execpolicy",
            "check",
            "--rules",
            str(root / ".codex/rules/homelab.rules"),
            "--",
            *shlex.split(command),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "forbidden" in json.dumps(json.loads(result.stdout))
