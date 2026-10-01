"""Pre/post comparison must notice when something disappears."""

from compare_pre_post_state import compare, render_markdown


def test_identical_snapshots_pass(discovery):
    report = compare(discovery, discovery, None)
    assert report["verdict"] == "pass"
    assert report["counts"]["regressions"] == 0


def test_a_missing_guest_is_a_regression(discovery, discovery_post):
    report = compare(discovery, discovery_post, ["pve1"])
    assert report["verdict"] == "fail"
    missing = [f for f in report["findings"] if f["issue"] == "guest_missing"]
    assert missing and "297" in missing[0]["detail"]


def test_a_version_change_is_informational_only(discovery, discovery_post):
    report = compare(discovery, discovery_post, ["pve2"])
    assert report["verdict"] == "pass"


def test_a_missing_disk_is_a_regression(discovery):
    post = _clone(discovery)
    post["hosts"]["pve1"]["guests"][0]["disks"] = []
    report = compare(discovery, post, ["pve1"])
    assert any(f["issue"] == "disk_missing" for f in report["findings"])
    assert report["verdict"] == "fail"


def test_a_changed_mac_is_a_regression(discovery):
    post = _clone(discovery)
    post["hosts"]["pve1"]["guests"][0]["nics"][0]["mac"] = "52:54:00:00:00:00"
    report = compare(discovery, post, ["pve1"])
    assert any(f["issue"] == "mac_changed" for f in report["findings"])


def test_a_missing_storage_definition_is_a_regression(discovery):
    post = _clone(discovery)
    post["hosts"]["pve1"]["storage"] = [
        s for s in post["hosts"]["pve1"]["storage"] if s["storage"] != "local-lvm"
    ]
    report = compare(discovery, post, ["pve1"])
    assert any(f["issue"] == "storage_missing" for f in report["findings"])
    assert report["verdict"] == "fail"


def test_a_missing_bridge_is_a_regression(discovery):
    post = _clone(discovery)
    post["hosts"]["pve1"]["network"]["interfaces"] = [
        i for i in post["hosts"]["pve1"]["network"]["interfaces"] if i.get("type") != "bridge"
    ]
    report = compare(discovery, post, ["pve1"])
    assert any(f["issue"] == "bridge_missing" for f in report["findings"])


def test_added_storage_is_informational(discovery):
    post = _clone(discovery)
    post["hosts"]["pve1"]["storage"].append(
        {
            "storage": "synology-backup",
            "type": "nfs",
            "content": "backup",
            "active": True,
            "enabled": True,
            "shared": True,
            "total_bytes": 0,
            "used_bytes": 0,
            "avail_bytes": 0,
        }
    )
    report = compare(discovery, post, ["pve1"])
    assert report["verdict"] == "pass"
    assert any(f["issue"] == "storage_added" for f in report["findings"])


def test_power_state_change_is_informational(discovery):
    post = _clone(discovery)
    post["hosts"]["pve1"]["guests"][0]["status"] = "stopped"
    report = compare(discovery, post, ["pve1"])
    assert report["verdict"] == "pass"
    assert any(f["issue"] == "guest_power_state_changed" for f in report["findings"])


def test_markdown_report_renders(discovery, discovery_post):
    report = compare(discovery, discovery_post, None)
    text = render_markdown(report, "pre.json", "post.json")
    assert "# Pre/post state comparison" in text
    assert "FAIL" in text


def _clone(doc):
    import json

    return json.loads(json.dumps(doc))
