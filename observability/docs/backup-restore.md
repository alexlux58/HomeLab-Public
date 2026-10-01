# Backup and restore

## Three recovery layers

1. **Git** — Compose, Ansible, dashboards, alerts, target files, documentation.
2. **Application-aware archive** — coherent Prometheus snapshot, SQLite-safe
   Grafana backup, configuration, image inventory, detached SHA-256 and internal
   manifest. Loki history and secret contents are intentionally excluded.
3. **Proxmox VM archive** — full VMID 310 snapshot to shared
   `synology-backup`, Zstandard, `keep-all=1`.
   **Status 2026-09-06: layer 3 does not exist yet.** `/etc/pve/jobs.cfg`
   contains exactly one `vzdump` job, for VMID 300. There are zero archives for
   VMID 310 on `synology-backup`. Until that job is created, the application
   archive in layer 2 lives only on VM 310's own disk and does not survive loss
   of the guest.

The application timer runs at 03:30 with low CPU/I/O priority and a randomized
delay. Schedule the Proxmox backup at 04:15 so the application archive is inside
the VM snapshot. No script prunes or overwrites an earlier archive.

## Known pitfalls

**Prometheus does not listen on loopback.** `compose.yaml` publishes
`${OBSERVABILITY_IP}:9090:9090`, so `http://127.0.0.1:9090` is refused inside the
guest. `backup.sh` originally hardcoded the loopback URL and failed every night
with `curl` exit 7, producing no archive between 2026-08-24 and 2026-09-06. It
now reads `OBSERVABILITY_IP` from the same `docker/.env` Compose uses. If you
ever move the stack to a new address, change `.env` only — the script follows.

**A failed backup raises no alert.** The unit failing is visible only in
`systemctl --failed`. `backup.sh` writes
`homelab_observability_backup_last_success_timestamp_seconds` to the
node_exporter textfile directory; add a rule on that metric going stale before
trusting the timer unattended.

**The backup directory is root-only.** `/srv/observability/backups` is `0750
root:root`, so a shell glob run as `labuser` expands to nothing and looks like an
empty directory. Wrap the whole pipeline: `sudo -n bash -c '...'`.

**The snapshot endpoint needs `--web.enable-admin-api`.** It is set in
`compose.yaml`. Removing it silently breaks layer 2.

## Application backup proof

```bash
make backup
ssh observability 'sudo ls -lh /srv/observability/backups'
make restore-drill ARCHIVE=/srv/observability/backups/homelab-observability-<UTC>.tar.zst
```

The drill verifies the detached archive hash, every internal file hash, Grafana
SQLite integrity, Prometheus snapshot structure, Compose, and configuration in
an isolated temporary directory. It never writes into live application paths.

## Full VM proof

- Backup only VMID 310 to `synology-backup` with snapshot mode and Zstandard.
- Preserve all archives (`keep-all=1`).
- Run full `vma verify` and record SHA-256.
- Restore to unused VMID 398 with a new MAC.
- Before first boot enforce `onboot=0`, `protection=1`, and `link_down=1`.
- Validate QGA, filesystem, application archive hashes, Compose recreation, and
  Grafana/Prometheus/Loki readiness through console or host-only methods.
- Stop and retain VM 398 protected; never delete it automatically.

## Bare rebuild

1. Recreate VM 310 with the documented MAC/resources and signed Ubuntu image.
2. Restore and verify the SSH host key or deliberately record the new one at
   console after confirming the rebuild.
3. Clone this repository; run preflight and base deployment.
4. Restore operator-owned secret files from the encrypted credential backup.
5. Restore `grafana.db` if desired. Prometheus snapshot restore is optional;
   starting with an empty TSDB is often safer after corruption.
6. Start Compose, validate targets/dashboards/logs, then deploy agents.
7. Keep the old VM/archive untouched until acceptance passes.
