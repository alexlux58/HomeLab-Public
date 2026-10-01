# AGENTS.md — platform/nas

Inherits `../../AGENTS.md`; these rules add to it.

## Purpose and layout

Synology the NAS (`nas`, 192.168.0.20, SSH port 2258) storage intent: the NFS
backup target registered in Proxmox, and storage-health records.

- `ansible/playbooks/05-synology-preflight.yml` and `ansible/roles/synology_nfs/`
  (also used by the Proxmox migration's `nas-preflight` stage).
- `docs/synology-nfs-setup.md`, `docs/synology-storage-health.md`.

## Commands

```text
make check        # yamllint + syntax check, offline
```

## Component rules

- Backups live on Volume 1, which is a **single disk**; never delete, prune or
  move an archive. Storage stays registered with `--prune-backups keep-all=1`
  (`allow_configure_nfs_storage` gates registration).
- The NAS never hosts observability storage or service databases. Approved
  media files and the Music library may live on the Media share.
- `ssh nas` is a non-root user; `sudo` needs the operator's password, which no
  agent handles. DSM changes are operator steps.
- Disk 3 failed SMART (2026-08-25). A bay-3 replacement and RAID1 rebuild are
  attended operator work; never script them.
- D5 approves a WD Red Plus 4 TB CMR replacement. Use
  `docs/disk3-replacement.md`; first verify Disk 4 and independent backups.
  Volume 1 remains single-disk; its separate fix is Basic → RAID1 with a
  second 12 TB+ CMR disk in bay 1. Do not promise RAID1 parity scrubbing.
- `du` on the NAS takes hours; use DSM reporting or `btrfs` tooling.

## Definition of done

`make check` passes here and `make COMPONENT=tests check` passes at the root;
staged gitleaks passes; `MEMORY.md` records any state change with its evidence.
