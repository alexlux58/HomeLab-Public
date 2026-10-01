# NetBox placement plan

Status: **placement approved 2026-08-25; nothing applied.** No NetBox VM,
container, database, DNS record, proxy route, or backup job exists. Read-only
discovery was performed on 2026-08-25 and nothing was mutated. The staged
automation described under "Automation status" has been written, linted, and
tested offline, but no `terraform apply` and no playbook has been run.

The old `pve2` guest 102 `UbuntuServer2` carried a snapshot named
`Netbox-Nautobot-2026`. That is a rebuild hint recorded in
[rebuild-catalog.md](rebuild-catalog.md), **not** a backup. There is no NetBox
data to restore. Any deployment is a fresh build.

## What NetBox actually needs

NetBox is not a single stateless container. A supportable deployment is:

| component | purpose | approximate RAM |
|---|---|---:|
| `netbox` (gunicorn) | web/API | 768 MiB–1 GiB |
| `netbox-worker` | background RQ jobs | 256–384 MiB |
| `netbox-housekeeping` | scheduled cleanup | 128 MiB |
| `postgres` | the source of truth | 512 MiB–1 GiB |
| `redis` (cache) | caching | 64–128 MiB |
| `redis` (tasks) | RQ queue; must be a separate instance | 64–128 MiB |

Steady state is roughly **2–3 GiB RAM**, with the working set dominated by
PostgreSQL. It also needs persistent media/scripts/reports volumes, a real
`pg_dump`-based application backup (a file-level copy of a running PostgreSQL
data directory is not a backup), HTTPS, a DNS record, and a restore drill.

## Measured capacity, 2026-08-25

Read from `pvesh get /cluster/resources`, `free -h`, `pvesm status`, `lsblk`,
and `vgs`/`lvs` on the live cluster.

| node | cores | RAM total / used | guest RAM committed | local storage |
|---|---:|---|---|---|
| `pve1` | 12 | 31.2 / 11.2 GiB | 31.4 GiB if 290, 297, and 310 all run | `local` dir 460 GiB, 163 GiB free |
| `pve2` | 8 | 11.5 / 7.6 GiB | 6 GiB running (VM 300) + 6 GiB if VM 399 ever starts | `local-lvm` 794 GiB thin on **HDD** |
| `pve3` | 4 | 7.6 / 1.7 GiB, 6.0 GiB available | **0 — no guests** | `local-lvm` 49.6 GiB thin, 0% used, on a 112 GiB **SSD**; VG `pve` has 13.75 GiB unallocated |

## Placement verdict

**Recommended: a new dedicated, protected VM on `pve3`.**

Why the alternatives are rejected:

- **VM 300 `homelab-services`** — it lives on `pve2`, whose only storage is a
  932 GiB spinning disk. NetBox's PostgreSQL is the most I/O-sensitive workload
  proposed for this lab, and VM 300 is deliberately a lightweight utility VM
  with 6 GiB total. Adding 2–3 GiB of database would leave almost no headroom on
  an 11.5 GiB node and would put a transactional database on an HDD.
  `rebuild-catalog.md` already recorded this conclusion.
- **VM 310 `observability`** — capped at 4 GiB precisely because VMs 290 and 297
  can together reserve 28 GiB on `pve1`. It has about 3.76 GiB usable and runs
  ten containers. There is no room, and mixing an IPAM source of truth into the
  monitoring VM couples two independent recovery domains.
- **`pve1`** — already committed to 31.4 GiB of 31.2 GiB if both protected
  guests and VM 310 run. Adding anything requires re-auditing VM 290/297 first.
- **`pve2` as a second VM** — same HDD problem, and only about 4 GiB of
  uncommitted RAM once VM 300 is accounted for.

`pve3` is the only node with an SSD, zero guests, and free RAM.

## Proposed shape (not provisioned)

| item | proposed value | note |
|---|---|---|
| VMID | `330` | 320–322 are reserved for the planned OpenBao voters |
| node | `pve3` | SSD-backed `local-lvm` |
| name | `netbox` | |
| resources | 2 vCPU, 3 GiB fixed RAM, 32 GiB disk | measured against the node's 6.0 GiB available |
| address | candidate `192.168.0.50/24` | probed 2026-08-25; nothing responded. Needs an the router reservation before first boot |
| MAC | to be generated | must be verified unique against all cluster guests |
| policy | `protection=1`, `onboot=0` until backup and restore gates pass | same gate discipline as VMs 300 and 310 |
| DNS | explicit `netbox.lab.example.com` A record on Synology | see the warning below |
| TLS | NPM proxy host on VM 300 with the existing wildcard certificate | |

### RAM budget on `pve3`

6.0 GiB available today. Planned OpenBao voter 321 takes 2 GiB, NetBox takes
3 GiB. That is 5 of 6 GiB with no margin for a third workload. Deploy one, then
re-measure before the other; do not assume both fit simultaneously without
checking.

### Disk budget on `pve3`

`local-lvm` is a 49.6 GiB thin pool with 0% used. NetBox at 32 GiB plus the
planned 24 GiB OpenBao voter is 56 GiB provisioned — over the pool. The pool is
thin, so both can be *created*, but the pool would need the 13.75 GiB of
unallocated VG extents before both are genuinely safe to fill. Decide this
before creating the second guest, not after.

