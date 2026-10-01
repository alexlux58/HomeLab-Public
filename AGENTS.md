# AGENTS.md — Home Lab

Canonical rules for all agents. Component `AGENTS.md` files add rules; never relax these.

## Purpose and layout

Private toolkit for the live Proxmox estate, NAS, services, observability,
media and secrets. Root `Makefile`: one target, one `COMPONENT`, no chaining.

| Path | What it owns |
| --- | --- |
| `inventory/` | Shared inventory boundary (see ADR-0001) |
| `platform/proxmox/` | Cluster migration history and Proxmox guest IaC |
| `platform/nas/` | Synology storage intent and checks |
| `services/homelab-services/` | VM 300 applications |
| `services/netbox/` | VM 330 NetBox |
| `services/media/` | workstation Plex/qBittorrent; *arr in media-vm; never in cluster code |
| `services/music-library/` | On-demand local music library (PySide6 + web companion) |
| `observability/` | VM 310 stack and agents |
| `security/secrets-openbao/`, `security/aaa-freeradius/` | Security plane |
| `tests/` | Cross-component contract tests, including agent guardrails |
| `tools/publish/` | Private sanitiser, scanner and publisher (`policy.yml` decides what is public); never published |
| `.github/workflows/` | Offline CI checks only, hosted runners, no secrets (ADR-0009) |
| `.agents/skills/`, `.agents/agents/` | Shared skills and reviewer prompts |
| `docs/` | Index, architecture, reference (incl. generated tables), runbooks, decisions, walkthrough, plan records |

Read first: this file, component `AGENTS.md`, `MEMORY.md`, `docs/reference/environment.md` and
`docs/reference/lessons-learned.md`. Plans live in `HOMELAB-ROADMAP.md`.

## Commands

```text
make COMPONENT=<component> check     # lint + test + syntax, offline
make -C <component> lint|test|syntax
make COMPONENT=tests check           # cross-component contracts (incl. workflows)
make docs-check                      # links, generated tables, diagrams, snippets, markdownlint
make docs                            # walkthrough PDF (devcontainer); fails on any warning
make rebuild-plan                    # L0-L8 ladder and local prerequisites
```

State plans/applies: workstation devcontainer with `D:\homelab-state`
mounted at `/homelab-state` (D1, ADR-0003). State
migration and re-adoption remain operator-only; never open state files.

Offline work needs no approval: lint, tests, `ansible-playbook --syntax-check`,
`terraform|tofu fmt`, and `validate` after `init -backend=false`.

## Safety contract

- Treat production hosts and irreplaceable data as live. Ask before changing a
  Proxmox host, NAS, guest, DNS, router, or workstation setting.
- Every playbook uses `serial: 1` and `any_errors_fatal: true`.
- Destructive tasks carry both `never` and `destructive` tags and run only with
  `--tags all,destructive`, their `allow_*` flag and exact confirmation string.
- `allow_*` defaults to `false`, paired confirmations default to `""`, and real
  assertions compare both. Every new gate gets a new test.
- No aggregate target of any name (`deploy-all`, `rebuild-all`, `media-all`…) in
  Make or in workflows.
- Never prune or delete a backup; NFS storage stays `keep-all=1`.
- D3 permits the reviewed one-node backup-pull stage only after the operator
  supplies its exact node confirmation. Install/run the local daily task only
  after that stage succeeds; never wake the PC or change its power/network settings.
- Terraform roots keep `prevent_destroy`, `purge_on_destroy = false` and
  `delete_unreferenced_disks_on_destroy = false`.
- Never auto-accept a changed SSH host key. Verify out of band (see lessons
  learned) and let the operator update the pin.
- ISO installs, `pvecm add`, OpenBao init/unseal/rekey and every approval value
  are the operator's. An agent prepares an approval; it never supplies one.
- D4: attended OpenBao ceremony 2026-10-10 (operator may move it); sole operator,
  five offline PGP keys/places, threshold three. Public keys/fingerprints only.
  Verify VM 320–322 archives the day before; follow `docs/runbooks/openbao-init-ceremony.md`.
- D5 approves the operator's WD Red Plus 4 TB CMR bay-3 replacement. Disk
  replacement, DSM Repair and RAID conversion stay attended operator work.
