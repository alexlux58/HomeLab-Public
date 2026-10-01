# ADR-0007: a separate create-mode root, used only for rebuilds

Status: accepted, Phase 3 (2026-09-29).

## Decision

`platform/proxmox/terraform/rebuild-guests` can create VMs 300, 310, 320–322
and 330 from `inventory/lab.yml` after a total loss. It is separate from every
live root, which stay unchanged:

| Root | Mode | Guests |
| --- | --- | --- |
| `platform/proxmox/terraform/homelab-guests` | import-first, live | 300, 310 |
| `security/secrets-openbao/terraform` | create-mode, live | 320–322 |
| `services/netbox/terraform/proxmox-guest` | create-mode, live | 330 |
| `platform/proxmox/terraform/rebuild-guests` | create-mode, **rebuild only** | none by default |

Safety properties, each tested:

- `rebuild_guests` defaults to an empty set, so a plan creates nothing.
- A precondition requires `rebuild_confirmation` to equal
  `REBUILD <sorted names> FROM ZERO`.
- Every VM keeps `prevent_destroy`, `protection = true`,
  `purge_on_destroy = false`, `delete_unreferenced_disks_on_destroy = false`,
  `on_boot = false` and `started = false`; `onboot` is flipped later at L8.
- Its own state prefix. It must never be pointed at a live root's state, and a
  plan against a lab where the guest still exists must be refused by the
  operator (the VMID would collide).

EVE-NG (VM 290) is not in this root: it is restored from vzdump, not rebuilt.
