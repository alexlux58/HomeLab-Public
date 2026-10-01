# ADR-0005: `inventory/lab.yml` is the single source of truth

Status: accepted, Phase 3 (2026-09-29). Supersedes ADR-0001.

## Decision

`inventory/lab.yml` holds every identity the lab depends on: nodes, guests
(VMID, name, node, address, MAC, CPU, RAM, disk, storage, protection,
`onboot`), NAS, workstation, network, DNS, backup jobs and SSH access.

- **OpenTofu reads it** with `yamldecode(file(...))`. The rebuild-only root
  (`platform/proxmox/terraform/rebuild-guests`) and the *arr root take every
  identity from it.
- **Ansible inventories are validated against it, not regenerated.** The five
  existing inventories stay as they are (live stages depend on their group
  names), and `tools/repo-checks/inventory_contract.py` compares every host,
  address, user, key and fingerprint with `lab.yml`. A test fails on drift.
- **Live import-first and create-mode roots keep their literal values**, and a
  test compares them with `lab.yml` so they cannot silently diverge.

## Why validate instead of generate

Regenerating the live inventories would change files that gated stages read,
for no functional gain, and a generator bug could point a stage at the wrong
host. Validation gives the same single-source guarantee with no live effect.
Generation can replace validation later, per inventory, as its own reviewed
change.
