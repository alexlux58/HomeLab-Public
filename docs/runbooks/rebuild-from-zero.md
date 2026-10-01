# Rebuild from zero (L0 → L8)

How to rebuild the whole lab from bare metal with this repository plus the
backups in `docs/reference/backup-matrix.yml`. Climb one rung at a time:

- Every step is **one** Make target or one manual action. No target chains
  steps (tested), and there is no aggregate target of any name.
- Run the step's `verify` before the next step. Stop on any surprise.
- Gates are passed as `EXTRA_JSON`, for example
  `make -C platform/proxmox rebuild-l1-host-config EXTRA_JSON='{"pve_host_config_allow":true,"pve_host_config_confirmation":"L1 CONFIGURE pve pve1 pve2"}'`.
  An agent prepares these strings (skill `run-gated-stage`); only the
  operator supplies them.
- `make rebuild-plan` prints this ladder and checks local prerequisites
  offline (tools, `null` inputs in `inventory/lab.yml`, `backend.hcl`, which
  environment variables are set — never their values).

Before starting: read `docs/reference/lessons-learned.md` (cloud-init
regenerates host keys on stopped guests; `/etc/pve` symlinks; the the router must
never own `lab.example.com`), `docs/reference/operator-inputs.md` (L7) and
`docs/reference/coverage-matrix.yml` (what is declared, restored or manual).

Known gaps that affect a rebuild are listed in `MEMORY.md`. In particular:
live OpenTofu state is still only in the Phase 1 source archive (ADR-0003),
and NFS storage registration has a flag-only gate.

## The ladder

The table is generated from `docs/runbooks/rebuild-ladder.yml`
(`python3 tools/rebuild/rebuild_plan.py --markdown`); edit the YAML, not the
table. A test fails if they differ.

<!-- BEGIN GENERATED LADDER -->
### L0 — Bare metal and base installs

| Step | Command | Gate | Inputs | Duration | Verify | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `l0-proxmox-answer-files` | `make -C platform/proxmox rebuild-l0-answer-files NODE=<node> WRITE=1` | local: Writes git-ignored files only; secrets come from the operator's environment | lab.yml nodes.<node>.install.{fqdn,disk_filter,interface_filter}; PVE_ROOT_PASSWORD_HASH; PVE_ROOT_SSH_KEYS_FILE; PVE_MAILTO | 5 min | proxmox-auto-install-assistant validate-answer artifacts/autoinstall/<node>.toml | Discard the generated file; nothing outside the controller changed. |
| `l0-proxmox-install` | manual | manual: ISO preparation and console install are operator steps by design | PVE 9 ISO; answer file from l0-proxmox-answer-files | 30 min per node | Compare the console host-key fingerprint with lab.yml nodes.<node>.host_fingerprint, then `ssh <alias> pveversion` | Reinstall the node; no guest exists yet. |
| `l0-nas` | manual | manual: DSM has no provider; NAS admin credentials are the operator's | DSM configuration backup; lab.yml nas | 2 h plus RAID resync | `ssh nas` succeeds with the pinned key; shares proxmox-cluster-backups, Media and media-backups exist | Restore the DSM configuration backup. |
| `l0-workstation` | manual | manual: workstation stays Windows and is never wiped by automation | Operator's own Windows backup | operator-dependent | `ssh workstation hostname` returns workstation | Not applicable; nothing in this repository changes Windows. |
| `l0-media-guest` | manual | manual: VirtualBox lifecycle on workstation is attended | services/media/config/cloud-init/user-data.yml.tmpl; admin public key | 30 min | make -C services/media preflight | Delete only the new VM; the retained media-vm disks are never touched. |

Operator actions:

- `l0-proxmox-install`: proxmox-auto-install-assistant prepare-iso <pve.iso> --fetch-from iso --answer-file <node>.toml; boot the node from it; pin the host key after verifying it at the console.
- `l0-nas`: Restore DSM, recreate shares (proxmox-cluster-backups on Volume 1, Media and media-backups on Volume 2), the plex-reader and media-backup accounts, NFS export for the cluster, and the split-horizon DNS zone from lab.yml dns_records.
- `l0-workstation`: Restore Windows from the operator's backup, then install VirtualBox, Plex Media Server and qBittorrent. Plex claim and the client-scoped firewall rule stay attended (L5).
- `l0-media-guest`: Create a 2 vCPU / 4 GiB VM with a 50 GiB data disk, NAT with a loopback-only SSH forward, fill the cloud-init template, build the seed with cloud-localds, attach it and boot.

