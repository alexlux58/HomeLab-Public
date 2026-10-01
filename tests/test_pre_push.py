"""D6 push enforcement includes arbitrary trailing flags and resolved URLs."""

import pytest

from conftest import load_module


@pytest.fixture
def policy(root):
    return load_module("pre_push", root / "tools/repo-checks/pre_push.py")


@pytest.mark.parametrize(
    "args",
    [
        ["git", "push", "origin", "main"],
        ["git", "-C", "public", "push", "origin", "main"],
        ["git", "push", "-u", "origin", "main", "snapshot/pre-restructure-20260929"],
    ],
)
def test_plain_push_allowed(policy, args):
    policy.check_argv(args)


@pytest.mark.parametrize(
    "tail",
    [
        ["--force"],
        ["--force-with-lease=main"],
        ["-f"],
        ["--delete", "old"],
        ["--mirror"],
        ["+main:main"],
        [":old"],
        ["--no-verify"],
        ["--repo=elsewhere"],
    ],
)
def test_unsafe_push_blocked_anywhere(policy, tail):
    with pytest.raises(ValueError):
        policy.check_argv(["git", "push", "origin", "main", *tail])


@pytest.mark.parametrize("remote", ["upstream", "arbitrary", "https://github.com/other/repo.git", ""])
def test_foreign_remote_blocked(policy, remote):
    with pytest.raises(ValueError):
        policy.check_argv(["git", "push", remote, "main"])


def test_destination_is_exact_for_each_checkout(policy):
    for public in (False, True):
        good = policy.URLS["public" if public else "private"]
        policy.check_destination("origin", good, good, public)
        for bad in (
            good + "/",
            "ssh://git" + "@" + "github.com/other/repo",
            policy.URLS["private" if public else "public"],
        ):
            with pytest.raises(ValueError):
                policy.check_destination("origin", bad, bad, public)


def test_all_hook_updates_checked_for_deletion(policy):
    good = f"refs/heads/main {'1' * 40} refs/heads/main {policy.ZERO}"
    assert policy.hook_updates([good]) == [(policy.ZERO, "1" * 40)]
    deletion = f"(delete) {policy.ZERO} refs/heads/old {'2' * 40}"
    with pytest.raises(ValueError, match="deletion"):
        policy.hook_updates([good, deletion])
    for bad in ([], ["incomplete"]):
        with pytest.raises(ValueError):
            policy.hook_updates(bad)


def test_windows_parent_inspection_uses_native_argv(policy, monkeypatch):
    command = '"C:\\Program Files\\Git\\cmd\\git.exe" push origin main'
    import json

    monkeypatch.setattr(policy.subprocess, "check_output", lambda *a, **k: json.dumps(command))
    monkeypatch.setattr(policy, "windows_argv", lambda value: [value])
    assert policy.windows_invoking_git() == [command]
