#!/usr/bin/env python3
"""Build the operator-approved restore plan for the rebuilt node.

Every restore decision is made here, in one reviewable document, *before* any
`qmrestore` runs: which archive, which VMID, which storage, which bridge, which
MAC, and whether the guest is allowed to touch the network at all.

Nothing in this file executes anything. It produces a plan a human approves.

Exit codes:
    0  plan generated and every entry is actionable
    7  plan has blocking problems (missing archive, unresolved VMID, ...)
"""

from __future__ import annotations

import argparse

from _common import (
    dump_json,
    eprint,
    hosts_of,
    human_bytes,
    load_json,
    normalize_mac,
    parse_size,
    utc_now,
    write_text,
)


def _index_manifest(manifest: dict, source_host: str, generation: str) -> dict[int, dict]:
    entries = manifest if isinstance(manifest, list) else manifest.get("archives", [])
    best: dict[int, dict] = {}
    for entry in entries:
        if (
            entry.get("source_hostname") != source_host
            and entry.get("inventory_host") != source_host
        ):
            continue
        if generation and entry.get("generation") != generation:
            continue
        if not (entry.get("verification") or {}).get("ok"):
            continue
        try:
            vmid = int(entry["original_vmid"])
        except (KeyError, TypeError, ValueError):
            continue
        current = best.get(vmid)
        if current is None or str(entry.get("timestamp", "")) > str(current.get("timestamp", "")):
            best[vmid] = entry
    return best


