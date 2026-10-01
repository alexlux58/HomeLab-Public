# AGENTS.md — platform/proxmox

Inherits `../../AGENTS.md`; these rules add to it.

## Purpose and layout

The finished Proxmox 8→9 three-node cluster migration (kept and tested) plus
import-first Terraform for protected VMs 300 and 310.

- `ansible/playbooks/migration/` — one-shot stages `00`–`90`; `ansible/roles/`.
- `ansible/ansible.cfg` — resolves paths from its own directory; `roles_path`
  includes `../../nas/ansible/roles` for `synology_nfs`.
- `terraform/homelab-guests/` — import-first root for VMs 300/310 (live).
- `terraform/rebuild-guests/` — rebuild-only, create-mode root for 300, 310,
  320–322 and 330 from `inventory/lab.yml` (ADR-0007); empty plan by default.
- `tests/` — pytest safety contract for this and the split-out components.
- `templates/`, `scripts/`, `docs/`, `site/` — stage inputs, helpers, runbooks.

## Commands

```text
make setup        # venv + Galaxy collections into ansible/collections
make check        # lint + test + syntax, offline
make help         # every stage; each runs exactly one
```

## Component rules

- The migration is complete. Re-running a stage is a live change; treat every
  stage target as operator-only.
- Destructive stages need `allow_*=true`, the exact confirmation string, and
  `--tags all,destructive`, passed as `EXTRA_JSON`. Flags include
  `allow_upgrade_pve1`, `allow_create_cluster`, `allow_join_pve3`,
  `allow_destroy_pve2`, `allow_join_pve2` and `allow_restore_pve2`.
- `test_repo_safety.py` also guards homelab-services, NetBox, NAS and AAA
  (includes resolve, SSH safety in every split-out `ansible.cfg`). Keep those
  assertions when paths move.
- OpenTofu here has no apply, destroy or import target, and never will. Live
  state is not in the monorepo (see `MEMORY.md`, ADR-0003); never plan a live
  root until the operator has migrated its state.
- VM 290 has snapshots vzdump does not include; VM 297 is gone and its VMID
  must not be reused without approval.

## Definition of done

`make check` passes here and `make COMPONENT=tests check` passes at the root;
staged gitleaks passes; `MEMORY.md` records any state change with its evidence.
