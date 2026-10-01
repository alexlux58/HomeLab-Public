---
name: add-gated-playbook
description: Use when writing a new Ansible playbook or stage that changes a live host, guest, NAS or service, or when adding an approval gate (allow_* flag plus confirmation string) to an existing one. Covers naming, serial/fatal settings, destructive tags, the gate variables, Make target and tests.
---

# Add a gated playbook

## Steps

1. Name it `NN-verb-object.yml` (two digits, kebab-case) in the component's
   `ansible/playbooks/`. Numbers follow lifecycle order — validate/discover,
   backup, provision, configure, deploy, restore, validate/rollback — and must
   slot into the component's existing sequence (list the directory first; `00`
   is preflight and `9x` is validate/rollback everywhere). Read-only first.
2. Every play: `serial: 1`, `any_errors_fatal: true`, explicit
   `gather_facts`, FQCN modules, named tasks, `changed_when: false` on reads.
3. Gate: add `allow_<action>: false` and `<action>_confirmation: ""` to the
   defaults (or `inventory/group_vars/all.yml` for migration stages). The first
   task asserts both: the flag is true **and** the confirmation equals the
   exact expected string, which names the host and action.
4. Destructive tasks sit in a block tagged `[never, destructive]` and run only
   with `--tags all,destructive`.
5. Forbidden: `ignore_errors`, `rm -rf`, `StrictHostKeyChecking=no`,
   `pvecm expected`, backup pruning, `bao operator` automation.
6. Add one Make target that runs exactly this playbook. No aggregate target.
7. Tests: add the pair to `APPROVAL_PAIRS` in
   `platform/proxmox/tests/test_repo_safety.py` (migration) or a component test
   that asserts both defaults and the assertion text. Every new gate gets a test.
8. Document the stage, its rollback, and its approval string in the component
   docs; add a `run-gated-stage` note if it has approvals.

## Checks

`make -C <component> check` (yamllint, ansible-lint production profile,
syntax), `make COMPONENT=tests check`, staged gitleaks.