def _remap_table(collisions: dict, source_host: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for collision in collisions.get("vmid_collisions", []) or []:
        for remap in collision.get("remaps", []) or []:
            if remap.get("host") == source_host:
                out[int(remap["old_vmid"])] = remap
    return out


def _target_host(discovery: dict, target_node: str) -> dict:
    return hosts_of(discovery).get(target_node, {})


def _existing_vmids(discovery: dict, disposable: set[str] | None = None) -> set[int]:
    disposable = disposable or set()
    used = set()
    for host_name, host in hosts_of(discovery).items():
        if host_name in disposable:
            continue
        for guest in host.get("guests", []) or []:
            try:
                used.add(int(guest["vmid"]))
            except (KeyError, TypeError, ValueError):
                continue
    return used


def _existing_macs(discovery: dict, exclude_hosts: set[str]) -> set[str]:
    macs = set()
    for name, host in hosts_of(discovery).items():
        if name in exclude_hosts:
            continue
        for guest in host.get("guests", []) or []:
            for nic in guest.get("nics", []) or []:
                mac = normalize_mac(nic.get("mac"))
                if mac:
                    macs.add(mac)
    return macs


def build(
    discovery: dict,
    collisions: dict,
    manifest: dict,
    source_host: str,
    target_node: str,
    generation: str,
    default_storage: str,
    isolated: dict[int, str],
    preserve_ids: set[int] | None,
    disposable_hosts: set[str] | None = None,
) -> dict:
    disposable = set(disposable_hosts or ())
    archives = _index_manifest(manifest, source_host, generation)
    remaps = _remap_table(collisions, source_host)
    source = hosts_of(discovery).get(source_host, {})
    target = _target_host(discovery, target_node)
    target_storage_ids = {s.get("storage") for s in target.get("storage", []) or []}
    target_bridges = {
        i.get("name")
        for i in target.get("network", {}).get("interfaces", []) or []
        if i.get("type") == "bridge"
    }
    target_free = {
        s.get("storage"): parse_size(s.get("avail_bytes")) for s in target.get("storage", []) or []
    }
    # The source host is being rebuilt, so its own VMIDs are not "in use" on the
    # destination. Everything else in the cluster is.
    used_vmids = {
        v
        for v in _existing_vmids(discovery, disposable)
        if v not in {int(g["vmid"]) for g in source.get("guests", []) or [] if "vmid" in g}
    }
    # The source host is being rebuilt and any disposable host has been wiped, so
    # neither still owns the MACs discovery recorded for them.
    used_macs = _existing_macs(discovery, exclude_hosts=disposable | {source_host})

    entries = []
    blocking = 0
    storage_demand: dict[str, int] = {}

    for guest in sorted(source.get("guests", []) or [], key=lambda g: int(g.get("vmid", 0))):
        vmid = int(guest["vmid"])
        problems: list[str] = []
        notes: list[str] = []

        archive = archives.get(vmid)
        if archive is None:
            problems.append(
                f"no verified '{generation}' archive for VMID {vmid} — restore not permitted"
            )

        remap = remaps.get(vmid)
        if remap and remap.get("new_vmid"):
            target_vmid = int(remap["new_vmid"])
            notes.append(
                f"renumbered {vmid} -> {target_vmid}: {remap.get('reason')}. "
                "The guest's internal IP configuration is untouched by this change."
            )
        elif remap:
            target_vmid = None
            problems.append(f"VMID {vmid} collides and no free replacement was found")
        else:
            target_vmid = vmid
            if preserve_ids is not None and vmid not in preserve_ids:
                notes.append("VMID preserved (not in the explicit preserve list, but free)")

        if target_vmid is not None and target_vmid in used_vmids:
            problems.append(f"target VMID {target_vmid} is already in use elsewhere in the cluster")
        if target_vmid is not None:
            used_vmids.add(target_vmid)

        nics = []
        for nic in guest.get("nics", []) or []:
            mac = normalize_mac(nic.get("mac"))
            bridge = nic.get("bridge")
            action = "preserve_mac"
            if mac and mac in used_macs:
                action = "regenerate_mac"
                problems.append(
                    f"MAC {mac} on {nic.get('key')} collides with another guest; "
                    "restore with --unique and record the new address"
                )
            elif mac:
                used_macs.add(mac)
            if bridge and target_bridges and bridge not in target_bridges:
                problems.append(
                    f"bridge {bridge} required by {nic.get('key')} does not exist on {target_node}"
                )
            nics.append(
                {
                    "key": nic.get("key"),
                    "model": nic.get("model"),
                    "mac": mac or nic.get("mac"),
                    "bridge": bridge,
                    "vlan_tag": nic.get("tag"),
                    "mac_action": action,
                    "link_down": bool(nic.get("link_down")),
                }
            )

        isolation_mode = isolated.get(vmid)
        if isolation_mode:
            for nic in nics:
                nic["link_down"] = True if isolation_mode == "link_down" else nic["link_down"]
            notes.append(
                "ISOLATION REQUIRED: this guest is intentionally vulnerable. It is restored "
                f"with mode '{isolation_mode}' and must never reach a routed network."
            )

        storage = guest.get("primary_storage") or default_storage
        if target_storage_ids and storage not in target_storage_ids:
            problems.append(
                f"storage '{storage}' does not exist on {target_node}; "
                "supply an explicit storage mapping before restoring"
            )
        size = parse_size(archive.get("archive_size_bytes")) if archive else 0
        restored_bytes = sum(
            parse_size(d.get("size_bytes") or d.get("size"))
            for d in guest.get("disks", []) or []
            if d.get("media") != "cdrom"
        )
        storage_demand[storage] = storage_demand.get(storage, 0) + restored_bytes

        passthrough = guest.get("passthrough", {}) or {}
        if passthrough.get("hostpci") or passthrough.get("usb"):
            notes.append(
                "Passthrough dependency: "
                + ", ".join(passthrough.get("hostpci", []) + passthrough.get("usb", []))
                + " — verify the same device exists on the destination before starting."
            )
        if guest.get("args"):
            notes.append(f"Custom QEMU args are preserved verbatim: {guest['args']}")
        if guest.get("efidisk") or guest.get("tpmstate"):
            notes.append(
                "EFI/TPM state disk present — destination storage must accept raw volumes."
            )
        if guest.get("machine"):
            notes.append(
                f"machine type pinned to {guest['machine']} — do not let it float on PVE 9."
            )

        if problems:
            blocking += 1

        entries.append(
            {
                "source_host": source_host,
                "target_node": target_node,
                "original_vmid": vmid,
                "target_vmid": target_vmid,
                "name": guest.get("name"),
                "type": guest.get("type", "qemu"),
                "archive": (archive or {}).get("archive_path"),
                "archive_sha256": (archive or {}).get("sha256"),
                "archive_size_bytes": size,
                "archive_size_human": human_bytes(size),
                "generation": generation,
                "restore_storage": storage,
                "restored_bytes_estimate": restored_bytes,
                "cpu": guest.get("cpu"),
                "machine": guest.get("machine"),
                "bios": guest.get("bios"),
                "nics": nics,
                "isolation": isolation_mode or "none",
                "start_after_restore": False,
                "original_running_state": (archive or {}).get("original_running_state"),
                "restore_command": _restore_command(guest, archive, target_vmid, storage),
                "notes": notes,
                "problems": problems,
                "actionable": not problems,
            }
        )

    capacity = []
    for storage, demand in sorted(storage_demand.items()):
        free = target_free.get(storage)
        capacity.append(
            {
                "storage": storage,
                "required_bytes": demand,
                "required_human": human_bytes(demand),
                "free_bytes": free,
                "free_human": human_bytes(free) if free is not None else None,
                "sufficient": None if free is None else free >= demand,
            }
        )
        if free is not None and free < demand:
            blocking += 1

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "source_host": source_host,
        "target_node": target_node,
        "generation": generation,
        "requires_approval": True,
        "approval_variable": "allow_restore_pve2",
        "start_policy": (
            "guests are restored in a stopped state; starting them is a separate approval"
        ),
        "entries": entries,
        "capacity": capacity,
        "counts": {
            "total": len(entries),
            "actionable": sum(1 for e in entries if e["actionable"]),
            "blocked": sum(1 for e in entries if not e["actionable"]),
        },
        "verdict": "fail" if blocking else "pass",
    }


def _restore_command(
    guest: dict, archive: dict | None, target_vmid: int | None, storage: str
) -> str:
    if not archive or target_vmid is None:
        return "<not available — resolve the problems listed for this guest first>"
    path = archive["archive_path"]
    if guest.get("type") == "lxc":
        return f"pct restore {target_vmid} {path} --storage {storage} --unprivileged 0"
    return f"qmrestore {path} {target_vmid} --storage {storage}"


