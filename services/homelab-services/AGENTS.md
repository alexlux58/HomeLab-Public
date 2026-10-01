# AGENTS.md — services/homelab-services

Inherits `../../AGENTS.md`; these rules add to it.

## Purpose and layout

VM 300 `homelab-services` (`pve2`, 192.168.0.30): Docker Engine and eight
Compose projects (nine containers) behind Nginx Proxy Manager with wildcard TLS.

- `ansible/playbooks/` — `30-configure-guest`, `31-preflight-services`,
  `40-deploy-service`, `50-configure-backups`; roles `homelab_guest_base`
  (also used by NetBox), `homelab_services`, `homelab_backup`.
- `config/templates/stage-d/` — per-app `compose/<app>/compose.yaml`, Homepage
  and NPM configuration. Inventory: `../../inventory/homelab-services.yml`.
- Live stages run from `platform/proxmox` (`make homelab-service SERVICE=<app>`).

## Commands

```text
make check        # yamllint + syntax check, offline
```

## Component rules

- One application per run (`SERVICE=<app>`); never reconcile all at once.
- Deployed Homepage cards need both `href` and `siteMonitor`; planned entries
  have neither (tests enforce this).
- NPM administration stays bound to `127.0.0.1:81`; public ports are 80/443.
- Secrets stay in `/etc/homelab/secret-store/` on the guest, never in templates.
- Use the `add-homelab-service` skill for a new app.

## Definition of done

`make check` passes here and `make COMPONENT=tests check` passes at the root;
staged gitleaks passes; `MEMORY.md` records any state change with its evidence.
