# Gated deployment runbook

Run one stage, review its evidence, then continue.

## I-1 — operator prerequisites — completed 2026-08-24

1. Eero reservation: `52:54:00:00:00:00` → `192.168.0.31`.
2. Dedicated SSH key:

   ```bash
   ssh-keygen -t ed25519 -a 100 -f ~/.ssh/homelab_observability_ed25519 -C homelab-observability
   ```

3. Reply `RESERVATION AND KEY READY`.

Completed 2026-08-24: reservation/key gate confirmed; public-key fingerprint
`SHA256:EXAMPLE_FINGERPRINT_REDACTED`. Canonical's signed August
Ubuntu 24.04 image was independently reverified on `pve1`, imported as a
64 GiB sparse QCOW2, and attached with EFI and cloud-init volumes. VM 310
remained stopped and protected throughout the import stage.

Canonical's signed Ubuntu 24.04 cloud-image manifest was verified with signing
fingerprint `D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81`. The signed image SHA-256
was `6e40c07ae715f744f84af0bec76415cc1987dd115b4b8de437818561f01a3733`.
The 64 GiB sparse disk, EFI volume, and cloud-init volume are attached with
backup enabled for the boot disk. `onboot=0` remains deliberate.

## I-2 — first boot and base hardening — completed 2026-08-24

- Ubuntu 24.04, QEMU agent, key-only SSH, unattended security upgrades.
- 2 GiB emergency swap, swappiness 10, bounded journal, LAN-only SSH.
- Verify the guest SSH host fingerprint through QEMU Guest Agent/console before
  adding it to `known_hosts`; never auto-accept a changed key.
- Add SSH alias `observability` using the dedicated private key.

Acceptance evidence:

- the router reservation produced `192.168.0.31/24` for MAC `52:54:00:00:00:00`;
- QGA and the network both reported SSH host fingerprint
  `SHA256:EXAMPLE_FINGERPRINT_REDACTED`;
- `ssh observability` and Ansible both use the dedicated key and
  `~/.ssh/observability_known_hosts` with strict checking;
- cloud-init reports `done` with zero errors after reboot;
- key-only SSH, LAN-only UFW, 2 GiB swap, swappiness 10, bounded journal,
  unattended upgrades, QGA, trim, internal DNS, and the 61 GiB ext4 root all
  passed post-reboot checks; and
- a second `make bootstrap` run returned `changed=0`, `failed=0`.

## I-3 — credentials (passed)

Follow [secrets.md](secrets.md). Confirm only that the three files exist and are
mode `0600`; do not disclose their contents.

Current evidence: all three files are nonempty, `root:root`, and mode `0600`;
the SNMP configuration contains the expected `synology_v3` section. No secret
value was read, logged, or committed. The rotated Grafana file is 20 bytes, so
the enforced minimum passes. Deployment checks this using file metadata only.

## I-4 — central deployment (complete)

Read-only preflight completed 2026-08-24. It verified Ubuntu 24.04 x86-64,
4 vCPU, approximately 3.76 GiB usable RAM, approximately 56.7 GiB root free,
no deployment-port conflicts, and no pre-existing Docker runtime. Sanitized
evidence is written to the gitignored `artifacts/preflight.json`.

The ten bounded containers are deployed and stable, Prometheus, Loki, Grafana,
and Alertmanager readiness passes, eight dashboards are provisioned, and
`homelab-observability-backup.timer` is active. After the operator corrected the
PVE exporter configuration without exposing the token, `make validate` passed
with healthy required PVE and Synology SNMPv3 targets.

```bash
make setup
make preflight
cat artifacts/preflight.json
make lint test
make deploy
make validate
```

Deployment fails closed on a port conflict, wrong OS/architecture, missing
secret file, permissive secret mode, invalid Compose model, or unhealthy
container.

## Dashboard and alert-rule updates

