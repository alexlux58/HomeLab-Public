# ADR-0006: media metrics are pushed, not scraped

Status: accepted, Phase 3 (2026-09-29).

## Context

`media-vm` sits behind VirtualBox NAT on workstation, whose NAT forwards are
loopback-only, and workstation's firewall must not be changed without approval.
VM 310 therefore cannot scrape exporters in the guest. workstation also sleeps
after five hours on AC, so the guest is expected to be down often.

## Decision

An Alloy agent in the guest scrapes node_exporter and exportarr (Radarr,
Prowlarr) locally and `remote_write`s to Prometheus on VM 310. Outbound NAT
needs no inbound rule anywhere.

- Prometheus gains `--web.enable-remote-write-receiver`. That is a change to the
  live observability stack, deployed only through its gated deploy stage.
- Series carry `host="media-vm"`. Alerts treat absence as expected
  (workstation sleeps); only a scrape that is up but failing alerts.
- Plex (native Windows) is not exported in this phase; its health is the Plex
  script's `check` mode run by the operator.

## Consequences

The receiver endpoint accepts writes from the LAN (VM 310's UFW already limits
it to the LAN). Media apps get **no Homepage cards, Uptime Kuma monitors or NPM
routes** yet: VM 300 cannot reach loopback-only services, and Homepage policy
forbids a card without a working health check. Exposing them needs a workstation
NAT/firewall change, which is an operator decision recorded in the coverage
matrix.
