# Operator inputs (L7)

Every secret or attended input the lab depends on: what it is, where it lives,
and when it is used. **No value is ever stored in Git, printed, or handled by an
agent.** Installed files are root-owned mode 0600 and checked by metadata only.
OpenBao initialization and unsealing stay attended.

| Input | What it is | Where it lives | Used at |
| --- | --- | --- | --- |
| Proxmox root password hash | crypt(3) hash for answer files | Operator password manager; `PVE_ROOT_PASSWORD_HASH` at build time | L0 |
| Root SSH public keys | Keys baked into answer files | `PVE_ROOT_SSH_KEYS_FILE` (public keys only) | L0 |
| Notification address | `mailto` for answer files | `PVE_MAILTO` at build time | L0 |
| Node install inputs | FQDN, disk and NIC filters | `inventory/lab.yml` `nodes.*.install` (not secret) | L0 |
| DSM admin credentials | NAS administration | Operator password manager; never in automation | L0, L1 |
| Cluster SSH key | `~/.ssh/proxmox_cluster_ed25519` | Operator controller only | L1–L3, L8 |
| Root password prompt for `pvecm add` | Join authentication | Typed by the operator at the prompt | L2 |
| Proxmox API token | Dedicated token for OpenTofu | `TF_VAR_proxmox_api_token` in the operator shell | L3 |
| State passphrase | Per-root PBKDF2/AES-GCM state and plan encryption | Operator password manager; `TF_VAR_state_passphrase` in local devcontainer only | L3, L5 (*arr) |
| State locations | D1 local backend and encrypted NAS copies | `D:\homelab-state\<root>\`; NAS `proxmox-cluster-backups/opentofu-state/<root>/` | L3 |
| Guest admin SSH keys | Per-guest keys (`homelab_services_ed25519`, `homelab_observability_ed25519`, `homelab_netbox_ed25519`, OpenBao key) | Operator controller; public halves in `rebuild.tfvars` (git-ignored) | L3–L5 |
| Guest host-key pins | Fingerprints verified out of band (guest agent) | `known_hosts`; recorded in `lab.yml` | L4 |
| VM 300 app secrets | NetKnife, Speedtest SMTP, DNS-01 credential, … | `/etc/homelab/secret-store/` on VM 300 | L5 |
| Observability secrets | PVE exporter token, Grafana admin, SNMPv3, SMTP | `/etc/observability/secret-store/` on VM 310 | L5 |
| NetBox superuser and API token | NetBox administration | Operator-installed on VM 330 | L5 |
| OpenBao TLS material | Node certificates from the offline root | Operator-installed on VMs 320–322 | L5 |
| Offline root CA key | Signs OpenBao node certificates | `~/.local-credentials/home-lab/openbao/pki/` → move to encrypted custody | L5 |
| OpenBao unseal shares | Five PGP-encrypted shares, threshold three | D4: sole operator, five offline keys/places; only public keys/fingerprints near Git or agents; never on NAS | L7, attended 2026-10-10; verify VM 320–322 archives the day before |
| OpenBao backup age identity | Decrypts Raft snapshots | Outside OpenBao and the NAS | L6 |
| NAS CIFS credential (media) | `plex-reader`/media account for the guest mounts | `/etc/media/secrets/cifs.cred` on media-vm | L4 |
| Radarr / Prowlarr API keys | App API keys | `/etc/media/secrets/*.env` on the guest; `TF_VAR_radarr_api_key`, `TF_VAR_prowlarr_api_key` for the *arr root | L5 |
| qBittorrent Web UI login | Download client credentials | `TF_VAR_qbittorrent_username`, `TF_VAR_qbittorrent_password`; qBittorrent on Windows | L5 |
| Plex claim | One-time claim in the operator's browser | Never stored | L5 (attended) |
| Plex token | `PLEX_TOKEN` for the library script | Operator password manager; also inside `Preferences.xml` backups | L5, L6 |
| Media guest connection | SSH forward port and admin user | `inventory/host_vars/media-vm.yml` (git-ignored) | L4–L6 |
| Backup pull private key | Dedicated passphrase-free ED25519 key; operator generates it | `~/.ssh/homelab_backup_pull_ed25519` on workstation only; agent handles only `.pub` | L6 |
| Backup node public key | Public ED25519 host key, compared with lab.yml fingerprint before pinning | `D:\homelab-backups\control\known_hosts` after verification | L6 |
| Rotation list | Credentials that must be rotated | `MEMORY.md` → Rotation list | L7 |
