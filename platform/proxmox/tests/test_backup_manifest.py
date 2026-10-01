"""Verified archive count must equal protected guest count — per generation."""

from verify_vma_archives import REQUIRED_MANIFEST_FIELDS, adjudicate


def test_complete_manifest_passes(manifest, protected):
    report = adjudicate(manifest, protected, ["initial", "final"], None)
    assert report["verdict"] == "pass"
    assert report["counts"]["equal"] is True
    assert (
        report["counts"]["verified_archives"]
        == len(protected["pve1"]) * 2 + len(protected["pve2"]) * 2
    )


def test_failed_verification_fails_the_run(manifest_broken, protected):
    report = adjudicate(manifest_broken, protected, ["initial", "final"], None)
    assert report["verdict"] == "fail"
    assert any(f["issue"] == "verification_failed" for f in report["findings"])


def test_missing_archive_is_reported(manifest_broken, protected):
    report = adjudicate(manifest_broken, protected, ["initial", "final"], None)
    missing = [f for f in report["findings"] if f["issue"] == "no_verified_archive"]
    assert missing
    assert any("9100" in f["target"] for f in missing)


def test_incomplete_manifest_entry_is_rejected(manifest, protected):
    del manifest["archives"][0]["sha256"]
    report = adjudicate(manifest, protected, ["initial", "final"], None)
    assert report["verdict"] == "fail"
    assert any(f["issue"] == "manifest_incomplete" for f in report["findings"])


def test_all_required_manifest_fields_are_present_in_the_fixture(manifest):
    for entry in manifest["archives"]:
        for field in REQUIRED_MANIFEST_FIELDS:
            assert field in entry, f"fixture missing {field}"


def test_zero_byte_archive_is_rejected(manifest, protected):
    manifest["archives"][0]["archive_size_bytes"] = 0
    report = adjudicate(manifest, protected, ["initial", "final"], None)
    assert any(f["issue"] == "empty_archive" for f in report["findings"])


def test_final_generation_must_be_the_newest(manifest, protected):
    for entry in manifest["archives"]:
        if entry["generation"] == "initial":
            entry["timestamp"] = "2026-08-23T09:00:00Z"  # newer than the final backup
    report = adjudicate(manifest, protected, ["initial", "final"], None)
    assert any(f["issue"] == "final_backup_not_newest" for f in report["findings"])
    assert report["verdict"] == "fail"


def test_host_filter_narrows_the_expectation(manifest, protected):
    report = adjudicate(manifest, protected, ["final"], ["pve2"])
    assert report["counts"]["protected_guest_generations_expected"] == len(protected["pve2"])
    assert report["verdict"] == "pass"


def test_original_running_state_is_carried_through(manifest, protected):
    report = adjudicate(manifest, protected, ["final"], ["pve2"])
    row = next(r for r in report["coverage"] if r["vmid"] == 101)
    assert row["generations"]["final"]["original_running_state"] == "running"
