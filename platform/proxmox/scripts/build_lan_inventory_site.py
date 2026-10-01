#!/usr/bin/env python3
"""Generate a self-contained LAN inventory dashboard.

Reads the read-only discovery document and a LAN scan, correlates guest MAC
addresses against the scan to resolve VM IP addresses, and emits ONE static HTML
file with no external assets. It is designed to be served by Synology Web
Station (or any static server) and to keep working when the Proxmox cluster is
mid-migration and half the nodes are down.

The page shows, for every host and guest:
  * the exact `ssh` command using the migration key
  * the matching `ssh-copy-id` command for installing that key
  * one-click links to every web endpoint discovered or configured

Nothing secret goes into the page: only the *public* key path and the commands.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from _common import human_bytes, load_json, normalize_mac, parse_size, utc_now

# Just enough OUI data to label the things a homelab actually contains.
OUI = {
    "52:54:00": "Proxmox VE (virtual NIC)",
    "90:09:D0": "Synology",
    "B8:27:EB": "Raspberry Pi Foundation",
    "DC:A6:32": "Raspberry Pi Trading",
    "E4:5F:01": "Raspberry Pi Trading",
    "30:BF:22": "Intel",
    "54:E1:AD": "Intel",
    "18:66:DA": "pve3",
    "68:5E:DD": "Apple",
    "28:94:01": "Ubiquiti",
    "80:B9:7A": "Ubiquiti",
    "08:5B:0E": "Ubiquiti",
    "94:B3:F7": "Espressif (IoT)",
    "54:07:7D": "TP-Link",
    "88:00:33": "Samsung",
}

DEFAULT_SSH_PORT = 22

PORT_LABEL = {
    22: "SSH",
    80: "HTTP",
    2258: "SSH (Synology)",
    443: "HTTPS",
    3000: "Grafana?",
    5000: "DSM / HTTP",
    5001: "DSM (HTTPS)",
    6443: "Kubernetes API",
    8000: "HTTP-alt",
    8006: "Proxmox VE",
    8080: "HTTP-alt",
    8443: "HTTPS-alt",
    9090: "Cockpit / Prometheus?",
    9100: "node_exporter?",
}
WEB_PORTS = {
    80: "http",
    443: "https",
    3000: "http",
    5000: "http",
    5001: "https",
    8000: "http",
    8006: "https",
    8080: "http",
    8443: "https",
    9090: "http",
}


def resolve_ssh_key(explicit: str | None, group_vars: str) -> str:
    """Derive the key path from `ssh_key_name` in group_vars.

    The filename is deliberately defined in exactly one place in this repository
    (a unit test enforces it), so this reads it rather than repeating it.
    """
    if explicit:
        return explicit
    path = Path(group_vars)
    if not path.is_file():
        raise SystemExit(f"ERROR: {path} not found; pass --ssh-key explicitly")
    match = re.search(r"^ssh_key_name:\s*(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise SystemExit(f"ERROR: no ssh_key_name in {path}; pass --ssh-key explicitly")
    return f"~/.ssh/{match.group(1)}"


def vendor_for(mac: str) -> str:
    return OUI.get(mac[:8].upper(), "")


def port_flag(port: int, flag: str = "-p") -> str:
    """Emit an explicit port flag only when the target is not on 22.

    The Synology moved DSM's Terminal service to 2258, so a command that omits
    the port silently targets a closed port.
    """
    return "" if port == DEFAULT_SSH_PORT else f"{flag} {port} "


def ssh_cmd(
    user: str,
    target: str,
    key: str,
    alias: str | None = None,
    port: int = DEFAULT_SSH_PORT,
) -> str:
    if alias:
        return f"ssh {alias}"
    return f"ssh {port_flag(port)}-i {key} -o IdentitiesOnly=yes {user}@{target}"


def copy_id_cmd(user: str, target: str, key: str, port: int = DEFAULT_SSH_PORT) -> str:
    return f"ssh-copy-id {port_flag(port)}-i {key}.pub {user}@{target}"


def build_model(discovery: dict, lan: list, overlay: dict, key: str) -> dict:
    by_ip = overlay.get("by_ip", {})
    default_user = overlay.get("defaults", {}).get("ssh_user", "root")

    # MAC -> scan entry, so guests can be located on the LAN.
    mac_to_scan = {normalize_mac(e["mac"]): e for e in lan if normalize_mac(e.get("mac"))}

    hosts = []
    guests = []
    for host_name, host in sorted(discovery.get("hosts", {}).items()):
        inv = host.get("inventory", {})
        ip = inv.get("ansible_host", "")
        cfg = by_ip.get(ip, {})
        sysinfo = host.get("system", {})
        hosts.append(
            {
                "name": sysinfo.get("hostname", host_name),
                "ip": ip,
                "role": "proxmox",
                "version": sysinfo.get("pve_version", ""),
                "kernel": sysinfo.get("kernel", ""),
                "alias": cfg.get("ssh_alias"),
                "ssh": ssh_cmd(default_user, ip, key),
                "ssh_alias_cmd": f"ssh {cfg['ssh_alias']}" if cfg.get("ssh_alias") else None,
                "copy_id": copy_id_cmd(default_user, ip, key),
                "endpoints": cfg.get("endpoints", []),
                "guest_count": len(host.get("guests", []) or []),
                "note": inv.get("role_note", ""),
            }
        )

        for g in sorted(host.get("guests", []) or [], key=lambda x: int(x.get("vmid", 0))):
            nics = g.get("nics", []) or []
            macs = [normalize_mac(n.get("mac")) for n in nics if normalize_mac(n.get("mac"))]
            found = next((mac_to_scan[m] for m in macs if m in mac_to_scan), None)
            guest_ip = found["ip"] if found else None
            disks = sum(
                parse_size(d.get("size_bytes") or d.get("size"))
                for d in g.get("disks", []) or []
                if d.get("media") != "cdrom"
            )
            endpoints = []
            if found:
                for p in found.get("open_ports", []):
                    scheme = WEB_PORTS.get(p)
                    if scheme:
                        endpoints.append(
                            {
                                "label": f"{PORT_LABEL.get(p, p)} :{p}",
                                "url": f"{scheme}://{guest_ip}:{p}",
                            }
                        )
            guests.append(
                {
                    "host": sysinfo.get("hostname", host_name),
                    "vmid": g.get("vmid"),
                    "name": g.get("name"),
                    "status": g.get("status"),
                    "type": g.get("type"),
                    "macs": macs,
                    "bridges": sorted({n.get("bridge") for n in nics if n.get("bridge")}),
                    "ip": guest_ip,
                    "disk_human": human_bytes(disks),
                    "ssh": ssh_cmd(default_user, guest_ip, key) if guest_ip else None,
                    "copy_id": copy_id_cmd(default_user, guest_ip, key) if guest_ip else None,
                    "endpoints": endpoints,
                    "isolated": all(n.get("link_down") for n in nics) if nics else False,
                }
            )

    known_ips = {h["ip"] for h in hosts}
    devices = []
    for e in lan:
        ip = e["ip"]
        if ip in known_ips:
            continue
        mac = normalize_mac(e.get("mac")) or e.get("mac", "")
        cfg = by_ip.get(ip, {})
        user = cfg.get("ssh_user", default_user)
        ssh_port = int(cfg.get("ssh_port", DEFAULT_SSH_PORT))
        ports = e.get("open_ports", []) or []
        endpoints = list(cfg.get("endpoints", []))
        for p in ports:
            scheme = WEB_PORTS.get(p)
            if scheme and not any(str(p) in ep.get("url", "") for ep in endpoints):
                endpoints.append(
                    {"label": f"{PORT_LABEL.get(p, p)} :{p}", "url": f"{scheme}://{ip}:{p}"}
                )
        devices.append(
            {
                "ip": ip,
                "mac": mac,
                "vendor": cfg.get("vendor") or vendor_for(mac),
                "name": cfg.get("name", ""),
                "role": cfg.get("role", "unknown"),
                "rdns": e.get("rdns", ""),
                "ports": ports,
                "has_ssh": ssh_port in ports,
                "ssh": None
                if cfg.get("skip_ssh")
                else ssh_cmd(user, ip, key, cfg.get("ssh_alias"), ssh_port),
                "copy_id": None if cfg.get("skip_ssh") else copy_id_cmd(user, ip, key, ssh_port),
                "endpoints": endpoints,
            }
        )

    return {
        "generated_at": utc_now(),
        "key": key,
        "hosts": hosts,
        "guests": guests,
        "devices": sorted(devices, key=lambda d: [int(x) for x in d["ip"].split(".")]),
    }


def e(text) -> str:
    return html.escape("" if text is None else str(text))


def cmd_cell(cmd: str | None) -> str:
    if not cmd:
        return '<span class="muted">—</span>'
    return (
        f'<div class="cmd"><code>{e(cmd)}</code>'
        f'<button class="copy" data-cmd="{e(cmd)}" title="Copy">copy</button></div>'
    )


def links_cell(endpoints: list) -> str:
    if not endpoints:
        return '<span class="muted">—</span>'
    return " ".join(
        f'<a class="btn" href="{e(x["url"])}" target="_blank" rel="noopener">{e(x["label"])}</a>'
        for x in endpoints
    )


def render(model: dict) -> str:
    hosts_rows = "".join(
        f"""<tr data-search="{e(h["name"] + " " + h["ip"] + " proxmox")}">
