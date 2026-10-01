# Proxmox three-node cluster migration

The repository also contains steady-state Home Lab automation: import-first
Terraform for protected VMs 300/310 and gated, one-application-at-a-time
Ansible reconciliation for VM 300. See `docs/homelab-automation.md`.

Safely turn three standalone Proxmox VE hosts into one three-node cluster
without losing a single VM that matters.

```text
192.168.0.11  pve1   PVE 8.2.2  →  upgraded in place  →  cluster seed
192.168.0.12  pve2  PVE 8.2.2  →  workloads cataloged, rebuilt, joined empty
192.168.0.13  pve3  PVE 9.2.2  →  workloads cataloged, rebuilt, joined empty
192.168.0.20  Synology            →  NFS backup target, Volume 1 only
```

**Nothing here runs unattended.** Every stage is a separate command, every
destructive stage needs a boolean flag *and* an exact confirmation string *and*
an explicit `--tags all,destructive` opt-in, and the operations that genuinely
cannot be safely automated — ISO installations, `pvecm add`'s password prompt,
accepting a changed SSH host key — are done by a human, on purpose.

---

## Quick start

```bash
make setup          # create .venv, install ansible-core + linters + pytest
make lint           # yamllint, ansible-lint, ruff, shellcheck — all offline
make test           # unit tests + repository safety checks — all offline
make validate-ssh   # FIRST contact with the real hosts (read-only)
make discover       # read-only inventory of all three hosts
```

Then work through [docs/migration-runbook.md](docs/migration-runbook.md), one
stage at a time.

## SSH access is already in place

Key authentication is installed and working from the macOS controller. This
project **never** generates a key, never asks for a root password, never copies a
private key into the repository, and never disables host-key checking.

```yaml
ansible_user: root
ansible_ssh_private_key_file: ~/.ssh/proxmox_cluster_ed25519
ansible_python_interpreter: /usr/bin/python3
```

Validate by hand:

```bash
ssh pve1 'hostname; pveversion'
ssh pve2 'hostname; pveversion'
ssh pve3 'hostname; pveversion'
ansible -i ../../inventory/hosts.yml proxmox -m ansible.builtin.ping
```

If your key file has a different name, change **one** variable —
`ssh_key_name` in `inventory/group_vars/all.yml`. A unit test fails if anyone
hardcodes the filename anywhere else.

### After a reinstall or a cluster join

Clean-installing a node changes its SSH host key; so does `pvecm add`, which
replaces host keys with cluster-signed ones. The automation stops at each of
those points and prints exactly what to do. Nothing is auto-accepted.
See [docs/reinstall-ssh-recovery.md](docs/reinstall-ssh-recovery.md).

## The plan

| stage | command | what it does | risk |
|---|---|---|---|
| 0a | `make validate-ssh` | prove key auth + host identity | none |
| 0b | `make discover` | read-only inventory, collision + capacity reports | none |
| 1 | `make nas-preflight` | prove the Synology export is real, writable, on Volume 1 | none |
| 2 | `make capture-config` | capture what vzdump does **not** contain | none |
| 3 | `make backup-initial HOST=pve1` | generation 1 for the two kept guests | none |
| 3b | `make verify-backups-initial` | verify generation 1 before final shutdown | none |
| 4 | `make backup-final HOST=pve1` | generation 2, guests cleanly stopped | downtime |
| 4b | `make verify-backups` | checksum + `vma verify` every archive | none |
| 5 | `make prepare-pve3` | clean-install checklist for an empty member | wipes `.13` |
| 6a | `make precheck-upgrade-pve1` | `pve8to9 --full` + repository change report | none |
| 6b | `make upgrade-pve1` | PVE 8 → 9 in place | **irreversible** |
| 7 | `make create-cluster` | `pvecm create homelab` on `.11` | high |
| 8 | `make join-pve3` | join the empty node | high |
| 9a | `make precheck-destroy-pve2` | seven gates before `.12` may be wiped | none |
| 9b | `make postinstall-pve2` | validate the rebuilt node | none |
| 9c | `make join-pve2` | three-node quorum | high |
| 10 | `make validate` | full read-only validation + report | none |

There is deliberately no `deploy-all` or `migrate-all` target, and a unit test
fails the build if anyone adds one.

## Approval gates

Every destructive stage needs all three of:

