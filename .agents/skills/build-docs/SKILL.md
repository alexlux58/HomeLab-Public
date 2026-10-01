---
name: build-docs
description: Use when building or updating the technical walkthrough PDF, architecture docs or runbooks - Mermaid diagrams rendered to SVG, clickable file links, real code snippets. Uses the pinned devcontainer toolchain (mermaid-cli, Pandoc, WeasyPrint).
---

# Build the documentation

The walkthrough source is `docs/walkthrough/homelab-technical-walkthrough.md`;
the build is `tools/docs-build/build.py` (Pandoc → HTML5 + print CSS →
WeasyPrint). Each document has exactly one source: link to it or include it,
never copy it.

## Steps

1. Work in the devcontainer or WSL checkout so the pinned mermaid-cli, Pandoc
   and WeasyPrint versions are used (`.devcontainer/`).
2. Diagrams: edit the numbered `.mmd` file in `docs/walkthrough/diagrams/` (shared theme in
   `mermaid-config.json`, `htmlLabels: false`), then `make docs-diagrams` and
   commit the `.mmd`, `.svg` and `manifest.json` together. Embed with
   `<!-- diagram: NN-name caption="..." -->`; every diagram must be used.
3. Code: never paste code. Use
   `<!-- snippet: PATH lines=A-B lang=LANG -->`, run
   `python3 tools/docs-build/build.py --fill` to pin its hash, then write a
   2–5 sentence explanation directly after it. A changed source fails the build
   until you review the lines and update the range and hash.
4. Links: use a Markdown link whose target is `repo:` plus the path from the
   repository root, optionally with `#LA-LB`; inline-code paths are linked
   automatically. `LINK_BASE=public` pins GitHub links to the commit.
5. Tables that could go stale (counts, versions, Make targets, workflows,
   gates, backups) come from `make docs-reference`; include them with
   an include directive naming the table under `docs/reference/generated/`
   with `shift=1`.
6. Destructive stages get a `::: danger` callout; use `::: note` and
   `::: warning` for the rest.
7. Facts come from `docs/reference/environment.md`, `MEMORY.md` and source;
   date anything volatile. Never include secrets, tokens, real `.env` values,
   or internal DDNS names in a document that may be published.

## Checks

`make docs-check` (links, anchors, generated tables, diagrams, snippets) and
`make docs` (zero warnings) pass; `make COMPONENT=tests check` passes,
including `tests/test_docs.py`. The PDF lands in the git-ignored `dist/`
directory next to the walkthrough; CI uploads it as an artifact.
