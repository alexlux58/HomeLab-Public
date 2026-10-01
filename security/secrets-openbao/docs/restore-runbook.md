# Emergency and isolated restore runbook

## Absolute rules

Never restore into an existing production voter, force restore, or remove a peer
until every surviving disk/config is preserved and the exact failure is proven.
Initial testing is on a new protected VM attached to an isolated bridge with no
route to `.5.19`–`.5.22`.

## Offline proof

Copy one encrypted snapshot, checksum, and the age identity to an isolated
operator workstation. Run:

```bash
python3 scripts/verify_snapshot.py \
  --input /secure/openbao-raft-TIMESTAMP.snap.age \
  --age-identity /offline/openbao-backup.agekey
```

This verifies ciphertext SHA-256, decrypts only into a temporary 0700 directory,
and runs OpenBao's snapshot inspector. It does not contact or restore a cluster.

## Isolated restore drill

1. Provision a new VM with a unique VMID/MAC on an isolated Proxmox bridge.
2. Install the exact OpenBao version that created the snapshot.
3. Install isolated TLS names and configure a **single-node** Raft path.
4. Initialize/unseal only this disposable isolated cluster.
5. Decrypt the snapshot locally in the isolated VM.
6. With the production network physically/logically absent, run the documented
   OpenBao snapshot restore command interactively.
7. Restart, unseal, verify key paths by metadata only, and run application-free
   smoke tests.
8. Seal and stop the VM. Retain the VM protected for review; do not delete it
   through this repository.
9. Save a sanitized test report under Synology `restore-tests/`.

## Quorum-loss emergency

Preserve all three Raft directories and Proxmox VM backups first. Identify the
newest consistent Raft snapshot. Use OpenBao's official lost-quorum recovery
procedure for the installed version. Peer removal and force restore commands are
intentionally absent from executable automation and require a second-person
review.

Recovery must remain possible with Synology offline by using an externally held
encrypted snapshot copy and age identity. Recovery access must remain possible
with OIDC offline through the documented operator/break-glass path.
