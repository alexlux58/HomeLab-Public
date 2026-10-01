#!/usr/bin/env python3
"""D6: validate the destination, reject destructive pushes, scan pushed commits.

Called by pre-commit or the installed standalone pre-push hook. Git's hook
protocol does not expose --force or --mirror; inspect the invoking git argv
through /proc as well. Missing context fails closed. Never opens credentials.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import sys

URLS = {
    "private": "https://github.com/labadmin/HomeLab-Private.git",
    "public": "https://github.com/alexlux58/HomeLab-Public.git",
}
ZERO = "0" * 40
SAFE_OPTIONS = {"-u", "--set-upstream", "--dry-run", "--porcelain", "--verbose", "-v"}


def check_argv(argv: list[str]) -> None:
    """Accept only explicit origin with ordinary refspecs and harmless options."""
    if "push" not in argv:
        raise ValueError("missing invoking git push")
    prefix, args = argv[: argv.index("push")], argv[argv.index("push") + 1 :]
    if "-c" in prefix or any(a.startswith("--config-env") for a in prefix):
        raise ValueError("push configuration overrides are forbidden")
    if any(a.startswith("-") and a not in SAFE_OPTIONS for a in args):
        raise ValueError("force, delete, mirror and destination overrides are forbidden")
    refs = [a for a in args if not a.startswith("-")]
    if not refs or refs[0] != "origin":
        raise ValueError("push must name origin explicitly")
    if any(a.startswith(("+", ":")) for a in refs[1:]):
        raise ValueError("forced or deleting refspec")


def windows_argv(command: str) -> list[str]:
    """Use Windows' native parser, preserving quoted paths and arguments."""
    import ctypes

    count = ctypes.c_int()
    parse = ctypes.windll.shell32.CommandLineToArgvW
    parse.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    parse.restype = ctypes.POINTER(ctypes.c_wchar_p)
    release = ctypes.windll.kernel32.LocalFree
    release.argtypes = [ctypes.c_void_p]
    release.restype = ctypes.c_void_p
    result = parse(command, ctypes.byref(count))
    if not result:
        raise ValueError("cannot inspect invoking Windows git")
    try:
        return [result[i] for i in range(count.value)]
    finally:
        release(result)


def windows_invoking_git() -> list[str]:
    # Only the matched git command is returned; other process arguments are
    # never exposed. The native Git transport keeps authentication in gh/GCM.
    script = f"""
    $processId = {os.getppid()}
    for ($i = 0; $i -lt 16 -and $processId -gt 1; $i++) {{
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
        if (-not $process) {{ break }}
        if ($process.Name -eq 'git.exe' -and $process.CommandLine -match '\\bpush\\b') {{
            $process.CommandLine | ConvertTo-Json -Compress
            exit 0
        }}
        $processId = $process.ParentProcessId
    }}
    exit 1
    """
    command = json.loads(
        subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            text=True,
        )
    )
    return windows_argv(command)


def invoking_git() -> list[str]:
    if os.name == "nt":
        return windows_invoking_git()
    pid = os.getppid()
    for _ in range(16):
        proc = Path("/proc") / str(pid)
        argv = proc.joinpath("cmdline").read_bytes().decode().strip("\0").split("\0")
        if argv and Path(argv[0]).name in {"git", "git.exe"} and "push" in argv:
            return argv
        status = proc.joinpath("status").read_text()
        pid = int(next(line.split()[1] for line in status.splitlines() if line.startswith("PPid:")))
        if pid <= 1:
            break
    raise ValueError("cannot verify invoking git push; the installed hook is required")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def check_destination(name: str, url: str, origin: str, public: bool) -> None:
    expected = URLS["public" if public else "private"]
    if name != "origin" or url != expected or origin != expected:
        raise ValueError("only this checkout's approved origin URL may receive a push")


def hook_updates(lines: list[str]) -> list[tuple[str, str]]:
    """Fail closed for any deleted ref in a multi-ref Git hook invocation."""
    updates = []
    for line in lines:
        fields = line.split()
        if len(fields) != 4:
            raise ValueError("invalid pre-push protocol")
        _, after, _, before = fields
        if after == ZERO:
            raise ValueError("remote ref deletion is forbidden")
        updates.append((before, after))
    if not updates:
        raise ValueError("no pushed commits to verify")
    return updates


def pushed_revisions(revisions: list[str], updates: list[tuple[str, str]]) -> list[str]:
    """D6 scans newly transferred commits, excluding verified remote history."""
    remote = list(dict.fromkeys(before for before, _ in updates if before and before != ZERO))
    return revisions + (["--not", *remote] if remote else [])


def main() -> int:
    try:
        argv = invoking_git()
        check_argv(argv)
        root = Path(git("rev-parse", "--show-toplevel"))
        standalone = len(sys.argv) == 4 and sys.argv[1] == "--hook"
        check_destination(
            sys.argv[2] if standalone else os.environ.get("PRE_COMMIT_REMOTE_NAME", ""),
            sys.argv[3] if standalone else os.environ.get("PRE_COMMIT_REMOTE_URL", ""),
            git("remote", "get-url", "--push", "origin"),
            root.name == "public",
        )
        before = os.environ.get("PRE_COMMIT_FROM_REF", "")
        after = os.environ.get("PRE_COMMIT_TO_REF") or git(
            "rev-parse", os.environ.get("PRE_COMMIT_LOCAL_BRANCH", "HEAD")
        )
        if not after or after == ZERO:
            raise ValueError("remote ref deletion is forbidden")
        updates = hook_updates(sys.stdin.read().splitlines()) if standalone else [(before, after)]
        for previous, current in updates:
            if previous and previous != ZERO:
                result = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", previous, current], check=False
                )
                if result.returncode:
                    raise ValueError("only fast-forward pushes are allowed")
        # pre-commit's hook selects one update. Resolve every explicit source
        # ref in the invoking push so every newly pushed history is scanned.
        # Only Git's verified remote tips are excluded, after ancestry checks;
        # a new remote scans the complete source history.
        refs = [a for a in argv[argv.index("push") + 1 :] if not a.startswith("-")][1:]
        revisions = [git("rev-parse", f"{ref.split(':')[0]}^{{commit}}") for ref in refs] or [after]
        revision = " ".join(pushed_revisions(revisions, updates))
        return subprocess.run(
            ["gitleaks", "git", "--redact=100", "--no-banner", f"--log-opts={revision}"],
            check=False,
        ).returncode
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"Push blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
