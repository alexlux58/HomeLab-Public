# Stage I discovery and sizing report

Collected read-only on 2026-08-23 before creating VM 310.

## Cluster

| node | CPU | RAM total / used | VM storage headroom | conclusion |
|---|---:|---:|---:|---|
| `pve1` `.11` | 12 threads | 31.2 / 4.4 GiB | ~168 GiB safely available on NVMe-backed `local` | chosen placement |
| `pve2` `.12` | 8 threads | 11.5 / 4.4 GiB | ~771 GiB on HDD `local-lvm` | keep VM 300 isolated from telemetry I/O |
| `pve3` `.13` | 4 threads | 7.6 / 1.7 GiB | ~49.6 GiB `local-lvm` | too small for durable metrics/logs |

`pve1` had a load average near zero and ~26.8 GiB available RAM. A 64 GiB
sparse VM disk preserves more than 20% physical root-filesystem headroom even if
the disk grows fully. Fixed 4 GiB memory prevents an observability fault from
consuming the node; container limits keep planned steady state below 3 GiB.

VM 297 is stopped but can consume 10 GiB if started, while VM 290 can consume
18 GiB. The monitoring VM therefore remains 4 GiB rather than the pasted
specification's generic 8 GiB default. Do not increase it without re-running the
capacity audit across all possible guest power states.

## Existing services VM

VM 300 used about 1.3 GiB of its 5.7 GiB guest RAM with 104 GiB free on `/`.
All nine containers were healthy. Approximate container memory at discovery:

- Uptime Kuma 292 MiB; NPM 199 MiB; Homepage 183 MiB.
- Linkding and Speedtest Tracker 167 MiB each.
- NetKnife API 103 MiB; PairDrop 88 MiB.
- IT-Tools 11 MiB; NetKnife web 8 MiB.

This is enough headroom for capped Node Exporter, cAdvisor, and Alloy agents, but
not a reason to co-locate Prometheus/Loki. Central telemetry failure must not
take down the services being observed.

## Synology

`nas1` `.20` is a the NAS ARM64 appliance with 1.6 GiB RAM. At discovery it
had ~1.0 GiB available, 479 MiB swap in use, load average 0.37/0.22/0.23, and
~11 TiB free on healthy Volume 1. It receives a 120-second SNMPv3 interval and no
container, TSDB, log database, or polling agent.

## Address and conflict checks

`192.168.0.31` returned no ICMP response, no TCP response on 22/3000/9090, and an
incomplete ARP neighbor entry from `pve1`. That means no device was visible;
it does not replace the required the router reservation.

VMID 310 was free. MAC `52:54:00:00:00:00` was absent from every current QEMU
and LXC configuration. VM 310 was then created protected, stopped, `onboot=0`,
with no disk or OS. This is the only live change in Stage I so far.

## Existing observability conflicts

No pre-existing `homelab-observability` project was found. VM 300 has Uptime
Kuma but no Prometheus, Grafana, Loki, Alloy, PVE Exporter, SNMP Exporter,
Blackbox Exporter, Node Exporter, or cAdvisor container. The current NPM and
application ports do not conflict with the dedicated VM design.
