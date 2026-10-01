# Terraform ownership of Home Lab guests

This root adopts protected VM 300 `homelab-services` and VM 310
`observability`. It intentionally manages stable identity, placement, CPU,
memory, NIC, startup, and protection settings. Existing disks, EFI variables,
cloud-init media, serial devices, and current power state are ignored because
they predate Terraform and contain recoverable production state.

The provider is pinned to `bpg/proxmox` 0.107.0. The newer `proxmox_vm`
resource is still explicitly marked experimental by its publisher, so this
configuration uses the mature `proxmox_virtual_environment_vm` resource.

## First adoption

Create a dedicated least-privilege Proxmox token and export it locally. Do not
write it into Git, a tfvars file, shell history, CI output, or chat.

```bash
export TF_VAR_proxmox_api_token='terraform@pve!home-lab=REDACTED'
make terraform-init
make terraform-plan
```

The checked-in import blocks make the first plan import `pve2/300` and
`pve1/310` instead of proposing duplicate guests. Review every plan. There is
deliberately no Make target for `terraform apply` or `terraform destroy`.

Store Terraform state in an encrypted, backed-up remote backend before the
first apply. Local state files are ignored but are not an acceptable durable
backend.

## Failure recovery

Terraform does not recreate or delete guest disks. Recover VM 300 or VM 310
from the latest verified Proxmox backup, confirm its isolated boot, restore its
original VMID/MAC, then run Terraform import/plan and the relevant Ansible
playbooks. This preserves the tested backup-first recovery path and prevents a
mistaken Terraform operation from deleting an unmanaged disk.
