#!/usr/bin/env python3
"""Read-only Proxmox VE host inventory collector.

Runs ON a Proxmox host and prints one JSON document to stdout. It executes only
read commands and reads only files; nothing here creates, modifies or deletes
anything, and it never touches /etc/pve except to read configuration.

Deliberately standard-library only and Python 3.9 compatible so it runs on both
PVE 8 (Debian 12 / Python 3.11) and PVE 9 (Debian 13 / Python 3.13).

Usage:
    pve_discover.py [--probe-agent] [--task-limit N]
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

SCHEMA_VERSION = 1
QEMU_CONF_DIR = "/etc/pve/qemu-server"
LXC_CONF_DIR = "/etc/pve/lxc"
SNIPPET_DIR = "/var/lib/vz/snippets"

SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)([KMGTP]?)$", re.IGNORECASE)
SIZE_MULT = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
DISK_KEY_RE = re.compile(r"^(scsi|virtio|ide|sata|efidisk|tpmstate|rootfs|mp)\d*$")
NET_KEY_RE = re.compile(r"^net\d+$")
NIC_MODEL_RE = re.compile(
    r"\b(virtio|e1000e?|e1000-82540em|rtl8139|vmxnet3|ne2k_pci|i82551|i82557b|i82559er|pcnet)="
    r"([0-9A-Fa-f:]{17})"
)
INTERESTING_MODULES = (
    "vfio",
    "vfio_pci",
    "vfio_iommu_type1",
    "kvm",
    "kvm_intel",
    "kvm_amd",
    "nf_conntrack",
    "zfs",
    "openvswitch",
    "tun",
    "br_netfilter",
    "8021q",
)


def run(cmd, timeout=60):
    """Run a read-only command. Never raises; returns (rc, stdout, stderr)."""
    if isinstance(cmd, str):
        cmd_list = cmd.split()
    else:
        cmd_list = list(cmd)
    if not shutil.which(cmd_list[0]) and not os.path.isabs(cmd_list[0]):
        return (127, "", "command not found: %s" % cmd_list[0])
    try:
        proc = subprocess.run(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return (
            proc.returncode,
            proc.stdout.decode("utf-8", "replace").strip(),
            proc.stderr.decode("utf-8", "replace").strip(),
        )
    except subprocess.TimeoutExpired:
        return (124, "", "timeout after %ss" % timeout)
    except OSError as exc:
        return (126, "", str(exc))


def out(cmd, timeout=60):
    return run(cmd, timeout)[1]


def jrun(cmd, timeout=60, default=None):
    rc, stdout, _err = run(cmd, timeout)
    if rc != 0 or not stdout:
        return default
    try:
        return json.loads(stdout)
    except ValueError:
        return default


def read_file(path, limit=1024 * 1024):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return None


def listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def sha256_file(path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def parse_size(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    match = SIZE_RE.match(str(value).strip())
    if not match:
        return 0
    number, unit = match.groups()
    return int(float(number) * SIZE_MULT[unit.upper()])


def kv_options(text):
    """Parse `key=value,key2=value2` option strings from a guest config line."""
    options = {}
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, _sep, value = part.partition("=")
            options[key.strip()] = value.strip()
        else:
            options.setdefault("_positional", []).append(part)
    return options


# ---------------------------------------------------------------------------
# Guest configuration
# ---------------------------------------------------------------------------
def parse_guest_config(text):
    """Split a PVE guest config into the current config plus its snapshots."""
    current = {}
    snapshots = {}
    description = []
    section = None
    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith("#"):
            if section is None:
                description.append(line[1:].strip())
            continue
        header = re.match(r"^\[([^\]]+)\]\s*$", line)
        if header:
            section = header.group(1)
            snapshots[section] = {}
            continue
        if ":" not in line:
            continue
        key, _sep, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if section is None:
            current[key] = value
        else:
            snapshots[section][key] = value
    return current, snapshots, "\n".join(description).strip()


def volume_storage(volume):
    """`local-lvm:vm-100-disk-0` -> ('local-lvm', 'vm-100-disk-0'). Host paths -> (None, path)."""
    if not volume:
        return (None, None)
    if volume.startswith("/"):
        return (None, volume)
    if ":" in volume:
        storage, _sep, name = volume.partition(":")
        return (storage, name)
    return (None, volume)


def build_disks(config, volume_sizes):
    disks = []
    unused = []
    efidisk = None
    tpmstate = None
    mountpoints = []

    for key, value in sorted(config.items()):
        if key.startswith("unused"):
            storage, name = volume_storage(value.split(",")[0])
            unused.append(
                {
                    "key": key,
                    "volume": value,
                    "storage": storage,
                    "size_bytes": volume_sizes.get(value, 0),
                    "attached": False,
                }
            )
            continue
        if not DISK_KEY_RE.match(key):
            continue

        parts = value.split(",")
        volume = parts[0]
        options = kv_options(",".join(parts[1:])) if len(parts) > 1 else {}
        storage, _name = volume_storage(volume)
        size_bytes = parse_size(options.get("size")) or volume_sizes.get(volume, 0)
        media = options.get("media", "disk")
        is_cdrom = media == "cdrom" or volume.endswith(".iso") or volume == "none"

        entry = {
            "key": key,
            "volume": volume,
            "storage": storage,
            "size": options.get("size"),
            "size_bytes": size_bytes,
            "media": "cdrom" if is_cdrom else "disk",
            # The absence of backup=0 means the disk IS backed up.
            "backup": options.get("backup", "1") not in ("0", "no", "false"),
            "cache": options.get("cache"),
            "discard": options.get("discard"),
            "iothread": options.get("iothread"),
            "ssd": options.get("ssd"),
            "replicate": options.get("replicate"),
            "raw": value,
        }

        if key.startswith("efidisk"):
            efidisk = entry
            continue
        if key.startswith("tpmstate"):
            tpmstate = entry
            continue
        if key.startswith("mp") or key == "rootfs":
            is_bind = volume.startswith("/")
            mountpoints.append(
                {
                    "key": key,
                    "source": volume,
                    "target": options.get("mp"),
                    "is_bind": is_bind,
                    "is_device": False,
                    "backup_flag": options.get("backup", "1") not in ("0", "no", "false"),
                    "size_bytes": size_bytes,
                    "raw": value,
                }
            )
            if is_bind:
                # Bind mounts are never included in a vzdump archive.
                continue
        disks.append(entry)

    for key, value in sorted(config.items()):
        if key.startswith("dev") and key[3:].isdigit():
            mountpoints.append(
                {
                    "key": key,
                    "source": value.split(",")[0],
                    "target": kv_options(value).get("path"),
                    "is_bind": False,
                    "is_device": True,
                    "backup_flag": False,
                    "size_bytes": 0,
                    "raw": value,
                }
            )

    return disks, unused, efidisk, tpmstate, mountpoints


def build_nics(config):
    nics = []
    for key, value in sorted(config.items()):
        if not NET_KEY_RE.match(key):
            continue
        options = kv_options(value)
        model = None
        mac = None
        match = NIC_MODEL_RE.search(value)
        if match:
            model, mac = match.group(1), match.group(2)
        else:
            for opt_key, opt_value in options.items():
                if re.match(r"^[0-9A-Fa-f:]{17}$", str(opt_value)):
                    model, mac = opt_key, opt_value
                    break
        nics.append(
            {
                "key": key,
                "model": model,
                "mac": mac.upper() if mac else None,
                "bridge": options.get("bridge"),
                "tag": options.get("tag"),
                "trunks": options.get("trunks"),
                "firewall": options.get("firewall") == "1",
                "link_down": options.get("link_down") == "1",
                "mtu": options.get("mtu"),
                "queues": options.get("queues"),
                "rate": options.get("rate"),
                "raw": value,
            }
        )
    return nics


def build_cloudinit(config):
    keys = [k for k in config if k in ("ide2", "scsi1") and "cloudinit" in str(config[k])]
    ci_keys = {
        k: v
        for k, v in config.items()
        if k in ("ciuser", "cipassword", "sshkeys", "ipconfig0", "ipconfig1", "nameserver",
                 "searchdomain", "citype", "cicustom")
    }
    if "cipassword" in ci_keys:
        ci_keys["cipassword"] = "<REDACTED>"
    if "sshkeys" in ci_keys:
        ci_keys["sshkeys"] = "<present>"
    return {
        "present": bool(keys or ci_keys),
        "drive_keys": keys,
        "settings": ci_keys,
        "custom_snippet": ci_keys.get("cicustom"),
    }


def build_guest(vmid, gtype, config_text, statuses, volume_sizes, probe_agent):
    config, snapshots, description = parse_guest_config(config_text)
    disks, unused, efidisk, tpmstate, mountpoints = build_disks(config, volume_sizes)
    nics = build_nics(config)

    hostpci = [f"{k}={v}" for k, v in sorted(config.items()) if k.startswith("hostpci")]
    usb = [f"{k}={v}" for k, v in sorted(config.items()) if re.match(r"^usb\d+$", k)]

    agent_opts = kv_options(config.get("agent", "")) if config.get("agent") else {}
    agent_enabled = str(config.get("agent", "0")).split(",")[0] in ("1", "enabled")

    agent_runtime = None
    if probe_agent and agent_enabled and statuses.get(vmid, {}).get("status") == "running":
        rc, _stdout, err = run(["qm", "agent", str(vmid), "ping"], timeout=15)
        agent_runtime = {"responsive": rc == 0, "error": err if rc else None}

    primary_storage = None
    for disk in disks:
        if disk["media"] == "disk" and disk["storage"]:
            primary_storage = disk["storage"]
            break

    return {
        "vmid": vmid,
        "type": gtype,
        "name": config.get("name") or config.get("hostname") or statuses.get(vmid, {}).get("name"),
        "status": statuses.get(vmid, {}).get("status", "unknown"),
        "uptime": statuses.get(vmid, {}).get("uptime"),
        "description": description,
        "cores": config.get("cores"),
        "sockets": config.get("sockets"),
        "memory": config.get("memory"),
        "balloon": config.get("balloon"),
        "cpu": config.get("cpu"),
        "machine": config.get("machine"),
        "bios": config.get("bios", "seabios"),
        "ostype": config.get("ostype"),
        "boot": config.get("boot"),
        "onboot": config.get("onboot") == "1",
        "startup": config.get("startup"),
        "protection": config.get("protection") == "1",
        "agent_enabled": agent_enabled,
        "agent_options": agent_opts,
        "agent_runtime": agent_runtime,
        "numa": config.get("numa"),
        "hookscript": config.get("hookscript"),
        "args": config.get("args"),
        "vmgenid": config.get("vmgenid"),
        "primary_storage": primary_storage,
        "disks": disks,
        "unused_disks": unused,
        "efidisk": efidisk,
        "tpmstate": tpmstate,
        "mountpoints": mountpoints,
        "nics": nics,
        "passthrough": {"hostpci": hostpci, "usb": usb},
        "cloudinit": build_cloudinit(config),
        "snapshots": [
            {
                "name": name,
                "parent": snap.get("parent"),
                "snaptime": snap.get("snaptime"),
                "vmstate": snap.get("vmstate"),
                "description": snap.get("description"),
            }
            for name, snap in sorted(snapshots.items())
        ],
        "config_keys": sorted(config.keys()),
    }


# ---------------------------------------------------------------------------
# Host-level collection
# ---------------------------------------------------------------------------
def collect_statuses():
    statuses = {}
    for cmd, gtype in ((["qm", "list"], "qemu"), (["pct", "list"], "lxc")):
        rc, stdout, _err = run(cmd)
        if rc != 0:
            continue
        lines = stdout.splitlines()[1:]
        for line in lines:
            fields = line.split()
            if len(fields) < 3:
                continue
            try:
                vmid = int(fields[0])
            except ValueError:
                continue
            if gtype == "qemu":
                statuses[vmid] = {"name": fields[1], "status": fields[2], "type": gtype}
            else:
                statuses[vmid] = {"status": fields[1], "name": fields[2], "type": gtype}
    return statuses


def collect_volume_sizes(nodename, storages):
    """Map volid -> size in bytes.

    `pvesm list --output-format json` does not exist on PVE 8.2 or 9.1 (verified
    on the live hosts), so the read-only API is used instead.
    """
    sizes = {}
    for store in storages:
        sid = store.get("storage")
        if not sid or not store.get("active"):
            continue
        content = str(store.get("content", ""))
        if "images" not in content and "rootdir" not in content:
            continue
        listing = jrun(
            [
                "pvesh", "get", "/nodes/%s/storage/%s/content" % (nodename, sid),
                "--output-format", "json",
            ],
            default=[],
        ) or []
        for item in listing:
            volid = item.get("volid")
            if volid:
                sizes[volid] = int(item.get("size") or 0)
    return sizes


def collect_network():
    addrs = jrun(["ip", "-j", "-d", "addr"], default=[]) or []
    routes = jrun(["ip", "-j", "route"], default=[]) or []
    bridge_links = jrun(["bridge", "-j", "link"], default=[]) or []

    port_map = {}
    for link in bridge_links:
        master = link.get("master")
        if master:
            port_map.setdefault(master, []).append(link.get("ifname"))

    interfaces = []
    for iface in addrs:
        name = iface.get("ifname")
        linkinfo = iface.get("linkinfo") or {}
        kind = linkinfo.get("info_kind") or ("ethernet" if name != "lo" else "loopback")
        info_data = linkinfo.get("info_data") or {}
        addresses = [
            "%s/%s" % (a.get("local"), a.get("prefixlen"))
            for a in iface.get("addr_info", [])
            if a.get("family") in ("inet", "inet6") and a.get("scope") != "link"
        ]
        interfaces.append(
            {
                "name": name,
                "type": "bridge" if kind == "bridge" else kind,
                "mac": (iface.get("address") or "").upper() or None,
                "mtu": iface.get("mtu"),
                "state": iface.get("operstate"),
                "addresses": addresses,
                "master": iface.get("master"),
                "ports": sorted(port_map.get(name, [])),
                "vlan_aware": bool(info_data.get("vlan_filtering")) if kind == "bridge" else None,
                "vlan_protocol": info_data.get("vlan_protocol"),
            }
        )

    gateway = None
    for route in routes:
        if route.get("dst") == "default":
            gateway = route.get("gateway")
            break

    resolv = read_file("/etc/resolv.conf") or ""
    dns = [line.split()[1] for line in resolv.splitlines() if line.startswith("nameserver")]

    return {
        "interfaces": interfaces,
        "routes": routes,
        "gateway": gateway,
        "dns": dns,
        "bridge_vlans": out(["bridge", "vlan", "show"]),
        "interfaces_file": read_file("/etc/network/interfaces"),
        "hosts_file": read_file("/etc/hosts"),
    }


def collect_time():
    td = {}
    rc, stdout, _err = run(["timedatectl", "show"])
    if rc == 0:
        for line in stdout.splitlines():
            if "=" in line:
                key, _sep, value = line.partition("=")
                td[key] = value
    chrony = out(["chronyc", "tracking"], timeout=15)
    return {
        "ntp_enabled": td.get("NTP") == "yes",
        "synchronized": td.get("NTPSynchronized") == "yes",
        "timezone": td.get("Timezone"),
        "source": "chrony" if chrony else td.get("NTP", "unknown"),
        "chrony_tracking": chrony or None,
        "raw": td,
    }


def collect_repositories():
    files = {}
    for path in ["/etc/apt/sources.list"]:
        content = read_file(path)
        if content:
            files[path] = content
    for name in listdir("/etc/apt/sources.list.d"):
        if name.endswith((".list", ".sources")):
            path = os.path.join("/etc/apt/sources.list.d", name)
            files[path] = read_file(path)

    blob = "\n".join(v or "" for v in files.values())
    return {
        "files": files,
        "has_enterprise": "enterprise.proxmox.com" in blob,
        "has_no_subscription": "pve-no-subscription" in blob,
        "has_test": "pve-test" in blob,
        "third_party": sorted(
            {
                line.strip()
                for line in blob.splitlines()
                if line.strip().startswith(("deb ", "URIs:"))
                and "proxmox.com" not in line
                and "debian.org" not in line
            }
        ),
        "held_packages": [p for p in out(["apt-mark", "showhold"]).splitlines() if p],
    }


def collect_filesystems():
    rc, stdout, _err = run(["df", "-B1", "-P", "-x", "tmpfs", "-x", "devtmpfs"])
    entries = []
    root = {}
    if rc == 0:
        for line in stdout.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 6:
                continue
            entry = {
                "source": fields[0],
                "size_bytes": int(fields[1]),
                "used_bytes": int(fields[2]),
                "avail_bytes": int(fields[3]),
                "use_pct": fields[4],
                "mount": fields[5],
            }
            entries.append(entry)
            if entry["mount"] == "/":
                root = entry
    return {"root": root, "all": entries}


def collect_storage(nodename):
    """Storage status via the read-only API.

    `pvesm status --output-format json` is rejected by both PVE 8.2 and 9.1
    ("Unknown option: output-format"); the API endpoint is the portable source.
    """
    result = []
    listing = jrun(
        ["pvesh", "get", "/nodes/%s/storage" % nodename, "--output-format", "json"],
        default=[],
    ) or []
    for store in listing:
        result.append(
            {
                "storage": store.get("storage"),
                "type": store.get("type"),
                "content": store.get("content"),
                "active": bool(store.get("active")),
                "enabled": bool(store.get("enabled")),
                "shared": bool(store.get("shared")),
                "total_bytes": int(store.get("total") or 0),
                "used_bytes": int(store.get("used") or 0),
                "avail_bytes": int(store.get("avail") or 0),
            }
        )
    return result


def collect_snippets():
    snippets = []
    for root, _dirs, files in os.walk(SNIPPET_DIR):
        for name in sorted(files):
            path = os.path.join(root, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            snippets.append(
                {"path": path, "size": size, "sha256": sha256_file(path)}
            )
    return snippets


def collect_boot():
    grub = read_file("/etc/default/grub") or ""
    cmdline = ""
    for line in grub.splitlines():
        if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT"):
            cmdline = line.split("=", 1)[1].strip().strip('"')
    loaded = {line.split()[0] for line in out(["lsmod"]).splitlines()[1:] if line.split()}
    nested = None
    nested_params = (
        "/sys/module/kvm_intel/parameters/nested",
        "/sys/module/kvm_amd/parameters/nested",
    )
    for param in nested_params:
        value = read_file(param)
        if value:
            nested = value.strip()
            break
    modprobe = {}
    for name in listdir("/etc/modprobe.d"):
        path = os.path.join("/etc/modprobe.d", name)
        modprobe[path] = read_file(path)
    return {
        "grub_cmdline": cmdline,
        "grub_file": grub,
        "cmdline_active": (read_file("/proc/cmdline") or "").strip(),
        "modules_file": read_file("/etc/modules"),
        "modprobe_d": modprobe,
        "relevant_modules": sorted(loaded & set(INTERESTING_MODULES)),
        "kvm_nested": nested,
        "iommu_groups": len(listdir("/sys/kernel/iommu_groups")),
    }


def collect_hardware():
    by_id = []
    rc, stdout, _err = run(["ls", "-l", "/dev/disk/by-id"])
    if rc == 0:
        for line in stdout.splitlines()[1:]:
            if "->" in line:
                name, _arrow, target = line.rpartition(" -> ")
                by_id.append({"id": name.split()[-1], "target": target})
    return {
        "lsblk": jrun(
            ["lsblk", "-J", "-b", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL,SERIAL"],
            default={},
        ),
        "lspci": out(["lspci", "-nnk"]),
        "lsusb": out(["lsusb"]),
        "disk_by_id": by_id,
        "zpool_status": out(["zpool", "status"], timeout=30) or None,
        "lvs": out(["lvs", "-a", "-o", "+devices", "--noheadings"], timeout=30) or None,
        "cpuinfo_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in (read_file("/proc/cpuinfo") or "").splitlines()
                if line.startswith("model name")
            ),
            None,
        ),
    }


def collect_cluster(nodename):
    rc, stdout, stderr = run(["pvecm", "status"], timeout=30)
    clustered = rc == 0 and "Cluster information" in stdout
    nodes = out(["pvecm", "nodes"]) if clustered else ""
    return {
        "clustered": clustered,
        "summary": "clustered" if clustered else "standalone",
        "status_raw": stdout or stderr,
        "nodes_raw": nodes,
        "corosync_conf_present": os.path.exists("/etc/pve/corosync.conf"),
        "nodename": nodename,
        "quorate": "Quorate:          Yes" in stdout or "Quorate: Yes" in stdout,
    }


def collect_tasks(nodename, limit):
    tasks = jrun(
        [
            "pvesh", "get", "/nodes/%s/tasks" % nodename,
            "--limit", str(limit), "--output-format", "json",
        ],
        timeout=45,
        default=[],
    ) or []
    active = [
        {
            "type": t.get("type"),
            "id": t.get("id"),
            "user": t.get("user"),
            "status": t.get("status", "running"),
            "starttime": t.get("starttime"),
            "upid": t.get("upid"),
        }
        for t in tasks
        if t.get("endtime") is None
    ]
    return active


def collect_backup_jobs():
    jobs = []
    jobs_cfg = read_file("/etc/pve/jobs.cfg") or ""
    current = None
    for line in jobs_cfg.splitlines():
        header = re.match(r"^(vzdump):\s*(\S+)", line)
        if header:
            current = {"id": header.group(2), "type": header.group(1)}
            jobs.append(current)
            continue
        if current is not None and line.strip() and ":" in line:
            key, _sep, value = line.strip().partition(":")
            current[key.strip()] = value.strip()
        elif not line.strip():
            current = None
    cron = read_file("/etc/pve/vzdump.cron")
    if cron:
        for line in cron.splitlines():
            if line.strip() and not line.startswith("#") and "vzdump" in line:
                jobs.append({"id": "legacy-cron", "type": "cron", "schedule": line.strip()})
    return jobs


def main():
    parser = argparse.ArgumentParser(description="Read-only Proxmox discovery")
    parser.add_argument(
        "--probe-agent",
        action="store_true",
        help="also ping the QEMU guest agent of running guests (still read-only)",
    )
    parser.add_argument("--task-limit", type=int, default=50)
    args = parser.parse_args()

    nodename = out(["hostname"]) or "unknown"
    pveversion = out(["pveversion"])
    match = re.search(r"pve-manager/(\S+)", pveversion or "")
    version = match.group(1) if match else pveversion

    statuses = collect_statuses()
    storages = collect_storage(nodename)
    volume_sizes = collect_volume_sizes(nodename, storages)

    guests = []
    for conf_dir, gtype in ((QEMU_CONF_DIR, "qemu"), (LXC_CONF_DIR, "lxc")):
        for name in listdir(conf_dir):
            if not name.endswith(".conf"):
                continue
            try:
                vmid = int(name[:-5])
            except ValueError:
                continue
            text = read_file(os.path.join(conf_dir, name))
            guests.append(build_guest(vmid, gtype, text, statuses, volume_sizes, args.probe_agent))

    document = {
        "schema_version": SCHEMA_VERSION,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "collector_version": "1.0.0",
        "read_only": True,
        "system": {
            "hostname": nodename,
            "fqdn": out(["hostname", "-f"]) or nodename,
            "kernel": out(["uname", "-r"]),
            "pve_version": version,
            "pve_version_full": out(["pveversion", "-v"]),
            "pve_major": (
                int(str(version).split(".")[0]) if str(version)[:1].isdigit() else None
            ),
            "debian_version": (read_file("/etc/debian_version") or "").strip(),
            "uptime_seconds": float((read_file("/proc/uptime") or "0").split()[0]),
            "time_synchronized": None,
            "time_source": None,
        },
        "cluster": collect_cluster(nodename),
        "network": collect_network(),
        "time": collect_time(),
        "repositories": collect_repositories(),
        "filesystems": collect_filesystems(),
        "storage": storages,
        "storage_cfg": read_file("/etc/pve/storage.cfg"),
        "datacenter_cfg": read_file("/etc/pve/datacenter.cfg"),
        "guests": sorted(guests, key=lambda g: g["vmid"]),
        "snippets": collect_snippets(),
        "boot": collect_boot(),
        "hardware": collect_hardware(),
        "active_tasks": collect_tasks(nodename, args.task_limit),
        "backup_jobs": collect_backup_jobs(),
        "firewall": {
            "cluster_fw": read_file("/etc/pve/firewall/cluster.fw"),
            "host_fw": read_file("/etc/pve/local/host.fw"),
            "guest_fw_files": listdir("/etc/pve/firewall"),
        },
    }
    document["system"]["time_synchronized"] = document["time"]["synchronized"]
    document["system"]["time_source"] = document["time"]["source"]

    json.dump(document, sys.stdout, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
