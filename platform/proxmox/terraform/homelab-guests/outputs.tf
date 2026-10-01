output "managed_guests" {
  description = "Stable Home Lab guest identity map used by Ansible and recovery documentation."
  value = {
    homelab_services = {
      id      = proxmox_virtual_environment_vm.homelab_services.vm_id
      name    = proxmox_virtual_environment_vm.homelab_services.name
      node    = proxmox_virtual_environment_vm.homelab_services.node_name
      address = "192.168.0.30"
    }
    observability = {
      id      = proxmox_virtual_environment_vm.observability.vm_id
      name    = proxmox_virtual_environment_vm.observability.name
      node    = proxmox_virtual_environment_vm.observability.node_name
      address = "192.168.0.31"
    }
  }
}
