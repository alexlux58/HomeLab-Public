SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
VENV ?= .venv
ANSIBLE_PLAYBOOK ?= $(VENV)/bin/ansible-playbook
INVENTORY ?= ../../inventory/hosts.yml
PLAYBOOK ?= ansible/playbooks/05-synology-preflight.yml
REQUIREMENTS ?= ../../platform/proxmox/requirements.txt
COLLECTIONS ?= ../../platform/proxmox/requirements.yml
# The preflight reads the Proxmox migration's discovery artifacts and scripts.
PROJECT_ROOT ?= $(abspath ../proxmox)

.PHONY: help setup lint test syntax check plan preflight deploy
help:
	@echo "NAS stages: preflight (read-only); configuration remains gated."
setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r $(REQUIREMENTS)
	ANSIBLE_CONFIG=ansible/ansible.cfg $(VENV)/bin/ansible-galaxy collection install -r $(COLLECTIONS)
lint:
	$(VENV)/bin/yamllint -s .
test:
	@test -d tests || true
syntax:
	@ANSIBLE_CONFIG=ansible/ansible.cfg $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) --syntax-check $(PLAYBOOK)
check: lint test syntax
plan:
	@echo "No NAS plan is executed in Phase 1."
preflight:
	@ANSIBLE_CONFIG=ansible/ansible.cfg $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) -e 'project_root=$(PROJECT_ROOT)' $(PLAYBOOK)
deploy:
	@echo "NAS deployment is a separately gated stage."; exit 2
