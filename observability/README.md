# Homelab observability

VM infrastructure is adopted by the import-first Terraform root in the sibling
Proxmox repository; this repository's Ansible owns guest and application state.
See [automation.md](docs/automation.md) for the boundary and recovery order.

Reproducible, resource-bounded monitoring for the three-node Proxmox `homelab`
cluster, Synology `nas1`, VM 300, Docker services, DNS, TLS, and internal
websites.

## Current state

Stage I discovery, provisioning, first boot, and base hardening passed on
2026-08-24. Protected VM 310 `observability` is running on `pve1` with these
fixed identifiers:

| item | value |
|---|---|
| VMID | `310` |
| reserved IP | `192.168.0.31/24` |
| MAC | `52:54:00:00:00:00` |
| placement | `pve1` / local NVMe directory storage |
| resources | 4 vCPU, 4 GiB fixed RAM, 64 GiB sparse QCOW2, 2 GiB swap |
| OS | Ubuntu 24.04.4 LTS; cloud-init `done`, QGA active |
| safety | protected, running, `onboot=0` until recovery gates pass |

Canonical's signed 2026-08-23 image manifest and checksum were reverified
before import. The guest's network-presented ED25519 host key exactly matched
the fingerprint read through QGA:
`SHA256:EXAMPLE_FINGERPRINT_REDACTED`. The dedicated client key
fingerprint is `SHA256:EXAMPLE_FINGERPRINT_REDACTED`.
`ssh observability` uses both pinned identities.

The versioned `make bootstrap` stage enforces key-only SSH, LAN-scoped UFW,
bounded journals, unattended upgrades without automatic reboots, weekly trim,
QGA, swappiness 10, and 2 GiB emergency swap. Its second run completed with
`changed=0`, and every control persisted across a controlled reboot.

The rotated read-only PVE token, Grafana administrator secret, and Synology
SNMPv3 configuration are installed as `root:root` mode-0600 files; only metadata
was inspected. The Grafana file is 20 bytes and meets the enforced administrator
secret floor, so the credential gate passes. The sanitized central preflight
passed on 2026-08-24:
Ubuntu 24.04 x86-64,
4 vCPU, about 3.76 GiB usable RAM, about 56.7 GiB root free, deployment ports
clear, and Docker absent as expected. The ten-container central stack is now
deployed with bounded resources, stable containers, ready core services, and an
active backup timer. Central validation passes with healthy PVE exporter and
Synology SNMPv3 targets. VM 310 remains `onboot=0` until application and VM
backup restore drills pass.

The expanded dashboards and the Synology alert rules were installed on
2026-08-25 through the approved `make update-dashboards` stage: `promtool`
validated every rule file, Prometheus reloaded through its lifecycle endpoint,
and no container was restarted or recreated. `make validate` then passed 15
tasks with `changed=0`. All nine `synology` alert rules are loaded.

The corrected queries immediately surfaced a real finding the previous broken
dashboard could not see: `diskBadSector` is non-zero on two of the three the NAS
disks (Disk 3 = 24, Disk 4 = 56, Disk 2 = 0). DSM still reports every disk
healthy and both volumes normal, so this is not an outage. Measurement the same
day showed the counts are flat across every sample ever collected, and that the
two affected disks are the mirrored pair behind Volume 2 rather than the
unprotected single disk behind Volume 1.

That made the original `diskBadSector > 0` rule permanently-firing noise, since
reallocated sectors never decrease and the condition could never clear. It was
replaced with `SynologyDiskBadSectorsRising` (`delta(diskBadSector[24h]) > 0`)
and `SynologyDiskBadSectorsHigh` (absolute count above 200); both load
`inactive` against live data, and a test fails the build if the `> 0` form
returns. Note that the exporter returns `diskID` hex-encoded, so panels label
disks as `0x4469736B2032` rather than `Disk 2`.

## What gets deployed

