# Application-aware backups

VM 300 runs `homelab-app-backup.timer` daily at 02:45. Each run creates a new
UTC timestamp directory under `/srv/homelab-backups/staging`; nothing is
overwritten or pruned.

Each completed set contains:

- SQLite online backups for Nginx Proxy Manager, Linkding bookmarks, and
  Speedtest Tracker, each checked with `PRAGMA integrity_check`;
- a compressed transactional MariaDB dump for Uptime Kuma 2;
- a protected configuration and certificate archive;
- sanitized NetKnife image/source metadata; and
- a JSON manifest containing sizes and SHA-256 hashes but no secret values.

Linkding's `tasks.sqlite3` is intentionally excluded because it is a disposable
background-task queue that Linkding recreates. Its durable bookmark database is
`db.sqlite3` and is included.

A directory containing an `INVALID-*` marker is test evidence, not a usable
backup. Failed or invalid proof sets are retained rather than deleted.

The next protection layer is the 03:15 Proxmox backup of VMID 300 to
`synology-backup`. Its retention must remain `keep-all=1`, and a restore test
must use an isolated NIC before first boot.