1. a boolean flag (`allow_*`), which defaults to `false`;
2. an **exact** confirmation string, which defaults to `""`;
3. `--tags all,destructive`, because the dangerous tasks are tagged
   `never,destructive`.

```bash
make join-pve3 EXTRA_JSON='{"allow_join_pve3":true,"join_confirmation_pve3":"JOIN pve3 192.168.0.13 TO homelab"}'

make postinstall-pve2 EXTRA_JSON='{"allow_destroy_pve2":true,"destroy_confirmation_pve2":"DESTROY pve2 192.168.0.12 AND DISCARD ALL FIVE GUESTS","pve2_reinstalled":true,"pve2_fingerprint_verified":true}'
```

Before it acts, each stage prints a **proposed-change report** describing exactly
what it is about to do.

## VMID collisions resolve during the clean installs

Only VMIDs 290 and 297 on `.11` survive. The eight current guests on `.12` and
`.13` are cataloged in [docs/rebuild-catalog.md](docs/rebuild-catalog.md), then
both nodes are clean-installed and join empty. No old guest is renumbered or
restored.

`scripts/detect_vmid_collisions.py` does not stop at the collision we were told
about. It walks every guest on every host and reports **every** duplicate VMID and
**every** duplicate MAC address, including the ones that only exist because the
rebuild-later nodes still hold an ID — those are reported as
`resolves_on_rebuild` and never cause a retained guest to be renumbered.

## Why Ansible and Python, and not Terraform

This migration is a **sequence of gated, imperative, one-shot operations against
machines that already exist** — `pve8to9`, `apt dist-upgrade`, `pvecm create`,
`vzdump`, and `vma verify`. Ansible gives ordered execution, `serial: 1`,
per-task assertions, `any_errors_fatal`, tags that can withhold a dangerous task,
and the ability to stop and hand control back to a human. Python does the parts
worth unit-testing: collision detection, capacity maths with a pessimistic
compression assumption, backup adjudication, collision analysis, and pre/post state
diffing — all tested offline against fixtures.

Terraform is the wrong tool here, and not because it is a bad tool:

* it reconciles **declared state**; "upgrade 8.2 → 8.4 → 9.2, running a checklist
  between each step and stopping on a warning" is not a state;
* `terraform apply` executes a computed plan — exactly the unattended destructive
  command this project exists to prevent;
* importing production VMs into state makes them destroyable by a provider
  upgrade or a drifted attribute; these VMs must never be in state at all;
* it cannot install an OS from an ISO, cannot wipe a node, and has no concept of
  Corosync membership;
* "stream 400 GiB through `vma verify` and stop on a non-zero pipeline status" has
  no declarative expression.

Terraform **is** a reasonable choice afterwards, for provisioning *new* VMs from a
template on the finished cluster (`bpg/proxmox` or `Telmate/proxmox`). Keep it in a
separate repository with its own state, and never `terraform import` an existing
guest. It is intentionally not part of this repository's execution path.

## Repository layout

```text
platform/proxmox/
├── ansible.cfg              host_key_checking=True, publickey-only, BatchMode
├── Makefile                 one target per stage; no aggregate target
├── inventory/
│   ├── hosts.yml            three hosts, no credentials, recorded fingerprints
│   └── group_vars/all.yml   every tunable and every approval gate
├── playbooks/               19 stage playbooks, serial:1, any_errors_fatal
├── roles/                   11 roles (ssh_validation … validation)
├── scripts/                 6 stdlib-only Python tools + _common.py
├── templates/               manifest, restore plan, migration report
├── docs/                    architecture, runbook, NFS setup, SSH recovery,
│                            rollback, troubleshooting, acceptance criteria
├── tests/                   96 offline tests incl. repository safety checks
└── .github/workflows/ci.yml ruff, pytest, yamllint, ansible-lint, shellcheck,
                             gitleaks, destructive-gate validation
```

Additions beyond the requested tree, and why: `scripts/_common.py` (shared
stdlib helpers), `tests/test_repo_safety.py` and `tests/test_inventory_schema.py`
(they implement the required CI checks for destructive-task approval, hardcoded
secrets and inventory schema), `tests/test_state_comparison.py`, `.yamllint`,
`.ansible-lint`, `.gitleaks.toml` and `pyproject.toml` (linter configuration).

