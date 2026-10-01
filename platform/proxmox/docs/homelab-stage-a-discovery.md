# Homelab services — Stage A discovery and Stage B proposal

Recorded 2026-08-23. This document covers read-only discovery and the proposed
design. No Proxmox, Synology, router, DNS, or VM configuration was changed
during Stage A.

## Decision summary

- Put the service VM on `pve2`, but first restore the missing cluster storage
  registration for its existing, empty `pve/data` thin pool.
- Use VMID `300`, name `homelab-services`, and candidate address
  `192.168.0.30`. The address is not final until the router confirms that it is
  outside active leases/reservations and reserves it to the VM's generated MAC.
- Start with 4 vCPU, **6 GiB fixed RAM**, and a 120 GiB thin disk. Eight GiB is
  not a safe initial allocation on an 11.47 GiB host: it would leave only about
  1.70 GiB of currently available host memory if the guest touched all of it.
- Use Nginx Proxy Manager's supported SQLite configuration. A separate MariaDB
  container is unnecessary for this small deployment.
- Keep all persistent application state on the VM's local disk. Synology NFS is
  for Proxmox backups only, not live container volumes or SQLite databases.
- Use split-horizon `lab.example.com` on Synology DNS and DNS-01 certificates
  through the existing Cloudflare-hosted public zone. No inbound router port
  forwards are needed.
- Fix and retest the one NetKnife backend authentication-test failure, rebuild
  the stale frontend with Node 20, and deploy its existing nginx-to-Express
  architecture without publishing its ports directly to the LAN.

## Live evidence

### Cluster and capacity

The `homelab` cluster had three online votes and was quorate.

| node | CPU | total RAM | available RAM | guests | relevant local storage |
|---|---:|---:|---:|---|---|
| `pve1` | 12 threads | 31.20 GiB | not a deployment target | stopped 290 and 297 | 460 GiB `local`; no thin pool |
| `pve2` | 8 threads | 11.47 GiB | 9.70 GiB | none | 794.30 GiB empty `pve/data` thin pool |
| `pve3` | 4 threads | 7.64 GiB | 5.88 GiB | none | 49.60 GiB empty `pve/data` thin pool |

Important storage finding: both rebuilt nodes still have healthy, empty LVM-thin
pools, but `local-lvm` is absent from cluster `/etc/pve/storage.cfg`. Cluster
join replaced their standalone storage configuration with the seed node's
cluster-wide configuration. `pvesm scan lvmthin pve` found `data` on both nodes;
`pve2` reported 0.00% data use and 0.24% metadata use.

The proposed correction is one normal node-restricted storage definition:

```text
lvmthin: local-lvm
        thinpool data
        vgname pve
        content images,rootdir
        nodes pve3,pve2
```

This registers existing pools; it does not format or initialize them. Stage C
must verify that both remain 0% used before and after registration.

Other verified facts:

- VMID `300` is free. The cluster's lowest free VMID is `100`, but `300` avoids
  reusing IDs from the discarded guests.
- `pve2` has no ISO or cloud image in `local` yet.
- `synology-backup` is active on all nodes with 10.12 TiB available. Its content
  type is only `backup`, and its storage retention remains `keep-all=1`.
- There are zero scheduled Proxmox backup jobs.
- Protected VMs 290 and 297 remain stopped on `pve1`; this project does not
  move or modify them.

### Address discovery

`192.168.0.30` was the old `lab-k3s` guest address and is a sensible candidate
to reuse. From `pve2`, two ICMP probes received no replies and the neighbor
entry remained `INCOMPLETE`. It did not appear in neighbor caches from any
cluster node or the Synology.

That evidence means **no device was observed at `.30`**. It does not prove that
the router has no dormant lease, static reservation, or powered-off device for
that address. Before the VM's first boot:

1. Create the powered-off VM and record its Proxmox-generated VirtIO MAC.
2. Check the router's active leases and reservations for `.30`.
3. Remove or update any old reservation for the discarded k3s MAC
   `52:54:00:00:00:00`.
4. Reserve `192.168.0.30` to the new VM MAC.
5. Repeat ping and neighbor-cache checks, then boot the VM using DHCP.

