#!/usr/bin/env python3
"""Diff two discovery snapshots and refuse to accept regressions.

Used around every risky operation: before/after `pvecm create`, before/after the
PVE 8 -> 9 upgrade, and before/after each node join. The question it answers is
narrow and important: *did anything disappear?*

Exit codes:
    0  no regressions (informational changes may still be reported)
    6  a guest, disk, NIC, storage definition or bridge disappeared
"""

from __future__ import annotations

import argparse

from _common import dump_json, eprint, hosts_of, load_json, normalize_mac, utc_now, write_text

REGRESSION_ISSUES = {
    "guest_missing",
    "disk_missing",
    "nic_missing",
    "storage_missing",
    "bridge_missing",
    "mac_changed",
    "vmid_changed",
}


def _guests_by_vmid(host: dict) -> dict[int, dict]:
    out = {}
    for guest in host.get("guests", []) or []:
        try:
            out[int(guest["vmid"])] = guest
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _bridges(host: dict) -> set[str]:
    return {
        i.get("name")
        for i in host.get("network", {}).get("interfaces", []) or []
        if i.get("type") == "bridge" and i.get("name")
    }


def _storage_ids(host: dict) -> set[str]:
    return {s.get("storage") for s in host.get("storage", []) or [] if s.get("storage")}


def compare(pre: dict, post: dict, hosts_filter: list[str] | None) -> dict:
    findings: list[dict] = []
    pre_hosts = hosts_of(pre)
    post_hosts = hosts_of(post)

    names = sorted(set(pre_hosts) | set(post_hosts))
    if hosts_filter:
        names = [n for n in names if n in hosts_filter]

    per_host = []
    for name in names:
        before = pre_hosts.get(name)
        after = post_hosts.get(name)
        if before is None:
            findings.append(
                {
                    "severity": "info",
                    "host": name,
                    "issue": "host_added",
                    "detail": "not present in the pre snapshot",
                }
            )
            continue
        if after is None:
            findings.append(
                {
                    "severity": "fail",
                    "host": name,
                    "issue": "host_missing",
                    "detail": "host present before but absent afterwards",
                }
            )
            continue

        pre_guests = _guests_by_vmid(before)
        post_guests = _guests_by_vmid(after)

        for vmid in sorted(set(pre_guests) - set(post_guests)):
            findings.append(
                {
                    "severity": "fail",
                    "host": name,
                    "issue": "guest_missing",
                    "detail": (
                        f"VMID {vmid} ({pre_guests[vmid].get('name')}) is no longer registered"
                    ),
                }
            )
        for vmid in sorted(set(post_guests) - set(pre_guests)):
            findings.append(
                {
                    "severity": "info",
                    "host": name,
                    "issue": "guest_added",
                    "detail": f"VMID {vmid} ({post_guests[vmid].get('name')}) appeared",
                }
            )

        for vmid in sorted(set(pre_guests) & set(post_guests)):
            gb, ga = pre_guests[vmid], post_guests[vmid]
            if gb.get("name") != ga.get("name"):
                findings.append(
                    {
                        "severity": "warn",
                        "host": name,
                        "issue": "guest_renamed",
                        "detail": f"VMID {vmid}: {gb.get('name')} -> {ga.get('name')}",
                    }
                )
            pre_disks = {d.get("key") for d in gb.get("disks", []) or []}
            post_disks = {d.get("key") for d in ga.get("disks", []) or []}
            for key in sorted(pre_disks - post_disks):
                findings.append(
                    {
                        "severity": "fail",
                        "host": name,
                        "issue": "disk_missing",
                        "detail": f"VMID {vmid}: disk {key} disappeared",
                    }
                )
            pre_macs = {normalize_mac(n.get("mac")) for n in gb.get("nics", []) or []}
            post_macs = {normalize_mac(n.get("mac")) for n in ga.get("nics", []) or []}
            for mac in sorted(m for m in pre_macs - post_macs if m):
                findings.append(
                    {
                        "severity": "fail",
                        "host": name,
                        "issue": "mac_changed",
                        "detail": f"VMID {vmid}: MAC {mac} is no longer configured",
                    }
                )
            if gb.get("status") != ga.get("status"):
                findings.append(
                    {
                        "severity": "info",
                        "host": name,
                        "issue": "guest_power_state_changed",
                        "detail": f"VMID {vmid}: {gb.get('status')} -> {ga.get('status')}",
                    }
                )

        for sid in sorted(_storage_ids(before) - _storage_ids(after)):
            findings.append(
                {
                    "severity": "fail",
                    "host": name,
                    "issue": "storage_missing",
                    "detail": f"storage '{sid}' is no longer defined",
                }
            )
        for sid in sorted(_storage_ids(after) - _storage_ids(before)):
            findings.append(
                {
                    "severity": "info",
                    "host": name,
                    "issue": "storage_added",
                    "detail": f"storage '{sid}' appeared",
                }
            )
        for bridge in sorted(_bridges(before) - _bridges(after)):
            findings.append(
                {
                    "severity": "fail",
                    "host": name,
                    "issue": "bridge_missing",
                    "detail": f"bridge '{bridge}' disappeared",
                }
            )

        pre_ver = before.get("system", {}).get("pve_version")
        post_ver = after.get("system", {}).get("pve_version")
        if pre_ver != post_ver:
            findings.append(
                {
                    "severity": "info",
                    "host": name,
                    "issue": "version_changed",
                    "detail": f"{pre_ver} -> {post_ver}",
                }
            )

        per_host.append(
            {
                "host": name,
                "guests_before": len(pre_guests),
                "guests_after": len(post_guests),
                "storage_before": len(_storage_ids(before)),
                "storage_after": len(_storage_ids(after)),
                "pve_version_before": pre_ver,
                "pve_version_after": post_ver,
            }
        )

    regressions = [
        f for f in findings if f["issue"] in REGRESSION_ISSUES or f["severity"] == "fail"
    ]
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "per_host": per_host,
        "findings": findings,
        "counts": {
            "regressions": len(regressions),
            "warnings": sum(1 for f in findings if f["severity"] == "warn"),
            "informational": sum(1 for f in findings if f["severity"] == "info"),
        },
        "verdict": "fail" if regressions else "pass",
    }


