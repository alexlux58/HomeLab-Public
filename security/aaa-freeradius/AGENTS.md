# AGENTS.md — security/aaa-freeradius

Inherits `../../AGENTS.md`; these rules add to it.

## Purpose and layout

Design and a one-host, read-only preflight for AAA (LDAP/RADIUS). The lab guest
`aaa-ldap-radius` runs in VirtualBox on the operator's Mac, not on Proxmox.

- `ansible/playbooks/00-preflight.yml` — read-only; `docs/aaa-deployment.md`.

## Commands

```text
make check        # yamllint + syntax check, offline
```

## Component rules

- Only read-only preflight exists. Authentication policy, guest access, ARM VM
  lifecycle and a publication audit are outstanding; each is a new gated stage
  with an `allow_*` flag, a confirmation string and a test.
- PiVPN (192.168.0.60) has no FreeRADIUS; never install or restart services
  there without approval. It is the estate's largest exposure.
- Never discard the VirtualBox guest's saved state or delete its disk.

## Definition of done

`make check` passes here and `make COMPONENT=tests check` passes at the root;
staged gitleaks passes; `MEMORY.md` records any state change with its evidence.