### L1 — Host configuration

| Step | Command | Gate | Inputs | Duration | Verify | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `l1-nfs-storage` | `make -C platform/proxmox nas-preflight` | `allow_configure_nfs_storage` (flag only) — gap: Flag-only gate predates Phase 3; add a confirmation string | NAS NFS export for the cluster | 10 min | pvesh get /nodes/<node>/storage/synology-backup/status on each node shows active | pvesm remove synology-backup (removes the storage definition only, never archives). |
| `l1-host-config` | `make -C platform/proxmox rebuild-l1-host-config` | `pve_host_config_allow` + `L1 CONFIGURE pve pve1 pve2` | inventory/lab.yml backup_jobs and guest onboot/startup | 5 min | pvesh get /cluster/backup lists every lab.yml backup job | Disable a created job in the UI (never delete archives); qm set <vmid> --onboot 0. |

### L2 — Cluster

| Step | Command | Gate | Inputs | Duration | Verify | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `l2-create-cluster` | `make -C platform/proxmox create-cluster` | `allow_create_cluster` + `CREATE CLUSTER homelab ON pve1 192.168.0.11` | three nodes installed and configured | 10 min | pvecm status on pve1 shows one node, quorate | Reinstall pve1 (no guests exist yet). |
| `l2-join-pve3` | `make -C platform/proxmox join-pve3` | `allow_join_pve3` + `JOIN pve3 192.168.0.13 TO homelab` | root password prompt answered at the console (pvecm add is manual) | 15 min | pvecm status shows two nodes, quorate | Reinstall pve3 and rejoin. |
| `l2-join-pve2` | `make -C platform/proxmox join-pve2` | `allow_join_pve2` + `JOIN pve2 192.168.0.12 TO homelab` | root password prompt answered at the console | 15 min | pvecm status shows three nodes, three votes, quorate | Reinstall pve2 and rejoin. |

### L3 — Guests

| Step | Command | Gate | Inputs | Duration | Verify | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `l3-state-backend` | manual | manual: State migration is the operator's (ADR-0003); agents never migrate state | D:/homelab-state mounted in devcontainer; encrypted NAS state copy or archived plaintext source; per-root TF_VAR_state_passphrase | 30 min per root | tofu plan shows no changes after migration | Keep using the archived local state; delete nothing until the plan is clean. |
| `l3-guests-plan` | `make -C platform/proxmox rebuild-guests-plan REBUILD_VARS='-var-file=rebuild.tfvars'` | `rebuild_guests` + `REBUILD <sorted guest names> FROM ZERO` | backend.hcl (ADR-0003); TF_VAR_proxmox_api_token; TF_VAR_state_passphrase; git-ignored rebuild.tfvars with names, confirmation and public keys | 10 min | The saved plan creates only the named VMIDs with lab.yml MACs, off and protected. | Discard the plan file. |
| `l3-guests-apply` | manual | manual: There is no apply target; the operator applies the reviewed plan | rebuild.tfplan from l3-guests-plan | 20 min | qm list on each node shows the new VMIDs stopped; qm config shows protection: 1 | Guests are protected and prevent_destroy is set; removing one is a separate attended decision. |
| `l3-eveng-restore` | manual | manual: Restores overwrite a VMID; attended by design | latest verified VM 290 archive on synology-backup | 1 h | qm config 290 matches the archive; boot with link_down on every NIC first | Leave the restored VM stopped and protected. |

Operator actions:

- `l3-state-backend`: Follow docs/runbooks/state-migration.md in order (OpenBao, NetBox, homelab-guests import-first). Restore encrypted NAS state or re-adopt by import; require a no-change plan before any apply.
- `l3-guests-apply`: tofu -chdir=platform/proxmox/terraform/rebuild-guests apply rebuild.tfplan
- `l3-eveng-restore`: qmrestore <archive> 290 --storage local on pve1, then verify.

### L4 — Guest base configuration

