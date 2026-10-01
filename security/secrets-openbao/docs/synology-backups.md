# Synology backup design

Create a dedicated DSM user `openbao-backup` with SFTP access only to:

```text
OpenBaoBackups/
├── raft/
├── configuration/
├── pki-public/
└── restore-tests/
```

Disable interactive shell where DSM permits it. Pin the NAS ED25519 fingerprint
in `/etc/openbao/backup/known_hosts`; never disable host-key checking. Put the
dedicated private key on `bao-1` as root-owned mode 0600 and keep a recovery copy
outside both OpenBao and Synology.

DSM Terminal SSH/SFTP listens on **2258**, not 22 (changed 2026-08-25; 22 is
closed). `openbao_synology_ssh_port` carries this into the backup unit. Because
the port is non-default, the pinned entry must be port-qualified — OpenSSH will
not match a bare hostname line:

```bash
ssh-keyscan -p 2258 -t ed25519 192.168.0.20
# expect SHA256:EXAMPLE_FINGERPRINT_REDACTED, stored as
# [192.168.0.20]:2258 ssh-ed25519 ...
```

The daily job obtains a short token through AppRole/Agent, creates an atomic Raft
snapshot, encrypts it with an age **public recipient**, hashes the ciphertext,
retains the encrypted local copy, and uploads snapshot/checksum/manifest over
SFTP. The age private identity is offline and never on a Bao node or NAS.

No repository task prunes archives. Enable separately reviewed Btrfs snapshots
on the dedicated share and monitor space. Initial RPO is 24 hours. Alert when
the newest successful remote backup is older than 30 hours, transfer fails,
checksum verification fails, or local snapshot storage exceeds 70%.

Proxmox VM backups of 320–322 are supplemental. Never coordinate hypervisor
snapshots as the primary Raft backup.
