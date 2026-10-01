# Prompt: deploy the optimized homelab services stack

Use this prompt in a fresh coding-agent session with access to both
`~/Desktop/Home Lab` and `~/Desktop/Netknife-app`.

```text
Build and deploy an optimized, maintainable home-lab services platform on my
existing Proxmox cluster. Work stage by stage, show evidence at every gate, and
ask before every change to Proxmox, Synology, router/DHCP, DNS, or a live VM.
Never request, store, print, or commit passwords, API keys, private keys, or the
contents of Netknife-app/server/.env.

Read these instruction/context files before acting:
- ~/Desktop/Home Lab/AGENTS.md
- ~/Desktop/Home Lab/CLAUDE.md
- platform/proxmox/docs/rebuild-catalog.md
- ~/Desktop/Netknife-app/AGENTS.md
- ~/Desktop/Netknife-app/README-LOCAL.md
- ~/Desktop/Netknife-app/docs/ARCHITECTURE-LOCAL.md
- ~/Desktop/Netknife-app/docs/ENV.md

Current verified environment:
- Proxmox cluster `homelab`, PVE 9.2, three quorate nodes:
  - `pve1` 192.168.0.11 (friendly DNS alias `nuc-proxmox`)
  - `pve2` 192.168.0.12 (friendly DNS alias `lenovo-proxmox`)
  - `pve3` 192.168.0.13
- Do not rename `pve1` or `pve2` in place. Their names are embedded in
  Corosync and pmxcfs. Friendly names must be DNS aliases only.
- Protected VMs 290 EVENG and 297 ubuntu-vm are on `pve1`.
- Synology `nas1` is 192.168.0.20. Proxmox storage
  `synology-backup` is NFSv4.1 from
  192.168.0.20:/volume1/proxmox-cluster-backups, content type `backup`, with
  `keep-all=1`. It is backup storage, not shared VM-disk storage.
- LAN is 192.168.0.0/24, gateway 192.168.0.1, DNS zone
  lab.example.com. Avoid `.local` because of mDNS.
- No scheduled Proxmox backup jobs exist yet.

Goal architecture:
1. Create one Ubuntu Server 24.04 LTS service VM on `pve2` local-lvm, not on
   Synology NFS. Before choosing an IP, prove it is unused and have me reserve it
   in router DHCP. Suggested initial shape: 4 vCPU, 8 GiB RAM, 120 GiB thin disk,
   VirtIO SCSI, discard and IO thread where supported, CPU type host, QEMU guest
   agent enabled, one VirtIO NIC on vmbr0. Verify that this leaves safe host RAM.
2. Use Docker Engine with the Compose plugin. Keep declarative configuration in
   a new Git repository under /opt/homelab, persistent volumes under
   /srv/homelab/<service>, secrets in mode-0600 env files outside Git, container
   log rotation, health checks, explicit image versions/digests, restart policies,
   resource limits/reservations, and an internal proxy network. Do not expose
   databases or application ports to the LAN unless necessary.
3. Nginx Proxy Manager owns host ports 80 and 443. Every app joins an internal
   Docker network and is published through NPM. If an app cannot share that
   network, bind it to the VM's loopback or a documented high port. Do not give
   multiple Compose projects competing 80/443 bindings.
4. Deploy the core stack first:
   - Nginx Proxy Manager
   - Homepage
   - Uptime Kuma
   - IT-Tools
   - NetKnife from ~/Desktop/Netknife-app
   - Linkding
   - PairDrop
   - Speedtest Tracker
   Add ChangeDetection.io, FreshRSS or Miniflux (choose one), Stirling-PDF,
   Excalidraw, and CyberChef only after reporting measured core utilization and
   confirming capacity with me.
5. For NetKnife, preserve its supported local architecture and invariants:
   browser -> its internal nginx -> Express server/index.js -> unchanged
   Lambda-style handlers. Keep VITE_API_URL=/api, VITE_LOCAL_AUTH=true,
   LOCAL_MEMORY_CACHE=true, and the billing usage stub. Do not add AWS
   infrastructure, Cognito, CloudFront, or DynamoDB. Do not rewrite handlers as
   Express routers. Build with Node 20. Never copy node_modules, server/.env,
   private keys, or caches from the Mac. Transfer source reproducibly, create
   server/.env manually from .env.example with mode 0600, run the documented
   shared-module preparation and frontend build, then smoke-test /health and a
   POST /api/dns request. Put NetKnife behind NPM as
   netknife.lab.example.com without exposing API port 3001 to the LAN.
6. Use these DNS names:
   proxy, home, status, tools, netknife, links, drop, and speed under
   lab.example.com. Add nuc-proxmox -> 192.168.0.11,
   lenovo-proxmox -> 192.168.0.12, and pve3 -> 192.168.0.13 as friendly
   records. The actual Proxmox node names remain unchanged.
7. Configure Synology DNS Server as authoritative for lab.example.com. Create a
   wildcard A record for *.lab.example.com pointing to the service VM/reverse
   proxy, plus explicit infrastructure records. Validate zone answers directly
   against 192.168.0.20 before changing DHCP. Then have me change router DHCP
   to hand out 192.168.0.20 as DNS and renew one test client. Do not configure a
   public resolver as a secondary DHCP DNS server because clients would
   intermittently bypass the private zone. Design a second local DNS resolver
   before advertising a secondary address.
8. Start with HTTP only if needed, but do not place Vaultwarden, Actual Budget,
   documents, or other sensitive apps into real use without HTTPS. Propose a
   maintainable local certificate design (private CA with client trust, or DNS-01
   using a properly controlled public domain). Do not silently create a CA or
   distribute trust roots.
9. Add Uptime Kuma checks for all HTTP endpoints, Proxmox APIs, Synology, DNS
   resolution, gateway reachability, and the NetKnife health endpoint. Build a
   Homepage dashboard with links and health widgets but no embedded credentials.
10. Backups are mandatory before completion:
   - Create a nightly Proxmox backup job for the service VM to
     synology-backup with an explicit reviewed retention policy. Existing
     migration archives must never be deleted.
   - Add application-aware exports/dumps for every database-backed service to a
     staging directory included in the VM backup.
   - Document and perform one restore test into a new temporary VMID without
     deleting any backup archive.
11. Security/quality requirements:
   - LAN-only firewall rules by default; no router port forwards or UPnP.
   - Unique credentials; no defaults; secrets excluded from Git and logs.
   - Unprivileged containers, read-only filesystems and dropped capabilities
     where compatible; automatic security updates on the VM.
   - Do not use Watchtower for blind major upgrades. Provide a controlled update
     script that pulls, validates Compose, snapshots/backs up, deploys, checks
     health, and supports rollback.
   - Run configuration linting, container health checks, DNS tests, HTTP smoke
     tests, reboot persistence tests, and resource measurements.

Stages and stop points:
A. Read-only discovery: cluster capacity, storage, existing IP use, Synology DNS
   capability, NetKnife build/test status, and proposed resource budget.
B. Present exact VM/IP/DNS/storage plan and request approval.
C. Create and harden only the base service VM; validate and request approval.
D. Deploy proxy plus one app at a time, validating each before continuing.
E. Configure DNS records; test directly; request approval before DHCP changes.
F. Configure backups and perform a non-destructive restore test.
G. Produce an operations handoff: architecture, inventory, URLs, ports, volumes,
   secrets locations (names only), update/rollback/restore procedures, measured
   utilization, deferred services, and all remaining risks.

Do not claim success because a container is merely running. Success requires a
healthy endpoint through the reverse proxy, correct DNS, persistence after VM
reboot, verified backups, and documented recovery.
```
