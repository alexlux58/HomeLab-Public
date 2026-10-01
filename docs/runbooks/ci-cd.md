# CI checks

GitHub checks source on hosted runners; it has no path into the lab.
See [ADR-0009](../decisions/ADR-0009-github-checks-only.md).

## Checks and permissions

`ci.yml` selects changed components and calls `_component-checks.yml`.
Contracts, gitleaks and docs always run. Music Library keeps its own
lint, test and import job. Actions are pinned by full SHA; workflow
permissions default to empty and jobs request read access only.

Actionlint checks syntax. Zizmor is installed at a pinned version with a
pinned SHA-256 and runs offline audits. There are no configured GitHub
secrets, environments, lab runners, deploy dispatches or plan jobs.

## Repository setup

Private origin: [HomeLab-Private](https://github.com/labadmin/HomeLab-Private.git).
Public origin: [HomeLab-Public](https://github.com/alexlux58/HomeLab-Public.git).
Enable Actions on the private repository using hosted runners only. Do not
register a self-hosted runner or configure lab credentials. Renovate may open
dependency PRs; auto-merge stays disabled. Public workflows remain withheld.

## Local operations and rollback

After checks pass, review the change and run one gated local Make target in
the devcontainer. Approval flags and exact confirmations are the operator's.
State plans and migrations follow ADR-0003 and its migration runbook.
No GitHub event can authorize or launch a lab stage.

A failing check stops publication or pushing until repaired. Revert a faulty
source change with a normal commit; never force-push. CI does not change
production. Deployment rollback follows the component runbook.
