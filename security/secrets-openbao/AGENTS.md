# AGENTS.md — security/secrets-openbao

Inherits `../../AGENTS.md`. These rules are additional and take precedence for
OpenBao work.

## Purpose and layout

A three-voter OpenBao 2.6.1 Raft cluster: VMs 320–322, one per Proxmox node,
Keepalived VIP `192.168.0.40`. `terraform/`, `ansible/playbooks/` (`00` … `99`),
`openbao/` policy and engine definitions, `scripts/` (safety validation, Raft
snapshot, recovery bundles), `docs/`. Inventory: `../../inventory/secrets-openbao/`.
Current state is in the root `MEMORY.md`.

## Commands

```text
make check             # yamllint, ansible-lint, ruff, validate_repo.py, tests, syntax
make discover-plan     # reads only local sanitized inputs
```

## Component rules

- Never initialize, unseal, rekey, generate a root token, restore Raft, remove
  a Raft peer, or migrate a credential without explicit operator approval for
  that exact stage. There is intentionally no automated `bao operator init`;
  initialization is an attended ceremony (five PGP recipients, threshold three).
  D4: 2026-10-10, movable by the operator; one operator controls five offline
  keys with distinct passphrases in five separate custody places. Follow
  `../../docs/runbooks/openbao-init-ceremony.md`; verify archives of all three
  voters the day before. This protects two lost places, not operator coercion.
- Never inspect, print, copy or commit tokens, unseal shares, SecretIDs, TLS
  private keys, backup identities, SMTP passwords or application secrets.
  Secret-bearing tasks use `no_log: true`; Python never prints values.
- Applications may consume operator-supplied runtime files through the
  approved workflow. Agents never open their secret contents.
- Raft lives only on local VM disks; Synology is a backup destination only.
- Mutating stages need a boolean and exact confirmation string
  (`allow_prepare_openbao_hosts`, `allow_install_openbao`,
  `allow_configure_openbao_tls|ha|post_init|backup|monitoring`,
  `allow_run_openbao_backup`). No aggregate deploy target.
- No archive pruning; retention is separately reviewed NAS snapshots. Restores
  run only in a verified isolated VM/network; production restore, forced
  restore and peer removal are documented, never executable from normal targets.
- Two historical paths are excluded (`SECRETS-EXCLUDED.md`). Never copy them in.
- Do not raise `bao-2` above 2 GiB without repeating capacity discovery.

## Gate order

1. `make check` — offline.
2. `make discover-plan` — local sanitized inputs only.
3. Terraform plan only with a runtime token and SSH public key; apply is a
   separate operator approval (and state is not in the monorepo yet).
4. Ansible preflight is read-only; host/install/TLS stages are separately gated.
5. Stop after `make validate-uninitialized`; it must report `initialized=false`.
6. Initialization is manual and attended; never capture its output.
7. Post-init, backup, monitoring and the PVE exporter pilot each need approval.

## Ownership

- Terraform: VM identity, placement, CPU/RAM, local disks, NICs, cloud-init.
- Ansible: hardening, verified binary, TLS, systemd, firewall, HAProxy and
  Keepalived, audit, backup timers, monitoring integration.
- Python: repository safety, API reconciliation, backup verification, recovery
  bundles, discovery reports, secret-reference inventories.
- Operator: DHCP/DNS, offline CA custody, unseal ceremony, runtime secret files,
  Synology accounts and shares, Terraform apply, all live approvals.

The first secret pilot is the read-only PVE exporter token on VM 310. The
backup decryption identity and at least three unseal shares stay outside both
OpenBao and the Synology backup location.

## Definition of done

`make check` passes here and `make COMPONENT=tests check` passes at the root;
staged gitleaks passes; `MEMORY.md` records any state change with its evidence.
