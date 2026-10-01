# Automation and ownership

## Terraform

Terraform creates only VM-level state. It never receives TLS keys, tokens,
unseal shares, application secrets, or password hashes. `sensitive=true` only
redacts CLI output; it does not encrypt state. Keep state on an encrypted local
volume or an independently protected backend and restrict its Proxmox token.

The initial OpenBao VMs necessarily use a bootstrap PVE token held outside
OpenBao. After OpenBao is healthy, a separate short-lived runtime token can be
delivered to Terraform, but OpenBao recovery must never depend on it.

## Ansible

Every playbook is one reviewed stage, `serial: 1`, and fail-fast. Live secret
material is referenced by protected file path and secret tasks use `no_log`.
Syntax/lint never contacts OpenBao. There is no initialization task.

## Python

Scripts use only the standard library plus installed system CLIs (`bao`, `age`,
`sftp`, `openssl`). They produce JSON or concise non-secret status and distinct
exit codes. The API reconciler handles mounts/policies/AppRole definitions but
does not create SecretIDs or secret values.

## Recovery order

1. recover Proxmox quorum/network/DNS and at least one clean compute node;
2. recover all three OpenBao VM definitions and local Raft disks if available;
3. if necessary, recover one isolated cluster from an encrypted Raft snapshot;
4. restore stable API DNS/VIP and unseal;
5. recover VM 310 monitoring, then VM 300 applications;
6. reissue AppRole SecretIDs and rotate any credential that may have been exposed;
7. validate backups and recreate the remaining voters one at a time.
