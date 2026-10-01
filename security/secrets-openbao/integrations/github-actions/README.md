# GitHub Actions boundary — checks only

ADR-0009/D7 supersedes the former prepared JWT/OIDC integration. GitHub runs
offline checks on hosted runners, with SHA-pinned actions, least permissions
and no secrets. There is no GitHub identity, credential, runner or network
route into OpenBao or the Home Lab. Do not configure OIDC access for Actions.

Plans and deployments stay local with their existing gates. Off-site data
backup, if later approved, initiates an outbound push from the lab.
See [ADR-0009](../../../../docs/decisions/ADR-0009-github-checks-only.md).
