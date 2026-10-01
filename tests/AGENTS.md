# AGENTS.md — tests

Inherits `../AGENTS.md`; these rules add to it.

## Purpose and layout

Cross-component contract tests (pytest) that no single component owns:

- `test_claude_guard.py` — the Claude Code PreToolUse guard and settings.
- `test_codex_rules.py` — the Codex execpolicy rules and project config.
- `test_agent_workspace.py` — AGENTS/CLAUDE/MEMORY shape, skills and links.
- `test_denylist.py` — no secret-bearing path or secret-shaped value is tracked.
- `test_docs.py` — docs layout, generated tables, diagrams, walkthrough
  snippets and sections, and the PDF build contract.
- `test_forbidden_constructs.py` — the shared checker in
  `../tools/repo-checks/forbidden_constructs.py`, also run by pre-commit.

Component-specific safety tests stay in their component (for example
`platform/proxmox/tests/test_repo_safety.py`).

## Commands

```text
make setup        # venv with the pins in requirements.txt
make check        # ruff, pytest, py_compile; offline
```

## Component rules

- Every guardrail (hook, rule, pre-commit check) has a test here; adding one
  means adding its test in the same commit.
- The forbidden-construct baseline is a ratchet: remove entries as findings
  are fixed; never add one without an entry in `MEMORY.md` "Known gaps".
- Tests read files and run local scripts only. They never contact a host.

## Definition of done

`make check` passes here and in every component you touched; staged gitleaks
passes.
