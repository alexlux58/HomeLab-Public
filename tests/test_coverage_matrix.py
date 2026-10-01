"""Phase 3 acceptance: every coverage row is declared, backup-restored, or
manual with a runbook step, and nothing in the lab is left out."""

import re

import pytest
import yaml

STATUSES = {"declared", "backup-restored", "manual"}
BACKUP_FIELDS = ("what", "source", "destination", "schedule", "restore", "verify", "status")


@pytest.fixture(scope="module")
def coverage(root):
    return yaml.safe_load((root / "docs/reference/coverage-matrix.yml").read_text(encoding="utf-8"))["rows"]


@pytest.fixture(scope="module")
def backups(root):
    items = yaml.safe_load((root / "docs/reference/backup-matrix.yml").read_text(encoding="utf-8"))["items"]
    return {item["id"]: item for item in items}


@pytest.fixture(scope="module")
def ladder_steps(root):
    rungs = yaml.safe_load((root / "docs/runbooks/rebuild-ladder.yml").read_text(encoding="utf-8"))["rungs"]
    return {step["id"] for rung in rungs for step in rung["steps"]}


@pytest.fixture(scope="module")
def lab(root):
    return yaml.safe_load((root / "inventory/lab.yml").read_text(encoding="utf-8"))


def test_zero_undocumented_rows(root, coverage):
    assert "UNDOCUMENTED" not in (root / "docs/reference/coverage-matrix.yml").read_text(encoding="utf-8")
    ids = [row["id"] for row in coverage]
    assert len(ids) == len(set(ids))
    for row in coverage:
        assert row["status"] in STATUSES, row["id"]
        assert row.get("owner") and "," not in row["owner"].split("(")[0], f"{row['id']}: one owner"
        assert re.fullmatch(r"L[0-8]", row["rung"]), row["id"]


def test_declared_rows_point_at_real_code(root, coverage):
    for row in coverage:
        if row["status"] == "declared":
            assert row.get("evidence"), row["id"]
            for path in row["evidence"]:
                assert (root / path).exists(), f"{row['id']}: {path} missing"


def test_manual_rows_have_a_runbook_step(coverage, ladder_steps):
    for row in coverage:
        if row["status"] == "manual":
            assert row.get("runbook_step") in ladder_steps, f"{row['id']}: no ladder step"


def test_backup_rows_point_at_a_complete_matching_backup_item(coverage, backups):
    for row in coverage:
        if row["status"] == "backup-restored":
            item = backups.get(row.get("backup"))
            assert item, f"{row['id']}: unknown backup item"
            assert item["status"] == "backup-restored", f"{row['id']}: backup item is {item['status']}"
        if row.get("backup"):
            assert row["backup"] in backups, row["id"]


def test_every_backup_item_is_complete(backups):
    for item_id, item in backups.items():
        for field in BACKUP_FIELDS:
            assert item.get(field), f"{item_id} lacks {field}"
        assert item["status"] in STATUSES
        text = " ".join(str(v) for v in item.values()).lower()
        for banned in ("prune", "rm -", "delete the"):
            assert banned not in text, f"{item_id}: {banned}"


def test_every_node_and_guest_is_covered(coverage, lab):
    nodes = {row["node"] for row in coverage if row.get("node")}
    guests = {row["guest"] for row in coverage if row.get("guest")}
    assert set(lab["nodes"]) == nodes
    assert set(lab["guests"]) == guests


def test_every_backup_item_is_referenced(coverage, backups):
    referenced = {row.get("backup") for row in coverage}
    assert set(backups) <= referenced, set(backups) - referenced


def test_operator_inputs_cover_every_sensitive_variable_and_secret_path(root):
    table = (root / "docs/reference/operator-inputs.md").read_text(encoding="utf-8")
    for tf in root.rglob("*.tf"):
        if {".terraform", "public"} & set(tf.parts):
            continue
        for name in re.findall(r'variable "([a-z_]+)"\s*\{[^}]*?sensitive\s*=\s*true', tf.read_text(), re.S):
            assert f"TF_VAR_{name}" in table, (
                f"{tf.relative_to(root)}: TF_VAR_{name} missing from operator-inputs.md"
            )
    for prefix in ("/etc/homelab/secret-store/", "/etc/observability/secret-store/", "/etc/media/secrets/"):
        assert prefix.rstrip("/") in table, prefix
