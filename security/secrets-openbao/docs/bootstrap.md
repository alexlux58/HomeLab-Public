# Bootstrap runbook

Each stage stops for review. There is no aggregate deployment command.

## 1. Operator prerequisites

1. Reserve `.5.19`–`.5.22` in the router using the Terraform MACs.
2. Add the four explicit Synology DNS A records from `discovery.md`.
3. Generate `~/.ssh/openbao_ed25519`; keep its private key off the VMs.
4. Create a dedicated least-privilege Terraform Proxmox token. Export it through
   `TF_VAR_proxmox_api_token`, never a tfvars file.
5. Load the Proxmox SSH key into `ssh-agent`; Terraform uses agent forwarding for
   the verified cloud-image import and does not read a private key into state.

## 2. Offline validation and operator state adoption

```bash
make setup
make check
```

VMs 320–322 already exist. **Do not plan from this state-less monorepo root
or recreate them.** The operator first follows the
[D1 state migration](../../../docs/runbooks/state-migration.md): encrypted
local backend on workstation D:, devcontainer mount, a strict no-change plan
or stop, and a verified encrypted NAS copy. State migration/import and every
plan/apply remain operator work. Keep the source archive until verified.
For a future empty-estate rebuild, review create mode separately rather than
using a state-less plan to duplicate live identities.

The cloud image uses Canonical's immutable `release-20260814` URL and the
previously signature-verified SHA-256. Keep a second copy of that image plus its
signed manifest in the configuration recovery backup so an upstream mirror
outage does not block rebuilding.

VMs are protected, `onboot=false`, and stopped by default. After creation,
start one at a time from Proxmox, read its ED25519 host fingerprint through QGA
or console, compare to the network-presented key, and build
`artifacts/openbao_known_hosts`. Never auto-accept a host key.

## 3. Guest stages

```bash
make preflight
make prepare-hosts EXTRA_JSON='{"allow_prepare_openbao_hosts":true,"prepare_openbao_hosts_confirmation":"PREPARE OPENBAO HOSTS 320 321 322"}'
make install-server EXTRA_JSON='{"allow_install_openbao":true,"install_openbao_confirmation":"INSTALL OPENBAO 2.6.1 WITHOUT INITIALIZING"}'
```

The install verifies the upstream GPG fingerprint, signed checksum manifest,
and exact archive before extracting `bao`. It does not start OpenBao.

## 4. Bootstrap TLS

From an operator workstation, generate certificates outside Git:

```bash
python3 scripts/pki_bootstrap.py \
  --output ~/.local-credentials/home-lab/openbao/pki \
  --confirm 'CREATE OFFLINE OPENBAO ROOT CA'
```

Move `offline-root-key.pem` to encrypted offline custody after issuance. Keep
only `ca.pem` and each node's certificate/key in the runtime deployment folder.

```bash
make configure-tls EXTRA_JSON='{"allow_configure_openbao_tls":true,"configure_openbao_tls_confirmation":"DEPLOY OPENBAO TLS TO THREE NODES"}'
make configure-ha EXTRA_JSON='{"allow_configure_openbao_ha":true,"configure_openbao_ha_confirmation":"CONFIGURE OPENBAO RAFT AND VIP UNINITIALIZED"}'
make validate-uninitialized
```

The last command must say that TLS is valid and `initialized=false`. Stop here
and use the [2026-10-10 attended ceremony](../../../docs/runbooks/openbao-init-ceremony.md).
