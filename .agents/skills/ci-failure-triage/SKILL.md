---
name: ci-failure-triage
description: Use when make check, a pre-commit hook or a CI workflow fails (lint, pytest, ansible-lint, syntax-check, yamllint, ruff, shellcheck, terraform fmt). Reproduces the failure offline, finds the root cause and fixes the source. For a failing safety test use triage-safety-test-failure instead.
---

# Triage a check failure

## Steps

1. Reproduce offline on a Linux toolchain: the devcontainer, WSL, or (on the
   Windows controller) a disposable container built from `git archive HEAD`
   plus the staged diff. Never lint the Windows worktree directly; it may be
   CRLF.
2. Run the single failing target: `make -C <component> lint|test|syntax`.
   yamllint stops ansible-lint from running, so rerun each tool on its own.
3. Classify:
   - **Path drift** after a move: fix the path, keep the assertion.
   - **Tooling setup**: missing collections (`ANSIBLE_CONFIG` must point at the
     component cfg during `ansible-galaxy install`), missing inventory, venv.
   - **Vendored noise**: scans must skip `.venv/`, `.ansible/`,
     `ansible/collections/`; never the source tree.
   - **Real defect**: fix it and add a test that would have caught it.
4. Never disable a rule, add `# noqa`, raise a threshold, or skip a test to get
   green. If a rule is genuinely wrong, stop and ask the operator.
5. Rerun the whole component `make check` and `make COMPONENT=tests check`.

## GitHub Actions

- `ci.yml` runs only the changed components through `_component-checks.yml`;
  reproduce one with the same `make` targets, or `act push -j <job>`.
- A failing `tests/test_workflows.py` means a workflow broke the contract
  (SHA pins, permissions, hosted checks only, no secrets or deploy stages): fix the
  workflow, never the test. Run actionlint with `.github/actionlint.yaml`.
- A new action needs a full commit SHA with the version as a comment.

## Known traps

- Relative paths in `ansible.cfg` resolve from the cfg's own directory.
- Ansible ignores `ansible.cfg` in a world-writable directory (`/mnt/c`).
- `python3` on workstation is the Microsoft Store stub.
