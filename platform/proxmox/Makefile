# ===========================================================================
#  Proxmox VE 8 -> 9 three-node cluster migration
#
#  Every target below runs exactly ONE stage. There is deliberately no
#  "deploy-all" / "migrate-all" target: each destructive stage requires an
#  explicit boolean plus an exact confirmation string supplied on the command
#  line, and each stage is meant to be reviewed by a human before the next one
#  is started.
#
#  Use EXTRA_JSON for approval gates so multi-word confirmation strings remain
#  one Ansible value, e.g.
#      make join-pve3 EXTRA_JSON='{"allow_join_pve3":true,"join_confirmation_pve3":"JOIN pve3 192.168.0.13 TO homelab"}'
#  EXTRA remains available for simple single-word Ansible arguments.
# ===========================================================================

SHELL          := /bin/bash
.SHELLFLAGS    := -eu -o pipefail -c
.DEFAULT_GOAL  := help

VENV           ?= .venv
PY             ?= $(VENV)/bin/python
PIP            ?= $(VENV)/bin/pip
ANSIBLE        ?= $(VENV)/bin/ansible
ANSIBLE_PB     ?= $(VENV)/bin/ansible-playbook
INVENTORY      ?= ../../inventory/hosts.yml
ARTIFACTS      ?= artifacts
EXTRA          ?=
EXTRA_JSON     ?=
HOST           ?=
SERVICE        ?=
SERVICES_INVENTORY ?= ../../inventory/homelab-services.yml
NETKNIFE_SOURCE ?= /Users/labadmin/Desktop/PROJECTS/NetKnife-App
TERRAFORM      ?= terraform
TF_DIR         ?= terraform/homelab-guests
NETBOX_INVENTORY ?= ../../inventory/netbox.yml
NETBOX_TF_DIR  ?= ../../services/netbox/terraform/proxmox-guest

# Long-running stages (backups, restores, upgrades) should survive a laptop
# sleeping. Wrap them in tmux/screen on the controller if you have any doubt.
# project_root anchors artifacts/, host-configs/ and scripts/ for every stage,
# including the NAS preflight that lives in ../nas.
PB             = ANSIBLE_CONFIG=ansible/ansible.cfg $(ANSIBLE_PB) -i $(INVENTORY) -e 'project_root=$(CURDIR)'
EXTRA_JSON_ARG = $(if $(strip $(EXTRA_JSON)),-e '$(EXTRA_JSON)',)

.PHONY: help setup lint test syntax check configure-backup-pull validate-ssh discover nas-preflight capture-config \
        backup-initial backup-final verify-backups prepare-pve3 test-restore \
        precheck-upgrade-pve1 upgrade-pve1 create-cluster join-pve3 \
        precheck-destroy-pve2 postinstall-pve2 join-pve2 build-restore-plan \
        restore-pve2 start-restored-guests verify-backups-initial validate clean-artifacts tree \
        homelab-preflight homelab-base homelab-service homelab-backups \
        netbox-preflight netbox-base netbox-deploy netbox-backups \
        netbox-terraform-fmt netbox-terraform-init netbox-terraform-validate \
        netbox-terraform-plan \
        terraform-fmt terraform-init terraform-validate terraform-plan

help: ## Show this help
	@echo ""
	@echo "Proxmox cluster migration — run one stage at a time, in order."
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Destructive stages additionally require -e flags; see docs/migration-runbook.md"
	@echo ""

# ---------------------------------------------------------------------------
# Local tooling (no network access to the Proxmox hosts)
# ---------------------------------------------------------------------------
setup: ## Create the local virtualenv and install controller dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	ANSIBLE_CONFIG=ansible/ansible.cfg $(VENV)/bin/ansible-galaxy collection install -r requirements.yml
	@echo "OK: controller tooling installed into $(VENV)"

lint: ## Run yamllint + ansible-lint + ruff + shellcheck (offline)
	$(VENV)/bin/yamllint -s .
	ANSIBLE_CONFIG=ansible/ansible.cfg $(VENV)/bin/ansible-lint
	$(VENV)/bin/ruff check scripts tests
	$(VENV)/bin/ruff format --check scripts tests
	@if command -v shellcheck >/dev/null 2>&1; then \
		find ansible/roles scripts -name '*.sh' -print0 | xargs -0 -r shellcheck -S style; \
	else \
		echo "WARN: shellcheck not installed locally (CI enforces it)"; \
	fi

