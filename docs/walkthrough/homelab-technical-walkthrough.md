<!--
Source of the technical walkthrough PDF. Build with `make docs`; the directives
(snippet, include, diagram) and repo: links are documented in
tools/docs-build/build.py. Never paste code by hand: use a snippet directive.
Each top-level heading is a numbered chapter of the PDF, hence MD025 is off.
-->
<!-- markdownlint-disable MD025 -->

# Overview

This lab is three Proxmox VE 9 nodes in one cluster called `homelab`, a Synology
NAS that holds the backups and the private DNS zone, and a Windows desktop
(workstation) used only for on-demand workloads. The repository you are reading is
the only way changes reach it: a gated, stage-by-stage toolkit of Ansible,
OpenTofu and Python. Nothing runs end to end. Every live stage is one Make
target that refuses to start until the operator passes an approval flag and an
exact confirmation string.

::: note
Facts in this document come from [`docs/reference/environment.md`](repo:docs/reference/environment.md),
[`MEMORY.md`](repo:MEMORY.md) and the source itself, and are true as of the
commit printed on the cover. Volatile state (what is running today, open gaps)
lives in [`MEMORY.md`](repo:MEMORY.md) and
[`HOMELAB-ROADMAP.md`](repo:HOMELAB-ROADMAP.md); read those before acting.
:::

## Hosts

| Host | Address | Alias | Role | Hardware |
| --- | --- | --- | --- | --- |
| `pve1` | 192.168.0.11 | `pve1` | Cluster seed; EVE-NG, observability, bao-1 | Xeon E-2186M, 12 cores, 31 GiB, 477 GiB NVMe |
| `pve2` | 192.168.0.12 | `pve2` | Homelab services, bao-2 | i5-8250U, 8 cores, 11.5 GiB, 932 GiB HDD |
| `pve3` | 192.168.0.13 | `pve3` | NetBox, bao-3 | i5-6500, 4 cores, 7.6 GiB, 112 GiB SSD |
| `nas1` | 192.168.0.20 | `nas` | Synology the NAS: backups (NFS), split-horizon DNS, media share | ARM64, 1.6 GiB |
| `workstation` | 192.168.0.70 | `workstation` | Windows 11 Home: Plex, media guest, music library, staging | Ryzen 7 2700X, 32 GiB, GTX 1080 |
| PiVPN | 192.168.0.60 | `pivpn` | WireGuard, IPsec, Pi-hole (unmanaged) | Raspberry Pi |

The network is one flat `/22` (192.168.0.0/24) behind an the router router. The
192.168.0.x addresses are inside that same `/22`; they are **not** a separate
security zone. The single source of truth for every identity above is
[`inventory/lab.yml`](repo:inventory/lab.yml):

<!-- snippet: inventory/lab.yml lines=14-22 sha=2e6b5e9b53f5 lang=yaml -->

The network block is what every consumer (OpenTofu through `yamldecode()`, the
Ansible inventories through a contract test) agrees on. The comments carry the
two constraints that matter most: the `/22` is flat, and the the router must never
become authoritative for the lab zone. A `null` anywhere in this file means
"not recorded", and any consumer that needs the value refuses to run.

<!-- diagram: 01-physical-network caption="Physical hosts, addresses and the flat /22 network" -->

## Service catalogue

| Guest | VMID | Node | Address | What runs there | Component |
| --- | --- | --- | --- | --- | --- |
| EVE-NG | 290 | `pve1` | — | Network emulation lab (restored from vzdump, never rebuilt) | [`platform/proxmox/`](repo:platform/proxmox) |
| homelab-services | 300 | `pve2` | 192.168.0.30 | Nginx Proxy Manager, Homepage, Uptime Kuma, Linkding, IT-Tools, PairDrop, Speedtest Tracker, NetKnife (API + web) | [`services/homelab-services/`](repo:services/homelab-services) |
| observability | 310 | `pve1` | 192.168.0.31 | Prometheus, Grafana, Loki, Alertmanager, Alloy and five exporters | [`observability/`](repo:observability) |
| bao-1, bao-2, bao-3 | 320–322 | one per node | 192.168.0.41–22, VIP .19 | OpenBao 2.6.1 Raft cluster, **uninitialized** | [`security/secrets-openbao/`](repo:security/secrets-openbao) |
| netbox | 330 | `pve3` | 192.168.0.50 | NetBox (six containers) | [`services/netbox/`](repo:services/netbox) |
| media-vm | VirtualBox | workstation | NAT | Radarr, Prowlarr, Recyclarr, exporters, Alloy | [`services/media/`](repo:services/media) |
| (native) | — | workstation | — | Plex Media Server, qBittorrent, Music Library | [`services/media/`](repo:services/media), [`services/music-library/`](repo:services/music-library) |

Private sites (`*.lab.example.com`) all terminate TLS at Nginx Proxy Manager
on VM 300 with a trusted DNS-01 wildcard certificate, then forward to the guest
that serves them.

<!-- diagram: 02-logical-components caption="Logical components and how they depend on each other" -->

# Repository map

The monorepo groups components by layer. Each component has its own
`Makefile`, `AGENTS.md` and offline checks; the root
[`Makefile`](repo:Makefile) only dispatches one target to one component
(`make COMPONENT=<path> <target>`).

```text
.
├── inventory/               lab.yml (single source of truth) + Ansible inventories
├── platform/
│   ├── proxmox/             cluster migration history, guest OpenTofu, rebuild L0–L3
│   ├── nas/                 Synology NFS preflight and registration
├── services/
│   ├── homelab-services/    VM 300 applications
│   ├── netbox/              VM 330 NetBox
│   ├── media/               workstation Plex and the *arr guest
│   └── music-library/       local music library (desktop + web companion)
├── observability/           VM 310 stack, dashboards, alerts, backups
├── security/
│   ├── secrets-openbao/     OpenBao cluster, PKI, policies, backups
│   └── aaa-freeradius/      FreeRADIUS discovery (no deployment yet)
├── tests/                   cross-component safety contracts
├── tools/                   repo checks, rebuild planner, CI helper, docs, publisher
├── docs/                    decisions, runbooks, reference, walkthrough
└── .github/workflows/       offline CI, PR plans, dispatch-only deploys
```

