#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: restore-drill.sh /srv/observability/backups/<archive>.tar.zst" >&2
  exit 2
fi

archive="$1"
backup_root="/srv/observability/backups"

if [[ "${archive}" != "${backup_root}/"*.tar.zst || ! -f "${archive}" ]]; then
  echo "archive must be an existing .tar.zst directly under ${backup_root}" >&2
  exit 3
fi

if [[ ! -f "${archive}.sha256" ]]; then
  echo "missing detached SHA-256 file" >&2
  exit 4
fi

(
  cd "$(dirname "${archive}")"
  sha256sum --check "$(basename "${archive}.sha256")"
)

work_dir="$(mktemp -d /var/tmp/observability-restore-drill.XXXXXX)"
cleanup() {
  if [[ "${work_dir}" == /var/tmp/observability-restore-drill.* && -d "${work_dir}" ]]; then
    find "${work_dir}" -depth -delete
  fi
}
trap cleanup EXIT

tar --zstd -C "${work_dir}" -xpf "${archive}"
(
  cd "${work_dir}"
  sha256sum --check MANIFEST.sha256
)

test "$(sqlite3 "${work_dir}/grafana.db" 'PRAGMA integrity_check;')" = "ok"
test -d "${work_dir}/prometheus-snapshot"
test -f "${work_dir}/compose.yaml"
test -d "${work_dir}/config"

echo "PASS: isolated validation completed without touching live data"