### Synology DNS

Synology DSM 7.4.1 has the DNS Server package directory present and is listening
on TCP and UDP port 53 at `192.168.0.20`. Direct queries currently return
`REFUSED` for all of the following:

- authoritative `lab.example.com` SOA lookup;
- `proxy.lab.example.com` A lookup;
- recursive `example.com` A lookup.

DNS Server is therefore installed and running, but the private zone, query
permissions, and recursive forwarding are not ready for clients. DHCP must not
be changed until direct tests against `192.168.0.20` return authoritative lab
answers and successful public answers.

Public DNS verifies that `example.com` is active on Cloudflare nameservers and
that `lab.example.com` is currently NXDOMAIN publicly. This supports a clean
split-horizon zone and Cloudflare DNS-01 certificate validation without any
router port forward.

### NetKnife

The contents of `server/.env` were not read. It must never be copied from the
Mac or committed.

| check | result |
|---|---|
| frontend lint | pass, zero warnings |
| frontend tests | 52/52 pass |
| backend tests | 157/158 pass |
| existing `frontend/dist` | 188 files, 5.6 MiB, but stale |
| required target runtime | Node 20, already declared by API Dockerfile |
| current Mac runtime | Node 26.3.0; not the target validation runtime |

The backend failure is `board handler auth / requires authentication`: the test
expects 401 without claims, but `getUserId()` returns the literal `unknown`, so
the handler treats it as authenticated. The copied `netknife-common` modules
also need regeneration with the documented preparation script.

The current frontend build predates changes to `LoginPage.tsx`, `api.ts`,
`auth.ts`, `vite-env.d.ts`, and `.env.production`; it must be rebuilt. The
current Compose file also publishes host port 80, which would conflict with
Nginx Proxy Manager. Deployment will change only the Compose/network shape:
NetKnife's web nginx remains its front end, its API remains internal on 3001,
and NPM targets the web container on the shared proxy network.

## Proposed Stage C base VM

| setting | value |
|---|---|
| node / VMID / name | `pve2` / `300` / `homelab-services` |
| OS | current signed Ubuntu Server 24.04 LTS Noble amd64 cloud image |
| machine | q35 + OVMF, serial console |
| CPU | 1 socket, 4 cores, type `host` |
| memory | 6144 MiB fixed, no ballooning initially |
| boot disk | 120 GiB on `local-lvm`, VirtIO SCSI single, IO thread, discard, backup enabled |
| cloud-init | separate small drive on `local-lvm`; DHCP for the reserved address |
| NIC | one VirtIO NIC on `vmbr0`; generated MAC recorded before first boot |
| candidate IP | `192.168.0.30/24`, gateway `192.168.0.1` |
| DNS during bootstrap | `192.168.0.1`; switch to `.20` only after DNS validation |
| guest agent | installed in guest and enabled in Proxmox |
| administrator | key-only non-root account using a dedicated guest SSH public key |

The current 9.70 GiB host-available memory minus a fully used 6 GiB guest leaves
about 3.70 GiB for Proxmox and filesystem cache. The 8 GiB proposal would leave
about 1.70 GiB, so it is deferred. Increase the VM only after measured demand or
after physically increasing host RAM.

Base hardening includes unattended security updates, time synchronization,
password and root SSH login disabled, QEMU guest agent, Docker Engine plus the
Compose plugin from Docker's signed repository, IPv4-only LAN listeners, UFW
default deny, and a `DOCKER-USER` policy that permits published 80/443 only from
`192.168.0.0/24`. No UPnP or router port forwards.

## Filesystem, Git, and container design

```text
/opt/homelab/                         declarative Git repository
  compose/<service>/compose.yaml
  apps/netknife/                      sanitized, reproducible source copy
  scripts/{check,backup,update,rollback}.sh
  docs/
/srv/homelab/<service>/               persistent application data
/srv/homelab-backups/staging/         application-aware backup staging
/etc/homelab/secret-store/<service>.env    root:root, mode 0600, outside Git
```

The Git repository contains no secret values, generated databases, certificates,
private keys, caches, `node_modules`, or container volumes. Each image uses an
explicit release tag and an amd64 digest captured in an image lock file. Updates
are deliberate; no Watchtower.

