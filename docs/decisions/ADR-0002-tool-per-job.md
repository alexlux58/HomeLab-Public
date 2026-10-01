# ADR-0002: one tool per job

Status: accepted, Phase 3 (2026-09-29).

## Decision

| Job | Tool | Why |
| --- | --- | --- |
| Proxmox guests (identity, CPU/RAM, disks, NICs, cloud-init) | OpenTofu, `bpg/proxmox` pinned `0.107.0` | Declarative API; plan shows drift before change |
| *arr configuration (root folders, download clients, remote path mappings, Prowlarr app links, notifications) | OpenTofu, `devopsarr/radarr` `2.5.0`, `devopsarr/prowlarr` `3.2.1` | Declarative API with providers |
| *arr quality profiles and custom formats | Recyclarr (ADR-0004) | TRaSH-maintained; the providers never touch these objects |
| DNS records on the Synology, NAS shares/quotas/accounts | Manual, runbook step | No maintained provider for DSM 7.2 on an ARM the NAS |
| OS config, packages, users, mounts, Docker and Compose deployment | Ansible | Ordered, idempotent, can stop and hand control back |
| Anything imperative, ordered or attended (cluster join, upgrades, restore drills, OpenBao install to `initialized=false`) | Ansible, one gated stage each | Needs `serial: 1`, assertions and a stop point |
| Collision and capacity maths, reports, inventory contract | Python (stdlib, unit-tested) | Logic worth testing |
| Plex libraries and settings | Python (`python-plexapi`) | No provider; API gap |
| Uptime Kuma monitors | Python (`uptime-kuma-api`) | No provider; API gap |
| NetBox seed data | Python generating CSV for NetBox bulk import | No write access needed from automation |
| Thin wrappers | Shell under ~50 lines, `set -euo pipefail`, shellcheck-clean | Glue only |

Rules that apply to every tool:

- Mutating scripts default to `--dry-run` and need `--apply` plus an
  `allow`/confirmation pair; the confirmation names the target.
- HCL stays Terraform-compatible where it costs nothing. OpenTofu-only features
  (state encryption) live in `*.tofu` files, which Terraform ignores.
- Two tools never manage the same object. Ownership is listed in
  `docs/reference/coverage-matrix.yml`, one owner per row.

## Consequences

Terraform remains usable for `fmt`/`validate` on every root. `make` targets and
the devcontainer use `tofu`. No provider is added without an exact version pin.