### DNS warning

Wildcard `*.lab.example.com` currently resolves `netbox.lab.example.com` and
`ipam.lab.example.com` to `192.168.0.30` (VM 300), verified against the
Synology DNS server on 2026-08-25. This is the same defect already recorded for
`bao.lab.example.com`. An explicit A record is required before NetBox exists,
otherwise the name silently reaches NPM's fallback page. Until then the Homepage
NetBox card intentionally carries **no** `href` and **no** `siteMonitor`.

## Staged gates, in order

Each stage is run and reviewed separately. None of this is automated yet.

1. **Placement approval.** Confirm `pve3`, VMID 330, 2 vCPU / 3 GiB /
   32 GiB, and the address. Nothing below starts until this is agreed.
2. **Reservations and trust.** the router reservation for the generated MAC, a
   dedicated `~/.ssh/homelab_netbox_ed25519` key, and explicit Synology DNS
   records for `netbox.lab.example.com`.
3. **Terraform.** Add a create-mode guest resource with `prevent_destroy`,
   `purge_on_destroy = false`, and `delete_unreferenced_disks_on_destroy =
   false`. Review `make terraform-plan` output. Apply remains manual and
   separately approved — this repository has no apply target and must not gain
   one.
4. **Image and first boot.** Verify Canonical's signed Ubuntu 24.04 image and
   SHA-256, import, inject only the dedicated public key, boot, and verify the
   guest SSH host fingerprint through the QEMU guest agent before trusting it.
5. **Base hardening.** Reuse the VM 300/310 pattern: key-only SSH, LAN-only UFW,
   bounded journal, swappiness 10, swap, unattended upgrades, QGA, weekly trim,
   then a persistence reboot.
6. **Application.** One gated Ansible run installing a pinned Compose project.
   `SECRET_KEY`, the PostgreSQL password, and the superuser password are
   root-owned mode-0600 runtime files, never in Git or inventory.
7. **DNS and TLS.** Explicit Synology record, then an NPM proxy host with the
   wildcard certificate and forced HTTPS. Only then does the Homepage card gain
   an `href` and a `siteMonitor`.
8. **Backups.** A `pg_dump`-based application-aware archive with a detached
   SHA-256 manifest and an append-only Synology target, plus a daily Proxmox
   VM backup with `keep-all=1`.
9. **Restore proof.** Isolated restore to a spare VMID with a unique MAC and
   `link_down=1`, verifying the database actually loads. Only after this passes
   does VM 330 get `onboot=1`.
10. **Observability.** Add the NetBox blackbox target and a Homepage card, and
    move the entry out of the "Planned and recovery" group.

## Automation status

Placement was approved on 2026-08-25, so the staged automation now exists. **It
has never been run.** No `terraform apply`, no playbook, no container.

| artifact | path | state |
|---|---|---|
| Terraform root | `terraform/netbox-guest/` | `init`/`validate`/`fmt` pass; never planned against the live cluster, never applied |
| Inventory | `inventory/netbox.yml` | target shape only; the host does not resolve or exist |
| Preflight | `playbooks/30-preflight.yml` | read-only |
| Guest base | `playbooks/31-configure-guest.yml` | reuses the proven `homelab_guest_base` role |
| Application | `playbooks/40-deploy.yml` + `roles/netbox_app` | gated by an approval flag and exact confirmation |
| Backups | `playbooks/50-configure-backups.yml` + `roles/netbox_backup` | installs the `pg_dump` program and a 03:45 timer |
| Backup program | `templates/netbox/stage-b/backup.py` | standard library only; never prunes |
| Compose model | `templates/netbox/stage-a/compose.yaml.j2` | six containers, hard memory limits summing to 2,208 MiB |

Commands, one reviewed stage at a time:

```bash
make netbox-terraform-init
make netbox-terraform-fmt
make netbox-terraform-validate
make netbox-terraform-plan        # apply stays a manual operator action
make netbox-preflight
make netbox-base
make netbox-deploy EXTRA_JSON='{"netbox_app_allow_first_deployment":true,"netbox_app_first_deployment_confirmation":"DEPLOY NETBOX ON VM 330"}'
make netbox-backups
```

There is no aggregate NetBox target, and a repository test fails the build if
one is added.

### Two values that must be confirmed before the first deployment

1. **Image pins.** `roles/netbox_app/defaults/main.yml` carries provisional tags
   for NetBox, PostgreSQL, and Redis. Confirm the current upstream release and
   record the chosen tags before stage 6. A wrong tag fails the pull loudly
   rather than deploying something unreviewed.
2. **The MAC and address.** `52:54:00:00:00:00` and `192.168.0.50` are proposed,
   verified unique against every current cluster guest and the planned OpenBao
   MACs, and probed as unused — but the the router reservation does not exist yet.

### Secrets

`/etc/netbox/secrets/netbox.env` and `/etc/netbox/secrets/netbox-postgres.env`
are root-owned mode-0600 files the operator installs. Ansible checks only their
metadata: existence, regular file, mode 0400/0600, non-empty. It never generates,
reads, prints, or commits a value. The NetBox `SECRET_KEY`, the PostgreSQL
password, and the superuser password live only in those files and the operator's
encrypted backup.
