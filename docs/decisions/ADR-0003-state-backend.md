# ADR-0003: encrypted local state on workstation

Status: accepted, 2026-09-30, operator decision D1. Supersedes the original
off-site bucket proposal; no bucket credentials or cloud backend are used.

## Decision

OpenTofu uses the local backend with client-side PBKDF2 and AES-GCM state
and plan encryption. Each root lives at `D:\homelab-state\<root>\` on
workstation, mounted at `/homelab-state` in the devcontainer. Plans and applies
run only there. The roots are `openbao`, `netbox`, `homelab-guests`,
`rebuild-guests` and `media-arr`. Independent passphrases live in the
operator's password manager, never in Git or on the NAS.

After each verified state write, the operator copies only ciphertext to a
new timestamped file under NAS `proxmox-cluster-backups/opentofu-state/<root>`
and compares SHA-256. Copies are retained forever. The NAS is a secondary
copy, never the live backend. The local backend uses filesystem locking;
it does not provide distributed locking across independent controllers.

## Migration and recovery

The only live state currently exists in the Phase 1 source archive (OpenBao
and NetBox); homelab-guests has none. The archive remains untouched until
strict encryption, no-change plans and NAS copies are proven for every root.
Follow [state-migration.md](../runbooks/state-migration.md), in order:
OpenBao, NetBox, then homelab-guests by import-first adoption. The temporary
plaintext fallback is operator-only and must be removed after the first
encrypted write. A plan must show no changes, or stop. No agent migrates or
imports state.

If both state copies or their passphrase are lost, re-adopt surviving
resources by import into a new encrypted local path. Keep failed or old state
intact. State reconstruction may require reconciling cloud-image resources
as well as VMs; never apply a create, replace or delete proposal as recovery.

## Accepted trade-offs

There is **no off-site state copy**. D: and the NAS share the same site and
can both be lost to fire, theft or flood. Desktop ransomware can destroy D:
and an authenticated NAS copy. Encryption protects confidentiality at rest,
not availability or replay. Passphrase loss prevents decryption. Copy
history and custody are manual; workstation sleeps and is not always available.
These risks are accepted because state can be rebuilt by import; Git stores
the desired resource declarations and the operator protects the credentials.

The original cloud bucket would have added off-site history, but D1 chooses
local recovery simplicity and operator custody. No GitHub workflow accesses
the backend or the lab (ADR-0009).