## Safety model

* `serial: 1` and `any_errors_fatal: true` on every playbook.
* Assertions before changes; the play stops on a failed check.
* `ignore_errors: true` appears nowhere. Neither does `rm -rf`,
  `pvecm expected`, `StrictHostKeyChecking=no`, or any password variable.
* No archive is ever deleted; the NFS storage is registered with
  `--prune-backups keep-all=1`, so Proxmox has no retention policy at all.
* No protected guest is touched without two verified archive generations.
  Rebuild-later guests are destroyed only after an exact discard confirmation.
* `/etc/pve` is never edited directly to bypass cluster rules.
* ISO reinstallation is never automated through the SSH session it would destroy.
* Every rule above is enforced by a test that runs in CI.

## What this cluster will and will not give you

| | |
|---|---|
| ✅ | one UI and API for three nodes; shared user, permission and firewall config |
| ✅ | cold migration between nodes; cluster-wide backup jobs |
| ❌ | **high availability** — HA is deliberately not enabled |
| ❌ | **live migration** — guest disks are on node-local LVM-thin, not shared storage |
| ❌ | **failover from the NAS** — it holds archives, not running disks |

`metasploitable2` is intentionally vulnerable software. It is not restored. If
rebuilt later, it must use an isolated, unrouted bridge.

## Backup strategy after the migration

Today you will have one copy of each VM, on one NAS, on one volume, in one
building. That is a backup target, not a backup strategy. Move toward **3-2-1**:
three copies, on two media types, one off-site.

The concrete next step is **Proxmox Backup Server**. Compared with dumping full
`vma.zst` files onto NFS, PBS gives you deduplicated incremental backups (so
daily backups of a 500 GiB EVE-NG VM stop costing 500 GiB), server-side
verification jobs that re-check archives on a schedule, retention that prunes
safely, single-file restore, and `proxmox-backup-manager sync` to replicate an
entire datastore to a second PBS off-site.

* Proxmox Backup Server documentation — <https://pbs.proxmox.com/docs/>
* Also worth resolving: the Synology's Storage Pool 1 health warning. A degraded
  pool sitting next to your only backup copy is a risk you can retire cheaply.

## Documentation

| document | what it is for |
|---|---|
| [architecture.md](docs/architecture.md) | environment, data flow, staging rationale, tooling choice |
| [migration-runbook.md](docs/migration-runbook.md) | the exact command order, with checklists and maintenance windows |
| [rebuild-catalog.md](docs/rebuild-catalog.md) | software and local websites to recreate after the cluster is stable |
| [synology-nfs-setup.md](../nas/docs/synology-nfs-setup.md) | manual DSM configuration, step by step |
| [reinstall-ssh-recovery.md](docs/reinstall-ssh-recovery.md) | what to do when a host key changes |
| [rollback.md](docs/rollback.md) | how to get back, per stage |
| [troubleshooting.md](docs/troubleshooting.md) | symptom-first decision tree |
| [acceptance-criteria.md](docs/acceptance-criteria.md) | the 16 criteria and their evidence |

## Official references

* Upgrade from 8 to 9 — <https://pve.proxmox.com/wiki/Upgrade_from_8_to_9>
* Cluster Manager — <https://pve.proxmox.com/wiki/Cluster_Manager>
* Backup and restore — <https://pve.proxmox.com/pve-docs/chapter-vzdump.html>
* NFS storage — <https://pve.proxmox.com/wiki/Storage:_NFS>
* Package repositories — <https://pve.proxmox.com/wiki/Package_Repositories>
* Roadmap / current release — <https://pve.proxmox.com/wiki/Roadmap>
* Proxmox VE 9.2 announcement — <https://proxmox.com/en/about/company-details/press-releases/proxmox-virtual-environment-9-2>
* ISO downloads — <https://www.proxmox.com/en/downloads/proxmox-virtual-environment/iso>
* Synology NFS permissions — <https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/file_share_privilege_nfs?version=7>
* Synology NFS service — <https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/file_winmacnfs_nfs?version=7>
* Accessing a Synology NAS over NFS — <https://kb.synology.com/en-global/DSM/tutorial/How_to_access_files_on_Synology_NAS_within_the_local_network_NFS>

## Licence

MIT — see [LICENSE](LICENSE).
