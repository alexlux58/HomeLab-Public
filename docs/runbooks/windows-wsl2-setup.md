# Windows: WSL2 and devcontainer setup

workstation (Windows 11 Home) is the operator's controller. The toolchain runs in
Linux: either the devcontainer (`.devcontainer/`) or a WSL2 distribution.
Nothing here changes Windows features beyond WSL, which is already enabled.

## Why not the Windows checkout

- **Ansible ignores `ansible.cfg` in a world-writable directory.** Everything
  under `/mnt/c` is world-writable from WSL, so every component's safety
  settings (host-key checking, BatchMode, `gathering = explicit`) would be
  silently dropped. Keep the checkout on the WSL filesystem (`~/src/Home-Lab`).
- The Windows checkout has `core.symlinks=false` and no Developer Mode, so the
  `.claude/skills/*` links are placeholder files there and Claude skills do not
  load.
- `python3` on Windows is the Microsoft Store stub.
- Git for Windows defaults to `core.autocrlf=true`; `.gitattributes` now forces
  LF, but tools run from Windows may still see CRLF in an old checkout.

## Pinned versions

| Tool | Version | Where pinned |
| --- | --- | --- |
| Python | 3.12 | `.devcontainer/Dockerfile` base image |
| ansible-core | 2.19.4 (components pin their own too) | Dockerfile, component `requirements.txt` |
| ansible-lint / yamllint | 25.12.2 / 1.37.1 | Dockerfile |
| OpenTofu | 1.12.6 | Dockerfile (`OPENTOFU_VERSION`) |
| Node.js | 24.21.0 LTS | Dockerfile (`NODE_VERSION`) |
| mermaid-cli | 12.0.0 | Dockerfile (`MERMAID_CLI_VERSION`) |
| Pandoc | 3.12 | Dockerfile (`PANDOC_VERSION`) |
| WeasyPrint | 70.0 | Dockerfile (`WEASYPRINT_VERSION`) |
| gitleaks | 8.30.1 | Dockerfile (`GITLEAKS_VERSION`) |
| pre-commit / ruff / pytest | 4.3.0 / 0.12.11 / 8.4.2 | Dockerfile, `tests/requirements.txt` |

Change a version in the Dockerfile and this table in the same commit.

## Option A — devcontainer (recommended)

1. Install a WSL2 distribution if none exists (operator step; today only
   `docker-desktop` is present): `wsl --install -d Ubuntu-24.04`.
2. In the distribution, clone the private repository onto the Linux
   filesystem, for example from the Windows copy:
   `git clone /mnt/c/Users/labuser/Documents/Home-Lab ~/src/Home-Lab`.
   Then `git -C ~/src/Home-Lab config core.symlinks true`.
3. Open `~/src/Home-Lab` in VS Code with the WSL and Dev Containers extensions
   and choose **Reopen in Container**. `post-create.sh` installs pre-commit and
   runs `make setup` in each component (downloads pinned packages only).
4. Verify: `make COMPONENT=tests check` and `make COMPONENT=platform/proxmox check`.

## Option B — plain WSL2

Follow steps 1–2, then install the tools in the table at the listed versions and
run `make -C <component> setup` for each component.

## Option C — disposable container (what the agents use on workstation today)

Without WSL, run checks in a throwaway container against the committed tree
plus the staged diff, so the Windows worktree is never linted directly:
`git archive HEAD` into the container, `git apply` the staged diff, then run
`make -C <component> check`. This is how the Phase 1 and Phase 2 gates were
verified.

## Codex and Claude Code

- Codex: mark the project trusted so `.codex/config.toml` and
  `.codex/rules/homelab.rules` load. Skills load from `.agents/skills/`.
- Claude Code: `.claude/settings.json` and its guard hook load automatically;
  skills load from `.claude/skills/` in a checkout with working symlinks.

## Rollback

Delete the WSL distribution or the container image. Nothing on Windows or in
the live lab changes.