NPM alone binds the VM's LAN address on ports 80 and 443. Port 81 binds only to
`127.0.0.1` for SSH-tunnel bootstrap, then `proxy.lab.example.com` can target
the NPM admin service internally. Every other application uses `expose`, not
`ports`, on a shared `homelab_proxy` bridge. Application-only backends remain on
private Compose networks.

Do not mount `/var/run/docker.sock` into Homepage or Uptime Kuma. Initial
Homepage configuration uses links and HTTP health data; later API widgets use
manually created least-privilege tokens from mode-0600 secret files.

## Core service budget and order

Nginx Proxy Manager 2.15.1 supports SQLite, which removes one database container
from the first deployment. Version tags below are the currently discovered
stable releases; Stage D records the resolved amd64 digest before starting each
container.

| order | service | planned tag/source | memory ceiling | persistent state |
|---:|---|---|---:|---|
| 1 | Nginx Proxy Manager | `jc21/nginx-proxy-manager:2.15.1` | 512 MiB | data, SQLite DB, certificates |
| 2 | Homepage | `ghcr.io/gethomepage/homepage:v1.13.2` | 256 MiB | YAML/config |
| 3 | IT-Tools | current official image pinned by digest | 128 MiB | none |
| 4 | Uptime Kuma | `louislam/uptime-kuma:2.3.2` | 512 MiB | SQLite/data on local disk |
| 5 | NetKnife | local Node-20 build tagged by source hash | 1088 MiB web+API | config only; memory cache |
| 6 | Linkding | `sissbruecker/linkding:1.45.0` | 384 MiB | SQLite and assets |
| 7 | PairDrop | `ghcr.io/schlagmichdoch/pairdrop:v1.11.2` | 256 MiB | minimal config |
| 8 | Speedtest Tracker | `lscr.io/linuxserver/speedtest-tracker:1.14.3` if registry tag verifies | 768 MiB | SQLite/config |

The ceilings total about 3.8 GiB because NPM uses SQLite. Allow roughly 1 GiB
for Ubuntu, Docker, and filesystem cache. After each service, record container
RSS/CPU, guest available memory and swap activity, node available memory, thin
pool use, and endpoint health. Stop adding services if the node has less than
3 GiB available under a representative peak, the VM has less than 1 GiB
available or swaps continuously, or any health check regresses.

Optional services remain deferred until the complete core stack has at least 24
hours of measurements and receives a separate approval.

## NetKnife deployment gate

Before building the image:

1. Correct the unauthenticated `getUserId()` fallback and run the official
   backend suite until all 158 tests pass.
2. Run `scripts/prepare-shared.sh`.
3. Run frontend lint, 52 tests, and a production build under Node 20.
4. Create a sanitized source manifest and SHA-256 checksum. Exclude
   `server/.env`, all `node_modules`, existing `frontend/dist`, private keys,
   caches, AWS infrastructure, and packer artifacts.
5. Create `server/.env` manually on the VM from `.env.example`, mode 0600. Keep
   `VITE_API_URL=/api`, `VITE_LOCAL_AUTH=true`, `LOCAL_FULL_ACCESS=true`, and
   `LOCAL_MEMORY_CACHE=true`.
6. Keep browser -> internal nginx -> Express -> unchanged Lambda handlers.
7. Verify `/health` and `POST /api/dns` internally and through
   `netknife.lab.example.com`. API port 3001 is never published to the LAN.

## DNS and TLS plan

Create a Synology primary zone `lab.example.com` with TTL 300 during rollout:

| record | value |
|---|---|
| `dns` / `nas` | `192.168.0.20` |
| `services` / `proxy` / `home` / `status` / `tools` | `192.168.0.30` |
| `netknife` / `links` / `drop` / `speed` | `192.168.0.30` |
| `*` | `192.168.0.30` |
| `nuc-proxmox` | `192.168.0.11` |
| `lenovo-proxmox` | `192.168.0.12` |
| `pve3` | `192.168.0.13` |

