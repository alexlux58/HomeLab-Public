# Rebuild-only, create-mode root (ADR-0007). It recreates guests after a total
# loss and is never pointed at a live guest: the live roots are
# terraform/homelab-guests (300, 310), security/secrets-openbao (320-322) and
# services/netbox (330). With the defaults a plan is empty.
#
# There is no apply or destroy Make target. Apply is an operator action at
# rung L3 of docs/runbooks/rebuild-from-zero.md.

locals {
  lab         = yamldecode(file(var.lab_file))
  rebuildable = { for name, guest in local.lab.guests : name => guest if try(guest.rebuild, false) }
  selected    = { for name, guest in local.rebuildable : name => guest if contains(var.rebuild_guests, name) }
  nodes       = toset([for guest in values(local.selected) : guest.node])

  expected_confirmation = "REBUILD ${join(" ", sort(tolist(var.rebuild_guests)))} FROM ZERO"
  description           = "Home Lab guest recreated by the rebuild-only root; Ansible configures it (L4+)"
}

resource "terraform_data" "rebuild_gate" {
  count = length(var.rebuild_guests) > 0 ? 1 : 0

  lifecycle {
    precondition {
      condition     = length(setsubtract(var.rebuild_guests, keys(local.rebuildable))) == 0
      error_message = "rebuild_guests may only name guests with rebuild: true in inventory/lab.yml."
    }
    precondition {
      condition     = var.rebuild_confirmation == local.expected_confirmation
      error_message = "rebuild_confirmation must equal the exact string \"REBUILD <sorted names> FROM ZERO\"."
    }
  }
}

resource "proxmox_download_file" "ubuntu" {
  for_each = local.nodes

  content_type        = "iso"
  datastore_id        = "local"
  node_name           = each.value
  file_name           = "ubuntu-24.04-cloudimg-20260814.img"
  url                 = var.ubuntu_image_url
  checksum            = var.ubuntu_image_checksum
  checksum_algorithm  = "sha256"
  overwrite           = false
  overwrite_unmanaged = false

  depends_on = [terraform_data.rebuild_gate]
}

resource "proxmox_virtual_environment_vm" "guest" {
  for_each = local.selected

  vm_id       = each.value.vmid
  name        = each.key
  node_name   = each.value.node
  description = local.description
  tags        = ["rebuild", "tofu", "ansible"]

  machine = "q35"
  bios    = "ovmf"

  # Recreated guests stay off and never auto-boot; onboot is flipped per guest
  # at L8 after its restore drill, under the L1 host-config gate.
  protection                           = true
  on_boot                              = false
  started                              = false
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
    cores   = each.value.cores
    sockets = 1
    type    = each.value.cpu_type
  }

  memory {
    dedicated = each.value.memory_mib
    floating  = 0
  }

  efi_disk {
    datastore_id      = each.value.datastore
    file_format       = each.value.disk_format
    pre_enrolled_keys = true
    type              = "4m"
  }

  disk {
    datastore_id = each.value.datastore
    file_id      = proxmox_download_file.ubuntu[each.value.node].id
    file_format  = each.value.disk_format
    interface    = "scsi0"
    iothread     = true
    discard      = "on"
    size         = each.value.disk_gib
    ssd          = each.value.ssd
    backup       = true
  }

  initialization {
    datastore_id = each.value.datastore

    dns {
      domain  = local.lab.network.dns_zone
      servers = [local.lab.network.lab_resolver]
    }

    ip_config {
      ipv4 {
        address = each.value.address
        gateway = local.lab.network.gateway
      }
    }

    user_account {
      username = each.value.admin_user
      keys     = lookup(var.ssh_public_keys, each.key, [])
    }
  }

  network_device {
    bridge      = local.lab.network.bridge
    firewall    = true
    mac_address = each.value.mac
    model       = "virtio"
  }

  operating_system {
    type = "l26"
  }

  serial_device {
    device = "socket"
  }

  startup {
    order      = tostring(each.value.startup.order)
    up_delay   = tostring(each.value.startup.up)
    down_delay = tostring(each.value.startup.down)
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [disk[0].file_id]

    precondition {
      condition     = length(lookup(var.ssh_public_keys, each.key, [])) > 0
      error_message = "Supply the guest's admin public key in ssh_public_keys; password login is not supported."
    }
  }

  depends_on = [terraform_data.rebuild_gate]
}
