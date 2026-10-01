# *arr configuration for media-vm (ADR-0002). Ownership, one tool each:
#   this root   root folders, download client, remote path mapping, Prowlarr
#               application link
#   Recyclarr   quality definitions, quality profiles, custom formats (ADR-0004)
#   operator    indexers (lawful-provider decision), notifications
# No apply or destroy target exists; the operator applies after review.

provider "radarr" {
  url     = var.radarr_url
  api_key = var.radarr_api_key
}

provider "prowlarr" {
  url     = var.prowlarr_url
  api_key = var.prowlarr_api_key
}

resource "radarr_root_folder" "movies" {
  path = "/media/Movies"
}

resource "radarr_download_client_qbittorrent" "lux_tower" {
  enable         = true
  priority       = 1
  name           = "qBittorrent (workstation)"
  host           = var.nat_host_address
  port           = var.qbittorrent_port
  username       = var.qbittorrent_username
  password       = var.qbittorrent_password
  movie_category = "radarr"
}

# qBittorrent runs on Windows and reports M:\Downloads\...; the guest sees the
# same NAS folder at /media/Downloads.
resource "radarr_remote_path_mapping" "downloads" {
  host        = var.nat_host_address
  remote_path = "M:\\Downloads\\"
  local_path  = "/media/Downloads/"
}

resource "prowlarr_application_radarr" "radarr" {
  name         = "Radarr"
  sync_level   = "fullSync"
  base_url     = "http://radarr:7878"
  prowlarr_url = "http://prowlarr:9696"
  api_key      = var.radarr_api_key
}
