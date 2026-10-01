# Migration runbook

Execute one stage at a time. Read the artifact each stage produces before
starting the next one. There is no command in this repository that runs the whole
migration, and there will not be.

## Conventions

* `EXTRA_JSON='{"key":"value"}'` safely passes approval variables, including
  multi-word confirmation strings, to Ansible. Approval flags are never committed.
  `EXTRA="..."` remains available for simple single-word arguments.
* Destructive stages additionally require `--tags all,destructive`, which the
  relevant `make` targets already pass.
* Anything marked **MANUAL** is done by a human at a console, on purpose.

## Prerequisites

* [ ] macOS controller with Python 3.9+, `make`, and `git`.
* [ ] `~/.ssh/proxmox_cluster_ed25519` exists, mode `600`, and is already
      authorised on all three hosts. (It is — see the environment notes.)
* [ ] `~/.ssh/config` has the `pve1` / `pve2` / `pve3` aliases.
* [ ] Physical, IPMI or iKVM console access to **all three** hosts. Non-negotiable
      for stages 5, 6 and 9.
* [ ] The Synology share exists per [docs/synology-nfs-setup.md](../../nas/docs/synology-nfs-setup.md).
* [ ] A Proxmox VE 9.2 ISO, checksum verified, on a USB stick.
* [ ] Time: budget a full day, or split across two maintenance windows (see below).

```bash
git clone <this repo> && cd proxmox-cluster-migration
make setup          # creates .venv and installs ansible-core, linters, pytest
make lint test      # offline; proves the tooling works before you point it at anything
```

## Maintenance windows

| window | stages | guest downtime | risk |
|---|---|---|---|
| W0 — any time | 0, 1, 2, 3 | **none** (live snapshot backups) | none |
| W1 — 2–4 h | 4, 5 | `.11` guests remain stopped after the final backup; `.13` guests destroyed | low |
| W2 — 3–5 h | 6, 7, 8 | `.11` guests down for the upgrade + reboot | **high** — irreversible upgrade |
| W3 — 2–4 h | 9, 10 | `.12` guests are already stopped and are deliberately discarded | **high** — `.12` is wiped |

Do not merge W2 and W3. Sleep between them and let the cluster run.

---

## Stage 0 — validate access and discover (read-only)

```bash
make validate-ssh
```

Expected: three hosts, each reporting its hostname, `pveversion`, and a
fingerprint matching `../../inventory/hosts.yml`. Any mismatch stops the run — that is
the feature, see [reinstall-ssh-recovery.md](reinstall-ssh-recovery.md).

Manual equivalent:

```bash
ssh pve1 'hostname; pveversion'
ssh pve2 'hostname; pveversion'
ssh pve3 'hostname; pveversion'
ansible -i ../../inventory/hosts.yml proxmox -m ansible.builtin.ping
```

```bash
make discover
```

Produces `artifacts/discovery.json`, `discovery.md`, `vmid-collisions.json`,
`storage-capacity.json`.

* [ ] **Read `artifacts/discovery.md` end to end.** This is the last point where
      surprises are cheap.
* [ ] Confirm the only protected guests are `.11` VMID 290 EVENG and VMID 297 ubuntu-vm.
* [ ] Note every guest flagged `**BACKUP=0**` or `**BIND-MOUNT**`.
* [ ] Note EVE-NG's (290) CPU type, machine type, `args`, and the host's
      `kvm_nested` value.
* [ ] Review `vmid-collisions.json`: every collision must be marked
      `resolves_on_rebuild`, because `.12` and `.13` both join empty.
* [ ] Review `docs/rebuild-catalog.md`; it is the record of software to rebuild,
      not a backup of those eight guests.

## Stage 1 — Synology preflight

```bash
make nas-preflight
```

Aborts if the export is missing, read-only, slow, too full, resolves under
`/volume2`, or is not actually an NFS mount. Then register the storage:

```bash
make nas-preflight EXTRA="-e allow_configure_nfs_storage=true"
```

* [ ] `artifacts/storage-capacity.json` verdict is `pass`.
* [ ] `pvesm status` on each host shows `synology-backup` active.

