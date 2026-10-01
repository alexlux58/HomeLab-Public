# Controlled upgrades

Never run a floating `latest` tag or unattended image updater.

1. Review upstream release notes and security advisories.
2. Change one component tag in `docker/compose.yaml` and `VERSION_MATRIX.md`.
3. Run offline lint/tests and `docker compose config`.
4. Run `scripts/verify-images.sh` on a Docker-capable staging host and record
   resolved digests outside Git artifacts.
5. Take and restore-drill an application-aware backup.
6. Pull the one new image, recreate only that service, validate health, data
   source access, dashboards, alerts, and resource use for 24 hours.
7. Roll back by restoring the previous exact tag. Do not delete the new image or
   backup during the observation window.

Upgrade Prometheus/Loki storage formats only after reading their explicit
upgrade paths. A Grafana database migration can be one-way; the pre-upgrade
SQLite-safe archive is mandatory.
