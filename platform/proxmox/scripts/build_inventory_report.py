#!/usr/bin/env python3
"""Render the read-only discovery document as a human-reviewable Markdown report.

Stage 0 produces a large JSON blob. Nobody approves a migration by reading JSON,
so this turns it into the document the operator actually signs off on: what runs
where, what is nested/passed through, what will not be backed up, and what has to
be mapped during restore.
"""

from __future__ import annotations

import argparse

from _common import (
    excluded_disks,
    guest_disk_bytes,
    hosts_of,
    human_bytes,
    load_json,
    parse_size,
    utc_now,
    write_text,
)


def _table(rows: list[list[str]], headers: list[str]) -> str:
    if not rows:
        return "_none_\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in row) + " |")
    return "\n".join(out) + "\n"


def _yesno(value) -> str:
    if value is None:
        return "?"
    return "yes" if value else "no"


def _guest_flags(guest: dict) -> str:
    flags = []
    if guest.get("passthrough", {}).get("hostpci"):
        flags.append("PCI-passthrough")
    if guest.get("passthrough", {}).get("usb"):
        flags.append("USB-passthrough")
    if guest.get("args"):
        flags.append("custom-args")
    if guest.get("efidisk"):
        flags.append("EFI")
    if guest.get("tpmstate"):
        flags.append("TPM")
    if guest.get("cloudinit", {}).get("present"):
        flags.append("cloud-init")
    if guest.get("protection"):
        flags.append("protected")
    if guest.get("snapshots"):
        flags.append(f"{len(guest['snapshots'])}-snapshots")
    if excluded_disks(guest):
        flags.append("**BACKUP=0**")
    for mp in guest.get("mountpoints", []) or []:
        if mp.get("is_bind") or mp.get("is_device"):
            flags.append("**BIND-MOUNT**")
            break
    return ", ".join(flags) or "-"