## Stage 2 — capture host configuration

```bash
make capture-config
```

* [ ] `host-configs/pve1/latest/` and `host-configs/pve2/latest/` exist.
* [ ] `files/etc/network/interfaces` is present and correct for both.
* [ ] `files/var/lib/vz/snippets/` contains every hook script you rely on.
* [ ] No private key material — the role fails the play if it finds any.

## Stage 3 — initial backup (guests stay running)

```bash
make backup-initial HOST=pve1
```

`.12` and `.13` are refused because none of their current guests is protected.

* [ ] EVENG is stopped. Keep its nested lab nodes stopped through the final backup.

## Stage 4 — final backup (guests cleanly stopped)

```bash
make verify-backups-initial

make backup-final HOST=pve1 EXTRA_JSON='{"allow_guest_shutdown":true,"guest_shutdown_confirmation":"SHUTDOWN GUESTS FOR FINAL BACKUP"}'

make verify-backups
```

* [ ] `artifacts/power-state-pve1.json` exists — this is how you
      put the guests back if you stop here.
* [ ] `artifacts/backup-verification.json` verdict is `pass` and
      `counts.equal` is `true`: **2 guests × 2 generations = 4 verified archives**.
* [ ] Every archive was verified with `zstdcat … | vma verify -v -` under
      `set -o pipefail`, with the full pipeline status checked.

`.11`'s guests can be restarted if the migration pauses. Leave `.12` stopped
so the reviewed discard list does not drift before its clean install.

## Stage 5 — rebuild .13 empty

```bash
make prepare-pve3        # writes artifacts/pve3-clean-install-checklist.md, then stops
```

**MANUAL** — follow the checklist:

* [x] Install Proxmox VE 9.2 from the ISO. Hostname `pve3`, IP `192.168.0.13/24`.
* [ ] Read the new fingerprint **at the console**, verify, clean `known_hosts`,
      accept once, reinstall the existing public key, update `../../inventory/hosts.yml`.

```bash
make prepare-pve3 EXTRA="-e pve3_reinstalled=true \
  -e pve3_fingerprint_verified=true -e allow_configure_nfs_storage=true"
```

* [ ] `.13` has zero guests. No temporary restore/delete is performed: neither
      protected `.11` guest fits safely on `.13` after reinstall.

## Stage 6 — upgrade .11 in place

```bash
make precheck-upgrade-pve1
```

* [ ] Read `artifacts/upgrade-precheck-pve1.md`.
* [ ] `pve8to9 --full` reports **0 failures and 0 warnings**. Fix each one at
      source; do not waive them.
* [ ] Decide enterprise vs no-subscription; do not run both.
* [ ] Disable third-party repositories for the duration.

**Have console access open before running the next command.**

```bash
make upgrade-pve1 EXTRA_JSON='{"allow_repo_change_pve1":true,"repo_change_confirmation_pve1":"CHANGE REPOSITORIES pve1 192.168.0.11","allow_upgrade_pve1":true,"upgrade_confirmation_pve1":"UPGRADE pve1 192.168.0.11 TO PVE 9","console_access_confirmed_pve1":true}'
```

This brings PVE 8 to the latest 8.4, re-runs `pve8to9`, shuts every guest down,
rewrites the repositories to Trixie, `dist-upgrade`s, and reboots.

After it returns:

* [ ] `artifacts/upgrade-diff-pve1.md` shows **no regressions**.
* [ ] `ip -br a`, `ip route`, ping the gateway.
* [ ] `pvesm status` — every storage active.
* [ ] `qm list` — both protected guests registered.
* [ ] `cat /sys/module/kvm_intel/parameters/nested` is `Y` before starting EVE-NG.
* [ ] Start guests **one at a time**, checking each before the next.

## Stage 7 — create the cluster

```bash
make create-cluster EXTRA_JSON='{"allow_create_cluster":true,"create_cluster_confirmation":"CREATE CLUSTER homelab ON pve1 192.168.0.11"}'
```

