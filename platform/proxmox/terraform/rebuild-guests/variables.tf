variable "lab_file" {
  description = "Path to the single source of truth (ADR-0005)."
  type        = string
  default     = "../../../../inventory/lab.yml"
}

variable "rebuild_guests" {
  description = "Guests to recreate after a total loss. Empty by default: a plan creates nothing."
  type        = set(string)
  default     = []
}

variable "rebuild_confirmation" {
  description = "Must equal \"REBUILD <sorted guest names separated by spaces> FROM ZERO\"."
  type        = string
  default     = ""
}

variable "proxmox_endpoint" {
  description = "Proxmox cluster API endpoint."
  type        = string
  default     = "https://192.168.0.11:8006"
}

variable "proxmox_api_token" {
  description = "Dedicated Proxmox API token, supplied only through TF_VAR_proxmox_api_token."
  type        = string
  sensitive   = true
  default     = null
}

variable "proxmox_tls_insecure" {
  description = "Allow the private cluster's self-signed API certificate."
  type        = bool
  default     = true
}

variable "ssh_public_keys" {
  description = "Admin public keys per guest name. Passwords are unsupported."
  type        = map(list(string))
  default     = {}

  validation {
    condition = alltrue(flatten([
      for keys in values(var.ssh_public_keys) : [for key in keys : can(regex("^ssh-(ed25519|rsa) ", key))]
    ]))
    error_message = "Every entry must be an SSH public key."
  }
}

variable "ubuntu_image_url" {
  description = "Canonical Ubuntu 24.04 cloud image, pinned by the signed checksum below."
  type        = string
  default     = "https://cloud-images.ubuntu.com/releases/noble/release-20260814/ubuntu-24.04-server-cloudimg-amd64.img"
}

variable "ubuntu_image_checksum" {
  description = "SHA-256 from the Canonical-signed manifest verified for VMs 300 and 310."
  type        = string
  default     = "6e40c07ae715f744f84af0bec76415cc1987dd115b4b8de437818561f01a3733"

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.ubuntu_image_checksum))
    error_message = "ubuntu_image_checksum must be a lowercase SHA-256 value."
  }
}
