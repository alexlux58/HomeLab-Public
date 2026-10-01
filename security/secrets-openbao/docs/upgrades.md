# Upgrade runbook

1. Review OpenBao release notes, security advisories, and upgrade path.
2. Run `make check` with the proposed version pin and signed artifact workflow.
3. Produce and verify a fresh encrypted Raft snapshot; prove it decrypts/inspects.
4. Confirm all three voters, one leader, no Autopilot failures, and one-host
   failure tolerance.
5. Upgrade one standby voter. Unseal and wait for healthy Raft membership.
6. Repeat for the second standby.
7. Step down the leader only through an attended maintenance approval, then
   upgrade the former leader.
8. Validate agents, policies, metrics, audit delivery, backup, VIP, direct nodes,
   and application pilot.

Never skip major versions unless OpenBao's release notes explicitly permit it.
Never upgrade two voters concurrently. Keep the old verified binary package and
config bundle; do not downgrade Raft storage unless official guidance supports it.
