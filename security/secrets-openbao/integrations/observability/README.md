# Observability integration

VM 310 remains the only central stack. Add three authenticated OpenBao metrics
targets, three Node Exporter targets, certificate probes, backup-age recording
rules, and the static-label audit stream through `homelab-observability`.

Prometheus gets a renewable short token from an Agent on VM 310. Never place it
in Prometheus YAML. Loki audit access is operator-only, and audit content fields
must never be labels.
