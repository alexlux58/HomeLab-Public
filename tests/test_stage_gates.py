"""Every live stage added to the ladder in Phase 3 is gated: a false-by-default
flag and an empty confirmation, asserted before any role runs."""

import pytest
import yaml

GATES = {
    "observability/ansible/playbooks/20-bootstrap.yml": (
        "observability_allow_bootstrap",
        "observability_bootstrap_confirmation",
        "'BOOTSTRAP ' ~ inventory_hostname",
    ),
    "observability/ansible/playbooks/40-deploy.yml": (
        "observability_allow_deploy",
        "observability_deploy_confirmation",
        "'DEPLOY OBSERVABILITY STACK ON ' ~ inventory_hostname",
    ),
    "services/homelab-services/ansible/playbooks/30-configure-guest.yml": (
        "homelab_allow_guest_config",
        "homelab_guest_config_confirmation",
        "'CONFIGURE GUEST ' ~ inventory_hostname",
    ),
    "services/homelab-services/ansible/playbooks/40-deploy-service.yml": (
        "homelab_allow_service_deploy",
        "homelab_service_deploy_confirmation",
        "'DEPLOY ' ~ homelab_services_service_name ~ ' ON ' ~ inventory_hostname",
    ),
    "services/homelab-services/ansible/playbooks/50-configure-backups.yml": (
        "homelab_allow_backup_config",
        "homelab_backup_config_confirmation",
        "'CONFIGURE BACKUPS ON ' ~ inventory_hostname",
    ),
    "services/netbox/ansible/playbooks/31-configure-guest.yml": (
        "netbox_allow_guest_config",
        "netbox_guest_config_confirmation",
        "'CONFIGURE GUEST ' ~ inventory_hostname",
    ),
    "services/netbox/ansible/playbooks/40-deploy.yml": (
        "netbox_allow_deploy",
        "netbox_deploy_confirmation",
        "'DEPLOY NETBOX ON ' ~ inventory_hostname",
    ),
    "services/netbox/ansible/playbooks/50-configure-backups.yml": (
        "netbox_allow_backup_config",
        "netbox_backup_config_confirmation",
        "'CONFIGURE BACKUPS ON ' ~ inventory_hostname",
    ),
}


@pytest.mark.parametrize("playbook", sorted(GATES))
def test_stage_is_gated_before_any_role(root, playbook):
    flag, confirmation, expected = GATES[playbook]
    (play,) = yaml.safe_load((root / playbook).read_text(encoding="utf-8"))
    assert play["vars"][flag] is False
    assert play["vars"][confirmation] == ""
    first = play["pre_tasks"][0]["ansible.builtin.assert"]["that"]
    assert first == [f"{flag} | bool", f"{confirmation} == ({expected})"]


@pytest.mark.parametrize("playbook", sorted(GATES))
def test_every_target_running_the_stage_passes_extra_json(root, playbook):
    name = playbook.rsplit("/", 1)[1]
    component = playbook.split("/ansible/")[0]
    makefiles = [root / component / "Makefile", root / "platform/proxmox/Makefile"]
    for makefile in makefiles:
        lines = makefile.read_text(encoding="utf-8").split("\n")
        for index, line in enumerate(lines):
            if (
                name in line
                and line.startswith("\t")
                and "--syntax-check" not in line
                and "for playbook" not in line
            ):
                recipe = line
                while recipe.rstrip().endswith("\\"):
                    index += 1
                    recipe += lines[index]
                assert "$(EXTRA_JSON_ARG)" in recipe, f"{makefile.name}: {line.strip()}"
