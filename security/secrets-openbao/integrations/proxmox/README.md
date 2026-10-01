# Proxmox integration

- Bootstrap VM creation uses a dedicated PVE token outside OpenBao.
- Future Terraform runtime token: `kv/automation/terraform/proxmox`.
- Monitoring pilot: `kv/observability/pve-exporter`, policy
  `pve-exporter-pilot`, read-only `PVEAuditor` token.
- OpenBao Agent on VM 310 renders the token into a root-owned mode-0600 file;
  only PVE Exporter is recreated. After proof, revoke the former token.
- Never use `root@pam`; never print token values; do not place a token in state,
  inventory, Compose YAML, or `docker inspect`-visible environment variables.
