#!/usr/bin/env bash
# Check formatting of the Terraform/OpenTofu roots that contain the given files.
# Prefers OpenTofu, falls back to Terraform. Never runs init, plan or apply.
set -euo pipefail

if command -v tofu >/dev/null 2>&1; then
  tool=tofu
elif command -v terraform >/dev/null 2>&1; then
  tool=terraform
else
  echo "Neither tofu nor terraform is installed; use the devcontainer." >&2
  exit 1
fi

status=0
for dir in $(for f in "$@"; do dirname "$f"; done | sort -u); do
  "$tool" fmt -check -diff "$dir" || status=1
done
exit "$status"
