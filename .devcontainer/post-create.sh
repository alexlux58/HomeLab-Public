#!/usr/bin/env bash
# One-time setup inside the devcontainer. Offline apart from package downloads
# for each component's pinned venv and Galaxy collections. Contacts no host.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Ansible refuses ansible.cfg in a world-writable directory (for example /mnt/c).
if [ -n "$(find . -maxdepth 0 -perm -0002)" ]; then
  echo "WARNING: $PWD is world-writable; Ansible will ignore ansible.cfg. Use the WSL filesystem." >&2
fi

git config core.symlinks true
pre-commit install --hook-type pre-commit --hook-type pre-push

for component in platform/proxmox platform/nas observability security/secrets-openbao \
                 security/aaa-freeradius services/homelab-services services/netbox tests; do
  echo "== make setup: $component"
  make -C "$component" setup PYTHON=python3
done

echo "Ready. Try: make COMPONENT=tests check"
