# ADR-0008: CI/CD with GitHub Actions

Status: superseded in part by [ADR-0009](ADR-0009-github-checks-only.md),
2026-09-30, operator decision D7.

The original design combined hosted checks with lab-hosted plans and gated
deployments. The runner was never built. Its code and deploy workflows have
been removed: outbound runner registration still exposed code execution
inside the network to workflow triggers.

The retained decisions are hosted offline checks, full action SHA pins,
explicit least-privilege permissions, no `pull_request_target`, verified
scanner binaries and disabled dependency auto-merge. GitHub has no lab
secrets or deployment authority. Plans and gated stages run locally only.
