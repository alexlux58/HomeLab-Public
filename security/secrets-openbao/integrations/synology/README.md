# Synology integration

Three credentials remain separate:

1. SNMPv3 monitoring material may migrate to `kv/observability/synology-snmp`.
2. API credentials are added only if a real DSM automation need exists.
3. The OpenBao snapshot SFTP key remains outside OpenBao so it is usable during
   a total OpenBao outage.

The NAS account is restricted to `OpenBaoBackups/`; it cannot administer DSM or
read unrelated shares. Pin the NAS SSH host key. Btrfs snapshots and replication
are DSM-side controls and must not grant broader account access.
