resource "proxmox_download_file" "ubuntu" {
  for_each = var.openbao_nodes

  content_type        = "iso"
  datastore_id        = each.value.image_datastore
  node_name           = each.value.node_name
  file_name           = local.cloud_image_name
  url                 = var.ubuntu_image_url
  checksum            = var.ubuntu_image_checksum
  checksum_algorithm  = "sha256"
  overwrite           = false
  overwrite_unmanaged = false
}

module "openbao_vm" {
  for_each = var.openbao_nodes
  source   = "./modules/openbao-vm"

  name                = each.key
  vm_id               = each.value.vm_id
  node_name           = each.value.node_name
  address             = each.value.address
  mac_address         = each.value.mac_address
  disk_datastore      = each.value.disk_datastore
  disk_format         = each.value.disk_format
  disk_ssd            = each.value.disk_ssd
  cloud_image_file_id = proxmox_download_file.ubuntu[each.key].id
  gateway             = local.gateway
  dns_server          = local.dns_server
  dns_domain          = local.dns_domain
  description         = local.managed_description
  ssh_public_keys     = var.ssh_public_keys
  started             = var.start_after_create
}
