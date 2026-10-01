# Threat model

## Protected assets

- application and infrastructure credentials;
- Raft encryption data and snapshots;
- unseal shares and initial/break-glass root tokens;
- offline root CA and backup decryption identity;
- TLS and AppRole private material;
- audit history.

## Trust boundaries

The LAN is trusted for routing, not confidentiality. OpenBao API and Raft use
private-CA TLS. TCP 8200 is LAN-scoped; 8201 and VRRP peer traffic are limited to
the three node addresses. SSH is key-only and LAN-scoped. No router port-forward
or Cloudflare public proxy is permitted.

The Proxmox administrators can inspect VM memory/disks and remain highly
privileged. Synology administrators can delete backups but cannot decrypt them
without the separately held age identity. Loki/Grafana operators can see
sensitive audit events and must be limited to the operator.

## Primary risks and controls

| risk | control |
|---|---|
| secret committed to Git/state/logs | runtime files, `no_log`, state warning, secret-name-only scan, CI safety scan |
| one host loss | one voter per physical host, three-voter quorum |
| backup unusable | signed manifests, age encryption, checksum, scheduled offline inspect and isolated restore |
| OpenBao locks out recovery | browser/Proxmox/NAS break-glass credentials remain outside OpenBao; backup key external |
| stolen AppRole SecretID | CIDR bounds, short TTL, least policy, documented rotation |
| audit device fills/fails | local disk alert, logrotate with SIGHUP, audit-failure alerts |
| unseal shares colocated | D4: sole operator, five offline PGP keys in five separate custody places, threshold three; protects two lost places, not operator coercion |
| compromised offline root | offline custody, intermediate-only online PKI, root rotation plan |
| malicious/accidental IaC destroy | VM protection, Terraform `prevent_destroy`, no destroy target, exact gates |

## Explicit non-goals

OpenBao does not protect against a fully compromised Proxmox administrator or
an operator who deliberately supplies three unseal shares. It does not replace
offline credential escrow, host backups, application backups, or network
segmentation.
