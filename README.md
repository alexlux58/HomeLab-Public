# HomeLab

Sanitised automation and documentation from a three-node Proxmox VE home lab:
the platform, NAS storage, VM services, a media stack, observability, and a
secrets/recovery plane.

Everything here is published deliberately. This repository contains only a
generated, sanitised copy of a private monorepo; the private source is never
reachable from here.

**Start with the technical walkthrough:**
[`docs/walkthrough/homelab-technical-walkthrough.pdf`](docs/walkthrough/homelab-technical-walkthrough.pdf)
(its source is the Markdown file next to it). It is written for an engineer
who has never seen the lab, and every file it mentions links into this
repository.

## What this is really about

The interesting part of this lab is not the service list. It is that the
automation is **gated**: it operates on live machines holding irreplaceable
data, so "make the tests pass" is not the goal — not destroying anything is.

That principle is enforced mechanically rather than by discipline:

- every playbook runs `serial: 1` with `any_errors_fatal: true`;
- there is no aggregate `deploy-all` target (in Make or CI), and a test fails
  the build if anyone adds one;
- every destructive task carries both a `never` and a `destructive` tag, so it
  additionally requires `--tags all,destructive`;
- every `allow_*` flag defaults to `false` and is paired with an exact
  confirmation string, both checked by a real assertion before any role runs;
- no backup archive is ever deleted or pruned — NFS storage is registered with
  `keep-all=1`;
- OpenTofu roots adopt live guests import-first and keep `prevent_destroy`;
  there is no apply or destroy target;
- coding agents work under a guard hook and execution-policy rules that block
  live commands and secret reads.

The `tests/` directories are what enforce those rules.

## Layout

The layout mirrors the private monorepo, so paths in the walkthrough match.

| path | contents |
| --- | --- |
| [`inventory/`](inventory/) | `lab.yml`, the single source of truth, plus per-component Ansible inventories |
| [`platform/proxmox/`](platform/proxmox/) | cluster migration stages, guest OpenTofu roots, rebuild tooling |
| [`platform/nas/`](platform/nas/) | NFS backup target checks |
| [`services/`](services/) | VM services (reverse proxy, dashboards, monitoring), NetBox, the media stack |
| [`observability/`](observability/) | Prometheus / Grafana / Loki / Alertmanager stack, dashboards, alerts, backups |
| [`security/`](security/) | three-voter OpenBao recovery plane; AAA discovery |
| [`tests/`](tests/) | cross-component safety contracts |
| [`tools/`](tools/) | inventory contract, forbidden-construct scanner, rebuild planner, docs build |
| [`docs/`](docs/) | decisions (ADRs), runbooks, reference tables, the walkthrough and its diagrams |
| [`.agents/`](.agents/), [`.claude/`](.claude/), [`.codex/`](.codex/) | agent skills, guard hook and execution-policy rules |

## Reading these files

They are **sanitised copies, not a runnable checkout.** Real addresses,
hostnames, MAC addresses, key fingerprints, domains, mailboxes, usernames and
hardware serials are replaced with stable placeholders by a script that is kept
out of this repository — its substitution table is a map of the real values.

| placeholder | meaning |
| --- | --- |
| `192.168.0.0/24` | the lab network |
| `192.168.0.11` / `.12` / `.13` | the three Proxmox nodes `pve1` / `pve2` / `pve3` |
| `192.168.0.20` | the NAS (`nas1`) — DNS and NFS backup target |
| `192.168.0.30` / `.31` / `.34` | services VM / observability VM / CI runner VM (planned) |
| `192.168.0.40`–`.43` | secrets cluster VIP and voters |
| `192.168.0.50` | IPAM/DCIM VM |
| `192.168.0.70` | the Windows workstation (`workstation`) |
| `198.51.100.N` | any other LAN address (test values, one-off devices) |
| `10.0.2.x` | VirtualBox's built-in NAT network (a fixed default, not a lab address) |
| `lab.example.com` | the private DNS zone |
| `labadmin` / `labuser` | operator accounts |
| `52:54:00:00:00:00` | any MAC address |
| `SHA256:EXAMPLE_FINGERPRINT_REDACTED` | any SSH host key fingerprint |
| `SERIAL-REDACTED-n` | a disk serial number |

Because substitution is global and consistent, cross-references still line up:
the node called `pve2` in a playbook is the same `pve2` in the runbook. Tests
that compare real identities (for example unique MAC addresses) will not pass
on the placeholders; that is expected.

## Deliberately not published

- **Captured host state:** `artifacts/`, `host-configs/` and the test fixtures
  built from them.
- **The LAN device inventory**, which enumerates personal devices.
- **Secrets of any kind.** Authentication is public-key only; on-host secret
  files are operator-installed, root-owned and mode `0600`. Secret directory
  *paths* are masked too.
- **Working state:** the volatile memory file, roadmap, phase evidence, legacy
  documents and the workstation inventory. The walkthrough marks a reference
  to any of these as "not published".
- **CI workflows**, because GitHub would run them against this non-runnable
  copy; the walkthrough describes them.
- **The full AAA deployment plan**, until its host-specific details are
  reviewed ([stub](security/aaa-freeradius/docs/aaa-deployment.md)).
- **A component still being written** (a local music library).
- **The sanitiser, the denylist and the publishing script.**

Every file is scanned before each commit against a literal denylist of real
values plus structural patterns: private IPv4 addresses (complete and partial),
MAC addresses, SSH fingerprints, private keys, e-mail addresses, cloud and API
tokens, Plex tokens and machine identifiers, *arr API keys and dynamic-DNS
hostnames. Text is extracted from PDF and SVG files first, so values inside
compressed PDF streams or split across SVG text elements are scanned too. The
pre-commit hook fails closed: if it cannot reach the scanner, the commit is
refused.
