# AGENTS.md — services/netbox

Inherits `../../AGENTS.md`; these rules add to it.

## Purpose and layout

VM 330 `netbox` on `pve3` (192.168.0.50). `terraform/proxmox-guest/`
is a create-mode root kept separate from the import-first guests;
`ansible/playbooks/` `30-preflight`, `31-configure-guest`, `40-deploy`,
`50-configure-backups`; roles `netbox_app`, `netbox_backup`; `config/templates/`.
Inventory: `../../inventory/netbox.yml`.

## Commands

```text
make setup        # venv + collections (shares the Proxmox pins)
make check        # yamllint + syntax check, offline
```

## Component rules

- First deployment is gated by `netbox_app_allow_first_deployment` and its
  exact confirmation; tests enforce both defaults.
- Backups are `pg_dump --serializable-deferrable`, append-only, never pruned.
- Superuser and API token are operator-installed; never generated here.
- The root must stay destroy-protected, `on_boot = false`, and separate from
  `terraform/homelab-guests`. Its state is only in the source archive.
- Isolated restore and `onboot=1` remain open gates.

## Definition of done

`make check` passes here and `make COMPONENT=tests check` passes at the root;
staged gitleaks passes; `MEMORY.md` records any state change with its evidence.
