# State migration to workstation (D1)

Operator-only, per root. Accepted 2026-09-30. See
[ADR-0003](../decisions/ADR-0003-state-backend.md).
An agent prepares these commands; it never opens state or runs init, plan,
migration or import. Keep the Phase 1 source archive and every backup.

## Controller and prerequisites

Use OpenTofu 1.12.6 in `homelab-devcontainer:phase6`. Create
`D:\homelab-state\openbao`, `netbox`, `homelab-guests`, `rebuild-guests` and
`media-arr` yourself. Keep independent strong per-root passphrases in your
password manager. Run only one process against each root and use only the
default workspace. Backend and plan files live on D:, outside Git.

Start the attended shell from PowerShell:

```powershell
docker run --rm -it --user root -v C:/Users/labuser/Documents/Home-Lab:/w -v D:/homelab-state:/homelab-state -v C:/Users/labuser/Documents/Home-Lab-Phase1-Source-Archive:/source-archive:ro -w /w homelab-devcontainer:phase6 bash
```

For each root, read its passphrase without echo and supply your Proxmox token
through the approved operator workflow. Never paste either into chat, a
command argument, a tracked file or a transcript:

```bash
set +x
umask 077
read -rsp 'This root state passphrase: ' TF_VAR_state_passphrase
echo
export TF_VAR_state_passphrase
```

Verify Proxmox TLS and host pins using the existing inventory. Do not change
cloud-init values to make a migration succeed: the known NetBox resolver
drift is a separate later stage, since changing it can regenerate host keys.

## One-time plaintext fallback

Copy that root's `backend.tofu.example` to the git-ignored `backend.tofu`.
For the first read only, edit your local copy: add
`method "unencrypted" "migration" {}` inside `encryption`; set **state**
`enforced = false` temporarily and add this inside its `state` block:

```hcl
fallback {
  method = method.unencrypted.migration
}
```