| Step | Command | Gate | Inputs | Duration | Verify | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `l4-vm300-base` | `make -C platform/proxmox homelab-base` | `homelab_allow_guest_config` + `CONFIGURE GUEST homelab-services` | VM 300 host key verified out of band through the guest agent | 15 min | make -C platform/proxmox homelab-preflight | Re-run with the previous commit's configuration. |
| `l4-vm310-bootstrap` | `make -C observability bootstrap` | `observability_allow_bootstrap` + `BOOTSTRAP observability` | VM 310 host key verified out of band | 15 min | make -C observability preflight | Re-run with the previous commit's configuration. |
| `l4-vm330-base` | `make -C platform/proxmox netbox-base` | `netbox_allow_guest_config` + `CONFIGURE GUEST netbox` | VM 330 host key verified out of band | 15 min | make -C platform/proxmox netbox-preflight | Re-run with the previous commit's configuration. |
| `l4-openbao-hosts` | `make -C security/secrets-openbao prepare-hosts` | `allow_prepare_openbao_hosts` + `PREPARE OPENBAO HOSTS 320 321 322` | VMs 320-322 host keys verified out of band | 20 min | make -C security/secrets-openbao preflight | Re-run with the previous commit's configuration. |
| `l4-media-host` | `make -C services/media configure-host` | `media_host_allow` + `MEDIA HOST media-vm` | /etc/media/secrets/cifs.cred installed root:root 0600 | 10 min | make -C services/media preflight | Unmount the shares; packages and directories are harmless to leave. |

### L5 — Applications and their configuration

