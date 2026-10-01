# Troubleshooting

## API name reaches VM 300

The current Synology wildcard points unknown `*.lab.example.com` names at NPM.
Create the explicit `bao` A record to `.5.19`; do not make NPM the OpenBao load
balancer. Verify with `dig @192.168.0.20 bao.lab.example.com A`.

## TLS listener will not start

Check certificate chain, node SAN, key/cert match, file ownership, and systemd
`ReadWritePaths`. Never disable TLS verification. Use direct node DNS names, not
raw IPs, unless the issued certificate contains those IP SANs.

## No leader after initialization

Check time synchronization, TCP 8201 between only the three node IPs, Raft
`retry_join`, unseal state on each node, and certificates. Do not use forced peer
removal as a diagnostic shortcut.

## VIP unavailable

Query all three direct `/v1/sys/health` endpoints with the CA, inspect Keepalived
state and UFW peer rules, then HAProxy health. Clients can temporarily use a
direct unsealed node while `.5.19` is repaired.

## Backup stale

Check Agent renewal, snapshot policy, age recipient, SFTP fingerprint/account,
Synology availability/space, and local encrypted files. Preserve all failed
artifacts. Never relax host-key checking or copy the age private identity to the
node as a shortcut.

## Lost access

Use independent SSH keys and operator recovery material. If OIDC is later added,
keep and test the non-OIDC recovery method. Root-token generation is a controlled
break-glass ceremony using quorum-held recovery/unseal shares.
