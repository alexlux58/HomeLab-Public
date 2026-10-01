---
name: triage-safety-test-failure
description: Use when a safety or contract test fails (test_repo_safety.py, inventory schema, OpenBao validate_repo, root tests/ guardrails, hook tests). Decides whether the change or the test is wrong. Never deletes, skips or loosens a safety assertion.
---

# Triage a safety-test failure

A safety test failing usually means it did its job.

## Steps

1. Read the assertion and its docstring or comment. Most name the incident
   that created them (see `docs/reference/lessons-learned.md`).
2. Decide which case applies:
   - **The change broke the contract** (new `ignore_errors`, a missing
     `never`/`destructive` tag, an `allow_*` default of `true`, an aggregate
     target, pruning, a vacuous alert). Fix the change.
   - **A path moved.** Update the path and keep the assertion unchanged.
   - **A new gate or approval flag.** Add it to the test's expected set
     (`APPROVAL_PAIRS` and friends) together with its enforcement.
   - **Vendored code is being scanned.** Narrow the scan to exclude
     `.venv/`, `.ansible/` or `ansible/collections/` only.
3. If the test itself looks wrong, stop and explain to the operator. Do not
   edit it until they agree.
4. Never delete a test, mark it skip or xfail, loosen a regex, or lower a
   count to make it pass. A conditional skip is acceptable only for a file
   excluded by a recorded secret boundary, and it must re-activate on its own.

## Checks

The original assertion text is unchanged or strictly stronger;
`make -C <component> check` and `make COMPONENT=tests check` pass.
