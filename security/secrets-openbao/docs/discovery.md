# Read-only discovery — 2026-08-24

No live state was changed during this discovery.

## Proxmox

The `homelab` cluster is quorate with three votes and quorum of two.

| physical node | version | available memory | current guests | storage implication |
|---|---|---:|---|---|
| `pve1` | PVE 9.2.11 | 20.6 GiB | 290 running, 297 stopped, 310 running | `local` NVMe directory |
| `pve2` | PVE 9.2.11 | 3.7 GiB | 300 running, 399 stopped | `local-lvm` on HDD |
| `pve3` | PVE 9.2.2 | 5.7 GiB | none | `local-lvm` on SSD |

VMIDs 320–322 and MACs `52:54:00:00:00:00` through `:22` do not collide with
the current cluster. The pve2 is the limiting node; its OpenBao voter is fixed
at 2 GiB. Re-run discovery before increasing any allocation or starting restore
VM 399 concurrently.

Local guest storage is not shared. Proxmox HA and live migration are therefore
not part of the OpenBao availability model. OpenBao's own Raft replicas provide
service availability.

## Network and DNS

- LAN: `192.168.0.0/24`, gateway `192.168.0.1`, no VLAN-aware bridge.
- Synology DNS: `192.168.0.20`.
- Existing wildcard behavior makes `bao.lab.example.com` resolve to
  `192.168.0.30`; this is not the desired OpenBao record.
- Candidate addresses `.5.19`–`.5.22` did not answer ICMP and had no local ARP
  entries. That is not proof they are free; the router reservations are mandatory.

Required records after reservations:

| record | address |
|---|---|
| `bao.lab.example.com` | `192.168.0.40` VIP |
| `bao-1.lab.example.com` | `192.168.0.41` |
| `bao-2.lab.example.com` | `192.168.0.42` |
| `bao-3.lab.example.com` | `192.168.0.43` |

## Synology

`nas1` is a the NAS ARM64 NAS. `/volume1` is Btrfs, 11 TiB, about 4% used.
It already supports Home Lab NFS backups. The OpenBao plan uses a new restricted
SFTP account and `OpenBaoBackups/` tree; neither exists until the operator creates
and approves it. Synology is never a Raft disk or required runtime dependency.

## Existing systems retained

- VM 300 applications, Nginx Proxy Manager, DNS/TLS, SMTP, application backups,
  VM backup, and isolated restore are already working; do not redeploy them.
- VM 310's ten-container observability stack is working; add OpenBao targets and
  agents through its existing Ansible repository instead of building a second
  monitoring stack.
- Browser logins remain in macOS Keychain with the index at
  `~/.local-credentials/home-lab`; OpenBao is not the sole break-glass store.

## Secret-reference review

The value-blind scanner recorded 81 current files containing secret-related key
names; it stores only filenames and variable names. Git-history filename review
found no candidate in the migration repository and only the expected
`docker/.env.example` and `docs/secrets.md` in observability. This is not proof
that no historical value was ever exposed. Before each credential migration,
rotate at the source and perform a targeted value-independent history/artifact
review using key names and known file locations.