The primary method stays AES-GCM, so new state is encrypted. Plan encryption
stays enforced throughout. A fallback does not convert a file until a state
write occurs. Use `init -migrate-state` to move the old local state into the
new local path. If init does not write a ciphertext envelope, stop; never
assume a plan converted the state and never apply resource changes to force
encryption. OpenTofu's
[encryption migration guidance](https://opentofu.org/docs/language/state/encryption/)
explains this temporary fallback and its removal.

## 1. OpenBao

In your attended devcontainer shell:

```bash
cd /w/security/secrets-openbao/terraform
cp backend.tofu.example backend.tofu
cp /source-archive/homelab-openbao/terraform/terraform.tfstate terraform.tfstate
```

Make the fallback edit above before these commands. Keep the old archive
read-only. Supply this root's existing non-secret variables and operator
credentials through its established workflow; do not generate new identities.

```bash
tofu init -migrate-state
tofu plan -detailed-exitcode -out=/homelab-state/openbao/migration.tfplan
```

**The plan must show no changes (exit 0), or stop.** Do not apply the plan.
Verify the destination is ciphertext without printing state contents:

```bash
grep -q '"encrypted_data"' /homelab-state/openbao/terraform.tfstate
```

Remove the unencrypted method and fallback; restore state `enforced = true`.
Then run a second plan with strict encryption:

```bash
tofu plan -detailed-exitcode -out=/homelab-state/openbao/verified.tfplan
```

Require exit 0 and no changes. Record the outcome and ciphertext SHA-256;
copy only the verified encrypted destination to the NAS as below. Never copy
the plaintext migration backup onto the NAS or into Git.

## 2. NetBox

Clear the prior passphrase and enter the independent NetBox passphrase with
the no-echo command above. Use the existing NetBox variables and credentials.

```bash
cd /w/services/netbox/terraform/proxmox-guest
cp backend.tofu.example backend.tofu
cp /source-archive/proxmox-cluster-migration/terraform/netbox-guest/terraform.tfstate terraform.tfstate
```

Make the same temporary fallback edit, then:

```bash
tofu init -migrate-state
tofu plan -detailed-exitcode -out=/homelab-state/netbox/migration.tfplan
grep -q '"encrypted_data"' /homelab-state/netbox/terraform.tfstate
```

Require **no changes, exit 0**, or stop. Remove fallback, restore enforcement,
and run:

```bash
tofu plan -detailed-exitcode -out=/homelab-state/netbox/verified.tfplan
```

Require exit 0 again; verify and copy ciphertext. Do not repair the known
resolver drift during migration. Keep the archived state and its backup.

## 3. Homelab-guests: import-first

This root has no old state. Enter its independent passphrase. Copy its strict
template without a plaintext fallback; supply the existing variables:

```bash
cd /w/platform/proxmox/terraform/homelab-guests
cp backend.tofu.example backend.tofu
tofu init
tofu import proxmox_virtual_environment_vm.homelab_services pve2/300
tofu import proxmox_virtual_environment_vm.observability pve1/310
tofu plan -detailed-exitcode -out=/homelab-state/homelab-guests/verified.tfplan
```

The existing import blocks stay in source. The CLI imports only adopt
identities into state; they do not create or modify guests. Require **no
changes, exit 0**, or stop. Never use an apply to adopt the guests if it would
also change their configuration.

## If a plan changes anything

Stop and retain every state version. Compare resource addresses and VMIDs
with inventory using your attended shell. Do not blindly migrate, overwrite
or apply. To re-adopt, use a **new empty local backend path** in a separately
reviewed working copy with strict encryption; keep the failed state intact.
Import OpenBao's module resources one at a time:

```bash
tofu import 'module.openbao_vm["bao-1"].proxmox_virtual_environment_vm.this' pve1/320
tofu import 'module.openbao_vm["bao-2"].proxmox_virtual_environment_vm.this' pve2/321
tofu import 'module.openbao_vm["bao-3"].proxmox_virtual_environment_vm.this' pve3/322
```

For NetBox: `tofu import proxmox_virtual_environment_vm.netbox pve3/330`.
For homelab-guests, use the two commands above. Verify the module label in
`security/secrets-openbao/terraform/main.tf` before import. If source labels
change, stop and review. Re-run a strict no-change plan before adopting this
new state path as canonical. Any proposed configuration repair is a separate
operator-approved stage.

The pinned bpg provider 0.107.0 does **not** implement import for
`proxmox_download_file` ([provider source](https://github.com/bpg/terraform-provider-proxmox/blob/v0.107.0/fwprovider/nodes/resource_download_file.go)).
VM imports alone therefore cannot reconstruct the original root's image
resource state. If a plan proposes a cloud-image download, stop. A separately
reviewed recovery configuration must reference the verified existing image
volume IDs without managing downloads, before importing the VMs. Preserve
the original root and archived state; never manufacture download state,
overwrite an image or apply a download to obtain a clean plan.

## Encrypted NAS copy after each verified write

In your own PowerShell session, use your existing authenticated NAS access.
Copy **only** the strict, verified encrypted `terraform.tfstate` for that root
to an unused timestamped filename under
`\\192.168.0.20\proxmox-cluster-backups\opentofu-state\<root>\`.
Do not copy plaintext `.backup` files. Example for OpenBao:

```powershell
$stateSource = 'D:\homelab-state\openbao\terraform.tfstate'
$stateDirectory = '\\192.168.0.20\proxmox-cluster-backups\opentofu-state\openbao'
$stateStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$stateDestination = Join-Path $stateDirectory ($stateStamp + '.tfstate')
New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null
if (Test-Path -LiteralPath $stateDestination) { throw 'Destination already exists' }
Copy-Item -LiteralPath $stateSource -Destination $stateDestination -ErrorAction Stop
if ((Get-FileHash -LiteralPath $stateSource -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $stateDestination -Algorithm SHA256).Hash) { throw 'State copy hash mismatch' }
```

Record both paths, matching hashes and strict no-change plan evidence in
`MEMORY.md`. Keep the source archive until all three roots pass. Never prune
state copies. D: and the NAS are one site and neither is immutable: ransomware
and site loss remain accepted risks. If both copies are lost, re-adopt by
import. A lost passphrase also requires re-adoption. Clear shell credentials
and close the attended container when finished.
