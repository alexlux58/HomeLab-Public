# Automation boundary

Terraform ownership for VM 310 lives in
`../../platform/proxmox/terraform/homelab-guests`. It adopts the existing
protected guest and manages safe identity/resource attributes without owning,
replacing, or deleting VM disks.

This repository's Ansible owns the Ubuntu guest, Docker Engine, firewall,
central Prometheus/Alertmanager/Grafana/Loki/Alloy stack, exporters, agents,
backups, and runtime validation. Existing playbooks remain separate gates:

```bash
make preflight
make bootstrap
make deploy
make deploy-agents
make validate
make backup
```

Runtime credentials remain root-only under `/etc/observability/secret-store` and are
excluded from Terraform, inventory, Git, logs, archives, and chat. Recovery is
backup-first: restore VM 310 isolated, confirm identity, reconcile Terraform
state, run Ansible preflight/deploy/validate, reinstall encrypted secrets, and
then restore application data only if needed.

Alertmanager is the only externally reachable central service that runs as
container root, solely because local Compose cannot translate a root-only
file-backed secret. Its filesystem is read-only, every capability is dropped,
and the host secret remains `root:root` mode 0600.
