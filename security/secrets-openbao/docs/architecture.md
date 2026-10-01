# Architecture

## Decision

Deploy three OpenBao 2.6.1 Raft voters, one per Proxmox host. Each has 2 vCPU,
2 GiB fixed RAM, and a 24 GiB local boot/Raft disk. This costs 6 GiB across the
cluster and tolerates one failed voter or one failed physical host.

A single node would fit more comfortably on pve3, but every host reboot,
disk failure, or guest failure would stop secret delivery. Because the Home Lab
already has three physical nodes and recovery-critical consumers, three voters
are the appropriate minimum. Five voters would add cost without providing a
new physical failure domain.

## Traffic flow

```text
clients / OpenBao Agents
          |
          | TLS 8200, private CA
          v
bao.lab.example.com -> 192.168.0.40 Keepalived VIP
          |
          v
HAProxy on current VIP owner
   |             |             |
bao-1:8200    bao-2:8200    bao-3:8200
   \_____________|_____________/
          Raft TLS 8201

active node -> local audit file -> Alloy -> Loki on VM 310
Prometheus on VM 310 -> authenticated /v1/sys/metrics
bao-1 daily -> Raft snapshot -> age encryption -> restricted SFTP -> Synology
```

Clients may also use direct node names during VIP recovery. OpenBao standbys
forward writes to the active node; HAProxy accepts only unsealed/healthy nodes
after initialization.

## Failure domains

| failure | expected result | operator action |
|---|---|---|
| one OpenBao VM | quorum remains 2/3 | repair/replace the voter; no restore |
| one Proxmox host | quorum remains 2/3 | keep service running; rebuild its voter locally |
| Synology offline | OpenBao remains normal | alert on backup age; resume SFTP later |
| VIP owner offline | Keepalived moves `.5.19` | verify DNS unchanged and direct nodes healthy |
| VM 310 offline | secrets remain available; telemetry unavailable | recover observability independently |
| VM 300 offline | OpenBao API remains direct on 8200 | NPM/Homepage unavailable, but no secret outage |
| quorum lost | reads/writes unavailable | preserve all disks; use emergency runbook only |

Raft never uses NFS. Proxmox VM backups are supplemental crash-consistent
images; encrypted OpenBao snapshots are the authoritative application backup.

## Capacity controls

- No memory ballooning and no host-wide swap disable. The systemd unit sets
  `MemorySwapMax=0` only for OpenBao.
- Raft `performance_multiplier=1`; local SSD/NVMe nodes are favored for VIP
  priority, while pve2 HDD remains an equal voter.
- Node Exporter and a native Alloy fragment are the only planned per-node
  observability overhead.
- OpenBao and OS logs are bounded and rotated. Alert before the local disk or
  audit directory reaches 80%.
