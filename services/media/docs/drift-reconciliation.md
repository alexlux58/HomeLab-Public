# Media drift reconciliation (Phase 3)

Every item from the Phase 0 ledger (`docs/_plan/00-media-ledger.md`) and where
it now lives. Nothing here was changed on workstation or in the guest.

| Ledger item | Phase 0 class | Now | Where |
| --- | --- | --- | --- |
| Media runtime record | codified narrative | Declared state is code; history stays in the roadmap | `config/`, `ansible/`, `terraform/arr/` |
| Plex design | partly stale | Libraries declared; settings drift reported; claim and client stay attended | `config/plex/libraries.yml`, `scripts/plex_libraries.py`, L5/L7 |
| Local status record | live drift | Superseded; kept as history only | `docs/legacy/workstation-LOCAL-STATUS.md` |
| Windows Plex firewall script | must-codify, attended | Kept as history; the client-scoped rule is an attended L5 step, never automated | `scripts/legacy/`, runbook L5 |
| Guest Compose source | must-codify | Codified, digest-pinned, extended with exporters, Alloy, Recyclarr | `config/compose.yaml` |
| Guest cloud-init seed | must-codify, non-public | Rewritten as a placeholder template from `lab.yml`; the old seed was not read | `config/cloud-init/user-data.yml.tmpl` |
| Old host-Docker Radarr state | quarantine | Still quarantined. **It is running** in Docker Desktop (MEMORY.md); stopping it is an operator decision | `MEMORY.md` Known gaps |
| VirtualBox disks, logs, snapshots | live drift | Retained. Rebuild is L0 (template) + L5 (Ansible) + L6 (app backups); a VirtualBox snapshot is not a backup | runbook L0, L6 |
| OVA, checksum, seed image | live drift | Retained; superseded by the template for rebuilds | runbook L0 |
| App Control policy XMLs | discard, keep for audit | Not deployed; kept outside the repo for audit | ledger |
| Session-only CIFS mount | live fact | Codified as a `nofail` systemd automount with an operator-installed credential | `ansible/roles/media_host` |
| Prowlarr → Radarr Full Sync | live fact | Declared | `terraform/arr/main.tf` |
| Radarr root folder, qBittorrent client, remote path map | live fact | Declared | `terraform/arr/main.tf` |
| Indexers | deferred decision | Deliberately undeclared: lawful-provider decision | ADR-0002 |
| Quality profiles and custom formats | not codified | Recyclarr (TRaSH), preview by default | ADR-0004, `config/recyclarr/` |
| Plex metadata backup | missing | Gated Windows task, append-only to NAS | `ansible/roles/plex`, `scripts/plex-backup.ps1` |
| *arr backups | missing | Nightly append-only copy with zip verification | `ansible/roles/media_backup`, `scripts/arr_backup.py` |
| Monitoring | missing | Alloy push to Prometheus; `MediaExporterDown` | ADR-0006, `observability/config/prometheus/rules/media.yml` |