- Metrics: Prometheus, Node Exporter, cAdvisor, PVE Exporter, SNMP Exporter,
  Blackbox Exporter, and Alertmanager.
- Logs: Grafana Alloy into single-binary Loki.
- Visualization: Grafana with provisioned Prometheus, Loki, and Alertmanager
  data sources plus eight version-controlled dashboards. The Synology dashboard
  includes live system/DSM state, volume capacity, RAID and disk health,
  temperatures, bad sectors, physical/volume I/O, connected users, and SNMP
  exporter performance using the metric schema observed from the the NAS. The
  fleet, Proxmox, and availability dashboards also expose target health by job,
  severity counts, node/guest/backup state, guest I/O, HTTP status and phase
  timing, DNS results, and certificate lifetime.
- Recovery: application-aware snapshots, detached SHA-256 manifests, isolated
  restore drills, and a separate Proxmox VM backup to `synology-backup`.

The initial deployment deliberately excludes Kubernetes, ELK/OpenSearch,
Mimir, Tempo, and distributed Loki. They add cost without solving a current
requirement.

## Resource envelope

The stack is sized for a 4 GiB VM. Every container has an explicit memory and
CPU cap. Prometheus keeps at most 15 days **and** 8 GiB. Loki keeps seven days,
uses low-cardinality labels, and has bounded ingestion/query concurrency.
Normal scrapes are 60 seconds; Synology SNMP is 120 seconds to respect its
1.6 GiB ARM64 hardware. Docker JSON logs rotate at 10 MiB × three files.

Telemetry databases stay on the VM's local ext4 disk. Prometheus explicitly
does not support NFS storage reliably; the Synology is a backup target and an
SNMP target, not a TSDB host.

## Repository map

```text
ansible/     independent preflight, deploy, agent, validate, and backup stages
config/      Prometheus, Loki, Alloy, Grafana, Alertmanager, SNMP, Blackbox
docker/      pinned central Compose model
scripts/     image verification, application backup, restore drill, repo checks
docs/        architecture, discovery, secrets, recovery, upgrades, troubleshooting
tests/       offline safety and reproducibility checks
```

## Local validation

```bash
make setup                  # uses Python 3.12 for Ansible Core 2.19
make install-hooks
make lint
make test
docker compose --file docker/compose.yaml --env-file docker/.env.example config --quiet
```

`make bootstrap` hardens only the existing guest. `make deploy` is not an
aggregate bootstrap. It configures only the already installed central VM and
intentionally fails until all three root-owned runtime secret files exist.
Docker-host agents are a separate `30-deploy-agents.yml` stage.
Proxmox host agents and syslog forwarding remain a later, separately approved
change; PVE Exporter provides cluster metrics without modifying the hypervisors.

## Operator-owned secrets

No passwords, tokens, private keys, generated SNMP configuration, or captured
host state belongs in Git. See [secrets.md](docs/secrets.md). The deployment
requires these mode `0600` files on VM 310:

```text
/etc/observability/secret-store/grafana_admin_password
/etc/observability/secret-store/smtp_password
/etc/observability/secret-store/pve.yml
/etc/observability/secret-store/snmp.yml
```

## Validation and acceptance

The stack is accepted only after:

- every Compose service is running/healthy;
- Prometheus config/rules and Alloy/Loki configs validate;
- PVE, Synology SNMPv3, VM 300, Docker, HTTPS, ICMP, and DNS targets are up;
- the Synology target contains non-empty RAID and disk payload metrics, not only
  a successful scrape status;
- Grafana shows all eight dashboards and both data sources;
- a synthetic alert appears in Alertmanager and resolves;
- logs from VM 300 and at least one network syslog sender are queryable;
- application backup passes an isolated restore drill; and
- the VM 310 Proxmox backup passes `vma verify` and an isolated link-down restore.

See [deployment.md](docs/deployment.md) and [backup-restore.md](docs/backup-restore.md).
