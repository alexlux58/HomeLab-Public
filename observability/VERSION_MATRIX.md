# Pinned component versions

Reviewed 2026-08-23 against upstream project releases. Tags are immutable deployment
inputs; upgrades are a reviewed stage, never an unattended `latest` pull.

| component | image | version |
|---|---|---|
| Prometheus | `prom/prometheus` | `v3.12.0` |
| Grafana OSS | `grafana/grafana` | `13.1.0` |
| Loki | `grafana/loki` | `3.7.4` |
| Grafana Alloy | `grafana/alloy` | `v1.18.0` |
| Alertmanager | `prom/alertmanager` | `v0.32.1` |
| Node Exporter | `prom/node-exporter` | `v1.12.1` |
| Blackbox Exporter | `prom/blackbox-exporter` | `v0.28.0` |
| SNMP Exporter | `prom/snmp-exporter` | `v0.30.1` |
| cAdvisor | `ghcr.io/google/cadvisor` | `v0.60.5` |
| Prometheus PVE Exporter | `prompve/prometheus-pve-exporter` | `3.9.0` |

Before promotion, `scripts/verify-images.sh` pulls every image and records its
resolved repository digest in `artifacts/image-digests.txt`.
