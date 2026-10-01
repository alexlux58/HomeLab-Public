# Private PKI

The offline root is created on an operator workstation by
`scripts/pki_bootstrap.py`. It signs the initial node listener certificates and
then leaves online systems.

After initialization:

1. `pki_int/` is enabled with a one-year maximum TTL.
2. Generate an intermediate private key and CSR inside OpenBao.
3. Move only the CSR to the offline root workstation.
4. Sign it with CA constraints and a shorter validity than the root.
5. Import only the signed intermediate chain into OpenBao.
6. Create roles limited to `lab.example.com`, with no bare/public domains and
   TTLs appropriate to the client.
7. Distribute `ca.pem` through Ansible; distribute private leaf keys only to the
   consuming host with mode 0640/0600.

The offline root key is never stored in OpenBao, Terraform state, Proxmox
cloud-init, Synology backups, or the repository. Alert at 30/14/7 days before
leaf and intermediate expiration. Rotate one listener certificate at a time and
use SIGHUP/restart plus direct-node validation before proceeding.
