# Phase 1 rename map

This map records the source-only naming normalization performed during Phase 1.
It does not rename a running host, VM, container, share, URL, or Plex library.

| Previous identifier | Repository identifier | Reason |
| --- | --- | --- |
| `pve146` | `pve1` | Stable node role name |
| `pve180` | `pve2` | Stable node role name |
| `pve222` | `pve3` | Stable node role name |
| `join-222` | `join-pve3` | Names the node role rather than a host-number suffix |
| `NN_name.yml` | `NN-name.yml` | One two-digit lifecycle prefix and kebab-case playbook name |
| `compose.yaml` | `compose.yaml` | One Compose filename convention |
| `name_with_underscores.sh` | `name-with-underscores.sh` | Kebab-case shell script convention |

Raw addresses and guest IDs remain values in the operator-controlled inventory
until the Phase 3 single-source-of-truth work. They are not hostnames.