def render(discovery: dict) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Proxmox discovery report")
    add("")
    add(f"* Generated: `{discovery.get('generated_at', utc_now())}`")
    add(f"* Schema version: `{discovery.get('schema_version', 1)}`")
    add("* Collection mode: **read-only** — no host was modified to produce this report.")
    add("")

    hosts = hosts_of(discovery)

    add("## Host summary")
    add("")
    add(
        _table(
            [
                [
                    name,
                    h.get("system", {}).get("hostname"),
                    h.get("inventory", {}).get("ansible_host"),
                    h.get("system", {}).get("pve_version"),
                    h.get("system", {}).get("kernel"),
                    (h.get("cluster", {}).get("clustered") and "clustered") or "standalone",
                    len(h.get("guests", []) or []),
                    _yesno(h.get("system", {}).get("time_synchronized")),
                ]
                for name, h in sorted(hosts.items())
            ],
            ["inventory", "hostname", "ip", "pve", "kernel", "cluster", "guests", "ntp"],
        )
    )
    add("")

    for name, host in sorted(hosts.items()):
        sysinfo = host.get("system", {})
        host_ip = host.get("inventory", {}).get("ansible_host", "?")
        add(f"## {name} — {sysinfo.get('hostname', '?')} ({host_ip})")
        add("")
        add(f"* FQDN: `{sysinfo.get('fqdn', '?')}`")
        add(f"* Proxmox: `{sysinfo.get('pve_version', '?')}` kernel `{sysinfo.get('kernel', '?')}`")
        add(f"* Cluster: `{host.get('cluster', {}).get('summary', 'standalone')}`")
        add(
            f"* Time sync: `{sysinfo.get('time_source', '?')}` "
            f"synchronized={_yesno(sysinfo.get('time_synchronized'))}"
        )
        root_fs = host.get("filesystems", {}).get("root", {})
        add(
            f"* Root filesystem: {human_bytes(parse_size(root_fs.get('avail_bytes')))} free "
            f"of {human_bytes(parse_size(root_fs.get('size_bytes')))}"
        )
        add("")

        add("### Network")
        add("")
        add(
            _table(
                [
                    [
                        i.get("name"),
                        i.get("type"),
                        ", ".join(i.get("addresses", []) or []) or "-",
                        i.get("mtu"),
                        i.get("state"),
                        _yesno(i.get("vlan_aware")) if i.get("type") == "bridge" else "-",
                        ", ".join(i.get("ports", []) or []) or "-",
                    ]
                    for i in host.get("network", {}).get("interfaces", []) or []
                ],
                ["iface", "type", "addresses", "mtu", "state", "vlan-aware", "ports"],
            )
        )
        add("")
        add(f"* Default gateway: `{host.get('network', {}).get('gateway', '?')}`")
        add(f"* DNS: `{', '.join(host.get('network', {}).get('dns', []) or []) or '?'}`")
        add("")

        add("### Storage")
        add("")
        add(
            _table(
                [
                    [
                        s.get("storage"),
                        s.get("type"),
                        s.get("content"),
                        _yesno(s.get("shared")),
                        _yesno(s.get("active")),
                        human_bytes(parse_size(s.get("total_bytes"))),
                        human_bytes(parse_size(s.get("avail_bytes"))),
                    ]
                    for s in host.get("storage", []) or []
                ],
                ["storage", "type", "content", "shared", "active", "total", "available"],
            )
        )
        add("")

        add("### Guests")
        add("")
        guests = sorted(host.get("guests", []) or [], key=lambda g: int(g.get("vmid", 0)))
        add(
            _table(
                [
                    [
                        g.get("vmid"),
                        g.get("name"),
                        g.get("type"),
                        g.get("status"),
                        human_bytes(guest_disk_bytes(g)),
                        g.get("cpu") or "-",
                        g.get("machine") or "default",
                        g.get("bios") or "seabios",
                        _yesno(g.get("agent_enabled")),
                        _guest_flags(g),
                    ]
                    for g in guests
                ],
                [
                    "vmid",
                    "name",
                    "type",
                    "status",
                    "provisioned",
                    "cpu",
                    "machine",
                    "bios",
                    "agent",
                    "flags",
                ],
            )
        )
        add("")

        add("#### Network interfaces per guest")
        add("")
        nic_rows = []
        for g in guests:
            for nic in g.get("nics", []) or []:
                nic_rows.append(
                    [
                        g.get("vmid"),
                        g.get("name"),
                        nic.get("key"),
                        nic.get("model"),
                        nic.get("mac"),
                        nic.get("bridge"),
                        nic.get("tag") or "-",
                        _yesno(nic.get("link_down")),
                    ]
                )
        add(
            _table(nic_rows, ["vmid", "name", "nic", "model", "mac", "bridge", "vlan", "link-down"])
        )
        add("")

        add("#### Disks per guest")
        add("")
        disk_rows = []
        for g in guests:
            for disk in (g.get("disks", []) or []) + (g.get("unused_disks", []) or []):
                disk_rows.append(
                    [
                        g.get("vmid"),
                        disk.get("key"),
                        disk.get("storage"),
                        disk.get("volume"),
                        human_bytes(parse_size(disk.get("size_bytes") or disk.get("size"))),
                        disk.get("media") or "disk",
                        _yesno(disk.get("backup", True)),
                    ]
                )
        add(_table(disk_rows, ["vmid", "key", "storage", "volume", "size", "media", "backup"]))
        add("")

        passthrough_rows = []
        for g in guests:
            pt = g.get("passthrough", {}) or {}
            for entry in pt.get("hostpci", []) or []:
                passthrough_rows.append([g.get("vmid"), g.get("name"), "hostpci", entry])
            for entry in pt.get("usb", []) or []:
                passthrough_rows.append([g.get("vmid"), g.get("name"), "usb", entry])
            if g.get("args"):
                passthrough_rows.append([g.get("vmid"), g.get("name"), "args", g.get("args")])
        add("#### Passthrough and custom QEMU arguments")
        add("")
        add(_table(passthrough_rows, ["vmid", "name", "kind", "value"]))
        add("")
        add(
            "> Passthrough and `args` are host-specific. A guest restored onto different "
            "hardware will not start until these are re-validated against the new host's "
            "PCI/USB topology."
        )
        add("")

        add("#### Boot order and protection")
        add("")
        add(
            _table(
                [
                    [
                        g.get("vmid"),
                        g.get("name"),
                        _yesno(g.get("onboot")),
                        g.get("startup") or "-",
                        _yesno(g.get("protection")),
                    ]
                    for g in guests
                ],
                ["vmid", "name", "onboot", "startup", "protection"],
            )
        )
        add("")

        snippets = host.get("snippets", []) or []
        add("### Snippets (`/var/lib/vz/snippets`)")
        add("")
        add(
            _table(
                [
                    [
                        s.get("path"),
                        human_bytes(parse_size(s.get("size"))),
                        s.get("sha256", "")[:16],
                    ]
                    for s in snippets
                ],
                ["path", "size", "sha256 (short)"],
            )
        )
        add("")

        modules = ", ".join(host.get("boot", {}).get("relevant_modules", []) or []) or "none"
        add("### Host kernel modules and passthrough prerequisites")
        add("")
        add(f"* GRUB cmdline: `{host.get('boot', {}).get('grub_cmdline', '?')}`")
        add(f"* Loaded modules of interest: `{modules}`")
        add(
            f"* Nested virtualisation: KVM nested = `{host.get('boot', {}).get('kvm_nested', '?')}`"
        )
        add("")

        tasks = host.get("active_tasks", []) or []
        add("### Active Proxmox tasks at collection time")
        add("")
        add(
            _table(
                [[t.get("type"), t.get("id"), t.get("status"), t.get("starttime")] for t in tasks],
                ["type", "id", "status", "started"],
            )
        )
        add("")

        jobs = host.get("backup_jobs", []) or []
        add("### Existing backup jobs")
        add("")
        add(
            _table(
                [
                    [
                        j.get("id"),
                        j.get("schedule"),
                        j.get("storage"),
                        j.get("enabled"),
                        j.get("vmid") or "all",
                    ]
                    for j in jobs
                ],
                ["id", "schedule", "storage", "enabled", "vmid"],
            )
        )
        add("")

    add("## What this report does not tell you")
    add("")
    add(
        "* Whether the data inside a guest is application-consistent — that needs an\n"
        "  app-level dump."
    )
    add(
        "* Whether passthrough hardware exists on the destination host — verify\n"
        "  against `lspci` there."
    )
    add(
        "* Whether a backup boots correctly — checksum and structural verification do not prove "
        "that."
    )
    add("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--out", help="write Markdown here (default: stdout)")
    args = parser.parse_args(argv)

    text = render(load_json(args.discovery))
    write_text(text, args.out)
    if not args.out:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
