output "netbox_guest" {
  description = "Stable NetBox guest identity used by Ansible inventory and recovery documentation."
  value = {
    id      = proxmox_virtual_environment_vm.netbox.vm_id
    name    = proxmox_virtual_environment_vm.netbox.name
    node    = proxmox_virtual_environment_vm.netbox.node_name
    address = var.netbox_address
    mac     = var.netbox_mac_address
  }
}
