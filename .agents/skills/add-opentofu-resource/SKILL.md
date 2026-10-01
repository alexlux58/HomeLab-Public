---
name: add-opentofu-resource
description: Use when adding or adopting a Proxmox guest or other resource in OpenTofu/Terraform (a new VMID, MAC, disk or NIC). Covers the VMID/MAC collision check, import-first versus create-mode roots, destroy protection and tests. Never runs plan, apply or import.
---

# Add an OpenTofu/Terraform resource

Agents write and validate IaC offline. Plan, apply, import and destroy are the
operator's. Terraform state is **not** in the monorepo yet (`MEMORY.md`), so a
plan from a monorepo root would propose re-creating existing guests.

## Decide import vs create

- The guest exists: import-first root (`platform/proxmox/terraform/homelab-guests`
  pattern) with an `import {}` block, `prevent_destroy = true`,
  `purge_on_destroy = false`, `delete_unreferenced_disks_on_destroy = false`,
  and disks, EFI and cloud-init left unmanaged unless the operator approves.
- The guest is new: its own create-mode root (NetBox pattern,
  `services/netbox/terraform/proxmox-guest`) so a drift plan for adopted guests
  can never propose creating it. `on_boot = false`, `started` behind a variable
  defaulting to `false`, `protection = true`.

A new guest is first an entry in `inventory/lab.yml` (ADR-0005): the
rebuild-only root `platform/proxmox/terraform/rebuild-guests` reads identities
from there, and `tests/test_inventory_contract.py` fails if a live root or an
Ansible inventory disagrees with it. Keep `tests/*.tftest.hcl` mock-provider
tests next to every root, and a multi-platform `.terraform.lock.hcl`.

## Steps

1. Check VMID and MAC uniqueness against `inventory/lab.yml`, the inventories, and the
   reserved lists in `platform/proxmox/tests/test_repo_safety.py`
   (`test_netbox_vmid_and_mac_do_not_collide_with_reserved_identities`).
   Retired MACs stay reserved. VMID 297 is never reused without approval.
2. Check capacity per node in `MEMORY.md` before choosing placement.
3. Pin the provider version exactly (currently `0.107.0`).
4. Add tests mirroring the NetBox ones: destroy protection, separate root,
   identity collisions, no apply/destroy Make target.
5. Run `terraform fmt -check` and, only if the provider is cached,
   `init -backend=false` plus `validate`.

## Hand-off

Give the operator the plan command and what to look for in it. Use
`run-gated-stage` for approval values. Never supply credentials.
