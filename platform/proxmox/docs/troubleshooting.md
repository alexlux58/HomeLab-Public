# Troubleshooting decision tree

Start at the symptom. Every branch ends in either a fix or "stop and do not
proceed" — the second is a valid outcome.

## A. Ansible cannot reach a host

```text
make validate-ssh fails
├─ "Permission denied (publickey)"
│  ├─ Did the host just get clean-installed or join the cluster?
│  │  └─ YES → authorized_keys was wiped/replaced.
│  │           Reinstall the EXISTING public key → reinstall-ssh-recovery.md §5
│  └─ NO  → check the key on the controller:
│           ls -l ~/.ssh/proxmox_cluster_ed25519   (must be 600)
│           ssh -v -i ~/.ssh/proxmox_cluster_ed25519 -o IdentitiesOnly=yes root@<ip>
│
├─ "SSH HOST KEY MISMATCH" from the ssh_validation role
│  ├─ Expected (reinstall / cluster join) → verify at the CONSOLE, then
│  │  reinstall-ssh-recovery.md §1–6. Never accept it blindly.
│  └─ Unexpected → STOP. Do not connect again until you know why.
│
├─ Hangs, then times out
│  └─ Host down, wrong IP, or a firewall. ansible.cfg uses BatchMode=yes, so a
│     password prompt fails rather than hangs — a hang is a network problem.
│
└─ "reports hostname 'X' instead of 'Y'"
   └─ You are talking to the wrong machine, or the inventory is wrong. Do not
      "fix" this by changing expected_hostname without checking which it is.
```

## B. The Synology preflight fails

```text
make nas-preflight fails
├─ "does not advertise /volume1/proxmox-cluster-backups"
│  ├─ NFS service disabled → synology-nfs-setup.md §2
│  └─ No NFS rule for THIS host's IP → §4 (one rule per host, three rules total)
│
├─ "is NOT a healthy NFS mount ... would silently fill the local root filesystem"
│  └─ The mount failed but the directory exists. This is the failure mode the
│     whole check exists for. Fix the export; never write backups to /mnt/pve/<id>
│     while it is not mounted.
│
├─ "touches '/volume2'"
│  └─ The share was created on the wrong volume. Volume 2 is on Storage Pool 1,
│     which has 0 bytes free and a health warning. Recreate on Volume 1. STOP.
│
├─ "mounted read-only"
│  └─ NFS rule privilege is Read-only, or DSM put the volume in read-only mode
│     after a filesystem error. Check Storage Manager before changing the rule.
│
├─ "Measured N MiB/s ... below the floor"
│  └─ "Enable asynchronous" is off, the link is 100Mb, or the NAS is busy
│     scrubbing. Fix it — a 400 GiB backup at 5 MiB/s is a 24-hour window.
│
└─ "Only N GiB free"
   └─ Read artifacts/storage-capacity.json. Free space, or reduce scope. Do not
      lower nas_min_free_gib to make the check pass.
```

## C. A backup fails or is refused

```text
make backup-initial / backup-final fails
├─ "have backup=0 and will NOT be included"
│  └─ A disk is excluded from vzdump. Either enable the backup flag, or copy that
│     disk's data another way and re-run with -e vzdump_accept_excluded_disks=true
│     ONLY after you have actually protected it.
│
├─ "bind/device mounts, whose contents are NEVER in a vzdump archive"
│  └─ Same reasoning. rsync the data off, then
│     -e vzdump_bind_mounts_protected=true
│
├─ "No captured host configuration found"
│  └─ Run `make capture-config` first. Snippets and bridges are not in archives.
│
├─ "A conflicting task is already running"
│  └─ Another vzdump/migration/apt task is in flight. Wait. Two concurrent
│     vzdumps on one host is how you get a corrupt archive and a full disk.
│
├─ "Not enough space on synology-backup"
│  └─ See B, last branch.
│
└─ vzdump itself errors mid-run
   └─ journalctl -u pvedaemon; check /var/log/vzdump/. Common causes: the guest
      has a snapshot in a bad state, or an LVM thin pool is over-committed.
```

## D. Verification fails

```text
make verify-backups fails
├─ "VERIFICATION FAILED ... zstdcat | vma verify"
│  └─ The archive is corrupt. Do NOT proceed to any destructive stage. Re-run the
│     backup for that guest. If it fails twice, suspect the source disk or the
│     network path to the NAS.
│
├─ "Checksum drift"
│  └─ The archive changed after it was written. Something else is writing to the
│     dump directory. Investigate before trusting anything on that share.
│
├─ "N verified archives for M protected guests. These numbers must be equal."
│  └─ A guest was missed. Check protected_guests in group_vars against `qm list`.
│
└─ "the cleanly-stopped 'final' backup must be the newest"
   └─ You took an initial backup after the final one. Re-take the final one.
```

