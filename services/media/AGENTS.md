# AGENTS.md — services/media

Inherits `../../AGENTS.md`; these rules add to it.

## Purpose and layout

The workstation media path: Plex and qBittorrent native on Windows, Radarr and
Prowlarr in the `media-vm` VirtualBox guest, library data on the NAS
`Media` share. It is its own component and never lives in cluster code.

- `config/compose.yaml` — digest-pinned guest containers (Radarr, Prowlarr,
  exportarr, node-exporter, Alloy, on-demand Recyclarr).
- `config/alloy/`, `config/recyclarr/`, `config/plex/libraries.yml`,
  `config/cloud-init/user-data.yml.tmpl`.
- `ansible/` — roles `media_host`, `arr_stack`, `plex`, `media_backup`;
  playbooks `00`, `30`, `40`, `41`, `45`, `50`. Inventory `../../inventory/media.yml`.
- `terraform/arr/` — *arr configuration (devopsarr providers), mocked tests.
- `scripts/` — `arr_backup.py`, `plex_libraries.py`, `plex-backup.ps1`.
- `docs/drift-reconciliation.md` — every Phase 0 ledger item and its home.

## Commands

```text
make setup        # venv, pinned tooling and collections
make check        # yamllint, ansible-lint, ruff, pytest, syntax
make plan         # offline tofu validate + test of the *arr root
make help         # each live stage runs exactly one playbook
```

## Component rules

- workstation stays Windows and sleeps after five hours; nothing always-on here.
- Never read or commit Plex tokens, `Preferences.xml`, *arr `config.xml`,
  application databases, CIFS credentials or media files.
- D2 retired the Docker Desktop Radarr container/image on 2026-09-30.
  Its opaque config archive is `D:\homelab-archive\radarr-config-20260930-212604.zip`;
  keep it unread, unadopted and unpublished. The live design stays in
  media-vm; do not recreate a competing Desktop Radarr container.
- Indexer/provider selection is an operator decision; never add one.
- One owner per object: OpenTofu (folders, clients, mappings, app links),
  Recyclarr (profiles, custom formats), operator (indexers, claim, firewall).
- Never change the Windows firewall, sleep policy or Plex settings from code.
- Every stage follows the full contract: `serial: 1`, `any_errors_fatal: true`,
  `allow_*` + exact confirmation, no `media-all` target.
- Use the `add-media-app` skill for a new app.

## Definition of done

`make check` passes here and `make COMPONENT=tests check` passes at the root;
staged gitleaks passes; `MEMORY.md` records any state change with its evidence.
