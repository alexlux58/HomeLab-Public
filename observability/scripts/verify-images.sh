#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly project_root
readonly compose_file="${project_root}/docker/compose.yaml"
readonly output="${project_root}/artifacts/image-digests.txt"

mapfile -t images < <(docker compose --file "${compose_file}" config --images | sort -u)
if [[ ${#images[@]} -eq 0 ]]; then
  echo "no images resolved from Compose" >&2
  exit 2
fi

: >"${output}.tmp"
for image in "${images[@]}"; do
  if [[ "${image}" == *:latest || "${image}" != *:* ]]; then
    echo "refusing unpinned image ${image}" >&2
    exit 3
  fi
  docker pull "${image}"
  digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "${image}")"
  printf '%s\t%s\n' "${image}" "${digest}" >>"${output}.tmp"
done
mv "${output}.tmp" "${output}"
echo "wrote ${output}"
