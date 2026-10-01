# Import-first adoption prevents an empty Terraform state from proposing new
# VMs over the two live, protected guests.
import {
  to = proxmox_virtual_environment_vm.homelab_services
  id = "pve2/300"
}

import {
  to = proxmox_virtual_environment_vm.observability
  id = "pve1/310"
}
