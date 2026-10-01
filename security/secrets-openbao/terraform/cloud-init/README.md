# Cloud-init boundary

The bpg/proxmox provider builds cloud-init directly in the VM resource. Only a
username, SSH public key, DNS, and fixed IP are injected. No passwords, tokens,
TLS private keys, unseal material, or application configuration pass through
cloud-init or Terraform state.

Ansible owns every post-boot setting. This separation avoids persisting secret
material in Proxmox snippets or Terraform state.
