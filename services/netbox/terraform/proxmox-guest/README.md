# NetBox guest (planned — not applied)

Create-mode Terraform for the planned NetBox VM. **Nothing here has been
applied.** No VM 330 exists on the cluster.

This is a separate root from `../homelab-guests` deliberately. That root is
import-first and adopts the two live protected guests; a create-mode resource
there would make every routine drift plan also propose a brand-new VM.

## Placement

Measured on 2026-08-25 and recorded in `../../docs/netbox-plan.md`.
`pve3` is the only node with an SSD, zero guests, and free RAM.

| item | value |
|---|---|
| VMID | 330 |
| node | `pve3` |
| resources | 2 vCPU, 3 GiB fixed, 32 GiB on `local-lvm` (SSD thin pool) |
| address | `192.168.0.50/24` — needs an the router reservation first |
| MAC | `52:54:00:00:00:00` — verified unique against every cluster guest |
| policy | `protection = true`, `on_boot = false`, `started = false` |

## Prerequisites, in order

1. Approve the placement in `../../docs/netbox-plan.md`.
2. Reserve `192.168.0.50` for `52:54:00:00:00:00` on the the router.
3. Create the explicit Synology DNS A record for `netbox.lab.example.com`.
   Wildcard DNS currently sends that name to VM 300.
4. `ssh-keygen -t ed25519 -a 100 -f ~/.ssh/homelab_netbox_ed25519 -C homelab-netbox`
   and put the public key in `terraform.tfvars`.

## Plan only

```bash
export TF_VAR_proxmox_api_token='terraform@pve!home-lab=REDACTED'
terraform -chdir=terraform/netbox-guest init
terraform -chdir=terraform/netbox-guest fmt -check
terraform -chdir=terraform/netbox-guest validate
terraform -chdir=terraform/netbox-guest plan
```

There is intentionally **no** `apply` or `destroy` Make target for this root, and
a repository test fails the build if one is added. Applying is a separate manual
operator action after the plan is reviewed. Store state in an encrypted,
backed-up remote backend before the first apply.

## What this root does not own

Application containers, PostgreSQL, secrets, DNS records, the NPM proxy host,
backups, and restores. Those belong to the gated Ansible stages in
`../../playbooks/11*_netbox_*.yml`.
