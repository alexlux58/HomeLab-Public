# Synology NFS backup target — manual DSM configuration

Everything in this document is done **by hand in the DSM web interface**. This
project never logs into DSM, never needs Synology credentials for the data path,
and never edits Synology-managed system files such as `/etc/exports`.

DSM: <https://192.168.0.20:5001>

## Hard rules

| rule | why |
|---|---|
| Use **Volume 1** (Storage Pool 2) only | ~10.3 TB free and healthy |
| **Never** use Volume 2 / Storage Pool 1 | 0 bytes free and reporting a health warning |
| Grant NFS access to exactly three IPs | `.11`, `.12`, `.13` — nothing else |
| No retention/pruning policy on the Proxmox side | this project never deletes an archive |

`inventory/group_vars/all.yml` encodes the first two rules as
`nas_forbidden_path_prefixes` and `nas_required_volume_prefix`; stage 1 aborts if
the mount source ever resolves under `/volume2`.

## 1. Check the volume health first

### Storage Manager → Storage → Storage Pool

- [ ] Storage Pool 2 / Volume 1 status is **Healthy**.
- [ ] Volume 1 free space is comfortably above the figure in
      `artifacts/storage-capacity.json` (`totals.required_with_margin_human`).
- [ ] Note Storage Pool 1's warning. Do not "fix" it by moving backups there.

If Storage Pool 2 is anything other than Healthy, stop and resolve that first.
Writing the only copy of your VMs onto a degraded pool is not a backup.

## 2. Enable the NFS service

### Control Panel → File Services → NFS

- [ ] Tick **Enable NFS service**.
- [ ] Maximum NFS protocol: **NFSv4.1** (or NFSv4.2 if your DSM offers it).
- [ ] Leave NFSv4 domain at the default unless you already use Kerberos.
- [ ] Apply.

Reference: <https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/file_winmacnfs_nfs?version=7>

## 3. Create the shared folder on Volume 1

### Control Panel → Shared Folder → Create

- [ ] Name: `proxmox-cluster-backups`
- [ ] Location: **Volume 1** — check this twice, DSM defaults to whichever volume
      it likes.
- [ ] Description: `Proxmox cluster migration backups — do not prune`
- [ ] Leave "Hide this shared folder" and recycle bin **off**.
- [ ] Encryption: **off**. An encrypted share that fails to mount after a NAS
      reboot turns your backup target into a silent local-disk fallback.
- [ ] Data checksum for advanced data integrity: **on** if offered.

The resulting export path is `/volume1/proxmox-cluster-backups`. If DSM gives you
anything starting with `/volume2`, delete it and start again.

## 4. Add one NFS permission rule per Proxmox host

### Control Panel → Shared Folder → `proxmox-cluster-backups` → Edit → NFS Permissions → Create

Create **three separate rules**, one per host. Do not use a subnet or `*`.

| field | value |
|---|---|
| Hostname or IP | `192.168.0.11` — then repeat for `.12` and `.13` |
| Privilege | **Read/Write** |
| Squash | **No mapping** |
| Security | `sys` |
| Enable asynchronous | **on** (throughput; the write test in stage 1 measures it) |
| Allow connections from non-privileged ports | **off** |
| Allow users to access mounted subfolders | **on** |

`No mapping` is required because `vzdump` writes as root and Proxmox needs to
preserve ownership inside the dump directory. This is why the rule must be scoped
to three specific IPs and nothing wider.

Reference: <https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/file_share_privilege_nfs?version=7>

## 5. Take a snapshot before the destructive stages

### Snapshot Replication → Snapshots → select `proxmox-cluster-backups` → Take a Snapshot

Stage 9a refuses to let `.12` be rebuilt until you confirm this with
`-e synology_snapshot_taken=true`. A snapshot protects the archives from the one
thing verification cannot: someone deleting them by accident.

## 6. Verify from the Proxmox side

```bash
make nas-preflight
```

This runs on all three hosts and proves, per host:

- ICMP and TCP 2049/111 reachability
- the export is advertised to *that specific host*
- it mounts as a real NFS filesystem (not a silent local-directory fallback)
- the mount source is under `/volume1`, never `/volume2`
- it is writable, and a uniquely named test file reads back with a matching SHA-256
- measured throughput is above `nas_preflight_min_write_mbps`
- free space clears both the absolute floor and the estimated requirement + 30%

Then register it as a Proxmox storage:

```bash
make nas-preflight EXTRA="-e allow_configure_nfs_storage=true"
```

which runs, per host:

```bash
pvesm add nfs synology-backup \
  --server 192.168.0.20 \
  --export /volume1/proxmox-cluster-backups \
  --content backup \
  --options vers=4.2,hard,noatime,nfsvers=4.2 \
  --prune-backups keep-all=1
```

`keep-all=1` is the important flag: it tells Proxmox this datastore has **no
retention policy**, so nothing is ever pruned.

Reference: <https://pve.proxmox.com/wiki/Storage:_NFS>

## Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `showmount -e` returns nothing | NFS service off, or no rule for this IP | steps 2 and 4 |
| mounts but writes fail with permission denied | Squash is not "No mapping" | step 4 |
| `findmnt` shows no filesystem at the mount point | mount silently failed; you are writing to local disk | stage 1 aborts on exactly this |
| Very slow throughput | "Enable asynchronous" off, or 1GbE saturated | step 4; consider a maintenance window |
| Export path starts with `/volume2` | share created on the wrong volume | delete and recreate on Volume 1 |