<td><strong>{e(h["name"])}</strong><div class="sub">{e(h["note"])}</div></td>
<td class="nowrap"><code class="ip">{e(h["ip"])}</code></td>
<td>{e(h["version"])}<div class="sub">{e(h["kernel"])}</div></td>
<td>{h["guest_count"]}</td>
<td>{cmd_cell(h["ssh_alias_cmd"] or h["ssh"])}{cmd_cell(h["ssh"]) if h["ssh_alias_cmd"] else ""}</td>
<td>{cmd_cell(h["copy_id"])}</td>
<td>{links_cell(h["endpoints"])}</td></tr>"""
        for h in model["hosts"]
    )

    guest_rows = "".join(
        f"""<tr data-search="{e(g["name"] + " " + str(g["vmid"]) + " " + g["host"] + " " + (g["ip"] or ""))}">
<td><span class="pill {e(g["status"])}">{e(g["status"])}</span></td>
<td>{e(g["vmid"])}</td>
<td><strong>{e(g["name"])}</strong>{' <span class="tag warn">ISOLATED</span>' if g["isolated"] else ""}</td>
<td>{e(g["host"])}</td>
<td class="nowrap">{f'<code class="ip">{e(g["ip"])}</code>' if g["ip"] else '<span class="muted">not on LAN</span>'}</td>
<td><code class="mac">{e(", ".join(g["macs"]))}</code><div class="sub">{e(", ".join(g["bridges"]))}</div></td>
<td>{e(g["disk_human"])}</td>
<td>{cmd_cell(g["ssh"])}</td>
<td>{cmd_cell(g["copy_id"])}</td>
<td>{links_cell(g["endpoints"])}</td></tr>"""
        for g in model["guests"]
    )

    device_rows = "".join(
        f"""<tr data-search="{e((d["name"] or "") + " " + d["ip"] + " " + d["mac"] + " " + (d["vendor"] or ""))}">
