# Offline: both providers are mocked, so no *arr API is contacted.
#   tofu init -backend=false && tofu test

mock_provider "radarr" {}
mock_provider "prowlarr" {}

variables {
  qbittorrent_port = 8080
  radarr_api_key   = "mock-radarr-key"
}

run "declares_only_the_owned_objects" {
  command = plan

  assert {
    condition     = radarr_root_folder.movies.path == "/media/Movies"
    error_message = "Movies live on the NAS Media share, mounted at /media."
  }
  assert {
    condition     = radarr_remote_path_mapping.downloads.local_path == "/media/Downloads/"
    error_message = "Windows downloads map to the guest's /media/Downloads."
  }
  assert {
    condition     = radarr_download_client_qbittorrent.lux_tower.host == "10.0.2.2"
    error_message = "qBittorrent is reached through the VirtualBox NAT host address."
  }
  assert {
    condition     = prowlarr_application_radarr.radarr.sync_level == "fullSync"
    error_message = "Prowlarr keeps Full Sync to Radarr."
  }
}
