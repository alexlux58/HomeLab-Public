# Rollback procedures

Every change to protected `.11` data has a recovery path. The way back is almost
never "undo" — it is "restore from an archive that was never deleted". This
project never prunes, configures retention, or removes a backup. The eight
rebuild-later guests are an explicit exception: their software is cataloged, but
their old disks are intentionally not recoverable after clean installation.

## Rollback matrix

| stage | what changed | how to get back |
|---|---|---|
| 0 discovery | nothing | nothing to undo |
| 1 NAS preflight | a transient mount, one test file (removed) | nothing to undo |
| 1b NFS storage added | one storage definition | `pvesm remove synology-backup` |
| 2 config capture | files written under `/root/.pve-migration` on the host | delete that directory |
| 3 initial backup | archives written to the NAS | keep them; they cost space, not risk |
| 4 final backup | **guests were shut down** | `qm start <vmid>` for each guest listed as `running` in `artifacts/power-state-<host>.json` |
| 5 .13 wiped | .13 lost its 3 disposable guests | accepted by design; nothing to recover |
| 6 .11 upgraded | **irreversible** — no supported PVE 9 → 8 downgrade | reinstall .11 with PVE 9.2 and restore its guests from the verified archives |
| 7 cluster created | `.11` became a one-node cluster | see "Undoing cluster creation" below |
| 8 .13 joined | `.13` is a member; its `/etc/pve` was overwritten | `pvecm delnode pve3` on the seed, then clean-install .13 again |
| 9 .12 rebuilt | **.12 wiped** | its old guests cannot be restored; rebuild desired software from `docs/rebuild-catalog.md` |
| 10 validation | nothing | nothing to undo |

## Pausing the migration after stage 4

Stage 4 shuts guests down. If you decide to stop there and go back to normal
service:

```bash
cat artifacts/power-state-pve1.json
# for every vmid whose state is "running":
ssh pve1 'qm start <vmid>'
```

Nothing else is required. The archives on the NAS stay where they are, and you can
resume later by re-taking the final generation so it is the newest again.

## Undoing cluster creation on the seed

There is no `pvecm uncreate`. If you must return `.11` to standalone:

1. Stop the cluster services:

   ```bash
   systemctl stop pve-cluster corosync
   ```

2. Start `pmxcfs` in local mode so `/etc/pve` is writable without quorum:

   ```bash
   pmxcfs -l
   ```

3. Remove the corosync configuration:

   ```bash
   rm /etc/pve/corosync.conf
   rm -r /etc/corosync/*
   ```

4. Restart:

   ```bash
   killall pmxcfs
   systemctl start pve-cluster
   ```

Guest configurations under `/etc/pve/qemu-server` are untouched by this. Verify
with `qm list` immediately afterwards.

> This is the one procedure in this repository that uses `rm -r`, and it is
> documented here as a manual recovery step rather than automated, because
> deleting things under `/etc/pve` by script is how clusters get destroyed.
> It comes from the Proxmox Cluster Manager chapter's "separate a node without
> reinstalling" guidance — read it before you run it:
> <https://pve.proxmox.com/wiki/Cluster_Manager>

## Removing a joined node

On a **surviving, quorate** node:

```bash
pvecm delnode <nodename>
```

The removed node must never be powered back on while still holding the old
corosync configuration — it must be clean-installed before it rejoins. Do not
attempt to "un-join" a node by editing `/etc/pve` by hand.

## If quorum is lost

Do **not** reach for `pvecm expected 1`. It is a foot-gun that lets a minority
partition write to `/etc/pve`, and recovering from two divergent copies of the
cluster filesystem is much worse than a night of downtime.

Instead:

1. `corosync-cfgtool -s` on each reachable node — are the rings connected?
2. `journalctl -u corosync -u pve-cluster -n 200`
3. Check the physical link, the switch, and that every node's hostname still
   resolves to its own address.
4. Bring the missing node back. Quorum returns on its own.

Use `pvecm expected` only as a deliberate, last-resort recovery action on a node
you have decided is the survivor, with the others powered off — never as a routine
workaround.

## Rebuilding .11 from scratch (worst case)

If the in-place upgrade leaves `.11` unbootable:

1. Boot the PVE 9.2 ISO and clean-install with hostname `pve1`, IP
   `192.168.0.11`.
2. Recover SSH access — [docs/reinstall-ssh-recovery.md](reinstall-ssh-recovery.md).
3. Reapply the captured host configuration by hand from
   `host-configs/pve1/latest/files/` — bridges first, then storage, then
   `/etc/modprobe.d` and the GRUB cmdline for VFIO/IOMMU.
4. Re-add the NFS storage: `make nas-preflight EXTRA="-e allow_configure_nfs_storage=true"`.
5. Restore its guests from `artifacts/backup-manifest.json` with their original
   VMID 290. (VMID 297 was destroyed on 2026-09-19 after the operator
   confirmed it obsolete. Its two archives are retained permanently and must
   never be deleted, but it is not restored as part of a rollback.)
6. Re-verify EVE-NG's nested virtualisation and any passthrough devices before
   starting VMID 290.

This restore path protects `.11` only. Stage 9 intentionally does not preserve
or restore `.12` guest disks.

## What is never rolled back

* Backup archives are never deleted by this project — not on failure, not on
  success, not by a retention policy.
* The five `.12` and three `.13` rebuild-later guests. Their software is
  cataloged, but their disks are intentionally outside the migration backup set.
