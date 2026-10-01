#!/usr/bin/env bash
# Run guard.py with the first Python that actually executes. On workstation
# `python3` is the Microsoft Store stub, so resolving a name is not enough.
# No working interpreter means the guard cannot decide: block (exit 2).
set -u
hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
input="$(cat)"
for candidate in python3 python "py -3"; do
  # shellcheck disable=SC2086
  if $candidate -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    printf '%s' "$input" | $candidate "$hook_dir/guard.py"
    exit $?
  fi
done
echo "Home Lab guard: no working Python interpreter; blocking the call." >&2
exit 2
