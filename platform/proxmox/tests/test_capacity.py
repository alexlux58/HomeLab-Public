"""Capacity must be pessimistic, and it must refuse Volume 2 outright."""

from calculate_backup_capacity import estimate

GIB = 1024**3
TIB = 1024**4


def _estimate(discovery, protected, **kw):
    params = dict(
        generations=2,
        margin_pct=30.0,
        compression_ratio=1.0,
        nas_free_bytes=10 * TIB,
        nas_total_bytes=12 * TIB,
        nas_mount_source="192.168.0.20:/volume1/proxmox-cluster-backups",
        forbidden_prefixes=["/volume2"],
        required_prefix="/volume1",
        min_free_gib=512.0,
    )
    params.update(kw)
    return estimate(discovery, protected, **params)


def test_healthy_environment_passes(discovery, protected):
    # Remove the deliberately excluded disk so the happy path is actually happy.
    for g in discovery["hosts"]["pve2"]["guests"]:
        for d in g["disks"]:
            d["backup"] = True
    report = _estimate(discovery, protected)
    assert report["verdict"] == "pass"


def test_two_generations_and_margin_are_applied(discovery, protected):
    report = _estimate(discovery, protected)
    totals = report["totals"]
    assert totals["all_generations_bytes"] == totals["per_generation_bytes"] * 2
    assert totals["required_with_margin_bytes"] == int(totals["all_generations_bytes"] * 1.3)


def test_volume2_is_rejected_outright(discovery, protected):
    report = _estimate(
        discovery, protected, nas_mount_source="192.168.0.20:/volume2/proxmox-cluster-backups"
    )
    assert report["verdict"] == "fail"
    assert any(f["issue"] == "forbidden_volume" for f in report["findings"])


def test_a_path_outside_volume1_is_rejected(discovery, protected):
    report = _estimate(discovery, protected, nas_mount_source="192.168.0.20:/volume9/backups")
    assert any(f["issue"] == "unexpected_volume" for f in report["findings"])
    assert report["verdict"] == "fail"


def test_insufficient_space_fails(discovery, protected):
    report = _estimate(discovery, protected, nas_free_bytes=100 * GIB)
    assert report["verdict"] == "fail"
    assert any(f["issue"] == "insufficient_capacity" for f in report["findings"])


def test_absolute_floor_is_enforced(discovery, protected):
    report = _estimate(discovery, protected, nas_free_bytes=10 * GIB, min_free_gib=512.0)
    assert any(f["issue"] == "below_absolute_floor" for f in report["findings"])


def test_disk_excluded_from_backup_is_a_hard_finding(discovery, protected):
    """metasploitable2 scsi1 has backup=0 in the fixture."""
    report = _estimate(discovery, protected)
    excluded = [f for f in report["findings"] if f["issue"] == "disk_excluded_from_backup"]
    assert excluded
    assert "9100" in excluded[0]["guest"]
    assert report["verdict"] == "fail"


def test_missing_protected_guest_is_a_hard_finding(discovery, protected):
    discovery["hosts"]["pve1"]["guests"] = [
        g for g in discovery["hosts"]["pve1"]["guests"] if g["vmid"] != 290
    ]
    report = _estimate(discovery, protected)
    assert any(f["issue"] == "protected_guest_missing" for f in report["findings"])
    assert report["verdict"] == "fail"


def test_bind_mounts_are_flagged(discovery, protected):
    discovery["hosts"]["pve2"]["guests"][0]["mountpoints"] = [
        {
            "key": "mp0",
            "source": "/srv/data",
            "target": "/data",
            "is_bind": True,
            "is_device": False,
            "backup_flag": False,
            "size_bytes": 0,
            "raw": "",
        }
    ]
    report = _estimate(discovery, protected)
    assert any(f["issue"] == "bind_mount_not_backed_up" for f in report["findings"])


def test_disposable_host_is_never_counted(discovery, protected):
    report = _estimate(discovery, protected)
    assert {h["host"] for h in report["per_host"]} == {"pve1", "pve2"}


def test_compression_assumption_is_conservative_by_default(discovery, protected):
    pessimistic = _estimate(discovery, protected, compression_ratio=1.0)
    optimistic = _estimate(discovery, protected, compression_ratio=0.4)
    assert (
        pessimistic["totals"]["required_with_margin_bytes"]
        > optimistic["totals"]["required_with_margin_bytes"]
    )
