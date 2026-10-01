variable "proxmox_endpoint" {
  description = "Proxmox cluster API endpoint."
  type        = string
  default     = "https://192.168.0.11:8006"
}

variable "proxmox_api_token" {
  description = "Dedicated Terraform Proxmox API token, supplied through TF_VAR_proxmox_api_token."
  type        = string
  sensitive   = true
}

variable "proxmox_tls_insecure" {
  description = "Allow the private cluster's currently self-signed API certificate."
  type        = bool
  default     = true
}

variable "homelab_services_node" {
  description = "Current Proxmox node name for VM 300."
  type        = string
  default     = "pve2"
}

variable "observability_node" {
  description = "Current Proxmox node name for VM 310."
  type        = string
  default     = "pve1"
}
