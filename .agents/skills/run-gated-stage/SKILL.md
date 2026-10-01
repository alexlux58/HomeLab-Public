---
name: run-gated-stage
description: Use when the operator wants to run a gated local make stage or playbook. Prepares the exact EXTRA_JSON and preconditions; never supplies an approval. Agent execution requires explicit authorization and the operator's exact confirmation.
---

# Prepare a gated stage for the operator

An approval is the operator's decision. Prepare the stage and stop for their
exact confirmation. If they explicitly authorize an agent to execute that
single stage, execute only after they supply the approval; never invent one.
Repository pushes follow D6: approved origin only, after checks, with the
pre-push hook; never force, delete, mirror or use another remote or URL.
Checks run in phase6; Windows transport may use its existing gh/GCM keyring
without exporting credentials. Install the shared pre-push guard in each checkout.

## Steps

1. Identify the one stage and its Make target (`make -C <component> help`).
   Refuse any request that chains stages.
2. Read the gate from source, not memory: the `allow_*` default, the
   confirmation variable, and the exact expected string in the assertion
   (`inventory/group_vars/all.yml` for migration stages, role defaults
   elsewhere).
3. List preconditions from the component docs and `MEMORY.md`: prior stages,
   backups verified, capacity, host-key pins, maintenance window.
4. Write the command as `EXTRA_JSON` so multi-word confirmations stay one
   value, for example:

   ```text
   make -C platform/proxmox join-pve3 EXTRA_JSON='{"allow_join_pve3":true,"join_confirmation_pve3":"<exact string from source>"}'
   ```

   GitHub performs checks only (ADR-0009). Plans, approvals and deploys stay
   on the local controller in the devcontainer.
5. State the rollback and the evidence to capture afterwards.
6. Stop until the operator supplies the exact approval. Do not put it in a
   default or persistent file. Without explicit execution authorization,
   the operator runs the stage. A supplied approval authorizes only that stage.

## Checks

The string you quote matches the assertion byte for byte; destructive stages
include `--tags all,destructive` in their Make target; the stage is a single
target.
