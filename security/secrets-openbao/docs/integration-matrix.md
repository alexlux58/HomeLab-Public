# Application-secret integration matrix

| consumer | current state | proposed path | delivery | pilot/order | outage fallback |
|---|---|---|---|---:|---|
| PVE Exporter, VM 310 | root-only file, read-only PVE token | `kv/observability/pve-exporter` | Agent file, restart exporter only | 1 | operator installs rotated read-only token |
| Alertmanager, VM 310 | root-only the SMTP provider SMTP file | `kv/observability/alertmanager` | Agent template/file | 3 | operator runtime file + the SMTP provider reset |
| Grafana, VM 310 | root-only admin secret | `kv/observability/grafana` | Agent file at controlled restart | 5 | Keychain/browser recovery |
| Synology SNMPv3, VM 310 | root-only SNMP config | `kv/observability/synology-snmp` | Agent-rendered exporter config | 4 | DSM-side SNMP rotation |
| Speedtest Tracker, VM 300 | root-only Compose env | `kv/homelab-services/speedtest-tracker` | Agent file and targeted recreate | 2 | the SMTP provider reset and application backup |
| NPM, VM 300 | persistent app database | `kv/homelab-services/npm` for future bootstrap only | Agent file where supported | later | app-aware backup + loopback admin |
| Uptime Kuma, VM 300 | application database | `kv/homelab-services/uptime-kuma` if external secret exists | Agent file | later | app-aware backup |
| Linkding, VM 300 | app credential/database | `kv/homelab-services/linkding` | Agent file | later | app-aware backup |
| NetKnife, VM 300 | repaired local auth | `kv/homelab-services/netknife` | Agent file | later | source rebuild + DB backup |
| Terraform controller | operator runtime PVE token | `kv/automation/terraform/proxmox` | short token in process environment | after pilot | independent bootstrap PVE token |
| Ansible controller | SSH keys + operator runtime files | `kv/automation/ansible/*` | lookup/Agent, `no_log` | after pilot | independent SSH keys and escrow |
| Synology backup transport | not yet created | deliberately outside KV | dedicated SSH key | bootstrap | operator-held copy outside NAS |
| age backup identity | not yet created | deliberately outside KV | public recipient on node; private key offline | bootstrap | offline duplicate held separately |
| browser accounts | macOS Keychain | stay outside initially | browser/Keychain | never first | Keychain export/recovery procedure |

Kubernetes, database dynamic credentials, and SSH certificate auth
are prepared patterns only; no current workload justifies deploying them.

GitHub OIDC access is superseded by D7/ADR-0009: Actions are hosted offline
checks only and have no OpenBao credentials or route into the lab.
