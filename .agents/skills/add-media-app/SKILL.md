---
name: add-media-app
description: Use when adding an *arr or Plex-adjacent app (Sonarr, Lidarr, Bazarr, Overseerr, Tautulli, an exporter) to the workstation media stack in services/media. Same checklist as add-homelab-service plus an exporter and backup. Not for VM 300 apps.
---

# Add a media app

Media is its own component (`services/media/`) and never lives in cluster code.
workstation is Windows, sleeps after five hours on AC, and is on-demand capacity.

## Steps

1. Decide placement: containers run in the `media-vm` VirtualBox guest,
   never in Docker Desktop (trusted runtime) and never as a new Windows service
   without operator approval. Check guest RAM (4 GiB) in `MEMORY.md`.
2. Add the service to `services/media/config/compose.yaml`: pinned image,
   `mem_limit`, health check, loopback-only published ports, drop all
   capabilities except what LinuxServer images need, `/media` bind for
   library paths, config under a named volume or guest path.
3. Never write API keys, `config.xml`, Plex tokens or `Preferences.xml` into
   source. Record the operator step that supplies them.
4. Indexer or provider selection is the operator's lawful-provider decision.
   Never add one.
5. Exporter: add an exportarr (or equivalent) container and a scrape target
   under `observability/config/prometheus/file_sd/`, marked as expected to be
   down while workstation sleeps.
6. Backup: document what state must be backed up (app database, config), where
   it goes (NAS), and how a restore is verified. A VirtualBox snapshot is not a
   verified backup. Never prune.
7. Any live stage you add follows the full contract: `serial: 1`,
   `any_errors_fatal: true`, `allow_*` + exact confirmation, a test for the
   gate, and no `media-all` target.
8. Update `services/media/README.md`, `docs/_plan/00-media-ledger.md` if a live
   fact changed, and `MEMORY.md`.

## Checks

`make -C services/media check`, `make -C observability check`,
`make COMPONENT=tests check`, staged gitleaks.
