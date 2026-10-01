# Media services

This component documents the workstation media path. workstation remains a Windows
workstation. Plex and qBittorrent run natively there; the `media-vm`
VirtualBox guest runs the Radarr and Prowlarr containers.

## Current contract

- The NAS `Media` share holds the library data. Its `Movies` and `Downloads`
  directories are data, never source-controlled files.
- qBittorrent writes to `M:\Downloads` on workstation.
- The guest mounts the same share at `/mnt/media` and exposes it to containers
  at `/media`.
- Radarr uses `/media/Movies` and maps qBittorrent's `M:\Downloads` to
  `/media/Downloads`.
- Prowlarr is connected to Radarr. Indexers remain an operator-approved,
  lawful-provider decision and are intentionally not declared here.

## Source boundaries

`config/compose.yaml` is the non-secret container definition recovered from
the VM bootstrap source. CIFS credentials, application API keys, Plex claim
state, Plex metadata, and *arr databases remain operator-managed runtime data
outside Git.

## Rebuild and operation (Phase 3)

| Concern | Where |
| --- | --- |
| Guest first boot (L0) | `config/cloud-init/user-data.yml.tmpl` |
| Packages, NAS automounts (L5) | `make configure-host` → role `media_host` |
| Containers (L5) | `make deploy-arr` → role `arr_stack`, `config/compose.yaml` |
| *arr settings (L5) | `terraform/arr/` (OpenTofu, devopsarr providers) |
| Quality profiles (L5) | `make sync-quality-profiles` → Recyclarr, preview by default |
| Plex libraries (L5) | `scripts/plex_libraries.py` (plan by default) |
| Backups (L6) | `make configure-backup` (*arr), `make check-plex` backup gate (Plex) |
| Metrics | Alloy push to VM 310 (ADR-0006) |

Every live target is gated; see `AGENTS.md` and
`docs/runbooks/rebuild-from-zero.md`. The Phase 0 ledger items are mapped in
`docs/drift-reconciliation.md`.
