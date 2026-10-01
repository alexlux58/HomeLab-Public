SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
VENV ?= .venv
ANSIBLE_PLAYBOOK ?= $(VENV)/bin/ansible-playbook
INVENTORY ?= ../../inventory/hosts.yml
ANSIBLE_CONFIG ?= ansible/ansible.cfg
REQUIREMENTS ?= ../../platform/proxmox/requirements.txt

.PHONY: help setup lint test syntax check plan preflight deploy
help:
	@echo "AAA stages: preflight only until the FreeRADIUS design is declared."
setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r $(REQUIREMENTS)
	ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(VENV)/bin/ansible-galaxy collection install -r ../../platform/proxmox/requirements.yml
lint:
	$(VENV)/bin/yamllint -s .
test:
	@test -d tests || true
syntax:
	@ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) --syntax-check ansible/playbooks/00-preflight.yml
check: lint test syntax
plan:
	@echo "AAA plan is read-only in Phase 1."
preflight:
	@ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/00-preflight.yml
deploy:
	@echo "AAA deployment is not authorized by Phase 1."; exit 2