Configure recursive forwarding to two upstream resolvers on the Synology and
allow queries/recursion only from the local networks. Public resolvers are
upstreams, not alternate DHCP DNS addresses. Test SOA, every A record, wildcard,
NXDOMAIN, and public recursion directly against `.20` over UDP and TCP before
asking for the DHCP change.

After that validation, the operator changes router DHCP to advertise only
`192.168.0.20`, renews one test client, and verifies both local and public
resolution. A secondary address waits for a second local resolver.

For HTTPS, use a least-privilege Cloudflare API token entered manually into NPM
to obtain a DNS-01 wildcard certificate for `*.lab.example.com`. The token is
limited to DNS edit on the `example.com` zone and is never stored in Git or
handled by the agent. DNS-01 requires no inbound port forwarding. Authenticated
applications do not receive real credentials or data until HTTPS works.

## Monitoring, backups, and recovery

Uptime Kuma will monitor each proxied HTTP endpoint, NetKnife `/health`, all
three Proxmox HTTPS APIs, Synology HTTPS, DNS A/SOA lookups against `.20`, TCP
53, and gateway reachability. WebSocket support is enabled on the Uptime Kuma
NPM proxy host.

At 02:45, a root-owned in-guest script creates consistent, timestamped exports
for the NPM, Uptime Kuma, Linkding, and Speedtest Tracker SQLite databases plus
archives of configuration and certificates. It writes hashes and a manifest to
`/srv/homelab-backups/staging`. NetKnife has no persistent database; only its
sanitized source/config metadata is staged. Secrets are restored from the
separate protected secret files, not printed in manifests.

At 03:15, Proxmox backs up only VMID 300 to `synology-backup`. Retention is
explicitly `keep-all=1` to comply with the migration project's no-pruning safety
contract. Capacity alerts are required because this is unbounded. The job never
selects VMIDs 290 or 297, and no existing migration archive is deleted.

Restore validation uses VMID `399` with its NIC link set down before first boot,
so the restored `.30` address cannot collide. Validate QEMU agent response,
filesystems, containers, staged export hashes, and configuration from the
console/guest agent. Leave the test guest stopped; this agent does not delete
guests, volumes, or backup archives.

## Approval boundary

The first mutation should be limited to:

1. register the existing `local-lvm` pools for `pve2` and `pve3` in
   cluster storage configuration;
2. revalidate cluster quorum, storage identity, and zero thin-pool use;
3. create powered-off VM 300 on `pve2` with the settings above;
4. record its generated MAC and stop for router reservation confirmation.

No DNS, DHCP, Synology, guest OS, or container change is included in that first
approval.

## Stage C1 execution result

Approved and applied 2026-08-23.

- The cluster remained quorate with three nodes and three votes before and after
  the change.
- `local-lvm` is active only on `pve2` and `pve3`. It maps to each
  node's independent `pve/data` thin pool and is not shared storage.
- Both pools remained at 0.00% data use after registration.
- VMID 300 `homelab-services` was created on `pve2` with 4 vCPU, 6144 MiB
  fixed RAM, q35/OVMF, CPU type `host`, VirtIO SCSI single, QEMU guest-agent
  support enabled, one firewall-enabled VirtIO NIC, protection enabled, and
  `onboot=0`.
- VM 300 is stopped. Its generated MAC is `52:54:00:00:00:00`.
- The second `.30` probe received no replies. This is still observation, not
  proof against a dormant lease or reservation.
- No disk, EFI volume, cloud-init volume, installation image, guest OS, or IP
  configuration was created. This deliberately avoids an unused blank volume
  that would have to be deleted when the verified cloud image is imported.

Required operator gate: reserve `192.168.0.30` to
`52:54:00:00:00:00` in router DHCP, remove/update any old `.30` reservation for
`52:54:00:00:00:00`, and confirm completion before Stage C continues.

The operator confirmed that reservation was saved on 2026-08-23.

## Stage C2 execution result

Approved and applied 2026-08-23. VM 300 was never started.

- Downloaded Canonical's current released
  `ubuntu-24.04-server-cloudimg-amd64.img` and its `SHA256SUMS` and
  `SHA256SUMS.gpg` files from `cloud-images.ubuntu.com`.
