"""The shared forbidden-construct checker (used by pre-commit) holds across the
whole tree, and its baseline can only shrink."""

import forbidden_constructs as fc
import pytest


def test_tree_has_no_forbidden_construct_beyond_the_baseline(tracked):
    assert fc.evaluate(tracked) == []


def test_baseline_has_no_stale_entries(tracked):
    assert fc.stale_baseline(tracked) == []


@pytest.mark.parametrize(
    ("sample", "construct"),
    [
        ("- name: x\n  ignore_errors: true\n", "ignore_errors on a task"),
        ("run: rm -rf /srv/data\n", "rm -rf"),
        ("ssh_args = -o StrictHostKeyChecking=no\n", "StrictHostKeyChecking disabled"),
        ("host_key_checking = False\n", "host_key_checking disabled"),
        ("cmd: pvecm expected 1\n", "pvecm expected"),
        ("cmd: pvesm set nas --prune-backups keep-last=3\n", "backup pruning"),
        ("cmd: bao operator init -key-shares=5\n", "automated OpenBao ceremony"),
        ("rebuild-all:\n\techo\n", "aggregate target"),
        ("\tterraform apply -auto-approve\n", "unsafe auto-approve"),
    ],
)
def test_checker_catches_each_construct(sample, construct):
    found = {name for _, name, _ in fc.scan_text("roles/x/tasks/main.yml", sample)}
    assert construct in found


def test_warnings_that_forbid_a_construct_are_not_findings():
    sample = "    fail_msg: Do NOT work around this with `pvecm expected 1`.\n# never rm -rf here\n"
    assert fc.scan_text("roles/x/tasks/main.yml", sample) == []


def test_prose_files_are_out_of_scope():
    assert not fc.in_scope("AGENTS.md")
    assert fc.in_scope("platform/proxmox/Makefile")
    assert fc.in_scope("services/netbox/ansible/playbooks/40-deploy.yml")
