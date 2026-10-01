# Synology storage health, scrubbing, and Volume 1 redundancy

Measured read-only against `nas1` (the NAS, DSM 7.4.1-90080) on 2026-08-25.
Nothing in this document has been executed. Every action below is an attended
operator step in DSM; no playbook in this repository touches Synology storage.

## Measured layout

The the NAS has four bays and **three disks. Bay 1 is empty.**

| Linux | DSM | model | serial | size | array | pool / volume |
|---|---|---|---|---|---|---|
| `sdb` | Disk 2 | ST12000VN0008-2YS101 | ZRT0KNH1 | 12 TB | `md3` RAID1, **1 of 1 member** | Storage Pool 2 → Volume 1, 11 TB |
| `sdc` | Disk 3 | ST4000VN006-3CW104 | SERIAL-REDACTED-1 | 4 TB | `md2` RAID1 member | Storage Pool 1 → Volume 2, 3.5 TB |
| `sdd` | Disk 4 | ST4000VN008-2DR166 | SERIAL-REDACTED-2 | 4 TB | `md2` RAID1 member | Storage Pool 1 → Volume 2, 3.5 TB |

From `/proc/mdstat`:

```text
md2 : active raid1 sdd5[0] sdc5[2]   3902187456 blocks [2/2] [UU]
md3 : active raid1 sdb5[0]          11708154880 blocks [1/1] [U]
```

Usage: Volume 1 is 370 GiB of 11 TiB (4%); Volume 2 is 445 GiB of 3.5 TiB (13%),
which confirms the `@synologydrive` reclamation completed — Volume 2 was 100%
full on 2026-08-22.

## Disk 3 SMART finding (2026-08-25 evening)

Operator-run `smartctl -a` changed the picture for Disk 3 (`sdc`,
ST4000VN006, serial SERIAL-REDACTED-1):

| disk | overall health | attr 5 raw | attr 5 VALUE/THRESH | 197 pending | 198 offline |
|---|---|---:|---|---:|---:|
| Disk 3 (`sdc`) | **FAILED / FAILING_NOW** | 24 | **001 / 010** | 0 | 0 |
| Disk 4 (`sdd`) | PASSED | 56 | 100 / 010 | 0 | 0 |

DSM's SNMP `diskHealthStatus` still reports normal for both. Trust SMART over
SNMP here. Seagate has already crossed its own pre-fail threshold on Disk 3;
the "failure expected in less than 24 hours" line is the drive's standard
FAILING_NOW template text, not a measured countdown — but the disk is no longer
"watch the trend."

**What "replace the disk" means:** buy a new ≥4 TB drive, shut down or hot-swap
per DSM guidance for the the NAS, remove Disk 3 from bay 3, insert the new drive,
and let DSM rebuild the RAID1 mirror from Disk 4. It does **not** mean wipe the
NAS, format Volume 2, or touch Volume 1 / the Proxmox backup archives. Volume 2
stays online during a normal Synology rebuild; it is degraded until the rebuild
finishes.

Until Disk 3 is replaced, Volume 2 has no redundancy — Disk 4 is the only good
copy. Do not scrub Storage Pool 1 first; scrubbing stresses a dying member. Order
a replacement, then rebuild, then scrub.

Disk 4 still has 56 reallocated sectors but its SMART overall result is PASSED
and attributes 197/198 are zero. Keep watching it; it is not FAILING_NOW today.

---

## The risk ranking after the SMART read

Volume 1 (single Disk 2, all Proxmox backups) remains the largest *structural*
risk. Disk 3 FAILING_NOW is the largest *active* risk on Volume 2. Both matter;
they need different actions.

## Data scrubbing

Corrected 2026-09-30: DSM does not offer RAID parity scrubbing for RAID1
or Basic pools. Filesystem checking depends on the actual filesystem and model;
do not promise Btrfs support without checking DSM. After bay-3 repair completes,
run Data Scrubbing only if DSM offers it; otherwise record it unsupported and
perform extended SMART plus backup/file checksum verification. Never scrub the
failing Disk 3 before replacement. The [replacement runbook](disk3-replacement.md)
gives the attended sequence and read-only monitoring checks.

See [Synology's RAID support table](https://kb.synology.com/en-global/DSM/tutorial/What_RAID_type_is_best_for_my_storage).
SNMP previously showed normal despite failed SMART; retain both forms of
evidence and use the operator's current SMART verdict before maintenance.

## Getting redundancy under Volume 1

Options, measured against the current hardware. Bay 1 being free is what makes
the first option viable without destroying anything.

### Option A — add a fourth disk and convert Basic to RAID1

Install a 12 TB (or larger) CMR SATA drive in the empty bay 1. First confirm
DSM reports Storage Pool 2 as Basic and Healthy, and the new disk satisfies
its exact capacity/type rules. Then Storage Manager → Storage Pool 2 → `…` →
Change RAID Type → RAID1. Basic → SHR is not a supported in-place conversion. DSM rebuilds
in place; Volume 1 stays online and mounted throughout, so the Proxmox NFS
storage keeps working and no backup archive is touched.

- Cost: one drive. Match or exceed 12 TB; a smaller disk cannot protect it.
- Usable capacity stays about 11 TB. You are buying redundancy, not space.
- Rebuild on a 12 TB SATA disk in a 1.6 GiB ARM NAS will take on the order of a
  day, with degraded I/O. Schedule around backup jobs.
- This is the only option that adds protection without moving the archives.

### Option B — relocate the backup target to the mirrored pool

Volume 2 has 3.1 TB free and is already RAID1. The current archive set is far
smaller than that, so the backups could live on protected storage today at zero
hardware cost.

The catch is capacity ceiling and the migration itself: `keep-all=1` means the
archive set only grows, 3.1 TB is a hard wall, and re-pointing the Proxmox
storage means registering a new NFS export and copying archives with verified
checksums before retiring the old path. No archive may be deleted, so both copies
must coexist during the transition. Treat this as a gated stage of its own, not a
quick change.

### Option C — accept the risk, with a second copy elsewhere

Keep the single-disk pool and rely on the fact that these archives are a
*secondary* copy — the guests themselves are the primary. This is defensible only
while the protected guests are healthy, and it is the current de-facto state. If
this is the chosen answer, make it explicit rather than accidental, and add an
alert on Disk 2's SMART attributes specifically, since a single-disk pool has no
margin for a slow failure.

### Not recommended

Do not convert Storage Pool 2 by adding a *smaller* disk, and do not merge the
two pools. Do not enable Btrfs snapshots on the backup share as a substitute for
redundancy: a snapshot on the failing disk dies with the disk.

## Alerting follow-up

`SynologyDiskBadSectors` was replaced on 2026-08-25 with
`SynologyDiskBadSectorsRising` (`delta(diskBadSector[24h]) > 0`) and
`SynologyDiskBadSectorsHigh` (absolute count above 200). The old `> 0` threshold
could never clear, because reallocated sectors never decrease. Rules live in
`observability/config/prometheus/rules/synology.yml`.

There is no alert today for a single-disk pool losing its only member beyond the
generic `SynologyRaidNotNormal`. If Option C is chosen, add one.
