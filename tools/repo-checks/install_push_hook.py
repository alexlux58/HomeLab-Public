#!/usr/bin/env python3
"""Install the same fail-closed D6 guard in the private and generated checkouts."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HOOK = """#!/bin/sh
set -eu
root=$(git rev-parse --show-toplevel)
guard="$root/tools/repo-checks/pre_push.py"
if [ "${root##*/}" = public ]; then
    guard="$root/../tools/repo-checks/pre_push.py"
fi
test -f "$guard" || { echo 'Push blocked: private guard missing' >&2; exit 1; }
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) exec python "$guard" --hook "$@" ;;
    *) exec python3 "$guard" --hook "$@" ;;
esac
"""


def main():
    for checkout in (ROOT, ROOT / "public"):
        if not (checkout / ".git").exists():
            continue
        hooks = subprocess.check_output(
            ["git", "rev-parse", "--git-path", "hooks"], cwd=checkout, text=True
        ).strip()
        target = Path(hooks)
        if not target.is_absolute():
            target = checkout / target
        target.mkdir(parents=True, exist_ok=True)
        hook = target / "pre-push"
        if hook.exists() and hook.read_text() != HOOK:
            backup = target / "pre-push.before-d6"
            if backup.exists():
                raise RuntimeError("Existing hook and backup need review")
            hook.rename(backup)
        hook.write_text(HOOK, encoding="utf-8", newline="\n")
        hook.chmod(0o755)
        print(f"Installed D6 history guard: {checkout.name}")


if __name__ == "__main__":
    main()