* [ ] `pvecm status` — `Quorate: Yes`.
* [ ] Both `.11` guests still registered (the play asserts this and diffs
      pre/post state into `artifacts/cluster-create-diff.md`).
* [ ] Storage definitions unchanged. HA still disabled.

## Stage 8 — join .13

```bash
make join-pve3 EXTRA_JSON='{"allow_join_pve3":true,"join_confirmation_pve3":"JOIN pve3 192.168.0.13 TO homelab","pve3_fingerprint_verified":true}'
```

By default the join is **MANUAL**: the play performs every precondition check,
prints the exact command, and stops. Run it on `.13`:

```bash
ssh pve3
pvecm add 192.168.0.11 --link0 192.168.0.13
```

You are prompted for `.11`'s root password. That password is yours and is never
handled by this automation — this is why the step is not automated. Then:

```bash
make join-pve3 EXTRA_JSON='{"allow_join_pve3":true,"join_confirmation_pve3":"JOIN pve3 192.168.0.13 TO homelab","pve3_fingerprint_verified":true,"pve3_join_executed":true}'
```

* [ ] Two members, quorate.
* [ ] `.13`'s SSH host key changed again (cluster-signed). Re-verify and update
      `../../inventory/hosts.yml`.

> Optional automated path: `-e join_method=ssh_key_trust` authorises the joining
> node's **existing** root key on the seed and installs the seed's host key —
> read from the seed over an already-authenticated channel, never blindly
> accepted — so `pvecm add --use_ssh` needs no password. Use it only if you
> understand what it changes.

## Stage 9 — rebuild .12 and join it

```bash
make precheck-destroy-pve2
```

Seven gates must pass. Read `artifacts/destroy-pve2-proposal.md`.

**MANUAL** — this automation never wipes a machine over SSH:

* [ ] Confirm the exact five `.12` guests match `docs/rebuild-catalog.md` and
      are still stopped. They have no migration backup and will not be restorable.
* [ ] Clean-install Proxmox VE 9.2. Hostname `pve2`, IP `192.168.0.12/24`.
* [ ] Recreate the bridges to match
      `host-configs/pve2/latest/files/etc/network/interfaces`.
* [ ] Verify the new SSH fingerprint at the console, reinstall the existing
      public key, update `../../inventory/hosts.yml`.

```bash
make postinstall-pve2 EXTRA_JSON='{"allow_destroy_pve2":true,"destroy_confirmation_pve2":"DESTROY pve2 192.168.0.12 AND DISCARD ALL FIVE GUESTS","pve2_reinstalled":true,"pve2_fingerprint_verified":true,"allow_configure_nfs_storage":true}'

make join-pve2 EXTRA_JSON='{"allow_join_pve2":true,"join_confirmation_pve2":"JOIN pve2 192.168.0.12 TO homelab","pve2_fingerprint_verified":true}'
# ... run `pvecm add` manually as in stage 8, then re-run with
#     -e pve2_join_executed=true
```

* [ ] Three members, `Total votes: 3`, `Quorate: Yes`.

## Stage 10 — validate

```bash
make validate
make discover        # refresh the snapshot with the final state
```

* [ ] Three online nodes, quorum, corosync rings connected.
* [ ] Every storage active; `synology-backup` visible from all three nodes.
* [ ] VMIDs and MACs unique cluster-wide.
* [ ] Both protected guests accounted for; `.12` and `.13` are empty.
* [ ] Guest agents responding; DNS and gateway reachable.
* [ ] EVE-NG nested virtualisation available on its node.
* [ ] Read `artifacts/migration-report.md`, especially the section on what
      clustering does **not** give you.
* [ ] Begin rebuilding services from `docs/rebuild-catalog.md` only after the
      cluster is stable.

## After the migration

* [ ] Configure a scheduled backup job (Datacenter → Backup) to `synology-backup`.
      The migration deliberately leaves scheduling to you so no job fires mid-run.
* [ ] Plan for 3-2-1 and Proxmox Backup Server — see the README.
* [ ] Investigate the Storage Pool 1 health warning on the Synology.