Dashboard-only changes use a narrow stage that does not recreate or restart the
ten-container stack. It validates all rule files with `promtool`, reloads
Prometheus through its lifecycle endpoint, waits for Grafana file provisioning,
and proves that Synology RAID and disk metrics are populated.

```bash
make update-dashboards EXTRA_JSON='{"allow_observability_dashboard_update":true,"observability_dashboard_update_confirmation":"UPDATE HOME LAB OBSERVABILITY DASHBOARDS"}'
make validate
```

The first command is a live configuration mutation and still requires explicit
operator approval. It never reads or replaces `snmp.yml` or another runtime
secret.

`promtool check rules` takes rule *files*, not a directory. The task expands the
glob in the container's own shell; invoking it with the directory fails the
stage before Prometheus is asked to reload, which is exactly what happened on
the first run on 2026-08-25.

Completed 2026-08-25. Dashboards (Synology 18 panels, Proxmox 12, fleet 11,
availability 9) and the eight Synology alert rules are installed. `promtool`
passed, Prometheus reloaded without a restart, the Synology RAID and disk
payload assertions passed, and `make validate` returned 15 tasks with
`changed=0`, `failed=0`. All ten containers were untouched.

## the SMTP provider email notifications

Alertmanager authenticates to `smtp.smtp.com:587` as
`alerts@example.com`, requires STARTTLS, and sends firing and resolved messages
to `operator@example.com`. Delivery was activated and tested on 2026-08-24:
Alertmanager recorded six email notifications and zero client, server, timeout,
cancellation, or other failures. The container remained running with zero
restarts after the test.

The password stays in
`/etc/observability/secret-store/smtp_password`, root-owned mode 0600. See
`secrets.md` for the constrained container-root exception required by local
Compose file-backed secrets.

## I-5 — VM 300 agents

Review the three additional containers (Node Exporter 96 MiB, cAdvisor 224 MiB,
Alloy 256 MiB) and then run only:

```bash
.venv/bin/ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/30-deploy-agents.yml
```

VM 300 firewall rules admit 9100/8080 only from `192.168.0.31`; Alloy initiates
its own outbound Loki connection.

## I-6 — DNS and reverse proxy

- Synology primary zone: `grafana.lab.example.com` A → `192.168.0.30`.
- NPM proxy host: `grafana.lab.example.com` → `http://192.168.0.31:3000`.
- Attach the existing wildcard certificate and force HTTPS.
- Keep Prometheus and Alertmanager direct-LAN unless a clear proxy need emerges.

Grafana, Prometheus, and Alertmanager are routed and are reachable from Homepage
on VM 300. Loki deliberately has **no** proxy route and no UI of its own: it is
queried through the provisioned "Centralized Logs" dashboard (`/d/homelab-logs`)
and, from there, Grafana Explore. Homepage links its Loki card to that dashboard
and health-checks `http://192.168.0.31:3100/ready` directly on the LAN. The internal exporters — Node Exporter, cAdvisor, Alloy, Blackbox, SNMP
Exporter, and PVE Exporter — are intentionally absent from Homepage; they have
no operator UI and no documented secure access path.

## I-7 — logs from appliances

After Loki/Alloy is healthy, configure one sender at a time:

- DSM Log Center → `192.168.0.31`, TCP syslog, port 1514.
- PVE rsyslog forwarding is a separate reviewed host change. Start with
  `pve3`, validate labels/volume for a day, then `.12`, then `.11`.

Do not attach dynamic filenames, message text, request IDs, or IP addresses as
Loki labels. Use `host`, `job`, `unit`, and `container` only.

## I-8 — backups and reboot gate

Run `make backup`, validate the new archive with `make restore-drill ARCHIVE=...`,
then create a Proxmox backup job for VMID 310 at 04:15 to `synology-backup` with
Zstandard and `keep-all=1`. Verify the VMA and restore to isolated VMID 398 with
a unique MAC and `link_down=1`. Only then set VM 310 `onboot=1`.