<td><strong>{e(d["name"] or d["rdns"] or "unidentified")}</strong><div class="sub">{e(d["role"])}</div></td>
<td class="nowrap"><code class="ip">{e(d["ip"])}</code></td>
<td><code class="mac">{e(d["mac"])}</code><div class="sub">{e(d["vendor"])}</div></td>
<td>{" ".join(f'<span class="tag">{e(PORT_LABEL.get(p, p))}</span>' for p in d["ports"]) or '<span class="muted">—</span>'}</td>
<td>{cmd_cell(d["ssh"]) if d["has_ssh"] else '<span class="muted">no SSH</span>'}</td>
<td>{cmd_cell(d["copy_id"]) if d["has_ssh"] else '<span class="muted">—</span>'}</td>
<td>{links_cell(d["endpoints"])}</td></tr>"""
        for d in model["devices"]
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LAN Inventory</title>
<style>
:root{{--bg:#f6f7f9;--fg:#1c1e21;--card:#fff;--line:#e2e5e9;--muted:#6b7280;--accent:#2563eb;--code:#f1f3f5;--warn:#b45309}}
@media(prefers-color-scheme:dark){{:root{{--bg:#15171a;--fg:#e6e8eb;--card:#1d2024;--line:#2c3036;--muted:#9099a6;--accent:#5b9bff;--code:#22262b;--warn:#f0a13a}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:1600px;margin:0 auto;padding:24px}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:32px 0 10px;display:flex;gap:10px;align-items:center}}
.meta{{color:var(--muted);font-size:13px;margin-bottom:18px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%;min-width:900px}}
th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600;white-space:nowrap}}
tr:last-child td{{border-bottom:0}}
code{{background:var(--code);padding:2px 6px;border-radius:4px;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}}
.mac{{font-size:11px;white-space:nowrap;word-break:normal}}
.ip{{white-space:nowrap;word-break:normal}}
td.nowrap{{white-space:nowrap}}
.sub{{color:var(--muted);font-size:11px;margin-top:3px}}
.muted{{color:var(--muted)}}
.cmd{{display:flex;gap:6px;align-items:flex-start;margin-bottom:4px}}
.copy{{background:transparent;border:1px solid var(--line);color:var(--muted);border-radius:4px;font-size:11px;padding:2px 7px;cursor:pointer;flex-shrink:0}}
.copy:hover{{border-color:var(--accent);color:var(--accent)}} .copy.ok{{color:#16a34a;border-color:#16a34a}}
.btn{{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:4px 10px;border-radius:5px;font-size:12px;margin:0 4px 4px 0;white-space:nowrap}}
.btn:hover{{opacity:.85}}
.pill{{font-size:11px;padding:2px 8px;border-radius:99px;background:var(--code);text-transform:capitalize}}
.pill.running{{background:#16a34a22;color:#16a34a}} .pill.stopped{{background:#6b728022;color:var(--muted)}}
.tag{{font-size:10px;background:var(--code);padding:2px 6px;border-radius:4px;margin-right:3px;display:inline-block}}
.tag.warn{{background:var(--warn);color:#fff}}
#q{{width:100%;padding:10px 14px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font-size:14px;margin-bottom:6px}}
.note{{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:8px;padding:12px 16px;margin:20px 0;font-size:13px}}
.count{{font-size:12px;color:var(--muted);font-weight:400}}
</style></head><body><div class="wrap">
<h1>LAN Inventory</h1>
<div class="meta">Generated {e(model["generated_at"])} &middot; key <code>{e(model["key"])}</code> &middot;
{len(model["hosts"])} hosts &middot; {len(model["guests"])} guests &middot; {len(model["devices"])} other devices</div>
<input id="q" type="search" placeholder="Filter by name, IP, MAC, VMID&hellip;" autocomplete="off">

<h2>Proxmox hosts <span class="count">{len(model["hosts"])}</span></h2>
<div class="card"><table><thead><tr>
<th>Host</th><th>IP</th><th>Version</th><th>Guests</th><th>SSH</th><th>Install key</th><th>Endpoints</th>
</tr></thead><tbody>{hosts_rows}</tbody></table></div>

<h2>Virtual machines <span class="count">{len(model["guests"])}</span></h2>
<div class="card"><table><thead><tr>
<th>State</th><th>VMID</th><th>Name</th><th>Host</th><th>IP</th><th>MAC / bridge</th><th>Disk</th>
<th>SSH</th><th>Install key</th><th>Endpoints</th>
</tr></thead><tbody>{guest_rows}</tbody></table></div>

<h2>Other LAN devices <span class="count">{len(model["devices"])}</span></h2>
<div class="card"><table><thead><tr>
<th>Device</th><th>IP</th><th>MAC / vendor</th><th>Open ports</th><th>SSH</th><th>Install key</th><th>Endpoints</th>
</tr></thead><tbody>{device_rows}</tbody></table></div>

<div class="note"><strong>Keep this page on the LAN.</strong> It lists internal addresses and login commands.
Do not port-forward it or publish it. It contains no private key and no password &mdash; only the public-key path
and the commands &mdash; but it is still a map of your network.<br><br>
A VM shows <em>not on LAN</em> when it is powered off or has never sent traffic; its MAC is still listed.
Edit <code>site/devices.json</code> to name unidentified devices, set their SSH user, or add endpoints,
then re-run the generator.</div>
</div><script>
document.getElementById('q').addEventListener('input',function(){{
  var v=this.value.toLowerCase();
  document.querySelectorAll('tbody tr').forEach(function(r){{
    r.style.display=(r.dataset.search||'').toLowerCase().includes(v)?'':'none';
  }});
}});
document.querySelectorAll('.copy').forEach(function(b){{
  b.addEventListener('click',function(){{
    var t=b.dataset.cmd;
    var done=function(){{b.textContent='copied';b.classList.add('ok');
      setTimeout(function(){{b.textContent='copy';b.classList.remove('ok')}},1200)}};
    if(navigator.clipboard&&window.isSecureContext){{navigator.clipboard.writeText(t).then(done)}}
    else{{var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);
      a.select();document.execCommand('copy');a.remove();done()}}
  }});
}});
</script></body></html>"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--discovery", default="artifacts/discovery.json")
    p.add_argument("--lan", default="artifacts/lan-inventory.json")
    p.add_argument("--overlay", default="site/devices.json")
    p.add_argument("--ssh-key", help="default: derived from ssh_key_name in group_vars")
    p.add_argument("--group-vars", default="inventory/group_vars/all.yml")
    p.add_argument("--out", default="site/index.html")
    args = p.parse_args(argv)

    overlay = load_json(args.overlay) if Path(args.overlay).is_file() else {}
    key = resolve_ssh_key(args.ssh_key, args.group_vars)
    model = build_model(load_json(args.discovery), load_json(args.lan), overlay, key)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(model), encoding="utf-8")
    print(
        f"wrote {out}  ({len(model['hosts'])} hosts, {len(model['guests'])} guests, "
        f"{len(model['devices'])} devices)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
