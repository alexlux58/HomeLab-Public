#!/usr/bin/env python3
"""Claude Code PreToolUse guard for the Home Lab monorepo.

Blocks live-changing commands and reads of secret-bearing paths, as listed in
AGENTS.md ("Forbidden commands" and "Secrets and boundaries"). It is a
guardrail, not a sandbox: it parses shell commands conservatively and blocks
when a forbidden program is the command being run, including inside `ssh`,
`sudo`, `bash -c`, `xargs` and `find -exec` wrappers.

Input: the hook JSON on stdin. Output: exit 0 to allow (no decision), exit 2
with a reason on stderr to block. Any internal error blocks (fail closed).
"""

from __future__ import annotations

import json
import re
import shlex
import sys

# ---------------------------------------------------------------------------
# Secret-bearing paths. Listing a filename is fine; reading contents is not.
# ---------------------------------------------------------------------------
PROTECTED_PATH = re.compile(
    r"""(?ix)
    (?:\.tfstate(?:\.backup)?$|\.tfstate\.)                # OpenTofu/Terraform state
    | (?:^|[/\\])[^/\\]*\.env$                              # real .env files
    | (?:^|[/\\])\.env\.(?!example$)[^/\\]+$                # .env.<name>, not .env.example
    | \.tfvars(?:\.json)?$                                  # real tfvars
    | \.(?:pem|key|p12|pfx)$                                # private keys and bundles
    | (?:^|[/\\])id_(?:rsa|ed25519|ecdsa|dsa)$              # SSH private keys
    | _ed25519$                                             # named private keys
    | (?:^|[/\\~])\.ssh(?:[/\\]|$)                          # ~/.ssh/**
    | (?:^|[/\\])artifacts(?:[/\\]|$)                       # machine captures
    | (?:^|[/\\])host-configs(?:[/\\]|$)                    # host configuration captures
    | (?:^|[/\\])Preferences\.xml$                          # Plex token store
    | (?:^|[/\\])config\.xml$                               # *arr API keys
    | (?:^|[/\\])\.local-credentials(?:[/\\]|$)                       # operator secret store
    | (?:^|[/\\])secrets(?:[/\\]|$)                         # runtime secret directories
    | (?:^|[/\\])\.runtime[/\\]radarr(?:[/\\]|$)            # quarantined legacy state
    | (?:^|[/\\])auth\.json$                                # agent credentials
    """
)

# Commands that read, copy or transmit file contents.
READ_VERBS = {
    "cat",
    "tac",
    "less",
    "more",
    "head",
    "tail",
    "bat",
    "nl",
    "strings",
    "xxd",
    "od",
    "hexdump",
    "base64",
    "sed",
    "awk",
    "gawk",
    "grep",
    "egrep",
    "fgrep",
    "rg",
    "ag",
    "jq",
    "yq",
    "cut",
    "sort",
    "uniq",
    "diff",
    "cmp",
    "cp",
    "mv",
    "scp",
    "rsync",
    "tar",
    "zip",
    "7z",
    "curl",
    "wget",
    "source",
    ".",
    "type",
    "get-content",
    "gc",
    "select-string",
    "sls",
    "copy-item",
    "cpi",
    "vim",
    "vi",
    "nano",
    "code",
    "openssl",
    "ssh-keygen",
    "gpg",
    "age",
    "sops",
    "python",
    "python3",
    "py",
    "node",
    "perl",
    "ruby",
    "pwsh",
    "powershell",
}

# Programs whose first positional argument is a pattern or script, not a file.
PATTERN_FIRST = {
    "grep",
    "egrep",
    "fgrep",
    "rg",
    "ag",
    "sed",
    "awk",
    "gawk",
    "jq",
    "yq",
    "select-string",
    "sls",
}

WRAPPERS = {"sudo", "doas", "env", "nohup", "time", "command", "exec", "nice", "stdbuf"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "pwsh", "powershell", "cmd", "cmd.exe"}
SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")", "\n"}

# Options that consume the next word, so it is not mistaken for the host or command.
SSH_VALUE_OPTIONS = set("-b -c -D -E -e -F -I -i -J -L -l -m -O -o -p -Q -R -S -W -w -B".split())
XARGS_VALUE_OPTIONS = {"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a"}


def _ssh_remote_command(args: list[str]) -> list[str]:
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in SSH_VALUE_OPTIONS else 1
    return args[index + 1 :]  # skip the destination host


