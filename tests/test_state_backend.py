"""D1: mounted local ciphertext state, strict templates and operator migration."""

import json

import pytest

ROOTS = {
    "security/secrets-openbao/terraform": ("openbao", "backend.tofu.example"),
    "services/netbox/terraform/proxmox-guest": ("netbox", "backend.tofu.example"),
    "platform/proxmox/terraform/homelab-guests": ("homelab-guests", "backend.tofu.example"),
    "platform/proxmox/terraform/rebuild-guests": ("rebuild-guests", "state.tofu"),
    "services/media/terraform/arr": ("media-arr", "state.tofu"),
}


@pytest.mark.parametrize("directory,spec", ROOTS.items())
def test_local_encrypted_root(root, directory, spec):
    state_id, filename = spec
    text = (root / directory / filename).read_text(encoding="utf-8")
    assert 'backend "local"' in text
    assert 'backend "s3"' not in text
    assert f"/homelab-state/{state_id}/terraform.tfstate" in text
    assert f"/homelab-state/{state_id}/workspaces" in text
    assert 'key_provider "pbkdf2" "state"' in text
    assert 'method "aes_gcm" "state"' in text
    assert text.count("enforced = true") == 2
    assert 'method "unencrypted"' not in text
    assert "fallback" not in text
    assert "sensitive   = true" in text


def test_mount_and_operator_only_migration(root):
    doc = json.loads((root / ".devcontainer/devcontainer.json").read_text())
    assert "source=D:/homelab-state,target=/homelab-state,type=bind" in doc["mounts"]
    text = (root / "docs/runbooks/state-migration.md").read_text()
    assert "Operator-only" in text and "no changes" in text and "or stop" in text
    assert 'method "unencrypted" "migration"' in text
    assert "state `enforced = true`" in text
    assert "Phase 1 source archive" in text
