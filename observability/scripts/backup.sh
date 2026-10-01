#!/usr/bin/env bash
set -euo pipefail

umask 077

readonly stack_root="/opt/observability"
readonly data_root="/srv/observability"
readonly backup_root="${data_root}/backups"
readonly metric_dir="/var/lib/node_exporter/textfile"
readonly compose=(docker compose --project-directory "${stack_root}/docker")

# Prometheus binds the LAN address, not loopback (see compose.yaml:
# ${OBSERVABILITY_IP}:9090:9090). Reading the address from the same .env that
# Compose uses keeps the two definitions from drifting. A hardcoded
# http://127.0.0.1:9090 here silently failed every nightly run with curl exit 7
# and produced no archive at all between 2026-08-24 and 2026-09-06.
observability_ip="$(sed -n 's/^OBSERVABILITY_IP=//p' "${stack_root}/docker/.env" 2>/dev/null | tail -1)"
readonly prometheus_url="http://${observability_ip:-192.168.0.31}:9090"

exec 9>/run/lock/homelab-observability-backup.lock
flock -n 9 || {
  echo "another observability backup is already running" >&2
  exit 20
}

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
stage="${backup_root}/.staging-${timestamp}"
archive="${backup_root}/homelab-observability-${timestamp}.tar.zst"
snapshot_path=""

cleanup_temporary_data() {
  if [[ -n "${snapshot_path}" && "${snapshot_path}" == "${data_root}/prometheus/snapshots/"* && -d "${snapshot_path}" ]]; then
    find "${snapshot_path}" -depth -delete
  fi
  if [[ "${stage}" == "${backup_root}/.staging-"* && -d "${stage}" ]]; then
    find "${stage}" -depth -delete
  fi
}
trap cleanup_temporary_data EXIT

mkdir -p "${backup_root}" "${stage}" "${metric_dir}"

snapshot_json="$(curl --fail --silent --show-error --request POST \
  "${prometheus_url}/api/v1/admin/tsdb/snapshot?skip_head=false")"
snapshot_name="$(jq -er '.data.name' <<<"${snapshot_json}")"
snapshot_path="${data_root}/prometheus/snapshots/${snapshot_name}"
test -d "${snapshot_path}"
cp -a --reflink=auto "${snapshot_path}" "${stage}/prometheus-snapshot"

sqlite3 "${data_root}/grafana/grafana.db" ".timeout 30000" ".backup '${stage}/grafana.db'"
test "$(sqlite3 "${stage}/grafana.db" 'PRAGMA integrity_check;')" = "ok"

cp -a "${stack_root}/config" "${stage}/config"
cp -a "${stack_root}/docker/compose.yaml" "${stage}/compose.yaml"
cp -a "${stack_root}/docker/.env" "${stage}/runtime.env"
"${compose[@]}" images --format json >"${stage}/images.json"
"${compose[@]}" ps --format json >"${stage}/containers.json"

cat >"${stage}/RECOVERY-NOTE.txt" <<'EOF'
Secret files are intentionally excluded. Restore /etc/observability/secret-store from
the operator's separate encrypted credential backup before starting Compose.
Prometheus and Loki history is optional; the stack can be rebuilt without it.
EOF

(
  cd "${stage}"
  mapfile -d '' manifest_files < <(find . -type f -print0 | sort -z)
  sha256sum "${manifest_files[@]}" >MANIFEST.sha256
)

tar --zstd -C "${stage}" -cpf "${archive}.partial" .
test -s "${archive}.partial"
mv "${archive}.partial" "${archive}"
sha256sum "${archive}" >"${archive}.sha256"

# The script-wide `umask 077` above is correct for the archive, which carries
# configuration, but it also made this metric file 0600 root:root. The
# node_exporter container runs as `nobody` and could not read it, so the
# textfile collector reported node_textfile_scrape_error=1 and
# homelab_observability_backup_last_success_timestamp_seconds NEVER EXISTED in
# Prometheus. A freshness alert written against it would have been vacuous: it
# would evaluate against no series, never fire, and look exactly like health.
# Discovered 2026-09-19. The file contains a single Unix timestamp and no
# secret, so 0644 is appropriate. Do not "fix" this by relaxing the umask.
metric_tmp="${metric_dir}/homelab_observability_backup.prom.tmp"
printf 'homelab_observability_backup_last_success_timestamp_seconds %s\n' "$(date +%s)" >"${metric_tmp}"
chmod 0644 "${metric_tmp}"
mv "${metric_tmp}" "${metric_dir}/homelab_observability_backup.prom"

logger --tag homelab-observability-backup "completed ${archive}"
echo "${archive}"