- The the router must never become authoritative for, or forward, `lab.example.com`.
- Never enable the declined Proxmox datacenter firewall or buy hardware.
- workstation stays Windows: no Proxmox, Hyper-V, wipes, sleep, VBS, firewall or
  networking changes, and nothing always-on. VirtualBox guests are permitted.
- Never loosen, skip or delete a safety test. If a path moves, move the path and
  keep the assertion.

## Forbidden commands (hooks and rules enforce these)

`terraform|tofu apply|destroy|import`, `bao operator …`, `pvecm …`,
`qm destroy`, `pct destroy`, `rm -rf`, `ignore_errors: true`,
`StrictHostKeyChecking=no`, live Ansible runs, and any Proxmox, OpenBao,
Synology, Plex or *arr API call — unless the current phase and the operator
explicitly allow that exact stage.

## Secrets and boundaries

Never open, print, copy or commit private keys, `~/.ssh/**`, real `.env` or
`*.tfvars`, `*.tfstate*`, runtime secret files, application databases, Plex
tokens or `Preferences.xml`, *arr `config.xml`, `artifacts/`, or
`host-configs/`. Listing filenames is fine. If a secret is already in a file,
record its path without printing it, move it behind a placeholder, and add it
to the rotation list in `MEMORY.md`. Credentials are operator-managed through
the approved secrets workflow.

Approved stages may handle public `.pub`/PGP `.asc` and fingerprints, never private keys.

D2 permits opaque Radarr config archival to `D:\homelab-archive`, then Desktop
folder/container/image removal. Never delete that ZIP, backups, snapshot branch,
legacy docs, artifacts or host-configs; retain Phase 1 archive until state is verified.
Music ownership transferred; preserve unrelated edits, media ledger, legacy
walkthrough and Music Library operator bootstrap MEMORY hunk. Stage MEMORY selectively.

`public/` is generated: never hand-edit; change private source and use `tools/publish/`.

Agents may push only to this repo's origin (HomeLab-Private) or public/'s origin
(HomeLab-Public), after relevant devcontainer checks and with the pre-push hook.
Install `python3 tools/repo-checks/install_push_hook.py`: resolved URL validation
and gitleaks on every newly pushed commit, excluding verified remote history. Windows gh/GCM is allowed;
never extract/transfer credentials. Public commits stay in the devcontainer for PDF scanning.
Never force (`--force`, `--force-with-lease`, `+refspec`), delete (`--delete`, `:ref`),
mirror, bypass hooks or use another remote/URL. GitHub: hosted checks only,
no lab secrets or deployments (ADR-0009).

## Conventions

Ansible FQCNs and named tasks; `changed_when: false` on read-only tasks.
snake_case for Python modules, roles and variables; kebab-case otherwise.
`.yml` for Ansible, `compose.yaml` for Compose, pytest for tests. Playbooks are
`NN-verb-object.yml`. Node names are `pve1`, `pve2` and `pve3` in source; a
repository change never renames anything live.

Use `git mv` or history-preserving merges for moves, one logical change per
Conventional Commit, and run gitleaks on staged content before every commit.
Measure before asserting: prefer a read-only command over an inference, and say
plainly when an earlier claim was wrong.

## Skills

| Task | Skill |
| --- | --- |
| Add an app to VM 300 | `add-homelab-service` |
| Add an *arr/Plex-adjacent app | `add-media-app` |
| Add a playbook with an approval gate | `add-gated-playbook` |
| Add a Proxmox guest or resource to IaC | `add-opentofu-resource` |
| Prepare approval values for a live stage | `run-gated-stage` |
| Plan a bare-metal rebuild | `rebuild-from-zero` |
| A check or workflow failed | `ci-failure-triage` |
| A safety test failed | `triage-safety-test-failure` |
| Build the walkthrough or docs | `build-docs` |
| Refresh the public copy | `publish-sanitised` |

## Definition of done

Component `make check`, root contracts and staged gitleaks pass offline.
MEMORY/roadmap record evidence, rollback and manual steps. Change rules here,
not in tool-specific files. Stop at phase gates until the operator says `go Phase N`.
