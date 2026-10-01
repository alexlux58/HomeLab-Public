# Documentation index

Each document has exactly one source; other documents link to it or include it
at build time, never copy it.

| Directory | What it holds |
| --- | --- |
| [`architecture/`](architecture/README.md) | Diagram index and pointers to each component's architecture document |
| [`decisions/`](decisions/) | Architecture decision records (ADR-0001 to ADR-0009) |
| [`runbooks/`](runbooks/) | Operator procedures: [rebuild](runbooks/rebuild-from-zero.md), [CI checks](runbooks/ci-cd.md), [state migration](runbooks/state-migration.md), [OpenBao ceremony](runbooks/openbao-init-ceremony.md), [Windows/WSL2](runbooks/windows-wsl2-setup.md) |
| [`reference/`](reference/) | Environment facts, lessons learned, operator inputs, backup and coverage matrices, and [`generated/`](reference/generated/) tables |

Approved physical maintenance: [Disk 3 replacement](../platform/nas/docs/disk3-replacement.md).
The [second backup copy](../platform/proxmox/docs/backup-pull.md) remains
prepared until its SSH/key prerequisites and acceptance checks succeed.
| [`walkthrough/`](walkthrough/homelab-technical-walkthrough.md) | The technical walkthrough source, its diagrams, and the PDF build output (`dist/`, git-ignored) |
| [`_plan/`](_plan/) | Phase evidence records and the media ledger |

## Building

```bash
make docs-check        # offline: links, anchors, generated tables, diagrams, snippets
make docs              # walkthrough PDF; LINK_BASE=local|public PAPER=A4|Letter
make docs-reference    # regenerate reference/generated/*.md
make docs-diagrams     # re-render the Mermaid diagrams (devcontainer)
```

Files under [`reference/generated/`](reference/generated/) are written by
[`tools/docs/generate_reference.py`](../tools/docs/generate_reference.py); edit
their sources, not the tables.

## Music Library

The Music Library component documents itself in
[`services/music-library/README.md`](../services/music-library/README.md). The
pre-Phase 5 walkthrough, including its Music Library section, is kept for
history in
[`walkthrough/legacy/HOMELAB-TECHNICAL-WALKTHROUGH.md`](walkthrough/legacy/HOMELAB-TECHNICAL-WALKTHROUGH.md).
