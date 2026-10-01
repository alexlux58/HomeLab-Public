"""The known 9000 collision must be found — and so must the ones nobody told us about."""

from detect_vmid_collisions import choose_free_vmid, detect, parse_preferred


def test_finds_the_known_9000_collision(discovery):
    report = detect(discovery, "pve1", {"pve2": {9000: 9200}}, 9200, 9999)
    vmids = [c["vmid"] for c in report["vmid_collisions"]]
    assert 9000 in vmids


def test_seed_node_keeps_its_vmid(discovery):
    report = detect(discovery, "pve1", {"pve2": {9000: 9200}}, 9200, 9999)
    collision = next(c for c in report["vmid_collisions"] if c["vmid"] == 9000)
    assert collision["keep"]["host"] == "pve1"
    assert all(r["host"] != "pve1" for r in collision["remaps"])


def test_preferred_remap_is_used_when_provably_free(discovery):
    report = detect(discovery, "pve1", {"pve2": {9000: 9200}}, 9200, 9999, {"pve"})
    collision = next(c for c in report["vmid_collisions"] if c["vmid"] == 9000)
    remap = next(r for r in collision["remaps"] if r["host"] == "pve2")
    assert remap["new_vmid"] == 9200
    assert "unused cluster-wide" in remap["reason"]


def test_preferred_remap_is_rejected_when_the_vmid_is_taken(discovery):
    # Put something on 9200 so the preference can no longer be honoured. It goes
    # on pve1, which survives, so it genuinely occupies the ID.
    discovery["hosts"]["pve1"]["guests"].append(
        {
            "vmid": 9200,
            "type": "qemu",
            "name": "squatter",
            "status": "stopped",
            "disks": [],
            "nics": [],
        }
    )
    report = detect(discovery, "pve1", {"pve2": {9000: 9200}}, 9200, 9999, {"pve"})
    collision = next(c for c in report["vmid_collisions"] if c["vmid"] == 9000)
    remap = next(r for r in collision["remaps"] if r["host"] == "pve2")
    assert remap["new_vmid"] != 9200
    assert "already in use" in remap["reason"]


def test_detects_collisions_beyond_the_known_one(discovery):
    """VMIDs 100/101/102 exist on both pve2 and pve."""
    report = detect(discovery, "pve1", {}, 9200, 9999)
    vmids = {c["vmid"] for c in report["vmid_collisions"]}
    assert {100, 101, 102, 9000}.issubset(vmids)


def test_finds_the_undeclared_mac_collision(discovery):
    report = detect(discovery, "pve1", {}, 9200, 9999)
    macs = {c["mac"] for c in report["mac_collisions"]}
    assert "52:54:00:00:00:00" in macs
    holders = next(c for c in report["mac_collisions"] if c["mac"] == "52:54:00:00:00:00")
    assert {h["host"] for h in holders["holders"]} == {"pve2", "pve"}


def test_renumbering_never_claims_to_touch_the_guest_network(discovery):
    report = detect(discovery, "pve1", {"pve2": {9000: 9200}}, 9200, 9999)
    for collision in report["vmid_collisions"]:
        for remap in collision["remaps"]:
            assert remap["guest_internal_ip_changes"] is False
            assert remap["requires_approval"] is True


def test_choose_free_vmid_reports_exhaustion():
    vmid, reason = choose_free_vmid({9200, 9201}, 9200, 9200, 9201)
    assert vmid is None
    assert "no free VMID" in reason


def test_parse_preferred_accepts_the_documented_form():
    assert parse_preferred(["pve2:9000=9200"]) == {"pve2": {9000: 9200}}


def test_parse_preferred_rejects_garbage():
    import pytest

    with pytest.raises(SystemExit):
        parse_preferred(["nonsense"])


def test_storage_mapping_is_reported(discovery):
    report = detect(discovery, "pve1", {}, 9200, 9999)
    ids = {s["storage_id"] for s in report["storage_mapping"]}
    assert "local-lvm" in ids


def test_disposable_host_collisions_do_not_renumber_real_guests(discovery):
    """VMIDs 100-102 exist on pve2 AND on the disposable pve node.

    pve is about to be clean-installed, so those IDs are not really taken and
    Ansible-Puppet must keep VMID 100.
    """
    report = detect(discovery, "pve1", {"pve2": {9000: 9200}}, 9200, 9999, {"pve"})
    collision = next(c for c in report["vmid_collisions"] if c["vmid"] == 100)
    assert collision["resolution_type"] == "resolves_on_rebuild"
    assert collision["remaps"] == []


def test_disposable_guests_do_not_consume_the_remap_range(discovery):
    report = detect(discovery, "pve1", {"pve2": {9000: 9200}}, 9200, 9999, {"pve"})
    collision = next(c for c in report["vmid_collisions"] if c["vmid"] == 9000)
    assert collision["remaps"][0]["new_vmid"] == 9200


def test_preferences_are_reserved_against_processing_order(discovery):
    """A second collision must not be handed 9200 just because it is processed first."""
    discovery["hosts"]["pve1"]["guests"].append(
        {"vmid": 500, "type": "qemu", "name": "a", "status": "stopped", "disks": [], "nics": []}
    )
    discovery["hosts"]["pve2"]["guests"].append(
        {"vmid": 500, "type": "qemu", "name": "b", "status": "stopped", "disks": [], "nics": []}
    )
    report = detect(discovery, "pve1", {"pve2": {9000: 9200}}, 9200, 9999, {"pve"})
    nine_thousand = next(c for c in report["vmid_collisions"] if c["vmid"] == 9000)
    five_hundred = next(c for c in report["vmid_collisions"] if c["vmid"] == 500)
    assert nine_thousand["remaps"][0]["new_vmid"] == 9200
    assert five_hundred["remaps"][0]["new_vmid"] != 9200


def test_mac_collision_on_a_disposable_host_is_marked_as_self_resolving(discovery):
    report = detect(discovery, "pve1", {}, 9200, 9999, {"pve"})
    clash = next(c for c in report["mac_collisions"] if c["mac"] == "52:54:00:00:00:00")
    assert clash["resolves_on_rebuild"] is True
    assert report["summary"]["mac_collisions_requiring_action"] == 0