def render_markdown(plan: dict) -> str:
    lines = [
        "# Restore plan (requires operator approval)",
        "",
        f"* Generated: `{plan['generated_at']}`",
        f"* Source host: `{plan['source_host']}` -> target node: `{plan['target_node']}`",
        f"* Backup generation: `{plan['generation']}`",
        f"* Verdict: **{plan['verdict'].upper()}** "
        f"({plan['counts']['actionable']}/{plan['counts']['total']} entries actionable)",
        "",
        "> Guests are restored **stopped**. Starting them is a separate, "
        "separately approved stage.",
        "",
        "## VMID mapping",
        "",
        "| original | target | name | type | archive | size | isolation |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in plan["entries"]:
        lines.append(
            f"| {e['original_vmid']} | {e['target_vmid']} | {e['name']} | {e['type']} | "
            f"`{e['archive'] or '-'}` | {e['archive_size_human']} | {e['isolation']} |"
        )
    lines += [
        "",
        "## Network",
        "",
        "| vmid | nic | mac | action | bridge | vlan | link down |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in plan["entries"]:
        for nic in e["nics"]:
            down = "yes" if nic["link_down"] else "no"
            lines.append(
                f"| {e['target_vmid']} | {nic['key']} | `{nic['mac']}` | {nic['mac_action']} | "
                f"{nic['bridge']} | {nic['vlan_tag'] or '-'} | {down} |"
            )
    lines += [
        "",
        "## Destination capacity",
        "",
        "| storage | required | free | sufficient |",
        "|---|---|---|---|",
    ]
    for c in plan["capacity"]:
        sufficient = (
            "unknown" if c["sufficient"] is None else ("yes" if c["sufficient"] else "**NO**")
        )
        lines.append(
            f"| {c['storage']} | {c['required_human']} | {c['free_human'] or '?'} | {sufficient} |"
        )
    lines += ["", "## Per-guest detail", ""]
    for e in plan["entries"]:
        lines += [
            f"### {e['original_vmid']} -> {e['target_vmid']} — {e['name']}",
            "",
            f"* Archive: `{e['archive'] or '-'}`",
            f"* SHA-256: `{e['archive_sha256'] or '-'}`",
            f"* Restore storage: `{e['restore_storage']}`",
            f"* Original running state at final backup: `{e['original_running_state']}`",
            f"* Command: `{e['restore_command']}`",
            "",
        ]
        if e["notes"]:
            lines.append("Notes:")
            lines += [f"* {n}" for n in e["notes"]]
            lines.append("")
        if e["problems"]:
            lines.append("**Blocking problems:**")
            lines += [f"* {p}" for p in e["problems"]]
            lines.append("")
    lines += [
        "## Approval",
        "",
        "Restore is refused unless BOTH are supplied on the command line:",
        "",
        "```bash",
        'make restore-pve2 EXTRA="-e allow_restore_pve2=true \\',
        "  -e restore_confirmation_pve2='RESTORE pve2 GUESTS FROM VERIFIED BACKUP'\"",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def parse_isolated(values: list[str]) -> dict[int, str]:
    out = {}
    for raw in values or []:
        try:
            vmid, mode = raw.split("=", 1)
            out[int(vmid)] = mode
        except ValueError as exc:
            raise SystemExit(f"ERROR: --isolate expects VMID=mode, got {raw!r}") from exc
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--collisions", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-host", default="pve2")
    parser.add_argument("--target-node", default="pve2")
    parser.add_argument("--generation", default="final")
    parser.add_argument("--default-storage", default="local-lvm")
    parser.add_argument(
        "--isolate", action="append", default=["9100=link_down"], metavar="VMID=MODE"
    )
    parser.add_argument("--preserve-id", action="append", type=int, default=None)
    parser.add_argument(
        "--disposable-host",
        action="append",
        default=[],
        help="host that has been (or will be) clean-installed; its old guests reserve nothing",
    )
    parser.add_argument("--out-json")
    parser.add_argument("--out-markdown")
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args(argv)

    plan = build(
        load_json(args.discovery),
        load_json(args.collisions),
        load_json(args.manifest),
        args.source_host,
        args.target_node,
        args.generation,
        args.default_storage,
        parse_isolated(args.isolate),
        set(args.preserve_id) if args.preserve_id else None,
        set(args.disposable_host),
    )
    text = dump_json(plan, args.out_json)
    if args.out_markdown:
        write_text(render_markdown(plan), args.out_markdown)
    if not args.out_json and not args.out_markdown:
        print(text, end="")

    eprint(
        f"Restore plan: {plan['verdict'].upper()}  "
        f"{plan['counts']['actionable']}/{plan['counts']['total']} actionable"
    )
    for entry in plan["entries"]:
        for problem in entry["problems"]:
            eprint(f"  [blocked] {entry['original_vmid']} {entry['name']}: {problem}")

    if plan["verdict"] == "fail" and not args.no_fail:
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
