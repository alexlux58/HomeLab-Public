terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    radarr = {
      source  = "devopsarr/radarr"
      version = "2.5.0"
    }
    prowlarr = {
      source  = "devopsarr/prowlarr"
      version = "3.2.1"
    }
  }
}
