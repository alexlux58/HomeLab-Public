# Version matrix

| component | pinned version | reason |
|---|---:|---|
| OpenBao | 2.6.1 | Current stable release reviewed 2026-08-24; install verifies the signed upstream checksum manifest |
| Ubuntu | 24.04 LTS | Matches VMs 300/310 and existing operational knowledge |
| Terraform | >= 1.8, < 2.0 | Current configuration language and lifecycle checks |
| bpg/proxmox | 0.107.0 | Same tested provider pin as existing Home Lab VM adoption root |
| Ansible Core | 2.19.2 | Pinned controller dependency |

Upgrades are one component and one Raft node at a time. Review
`docs/upgrades.md` before changing any pin.
