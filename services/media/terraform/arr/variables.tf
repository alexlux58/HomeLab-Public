# The apps are reached through workstation's loopback NAT forwards, so this root
# is planned from workstation itself. API keys and the qBittorrent login are
# operator inputs (L7 table), supplied only as TF_VAR_* in the shell.

variable "radarr_url" {
  description = "Radarr as seen from the controller on workstation."
  type        = string
  default     = "http://127.0.0.1:7878"
}

variable "radarr_api_key" {
  description = "Radarr API key (Settings > General). Operator input."
  type        = string
  sensitive   = true
  default     = null
}

variable "prowlarr_url" {
  description = "Prowlarr as seen from the controller on workstation."
  type        = string
  default     = "http://127.0.0.1:9696"
}

variable "prowlarr_api_key" {
  description = "Prowlarr API key. Operator input."
  type        = string
  sensitive   = true
  default     = null
}

variable "nat_host_address" {
  description = "The Windows host as seen from the VirtualBox NAT guest."
  type        = string
  default     = "10.0.2.2"
}

variable "qbittorrent_port" {
  description = "qBittorrent Web UI port on workstation. Not recorded yet: operator input."
  type        = number
}

variable "qbittorrent_username" {
  description = "qBittorrent Web UI user. Operator input."
  type        = string
  sensitive   = true
  default     = null
}

variable "qbittorrent_password" {
  description = "qBittorrent Web UI password. Operator input."
  type        = string
  sensitive   = true
  default     = null
}
