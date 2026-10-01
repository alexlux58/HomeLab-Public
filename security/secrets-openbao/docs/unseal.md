# Initialization and unseal ceremony

The canonical operator procedure is the
[OpenBao ceremony runbook](../../../docs/runbooks/openbao-init-ceremony.md),
scheduled for **Saturday 2026-10-10**, movable by the operator.

D4 supersedes the former independent-holder assumption: one operator owns
five offline PGP keys, each with its own passphrase, in five separate custody
places. Threshold three protects against losing/stealing two places, not
coercion of the operator. Only public keys and fingerprints approach Git/agents.

The runbook gives the day-before prerequisites (verified archives of every
VM 320–322), offline generation and fingerprint checks, exact operator-only
init/unseal commands, initial root-token revocation, offline CA custody and
separate local post-init/backup/monitoring gates. Never capture recovery output
in Ansible, CI, recordings, tool outputs or chat.

After a reboot, the operator supplies three distinct shares through hidden
prompts for each sealed voter. Auto-unseal remains deferred; it must never
depend circularly on this cluster. Do not initialize a voter a second time.
