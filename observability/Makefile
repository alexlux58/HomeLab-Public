SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

VENV ?= .venv
PYTHON ?= python3.12
ANSIBLE_PLAYBOOK ?= $(VENV)/bin/ansible-playbook
INVENTORY ?= ../inventory/observability/hosts.yml
EXTRA_JSON ?=
EXTRA_JSON_ARG = $(if $(strip $(EXTRA_JSON)),-e '$(EXTRA_JSON)',)

.PHONY: help setup install-hooks lint test syntax check preflight bootstrap deploy validate \
	update-dashboards backup restore-drill

help: ## List independently gated stages
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

setup: ## Install local controller tooling
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/ansible-galaxy collection install -r requirements.yml

install-hooks: ## Install pinned pre-commit secret and safety checks
	$(VENV)/bin/pre-commit install

lint: ## Validate YAML, Ansible, Compose, Prometheus, and secret hygiene
	$(VENV)/bin/yamllint -s .
	ANSIBLE_CONFIG=ansible.cfg $(VENV)/bin/ansible-lint ansible/
	$(VENV)/bin/python scripts/validate_repo.py
	@if command -v gitleaks >/dev/null 2>&1; then gitleaks detect --no-banner --redact; else echo "WARN: gitleaks not installed"; fi

test: ## Run offline repository tests
	$(VENV)/bin/python -m unittest discover -s tests -v

syntax: ## Syntax-check every playbook without contacting a host
	@for playbook in ansible/playbooks/*.yml; do 		ANSIBLE_CONFIG=ansible.cfg $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) --syntax-check "$$playbook"; 	done

check: lint test syntax ## Run all offline validation

preflight: ## Read-only discovery; writes artifacts/preflight.json on controller
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/00-preflight.yml

bootstrap: ## Harden the already-created observability VM; no stack deployment
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/20-bootstrap.yml $(EXTRA_JSON_ARG)

deploy: ## Deploy central stack only after reviewing preflight and providing secrets
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/40-deploy.yml $(EXTRA_JSON_ARG)

validate: ## Read-only runtime validation
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/90-validate.yml

update-dashboards: ## Gated dashboard/rule update without restarting containers
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) \
		ansible/playbooks/41-update-dashboards.yml $(EXTRA_JSON_ARG)

backup: ## Trigger one application-aware backup on the observability VM
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/50-backup.yml

restore-drill: ## Validate a named backup archive without overwriting live data
	@test -n "$(ARCHIVE)" || { echo "usage: make restore-drill ARCHIVE=/srv/observability/backups/<file>"; exit 2; }
	ssh observability sudo /opt/observability/scripts/restore-drill.sh "$(ARCHIVE)"
