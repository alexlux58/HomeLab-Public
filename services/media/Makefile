SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# Media stages for media-vm and the workstation Plex host. Every live target
# runs exactly one playbook and needs its gate in EXTRA_JSON. There is no
# aggregate target and no OpenTofu apply or destroy target.
VENV ?= .venv
PYTHON ?= python3
ANSIBLE_PLAYBOOK ?= $(VENV)/bin/ansible-playbook
ANSIBLE_CONFIG ?= ansible/ansible.cfg
INVENTORY ?= ../../inventory/media.yml
TOFU ?= tofu
ARR_TF_DIR ?= terraform/arr
EXTRA_JSON ?=
EXTRA_JSON_ARG = $(if $(strip $(EXTRA_JSON)),-e '$(EXTRA_JSON)',)
PB = ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY)

.PHONY: help setup lint test syntax check plan preflight deploy \
	configure-host deploy-arr sync-quality-profiles check-plex configure-backup \
	arr-fmt arr-validate arr-test arr-plan

help: ## List the media stages
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-24s %s\n", $$1, $$2}'

setup: ## Create the venv and install pinned tooling and collections
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt
	ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(VENV)/bin/ansible-galaxy collection install -r requirements.yml

lint: ## yamllint, ansible-lint, ruff
	$(VENV)/bin/yamllint -s .
	ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(VENV)/bin/ansible-lint ansible/
	$(VENV)/bin/ruff check --line-length 110 scripts tests
	$(VENV)/bin/ruff format --check --line-length 110 scripts tests

test: ## Offline pytest
	$(VENV)/bin/pytest -q -p no:cacheprovider tests

syntax: ## Syntax-check every playbook without contacting a host
	@for playbook in ansible/playbooks/*.yml; do \
		$(PB) --syntax-check "$$playbook"; \
	done

check: lint test syntax ## Run all offline validation

plan: ## Offline: validate and test the *arr root with mocked providers
	$(MAKE) arr-validate arr-test

preflight: ## Read-only media guest preflight
	$(PB) ansible/playbooks/00-preflight.yml $(EXTRA_JSON_ARG)

configure-host: ## Gated: packages, directories, NAS automounts
	$(PB) ansible/playbooks/30-configure-media-host.yml $(EXTRA_JSON_ARG)

deploy-arr: ## Gated: deploy the digest-pinned *arr Compose project
	$(PB) ansible/playbooks/40-deploy-arr-stack.yml $(EXTRA_JSON_ARG)

deploy: deploy-arr ## Alias of deploy-arr (one stage)

sync-quality-profiles: ## Recyclarr --preview, or a real sync behind its own gate
	$(PB) ansible/playbooks/41-sync-quality-profiles.yml $(EXTRA_JSON_ARG)

check-plex: ## Read-only Plex check; backup task behind its gate
	$(PB) ansible/playbooks/45-check-plex.yml $(EXTRA_JSON_ARG)

configure-backup: ## Gated: nightly append-only *arr backup copy
	$(PB) ansible/playbooks/50-configure-media-backup.yml $(EXTRA_JSON_ARG)

arr-fmt: ## Check *arr root formatting
	$(TOFU) -chdir=$(ARR_TF_DIR) fmt -check -recursive

arr-validate: ## Validate the *arr root (init -backend=false)
	$(TOFU) -chdir=$(ARR_TF_DIR) init -backend=false -input=false
	$(TOFU) -chdir=$(ARR_TF_DIR) validate

arr-test: ## Offline tofu test with mocked providers
	$(TOFU) -chdir=$(ARR_TF_DIR) init -backend=false -input=false
	$(TOFU) -chdir=$(ARR_TF_DIR) test

arr-plan: ## Operator plan from workstation; needs backend.hcl and TF_VAR_* inputs
	@test -f $(ARR_TF_DIR)/backend.hcl || { echo "copy backend.hcl.example to backend.hcl first (ADR-0003)"; exit 2; }
	$(TOFU) -chdir=$(ARR_TF_DIR) init -backend-config=backend.hcl -input=false
	$(TOFU) -chdir=$(ARR_TF_DIR) plan -out=arr.tfplan
