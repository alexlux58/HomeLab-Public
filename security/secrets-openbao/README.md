# Home Lab OpenBao

Staged infrastructure-as-code and recovery documentation for a private,
three-node OpenBao Raft cluster across the existing three Proxmox hosts.

This repository does **not** initialize OpenBao, contain secrets, or provide an
end-to-end deploy command. The normal endpoint will be
`https://bao.lab.example.com:8200`; each node also has a direct recovery name.

## Why three nodes

The Proxmox cluster has three physical failure domains and enough measured
capacity for one 2 GiB OpenBao voter per host. Three voters tolerate one failed
OpenBao VM or one failed Proxmox host. A single node would be smaller, but it
would turn routine host failure into a secrets outage and is rejected for this
environment.

Raft data stays on each VM's local disk. The Synology receives encrypted,
application-consistent Raft snapshots and configuration/recovery bundles; it is
not required for normal reads, writes, leader election, or unseal.

## Safe starting point

```bash
make setup
make check
make terraform-init
make terraform-validate
make terraform-plan
```

`terraform-plan` requires a dedicated Proxmox API token through
`TF_VAR_proxmox_api_token`; it is never stored here. There is intentionally no
Make target for apply or destroy.

After the operator reserves the four addresses, creates the DNS records,
generates the SSH key, reviews the plan, and explicitly approves provisioning,
follow [bootstrap.md](docs/bootstrap.md). Stop at the uninitialized validation
gate. [unseal.md](docs/unseal.md) is the attended initialization ceremony.

## Repository map

- `terraform/`: three protected local-disk VMs, one per Proxmox host.
- `ansible/`: independently gated OS, TLS, server, backup, and monitoring stages.
- `openbao/`: policies and non-secret declarative inputs.
- `scripts/`: standard-library recovery, validation, and API tools.
- `integrations/`: product-specific runtime delivery patterns.
- `docs/`: human architecture, operations, recovery, and threat-model guides.

Start with [architecture.md](docs/architecture.md),
[integration-matrix.md](docs/integration-matrix.md), and
[restore-runbook.md](docs/restore-runbook.md).