| Path | Responsibility | Invoked by | Reads / writes |
| --- | --- | --- | --- |
| [`inventory/lab.yml`](repo:inventory/lab.yml) | Every node, guest, address, MAC, backup job | OpenTofu `yamldecode()`, contract tests, rebuild planner | Read only by tooling; edited by hand |
| [`inventory/`](repo:inventory) `*.yml` | Ansible inventories per component | Each component's `ansible.cfg` | Read by Ansible |
| [`platform/proxmox/`](repo:platform/proxmox) | Migration stages 0–11, VM 300/310 adoption, rebuild L0–L3 | `make -C platform/proxmox <stage>` | Proxmox hosts over SSH; `artifacts/` (git-ignored) |
| [`platform/nas/`](repo:platform/nas) | NFS target preflight and storage registration | `make -C platform/nas preflight` | Proxmox storage config |
| [`services/homelab-services/`](repo:services/homelab-services) | VM 300 base, one Compose project per app, app backups | `make -C platform/proxmox homelab-service SERVICE=<app>` | `/opt/homelab`, `/srv/homelab` on VM 300 |
| [`services/netbox/`](repo:services/netbox) | VM 330 guest, NetBox Compose, `pg_dump` backups | `make -C platform/proxmox netbox-*` | VM 330 |
| [`services/media/`](repo:services/media) | Media guest, *arr containers and settings, Plex checks | `make -C services/media <stage>` | media-vm, NAS media share |
| [`observability/`](repo:observability) | Central monitoring stack and its backup/restore drill | `make -C observability <stage>` | VM 310 |
| [`security/secrets-openbao/`](repo:security/secrets-openbao) | OpenBao hosts, TLS, HA, post-init policy, Raft backups | `make -C security/secrets-openbao <stage>` | VMs 320–322 |
| [`tests/`](repo:tests) | Contracts across components: gates, workflows, denylist, guards | `make COMPONENT=tests check`, CI | Read only |
| [`tools/`](repo:tools) | Inventory contract, forbidden constructs, rebuild planner, docs build, publisher | Make targets and CI | Generated docs only |
| [`.github/workflows/`](repo:.github/workflows) | Offline checks only | GitHub Actions | See [CI checks](#ci-checks) |
| [`.agents/`](repo:.agents), [`.claude/`](repo:.claude), [`.codex/`](repo:.codex) | Agent skills, guard hook, execution policy | Coding agents | Read only |
| [`docs/`](repo:docs) | Decisions, runbooks, reference, this walkthrough | Humans, `make docs` | `docs/reference/generated/` is generated |

<!-- diagram: 03-repo-responsibility caption="Which directory is responsible for which part of the lab" -->

## One source of truth

[`inventory/lab.yml`](repo:inventory/lab.yml) is the single source of truth
([ADR-0005](repo:docs/decisions/ADR-0005-inventory-source-of-truth.md)). A live
identity changes there first and in its consumer in the same commit.
[`tools/repo-checks/inventory_contract.py`](repo:tools/repo-checks/inventory_contract.py)
compares the file with every Ansible inventory and OpenTofu root. Deliberate
differences are recorded in a ratchet:

<!-- snippet: tools/repo-checks/inventory_contract.py lines=21-30 sha=af601977c5bd lang=python -->

Each entry is keyed by the consumer file and the key that differs, and its value
says why the difference is allowed and how it will be removed. The one current
entry is the NetBox root's retired NAS address. Changing it before the state
migration would make a plan against the live VM 330 propose a cloud-init
change.

<!-- snippet: tools/repo-checks/inventory_contract.py lines=229-239 sha=93f89514d65d lang=python -->

The ratchet works in both directions. `unexpected` returns drift that is not
listed, which fails `test_no_unexpected_drift`. `stale_known_drift` returns
entries that no longer drift, which fails
`test_known_drift_entries_are_still_real`. An exception therefore cannot
outlive its reason.

<!-- diagram: 04-single-source-of-truth caption="inventory/lab.yml and the consumers checked against it" -->

# Safety model

The lab is live and some of its data is irreplaceable. The repository is built
so that the default outcome of any command is "nothing changed". Every rule
below has a mechanism that enforces it and a test that fails the build if the
mechanism is removed.

<!-- diagram: 05-gated-stage caption="How one gated stage runs, from the operator's command to the verify step" -->

| Rule | Gate or mechanism | Enforcing test |
| --- | --- | --- |
| A live stage needs an approval flag **and** an exact confirmation | `pre_tasks` assert in each playbook; flags default `false`, confirmations `""` | [`tests/test_stage_gates.py`](repo:tests/test_stage_gates.py#L51-L58), [`test_every_allow_flag_defaults_to_false`](repo:platform/proxmox/tests/test_repo_safety.py#L409), [`test_every_confirmation_defaults_to_empty`](repo:platform/proxmox/tests/test_repo_safety.py#L417) |
| Destructive tasks never run by accident | Tagged `never` + `destructive`; need `--tags all,destructive` | [`test_destructive_tasks_carry_never_and_destructive`](repo:platform/proxmox/tests/test_repo_safety.py#L238) |
| One host at a time, stop on first error | `serial: 1`, `any_errors_fatal: true` | [`test_every_playbook_is_serial_one_and_fatal_on_error`](repo:platform/proxmox/tests/test_repo_safety.py#L132-L144) |
| No aggregate target (`deploy-all` and friends) | Root Makefile only dispatches one target | [`test_makefile_has_no_aggregate_target`](repo:platform/proxmox/tests/test_repo_safety.py#L153-L156), [`test_no_target_chains_rungs`](repo:tests/test_rebuild_ladder.py#L94) |
| Backups are never pruned or deleted | NFS storage and every job are `keep-all=1` | [`test_no_archive_is_ever_deleted`](repo:platform/proxmox/tests/test_repo_safety.py#L312-L321), [`test_pruning_is_disabled_by_policy`](repo:platform/proxmox/tests/test_repo_safety.py#L487), [`test_no_backup_job_prunes`](repo:tests/test_inventory_contract.py#L78) |
| OpenTofu never destroys a live guest | `prevent_destroy`, `purge_on_destroy = false`, import-first adoption; no apply/destroy Make target | [`test_home_lab_terraform_is_import_first_and_destroy_protected`](repo:platform/proxmox/tests/test_repo_safety.py#L159), [`checks-only workflow contract`](repo:tests/test_workflows.py) |
| SSH host keys are never auto-accepted | `StrictHostKeyChecking` stays on in every `ansible.cfg` | [`test_every_monorepo_ansible_cfg_keeps_host_key_checking_on`](repo:platform/proxmox/tests/test_repo_safety.py#L572) |
| No secret is ever tracked | `.gitignore`, gitleaks in pre-commit and CI, denylist scan | [`test_no_secret_bearing_path_is_tracked`](repo:tests/test_denylist.py#L37), [`test_no_secret_shaped_value_is_tracked`](repo:tests/test_denylist.py#L44) |
| No `ignore_errors`, `rm -rf` or `StrictHostKeyChecking=no` | Forbidden-construct scanner with a shrinking baseline | [`test_tree_has_no_forbidden_construct_beyond_the_baseline`](repo:tests/test_forbidden_constructs.py#L8) |
| Agents cannot run live commands or read secrets | Claude `PreToolUse` guard, Codex execution-policy rules | [`test_forbidden_commands_are_blocked`](repo:tests/test_claude_guard.py#L92), [`test_forbidden_commands`](repo:tests/test_codex_rules.py#L87) |
| GitHub performs hosted checks only | Read permissions, SHA-pinned actions, no secrets or deploy stages | [`checks-only workflow contract`](repo:tests/test_workflows.py) |
| Every stateful item has a backup or a stated reason | Coverage and backup matrices | [`test_zero_undocumented_rows`](repo:tests/test_coverage_matrix.py#L35), [`test_every_guest_has_a_backup_job_or_a_reason`](repo:tests/test_inventory_contract.py#L70) |

## The approval gate

Every live playbook opens the same way. Here is the stage that deploys one
application to VM 300:

<!-- snippet: services/homelab-services/ansible/playbooks/40-deploy-service.yml lines=1-22 sha=97f092610cbb lang=yaml -->

The play targets one group, one host at a time (`serial: 1`), and aborts every
host on the first failure (`any_errors_fatal`). The flag and the confirmation
are declared as play variables with safe defaults, so the assert fails unless
both are overridden with extra variables. The confirmation embeds the
application name and the host, so an approval for one app on one guest cannot
be replayed against another. The test below pins this exact shape.

<!-- snippet: tests/test_stage_gates.py lines=51-58 sha=53bcd97eba8d lang=python -->

The test loads the playbook as YAML rather than grepping it. It checks that the
defaults are `False` and `""` and that the **first** pre-task is the two-line
assert, so no role can run before the gate. Confirmations are passed as
`EXTRA_JSON`, never as `-e key=value`: Ansible's key/value parser splits
multi-word strings (see [lessons learned](repo:docs/reference/lessons-learned.md)).

## Destructive tasks

::: danger
Tasks that stop guests, wipe disks or discard data carry both the `never` and
`destructive` tags. They run only when the command line also says
`--tags all,destructive`, the stage's `allow_*` flag is `true`, and its exact
confirmation string matches. Never add the tags to a command you have not
reviewed line by line.
:::

<!-- snippet: platform/proxmox/ansible/roles/vzdump_backup/tasks/shutdown_guests.yml lines=16-27 sha=882a1e3cc6d0 lang=yaml -->

The second assert exists because Ansible silently skips `never`-tagged tasks.
Without it, an operator who set the approval variables but forgot the tag would
see a green run that shut nothing down and backed up running guests. The
assert turns that silent skip into a failure that says exactly what to add.

<!-- snippet: platform/proxmox/ansible/roles/vzdump_backup/tasks/shutdown_guests.yml lines=60-69 sha=442452e65821 lang=yaml -->

The shutdown itself is graceful (`--forceStop 0`), loops only over guests that
were recorded as running, and is tagged so it cannot run by default. The
recorded power states are written to `artifacts/` first, so the rollback knows
which guests to start again.

## Structural tests

<!-- snippet: platform/proxmox/tests/test_repo_safety.py lines=132-156 sha=fe8f5c8e23f6 lang=python -->

These tests read every playbook and the Makefile. They fail on a play without
`any_errors_fatal: true`, a host play without `serial: 1`, a banned playbook
name such as `site.yml`, or an aggregate target such as `deploy-all:`. Local
plays against `localhost` are exempt from `serial` because they touch no host.

## Agent guardrails

Coding agents work in this repository. The Claude Code hook
[`.claude/hooks/guard.py`](repo:.claude/hooks/guard.py) and the Codex rules in
[`.codex/rules/homelab.rules`](repo:.codex/rules/homelab.rules) block live
commands and reads of secret-bearing paths:

<!-- snippet: .claude/hooks/guard.py lines=24-43 sha=9e59b8a6c4f2 lang=python -->

The guard blocks reading these paths; listing a filename is still allowed. It
fails closed: malformed hook input, or any internal error, blocks the tool
call. [`tests/test_claude_guard.py`](repo:tests/test_claude_guard.py) runs the
hook as a subprocess against forbidden commands, wrapped forms (`ssh`, `sudo`,
`bash -c`, `xargs`), and ordinary offline work that must stay allowed.

<!-- diagram: 17-agent-workflow caption="How an agent change moves from task to commit under the guardrails" -->

The full list of gates, generated from the playbooks, is in
[Appendix C](#appendix-c-approval-gates).

# Proxmox cluster

## Architecture

Three standalone PVE hosts were converted into one cluster, `homelab`, without
losing a protected guest (stages 0–11, all complete). HA is disabled. There is
no shared storage for guests: `pve1` uses `local` (directory on NVMe), and
`pve2` and `pve3` each have their own `local-lvm` thin pool, so live
migration is not available. Shared storage exists only for backups:
`synology-backup`, an NFS export on NAS Volume 1 registered with
`--prune-backups keep-all=1`.

OpenTofu owns guest *identity* (VMID, node, CPU, memory, NIC, protection,
startup). It does not own disks, EFI, cloud-init, applications, DNS or
passwords. Two kinds of root exist
([ADR-0007](repo:docs/decisions/ADR-0007-rebuild-only-guest-root.md)):
import-first roots that adopt live guests, and one create-mode root that is only
ever used to rebuild after a total loss.

<!-- diagram: 07-tofu-import-vs-create caption="Import-first roots adopt live guests; the rebuild-only root creates them after a loss" -->

## Files

| File | Purpose |
| --- | --- |
| [`platform/proxmox/Makefile`](repo:platform/proxmox/Makefile) | Every stage as one target; `EXTRA_JSON` carries approvals |
| [`platform/proxmox/ansible/playbooks/migration/`](repo:platform/proxmox/ansible/playbooks/migration) | Numbered migration stages 00–90 |
| [`platform/proxmox/ansible/roles/`](repo:platform/proxmox/ansible/roles) | Backup, verify, cluster, join, host-config and guest roles |
| [`platform/proxmox/terraform/homelab-guests/`](repo:platform/proxmox/terraform/homelab-guests) | Import-first adoption of VMs 300 and 310 |
| [`platform/proxmox/terraform/rebuild-guests/`](repo:platform/proxmox/terraform/rebuild-guests) | Create-mode root, driven by `lab.yml` |
| [`platform/proxmox/scripts/`](repo:platform/proxmox/scripts) | Answer files, restore plans, capacity, VMID collisions, archive verification |
| [`platform/proxmox/tests/test_repo_safety.py`](repo:platform/proxmox/tests/test_repo_safety.py) | The structural safety suite |
| [`platform/proxmox/docs/`](repo:platform/proxmox/docs) | Migration runbook, rollback, troubleshooting, rebuild catalogue |

## Key code

<!-- snippet: platform/proxmox/terraform/homelab-guests/imports.tf lines=1-11 sha=f712001c8c3f lang=terraform -->

With an empty state, a plain `resource` block would make OpenTofu propose
creating VMs 300 and 310 again. The `import` blocks bind the resources to the
existing guests by `node/vmid`. The first plan therefore shows an adoption, not
a creation.

<!-- snippet: platform/proxmox/terraform/homelab-guests/main.tf lines=5-18 sha=a75c8f820f5d lang=terraform -->

Proxmox-level `protection` stops the guest being deleted from the UI or API.
The three `*_on_destroy` settings make a destroy leave disks alone.
`prevent_destroy` in the `lifecycle` block makes OpenTofu refuse any plan that
would destroy the resource. The `lifecycle` block also ignores disks and
cloud-init, which Ansible and the guest own.

<!-- snippet: platform/proxmox/terraform/rebuild-guests/main.tf lines=9-32 sha=3c55be1b2441 lang=terraform -->

The rebuild root reads [`inventory/lab.yml`](repo:inventory/lab.yml) directly
and considers only guests marked `rebuild: true`. By default
`rebuild_guests` is empty, so a plan is empty. To create anything, the operator
must list guests by name **and** supply the confirmation
`REBUILD <sorted names> FROM ZERO`; both are OpenTofu preconditions.

## Operate

```bash
make -C platform/proxmox check                  # offline: lint, tests, syntax
make -C platform/proxmox validate-ssh           # read-only
make -C platform/proxmox discover               # read-only
make -C platform/proxmox terraform-plan         # import-first plan for 300/310
make -C platform/proxmox rebuild-guests-test    # offline, mocked provider
```

There is no `apply` or `destroy` Make target anywhere. Applying a reviewed plan
is an operator action, done in
the local devcontainer. The operator reviews the plan and supplies the
existing local approval; GitHub never plans or applies.

::: warning
`qm set <vmid> --nameserver …` on a **stopped** cloud-init guest regenerates
its SSH host keys on the next boot. Expect a host-key change and verify the new
key through `qm guest exec <vmid> -- /usr/bin/ssh-keygen -lf
/etc/ssh/ssh_host_ed25519_key.pub` before the operator updates the pin.
:::

## Recover

A node is rebuilt with rungs L0–L2 of the [rebuild ladder](#rebuild-ladder).
The rungs are: an answer-file ISO install, `pve_host_config` for jobs, onboot
and startup, and a manual `pvecm add`. Guests come back from
`synology-backup` with `qmrestore` to a spare VMID, all NICs link-down, before
anything is swapped in. VM 290 (EVE-NG) is only ever restored from vzdump.

::: danger
Rebuilding a node discards its local guests. `pvecm add`, ISO installs and any
restore over a live VMID are manual operator steps. No Make target or workflow
performs them.
:::

# NAS and network

## Architecture

The Synology the NAS (`nas1`, 192.168.0.20) has two jobs here. It is the
backup target (NFS on Volume 1), and it is the authoritative DNS server for
the private zone `lab.example.com`. Volume 1 is a single 12 TB disk with **no
redundancy**, so losing that disk loses every archive at once. Volume 2 is a
RAID1 mirror whose Disk 3 has failed SMART and is scheduled for replacement.

D5 approves a WD Red Plus 4 TB CMR replacement in bay 3. The
[attended replacement runbook](repo:platform/nas/docs/disk3-replacement.md)
requires a fresh healthy Disk 4 result and a verified independent backup,
then DSM Repair and supported post-rebuild checks. RAID1 parity scrubbing
is unavailable in DSM; use the actual filesystem's offered scrub operation
or record it unsupported and verify SMART/files instead. Volume 1's larger
structural risk is addressed separately by adding a 12 TB+ CMR disk in empty
bay 1 and converting its Basic pool to RAID1, never Basic to SHR.

DNS is split-horizon **without** the router. The the router must never be
authoritative for, or forward, `lab.example.com`: doing so takes the
operator's home-automation hub offline. Each guest therefore gets a systemd-resolved
*routing domain* (`Domains=~lab.example.com`, `DNS=192.168.0.20`). Only
private-zone queries go to the NAS; everything else stays on the the router,
including its IPv6 resolver.

## Files

| File | Purpose |
| --- | --- |
| [`platform/nas/ansible/playbooks/05-synology-preflight.yml`](repo:platform/nas/ansible/playbooks/05-synology-preflight.yml) | Read-only NFS reachability and throughput probe |
| [`platform/nas/ansible/roles/synology_nfs/`](repo:platform/nas/ansible/roles/synology_nfs) | Preflight and gated storage registration |
| [`platform/nas/docs/synology-storage-health.md`](repo:platform/nas/docs/synology-storage-health.md) | Disk and pool health, measured options |
| [`observability/config/prometheus/file_sd/dns.yml`](repo:observability/config/prometheus/file_sd/dns.yml) | The only DNS target that may be probed |

## Key code

<!-- snippet: platform/nas/ansible/roles/synology_nfs/defaults/main.yml lines=8-10 sha=d35f340481b1 lang=yaml -->

This one value makes the NFS storage append-only from Proxmox's point of view.
With no retention policy, Proxmox never prunes an archive. The same value is
repeated on every scheduled job by `pve_host_config`, and a test asserts that no
job prunes.

<!-- snippet: observability/config/prometheus/file_sd/dns.yml lines=1-16 sha=f01173a2b4e3 lang=yaml -->

The comment records a decision that is easy to undo by mistake. Probing the
the router for the lab zone would look like thorough monitoring, but it asserts a
behaviour the architecture forbids. It would fire `DnsResolutionFailed`
permanently.

## Operate

```bash
make -C platform/nas check          # offline
make -C platform/proxmox nas-preflight   # read-only NFS probe from all nodes
ssh nas                             # port 2258, user labadmin; sudo needs a password
```

## Recover

The NAS is rung L0 and is entirely manual. The steps are: restore the DSM
configuration backup, recreate the shares (`proxmox-cluster-backups` on
Volume 1; `Media` and `media-backups` on Volume 2), recreate the NFS export and
the DNS zone, and pin the SSH host key under `HostKeyAlias nas`. DSM has no
provider, and its admin credentials are the operator's.

::: warning
Never "simplify" guest DNS by pointing guests wholesale at 192.168.0.20. If
the NAS is down, guests would lose all name resolution instead of only the
private zone.
:::

# Homelab services (VM 300)

## Architecture

VM 300 `homelab-services` runs on `pve2` at 192.168.0.30 (Ubuntu 24.04,
4 vCPU, 6 GiB, 120 GiB on `local-lvm`). It runs eight independent Compose
projects with nine containers. Every image is digest-pinned and has an explicit
memory limit and a health check. Nginx Proxy Manager terminates TLS for every
private site, including the observability UIs on VM 310 and NetBox on VM 330.
Its admin UI is bound to `127.0.0.1:81` and reached only through an SSH tunnel.

<!-- diagram: 08-vm300-request-path caption="A browser request to a private site: DNS, TLS at NPM, then the backend" -->

## Files

| File | Purpose |
| --- | --- |
| [`services/homelab-services/ansible/playbooks/`](repo:services/homelab-services/ansible/playbooks) | Guest config (30), preflight (31), one-app deploy (40), backups (50) |
| [`services/homelab-services/ansible/roles/homelab_services/tasks/main.yml`](repo:services/homelab-services/ansible/roles/homelab_services/tasks/main.yml) | Renders exactly one Compose project; NPM route ownership gate |
| [`services/homelab-services/config/templates/stage-d/compose/`](repo:services/homelab-services/config/templates/stage-d/compose) | One `compose.yaml` per application |
| [`services/homelab-services/config/templates/stage-d/images.lock.json`](repo:services/homelab-services/config/templates/stage-d/images.lock.json) | Image digests |
| [`services/homelab-services/config/templates/stage-g/backup.py`](repo:services/homelab-services/config/templates/stage-g/backup.py) | Application-aware backup |
| [`services/homelab-services/config/uptime-kuma/monitors.yml`](repo:services/homelab-services/config/uptime-kuma/monitors.yml) | Declared monitors, compared with the live dump |

## Key code

<!-- snippet: services/homelab-services/config/templates/stage-g/backup.py lines=63-78 sha=06c7984fa9f4 lang=python -->

SQLite files are never copied while the app is running. The source is opened
read-only through a URI, and SQLite's online backup API writes a consistent
copy. `PRAGMA integrity_check` must return exactly `ok` or the run fails.
Uptime Kuma 2 uses MariaDB, not SQLite, so it gets a transactional
`mariadb-dump` instead.

## Operate

```bash
make -C platform/proxmox homelab-preflight            # read-only
make -C platform/proxmox homelab-service SERVICE=homepage \
  EXTRA_JSON='{"homelab_allow_service_deploy":true,"homelab_service_deploy_confirmation":"DEPLOY homepage ON homelab-services"}'
ssh -N npm-admin    # then browse http://127.0.0.1:8181 for the NPM admin UI
```

One run reconciles one application. The Homepage card policy is tested:
deployed cards need both an `href` and a `siteMonitor`, and planned entries have
neither.

## Recover

The backup timer runs at 02:45 and writes to `/srv/homelab-backups/staging`.
The 03:15 vzdump of VM 300 carries that off the guest. A restore goes to an
isolated copy (protected VMID 399, NIC link-down). The SQLite files are copied
back with the app stopped, and the Kuma dump is replayed into its MariaDB. This
path was proven end to end before VM 300 was set to `onboot=1`.

# NetBox (VM 330)

## Architecture

VM 330 `netbox` runs on `pve3` at 192.168.0.50 with six containers.
UFW admits port 8000 only from VM 300, and NPM serves `netbox.lab.example.com`
and `ipam.lab.example.com`. The database starts empty; the rebuild hint from
the destroyed `pve2` snapshot is not a backup. Its OpenTofu root
([`services/netbox/terraform/proxmox-guest/`](repo:services/netbox/terraform/proxmox-guest))
is separate from the VM 300/310 root on purpose. A drift plan for the adopted
guests can therefore never also propose creating VM 330.

## Files

| File | Purpose |
| --- | --- |
| [`services/netbox/ansible/playbooks/`](repo:services/netbox/ansible/playbooks) | Preflight (30), guest config (31), deploy (40), backups (50) |
| [`services/netbox/config/templates/stage-a/compose.yaml.j2`](repo:services/netbox/config/templates/stage-a/compose.yaml.j2) | NetBox Compose project |
| [`services/netbox/config/templates/stage-b/backup.py`](repo:services/netbox/config/templates/stage-b/backup.py) | `pg_dump` plus media, hashed, never pruned |
| [`services/netbox/scripts/netbox_seed_csv.py`](repo:services/netbox/scripts/netbox_seed_csv.py) | Offline CSV seed built from inventory |

## Key code

<!-- snippet: services/netbox/config/templates/stage-b/backup.py lines=66-92 sha=893814501cdd lang=python -->

The dump runs inside the Postgres container as a single
`--serializable-deferrable` transaction. It gets a consistent snapshot without
blocking writers. Output streams straight into gzip without touching disk
uncompressed. A non-zero exit or an empty file is an error, never a silently
truncated backup.

## Operate and recover

```bash
make -C platform/proxmox netbox-preflight     # read-only
make -C platform/proxmox netbox-deploy EXTRA_JSON='{"netbox_allow_deploy":true,"netbox_deploy_confirmation":"DEPLOY NETBOX ON netbox"}'
```

The backup runs at 03:45 and the 04:45 vzdump carries it off the guest. To
restore, load the dump into an isolated VM 330 copy with an empty database,
then compare object counts. That isolated restore and `onboot=1` are still
gated; see [`MEMORY.md`](repo:MEMORY.md).

# Media (workstation)

## Architecture

workstation stays Windows 11 Home. Plex Media Server and qBittorrent run
natively. Radarr, Prowlarr, Recyclarr, the exportarr exporters and Alloy run in
Docker inside `media-vm`, a VirtualBox guest. The library lives on the NAS
`Media` share. Sonarr is not deployed. Running Radarr natively on Windows
would have needed App Control policy changes, which were rejected. The
VirtualBox guest replaced that path.

<!-- diagram: 09-media-flow caption="Media request flow: Radarr and Prowlarr in the guest, qBittorrent and Plex on Windows, library on the NAS" -->

## Files

| File | Purpose |
| --- | --- |
| [`services/media/config/compose.yaml`](repo:services/media/config/compose.yaml) | Digest-pinned container definitions |
| [`services/media/config/cloud-init/`](repo:services/media/config/cloud-init) | Guest first boot (L0) |
| [`services/media/ansible/roles/`](repo:services/media/ansible/roles) | `media_host`, `arr_stack`, `media_backup`, `plex` |
| [`services/media/terraform/arr/`](repo:services/media/terraform/arr) | *arr settings through the devopsarr providers |
| [`services/media/config/recyclarr/`](repo:services/media/config/recyclarr) | Quality profiles ([ADR-0004](repo:docs/decisions/ADR-0004-arr-quality-profiles.md)) |
| [`services/media/scripts/plex_libraries.py`](repo:services/media/scripts/plex_libraries.py) | Plex library plan (plan by default) |

## Key code

<!-- snippet: services/media/config/compose.yaml lines=1-32 sha=6ad5078441a9 lang=yaml -->

Each image is pinned by digest even when its tag is `latest`, so a rebuild gets
the same bytes. Containers drop every capability and add back only `SETUID`
and `SETGID`, which the LinuxServer images need to switch users. Each one has
hard memory, CPU and PID limits. API keys are never in the file; they come from
root-owned env files under `/etc/media/secrets`.

## Operate and recover

```bash
make -C services/media check                 # offline
make -C services/media preflight             # read-only
make -C services/media sync-quality-profiles # Recyclarr --preview unless gated
```

Metrics are pushed from the guest to VM 310
([ADR-0006](repo:docs/decisions/ADR-0006-media-telemetry.md)). The guest sits
behind VirtualBox NAT with loopback-only forwards, so VM 310 cannot scrape it.
workstation also sleeps, so alerts treat an absent series as expected. Radarr's
and Prowlarr's own scheduled backups are copied nightly, append-only, to the
NAS `media-backups` share. Plex's backup task is
behind its own gate.

::: warning
Nothing always-on may live on workstation: it sleeps after five hours on AC. Do
not stop or reconfigure the Docker Desktop `radarr` container there; that
decision is the operator's.
:::

## Music Library

[`services/music-library/`](repo:services/music-library) is a local,
on-demand music library for workstation. It has a PySide6 desktop app and a
FastAPI web companion for other devices on the LAN. It is its own Python
project with its own CI job. Its architecture, legal boundaries and operation
are documented in
[`services/music-library/README.md`](repo:services/music-library/README.md),
which is the single source for that component.

# Observability (VM 310)

## Architecture

VM 310 runs the central stack on `pve1` NVMe: Prometheus (15 days, 8 GiB
cap), Grafana, Loki (seven days), Alertmanager (SMTP through a dedicated
mailbox), Alloy, and node, cAdvisor, blackbox, SNMP and PVE exporters. That is
ten containers, each with a hard memory limit. The Synology is monitored over
SNMPv3 read-only and never hosts observability storage. The PVE exporter uses
a read-only API token and installs nothing on the hypervisors.

<!-- diagram: 10-observability-flow caption="Metrics, logs and alerts: scrape and push paths into VM 310, alerts out by email" -->

## Files

| File | Purpose |
| --- | --- |
| [`observability/docker/compose.yaml`](repo:observability/docker/compose.yaml) | The ten-container stack |
| [`observability/config/prometheus/`](repo:observability/config/prometheus) | Scrape config, file-based targets, alert rules |
| [`observability/config/grafana/`](repo:observability/config/grafana) | Provisioned dashboards (Synology, Proxmox, fleet, availability) |
| [`observability/scripts/backup.sh`](repo:observability/scripts/backup.sh) | TSDB snapshot plus Grafana DB and config archive |
| [`observability/scripts/restore-drill.sh`](repo:observability/scripts/restore-drill.sh) | Validates an archive without touching live data |
| [`observability/ansible/playbooks/`](repo:observability/ansible/playbooks) | Bootstrap (20), deploy (40), dashboard update (41) |

## Key code

<!-- snippet: observability/scripts/backup.sh lines=12-18 sha=26c5411e84de lang=bash -->

Prometheus binds the LAN address, not loopback. A hardcoded `127.0.0.1` made
every nightly backup fail for two weeks with no alert. The script now reads the
same `.env` file Compose uses, so the two cannot drift apart again.

<!-- snippet: observability/scripts/backup.sh lines=76-88 sha=756f75f21e2a lang=bash -->

The freshness metric is written atomically (temporary file, then `mv`), and it
is made world-readable on purpose. The comment records why. The first version
was `0600`, the exporter runs as `nobody`, and the metric never reached
Prometheus. The freshness alert built on it could never fire.

<!-- snippet: observability/config/prometheus/rules/observability.yml lines=51-78 sha=e90d7f4e0fc5 lang=yaml -->

These two rules guard the guard. `absent()` fires if the backup metric
disappears. `node_textfile_scrape_error > 0` fires if any textfile metric
cannot be read. Together they stop the staleness alert from silently becoming
vacuous again. They must never be deleted.

## Operate

```bash
make -C observability check        # offline, includes promtool
make -C observability validate     # read-only runtime checks
make -C observability restore-drill ARCHIVE=/srv/observability/backups/<file>
```

## Recover

The backup runs at 03:30 into `/srv/observability/backups` (root-only, so use
`sudo -n bash -c '…'` for globbing). The 04:15 vzdump carries it off the guest.
Loki history is disposable. Rebuilding means: the guest from L3, the stack from
the gated deploy, and Prometheus and Grafana state from the latest archive.
VM 310 stays `onboot=0` until its restore and onboot gates pass.

# Secrets — OpenBao

## Architecture

Three OpenBao 2.6.1 voters (VMs 320–322), one on each node, form a Raft
cluster. Keepalived holds the VIP 192.168.0.40, where HAProxy terminates HTTP
on port 8200 and re-encrypts to each node over TLS. NPM publishes
`bao.lab.example.com`. TLS is valid everywhere, and the cluster is
deliberately **uninitialized**. Initialization, unsealing and rekeying are
attended ceremonies that no automation performs.

<!-- diagram: 11-openbao-topology caption="OpenBao voters, the Keepalived VIP and the HAProxy front end" -->

## Files

| File | Purpose |
| --- | --- |
| [`security/secrets-openbao/ansible/playbooks/`](repo:security/secrets-openbao/ansible/playbooks) | Prepare (10), install (20), TLS (30), HA (40), validate (50), post-init (60/65), backup (70/90), monitoring (80) |
| [`security/secrets-openbao/openbao/policies/`](repo:security/secrets-openbao/openbao/policies) | Least-privilege policies, applied after init |
| [`security/secrets-openbao/scripts/raft_snapshot.py`](repo:security/secrets-openbao/scripts/raft_snapshot.py) | Encrypted (age) Raft snapshots |
| [`security/secrets-openbao/docs/bootstrap.md`](repo:security/secrets-openbao/docs/bootstrap.md), [`unseal.md`](repo:security/secrets-openbao/docs/unseal.md) | The attended initialization and unseal ceremony |
| [`security/secrets-openbao/docs/restore-runbook.md`](repo:security/secrets-openbao/docs/restore-runbook.md) | Isolated restore |

## Key code

<!-- snippet: security/secrets-openbao/ansible/roles/openbao_cluster/tasks/main.yml lines=90-107 sha=38b91df941ef lang=yaml -->

The validation stage proves two things over verified TLS (the CA path is
pinned): every node answers, and `initialized` is still false. If someone
initialized the cluster, this stage fails rather than carrying on. The
post-init stages are separate playbooks with separate gates.

<!-- diagram: 12-openbao-init-ceremony caption="The attended initialization ceremony: automation stops before init" -->

::: danger
Never run `bao operator init`, `unseal` or `rekey` from automation, CI or an
agent. The guard hook and the Codex rules block the whole `bao operator`
family. D4 schedules the attended ceremony for **2026-10-10**. One operator
owns five PGP keys with separate passphrases in five custody places, threshold
three. This protects against losing any two places, not coercing that operator.
The [ceremony runbook](repo:docs/runbooks/openbao-init-ceremony.md) gives offline
key generation, fingerprint verification, operator commands and separate
post-init gates. The day before requires a verified vzdump archive of each
VM 320–322. The initial root token is revoked after replacement access works.
:::

<!-- diagram: 13-openbao-approle caption="After initialization: an OpenBao Agent renders a secret to a file for the PVE exporter" -->

The first planned integration is the read-only PVE exporter token. It uses a
response-wrapped AppRole SecretID, an Agent that renders the secret to a
`0600` file under `/run`, and a `*_FILE` variable in Compose. No token ever
appears in Git, inventory or Compose.

## Operate and recover

```bash
make -C security/secrets-openbao check                   # offline
make -C security/secrets-openbao validate-uninitialized  # read-only: TLS valid, still uninitialized
make -C security/secrets-openbao recovery-bundle         # secret-free configuration bundle
```

Before initialization there is no data to lose. The hosts are rebuilt from L3
and the gated prepare, install, TLS and HA stages. After initialization,
encrypted Raft snapshots are restored into a protected VM on an isolated bridge
by following the restore runbook. The age identity that decrypts them lives
outside both OpenBao and the NAS.

# AAA — FreeRADIUS

[`security/aaa-freeradius/`](repo:security/aaa-freeradius) holds discovery and a
read-only preflight playbook only. Nothing is deployed. The existing
`aaa-ldap-radius` VirtualBox guest on the operator's Mac has not been
inspected through trusted access. PiVPN has no RADIUS listener. The plan and
its required inputs are in
[`security/aaa-freeradius/docs/aaa-deployment.md`](repo:security/aaa-freeradius/docs/aaa-deployment.md).
RADIUS and LDAP must never be exposed to the Internet.

# Rebuild ladder

The whole lab can be rebuilt from bare metal by climbing nine rungs, L0 to L8.
Each step is one Make target or one manual action, with its own gate, verify
command and rollback. The ladder is data
([`docs/runbooks/rebuild-ladder.yml`](repo:docs/runbooks/rebuild-ladder.yml)),
and both the runbook table and `make rebuild-plan` are generated from it:

<!-- snippet: docs/runbooks/rebuild-ladder.yml lines=10-21 sha=e08c8d0ec49f lang=yaml -->

A step carries its component, its single Make target, the kind of gate
(`local`, `read-only`, `manual`, or a `{flag, confirmation}` pair), the
operator inputs it needs, a verify command and a rollback. Tests check that
every target exists and that no target chains rungs. They also check that every
gate flag and confirmation string really appears in the source.

<!-- diagram: 06-rebuild-ladder caption="Rungs L0 to L8, from bare metal to validated onboot" -->

The runbook is included here unchanged. It is the single source for the
procedure:

<!-- include: docs/runbooks/rebuild-from-zero.md shift=1 -->

# CI checks

## Pipeline

GitHub runs offline checks on hosted runners with no lab credentials.
Plans and deployments run locally from the devcontainer, one gated stage
at a time; there is no GitHub runner inside the lab (ADR-0009).

<!-- diagram: 15-cicd-pipeline caption="GitHub checks end at review; the operator runs gated local stages" -->

<!-- snippet: .github/workflows/ci.yml lines=1-15 sha=328e7d42ab6f lang=yaml -->

`permissions: {}` at the top means every job must ask for exactly the scopes it
uses. The `on:` key is quoted so YAML 1.1 parsers do not read it as `true`.
Every action is pinned by full commit SHA, which a contract test enforces.

## Local operations

The operator reviews the change, then runs its existing local Make target
with the exact gate. GitHub supplies neither approvals nor credentials.

<!-- include: docs/runbooks/ci-cd.md shift=1 -->

## Publishing and documentation

A sanitised public copy is produced by [`tools/publish/`](repo:tools/publish)
(Phase 6). Its origin is the approved public repository. This document is built by
[`tools/docs-build/build.py`](repo:tools/docs-build/build.py) from Markdown,
Mermaid sources and the generated reference. The build fails on any warning,
broken link or anchor, or changed snippet source.

<!-- diagram: 16-publish-pipeline caption="From private source to the sanitised public copy and this PDF" -->

# On-demand music library

The private [Music Library app](repo:services/music-library/README.md) runs
on demand on workstation. Completed downloads are checksum-verified into the
user's Music folder and NAS Media/Music. Tempo is estimated locally and used
for ten-BPM range folders; unavailable analysis uses Unknown BPM. A sortable
BPM column and editable metadata expose the result. Tempo estimation can
report half/double tempo, so the operator can correct it.

The prior packaged app saved downloads inside its bundle instead of the user
Music folder. Three existing tracks now have verified copies in both
destinations. The desktop launcher targets the new BPM bundle; close the
old app, restart, and use Organize by BPM once to redirect its existing
catalog to those copies. Existing song originals and the only live catalog
remain preserved. This app's source is withheld from the public reading copy.

# Backup and restore

Every stateful item has a source, a destination, a schedule, a restore method
and a verify step. Restores always go to an isolated guest first: a spare
protected VMID with every NIC link-down. Nothing prunes. Destinations are
append-only, and Proxmox storage is `keep-all=1`.

<!-- diagram: 14-backup-restore caption="NAS backups, the approved read-only D: pull copy, and isolated restore paths" -->

The [D3 pull stage](repo:platform/proxmox/docs/backup-pull.md) restricts one
key to list/get on the NAS-mounted archive directory of one confirmed node.
workstation initiates SSH and verifies hashes before publishing each D: copy;
its daily task catches missed starts while awake, never wakes the PC and
stops below a 100 GB reserve. The exact pve1 installation confirmation was
supplied on 2026-09-30. The public key and all three host pins were verified;
the gated preflight confirmed pve1 as the least-loaded mounted node. The
operator ran that one stage with an interactive password prompt, installing
the server and restricted key. The Windows task is installed. Accept each
D: copy only after its SHA-256 matches the NAS before and after the pull;
registration or a running task alone does not prove that acceptance.
Copies are never pruned. D: is a second on-site copy exposed to desktop
ransomware. Future off-site data transfer must be an outbound push; GitHub
has no path into the lab (ADR-0009).

::: danger
Never delete or prune a backup archive, and never restore over a live VMID.
The two archives of VM 297 (`ubuntu-vm`, destroyed on or before 2026-09-19) are the only remaining copy of
that guest and must be kept.
:::

<!-- include: docs/reference/generated/backups.md shift=1 -->

# Troubleshooting

| Symptom | Likely cause | First response |
| --- | --- | --- |
| A stage fails immediately with "Set … to the exact string" | Gate not passed, or the confirmation differs by a character | Copy the expected string from [Appendix C](#appendix-c-approval-gates); pass it in `EXTRA_JSON` |
| Approval set but destructive tasks skipped | `--tags all,destructive` missing | Use the Make target, which passes the tags |
| SSH fails with a changed host key | Cloud-init re-ran on a stopped guest, or a reinstall | Verify through `qm guest exec … ssh-keygen -lf`; the operator re-pins |
| Private names fail on a guest, public names work | NAS DNS down, or the routing-domain drop-in missing | Check `resolvectl status`; never point the guest wholesale at the NAS |
| A freshness alert never fires | Its input series does not exist | Query the metric first; check `node_textfile_scrape_error` |
| Backup timer failed for days, no alert | Unit failure is not a metric | Check `journalctl -u <timer>`; the freshness metric covers it now |
| `make docs` fails with "snippet … changed" | The source lines moved or changed | Review the new lines, fix the range, run `build.py --fill` |
| CI `inventory contract` fails | A live identity changed in one place only | Change `inventory/lab.yml` and the consumer together |

The facts behind most of these rows were learned against the live hosts. They
are recorded once, in the lessons-learned reference, included here:

<!-- include: docs/reference/lessons-learned.md shift=1 -->

# Glossary

| Term | Meaning |
| --- | --- |
| Allow flag | A boolean such as `netbox_allow_deploy`; defaults `false` |
| Confirmation | An exact string, often embedding the host, that must match before a stage runs |
| `EXTRA_JSON` | The Make variable that carries approvals as JSON to `ansible-playbook -e` |
| Import-first | An OpenTofu root that adopts existing guests with `import` blocks before managing them |
| Rebuild-only root | A create-mode OpenTofu root used only after total loss ([ADR-0007](repo:docs/decisions/ADR-0007-rebuild-only-guest-root.md)) |
| Rung | One level (L0–L8) of the rebuild ladder |
| Routing domain | A systemd-resolved `~domain` that sends only that zone to a given server |
| `keep-all=1` | Proxmox prune policy that retains every archive |
| Isolated restore | A restore into a spare protected VMID with every NIC link-down |
| vzdump | Proxmox's whole-guest backup; archives are `.vma.zst` |
| VIP | The Keepalived virtual address (192.168.0.40) in front of OpenBao |
| Ratchet | A list of accepted exceptions that tests only allow to shrink |
| Split horizon | The lab zone resolves only inside the LAN, from the NAS |

# Appendix A: Make targets

Generated from every `Makefile` by
[`tools/docs/generate_reference.py`](repo:tools/docs/generate_reference.py).
Targets without help text print `—`.

<!-- include: docs/reference/generated/make-targets.md shift=1 -->

# Appendix B: Workflows

<!-- include: docs/reference/generated/workflows.md shift=1 -->

# Appendix C: Approval gates

<!-- include: docs/reference/generated/gates.md shift=1 -->

# Appendix D: Operator inputs

<!-- include: docs/reference/operator-inputs.md shift=1 -->

# Appendix E: Versions and counts

<!-- include: docs/reference/generated/versions.md shift=1 -->

<!-- include: docs/reference/generated/counts.md shift=1 -->