test: ## Run the offline unit test-suite
	$(VENV)/bin/pytest -q

syntax: ## Syntax-check every migration playbook without contacting a host
	@for playbook in ansible/playbooks/migration/*.yml ansible/playbooks/host/*.yml ../nas/ansible/playbooks/*.yml; do 		$(PB) --syntax-check "$$playbook"; 	done

check: lint test syntax ## Run all offline validation

tree: ## Print the repository tree
	@find . -path ./$(VENV) -prune -o -path ./.git -prune -o -print | sort

clean-artifacts: ## Remove generated reports (NEVER touches backups on the NAS)
	@echo "This removes local reports under $(ARTIFACTS)/ only. Backups are never touched."
	find $(ARTIFACTS) -mindepth 1 ! -name '.gitkeep' -delete

# ---------------------------------------------------------------------------
# Stage 0 — read-only
# ---------------------------------------------------------------------------
configure-backup-pull: ## Gated: authorize the restricted workstation pull key on ONE node
	$(PB) ansible/playbooks/host/20-configure-backup-pull.yml $(EXTRA_JSON_ARG) $(EXTRA)

validate-ssh: ## Stage 0a: prove existing SSH key auth works on all three hosts
	$(PB) ansible/playbooks/migration/00-validate-ssh.yml $(EXTRA_JSON_ARG) $(EXTRA)

discover: ## Stage 0b: read-only discovery of all three hosts
	$(PB) ansible/playbooks/migration/01-discover.yml $(EXTRA_JSON_ARG) $(EXTRA)

# ---------------------------------------------------------------------------
# Stage 1-2 — NAS preflight and host configuration capture
# ---------------------------------------------------------------------------
nas-preflight: ## Stage 1: validate the Synology NFS target from all three hosts
	$(PB) ../nas/ansible/playbooks/05-synology-preflight.yml $(EXTRA_JSON_ARG) $(EXTRA)

capture-config: ## Stage 2: capture sanitized host configuration from .11 and .12
	$(PB) ansible/playbooks/migration/10-capture-host-config.yml $(EXTRA_JSON_ARG) $(EXTRA)

# ---------------------------------------------------------------------------
# Stage 3-4 — backups
# ---------------------------------------------------------------------------
backup-initial: ## Stage 3: snapshot-mode backup   (usage: make backup-initial HOST=pve1)
	@test "$(HOST)" = "pve1" || { echo "ERROR: only HOST=pve1 has protected guests"; exit 2; }
	$(PB) ansible/playbooks/migration/20-backup-initial.yml --limit '$(HOST)' $(EXTRA_JSON_ARG) $(EXTRA)

backup-final: ## Stage 4: stopped-guest backup     (usage: make backup-final HOST=pve1)
	@test "$(HOST)" = "pve1" || { echo "ERROR: only HOST=pve1 has protected guests"; exit 2; }
	$(PB) ansible/playbooks/migration/21-backup-final-stopped.yml --limit '$(HOST)' --tags all,destructive $(EXTRA_JSON_ARG) $(EXTRA)

verify-backups-initial: ## Stage 3b: verify the initial generation before final shutdown
	$(PB) ansible/playbooks/migration/25-verify-backups.yml -e '{"backup_verify_generations":["initial"]}' $(EXTRA_JSON_ARG) $(EXTRA)

verify-backups: ## Stage 4b: checksum + vma/tar verify every archive
	$(PB) ansible/playbooks/migration/25-verify-backups.yml $(EXTRA_JSON_ARG) $(EXTRA)

# ---------------------------------------------------------------------------
# Stage 5 — .13 clean install; the old test-restore target is retained as legacy tooling
# ---------------------------------------------------------------------------
prepare-pve3: ## Stage 5a: emit the .13 clean-install checklist / validate after reinstall
	$(PB) ansible/playbooks/migration/30-prepare-pve3.yml $(EXTRA_JSON_ARG) $(EXTRA)

test-restore: ## Legacy plan only (not used by the current rebuild-later migration)
	$(PB) ansible/playbooks/migration/31-test-restore.yml --tags all,destructive $(EXTRA_JSON_ARG) $(EXTRA)

# ---------------------------------------------------------------------------
# Stage 6 — align versions on the seed node
# ---------------------------------------------------------------------------
precheck-upgrade-pve1: ## Stage 6a: pve8to9 --full + repository change report for .11
	$(PB) ansible/playbooks/migration/40-precheck-pve1-upgrade.yml $(EXTRA_JSON_ARG) $(EXTRA)

upgrade-pve1: ## Stage 6b: gated PVE 8 -> 9 upgrade of .11 (requires console access)
	$(PB) ansible/playbooks/migration/41-upgrade-pve1.yml --tags all,destructive $(EXTRA_JSON_ARG) $(EXTRA)

# ---------------------------------------------------------------------------
# Stage 7-9 — cluster
# ---------------------------------------------------------------------------
create-cluster: ## Stage 7: create the cluster on .11 only
	$(PB) ansible/playbooks/migration/50-create-cluster.yml --tags all,destructive $(EXTRA_JSON_ARG) $(EXTRA)

join-pve3: ## Stage 8: join .13 (requires allow_join_pve3 + confirmation string)
	$(PB) ansible/playbooks/migration/60-join-pve3.yml --tags all,destructive $(EXTRA_JSON_ARG) $(EXTRA)

precheck-destroy-pve2: ## Stage 9a: verify every gate before .12 may be clean-installed
	$(PB) ansible/playbooks/migration/70-precheck-pve2-destroy.yml $(EXTRA_JSON_ARG) $(EXTRA)

postinstall-pve2: ## Stage 9b: validate .12 after its manual clean install
	$(PB) ansible/playbooks/migration/71-postinstall-pve2.yml $(EXTRA_JSON_ARG) $(EXTRA)

join-pve2: ## Stage 9c: join .12 to the cluster
	$(PB) ansible/playbooks/migration/72-join-pve2.yml --tags all,destructive $(EXTRA_JSON_ARG) $(EXTRA)

# ---------------------------------------------------------------------------
# Legacy restore tooling plus final validation
# ---------------------------------------------------------------------------
build-restore-plan: ## Legacy plan only: generate the retired .12 restore plan
	$(PY) scripts/build_restore_plan.py \
		--discovery $(ARTIFACTS)/discovery.json \
		--collisions $(ARTIFACTS)/vmid-collisions.json \
		--manifest $(ARTIFACTS)/backup-manifest.json \
		--source-host pve2 --target-node pve2 \
		--disposable-host pve \
		--out-json $(ARTIFACTS)/restore-plan.json \
		--out-markdown $(ARTIFACTS)/restore-plan.md

restore-pve2: ## Legacy plan only: restore .12 guests (not in current migration)
	$(PB) ansible/playbooks/migration/80-restore-pve2.yml --tags all,destructive $(EXTRA_JSON_ARG) $(EXTRA)

start-restored-guests: ## Legacy plan only: start restored .12 guests
	$(PB) ansible/playbooks/migration/81-start-restored-guests.yml $(EXTRA_JSON_ARG) $(EXTRA)

# ---------------------------------------------------------------------------
# LAN inventory dashboard (independent of the migration stages)
# ---------------------------------------------------------------------------
lan-scan: ## Read-only LAN sweep -> artifacts/lan-inventory.json
	ssh -o BatchMode=yes pve1 'bash -s' < scripts/lan-scan.sh > $(ARTIFACTS)/lan-inventory.json
	@$(PY) -c "import json;d=json.load(open('$(ARTIFACTS)/lan-inventory.json'));print(f'  {len(d)} devices')"

lan-site: ## Build the static LAN inventory page -> site/index.html
	$(PY) scripts/build_lan_inventory_site.py

lan-preview: ## Serve site/ locally at http://127.0.0.1:8899
	@echo "http://127.0.0.1:8899/index.html  (ctrl-c to stop)"
	@cd site && python3 -m http.server 8899 --bind 127.0.0.1

lan-deploy: ## Copy the page to the Synology (requires Web Station + a Volume 1 docroot)
	@test -f site/index.html || { echo "run 'make lan-site' first"; exit 2; }
	scp site/index.html nas:/volume1/web/lan/index.html
	@echo "deployed -> http://192.168.0.20/lan/"

# ---------------------------------------------------------------------------
# Steady-state Home Lab guest and application automation
# ---------------------------------------------------------------------------
homelab-preflight: ## Read-only validation of VM 300 before reconciliation
	ANSIBLE_CONFIG=../../services/homelab-services/ansible/ansible.cfg $(ANSIBLE_PB) -i $(SERVICES_INVENTORY) ../../services/homelab-services/ansible/playbooks/31-preflight-services.yml

homelab-base: ## Reconcile VM 300 Docker, hardening, and filesystem prerequisites
	ANSIBLE_CONFIG=../../services/homelab-services/ansible/ansible.cfg $(ANSIBLE_PB) -i $(SERVICES_INVENTORY) ../../services/homelab-services/ansible/playbooks/30-configure-guest.yml $(EXTRA_JSON_ARG)

homelab-service: ## Reconcile one app (usage: make homelab-service SERVICE=homepage)
	@case "$(SERVICE)" in \
		homepage|it-tools|linkding|netknife|npm|pairdrop|speedtest-tracker|uptime-kuma) ;; \
		*) echo "ERROR: set SERVICE to one reviewed Home Lab application"; exit 2 ;; \
	esac
	ANSIBLE_CONFIG=../../services/homelab-services/ansible/ansible.cfg $(ANSIBLE_PB) -i $(SERVICES_INVENTORY) ../../services/homelab-services/ansible/playbooks/40-deploy-service.yml \
		-e homelab_services_service_name='$(SERVICE)' \
		-e homelab_services_controller_netknife_source='$(NETKNIFE_SOURCE)' \
		$(EXTRA_JSON_ARG) $(EXTRA)

homelab-backups: ## Reconcile VM 300 application-aware backup timer
	ANSIBLE_CONFIG=../../services/homelab-services/ansible/ansible.cfg $(ANSIBLE_PB) -i $(SERVICES_INVENTORY) ../../services/homelab-services/ansible/playbooks/50-configure-backups.yml $(EXTRA_JSON_ARG)

# ---------------------------------------------------------------------------
# NetBox (VM 330 exists; see MEMORY.md). Every stage below is gated.
# Each stage is separate on purpose; there is no aggregate NetBox target.
# ---------------------------------------------------------------------------
netbox-preflight: ## Read-only validation of the NetBox guest before reconciliation
	ANSIBLE_CONFIG=../../services/netbox/ansible/ansible.cfg $(ANSIBLE_PB) -i $(NETBOX_INVENTORY) ../../services/netbox/ansible/playbooks/30-preflight.yml

netbox-base: ## Reconcile NetBox guest Docker, hardening, and prerequisites
	ANSIBLE_CONFIG=../../services/netbox/ansible/ansible.cfg $(ANSIBLE_PB) -i $(NETBOX_INVENTORY) ../../services/netbox/ansible/playbooks/31-configure-guest.yml $(EXTRA_JSON_ARG)

netbox-deploy: ## Deploy NetBox (requires the documented approval, see docs/netbox-plan.md)
	ANSIBLE_CONFIG=../../services/netbox/ansible/ansible.cfg $(ANSIBLE_PB) -i $(NETBOX_INVENTORY) ../../services/netbox/ansible/playbooks/40-deploy.yml \
		$(EXTRA_JSON_ARG) $(EXTRA)

netbox-backups: ## Reconcile the NetBox application-aware backup timer
	ANSIBLE_CONFIG=../../services/netbox/ansible/ansible.cfg $(ANSIBLE_PB) -i $(NETBOX_INVENTORY) ../../services/netbox/ansible/playbooks/50-configure-backups.yml $(EXTRA_JSON_ARG)

netbox-terraform-fmt: ## Check planned NetBox guest Terraform formatting
	$(TERRAFORM) -chdir=$(NETBOX_TF_DIR) fmt -check -recursive

netbox-terraform-init: ## Initialize the pinned Proxmox provider without a backend
	$(TERRAFORM) -chdir=$(NETBOX_TF_DIR) init -backend=false

netbox-terraform-validate: ## Validate the planned NetBox guest Terraform configuration
	$(TERRAFORM) -chdir=$(NETBOX_TF_DIR) validate

netbox-terraform-plan: ## Plan the planned NetBox guest. Apply stays a manual, reviewed step.
	$(TERRAFORM) -chdir=$(NETBOX_TF_DIR) plan

terraform-fmt: ## Check Home Lab guest Terraform formatting
	$(TERRAFORM) -chdir=$(TF_DIR) fmt -check -recursive

terraform-init: ## Initialize the pinned Proxmox provider without a backend
	$(TERRAFORM) -chdir=$(TF_DIR) init -backend=false

terraform-validate: ## Validate Home Lab guest Terraform configuration
	$(TERRAFORM) -chdir=$(TF_DIR) validate

terraform-plan: ## Import-first, non-destructive Terraform plan for VMs 300 and 310
	$(TERRAFORM) -chdir=$(TF_DIR) plan

# ---------------------------------------------------------------------------
# Ladder rung L0: Proxmox automated-install answer files from inventory/lab.yml.
# Dry run (secrets redacted) by default; WRITE=1 writes artifacts/autoinstall/
# with mode 0600 using PVE_ROOT_PASSWORD_HASH, PVE_ROOT_SSH_KEYS_FILE and
# PVE_MAILTO from the operator's environment. ISO preparation and booting are
# manual (docs/runbooks/rebuild-from-zero.md, L0).
# ---------------------------------------------------------------------------
NODE           ?=
WRITE          ?=

rebuild-l0-answer-files: ## L0: render Proxmox answer files (dry run unless WRITE=1)
	$(PY) scripts/build_answer_files.py $(if $(NODE),--node $(NODE),) $(if $(WRITE),--write,)

rebuild-l1-host-config: ## L1: vzdump jobs, onboot, startup from lab.yml (gated by EXTRA_JSON)
	$(PB) ansible/playbooks/host/10-configure-hosts.yml $(EXTRA_JSON_ARG) $(EXTRA)

# ---------------------------------------------------------------------------
# Rebuild-only guest root (ADR-0007, ladder rung L3). fmt/validate/test are
# offline (the test mocks the provider). The plan is an operator step that
# needs backend.hcl, the API token and the state passphrase; apply has no
# target and is run by hand after the plan is reviewed.
# ---------------------------------------------------------------------------
TOFU           ?= tofu
REBUILD_TF_DIR ?= terraform/rebuild-guests

rebuild-guests-fmt: ## Check rebuild-only root formatting
	$(TOFU) -chdir=$(REBUILD_TF_DIR) fmt -check -recursive

rebuild-guests-validate: ## Validate the rebuild-only root (init -backend=false)
	$(TOFU) -chdir=$(REBUILD_TF_DIR) init -backend=false -input=false
	$(TOFU) -chdir=$(REBUILD_TF_DIR) validate

rebuild-guests-test: ## Offline tofu test with a mocked provider
	$(TOFU) -chdir=$(REBUILD_TF_DIR) init -backend=false -input=false
	$(TOFU) -chdir=$(REBUILD_TF_DIR) test

rebuild-guests-plan: ## L3 operator plan; needs REBUILD_VARS='-var-file=...' with names + confirmation
	@test -f $(REBUILD_TF_DIR)/backend.hcl || { echo "copy backend.hcl.example to backend.hcl first (ADR-0003)"; exit 2; }
	$(TOFU) -chdir=$(REBUILD_TF_DIR) init -backend-config=backend.hcl -input=false
	$(TOFU) -chdir=$(REBUILD_TF_DIR) plan -out=rebuild.tfplan $(REBUILD_VARS)

validate: ## Stage 11: full three-node cluster validation + migration report
	$(PB) ansible/playbooks/migration/90-validate-cluster.yml $(EXTRA_JSON_ARG) $(EXTRA)
