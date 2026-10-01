provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = var.proxmox_tls_insecure

  # Cloud-image disk import uses SSH as root with the loaded agent; the
  # provider does not read ~/.ssh/config.
  ssh {
    agent    = true
    username = "root"
  }
}