- Imported the UEC Image Automatic Signing Key only after enforcing fingerprint
  `D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81` from Canonical's verification
  documentation.
- The checksum file had a good signature made 2026-08-14 with that exact key.
- The image passed its signed checksum. SHA-256:
  `6e40c07ae715f744f84af0bec76415cc1987dd115b4b8de437818561f01a3733`.
- Retained the verified source and verification artifacts at
  `/var/lib/vz/template/iso/ubuntu-24.04-cloudimg-20260823/` on `pve2`.
- Imported the QCOW2 into `local-lvm`, attached it as `scsi0`, and extended the
  thin volume from 3.5 GiB to 120 GiB. The drive uses VirtIO SCSI single,
  IO thread, `io_uring`, cache `none`, discard, and backup enabled; it is not
  marked as an SSD because the physical device is an HDD.
- Added a 4 MiB OVMF EFI variable store with current pre-enrolled keys and a
  4 MiB cloud-init drive. Boot order is only `scsi0`.
- `local-lvm` physical use after import was 1.75 GiB (0.22% of the pool), which
  confirms thin provisioning rather than a 120 GiB physical allocation.
- Cluster quorum remained three nodes/three votes. VM 300 remained protected,
  `onboot=0`, and stopped; `.30` still had no responding neighbor.
- No cloud-init user, SSH key, IP configuration, guest boot, package change, or
  DNS change occurred.

Next gate: select a guest SSH public key, configure cloud-init for DHCP, and
approve first boot plus base-OS hardening.

## Stage C3 execution result

Approved and applied 2026-08-23.

- Configured NoCloud for user `labuser`, key-only SSH, DHCP, router DNS
  `192.168.0.1`, search domain `lab.example.com`, and the reviewed vendor-data
  package/update policy. No cloud-init password was set.
- The dedicated guest public key fingerprint is
  `SHA256:EXAMPLE_FINGERPRINT_REDACTED`. No private key was read,
  copied to a host, or stored in this repository.
- VM 300 received reserved address `192.168.0.30/24` with default gateway
  `192.168.0.1`. Its observed MAC remained `52:54:00:00:00:00`.
- Cloud-init reached `done` with `errors: []`. Its `degraded done` extended
  status consists only of recoverable deprecation notices for Proxmox's
  generated scalar `user` field; package installation and `runcmd` completed.
- Established strict SSH trust before the first login. The ED25519 host-key
  fingerprint obtained through the trusted QEMU guest-agent channel exactly
  matched the network scan:
  `SHA256:EXAMPLE_FINGERPRINT_REDACTED`.
- Installed all current Ubuntu updates and rebooted into
  `6.8.0-138-generic`. The final simulation reported zero pending updates and
  `/var/run/reboot-required` was absent.
- Effective SSH policy denies root, password, keyboard-interactive, empty
  password, X11, agent forwarding, remote TCP forwarding, gateway ports, and
  tunnels; it allows only user `labuser`, public-key authentication, and local TCP
  forwarding. `sshd -t` passed before reload and a fresh strict SSH connection
  passed afterward.
- UFW is enabled with default deny incoming/default allow outgoing. Its only
  inbound rule permits TCP/22 from `192.168.0.0/24`.
- Applied redirect/source-route, martian logging, kernel pointer/dmesg, and
  protected-link sysctl controls. Enabled unattended upgrades, bounded the
  system journal to 512 MiB and 14 days, and enabled a 2 GiB `/swapfile` through
  `swapfile.swap`.
- A persistence reboot passed: guest uptime reset, the reserved address and SSH
  host fingerprint were unchanged, and the guest agent, firewall, swap,
  unattended upgrades, journald, and hardened SSH policy were all active.
- VM 300 remains protected and running with 4 vCPU, 6144 MiB fixed RAM,
  `onboot=0`, and its 120 GiB thin boot disk. `local-lvm` physical use was 0.33%
  after updates and swap allocation.
- No Docker engine, container, application, DNS record, Synology setting,
  Proxmox backup job, or cluster-storage setting was changed in Stage C3.

Next gate: review and explicitly approve Stage D for the container runtime and
service deployment. Keep `onboot=0` until startup behavior and recovery have
been reviewed.
