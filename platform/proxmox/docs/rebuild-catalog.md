# Rebuild-later catalog

Recorded 2026-08-22 before clean-installing `pve2` (`192.168.0.12`) and
`pve3` (inventory alias `pve`, `192.168.0.13`). Only the guests on `pve1` (`192.168.0.11`) are
protected by this migration.

This file is a rebuild checklist, **not a backup**. The eight guests below and
their local disks may be lost during the clean installs. Their names, Proxmox
configuration, ISO names, descriptions, snapshots, and cloud-init metadata were
captured read-only in `artifacts/discovery.json`; the `pve2` host and guest
configuration was also captured under `host-configs/pve2/latest/`.

## Evidence boundary

None of the guests has the QEMU guest agent. At the last discovery all eight
were stopped, so the collector could not inspect installed packages or running
services inside them. Items marked **confirmed** come directly from Proxmox
configuration. Items marked **inferred** come from a VM name or snapshot name
and should be treated as a rebuild hint, not proof of the exact old stack.

## pve2 / 192.168.0.12

| VMID | old guest | resources | software or purpose to rebuild | evidence |
|---|---|---|---|---|
| 100 | `Ansbile-Puppet` (spelling on host) | 2 vCPU, 7.5 GB RAM, 150 GB disk, Ubuntu 22.04 ISO | Ansible/Puppet automation; likely AWX and PostgreSQL/PuppetDB | **Inferred** from guest name and snapshot `AWX_08_17_2025` |
| 101 | `lab-k3s` | 4 vCPU, 8 GB RAM, 60 GB disk, Ubuntu Jammy cloud-init, old IP `192.168.0.30/24` | k3s Kubernetes lab | **Confirmed** by name, cloud-init description, and captured `k3s-user-data.yaml` snippet |
| 102 | `UbuntuServer2` | 2 vCPU, 6 GB RAM, 300 GB disk, Ubuntu 22.04 ISO | NetBox and/or Nautobot | **Inferred** from snapshot `Netbox-Nautobot-2026` |
| 9000 | `ubuntu-jammy-ci` | 2 vCPU, 4 GB RAM, 2.2 GB base disk plus cloud-init drive | reusable Ubuntu Jammy cloud-init template | **Confirmed** by guest description and cloud-init disk |
| 9100 | `metasploitable2` | 2 vCPU, 2 GB RAM, 8 GB disk | Metasploitable 2 security-training target | **Confirmed** by guest description; if rebuilt, attach only to an isolated, unrouted bridge |

Useful retained details:

- `lab-k3s` used `vmbr0`, virtio MAC `52:54:00:00:00:00`, cloud-init user
  `labuser`, gateway `192.168.0.1`, and a captured custom user-data snippet.
- `Ansbile-Puppet` had snapshot `AWX_08_17_2025`; `UbuntuServer2` had snapshot
  `Netbox-Nautobot-2026`. Snapshots themselves are not preserved.
- All five used node-local storage. No PCI/USB passthrough or custom QEMU
  arguments were discovered.

## pve3 / 192.168.0.13

| VMID | old guest | resources | software or purpose to rebuild | evidence |
|---|---|---|---|---|
| 100 | `NIXOS` | 2 vCPU, 4,048 MB RAM, 50 GB disk | NixOS graphical 25.11 lab | **Confirmed** by attached `nixos-graphical-25.11.5148.d04d8548aed3-x86_64-linux.iso` |
| 101 | `Kali` | 2 vCPU, 4,048 MB RAM, 32 GB disk | Kali Linux 2025.4 security lab | **Confirmed** by attached `kali-linux-2025.4-installer-amd64.iso` |
| 102 | `ProxmoxDatacenterManager` | 2 vCPU, 4,048 MB RAM, 40 GB disk | Proxmox Datacenter Manager 1.0-2 evaluation | **Confirmed** by attached `proxmox-datacenter-manager_1.0-2.iso` |

All three were stopped, had one virtio NIC on `vmbr0`, and had no passthrough,
custom arguments, or snapshots.

## Local websites and services to add later

The preferred shape is one new Ubuntu VM running Docker Compose, with persistent
data on a deliberate storage path and service definitions kept in Git. Use a
reverse proxy plus Synology DNS rather than remembering port numbers.

Start with these high-value services:

| service | approximate RAM | purpose |
|---|---:|---|
| Caddy or Nginx Proxy Manager | 128 MB | reverse proxy and HTTPS front door; choose one |
| Uptime Kuma | 128 MB | service monitoring and local status page |
| Homepage or Dashy | 128 MB | live infrastructure dashboard; choose one |
| IT-Tools | 64 MB | subnet, CIDR, encoding, JWT, and regex utilities |
| Vaultwarden | 256 MB | Bitwarden-compatible password manager |

Network and automation services mentioned for a later phase:

| service | approximate RAM | purpose |
|---|---:|---|
| Oxidized | 256 MB | automated network-device configuration backups |
| LibreNMS | 2 GB | SNMP monitoring for Ubiquiti devices and the Synology |
| Grafana + Prometheus + `prometheus-pve-exporter` | 1.5 GB | Proxmox and lab metrics |
| NetBox | 2–3 GB | source of truth for IPAM/DCIM; replaces the old `UbuntuServer2` workload. Placement measured and planned in [netbox-plan.md](netbox-plan.md): a dedicated protected VM on `pve3`, **not** VM 300 or VM 310 |
| Semaphore | 256 MB | lightweight Ansible web UI |
| Forgejo or Gitea | 512 MB | local Git hosting; choose one |
| Wiki.js or BookStack | 512 MB | lab documentation; choose one |
| Authentik or Authelia | 512 MB+ | single sign-on/access proxy; choose one after the basic stack is stable |
| Immich | 2–4 GB | optional photo platform using NAS-backed storage |
| Paperless-ngx | 1 GB | optional document ingestion and search |

The existing static LAN inventory dashboard should remain on the Synology while
the Proxmox hosts are being rebuilt. It has no external assets and is independent
of cluster availability.

## DNS and URL convention

- Use the Synology DNS Server as the authoritative server for
  `lab.example.com`; avoid `.local`, which collides with mDNS/Bonjour.
- Point a wildcard `*.lab.example.com` record at the reverse-proxy VM.
- Configure the the router DHCP/custom-DNS setting to hand clients the Synology DNS
  address. The the router can forward DNS but does not provide the local authoritative
  records this plan needs.
- Add a secondary DNS server on the cluster only after the three-node cluster is
  stable; otherwise the Synology remains a DNS single point of failure.

Suggested hostnames include `status`, `home`, `tools`, `vault`, `netbox`,
`metrics`, `git`, `docs`, and `ansible` under the chosen lab zone.

### Expanded local-service menu

Keep the first deployment small enough for the 11.5 GiB `pve2` node. The
recommended core stack is Nginx Proxy Manager, Homepage, Uptime Kuma, IT-Tools,
NetKnife, Linkding, PairDrop, and Speedtest Tracker. Add only one service at a
time after measuring idle and peak memory.

| service | approximate RAM | local name | why it is useful |
|---|---:|---|---|
| NetKnife | 512 MB–1 GB | `netknife` | the existing local network/security toolkit from `~/Desktop/Netknife-app` |
| Linkding | 128–256 MB | `links` | searchable, taggable bookmarks |
| PairDrop | 64–128 MB | `drop` | browser-based LAN file transfer |
| Speedtest Tracker | 256–512 MB | `speed` | scheduled WAN performance history |
| ChangeDetection.io | 256–512 MB | `changes` | monitor pages and feeds for changes |
| FreshRSS or Miniflux | 128–256 MB | `feeds` | private RSS reader; choose one |
| Stirling-PDF | 512 MB–1 GB | `pdf` | local PDF conversion and manipulation |
| Excalidraw | 128 MB | `draw` | diagrams and whiteboarding |
| CyberChef | 128 MB | `cyberchef` | offline encoding, decoding, and data transforms |
| Mealie | 512 MB–1 GB | `meals` | recipes and meal planning |
| Actual Budget | 256–512 MB | `budget` | local-first personal budgeting |
| Home Assistant | 1–2 GB | `homeassistant` | home automation; preferably its own VM when integrations grow |
| Jellyfin | 1–4 GB | `media` | media server; requires separate NAS media paths and hardware-transcode planning |
| Open WebUI | 512 MB–2 GB | `ai` | optional UI for a separately hosted model/API; do not run a large model on these nodes |

Do not deploy all optional services at once. Vaultwarden, personal finance,
documents, and home automation require verified application-level backups and
working HTTPS before holding important data. LibreNMS, NetBox, Prometheus, and
Grafana belong in a later monitoring VM because their combined steady-state
memory and database I/O are a poor fit for the core utility VM.

The friendly DNS records `nuc-proxmox.lab.example.com` and
`lenovo-proxmox.lab.example.com` may point to `192.168.0.11` and
`192.168.0.12`. They are aliases only: the immutable Proxmox cluster node names
remain `pve1` and `pve2`.

## Rebuild order

1. Finish and validate the three-node Proxmox cluster.
2. Create one clean Ubuntu service VM with QEMU guest agent, regular verified
   backups, Docker Compose, and version-controlled configuration.
3. Deploy the reverse proxy, Uptime Kuma, dashboard, and IT-Tools first.
4. Add NetBox, monitoring, automation, Git, and documentation one at a time.
   NetBox has its own measured placement plan in [netbox-plan.md](netbox-plan.md);
   it is still planned only, and no NetBox VM, container, or data exists.
5. Recreate isolated security labs separately; never attach Metasploitable to a
   routed bridge.
6. Record each new VM, address, DNS name, persistent-data path, and restore test
   in this catalog or its successor.

The implementation brief for the next agent is in
`docs/homelab-services-deployment-prompt.md`.
