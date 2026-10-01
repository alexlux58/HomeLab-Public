"""L0 answer files render from lab.yml, refuse missing operator inputs, and
never let a secret reach stdout or the repository."""

import copy

import pytest
import tomllib
import yaml
from build_answer_files import REDACTED, NotReady, build, render, secrets_from_env

pytestmark = pytest.mark.repo


@pytest.fixture
def lab(repo_root):
    with (repo_root.parents[1] / "inventory/lab.yml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    ready = copy.deepcopy(data)
    for name, node in ready["nodes"].items():
        node["install"].update(
            fqdn=f"{name}.example.invalid",
            disk_filter={"ID_SERIAL": "TEST_DISK*"},
            interface_filter={"ID_NET_NAME_MAC": "enx*"},
        )
    return data, ready


@pytest.fixture
def env(tmp_path):
    keys = tmp_path / "keys.pub"
    keys.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKeyOnly operator\n", encoding="utf-8")
    return {
        "PVE_ROOT_PASSWORD_HASH": "$6$testsalt$notarealhash",
        "PVE_ROOT_SSH_KEYS_FILE": str(keys),
        "PVE_MAILTO": "ops@example.invalid",
    }


def test_unrecorded_inputs_make_the_build_refuse(lab):
    committed, _ = lab
    with pytest.raises(NotReady, match=r"install\.fqdn"):
        build(committed, ["pve1"], env={}, write=False)


def test_rendered_file_is_valid_pve9_kebab_case_toml(lab, env):
    _, ready = lab
    node = ready["nodes"]["pve3"]
    text = render("pve3", node, ready, secrets_from_env(env))
    doc = tomllib.loads(text)
    assert set(doc) == {"global", "network", "disk-setup"}
    for key in (
        "keyboard",
        "country",
        "fqdn",
        "mailto",
        "timezone",
        "root-password-hashed",
        "root-ssh-keys",
    ):
        assert key in doc["global"]
    assert "root-password" not in doc["global"], "only the hash is ever used"
    assert doc["network"]["source"] == "from-answer"
    assert doc["network"]["cidr"] == "192.168.0.13/24"
    assert doc["network"]["gateway"] == "192.168.0.1"
    assert doc["disk-setup"]["filesystem"] == "ext4"
    assert doc["disk-setup"]["filter"] == {"ID_SERIAL": "TEST_DISK*"}


def test_dry_run_redacts_every_secret(lab, env):
    _, ready = lab
    rendered = build(ready, sorted(ready["nodes"]), env=env, write=False)
    for text in rendered.values():
        assert "$6$" not in text and "ops@example.invalid" not in text and "TestKeyOnly" not in text
        assert REDACTED in text


def test_plain_passwords_and_private_keys_are_rejected(lab, env, tmp_path):
    bad = dict(env, PVE_ROOT_PASSWORD_HASH="hunter2")
    with pytest.raises(NotReady, match="hash"):
        secrets_from_env(bad)
    private = tmp_path / "id"
    private.write_text("-----BEGIN OPENSSH " + "PRIVATE KEY-----\n", encoding="utf-8")
    with pytest.raises(NotReady, match="public keys only"):
        secrets_from_env(dict(env, PVE_ROOT_SSH_KEYS_FILE=str(private)))


def test_output_directory_is_git_ignored(repo_root):
    gitignore = (repo_root.parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert "**/artifacts/" in gitignore
