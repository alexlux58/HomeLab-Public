---
name: publish-sanitised
description: Use when refreshing the public sanitised copy (public/ -> github.com/alexlux58/HomeLab-Public). Runs the private publisher and scanner, then summarises the diff for the operator. Never edits public/ by hand.
---

# Publish the sanitised copy

`public/` is a separate, generated repository. `tools/publish/` is private and
is never published.

## Preconditions

- The private tree is committed, `make COMPONENT=tests check` passes and
  `make docs-check` passes.
- `public/` has a clean working tree (the publisher refuses otherwise, so every
  file it replaces stays recoverable from `public/`'s history).
- You are in the devcontainer: the publisher needs perl, Pandoc, WeasyPrint,
  mermaid-cli and poppler's `pdftotext`.

## Steps

1. Run `python3 tools/publish/publish_snapshot.py`. It selects files by
   `tools/publish/policy.yml`, sanitises them, re-renders diagrams, builds the
   walkthrough PDF with `LINK_BASE=public`, scans everything (PDF and SVG text
   included) and only then replaces `public/`.
2. Any scanner finding stops the run and leaves `public/` untouched. Fix the
   private source or the sanitiser; never allowlist a real value and never edit
   `public/` directly. `--keep-staging` keeps the sanitised tree for inspection.
3. Run `tools/publish/check-public.sh` on `public/` and gitleaks over it.
4. Summarise the published diff for the operator: files added, removed and
   changed per area, anything newly published, and anything that looks like an
   address, name or key.
5. If publishing and pushing are authorized, commit from the devcontainer
   with the scanner hook, then push only to this checkout's approved origin
   after checks pass. The pre-push hook scans the commits with gitleaks.
   Never force, delete, mirror, bypass hooks or use another remote or URL.
   Git transport may use the existing Windows gh/GCM keyring without exporting
   credentials; install the common pre-push guard in both checkouts first.
