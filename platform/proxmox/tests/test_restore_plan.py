"""The restore plan is the document that decides what actually happens."""

from build_restore_plan import build, parse_isolated, render_markdown


def _plan(discovery, collisions, manifest, **kw):
    params = dict(
        source_host="pve2",
        target_node="pve2",
        generation="final",
        default_storage="local-lvm",
        isolated={9100: "link_down"},
        preserve_ids=None,
        disposable_hosts={"pve"},
    )
    params.update(kw)
    return build(discovery, collisions, manifest, **params)


def test_ids_are_preserved_where_possible(discovery, collisions, manifest):
    plan = _plan(discovery, collisions, manifest)
    mapping = {e["original_vmid"]: e["target_vmid"] for e in plan["entries"]}
    assert mapping[100] == 100
    assert mapping[101] == 101
    assert mapping[102] == 102
    assert mapping[9100] == 9100


def test_the_colliding_vmid_is_renumbered(discovery, collisions, manifest):
    plan = _plan(discovery, collisions, manifest)
    mapping = {e["original_vmid"]: e["target_vmid"] for e in plan["entries"]}
    assert mapping[9000] == 9200


def test_metasploitable_is_isolated(discovery, collisions, manifest):
    plan = _plan(discovery, collisions, manifest)
    entry = next(e for e in plan["entries"] if e["original_vmid"] == 9100)
    assert entry["isolation"] == "link_down"
    assert all(nic["link_down"] for nic in entry["nics"])
    assert any("never reach a routed network" in n for n in entry["notes"])


def test_nothing_starts_automatically(discovery, collisions, manifest):
    plan = _plan(discovery, collisions, manifest)
    assert all(e["start_after_restore"] is False for e in plan["entries"])
    assert "separate approval" in plan["start_policy"]


def test_restore_commands_are_generated(discovery, collisions, manifest):
    plan = _plan(discovery, collisions, manifest)
    entry = next(e for e in plan["entries"] if e["original_vmid"] == 9000)
    assert entry["restore_command"].startswith("qmrestore ")
    assert " 9200 " in entry["restore_command"]
    assert "--storage local-lvm" in entry["restore_command"]


def test_missing_archive_blocks_the_entry(discovery, collisions, manifest):
    manifest["archives"] = [
        a
        for a in manifest["archives"]
        if not (a["original_vmid"] == 101 and a["generation"] == "final")
    ]
    plan = _plan(discovery, collisions, manifest)
    entry = next(e for e in plan["entries"] if e["original_vmid"] == 101)
    assert not entry["actionable"]
    assert plan["verdict"] == "fail"


def test_unverified_archive_is_not_usable(discovery, collisions, manifest):
    for a in manifest["archives"]:
        if a["original_vmid"] == 100 and a["generation"] == "final":
            a["verification"]["ok"] = False
    plan = _plan(discovery, collisions, manifest)
    entry = next(e for e in plan["entries"] if e["original_vmid"] == 100)
    assert not entry["actionable"]


def test_missing_bridge_on_the_destination_blocks_the_entry(discovery, collisions, manifest):
    discovery["hosts"]["pve2"]["network"]["interfaces"] = [
        i
        for i in discovery["hosts"]["pve2"]["network"]["interfaces"]
        if i.get("type") != "bridge"
    ] + [
        {
            "name": "vmbr1",
            "type": "bridge",
            "addresses": [],
            "ports": [],
            "mtu": 1500,
            "state": "UP",
            "vlan_aware": True,
            "master": None,
            "mac": None,
        }
    ]
    plan = _plan(discovery, collisions, manifest)
    assert plan["verdict"] == "fail"
    assert any("does not exist" in p for e in plan["entries"] for p in e["problems"])


def test_capacity_is_checked_against_the_destination(discovery, collisions, manifest):
    plan = _plan(discovery, collisions, manifest)
    entry = next(c for c in plan["capacity"] if c["storage"] == "local-lvm")
    assert entry["required_bytes"] > 0
    assert entry["sufficient"] is True


def test_insufficient_destination_capacity_fails_the_plan(discovery, collisions, manifest):
    for store in discovery["hosts"]["pve2"]["storage"]:
        if store["storage"] == "local-lvm":
            store["avail_bytes"] = 1024
    plan = _plan(discovery, collisions, manifest)
    assert plan["verdict"] == "fail"
    assert next(c for c in plan["capacity"] if c["storage"] == "local-lvm")["sufficient"] is False


def test_macs_are_preserved_when_the_only_clash_is_on_a_wiped_host(discovery, collisions, manifest):
    """pve holds a duplicate MAC today, but pve is clean-installed before this runs."""
    plan = _plan(discovery, collisions, manifest)
    entry = next(e for e in plan["entries"] if e["original_vmid"] == 100)
    assert entry["nics"][0]["mac_action"] == "preserve_mac"


def test_mac_collision_with_a_surviving_host_forces_regeneration(discovery, collisions, manifest):
    # Give a guest on the seed node the same MAC as pve2 VMID 100.
    discovery["hosts"]["pve1"]["guests"][0]["nics"][0]["mac"] = "52:54:00:00:00:00"
    plan = _plan(discovery, collisions, manifest)
    entry = next(e for e in plan["entries"] if e["original_vmid"] == 100)
    assert entry["nics"][0]["mac_action"] == "regenerate_mac"
    assert not entry["actionable"]


def test_markdown_renders_and_names_the_approval_string(discovery, collisions, manifest):
    plan = _plan(discovery, collisions, manifest)
    text = render_markdown(plan)
    assert "# Restore plan" in text
    assert "allow_restore_pve2=true" in text
    assert "9200" in text


def test_parse_isolated_round_trips():
    assert parse_isolated(["9100=link_down"]) == {9100: "link_down"}
