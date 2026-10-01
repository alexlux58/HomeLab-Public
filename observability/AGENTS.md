# AGENTS.md — observability

Inherits `../AGENTS.md`; these rules add to it.

## Purpose and layout

The VM 310 monitoring stack (Prometheus, Grafana, Loki, Alloy, Alertmanager,
exporters) and its agents.

- `ansible.cfg`, `ansible/playbooks/` (`00-preflight` … `90-validate`),
  `ansible/roles/`.
- `config/` — Prometheus rules and file_sd targets, Grafana provisioning,
  Alertmanager; `docker/compose.yaml`; `scripts/` including `backup.sh`.
- Inventory: `../inventory/observability/`.

## Commands

```text
make setup        # venv + pinned collections
make check        # yamllint, ansible-lint, validate_repo.py, unittest, syntax
make help         # stages: preflight, bootstrap, deploy, validate, backup …
```

## Component rules

- Every container keeps a hard memory limit; Prometheus stays at 15 days and
  8 GiB, Loki at seven days; Docker logs rotate at 10 MiB x 3.
- Before adding an alert, prove its input series returns data. Never delete
  `ObservabilityBackupMetricMissing` or `NodeTextfileCollectorFailing`.
- Never add `192.168.0.1:53` to `config/prometheus/file_sd/dns.yml`.
- Prometheus keeps `--web.enable-admin-api`; backups depend on it.
- Dashboard updates are gated by `allow_observability_dashboard_update` and
  must reload Prometheus without restarting containers.
- Secrets stay root-owned mode-0600 files under `/etc/observability/secret-store`.

## Definition of done

`make check` passes here and `make COMPONENT=tests check` passes at the root;
staged gitleaks passes; `MEMORY.md` records any state change with its evidence.
