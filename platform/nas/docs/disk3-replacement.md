# Disk 3 replacement — the NAS bay 3

Approved D5, 2026-09-30: the operator is buying a WD Red Plus 4 TB CMR disk.
This is an attended DSM procedure, not an Ansible stage. No replacement,
storage operation or purchase has been performed by an agent.

## Before removing anything

1. Identify **bay 3 / Disk 3**, currently ST4000VN006, serial SERIAL-REDACTED-1, in
   Storage Manager and on the tray. Do not touch Disk 2 (Volume 1 backups) or
   Disk 4 (the surviving Volume 2 mirror member). Bay 1 is empty.
2. Check Disk 4 now: DSM health, extended SMART result, pending/uncorrectable
   sectors and reallocation trend. Its August baseline was PASSED with 56
   reallocated sectors, zero pending and zero offline-uncorrectable sectors.
   That historical result is insufficient. If it is unhealthy, stop and
   secure a verified independent copy before stressing it with a rebuild.
3. Have a recent independent, checksum-verified backup of irreplaceable
   **Volume 2 data**, including Music and Movies. Proxmox archives on Volume 1
   do not back up those folders. Verify an archive or sample restore, not just
   a successful job status. Keep every existing backup.
4. Confirm Storage Pool 1 / Volume 2 is the two-disk RAID1 mirror and its
   surviving member is accessible. Record pool state, drive identities and
   SMART baseline. Suspend discretionary downloads/imports and choose a quiet
   window; do not scrub the failing member before replacement.
5. Check the replacement's exact usable sector capacity is at least the old
   member's. Both being marketed as 4 TB does not prove this. Confirm the new
   disk is CMR and that DSM accepts it for the repair.

## Replace and repair

The [the NAS hardware installation guide](https://global.download.synology.com/download/Document/Hardware/HIG/DiskStation/18-year/the NAS/enu/Syno_HIG_DS418_enu.pdf)
documents hot-swappable trays. Follow DSM's current prompts and the guide.

1. In Storage Manager → HDD/SSD, select **Disk 3** and deactivate it if DSM
   offers that action. Check the selected serial again. Wait for DSM to mark
   the member removed/degraded before withdrawing **tray 3 only**.
2. Fit the WD Red Plus replacement to tray 3 and insert it fully. Retain the
   old disk securely; it contains data and is not an agent cleanup item.
3. Storage Manager → Storage → **Storage Pool 1** → `…` → **Repair**.
   Select the new bay-3 disk and confirm its identity. DSM erases the new
   disk during repair. Never create a replacement pool, initialize Volume 1,
   select Disk 2 or Disk 4 as a disk to erase, or remove the surviving member.
4. Monitor repair progress, SMART and system logs until the pool is Healthy
   and both RAID1 members are present. Do not reboot, pull another tray or
   run another storage maintenance operation during repair.

Allow roughly **12–48 hours**, possibly longer under load or with read retries.
This is a planning window, not a deadline; capacity and actual rebuild speed
determine completion. See Synology's
[storage-operation time guidance](https://kb.synology.com/en-nz/DSM/tutorial/Estimated_time_of_storage_operations).

## After the rebuild

Check both disks with extended SMART and compare the recorded error counts.
Run DSM **Data Scrubbing** afterwards only if DSM offers it for the actual
filesystem and pool. DSM's supported RAID table marks RAID1 parity scrubbing
as unavailable; Btrfs filesystem checking depends on model/filesystem support.
If DSM provides no scrub action, record it as unsupported and use extended
SMART plus checksum verification of backed-up files. Do not attempt an
undocumented SSH repair or imply a parity scrub occurred.
See [Synology's RAID support table](https://kb.synology.com/en-global/DSM/tutorial/What_RAID_type_is_best_for_my_storage).

Once the operator reports completion, the agent's checks are read-only queries
to Prometheus on **VM 310**, followed by a comparison with the DSM result:

```bash
curl --fail --silent --show-error --get http://192.168.0.31:9090/api/v1/query \
  --data-urlencode 'query=up{job="synology-snmp"}'
curl --fail --silent --show-error --get http://192.168.0.31:9090/api/v1/query \
  --data-urlencode 'query=raidStatus{job="synology-snmp"}'
curl --fail --silent --show-error --get http://192.168.0.31:9090/api/v1/query \
  --data-urlencode 'query=diskHealthStatus{job="synology-snmp"}'
```

Require a fresh successful scrape, all returned RAID/disk status values normal
(`1`), and the replacement disk represented in DSM. SNMP previously reported
normal while Disk 3 failed SMART; these metrics supplement, never replace,
the operator's SMART and DSM verification. No NAS setting is changed.

## The larger Volume 1 risk

**Volume 1 is a single disk holding every Proxmox archive. Bay 1 is empty.**
The structural fix is a second **12 TB or larger CMR SATA disk** in bay 1,
then an attended **Storage Pool 2 Basic → RAID1** conversion. Confirm DSM
reports Basic and Healthy and the new disk meets its exact size/type rules
first. This is a separate operator project after Disk 3 is repaired, with
verified independent backups; it is not a Basic → SHR conversion and does
not increase usable capacity. See Synology's
[Change RAID Type procedure](https://kb.synology.com/index.php/en-af/DSM/help/DSM/StorageManager/storage_pool_change_raid_type?version=7).

The approved D: pull copy reduces dependence on that one disk but is neither
off-site nor immutable. No archive is deleted during either project. There
is no safe automatic rollback of a failed physical rebuild: stop maintenance,
retain both disks and all backups, and assess recovery with the operator.
