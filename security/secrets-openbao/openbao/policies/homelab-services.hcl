path "kv/data/homelab-services/*" {
  capabilities = ["read"]
}

path "kv/metadata/homelab-services/*" {
  capabilities = ["read", "list"]
}

