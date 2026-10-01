# ADR-0009: GitHub checks only

Status: accepted, 2026-09-30, operator decision D7. Supersedes ADR-0008's
plan, deploy, runner and GitHub secret design.

## Decision

GitHub runs checks only, on GitHub-hosted runners, with no configured secrets
or environments. The automatically scoped GitHub token reads repository
contents and pull-request metadata only. The only workflows are `ci.yml` and
`_component-checks.yml`: component lint, tests, syntax, inventory contracts,
configuration scanners, gitleaks, actionlint, zizmor, docs and the PDF build.
Actions remain pinned by full SHA and permissions are explicit per job.
No `pull_request_target`, deploy dispatch, plans or infrastructure changes.

Plans and deployments stay on the local controller in the devcontainer;
each local Make target retains its existing approval gate. VM 340 was never
built and its source component has been removed.

## Why

There must be no path from GitHub into the lab. A self-hosted runner initiates
an outbound connection, but anyone or anything able to trigger its workflow
can still run code inside the network. Egress restrictions and ephemeral
registration do not remove that execution path.

Dependency update PRs remain reviewable changes and never auto-merge. GitHub
has no SSH keys, Proxmox tokens, state encryption passphrases or OpenBao
credentials. If off-site data backup is introduced later, it will be an
outbound push from the lab, never an inbound connection or GitHub-controlled
pull into the network.

## Consequences

CI cannot validate live connectivity or produce infrastructure plans. The
operator measures and reviews these locally. GitHub outages do not block a
local recovery stage. The public repository remains a sanitised source copy;
its workflows are withheld by the publisher policy.
