# ADR-0001: inventory boundary during Phase 1

Status: superseded by ADR-0005 (2026-09-29). Accepted for Phase 1.

The imported repositories contain distinct Ansible inventories for Proxmox,
VM 300 services, observability, and OpenBao. Their host groups and variable
contracts are not equivalent. Phase 1 therefore places each inventory under
the single root `inventory/` boundary while retaining its source-specific
subdirectory or filename. Phase 3 will generate and validate one inventory
from `inventory/lab.yml` after every consumer is mapped.

Blindly merging group variables during an offline tree move could target the
wrong host. No live inventory or host configuration was changed by this ADR.
