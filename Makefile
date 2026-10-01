SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

COMPONENT ?=

.PHONY: help setup lint test syntax check plan preflight deploy rebuild-plan docs-check docs docs-reference docs-diagrams

help:
	@echo "Use make COMPONENT=<path> <target> for one component."
	@echo "Example: make COMPONENT=platform/proxmox check"
	@echo "Targets: setup lint test syntax check plan preflight deploy"
	@echo "make rebuild-plan  prints the L0-L8 ladder and checks local prerequisites (offline)"
	@echo "make docs          builds the walkthrough PDF (LINK_BASE=local|public PAPER=A4|Letter)"
	@echo "make docs-check    offline docs checks; docs-reference / docs-diagrams regenerate"

define dispatch_target
$1:
	@test -n "$(COMPONENT)" || { echo "set COMPONENT to one component path"; exit 2; }
	$(MAKE) -C "$(COMPONENT)" $1
endef

$(foreach target,setup lint test syntax check plan preflight deploy,$(eval $(call dispatch_target,$(target))))

# Prints the ladder; runs nothing. Each rung is one component target.
rebuild-plan:
	python3 tools/rebuild/rebuild_plan.py

# Offline documentation checks: links and anchors (including repo: links),
# generated reference freshness, diagram sources vs SVGs, walkthrough snippet
# hashes, then markdownlint when it is installed (CI always runs it).
docs-check:
	python3 tools/docs/check_links.py
	python3 tools/docs/generate_reference.py --check
	python3 tools/docs-build/render_diagrams.py --check
	python3 tools/docs-build/build.py --check
	@if command -v markdownlint-cli2 >/dev/null 2>&1; then markdownlint-cli2; else echo "markdownlint-cli2 not installed here; ci.yml runs it"; fi

# Regenerate docs/reference/generated/*.md from the repository.
docs-reference:
	python3 tools/docs/generate_reference.py

# Re-render docs/walkthrough/diagrams/*.svg (needs mermaid-cli; devcontainer).
docs-diagrams:
	python3 tools/docs-build/render_diagrams.py

# Build docs/walkthrough/dist/homelab-technical-walkthrough.pdf (Pandoc +
# WeasyPrint). Fails on any warning, broken link or anchor, or changed snippet.
LINK_BASE ?= local
PAPER ?= A4
docs:
	LINK_BASE=$(LINK_BASE) PAPER=$(PAPER) python3 tools/docs-build/build.py
