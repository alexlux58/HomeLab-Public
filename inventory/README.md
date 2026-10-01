# Inventory boundary

`lab.yml` is the single source of truth (ADR-0005). OpenTofu reads it with
`yamldecode`; the Ansible inventories below are validated against it by
`tools/repo-checks/inventory_contract.py`, and `tests/test_inventory_contract.py`
fails on any drift.

| File | Consumers |
| --- | --- |
| `lab.yml` | rebuild root, *arr root, answer-file builder, L1 host config, contract check |
| `hosts.yml`, `group_vars/all.yml` | Proxmox migration stages, NAS preflight, L1 host config |
| `homelab-services.yml` | VM 300 stages |
| `netbox.yml` | VM 330 stages |
| `observability/` | VM 310 stages and agents |
| `secrets-openbao/` | VMs 320–322 stages |
| `media.yml` | media-vm stages (services/media) |

To change a live identity: edit `lab.yml`, then the consumer, in one commit,
and run `make COMPONENT=tests check`. Do not point a live stage at a changed
inventory until its diff has been reviewed and the stage's own gate has passed.
