---
name: add-homelab-service
description: Use when adding a new application to VM 300 homelab-services (a Compose project behind NPM with a Homepage card). Covers compose, role defaults, NPM route, Homepage card with health check, backup and tests. Not for media/*arr apps (use add-media-app) or new VMs (use add-opentofu-resource).
---

# Add a VM 300 application

The operator deploys; you prepare an offline, reviewed change.

## Steps

1. Confirm the app is approved and measure capacity from `MEMORY.md` (VM 300
   has 6 GiB RAM on the HDD node `pve2`). Pick a port that is free in every
   existing `compose.yaml`.
2. Add `services/homelab-services/config/templates/stage-d/compose/<app>/compose.yaml`:
   pinned image (tag plus digest when known), `mem_limit`, health check,
   `restart: unless-stopped`, logging `max-size: 10m`, `max-file: "3"`, setup
   ports bound to `127.0.0.1` only, secrets from `/etc/homelab/secret-store/<app>.env`
   (never inline).
3. Add `<app>` to `homelab_services_valid_services` in
   `services/homelab-services/ansible/roles/homelab_services/defaults/main.yml`
   and to the `deploy` allow-list in `services/homelab-services/Makefile`.
4. Add the NPM route to `config/templates/stage-d/config/npm/http.conf` using the
   wildcard certificate, forced HTTPS and HSTS.
5. Add a Homepage card to `config/templates/stage-d/config/homepage/services.yaml`
   with both `href` and `siteMonitor`. A planned app gets neither.
6. If the app holds state, extend the backup set under
   `config/templates/stage-g/` and the `homelab_backup` role. Never prune.
7. Add an HTTPS probe to `observability/config/prometheus/file_sd/http.yml`.
8. Update the expected sets in `platform/proxmox/tests/test_repo_safety.py`
   (`test_every_vm300_application_has_declarative_compose_and_ansible_selection`,
   `test_declarative_proxy_covers_every_home_lab_site`) — add, never remove.
9. Record the change in `MEMORY.md` (planned, not deployed).

## Checks

- `make -C services/homelab-services check`, `make -C platform/proxmox check`,
  `make -C observability check`, `make COMPONENT=tests check`.
- Staged gitleaks passes; no secret value appears in any template.

## Hand-off

Give the operator the single-app command and its DNS step; use
`run-gated-stage` for any approval values. Never run the deploy yourself.
