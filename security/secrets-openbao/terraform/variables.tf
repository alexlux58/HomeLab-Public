variable "proxmox_endpoint" {
  description = "Proxmox API endpoint."
  type        = string
  default     = "https://192.168.0.11:8006"
}

variable "proxmox_api_token" {
  description = "Dedicated bootstrap Proxmox API token supplied only through TF_VAR_proxmox_api_token."
  type        = string
  sensitive   = true
}

variable "proxmox_tls_insecure" {
  description = "Allow the cluster's currently private/self-signed API certificate."
  type        = bool
  default     = true
}

variable "ssh_public_keys" {
  description = "One or more operator SSH public keys for the openbao-admin account."
  type        = list(string)
  sensitive   = false

  validation {
    condition     = length(var.ssh_public_keys) > 0 && alltrue([for key in var.ssh_public_keys : can(regex("^ssh-(ed25519|rsa) ", key))])
    error_message = "Supply at least one valid SSH public key; passwords are unsupported."
  }
}

variable "ubuntu_image_url" {
  description = "Canonical Ubuntu 24.04 cloud image URL pinned by the signed checksum below."
  type        = string
  default     = "https://cloud-images.ubuntu.com/releases/noble/release-20260814/ubuntu-24.04-server-cloudimg-amd64.img"
}

variable "ubuntu_image_checksum" {
  description = "SHA-256 from the Canonical-signed 2026-08-14 manifest already verified for VMs 300/310."
  type        = string
  default     = "6e40c07ae715f744f84af0bec76415cc1987dd115b4b8de437818561f01a3733"

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.ubuntu_image_checksum))
    error_message = "ubuntu_image_checksum must be a lowercase SHA-256 value."
  }
}

variable "start_after_create" {
  description = "Boot only after the plan, reservations, DNS, and console access are approved."
  type        = bool
  default     = false
}

variable "openbao_nodes" {
  description = "Fixed identities and one-per-host placement for the OpenBao voters."
  type = map(object({
    vm_id           = number
    node_name       = string
    address         = string
    mac_address     = string
    disk_datastore  = string
    image_datastore = string
    disk_format     = string
    disk_ssd        = bool
  }))

  default = {
    bao-1 = {
      vm_id           = 320
      node_name       = "pve1"
      address         = "192.168.0.41/24"
      mac_address     = "52:54:00:00:00:00"
      disk_datastore  = "local"
      image_datastore = "local"
      disk_format     = "qcow2"
      disk_ssd        = true
    }
    bao-2 = {
      vm_id           = 321
      node_name       = "pve2"
      address         = "192.168.0.42/24"
      mac_address     = "52:54:00:00:00:00"
      disk_datastore  = "local-lvm"
      image_datastore = "local"
      disk_format     = "raw"
      disk_ssd        = false
    }
    bao-3 = {
      vm_id           = 322
      node_name       = "pve3"
      address         = "192.168.0.43/24"
      mac_address     = "52:54:00:00:00:00"
      disk_datastore  = "local-lvm"
      image_datastore = "local"
      disk_format     = "raw"
      disk_ssd        = true
    }
  }

  validation {
    condition     = length(distinct([for node in values(var.openbao_nodes) : node.vm_id])) == length(var.openbao_nodes)
    error_message = "Every OpenBao VM must have a unique VMID."
  }

  validation {
    condition     = length(distinct([for node in values(var.openbao_nodes) : node.mac_address])) == length(var.openbao_nodes)
    error_message = "Every OpenBao VM must have a unique MAC address."
  }
}