## E. The upgrade of .11 goes wrong

```text
make upgrade-pve1
├─ pve8to9 reports failures
│  └─ STOP. Fix each at source. Failures can never be waived; warnings only with
│     -e pve_precheck_accept_warnings=true after you have read every one.
│
├─ dist-upgrade halts on a conflict
│  └─ Almost always a third-party repository. Disable it, `apt -f install`, retry.
│     Check artifacts/upgrade-precheck-pve1.md for the list found.
│
├─ Host does not come back after the reboot
│  └─ THIS is why console access was mandatory. At the console:
│     - `ip -br a` — did the interface name change? (predictable names can shift)
│     - compare with host-configs/pve1/latest/files/etc/network/interfaces
│     - boot the previous kernel from the GRUB menu if the new one panics
│
├─ Guests missing from `qm list` after the upgrade
│  └─ Check /etc/pve is mounted: `findmnt /etc/pve`. If pmxcfs is not running,
│     the configs are there but invisible. `systemctl status pve-cluster`.
│
└─ EVE-NG labs will not start
   └─ cat /sys/module/kvm_intel/parameters/nested  → must be Y
      Check /etc/modprobe.d/ survived the upgrade; compare against the capture.
```

## F. Cluster problems

```text
pvecm status is unhappy
├─ "Quorate: No" on a single-node cluster right after `pvecm create`
│  └─ systemctl status corosync pve-cluster; check the node name resolves to its
│     OWN address and not 127.0.1.1 in /etc/hosts. This is the #1 cause.
│
├─ A node will not join: "authentication key ... "
│  └─ The joining node is not empty, or its clock is skewed. Both are checked by
│     the pve_join precheck before you get here.
│
├─ Join fails with a host key warning
│  └─ Verify at the console. Never disable StrictHostKeyChecking to get past it.
│
├─ Quorum lost after a node reboot
│  └─ Wait for it to come back. Do NOT run `pvecm expected 1` as a workaround —
│     see rollback.md. Diagnose with corosync-cfgtool -s and journalctl.
│
└─ /etc/pve is read-only
   └─ That is pmxcfs refusing to write without quorum, working as designed. Fix
      quorum; do not bypass it.
```

## G. Restore problems

```text
make restore-pve2 fails
├─ "The restore plan is not clean: N blocked entries"
│  └─ Read artifacts/restore-plan.md — each entry lists its own blocking reason.
│
├─ "bridge vmbrX ... does not exist on pve2"
│  └─ The rebuilt host's network configuration does not match the old one.
│     Recreate the bridge from host-configs/pve2/latest/files/etc/network/interfaces.
│
├─ "MAC ... is already in use"
│  └─ Restore that guest with --unique and record the new address. Two identical
│     MACs on one L2 segment produce intermittent, maddening failures.
│
├─ "Checksum mismatch — do not restore from it"
│  └─ The archive changed since verification. Use the other generation. If both
│     are bad, you have a NAS problem, not a Proxmox problem.
│
├─ Restored guest will not boot
│  └─ Compare `qm config <vmid>` against artifacts/discovery.md for the original:
│     machine type, BIOS (seabios vs ovmf), EFI disk present, boot order, CPU type.
│     A guest that booted under q35+OVMF will not boot as i440fx+SeaBIOS.
│
└─ Guest boots but has no network
   └─ Expected for metasploitable2 (link_down=1 by design). For anything else,
      check the bridge name and VLAN tag against the discovery report.
```

## H. "Ansible skipped the thing I wanted it to do"

```text
The play ran, printed prechecks, and changed nothing
└─ The destructive tasks are tagged `never,destructive` on purpose.
   Re-run with --tags all,destructive (the make targets already do this), AND
   supply the approval variables. Both are required; neither alone is enough.
```

## When to stop entirely

Stop the migration and reassess if any of these are true:

* A backup archive fails verification twice.
* `pve8to9` reports a failure you cannot explain.
* A guest disappears from `qm list` after any operation.
* The NAS mount source ever resolves under `/volume2`.
* You lose console access to a host you are about to modify.
* Quorum behaves erratically before you have added the third node.

Nothing in this migration is urgent enough to justify proceeding past one of these.
