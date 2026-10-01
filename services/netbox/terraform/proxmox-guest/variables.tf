variable "proxmox_endpoint" {
  description = "Proxmox cluster API endpoint."
  type        = string
  default     = "https://192.168.0.11:8006"
}

variable "proxmox_api_token" {
  description = "Dedicated Terraform Proxmox API token, supplied only through TF_VAR_proxmox_api_token."
  type        = string
  sensitive   = true
}

variable "proxmox_tls_insecure" {
  description = "Allow the private cluster's currently self-signed API certificate."
  type        = bool
  default     = true
}

variable "netbox_vm_id" {
  description = "VMID for the NetBox guest. 320-322 are reserved for the planned OpenBao voters."
  type        = number
  default     = 330

  validation {
    condition     = var.netbox_vm_id != 300 && var.netbox_vm_id != 310 && var.netbox_vm_id != 399
    error_message = "Refusing a VMID already used by a live protected guest or the retained restore test."
  }
}

variable "netbox_node" {
  description = "Placement node. pve3 is the only node with an SSD, no guests, and free RAM."
  type        = string
  default     = "pve3"

  validation {
    condition     = contains(["pve3"], var.netbox_node)
    error_message = "NetBox placement was measured for pve3. Re-measure capacity before overriding."
  }
}

variable "netbox_address" {
  description = "Static CIDR address handed to cloud-init; must match the the router reservation."
  type        = string
  default     = "192.168.0.50/24"
}

variable "netbox_mac_address" {
  description = "Fixed MAC. Must be unique across every cluster guest and match the the router reservation."
  type        = string
  default     = "52:54:00:00:00:00"

  validation {
    condition     = can(regex("^([0-9A-F]{2}:){5}[0-9A-F]{2}$", var.netbox_mac_address))
    error_message = "netbox_mac_address must be an uppercase colon-separated MAC address."
  }
}

variable "netbox_memory_mib" {
  description = "Fixed RAM. pve3 has about 6.0 GiB available and a planned 2 GiB OpenBao voter."
  type        = number
  default     = 3072

  validation {
    condition     = var.netbox_memory_mib <= 4096
    error_message = "Above 4 GiB the node cannot also host the planned OpenBao voter. Re-measure first."
  }
}

variable "netbox_disk_size_gib" {
  description = "Boot disk size. local-lvm on pve3 is a 49.6 GiB thin pool."
  type        = number
  default     = 32
}

variable "netbox_disk_datastore" {
  description = "Node-local SSD-backed thin pool."
  type        = string
  default     = "local-lvm"
}

variable "ssh_public_keys" {
  description = "Dedicated NetBox guest public keys. Passwords are unsupported."
  type        = list(string)

  validation {
    condition = length(var.ssh_public_keys) > 0 && alltrue([
      for key in var.ssh_public_keys : can(regex("^ssh-(ed25519|rsa) ", key))
    ])
    error_message = "Supply at least one valid SSH public key; password login is not supported."
  }
}

variable "ubuntu_image_url" {
  description = "Canonical Ubuntu 24.04 cloud image URL, pinned by the signed checksum below."
  type        = string
  default     = "https://cloud-images.ubuntu.com/releases/noble/release-20260814/ubuntu-24.04-server-cloudimg-amd64.img"
}

variable "ubuntu_image_checksum" {
  description = "SHA-256 from the Canonical-signed manifest already verified for VMs 300 and 310."
  type        = string
  default     = "6e40c07ae715f744f84af0bec76415cc1987dd115b4b8de437818561f01a3733"

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.ubuntu_image_checksum))
    error_message = "ubuntu_image_checksum must be a lowercase SHA-256 value."
  }
}

variable "start_after_create" {
  description = "Boot only after the plan, the router reservation, DNS records, and console access are approved."
  type        = bool
  default     = false
}
