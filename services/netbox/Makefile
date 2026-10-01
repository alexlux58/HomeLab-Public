SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
VENV ?= .venv
ANSIBLE_PLAYBOOK ?= $(VENV)/bin/ansible-playbook
INVENTORY ?= ../../inventory/netbox.yml
ANSIBLE_CONFIG ?= ansible/ansible.cfg
REQUIREMENTS ?= ../../platform/proxmox/requirements.txt
COLLECTIONS ?= ../../platform/proxmox/requirements.yml

EXTRA_JSON ?=
EXTRA_JSON_ARG = $(if $(strip $(EXTRA_JSON)),-e '$(EXTRA_JSON)',)

.PHONY: help setup lint test syntax check plan preflight deploy backup
help:
	@echo "NetBox stages: preflight, deploy, backup; no aggregate deployment."
setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r $(REQUIREMENTS)
	ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(VENV)/bin/ansible-galaxy collection install -r $(COLLECTIONS)
lint:
	$(VENV)/bin/yamllint -s .
test:
	$(VENV)/bin/pytest -q -p no:cacheprovider tests
syntax:
	@for playbook in ansible/playbooks/*.yml; do ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) --syntax-check "$$playbook"; done
check: lint test syntax
plan:
	@echo "NetBox plan is reviewed separately from deployment."
preflight:
	@ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/30-preflight.yml
deploy:
	@ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/40-deploy.yml $(EXTRA_JSON_ARG)
backup:
	@ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/50-configure-backups.yml $(EXTRA_JSON_ARG)
