# Home Lab automation ownership

The steady-state Home Lab uses Terraform only for safe Proxmox guest
infrastructure and Ansible for guest operating systems, application containers,
configuration, backups, and validation. Runtime credentials and destructive
recovery decisions remain operator-owned.

## Ownership matrix

| component | infrastructure owner | configuration owner | persistent recovery |
|---|---|---|---|
| VM 300 `homelab-services` | Terraform import-first resource | Ansible guest base | verified Proxmox backup |
| Nginx Proxy Manager | VM 300 boundary | Ansible Compose + HTTPS routes | app archive + VM backup |
| Homepage | VM 300 boundary | Ansible Compose + YAML | Git + VM backup |
| Uptime Kuma | VM 300 boundary | Ansible Compose | application database + VM backup |
| IT-Tools | VM 300 boundary | Ansible Compose | stateless pinned-image redeploy |
| NetKnife | VM 300 boundary | Ansible source sync/build + Compose | source checkout + metadata |
| Linkding | VM 300 boundary | Ansible Compose | SQLite backup + VM backup |
| PairDrop | VM 300 boundary | Ansible Compose | stateless pinned-image redeploy |
| Speedtest Tracker | VM 300 boundary | Ansible Compose + root-only env | SQLite + encrypted credentials |
| VM 310 `observability` | Terraform import-first resource | observability Ansible | verified Proxmox backup |
| Prometheus/Alertmanager/Grafana | VM 310 boundary | observability Ansible | app archive + VM backup |
| Loki/Alloy/exporters | VM 310/300 boundary | observability Ansible | Git; telemetry is disposable |
| NetBox (planned VM 330) | `terraform/netbox-guest`, create-mode, never applied | `netbox_app` / `netbox_backup`, never run | `pg_dump` archive + planned VM backup |
| OpenBao (planned VMs 320–322) | `homelab-openbao` Terraform | `homelab-openbao` Ansible | encrypted Raft snapshots |

## Terraform workflow

Terraform lives in `terraform/homelab-guests`. Checked-in import blocks adopt
VM 300 and VM 310 into an empty state. It manages safe identity/resource
attributes while ignoring pre-existing disks, EFI, cloud-init, serial devices,
and power state. Both resources set `prevent_destroy`, disable purge, and
preserve unreferenced disks.

```bash
export TF_VAR_proxmox_api_token='terraform@pve!home-lab=REDACTED'
make terraform-init
make terraform-fmt
make terraform-validate
make terraform-plan
```

There is no automated apply or destroy target. Store state in an encrypted,
backed-up remote backend before the first reviewed apply.

## VM 300 Ansible workflow

Every application is reconciled independently; there is intentionally no
deploy-all target.

```bash
make homelab-preflight
make homelab-base
make homelab-service SERVICE=npm
make homelab-service SERVICE=homepage
make homelab-service SERVICE=uptime-kuma
make homelab-service SERVICE=it-tools
make homelab-service SERVICE=netknife
make homelab-service SERVICE=linkding
make homelab-service SERVICE=pairdrop
make homelab-service SERVICE=speedtest-tracker
make homelab-backups
```

Before the first Ansible-owned NPM deployment, disable the duplicate UI proxy
hosts for all ten declarative names, retain the wildcard certificate, and run:

```bash
make homelab-service SERVICE=npm EXTRA_JSON='{"homelab_services_allow_npm_route_ownership":true,"homelab_services_npm_route_confirmation":"REPLACE NPM UI PROXY HOSTS WITH DECLARATIVE HOME LAB ROUTES"}'
```

The explicit gate prevents Nginx from receiving competing UI-managed and custom
server blocks. The custom configuration covers the seven VM 300 applications
plus Grafana, Prometheus, and Alertmanager on VM 310.

NetKnife defaults to the reviewed controller checkout at
`/Users/labadmin/Desktop/PROJECTS/NetKnife-App`; override `NETKNIFE_SOURCE` when
using a different checkout.

## VM 310 Ansible workflow

Use the independent gates in `../homelab-observability`:

```bash
make preflight
make bootstrap
make deploy
make deploy-agents
make validate
make backup
```

## Homepage content policy

`templates/homelab-services/stage-d/config/homepage/services.yaml` is the single
source of truth for what the Home Lab claims to be running. Two rules are
enforced by `tests/test_repo_safety.py`:

- Every card outside the "Planned and recovery" group must have both an `href`
  and a `siteMonitor`. A card without a health check is an unverified claim.
- Every entry inside "Planned and recovery" must have neither. Wildcard DNS
  resolves every unconfigured `*.lab.example.com` name to VM 300, so a link or
  a monitor on a planned service would report the NPM fallback page as a healthy
  service.

Internal exporters — Node Exporter, cAdvisor, Alloy, Blackbox, SNMP Exporter,
and PVE Exporter — deliberately have no cards. They have no operator UI and no
documented secure access path; Grafana already presents their data. Loki is the
one exception among non-UI components: it has a real readiness endpoint and its
data is reached through the Grafana "Centralized Logs" dashboard
(`/d/homelab-logs`), which has Host, Job, label, severity, and regex filters.
The dashboard also links through to Explore for raw LogQL.

Deploying a Homepage change is one narrow run:

```bash
make homelab-service SERVICE=homepage
```

Never redeploy the other VM 300 projects to publish a dashboard edit.

## NetBox workflow (planned — never run)

VM 330 does not exist. The automation is staged so that the placement decision
in `netbox-plan.md` is encoded once and reviewed before anything is created.

```bash
make netbox-terraform-init
make netbox-terraform-validate
make netbox-terraform-plan
make netbox-preflight
make netbox-base
make netbox-deploy EXTRA_JSON='{"netbox_app_allow_first_deployment":true,"netbox_app_first_deployment_confirmation":"DEPLOY NETBOX ON VM 330"}'
make netbox-backups
```

`terraform/netbox-guest` is a **separate root** from `terraform/homelab-guests`.
That root is import-first over two live guests; a create-mode resource in it
would make every drift plan for VMs 300 and 310 also propose creating VM 330.
Neither root has an apply or destroy target.

NetBox's two Redis instances are not redundancy. NetBox needs a volatile cache
and a durable RQ queue with different eviction policies; sharing one instance
silently drops queued jobs when the cache evicts.

## Manual and secret boundaries

The following deliberately stay outside Terraform state and Ansible inventory:

- the SMTP provider, Grafana, PVE, SNMPv3, Cloudflare, browser-account, and SSH secrets;
- the router DHCP reservations and Synology DNS records, which lack a safe supported
  provider in this environment;
- NPM first-run account creation and wildcard certificate issuance;
- backup restoration, isolated restore networking, deletion, apply, or destroy.

Secrets stay in root-only runtime files and an encrypted offline backup. Ansible
checks metadata where practical and never prints the values.

## Recovery order

1. Restore the latest verified VM backup with networking isolated.
2. Confirm VMID, MAC, disk, protection, and boot policy.
3. Reconcile Terraform state and review a plan.
4. Run the relevant Ansible preflight.
5. Reconcile one application at a time and verify health after each.
6. Restore application archives only when VM recovery did not retain state.
7. Reinstall runtime secrets from the encrypted operator backup.
8. Re-enable networking and test DNS, HTTPS, authentication, email, dashboards,
   and both backup layers.