RM_RECURSIVE = re.compile(r"^-[a-zA-Z]*[rR]")
RM_FORCE = re.compile(r"^-[a-zA-Z]*f")


class Blocked(Exception):
    """Raised with the reason a tool call is refused."""


def _segments(command: str) -> list[list[str]]:
    # A newline ends a command just like `;` (shlex would treat it as a space).
    command = command.replace("\r\n", "\n").replace("\n", " ; ")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)
    segments, current = [], []
    for token in tokens:
        if token in SEPARATORS or set(token) <= set(";&|()"):
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _strip_prefixes(words: list[str]) -> list[str]:
    """Drop env assignments and harmless wrappers so words[0] is the program."""
    while words:
        head = words[0]
        base = head.rsplit("/", 1)[-1].lower()
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", head):
            words = words[1:]
        elif base in WRAPPERS:
            words = words[1:]
            while words and words[0].startswith("-"):
                words = words[1:]
        elif base == "timeout":
            words = words[1:]
            while words and (words[0].startswith("-") or re.match(r"^\d", words[0])):
                words = words[1:]
        else:
            break
    return words


def _check_program(words: list[str], depth: int) -> None:
    words = _strip_prefixes(words)
    if not words:
        return
    program = words[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    args = words[1:]
    lowered = [a.lower() for a in args]

    # Nested command strings: ssh host 'cmd', bash -c 'cmd', pwsh -Command 'cmd'.
    if program == "ssh":
        remote = _ssh_remote_command(args)
        if remote:
            check_command(" ".join(remote), depth + 1)
    if program in SHELLS:
        for flag in ("-c", "-lc", "-ic", "/c", "-command", "-c"):
            if flag in lowered:
                idx = lowered.index(flag)
                check_command(" ".join(args[idx + 1 :]), depth + 1)
    if program == "xargs":
        index = 0
        while index < len(args) and args[index].startswith("-"):
            index += 2 if args[index] in XARGS_VALUE_OPTIONS else 1
        _check_program(args[index:], depth + 1)
    if program == "find" and "-exec" in args:
        idx = args.index("-exec")
        _check_program([a for a in args[idx + 1 :] if a not in {";", "+", "{}"}], depth + 1)

    # Live-changing programs.
    if program in {"terraform", "tofu", "terraform.exe", "tofu.exe"}:
        verbs = [a for a in lowered if not a.startswith("-")]
        if any(v in {"apply", "destroy", "import"} for v in verbs[:2]):
            raise Blocked(f"{program} {verbs[0]} changes live infrastructure")
        if (
            verbs[:2]
            and verbs[0] == "state"
            and verbs[1:2]
            and verbs[1] in {"rm", "mv", "push", "replace-provider"}
        ):
            raise Blocked(f"{program} state {verbs[1]} rewrites state")
        if verbs[:1] == ["force-unlock"]:
            raise Blocked(f"{program} force-unlock breaks a state lock")
    if program == "git":
        # Skip global options and their values; inspect push options anywhere.
        index = 0
        while index < len(args) and args[index].startswith("-"):
            if args[index] in {"-C", "-c", "--git-dir", "--work-tree"}:
                if args[index] == "-c":
                    raise Blocked("git -c may override the approved push destination or hooks")
                index += 2
            else:
                index += 1
        if args[index : index + 1] == ["push"]:
            push = args[index + 1 :]
            options = [a for a in push if a.startswith("-")]
            safe = {"-u", "--set-upstream", "--dry-run", "--porcelain", "--verbose", "-v"}
            if any(a not in safe for a in options):
                raise Blocked("push options may not force, delete, mirror or override the destination")
            refs = [a for a in push if not a.startswith("-")]
            if not refs or refs[0] != "origin":
                raise Blocked("agents may push only to origin of this repo or public/")
            if any(a.startswith(("+", ":")) for a in refs[1:]):
                raise Blocked("forced refspecs and remote ref deletion are forbidden")
    if program == "bao" and "operator" in lowered:
        raise Blocked("bao operator is the attended OpenBao ceremony's")
    if program == "pvecm":
        raise Blocked("pvecm changes cluster membership or quorum")
    if program in {"qm", "pct"} and "destroy" in lowered:
        raise Blocked(f"{program} destroy deletes a guest")
    if program == "rm":
        flags = [a for a in args if a.startswith("-")]
        recursive = any(RM_RECURSIVE.match(f) for f in flags) or "--recursive" in flags
        force = any(RM_FORCE.match(f) for f in flags) or "--force" in flags
        if recursive and force:
            raise Blocked("rm -rf is forbidden in this repository")
    if program in {"remove-item", "ri", "rd", "rmdir", "del", "erase"}:
        if any(a in lowered for a in ("-recurse", "-r", "/s")) and any(
            a in lowered for a in ("-force", "/q")
        ):
            raise Blocked("recursive forced delete is forbidden in this repository")

    # Reads of secret-bearing paths.
    if program in READ_VERBS:
        positional = [a for a in args if not a.startswith("-")]
        if program in PATTERN_FIRST and not {"-e", "-f", "--regexp", "--file"} & set(args):
            positional = positional[1:]  # the first word is a pattern or script, not a path
        for arg in positional:
            if PROTECTED_PATH.search(arg.strip("'\"")):
                raise Blocked(f"{program} would read the protected path {arg!r}")


HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
PIPE_TO_SHELL = re.compile(r"\|\s*(?:sudo\s+)?(?:bash|sh|zsh|dash|ksh|ssh)\b")


def _split_heredocs(command: str) -> tuple[str, list[tuple[bool, str]]]:
    """Remove here-document bodies, which are data such as commit messages.

    Returns the command without bodies, and (executed, body) pairs, where
    executed is true when the body feeds a shell or ssh and must be checked.
    """
    lines = command.split("\n")
    kept: list[str] = []
    bodies: list[tuple[bool, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        index += 1
        for match in HEREDOC.finditer(line):
            strip_tabs, terminator = match.group(1) == "-", match.group(3)
            before, after = line[: match.start()], line[match.end() :]
            try:
                segments = _segments(before)
            except ValueError:
                segments = [before.split()]
            consumer = _strip_prefixes(segments[-1]) if segments else []
            program = consumer[0].rsplit("/", 1)[-1].lower() if consumer else ""
            executed = program in SHELLS or program == "ssh" or bool(PIPE_TO_SHELL.search(after))
            body = []
            while index < len(lines):
                candidate = lines[index].lstrip("\t") if strip_tabs else lines[index]
                index += 1
                if candidate == terminator:
                    break
                body.append(lines[index - 1])
            bodies.append((executed, "\n".join(body)))
    return "\n".join(kept), bodies


def check_command(command: str, depth: int = 0) -> None:
    if depth > 4:
        raise Blocked("command nesting too deep to verify")
    command, bodies = _split_heredocs(command)
    for executed, body in bodies:
        if executed:
            check_command(body, depth + 1)
    try:
        segments = _segments(command)
    except ValueError as exc:  # unbalanced quotes: cannot verify, so block
        raise Blocked(f"could not parse the command safely ({exc})") from exc
    for index, words in enumerate(segments):
        _check_program(words, depth)
    # Input redirection from a protected path: `< .env`.
    for match in re.finditer(r"<\s*([^\s;&|<>]+)", command):
        if PROTECTED_PATH.search(match.group(1).strip("'\"")):
            raise Blocked(f"redirection reads the protected path {match.group(1)!r}")


def check_path(path: str | None, action: str) -> None:
    if path and PROTECTED_PATH.search(path.strip()):
        raise Blocked(f"{action} of the protected path {path!r} is not allowed")


def decide(event: dict) -> None:
    tool = event.get("tool_name", "")
    data = event.get("tool_input") or {}
    if tool in {"Bash", "PowerShell"}:
        check_command(str(data.get("command", "")))
    elif tool in {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit"}:
        check_path(data.get("file_path") or data.get("notebook_path"), tool)
    elif tool == "Grep":
        # Grep reads contents. Glob only lists names, which is allowed.
        for path in [data.get("path"), *list(data.get("paths") or [])]:
            check_path(path, tool)
        if data.get("glob"):
            check_path(str(data.get("glob")), tool)


def main() -> int:
    try:
        event = json.load(sys.stdin)
        decide(event)
    except Blocked as reason:
        print(
            f"Blocked by the Home Lab guard: {reason}. See AGENTS.md; ask the "
            "operator instead of retrying another way.",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:  # fail closed
        print(f"Home Lab guard could not evaluate the call ({exc!r}); blocking.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
