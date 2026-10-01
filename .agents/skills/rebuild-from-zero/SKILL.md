---
name: rebuild-from-zero
description: Use when planning, reviewing or rehearsing a bare-metal rebuild of the lab (lost node, lost cluster, disaster recovery drill) from IaC plus backups. Walks the L0-L8 ladder in docs/runbooks/rebuild-ladder.yml for the operator; never executes a live step.
---

# Plan a rebuild from bare metal

The ladder is the source of truth: `docs/runbooks/rebuild-ladder.yml`,
rendered into `docs/runbooks/rebuild-from-zero.md`. `make rebuild-plan` prints
it and checks local prerequisites offline.

## Steps

1. Run `make rebuild-plan`. Report missing tools, `null` operator inputs in
   `inventory/lab.yml`, missing `backend.hcl`, and unset environment variables
   (names only).
2. Establish what survived. Check `docs/reference/backup-matrix.yml`: which
   archives exist and verify, and which items have no backup (qBittorrent
   state, the media library beyond RAID1, the media guest disk).
3. Walk the rungs in order, L0 → L8. For each step give the operator the one
   Make target or manual action, its gate via `run-gated-stage`, its inputs
   (`docs/reference/operator-inputs.md`), the verify command and the rollback.
   Never combine steps; never skip a verify.
4. L3 needs the OpenTofu state decision first (ADR-0003, step
   `l3-state-backend`); the rebuild root plans nothing unless given
   `rebuild_guests` and `REBUILD <sorted names> FROM ZERO`.
5. L6 restores run only on isolated copies (spare VMID, NICs `link_down`).
6. L7 OpenBao initialization is an attended ceremony. L8 flips `onboot` in
   `lab.yml` only for guests whose drill passed, then re-runs L1.

## Checks

Every row of `docs/reference/coverage-matrix.yml` is accounted for; facts
match `docs/reference/environment.md` and `lessons-learned.md` (cloud-init
regenerates host keys on stopped guests; the the router never owns the lab zone).
