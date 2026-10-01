SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
VENV ?= .venv
ANSIBLE_PLAYBOOK ?= $(VENV)/bin/ansible-playbook
INVENTORY ?= ../../inventory/homelab-services.yml
ANSIBLE_CONFIG ?= ansible/ansible.cfg
REQUIREMENTS ?= ../../platform/proxmox/requirements.txt

EXTRA_JSON ?=
EXTRA_JSON_ARG = $(if $(strip $(EXTRA_JSON)),-e '$(EXTRA_JSON)',)

.PHONY: help setup lint test syntax check plan preflight deploy backup
help:
	@echo "VM 300 stages: preflight, deploy SERVICE=<approved-name>, backup"
setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r $(REQUIREMENTS)
	ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(VENV)/bin/ansible-galaxy collection install -r ../../platform/proxmox/requirements.yml
lint:
	$(VENV)/bin/yamllint -s .
test:
	$(VENV)/bin/pytest -q -p no:cacheprovider tests
syntax:
	@for playbook in ansible/playbooks/*.yml; do ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) --syntax-check "$$playbook"; done
check: lint test syntax
plan:
	@echo "VM 300 plan is read-only and remains component-scoped."
preflight:
	@ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/31-preflight-services.yml
deploy:
	@test -n "$(SERVICE)" || { echo "set SERVICE to one reviewed application"; exit 2; }
	@case "$(SERVICE)" in homepage|it-tools|linkding|netknife|npm|pairdrop|speedtest-tracker|uptime-kuma) ;; *) echo "unapproved service"; exit 2 ;; esac
	@ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/40-deploy-service.yml -e homelab_services_service_name=$(SERVICE) $(EXTRA_JSON_ARG)
backup:
	@ANSIBLE_CONFIG=$(ANSIBLE_CONFIG) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/50-configure-backups.yml $(EXTRA_JSON_ARG)
