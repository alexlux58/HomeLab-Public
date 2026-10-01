#!/usr/bin/env python3
"""Estimate the space the migration backups need and compare it to the NAS.

Two backup generations are taken of every protected guest (live snapshot, then
cleanly stopped), so the requirement is roughly ``2 x provisioned bytes`` plus a
safety margin. The estimate is deliberately pessimistic: by default no
compression benefit is assumed, because running out of space halfway through a
migration backup is far worse than over-provisioning.

Exit codes:
    0  enough space (or --no-fail requested)
    4  insufficient capacity, forbidden volume, or a disk excluded from backup
"""

from __future__ import annotations

import argparse

from _common import (
    backed_up_disk_bytes,
    dump_json,
    eprint,
    excluded_disks,
    guest_disk_bytes,
    guest_label,
    hosts_of,
    human_bytes,
    load_json,
    pct,
    utc_now,
)


def _protected_vmids(protected: dict, host: str) -> set[int] | None:
    entries = protected.get(host)
    if entries is None:
        return None
    return {int(e["vmid"]) for e in entries}


def estimate(
    discovery: dict,
    protected: dict,
    generations: int,
    margin_pct: float,
    compression_ratio: float,
    nas_free_bytes: int | None,
    nas_total_bytes: int | None,
    nas_mount_source: str | None,
    forbidden_prefixes: list[str],
    required_prefix: str | None,
    min_free_gib: float,
) -> dict:
    per_host = []
    grand_total_raw = 0
    findings: list[dict] = []

    for host_name, host in sorted(hosts_of(discovery).items()):
        wanted = _protected_vmids(protected, host_name)
        if wanted is None:
            continue  # host has no protected guests (e.g. the disposable node)
        guests_out = []
        host_raw = 0
        seen: set[int] = set()

        for guest in host.get("guests", []) or []:
            try:
                vmid = int(guest.get("vmid"))
            except (TypeError, ValueError):
                continue
            if vmid not in wanted:
                continue
            seen.add(vmid)
            provisioned = guest_disk_bytes(guest)
            backed_up = backed_up_disk_bytes(guest)
            skipped = excluded_disks(guest)
            if skipped:
                findings.append(
                    {
                        "severity": "fail",
                        "host": host_name,
                        "guest": guest_label(guest),
                        "issue": "disk_excluded_from_backup",
                        "detail": (
                            "disks with backup=0 will be silently skipped by vzdump: "
                            + ", ".join(str(d.get("key")) for d in skipped)
                        ),
                    }
                )
            for mp in guest.get("mountpoints", []) or []:
                if mp.get("is_bind") or mp.get("is_device"):
                    findings.append(
                        {
                            "severity": "fail",
                            "host": host_name,
                            "guest": guest_label(guest),
                            "issue": "bind_mount_not_backed_up",
                            "detail": (
                                f"{mp.get('key')} -> {mp.get('source')} is a bind/device mount; "
                                "vzdump never includes these, an approved separate copy is required"
                            ),
                        }
                    )
            host_raw += provisioned
            guests_out.append(
                {
                    "vmid": vmid,
                    "name": guest.get("name"),
                    "type": guest.get("type", "qemu"),
                    "provisioned_bytes": provisioned,
                    "provisioned_human": human_bytes(provisioned),
                    "backup_eligible_bytes": backed_up,
                    "excluded_disk_count": len(skipped),
                }
            )

        for missing in sorted(wanted - seen):
            findings.append(
                {
                    "severity": "fail",
                    "host": host_name,
                    "guest": str(missing),
                    "issue": "protected_guest_missing",
                    "detail": "declared in protected_guests but not found by discovery",
                }
            )

        per_host.append(
            {
                "host": host_name,
                "guest_count": len(guests_out),
                "provisioned_bytes": host_raw,
                "provisioned_human": human_bytes(host_raw),
                "guests": sorted(guests_out, key=lambda g: g["vmid"]),
            }
        )
        grand_total_raw += host_raw

    per_generation = int(grand_total_raw * compression_ratio)
    all_generations = per_generation * generations
    required = int(all_generations * (1.0 + margin_pct / 100.0))

    nas = {
        "free_bytes": nas_free_bytes,
        "free_human": human_bytes(nas_free_bytes) if nas_free_bytes is not None else None,
        "total_bytes": nas_total_bytes,
        "mount_source": nas_mount_source,
    }

    verdict = "pass"
    if nas_mount_source:
        for prefix in forbidden_prefixes:
            if prefix and prefix in nas_mount_source:
                findings.append(
                    {
                        "severity": "fail",
                        "host": "nas",
                        "guest": "-",
                        "issue": "forbidden_volume",
                        "detail": (
                            f"mount source {nas_mount_source!r} touches {prefix!r}; "
                            "Storage Pool 1 / Volume 2 is full and degraded and must never be used"
                        ),
                    }
                )
        if required_prefix and required_prefix not in nas_mount_source:
            findings.append(
                {
                    "severity": "fail",
                    "host": "nas",
                    "guest": "-",
                    "issue": "unexpected_volume",
                    "detail": f"mount source {nas_mount_source!r} is not under {required_prefix!r}",
                }
            )

    if nas_free_bytes is not None:
        if nas_free_bytes < required:
            findings.append(
                {
                    "severity": "fail",
                    "host": "nas",
                    "guest": "-",
                    "issue": "insufficient_capacity",
                    "detail": (
                        f"need {human_bytes(required)} including a {margin_pct:.0f}% margin, "
                        f"NAS reports {human_bytes(nas_free_bytes)} free"
                    ),
                }
            )
        if nas_free_bytes < min_free_gib * 1024**3:
            findings.append(
                {
                    "severity": "fail",
                    "host": "nas",
                    "guest": "-",
                    "issue": "below_absolute_floor",
                    "detail": f"NAS free space is below the {min_free_gib} GiB absolute floor",
                }
            )

    if any(f["severity"] == "fail" for f in findings):
        verdict = "fail"

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "assumptions": {
            "generations": generations,
            "margin_pct": margin_pct,
            "compression_ratio_assumption": compression_ratio,
            "note": (
                "compression_ratio 1.0 assumes zstd saves nothing. Real ratios are usually "
                "0.3-0.6 for sparse Linux guests, but the plan must survive the worst case."
            ),
        },
        "per_host": per_host,
        "totals": {
            "provisioned_bytes": grand_total_raw,
            "provisioned_human": human_bytes(grand_total_raw),
            "per_generation_bytes": per_generation,
            "per_generation_human": human_bytes(per_generation),
            "all_generations_bytes": all_generations,
            "all_generations_human": human_bytes(all_generations),
            "required_with_margin_bytes": required,
            "required_with_margin_human": human_bytes(required),
        },
        "nas": nas,
        "utilisation_pct_after_backup": (pct(required, nas_free_bytes) if nas_free_bytes else None),
        "findings": findings,
        "verdict": verdict,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--discovery", required=True)
    parser.add_argument(
        "--protected",
        required=True,
        help="JSON file mapping host -> [{vmid,name,type}] (rendered from group_vars)",
    )
    parser.add_argument("--out")
    parser.add_argument("--generations", type=int, default=2)
    parser.add_argument("--margin-pct", type=float, default=30.0)
    parser.add_argument("--compression-ratio", type=float, default=1.0)
    parser.add_argument("--nas-free-bytes", type=int)
    parser.add_argument("--nas-total-bytes", type=int)
    parser.add_argument("--nas-mount-source")
    parser.add_argument("--forbidden-prefix", action="append", default=["/volume2"])
    parser.add_argument("--required-prefix", default="/volume1")
    parser.add_argument("--min-free-gib", type=float, default=512.0)
    parser.add_argument("--no-fail", action="store_true", help="always exit 0")
    args = parser.parse_args(argv)

    report = estimate(
        load_json(args.discovery),
        load_json(args.protected),
        args.generations,
        args.margin_pct,
        args.compression_ratio,
        args.nas_free_bytes,
        args.nas_total_bytes,
        args.nas_mount_source,
        args.forbidden_prefix,
        args.required_prefix,
        args.min_free_gib,
    )
    text = dump_json(report, args.out)
    if not args.out:
        print(text, end="")

    eprint(
        f"Capacity verdict: {report['verdict'].upper()}  "
        f"required {report['totals']['required_with_margin_human']}  "
        f"available {report['nas']['free_human']}"
    )
    for finding in report["findings"]:
        eprint(
            f"  [{finding['severity']}] {finding['host']} {finding['guest']}: {finding['detail']}"
        )

    if report["verdict"] == "fail" and not args.no_fail:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
