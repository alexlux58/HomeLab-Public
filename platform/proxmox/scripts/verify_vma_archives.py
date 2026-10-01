#!/usr/bin/env python3
"""Adjudicate the backup verification results collected from the Proxmox hosts.

The hosts do the expensive work (`vma verify`, `zstd -t`, `sha256sum`); this
script decides whether the result is good enough to allow a destructive stage.
The rule that matters: **the number of successfully verified archives must equal
the number of protected guests**, per generation. A backup that was not verified
does not count as a backup.

Exit codes:
    0  every protected guest has a verified archive in every required generation
    5  at least one guest is unverified, missing, or failed verification
"""

from __future__ import annotations

import argparse

from _common import dump_json, eprint, human_bytes, load_json, parse_size, utc_now

REQUIRED_MANIFEST_FIELDS = (
    "source_ip",
    "source_hostname",
    "original_vmid",
    "guest_name",
    "guest_type",
    "archive_path",
    "archive_size_bytes",
    "timestamp",
    "sha256",
    "verification",
    "expected_disks",
    "planned_vmid",
    "planned_restore_node",
    "bridge_dependency",
    "passthrough_dependency",
    "original_running_state",
)


def _entries(manifest: dict) -> list[dict]:
    if isinstance(manifest, list):
        return manifest
    for key in ("archives", "entries", "backups"):
        if isinstance(manifest.get(key), list):
            return manifest[key]
    raise SystemExit("ERROR: manifest has no 'archives' list")


def adjudicate(
    manifest: dict,
    protected: dict,
    required_generations: list[str],
    hosts: list[str] | None,
) -> dict:
    entries = _entries(manifest)
    findings: list[dict] = []
    verified_index: dict[tuple[str, int, str], dict] = {}

    for entry in entries:
        label = f"{entry.get('source_hostname', '?')}/{entry.get('original_vmid', '?')}"
        missing = [f for f in REQUIRED_MANIFEST_FIELDS if f not in entry]
        if missing:
            findings.append(
                {
                    "severity": "fail",
                    "target": label,
                    "issue": "manifest_incomplete",
                    "detail": f"missing fields: {', '.join(missing)}",
                }
            )
            continue

        verification = entry.get("verification") or {}
        ok = bool(verification.get("ok"))
        if not ok:
            findings.append(
                {
                    "severity": "fail",
                    "target": label,
                    "issue": "verification_failed",
                    "detail": (
                        f"{verification.get('method', 'unknown method')} "
                        f"rc={verification.get('rc', '?')}: {verification.get('message', '')}"
                    ),
                }
            )
            continue
        if not entry.get("sha256"):
            findings.append(
                {
                    "severity": "fail",
                    "target": label,
                    "issue": "missing_checksum",
                    "detail": "archive has no SHA-256 checksum",
                }
            )
            continue
        if parse_size(entry.get("archive_size_bytes")) <= 0:
            findings.append(
                {
                    "severity": "fail",
                    "target": label,
                    "issue": "empty_archive",
                    "detail": "archive size is zero",
                }
            )
            continue

        key = (
            str(entry["source_hostname"]),
            int(entry["original_vmid"]),
            str(entry.get("generation", "unknown")),
        )
        previous = verified_index.get(key)
        if previous is None or str(entry.get("timestamp", "")) > str(previous.get("timestamp", "")):
            verified_index[key] = entry

    coverage = []
    for host_name, guests in sorted(protected.items()):
        if hosts and host_name not in hosts:
            continue
        for guest in guests:
            vmid = int(guest["vmid"])
            row = {
                "host": host_name,
                "vmid": vmid,
                "name": guest.get("name"),
                "generations": {},
            }
            for generation in required_generations:
                found = None
                for (h, v, g), entry in verified_index.items():
                    if v != vmid or g != generation:
                        continue
                    # Manifests record the PVE hostname; accept either the
                    # inventory name or the reported hostname.
                    if h != host_name and h != guest.get("source_hostname"):
                        continue
                    found = entry
                    break
                row["generations"][generation] = (
                    {
                        "verified": True,
                        "archive_path": found["archive_path"],
                        "sha256": found["sha256"],
                        "size_human": human_bytes(parse_size(found["archive_size_bytes"])),
                        "timestamp": found["timestamp"],
                        "original_running_state": found.get("original_running_state"),
                    }
                    if found
                    else {"verified": False}
                )
                if not found:
                    findings.append(
                        {
                            "severity": "fail",
                            "target": f"{host_name}/{vmid} ({guest.get('name')})",
                            "issue": "no_verified_archive",
                            "detail": f"no verified archive for generation '{generation}'",
                        }
                    )
            coverage.append(row)

    newest_by_guest = {}
    for (host_name, vmid, generation), entry in verified_index.items():
        cur = newest_by_guest.get((host_name, vmid))
        if cur is None or str(entry.get("timestamp", "")) > str(cur[1].get("timestamp", "")):
            newest_by_guest[(host_name, vmid)] = (generation, entry)

    for (host_name, vmid), (generation, _entry) in sorted(newest_by_guest.items()):
        if "final" in required_generations and generation != "final":
            findings.append(
                {
                    "severity": "fail",
                    "target": f"{host_name}/{vmid}",
                    "issue": "final_backup_not_newest",
                    "detail": (
                        f"newest verified archive is generation '{generation}', "
                        "but the cleanly-stopped 'final' backup must be the newest"
                    ),
                }
            )

    expected_count = sum(len(g) for h, g in protected.items() if not hosts or h in hosts) * len(
        required_generations
    )
    verified_count = sum(
        1 for row in coverage for gen in row["generations"].values() if gen["verified"]
    )

    verdict = "pass" if verified_count == expected_count and not findings else "fail"

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "required_generations": required_generations,
        "counts": {
            "protected_guest_generations_expected": expected_count,
            "verified_archives": verified_count,
            "manifest_entries": len(entries),
            "equal": verified_count == expected_count,
        },
        "coverage": coverage,
        "findings": findings,
        "verdict": verdict,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True, help="artifacts/backup-manifest.json")
    parser.add_argument("--protected", required=True, help="protected guests JSON")
    parser.add_argument(
        "--generation",
        action="append",
        default=None,
        help="generation that must exist and be verified (repeatable)",
    )
    parser.add_argument("--host", action="append", default=None, help="limit to these hosts")
    parser.add_argument("--out")
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args(argv)

    generations = args.generation or ["initial", "final"]
    report = adjudicate(load_json(args.manifest), load_json(args.protected), generations, args.host)
    text = dump_json(report, args.out)
    if not args.out:
        print(text, end="")

    counts = report["counts"]
    eprint(
        f"Backup verification: {report['verdict'].upper()}  "
        f"{counts['verified_archives']}/{counts['protected_guest_generations_expected']} "
        "guest-generations verified"
    )
    for finding in report["findings"]:
        eprint(f"  [{finding['severity']}] {finding['target']}: {finding['detail']}")

    if report["verdict"] == "fail" and not args.no_fail:
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
