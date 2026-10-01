locals {
  managed_description = "Home Lab infrastructure: Terraform identity/resources, Ansible guest configuration"
}

resource "proxmox_virtual_environment_vm" "homelab_services" {
  vm_id       = 300
  name        = "homelab-services"
  node_name   = var.homelab_services_node
  description = local.managed_description
  tags        = ["homelab-services", "terraform", "ansible"]

  protection                           = true
  on_boot                              = true
  started                              = true
  reboot_after_update                  = false
  stop_on_destroy                      = false
  purge_on_destroy                     = false
  delete_unreferenced_disks_on_destroy = false

  cpu {
    cores   = 4
    sockets = 1
    type    = "host"
  }

  memory {
    dedicated = 6144
    floating  = 0
  }

  network_device {
    bridge      = "vmbr0"
    firewall    = true
    mac_address = "52:54:00:00:00:00"
    model       = "virtio"
  }

  startup {
    order      = "1"
    up_delay   = "30"
    down_delay = "120"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      description,
      disk,
      efi_disk,
      initialization,
      serial_device,
      started,
    ]
  }
}

resource "proxmox_virtual_environment_vm" "observability" {
  vm_id       = 310
  name        = "observability"
  node_name   = var.observability_node
  description = local.managed_description
  tags        = ["observability", "terraform", "ansible"]

  protection                           = true
  on_boot                              = false
  started                              = true
  reboot_after_update                  = false
  stop_on_destroy                      = false
  purge_on_destroy                     = false
  delete_unreferenced_disks_on_destroy = false

  cpu {
    cores   = 4
    sockets = 1
    type    = "host"
  }

  memory {
    dedicated = 4096
    floating  = 0
  }

  network_device {
    bridge      = "vmbr0"
    firewall    = true
    mac_address = "52:54:00:00:00:00"
    model       = "virtio"
  }

  startup {
    order      = "2"
    up_delay   = "60"
    down_delay = "180"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      description,
      disk,
      efi_disk,
      initialization,
      serial_device,
      started,
    ]
  }
}
