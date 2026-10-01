# Implementation status

Last updated: 2026-08-26.

- [x] Existing Home Lab and pasted requirements reconciled.
- [x] Proxmox/NAS/DNS capacity and collision discovery completed read-only.
- [x] Three-node architecture, failure domains, IP/DNS/TLS/storage plan recorded.
- [x] Terraform VM provisioning and lifecycle protection implemented.
- [x] Gated Ansible host/install/TLS/HA/post-init/backup/monitoring stages implemented.
- [x] Python API, snapshot, verification, PKI, inventory, recovery bundle, and safety tools implemented.
- [x] Policies, AppRoles, secret hierarchy, integration matrix, and pilot selected.
- [x] Offline unit tests and repository safety passed on 2026-08-26.
- [x] the router reservations and explicit Synology DNS records for `bao` / `bao-1` / `bao-2` / `bao-3`.
- [x] dedicated SSH key and pinned guest host fingerprints.
- [x] dedicated bootstrap Proxmox token and reviewed Terraform apply.
- [x] operator-generated bootstrap TLS. Move `offline-root-key.pem` to encrypted custody.
- [x] OpenBao installation/configuration to the uninitialized gate (`initialized=false`).
- [ ] Point `bao.lab.example.com` at NPM `192.168.0.30` (VIP stays on `.5.19` for HAProxy).
- [ ] attended five-share/three-threshold initialization and unseal.
- [ ] post-init configuration, initial root-token revocation, and recovery auth.
- [ ] Synology restricted SFTP account/share and external age identity.
- [ ] first backup plus offline inspection and isolated restore drill.
- [ ] VM 310 Alloy/Prometheus integration and alert proof.
- [ ] read-only PVE exporter token pilot, rotation, and rollback proof.
- [ ] one-node/one-host/VIP/Synology outage tests and controlled onboot gate.
