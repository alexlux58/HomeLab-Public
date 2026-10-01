#!/usr/bin/env python3
"""Detect every VMID and MAC-address collision across the discovered hosts.

The migration has one *known* collision (VMID 9000 on both .11 and .12) but
assuming that is the only one would be a good way to lose a VM. This walks the
whole discovery document and reports every duplicate it can find, then proposes
a resolution that always keeps the seed node's guest at its original VMID.

Exit codes:
    0  no unresolved collisions (collisions may exist but all have a proposal)
    3  a collision exists that the tool could not resolve automatically
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from _common import (
    dump_json,
    eprint,
    guest_label,
    hosts_of,
    iter_guests,
    normalize_mac,
    utc_now,
)


def _holder(host_name: str, guest: dict, preserve_host: str, disposable: set[str]) -> dict:
    return {
        "host": host_name,
        "vmid": guest.get("vmid"),
        "name": guest.get("name"),
        "type": guest.get("type", "qemu"),
        "status": guest.get("status"),
        "preserve": host_name == preserve_host,
        "disposable": host_name in disposable,
    }


def collect_used_vmids(discovery: dict, disposable: set[str] | None = None) -> set[int]:
    """VMIDs that are genuinely taken.

    Guests on a disposable host do not count: that host is about to be wiped, so
    holding 9200 hostage for a Kali VM that will not exist in an hour would push
    a real guest into an arbitrary VMID for no reason.
    """
    disposable = disposable or set()
    used: set[int] = set()
    for host_name, guest in iter_guests(discovery):
        if host_name in disposable:
            continue
        try:
            used.add(int(guest["vmid"]))
        except (KeyError, TypeError, ValueError):
            continue
    for host_name, host in hosts_of(discovery).items():
        if host_name in disposable:
            continue
        for reserved in host.get("reserved_vmids", []) or []:
            try:
                used.add(int(reserved))
            except (TypeError, ValueError):
                continue
    return used


def choose_free_vmid(
    used: set[int],
    preferred: int | None,
    search_start: int,
    search_end: int,
    reserved: set[int] | None = None,
) -> tuple[int | None, str]:
    """Pick a cluster-wide free VMID.

    The preferred VMID is only honoured if discovery proves it is unused. This
    is the difference between "we like 9200" and "9200 is provably free".

    ``reserved`` holds VMIDs that some *other* guest has asked for by name. The
    fallback scan skips them so that processing order cannot steal a preference.
    """
    reserved = reserved or set()
    if preferred is not None and preferred not in used:
        return preferred, f"preferred VMID {preferred} is unused cluster-wide"
    reason_prefix = ""
    if preferred is not None:
        reason_prefix = f"preferred VMID {preferred} is already in use; "
    for candidate in range(search_start, search_end + 1):
        if candidate not in used and candidate not in reserved:
            return candidate, f"{reason_prefix}first free VMID in {search_start}-{search_end}"
    return None, f"{reason_prefix}no free VMID in {search_start}-{search_end}"


def detect(
    discovery: dict,
    preserve_host: str,
    preferred_remap: dict[str, dict[int, int]],
    search_start: int,
    search_end: int,
    disposable_hosts: set[str] | None = None,
) -> dict:
    disposable = set(disposable_hosts or ())
    by_vmid: dict[int, list[dict]] = defaultdict(list)
    by_mac: dict[str, list[dict]] = defaultdict(list)
    unparsed_macs: list[dict] = []

    for host_name, guest in iter_guests(discovery):
        try:
            vmid = int(guest["vmid"])
        except (KeyError, TypeError, ValueError):
            continue
        by_vmid[vmid].append(_holder(host_name, guest, preserve_host, disposable))
        for nic in guest.get("nics", []) or []:
            mac = normalize_mac(nic.get("mac"))
            entry = {
                "host": host_name,
                "vmid": vmid,
                "name": guest.get("name"),
                "interface": nic.get("key"),
                "bridge": nic.get("bridge"),
                "raw_mac": nic.get("mac"),
                "disposable": host_name in disposable,
            }
            if not mac:
                unparsed_macs.append(entry)
                continue
            by_mac[mac].append(entry)

    used = collect_used_vmids(discovery, disposable)
    # Preferences are reserved up front so the order in which collisions happen
    # to be processed cannot hand 9200 to somebody who did not ask for it.
    reserved = {
        target
        for host_map in preferred_remap.values()
        for target in host_map.values()
        if target not in used
    }
    vmid_collisions = []
    unresolved = 0

    for vmid in sorted(v for v, holders in by_vmid.items() if len(holders) > 1):
        holders = by_vmid[vmid]
        surviving = [h for h in holders if not h["disposable"]]
        remaps: list[dict] = []

        if len(surviving) < 2:
            # The clash only exists because a host that is about to be wiped
            # still holds the ID. Report it, but do not renumber a real guest.
            keep = surviving[0] if surviving else holders[0]
            vmid_collisions.append(
                {
                    "vmid": vmid,
                    "holders": holders,
                    "keep": {"host": keep["host"], "name": keep["name"], "vmid": vmid},
                    "resolution_type": "resolves_on_rebuild",
                    "resolution_note": (
                        "the other holder(s) are on a disposable host that will be "
                        "clean-installed; no renumbering is required"
                    ),
                    "remaps": [],
                }
            )
            continue

        keep = next((h for h in surviving if h["preserve"]), surviving[0])
        for holder in surviving:
            if holder is keep:
                continue
            preferred = preferred_remap.get(holder["host"], {}).get(vmid)
            new_vmid, reason = choose_free_vmid(
                used, preferred, search_start, search_end, reserved - {preferred}
            )
            if new_vmid is None:
                unresolved += 1
            else:
                used.add(new_vmid)
                reserved.discard(new_vmid)
            remaps.append(
                {
                    "host": holder["host"],
                    "name": holder["name"],
                    "type": holder["type"],
                    "old_vmid": vmid,
                    "new_vmid": new_vmid,
                    "reason": reason,
                    "requires_approval": True,
                    "guest_internal_ip_changes": False,
                }
            )
        vmid_collisions.append(
            {
                "vmid": vmid,
                "holders": holders,
                "keep": {"host": keep["host"], "name": keep["name"], "vmid": vmid},
                "resolution_type": "remap_required",
                "resolution_note": f"{keep['host']} keeps VMID {vmid}",
                "remaps": remaps,
            }
        )

    mac_collisions = [
        {
            "mac": mac,
            "holders": holders,
            "resolves_on_rebuild": sum(1 for h in holders if not h["disposable"]) < 2,
        }
        for mac, holders in sorted(by_mac.items())
        if len(holders) > 1
    ]

    storage_ids: dict[str, list[str]] = defaultdict(list)
    for host_name, host in sorted(hosts_of(discovery).items()):
        for store in host.get("storage", []) or []:
            sid = store.get("storage")
            if sid:
                storage_ids[sid].append(host_name)

    guest_storage_refs: dict[str, list[str]] = defaultdict(list)
    for host_name, guest in iter_guests(discovery):
        for disk in guest.get("disks", []) or []:
            sid = disk.get("storage")
            if sid:
                guest_storage_refs[sid].append(f"{host_name}:{guest_label(guest)}")

    storage_mapping = [
        {
            "storage_id": sid,
            "defined_on": sorted(set(storage_ids.get(sid, []))),
            "referenced_by": sorted(set(refs)),
            "needs_restore_mapping": not storage_ids.get(sid),
        }
        for sid, refs in sorted(guest_storage_refs.items())
    ]

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "policy": {
            "preserve_host": preserve_host,
            "preferred_remap": {
                h: {str(k): v for k, v in m.items()} for h, m in preferred_remap.items()
            },
            "search_range": [search_start, search_end],
            "disposable_hosts": sorted(disposable),
        },
        "summary": {
            "total_guests": sum(1 for _ in iter_guests(discovery)),
            "vmid_collision_count": len(vmid_collisions),
            "mac_collision_count": len(mac_collisions),
            "mac_collisions_requiring_action": sum(
                1 for c in mac_collisions if not c["resolves_on_rebuild"]
            ),
            "collisions_resolving_on_rebuild": sum(
                1 for c in vmid_collisions if c["resolution_type"] == "resolves_on_rebuild"
            ),
            "unparsed_mac_count": len(unparsed_macs),
            "unresolved_collision_count": unresolved,
            "storage_ids_needing_mapping": sum(
                1 for s in storage_mapping if s["needs_restore_mapping"]
            ),
        },
        "vmid_collisions": vmid_collisions,
        "mac_collisions": mac_collisions,
        "unparsed_macs": unparsed_macs,
        "storage_mapping": storage_mapping,
    }


def parse_preferred(values: list[str]) -> dict[str, dict[int, int]]:
    """Parse ``host:old=new`` pairs, e.g. ``pve2:9000=9200``."""
    out: dict[str, dict[int, int]] = defaultdict(dict)
    for raw in values or []:
        try:
            host, mapping = raw.split(":", 1)
            old, new = mapping.split("=", 1)
            out[host][int(old)] = int(new)
        except ValueError as exc:
            raise SystemExit(f"ERROR: --prefer expects host:old=new, got {raw!r}") from exc
    return dict(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--discovery", required=True, help="artifacts/discovery.json")
    parser.add_argument("--out", help="write the collision report here")
    parser.add_argument(
        "--preserve-host",
        default="pve1",
        help="host whose VMIDs are never renumbered (the cluster seed)",
    )
    parser.add_argument(
        "--prefer",
        action="append",
        default=[],
        metavar="HOST:OLD=NEW",
        help="preferred remap, honoured only if the new VMID is provably free",
    )
    parser.add_argument(
        "--disposable-host",
        action="append",
        default=[],
        help="host whose guests will be destroyed and therefore do not reserve VMIDs",
    )
    parser.add_argument("--search-start", type=int, default=9200)
    parser.add_argument("--search-end", type=int, default=9999)
    parser.add_argument(
        "--fail-on-unresolved",
        action="store_true",
        help="exit 3 if any collision could not be resolved",
    )
    args = parser.parse_args(argv)

    from _common import load_json  # local import keeps the module import-light

    report = detect(
        load_json(args.discovery),
        args.preserve_host,
        parse_preferred(args.prefer),
        args.search_start,
        args.search_end,
        set(args.disposable_host),
    )
    text = dump_json(report, args.out)
    if not args.out:
        print(text, end="")

    summary = report["summary"]
    eprint(
        f"VMID collisions: {summary['vmid_collision_count']}  "
        f"MAC collisions: {summary['mac_collision_count']}  "
        f"unresolved: {summary['unresolved_collision_count']}"
    )
    if args.fail_on_unresolved and summary["unresolved_collision_count"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
