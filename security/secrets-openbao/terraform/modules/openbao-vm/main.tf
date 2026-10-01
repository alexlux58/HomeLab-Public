resource "proxmox_virtual_environment_vm" "this" {
  vm_id       = var.vm_id
  name        = var.name
  node_name   = var.node_name
  description = var.description
  tags        = ["openbao", "raft-voter", "terraform", "ansible"]

  machine = "q35"
  bios    = "ovmf"

  protection                           = true
  on_boot                              = false
  started                              = var.started
  reboot_after_update                  = false
  stop_on_destroy                      = true
  purge_on_destroy                     = false
  delete_unreferenced_disks_on_destroy = false

  agent {
    enabled = true
    trim    = true
    type    = "virtio"
  }

  cpu {
    cores   = 2
    sockets = 1
    type    = "x86-64-v2-AES"
  }

  memory {
    dedicated = 2048
    floating  = 0
  }

  efi_disk {
    datastore_id      = var.disk_datastore
    file_format       = var.disk_format
    pre_enrolled_keys = true
    type              = "4m"
  }

  disk {
    datastore_id = var.disk_datastore
    file_id      = var.cloud_image_file_id
    file_format  = var.disk_format
    interface    = "scsi0"
    iothread     = true
    discard      = "on"
    size         = 24
    ssd          = var.disk_ssd
    backup       = true
  }

  initialization {
    datastore_id = var.disk_datastore

    dns {
      domain  = var.dns_domain
      servers = [var.dns_server]
    }

    ip_config {
      ipv4 {
        address = var.address
        gateway = var.gateway
      }
    }

    user_account {
      username = "openbao-admin"
      keys     = var.ssh_public_keys
    }
  }

  network_device {
    bridge      = "vmbr0"
    firewall    = true
    mac_address = var.mac_address
    model       = "virtio"
  }

  operating_system {
    type = "l26"
  }

  serial_device {
    device = "socket"
  }

  startup {
    order      = "3"
    up_delay   = "30"
    down_delay = "120"
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = length(var.ssh_public_keys) > 0
      error_message = "At least one SSH public key is required; password login is not supported."
    }
  }
}

