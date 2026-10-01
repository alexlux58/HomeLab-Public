# NetBox lives in its own Terraform root on purpose.
#
# terraform/homelab-guests is import-first: it adopts VMs 300 and 310, which
# already exist. Putting a create-mode resource in that root would mean every
# routine drift plan for the two live guests also proposed creating a third VM.
# Keeping NetBox separate means a plan here can only ever be about NetBox.
#
# There is no apply or destroy target for this root, in this Makefile or any
# other. Applying it is a separate, reviewed, manual operator action.

locals {
  managed_description = "NetBox IPAM/DCIM: Terraform identity/resources, Ansible guest and application configuration"
  gateway             = "192.168.0.1"
  dns_server          = "192.168.0.20"
  dns_domain          = "lab.example.com"
}

resource "proxmox_download_file" "ubuntu" {
  content_type        = "iso"
  datastore_id        = "local"
  node_name           = var.netbox_node
  file_name           = "ubuntu-24.04-server-cloudimg-amd64.img"
  url                 = var.ubuntu_image_url
  checksum            = var.ubuntu_image_checksum
  checksum_algorithm  = "sha256"
  overwrite           = false
  overwrite_unmanaged = false
}

resource "proxmox_virtual_environment_vm" "netbox" {
  vm_id       = var.netbox_vm_id
  name        = "netbox"
  node_name   = var.netbox_node
  description = local.managed_description
  tags        = ["netbox", "ipam", "terraform", "ansible"]

  machine = "q35"
  bios    = "ovmf"

  # onboot stays false until the application backup and an isolated restore
  # drill both pass, exactly as VMs 300 and 310 were gated.
  protection                           = true
  on_boot                              = false
  started                              = var.start_after_create
  reboot_after_update                  = false
  stop_on_destroy                      = false
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
    dedicated = var.netbox_memory_mib
    floating  = 0
  }

  efi_disk {
    datastore_id      = var.netbox_disk_datastore
    file_format       = "raw"
    pre_enrolled_keys = true
    type              = "4m"
  }

  disk {
    datastore_id = var.netbox_disk_datastore
    file_id      = proxmox_download_file.ubuntu.id
    file_format  = "raw"
    interface    = "scsi0"
    iothread     = true
    discard      = "on"
    size         = var.netbox_disk_size_gib
    ssd          = true
    backup       = true
  }

  initialization {
    datastore_id = var.netbox_disk_datastore

    dns {
      domain  = local.dns_domain
      servers = [local.dns_server]
    }

    ip_config {
      ipv4 {
        address = var.netbox_address
        gateway = local.gateway
      }
    }

    user_account {
      username = "netbox-admin"
      keys     = var.ssh_public_keys
    }
  }

  network_device {
    bridge      = "vmbr0"
    firewall    = true
    mac_address = var.netbox_mac_address
    model       = "virtio"
  }

  operating_system {
    type = "l26"
  }

  serial_device {
    device = "socket"
  }

  startup {
    order      = "4"
    up_delay   = "30"
    down_delay = "180"
  }

  lifecycle {
    prevent_destroy = true
    # file_id is a create-time import source. Once the boot disk exists, a
    # provider retry or future image refresh must not replace this protected VM.
    ignore_changes = [disk[0].file_id]

    precondition {
      condition     = length(var.ssh_public_keys) > 0
      error_message = "At least one SSH public key is required; password login is not supported."
    }
  }
}