def render_markdown(report: dict, pre_label: str, post_label: str) -> str:
    lines = [
        "# Pre/post state comparison",
        "",
        f"* Before: `{pre_label}`",
        f"* After: `{post_label}`",
        f"* Generated: `{report['generated_at']}`",
        f"* Verdict: **{report['verdict'].upper()}**",
        "",
        "| host | guests before | guests after | storage before | storage after "
        "| pve before | pve after |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report["per_host"]:
        lines.append(
            f"| {row['host']} | {row['guests_before']} | {row['guests_after']} | "
            f"{row['storage_before']} | {row['storage_after']} | "
            f"{row['pve_version_before']} | {row['pve_version_after']} |"
        )
    lines += ["", "## Findings", ""]
    if not report["findings"]:
        lines.append("_No differences detected._")
    else:
        lines += ["| severity | host | issue | detail |", "|---|---|---|---|"]
        for f in report["findings"]:
            lines.append(f"| {f['severity']} | {f['host']} | {f['issue']} | {f['detail']} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pre", required=True)
    parser.add_argument("--post", required=True)
    parser.add_argument("--host", action="append", default=None)
    parser.add_argument("--out-json")
    parser.add_argument("--out-markdown")
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args(argv)

    report = compare(load_json(args.pre), load_json(args.post), args.host)
    text = dump_json(report, args.out_json)
    if args.out_markdown:
        write_text(render_markdown(report, args.pre, args.post), args.out_markdown)
    if not args.out_json and not args.out_markdown:
        print(text, end="")

    eprint(
        f"State comparison: {report['verdict'].upper()} "
        f"({report['counts']['regressions']} regressions)"
    )
    for finding in report["findings"]:
        if finding["severity"] != "info":
            eprint(f"  [{finding['severity']}] {finding['host']}: {finding['detail']}")

    if report["verdict"] == "fail" and not args.no_fail:
        return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
