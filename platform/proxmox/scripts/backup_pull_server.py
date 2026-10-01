#!/usr/bin/env python3
"""Forced SSH command: list/hash or stream finalized vzdump archives, read only."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
from pathlib import Path

DUMP = Path("/mnt/pve/synology-backup/dump")
NAME = re.compile(
    r"vzdump-(?:qemu-[0-9]{3,5}-[0-9]{4}_[0-9]{2}_[0-9]{2}-[0-9]{2}_[0-9]{2}_[0-9]{2}\.vma"
    r"|lxc-[0-9]{3,5}-[0-9]{4}_[0-9]{2}_[0-9]{2}-[0-9]{2}_[0-9]{2}_[0-9]{2}\.tar)\.(?:zst|gz|lzo)"
)


def signature(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def stream(directory_fd, name, output=None):
    """No-follow open relative to an already-open directory; never write a file."""
    if not NAME.fullmatch(name):
        raise ValueError("invalid archive filename")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        os.close(fd)
        raise ValueError("archive must be a regular file")
    with os.fdopen(fd, "rb") as source:
        digest = hashlib.sha256()
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
        if signature(before) != signature(os.fstat(source.fileno())):
            raise ValueError("archive changed while reading; retry later")
        return before.st_size, digest.hexdigest()


def serve(command, directory=DUMP, text_output=sys.stdout, binary_output=None):
    if command != "list" and not (command.startswith("get ") and NAME.fullmatch(command[4:])):
        raise ValueError("only list or get <archive> is supported")
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if command == "list":
            # Path.iterdir cannot list an already-open directory descriptor safely.
            for name in sorted(os.listdir(directory_fd)):  # noqa: PTH208
                if NAME.fullmatch(name):
                    size, digest = stream(directory_fd, name)
                    print(f"{name}\t{size}\t{digest}", file=text_output)
        else:
            stream(directory_fd, command[4:], binary_output or sys.stdout.buffer)
    finally:
        os.close(directory_fd)


def main():
    try:
        serve(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Backup pull refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