| Step | Command | Gate | Inputs | Duration | Verify | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `l5-vm300-apps` | `make -C platform/proxmox homelab-service SERVICE=<app>` | `homelab_allow_service_deploy` + `DEPLOY <app> ON homelab-services` | /etc/homelab/secret-store/* for the app; one app per run | 10 min per app | Homepage card for the app turns green; uptime_kuma_monitors.py reports no drift | Re-deploy the app from the previous commit. |
| `l5-npm-routes` | `make -C platform/proxmox homelab-service SERVICE=npm` | `homelab_services_allow_npm_route_ownership` + `REPLACE NPM UI PROXY HOSTS WITH DECLARATIVE HOME LAB ROUTES` | wildcard certificate DNS-01 credential | 15 min | every lab.yml proxied site answers over HTTPS | Restore NPM data from the L6 application backup. |
| `l5-dns-records` | manual | manual: Synology DNS has no provider | lab.yml dns_records | 20 min | dig @192.168.0.20 <site>.lab.example.com returns 192.168.0.30 | Revert the record in DSM. |
| `l5-observability` | `make -C observability deploy` | `observability_allow_deploy` + `DEPLOY OBSERVABILITY STACK ON observability` | /etc/observability/secret-store/* (L7 table) | 20 min | make -C observability validate | Restore the observability archive (L6). |
| `l5-netbox` | `make -C platform/proxmox netbox-deploy` | `netbox_allow_deploy` + `DEPLOY NETBOX ON netbox` | NetBox secrets; on a first deployment also netbox_app_allow_first_deployment with "DEPLOY NETBOX ON VM 330" | 20 min | make -C platform/proxmox netbox-preflight | Restore the pg_dump backup (L6). |
| `l5-netbox-seed` | manual | manual: Automation never writes to NetBox | lab.yml | 15 min | NetBox lists every lab.yml node, guest and address | Delete the imported objects in NetBox. |
| `l5-openbao-install` | `make -C security/secrets-openbao install-server` | `allow_install_openbao` + `INSTALL OPENBAO 2.6.1 WITHOUT INITIALIZING` | signed OpenBao 2.6.1 binary | 15 min | make -C security/secrets-openbao validate-uninitialized | Stop and disable the service. |
| `l5-openbao-tls` | `make -C security/secrets-openbao configure-tls` | `allow_configure_openbao_tls` + `DEPLOY OPENBAO TLS TO THREE NODES` | operator-issued node certificates from the offline root | 15 min | make -C security/secrets-openbao validate-uninitialized | Re-deploy the previous certificates. |
| `l5-openbao-ha` | `make -C security/secrets-openbao configure-ha` | `allow_configure_openbao_ha` + `CONFIGURE OPENBAO RAFT AND VIP UNINITIALIZED` | VIP 192.168.0.40 reserved | 15 min | make -C security/secrets-openbao validate-uninitialized | Stop Keepalived and HAProxy. |
| `l5-media-arr` | `make -C services/media deploy-arr` | `arr_stack_allow` + `MEDIA DEPLOY media-vm` | /etc/media/secrets/*.env installed root:root 0600 | 15 min | Radarr and Prowlarr answer on workstation's loopback forwards; up{host="media-vm"} appears in Prometheus | docker compose down in /opt/lux-media, then restore *arr backups (L6). |
| `l5-media-arr-config` | `make -C services/media arr-plan` | manual: Apply is manual after the plan is reviewed; no apply target exists | backend.hcl; TF_VAR_radarr_api_key; TF_VAR_prowlarr_api_key; TF_VAR_qbittorrent_*; TF_VAR_state_passphrase | 10 min | The plan shows only the root folder, qBittorrent client, remote path mapping and Prowlarr link. | Restore the Radarr/Prowlarr backup zip (L6). |
| `l5-media-profiles` | `make -C services/media sync-quality-profiles` | `arr_stack_allow_recyclarr_sync` + `RECYCLARR SYNC media-vm` | /etc/media/secrets/recyclarr.env | 5 min | The preview (no gate) shows no changes after a real sync. | Restore the Radarr backup zip (L6). |
| `l5-plex` | manual | manual: Claim, client firewall rule and library apply are attended | Plex claim session; PLEX_TOKEN; first client IP | 30 min | python services/media/scripts/plex_libraries.py | Remove the library in Plex; NAS media is untouched. |
| `l5-uptime-kuma` | manual | manual: Uptime Kuma 2 has no supported write API | services/homelab-services/config/uptime-kuma/monitors.yml | 20 min | python services/homelab-services/scripts/uptime_kuma_monitors.py --dump <latest dump> | Remove the monitor in the UI. |

Operator actions:

- `l5-dns-records`: Create the A records in lab.yml dns_records in Synology DNS Server.
- `l5-netbox-seed`: python services/netbox/scripts/netbox_seed_csv.py --out <dir>, then bulk import the three files in order.
- `l5-plex`: Claim Plex in the operator's browser, add the client-scoped firewall rule by hand, then run plex_libraries.py plan and, with PLEX_ALLOW_APPLY=true and PLEX_CONFIRMATION="PLEX LIBRARIES workstation", --apply.
- `l5-uptime-kuma`: Create each monitor in monitors.yml in the Uptime Kuma UI.

### L6 — Data restore (isolated first)

| Step | Command | Gate | Inputs | Duration | Verify | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `l6-restore-drills` | manual | manual: Restores run only against an isolated VM or network, attended | docs/reference/backup-matrix.yml | 1-4 h | Each backup-matrix row's verify command passes on the isolated copy. | Discard the isolated copy; production was never touched. |
| `l6-backup-pull` | `make -C platform/proxmox configure-backup-pull` | `allow_backup_pull` + `INSTALL BACKUP PULL ON <inventory-node> <address>` | dedicated public key; least-loaded mounted node; verified host pins; D free space | 10 min plus archive copy | Install the local task; size and SHA-256 match NAS before and after the first pull. | Disable only this task and separately remove only its public key; retain every copy. |
| `l6-media-backups` | `make -C services/media configure-backup` | `media_backup_allow` + `MEDIA BACKUP media-vm` | media-backups share mounted | 5 min | systemctl list-timers arr-backup.timer on the guest | systemctl disable --now arr-backup.timer (copies are kept). |

Operator actions:

- `l6-restore-drills`: Follow every row of docs/reference/backup-matrix.yml, one at a time.
- `l6-backup-pull`: Follow platform/proxmox/docs/backup-pull.md; stop for the exact node confirmation.

### L7 — Attended secrets and ceremonies

| Step | Command | Gate | Inputs | Duration | Verify | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `l7-openbao-init` | manual | manual: bao operator init/unseal is an attended ceremony; never automated | five PGP recipients; threshold three | 1 h | make -C security/secrets-openbao validate-post-init | None automated; see security/secrets-openbao/docs/restore-runbook.md. |
| `l7-operator-inputs` | manual | manual: Secrets are installed by the operator only | docs/reference/operator-inputs.md | 1 h | Each stage's secret-file metadata check passes (root:root 0600). | Rotate the affected credential. |

Operator actions:

- `l7-openbao-init`: Run the ceremony by hand, then `make -C security/secrets-openbao configure-post-init` with its gate.
- `l7-operator-inputs`: Install or rotate each row of docs/reference/operator-inputs.md.

### L8 — Validate and enable onboot

| Step | Command | Gate | Inputs | Duration | Verify | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `l8-validate-cluster` | `make -C platform/proxmox validate` | read-only: Validation only | — | 10 min | The report shows every check passing. | Not applicable. |
| `l8-validate-observability` | `make -C observability validate` | read-only: Validation only | — | 5 min | make -C observability validate passes with changed=0. | Not applicable. |
| `l8-onboot` | `make -C platform/proxmox rebuild-l1-host-config` | `pve_host_config_allow` + `L1 CONFIGURE pve pve1 pve2` | lab.yml onboot set to true only for guests whose L6 drill passed | 5 min | A controlled node reboot brings the chosen guests back. | Set onboot back to false in lab.yml and re-run. |
<!-- END GENERATED LADDER -->
