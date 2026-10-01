SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

VENV ?= .venv
PYTHON ?= python3

.PHONY: help setup lint test syntax check plan preflight deploy

help:
	@echo "Cross-component contract tests: setup lint test syntax check"

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt

lint:
	$(VENV)/bin/ruff check --line-length 110 . ../tools/repo-checks ../tools/rebuild ../tools/docs ../tools/docs-build ../.claude/hooks
	$(VENV)/bin/ruff format --check --line-length 110 . ../tools/repo-checks ../tools/rebuild ../tools/docs ../tools/docs-build ../.claude/hooks
	bash -n ../.claude/hooks/guard.sh

test:
	$(VENV)/bin/pytest -q -p no:cacheprovider

syntax:
	$(VENV)/bin/python -m py_compile ../.claude/hooks/guard.py ../tools/repo-checks/forbidden_constructs.py ../tools/rebuild/rebuild_plan.py ../tools/docs/check_links.py ../tools/docs/generate_reference.py ../tools/docs-build/build.py ../tools/docs-build/render_diagrams.py

check: lint test syntax

plan preflight deploy:
	@echo "tests has no live stages"; exit 2
