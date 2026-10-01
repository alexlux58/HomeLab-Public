provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = var.proxmox_tls_insecure

  # The provider uses SSH for cloud-image disk import. It does not read
  # ~/.ssh/config, so state the root user explicitly and use the loaded agent.
  ssh {
    agent    = true
    username = "root"
  }
}
